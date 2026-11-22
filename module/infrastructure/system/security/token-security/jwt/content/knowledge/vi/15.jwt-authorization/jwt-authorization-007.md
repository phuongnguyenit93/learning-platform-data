# Giới hạn tin cậy đối với claims do dịch vụ trung gian chuyển tiếp

## 1. Một claim được chuyển tiếp không tự động trở thành sự thật đáng tin cậy

Trong kiến trúc có nhiều API hoặc microservice, request thường đi qua một hay nhiều thành phần trung gian trước khi tới dịch vụ xử lý tài nguyên. Ví dụ, người dùng gọi API Gateway, Gateway chuyển request đến Billing API, rồi Billing API gọi Document API để lấy chứng từ.

Trên đường đi, các dịch vụ có thể chuyển tiếp access token, một số claims, thông tin principal hoặc một token mới được cấp cho dịch vụ phía sau. Nếu không xác định rõ nguồn phát hành và ranh giới tin cậy, dịch vụ nhận có thể nhầm dữ liệu do client tự gửi với một khẳng định đã được xác minh.

Ví dụ request ban đầu:

~~~http
GET /invoices/INV-100 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Gateway xác minh token rồi chuyển đến Billing API. Billing API tiếp tục gọi Document API để lấy chứng từ. Document API cần biết người dùng cuối là ai, dịch vụ nào đang trực tiếp gọi nó, request được thực hiện thay mặt người dùng hay bằng quyền riêng của dịch vụ, token được phát hành bởi ai và dành cho API nào, những claims nào đã được xác minh, những claims nào chỉ được dịch vụ trung gian suy ra, và quyền nào được ủy quyền cho lần gọi downstream này.

Không thể trả lời các câu hỏi đó chỉ bằng cách nhận một header như X-User-Id hoặc tin rằng mọi dữ liệu đến từ Gateway đều đúng.

> **Khi claims đi qua ranh giới dịch vụ, bên nhận phải xác minh nguồn phát hành, tính toàn vẹn, audience, ngữ nghĩa và phạm vi ủy quyền. Việc một dịch vụ trung gian chuyển tiếp dữ liệu không tự làm dữ liệu đó đáng tin cậy.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API Gateway, resource server, dịch vụ phân tán và hệ thống ủy quyền. Nội dung không phụ thuộc một ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Bốn loại dữ liệu thường bị gọi chung là claims chuyển tiếp

Trước khi thiết kế trust boundary, cần phân biệt cách dữ liệu được chuyển giữa các dịch vụ.

| Cách chuyển | Ví dụ | Bên nhận nên tin điều gì? |
| --- | --- | --- |
| **Chuyển tiếp JWT gốc (bearer token relay)** | Gateway gửi nguyên access token do Identity Provider phát hành. | Có thể xác minh chữ ký và claims của issuer gốc; vẫn phải kiểm tra audience và mục đích token. |
| **Chuyển tiếp thông tin qua header** | Gateway gửi X-Authenticated-User hoặc X-Tenant-Id. | Chỉ tin nếu request đến từ một nguồn trung gian đã xác thực và header đã được bảo vệ khỏi input do client giả mạo. |
| **Phát hành token/assertion mới** | Billing API ký JWT nội bộ hoặc đổi token để gọi Document API. | Token mới là một khẳng định của issuer mới; phải kiểm tra chữ ký, issuer, audience và hợp đồng mới. |
| **Chuyển tiếp context trong message/job** | Dịch vụ gửi subject, tenant, actor và action trong message queue. | Cần xác minh nguồn message, tính toàn vẹn, quyền ủy quyền và thời điểm kiểm tra lại quyền. |

Những cách này có mức bảo đảm khác nhau. Không nên coi header, message payload và JWT đã ký là các bằng chứng tương đương.

## 3. Ranh giới tin cậy trong chuỗi dịch vụ

Một kiến trúc minh họa:

~~~mermaid
flowchart LR
    U["Người dùng / Client"] --> G["API Gateway"]
    G --> A["Billing API"]
    A --> D["Document API"]
    I["Identity Provider / Authorization Server"] -. "phát hành access token" .-> U
    I -. "ký token exchange" .-> A
~~~

Mỗi mũi tên là một lần chuyển giao dữ liệu qua một kết nối và một ranh giới tin cậy. Mỗi dịch vụ phải hiểu mình đang nhận loại bằng chứng nào.

### 3.1. Client đến Gateway

Client có thể gửi bearer access token, các header tùy chỉnh như X-User-Id, X-Roles, X-Tenant-Id, hoặc tham số tenant/resource ID trong URL và body.

Ở ranh giới Internet, các header định danh do client tự gửi là dữ liệu không đáng tin cậy. Client có thể tự tạo X-User-Id: admin hoặc X-Roles: ["administrator"]. Gateway phải xác minh token và không được sử dụng các header đó làm nguồn danh tính.

### 3.2. Gateway đến API

