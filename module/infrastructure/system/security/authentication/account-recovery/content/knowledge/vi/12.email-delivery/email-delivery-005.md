# Recovery email bounce handling — Xử lý email khôi phục bị trả lại

## 1. Vì sao bounce cần được xử lý riêng trong khôi phục tài khoản?

**Bounce** là thông tin cho biết một email không được giao thành công ở một bước của quá trình chuyển thư. Lỗi có thể xuất hiện ngay lúc gửi hoặc được báo về sau khi nhà cung cấp đã nhận email để xử lý.

Ví dụ, Minh quên mật khẩu và yêu cầu nhận liên kết khôi phục. Recovery API đã tiếp nhận yêu cầu, nhà cung cấp email trả về mã thông điệp, nhưng máy chủ nhận sau đó từ chối thư vì hộp thư không còn tồn tại. Nếu hệ thống chỉ lưu `sent=true`, Minh sẽ tiếp tục chờ, còn nút gửi lại có thể tạo thêm nhiều thư không thể giao.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, xử lý bounce phải phục vụ đồng thời hai mục tiêu: giúp người mất mật khẩu, MFA, passkey hoặc thiết bị xác thực tìm được đường khôi phục hợp lệ; và không để thông tin giao nhận trở thành bằng chứng sai để cấp quyền hoặc thay kênh nhận token.

Một bounce không chứng minh người yêu cầu là chủ tài khoản. Nó cũng không cho phép tự đổi email đích, gỡ MFA, tạo phiên đăng nhập hay bỏ qua xác minh danh tính. Đây là tín hiệu về khả năng giao thư, cần được xử lý trong ranh giới riêng với quyền khôi phục.

Sau bài này, người học cần phân biệt lỗi tạm thời và lỗi kết thúc giao nhận, thiết kế retry phù hợp thời hạn token, xử lý sự kiện lặp hoặc sai thứ tự và quản lý trạng thái kênh liên hệ mà không khóa nhầm người dùng.

## 2. Phân biệt các mốc trong quá trình giao email

```text
Yêu cầu khôi phục được tiếp nhận
  -> Công việc gửi được lưu bền vững
  -> Nhà cung cấp nhận thông điệp
  -> Máy chủ nhận chấp nhận hoặc từ chối thư
  -> Hộp thư và bộ lọc xử lý tiếp
  -> Người nhận có thể đọc và sử dụng liên kết
```

Mỗi mốc cung cấp một mức thông tin khác nhau:

| Tín hiệu | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| Recovery API trả tiếp nhận | Hệ thống đã tiếp nhận đầu vào theo hợp đồng API | Tài khoản tồn tại hoặc thư đã được giao |
| Công việc có trong outbox | Ý định gửi đã được lưu để xử lý | Nhà cung cấp đã nhận thông điệp |
| Nhà cung cấp chấp nhận | Nhà cung cấp đã nhận công việc hoặc thông điệp theo hợp đồng của họ | Thư nằm trong inbox của người dùng |
| `deferred` hoặc tương đương | Việc giao đang bị trì hoãn | Thư chắc chắn thất bại hoặc cần ứng dụng gửi một bản khác ngay |
| `delivered` theo sự kiện của nhà cung cấp | Đã đạt mốc giao mà nhà cung cấp định nghĩa, thường là máy chủ nhận chấp nhận | Người thật đã đọc thư hoặc đang kiểm soát tài khoản |
| Bounce kết thúc | Lần giao tương ứng đã thất bại theo thông tin hiện có | Mọi lần gửi khác đều thất bại, địa chỉ chắc chắn sai hoặc người dùng không phải chủ tài khoản |

Không nhận được bounce không đồng nghĩa giao thành công. Không nhận được sự kiện `delivered` cũng không tự chứng minh thất bại; callback có thể đến muộn hoặc bị mất. Cần giữ được trạng thái **chưa biết** thay vì đoán kết quả.

Email bị đưa vào spam, bị cách ly nội bộ hoặc người dùng không nhìn thấy thông báo có thể không tạo bounce. Việc chẩn đoán cần dựa trên đúng loại tín hiệu.

