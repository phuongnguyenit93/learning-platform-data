# Thay đổi quyền khẩn cấp và chiến lược vô hiệu hóa token

> **Chương:** JWT và phân quyền  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho hệ thống xác thực và phân quyền sử dụng JWT nói chung, độc lập với ngôn ngữ lập trình hoặc framework.

## 1. Vì sao thay đổi quyền và vô hiệu hóa JWT là một bài toán riêng?

JWT self-contained thường mang theo claims như issuer, subject, audience, thời hạn và quyền. Resource server có thể xác minh chữ ký và kiểm tra claims ngay tại chỗ mà không cần hỏi authorization server ở mỗi request.

Cách này giúp giảm độ trễ và giảm phụ thuộc vào dịch vụ trung tâm. Tuy nhiên, token đã phát hành là một bản chụp trạng thái tại thời điểm phát hành. Nếu quyền của người dùng thay đổi sau đó, nội dung token không tự thay đổi theo.

Ví dụ:

1. Lúc 09:00, người dùng có quyền đọc và duyệt hóa đơn. Authorization server phát hành access token chứa scope đọc và duyệt.
2. Lúc 09:05, quản trị viên phát hiện tài khoản bị xâm nhập và thu hồi quyền duyệt.
3. Token cũ vẫn có chữ ký hợp lệ và còn hạn đến 09:30.
4. Nếu resource server chỉ kiểm tra chữ ký, audience và expiration, token cũ có thể tiếp tục được dùng để duyệt hóa đơn.

Đây là khoảng thời gian giữa lúc trạng thái quyền thay đổi và lúc mọi nơi thực thi quyền nhận biết thay đổi đó. Nó thường được gọi là **revocation window** hoặc khoảng hiệu lực còn sót lại của token.

Cần phân biệt hai việc:

- **Thay đổi quyền (authorization change):** cập nhật quyền mà một chủ thể được phép thực hiện.
- **Vô hiệu hóa token (token revocation):** làm cho một token hoặc một nhóm token không còn được chấp nhận trước thời điểm hết hạn tự nhiên.

Thay đổi quyền không phải lúc nào cũng đòi hỏi vô hiệu hóa toàn bộ token. Ngược lại, khi token hoặc tài khoản bị xâm phạm, chỉ cập nhật quyền hiện tại có thể chưa đủ để chặn các token cũ.

## 2. Giới hạn tự nhiên của JWT self-contained

JWT có chữ ký không phải một phiên đăng nhập có trạng thái tự động đồng bộ. Sau khi phát hành, JWT vẫn chứa claims ban đầu cho đến khi hết hạn hoặc bị một cơ chế phía nhận từ chối.

| Cơ chế kiểm tra | Có phát hiện quyền vừa bị thay đổi không? | Ghi chú |
|---|---|---|
| Xác minh chữ ký | Không | Chữ ký chứng minh token không bị sửa và được ký bằng khóa tương ứng; không cập nhật claims. |
| Kiểm tra exp | Không | Chỉ xác định token đã hết hạn hay chưa. |
| Kiểm tra iss và aud | Không | Ràng buộc issuer và recipient, không phản ánh quyền hiện tại. |
| Kiểm tra scope/role nằm trong token | Không, nếu chỉ đọc claims cũ | Claims phản ánh quyền lúc phát hành. |
| Tra cứu trạng thái phiên hoặc token | Có, nếu dữ liệu được cập nhật và kiểm tra trên mỗi request | Tạo thêm phụ thuộc trạng thái và chi phí tra cứu. |
| Đánh giá quyền hiện tại từ policy/service | Có | Có thể áp dụng thay đổi ngay, tùy độ trễ đồng bộ và cache. |

Một token có chữ ký hợp lệ vẫn có thể không còn được phép sử dụng. **Authentication** trả lời token có hợp lệ và đại diện cho chủ thể nào; **authorization** quyết định chủ thể có được thực hiện hành động cụ thể trên tài nguyên tại thời điểm hiện tại hay không.

Không nên xem việc xác minh JWT thành công là quyết định authorization cuối cùng cho các thao tác nhạy cảm.

## 3. Xác định phạm vi cần vô hiệu hóa

Trước khi chọn kỹ thuật, cần xác định chính xác phạm vi sự cố hoặc thay đổi quyền. Phạm vi càng rộng thì tác động đến người dùng và dịch vụ càng lớn.