Gateway có thể chuyển tiếp nguyên token gốc, chuyển tiếp một tập header nội bộ sau khi đã xác minh token, hoặc yêu cầu Authorization Server cấp token dành cho API đích.

API cần biết chính xác lựa chọn nào được dùng. Nếu API chấp nhận cả token và header nhưng không định nghĩa ưu tiên, một request có thể mang hai danh tính mâu thuẫn.

### 3.3. API đến API downstream

Billing API có thể dùng quyền riêng của nó để đọc chứng từ, hoặc gọi Document API thay mặt người dùng. Hai tình huống này phải được phân biệt:

- **Service-to-service:** Billing API gọi bằng service principal của chính nó.
- **On-behalf-of/delegation:** Billing API gọi thay mặt user-514, với phạm vi được ủy quyền cụ thể.

Không được lấy quyền rộng của Billing API để suy ra rằng người dùng cuối cũng có quyền tương ứng.

## 4. Chuyển tiếp nguyên JWT: chữ ký còn giá trị nhưng audience vẫn quyết định

Khi một Gateway chuyển tiếp nguyên access token mà không thay đổi nội dung, chữ ký JWT vẫn có thể được xác minh bởi dịch vụ downstream nếu dịch vụ đó tin issuer và có khóa phù hợp.

Điều này **không** có nghĩa token được dùng ở mọi dịch vụ.

Ví dụ token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "scope": "invoice:read",
  "exp": 1900003600
}
~~~

Billing API có thể chấp nhận token này vì audience phù hợp. Nếu Billing API chuyển nguyên token sang Document API, Document API phải từ chối nếu audience không bao gồm hoặc không dành cho Document API theo hợp đồng.

### 4.1. Vì sao không nên dùng một token cho mọi dịch vụ?

Một token có audience quá rộng có thể bị dùng ở nhiều resource server:

- Token bị lộ ở một dịch vụ có thể được thử lại ở dịch vụ khác.
- Scope của một API có thể bị hiểu nhầm thành quyền ở API khác.
- Mỗi API có thể diễn giải role/permission khác nhau.
- Khó xác định ranh giới trách nhiệm khi một service bị xâm phạm.

Ưu tiên token có audience rõ cho resource server cần truy cập. Nếu hệ thống cho phép một token có nhiều audience, phải định nghĩa rõ từng bên nhận được phép sử dụng claims và quyền nào.

### 4.2. Chuyển tiếp token không phải chuyển quyền

Gateway chuyển tiếp token không tạo ra quyền mới. Gateway cũng không thể tự sửa payload của JWT có chữ ký rồi vẫn giữ nguyên chữ ký cũ. Nếu thay đổi claim, chữ ký không còn hợp lệ.

Nếu một dịch vụ cần phát hành token mới, token mới phải được ký bởi issuer có thẩm quyền và phải thể hiện rõ dịch vụ nào chịu trách nhiệm cho các khẳng định trong token đó.

### 4.3. Bearer token là thông tin có thể bị sử dụng lại

Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu token và được resource server chấp nhận. Vì vậy:

- Chỉ gửi token qua kênh bảo mật như TLS.
- Không ghi nguyên token vào log, URL, message hoặc telemetry.
- Không chuyển token đến dịch vụ không cần nó.
- Hạn chế thời hạn và audience theo rủi ro.
- Cân nhắc token sender-constrained khi cần giảm nguy cơ token bị đánh cắp và sử dụng lại.

## 5. Claims trong header không tự có tính xác thực

Một số hệ thống dùng reverse proxy hoặc API Gateway để xác minh token rồi thêm header:

~~~http
X-Authenticated-User: user-514
X-Authenticated-Issuer: https://identity.example.test
X-Tenant-Id: company-a
X-Granted-Scope: invoice:read
~~~

Các header này chỉ là dữ liệu HTTP. Chúng không có chữ ký độc lập và không tự chứng minh ai đã tạo ra chúng.

### 5.1. Rủi ro giả mạo header

Nếu Gateway giữ nguyên header do client gửi và API phía sau tin header đó, client có thể gửi:

~~~http
X-Authenticated-User: admin
X-Tenant-Id: company-b
X-Granted-Scope: invoice:approve
~~~

API phía sau có thể nhầm dữ liệu giả mạo thành kết quả xác thực của Gateway.

### 5.2. Quy tắc bảo vệ header nội bộ

Nếu kiến trúc chọn header làm kênh chuyển tiếp danh tính:

1. Gateway phải xóa hoặc ghi đè mọi header định danh cùng tên do client gửi.
2. API phía sau chỉ nhận các header đó từ Gateway hoặc proxy được xác thực.
3. Kết nối nội bộ cần xác thực peer, ví dụ mTLS hoặc cơ chế service identity tương đương.
4. Chặn đường truy cập trực tiếp đến API phía sau từ nguồn không được phép.
5. Quy định schema, kiểu dữ liệu, nguồn và ngữ nghĩa của từng header.
6. Không dùng header do Gateway thêm làm bằng chứng cho những claim mà Gateway chưa thực sự xác minh.
7. Nếu nhiều proxy cùng tham gia, quy định rõ thành phần nào được thêm, xóa và tin từng trường.

