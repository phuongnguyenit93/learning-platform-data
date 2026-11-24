# Recovery structured logging

## 1. Structured logging giúp hiểu luồng khôi phục như thế nào?

Một luồng khôi phục tài khoản có thể đi qua API, kiểm tra rủi ro, xác minh bằng chứng, cập nhật credential, thu hồi session và gửi thông báo. Khi xảy ra lỗi, một câu như “recovery failed” không cho biết bước nào thất bại, kết quả có được commit hay không hoặc dịch vụ phụ thuộc nào gặp sự cố.

Structured logging ghi sự kiện thành các trường có tên, kiểu dữ liệu và ý nghĩa ổn định. Người vận hành có thể lọc theo bước, kết quả, mã nguyên nhân và định danh tương quan mà không phải phân tích hàng loạt câu mô tả tùy ý.

So sánh hai bản ghi minh họa:

```text
Recovery failed for user alice, token=..., error=...
```

```json
{
  "event_name": "recovery.evidence_verification",
  "outcome": "DENIED",
  "reason_code": "EVIDENCE_INVALID",
  "recovery_request_ref": "rr_example_27",
  "duration_ms": 18.4
}
```

Bản ghi thứ hai diễn đạt kết quả kiểm tra mà không cần ghi token hoặc tên người dùng. Tuy nhiên, chỉ đổi định dạng sang JSON không bảo đảm log an toàn hoặc đủ thông tin. Cần thiết kế cả schema, nguồn dữ liệu, thời điểm phát và cách quản lý dữ liệu nhạy cảm.

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes) hướng dẫn ghi đủ thông tin về thời điểm, nơi xảy ra, chủ thể và hành động. Với account recovery, những nhóm đó phải phản ánh đúng giới hạn xác minh và trạng thái thực tế của quy trình.

## 2. Phân biệt log quan sát với audit và dữ liệu nghiệp vụ

Ba nguồn sau có thể liên kết nhưng không thay thế nhau:

| Nguồn | Câu hỏi chính | Giới hạn cần nhớ |
| --- | --- | --- |
| Dữ liệu nghiệp vụ | Request, token và credential hiện đang ở trạng thái nào? | Là nguồn quyết định hành động theo thiết kế, không phải chỉ một dòng thông báo |
| Audit bảo mật | Ai thực hiện thay đổi nhạy cảm nào, trên đối tượng nào, với kết quả gì? | Cần hợp đồng lưu giữ và bảo vệ phù hợp |
| Log quan sát | Bước nào chậm, lỗi ở đâu, các thành phần phối hợp ra sao? | Có thể bị trễ, mất, lặp hoặc giảm mức chi tiết theo cấu hình |

Một dòng log “token consumed” không phải cơ chế ngăn token dùng lại. Tính dùng một lần phải được bảo vệ tại nơi xử lý trạng thái có thẩm quyền.

Tương tự, log JSON gửi lên nền tảng quan sát không tự trở thành audit bền vững. Nếu log quan sát bị sampling hoặc hết thời hạn sớm, không thể dùng sự vắng mặt của một dòng để kết luận một thay đổi chưa từng xảy ra.

Có thể dùng cùng một schema nền tảng hoặc cùng định danh sự kiện ở các nguồn, nhưng phải xác định rõ luồng nào chịu trách nhiệm cho bằng chứng bảo mật bắt buộc và luồng nào phục vụ chẩn đoán.

## 3. Xây dựng hợp đồng schema

Một schema minh họa có thể chia thành các nhóm sau:

| Nhóm | Trường ví dụ | Ý nghĩa |
| --- | --- | --- |
| Phiên bản | `schema_version` | Giúp bên nhận diễn giải đúng cấu trúc |
| Thời gian | `timestamp`, `observed_timestamp` | Thời điểm xảy ra và thời điểm được hệ thống thu thập quan sát |
| Nguồn phát | `service.name`, `service.version`, `environment` | Thành phần và phiên bản phát log |
| Loại sự kiện | `event_name`, `step` | Công việc hoặc ranh giới xử lý đang được mô tả |
| Kết quả | `outcome`, `reason_code` | Phân biệt kết quả nghiệp vụ và nguyên nhân |
| Mức độ | `severity` | Mức ưu tiên vận hành theo chính sách |
| Tương quan | `interaction_ref`, `recovery_request_ref`, `event_id` | Nối các tương tác, workflow và sự kiện |
| Trace | `trace_id`, `span_id` | Liên kết tới ngữ cảnh trace khi có |
| Chủ thể | `actor.kind`, `actor.principal_ref` | Loại chủ thể và danh tính đã được biết |
| Đo lường tại bước | `duration_ms`, `attempt_number` | Thời lượng xử lý và lần thực thi của thao tác |
| Phụ thuộc | `dependency.name`, `dependency.result` | Kết quả gọi thành phần bên ngoài nếu có |

