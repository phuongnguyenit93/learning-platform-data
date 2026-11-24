# Idempotent distributed commands — Lệnh phân tán có tính lặp an toàn

## 1. Retry một lệnh khôi phục có thể gây ra điều gì?

Trong một luồng khôi phục tài khoản, client, API gateway, worker hoặc bộ điều phối đều có thể thử gửi lại khi không nhận được phản hồi. Lời gọi trước có thể chưa tới dịch vụ đích, đang xử lý hoặc đã commit nhưng phản hồi bị mất. Bên gọi thường không thể phân biệt những trường hợp này chỉ từ một lỗi timeout.

Nếu mỗi lần nhận lệnh đều thực hiện lại, hệ thống có thể đổi credential nhiều lần, cấp nhiều quyền đăng ký MFA, tạo nhiều bộ recovery code hoặc gửi các liên kết bảo mật khác nhau. Những tác động này đặc biệt nguy hiểm khi quyền ban đầu chỉ cho phép một hành động.

**Idempotent distributed commands** là thiết kế để việc gửi lại cùng một ý định nghiệp vụ không tạo thêm tác động ngoài contract đã định nghĩa. Hệ thống nhận diện lệnh, ràng buộc nội dung và trả lại trạng thái phù hợp của thao tác đã có thay vì tự tạo thao tác mới.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, mục tiêu là bảo vệ các hành động đặt lại mật khẩu, đăng ký lại MFA, thay passkey hoặc thiết bị xác thực, đồng thời giữ nguyên các điều kiện về danh tính, rủi ro, token dùng một lần và kiểm soát phiên.

### Ví dụ mở đầu

Người dùng gửi lệnh đặt mật khẩu mới với key `recovery-command-demo-19`. Backend đã đổi mật khẩu và tiêu thụ quyền khôi phục, nhưng kết nối bị ngắt trước khi trả kết quả. Người dùng nhấn lại nút hoàn tất.

Kết quả mong muốn là tìm lại operation đã commit và trả trạng thái được phép xem. Backend không nên coi token đã dùng là lý do tự mở lại quyền, cũng không nên tạo thêm một lần thay đổi credential chỉ vì lời gọi thứ hai có mặt.

## 2. Định nghĩa tính lặp an toàn theo tác động nghiệp vụ

Ở mức khái niệm, một thao tác có tính idempotent nếu áp dụng lại cùng thao tác không làm thay đổi kết quả nghiệp vụ thêm lần nữa sau lần áp dụng đầu tiên.

```text
apply(command)
apply(the same command again)
    → một tác động nghiệp vụ được ghi nhận theo contract
```

Điều này không có nghĩa mọi chi tiết kỹ thuật phải giống hệt nhau. Lần gọi lại có thể tạo thêm log truy cập hoặc một bản ghi attempt, nhưng không được tiêu thụ thêm quyền hay cấp thêm credential ngoài phạm vi đã cho phép.

Phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Giới hạn |
|---|---|---|
| Tính xác định | Cùng đầu vào cho cùng kết quả tính toán theo điều kiện đã xác định | Không tự ngăn một tác dụng phụ bị thực hiện nhiều lần |
| Phát hiện trùng | Nhận ra hai lần giao có cùng định danh | Chưa bảo đảm thay đổi nghiệp vụ và bản ghi chống trùng được lưu nhất quán |
| Idempotency | Cùng lệnh được xử lý lại mà không tăng tác động ngoài contract | Cần phạm vi, nội dung và trạng thái bền vững phù hợp |
| Dùng một lần | Một quyền chỉ cho phép một lần thực thi được chấp nhận | Không tự giúp client tìm lại kết quả khi mất phản hồi |
| Giao đúng một lần | Một thuộc tính của cơ chế giao hoặc xử lý trong phạm vi cụ thể | Không mặc nhiên bao phủ mọi tác dụng phụ ở dịch vụ khác |

Ví dụ, lệnh “đặt email liên hệ thành X” có vẻ lặp an toàn về giá trị cuối, nhưng mỗi lần chạy có thể phát thêm token, gửi thêm thông báo hoặc kích hoạt thay đổi phiên. Cần xét toàn bộ tác động bảo mật, không chỉ giá trị một cột.

## 3. Định danh một ý định nghiệp vụ

Một lệnh nhạy cảm nên có định danh ổn định được dùng xuyên các lần retry. Các trường minh họa:

