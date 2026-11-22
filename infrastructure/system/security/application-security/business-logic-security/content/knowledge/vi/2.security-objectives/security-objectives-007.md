# Traceability of business changes — Khả năng truy vết thay đổi nghiệp vụ

Một đơn hàng đang được ghi nhận là đã phê duyệt với tổng tiền 900.000 đồng. Chỉ nhìn bản ghi hiện tại, nhóm vận hành không biết số tiền này đã có từ lúc gửi duyệt hay được sửa sau đó; ai đã sửa; quyết định phê duyệt có áp dụng cho nội dung hiện tại không; và một tác vụ thanh toán chạy nền có liên quan đến yêu cầu nào của người dùng.

**Traceability of business changes**, hay khả năng truy vết thay đổi nghiệp vụ, giúp nối trạng thái hiện tại với những hành động đã tạo ra nó. Mục tiêu là có bằng chứng đủ tin cậy để tái dựng diễn biến, xác định chủ thể và đối chiếu thay đổi với quy tắc nghiệp vụ.

Trong chương **Security Objectives**, bài học này đặt truy vết vào bối cảnh bảo vệ quy trình phê duyệt, giá, quyền trên đối tượng, transaction và idempotency. Trọng tâm là thiết kế lịch sử thay đổi có ý nghĩa nghiệp vụ, thay vì chỉ thu thập thật nhiều dòng log kỹ thuật.

## 1. Truy vết cần trả lời được những gì?

Với một thay đổi quan trọng, hệ thống nên có khả năng trả lời:

- **Ai khởi xướng và ai thực thi?** Một người dùng, tác vụ định kỳ, dịch vụ tích hợp hay người thao tác thay mặt người khác?
- **Đối tượng nào bị thay đổi?** Thuộc tổ chức nào, phiên bản nào và có liên quan đến quyết định nào trước đó?
- **Thay đổi có ý nghĩa gì?** Sửa giá, gửi duyệt, phê duyệt, thu hồi phê duyệt, khởi tạo thanh toán hay xác nhận khoản thu?
- **Trước và sau khác nhau thế nào?** Trường nào thay đổi, nội dung được duyệt là bản nào và tác động tài chính là bao nhiêu?
- **Vì sao được thực hiện?** Theo chính sách hoặc quyết định nào; có lý do nghiệp vụ hay cơ chế đặc biệt nào không?
- **Khi nào và theo quan hệ nào?** Sự kiện xảy ra trong chuỗi xử lý nào; nguyên nhân trực tiếp là lệnh hay sự kiện nào?
- **Kết quả thật sự là gì?** Thay đổi đã commit, bị từ chối, đã rollback hay đang chờ xác minh tác động bên ngoài?

Không phải mọi loại dữ liệu đều cần ghi cùng mức chi tiết. Phạm vi nên dựa trên tài sản và quy tắc cần bảo vệ: tiền, giá, hạn mức, quyền truy cập, trạng thái phê duyệt và các quyết định làm thay đổi quyền lợi.

### 1.1. Phân biệt các loại dấu vết

| Loại thông tin | Mục đích chính | Ví dụ | Giới hạn khi dùng riêng lẻ |
| --- | --- | --- | --- |
| Log kỹ thuật | Chẩn đoán hoạt động chương trình | Gọi repository mất 20 ms, kết nối thất bại | Có thể không cho biết ý nghĩa nghiệp vụ hoặc trạng thái đã commit |
| Distributed trace | Theo dõi đường xử lý qua thành phần | Request đi qua API, order-service và payment-service | Một span thành công không tự chứng minh khoản thu hoặc thay đổi dữ liệu hợp lệ |
| Audit nghiệp vụ | Ghi nhận hành động và thay đổi có ý nghĩa | Người X duyệt bản nội dung Y theo chính sách Z | Cần bảo đảm tính đầy đủ, liên kết và bảo vệ bản ghi |
| Lịch sử phiên bản | Lưu các bản nội dung qua thời gian | Đơn có bản nội dung 7 và 8 | Hai snapshot chưa chắc giải thích ai thay đổi hoặc vì sao |
| Security event | Theo dõi hành vi liên quan bảo mật | Bị từ chối vì không có quyền trên đối tượng | Một lần thử bị chặn khác với một thay đổi nghiệp vụ đã xảy ra |

Các loại dấu vết hỗ trợ nhau. Không nên coi `HTTP 200`, một span kết thúc hoặc một dòng “approve success” ghi trước commit là bằng chứng đủ rằng nghiệp vụ đã hoàn tất.

Truy vết cũng không tự đồng nghĩa với chống chối bỏ tuyệt đối. Một bản ghi gắn với tài khoản cho biết hành động được hệ thống quy cho tài khoản đó theo cơ chế xác thực; nó chưa chứng minh ý định của một con người, cũng không loại trừ tài khoản bị chiếm quyền hoặc thông tin xác thực bị dùng chung.

## 2. Ví dụ xuyên suốt: sửa giá sau phê duyệt

Giả sử hệ thống quản lý đơn hàng áp dụng các quy tắc:

1. Giá và tổng tiền có thẩm quyền được xác định ở máy chủ.
2. Đơn phải được duyệt trước khi thanh toán.
3. Người tạo không được tự duyệt đơn của mình theo chính sách của tổ chức.
4. Phê duyệt gắn với một phiên bản nội dung cụ thể.
5. Sửa nội dung ảnh hưởng đến quyết định duyệt phải làm mất hiệu lực phê duyệt cũ hoặc bị từ chối theo chính sách.
6. Một nghĩa vụ thanh toán không được thu trùng do retry.

