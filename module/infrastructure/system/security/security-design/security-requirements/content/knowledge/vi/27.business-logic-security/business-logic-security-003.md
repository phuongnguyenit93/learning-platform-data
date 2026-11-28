# Server-side state validation — Kiểm chứng trạng thái nghiệp vụ ở phía máy chủ

## 1. Mục tiêu bảo mật của kiểm chứng trạng thái

Server-side state validation là việc máy chủ kiểm tra trạng thái và các điều kiện nghiệp vụ có thẩm quyền trước khi chấp nhận một thao tác. Mục tiêu là bảo đảm yêu cầu chỉ được thực hiện tại thời điểm hợp lệ, trên đúng đối tượng, bởi đúng chủ thể và với những dữ kiện còn hiệu lực.

Một giao diện ẩn nút “Phê duyệt” sau khi hồ sơ đã được duyệt không ngăn client gửi lại API phê duyệt. Một trường JSON ghi `"status": "APPROVED"` không chứng minh đối tượng đã đi qua quy trình duyệt. Ngay cả giá trị do máy chủ gửi trước đó cũng có thể đã lỗi thời khi client sử dụng lại.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, bài học chuyển những rủi ro này thành yêu cầu cụ thể:

- Nguồn nào có thẩm quyền xác định trạng thái hiện tại?
- Ai được thực hiện chuyển trạng thái nào?
- Những điều kiện nghiệp vụ nào phải còn đúng tại thời điểm quyết định?
- Nếu trạng thái thay đổi đồng thời, kết quả nào được phép commit?
- Làm thế nào để retry hoặc sự kiện đến muộn không tạo tác dụng phụ lặp?
- Bằng chứng nào chứng minh mọi đường ghi đều tuân theo quy tắc?

Đích đến là yêu cầu có thể kiểm chứng trong thiết kế, triển khai và kiểm thử; không chỉ là lời nhắc chung “hãy validate trên backend”.

## 2. Phân biệt các lớp kiểm tra

| Lớp kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Kiểm tra định dạng đầu vào | Dữ liệu có đúng kiểu và phạm vi biểu diễn không? | Số tiền là số nguyên dương theo đơn vị nhỏ nhất của đồng tiền |
| Xác thực | Chủ thể đang gửi lệnh là ai? | Phiên đăng nhập hoặc danh tính dịch vụ hợp lệ |
| Phân quyền | Chủ thể có quyền với đối tượng và thao tác không? | Người duyệt thuộc đúng tenant và được giao quyền duyệt |
| Kiểm chứng trạng thái | Thao tác có hợp lệ trong trạng thái hiện tại không? | Chỉ được duyệt hồ sơ đang chờ duyệt |
| Kiểm tra bất biến nghiệp vụ | Điều gì phải luôn được giữ đúng sau commit? | Không tự duyệt; không chi vượt ngân sách; không đổi người nhận sau khi duyệt |
| Kiểm soát cạnh tranh và phát lại | Lệnh đồng thời hoặc lặp lại có phá các điều kiện trên không? | Chỉ một lệnh chuyển hồ sơ sang bước chi được thắng |

Các lớp bổ sung cho nhau. Một người có quyền duyệt vẫn không được duyệt hồ sơ đã hủy. Một hồ sơ đang chờ duyệt cũng không được duyệt bởi người không có quyền.

Kiểm tra kiểu dữ liệu và chữ ký của token không thay thế việc kiểm tra trạng thái hiện hành. Tương tự, transaction không tự hiểu quy tắc nghiệp vụ nếu ứng dụng không đưa đúng điều kiện vào ranh giới nhất quán.

## 3. Ví dụ xuyên suốt: yêu cầu chi nội bộ

Xét hệ thống quản lý yêu cầu chi với các trạng thái:

```text
DRAFT → SUBMITTED → APPROVED → PAYOUT_PENDING → PAID
            |
            +→ REJECTED

DRAFT hoặc SUBMITTED → CANCELLED
```

Giả định chính sách của ví dụ:

- Người lập được sửa hồ sơ nháp và gửi duyệt.
- Sau khi gửi, nội dung cần duyệt được đóng thành một phiên bản xác định.
- Người duyệt phải có quyền tại thời điểm quyết định và không được là người lập.
- Phê duyệt gắn với đúng phiên bản nội dung, số tiền và người nhận.
- Chỉ dịch vụ xử lý chi được chuyển hồ sơ đã duyệt sang chờ kết quả chi.
- Chỉ kết quả thanh toán được xác minh và đối soát đúng mới cho phép đánh dấu đã chi.
- Không cho hủy bằng API thông thường khi đã bước vào quá trình chi.

Đây là chính sách minh họa, không phải quy trình bắt buộc cho mọi tổ chức. Hệ thống thực tế có thể có nhiều cấp duyệt hoặc bước điều chỉnh, nhưng phải đặc tả chúng thành chuyển trạng thái rõ ràng.

### 3.1. Đối tượng trạng thái cần đủ thông tin

```json
{
  "request_id": "payreq-482",
  "tenant_id": "tenant-07",
  "state": "SUBMITTED",
  "version": 12,
  "submission_revision": 3,
  "requester_id": "user-19",
  "amount_minor": 2500000,
  "currency": "VND",
  "beneficiary_ref": "beneficiary-91",
  "approved_revision": null,
  "payment_attempt_ref": null
}
```

Đối tượng này chỉ minh họa những dữ kiện cần xem xét. Bản JSON mà client đang giữ không phải nguồn quyết định cuối cùng. Máy chủ phải đọc hoặc truy cập trạng thái có thẩm quyền theo mô hình nhất quán đã chọn.

Cần định nghĩa riêng ý nghĩa các phiên bản:

- `version`: phiên bản cạnh tranh của đối tượng, thay đổi theo các cập nhật được quy định.
- `submission_revision`: phiên bản nội dung đưa đi duyệt.
- `approved_revision`: phiên bản nội dung đã được phê duyệt.

Không mặc định timestamp cập nhật có thể thay thế version cạnh tranh. Nhiều thay đổi có thể trùng độ phân giải timestamp hoặc đến từ các đồng hồ khác nhau.

### 3.2. Trạng thái quy trình và trạng thái kỹ thuật

Trạng thái nghiệp vụ `PAYOUT_PENDING` không có nghĩa lời gọi mạng đang chạy trên một worker cụ thể. Nó có thể bao gồm trường hợp đã gửi lệnh nhưng chưa biết kết quả cuối.

Trạng thái kỹ thuật của một lần thử, như chưa gửi, đã gửi, chưa rõ kết quả hoặc đã xác nhận, cần được quản lý riêng khi cần. Không chuyển hồ sơ trở lại `APPROVED` chỉ vì client timeout; bên cung cấp có thể đã thực hiện lệnh chi.

## 4. Mô hình đe dọa và bất biến cần bảo vệ

| Tình huống | Rủi ro | Bất biến hoặc hướng yêu cầu |
| --- | --- | --- |
| Client gửi thẳng trạng thái đích | Bỏ qua các bước bắt buộc | Chỉ máy chủ được quyết định chuyển trạng thái qua lệnh được hỗ trợ |
| Người lập gửi lệnh tự duyệt | Vượt kiểm soát phân tách nhiệm vụ | Người lập và người duyệt phải khác nhau theo chính sách |
| Client dùng bản hồ sơ cũ | Duyệt dữ liệu đã thay đổi | Phê duyệt phải ràng buộc đúng phiên bản nội dung |
| Hai yêu cầu duyệt/hủy đến đồng thời | Cả hai tác dụng trái nhau cùng được ghi nhận | Chỉ tổ hợp kết quả hợp lệ được phép commit |
| Hai hồ sơ cùng dùng ngân sách còn lại | Tổng vượt hạn mức dù từng kiểm tra riêng đạt | Kiểm tra và đặt trước ngân sách trong ranh giới nhất quán thích hợp |
| Retry sau mất phản hồi | Tạo hai tác vụ chi | Định danh lệnh và quy tắc chống lặp ở cấp nghiệp vụ |
| Callback cũ hoặc không được xác minh | Đánh dấu đã chi sai đối tượng | Kiểm tra nguồn, liên kết lần thử, dữ kiện và trạng thái hiện tại |
| Tenant sửa ID đối tượng | Truy cập hoặc đổi trạng thái của tenant khác | Tra cứu và ghi luôn bị giới hạn bởi tenant có thẩm quyền |
| Quyền bị thu hồi nhưng cache còn cũ | Thực hiện thao tác sau khi không còn quyền | Định nghĩa tính hiện hành của quyền và điểm quyết định |
| Đường batch hoặc công cụ quản trị ghi trực tiếp | Bỏ qua các guard của API chính | Mọi đường ghi phải đi qua chính sách tương đương |
| Fallback dùng trạng thái client khi kho chính lỗi | Chấp nhận dữ kiện không đáng tin | Không dùng client hoặc cache không đủ bảo đảm để quyết định thao tác nhạy cảm |

Một bất biến tốt có thể kiểm tra trên mọi trạng thái đã commit. Ví dụ:

```text
Nếu state = APPROVED hoặc đang ở các bước chi phía sau:
    approved_revision phải tồn tại và khớp nội dung được phép chi.

Nếu state = PAID:
    phải có kết quả thanh toán hợp lệ, gắn với đúng yêu cầu và lần thử.

Mỗi yêu cầu và phiên bản phê duyệt:
    không được tạo nhiều lệnh chi logic trái chính sách.
```

Bất biến không chỉ kiểm tra khi đi vào một endpoint. Các thao tác chỉnh sửa, khôi phục, nhập dữ liệu và chạy lại sự kiện cũng không được phá chúng.

## 5. Nguồn dữ kiện và ranh giới tin cậy

### 5.1. Dữ kiện nào có thẩm quyền?

| Dữ kiện | Nguồn cần dùng | Điều không nên tin trực tiếp |
| --- | --- | --- |
| Danh tính và tenant | Ngữ cảnh xác thực đã kiểm chứng và quan hệ thành viên hợp lệ | Header tenant hoặc actor do client tùy ý khai báo |
| Trạng thái hồ sơ | Kho trạng thái có thẩm quyền theo mô hình nhất quán | Trường status trong request hoặc trang đã mở từ lâu |
| Vai trò và quyền | Chính sách và dữ liệu quyền đáp ứng yêu cầu về độ mới | Cờ isAdmin hoặc danh sách quyền do client gửi |
| Số tiền, người nhận đã duyệt | Phiên bản nội dung phê duyệt được máy chủ quản lý | Các giá trị thay thế ở lệnh thực hiện chi |
| Hạn mức và phần đã giữ chỗ | Sổ hạn mức có bảo đảm cạnh tranh phù hợp | Tổng do client tính hoặc kết quả đọc cũ |
| Kết quả bên cung cấp | Sự kiện/lời đáp được xác minh và đối soát | Trạng thái thành công trong trình duyệt người dùng |

“Server-side” không đơn giản là dữ liệu nằm ở một máy chủ bất kỳ. Một read replica hoặc cache cập nhật trễ có thể chưa đủ làm căn cứ cho chuyển trạng thái nhạy cảm.

Yêu cầu phải chỉ rõ đường đọc/ghi có thẩm quyền, mức nhất quán và cách xử lý khi không lấy được dữ liệu đủ tin cậy.

