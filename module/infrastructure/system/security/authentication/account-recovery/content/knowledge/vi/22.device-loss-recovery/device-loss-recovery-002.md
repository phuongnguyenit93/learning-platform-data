# Stolen device response — Ứng phó khi thiết bị bị trộm

Trong chương **Device Loss Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **stolen device response** là quy trình giảm quyền truy cập của người đang giữ thiết bị bị trộm, kiểm soát các bí mật có thể bị lộ và giúp chủ tài khoản thiết lập lại khả năng xác thực an toàn.

Một chiếc điện thoại hoặc laptop có thể đồng thời chứa session đang đăng nhập, passkey, ứng dụng TOTP, SIM nhận SMS, email khôi phục và kho mật khẩu. Vì vậy, “đăng xuất thiết bị” không đồng nghĩa đã thu hồi mọi quyền, còn “đổi mật khẩu” không bảo đảm session cũ hoặc passkey bị ảnh hưởng đã mất hiệu lực.

Bài học trình bày một thiết kế tham khảo cho nền tảng có nhiều thiết bị, nhiều phương tiện xác thực và các dịch vụ độc lập. Mục tiêu là xử lý đúng quyền thực tế ở phía server, không chỉ thay nhãn trạng thái trên màn hình quản lý thiết bị.

## 1. Ba kết quả cần đạt và thứ tự ưu tiên

Một quy trình đầy đủ có ba nhóm công việc:

| Nhóm | Câu hỏi cần trả lời | Kết quả cần đạt |
|---|---|---|
| Cô lập quyền truy cập | Thiết bị và bí mật liên quan còn làm được gì? | Các đường truy cập bị ảnh hưởng bị chặn hoặc giới hạn |
| Khắc phục bí mật và thay đổi trái phép | Kẻ giữ thiết bị có thể đăng nhập lại bằng cách nào? | Credential, kênh recovery và quyền mới được rà soát, xử lý |
| Khôi phục cho chủ tài khoản | Người hợp lệ sẽ xác thực từ đâu và bằng gì? | Đăng ký phương tiện thay thế và cấp session mới đúng chính sách |

Không bắt chủ tài khoản hoàn tất mọi thủ tục khôi phục rồi mới được báo mất thiết bị. Trong thời gian chờ đó, session hoặc authenticator trên thiết bị bị trộm có thể vẫn hoạt động.

Ngược lại, quyền báo sự cố không được tự biến thành quyền đổi email, xóa MFA hoặc đăng ký một passkey mới. Mỗi nhóm thao tác cần mức bằng chứng và phạm vi quyền riêng.

Thiết kế nên thể hiện các mốc tách biệt:

~~~text
Đã nhận báo cáo
  -> đã chặn quyền ở nguồn có thẩm quyền
  -> các hệ thống liên quan đã thực thi giới hạn
  -> đã xử lý bí mật và thay đổi đáng ngờ
  -> chủ tài khoản đã khôi phục phương tiện an toàn
~~~

Nếu chỉ hoàn thành mốc thứ hai, giao diện không nên tuyên bố “tài khoản đã được bảo vệ hoàn toàn”.

## 2. Thiết bị không phải một credential duy nhất

### 2.1. Lập bản đồ quyền có thể nằm trên thiết bị

| Thành phần | Rủi ro khi bị trộm | Hành động cần đánh giá |
|---|---|---|
| Cookie/session ứng dụng | Tiếp tục đọc dữ liệu và thao tác như người dùng | Thu hồi session và các ID thuộc cùng phiên logic |
| Refresh token | Tạo access token mới dù access token hiện tại hết hạn | Thu hồi token family hoặc grant tương ứng |
| Access token tự chứa | Dịch vụ có thể tiếp tục chấp nhận tới khi có cơ chế chặn | Introspection, epoch, denylist hoặc giới hạn tương đương |
| Passkey gắn thiết bị | Kẻ giữ máy có thể sử dụng nếu vượt được cơ chế kích hoạt | Vô hiệu credential phía dịch vụ khi thuộc phạm vi xâm phạm |
| Passkey đồng bộ | Một credential có thể có bản sao trên nhiều thiết bị | Đánh giá cả credential và tài khoản đồng bộ |
| TOTP | Seed có thể còn dùng trên máy hoặc đã được sao chép | Vô hiệu binding cũ; đăng ký seed mới sau xác minh |
| SIM/eSIM và SMS | Nhận mã xác thực hoặc recovery | Đánh giá độ tin cậy của số, phối hợp với nhà mạng |
| Email và kho mật khẩu | Tạo đường reset hoặc lộ nhiều bí mật khác | Bảo vệ các tài khoản gốc và thay bí mật có khả năng lộ |
| Recovery code đã lưu | Vượt qua một phần luồng xác thực thông thường | Thu hồi hoặc thay bộ mã bị ảnh hưởng |
| API key, chứng thư, token ứng dụng | Tiếp tục gọi API ngoài session trình duyệt | Thu hồi theo cơ chế riêng |
| Dữ liệu offline, tệp tải xuống | Có thể được đọc không cần server | Đánh giá lộ dữ liệu; server không thể thu hồi bản đã sao chép |

Nền tảng không nhất thiết biết mọi thứ trên thiết bị. Mục tiêu là có bản đồ đủ tin cậy cho những quyền do chính nền tảng quản lý và hướng dẫn rõ phần thuộc hệ thống khác.

### 2.2. Device ID chỉ có ý nghĩa trong mô hình quản lý của sản phẩm

Một `device_id` có thể là ID cài đặt ứng dụng, ID đăng ký push hoặc bản ghi thiết bị do server cấp. Nó không tự là số định danh vật lý duy nhất, khó giả mạo và không đổi.

IP, User-Agent, tên máy và fingerprint hỗ trợ nhận diện trên giao diện nhưng không tự chứng minh ai đang giữ thiết bị. Đừng cho client gửi một device ID tùy ý rồi suy ra họ có quyền thu hồi mọi session mang ID đó.

Liên kết đáng tin có thể gồm:

~~~text
account_id + tenant_id
  -> device_registration
  -> session_family
  -> refresh_token_family
  -> credential_binding hoặc device_key
  -> notification_endpoint
~~~

Mỗi liên kết cần nguồn gốc, trạng thái và phiên bản. Không giả định mọi credential được tạo khi truy cập từ cùng một trình duyệt đều chỉ tồn tại trên trình duyệt đó.

### 2.3. Khóa màn hình không phải bằng chứng thiết bị còn an toàn

Thông tin “máy đang khóa” hữu ích cho đánh giá rủi ro nhưng có thể thiếu hoặc đã cũ. Kẻ trộm có thể biết mã mở khóa, máy có thể bị lấy khi đang mở hoặc dữ liệu đã được truy cập trước lúc khóa từ xa có hiệu lực.

