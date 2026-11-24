# Recovery compromise detection — Phát hiện việc chiếm dụng luồng khôi phục tài khoản

## 1. Phát hiện điều gì, trước khi quyết định xử lý thế nào?

Luồng khôi phục tài khoản tạo ra một con đường thay thế để người dùng lấy lại quyền truy cập khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Chính con đường đó cũng có thể bị lợi dụng để thay credential, thêm factor của người khác hoặc giữ quyền truy cập sau khi chủ tài khoản tưởng đã an toàn.

Recovery compromise detection là khả năng nhận biết bằng chứng cho thấy quy trình, bằng chứng khôi phục hoặc quyền được cấp qua recovery có thể đã bị chiếm dụng. Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, phát hiện cần theo dõi từ lúc khởi tạo yêu cầu đến khi thay credential và sử dụng session sau recovery.

Cần phân biệt ba tình huống:

| Tình huống | Ví dụ | Kết luận ban đầu phù hợp |
|---|---|---|
| Lạm dụng endpoint nhưng chưa chiếm được tài khoản | Gửi nhiều yêu cầu reset cho một email | Có abuse; chưa có bằng chứng recovery đã thành công |
| Nghi ngờ chiếm dụng một tài khoản | Recovery thành công, thay factor, rồi thực hiện tác vụ nhạy cảm từ ngữ cảnh lạ | Cần điều tra chuỗi sự kiện và bằng chứng xác minh |
| Vi phạm kiểm soát của cơ chế recovery | Grant đã hủy vẫn tạo credential mới theo thứ tự commit đã xác nhận | Có bằng chứng vi phạm bất biến; cần xác định phạm vi ảnh hưởng |

Một IP mới hoặc một lần quên mật khẩu không đủ để kết luận chủ tài khoản bị tấn công. Ngược lại, lưu lượng thấp không chứng minh recovery an toàn: một người có quyền truy cập email bị chiếm có thể hoàn tất chỉ một giao dịch.

Bài học tập trung vào thiết kế dữ liệu phát hiện, luật tương quan, đánh giá độ tin cậy và bàn giao bằng chứng cho xử lý sự cố. Các tên event, cửa sổ thời gian và ví dụ code là thiết kế minh họa; không phải cấu hình triển khai hoặc ngưỡng chuẩn cho mọi hệ thống.

Sau bài học, người học cần làm được:

- Xác định những điểm cần quan sát trong vòng đời recovery.
- Phân biệt dấu hiệu bất thường, vi phạm bất biến và sự cố đã được xác minh.
- Liên kết đúng account, tenant, transaction, grant, factor và session.
- Viết luật có thể giải thích được, kể cả khi dữ liệu thiếu hoặc đến muộn.
- Kiểm tra chất lượng phát hiện bằng dữ liệu giả lập và đối chứng hợp lệ.
- Tạo hồ sơ cảnh báo giúp người xử lý hiểu điều gì đã xảy ra và điều gì chưa biết.

## 2. Mô hình đe dọa của recovery compromise

### 2.1. Những tài sản cần được bảo vệ

Tài sản quan trọng không chỉ là mật khẩu. Đường kiểm soát tài khoản có thể nằm ở:

- Địa chỉ email hoặc số điện thoại dùng cho recovery.
- Recovery code và các bằng chứng đã được cấp trước.
- Grant dùng một lần cho thao tác thay credential.
- Quyền đăng ký passkey hoặc factor thay thế.
- Quyền phê duyệt của nhân viên hỗ trợ.
- Session, refresh token và các quyền tồn tại sau recovery.

Ví dụ, người chiếm email có thể đặt lại password rồi đăng ký factor của họ. Nếu hệ thống chỉ phát hiện password reset nhưng không theo dõi factor và session, nhóm vận hành có thể bỏ sót cách duy trì quyền truy cập.

[OWASP Forgot Password Cheat Sheet — Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise) lưu ý rằng đặt lại password đơn thuần có thể chưa lấy lại toàn bộ quyền kiểm soát khi session, thông tin recovery hoặc MFA đã bị thay đổi. Vì vậy, mô hình phát hiện phải bao quát các thay đổi đó, thay vì coi password reset thành công là điểm kết thúc quan sát.

### 2.2. Các đường chiếm dụng cần nhận diện

| Đường đe dọa | Dữ kiện có thể quan sát | Giới hạn của dữ kiện |
|---|---|---|
| Đoán hoặc thử bằng chứng recovery | Nhiều lần xác minh thất bại, nhiều nguồn hoặc nhiều account bị nhắm | Có thể lẫn với lỗi nhập, app lỗi hoặc automation hợp lệ |
| Sử dụng bằng chứng đã bị lộ | Recovery thành công trong ngữ cảnh khác với lúc khởi tạo | Không chứng minh bằng chứng bị lộ nếu người dùng đổi thiết bị |
| Chiếm kênh recovery | Đổi địa chỉ recovery rồi dùng địa chỉ đó để lấy lại tài khoản | Có thể là người dùng đổi email hợp lệ |
| Vượt quy trình hỗ trợ | Phê duyệt ngoài quyền, ngoài tenant hoặc thiếu bước bắt buộc | Phải đối chiếu policy và trạng thái thật |
| Replay hoặc race | Một quyền dùng một lần tạo nhiều thay đổi credential | Cần phân biệt hai tác động với hai bản sao cùng event |
| Duy trì quyền sau recovery | Refresh hoặc session cũ vẫn truy cập ngoài thời hạn thu hồi | Phải biết hợp đồng revocation và điểm thực thi |
| Lỗi hệ thống hoặc cấu hình | Nhiều account vi phạm cùng bất biến sau một lần triển khai | Không tự quy mọi bất thường cho một actor độc hại |

Một sự cố recovery có thể bắt nguồn từ lỗi code, cấu hình, provider hoặc thao tác hỗ trợ; không nhất thiết có người tấn công. Detector nên ghi nhận điều kiện vi phạm trước khi gán nguyên nhân.

## 3. Đặt detector vào vòng đời recovery

~~~mermaid
flowchart LR
    A[Khoi tao recovery] --> B[Cap bang chung hoac challenge]
    B --> C[Xac minh va danh gia chinh sach]
    C --> D[Cap quyen thay credential]
    D --> E[Commit thay doi]
    E --> F[Dang nhap va su dung session]
    A --> G[Su kien da xac minh nguon]
    B --> G
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H[Tuong quan va doi chieu trang thai]
    H --> I[Canh bao co bang chung]
~~~

Ở mỗi giai đoạn, câu hỏi phát hiện khác nhau:

1. Khi khởi tạo: có một account bị quấy rối hay nhiều account bị thăm dò?
2. Khi xác minh: số lần sai, mục đích và scope có phù hợp?
3. Khi cấp grant: bằng chứng nào và phiên bản policy nào đã cho phép?
4. Khi commit: thay đổi thực tế có đúng grant, account và trạng thái được phép?
5. Sau recovery: credential hoặc session mới có được sử dụng theo cách đáng ngờ?
6. Sau thu hồi: quyền cũ còn thực hiện được thao tác mà policy yêu cầu chặn hay không?

