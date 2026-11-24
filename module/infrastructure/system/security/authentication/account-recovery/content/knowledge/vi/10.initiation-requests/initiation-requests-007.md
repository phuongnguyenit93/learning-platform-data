# Recovery request replay handling

Một yêu cầu khôi phục tài khoản có thể đến máy chủ nhiều lần dù người dùng chỉ nhấn nút một lần. Trình duyệt gửi lại sau khi mất kết nối, ứng dụng di động retry vì timeout, proxy thử lại, hoặc hàng đợi chuyển cùng một thông điệp cho hai lần xử lý. Kẻ tấn công cũng có thể chủ động phát lại request để làm ngập email, tạo nhiều token hoặc liên tục làm mất hiệu lực liên kết mà nạn nhân vừa nhận.

Bài học thuộc chương **Initiation Requests** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`. Trọng tâm là xử lý phát lại ở bước khởi tạo recovery cho trường hợp mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Thiết kế cần cho phép retry hợp lệ, giới hạn tác dụng phụ và giữ nguyên yêu cầu xác minh danh tính trước khi thay đổi thông tin bảo mật.

Sau bài học, bạn có thể:

- Phân biệt retry, idempotency, chống lạm dụng và chống sử dụng lại token.
- Xây dựng ranh giới giao dịch để request trùng không tạo thêm challenge hoặc lệnh gửi.
- Xử lý race condition, hàng đợi giao lại và lỗi không biết chắc nhà cung cấp đã gửi hay chưa.
- Thiết kế thời hạn lưu, chính sách gửi lại và phản hồi công khai không làm lộ tài khoản.

## 1. Phát lại ở bước khởi tạo là gì?

Giả sử ứng dụng gửi một request minh họa:

```http
POST /account-recovery/requests HTTP/1.1
Content-Type: application/json
Idempotency-Key: 4f2c8d46-84ec-4dd3-82ce-4b84f54ee243