### 5.2. Token có chữ ký vẫn có thể lỗi thời

Một token có chữ ký có thể chứng minh nội dung được bên có khóa phát hành và chưa bị sửa. Nó không tự chứng minh trạng thái bên trong vẫn đúng tại lúc dùng.

Ví dụ, token xác nhận cho phiên bản nội dung số 3 không được phép duyệt phiên bản số 4. Nếu dùng challenge hoặc nonce, phải quy định ràng buộc với chủ thể, tenant, đối tượng, thao tác, phiên bản và thời hạn; đồng thời kiểm tra điều kiện hiện tại cần thiết.

Nonce dùng một lần cũng cần được tiêu thụ với bảo đảm cạnh tranh thích hợp. Hai request đồng thời không được cùng coi nonce là chưa sử dụng rồi cùng thực hiện tác dụng phụ.

### 5.3. UI chỉ hỗ trợ trải nghiệm

Máy chủ có thể gửi danh sách thao tác khả dụng để giao diện hiển thị. Danh sách đó là gợi ý theo thời điểm tạo phản hồi, không phải quyền miễn kiểm tra cho lệnh sau này.

Mọi lệnh vẫn phải được đánh giá lại. Nếu trạng thái đã đổi, API cần trả kết quả xung đột hoặc không hợp lệ theo hợp đồng, để client tải lại hoặc xử lý tiếp.

## 6. Đặc tả chuyển trạng thái bằng guard

Một bảng chuyển trạng thái nên có ít nhất trạng thái nguồn, lệnh, chủ thể, điều kiện và tác dụng được phép.

| Trạng thái nguồn | Lệnh | Chủ thể | Guard chính | Kết quả |
| --- | --- | --- | --- | --- |
| DRAFT | Gửi duyệt | Người lập có quyền | Dữ liệu hoàn chỉnh, tenant đúng, nội dung hợp lệ | SUBMITTED; tạo phiên bản nội dung gửi duyệt |
| SUBMITTED | Duyệt | Người duyệt có quyền | Không tự duyệt; đúng revision; trong hạn mức theo chính sách | APPROVED; ghi người duyệt và revision |
| SUBMITTED | Từ chối | Người duyệt có quyền | Đúng revision; lý do theo chính sách | REJECTED; ghi dấu vết quyết định |
| DRAFT hoặc SUBMITTED | Hủy | Người có quyền hủy | Chưa bước vào chi; version hiện tại phù hợp | CANCELLED |
| APPROVED | Chuẩn bị thực hiện chi | Dịch vụ được phân quyền | Phê duyệt còn hợp lệ; đúng snapshot; tài nguyên/hạn mức cần thiết đã được giữ | PAYOUT_PENDING; tạo lệnh chi logic bền vững |
| PAYOUT_PENDING | Xác nhận đã chi | Bộ xử lý kết quả được tin cậy | Khớp lần thử, số tiền, đồng tiền, người nhận và kết quả hợp lệ | PAID; ghi tham chiếu kết quả |

Các trường hợp không có trong bảng không mặc nhiên được phép. Điều này bao gồm chuyển từ `REJECTED` sang `PAID`, sửa số tiền sau duyệt hoặc chuyển trạng thái bằng cách gán trường chung.

Nếu nghiệp vụ cho gửi lại hồ sơ bị từ chối, phải định nghĩa lệnh và revision mới, cùng điều kiện làm mất hiệu lực phê duyệt cũ. Không âm thầm dùng lại phê duyệt của nội dung trước đó.

Một API cập nhật tổng quát không nên cho phép client sửa tùy ý các trường như `state`, `approved_by`, `approved_revision` hoặc `payment_attempt_ref`. Các trường này là kết quả của lệnh nghiệp vụ được kiểm soát.

## 7. Quy trình xử lý một lệnh

Một luồng hợp lý có thể gồm:

1. Kiểm tra kích thước, định dạng và cấu trúc đầu vào.
2. Xác thực chủ thể, xác định tenant có thẩm quyền.
3. Tìm đối tượng trong phạm vi tenant và kiểm tra quyền thao tác.
4. Nếu có idempotency key, xử lý theo chính sách ràng buộc và quyền đọc kết quả hiện tại.
5. Lấy trạng thái, phiên bản nội dung và dữ kiện liên quan từ nguồn có thẩm quyền.
6. Kiểm tra guard: trạng thái nguồn, revision, phân tách nhiệm vụ, hạn mức và điều kiện phê duyệt.
7. Ghi chuyển trạng thái cùng các đặt trước hoặc kết quả liên quan bằng cơ chế nhất quán phù hợp.
8. Ghi ý định tác dụng phụ bền vững nếu cần gọi hệ thống bên ngoài.
9. Ghi audit và trả phản hồi có thể đối chiếu.

Đây là mô hình trách nhiệm, không quy định một thứ tự SQL duy nhất. Trong triển khai, một số bước phải nằm trong transaction hoặc được ràng buộc bằng điều kiện cập nhật nguyên tử; không được để kiểm tra đúng ở bước 6 nhưng mất hiệu lực trước bước 7.

### 7.1. Định nghĩa điểm quyết định

Với thao tác nhạy cảm, cần nói rõ thời điểm quyền và dữ kiện phải đúng. Ví dụ:

> Lệnh duyệt phải được đánh giá bằng quyền có hiệu lực tại điểm quyết định được hệ thống tuần tự hóa. Một quyết định thu hồi quyền có hiệu lực trước điểm đó phải được tôn trọng.

Nếu yêu cầu là thu hồi quyền phải ngăn cả lệnh đang chạy trước commit, cần thiết kế thêm ràng buộc tương ứng. Không thể kiểm tra quyền một lần ở đầu request rồi tự suy ra đã đáp ứng chính sách mạnh hơn.

