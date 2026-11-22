# Chọn thông tin cần chứa và thông tin cần tra cứu bên ngoài

## 1. JWT không phải bản sao của cơ sở dữ liệu

Một **JSON Web Token (JWT)** mang các claim do bên phát hành (*issuer*) đưa ra tại thời điểm phát hành. Khi token được ký, bên nhận có thể kiểm tra tính toàn vẹn và nguồn ký theo khóa tin cậy. Những claim đó là **khẳng định tại một thời điểm**, không phải bản sao luôn cập nhật của hồ sơ người dùng, quyền truy cập hay trạng thái nghiệp vụ.

Ví dụ, token được phát hành lúc người dùng còn là thành viên của cửa hàng `store_17`. Mười phút sau, người dùng bị thu hồi tư cách thành viên. Chữ ký của token vẫn hợp lệ và claim `store_id` vẫn giữ nguyên; token không tự biết sự thay đổi vừa xảy ra.

Vì vậy, khi thiết kế JWT cần quyết định rõ:

- Thông tin nào cần có ngay trong token để consumer xác định chủ thể, mục đích và ngữ cảnh của yêu cầu?
- Thông tin nào đủ ổn định để dùng như một snapshot trong thời hạn token?
- Thông tin nào phải lấy từ hệ thống đang sở hữu dữ liệu tại thời điểm xử lý?
- Khi thông tin thay đổi, hệ thống chấp nhận độ trễ bao lâu trước khi quyết định truy cập phản ánh thay đổi đó?

**Mục tiêu là mang theo lượng thông tin vừa đủ cho quyết định đã xác định, còn dữ liệu cần độ tươi cao phải được kiểm tra tại nguồn có thẩm quyền.** JWT tự chứa giúp giảm một số lần tra cứu, nhưng không loại bỏ nhu cầu đọc dữ liệu nghiệp vụ.

## 2. Hai cách cung cấp thông tin cho consumer

### 2.1. Mang claim trong token

Issuer đưa thông tin vào JWT Claims Set. Consumer xác minh token, sau đó đọc các claim cần thiết mà không cần gọi issuer để lấy lại chính những giá trị đó.

Ví dụ:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "iat": 1893456000,
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read orders:create"
}
```

Trong hợp đồng minh họa:

- `iss`, `sub`, `aud`, `iat`, `exp` là registered claims theo RFC 7519.
- `tenant_id` là ngữ cảnh tenant do hệ thống quy ước.
- `scope` là quy ước phổ biến trong các hồ sơ OAuth; JWT không tự quy định mọi cách đặt tên hoặc ngữ nghĩa scope.

Token có thể được xác minh cục bộ tại nhiều API nếu chúng có khóa tin cậy và cùng áp dụng một hồ sơ xác minh. Điều này giảm phụ thuộc vào một dịch vụ tra cứu trong đường đi của mỗi yêu cầu.

Đổi lại, giá trị claim là snapshot tại thời điểm phát hành. Nếu quyền, trạng thái hoặc quan hệ nghiệp vụ thay đổi, consumer có thể tiếp tục sử dụng snapshot cũ cho đến khi token hết hạn hoặc có cơ chế thu hồi/kiểm tra bổ sung.

### 2.2. Chỉ mang định danh/ngữ cảnh rồi tra cứu bên ngoài

Token có thể chỉ mang định danh ổn định và thông tin tối thiểu để consumer biết cần tra cứu gì. API dùng định danh đó để hỏi hệ thống sở hữu dữ liệu, dịch vụ entitlement, policy decision point hoặc kho dữ liệu nghiệp vụ.

Ví dụ, token có `sub = "user_42"` và `tenant_id = "tenant_17"`. Khi người dùng yêu cầu đọc đơn hàng, API truy vấn dịch vụ phân quyền để kiểm tra:

- Người dùng còn là thành viên tenant đó không?
- Người dùng hiện có quyền `orders:read` không?
- Người dùng có quan hệ được phép với đơn hàng cụ thể không?
- Tài khoản, tenant hoặc đơn hàng có đang ở trạng thái cho phép không?

Kết quả tra cứu phản ánh trạng thái gần với thời điểm xử lý hơn, tùy mức nhất quán của nguồn dữ liệu. Tuy nhiên, API phải chịu thêm độ trễ mạng, phụ thuộc khả dụng của dịch vụ, chi phí vận hành và các tình huống lỗi khi tra cứu.

### 2.3. Mô hình kết hợp

Nhiều hệ thống dùng **mô hình kết hợp**: JWT mang định danh, audience, thời hạn, ngữ cảnh và phạm vi truy cập thô; API tra cứu các quyền hoặc trạng thái thay đổi nhanh.

```text
Client
  |
  | Access token
  v