Việc dùng mạng nội bộ hoặc địa chỉ IP private không tự tạo ra trust boundary đủ mạnh. Kẻ tấn công có thể khai thác service khác trong cùng mạng hoặc một đường cấu hình sai.

### 5.3. Không trộn header và token theo cách nhập nhằng

Ví dụ một request có:

~~~http
Authorization: Bearer <token-for-user-A>
X-Authenticated-User: user-B
~~~

API phải có hợp đồng rõ:

- Nếu tự xác minh JWT, principal phải được lấy từ claims đã xác minh.
- Nếu tin header do Gateway xác thực, API chỉ chấp nhận request từ Gateway tin cậy và phải bảo đảm client không thể chèn header.
- Không chọn header có vẻ quyền cao hơn hoặc token có vẻ thuận tiện hơn.
- Nếu danh tính từ hai nguồn không khớp, từ chối và ghi nhận sự kiện theo chính sách.

## 6. Khi dịch vụ trung gian phát hành token mới

Một Gateway hoặc service có thể phát hành JWT nội bộ để downstream không phải nhận bearer token ban đầu. Khi đó cần phân biệt:

- **Issuer mới:** dịch vụ nào đã ký token mới?
- **Subject:** token đại diện cho người dùng hoặc thực thể nào?
- **Actor:** dịch vụ hoặc tác nhân nào đang hành động thay mặt subject?
- **Audience:** downstream API nào được phép nhận token?
- **Scope/permission:** quyền nào được ủy quyền cho lần gọi này?
- **Provenance:** các khẳng định về subject và quyền được lấy từ đâu?

Token mới là một khẳng định của issuer mới. Nếu Gateway ký token, downstream đang tin Gateway về các claims mà Gateway đã đưa vào token; downstream không tự động nhận được bảo đảm trực tiếp từ Identity Provider ban đầu.

### 6.1. Không giả danh issuer gốc

Giả sử Billing API tự tạo JWT mới nhưng đặt:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/documents"
}
~~~

trong khi token được ký bằng khóa riêng của Billing API. Đây là cách biểu diễn sai lệch: claim iss nói Identity Provider phát hành nhưng chữ ký thực tế thuộc Billing API. Document API có thể từ chối vì khóa không thuộc issuer hoặc, tệ hơn, một cấu hình tin cậy sai có thể làm nó hiểu nhầm nguồn phát hành.

Nếu Billing API phát hành token nội bộ, issuer phải nhận diện Billing API hoặc một issuer nội bộ có thẩm quyền. Cần có claim/context riêng để thể hiện subject gốc và actor theo hợp đồng.

Không sao chép iss của issuer ban đầu vào token mới rồi ký bằng khóa của dịch vụ trung gian như thể token vẫn do issuer ban đầu phát hành.

### 6.2. Phân biệt subject và actor

Trong luồng ủy quyền:

- **sub** thường nhận diện subject mà token đại diện.
- **act** theo RFC 8693 có thể mô tả actor đang hành động thay mặt subject.

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://authorization.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/documents",
  "act": {
    "sub": "billing-service"
  },
  "scope": "document:read",
  "exp": 1900001200
}
~~~

Trong ví dụ, subject là user-514 và actor là billing-service. Ý nghĩa chính xác phụ thuộc token exchange và hợp đồng được các bên triển khai.

Không nhầm:

- **sub:** chủ thể được đại diện.
- **act:** actor thực hiện thay mặt subject trong ngữ cảnh ủy quyền.
- **client_id:** ứng dụng khách liên quan đến token theo profile/hợp đồng.
- **iss:** bên phát hành token hiện tại.
- **aud:** resource server dự kiến nhận token.

Actor không tự có quyền chỉ vì xuất hiện trong claim. Authorization Server phải xác minh actor được phép đại diện subject; resource server phải kiểm tra token và chính sách của mình.

## 7. OAuth Token Exchange và ủy quyền cho downstream

OAuth 2.0 Token Exchange (RFC 8693) mô tả cơ chế một bên đổi token đầu vào để nhận token mới phù hợp với một ngữ cảnh khác. Đây là một cách tiêu chuẩn hóa việc cấp token cho downstream thay vì chuyển nguyên token không đúng audience.

Một luồng tổng quát:

1. Client nhận access token ban đầu dành cho API đầu tiên.
2. Billing API xác minh token và xác định subject cùng quyền cần thiết.
3. Billing API yêu cầu Authorization Server cấp token dành cho Document API.
4. Authorization Server kiểm tra subject, actor, grant, resource/audience và quyền ủy quyền.
5. Token mới được phát hành với audience và quyền phù hợp cho Document API.
6. Document API xác minh token mới và vẫn kiểm tra quyền trên tài nguyên cụ thể.

