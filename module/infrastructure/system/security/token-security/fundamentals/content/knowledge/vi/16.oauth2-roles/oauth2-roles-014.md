# Quan hệ giữa role và trust boundary

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **bốn vai trò trong OAuth 2.0** (Resource Owner, Client, Authorization Server, Resource Server) với **role trong RBAC** như admin, editor, viewer.
- Giải thích **trust boundary** là ranh giới mà dữ liệu, credential hoặc tuyên bố danh tính đi từ một vùng/đối tượng có mức tin cậy khác sang một vùng/đối tượng khác.
- Xác định ai được quyền **đề nghị truy cập, phát hành token, xác minh token và đưa ra quyết định phân quyền trên tài nguyên**, thay vì đặt quá nhiều niềm tin vào một thành phần.
- Thiết kế các bước kiểm tra **issuer, audience, token type, scope, subject, client identity, tenant và permission** tại đúng ranh giới tin cậy.
- Nhận diện những lỗi như **confused deputy, token substitution, tin role do frontend tự khai, nhầm service principal với user principal, cross-tenant access** và tin mù quáng vào header của gateway.
- Sử dụng sơ đồ luồng, bảng trách nhiệm, mã giả và negative tests để review kiến trúc OAuth 2.0/OIDC.

## 1. Hai ý nghĩa khác nhau của từ role

Khi thảo luận về token security, từ **role** thường được dùng cho hai lớp hoàn toàn khác nhau.

**Lớp thứ nhất: protocol role — vai trò trong giao thức OAuth 2.0.** RFC 6749 định nghĩa các bên tham gia dựa trên **trách nhiệm trong luồng ủy quyền**:

- **Resource Owner:** thực thể có thể cho phép truy cập một tài nguyên được bảo vệ.
- **Client:** ứng dụng yêu cầu truy cập tài nguyên; có thể hành động thay mặt resource owner hoặc theo quyền của chính client.
- **Authorization Server (AS):** bên xác minh grant/client, xử lý sự ủy quyền và phát hành access token.
- **Resource Server (RS):** bên lưu trữ/bảo vệ tài nguyên, nhận access token và đánh giá request truy cập.

**Lớp thứ hai: authorization role — vai trò phân quyền nghiệp vụ, thường thuộc RBAC.** Đây là các vai trò như:

~~~text
order_viewer
order_manager
payment_approver
tenant_admin
~~~

Những tên này **không phải bốn role chuẩn của OAuth**; chúng là dữ liệu/chính sách ứng dụng dùng để quyết định một principal được làm gì.

| Câu hỏi | Protocol role của OAuth 2.0 | Role nghiệp vụ (RBAC) |
| --- | --- | --- |
| Đang mô tả điều gì? | Thành phần nào tham gia một giao thức và có trách nhiệm gì. | Chủ thể có nhóm quyền nghiệp vụ nào. |
| Ví dụ | Client, Authorization Server, Resource Server. | order_viewer, tenant_admin. |
| Được định nghĩa ở đâu? | OAuth 2.0 framework và profile liên quan. | Mô hình phân quyền của tổ chức/ứng dụng. |
| Role quyết định quyền duyệt đơn hàng? | **Không trực tiếp.** | Có thể góp phần, cùng policy và dữ liệu bản ghi. |
| Có thể thay role bằng scope? | Không: protocol role khác phạm vi token. | Không: scope OAuth và RBAC role giải quyết các lớp khác nhau. |

Một developer có thể nói “AS có role cấp token” và “Alice có role admin”. Hai mệnh đề đều có thể đúng, nhưng **không được suy ra Alice là Authorization Server hoặc access token của Alice có quyền ở mọi API**.

## 2. Trust boundary là gì?

**Trust boundary** là ranh giới giữa hai ngữ cảnh có **quyền kiểm soát, nguồn tin cậy hoặc mô hình đe dọa khác nhau**. Khi dữ liệu đi qua ranh giới này, bên nhận phải kiểm tra những giả định mà trước đó chưa được bảo đảm.

Ví dụ:

~~~text
Trình duyệt do người dùng kiểm soát
    | [trust boundary A]
    v
Backend của ứng dụng
    | [trust boundary B]
    v
Authorization Server
    | [trust boundary C]
    v
Resource Server / Business API
    | [trust boundary D]
    v
Cơ sở dữ liệu và policy của tài nguyên
~~~

Đây là sơ đồ khái niệm; trong thực tế trình duyệt có thể trực tiếp giao tiếp AS/RS, BFF có thể giữ token, gateway có thể kết thúc TLS và AS/RS có thể cùng một sản phẩm.

Một trust boundary **không nhất thiết trùng với địa chỉ IP, container, VPC hoặc phòng máy**. Ngay cả hai service chạy trên cùng cluster vẫn có thể có trust boundary khác nhau nếu chúng có quyền riêng, credential riêng và trách nhiệm riêng.

### Ba câu hỏi tại mỗi boundary

Khi một giá trị đi qua ranh giới, hỏi:

1. **Ai tạo hoặc khẳng định giá trị đó?** Người dùng, JavaScript, client, AS, gateway hay cơ sở dữ liệu nghiệp vụ?
2. **Bên nhận cần bằng chứng gì để tin?** TLS/hostname, chữ ký, introspection, client authentication, sender proof, policy lookup hoặc ràng buộc session?
3. **Được tin đến mức nào?** Tin token được phát hành hợp lệ khác với tin chủ thể có quyền sửa mọi tài nguyên.

**Một dữ liệu có thể đáng tin cho mục đích này nhưng không đáng tin cho mục đích khác.** Ví dụ claim sub trong access token đã xác minh có thể nhận diện principal, nhưng không tự chứng minh principal có permission hoàn tiền tại tenant hiện tại.

## 3. Bốn vai trò OAuth và quyền hạn trong ranh giới tin cậy

| Bên | Được làm gì theo trách nhiệm? | Không nên được tin để làm gì? |
| --- | --- | --- |
| **Resource Owner** | Cấp/thu hồi sự ủy quyền trong phạm vi có quyền theo mô hình hệ thống. | Tự cấp scope vượt policy tổ chức hoặc giả mạo token của AS. |
| **Client** | Yêu cầu grant/scope, giữ và dùng token đúng profile, chứng minh client identity khi phù hợp. | Tự khai role, sub, audience, expiry rồi buộc RS chấp nhận. |
| **Authorization Server** | Xác thực/ràng buộc grant, áp chính sách cấp phát, phát hành token, quản lý RT và revocation khi hỗ trợ. | Tự động quyết định mọi điều kiện nghiệp vụ động của từng tài nguyên nếu không có dữ liệu/chính sách tương ứng. |
| **Resource Server** | Kiểm token đúng issuer/audience/scope/trạng thái và phân quyền request trên dữ liệu cụ thể. | Tin mọi header/claim client tự gửi, nhận ID token/RT như access token, cấp quyền dựa vào chữ ký đơn thuần. |