```text
commandId
idempotencyKey
tenantId
initiatorScope
commandType
accountId
recoveryRequestId
requestVersion
recoveryGrantId
actionPayloadReference
payloadFingerprint
createdAt
executionDeadline
```

`commandId` hoặc idempotency key nhận diện ý định nghiệp vụ. `attemptId` nếu có chỉ nhận diện một lần gửi hoặc lần thực thi kỹ thuật. Retry không được tạo command mới chỉ để làm cho mỗi attempt có ID khác nhau.

Một người dùng chủ động thực hiện một hành động mới có thể cần command mới, nhưng command mới vẫn phải có quyền hợp lệ. Đổi key không được trở thành cách vượt giới hạn một lần sử dụng của cùng recovery grant.

### Phạm vi của key

Một ràng buộc duy nhất minh họa:

```text
(tenantId, initiatorScope, commandType, idempotencyKey)
```

Phạm vi này giúp ngăn trả nhầm kết quả giữa tenant hoặc người khởi tạo khác nhau. Nội dung target và hành động cần được đưa vào phép kiểm tra nội dung để phát hiện cùng key bị dùng cho tài khoản hoặc yêu cầu khác.

Nếu lệnh được chuyển qua nhiều dịch vụ, danh tính khởi tạo cần được truyền theo một cơ chế có thẩm quyền. Không lấy trường `initiatorScope` tự khai từ payload làm bằng chứng rằng người gửi được phép dùng kết quả của người khác.

## 4. Ràng buộc key với nội dung, không chỉ với thời gian

Khi đã có operation tương ứng với một key, backend cần kiểm tra lần gọi mới có cùng nội dung nghiệp vụ hay không.

```text
Cùng phạm vi + cùng key + cùng nội dung
    → tra cứu hoặc tiếp tục operation đã có

Cùng phạm vi + cùng key + khác nội dung
    → xung đột, không ghi đè operation cũ
```

Nội dung cần so sánh có thể gồm tài khoản, yêu cầu, phiên bản, loại hành động, grant và payload liên quan. Không chỉ so sánh email hoặc một trường `action` chung chung.

Việc chuẩn hóa phải có quy tắc ổn định. Không tùy ý bỏ qua các trường ảnh hưởng bảo mật như đích nhận kết quả hoặc phương thức xác thực cần đăng ký. Nếu dùng fingerprint, cần lưu phiên bản phương pháp để có thể kiểm tra đúng về sau.

### Đặc biệt cẩn thận với mật khẩu và bí mật

Không lưu payload thô của lệnh đặt mật khẩu vào bảng idempotency hoặc log. Cũng không mặc định băm mật khẩu bằng một hàm băm nhanh rồi lưu công khai là cách an toàn để so sánh các lần retry; giá trị đó có thể tạo thêm dữ liệu hữu ích cho việc đoán bí mật.

Một thiết kế có thể dùng tham chiếu payload bất biến đã được bảo vệ hoặc một cơ chế fingerprint phía máy chủ được bảo vệ theo mô hình đe dọa, có quản lý khóa và quyền truy cập phù hợp. Cần tránh trả fingerprint hoặc dữ liệu bí mật cho client khi báo xung đột.

Quá trình lưu credential chính thức vẫn phải dùng cơ chế bảo vệ credential của hệ thống. Fingerprint phục vụ idempotency không thay thế việc băm mật khẩu hoặc quản lý bí mật xác thực đúng cách.

## 5. Idempotency key không phải thông tin xác thực

Một key có thể khó đoán nhưng biết key không đồng nghĩa có quyền thực hiện lệnh hoặc xem kết quả.

Mỗi lời gọi cần đi qua các kiểm tra xác thực và phân quyền phù hợp trước khi trả dữ liệu của operation. Nếu người gọi đã mất quyền, backend không nên trả kết quả nhạy cảm chỉ vì họ gửi đúng key của một thao tác trước đây.

Cần phân biệt hai đường:

- **Thực hiện hành động mới:** phải đáp ứng điều kiện cấp quyền và thực thi hiện hành theo contract.
- **Tra cứu kết quả đã commit:** không lặp hành động, nhưng vẫn phải được phép xem trạng thái hoặc dữ liệu trả về.