API nhận yêu cầu
  |
  +--> Xác minh chữ ký, iss, aud, exp, loại token
  |
  +--> Đọc sub, tenant_id, scope
  |
  +--> Kiểm tra scope có cho phép gọi chức năng?
  |
  +--> Tra cứu trạng thái/quyền hiện hành khi cần
  |       |
  |       +--> Identity / Membership / Entitlement / Policy
  |       +--> Dữ liệu tài nguyên và trạng thái nghiệp vụ
  |
  +--> Kết hợp kết quả với chính sách truy cập
          |
          +--> Cho phép hoặc từ chối
```

Mô hình kết hợp thường cân bằng được hiệu năng và độ tươi dữ liệu. Không có một tỷ lệ cố định giữa claims và tra cứu ngoài; ranh giới cần dựa trên yêu cầu nghiệp vụ và mức rủi ro.

## 3. Tiêu chí quyết định thông tin nào nên nằm trong JWT

### 3.1. Độ ổn định của thông tin

Thông tin ít thay đổi trong thời hạn token thường phù hợp hơn để mang theo. Ví dụ, định danh chủ thể ổn định, issuer, audience và một số ngữ cảnh đã được xác nhận tại thời điểm cấp token.

Thông tin thay đổi liên tục như số dư, hạn mức còn lại, trạng thái đơn hàng hoặc điểm rủi ro thường nên được lấy từ nguồn có thẩm quyền khi cần. Nếu đưa vào token, consumer có thể sử dụng một giá trị đã lỗi thời.

Hãy hỏi: **Nếu giá trị này thay đổi ngay sau khi token được phát hành, điều gì sẽ xảy ra?** Nếu hệ thống vẫn có thể chấp nhận giá trị cũ trong một khoảng thời gian xác định, snapshot có thể phù hợp. Nếu giá trị cũ gây thiệt hại hoặc vi phạm chính sách, cần tra cứu hoặc cơ chế cập nhật/thu hồi nhanh hơn.

### 3.2. Yêu cầu về độ trễ thu hồi

Độ trễ thu hồi là khoảng thời gian từ lúc một thay đổi có hiệu lực ở nguồn dữ liệu đến lúc mọi quyết định truy cập phản ánh thay đổi đó.

Ví dụ:

- Một nhân viên chuyển cửa hàng có thể được phép dùng ngữ cảnh cũ thêm vài phút trong một hệ thống rủi ro thấp.
- Một tài khoản bị vô hiệu hóa do sự cố bảo mật có thể cần mất quyền truy cập gần như ngay lập tức.
- Một giao dịch vượt hạn mức phải được kiểm tra theo số dư/hạn mức hiện hành, không dựa trên snapshot đã phát hành từ trước.

JWT sống lâu và chỉ kiểm tra cục bộ thường tạo ra cửa sổ sử dụng claims cũ. Nếu yêu cầu thu hồi nhanh, cân nhắc token ngắn hạn, tra cứu trạng thái, danh sách thu hồi, token introspection hoặc một cơ chế cập nhật quyền tương đương. Mỗi phương án có chi phí và giới hạn riêng.

### 3.3. Nguồn có thẩm quyền

Mỗi thông tin cần có một **nguồn sự thật (source of truth)**:

| Thông tin | Nguồn thường có thẩm quyền |
| --- | --- |
| Định danh chủ thể được cấp | Hệ thống định danh |
| Quan hệ thành viên tenant | Dịch vụ quản lý tổ chức/thành viên |
| Quyền theo vai trò hiện hành | Hệ thống quản lý quyền hoặc policy service |
| Chủ sở hữu đơn hàng | Dịch vụ quản lý đơn hàng |
| Trạng thái đơn hàng | Hệ thống xử lý đơn hàng |
| Số dư và hạn mức | Hệ thống tài chính/sổ cái có thẩm quyền |
| Tình trạng rủi ro tức thời | Hệ thống phát hiện gian lận hoặc quản trị rủi ro |

Issuer chỉ nên đưa một khẳng định vào token nếu có thẩm quyền xác nhận khẳng định đó và consumer hiểu rõ ngữ nghĩa. Không nên dùng một claim được phát hành từ dữ liệu sao chép hoặc cache cũ làm nguồn quyết định cuối cùng cho thông tin cần độ tươi cao.

### 3.4. Kích thước token và chi phí truyền tải

Mỗi claim làm payload lớn hơn. Khi token được gửi theo từng yêu cầu HTTP, kích thước tăng có thể làm tăng:

- Dung lượng header hoặc cookie.
- Băng thông giữa client, proxy, gateway và API.
- Chi phí chuyển đổi Base64URL, ký/xác minh mật mã và phân tích JSON.
- Nguy cơ vượt giới hạn header của một thành phần trung gian.
- Rủi ro token bị ghi vào log hoặc công cụ quan sát với nhiều dữ liệu hơn.

Một mảng hàng trăm quyền, danh sách nhóm lớn hoặc hồ sơ cá nhân đầy đủ thường không phù hợp với access token. Chỉ mang các thông tin thật sự cần trong đường đi của yêu cầu; dữ liệu chi tiết nên được truy vấn khi chức năng cần đến.

### 3.5. Quyền riêng tư và tối thiểu hóa dữ liệu

JWT ký theo JWS không mặc nhiên mã hóa payload. Người giữ token thường có thể giải mã phần payload và đọc claims. Token cũng có thể xuất hiện trong bộ nhớ client, log, trace, URL do cấu hình sai hoặc các hệ thống trung gian.

Không đưa vào JWT những dữ liệu không cần thiết như:

- Mật khẩu, bí mật xác thực, khóa riêng hoặc credential có thể dùng lại.
- Số dư tài chính, dữ liệu thanh toán chi tiết hoặc thông tin nhạy cảm nếu API không cần chúng.
- Hồ sơ cá nhân đầy đủ, địa chỉ, số điện thoại hoặc dữ liệu nhận dạng không phục vụ quyết định truy cập.
- Danh sách tài nguyên dài hoặc thông tin nội bộ có thể tiết lộ cấu trúc hệ thống.

Nếu cần bảo mật nội dung token, JWE có thể bảo vệ tính bí mật theo mô hình khóa phù hợp, nhưng mã hóa không thay thế việc giảm thiểu dữ liệu. Bên nhận vẫn phải kiểm tra quyền truy cập và xử lý dữ liệu theo chính sách.

### 3.6. Độ trễ và khả dụng của hệ thống tra cứu

Tra cứu bên ngoài tạo một phụ thuộc trong đường đi của yêu cầu. Nếu dịch vụ entitlement chậm hoặc ngừng hoạt động, API có thể không đưa ra quyết định kịp thời.

Đánh giá:

- Độ trễ p95/p99 của tra cứu và ngân sách thời gian của API.
- Khả năng sẵn sàng của dịch vụ nguồn.
- Số lượng yêu cầu đồng thời và nguy cơ tạo tải dây chuyền.
- Khả năng cache, batch hoặc gộp truy vấn.
- Hành vi khi timeout, lỗi mạng hoặc dữ liệu nguồn không nhất quán.

Với quyết định bảo mật, không nên mặc định cho phép truy cập khi không tra cứu được dữ liệu bắt buộc. Nếu chính sách cho phép dùng cache khi nguồn tạm lỗi, phải xác định trước dữ liệu nào được cache, tuổi tối đa và giới hạn rủi ro.

## 4. Bảng quyết định: đưa vào token hay tra cứu?

| Loại thông tin | Lựa chọn thường phù hợp | Lý do và lưu ý |
| --- | --- | --- |
| Issuer, subject, audience, expiration | Claim trong JWT | Là thông tin cốt lõi để xác định nguồn, chủ thể, bên nhận và thời hạn token |
| Định danh tenant đang chọn | Có thể đưa vào JWT | Là ngữ cảnh của token; vẫn phải kiểm tra tenant của tài nguyên và membership khi chính sách yêu cầu |
| Scope thô cho API | Có thể đưa vào JWT | Giúp kiểm tra phạm vi endpoint; cần hiểu đây là quyền được cấp tại thời điểm phát hành |
| Vai trò ít thay đổi, chấp nhận snapshot | Có thể đưa vào JWT | Giảm tra cứu; phải giới hạn thời gian sử dụng claims cũ |
| Thành viên tenant có thể bị thu hồi ngay | Tra cứu hoặc kết hợp | Cần phản ánh thay đổi membership nhanh |
| Quyền trên từng đơn hàng/tài liệu | Tra cứu dữ liệu và chính sách | Phụ thuộc chủ sở hữu, trạng thái và quan hệ với tài nguyên cụ thể |
| Số dư, hạn mức, tồn kho | Tra cứu nguồn có thẩm quyền | Giá trị thay đổi thường xuyên và có thể ảnh hưởng quyết định tài chính/nghiệp vụ |
| Trạng thái khóa tài khoản, rủi ro tức thời | Tra cứu hoặc kiểm tra trạng thái bổ sung | Cần phản ánh các sự kiện bảo mật mới |
| Hồ sơ người dùng đầy đủ | Tra cứu khi cần | Tránh token lớn, lộ dữ liệu và dữ liệu lỗi thời |
| Feature flag hoặc cấu hình thay đổi thường xuyên | Thường tra cứu/cache riêng | Không nên phát hành lại token mỗi lần cấu hình thay đổi |

Đây là hướng dẫn lựa chọn, không phải quy tắc tuyệt đối. Ví dụ, một hệ thống có thể đưa entitlement vào token nếu nghiệp vụ chấp nhận snapshot trong 5 phút và có cơ chế thu hồi phù hợp. Một hệ thống khác có thể yêu cầu tra cứu mỗi lần vì hậu quả của quyền cũ quá lớn.

## 5. Ví dụ: API đơn hàng đa tenant

### 5.1. Chỉ mang thông tin cần thiết trong token

Giả sử một nền tảng bán hàng có nhiều tenant. Access token có thể chứa:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "iat": 1893456000,
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read orders:create"
}
```