Đây là schema đề xuất trong bài, không phải bộ tên trường chuẩn cho mọi nền tảng.

[OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) phân biệt Timestamp với ObservedTimestamp và có các trường trace context, severity, body cùng attributes. Khi ánh xạ schema ứng dụng sang OpenTelemetry, cần giữ đúng ý nghĩa trường; không giả định tên JSON trong ví dụ chính là tên hoặc cách mã hóa trên giao thức OTLP.

Chọn kiểu dữ liệu rõ ràng: `duration_ms` là số, `attempt_number` là số nguyên, không lúc là số lúc là chuỗi “18 ms”. Dùng đơn vị cố định và định nghĩa cách biểu diễn trường chưa biết.

Tên sự kiện và mã nguyên nhân nên có tập giá trị được quản lý. Không tạo một tên sự kiện mới cho từng tài khoản, URL hoặc nội dung exception.

## 4. Ghi tại ranh giới nghiệp vụ có ý nghĩa

Không cần ghi mọi biến cục bộ hoặc mọi lần đọc cơ sở dữ liệu. Cần chọn các ranh giới giúp giải thích quy trình:

- Tiếp nhận một tương tác khôi phục.
- Hoàn tất đánh giá rủi ro tại bước liên quan.
- Chấp nhận hoặc từ chối một lần xác minh bằng chứng.
- Cấp quyền khôi phục giới hạn.
- Commit thay đổi mật khẩu, MFA hoặc ràng buộc passkey.
- Ghi nhận hoặc hoàn tất tác động thu hồi session theo thiết kế.
- Tiếp nhận, thử lại hoặc thất bại khi chuyển thông báo.
- Phát hiện lỗi hạ tầng khiến kết quả xử lý chưa rõ.

Tên và kết quả phải khớp với ranh giới đã đạt. Ví dụ:

| Điều thực sự xảy ra | Cách ghi phù hợp | Cách ghi dễ gây hiểu sai |
| --- | --- | --- |
| Request đã được đưa vào hàng đợi | `outcome=ACCEPTED` cho bước tiếp nhận | `recovery.completed` |
| Bằng chứng không được chấp nhận | `outcome=DENIED` với mã nguyên nhân nội bộ | Mọi trường hợp đều là lỗi hệ thống |
| Credential đã commit | Sự kiện về thay đổi đã commit | Thành công trước khi transaction kết thúc |
| Lệnh thu hồi session đang chờ | Kết quả tiếp nhận hoặc chờ xử lý | “Mọi session đã bị thu hồi” |
| Mất kết nối trong lúc nhận xác nhận commit | Kết quả chưa xác định nếu đúng trạng thái đã biết | Khẳng định chắc chắn rollback |
| Nhà cung cấp email nhận yêu cầu | Kết quả nhà cung cấp chấp nhận | “Chủ tài khoản đã đọc thông báo” |

Không coi HTTP 200 là thành công nghiệp vụ. Endpoint công khai có thể trả thông điệp thống nhất để hạn chế dò tài khoản, trong khi kết quả xử lý nội bộ khác nhau và cần được bảo vệ riêng.

## 5. Ví dụ bản ghi có cấu trúc

Bản ghi sau minh họa một lần xác minh bằng chứng bị từ chối. Nó đã được bổ sung thời điểm quan sát tại lớp thu thập:

```json
{
  "schema_version": 1,
  "event_id": "evt_example_603",
  "timestamp": "2026-11-24T10:30:00.000Z",
  "observed_timestamp": "2026-11-24T10:30:00.240Z",
  "severity": "INFO",
  "service": {
    "name": "security-authentication-account-recovery",
    "version": "1.0.0-example"
  },
  "environment": "production",
  "event_name": "recovery.evidence_verification",
  "step": "VERIFY_RECOVERY_EVIDENCE",
  "outcome": "DENIED",
  "reason_code": "EVIDENCE_INVALID",
  "interaction_ref": "int_example_52",
  "recovery_request_ref": "rr_example_27",
  "trace_id": "f47ac10b58cc4372a5670e02b2c3d479",
  "span_id": "a1b2c3d4e5f60718",
  "actor": {
    "kind": "RECOVERY_CLAIMANT",
    "principal_ref": null
  },
  "duration_ms": 18.4,
  "attempt_number": 1,
  "message": "Recovery evidence verification was denied"
}
```