### Một vai trò không nhất thiết tương ứng một máy chủ

Một sản phẩm có thể vừa chạy **Authorization Server** vừa cung cấp một **Resource Server**. Sự đồng vị trí không xóa đi yêu cầu phân biệt trách nhiệm.

Tương tự, cùng một ứng dụng có thể là:

- **Client** khi gọi một API bên ngoài.
- **Resource Server** khi nhận request API từ ứng dụng khác.
- **Confidential client** khi backend gọi token endpoint.
- **Public client** đối với phần SPA/mobile không thể giữ secret.

Vì vậy, “service này đáng tin” là phát biểu quá chung. Cần nói rõ **service được tin theo vai trò nào, với credential nào và cho quyết định nào**.

## 4. Bản đồ ranh giới trong luồng Authorization Code + PKCE

Xem một ứng dụng dashboard truy cập Orders API thay mặt người dùng.

~~~mermaid
sequenceDiagram
    participant U as Browser / Resource Owner
    participant C as Dashboard Client
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    participant P as Policy / Orders DB

    C->>C: Sinh state và PKCE verifier/challenge
    C->>U: Chuyển sang authorization URL
    U->>AS: HTTPS /authorize
    AS->>AS: Xác thực user, kiểm client/redirect/scope và consent/policy
    AS-->>U: Redirect code + state về callback đã đăng ký
    U->>C: Code + state
    C->>C: Kiểm state và ràng buộc phiên
    C->>AS: HTTPS POST /token, code + verifier + client auth nếu cần
    AS->>AS: Kiểm grant, PKCE, client và phạm vi được ủy quyền
    AS-->>C: Access token; RT/ID token khi profile cho phép
    C->>RS: HTTPS Authorization: Bearer AT
    RS->>RS: Kiểm issuer, signature/active, type, audience, exp, scope
    RS->>P: Hỏi quyền theo user/tenant/order hiện hành
    P-->>RS: Policy decision và dữ liệu liên quan
    RS-->>C: Dữ liệu được phép hoặc từ chối
~~~

Ở đây có các trust boundary cốt lõi:

**Boundary 1 — Browser/Resource Owner → Authorization Server.** AS không tin client đã xác thực người dùng chỉ vì client tự khai username. AS kiểm session, phương thức xác thực, redirect request và chính sách phù hợp.

**Boundary 2 — Browser redirect → Client.** Client không coi authorization code/state từ URL là bằng chứng đăng nhập hoàn tất. Client kiểm **state**, bảo đảm code gắn với đúng giao dịch, sau đó đổi code qua token endpoint.

**Boundary 3 — Client → Authorization Server tại token endpoint.** AS không cấp token chỉ vì nhận được code, client_id hay một chuỗi grant_type. AS kiểm **code sử dụng một lần**, client binding, redirect URI, **PKCE code_verifier**, client authentication và sự ủy quyền.

**Boundary 4 — Client → Resource Server.** RS không tin role do frontend gửi. RS yêu cầu **access token đúng loại**, kiểm nguồn phát hành và audience, đồng thời kiểm scope và trạng thái.

**Boundary 5 — Resource Server → dữ liệu/chính sách nghiệp vụ.** Scope đúng mới mở khả năng xét request; RS phải kiểm người dùng có quyền trên **đơn hàng và tenant cụ thể** tại thời điểm xử lý.

Một luồng an toàn không bỏ qua Boundary 5 chỉ vì các boundary trước đó đã thành công.

## 5. Trust relationship giữa Authorization Server và Resource Server

RS có thể tin AS là **nguồn phát hành token**, nhưng mối tin cậy đó cần được cấu hình và giới hạn.

Với **JWT access token**, RS thường phải:

1. Chỉ chấp nhận **issuer** đã được cấu hình tin cậy.
2. Xác minh chữ ký bằng khóa đúng issuer và thuật toán được cho phép theo profile.
3. Không nhận thuật toán hoặc JWKS URL tùy ý từ token làm nguồn tin cậy mới.
4. Kiểm **audience** chứa đúng API đích.
5. Kiểm **token type**, cấu trúc claims bắt buộc, exp/nbf và các yêu cầu profile.
6. Kiểm scope cụ thể và chính sách tài nguyên hiện hành.

Với **opaque access token**, RS thường hỏi **introspection endpoint** hoặc dịch vụ xác minh đáng tin theo hợp đồng với AS. RS cần xác thực bản thân với endpoint nếu yêu cầu, bảo vệ TLS và xử lý **active**, audience, scope, type cùng thông tin ngữ cảnh được trả về.

| Tình huống | Điều RS có thể tin sau khi kiểm đúng | Điều RS chưa thể kết luận |
| --- | --- | --- |
| JWT chữ ký hợp lệ | Token do issuer được cấu hình ký và nội dung chưa bị sửa trái phép. | Người dùng được sửa mọi bản ghi; token chắc chắn chưa bị thu hồi trước hạn. |
| JWT có scope orders:write | Token được cấp phạm vi OAuth tương ứng theo hợp đồng issuer. | User có permission ghi ở mọi tenant. |
| Introspection active=true | AS coi token hoạt động theo trạng thái của nó tại thời điểm kiểm. | Token dành đúng API nếu chưa kiểm aud; quyền nghiệp vụ vẫn chưa được xét. |
| AT có sub=user-42 | Issuer khẳng định chủ thể theo profile token đã xác minh. | Sub là định danh toàn cục qua mọi issuer hoặc tương ứng user local cùng chuỗi. |
| Token có client_id=dashboard | Token gắn với client đã được issuer xác nhận theo profile. | Dashboard là môi trường hoàn toàn an toàn hoặc được admin permission. |

**Tin AS phát token hợp lệ không đồng nghĩa trao quyền quyết định toàn bộ nghiệp vụ cho token.**

## 6. Scope, permission, RBAC role và policy: mỗi lớp giải quyết câu hỏi nào?

Trong một ứng dụng Orders API:

- **OAuth scope** có thể là **orders:read**, **orders:write** hoặc **orders:approve**.
- **RBAC role** có thể là **order_viewer**, **order_manager** hoặc **tenant_admin**.
- **Permission** có thể là **order:update**, **order:approve**.
- **Policy** có thể quy định không tự duyệt đơn do chính mình tạo, chỉ được sửa đơn thuộc tenant hiện tại và chỉ khi trạng thái đơn còn cho phép.

