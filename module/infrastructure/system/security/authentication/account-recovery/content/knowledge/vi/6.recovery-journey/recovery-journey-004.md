# Gián đoạn trong hành trình khôi phục tài khoản

Một người dùng bắt đầu khôi phục tài khoản, mở email xác nhận rồi đóng trình duyệt. Người khác gửi biểu mẫu đặt mật khẩu mới nhưng mất mạng trước khi nhận phản hồi. Có người chuyển từ điện thoại sang máy tính, hoặc quay lại sau khi token đã hết hạn.

Các tình huống này đều là **gián đoạn hành trình recovery**, nhưng không có cùng ý nghĩa bảo mật. Hệ thống phải biết việc gì đã được thực hiện, bằng chứng nào còn giá trị và người đang quay lại có quyền tiếp tục đến đâu.

Trong chương **Recovery Journey** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này tập trung vào cách thiết kế khả năng tiếp tục sau gián đoạn khi khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là giữ tiến độ hợp lệ cho người dùng thật mà không tạo đường phát lại token, bỏ xác minh hoặc cấp quyền từ trạng thái đã cũ.

Sau bài học, người học có thể:

- Phân biệt gián đoạn giao diện, hết hạn quyền tiếp tục và thất bại của thao tác bảo mật.
- Thiết kế checkpoint phía máy chủ và điều kiện tiếp tục từ từng checkpoint.
- Xử lý mất kết nối khi kết quả thay đổi tài khoản chưa rõ.
- Quản lý nhiều tab, thiết bị, yêu cầu recovery và thay đổi bảo mật cạnh tranh.
- Thiết kế thông báo và đường phục hồi phù hợp mà không hạ yêu cầu xác minh.

## 1. Gián đoạn không đồng nghĩa với thất bại hoặc hủy

Giả sử Mai nhận liên kết recovery, xác minh một bằng chứng rồi đóng trình duyệt. Việc đóng cửa sổ chỉ cho biết giao diện không còn hoạt động. Máy chủ không nên tự suy ra rằng Mai muốn hủy hồ sơ.

Ngược lại, nếu Mai nhấn “Hủy yêu cầu” sau khi đáp ứng điều kiện cần thiết, đây là một chuyển trạng thái có chủ đích. Hồ sơ đã hủy không được mở lại chỉ vì một tab cũ vẫn còn biểu mẫu.

Cần phân biệt:

| Tình huống | Điều đã biết | Điều chưa được phép suy ra |
|---|---|---|
| Người dùng đóng tab | Kết nối giao diện kết thúc hoặc không còn được quan sát | Người dùng đã hủy recovery |
| Hết thời hạn recovery context | Quyền tiếp tục hiện tại đã hết hạn | Mọi checkpoint của hồ sơ đều phải xóa |
| Token email hết hạn | Token đó không còn được chấp nhận | Người dùng đã mất quyền sở hữu tài khoản |
| POST bị timeout | Trình duyệt chưa nhận được kết quả chắc chắn | Máy chủ chưa thực hiện thay đổi |
| Hồ sơ bị hủy hoặc từ chối | Quyết định kết thúc đã có hiệu lực | Có thể dùng lại bằng chứng cũ để bỏ qua quyết định |
| Recovery đã hoàn tất | Thay đổi đã được xác nhận theo trạng thái máy chủ | Mọi token và session trước đó vẫn được tiếp tục dùng |

Một thiết kế tốt tách **trạng thái hành trình** khỏi **trạng thái kết nối**. Mất kết nối không được tự nâng hoặc hạ quyền.

## 2. Phân loại điểm gián đoạn trước khi thiết kế cách tiếp tục

Không phải mọi gián đoạn đều giải quyết bằng nút “Thử lại”.

| Điểm gián đoạn | Ví dụ | Hướng xử lý chính |
|---|---|---|
| Trước khi tạo hồ sơ | Không gửi được yêu cầu khởi tạo | Cho gửi lại với kiểm soát lặp và chống lạm dụng phù hợp |
| Sau khi tạo hồ sơ, chưa nhận thư | Email trễ hoặc người dùng rời trang | Tra tiến độ trong ngữ cảnh được phép; gửi lại theo chính sách |
| Sau khi mở liên kết | Trình duyệt bị đóng hoặc bộ quét đã mở URL | Không coi GET là hoàn tất recovery; kiểm tra token khi người dùng chủ động tiếp tục |
| Sau khi chấp nhận bằng chứng | Token đã dùng nhưng phản hồi bị mất | Dựa vào checkpoint bền vững và quyền tiếp tục hợp lệ, không bật lại token |
| Trong khoảng chờ | Người dùng quay lại sau vài giờ | Giữ lịch chờ phía máy chủ và kiểm tra lại điều kiện |
| Khi gửi thay đổi cuối cùng | Mất mạng sau khi bấm xác nhận | Tra kết quả thao tác trước khi yêu cầu thực hiện lại |
| Sau thay đổi, trước thông báo | Tài khoản đã đổi nhưng email chưa gửi | Gửi lại thông báo theo cơ chế tin cậy, không lặp thay đổi tài khoản |
| Khi chuyển thiết bị | Email mở trên điện thoại, biểu mẫu trên máy tính | Thiết lập quyền tiếp tục cho thiết bị mới theo chính sách |