Một quyền khôi phục đã được tiêu thụ có thể không còn cho phép hành động mới. Nếu client mất phản hồi, hệ thống cần một cơ chế tra cứu kết quả được ràng buộc an toàn, chẳng hạn ngữ cảnh giao dịch hạn chế hoặc quyền xem operation được thiết kế riêng. Không mở lại grant để làm cho retry hoạt động.

Không tái sử dụng token hành động như một bearer token đọc được mọi kết quả vô thời hạn. Phạm vi, thời hạn và mức nhạy cảm của đường tra cứu phải được định nghĩa rõ.

## 6. Mô hình trạng thái của operation

Một mô hình minh họa có thể gồm:

```text
RECEIVED
    → RUNNING
        ├─ SUCCEEDED
        ├─ REJECTED
        └─ OUTCOME_UNKNOWN
```

Các nhánh trên không có nghĩa mọi trạng thái đều được chuyển tùy ý. Cần định nghĩa các chuyển trạng thái cho từng loại lệnh.

| Trạng thái | Ý nghĩa | Cách xử lý lời gọi lại |
|---|---|---|
| `RECEIVED` | Lệnh đã được ghi nhận, chưa bắt đầu tác động | Có thể nhận quyền xử lý theo cơ chế đồng thời |
| `RUNNING` | Có một lần xử lý đang sở hữu bước thực thi | Trả trạng thái chờ hoặc tiếp tục theo contract, không chạy song song tùy ý |
| `SUCCEEDED` | Tác động đã commit và có kết quả bền vững | Trả trạng thái được phép xem, không thực thi lần nữa |
| `REJECTED` | Lệnh bị từ chối với kết quả nghiệp vụ đã ghi | Trả kết quả tương ứng cho cùng nội dung |
| `OUTCOME_UNKNOWN` | Chưa biết tác dụng phụ bên ngoài đã hoàn tất hay chưa | Đối chiếu với nguồn trước khi quyết định retry |

Một lỗi hạ tầng trước khi có tác động không nhất thiết là kết quả từ chối nghiệp vụ cuối cùng. Ngược lại, một lỗi timeout sau lời gọi bên ngoài không được tự gán thành “chưa làm gì”.

Không hạ `SUCCEEDED` về `RUNNING` vì response bị mất hoặc vì một bước thông báo sau đó thất bại. Trạng thái của hành động chính và trạng thái giao thông báo cần được quản lý riêng.

## 7. Phối hợp bản ghi idempotency với thay đổi credential

Một cách triển khai trong cùng cơ sở dữ liệu là dùng transaction để phối hợp:

1. Nhận diện và kiểm soát operation theo khóa duy nhất.
2. Kiểm tra nội dung trùng khớp và thẩm quyền thực thi.
3. Kiểm tra recovery grant đúng phạm vi, còn hiệu lực và chưa dùng.
4. Đổi credential hoặc ghi nhận quyền đăng ký yếu tố theo hành động được cho phép.
5. Tiêu thụ grant, lưu kết quả operation và ghi sự kiện outbox.
6. Commit toàn bộ thay đổi thuộc phạm vi transaction.

```text
Operation + grant consumption + credential change + outbox
    → một transaction trong miền có thẩm quyền
```

Nếu những phần này nằm ở các dịch vụ độc lập, một transaction cục bộ không đủ. Cần contract thực thi xuyên dịch vụ, operation có thể tra cứu và quy tắc đối chiếu rõ ràng. Không gọi một loạt request HTTP tuần tự là thao tác nguyên tử.

### Khung xử lý minh họa

```text
executeRecoveryCommand(command, caller):
    xác thực caller và phạm vi tenant
    phân giải nội dung có thẩm quyền
    xác định idempotency scope và fingerprint được bảo vệ

    bắt đầu transaction phù hợp:
        tìm hoặc tạo operation theo khóa duy nhất
        nếu operation đã tồn tại:
            nếu nội dung khác: trả xung đột
            nếu đã có kết quả cuối: trả trạng thái được phép xem
            nếu đang có chủ xử lý: trả trạng thái đang xử lý

        kiểm tra quyền, phiên bản, thời hạn và trạng thái grant
        thực hiện đúng hành động đã được cấp
        tiêu thụ grant một lần
        lưu kết quả operation
        ghi outbox event
    commit
```

Khung này mô tả nguyên tắc, không phải mã chạy hoàn chỉnh. Các nhánh trả kết quả phải được triển khai với cơ chế transaction, khóa và phân quyền đúng với hệ thống thực tế.