Các định danh và giá trị là dữ liệu giả. `message` là câu do ứng dụng kiểm soát để hỗ trợ con người đọc; truy vấn không nên phụ thuộc vào việc tách chuỗi từ câu này.

`actor.principal_ref=null` diễn đạt rằng sự kiện này chưa gắn với một principal đã xác thực. Không điền ID tài khoản mục tiêu vào actor chỉ vì người gọi nhập email tương ứng.

`attempt_number` trong ví dụ là số lần thực thi của thao tác được định nghĩa, không mặc nhiên là tổng số lần một người đã thử khôi phục. Nếu cần theo dõi hai đại lượng khác nhau, dùng hai trường với ý nghĩa riêng.

Mức INFO chỉ minh họa một kết quả từ chối dự kiến. Chính sách có thể nâng mức khi xuất hiện dấu hiệu lạm dụng; không mặc định mọi mã sai đều là sự cố nghiêm trọng.

## 6. Tương quan request, workflow và trace

Một workflow có thể kéo dài nhiều phút hoặc nhiều giờ, qua nhiều lần người dùng quay lại. Không nên đồng nhất tất cả định danh thành một chuỗi.

| Định danh | Phạm vi minh họa |
| --- | --- |
| `interaction_ref` | Một lần gọi API hoặc tương tác được máy chủ nhận |
| `recovery_request_ref` | Hồ sơ workflow khôi phục |
| `event_id` | Một sự kiện logic để đối chiếu và xử lý bản sao |
| `trace_id` | Ngữ cảnh trace của một chuỗi xử lý kỹ thuật |
| `span_id` | Một phần xử lý trong trace |
| `command_ref` | Ý định xử lý bất đồng bộ hoặc thao tác được retry |

Một workflow có thể liên quan nhiều trace. Giữ tham chiếu workflow giúp nối các trace mà không cần mở một span dài chỉ để chờ người dùng nhập OTP.

Định danh tương quan là tham chiếu, không phải bằng chứng cấp quyền. Biết `recovery_request_ref` không được phép đọc hồ sơ hoặc hoàn tất khôi phục.

Header trace hoặc correlation do bên ngoài gửi cần được xử lý theo ranh giới tin cậy của hệ thống. Không coi chuỗi do người gọi cung cấp là bằng chứng rằng hai hành động thuộc cùng chủ thể hoặc cùng tenant.

Khi chuyển công việc qua hàng đợi, truyền ngữ cảnh cần thiết theo hợp đồng được kiểm soát. Worker phải gắn đúng ngữ cảnh cho lần xử lý và dọn ngữ cảnh khi kết thúc; tránh để principal hoặc request reference của công việc trước xuất hiện ở công việc sau.

Nếu trace không được lưu do sampling, log vẫn cần đủ thông tin cơ bản để diễn giải. Một trace ID trong log không bảo đảm luôn có trace đầy đủ để mở.

## 7. Loại bí mật trước khi serialize

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude) cảnh báo việc ghi trực tiếp mật khẩu, access token, định danh session và dữ liệu nhạy cảm. Với khôi phục tài khoản, áp dụng nguyên tắc chọn trường được phép ngay tại nơi tạo log.

Những dữ liệu không nên có trong log quan sát:

- Mật khẩu cũ hoặc mới.
- OTP, mã khôi phục dự phòng hoặc mã dùng một lần.
- Token khôi phục, cookie, authorization header và URL chứa token.
- Seed TOTP, QR cài đặt, private key của phương thức xác thực.
- Toàn bộ ảnh giấy tờ hoặc payload xác minh danh tính.
- Toàn bộ request, response hoặc đối tượng security context.

Không ghi token sai với lý do “nó không dùng được”. Máy chủ có thể chưa biết token thuộc ngữ cảnh khác hay vẫn còn giá trị ở đâu đó.

Không mặc định hash một OTP là đủ an toàn để lưu. Không gian giá trị nhỏ có thể bị dò. Tham chiếu challenge và kết quả kiểm tra thường đủ cho mục đích quan sát mà không cần giữ mã hoặc bản biến đổi của mã.

Redaction cần diễn ra cả ở nhánh thành công lẫn nhánh lỗi. Exception, URL của nhà cung cấp hoặc chuỗi mô tả lỗi có thể mang thông tin nhạy cảm; không đưa nguyên `exception.message` vào một trường “an toàn” chỉ vì trường đó có tên `error`.

Bật DEBUG không nên tắt các ràng buộc loại bí mật. Cấu hình tại collector có thể là lớp bảo vệ bổ sung, nhưng không thay thế việc tránh phát bí mật từ ứng dụng.

