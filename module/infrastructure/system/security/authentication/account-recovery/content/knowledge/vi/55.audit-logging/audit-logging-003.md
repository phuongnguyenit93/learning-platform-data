# Recovery outcome recording

## 1. Ghi nhận kết quả recovery là ghi nhận điều gì?

Ghi nhận kết quả khôi phục tài khoản là lưu lại những sự kiện và quyết định đủ để giải thích một yêu cầu đã đi tới đâu, vì sao dừng ở đó và những tác động an toàn nào thực sự xảy ra.

Trong luồng khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, một dòng log như `recovery success` thường không đủ. Nó không cho biết:

- Người dùng mới xác minh được một kênh hay đã đủ điều kiện recovery.
- Token đã được tiêu thụ hay chỉ được kiểm tra hợp lệ.
- Credential đã thay đổi thành công hay mới được lên lịch thay đổi.
- Session cũ đã bị thu hồi theo chính sách hay dịch vụ session mới nhận yêu cầu.
- Thao tác hỗ trợ là đề xuất, phê duyệt hay thực thi.
- Kết quả là trạng thái đã commit hay chỉ là điều ứng dụng định làm.

Mục tiêu của audit là tạo một lịch sử có thể giải thích, đối chiếu và điều tra. Audit không thay thế trạng thái nghiệp vụ có thẩm quyền, cũng không biến một quyết định thiếu bằng chứng thành quyết định đúng.

Ví dụ xuyên suốt: người dùng mất điện thoại chứa MFA, vượt qua xác minh bổ sung, đăng ký lại yếu tố xác thực và yêu cầu thu hồi các session theo chính sách. Hệ thống cần phân biệt rõ từng kết quả, nhất là khi lời gọi giữa các dịch vụ bị timeout.

## 2. Phân biệt yêu cầu, lần thử và thao tác

Một mô hình đơn giản có ba cấp:

| Cấp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Yêu cầu recovery | Toàn bộ hồ sơ hoặc quy trình khôi phục | Khôi phục MFA sau khi mất điện thoại |
| Lần thử | Một lần tương tác trong một bước | Nhập mã xác minh lần thứ hai |
| Thao tác có tác động | Một thay đổi hoặc một công việc cụ thể | Đổi credential, thu hồi session, gửi thông báo |

Một yêu cầu có thể chứa nhiều lần thử và nhiều thao tác. Một lần thử thất bại không mặc nhiên làm toàn bộ yêu cầu thất bại.

Nên có định danh tách biệt:

```text
recovery_id   = định danh yêu cầu
attempt_id    = định danh một lần thử
operation_id  = định danh một thao tác nghiệp vụ
event_id      = định danh một sự kiện audit
```

Một thao tác được retry nên giữ ràng buộc với cùng operation ID theo thiết kế idempotency. Các sự kiện diễn tả những giai đoạn khác nhau của nó vẫn có event ID khác nhau.

Ngược lại, việc phát lại cùng một sự kiện do hàng đợi gửi lặp phải giữ nguyên event ID. Nếu mỗi lần chuyển tiếp tạo một ID mới, hệ thống nhận khó phân biệt gửi lặp với một sự kiện nghiệp vụ mới.

## 3. Tách trạng thái quy trình khỏi kết quả sự kiện

Trạng thái cho biết yêu cầu đang ở đâu. Kết quả cho biết một bước hoặc thao tác vừa diễn ra thế nào.

Ví dụ về trạng thái khái niệm:

```text
PENDING_VERIFICATION
    → PENDING_APPROVAL
    → APPLYING_SECURITY_CHANGES
    → COMPLETED

Các nhánh kết thúc khác:
REJECTED, EXPIRED, CANCELLED
```

Tên trạng thái cụ thể do hệ thống định nghĩa; điều quan trọng là mỗi trạng thái có điều kiện vào rõ ràng.

Một sự kiện có thể mang kết quả:

| Kết quả | Diễn giải |
| --- | --- |
| SUCCEEDED | Tác động hoặc bước được mô tả đã đạt điều kiện thành công |
| FAILED | Đã xác định bước hoặc thao tác không thành công |
| DENIED | Bị chính sách từ chối |
| PENDING | Đã ghi nhận nhưng chưa đủ điều kiện kết luận |
| UNKNOWN | Chưa xác định được tác động có xảy ra hay không |

Không dùng `FAILED` chỉ vì client hết thời gian chờ. Server hoặc dịch vụ đích có thể đã commit dù phản hồi không tới được client.

