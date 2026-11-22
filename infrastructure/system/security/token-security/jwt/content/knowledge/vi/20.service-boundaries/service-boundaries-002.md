# Xác minh ở biên và kiểm tra lại tại từng ranh giới tin cậy

## 1. Vì sao xác minh ở API Gateway chưa đủ?

Trong hệ thống có nhiều dịch vụ, request thường đi qua một hoặc nhiều lớp trước khi tới nơi thực hiện nghiệp vụ: CDN, WAF, API Gateway, reverse proxy, service mesh và các service phía sau. JWT có thể được xác minh ở cổng API để chặn request không hợp lệ ngay từ bên ngoài.

Tuy nhiên, **mỗi ranh giới tin cậy cần có quyết định xác thực và phân quyền phù hợp với trách nhiệm của thành phần nhận request**. Một service không nên mặc nhiên tin rằng mọi request tới nó đã được gateway xác minh đúng, đặc biệt khi service có thể được gọi từ nhiều nguồn hoặc có đường truy cập nội bộ riêng.

Gateway có thể xác minh token và kiểm tra quyền truy cập route ở mức tổng quát. Service nghiệp vụ vẫn phải biết:

- Request đến từ service hoặc client nào.
- Request đang đại diện cho người dùng hay chủ thể nào.
- Credential được phát hành bởi issuer nào và dành cho service nào.
- Claims, audience, thời hạn và phạm vi quyền có phù hợp không.
- Chủ thể có được phép thực hiện hành động trên đúng tài nguyên này không.

Một JWT có chữ ký hợp lệ chỉ là một phần của quyết định. Nó không tự chứng minh token dành cho service hiện tại, không xác định quyền trên mọi tài nguyên và không bảo đảm request đã đi qua đúng gateway.

**Nguyên tắc:** xác minh tại biên giúp loại request không hợp lệ sớm; mỗi thành phần nhận dữ liệu qua một ranh giới tin cậy phải xác lập danh tính và quyền mà nó cần dựa trên một cơ chế có thể kiểm chứng.

## 2. Ranh giới tin cậy xuất hiện ở đâu?

Ranh giới tin cậy là điểm mà dữ liệu, danh tính hoặc quyền từ một vùng bảo mật được chuyển sang một vùng có mức tin cậy, chủ thể quản trị hoặc trách nhiệm khác.

Ví dụ:

~~~mermaid
flowchart LR
    U["Browser / Client"] --> E["Edge / WAF"]
    E --> G["API Gateway"]
    G --> O["Orders Service"]
    O --> P["Payments Service"]
    O --> Q["Message Broker"]
    Q --> W["Background Worker"]
    P --> D["Payment Provider"]
~~~

Các ranh giới có thể gồm:

| Ranh giới | Câu hỏi cần xác minh |
| --- | --- |
| Client → Edge | Kết nối có được bảo vệ? Request có hợp lệ và nằm trong giới hạn không? |
| Edge → Gateway | Thành phần gửi có được tin cậy? Header nào do edge tạo và header nào do client gửi? |
| Gateway → Service | Gateway có được phép gọi service? Danh tính người dùng/subject được chuyển tiếp bằng cách nào? |
| Service → Service | Service gọi có được xác thực? Token có đúng audience và scope của service nhận không? |
| Service → Broker | Message đến từ producer nào? Consumer nào được phép xử lý? |
| Broker → Worker | Message có nguồn gốc, tenant, thời hạn và trạng thái hợp lệ không? |
| Service → External API | Credential có được cấp cho đúng provider/resource và đúng hành động không? |

Không phải mọi ranh giới đều cần cùng một loại token hoặc cùng một bước xác minh. Một kết nối nội bộ có thể dùng mTLS để xác thực service; một JWT có thể mang danh tính người dùng; một message có thể dùng chữ ký hoặc cơ chế xác thực của broker. Điều quan trọng là xác định rõ **ai đang được xác thực, bằng chứng nào được kiểm tra và quyết định nào được đưa ra**.

## 3. Gateway nên xác minh điều gì?