Token cho biết issuer, chủ thể, API đích, thời gian, tenant đang chọn và scope được cấp. Nó không chứa danh sách tất cả đơn hàng, trạng thái tài khoản, quan hệ membership chi tiết hoặc quyền sở hữu từng đơn hàng.

Khi nhận `GET /orders/order_777`, API có thể:

1. Xác minh chữ ký, issuer, audience, thời gian và loại token.
2. Kiểm tra `scope` có cho phép gọi chức năng đọc đơn hàng.
3. Đọc `sub` và `tenant_id` từ claims đã xác minh.
4. Tải đơn hàng từ dịch vụ sở hữu dữ liệu.
5. Kiểm tra đơn hàng có thuộc `tenant_17` không.
6. Kiểm tra membership, quyền theo tài nguyên và trạng thái tài khoản nếu chính sách yêu cầu.
7. Chỉ trả dữ liệu nếu tất cả điều kiện bắt buộc đạt.

### 5.2. Vì sao không nhúng toàn bộ quyền vào token?

Giả sử người dùng có quyền đọc 2.000 đơn hàng. Nếu issuer đưa danh sách ID của cả 2.000 đơn vào token, token sẽ lớn, khó truyền tải, dễ vượt giới hạn header và nhanh chóng lỗi thời khi quyền sở hữu thay đổi.