Ví dụ, `IDENTITY_EVIDENCE_ACCEPTED / SUCCEEDED` chỉ nói rằng bằng chứng đã được chấp nhận ở bước đó. Nó không đồng nghĩa `RECOVERY_COMPLETED`.

Tương tự, `SESSION_REVOCATION_REQUESTED / SUCCEEDED` có thể chỉ xác nhận đã lưu một yêu cầu thu hồi. Nếu sản phẩm cần bảo đảm session không còn được chấp nhận trước khi mở lại tài khoản, phải có điều kiện xác nhận hiệu lực tương ứng.

## 4. Định nghĩa chính xác khi nào recovery thành công

Trước khi ghi sự kiện hoàn tất, cần xác định hợp đồng thành công của loại recovery.

Với khôi phục MFA, hợp đồng có thể yêu cầu:

1. Bằng chứng và mức xác minh đạt chính sách áp dụng.
2. Phê duyệt và thời gian chờ bắt buộc đã được đáp ứng.
3. Quyền recovery hoặc challenge dùng một lần đã được tiêu thụ đúng cách.
4. Yếu tố xác thực mới đã được thiết lập theo quy trình.
5. Yếu tố cũ đã được xử lý theo quyết định an toàn.
6. Các session thuộc phạm vi thu hồi đã đạt điều kiện vô hiệu hóa được quy định.
7. Các quyền tạm cấp cho recovery đã hết hiệu lực theo thiết kế.

Không phải hệ thống nào cũng chọn cùng một hợp đồng. Có hệ thống cho phép hoàn tất một phần và giữ tài khoản ở trạng thái hạn chế trong lúc tác động khác tiếp tục xử lý. Khi đó, tên trạng thái và audit phải diễn tả đúng việc còn lại.

Không lấy “API trả HTTP 200” làm định nghĩa chung cho thành công. Một API có thể trả thành công vì đã tiếp nhận công việc bất đồng bộ, trong khi công việc chưa hoàn tất.

Cũng không coi việc gửi email thành công là bằng chứng rằng chủ tài khoản đã khôi phục quyền kiểm soát.

## 5. Ai là người thực hiện, tài khoản nào bị tác động?

Audit cần phân biệt actor và subject:

- **Actor** là bên thực hiện hành động: người yêu cầu, nhân viên hỗ trợ, dịch vụ hoặc tác vụ tự động.
- **Subject** là tài khoản mà recovery tác động tới.
- **Approver** là bên phê duyệt nếu quy trình có bước phê duyệt.
- **Executor** là dịch vụ thực thi thay đổi nếu khác với bên ra quyết định.

Một người nhập email của nạn nhân không được ghi nhận như chính nạn nhân đã xác thực.

Có thể biểu diễn actor chưa xác minh như sau:

```text
actor_type = UNAUTHENTICATED_CLAIMANT
authenticated_principal_id = null
subject_binding = RESOLVED_INTERNALLY
```

Nếu tài khoản chưa được xác định đáng tin cậy, để subject trống hoặc dùng tham chiếu được kiểm soát phù hợp. Không suy subject từ một recovery ID do client tự gửi mà chưa kiểm tra.

Với tác vụ hỗ trợ, cần ghi riêng người đề nghị và người phê duyệt. Dịch vụ thực thi không nên làm mất dấu người đã cấp quyền cho hành động.

Tenant, chủ thể và mục đích recovery phải được xác định từ ngữ cảnh tin cậy và dữ liệu chuẩn. Chúng không phải các trường mà client được tự chọn để làm thay đổi ý nghĩa audit.

## 6. Schema sự kiện đủ dùng

Schema sau là mô hình minh họa, không phải chuẩn bắt buộc:

```text
RecoveryAuditEvent
  schema_version
  event_id
  event_type
  occurred_at
  recorded_at
  source_service
  source_instance_ref
  tenant_id
  recovery_id
  attempt_id
  operation_id
  subject_ref
  actor
  stage
  outcome
  reason_code
  state_before
  state_after
  aggregate_version
  policy_version
  evidence_refs
  causal_event_id
  correlation_id
```

Những nhóm trường quan trọng:

| Nhóm | Câu hỏi được trả lời |
| --- | --- |
| Định danh sự kiện và nguồn | Sự kiện nào, do thành phần nào tạo? |
| Phạm vi recovery | Yêu cầu, tenant, tài khoản và thao tác nào? |
| Actor và vai trò | Ai khởi tạo, phê duyệt hoặc thực thi? |
| Kết quả và lý do | Điều gì được xác nhận, vì sao có kết quả đó? |
| Trạng thái và phiên bản | Thay đổi nào đã được commit? |
| Chính sách và tham chiếu bằng chứng | Quyết định dựa trên phiên bản và hồ sơ nào? |
| Thời gian và quan hệ nhân quả | Sự kiện xảy ra khi nào, liên quan sự kiện nào? |

`occurred_at` và `recorded_at` có thể khác nhau khi vận chuyển bị trễ. Thời gian do client gửi chỉ nên là dữ liệu phụ nếu cần; không lấy nó làm thời gian có thẩm quyền của thay đổi nghiệp vụ.

`evidence_refs` trỏ tới bằng chứng được bảo vệ trong kho riêng. Không nhúng ảnh giấy tờ, nội dung xác minh hay bản sao secret vào sự kiện.

`policy_version` giúp giải thích chính sách tại thời điểm quyết định. Nếu có thành phần đánh giá rủi ro, lưu tham chiếu quyết định hoặc phiên bản cần thiết theo quyền truy cập, thay vì sao chép toàn bộ đặc trưng nhạy cảm sang mọi nơi.

## 7. Ví dụ ghi một kết quả đã được xác nhận

Giả sử hệ thống chỉ phát `RECOVERY_COMPLETED` sau khi credential mới được commit và các tác động bắt buộc đối với session đã đạt điều kiện theo chính sách.

```json
{
  "schema_version": 1,
  "event_id": "evt_8fd2c1",
  "event_type": "RECOVERY_COMPLETED",
  "occurred_at": "2026-11-24T03:10:24Z",
  "recorded_at": "2026-11-24T03:10:25Z",
  "source_service": "account-recovery",
  "tenant_id": "tenant_17",
  "recovery_id": "rec_6c9ab2",
  "operation_id": "op_5e10d8",
  "subject_ref": "subject_42",
  "actor": {
    "type": "RECOVERY_SESSION",
    "principal_ref": "recovery_session_31"
  },
  "stage": "FINALIZATION",
  "outcome": "SUCCEEDED",
  "reason_code": "REQUIRED_EFFECTS_CONFIRMED",
  "state_before": "APPLYING_SECURITY_CHANGES",
  "state_after": "COMPLETED",
  "aggregate_version": 18,
  "policy_version": "mfa-recovery-policy-v7",
  "evidence_refs": [
    "proofing_decision_25",
    "credential_change_73",
    "session_revocation_91"
  ],
  "causal_event_id": "evt_7aa9e0",
  "correlation_id": "corr_83ca19"
}
```

Các ID trong ví dụ là dữ liệu giả, không chứa token. `principal_ref` của một recovery session cũng không phải cookie hay bearer credential để dùng lại.

Sự kiện chứng minh hệ thống đã ghi nhận các điều kiện trong hợp đồng thành công của nó. Nó không tự chứng minh rằng mọi đánh giá danh tính trước đó đều đúng; điều tra vẫn có thể phải xem bằng chứng và quyết định liên quan.

Nếu mới xác nhận yêu cầu thu hồi session đã được tiếp nhận, chưa đủ điều kiện hiệu lực theo hợp đồng trên, sự kiện phù hợp phải là sự kiện trung gian.

## 8. Ghi nhận cùng ranh giới commit

Một lỗi thiết kế là ghi “thành công” trước giao dịch:

```text
Ghi log RECOVERY_COMPLETED
→ cập nhật credential
→ giao dịch rollback
```

Audit lúc này khẳng định một điều chưa xảy ra.

Chiều ngược lại cũng có vấn đề:

```text
Commit kết quả recovery
→ tiến trình dừng
→ chưa gửi sự kiện tới kho audit
```

Có thể dùng một bản ghi audit bền vững hoặc outbox trong cùng miền giao dịch với thay đổi trạng thái:

```text
transaction:
    validateExpectedStateAndVersion()
    applyAllowedTransition()
    persistAuditEvent()
    persistOutboxReference()

commit
```

`persistAuditEvent` ghi sự kiện theo chuyển trạng thái thực tế; outbox tham chiếu sự kiện đó để vận chuyển tới kho audit tập trung. Có thể dùng outbox làm bản ghi sự kiện bền vững ban đầu nếu thiết kế bảo đảm nội dung và quyền lưu trữ cần thiết.