Gateway là điểm kiểm soát hữu ích để xác minh credential trước khi request đi sâu vào hệ thống. Với access token JWT, gateway thường kiểm tra tối thiểu:

1. Cấu trúc và định dạng token đúng profile mà endpoint chấp nhận.
2. Thuật toán nằm trong allowlist và phù hợp với loại khóa.
3. Chữ ký JWS hợp lệ bằng khóa lấy từ nguồn tin cậy đã cấu hình.
4. `iss` khớp issuer được tin cậy.
5. `aud` phù hợp với gateway hoặc resource/API theo hợp đồng token.
6. `exp`, `nbf` và các giới hạn thời gian hợp lệ, có tính đến clock skew nhỏ đã quy định.
7. Loại token/profile phù hợp, tránh nhầm access token với ID token hoặc assertion dùng cho mục đích khác.
8. Claims có kiểu dữ liệu và cấu trúc đáp ứng profile.
9. Scope hoặc quyền tổng quát đủ để đi vào route được yêu cầu.

Nếu token là JWE, gateway cần giải mã và xác thực authentication tag bằng khóa phù hợp trước khi sử dụng plaintext. Nếu payload là nested JWT, phải xử lý các lớp theo profile đã định nghĩa và xác minh lớp chữ ký cần thiết.

### Gateway không thể thay service quyết định mọi quyền

Gateway có thể biết request được phép gọi POST /orders, nhưng chưa chắc biết người dùng có quyền sửa **đơn hàng cụ thể** mà request nhắm tới. Quyết định đó có thể phụ thuộc vào:

- Đơn hàng có thuộc đúng người dùng hoặc tenant không.
- Trạng thái hiện tại của đơn hàng.
- Người dùng có vai trò quản lý đơn hàng đó không.
- Hạn mức, quy trình phê duyệt hoặc chính sách nghiệp vụ.
- Quan hệ giữa subject, actor và tài nguyên tại thời điểm xử lý.

Vì vậy, gateway nên thực hiện xác minh và kiểm soát route; service sở hữu tài nguyên phải thực hiện authorization cho hành động nghiệp vụ cụ thể.

## 4. Service phía sau có cần xác minh lại JWT không?

Câu trả lời phụ thuộc vào cách service nhận danh tính và vào trust model đã thiết kế. Có hai mô hình thường gặp.

### Mô hình A — Service tự xác minh access token

Gateway chuyển tiếp access token tới service. Service tự xác minh chữ ký, issuer, audience, thời hạn và claims theo profile mà service chấp nhận.

Mô hình này phù hợp khi:

- Service có thể được gọi từ nhiều gateway hoặc caller.
- Service có endpoint nội bộ mà không thể bảo đảm mọi request đều qua một gateway duy nhất.
- Service cần kiểm soát audience và scope riêng.
- Service là ranh giới bảo mật độc lập hoặc cần khả năng phòng thủ nhiều lớp.

Token phải có audience phù hợp với service nhận. Nếu token chỉ dành cho `orders-api`, Payments Service không nên chấp nhận nó chỉ vì Orders Service đã xác minh thành công. Payments Service cần credential dành cho chính nó hoặc một cơ chế delegation được tin cậy.

### Mô hình B — Gateway xác minh và chuyển identity context đáng tin cậy

Một service có thể không nhận raw JWT của người dùng. Gateway xác minh token bên ngoài, sau đó gửi một identity context được bảo vệ qua kênh service-to-service đã xác thực.

Identity context có thể là:

- Một assertion nội bộ được ký, có audience và thời hạn ngắn.
- Metadata được truyền trên kết nối mTLS, trong đó service nhận xác thực danh tính gateway và chỉ tin các trường gateway đã tạo.
- Một credential nội bộ do hệ thống phát hành theo profile delegation riêng.

Mô hình này chỉ an toàn khi các điều kiện trust được thiết kế và thực thi rõ:

- Service chỉ nhận request từ caller được xác thực, ví dụ gateway có service identity qua mTLS.
- Backend không thể bị truy cập trực tiếp từ mạng không tin cậy hoặc đường truy cập trực tiếp cũng có xác thực tương đương.
- Gateway xóa các identity header do client gửi vào rồi tự tạo lại giá trị sau khi xác minh.
- Identity context được bảo vệ khỏi sửa đổi và gắn với đúng service nhận.
- Service biết rõ issuer/gateway nào được phép phát hành context và schema nào được chấp nhận.
- Có thời hạn ngắn, giới hạn quyền và cơ chế xử lý replay phù hợp.

**Chỉ đặt service trong private network không đủ để tin mọi header danh tính.** Sai cấu hình mạng, SSRF, service bị xâm nhập hoặc một caller nội bộ không được phép đều có thể làm ranh giới này bị vượt qua.

## 5. Vì sao không được tin các identity header do client tự gửi?

Một anti-pattern phổ biến là gateway hoặc proxy thêm các header như:

~~~http
X-User-Id: user-123
X-User-Roles: admin
X-Tenant-Id: tenant-17
~~~

Nếu backend nhận các header này mà không xác thực nguồn gửi, client có thể tự thêm hoặc sửa chúng để mạo danh người dùng khác hoặc tự nâng quyền.

Ví dụ request độc hại:

~~~http
GET /admin/reports HTTP/1.1
Host: api.example
X-User-Id: administrator
X-User-Roles: admin
~~~

Nếu gateway chỉ kiểm tra token nhưng vẫn chuyển tiếp header do client cung cấp, hoặc backend ưu tiên header đó, attacker có thể vượt qua kiểm tra danh tính.

### Quy tắc xử lý identity header

1. Ở biên nhận request từ client, loại bỏ các header danh tính nội bộ được dành riêng cho gateway.
2. Chỉ tạo lại header sau khi xác minh credential và ánh xạ subject/claims theo chính sách.
3. Chỉ chuyển tiếp qua kết nối có xác thực caller, ví dụ mTLS hoặc service identity tương đương.
4. Backend phải kiểm tra danh tính caller và chỉ chấp nhận identity context từ nguồn đã cấu hình.
5. Nếu backend có thể được gọi trực tiếp, đường gọi đó cũng phải bảo vệ identity context; không dựa vào giả định rằng gateway luôn đứng trước.

Tên header không tạo ra độ tin cậy. Độ tin cậy đến từ kênh truyền, danh tính caller, tính toàn vẹn của context và chính sách kiểm tra ở bên nhận.

## 6. Audience ngăn token bị dùng nhầm giữa các service

Claim `aud` xác định bên nhận dự kiến của token. Đây là cơ chế quan trọng khi một hệ thống có nhiều API hoặc service độc lập.

Giả sử issuer phát hành token:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456300
}
~~~

Orders Service có thể chấp nhận token nếu issuer, audience, chữ ký, thời hạn và policy đều hợp lệ. Payments Service không được tự động chấp nhận cùng token vì nó không phải audience đã định.

Nếu Orders Service cần gọi Payments Service, hệ thống nên dùng một credential được cấp cho Payments Service và thể hiện đúng quyền cần thiết. Các lựa chọn gồm:

- Token service-to-service riêng của Orders Service.
- Token exchange để đổi token đầu vào thành token có audience và scope phù hợp với Payments Service.
- Identity/delegation assertion nội bộ được phát hành theo profile rõ ràng.

Không nên dùng một token có audience quá rộng cho toàn bộ hệ thống chỉ để tránh phải cấp token theo từng service. Điều đó làm tăng hậu quả nếu token bị lộ và tạo điều kiện cho confused deputy.

## 7. Token exchange và delegation giữa các service

OAuth 2.0 Token Exchange (RFC 8693) cung cấp một cơ chế chuẩn để đổi một security token lấy token khác theo ngữ cảnh và chính sách của Authorization Server.

Ví dụ, Orders Service nhận access token dành cho Orders API. Khi cần gọi Payments Service thay mặt người dùng, Orders Service có thể yêu cầu token mới với audience/resource và scope dành cho Payments Service, nếu AS cho phép delegation đó.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Orders Service
    participant AS as Authorization Server
    participant P as Payments Service

    U->>O: Access token aud=orders-api
    O->>O: Verify token và quyền trên order
    O->>AS: Token exchange: subject token + actor identity + target audience
    AS->>AS: Kiểm tra trust, delegation và policy
    AS-->>O: Token aud=payments-api, scope=payments:authorize
    O->>P: Request + token dành cho Payments
    P->>P: Verify issuer, audience, scope và caller
    P->>P: Authorize thao tác thanh toán
    P-->>O: Kết quả