## 8. Chống log injection và giữ schema nhất quán

Một nhãn thiết bị, user agent hoặc trường do người gọi nhập có thể chứa dấu xuống dòng, dấu phân cách hoặc chuỗi giống một bản ghi JSON khác. Không nối chuỗi thủ công để tạo log.

Mã giả:

```text
safeEvent = RecoveryLogEvent(
  eventName = RECOVERY_EVIDENCE_VERIFICATION,
  outcome = decision.outcome,
  reasonCode = decision.safeReasonCode,
  recoveryRequestRef = serverContext.recoveryRequestRef,
  durationMs = elapsedTime
)

structuredLogger.emit(safeEvent)
```

`decision.safeReasonCode` là giá trị đã được ánh xạ từ tập mã nội bộ, không phải chuỗi exception tùy ý. `serverContext` phải là ngữ cảnh có thẩm quyền, không phải bản sao nguyên payload người gọi.

Dùng serializer hoặc encoder có xử lý escape đúng với định dạng đích. Chỉ sử dụng placeholder của logger không tự bảo đảm đầu ra là JSON hoặc mọi ký tự điều khiển đều được xử lý an toàn.

Giới hạn độ dài từng trường và kích thước tổng của sự kiện. Khi một thuộc tính bổ sung không hợp lệ, có thể loại thuộc tính đó, ghi dấu hiệu lỗi schema an toàn và giữ phần sự kiện cần thiết. Không để một user agent quá dài làm mất hoàn toàn sự kiện bảo mật.

Thay đổi schema cần có chiến lược tương thích. Thêm trường thường dễ hơn đổi nghĩa trường cũ hoặc đổi kiểu dữ liệu khi dashboard vẫn đang sử dụng nó. Nếu đổi `outcome` hoặc `reason_code`, phải xét tác động đến các bên đọc và cảnh báo.

## 9. Kết quả nghiệp vụ, severity và lỗi kỹ thuật

Severity cho biết mức ưu tiên vận hành; outcome cho biết thao tác đạt kết quả gì. Chúng không phải cùng một đại lượng.

Một chính sách minh họa:

| Tình huống | Outcome | Severity có thể dùng |
| --- | --- | --- |
| Một mã không hợp lệ trong điều kiện bình thường | DENIED | INFO |
| Một điều kiện chính sách chưa đạt | DENIED hoặc PENDING tùy nghiệp vụ | INFO |
| Dấu hiệu thử hàng loạt đáng chú ý | DENIED hoặc kết quả thực tế | WARN theo chính sách phát hiện |
| Nhà cung cấp xác minh timeout | ERROR cho lần gọi phụ thuộc | WARN hoặc ERROR theo ảnh hưởng |
| Thay đổi credential đã commit | COMMITTED | INFO |
| Không xác định được kết quả commit từ góc nhìn hiện tại | UNKNOWN | ERROR hoặc mức cần xử lý theo chính sách |

Timeout không phải bằng chứng người dùng cung cấp thông tin sai. Mã sai cũng không tự chứng minh hệ thống hỏng.

Trong luồng retry, phân biệt lỗi một lần gọi với kết quả cuối của thao tác. Ví dụ, lần gửi thông báo đầu timeout nhưng lần sau được nhà cung cấp chấp nhận. Không xóa dòng lỗi ban đầu, nhưng cũng không để truy vấn coi mọi timeout là một workflow khôi phục thất bại.

Thời lượng của bước xử lý nên đo bằng cơ chế thời gian trôi qua phù hợp. Dấu thời gian dùng cho sắp xếp và đối chiếu không thay thế phép đo duration đáng tin cậy; chênh lệch đồng hồ giữa hai máy có thể làm phép trừ timestamp sai.

Định nghĩa rõ duration có bao gồm thời gian chờ hàng đợi, thời gian gọi phụ thuộc hoặc thời gian người dùng suy nghĩ hay không.

## 10. Truy vấn hữu ích và giới hạn của phép đếm

Khi schema ổn định, truy vấn có thể tập trung vào câu hỏi nghiệp vụ. Ví dụ dưới đây chỉ là cách diễn đạt truy vấn, không phải cú pháp của một sản phẩm cụ thể:

```text
phạm vi dữ liệu: tenant và hồ sơ mà người truy vấn được phép đọc
lọc:
  service.name = dịch vụ account recovery
  event_name = recovery.evidence_verification
  timestamp nằm trong cửa sổ cần xem
nhóm:
  outcome, reason_code
tính:
  số sự kiện logic sau khi đối chiếu bản sao theo event_id
```

