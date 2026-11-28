# Authentication boundary

## 1. Ranh giới xác thực là gì?

**Authentication boundary** là ranh giới mà tại đó một thành phần quyết định có chấp nhận một bằng chứng danh tính và tạo ra ngữ cảnh đã xác thực để sử dụng hay không. Trước ranh giới, các dữ liệu như tên người dùng, token, cookie, header hoặc chứng thư chỉ là đầu vào cần kiểm tra. Sau khi vượt qua kiểm tra theo hợp đồng, hệ thống mới được dùng danh tính cùng các điều kiện tin cậy đã xác định.

Ví dụ, một API nhận request có header `Authorization`. Sự hiện diện của header không chứng minh người gọi đã được xác thực. API hoặc thành phần được nó tin cậy phải xác minh loại credential, nguồn phát hành, đối tượng nhận, hiệu lực và các ràng buộc cần thiết trước khi tạo security context.

Ranh giới xác thực là một ranh giới **logic và thẩm quyền tin cậy**, không chỉ là đường mạng. Nó có thể nằm ở IdP, callback SSO, gateway, bộ lọc bảo mật trong service, một endpoint quản trị hoặc một consumer nhận message. Cùng một request có thể đi qua nhiều ranh giới, mỗi nơi kiểm tra một loại bằng chứng khác nhau.

Điểm quan trọng là nhận diện chính xác **điều gì đã được xác thực, bởi ai, cho bên nhận nào và còn hiệu lực đến đâu**. Câu “request đã qua nội bộ” hoặc “người dùng đã đăng nhập ở đâu đó” không trả lời đủ các câu hỏi này.

## 2. Phân biệt với các ranh giới liên quan

| Khái niệm | Câu hỏi chính | Không tự chứng minh |
| --- | --- | --- |
| Ranh giới mạng | Gói tin đi từ vùng mạng nào sang vùng nào? | Caller có danh tính hợp lệ |
| Ranh giới xác thực | Bằng chứng danh tính nào được chấp nhận? | Danh tính đó có quyền thực hiện thao tác |
| Ranh giới phân quyền | Subject có được làm hành động này trên tài nguyên này không? | Credential ban đầu đã được kiểm tra đúng |
| Ranh giới phiên | Trạng thái đăng nhập được tạo, tiếp tục và kết thúc thế nào? | Người dùng vừa xác thực lại cho thao tác nhạy cảm |
| Ranh giới quản trị | Ai có quyền thay đổi trust, credential hoặc phương thức xác thực? | Thay đổi được yêu cầu là hợp lệ chỉ vì tài khoản đã đăng nhập |

Xác thực và phân quyền thường nằm cạnh nhau nhưng cần tách trách nhiệm. Một người dùng có token hợp lệ cho API vẫn có thể bị từ chối khi sửa tài nguyên của tenant khác. Ngược lại, kiểm tra `role=admin` từ một payload chưa được xác minh không tạo ra quyết định quyền đáng tin cậy.

Transport được bảo vệ cũng không thay thế mọi xác thực. TLS có thể bảo vệ kênh và xác thực server; mTLS có thể xác thực danh tính đầu cuối của kết nối theo cấu hình trust. Điều đó chưa tự xác định người dùng cuối đang được đại diện, cũng chưa cấp quyền cho mọi hành động của ứng dụng.

## 3. Một hợp đồng ranh giới cần nêu những gì?

Mỗi authentication boundary nên có hợp đồng rõ giữa thành phần nhận và các bên cung cấp bằng chứng.

| Thành phần hợp đồng | Ví dụ câu hỏi cần trả lời |
| --- | --- |
| Bên nhận | Đây là callback đăng nhập, API tài nguyên hay endpoint quản trị? |
| Loại bằng chứng | Session cookie, access token, assertion, chứng thư hay credential workload? |
| Nguồn tin cậy | Issuer, IdP, CA, session store hoặc proxy nào được cấu hình tin cậy? |
| Phạm vi sử dụng | Credential dành cho client, API, tenant hoặc môi trường nào? |
| Kiểm tra bắt buộc | Tính toàn vẹn, thời hạn, ràng buộc giao dịch, trạng thái và các điều kiện của giao thức |
| Ngữ cảnh đầu ra | Subject, namespace, actor, phương thức/độ mới xác thực và phạm vi liên quan |
| Hành vi lỗi | Từ chối hay yêu cầu xác thực bổ sung; phân biệt thiếu credential với lỗi phụ thuộc |
| Vòng đời | Tạo, thay thế, hết hạn, thu hồi, logout và xử lý credential cũ |
| Chủ sở hữu | Nhóm nào quản trị cấu hình, vận hành và xử lý sự cố? |