### 7.1. Minh họa token đầu vào và token đầu ra

Token đầu vào:

~~~text
iss = Identity Provider
sub = user-514
aud = Billing API
scope = invoice:read
~~~

Token downstream:

~~~text
iss = Authorization Server
sub = user-514
act.sub = billing-service
aud = Document API
scope = document:read
~~~

Token đầu ra không nên kế thừa toàn bộ scope của token đầu vào. Nó chỉ nên chứa quyền cần thiết và được Authorization Server chấp thuận cho lần gọi downstream.

### 7.2. Subject token và actor token

RFC 8693 định nghĩa các tham số token exchange như **subject_token**, **subject_token_type**, và tùy luồng có thể có **actor_token** cùng loại tương ứng. Subject token đại diện cho chủ thể; actor token có thể cung cấp thông tin về bên thực hiện thay mặt subject.

Authorization Server phải xác định:

- Subject token có hợp lệ và phù hợp không?
- Actor token có hợp lệ và actor có được phép hành động thay mặt subject không?
- Resource/audience đích có được phép không?
- Quyền yêu cầu có nằm trong phạm vi subject và actor được ủy quyền không?
- Có giới hạn tenant, client, thời hạn hoặc loại hành động nào không?

Việc gửi subject_token hoặc actor_token không buộc Authorization Server phải cấp token. Chúng là đầu vào cho một quyết định cấp quyền mới.

### 7.3. Claims act và may_act

RFC 8693 mô tả claim **act** để biểu diễn actor trong token đã được trao đổi và claim **may_act** để biểu diễn thông tin về actor được phép hành động thay mặt subject trong một ngữ cảnh phù hợp.

Không tự tạo ý nghĩa tùy ý cho hai claim này:

- **act** mô tả actor trong token; nó không phải permission tổng quát.
- **may_act** là dữ kiện để Authorization Server đánh giá việc ủy quyền; resource server vẫn phải áp dụng policy.
- Actor chain lồng nhau cần được xử lý theo profile và hợp đồng; không bỏ qua actor trung gian nếu việc đó làm mất dấu vết ủy quyền.

## 8. Không mở rộng quyền qua chuỗi dịch vụ

Một nguyên tắc quan trọng là quyền ở downstream không được tự động rộng hơn quyền mà subject và actor được phép sử dụng trong ngữ cảnh hiện tại.

Giả sử:

~~~text
User permission:       invoice.read
Billing service grant: document.read
Requested downstream:  document.read
Document API policy:   document.read on DOC-100 only
~~~

Document API chỉ nên cho phép thao tác nếu tất cả điều kiện cần đều đạt. Nếu Billing service có quyền document.delete nhưng user chỉ được yêu cầu đọc chứng từ, dịch vụ không được dùng quyền delete để thực hiện thay mặt user.

Một cách tư duy bảo thủ:

~~~text
Effective delegated authority
    = subject authority
    INTERSECT actor delegation grant
    INTERSECT downstream token scope
    INTERSECT resource policy
    INTERSECT current business constraints
~~~

Đây là nguyên tắc giới hạn quyền theo giao của các ràng buộc, không phải công thức bắt buộc của mọi giao thức. Hệ thống có thể có quyền service độc lập cho tác vụ nội bộ, nhưng phải phân biệt rõ tác vụ đó với hành động được thực hiện thay mặt user.

### 8.1. Confused deputy

Confused deputy xảy ra khi một dịch vụ có quyền rộng bị lợi dụng để thực hiện hành động mà caller không được phép.

Ví dụ:

1. User A chỉ có quyền đọc hóa đơn company-a.
2. Billing API có credential dịch vụ để đọc mọi chứng từ.
3. User A gửi ID chứng từ của company-b.
4. Billing API không kiểm tra quyền của User A trên chứng từ.
5. Billing API gọi Document API bằng credential rộng của chính nó.
6. Document API chấp nhận service principal và trả chứng từ company-b.

Để ngăn lỗi:

- Billing API kiểm tra quyền của User A trên resource trước khi gọi downstream.
- Token downstream chỉ cấp action và resource cần thiết.
- Document API kiểm tra tenant/object policy của request.
- Actor và subject được thể hiện rõ khi dùng delegation.
- Quyền riêng của service không tự được xem là quyền của user.

### 8.2. Không tin claims quyền do service tự suy ra nếu không có thẩm quyền

Một dịch vụ nghiệp vụ có thể biết user đã đăng nhập, nhưng không nhất thiết là nguồn có thẩm quyền để quyết định role quản trị hoặc quyền thanh toán. Nếu dịch vụ tự ký:

~~~json
{
  "sub": "user-514",
  "roles": ["super_admin"],
  "permissions": ["payment.refund"]
}
~~~

thì downstream chỉ nên tin các claims đó nếu dịch vụ có thẩm quyền phát hành những khẳng định ấy theo hợp đồng. Khả năng ký JWT không tự cấp quyền quản lý danh tính hoặc permission.

