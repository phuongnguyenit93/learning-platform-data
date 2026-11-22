# Hạn chế thời gian tồn tại của dữ liệu đã đóng gói vào JWT

## 1. Vì sao dữ liệu trong JWT cần có thời hạn tồn tại ngắn?

JWT thường mang thông tin xác thực và một phần ngữ cảnh ủy quyền giữa client, API gateway và resource server. Vì token có thể được xác minh cục bộ mà không cần truy vấn trạng thái ở mỗi request, JWT thuận tiện cho hệ thống phân tán. Nhưng tính tự chứa này cũng tạo ra một vấn đề về dữ liệu: **mọi claim được đưa vào token trở thành một bản sao dữ liệu được phân phối tới các bên nhận token**.

Ví dụ access token chứa email, tên đầy đủ, tenant, danh sách role và thông tin hồ sơ. Sau khi token được phát hành, các dữ liệu đó có thể tồn tại trong trình duyệt hoặc thiết bị, request header qua proxy/gateway/service, cache, log, trace, hệ thống phát hiện lỗi, message queue, background job và bản sao lưu.

Khi người dùng sửa email, rời tenant, bị thu hồi quyền hoặc yêu cầu xóa dữ liệu, các bản sao đã được đóng gói vào JWT không tự biến mất. Claim `exp` giúp verifier ngừng chấp nhận token sau một thời điểm, nhưng không xóa nội dung token khỏi các nơi đã lưu.

Vì vậy, cần kiểm soát đồng thời **dữ liệu nào được đưa vào JWT** và **JWT được phép tồn tại, được chấp nhận trong bao lâu**. Mục tiêu là giảm dữ liệu cá nhân được sao chép, giảm thời gian một bản sao cũ còn có thể được sử dụng và giới hạn hậu quả khi token bị lộ.

Bài thuộc chương **Dữ liệu và riêng tư** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho JWT, OAuth 2.0 và hệ thống phân tán; không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Phân biệt thời hạn token với thời gian lưu giữ dữ liệu

### 2.1. Token lifetime

Token lifetime là khoảng thời gian verifier chấp nhận token theo các điều kiện thời gian, thường dựa trên:

- `iat`: thời điểm token được phát hành.
- `nbf`: thời điểm token bắt đầu có hiệu lực.
- `exp`: thời điểm token hết hạn.
- Clock skew: sai lệch đồng hồ được policy cho phép.

Với JWT, các giá trị thời gian NumericDate được biểu diễn theo giây từ Unix epoch. Verifier phải áp dụng policy thời gian nhất quán và không tự kéo dài thời hạn khi token bị từ chối.

### 2.2. Data retention

Data retention là thời gian một bản dữ liệu được lưu ở một hệ thống hoặc vị trí cụ thể. Ví dụ:

- Browser còn lưu cookie chứa JWT.
- Client còn lưu token trong secure storage.
- API gateway còn giữ request trong cache.
- Log platform còn lưu header hoặc payload.
- Backup còn giữ bản snapshot chứa token.

Các thời hạn này độc lập với `exp`. Token có thể hết hạn sau 5 phút nhưng bản sao token vẫn nằm trong log 90 ngày. Verifier có thể từ chối token đã hết hạn, nhưng dữ liệu cá nhân trong payload vẫn tồn tại ở log cho tới khi log được xóa theo retention policy.

### 2.3. Bốn khái niệm không được nhầm lẫn

| Khái niệm | Câu hỏi cần trả lời | Cơ chế điển hình |
| --- | --- | --- |
| Validity | Token có được chấp nhận tại thời điểm này không? | exp, nbf, chữ ký, issuer, audience, policy |
| Storage lifetime | Bản token còn được lưu ở đâu và bao lâu? | Cookie expiry, secure storage, cache TTL, log retention |
| Data freshness | Claims có còn phản ánh trạng thái hiện tại không? | Token TTL, introspection, version/epoch, policy lookup |
| Deletion | Các bản sao dữ liệu đã được xóa hoặc xử lý theo yêu cầu chưa? | Data lifecycle, log deletion, backup expiry, revocation |

Một hệ thống có thể có token lifetime ngắn nhưng data retention dài. Ngược lại, client có thể xóa token khỏi thiết bị nhưng server vẫn chấp nhận bản token bị đánh cắp cho tới `exp`. Cần thiết kế cả bốn khía cạnh.

## 3. JWT là bản sao dữ liệu được phân phối

### 3.1. Claims là snapshot tại thời điểm phát hành

Khi issuer tạo JWT, claims phản ánh dữ liệu và quyết định tại thời điểm phát hành. Nếu token có:

~~~json
{
  "sub": "user-42",
  "email": "user@example.com",
  "tenant_id": "tenant-7",
  "roles": ["manager"],
  "exp": 1760000300
}
~~~

thì email, tenant và role trong token là một snapshot. Nếu người dùng đổi email hoặc bị gỡ role sau đó, token cũ vẫn chứa giá trị cũ cho tới khi bị loại khỏi các nơi lưu hoặc hết thời hạn chấp nhận.

### 3.2. Token càng nhiều claim, càng nhiều bản sao

Một token thường được gửi trong nhiều request. Nếu token chứa 2 KB dữ liệu cá nhân và được gửi tới 10 service trong hàng trăm request, cùng một tập thông tin có thể được sao chép qua nhiều lớp hạ tầng.

Điều này làm tăng số nơi cần bảo vệ, khả năng dữ liệu xuất hiện trong log hoặc telemetry, chi phí xử lý yêu cầu truy cập/chỉnh sửa/xóa, tác động nếu token hoặc hệ thống trung gian bị lộ và khó khăn khi cần cập nhật thông tin nhanh chóng.

Giảm kích thước token là lợi ích phụ. Lý do chính là giảm dữ liệu cá nhân và quyền được phát tán.

