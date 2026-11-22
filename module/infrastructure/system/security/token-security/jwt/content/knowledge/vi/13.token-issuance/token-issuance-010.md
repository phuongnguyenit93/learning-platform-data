# Phân biệt tái phát hành, làm mới và đổi token

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vì sao cần phân biệt ba thao tác?

Trong vòng đời xác thực và ủy quyền, một hệ thống có thể tạo JWT mới vì nhiều lý do: cấp lại sau khi xác thực, làm mới access token bằng refresh token hoặc đổi một token hiện có sang token khác dành cho một resource server hay ngữ cảnh ủy quyền khác. Cả ba thao tác đều có thể trả về một token mới, nhưng **bằng chứng đầu vào, mục đích và giới hạn quyền hoàn toàn khác nhau**.

Ba khái niệm trong bài:

- **Tái phát hành (re-issuance):** cách gọi khái quát cho việc issuer phát hành một token mới dựa trên một quyết định xác thực/ủy quyền hợp lệ. Đây không phải tên một OAuth grant chuẩn duy nhất; hệ thống phải định nghĩa rõ điều kiện tái phát hành của mình.
- **Làm mới (refresh):** sử dụng refresh token theo refresh token grant để yêu cầu access token mới trong phạm vi grant/phiên hiện có, theo quy tắc của giao thức.
- **Đổi token (token exchange):** trình một token đầu vào (và có thể một actor token) để nhận token đầu ra có loại, audience, subject/actor hoặc phạm vi quyền phù hợp với một ngữ cảnh khác, theo giao thức như RFC 8693.

Điểm dễ nhầm là: refresh và exchange đều nhận một token làm đầu vào; re-issuance và refresh đều có thể tạo access token mới cho cùng người dùng. Cần chọn luồng dựa trên **mục đích và quan hệ ủy quyền**, không chỉ dựa trên việc “cần một JWT mới”.

## 2. So sánh nhanh

| Tiêu chí | Tái phát hành | Làm mới (refresh) | Đổi token (exchange) |
| --- | --- | --- | --- |
| Ý nghĩa | Issuer phát hành token mới sau khi xác minh điều kiện theo chính sách | Dùng refresh token để tiếp tục grant/phiên hiện có | Đổi token đầu vào thành token phù hợp mục đích hoặc ngữ cảnh khác |
| Giao thức | Không có một grant OAuth chung mang tên re-issuance; phụ thuộc thiết kế | OAuth 2.0 refresh token grant (`grant_type=refresh_token`) | OAuth 2.0 Token Exchange (RFC 8693) hoặc giao thức tương đương |
| Bằng chứng đầu vào | Có thể là xác thực mới, grant hiện có hoặc quy trình nội bộ được định nghĩa | Refresh token hợp lệ gắn với client/grant | Subject token và tùy chọn actor token cùng quyền trao đổi |
| Mục đích | Cấp một token mới sau khi điều kiện phát hành được xác minh | Thay access token sắp hết hạn/hết hạn | Tạo token cho resource, audience, subject/actor hoặc token type khác |
| Quyền | Tính lại theo chính sách và bằng chứng hiện tại | Không tự mở rộng grant; thường giữ hoặc giảm quyền theo chính sách | Token mới bị giới hạn bởi quyền của token đầu vào, actor, delegation và policy |
| Ngữ cảnh xác thực | Có thể yêu cầu xác thực lại; không được giả vờ xác thực mới nếu chỉ đổi chữ ký | Không mặc nhiên xác thực lại người dùng | Không mặc nhiên xác thực lại; phụ thuộc token đầu vào và yêu cầu policy |
| Thu hồi | Token cũ không tự mất hiệu lực khi token mới được cấp | Rotation/reuse detection có thể thu hồi refresh token family; access token cũ cần cơ chế riêng | Token đầu vào không tự bị thu hồi chỉ vì đã exchange |
| Ví dụ | Người dùng xác thực lại và nhận token mới | Client dùng refresh token để nhận access token mới | Backend đổi token dành cho API A thành token giới hạn cho API B |