~~~

Token mới có thể giữ subject là người dùng và biểu diễn actor là service đang hành động thay mặt subject theo profile hỗ trợ. Điều này giúp Payments Service phân biệt:

- **Subject:** chủ thể mà hành động được thực hiện thay mặt.
- **Actor/client:** service thực sự gửi request.
- **Audience/resource:** service nhận được phép sử dụng token.
- **Scope/authorization details:** hành động được phép trong ngữ cảnh đó.

Token exchange không tự động cho phép delegation. Authorization Server phải xác định client nào được đổi token, subject nào được đại diện, audience nào được yêu cầu và quyền nào có thể cấp. Service nhận vẫn phải xác minh token mới và kiểm tra quyền trên tài nguyên.

## 8. Xác thực service-to-service khác với xác thực người dùng

Khi Orders Service gọi Payments Service, có ít nhất hai câu hỏi độc lập:

1. **Ai đang gọi?** Đây là danh tính service/client gửi request.
2. **Service đang hành động thay mặt ai và được phép làm gì?** Đây là subject, delegation context và quyền nghiệp vụ.

mTLS có thể xác thực danh tính workload hoặc service ở lớp kết nối. Nhưng mTLS một mình không chứng minh người dùng cuối có quyền thanh toán đơn hàng. Ngược lại, JWT của người dùng không nhất thiết chứng minh service gọi có được phép truy cập endpoint nội bộ.

Một request nhạy cảm có thể cần cả hai:

- Xác thực caller là Orders Service qua mTLS hoặc service credential.
- Xác minh access token/delegation token dành cho Payments Service.
- Kiểm tra subject, actor, tenant, scope và trạng thái tài nguyên.
- Áp dụng policy của Payments Service trước khi thực hiện hành động.

Không được dùng một danh tính để suy ra danh tính còn lại. Service identity và user identity có vai trò khác nhau và cần được liên kết theo policy rõ ràng.

## 9. Kiểm tra lại claims ở mỗi service theo trách nhiệm của nó

“Kiểm tra lại” không có nghĩa mọi service phải lặp lại toàn bộ mọi bước giống hệt gateway. Nó có nghĩa service nhận phải xác lập đủ bằng chứng và điều kiện để đưa ra quyết định của chính mình.

| Kiểm tra | Gateway | Service nhận |
| --- | --- | --- |
| Xác thực nguồn credential | Xác minh issuer/key và token profile | Tự xác minh token hoặc xác minh identity context từ caller tin cậy |
| Audience | Kiểm tra token dành cho API/gateway theo profile | Kiểm tra token/context dành cho chính service |
| Thời hạn | Kiểm tra `exp`, `nbf` và clock skew | Không chấp nhận context đã hết hạn; áp dụng chính sách thời gian riêng |
| Scope/permission tổng quát | Có thể kiểm tra quyền gọi route | Kiểm tra quyền cần cho thao tác nghiệp vụ |
| Tenant/resource ownership | Có thể kiểm tra ở mức route nếu đủ dữ liệu | Service sở hữu tài nguyên kiểm tra quan hệ tenant và resource |
| Service caller | Xác thực caller nội bộ khi cần | Xác thực service gọi bằng mTLS hoặc credential nội bộ |
| Replay/revocation | Có thể áp dụng ở cổng | Áp dụng theo loại token và rủi ro của thao tác |
| Audit | Ghi nhận quyết định tại gateway | Ghi nhận actor, subject và quyết định nghiệp vụ |

Một service có thể tin kết quả xác minh của gateway nếu identity context được chuyển qua một kênh tin cậy và backend chỉ nhận context từ gateway đã xác thực. Nhưng service không nên tin một cờ boolean kiểu `X-Token-Verified: true` từ một request bất kỳ. Bên nhận phải biết ai đã đưa ra khẳng định đó và vì sao khẳng định không thể bị giả mạo.

