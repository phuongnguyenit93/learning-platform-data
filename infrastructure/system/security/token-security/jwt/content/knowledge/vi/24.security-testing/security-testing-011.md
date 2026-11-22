# Token bị dùng chéo dịch vụ, tenant hoặc mục đích

## 1. Mục tiêu của kiểm thử

Một JWT có thể có chữ ký hợp lệ, issuer đáng tin cậy và thời hạn còn hiệu lực nhưng vẫn không được phép sử dụng tại dịch vụ, tenant hoặc giao thức đang nhận nó. Kiểm thử bảo mật cần chứng minh hệ thống giữ đúng các ranh giới này, kể cả khi nhiều thành phần dùng chung Identity Provider, signing key, JWKS hoặc một gateway.

Các tình huống cần phát hiện gồm:

- Token dành cho API A được gửi tới API B.
- Token thuộc tenant A được dùng để truy cập dữ liệu tenant B.
- ID Token, client assertion, DPoP proof hoặc JWT nội bộ bị dùng thay Access Token.
- Token của môi trường staging được gửi tới production.
- Token của phiên hoặc giao dịch khác bị ghép vào request hiện tại.
- Gateway xác minh token nhưng downstream service chấp nhận nhầm token hoặc identity context.
- Token có scope đúng tên nhưng audience, tenant, subject, client hoặc resource không phù hợp.

Mục tiêu không chỉ là xác nhận token sai bị từ chối. Bộ kiểm thử phải chứng minh token đúng vẫn hoạt động, quyền không bị mở rộng và lỗi ở một ranh giới không làm suy yếu ranh giới khác.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Kiểm thử bảo mật. Phạm vi áp dụng chung cho OAuth, OIDC, JWT và kiến trúc dịch vụ; không phụ thuộc Java, Spring Security hoặc một framework cụ thể.

## 2. Phân biệt các loại nhầm lẫn cần kiểm thử

| Nhóm | Mô tả | Ví dụ |
| --- | --- | --- |
| Cross-service token use | Token dành cho một Resource Server được gửi tới Resource Server khác | aud=invoice-api gửi tới Profile API |
| Cross-tenant substitution | Token hoặc context của tenant này được dùng trong tenant khác | Token tenant-blue truy cập dữ liệu tenant-red |
| Cross-JWT confusion | JWT hợp lệ thuộc token class/profile khác bị chấp nhận | ID Token được API nhận như Access Token |
| Cross-client substitution | Token được cấp cho client hoặc actor khác được dùng sai ngữ cảnh | Assertion của client A được gửi trong luồng client B |
| Cross-environment substitution | Credential của môi trường ít tin cậy được dùng ở môi trường nhạy cảm hơn | Token staging gửi tới production |
| Cross-session/transaction substitution | Token, code hoặc proof của giao dịch khác được ghép vào giao dịch hiện tại | ID Token có nonce khác hoặc Code thuộc phiên khác |
| Gateway/downstream confusion | Gateway và service phía sau áp dụng các trust rule khác nhau | Gateway xác minh token gateway rồi service tin raw token |

Các nhóm này có thể chồng lấp. Ví dụ, một ID Token có thể vừa sai token class vừa có audience của client thay vì API; một token từ tenant khác có thể được chuyển tiếp qua gateway mà không kiểm tra tenant context.

## 3. Xác định threat model và trust boundary

Trước khi viết test, xác định rõ các thành phần và nơi token đi qua:

~~~mermaid
flowchart LR
    U["Client / User Agent"] --> G["API Gateway"]
    G --> A["Invoice API"]
    G --> B["Profile API"]
    G --> C["Reporting API"]
    AS["Authorization Server / OIDC Provider"] --> U
    AS --> G
    AS --> A
    AS --> B
    AS --> C
    T["Tenant / Session Context"] --> A
    T --> B
    T --> C
~~~

Liệt kê cho mỗi endpoint:

- Token class/profile được chấp nhận.
- Issuer và nguồn khóa được tin cậy.
- Audience identifier.
- Thuộc tính client, subject, actor và tenant cần kiểm tra.
- Scope hoặc quyền tối thiểu.
- Session, transaction hoặc sender binding nếu có.
- Nơi kiểm tra revocation/replay.
- Thành phần nào có quyền tạo identity context nội bộ.

Không giả định mọi service đều có cùng policy chỉ vì chúng dùng chung issuer hoặc thư viện. Mỗi Resource Server cần một hợp đồng nhận token rõ ràng.

### 3.1. Xác định attacker capability