Bảng là mô hình khái niệm. Tái phát hành có thể được hiện thực hóa bằng một grant hoặc API riêng; cần tài liệu hóa chính xác để không gọi nhầm nó là refresh hay token exchange.

## 3. Tái phát hành token (re-issuance)

### 3.1. Khái niệm

Tái phát hành là hành động issuer tạo một JWT mới sau khi kiểm tra lại các điều kiện phát hành. Tùy chính sách, việc này có thể xảy ra khi:

- người dùng vừa hoàn tất xác thực hoặc xác thực tăng cường;
- phiên/grant còn hiệu lực và có một quy trình nội bộ cho phép cấp lại token;
- claim hoặc audience cần thay đổi sau khi quyền đã được đánh giá lại;
- token cũ cần được thay bằng token mới theo quy trình vận hành hoặc bảo mật;
- client/workload được xác thực lại và xin token mới.

Tái phát hành **không phải lý do để bỏ qua authentication hoặc authorization**. Issuer cần biết bằng chứng nào cho phép phát hành token mới và bằng chứng đó còn hiệu lực đến đâu.

### 3.2. Khi nào cần xác thực lại?

Nếu token mới được cấp dựa trên phiên đã xác thực, issuer phải đánh giá tuổi và mức bảo đảm của lần xác thực ban đầu. Một lần phát hành JWT mới làm `iat` mới hơn nhưng **không có nghĩa người dùng vừa nhập lại thông tin xác thực**.

Khi thao tác yêu cầu xác thực mới, issuer cần thực hiện reauthentication hoặc step-up phù hợp. Những thông tin như `auth_time`, `acr` và `amr` phải phản ánh đúng lần xác thực và phương thức thực sự đã dùng theo profile. Không cập nhật `auth_time` thành thời điểm phát hành chỉ để làm phiên có vẻ mới.

### 3.3. Tái phát hành có thể giữ hay thay đổi quyền?

Issuer phải tính lại quyền dựa trên subject, client, audience, grant, tenant và policy hiện tại. Tái phát hành không phải thao tác sao chép payload cũ rồi đổi `iat`/`exp`.

- Nếu quyền đã bị thu hồi, token mới không được chứa quyền đó.
- Nếu audience thay đổi, phải xác minh client/grant có quyền với resource mới.
- Nếu subject hoặc actor thay đổi, cần bằng chứng ủy quyền phù hợp.
- Nếu token profile thay đổi, cần validate theo schema của profile mới.
- Nếu không còn đủ bằng chứng hoặc trạng thái phiên không hợp lệ, phải từ chối phát hành.

### 3.4. Ví dụ

Người dùng đăng nhập vào một ứng dụng quản lý đơn hàng. Access token sắp hết hạn nhưng hệ thống không sử dụng refresh token; người dùng phải xác thực lại theo chính sách. Sau khi mật khẩu và MFA được xác minh, issuer tạo JWT mới với `iat` và `exp` mới, kiểm tra trạng thái tài khoản, quyền và audience trước khi ký.

Đây là tái phát hành sau xác thực mới. Nếu chỉ lấy JWT cũ, đổi thời gian và ký lại mà không kiểm tra phiên/grant hoặc xác thực lại khi cần, hệ thống đã biến việc tái phát hành thành một đường gia hạn quyền không được kiểm soát.

## 4. Làm mới access token bằng refresh token

### 4.1. Mục đích của refresh

Trong OAuth 2.0, client có thể nhận refresh token cùng access token. Khi access token hết hạn hoặc cần thay thế, client gửi refresh token tới authorization server bằng refresh token grant để xin access token mới.

Refresh token thường có vòng đời dài hơn access token và có giá trị bảo mật cao. Nó cho phép tiếp tục grant mà không yêu cầu người dùng nhập lại thông tin xác thực ở mỗi lần refresh. Tuy nhiên, **refresh token không phải bằng chứng rằng mọi quyền cũ vẫn còn hợp lệ mãi mãi**.

Refresh token có thể là chuỗi opaque được quản lý trạng thái phía máy chủ; nó không bắt buộc phải là JWT. Nếu refresh token là JWT, issuer vẫn cần kiểm tra trạng thái grant, thu hồi và rotation theo chính sách thay vì chỉ xác minh chữ ký và `exp`.

