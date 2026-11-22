# Token truy cập ngắn hạn và cơ chế làm mới riêng

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Vòng đời token. Bài viết áp dụng cho hệ thống xác thực và ủy quyền nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vì sao nên tách access token và refresh token?

Access token là credential mà client gửi tới resource server để truy cập API hoặc tài nguyên được cấp phép. Refresh token là credential mà client gửi tới authorization server để xin access token mới khi access token hiện tại sắp hết hạn hoặc đã hết hạn.

Hai token phục vụ hai vai trò khác nhau:

- **Access token:** được sử dụng thường xuyên ở resource server, nên cần thời hạn ngắn, audience cụ thể và quyền tối thiểu.
- **Refresh token:** được sử dụng ít hơn, chỉ tại authorization server, nên có thể có vòng đời dài hơn nhưng phải được bảo vệ chặt chẽ, ràng buộc với client/grant và có khả năng thu hồi.

Mô hình này cho phép hệ thống giảm thời gian sử dụng của access token nếu token bị đánh cắp, đồng thời không buộc người dùng xác thực lại ở mỗi lần access token hết hạn. Tuy nhiên, refresh token trở thành credential có giá trị cao: nếu bị đánh cắp, kẻ tấn công có thể liên tục xin access token mới cho đến khi refresh token hoặc grant bị thu hồi/hết hạn.

Vì vậy, tách hai token chỉ có ý nghĩa khi hệ thống quản lý đúng vòng đời của cả hai. Phát hành access token ngắn hạn nhưng để refresh token không hết hạn, không rotation, không ràng buộc client và không có cơ chế thu hồi sẽ tạo ra một điểm yếu mới.

## 2. Phân biệt access token và refresh token

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Truy cập resource/API | Xin access token mới |
| Nơi gửi | Resource server tương ứng | Authorization server/token endpoint |
| Tần suất sử dụng | Thường xuyên theo request API | Ít hơn, khi cần làm mới |
| Thời hạn | Thường ngắn | Thường dài hơn nhưng có giới hạn |
| Audience | Resource server hoặc nhóm resource được phép | Authorization server theo giao thức |
| Quyền | Scope/permission cần cho API | Đại diện cho grant có thể cấp access token trong phạm vi được phép |
| Định dạng | Có thể là JWT hoặc opaque token | Thường nên là opaque random credential; không bắt buộc là JWT |
| Trạng thái | JWT có thể xác minh cục bộ; thu hồi tức thời cần cơ chế bổ sung | Thường cần trạng thái phía máy chủ để rotation, reuse detection và revoke |
| Khi bị lộ | Kẻ giữ token có thể dùng đến khi hết hạn hoặc bị chặn | Kẻ giữ token có thể xin token mới, nên tác động có thể kéo dài |
| Nơi lưu | Theo kiến trúc client và mức rủi ro | Kho lưu trữ được bảo vệ nghiêm ngặt hơn |

Không gửi refresh token tới resource server. Resource server chỉ cần access token dành cho audience của nó. Nếu một API chấp nhận refresh token như access token, ranh giới giữa hai credential đã bị phá vỡ.

Refresh token không nhất thiết phải là JWT. Một chuỗi ngẫu nhiên khó đoán, có entropy cao và được quản lý trạng thái phía authorization server thường dễ rotation và thu hồi hơn. Nếu dùng JWT làm refresh token, chữ ký và claim thời gian không thay thế được việc theo dõi grant, trạng thái sử dụng, rotation và thu hồi.

## 3. Thiết kế access token có thời hạn ngắn

### 3.1. Lợi ích và giới hạn

Thời hạn access token ngắn giúp giảm khoảng thời gian token bị đánh cắp có thể được sử dụng. Khi access token hết hạn, resource server từ chối token theo claim thời gian, ngay cả khi chữ ký vẫn hợp lệ.

Nhưng TTL ngắn không tự động giải quyết mọi vấn đề:

- token bị đánh cắp vẫn có thể được dùng trong thời gian còn hiệu lực;
- refresh token bị đánh cắp có thể tạo access token mới;
- resource server có thể chấp nhận token đã bị thu hồi nếu chỉ kiểm tra chữ ký và thời gian;
- clock skew, cache, thời gian xử lý và retry có thể ảnh hưởng thời điểm hết hạn thực tế;
- TTL quá ngắn làm tăng số lần refresh, tải lên authorization server và độ phức tạp xử lý lỗi.

Cần chọn TTL theo rủi ro, loại client, loại dữ liệu, audience, khả năng thu hồi và yêu cầu trải nghiệm. Không có một con số thời hạn chung phù hợp mọi hệ thống.

### 3.2. Những yếu tố quyết định TTL

Khi chọn TTL, đánh giá:

1. **Mức nhạy cảm của resource:** API đọc thông tin công khai có thể có mức rủi ro khác API chuyển tiền hoặc quản trị.
2. **Phạm vi quyền:** token có quyền rộng cần được kiểm soát chặt hơn token chỉ đọc một resource.
3. **Khả năng phát hiện và thu hồi:** hệ thống có introspection, denylist, grant version hoặc sender constraint không?
4. **Loại client:** browser, native app, desktop app, workload hoặc service-to-service có khả năng bảo vệ credential khác nhau.
5. **Tần suất sử dụng:** token được gửi trong hàng nghìn request mỗi phút có rủi ro và chi phí khác token chỉ dùng một lần.
6. **Độ trễ và khả năng sẵn sàng:** refresh endpoint có thể chịu được tần suất làm mới dự kiến không?
7. **Yêu cầu nghiệp vụ:** thao tác nhạy cảm có yêu cầu xác thực lại hoặc step-up không?

TTL phải được cấu hình theo token profile hoặc resource policy. Tránh một TTL rất dài cho mọi loại token chỉ để giảm số lần refresh.

### 3.3. Kiểm tra exp và thời gian

Access token dạng JWT thường dùng `iat` để biểu thị thời điểm phát hành và `exp` để biểu thị thời điểm hết hạn. Resource server phải kiểm tra thời gian theo chính sách, với clock skew nhỏ để xử lý sai lệch đồng hồ hợp lý.

- `exp` phải là NumericDate hợp lệ.
- Token không được chấp nhận sau thời điểm hết hạn, ngoại trừ leeway nhỏ được cấu hình rõ.
- `iat` không nên nằm trong tương lai vượt quá clock skew cho phép.
- Có thể kiểm tra TTL thực tế bằng `exp - iat` và giới hạn TTL tối đa theo profile.
- Không kéo dài hiệu lực bằng cách tự thêm thời gian khi token đã hết hạn.
- Không dùng `nbf` hoặc `iat` thay thế `exp`.

Nếu resource server chấp nhận clock skew quá lớn, thời gian sử dụng thực tế của token sẽ dài hơn TTL issuer dự kiến. Các thành phần nên đồng bộ thời gian và thống nhất leeway.

### 3.4. Access token phải giới hạn theo audience và quyền

TTL ngắn không thay thế least privilege. Access token nên:

- có `aud` cụ thể cho resource server;
- chỉ chứa scope/permission cần thiết;
- giới hạn tenant và ngữ cảnh truy cập khi profile yêu cầu;
- không chứa quyền quản trị hoặc dữ liệu cá nhân không cần thiết;
- có token type/profile rõ ràng;
- được ký bằng khóa và thuật toán được cấu hình tin cậy.

Token có thời hạn 5 phút nhưng chứa quyền truy cập toàn bộ hệ thống vẫn có thể gây thiệt hại lớn trong 5 phút đó. Thời hạn và phạm vi quyền phải được thiết kế cùng nhau.

## 4. Refresh token là credential riêng

### 4.1. Refresh token không phải access token thứ hai

Refresh token chỉ được gửi tới authorization server tại token endpoint theo giao thức. Nó không phải credential để gọi API và không nên được resource server chấp nhận.

Một refresh token hợp lệ chỉ cho phép tiếp tục grant đã được cấp, trong các giới hạn như:

- client được gắn với refresh token;
- subject và grant còn hiệu lực;
- audience/resource được phép;
- scope không vượt quyền đã cấp;
- thời hạn và trạng thái refresh token còn hợp lệ;
- sender constraint hoặc bằng chứng sở hữu được đáp ứng nếu có.

Refresh token không phải bằng chứng đăng nhập vô hạn. Tài khoản bị khóa, consent bị thu hồi, grant hết hạn hoặc chính sách rủi ro thay đổi đều có thể khiến refresh bị từ chối.

### 4.2. Nên dùng refresh token ngẫu nhiên, khó đoán

Nếu refresh token là opaque credential, hãy tạo bằng CSPRNG với entropy cao. Token phải đủ dài để không thể dò đoán thực tế, không chứa username, email, timestamp hoặc thông tin có thể suy ra.

Authorization server có thể lưu bản băm hoặc HMAC của refresh token thay vì giá trị nguyên bản:

- khi nhận token, tính lại digest/fingerprint theo cơ chế đã chọn;
- tra cứu bản ghi trạng thái tương ứng;
- xác minh client, grant, trạng thái, expiry và rotation;
- không ghi token nguyên vẹn vào log hoặc telemetry;
- bảo vệ khóa HMAC nếu dùng keyed fingerprint.

Việc lưu digest không thay thế mã hóa dữ liệu nhạy cảm, phân quyền kho dữ liệu hoặc kiểm soát truy cập. Cần chọn thuật toán phù hợp và bảo đảm token có entropy đủ cao.

### 4.3. Refresh token cần gắn với grant và client