Test nên mô phỏng các khả năng thực tế:

- Attacker lấy được một Access Token hợp lệ nhưng dành cho API khác.
- Attacker có ID Token hoặc assertion hợp lệ từ cùng issuer.
- Attacker có token của tenant hoặc session khác.
- Attacker có thể tự gửi header, path, query hoặc resource indicator.
- Attacker có thể phát lại request hoặc token đã quan sát.
- Attacker kiểm soát một service nội bộ có quyền thấp hơn và thử gọi service khác.

Không cần giả định attacker có thể ký token bằng private key của issuer. Các lỗi audience/profile/tenant thường xảy ra ngay cả khi attacker chỉ tái sử dụng credential hợp lệ bị lấy từ một ngữ cảnh khác.

## 4. Các invariant bảo mật phải giữ

Một bộ kiểm thử tốt cần xác nhận những invariant sau:

1. Mỗi API chỉ chấp nhận token có audience phù hợp với chính API đó.
2. Issuer phải khớp trust configuration; token không được tự chọn issuer hoặc nguồn khóa.
3. Token class/profile phải khớp endpoint nhận.
4. Tenant trong token hoặc context phải được đối chiếu với tenant đã xác định và được phép truy cập.
5. Subject, client và actor không được hoán đổi tùy tiện.
6. Scope không thể bù cho audience sai; audience đúng cũng không tự cấp quyền.
7. Token của môi trường khác không được chấp nhận chỉ vì dùng chung định dạng.
8. Nonce, state, PKCE, at_hash/c_hash và DPoP proof phải được kiểm tra khi flow yêu cầu.
9. Gateway không được tin header identity do client tự gửi.
10. Downstream chỉ tin raw token nếu nó tự xác minh token theo audience/profile của chính nó, hoặc tin context nội bộ qua một trust channel được bảo vệ.
11. Cache không được làm mất ranh giới issuer, audience, tenant hoặc policy.
12. Mọi lỗi validation bắt buộc phải chặn thao tác trước khi truy cập dữ liệu hoặc thực hiện side effect.

## 5. Chuẩn bị test fixture và token có kiểm soát

Tạo test fixture trong môi trường kiểm thử riêng, dùng issuer, khóa và dữ liệu giả lập. Không dùng token production, private key production hoặc dữ liệu người dùng thật.

### 5.1. Fixture cho nhiều dịch vụ

Ví dụ hệ thống kiểm thử:

| Thành phần | Định danh |
| --- | --- |
| Issuer | https://test-id.example.org/ |
| Invoice API | https://test-api.example.org/invoices |
| Profile API | https://test-api.example.org/profiles |
| Reporting API | https://test-api.example.org/reports |
| Gateway | https://test-api.example.org/gateway |
| Tenant X | tenant-blue |
| Tenant Y | tenant-red |
| Client A | portal-client |
| Client B | mobile-client |

Tạo khóa kiểm thử riêng cho issuer và publish public keys qua JWKS test endpoint đã cấu hình. Có thể dùng cùng issuer và cùng signing key cho các API trong một số test để chứng minh audience validation thực sự hoạt động; test khác nên dùng issuer/key khác để kiểm tra trust boundary.

### 5.2. Fixture token

Tạo các token có cùng những claims chung nhưng khác một thuộc tính quan trọng:

~~~json
{
  "iss": "https://test-id.example.org/",
  "sub": "user-100",
  "aud": "https://test-api.example.org/invoices",
  "client_id": "portal-client",
  "tenant_id": "tenant-blue",
  "scope": "invoice:read",
  "iat": 1893456000,
  "exp": 1893456900,
  "jti": "test-token-001"
}
~~~

Các fixture khác lần lượt thay aud, tenant_id, client_id, sub, typ, issuer, thời hạn hoặc transaction binding. Khi chỉ thay một thuộc tính, kết quả test giúp xác định chính xác ranh giới nào đang được kiểm tra. Dùng test clock cố định và chọn iat/exp tương đối với clock đó để ca hết hạn không phụ thuộc thời điểm chạy test.

Không chỉ dùng token malformed. Các trường hợp quan trọng nhất thường là **token có chữ ký đúng nhưng sai ngữ cảnh**.

### 5.3. Ma trận token cơ sở