| Phạm vi | Ví dụ | Mục tiêu |
|---|---|---|
| Một access token | Một token bị lộ trong log hoặc thiết bị thất lạc | Chặn đúng token đó. |
| Một phiên hoặc thiết bị | Người dùng đăng xuất một thiết bị hoặc báo mất điện thoại | Chặn mọi token thuộc một session/device. |
| Một chủ thể | Tài khoản bị khóa hoặc nhân viên rời tổ chức | Chặn token của chủ thể đó. |
| Một nhóm quyền | Quyền quản trị hoặc quyền duyệt bị thu hồi | Ngăn hành động thuộc quyền đã thu hồi. |
| Một client/application | Client secret hoặc thiết bị tích hợp bị xâm phạm | Chặn token phát hành cho client bị ảnh hưởng. |
| Một issuer hoặc signing key | Khóa ký bị lộ | Ngừng tin token được ký bằng khóa bị xâm phạm. |
| Toàn hệ thống | Sự cố nghiêm trọng ảnh hưởng trust boundary | Kích hoạt quy trình ứng phó và tái thiết lập tin cậy. |

Không mặc định dùng biện pháp rộng nhất. Thu hồi toàn bộ signing key có thể làm gián đoạn mọi người dùng được ký bằng khóa đó; chỉ chặn một jti sẽ không chặn token khác của cùng tài khoản. Chọn phạm vi theo bằng chứng và mục tiêu ứng phó.

## 4. Các chiến lược vô hiệu hóa token

### 4.1. Access token có thời hạn ngắn

Phát hành access token với thời hạn ngắn giúp giới hạn khoảng thời gian token cũ còn được chấp nhận.

Ví dụ, nếu access token có thời hạn 5 phút, token bị thu hồi nhưng không có cơ chế kiểm tra trạng thái vẫn có thể được sử dụng trong phần thời gian còn lại, cộng sai lệch đồng hồ được cho phép.

**Ưu điểm:**

- Dễ triển khai với JWT self-contained.
- Không cần tra cứu trạng thái token trên mỗi request.
- Giới hạn thời gian ảnh hưởng khi token bị lộ hoặc quyền thay đổi.

**Hạn chế:**

- Không vô hiệu hóa tức thời.
- Token bị đánh cắp vẫn có thể dùng đến khi hết hạn.
- Thời hạn quá ngắn có thể làm tăng tần suất refresh và tải lên authorization server.

Access token ngắn hạn là một lớp giảm thiểu rủi ro, không phải cơ chế thu hồi tức thời.

### 4.2. Denylist theo jti

JWT có thể mang claim jti để định danh duy nhất token. Khi cần thu hồi một token cụ thể, hệ thống ghi jti vào denylist và resource server kiểm tra trạng thái trước khi chấp nhận.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "billing-api",
  "jti": "at-7f4c1b2e",
  "iat": 1800000000,
  "exp": 1800000300,
  "scope": "invoice:read"
}
~~~

Khi thu hồi token, có thể lưu khóa tra cứu được tạo từ issuer và jti, ví dụ cặp (iss, jti), vào kho trạng thái bị thu hồi.

**Ưu điểm:**

- Thu hồi một token cụ thể.
- Không cần thay đổi mọi token khác của người dùng.
- Có thể đặt thời gian tồn tại bản ghi đến khi token hết hạn.

**Hạn chế:**

- Resource server phải tra cứu trạng thái hoặc dùng cache.
- Denylist cần được chia sẻ giữa các instance và khu vực.
- Nếu kho trạng thái không khả dụng, phải có chính sách fail-open/fail-closed rõ ràng.
- Cần tránh jti trùng giữa các issuer bằng cách namespace theo issuer.

Bản ghi denylist chỉ cần tồn tại đến sau thời điểm token không còn hợp lệ, thường là exp cộng clock-skew leeway mà hệ thống cho phép. Không giữ vô hạn nếu không có yêu cầu kiểm toán hoặc điều tra riêng.

### 4.3. Thu hồi theo session ID

Nếu token mang claim định danh phiên, chẳng hạn sid theo profile của hệ thống, nhiều access token có thể được gắn với cùng một phiên. sid không phải claim đăng ký chung trong RFC 7519; đây là claim do profile/giao thức cụ thể định nghĩa, vì vậy issuer và resource server phải thống nhất ý nghĩa, nguồn phát hành và phạm vi của nó.

Khi người dùng đăng xuất một thiết bị hoặc báo mất thiết bị, hệ thống đánh dấu session ID đó bị thu hồi. Resource server kiểm tra trạng thái phiên trước khi chấp nhận token.