Cũng cần xác định gián đoạn do lỗi hay do thay đổi bảo mật. Một hồ sơ hết hiệu lực vì tài khoản vừa được khôi phục ở nơi khác không giống một trang bị tải lại do mạng yếu.

## 3. Máy chủ là nguồn sự thật cho tiến độ và quyền

Trình duyệt có thể hiển thị bước hiện tại, nhưng không nên tự quyết định rằng một bước xác minh đã hoàn tất.

Các dữ liệu như `step=verified` trong URL, cờ `mfaPassed=true` ở local storage hoặc trường ẩn trong biểu mẫu đều có thể bị sửa hoặc trở nên lỗi thời.

Một hồ sơ recovery phía máy chủ có thể chứa:

~~~text
recovery_attempt_id
account_id
requested_actions
state
created_at
overall_deadline
policy_version
security_version_at_evaluation
evidence_records
not_before
approved_plan_reference
current_operation_id
completed_at
cancelled_at
~~~

Đây là mô hình minh họa, không phải một lược đồ bắt buộc.

### Checkpoint là gì?

Checkpoint là bản ghi bền vững cho biết một bước đã được máy chủ chấp nhận trong đúng phạm vi. Ví dụ:

- Token xác nhận kênh đã được chấp nhận vào thời điểm nào.
- Bằng chứng độc lập nào đã được kiểm tra.
- Điều kiện chờ nào đang áp dụng.
- Kế hoạch thay đổi nào đã được phê duyệt.
- Thao tác hoàn tất đang chờ, đã thành công hoặc đã kết thúc không thành công.

Checkpoint không chỉ là tên màn hình. Nó phải gắn với tài khoản, hồ sơ, mục đích và điều kiện có hiệu lực.

### Chỉ lưu những gì cần để ra quyết định

Với bằng chứng đã xác minh, có thể lưu loại bằng chứng, tham chiếu, thời điểm, mức bảo đảm và hạn giá trị theo chính sách. Không lưu nguyên OTP, token reset, mã dự phòng hay mật khẩu vừa nhập vào bản nháp recovery.

Một mã dự phòng đã dùng có thể để lại bản ghi “đã xác minh và tiêu thụ”, nhưng không được trở lại trạng thái chưa dùng để hỗ trợ người quay lại.

Đối với mật khẩu mới, không lưu bản rõ để điền lại biểu mẫu. Nếu chưa được áp dụng, người dùng có thể phải nhập lại. Nếu đã áp dụng, hệ thống cần trả lời trạng thái thao tác thay vì cố hiển thị lại bí mật.

## 4. Mô hình trạng thái để tạm dừng và tiếp tục

Một mô hình đơn giản có thể gồm các trạng thái sau:

| Trạng thái | Ý nghĩa | Hành vi khi người dùng quay lại |
|---|---|---|
| `CREATED` | Hồ sơ đã tồn tại, chưa đủ bằng chứng | Tiếp tục bước phù hợp nếu còn quyền và còn hạn |
| `CHANNEL_PROVEN` | Đã kiểm tra khả năng tiếp cận một kênh | Chỉ tiếp tục trong phạm vi đó, chưa mặc định xác minh chủ tài khoản |
| `EVIDENCE_VERIFIED` | Đã đạt bằng chứng theo quyết định tại thời điểm kiểm tra | Đánh giá độ mới và điều kiện nền trước khi cho đi tiếp |
| `WAITING` | Có điều kiện chờ chưa kết thúc | Hiển thị tiến độ được phép, không cho bỏ thời gian chờ bằng tải lại |
| `READY` | Đủ điều kiện chuẩn bị áp dụng thay đổi | Kiểm tra lại ngay trước thực thi |
| `APPLYING` | Thao tác đã được tiếp nhận và đang áp dụng | Tra kết quả cùng thao tác, không tạo thay đổi cạnh tranh |
| `COMPLETED` | Thay đổi đã hoàn tất theo định nghĩa của hệ thống | Chuyển sang bước xác thực hoặc hướng dẫn sau recovery |
| `EXPIRED`, `CANCELLED`, `REJECTED`, `SUPERSEDED` | Hồ sơ kết thúc không còn được tiếp tục | Giải thích kết quả phù hợp và cung cấp đường bắt đầu lại nếu được phép |

Không cần chuyển sang một trạng thái `PAUSED` chỉ vì tab bị đóng. Nếu dùng trạng thái tạm dừng vì nghiệp vụ, phải định nghĩa rõ nó có ảnh hưởng gì đến thời hạn và quyền.

~~~mermaid
flowchart TD
    A["CREATED"] --> B["CHANNEL_PROVEN"]
    B --> C["EVIDENCE_VERIFIED"]
    C --> D["WAITING nếu chính sách yêu cầu"]
    C --> E["READY"]
    D --> E
    E --> F["APPLYING"]
    F --> G["COMPLETED"]
    H["Người dùng quay lại"] --> I["Kiểm tra quyền tiếp tục và trạng thái máy chủ"]
    I --> J{"Còn điều kiện hợp lệ?"}
    J -->|Có| K["Hiển thị bước được phép"]
    J -->|Không| L["Xác minh lại hoặc bắt đầu hồ sơ phù hợp"]