## 3. Phân loại lỗi theo nguyên nhân và bên chịu trách nhiệm

### 3.1. Soft bounce và hard bounce

**Soft bounce** thường chỉ lỗi có tính tạm thời, chẳng hạn máy chủ nhận chưa sẵn sàng hoặc tài nguyên hộp thư tạm bị giới hạn. **Hard bounce** thường chỉ lỗi mà nhà cung cấp xem là kết thúc và không tự thử lại cho lần giao đó, chẳng hạn người nhận không tồn tại.

Tên gọi và cách phân loại có thể khác giữa các nhà cung cấp. Hệ thống cần chuẩn hóa vào mô hình nội bộ nhưng vẫn giữ mã nguồn cần thiết cho điều tra. Không suy luận “địa chỉ không tồn tại” chỉ từ một nhãn `hard` mà chưa xét nguyên nhân.

### 3.2. Mã SMTP không phải kết luận về danh tính

Phản hồi SMTP lớp `4xx` thường biểu thị lỗi tạm thời và lớp `5xx` biểu thị lỗi lâu dài cho thao tác tương ứng. Tuy nhiên, lỗi lâu dài có thể do chính sách, cấu hình người gửi hoặc nội dung thư, chứ không chỉ do địa chỉ nhận sai.

| Nhóm nguyên nhân | Ví dụ | Hướng xử lý |
|---|---|---|
| Người nhận không tồn tại | Báo lỗi xác định mailbox không hợp lệ | Dừng thử lại cùng địa chỉ cho lần giao; cân nhắc suppression theo bằng chứng và phạm vi |
| Hộp thư đầy hoặc tài nguyên tạm thời thiếu | Máy chủ nhận báo giới hạn dung lượng | Áp dụng chính sách tạm thời của nhà cung cấp; retry có giới hạn nếu còn phù hợp thời hạn token |
| Máy chủ nhận tạm lỗi hoặc trì hoãn | Kết nối tạm thất bại, greylisting, throttling | Phân định bên đang retry; không tạo nhiều bản gửi trùng |
| Người gửi hoặc nội dung bị từ chối | Chính sách chống spam, danh tiếng, lỗi cấu hình xác thực tên miền | Điều tra hạ tầng gửi; không mặc định đánh dấu mọi địa chỉ nhận là hỏng |
| Nhà cung cấp chặn trước khi gửi | Địa chỉ nằm trong suppression list hoặc vi phạm chính sách gửi | Xác định phạm vi chặn và quy trình xử lý được phép; không tự né bằng đổi nhà cung cấp |
| Lời gọi API gửi timeout | Không rõ nhà cung cấp đã nhận thông điệp hay chưa | Giữ kết quả chưa biết và đối soát/idempotency nếu được hỗ trợ |
| Khiếu nại spam | Người nhận báo spam | Xử lý như tín hiệu chính sách và lạm dụng riêng, không gộp thành mailbox không tồn tại |

Các mã chi tiết và văn bản chẩn đoán cần được diễn giải theo hợp đồng của hệ thống gửi và máy chủ nhận. Không dùng phép so khớp một từ như `blocked` để tự động thay đổi trạng thái bảo mật tài khoản.

## 4. Tách ba loại trạng thái

Một thiết kế nên tách **quyền khôi phục**, **lần giao thư** và **khả năng sử dụng kênh liên hệ**.

```text
RecoveryChallenge
  challengeId
  accountId
  purpose
  tokenDigest
  contactId
  contactVersion
  expiresAt
  consumedAt
  revokedAt

EmailDeliveryAttempt
  attemptId
  recoveryRequestId
  challengeId
  contactId
  contactVersion
  providerAccountId
  providerMessageId
  submittedAt
  lastEventAt
  deliveryOutcome
  normalizedFailureCategory
  nextRetryAt

ContactDeliveryHealth
  contactId
  contactVersion
  suppressionScope
  state
  evidenceReference
  updatedAt
```

