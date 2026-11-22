# Giới hạn của quyền được chụp tại thời điểm cấp phát

## 1. Vấn đề: token vẫn hợp lệ nhưng quyền đã thay đổi

Một access token dạng JSON Web Token (JWT) thường mang các claims mô tả danh tính, scope, role, permission hoặc ngữ cảnh tổ chức tại thời điểm token được phát hành. Khi API xác minh chữ ký và các điều kiện của token, API có thể đọc những claims đó mà không cần hỏi lại bên phát hành trong mỗi yêu cầu.

Đặc điểm này hữu ích cho hệ thống phân tán: nhiều API có thể tự xác minh token, giảm số lần gọi đến hệ thống định danh và tránh một điểm kiểm tra tập trung cho mọi request. Tuy nhiên, nó tạo ra một giới hạn quan trọng:

> **Một JWT tự xác minh chỉ cho biết những phát biểu đã được ký tại thời điểm phát hành. Chữ ký hợp lệ không chứng minh rằng quyền đó vẫn còn hiệu lực ở thời điểm hiện tại.**

Ví dụ:

- 09:00, nhân viên được cấp role **invoice_approver** và access token có permission **invoice.approve**.
- 09:10, quản trị viên gỡ role phê duyệt vì nhân viên chuyển bộ phận.
- 09:12, nhân viên vẫn gửi token cũ đến API.
- 09:30, token mới hết hạn.

Nếu API chỉ xác minh chữ ký, issuer, audience và thời hạn rồi tin vào claim permission, token cũ có thể tiếp tục được dùng đến khi hết hạn. Hệ thống đã thay đổi quyền lúc 09:10 nhưng các API không nhận biết thay đổi đó.

Đây là **độ trễ thu hồi quyền (revocation latency)** hoặc **khoảng thời gian quyền cũ còn được chấp nhận**. Nó là hệ quả của việc đóng gói trạng thái quyền vào một bằng chứng có thời hạn và xác minh độc lập.

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API, dịch vụ phân tán và ứng dụng nhiều tổ chức. Trọng tâm là vòng đời của quyền sau khi token được cấp, cách giới hạn rủi ro và lựa chọn cơ chế thu hồi phù hợp; không phụ thuộc một ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Vì sao quyền trong JWT bị cũ?

JWT là một thông điệp có cấu trúc. Với JWT có chữ ký, bên nhận có thể xác minh rằng payload không bị sửa kể từ khi issuer ký token. Chữ ký không làm cho dữ liệu tự cập nhật khi trạng thái bên ngoài thay đổi.

Giả sử token chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "iat": 1900000000,
  "exp": 1900003600,
  "jti": "access-7d31",
  "tenant_id": "company-a",
  "roles": ["invoice_approver"],
  "permissions": ["invoice.read", "invoice.approve"]
}
~~~

Payload trên là ví dụ đã giải mã, không phải token có thể dùng thực tế. Những claim **roles**, **permissions** và **tenant_id** là quy ước của ứng dụng. Khi issuer ký token, chúng phản ánh trạng thái mà issuer đã dùng để ra quyết định lúc phát hành. Nếu role, quyền thành viên, tenant, chính sách hoặc trạng thái tài khoản thay đổi sau đó, các byte trong token vẫn giữ nguyên.

### 2.1. Những loại thay đổi có thể làm claims lỗi thời

| Thay đổi sau khi phát hành | Claim hoặc quyết định có thể bị cũ | Rủi ro |
| --- | --- | --- |
| Người dùng bị khóa hoặc vô hiệu hóa | Trạng thái tài khoản/đăng nhập | Token vẫn được chấp nhận dù tài khoản không còn được phép hoạt động. |
| Người dùng bị gỡ khỏi tổ chức | **tenant_id**, role hoặc permission theo tenant | Truy cập tiếp vào dữ liệu tổ chức sau khi tư cách thành viên kết thúc. |
| Role bị thu hồi hoặc thay đổi | **roles** | Người dùng tiếp tục nhận quyền suy ra từ role cũ. |
| Permission trực tiếp bị thu hồi | **permissions** | Thao tác nhạy cảm vẫn được thực hiện theo quyền cũ. |
| Ứng dụng khách bị thu hồi quyền | **client_id**, scope hoặc grant | Client tiếp tục gọi API bằng token đã phát hành trước khi thu hồi grant. |
| Phiên đăng nhập bị kết thúc | ID phiên hoặc trạng thái phiên | Token bị đánh cắp vẫn dùng được dù người dùng đã đăng xuất. |
| Chính sách nghiệp vụ thay đổi | Điều kiện suy ra từ role/permission | Một quyền từng hợp lệ có thể không còn phù hợp với quy định mới. |
| Tài nguyên đổi chủ hoặc trạng thái | Quyền trên đối tượng | Token hợp lệ nhưng chủ thể không còn được truy cập tài nguyên hiện tại. |

Một số thay đổi có thể được kiểm tra ngoài JWT. Ví dụ, API có thể luôn tải bản ghi hóa đơn và kiểm tra **owner_id** hoặc trạng thái hiện tại. Nhưng những thay đổi về trạng thái tài khoản, membership, role hoặc grant sẽ không tự xuất hiện trong token cũ nếu API không có một nguồn trạng thái bổ sung.

### 2.2. Cấp quyền mới cũng có độ trễ

Vấn đề không chỉ là thu hồi. Nếu một người vừa được cấp thêm quyền **invoice.export**, token cũ có thể chưa chứa permission đó. Kết quả là:

- Quyền bị thu hồi: token cũ có thể **cho phép quá lâu**.
- Quyền mới được cấp: token cũ có thể **không cho phép đủ sớm**.

Đây là hai phía của cùng một hiện tượng: token là ảnh chụp tại thời điểm phát hành. API chỉ có thể biết quyền mới khi token được phát hành lại hoặc khi API tra cứu trạng thái quyền hiện hành.