~~~

Sơ đồ bỏ qua một số chuyển trạng thái để dễ đọc. Trong triển khai, hủy, hết hạn, xung đột hoặc phát hiện rủi ro có thể kết thúc hồ sơ ở nhiều bước, trừ khi thao tác đã được tiếp nhận để áp dụng và cần hoàn tất xử lý theo quy tắc riêng.

## 5. Bốn loại thời hạn cần tách biệt

Dùng một thời hạn chung cho mọi thứ dễ gây lỗi: hoặc người dùng bị mất toàn bộ tiến độ quá sớm, hoặc quyền yếu tồn tại quá lâu.

| Thời hạn | Quản lý điều gì? | Khi hết hạn |
|---|---|---|
| Thời hạn token | Một bí mật dùng để chứng minh hoặc tiếp tục một bước | Không chấp nhận token đó nữa |
| Thời hạn recovery context | Quyền của trình duyệt hoặc thiết bị trong hồ sơ | Cần thiết lập lại quyền tiếp tục phù hợp |
| Độ mới của bằng chứng | Bằng chứng có còn đủ giá trị cho hành động đang xét không? | Có thể phải xác minh hoặc đánh giá lại |
| Hạn tổng thể của hồ sơ | Hồ sơ được phép tồn tại để hoàn tất trong bao lâu? | Kết thúc hồ sơ hoặc chuyển sang quy trình mới theo chính sách |

Ngoài ra, `not_before` hoặc thời điểm kết thúc khoảng chờ là một **mốc chưa được hành động trước đó**, không phải thời hạn xác thực.

Một người quay lại sau khi thời gian chờ kết thúc vẫn phải có quyền tiếp tục và bằng chứng phù hợp. “Đã đợi đủ lâu” không tự là xác minh danh tính.

### Không kéo dài vô hạn bằng cách tương tác

Cần phân biệt hạn bất hoạt với hạn tuyệt đối. Nếu mỗi lần tải trang hoặc gửi lại email đều gia hạn mọi quyền, đối thủ có thể giữ một hồ sơ sống vô thời hạn.

Việc kéo dài thời gian có chủ đích phải theo chính sách và có dấu vết. Không cho trình duyệt tự ghi lại `created_at` hoặc dùng đồng hồ thiết bị để quyết định token còn hạn.

### Bằng chứng đã dùng và bằng chứng còn đủ mới là hai câu hỏi khác nhau

Một OTP có thể đã được tiêu thụ đúng một lần và tạo checkpoint. Checkpoint đó có thể được dùng để tiếp tục hồ sơ trong phạm vi cho phép, nhưng không có nghĩa OTP được dùng lần thứ hai.

Nếu hành động cuối cần xác thực mới, hệ thống yêu cầu bằng chứng mới phù hợp. Không yêu cầu nhập lại mã dự phòng đã tiêu thụ như thể mã ấy vẫn hợp lệ, cũng không lặp lại một challenge passkey cũ.

## 6. Quyền tiếp tục: biết mã hồ sơ chưa đủ

Mã hồ sơ giúp tra cứu một đối tượng. Nó không nên mặc định là quyền đổi credential hoặc xem thông tin tài khoản.

Cần phân biệt:

- **Định danh hồ sơ:** cho biết đang nói đến hồ sơ nào.
- **Quyền tiếp tục:** cho biết ngữ cảnh hiện tại được phép làm gì với hồ sơ.
- **Bằng chứng xác minh:** cho biết điều kiện nào đã được chứng minh và còn giá trị.
- **Quyền hoàn tất:** cho biết có được thực hiện thay đổi cụ thể ngay lúc này không.

Một recovery context có thể được lưu bằng cookie bảo vệ phù hợp và liên kết với trạng thái máy chủ. Nó cần phạm vi hẹp, thời hạn và cơ chế vô hiệu; không nên là session tài khoản đầy đủ.

Không lưu bearer token dài hạn trong local storage chỉ để tiện quay lại. Kịch bản XSS hoặc mã bên thứ ba có thể làm lộ nó. Nếu dùng cookie, vẫn cần các thuộc tính bảo vệ phù hợp và kiểm soát chống giả mạo yêu cầu theo thiết kế của luồng.

### Cùng trình duyệt

Nếu recovery context còn hợp lệ, máy chủ có thể trả bước hiện tại theo checkpoint. Trình duyệt không cần giữ lại bí mật của bước đã hoàn tất.

Nếu context đã hết hạn nhưng hồ sơ còn hạn, có thể thiết lập lại quyền tiếp tục theo chính sách. Việc này không tự biến một xác nhận email mới thành quyền vượt qua bằng chứng độc lập đã hết giá trị.

### Thiết bị khác

Một liên kết email thường được mở ở thiết bị khác với nơi khởi tạo. Có thể hỗ trợ chuyển tiếp, nhưng cần thiết kế rõ:

1. Thiết bị mới nhận quyền phạm vi hẹp cho đúng hồ sơ.
2. Token hoặc cơ chế chuyển tiếp được kiểm tra đúng mục đích và còn hạn.
3. Máy chủ xác định bằng chứng nào có thể tiếp tục được dùng và bằng chứng nào phải kiểm tra lại.
4. Các hành động nhạy cảm vẫn tuân thủ yêu cầu xác thực tương ứng.

Không nên chuyển toàn bộ quyền chỉ vì thiết bị mới đọc được email. Nếu hộp thư bị chiếm, đối thủ cũng có thể thực hiện bước đó.

Nếu sản phẩm chủ động yêu cầu cùng thiết bị cho một bước nhất định, cần giải thích và có phương án khi người dùng không còn thiết bị ấy. Không thay yêu cầu bằng một nút bỏ qua.

### Token bị trình quét email mở trước

GET từ một bộ quét hoặc trình xem trước không được đổi mật khẩu, xóa MFA hoặc hoàn tất recovery. Không nên tiêu thụ token xác minh chỉ vì có lượt mở URL tự động.

Trang có thể yêu cầu một hành động chủ động phù hợp qua POST trước khi chấp nhận bằng chứng. URL chứa token cũng cần tránh lọt vào log, analytics, referrer hoặc tài nguyên bên thứ ba.


## 7. Token đã dùng nhưng người dùng không thấy bước tiếp theo

Đây là tình huống thường bị xử lý sai:

1. Người dùng gửi token hợp lệ.
2. Máy chủ tiêu thụ token và ghi checkpoint.
3. Kết nối mất trước khi trình duyệt nhận phản hồi.
4. Người dùng mở lại cùng liên kết.
5. Hệ thống chỉ thông báo “token đã dùng”, khiến họ tưởng toàn bộ recovery thất bại.

Không nên sửa bằng cách cho token đã dùng hoạt động lại. Một đối thủ có bản sao token cũng sẽ được hưởng đường phát lại đó.

Cách xử lý phụ thuộc quyền còn lại:

| Điều kiện khi quay lại | Hướng xử lý |
|---|---|
| Còn recovery context hợp lệ, gắn với đúng hồ sơ | Đọc checkpoint và chuyển đến bước hiện tại |
| Có quyền tra trạng thái phù hợp nhưng không còn quyền thay đổi | Chỉ trả tiến độ được phép; thiết lập lại quyền thao tác nếu cần |
| Không còn quyền tiếp tục, nhưng có đường xác minh lại được phê duyệt | Thiết lập context mới và đánh giá những checkpoint được phép giữ |
| Hồ sơ hoặc bằng chứng đã hết hiệu lực | Yêu cầu bước xác minh mới hoặc hồ sơ mới theo chính sách |
| Token bị trình từ ngữ cảnh không được phép | Không tiết lộ tiến độ nhạy cảm chỉ vì người trình biết token cũ |

Nếu quyền tiếp tục chỉ được gửi trong phản hồi bị mất, hệ thống cần một đường thiết lập lại quyền hợp lệ. Có thể dùng cơ chế tiếp tục được thiết kế riêng hoặc khởi tạo lại bước cần thiết, nhưng không được coi token đã tiêu thụ là credential còn sống.

### Gửi lại token không nhất thiết tạo lại mọi bước

Có thể phát hành token mới cho cùng hồ sơ hoặc thay thế hồ sơ theo chính sách. Điều quan trọng là giữ rõ mục đích: token mới để chứng minh lại một kênh hoặc thiết lập quyền tiếp tục, không mặc định cấp lại mọi quyền đã có trong một context trước đó.

Giới hạn số lần gửi và chính sách thay token cần tránh hai rủi ro:

- Để nhiều token còn hiệu lực quá rộng.
- Cho người chưa xác minh liên tục gửi lại, làm vô hiệu tiến trình của nạn nhân.

Một yêu cầu gửi lại không nên tự đặt lại khoảng chờ hoặc kéo dài hạn tổng thể vô hạn.

## 8. Mất mạng ở bước cuối: tra kết quả trước khi làm lại

Khi trình duyệt bị timeout, có ít nhất ba khả năng:

1. Yêu cầu chưa đến máy chủ.
2. Yêu cầu đã đến nhưng chưa hoàn tất.
3. Thay đổi đã hoàn tất, chỉ phản hồi bị mất.

Giao diện không thể phân biệt các khả năng này chỉ từ một thông báo lỗi mạng.

### Theo dõi một thao tác logic

Nên có định danh thao tác và cơ chế lặp lại an toàn. Ví dụ, thao tác “áp dụng kế hoạch recovery này” có một khóa idempotency gắn với đúng hồ sơ và ngữ cảnh được phép.

Khi nhận lại cùng thao tác, hệ thống:

- Trả trạng thái hoặc kết quả đã lưu nếu đã xử lý.
- Trả trạng thái đang xử lý nếu còn chạy.
- Từ chối nếu cùng khóa nhưng nội dung hành động khác.
- Không coi khóa idempotency là bằng chứng xác thực.

Khóa không được chỉ là một giá trị toàn cục có thể dùng lại cho mọi tài khoản. Cần ràng buộc với tài khoản, hồ sơ, loại hành động và phạm vi kiểm tra thích hợp.