## 8. Hai lời gọi đồng thời và khoảng hở kiểm tra trước rồi ghi

Một lỗi phổ biến:

```text
Nếu chưa thấy key:
    thực hiện thay đổi
    lưu key đã xử lý
```

Hai worker có thể cùng không thấy key rồi cùng thực hiện. Việc kiểm tra trong bộ nhớ hoặc cache cục bộ không bảo vệ được toàn bộ các instance.

Cần có cơ chế phân xử bền vững tại nơi quản lý trạng thái, chẳng hạn ràng buộc duy nhất kết hợp transaction hoặc cập nhật có điều kiện. Worker thua trong cạnh tranh phải đọc operation đã có và áp dụng contract tương ứng, không tự chọn key khác.

Một ràng buộc SQL minh họa cho bảng operation:

```sql
UNIQUE (
    tenant_id,
    initiator_scope,
    command_type,
    idempotency_key
)
```

Ràng buộc này chỉ bảo vệ định danh lệnh. Nó không tự bảo đảm một grant không bị hai command khác key cùng sử dụng. Quyền dùng một lần cũng cần cập nhật có điều kiện hoặc ràng buộc phù hợp trong cùng điểm quyết định.

Ví dụ, hai command C1 và C2 có key khác nhau nhưng cùng dùng grant G. Dù mỗi key chỉ được xử lý một lần, G vẫn phải chỉ cho phép một hành động được chấp nhận. Đây là lớp kiểm soát độc lập với chống trùng key.

## 9. Worker bị dừng, lease hết hạn và fencing

Một operation dài có thể được worker nhận xử lý bằng lease. Nếu worker mất liên lạc, hệ thống có thể giao việc cho worker khác. Tuy nhiên, lease hết hạn không chứng minh worker cũ đã ngừng chạy.

Nếu cả hai còn có thể ghi, chúng có thể lặp tác dụng phụ hoặc ghi đè trạng thái mới. Cần một cơ chế làm cho chủ xử lý cũ không còn được chấp nhận tại nơi thay đổi trạng thái.

Một thiết kế có thể dùng phiên bản sở hữu tăng dần:

```text
worker-1 owns operation at executionVersion=5
lease expires
worker-2 acquires operation at executionVersion=6
write from worker-1 with version=5
    → rejected by the authoritative write path
```

Phiên bản phải được kiểm tra nơi tác động thực sự xảy ra, không chỉ ở bộ điều phối. Nếu dịch vụ bên ngoài không hỗ trợ cơ chế tương ứng, fencing ở cơ sở dữ liệu nội bộ không tự ngăn request cũ đã gửi tới bên đó.

Việc tiếp quản operation còn cần biết bước trước đã làm gì. Không đặt operation về trạng thái mới rồi chạy lại toàn bộ chỉ vì lease hết hạn. Với kết quả chưa rõ, ưu tiên tra cứu hoặc đối chiếu theo định danh ổn định.

## 10. Truyền idempotency qua nhiều dịch vụ

Giả sử bộ điều phối gửi lệnh đến dịch vụ danh tính và sau đó đến dịch vụ phiên. Mỗi bước cần định danh phù hợp, liên kết với operation gốc nhưng không nhất thiết dùng cùng một key cho mọi loại hành động.

```text
recoveryOperationId = operation-demo-19
    → credentialStepId = credential-step-demo-1
    → sessionStepId = session-step-demo-1
    → notificationStepId = notification-step-demo-1
```

Định danh bước giúp retry đúng tác động. Nếu dịch vụ nhận chỉ biết một key chung mà không kiểm tra command type hoặc nội dung, retry bước thu hồi phiên có thể bị nhầm với bước đổi credential.

Dịch vụ nhận phải kiểm tra nguồn lệnh, tenant, tài khoản, phạm vi và nội dung được cấp. Một payload có operation ID hợp lệ không tự có quyền ra lệnh cho mọi tài khoản.

Nếu bên đích hỗ trợ idempotency, các lần retry cùng bước cần giữ định danh và nội dung theo contract của bên đó. Không tạo key mới mỗi lần gọi vì timeout.

Nếu bên đích không hỗ trợ chống trùng hoặc tra cứu kết quả, không thể hứa tác dụng phụ đúng một lần chỉ bằng việc lưu một cờ ở bên gọi. Cần thay đổi cách tích hợp, chấp nhận rõ giới hạn hoặc đưa tình huống chưa rõ sang xử lý có kiểm soát.