## 3. Phân biệt thời hạn token, kết thúc phiên và thu hồi quyền

Ba khái niệm này có liên quan nhưng không giống nhau.

| Khái niệm | Điều gì xảy ra? | Có tự làm JWT access token cũ mất hiệu lực ngay không? |
| --- | --- | --- |
| **Token hết hạn** | Thời điểm **exp** đã đến; API không còn chấp nhận token theo chính sách thời gian. | Có, khi API kiểm tra thời gian đúng và không áp dụng sai lệch vượt chính sách. |
| **Đăng xuất/kết thúc phiên** | Hệ thống đánh dấu phiên hoặc thông tin xác thực không còn hoạt động. | Không, nếu API chỉ xác minh JWT độc lập và không kiểm tra trạng thái phiên. |
| **Thu hồi refresh token** | Không cho phép tiếp tục dùng refresh token để lấy access token mới. | Không nhất thiết; access token đã phát hành có thể vẫn dùng đến khi hết hạn. |
| **Thu hồi access token** | Một token cụ thể hoặc một nhóm token bị đánh dấu không còn được chấp nhận. | Chỉ khi API có cách nhận biết trạng thái thu hồi, ví dụ introspection, denylist hoặc phiên bản quyền. |
| **Thu hồi role/permission** | Quyền của chủ thể thay đổi trong hệ thống phân quyền. | Không, nếu quyền cũ đã được đóng gói vào JWT và API không kiểm tra nguồn quyền hiện hành. |
| **Thu hồi khóa ký** | API ngừng tin một khóa hoặc bộ khóa phát hành token. | Có thể làm nhiều token mất hiệu lực, nhưng phạm vi rộng và phụ thuộc cách phân phối khóa. |

**Đăng xuất không đồng nghĩa thu hồi mọi access token đã phát hành.** Một ứng dụng có thể xóa token khỏi thiết bị của người dùng nhưng token bị sao chép trước đó vẫn có thể được dùng ở nơi khác. Muốn chặn token đã bị sao chép, hệ thống cần một cơ chế mà API kiểm tra được.

Tương tự, thu hồi refresh token chủ yếu ngăn việc nhận token mới. Nó không tự thay đổi chữ ký, claims hoặc **exp** của access token đã tồn tại.

## 4. Định lượng khoảng thời gian quyền cũ còn hiệu lực

Giả sử:

- Access token được phát hành lúc \(t_i\).
- Token hết hạn lúc \(t_e\).
- Quyền bị thu hồi lúc \(t_r\).
- API chỉ xác minh JWT ngoại tuyến và không kiểm tra trạng thái thu hồi.

Khi đó, khoảng thời gian tối đa còn lại mà token cũ có thể được chấp nhận xấp xỉ:

\[
W = \max(0, t_e - t_r)
\]

Đây là **cửa sổ phơi nhiễm** sau thời điểm thu hồi. Nếu token có thời hạn 30 phút và quyền bị thu hồi ngay sau khi phát hành, cửa sổ có thể gần 30 phút. Nếu quyền bị thu hồi ngay trước khi token hết hạn, cửa sổ nhỏ hơn.

Ví dụ:

Ví dụ với token có TTL 30 phút, phát hành lúc 09:00 và quyền bị thu hồi lúc 09:10:

| Thời điểm | Sự kiện | API chỉ xác minh JWT ngoại tuyến |
| --- | --- | --- |
| **09:00** | Phát hành token | Chấp nhận token hợp lệ. |
| **09:10** | Quyền bị thu hồi ở hệ thống nguồn | Vẫn có thể chấp nhận token cũ vì claims chưa thay đổi. |
| **09:30** | Token hết hạn | Từ chối token theo kiểm tra **exp**. |

**Cửa sổ quyền cũ có thể còn được chấp nhận: 20 phút** (từ 09:10 đến 09:30).

Thời gian thực tế còn phụ thuộc sai lệch đồng hồ được chấp nhận, độ trễ phân phối khóa, cache hoặc chính sách triển khai. Không nên mô tả token ngắn hạn là “thu hồi tức thì”; nó chỉ **giới hạn** khoảng thời gian còn lại.

### 4.1. Khi có cache hoặc cơ chế cập nhật trạng thái

Nếu API kiểm tra một nguồn trạng thái nhưng cache kết quả, cửa sổ rủi ro phụ thuộc:

- Thời gian cache còn hiệu lực.
- Độ trễ phát sự kiện thu hồi và phân phối đến các API.
- Độ trễ cập nhật kho trạng thái.
- Cách xử lý khi cache hoặc dịch vụ kiểm tra không khả dụng.
- Sai lệch đồng hồ và cách áp dụng thời hạn.

Ví dụ, một hệ thống có cache quyền 60 giây và sự kiện thu hồi thường đến các API trong 5 giây có thể có độ trễ đáng kể gần bằng thời gian cache còn hiệu lực, tùy cách invalidation. **Không được cộng hoặc lấy min các con số một cách máy móc** nếu kiến trúc không xác định thứ tự kiểm tra và cache.

Điều cần thiết là định nghĩa một **SLO về thời gian thu hồi**: ví dụ, quyền nhạy cảm phải bị chặn trong tối đa 10 giây sau khi thao tác thu hồi được xác nhận. Sau đó thiết kế các đường dữ liệu và xử lý lỗi để đáp ứng SLO đó, thay vì chỉ đặt một con số TTL.

## 5. Các chiến lược giới hạn quyền cũ

Không có một chiến lược phù hợp với mọi API. Những phương án dưới đây có thể dùng riêng hoặc kết hợp.

### 5.1. Access token có thời hạn ngắn

Đặt **exp** gần thời điểm phát hành hơn, ví dụ 5–10 phút tùy rủi ro và trải nghiệm. Khi quyền thay đổi, token cũ sớm hết hạn và client phải lấy token mới.