## 10. Đừng biến gateway thành confused deputy

**Confused deputy** xảy ra khi một thành phần có quyền cao bị thuyết phục sử dụng quyền của mình cho một caller không có quyền tương ứng.

Ví dụ:

- Gateway có credential gọi Payments Service.
- Người dùng chỉ có quyền đọc đơn hàng.
- Request đi qua Orders Service yêu cầu thanh toán.
- Orders Service dùng credential rộng của chính nó gọi Payments mà không truyền hoặc kiểm tra delegation của người dùng.

Payments Service chỉ thấy một caller đáng tin là Orders Service và có thể thực hiện thao tác mà người dùng ban đầu không được phép.

Để giảm rủi ro:

- Tách service authentication khỏi user authorization.
- Giữ subject/actor context rõ ràng khi delegation được phép.
- Dùng token có audience và scope giới hạn cho service nhận.
- Authorization Server kiểm soát việc đổi token và delegation.
- Service đích kiểm tra quyền trên tài nguyên và trạng thái nghiệp vụ.
- Không để service dùng quyền máy móc rộng hơn quyền đã được policy cấp cho request hiện tại.

Service có thể có quyền kỹ thuật gọi service khác, nhưng mỗi hành động thay mặt người dùng vẫn phải tuân theo delegation policy và authorization tại nơi sở hữu tài nguyên.

## 11. Ranh giới bất đồng bộ: message broker và background worker

Không phải mọi request đều được xử lý đồng bộ. Service có thể đưa message vào queue để worker xử lý sau. Khi đó access token ban đầu có thể hết hạn trước khi worker chạy.

Không nên mặc định chuyển nguyên bearer token vào message và tin rằng chữ ký hợp lệ đủ để xử lý an toàn. Cần xác định message đang đại diện cho:

- Một sự kiện đã xảy ra, ví dụ OrderCreated.
- Một lệnh cần thực hiện, ví dụ CapturePayment.
- Một yêu cầu tiếp tục thực hiện thay mặt một subject cụ thể.

Các lựa chọn thiết kế:

- Dùng broker authentication/authorization để xác thực producer và consumer.
- Ký hoặc bảo vệ message theo cơ chế đã thống nhất nếu cần xác thực nguồn gốc xuyên broker.
- Mang subject, actor, tenant và correlation ID tối thiểu khi cần audit/delegation.
- Gắn message với consumer/audience hoặc loại công việc được phép.
- Đặt thời hạn xử lý, nonce/idempotency key và chống xử lý trùng.
- Với lệnh cần quyền tại thời điểm thực thi, re-evaluate policy hoặc lấy credential mới theo delegation policy; không dựa mù quáng vào quyền cũ đã nhúng trong message.
- Giới hạn payload và không đưa access token dài hạn vào queue/log nếu không cần thiết.

Một event bất biến ghi nhận sự kiện đã được xác nhận có thể được xử lý theo mô hình event trust riêng. Một command yêu cầu chuyển tiền hoặc thay đổi dữ liệu cần authorization rõ tại thời điểm worker thực hiện.

## 12. Cache kết quả xác minh và rủi ro khi tin dữ liệu cũ

Để giảm chi phí xác minh chữ ký, một service có thể cache kết quả hoặc metadata đã kiểm tra. Cache không được làm mất các điều kiện thời gian và trust.

Cần cân nhắc:

- Cache không vượt quá `exp` hoặc thời hạn của identity context.
- Key cache phải gắn với token/context cụ thể, issuer và profile; không cache chỉ theo subject.
- Khi khóa bị thu hồi hoặc JWKS thay đổi, có chính sách làm mới cache.
- Khi cần thu hồi nhanh, phải có cơ chế denylist/introspection hoặc invalidation phù hợp.
- Không dùng kết quả xác minh của một audience cho service khác.
- Không dùng cache để bỏ qua authorization trên tài nguyên có trạng thái thay đổi nhanh.