{
  "identifierType": "EMAIL",
  "identifier": "lan@example.com",
  "purpose": "PASSWORD_RESET"
}
```

Máy chủ lưu yêu cầu và tạo công việc gửi email, nhưng kết nối đứt trước khi ứng dụng nhận phản hồi. Ứng dụng không biết request thất bại hay chỉ mất phản hồi. Nếu mỗi lần gọi đều tạo token và gửi email mới, một thao tác có thể sinh nhiều tác dụng phụ.

Các dạng lặp cần xử lý khác nhau:

| Dạng lặp | Ví dụ | Cơ chế chính |
|---|---|---|
| Cùng một thao tác được gửi lại | Retry cùng key và cùng nội dung | Idempotency trong phạm vi được xác định |
| Nhiều request mới cùng nhắm một tài khoản | Mỗi lần dùng key khác | Giới hạn theo tài khoản, kênh và chính sách challenge đang hoạt động |
| Hai request đến đồng thời | Hai instance cùng đọc trạng thái chưa tồn tại | Unique constraint, khóa hoặc cập nhật có điều kiện |
| Cùng một sự kiện được hàng đợi giao lại | Consumer xử lý xong nhưng mất ACK | Xử lý sự kiện có tính idempotent |
| Gọi lại thao tác gửi lại hướng dẫn | Nhấn “Gửi lại” nhiều lần | Idempotency riêng và khoảng nghỉ gửi |
| Dùng lại liên kết hoặc mã đã tiêu thụ | Gửi token cũ sau khi đổi mật khẩu | Kiểm tra token một lần và chuyển trạng thái nguyên tử |

Idempotency có nghĩa là các lần thực hiện lại cùng một thao tác không tạo thêm tác dụng nghiệp vụ ngoài tác dụng đã được chấp nhận. Nó không chứng minh người gửi là chủ tài khoản. Kẻ tấn công có thể tạo key mới, đổi trình duyệt hoặc bỏ cookie, nên idempotency không thay thế rate limit và đánh giá rủi ro.

Chống phát lại request khởi tạo cũng không tự bảo vệ bước dùng token. Hai bước có trạng thái và bất biến riêng.

## 2. Những bất biến cần bảo vệ

Trước khi chọn Redis, database hay thư viện retry, hãy xác định kết quả hệ thống phải giữ:

1. Trong thời hạn cam kết, cùng một thao tác hợp lệ chỉ tạo tối đa một ý định khởi tạo bền vững.
2. Cùng key nhưng khác nội dung không được âm thầm trở thành một thao tác mới.
3. Request trùng không tự tạo challenge mới, gia hạn challenge cũ hoặc đặt lại số lần thử.
4. Request mới dùng key khác vẫn chịu giới hạn theo tài khoản và kênh đã xác minh.
5. Bước khởi tạo không đổi mật khẩu, xóa MFA, đăng ký passkey mới hoặc thu hồi session của người dùng.
6. Thông điệp khôi phục chỉ gửi đến kênh đủ điều kiện trong hồ sơ, không đến địa chỉ do request tùy ý cung cấp.
7. Phản hồi công khai không xác nhận tài khoản có tồn tại, đã có challenge hay đã gửi thành công.
8. Mọi quyền thực hiện hành động nhạy cảm vẫn cần bằng chứng theo mục đích và mức rủi ro.

Một request có thể được ghi nhận thành công nhưng bị chính sách nội bộ ngăn gửi. Vì vậy, “đã tiếp nhận” không đồng nghĩa “email chắc chắn đã đến” hoặc “người gửi đã được xác minh”.

## 3. Thiết kế idempotency key và phạm vi sử dụng

### 3.1. Key đại diện cho một thao tác

Client tạo một key khó đoán cho một lần người dùng chủ động bắt đầu recovery và giữ nguyên key khi retry thao tác đó. Khi người dùng chủ động thực hiện một thao tác mới, client có thể tạo key mới, nhưng máy chủ vẫn áp dụng chính sách chống lạm dụng độc lập.

Máy chủ cần giới hạn độ dài, bảng ký tự và số key được lưu trên một nguồn gửi. Không nhận key tùy ý dài rồi dùng trực tiếp trong log hoặc làm tên tài nguyên.

Một phạm vi minh họa:

```text
scope = tenant_id + endpoint + server_flow_id
operation_key = scope + idempotency_key
```

`server_flow_id` có thể là mã ngẫu nhiên do máy chủ cấp cho một luồng trước đăng nhập, được bảo vệ khi truyền qua cookie hoặc cơ chế tương ứng. Nó chỉ định phạm vi thao tác, không phải bằng chứng sở hữu tài khoản.

Không tin một `tenant_id` hay flow ID tùy ý do client khai báo mà không kiểm tra. Không dùng riêng địa chỉ IP làm phạm vi: nhiều người có thể chung IP, còn một người có thể đổi IP giữa hai lần retry.

Tạo flow mới hoặc đổi key không được giúp vượt quota tài khoản. Các lớp giới hạn sau khi phân giải tài khoản phải hoạt động xuyên qua các flow đó.

### 3.2. Ràng buộc key với nội dung nghiệp vụ

Lưu fingerprint của các trường ảnh hưởng đến ý nghĩa thao tác, chẳng hạn:

- Tenant đã được máy chủ xác định.
- Loại định danh và khóa định danh theo chính sách chung của hệ thống.
- Mục đích recovery được phép.
- Lựa chọn kênh nếu API thực sự cho phép chọn trong tập kênh đã xác minh.
- Ngữ cảnh khác có thể làm thay đổi challenge hoặc thông điệp.

Dữ liệu phải được tuần tự hóa không nhập nhằng. Không nối chuỗi bằng một dấu phân cách mà không quy định escape. Không hash nguyên JSON rồi mặc định hai request cùng nghĩa phải có cùng byte: thứ tự field, khoảng trắng và cách biểu diễn định danh có thể khác nhau.

Có thể dùng HMAC trên biểu diễn chuẩn của nội dung để giảm lộ định danh khi kho idempotency bị đọc. Hash thuần của một email phổ biến có thể bị đoán bằng cách thử danh sách email; HMAC cần khóa bí mật riêng và cách quản lý khóa phù hợp.

| Tình huống | Quyết định nội bộ |
|---|---|
| Chưa có key trong scope | Cố gắng tạo bản ghi thao tác bằng thao tác nguyên tử |
| Có key, fingerprint giống nhau | Dùng lại biên nhận; không tạo thêm công việc |
| Có key, fingerprint khác nhau | Từ chối áp dụng nội dung mới; không sửa thao tác cũ |
| Có key, thao tác đang xử lý | Trả biên nhận chung; giữ nguyên công việc đang chạy |
| Có key, thao tác đã hoàn tất hoặc bị chặn gửi | Không mở lại thao tác chỉ vì client retry |

Trong API recovery công khai, có thể dùng cùng phản hồi chung cho các request hợp cú pháp này, kể cả xung đột key. Chi tiết xung đột phục vụ quan sát nội bộ. Nếu chọn một mã lỗi riêng cho việc dùng key sai, lỗi đó chỉ được phụ thuộc vào hợp đồng request của người gọi, không vào trạng thái tài khoản.

Không trả token recovery trong kết quả idempotency. Biết key hoặc biên nhận không được cấp quyền xem kênh liên hệ hay lấy token.

## 4. Dữ liệu và trạng thái cần lưu

Một mô hình khái niệm gồm ba nhóm dữ liệu:

```text
RecoveryInitiation
  operation_id
  tenant_id
  scope_digest
  key_digest
  payload_fingerprint
  state
  accepted_at
  retain_until
  internal_outcome

