# Token theft trong hệ thống quản lý truy cập đặc quyền

## 1. Mục tiêu và phạm vi

Trong hệ thống quản lý truy cập đặc quyền, **token theft** là việc một bên không được phép chiếm được token hoặc vật liệu xác thực có thể dùng để đại diện cho người dùng, ứng dụng hay phiên làm việc. Rủi ro xuất hiện khi bên đó có thể đem token đến một thành phần chấp nhận nó và thực hiện hành động trong phạm vi quyền được cấp.

Kẻ sử dụng token bị đánh cắp có thể không cần biết mật khẩu và có thể không phải thực hiện lại bước MFA đã diễn ra khi token được cấp. Vì vậy, một lần đăng nhập hợp lệ không bảo đảm mọi yêu cầu sử dụng token sau đó đều do chủ thể hợp lệ thực hiện.

Trong PAM, tác động có thể là truy cập vault, mở phiên quản trị qua gateway, gọi API quản trị, đọc secret của tài khoản dịch vụ hoặc sử dụng quyền JIT trong thời gian còn hiệu lực. Không phải token nào cũng có tất cả những quyền này; mức độ ảnh hưởng phụ thuộc nơi chấp nhận token, quyền thực tế và các kiểm soát bổ sung.

Sau bài học, người học cần có khả năng:

- Phân biệt access token, refresh token, ID token, session cookie và token riêng của một hệ thống PAM.
- Xác định khi nào việc sao chép token đủ để sử dụng trái phép và khi nào còn cần bằng chứng sở hữu khóa hoặc điều kiện khác.
- Thiết kế tín hiệu phát hiện dựa trên chuỗi cấp token, kích hoạt quyền, mở phiên và truy cập tài nguyên.
- Xử lý sự cố mà không nhầm việc đổi mật khẩu, kết thúc JIT hay thu hồi refresh token với việc vô hiệu hóa mọi access token.
- Thu thập bằng chứng phục vụ kiểm toán mà không làm phát tán thêm credential.

Các trường dữ liệu và thuật toán trong bài là mô hình minh họa cho thiết kế phòng vệ. Cần ánh xạ chúng sang khả năng thực tế của nhà cung cấp danh tính, vault, gateway và tài nguyên đích trước khi triển khai.

## 2. Token nào bị đánh cắp?

### 2.1. Phân biệt các đối tượng có vòng đời khác nhau

| Đối tượng | Vai trò thông thường | Rủi ro khi bị chiếm được | Điểm cần xác minh |
|---|---|---|---|
| Access token | Cho phép truy cập một API hoặc tài nguyên trong phạm vi nhất định | Gọi tài nguyên chấp nhận token trong thời gian token còn được chấp nhận | Audience, quyền, thời hạn, cơ chế ràng buộc người gửi và khả năng thu hồi |
| Refresh token | Xin access token mới theo quy tắc của authorization server | Duy trì khả năng xin token mới, đôi khi vượt xa tuổi thọ của một access token | Client, grant, token family, rotation, reuse detection và chính sách thu hồi |
| ID token | Cung cấp thông tin về lần xác thực cho client | Có thể ảnh hưởng luồng đăng nhập nếu ứng dụng kiểm tra sai hoặc quản lý phiên kém | Không dùng ID token thay cho access token để cấp quyền gọi API |
| Session cookie | Tham chiếu hoặc mang trạng thái phiên của ứng dụng web | Chiếm phiên nếu ứng dụng chấp nhận cookie và không có kiểm soát ngăn chặn khác | Phiên phía máy chủ, thời hạn, cờ cookie, reauthentication và session revocation |
| Token của PAM gateway hoặc vault | Cho phép các thao tác riêng như mở phiên, nhận lease hoặc gọi API vault | Vượt qua một phần quy trình cấp quyền nếu token có thể tái sử dụng | Chính sách vault/gateway, tài nguyên, TTL, số lần dùng và ràng buộc phiên |
| Credential ngắn hạn của workload | Đại diện workload để truy cập dịch vụ hoặc hạ tầng | Sử dụng quyền của workload từ vị trí khác nếu kiểm soát cho phép | Workload identity, môi trường chạy, audience, quyền và điều kiện mạng |

Một session cookie có thể là bearer credential nhưng không nhất thiết là OAuth token. Một API key cũng có thể có tính chất bearer nhưng không có cùng vòng đời hoặc giao thức với OAuth access token. Phân loại đúng giúp chọn đúng nơi vô hiệu hóa và đúng loại log để điều tra.

JWT chỉ là một định dạng có thể được dùng cho token. Access token có thể là JWT hoặc chuỗi opaque; không thể kết luận token có thể thu hồi hay không chỉ từ định dạng của nó. JWT có thể được kết hợp với kiểm tra trạng thái phía máy chủ, còn opaque token có thể chịu ảnh hưởng của cache tại nơi xác thực.

### 2.2. Bearer token và token có ràng buộc người gửi

Với **bearer token**, bên giữ token có thể trình token như credential. Nếu không có kiểm soát bổ sung ngăn cản, bản sao có thể đủ để gọi tài nguyên. Chữ ký hợp lệ của JWT chứng minh token do một bên tin cậy phát hành và không bị sửa đổi; chữ ký đó không chứng minh người đang gửi yêu cầu là người được cấp token ban đầu.