`deliveryOutcome` mô tả lần giao, không cấp hoặc thu hồi quyền thay mật khẩu. `ContactDeliveryHealth` mô tả điều kiện gửi tiếp theo, không thay thế lịch sử xác minh địa chỉ. Trường `verifiedAt` từng được ghi trong quá khứ không nên bị diễn giải thành “luôn giao được”, còn một bounce mới không xóa được sự kiện lịch sử đã xảy ra.

Một địa chỉ có thể đã được xác minh nhưng hiện không còn nhận thư. Ngược lại, một sự kiện giao thành công không xác minh rằng chính người đang yêu cầu khôi phục kiểm soát địa chỉ đó.

Mỗi lần giao cần ràng buộc với đúng phiên bản kênh. Sự kiện muộn của địa chỉ cũ không được làm hỏng trạng thái của email mới vừa được người dùng thay và xác minh.

## 5. Tiếp nhận webhook hoặc thông báo bounce an toàn

### 5.1. Xác thực trước khi tác động trạng thái

Nếu kẻ tấn công có thể giả sự kiện bounce, họ có thể làm hệ thống ngừng gửi email cho người thật. Callback giao nhận vì vậy là một đầu vào an ninh, không chỉ là dữ liệu thống kê.

Quy trình tiếp nhận nên:

1. Giới hạn kích thước và kiểm tra cấu trúc đầu vào.
2. Xác thực nguồn theo cơ chế của nhà cung cấp, chẳng hạn chữ ký trên raw body và các header liên quan.
3. Kiểm tra thời gian, định danh sự kiện và cơ chế chống phát lại theo hợp đồng tích hợp.
4. Đối chiếu tài khoản nhà cung cấp, tenant, mã thông điệp và người nhận với lần giao đã lưu.
5. Ghi sự kiện vào kho bền vững và xử lý idempotent trước khi cập nhật trạng thái dẫn xuất.

Không chỉ tin `recipient`, `accountId` hoặc `challengeId` có trong payload. Chúng phải khớp quan hệ được tạo bởi hệ thống khi gửi. Mã thông điệp cũng cần đặt trong phạm vi nhà cung cấp/tài khoản gửi phù hợp, không mặc định duy nhất trên mọi tích hợp.

Nếu cơ chế xác thực yêu cầu khóa hoặc chứng thư, nguồn lấy chúng phải được kiểm soát. Không tải tùy ý URL do payload đưa vào để “xác minh” chữ ký. Việc đổi khóa, xác thực và giới hạn thời gian phải theo đúng tích hợp thực tế.

Một email báo lỗi được chuyển tiếp thủ công hoặc có người gửi trông giống hệ thống mail không tự có độ tin cậy của webhook đã xác thực. Với bounce qua SMTP/DSN, cần cơ chế tiếp nhận, liên kết và đánh giá nguồn riêng; không dùng bất kỳ thư đến nào có tiêu đề “delivery failed” để chặn kênh tài khoản.

### 5.2. Ghi bền vững rồi phản hồi

Webhook có thể được gửi nhiều lần nếu nhà cung cấp không nhận được phản hồi thành công. Cần ràng buộc duy nhất theo định danh sự kiện trong phạm vi tích hợp. Nếu hệ thống đã lưu thành công, lần giao lặp có thể được xác nhận mà không áp dụng lại tác dụng phụ.

Nếu chưa lưu được sự kiện, không trả thành công rồi bỏ mất dữ liệu với giả định callback sẽ không cần xử lý nữa. Cách phản hồi lỗi và retry phải phù hợp hợp đồng nhà cung cấp; theo dõi cả sự kiện không xác thực, không liên kết được và không xử lý được.

Mã giả:

```text
event = verifyAndParse(rawBody, headers, configuredProvider)
attempt = findAttempt(
    configuredProvider.account,
    event.messageId,
    event.recipientReference
)

require attempt exists and matches the expected recipient/version

BEGIN TRANSACTION
  insert event if not already recorded
  if this is a duplicate:
      do not repeat state changes or notifications
  else:
      derive outcome for this attempt from trusted evidence
      update contact delivery health only when policy permits
      schedule permitted work through outbox if needed
COMMIT

acknowledge durable receipt
```