RecoveryChallenge
  challenge_id
  account_id
  purpose
  channel_id
  channel_version
  security_version
  token_digest
  expires_at
  attempts_used
  state

OutboxEvent
  event_id
  operation_id
  event_type
  challenge_id
  generation
  encrypted_payload_reference
  delivery_state
  attempts
  next_attempt_at
```

`internal_outcome` có thể biểu thị không tìm được tài khoản, chặn vì quota, dùng lại challenge đủ điều kiện hoặc đã tạo công việc gửi. Không đưa field này vào phản hồi công khai.

Các ràng buộc quan trọng:

- Duy nhất một bản ghi theo scope và key.
- Một operation không sinh hai sự kiện khởi tạo giống nhau.
- Một lệnh gửi cụ thể có event ID và generation ổn định khi retry.
- Quyết định tạo challenge được tuần tự hóa theo tài khoản và mục đích, kể cả khi các operation dùng key khác nhau.

Để khóa quyết định khi chưa có challenge, có thể dùng một bản ghi slot ổn định theo `(account_id, purpose)`. Chỉ `SELECT ... FOR UPDATE` một tập kết quả rỗng không tự tạo ra mọi bảo đảm cần thiết trên mọi database. Cần cơ chế tạo slot duy nhất, mức cô lập hoặc primitive tương đương đã được xác định rõ.

Không cần áp dụng mọi tên bảng trong ví dụ. Điều bắt buộc là các bất biến được thực thi bằng ranh giới lưu trữ phù hợp, không chỉ bằng một câu `if` trong ứng dụng.

## 5. Chấp nhận request và xử lý đồng thời

### 5.1. Không dùng “kiểm tra rồi ghi” rời rạc

Cách làm sau có race condition:

```text
if not exists(idempotencyKey):
    createChallenge()
    sendEmail()
    saveIdempotencyKey()
```

Hai instance có thể cùng thấy key chưa tồn tại, rồi cùng tạo challenge và gửi email. Nếu tiến trình chết sau gửi nhưng trước lưu key, retry cũng gửi lại.

Một mutex trong bộ nhớ chỉ bảo vệ một process. Khóa phân tán có thời hạn cũng không thay thế trạng thái bền vững: khóa có thể hết hạn khi worker cũ vẫn đang chạy. Phần ghi nghiệp vụ vẫn cần unique constraint, kiểm tra phiên bản hoặc điều kiện cập nhật để worker cũ không ghi đè kết quả mới.

### 5.2. Ghi ý định và outbox trong cùng transaction

Một cách tổ chức là tiếp nhận request trước, rồi phân giải tài khoản trong công việc nền. Với request hợp cú pháp được chấp nhận, đường ghi biên nhận không cần phản ánh tài khoản có tồn tại hay không.

```text
acceptRecovery(input, trustedContext):
    validateBoundedRequest(input)
    enforceIngressAbuseLimits(trustedContext)
    scope = deriveScope(trustedContext)
    fingerprint = fingerprintSemanticInput(input, trustedContext)

    begin transaction
        inserted = insertInitiationIfAbsent(scope, input.key, fingerprint)

        if not inserted:
            existing = readInitiation(scope, input.key)
            if existing.fingerprint != fingerprint:
                recordInternalKeyConflict()
            commit
            return genericAcceptedResponse()

        insertOutboxEvent(
            eventId = stableEventIdForNewOperation,
            type = PROCESS_INITIATION,
            operationId = newOperationId
        )
    commit

    return genericAcceptedResponse()
