# Password reset: ghi log và kiểm toán quá trình đặt lại mật khẩu

## 1. Vì sao đặt lại mật khẩu cần một dấu vết riêng?

**Password reset** là quá trình thiết lập mật khẩu mới thông qua một cơ chế khôi phục được chấp nhận, thường vì người dùng không còn sử dụng được mật khẩu hiện tại. Nó khác với đổi mật khẩu khi người dùng đã xác thực và đang chủ động cập nhật thông tin đăng nhập.

Luồng đặt lại mật khẩu có thể trở thành một đường tiếp quản tài khoản nếu bằng chứng khôi phục hoặc quyền hỗ trợ bị lạm dụng. Vì vậy, hệ thống IAM cần ghi nhận đủ sự kiện để trả lời:

- Ai hoặc nguồn nào bắt đầu yêu cầu?
- Tài khoản nào được nhắm đến và khi nào hệ thống xác định được tài khoản đó?
- Bằng chứng khôi phục nào đã được kiểm tra?
- Mật khẩu có thực sự được cập nhật không?
- Các phiên và token liên quan đã được xử lý đến đâu?
- Có nhân viên hỗ trợ hoặc công cụ quản trị tham gia không?

Ví dụ xuyên suốt: có một yêu cầu đặt lại mật khẩu cho tài khoản của Lan. Việc nhận được request không chứng minh Lan là người gửi. Việc gửi một email cũng không chứng minh mật khẩu đã đổi. Audit cần giữ được các khác biệt này thay vì ghi một dòng chung chung “Lan reset password thành công”.

Mục tiêu là truy vết quyết định và kết quả, không phải thu thập chính mật khẩu hoặc token khôi phục.

## 2. Phân biệt các hành động gần nhau

| Hành động | Ngữ cảnh thường gặp | Điều cần ghi rõ |
| --- | --- | --- |
| Đổi mật khẩu | Người dùng có một ngữ cảnh xác thực được chấp nhận | Chủ thể đã xác thực, điều kiện bổ sung và kết quả cập nhật |
| Đặt lại mật khẩu tự phục vụ | Người dùng đi qua cơ chế khôi phục | Người yêu cầu ban đầu có thể chưa xác thực; cần ghi nhận bước xác minh |
| Hỗ trợ đặt lại mật khẩu | Nhân viên hoặc công cụ được phép hỗ trợ | Người thực hiện thật, tài khoản đích và căn cứ thẩm quyền |
| Bắt buộc đổi mật khẩu | Chính sách hoặc xử lý sự cố yêu cầu cập nhật | Ai áp dụng yêu cầu, lý do và khi nào người dùng hoàn tất |
| Thu hồi phiên sau reset | Một bước bảo vệ liên quan | Phạm vi phiên hoặc token đã thu hồi và kết quả thực tế |

Không dùng một sự kiện “password updated” để thay thế toàn bộ chuỗi trên.

Nếu tài khoản đăng nhập qua một nhà cung cấp danh tính liên kết, ứng dụng có thể không quản lý mật khẩu của tài khoản đó. Khi đó, phải ghi đúng thành phần thực hiện reset. Việc ứng dụng nhận một sự kiện từ nhà cung cấp không có nghĩa ứng dụng đã trực tiếp thay mật khẩu.

## 3. Thiết kế chuỗi sự kiện theo các mốc có ý nghĩa

Một luồng tự phục vụ có thể được mô tả như sau:

```text
Yêu cầu reset được tiếp nhận
    -> áp dụng kiểm soát và quyết định xử lý
    -> tạo cơ chế khôi phục theo chính sách
    -> chuyển thông báo đến dịch vụ gửi
    -> kiểm tra bằng chứng khi người nhận tiếp tục
    -> cập nhật mật khẩu và kết thúc hiệu lực bằng chứng
    -> xử lý phiên hoặc token theo chính sách
    -> thông báo thay đổi và kết thúc
```

