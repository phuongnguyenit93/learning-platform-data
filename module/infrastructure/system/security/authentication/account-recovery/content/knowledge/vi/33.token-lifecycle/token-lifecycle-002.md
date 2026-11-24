# Token activation event

## 1. Sự kiện kích hoạt token biểu thị điều gì?

Trong luồng khôi phục tài khoản, **token activation event** là sự kiện ghi nhận một token hoặc quyền khôi phục đã chuyển sang trạng thái có thể được sử dụng theo chính sách của máy chủ. Đây là thời điểm một quyền hạn có hiệu lực, vì vậy cần xác định rõ điều kiện, phạm vi và thời hạn của quyền đó.

Ví dụ, một token có mục đích `RESET_PASSWORD` cho tài khoản A được kích hoạt lúc 10:00. Từ thời điểm đó, người giữ token có thể yêu cầu thao tác đặt lại mật khẩu trong phạm vi được cấp, miễn là token còn hạn và các điều kiện sử dụng vẫn thỏa mãn. Sự kiện này không tự chứng minh người dùng đã đổi mật khẩu, đã khôi phục MFA hoặc đã đăng nhập.

Trong bài này, `RecoveryTokenActivated` và các trạng thái phía dưới là **một mô hình thiết kế minh họa**. Tên sự kiện, schema và việc có cần trạng thái chờ kích hoạt phụ thuộc hệ thống; không có yêu cầu rằng mọi dịch vụ phải dùng đúng các tên này.