| Fixture | Chữ ký | Issuer | Audience | Tenant | Profile |
| --- | --- | --- | --- | --- | --- |
| T-invoice-blue | Hợp lệ | Tin cậy | Invoice API | Blue | Access Token |
| T-profile-blue | Hợp lệ | Tin cậy | Profile API | Blue | Access Token |
| T-invoice-red | Hợp lệ | Tin cậy | Invoice API | Red | Access Token |
| T-staging | Hợp lệ | Staging | Staging API | Blue | Access Token |
| T-report-blue | Hợp lệ | Tin cậy | Reporting API | Blue | Access Token |
| T-id-token | Hợp lệ | Tin cậy | OIDC Client | Blue | ID Token |
| T-client-assertion | Hợp lệ | Client/issuer theo profile | Token Endpoint | Không áp dụng | Client Assertion |
| T-expired | Hợp lệ | Tin cậy | Invoice API | Blue | Access Token đã hết hạn |
| T-bad-signature | Không hợp lệ | Khai báo đúng | Invoice API | Blue | Access Token |

## 6. Kiểm thử token bị dùng chéo giữa các dịch vụ

Đây là nhóm kiểm thử cơ bản nhất khi có nhiều Resource Server cùng tin một Authorization Server.

### 6.1. Positive test: token đúng API

1. Lấy T-invoice-blue.
2. Gửi request đọc tài nguyên giả lập tại Invoice API.
3. Đảm bảo chữ ký, issuer, audience, thời gian, profile và scope đều đạt.
4. Xác nhận request được xử lý theo authorization policy.

Lặp lại với token dành cho Profile API và Reporting API.

### 6.2. Negative test: token API A gửi tới API B

| Token gửi | API nhận | Kết quả mong đợi |
| --- | --- | --- |
| T-invoice-blue | Invoice API | Chấp nhận nếu authorization đạt |
| T-invoice-blue | Profile API | Từ chối audience mismatch |
| T-invoice-blue | Reporting API | Từ chối audience mismatch |
| T-profile-blue | Invoice API | Từ chối audience mismatch |
| T-profile-blue | Reporting API | Từ chối audience mismatch |
| T-report-blue | Invoice API | Từ chối audience mismatch |

Giữ nguyên issuer, signing key, subject và thời gian giữa các fixture; chỉ thay audience. Điều này chứng minh hệ thống không dựa vào sự khác biệt khóa để vô tình chặn token.

### 6.3. Kiểm thử exact audience matching

Tạo token có aud gần giống nhưng không bằng identifier đã cấu hình:

- Khác chữ hoa/chữ thường.
- Có hoặc thiếu dấu slash cuối.
- Khác port.
- Khác path.
- Chỉ chứa domain gốc.
- Chứa identifier dưới dạng substring.
- Audience là URI khác nhưng cùng hostname.

Resource Server phải so khớp theo identifier và profile đã cấu hình. Không dùng substring hoặc so domain làm phép kiểm tra audience.

### 6.4. Kiểm thử audience dạng mảng

JWT cho phép aud là một mảng. Test cần xác định rõ policy:

- Nếu API yêu cầu đúng một audience, token có thêm recipient phải bị từ chối.
- Nếu profile cho phép nhiều audience, API phải kiểm tra chính xác audience của nó và các ràng buộc recipient khác.
- Token có audience của API A và B chỉ được chấp nhận tại cả hai nếu Authorization Server thực sự được phép phát hành token đa recipient theo policy.
- Không tự động coi mọi mảng aud là sai; cũng không chấp nhận mảng tùy ý.

Ghi nhận số lượng recipient và lý do từ chối để phát hiện cấu hình audience quá rộng.

## 7. Kiểm thử truy cập chéo tenant

Tenant isolation là ranh giới dữ liệu quan trọng. Chữ ký và audience đúng vẫn không đủ nếu token thuộc tenant khác với tài nguyên đang truy cập.

### 7.1. Token tenant X truy cập dữ liệu tenant Y

Chuẩn bị hai tenant với dữ liệu giả lập có thể phân biệt:

- T-invoice-blue có tenant_id=tenant-blue.
- T-invoice-red có tenant_id=tenant-red.
- Request context chỉ định tài nguyên thuộc tenant-red.

Giữ nguyên issuer, signing key, audience và scope giữa hai token; chỉ thay tenant claim và resource context. Gửi T-invoice-blue tới endpoint truy cập tài nguyên tenant-red. Kết quả phải bị từ chối trước khi dữ liệu tenant-red được trả về hoặc thay đổi.

### 7.2. Thử thay tenant trong request

Thực hiện các biến thể:

- Thay tenant trong URL path.
- Thay tenant trong query parameter.
- Thay tenant trong request body.
- Thay tenant trong header.
- Thay tenant trong claim JWT bằng token fixture được ký hợp lệ.
- Gửi tenant context do gateway chuyển tiếp nhưng giả mạo từ client.

Hệ thống phải xác định nguồn tenant context có thẩm quyền và đối chiếu nó với token cùng quyền của subject. Không để client tự chọn tenant chỉ bằng cách thay một tham số.

### 7.3. Tenant claim không phải quyền truy cập vô điều kiện

Claim tenant_id chỉ là một dữ liệu được issuer phát hành. Nó không tự chứng minh subject có quyền với mọi bản ghi trong tenant đó. API vẫn phải kiểm tra quan hệ subject-resource, membership, entitlement hoặc policy tương ứng.

Kiểm thử cần có:

- Token tenant-blue, tài nguyên tenant-blue, subject có quyền: cho phép.
- Token tenant-blue, tài nguyên tenant-blue, subject không có quyền trên bản ghi: từ chối authorization.
- Token tenant-blue, tài nguyên tenant-red: từ chối tenant boundary.
- Token thiếu tenant claim trong profile bắt buộc: từ chối.
- Tenant claim sai kiểu hoặc nhiều giá trị mơ hồ: từ chối.
- Tenant context từ gateway không được bảo vệ: không tin cậy.

### 7.4. Kiểm tra rò rỉ qua side effect

Khi request cross-tenant bị từ chối, xác nhận:

- Không trả nội dung bản ghi của tenant khác.
- Không tạo hoặc sửa dữ liệu.
- Không gửi event hoặc job nền.
- Không thay đổi cache theo khóa tenant sai.
- Không tiết lộ tenant có tồn tại hay không ngoài chính sách phản hồi.
- Audit ghi nhận sự kiện nhưng không lưu raw token hoặc dữ liệu nhạy cảm không cần thiết.

## 8. Kiểm thử nhầm lẫn token class hoặc mục đích

Các loại JWT có thể dùng chung issuer hoặc signing key nhưng phải có validator riêng.

| Token | Endpoint thử gửi tới | Kết quả mong đợi |
| --- | --- | --- |
| ID Token | Resource Server | Từ chối |
| Access Token | OIDC callback chờ ID Token | Từ chối |
| Client Assertion | Resource Server | Từ chối |
| JWT Bearer Assertion | API nghiệp vụ | Từ chối |
| DPoP Proof | Bearer Access Token endpoint | Từ chối |
| Refresh Token | Resource Server | Từ chối |
| Logout Token | API nghiệp vụ | Từ chối |
| JWT nội bộ | Public API không tin cậy issuer nội bộ | Từ chối |

Nếu sử dụng JWT Access Token theo RFC 9068, kiểm tra token type/profile theo RFC, bao gồm typ=at+jwt trong trường hợp profile yêu cầu. Không giả định mọi ID Token phải có một typ riêng phổ quát; dùng đầy đủ quy tắc OIDC Core cho ID Token.

### 8.1. Token đúng chữ ký nhưng sai profile

Tạo token có:

- Cùng issuer.
- Cùng signing key.
- Claims chung hợp lệ như sub, iat và exp.
- Audience của một loại token khác.
- Token type/profile khác endpoint mong đợi.

Gửi tới endpoint. Hệ thống phải từ chối do profile/audience mismatch, dù chữ ký hợp lệ.

### 8.2. Claims đặc trưng bị thiếu hoặc sai

Ví dụ:

- ID Token thiếu hoặc sai nonce khi giao dịch yêu cầu.
- Client assertion có aud không phải Token Endpoint.
- DPoP proof thiếu htm/htu/jti/iat theo profile.
- Access Token thiếu aud hoặc claim bắt buộc.
- Logout Token thiếu claim bắt buộc hoặc có nonce trong trường hợp profile cấm.

Kết quả phải theo đúng profile và phiên bản tiêu chuẩn được triển khai. Không tạo một validator một bộ claims dùng cho mọi JWT.

## 9. Kiểm thử client, actor và subject substitution

Trong OAuth, client_id, sub và actor không có cùng ý nghĩa. Một token có thể đại diện cho người dùng, client hoặc workload; hệ thống phải diễn giải theo profile.

Test các tình huống:

- Token cấp cho client A được gửi trong request yêu cầu client B.
- Client assertion của client A được dùng để xác thực client B.
- Subject của người dùng A được ghép với actor/service identity của B.
- Token delegation có actor claim không khớp actor đang gọi.
- Token user-delegated bị dùng trong luồng machine-to-machine không được phép.
- Token client-credentials bị diễn giải như danh tính người dùng cuối.

