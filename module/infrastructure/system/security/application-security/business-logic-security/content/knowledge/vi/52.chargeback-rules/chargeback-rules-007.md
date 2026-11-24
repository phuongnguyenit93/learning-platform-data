# Chargeback audit history: lịch sử kiểm toán cho tranh chấp thanh toán

Trong chương **Chargeback Rules**, audit history là lịch sử có thể dùng để dựng lại một tranh chấp: dữ liệu nào đã đến, ai thực hiện thao tác gì, quyết định dựa trên quyền và phiên bản nào, bằng chứng nào đã được gửi, cùng những tác động tài chính đã được ghi nhận. Một danh sách log có timestamp chưa đủ nếu không liên kết được các sự kiện với đúng hồ sơ và quyết định.

Lịch sử này cũng là một kiểm soát bảo mật nghiệp vụ. Nếu nhân viên có thể sửa dấu vết sau khi bỏ qua phê duyệt, callback trùng làm ghi nhận tiền hai lần hoặc hệ thống xóa một trạng thái lỗi để tạo cảm giác đã gửi đúng hạn, ứng dụng mất khả năng phát hiện và giải thích hành vi sai.

Bài học tập trung vào business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử lạm dụng logic. Các tên trạng thái và chính sách trong ví dụ là thiết kế minh họa; ý nghĩa sự kiện, vòng phản hồi, thời hạn và giao dịch tiền thực tế phải được ánh xạ theo nguồn có thẩm quyền của tích hợp.

## 1. Mục tiêu và câu hỏi lịch sử phải trả lời

Sau bài học, bạn có thể:

- Phân biệt audit nghiệp vụ với log vận hành, thông điệp nguồn và sổ tiền.
- Thiết kế sự kiện có danh tính, quan hệ nhân quả, phiên bản và thời gian rõ ràng.
- Ghi thay đổi trạng thái cùng audit trong transaction mà không làm mất sự kiện bên ngoài.
- Xử lý trùng, đến muộn, sửa sai và replay mà không lặp tác dụng nghiệp vụ.
- Bảo vệ tính toàn vẹn, quyền đọc và khả năng xuất lịch sử theo đúng phạm vi.

Một lịch sử hữu ích cần trả lời được những câu hỏi cụ thể:

1. Tranh chấp này thuộc tenant, merchant account, môi trường và giao dịch nào?
2. Nhân viên nào đã chuẩn bị, duyệt và yêu cầu gửi hồ sơ? Dịch vụ nào thực sự phát lệnh?
3. Người duyệt đã xem snapshot bằng chứng nào, và nội dung gửi có đúng snapshot đó không?
4. Hệ thống biết deadline nào tại thời điểm quyết định? Deadline có được nguồn thay đổi về sau không?
5. Khi timeout, hệ thống đã giữ trạng thái chưa rõ hay tự coi là thất bại rồi gửi lại?
6. Kết quả cuối của case và ảnh hưởng tiền được ghi từ những nguồn nào, có bị tính lặp không?
7. Nếu có điều chỉnh, ai cho phép và điều chỉnh tham chiếu sự kiện gốc nào?

Khả năng trả lời không đến từ việc ghi càng nhiều càng tốt. Nó đến từ một mô hình sự kiện đủ thông tin, liên kết đúng và được bảo vệ trước sửa đổi trái phép.

## 2. Phân biệt các loại sổ và nguồn thông tin

| Thành phần | Mục đích | Không nên được dùng thay cho |
| --- | --- | --- |
| Log vận hành | Chẩn đoán lỗi, độ trễ và hành vi tiến trình | Lịch sử quyết định nghiệp vụ đầy đủ |
| Inbox thông điệp nguồn | Ghi nhận sự kiện đã nhận, phạm vi tích hợp và kết quả xử lý | Bằng chứng rằng mọi thông điệp đều đúng hoặc đã áp dụng |
| Audit nghiệp vụ | Dựng lại hành động, quyết định, phiên bản và căn cứ | Sổ tiền có quy tắc hạch toán riêng |
| Projection hoặc timeline đọc | Giúp người dùng tra cứu trạng thái và diễn biến | Nguồn sự thật có thể tùy ý sửa để thay lịch sử |
| Sổ tài chính | Ghi tác động tiền theo giao dịch nguồn và quy tắc được chọn | Kết luận suy ra từ mọi thay đổi trạng thái case |
| Kho bằng chứng | Giữ artifact, snapshot và biên nhận liên quan | Audit ai đã chọn, duyệt và gửi chúng |

Ví dụ, log `submit completed in 250ms` không cho biết provider chỉ tiếp nhận upload hay đã nhận phản hồi chính thức. Audit cần phân biệt hai hành động đó và liên kết đúng operation.

Một dòng `CASE_CLOSED` cũng không tự chứng minh đã có khoản tiền được ghi có. Kết quả case và movement tài chính có thể là hai sự kiện khác nhau. Mỗi loại sổ phải giữ đúng ý nghĩa của nó rồi liên kết bằng định danh, thay vì cộng hoặc suy diễn theo tên hiển thị.