Khi quyền nằm ở dịch vụ khác hoặc có cache, phải đặc tả độ trễ hiệu lực được chấp nhận, phiên bản chính sách và hành vi khi không xác minh được. Không hứa kiểm tra “ngay lập tức” nếu kiến trúc chỉ cung cấp dữ liệu cập nhật trễ.

### 7.2. Thất bại khi thiếu dữ kiện

Khi không đọc được trạng thái có thẩm quyền, thao tác chi hoặc duyệt không được dựa vào trạng thái client để tiếp tục.

Có thể trả lỗi tạm thời, xếp lệnh vào hàng chờ theo hợp đồng hoặc yêu cầu thử lại. Nếu xếp hàng, điều kiện trạng thái và quyền phải được đánh giá tại thời điểm thực thi theo chính sách; việc tiếp nhận lệnh chưa đồng nghĩa đã phê duyệt nó.

## 8. Kiểm tra nguyên tử và cạnh tranh

### 8.1. Mẫu đọc rồi ghi không có ràng buộc

```text
A đọc: hồ sơ đang SUBMITTED
B đọc: hồ sơ đang SUBMITTED
A kiểm tra và duyệt
B kiểm tra và hủy
A ghi APPROVED
B ghi CANCELLED
```

Nếu cả A và B đều đã phát tác dụng phụ, trạng thái cuối không phản ánh được lịch sử hợp lệ. Chỉ đặt guard ở một câu lệnh if trước cập nhật là chưa đủ.

Đây là vấn đề time-of-check to time-of-use: điều kiện có thể thay đổi giữa lúc kiểm tra và lúc sử dụng.

### 8.2. Cập nhật có điều kiện và optimistic concurrency

Ví dụ SQL khái niệm cho một chuyển trạng thái đơn đối tượng:

```sql
UPDATE payment_requests
SET state = 'APPROVED',
    approved_by = :verified_actor_id,
    approved_revision = submission_revision,
    version = version + 1
WHERE request_id = :request_id
  AND tenant_id = :verified_tenant_id
  AND state = 'SUBMITTED'
  AND version = :expected_version
  AND submission_revision = :expected_revision
  AND requester_id <> :verified_actor_id;
```

Các tham số actor và tenant được lấy từ ngữ cảnh máy chủ đã xác minh. Client có thể gửi phiên bản mà họ kỳ vọng, nhưng phiên bản đó là điều kiện phát hiện cạnh tranh, không phải bằng chứng phân quyền.

Nếu không có hàng nào được cập nhật, ứng dụng không được coi là đã duyệt. Nó cần ánh xạ thành kết quả phù hợp mà không làm lộ đối tượng của tenant khác.

Ví dụ này chỉ minh họa guard trên một bản ghi. Nó chưa tự kiểm tra quyền duyệt, hạn mức nhiều bản ghi, audit hoặc ghi ý định gửi sự kiện. Những yêu cầu đó phải được đưa vào thiết kế đầy đủ.

### 8.3. Khóa và transaction

Một phương án khác là khóa dữ liệu cần thiết trong transaction rồi kiểm tra và cập nhật. Dù dùng cách nào, cần nêu:

- Những dữ kiện nào thuộc cùng ranh giới nhất quán.
- Các guard có còn đúng khi commit không.
- Khi xung đột, hệ thống từ chối hay thử lại.
- Retry có đánh giá lại trạng thái và quyền không.
- Thứ tự khóa, thời hạn chờ và hành vi khi deadlock hoặc timeout.

Không chọn mức cô lập theo tên gọi rồi bỏ qua việc kiểm chứng. Cơ chế phù hợp phụ thuộc dữ liệu và bất biến cần bảo vệ.

### 8.4. Bất biến nhiều bản ghi

Giả sử hạn mức còn 100, hai yêu cầu khác nhau cùng chi 80. Mỗi lệnh có thể đọc hạn mức còn 100 rồi cùng thấy hợp lệ, dù chúng không cập nhật cùng một hồ sơ.

Version trên từng hồ sơ không ngăn được tổng chi vượt hạn mức. Có thể cần đặt trước ngân sách bằng cập nhật có điều kiện trên bản ghi ngân sách chung, khóa phù hợp hoặc cơ chế tuần tự hóa khác.

```text
Trong cùng ranh giới nhất quán phù hợp:
    kiểm tra hồ sơ và quyền
    giữ ngân sách nếu used + reserved + amount <= limit
    chuyển trạng thái hồ sơ
    ghi ý định chi bền vững

Nếu một bước không đạt:
    không commit tổ hợp cập nhật một phần
```

Nếu dữ liệu trải qua nhiều dịch vụ không có transaction chung, phải thiết kế reservation, điều phối và đối soát cụ thể. Không tuyên bố toàn bộ quy trình nguyên tử chỉ vì từng dịch vụ có transaction cục bộ.

## 9. Retry, phát lại và tác dụng phụ

### 9.1. Idempotency cần ràng buộc với ý nghĩa lệnh

Sau timeout, client không biết máy chủ đã xử lý hay chưa. Retry là bình thường; yêu cầu phải nêu khi nào lệnh lặp trả lại kết quả cũ và khi nào bị từ chối.

Một thiết kế idempotency có thể ràng buộc khóa với:

- Tenant và chủ thể hoặc phạm vi danh tính đã được định nghĩa.
- Loại thao tác và đối tượng.
- Dữ kiện lệnh đã chuẩn hóa cần cho ý nghĩa nghiệp vụ.
- Kết quả bền vững, trạng thái xử lý và thời gian giữ khóa.