Đây là mã giả mô tả ranh giới xử lý. Dữ liệu người nhận trong event vẫn cần giảm thiểu và bảo vệ khi lưu; xác thực callback không làm dữ liệu đó trở thành thông tin công khai.

## 6. Xử lý sự kiện trùng và sai thứ tự

Không dùng quy tắc “event đến cuối cùng thắng” cho mọi tình huống. Một `deferred` tới muộn không được kéo lần giao đã có kết quả kết thúc trở lại trạng thái đang chờ. Tương tự, sự kiện thành công của lần gửi A không được ghi đè bounce của lần gửi B chỉ vì chúng thuộc cùng tài khoản.

Nên giữ lịch sử sự kiện theo từng attempt và tính trạng thái dẫn xuất theo quy tắc đã định nghĩa. Cần phân biệt thời gian sự kiện ở nhà cung cấp, thời gian hệ thống nhận và số thứ tự nếu nhà cung cấp có cung cấp. Không giả định timestamp từ các nguồn luôn cho một thứ tự hoàn hảo.

Một số điều kiện có thể đòi hỏi đánh giá bổ sung thay vì ép vào một trạng thái duy nhất. Ví dụ, nhà cung cấp báo `delivered` rồi có thông tin không giao được ở chặng sau. Hệ thống cần hiểu định nghĩa của sự kiện đó và lưu bằng chứng, thay vì bỏ qua bounce hoặc tự kết luận người dùng đã đọc thư.

| Sự kiện nhận được | Tình trạng hiện tại | Quyết định cần có |
|---|---|---|
| Cùng event ID được gửi lại | Sự kiện đã được ghi nhận | Không đếm lỗi, gửi cảnh báo hoặc retry lần thứ hai |
| `deferred` đến sau kết quả kết thúc | Cùng attempt | Giữ lịch sử; không tự mở lại retry |
| Bounce của email cũ | Contact đã tăng phiên bản | Chỉ cập nhật attempt cũ; không chặn email mới |
| Callback không khớp message ID | Không có attempt tương ứng | Cách ly để đối soát; không sửa tài khoản theo email trong payload |
| Hai kết quả có vẻ mâu thuẫn | Cùng attempt | Dùng quy tắc theo tích hợp và đối soát, không đoán từ thứ tự nhận |

## 7. Retry theo thời hạn token và quyền sở hữu công việc

### 7.1. Phân định bên đang thử lại

Nếu nhà cung cấp đã nhận thư và đang retry SMTP sau một lỗi tạm thời, ứng dụng thường không cần gửi thêm thông điệp mỗi lần nhận `deferred`. Hai lớp retry độc lập có thể gây nhiều thư chứa liên kết, tăng chi phí và làm người dùng khó biết thư nào còn dùng được.

Cần xác định rõ:

- Lỗi trước khi nhà cung cấp nhận công việc do ứng dụng xử lý thế nào.
- Khi đã chấp nhận, thời gian và giới hạn retry do nhà cung cấp quản lý ra sao.
- Sự kiện nào xác nhận lần giao đã kết thúc để ứng dụng xem xét hành động tiếp theo.
- Trường hợp timeout không rõ kết quả được đối soát hoặc chống lặp bằng cách nào.

Idempotency key nếu được hỗ trợ cần gắn đúng một công việc gửi. Không suy diễn có cơ chế “gửi đúng một lần” chỉ vì phía ứng dụng đặt một mã request.

### 7.2. Không gửi một bí mật sắp hết tác dụng

Retry phải xét cả số lần thử lẫn thời gian còn lại của challenge:

```text
nextAttemptAt = serverNow + boundedBackoffWithJitter(attemptCount)
latestUsefulSendAt = challenge.expiresAt - minimumUsefulLifetime

retryAllowed =
    failure is classified as retryable
    and application is responsible for retry
    and attemptCount < configuredLimit
    and nextAttemptAt < latestUsefulSendAt
    and challenge is not consumed or revoked
    and contact version is still eligible
    and contact is not suppressed for this send
```