Với **sender-constrained token**, nơi nhận yêu cầu còn kiểm tra bằng chứng gắn với một khóa hoặc credential của người gửi, chẳng hạn thiết kế dùng mTLS hoặc DPoP. Việc đánh cắp chuỗi token đơn thuần có thể không đủ. Tuy nhiên, lợi ích này phụ thuộc kiểm tra đúng ở các thành phần liên quan. Nếu khóa tương ứng cũng bị chiếm hoặc mã độc có thể sử dụng khóa trên thiết bị hợp lệ, rủi ro vẫn tồn tại.

Thiết bị được quản lý, mạng cho phép và vị trí địa lý là các điều kiện truy cập hữu ích. Chúng không mặc nhiên biến một bearer token thành token được ràng buộc bằng mật mã với người gửi.

### 2.3. Định danh không đồng nghĩa với quyền hiện tại

Một token có thể mô tả chủ thể và quyền tại thời điểm phát hành, trong khi quyền PAM còn phụ thuộc trạng thái hiện tại:

- Yêu cầu JIT đã được duyệt và còn trong cửa sổ sử dụng hay chưa.
- Người dùng có được phép truy cập đúng hệ thống đích và đúng môi trường hay không.
- Phiên gateway có còn hoạt động và còn liên kết với người dùng, thiết bị, phê duyệt ban đầu hay không.
- Quy tắc JEA có cho phép thao tác cụ thể hay chỉ cho phép một tập lệnh hoặc tác vụ hẹp.
- Vault lease, credential thuê hoặc quyền truy cập secret có còn hiệu lực hay đã bị thu hồi.

Nếu tài nguyên chỉ tin vào quyền được nhúng trong token mà không có cơ chế cập nhật phù hợp, thay đổi JIT hoặc nhóm quyền có thể chưa tác động ngay đến token đã phát hành. Ngược lại, một tài nguyên có kiểm tra trạng thái quyền hoặc phiên ở mỗi yêu cầu có thể từ chối sớm hơn. Phải kiểm chứng từng đường truy cập, không suy diễn từ tên tính năng của sản phẩm.

## 3. Vì sao token theft nguy hiểm đối với PAM?

### 3.1. MFA bảo vệ một thời điểm, token được sử dụng ở nhiều thời điểm

MFA có thể bảo vệ quá trình đăng nhập hoặc một hành động nhạy cảm. Sau khi hoàn tất, hệ thống có thể cấp token hoặc tạo phiên để tránh yêu cầu người dùng xác thực lại ở mọi thao tác. Nếu credential sau xác thực bị lộ, kẻ khác có thể sử dụng lại trạng thái đã được cấp.

Điều này không làm MFA trở nên vô ích. Nó cho thấy cần bảo vệ cả trước, trong và sau lần xác thực: thiết bị quản trị, trình duyệt, client, đường truyền, lưu trữ token, vòng đời phiên và hành vi sử dụng quyền.

Yêu cầu xác thực lại cũng chỉ có tác dụng nếu hành động thực sự bị chặn cho đến khi hoàn tất và cơ chế xác nhận đủ gắn với hành động hoặc ngữ cảnh cần bảo vệ. Một bước nhắc lại không được tài nguyên đích thực thi không thể bảo đảm bảo vệ thao tác đó.

### 3.2. Token có thể nối nhiều tầng quyền

Xét một luồng quản trị hợp lệ:

```text
Người quản trị trên thiết bị được quản lý
  → xác thực tại nhà cung cấp danh tính
  → kích hoạt quyền JIT theo yêu cầu đã duyệt
  → nhận quyền mở phiên tại PAM gateway
  → gateway sử dụng credential được vault quản lý
  → quản trị tài nguyên trong giới hạn JEA và ghi lại phiên
```

Mỗi mũi tên có thể tạo một loại phiên hoặc credential mới. Thu hồi token đăng nhập ở đầu luồng chưa chắc tự kết thúc phiên SSH, RDP hoặc phiên ứng dụng đã được thiết lập ở cuối luồng. Tương tự, kết thúc phiên gateway chưa chắc vô hiệu hóa một secret đã bị đọc hoặc sao chép.

Do đó, điều tra phải xác định **token bị mất nằm ở tầng nào** và từ tầng đó có thể tạo thêm đối tượng truy cập nào. Không nên dùng một danh sách thu hồi chung mà bỏ qua các phiên hoặc credential phát sinh phía sau.

### 3.3. Least privilege vẫn làm giảm tác động

Token bị chiếm không tự sinh ra quyền không tồn tại. Tuy nhiên, quyền rộng, audience dùng chung, TTL dài và đường truy cập bỏ qua PAM làm tăng tác động. Các biện pháp cần phối hợp gồm:

- Tách danh tính quản trị khỏi danh tính dùng email, duyệt web và công việc thông thường.
- Chỉ cấp audience, scope hoặc role cần thiết cho công việc cụ thể.
- Dùng JIT cho thời gian cần quyền và JEA cho tập thao tác được phép.
- Duy trì gateway làm điểm kiểm soát khi mô hình kiến trúc yêu cầu đi qua PAM.
- Tách danh tính workload theo ứng dụng, môi trường và trách nhiệm thay vì dùng chung một tài khoản dịch vụ đặc quyền.

## 4. Các điểm có thể làm lộ token

Mục đích của phần này là kiểm kê bề mặt rủi ro và kiểm soát, không phải hướng dẫn thu thập credential.