**Ưu điểm**

- Resource server vẫn có thể xác minh token ngoại tuyến.
- Không cần lưu trạng thái từng access token.
- Giới hạn rõ cửa sổ rủi ro theo thời gian còn lại.
- Dễ áp dụng cho nhiều API nếu các bên thống nhất chính sách TTL.

**Giới hạn**

- Không chặn ngay token bị đánh cắp hoặc quyền vừa bị thu hồi.
- Tăng tần suất refresh hoặc yêu cầu cấp token mới.
- Nếu refresh token vẫn hợp lệ và issuer không kiểm tra quyền mới, client có thể liên tục nhận access token chứa quyền cũ.
- TTL quá ngắn có thể gây tải lên issuer và làm trải nghiệm kém khi mạng chập chờn.

**Điều kiện quan trọng:** lúc cấp access token mới, issuer phải đọc trạng thái quyền hiện hành hoặc một nguồn cache có giới hạn độ trễ phù hợp. Chỉ giảm TTL mà không cập nhật logic phát hành thì không giải quyết được việc token mới tiếp tục chứa quyền đã thu hồi.

### 5.2. Token introspection

Với **introspection**, resource server hỏi authorization server hoặc dịch vụ quản lý token xem token có còn active hay không. RFC 7662 mô tả OAuth 2.0 Token Introspection.

Một phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "scope": "invoice:read",
  "exp": 1900003600
}
~~~

Phản hồi thực tế phụ thuộc hợp đồng introspection và có thể chứa thêm hoặc ít trường hơn. Resource server phải xác thực kênh giao tiếp, quyền gọi introspection, kiểu token và ngữ nghĩa trường **active** theo nhà cung cấp.

Khi quyền bị thu hồi, authorization server có thể trả **active: false** hoặc cung cấp claims hiện hành tùy thiết kế. Resource server có thể từ chối ngay khi nhận trạng thái không còn hoạt động.

**Ưu điểm**

- Có nguồn trạng thái tập trung để nhận biết token hoặc grant bị thu hồi.
- Có thể hỗ trợ thu hồi theo token, phiên hoặc quyền.
- Không buộc mọi API phải tự duy trì danh sách token bị thu hồi.

**Giới hạn**

- Mỗi lần kiểm tra có thể tạo thêm độ trễ và tải mạng.
- Authorization server trở thành phụ thuộc về khả dụng.
- Cache phản hồi introspection tạo ra một cửa sổ stale mới.
- Phải bảo vệ endpoint introspection và kiểm soát bên nào được tra cứu token.

Một hệ thống có thể introspect mỗi request nhạy cảm và cache request ít nhạy cảm trong thời gian ngắn. Chính sách cache phải được thiết kế theo SLO thu hồi.

### 5.3. Denylist theo định danh token

JWT có thể chứa **jti** (JWT ID), một định danh token. Khi một access token bị thu hồi, hệ thống ghi lại định danh đó vào denylist. Resource server kiểm tra **jti** trước khi chấp nhận token.

Khóa lưu trữ nên có phạm vi issuer, ví dụ:

~~~text
revoked-token:<issuer-id>:<jti>
~~~

Không chỉ dùng **jti** toàn cục nếu nhiều issuer có thể phát hành cùng giá trị. Cũng không nên lưu nguyên JWT làm khóa hoặc log, vì token là bearer credential.

**Thời hạn bản ghi denylist:** thường có thể giữ đến sau thời điểm token hết hạn cộng sai lệch đồng hồ cho phép. Khi token không còn được chấp nhận ở bất kỳ API nào, bản ghi mới hết giá trị.

**Ưu điểm**

- Thu hồi một token cụ thể mà không ảnh hưởng token khác của cùng người dùng.
- Có thể hỗ trợ xử lý token bị lộ hoặc đăng xuất khỏi một thiết bị.
- Có thể kết hợp với JWT tự xác minh.

**Giới hạn**

- Resource server phải tra cứu trạng thái hoặc nhận bản sao denylist.
- Số lượng bản ghi tăng theo lượng token bị thu hồi.
- Các API phải đồng bộ dữ liệu thu hồi; cache hoặc replication chậm làm tăng độ trễ.
- Nếu kẻ tấn công dùng token trước khi thông tin thu hồi tới API, request vẫn có thể thành công.

Ví dụ quyết định:

~~~text
verify JWT signature and standard claims
if (issuer, jti) is in denylist:
    reject token
else:
    continue with authorization policy
~~~

### 5.4. Phiên bản quyền hoặc phiên đăng nhập

Thay vì lưu từng token bị thu hồi, hệ thống có thể lưu một **phiên bản trạng thái** ở phía server. Token mang phiên bản tại thời điểm phát hành; API hoặc dịch vụ kiểm tra so sánh với phiên bản hiện tại.

Token minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "authz_version": 12,
  "session_version": 4,
  "exp": 1900003600
}
~~~

Giá trị **authz_version** và **session_version** là custom claims do ứng dụng định nghĩa. Chúng không phải registered claims của JWT.

Ví dụ, khi role của người dùng thay đổi:

~~~text
Token đã phát hành: authz_version = 12
Trạng thái hiện tại: authz_version = 13
So sánh: 12 != 13 -> token không còn phù hợp
~~~

**Các phạm vi version có thể khác nhau:**

- **User authorization version:** thu hồi mọi token cũ của một người dùng khi quyền của họ thay đổi.
- **Session version:** kết thúc một hoặc nhiều phiên theo mô hình lưu trữ.
- **Tenant membership version:** thay đổi membership của một người trong một tổ chức.
- **Client/grant version:** thu hồi quyền cấp cho một ứng dụng khách.
- **Global policy version:** buộc đánh giá lại token khi chính sách chung thay đổi.

**Ưu điểm**