Tên sự kiện dưới đây là ví dụ thiết kế, không phải schema bắt buộc:

| Sự kiện | Điều sự kiện xác nhận | Điều chưa được phép suy ra |
| --- | --- | --- |
| `PASSWORD_RESET_REQUESTED` | Hệ thống nhận một yêu cầu | Người gửi là chủ tài khoản |
| `PASSWORD_RESET_REQUEST_BLOCKED` | Một kiểm soát đã chặn xử lý yêu cầu | Đã xác định có tấn công hoặc tài khoản bị chiếm |
| `PASSWORD_RESET_CHALLENGE_CREATED` | Cơ chế khôi phục được tạo cho một thao tác | Người dùng đã nhận được hoặc sử dụng |
| `PASSWORD_RESET_NOTIFICATION_QUEUED` | Thông báo được đưa vào đường gửi | Email đã đến hộp thư |
| `PASSWORD_RESET_PROOF_REJECTED` | Bằng chứng không được chấp nhận | Mật khẩu đã bị thay đổi |
| `PASSWORD_RESET_PROOF_ACCEPTED` | Bằng chứng thỏa bước kiểm tra tương ứng | Giao dịch cập nhật mật khẩu đã thành công |
| `PASSWORD_RESET_COMPLETED` | Mật khẩu đã được cập nhật theo trạng thái có thẩm quyền | Mọi phiên tại mọi ứng dụng đã bị thu hồi |
| `PASSWORD_RESET_SESSION_REVOCATION_RESULT` | Kết quả xử lý một phạm vi phiên hoặc token | Các phạm vi khác cũng đã xử lý xong |

Một số hệ thống gộp các mốc thành ít sự kiện hơn. Dù chọn cách nào, tên sự kiện và ý nghĩa cần chính xác, đặc biệt ở điểm quyết định “đã hoàn tất”.

## 4. Nhận diện đúng actor, tài khoản đích và mức bằng chứng

### 4.1. Request chưa xác thực

Ở bước đầu, người gửi thường chỉ nhập email hoặc tên đăng nhập. Đây là định danh được khai báo, chưa phải danh tính đã xác minh của người thao tác.

Một sự kiện có thể biểu diễn:

```text
actor.type = anonymous
actor.id = null
target.userId = định danh nội bộ nếu đã được xác định hợp lệ
identityEvidence = chưa xác thực người yêu cầu
```

Không gán `actor.id = target.userId` chỉ vì request đề nghị reset tài khoản đó. Cách gán này làm audit trông như chính chủ tài khoản đã chủ động thực hiện mọi yêu cầu, kể cả request do người khác gửi.

### 4.2. Bằng chứng khôi phục đã được chấp nhận

Sau khi một bằng chứng khôi phục hợp lệ được sử dụng, hệ thống có thể ghi nhận mức bằng chứng tương ứng với cơ chế đó.

Điều này vẫn không chứng minh tuyệt đối người sử dụng là Lan ngoài đời thực. Người khác có thể kiểm soát hộp thư, thiết bị hoặc bằng chứng khôi phục. Audit nên mô tả điều hệ thống đã xác minh, chẳng hạn “bằng chứng reset được chấp nhận”, thay vì khẳng định quá mức về danh tính con người.

### 4.3. Nhân viên hỗ trợ thao tác

Nếu nhân viên hỗ trợ Minh thực hiện một bước quản trị cho Lan, cần phân biệt:

```text
actor.id = support-minh
target.userId = user-lan
operation = administrative_password_reset
approvalReference = tham chiếu yêu cầu hoặc phê duyệt nếu có
```

Không ghi mọi hoạt động dưới tài khoản Lan. Nếu công cụ hỗ trợ dùng một danh tính workload để gọi API, có thể cần ghi cả người vận hành và dịch vụ thực hiện.