**Ưu điểm:**

- Thu hồi nhiều token của cùng một phiên cùng lúc.
- Phù hợp với đăng xuất theo thiết bị hoặc session.
- Có thể giữ các phiên khác của người dùng hoạt động.

**Hạn chế:**

- Cần quản lý trạng thái phiên.
- Mỗi request cần kiểm tra trạng thái hoặc dùng cache.
- Token phải được ràng buộc rõ ràng với session; không thể suy ra session từ một claim tùy ý không được kiểm chứng.

### 4.4. Token version hoặc authorization version

Một cách khác là lưu phiên bản trạng thái bảo mật hoặc quyền hiện tại ở phía server. JWT mang phiên bản tại thời điểm phát hành. Khi quyền hoặc trạng thái tài khoản thay đổi, server tăng phiên bản hiện tại. Resource server so sánh giá trị trong token với giá trị hiện tại.

Ví dụ claims:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "billing-api",
  "authz_ver": 12,
  "iat": 1800000000,
  "exp": 1800000300,
  "scope": "invoice:read invoice:approve"
}
~~~

Trạng thái hiện tại của user có thể là authz_ver = 13. Token mang 12 sẽ bị từ chối.

**Ưu điểm:**

- Vô hiệu hóa cùng lúc nhiều token của một chủ thể.
- Có thể áp dụng khi thay đổi role, scope, trạng thái tài khoản hoặc sự cố bảo mật.
- Không cần lưu từng jti bị thu hồi.

**Hạn chế:**

- Cần tra cứu phiên bản hiện tại hoặc cache có đồng bộ.
- Tăng phiên bản sẽ thu hồi rộng hơn một token đơn lẻ.
- Phải xác định phiên bản áp dụng cho user, tenant, client hay session.

Tên claim như authz_ver hoặc token_version là quy ước của ứng dụng, không phải claim chuẩn bắt buộc của JWT. Cần bảo vệ dữ liệu phiên bản và tránh cho client tự cập nhật giá trị này.

### 4.5. Thu hồi theo thời điểm bảo mật

Có thể lưu thời điểm thu hồi token gần nhất cho một chủ thể hoặc một phiên, ví dụ revoked_before. Resource server so sánh iat của token với mốc này.

Nếu token được phát hành trước thời điểm thu hồi, từ chối token.

**Ưu điểm:**

- Không cần lưu từng jti.
- Phù hợp khi cần thu hồi tất cả token cũ của một user/session.
- Có thể triển khai cùng trạng thái tài khoản.

**Hạn chế:**

- Phụ thuộc độ chính xác đồng hồ và quy tắc clock skew.
- Có thể vô tình chặn token vừa được phát hành nếu timestamp hoặc propagation sai.
- Cần xác định phạm vi của mốc thu hồi.

Không dùng riêng iat để làm bằng chứng chống phát lại. iat là thời điểm phát hành, không phải định danh duy nhất của token.

### 4.6. Introspection hoặc tra cứu trạng thái token

Resource server có thể hỏi authorization server xem token còn active hay không. RFC 7662 định nghĩa OAuth 2.0 Token Introspection.

Cách này thường phù hợp khi:

- Cần trạng thái thu hồi gần thời gian thực.
- Muốn giữ quyết định trạng thái tập trung.
- Resource server không muốn tự quản lý denylist hoặc version.
- Chấp nhận thêm độ trễ và phụ thuộc vào authorization server.

**Ưu điểm:**

- Authorization server có thể phản ánh trạng thái thu hồi mới nhất.
- Có thể trả thêm metadata về client, scope và thời hạn.
- Phù hợp với mô hình token có trạng thái hoặc hệ thống cần kiểm soát tập trung.

**Hạn chế:**

- Thêm network call và latency.
- Authorization server trở thành dependency quan trọng.
- Cần xác thực resource server gọi introspection và bảo vệ response.
- Cache kết quả active có thể làm chậm hiệu lực thu hồi.

Nếu cache kết quả introspection, TTL của cache là một phần của revocation window. Không thể tuyên bố thu hồi tức thời khi resource server vẫn dùng kết quả active cũ trong cache.

### 4.7. Thu hồi signing key

Nếu signing key bị lộ hoặc không còn đáng tin, issuer có thể ngừng ký bằng khóa đó và loại khóa khỏi tập khóa được resource server tin cậy.

Biện pháp này ảnh hưởng đến tất cả token được ký bằng khóa đó, không chỉ một user.

**Ưu điểm:**