### 4.2. Các kiểm tra bắt buộc trước khi refresh

Authorization server cần xác minh tối thiểu:

1. Refresh token có đúng định dạng, chữ ký hoặc tham chiếu trạng thái hợp lệ?
2. Token chưa hết hạn, chưa bị thu hồi và chưa bị đánh dấu đã sử dụng trái quy tắc rotation?
3. Token thuộc grant/phiên nào; grant còn hoạt động không?
4. Client hiện tại có đúng client đã được gắn với refresh token không? Với confidential client, xác thực client theo yêu cầu giao thức.
5. Subject, tenant, audience và quyền của grant còn hợp lệ không?
6. Có yêu cầu sender-constraining, client binding hoặc bằng chứng sở hữu nào phải xác minh không?
7. Phiên còn trong idle timeout và absolute timeout không?
8. Có tín hiệu rủi ro hoặc yêu cầu xác thực lại/step-up không?

Nếu bất kỳ điều kiện bắt buộc nào không đạt, không cấp access token mới.

### 4.3. Scope khi refresh

Theo OAuth 2.0, client có thể gửi scope trong refresh request nếu muốn yêu cầu một phạm vi khác, nhưng scope được cấp không được vượt quá scope đã được resource owner cấp ban đầu. Nếu client bỏ qua scope, authorization server xử lý theo quy tắc của giao thức và grant hiện có.

Vì vậy:

- Refresh không tự động mở rộng quyền.
- Có thể downscope nếu policy cho phép.
- Muốn tăng quyền phải thực hiện một quy trình authorization/consent mới phù hợp, không dùng refresh token như đường tắt.
- Audience/resource mới cũng phải được đánh giá theo grant và chính sách; không mặc định refresh token có quyền tới mọi API.

### 4.4. Rotation và reuse detection

Một thực hành quan trọng là **refresh token rotation**: mỗi lần refresh thành công, authorization server cấp refresh token mới và vô hiệu hóa refresh token cũ. Nếu token cũ bị sử dụng lại sau khi đã rotation, đó có thể là dấu hiệu token bị sao chép hoặc đánh cắp.

Một mô hình family:

~~~text
Refresh token family:
RT-1 --refresh--> RT-2 --refresh--> RT-3
  |                 |                 |
revoked           revoked           active
~~~

Khi phát hiện RT-1 hoặc RT-2 bị dùng lại trái quy tắc, authorization server có thể thu hồi toàn bộ family/grant liên quan và yêu cầu xác thực lại theo chính sách.

Cần xử lý đồng thời và retry cẩn thận. Nếu hai request refresh cùng dùng một token hợp lệ gần như đồng thời, hệ thống không được vô tình tạo hai nhánh token family hoặc báo reuse sai cho một request hợp lệ. Rotation nên có thao tác trạng thái nguyên tử, idempotency/coordination phù hợp và sự kiện audit.

### 4.5. Ví dụ refresh

Client có access token với `aud` là Orders API và refresh token gắn với grant đọc đơn hàng. Khi access token hết hạn, client gửi refresh request. Authorization server xác minh refresh token, client, grant, trạng thái subject và scope hiện tại. Nếu hợp lệ, issuer phát hành access token mới cho Orders API với quyền còn hiệu lực, đồng thời rotation refresh token nếu chính sách áp dụng.

Nếu người dùng đã bị gỡ khỏi tenant hoặc grant đã bị thu hồi, refresh phải bị từ chối dù refresh token vẫn còn trong kho hoặc chữ ký JWT vẫn hợp lệ.

## 5. Đổi token (OAuth 2.0 Token Exchange)

### 5.1. Mục đích

Token exchange cho phép một client gửi token đầu vào để nhận token khác phù hợp với một ngữ cảnh sử dụng mới. RFC 8693 định nghĩa OAuth 2.0 Token Exchange, với các tham số quan trọng như `subject_token`, `subject_token_type`, `actor_token`, `actor_token_type`, `requested_token_type`, `audience`, `resource` và `scope`.

