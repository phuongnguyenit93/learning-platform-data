# Chọn tên sự kiện, chủ thể, dữ liệu và thời điểm có ý nghĩa nghiệp vụ

## 1. Bài toán thiết kế: ghi lại **điều đã xảy ra** một cách không nhập nhằng

Một hệ thống có thể lưu trạng thái hiện tại của đơn hàng, thiết bị thuê hoặc giao dịch; nhưng khi cần giải thích **vì sao** trạng thái thay đổi, **ai** thực hiện, **đối tượng nào** bị tác động và **sự việc xảy ra lúc nào**, chỉ một cột `status` thường không đủ.

Giả sử bộ phận vận hành của dịch vụ thuê thiết bị đưa ra yêu cầu:

> “Khi khách trả thiết bị, chúng tôi muốn biết khách đã gửi yêu cầu trả hay đã thực sự bàn giao, ai nghiệm thu, có hư hỏng không, có trễ hạn không và khi nào tiền cọc được hoàn.”

Nếu thiết kế một sự kiện chung tên `RentalUpdated` với payload tùy ý, dữ liệu lưu được về mặt kỹ thuật nhưng rất khó hiểu và kiểm chứng sau này. Một mô hình sự kiện có chất lượng cần trả lời bốn nhóm câu hỏi:

1. **Tên:** chính xác sự việc nghiệp vụ nào đã hoàn tất?
2. **Chủ thể và tác nhân:** sự việc thuộc đối tượng nào, và ai/hệ thống nào gây ra hoặc xác nhận nó?
3. **Dữ liệu:** phải giữ những sự thật, định danh và ngữ cảnh nào để diễn giải sự kiện sau nhiều năm?
4. **Thời điểm:** sự việc xảy ra, có hiệu lực và được ghi nhận tại những thời điểm nào?

Bốn quyết định này nối trực tiếp yêu cầu nghiệp vụ với **thực thể, quan hệ, ràng buộc, khóa và lược đồ vật lý** của hệ thống dữ liệu. Chúng áp dụng khi xây dựng nhật ký nghiệp vụ, domain event, integration event hoặc event-sourced model; không bắt buộc hệ thống phải áp dụng event sourcing toàn phần.

## 2. Xác định ranh giới của một sự kiện có ý nghĩa nghiệp vụ

Sự kiện nghiệp vụ là một **sự thật đã được hệ thống chấp nhận** theo quy tắc rõ ràng. Cần phân biệt:

| Loại thông tin | Ví dụ | Cách hiểu |
| --- | --- | --- |
| **Ý định/command** | `RequestEquipmentReturn` | Có yêu cầu tiếp nhận việc trả thiết bị; yêu cầu có thể bị từ chối. |
| **Sự kiện** | `ReturnRequested` | Hệ thống đã ghi nhận yêu cầu trả hợp lệ; chưa có nghĩa thiết bị đã về kho. |
| **Sự kiện** | `EquipmentDroppedOff` | Thiết bị đã được bàn giao tại điểm nhận theo quy trình xác nhận. |
| **Sự kiện** | `EquipmentReturnAccepted` | Nhân viên đã nghiệm thu và chấp nhận việc trả thiết bị. |
| **Trạng thái** | `rental_status = RETURNED` | Hình chiếu về tình trạng hiện tại; bản thân nó không cho biết đầy đủ chuỗi diễn tiến. |

Không phải mọi thao tác kỹ thuật đều là domain event. Ví dụ, **người dùng mở trang**, **API được gọi**, **hàng trong bảng được UPDATE** có thể là telemetry hoặc audit kỹ thuật; chúng không nhất thiết nói lên một sự thật mà người làm nghiệp vụ quan tâm. Ngược lại, việc **tiền cọc đã được đơn vị thanh toán xác nhận hoàn thành** có giá trị độc lập với cách dịch vụ triển khai và thường đáng đặt tên thành sự kiện.

### Chuyển câu mô tả thành danh mục sự kiện

Một kỹ thuật hiệu quả là làm việc cùng người hiểu nghiệp vụ và điền bảng sau:

| Câu nghiệp vụ | Sự kiện ứng viên | Khi nào được công nhận? | Ai cần thông tin này? |
| --- | --- | --- | --- |
| “Khách đề nghị trả sớm.” | `ReturnRequested` | Yêu cầu hợp lệ được ghi nhận. | Chăm sóc khách hàng, điều phối nhận hàng. |
| “Kiosk đã nhận thiết bị.” | `EquipmentDroppedOff` | Có bằng chứng quét/tiếp nhận tại kiosk. | Kho, bộ phận tính phí trễ. |
| “Nhân viên xác nhận thiết bị đạt yêu cầu.” | `EquipmentReturnAccepted` | Biên bản kiểm tra được chấp nhận. | Kho, kế toán tiền cọc. |
| “Phát hiện thiết bị bị hỏng.” | `EquipmentDamageAssessed` | Kết quả đánh giá thiệt hại đã được phê duyệt. | Kế toán, xử lý khiếu nại. |
| “Đơn vị thanh toán xác nhận hoàn cọc.” | `DepositRefundConfirmed` | Nhận được thông tin xác nhận hoàn tiền đáng tin cậy. | Khách hàng, kế toán, đối soát. |