Đây là bảo đảm trong một miền giao dịch. Nó không khiến thay đổi ở dịch vụ credential, session và email tự trở thành một giao dịch duy nhất.

### Khi audit tạm thời không khả dụng

Cần phân biệt kho audit tập trung bị gián đoạn với việc không còn chỗ lưu dấu vết bền vững tại nguồn.

- Nếu sự kiện đã được lưu bền vững tại nguồn, có thể chuyển tiếp lại theo chính sách và giới hạn dung lượng.
- Nếu không thể lưu dấu vết bắt buộc trước một thay đổi nhạy cảm, cần giữ hoặc từ chối chuyển trạng thái theo chính sách đã định.
- Nếu tác động đã xảy ra ở dịch vụ khác, lỗi ghi audit không được biến lịch sử thành “chưa xảy ra”. Phải đối soát và ghi nhận sự thật khi phục hồi.
- Không tiếp tục cấp quyền recovery rộng hơn chỉ để vượt qua sự cố logging.

Thông báo cho người dùng có thể giữ mức chi tiết phù hợp; nguyên nhân hạ tầng được ghi trong kênh nội bộ có kiểm soát.

## 9. Kết quả chưa rõ trong hệ thống nhiều dịch vụ

Giả sử dịch vụ recovery gọi đổi credential và bị timeout:

```text
Recovery Service → Credential Service
                ← phản hồi bị mất
```

Có ít nhất hai khả năng:

1. Credential Service chưa áp dụng thay đổi.
2. Credential Service đã áp dụng thay đổi nhưng phản hồi bị thất lạc.

Ngay lúc timeout, kết luận an toàn là chưa biết tác động, không tự chọn thất bại.

Một chuỗi sự kiện minh họa:

```text
CREDENTIAL_CHANGE_REQUESTED
CREDENTIAL_CHANGE_RESULT_UNKNOWN
CREDENTIAL_CHANGE_CONFIRMED
SESSION_REVOCATION_REQUESTED
SESSION_REVOCATION_CONFIRMED
RECOVERY_COMPLETED
```

Dùng operation ID để tra cứu hoặc retry có idempotency. Sau khi đối soát được trạng thái có thẩm quyền, ghi một sự kiện xác nhận mới và liên kết với thao tác ban đầu.

Không xóa sự kiện `RESULT_UNKNOWN` vì nó vẫn giải thích điều gì đã xảy ra trong quá trình vận hành.

Nếu phải thực hiện hành động bù, ghi riêng hành động bù và kết quả của nó. Một thay đổi credential đã commit rồi được xử lý tiếp không tương đương với giao dịch ban đầu chưa từng xảy ra.

Khi sự kiện đi qua nhiều dịch vụ, cần biết nguồn nào có thẩm quyền xác nhận từng tác động. Một worker điều phối không được tự khẳng định dịch vụ session đã thực thi chỉ vì nó đã gửi thông điệp vào hàng đợi.

## 10. Ghi nhận từ chối, hết hạn và hủy đúng nghĩa

### 10.1. Thất bại xác minh

Ghi cấp bước hoặc lần thử, nhóm nguyên nhân và tác động lên trạng thái yêu cầu. Không lưu đáp án sai hay mã OTP người dùng đã nhập.

Ví dụ:

```text
event_type = VERIFICATION_ATTEMPT_REJECTED
stage = CHANNEL_VERIFICATION
outcome = DENIED
reason_code = CHALLENGE_NOT_ACCEPTED
request_state_after = PENDING_VERIFICATION
```

Mã lý do chi tiết hơn có thể được giữ ở miền nội bộ phù hợp. Không biến nội dung này thành API công khai cho người chưa đủ quyền xem.

### 10.2. Từ chối theo chính sách

Phân biệt quyết định tự động và quyết định thủ công. Ghi tham chiếu chính sách, người phê duyệt nếu có và trạng thái sau quyết định.

Không lưu một đoạn ghi chú tự do chứa dữ liệu giấy tờ hoặc phỏng đoán nhạy cảm trong trường `reason_code`. Dùng mã phân loại và tham chiếu hồ sơ được bảo vệ.

### 10.3. Hết hạn

Tách thời điểm hết hiệu lực theo chính sách khỏi thời điểm tác vụ nền phát hiện và ghi sự kiện hết hạn. Nếu ghi muộn, không sửa thời gian để làm như tác vụ đã chạy đúng lúc.