Không phải mọi quyết định đều chờ hệ thống giám sát. Các kiểm tra bắt buộc như token đúng purpose, còn hạn và chưa dùng phải được thực thi trong đường cấp quyền. Detector là lớp quan sát bổ sung để nhận ra hành vi, vi phạm và phạm vi ảnh hưởng; nó không thay thế authorization hoặc phép tiêu thụ grant nguyên tử.

### 3.1. Tách ba đầu ra

Một kiến trúc dễ vận hành tách:

- Event: dữ kiện đã xảy ra, như credential mutation đã commit.
- Finding: nhận định của một luật, kèm bằng chứng và mức tin cậy.
- Action: quyết định xử lý, như yêu cầu xác minh thêm hoặc thu hồi quyền.

Nếu chỉ lưu một log “suspicious=true”, người điều tra khó biết nhận định dựa trên dữ kiện nào. Nếu detector tự thay credential ngay khi có một IP lạ, người khác có thể biến detector thành công cụ gây mất quyền truy cập cho chủ tài khoản.

Việc chọn hành động thuộc chính sách phản ứng của hệ thống. Bài học chỉ mô tả những thông tin detector cần cung cấp để quyết định đó có căn cứ.

## 4. Thiết kế event đủ để tái dựng diễn biến

### 4.1. Phân biệt request, quyết định và tác động đã commit

Một dòng HTTP 200 không chứng minh password đã đổi. Nó có thể là phản hồi chung của API khởi tạo, kết quả idempotency được phát lại hoặc thông báo nhận yêu cầu.

Những event có ý nghĩa khác nhau cần có tên và outcome rõ ràng:

| Event minh họa | Ý nghĩa |
|---|---|
| RECOVERY_REQUEST_ACCEPTED | API đã tiếp nhận yêu cầu công khai |
| RECOVERY_EVIDENCE_REJECTED | Kiểm tra bằng chứng bị từ chối |
| RECOVERY_EVIDENCE_ACCEPTED | Bằng chứng đạt điều kiện đã xác định |
| RECOVERY_GRANT_ISSUED | Đã cấp quyền giới hạn theo scope |
| RECOVERY_CANCELLED_COMMITTED | Quyết định hủy đã có hiệu lực tại ranh giới được định nghĩa |
| CREDENTIAL_MUTATION_COMMITTED | Thay đổi credential đã được lưu bền vững |
| FACTOR_REPLACEMENT_COMMITTED | Thay đổi factor đã được lưu bền vững |
| SESSION_REVOCATION_REQUESTED | Đã yêu cầu thu hồi session |
| SESSION_REVOCATION_EFFECTIVE | Cơ chế thu hồi xác nhận mốc hiệu lực theo hợp đồng |
| PROTECTED_ACTION_AUTHORIZED | Một resource đã cho phép tác vụ được bảo vệ |
| RECOVERY_DISPUTED | Có người báo giao dịch không phải do họ thực hiện |

Không dùng event “yêu cầu thu hồi” làm bằng chứng mọi resource đã chặn session. Không dùng “provider đã nhận yêu cầu gửi mail” làm bằng chứng người dùng đã đọc mail.

### 4.2. Schema minh họa

~~~json
{
  "schemaVersion": 1,
  "eventId": "event-7d3",
  "eventType": "CREDENTIAL_MUTATION_COMMITTED",
  "occurredAt": "2030-01-01T10:03:00Z",
  "ingestedAt": "2030-01-01T10:03:02Z",
  "sourceService": "credential-service",
  "tenantRef": "tenant-a",
  "subjectAccountRef": "account-a",
  "actorRef": "recovery-principal-a",
  "recoveryTransactionRef": "recovery-a",
  "grantRef": "grant-a",
  "businessMutationRef": "mutation-a",
  "purpose": "PASSWORD_RESET",
  "outcome": "COMMITTED",
  "policyVersion": "recovery-policy-v3",
  "evidenceVersion": 12,
  "requestCorrelationRef": "correlation-a"
}
~~~

Đây là schema ví dụ cho dữ liệu sự kiện, không phải trường cần bổ sung vào YAML metadata của bài học.

Các reference phải được quản lý theo yêu cầu truy cập và lưu trữ dữ liệu của tổ chức. Một ID nội bộ vẫn có thể liên kết tới cá nhân; không mặc định dữ liệu đó đã ẩn danh.

Một số ngữ cảnh có ích như loại factor trước/sau, mức xác thực được xác minh hoặc nhóm rủi ro mạng có thể nằm ở bảng enrichment riêng. Không cần sao chép tất cả thông tin người dùng vào mọi event.

### 4.3. Những trường dễ bị hiểu sai

- subjectAccountRef là account bị tác động; actorRef là người hoặc dịch vụ thực hiện. Hai trường có thể khác nhau trong luồng hỗ trợ.
- eventId định danh bản ghi sự kiện; businessMutationRef định danh thay đổi nghiệp vụ. Một mutation có thể sinh nhiều event hoặc được gửi lại.
- occurredAt là thời điểm sự kiện theo nguồn; ingestedAt là lúc collector nhận. Không dùng hai trường này thay nhau một cách tùy tiện.
- requestCorrelationRef nối các bước của một request; recoveryTransactionRef nối nhiều request thuộc cùng hồ sơ.
- purpose và policyVersion phải phản ánh quyết định server, không lấy nguyên từ body client rồi coi là sự thật.

Ở bước trước xác thực, có thể chỉ biết target claim mà chưa có subject đã xác minh. Cần biểu diễn điều đó trong schema. Không gán một accountRef đã xác thực cho mọi email người gọi nhập.

### 4.4. Nguồn phát và tính nhất quán

Event về thay credential nên gắn với ranh giới commit hoặc cơ chế phát sự kiện nhất quán với commit, chẳng hạn một outbox trong cùng transaction nếu kiến trúc phù hợp.

Nếu event được ghi trước commit rồi transaction rollback, detector có thể báo một thay đổi chưa từng có. Nếu commit xong nhưng tiến trình chết trước khi phát event mà không có cơ chế phục hồi, detector có thể bỏ sót thay đổi.

Outbox giúp giữ quan hệ giữa dữ liệu và event, nhưng không tự loại bỏ redelivery. Detector vẫn phải biết định danh event và định danh tác động nghiệp vụ để xử lý trùng đúng mức.

## 5. Dữ liệu phát hiện phải đáng tin mà không trở thành nơi lộ secret

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) nhấn mạnh giá trị của log ứng dụng, ngữ cảnh sự kiện và việc tránh ghi trực tiếp secret. Đối với recovery, chọn các reference và kết quả xác minh phục vụ tương quan thay vì lưu nguyên credential.

Không ghi vào log giám sát thông thường:

- Password mới hoặc cũ.
- Token recovery thô và toàn bộ URL chứa token.
- Recovery code, seed TOTP hoặc private key.
- Cookie hay access/refresh token có thể dùng trực tiếp.
- Ảnh, giấy tờ và toàn bộ nội dung hồ sơ xác minh danh tính.

Để nhận biết cùng một grant, dùng grantRef do server cấp nếu có thể. Nếu cần một fingerprint, thiết kế cách tạo và phạm vi sử dụng theo mô hình dữ liệu; không tùy tiện hash email rồi coi là ẩn danh, vì không gian email có thể bị dò đoán.

### 5.1. Ngữ cảnh thiết bị và mạng là tín hiệu, không phải danh tính

IP có thể thay đổi do mạng di động, VPN hoặc proxy. Nhiều người có thể dùng chung IP sau NAT. User-Agent và một số device ID có thể do client tự khai hoặc bị sao chép.

Detector cần ghi được nguồn và độ tin cậy của dữ kiện, ví dụ “device continuity được xác nhận bằng credential đã đăng ký” khác với “cookie nhận diện trình duyệt không còn”.

Đừng nối hai account chỉ vì cùng IP rồi coi chúng thuộc một người. Có thể dùng IP làm một chiều tổng hợp chống abuse, nhưng kết luận chiếm dụng cần bằng chứng khác.

### 5.2. Bảo vệ pipeline

Giới hạn quyền ghi và đọc event, kiểm tra schema, xác thực nguồn gửi và xử lý dữ liệu không tin cậy trước khi hiển thị trong công cụ điều tra. Nội dung do người dùng nhập có thể chứa ký tự điều khiển hoặc chuỗi làm sai giao diện log.

Theo dõi cả việc dừng collector, schema bị từ chối và tăng độ trễ gửi event. Không có cảnh báo khi nguồn dữ liệu đã mất không phải là bằng chứng hệ thống an toàn.

Nếu một sự cố có thể làm actor sửa được cả dữ liệu account và log ứng dụng, cần nguồn đối chiếu độc lập thích hợp như audit của tầng credential hoặc hạ tầng kiểm soát truy cập. Không coi cùng một chuỗi log do cùng thành phần phát là hai bằng chứng độc lập.

## 6. Danh mục tín hiệu theo giai đoạn

| Tín hiệu | Điều đáng chú ý | Cần kiểm tra thêm |
|---|---|---|
| Một nguồn khởi tạo cho nhiều account | Có thể là thăm dò hoặc recovery spraying | NAT, công cụ hỗ trợ, lưu lượng chiến dịch hợp lệ |
| Một account nhận nhiều yêu cầu từ nhiều nguồn | Có thể bị quấy rối hoặc bị nhắm có chủ đích | Client retry, sự cố delivery, phản hồi chủ tài khoản |
| Nhiều lần xác minh sai rồi một lần đúng | Có thể có dò đoán hoặc bằng chứng bị lộ | Định danh từng lần thử, cùng transaction hay khác hồ sơ |
| Bằng chứng được dùng trong ngữ cảnh khác lúc cấp | Có thể chuyển giao token hoặc chiếm kênh | Người dùng đổi thiết bị, email scanner, nguồn context đáng tin |
| Địa chỉ recovery mới được dùng ngay cho recovery | Có thể tự tạo đường chiếm quyền | Điều kiện xác minh trước đó và bằng chứng độc lập |
| Thay factor rồi xóa factor cũ | Có thể là giữ quyền và loại chủ tài khoản | Quy trình thay thiết bị hợp lệ và loại factor bị xóa |
| Recovery xong rồi tạo API key hoặc tác vụ nhạy cảm | Có thể sử dụng tài khoản vừa chiếm | Quyền ban đầu, xác thực bổ sung và ngữ cảnh nghiệp vụ |
| Chủ tài khoản phản đối giao dịch | Có thể là recovery trái phép | Xác minh người phản đối qua một kênh còn đáng tin |
| Grant sai purpose vẫn tạo credential | Có thể vi phạm authorization | Hợp đồng purpose và dữ liệu commit thật |
| Grant đã kết thúc vẫn có tác động mới | Có thể replay, race hoặc kiểm tra state bị bỏ | Thứ tự commit, idempotency và clock |
| Một nhân viên phê duyệt khác thường | Có thể lạm quyền hoặc session hỗ trợ bị chiếm | Quyền được cấp, ca trực, tenant, chiến dịch hỗ trợ |
| Session bị thu hồi vẫn dùng được sau deadline | Có thể còn đường duy trì quyền | Cơ chế thực thi của resource và mốc hiệu lực revocation |

Tín hiệu có thể làm tăng ưu tiên điều tra mà chưa đủ để kết luận compromise. Ví dụ, thay factor và xóa factor cũ cũng là việc bình thường khi người dùng đổi điện thoại. Cần xét bằng chứng cho phép thay, actor, lịch sử liên quan và các tác vụ tiếp theo.

Không đặt ngưỡng chỉ từ trực giác như “ba lần sai là tấn công”. Chọn ngưỡng theo phân bố hoạt động, ngân sách thử của policy, chi phí bỏ sót và chi phí gây gián đoạn. Các lớp account hoặc tenant có thể cần cách hiệu chỉnh khác nhau.

## 7. Phân biệt luật bất biến và luật hành vi

### 7.1. Luật bất biến

Luật bất biến kiểm tra điều hệ thống không được phép làm theo hợp đồng cụ thể. Ví dụ:

- Grant chỉ cấp một mutation nhưng tạo hai mutation độc lập.
- Token thuộc tenant T1 thay credential ở tenant T2.
- PASSWORD_RESET bị chấp nhận cho hành động chỉ được cấp bởi FACTOR_REBIND.
- Một quyết định hủy có hiệu lực trước điểm commit nhưng tác động vẫn được chấp nhận sau đó.
- Session tiếp tục truy cập tài nguyên ngoài deadline thu hồi đã cam kết.

Khi nguồn dữ liệu và hợp đồng đã được xác minh, đây là bằng chứng mạnh về lỗi kiểm soát. Tuy nhiên, vẫn cần phân biệt tác động do tấn công với lỗi triển khai hoặc dữ liệu giám sát sai.

Một event tự khai “purpose mismatch” từ client không phải bằng chứng như event từ thành phần authorization đã xác minh purpose và grant. Độ tin cậy của nguồn là một phần của điều kiện luật.

### 7.2. Luật hành vi

Luật hành vi tìm chuỗi có xác suất rủi ro cao hơn baseline, ví dụ:

~~~text
Thay địa chỉ recovery
  -> Hoàn tất recovery sau đó không lâu
  -> Đăng ký factor mới
  -> Xóa factor trước đó
  -> Thực hiện tác vụ nhạy cảm từ phiên liên quan
~~~

Một người dùng có thể thực hiện chuỗi tương tự hợp lệ. Vì vậy, luật cần xuất ra bằng chứng, khoảng thời gian, điều kiện còn thiếu và lý do ưu tiên, thay vì gắn nhãn chắc chắn “attacker”.