Nếu cần đối chiếu nội dung nhạy cảm giữa các lần gửi, dùng cơ chế bảo vệ phù hợp. Không lưu hoặc log mật khẩu bản rõ, cũng không tạo một dấu băm công khai của mật khẩu chỉ để kiểm tra retry.

### Mã giả cho trường hợp thay đổi cốt lõi trong một transaction

~~~text
function submitFinalChange(context, attemptId, operationKey, request):
    require validSubmissionContext(context)

    transaction:
        attempt = lockRecoveryAttempt(attemptId)
        require context is authorized for attempt

        operation = findOperation(attemptId, operationKey)

        if operation exists:
            require requestMatchesSafely(operation, request)
            return permittedOperationStatus(operation, context)

        require context may submit final change
        account = lockAccount(attempt.accountId)

        require attempt.state == "READY"
        require attempt.overallDeadline > now
        require requiredEvidenceStillValid(attempt, account)
        require now >= attempt.notBefore
        require account.securityVersion ==
                attempt.approvedSecurityVersion

        plan = validateRequestedActionAgainstApprovedPlan(
            request, attempt, account
        )

        operation = createOperation(attemptId, operationKey, plan)
        applyCredentialChangeAndLocalEnforcement(account, plan)

        account.securityVersion += 1
        attempt.state = "COMPLETED"
        operation.state = "SUCCEEDED"

        narrowContinuationRightsToStatusOnly(context)
        recordOutcomeWithoutSecrets(operation)
        enqueueNotification(operation)

    return permittedOperationStatus(operation, context)
~~~

Mã giả này minh họa trường hợp thay đổi cốt lõi và ranh giới thu hồi liên quan có thể thực hiện trong cùng transaction. Nó không phải cách bảo đảm nguyên tử cho nhiều dịch vụ độc lập.

Quyền tra trạng thái sau hoàn tất có thể rất ngắn và chỉ đọc. Nó giúp xử lý phản hồi bị mất, nhưng không được dùng để thêm yếu tố, lấy token mới hoặc truy cập dữ liệu tài khoản.

### Khi kết quả còn chưa rõ

Giao diện có thể thông báo:

> Chưa xác định được kết quả do kết nối bị gián đoạn. Đang kiểm tra trạng thái của thao tác vừa gửi.

Nếu máy chủ trả “đang xử lý”, chờ hoặc kiểm tra lại theo nhịp có giới hạn. Nếu trả “đã hoàn tất”, chuyển sang hướng dẫn phù hợp. Nếu trả “chưa tiếp nhận” một cách đáng tin cậy, có thể gửi lại cùng thao tác trong phạm vi còn hiệu lực.

Không khuyến khích người dùng tạo ngay một yêu cầu recovery khác hoặc bấm liên tục nút xác nhận khi thao tác cũ có thể đang chạy.

## 9. Nhiều tab, nhiều thiết bị và hồ sơ cạnh tranh

### Hai tab của cùng một hồ sơ

Tab A và tab B cùng hiển thị bước nhập mật khẩu mới. Tab A hoàn tất trước. Khi tab B gửi biểu mẫu cũ, máy chủ cần nhận ra hồ sơ đã kết thúc hoặc thao tác đã có kết quả.

Nút bị vô hiệu ở tab A không bảo vệ được tab B. Trạng thái và điều kiện phải được kiểm tra tại endpoint thay đổi.

Nếu hai tab gửi cùng khóa thao tác, trả kết quả cùng thao tác theo quyền được phép. Nếu gửi hai thao tác khác nhau, quy tắc cạnh tranh phải bảo đảm không có hai lần hoàn tất độc lập từ cùng một phê duyệt.

### Hai hồ sơ của cùng một tài khoản

Hệ thống cần chính sách rõ: cho phép một hồ sơ hiện hành, nhiều hồ sơ có phạm vi riêng, hay thay thế có kiểm soát.

Không nên tự động hủy mọi hồ sơ cũ chỉ vì có người chưa xác minh tạo một yêu cầu mới. Điều đó có thể trở thành cách làm gián đoạn recovery của người dùng thật.

Tại thời điểm áp dụng thay đổi, vẫn cần ngăn hai hồ sơ cùng dựa vào trạng thái bảo mật cũ rồi lần lượt xóa hoặc thêm yếu tố theo những kế hoạch khác nhau.

Có thể dùng phiên bản bảo mật của tài khoản để phát hiện quyết định cũ. Những thay đổi liên quan như credential, kênh recovery hoặc quyền quan trọng làm phiên bản thay đổi; hồ sơ cũ cần được đánh giá lại hoặc kết thúc theo chính sách.

### Không mặc định mọi xung đột đều là chiếm đoạt

Người dùng có thể mở liên kết hai lần hoặc dùng cả điện thoại và máy tính. Cần thông báo rõ khi nào chỉ là trạng thái đã được cập nhật, khi nào phải xác minh lại và khi nào cần xử lý tranh chấp quyền sở hữu.

Việc chuyển tab hoặc đổi mạng cũng không tự tạo lý do để bỏ kiểm tra. Tín hiệu thiết bị và mạng có thể hỗ trợ đánh giá rủi ro, nhưng không thay thế bằng chứng sở hữu.

