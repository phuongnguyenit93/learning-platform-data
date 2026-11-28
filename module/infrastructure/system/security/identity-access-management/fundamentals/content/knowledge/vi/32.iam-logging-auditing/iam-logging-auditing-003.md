# MFA event

## 1. MFA event là gì?

**MFA event** là bản ghi mô tả một sự kiện liên quan đến xác thực đa yếu tố: đăng ký authenticator, tạo challenge, gửi yêu cầu xác minh, kiểm tra một lần thử, từ chối push, hết hạn, phục hồi hoặc thu hồi phương thức xác thực.

Trong logging và audit IAM, mục tiêu không phải ghi lại bí mật người dùng đã nhập. Mục tiêu là biết bước nào đã xảy ra, với chủ thể và tài khoản nào, kết quả gì, bằng chứng đến từ đâu và sự kiện đó thuộc giao dịch xác thực nào.

Ví dụ, dòng log `MFA success` không cho biết thành công ở bước gửi OTP, kiểm tra mã hay hoàn tất toàn bộ đăng nhập. Nếu không có ngữ nghĩa rõ ràng, dashboard có thể báo đăng nhập thành công trong khi người dùng chưa được cấp phiên.

Logging cần bao phủ cả kết quả xác thực thành công và thất bại để hỗ trợ phát hiện, điều tra. OWASP xem các kết quả này là những sự kiện bảo mật quan trọng của ứng dụng. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Bài học tập trung vào cách thiết kế và sử dụng bản ghi MFA. Tên sự kiện và schema bên dưới là ví dụ tự xây dựng để giải thích, không phải tên bắt buộc của mọi IdP hoặc sản phẩm MFA.

## 2. Phân biệt các mức thành công

Một luồng MFA có nhiều bước và mỗi bước có thể thành công độc lập với các bước còn lại.

| Bản ghi hoặc trạng thái | Điều đã được xác nhận | Điều chưa được suy ra |
|---|---|---|
| Challenge được tạo | Máy chủ đã khởi tạo một yêu cầu xác minh | Người dùng đã nhận hoặc đã hoàn tất yêu cầu |
| Nhà cung cấp chấp nhận gửi | Nhà cung cấp nhận yêu cầu gửi tin hoặc push | Tin đã tới thiết bị hoặc người dùng đã đọc |
| Thông báo được xác nhận đã giao | Nguồn giao nhận báo trạng thái giao theo khả năng của nó | Người dùng đã xác thực thành công |
| Một lần thử được xác minh | Verifier chấp nhận bằng chứng của lần thử theo cơ chế tương ứng | Toàn bộ giao dịch đăng nhập đã hoàn tất |
| Challenge hoàn tất | Challenge chuyển sang trạng thái kết thúc hợp lệ | Mọi điều kiện đăng nhập hoặc step-up đều đã đáp ứng |
| Giao dịch xác thực hoàn tất | Hệ thống xác nhận đầy đủ các bước cần thiết cho giao dịch đó | Người dùng có quyền với mọi tài nguyên |
| Phiên được cấp | Ứng dụng tạo phiên theo ngữ cảnh đã kiểm tra | Mọi yêu cầu nghiệp vụ tiếp theo đều được cho phép |

Một OTP hợp lệ có thể xuất hiện trong giao dịch sau đó bị từ chối vì tài khoản đã bị khóa. Ngược lại, đăng nhập hoàn tất nhưng thao tác export bị từ chối có thể là quyết định phân quyền nghiệp vụ, không phải MFA thất bại.

Tên event, trường kết quả và dashboard cần giữ được những khác biệt này. Không dùng một cờ `mfaSuccess=true` để đại diện cho mọi trạng thái từ gửi mã đến truy cập tài nguyên.

## 3. Những nhóm sự kiện cần mô hình hóa

### 3.1. Vòng đời authenticator

Các sự kiện đáng quan tâm gồm bắt đầu đăng ký, xác nhận liên kết authenticator với tài khoản, thay đổi phương thức, thay thế thiết bị, thu hồi và phục hồi.