Ngữ cảnh mạng, thiết bị hoặc hành vi nên bổ sung cho chuỗi nghiệp vụ. Nếu chỉ dựa vào IP, người dùng đổi mạng có thể bị cảnh báo còn người dùng session bị đánh cắp trên cùng proxy lại không bị phát hiện.

### 7.3. Không cộng điểm những tín hiệu phụ thuộc nhau như độc lập

“IP mới”, “ASN mới” và “quốc gia mới” có thể đều bắt nguồn từ cùng một kết nối VPN. Cộng ba điểm cao độc lập có thể phóng đại độ tin cậy.

Một thiết kế đơn giản có thể gom tín hiệu theo nhóm:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| Tính đúng đắn của quyền | Sai scope, sai purpose, grant kết thúc | Đối chiếu bất biến |
| Thay đổi quyền kiểm soát | Recovery address, factor, session | Xác định tác động |
| Ngữ cảnh truy cập | Thiết bị, mạng, continuity | Bổ sung mức nghi ngờ |
| Xác nhận độc lập | Phản đối đã xác minh, bằng chứng điều tra | Tăng hoặc giảm độ tin cậy |
| Chất lượng dữ liệu | Nguồn thiếu, clock lệch, event đến muộn | Giới hạn kết luận |

Cách gom nhóm phải được giải thích và hiệu chỉnh bằng dữ liệu. Một risk score tự đặt không phải xác suất compromise và không nên được trình bày như “90% tài khoản đã bị chiếm” nếu chưa có hiệu chuẩn phù hợp.

## 8. Tương quan đúng account, giao dịch và thời gian

### 8.1. Chọn khóa theo câu hỏi

- Theo tenant + account để tìm diễn biến thay đổi quyền kiểm soát.
- Theo recoveryTransactionRef để nối bằng chứng, grant và kết quả.
- Theo grantRef để kiểm tra scope và số tác động được cấp.
- Theo session reference để nối recovery với hành động sau đăng nhập.
- Theo actor hỗ trợ để phát hiện hành vi phê duyệt khác thường.
- Theo nguồn truy cập để phát hiện chiến dịch nhắm nhiều account.

Không dùng transactionRef làm khóa duy nhất nếu ID chỉ duy nhất trong tenant. Không nối mọi sự kiện của cùng IP thành một hồ sơ người dùng. Khi không có liên kết session đáng tin, phải ghi rõ hành động sau recovery chỉ liên quan theo account và thời gian, chưa chứng minh cùng actor.

### 8.2. Event time và ingestion time

Một event commit lúc 10:03 có thể tới collector lúc 10:07, sau event đăng nhập lúc 10:05. Sắp xếp theo ingestedAt sẽ làm sai diễn biến nghiệp vụ.

Đối với dữ liệu phân tán:

- Dùng thời gian nguồn đã được kiểm soát để đặt cửa sổ sự kiện.
- Giữ thời gian nhận để đo độ trễ và nhận biết dữ liệu muộn.
- Dùng sequence hoặc version do authority phát hành khi cần xác định thứ tự commit.
- Cho phép cập nhật một finding khi bằng chứng đến sau.
- Ghi rõ khi clock không đủ tin cậy để kết luận thứ tự.

Một cách phân tích hợp lệ là “có hai mutation dùng cùng grant” mà không cần biết mutation nào trước. Ngược lại, kết luận “commit sau khi hủy có hiệu lực” thường cần dữ liệu thứ tự mạnh hơn so với hai timestamp từ hai máy.

### 8.3. Dữ liệu đến muộn không được xóa lịch sử nhận định

Giả sử luật ban đầu báo “không thấy phê duyệt trước khi thay factor”. Sau đó event phê duyệt đến muộn và authority xác nhận nó đã có hiệu lực trước thay đổi.

Finding nên được bổ sung hoặc điều chỉnh trạng thái với lý do và bằng chứng mới. Không sửa âm thầm báo cáo cũ khiến người xử lý không biết điều gì thay đổi.

Một nhãn như DATA_INCOMPLETE có ích hơn “không có phê duyệt” khi collector đang chậm. Thiếu event trong một cửa sổ chưa đóng không đồng nghĩa bước đó chưa từng xảy ra.

### 8.4. Chống đếm trùng ở đúng tầng

Có ba khái niệm khác nhau:

1. Cùng eventId được giao lại: duplicate transport.
2. Hai eventId khác nhau mô tả cùng businessMutationRef: duplicate representation hoặc nhiều nguồn cho cùng tác động.
3. Hai businessMutationRef độc lập dùng cùng một grant chỉ được phép một lần: ứng viên vi phạm bất biến.

Nếu chỉ COUNT(*) trên event stream, trường hợp 1 và 2 có thể tạo cảnh báo giả. Nếu chỉ deduplicate theo account và thời gian, trường hợp 3 có thể bị gộp mất.

## 9. Ví dụ luật phát hiện: một grant tạo nhiều mutation

Giả sử policy quy định một grant cụ thể chỉ được tạo một credential mutation. Luật cần đếm tác động đã commit độc lập, không đếm response hoặc số lần broker gửi event.

Một truy vấn minh họa trên view quan sát đã được chuẩn hóa:

~~~sql
SELECT
    e.tenant_ref,
    e.grant_ref,
    COUNT(DISTINCT e.business_mutation_ref) AS mutation_count
FROM credential_commit_events e
JOIN grant_policy_snapshot p
  ON p.tenant_ref = e.tenant_ref
 AND p.grant_ref = e.grant_ref
WHERE e.outcome = 'COMMITTED'
  AND p.max_credential_mutations = 1
  AND e.business_mutation_ref IS NOT NULL
  AND e.occurred_at >= :window_start
  AND e.occurred_at < :window_end
GROUP BY e.tenant_ref, e.grant_ref
HAVING COUNT(DISTINCT e.business_mutation_ref) > 1;
~~~

Tên view và bảng là giả định. grant_policy_snapshot cần duy nhất theo tenant + grant và phản ánh hợp đồng của grant, không lấy giá trị một lần từ suy đoán của detector.

Cửa sổ truy vấn phải bao phủ những mutation có thể thuộc cùng vòng đời grant, có xử lý dữ liệu muộn. Nếu chạy các cửa sổ rời nhau mà không giữ trạng thái, mutation đầu ở cuối cửa sổ trước và mutation thứ hai ở đầu cửa sổ sau có thể bị bỏ sót.

Một kết quả cần được đối chiếu với authority của credential: hai businessMutationRef có thực sự là hai tác động hay chỉ là lỗi cấp ID khi phát lại event? Sau khi xác nhận, finding có thể chỉ ra chính xác grant, account bị tác động và hai mutation.

### 9.1. Ví dụ Java cho phần gom tác động độc lập