- Không cần lưu từng **jti** nếu mục tiêu là vô hiệu hóa cả nhóm token cũ.
- Dễ biểu diễn sự thay đổi quyền ở cấp người dùng, tenant hoặc client.
- Có thể giảm dữ liệu trạng thái so với denylist token.

**Giới hạn**

- Vẫn cần truy vấn hoặc cache phiên bản hiện tại.
- Thay đổi version quá rộng có thể buộc người dùng lấy token mới ở nhiều thiết bị/phiên.
- Phải xác định rõ phạm vi version và sự kiện nào làm tăng version.
- Cache version cũ vẫn tạo độ trễ thu hồi.

Nếu chỉ tăng **authz_version** khi đổi role nhưng quên tăng khi gỡ membership hoặc thu hồi quyền trực tiếp, cơ chế sẽ không bảo vệ được những thay đổi bị bỏ sót. Danh sách sự kiện làm tăng version phải là một phần của hợp đồng nghiệp vụ.

### 5.5. Kiểm tra quyền hiện hành tại thời điểm yêu cầu

API có thể xác minh token để nhận diện chủ thể, rồi lấy role, permission hoặc membership hiện hành từ nguồn dữ liệu quyền:

~~~text
principal = verifyAndResolvePrincipal(accessToken)
currentMembership = loadMembership(principal, tenant)
currentPermissions = loadPermissions(principal, tenant)

if not currentMembership.active:
    deny
if requiredAction not in currentPermissions:
    deny
continue with resource-specific policy
~~~

**Ưu điểm**

- Quyền có thể phản ánh trạng thái hiện hành thay vì ảnh chụp trong token.
- Thu hồi quyền có thể có hiệu lực nhanh theo độ nhất quán của nguồn dữ liệu.
- Dễ áp dụng chính sách phức tạp theo tenant hoặc nghiệp vụ.

**Giới hạn**

- Tăng độ trễ và tải cho kho dữ liệu hoặc dịch vụ phân quyền.
- Cần thiết kế cache và xử lý khi nguồn quyền không khả dụng.
- Cần tránh việc API khác nhau tự triển khai các cách tính quyền không nhất quán.

Không nhất thiết phải bỏ mọi claims phân quyền khỏi JWT. Một thiết kế có thể dùng scope/permission trong token như **giới hạn trên**, rồi giao quyền hiện hành ở backend quyết định có cho phép hay không. Điều này ngăn token tự tạo thêm quyền khi trạng thái server đã thu hẹp.

### 5.6. Thu hồi theo khóa ký

Nếu một khóa ký bị lộ hoặc không còn đáng tin, hệ thống có thể ngừng chấp nhận khóa đó trong tập khóa được tin cậy. Các JWT được ký bằng khóa đó sẽ không vượt qua xác minh sau khi thay đổi khóa được phân phối đến resource server.

Đây là biện pháp có phạm vi rộng:

- Có thể ảnh hưởng mọi token được ký bằng khóa đó, kể cả token của người dùng không liên quan.
- Resource server có thể cache JWKS nên việc loại bỏ khóa không lan tới tất cả API tức thì.
- Nếu khóa cũ vẫn cần để xác minh token hợp lệ trong thời gian chuyển tiếp, phải cân bằng giữa khả năng tương thích và rủi ro.

Thu hồi khóa phù hợp với sự cố khóa ký hoặc thay đổi trust anchor, **không phải** lựa chọn thông thường để thu hồi quyền của một người dùng.

## 6. So sánh các chiến lược

| Chiến lược | Thu hồi cá thể | Cần trạng thái ngoài JWT khi gọi API? | Độ trễ thu hồi | Chi phí/chú ý |
| --- | --- | --- | --- | --- |
| Token TTL ngắn | Không trực tiếp | Không | Tối đa phần thời hạn còn lại | Tăng tần suất cấp/refresh; không tức thì. |
| Introspection | Có thể | Có, gọi dịch vụ hoặc cache | Theo tính nhất quán và cache | Phụ thuộc dịch vụ introspection. |
| Denylist **jti** | Có | Có, tra cứu denylist | Theo thời gian phân phối/tra cứu | Lưu trạng thái token bị thu hồi. |
| Authorization/session version | Theo phạm vi version | Có, so sánh version | Theo độ trễ đọc/cập nhật version | Có thể thu hồi cả nhóm token. |
| Tra quyền hiện hành | Theo chủ thể, tenant, tài nguyên | Có | Theo độ nhất quán nguồn quyền | Tăng tải; phù hợp quyết định động. |
| Thu hồi khóa ký | Không chọn lọc theo người dùng | Cập nhật trust/key set | Theo phân phối khóa/cache | Phạm vi ảnh hưởng rất rộng. |

Các cơ chế có thể kết hợp, ví dụ:

- JWT ngắn hạn + refresh token được quản lý theo phiên.
- JWT + denylist cho sự cố token bị lộ.
- JWT + authorization version cho thay đổi quyền theo người dùng.
- JWT + kiểm tra membership hiện hành cho hệ thống đa tổ chức.
- JWT + introspection hoặc tra quyền trực tiếp cho thao tác rủi ro cao.

## 7. Refresh token không thay thế cơ chế thu hồi access token

Một luồng thường gặp:

1. Người dùng xác thực và nhận access token cùng refresh token.
2. Access token được gửi tới resource server.
3. Khi access token hết hạn, client gửi refresh token tới authorization server để lấy access token mới.
4. Authorization server kiểm tra refresh token, trạng thái phiên, grant và quyền hiện hành rồi mới phát hành token mới.

**Refresh token** có vòng đời và mục đích khác access token. Nó thường được gửi tới authorization server, không gửi cho API tài nguyên để truy cập dữ liệu.

Nếu quyền bị thu hồi:

- Thu hồi refresh token hoặc phiên có thể ngăn token mới được phát hành.
- Access token cũ vẫn có thể được chấp nhận cho đến khi hết hạn, trừ khi resource server có cơ chế thu hồi/kiểm tra trạng thái.
- Nếu authorization server không đọc quyền hiện hành khi refresh, nó có thể tiếp tục cấp token mới chứa quyền cũ.

### 7.1. Rotation và phát hiện tái sử dụng refresh token

Với refresh token rotation, mỗi lần refresh thành công, hệ thống phát hành refresh token mới và vô hiệu hóa token cũ. Nếu refresh token cũ bị sử dụng lại, hệ thống có thể phát hiện dấu hiệu token bị sao chép và thu hồi cả nhóm token/phiên liên quan theo chính sách.

Rotation giúp kiểm soát vòng đời refresh token, nhưng không tự thu hồi access token JWT đã được phát hành trước đó. Muốn giảm cửa sổ rủi ro của access token, cần TTL phù hợp hoặc một cơ chế kiểm tra trạng thái bổ sung.

### 7.2. Khi cấp token mới phải tính lại quyền

Khi refresh, authorization server nên:

- Kiểm tra refresh token còn hiệu lực và gắn với đúng client/grant.
- Kiểm tra người dùng, tài khoản dịch vụ và phiên còn được phép hoạt động.
- Đọc quyền hiện hành hoặc cache quyền có giới hạn độ trễ đã định nghĩa.
- Không cấp scope rộng hơn quyền được yêu cầu và được chấp thuận.
- Áp dụng lại ràng buộc audience và mục đích của access token.
- Ghi nhận việc refresh và sự kiện thu hồi theo chính sách audit.

## 8. Độ nhất quán trong hệ thống phân tán

Ngay cả khi đã có denylist, introspection hoặc authorization version, “thu hồi ngay lập tức” vẫn là một yêu cầu kiến trúc. Một API có thể đang đọc cache cũ, một vùng triển khai có thể chưa nhận sự kiện, hoặc dịch vụ quyền có thể tạm thời không khả dụng.

### 8.1. Mô hình phân phối sự kiện thu hồi

Một kiến trúc thường gặp:

~~~mermaid
flowchart LR
    A["Quản trị viên thu hồi quyền"] --> B["Authorization service"]
    B --> C["Cập nhật trạng thái quyền"]
    C --> D["Phát sự kiện thu hồi"]
    D --> E["Cache/API vùng 1"]
    D --> F["Cache/API vùng 2"]
    E --> G["Từ chối token cũ"]
    F --> H["Từ chối token cũ"]
~~~

Sự kiện có thể mang:

~~~json
{
  "event_id": "evt-9081",
  "event_type": "principal.authorization.changed",
  "issuer": "https://identity.example.test",
  "subject": "user-514",
  "tenant_id": "company-a",
  "authorization_version": 13,
  "occurred_at": "2030-03-17T09:10:00Z"
}
~~~

Đây là payload sự kiện nội bộ minh họa, không phải định dạng chuẩn của JWT hoặc OAuth. Không đưa access token hoặc bí mật vào sự kiện.

### 8.2. Các yêu cầu để sự kiện thu hồi đáng tin cậy

- **Xác thực nguồn phát:** chỉ nguồn quản trị quyền có thẩm quyền mới được phát sự kiện.
- **Idempotency:** nhận lại cùng event không làm sai trạng thái.
- **Ordering:** nếu sự kiện version 13 đến sau version 14, consumer không được hạ trạng thái về 13.
- **Durability:** sự kiện không bị mất khi consumer tạm dừng hoặc mạng gián đoạn.
- **Replay/recovery:** consumer có thể đọc lại sự kiện sau checkpoint hoặc đối chiếu snapshot trạng thái hiện hành.
- **Bounded cache:** cache có TTL và cơ chế invalidation được định nghĩa.
- **Observability:** theo dõi thời điểm thu hồi được xác nhận, thời điểm từng vùng áp dụng và độ trễ lớn nhất.

Sự kiện thường nên chứa **version tăng đơn điệu** hoặc sequence để consumer nhận biết trạng thái mới/cũ. Không nên chỉ dựa vào timestamp do nhiều hệ thống có thể lệch đồng hồ.

### 8.3. Đặt mục tiêu thu hồi có thể đo được

Ví dụ một hệ thống đặt:

~~~text
SLO: 99.9% API nhạy cảm chặn quyền đã thu hồi trong <= 10 giây.

Các mốc cần đo:
T0: thao tác thu hồi được commit
T1: sự kiện được phát bền vững
T2: API/region nhận sự kiện
T3: cache quyền cũ bị vô hiệu
T4: request tiếp theo bị từ chối

Revocation latency = T4 - T0
~~~

Nếu một vùng không nhận được sự kiện, hệ thống cần có cơ chế đối chiếu hoặc đường kiểm tra đồng bộ. Nếu không, SLO chỉ đúng ở vùng khỏe mạnh và không phản ánh trường hợp lỗi.

## 9. Cache và chính sách khi nguồn trạng thái không khả dụng

Cache giúp giảm độ trễ và tải, nhưng cache một kết quả **ALLOW** cũng có nghĩa hệ thống có thể tiếp tục cho phép dựa trên dữ liệu đã cũ.

### 9.1. Cache kết quả nào?

Có thể cache:

- Trạng thái token introspection theo định danh token.
- Phiên bản quyền theo chủ thể hoặc tenant.
- Membership và tập permission hiện hành.
- Kết quả đánh giá chính sách cho một tài nguyên cụ thể.

Mỗi loại cache cần key đủ hẹp. Một kết quả cho phép **user-514 đọc invoice-100** không được dùng cho **invoice-200** hoặc hành động **invoice.approve**. Cache phải xét đúng issuer, principal, tenant, action, resource và version/policy liên quan.

### 9.2. Fail-open và fail-closed