Hệ thống phân biệt **aggregate version**, tức phiên bản thay đổi của đơn, với **content revision**, tức phiên bản nội dung mà quyết định phê duyệt tham chiếu. Hai số này có thể tăng theo những quy tắc khác nhau.

Một lịch sử hợp lệ có thể là:

| Phiên bản đơn sau thay đổi | Phiên bản nội dung | Hành động | Kết quả có ý nghĩa |
| --- | --- | --- | --- |
| 12 | 7 | Gửi duyệt | Nội dung 7 có tổng 1.000.000 VND đang chờ duyệt |
| 13 | 7 | Người được phép phê duyệt | Phê duyệt có hiệu lực với nội dung 7 |
| 14 | 8 | Người có quyền sửa giá | Tổng đổi thành 900.000 VND; phê duyệt cũ mất hiệu lực; đơn trở về nháp |
| 15 | 8 | Gửi duyệt lại | Nội dung 8 đang chờ quyết định mới |
| 16 | 8 | Người được phép phê duyệt | Quyết định mới gắn với nội dung 8 |

Nếu chỉ lưu `updatedBy`, `updatedAt` và trạng thái hiện tại, phần lớn thông tin trên bị mất sau những lần cập nhật tiếp theo.

Nếu lịch sử cho thấy đơn đổi từ phiên bản 13 sang 14 nhưng vẫn giữ phê duyệt cho nội dung 7 rồi được thanh toán theo nội dung 8, có cơ sở để kiểm tra một vi phạm cụ thể. Nếu thiếu lịch sử liên kết, việc phát hiện và đánh giá vi phạm khó hơn nhiều.

Audit giúp điều tra và phát hiện sai lệch. Các guard chuyển trạng thái và kiểm tra quyền vẫn phải chủ động chặn thay đổi trái phép; ghi lại một lần sửa giá sai không làm cho việc sửa giá đó trở nên an toàn.

## 3. Viết invariant cho chính cơ chế truy vết

Một hệ thống audit có thể tồn tại nhưng vẫn không đáp ứng mục tiêu. Cần đặt yêu cầu có thể kiểm chứng cho nó.

| Mã | Invariant truy vết | Dấu hiệu vi phạm |
| --- | --- | --- |
| T1 | Mọi thay đổi nghiệp vụ nằm trong phạm vi bắt buộc đều có dấu vết chuẩn tương ứng | Đơn thay đổi qua API quản trị nhưng không có lịch sử |
| T2 | Thay đổi commit và bản ghi audit bắt buộc được gắn kết theo cơ chế nguyên tử đã thiết kế | Trạng thái đổi nhưng mất audit khi hệ thống log ngừng hoạt động |
| T3 | Không có sự kiện chuẩn khẳng định thay đổi đã commit nếu transaction đã rollback | Có bản ghi `ORDER_APPROVED` thành công nhưng đơn chưa bao giờ được duyệt |
| T4 | Chủ thể, tổ chức và nguồn thay đổi lấy từ ngữ cảnh đáng tin tương ứng | Client tự gửi `approvedBy=admin` và được ghi thành người duyệt thật |
| T5 | Có thể liên kết thay đổi với phiên bản, thao tác và nguyên nhân liên quan | Biết ai gọi API nhưng không biết bản nội dung nào được duyệt |
| T6 | Retry và việc gửi lại sự kiện không làm lịch sử chuẩn hiểu sai số thay đổi thực tế | Một quyết định bị ghi thành hai lần phê duyệt độc lập |
| T7 | Quyền sửa, xóa, đọc và xuất audit được giới hạn theo chính sách | Người sửa giá có thể xóa luôn dấu vết hoặc xem dữ liệu tổ chức khác |
| T8 | Bản ghi còn đọc hiểu và tra cứu được trong thời hạn lưu đã xác định | Dữ liệu còn tồn tại nhưng mất schema hoặc mất bản nội dung được tham chiếu |

“Dấu vết chuẩn” ở đây là nguồn mà hệ thống dùng để ghi nhận sự kiện nghiệp vụ đã xác lập. Một sự kiện có thể được sao chép sang nhiều hệ thống; những bản sao ấy không phải những thay đổi nghiệp vụ mới.

Một lệnh cũng có thể tạo nhiều sự kiện có ý nghĩa. Không nên áp đặt “mỗi request chỉ có một audit event” cho mọi trường hợp. Điều cần có là cách nhận diện các sự kiện và liên hệ chúng với cùng thao tác hoặc thay đổi nghiệp vụ.

## 4. Chọn đơn vị ghi nhận theo ý nghĩa nghiệp vụ

### 4.1. Ghi hành động thay vì chỉ ghi câu SQL

Dòng “bảng orders được cập nhật” không đủ giải thích quyết định. Một sự kiện như `ORDER_APPROVED` hoặc `ORDER_COMMERCIAL_TERMS_CHANGED` rõ ý nghĩa hơn vì nó mô tả hành động trong ngôn ngữ nghiệp vụ.

Ví dụ, một lần sửa giá có thể đồng thời:

```text
Đổi tổng tiền: 1.000.000 → 900.000 VND.
Tăng phiên bản nội dung: 7 → 8.
Chuyển trạng thái: APPROVED → DRAFT.
Làm mất hiệu lực tham chiếu phê duyệt cho nội dung 7.
```

Có thể biểu diễn bằng một sự kiện bao gồm các thay đổi liên quan, hoặc nhiều sự kiện được liên kết theo cùng một thao tác. Mô hình cần cho phép hiểu rằng đây là kết quả của cùng quyết định sửa điều khoản thương mại, thay vì các dòng cập nhật rời rạc không rõ nguyên nhân.