Ngay cả khi chữ ký và claims được cache là hợp lệ, quyền trên tài nguyên có thể thay đổi giữa hai request. Ví dụ người dùng vừa bị thu hồi quyền quản trị hoặc đơn hàng đã chuyển sang trạng thái không cho phép hủy. Authorization cần được đánh giá theo dữ liệu và chính sách tại thời điểm thao tác.

## 13. Xử lý lỗi ở từng ranh giới

Mỗi thành phần phải từ chối request khi không thể xác lập danh tính hoặc quyền cần thiết. Không nên “fail open” bằng cách bỏ qua xác minh khi JWKS endpoint lỗi, service identity không rõ hoặc identity context không hợp lệ.

Một số quy tắc:

| Tình huống | Hành vi phù hợp |
| --- | --- |
| Chữ ký không hợp lệ hoặc token sai định dạng | Từ chối credential |
| Issuer không tin cậy | Từ chối |
| Audience không dành cho service nhận | Từ chối |
| Token hết hạn hoặc chưa có hiệu lực | Từ chối |
| Caller service không được xác thực | Từ chối kết nối/request |
| Identity header đến từ client hoặc caller không tin cậy | Xóa/bỏ qua và không dùng làm danh tính |
| Token hợp lệ nhưng thiếu scope | Từ chối hành động do thiếu quyền |
| Subject hợp lệ nhưng không sở hữu tài nguyên | Từ chối theo policy tài nguyên |
| Không thể lấy khóa hoặc không thể xác minh | Từ chối hoặc áp dụng chính sách availability đã định nghĩa; không tin token chưa xác minh |
| Message bị trùng hoặc idempotency key đã dùng | Trả kết quả đã lưu hoặc từ chối theo semantics của thao tác |

Trong HTTP API, 401 thường biểu thị thiếu hoặc credential không hợp lệ; 403 biểu thị danh tính đã được xác lập nhưng không đủ quyền. Hệ thống có thể dùng mã lỗi nội bộ hoặc response khác theo giao thức, nhưng không nên tiết lộ chi tiết nhạy cảm về khóa, issuer nội bộ hoặc policy.

## 14. Ví dụ: gateway xác minh đúng nhưng service vẫn phải từ chối

Một người dùng có token:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456300
}
~~~

Gateway xác minh chữ ký, issuer, audience và thời hạn thành công. Người dùng gọi Orders Service để đọc đơn hàng. Orders Service kiểm tra quyền đọc và xác nhận đơn hàng thuộc tenant của subject; request được phép.

Sau đó Orders Service gọi Payments Service để capture payment. Nếu nó chuyển nguyên token trên cho Payments Service:

- `aud` chỉ dành cho `orders-api`, không dành cho `payments-api`.
- Scope chỉ có `orders:read`, không có quyền thanh toán.
- Token không chứng minh Orders Service được phép thực hiện hành động thay mặt người dùng.

Payments Service phải từ chối token đó. Nếu nghiệp vụ cho phép, Orders Service cần dùng token exchange hoặc delegation credential có audience `payments-api`, scope phù hợp và actor là Orders Service. Payments Service xác minh credential mới, xác thực caller và kiểm tra payment/order state trước khi thực hiện.