Quyền xem audit không mặc nhiên cho phép hỗ trợ reset. Quyền hỗ trợ reset cũng không nhất thiết cho phép đọc toàn bộ lịch sử đăng nhập của mọi người dùng.

## 5. Những trường nên có trong một sự kiện

Một cấu trúc có thể gồm:

| Trường | Mục đích |
| --- | --- |
| `eventId` | Phân biệt và khử trùng một sự kiện |
| `eventType`, `schemaVersion` | Xác định ý nghĩa và cấu trúc dữ liệu |
| `occurredAt` | Thời điểm sự kiện được nguồn ghi nhận là xảy ra |
| `recordedAt` | Thời điểm hệ thống thu thập tiếp nhận hoặc lưu |
| `service`, `environment` | Xác định nguồn phát sinh |
| `actor` | Chủ thể thực hiện thật và trạng thái xác thực |
| `target` | Tài khoản hoặc đối tượng bị tác động |
| `operationId` | Liên kết các mốc của một lần reset |
| `requestId` hoặc `correlationId` | Liên kết các bước xử lý kỹ thuật |
| `result`, `reasonCode` | Kết quả và lý do có cấu trúc |
| `sourceContext` | Ngữ cảnh nguồn trong phạm vi cần thiết |
| `policyReference` | Chính sách hoặc cấu hình quyết định khi cần |

`operationId` phải là tham chiếu theo dõi riêng, không phải token bí mật hoặc một phần đủ để sử dụng thay token.

Một correlation ID do client gửi không tự là dữ liệu tin cậy. Cần giới hạn định dạng, chiều dài và cách truyền; không dùng nó để xác định người sở hữu một thao tác hoặc cấp quyền xem trạng thái.

Trong hệ thống phân tán, `occurredAt` và `recordedAt` giúp nhận biết sự kiện đến muộn. Không nên kết luận thứ tự nhân quả chỉ từ thứ tự xuất hiện trên dashboard khi đồng hồ hoặc độ trễ các nguồn khác nhau.

## 6. Ví dụ sự kiện có cấu trúc

### 6.1. Yêu cầu reset ban đầu

Ví dụ minh họa, các ID là dữ liệu giả:

```json
{
  "eventId": "evt-reset-101",
  "schemaVersion": 1,
  "eventType": "PASSWORD_RESET_REQUESTED",
  "service": "identity-service",
  "environment": "production",
  "operationId": "reset-op-251",
  "requestId": "req-901",
  "actor": {
    "type": "anonymous",
    "id": null,
    "authenticated": false
  },
  "target": {
    "type": "user",
    "userId": "user-lan"
  },
  "result": "RECEIVED",
  "sourceContext": {
    "sourceIp": "192.0.2.40",
    "clientCategory": "web"
  }
}
```

Việc có `target.userId` trong ví dụ giả định nguồn phát đã xác định được tài khoản từ dữ liệu có thẩm quyền. Với đầu vào chưa được đối chiếu hoặc không tìm được tài khoản, không tự tạo một user ID hoặc gán tài khoản dựa trên dữ liệu không được xác minh.

Địa chỉ IP là ngữ cảnh kỹ thuật, không phải định danh chắc chắn của người thực hiện. Nhiều người có thể dùng chung một địa chỉ; thông tin proxy cũng cần được xử lý theo đường tin cậy của hệ thống.

### 6.2. Hoàn tất cập nhật mật khẩu

```json
{
  "eventId": "evt-reset-108",
  "schemaVersion": 1,
  "eventType": "PASSWORD_RESET_COMPLETED",
  "service": "identity-service",
  "environment": "production",
  "operationId": "reset-op-251",
  "requestId": "req-908",
  "actor": {
    "type": "recovery-flow",
    "id": null,
    "evidence": "VALIDATED_RESET_PROOF"
  },
  "target": {
    "type": "user",
    "userId": "user-lan"
  },
  "result": "SUCCESS",
  "credentialUpdate": {
    "type": "password",
    "committed": true
  },
  "sessionRevocation": {
    "state": "PENDING",
    "scope": "configured-application-sessions"
  }
}
```