## 10. Gián đoạn giữa các thay đổi bảo mật

Recovery có thể gồm nhiều tác động:

- Thay mật khẩu.
- Vô hiệu hoặc thay yếu tố xác thực.
- Thu hồi session và refresh token.
- Xử lý mã dự phòng, dấu tin cậy thiết bị hoặc quyền ứng dụng.
- Gửi thông báo.
- Ghi dấu vết điều tra.

Nếu tiến trình dừng ở giữa, không nên chỉ nhìn trạng thái email để kết luận toàn bộ recovery thành công hay thất bại.

### Phân biệt tác động cốt lõi và tác vụ có thể gửi lại

Thay credential và bảo đảm ranh giới cấp quyền là tác động cốt lõi. Thông báo có thể được xếp hàng và gửi lại nếu lỗi, nhưng phải tránh ghi nhận sai rằng người dùng đã nhận hoặc đọc thư.

Ví dụ, dùng outbox cùng transaction với thay đổi cốt lõi giúp giữ sự kiện cần gửi. Worker gửi lại thông báo không được áp dụng lại thay đổi mật khẩu.

### Khi thu hồi session ở dịch vụ khác

Nếu credential đã đổi nhưng một dịch vụ vẫn chấp nhận refresh token cũ, đối thủ có thể giữ quyền. Chỉ ghi “revocation requested” chưa chứng minh tài khoản đã được làm sạch.

Cần định nghĩa rõ:

1. Khi nào ranh giới thu hồi có hiệu lực?
2. Quyền nào còn bị hạn chế trong lúc chờ?
3. Hệ thống phát hiện và xử lý lỗi thu hồi ra sao?
4. Điều kiện nào cho phép công bố hoàn tất?
5. Ai chịu trách nhiệm với tác vụ bị kẹt?

Có thể dùng phiên bản quyền được kiểm tra khi truy cập, cơ chế thu hồi tập trung hoặc một mô hình phối hợp khác phù hợp với kiến trúc. Không có một lựa chọn duy nhất cho mọi hệ thống; yêu cầu là quyền cũ không tiếp tục được chấp nhận ngoài mức rủi ro đã định.

### Hồ sơ đang áp dụng không được bỏ mặc theo timeout giao diện

Nếu thao tác đã được tiếp nhận hợp lệ, việc cookie của người dùng hết hạn sau đó không tự có nghĩa hệ thống phải bỏ dở giữa các thay đổi.

Ngược lại, một tác vụ mới chỉ được xếp hàng cũng không nên giữ quyền áp dụng mãi mãi. Cần có thời hạn thực thi, kiểm tra lại các điều kiện quan trọng trước thay đổi và một trạng thái kết thúc rõ nếu không thể tiếp tục.

Mất kết nối của người dùng không quyết định các quy tắc này. Trạng thái bền vững và cơ chế điều phối phía máy chủ mới quyết định.

### Tính lặp lại an toàn của tác vụ nền

Một worker có thể chạy lại sau khi bị dừng. Nó cần biết tác động nào đã áp dụng, không tạo nhiều yếu tố hoặc nhiều session ngoài kế hoạch.

Nếu đã xuất hiện thay đổi bảo mật mới từ một luồng hợp lệ khác, worker không được quay lại áp dụng kế hoạch cũ chỉ vì có một thông điệp chưa xử lý trong hàng đợi.

Không tự khôi phục yếu tố bị nghi xâm nhập để “rollback cho đủ bước”. Với thay đổi bảo mật, quay lui cần một kế hoạch an toàn, không phải luôn đảo ngược mọi thao tác đã làm.

## 11. Thiết kế giao diện tiếp tục mà không làm lộ thông tin

Giao diện nên trả lời bốn câu hỏi:

- Tiến trình hiện đang ở đâu?
- Điều gì đã được xác nhận?
- Điều gì cần làm tiếp?
- Nếu không thể tiếp tục, có đường xử lý nào được phép?

Thông điệp cần phù hợp với mức quyền của người xem. Trước khi có quyền xem hồ sơ, không trả chi tiết yếu tố xác thực, địa chỉ đầy đủ hoặc lịch sử recovery chỉ vì người dùng nhập một email.

### Ví dụ thông điệp

| Trạng thái | Cách diễn đạt minh họa |
|---|---|
| Context hết hạn, hồ sơ còn có thể tiếp tục | “Phiên tiếp tục đã hết hạn. Hãy hoàn thành bước xác minh để tiếp tục yêu cầu này.” |
| Token không còn hợp lệ | “Liên kết này không còn dùng được. Bạn có thể yêu cầu liên kết phù hợp nếu yêu cầu vẫn còn hiệu lực.” |
| Đang xử lý thay đổi | “Thao tác đang được xử lý. Hãy kiểm tra trạng thái trước khi gửi yêu cầu khác.” |
| Hồ sơ đã hoàn tất, người xem có quyền tra kết quả | “Yêu cầu đã hoàn tất. Hãy thực hiện bước đăng nhập hoặc xác thực tiếp theo.” |
| Điều kiện tài khoản thay đổi | “Không thể tiếp tục theo trạng thái cũ. Yêu cầu cần được kiểm tra lại.” |
| Chưa đủ bằng chứng | “Chưa đủ điều kiện cấp lại quyền. Bạn có thể xem các phương án xác minh được hỗ trợ.” |