```

`insertInitiationIfAbsent` phải dựa trên thao tác nguyên tử và unique constraint. Khi hai transaction cạnh tranh, nhánh đọc bản ghi hiện có phải tuân thủ hành vi khóa và mức cô lập của database; nếu gặp lỗi cạnh tranh có thể retry có giới hạn. Nó không phải phép đọc rồi ghi riêng biệt được đổi tên.

Nếu transaction rollback, cả biên nhận và sự kiện đều chưa được chấp nhận. Nếu commit xong nhưng HTTP response bị mất, lần retry đọc lại bản ghi và không thêm sự kiện.

Không cố gửi email bên trong transaction database để “gộp mọi thứ làm một”. Việc gửi qua mạng không rollback cùng database và có thể giữ khóa quá lâu. Outbox lưu bền vững ý định xử lý, sau đó dispatcher chuyển sự kiện đi với cơ chế retry.

### 5.3. Giới hạn tài khoản phải được kiểm tra sau lookup

Worker xử lý sự kiện khởi tạo cần có tính idempotent:

```text
processInitiation(operationId):
    begin transaction
        operation = lockInitiation(operationId)
        if operation.state == APPLIED:
            commit
            return

        account = resolveAccountExactly(operation)
        if account.notEligible:
            markAppliedWithSuppressedOutcome(operation)
            commit
            return

        slot = lockOrCreateRecoverySlot(account.id, operation.purpose)
        channel = selectEligibleVerifiedChannel(account.id)

        recheckSecurityVersionChannelAndRisk(account, channel, operation)

        if activeChallengeCanBeReusedWithoutSending(slot):
            markAppliedAsCoalesced(operation)
        else if cannotReserveAccountAndChannelSendBudget():
            markAppliedWithSuppressedOutcome(operation)
        else:
            challenge = createChallengeWithFixedExpiry(account, channel)
            insertUniqueDeliveryEvent(challenge, operation)
            updateRecoverySlot(slot, challenge)
            markApplied(operation)
    commit