- Có thể chặn diện rộng token được ký bằng một khóa bị xâm phạm.
- Phù hợp với sự cố lộ private signing key.

**Hạn chế:**

- Có thể làm gián đoạn nhiều ứng dụng hoặc người dùng.
- Resource server có thể cache JWKS cũ và tiếp tục tin khóa trong một khoảng thời gian.
- Cần phối hợp xoay khóa, cập nhật trust store, xử lý token đang lưu hành và kiểm tra các issuer/client liên quan.

Không thu hồi signing key chỉ vì một người dùng đổi role. Đây là biện pháp dành cho sự cố khóa hoặc thay đổi trust policy có phạm vi tương ứng.

## 5. Bảng chọn chiến lược theo tình huống

| Tình huống | Chiến lược thường phù hợp | Phạm vi ảnh hưởng |
|---|---|---|
| Một access token bị lộ | Denylist jti | Một token |
| Người dùng đăng xuất một thiết bị | Thu hồi sid/session | Một phiên |
| Tài khoản bị khóa hoặc nhân viên rời tổ chức | User token version, revoked_before hoặc trạng thái tài khoản | Các token của user |
| Thu hồi một quyền nhạy cảm | Authorization version hoặc kiểm tra policy hiện tại | Token/quyền của phạm vi được chọn |
| Thay đổi quyền cần có hiệu lực ngay | Policy lookup hoặc trạng thái authorization hiện tại ở resource server | Các request thuộc policy thay đổi |
| Refresh token bị lộ | Thu hồi refresh token/token family; đánh giá access token đã phát hành | Phiên hoặc token family |
| Signing private key bị lộ | Thu hồi key, rotate và cập nhật trust store | Mọi token chịu ảnh hưởng của key |
| Cần trạng thái tập trung | Token introspection | Theo trạng thái authorization server |

Có thể kết hợp nhiều cơ chế. Ví dụ, access token ngắn hạn cộng denylist jti cho sự cố cá biệt và token version cho việc khóa tài khoản.

## 6. Thay đổi quyền khẩn cấp: xử lý theo loại sự cố

### 6.1. Thu hồi một quyền nhưng giữ các quyền khác

Ví dụ nhân viên không còn được phép duyệt thanh toán nhưng vẫn cần xem hóa đơn.

Nếu token hiện tại chứa scope đọc và duyệt, chỉ cập nhật role trong cơ sở dữ liệu chưa làm scope cũ biến mất khỏi JWT.

Các lựa chọn:

- Kiểm tra quyền hiện tại ở resource server cho hành động duyệt.
- Tăng authorization version để buộc phát hành token mới.
- Thu hồi các token/session có quyền duyệt.
- Dùng access token ngắn hạn để giới hạn thời gian còn sót lại.

Với thao tác nhạy cảm, kiểm tra policy hiện tại thường phù hợp hơn việc chỉ dựa vào scope cũ. Token có thể xác định chủ thể và quyền tối đa được cấp, còn policy hiện tại quyết định hành động có được phép tại thời điểm request hay không.

### 6.2. Khóa tài khoản ngay lập tức

Khi phát hiện tài khoản bị xâm nhập:

1. Đánh dấu tài khoản bị khóa hoặc suspended trong nguồn trạng thái trung tâm.
2. Tăng token/authz version hoặc đặt mốc revoked_before cho user.
3. Thu hồi refresh token và token family liên quan.
4. Thu hồi session ID hoặc jti nếu cần phạm vi hẹp hơn.
5. Bảo đảm resource server kiểm tra trạng thái mới trước các hành động nhạy cảm.
6. Thu thập audit log và đánh giá các hành động đã thực hiện bằng token cũ.

Nếu resource server chỉ kiểm tra chữ ký và exp, bước 2 sẽ không có tác dụng cho đến khi token hết hạn. Cần bảo đảm đường kiểm tra trạng thái thực sự được thực thi.

### 6.3. Người dùng đổi mật khẩu hoặc reset thông tin xác thực

Đổi mật khẩu không mặc nhiên làm mọi access token JWT đã phát hành trở nên vô hiệu.

Chính sách có thể quy định:

- Giữ các phiên hiện tại nếu đây là thay đổi mật khẩu chủ động và không có dấu hiệu xâm phạm.
- Thu hồi tất cả refresh token nếu có nghi ngờ credential bị lộ.
- Tăng security/token version để chặn access token cũ khi cần.
- Thu hồi tất cả session khi reset mật khẩu do quản trị viên hoặc quy trình khôi phục tài khoản.
- Yêu cầu xác thực lại hoặc MFA cho thao tác nhạy cảm.