Cũng không nên suy ra private key chắc chắn đã bị xuất chỉ vì máy bị trộm. Cần phân biệt nguy cơ sử dụng credential trên máy, nguy cơ sao chép bí mật và bằng chứng xâm phạm thực tế. Quyết định cô lập có thể cần thực hiện trước khi điều tra xong các khả năng đó.

## 3. Phân loại báo cáo và chọn phạm vi cô lập

### 3.1. Những câu hỏi hỗ trợ quyết định

- Thiết bị nào bị lấy và người dùng còn thiết bị nào để thao tác?
- Máy bị lấy khi đang mở khóa hay chưa xác định được?
- Mã mở khóa, mật khẩu hoặc secret có khả năng bị người khác biết không?
- Những session, credential và kênh recovery nào liên quan?
- Có thay email, số điện thoại, MFA hoặc quyền truy cập gần thời điểm sự cố không?
- Người yêu cầu đang chứng minh quyền bằng phương tiện nào, phương tiện đó có nằm trên máy bị trộm không?
- Hệ thống có thể cô lập chính xác một thiết bị hay chỉ biết tài khoản có nguy cơ?

Những câu hỏi này phục vụ định tuyến và đánh giá rủi ro. Câu trả lời “tôi bị mất điện thoại” hoặc biết model máy không tự là bằng chứng cấp quyền quản lý tài khoản.

### 3.2. Cô lập có mục tiêu hay mở rộng toàn tài khoản?

| Mức hiểu biết | Hướng xử lý có thể phù hợp |
|---|---|
| Xác định rõ session và credential riêng của thiết bị | Thu hồi tập quyền có mục tiêu; rà soát đường truy cập liên quan |
| Có khả năng lộ mật khẩu hoặc recovery code | Mở rộng sang bí mật và các quyền được tạo từ chúng |
| Không thể giới hạn phạm vi hoặc đã thấy thay đổi bảo mật trái phép | Thu hồi rộng hơn và áp dụng trạng thái tài khoản hạn chế |
| Chỉ có báo cáo công khai chưa xác minh | Tiếp nhận an toàn, yêu cầu bằng chứng; chưa cấp quyền khóa tùy ý |
| Bằng chứng đủ cho báo mất nhưng chưa đủ cho recovery | Cho hành động bảo vệ trong phạm vi chính sách; giữ bước khôi phục riêng |

Đăng xuất mọi phiên có thể phù hợp khi không xác định được phạm vi. Tuy nhiên, đó là quyết định có tác động tới người dùng hợp lệ và phải dựa trên quyền báo sự cố đã được xác minh tương ứng.

Không mặc định giữ lại “phiên hiện tại” như một phiên an toàn. Người gọi có thể đang dùng chính thiết bị bị trộm hoặc một session bị sao chép. Việc giữ lại phải dựa trên bằng chứng và nguồn gốc phiên đủ tin cậy.

## 4. Cho báo mất nhanh nhưng không mở đường chiếm đoạt

### 4.1. Tách quyền bảo vệ khỏi quyền đăng nhập lại

Nên định nghĩa các capability nghiệp vụ có phạm vi hẹp:

~~~text
REPORT_STOLEN_DEVICE:
  Ghi nhận một báo cáo có bằng chứng theo chính sách.

CONTAIN_DEVICE_ACCESS:
  Chặn tập quyền đã được server xác định.

REVIEW_ACCOUNT_SECURITY:
  Xem dữ liệu bảo mật tối thiểu trong phạm vi cho phép.

REPLACE_AUTHENTICATOR:
  Đăng ký phương tiện thay thế sau xác minh đủ điều kiện.

RESTORE_NORMAL_ACCESS:
  Kết thúc trạng thái hạn chế và cấp quyền truy cập theo chính sách.
~~~

Một capability `CONTAIN_DEVICE_ACCESS` không được dùng ở endpoint reset mật khẩu hoặc thêm passkey. Kết quả xử lý báo mất không tự tạo session đăng nhập đầy đủ.