| Điểm trong vòng đời | Tình huống rò rỉ cần xem xét | Kiểm soát và bằng chứng tương ứng |
|---|---|---|
| Thiết bị quản trị | Mã độc, công cụ hỗ trợ hoặc tiến trình có quyền cao đọc được trạng thái xác thực | Thiết bị quản trị được bảo vệ, giới hạn phần mềm, telemetry endpoint, bảo vệ khóa |
| Trình duyệt và ứng dụng web | XSS, extension có quyền rộng, xử lý phiên không an toàn | Phòng chống XSS, quản lý extension, cờ cookie phù hợp, kiểm soát phiên phía máy chủ |
| Client và automation | Token nằm trong file cấu hình, biến môi trường, output hoặc thư mục làm việc | Workload identity, secret injection có giới hạn, quyền file, che giá trị nhạy cảm |
| Logging và tracing | Header Authorization, cookie hoặc phản hồi cấp token đi vào log | Redaction tại nguồn, allowlist trường được ghi, kiểm soát collector và retention |
| Hỗ trợ và vận hành | Người dùng gửi token trong ticket, chat, ảnh hoặc bản ghi màn hình | Hướng dẫn hỗ trợ, kênh bảo mật, lọc credential và quy trình xử lý rò rỉ |
| Proxy và tích hợp | Thành phần trung gian chuyển tiếp hoặc ghi token ngoài phạm vi cần thiết | Giới hạn hop được nhận credential, TLS, cấu hình proxy và kiểm kê tích hợp |
| Artifact và backup | Token còn trong bản sao cấu hình, artifact build hoặc gói chẩn đoán | Scan secret, giới hạn truy cập artifact, thời hạn lưu và vô hiệu hóa credential lộ |

`HttpOnly` giúp ngăn JavaScript truy cập trực tiếp giá trị cookie qua API thông thường của trình duyệt, nhưng không giải quyết mọi hành vi sử dụng phiên trái phép. `Secure` giới hạn việc gửi cookie qua kết nối bảo mật theo quy tắc trình duyệt; `SameSite` hỗ trợ giảm một số rủi ro gửi yêu cầu chéo site. Các cờ này cần được cấu hình đúng và không thay thế việc phòng chống XSS, kiểm soát endpoint hay thu hồi phiên.

Không có một vị trí lưu token phù hợp cho mọi loại client. Ứng dụng web phía máy chủ, SPA, ứng dụng desktop và workload có ràng buộc khác nhau. Quyết định lưu trữ phải dựa trên mô hình đe dọa và thư viện xác thực được hỗ trợ, tránh tự xây dựng cơ chế mã hóa mà khóa giải mã lại nằm cạnh token và coi đó là cách giải quyết đầy đủ.

## 5. Xây dựng dữ liệu để phát hiện

### 5.1. Cần quan sát cả cấp phát và sử dụng

Chỉ đọc log đăng nhập thường không đủ. Một access token đã có sẵn có thể được sử dụng tại API mà không tạo một lần đăng nhập tương tác mới. Thiết kế thu thập cần liên kết được các nguồn sau, trong giới hạn khả năng của hệ thống:

1. Sự kiện xác thực, cấp token, refresh token và thay đổi trạng thái grant từ nhà cung cấp danh tính.
2. Sự kiện yêu cầu, duyệt, kích hoạt và kết thúc quyền JIT.
3. Sự kiện mở, sử dụng, ngắt và kết thúc phiên PAM gateway.
4. Audit truy cập vault, cấp hoặc thu hồi lease, truy xuất secret và rotation.
5. Log quyết định cấp quyền và thao tác thực tế tại tài nguyên đích.
6. Telemetry thiết bị, workload, mạng và các thay đổi cấu hình liên quan.

Không phải nhà cung cấp nào cũng phát sinh đủ các sự kiện này hoặc dùng cùng định danh. Thiếu dữ liệu phải được ghi nhận là khoảng trống quan sát; không nên diễn giải thành không có hành vi bất thường.

### 5.2. Mô hình sự kiện tối thiểu

Một mô hình chuẩn hóa minh họa có thể gồm:

```json
{
  "event_time": "2026-01-15T02:12:00Z",
  "ingest_time": "2026-01-15T02:12:03Z",
  "event_type": "privileged_api_request",
  "issuer_id": "idp-lab",
  "tenant_id": "tenant-lab-a",
  "subject_id": "admin-lab-17",
  "client_id": "pam-portal-lab",
  "audience": "vault-api-lab",
  "token_ref": "protected-reference-42",
  "token_issued_at": "2026-01-15T02:00:00Z",
  "token_expires_at": "2026-01-15T02:20:00Z",
  "grant_ref": "grant-lab-8",
  "jit_request_id": "jit-lab-231",
  "pam_session_id": "pam-lab-901",
  "device_id": "device-lab-7",
  "device_evidence_source": "trusted-gateway",
  "source_network_ref": "managed-admin-egress",
  "target_id": "vault-prod-lab",
  "action": "read_secret_metadata",
  "decision": "allow",
  "correlation_id": "trace-lab-502"
}
```

Toàn bộ định danh trong ví dụ là giả lập; không có token thật. Các trường `token_ref`, `grant_ref`, `jit_request_id` và `pam_session_id` không phải claim bắt buộc của mọi giao thức. Chúng có thể là tham chiếu audit nội bộ được bổ sung tại điểm thực thi đáng tin cậy.

Những điểm thiết kế cần làm rõ:

- **Định danh chủ thể:** kết hợp issuer, tenant và subject; tránh nối theo tên hiển thị hoặc email có thể thay đổi.
- **Định danh token:** nếu có `jti`, không mặc định nó duy nhất toàn hệ thống. Dùng cùng namespace của issuer và các ngữ cảnh cần thiết; xác minh cam kết của bên phát hành.
- **Nguồn thiết bị:** một `device_id` do client tự khai khác với bằng chứng thiết bị được thành phần tin cậy xác minh. Không dùng chúng như nhau khi tính độ tin cậy.
- **Thời gian:** lưu event time và ingest time, đồng bộ clock, xử lý log đến muộn và sai lệch thời gian có giới hạn.
- **Kết quả:** ghi cả quyết định allow/deny và thao tác đã hoàn tất nếu có. Một yêu cầu bị từ chối không chứng minh tài nguyên đã bị truy cập.
- **Giới hạn dữ liệu:** token claim chỉ dùng để suy luận sau khi được xác minh bằng cơ chế phù hợp tại nơi có trách nhiệm; decode JWT không đồng nghĩa với xác thực JWT.

### 5.3. Không đưa credential vào hệ thống giám sát

Không ghi toàn bộ access token, refresh token, cookie, header Authorization, private key hoặc secret đã đọc vào log thông thường. Việc này có thể biến nền tảng giám sát thành một kho credential mới.

Ưu tiên định danh audit do nhà cung cấp hỗ trợ hoặc một tham chiếu không thể dùng để xác thực. Nếu cần tạo fingerprint để tương quan token, phải có thiết kế riêng về thuật toán, khóa, quyền truy cập và thời hạn lưu. HMAC với khóa được bảo vệ có thể là một lựa chọn phù hợp; việc tạo fingerprint chỉ diễn ra ở thành phần đã được phép xử lý token. Nó không phải lý do để tập trung token thô vào collector.

Fingerprint không phải token thật nhưng vẫn có thể là dữ liệu nhạy cảm vì cho phép nối hành vi giữa các nguồn. Cần áp dụng kiểm soát truy cập và retention cho cả dữ liệu tương quan. Nếu bắt buộc giữ mẫu credential trong điều tra, dùng kho bằng chứng hạn chế riêng theo quy trình được phê duyệt, không dán vào ticket hay chat vận hành.

## 6. Các tín hiệu phát hiện quan trọng

### 6.1. Cùng token xuất hiện trong những ngữ cảnh khó tương thích

Một tín hiệu đáng xem xét là cùng tham chiếu token được chấp nhận ở hai ngữ cảnh không phù hợp trong cùng cửa sổ thời gian: thiết bị quản trị quen thuộc và một môi trường workload không liên quan, hoặc hai nguồn có bằng chứng khác nhau cho cùng phiên người dùng.

Đây không phải kết luận tự động rằng token đã bị đánh cắp. Proxy doanh nghiệp, NAT, VPN, client phân tán hoặc tiến trình hợp lệ cùng chia sẻ token có thể tạo nhiều địa chỉ nguồn. Ngược lại, kẻ sử dụng trái phép có thể đi qua cùng proxy hoặc endpoint hợp lệ nên không tạo thay đổi IP rõ ràng.

Tín hiệu mạnh hơn xuất hiện khi có nhiều bằng chứng độc lập: token dành cho client quản trị tương tác được dùng từ workload không được phê duyệt, không có JIT tương ứng, kèm thao tác đọc secret nhạy cảm khác với công việc đã duyệt.

### 6.2. Quyền được dùng mà không có phê duyệt hoặc phiên phù hợp

Đối chiếu thao tác với các điều kiện bắt buộc của chính sách:

- Có yêu cầu JIT cho đúng chủ thể, tài nguyên và khoảng thời gian hay không.
- Người dùng có đi qua gateway nếu tài nguyên bắt buộc truy cập qua gateway hay không.
- `pam_session_id` có liên kết hợp lệ với chủ thể và công việc đang xét hay không.
- Quyền trong token có phù hợp với quyền hiệu lực theo mô hình cấp quyền hiện tại hay không.
- Hành động có vượt tập JEA được duyệt hoặc mở rộng sang tài nguyên không thuộc yêu cầu hay không.

Phát hiện lệch chính sách là bằng chứng cần điều tra ngay cả khi chưa biết token có bị đánh cắp. Nguyên nhân có thể là sai cấu hình, đường truy cập trực tiếp ngoài kiểm soát PAM, sai tương quan log hoặc lạm dụng bởi chính tài khoản hợp lệ.

### 6.3. Hành vi bất thường sau khi nhận token

Các hành vi cần kết hợp với ngữ cảnh gồm: đọc secret hàng loạt, tạo thêm credential, thay chính sách vault, thay trust của ứng dụng, mở nhiều phiên quản trị bất thường hoặc truy cập môi trường không liên quan đến yêu cầu công việc.

Đánh giá theo nhóm người dùng và loại workload. Một tác vụ rotation đã được duyệt có thể truy cập nhiều credential trong thời gian ngắn; một người dùng chỉ được phép chẩn đoán một máy chủ thì có baseline khác. Dùng một ngưỡng toàn hệ thống thường gây nhiều cảnh báo giả và có thể bỏ sót hành vi quan trọng ở tài nguyên ít được truy cập.

### 6.4. Refresh token reuse hoặc chuỗi cấp token bất thường

Trong một thiết kế refresh token rotation có phát hiện tái sử dụng, sự kiện một refresh token cũ bị sử dụng lại là tín hiệu có giá trị. Tuy nhiên, khả năng phát hiện, thời gian grace, cách xử lý request đồng thời và phạm vi thu hồi token family phụ thuộc triển khai.