## 11. Outbox, inbox và tác dụng phụ bên ngoài

Outbox giúp tránh khoảng hở giữa commit trạng thái nguồn và phát lệnh hoặc sự kiện. Có thể ghi kết quả operation và outbox trong cùng transaction, rồi để bộ chuyển tiếp giao lại khi cần.

Consumer có thể dùng inbox hoặc bản ghi event đã xử lý để nhận diện giao trùng. Với thay đổi trong cùng cơ sở dữ liệu của consumer, việc ghi inbox và tác động nghiệp vụ nên được phối hợp nhất quán.

Nhưng nếu consumer gọi một nhà cung cấp bên ngoài, hai lựa chọn đơn giản đều có khoảng hở:

```text
Đánh dấu đã xử lý trước → ứng dụng có thể dừng trước khi gọi bên ngoài
Gọi bên ngoài trước → ứng dụng có thể dừng trước khi đánh dấu đã xử lý
```

Idempotency phía đích hoặc khả năng tra cứu operation có thể giúp xử lý. Outbox và inbox không tự xóa được khoảng hở này cho mọi hệ thống.

Một thông báo bị gửi trùng không nhất thiết làm lặp thay đổi credential, nhưng vẫn có thể gây nhầm lẫn hoặc lạm dụng. Nếu thông báo mang liên kết bảo mật, không tự phát một token khác mỗi lần gửi lại mà không có quy tắc vòng đời rõ ràng.

Không ghi token thô vào log hoặc payload sự kiện rộng chỉ để gửi lại dễ hơn. Việc giao bí mật cần một cơ chế được bảo vệ, có phạm vi và thời hạn phù hợp.

## 12. Kết quả trả về và bí mật chỉ được cấp một lần

Không phải mọi kết quả thành công đều an toàn để lưu rồi trả lại nguyên văn. Một operation có thể tạo recovery code hoặc một quyền truy cập nhạy cảm chỉ được hiển thị trong ngữ cảnh đặc biệt.

Cần định nghĩa contract trả kết quả:

- Có thể trả lại metadata như operation ID, trạng thái và thời điểm hoàn tất khi người gọi có quyền xem.
- Không mặc định lưu toàn bộ HTTP response nếu nó chứa token, mật khẩu hoặc dữ liệu định danh nhạy cảm.
- Nếu cần cho phép lấy lại bí mật, phải có cơ chế bảo vệ và thời hạn riêng; idempotency key không được trở thành khóa đọc bí mật.
- Nếu bí mật không còn được phép trả lại, phản hồi trạng thái thành công không được tự tạo thêm một bí mật thay thế.

Ví dụ, retry sau khi recovery code mới đã được cấp không nên tạo thêm một bộ code vì response trước bị mất. Cần một luồng xử lý đã được thiết kế cho việc mất kết quả, với xác minh và thẩm quyền phù hợp nếu phải cấp lại.

Trạng thái HTTP hoặc nội dung phản hồi có thể khác giữa lần đầu và lần tra cứu lại, miễn contract rõ ràng và không làm client hiểu rằng cần thực hiện một hành động mới ngoài ý muốn.

## 13. Thời hạn thực thi khác thời gian giữ bản ghi chống trùng

Một lệnh có nhiều thời hạn liên quan:

| Thời hạn | Vai trò |
|---|---|
| Hạn quyền khôi phục | Giới hạn khả năng thực hiện hành động được cấp |
| Hạn quyết định phê duyệt | Giới hạn việc sử dụng quyết định theo chính sách |
| Hạn lease | Giới hạn quyền sở hữu một lượt xử lý kỹ thuật |
| Cửa sổ retry | Khoảng thời gian bên gọi được hỗ trợ thử lại theo contract |
| Hạn lưu operation | Khoảng thời gian giữ kết quả và dữ liệu chống trùng |

Retry không làm mới hạn quyền khôi phục. Job được tạo trước hạn cũng không tự giữ quyền thực thi sau hạn; dịch vụ có thẩm quyền cần kiểm tra tại điểm quyết định theo ngữ nghĩa đã chọn.

Sau khi operation đã commit, việc trả lại trạng thái thành công là quan sát kết quả cũ, không phải thực hiện lại hành động sau hạn. Đường quan sát vẫn cần kiểm tra quyền truy cập và giới hạn dữ liệu trả về.