Nếu cùng khóa được gửi với payload khác, không được âm thầm thực hiện lệnh mới. Nếu trả lại kết quả cũ, vẫn phải kiểm tra quyền truy cập kết quả theo chính sách hiện hành; không dùng khóa đoán được để lấy dữ liệu của người khác.

Hết thời gian giữ idempotency key không có nghĩa được tạo lại một lệnh chi vốn bị cấm lặp. Ràng buộc ở cấp đối tượng, như một lệnh chi logic cho một phiên bản phê duyệt, cần tồn tại theo vòng đời nghiệp vụ.

### 9.2. Chống lặp không chỉ ở API

Hai request có khóa khác nhau vẫn có thể cùng muốn chi một hồ sơ. Cần ràng buộc chuyển trạng thái và định danh nghiệp vụ, thay vì chỉ dựa vào client dùng đúng một khóa.

Có thể dùng ràng buộc duy nhất cho định danh lệnh chi logic theo hồ sơ và phiên bản phê duyệt, kết hợp trạng thái hiện tại. Tuy nhiên, tạo một bản ghi duy nhất trong DB không tự bảo đảm bên thanh toán ngoài chỉ thực hiện một lần.

### 9.3. Ghi ý định trước khi gọi ra ngoài

Một mẫu phổ biến là ghi chuyển trạng thái và bản ghi ý định gửi lệnh trong cùng transaction tại kho dữ liệu có thẩm quyền. Worker sau đó gửi lệnh từ bản ghi này.

```text
Transaction cục bộ:
    APPROVED → PAYOUT_PENDING
    tạo payment_operation với định danh nghiệp vụ duy nhất
    tạo outbox event
    commit

Worker:
    đọc event
    gửi lệnh với định danh được hỗ trợ
    lưu kết quả hoặc trạng thái chưa rõ
    đối soát trước khi quyết định gửi lại khi cần
```

Outbox giúp tránh khoảng trống giữa commit trạng thái và ghi ý định, nhưng thường vẫn phải xử lý giao nhận lặp. Consumer và hệ thống bên ngoài cần cơ chế chống lặp hoặc đối soát phù hợp.

Không hứa “exactly once” chỉ vì dùng queue hoặc outbox. Nếu bên ngoài đã nhận lệnh nhưng phản hồi bị mất, hệ thống cần chính sách cho trạng thái chưa rõ; không tự hạ trạng thái để gửi một lệnh hoàn toàn mới.

### 9.4. Callback và sự kiện đến muộn

Một callback hợp lệ về nguồn vẫn cần được kiểm tra nội dung:

- Có thuộc đúng môi trường, tenant và đối tượng được ánh xạ không?
- Có khớp định danh lần thử hoặc lệnh đã tạo không?
- Số tiền, đồng tiền và người nhận có khớp phạm vi được xác nhận không?
- Kết quả có hợp lệ theo giao thức và đủ chứng cứ không?
- Trạng thái hiện tại có cho phép áp dụng kết quả đó không?
- Đây là sự kiện mới, lặp hay đến sai thứ tự?

Sự kiện cũ không được làm lùi trạng thái đã hoàn tất. Sự kiện không phù hợp nên được ghi nhận và đưa vào đối soát, thay vì ép trạng thái cho “khớp” payload nhận được.

## 10. Hợp đồng lỗi và audit

### 10.1. Lỗi phải có ý nghĩa ổn định

| Tình huống | Hành vi cần đặc tả |
| --- | --- |
| Đầu vào sai cấu trúc | Không thực hiện tác dụng phụ; trả lỗi theo schema |
| Không có quyền hoặc ngoài tenant | Không tiết lộ dữ liệu ngoài phạm vi; dùng chính sách lỗi nhất quán |
| Version hoặc trạng thái không còn phù hợp | Trả kết quả xung đột/không hợp lệ theo hợp đồng; client có thể tải lại |
| Idempotency key trùng nhưng nội dung khác | Không thực hiện lại với nội dung mới |
| Nguồn trạng thái không truy cập được | Không dựa vào dữ kiện client để tiếp tục thao tác nhạy cảm |
| Lệnh ngoài hệ thống chưa rõ kết quả | Biểu diễn đang chờ đối soát; không giả định thất bại đồng nghĩa chưa có tác dụng |

HTTP 403, 404, 409 hoặc các mã khác cần được chọn theo chính sách API cụ thể. Mã lỗi không phải kiểm soát thay thế; điều quan trọng là không có chuyển trạng thái hoặc tác dụng phụ trái phép và không lộ thông tin.

### 10.2. Dấu vết cần đủ để kiểm chứng quyết định

Một audit record có thể gồm:

```json
{
  "event_type": "payment_request.approval_decision",
  "request_id": "payreq-482",
  "tenant_id": "tenant-07",
  "actor_id": "user-37",
  "command_id": "cmd-a73",
  "state_before": "SUBMITTED",
  "state_after": "APPROVED",
  "version_before": 12,
  "version_after": 13,
  "submission_revision": 3,
  "policy_version": "approval-policy-8",
  "outcome": "committed",
  "correlation_id": "trace-912"
}
```

Chỉ ghi `committed` khi kết quả thực sự đã commit. Nếu quyết định không được chấp nhận, cần lý do phân loại phù hợp, không ghi bí mật, token hoặc toàn bộ payload nhạy cảm.

Với thao tác bắt buộc audit bền vững, thiết kế phải bảo đảm không có khoảng trống giữa ghi trạng thái và ghi bằng chứng theo chính sách. Log ứng dụng được ghi trước commit có thể tồn tại dù transaction sau đó rollback; không dùng nó đơn độc làm bằng chứng hồ sơ đã chuyển trạng thái.

## 11. Bộ yêu cầu minh họa có thể nghiệm thu