Khi dịch vụ kiểm tra quyền không truy cập được:

- **Fail-closed:** từ chối hoặc tạm dừng thao tác cần kiểm tra vì không đủ bằng chứng cho phép.
- **Fail-open:** tiếp tục cho phép dựa trên token hoặc cache cũ để duy trì khả dụng.

Không có lựa chọn nào miễn phí. Fail-closed có thể làm gián đoạn dịch vụ; fail-open làm tăng nguy cơ chấp nhận quyền đã bị thu hồi. Cần phân loại thao tác:

| Loại thao tác | Hướng xử lý thường phù hợp |
| --- | --- |
| Chuyển tiền, hoàn tiền, thay đổi tài khoản quản trị | Fail-closed khi không thể xác minh quyền hiện hành. |
| Đọc dữ liệu nội bộ nhạy cảm | Thường fail-closed hoặc dùng cache rất ngắn có SLO rõ. |
| Đọc nội dung ít nhạy cảm, có thể công khai | Có thể chấp nhận cache lâu hơn nếu chính sách dữ liệu cho phép. |
| Ghi dữ liệu làm thay đổi quyền hoặc chính sách | Cần kiểm tra quyền tin cậy tại thời điểm thực thi. |

Nếu hệ thống cho phép dùng cache cũ trong một khoảng thời gian khi nguồn trạng thái lỗi, khoảng thời gian đó phải được tính vào **cửa sổ thu hồi tối đa**. Không gọi đó là thu hồi tức thì.

## 10. Quyền thay đổi giữa lúc kiểm tra và lúc thực thi

Ngay cả khi API kiểm tra quyền hiện hành, vẫn có thể xuất hiện một khoảng trống:

1. 09:10:00.000, API kiểm tra người dùng còn quyền duyệt.
2. 09:10:00.050, quản trị viên thu hồi quyền.
3. 09:10:00.100, API ghi trạng thái hóa đơn đã duyệt.

Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**. Với thao tác quan trọng, cần xem xét kiểm tra quyền và thay đổi dữ liệu trong cùng một ranh giới nhất quán:

- Đánh giá quyền bên trong giao dịch hoặc cơ chế đồng bộ phù hợp.
- Dùng điều kiện ghi có xét version/trạng thái quyền hoặc trạng thái tài nguyên.
- Khóa hoặc kiểm soát đồng thời khi cần.
- Đối với hành động tài chính, có thể yêu cầu xác nhận/step-up gần thời điểm thực thi.
- Ghi lại chủ thể, hành động, tài nguyên và quyết định đã được áp dụng.

Không phải mọi thao tác đều cần khóa giao dịch dài. Mục tiêu là bảo đảm mức nhất quán tương ứng với hậu quả của hành động, đồng thời tránh tạo điểm nghẽn không cần thiết.

## 11. Lựa chọn cơ chế theo mức độ rủi ro

Một cách thiết kế thực tế là xác định **thời gian tối đa chấp nhận được cho quyền cũ** trước khi chọn cơ chế.

| Mức rủi ro ví dụ | Mục tiêu thu hồi gợi ý | Cách tiếp cận có thể cân nhắc |
| --- | --- | --- |
| Nội dung ít nhạy cảm, chỉ đọc | Vài phút có thể chấp nhận tùy dữ liệu | JWT TTL ngắn/vừa, kiểm tra tài nguyên cơ bản. |
| Dữ liệu doanh nghiệp theo tenant | Trong thời gian ngắn và có kiểm soát | JWT + membership/version hiện hành, cache ngắn, kiểm tra tenant. |
| Dữ liệu cá nhân hoặc báo cáo nhạy cảm | Rất ngắn, có khả năng chặn phiên cụ thể | Introspection hoặc version/denylist kết hợp cache ngắn. |
| Duyệt giao dịch, chuyển tiền, thay đổi quyền quản trị | Gần thời điểm thực thi | Kiểm tra quyền hiện hành, fail-closed, kiểm soát TOCTOU và audit. |
| Khóa ký bị xâm phạm | Phản ứng khẩn cấp ở phạm vi khóa | Ngừng tin khóa, phân phối cấu hình mới và đánh giá toàn bộ token liên quan. |

Đây là gợi ý phân loại, không phải ngưỡng tuân thủ cố định. Thời hạn thực tế phải dựa trên phân tích tác động, yêu cầu nghiệp vụ, kiến trúc triển khai và khả năng vận hành.

### 11.1. Một ma trận quyết định đơn giản

Trước tiên hỏi:

1. Nếu quyền cũ được dùng thêm 5 phút, hậu quả là gì?
2. Có cần thu hồi **một token**, **một phiên**, **mọi token của người dùng**, hay **mọi token của một client/issuer**?
3. API có thể phụ thuộc vào dịch vụ kiểm tra trực tuyến không?
4. Khi dịch vụ kiểm tra lỗi, thao tác có thể tạm dừng hay phải tiếp tục?
5. Mục tiêu thu hồi có đo được và kiểm thử được không?

Ví dụ lựa chọn:

- Cần thu hồi một thiết bị bị mất: có thể quản lý session hoặc denylist token/session.
- Cần thu hồi mọi quyền của một người trong một tenant: có thể tăng authorization version theo tenant hoặc tra membership hiện hành.
- Cần thu hồi grant của một ứng dụng: kiểm tra client/grant state hoặc introspection.
- Cần chặn ngay thao tác chuyển tiền khi role bị gỡ: kiểm tra quyền hiện hành và trạng thái giao dịch tại thời điểm ghi.
- Cần xử lý khóa ký bị lộ: thu hồi khóa và chấp nhận tác động tới tất cả token phụ thuộc khóa đó.

## 12. Ví dụ pseudocode cho nhiều lớp kiểm tra