Thay vào đó, token mang định danh chủ thể và tenant. API truy vấn quan hệ giữa người dùng với đơn hàng cần đọc. Nếu có thể, dịch vụ đơn hàng nên kiểm tra quyền trong cùng truy vấn hoặc cùng transaction với thao tác đọc, tránh tải dữ liệu xong rồi áp dụng một quyết định đã cũ.

### 5.3. Khi nào có thể cache kết quả tra cứu?

Nếu membership được truy vấn nhiều lần, API có thể cache kết quả trong thời gian ngắn để giảm độ trễ. Tuy nhiên, cache tạo ra một cửa sổ dữ liệu cũ. Nếu TTL là 30 giây, thay đổi membership có thể chưa được phản ánh trong tối đa khoảng thời gian đó, cộng thêm độ trễ đồng bộ và xử lý invalidation.

Với quyền có rủi ro cao, có thể cần TTL ngắn hơn, cơ chế invalidation theo sự kiện hoặc truy vấn trực tiếp. Không dùng cache vô thời hạn cho quyền có thể bị thu hồi.

## 6. Đánh đổi khi tra cứu trạng thái bên ngoài

### 6.1. Tra cứu trực tiếp theo từng yêu cầu

API gọi nguồn có thẩm quyền mỗi khi cần quyết định. Cách này phù hợp khi dữ liệu thay đổi thường xuyên hoặc yêu cầu thu hồi nhanh. Đổi lại, độ trễ và khả dụng của nguồn trở thành một phần của độ trễ/khả dụng API.