Bộ yêu cầu sau áp dụng cho quy trình yêu cầu chi đã mô tả. Các ngưỡng và chính sách thực tế phải được chủ sở hữu nghiệp vụ và bảo mật xác nhận.

| ID | Yêu cầu | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| SSV-01 | Mọi lệnh thay đổi quy trình phải lấy tenant, chủ thể, trạng thái và quyền từ nguồn được quy định; client không được gán trực tiếp trường trạng thái hoặc kết quả duyệt. | Ứng dụng | Thử sửa trường hệ thống và ID tenant; không có cập nhật trái phép trên mọi đường ghi được kiểm kê. |
| SSV-02 | Mỗi chuyển trạng thái phải tuân theo bảng nguồn–lệnh–guard được duyệt; chuyển không được liệt kê bị từ chối và không tạo tác dụng phụ. | Nghiệp vụ/ứng dụng | Ma trận chuyển hợp lệ và không hợp lệ; kiểm tra cả API, worker, batch và công cụ quản trị. |
| SSV-03 | Phê duyệt chỉ có hiệu lực cho revision nội dung đã xác định; thay đổi số tiền hoặc người nhận phải theo quy trình làm mất hiệu lực quyết định cũ. | Nghiệp vụ | Phê duyệt revision cũ không áp dụng cho nội dung mới; audit liên kết đúng revision. |
| SSV-04 | Người lập không được tự duyệt trong chính sách ví dụ; quyền duyệt phải hợp lệ tại điểm quyết định và theo quy tắc thu hồi đã đặc tả. | Bảo mật | Test tự duyệt, đổi vai trò, thu hồi quyền và lệnh đang chạy theo thứ tự đã kiểm soát. |
| SSV-05 | Các guard cạnh tranh của đối tượng phải được bảo vệ bằng cập nhật có điều kiện, khóa hoặc cơ chế tương đương; không có tổ hợp commit trái bảng chuyển. | Ứng dụng/dữ liệu | Test song song duyệt–hủy, duyệt–duyệt, sửa–gửi và kiểm tra trạng thái cuối cùng cùng tác dụng phụ. |
| SSV-06 | Hạn mức nhiều hồ sơ phải được kiểm tra và đặt trước theo cơ chế bảo vệ bất biến tổng; thất bại không để lại trạng thái một phần. | Dữ liệu/nghiệp vụ | Hai lệnh cạnh tranh phần ngân sách không đủ không thể cùng vượt tổng; đối soát phần đã giữ và đã dùng. |
| SSV-07 | Retry cùng lệnh phải có ngữ nghĩa idempotent đã công bố; đổi payload với cùng khóa không tạo lệnh mới; trả lại kết quả vẫn tuân thủ quyền đọc. | Ứng dụng | Retry trước/sau timeout, cùng khóa khác nội dung và truy cập kết quả bằng chủ thể khác. |
| SSV-08 | Mỗi hồ sơ và phiên bản phê duyệt chỉ có số lệnh chi logic theo chính sách; retry, queue và callback lặp không được tăng số tác dụng trái phép. | Ứng dụng/tích hợp | Đếm bản ghi nghiệp vụ, lệnh gửi và kết quả đối soát; không chỉ đếm response của API. |
| SSV-09 | Kết quả từ bên ngoài phải được xác minh và gắn với đúng lệnh, dữ kiện và trạng thái hiện hành; sự kiện cũ không làm lùi trạng thái. | Tích hợp | Test giả nguồn, sai tham chiếu, sai dữ kiện, callback lặp và sai thứ tự. |
| SSV-10 | Không lấy được trạng thái hoặc quyền đủ tin cậy thì lệnh nhạy cảm không được tiếp tục bằng dữ kiện client; hàng chờ phải đánh giá lại lúc thực thi. | Bảo mật/ứng dụng | Ngắt kho có thẩm quyền, cung cấp cache cũ và trì hoãn lệnh qua lúc quyền bị thu hồi. |
| SSV-11 | Quyết định và chuyển trạng thái phải truy vết được bằng actor, tenant, lệnh, revision, kết quả commit và phiên bản chính sách khi áp dụng. | Vận hành/ứng dụng | Audit khớp DB và tác dụng phụ; không có bản ghi thành công giả khi rollback. |
| SSV-12 | Thêm trạng thái, lệnh hoặc đường ghi mới phải cập nhật bảng chuyển, bất biến, quyền và test trước khi được đưa vào sử dụng. | Chủ dịch vụ | Kiểm kê endpoint/consumer/batch; review thiết kế và bằng chứng test cho phần thay đổi. |

“Mọi đường ghi” cần một danh mục cụ thể. Không thể chỉ kiểm tra API công khai trong khi một consumer hoặc script vận hành vẫn gán trạng thái trực tiếp.

### Mẫu đặc tả chi tiết

```text
ID: SSV-05
Mục tiêu: ngăn kết quả trái nhau cùng được chấp nhận khi có cạnh tranh
Rủi ro: R-BL-03 — guard đúng lúc đọc nhưng không còn đúng khi ghi
Phạm vi: duyệt, hủy và chuẩn bị chi của payment_request
Nguồn sự thật: kho trạng thái được chỉ định; không dùng payload làm căn cứ
Điều kiện:
  - Trạng thái nguồn và version phải còn phù hợp tại điểm ghi
  - Revision phê duyệt phải khớp nội dung
  - Quyền và bất biến liên quan phải theo chính sách nhất quán đã chọn
Kết quả:
  - Chỉ chuyển trạng thái hợp lệ được commit
  - Lệnh thua cạnh tranh không phát tác dụng phụ trái phép
  - Retry phải đánh giá lại điều kiện, không lặp mù thao tác cũ
Chủ sở hữu: đội ứng dụng, phối hợp đội dữ liệu
Kiểm thử: T-SSV-04, T-SSV-05, T-SSV-06
Bằng chứng: lịch thực thi song song, trạng thái, audit và tác dụng ngoài
```