Ví dụ dưới đây mô tả API hóa đơn có JWT access token. Claims trong token là giới hạn quyền tại lúc phát hành; trạng thái phiên, membership và permission hiện tại được lấy từ nguồn tin cậy.

~~~text
function authorizeSensitiveInvoiceAction(request, action):
    token = extractBearerToken(request)
    verified = validateAccessToken(
        token,
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing",
        allowedAlgorithms = ["RS256"]
    )
    if verified.failed:
        return UNAUTHENTICATED

    claims = verified.claims
    if claims.jti is missing or claims.sub is missing:
        return DENY

    if denylist.contains(claims.iss, claims.jti):
        return UNAUTHENTICATED

    principal = resolvePrincipal(claims.iss, claims.sub)
    if principal is null:
        return DENY

    current = authorizationState.load(
        principal = principal,
        tenant = claims.tenant_id
    )
    if current.unavailable:
        return DENY_OR_TEMPORARILY_UNAVAILABLE

    if not current.active:
        return DENY
    if claims.authz_version != current.authz_version:
        return UNAUTHENTICATED_OR_REQUIRE_NEW_TOKEN

    requiredScope = scopeFor(action)
    requiredPermission = permissionFor(action)
    if requiredScope not in parseExactScopes(claims.scope):
        return DENY
    if requiredPermission not in claims.permissions:
        return DENY
    if requiredPermission not in current.permissions:
        return DENY

    resource = loadResourceInTenant(claims.tenant_id, request.resourceId)
    if resource is null:
        return NOT_FOUND
    if not resourcePolicyAllows(principal, action, resource, current):
        return DENY

    return ALLOW
~~~

Đây là pseudocode, không phải thư viện hoặc thuật toán triển khai hoàn chỉnh. API phải định nghĩa rõ trường hợp version không khớp được ánh xạ sang lỗi nào, cache trạng thái có độ trễ tối đa bao lâu, và thao tác ghi được bảo vệ khỏi TOCTOU ra sao. Nếu không cần denylist hoặc version cho một loại API, có thể bỏ lớp đó theo hợp đồng; không nên thêm kiểm tra mà không có chủ sở hữu dữ liệu và chính sách cập nhật rõ ràng.

## 13. Quan sát, audit và vận hành thu hồi

Một cơ chế thu hồi chỉ đáng tin khi đội vận hành biết nó có hoạt động không. Nên theo dõi:

- Số lượng token bị từ chối do hết hạn, denylist, version không khớp hoặc introspection trả inactive.
- Độ trễ từ lúc thao tác thu hồi được commit đến lúc API cuối cùng áp dụng.
- Số lượng API/vùng chưa nhận sự kiện hoặc đang dùng cache quá thời hạn.
- Lỗi và độ trễ của dịch vụ introspection/authorization state.
- Tỷ lệ request bị từ chối khi nguồn trạng thái không khả dụng.
- Số lần refresh token bị từ chối và dấu hiệu refresh token reuse.
- Các thay đổi role, permission, membership, grant và khóa ký.

Log/audit nên ghi **định danh cần thiết** như issuer, subject, tenant, client, jti đã được xử lý theo chính sách, hành động, tài nguyên, kết quả, lý do và thời điểm. Tránh ghi nguyên access token, refresh token, secret hoặc payload có dữ liệu nhạy cảm.

Khi người dùng báo “đã bị gỡ quyền nhưng vẫn truy cập được”, việc điều tra cần xác định:

1. Token được phát hành lúc nào, **exp** là gì, audience và issuer nào?
2. API có chỉ xác minh JWT hay còn tra cứu trạng thái?
3. Thay đổi quyền đã commit ở nguồn nào và có tăng version/phát sự kiện không?
4. API đang dùng cache nào, cache key và TTL ra sao?
5. Các vùng triển khai đã nhận sự kiện thu hồi chưa?
6. Request cuối cùng được cho phép ở thời điểm nào và dựa trên dữ kiện nào?

Không thể kết luận chỉ từ việc “token vẫn còn hạn”; cần kiểm tra đường quyết định thực tế.

## 14. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Nghĩ chữ ký hợp lệ nghĩa là quyền hiện tại còn đúng | Chữ ký chỉ bảo vệ nội dung đã ký. | Tách xác minh token khỏi kiểm tra quyền hiện hành. |
| Nghĩ logout làm mọi JWT mất hiệu lực | Token đã sao chép vẫn có thể được dùng ngoại tuyến. | Quản lý session/denylist/introspection/version tùy yêu cầu. |
| Thu hồi refresh token nhưng bỏ qua access token cũ | Access token vẫn có thể dùng đến **exp**. | Giới hạn TTL hoặc kiểm tra trạng thái access token. |
| Rút ngắn TTL nhưng issuer vẫn phát hành quyền cũ | Token mới tiếp tục chứa trạng thái đã bị thu hồi. | Tính lại quyền hiện hành mỗi lần cấp/refresh. |
| Dùng denylist nhưng API không tra cứu hoặc cache quá lâu | Thông tin thu hồi không tới điểm thực thi. | Kiểm tra đường phân phối và đặt SLO cache/invalidation. |
| Tăng version nhưng bỏ sót một loại thay đổi quyền | Một số token cũ vẫn vượt kiểm tra. | Xác định mọi sự kiện phải làm tăng version. |
| Coi event đã publish là mọi API đã áp dụng | Có thể có consumer lỗi hoặc vùng bị phân vùng mạng. | Đo xác nhận theo từng consumer/region và có cơ chế recovery. |
| Fail-open không giới hạn khi nguồn quyền lỗi | Token cũ có thể tiếp tục cấp quyền không còn phù hợp. | Phân loại thao tác và giới hạn thời gian dùng cache cũ. |
| Thu hồi khóa để xử lý một người dùng | Tác động tới mọi token phụ thuộc khóa. | Chọn cơ chế theo phạm vi cần thu hồi. |
| Kiểm tra quyền rồi ghi dữ liệu sau một khoảng không kiểm soát | Quyền có thể bị thu hồi giữa hai bước (TOCTOU). | Đồng bộ quyết định và thao tác nhạy cảm. |
| Cache ALLOW chỉ theo user | Quyền của một tenant/tài nguyên bị áp dụng sang nơi khác. | Cache key gồm issuer, principal, tenant, action, resource và version cần thiết. |