### 3.3. JWT không phải hồ sơ người dùng

JWT nên mang thông tin tối thiểu để verifier xác định token có hợp lệ và request có được phép thực hiện hay không. Hồ sơ người dùng, địa chỉ, số điện thoại, thông tin thanh toán hoặc dữ liệu nghiệp vụ chi tiết nên được lưu ở hệ thống có trách nhiệm quản lý dữ liệu đó.

Nếu downstream cần một thuộc tính hồ sơ, hãy cân nhắc truy vấn nguồn dữ liệu có kiểm soát bằng một định danh subject đã xác minh. Không nhúng toàn bộ hồ sơ vào token chỉ để tránh một lần truy vấn.

## 4. Nguyên tắc data minimization cho JWT

### 4.1. Chỉ đưa claim thực sự cần thiết

Trước khi thêm một claim, trả lời:

1. Resource server nào cần claim này?
2. Claim được dùng để xác minh, phân quyền hay chỉ để hiển thị?
3. Có thể lấy dữ liệu từ nguồn có thẩm quyền khi cần không?
4. Claim có thay đổi thường xuyên không?
5. Nếu token bị lộ, claim này gây rủi ro gì?
6. Claim cần tồn tại trong toàn bộ thời hạn token hay chỉ trong một request?

Nếu claim chỉ phục vụ giao diện, analytics hoặc hiển thị tên, thường không cần đưa vào access token.

### 4.2. Phân loại claim theo mục đích

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Định danh subject | sub | Dùng định danh ổn định, hạn chế khả năng suy ra danh tính trực tiếp |
| Nguồn và đích token | iss, aud | Cần cho trust validation; giữ chính xác và tối thiểu |
| Thời gian và định danh token | iat, exp, nbf, jti | Dùng cho validity, replay, audit theo policy |
| Quyền truy cập | scope, permission cần thiết | Chỉ cấp quyền cho resource và thời gian cần thiết |
| Ngữ cảnh tenant | tenant identifier | Chỉ đưa vào nếu resource cần và được xác minh |
| Hồ sơ cá nhân | email, tên, điện thoại, địa chỉ | Thường không đưa vào access token |
| Dữ liệu nhạy cảm | mật khẩu, secret, dữ liệu tài chính/đặc biệt | Không đưa vào bearer JWT thông thường |
| Dữ liệu hiển thị | avatar URL, display name, locale | Lấy từ profile API hoặc cache phù hợp |
| Dữ liệu vận hành | trace ID, debug flags | Truyền qua observability context, không dùng làm quyền |

### 4.3. Claims chuẩn không có nghĩa là bắt buộc phải có

JWT định nghĩa các registered claims như iss, sub, aud, exp, nbf, iat và jti. Việc một claim có tên chuẩn không có nghĩa mọi token đều phải chứa claim đó hoặc phải đưa thêm thông tin cá nhân vào token.

Issuer và resource server cần thống nhất token profile. Chỉ phát hành các claim bắt buộc theo profile và policy; không sao chép mọi thuộc tính của user object vào payload.

### 4.4. Tránh claim chứa cấu trúc lớn

Không nhúng toàn bộ danh sách role hoặc ACL của hàng nghìn resource, danh sách nhóm người dùng lớn, hồ sơ đầy đủ hoặc dữ liệu lịch sử, danh sách đơn hàng/sản phẩm/giao dịch hay JSON tùy ý từ database.

Thay vào đó, dùng scope/permission gọn cho chức năng, rồi thực hiện object-level authorization tại resource server. Nếu policy quá động hoặc danh sách quyền quá lớn, cân nhắc introspection hoặc authorization service.

## 5. Dữ liệu cá nhân và dữ liệu nhạy cảm không nên nằm trong JWT

### 5.1. Không đưa secret hoặc credential vào claims

Không đưa password hoặc password hash, API key/client secret/refresh secret, private key/seed/recovery code, session cookie/bearer token khác, credential của database/cloud hoặc hệ thống nội bộ vào payload JWT.

JWT được ký không có nghĩa payload bí mật. Một JWS thông thường chỉ bảo vệ tính toàn vẹn và nguồn phát hành; bất kỳ bên nào có token đều có thể giải mã Base64URL để đọc header và payload.

### 5.2. Hạn chế dữ liệu định danh trực tiếp

Các thuộc tính như email, số điện thoại, họ tên, địa chỉ nhà, ngày sinh hoặc mã nhân viên có thể làm tăng khả năng nhận diện và liên kết dữ liệu. Nếu resource server chỉ cần biết subject, dùng một identifier phù hợp thay cho hồ sơ cá nhân.

Không đưa dữ liệu cá nhân vào token chỉ vì nó tiện cho việc log hoặc hiển thị.

### 5.3. Dữ liệu đặc biệt nhạy cảm

Thông tin sức khỏe, sinh trắc học, tài chính, vị trí chính xác hoặc dữ liệu nhạy cảm khác cần được xử lý theo threat model và nghĩa vụ pháp lý áp dụng. Bearer JWT thường được truyền qua nhiều hệ thống nên không phải nơi lưu trữ phù hợp cho loại dữ liệu này.

Nếu một nghiệp vụ thực sự cần sử dụng dữ liệu nhạy cảm, hãy lấy dữ liệu từ hệ thống chuyên trách qua một luồng được xác thực và phân quyền riêng, chỉ trả về kết quả tối thiểu cần thiết.

### 5.4. Pseudonymization không phải anonymization

Một `sub` dạng `usr_8f3...` có thể giảm việc lộ tên hoặc email, nhưng nếu có thể liên kết nó với một người thông qua dữ liệu khác thì đó vẫn có thể là dữ liệu cá nhân.

Định danh giả danh giúp giảm lộ trực tiếp, không biến dữ liệu thành vô danh. Cần kiểm soát khả năng liên kết, quyền truy cập bảng ánh xạ và thời gian lưu identifier.