Việc challenge đã hết hiệu lực được quyết định bởi kiểm tra thời hạn tại nơi xác minh, không phụ thuộc vào lúc audit nhận sự kiện.

### 10.4. Hủy yêu cầu

Ghi rõ hủy do ai và đã có hiệu lực chưa. “Đã tiếp nhận yêu cầu hủy” khác với “mọi thao tác đang chạy đã dừng”.

Nếu một thao tác bên ngoài đã commit trước khi hủy, lịch sử phải giữ tác động đó. Không ghi một kết quả hủy chung làm người đọc tưởng không có credential nào từng thay đổi.

## 11. Chống trùng và sắp xếp lịch sử đúng

Kho audit thường có thể nhận sự kiện lặp hoặc tới không đúng thứ tự. Cần thiết kế để lịch sử vẫn đọc được.

- Dùng event ID ổn định và cơ chế nhận lặp an toàn.
- Xác định phạm vi duy nhất của event ID; nếu chỉ duy nhất trong từng nguồn, dùng thêm định danh nguồn.
- Dùng phiên bản của aggregate khi cần sắp xếp chuyển trạng thái thuộc cùng yêu cầu.
- Giữ quan hệ nhân quả giữa sự kiện điều phối và xác nhận tác động.
- Theo dõi khoảng trống phiên bản hoặc sự kiện dự kiến chưa tới.
- Không suy trạng thái cuối chỉ từ sự kiện có timestamp lớn nhất.

Phiên bản của hai dịch vụ khác nhau không tự có cùng ý nghĩa. Không so sánh `version=20` của dịch vụ session với `version=18` của dịch vụ recovery rồi kết luận thứ tự toàn cục.

Nếu nhận cùng event ID nhưng nội dung khác, cần phát hiện xung đột và điều tra. Không ghi đè âm thầm để bản đến sau thay lịch sử.

Lịch sử hiển thị cho hỗ trợ có thể là một projection dễ đọc. Projection đó cần phân biệt sự kiện thực tế, dữ liệu dẫn xuất và trạng thái đang chờ đối soát.

## 12. Giảm dữ liệu nhạy cảm trong outcome record

Audit recovery thường gắn với dữ liệu có giá trị cao. Một bộ log quá đầy đủ có thể trở thành nơi đánh cắp bí mật thuận tiện hơn chính hệ thống xác thực.

Không ghi:

- Mật khẩu mới hoặc cũ.
- Token recovery, cookie, authorization header hoặc URL chứa secret.
- OTP, recovery code và secret MFA.
- Private key, dữ liệu seed hoặc vật liệu khóa passkey.
- Ảnh giấy tờ hoặc toàn bộ nội dung xác minh danh tính.
- Payload request và response nguyên vẹn nếu chứa các trường trên.

Ghi tham chiếu nội bộ thay cho nội dung nhạy cảm khi có thể. Tham chiếu vẫn cần phân quyền vì có thể liên kết tới tài khoản thật.

Băm email hoặc số điện thoại không tự làm dữ liệu trở thành vô danh. Không gian giá trị có thể đoán được; kẻ có dữ liệu và cách băm có thể thử đối chiếu. Nếu cần khả năng liên kết có kiểm soát, cân nhắc định danh nội bộ hoặc cơ chế có khóa theo mô hình đe dọa, cùng chính sách truy cập và vòng đời.

Nội dung do người dùng nhập phải được mã hóa hoặc escape đúng tại nơi hiển thị, giới hạn độ dài và tránh chèn vào cấu trúc log như một chuỗi điều khiển. Ưu tiên trường có kiểu và danh mục giá trị rõ ràng.

## 13. Nguồn tin cậy và bảo vệ lịch sử

Sự kiện về thay đổi credential phải đến từ nguồn được phép xác nhận thay đổi đó. Không chấp nhận `outcome=SUCCEEDED` do client gửi như sự thật nghiệp vụ.

Cần phân quyền theo vai trò:

| Vai trò | Quyền phù hợp |
| --- | --- |
| Dịch vụ tạo sự kiện | Ghi sự kiện thuộc miền được cấp |
| Bộ chuyển tiếp | Đọc hàng chờ và chuyển tiếp, không tự sửa quyết định |
| Hỗ trợ | Đọc phần lịch sử cần thiết theo quyền |
| Điều tra an toàn | Truy cập mở rộng có kiểm soát và dấu vết |
| Vận hành lưu trữ | Quản lý hạ tầng với giới hạn về đọc và sửa dữ liệu |