### 4.2. Chỉ lưu trạng thái trước và sau chưa luôn đủ

Hai snapshot giúp biết dữ liệu đã thay đổi thế nào. Nhưng để trả lời vì sao, có thể cần thêm loại hành động, lý do, chủ thể, phiên bản chính sách, lệnh nguồn và dữ liệu mà người duyệt thực sự nhìn thấy.

Nếu dùng tham chiếu đến một bản nội dung thay vì lưu toàn bộ snapshot, bản đó phải còn tồn tại, được bảo vệ và có thể truy xuất trong thời hạn cần đối chiếu. Tham chiếu tới một bản ghi có thể bị sửa đè không giữ được ý nghĩa lịch sử.

### 4.3. Xử lý batch và thay đổi bù rõ ràng

Một lệnh cập nhật hàng loạt nên có định danh cấp lệnh và liên kết tới từng kết quả cần truy vết. Nếu batch cho phép thành công một phần, audit phải phản ánh đúng các đối tượng thực sự commit, không chỉ ghi “batch thành công”.

Nếu hủy hoặc sửa một quyết định cũ, hãy ghi sự kiện mới như `APPROVAL_REVOKED` hoặc `ORDER_PRICE_CORRECTED`, tham chiếu tới quyết định liên quan. Việc âm thầm chỉnh lại lịch sử làm mất khả năng tái dựng điều đã xảy ra.

Tác vụ đồng bộ, script vận hành và công cụ quản trị cũng nằm trong phạm vi nếu chúng thay đổi các dữ liệu được bảo vệ. Nếu một đường thay đổi đi trực tiếp vào cơ sở dữ liệu, cần thiết kế cách ghi nhận riêng và thừa nhận giới hạn quy kết khi chỉ biết tài khoản kỹ thuật dùng chung.

## 5. Thiết kế nội dung một audit event

Không có schema duy nhất phù hợp mọi hệ thống. Tuy nhiên, một sự kiện thay đổi quan trọng thường cần các nhóm thông tin sau.

| Nhóm | Trường minh họa | Ý nghĩa |
| --- | --- | --- |
| Nhận diện sự kiện | `eventId`, `eventType`, `schemaVersion` | Phân biệt sự kiện, loại hành động và cách giải nghĩa payload |
| Phạm vi | `tenantId`, `aggregateType`, `aggregateId` | Xác định tổ chức và đối tượng nghiệp vụ |
| Phiên bản | `aggregateVersionBefore`, `aggregateVersionAfter`, `contentRevision` | Liên kết thay đổi với trạng thái và nội dung được quyết định |
| Chủ thể | Người khởi xướng, dịch vụ thực thi, tham chiếu ủy quyền | Phân biệt người yêu cầu với thành phần thực hiện |
| Liên kết xử lý | `operationId`, `requestId`, `correlationId`, `causationId` | Nối retry, request, chuỗi dịch vụ và nguyên nhân trực tiếp |
| Thời gian | `occurredAt`, thời điểm nhận hoặc công bố nếu cần | Phân biệt mốc thời gian và độ trễ xử lý |
| Kết quả | Loại kết quả phù hợp với sự kiện | Phân biệt đã commit, bị từ chối và tác động chưa rõ |
| Thay đổi | Giá trị trước/sau hoặc tham chiếu snapshot | Giải thích tác động nghiệp vụ thực tế |
| Quyết định | Mã lý do, tham chiếu chính sách, ngữ cảnh cần thiết | Hỗ trợ đối chiếu tại sao hành động được chấp thuận |

Ví dụ sự kiện chuẩn cho một phê duyệt đã commit:

```json
{
  "eventId": "audit-2a1f",
  "eventType": "ORDER_APPROVED",
  "schemaVersion": 1,
  "tenantId": "organization-a",
  "aggregateType": "ORDER",
  "aggregateId": "order-2048",
  "aggregateVersionBefore": 12,
  "aggregateVersionAfter": 13,
  "contentRevision": 7,
  "actor": {
    "initiatorType": "USER",
    "initiatorId": "user-42",
    "executorType": "SERVICE",
    "executorId": "order-service",
    "delegationId": null
  },
  "operationId": "operation-771",
  "requestId": "request-004",
  "correlationId": "workflow-909",
  "causationId": "command-approve-771",
  "occurredAt": "2026-11-21T03:15:14.218Z",
  "outcome": "COMMITTED",
  "reasonCode": "STANDARD_APPROVAL",
  "decisionContext": {
    "policyId": "order-approval",
    "policyVersion": "2026-10-01",
    "approvedAmount": "1000000",
    "currency": "VND"
  },
  "changes": {
    "status": {
      "before": "PENDING_APPROVAL",
      "after": "APPROVED"
    },
    "approvedContentRevision": {
      "before": null,
      "after": 7
    }
  }
}
```

Trong ví dụ, số tiền được biểu diễn bằng chuỗi thập phân và có tiền tệ đi kèm để tránh cách hiểu mơ hồ. Hệ thống cần thống nhất quy ước biểu diễn số, thời gian và giá trị rỗng.

`occurredAt` có thể là thời điểm service tạo sự kiện trong lúc xử lý. Nó không tự là thời điểm commit chính xác của cơ sở dữ liệu. Nếu cần mốc commit, phải lấy từ một cơ chế có ngữ nghĩa tương ứng, thay vì đặt tên `committedAt` cho kết quả gọi đồng hồ trước khi transaction hoàn tất.