## 6. Thiết kế subject identifier để giảm liên kết dữ liệu

### 6.1. Tránh dùng email làm subject

Email có thể thay đổi, thường được dùng ở nhiều dịch vụ và dễ liên kết hoạt động của cùng một người. Nếu dùng email làm sub, mọi resource nhận token có thể nhìn thấy cùng một định danh trực tiếp.

Ưu tiên subject identifier ổn định trong phạm vi issuer và phù hợp với mục đích sử dụng. Không mặc định rằng subject phải là username hoặc email.

### 6.2. Pairwise subject identifier

Trong các hệ thống có nhiều client hoặc resource domain, pairwise identifier có thể giúp hạn chế việc các bên liên kết cùng một người qua các dịch vụ khác nhau.

~~~text
Same person:
  subject for app-A = pairwise-id-A
  subject for app-B = pairwise-id-B
  subject for app-C = pairwise-id-C
~~~

Issuer giữ cơ chế ánh xạ nội bộ và chỉ cung cấp identifier phù hợp cho từng client/sector theo policy. Pairwise identifier không thay thế authorization; nó chỉ giảm khả năng liên kết chéo.

### 6.3. Không tự băm email để tạo subject

Hash email không tự động tạo identifier an toàn vì email có entropy thấp và attacker có thể dò dictionary. Nếu cần identifier giả danh, dùng ID ngẫu nhiên hoặc cơ chế keyed derivation được thiết kế, quản lý khóa và rotation rõ ràng.

Không đưa thông tin có thể đảo ngược hoặc đoán được vào claim chỉ dưới dạng hash rồi coi là dữ liệu vô danh.

### 6.4. Tenant và subject

Trong hệ thống multi-tenant, subject có thể có quyền khác nhau theo tenant. Chỉ đưa tenant context vào token khi cần cho resource server và tenant đó đã được xác minh tại thời điểm phát hành.

Không dùng một sub hoặc tenant_id do client tự khai báo. Resource server vẫn phải kiểm tra resource có thuộc tenant được token đại diện hay không.

## 7. Chọn thời hạn token theo độ nhạy của dữ liệu và quyền

### 7.1. TTL là giới hạn thời gian chấp nhận một snapshot

Khi token chứa claims cá nhân hoặc quyền có thể thay đổi, TTL càng dài thì snapshot cũ càng có thể được sử dụng lâu. TTL ngắn giảm khoảng thời gian token cũ được chấp nhận, nhưng không xóa bản sao dữ liệu.

TTL nên dựa trên độ nhạy của claims, mức độ nguy hiểm nếu token bị đánh cắp, tần suất thay đổi quyền và trạng thái người dùng, khả năng thu hồi hoặc introspection, số lượng resource server nhận token, độ trễ/khả năng chịu lỗi của hệ thống xác minh và thời gian nghiệp vụ thực sự cần token.

### 7.2. Không có một TTL phù hợp cho mọi access token

Ví dụ dưới đây chỉ minh họa các mức cân nhắc, không phải giá trị chuẩn:

| Loại token/ngữ cảnh | Hướng TTL | Lý do |
| --- | --- | --- |
| Access token cho thao tác nhạy cảm | Rất ngắn theo nhu cầu nghiệp vụ | Giảm cửa sổ sử dụng khi bị lộ |
| Access token API thông thường | Ngắn, cân bằng tải và trải nghiệm | Giới hạn độ cũ của claims |
| Token nội bộ service-to-service | Ngắn và gắn audience cụ thể | Hạn chế lateral movement |
| Token cho job bất đồng bộ | Chỉ đủ cho bước thực thi hoặc lấy mới khi cần | Không lưu bearer token dài hạn trong queue |
| Refresh token | Có thời hạn dài hơn access token nhưng phải có rotation/revocation policy | Duy trì phiên mà vẫn kiểm soát reuse |

Đừng chọn TTL dài chỉ để giảm số lần refresh. Nếu phải kéo dài token để hệ thống hoạt động, cần xem lại caching, refresh flow hoặc availability của authorization service.

### 7.3. Clock skew không phải cách gia hạn token

Một khoảng clock skew nhỏ có thể cần để xử lý sai lệch đồng hồ giữa issuer và verifier. Không dùng leeway lớn để bù cho token lifetime quá ngắn hoặc hệ thống đồng hồ không được quản lý.

Clock skew chỉ là dung sai kiểm tra thời gian; nó không thay đổi thời điểm dữ liệu được tạo, không làm claims mới hơn và không xóa token.

### 7.4. Thời hạn token không nên vượt quá thời hạn nguồn

Nếu access token được phát hành dựa trên một phiên hoặc một delegation có thời hạn, policy cần giới hạn token mới theo thời hạn còn lại của credential nguồn và thời hạn tối đa của phiên. Không để token downstream tiếp tục cấp quyền sau khi delegation đã hết hiệu lực theo policy.

## 8. Access token, refresh token và lượng dữ liệu cần mang

### 8.1. Access token mang claims tối thiểu

Access token nên chứa thông tin resource server cần để xác minh và quyết định truy cập: issuer, subject identifier, audience, thời gian, token identifier và scope/permission cần thiết theo profile.

Không đưa toàn bộ hồ sơ user vào access token chỉ vì token được gửi tới mọi API.

### 8.2. Refresh token nên mang ít thông tin hơn

Refresh token chủ yếu đại diện khả năng yêu cầu cấp token mới. Nó không cần mang profile người dùng hoặc toàn bộ quyền. Một refresh token opaque ngẫu nhiên, high-entropy, được quản lý trạng thái phía server thường giúp giảm dữ liệu cá nhân trong credential.