## 9. Bảo toàn nguồn gốc và ngữ nghĩa claims

Khi một dịch vụ trung gian chuyển đổi claims, cần giữ được câu trả lời cho câu hỏi: **claim này do ai khẳng định và được xác minh bằng cách nào?**

### 9.1. Phân biệt claim gốc và claim suy ra

| Claim/context | Nguồn có thể có | Điều bên nhận cần hiểu |
| --- | --- | --- |
| **sub** trong token gốc | Identity Provider | Chủ thể do issuer gốc xác định. |
| **iss** trong token gốc | Identity Provider | Nguồn phát hành token gốc. |
| **aud** trong token mới | Authorization Server | API được dự kiến nhận token mới. |
| **act** | Authorization Server/token exchange | Actor được biểu diễn trong luồng ủy quyền. |
| **tenant context** | Identity Provider hoặc hệ thống membership | Phải theo hợp đồng và có thể cần kiểm tra trạng thái hiện hành. |
| **resource classification** | Hệ thống quản lý tài nguyên | Thuộc tính của object, không nên lấy từ client. |
| **risk score** | Dịch vụ đánh giá rủi ro | Khẳng định của dịch vụ đó; phải định nghĩa issuer, freshness và cách dùng. |

Nếu một service tự suy ra tenant, role hoặc risk level, nó phải có thẩm quyền đối với dữ liệu đó hoặc phải ghi nhận đó là một đánh giá của chính service.

### 9.2. Không làm mất nguồn gốc bằng cách đổi tên claim tùy tiện

Ví dụ, service A nhận sub từ issuer gốc rồi tạo header:

~~~http
X-User: user-514
~~~

Ở downstream, header này không còn thể hiện rõ issuer gốc nào đã định danh user-514, service A đã xác minh token hay chỉ đọc payload, header có bị client gửi từ đầu không, service A có quyền xác nhận user-514 không, và token gốc có dành cho downstream không.

Nếu cần chuyển tiếp context, dùng một hợp đồng rõ về nguồn phát, kết nối tin cậy và ngữ nghĩa. Với delegation xuyên dịch vụ, token exchange thường cung cấp cách thể hiện subject/actor/audience rõ hơn việc tự tạo một số header không có cơ chế xác thực.

### 9.3. Allowlist claims

Không sao chép toàn bộ payload của token đầu vào sang token mới. Chỉ đưa các claims downstream cần:

- Subject/actor phù hợp với mục đích gọi.
- Audience downstream.
- Scope/permission tối thiểu.
- Tenant hoặc resource context cần thiết.
- Thời hạn phù hợp.
- Claim phiên bản hợp đồng nếu cần.

Tránh chuyển tiếp thông tin nhạy cảm hoặc claim không liên quan. Việc giảm dữ liệu cũng giảm nguy cơ downstream hiểu sai các claims do issuer khác định nghĩa.

## 10. Trust boundary và xác thực kết nối giữa dịch vụ

JWT xác minh nguồn phát hành token; nó không tự xác minh dịch vụ đang kết nối có phải là dịch vụ mà kiến trúc dự kiến hay không. Ngược lại, mTLS xác thực peer/kết nối nhưng không tự quyết định người dùng cuối được thao tác trên object nào.

Hai lớp này bổ sung cho nhau:

- **Workload/service identity:** dịch vụ nào đang kết nối?
- **User/delegated identity:** request đại diện cho subject nào?
- **Authorization:** service hoặc subject được phép thực hiện action nào trên resource nào?

### 10.1. mTLS cho service-to-service

Mutual TLS có thể giúp hai dịch vụ xác thực lẫn nhau và bảo vệ kênh truyền. Ví dụ, Document API chỉ chấp nhận kết nối từ Billing API có certificate/workload identity hợp lệ.

Nhưng nếu Billing API được xác thực bằng mTLS, điều đó chỉ chứng minh caller là Billing API theo trust configuration. Nó không tự chứng minh user-514 có quyền đọc DOC-100. Document API vẫn cần token/delegation context hoặc policy phù hợp.

### 10.2. Sender-constrained token

Bearer token có thể bị sử dụng lại nếu bị đánh cắp. Một số cơ chế OAuth có thể ràng buộc access token với khóa hoặc chứng thư của client:

- **Mutual-TLS Certificate-Bound Access Tokens** (RFC 8705) gắn token với chứng thư client theo profile.
- **Demonstrating Proof of Possession (DPoP)** (RFC 9449) sử dụng proof được ký bằng khóa của client cho request.

Các cơ chế này giúp giảm nguy cơ bên khác chỉ cần có chuỗi token là sử dụng được. Chúng không thay thế kiểm tra audience, actor/subject, tenant hoặc quyền trên resource.

### 10.3. Chặn đường đi vòng qua Gateway

Nếu API phía sau giả định mọi request đã qua Gateway:

- Không để API có đường truy cập trực tiếp từ Internet hoặc nguồn không tin cậy.
- Xác thực kết nối từ Gateway.
- Không tin forwarded headers từ kết nối không được xác thực.
- Có chính sách riêng cho health check, batch job và service-to-service.
- Định nghĩa rõ API có tự xác minh token hay chỉ chấp nhận assertion từ Gateway.

Không dựa duy nhất vào việc API nằm trong private subnet để bỏ kiểm tra danh tính và quyền.

## 11. Claims chuyển tiếp trong message và background job

Không phải mọi luồng đều là HTTP request đồng bộ. Một dịch vụ có thể gửi message vào queue để dịch vụ khác xử lý sau.

Ví dụ message:

~~~json
{
  "event_id": "evt-8102",
  "requested_by": "user-514",
  "actor_service": "billing-service",
  "tenant_id": "company-a",
  "action": "invoice.export",
  "resource_ids": ["INV-100", "INV-101"]
}
~~~

Payload trên là context nghiệp vụ minh họa, không phải bằng chứng xác thực độc lập. Consumer phải xác minh nguồn message và chính sách của job.

### 11.1. Không đưa bearer token vào queue một cách tùy tiện

Bearer token trong message có thể tồn tại lâu hơn thời hạn dự kiến, bị lưu trong dead-letter queue, log hoặc backup, được consumer khác sử dụng lại ngoài mục đích ban đầu, hoặc bị xử lý sau khi quyền của người dùng đã thay đổi.

Thay vào đó, message có thể mang job ID và context tối thiểu. Worker lấy thông tin ủy quyền từ nguồn tin cậy, kiểm tra quyền khi thực thi theo chính sách và kiểm tra quyền khi người dùng tải kết quả.

### 11.2. Xác minh nguồn message

Consumer cần biết:

- Message đến từ producer nào?
- Producer được phép yêu cầu loại job này không?
- Payload có bị sửa đổi không?
- Event có bị phát lại hoặc xử lý trùng không?
- Subject, actor, tenant và resource context có được xác minh không?
- Quyền có cần kiểm tra lại tại thời điểm thực thi không?

Chữ ký message hoặc xác thực broker giúp bảo vệ nguồn và tính toàn vẹn, nhưng không tự cấp quyền nghiệp vụ.

## 12. Thiết kế hợp đồng chuyển tiếp claims

Một hợp đồng nội bộ cho Billing API gọi Document API có thể định nghĩa:

~~~yaml
contract_id: billing-to-documents/v1
caller_service:
  identity: billing-service
  authentication: mutual_tls

incoming_token:
  trusted_issuer: https://identity.example.test
  expected_audience: https://api.example.test/billing
  token_purpose: access_token

downstream_token:
  issuer: https://authorization.example.test
  expected_audience: https://api.example.test/documents
  subject_source: verified_incoming_subject
  actor: billing-service
  allowed_scope:
    - document:read
  tenant_source: verified_membership_context
  maximum_lifetime_seconds: 300

authorization:
  subject_must_be_allowed_for_resource: true
  actor_must_be_authorized_to_delegate: true
  downstream_scope_must_be_narrowed: true
  missing_or_invalid_context: deny
~~~

Đây là đặc tả ứng dụng minh họa, không phải schema chuẩn bắt buộc của JWT hoặc OAuth. Nó giúp các đội thống nhất ai xác thực request đầu vào, dịch vụ nào đang gọi downstream, ai là subject được đại diện, ai là actor, token downstream được phát hành bởi issuer nào, token dành cho audience nào, scope nào được phép, tenant context lấy từ đâu và điều kiện nào khiến request bị từ chối.

### 12.1. Quy tắc về nguồn claims

| Trường | Nguồn được tin | Cách xác minh |
| --- | --- | --- |
| Subject | Issuer token đầu vào | Xác minh JWT, issuer và subject mapping. |
| Actor service | Workload identity của caller | mTLS hoặc cơ chế service authentication được cấu hình. |
| Audience downstream | Authorization Server | Token mới phải có audience phù hợp. |
| Scope downstream | Authorization Server theo grant/policy | Kiểm tra tập scope đã cấp, không chỉ tập scope yêu cầu. |
| Tenant | Nguồn membership có thẩm quyền | Đối chiếu token context với membership hiện hành theo yêu cầu. |
| Resource ID/owner/state | Dịch vụ sở hữu dữ liệu | Tải object từ nguồn dữ liệu và kiểm tra quan hệ. |
| Delegation | Authorization Server hoặc kho delegation | Xác minh actor được phép đại diện subject trong phạm vi cụ thể. |

## 13. Pseudocode: gọi downstream với delegation đúng phạm vi

Ví dụ dưới đây mô tả Billing API nhận request từ người dùng và gọi Document API. Hàm xác minh token phải kiểm tra chữ ký, issuer, audience, thời gian, profile và các claims bắt buộc.