Không chọn nguồn tin cậy chỉ từ dữ liệu do request tự khai. Ví dụ, đọc `iss` chưa xác minh có thể phục vụ định tuyến đến một cấu hình **đã được cho phép**, nhưng không được biến mọi issuer hoặc URL khóa được gửi vào thành một nguồn tin cậy mới.

Cũng cần quy định xử lý khi có nhiều credential cùng xuất hiện. Nếu request mang cả cookie và bearer token, không để hệ thống âm thầm chọn danh tính có quyền cao hơn hoặc ghép thuộc tính từ hai danh tính. Cách chọn hoặc từ chối phải rõ theo từng endpoint.

## 4. Từ đầu vào chưa tin cậy đến security context

Một đường xử lý khái niệm:

```text
Request chưa tin cậy
  → xác định hợp đồng của endpoint và loại credential được phép
  → phân tích đầu vào theo định dạng được hỗ trợ
  → xác minh credential bằng nguồn trust đã cấu hình
  → kiểm tra phạm vi, hiệu lực và ràng buộc cần thiết
  → tạo security context có ngữ nghĩa rõ
  → kiểm tra quyền trên hành động/tài nguyên thực tế
  → thực thi và ghi bằng chứng cần thiết
```

### 4.1. Parse không có nghĩa là verify

Giải mã JWT để đọc JSON chỉ cho biết payload có thể phân tích được. Nó không chứng minh chữ ký đúng, token được phát cho API này hoặc còn được phép sử dụng. Tương tự, đọc được một SAML assertion hoặc một session ID không có nghĩa nội dung đã được chấp nhận.

Thành phần bảo mật phải kiểm tra theo loại credential và giao thức thực tế. Không tự viết một bộ kiểm tra chung chỉ dựa vào `sub` và `exp` rồi dùng cho mọi ID token, access token và assertion.

### 4.2. Danh tính cần có namespace

Một chuỗi subject chỉ có ý nghĩa trong namespace của nguồn phát hành hoặc hệ thống quản lý tương ứng. Cùng một `sub` từ hai issuer khác nhau không mặc định chỉ cùng người.

Khi liên kết tài khoản, phải dựa vào nguồn đã được tin cậy và mapping có kiểm soát. Email hoặc tên hiển thị thường không đủ làm bằng chứng để gộp hai tài khoản. Một lỗi mapping ở ranh giới xác thực có thể làm người dùng nhận được tài khoản hoặc lịch sử của người khác.

### 4.3. Security context không phải bản sao toàn bộ credential

Ngữ cảnh sau xác thực nên chứa các thông tin đã kiểm tra và cần thiết cho xử lý: tham chiếu subject, nguồn phát hành, loại principal, phạm vi tenant được xác minh khi có, thông tin độ mới/mức bảo đảm được hỗ trợ và quan hệ đại diện nếu có.

Không cần lưu raw token, mật khẩu hoặc toàn bộ hồ sơ vào mọi đối tượng context. Một claim đã được ký cũng chỉ đáng tin trong phạm vi ý nghĩa mà issuer được phép khẳng định; chẳng hạn một IdP đối tác không tự có thẩm quyền cấp role quản trị nội bộ.

Security context phải gắn với đúng request hoặc tác vụ. Không dùng biến toàn cục, trạng thái thread chưa được dọn hoặc cache chỉ theo URL khiến danh tính của request trước bị tái sử dụng cho request sau.

## 5. Ranh giới đăng nhập và ranh giới sử dụng phiên

### 5.1. Xác thực ban đầu

Ở luồng đăng nhập, hệ thống kiểm tra bằng chứng mà người dùng cung cấp hoặc điều phối xác thực với IdP. Điều này có thể gồm nhiều bước và MFA theo yêu cầu. Chỉ khi flow đạt kết quả hợp lệ mới tạo trạng thái phiên đã xác thực.

Không tạo phiên có quyền đầy đủ khi mới xác minh xong một bước nếu flow còn yêu cầu yếu tố khác. Trạng thái tạm như “đã nhập đúng mật khẩu, còn chờ MFA” phải khác với trạng thái đăng nhập hoàn tất và không được đi vào các endpoint được bảo vệ như một session đầy đủ.

### 5.2. Xác minh phiên trên request tiếp theo