Các điều kiện này không tự bao hàm nhau.

| Lớp | Ví dụ | Nguồn đáng tin | Người kiểm |
| --- | --- | --- | --- |
| **Scope của token** | orders:approve | AS phát hành/introspection theo grant đã xác minh. | RS kiểm scope theo hợp đồng endpoint. |
| **Principal identity** | issuer + sub, hoặc service principal | Token đã xác minh và identity mapping của server. | RS/identity middleware. |
| **RBAC role** | order_manager ở tenant-blue | Directory/policy store đáng tin, hoặc claim hợp lệ có ngữ nghĩa/sự mới được quy định. | RS/authorization service. |
| **Permission** | order:approve | Policy engine / role-permission mapping hiện hành. | RS. |
| **Quan hệ với tài nguyên** | Người tạo đơn không được tự duyệt | Orders DB và business rule đáng tin. | RS/business layer. |
| **Trạng thái nghiệp vụ** | Order đã đóng, không cho cập nhật | Database/transaction state. | RS. |

Một quyết định có thể viết:

~~~text
ALLOW_APPROVE(order, request) =
    trusted_access_token
    AND correct_audience("orders-api")
    AND exact_scope("orders:approve")
    AND principal_is_active
    AND permission("order:approve", order.tenantId)
    AND principal_is_not_order_creator
    AND order_status_allows_approval
~~~

Nếu chỉ kiểm role trong JWT mà bỏ policy bản ghi, hệ thống dễ phát sinh **IDOR/BOLA**: người có token hợp lệ truy cập tài nguyên không thuộc quyền của mình.

### Role claim trong JWT có phải tiêu chuẩn OAuth không?

OAuth 2.0 **không mặc định một claim role với ngữ nghĩa RBAC thống nhất cho mọi hệ thống**. Một issuer có thể thêm **roles**, **groups**, **permissions** hoặc claim namespace riêng theo hợp đồng. Tên trường không đủ làm bằng chứng; phải biết:

- Issuer nào phát hành và đã được RS tin cậy chưa?
- Token này là **access token dành cho RS** hay ID token dành cho client?
- Role nói về **user hay client**?
- Role có phạm vi **tenant/resource** nào?
- Độ mới của role và cách thu hồi khi quyền thay đổi?
- Role đó được ánh xạ sang permission ở RS như thế nào?

Nhận một JWT có chuỗi **admin** chưa có nghĩa mọi dịch vụ trong công ty phải coi principal là quản trị viên.

## 7. Sự khác biệt giữa role của người dùng và role của client

Trong hệ thống thực tế có ít nhất hai dạng principal dễ bị nhầm:

1. **End-User principal:** người dùng được xác minh qua luồng có sự ủy quyền.
2. **Client/workload principal:** ứng dụng hoặc dịch vụ xin access token theo quyền của chính nó, ví dụ **client_credentials**.

Ví dụ:

~~~text
User grant:
    issuer = https://identity.example.test
    sub = user-42
    client_id = dashboard-web
    scope = orders:read

Service grant:
    issuer = https://identity.example.test
    sub = reports-worker  // tùy token profile
    client_id = reports-worker
    scope = reports:generate
~~~

Không nên diễn giải **sub** của service token thành một user giống như cách đọc End-User token. Tùy issuer/profile, sub của token client_credentials có thể đại diện client hoặc một service principal.

### Lỗi nhầm principal

Giả sử một API có logic:

~~~text
if token.sub is not empty:
    user = findUserById(token.sub)
    allowUserAction(user)
~~~

Nếu token service có **sub** trùng với một user ID hoặc API không phân biệt profile, nó có thể dẫn tới **identity confusion**.

Hướng an toàn:

~~~text
principal = resolvePrincipal(
    trustedIssuer,
    validatedTokenProfile,
    validatedSubject,
    validatedClientIdentity,
    grantContextWhenAvailable
)

if principal.type == USER:
    applyUserAuthorization(principal, resource)
else if principal.type == SERVICE:
    applyServiceAuthorization(principal, resource)
else:
    deny
~~~

RS cần một mô hình identity rõ ràng, không dựa vào giả định mọi token đều có người dùng cuối hoặc mọi client được hành động như người dùng đã login.

### Client identity không phải bằng chứng quyền

**client_id** có thể xác nhận token được AS cấp cho một client theo profile, nhưng tên client không tự mang quyền. Với confidential client, AS có thể xác thực client bằng **client_secret_basic**, **private_key_jwt** hoặc **mTLS** theo cấu hình. Nhưng **xác thực thành công không đồng nghĩa được cấp scope tùy ý**.

Bản thân một public client_id cũng không phải secret; bất kỳ ai có thể biết một ID ứng dụng công khai. AS vẫn phải kiểm grant, PKCE, redirect và chính sách.

## 8. Audience là hàng rào ngăn token đi sai ranh giới

Audience trả lời: **Access token này được cấp cho Resource Server nào?**

Giả sử AS cấp token để dùng cho Reports API:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "reports-api",
  "client_id": "dashboard-web",
  "scope": "reports:read",
  "exp": 1730000900
}
~~~

Đây là **payload JWT minh họa**, chưa có chữ ký. Nếu Orders API thấy token này, nó phải từ chối khi audience của token **không bao gồm Orders API** theo profile, dù chữ ký đúng và người dùng có role manager.

**Token substitution** xảy ra khi một bên đưa một credential hợp lệ **cho ngữ cảnh khác** vào một API chấp nhận sai loại token hoặc sai audience.

Các trường hợp:

- Dùng **ID token OIDC** có audience là client để gọi API dữ liệu.
- Dùng **access token của Reports API** ở Payments API.
- Dùng **refresh token** ở Resource Server thay vì token endpoint của AS.
- Dùng token từ **issuer khác** nhưng API chỉ kiểm có chuỗi JWT ba phần.
- Dùng token của client credentials trong endpoint chỉ cho phép user delegation.

Khi chuyển một yêu cầu từ service A sang service B, **không tự chuyển tiếp access token gốc nếu token đó không dành cho service B**. Có thể cần token audience mới hoặc cơ chế token exchange/delegation được AS hỗ trợ và giới hạn đúng policy.

### Scope hẹp nhưng audience sai vẫn nguy hiểm

Một token có scope **orders:read** không được mặc nhiên nhận ở bất kỳ API có endpoint tên “orders”. RS phải kiểm **aud** bằng tập identifier được cấu hình, không suy đoán dựa trên scope hoặc host gần giống.