~~~text
function getInvoiceDocument(request):
    incoming = validateAccessToken(
        extractBearerToken(request.headers),
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing"
    )
    if incoming.failed:
        return HTTP 401

    subject = resolvePrincipal(incoming.claims.iss, incoming.claims.sub)
    if subject is null:
        return HTTP 403

    invoice = loadInvoice(request.invoiceId)
    if invoice is null:
        return HTTP 404

    if not billingPolicy.canReadInvoice(subject, invoice):
        return HTTP 404

    if not billingPolicy.canReadAttachedDocument(subject, invoice):
        return HTTP 403

    downstreamToken = authorizationServer.exchange(
        subjectToken = incoming.originalToken,
        actor = authenticatedServiceIdentity("billing-service"),
        audience = "https://api.example.test/documents",
        requestedScope = ["document:read"],
        resourceContext = invoice.documentId
    )
    if downstreamToken.failed:
        return HTTP 403

    response = documentApi.getDocument(
        documentId = invoice.documentId,
        bearerToken = downstreamToken
    )
    return response
~~~

Đây là pseudocode mô tả mục tiêu, không phải cú pháp request RFC 8693 hoàn chỉnh. Authorization Server phải tự kiểm tra subject token, actor/service identity, delegation, resource, audience và quyền được phép. Document API vẫn phải xác minh token downstream và kiểm tra quyền trên document thực tế.

Không được coi resourceContext do Billing API gửi là sự thật chỉ vì Billing API có thể gọi Authorization Server. Authorization Server cần có chính sách xác minh hoặc giới hạn quyền của caller đối với context đó.

## 14. Những lỗi thường gặp khi chuyển tiếp claims

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Tin X-User-Id do client gửi | Mạo danh người dùng. | Gateway xóa/ghi đè header và xác thực nguồn chuyển tiếp. |
| Tin mọi header từ mạng nội bộ | Service bị xâm phạm có thể giả mạo danh tính. | Xác thực workload, giới hạn nguồn và kiểm tra hợp đồng. |
| Chuyển nguyên token có audience sai | Downstream chấp nhận token không dành cho mình nếu bỏ kiểm tra aud. | Mỗi resource server kiểm tra audience. |
| Dùng một token rộng cho mọi API | Token bị lộ ở một dịch vụ có thể mở rộng tác động. | Token theo audience và scope tối thiểu. |
| Tạo JWT mới nhưng giữ iss của issuer gốc | Giả mạo nguồn phát hành hoặc làm sai trust configuration. | Token mới dùng issuer thật sự ký nó; biểu diễn subject/actor riêng. |
| Sao chép tất cả claims vào token mới | Claim không liên quan hoặc có ngữ nghĩa khác bị downstream hiểu nhầm. | Allowlist claims cần thiết và định nghĩa provenance. |
| Coi service identity là user identity | Quyền kỹ thuật của service bị dùng thay quyền của người dùng. | Phân biệt actor, subject và quyền độc lập của service. |
| Dùng actor như permission | Actor xuất hiện trong token nhưng chưa chắc được ủy quyền. | Authorization Server xác minh delegation; downstream kiểm tra policy. |
| Scope downstream rộng hơn nhu cầu | Confused deputy và privilege amplification. | Downscope theo action/resource cần thiết. |
| Chuyển token vào queue/log | Token bị lưu lâu và có thể phát lại. | Chuyển context tối thiểu, tránh lưu bearer token. |
| Tin message payload chỉ vì broker nội bộ | Producer hoặc consumer sai cấu hình có thể giả mạo context. | Xác thực producer, integrity, replay protection và authorization. |
| Không kiểm tra quyền ở downstream | Service trung gian có thể vượt qua policy của API sở hữu resource. | Downstream tự xác minh token và object-level policy. |
| Không phân biệt claims gốc và claims suy ra | Không thể xác định nguồn của quyết định quyền. | Ghi provenance và version hợp đồng. |

## 15. Kiểm thử ranh giới tin cậy giữa các dịch vụ

Kiểm thử phải bao gồm cả token, header, delegation và service identity.

### 15.1. Kiểm thử bearer token relay

~~~text
Token có aud = Billing API, gửi tới Billing API
    -> có thể tiếp tục xác minh quyền

Token có aud = Billing API, gửi tới Document API
    -> từ chối nếu Document API không phải audience được phép

Token hết hạn hoặc issuer không tin cậy
    -> từ chối

Token bị sửa payload nhưng giữ chữ ký cũ
    -> xác minh chữ ký thất bại

Token có audience mảng
    -> xử lý theo chính sách multi-audience đã công bố
~~~

### 15.2. Kiểm thử header forwarding

- Client gửi X-Authenticated-User giả mạo; Gateway phải xóa/ghi đè.
- Client gửi X-Tenant-Id khác; Gateway/API không được tin nếu chưa xác minh.
- Request đi thẳng vào API phía sau không có service identity hợp lệ phải bị từ chối.
- Header trùng tên hoặc nhiều giá trị phải được xử lý theo hợp đồng, không chọn giá trị tùy tiện.
- Header từ proxy không tin cậy phải bị loại bỏ.