## 12. Ma trận kiểm thử nghiệm thu

Thử trên môi trường kiểm soát với dữ liệu giả và hệ thống ngoài giả lập hoặc sandbox thích hợp. Các test cạnh tranh phải kiểm soát thứ tự hoặc tạo điểm đồng bộ để chứng minh guard bị tranh chấp, thay vì chỉ gửi nhiều request rồi hy vọng gặp race.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-SSV-01 | Client gửi state, approved_by hoặc tenant khác trong payload và gọi các đường ghi đã kiểm kê. | Không gán được trường hệ thống; không truy cập đối tượng tenant khác; không có tác dụng phụ trái phép. | SSV-01, 02 |
| T-SSV-02 | Gửi từng lệnh từ mọi trạng thái, gồm trạng thái kết thúc và chuyển bị bỏ bước. | Chỉ các chuyển có guard đạt được commit; các trường hợp còn lại theo hợp đồng lỗi. | SSV-02 |
| T-SSV-03 | Lấy revision cũ, thay số tiền/người nhận theo luồng hợp lệ rồi thử duyệt hoặc chi bằng revision cũ. | Không sử dụng phê duyệt cũ cho nội dung mới; audit phản ánh đúng phiên bản. | SSV-03 |
| T-SSV-04 | Cho hai lệnh cùng đọc trước khi ghi: duyệt–hủy, duyệt–duyệt và chuẩn bị chi–hủy. | Chỉ kết quả được bảng chuyển cho phép tồn tại; lệnh không thắng không tạo tác dụng phụ trái phép. | SSV-05, 08 |
| T-SSV-05 | Hai hồ sơ khác nhau cạnh tranh hạn mức chỉ đủ cho một hồ sơ. | Tổng used/reserved không vượt hạn mức; không commit một phần giữa ngân sách và hồ sơ. | SSV-05, 06 |
| T-SSV-06 | Tiêm lỗi giữa cập nhật trạng thái, tạo bản ghi lệnh, ghi outbox và commit. | Các dữ kiện cần nguyên tử không bị tách rời; audit không báo thành công cho phần rollback. | SSV-05, 08, 11 |
| T-SSV-07 | Retry cùng khóa sau mất phản hồi; dùng lại khóa với payload khác; gửi khóa khác cho cùng nghiệp vụ. | Trả kết quả theo hợp đồng; không tạo lệnh chi logic trái chính sách hoặc lộ kết quả cho người không có quyền. | SSV-07, 08 |
| T-SSV-08 | Lặp callback, đổi tham chiếu, dữ kiện hoặc thứ tự sự kiện. | Chỉ kết quả hợp lệ được áp dụng; không làm lùi trạng thái hoặc ghi nhận chi sai đối tượng. | SSV-09 |
| T-SSV-09 | Người lập tự duyệt; thu hồi quyền trước điểm quyết định; cho request chạy qua lúc thay quyền. | Áp dụng đúng phân tách nhiệm vụ và chính sách hiệu lực quyền; kết quả có dấu vết. | SSV-04, 11 |
| T-SSV-10 | Ngắt kho trạng thái/quyền; cung cấp dữ liệu cache cũ hoặc payload client có vẻ hợp lệ. | Lệnh nhạy cảm không tiếp tục bằng nguồn thiếu tin cậy; phản hồi theo chính sách suy giảm. | SSV-10 |
| T-SSV-11 | Đưa lệnh vào hàng chờ rồi thay trạng thái, revision hoặc thu hồi quyền trước lúc worker xử lý. | Worker đánh giá điều kiện tại thời điểm thực thi; tiếp nhận trước đó không biến thành quyền thực hiện. | SSV-02, 03, 04, 10 |
| T-SSV-12 | Bên ngoài nhận lệnh nhưng phản hồi bị mất; worker hoặc consumer khởi động lại. | Giữ trạng thái chưa rõ và đối soát; không tự tạo lệnh mới gây chi lặp; trạng thái và audit nhất quán với kết quả đã xác minh. | SSV-08, 09, 11 |

Nghiệm thu phải kiểm tra dữ liệu đã commit và tác dụng phụ thực tế, không chỉ mã HTTP. Hai response lỗi không chứng minh an toàn nếu hai lệnh chi vẫn được gửi.

Bằng chứng nên ghi phiên bản ứng dụng, schema, chính sách, lịch thực thi, định danh lệnh, trạng thái trước/sau và kết quả đối soát. Trường hợp còn chưa rõ phải được báo là chưa đạt hoặc cần điều tra, không gộp vào kết quả thành công.

## 13. Truy vết yêu cầu trong vòng đời phát triển

Một chuỗi truy vết phù hợp:

```text
Mục tiêu bảo mật
    → Kịch bản lạm dụng hoặc race
    → Bất biến và bảng chuyển trạng thái
    → Yêu cầu SSV-xx
    → Nguồn sự thật, transaction và giao thức tích hợp
    → Test T-SSV-xx
    → Audit, metric và quy trình đối soát
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Không bỏ bước duyệt | Client đặt trạng thái đích | SSV-01, 02 | API lệnh và guard phía máy chủ; T-SSV-01, 02 |
| Duyệt đúng nội dung | Sửa dữ liệu sau khi người duyệt xem | SSV-03, 05 | Revision và snapshot phê duyệt; T-SSV-03, 04 |
| Không vượt hạn mức | Hai hồ sơ dùng cùng ngân sách | SSV-06 | Đặt trước có bảo đảm cạnh tranh; T-SSV-05 |
| Không tạo chi lặp | Retry, queue và timeout | SSV-07, 08, 09 | Định danh nghiệp vụ, outbox và đối soát; T-SSV-07, 12 |
| Giữ hiệu lực thu hồi quyền | Dữ liệu quyền cũ hoặc lệnh chờ | SSV-04, 10 | Điểm quyết định và kiểm tra lúc thực thi; T-SSV-09, 11 |

Khi thêm trạng thái mới, đổi quy tắc sửa nội dung, đổi cache hoặc thay nhà cung cấp bên ngoài, cần đánh giá lại bất biến và test. Cùng một endpoint nhưng nguồn đọc chuyển sang replica trễ có thể làm thay đổi kết luận bảo mật.

Ngoại lệ cần có phạm vi, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Không bỏ một đường ghi khỏi danh mục chỉ vì chưa có cách áp dụng guard giống API chính.

## 14. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Frontend đã khóa nút.” | Client vẫn gửi được lệnh trực tiếp | Kiểm tra guard tại máy chủ trên mọi lệnh |
| “Token có chữ ký nên state đúng.” | Chữ ký không chứng minh trạng thái còn hiện hành | Kiểm tra nguồn trạng thái và binding revision |
| “Đã kiểm tra quyền nên được đổi trạng thái.” | Có quyền chưa đủ điều kiện quy trình | Kiểm tra cả trạng thái, nội dung và bất biến |
| “Đọc status rồi update là đủ.” | Điều kiện có thể đổi giữa đọc và ghi | Guard nguyên tử hoặc khóa/tuần tự hóa phù hợp |
| “Có version từng hồ sơ nên không vượt quota.” | Bất biến tổng có thể trải qua nhiều hồ sơ | Bảo vệ riêng dữ liệu hạn mức hoặc reservation |
| “Timeout là thất bại hoàn toàn.” | Tác dụng bên ngoài có thể đã xảy ra | Trạng thái chưa rõ, định danh ổn định và đối soát |
| “Idempotency key ngăn mọi lệnh lặp.” | Khóa khác vẫn có thể trùng nghiệp vụ | Ràng buộc chống lặp ở cấp đối tượng và phiên bản |
| “Callback ký đúng là cập nhật luôn.” | Có thể sai đối tượng, dữ kiện hoặc thứ tự | Kiểm tra liên kết lệnh và trạng thái hiện tại |
| “Worker nội bộ nên không cần validate.” | Lệnh có thể đã cũ hoặc bị tạo sai | Áp chính sách tương đương ở mọi đường ghi |
| “Log thành công là chứng minh commit.” | Transaction có thể rollback sau khi ghi log | Liên kết audit với kết quả bền vững thực tế |

## 15. Bài tập áp dụng

Một nền tảng cho phép tạo đơn hàng, áp mã giảm giá, thanh toán và yêu cầu hoàn tiền. Client gửi cả tổng tiền và trạng thái đơn. Hai request hoàn tiền có thể đến đồng thời; kết quả thanh toán đến qua webhook.

Hãy thực hiện:

1. Xác định nguồn có thẩm quyền cho giá, tổng tiền, trạng thái, quyền và kết quả thanh toán.
2. Vẽ bảng chuyển trạng thái với chủ thể và guard cho từng lệnh.
3. Nêu ít nhất bốn bất biến, gồm tổng hoàn không vượt số tiền được phép hoàn và không dùng mã giảm giá quá hạn mức.
4. Viết sáu yêu cầu có ID, phạm vi, điểm quyết định, hành vi khi xung đột và bằng chứng nghiệm thu.
5. Thiết kế test cho client sửa tổng tiền, revision cũ, hoàn tiền song song, webhook lặp và mất phản hồi.
6. Giải thích cách xử lý khi đã gửi lệnh ra ngoài nhưng chưa xác định được kết quả.
7. Kiểm kê cả API, worker, batch và công cụ quản trị có thể thay đổi trạng thái.

Đáp án tốt cần nêu rõ điều gì phải đúng tại commit, dữ kiện nào cần nhất quán và cách chứng minh tác dụng phụ không vượt phạm vi được phép.

## 16. Checklist chấp nhận yêu cầu

- Đã chỉ rõ nguồn trạng thái, quyền và dữ kiện nghiệp vụ có thẩm quyền chưa?
- Client có bị giới hạn khỏi việc gán các trường kết quả do máy chủ quản lý không?
- Bảng chuyển có trạng thái nguồn, chủ thể, guard và tác dụng được phép không?
- Phê duyệt hoặc xác nhận có ràng buộc với đúng revision nội dung không?
- Điểm quyết định và hiệu lực thu hồi quyền có rõ ràng không?
- Guard có được giữ đúng khi commit, kể cả cạnh tranh giữa nhiều bản ghi không?
- Retry, idempotency và chống lặp nghiệp vụ có được đặc tả riêng không?
- Timeout hoặc kết quả chưa rõ có tránh tạo lại tác dụng phụ mù không?
- Callback có được xác minh cả nguồn, nội dung, liên kết và thứ tự không?
- Lệnh chờ, worker, batch và công cụ quản trị có cùng yêu cầu kiểm chứng không?
- Audit có phản ánh đúng quyết định, revision và kết quả commit không?
- Test có kiểm tra dữ liệu và tác dụng phụ thực tế thay vì chỉ response không?

Kiểm chứng trạng thái phía máy chủ có giá trị bảo mật khi mỗi lệnh được ràng buộc với trạng thái và dữ kiện còn hiệu lực, các bất biến được bảo vệ trước cạnh tranh, và mọi tác dụng phụ đều có thể đối soát với quyết định đã được phép.