NIST phân biệt báo mất hoặc xâm phạm authenticator với khôi phục quyền truy cập: một phương tiện dự phòng có thể được dùng để báo sự cố, và việc báo có thể chỉ yêu cầu một yếu tố trong phạm vi được mô tả. Tài liệu yêu cầu xử lý authenticator bị xâm phạm kịp thời. Không nên biến yêu cầu MFA đầy đủ của bước khôi phục thành rào cản tuyệt đối cho mọi hành động báo mất. [NIST SP 800-63B-4 — Loss, Theft, Damage, and Compromise](https://pages.nist.gov/800-63-4/sp800-63b/events/#loss-theft-damage-and-compromise).

Việc áp dụng cụ thể vẫn cần chính sách chống lạm dụng. Một bằng chứng đủ để tạm hạn chế một authenticator không tự đủ để biết toàn bộ hồ sơ hoặc nhận token mạnh hơn.

### 4.2. Khi không còn phương tiện trên thiết bị khác

Các đường có thể được chuẩn bị trước gồm:

- Hardware security key hoặc authenticator khác đã đăng ký.
- Recovery code được cất riêng khỏi thiết bị bị trộm.
- Kênh recovery đã thiết lập và còn đáng tin.
- Quy trình hỗ trợ có bằng chứng phù hợp với mô hình tài khoản.

Không yêu cầu duyệt push trên chính điện thoại đã bị trộm để cho phép báo mất điện thoại. Nếu kênh đó nằm trong phạm vi nghi ngờ, không dùng nó làm bằng chứng độc lập duy nhất.

Nếu tài khoản chưa từng được gắn với danh tính thật, giấy tờ mới xuất trình không tự chứng minh người mang giấy tờ sở hữu tài khoản trước đây. Quy trình hỗ trợ phải biết bằng chứng nào thực sự liên hệ với tài khoản.

### 4.3. Ngăn gây gián đoạn bằng báo cáo giả

Biểu mẫu công khai nên có giới hạn và phản hồi không tiết lộ tài khoản. Trước khi áp dụng tác dụng bảo vệ cần xác minh đúng phạm vi, thay vì chỉ nhận account ID hoặc email.

Giới hạn theo tài khoản, nguồn truy cập, context, tenant và ngân sách tổng. Không cho tạo nhiều báo cáo để liên tục khóa tài khoản của người khác, nhưng cũng không để ngân sách bị người lạ tiêu hết làm chủ tài khoản không thể báo thật.

Các chính sách giới hạn cần có đường xử lý cho người dùng hợp lệ. CAPTCHA hoặc việc biết tên thiết bị không thay thế kiểm tra quyền.

## 5. Thu hồi session, token và kết nối đang hoạt động

### 5.1. Thu hồi ở phía server

Xóa cookie trên một trình duyệt khác hoặc đặt nhãn `device=LOST` không tự vô hiệu cookie đang nằm trên thiết bị bị trộm.

Với session server-side, đánh dấu phiên hoặc family không còn được chấp nhận tại kho có thẩm quyền. Bao gồm các ID đã xoay nhưng vẫn nằm trong grace period, không chỉ ID mới nhất được hiển thị.

OWASP nêu yêu cầu vô hiệu session phía server và xử lý các ID thuộc cùng một phiên logic, kể cả trường hợp xoay ID hoặc thao tác gia hạn đang diễn ra. Bài này dùng nguyên tắc đó cho thao tác đăng xuất thiết bị từ xa. [OWASP Session Management — Logout Button](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#logout-button).

Không trả thành công thu hồi trước khi có trạng thái bền vững để mọi lần chấp nhận tiếp theo thực thi được quyết định theo mô hình nhất quán của hệ thống.

### 5.2. Access token và refresh token cần cơ chế riêng

| Loại quyền | Vấn đề | Cơ chế cần quyết định |
|---|---|---|
| Session ID | Kho phiên hoặc cache vẫn chấp nhận | Trạng thái thu hồi có thẩm quyền, version và invalidation phù hợp |
| Refresh token | Tiếp tục tạo access token mới | Thu hồi token family/grant; kiểm tra lúc refresh |
| JWT access token | Chữ ký vẫn hợp lệ sau báo mất | Kiểm tra epoch, introspection, denylist hoặc giới hạn tương đương |
| Remember-me token | Đăng nhập lại không cần kiểm tra đủ | Thu hồi binding hoặc family tương ứng |
| API key | Không chịu trạng thái session | Vô hiệu key hoặc quyền liên quan bằng cơ chế riêng |
| Token ràng buộc với khóa trên máy | Kẻ giữ máy có thể vẫn sử dụng khóa | Đánh giá và thu hồi cả binding khóa/token trong phạm vi bị ảnh hưởng |

Khả năng chứng minh sở hữu khóa trên máy không giải quyết mọi trường hợp máy bị trộm. Nếu kẻ tấn công sử dụng được chính thiết bị và cơ chế kích hoạt khóa, token ràng buộc thiết bị vẫn có thể bị lạm dụng.

Thời hạn access token ngắn giúp giới hạn một số rủi ro, nhưng không tự đáp ứng yêu cầu thu hồi tức thời. Nếu thiết kế chấp nhận cửa sổ còn hiệu lực, cần mô tả rõ; với thao tác nhạy cảm có thể phải chặn tại điểm kiểm tra có thẩm quyền.

### 5.3. Kết nối dài và dữ liệu đã tải

Một WebSocket hoặc phiên streaming đã được xác thực lúc mở có thể tiếp tục nhận dữ liệu nếu không có cơ chế kiểm tra lại hoặc đóng khi quyền đổi.

Kết nối tới dịch vụ khác, URL tải tệp có chữ ký và tác vụ xuất dữ liệu cũng cần được xem xét. Không mặc định chúng kiểm tra lại cookie ở mỗi lần sử dụng.

Thu hồi server ngăn quyền truy cập tương lai theo cơ chế của hệ thống. Nó không xóa được tệp đã tải xuống, ảnh chụp màn hình hoặc bí mật đã được sao chép trước đó.

## 6. Xử lý từng loại authenticator và bí mật

### 6.1. Passkey gắn thiết bị và passkey đồng bộ

Với một credential được xác định thuộc phạm vi bị xâm phạm, relying party có thể ngừng chấp nhận credential đó trong dữ liệu có thẩm quyền. Không chỉ ẩn nó khỏi danh sách quản lý.

Passkey đồng bộ cần được giải thích khác. Một credential có thể xuất hiện trên nhiều authenticator thông qua cơ chế sao lưu hoặc đồng bộ; các cờ backup eligibility và backup state mô tả thuộc tính tương ứng, không phải danh sách đầy đủ các máy đang giữ bản sao. [W3C WebAuthn Level 3 — Credential Backup State](https://www.w3.org/TR/webauthn-3/#sctn-credential-backup-state).

Hệ quả thiết kế:

- Xóa một bản ghi thiết bị ứng dụng không tự xóa bản sao passkey trong nhà cung cấp đồng bộ.
- Thu hồi credential tại relying party có thể làm mọi bản sao của credential đó không dùng được cho dịch vụ, kể cả bản sao trên máy hợp lệ.
- Không luôn có cách xác định từ assertion rằng bản sao nào trên thiết bị vật lý nào đang được dùng.
- Chỉ xóa passkey trong giao diện kho lưu trữ không thay thế trạng thái chấp nhận credential của server.
- Nếu tài khoản đồng bộ bị ảnh hưởng, phải xử lý quyền truy cập tới hệ thống đồng bộ theo cơ chế của bên quản lý.

Không dùng tên thiết bị hoặc AAGUID như một định danh duy nhất của chiếc máy bị trộm. Nếu không xác định được bản sao nào bị ảnh hưởng, cần giải thích tác động khi thu hồi cả credential và cung cấp đường khôi phục thích hợp.

Một assertion có user verification vẫn phải được kiểm tra trạng thái credential hiện tại. Nó không là bằng chứng rằng thiết bị chưa bị trộm hoặc người đang dùng nó là chủ hợp lệ sau khi mã mở khóa bị lộ.

### 6.2. TOTP và recovery code

TOTP có thể vẫn đúng về mặt toán học dù authenticator đã bị báo mất. Verifier phải đối chiếu trạng thái binding trước khi chấp nhận.

Nếu seed có thể đã bị sao chép, việc cài lại ứng dụng trên máy mới với cùng seed không thu hồi bản sao của kẻ tấn công. Cần vô hiệu binding cũ và cấp seed mới sau xác minh đủ điều kiện.

Nếu recovery code được lưu trên máy bị trộm, thay bộ mã bị ảnh hưởng và vô hiệu mã cũ theo chính sách. Không để việc người dùng giữ một bản in khác khiến server coi bộ mã đã có nguy cơ lộ vẫn an toàn.

Mã recovery dùng một lần phải được tiêu thụ nguyên tử. Việc báo mất hoặc retry không được đặt lại trạng thái mã đã dùng.

### 6.3. SMS, email và kho mật khẩu

Số điện thoại trong database có thể không đổi dù SIM nằm trên máy bị trộm. Phải đánh giá người đang nhận SMS, không chỉ hỏi số còn khớp hồ sơ hay không.

Phối hợp với nhà mạng để xử lý SIM/eSIM thuộc thẩm quyền của nhà mạng; ứng dụng không được coi lệnh khóa thiết bị của mình là đã khóa SIM. Đăng ký số thay thế vẫn cần quy trình thay kênh có bằng chứng và kiểm soát rủi ro.

Nếu email recovery hoặc kho mật khẩu đăng nhập sẵn trên máy, đó có thể là đường tạo credential mới ngay sau thu hồi session ứng dụng. Bảo vệ tài khoản gốc và những bí mật có khả năng bị lộ là phần của đánh giá sự cố.

Không bắt người dùng đổi mọi mật khẩu ở mọi nơi một cách mù quáng. Xác định dữ liệu nào có thể bị truy cập, mật khẩu nào đã lưu hoặc có dấu hiệu lộ và quyền nào cần ưu tiên thay.

## 7. Mô hình trạng thái: tiếp nhận không đồng nghĩa đã cô lập

### 7.1. Trạng thái hồ sơ sự cố

~~~mermaid
stateDiagram-v2
    [*] --> REPORTED: Nhận báo cáo
    REPORTED --> VERIFIED_FOR_CONTAINMENT: Đủ bằng chứng cho phạm vi bảo vệ
    REPORTED --> AWAITING_EVIDENCE: Cần bằng chứng bổ sung
    AWAITING_EVIDENCE --> VERIFIED_FOR_CONTAINMENT
    VERIFIED_FOR_CONTAINMENT --> CONTAINING: Commit chặn quyền có thẩm quyền
    CONTAINING --> CONTAINED: Đạt các điều kiện thực thi bắt buộc
    CONTAINING --> CONTAINMENT_DEGRADED: Có hệ thống chưa thực thi được
    CONTAINMENT_DEGRADED --> CONTAINED: Khắc phục và xác nhận
    CONTAINED --> REMEDIATING: Xử lý bí mật và thay đổi liên quan
    REMEDIATING --> RECOVERING: Thiết lập lại phương tiện an toàn
    RECOVERING --> RESOLVED: Đủ điều kiện kết thúc
~~~

Trạng thái này là mô hình tham khảo, không bắt buộc mọi ứng dụng có cùng tên.

`CONTAINED` phải có định nghĩa cụ thể: tập quyền nào đã bị chặn, ở đâu và có cửa sổ còn hiệu lực nào được chấp nhận. Nếu một dịch vụ quan trọng vẫn cho token cũ thực hiện thao tác nhạy cảm, không đánh dấu hoàn tất chỉ vì message đã gửi.

### 7.2. Trạng thái credential tách khỏi hồ sơ

~~~text
ACTIVE -> SUSPENDED -> REVOKED
ACTIVE -> REVOKED
~~~

Một chính sách có thể cho khôi phục `SUSPENDED` bằng xác minh độc lập đủ điều kiện. Với credential đã thu hồi vì xâm phạm, thiết kế tham khảo không tự kích hoạt lại; phương tiện thay thế dùng binding mới.

NIST có mô tả việc tạm đình chỉ và điều kiện xem xét khôi phục khi được hỗ trợ. Vì vậy, không đồng nhất mọi hình thức đình chỉ với thu hồi vĩnh viễn. [NIST SP 800-63B-4 — Loss, Theft, Damage, and Compromise](https://pages.nist.gov/800-63-4/sp800-63b/events/#loss-theft-damage-and-compromise).

Tìm lại máy không tự đưa credential hoặc session về `ACTIVE`. Cần đánh giá việc máy có thể đã bị mở, sao chép dữ liệu hoặc thay đổi bảo mật trong thời gian mất kiểm soát.

## 8. Ghi quyết định cô lập bền vững và thực thi trên nhiều dịch vụ

### 8.1. Mô hình dữ liệu tham khảo

| Thực thể | Trường tiêu biểu | Trách nhiệm |
|---|---|---|
| `account_security` | account, tenant, account epoch, recovery version, security state | Hàng rào chung cho xác thực và thay đổi bảo mật |
| `device_registration` | device ref, account, status, device access version | Quản lý một đăng ký thiết bị có nguồn gốc rõ |
| `session_family` | account, device ref nếu có, generation, status, issued epoch | Toàn bộ phiên logic và các lần xoay |
| `refresh_token_family` | grant ref, account, source session, status | Khả năng gia hạn quyền truy cập |
| `authenticator_binding` | credential ref, loại, trạng thái, version, nguồn đăng ký | Những phương tiện server còn chấp nhận |
| `device_loss_incident` | incident ref, actor/evidence ref, phạm vi, trạng thái | Điều phối sự cố và kết quả cần đạt |
| `containment_capability` | digest, purpose, account/tenant, scope, hạn, context, lần dùng | Quyền bảo vệ có phạm vi đã được xác minh |
| `revocation_action` | action ref, incident, target, desired version, status | Theo dõi hành động ở từng hệ thống |
| `security_event`, `outbox` | event ID, version, loại, payload tối thiểu | Audit và giao việc sau commit |
| `operation_receipt` | thao tác, scope digest, context, kết quả commit | Retry không mở rộng hoặc lặp lại tác dụng |

Các bảng chỉ nêu trách nhiệm; triển khai cần ràng buộc account/tenant, khóa ngoại, tính duy nhất và kiểm soát truy cập tương ứng.

Credential đồng bộ không nên bị mô hình hóa như luôn thuộc duy nhất một đăng ký thiết bị. Session không có liên kết đáng tin cũng không được tự gán vào một máy chỉ từ User-Agent.

### 8.2. Đặt hàng rào trước, giao việc ngoài hệ thống sau

Trong một transaction có thẩm quyền, backend có thể:

1. Xác minh lại capability báo mất/cô lập và trạng thái tài khoản.
2. Chốt phạm vi bảo vệ do server quyết định.
3. Đặt trạng thái hạn chế các thao tác bảo mật có nguy cơ.
4. Đánh dấu thu hồi session, token family và credential thuộc thẩm quyền cục bộ.
5. Tăng các phiên bản truy cập/recovery cần thiết.
6. Ghi hồ sơ, các hành động còn phải thực hiện và outbox.
7. Tiêu thụ capability, ghi receipt và audit.

Sau commit, worker gọi các hệ thống ngoài transaction như IdP, dịch vụ token khác hoặc cơ chế quản lý thiết bị.

Không giữ transaction database mở để chờ khóa máy từ xa. Nếu bên ngoài bị timeout, quyết định chặn cục bộ đã commit không được rollback chỉ để mọi trạng thái trông đồng nhất.

Outbox bảo đảm có dữ liệu để retry, không chứng minh công việc bên ngoài đã hoàn thành. Mỗi hành động cần kết quả riêng và điều kiện đóng hồ sơ rõ ràng.

### 8.3. Mã giả của thao tác cô lập

Ví dụ dưới đây thể hiện ranh giới nghiệp vụ. Repository, policy và kiểu dữ liệu là giả định, không phải API thư viện hoặc chương trình chạy nguyên trạng:

~~~java
ContainmentResult contain(ContainmentCommand command) {
    inputLimits.check(command);
    abuseLimiter.check(command.publicContext());

    // Chỉ định tuyến từ capability do server quản lý.
    CapabilityRoute route =
            capabilities.lookupRoute(command.capabilitySecret());

    ContainmentResult result = transactions.execute(tx -> {
        LockedIncidentContext state = store.lockInOrder(tx, route);

        capabilityPolicy.requireMatchingSecretPurposeAndContext(
                state, command);

        if (receipts.hasCommittedOperation(state, command.operationRef())) {
            return receipts.safeResultForSameScopeAndContext(
                    state, command);
        }

        Instant now = tx.currentWallClockTime();
        capabilityPolicy.requireUnusedAndUnexpired(state, now);
        evidencePolicy.requireEnoughForContainment(state, now);

        ContainmentPlan plan = containmentPolicy.buildCurrentPlan(state);
        containmentPolicy.requireAuthorizedTargets(state, plan);

        security.placeRequiredRestrictions(tx, state.accountId(), plan);
        sessions.revokeAffectedFamilies(tx, plan);
        refreshTokens.revokeAffectedFamilies(tx, plan);
        authenticators.suspendOrRevokeAffectedBindings(tx, plan);
        security.advanceRequiredRevocationVersions(tx, plan);
        recovery.invalidateAffectedChallengesAndGrants(tx, plan);

        Incident incident = incidents.recordContaining(tx, state, plan);
        actions.recordRequiredExternalActions(tx, incident, plan);
        outbox.enqueueActionsAndNotifications(tx, incident, plan);

        capabilities.markUsed(tx, state.capabilityId(), now);
        receipts.recordCommittedScope(tx, incident, command, plan);
        audit.appendContainmentDecision(tx, incident, plan);

        return ContainmentResult.localDecisionCommitted(incident);
    });

    // Không khẳng định external actions đã hoàn tất.
    return result;
}
~~~

Việc tra route trước transaction không phải một quyết định cấp quyền. Secret, purpose, account, tenant, phạm vi và context phải được đối chiếu lại dưới cơ chế đồng bộ có thẩm quyền.

`buildCurrentPlan` không nhận danh sách account hoặc credential tùy ý từ client. Nó dựa trên liên kết server và quyền được cấp. Nếu không giới hạn được phạm vi bằng dữ liệu đáng tin, chính sách cần yêu cầu bằng chứng phù hợp cho phạm vi rộng hơn.

`advanceRequiredRevocationVersions` có thể tăng phiên bản theo thiết bị khi toàn bộ điểm nhận quyền có thể thực thi phạm vi đó, hoặc tăng account epoch cho phương án thu hồi rộng. Không giả định một epoch theo thiết bị có thể tách riêng từng bản sao của passkey đồng bộ.

Receipt chỉ trả lại trạng thái tối thiểu của thao tác đã commit cho đúng người được phép. Một idempotency key không phải bí mật thay thế capability và không được dùng để đổi phạm vi từ một thiết bị sang toàn tài khoản.

### 8.4. Trạng thái cục bộ và trạng thái phân tán

Có thể biểu diễn kết quả theo từng lớp:

~~~json
{
  "incidentRef": "incident-example-24",
  "status": "CONTAINING",
  "localRevocation": "COMMITTED",
  "requiredExternalActions": "PENDING",
  "nextAction": "CONTINUE_SECURITY_REVIEW"
}
~~~

Đây là response minh họa cho người đã được phép xem hồ sơ. Không công bố danh sách thiết bị hoặc trạng thái tài khoản qua endpoint báo mất công khai.

Nếu một dịch vụ không thực thi được version mới, có thể cần chặn các thao tác nhạy cảm ở gateway hoặc nguồn quyết định quyền cho tới khi khắc phục. Nếu không có hàng rào bao phủ được đường đó, hồ sơ phải phản ánh giới hạn còn lại.

Không coi một ACK nhận message là bằng chứng rằng mọi token đã bị từ chối. Hợp đồng giữa các dịch vụ cần xác định ACK nói về nhận việc, ghi trạng thái hay thực thi quyền.

## 9. Các cuộc đua phải xử lý tại điểm cấp và dùng quyền

### 9.1. Refresh đồng thời với báo mất

~~~text
R1: Đọc refresh token còn ACTIVE.
R2: Cô lập thiết bị, thu hồi family và tăng version, rồi commit.
R1: Cố phát access token mới.
~~~

Nếu R1 chỉ dựa vào kết quả đọc đầu tiên, token mới có thể sống sau thu hồi.

Endpoint refresh phải phối hợp với quyết định thu hồi bằng khóa hoặc cập nhật có điều kiện phù hợp. Token mới không được tự mang epoch hiện tại chỉ vì refresh token cũ đã qua một kiểm tra trước đó.

Quyền gia hạn phải còn hợp lệ tại điểm phát hành đã được đồng bộ. Không “nâng cấp” một token family đã bị thu hồi thành family mới.

### 9.2. Authenticator bị thu hồi giữa ceremony

Một challenge WebAuthn có thể được tạo trước báo mất, còn assertion quay về sau khi credential đã bị thu hồi.

Chữ ký hợp lệ chưa đủ. Trước khi cấp session hoặc quyền nhạy cảm, backend cần đối chiếu challenge, credential status, version và trạng thái tài khoản hiện tại trong cơ chế ngăn tranh chấp tương ứng.

TOTP hoặc OTP cũng vậy: mã đúng theo thuật toán không cho phép bỏ qua binding đã bị đình chỉ.

### 9.3. Thay đổi bảo mật từ session cũ

Kẻ giữ máy có thể bắt đầu thêm email, đổi số hoặc đăng ký credential ngay trước báo mất. Điểm ghi thay đổi phải kiểm tra lại session và trạng thái an ninh, không chỉ middleware đã kiểm tra ở đầu request.

Những đường ghi này cần cùng cơ chế phối hợp với hàng rào cô lập. Nếu một thay đổi đã commit trước hàng rào, nó là dữ liệu cần điều tra và xử lý, không biến mất khi session cũ bị thu hồi.

Không chỉ thu hồi những credential hiện đang gắn với device ID nếu kẻ tấn công đã tạo một credential mới không còn mang liên kết đó. Cần nguồn gốc đăng ký, source session và lịch sử thay đổi; khi thiếu dữ liệu, đánh giá phạm vi rộng hơn.

### 9.4. Tác vụ đang chạy và hiệu lực trong tương lai

Một tác vụ xuất tệp hoặc giao dịch nền có thể đã được xếp hàng bằng quyền cũ. Worker cần quyết định xem có phải kiểm tra lại quyền trước khi tạo tác dụng nhạy cảm hay không.

Không thể luôn hủy một tác dụng đã hoàn tất ở hệ thống khác. Phân biệt:

- Quyền chưa được sử dụng và có thể chặn.
- Tác vụ đã nhận nhưng chưa tạo tác dụng.
- Tác dụng đã commit, cần xử lý nghiệp vụ riêng.
- Dữ liệu đã giao hoặc sao chép, không thể chắc chắn thu hồi.

Một lời hứa “mọi hoạt động dừng ngay khi bấm báo mất” chỉ đúng nếu có cơ chế bao phủ các điểm tạo tác dụng đó. Thiết kế cần nêu giới hạn thực tế.

## 10. Những thay đổi và bí mật cần rà soát sau cô lập

### 10.1. Không dừng ở session đã biết

Rà soát theo quyền và dữ liệu có khả năng bị ảnh hưởng:

| Hạng mục | Dấu hiệu cần tìm | Hướng xử lý |
|---|---|---|
| Email/số recovery | Kênh mới, kênh cũ bị xóa, yêu cầu đang chờ | Giữ hoặc thu hồi thay đổi, xác minh lại theo chính sách |
| Credential | Passkey, TOTP hoặc khóa mới | Kiểm tra nguồn đăng ký, vô hiệu khi không còn đáng tin |
| Recovery code | Bộ mã mới phát hoặc bộ cũ nằm trên máy | Vô hiệu bộ bị ảnh hưởng và cấp mới đúng quyền |
| API/ứng dụng được ủy quyền | Key mới, grant mới, quyền tăng | Thu hồi phạm vi liên quan |
| Mật khẩu | Đã lưu trên máy, đã bị đổi, có dấu hiệu truy cập | Đặt mật khẩu mới khi phù hợp; không khôi phục hash cũ |
| Dữ liệu và hoạt động nhạy cảm | Xuất dữ liệu, chia sẻ, đổi quyền | Chặn phần chưa thực hiện và xử lý tác dụng đã xảy ra |
| Session khác | Phiên được tạo từ credential có thể lộ | Đánh giá nguồn gốc, không mặc định ngoài máy bị trộm là an toàn |

Thời gian báo mất và thời gian thực tế mất kiểm soát có thể khác nhau. Không chỉ lọc các thay đổi sau thời điểm người dùng bấm báo cáo.

Mốc thời gian giúp thu hẹp điều tra nhưng không tự chứng minh thay đổi nào hợp lệ. Một credential đăng ký trước báo cáo vẫn có thể do kẻ tấn công tạo.

### 10.2. Không đảo dữ liệu bảo mật một cách máy móc

Không phục hồi toàn bộ hồ sơ tài khoản từ snapshot trước sự cố. Cách này có thể làm sống lại session, recovery code hoặc credential đã bị thu hồi từ trước.

Nếu cần hủy một thay đổi email hoặc số, dùng giao dịch bù có kiểm tra đối tượng, phiên bản, quyền và tính hợp lệ hiện tại. Email hoặc số lịch sử có thể đã mất an toàn hoặc được cấp cho người khác.

Nếu credential cũ có nguy cơ lộ, tạo secret mới thay vì sao chép seed, private key hoặc hash cũ từ backup.

### 10.3. Khi hệ thống không có đủ lịch sử

Thiếu audit không phải lý do khẳng định chưa có thay đổi trái phép. Giữ trạng thái hạn chế phù hợp, dùng bằng chứng độc lập để thiết lập lại những phương tiện cần thiết và ghi rõ giới hạn điều tra.

Hệ thống mới nên lưu nguồn gốc của các hành động bảo mật ngay từ đầu: actor, session hoặc capability nguồn, credential dùng để cấp quyền, phiên bản, thời gian và kết quả commit. Không đưa bí mật vào các bản ghi này.

## 11. Khôi phục phương tiện xác thực trên thiết bị an toàn

### 11.1. Đánh giá tính độc lập của bằng chứng

Một email, TOTP và SMS có thể là ba kênh logic nhưng đều nằm trên cùng điện thoại bị trộm. Chúng không còn là ba đường độc lập về rủi ro thiết bị.

Tương tự, một passkey xuất hiện trên laptop không tự là bằng chứng hoàn toàn độc lập nếu nó là bản sao đồng bộ của credential đang thuộc phạm vi xâm phạm hoặc nếu tài khoản đồng bộ bị chiếm.

Chính sách recovery cần xác định phương tiện nào còn đáng tin và bằng chứng nào đủ cho thao tác tiếp theo. Không chỉ đếm số mã người yêu cầu có thể nhập.

Một phương tiện mới do kẻ tấn công đăng ký trong khoảng sự cố cũng không tự trở thành bằng chứng để giải quyết chính sự cố đó.

### 11.2. Context khôi phục có quyền hẹp

Khi đủ bằng chứng recovery, có thể tạo context ngắn hạn với mục đích rõ, chẳng hạn `REPLACE_AUTHENTICATOR`.

Context cần gắn với:

~~~text
account_id, tenant_id
incident_id
allowed_operations
recovery_version hoặc security_epoch
evidence_refs
expires_at
context_binding
single-use hoặc ngân sách thao tác được xác định
~~~

Nó không tự cấp quyền xem toàn bộ dữ liệu, thay mọi kênh hoặc thực hiện giao dịch.

Đăng ký authenticator mới phải theo ceremony tương ứng, kiểm tra origin/challenge và yêu cầu của phương tiện. Sau đó xác nhận người dùng sử dụng được phương tiện mới theo chính sách trước khi kết thúc recovery.

Nếu cơ chế cần delay cho thay số hoặc kênh recovery, delay bảo vệ việc cấp quyền mới. Nó không được trì hoãn việc chặn authenticator đã bị xác định xâm phạm.

### 11.3. Cấp lại quyền truy cập thông thường

Chỉ đưa tài khoản về trạng thái bình thường khi đạt những điều kiện đã định nghĩa:

- Tập quyền bị ảnh hưởng đã được chặn theo phạm vi cần thiết.
- Không còn thay đổi bảo mật đáng ngờ đang được tự động áp dụng.
- Có phương tiện xác thực còn đáng tin hoặc phương tiện thay thế được đăng ký đúng.
- Các bí mật cần thay đã được xử lý.
- Những hành động bắt buộc tại hệ thống liên quan đã hoàn tất hoặc có cơ chế bù đủ để kiểm soát rủi ro.
- Người dùng đã hoàn tất bước xác thực cần thiết để nhận session mới.

Session mới dùng secret và phiên bản mới. Không nâng phiên bị thu hồi thành phiên hợp lệ hoặc sao chép cookie cũ.

Nếu thu hồi rộng làm phiên báo sự cố cũng bị chặn, có thể cung cấp receipt/context bảo vệ riêng trong cùng quyết định có thẩm quyền theo chính sách. Quyền này không tự là session đăng nhập và không được miễn xác minh chỉ để giúp giao diện tiếp tục chạy.

### 11.4. Khi tìm lại được thiết bị

Việc tìm lại máy chỉ kết thúc tình trạng thất lạc vật lý. Nó không chứng minh không có dữ liệu bị sao chép.

Không tự hủy sự cố, mở lại token cũ hoặc gắn lại credential đã thu hồi. Đánh giá thiết bị theo quy trình phù hợp, rồi đăng ký lại bằng chứng và binding mới nếu cần.

Đối với đình chỉ tạm thời, chỉ xem xét khôi phục khi chính sách hỗ trợ và có bằng chứng độc lập đủ điều kiện. Hành động đó phải được ghi riêng, không diễn ra chỉ vì máy xuất hiện online.

## 12. Phối hợp ngoài ứng dụng và giới hạn của khóa/xóa từ xa

Ứng dụng quản lý tài khoản, nhà cung cấp hệ điều hành, nhà mạng và IdP có phạm vi khác nhau:

| Chủ thể | Có thể quản lý | Không tự bảo đảm |
|---|---|---|
| Ứng dụng | Session, credential và dữ liệu thuộc dịch vụ | Khóa toàn hệ điều hành hoặc vô hiệu SIM |
| Cơ chế quản lý thiết bị/hệ điều hành | Khóa, định vị hoặc xóa theo khả năng đã thiết lập | Thu hồi mọi token ở mọi dịch vụ độc lập |
| Nhà mạng | SIM/eSIM và dịch vụ số điện thoại | Thu hồi cookie hoặc passkey của ứng dụng |
| IdP/tài khoản đồng bộ | Phiên và credential trong phạm vi của họ | Tự đóng mọi phiên RP đã có nếu không có cơ chế phối hợp |
| Relying party | Quyền truy cập của ứng dụng mình | Xóa private key khỏi mọi bản sao vật lý |

Khóa hoặc xóa từ xa có thể phụ thuộc vào thiết lập trước đó, kết nối và khả năng của nền tảng. Không coi trạng thái “đã yêu cầu xóa” là bằng chứng rằng dữ liệu đã bị xóa.

Nếu thiết bị offline, việc thu hồi phía server vẫn cần có hiệu lực khi nó kết nối lại hoặc gửi request. Không chờ lệnh quản lý thiết bị được xác nhận rồi mới thu hồi session.

Dữ liệu offline đã được truy cập hoặc sao chép có thể không thu hồi được. Giao diện nên phân biệt rõ trạng thái lệnh thiết bị và trạng thái quyền tài khoản.

Người dùng cần thực hiện các thao tác ngoài ứng dụng từ thiết bị còn đáng tin và qua kênh chính thức. Không gửi mã recovery hoặc secret cho người liên hệ tự xưng đã tìm thấy máy.

## 13. Thông báo, audit và giao diện xử lý

### 13.1. Thông báo không được phát lại bí mật cho thiết bị bị trộm

Sau báo mất, không gửi token phục hồi mạnh tới chính push endpoint, SIM hoặc email đang nằm trong phạm vi nghi ngờ chỉ vì chúng là kênh mặc định.

Có thể cần thông báo tối thiểu tới một số kênh để hỗ trợ phát hiện, nhưng đích nhận bí mật và quyền tiếp tục recovery phải theo chính sách tin cậy riêng.

Thông báo nên nêu sự kiện, thời gian, tác dụng đã thực hiện và cách phản đối. Tránh tiết lộ địa chỉ đầy đủ, danh sách credential hoặc đường khôi phục mới tới kênh có nguy cơ.

### 13.2. Audit phân biệt ý định, commit và thực thi

Một event có thể có dạng:

~~~json
{
  "eventId": "evt-device-containment-example",
  "eventType": "DEVICE_CONTAINMENT_COMMITTED",
  "accountRef": "account-internal-17",
  "tenantRef": "tenant-internal-03",
  "incidentRef": "incident-internal-24",
  "scopeType": "ACCOUNT_WIDE",
  "revocationVersion": 42,
  "externalActionsState": "PENDING"
}
~~~

Các giá trị chỉ minh họa. Không đưa token, OTP, private key, TOTP seed, recovery code hoặc raw session ID vào audit.

Các event `REPORTED`, `LOCAL_REVOCATION_COMMITTED`, `REQUIRED_ACTION_FAILED` và `CONTAINMENT_COMPLETED` cần có nghĩa khác nhau. Không ghi hoàn tất trước commit hoặc trước điều kiện thực thi bắt buộc.

Giới hạn quyền truy cập, thời gian lưu và dữ liệu vị trí/thiết bị theo nhu cầu điều tra. Nếu dùng tham chiếu session để liên kết sự kiện, dùng cách không làm lộ secret có thể đăng nhập.

### 13.3. Giao diện phải phản ánh tác dụng thật

Thay vì một dấu tích chung “đã xóa thiết bị”, có thể hiển thị:

~~~text
Đã chặn các phiên thuộc phạm vi xử lý trong ứng dụng.
Đang chờ xác nhận thu hồi từ hệ thống đăng nhập liên quan.
Cần kiểm tra phương tiện xác thực và kênh khôi phục.
Lệnh khóa/xóa thiết bị là thao tác riêng của nền tảng quản lý thiết bị.
~~~

Chỉ hiển thị các trạng thái mà server thực sự biết. Không gọi một nhãn thiết bị trên ứng dụng là vị trí vật lý chắc chắn.

Trước thao tác có tác động rộng, sản phẩm cần giải thích phạm vi: thu hồi một credential đồng bộ có thể làm các máy khác mất khả năng dùng credential đó. Giải thích này giúp người dùng chọn và hiểu kết quả trong luồng, không thay thế kiểm tra quyền server.

## 14. Ví dụ xuyên suốt: điện thoại bị lấy khi đang mở khóa

An bị lấy điện thoại lúc 09:00. Trên điện thoại có session ứng dụng, TOTP, SIM và email. An còn laptop và một hardware security key được cất riêng.

1. Lúc 09:05, An mở trang bảo mật từ laptop qua địa chỉ tin cậy. Phiên laptop giúp định tuyến nhưng không tự chứng minh toàn bộ quyền khôi phục.
2. An dùng phương tiện đủ điều kiện để báo mất và cho phép phạm vi cô lập theo chính sách. Backend không yêu cầu duyệt push trên điện thoại bị trộm.
3. Server rà liên kết session, refresh family và credential. Do điện thoại đang mở và email recovery cũng có thể bị truy cập, chính sách mở rộng xử lý thay vì chỉ xóa một device registration.
4. Transaction ghi hàng rào, thu hồi quyền cục bộ, tăng version cần thiết, giữ thay đổi bảo mật và tạo outbox. Response cho biết quyết định cục bộ đã commit, không tuyên bố mọi bên ngoài đã hoàn tất.
5. Một refresh request từ điện thoại đã bắt đầu trước bước 4 phải kiểm tra lại trạng thái tại điểm phát hành, nên không được cấp quyền mới từ family vừa thu hồi.
6. Worker xử lý các hệ thống liên quan. Một hệ thống lỗi giữ hồ sơ ở trạng thái chưa hoàn tất; retry không gỡ hàng rào đã có.
7. An dùng hardware security key còn đáng tin để thực hiện các bước recovery cần thiết. TOTP cũ bị vô hiệu nếu thuộc phạm vi xâm phạm; authenticator thay thế dùng seed mới.
8. Hệ thống kiểm tra thay email, số, passkey và ứng dụng được ủy quyền trong khoảng mất kiểm soát, kể cả thay đổi trước lúc báo cáo.
9. Khi đủ điều kiện, An xác thực lại và nhận session mới. Những phiên đã thu hồi không được hồi sinh.
10. Nếu tìm lại điện thoại sau đó, các token cũ vẫn không có quyền. Thiết bị chỉ được dùng lại sau quy trình đánh giá và đăng ký thích hợp.

Nếu phương tiện duy nhất An còn dùng trên laptop là bản sao của một passkey đồng bộ đang bị nghi ngờ, không tự coi nó tương đương hardware key độc lập trong ví dụ. Cần đánh giá phạm vi credential và tài khoản đồng bộ.

Nếu An không còn phương tiện nào đủ tin cậy, hồ sơ vẫn có thể tiếp nhận và áp dụng tác dụng bảo vệ theo mức bằng chứng được chính sách cho phép; quyền đăng ký mới tiếp tục qua đường recovery riêng.

## 15. Các tình huống cần kiểm chứng khi triển khai

Bảng dưới là yêu cầu đối chiếu thiết kế, không phải kết quả kiểm thử đã chạy trên ứng dụng.

| Tình huống | Điều cần chứng minh |
|---|---|
| Báo mất chỉ bằng email/account ID công khai | Không cấp quyền khóa hoặc xem tài khoản tùy ý |
| Bằng chứng đủ cho cô lập nhưng chưa đủ recovery | Không phát session đầy đủ hoặc grant thêm credential |
| Thiết bị bị trộm là nơi nhận push mặc định | Không bắt duyệt hoặc gửi bí mật recovery duy nhất tới đó |
| Client sửa device ref, credential ref hoặc tenant | Không mở rộng phạm vi ngoài capability |
| Xóa device registration | Các quyền được xử lý thực tế, không chỉ mất dòng trên giao diện |
| Session có nhiều ID do rotation/grace period | Mọi ID cùng phiên logic thuộc phạm vi bị thu hồi |
| Refresh cạnh tranh với thu hồi | Không sinh token sống sau hàng rào từ family đã bị thu hồi |
| WebAuthn assertion về sau khi credential bị chặn | Chữ ký hợp lệ không vượt qua trạng thái hiện tại |
| TOTP đúng từ seed đã thu hồi | Verifier từ chối binding đó |
| Kẻ tấn công thêm credential trước báo cáo | Có đường rà soát và xử lý, không chỉ lọc theo device ID |
| Cùng passkey có bản sao trên nhiều máy | Phạm vi và tác động thu hồi credential được hiểu đúng |
| API key không dùng session epoch | Có cơ chế thu hồi riêng được thực thi |
| WebSocket hoặc tác vụ nền còn hoạt động | Không tiếp tục tạo tác dụng nhạy cảm trái chính sách |
| Token ràng buộc khóa thiết bị | Không mặc định chống được người đang giữ và sử dụng máy |
| Đăng xuất rộng gồm cả phiên báo mất | Context tiếp tục có quyền hẹp, không phục hồi phiên cũ |
| Hệ thống ngoài timeout hoặc callback bị trùng | Giữ hàng rào cục bộ, retry có giới hạn và kết quả riêng |
| Commit xong nhưng mất response | Retry không lặp tác dụng hoặc mở rộng scope |
| Đổi mật khẩu sau sự cố | Không mặc định session, API key và passkey cũ tự bị thu hồi |
| SIM bị lấy nhưng số không đổi | Kênh SMS được đánh giá theo quyền kiểm soát thực tế |
| Máy offline hoặc lệnh xóa chưa thực thi | Thu hồi server vẫn chặn khi quyền được dùng lại |
| Tìm lại thiết bị | Không tự tái kích hoạt credential/session đã thu hồi |
| Restore backup trước thời điểm thu hồi | Không chấp nhận lại quyền cũ khi chưa có hàng rào khôi phục |
| Log, trace và thông báo | Không chứa bí mật hoặc chi tiết vượt phạm vi người nhận |

Nên đo thời gian từ báo cáo đủ điều kiện đến commit hàng rào, thời gian các hệ thống bắt buộc thực thi, số hành động còn lỗi và lần token cũ bị từ chối. Không chỉ đo thời gian API trả response.

Kiểm chứng cần quan sát hành vi tại điểm chấp nhận quyền: request từ thiết bị cũ, refresh, ceremony đang dở và tác vụ nhạy cảm. Một response `REVOKED` không đủ nếu dịch vụ phía sau vẫn nhận token.

Khi restore hoặc failover làm mất lịch sử thu hồi, phải xử lý nhóm session, token hoặc credential bị ảnh hưởng trước khi mở lại quyền. Khởi động lại ứng dụng không tự sửa được phiên bản an ninh đã bị phục hồi lùi.

## 16. Tài liệu đối chiếu và phạm vi thiết kế

- [NIST SP 800-63B-4 — Loss, Theft, Damage, and Compromise](https://pages.nist.gov/800-63-4/sp800-63b/events/#loss-theft-damage-and-compromise): báo sự cố, xử lý authenticator bị xâm phạm và đình chỉ khi được hỗ trợ.
- [NIST SP 800-63B-4 — Invalidation](https://pages.nist.gov/800-63-4/sp800-63b/events/#invalidation): thu hồi liên kết authenticator.
- [OWASP Session Management — Logout Button](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#logout-button): vô hiệu session phía server và các ID liên quan.
- [W3C WebAuthn Level 3 — Credential Backup State](https://www.w3.org/TR/webauthn-3/#sctn-credential-backup-state): thuộc tính backup của credential đa thiết bị.

Capability cô lập, mô hình trạng thái sự cố, epoch, receipt và quy trình outbox trong bài là thiết kế tham khảo. Triển khai phải xác định mức bằng chứng, phạm vi thu hồi và khả năng thực thi của từng dịch vụ. Các ví dụ không tự chứng nhận mức bảo đảm, không bảo đảm xóa được dữ liệu đã sao chép và không thay thế quy trình quản lý thiết bị của bên có thẩm quyền.