Client hợp lệ có thể tạo request trùng do retry hoặc cạnh tranh giữa nhiều tiến trình. Không nên tự xây quy tắc kết luận sự cố chỉ dựa vào một lần reuse mà không hiểu hành vi của client và nhà cung cấp. Cũng không được coi thiếu sự kiện reuse là bằng chứng refresh token chưa bị chiếm.

### 6.5. Hoạt động tiếp tục sau thời điểm dự kiến thu hồi

Nếu audit ghi nhận yêu cầu được chấp nhận sau khi đã xác nhận cơ chế thu hồi phải có hiệu lực đối với đường truy cập đó, cần kiểm tra:

1. Thời điểm thu hồi thực tế và độ trễ phân phối trạng thái.
2. Log dùng event time hay ingest time.
3. Token được dùng là access token cũ, token mới hay một credential khác.
4. Cache, phiên downstream và đường truy cập có bỏ qua điểm kiểm tra hay không.
5. Phạm vi thu hồi có đúng user, grant, client, token family, lease hoặc phiên liên quan hay không.

Không mặc định mọi lần sử dụng sau lệnh revoke đều là dấu hiệu kẻ tấn công vừa nhận token mới. Chỉ có thể kết luận sau khi nối được chuỗi sự kiện và hiểu ngữ nghĩa thu hồi.

## 7. Quy tắc tương quan minh họa

Đoạn dưới là **pseudocode**, không phải truy vấn chạy trực tiếp trên một SIEM. Cửa sổ thời gian, tập hành động và ngưỡng phải được điều chỉnh theo kiến trúc, độ trễ log và đường truy cập đã phê duyệt.

```text
FOR each accepted privileged request R:
    identity = (R.issuer_id, R.tenant_id, R.subject_id)
    policy = policy_for(R.target_id, R.action, R.event_time)
    reasons = []

    IF policy.requires_jit:
        jit_state = lookup_jit_with_late_event_tolerance(identity, R)
        IF jit_state == CONFIRMED_NO_MATCH:
            reasons.add("missing_required_jit")
        ELSE IF jit_state == UNKNOWN:
            record_visibility_gap("jit_correlation_incomplete", R)

    IF policy.requires_gateway:
        session_state = lookup_trusted_pam_session(identity, R)
        IF session_state == CONFIRMED_NO_MATCH:
            reasons.add("missing_required_gateway_session")

    IF R.token_ref IS AVAILABLE:
        prior = accepted_requests_for_same_token_namespace(R)
        IF trusted_contexts_are_incompatible(prior, R):
            reasons.add("incompatible_token_use_contexts")

    IF action_exceeds_approved_work_scope(R):
        reasons.add("action_outside_approved_scope")

    IF reasons IS NOT EMPTY:
        emit_correlated_alert(
            identity = identity,
            target = R.target_id,
            reasons = reasons,
            evidence_refs = collect_non_secret_evidence_refs(R)
        )
```

Quy tắc cần phân biệt **không có phê duyệt** với **chưa nhận được log phê duyệt**. Trạng thái `UNKNOWN` không đồng nghĩa được phép truy cập; nó mô tả mức độ chắc chắn của phát hiện. Quyết định fail-open hay fail-closed ở điểm thực thi quyền là một quyết định kiến trúc riêng, phải phù hợp yêu cầu vận hành và mức nhạy cảm.

Với tài nguyên không phát lộ định danh token an toàn, vẫn có thể phát hiện theo chủ thể, client, phiên và hành vi. Khi đó không được gắn nhãn “cùng một token” chỉ vì hai sự kiện có cùng subject.

Các điều kiện trực tiếp vi phạm chính sách đặc quyền có thể tạo cảnh báo riêng mà không cần chờ đủ nhiều tín hiệu. Độ ưu tiên xử lý nên dựa trên độ nhạy của tài nguyên, hành động thực tế, độ tin cậy của bằng chứng và khả năng credential vẫn còn dùng được.

## 8. Tình huống minh họa: token của quản trị viên xuất hiện ngoài phiên được duyệt

### 8.1. Bối cảnh và timeline

Một quản trị viên được duyệt quyền JIT để kiểm tra một hệ thống trong cửa sổ 02:00–02:15 UTC. Chính sách yêu cầu thiết bị quản trị được quản lý và truy cập qua gateway. Access token của API vault được phát hành lúc 02:00, có thời hạn đến 02:20 theo cấu hình giả lập.

| Thời điểm UTC | Sự kiện | Ý nghĩa ban đầu |
|---|---|---|
| 02:00 | JIT được kích hoạt cho đúng tài nguyên | Có phê duyệt hợp lệ trong một cửa sổ hữu hạn |
| 02:01 | Gateway mở phiên từ thiết bị quản trị | Luồng dự kiến đang hoạt động |
| 02:06 | Cùng tham chiếu token xuất hiện từ một workload không thuộc luồng được duyệt | Có dấu hiệu sử dụng token ở ngữ cảnh không phù hợp |
| 02:07 | Workload yêu cầu đọc secret của tài nguyên ngoài phạm vi JIT | Tăng độ ưu tiên điều tra, cần kiểm tra allow/deny và kết quả thực tế |
| 02:08 | SOC xác nhận workload không có tác vụ hợp lệ tương ứng | Giảm khả năng đây là hoạt động được phê duyệt |
| 02:09 | Thực hiện containment theo các tầng bị ảnh hưởng | Cần theo dõi hiệu lực, không chỉ ghi nhận đã gửi lệnh |