`outcome=COMMITTED` chỉ được xem là sự thật nghiệp vụ sau khi transaction chứa bản ghi đã commit. Không được phát một bản khẳng định tương tự ra ngoài trước commit rồi bỏ mặc nó khi transaction rollback.

### 5.1. Lưu đủ ngữ cảnh nhưng tránh sao chép tràn lan

Audit có thể cần số tiền, trạng thái và tham chiếu bản nội dung để giải thích quyết định. Điều đó không có nghĩa phải lưu toàn bộ request, response, chứng từ và mọi dữ liệu cá nhân vào mỗi sự kiện.

Không nên ghi mật khẩu, token truy cập hoặc khóa bí mật. Với dữ liệu nhạy cảm cần cho đối chiếu, chọn trường có mục đích rõ ràng, áp dụng quyền đọc phù hợp và quản lý thời hạn lưu.

Một mã băm của snapshot có thể giúp kiểm tra sự khớp nhau với bản nội dung đang có. Chỉ mã băm, khi không còn bản nội dung tương ứng, không cho biết những dữ liệu cần đọc để giải thích quyết định.

## 6. Danh tính, lý do và quan hệ nhân quả phải đáng tin

### 6.1. Phân biệt người khởi xướng với dịch vụ thực thi

Một yêu cầu thanh toán có thể do người mua gửi, được order-service tiếp nhận rồi payment-service thực hiện sau vài giây. Nếu chỉ ghi `actor=payment-service`, dấu vết mất người khởi xướng. Nếu chỉ ghi người mua, dấu vết mất thông tin thành phần thực thi.

Với thao tác thay mặt người khác hoặc hỗ trợ vận hành, cần giữ được các danh tính và quan hệ ủy quyền theo thiết kế. Không nên ghi đè người thực hiện thành người được đại diện rồi mất dấu việc ủy quyền.

Danh tính lấy từ ngữ cảnh xác thực và kênh dịch vụ đã được kiểm tra. Trường `actorId`, `approvedBy` hoặc header do client có thể tự đặt không được tự trở thành căn cứ quy kết.

Địa chỉ IP, user-agent hoặc thiết bị có thể là ngữ cảnh hỗ trợ điều tra, nhưng chúng không tự chứng minh danh tính con người. Nếu dùng thông tin từ proxy, phải xác định ranh giới proxy nào đáng tin.

### 6.2. Mỗi loại định danh trả lời một câu hỏi

| Định danh | Câu hỏi nó hỗ trợ |
| --- | --- |
| `eventId` | Đây có phải cùng một sự kiện đang được gửi lại không? |
| `operationId` | Những lần xử lý này có thuộc cùng một thao tác logic không? |
| `requestId` | Dấu vết nào thuộc cùng một lần nhận request? |
| `correlationId` | Những hoạt động nào thuộc cùng luồng liên quan? |
| `causationId` | Lệnh hoặc sự kiện nào trực tiếp dẫn tới sự kiện này? |
| `aggregateId` và phiên bản | Đối tượng đã chuyển từ bản nào sang bản nào? |

Một retry có thể có `requestId` mới nhưng cùng `operationId`. Cùng một `correlationId` có thể bao gồm nhiều hành động, nhiều đối tượng và nhiều kết quả; không nên dùng nó như khóa duy nhất của một thay đổi.

Định danh do bên ngoài gửi có thể hữu ích để liên kết, nhưng không phải bằng chứng phân quyền. Cần kiểm tra định dạng, phạm vi và cách ghi nhận; các định danh có thẩm quyền trong hệ thống phải có cơ chế tạo hoặc xác minh phù hợp.

### 6.3. Lý do giải thích quyết định không thay thế kiểm tra quyền

Một ghi chú như “khách hàng quan trọng” có thể là lời khai của người thao tác. Nó không chứng minh người đó được phép giảm giá hoặc bỏ qua phê duyệt.

Nên phân biệt lý do nghiệp vụ do người dùng cung cấp với kết quả kiểm tra của hệ thống và tham chiếu chính sách. Dữ liệu tự do cần được ghi theo cấu trúc và hiển thị an toàn để tránh giả mạo dòng log hoặc chèn nội dung khi người vận hành đọc lại.

Lưu phiên bản chính sách chỉ hữu ích cho việc đối chiếu nếu còn biết phiên bản đó có nội dung gì. Với quyết định cần giải thích lâu dài, cần bảo tồn chính sách hoặc các dữ liệu quyết định liên quan theo thời hạn đã chọn.

## 7. Gắn thay đổi và audit bằng transaction

### 7.1. Hai thứ tự ghi dễ tạo lịch sử sai

```text
Cách A:
Cập nhật đơn và commit.
Gửi audit tới hệ thống khác.
Nếu bước gửi thất bại → thay đổi có thật nhưng thiếu dấu vết bắt buộc.

Cách B:
Gửi audit khẳng định thành công tới hệ thống khác.
Cập nhật đơn.
Nếu transaction rollback → có dấu vết thành công nhưng thay đổi không tồn tại.
```

Đổi thứ tự giữa hai lần ghi độc lập không tạo ra tính nguyên tử.

Khi trạng thái nghiệp vụ và audit chuẩn nằm trong cùng cơ sở dữ liệu có transaction phù hợp, một thiết kế có thể là:

```text
BEGIN
  Kiểm tra quyền và điều kiện nghiệp vụ.
  Cập nhật trạng thái đơn với cơ chế chống xung đột.
  Ghi audit_event bất biến cho thay đổi đó.
  Ghi outbox_message nếu cần chuyển sự kiện sang hệ thống khác.
COMMIT
```

