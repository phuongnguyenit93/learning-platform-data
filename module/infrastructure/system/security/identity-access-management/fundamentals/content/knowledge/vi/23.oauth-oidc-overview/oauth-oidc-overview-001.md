# OAuth 2.0 là gì

## 1. Bài toán: cho ứng dụng truy cập mà không giao mật khẩu

Giả sử Lan dùng một hệ thống quản lý lịch làm việc. Lan muốn ứng dụng **Meeting Planner** đọc các khoảng thời gian đang bận để đề xuất lịch họp. Ứng dụng không cần sửa lịch, xóa sự kiện hay đọc hộp thư của Lan.

Nếu Meeting Planner yêu cầu mật khẩu tài khoản của Lan, ứng dụng có thể nhận nhiều quyền hơn nhu cầu thực tế. Lan cũng khó thu hồi riêng quyền của ứng dụng mà không ảnh hưởng những nơi đang sử dụng cùng mật khẩu.

Một thiết kế phù hợp hơn là:

1. Lan thực hiện việc xác thực tại hệ thống đang quản lý tài khoản của mình.
2. Hệ thống xác định Meeting Planner được phép đọc những dữ liệu nào.
3. Meeting Planner nhận một **access token** đại diện cho quyền truy cập đã được cấp.
4. API lịch kiểm tra token và chính sách trước khi trả dữ liệu.

Trong thiết kế này, Meeting Planner cần khả năng đọc lịch, không cần biết mật khẩu của Lan.

**OAuth 2.0 là một framework cấp quyền truy cập có giới hạn cho ứng dụng vào tài nguyên được bảo vệ.** Ứng dụng có thể truy cập thay mặt người dùng hoặc truy cập theo quyền của chính ứng dụng, tùy trường hợp. Đặc tả nền tảng là [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html).

Từ “framework” cho biết OAuth cung cấp các vai trò và cách trao đổi thông điệp để xây dựng giải pháp cấp quyền. OAuth không tự định nghĩa toàn bộ mô hình tài khoản, chính sách nghiệp vụ hay giao diện quản trị IAM của một tổ chức.

## 2. Bốn vai trò cần phân biệt

Với ví dụ đọc lịch, có bốn vai trò:

| Vai trò | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| Resource owner | Chủ thể có khả năng cấp quyền truy cập tài nguyên; thường là người dùng trong luồng ủy quyền | Lan |
| Client | Ứng dụng yêu cầu quyền truy cập | Meeting Planner |
| Authorization server | Hệ thống đánh giá yêu cầu cấp quyền và phát hành token | Máy chủ cấp quyền của hệ thống lịch |
| Resource server | API lưu giữ hoặc cung cấp tài nguyên được bảo vệ | Calendar API |

Một hệ thống có thể triển khai authorization server và resource server cùng chỗ, nhưng hai trách nhiệm vẫn khác nhau: một bên cấp quyền qua token, một bên thực thi quyền khi nhận yêu cầu API.

Trong tài liệu OAuth, **client là ứng dụng**, không phải tên gọi khác của người dùng hay trình duyệt. Một ứng dụng Spring chạy ở backend vẫn có thể là OAuth client. Một API Java nhận và kiểm tra access token thường đóng vai trò resource server.

Từ cách chia vai trò này, nhóm triển khai có thể xác định rõ trách nhiệm:

- Nhóm quản lý tài khoản quyết định cách Lan xác thực, chẳng hạn mật khẩu kết hợp MFA.
- Nhóm quản lý ứng dụng xác định Meeting Planner được đăng ký với những khả năng nào.
- Nhóm Calendar API quyết định request cụ thể có được đọc lịch của Lan hay không.

Việc Lan vượt qua MFA không đồng nghĩa Meeting Planner được cấp mọi quyền. Đó là hai quyết định khác nhau trong hệ thống IAM.

## 3. Cấp quyền không đồng nghĩa xác thực danh tính

Ba câu hỏi sau giúp đặt OAuth đúng vị trí:

| Câu hỏi | Ví dụ | Cơ chế liên quan |
| --- | --- | --- |
| Ai đang tương tác với hệ thống? | Đây có phải tài khoản của Lan không? | Xác thực, MFA; OIDC khi cần kết quả đăng nhập liên kết |
| Ứng dụng được cấp khả năng truy cập nào? | Meeting Planner có được gọi API đọc lịch không? | OAuth 2.0 |
| Request cụ thể có được phép thực hiện không? | Token này có được đọc lịch thuộc tổ chức khác không? | Kiểm tra token kết hợp RBAC, ABAC và chính sách nghiệp vụ tại API |