Ví dụ cố ý không đánh dấu toàn bộ quy trình bảo vệ đã xong. Mật khẩu đã cập nhật, nhưng việc thu hồi phiên còn chờ kết quả riêng.

Nếu bước reset không tự tạo phiên đăng nhập mới, audit cũng không được ngầm coi đây là một sự kiện đăng nhập thành công. Nếu có cấp phiên mới theo thiết kế, cần ghi nhận sự kiện cấp phiên riêng cùng căn cứ xác thực phù hợp.

## 7. Tuyệt đối tránh đưa bí mật vào log

Những dữ liệu không nên được đưa vào audit reset gồm:

- Mật khẩu mới hoặc mật khẩu xác nhận.
- Giá trị băm mật khẩu và dữ liệu kiểm chứng không cần cho audit.
- Token reset, mã dùng một lần hoặc mã khôi phục.
- Giá trị kiểm chứng token được lưu trong kho xác thực.
- URL đầy đủ chứa token trong query, path hoặc fragment.
- Cookie phiên, access token, refresh token hoặc header xác thực.
- Toàn bộ nội dung email khôi phục nếu chứa bí mật.
- Request body hoặc response body chưa được chọn lọc.

Việc chỉ che một phần bí mật chưa chắc làm dữ liệu an toàn. Audit thường chỉ cần ID thao tác, ID thông tin xác thực hoặc định danh phiên bản không mang khả năng sử dụng credential.

Cần xét mọi lớp ghi log, không chỉ mã ứng dụng:

- Gateway và reverse proxy.
- Access log của máy chủ.
- Tracing và công cụ theo dõi lỗi.
- Log của client tích hợp.
- Hệ thống gửi email.
- Công cụ hỗ trợ hoặc ảnh chụp màn hình.
- Bản ghi chẩn đoán khi có exception.

Nếu ứng dụng lọc token khỏi audit nhưng gateway vẫn ghi toàn bộ URL reset, bí mật vẫn bị thu thập.

Một hướng triển khai tốt là chọn các trường được phép ghi theo schema, thay vì ghi toàn bộ đối tượng request rồi cố xóa một vài trường được biết là nhạy cảm.

## 8. Giữ riêng tư và tránh lộ sự tồn tại của tài khoản

### 8.1. Phản hồi công khai và audit nội bộ có mục đích khác nhau

Luồng reset thường cần tránh trở thành công cụ dò tài khoản. Nội dung phản hồi, luồng xử lý và các tín hiệu có thể quan sát cần được xem xét theo chính sách của sản phẩm.

Một phản hồi chung cho client không có nghĩa mọi chi tiết nội bộ cũng phải bị xóa khỏi audit. Đội có thẩm quyền có thể cần phân biệt yêu cầu được xử lý, bị giới hạn hoặc không có tài khoản phù hợp.

Nhưng thông tin phân biệt đó phải được bảo vệ, không xuất hiện qua endpoint trạng thái công khai, notification không phù hợp hoặc dashboard mà mọi người đều được xem.

### 8.2. Hạn chế định danh cá nhân không cần thiết

Nếu đã có user ID nội bộ, audit có thể không cần ghi nguyên email hoặc số điện thoại ở mỗi sự kiện.

Với yêu cầu chưa xác định được tài khoản, việc cần lưu định danh được nhập phải được đánh giá theo mục đích phát hiện lạm dụng và chính sách riêng tư.

Nếu dùng một giá trị đối chiếu giả danh, cần hiểu rằng băm email theo cách đơn giản không bảo đảm ẩn danh: miền giá trị có thể đoán được. Một cơ chế đối chiếu có khóa được quản lý có thể phù hợp hơn trong một số thiết kế, nhưng vẫn là dữ liệu cần kiểm soát và có vòng đời.