Với thay đổi được quy định bắt buộc có audit, nếu ghi audit chuẩn thất bại thì transaction thay đổi phải thất bại theo hợp đồng này. Đây là quyết định thiết kế cho loại thay đổi đó, không phải yêu cầu rằng mọi dòng log debug đều phải làm dừng nghiệp vụ.

### 7.2. Minh họa service Java

Đoạn sau minh họa quan hệ giữa cập nhật, audit và outbox. Các repository phải dùng chung transaction và nguồn dữ liệu tương ứng. `OperationContext` đã được thiết lập, kiểm tra phạm vi và nội dung ở ranh giới tiếp nhận lệnh; không phải metadata được tin trực tiếp từ client.

```java
@Transactional
public ApprovalResult approve(
        AuthenticatedActor actor,
        UUID orderId,
        long expectedContentRevision,
        OperationContext operation) {

    Order order = orders.findInTenant(actor.tenantId(), orderId)
            .orElseThrow(OrderNotVisibleException::new);

    policy.requireCanApproveCurrentRevision(
            actor, order, expectedContentRevision);

    OrderAuditSnapshot before = order.auditSnapshot();
    order.approveCurrentContent(actor.userId(), clock.instant());

    int changed = orders.updateIfVersionMatches(
            order, before.aggregateVersion());
    if (changed != 1) {
        throw new ConcurrentOrderChangeException();
    }

    AuditEvent event = auditFactory.orderApproved(
            actor, operation, before, order.auditSnapshot());

    auditEvents.append(event);
    outboxMessages.append(AuditEnvelope.from(event));

    return ApprovalResult.from(order);
}
```

Trong hợp đồng minh họa này:

- `requireCanApproveCurrentRevision` kiểm tra quyền theo đối tượng, trạng thái chờ duyệt, chính sách không tự duyệt, hạn mức và phiên bản nội dung.
- `approveCurrentContent` thực hiện chuyển trạng thái hợp lệ, ghi tham chiếu nội dung được duyệt và tăng phiên bản aggregate theo quy ước của mô hình.
- `updateIfVersionMatches` chỉ cập nhật nếu phiên bản hiện tại còn khớp, đồng thời giữ đúng phạm vi tổ chức. Mọi đường cập nhật cùng aggregate phải tuân thủ giao thức phiên bản tương thích.
- Snapshot sau thay đổi phải phản ánh đúng những giá trị được lưu. Nếu phiên bản hoặc thời gian do cơ sở dữ liệu sinh, phải lấy giá trị thực tế theo cơ chế lưu trữ trước khi lập dấu vết tương ứng.
- Lỗi xung đột, lỗi audit hoặc lỗi outbox phải làm rollback transaction theo cấu hình ứng dụng.

Đoạn mã tập trung vào tính gắn kết của audit. Nếu hạn mức hoặc quyền nằm ở dữ liệu khác có thể đổi đồng thời, cần cơ chế phối hợp bổ sung để giữ các invariant đó; kiểm tra phiên bản đơn không tự bảo vệ mọi bảng liên quan.

### 7.3. Outbox giúp chuyển sự kiện sau commit

Outbox lưu thông điệp cần công bố trong cùng transaction với thay đổi. Một publisher đọc các thông điệp đã commit rồi gửi sang broker hoặc kho audit tập trung.

Nhờ đó, lỗi tạm thời của hệ thống đích không nhất thiết làm mất sự kiện: thông điệp vẫn còn để gửi lại. Tuy nhiên, cần cơ chế retry, theo dõi tồn đọng, dung lượng và xử lý lỗi kéo dài.

Bảng outbox thường có trạng thái gửi, số lần thử hoặc thời hạn dọn dẹp. Nó không mặc nhiên thay thế kho audit được lưu theo chính sách. Nếu xóa outbox sau khi gửi, audit chuẩn hoặc bản lưu cần thiết vẫn phải còn ở nơi được thiết kế.

### 7.4. Ghi nhận lần thử bị từ chối khác với thay đổi đã commit

Một sự kiện `APPROVAL_DENIED` có thể cần tồn tại dù transaction xử lý nghiệp vụ rollback. Nếu ghi nó trong chính transaction đã rollback, nó cũng bị mất.

Cần một đường ghi nhận lần thử có ngữ nghĩa riêng, chẳng hạn cơ chế security event độc lập sau khi đã xác định kết quả. Nếu đường đó không có cùng bảo đảm giao nhận với audit chuẩn, cần biết giới hạn và theo dõi mất sự kiện tương ứng.

Không nên tạo một transaction phụ khẳng định `ORDER_APPROVED` chỉ để bản ghi đó sống sót qua rollback. Lần thử và sự thật thay đổi phải được phân biệt rõ.

## 8. Retry, đồng thời và thứ tự lịch sử

### 8.1. Một thao tác có thể có nhiều lần thử

Giả sử phê duyệt đã commit nhưng client mất response rồi gửi lại. Hệ thống có thể ghi hai lần tiếp nhận request và một kết quả trả lại từ idempotency, nhưng chỉ có một quyết định phê duyệt nghiệp vụ nếu thao tác không được thực hiện thêm.

```text
Request A → operation X → phê duyệt commit → event E.
Mất response.
Request B → operation X → trả kết quả đã xác lập.
```

Không tạo thêm một sự kiện độc lập mang ý nghĩa “đơn lại được phê duyệt lần nữa” chỉ vì request B được nhận. Nếu cần quan sát retry, dùng sự kiện lần thử hoặc loại sự kiện phản ánh đúng việc trả lại kết quả cũ.