Cần phân biệt đổi mật khẩu thông thường với reset do sự cố; mức thu hồi nên dựa trên threat model và chính sách tổ chức.

### 6.4. Signing key bị xâm phạm

Nếu private signing key bị lộ:

1. Ngừng sử dụng key đó để ký token mới.
2. Loại key khỏi trust set hoặc đánh dấu không còn được chấp nhận ở resource server.
3. Phát hành key mới và phân phối public key qua kênh tin cậy.
4. Kiểm tra thời gian cache JWKS và propagation giữa các vùng.
5. Đánh giá token đã phát hành bằng key bị lộ.
6. Xem xét thu hồi session/refresh token liên quan và yêu cầu cấp token mới.
7. Theo dõi các lần xác minh token cũ và hoạt động bất thường.

Nếu chỉ xóa key khỏi JWKS nhưng resource server giữ bản cache cũ, token có thể vẫn được chấp nhận cho đến khi cache hết hạn. Cần có cơ chế cập nhật hoặc purge khẩn cấp trust cache.

## 7. Refresh token và access token có vòng đời khác nhau

Refresh token thường được dùng để xin access token mới. Thu hồi refresh token ngăn cấp access token mới từ refresh token đó, nhưng **không tự động làm access token JWT đã phát hành trước đó mất hiệu lực**.

| Hành động | Ảnh hưởng |
|---|---|
| Thu hồi refresh token | Ngăn sử dụng refresh token để xin access token mới. |
| Thu hồi token family | Chặn refresh token thuộc chuỗi/nhóm liên quan, tùy chính sách authorization server. |
| Thu hồi jti access token | Chặn access token cụ thể nếu resource server kiểm tra denylist. |
| Tăng user token version | Chặn các access token cũ nếu resource server so sánh version hiện tại. |
| Chờ access token exp | Token tự hết hiệu lực theo thời gian; không phải thu hồi tức thời. |

Nếu hệ thống hỗ trợ refresh token rotation, cần phát hiện việc sử dụng lại refresh token cũ theo chính sách. Khi phát hiện replay, có thể thu hồi token family và yêu cầu xác thực lại.

RFC 7009 mô tả OAuth 2.0 Token Revocation cho authorization server và khuyến nghị xử lý các token khác thuộc cùng authorization grant. Tuy nhiên, resource server chỉ xác minh JWT cục bộ vẫn có thể tiếp tục chấp nhận access token đã phát hành nếu không nhận được trạng thái thu hồi. Vì vậy cần một cơ chế để resource server nhận biết access token không còn active khi yêu cầu thu hồi sớm, chẳng hạn denylist, token version hoặc introspection.

## 8. Đồng bộ trạng thái thu hồi trong hệ thống phân tán

Một chiến lược revocation chỉ hiệu quả khi mọi resource server áp dụng trạng thái mới trong khoảng thời gian được yêu cầu.

### 8.1. Các nguồn gây trễ

- Cache denylist hoặc token version còn giá trị cũ.
- JWKS cache chưa nhận key rotation/revocation.
- Event invalidation bị mất hoặc xử lý chậm.
- Replica database chưa đồng bộ.
- Một vùng/cluster không kết nối được dịch vụ trạng thái.
- Clock skew giữa issuer, resource server và hệ thống lưu revoked_before.

### 8.2. Đặt mục tiêu propagation rõ ràng

Cần xác định mục tiêu như:

- Thu hồi token cá biệt có hiệu lực tối đa sau bao lâu?
- Tài khoản bị khóa phải chặn thao tác nhạy cảm trong bao lâu?
- Signing key bị lộ phải bị loại khỏi trust cache trong bao lâu?
- Khi nguồn trạng thái không khả dụng, endpoint nào fail-closed?

Không nên dùng từ “ngay lập tức” nếu hệ thống có cache hoặc replication không đồng bộ mà chưa chứng minh được thời gian propagation.

### 8.3. Cache và TTL

| Dữ liệu cache | Rủi ro khi TTL quá dài | Cách kiểm soát |
|---|---|---|
| Denylist jti | Token bị thu hồi vẫn được chấp nhận ở instance giữ cache cũ. | TTL ngắn, invalidation event và namespace theo issuer. |
| Session status | Logout/revoke session có hiệu lực chậm. | Pub/sub invalidation, version hoặc tra cứu live cho thao tác nhạy cảm. |
| User token version | Token cũ tiếp tục được chấp nhận. | TTL theo SLA revocation và cập nhật chủ động. |
| JWKS/trusted signing keys | Token ký bằng key bị lộ vẫn được xác minh. | Cache policy có giới hạn và kênh key-revocation khẩn cấp. |
| Introspection active result | Resource server tiếp tục tin token đã bị thu hồi. | TTL ngắn theo mức rủi ro và yêu cầu độ trễ. |