Nếu dùng refresh JWT, giữ claims tối thiểu như issuer, subject identifier phù hợp, audience/client, thời hạn, token ID và session/family reference cần thiết. Trạng thái rotation và reuse vẫn cần được quản lý theo policy.

### 8.3. Không dùng refresh token làm access token

Refresh token có mục đích và audience riêng. Resource server không được chấp nhận refresh token như bearer access token chỉ vì chữ ký hợp lệ. Tách token type, audience và validation policy để tránh nhầm lẫn.

### 8.4. Token exchange có thể giảm bản sao dữ liệu

Thay vì chuyển tiếp một user token chứa nhiều claims qua mọi dịch vụ, token exchange có thể tạo token downstream với audience chỉ dành cho service nhận, scope tối thiểu cho operation, subject identifier phù hợp, actor context cần cho audit, thời hạn ngắn hơn và không có claims hồ sơ không cần thiết.

Token exchange không tự xóa token nguồn; nó chỉ giúp giới hạn dữ liệu và quyền trong token mới.

## 9. Claims thay đổi thường xuyên và vấn đề freshness

### 9.1. Role và permission trong token có thể lỗi thời

Nếu token chứa `roles=["admin"]`, người dùng bị gỡ quyền admin sau khi token phát hành, token cũ vẫn mang claim đó. Resource server xác minh chữ ký thành công nhưng có thể đưa ra quyết định dựa trên trạng thái cũ.

Với quyền thay đổi thường xuyên hoặc có tác động lớn, cân nhắc TTL ngắn, introspection hoặc authorization lookup, session version/authorization epoch, denylist hoặc revocation event và kiểm tra object-level permission tại thời điểm thao tác.

### 9.2. Dữ liệu hồ sơ không nên được dùng như quyền

Claim `department`, `email_verified`, `plan`, `country` hoặc `account_status` có thể là dữ liệu snapshot. Không biến chúng thành quyền truy cập nếu policy yêu cầu trạng thái mới nhất.

Ví dụ, `account_status=active` trong token không chứng minh tài khoản vẫn active sau khi token được phát hành. Với thao tác nhạy cảm, kiểm tra trạng thái tại nguồn có thẩm quyền hoặc dùng cơ chế version/revocation.

### 9.3. Version hoặc epoch

Issuer có thể duy trì session version hoặc authorization epoch. Token mang version tại thời điểm phát hành; resource server so sánh với version hiện tại được cung cấp bởi nguồn trạng thái tin cậy.

~~~text
Token:
  sub = user-42
  authz_epoch = 18

Current user/session state:
  authz_epoch = 19

Decision:
  token version is stale -> reject or re-evaluate
~~~

Version claim không tự hoạt động nếu không có nơi lưu version hiện tại và quy tắc so sánh. Nếu cache version, TTL cache cũng ảnh hưởng thời gian quyền cũ còn được chấp nhận.

### 9.4. Claim iat không chứng minh dữ liệu còn mới

`iat` chỉ cho biết thời điểm token được phát hành. Nó không chứng minh profile hoặc quyền chưa thay đổi kể từ lúc đó. Cần xác định freshness theo từng loại claim và policy.

## 10. Revocation và giới hạn thời gian chấp nhận dữ liệu cũ

### 10.1. JWT stateless khó thu hồi tức thì

Nếu resource server chỉ xác minh chữ ký và claims cục bộ, một JWT đã phát hành thường tiếp tục hợp lệ cho tới `exp`, trừ khi có thêm trạng thái thu hồi hoặc policy khác.

Xóa session ở identity provider không tự động làm mọi resource server biết token đã bị thu hồi. Cần xác định rõ thời gian tối đa mà token cũ có thể được chấp nhận.

### 10.2. Các lựa chọn

| Cơ chế | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Short-lived access token | Token hết hạn nhanh | Tăng tần suất refresh |
| Introspection | Resource hỏi authorization server về trạng thái token | Tăng dependency và độ trễ |
| Denylist theo jti | Từ chối token ID đã bị thu hồi | Cần lưu/truyền trạng thái và dọn dữ liệu |
| Session/authz epoch | So sánh version trong token với version hiện tại | Cần tra cứu hoặc cache version |
| Revocation event | Phân phối thay đổi tới resource server | Cần bảo đảm event delivery và cache invalidation |

Có thể kết hợp nhiều cơ chế. Chọn theo mức độ cần thu hồi tức thì, quy mô hệ thống và khả năng chịu lỗi.

### 10.3. Denylist cũng có retention

Một denylist không cần giữ token ID vô hạn nếu token đã hết hạn và không còn được chấp nhận. Có thể đặt retention của entry tới thời điểm token hết hạn cộng dung sai cần thiết.

Lưu hash hoặc fingerprint của `jti` nếu phù hợp, hạn chế dữ liệu kèm theo và bảo vệ quyền truy cập. Không đưa raw JWT vào denylist chỉ để thuận tiện tra cứu.

### 10.4. Revocation không phải deletion

Revocation làm token không còn được chấp nhận theo policy. Nó không xóa token khỏi browser, log, queue, backup hoặc thiết bị đã nhận. Deletion cần quy trình riêng cho từng nơi lưu dữ liệu.

## 11. JWS, JWE và quyền riêng tư của payload

### 11.1. JWS ký không đồng nghĩa với mã hóa

JWS bảo vệ tính toàn vẹn và xác thực nguồn phát hành theo thuật toán/chính sách xác minh. Payload JWS thông thường được mã hóa Base64URL, không được mã hóa bí mật. Bất kỳ bên nào có token đều có thể đọc claims.

Không đặt dữ liệu bí mật trong JWS chỉ vì token có chữ ký.

### 11.2. JWE cung cấp confidentiality nhưng không xóa rủi ro retention

JWE mã hóa nội dung cho recipient có khóa phù hợp. Điều này hạn chế bên trung gian đọc payload nếu họ không có khóa giải mã.

Tuy nhiên:

- Recipient vẫn có thể giải mã và sao chép plaintext.
- Token vẫn có thể được lưu trong log hoặc queue.
- Header và metadata có thể để lộ một phần thông tin tùy serialization/profile.
- Token bị đánh cắp vẫn có thể được sử dụng nếu attacker có khả năng giải mã hoặc token bị lộ ở nơi đã giải mã.
- `exp` vẫn không xóa ciphertext hoặc plaintext copies.

JWE là biện pháp bảo mật nội dung, không phải chính sách data retention.

### 11.3. Mã hóa không thay thế data minimization

Nếu một claim không cần thiết, mã hóa claim đó không làm cho việc thu thập và phân phối trở nên cần thiết. Hãy giảm dữ liệu trước, sau đó áp dụng chữ ký, mã hóa và kiểm soát truy cập phù hợp cho phần còn lại.

### 11.4. Nested JWT

Một nested JWT có thể kết hợp JWS và JWE, ví dụ ký nội dung rồi mã hóa. Điều này có thể bảo vệ tính toàn vẹn và tính bí mật theo thiết kế, nhưng làm tăng độ phức tạp về key management, recipient và xử lý lỗi.

Nested JWT không phải lý do để nhúng thêm hồ sơ hoặc giữ token lâu hơn nhu cầu.

## 12. Cache, proxy, gateway và các bản sao trung gian

### 12.1. Authorization header có thể đi qua nhiều lớp

Access token trong header `Authorization: Bearer` có thể được chuyển qua client, CDN, reverse proxy, API gateway, service mesh và nhiều service. Mỗi lớp cần có chính sách xử lý credential.

### 12.2. Không cache response chứa token hoặc dữ liệu nhạy cảm một cách tùy tiện

Với response cấp token hoặc dữ liệu xác thực, cân nhắc header cache phù hợp, thường là `Cache-Control: no-store` theo hợp đồng và threat model. Không để shared cache lưu response token rồi trả cho người dùng khác.

Không phải mọi API response đều cần `no-store`; quyết định dựa trên nội dung và chính sách cache. Nhưng token endpoint cần đặc biệt tránh cache credential.

### 12.3. Không log token

Tắt hoặc redact các trường:

- `Authorization`.
- `Cookie` chứa credential.
- `Set-Cookie` chứa token.
- Request/response body của token endpoint.
- Query parameter có chứa credential.

Redaction phải áp dụng ở mọi lớp: application logger, gateway, reverse proxy, APM, error tracker và packet/debug tooling.

### 12.4. Cache claims và cache authorization

Nếu service cache kết quả introspection hoặc user permissions, TTL của cache tạo ra một khoảng thời gian dữ liệu cũ vẫn được dùng. Cần đặt TTL theo mức nhạy cảm và khả năng chấp nhận stale authorization.

Không cache dữ liệu cá nhân lâu hơn nhu cầu chỉ vì cache giúp giảm latency. Có thể cache định danh hoặc kết quả tối thiểu, có TTL và invalidation phù hợp.

## 13. Lưu trữ ở client và thiết bị

### 13.1. Browser storage

Token ở browser có thể tồn tại trong cookie, memory, session storage hoặc local storage. Mỗi lựa chọn có đặc tính bảo mật và vòng đời khác nhau:

- HttpOnly cookie giảm khả năng JavaScript đọc trực tiếp nhưng tự động gửi cookie nên cần CSRF protection.
- Memory có thể mất khi reload/tab đóng, nhưng vẫn có thể bị mã độc cùng origin sử dụng trong phiên.
- Session storage gắn với tab/session browser và vẫn có thể bị JavaScript cùng origin đọc.
- Local storage tồn tại lâu hơn và dễ bị JavaScript cùng origin đọc; không nên dùng để giữ credential dài hạn nếu không có lý do và threat model rõ.

Chọn nơi lưu theo kiến trúc, XSS/CSRF threat model và yêu cầu trải nghiệm. Không coi xóa token ở client là thay thế revocation phía server.

### 13.2. Mobile và desktop

Nếu ứng dụng cần lưu credential qua lần khởi động, dùng secure storage do nền tảng cung cấp và hạn chế thời gian giữ token. Không ghi token vào file cấu hình, crash dump, clipboard, notification, analytics hoặc log.

Khi logout, xóa credential khỏi secure storage và gọi revocation endpoint nếu hệ thống hỗ trợ. Việc xóa local không thu hồi bản sao token đã bị lấy trước đó.

### 13.3. Device backup và synchronization

Một số hệ điều hành có thể sao lưu hoặc đồng bộ dữ liệu ứng dụng. Xác định credential có được backup hay không, có được restore sang thiết bị khác hay không và chính sách xóa khi thiết bị bị thu hồi.

Không để token có quyền cao được đồng bộ qua một nơi lưu trữ không có cùng mức bảo vệ.

## 14. Queue, background job và dữ liệu token tồn tại lâu

### 14.1. Không đưa bearer token dài hạn vào message

Message queue có thể giữ message nhiều giờ hoặc nhiều ngày, retry nhiều lần và lưu dead-letter message. Nếu message chứa access token hoặc refresh token, credential có thể tồn tại lâu hơn token lifetime dự kiến và lan sang nhiều hệ thống.

Ưu tiên message mang business reference và context tối thiểu:

~~~json
{
  "event_id": "evt-1001",
  "subject_ref": "subject-pairwise-42",
  "tenant_ref": "tenant-7",
  "resource_id": "order-900",
  "action": "reserve-inventory",
  "correlation_id": "trace-abc"
}
~~~

Các trường này vẫn cần được xác thực nguồn gốc và kiểm tra policy; chúng không tự là credential.

### 14.2. Worker lấy quyền tại thời điểm thực thi