Idempotency theo khóa không thay thế kiểm tra trạng thái hoặc invariant nghiệp vụ. Hai khóa khác nhau vẫn không được biến một nghĩa vụ đã hoàn tất thành hai lần thu tiền hợp lệ.

### 8.2. Publisher có thể gửi cùng sự kiện nhiều lần

Một publisher có thể gửi thành công rồi dừng trước khi đánh dấu đã gửi. Sau khi chạy lại, nó gửi tiếp cùng sự kiện. Vì vậy, consumer cần nhận diện sự kiện đã xử lý bằng định danh ổn định hoặc cơ chế tương đương.

Nếu consumer ghi vào một kho cục bộ, việc ghi dấu đã xử lý và cập nhật projection cần có tính nguyên tử phù hợp; nếu hai bước độc lập, lỗi ở giữa vẫn có thể tạo mất hoặc lặp tác động.

Không nên gọi toàn bộ chuỗi là “exactly once” chỉ vì có `eventId`. Điều cần kiểm chứng là gửi lại cùng sự kiện không tạo thêm một thay đổi hay một bản ghi chuẩn bị hiểu là sự kiện mới.

### 8.3. Không dùng timestamp làm nguồn thứ tự duy nhất

Đồng hồ giữa các máy có thể lệch. Sự kiện phát sinh trước có thể được nhận sau vì hàng đợi hoặc retry. Nhiều sự kiện có thể có cùng độ phân giải thời gian.

Đối với cùng một aggregate, phiên bản hoặc số thứ tự có quy tắc rõ ràng giúp tái dựng chuyển đổi. Với nhiều aggregate hoặc nhiều dịch vụ, cần thêm quan hệ nhân quả và định danh thao tác; không nên suy ra một thứ tự toàn cục chắc chắn chỉ bằng cách sắp xếp thời gian.

Nếu một thay đổi aggregate tạo nhiều sự kiện, cần có thứ tự sự kiện trong thay đổi hoặc cách diễn giải tương ứng. Ràng buộc duy nhất trên cặp `(aggregateId, aggregateVersion)` chỉ phù hợp nếu mô hình thật sự quy định một sự kiện chuẩn cho mỗi phiên bản; không phải quy tắc chung.

Kho audit tập trung có thể cập nhật chậm hơn trạng thái nghiệp vụ. Khi điều tra, cần biết độ trễ công bố, số thông điệp tồn và nguồn chuẩn để phân biệt “chưa được chuyển tới” với “không được ghi”.

## 9. Truy vết tác động qua nhiều dịch vụ và hệ thống ngoài

Một transaction cơ sở dữ liệu cục bộ không tự bao phủ nhà cung cấp thanh toán bên ngoài. Vì vậy, không thể chỉ có một nhãn “thanh toán thành công” cho mọi giai đoạn.

Một chuỗi sự kiện có thể gồm:

```text
PAYMENT_REQUESTED
→ PAYMENT_PROVIDER_REQUEST_SENT
→ PAYMENT_PROVIDER_CONFIRMED
→ ORDER_PAYMENT_RECORDED
```

Nếu request tới nhà cung cấp timeout, kết quả có thể chưa rõ. Hệ thống có thể cần trạng thái và sự kiện như `PAYMENT_RECONCILIATION_REQUIRED`, rồi truy vấn hoặc đối soát trước khi kết luận.

Các sự kiện phải mô tả đúng điều nguồn ghi biết được:

- `PAYMENT_REQUESTED` không có nghĩa tiền đã được thu.
- Timeout không tự chứng minh nhà cung cấp chưa xử lý.
- Callback đã nhận không tự chứng minh callback hợp lệ hoặc đã áp dụng vào trạng thái đơn.
- `ORDER_PAYMENT_RECORDED` phản ánh thay đổi cục bộ; cần liên kết với khoản thu hoặc bằng chứng xác nhận phù hợp.

Để nối chuỗi, có thể cần định danh nghĩa vụ thanh toán, lần thử, khóa idempotency có phạm vi, tham chiếu giao dịch nhà cung cấp, sự kiện nguồn và định danh thao tác nội bộ. Không nên dùng chung một trường cho mọi loại định danh nếu chúng có ý nghĩa khác nhau.

Callback lặp là tình huống bình thường trong nhiều thiết kế giao nhận. Có thể ghi nhận lần nhận lặp phục vụ vận hành, nhưng không được biến nó thành khoản thu hoặc thay đổi trạng thái lần hai. Một sự kiện bị bỏ qua do đã xử lý cũng cần được diễn giải đúng, thay vì mặc định đó là một cuộc tấn công.

Nếu quy trình dùng hành động bù, chẳng hạn hoàn tiền sau khi không thể hoàn tất đơn, lịch sử nên giữ cả khoản thu ban đầu và khoản hoàn liên quan. Hành động bù không làm cho sự kiện ban đầu chưa từng xảy ra.

## 10. Bảo vệ chính dữ liệu audit

### 10.1. Giới hạn sửa và xóa

Một chính sách thường dùng là ứng dụng chỉ được thêm audit event, còn quyền sửa hoặc xóa được giới hạn cho cơ chế quản trị có kiểm soát. Cần xem xét cả tài khoản vận hành, tài khoản cơ sở dữ liệu, bản sao và công cụ quản trị.

Chỉ đặt tên bảng là `immutable_audit_log` không tạo ra tính bất biến. Các ràng buộc, quyền truy cập và cơ chế lưu trữ phải thực thi mục tiêu đó.