Mỗi sự kiện cần có **điểm chốt sự thật**. Nếu chưa thống nhất “đã nhận”, “đã xác nhận”, “đã hoàn tiền” nghĩa là gì và ai có quyền xác nhận, tên event sẽ gây tranh luận, còn dữ liệu sẽ có nhiều cách diễn giải.

### Chọn độ hạt phù hợp

Không nên gộp các mốc độc lập vào một `ReturnProcessed` nếu chúng diễn ra ở các thời điểm khác nhau, do các bên khác nhau thực hiện hoặc có thể thành công/thất bại riêng. Cũng không cần phát event cho mỗi lần một ô nhập liệu mất focus. Hãy tách sự kiện khi ít nhất một điều kiện sau đúng:

- Có **quy tắc nghiệp vụ** riêng cho việc chấp nhận hoặc từ chối.
- Có **thời điểm, người xác nhận** hoặc **bằng chứng** riêng.
- Có bên tiêu thụ cần biết mốc đó mà không cần suy đoán từ thay đổi kỹ thuật.
- Sự việc tạo ra nghĩa vụ, quyền lợi, chi phí hoặc trạng thái pháp lý/vận hành cần truy vết.

Ví dụ: thiết bị được bỏ vào kiosk lúc 10:05 nhưng nhân viên nghiệm thu lúc 10:13. Nếu phí trễ tính theo **thời gian bàn giao tại kiosk**, hai sự kiện riêng là cách mô hình hóa rõ nghĩa hơn một event `Returned` không xác định thời điểm.

## 3. Chọn **tên sự kiện** theo ngôn ngữ của nghiệp vụ

Tên tốt mô tả một sự thật đã xảy ra, thường dùng cấu trúc **Đối tượng + Hành động ở dạng đã hoàn tất**. Tiếng Anh thường dùng `OrderPlaced`, `InvoiceIssued`, `PaymentCaptured`, `ShipmentDispatched`; với từ bất quy tắc hoặc thuật ngữ miền, ưu tiên nghĩa rõ hơn một quy tắc ngữ pháp máy móc.

| Tên dễ gây vấn đề | Tên diễn đạt rõ hơn | Lý do |
| --- | --- | --- |
| `UpdateRental` | `RentalDueDateChanged` | Nêu rõ sự thay đổi nào đã xảy ra. |
| `Returned` | `EquipmentDroppedOff` hoặc `EquipmentReturnAccepted` | Phân biệt bàn giao vật lý với nghiệm thu. |
| `PayDeposit` | `DepositPaymentCaptured` | `PayDeposit` nghe như yêu cầu; “captured” là kết quả đã xác nhận. |
| `RefundDone` | `DepositRefundConfirmed` | Chỉ rõ nghiệp vụ và điểm xác nhận. |
| `RentalStatusChanged` | `RentalClosed` | Chỉ rõ chuyển biến thực sự có ý nghĩa đối với bên tiêu thụ. |
| `ErrorHappened` | `DepositRefundFailed` | Phân biệt thất bại có ý nghĩa với lỗi hệ thống chung. |

Một số quy tắc thực hành:

1. **Dùng ngôn ngữ chung của người làm nghiệp vụ.** Nếu “nghiệm thu” khác “nhận tại quầy”, hai tên event phải khác nhau.
2. **Đặt tên theo sự thật, không theo thao tác lưu trữ.** Tránh `InsertRow`, `ChangeField`, `SyncCompleted` nếu điều cần diễn tả là thay đổi nghiệp vụ.
3. **Không đặt tên hàm ý thành công trước khi có xác nhận.** `RefundRequested`, `RefundInitiated` và `RefundConfirmed` là những mốc khác nhau.
4. **Đảm bảo tính nhất quán.** Chọn một cách gọi `Cancelled`/`Canceled`, `Confirmed`/`Approved` theo từ điển miền để tránh event type trùng nghĩa.
5. **Giữ nghĩa ổn định theo thời gian.** Nếu tiêu chí nghiệm thu thay đổi, có thể dùng `event_version` cho thay đổi cấu trúc; nếu định nghĩa nghiệp vụ khác hẳn, cân nhắc event type mới.

**Thử nghiệm nhanh:** chỉ đọc tên event, người phụ trách nghiệp vụ có hiểu điều gì được xác nhận không? Nếu phải xem mã nguồn mới biết `OrderUpdated` thực sự có nghĩa gì, tên chưa đạt yêu cầu.

## 4. Xác định **chủ thể**, **aggregate** và **tác nhân**

Một sự kiện thường liên quan nhiều đối tượng. Không nên đưa tất cả vào một trường `user_id` vì sẽ mất ngữ nghĩa.