Nếu một resource server không thể xác minh trạng thái thu hồi, lựa chọn fail-open hay fail-closed phải được quyết định theo mức độ nhạy cảm. Với chuyển tiền, thay đổi quyền quản trị hoặc thao tác có tác động lớn, fail-closed thường phù hợp hơn. Với endpoint ít rủi ro, tổ chức có thể chọn chính sách khác để duy trì availability, nhưng cần chấp nhận rõ revocation window.

## 9. Fail-open và fail-closed khi kiểm tra revocation

| Chính sách | Hành vi khi không truy cập được kho revocation | Ưu điểm | Rủi ro |
|---|---|---|---|
| **Fail-open** | Tiếp tục chấp nhận JWT nếu chữ ký và claims cơ bản hợp lệ. | Duy trì availability. | Token đã thu hồi có thể tiếp tục được dùng trong thời gian outage. |
| **Fail-closed** | Từ chối request cần kiểm tra trạng thái. | Ưu tiên bảo vệ trước token đã thu hồi. | Outage của kho trạng thái có thể gây gián đoạn dịch vụ. |
| **Phân tầng theo rủi ro** | Endpoint nhạy cảm fail-closed; endpoint ít rủi ro có thể dùng cache/TTL hoặc fail-open theo policy. | Cân bằng availability và security. | Cần phân loại endpoint và kiểm thử chính sách rõ ràng. |

Không để từng service tự chọn hành vi khi dependency lỗi. Quyết định phải là một phần của security policy chung và được kiểm tra trong vận hành.

## 10. Quy trình ứng phó khi cần vô hiệu hóa khẩn cấp

Một runbook nên xác định ai có quyền kích hoạt, phạm vi thu hồi, cách đồng bộ và cách xác nhận kết quả.

### 10.1. Quy trình khái quát

~~~mermaid
flowchart TD
    A["Phát hiện sự cố hoặc thay đổi quyền"] --> B["Xác định subject, session, token, client hoặc signing key"]
    B --> C["Chọn phạm vi thu hồi tối thiểu đủ bảo vệ"]
    C --> D["Cập nhật trạng thái trung tâm và revoke refresh/session"]
    D --> E["Phát tán invalidation/version/key update"]
    E --> F["Resource server kiểm tra trạng thái mới"]
    F --> G["Kiểm thử token cũ và token mới"]
    G --> H["Theo dõi propagation, audit và hoàn tất sự cố"]
~~~

### 10.2. Các bước vận hành

1. **Xác nhận sự cố:** xác định token, chủ thể, session, client hoặc key có khả năng bị ảnh hưởng.
2. **Chọn phạm vi:** một jti, một sid, một user, một client hay một signing key.
3. **Chặn cấp mới:** thu hồi refresh token/token family hoặc ngừng ký bằng key bị xâm phạm.
4. **Cập nhật trạng thái:** denylist, token version, session state, account status hoặc trust store.
5. **Phát tán thay đổi:** gửi invalidation event, purge cache hoặc cập nhật JWKS/trust set.
6. **Xác nhận hiệu lực:** thử token cũ ở các resource server và vùng triển khai.
7. **Cấp lại quyền/token:** chỉ sau khi trạng thái tài khoản và quyền đã được xác minh.
8. **Theo dõi:** giám sát request bị từ chối, token cũ còn xuất hiện và lỗi dependency.
9. **Lưu audit:** ai kích hoạt, lý do, phạm vi, thời gian, kết quả và ngoại lệ.

### 10.3. Kiểm soát quyền kích hoạt revocation

Vô hiệu hóa diện rộng có thể làm gián đoạn nhiều người dùng. Vì vậy:

- Chỉ vai trò vận hành được ủy quyền mới được thu hồi signing key hoặc toàn bộ token của tenant.
- Ghi audit mọi thao tác revoke và thay đổi policy.
- Yêu cầu xác nhận bổ sung cho thao tác ảnh hưởng diện rộng nếu quy trình tổ chức quy định.
- Có cơ chế rollback cho cấu hình hoặc cache update bị lỗi, nhưng không khôi phục key đã bị xâm phạm.
- Kiểm tra độc lập sau khi thao tác hoàn tất.