Tài khoản dịch vụ recovery không nên có khả năng xóa tùy ý toàn bộ audit sau khi tạo sự kiện.

Có thể bổ sung lưu trữ chống sửa, chuỗi băm, chữ ký hoặc checkpoint độc lập để phát hiện can thiệp. Những cơ chế này cần mô hình khóa, điểm neo tin cậy và vận hành thực tế.

Một chuỗi băm nằm hoàn toàn trong cùng kho mà đối thủ có thể ghi lại không tự chứng minh lịch sử chưa bị sửa. Chữ ký hợp lệ cũng chỉ cho biết nguồn có khóa đã ký nội dung, không chứng minh quyết định danh tính trong nội dung là chính xác.

Sửa dữ liệu sai nên tạo sự kiện đính chính có tham chiếu và quyền phù hợp. Việc giữ lịch sử không có nghĩa được lưu mọi dữ liệu cá nhân vô thời hạn; cần chính sách lưu giữ, xóa và xử lý bản sao tương ứng.

## 14. Đọc một chuỗi outcome để điều tra

Một timeline có thể diễn ra như sau:

| Thứ tự nhân quả | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| 1 | RECOVERY_REQUEST_CREATED | Có một yêu cầu được tạo |
| 2 | VERIFICATION_ATTEMPT_REJECTED | Một lần thử chưa đạt, yêu cầu vẫn mở |
| 3 | IDENTITY_EVIDENCE_ACCEPTED | Bước bằng chứng đạt điều kiện |
| 4 | RECOVERY_APPROVED | Chính sách cho phép thực hiện các thay đổi đã xác định |
| 5 | CREDENTIAL_CHANGE_RESULT_UNKNOWN | Chưa biết kết quả do gián đoạn phản hồi |
| 6 | CREDENTIAL_CHANGE_CONFIRMED | Đối soát xác nhận credential đã đổi |
| 7 | SESSION_REVOCATION_CONFIRMED | Điều kiện thu hồi bắt buộc đã đạt |
| 8 | RECOVERY_COMPLETED | Hợp đồng hoàn tất của yêu cầu đã được đáp ứng |

Khi đọc chuỗi này, người điều tra cần trả lời được:

- Ai yêu cầu và actor đã có mức xác minh nào ở từng thời điểm?
- Quyết định phê duyệt dựa trên chính sách và bằng chứng nào?
- Thay đổi nào thực sự đã xảy ra?
- Vì sao có khoảng chờ giữa các bước?
- Có session hoặc quyền recovery tạm nào còn hiệu lực không?
- Có sự kiện nào thiếu, trùng hoặc xung đột không?

Không bỏ qua lần thử thất bại chỉ vì sau đó yêu cầu thành công. Nó có thể là lỗi nhập bình thường hoặc một dấu hiệu quan trọng khi đối chiếu hoạt động khác.

## 15. Những lỗi ghi nhận dễ gây kết luận sai

**Ghi thành công trước commit.** Lịch sử có thể khẳng định một thay đổi đã bị rollback.

**Đồng nhất timeout với thất bại.** Retry có thể thực hiện thêm một tác động mà lần đầu đã hoàn tất.

**Đồng nhất xác minh kênh với xác minh danh tính đầy đủ.** Khả năng nhận một mã không mặc nhiên đủ quyền bỏ MFA hoặc thay passkey.

**Ghi actor là chủ tài khoản ngay khi họ nhập username.** Lịch sử gán hành vi của người chưa xác minh cho nạn nhân.

**Dùng “session revoked” cho việc mới gửi yêu cầu thu hồi.** Người đọc có thể tưởng các session đã hết hiệu lực.

**Chỉ có log ứng dụng và không có dấu vết bền vững gắn với trạng thái.** Sự cố tiến trình có thể để lại thay đổi mà không có bằng chứng dự kiến.

**Ghi đè sự kiện chưa rõ kết quả.** Mất thông tin cần giải thích retry, đối soát và thời gian gián đoạn.

**Đưa secret vào audit để hỗ trợ dễ tra cứu.** Audit trở thành nguồn lộ quyền recovery và thông tin xác thực.

Một outcome record hữu ích phải nói đúng điều đã được xác nhận, giữ rõ phạm vi của kết quả, liên kết được actor và bằng chứng, đồng thời bảo vệ bí mật của chính luồng khôi phục.