Đoạn mã dùng Java 17 trở lên và thư viện chuẩn. Đầu vào là một tập hữu hạn các event đã được kiểm tra nguồn, xác nhận commit và làm giàu rằng grant chỉ cho phép một mutation. Đây là phần xử lý batch minh họa, không phải một stream processor hoàn chỉnh.

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class DuplicateRecoveryMutationDetector {

    public record GrantKey(String tenantRef, String grantRef) {
        public GrantKey {
            requireText(tenantRef, "tenantRef");
            requireText(grantRef, "grantRef");
        }
    }

    public record CommittedMutation(
            GrantKey grant,
            String businessMutationRef) {
        public CommittedMutation {
            if (grant == null) {
                throw new IllegalArgumentException("grant is required");
            }
            requireText(businessMutationRef, "businessMutationRef");
        }
    }

    public record Finding(
            GrantKey grant,
            Set<String> mutationRefs) {
    }

    public static List<Finding> detect(
            List<CommittedMutation> committedMutations) {

        Map<GrantKey, Set<String>> mutationsByGrant = new HashMap<>();

        for (CommittedMutation mutation : committedMutations) {
            if (mutation == null) {
                throw new IllegalArgumentException(
                        "null mutation must be quarantined");
            }

            mutationsByGrant
                    .computeIfAbsent(
                            mutation.grant(), ignored -> new HashSet<>())
                    .add(mutation.businessMutationRef());
        }

        return mutationsByGrant.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .map(entry -> new Finding(
                        entry.getKey(),
                        Set.copyOf(entry.getValue())))
                .toList();
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " is required");
        }
    }
}
~~~

Với dữ liệu:

~~~text
tenant-a, grant-a, mutation-1
tenant-a, grant-a, mutation-1
tenant-a, grant-a, mutation-2
tenant-b, grant-a, mutation-3
~~~

Detector tạo một finding cho tenant-a/grant-a với mutation-1 và mutation-2. Bản sao mutation-1 không được tính thành tác động thứ hai; tenant-b/grant-a là một scope riêng trong mô hình ID này.

Trong hệ thống thật, cần thêm điều kiện vòng đời, policy, account binding, quản lý trạng thái, dữ liệu muộn, hạn mức bộ nhớ và deduplication của finding. Nếu không biết cardinality của grant, không đưa event vào luật một lần rồi tự kết luận vi phạm.

Đoạn mã không kiểm tra token, không phát hiện mọi dạng chiếm tài khoản và không thực hiện containment. Nó chỉ minh họa một phép đếm có thể giải thích được.

## 10. Ví dụ luật hành vi: thay đường recovery rồi đổi factor

Một luật hành vi có thể quan tâm chuỗi sau trên cùng tenant + account:

~~~text
A: RECOVERY_CHANNEL_CHANGED_COMMITTED
B: RECOVERY_COMPLETED_COMMITTED
C: FACTOR_REPLACEMENT_COMMITTED
D: SENSITIVE_ACTION_AUTHORIZED

Điều kiện minh họa:
  A xảy ra trước B trong một cửa sổ được policy cấu hình.
  B liên quan đến địa chỉ hoặc bằng chứng vừa thay ở A.
  C có liên kết giao dịch hoặc session đáng tin với B.
  D có liên kết phiên với kết quả của B/C, nếu dữ liệu cho phép.
~~~

Nếu sản phẩm chưa có RECOVERY_COMPLETED_COMMITTED, có thể suy kết quả từ các mutation và trạng thái authority, nhưng phải mô tả rõ cách suy. Không tạo event “đã hoàn tất” chỉ từ một HTTP status.

Cần giữ cả trường hợp C xảy ra ở một giao dịch liên quan khác. Nếu ép mọi event có cùng transactionRef, detector có thể bỏ sót người thay email trong một request rồi mở recovery ở request khác.

### 10.1. Khi nào ưu tiên cao hơn?

Ưu tiên tăng nếu có thêm một hoặc nhiều dữ kiện độc lập:

- Kênh mới được thay bằng một phiên đang bị nghi ngờ hoặc đã bị xác định bị chiếm.
- Actor hỗ trợ không có quyền phù hợp nhưng đã tạo quyết định có hiệu lực.
- Factor bị xóa là phương thức an toàn cuối cùng của chủ tài khoản theo dữ liệu đã xác minh.
- Có phản đối từ chủ tài khoản được xác minh qua kênh độc lập còn tin cậy.
- Sau recovery xuất hiện hành động nhạy cảm không phù hợp với quyền hoặc điều kiện step-up.
- Một bất biến scope, purpose hoặc vòng đời bị vi phạm trong chính chuỗi đó.

Không khẳng định độc lập chỉ vì dữ liệu đến từ hai bảng. Hai bảng có thể được điền từ cùng một request client chưa xác minh.

### 10.2. Khi nào có giải thích hợp lệ?

Người dùng đổi email sau khi đổi công ty, mất điện thoại, khôi phục rồi đăng ký thiết bị mới có thể tạo chuỗi tương tự. Nhân viên hỗ trợ cũng có thể đang thực hiện một chiến dịch chuyển đổi đã được phê duyệt.

Các giải thích đó cần bằng chứng và phạm vi, không chỉ một allowlist vô thời hạn. Một chiến dịch hợp lệ có thể giúp điều chỉnh ưu tiên nhưng không được che một vi phạm rõ ràng như dùng sai tenant hoặc grant đã hủy vẫn có hiệu lực.

### 10.3. Finding phải nói được giới hạn

Một mô tả phù hợp:

~~~text
Phát hiện:
  Account A trong tenant T1 đã đổi kênh recovery,
  hoàn tất recovery và thay factor trong cùng chuỗi quan sát.

Bằng chứng:
  Ba mutation đã commit, liên kết grant và transaction.
  Phiên thực hiện sau recovery chưa có continuity đáng tin cậy.

Chưa biết:
  Người thực hiện có phải chủ tài khoản hay không.
  Kênh email cũ còn an toàn để liên hệ hay không.

Đề nghị triage:
  Đối chiếu bằng chứng cho phép thay kênh và thay factor,
  kiểm tra phiên liên quan và xác minh phản hồi của chủ tài khoản.
~~~

Mô tả này hữu ích hơn một nhãn “high risk” không có điều kiện, vì người điều tra biết dữ kiện nào đã có và việc kiểm tra tiếp theo sẽ giải quyết điều gì.

## 11. Tình huống xuyên suốt: một chuỗi nghi ngờ chiếm quyền

Các mốc dưới đây là dữ liệu giả lập theo UTC, không phải sự cố thật:

| Thời điểm | Dữ kiện đã quan sát | Nhận định lúc đó |
|---|---|---|
| 10:00 | Địa chỉ recovery của A được thay bởi một session hiện có | Thay đổi quyền kiểm soát cần theo dõi |
| 10:04 | Bằng chứng từ kênh vừa thêm được chấp nhận cho một hồ sơ mới | Cần kiểm tra kênh mới có được dùng cho nhánh này theo policy không |
| 10:06 | Password mutation đã commit | Recovery có tác động thật, chưa biết actor có hợp lệ không |
| 10:08 | Factor mới được đăng ký và một factor cũ bị xóa | Mức tác động tăng; có khả năng thay đường kiểm soát |
| 10:09 | Phiên sau recovery tạo một API key | Cần xét quyền và liên kết phiên |
| 10:12 | Có phản đối được xác minh bằng một credential độc lập còn đáng tin | Tăng độ tin cậy về recovery trái phép, mở điều tra theo policy |