Không xóa bản ghi chống trùng quá sớm rồi dựa vào nó như hàng rào duy nhất chống replay. Ngay cả khi kết quả chi tiết đã hết hạn lưu, trạng thái tiêu thụ hoặc thu hồi của grant và các ràng buộc bảo mật cần thiết vẫn phải được duy trì theo chính sách.

Phục hồi từ backup hoặc làm sạch dữ liệu vận hành không được khiến grant đã dùng trở lại có thể thực thi. Tính lặp an toàn cần được xem cùng vòng đời dữ liệu và khả năng phục hồi, không chỉ một TTL của cache.

## 14. Đối chiếu kết quả và vận hành retry

Khi chưa rõ kết quả, bộ điều phối cần hỏi đúng nguồn có thẩm quyền bằng operation ID hoặc định danh bước. Không suy luận thành công từ việc không còn message trong hàng đợi, cũng không suy luận thất bại từ việc chưa có event ở dashboard.

Một quy trình minh họa:

```text
Nhận timeout
    → giữ trạng thái chưa xác định ở bên gọi
    → tra cứu operation tại dịch vụ thực thi
    → nếu đã commit: đồng bộ kết quả
    → nếu chưa thực hiện: retry theo cùng contract
    → nếu chưa rõ: tiếp tục đối chiếu hoặc chuyển xử lý phù hợp
```

Retry nên có khoảng lùi, phân tán thời điểm thử lại và giới hạn vận hành để tránh làm quá tải dịch vụ đang gặp sự cố. Hết retry tự động không chứng minh tác dụng phụ chưa xảy ra; trạng thái nghiệp vụ cần được giữ đúng.

Nhật ký nên phân biệt command, operation, step và attempt. Các tín hiệu hữu ích gồm key bị dùng khác nội dung, nhiều attempt đồng thời, operation mắc kẹt, kết quả bên đích chưa rõ và sự kiện giao lại.

Không sửa operation thành `SUCCEEDED` chỉ để làm sạch cảnh báo. Việc đối chiếu cần có căn cứ từ hệ thống sở hữu tác động. Nếu không đủ căn cứ, duy trì trạng thái rõ và giới hạn các bước tiếp theo có thể làm tăng rủi ro.

## 15. Các tình huống thiết kế cần được làm rõ

Những tình huống sau minh họa hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Cùng key, cùng nội dung sau khi đã commit | Trả trạng thái được phép xem, không đổi credential lần nữa |
| Cùng key nhưng khác tài khoản hoặc payload | Từ chối xung đột, không ghi đè operation cũ |
| Hai instance nhận cùng key đồng thời | Cơ chế bền vững phân xử, chỉ một tác động được chấp nhận |
| Hai key khác nhau cùng dùng một grant | Tính dùng một lần của grant vẫn chặn hành động thứ hai |
| Phản hồi bị mất sau commit | Tra cứu operation, không mở lại quyền khôi phục |
| Worker cũ tiếp tục sau khi mất lease | Nơi ghi kiểm tra phiên bản sở hữu hoặc cơ chế tương đương |
| Bên ngoài có thể đã làm xong nhưng timeout | Đối chiếu theo định danh trước khi lặp tác dụng phụ |
| Event được giao lại | Consumer xử lý trùng theo contract, không tự tạo command mới |
| Kết quả chứa bí mật không được phép trả lại | Không tái cấp hoặc tiết lộ bí mật chỉ nhờ biết key |
| Quyền khôi phục đã hết hạn trước thực thi | Retry không gia hạn hoặc bỏ qua điều kiện thời gian |
| Bản ghi cache chống trùng đã hết hạn | Ràng buộc grant và trạng thái bền vững vẫn ngăn replay |

Những lỗi cốt lõi là coi key như quyền truy cập, chỉ chống trùng trong bộ nhớ, tạo key mới mỗi lần retry hoặc lưu cờ đã xử lý tách rời tác động nhạy cảm mà không có cơ chế nhất quán.

Một lệnh khôi phục có tính lặp an toàn cần định danh đúng ý định, ràng buộc đúng nội dung, có quyền thực thi hợp lệ và lưu kết quả ở nơi sở hữu tác động. Khi có lỗi phân tán, retry phải tìm lại hoặc tiếp tục cùng operation theo contract, thay vì tạo thêm quyền đặt lại mật khẩu, MFA hoặc passkey ngoài quyết định ban đầu.