NIST SP 800-63B mô tả việc duy trì bản ghi về authenticator gắn với tài khoản và thời điểm các thay đổi vòng đời quan trọng. Điều này cho thấy audit không nên chỉ tập trung vào các lần nhập mã khi đăng nhập. [NIST — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Ví dụ các tên sự kiện:

```text
MFA_ENROLLMENT_STARTED
MFA_AUTHENTICATOR_BOUND
MFA_AUTHENTICATOR_REVOKED
MFA_RECOVERY_STARTED
MFA_RECOVERY_COMPLETED
```

Bắt đầu đăng ký chưa có nghĩa authenticator đã được liên kết thành công. Việc tạo mã dự phòng cũng khác với sử dụng một mã dự phòng; cả hai đều không cần ghi giá trị mã vào log.

### 3.2. Challenge, gửi thông báo và lần thử

Một taxonomy minh họa:

| Event type | Thời điểm ghi | Dữ liệu hữu ích |
|---|---|---|
| `MFA_CHALLENGE_CREATED` | Challenge được tạo hợp lệ | Giao dịch, phương thức, mục đích, thời hạn |
| `MFA_DELIVERY_ACCEPTED` | Nhà cung cấp chấp nhận yêu cầu gửi | Challenge reference, nhà cung cấp, mã tham chiếu không bí mật |
| `MFA_ATTEMPT_RESULT` | Có kết quả một lần xác minh | Attempt reference, phương thức, outcome và reason code |
| `MFA_ATTEMPT_THROTTLED` | Một phép thử bị chặn trước khi xác minh | Phạm vi giới hạn và lý do nội bộ cần thiết |
| `MFA_CHALLENGE_CLOSED` | Challenge kết thúc | Thành công, người dùng từ chối, hết hạn hoặc bị hủy |

Một lần nhập mã sai có thể chỉ làm giảm số lượt còn lại, trong khi challenge vẫn hoạt động. Vì vậy, kết quả của một attempt không nên tự động được diễn giải là trạng thái kết thúc của challenge.

Throttling cũng không chứng minh người gọi nhập sai mã: nếu verifier chưa kiểm tra mã, sự kiện cần phản ánh rằng phép thử bị giới hạn chứ không khẳng định credential không hợp lệ.

### 3.3. Kết quả giao dịch và cấp phiên

Có thể dùng các sự kiện riêng như `AUTHENTICATION_TRANSACTION_COMPLETED`, `AUTHENTICATION_TRANSACTION_DENIED` và `SESSION_CREATED` để mô tả kết quả toàn bộ luồng.

Nếu MFA phục vụ một thao tác nhạy cảm trong phiên đã tồn tại, mục đích cần thể hiện `STEP_UP` cùng tham chiếu hành động phù hợp, thay vì đếm nó như một lần đăng nhập mới.

Việc nhận diện phương thức cũng cần có ý nghĩa rõ ràng. Tên chung `OTP` có thể chưa đủ để phân biệt mã thời gian, mã qua tin nhắn hoặc phương thức khác mà hệ thống hỗ trợ. Đồng thời, hai bước nhập cùng loại bí mật không tự động chứng minh đã dùng hai yếu tố độc lập.

## 4. Định danh và ngữ cảnh để liên kết sự kiện

Một cuộc điều tra thường cần liên kết những sự kiện phát sinh ở ứng dụng, IdP, dịch vụ MFA và hệ thống cấp phiên. Chỉ dựa vào email và thời gian gần nhau dễ ghép nhầm các giao dịch chạy đồng thời.

Các định danh nên có trách nhiệm khác nhau:

| Trường | Vai trò |
|---|---|
| `eventId` | Nhận diện một sự kiện đã phát sinh để theo dõi và khử bản sao |
| `authenticationTransactionId` | Liên kết các bước của cùng giao dịch đăng nhập hoặc step-up |
| `challengeRef` | Nhận diện challenge bằng tham chiếu nội bộ được phép đưa vào audit |
| `attemptRef` | Phân biệt các lần thử trong một challenge |
| `requestId` hoặc `traceId` | Theo dõi một yêu cầu hoặc chuỗi xử lý kỹ thuật |
| `authenticatorRef` | Tham chiếu authenticator mà không ghi secret của nó |
| `sessionRef` | Liên kết phiên bằng giá trị dành cho audit, không dùng trực tiếp để xác thực |

Tham chiếu audit không nên là một bearer credential. Nếu một ID hoặc URL có thể dùng để hoàn tất challenge, tải credential hay tiếp tục phiên, không đưa nguyên giá trị đó vào log chỉ vì nó được gọi là “ID”.

Nếu cần liên kết phiên, có thể dùng tham chiếu thay thế hoặc giá trị dẫn xuất có bảo vệ theo thiết kế của hệ thống. Không ghi cookie phiên hoặc access token đầy đủ vào bản ghi.

### Actor và tài khoản bị tác động

Đối với một lần xác minh của người dùng, actor và tài khoản đích có thể là cùng một chủ thể trong ngữ cảnh đã được xác thực trước đó. Với thao tác quản trị đặt lại MFA, actor là người quản trị hoặc workload thực hiện, còn tài khoản đích là người bị thay đổi authenticator.

Nếu có thao tác thay người dùng, cần giữ người thực hiện thật và người được đại diện theo mô hình của hệ thống. Không ghi mọi hành động như thể chính chủ tài khoản đích đã thực hiện.

Trước khi identity được xác minh, tên đăng nhập được trình bày chỉ là thông tin ứng viên. Không gán một actor đã xác thực cho mọi yêu cầu chỉ vì tìm thấy một tài khoản khớp tên đó trong directory. Có thể tách định danh được trình bày đã được bảo vệ khỏi chủ thể đã xác thực.

### Tenant và nguồn dữ liệu

Tenant phải được lấy từ ngữ cảnh đã xác minh của luồng. Một `tenantId` do client tự gửi không đủ để định tuyến log vào kho mà quản trị viên tenant đó được xem.

Với identity liên kết qua nhiều nguồn, cần đủ ngữ cảnh nguồn phát hành hoặc directory để tránh ghép cùng một chuỗi `subjectId` của hai hệ thống khác nhau.

IP và thông tin thiết bị cũng cần ghi kèm nguồn và mức tin cậy phù hợp. Một header do client tự khai không được biến thành bằng chứng rằng thao tác đến từ thiết bị đã được quản lý.

## 5. Ví dụ một MFA event có cấu trúc

Ví dụ sau mô tả một lần thử TOTP đã được verifier chấp nhận trong giao dịch đăng nhập. Người gọi đã đi qua bước xác thực ban đầu; sự kiện này chưa tuyên bố toàn bộ giao dịch hoàn tất.

```json
{
  "schemaVersion": 1,
  "eventId": "event-7204",
  "eventType": "MFA_ATTEMPT_RESULT",
  "occurredAt": "2026-06-01T09:15:20Z",
  "receivedAt": "2026-06-01T09:15:21Z",
  "source": {
    "service": "mfa-verifier",
    "environment": "production"
  },
  "tenantId": "tenant-an-phu",
  "actor": {
    "kind": "USER",
    "subjectId": "user-lan",
    "identityContext": "PRIMARY_AUTHENTICATED"
  },
  "authenticationTransactionId": "auth-tx-508",
  "challengeRef": "audit-challenge-31",
  "attemptRef": "attempt-2",
  "authenticatorRef": "authenticator-19",
  "method": "TOTP",
  "purpose": "LOGIN",
  "outcome": "SUCCESS",
  "reasonCode": "FACTOR_VERIFIED",
  "requestId": "request-816"
}
```

Schema này không chứa OTP, secret TOTP, QR code đăng ký, cookie hoặc token. Các tham chiếu là dữ liệu minh họa dành cho audit, không phải credential có thể dùng để truy cập.

`PRIMARY_AUTHENTICATED` trong ví dụ chỉ mô tả ngữ cảnh mà hệ thống đã xác nhận ở bước trước. Nó không tự đồng nghĩa mọi điều kiện MFA, policy đăng nhập hoặc quyền nghiệp vụ đều đã đáp ứng.

Các hệ thống dùng IdP bên ngoài có thể nhận thông tin về phương thức hoặc mức xác thực trong kết quả giao thức. Chỉ dùng thông tin đã được kiểm tra theo mô hình tin cậy của giao thức và nguồn phát hành; không lấy một cờ `mfa=true` do client tự gửi làm bằng chứng audit.

Nên chuẩn hóa các trường có thể so sánh như event type, outcome, phương thức và reason code. Có thể giữ tên loại sự kiện từ nhà cung cấp nếu cần truy vết, nhưng không vì thế lưu nguyên toàn bộ payload chứa dữ liệu nhạy cảm.

## 6. Bí mật và dữ liệu cần loại khỏi log

OTP là bí mật xác thực. OWASP khuyến cáo không ghi giá trị OTP vào log; việc mã có thời hạn ngắn không làm nó trở thành dữ liệu được phép công khai. [OWASP Multifactor Authentication Cheat Sheet — OTP Handling](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#one-time-password-otp-handling-and-storage).

Những dữ liệu cần tránh ghi trực tiếp gồm:

- Mật khẩu, OTP, mã dự phòng và mã phục hồi.
- Secret tạo TOTP, URI đăng ký hoặc nội dung QR chứa secret.
- Private key và credential dùng để gọi nhà cung cấp MFA.
- Access token, refresh token, cookie phiên và liên kết xác thực có thể sử dụng được.
- Toàn bộ request hoặc response xác thực chưa qua lọc.
- Dữ liệu sinh trắc học thô hoặc thông tin thiết bị không cần thiết cho mục đích audit.

Với authenticator thực hiện kiểm tra sinh trắc học cục bộ, máy chủ có thể chỉ biết kết quả hoặc thuộc tính giao thức liên quan mà nó thực sự xác minh được. Không tự suy ra hoặc thu thập loại sinh trắc học người dùng đã sử dụng nếu hệ thống không có bằng chứng và nhu cầu phù hợp.

Địa chỉ email, số điện thoại, IP và tên thiết bị có thể hữu ích trong điều tra nhưng cũng cần được giảm thiểu, che bớt hoặc giới hạn quyền đọc. Không nên đưa những giá trị đó vào mọi bản ghi nếu một định danh nội bộ đủ để phục vụ mục đích.

OWASP cũng lưu ý việc hạn chế ghi trực tiếp token, mật khẩu, giá trị nhận diện phiên và dữ liệu nhạy cảm trong application log. [OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

### Log injection và dữ liệu do bên ngoài cung cấp

Tên thiết bị, user agent hoặc thông báo từ nhà cung cấp có thể chứa ký tự không mong đợi. Nếu nối thẳng chúng vào dòng log, dữ liệu đầu vào có thể phá cấu trúc hoặc tạo bản ghi giả trong giao diện đọc log.

Nên dùng serializer cho log có cấu trúc, kiểm tra kiểu và độ dài, cùng cơ chế encode phù hợp với đầu ra. Một danh sách trường được phép ghi an toàn hơn việc dump toàn bộ object rồi cố che bí mật sau đó.

Việc che bí mật phải bao phủ cả debug log, exception, tracing, dead-letter queue và công cụ hỗ trợ. Tắt trường OTP trong audit chính không có tác dụng đầy đủ nếu request body vẫn xuất hiện trong trace.

## 7. Trạng thái challenge, sự kiện trùng và thứ tự thời gian

Một luồng minh họa có thể như sau:

```text
Xác thực ban đầu thành công
        ↓
MFA_CHALLENGE_CREATED
        ↓
MFA_DELIVERY_ACCEPTED nếu phương thức cần gửi
        ↓
Một hoặc nhiều MFA_ATTEMPT_RESULT
        ↓
MFA_CHALLENGE_CLOSED
        ↓
Đánh giá các điều kiện còn lại của giao dịch
        ↓
AUTHENTICATION_TRANSACTION_COMPLETED hoặc DENIED
        ↓
SESSION_CREATED nếu luồng cần cấp phiên và được phép
```

Không phải phương thức nào cũng có bước gửi tin, và một giao dịch có thể có nhiều challenge. Schema cần biểu diễn được quan hệ này thay vì giả định mỗi giao dịch chỉ có đúng một dòng MFA.

### Thời điểm xảy ra khác thời điểm tiếp nhận

`occurredAt` biểu diễn thời điểm sự kiện xảy ra theo nguồn. `receivedAt` biểu diễn lúc thành phần nhận tiếp nhận sự kiện. Một webhook vừa tới có thể mô tả sự kiện đã xảy ra trước đó.

Các hệ thống cần định dạng thời gian rõ múi giờ và theo dõi độ lệch đồng hồ. Thứ tự theo thời gian nhận không đủ để khẳng định thứ tự nhân quả giữa mọi dịch vụ. Có thể cần phiên bản trạng thái, số thứ tự từ nguồn hoặc liên kết nguyên nhân theo mô hình được hỗ trợ.

Không để một thông báo “đang chờ” đến muộn làm trạng thái challenge đã hoàn tất quay lại chờ. Đồng thời, log cần giữ được việc thông báo đến muộn mà không sửa lịch sử cũ để làm nó trông như luôn đến đúng thứ tự.

### Bản sao sự kiện khác lần thử mới

Nhà cung cấp hoặc hàng đợi có thể gửi lại cùng một sự kiện. Dùng `eventId` ổn định trong phạm vi nguồn giúp nhận ra bản sao do retry, nhưng không nên gộp mọi event cùng tài khoản và outcome thành một sự kiện duy nhất.

Hai lần nhập mã sai thực sự là hai lần thử khác nhau. Ngược lại, ba bản sao của cùng một thông báo không được làm dashboard đếm thành ba lần thất bại hay ba lần người dùng từ chối push.

Việc khử trùng cần kết hợp với xác thực nguồn và kiểm tra định dạng. Một event ID do nguồn không được tin cậy tự khai không đủ để cho phép ghi đè hoặc loại bỏ một sự kiện hợp lệ khác.

Trạng thái xác thực chuẩn phải được quản lý tại thành phần thực thi xác thực. Kho log bất đồng bộ không nên trở thành nơi duy nhất đếm lượt OTP hoặc quyết định một challenge đã được dùng, vì sự kiện có thể trễ, lặp hoặc thiếu.

## 8. Thay đổi phương thức MFA là sự kiện đặc quyền

Liên kết một authenticator mới, vô hiệu hóa MFA hoặc đặt lại phương thức có thể thay đổi cách kiểm soát tài khoản trong những lần đăng nhập sau. Các hành động này cần được quan sát tương xứng, không chỉ ghi một dòng “profile updated”.

Một sự kiện quản trị cần cho biết ai yêu cầu thay đổi, tài khoản nào bị tác động, loại thay đổi, kết quả và căn cứ quy trình như ticket hoặc approval nếu có. Nếu quản trị viên Huy đặt lại MFA cho Lan, cần phân biệt Huy với Lan và với service account áp dụng thay đổi.

Chỉ lưu tham chiếu authenticator cũ và mới cùng loại thay đổi khi cần; không lưu secret trước hoặc sau. Nếu tạo mã phục hồi, audit có thể ghi việc tạo và số lượng theo policy mà không ghi giá trị các mã.

Thông báo cho chủ tài khoản là một kiểm soát khác với audit nội bộ. NIST mô tả các thông báo độc lập cho một số sự kiện như liên kết authenticator và phục hồi tài khoản. [NIST — Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications).

Một bản ghi gửi thông báo chỉ chứng minh bước gửi theo trạng thái thực tế của hệ thống. Không coi việc nhà cung cấp đã nhận tin là bằng chứng chủ tài khoản đã biết và đồng ý với thay đổi.

Nếu policy cho phép một cơ chế phục hồi hoặc ngoại lệ làm giảm yêu cầu MFA, cần ghi rõ mục đích và phạm vi ngoại lệ. Không gộp việc dùng ngoại lệ với một lần hoàn tất MFA thông thường trong báo cáo.

## 9. Phát hiện bất thường từ chuỗi MFA event

Một sự kiện đơn lẻ thường chưa đủ để kết luận có tấn công. Người dùng có thể nhập sai mã, mất kết nối hoặc bỏ quên thông báo. Giá trị phát hiện đến từ việc kết hợp tần suất, lịch sử, ngữ cảnh và kết quả sau đó.

| Mẫu quan sát | Câu hỏi điều tra | Điều không nên kết luận tự động |
|---|---|---|
| Nhiều challenge hoặc push trong thời gian ngắn | Có lạm dụng gửi thông báo hoặc lỗi retry của ứng dụng không? | Mọi lần gửi đều do một lần đăng nhập khác nhau |
| Người dùng từ chối nhiều push rồi có một lần thành công | Thành công thuộc giao dịch nào, phương thức nào và nguồn nào? | Thành công chắc chắn là kẻ tấn công hoặc chắc chắn là hợp lệ |
| Nhiều OTP không hợp lệ cho cùng tài khoản | Có phép đoán, đồng hồ thiết bị sai hay lỗi người dùng không? | Mọi thất bại đều là credential stuffing |
| Authenticator mới được liên kết rồi có hoạt động đặc quyền | Ai liên kết, qua luồng nào, có approval hoặc thông báo cần thiết không? | Việc liên kết mới tự nó chứng minh chiếm tài khoản |
| Phục hồi MFA rồi đăng nhập từ ngữ cảnh bất thường | Luồng phục hồi và lần đăng nhập có quan hệ gì? | Một lần phục hồi hợp lệ luôn làm mọi truy cập sau đó an toàn |
| Tăng mạnh lỗi nhà cung cấp | Dependency có gián đoạn không? | Người dùng đồng loạt nhập sai mã |

Ngưỡng cảnh báo cần dựa trên loại phương thức, quy mô và hành vi bình thường của hệ thống. Không chỉ đổi log level của mọi lỗi OTP thành cảnh báo khẩn cấp rồi kỳ vọng có tín hiệu điều tra tốt.

Một số dữ liệu như reason code chi tiết có thể dùng nội bộ nhưng không nên trả đầy đủ cho client trước xác thực nếu làm lộ trạng thái tài khoản hoặc cơ chế kiểm soát.

Cảnh báo và thực thi cũng cần được phân biệt. Một rule SIEM tạo alert chưa có nghĩa phiên bị thu hồi. Nếu hệ thống tự động phản ứng, cần biết thành phần nào có thẩm quyền áp dụng hành động, phạm vi ảnh hưởng và bằng chứng audit của chính hành động đó.

## 10. Pipeline ghi nhận và bảo vệ audit

Một pipeline minh họa:

```text
Dịch vụ MFA hoặc IdP
        ↓
Sự kiện có cấu trúc, chỉ chứa trường được phép
        ↓
Tiếp nhận có xác thực nguồn và truyền an toàn
        ↓
Kiểm tra schema, chuẩn hóa và nhận diện bản sao
        ↓
Kho audit được bảo vệ + chỉ mục phục vụ điều tra
        ↓
Dashboard, phát hiện và quy trình phản ứng
```

Nếu nhận webhook, cần xác minh nguồn theo cơ chế mà nhà cung cấp hỗ trợ và xử lý chống replay phù hợp. Không tin một webhook tự khai `outcome=SUCCESS` rồi dùng nó làm bằng chứng người dùng đã xác thực mà chưa kiểm tra nguồn và quan hệ với giao dịch đang xử lý.

Schema nên có phiên bản và quy tắc chuyển đổi rõ ràng. Nếu một trường outcome mới chưa được hiểu, không tự đổi nó thành `FAILURE` hoặc `SUCCESS` chỉ để dashboard tiếp tục chạy. Có thể giữ trạng thái không hiểu được và phát hiện lỗi tương thích mà không làm sai ngữ nghĩa bảo mật.

### Ghi bền vững và đối chiếu trạng thái

Với thay đổi authenticator nhạy cảm, có thể dùng một bản ghi audit hoặc durable outbox đi cùng giao dịch thay đổi trạng thái. Sau đó hệ thống chuyển sự kiện tới nơi lưu trữ tập trung, có retry và theo dõi backlog.

Việc trạng thái thay đổi thành công rồi tiến trình chết trước khi gửi log có thể làm mất bằng chứng nếu chỉ gọi logger mạng sau khi commit. Ngược lại, một sự kiện yêu cầu thay đổi được gửi đi chưa chứng minh thay đổi đã hoàn tất. Cần mô hình hóa ý định và kết quả đúng lúc.

Nếu pipeline có thể giao sự kiện nhiều lần, phải thiết kế consumer chịu được bản sao. Không tuyên bố xử lý đúng một lần trên toàn hệ thống chỉ vì một thành phần có khóa duy nhất theo event ID.

### Quyền đọc, sửa và phạm vi tenant

Quyền xem audit nên được cấp theo nhiệm vụ. Người hỗ trợ có thể cần xem kết quả và mã tham chiếu, nhưng không nhất thiết được xem đầy đủ dữ liệu nguồn hoặc xuất log hàng loạt.

Quản trị viên tenant chỉ được xem dữ liệu trong phạm vi được cấp. Tìm kiếm, export và dashboard cũng cần giữ ranh giới tenant; một bộ lọc giao diện không thay thế phân quyền phía máy chủ.

Người quản trị MFA không nên tùy ý sửa hoặc xóa dấu vết các thay đổi của chính mình. Có thể kết hợp giới hạn thao tác ghi, bản sao độc lập, lưu trữ có kiểm soát và cơ chế phát hiện sửa đổi phù hợp.

Một chuỗi hash hỗ trợ phát hiện thay đổi chỉ khi những điểm neo và quyền quản trị liên quan được bảo vệ đúng thiết kế. Nó không tự chứng minh nội dung nguồn là sự thật hoặc bảo đảm không thể xóa cả một đoạn lịch sử mà không có bằng chứng đối chiếu.

### Khi logging gặp lỗi

Cần có policy cho lỗi schema, queue đầy, kho lưu trữ không sẵn sàng và log vượt dung lượng. Không để lỗi ghi log làm lộ credential trong exception hoặc tự chuyển sang dump request để gỡ lỗi.

Với thay đổi đặc quyền yêu cầu audit bền vững, thiết kế có thể chưa hoàn tất thay đổi khi chưa ghi được bằng chứng bắt buộc. Với lưu lượng xác thực lớn, cần buffer có giới hạn, giám sát mất dữ liệu và chế độ vận hành phù hợp. Không dùng cùng một quy tắc mù quáng cho mọi event và mọi mức nhạy cảm.

Nếu phải tổng hợp hoặc giới hạn log để bảo vệ hệ thống, cần xác định rõ những bằng chứng nào vẫn được giữ và theo dõi số sự kiện không được lưu. Sampling vô tình có thể làm mất chính chuỗi thất bại hoặc thay đổi authenticator cần điều tra.

## 11. Tình huống: mã hợp lệ nhưng không có phiên đăng nhập

Lan bắt đầu đăng nhập vào ứng dụng của An Phú. Bước xác thực ban đầu thành công và hệ thống tạo một challenge TOTP. Trong lúc Lan nhập mã, tài khoản của Lan bị vô hiệu hóa qua quy trình quản trị.

| Thứ tự logic | Sự kiện | Ý nghĩa |
|---|---|---|
| 1 | `MFA_CHALLENGE_CREATED` | Có challenge trong giao dịch `auth-tx-508` |
| 2 | `MFA_ATTEMPT_RESULT`, outcome `SUCCESS` | Verifier chấp nhận bằng chứng của lần thử |
| 3 | `MFA_CHALLENGE_CLOSED`, lý do đã xác minh | Challenge hoàn tất theo trạng thái chuẩn |
| 4 | `AUTHENTICATION_TRANSACTION_DENIED`, lý do tài khoản bị vô hiệu hóa | Giao dịch không được hoàn tất thành đăng nhập |
| 5 | Không có sự kiện cấp phiên tương ứng; trạng thái hệ thống xác nhận không tạo phiên | Ứng dụng chưa cấp phiên cho giao dịch này |

Dashboard đếm mọi `MFA_ATTEMPT_RESULT=SUCCESS` như login success sẽ báo sai. Người điều tra cần truy theo transaction ID, kiểm tra kết quả giao dịch và đối chiếu trạng thái cấp phiên.

Chỉ riêng việc không tìm thấy `SESSION_CREATED` trong log cũng chưa chứng minh phiên không tồn tại: sự kiện có thể bị trễ hoặc thất lạc. Trong tình huống này, kết luận cần dựa thêm vào trạng thái chuẩn và độ đầy đủ của pipeline.

Nếu tài khoản được bật lại sau đó, một giao dịch mới cần được xử lý theo policy hiện hành. Không lấy sự kiện xác minh cũ làm bằng chứng cho một challenge hoặc mục đích khác.

## 12. Chỉ số và câu hỏi tự kiểm tra

Nên tách các chỉ số như số challenge, số lần thử, số challenge hoàn tất, số giao dịch xác thực thành công và số phiên được tạo. Mỗi chỉ số có đơn vị và mẫu số khác nhau.

Các chỉ số vận hành hữu ích còn gồm độ trễ từ phát sinh tới tiếp nhận, tỷ lệ bản sao, số event không hợp lệ theo schema, backlog, sai lệch trạng thái và số giao dịch thiếu chuỗi sự kiện mong đợi.

Khi tính tỷ lệ thành công MFA, phải nêu rõ đang tính theo attempt, challenge hay transaction. Nhiều lần thử sai trước một challenge thành công không có cùng ý nghĩa với nhiều giao dịch đăng nhập thất bại độc lập.

Các tình huống nên kiểm tra gồm mã sai rồi đúng, challenge hết hạn, người dùng từ chối push, provider timeout, webhook lặp hoặc đến muộn, tài khoản bị khóa giữa luồng, thay đổi authenticator bằng tài khoản quản trị và pipeline audit bị gián đoạn.

Câu hỏi tự kiểm tra:

1. Vì sao `MFA_DELIVERY_ACCEPTED` không chứng minh người dùng nhận tin hoặc xác thực thành công?
2. Một lần thử, một challenge và một giao dịch đăng nhập cần các định danh khác nhau để làm gì?
3. Những dữ liệu nào phải được loại khỏi audit ngay cả khi chỉ bật debug tạm thời?
4. Vì sao ba bản sao webhook không được đếm thành ba lần người dùng từ chối push?
5. Cần thêm bằng chứng gì trước khi kết luận không có phiên chỉ vì không thấy sự kiện cấp phiên trong kho log?

MFA event có giá trị khi nó mô tả đúng bước, đúng chủ thể, đúng kết quả và liên kết được với trạng thái xác thực thực tế. Audit đầy đủ về mặt ngữ nghĩa, được bảo vệ và không chứa bí mật giúp điều tra mà không biến hệ thống log thành một kho credential khác.