Các thực hành nền tảng vẫn áp dụng: token cần được sinh bằng nguồn ngẫu nhiên mật mã, đủ khó đoán, lưu an toàn, dùng một lần và có thời hạn phù hợp. OWASP cũng khuyến nghị tránh thay đổi tài khoản trước khi nhận được token hợp lệ. Xem [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 2. Phân biệt các mốc trong vòng đời

| Mốc | Ý nghĩa | Điều chưa thể kết luận |
| --- | --- | --- |
| Requested | Hệ thống nhận yêu cầu bắt đầu khôi phục | Người gửi yêu cầu là chủ tài khoản |
| Issued | Token đã được tạo và gắn với một yêu cầu cụ thể | Token luôn có hiệu lực ngay |
| Delivered | Kênh gửi báo đã tiếp nhận hoặc chuyển thông điệp | Chủ tài khoản đã nhận và đọc thông điệp |
| Activated | Quyền của token bắt đầu có hiệu lực theo chính sách | Thao tác khôi phục đã thành công |
| Presented | Một bên đã gửi token đến máy chủ | Token hợp lệ hoặc được phép dùng |
| Consumed | Quyền dùng một lần đã được sử dụng thành công | Có thể dùng lại cùng token |
| Revoked | Máy chủ thu hồi quyền trước khi hết hạn tự nhiên | Một sự kiện cũ có thể khôi phục quyền đó |
| Expired | Thời hạn sử dụng đã kết thúc | Chờ tác vụ dọn dẹp chạy thì token mới hết hiệu lực |

Hai cách tổ chức thường gặp:

**Kích hoạt ngay khi phát hành.** Máy chủ tạo bản ghi token ở trạng thái `ACTIVE` trong giao dịch phát hành. Nếu cần sự kiện, `Issued` và `Activated` có thể được ghi cùng giao dịch. Cách này phù hợp với nhiều liên kết đặt lại mật khẩu, vì việc chứng minh quyền giữ token diễn ra khi sử dụng liên kết.

**Kích hoạt sau một điều kiện bổ sung.** Token được tạo ở trạng thái `PENDING`, sau đó chỉ chuyển sang `ACTIVE` khi hệ thống xác nhận điều kiện đã định, chẳng hạn hoàn tất một bước xác minh riêng hoặc hết thời gian chờ của một quy trình khôi phục nhạy cảm. Điều kiện phải có bằng chứng phía máy chủ và còn hiệu lực tại lúc kích hoạt.

Không thêm trạng thái `PENDING` chỉ để làm luồng trông an toàn hơn. Nếu ai biết token cũng có thể kích hoạt rồi sử dụng ngay, bước bổ sung đó chưa tạo thêm bằng chứng danh tính.

## 3. Điều kiện cho phép kích hoạt

Một quyết định kích hoạt cần trả lời được những câu hỏi sau:

1. Token thuộc đúng tài khoản, tenant, yêu cầu khôi phục và mục đích nào?
2. Yêu cầu khôi phục còn đang mở hay đã hoàn tất, bị hủy hoặc bị thay thế?
3. Bằng chứng cần thiết đã được xác minh bởi thành phần có thẩm quyền chưa?
4. Bằng chứng có gắn với đúng yêu cầu này và còn đủ mới không?
5. Token còn trong thời gian cho phép kích hoạt và chưa hết hạn sử dụng không?
6. Trạng thái tài khoản, rủi ro hoặc phương thức xác thực có thay đổi làm mất hiệu lực quyết định trước đó không?
7. Chủ thể gọi lệnh kích hoạt có quyền thực hiện chuyển trạng thái này không?

Không nhận các trường như `identityVerified=true`, `riskApproved=true` hoặc `purpose=RESET_MFA` từ trình duyệt rồi coi đó là quyết định bảo mật. Client có thể cung cấp đầu vào; máy chủ phải tự xác thực bằng chứng và lấy phạm vi quyền từ bản ghi đã quản lý.

Cũng cần tách **quyền kích hoạt** khỏi **quyền sử dụng**. Dịch vụ xử lý khôi phục có thể được phép kích hoạt sau một quyết định hợp lệ; người dùng sử dụng token vẫn phải chứng minh quyền giữ token và đáp ứng các điều kiện của thao tác đích.

### Phạm vi theo loại khôi phục

| Mục đích token | Quyền có thể cấp | Điều cần tránh |
| --- | --- | --- |
| Đặt lại mật khẩu | Cho phép đặt mật khẩu mới cho tài khoản đã ràng buộc | Ngầm tắt MFA hoặc cấp phiên đăng nhập đầy đủ |
| Khôi phục MFA | Cho phép bước thay thế yếu tố đã được phê duyệt | Dùng token đặt lại mật khẩu để xóa mọi yếu tố |
| Đăng ký passkey thay thế | Cho phép bắt đầu đăng ký trong ngữ cảnh đã xác minh | Cho rằng token chứa hoặc khôi phục khóa riêng của passkey cũ |
| Khôi phục thiết bị xác thực | Cho phép bước thiết lập thiết bị thay thế theo chính sách | Tự động tin cậy vĩnh viễn thiết bị chỉ vì có liên kết khôi phục |

Một token đã kích hoạt không phải quyền khôi phục toàn bộ tài khoản. Mỗi thao tác nhạy cảm cần kiểm tra đúng `purpose`, đối tượng và giới hạn của quyền được cấp.

## 4. Mô hình trạng thái và các bất biến

Mô hình sau dành cho trường hợp có bước kích hoạt trì hoãn:

```text
PENDING -- điều kiện hợp lệ --> ACTIVE -- sử dụng thành công --> CONSUMED
   |                              |
   +---- thu hồi --> REVOKED <-----+
   |                              |
   +---- quá hạn --> EXPIRED <-----+
```

Không có cạnh chuyển từ `CONSUMED`, `REVOKED` hoặc `EXPIRED` về `ACTIVE`. Khi người dùng cần thử lại sau một trạng thái kết thúc, hệ thống xét một yêu cầu mới theo chính sách, thay vì hồi sinh token cũ.

Các bất biến quan trọng của mô hình:

- Kích hoạt chỉ hợp lệ từ `PENDING`; với luồng kích hoạt ngay, bản ghi bắt đầu ở `ACTIVE`.
- Thời hạn sử dụng được kiểm tra khi nhận lệnh kích hoạt và khi sử dụng.
- Kích hoạt không được thay đổi tài khoản, mục đích hoặc yêu cầu khôi phục đã ràng buộc.
- Gửi lại một sự kiện hoặc retry cùng lệnh không kéo dài thời hạn token.
- Token đã thu hồi hoặc đã sử dụng không được chấp nhận dù cache hay bản sao đọc còn thể hiện trạng thái cũ.
- Mỗi lần chuyển trạng thái có phiên bản tăng dần để phát hiện cập nhật cạnh tranh.

Có thể xem điều kiện sử dụng như sau:

```text
usable =
    token_secret_matches
    AND state == ACTIVE
    AND not_before <= authoritative_now
    AND authoritative_now < expires_at
    AND recovery_request_is_current
    AND account_and_purpose_match
    AND required_policy_conditions_still_hold
```

Một job có thể đánh dấu các dòng quá hạn thành `EXPIRED` để tiện vận hành. Tuy nhiên, đường xử lý bảo mật vẫn phải kiểm tra `expires_at`; không phụ thuộc vào thời điểm job chạy.

## 5. Thiết kế thời gian kích hoạt và thời hạn sử dụng

Với kích hoạt trì hoãn, cần phân biệt:

- `issued_at`: lúc tạo token.
- `activation_deadline`: hạn cuối để được kích hoạt.
- `activated_at`: lúc giao dịch kích hoạt được ghi nhận.
- `not_before`: thời điểm sớm nhất cho phép sử dụng, nếu chính sách cần.
- `expires_at`: hạn cuối sử dụng.
- `absolute_deadline`: giới hạn tuyệt đối của cả quyền khôi phục, nếu có.

Một chính sách minh họa:

```text
expires_at = min(
    activated_at + allowed_active_lifetime,
    absolute_deadline
)
```

Đây là lựa chọn thiết kế, không phải thời hạn mặc định cho mọi hệ thống. Nếu thời hạn được tính từ lúc phát hành, kích hoạt muộn chỉ còn phần thời gian còn lại. Nếu thời hạn tính từ lúc kích hoạt, cần giới hạn thời gian chờ để token không nằm ở `PENDING` vô thời hạn.

Ví dụ:

```text
10:00  phát hành token PENDING
10:05  hạn cuối kích hoạt
10:03  điều kiện được xác nhận, token chuyển ACTIVE
10:08  hết hạn sử dụng theo chính sách của ví dụ
10:09  sự kiện Activated được chuyển lại do retry
```

Sự kiện đến lúc 10:09 vẫn mô tả việc đã xảy ra lúc 10:03. Nó không mở thêm một khoảng sử dụng mới.

Máy chủ dùng nguồn thời gian đã thống nhất cho quyết định bảo mật, ưu tiên cùng nguồn trong một giao dịch. Không dùng thời gian từ điện thoại, trình duyệt hoặc thời điểm consumer nhận message làm mốc kích hoạt thực tế.

## 6. Ghi nhận kích hoạt bằng giao dịch

Điểm quyết định của việc kích hoạt là **giao dịch chuyển trạng thái thành công**, thay vì việc một message được phát lên broker.

Một luồng xử lý minh họa:

```text
activate(recoveryRequestId, tokenRecordId, commandId):
    BEGIN TRANSACTION

    khóa recovery_request liên quan
    khóa token_record liên quan
    lấy authoritative_now từ nguồn thời gian đã chọn

    xác thực chủ thể gọi lệnh và ràng buộc request/token/account
    đọc kết quả commandId nếu đây là retry đã được xử lý

    nếu token không còn PENDING:
        chỉ trả kết quả cũ khi đúng cùng lệnh đã hoàn tất
        không tạo lần kích hoạt mới

    kiểm tra request còn mở
    kiểm tra bằng chứng, phiên bản chính sách và điều kiện rủi ro
    kiểm tra activation_deadline và expires_at
    kiểm tra phiên bản khôi phục chưa bị thay thế

    chuyển token sang ACTIVE
    ghi activated_at và tăng state_version
    ghi kết quả commandId
    ghi RecoveryTokenActivated vào outbox trong cùng database

    COMMIT
```

Đây là giả mã để thể hiện ranh giới giao dịch. Khi triển khai, cần xác định cơ chế khóa hoặc cập nhật có điều kiện phù hợp với database, đồng thời quy định thứ tự khóa để hạn chế deadlock.

Nếu bằng chứng được lưu tại dịch vụ khác, một giá trị boolean đã đọc từ lâu không đủ bảo đảm nó vẫn hợp lệ. Có thể dùng một quyết định có định danh, thời hạn, phạm vi và phiên bản rõ ràng; dịch vụ kích hoạt kiểm tra các thuộc tính này theo giao thức đã thiết kế. Không giữ một giao dịch database mở lâu chỉ để chờ hàng loạt cuộc gọi mạng thiếu giới hạn.

### Hai lệnh kích hoạt chạy đồng thời

Giả sử lệnh A và B cùng đọc thấy `PENDING`. Với khóa phù hợp hoặc compare-and-set, chỉ một lệnh được ghi chuyển trạng thái hợp lệ. Lệnh còn lại đọc kết quả mới và xử lý theo quy tắc retry hoặc xung đột.

Không triển khai bằng hai bước độc lập:

```text
if token.state == PENDING:
    token.state = ACTIVE
    publish_event()
```

Nếu kiểm tra, ghi trạng thái và ghi sự kiện không được phối hợp, hai tiến trình có thể tạo hai kết quả kích hoạt hoặc trạng thái đã lưu nhưng sự kiện bị mất.

### Chính sách chỉ giữ một quyền hiện hành

Nếu hệ thống cho phép tối đa một quyền đang hoạt động cho một nhóm tài khoản và mục đích, cần tuần tự hóa quyết định ở phạm vi đó, chẳng hạn khóa bản ghi yêu cầu hiện hành hoặc dùng ràng buộc dữ liệu phù hợp. Chỉ khóa từng token riêng lẻ không ngăn hai token khác nhau cùng được kích hoạt.

Việc nhận một yêu cầu quên mật khẩu công khai cũng không nên tự động vô hiệu hóa mọi quyền hoặc phiên hợp lệ của người dùng. Kẻ tấn công có thể lặp yêu cầu để gây gián đoạn. Cần quyết định rõ khi nào yêu cầu mới thực sự thay thế quyền cũ, kết hợp giới hạn tần suất và bằng chứng mà chính sách yêu cầu.

## 7. Sự kiện nên chứa gì?

Sự kiện phục vụ audit, thông báo và cập nhật các góc nhìn phụ trợ. Một schema minh họa:

```json
{
  "eventId": "evt_demo_0081",
  "eventType": "RecoveryTokenActivated",
  "schemaVersion": 1,
  "tokenRecordId": "rt_demo_0042",
  "recoveryRequestId": "rr_demo_0018",
  "accountRef": "acct_internal_027",
  "purpose": "RESET_PASSWORD",
  "activatedAt": "2026-01-01T03:03:00Z",
  "expiresAt": "2026-01-01T03:08:00Z",
  "stateVersion": 2,
  "policyDecisionRef": "pd_demo_0015",
  "correlationId": "corr_demo_0036"
}
```

Các ID trong ví dụ là dữ liệu giả. `tokenRecordId` chỉ là định danh bản ghi, không phải bí mật có thể đổi mật khẩu. `accountRef` vẫn có thể là dữ liệu liên quan cá nhân; cần giới hạn quyền đọc, mục đích sử dụng và thời gian lưu.

Không đưa raw token, mã OTP, cookie, URL khôi phục chứa bí mật hoặc thông tin xác minh danh tính đầy đủ vào sự kiện. OWASP hướng dẫn loại trừ hoặc xử lý phù hợp các dữ liệu nhạy cảm như access token, mật khẩu và định danh phiên khi ghi log. Xem [OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Chỉ sự kiện có nguồn hợp lệ mới được consumer xử lý. Quyền publish vào topic, xác thực dịch vụ, kiểm soát truy cập broker và kiểm tra schema là những phần của ranh giới tin cậy. Một trường `eventType` đúng tên trong JSON không chứng minh sự kiện do dịch vụ khôi phục phát ra.

Sự kiện `RecoveryTokenActivated` thông báo một chuyển trạng thái đã commit. Nó khác lệnh `ActivateRecoveryToken`, vốn có thể bị từ chối. Không để một consumer nhận thông báo rồi tự ghi `ACTIVE` vào kho trạng thái chuẩn.

## 8. Outbox, retry và sự kiện đến sai thứ tự

**Transactional outbox** là một lựa chọn cho việc lưu thay đổi trạng thái và ý định phát sự kiện trong cùng giao dịch database. Một tiến trình riêng đọc outbox và gửi sự kiện sau commit.

Luồng có thể gặp:

```text
database commit ACTIVE + outbox thành công
publisher gửi event thành công
publisher mất kết nối trước khi ghi nhận đã gửi
publisher gửi lại cùng eventId
```

Consumer phải xử lý được việc nhận trùng. Ví dụ, dịch vụ thông báo lưu `eventId` đã xử lý bằng cơ chế nguyên tử cùng với tác dụng phụ nội bộ của nó. Nếu tác dụng phụ là gọi nhà cung cấp ngoài, cần cơ chế idempotency hoặc đối soát riêng phù hợp; chỉ thêm một bảng `processed_events` không tự bảo đảm email bên ngoài được gửi đúng một lần.

Một tình huống khác:

```text
version 2: token ACTIVE
version 3: token REVOKED
consumer nhận version 3 trước version 2
```

Góc nhìn phụ trợ không được để version 2 ghi đè version 3. Có thể dùng kiểm tra phiên bản, tuần tự hóa theo aggregate hoặc đọc lại trạng thái chuẩn khi cần. Cách cụ thể phụ thuộc mô hình phân phối message.

Tuy nhiên, giữ đúng thứ tự một projection không loại bỏ mọi độ trễ. Một projection chưa nhận được sự kiện thu hồi vẫn có thể đang hiển thị `ACTIVE`. Đường sử dụng token cần đọc trạng thái đủ mạnh hoặc có cơ chế đồng bộ thu hồi đáp ứng yêu cầu an toàn của hệ thống.

Outbox giúp phối hợp database với việc phát sự kiện. Nó không tự giải quyết giao dịch xuyên dịch vụ, không bảo đảm broker chỉ giao một lần và không thay thế quyết định cấp quyền.

## 9. Không lấy việc mở email làm bằng chứng kích hoạt

Liên kết khôi phục có thể được truy cập bởi bộ quét chống phishing, trình xem trước tin nhắn hoặc cơ chế prefetch. Vì vậy, một request GET đến liên kết chưa đủ để kết luận chủ tài khoản đã chủ động thực hiện khôi phục.

Thiết kế trang đích có thể:

1. Nhận liên kết qua HTTPS và hiển thị giao diện phù hợp.
2. Hạn chế lộ token qua log truy cập, referrer, analytics và tài nguyên bên thứ ba.
3. Yêu cầu một thao tác chủ động trước khi thay đổi trạng thái nhạy cảm.
4. Gửi thao tác thay đổi bằng POST với các biện pháp bảo vệ yêu cầu phù hợp.
5. Máy chủ xác minh token và điều kiện chính sách trước khi thực hiện.

POST giúp thể hiện ý định thay đổi trạng thái trong giao thức ứng dụng; bản thân phương thức POST không chứng minh danh tính và không thay thế kiểm tra CSRF, Origin hoặc ràng buộc phiên khi các cơ chế đó áp dụng.

Nếu hệ thống đổi token từ URL sang một phiên khôi phục giới hạn, phải định nghĩa rõ việc trao đổi có tiêu thụ token gốc hay không. Phiên thay thế cần đủ bảo vệ tương ứng, thời hạn và phạm vi hẹp; không dùng việc trao đổi để âm thầm cấp quyền đăng nhập đầy đủ.

Với mô hình kích hoạt ngay khi phát hành, việc mở liên kết chỉ là một lần token được trình diện. Không cần phát thêm `Activated` mỗi lần trang được tải lại.

## 10. Kích hoạt không hoàn tất việc khôi phục

Sau khi token có hiệu lực, endpoint thực hiện thao tác đích vẫn phải kiểm tra quyền dùng một lần tại thời điểm thay đổi dữ liệu.

Trong trường hợp mật khẩu và token cùng nằm trong một database, có thể tổ chức:

```text
BEGIN TRANSACTION
    khóa token và tài khoản theo thứ tự đã quy định
    kiểm tra token ACTIVE, còn hạn, đúng mục đích và yêu cầu hiện hành
    kiểm tra bí mật token do người dùng trình bày
    cập nhật mật khẩu mới đã được băm bằng cơ chế của hệ thống
    chuyển token sang CONSUMED
    vô hiệu hóa các quyền khôi phục liên quan theo chính sách
    ghi ý định xử lý phiên và thông báo cần thiết
COMMIT
```

Nếu cập nhật mật khẩu thất bại, giao dịch rollback để tránh vừa mất token vừa không đổi được mật khẩu. Nếu hai request cùng dùng token, cơ chế tuần tự hóa phải bảo đảm chỉ một lần được thực hiện thành công.

Khi dữ liệu nằm ở nhiều dịch vụ, cần thiết kế riêng cơ chế phối hợp và khôi phục lỗi. Ghi một sự kiện `Consumed` lên broker không tự biến nhiều thay đổi phân tán thành một giao dịch nguyên tử.

Việc xử lý session cũng cần một chính sách cụ thể. Nếu đã yêu cầu thu hồi phiên, các endpoint dùng phiên phải thực thi cơ chế đó, chẳng hạn kiểm tra phiên bản phiên hoặc trạng thái phiên đủ mới. Một thông báo thu hồi còn nằm trên hàng đợi chưa chứng minh mọi phiên đã mất hiệu lực.

Đối với mất MFA, passkey hoặc thiết bị xác thực, token kích hoạt chỉ mở quyền thực hiện bước đã được phê duyệt. Các bước đăng ký yếu tố thay thế, xử lý yếu tố bị lộ và cấp phiên sau cùng vẫn phải tuân theo chính sách của loại khôi phục đó.

## 11. Các tình huống cần thiết kế kết quả rõ ràng

| Tình huống | Kết quả mong muốn trong mô hình |
| --- | --- |
| Điều kiện kích hoạt chưa đạt | Giữ `PENDING` hoặc từ chối theo chính sách; không cấp quyền sử dụng |
| Token đã hết hạn trước lúc xử lý lệnh | Không kích hoạt, dù lệnh được gửi trước hạn |
| Retry cùng lệnh kích hoạt đã thành công | Trả kết quả tương ứng, không gia hạn hay phát sinh lần cấp quyền mới |
| Token bị thu hồi trước khi message kích hoạt đến consumer | Không hồi sinh token |
| Tài khoản hoàn tất một yêu cầu khôi phục khác | Quyền cũ bị từ chối nếu chính sách đã đánh dấu thay thế |
| Bộ quét email tải liên kết | Không tự đổi mật khẩu hoặc tiêu thụ quyền khôi phục cuối cùng |
| Broker tạm ngừng sau commit | Outbox giữ việc cần phát; trạng thái chuẩn vẫn nhất quán |
| Có sự kiện giả mạo đúng schema | Từ chối nguồn không được phép; schema không thay thế xác thực |
| Cache còn `ACTIVE` sau thu hồi | Không dùng cache lỗi thời làm căn cứ duy nhất để chấp nhận token |
| Token đặt lại mật khẩu được gửi đến API thay MFA | Từ chối do sai mục đích |
| Người dùng bấm gửi lại nhiều lần | Giới hạn lạm dụng, không tạo chuỗi gia hạn vô hạn hoặc khóa người dùng |

Các kết quả này nên được định nghĩa trước khi triển khai để giao diện, dịch vụ khôi phục, kho dữ liệu và consumer hiểu cùng một hợp đồng.

## 12. Dấu vết vận hành và quyết định thiết kế

Audit kích hoạt cần đủ thông tin để truy vết: yêu cầu nào, bản ghi token nào, mục đích gì, quyết định chính sách nào, thời điểm nào, phiên bản trạng thái bao nhiêu và kết quả thành công hay từ chối. Dữ liệu ghi nhận phải phù hợp quyền truy cập và không chứa bí mật dùng để khôi phục.

Một số tín hiệu hữu ích:

- Nhiều lần kích hoạt bị từ chối trên cùng yêu cầu.
- Tăng mạnh số token chờ mà không được kích hoạt.
- Outbox tồn đọng làm thông báo đến muộn.
- Lệnh kích hoạt xuất hiện sau khi đã thu hồi hoặc hoàn tất.
- Chênh lệch lớn giữa thời điểm sự kiện xảy ra và thời điểm consumer xử lý.
- Nhiều yêu cầu khôi phục liên tiếp hướng vào cùng tài khoản hoặc kênh liên hệ.

Mỗi tín hiệu cần được diễn giải trong bối cảnh. Một token không được kích hoạt có thể do người dùng bỏ dở; một sự kiện giao trùng có thể là retry bình thường. Không tự coi mọi bất thường là bằng chứng tài khoản bị chiếm đoạt.

Khi quyết định có cần token activation event, hãy xác định rõ: **quyền nào bắt đầu có hiệu lực, điều kiện nào cho phép điều đó, giao dịch nào ghi nhận sự thật, và thành phần nào được phép sử dụng sự kiện**. Với một luồng đơn giản, kích hoạt ngay khi phát hành có thể đủ. Với một luồng nhiều bước, trạng thái chờ và sự kiện kích hoạt giúp thể hiện ranh giới cấp quyền, miễn là các ràng buộc được thực thi tại máy chủ.