Nếu AS hỗ trợ **Resource Indicators for OAuth 2.0 (RFC 8707)**, client có thể yêu cầu access token cho tài nguyên đích. AS phải áp chính sách và RS vẫn phải kiểm audience; tham số **resource** do client gửi không tự biến nó thành bên được phép nhận token.

## 9. Boundaries khi token đi qua API Gateway và microservice

Kiến trúc thường có nhiều hop:

~~~mermaid
flowchart LR
    B["Browser / Client"] -->|"HTTPS + AT"| G["API Gateway"]
    G -->|"mTLS + authenticated context hoặc AT"| O["Orders Service"]
    O -->|"mTLS / token riêng"| P["Payments Service"]
    O -->|"Trusted data access"| DB[("Orders DB")]
    G -.->|"JWKS / introspection tin cậy"| AS["Authorization Server"]
    O -.->|"Policy / identity lookup"| Q["Authorization Policy Service"]
~~~

**Gateway là một trust boundary chứ không phải chiếc máy biến mọi request thành đáng tin.**

Hai phương án thường gặp:

**Phương án A — mỗi Resource Server tự kiểm access token.** Gateway định tuyến/giới hạn lưu lượng; từng service kiểm token issuer, audience, scope và permission. Cần tránh mỗi service cấu hình khác nhau gây drift.

**Phương án B — gateway kiểm token rồi truyền authenticated context qua kênh tin cậy.** Khi đó backend cần:

- Chỉ nhận request từ gateway đã được xác thực/định danh; ngăn truy cập trực tiếp nếu backend dựa vào gateway.
- Gateway **xóa và ghi đè** header mà client Internet có thể giả mạo.
- Kênh gateway → backend được bảo vệ, thường bằng TLS/mTLS theo threat model.
- Context do gateway chuyển có hợp đồng rõ về identity, issuer, audience, scope, tenant và thời hạn.
- Backend vẫn kiểm permission trên tài nguyên hiện hành, không cấp quyền theo mỗi role header không rõ nguồn.

Ví dụ header nguy hiểm:

~~~http
GET /orders/123 HTTP/1.1
Host: orders.internal.example.test
X-Authenticated-User: admin
X-User-Roles: super-admin
X-Tenant-Id: tenant-blue
~~~

Nếu service tin các header trên khi request có thể đến trực tiếp từ Internet, kẻ tấn công có thể **tự khẳng định mình là admin**.

**Không xem X-Forwarded-Proto, X-Authenticated-User hoặc X-User-Roles là bằng chứng độc lập.** Chúng chỉ đáng tin khi xuất phát từ một proxy tin cậy, được làm sạch ở ingress và đi trong kênh được bảo vệ với cơ chế kiểm soát rõ.

### mTLS có đủ để bỏ kiểm role không?

Không. **mTLS** có thể xác thực workload/certificate của bên gọi trong một kết nối. Nó không tự chứng minh user được duyệt Order #123. Service identity và end-user authorization là hai trục khác nhau.

Service A có thể được phép kết nối Orders Service qua mTLS nhưng chỉ được phép gọi endpoint thống kê, không được phê duyệt thanh toán.

## 10. Confused deputy: dùng quyền của ai, tại ranh giới nào?

**Confused deputy** là tình huống một thành phần có quyền cao bị bên ít quyền hơn dẫn dụ sử dụng quyền đó sai mục đích.

Ví dụ:

~~~text
Frontend user chỉ được đọc báo cáo.
Backend có service token với scope payments:refund.
Frontend gửi request "refund order 123" tới backend.
Backend tin role ở JSON body và dùng service token để gọi Payments API.
~~~

Trong ví dụ này, backend có quyền hoàn tiền và bị biến thành **deputy** thực hiện yêu cầu của bên không được phép.

Biện pháp:

1. Backend xác minh user/session/token của request ban đầu.
2. Kiểm hành động được phép trên Order #123 theo tenant và chính sách nghiệp vụ.
3. Không dùng service token quyền cao như cách “nâng quyền giùm” người dùng bất kỳ.
4. Phân biệt **service authority** với **delegated user authority**.
5. Khi service gọi API khác, truyền ngữ cảnh ủy quyền đã xác minh qua giao thức/hợp đồng tin cậy; downscope và giới hạn audience.
6. API đích vẫn kiểm điều kiện của mình; không dựa vào “backend trước chắc đã kiểm”.

### On-behalf-of và token exchange

Một kiến trúc có thể cần service A gọi service B **thay mặt người dùng**, với audience/token khác nhau. **OAuth 2.0 Token Exchange (RFC 8693)** mô tả một cơ chế trao đổi token theo profile được AS hỗ trợ.

Điều cần giữ:

- Client/service yêu cầu exchange phải có quyền.
- AS xác minh token đầu vào, actor và ngữ cảnh delegation được phép.
- Token đầu ra phải có **audience và scope giới hạn cho service B**, không tự tăng quyền.
- RS đích kiểm token đầu ra theo profile và quyền tài nguyên.
- Các trường **actor**, **subject** hoặc chain delegation phải được diễn giải theo hợp đồng, không tự chế từ HTTP header.

Token exchange **không mặc nhiên an toàn** nếu AS chấp nhận mọi subject hoặc service tự khai và phát token quyền cao. Đây vẫn là một boundary cần kiểm soát.

## 11. Multi-tenant: role thường có phạm vi, không phải quyền toàn cục

Một user có thể là manager ở tenant A và viewer ở tenant B:

~~~text
Principal: issuer-1 / user-42

tenant-blue:
    role = order_manager

tenant-green:
    role = order_viewer
~~~

Nếu access token chỉ mang:

~~~json
{
  "sub": "user-42",
  "roles": ["order_manager"]
}
~~~

thì RS **không thể tự suy** role này áp dụng toàn hệ thống, trừ khi issuer và hợp đồng cấp claims xác định rõ phạm vi, có chính sách bảo đảm tính mới.

Một kiểm tra đúng cần:

- Lấy **tenant của resource từ dữ liệu server đáng tin**, không chỉ từ tenant_id trong URL/header do client chọn.
- Ánh xạ principal từ **issuer + subject** hoặc khóa identity ổn định theo hợp đồng.
- Kiểm membership và permission của principal **ở tenant tương ứng**.
- Kiểm role/permission có còn hiệu lực, tài khoản có hoạt động hay bị khóa không.
- Áp quan hệ với bản ghi (ownership, tổ chức, trạng thái đơn) và separation of duties nếu cần.
- Đảm bảo một service token có quyền ở tenant A không được tự dùng ở tenant B.