Không thu thập nội dung đầu vào tùy ý để “phòng khi cần”. Dữ liệu reset có thể trở thành một nguồn thông tin cá nhân nhạy cảm nếu lưu quá rộng hoặc quá lâu.

### 8.3. Chống chèn nội dung vào log

Tên tài khoản hoặc user agent là đầu vào không đáng tin cậy. Nó có thể chứa ký tự điều khiển, nội dung dài hoặc chuỗi cố tạo một dòng log giả.

Cần dùng ghi log có cấu trúc, giới hạn độ dài, chuẩn hóa hoặc mã hóa thích hợp cho kênh hiển thị. Không nối trực tiếp đầu vào vào một thông điệp có hình thức như sự kiện quản trị chính thức.

## 9. Ghi “hoàn tất” đúng thời điểm

### 9.1. Không ghi thành công trước khi cập nhật bền vững

Một luồng sai:

```text
ghi audit PASSWORD_RESET_COMPLETED
cập nhật mật khẩu
giao dịch cập nhật thất bại
```

Audit lúc này khẳng định một thay đổi chưa thực sự diễn ra.

Kết quả hoàn tất phải dựa trên trạng thái có thẩm quyền của thao tác cập nhật. Việc kiểm tra token thành công hoặc vượt qua một bước trong giao diện chưa đủ.

### 9.2. Phối hợp cập nhật, tiêu thụ bằng chứng và audit

Nếu dữ liệu liên quan nằm trong cùng một cơ sở dữ liệu có giao dịch phù hợp, có thể phối hợp theo hướng:

```text
bắt đầu giao dịch
    xác nhận bằng chứng reset còn hợp lệ cho tài khoản đích
    cập nhật giá trị kiểm chứng mật khẩu
    kết thúc khả năng sử dụng bằng chứng theo chính sách
    ghi sự kiện hoàn tất vào vùng lưu bền vững cho audit
commit

sau commit
    chuyển sự kiện audit đến hệ thống thu thập
    xử lý thu hồi phiên theo thiết kế
    lên lịch thông báo thay đổi
```

Đây là mô hình minh họa. Nếu các thành phần nằm ở nhiều hệ thống, cần một quy trình có trạng thái bền vững và đối soát, không giả định có một giao dịch bao trùm mọi dịch vụ.

Một vùng lưu sự kiện bền vững cùng giao dịch có thể giúp tránh tình trạng mật khẩu đã đổi nhưng tiến trình dừng trước khi sự kiện được gửi. Bên thu thập cần chịu được việc nhận lại cùng sự kiện.

### 9.3. Không đánh đồng audit với thông báo

Gửi email báo mật khẩu đã đổi là một tác vụ riêng. Nếu email gửi lỗi, mật khẩu có thể vẫn đã cập nhật thành công.

Ngược lại, một email được xếp hàng hoặc nhà cung cấp thông báo “đã chuyển” không chứng minh người dùng đã đọc hoặc kiểm soát địa chỉ nhận.

Cần ghi đúng mốc: đã xếp hàng, đã chuyển cho nhà cung cấp, có kết quả chuyển phát hoặc gửi thất bại. Không gọi tất cả là “người dùng đã được xác minh”.

## 10. Phiên và token sau khi reset

Đổi mật khẩu không mặc nhiên làm mọi phiên và token mất hiệu lực ngay lập tức. Hành vi phụ thuộc vào thiết kế của kho phiên, token, ứng dụng và nhà cung cấp danh tính.

Audit cần thể hiện phạm vi xử lý thực tế, chẳng hạn:

```text
operationId = reset-op-251
revocationScope = application-sessions
requestedCount = số phiên xác định trong phạm vi
result = COMPLETED hoặc PARTIAL hoặc FAILED
```