Tại 10:09, detector có thể tạo một finding hành vi với mức ưu tiên phù hợp. Nó không cần chờ một chuỗi thất bại hay lưu lượng lớn mới phát hiện.

Tại 10:12, phản đối đã được xác minh cung cấp bằng chứng mới. Nhóm điều tra vẫn cần xác định session nào đổi kênh, bằng chứng nào cho phép thay factor, API key có thuộc cùng actor và quyền nào còn tồn tại.

Nếu event 10:00 đến collector lúc 10:11, finding có thể được bổ sung khi event đó tới. Hệ thống cần giữ sự khác biệt giữa “không thấy thay đổi kênh trước đó” và “đã xác minh không có thay đổi kênh”.

### 11.1. Điều gì không được suy ra?

Không suy ra địa chỉ recovery cũ chắc chắn còn an toàn. Nó có thể đã bị thay vì bị chiếm hoặc mất quyền truy cập. Không suy ra mọi credential mới đều độc hại nếu chưa kiểm tra quá trình cấp quyền.

Không suy ra API key đã được sử dụng để lấy dữ liệu chỉ vì nó được tạo. Muốn đánh giá tác động đó, cần event sử dụng key và tài nguyên đã được truy cập.

Không suy ra reset thêm một lần password là đủ loại bỏ quyền còn lại. Cần kiểm tra session, factor, recovery grant và các credential liên quan theo phạm vi điều tra.

## 12. Triage: từ finding tới giả thuyết có thể kiểm chứng

### 12.1. Năm câu hỏi đầu tiên

1. Có thay đổi nào thực sự đã commit, hay mới chỉ có request?
2. Bằng chứng và policy nào đã cho phép thay đổi đó?
3. Actor, account, tenant, transaction và grant có khớp không?
4. Quyền mới đã được sử dụng ở đâu, và quyền cũ còn hoạt động không?
5. Dữ liệu nào còn thiếu hoặc chưa đủ tin cậy để kết luận?

Triage nên bắt đầu từ mutation hoặc quyết định cấp quyền đáng tin cậy, rồi lần ngược tới bằng chứng và lần xuôi tới session. Chỉ bắt đầu từ một IP có thể dẫn tới gộp nhầm nhiều người và bỏ sót chuỗi đổi nguồn.

### 12.2. Tách tác động, độ tin cậy và phạm vi

Ba chiều này không đồng nghĩa:

- Tác động: thay password, thay factor, tạo credential lâu dài hoặc sử dụng quyền nhạy cảm.
- Độ tin cậy: nguồn dữ liệu, bất biến được xác nhận, bằng chứng độc lập, phản hồi đã được xác minh.
- Phạm vi: một giao dịch, một account, một tenant hay nhiều account dùng chung thành phần lỗi.

Một sự kiện có thể tác động lớn nhưng độ tin cậy còn thấp. Một vi phạm bất biến được xác nhận có thể chưa thấy account nào bị sử dụng trái phép, nhưng vẫn cần ưu tiên vì nó chỉ ra đường kiểm soát bị phá.

Nếu nhiều finding trỏ tới cùng phiên bản service, provider hoặc policy mới triển khai, hãy kiểm tra khả năng sự cố hệ thống thay vì tạo hàng nghìn hồ sơ riêng lẻ không liên kết. Giữ được cả tổng hợp theo sự cố và bằng chứng theo từng account.

### 12.3. Hồ sơ bàn giao tối thiểu

~~~yaml
findingId: recovery-finding-example
rule:
  id: RECOVERY_CONTROL_CHANGE_CHAIN
  version: 3
scope:
  tenantRef: synthetic-tenant-a
  accountRef: synthetic-account-a
classification:
  suspectedCause: UNKNOWN
  confidence: NEEDS_CORROBORATION
  impact: CREDENTIAL_AND_FACTOR_CONTROL_CHANGED
evidence:
  - channel-change-mutation-reference
  - password-mutation-reference
  - factor-mutation-reference
  - linked-session-reference
unknowns:
  - whether-original-session-was-compromised
  - whether-established-contact-channel-remains-safe
dataQuality:
  sourceCoverage: PARTIAL
  lateEventsPossible: true
nextChecks:
  - verify-policy-and-evidence-binding
  - inspect-linked-session-and-api-key-activity
  - validate-user-dispute-through-independent-evidence
~~~

Đây là mẫu hồ sơ phát hiện. Trong hệ thống thật, các giá trị classification nên thuộc taxonomy được nhóm vận hành thống nhất. Không dùng cùng một trường severity để vừa biểu diễn mức nguy hại vừa biểu diễn sự chắc chắn.

### 12.4. Bàn giao cho containment mà không làm mất bằng chứng

Detector nên chỉ ra các grant, credential và session có liên quan cùng độ tin cậy của từng liên kết. Chính sách phản ứng quyết định hành động nào được tự động hóa và hành động nào cần người xử lý.

Những hành động có thể được xem xét trong một playbook đã phê duyệt gồm hạn chế riêng giao dịch nghi ngờ, yêu cầu bằng chứng bổ sung, thu hồi quyền liên quan hoặc xác minh lại chủ tài khoản. Không khóa toàn bộ account chỉ vì người ngoài gửi nhiều request reset; chính tín hiệu dễ tạo đó có thể bị dùng để gây từ chối dịch vụ.

Trước và sau một hành động, giữ reference tới dữ liệu bền vững và kết quả thực thi phù hợp. Ví dụ, “đã yêu cầu revoke” khác với “resource đã chặn session liên quan”. Việc xử lý cũng nên tạo event để quá trình phát hiện có thể theo dõi hiệu quả và những quyền còn sót.

[NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) đặt hoạt động ứng phó sự cố trong quản lý rủi ro an ninh mạng, với mục tiêu cải thiện phát hiện, phản ứng và phục hồi. Các mẫu finding và bước triage trong bài là đề xuất thiết kế cho recovery, không phải biểu mẫu bắt buộc của tài liệu NIST.

## 13. Đo chất lượng phát hiện

### 13.1. Đo thời gian ở đúng điểm

Có thể tách các khoảng thời gian:

~~~text
Độ trễ nguồn:
  ingestedAt - occurredAt

Độ trễ xử lý:
  findingCreatedAt - thời điểm đã nhận đủ bằng chứng cần thiết

Độ trễ phản hồi:
  triageStartedAt - findingCreatedAt

Độ trễ có hiệu lực:
  containmentEffectiveAt - containmentRequestedAt
~~~