Ở request sau, ứng dụng thường không hỏi lại mật khẩu mà kiểm tra session credential. Ranh giới lúc này chấp nhận bằng chứng về một phiên đã được thiết lập, theo các điều kiện hết hạn, thu hồi và ràng buộc của phiên.

Session cookie vẫn là đầu vào từ client. Nếu hệ thống dùng session store, cần xác định session có tồn tại, còn hiệu lực và gắn với trạng thái tài khoản nào. Nếu dùng token phiên tự chứa, cần hiểu cơ chế xác minh và giới hạn thu hồi của thiết kế đó.

Tạo hoặc nâng cấp phiên cần xử lý nguy cơ session fixation theo thiết kế của framework. Các thuộc tính bảo vệ cookie và chống CSRF cho thao tác phù hợp cũng là phần của đường bảo vệ phiên; chúng không được thay thế bằng câu “cookie được tạo sau khi đăng nhập”.

### 5.3. Xác thực mới hơn cho thao tác nhạy cảm

Một phiên hợp lệ từ nhiều giờ trước có thể đủ để đọc trang thông thường nhưng không đủ để thêm phương thức MFA, đổi địa chỉ khôi phục hoặc tạo credential đặc quyền. Endpoint nhạy cảm có thể yêu cầu xác thực lại hoặc step-up theo chính sách.

Kiểm tra độ mới và mức bảo đảm từ dữ liệu đã được xác minh hoặc trạng thái server đáng tin cậy. Không tin một field `mfa=true` do client gửi. Có hai phương thức đã đăng ký không đồng nghĩa cả hai vừa được sử dụng trong giao dịch hiện tại.

Ranh giới xác thực không nhất thiết yêu cầu người dùng nhập lại credential ở mọi service hop. Nó yêu cầu mỗi bên nhận có bằng chứng phù hợp với mức tin cậy và hành động của mình; trải nghiệm SSO có thể được giữ khi các ràng buộc đó vẫn đáp ứng.

## 6. Ranh giới federation: từ IdP sang ứng dụng

Khi dùng SSO, có hai việc khác nhau:

1. IdP xác thực người dùng theo chính sách của nó.
2. Ứng dụng xác minh kết quả do IdP cung cấp và quyết định có tạo phiên cục bộ hay không.

MFA thành công tại IdP không tự làm callback bất kỳ trở thành hợp lệ tại ứng dụng. RP/SP phải kiểm tra trust, bên nhận, tính toàn vẹn, thời hạn và các ràng buộc tương quan theo flow được hỗ trợ.

```text
Người dùng ── bằng chứng đăng nhập ──> IdP
                                         │
                         kết quả theo giao thức
                                         │
                                         v
                             Ranh giới tại RP/SP
                                         │
                      xác minh + mapping + tạo phiên
```

Với OIDC, cần phân biệt các vai trò của ID token, access token và các cơ chế ràng buộc giao dịch như `state`, `nonce`, PKCE theo flow và thư viện thực tế. Không coi các cơ chế này là một field chung có thể tùy ý thay thế nhau; cũng không dùng ID token của một ứng dụng làm bằng chứng truy cập mọi API.

Với SAML, xác minh assertion phải theo profile/flow được hỗ trợ, gồm các điều kiện trust và ràng buộc liên quan. Không chấp nhận assertion chỉ vì có tên người dùng hoặc vì được gửi tới một URL callback được biết trước.

Lỗi kiểm tra tương quan, chữ ký hoặc audience phải chặn việc tạo security context. Không chuyển sang mapping tài khoản theo email như một đường dự phòng khi việc xác minh giao thức thất bại.

## 7. Ranh giới giữa gateway và service

### 7.1. Gateway xác thực, service nhận assertion nội bộ

Một mô hình phổ biến là gateway xác minh credential bên ngoài rồi chuyển ngữ cảnh danh tính đến service. Service vẫn cần biết vì sao nó có thể tin thông tin đó.

Các điều kiện thiết kế thường cần có:

- Chỉ các proxy/gateway được cho phép mới có thể đưa assertion danh tính vào đường sử dụng tương ứng.
- Kênh hoặc thông điệp giữa gateway và service được bảo vệ để service xác thực nguồn và tính toàn vẹn theo thiết kế.
- Dữ liệu danh tính từ phía ngoài không được giữ nguyên như một assertion nội bộ đáng tin cậy.
- Service không có đường đi vòng có thể truy cập mà bỏ qua cơ chế xác minh.
- Assertion có phạm vi bên nhận, thời hạn và ngữ nghĩa rõ nếu kiến trúc dùng dạng assertion riêng.