```

Đây là mã giả về ranh giới trạng thái, chưa phải mã thư viện. Các nhánh không có kênh phù hợp, cần xác minh bổ sung hoặc phiên bản bảo mật đã thay đổi phải kết thúc hoặc chuyển sang luồng phù hợp mà không phát hành sai challenge.

Quyết định giữ chỗ quota gửi và ghi lệnh gửi phải phối hợp nguyên tử hoặc có cơ chế nhất quán tương đương. Không kiểm tra quota ở một nơi rồi cho nhiều worker cùng gửi dựa trên cùng một số dư cũ. Các bước đánh giá tốn thời gian có thể nằm ngoài transaction, nhưng điều kiện bảo mật ảnh hưởng đến phát hành phải được kiểm tra lại khi ghi.

Hai operation khác key cùng nhắm một tài khoản sẽ cạnh tranh trên slot và quota. Nhờ vậy, idempotency theo request và chính sách theo tài khoản bổ sung cho nhau.

## 6. Retry và gửi lại hướng dẫn là hai ý định khác nhau

Retry có mục tiêu biết lại kết quả của cùng thao tác. “Gửi lại hướng dẫn” là yêu cầu tạo thêm một lần gửi có chủ đích. Hai ý định này không nên dùng chung logic “mỗi request đều phát token mới”.

Một chính sách minh họa:

| Tình huống | Hành vi |
|---|---|
| Retry cùng key | Không thêm challenge hoặc lệnh gửi |
| Request mới trong khoảng nghỉ gửi | Có thể gộp vào trạng thái đang hoạt động, không gửi thêm |
| Người dùng chủ động gửi lại sau khoảng nghỉ | Xét quota và rủi ro rồi tạo một lệnh gửi mới có idempotency riêng |
| Challenge đã hết hạn | Chỉ tạo challenge mới nếu chính sách cho phép; không hồi sinh token cũ |
| Tài khoản đổi kênh hoặc thay đổi trạng thái bảo mật | Đánh giá lại điều kiện và vô hiệu hóa phù hợp |

Ví dụ, sản phẩm có thể đặt khoảng nghỉ gửi là 60 giây và token có hạn dùng 10 phút. Đây chỉ là số minh họa; thời gian thực tế phải theo rủi ro, loại kênh và khả năng vận hành.

Những quy tắc cần giữ:

- Retry không cập nhật `expires_at` của challenge đang có.
- Retry không đặt lại `attempts_used` hoặc bộ đếm đoán mã.
- Request chưa xác thực không liên tục thay token rồi làm liên kết trước đó của nạn nhân vô hiệu.
- Hết khoảng nghỉ gửi không tự chứng minh người yêu cầu là chủ tài khoản.
- Không thu hồi session hiện có chỉ vì ai đó nhập email của nạn nhân vào recovery.

Nếu chọn gửi lại cùng token, hệ thống cần cách cung cấp token đó cho dịch vụ gửi một cách an toàn. Chỉ có `token_digest` thì không thể khôi phục token gốc để gửi lại. Có thể dùng bản payload được mã hóa, giới hạn thời gian và quyền đọc, hoặc chọn chính sách phát hành khác đã được đánh giá. Không đổi sang lưu token thô chỉ để tiện resend.

Nếu chọn tạo token mới, việc thay thế token trước phải có chính sách rõ để hạn chế hành vi làm gián đoạn recovery của nạn nhân. Không biến thao tác gửi lại công khai thành nút vô hiệu hóa token liên tục.

## 7. Hàng đợi, dịch vụ gửi và giới hạn của bảo đảm một lần

Outbox giúp tránh mất ý định gửi khi database đã commit mà process chết. Nó không tự bảo đảm email hoặc SMS ngoài hệ thống chỉ được gửi đúng một lần.

Xét chuỗi sự kiện:

```text
1. Dispatcher gọi nhà cung cấp gửi email.
2. Nhà cung cấp chấp nhận và gửi email.
3. Kết nối đứt trước khi dispatcher nhận kết quả.
4. Dispatcher chưa ghi nhận SENT và thử lại.
```

Ở bước 4, hệ thống không biết chắc lần trước đã gửi hay chưa. Nếu nhà cung cấp hỗ trợ idempotency hoặc tra cứu trạng thái theo mã yêu cầu, dùng cùng mã gửi ổn định để chống trùng trong phạm vi họ cam kết. Nếu không có khả năng đó, không thể hứa tuyệt đối “email chỉ gửi đúng một lần” chỉ bằng transaction trong database của mình.

Thiết kế thực tế nên:

1. Giữ event ID và payload ổn định cho retry cùng một lệnh gửi.
2. Không tạo challenge mới khi chỉ retry delivery.
3. Ghi nhận delivery attempt và trạng thái kết quả không chắc chắn.
4. Áp dụng backoff, giới hạn số lần thử và thời hạn thử không vượt quá tính hữu ích của challenge.
5. Đối soát trạng thái với nhà cung cấp khi có thể; chuyển các lỗi kéo dài sang xử lý vận hành.
6. Kiểm tra challenge, kênh và phiên bản bảo mật trước khi gửi lại công việc còn tồn đọng.

Có thể đánh dấu worker đang xử lý bằng lease, nhưng worker mất lease không được tự do ghi đè trạng thái của worker mới. Dùng version hoặc điều kiện cập nhật cho quyền sở hữu công việc. Vẫn phải tính đến tình huống một lời gọi mạng cũ hoàn tất muộn.

Sự kiện đến muộn sau khi challenge hết hạn hoặc tài khoản đổi kênh không được khởi động lại một recovery cũ. Nếu một thông điệp đã rời hệ thống trước khi trạng thái thay đổi, bước redeem vẫn phải từ chối token không còn hợp lệ.

Mục tiêu có thể đạt được trong database là một chuyển trạng thái nghiệp vụ hợp lệ và một ý định gửi cho mỗi operation hoặc generation đã cho phép. Số thông điệp thực tế đến người nhận còn phụ thuộc khả năng chống trùng của kênh bên ngoài.

## 8. Cửa sổ phát lại, thời gian lưu và chống lạm dụng

### 8.1. Không có một TTL dùng cho mọi thứ

| Loại thời gian | Ý nghĩa |
|---|---|
| Thời hạn lưu idempotency | Khoảng thời gian cùng key còn được nhận diện là cùng thao tác |
| Hạn dùng challenge | Khoảng thời gian token còn có thể được chấp nhận |
| Khoảng nghỉ gửi | Khoảng cách tối thiểu giữa các lần gửi được phép |
| Thời hạn retry delivery | Khoảng thời gian hệ thống còn thử chuyển một thông điệp |
| Thời hạn lưu dấu xử lý sự kiện | Khoảng thời gian nhận diện sự kiện hàng đợi đã xử lý |

Thời hạn idempotency cần bao phủ cửa sổ retry mà API cam kết. Thời hạn nhận diện sự kiện cần tính cả khả năng broker giao lại hoặc vận hành phát lại dữ liệu cũ. Dọn bản ghi đang xử lý chỉ vì đã đến thời điểm TTL có thể tạo điều kiện cho cùng công việc được chấp nhận lại.

Sau khi hết thời hạn lưu và không còn dấu vết, hệ thống có thể không nhận ra cùng key đã từng được dùng. Không tuyên bố chống phát lại vô thời hạn. Khi request được coi là mới, các kiểm tra challenge đang hoạt động, quota và rủi ro vẫn phải giữ tác dụng.

Nếu cần giữ tombstone để chặn mở lại thao tác, chỉ lưu dữ liệu tối thiểu và có vòng đời rõ ràng. Không giữ email, token hay toàn bộ request vô hạn chỉ để phục vụ deduplication.

### 8.2. Timestamp và nonce có giới hạn riêng

Timestamp do client gửi không tự chứng minh request mới: kẻ tấn công có thể sửa timestamp. Chữ ký có thể bảo vệ tính toàn vẹn trong một giao thức thích hợp, nhưng request có chữ ký vẫn có thể được phát lại trong cửa sổ hợp lệ nếu không có cơ chế kiểm tra nonce hoặc trạng thái tương ứng.

Một nonce do máy chủ cấp có thể ràng buộc với flow, mục đích và hạn dùng. Việc tiêu thụ nonce cần nguyên tử nếu yêu cầu dùng một lần. Khi nonce đã tiêu thụ nhưng phản hồi bị mất, retry hợp lệ cần được ánh xạ đến biên nhận đã có; không tạo operation mới chỉ vì nonce bị dùng rồi.

Nonce của biểu mẫu recovery công khai không phải bằng chứng sở hữu tài khoản. Kẻ tấn công vẫn có thể mở flow mới để lấy nonce mới.

Sử dụng đồng hồ máy chủ hoặc thời gian của nơi lưu trữ làm căn cứ thực thi thời hạn. Việc lệch đồng hồ giữa các node phải được tính đến; không giao quyền gia hạn challenge cho timestamp trên client.

### 8.3. Rate limit vẫn cần trước và sau idempotency

Cần giới hạn request đến để replay không tiêu hao vô hạn việc đọc database hoặc tạo log. Đồng thời, sau lookup cần giới hạn theo account ID và kênh đã xác minh để các key khác nhau không tạo vô hạn lần gửi.

Theo dõi cả số request thô và số tác dụng phụ đã phát sinh. Deduplicate thành công không có nghĩa lưu lượng đó vô hại. Ngược lại, retry delivery nội bộ không nên bị tính như một yêu cầu gửi lại mới của người dùng rồi tự tạo một vòng phát hành khác.

Không dùng khóa IP cứng làm điều kiện sở hữu token: người dùng có thể đổi mạng trong quá trình recovery. Dữ liệu mạng và thiết bị phù hợp hơn cho đánh giá rủi ro và hạn chế lạm dụng.

## 9. Phản hồi công khai và ranh giới bảo mật

Một phản hồi minh họa cho request hợp cú pháp:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp với một tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký."
}
```