Các trường hợp sử dụng:

- backend nhận token dành cho một API và đổi sang token dành cho API khác;
- service hành động thay mặt người dùng với quyền delegation giới hạn;
- hệ thống đổi token từ một miền tin cậy sang miền khác sau khi xác minh federation;
- tạo token ngắn hạn cho một workload hoặc resource cụ thể;
- chuyển đổi token giữa các loại/format được các hệ thống tin cậy hỗ trợ.

Token exchange không phải cách “làm mới” một token hết hạn. Token đầu vào phải hợp lệ theo điều kiện exchange; authorization server cần xác minh và quyết định có cho phép chuyển đổi hay không.

### 5.2. Subject token và actor token

- **Subject token:** token đại diện cho subject hoặc quyền của subject mà token mới sẽ kế thừa/giới hạn.
- **Actor token (tùy chọn):** token đại diện cho actor đang thực hiện hành động thay mặt subject.

Ví dụ: người dùng `user-84` cho phép dashboard đọc đơn hàng. Backend service `order-worker` gọi token exchange với subject token của người dùng và actor token của workload. Authorization server phải xác minh cả hai, kiểm tra quan hệ delegation và chỉ cấp token mới với quyền mà subject, actor, grant và resource policy cùng cho phép.

Không được coi actor token là quyền để nâng quyền của subject. Delegation phải có chuỗi tin cậy và giới hạn rõ ràng; một actor không được tự nhận danh tính hoặc quyền của người dùng chỉ bằng cách gửi subject token.

### 5.3. Audience, resource và scope của token đầu ra

Token exchange có thể yêu cầu audience/resource khác với token đầu vào. Authorization server phải xác minh:

- client được phép yêu cầu token cho resource đó;
- token đầu vào có thể được dùng trong luồng exchange;
- subject và actor có quyền trong resource/tenant đích;
- scope đầu ra không vượt quá quyền được ủy quyền;
- token type đầu ra được hỗ trợ bởi issuer và recipient;
- thời hạn đầu ra phù hợp chính sách và không làm tăng thời gian quyền tồn tại ngoài mức cho phép.

Token đầu ra thường có audience cụ thể hơn hoặc scope hẹp hơn token đầu vào. **Exchange không phải cơ chế nâng quyền**. Nếu token đầu vào chỉ có quyền đọc, token đầu ra không thể tự có quyền ghi trừ khi có grant/ủy quyền bổ sung hợp lệ.

### 5.4. Impersonation và delegation

RFC 8693 phân biệt các mô hình subject và actor. Trong impersonation, token mới đại diện cho subject theo ngữ nghĩa của issuer và actor có thể không được biểu diễn giống delegation. Trong delegation, token thể hiện một actor đang hành động thay mặt subject; claim `act` có thể được dùng theo quy tắc của RFC 8693.

Không được tự suy ra impersonation/delegation chỉ từ việc có hai token đầu vào. Phải định nghĩa rõ:

- ai là subject;
- ai là actor;
- actor được ủy quyền bởi ai;
- phạm vi và audience được phép;
- chuỗi delegation có giới hạn độ sâu và thời gian không;
- bên nhận hiểu claim actor theo cùng một profile không.

### 5.5. Ví dụ token exchange

Một frontend nhận access token cho API Gateway. Gateway cần gọi Inventory API thay mặt người dùng, nhưng token hiện tại không dành cho Inventory API. Gateway dùng token exchange:

~~~text
subject_token = user_access_token
subject_token_type = access_token_type
actor_token = gateway_workload_token
actor_token_type = access_token_type
requested_token_type = access_token_type
resource = inventory_api
scope = inventory:read
~~~

Authorization server xác minh token người dùng, token workload, client, grant và policy. Nếu hợp lệ, nó phát hành token mới:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/inventory",
  "client_id": "gateway",
  "scope": "inventory:read",
  "iat": 1900000000,
  "exp": 1900000300
}
~~~

Các giá trị chỉ minh họa. Token thực tế có thể biểu diễn actor/delegation theo profile phù hợp; không nên bỏ mất thông tin actor nếu resource server cần kiểm tra ai đang hành động thay mặt subject.