Một truy vấn khác có thể tìm các request đã commit thay credential nhưng chưa có kết quả xử lý thông báo, rồi đối chiếu với dữ liệu workflow có thẩm quyền. Vắng log chưa đủ để khẳng định tác vụ chưa chạy; có thể collector đang chậm hoặc sự kiện bị mất.

Đếm dòng log khác với đếm sự kiện logic. Bộ chuyển tiếp có thể gửi lại cùng sự kiện; thao tác có thể có nhiều lần thử; sampling có thể làm thiếu dữ liệu.

Nếu cần tỷ lệ thành công hoặc SLO chính xác, phải định nghĩa nguồn, mẫu số, cách xử lý retry và các giới hạn thu thập. Không dùng một tập log đã giảm mẫu rồi diễn giải như toàn bộ lưu lượng mà không nêu phương pháp.

Không biến account reference, email hoặc request reference thành tập nhãn metric không giới hạn. Những định danh đó có thể cần cho tra cứu log có kiểm soát, nhưng tạo chi phí và rủi ro khác khi dùng làm chiều tổng hợp diện rộng.

## 11. Bảo vệ và quan sát chính đường thu log

Structured logging vẫn có thể thất bại ở encoder, bộ đệm, mạng, collector hoặc kho tìm kiếm. Cần nhìn thấy trạng thái của đường thu thập, không chỉ trạng thái luồng recovery.

Một thiết kế vận hành có thể theo dõi:

- Số sự kiện bị từ chối vì schema hoặc vượt giới hạn kích thước.
- Độ trễ từ lúc xảy ra đến lúc được quan sát hoặc lập chỉ mục.
- Số lượng bị loại, bộ đệm đầy và lần gửi lại.
- Lỗi phân quyền hoặc mất kết nối tới nơi thu nhận.
- Sự thay đổi cấu hình logging và mức độ ghi.
- Sai lệch trường nguồn phát hoặc phiên bản schema.

Sampling, nếu dùng cho chẩn đoán, cần có chính sách tách khỏi bằng chứng bảo mật phải giữ. Không để lượng lớn log DEBUG làm mất các sự kiện quan trọng mà không có dấu hiệu cảnh báo.

Quyền đọc log cần giới hạn theo dữ liệu và mục đích, kể cả trên dashboard, alert và file xuất. Mã lý do nội bộ có thể giúp kẻ tấn công nếu bị lộ qua một endpoint công khai.

Khi log pipeline lỗi, không tự đổi kết quả nghiệp vụ đã commit hoặc làm token đã tiêu thụ dùng lại được. Nếu một bước nhạy cảm yêu cầu audit bền vững trước khi hoàn tất, điều kiện đó phải được thiết kế trong luồng audit tương ứng, không dựa vào việc một logger đã trả về.

Giới hạn tài nguyên logging cũng là một phần thiết kế: người gọi không nên có thể làm cạn đĩa hoặc bộ nhớ chỉ bằng cách gửi payload quá lớn hoặc tạo vô số lỗi lặp.

## 12. Tình huống minh họa

### Token đã hết hạn

Ứng dụng ghi kết quả từ chối với mã nguyên nhân nội bộ được phép, bước xử lý và tham chiếu request khi có. Không ghi token hoặc URL chứa nó. Phản hồi công khai vẫn tuân theo chính sách chống tiết lộ thông tin.

### Nhà cung cấp xác minh danh tính timeout

Log mô tả lỗi phụ thuộc, thời lượng, lần thử và ngữ cảnh tương quan. Nó không ghi người yêu cầu “xác minh thất bại” nếu hệ thống chỉ biết chưa nhận được kết quả.

### Thay mật khẩu đã commit nhưng mất phản hồi HTTP

Log sau điểm commit, dữ liệu workflow và định danh thao tác giúp đối chiếu kết quả. Không phát một sự kiện hoàn tất mới cho mỗi lần client gửi lại cùng ý định.

### Tác vụ gửi thông báo xử lý ở instance khác

Tham chiếu request và command nối các bước dù trace khác nhau. Worker dùng đúng ngữ cảnh của tác vụ hiện tại, ghi kết quả chuyển phát thực tế và không ghi token khôi phục trong payload lỗi.

Recovery structured logging giúp hệ thống giải thích diễn biến bằng dữ liệu có cấu trúc. Giá trị của nó đến từ ý nghĩa trường nhất quán, kết quả được ghi đúng thời điểm và giới hạn rõ ràng đối với dữ liệu nhạy cảm, tương quan và phép suy luận từ log.