Không đủ nếu chỉ đổi tên header thành `X-Authenticated-User`. Client có thể gửi cùng tên header nếu hệ thống không loại bỏ hoặc xử lý nó đúng tại ranh giới. Một service công khai nhận trực tiếp header đó còn có thể bị giả mạo dù đường chính qua gateway là an toàn.

### 7.2. Service tự xác minh credential

Một lựa chọn khác là gateway thực hiện kiểm tra ban đầu và service vẫn tự xác minh token dành cho mình. Cách này có thể giảm phụ thuộc vào việc truyền principal qua header, nhưng đòi hỏi cấu hình trust, audience và xử lý vòng đời nhất quán.

Không mặc định token hợp lệ tại gateway cũng hợp lệ cho mọi service. Credential phải phù hợp với bên nhận và loại sử dụng đã thiết kế. Mỗi service còn phải kiểm tra quyền tài nguyên, tenant và điều kiện nghiệp vụ sau khi có danh tính hợp lệ.

### 7.3. Ranh giới mạng không thay thế hợp đồng

Network policy có thể giúp hạn chế đường đi vòng, nhưng cấu hình mạng sai hoặc một service nội bộ bị chiếm quyền vẫn là tình huống cần xét. Nên xác định cả ai được kết nối lẫn ai được phép khẳng định danh tính, thay vì dùng một trong hai làm bằng chứng cho toàn bộ chuỗi.

Nếu hệ thống dùng proxy để cung cấp thông tin client certificate hoặc địa chỉ nguồn, các header chuyển tiếp cũng phải có quy tắc trust. Địa chỉ IP được chuyển trong header không tự là danh tính người dùng hoặc bằng chứng xác thực mạnh.

## 8. Ranh giới service-to-service và quan hệ đại diện

### 8.1. Danh tính workload khác với danh tính người dùng

Một service có thể chứng minh nó là `report-service` bằng credential workload. Điều đó cho biết caller là workload nào theo nguồn tin cậy, không tự cho biết người dùng nào yêu cầu báo cáo hoặc workload có được đại diện người đó hay không.

Nếu hành động chạy trong ngữ cảnh người dùng, thiết kế cần biểu diễn cả subject và actor, cùng phạm vi delegation nếu có. Không cho caller gửi một `userId` tùy ý trong body rồi coi đó là chủ thể đã xác thực.

```text
Người dùng → service A → service B

Tại B cần phân biệt:
  actor: workload A
  subject: người dùng được đại diện, nếu có bằng chứng hợp lệ
  quyền: thao tác B được phép thực hiện trong quan hệ đó
```

Nếu đây là job nền của hệ thống, có thể không có người dùng cuối. Khi đó cần mô hình quyền workload phù hợp, thay vì gán tùy tiện một tài khoản quản trị cá nhân làm subject cho mọi tác vụ.

### 8.2. Không chuyển trust vượt phạm vi

Service A được phép đọc hồ sơ không tự được quyền tạo một assertion rằng người dùng là quản trị viên để service B chấp nhận. Khả năng phát hành hoặc đại diện danh tính phải được cấp rõ và giới hạn theo bên nhận, hành động và ngữ cảnh.

Cơ chế token dành cho downstream hoặc credential workload cần tuân theo hợp đồng được hỗ trợ. Không chuyển một token mang audience của A sang B chỉ vì B cũng hiểu JWT, và không cấp một secret chung toàn năng cho tất cả service để đơn giản hóa xác thực.

### 8.3. Xác thực workload cũng có vòng đời

Khóa, chứng thư và token của workload có nguồn cấp, thời hạn và cơ chế thu hồi/luân chuyển. Chấp nhận mọi chứng thư ký bởi một CA mà không kiểm tra danh tính và chính sách phù hợp có thể mở rộng trust ngoài phạm vi dự kiến.

Khi credential hết hạn hoặc nguồn xác minh lỗi, không chuyển sang một danh tính mặc định nhiều quyền hơn. Hành vi lỗi phải được thiết kế rõ như với người dùng.

## 9. Ranh giới bất đồng bộ và kết nối tồn tại lâu

### 9.1. Message và job nền

Broker xác thực producer không tự chứng minh mọi trường `subject`, `role` hoặc `tenant` trong message là đúng. Consumer cần biết producer được phép khẳng định ngữ cảnh nào và cách bảo vệ thông điệp, phạm vi người nhận cùng vòng đời xử lý.