| Vai trò | Câu hỏi | Ví dụ với `EquipmentReturnAccepted` |
| --- | --- | --- |
| **Aggregate/stream owner** | Sự kiện thuộc chuỗi thay đổi có thứ tự của đối tượng nghiệp vụ nào? | Hợp đồng thuê `RENT-204`. |
| **Chủ thể (subject)** | Thực thể nào là đối tượng trực tiếp của sự việc? | Thiết bị `EQ-042` được nghiệm thu. |
| **Tác nhân (actor)** | Ai hoặc hệ thống nào thực hiện/ra quyết định? | Nhân viên kho `EMP-18`. |
| **Bên liên quan (party)** | Quyền lợi/nghĩa vụ của ai bị tác động? | Khách hàng của hợp đồng thuê. |
| **Nguồn xác nhận (source/authority)** | Ai cung cấp bằng chứng cho kết quả? | Dịch vụ kho cùng mã biên bản nghiệm thu. |

**Aggregate** là ranh giới để kiểm tra quy tắc và xác định thứ tự cục bộ. Trong một mô hình, hợp đồng `Rental` có thể chứa nhiều thiết bị; trong mô hình khác, từng `RentedItem` là một aggregate riêng. Việc chọn ranh giới phụ thuộc vào bất biến: có cần nghiệm thu toàn bộ hợp đồng như một giao dịch hay mỗi thiết bị có vòng đời độc lập? Không mặc định chủ thể của sự kiện luôn chính là aggregate.

**Actor** cũng không nhất thiết là người hưởng lợi, người tạo bản ghi hay người sở hữu aggregate:

- Khách tạo yêu cầu trả; nhân viên nghiệm thu; dịch vụ gửi event. Đây có thể là **ba tác nhân hoặc nguồn thông tin khác nhau** ở các bước khác nhau.
- Hệ thống tự động đóng hợp đồng: `actor_type = SYSTEM`, `actor_id = rental-scheduler`; không gán nhầm cho khách hàng.
- Tác vụ được nhân viên thực hiện thay mặt khách: có thể cần **acting_on_behalf_of** hoặc **requested_by** tùy yêu cầu truy vết và quyền hạn.
- Bên thanh toán xác nhận hoàn tiền: ghi định danh nguồn/correlation của nhà cung cấp; actor là hệ thống thanh toán hoặc quy trình phù hợp với sự kiện, không tự coi khách đã xác nhận.

Danh tính trong event nên là **định danh ổn định có phạm vi rõ** như `employee_id`, `customer_id`, `service_name` hoặc `provider_reference`. Tên hiển thị, email và số điện thoại có thể thay đổi và chứa dữ liệu cá nhân; chỉ sao chép vào sự kiện khi có lý do nghiệp vụ và chính sách bảo vệ thích hợp.

Trong hệ thống đa khách thuê (multi-tenant), các ID như `EQ-042` có thể chỉ duy nhất **trong từng tenant**. Vì vậy cần có `tenant_id` và xác định khóa, chỉ mục, quyền truy cập theo phạm vi tenant, thay vì mặc định mọi ID đều duy nhất toàn cục.

## 5. Chọn **dữ liệu sự kiện**: tối thiểu nhưng đủ nghĩa

Event được dùng sau khi người viết mã hoặc bảng hiện tại đã thay đổi. Một payload tốt giữ đủ dữ liệu để hiểu **sự thật tại lúc xảy ra**, kiểm chứng quy tắc liên quan, khôi phục trạng thái cần thiết và phục vụ câu hỏi lịch sử đã thống nhất.

Có thể phân thành bốn nhóm:

| Nhóm | Nội dung | Ví dụ |
| --- | --- | --- |
| **Định danh và liên kết** | Event ID, aggregate ID, subject ID, event type, event version, causation/correlation. | `event_id`, `rental_id`, `equipment_id`. |
| **Sự thật nghiệp vụ** | Kết quả, số lượng, số tiền, kết quả kiểm tra, thay đổi đã được chấp nhận. | `inspection_result = PASSED`, `damage_code = NONE`. |
| **Ngữ cảnh để diễn giải** | Chính sách/phiên bản biểu phí, nơi tiếp nhận, nguyên nhân có mã hóa, đơn vị đo. | `branch_id`, `policy_version`, `reason_code`. |
| **Nguồn gốc và thời gian** | Actor, source, thời điểm, request/correlation, định danh bằng chứng. | `actor_id`, `occurred_at`, `receipt_id`. |

Các nguyên tắc chọn trường:

- **Ghi dữ liệu mang nghĩa rõ ràng.** `refund_amount_minor = 500000`, `currency = VND` tốt hơn `amount = 500000` thiếu đơn vị. Với tiền, số nguyên theo đơn vị nhỏ nhất đã được xác định cho loại tiền thường dễ kiểm soát hơn số thực.
- **Giữ giá trị tại thời điểm phát sinh nếu về sau không thể suy ra chắc chắn.** Chẳng hạn biểu phí áp dụng tại lúc tính phí hoặc mức cọc đã duyệt; đọc biểu phí **hiện tại** có thể tạo kết quả sai cho lịch sử.
- **Tách tham chiếu và bản chụp có chủ đích.** `product_id` để liên kết là hữu ích, nhưng nếu chính tên hoặc phân loại tại thời điểm giao dịch quyết định nghĩa vụ thì cần snapshot hoặc tham chiếu đến phiên bản dữ liệu bất biến.
- **Có schema theo event type và version.** Trường bắt buộc, enum, đơn vị đo và quan hệ giữa các trường phải được công bố; `payload: {}` không đủ dù là JSON hợp lệ.
- **Không nhồi nguyên bản request, đối tượng cơ sở dữ liệu hoặc dữ liệu nhạy cảm vô cớ.** Payload toàn bộ hồ sơ khách có thể làm tăng rủi ro riêng tư và làm event khó tiến hóa.
- **Đừng lưu kết quả tính toán có thể suy ra từ dữ kiện bất biến chỉ để “cho đủ”.** Nhưng nếu kết quả đã là **quyết định nghiệp vụ được phê duyệt** (ví dụ phí hư hỏng cuối cùng), nó có thể chính là sự thật cần lưu.

### Khi nào cần giá trị trước và sau?

Với `RentalDueDateChanged`, payload như sau thường dễ kiểm toán:

~~~json
{
  "old_due_at": "2026-11-20T10:00:00+07:00",
  "new_due_at": "2026-11-22T10:00:00+07:00",
  "reason_code": "CUSTOMER_EXTENSION_APPROVED",
  "approval_id": "APR-891"
}
~~~

Trong event sourcing thuần, `old_due_at` có thể suy ra từ trạng thái trước đó. Tuy nhiên, ghi thêm giá trị cũ nếu có yêu cầu đối chiếu rõ ràng là lựa chọn hợp lý, miễn là **lúc ghi phải kiểm chứng `old_due_at` trùng trạng thái đã chấp nhận** để tránh lưu hai sự thật mâu thuẫn. `new_due_at` là thay đổi được phê duyệt, không thể chỉ dựa vào tên event.

### Sự kiện không phải nơi thay cho toàn bộ mô hình quan hệ

Các quan hệ nghiệp vụ vẫn phải rõ: một `Rental` thuộc khách nào, một `RentalItem` tham chiếu thiết bị nào, một `Refund` gắn với khoản cọc nào. Event cần giữ định danh để nối các thực thể đó; read model có thể chuẩn hóa các bảng quan hệ, tối ưu tài liệu theo aggregate, hoặc xây bảng phân tích theo thời gian. Lựa chọn này dựa vào truy vấn và nhu cầu nhất quán của từng ngữ cảnh.

## 6. Thiết kế **thời điểm** theo câu hỏi nghiệp vụ

Một trường `timestamp` duy nhất rất dễ che giấu nhiều khái niệm. Cần thống nhất từng mốc:

| Thời điểm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **occurred_at** | Khi sự việc mà event mô tả thực sự xảy ra theo nguồn được công nhận. | Nhân viên chấp nhận nghiệm thu lúc 10:13. |
| **recorded_at** | Khi event được hệ thống lưu vào kho sự kiện. | Database ghi sự kiện lúc 10:13:02. |
| **effective_at** (nếu có) | Khi kết quả nghiệp vụ bắt đầu áp dụng. | Gia hạn được duyệt hôm nay nhưng lịch mới có hiệu lực ngày mai. |
| **source_observed_at** (nếu cần) | Khi thiết bị/đối tác quan sát sự việc, trước khi gửi vào hệ thống. | Kiosk quét và xác nhận nhận đồ lúc 10:05. |
| **processed_at** (trên read model/bộ tiêu thụ) | Khi một tác vụ xử lý event. | Báo cáo cập nhật lúc 10:15. |

Không bắt buộc mọi event phải có tất cả trường trên. Thêm thời gian khi sự phân biệt đó làm thay đổi quyết định nghiệp vụ, kiểm toán hoặc kết quả báo cáo.

### Ví dụ: trả thiết bị và nghiệm thu

Ngày 20/11/2026 theo giờ Việt Nam (`Asia/Ho_Chi_Minh`):

1. **10:05:00:** kiosk xác nhận bàn giao thiết bị → `EquipmentDroppedOff` với `occurred_at = 10:05:00`.
2. **10:13:00:** nhân viên kiểm tra và phê duyệt nhận trả → `EquipmentReturnAccepted` với `occurred_at = 10:13:00`.
3. **10:13:02:** hệ thống lưu event nghiệm thu → `recorded_at = 10:13:02`.

Nếu phí trả muộn tính theo **thời gian bàn giao tại kiosk**, phải dùng thời gian có bằng chứng của `EquipmentDroppedOff`. Nếu chất lượng kho tính tốc độ nghiệm thu, dùng chênh lệch từ lúc nhận vật lý đến lúc chấp nhận. Dùng thời gian ghi vào database cho cả hai chỉ số sẽ làm kết quả sai khi có độ trễ xử lý.