## 11. Mã giả: kiểm tra token version và denylist

Mã giả sau minh họa một resource server kết hợp xác minh JWT với trạng thái thu hồi. Tên claim và cấu trúc kho trạng thái là quy ước ứng dụng.

~~~text
function authorize_request(token, request, policy):
    claims = verify_jwt_signature_and_standard_claims(token, policy)

    # Không truy vấn revocation bằng claims chưa xác minh.
    require_expected_issuer(claims.iss, policy.issuer)
    require_expected_audience(claims.aud, policy.audience)

    # Thu hồi một token cụ thể.
    token_key = namespace(claims.iss, claims.jti)
    if revocation_store.is_revoked(token_key):
        reject("invalid_token")

    # Thu hồi mọi token cũ của một session nếu có sid.
    if claims.sid is present:
        if session_store.is_revoked(claims.iss, claims.sid):
            reject("invalid_token")

    # Thu hồi token cũ của user khi security/authz version tăng.
    current_version = user_state.get_authz_version(claims.iss, claims.sub)
    if claims.authz_ver != current_version:
        reject("invalid_token")

    # Kiểm tra trạng thái tài khoản hiện tại.
    if user_state.is_disabled(claims.iss, claims.sub):
        reject("invalid_token")

    # Quyền hiện tại vẫn được áp dụng cho tài nguyên/hành động cụ thể.
    require_current_policy_allows(
        subject = claims.sub,
        action = request.action,
        resource = request.resource
    )

    return allow()
~~~

Các kiểm tra trạng thái chỉ có ý nghĩa nếu resource server thực sự thực hiện chúng và nguồn dữ liệu được bảo vệ. Trong thực tế cần xử lý cache, lỗi dependency, timeout và fail-open/fail-closed theo policy.

Không dùng jti, sid, iss hoặc sub từ token chưa xác minh để thực hiện tra cứu có tác động bảo mật. Có thể parse sơ bộ để chuẩn bị dữ liệu, nhưng chỉ sử dụng giá trị sau khi chữ ký và các điều kiện xác minh cần thiết đã thành công.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ rằng xóa refresh token sẽ thu hồi access JWT đã phát hành. | Access token cũ vẫn hoạt động đến exp nếu resource server không kiểm tra trạng thái. | Kết hợp access token ngắn hạn với denylist/version/introspection khi cần. |
| Chỉ đổi role trong database. | Claims role/scope trong JWT cũ không đổi. | Kiểm tra policy hiện tại hoặc tăng authz version/thu hồi token cũ. |
| Dùng denylist nhưng resource server không kiểm tra mỗi request. | Token đã thu hồi vẫn được chấp nhận. | Tích hợp check vào pipeline xác minh bắt buộc. |
| Lưu jti mà không namespace theo issuer. | Có nguy cơ va chạm giữa token của nhiều issuer. | Dùng cặp issuer+jti hoặc khóa tra cứu namespaced. |
| Cache trạng thái revocation quá lâu. | Revocation propagation chậm. | TTL theo SLA, invalidation và kiểm thử cache. |
| Thu hồi signing key cho một user đơn lẻ. | Ảnh hưởng toàn bộ token dùng key đó. | Dùng cơ chế revoke theo jti/session/user cho sự cố hẹp. |
| Chỉ xóa key khỏi JWKS. | Resource server có thể vẫn giữ key cũ trong cache. | Có key-revocation/purge path và giới hạn JWKS cache. |
| Tin rằng introspection cache luôn phản ánh trạng thái mới. | Token đã thu hồi vẫn active trong TTL cache. | Đặt TTL theo mức rủi ro và mục tiêu propagation. |
| Không phân biệt lỗi trạng thái với lỗi token. | Có thể fail-open ngoài ý muốn hoặc gây gián đoạn không cần thiết. | Định nghĩa fail policy cho từng nhóm endpoint. |
| Không thu hồi refresh token family sau replay. | Kẻ tấn công có thể tiếp tục xin access token mới. | Có rotation/reuse detection và family revocation. |
| Dùng iat đơn lẻ như token ID. | Nhiều token có thể cùng thời điểm phát hành. | Dùng jti cho định danh token; iat chỉ làm mốc thời gian. |
| Cho client tự quyết định version hoặc trạng thái revoke. | Người dùng có thể giả mạo trạng thái mới. | Trạng thái version/revocation chỉ do server quản lý. |