Nếu hệ thống gửi yêu cầu thu hồi đến một ứng dụng khác, cần phân biệt “đã gửi yêu cầu” với “đã xác nhận thu hồi”.

Một token tự chứa hoặc một ứng dụng có phiên riêng có thể có khoảng trễ hoặc cơ chế thu hồi khác. Không ghi `all_access_revoked=true` khi mới chỉ xóa một phiên tại identity service.

Khi điều tra, cần liên kết:

- Sự kiện reset hoàn tất.
- Sự kiện thu hồi phiên hoặc refresh token liên quan.
- Các lần đăng nhập mới sau reset.
- Các hoạt động đặc quyền hoặc truy cập nhạy cảm tiếp diễn.

Những liên kết này giúp phát hiện trường hợp credential đã đổi nhưng một phiên bị chiếm đoạt vẫn hoạt động.

## 11. Tương quan sự kiện và phát hiện hành vi bất thường

Các mẫu đáng xem xét có thể gồm:

| Mẫu quan sát | Câu hỏi điều tra |
| --- | --- |
| Nhiều yêu cầu nhắm đến một tài khoản | Có lạm dụng gửi thông báo, dò luồng hoặc người dùng gặp khó khăn không? |
| Một nguồn gửi yêu cầu cho nhiều tài khoản | Có hoạt động tự động hóa bất thường không? |
| Nhiều lần bằng chứng bị từ chối | Là token hết hạn, retry sai, lỗi client hay thử dùng trái phép? |
| Bằng chứng đã kết thúc hiệu lực bị dùng lại | Có retry hợp lệ cần giải thích hay dấu hiệu bị sao chép? |
| Reset hoàn tất rồi đăng nhập từ ngữ cảnh khác thường | Có cần kiểm tra việc tiếp quản tài khoản không? |
| Reset tài khoản đặc quyền qua công cụ hỗ trợ | Ai thao tác, có đúng thẩm quyền và quy trình không? |
| Thu hồi phiên thất bại sau reset | Còn đường truy cập nào cần xử lý? |
| Có thay đổi mật khẩu nhưng không có sự kiện audit tương ứng | Có mất sự kiện, đường cập nhật bỏ qua audit hoặc nguồn khác không? |

Một mẫu không tự chứng minh có tấn công. Ví dụ, nhiều người sau cùng một proxy có thể dùng chung địa chỉ IP; việc dùng lại một request có thể do retry sau khi mất response.

Cảnh báo nên đi cùng ngữ cảnh, khả năng đối chiếu và mức chắc chắn. Không tự khóa hàng loạt tài khoản chỉ vì một hệ thống gửi email hoặc dịch vụ xác minh bị lỗi.

Khi ghi lý do từ chối nội bộ, có thể phân biệt `EXPIRED`, `ALREADY_USED`, `INVALID_PROOF` hoặc `DEPENDENCY_UNAVAILABLE` theo khả năng xác minh thật. Không đoán loại lỗi từ một exception chung rồi ghi sai nguyên nhân.

## 12. Bảo vệ chính hệ thống audit

Audit reset có thể tiết lộ tài khoản, lịch sử khôi phục và hoạt động hỗ trợ. Cần bảo vệ nó như một nguồn dữ liệu nhạy cảm.

Các kiểm soát cần xét:

- Tách quyền phát sinh sự kiện khỏi quyền sửa hoặc xóa dữ liệu audit.
- Giới hạn quyền truy vấn theo trách nhiệm, tenant và mục đích.
- Ghi nhận các lượt truy vấn hoặc xuất audit nhạy cảm khi cần.
- Bảo vệ tính toàn vẹn và khả năng phát hiện thay đổi theo thiết kế.
- Xác định thời gian lưu phù hợp với mục đích và chính sách áp dụng.
- Kiểm soát quyền xem dữ liệu giả danh và khóa dùng để đối chiếu.
- Có quy trình lưu giữ phục vụ điều tra và kết thúc lưu giữ theo thẩm quyền.