## 6. Những điểm khác nhau về quyền và ngữ cảnh bảo mật

| Vấn đề | Tái phát hành | Refresh | Token exchange |
| --- | --- | --- | --- |
| Bằng chứng danh tính | Có thể yêu cầu xác thực mới hoặc phiên/grant đã xác minh | Refresh token và grant hiện có | Subject token, actor token nếu có, cùng quyền exchange |
| Mục tiêu | Cấp token mới theo chính sách phát hành | Tiếp tục grant bằng access token mới | Chuyển đổi token cho resource/ngữ cảnh/loại token khác |
| Reauthentication | Có thể bắt buộc tùy authentication age/risk | Không tự diễn ra; có thể được policy yêu cầu | Không tự diễn ra; token đầu vào không thay thế yêu cầu step-up |
| Scope | Tính lại từ policy và bằng chứng hiện tại | Không vượt quá grant ban đầu; có thể downscope | Bị giới hạn bởi subject, actor, delegation, resource và policy |
| Audience | Chọn theo mục đích phát hành | Theo grant/resource được phép | Có thể khác token đầu vào nhưng phải được cho phép |
| Subject | Theo principal đã xác thực | Thường giữ subject của grant | Theo subject token và quy tắc exchange |
| Actor | Theo mô hình client/actor của luồng | Thường là client sử dụng refresh token | Có thể biểu diễn rõ actor/delegation |
| Thu hồi | Token mới không tự thu hồi token cũ | Có thể rotation/revoke refresh family; access token cũ cần kiểm soát riêng | Token đầu vào không tự thu hồi; token đầu ra có vòng đời riêng |

## 7. Lựa chọn luồng phù hợp

Dùng các câu hỏi sau để chọn đúng thao tác:

- **Người dùng vừa xác thực lại hoặc issuer cần cấp token sau một quyết định xác thực mới?** Dùng quy trình tái phát hành theo chính sách, bảo đảm claim xác thực phản ánh đúng lần xác thực.
- **Client chỉ cần access token mới trong grant/phiên đang hoạt động và có refresh token hợp lệ?** Dùng refresh token grant.
- **Một service cần token cho resource khác hoặc cần hành động thay mặt subject theo delegation?** Xem xét token exchange.
- **Token đầu vào hết hạn hoặc bị thu hồi?** Không dùng exchange để lách điều kiện; phải có bằng chứng/grant hợp lệ khác.
- **Cần tăng quyền hoặc thay đổi consent?** Thực hiện authorization/consent mới phù hợp; không gọi refresh hay exchange để tự nâng quyền.
- **Cần xác thực mới cho thao tác nhạy cảm?** Yêu cầu reauthentication/step-up, không chỉ phát hành JWT mới.

## 8. Quy trình quyết định và phát hành

~~~mermaid
flowchart TD
    A["Client cần token"] --> B{"Mục đích yêu cầu?"}
    B -- "Sau xác thực mới / policy" --> C["Tái phát hành"]
    B -- "Tiếp tục grant hiện có" --> D["Refresh token grant"]
    B -- "Đổi resource / subject-actor context" --> E["Token exchange"]
    C --> F["Xác minh authentication/grant và risk"]
    D --> G["Xác minh refresh token, client, family, grant"]
    E --> H["Xác minh subject token, actor token và quyền exchange"]
    F --> I["Tính subject, audience, scope và thời hạn"]
    G --> I
    H --> I
    I --> J{"Policy cho phép token đầu ra?"}
    J -- "Không" --> X["Từ chối và ghi sự kiện"]
    J -- "Có" --> K["Validate profile/schema và ký token mới"]
    K --> L["Quản lý rotation/revocation nếu áp dụng"]
    L --> M["Audit và trả token an toàn"]
~~~

Mỗi nhánh cần có schema, token type và chính sách riêng. Không dùng một handler chung chỉ dựa trên việc request có trường token đầu vào.

## 9. Các ràng buộc phải giữ khi tạo token mới

Dù là tái phát hành, refresh hay exchange, issuer cần:

- chọn `iss` từ cấu hình tin cậy;
- chọn `aud`/resource theo client, grant và mục tiêu hợp lệ;
- đặt `sub` đúng principal; nếu có actor, biểu diễn theo profile;
- tính scope/permission theo nguyên tắc least privilege;
- đặt `iat`/`exp` và thời hạn theo loại token, risk và giới hạn grant;
- sinh `jti` mới cho mỗi token mới nếu profile sử dụng claim này;
- chọn khóa ký và `kid` theo quy tắc quản lý khóa;
- validate schema và protected header trước khi ký;
- không sao chép claim xác thực cũ như thể vừa xác thực lại;
- không đưa refresh token hoặc token đầu vào vào payload/log;
- xác định cách xử lý token cũ, grant cũ và trạng thái thu hồi.

**Token mới phải là một quyết định phát hành mới**, dù nó kế thừa một phần ngữ cảnh trước đó. Không sao chép toàn bộ payload cũ rồi chỉ đổi thời gian.

## 10. Thu hồi và trạng thái của token cũ

Cấp token mới không làm token cũ tự hết hiệu lực. Với JWT tự chứa, resource server có thể tiếp tục chấp nhận token cũ đến `exp` nếu không có cơ chế trạng thái bổ sung.

Tùy luồng:

- **Re-issuance:** nếu token cũ cần bị vô hiệu hóa, dùng cơ chế revoke theo grant/session, denylist theo `jti`, phiên bản grant hoặc introspection.
- **Refresh rotation:** refresh token cũ bị đánh dấu đã dùng/vô hiệu hóa; access token cũ có thể vẫn còn hiệu lực đến `exp` trừ khi có cơ chế thu hồi riêng.
- **Token exchange:** subject token vẫn tồn tại theo vòng đời của nó; token đầu ra có audience, quyền và thời hạn riêng. Exchange không tự revoke subject token.

Nếu refresh token bị phát hiện reuse, có thể thu hồi token family hoặc grant theo chính sách. Nếu khóa ký bị xâm phạm, cần quy trình key compromise; chỉ revoke một vài token ID không đủ để ngăn kẻ tấn công tạo JWT mới bằng khóa bị lộ.

## 11. Xử lý lỗi, retry và concurrency

Các thao tác token thường có thể được client retry do timeout hoặc lỗi mạng. Nếu không có thiết kế phù hợp, retry có thể tạo nhiều token hoặc làm rotation/reuse detection hoạt động sai.

- Với tái phát hành, xác định idempotency/correlation theo giao dịch nếu nghiệp vụ yêu cầu tránh tạo nhiều token cho một hành động.
- Với refresh rotation, xử lý đồng thời cùng refresh token bằng thao tác nguyên tử và quy tắc retry rõ ràng.
- Với token exchange, không để token đầu vào bị tiêu thụ nhiều lần nếu profile yêu cầu one-time assertion; nếu token đầu vào là bearer access token thông thường, exchange không tự biến nó thành one-time.
- Khi response bị mất sau khi token đã được tạo, thiết kế cách client retry hoặc lấy lại kết quả mà không làm lộ token.
- Không log token để hỗ trợ retry; dùng request ID, grant ID hoặc idempotency key theo đúng mục đích.
- Lỗi xác minh, grant hết hạn, scope không được phép hoặc audience sai phải dẫn tới từ chối; không fallback sang một luồng yếu hơn.

## 12. Mã giả phân biệt ba luồng

~~~text
function issueByReauthentication(request):
    authentication = verifyFreshAuthentication(request.credentials)
    require authentication.valid
    require authentication.assuranceMeetsPolicy

    context = buildVerifiedContext(authentication)
    return issueNewTokenFromCurrentPolicy(context)


function refreshAccessToken(request):
    client = authenticateRefreshClient(request.client)
    refreshGrant = refreshStore.verifyAndLock(request.refreshToken, client)
    require refreshGrant.active
    require refreshGrant.notExpired
    require refreshGrant.notRevoked
    require refreshGrant.notReused

    currentPermissions = authorizationPolicy.recalculate(refreshGrant)
    scopes = limitToExistingGrant(request.requestedScope, currentPermissions)
    require scopes.allowed

    accessToken = issueNewAccessToken(refreshGrant.subject, client, scopes)
    rotateRefreshTokenAtomically(refreshGrant)
    return accessToken