`minimumUsefulLifetime` là khoảng thời gian sản phẩm muốn còn lại cho người nhận thao tác sau lúc gửi, không bảo đảm thư sẽ tới trong khoảng đó. Giá trị phải dựa trên thời hạn token, độ trễ giao nhận và trải nghiệm mong muốn; không có một con số đúng cho mọi dịch vụ.

Nếu không còn đủ thời gian, dừng retry của challenge đó và để người dùng khởi tạo yêu cầu mới theo chính sách. Không tự kéo dài `expiresAt` chỉ vì email bị trì hoãn, cũng không để worker gửi tự phát hành một token mới với quyền rộng hơn.

Retry cùng một công việc phải có chính sách token nhất quán. Nếu dùng lại token đã phát hành, phần bí mật cần thiết để gửi phải được bảo vệ, chẳng hạn payload mã hóa có thời hạn trong outbox. Nếu phát hành challenge thay thế, đó là quyết định cấp quyền riêng, có giới hạn và quy tắc vô hiệu hóa rõ ràng.

### 7.3. Chặn retry vô hạn và retry dồn dập

Backoff có giới hạn, jitter, ngân sách theo người nhận và giới hạn toàn dịch vụ giúp tránh dồn tải khi máy chủ nhận hoặc nhà cung cấp gặp sự cố. Hết ngân sách cần trạng thái kết thúc hoặc chuyển xử lý vận hành, không đẩy vòng lặp sang dead-letter queue rồi tự động gửi lại mãi.

Không đổi liên tục nhà cung cấp để né suppression hoặc chính sách của máy chủ nhận. Failover chỉ nên dùng trong kế hoạch vận hành đã xác định, với cùng kiểm soát quyền, đích gửi, dữ liệu và giới hạn lạm dụng.

## 8. Suppression: dừng gửi đúng phạm vi, không khóa nhầm tài khoản

**Suppression** là chủ động không gửi tới một đích trong một phạm vi nhất định do bằng chứng giao nhận hoặc chính sách. Nó có thể được quản lý tại ứng dụng, nhà cung cấp hoặc cả hai.

Cần ghi rõ nguyên nhân, phạm vi và điều kiện xem xét lại. Phạm vi có thể phụ thuộc địa chỉ/kênh, phiên bản kênh, tenant, tài khoản gửi của nhà cung cấp hoặc loại thông điệp. Nhà cung cấp có thể áp dụng phạm vi rộng hơn mô hình local; ứng dụng phải nhận biết điều này thay vì cho rằng xóa cờ trong cơ sở dữ liệu là đã gửi được.

| Bằng chứng | Phản ứng có thể phù hợp | Phản ứng cần tránh |
|---|---|---|
| Người nhận không tồn tại được xác nhận từ nguồn tin cậy | Dừng retry và áp dụng suppression theo chính sách | Xóa tài khoản hoặc cấp quyền nhập email mới chưa xác minh |
| Vài lỗi tạm thời | Giảm tần suất, retry hữu hạn, theo dõi | Chặn vĩnh viễn địa chỉ ngay sau một lỗi |
| Lỗi cấu hình người gửi trên nhiều đích | Cảnh báo vận hành và hạn chế nguồn lỗi | Gắn cờ hỏng cho mọi mailbox nhận thư |
| Sự kiện không xác thực hoặc không liên kết được | Cách ly để điều tra | Thay đổi deliverability của tài khoản theo payload |
| Contact đã được thay và xác minh theo quy trình | Đánh giá trạng thái gửi của phiên bản mới | Sao chép suppression cũ hoặc xóa suppression nhà cung cấp một cách mù quáng |

Mở suppression cần có căn cứ và quyền phù hợp: sửa nguyên nhân hệ thống, xác minh lại kênh bằng quy trình được phép, hoặc xử lý hỗ trợ có kiểm soát. Một cú bấm “Gửi lại” công khai không được tự xóa mọi chặn gửi.

Nếu địa chỉ không còn dùng được, người dùng có thể cần kênh dự phòng đã liên kết hoặc quy trình xác minh danh tính thay thế. Không chuyển token sang một địa chỉ mới do người yêu cầu nhập chỉ vì email cũ bị bounce.