Nên đặt timeout, giới hạn retry, circuit breaker và ngân sách độ trễ phù hợp. Retry không kiểm soát có thể làm sự cố của dịch vụ nguồn trở nên nghiêm trọng hơn.

### 6.2. Cache có thời hạn

Cache giúp giảm tải và độ trễ, nhưng phải mô tả rõ:

- Key cache bao gồm định danh nào, ví dụ issuer, subject, tenant và loại quyền.
- TTL tối đa cho từng loại dữ liệu.
- Cách invalidation khi quyền bị thay đổi hoặc thu hồi.
- Hành vi khi dữ liệu hết hạn mà nguồn không truy cập được.
- Có cho phép dùng stale value khi lỗi hay không và trong giới hạn nào.

Không cache chỉ theo `sub` nếu quyền còn phụ thuộc tenant hoặc audience; dễ dùng nhầm kết quả của ngữ cảnh khác. Cache phải được phân vùng theo đúng các yếu tố ảnh hưởng quyết định.

### 6.3. Event-driven invalidation

Nguồn dữ liệu có thể phát sự kiện khi người dùng bị khóa, rời tenant hoặc thay đổi vai trò. Các API nhận sự kiện và xóa cache liên quan. Cách này giảm cửa sổ dữ liệu cũ nhưng phụ thuộc khả năng phát sự kiện, giao nhận, thứ tự và xử lý lại.

Sự kiện có thể bị trễ hoặc thất lạc. Với quyết định quan trọng, nên có cơ chế đối soát hoặc giới hạn tuổi cache; không giả định event-driven invalidation luôn tức thời.

### 6.4. Introspection hoặc trạng thái token tập trung

Trong một số kiến trúc, API có thể hỏi authorization server về trạng thái token hoặc thông tin liên quan thay vì chỉ xác minh JWT cục bộ. OAuth Token Introspection (RFC 7662) định nghĩa cách một resource server hỏi authorization server về trạng thái token, thường gồm trạng thái active và metadata được phép trả về.