Không đặt ra một thời gian lưu duy nhất cho mọi tổ chức nếu chưa có yêu cầu cụ thể. Nhu cầu điều tra, hợp đồng, riêng tư và khả năng vận hành có thể khác nhau.

Một tài khoản hỗ trợ chỉ cần xem trạng thái gửi thông báo có thể không cần đọc toàn bộ nguồn IP hoặc lịch sử reset của mọi tenant.

## 13. Kiểm thử chất lượng dấu vết reset

| Tình huống | Bằng chứng cần kiểm tra |
| --- | --- |
| Người chưa đăng nhập gửi yêu cầu | Actor không bị ghi thành chủ tài khoản đã xác thực |
| Yêu cầu không đối chiếu được tài khoản | Không tạo user ID giả hoặc lộ thông tin qua giao diện công khai |
| Token hết hạn, sai hoặc đã dùng | Lý do được ghi đúng mức có thể xác minh; mật khẩu không đổi |
| Bằng chứng hợp lệ nhưng cập nhật giao dịch lỗi | Không xuất hiện kết quả hoàn tất sai |
| Cập nhật thành công rồi tiến trình dừng | Có khả năng khôi phục việc phát audit từ trạng thái bền vững |
| Một sự kiện được gửi lại | Không bị hiểu thành hai lần đổi mật khẩu độc lập |
| Hai request dùng cùng bằng chứng chạy đồng thời | Dấu vết phản ánh kết quả xử lý thật và không có thành công ngoài chính sách |
| Gửi thông báo thất bại | Không làm sai kết quả cập nhật mật khẩu |
| Thu hồi phiên chỉ hoàn tất một phần | Không khẳng định mọi phiên đã bị kết thúc |
| Nhân viên hỗ trợ đặt lại cho người dùng | Actor thật và tài khoản đích được giữ riêng |
| Input chứa ký tự điều khiển hoặc chuỗi dài | Không tạo dòng log giả hoặc phá định dạng sự kiện |
| Kiểm tra gateway, tracing và lỗi ứng dụng | Không có mật khẩu, token hay URL chứa bí mật |
| Một tenant truy vấn audit của tenant khác | Không nhận dữ liệu ngoài phạm vi |
| Sự kiện đến muộn hoặc sai thứ tự nhận | Có đủ ID và thông tin thời gian để đối soát |

Kiểm thử cần theo cả đường thành công lẫn đường lỗi. Một chuỗi audit đầy đủ trong điều kiện bình thường chưa chứng minh hệ thống vẫn ghi đúng khi giao dịch rollback, hệ thống gửi thư lỗi hoặc tiến trình bị ngắt.

## 14. Đọc lại tình huống của Lan

Một yêu cầu reset cho Lan xuất hiện từ một nguồn chưa xác thực. Hệ thống ghi nhận yêu cầu với actor chưa xác minh và liên kết nó bằng `operationId` do server quản lý.

Khi bằng chứng khôi phục được sử dụng, hệ thống ghi nhận kết quả kiểm tra nhưng chỉ phát sự kiện hoàn tất khi việc cập nhật mật khẩu đã được xác nhận bền vững. Sự kiện không chứa mật khẩu hoặc token.

Các bước thu hồi phiên và gửi thông báo được ghi theo kết quả riêng. Nếu thu hồi một ứng dụng thất bại, audit vẫn cho thấy mật khẩu đã đổi và phạm vi truy cập nào còn cần xử lý.

Khi điều tra, người có thẩm quyền có thể nối chuỗi từ yêu cầu ban đầu đến các lần đăng nhập tiếp theo, đồng thời phân biệt điều hệ thống đã xác minh với điều chỉ được khai báo. Đó là giá trị của audit password reset: đủ chính xác để giải thích sự kiện mà không biến log thành kho bí mật khôi phục tài khoản.