## 9. Tác động tới token, MFA và phiên

Bounce là kết quả giao nhận của một attempt. Chính sách có thể dừng gửi, đóng công việc hoặc thu hồi challenge liên quan khi có lý do phù hợp, nhưng không được coi mọi bounce là lệnh thu hồi toàn bộ quyền của tài khoản.

Một thư bị bounce không chứng minh mọi bản sao token chưa từng được giao. Có thể tồn tại lần gửi trước, bản sao khác hoặc sự kiện giao nhận đến không đúng thứ tự. Nếu cần thu hồi, thực hiện bằng trạng thái ở máy chủ và kiểm tra cả recovery grant đã đổi từ challenge; không dựa vào giả định rằng người nhận không có token.

Các giới hạn cần giữ:

- Không đánh dấu email đã được người dùng xác minh từ sự kiện `delivered`.
- Không tạo phiên hoặc nâng quyền khi có callback giao thành công.
- Không gỡ MFA hay thay passkey vì kênh gửi thất bại.
- Không thu hồi mọi phiên đăng nhập chỉ từ một bounce chưa được đánh giá là sự cố bảo mật.
- Không đánh dấu khôi phục hoàn tất chỉ vì thông điệp đã được chấp nhận hoặc giao.

Nếu có dấu hiệu email bị chiếm đoạt hoặc thông tin liên hệ bị thay trái phép, đó là đánh giá rủi ro bảo mật bổ sung. Hành động thu hồi token và phiên cần dựa trên chính sách sự cố, không chỉ dựa vào nhãn giao nhận.

## 10. Phản hồi cho người dùng và bảo vệ dữ liệu

### 10.1. Không công khai bounce ở bước chưa xác minh

Endpoint khởi tạo có thể trả thông báo chung:

> Nếu thông tin phù hợp, bạn sẽ nhận được hướng dẫn khôi phục. Nếu chưa thấy thư, hãy kiểm tra các thư mục liên quan hoặc dùng phương án hỗ trợ được cung cấp.

Không trả các trường công khai như `accountExists`, `recipientInvalid`, `suppressed` hoặc địa chỉ dự phòng từ kết quả tra cứu. Nếu chỉ tài khoản thật mới nhận thông báo “Email không giao được”, hệ thống đã tạo một kênh dò tài khoản.

Một phiên đã được xác minh phù hợp hoặc nhân viên hỗ trợ có quyền có thể được xem thông tin chi tiết hơn để xử lý. Tuy nhiên, cần giới hạn dữ liệu theo vai trò; thông báo lỗi của nhà cung cấp có thể chứa địa chỉ đầy đủ, nội dung thư gốc hoặc chi tiết hạ tầng.

### 10.2. Bounce payload cũng có thể chứa bí mật

Thông báo lỗi giao nhận có thể đính kèm header hoặc phần nội dung email gốc, bao gồm URL có token. Không mặc định lưu toàn bộ payload vào log hoặc hệ thống hỗ trợ.

Nên tách dữ liệu chuẩn hóa dùng cho xử lý khỏi payload thô. Nếu cần giữ payload để điều tra, áp dụng mã hóa, quyền truy cập, thời hạn lưu và cơ chế che dữ liệu phù hợp. Audit thông thường chỉ cần mã attempt, mã sự kiện, nhóm nguyên nhân và quyết định xử lý.

Không đưa email, token, URL khôi phục hoặc toàn bộ provider diagnostic vào nhãn metric. Dùng nhãn có số lượng giá trị hữu hạn, như loại thông điệp, nhà cung cấp, nhóm lỗi và môi trường.

## 11. Ví dụ xuyên suốt và quan sát vận hành

Minh gửi một yêu cầu đặt lại mật khẩu. Challenge C1 được phát hành với thời hạn đã chọn; attempt A1 gửi tới phiên bản email V3. Nhà cung cấp nhận thư và tự retry do máy chủ nhận tạm bận. Sau đó nhà cung cấp báo lỗi người nhận không tồn tại.