Nếu policy yêu cầu client binding, Resource Server hoặc Authorization Server phải xác minh binding đó. Không lấy client_id do request tự khai làm bằng chứng. Không mặc định sub luôn là user ID.

## 10. Kiểm thử gateway và downstream service

Gateway là ranh giới thường xác minh token đầu tiên, nhưng downstream service vẫn cần hợp đồng tin cậy rõ ràng.

### 10.1. Raw token forwarding

Nếu gateway chuyển nguyên Access Token tới downstream:

1. Gửi token dành cho Gateway tới Gateway.
2. Gateway xác minh thành công.
3. Gateway chuyển token tới Invoice API.
4. Invoice API phải tự xác minh audience của nó.

Nếu audience chỉ dành cho Gateway, Invoice API phải từ chối. Việc gateway đã xác minh token không tự mở rộng audience.

### 10.2. Identity context nội bộ

Nếu gateway tạo context nội bộ thay cho việc downstream xác minh raw token, test:

- Gateway xóa mọi identity header do client gửi trước khi tạo context.
- Downstream chỉ nhận context qua kết nối/service identity được xác thực.
- Context có integrity protection hoặc cơ chế bảo vệ tương đương.
- Context chỉ dành cho service recipient phù hợp.
- Context không thể được client phát lại trực tiếp tới downstream.
- Context hết hạn và có policy chống replay phù hợp nếu cần.
- Downstream vẫn kiểm tra quyền trên tài nguyên và tenant của nó.

Gửi các header giả như X-User-Id, X-Tenant-Id, X-Roles từ client. Kết quả phải chứng minh gateway đã loại bỏ/ghi đè chúng trước khi chuyển tiếp.

### 10.3. Token Exchange

Nếu gateway dùng OAuth Token Exchange để lấy token cho downstream:

- Subject token hợp lệ nhưng audience đích không được phép: từ chối exchange.
- Actor/client không được phép impersonate/delegate: từ chối.
- Token mới phải có audience của downstream.
- Scope mới không vượt quyền được phép từ subject token và policy.
- Token của downstream A gửi tới downstream B: B từ chối.
- Token exchange không được tạo quyền cao hơn chỉ vì gateway có quyền gọi endpoint exchange.

## 11. Kiểm thử môi trường, issuer và khóa

Tách biệt môi trường cần được kiểm tra cả ở issuer, audience và key trust:

| Test | Cấu hình token | Nơi nhận | Kết quả |
| --- | --- | --- | --- |
| Staging token tới staging API | Issuer/aud staging | Staging | Chấp nhận nếu các bước khác đạt |
| Staging token tới production API | Issuer/aud staging | Production | Từ chối |
| Production token tới staging API | Issuer/aud production | Staging | Từ chối nếu không có trust policy rõ |
| Issuer giả khai tên issuer thật | Chữ ký bằng key không tin cậy | Production | Từ chối |
| kid trùng giữa hai issuer | Key ID giống nhau nhưng key set khác | API | Chỉ resolver của issuer đã cấu hình được dùng |
| Token dùng key đã thu hồi | Chữ ký cũ nhưng key không còn được tin | API | Từ chối theo key lifecycle policy |

Không chỉ thay claim iss trong payload của token đã ký; hãy tạo fixture được ký hợp lệ bởi issuer test khác để chứng minh hệ thống không chỉ dựa vào lỗi chữ ký.

## 12. Kiểm thử OIDC transaction và session substitution

Một ID Token có thể hợp lệ nhưng thuộc một Authentication Request khác. Client cần ràng buộc response với transaction đã khởi tạo.

Kiểm thử:

- State từ tab/transaction A được ghép với response B.
- ID Token có nonce khác nonce đã lưu.
- ID Token của người dùng A được ghép vào callback của transaction B.
- Authorization Code từ giao dịch khác được đưa vào callback hiện tại.
- Code đúng nhưng PKCE verifier sai.
- c_hash hoặc at_hash sai khi response_type/endpoint yêu cầu.
- ID Token từ Token Endpoint bị áp dụng điều kiện của ID Token từ Authorization Endpoint hoặc ngược lại.
- Session đã logout hoặc bị thu hồi vẫn được dùng để hoàn tất giao dịch cũ trái policy.

Kết quả phải theo OIDC Core và OAuth flow tương ứng. Không yêu cầu at_hash hoặc c_hash trong mọi flow; test fixture phải ghi rõ response_type và endpoint phát hành ID Token.