Không hiển thị “khôi phục thất bại, hãy tạo tài khoản mới” khi chỉ có một token hết hạn. Cũng không hứa rằng mọi hồ sơ đều sẽ thành công sau thời gian chờ.

### Hỗ trợ tiếp cận và sử dụng thực tế

- Cho phép dán mã và nhập bằng bàn phím theo thiết kế an toàn.
- Hiển thị trạng thái lỗi bằng nội dung có thể đọc được, không chỉ bằng màu.
- Giải thích khi phải mở liên kết trên thiết bị khác hoặc quay lại trình duyệt ban đầu.
- Báo thời gian chờ từ dữ liệu máy chủ và tránh bộ đếm tự đặt lại mỗi lần tải trang.
- Không buộc người dùng ghi nhớ một bí mật đã dùng chỉ để xác định bước tiếp theo.

Nếu cần nhập lại dữ liệu vì không lưu bản nháp nhạy cảm, giải thích ngắn gọn. Sự thuận tiện không nên dựa vào việc giữ mật khẩu hoặc mã recovery trong lưu trữ trình duyệt.

### Hỗ trợ khách hàng khi tiến trình bị kẹt

Nhân viên có thể xem mã hồ sơ, trạng thái và kết quả kỹ thuật theo quyền của họ. Họ không nên yêu cầu người dùng gửi token, OTP hoặc mã dự phòng vào ticket.

Công cụ hỗ trợ cần phân biệt “không nhận được phản hồi”, “chưa áp dụng”, “đang áp dụng” và “đã áp dụng”. Nếu chỉ có nút “đặt lại toàn bộ”, hỗ trợ dễ làm mất dấu hoặc tạo thêm xung đột.

Khi thật sự cần ngoại lệ, xử lý theo cơ chế phê duyệt tương ứng. “Người dùng đã thử nhiều lần” không tự là lý do bỏ MFA hoặc chuyển sang một kênh yếu hơn.

## 12. Chống lạm dụng cơ chế tiếp tục

Đối thủ có thể chủ động tạo gián đoạn hoặc lợi dụng cách hệ thống xử lý gián đoạn.

| Hành vi lạm dụng | Kiểm soát cần có |
|---|---|
| Trình lại token đã tiêu thụ | Token dùng một lần; tiếp tục bằng quyền riêng, không hồi sinh token |
| Sửa bước trên trình duyệt | Máy chủ kiểm tra trạng thái và quyền cho từng hành động |
| Dùng mã hồ sơ để dò tiến độ | Xác thực quyền tra cứu, phản hồi tối thiểu và giới hạn phù hợp |
| Gửi lại liên tục để kéo dài hồ sơ | Hạn tuyệt đối và chính sách phát hành lại |
| Tạo yêu cầu mới để phá tiến trình của nạn nhân | Không cho yêu cầu chưa xác minh tùy tiện vô hiệu mọi hồ sơ |
| Thay thiết bị để né kiểm tra | Thiết lập context mới đúng phạm vi và đánh giá lại điều kiện cần thiết |
| Lặp thao tác sau timeout | Idempotency, lưu kết quả bền vững và kiểm tra quyền |
| Kích hoạt luồng cũ sau khi tài khoản thay đổi | Phiên bản bảo mật hoặc cơ chế phát hiện quyết định cũ |
| Gọi API trực tiếp từ context yếu | Phân quyền phía máy chủ, không chỉ điều khiển giao diện |
| Dùng lỗi dịch vụ để yêu cầu bỏ kiểm soát | Phương án dự phòng được phê duyệt, không tự hạ bằng chứng |

Giới hạn tần suất cần xét tài khoản, hồ sơ, nguồn yêu cầu và hành vi. Giới hạn chỉ theo một chiều có thể bị né hoặc bị dùng để chặn nạn nhân.

Cũng cần giảm tải từ việc kiểm tra trạng thái: khoảng kiểm tra hợp lý, thời gian lùi khi lỗi và dừng khi hồ sơ kết thúc. Không để một giao diện đang chờ tạo lưu lượng truy vấn vô hạn.

## 13. Theo dõi gián đoạn mà không thu thập bí mật

Các sự kiện có ích gồm:

- Tạo hồ sơ, chấp nhận bằng chứng và ghi checkpoint.
- Phát hành hoặc hết hạn recovery context.
- Tiếp tục thành công, yêu cầu xác minh lại hoặc từ chối tiếp tục.
- Thao tác được tiếp nhận, đang xử lý và kết thúc.
- Xung đột phiên bản bảo mật hoặc hồ sơ cạnh tranh.
- Tác vụ thu hồi hoặc thông báo bị lỗi và được xử lý lại.

Log nên dùng định danh nội bộ và mã lý do phù hợp. Không ghi token, OTP, mã dự phòng, cookie, mật khẩu hoặc URL recovery đầy đủ.

### Đọc số liệu theo đúng đơn vị