## 13. Ma trận kiểm thử revocation

| Tình huống | Kết quả mong đợi |
|---|---|
| JWT hợp lệ, chưa hết hạn, không có trạng thái revoke. | Chấp nhận nếu claims và policy cho phép. |
| jti nằm trong denylist. | Từ chối token đó. |
| jti của issuer khác có cùng chuỗi ký tự nhưng không cùng namespace. | Không thu hồi nhầm token khác issuer. |
| sid bị thu hồi. | Từ chối các token thuộc session đó. |
| authz_ver trong token thấp hơn version hiện tại. | Từ chối token cũ. |
| Tài khoản bị disabled. | Từ chối theo trạng thái hiện tại. |
| Role đã bị thu hồi nhưng token cũ vẫn chứa scope cũ. | Hành động nhạy cảm bị từ chối bởi policy hiện tại hoặc version check. |
| Refresh token bị thu hồi nhưng access token cũ còn hạn. | Access token chỉ bị chặn nếu có cơ chế kiểm tra revocation; nếu không, chỉ hết hạn tự nhiên. |
| Signing key bị thu hồi và trust cache đã cập nhật. | Token ký bằng key đó bị từ chối. |
| Signing key bị thu hồi nhưng một resource server còn cache cũ. | Test phải phát hiện propagation gap và không coi thu hồi đã hoàn tất. |
| Revocation store không khả dụng ở endpoint nhạy cảm fail-closed. | Request bị từ chối an toàn theo policy. |
| Introspection trả inactive. | Token bị từ chối. |
| Introspection cache còn active sau khi token bị revoke. | Thời gian tồn tại stale phải nằm trong SLA đã công bố; test xác nhận TTL/invalidation. |
| Token hợp lệ nhưng scope không cho phép hành động. | Từ chối authorization. |
| Người dùng đăng xuất một session nhưng còn session khác. | Chỉ session bị thu hồi bị chặn, nếu policy yêu cầu revoke theo session. |

## 14. Checklist thiết kế và vận hành

- [ ] Đã xác định phạm vi revoke: jti, session, user, client, tenant hay signing key.
- [ ] Access token có thời hạn phù hợp với mức rủi ro.
- [ ] Có chiến lược thu hồi cho token bị lộ hoặc quyền thay đổi khẩn cấp.
- [ ] jti được định danh trong namespace issuer.
- [ ] sid/session được quản lý và kiểm tra nếu dùng.
- [ ] Token version/authz version chỉ được quản lý phía server.
- [ ] Thu hồi refresh token được phân biệt với thu hồi access token.
- [ ] Có quy trình rotate/revoke signing key và purge trust cache.
- [ ] Cache TTL và propagation đáp ứng mục tiêu revocation.
- [ ] Đã xác định fail-open/fail-closed theo mức độ nhạy cảm.
- [ ] Resource server kiểm tra trạng thái trước khi thực hiện hành động cần bảo vệ.
- [ ] Quyền hiện tại được áp dụng cho thao tác nhạy cảm.
- [ ] Có runbook khẩn cấp, audit và kiểm thử end-to-end.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một JWT đã ký hợp lệ vẫn có thể chứa quyền không còn được phép?
2. Revocation window là gì và chịu ảnh hưởng bởi những yếu tố nào?
3. Khi nào nên dùng denylist theo jti thay vì token version?
4. Thu hồi theo sid khác thu hồi theo user như thế nào?
5. Vì sao tăng authz version có thể chặn nhiều token cùng lúc?
6. Tại sao thu hồi refresh token không tự động vô hiệu hóa access token đã phát hành?
7. Khi nào nên dùng token introspection?
8. Vì sao thu hồi signing key có phạm vi ảnh hưởng rộng?
9. Cache JWKS và revocation state có thể làm chậm hiệu lực thu hồi như thế nào?
10. Khi nào resource server nên fail-closed nếu không truy cập được kho revocation?
11. Vì sao thay đổi role trong database chưa đủ để làm mất scope cũ trong JWT?
12. Cần kiểm tra gì để xác nhận một lệnh revoke đã có hiệu lực trên toàn bộ resource server?

## 16. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): claims về issuer, subject, audience, expiration và JWT ID (jti, §4.1).
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): thu hồi access token và refresh token tại authorization server.
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): kiểm tra trạng thái active của token tại resource server.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): thực hành bảo mật khi xác minh JWT và kiểm soát claims.
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): profile JWT access token và các yêu cầu xác minh ở resource server.