Authorization server có thể xác thực người dùng trong quá trình cấp quyền. Tuy nhiên, **OAuth 2.0 tự nó không cung cấp một giao thức đăng nhập người dùng chuẩn cho client**.

Nếu yêu cầu là “Đăng nhập vào Meeting Planner bằng tài khoản của hệ thống danh tính”, OpenID Connect, viết tắt **OIDC**, bổ sung lớp danh tính trên OAuth 2.0. OIDC định nghĩa **ID token** để client kiểm tra kết quả xác thực người dùng. Access token và ID token có mục đích và bên nhận khác nhau; không hoán đổi chúng. Xem [OpenID Connect Core 1.0 — Introduction và ID Token](https://openid.net/specs/openid-connect-core-1_0.html#Introduction).

Ví dụ, Meeting Planner có thể cần hai khả năng độc lập: biết người đang đăng nhập là ai và được đọc lịch của họ. Khi thiết kế, cần viết rõ cả hai yêu cầu thay vì gộp thành câu mơ hồ “tích hợp OAuth login”.

## 4. Scope, access token và những giới hạn của quyền truy cập

### 4.1. Scope mô tả phạm vi được yêu cầu hoặc được cấp

Giả sử hệ thống lịch định nghĩa:

```text
calendar.freebusy.read
calendar.events.read
calendar.events.write
```

Đây là tên scope minh họa do hệ thống lịch thiết kế, không phải bộ tên chuẩn áp dụng cho mọi nhà cung cấp OAuth.

Meeting Planner chỉ cần đề xuất giờ họp, nên nhóm thiết kế chọn `calendar.freebusy.read`. Một ứng dụng lập báo cáo chi tiết sự kiện có thể cần phạm vi khác. Việc chọn scope phải xuất phát từ dữ liệu và thao tác cần thiết, theo nguyên tắc ít quyền nhất.

Đừng coi việc client gửi một scope trong request là bằng chứng client đã được cấp quyền đó. Authorization server còn phải đánh giá cấu hình client, quyền của chủ thể và chính sách cấp quyền.

### 4.2. Access token dùng để truy cập API

Access token là thông tin đại diện cho quyền truy cập mà client đã nhận. Khi dùng bearer token, client thường truyền token qua HTTP header:

```http
GET /v1/calendars/lan/freebusy HTTP/1.1
Host: calendar.example.com
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
```

`ACCESS_TOKEN_PLACEHOLDER` chỉ là ký hiệu minh họa, không phải token thật.

Với **bearer token**, bên có token có thể sử dụng nó mà không cần chứng minh sở hữu khóa mật mã gắn với token đó. Vì vậy, phải bảo vệ token trong lưu trữ và truyền tải; sử dụng HTTPS và tránh để token xuất hiện trong log, thông báo lỗi hoặc ảnh chụp màn hình. Cách dùng bearer token được quy định trong [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html).

Token là một bí mật truy cập. Việc nó không phải mật khẩu của Lan không làm cho việc tiết lộ token trở nên an toàn.

### 4.3. Access token không bắt buộc là JWT

OAuth 2.0 không bắt buộc access token phải có một định dạng duy nhất. Hệ thống có thể dùng token không tự mô tả, thường gọi là **opaque token**, hoặc sử dụng token có cấu trúc theo một profile phù hợp.

Một cách triển khai với opaque token là resource server hỏi authorization server qua cơ chế **introspection** để nhận trạng thái và metadata liên quan. Cơ chế đó được định nghĩa trong [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html).

Việc lựa chọn token cần đi cùng cách API xác minh nó. Đừng xây dựng suy luận “token có dấu chấm nên hợp lệ”, hoặc “giải mã được nội dung token nên có thể tin nội dung đó”. Đọc được dữ liệu và xác thực được nguồn gốc là hai việc khác nhau.

### 4.4. Scope chưa đủ để quyết định quyền trên từng bản ghi

Giả sử token của Meeting Planner cho phép `calendar.freebusy.read`. API vẫn cần phân biệt:

- Lịch đang được yêu cầu có thuộc chủ thể hoặc phạm vi tổ chức được cho phép không?
- Lan có chia sẻ lịch này với ứng dụng theo chính sách đang áp dụng không?
- Lịch có đang bị khóa truy cập vì một quyết định quản trị không?

Một quy tắc thiết kế minh họa là:

```text
Cho phép đọc lịch khi:
  token được xác minh và được chấp nhận cho Calendar API
  VÀ có quyền calendar.freebusy.read
  VÀ lịch thuộc phạm vi mà chủ thể được phép truy cập
  VÀ chính sách hiện tại cho phép thao tác đọc
```

Đây là mô hình tư duy cho ví dụ, không phải cú pháp chính sách chuẩn của OAuth. Nó thể hiện rằng cấp token và thực thi quyền trên đối tượng phải phối hợp với nhau.

## 5. Hình dung một luồng Authorization Code kết hợp PKCE

Trong một luồng có người dùng, ứng dụng có thể sử dụng **Authorization Code** kết hợp **PKCE**, viết đầy đủ là Proof Key for Code Exchange.

Authorization code là giá trị trung gian để đổi lấy token, không phải access token gửi đến API. PKCE ràng buộc quá trình đổi code với một giá trị bí mật do client tạo cho lần giao dịch đó. Cơ chế này giúp bảo vệ khi authorization code bị chặn lấy. Xem [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636.html).

```mermaid
sequenceDiagram
    actor U as Lan
    participant C as Meeting Planner
    participant A as Authorization Server
    participant R as Calendar API
    U->>C: Yêu cầu kết nối lịch
    C->>C: Tạo state, code_verifier và code_challenge
    C-->>U: Chuyển trình duyệt đến authorization endpoint
    U->>A: Xác thực và tham gia bước cấp quyền khi cần
    A-->>U: Chuyển về redirect URI với code và state
    U->>C: Trình duyệt gọi callback
    C->>C: Kiểm tra state và giao dịch đang chờ
    C->>A: Đổi code, gửi code_verifier và xác thực client nếu cần
    A-->>C: Trả access token và metadata
    C->>R: Gọi API bằng access token
    R->>R: Xác minh token và áp dụng chính sách
    R-->>C: Trả dữ liệu được phép
```

Sơ đồ giả định dùng `state` được ràng buộc với giao dịch để chống giả mạo yêu cầu callback. Tùy kiến trúc, phần xử lý callback và giữ token có thể nằm ở backend hoặc một loại client khác; việc vẽ cùng một client không có nghĩa mọi bước phải chạy trong JavaScript trên trình duyệt.

### 5.1. Yêu cầu cấp quyền

Dưới đây là dạng URL minh họa. Các giá trị đại diện phải được thư viện triển khai tạo và mã hóa đúng trước khi sử dụng:

```text
https://auth.example.com/authorize
  ?response_type=code
  &client_id=meeting-planner
  &redirect_uri=https%3A%2F%2Fplanner.example.com%2Foauth%2Fcallback
  &scope=calendar.freebusy.read
  &state=TRANSACTION_BOUND_RANDOM_STATE
  &code_challenge=BASE64URL_SHA256_OF_CODE_VERIFIER
  &code_challenge_method=S256
```

Trong ví dụ, authorization server cần hiểu client `meeting-planner` là ứng dụng nào và địa chỉ callback nào được chấp nhận. Việc ứng dụng gửi một URL trong `redirect_uri` không có nghĩa URL bất kỳ đều được tin cậy.

PKCE dùng hai giá trị liên quan:

```text
code_verifier  = giá trị ngẫu nhiên đủ mạnh, tạo mới cho giao dịch
code_challenge = BASE64URL(SHA256(ASCII(code_verifier))) với phương thức S256
```

Client gửi challenge khi bắt đầu và verifier khi đổi code. Nếu chỉ có code mà không có verifier tương ứng, bên lấy cắp code không đáp ứng được phép kiểm tra PKCE. Các giá trị viết hoa trong ví dụ là placeholder; không sao chép chúng làm hằng số trong ứng dụng.

### 5.2. Tiếp nhận kết quả và gọi API

Sau khi callback được chấp nhận, client đổi authorization code tại token endpoint. Client có khả năng giữ bí mật phải thực hiện phương thức xác thực client theo cấu hình của nó; PKCE không thay thế bước đó.

Client sau đó dùng access token để gọi Calendar API. Trong hệ thống minh họa, nhóm Calendar API cấu hình rõ nguồn phát hành được tin cậy, cách xác minh token và các quyền cần có cho từng thao tác.

Đây là ranh giới quan trọng: việc đổi code thành công chỉ cho biết client đã nhận được token. Nó không có nghĩa Calendar API phải cho phép mọi URL, mọi bản ghi hay mọi hành động mà client yêu cầu tiếp theo.

## 6. Phân biệt các loại giá trị trong luồng

| Giá trị | Vai trò | Bên nhận trong trường hợp thông thường |
| --- | --- | --- |
| Client ID | Định danh ứng dụng đã đăng ký; không phải bí mật tự nó chứng minh quyền sở hữu ứng dụng | Authorization server |
| Client credential | Dùng xác thực một client có khả năng bảo vệ credential | Authorization server |
| Authorization code | Giá trị trung gian, ngắn hạn, dùng một lần trong luồng đổi code | Token endpoint |
| Access token | Đại diện cho quyền truy cập tài nguyên | Resource server |
| Refresh token, nếu được cấp | Xin access token mới theo quyền và chính sách cho phép | Token endpoint |
| ID token trong OIDC | Truyền kết quả xác thực người dùng để client kiểm tra | OIDC client |

Refresh token không phải thành phần bắt buộc của mọi lần cấp token. Nếu được cấp, nó cần được bảo vệ theo chính sách phù hợp; không gửi nó đến Calendar API như một access token.

Với ứng dụng cài trên thiết bị người dùng hoặc mã được phân phối vào trình duyệt, không nên coi một chuỗi nhúng sẵn trong mã là bí mật chỉ ứng dụng hợp lệ có thể biết. Ngược lại, backend do tổ chức kiểm soát có thể có điều kiện bảo vệ credential. Sự khác biệt đó ảnh hưởng cách đăng ký và xác thực client.

Trong ví dụ Meeting Planner, việc lộ Client ID không có cùng ý nghĩa với việc lộ access token hoặc khóa riêng của backend. Kế hoạch xử lý sự cố cần phân loại đúng từng giá trị, thay vì coi tất cả chuỗi liên quan OAuth đều là “mật khẩu”.

## 7. OAuth cũng phục vụ danh tính workload

Không phải mọi tương tác OAuth đều có một người dùng đang ngồi trước màn hình. Giả sử một dịch vụ tổng hợp số liệu cần lấy thống kê lịch trống của các phòng họp do tổ chức quản lý.

Nhóm vận hành có thể cấp quyền riêng cho workload này và chọn **Client Credentials** khi phù hợp với mô hình quyền của hệ thống. Khi đó, dịch vụ truy cập theo quyền của chính nó, không giả định đang thay mặt Lan. Client Credentials dành cho confidential client theo [RFC 6749, mục 4.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4).

Ví dụ về quyết định thiết kế cho workload:

| Nhu cầu | Quyền được thiết kế cho ví dụ | Quyền không cần cấp |
| --- | --- | --- |
| Đếm số giờ phòng họp bị đặt trong tuần | Đọc thống kê phòng họp của đúng tổ chức | Sửa lịch cá nhân của Lan |
| Xuất báo cáo định kỳ | Đọc dữ liệu báo cáo đã được giới hạn | Quản trị tài khoản hoặc xóa sự kiện |

Cần nhận diện workload, quản lý credential, thu hồi quyền khi ngừng dịch vụ và ghi log kiểm toán cho các hành động của nó. Không dùng một tài khoản người dùng có nhiều đặc quyền chỉ vì thuận tiện cho tác vụ chạy nền.

## 8. Những nguyên tắc an toàn ở mức nền tảng

Đặc tả ban đầu không phải tài liệu duy nhất cần đọc khi triển khai mới. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html) cập nhật hướng dẫn bảo mật cho OAuth 2.0, trong đó có các điểm sau:

- Public client dùng Authorization Code phải sử dụng PKCE; confidential client cũng được khuyến nghị dùng PKCE. Chọn `S256` thay vì để lộ verifier trong authorization request.
- Resource Owner Password Credentials grant không được sử dụng. Không thiết kế luồng để ứng dụng thu mật khẩu của người dùng nhằm đổi lấy token.
- Tránh implicit grant và các cách trả trực tiếp access token qua authorization response; ưu tiên luồng đổi code với các biện pháp bảo vệ phù hợp.
- Giới hạn đặc quyền và bên nhận của access token theo nhu cầu; resource server phải từ chối token không dành cho mình.
- Không truyền access token trong query string của URL. Public client có refresh token phải áp dụng rotation hoặc cơ chế ràng buộc bên gửi theo yêu cầu của đặc tả.

Các quyết định áp dụng cho Meeting Planner có thể được diễn giải như sau:

**Giảm dữ liệu tiếp cận.** Nếu chỉ cần tìm giờ rảnh, trả khoảng bận/rảnh thay vì cả tên cuộc họp và nội dung mô tả. Đây là lựa chọn thiết kế sản phẩm và API hỗ trợ nguyên tắc ít quyền nhất.

**Giảm điểm lộ bí mật.** Nhóm hỗ trợ không yêu cầu Lan gửi token thật trong phiếu trợ giúp. Nhóm phát triển kiểm tra cấu hình log để thông tin xác thực không bị ghi vào hệ thống thu thập lỗi.