Giữ thông điệp này nhất quán cho tài khoản không tồn tại, operation đã tiếp nhận, request bị gộp và trường hợp không được gửi vì chính sách. Không đưa thông tin như “email này đã yêu cầu 3 lần”, “token còn hiệu lực” hoặc “MFA recovery đang chờ duyệt” cho người chưa xác thực.

Cần xem xét cả mã trạng thái, kích thước, header, thời gian phản hồi và endpoint đọc biên nhận. Nếu có receipt ID, nó phải khó đoán và endpoint tra cứu không được trả trạng thái nhạy cảm chỉ dựa trên ID đó. Một idempotency key không phải credential.

Nếu hạ tầng không thể ghi nhận một thao tác đáng lẽ cần lưu bền vững, không coi một cache cục bộ là bằng chứng hoàn tất. Có thể trả lỗi khả dụng chung cho cả endpoint để client retry, hoặc thực hiện chính sách giảm tải đã định nghĩa; không bỏ qua deduplication rồi phát hành không kiểm soát. Việc cố ý chặn gửi vì chính sách là một kết quả khác với lỗi ghi nhận ngoài dự kiến.

TLS bảo vệ đường truyền, còn POST chỉ lựa chọn phương thức HTTP; cả hai không tự ngăn mọi phát lại ở tầng ứng dụng. Với luồng dựa trên trình duyệt và cookie, áp dụng bảo vệ CSRF phù hợp cùng chính sách origin và cookie. Các kiểm tra này giảm một số cách kích hoạt trái ý người dùng, nhưng không thay thế chống bot trên endpoint công khai.