### 12.1. Không dùng subject làm session binding

Cùng một sub có thể xuất hiện trong nhiều phiên đăng nhập hợp lệ. Nếu ứng dụng cần binding theo session, phải kiểm tra session/transaction identifier hoặc trạng thái tương ứng, không suy ra “cùng user thì cùng phiên”.

## 13. Kiểm thử scope, resource và authorization

Audience đúng mới chỉ xác nhận token được gửi tới đúng Resource Server. Tiếp theo phải kiểm tra quyền:

- Token đúng audience nhưng thiếu scope: từ chối thao tác.
- Token có scope đúng nhưng subject không sở hữu tài nguyên: từ chối.
- Token có role quản trị trong tenant A nhưng request tenant B: từ chối.
- Token có scope cho read nhưng request thực hiện write: từ chối.
- Token có resource indicator yêu cầu nhưng Authorization Server không cấp quyền: không phát hành token rộng hơn.
- Token đa audience nhưng scope/permission không hợp lệ với API hiện tại: từ chối.

Phân biệt kết quả xác thực và phân quyền:

| Tình huống | Phân loại kết quả thường gặp |
| --- | --- |
| Token sai chữ ký, issuer, audience, profile hoặc hết hạn | Authentication/token validation failure |
| Token hợp lệ nhưng thiếu scope/quyền | Authorization failure |
| Token hợp lệ nhưng tenant không khớp | Từ chối tại tenant/resource authorization boundary |
| Token hợp lệ nhưng trạng thái tài nguyên không cho phép thao tác | Business rule failure |

Với OAuth Bearer Token, phản hồi lỗi nên theo RFC 6750 và giao thức API đang dùng. Thông thường token không hợp lệ được thể hiện như invalid_token, còn thiếu quyền có thể là insufficient_scope; không làm lộ chi tiết nội bộ trong body.

## 14. Kiểm thử sender constraint và replay

Nếu token được ràng buộc với DPoP hoặc mTLS, kiểm tra token và proof phải thuộc cùng credential binding:

- Access Token có cnf.jkt nhưng DPoP proof ký bởi khóa khác: từ chối.
- DPoP proof có htm hoặc htu khác request: từ chối.
- DPoP proof cũ hoặc jti đã dùng lại: từ chối theo replay policy.
- ath không khớp Access Token: từ chối khi profile yêu cầu.
- Token certificate-bound nhưng client certificate khác: từ chối.
- Gateway terminate TLS: xác nhận service nhận chứng thư qua kênh/proxy tin cậy và không thể bị client giả mạo.
- Token sender-constrained bị gửi từ client không có private key: từ chối.

IP hoặc device fingerprint không thay thế các kiểm tra này. Nếu hệ thống chỉ dùng IP/fingerprint như risk signal, test cần bảo đảm thay đổi tín hiệu yếu không tự động biến thành proof hợp lệ hoặc vô hiệu hóa sender constraint.

## 15. Kiểm thử revocation, cache và tính nhất quán

Token có thể bị thu hồi hoặc đổi trạng thái trong khi các service đang cache metadata/validation result.

Các trường hợp cần kiểm thử:

- Token bị thu hồi ở issuer nhưng cache API vẫn active.
- Token family bị thu hồi sau refresh token reuse.
- User bị khóa hoặc tenant membership bị gỡ.
- JWKS đổi khóa giữa lúc nhiều service cache khác nhau.
- Cache key không bao gồm issuer/audience/policy và dẫn tới dùng kết quả API A cho API B.
- Một service có policy version mới, service khác vẫn dùng policy cũ.
- Revocation store hoặc introspection endpoint không khả dụng.
- Event invalidation bị mất hoặc đến trễ.

Đặt một revocation SLA rõ ràng, ví dụ thời gian tối đa để mọi Resource Server ngừng chấp nhận token đã thu hồi. Giá trị cụ thể phụ thuộc mức nhạy cảm và kiến trúc.

Không cache kết luận token hợp lệ mà bỏ qua audience, tenant, endpoint hoặc policy context. Nếu cache kết quả chữ ký riêng, bước audience/profile/authorization vẫn phải chạy cho từng ngữ cảnh nhận.

## 16. Test harness và pseudocode

Một test harness có thể tạo token fixture, gửi request tới nhiều API và xác nhận cả response lẫn side effect:

~~~text
function runCrossBoundaryTest(tokenFixture, target, requestContext, expected):
    before = snapshotProtectedState(target, requestContext)

    response = sendRequest(
        target.endpoint,
        tokenFixture.serializedToken,
        requestContext
    )

    after = snapshotProtectedState(target, requestContext)

    assert response.status matches expected.statusClass
    assert response.body does not expose protected data
    assert after has no unauthorized mutation compared with before
    assert audit contains sanitized security outcome
    assert audit does not contain raw token

function testAudienceIsolation():
    for token in allServiceTokens:
        for api in allResourceServers:
            expected = policyMatrix[token.audience][api.id]
            runCrossBoundaryTest(token, api, validRequestContext, expected)

function testTenantIsolation():
    runCrossBoundaryTest(
        token = tokenForTenantBlue,
        target = invoiceApi,
        requestContext = tenantRedResource,
        expected = DENY
    )

function testTokenPurpose():
    for token in [idToken, clientAssertion, dpopProof, refreshToken]:
        runCrossBoundaryTest(token, resourceServer, validRequestContext, DENY)
~~~

Đây là pseudocode mô tả phương pháp kiểm thử, không phải API của một công cụ cụ thể. Test harness nên lưu fixture ID và kết quả, không lưu raw bearer token trong báo cáo.

## 17. Fuzzing và mutation testing

Ngoài fixture được chuẩn bị trước, có thể tạo biến thể để kiểm tra validator có nhất quán không:

- Đổi một ký tự trong issuer hoặc audience.
- Chuyển aud giữa string và array.
- Thêm recipient ngoài policy.
- Đổi kiểu claim tenant, exp, nbf hoặc scope.
- Thêm duplicate JSON member.
- Thay typ, alg, kid hoặc crit.
- Thay đổi header/payload nhưng giữ signature cũ.
- Tạo nested JWT không đúng độ sâu hoặc cấu trúc.
- Thay nonce, jti, htm, htu hoặc ath.
- Hoán đổi thứ tự các request giữa tenant/service.

Mutation test nên giữ nguyên chữ ký hợp lệ khi muốn kiểm tra policy layer. Ví dụ, để kiểm tra audience mismatch, tạo một token mới được ký hợp lệ với audience sai; không chỉ sửa payload làm chữ ký hỏng. Nếu chỉ sửa byte payload, test mới chứng minh chữ ký phát hiện sửa đổi, chưa chứng minh audience validation hoạt động.

Fuzzing parser và serialization nên chạy trong môi trường cô lập, có giới hạn CPU/bộ nhớ và không dùng dữ liệu production. Kiểm tra không crash, không treo, không fetch URL ngoài trust configuration và không tạo validated context một phần.

## 18. Quan sát, audit và bằng chứng kiểm thử

Khi test thất bại, cần đủ bằng chứng để biết ranh giới nào bị vi phạm mà không làm lộ credential.

Nên ghi:

- Test case ID và fixture ID.
- API/endpoint nhận.
- Policy ID/version.
- Loại lỗi tổng quát: issuer mismatch, audience mismatch, tenant mismatch, token type mismatch, scope denied hoặc proof failure.
- Correlation/request ID.
- Kết quả authorization và side-effect assertion.
- Thời gian xử lý và trạng thái cache nếu liên quan.

Không ghi:

- Raw JWT, refresh token hoặc Authorization header.
- Private key, shared secret hoặc toàn bộ JWK nhạy cảm.
- Payload claims nhạy cảm không cần cho audit.
- Dữ liệu cá nhân thật trong test report.

Test report nên lưu token fixture ID, hash/fingerprint test-only nếu cần liên kết, và cấu hình môi trường đã dùng. Không dùng hash ổn định của production token làm định danh audit nếu nó tạo khả năng theo dõi không cần thiết.