### Vì sao issuer + sub quan trọng?

**sub** chỉ được đảm bảo có ngữ nghĩa trong phạm vi issuer/profile đã xác minh. Hai issuer khác nhau có thể phát cùng sub **user-42** cho hai chủ thể khác nhau.

~~~text
Key không an toàn nếu hệ thống multi-issuer:
    principalKey = sub

Key có ngữ cảnh tốt hơn:
    principalKey = (trustedIssuer, validatedSubject)
~~~

Nếu hệ thống có pairwise subject trong OIDC hoặc mapping liên kết tài khoản, cần dùng quy tắc identity mapping chính thức, không ghép người dùng chỉ vì email hoặc tên hiển thị trùng nhau.

## 12. RBAC role có thể thay đổi khi access token chưa hết hạn

Một access token JWT có thể chứa role tại thời điểm phát hành:

~~~text
10:00  AS phát JWT: role=order_manager, exp=10:15.
10:03  Quản trị viên rút role của user.
10:04  User tiếp tục gọi API bằng JWT còn hạn.
~~~

JWT đã ký có thể vẫn **hợp lệ về chữ ký và exp**. Nếu RS chỉ tin role trong token mà không có cơ chế cập nhật trạng thái, user có thể tiếp tục được cấp quyền cũ cho đến khi token hết hạn.

Các chiến lược theo nhu cầu:

| Chiến lược | Lợi ích | Đánh đổi |
| --- | --- | --- |
| **AT sống ngắn** | Giảm cửa sổ quyền cũ. | Không bảo đảm thu hồi tức thì; tăng tần suất cấp mới. |
| **Opaque token + introspection** | AS có thể phản ánh trạng thái khi RS hỏi. | Cache active có thể làm trễ phản ánh; phụ thuộc AS. |
| **JWT + lookup quyền hiện hành** | RS kiểm quyền/role động ngay khi xử lý. | Thêm dependency/độ trễ; cần cache và fallback đúng. |
| **JWT + denylist/session version** | Có thể từ chối token/phiên đã rút. | Cần dữ liệu trạng thái đồng bộ giữa các RS. |
| **Permission trong token với policy freshness rõ** | Giảm lookup cho một số API. | Phải chấp nhận và tài liệu hóa độ trễ quyền cũ. |

Không có một lựa chọn duy nhất phù hợp mọi API. Đối với quyền nhạy cảm như hoàn tiền hoặc thay đổi role, thường cần **policy freshness và khả năng thu hồi** chặt hơn API đọc dữ liệu ít rủi ro.

**Role claim là snapshot của một ngữ cảnh xác minh/cấp quyền**, không phải chứng chỉ rằng permission hiện hành không bao giờ thay đổi.

## 13. ID token, access token và refresh token ở các trust boundary

Ba loại token thường bị nhầm vì đều có thể xuất hiện trong một response từ AS/OP.

| Loại token | Chủ thể nhận/dùng đúng mục đích | Boundary sử dụng | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Access token** | Client trình bày cho RS có audience đúng. | Client → Resource Server. | API chấp nhận token sai audience/scope/type. |
| **Refresh token** | Client gửi tới token endpoint của AS. | Client → Authorization Server. | Gửi RT vào Orders API như bearer access token. |
| **ID token (OIDC)** | Relying Party/client xác minh thông tin xác thực. | OpenID Provider → Client. | RS dùng ID token làm access token chỉ vì cùng issuer. |

Một lỗi thường gặp:

~~~text
Dashboard nhận ID token có aud="dashboard-web".
Dashboard gọi Orders API với Authorization: Bearer <ID_TOKEN>.
Orders API chỉ kiểm chữ ký và exp.
~~~

Dù chữ ký hợp lệ, Orders API phải từ chối vì token **không có mục đích/audience của access token API**. Các thư viện xác minh JWT phải được cấu hình phân biệt profile, không có một bộ “JWT hợp lệ chung cho mọi nơi”.

OIDC **openid**, **profile** là scope có ngữ nghĩa trong OIDC, không tự trở thành permission sửa bản ghi nghiệp vụ.

## 14. Gắn role vào token: khi nào hữu ích, khi nào nguy hiểm?

Một số hệ thống đưa **roles** hoặc **permissions** vào JWT access token để RS giảm số lần gọi directory.

Ví dụ theo hợp đồng nội bộ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_roles": {
    "tenant-blue": ["order_viewer"]
  },
  "iat": 1730000000,
  "exp": 1730000900
}
~~~

Các trường **tenant_roles** và cấu trúc trên là **extension minh họa**. JWT/ OAuth không mặc nhiên định nghĩa ý nghĩa của chúng.

Ưu điểm:

- RS có thể xử lý một số quyết định đơn giản mà không gọi directory mỗi request.
- Dễ kiểm toán những thông tin quyền mà AS đã đưa vào token khi phát hành.
- Có thể có ích trong hệ thống có TTL ngắn và quyền ổn định.

Rủi ro:

- Role thay đổi nhưng JWT cũ vẫn còn hạn.
- Một role của tenant bị áp sai sang tenant khác.
- Token trở nên quá lớn, chứa nhiều thông tin cá nhân hoặc cấu trúc quyền nhạy cảm.
- RS khác nhau diễn giải cùng claim khác nhau.
- Client hoặc gateway tìm cách thêm/sửa claim ngoài nguồn tin cậy.
- Role tổng quát **admin** bị mọi service coi là quyền toàn hệ thống.

Nếu quyết định dùng role claim, phải có **hợp đồng issuer/audience/semantics, phạm vi tenant, TTL, policy rút quyền và kiểm thử token confusion**. Những endpoint nhạy cảm vẫn có thể cần kiểm quyền tại source of truth.

## 15. Bảo vệ ranh giới khi có token bị đánh cắp hoặc phát lại

Một **bearer access token** bị lấy từ log hoặc bộ nhớ client có thể được bên khác thử dùng, dù nó được phát qua luồng OAuth hợp lệ.

**TLS** bảo vệ token **trên đường truyền** nếu cấu hình đúng, nhưng không ngăn token bị lấy từ endpoint sau khi TLS kết thúc. **JWT signature** không giữ bí mật token và không ngăn sao chép nguyên token.

Các lớp giới hạn rủi ro:

1. **Least-privilege scope:** cấp ít phạm vi nhất đủ nhiệm vụ.
2. **Audience cụ thể:** token không dùng được ở RS khác nếu API kiểm aud đúng.
3. **TTL phù hợp:** exp/nbf được kiểm, leeway nhỏ theo rủi ro.
4. **Lưu trữ an toàn:** không đưa AT/RT vào URL, logs, analytics hoặc JS storage không cần thiết.
5. **Revocation và kiểm trạng thái:** xử lý quyền bị rút trước exp theo SLA nghiệp vụ.
6. **Sender-constraining khi phù hợp:** DPoP hoặc mTLS-bound access token yêu cầu proof/khóa tương ứng theo profile.
7. **Refresh token rotation/sender-constraining:** giảm khả năng tiếp tục xin token khi RT bị sao chép.
8. **Permission theo tài nguyên:** token sống/đúng scope vẫn không thể vượt role/tenant hiện hành.
9. **Phòng replay nghiệp vụ:** dùng idempotency/nonce khi thao tác cần chống xử lý giao dịch nhiều lần.

### Sender-constrained token có loại bỏ mọi nguy cơ không?

Không. DPoP (RFC 9449) hoặc mTLS-bound access token (RFC 8705) có thể giảm khả năng sử dụng **bản sao token đơn thuần** nếu kẻ tấn công không có khóa/chứng chỉ phù hợp.

Tuy nhiên, nếu client/workload đang giữ khóa bị xâm nhập và attacker có thể gọi thao tác ký/đính proof trong ngữ cảnh hợp lệ, sender-constraining không thay thế kiểm quyền hoặc chống malware. Cả hai cơ chế cũng **không thay thế TLS**.

## 16. Pseudocode: quyết định quyền sau khi vượt trust boundary

Mã giả sau minh họa một endpoint cập nhật đơn hàng. Nó **không triển khai JWT verifier**, mà giả định dùng thư viện được cấu hình đúng để xác minh access token và binding.

~~~text
function updateOrder(request, orderId, proposedChange):
    token = extractAccessTokenFromExpectedTransport(request)

    verified = validateByTrustedProfile(
        token,
        allowedIssuers = configuredIssuers,
        expectedAudience = "orders-api",
        expectedTokenUse = ACCESS_TOKEN,
        algorithmsAndKeys = trustedIssuerConfig,
        requiredSenderProof = profileRequirement
    )

    if verified.invalidOrExpired:
        return HTTP_401

    if not verified.scopes.hasExactValue("orders:write"):
        return HTTP_403

    principal = resolvePrincipal(
        issuer = verified.issuer,
        subject = verified.subject,
        clientId = verified.clientId,
        tokenProfile = verified.profile
    )
    if principal == null or not principal.active:
        return HTTP_403

    order = ordersRepository.find(orderId)
    if order == null:
        return HTTP_404

    trustedTenant = order.tenantId

    if not policyEngine.allows(
        principal = principal,
        client = verified.clientId,
        action = "order:update",
        tenant = trustedTenant,
        resource = order,
        currentState = order.status,
        requestedChange = proposedChange
    ):
        return HTTP_403

    return ordersRepository.updateWithBusinessChecks(order, proposedChange)
~~~

Điểm cần lưu ý:

- **verified.scopes** phải lấy từ token đã xác minh/introspection tin cậy, không từ trường JSON do client tự gửi.
- **order.tenantId** phải lấy từ dữ liệu tài nguyên server đáng tin, không dựa vào X-Tenant-Id chưa xác minh.
- **resolvePrincipal** cần phân biệt user và service client, tránh nhầm sub cùng chuỗi ở issuer khác.
- **Role/permission** nên được đánh giá theo chính sách về tính mới, không phụ thuộc mặc định mọi JWT claim bất biến.
- **updateWithBusinessChecks** phải bảo vệ điều kiện nghiệp vụ và race trong transaction; authorization không chỉ là một if ở controller.
- Khi policy store không khả dụng, các thao tác có rủi ro cao không được tự chuyển sang **allow all**.

Một token hợp lệ nhưng thiếu scope/permission thường dẫn đến **403 Forbidden**; token không hợp lệ hoặc thiếu credential thường là **401 Unauthorized** theo HTTP Bearer profile (RFC 6750), tùy tình huống và yêu cầu tránh lộ thông tin.

## 17. Trust-boundary review theo từng đường dữ liệu

Trước khi cho một trường dữ liệu ảnh hưởng tới quyết định quyền, hãy xác định **nguồn tạo, đường truyền và bước xác minh**.

| Dữ liệu đi qua boundary | Ai có thể tạo/gửi? | Kiểm tra tại bên nhận |
| --- | --- | --- |
| **client_id** trong authorization request | OAuth client, kể cả public client. | AS tìm client registration; không coi client_id là bí mật. |
| **redirect_uri** | Client yêu cầu. | AS so khớp URI đã đăng ký và quy tắc của flow. |
| **authorization code** | AS cấp, qua user agent đến client. | Token endpoint kiểm code một lần, client, redirect URI, PKCE. |
| **code_verifier** | Client giữ và gửi khi đổi code. | AS đối chiếu với code_challenge đã gắn grant. |
| **access token** | AS phát, client giữ và trình cho RS. | RS kiểm issuer, signature/introspection, audience, type, exp, scope. |
| **refresh token** | AS phát cho client khi được phép. | AS kiểm client binding, grant, rotation, thời hạn và policy. |
| **ID token** | OIDC OpenID Provider phát cho client. | Client kiểm theo OIDC; RS không nhận làm AT. |
| **role claim** | AS phát nếu profile có định nghĩa; client cũng có thể tự khai role trong body khác. | Chỉ xét claim đã xác minh và đúng semantics/tenant; không tin role do body tự khai. |
| **X-Authenticated-User** | Proxy/gateway hoặc client giả mạo nếu ingress không lọc. | Chỉ tin qua channel/proxy đã được xác thực, có xóa/ghi đè header ngoài. |
| **tenant_id trong URL** | Client. | Đối chiếu tenant thật của resource và quyền principal. |
| **order.owner_id** | Database nghiệp vụ. | Lấy từ truy vấn/transaction tin cậy; không tin client thay tùy ý. |
| **permission cache** | Directory/policy service, cache nội bộ. | Xác định TTL, invalidation, version và SLA thu hồi. |

### Rủi ro khi cùng một dữ liệu được kiểm nhiều lần khác nhau

Nếu Gateway kiểm JWT nhưng backend đọc role từ một header khác, hệ thống có thể không có một **nguồn chân lý nhất quán**. Nên xác định rõ hợp đồng:

- Ai xác minh cryptographic token?
- Ai ánh xạ subject thành principal?
- Ai giữ permission/role hiện hành?
- Ai kiểm quyền trên tài nguyên?
- Trường nào được phép đi qua boundary, trường nào phải được tái xác minh?

**Bảo mật không đến từ việc kiểm nhiều lần một cách tùy ý, mà đến từ việc mỗi boundary có một hợp đồng xác minh và trách nhiệm không thể bị bỏ qua.**

## 18. Threat modeling: một số đường tấn công liên quan role

### 18.1 Tự khai role ở frontend

~~~json
{
  "orderId": "order-123",
  "role": "admin",
  "tenant": "tenant-blue",
  "action": "approve"
}
~~~

Client có toàn quyền sửa JSON. Nếu RS dựa trực tiếp vào role trong body để approve, user có thể nâng quyền bằng một request tự tạo.

**Kiểm soát:** Xác minh principal từ token/session, lấy role từ nguồn tin cậy và kiểm tenant/order ở server.

### 18.2 Nhầm OIDC ID token với access token

Client nhận ID token có audience **dashboard-web**, gửi nó đến Orders API. API chỉ kiểm JWT signature.

**Kiểm soát:** RS kiểm đúng token use/type và audience riêng, không dùng một hàm **isValidJwt()** chung để cấp quyền cho mọi loại token.

### 18.3 Truy cập chéo tenant

User là manager ở tenant-blue nhưng gửi orderId của tenant-green. API chỉ kiểm role=order_manager.

**Kiểm soát:** Lấy tenant của order từ DB, kiểm permission theo tenant và quan hệ với resource; không xem role toàn cục.

### 18.4 Chuyển tiếp token giữa dịch vụ sai audience

Service A nhận access token cho audience **service-a** và chuyển nguyên sang service B, nơi không kiểm audience.

**Kiểm soát:** Service B từ chối; dùng token mới dành cho service B hoặc token exchange/downscoping hợp lệ nếu thiết kế cần delegation.

### 18.5 Gateway giả mạo context

Attacker gọi trực tiếp backend, gửi X-Authenticated-User là admin và X-Tenant-Id tùy ý.

**Kiểm soát:** Chặn đường bypass, xác thực proxy/hop, xóa header đầu vào và kiểm policy resource.

### 18.6 Client credentials bị đối xử như user token

Một batch worker có AT service principal, gửi vào endpoint chỉ dành cho người dùng để duyệt giao dịch.

**Kiểm soát:** Phân biệt token/profile/principal type, giới hạn grant và service permission, không ánh xạ sub vào local user tùy tiện.

### 18.7 Stale role sau khi rút quyền

AS phát JWT role cao, admin rút role nhưng RS tin claim đến tận exp.

**Kiểm soát:** TTL, lookup quyền, trạng thái phiên, introspection/denylist hoặc cơ chế theo SLA rút quyền, tùy rủi ro.

## 19. Kiểm thử âm tính cho từng boundary

Chỉ kiểm thử “user hợp lệ được đọc dữ liệu” là chưa đủ. Cần chứng minh request **không được phép** bị từ chối.

| Test | Bối cảnh | Kỳ vọng |
| --- | --- | --- |
| Role do frontend tự khai | Body chứa role=admin nhưng principal không có role. | RS từ chối; không tin role client. |
| Scope sai | Token có orders:read gọi endpoint orders:write. | 403 hoặc lỗi phù hợp; không tự nâng scope theo role. |
| Audience sai | Token của reports-api gửi Orders API. | RS từ chối. |
| Issuer sai | JWT cùng sub nhưng từ issuer không nằm allowlist. | RS từ chối. |
| ID token substitution | ID token OIDC gửi làm Bearer AT. | RS từ chối sai type/audience. |
| Refresh token substitution | RT gửi vào Resource Server. | RS từ chối, không introspect như AT nếu profile không cho phép. |
| Token hết hạn | JWT signature đúng nhưng exp đã qua. | 401 theo profile. |
| Subject collision | Hai issuer cùng sub=user-42. | Không gộp thành cùng principal khi không có mapping tin cậy. |
| Service-user confusion | Client_credentials token dùng như End-User. | Từ chối ở endpoint yêu cầu user delegation. |
| Tenant crossing | Role ở tenant-blue, order thuộc tenant-green. | Từ chối. |
| Role stale | Role bị rút trước token exp. | Hành vi thỏa SLA freshness/revocation đã công bố. |
| Header spoofing | Client gửi X-Authenticated-User=admin. | Gateway loại bỏ/ghi đè; backend không cấp quyền theo input. |
| Direct backend bypass | Request không đi qua gateway nhưng có header nội bộ. | Chặn hoặc xác minh độc lập. |
| Confused deputy | Frontend ít quyền gọi backend có service credential quyền cao. | Backend kiểm user action và scope/permission; từ chối thao tác trái phép. |
| Wrong sender proof | DPoP/mTLS-bound AT dùng với khóa/chứng chỉ khác. | RS từ chối theo profile. |
| Stale introspection cache | AS revoke token nhưng cache còn active. | Độ trễ được kiểm và nằm trong SLA chấp nhận. |
| Policy service outage | Permission store timeout khi giao dịch nhạy cảm. | Fail-safe; không cấp quyền theo mặc định mở. |
| Token exchange abuse | Client xin token cho API khác với scope rộng hơn grant. | AS từ chối hoặc giới hạn theo policy; RS vẫn kiểm. |
| Resource state changed | Order đã khóa sau khi request được đọc lần đầu. | Kiểm điều kiện trong transaction, không cấp quyền từ trạng thái cũ. |

### Kiểm thử boundary thay vì chỉ kiểm endpoint

Một bộ test integration tốt có thể thay đổi **một biến tin cậy mỗi lần**:

~~~text
Given:
  Valid user access token
  Issuer đúng
  Audience orders-api
  Scope orders:write
  Principal có role order_manager tại tenant-blue

Test 1:
  Order nằm tenant-green
  -> DENY

Test 2:
  Order tenant-blue nhưng principal đã bị rút permission
  -> DENY theo policy freshness

Test 3:
  Cùng token nhưng gửi sang payments-api
  -> DENY do audience

Test 4:
  Client thêm JSON "role": "super-admin"
  -> Không làm thay đổi quyết định quyền

Test 5:
  Gateway trust header bị giả từ Internet
  -> Context giả bị loại bỏ; DENY
~~~

Bộ test này kiểm **chuỗi bảo đảm qua các boundary**, không chỉ việc mã kiểm JWT trả thành công.

## 20. Tình huống thực hành: ba service và hai loại principal

Xét hệ thống gồm:

~~~text
Authorization Server:
    identity.example.test

OAuth Clients:
    dashboard-web
    reconciliation-worker

Resource Servers:
    orders-api
    payments-api

Tenants:
    tenant-blue
    tenant-green
~~~

**Alice** là order_manager ở tenant-blue và chỉ là viewer ở tenant-green. **reconciliation-worker** là service principal có quyền lấy báo cáo đối soát ở Payments API, không có quyền duyệt lệnh hoàn tiền.

### Tình huống A — User delegation hợp lệ

Dashboard nhận AT:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice-user",
  "aud": "orders-api",
  "client_id": "dashboard-web",
  "scope": "orders:read orders:write",
  "exp": 1730000900
}
~~~

Alice sửa một order thuộc tenant-blue.

**Đánh giá:** RS kiểm token và scope, ánh xạ Alice theo issuer+sub, sau đó kiểm role/permission ở tenant-blue và điều kiện order. Chỉ khi mọi điều kiện đạt, thay đổi mới được thực hiện.

### Tình huống B — Cùng token, order tenant-green

Alice gửi orderId thuộc tenant-green, nơi Alice chỉ có role viewer.

**Đánh giá:** Scope orders:write không tự cấp quyền ở tenant-green. RS phải từ chối nếu policy không cho Alice sửa đơn ở tenant này.

### Tình huống C — Worker dùng service authority

reconciliation-worker nhận token client_credentials audience payments-api, scope reports:reconcile. Worker cố gọi endpoint refunds:approve.

**Đánh giá:** RS kiểm token profile/service principal, scope và service permission. Không suy từ việc worker được kết nối Payments API rằng nó có quyền hoàn tiền.

### Tình huống D — Backend gọi Payments API thay mặt Alice

Dashboard yêu cầu backend tạo hoàn tiền. Backend có một confidential service credential quyền cao.

**Đánh giá:** Backend phải kiểm Alice được phép yêu cầu hoàn tiền cho giao dịch cụ thể. Nếu cần delegation qua dịch vụ, AS/phần chuyển token phải giới hạn đúng actor/subject/scope/audience. Không dùng service credential để bỏ qua policy người dùng.

### Tình huống E — Role thay đổi giữa hai request

Admin rút quyền order_manager của Alice sau request đầu tiên nhưng JWT còn hạn.

**Đánh giá:** RS phải tuân thủ policy về **độ mới của phân quyền**, ví dụ lookup permission hoặc cơ chế trạng thái tương ứng. Không khẳng định chữ ký token tự động phản ánh role mới.

## 21. Checklist kiến trúc về role và trust boundary

Trước khi triển khai OAuth 2.0/OIDC trong hệ thống nhiều service:

1. **Định nghĩa role:** Đã tách protocol role của OAuth khỏi RBAC role của user/client chưa?
2. **Liệt kê boundary:** Đã vẽ các hop browser/client/AS/RS/gateway/policy store và xác định nguồn tin cậy của mỗi hop?
3. **Client registration:** AS có kiểm loại client, grant, redirect URI, PKCE, client authentication, allowed scopes/resources?
4. **Authorization flow:** Client có kiểm state, AS có code dùng một lần và code_verifier/redirect binding?
5. **Issuer:** RS chỉ tin issuer và khóa/endpoint đã được cấu hình, không chấp nhận jwks_uri/kid tùy tiện?
6. **Audience:** Mỗi RS kiểm access token thực sự dành cho mình, không nhận token từ API khác?
7. **Token type:** RS phân biệt access token, ID token và refresh token theo profile?
8. **Scope:** AS cấp tối thiểu; RS so khớp scope endpoint chính xác, không suy role=admin thành scope vô hạn?
9. **Principal type:** Hệ thống phân biệt user principal, client/workload principal và actor trong delegation?
10. **Identity key:** Có dùng issuer + subject hoặc mapping định danh đã xác minh để tránh ghép nhầm account?
11. **Tenant:** Role/permission có phạm vi tenant, resource owner và data policy cụ thể?
12. **Dynamic permission:** Có cơ chế áp chính sách quyền hiện hành và SLA thu hồi role/token?
13. **Gateway:** Proxy có xóa/ghi đè header giả, backend ngăn bypass và kênh nội bộ có trust contract?
14. **Downstream delegation:** Các service không chuyển tiếp token sai audience; token exchange chỉ được cấp theo policy?
15. **Credential theft:** AT/RT được bảo vệ trong TLS, storage và logs; sender-constraining/revocation khi phù hợp?
16. **Policy failure:** Không tự mở quyền khi KMS, AS introspection hoặc permission store lỗi?
17. **Transaction checks:** Các điều kiện nghiệp vụ/ràng buộc role được kiểm trong vòng đời transaction phù hợp?
18. **Negative tests:** Có test sai issuer/audience/type, service-user confusion, header spoofing, IDOR/BOLA và stale role?
19. **Observability:** Có audit quyết định quyền bằng metadata tối thiểu, không log bearer token/refresh token?
20. **Review trách nhiệm:** Mỗi rule “ai được phép làm gì” có chủ sở hữu rõ ở AS, RS hoặc policy engine?

## Kết luận

**Role và trust boundary là hai góc nhìn bổ sung nhau khi thiết kế token security.** Bốn role trong OAuth 2.0 mô tả **ai tham gia và chịu trách nhiệm gì** trong luồng ủy quyền; RBAC role mô tả **nhóm quyền nghiệp vụ của một principal**. Trust boundary xác định **bằng chứng nào phải được kiểm khi danh tính, credential và yêu cầu đi từ bên này sang bên kia**.

Authorization Server có thẩm quyền phát hành token trong phạm vi grant/chính sách được phép, nhưng **Resource Server không được coi token đã ký là giấy phép truy cập mọi bản ghi**. RS phải kiểm issuer, audience, loại token, thời gian, scope, subject/client identity, tenant và permission hiện hành. Khi có gateway, service-to-service delegation hoặc multi-tenant, mỗi boundary mới đều cần xác thực nguồn thông tin và giới hạn quyền tương ứng.

Cốt lõi của một mô hình tin cậy vững chắc là: **không bên nào được tự khai quyền cho chính mình mà không có bằng chứng và chính sách được kiểm ở ranh giới nhận dữ liệu**. Phân chia rõ trách nhiệm giữa AS, client, RS và policy theo tài nguyên giúp giảm token substitution, confused deputy, cross-tenant access và tác hại của token bị đánh cắp hoặc phát lại.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 1.1: Roles](https://www.rfc-editor.org/rfc/rfc6749#section-1.1)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