## 15. Kịch bản kiểm thử cần có

Kiểm thử phải xác nhận thời điểm và phạm vi thu hồi, không chỉ xác nhận token hết hạn.

~~~text
1. Token hợp lệ, quyền hiện hành còn hiệu lực
   -> ALLOW nếu tài nguyên và hành động phù hợp.

2. Quyền bị thu hồi, API chỉ xác minh JWT offline
   -> token cũ còn có thể được chấp nhận cho tới exp.
   -> đo cửa sổ rủi ro dự kiến.

3. Quyền bị thu hồi, API dùng authorization version
   -> token version cũ bị từ chối sau khi API nhận version mới.

4. Một jti bị denylist
   -> đúng token bị từ chối; token khác không bị ảnh hưởng nếu policy không yêu cầu.

5. Refresh token bị thu hồi, access token cũ chưa hết hạn
   -> refresh bị từ chối; access token cũ chỉ bị chặn nếu có cơ chế riêng.

6. Sự kiện thu hồi bị gửi trùng hoặc sai thứ tự
   -> trạng thái không bị lùi; xử lý idempotent.

7. Một vùng không nhận được sự kiện
   -> phát hiện qua monitoring; recovery/đối chiếu đưa vùng về trạng thái đúng.

8. Dịch vụ kiểm tra quyền không khả dụng
   -> hành vi fail-open/fail-closed đúng phân loại rủi ro đã công bố.

9. Quyền bị thu hồi giữa kiểm tra và thao tác ghi
   -> hành vi tuân theo chính sách nhất quán/TOCTOU.

10. Token có issuer, audience hoặc jti khác
    -> không nhầm trạng thái thu hồi giữa các issuer hoặc token.
~~~

Nên có kiểm thử tích hợp trên các API thực sự thực thi thao tác. Kiểm thử riêng hàm so sánh version không chứng minh tất cả resource server đều nhận và áp dụng version đó.

## 16. Checklist thiết kế chính sách thu hồi

Trước khi phát hành một loại access token, hãy trả lời:

1. **Quyền nào được chụp vào token?** Scope, role, permission, tenant, client và session có ý nghĩa gì?
2. **Những thay đổi nào làm claims cũ?** Khóa tài khoản, gỡ membership, thay role, thu hồi grant, kết thúc phiên, đổi chủ tài nguyên?
3. **Cửa sổ rủi ro tối đa là bao lâu?** Tính từ lúc thao tác thu hồi được commit đến lúc request bị chặn.
4. **Phạm vi thu hồi là gì?** Một token, một phiên, một user, một tenant membership, một client/grant hay một khóa?
5. **Nguồn trạng thái hiện hành ở đâu?** Ai sở hữu dữ liệu và đảm bảo tính nhất quán?
6. **Cơ chế nào được chọn?** TTL, introspection, denylist, version, tra quyền trực tiếp hay kết hợp?
7. **Cache và sự kiện hoạt động thế nào?** TTL, invalidation, ordering, replay, recovery và SLO?
8. **Khi nguồn kiểm tra lỗi thì sao?** Hành động nào fail-closed, hành động nào được dùng cache cũ trong giới hạn?
9. **Refresh có tính lại quyền không?** Access token cũ còn được chấp nhận trong bao lâu?
10. **Có bảo vệ TOCTOU không?** Kiểm tra quyền có nhất quán với thời điểm thực thi thao tác nhạy cảm?
11. **Có đo được không?** Audit và metric cho biết mọi API đã chặn quyền cũ hay chưa?
12. **Có diễn tập không?** Thử thu hồi token bị lộ, người dùng bị khóa, quyền tenant bị gỡ, sự cố khóa ký và vùng mất kết nối.

## 17. Ghi nhớ trọng tâm

- Claims phân quyền trong JWT là **ảnh chụp tại thời điểm phát hành**; chữ ký hợp lệ không làm chúng cập nhật theo trạng thái hiện tại.
- Token tự xác minh ngoại tuyến thường còn có thể được chấp nhận đến **exp** nếu API không có cơ chế kiểm tra thu hồi.
- Thu hồi role, logout hoặc thu hồi refresh token **không tự động** vô hiệu hóa mọi access token đã phát hành.
- TTL ngắn giới hạn cửa sổ rủi ro; introspection, denylist, version và tra quyền hiện hành cung cấp những cách nhận biết trạng thái bổ sung.
- Cache và phân phối sự kiện tạo ra độ trễ; cần đặt và đo **SLO thu hồi** trên toàn bộ API/vùng triển khai.
- Quyền cho thao tác nhạy cảm cần được kiểm tra sát thời điểm thực thi và có kiểm soát TOCTOU.
- Chọn cơ chế theo phạm vi thu hồi, mức độ rủi ro, yêu cầu khả dụng và độ trễ chấp nhận được; không có một kỹ thuật duy nhất giải quyết mọi tình huống.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token, các registered claims như **exp**, **iat**, **jti**); RFC 8725 (JWT Best Current Practices); RFC 7662 (OAuth 2.0 Token Introspection); RFC 7009 (OAuth 2.0 Token Revocation); RFC 6749 (OAuth 2.0 Authorization Framework); RFC 9700 (Best Current Practice for OAuth 2.0 Security). Các RFC mô tả cơ chế token và giao thức; chính sách thu hồi quyền, SLO và nhất quán phân tán vẫn phải được hệ thống cụ thể thiết kế.