Việc xuất hiện cùng `token_ref` chỉ có giá trị nếu tham chiếu này được tạo đáng tin cậy, không va chạm ngoài dự kiến và không do client tự khai. Nếu chưa đáp ứng các điều kiện đó, diễn đạt phát hiện là “cùng danh tính có hoạt động bất thường”, không khẳng định cùng token.

### 8.2. Điều tra theo giả thuyết

Cần xem xét ít nhất các khả năng: token bị sao chép, workload được cấu hình dùng chung credential sai quy định, luồng proxy bị ánh xạ sai hoặc có tích hợp hợp lệ chưa cập nhật vào chính sách. Đồng thời kiểm tra endpoint quản trị và các kênh log để tìm nguồn lộ mà không thu thập credential quá mức.

Các câu hỏi quyết định gồm:

- Yêu cầu 02:07 bị từ chối hay đã đọc được secret? Có bằng chứng truy cập tại chính vault không?
- Workload dùng token đã phát hành lúc 02:00 hay xin token mới từ một grant khác?
- Có phiên downstream hoặc credential thuê nào đã được tạo từ hoạt động đó không?
- Người quản trị có thực hiện hành động tương ứng không, và bằng chứng phiên có khớp không?
- Có dấu hiệu tạo credential, thay đổi role hoặc chỉnh chính sách để duy trì truy cập không?

Một phiên quản trị hợp lệ còn tồn tại không loại trừ token theft. Chủ thể hợp lệ và bên sử dụng trái phép có thể hoạt động đồng thời.

### 8.3. Cửa sổ JIT và thời hạn token

Trong ví dụ, JIT kết thúc lúc 02:15 còn token ghi thời hạn đến 02:20. Không thể từ hai mốc này kết luận tài nguyên chắc chắn cho phép dùng quyền thêm năm phút. Cũng không thể kết luận quyền tự hết ngay lúc 02:15.

Kết quả phụ thuộc tài nguyên kiểm tra quyền hiện tại, trạng thái phiên, sự kiện thu hồi hoặc chỉ dùng quyền trong token. Thực hành cần kiểm chứng cả yêu cầu mới và phiên đã thiết lập để xác định cửa sổ rủi ro thực tế. Khi thiết kế JIT, phải gắn việc kết thúc quyền với cơ chế thực thi ở các tầng liên quan thay vì chỉ giảm thời gian trên giao diện phê duyệt.

## 9. Ứng phó sự cố theo từng tầng truy cập

### 9.1. Xác định đối tượng bị lộ và giảm tác động

Mở hồ sơ sự cố và ghi nhận chủ thể, issuer, tenant, client, tài nguyên, loại credential, thời gian nghi lộ, quyền và phiên liên quan. Tránh đưa giá trị credential vào hồ sơ chung. Dùng tham chiếu bằng chứng để nối các hệ thống.

Tùy bằng chứng và tác động, containment có thể gồm khóa hoặc hạn chế danh tính bị ảnh hưởng, chặn client hoặc workload, ngắt thiết bị, chấm dứt phiên PAM và giới hạn truy cập tài nguyên. Với hệ thống phục vụ sản xuất, chọn phạm vi đủ để ngăn tiếp tục sử dụng trái phép, đồng thời phối hợp chủ dịch vụ để kiểm soát tác động vận hành. Không trì hoãn biện pháp khẩn cấp đã được quy trình cho phép chỉ để chờ mọi log đầy đủ.

### 9.2. Thu hồi đúng đối tượng

| Đối tượng | Hành động cần xem xét | Điều hành động đó không tự bảo đảm |
|---|---|---|
| Phiên đăng nhập hoặc session cookie | Vô hiệu hóa phiên phía máy chủ, yêu cầu xác thực lại theo chính sách | Mọi access token và phiên downstream đều bị chặn ngay |
| Refresh token hoặc grant | Thu hồi grant/token family theo khả năng nhà cung cấp | Access token đã cấp lập tức mất hiệu lực ở mọi tài nguyên |
| Access token | Áp dụng cơ chế revoke, denylist, introspection hoặc kiểm soát tại tài nguyên nếu được hỗ trợ | Mọi hệ thống dùng cùng ngữ nghĩa và độ trễ thu hồi |
| Quyền JIT | Kết thúc activation và cập nhật quyền hiệu lực | Phiên đang mở hoặc token chứa quyền cũ tự kết thúc |
| Phiên PAM gateway | Ngắt phiên và thu hồi vé/token mở phiên liên quan | Credential đã được lộ ra ngoài không còn dùng được |
| Vault lease hoặc credential thuê | Thu hồi lease và vô hiệu hóa credential tại đích theo cơ chế hỗ trợ | Mọi phiên đã xác thực bằng credential đó đều bị ngắt |
| Secret thực tế đã bị đọc | Rotation hoặc thay thế secret, cập nhật consumer và vô hiệu hóa bản cũ | Token đăng nhập hoặc cơ chế duy trì truy cập khác đã được xử lý |
| Khóa ràng buộc người gửi bị chiếm | Thu hồi credential/chứng thư hoặc thay khóa và liên kết liên quan | Chỉ thu hồi token đơn lẻ đã loại bỏ khả năng xin hoặc dùng token khác |

Không cần áp dụng mọi hàng cho mọi sự cố. Phạm vi phải theo đối tượng thực sự bị ảnh hưởng và đường truy cập có thể phát sinh. Nếu xác định được secret đã bị đọc trái phép thì việc chỉ thu hồi token dùng để đọc secret thường chưa xử lý đủ hậu quả.