Khi worker xử lý message, nó có thể xác thực bằng workload identity rồi lấy credential ngắn hạn cho đúng audience và action. Nếu cần giữ quyền người dùng, authorization server phải xác minh delegation assertion hoặc context đã được bảo vệ theo policy.

Không giả định quyền của user tại thời điểm tạo job vẫn còn nguyên khi worker thực thi. Với thao tác nhạy cảm, có thể cần đánh giá lại trạng thái account, tenant và permission.

### 14.3. Dead-letter queue và retry storage

Dead-letter queue, retry topic và failed job store cũng là nơi lưu dữ liệu. Áp dụng:

- Không chứa raw JWT hoặc refresh token nếu không cần.
- Mã hóa dữ liệu queue theo yêu cầu.
- Giới hạn retention và quyền truy cập.
- Redact payload trong dashboard và log.
- Có quy trình xóa hoặc xử lý message hết hạn.
- Không replay một message cũ mà bỏ qua authorization hiện tại.

## 15. Xóa dữ liệu, logout và yêu cầu quyền riêng tư

### 15.1. Xóa profile không tự xóa JWT đã phát hành

Khi user xóa tài khoản hoặc cập nhật dữ liệu:

- Token đang nằm trên thiết bị vẫn có thể chứa claims cũ.
- Resource server có thể tiếp tục chấp nhận token tới `exp`.
- Log và telemetry có thể còn bản sao token hoặc claims.
- Backup và queue có thể còn dữ liệu đã sao chép.

Vì vậy, quy trình xóa dữ liệu phải xác định các hệ thống đã nhận bản sao và chính sách retention của từng nơi.

### 15.2. Logout

Logout thường cần kết hợp:

1. Xóa cookie hoặc credential phía client.
2. Thu hồi refresh token/session phía server.
3. Thu hồi hoặc vô hiệu hóa token theo cơ chế mà resource server hỗ trợ.
4. Xóa cache/session state phù hợp.
5. Tránh ghi token vào log trong quá trình logout.

Với access JWT stateless, token có thể còn được chấp nhận tới `exp` nếu không có revocation check. UI báo logout thành công không tự chứng minh mọi bản sao token đã bị vô hiệu.

### 15.3. Yêu cầu xóa dữ liệu cá nhân

Nếu một claim chứa dữ liệu cá nhân và người dùng yêu cầu xóa, cần xác định token nào đã được phát hành và còn hiệu lực, có thể thu hồi token/session liên quan không, log có chứa claim hoặc token không, cache/queue/analytics/backup có bản sao không, thời hạn xóa hoặc ẩn danh theo policy và luật áp dụng là gì, và có ngoại lệ lưu giữ hợp pháp hoặc yêu cầu kiểm toán nào không.

Không hứa xóa ngay mọi bản sao nếu hệ thống backup hoặc log có retention khác. Hãy xác định và thực thi lifecycle đã công bố, có audit kết quả.

### 15.4. Retention có giới hạn và mục đích

Đối với từng bản dữ liệu, xác định mục đích, owner, nơi lưu, thời hạn, điều kiện xóa và ngoại lệ. Khi mục đích kết thúc, dữ liệu cần được xóa, ẩn danh hoặc xử lý theo policy phù hợp.

Các nguyên tắc data minimization và storage limitation xuất hiện trong nhiều khung bảo vệ dữ liệu, nhưng nghĩa vụ cụ thể phụ thuộc khu vực pháp lý, loại dữ liệu và vai trò tổ chức. Cần phối hợp với bộ phận privacy/legal khi xác định nghĩa vụ áp dụng.

## 16. Chiến lược thiết kế để giảm thời gian dữ liệu tồn tại trong JWT

### 16.1. Access token nhỏ và ngắn hạn

Phát hành access token chỉ gồm claims xác minh và quyền cần thiết, với TTL ngắn theo mức rủi ro. Dữ liệu hồ sơ lấy từ profile service khi cần.

### 16.2. Opaque reference thay cho dữ liệu lớn

Thay vì nhúng danh sách quyền hoặc hồ sơ lớn, token có thể mang subject/reference ID. Resource server truy vấn authorization service hoặc data service có thẩm quyền để lấy quyết định/dữ liệu tối thiểu.

Pattern này tăng dependency online nhưng giúp dữ liệu cập nhật và xóa tập trung hơn.

### 16.3. Token exchange theo resource

Mỗi service nhận token có audience và scope riêng. Token downstream không cần mang mọi claims của token nguồn. Authorization server chỉ phát hành dữ liệu cần thiết cho resource đích.

### 16.4. Claims động được kiểm tra ngoài token

Với role, account status, membership hoặc quyền thay đổi thường xuyên, dùng introspection, epoch/version hoặc policy decision point. JWT giữ thông tin định danh tối thiểu; trạng thái động được kiểm tra theo yêu cầu.

### 16.5. Pseudonymous subject

Dùng identifier không trực tiếp tiết lộ email/tên, có phạm vi theo client/resource khi phù hợp. Bảo vệ bảng ánh xạ và hạn chế khả năng liên kết giữa các hệ thống.

### 16.6. Không lưu token trong telemetry

Redact credential ở gateway, service, APM và error tracker. Log token ID/fingerprint đã được xử lý an toàn nếu thực sự cần điều tra, thay vì raw token.

## 17. Quy trình phát hành và xác minh JWT có xét tới retention

### 17.1. Trước khi phát hành

~~~text
function issueAccessToken(subject, resource, requestedScopes):
    policy = loadTokenPolicy(resource)
    require policy is valid

    permissions = evaluateCurrentPermissions(subject, resource)
    scopes = intersect(
        requestedScopes,
        permissions,
        policy.allowedScopes
    )

    claims = {
        iss: configuredIssuer,
        sub: minimalSubjectIdentifier(subject, resource),
        aud: resource,
        scope: scopes,
        iat: now,
        exp: now + policy.shortLifetime,
        jti: randomTokenIdentifier()
    }

    claims = removeUnnecessaryClaims(claims)
    assert noSecretsOrUnneededPersonalData(claims)

    token = signAccordingToApprovedProfile(claims)
    return token