Introspection hữu ích khi cần trạng thái tập trung hoặc token có thể bị thu hồi trước hạn. Nó thêm một lần gọi mạng và cần kiểm soát xác thực giữa resource server với authorization server. Không phải mọi JWT đều bắt buộc phải dùng introspection; lựa chọn phụ thuộc yêu cầu thu hồi và kiến trúc.

## 7. Cache, nhất quán và giới hạn thời gian sử dụng

### 7.1. Xác định độ trễ chấp nhận được

Trước khi chọn TTL hoặc thời hạn JWT, hãy xác định yêu cầu nghiệp vụ:

| Dữ liệu/quyết định | Ví dụ yêu cầu | Hướng cân nhắc |
| --- | --- | --- |
| Ngữ cảnh giao diện ít rủi ro | Chấp nhận thay đổi chậm vài phút | Snapshot hoặc cache ngắn có thể đủ |
| Membership tenant | Thu hồi trong vòng vài chục giây | Cache ngắn và invalidation; cân nhắc kiểm tra trực tiếp |
| Tài khoản bị khóa do sự cố | Thu hồi gần như tức thời | Kiểm tra trạng thái tập trung hoặc cơ chế thu hồi nhanh |
| Số dư/hạn mức giao dịch | Phải phản ánh giá trị hiện tại | Đọc nguồn tài chính có thẩm quyền, có kiểm soát đồng thời |
| Quyền sở hữu tài nguyên | Phải đúng tại thời điểm thao tác | Kiểm tra cùng truy vấn/transaction khi có thể |

Các con số thời gian là yêu cầu ví dụ, không phải giá trị mặc định cho mọi hệ thống. Chủ sở hữu nghiệp vụ và bảo mật cần thống nhất mức rủi ro chấp nhận được.

### 7.2. JWT expiration không phải cơ chế thu hồi tức thời

`exp` giới hạn thời điểm token không còn được chấp nhận. Nó không làm token bị vô hiệu ngay khi một quyền bị thu hồi. Nếu access token còn hạn 15 phút và API chỉ kiểm tra chữ ký cùng `exp`, snapshot claims có thể được sử dụng trong phần thời gian còn lại.

Các biện pháp có thể kết hợp:

- Access token có thời hạn ngắn phù hợp với mức rủi ro.
- Tra cứu trạng thái tài khoản hoặc entitlement hiện hành.
- Danh sách thu hồi theo `jti` hoặc một định danh phiên/token phù hợp.
- Introspection hoặc cơ chế kiểm tra trạng thái tập trung.
- Xoay khóa khi cần vô hiệu hóa token ký bằng khóa bị xâm phạm, có đánh giá phạm vi ảnh hưởng.

Không có một biện pháp đơn lẻ phù hợp cho mọi tình huống. Chọn theo độ trễ thu hồi, quy mô hệ thống, khả năng chịu lỗi và chi phí vận hành.

### 7.3. Tránh lỗi TOCTOU

TOCTOU (*time-of-check to time-of-use*) xảy ra khi quyền được kiểm tra ở một thời điểm nhưng trạng thái tài nguyên thay đổi trước khi thao tác thực sự diễn ra.

Ví dụ:

1. API kiểm tra người dùng là chủ sở hữu đơn hàng.
2. Đơn hàng được chuyển sang tài khoản khác.
3. API vẫn thực hiện thao tác dựa trên kết quả kiểm tra cũ.

Với hành động nhạy cảm, cần gắn kiểm tra quyền với thao tác tài nguyên trong cùng transaction, truy vấn có điều kiện hoặc cơ chế khóa/kiểm soát đồng thời phù hợp. Cache hoặc claim trong token không giải quyết được cửa sổ TOCTOU ở dữ liệu thay đổi nhanh.

## 8. Chính sách khi dịch vụ tra cứu gặp lỗi

Nếu một quyết định yêu cầu dữ liệu hiện hành nhưng dịch vụ nguồn timeout, API cần có hành vi đã được thiết kế trước:

| Tình huống | Cách xử lý thường an toàn |
| --- | --- |
| Không tra cứu được quyền bắt buộc | Từ chối tạm thời hoặc trả lỗi dịch vụ phù hợp; không tự cấp quyền |
| Cache còn trong TTL cho phép | Dùng theo chính sách cache đã công bố |
| Cache đã quá hạn | Không dùng stale data nếu chính sách không cho phép |
| Nguồn trả về “không có quyền” | Từ chối truy cập |
| Nguồn trả dữ liệu sai kiểu/không đầy đủ | Xem là lỗi dữ liệu; không suy đoán quyền |
| Sự kiện invalidation bị trễ | Áp dụng TTL tối đa và cơ chế đối soát |

**Fail closed** là nguyên tắc phù hợp cho quyết định phân quyền: nếu không có đủ thông tin đáng tin cậy để chứng minh quyền, không cho phép hành động. Điều này không có nghĩa mọi lỗi đều phải trả HTTP 403; lỗi phụ thuộc dịch vụ có thể cần phản hồi 503 hoặc mã lỗi phù hợp để phân biệt với trường hợp người dùng thực sự không có quyền.

Chỉ dùng stale cache khi chủ sở hữu nghiệp vụ chấp nhận rõ ràng rủi ro và đã xác định loại thao tác nào được phép. Không áp dụng một chính sách fallback chung cho cả đọc dữ liệu ít nhạy cảm và giao dịch tài chính.

## 9. Quy trình chọn claim hay tra cứu

Với mỗi thông tin dự kiến đưa vào JWT, có thể đi theo các bước:

1. **Xác định quyết định cần thông tin.** Thông tin dùng để định danh, chọn ngữ cảnh, kiểm tra scope hay quyết định quyền trên một tài nguyên?
2. **Xác định nguồn sự thật.** Thành phần nào có quyền xác nhận và cập nhật thông tin?
3. **Đánh giá độ biến động.** Giá trị có thể thay đổi trong thời hạn token không? Nếu thay đổi, hậu quả của việc dùng giá trị cũ là gì?
4. **Đặt mục tiêu thu hồi.** Hệ thống cần phản ánh thay đổi trong vài giây, vài phút hay chấp nhận đến khi token hết hạn?
5. **Đánh giá chi phí.** So sánh kích thước token, quyền riêng tư, độ trễ, khả dụng và chi phí tra cứu.
6. **Chọn cách cung cấp.** Đưa vào claim, tra cứu trực tiếp, cache có giới hạn hoặc kết hợp.
7. **Định nghĩa fallback.** Khi nguồn lỗi hoặc dữ liệu không hợp lệ, cho phép, từ chối hay dùng cache trong giới hạn nào?
8. **Kiểm thử thay đổi trạng thái.** Kiểm thử thu hồi quyền, chuyển tenant, khóa tài khoản, thay đổi chủ sở hữu và sự cố dịch vụ tra cứu.

Một câu hỏi hữu ích để chốt thiết kế: **Nếu dữ liệu này đổi ngay sau khi JWT được phát hành, API có được phép tiếp tục tin giá trị cũ không?** Nếu câu trả lời là không, thông tin đó cần được kiểm tra ở nguồn có thẩm quyền hoặc có cơ chế thu hồi/cập nhật đủ nhanh.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Đưa toàn bộ hồ sơ người dùng vào token | Token lớn, lộ dữ liệu và nhanh lỗi thời | Chỉ mang định danh và thông tin cần cho consumer |
| Nhúng danh sách quyền/tài nguyên rất dài | Header lớn, khó cập nhật khi quan hệ thay đổi | Tra cứu quyền theo tài nguyên hoặc dùng policy service |
| Cho rằng chữ ký hợp lệ nghĩa là dữ liệu còn mới | Quyền đã thu hồi vẫn được dùng | Giới hạn tuổi token hoặc kiểm tra trạng thái hiện hành |
| Tra cứu bên ngoài nhưng không có timeout | API bị treo khi dịch vụ nguồn chậm | Đặt timeout, ngân sách độ trễ và giới hạn retry |
| Cho phép truy cập khi dịch vụ phân quyền lỗi | Có thể cấp quyền khi không xác minh được | Fail closed cho quyết định bảo mật bắt buộc |
| Cache quyền không có TTL/invalidation | Quyền cũ tồn tại không giới hạn | Đặt tuổi tối đa, invalidation và đối soát |
| Cache chỉ theo subject | Dùng nhầm quyền giữa tenant hoặc audience | Bao gồm mọi yếu tố ảnh hưởng quyết định vào cache key |
| Kiểm tra quyền tách xa thao tác tài nguyên | Có thể phát sinh TOCTOU | Gắn kiểm tra với truy vấn/transaction khi có thể |
| Đưa dữ liệu nhạy cảm vào JWT ký | Người giữ token có thể đọc payload | Giảm thiểu dữ liệu; dùng JWE khi thật sự cần bí mật |