Một bản ghi refresh token nên liên kết tới thông tin cần thiết để thực thi chính sách, ví dụ:

| Trường trạng thái | Mục đích |
| --- | --- |
| Token reference / digest | Tra cứu và xác minh credential |
| Grant/session ID | Xác định authorization grant hoặc phiên gốc |
| Client ID | Giới hạn client được phép sử dụng |
| Subject ID | Chủ thể mà grant đại diện, nếu có |
| Authorized scope | Phạm vi quyền tối đa đã cấp |
| Resource/audience | Resource được phép nhận access token |
| Issued/expiry time | Theo dõi thời hạn |
| Last used time | Hỗ trợ idle timeout và phát hiện bất thường |
| Family ID / generation | Theo dõi rotation và reuse |
| Status | Active, used, revoked, expired hoặc compromised |
| Sender constraint | Khóa/chứng thư ràng buộc nếu profile áp dụng |

Không cần mọi hệ thống lưu mọi trường theo cùng một schema, nhưng phải có đủ trạng thái để biết token thuộc grant nào, client nào được sử dụng và có bị thu hồi hay chưa.

## 5. Vòng đời tổng thể

Một mô hình điển hình:

~~~text
Authentication / Authorization
          |
          v
Authorization Server
          |
          +----> Short-lived Access Token
          |
          +----> Protected Refresh Token
                       |
                       v
                  Client stores
                       |
             Access token expires
                       |
                       v
              Refresh Token Grant
                       |
             Validate client/grant
                       |
             Recalculate permissions
                       |
             Rotate refresh token
                       |
             +---------+---------+
             |                   |
             v                   v
       New Access Token    New Refresh Token
~~~

Các giai đoạn:

1. **Cấp phát:** authorization server xác minh authentication/grant, tính quyền và phát hành access token cùng refresh token nếu flow cho phép.
2. **Sử dụng:** client gửi access token tới resource server phù hợp.
3. **Làm mới:** khi access token sắp hết hạn hoặc hết hạn, client gửi refresh token tới token endpoint.
4. **Xác minh:** authorization server kiểm tra client, token, grant, trạng thái, scope/resource và risk.
5. **Rotation:** nếu áp dụng, refresh token cũ bị vô hiệu hóa và token mới được cấp.
6. **Thu hồi:** logout, phát hiện reuse, thay đổi consent hoặc sự cố có thể vô hiệu hóa refresh token/grant.
7. **Kết thúc:** access token hết hạn; refresh token hết hạn, bị thu hồi hoặc bị xóa theo retention policy.

Refresh token và access token có vòng đời riêng. Thu hồi refresh token ngăn các lần refresh tiếp theo, nhưng không nhất thiết làm access token JWT đã phát hành mất hiệu lực ngay lập tức.

## 6. Quy trình refresh an toàn

### 6.1. Các bước kiểm tra

Khi nhận refresh request, authorization server cần:

1. Xác thực client theo loại client và yêu cầu giao thức.
2. Xác định refresh token và kiểm tra trạng thái.
3. Kiểm tra token chưa hết hạn, chưa bị thu hồi, chưa bị sử dụng trái quy tắc rotation.
4. Xác minh refresh token thuộc đúng client/grant.
5. Kiểm tra grant, subject, consent và phiên còn hoạt động.
6. Xác minh resource/audience và scope được yêu cầu nằm trong phạm vi được phép.
7. Tính lại quyền theo policy hiện tại, bao gồm tenant membership và trạng thái tài khoản.
8. Kiểm tra sender constraint nếu token được ràng buộc với khóa/chứng thư.
9. Phát hành access token mới theo TTL và profile.
10. Rotation refresh token nếu chính sách yêu cầu; ghi nhận trạng thái và audit event.

Không cấp token mới chỉ vì refresh token có chữ ký hợp lệ hoặc chưa tới `exp`. Trạng thái grant và chính sách hiện tại vẫn phải được kiểm tra.

### 6.2. Scope khi refresh

Theo OAuth 2.0, nếu client không gửi tham số `scope` trong refresh request, scope được xử lý như scope đã được resource owner cấp ban đầu. Nếu client gửi scope, phạm vi yêu cầu không được vượt quá scope đã cấp.

Hệ thống nên:

- giữ nguyên quyền nếu grant còn hợp lệ và policy không thay đổi;
- downscope khi quyền bị giảm hoặc resource policy yêu cầu;
- từ chối nếu client yêu cầu quyền vượt grant;
- không mở rộng scope chỉ vì refresh token còn hợp lệ;
- yêu cầu authorization/consent mới khi cần cấp thêm quyền.

Nếu quyền của người dùng đã bị thu hồi sau lần cấp access token trước, refresh phải tính lại quyền và không được tái phát hành quyền cũ từ snapshot lỗi thời.

### 6.3. Resource/audience khi refresh