## 3. Mô hình đe dọa đối với audit history

| Tình huống | Sai sót logic | Hậu quả |
| --- | --- | --- |
| Sửa hoặc xóa sự kiện cũ | Audit là bảng CRUD thông thường | Che việc bỏ qua duyệt hoặc thay nội dung đã gửi |
| Chỉ ghi sau commit bằng lệnh rời | Không có ranh giới nhất quán | Trạng thái thay đổi nhưng thiếu lịch sử |
| Ghi audit rồi rollback nghiệp vụ | Không phân biệt tiếp nhận, thử và thành công | Lịch sử nói thao tác đã thành công dù không có thay đổi |
| Callback đến lại | Không định danh nguồn và tác dụng nghiệp vụ | Hai lần thay trạng thái, hai thông báo hoặc hai bút toán |
| Cùng event ID ở merchant khác | Giả định ID duy nhất toàn hệ thống | Bỏ nhầm sự kiện hoặc ghép sai case |
| Dùng timestamp nguồn để sắp xếp lại mọi thứ | Trộn thời điểm xảy ra với thời điểm biết tin | Mất dấu hệ thống đã quyết định dựa trên dữ liệu nào |
| Replay để dựng timeline | Replay cũng phát lệnh ra provider | Gửi hồ sơ hoặc tác động tiền lần nữa |
| Chỉnh bộ đếm để khớp dashboard | Projection được coi như nguồn sự thật | Che sai lệch và làm mất khả năng đối soát |
| Xuất lịch sử chỉ bằng case ID | Không kiểm tra quyền tenant và merchant | Lộ dữ liệu thanh toán, nhân sự và bằng chứng |
| Nhận cùng event ID nhưng nội dung khác | Tự bỏ qua vì tưởng là duplicate | Không phát hiện dữ liệu nguồn mâu thuẫn |
| Cập nhật hàng loạt actor hoặc snapshot reference | Audit tham chiếu dữ liệu thay đổi mà không có phiên bản | Lịch sử hiển thị khác so với quyết định gốc |
| Lưu toàn bộ payload vào log | Không giảm dữ liệu và phân quyền | Dấu vết điều tra trở thành nguồn lộ bí mật |

Audit history không tự ngăn mọi hành động xấu. Nó giúp đặt ràng buộc trước hành động, phát hiện sai lệch sau hành động và cung cấp căn cứ để điều tra. Quyền nghiệp vụ vẫn phải được kiểm tra ở nơi thực hiện lệnh.

## 4. Các bất biến của lịch sử kiểm toán

### 4.1. Danh tính và phạm vi

1. Mỗi sự kiện gắn đúng case nội bộ cùng phạm vi provider, provider account và môi trường.
2. Actor được phân biệt với chủ thể mà actor đang đại diện và dịch vụ thực thi.
3. Sự kiện chỉ tham chiếu snapshot, approval, operation và giao dịch thuộc quan hệ hợp lệ của case.
4. Đọc, xuất và điều chỉnh lịch sử đều có quyền riêng; quyền xem order không tự cấp quyền xem toàn bộ audit.

### 4.2. Tính toàn vẹn và ý nghĩa

1. Sự kiện đã ghi không được sửa nội dung qua luồng nghiệp vụ thông thường. Sửa sai được biểu diễn bằng sự kiện mới tham chiếu bản cũ.
2. Mỗi thay đổi nghiệp vụ cần audit có liên kết tới đúng phiên bản trước và sau hoặc một căn cứ tương đương.
3. Thao tác đã được yêu cầu, đã phát hành, đã được tiếp nhận và đã có kết quả phải được phân biệt.
4. Bằng chứng là tham chiếu có phiên bản cùng định danh nội dung, không chỉ là URL có thể thay byte.
5. Sự kiện nguồn được giữ riêng với kết luận xử lý của ứng dụng; một thông điệp hợp lệ không tự chứng minh mọi nội dung bên trong đã được ánh xạ đúng.

### 4.3. Đồng thời và tác dụng phụ

1. Với thay đổi cục bộ, audit và trạng thái nghiệp vụ cùng commit hoặc cùng rollback.
2. Một sự kiện nguồn hoặc kết quả logic không được tạo tác dụng nghiệp vụ lặp chỉ vì được giao nhiều lần.
3. Thứ tự ghi của stream có tính xác định; thứ tự thời gian nguồn được lưu riêng để không viết lại lịch sử đã biết.
4. Replay để dựng dữ liệu đọc không phát hành lệnh ra ngoài hoặc ghi lại tiền.
5. Khoảng trống, sự kiện chưa áp dụng và dữ liệu chưa đối soát phải được thể hiện, không được che bằng trạng thái thành công giả.

Các bất biến này cần được dùng để thiết kế transaction, khóa duy nhất, phân quyền và kiểm thử. Một trường `auditEnabled = true` không bảo đảm chúng đã được đáp ứng.

## 5. Mô hình một sự kiện audit đủ để dựng lại quyết định

Một sự kiện có thể được tổ chức như sau:

```json
{
  "eventId": "audit-event-example",
  "schemaVersion": 1,
  "tenantId": "tenant-T",
  "caseId": "case-example",
  "caseSequence": 12,
  "eventType": "EVIDENCE_SUBMISSION_REQUESTED",
  "providerScope": {
    "providerId": "provider-example",
    "providerAccountId": "merchant-account-example",
    "environment": "LIVE"
  },
  "actor": {
    "subjectId": "operator-example",
    "subjectType": "USER",
    "actingForSubjectId": "merchant-example"
  },
  "operationId": "submission-operation-example",
  "causedByEventId": "approval-event-example",
  "correlationId": "correlation-example",
  "recordedAt": "2026-11-22T03:00:00Z",
  "caseVersionBefore": 7,
  "caseVersionAfter": 8,
  "snapshotId": "snapshot-v3",
  "snapshotDigest": "digest-example",
  "approvalId": "approval-example",
  "policyVersion": "policy-v2",
  "decisionCode": "APPROVED_SNAPSHOT_AND_OPEN_RESPONSE_ROUND"
}
```

Giá trị trong ví dụ chỉ minh họa cấu trúc. Những sự kiện không đổi case version không cần giả tạo một thay đổi chỉ để điền đủ trường; chúng có thể dùng kiểu dữ liệu riêng theo `eventType`.

### 5.1. Các định danh có trách nhiệm khác nhau

- `eventId`: định danh bản ghi audit nội bộ.
- `sourceEventId`: định danh thông điệp bên ngoài trong phạm vi tích hợp xác định.
- `operationId`: định danh thao tác nghiệp vụ ổn định qua retry.
- `caseSequence`: thứ tự ghi trong stream của case.
- `correlationId`: gom các bước của một luồng để tra cứu.
- `causedByEventId`: chỉ quan hệ nhân quả khi có căn cứ rõ ràng.

Không dùng một `requestId` thay mọi định danh. Cùng operation có thể đi qua nhiều HTTP request, còn một request có thể tạo nhiều sự kiện có vai trò khác nhau.

### 5.2. Actor không được lấy từ dữ liệu người gọi tự khai

Actor đến từ ngữ cảnh xác thực hoặc danh tính tích hợp đã được xác minh. Với tác vụ nền, ghi dịch vụ thực thi và lệnh gốc mà nó thực hiện; không giả mạo như người dùng đang trực tiếp gọi ở thời điểm worker chạy.

Nếu có ủy quyền hoặc thao tác hỗ trợ thay mặt merchant, lưu quan hệ đại diện cùng căn cứ quyền. Tên hiển thị hiện tại có thể đổi; định danh lịch sử phải vẫn xác định được chủ thể mà không phụ thuộc hoàn toàn vào nhãn đang hiển thị.

## 6. Thời gian và thứ tự: biết tin muộn không phải xảy ra muộn

Nên phân biệt ít nhất:

| Trường | Câu hỏi được trả lời |
| --- | --- |
| `sourceOccurredAt` | Nguồn khai báo sự kiện xảy ra khi nào? |
| `sourceSentAt` | Nếu có, nguồn cho biết đã gửi khi nào? |
| `receivedAt` | Hệ thống tiếp nhận thông điệp khi nào? |
| `recordedAt` | Sự kiện audit được ghi nhận khi nào? |
| `effectiveAt` | Quyết định hoặc điều chỉnh có hiệu lực theo quy tắc nào? |
| `caseSequence` | Sự kiện được ghi ở vị trí nào trong stream? |

Thời điểm do nguồn khai báo không tự đáng tin như nhau cho mọi nguồn. Cần lưu trạng thái xác minh và không dùng timestamp client gửi để chứng minh đã hoàn thành trước deadline.

Ví dụ một chuỗi diễn biến:

| Sequence | Hệ thống ghi nhận | Ý nghĩa |
| --- | --- | --- |
| 1 | Nhận thông báo mở dispute | Lưu nguồn và ngữ cảnh ban đầu |
| 2 | Duyệt snapshot v3 | Biết chính xác người duyệt đã xét nội dung nào |
| 3 | Tiếp nhận lệnh gửi | Tạo operation và giữ lượt gửi |
| 4 | Gửi gặp timeout | Kết quả bên ngoài chưa rõ |
| 5 | Nhận callback tiếp nhận đến muộn | Provider khai báo thời điểm tiếp nhận sớm hơn lúc callback đến |
| 6 | Áp dụng kết quả đối soát | Operation được xác nhận đã tiếp nhận, không phát lệnh mới |

Không đưa sự kiện sequence 5 lên trước sequence 4 rồi xóa dấu đã từng `UNKNOWN`. Có thể hiển thị thêm trục thời gian nguồn, nhưng cần giữ lịch sử hệ thống đã biết gì ở thời điểm quyết định.

`caseSequence` là thứ tự trong một stream, không tự chứng minh thứ tự tuyệt đối giữa mọi case hoặc giữa các hệ thống độc lập. Nếu một quyết định liên quan nhiều đối tượng, lưu các phiên bản và quan hệ cần thiết thay vì suy từ timestamp gần nhau.