**Tách vòng đời quyền.** Khi Lan ngừng dùng Meeting Planner, hệ thống phải có phương án chấm dứt khả năng truy cập của ứng dụng. Đăng xuất khỏi giao diện, thu hồi refresh token và làm cho access token đang tồn tại hết hiệu lực là các vấn đề cần được thiết kế riêng; không giả định một nút “Logout” tự động giải quyết tất cả.

**Giữ dấu vết có ích.** Một bản ghi kiểm toán của ví dụ có thể gồm thời điểm, định danh client, hành động, tài nguyên và kết quả cho phép/từ chối. Không cần lưu toàn bộ access token để biết ứng dụng nào đã yêu cầu đọc lịch.

## 9. Các hiểu nhầm thường gặp

| Nhận định | Cách hiểu phù hợp |
| --- | --- |
| “Tích hợp OAuth xong thì phân quyền nghiệp vụ đã xong” | Calendar API còn phải kiểm tra phạm vi tổ chức, đối tượng dữ liệu và chính sách hiện tại |
| “Ứng dụng xin scope nào thì nhận scope đó” | Scope được yêu cầu còn phải qua quyết định cấp quyền; phía sử dụng cần xử lý quyền thực tế được cấp |
| “Có token nghĩa là có thể dùng ở mọi API” | Token cần được chấp nhận cho đúng API và đúng mục đích |
| “OAuth token nào cũng là JWT” | OAuth không áp đặt một định dạng access token duy nhất |
| “PKCE là một client secret mới” | PKCE bảo vệ giao dịch đổi code; credential của confidential client có chức năng riêng |
| “Người dùng đã xác thực nên ứng dụng được toàn quyền” | Xác thực người dùng và cấp quyền cho ứng dụng là hai quyết định khác nhau |
| “Mỗi request OAuth đều cần người dùng bấm đồng ý” | Trải nghiệm tương tác phụ thuộc chính sách và loại luồng; workload có thể hoạt động theo quyền của chính nó |