Có thể đo tỷ lệ quay lại thành công theo checkpoint, số thao tác có phản hồi mất nhưng đã hoàn tất, thời gian ở trạng thái đang xử lý và số hồ sơ phải bắt đầu lại.

Cần phân biệt một người với nhiều lần tải lại, một hồ sơ với nhiều lần gửi email, và một thao tác với nhiều retry. Nếu đếm mọi retry là một lần recovery thất bại, báo cáo sẽ sai lệch.

Tỷ lệ tiếp tục cao không tự chứng minh an toàn. Nó có thể tăng do hệ thống cho giữ bằng chứng quá lâu. Tỷ lệ bắt đầu lại cao cũng có thể do thiết kế giao diện, nhà cung cấp gửi thư chậm hoặc người dùng thiếu phương án dự phòng.

Theo dõi cần kết hợp sự cố chiếm đoạt, phản hồi người dùng và kết quả hỗ trợ. Không có khiếu nại ngay không chứng minh không có lạm dụng, vì phát hiện sự cố thường có độ trễ.

## 14. Các tình huống dùng để kiểm tra thiết kế

Bảng sau là các tình huống rà soát cho bài học, không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Kết quả mong đợi |
|---|---|
| Đóng tab sau khi tạo hồ sơ | Không tự hủy; khi quay lại phải có quyền phù hợp |
| Tải lại sau khi xác minh bằng chứng | Dùng checkpoint hợp lệ, không yêu cầu phát lại token đã tiêu thụ |
| Mất phản hồi ngay sau khi tiêu thụ token | Có đường thiết lập lại quyền tiếp tục; không bật lại token cũ |
| Token hết hạn nhưng hồ sơ còn hạn | Phát hành hoặc xác minh lại theo chính sách, không mặc định xóa mọi tiến độ |
| Context hết hạn trong thời gian chờ | Thiết lập lại quyền tiếp tục; không coi hết chờ là đủ xác minh |
| Chuyển sang thiết bị khác | Chỉ chuyển quyền được phép, không tự bỏ bằng chứng độc lập |
| Bộ quét mở liên kết email | Không thực hiện thay đổi bảo mật hoặc hoàn tất recovery bằng GET |
| Timeout ở bước áp dụng mật khẩu mới | Tra kết quả cùng thao tác trước khi làm lại |
| Hai tab gửi cùng thao tác | Một kết quả logic, không áp dụng hai lần |
| Hai hồ sơ cạnh tranh | Không cùng hoàn tất dựa trên quyết định bảo mật đã cũ |
| Người dùng thật thay yếu tố trong lúc hồ sơ cũ chờ | Hồ sơ cũ được đánh giá lại hoặc kết thúc theo chính sách |
| Worker dừng rồi chạy lại | Không lặp tác động hoặc áp dụng kế hoạch đã mất hiệu lực |
| Thu hồi session bị lỗi | Không báo tài khoản đã an toàn chỉ vì đã gửi lệnh thu hồi |
| Thông báo email gửi lỗi sau khi thay đổi thành công | Gửi lại thông báo, không lặp thay đổi credential |
| Mã hồ sơ bị lộ | Không đủ để tra thông tin nhạy cảm hoặc thực hiện recovery |
| Người dùng liên tục bấm gửi lại | Không kéo dài quyền vô hạn hoặc gây mất hiệu lực tùy tiện cho hồ sơ hợp lệ |

## 15. Áp dụng lại vào hành trình của Mai

Mai bắt đầu recovery trên máy tính nhưng mở email trên điện thoại. Sau khi hoàn thành bước xác nhận kênh, cô quay lại máy tính và nhận được thông báo phiên tiếp tục đã hết hạn.

Một hành trình phù hợp có thể là:

1. Hồ sơ và checkpoint vẫn tồn tại phía máy chủ trong thời hạn cho phép.
2. Máy tính thiết lập lại quyền tiếp tục theo quy trình, không chỉ dựa vào việc Mai nhập đúng email.
3. Hệ thống xác định bằng chứng nào còn hợp lệ và yêu cầu lại những bằng chứng cần thiết.
4. Sau khi đủ điều kiện, Mai gửi thay đổi cuối cùng với định danh thao tác đã được ràng buộc.
5. Nếu mất mạng, giao diện tra kết quả cùng thao tác thay vì tạo thêm một lần thay đổi.
6. Nếu đã hoàn tất, Mai được hướng dẫn bước xác thực tiếp theo; context recovery không trở thành quyền truy cập toàn bộ tài khoản.
7. Các tác vụ thông báo và xử lý quyền tồn tại được theo dõi theo trạng thái thực tế.

Nếu trong lúc Mai rời trang, một luồng khác đã thay yếu tố hoặc có tín hiệu chiếm đoạt, hệ thống không tiếp tục từ checkpoint cũ một cách máy móc. Nó đánh giá lại theo trạng thái mới.

Khả năng tiếp tục an toàn dựa trên ba điều: **tiến độ được ghi bền vững, quyền được kiểm tra lại và kết quả thay đổi được xác định rõ**. Giữ lại một màn hình hoặc cho token cũ hoạt động thêm lần nữa không đáp ứng được ba điều đó.