Đổi mật khẩu có thể là một phần xử lý nếu thông tin xác thực hoặc tài khoản bị ảnh hưởng. Không được mặc định đổi mật khẩu sẽ thu hồi mọi cookie, refresh token, access token, API key và phiên quản trị; phải xác minh hành vi của từng hệ thống.

Không xoay toàn bộ khóa ký của issuer chỉ vì một bearer token đơn lẻ bị lộ. Token bị sao chép không đồng nghĩa khóa ký đã mất. Thay khóa ký có thể ảnh hưởng nhiều client và không phải cách thu hồi phù hợp cho mọi tài nguyên. Chỉ xem xét theo bằng chứng về khóa và quy trình quản lý khóa tương ứng.

### 9.3. Kiểm chứng hiệu lực containment

Sau mỗi biện pháp quan trọng, xác minh ở nơi thực thi quyền thay vì chỉ đọc trạng thái thành công của lệnh quản trị:

- Chủ thể, grant hoặc phiên bị ảnh hưởng có còn tạo được access token mới không?
- Tài nguyên có từ chối các credential thuộc phạm vi đã thu hồi theo cơ chế đã cam kết không?
- Phiên gateway và phiên đích có thực sự kết thúc không?
- Credential cũ đã rotation có còn được tài nguyên đích chấp nhận không?
- Có hoạt động từ credential, client hoặc danh tính khác được tạo trong sự cố không?

Ưu tiên kiểm tra bằng tài khoản và môi trường kiểm chứng được cho phép, hoặc telemetry đáng tin cậy. Không đưa token nghi bị đánh cắp vào công cụ bên ngoài để “thử còn sống không”. Nếu điều tra cần thao tác với mẫu credential thật, phải theo quyền truy cập và quy trình bằng chứng riêng.

### 9.4. Bảo toàn bằng chứng và phục hồi

Ghi lại thời gian, người thực hiện, đối tượng, thao tác containment, kết quả và nguồn xác nhận. Bảo toàn log từ issuer, PAM, vault, endpoint và tài nguyên đích với thông tin nguồn, kiểm tra toàn vẹn và lịch sử truy cập theo quy trình điều tra.

Trước khi khôi phục, xử lý nguyên nhân lộ: mã độc trên endpoint, log chứa token, client chia sẻ credential, ứng dụng có lỗi hoặc quyền tích hợp quá rộng. Khôi phục phiên từ môi trường đã được đánh giá phù hợp, cấp lại quyền tối thiểu và theo dõi giai đoạn sau phục hồi. Nếu dùng break-glass để duy trì vận hành, ghi nhận rõ người sử dụng, thời gian, mục đích và việc rotation hoặc thu hồi sau đó.

## 10. Phòng ngừa trong thiết kế PAM

### 10.1. Giảm khả năng lấy và tái sử dụng token

Sử dụng thiết bị quản trị được quản lý, giảm phần mềm và extension không cần thiết, tách công việc quản trị khỏi duyệt web thông thường và hạn chế quyền đọc dữ liệu của tiến trình khác. Khi có khả năng hỗ trợ xuyên suốt, cân nhắc token ràng buộc người gửi và khóa được bảo vệ phù hợp.

Tại ứng dụng và hạ tầng, dùng TLS với kiểm tra chứng thư đúng, tránh truyền credential qua URL, bỏ credential khỏi log và chỉ chuyển token đến thành phần thực sự cần. Kiểm kê cả proxy, collector, agent hỗ trợ và gói chẩn đoán vì chúng có thể giữ bản sao ngoài thiết kế ban đầu.

### 10.2. Thu hẹp thời gian và phạm vi sử dụng

Chọn tuổi thọ access token phù hợp độ nhạy và khả năng vận hành. TTL ngắn giúp giới hạn một phần thời gian sử dụng nhưng không ngăn được hành động ngay sau khi lộ, không xử lý refresh token bị chiếm và không thay thế kiểm soát quyền.

Áp dụng audience đúng tài nguyên, scope hoặc role hẹp, danh tính riêng theo workload và môi trường. Hạn chế offline access hoặc quyền cấp token dài hạn nếu công việc không cần. Với refresh token, dùng rotation và phát hiện reuse khi hệ thống hỗ trợ đúng mô hình client; xác minh hành vi thu hồi và request đồng thời.

JIT giảm thời gian có quyền, JEA giảm thao tác được phép, vault giảm việc người dùng phải biết secret và giám sát phiên tăng khả năng phát hiện. Hiệu quả tổng thể phụ thuộc tài nguyên có thực thi các giới hạn này và credential có bị đưa ra ngoài luồng được bảo vệ hay không.

### 10.3. Thiết kế khả năng thu hồi từ đầu

Với mỗi đường truy cập đặc quyền, cần trả lời rõ ai có thể thu hồi, thu hồi đối tượng nào, tác động đến phiên đang mở, độ trễ dự kiến và bằng chứng xác nhận. Đặc biệt kiểm tra tài nguyên tự xác minh token, hệ thống có cache, tài nguyên ở mạng gián đoạn và phiên giao thức tồn tại lâu.

Nếu một đường truy cập không hỗ trợ vô hiệu hóa access token ngay, phải mô tả giới hạn đó và có biện pháp bổ sung phù hợp như TTL ngắn, kiểm soát tại gateway hoặc tài nguyên, giới hạn quyền và khả năng ngắt phiên. Không ghi một cam kết “revoke tức thời toàn hệ thống” khi chưa có bằng chứng thực thi.