Không mặc định refresh token được sử dụng cho mọi API. Authorization server phải kiểm tra resource được yêu cầu thuộc phạm vi grant/client. Nếu hệ thống dùng resource indicator hoặc audience cụ thể, mỗi lần refresh cần tuân thủ đúng policy và profile.

Một token cho Orders API không tự động được đổi thành token cho Payments API chỉ vì client đang sở hữu refresh token. Quyền truy cập resource khác phải được cấp theo authorization decision phù hợp.

## 7. Refresh token rotation và reuse detection

### 7.1. Rotation là gì?

Refresh token rotation nghĩa là sau một lần refresh thành công, authorization server cấp refresh token mới và vô hiệu hóa refresh token cũ. Client phải thay thế token cũ bằng token mới một cách an toàn.

Ví dụ family:

~~~text
RT-1 --refresh--> RT-2 --refresh--> RT-3
  |                 |                 |
used/revoked      used/revoked       active
~~~

Rotation làm giảm giá trị của bản sao refresh token cũ: sau khi token đã được dùng và thay thế, việc sử dụng lại nó có thể cho thấy credential đã bị sao chép.

### 7.2. Reuse detection

Nếu authorization server nhận lại refresh token đã bị đánh dấu used/revoked trong khi family đã được rotation, đây có thể là dấu hiệu replay hoặc token theft.

Một phản ứng phổ biến:

- xác định family/grant liên quan;
- đánh dấu sự kiện reuse;
- thu hồi refresh token đang active trong family hoặc toàn bộ grant theo policy;
- yêu cầu người dùng/client thực hiện authorization lại;
- ghi audit event và cảnh báo;
- điều tra thiết bị, client, thời điểm và nguồn truy cập.

Không chỉ từ chối token cũ rồi tiếp tục chấp nhận token mới mà không đánh giá rủi ro. Kẻ tấn công có thể đang giữ bản sao token mới nhất.

### 7.3. Rotation cần xử lý concurrency

Hai request refresh đồng thời có thể cùng gửi một refresh token. Nếu không có thao tác nguyên tử, hệ thống có thể tạo hai token kế tiếp hoặc nhận nhầm request hợp lệ là reuse.

Cần thiết kế:

- chuyển trạng thái token từ active sang used một cách nguyên tử;
- chỉ một request được phép thắng việc tiêu thụ token;
- ghi quan hệ parent/child hoặc generation trong family;
- định nghĩa rõ retry và trường hợp response bị mất;
- không tạo grace period rộng khiến token cũ được chấp nhận tùy tiện.

Nếu client gửi hai refresh request song song, client nên điều phối để chỉ có một refresh đang diễn ra cho cùng grant. Authorization server vẫn phải bảo vệ ở phía máy chủ vì client không đáng tin tuyệt đối.

### 7.4. Mất response sau khi rotation

Một tình huống khó: authorization server đã tiêu thụ RT-1 và phát hành RT-2, nhưng response bị mất trên đường truyền. Client chỉ còn RT-1; nếu gửi lại, server có thể phát hiện reuse và thu hồi family.

Đây là trade-off giữa bảo vệ replay và khả năng phục hồi. Các lựa chọn triển khai cần được thiết kế rõ ràng:

- dùng cơ chế idempotency/transaction phù hợp để xử lý retry của cùng một thao tác;
- ràng buộc retry với client/session và request context đã xác minh;
- dùng grace window rất hẹp chỉ khi threat model và sender constraint cho phép;
- nếu không thể khôi phục an toàn, yêu cầu authorization lại.

Không trả lại refresh token mới chỉ dựa trên một request có RT cũ mà không xác minh đủ ngữ cảnh; điều đó có thể giúp kẻ đánh cắp token lấy được token kế tiếp.

## 8. Ràng buộc refresh token với client và sender

Refresh token cần được ràng buộc với client đã được cấp token. Với confidential client, authorization server xác thực client theo yêu cầu giao thức. Với public client, không có client secret đủ tin cậy để chứng minh danh tính ứng dụng theo cách của confidential client, nên cần biện pháp bổ sung.

Các cơ chế sender-constrained có thể giúp giảm nguy cơ token bị dùng bởi bên chỉ đánh cắp được chuỗi token:

- **DPoP:** client chứng minh quyền kiểm soát khóa bằng proof ở tầng ứng dụng; token có thể được ràng buộc với khóa.
- **Mutual TLS certificate-bound tokens:** token được ràng buộc với chứng thư client; bên gọi phải chứng minh sở hữu private key tương ứng.
- **Các cơ chế ràng buộc thiết bị/khóa khác:** chỉ dùng khi profile và hệ sinh thái xác định rõ cách tạo, lưu, xoay và xác minh bằng chứng.