Một luồng xử lý phù hợp:

1. Recovery API giữ phản hồi tiếp nhận chung; không chờ callback để quyết định công khai tài khoản tồn tại.
2. Ứng dụng không tạo A2 mỗi lần nhận `deferred` vì nhà cung cấp còn đang xử lý A1.
3. Webhook lỗi cuối được xác thực, liên kết với A1/V3 và ghi bền vững một lần.
4. A1 chuyển sang kết quả thất bại theo quy tắc tích hợp; V3 được đánh giá suppression dựa trên nguyên nhân và chính sách.
5. Callback lặp không tạo thêm lỗi thống kê hoặc thêm yêu cầu hỗ trợ.
6. Nếu Minh đã thay email sang V4 bằng một quy trình được phép, lỗi của V3 không được chặn V4.
7. Nếu Minh không còn kênh dùng được, hệ thống cung cấp quy trình thay thế có xác minh; không gửi C1 sang email mới tùy ý.

Các chỉ số hữu ích gồm tỷ lệ bounce theo thông điệp/lần giao đã chuẩn hóa, tỷ lệ lỗi theo nhóm nguyên nhân, thời gian từ tiếp nhận tới kết quả giao, số công việc dừng vì token sắp hết hạn và số callback không liên kết được. Khi tính tỷ lệ, phải xác định mẫu số và loại bỏ event trùng; số HTTP request khôi phục không nhất thiết bằng số thư gửi.

Nếu bounce tăng đồng thời trên nhiều miền nhận, cần xem xét nguyên nhân hạ tầng hoặc cấu hình người gửi trước khi kết luận từng địa chỉ đều sai. Cảnh báo nên giúp xác định phạm vi và loại lỗi, không phát tán danh sách email người dùng.

## 12. Tình huống cần kiểm tra và bài tập

| Tình huống | Hành vi cần bảo đảm |
|---|---|
| API gửi timeout sau khi nhà cung cấp có thể đã nhận | Không giả định chưa gửi; tránh gửi trùng không kiểm soát |
| Soft bounce khi nhà cung cấp đang retry | Không tạo lớp retry ứng dụng cạnh tranh |
| Lần retry kế tiếp nằm sát hoặc sau hạn token | Dừng theo ngân sách thời gian, không tự gia hạn token |
| Hard bounce do chính sách người gửi | Không tự đánh dấu người nhận không tồn tại |
| Webhook giả hoặc chữ ký sai | Không thay trạng thái tài khoản/kênh |
| Cùng webhook tới nhiều lần | Tác dụng phụ và số liệu không bị nhân lên |
| Bounce của email cũ tới sau khi đổi contact | Không chặn phiên bản contact mới |
| `deferred` tới sau kết quả kết thúc | Không tự đưa attempt trở lại vòng gửi |
| Event không khớp tài khoản nhà cung cấp hoặc người nhận | Không cập nhật dựa trên email trong payload |
| Suppression tồn tại ở nhà cung cấp | Không bỏ qua bằng cách chỉ sửa cờ local |
| Payload bounce chứa email gốc và token | Không phát tán bí mật qua log, APM hoặc ticket |
| Người ngoài gọi gửi lại liên tục | Không xóa suppression hoặc được chọn đích nhận token mới |

Bài tập: Một dịch vụ nhận 500 yêu cầu khôi phục, gửi 180 thông điệp và nhận 260 callback, trong đó có callback lặp và callback tạm thời. Cùng lúc, người dùng đổi một email liên hệ trước khi bounce cũ tới. Hãy thiết kế cách tính tỷ lệ bounce, nhận diện event trùng, quyết định retry và cập nhật trạng thái contact.

Phương án cần chỉ rõ ý nghĩa từng trạng thái giao nhận, ai đang chịu trách nhiệm retry, thời hạn hữu ích còn lại của token và điều kiện chuyển sang hỗ trợ có xác minh. Xử lý bounce tốt giúp hệ thống dừng đúng những lần gửi không còn phù hợp mà vẫn giữ nguyên ranh giới cấp quyền của quy trình khôi phục tài khoản.