## 19. Ma trận kiểm thử tổng hợp

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Cross-service | Token API A gửi tới API B | Audience mismatch, từ chối |
| Audience exact match | Khác case/path/port/slash | Từ chối nếu không đúng identifier |
| Multi-audience | Token có nhiều recipient | Xử lý đúng single/multi-audience policy |
| Cross-tenant | Token tenant X truy cập dữ liệu tenant Y | Từ chối, không rò rỉ hoặc side effect |
| Tenant tampering | Thay tenant trong path/header/body | Không vượt tenant authorization |
| Token class | ID Token gửi tới Resource Server | Từ chối |
| Token class | Access Token gửi tới OIDC callback | Từ chối |
| Assertion | Client assertion gửi tới API | Từ chối |
| DPoP | Proof gửi như bearer token | Từ chối |
| Refresh token | Refresh token gửi tới API | Từ chối |
| Cross-client | Token/assertion của client A dùng cho B | Từ chối nếu binding yêu cầu |
| Cross-environment | Staging token gửi tới production | Từ chối |
| Cross-session | ID Token/Code từ transaction khác | Từ chối do state/nonce/PKCE/hash mismatch |
| Gateway | Header identity giả từ client | Bị loại bỏ/ghi đè |
| Downstream | Raw token gateway gửi service không đúng aud | Service từ chối |
| Token exchange | Audience đích không được phép | Authorization Server từ chối |
| Scope | Audience đúng nhưng thiếu scope | Authorization từ chối |
| Ownership | Scope đúng nhưng không sở hữu tài nguyên | Authorization từ chối |
| Sender constraint | DPoP key/certificate không khớp | Từ chối |
| Replay | Proof/jti đã dùng lại | Từ chối theo policy |
| Revocation | Token đã thu hồi nhưng cache cũ | Chặn trong SLA đã định |
| Cache isolation | Cache API A được dùng cho API B | Không tái sử dụng kết luận sai |
| Failure mode | Revocation store bắt buộc không khả dụng | Theo failure policy, không bypass |
| Side effects | Request cross-boundary bị từ chối | Không tạo/sửa dữ liệu hoặc phát event |
| Audit | Test thất bại | Có sự kiện đã sanitize, không có raw token |

## 20. Checklist trước khi phát hành

1. [ ] Có sơ đồ trust boundary và danh sách endpoint/token profile.
2. [ ] Có fixture được ký hợp lệ cho từng service, tenant, client và môi trường.
3. [ ] Test cross-service giữ nguyên issuer/key để chứng minh audience validation.
4. [ ] Test exact audience matching và chính sách multi-audience.
5. [ ] Test tenant X truy cập tài nguyên tenant Y, bao gồm path/header/body tampering.
6. [ ] Xác nhận tenant context đến từ nguồn tin cậy và subject có quyền trên tài nguyên.
7. [ ] Test ID Token, Access Token, client assertion, DPoP proof, refresh token và JWT nội bộ tại sai endpoint.
8. [ ] Test client/actor/subject substitution.
9. [ ] Test staging/production issuer, audience, key và JWKS separation.
10. [ ] Test state, nonce, PKCE, at_hash/c_hash theo đúng flow và endpoint.
11. [ ] Test gateway header spoofing, raw token forwarding và identity context integrity.
12. [ ] Test token exchange audience/scope restriction.
13. [ ] Test scope, ownership, tenant và business authorization riêng biệt.
14. [ ] Test sender constraint và replay nếu được sử dụng.
15. [ ] Test revocation, JWKS rotation, cache isolation và policy version.
16. [ ] Xác nhận request bị từ chối không gây side effect hoặc rò rỉ dữ liệu.
17. [ ] Log/audit có đủ bằng chứng nhưng không chứa raw token hoặc secret.
18. [ ] Có negative tests, mutation tests, integration tests và regression suite.
19. [ ] Chạy trong môi trường kiểm thử với dữ liệu và khóa giả lập; không dùng credential production.
20. [ ] Lưu lại policy version, fixture ID, kết quả và các ngoại lệ được phê duyệt.

## 21. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** claims iss, sub, aud, exp, nbf, iat và quy tắc recipient.
- **RFC 8725 — JSON Web Token Best Current Practices:** audience validation, explicit typing, mutually exclusive validation rules và phòng token confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile Access Token dạng JWT và validation tại Resource Server.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi bearer token và phản hồi lỗi invalid_token/insufficient_scope.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** yêu cầu token cho resource cụ thể.
- **RFC 8693 — OAuth 2.0 Token Exchange:** đổi token cho subject/actor/resource đích.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession và ràng buộc Access Token.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc token với chứng thư client.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE):** ràng buộc Authorization Code với client verifier.
- **OpenID Connect Core 1.0:** xác minh ID Token, nonce, audience và flow binding.

**Nguyên tắc ghi nhớ:** Để kiểm thử token bị dùng chéo, hãy tạo token có chữ ký hợp lệ nhưng cố ý sai audience, tenant, token profile, client, session hoặc transaction. Gửi chúng qua đúng các đường đi thực tế từ client, gateway tới downstream. Một hệ thống đạt yêu cầu khi mỗi ranh giới tự xác minh đúng ngữ cảnh, từ chối trước khi có side effect và không làm lộ dữ liệu của dịch vụ hoặc tenant khác.