Sender constraint không làm token không thể bị đánh cắp hoặc sử dụng sai trong mọi trường hợp. Nếu kẻ tấn công chiếm được cả token và khả năng dùng khóa, rủi ro vẫn tồn tại. Vì vậy vẫn cần TTL, rotation, revoke, phát hiện bất thường và bảo vệ endpoint.

Không coi IP address hoặc User-Agent là sender constraint mạnh. Chúng có thể thay đổi, bị chia sẻ hoặc giả mạo.

## 9. Lưu trữ refresh token an toàn ở phía client

Refresh token thường có giá trị cao hơn access token vì nó có thể tạo token mới nhiều lần. Nơi lưu phụ thuộc loại client:

### 9.1. Web application có backend trung gian

Một mô hình thường an toàn hơn là giữ refresh token ở backend-for-frontend (BFF) hoặc server-side session store. Browser chỉ giữ session cookie có thuộc tính phù hợp như `Secure`, `HttpOnly` và `SameSite` theo kiến trúc.

Lợi ích:

- refresh token không cần xuất hiện trong JavaScript của browser;
- backend có thể quản lý rotation và thu hồi tập trung;
- browser chỉ cần credential phiên ứng dụng;
- giảm khả năng XSS trực tiếp đọc refresh token.

Cookie-based session vẫn cần bảo vệ CSRF, cấu hình domain/path phù hợp, HTTPS và kiểm soát XSS. `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn script độc hại gửi request từ trang đã bị chiếm quyền.

### 9.2. Single-page application / public browser client

Nếu browser client trực tiếp giữ refresh token, phải xem đây là credential có nguy cơ bị XSS lấy cắp. Local storage tồn tại lâu và có thể bị JavaScript cùng origin đọc; không nên coi nó là kho bí mật.

Các biện pháp giảm rủi ro:

- ưu tiên kiến trúc không để refresh token lộ cho JavaScript khi có thể;
- nếu phải dùng public client, áp dụng refresh token rotation hoặc sender constraint theo RFC 9700;
- dùng CSP nghiêm ngặt, kiểm soát dependency và giảm bề mặt XSS;
- tránh lưu refresh token lâu dài trong local storage;
- giới hạn idle/absolute lifetime và có revoke;
- không để token xuất hiện trong URL, console, analytics hoặc error report.

Lưu token trong memory giảm thời gian tồn tại qua reload nhưng không ngăn XSS đang chạy đọc hoặc sử dụng token. Cần đánh giá toàn bộ threat model, không dựa vào một lựa chọn storage đơn lẻ.

### 9.3. Native/mobile/desktop client

Với ứng dụng native hoặc desktop, ưu tiên kho credential bảo mật do hệ điều hành cung cấp, gắn với quyền truy cập của ứng dụng và cơ chế khóa thiết bị phù hợp. Không hardcode refresh token hoặc secret vào binary, file cấu hình, log hay backup không bảo vệ.

Nếu thiết bị bị root/jailbreak hoặc môi trường bị xâm nhập, bảo vệ local token có thể suy giảm. Cần kết hợp device/session risk, rotation, revoke và yêu cầu xác thực lại khi rủi ro tăng.

### 9.4. Không log hoặc chia sẻ refresh token

Không đưa refresh token vào:

- URL hoặc query string;
- log, trace, crash report hoặc analytics;
- clipboard hoặc thông báo;
- dữ liệu telemetry;
- ticket hỗ trợ hoặc ảnh chụp màn hình;
- message queue không có kiểm soát credential.

Khi cần correlation, dùng grant ID, token reference hoặc fingerprint được bảo vệ thay vì giá trị token nguyên vẹn.

## 10. Thời hạn refresh token và session lifetime

Refresh token có thể tồn tại lâu hơn access token, nhưng không nên mặc định không hết hạn. Nên có ít nhất hai giới hạn:

- **Absolute lifetime:** thời điểm tối đa mà grant/refresh token có thể tồn tại kể từ lúc cấp.
- **Idle lifetime:** khoảng thời gian tối đa không sử dụng trước khi refresh token/grant hết hiệu lực.

Một số hệ thống còn giới hạn số lần refresh, thời gian kể từ lần xác thực gần nhất hoặc yêu cầu step-up theo rủi ro.

Ví dụ minh họa:

| Thành phần | Chính sách giả định |
| --- | --- |
| Access token | TTL ngắn, ví dụ 5 phút |
| Refresh token absolute lifetime | Ví dụ 30 ngày từ lúc cấp |
| Refresh token idle timeout | Ví dụ 7 ngày không sử dụng |
| Reauthentication | Yêu cầu lại khi thao tác nhạy cảm hoặc vượt tuổi xác thực cho phép |

Các con số trên chỉ minh họa cách kết hợp giới hạn; không phải khuyến nghị mặc định cho mọi hệ thống. TTL thực tế cần dựa trên threat model, client type, dữ liệu và yêu cầu vận hành.

Refresh thành công có thể cập nhật last-used time nhưng không nhất thiết đặt lại absolute lifetime. Nếu mỗi lần refresh đều kéo dài vô hạn, một credential bị đánh cắp có thể duy trì quyền truy cập không giới hạn.

Cần phân biệt:

- access token expiration;
- refresh token expiration;
- grant/session expiration;
- authentication age (`auth_time`);
- idle timeout và absolute timeout.

Một phiên có thể còn active nhưng đã quá tuổi xác thực cho một hành động nhạy cảm. Khi đó, refresh access token không thay thế reauthentication/step-up.

## 11. Thời điểm client nên refresh

Client có thể refresh ngay khi access token hết hạn hoặc chủ động refresh trước một khoảng nhỏ để tránh request API thất bại. Nếu refresh trước:

- tính thời điểm refresh từ `exp` và clock skew dự phòng;
- tránh refresh quá sớm làm tăng tải và giảm tuổi thọ hữu ích của token;
- tránh mọi request đồng thời cùng khởi chạy refresh;
- chia sẻ access token mới giữa các request đang chờ trong cùng session;
- điều phối rotation để chỉ có một refresh token được tiêu thụ cho mỗi generation.

Một chiến lược khái niệm:

~~~text
if accessToken.expiresAt <= now + refreshSafetyWindow:
    acquireRefreshLock(grantId)

    if accessToken is still valid beyond refreshSafetyWindow:
        releaseRefreshLock(grantId)
        return accessToken

    response = refreshOnce(currentRefreshToken)
    atomicallyReplaceStoredTokens(response)
    releaseRefreshLock(grantId)
    return response.accessToken
else:
    return accessToken
~~~

Đây là pseudocode, không phải quy tắc bắt buộc. Client cần xử lý lock timeout, process crash, response mất và token rotation. Không giữ lock vô hạn và không lưu token mới một phần khiến access token và refresh token thuộc hai generation khác nhau.

Không nên refresh mỗi lần nhận HTTP 401 một cách mù quáng. 401 có thể do chữ ký sai, issuer/audience sai, token bị thu hồi hoặc credential không hợp lệ. Client chỉ nên thử refresh khi xác định lỗi liên quan tới access token hết hạn theo hợp đồng API; tránh vòng lặp refresh vô hạn.

## 12. Thu hồi và logout

### 12.1. Thu hồi refresh token

Khi logout, phát hiện refresh token reuse, thiết bị bị mất, client bị xâm phạm hoặc grant bị thu hồi, authorization server cần vô hiệu hóa refresh token và trạng thái liên quan.

Có thể thu hồi theo:

- một refresh token;
- toàn bộ refresh token family;
- grant/session của một client;
- tất cả phiên của một subject;
- credential hoặc client cụ thể khi xảy ra sự cố.

Phạm vi revoke phải dựa trên mục tiêu nghiệp vụ và threat model. Logout trên một thiết bị không nhất thiết phải logout mọi thiết bị, trừ khi policy yêu cầu.

### 12.2. Access token JWT có thể vẫn còn hiệu lực

Thu hồi refresh token không tự động làm access token JWT đã phát hành bị vô hiệu hóa. Nếu resource server chỉ kiểm tra chữ ký, issuer, audience và `exp`, token vẫn có thể được chấp nhận đến khi hết hạn.

Muốn thu hồi access token sớm hơn, hệ thống có thể dùng:

- TTL access token ngắn để giới hạn cửa sổ;
- denylist theo `jti` hoặc token reference;
- introspection hoặc kiểm tra trạng thái grant;
- grant/session version được resource server kiểm tra;
- sender-constrained token và policy cập nhật;
- cơ chế phân phối sự kiện thu hồi tới resource server.

Mỗi lựa chọn có chi phí về latency, availability, cache và consistency. Cần xác định mức độ tức thời thực sự cần thiết.

### 12.3. Logout ở client không đủ

Xóa token khỏi storage phía client chỉ ngăn client đó tiếp tục gửi token. Bản sao đã bị đánh cắp ở nơi khác vẫn có thể được sử dụng.

Một quy trình logout hoàn chỉnh có thể cần:

1. Gọi endpoint revoke hoặc API kết thúc session theo giao thức.
2. Authorization server đánh dấu refresh token/grant bị thu hồi.
3. Xóa token và session state ở client.
4. Resource server nhận trạng thái revoke nếu cần vô hiệu hóa access token sớm.
5. Ghi audit event mà không lưu token nguyên vẹn.

## 13. Xử lý lỗi refresh và khả năng phục hồi

Không phải mọi lỗi refresh đều có thể thử lại:

| Lỗi | Cách xử lý |
| --- | --- |
| Access token đã hết hạn, refresh hợp lệ | Thực hiện refresh theo policy |
| Refresh token hết hạn | Yêu cầu authorization/đăng nhập lại |
| Refresh token bị revoke | Không retry; kết thúc grant/session |
| Client authentication thất bại | Không retry bằng credential cũ vô hạn; xử lý cấu hình/client |
| Scope/resource vượt grant | Downscope hoặc yêu cầu authorization mới |
| Refresh token reuse detected | Thu hồi family/grant theo policy và điều tra |
| Network timeout trước khi server xử lý | Retry có kiểm soát nếu biết request chưa được tiêu thụ |
| Timeout không rõ server đã rotation hay chưa | Dùng cơ chế idempotency/coordination; không gửi token cũ lặp vô hạn |
| Authorization server tạm unavailable | Backoff, giữ trạng thái session phù hợp và tránh refresh storm |

Client nên dùng exponential backoff có jitter cho lỗi tạm thời, nhưng không retry lỗi xác thực/ủy quyền vĩnh viễn. Nếu access token đã hết hạn và refresh không thể thực hiện, client cần đưa người dùng về luồng xác thực phù hợp.

Không tiếp tục gọi API bằng access token hết hạn chỉ vì refresh endpoint đang lỗi. Resource server vẫn phải thực thi expiry; client cần xử lý trạng thái chưa xác thực một cách rõ ràng.

## 14. Phát hiện lạm dụng refresh token

Refresh token được dùng ít hơn access token, nên các mẫu bất thường có thể hữu ích cho phát hiện xâm phạm:

- cùng một refresh token xuất hiện từ nhiều thiết bị/nguồn bất thường;
- token đã rotation bị dùng lại;
- refresh xảy ra với tần suất cao hơn baseline;
- một grant liên tục xin token cho nhiều audience hoặc scope khác nhau;
- refresh tiếp tục sau khi subject bị khóa hoặc consent bị thu hồi;
- client identity không khớp với grant;
- sender constraint thất bại;
- refresh từ môi trường hoặc vị trí có rủi ro cao.

Có thể ghi nhận event với grant ID, client ID, subject reference đã giả danh hóa, token family/generation, timestamp, kết quả và reason code. Không log refresh token nguyên vẹn, access token hoặc secret.

Khi có dấu hiệu compromise, cân nhắc thu hồi family/grant, yêu cầu xác thực lại, cảnh báo người dùng và điều tra các access token đã được phát hành. Chỉ rotate token mà không xử lý phiên bị xâm phạm có thể để kẻ tấn công tiếp tục.

## 15. Kiến trúc tham khảo

### 15.1. Access token tới resource server, refresh token tới authorization server

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server

    C->>AS: Authorization / token request
    AS->>C: Access token ngắn hạn + refresh token
    C->>API: API request với access token
    API->>API: Verify signature, iss, aud, exp, scope
    API->>C: Protected resource response

    Note over C: Access token sắp hết hạn
    C->>AS: Refresh grant với refresh token
    AS->>AS: Verify client, grant, status, scope
    AS->>AS: Rotate refresh token nếu áp dụng
    AS->>C: Access token mới + refresh token mới
    C->>C: Thay thế token state nguyên tử
~~~

### 15.2. Trạng thái refresh token family

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Used: Refresh thành công và rotate
    Used --> Active: Tạo generation kế tiếp
    Used --> Compromised: Phát hiện reuse
    Active --> Revoked: Logout / revoke / grant bị thu hồi
    Active --> Expired: Hết absolute hoặc idle lifetime
    Compromised --> Revoked: Thu hồi family
    Revoked --> [*]
    Expired --> [*]
~~~

Sơ đồ là mô hình khái niệm. Triển khai cần lưu trạng thái family/generation và cập nhật nguyên tử; không chỉ dựa trên một claim JWT.

## 16. Mã giả phía authorization server

~~~text
function refreshAccessToken(request):
    client = authenticateClientAccordingToType(request.client)
    require client is valid

    tokenRecord = refreshStore.findBySecureFingerprint(
        request.refreshToken
    )
    require tokenRecord exists

    transaction = refreshStore.beginAtomicTransaction(
        tokenRecord.familyId
    )

    require tokenRecord.clientId == client.id
    require tokenRecord.status == ACTIVE
    require tokenRecord.absoluteExpiry > now
    require tokenRecord.idleExpiry > now

    grant = grantStore.load(tokenRecord.grantId)
    require grant.status == ACTIVE
    require grant.clientId == client.id
    require grant.subjectIsEligible

    if tokenRecord.isSenderConstrained:
        verifyProofOfPossession(request, tokenRecord.binding)

    require tokenRecord.generation is currentGeneration

    currentPermissions = policyEngine.recalculate(
        grant.subject,
        client,
        grant.resources,
        grant.tenant
    )

    grantedScopes = intersect(
        tokenRecord.authorizedScopes,
        request.requestedScopesOrOriginal,
        currentPermissions
    )
    require grantedScopes satisfy request policy

    markRefreshTokenUsedAtomically(tokenRecord)

    newAccessToken = issueShortLivedAccessToken(
        subject = grant.subject,
        audience = selectAllowedAudience(request, grant),
        scopes = grantedScopes,
        expiration = accessTokenPolicy.expiration
    )

    newRefreshToken = generateHighEntropyRefreshToken()
    storeNextGeneration(
        family = tokenRecord.familyId,
        parent = tokenRecord.id,
        client = client.id,
        grant = grant.id,
        token = secureFingerprint(newRefreshToken),
        scopes = grantedScopes
    )

    commit(transaction)
    return newAccessToken, newRefreshToken
~~~

Đây là pseudocode mô tả các kiểm tra và ranh giới giao dịch. Trong hệ thống thực tế, cần xử lý trường hợp transaction rollback, signing service lỗi, response mất, client retry và audit event. Không đánh dấu token cũ đã dùng rồi để lộ trạng thái nửa chừng mà không có cơ chế khôi phục nhất quán.

## 17. Kiểm thử cần có

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Access expiry | Access token hết hạn | Resource server từ chối |
| Refresh validity | Refresh token hợp lệ, grant active | Cấp access token mới theo policy |
| Refresh expiry | Refresh token hết absolute/idle lifetime | Từ chối và yêu cầu authorization lại |
| Client binding | Client khác dùng refresh token | Từ chối |
| Scope | Request scope vượt grant | Downscope hoặc từ chối |
| Permission change | Subject bị thu hồi quyền trước refresh | Token mới không chứa quyền cũ |
| Audience | Yêu cầu resource không thuộc grant | Từ chối |
| Rotation | Refresh thành công | Token cũ used/revoked, token mới active |
| Reuse | Dùng lại refresh token đã rotation | Phát hiện reuse và xử lý family |
| Concurrency | Hai request refresh cùng token | Chỉ một thao tác tiêu thụ token thành công |
| Lost response | Server rotation nhưng response bị mất | Retry theo cơ chế đã thiết kế, không tạo nhánh family sai |
| Logout | Revoke refresh token/grant | Không thể refresh tiếp |
| Access revoke | Revoke refresh nhưng access JWT cũ còn hạn | Hành vi đúng theo cơ chế access-token revocation đã chọn |
| Sender constraint | Proof/khóa không hợp lệ | Từ chối |
| Storage | Token bị lộ qua log/URL/analytics | Kiểm soát phát hiện không ghi credential |
| Failure | Authorization server hoặc state store tạm lỗi | Backoff, fail-safe theo policy, không fallback cấp quyền |

Kiểm thử thêm việc client chỉ có một refresh request đang chạy cho mỗi grant, thay thế access/refresh token mới theo thao tác nguyên tử và không tiếp tục dùng refresh token generation cũ sau khi rotation.

## 18. Những sai lầm cần tránh

- Dùng access token có thời hạn dài chỉ để giảm số lần refresh.
- Dùng refresh token như bearer token gọi API.
- Cho rằng refresh token bắt buộc phải là JWT.
- Coi refresh token còn hạn là đủ để cấp access token mới mà không kiểm tra grant.
- Để refresh token không có absolute lifetime hoặc idle timeout.
- Không ràng buộc refresh token với client/grant.
- Không rotation hoặc sender-constrain refresh token cho public client theo yêu cầu bảo mật hiện hành.
- Không phát hiện refresh token reuse.
- Rotation không nguyên tử, tạo hai nhánh family khi có request đồng thời.
- Không xử lý trường hợp response mất sau khi server đã tiêu thụ token.
- Coi revoke refresh token đồng nghĩa access token JWT cũ bị vô hiệu hóa ngay.
- Lưu refresh token trong storage dễ bị script đọc mà không đánh giá XSS.
- Ghi refresh token hoặc access token vào log, URL, analytics.
- Tự mở rộng scope/audience trong refresh.
- Dùng refresh để thay thế reauthentication hoặc step-up khi policy yêu cầu.

## 19. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): refresh token grant và quy tắc scope khi refresh.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation, sender constraint và public clients.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint và ngữ nghĩa thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token tại authorization server.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): ràng buộc token với khóa và proof of possession.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): xác thực client và token ràng buộc chứng thư.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim thời gian và cấu trúc JWT.

**Ghi nhớ:** Access token nên ngắn hạn, giới hạn theo audience và quyền; refresh token là credential riêng, chỉ gửi tới authorization server và phải được ràng buộc với client/grant. Hãy bảo vệ nơi lưu, đặt absolute/idle lifetime, rotation hoặc sender constraint phù hợp, phát hiện reuse và hiểu rõ rằng thu hồi refresh token không tự động vô hiệu hóa access token JWT đã phát hành.