### Thời điểm có hiệu lực không đồng nghĩa đã hoàn tất

Ngày 20/11, khách đăng ký đổi gói có hiệu lực ngày 01/12. Tại thời điểm chấp thuận lịch, event phù hợp có thể là `PlanChangeScheduled` với `effective_at = 2026-12-01...`. Chưa được ghi `PlanActivated` nếu việc kích hoạt thực tế vẫn chưa xảy ra. Khi điều kiện kích hoạt được thỏa mãn, hệ thống ghi một event xác nhận kích hoạt riêng hoặc đưa ra mô hình trạng thái dự kiến đã được quy định rõ.

Một hiệu lực **hồi tố** cũng cần được mô hình hóa có chủ đích. Ví dụ chính sách cho phép điều chỉnh thời điểm bắt đầu thuê: `RentalStartCorrected` có thời điểm chấp thuận hôm nay nhưng `effective_at` ở quá khứ. Không sửa âm thầm `occurred_at` của event cũ để làm lịch sử có vẻ như chưa từng có sai lệch.

### Chuẩn hóa thời gian và thứ tự

- Dùng kiểu thời gian có múi giờ (`TIMESTAMPTZ` trong PostgreSQL) hoặc lưu giá trị UTC cùng quy ước diễn giải rõ ràng; khi hiển thị và chia ngày kinh doanh, chuyển về múi giờ nghiệp vụ thích hợp.
- Không so sánh chuỗi ngày giờ định dạng tự do. Nếu chỉ có **ngày nghiệp vụ** (không có giờ), dùng kiểu `DATE` và quy tắc riêng, thay vì bịa một mốc `00:00:00` như thể có bằng chứng về giờ.
- Đồng hồ của thiết bị ngoại vi và đối tác có thể sai, sự kiện có thể đến muộn. Lưu nguồn thời gian và độ tin cậy khi cần; không suy ra thứ tự tuyệt đối bằng cách sắp xếp `occurred_at` của nhiều hệ thống.
- Với chuỗi sự kiện của một aggregate, dùng **sequence_no** hoặc cơ chế thứ tự được bảo đảm để áp dụng thay đổi. `occurred_at` phục vụ nghĩa nghiệp vụ và phân tích thời gian, không thay thế thứ tự ghi nhận.
- Với phân tích theo “thời gian sự việc” (event time), cần chính sách xử lý dữ liệu đến muộn; với vận hành bộ tiêu thụ, dùng thời gian ghi nhận/xử lý để đo độ trễ.

Sự phân biệt giữa **thời gian có hiệu lực trong thế giới nghiệp vụ** và **thời gian hệ thống biết/ghi nhận** cũng là nền tảng của thiết kế **bitemporal** khi cần trả lời đồng thời “lúc đó thực tế có hiệu lực thế nào?” và “tại thời điểm báo cáo trước đây, hệ thống đã biết gì?”.

## 7. Ví dụ hợp đồng sự kiện hoàn chỉnh

Giả sử một hợp đồng `RENT-204` thuê thiết bị `EQ-042`. Sau khi kiosk ghi nhận bàn giao, nhân viên `EMP-18` kiểm tra và chấp nhận thiết bị trong tình trạng tốt. Event nghiệp vụ là **EquipmentReturnAccepted**; điều kiện phát event là nghiệm thu đã được chấp thuận.

~~~json
{
  "event_id": "13773c4c-66d7-44a7-9d25-c37a53e2a8ce",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "sequence_no": 7,
  "event_type": "EquipmentReturnAccepted",
  "event_version": 1,
  "subject_type": "Equipment",
  "subject_id": "EQ-042",
  "actor_type": "STAFF",
  "actor_id": "EMP-18",
  "source_system": "warehouse-service",
  "occurred_at": "2026-11-20T03:13:00Z",
  "recorded_at": "2026-11-20T03:13:02Z",
  "idempotency_key": "inspection-REC-992",
  "correlation_id": "b0d7e384-d4eb-40ab-9733-e43999f4280b",
  "causation_id": "e3b535d0-823c-4ae3-b79f-64d8fcbec7e4",
  "payload": {
    "equipment_id": "EQ-042",
    "inspection_receipt_id": "REC-992",
    "inspection_result": "PASSED",
    "condition_code": "GOOD",
    "branch_id": "HCM-03",
    "dropoff_event_id": "6f5f5915-d94e-4cf9-aa81-1d5c1c8f3b44"
  }
}
~~~

**Cách đọc hợp đồng này:**