## 11. Bài thực hành phòng vệ bằng dữ liệu giả lập

### 11.1. Thiết lập và dữ liệu

Thực hiện trên bảng sự kiện giả lập hoặc môi trường lab được phép. Không cần thu thập, xuất hoặc dùng lại token thật. Dùng các tham chiếu không có khả năng xác thực:

```text
02:00  jit_activated        subject=admin-lab-17 target=server-lab-a
02:01  pam_session_opened   subject=admin-lab-17 session=S-A device=D-A
02:02  api_allow            token_ref=T-A target=server-lab-a context=D-A
02:06  api_allow            token_ref=T-A target=vault-lab-b context=W-B
02:07  secret_read_denied   token_ref=T-A target=vault-lab-b context=W-B
02:09  grant_revoked        subject=admin-lab-17 grant=G-A
02:10  pam_session_closed   subject=admin-lab-17 session=S-A
02:11  api_allow            token_ref=T-A target=server-lab-a context=W-B
```

Trong bộ dữ liệu, `W-B` là workload không thuộc luồng quản trị được duyệt. Sự kiện `api_allow` không tự đồng nghĩa đã đọc secret; cần dựa vào loại thao tác cụ thể. Sự kiện `secret_read_denied` thể hiện lần đọc đó bị từ chối, không chứng minh mọi lần đọc khác cũng thất bại.

### 11.2. Nhiệm vụ

1. Nối các sự kiện theo chủ thể, token reference, tài nguyên và phiên; nêu rõ trường hợp thiếu dữ liệu để kết luận.
2. Phân loại tín hiệu bất thường ở 02:06 và 02:07. Phân biệt lệch chính sách với bằng chứng token theft đã được xác nhận.
3. Giải thích ít nhất hai nguyên nhân có thể làm xuất hiện `api_allow` lúc 02:11 sau sự kiện thu hồi grant.
4. Đề xuất các đối tượng cần kiểm tra hoặc thu hồi, cùng nguồn bằng chứng để xác nhận hiệu lực.
5. Thiết kế biến thể hợp lệ có đổi IP do VPN nhưng vẫn dùng cùng thiết bị và đúng phiên, để kiểm tra cảnh báo giả.
6. Thiết kế biến thể không có `token_ref`; sửa kết luận của detector để không khẳng định cùng token.

### 11.3. Kết quả mong đợi

Bài làm tốt nhận ra cần điều tra việc dùng `T-A` ở ngữ cảnh `W-B`, nhưng không kết luận thành công truy xuất secret từ một sự kiện deny. Nó cũng không xem thu hồi grant là bằng chứng mọi access token bị chặn ngay: request 02:11 có thể do access token còn được chấp nhận, cache trạng thái, đường truy cập khác hoặc sai lệch thứ tự log. Phải có dữ liệu bổ sung để chọn nguyên nhân.

Kế hoạch containment cần bao quát grant, access token theo khả năng thực tế, phiên PAM và credential phát sinh nếu có. Bài thực hành chỉ đạt khi mô tả được bằng chứng tại điểm thực thi quyền và giữ credential thô ngoài log, không phải chỉ khi tạo được nhiều cảnh báo.

## 12. Lỗi thường gặp và nguyên tắc ghi nhớ

| Nhận định sai | Cách hiểu cần áp dụng |
|---|---|
| “Đã có MFA nên token bị sao chép không dùng được” | Kiểm tra loại token và các điều kiện ở lần sử dụng; MFA của lần cấp token không tự xác minh người gửi mọi request |
| “JWT có chữ ký nên không thể bị replay” | Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành, không tự ngăn sử dụng bản sao |
| “Decode được JWT là đủ để tin các claim” | Claim cần được xác minh theo trách nhiệm và cấu hình của nơi chấp nhận token |
| “IP thay đổi là token theft” | Dùng ngữ cảnh và bằng chứng độc lập; VPN, proxy và NAT có thể tạo thay đổi hợp lệ |
| “Không có đăng nhập mới nghĩa là không có truy cập trái phép” | Token hoặc phiên có sẵn có thể được dùng mà không tạo đăng nhập tương tác mới |
| “JIT hết hạn thì mọi phiên tự dừng” | Kiểm chứng quyền ở tài nguyên, phiên gateway và phiên downstream |
| “Revoke refresh token hoặc đổi mật khẩu đã xử lý mọi token” | Xác minh phạm vi thu hồi của từng loại credential và các phiên đã tạo |
| “Ghi token đầy đủ sẽ giúp điều tra chính xác hơn” | Dùng tham chiếu audit và dữ liệu tối thiểu; tránh tạo thêm điểm rò rỉ |
| “Token bị lộ nghĩa là phải thay khóa ký toàn hệ thống” | Phân biệt lộ một credential với mất khóa ký của issuer; xử lý theo bằng chứng |

Token theft cần được xem xét xuyên suốt từ danh tính, thiết bị và client đến PAM gateway, vault và tài nguyên đích. Phòng vệ hiệu quả kết hợp quyền tối thiểu, JIT/JEA, bảo vệ credential, giám sát hành vi và cơ chế thu hồi được kiểm chứng. Khi sự cố xảy ra, câu hỏi quyết định là bên giữ credential còn có thể thực hiện hành động nào, qua đường truy cập nào, và bằng chứng nào xác nhận khả năng đó đã bị chặn.