Với job được đưa vào hàng đợi, có thể có khoảng cách dài giữa lúc yêu cầu được tạo và lúc thực thi. Cần xác định quyền được kiểm tra lúc nào, có cần kiểm tra lại trước tác động không, và điều gì xảy ra nếu người dùng đã bị vô hiệu hóa hoặc mất quyền trong thời gian chờ.

Không nhét refresh token hoặc credential cá nhân vào message để consumer có thể hoạt động lâu dài. Có thể truyền tham chiếu công việc và ngữ cảnh tối thiểu được bảo vệ, rồi dùng danh tính workload cùng cơ chế ủy quyền phù hợp tại lúc xử lý.

### 9.2. WebSocket và stream

Xác thực lúc mở kết nối không tự bảo đảm một kết nối kéo dài vô hạn còn đáp ứng điều kiện truy cập. Thiết kế cần xét thời hạn credential, trạng thái session, thu hồi và quyền cho từng loại thông điệp hoặc tài nguyên được đăng ký theo dõi.

Nếu cho phép cập nhật credential trên kết nối, việc cập nhật cũng là một ranh giới xác thực cần được kiểm tra. Không cho client thay subject bằng một thông điệp tùy ý sau khi kết nối đã được chấp nhận.

## 10. Những đường có thể làm thay đổi danh tính

### 10.1. Khôi phục và đăng ký phương thức xác thực

Endpoint đặt lại mật khẩu, thêm passkey, thay MFA hoặc đổi thông tin khôi phục có thể quyết định ai kiểm soát tài khoản về sau. Chúng cần mức xác minh và chống lạm dụng phù hợp, không được xem là các chức năng hồ sơ ít nhạy cảm.

Một luồng khôi phục yếu có thể vượt qua độ mạnh của xác thực chính. Cần giới hạn hiệu lực bằng chứng khôi phục, ràng buộc đúng mục tiêu và ngăn tái sử dụng theo thiết kế. Không ghi vật liệu khôi phục hoặc token xác nhận vào log.

### 10.2. Liên kết tài khoản và federation mới

Thêm một IdP hoặc liên kết tài khoản làm thay đổi nguồn có thể được dùng để đăng nhập. Việc này cần bằng chứng quyền kiểm soát và quy tắc liên kết phù hợp với rủi ro, thay vì chỉ trùng email là tự ghép.

Đổi tenant, chuyển tài khoản hoặc nâng quyền không được thực hiện bằng cách sửa một field trong security context do client điều khiển. Nếu người dùng lựa chọn tenant, server phải xác minh lựa chọn đó phù hợp với membership/quyền; lựa chọn là đầu vào, không phải bằng chứng.

### 10.3. Quản trị trust

Thay issuer được tin cậy, client registration, CA hoặc khóa xác minh là thay đổi authentication boundary. Quyền thực hiện thay đổi phải được bảo vệ, kiểm soát và audit vì có thể làm một nguồn mới được chấp nhận cho nhiều tài khoản.

Luân chuyển khóa cần xử lý vòng đời tin cậy, cache và vật liệu bị thu hồi. Không tự tải hoặc tin khóa từ một địa chỉ tùy ý trong credential chưa xác minh để làm cho việc xác minh “thành công”.

## 11. Lỗi, quan sát và bảo vệ dữ liệu

### 11.1. Không có bằng chứng hợp lệ thì không tạo danh tính có quyền

Thiếu credential, credential không hợp lệ, không đủ độ mới và lỗi phụ thuộc là các tình huống khác nhau. Hệ thống cần phân biệt để xử lý đúng, nhưng không được coi lỗi xác minh là thành công hoặc gán một principal mặc định nhiều quyền.

Với HTTP API, phản hồi thường phân biệt chưa xác thực/credential không được chấp nhận với đã xác thực nhưng không đủ quyền. Tuy nhiên mã trả cụ thể phụ thuộc giao thức và chính sách che giấu tài nguyên; lỗi hạ tầng cũng không nên bị ghi nội bộ như “người dùng nhập sai mật khẩu”. Quan trọng là giữ được ngữ nghĩa chính xác trong dữ liệu vận hành.

Thông báo cho client nên đủ để xử lý an toàn, không tiết lộ secret, chi tiết trust nhạy cảm hoặc việc tồn tại của tài khoản ngoài phạm vi cần thiết. Nhóm hỗ trợ có thể dùng mã tham chiếu để tra cứu sự kiện đã được phân quyền.