## 11. Tình huống tự kiểm tra

Một nhân viên nhận access token lúc 09:00. Token có `sub`, `tenant_id`, `scope = "orders:read"` và hết hạn lúc 09:15. Đến 09:05, quản trị viên thu hồi quyền thành viên của nhân viên trong tenant. API chỉ xác minh chữ ký, `iss`, `aud`, `exp` và scope cục bộ; không tra cứu membership hoặc trạng thái token.

**Câu hỏi:** API có thể tiếp tục chấp nhận yêu cầu đọc đơn hàng lúc 09:06 không?

**Trả lời:** Theo cách triển khai đã mô tả, có thể token vẫn vượt qua các kiểm tra cục bộ vì chữ ký và thời hạn còn hợp lệ. Điều đó cho thấy quyết định vẫn dựa trên snapshot cũ. Nếu nghiệp vụ yêu cầu thu hồi membership ngay, API phải bổ sung kiểm tra trạng thái hiện hành hoặc cơ chế thu hồi có độ trễ đáp ứng yêu cầu. Nếu nghiệp vụ chấp nhận cửa sổ đến 09:15, cần ghi rõ rủi ro và bảo đảm thời hạn token thực sự giới hạn cửa sổ đó.

**Câu hỏi tiếp:** Nếu dịch vụ membership không truy cập được lúc 09:06, API có nên mặc định cho phép?

**Trả lời:** Không, nếu membership là điều kiện bắt buộc để chứng minh quyền. API nên từ chối tạm thời hoặc dùng cache còn trong giới hạn đã được phê duyệt; không tự suy luận rằng quyền vẫn tồn tại.

## 12. Ghi nhớ

JWT phù hợp để mang các khẳng định gọn, có ý nghĩa rõ và đủ ổn định trong thời hạn token. Những thông tin thay đổi nhanh, cần thu hồi ngay, phụ thuộc trạng thái tài nguyên hoặc có hậu quả lớn khi bị lỗi thời nên được lấy từ nguồn có thẩm quyền tại thời điểm cần thiết.

Trong thực tế, mô hình kết hợp thường hiệu quả: token mang định danh, audience, thời hạn, ngữ cảnh và phạm vi thô; API tra cứu membership, entitlement, trạng thái và quyền trên tài nguyên khi yêu cầu nghiệp vụ đòi hỏi. Hãy định nghĩa rõ độ trễ thu hồi, chính sách cache, hành vi khi nguồn lỗi và cách giữ kiểm tra quyền gần với thao tác tài nguyên.

**Chọn claim hay tra cứu là một quyết định về độ tươi, ranh giới tin cậy và chi phí vận hành.** Thiết kế tốt giúp API vừa tránh phụ thuộc không cần thiết vào các dịch vụ tra cứu, vừa không dùng snapshot cũ cho những quyết định cần dữ liệu hiện hành.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims Set, registered claims và NumericDate.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành bảo mật khi xác minh và sử dụng JWT.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cơ chế resource server truy vấn authorization server về trạng thái token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): hồ sơ JWT access token trong OAuth 2.0.