Các phép trừ liên quan clock khác nguồn chỉ có ý nghĩa khi biết độ lệch và chất lượng đồng bộ. Nếu chưa biết thời điểm compromise thực sự bắt đầu, không đặt nhãn “thời gian phát hiện từ lúc bị chiếm” cho một con số chỉ đo từ event đầu tiên mà detector nhìn thấy.

Dùng phân bố theo nhóm sự cố, không chỉ giá trị trung bình. Một số event đến rất muộn có thể là phần nguy hiểm nhất nhưng bị trung bình che khuất.

### 13.2. Precision và recall cần mẫu chuẩn phù hợp

Precision trên các finding đã phân loại có thể được mô tả:

~~~text
Số finding được xác nhận đúng trong tập đã đánh giá
--------------------------------------------------
Tổng số finding đã được đánh giá trong tập đó
~~~

Cần định nghĩa “đúng” là abuse, vi phạm bất biến hay compromise đã xác minh. Một finding đúng về vi phạm policy chưa chắc là một vụ chiếm tài khoản.

Mẫu chỉ gồm finding người điều tra chọn xem có thể bị thiên lệch. Các finding chưa có kết luận phải được báo riêng; không coi chúng là đúng hoặc sai chỉ để làm đẹp tỷ lệ.

Recall cần biết những tình huống đáng lẽ phải được phát hiện. Với hệ thống thật, nhiều sự cố có thể chưa được biết đến, nên recall toàn cục thường không đo được trực tiếp. Có thể đo trên tập scenario giả lập đã gắn nhãn và trên những sự cố đã xác nhận, đồng thời nêu rõ giới hạn của tập đó.

### 13.3. Coverage và chất lượng dữ liệu

Các chỉ số hữu ích khác:

| Chỉ số | Giúp trả lời |
|---|---|
| Tỷ lệ mutation có event tương ứng theo nguồn authority | Có bỏ sót tác động đã commit không? |
| Tỷ lệ event thiếu tenant/account/transaction cần thiết | Luật có tương quan được đúng scope không? |
| Collector lag và số event bị từ chối schema | Có điểm mù hoặc thay đổi schema không? |
| Số finding trùng trên cùng mutation hoặc sự cố | Người xử lý có bị ngập cảnh báo không? |
| Tỷ lệ case có đủ bằng chứng để kết luận | Event có hữu ích cho điều tra không? |
| Số phản ứng gây gián đoạn cho recovery hợp lệ | Cách dùng detector có gây mất quyền truy cập không? |
| Tỷ lệ scenario đã gắn nhãn được phát hiện | Các đường đe dọa được mô hình hóa có coverage ra sao? |

Một lượng cảnh báo giảm mạnh có thể do luật tốt hơn, nhưng cũng có thể do nguồn event đã dừng. Luôn xem chỉ số phát hiện cùng chất lượng và độ bao phủ dữ liệu.

## 14. Kiểm chứng detector bằng các kịch bản có đối chứng

### 14.1. Ma trận dữ liệu giả lập

| Scenario | Đầu vào quan trọng | Kết quả mong đợi |
|---|---|---|
| Người dùng đổi điện thoại hợp lệ | Bằng chứng độc lập đạt policy, factor thay đúng scope | Không kết luận compromise; có thể vẫn có event và nhận định phù hợp |
| Gửi nhiều request nhưng không có mutation | Request dày, bằng chứng không được chấp nhận | Phân loại abuse, không báo recovery đã thành công |
| Broker giao cùng event nhiều lần | Cùng mutationRef | Không tăng số tác động độc lập |
| Hai eventId khác nhau cho cùng mutation | Event hợp lệ cùng businessMutationRef | Không báo hai mutation |
| Một grant một lần tạo hai mutation | Hai mutationRef độc lập đã commit | Finding vi phạm sau khi đối chiếu cardinality |
| Mutation ở cuối và đầu hai cửa sổ liên tiếp | Cùng grant, dữ liệu sát ranh giới | Không bỏ sót vì chia cửa sổ |
| Phê duyệt đến collector muộn | Thứ tự authority chứng minh phê duyệt hợp lệ trước commit | Không kết luận bỏ bước chỉ từ thứ tự nhận |
| Grant sai tenant vẫn có mutation | Binding authority không khớp target | Finding scope mismatch với bằng chứng rõ |
| Chuỗi thay kênh–recovery–factor | Các thay đổi liên kết, chưa có xác nhận chủ tài khoản | Finding nghi ngờ, không tự gắn nhãn đã xác minh |
| Có phản đối được xác minh độc lập | Phản đối liên kết giao dịch đáng ngờ | Cập nhật mức tin cậy và hồ sơ triage |
| Một nguồn event bị ngắt | Thiếu telemetry có bằng chứng từ monitor | Cảnh báo độ bao phủ; không báo “không có sự cố” |
| Account cùng ID ở hai tenant | Event thuộc hai scope khác nhau | Không gộp thành một account hoặc grant |

Với luật có phản ứng tự động, cần test riêng quyết định policy và hiệu lực hành động. Detector tìm được finding không chứng minh session đã bị thu hồi hoặc credential nghi ngờ đã bị vô hiệu.

### 14.2. Shadow mode và replay lịch sử

Trước khi dùng luật mới để kích hoạt phản ứng, có thể chạy ở chế độ chỉ tạo finding trên dữ liệu đã được phép sử dụng. So sánh với hồ sơ điều tra, scenario giả lập và hành vi recovery hợp lệ.

Replay dữ liệu lịch sử cần giữ thông tin policy có hiệu lực lúc đó. Nếu dùng policy hiện tại để phán xét mọi grant cũ, detector có thể tạo các vi phạm giả.

Cũng cần phân biệt event-time replay với việc nhận lại event cũ trong production. Một finding được tính lại không được vô tình kích hoạt lại hành động containment của một sự cố đã đóng.

### 14.3. Kiểm tra parser, deduplication và đường hiển thị

Ngoài logic luật, tạo case cho:

- Event thiếu trường bắt buộc hoặc schema version chưa hỗ trợ.
- Reference rỗng, tenant không hợp lệ và nguồn không được xác minh.
- Event rất muộn, timestamp nằm ngoài phạm vi cho phép hoặc clock lệch.
- Nội dung do client nhập có ký tự điều khiển.
- Cùng finding được tính lại sau khi worker restart.
- Actor hỗ trợ hoặc dịch vụ được xem là “tin cậy” nhưng tạo thao tác ngoài quyền.

Dữ liệu lỗi cần có đường quarantine hoặc trạng thái chất lượng rõ ràng; không âm thầm bỏ qua rồi báo detector hoạt động đầy đủ. Cơ chế này cũng cần giới hạn tài nguyên để dữ liệu lỗi không làm tê liệt pipeline.

### 14.4. Mutation kiểm thử cho luật

Một cách kiểm tra độ nhạy là sửa dữ liệu giả lập có chủ đích:

- Bỏ tenant khỏi khóa gom nhóm để xem test có bắt gộp nhầm không.
- Đổi COUNT DISTINCT mutation thành COUNT event để xem duplicate có tạo cảnh báo giả không.
- Bỏ policy cardinality để xem grant nhiều tác động hợp lệ bị báo sai không.
- Chỉ nhìn cửa sổ hiện tại để xem case sát ranh giới có bị bỏ sót không.
- Xóa nhãn dữ liệu thiếu để xem hệ thống có kết luận quá mức không.

Những thay đổi này chỉ phục vụ kiểm thử trong môi trường kiểm soát. Chúng giúp chứng minh suite bảo vệ đúng những giả định quan trọng của detector.

## 15. Những lỗi thiết kế cần tránh

### 15.1. Chỉ phát hiện thất bại

Người có bằng chứng bị lộ có thể thành công ngay lần đầu. Cần quan sát mutation, factor, kênh recovery và session sau thành công, thay vì chỉ đếm code sai.

### 15.2. Đồng nhất HTTP success với nghiệp vụ success

API khởi tạo có thể trả phản hồi công khai giống nhau cho account có và không có. Chỉ event authority hoặc trạng thái bền vững mới cho biết có grant hoặc mutation thực sự.

### 15.3. Coi ngữ cảnh lạ là kết luận

Người mất thiết bị thường dùng thiết bị mới, mạng mới và có thể đang ở nơi khác. Đây chính là những người mà recovery cần phục vụ. Ngữ cảnh lạ chỉ là một phần của lập luận.

### 15.4. Coi không có log là không có hành động

Thiếu log có thể do pipeline, sampling, schema lỗi hoặc nguồn chưa instrument. Một kết luận về việc bước bắt buộc bị bỏ qua cần nguồn dữ liệu và điều kiện đầy đủ.

Đối với event bảo mật trọng yếu, chiến lược sampling phải phù hợp mục tiêu phát hiện. Nếu mutation chỉ được lấy mẫu một phần, không thể dùng số event nhận được làm tổng tác động chắc chắn.

### 15.5. Cho phép ngoại lệ che mọi vi phạm

Một allowlist cho IP công ty hoặc tài khoản hỗ trợ không nên loại bỏ kiểm tra scope, purpose và cardinality. Session nội bộ cũng có thể bị chiếm hoặc bị dùng sai.

### 15.6. Dùng cảnh báo để tự động tạo thêm recovery

Không gửi hàng loạt liên kết reset mới chỉ vì có một tín hiệu dễ kích hoạt. Điều đó có thể làm người dùng bị quấy rối, tăng số quyền đang lưu hành hoặc làm khó điều tra. Phản ứng cần phù hợp chính sách và dựa trên bằng chứng đủ mạnh cho hành động đã chọn.

## 16. Bài tập vận dụng

### Bài tập 1: Hai event hay hai thay đổi?

Collector nhận ba eventId khác nhau với cùng tenant, grant và businessMutationRef. Luật hiện tại cảnh báo grant được dùng ba lần.

Hãy xác định thông tin còn thiếu và sửa oracle.

Gợi ý đáp án: eventId khác nhau chưa chứng minh ba tác động. Cần đối chiếu businessMutationRef với authority, kiểm tra cardinality của grant và đếm mutation độc lập. Transport retry hoặc nhiều biểu diễn cùng một mutation không được tính thành lần tiêu thụ mới.

### Bài tập 2: Phê duyệt đến muộn

Event thay factor tới lúc 11:00, event phê duyệt tới lúc 11:03. Timestamp và version từ authority chứng minh phê duyệt có hiệu lực trước thay factor.

Luật “không thấy phê duyệt khi nhận event thay factor” nên kết luận thế nào?

Gợi ý đáp án: ở thời điểm dữ liệu thiếu, tạo nhận định có giới hạn hoặc chờ theo chính sách dữ liệu muộn; khi bằng chứng tới, cập nhật finding với lý do. Không dùng ingestion order để khẳng định đã bỏ bước phê duyệt.

### Bài tập 3: Mạng mới sau khi mất điện thoại

Người dùng mất điện thoại, dùng laptop mới để khôi phục bằng bằng chứng độc lập đã cấp trước, rồi đăng ký factor mới. Không có bất biến bị phá.

Hãy giải thích vì sao rule “thiết bị mới + recovery = compromise” có chất lượng thấp.

Gợi ý đáp án: ngữ cảnh mới phù hợp chính use case recovery. Cần xem điều kiện bằng chứng, liên kết giao dịch, tác động sau đó và dữ kiện độc lập. Rule chỉ từ ngữ cảnh có thể tạo gián đoạn cho người dùng hợp lệ mà vẫn bỏ lọt actor dùng session hoặc thiết bị quen thuộc.

### Bài tập 4: Không có cảnh báo trong một giờ

Dashboard không có finding. Đồng thời, credential service báo có mutation nhưng collector không nhận event từ service đó.

Hãy mô tả kết luận phù hợp.

Gợi ý đáp án: có khoảng mù telemetry; không đủ dữ liệu kết luận không có recovery compromise. Cần xử lý chất lượng dữ liệu, đối chiếu nguồn authority và xem xét replay phần bị thiếu theo quy trình.

### Bài tập 5: Grant một lần, hai cửa sổ

Mutation đầu nằm trước ranh giới cửa sổ một giây; mutation thứ hai nằm sau ranh giới một giây. Hai mutation dùng cùng grant một lần, nhưng hai truy vấn rời nhau đều chỉ thấy một mutation.

Hãy đề xuất cách tránh bỏ sót.

Gợi ý đáp án: giữ trạng thái theo grant đủ vòng đời và độ trễ cho phép, hoặc truy vấn chồng lấn có cơ chế deduplicate finding cùng đối chiếu dữ liệu authority. Không chỉ tăng ngẫu nhiên cửa sổ nếu vẫn giữ các đoạn hoàn toàn rời nhau.

## 17. Điều kiện để một cảnh báo có giá trị điều tra

Một finding tốt cho biết điều gì đã commit, bằng chứng nào liên quan, luật và policy nào được áp dụng, scope nào bị tác động và dữ liệu nào còn thiếu. Nó cho phép người xử lý kiểm chứng kết luận thay vì chỉ tin một điểm rủi ro.

Khả năng phát hiện recovery compromise mạnh nhất khi hệ thống vừa bảo vệ được các bất biến trong đường cấp quyền, vừa quan sát được diễn biến trước và sau recovery. Những sai phạm chắc chắn cần được phân biệt với chuỗi đáng ngờ; cả hai đều cần dữ liệu đúng scope, xử lý trùng và thời gian đúng, cùng một đường triage không làm người dùng hợp lệ mất quyền truy cập ngoài dự kiến.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thiết kế log ứng dụng, ngữ cảnh sự kiện, dữ liệu cần tránh ghi và bảo vệ pipeline.
- [OWASP Forgot Password Cheat Sheet — Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise): xem xét session, factor và thông tin recovery khi nghi ngờ tài khoản bị chiếm.
- [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final): bối cảnh quản lý rủi ro cho hoạt động phát hiện, phản ứng và phục hồi sự cố.