- `event_id` là định danh của **lần xảy ra sự kiện**; `aggregate_id + sequence_no` thể hiện vị trí của sự kiện trong lịch sử `Rental`. Số 7 trong ví dụ là thứ tự **trong RENT-204**, không phải số thứ tự toàn hệ thống.
- `subject_id = EQ-042` nói rõ thiết bị được nghiệm thu, trong khi `actor_id = EMP-18` là nhân viên xác nhận.
- `occurred_at` và `recorded_at` được ghi ở UTC: 03:13Z tương ứng 10:13 giờ Việt Nam.
- `dropoff_event_id` kết nối với việc kiosk đã nhận trước đó; không tự suy ra thời gian bàn giao từ thời gian nghiệm thu.
- `inspection_result` và `condition_code` là giá trị theo **từ điển mã nghiệp vụ** được quản lý, tránh chuỗi mô tả tùy ý.
- `correlation_id` liên kết các bước thuộc một tiến trình; `causation_id` trong ví dụ là ID của command hoặc thông điệp gây ra event, có kiểu và cách quản lý được định nghĩa rõ.
- `idempotency_key` dùng để phát hiện yêu cầu nghiệm thu bị gửi lại. Phạm vi duy nhất của khóa phải được quy định, ví dụ theo `source_system`; nó không thay thế `event_id`.

Hợp đồng event không nhất thiết sao chép toàn bộ trạng thái hợp đồng, lịch sử tính phí hoặc hồ sơ khách hàng. Nếu một projection cần dữ liệu không có trong event, phải xác định lấy từ **các event trước trong cùng luồng**, từ **dữ liệu tham chiếu có phiên bản** hay bổ sung vào payload để replay không phụ thuộc trạng thái bên ngoài đã thay đổi.

## 8. Từ hợp đồng sự kiện đến bảng, khóa và chỉ mục

Trong mô hình quan hệ, có thể tách metadata ổn định thành các cột có kiểu dữ liệu rõ và giữ phần payload khác nhau theo event trong `JSONB`. Ví dụ PostgreSQL dưới đây giới hạn ở **stream của hợp đồng Rental**:

~~~sql
CREATE TABLE rental_stream (
    rental_id       VARCHAR(64) PRIMARY KEY,
    last_sequence   BIGINT NOT NULL DEFAULT 0
                    CHECK (last_sequence >= 0)
);

CREATE TABLE rental_event (
    event_id         UUID PRIMARY KEY,
    rental_id        VARCHAR(64) NOT NULL
                     REFERENCES rental_stream (rental_id),
    sequence_no      BIGINT NOT NULL CHECK (sequence_no > 0),
    event_type       VARCHAR(100) NOT NULL,
    event_version    SMALLINT NOT NULL CHECK (event_version > 0),
    subject_type     VARCHAR(50) NOT NULL,
    subject_id       VARCHAR(80) NOT NULL,
    actor_type       VARCHAR(40) NOT NULL,
    actor_id         VARCHAR(100),
    source_system    VARCHAR(80) NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at     TIMESTAMPTZ,
    idempotency_key  VARCHAR(160),
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (rental_id, sequence_no)
);