Tránh đặt identifier, key nhạy cảm hoặc token vào URL có thể đi vào lịch sử, access log và referrer. Không gửi token recovery trong log, thông báo lỗi hoặc kết quả truy vấn idempotency.

## 10. Liên hệ với token, MFA, passkey và session

Replay ở bước khởi tạo thường làm tăng số cơ hội tấn công. Ví dụ, nếu mỗi request tạo thêm một mã hợp lệ song song, số mã mà kẻ tấn công có thể đoán trúng có thể tăng. Chính sách số challenge hoạt động và quota theo tài khoản phải được xác định, thay vì chỉ giới hạn từng mã riêng lẻ.

Khi dùng token, hệ thống vẫn cần kiểm tra purpose, account ID, hạn dùng, trạng thái tiêu thụ, kênh và phiên bản bảo mật cần thiết. Việc đánh dấu token đã dùng và áp dụng thay đổi nhạy cảm phải phối hợp nguyên tử hoặc qua một quy trình trạng thái có bảo đảm tương đương. Hai request redeem đồng thời không được cùng đổi thông tin bảo mật như thể mỗi request có một quyền riêng.

Một operation khởi tạo lại không được:

- Xóa cờ token đã tiêu thụ.
- Tạo quyền bỏ qua kiểm tra danh tính đang chờ.
- Hạ luồng lấy lại MFA hoặc passkey xuống chỉ còn biết email.
- Chuyển đích nhận sang email chưa xác minh vừa được nhập.
- Gọi lại hành động thu hồi session chỉ vì hàng đợi giao lại sự kiện khởi tạo.

Sau recovery thành công, chính sách thu hồi session hoặc refresh token, thông báo bảo mật và đăng nhập lại phụ thuộc hành động đã thực hiện. Các tác dụng đó thuộc bước hoàn tất được cho phép; phải có cơ chế tránh lặp riêng khi công việc nền được giao lại.

## 11. Tình huống theo dòng thời gian

Lan mất mật khẩu và nhấn “Khôi phục” trên điện thoại:

| Thời điểm | Sự kiện | Kết quả mong đợi |
|---|---|---|
| T0 | Client gửi operation K1 | Lưu một biên nhận và một sự kiện xử lý |
| T1 | Database commit nhưng HTTP response bị mất | Công việc vẫn tồn tại |
| T2 | Client retry K1 với cùng nội dung | Trả phản hồi chung, không thêm sự kiện |
| T3 | Broker giao sự kiện khởi tạo cho worker | Tạo một challenge đủ điều kiện và một ý định gửi |
| T4 | Worker xử lý xong nhưng mất ACK | Lần giao lại thấy operation đã áp dụng, không tạo challenge mới |
| T5 | Kẻ tấn công gửi K2, K3 cùng nhắm tài khoản Lan | Chịu slot challenge, quota và khoảng nghỉ theo tài khoản |
| T6 | Lan chủ động gửi lại sau khoảng nghỉ | Xét một operation gửi lại riêng theo chính sách |
| T7 | Lan dùng token và hoàn tất đổi mật khẩu | Tiêu thụ quyền một lần và áp dụng kiểm soát session phù hợp |
| T8 | Một request hoặc sự kiện cũ xuất hiện lại | Không khôi phục trạng thái cũ hoặc mở lại token đã dùng |

Nếu một sự kiện gửi ở T3 đã đến nhà cung cấp nhưng kết quả bị mất, có thể cần retry cùng mã gửi. Điều đó khác với tạo một challenge thứ hai. Đây là lý do phải phân biệt operation, challenge và delivery event trong dữ liệu và quan sát hệ thống.

## 12. Tiêu chí kiểm tra thiết kế

Các tình huống dưới đây giúp đánh giá triển khai sau này; chúng không đòi hỏi một công cụ hay framework cụ thể:

| Tình huống | Bất biến cần quan sát |
|---|---|
| Gửi tuần tự 10 request cùng key và payload | Một operation; không nhân số challenge hoặc ý định gửi |
| Hai instance nhận cùng key đồng thời | Unique constraint phân xử; không cùng nhận là operation mới |
| Cùng key nhưng đổi identifier hoặc purpose | Không sửa operation cũ, không thực hiện payload mới |
| Khác key nhưng cùng tài khoản | Quota và slot vẫn giới hạn tác dụng phụ |
| Tiến trình chết trước commit | Không tồn tại nửa biên nhận hoặc ý định gửi bị tách rời |
| Chết sau commit, trước HTTP response | Retry đọc kết quả đã lưu và không tạo mới |
| Broker giao lại sự kiện đã xử lý | Không phát hành lại challenge hoặc mở lại operation |
| Nhà cung cấp đã gửi nhưng response bị mất | Retry giữ nguyên mã gửi; thừa nhận giới hạn của kênh ngoài |
| Lease worker hết hạn khi worker cũ chưa dừng | Worker cũ không ghi đè kết quả mới bằng cập nhật vô điều kiện |
| Retry nhiều lần khi token sắp hết hạn | Hạn dùng và số lần thử không được đặt lại |
| Đổi kênh hoặc tăng phiên bản bảo mật trước delivery | Công việc cũ được đánh giá lại, không gửi sai kênh |
| Sự kiện đến sau khi token hết hạn hoặc đã dùng | Không tạo lại quyền từ trạng thái cũ |
| Dọn dữ liệu idempotency | Giữ đúng cửa sổ cam kết; không dọn công việc đang xử lý thiếu kiểm soát |
| Kho trạng thái chống trùng gặp sự cố | Không chuyển sang phát hành không kiểm soát |
| Tài khoản tồn tại và không tồn tại | Phản hồi công khai và hành vi quan sát được không tiết lộ trạng thái riêng |

Trong vận hành, nên theo dõi tỷ lệ request trùng, xung đột key, operation bị gộp, số challenge mới, số delivery attempt, thời gian chờ và số lần bị quota chặn. Log dùng correlation ID và ID nội bộ với quyền truy cập phù hợp, tránh token và định danh đầy đủ.

Một luồng khởi tạo đáng tin cậy giữ được ý định của người dùng qua lỗi mạng và retry, trong khi số quyền khôi phục và số tác dụng phụ vẫn bị kiểm soát bởi trạng thái bền vững, quota và chính sách bảo mật. Quyền đổi mật khẩu, lấy lại MFA hay đăng ký lại passkey chỉ xuất hiện sau khi các bước xác minh tương ứng đã hoàn tất.