### 15.3. Kiểm thử token mới và provenance

- Token do Billing API ký phải được nhận diện với issuer của Billing API hoặc issuer nội bộ thực sự ký token.
- Không chấp nhận token giả khai báo issuer gốc nhưng được ký bằng khóa không thuộc issuer đó.
- Subject và actor phải được phân biệt.
- Actor không được tự đại diện user nếu Authorization Server chưa chấp thuận delegation.
- Token downstream phải có audience và scope đúng.
- Claim tenant/resource phải lấy từ nguồn được hợp đồng cho phép.

### 15.4. Kiểm thử privilege escalation và confused deputy

- User chỉ có invoice.read không thể khiến Billing API gọi document.delete thay mặt họ.
- Service có quyền rộng không được dùng quyền đó cho request user không đủ quyền.
- Downstream từ chối object thuộc tenant khác.
- Token exchange không cấp scope vượt quá policy của subject/actor.
- Token downstream không được dùng ở API khác.

### 15.5. Kiểm thử message và background job

- Message giả mạo producer bị từ chối.
- Event phát lại không gây thực thi lặp ngoài chính sách idempotency.
- Job thực thi sau khi quyền bị thu hồi phải xử lý theo policy hiện hành.
- Kết quả export không thể tải bởi principal khác chỉ nhờ biết job ID.
- Không có bearer token trong log, dead-letter queue hoặc telemetry.

## 16. Checklist thiết kế trust boundary

Trước khi cho phép một dịch vụ chuyển tiếp danh tính hoặc claims, cần trả lời:

1. **Loại bằng chứng:** đang relay JWT gốc, forward header, phát hành token mới hay gửi message context?
2. **Nguồn phát hành:** issuer nào ký token hiện tại; dịch vụ trung gian có thẩm quyền phát hành những claim nào?
3. **Audience:** token dành cho API nào; downstream có kiểm tra audience của chính nó không?
4. **Subject và actor:** ai được đại diện, dịch vụ nào đang hành động, actor có quyền delegation không?
5. **Client/service identity:** client_id, service principal và user principal có được phân biệt không?
6. **Claim provenance:** mỗi claim đến từ issuer, membership service, resource service hay suy luận của intermediary?
7. **Header security:** header từ client có bị xóa/ghi đè; kết nối nội bộ có xác thực peer không?
8. **Downscoping:** quyền downstream có bị giới hạn theo action, resource, tenant và thời hạn không?
9. **Resource policy:** downstream có tự kiểm tra quyền trên object thực tế không?
10. **Token lifecycle:** token có thời hạn phù hợp, có sender constraint hoặc khả năng thu hồi cần thiết không?
11. **Message context:** producer, integrity, replay, idempotency và quyền tại thời điểm xử lý được kiểm soát thế nào?
12. **Audit:** có thể truy vết subject, actor, issuer, audience, service hop, action, resource và quyết định không?
13. **Failure handling:** thiếu claim, issuer sai, actor không hợp lệ hoặc dịch vụ xác minh không khả dụng thì từ chối ra sao?
14. **Testing:** có thử giả mạo header, sai audience, token substitution, confused deputy và quyền downstream quá rộng không?

## 17. Ghi nhớ trọng tâm

- Claims chuyển tiếp không tự đáng tin chỉ vì đi qua một dịch vụ nội bộ.
- JWT gốc giữ tính toàn vẹn nếu được chuyển nguyên vẹn, nhưng downstream vẫn phải kiểm tra issuer, audience, profile, thời gian và quyền.
- Header định danh không có chữ ký; chỉ tin header từ proxy đã xác thực, sau khi header do client gửi được xóa hoặc ghi đè.
- Nếu dịch vụ phát hành JWT mới, token mới là khẳng định của issuer mới; không giả danh issuer gốc.
- Phân biệt **sub** (subject), **act** (actor), **client_id**, **iss** và **aud**.
- Token exchange có thể cấp token cho downstream với audience và quyền hẹp; Authorization Server phải kiểm tra subject, actor và delegation.
- Quyền service không tự động là quyền của user. Cần ngăn confused deputy và privilege amplification.
- Downstream phải tự xác minh token và kiểm tra quyền trên tài nguyên thực tế.
- Bảo vệ cả HTTP headers, message queues, background jobs, cache và audit; không để bearer token lan rộng ngoài nhu cầu.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token); RFC 8725 (JWT Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); RFC 8693 (OAuth 2.0 Token Exchange, bao gồm actor và delegation claims); RFC 8705 (OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens); RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession); RFC 9700 (Best Current Practice for OAuth 2.0 Security). Các chuẩn mô tả token và cơ chế ủy quyền; trust boundary và nguồn thẩm quyền của claims vẫn phải được các dịch vụ thống nhất theo hợp đồng ứng dụng.