function exchangeToken(request):
    subject = verifySubjectToken(request.subjectToken)
    actor = verifyActorTokenIfPresent(request.actorToken)
    require tokenExchangePolicy.permits(subject, actor, request.client)

    audience = resourcePolicy.resolveAllowedResource(request.resource)
    scopes = delegationPolicy.authorize(
        subject, actor, audience, request.requestedScope
    )
    require scopes.allowed

    return issueTokenForExchange(subject, actor, audience, scopes)
~~~

Mã giả chỉ minh họa ranh giới quyết định. Thực tế cần xác minh token type, issuer, audience, thời gian, grant, client authentication, sender constraint, rotation state, schema và khóa ký theo từng profile.

## 13. Các tình huống kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tái phát hành khi không có bằng chứng xác thực/grant hợp lệ | Từ chối |
| Tái phát hành sau step-up | Token phản ánh đúng `auth_time`/`acr`/`amr` theo profile |
| Chỉ refresh bằng access token, không có refresh grant | Từ chối |
| Refresh token hết hạn hoặc bị thu hồi | Từ chối |
| Refresh token thuộc client khác | Từ chối theo binding và giao thức |
| Refresh yêu cầu scope vượt grant | Downscope hoặc từ chối; không nâng quyền |
| Refresh token cũ bị dùng lại sau rotation | Phát hiện reuse và xử lý family/grant |
| Token exchange với subject token sai audience/issuer | Từ chối |
| Actor token không được phép delegation | Từ chối |
| Exchange yêu cầu resource không được cấp | Từ chối |
| Exchange tạo scope rộng hơn quyền subject/actor | Từ chối |
| Token đầu vào hết hạn | Từ chối exchange nếu profile yêu cầu token đầu vào còn hiệu lực |
| Token mới được cấp nhưng token cũ chưa bị revoke | Resource server xử lý theo TTL/trạng thái; không giả định token cũ tự mất hiệu lực |
| Response bị timeout sau refresh rotation | Retry theo cơ chế idempotent/coordination; không tạo nhánh family sai |
| Token ID mới bị tái sử dụng | Mỗi lần phát hành mới có `jti` riêng nếu profile yêu cầu |

## 14. Những sai lầm cần tránh

- Gọi mọi thao tác tạo JWT mới là refresh.
- Dùng access token hết hạn làm bằng chứng refresh.
- Coi refresh token là quyền đăng nhập vô hạn hoặc quyền mở rộng scope.
- Dùng token exchange để lách xác thực lại hoặc grant đã thu hồi.
- Không xác minh actor trong luồng delegation.
- Cấp token đầu ra cho audience tùy ý do client gửi.
- Sao chép payload cũ mà không tính lại quyền và trạng thái.
- Cập nhật `iat` mới rồi giả mạo `auth_time` như thể người dùng vừa xác thực.
- Cho rằng rotation refresh token tự thu hồi access token đã cấp.
- Cho rằng exchange tự tiêu thụ hoặc thu hồi subject token.
- Không xử lý concurrency, retry và mất response.
- Không ghi audit cho refresh reuse, exchange bị từ chối hoặc thay đổi quyền.

## 15. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): refresh token grant, scope và vòng đời access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation và phát hiện reuse.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token, requested token type, audience và delegation.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim và cấu trúc JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token dạng JWT.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): xác thực, ID token, authentication time và assurance claims.

**Ghi nhớ:** Tái phát hành là quyết định phát hành token mới theo chính sách xác thực/ủy quyền; refresh tiếp tục một grant hiện có bằng refresh token; token exchange chuyển token sang ngữ cảnh hoặc recipient khác theo quan hệ subject/actor được phép. Mỗi luồng có bằng chứng, giới hạn quyền, trạng thái và quy tắc thu hồi riêng. Không dùng luồng này để lách điều kiện của luồng kia.