Với mức bảo vệ cao hơn, có thể dùng bản sao độc lập, cơ chế lưu giữ chống sửa trong phạm vi cấu hình tương ứng, chữ ký hoặc chuỗi băm. Các biện pháp cần được đánh giá theo người có khả năng sửa dữ liệu, giữ khóa hoặc quản trị nơi lưu.

Một chuỗi băm không tự phát hiện được mọi sửa đổi nếu cùng tác nhân có thể viết lại toàn bộ chuỗi và giá trị đối chiếu. Cần một điểm kiểm chứng hoặc ranh giới tin cậy phù hợp. Chữ ký giúp kiểm tra nguồn hoặc tính toàn vẹn theo mô hình khóa; nó không tự chứng minh nội dung nghiệp vụ đã được kiểm tra đúng.

### 10.2. Audit cũng chứa dữ liệu nghiệp vụ nhạy cảm

Giá trước và sau, hạn mức, nhận xét duyệt hoặc danh tính người liên quan có thể nhạy cảm. Quyền đọc lịch sử nên có phạm vi theo tổ chức, đối tượng và loại dữ liệu, thay vì cho mọi tài khoản hỗ trợ xem toàn bộ.

Export audit, truy vấn điều tra và truy cập đặc quyền cũng cần dấu vết phù hợp. API xem lịch sử phải tránh việc người dùng đổi `aggregateId` rồi đọc được thay đổi của tổ chức khác.

### 10.3. Thời hạn lưu và khả năng đọc hiểu là một phần thiết kế

Thời hạn lưu phụ thuộc nhu cầu nghiệp vụ và chính sách áp dụng cho hệ thống. Cần quy định nơi lưu, khả năng khôi phục, cách dọn dữ liệu, và cách giữ các liên kết tới nội dung hoặc chính sách được tham chiếu.

`schemaVersion` giúp biết payload được viết theo cấu trúc nào. Khi đổi schema, cần giữ khả năng đọc dữ liệu cũ hoặc chuyển đổi có kiểm soát; không được diễn giải lại lịch sử theo định nghĩa mới mà không biết sự khác biệt.

Các mốc thời gian nên có múi giờ hoặc quy ước UTC rõ ràng. Việc hiển thị giờ địa phương có thể thực hiện ở lớp đọc, trong khi giá trị gốc vẫn được giữ với ngữ nghĩa thống nhất.

## 11. Dùng lịch sử để điều tra một thay đổi đáng ngờ

Giả sử có phản ánh: “Đơn được duyệt 1.000.000 đồng nhưng thanh toán 900.000 đồng.” Một trình tự điều tra có thể là:

1. Xác định đúng tổ chức, đơn hàng, nghĩa vụ thanh toán và nội dung đang xét.
2. Lấy các thay đổi chuẩn của đơn, đối chiếu phiên bản và tìm đoạn lịch sử liên quan.
3. Tìm quyết định duyệt: người duyệt, nội dung được xem, số tiền, chính sách và quyền áp dụng.
4. Kiểm tra thay đổi giá hoặc số lượng sau quyết định đó, cùng việc làm mất hiệu lực phê duyệt.
5. Theo định danh thao tác và quan hệ nhân quả sang các sự kiện thanh toán.
6. Đối chiếu khoản thu thực tế, retry, callback lặp và tình trạng đối soát.
7. Kiểm tra nguồn audit, độ trễ công bố và những đường thay đổi có thể chưa được bao phủ.

Nếu phiên bản 14 làm mất hiệu lực quyết định cho nội dung 7 và phiên bản 16 đã có quyết định mới cho nội dung 8, chênh lệch có thể là kết quả hợp lệ. Nếu không có quyết định mới mà vẫn thanh toán nội dung 8, cần xem xét vi phạm invariant.

Không có bản ghi ở một dashboard chưa đủ để kết luận hành động không xảy ra. Có thể projection chưa cập nhật, bộ lọc sai hoặc một đường ghi bị thiếu audit. Ngược lại, một dòng log tự do khẳng định thành công cũng chưa đủ chứng minh trạng thái đã commit.

Báo cáo điều tra nên phân biệt sự kiện đã được xác nhận, suy luận dựa trên liên kết và phần chưa đủ bằng chứng. Khả năng truy vết tốt giúp giảm phần chưa rõ; nó không cho phép điền những thông tin hệ thống chưa từng ghi nhận.

## 12. Kiểm thử truy vết bằng tình huống lỗi thực tế

Không chỉ kiểm tra “có gọi hàm ghi log”. Cần kiểm tra quan hệ giữa trạng thái nghiệp vụ, dấu vết chuẩn và việc chuyển sự kiện.