Ví dụ này cho thấy **một lần xác minh thành công ở gateway không phải giấy phép toàn hệ thống**. Mỗi service chỉ nhận và thực hiện những quyền được cấp rõ cho nó.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng gateway verify rồi thì backend không cần trust check | Request đi đường khác có thể bỏ qua gateway | Xác minh token hoặc identity context tại ranh giới backend |
| Tin mọi request từ private network | Caller nội bộ bị xâm nhập có thể giả danh | Xác thực service identity và giới hạn network path |
| Tin `X-User-Id` hoặc `X-User-Roles` do client gửi | User spoofing và privilege escalation | Strip header đầu vào, tạo context sau xác minh và bảo vệ kênh |
| Dùng token audience của Orders cho Payments | Token substitution hoặc confused deputy | Dùng token exchange/audience dành cho Payments |
| Chỉ xác thực service caller, bỏ qua subject | Service có thể dùng quyền máy móc thay người dùng | Giữ delegation context và kiểm tra authorization |
| Chỉ kiểm tra scope ở gateway | Bỏ sót ownership, tenant và trạng thái tài nguyên | Service sở hữu tài nguyên kiểm tra quyền nghiệp vụ |
| Chuyển tiếp token bên ngoài tới mọi service | Mở rộng phạm vi token và tăng hậu quả khi lộ | Chỉ forward khi audience cho phép; nếu cần hãy exchange |
| Tin header `X-Token-Verified: true` | Caller có thể tự khai kết quả xác minh | Dùng assertion/kênh tin cậy có xác thực nguồn |
| Đưa bearer token vào message queue không cần thiết | Token có thể tồn tại lâu trong broker/log/backup | Dùng identity context tối thiểu và policy xử lý message |
| Dùng cache xác minh vô thời hạn | Tiếp tục tin token/khóa đã hết hạn hoặc bị thu hồi | Giới hạn TTL và xử lý key/revocation invalidation |
| Không phân biệt 401 và 403 | Khó vận hành và dễ xử lý lỗi sai | Phân biệt credential không hợp lệ với thiếu quyền |

## 16. Checklist thiết kế ranh giới dịch vụ

**Ở edge và gateway**

- Xác định token profile và loại credential được endpoint chấp nhận.
- Xác minh chữ ký/MAC hoặc giải mã JWE bằng khóa tin cậy.
- Kiểm tra issuer, audience, thời hạn, loại token và claims.
- Kiểm tra scope ở mức route khi phù hợp.
- Xóa các identity header do client gửi và chỉ tạo lại sau xác minh.
- Giới hạn request size, chống replay theo profile và che token khỏi log.
- Không coi gateway là nơi duy nhất quyết định quyền tài nguyên.

**Ở service nhận request**

- Xác thực service caller qua mTLS hoặc cơ chế service identity phù hợp.
- Quy định rõ nhận raw JWT hay trusted identity context.
- Nếu tự xác minh JWT, kiểm tra audience, issuer, key, expiry và claims theo profile riêng.
- Nếu tin identity context, xác thực nguồn phát hành, kênh truyền, audience và thời hạn của context.
- Không tin header danh tính từ caller chưa xác thực.
- Kiểm tra scope, tenant, ownership, trạng thái và quyền trên tài nguyên.
- Giữ subject và actor riêng biệt khi có delegation.
- Áp dụng replay, revocation và cache policy theo mức rủi ro.

**Khi gọi service khác hoặc xử lý bất đồng bộ**

- Dùng token có audience dành cho service nhận.
- Dùng token exchange/delegation khi cần thay mặt người dùng.
- Giới hạn scope và thời hạn theo hành động.
- Xác thực service identity độc lập với user identity.
- Không chuyển tiếp bearer token rộng hơn nhu cầu.
- Bảo vệ message, kiểm tra producer/consumer và xử lý idempotency.
- Đánh giá lại quyền tại thời điểm worker thực thi nếu chính sách yêu cầu.

**Ghi nhớ:** Gateway xác minh token giúp bảo vệ cổng vào, nhưng không thay thế việc xác lập trust và authorization tại các service. Service nhận phải biết caller là ai, subject là ai, token/context dành cho ai và hành động nào được phép. Có thể tự xác minh JWT hoặc tin identity context do gateway phát hành, nhưng lựa chọn thứ hai chỉ an toàn khi caller, kênh truyền, nguồn phát hành và tính toàn vẹn của context đều được bảo vệ. Audience, token exchange, service identity và authorization tại nơi sở hữu tài nguyên giúp ngăn token bị dùng nhầm giữa các service và giảm rủi ro confused deputy.

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** claims iss, sub, aud, exp, nbf, iat và jti.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra issuer, audience, thuật toán và phân biệt loại JWT.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** profile access token JWT và validation tại Resource Server.
- **RFC 8693 — OAuth 2.0 Token Exchange:** đổi token, subject token, actor token và delegation giữa các service.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client/service bằng mTLS và ràng buộc token với chứng thư.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái token tại Authorization Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ access token và giới hạn quyền.