CREATE UNIQUE INDEX ux_rental_event_idempotency
    ON rental_event (source_system, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_rental_event_type_time
    ON rental_event (event_type, occurred_at);
~~~

Giải thích các lựa chọn:

- **Khóa chính `event_id`** phân biệt mọi sự kiện; **UNIQUE(`rental_id`, `sequence_no`)** bảo đảm một vị trí duy nhất trong từng stream. Khi sinh số thứ tự, ứng dụng phải khóa hoặc kiểm tra phiên bản của aggregate trong giao dịch, không chỉ dựa vào việc tự tính `MAX(sequence_no) + 1` ngoài transaction.
- **Khóa chống lặp `(source_system, idempotency_key)`** phù hợp nếu mỗi nguồn cam kết không tái sử dụng khóa cho nghiệp vụ khác. Nếu phạm vi chống lặp thực tế là từng hợp đồng, thiết kế khóa nên bao gồm `rental_id`; chọn theo hợp đồng với nguồn phát.
- **`subject_type + subject_id`** mô tả đối tượng trực tiếp; ràng buộc tham chiếu kiểu đa hình không tự phát sinh chỉ từ hai cột. Nếu cần khóa ngoại nghiêm ngặt, dùng bảng hoặc quan hệ chuyên biệt cho từng loại subject.
- **`actor_type + actor_id`** biểu diễn người hoặc dịch vụ thực thi. Giá trị `actor_id` có thể rỗng trong trường hợp được quy định rõ (ví dụ tác vụ hệ thống chưa định danh cá thể), nhưng không nên dùng `NULL` cho mọi trường hợp không biết ai.
- **`payload JSONB`** cho phép schema riêng theo `event_type`, nhưng `CHECK(jsonb_typeof(payload) = 'object')` chỉ kiểm tra dạng JSON. Các trường bắt buộc, enum, quan hệ và quy tắc version phải được xác minh ở tầng viết event hoặc bằng cơ chế ràng buộc bổ sung.
- **Chỉ mục theo loại và thời gian** hỗ trợ một số báo cáo, nhưng có chi phí ghi. Kiểm tra tần suất truy vấn và kế hoạch thực thi trước khi thêm nhiều chỉ mục. Với dữ liệu lớn có thể cân nhắc phân vùng và chiến lược lưu trữ theo yêu cầu truy vấn/retention.

Một truy vấn báo cáo dựa trên **thời điểm nghiệp vụ** thay vì ngày ghi database:

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS business_day,
    COUNT(*) AS returns_accepted
FROM rental_event
WHERE event_type = 'EquipmentReturnAccepted'
GROUP BY 1
ORDER BY 1;
~~~

Truy vấn chỉ đếm **lượt nghiệm thu được chấp nhận**. Nó không đếm số yêu cầu trả, số lượt kiosk nhận đồ hay số hợp đồng đã hoàn cọc; mỗi chỉ số phải được gắn đúng event và quy tắc loại trừ lặp/điều chỉnh của chính nó.

## 9. Ghi nhận sự kiện đúng khi có đồng thời, gửi lặp và nhiều dịch vụ

Một tên và payload đúng vẫn có thể tạo dữ liệu sai nếu cơ chế ghi nhận không bảo vệ ý nghĩa nghiệp vụ. Quy trình xử lý một command thường gồm:

~~~mermaid
flowchart TD
    C["Command: AcceptEquipmentReturn"] --> I{"Yêu cầu đã xử lý?"}
    I -->|Có| O["Trả kết quả của lần trước"]
    I -->|Chưa| L["Khóa/kiểm tra phiên bản Rental"]
    L --> V{"Bất biến nghiệp vụ hợp lệ?"}
    V -->|Không| R["Từ chối, không phát sự kiện thành công"]
    V -->|Có| E["Ghi EquipmentReturnAccepted với sequence tiếp theo"]
    E --> T["Commit cùng dữ liệu cần nhất quán"]
    T --> P["Cập nhật projection / phát qua outbox"]
~~~

Chẳng hạn nếu thiết bị `EQ-042` đã nghiệm thu, một lần gọi API lặp lại không được tạo thêm `EquipmentReturnAccepted` khiến báo cáo đếm hai lần. Ràng buộc duy nhất trên khóa yêu cầu, kiểm tra trạng thái cùng aggregate và consumer xử lý idempotent cùng góp phần ngăn lỗi.

Khi event được chuyển đến các hệ thống khác:

- **Domain event** diễn tả sự thật trong ranh giới nghiệp vụ nội bộ; **integration event** là hợp đồng công bố ra ngoài, có thể được lọc hoặc chuyển đổi để giảm ràng buộc.
- Dịch vụ lưu dữ liệu và công bố thông điệp qua broker có thể gặp lỗi ở giữa hai thao tác. **Transactional outbox** giúp lưu nội dung cần phát trong cùng giao dịch với thay đổi nguồn; tiến trình phát và bên nhận vẫn phải xử lý việc gửi lặp.
- **Correlation** nối toàn bộ một quy trình, **causation** chỉ nguyên nhân trực tiếp; hai khái niệm không thay cho `aggregate_id` hay `event_id`.
- Nếu một thay đổi trải qua thanh toán, kho và hợp đồng, cần xác định sự thật được xác nhận ở từng dịch vụ cùng cơ chế bù trừ hoặc phối hợp; không coi một event cục bộ là bằng chứng mọi hệ thống đã hoàn tất.

## 10. Kiểm chứng chất lượng hợp đồng và quản lý thay đổi

Trước khi chính thức sử dụng event, nên có **event contract** cho từng `event_type` gồm: định nghĩa bằng một câu; điều kiện phát; aggregate, subject, actor, authority; schema payload/version; quy tắc thời gian; idempotency; ràng buộc và các consumer cần nó.

Ví dụ hợp đồng rút gọn:

| Thành phần | `EquipmentReturnAccepted` |
| --- | --- |
| Định nghĩa | Việc nghiệm thu nhận lại một thiết bị của hợp đồng thuê đã được chấp nhận. |
| Điều kiện phát | Bản ghi kiểm tra hợp lệ, người có quyền phê duyệt, thiết bị chưa được nghiệm thu trước đó. |
| Aggregate | `Rental`; có thứ tự `sequence_no` trong từng `rental_id`. |
| Subject | Thiết bị được nghiệm thu, được xác định bằng `equipment_id`. |
| Actor/authority | Người phê duyệt và dịch vụ kho xác nhận kết quả. |
| Payload tối thiểu | `inspection_receipt_id`, `equipment_id`, `inspection_result`, `branch_id`, mã tình trạng phù hợp. |
| Thời điểm | `occurred_at` khi nghiệm thu được chấp thuận; `recorded_at` khi lưu. |
| Chống lặp | Một biên bản nghiệm thu hợp lệ chỉ được chấp nhận một lần trong phạm vi quy định. |

### Tiến hóa schema mà không đánh mất nghĩa lịch sử

Giả sử phiên bản 2 của event bổ sung `damage_assessment_version`. Người đọc cần hiểu cả event v1 và v2 thông qua phiên bản và quy tắc chuyển đổi rõ ràng. Không lặng lẽ thay đổi cách tính hoặc tên mã của một field cũ khi event lịch sử vẫn còn. Có thể dùng **upcaster** khi replay, hoặc triển khai nhiều reader tương thích tùy kiến trúc.

Nếu event đã ghi sai, cân nhắc một event **điều chỉnh có dấu vết** (`EquipmentReturnAcceptanceCorrected`, `DamageAssessmentRevised`) theo quyền hạn và quy tắc nghiệp vụ, thay vì chỉnh payload cũ mà không lưu lịch sử. Nếu phải xóa hoặc ẩn dữ liệu cá nhân theo chính sách, thiết kế lưu trữ và quyền truy cập phải đáp ứng yêu cầu đó ngay từ đầu; nguyên tắc append-only không có nghĩa lưu vô thời hạn mọi dữ liệu.

### Bảng kiểm rà soát

| Câu hỏi kiểm chứng | Dấu hiệu đạt |
| --- | --- |
| Đọc tên event có biết sự việc nào đã hoàn tất? | Phân biệt được “đã yêu cầu”, “đã nhận”, “đã duyệt”, “đã hoàn tiền”. |
| Biết ai quyết định và ai bị tác động? | Actor, subject, aggregate và bên liên quan có vai trò tách biệt khi cần. |
| Replay có cần gọi dữ liệu hiện tại dễ thay đổi không? | Dữ liệu bắt buộc hoặc tham chiếu phiên bản bất biến được xác định. |
| Thời gian có đúng nghĩa khi báo cáo trả muộn? | Biết nguồn và quy tắc chọn `occurred_at`/`effective_at`/`recorded_at`. |
| Có thể phân biệt hai event thật và một lần gửi lặp? | Có event ID, khóa idempotency có phạm vi, quy tắc xử lý lặp. |
| Ghi đồng thời có tạo lịch sử sai không? | Có ranh giới aggregate, phiên bản/khóa và bất biến được kiểm tra trong giao dịch. |
| Reader sau này đọc được event cũ? | Có hợp đồng version và chiến lược tương thích. |
| Có quyền kiểm soát dữ liệu nhạy cảm? | Payload tối thiểu, định danh ổn định, chính sách truy cập và retention rõ ràng. |

## 11. Bài tập áp dụng: thiết kế sự kiện cho đơn giao hàng

**Yêu cầu:** cửa hàng cần biết lúc nhân viên chuẩn bị xong hàng, thời điểm đơn vị vận chuyển thực sự nhận, người xác nhận bàn giao, khi nào khách nhận thành công và lý do giao không thành công. Một đơn có thể giao lại nhiều lần.

**Nhiệm vụ:**

1. Đề xuất ít nhất bốn tên event và định nghĩa **điểm xác nhận** của từng event. Phân biệt yêu cầu giao lại với lần giao lại thực tế.
2. Với event bàn giao cho đơn vị vận chuyển, xác định **aggregate**, **subject**, **actor**, **nguồn xác nhận**, các định danh liên quan và payload tối thiểu.
3. Nếu tài xế giao hàng lúc 14:30 nhưng thiết bị offline đến 16:00 mới đồng bộ, xác định giá trị và nguồn của `occurred_at`, `recorded_at`, cùng cách xử lý khi đồng hồ thiết bị không đáng tin.
4. Thiết kế cách đếm **số lần giao thực tế** để không tăng khi thiết bị gửi lại cùng thông điệp; xác định khóa chống lặp và quy tắc phân biệt hai lần giao khác nhau.
5. Nêu một bất biến và một truy vấn báo cáo mà mô hình phải hỗ trợ; xác định chỉ mục cần thiết dựa trên truy vấn đó.

**Gợi ý đối chiếu:** `OrderPacked`, `ShipmentHandedOver`, `DeliveryAttempted`, `DeliverySucceeded`, `DeliveryFailed` là các tên ứng viên. Cần quy định rõ `DeliveryAttempted` có phát cho cả lần thành công hay chỉ phát một lần trước kết quả; nếu dùng cả `DeliveryAttempted` và `DeliveryFailed`, không được cộng cả hai làm hai lượt giao. Bản ghi lần giao nên có `attempt_id` ổn định và có bằng chứng từ nguồn được tin cậy. Nếu kết quả thành công được biết muộn, không tự đặt `occurred_at = recorded_at` nếu yêu cầu báo cáo dựa trên thời điểm giao thực tế.

Một mô hình tốt cho câu hỏi này không chỉ có schema hợp lệ, mà còn phải trả lời được: **đã xảy ra điều gì, với ai/đối tượng nào, bằng dữ kiện nào, vào thời điểm nào, và hệ thống có thể kiểm chứng điều đó ra sao?** Chính những câu trả lời ấy quyết định tên sự kiện, khóa liên kết, cấu trúc payload, ràng buộc và phép truy vấn đáng tin cậy.