| Tình huống | Cách tạo điều kiện | Thuộc tính cần xác minh |
| --- | --- | --- |
| Thay đổi hợp lệ | Phê duyệt đúng chủ thể, trạng thái và revision | Trạng thái commit và audit tham chiếu đúng nội dung |
| Sai quyền | Gọi duyệt trên đơn ngoài phạm vi | Không có thay đổi; sự kiện từ chối không bị ghi thành thành công |
| Giả danh tính | Gửi `actorId` hoặc `approvedBy` khác trong payload | Audit dùng danh tính có thẩm quyền từ máy chủ |
| Sửa giá | Đổi tổng tiền sau duyệt theo chính sách cho phép | Lịch sử chứa thay đổi và việc mất hiệu lực phê duyệt liên quan |
| Xung đột phiên bản | Hai thao tác tranh cùng phiên bản đơn | Chỉ thay đổi thực sự commit có sự kiện chuẩn tương ứng |
| Audit insert lỗi | Làm thao tác ghi audit bắt buộc thất bại | Thay đổi nghiệp vụ rollback theo hợp đồng nguyên tử |
| Outbox insert lỗi | Làm thao tác ghi outbox bắt buộc thất bại | Không commit một thay đổi thiếu thông điệp bắt buộc |
| Transaction rollback | Phát sinh lỗi sau khi đã tạo đối tượng event trong bộ nhớ | Không xuất hiện sự kiện chuẩn khẳng định thay đổi đã commit |
| Mất response | Commit rồi client gửi lại cùng thao tác | Một thay đổi nghiệp vụ; các lần thử được liên kết đúng |
| Gửi trùng sự kiện | Publisher gửi lại cùng `eventId` | Consumer không tạo tác động hoặc sự kiện chuẩn mới ngoài ý nghĩa thật |
| Đích audit ngừng hoạt động | Dừng consumer hoặc hệ thống nhận | Dữ liệu cục bộ và outbox giữ bảo đảm đã chọn; có thể phục hồi chuyển tiếp |
| Dừng sau khi gửi | Publisher dừng trước khi đánh dấu đã gửi | Việc gửi lại được xử lý, không mất liên kết hoặc nhân đôi ý nghĩa |
| Tác động bên ngoài chưa rõ | Nhà cung cấp xử lý nhưng phản hồi timeout | Lịch sử phản ánh chưa rõ và các bước đối soát, không khẳng định sai |
| Đường quản trị hoặc batch | Sửa cùng dữ liệu qua công cụ khác | Vẫn có chủ thể, phạm vi và dấu vết theo hợp đồng |
| Đọc hoặc sửa audit trái phép | Dùng tài khoản ngoài phạm vi | Không tiết lộ hoặc cho sửa lịch sử ngoài quyền |
| Dữ liệu lịch sử cũ | Đọc sự kiện schema cũ sau khi nâng cấp | Vẫn giải nghĩa đúng và truy xuất được tham chiếu cần thiết |

Unit test có thể xác minh nội dung sự kiện được tạo từ trạng thái và chủ thể đúng. Integration test cần cho các bảo đảm rollback, cập nhật có điều kiện, ràng buộc định danh và việc dùng chung transaction. Kiểm thử publisher, consumer và tác động bên ngoài cần quan sát được retry, lỗi giữa chừng và sự nhất quán sau phục hồi.

Khi kiểm tra bất đồng bộ, phải có điều kiện chờ hoàn tất hoặc giới hạn quan sát phù hợp. Kiểm tra quá sớm rồi kết luận thiếu sự kiện có thể nhầm độ trễ với mất dữ liệu; chờ vô hạn lại che mất việc pipeline đã dừng.

Ngoài test, cần theo dõi các tín hiệu vận hành như số thông điệp tồn, tuổi thông điệp cũ nhất, số sự kiện bị từ chối do schema, lỗi ghi audit và khoảng trống phiên bản cần giải thích. Cách phát hiện khoảng trống phải dựa trên quy tắc phiên bản thật của mô hình, vì không phải mọi số phiên bản đều nhất thiết có một loại audit event duy nhất.

## 13. Cách áp dụng khi thiết kế một chức năng thay đổi dữ liệu

Với chức năng nhạy cảm như sửa giá, phê duyệt, điều chỉnh hạn mức hoặc xác nhận thanh toán, có thể đi theo trình tự:

1. **Chọn thay đổi bắt buộc truy vết:** nêu rõ tài sản, quy tắc và các đường ghi nằm trong phạm vi.
2. **Định nghĩa ý nghĩa sự kiện:** điều gì là lần thử, điều gì là thay đổi đã commit, điều gì là tác động bên ngoài chưa xác nhận?
3. **Xác định chủ thể có thẩm quyền:** người khởi xướng, dịch vụ thực thi và quan hệ ủy quyền nếu có.
4. **Liên kết phiên bản và nội dung:** biết quyết định áp dụng cho bản nào, và những trường nào cần lưu để giải thích thay đổi.
5. **Chọn bảo đảm lưu trữ:** transaction cho thay đổi và audit bắt buộc, outbox khi cần chuyển tiếp, cơ chế chống xử lý trùng tương ứng.
6. **Bao phủ retry và cạnh tranh:** giữ định danh thao tác ổn định, phân biệt lần nhận request và sự kiện nghiệp vụ.
7. **Bảo vệ và duy trì lịch sử:** phân quyền, hạn chế sửa xóa, quản lý schema, thời hạn lưu và khả năng đối chiếu tham chiếu.
8. **Kiểm thử thất bại giữa các bước:** không chỉ chứng minh luồng thành công, mà còn chứng minh không mất dấu hoặc tạo bằng chứng sai khi rollback, timeout và gửi lại.

Một yêu cầu cụ thể có thể là:

> Mỗi quyết định phê duyệt đã commit phải có audit chuẩn gắn với người thực hiện, tổ chức, phiên bản nội dung, số tiền và chính sách liên quan. Bản ghi audit và thay đổi trạng thái được commit nguyên tử. Retry của cùng thao tác không tạo quyết định mới; mọi lần chuyển tiếp sự kiện giữ nguyên định danh để có thể nhận diện việc gửi lại.

Khả năng truy vết có giá trị khi có thể nối một thay đổi thực tế với chủ thể, nguyên nhân, nội dung và kết quả đáng tin. Các guard nghiệp vụ ngăn lạm dụng; lịch sử được thiết kế đúng giúp chứng minh điều đã xảy ra, phát hiện sai lệch và xử lý sự cố trên cơ sở bằng chứng.