~~~

Điểm quan trọng là chọn claims trước khi ký. Không tạo token chứa hồ sơ đầy đủ rồi trông chờ mã hóa hoặc thời hạn ngắn giải quyết vấn đề.

### 17.2. Khi xác minh

~~~text
function authorize(token, resource, action):
    parsed = strictParse(token)
    require verifySignatureAndAllowedAlgorithm(parsed)
    require parsed.iss is trusted
    require resource in parsed.aud
    require now < parsed.exp
    require parsed.nbf is absent or now >= parsed.nbf

    require tokenProfileIsExpected(parsed)
    require requiredScope(parsed, action)

    if policy.requiresFreshAuthorization:
        require currentSessionOrAuthorizationState(parsed)

    require objectAndTenantPolicy(parsed.sub, resource, action)
    return ALLOW
~~~

Verifier phải xác minh chữ ký và claims trước khi sử dụng dữ liệu. Nếu quyền hoặc account status phải mới tại thời điểm request, cần kiểm tra nguồn trạng thái hiện tại thay vì tin snapshot trong JWT.

### 17.3. Xử lý khi dữ liệu trong claim thay đổi

~~~text
onSensitiveAttributeChanged(subject):
    increment subject authorization/data version
    revoke affected refresh sessions when policy requires
    publish invalidation event
    clear relevant caches
    identify active tokens with stale claims
    rely on short exp or online state check to reject them
    apply log/cache/queue retention and deletion policy
~~~

Việc tăng version hoặc thu hồi session chỉ là một phần của xử lý. Các resource server phải thực sự kiểm tra version/event hoặc chờ token hết hạn theo giới hạn đã công bố.

## 18. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Đưa toàn bộ user profile vào JWT | Muốn giảm API lookup | Dữ liệu cá nhân bị sao chép rộng | Chỉ giữ subject và claims cần thiết |
| Dùng email làm sub | Tiện cho log và tra cứu | Dễ liên kết và lộ định danh | Dùng subject identifier phù hợp |
| Nghĩ JWS đã mã hóa payload | Nhầm ký với mã hóa | Bên giữ token đọc được claims | Dùng JWE khi thật sự cần confidentiality, đồng thời giảm dữ liệu |
| Nghĩ JWE giải quyết retention | Chỉ quan tâm ciphertext | Recipient vẫn có plaintext và bản sao | Có lifecycle/retention policy riêng |
| TTL dài để giảm refresh | Ưu tiên tiện dụng | Claims cũ và bearer exposure kéo dài | TTL theo risk, tối ưu refresh flow |
| exp được coi là xóa dữ liệu | Nhầm validity với deletion | Token vẫn nằm trong log/cache/backup | Quản lý storage retention riêng |
| Role trong token không được cập nhật | Snapshot cũ | Quyền đã thu hồi vẫn được dùng | TTL ngắn, epoch hoặc introspection |
| Log Authorization header | Debug mặc định | Lộ bearer token và claims | Redact ở mọi lớp |
| Queue chứa refresh token | Muốn worker dùng lại | Credential tồn tại lâu và lan rộng | Message mang business reference, worker lấy token mới |
| Chỉ xóa token ở client khi logout | Bỏ qua server state | Token bị đánh cắp vẫn có thể dùng | Revoke session/refresh và giới hạn access TTL |
| Hash email được coi là anonymous | Bỏ qua dictionary attack | Có thể suy ra email | Dùng random/pairwise identifier hoặc keyed derivation |
| Denylist lưu vô hạn | Không có cleanup | Lưu dữ liệu token dư thừa | Retention theo exp và policy |
| Cache quyền quá lâu | Tối ưu latency | Quyền cũ còn hiệu lực | TTL/invalidation theo độ nhạy |
| Không xử lý backup/telemetry | Chỉ xét database chính | Bản sao vẫn tồn tại | Lập inventory nơi lưu và retention |

## 19. Checklist thiết kế và vận hành

### 19.1. Claims và data minimization

- [ ] Mỗi claim có mục đích và consumer cụ thể.
- [ ] Không nhúng password, secret, private key hoặc credential.
- [ ] Không nhúng hồ sơ cá nhân nếu resource không cần.
- [ ] Subject identifier hạn chế khả năng suy ra danh tính và liên kết chéo.
- [ ] Không đưa ACL hoặc danh sách nghiệp vụ lớn vào token.
- [ ] Claims động có freshness/revocation strategy.

### 19.2. Lifetime và validity

- [ ] TTL dựa trên độ nhạy dữ liệu, quyền và threat model.
- [ ] Access token ngắn hạn theo nhu cầu.
- [ ] Refresh token có rotation/revocation policy và mang dữ liệu tối thiểu.
- [ ] exp, nbf, iat được kiểm tra đúng semantics.
- [ ] Clock skew nhỏ, có giới hạn và được giám sát.
- [ ] Token downstream không tồn tại lâu hơn delegation policy.

### 19.3. Storage và propagation

- [ ] Không log raw JWT, Authorization, Cookie hoặc Set-Cookie.
- [ ] Gateway, proxy, APM và error tracker có redaction.
- [ ] Token endpoint response không bị shared cache lưu.
- [ ] Client storage được chọn theo XSS/CSRF threat model.
- [ ] Queue/job không lưu bearer token dài hạn nếu không cần.
- [ ] Cache claims/permissions có TTL và invalidation phù hợp.
- [ ] Backup và archive có retention/deletion policy.

### 19.4. Revocation và deletion