### 11.2. Ghi rõ ranh giới nào đưa ra kết quả

Một sự kiện minh họa:

```json
{
  "event_type": "authentication_boundary_result",
  "service": "course-api",
  "boundary": "api_bearer_validation",
  "credential_type": "access_token",
  "trust_profile": "corporate-production",
  "result": "rejected",
  "reason_class": "audience_mismatch",
  "request_ref": "request-example-71",
  "timestamp": "2026-01-15T08:30:00Z"
}
```

Sự kiện không cần raw token, authorization code, cookie, mật khẩu hoặc MFA secret. Nếu có thông tin đọc từ credential chưa được chấp nhận để chẩn đoán, cần đánh dấu rõ đó là dữ liệu chưa xác minh, lọc và giới hạn trước khi ghi; không dùng nó làm định danh đáng tin trong audit.

Metric nên dùng nhãn hữu hạn như dịch vụ, loại ranh giới và kết quả. User ID, email, request ID hoặc token không phù hợp làm nhãn tổng hợp. Cần nhìn cả số lần thành công, từ chối và lỗi phụ thuộc để phát hiện sự cố hoặc đường bypass.

## 12. Tình huống minh họa: header danh tính vượt ranh giới

Một cổng học có gateway xác minh token rồi gửi `X-Authenticated-User` đến course service. Ban đầu, service chỉ đọc header để tạo principal. Đường chính hoạt động, nhưng một endpoint nội bộ vẫn có thể được gọi trực tiếp từ một workload không được phép khẳng định danh tính người dùng.

Sai sót nằm ở ranh giới giữa gateway và service: service chưa xác minh nguồn assertion và đường đi vòng. Việc gateway đã xác thực người dùng trên một số request không bảo vệ request không đi qua cơ chế đó.

Thiết kế được làm rõ: service chỉ chấp nhận assertion theo hợp đồng từ nguồn được phép qua đường được bảo vệ, hoặc tự xác minh credential dành cho nó. Gateway loại bỏ dữ liệu danh tính giả mạo từ phía ngoài và không cho một header do client gửi trở thành assertion nội bộ. Các đường nội bộ và job cũng có cơ chế xác thực tương ứng.

Sau khi tạo được principal đáng tin, service vẫn kiểm tra tenant và quyền trên khóa học. Một caller hợp lệ không được thay subject bằng body `userId`, cũng không được dùng role của ứng dụng khác để vượt quyền.

Các kiểm tra cần chứng minh cả hai phía: request hợp lệ được xử lý; header giả mạo, credential sai audience, caller không được phép và tài nguyên thuộc tenant khác đều bị xử lý đúng. Chỉ kiểm tra “đăng nhập thành công” không phát hiện được lỗ hổng ranh giới này.

## 13. Những câu hỏi cần trả lời khi thiết kế

| Câu hỏi | Ý nghĩa |
| --- | --- |
| Đầu vào nào còn do bên ngoài điều khiển? | Ngăn dữ liệu tự khai bị nâng thành danh tính đã xác thực |
| Thành phần nào được phép xác minh hoặc khẳng định danh tính? | Xác định cơ quan có thẩm quyền và phạm vi trust |
| Credential có dành cho bên nhận này không? | Tránh dùng sai token, môi trường hoặc audience |
| Subject, actor và tenant được xác định từ đâu? | Ngăn trộn danh tính, đại diện tùy ý và truy cập chéo tenant |
| Có đường truy cập nào bỏ qua ranh giới không? | Bao phủ endpoint nội bộ, batch, message và đường dữ liệu khác |
| Khi nào cần xác thực lại hoặc step-up? | Đáp ứng độ mới và mức bảo đảm cho thao tác nhạy cảm |
| Phiên/credential hết hạn hoặc bị thu hồi được xử lý thế nào? | Giữ ý nghĩa xác thực xuyên suốt vòng đời |
| Có gì xảy ra khi nguồn xác minh không sẵn sàng? | Tránh chuyển lỗi phụ thuộc thành truy cập được phép |
| Dữ liệu nào được đưa vào context, log và downstream? | Giảm rò rỉ credential và thuộc tính danh tính |

Authentication boundary rõ ràng giúp hệ thống biết chính xác khi nào một khẳng định danh tính được chấp nhận và phạm vi tin cậy của nó. Từ đó, phiên, delegation và kiểm soát quyền có thể dựa trên ngữ cảnh đã xác minh thay vì những giả định về mạng, header hoặc việc đăng nhập ở một nơi khác.