## 10. Tự áp dụng vào một thiết kế IAM

Giả sử nhóm sản phẩm bổ sung hai tính năng cho Meeting Planner:

1. Đọc khoảng bận/rảnh để đề xuất giờ họp.
2. Khi Lan chủ động xác nhận, tạo một sự kiện mới trong lịch của Lan.

Trước khi chọn thư viện, hãy mô tả các quyết định cần có:

- **Ranh giới tài nguyên:** ứng dụng được đọc lịch nào và được tạo sự kiện vào lịch nào?
- **Phạm vi cấp quyền:** tính năng đầu chỉ cần đọc; tính năng sau có thể cần quyền ghi riêng, được xin vào thời điểm phù hợp.
- **Danh tính thực hiện:** hành động đang thay mặt Lan hay do một workload thực hiện theo quyền của nó?
- **Kiểm tra tại API:** sự kiện mới có thuộc lịch và tổ chức được phép không? Việc Lan có quyền ghi còn hiệu lực không?
- **Vòng đời:** khi Lan rút quyền hoặc tổ chức vô hiệu hóa ứng dụng, những token đang tồn tại được xử lý ra sao?
- **Kiểm toán:** có xác định được client nào tạo sự kiện và chủ thể nào đã cho phép không?

Một phương án phù hợp cho ví dụ là ban đầu chỉ xin quyền đọc bận/rảnh, sau đó mới yêu cầu thêm quyền tạo sự kiện khi tính năng thực sự được sử dụng. Nếu Lan không cấp quyền ghi, ứng dụng vẫn có thể giữ tính năng đề xuất giờ họp và giải thích rõ giới hạn đang có.

Các câu hỏi này kết nối OAuth với phần còn lại của IAM: xác thực và MFA, danh tính người dùng hoặc workload, quyền tối thiểu, kiểm soát trên tài nguyên, vòng đời quyền và kiểm toán. OAuth cung cấp cơ chế để client nhận và sử dụng quyền truy cập; hệ thống vẫn cần thiết kế rõ quyền đó mang ý nghĩa gì trong nghiệp vụ.