- [ ] Có thời gian tối đa xác định cho token cũ còn được chấp nhận.
- [ ] Có cơ chế revoke phù hợp với yêu cầu nghiệp vụ.
- [ ] Revocation được phân biệt với deletion.
- [ ] Logout xử lý client credential và server session.
- [ ] Có quy trình khi dữ liệu cá nhân thay đổi hoặc cần xóa.
- [ ] Log, queue, cache và backup được xem xét trong data lifecycle.

## 20. Kiểm thử privacy và retention

### 20.1. Kiểm thử nội dung token

- Giải mã payload của token test và kiểm tra không có email, số điện thoại, địa chỉ hoặc profile ngoài policy.
- Kiểm tra không có password, secret, key material hoặc credential khác.
- Kiểm tra scope và tenant chỉ chứa thông tin resource cần.
- Kiểm tra token không chứa ACL hoặc JSON nghiệp vụ lớn.
- Kiểm tra subject identifier không để lộ định danh trực tiếp ngoài yêu cầu.

### 20.2. Kiểm thử lifetime

- Token bị từ chối sau exp theo clock skew đã cấu hình.
- Token chưa tới nbf bị từ chối.
- Thay đổi quyền hoặc account status kích hoạt cơ chế freshness/revocation theo policy.
- Cache không tiếp tục dùng claims sau TTL hoặc invalidation bắt buộc.
- Exchanged token không vượt thời hạn delegation được phép.

### 20.3. Kiểm thử leakage

- Gửi request qua gateway và xác nhận Authorization/Cookie không xuất hiện trong log.
- Kiểm tra error tracker và APM không lưu raw token.
- Kiểm tra token endpoint response có cache directive phù hợp.
- Kiểm tra queue, dead-letter queue và retry store không chứa bearer token không cần thiết.
- Kiểm tra crash report, debug dump và analytics không chứa credential.

### 20.4. Kiểm thử deletion và revocation

- Logout thu hồi refresh session theo policy.
- Token bị revoke không được chấp nhận ở resource server có hỗ trợ revocation.
- Token stateless còn hiệu lực có thời gian tồn tại tối đa được xác định rõ.
- Xóa/cập nhật profile không khiến token cũ được tin vô hạn.
- Quy trình xóa dữ liệu xác định được log, cache, queue và backup liên quan.
- Denylist entry được dọn sau khi token không còn có thể được chấp nhận.

## 21. Những hiểu lầm phổ biến

**“JWT hết hạn thì dữ liệu trong JWT cũng bị xóa.”** Sai. exp chỉ giới hạn việc chấp nhận token; bản sao vẫn có thể tồn tại trong thiết bị, log, cache hoặc backup.

**“JWS an toàn để chứa dữ liệu cá nhân vì payload đã được ký.”** Sai. Chữ ký không mã hóa payload.

**“Dùng JWE thì có thể đưa mọi dữ liệu nhạy cảm vào token.”** Sai. Recipient vẫn đọc và sao chép plaintext; data minimization vẫn cần thiết.

**“TTL càng ngắn thì không cần quan tâm log.”** Sai. Token hết hạn không xóa log chứa token.

**“iat mới nghĩa là mọi claim đều mới.”** Sai. iat chỉ là thời điểm phát hành; dữ liệu nguồn có thể đã thay đổi hoặc được đồng bộ sai.

**“Hash email là dữ liệu vô danh.”** Sai. Email có thể bị dò từ không gian giá trị nhỏ; hash không tự loại bỏ khả năng liên kết.

**“Thu hồi refresh token làm access JWT mất hiệu lực ngay.”** Không nhất thiết. Resource server stateless có thể tiếp tục chấp nhận access token tới exp.

**“Đưa role và ACL đầy đủ vào JWT giúp phân quyền tốt hơn.”** Không nhất thiết. Claims lớn, động và lỗi thời có thể tăng rủi ro; object-level authorization vẫn cần ở resource server.

**“Xóa token trong browser là đủ cho logout.”** Sai. Bản sao bị đánh cắp và server-side session vẫn cần được xử lý.

## 22. Câu hỏi tự kiểm tra

1. Phân biệt token lifetime và data retention bằng ví dụ token hết hạn nhưng còn trong log.
2. Vì sao claims trong JWT được xem là snapshot tại thời điểm phát hành?
3. Những loại dữ liệu nào thường không nên đưa vào access token?
4. Vì sao sub bằng email làm tăng khả năng liên kết dữ liệu?
5. Pairwise subject identifier giúp giảm loại rủi ro nào?
6. Vì sao pseudonymization không đồng nghĩa anonymization?
7. Các yếu tố nào cần cân nhắc khi chọn access-token TTL?
8. Vì sao iat không chứng minh claims vẫn mới?
9. JWT stateless được thu hồi như thế nào và giới hạn ra sao?
10. JWE bảo vệ điều gì và không giải quyết vấn đề gì về retention?
11. Vì sao không nên ghi Authorization header vào log?
12. Message queue và dead-letter queue tạo ra rủi ro retention nào?
13. Logout cần xử lý những bản sao hoặc trạng thái nào?
14. Làm thế nào để kiểm thử rằng token chỉ chứa claims cần thiết?

## 23. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), registered claims, NumericDate và cấu trúc JWT.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), chữ ký và cấu trúc JWS; JWS không tự mã hóa payload.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516), mã hóa nội dung JWT/JWE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), thực hành an toàn khi phát hành và xác minh JWT.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), profile access token và claims liên quan.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009), thu hồi token và giới hạn phụ thuộc triển khai.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), truy vấn trạng thái token tại authorization server.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), bảo vệ bearer token và API theo hướng áp dụng chung.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), loại trừ hoặc bảo vệ dữ liệu nhạy cảm trong log.
- [GDPR — Regulation (EU) 2016/679, Article 5](https://eur-lex.europa.eu/eli/reg/2016/679/oj), nguyên tắc data minimisation và storage limitation khi GDPR áp dụng.
