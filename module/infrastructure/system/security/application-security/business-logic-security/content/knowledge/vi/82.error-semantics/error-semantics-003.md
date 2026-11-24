# Conflict response — Phản hồi xung đột trong nghiệp vụ

## 1. Phản hồi conflict phải giải thích điều gì?

**Conflict response** là phản hồi cho biết thao tác được yêu cầu không thể được áp dụng theo điều kiện hiện tại của tài nguyên hoặc lệnh nghiệp vụ. Ví dụ: một hoàn tiền đã được người khác duyệt, phiên bản đơn hàng đã thay đổi hoặc một idempotency key được dùng lại với nội dung khác.

Trong bảo mật logic nghiệp vụ, mục tiêu không chỉ là chọn một mã HTTP. Phản hồi cần giúp client hiểu:

- Điều kiện nào không còn phù hợp với ý định gửi lên?
- Hệ thống có chắc thao tác chưa tạo tác động hay không?
- Client có thể đọc lại kết quả cũ, cần tải lại dữ liệu hay phải đợi xử lý?
- Việc gửi lại có giữ nguyên cùng một lệnh hay đang tạo một lệnh mới?
- Thông tin nào được phép tiết lộ cho người đang gọi?

Một phản hồi không rõ nghĩa có thể khiến client retry vô hạn, tự cập nhật phiên bản rồi ghi đè quyết định mới, hoặc đổi idempotency key để tạo tác động lần thứ hai.

Phản hồi conflict phải đi cùng kiểm tra quyền theo đối tượng, state machine, transaction và idempotency. Trả đúng mã lỗi không làm một thao tác thiếu kiểm soát trở nên an toàn.

## 2. Tình huống xuyên suốt: hai người cùng phê duyệt hoàn tiền

Giả sử hoàn tiền R-420 có dữ liệu:

~~~json
{
  "id": "R-420",
  "tenantId": "t-a",
  "state": "PENDING_APPROVAL",
  "amountMinor": 750000,
  "currency": "VND",
  "requestedBy": "u-17",
  "version": 8
}
~~~

Các invariant của ví dụ:

1. Chỉ hoàn tiền đang PENDING_APPROVAL mới được phê duyệt.
2. Người thao tác phải có quyền trong tenant và trên đối tượng.
3. Người tạo không được tự phê duyệt.
4. Quyết định phải dựa trên dữ liệu và phiên bản mà người phê duyệt đã xem.
5. Mỗi chuyển trạng thái chỉ có tác động hợp lệ theo mô hình nghiệp vụ.

Hai người có thẩm quyền độc lập cùng mở màn hình ở phiên bản 8. Người A phê duyệt trước, làm đối tượng chuyển sang APPROVED và phiên bản 9. Người B sau đó gửi lệnh dựa trên phiên bản 8.

Nếu máy chủ chỉ đọc trạng thái rồi ghi không có điều kiện nguyên tử, cả hai request có thể cùng nghĩ mình được phép phê duyệt. Nếu máy chủ luôn trả thành công khi thấy đối tượng đã APPROVED, lịch sử có thể ghi nhận sai ai thực sự tạo quyết định.

Phản hồi dành cho B phải phản ánh rằng lệnh của B không được áp dụng theo điều kiện ban đầu. Client cần tải lại dữ liệu và hiểu kết quả hiện có, thay vì tự tăng expectedVersion rồi tiếp tục duyệt.

~~~mermaid
sequenceDiagram
    participant A as Người A
    participant B as Người B
    participant S as API
    participant D as Database
    A->>S: Đọc R-420
    S-->>A: PENDING_APPROVAL, version 8
    B->>S: Đọc R-420
    S-->>B: PENDING_APPROVAL, version 8
    A->>S: Phê duyệt với expectedVersion 8
    S->>D: Cập nhật có điều kiện + outbox cùng transaction
    D-->>S: Commit, version 9
    S-->>A: Kết quả thành công
    B->>S: Phê duyệt với expectedVersion 8
    S->>D: Thử cập nhật theo điều kiện version 8
    D-->>S: Không có bản ghi phù hợp
    S-->>B: Conflict, cần tải lại và xem xét
~~~

Sơ đồ giả định cả A và B đã vượt qua kiểm tra quyền phù hợp. Không dùng việc phát hiện xung đột để tiết lộ trạng thái cho người vốn không được phép biết đối tượng tồn tại.

## 3. Phân loại trước khi chọn mã phản hồi

Không phải mọi lần từ chối đều là conflict.

| Nhóm tình huống | Ví dụ | Cách phản hồi theo hợp đồng API |
|---|---|---|
| Dữ liệu yêu cầu không hợp lệ | expectedVersion không đúng kiểu hoặc thiếu trường bắt buộc | Lỗi validation, thường dùng 400 theo thiết kế |
| Chưa được xác thực | Thiếu thông tin xác thực hợp lệ | 401 khi phù hợp với cơ chế xác thực |
| Không có quyền | Không được duyệt đối tượng hoặc tự duyệt trái chính sách | 403, hoặc phản hồi che giấu tài nguyên theo chính sách |
| Không tìm thấy hoặc cần che giấu sự tồn tại | ID không có trong phạm vi được phép nhìn thấy | 404 theo hợp đồng quyền và tài nguyên |
| Xung đột với trạng thái hiện tại | Đối tượng đã hủy hoặc phiên bản trong command đã cũ | 409 cho loại xung đột được API định nghĩa |
| Điều kiện HTTP thất bại | If-Match không thỏa khi điều kiện được áp dụng | 412 cho thất bại điều kiện tương ứng |
| Hệ thống không thực thi được | Database không truy cập được, lỗi lưu outbox | Lỗi máy chủ hoặc hạ tầng phù hợp, không tự đổi thành 409 |
| Chưa biết kết quả cuối cùng | Timeout sau khi có thể đã phát lệnh ra ngoài | Thể hiện trạng thái chưa xác định và cách tra cứu, không khẳng định chưa có tác động |

Bảng là cách phân loại phục vụ thiết kế. Một API vẫn cần quy định chi tiết cho từng endpoint, bao gồm dữ liệu phản hồi và khả năng retry.

### 3.1. 409 không đồng nghĩa “thử lại ngay”

Xung đột do phiên bản cũ có thể được giải quyết bằng tải lại và xem xét. Xung đột do đối tượng đã hủy có thể khiến hành động không còn hợp lệ. Cùng key nhưng payload khác đòi hỏi sửa cách sử dụng idempotency.

Một vòng retry không thay đổi gì chỉ lặp lại cùng xung đột. Một vòng retry tự thay phiên bản có thể làm mất điều kiện bảo vệ ý định của người dùng.

### 3.2. 412 gắn với điều kiện của request

Nếu API dùng If-Match, cần giữ ngữ nghĩa của cơ chế điều kiện thay vì đổi mọi thất bại của nó thành một mã conflict chung.

Nếu API dùng expectedVersion trong body, đó là hợp đồng nghiệp vụ do ứng dụng thiết kế. API có thể dùng 409 cho phiên bản không còn phù hợp. Không nên lúc dùng 409, lúc dùng 412 cho cùng một trường body mà không có quy tắc rõ ràng.

Một số trường hợp nhận lại thao tác đã hoàn tất có thể được xử lý bằng kết quả thành công theo hợp đồng idempotency hoặc điều kiện tương ứng. Client không nên chỉ nhìn mã lỗi để suy ra rằng request trước chắc chắn chưa chạy.

### 3.3. Lỗi quyền phải được giữ đúng bản chất

Người tạo tự phê duyệt không đơn giản là “dữ liệu đang có version mới”. Đó là vi phạm điều kiện về tác nhân trong chính sách.

Không trả expectedVersion hoặc state hiện tại cho một người không có quyền chỉ vì hệ thống muốn giải thích conflict thật chi tiết. Mức chi tiết của lỗi bị giới hạn bởi quyền nhìn thấy tài nguyên.

## 4. Các dạng conflict thường gặp

### 4.1. Xung đột phiên bản

Client đưa ra quyết định trên phiên bản 8 nhưng tài nguyên hiện ở phiên bản 9.

Cơ chế kiểm tra phiên bản bảo vệ khỏi lost update và khỏi việc vô tình áp dụng một quyết định lên dữ liệu khác với dữ liệu đã xem. Trong nghiệp vụ nhạy cảm, thay đổi số tiền có thể làm cùng một nút “Duyệt” mang ý nghĩa khác.

Phản hồi nên hướng client tải lại và xem xét phần thay đổi. Không hướng dẫn client chỉ thay 8 thành 9 rồi gửi lại tự động.

### 4.2. Xung đột trạng thái

Phiên bản có thể đúng nhưng hành động không hợp lệ ở trạng thái hiện tại. Ví dụ: yêu cầu phê duyệt một hoàn tiền đã CANCELLED.

Cần mô hình hóa rõ chuyển trạng thái được phép:

~~~text
PENDING_APPROVAL -> APPROVED
PENDING_APPROVAL -> CANCELLED

APPROVED -> PAID
~~~

Nếu mô hình không cho CANCELLED chuyển sang APPROVED, retry không thể tự sửa điều kiện đó. Nếu muốn khôi phục hoặc tạo yêu cầu mới, cần một hành động nghiệp vụ riêng có quyền và invariant riêng.

### 4.3. Xung đột với ràng buộc nghiệp vụ duy nhất

Ví dụ: một mã tham chiếu được phép tạo duy nhất một lệnh thanh toán trong phạm vi tenant.

Khi hai request cạnh tranh, ràng buộc dữ liệu có thể chặn request đến sau. Máy chủ cần biết ràng buộc nào đã bị vi phạm và nó có ý nghĩa gì trong nghiệp vụ.

Không ánh xạ mọi lỗi unique constraint thành 409 giống nhau. Một ràng buộc nội bộ bị vi phạm do lỗi lập trình có thể là lỗi máy chủ. Cũng không đưa tên bảng, tên constraint hoặc câu SQL vào phản hồi công khai.

### 4.4. Xung đột idempotency

Cùng một key được dùng trong cùng phạm vi nhưng payload khác. Đây không phải replay hợp lệ của cùng một lệnh.

Phản hồi cần nói rõ key đã gắn với nội dung khác theo hợp đồng, nhưng không trả payload hoặc kết quả nhạy cảm của một chủ thể khác. Việc chọn phạm vi key phải xét tenant, hành động và danh tính phù hợp.

### 4.5. Lệnh đang được xử lý

Một lệnh có thể đã được nhận nhưng chưa có kết quả cuối cùng. API có thể dùng một giao thức xử lý bất đồng bộ với operation reference, hoặc một phản hồi in-progress được định nghĩa riêng.

Nếu sử dụng 409 cho trường hợp đang xử lý, client cần phân biệt mã nghiệp vụ IN_PROGRESS với mã VERSION_CONFLICT. Không thể suy ra cách retry chỉ từ số 409.

Chỉ trả “đã nhận và đang xử lý” khi hệ thống có căn cứ bền vững cho khẳng định đó. Timeout hoặc mất kết nối không tự chứng minh một lệnh đã được nhận.

## 5. Bảo vệ ý định bằng phiên bản và điều kiện

### 5.1. Phiên bản phải bao phủ thay đổi có ý nghĩa

Nếu số tiền đổi mà version không tăng, client có thể phê duyệt với cùng version dù nội dung đã khác.

Cần định nghĩa các thay đổi nào làm phiên bản tăng. Với thao tác phê duyệt, những dữ kiện ảnh hưởng quyết định như số tiền, chủ thể nhận hoặc trạng thái phải được bảo vệ bằng cơ chế nhất quán phù hợp.

Một version duy nhất không tự bao phủ chính sách quyền ở hệ thống khác. Nếu điều kiện cấp quyền thay đổi độc lập, cần mô hình kiểm tra và thu hồi phù hợp; không tuyên bố khóa optimistic trên một dòng giải quyết được mọi loại thay đổi.

### 5.2. If-Match và ETag

Một giao thức minh họa:

~~~http
GET /refunds/R-420

HTTP/1.1 200 OK
ETag: "refund-R-420-v8"
Content-Type: application/json

{
  "id": "R-420",
  "state": "PENDING_APPROVAL",
  "amountMinor": 750000,
  "currency": "VND"
}
~~~

Client gửi điều kiện với hành động thay đổi:

~~~http
POST /refunds/R-420
If-Match: "refund-R-420-v8"
Content-Type: application/json

{
  "action": "APPROVE",
  "reason": "Approved after review"
}
~~~

API cần ánh xạ validator vào phiên bản phù hợp của tài nguyên và thực thi điều kiện nhất quán với cập nhật. Không chỉ kiểm tra header trong controller rồi ghi dữ liệu không có điều kiện cạnh tranh.

If-Match dùng so sánh mạnh; một weak ETag không thích hợp để làm validator cho phép so sánh đó. Trong ví dụ, ETag không có tiền tố W/.

ETag không phải token cấp quyền. Người biết hoặc đoán được ETag vẫn phải vượt kiểm tra xác thực, quyền theo đối tượng và invariant.

Nếu endpoint dùng điều kiện trên một representation khác với đối tượng nghiệp vụ bị thay đổi, cần định nghĩa rõ quan hệ giữa chúng. Không dùng validator của danh sách để bảo vệ tùy ý một phần tử mà không có hợp đồng tương ứng.

### 5.3. expectedVersion trong command

Một thiết kế khác có thể gửi:

~~~json
{
  "expectedVersion": 8,
  "reason": "Approved after review"
}
~~~

Máy chủ kiểm tra expectedVersion như một điều kiện của lệnh. Version hiện tại phải lấy từ nguồn có thẩm quyền, không từ một header hoặc trường khác mà client cũng tự khai.

Nếu API hỗ trợ đồng thời If-Match và expectedVersion, cần quy định quan hệ và cách xử lý khi chúng mâu thuẫn. Việc có hai cơ chế mà mỗi tầng tin một giá trị khác nhau có thể tạo hành vi khó đoán.

## 6. Cập nhật nguyên tử để conflict phản ánh thực tế

Phản hồi conflict chỉ đáng tin khi kiểm soát cạnh tranh thực sự bảo vệ cập nhật.

Với ví dụ thao tác trực tiếp, không có đại diện, một câu SQL minh họa có thể là:

~~~sql
UPDATE refund
SET state = 'APPROVED',
    approved_by = :verified_actor_id,
    version = version + 1
WHERE id = :refund_id
  AND tenant_id = :verified_tenant_id
  AND state = 'PENDING_APPROVAL'
  AND version = :expected_version
  AND requested_by <> :verified_actor_id;
~~~

Điều kiện của ví dụ:

- Actor và tenant đã được xác minh ở phía máy chủ.
- Quyền phê duyệt trên đối tượng đã được kiểm tra.
- requested_by là dữ liệu có thẩm quyền.
- Các cập nhật ảnh hưởng quyết định sử dụng cơ chế phiên bản nhất quán.
- Trường hợp đại diện có policy riêng xét người thao tác thật, không chỉ so sánh một effective subject.
- Kiểm soát lỗi và transaction bao quanh toàn bộ thao tác.

Nếu cập nhật một dòng, transaction có thể tiếp tục ghi sự kiện hoặc outbox rồi commit. Nếu không có dòng phù hợp, không được tạo tác động phê duyệt.

### 6.1. Không có dòng phù hợp chưa cho biết chính xác nguyên nhân

Kết quả bằng 0 có thể do version đổi, state đổi, đối tượng không còn ở phạm vi hoặc một điều kiện khác thất bại.

Không bịa nguyên nhân VERSION_CONFLICT chỉ từ số dòng bằng 0. Có thể dùng mã tổng quát RESOURCE_CHANGED khi phù hợp, hoặc đọc lại có kiểm soát để phân loại chính xác hơn sau khi áp dụng lại quyền nhìn thấy.

Phản hồi chi tiết không được dựa trên dữ liệu trái quyền hoặc một lần đọc đã lỗi thời mà lại trình bày như trạng thái chắc chắn hiện tại.

### 6.2. Ghi dữ liệu và outbox trong cùng transaction

Nếu cập nhật hoàn tiền thành công nhưng ghi outbox thất bại, transaction cần tuân theo hợp đồng nhất quán của hệ thống. Trong thiết kế cùng transaction, lỗi này làm toàn bộ thay đổi rollback.

Đây là lỗi thực thi, không phải bằng chứng có một conflict nghiệp vụ. Không bắt mọi exception rồi trả 409 để che lỗi hạ tầng.

Ở ứng dụng Java dùng ORM, lỗi cạnh tranh có thể chỉ xuất hiện lúc flush hoặc commit. Lớp ánh xạ phản hồi phải nằm ở vị trí quan sát được kết quả transaction thực tế. Không bắt lỗi rồi tiếp tục dùng một transaction đã không còn khả năng commit.

### 6.3. Retry transaction không được đổi ý định

Một số lỗi cạnh tranh ở tầng lưu trữ có thể được retry nội bộ theo chính sách. Nhưng retry phải giữ điều kiện và invariant ban đầu.

Nếu request yêu cầu phê duyệt version 8, việc tự đọc version 9 rồi phê duyệt là thay đổi điều kiện lệnh, không phải chỉ thử lại cùng transaction.

Quyết định nào có thể được đánh giá lại tự động, quyết định nào cần người dùng xác nhận lại phải thuộc hợp đồng nghiệp vụ.

## 7. Thiết kế nội dung phản hồi

Một envelope ứng dụng minh họa:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Cache-Control: no-store

{
  "code": "REFUND_CHANGED",
  "message": "Yêu cầu hoàn tiền đã thay đổi. Hãy tải lại và xem xét trước khi gửi lệnh mới.",
  "requestId": "req-391",
  "commandReference": "cmd-882",
  "resultStatus": "NOT_APPLIED",
  "recovery": {
    "strategy": "REFRESH_REVIEW_RESUBMIT"
  }
}
~~~

Đây là schema do ứng dụng tự định nghĩa. Nó không mặc nhiên là một định dạng lỗi chuẩn chỉ vì có các trường code và message.

### 7.1. Mã máy đọc phải ổn định

Client nên phân nhánh theo code hoặc trường phục hồi có hợp đồng, không phân tích chuỗi message tiếng Việt.

Có thể dùng tập mã hữu hạn:

~~~text
REFUND_CHANGED
REFUND_STATE_CONFLICT
IDEMPOTENCY_PAYLOAD_CONFLICT
COMMAND_IN_PROGRESS
~~~

Mã cần cụ thể đủ cho hành vi client nhưng không tiết lộ nội bộ. Thông điệp có thể được dịch hoặc chỉnh cách diễn đạt mà không làm đổi ý nghĩa code.

Không tạo một code mới chứa ID đối tượng, tên exception hoặc nội dung do client cung cấp.

### 7.2. Trạng thái kết quả phải có bằng chứng

NOT_APPLIED chỉ phù hợp khi hệ thống biết lệnh này chưa tạo tác động trong phạm vi được khẳng định. Ví dụ: điều kiện cập nhật không khớp và transaction không có thay đổi nghiệp vụ đã commit.

Nếu đã gọi hệ thống thanh toán rồi timeout, không được dùng NOT_APPLIED chỉ vì API nội bộ chưa có response. Cần trạng thái chưa xác định hoặc quy trình tra cứu, đối chiếu theo thiết kế.

Nếu nghiệp vụ nhiều bước có thể đã tạo tác động một phần, một phản hồi conflict đơn giản không nên ngầm hứa rollback toàn bộ các hệ thống.

### 7.3. Chỉ trả chi tiết người gọi được phép biết

Có thể trả currentVersion hoặc trạng thái hiện tại nếu người gọi có quyền đọc và API thật sự cần thông tin đó. Tuy nhiên, dữ liệu này không phải giấy phép cho client tự resubmit.

Không trả:

- Dữ liệu của tenant khác.
- Danh tính người duyệt khác nếu người gọi không có quyền xem.
- Số dư, hạn mức hoặc thông tin grant ngoài phạm vi.
- Tên bảng, câu SQL, stack trace hay tên constraint nội bộ.
- Nội dung request gốc của một idempotency key thuộc chủ thể khác.

Request ID giúp điều tra nhưng không phải token truy cập. Máy chủ cần tạo hoặc kiểm soát định dạng giá trị chuyển tiếp, tránh phản chiếu dữ liệu tùy ý vào log hoặc giao diện.

### 7.4. Chính sách cache phải phù hợp dữ liệu

Phản hồi xung đột có thể chứa thông tin nhạy cảm theo người dùng và tài nguyên. Ví dụ dùng Cache-Control: no-store để tránh lưu phản hồi đó qua cơ chế cache thông thường.

Nếu hệ thống chọn chính sách khác, phải xét cache dùng chung, phạm vi xác thực và vòng đời thông tin. Không để phản hồi của một người được phục vụ cho người khác chỉ vì URL giống nhau.

## 8. Idempotency: replay hợp lệ không phải conflict mới

### 8.1. Cùng key, cùng nội dung, lệnh đã hoàn tất

Nếu cùng một lệnh hợp lệ được gửi lại sau timeout, API có thể trả lại kết quả đã lưu theo hợp đồng idempotency. Đây không phải một lần phê duyệt mới.

Trước khi trả kết quả, vẫn phải kiểm tra người gọi có quyền nhận kết quả trong phạm vi tương ứng. Biết key không thay thế xác thực và quyền.

Không sửa actor của quyết định gốc thành người gửi lại gần nhất. Một lần truy vấn hoặc replay có thể có audit riêng, nhưng tác động cũ giữ nguyên nguồn gốc.

### 8.2. Cùng key, nội dung khác

Ví dụ request đầu dùng expectedVersion 8, request sau dùng expectedVersion 9 với cùng key.

Nếu fingerprint của API bao gồm expectedVersion, đây là payload khác và cần được xử lý như xung đột idempotency. Fingerprint phải được xây dựng từ dữ kiện có ý nghĩa theo hợp đồng; không so chuỗi JSON thô rồi để thứ tự field tạo kết quả ngẫu nhiên.

Không cho client đổi nội dung một lệnh đang xử lý bằng cách gửi lại cùng key. Cũng không trả dữ liệu của lệnh gốc vượt quyền để giải thích conflict.

### 8.3. Lệnh mới sau khi xem xét lại

Giả sử API lưu kết quả conflict như kết quả cuối của một command. Sau khi người dùng tải lại, hiểu thay đổi và xác nhận một ý định mới, client có thể tạo command và key mới theo hợp đồng.

Không đổi key chỉ vì request cũ bị timeout. Khi chưa biết kết quả, cần dùng key cũ hoặc operation reference để tra cứu, tránh tạo tác động thứ hai.

Có thể phân biệt:

| Trạng thái đã biết | Hành vi client |
|---|---|
| Lệnh cũ hoàn tất thành công | Dùng kết quả cũ, không tạo lại tác động |
| Lệnh cũ bị từ chối cuối cùng và chưa áp dụng | Có thể chuẩn bị lệnh mới sau khi sửa điều kiện và được xác nhận phù hợp |
| Lệnh cũ đang xử lý | Theo dõi cùng lệnh, không tạo key mới chỉ để vượt in-progress |
| Kết quả lệnh cũ chưa xác định | Tra cứu hoặc đối chiếu trước khi cân nhắc một ý định mới |
| Cùng key nhưng nội dung khác | Sửa cách sử dụng key; không ghi đè nội dung đã gắn |

### 8.4. Trạng thái đã đạt không chứng minh cùng lệnh đã thành công

R-420 đã APPROVED có thể do A thực hiện. Điều đó không chứng minh lệnh của B đã thành công.

Với một hành động phê duyệt có actor và bằng chứng riêng, không được trả “B đã phê duyệt” chỉ vì trạng thái cuối giống mong muốn. Nếu API định nghĩa một thao tác chỉ bảo đảm trạng thái đích, cần quy định rõ ngữ nghĩa đó và vẫn giữ chính xác nguồn gốc tác động.

## 9. Chọn chiến lược phục hồi thay vì một cờ retryable

Một boolean retryable thường không đủ. Retry sau khi tải lại khác với retry nguyên request; polling khác với tạo lệnh mới.

| Chiến lược | Khi phù hợp | Điều client không nên tự làm |
|---|---|---|
| REFRESH_REVIEW_RESUBMIT | Phiên bản hoặc dữ kiện quyết định đã thay đổi | Tự thay version rồi gửi lại quyết định nhạy cảm |
| USE_EXISTING_RESULT | Đã có kết quả cho cùng lệnh và người gọi có quyền đọc | Tạo thêm tác động hoặc ghi đè actor gốc |
| POLL_EXISTING_COMMAND | Lệnh đã được nhận bền vững và còn xử lý | Tạo nhiều command mới cho cùng ý định |
| FIX_REQUEST | Nội dung hoặc cách dùng key không đúng hợp đồng | Giữ nguyên request sai rồi retry vô hạn |
| ACTION_NO_LONGER_AVAILABLE | State machine không còn cho hành động | Tìm endpoint khác để bỏ qua chuyển trạng thái |
| RESOLVE_OUTCOME_FIRST | Chưa biết tác động của lệnh trước | Suy ra không thành công rồi thực hiện lại bằng key khác |

Nếu có hướng dẫn thời gian chờ, cần tách nó khỏi điều kiện an toàn. Chờ vài giây không tự làm một thanh toán chưa biết kết quả trở thành an toàn để gửi lại bằng key mới.

### 9.1. Giao diện cần giữ ngữ cảnh quyết định

Sau conflict do dữ liệu thay đổi, giao diện nên hiển thị dữ liệu mới mà người dùng có quyền xem và yêu cầu xem xét lại khi hành động nhạy cảm.

Không chỉ hiển thị “Có lỗi, thử lại” rồi tự gửi lại request ở nền. Với sửa giá hoặc hoàn tiền, có thể cần cho người dùng thấy số tiền, đối tượng hoặc trạng thái đã thay đổi trước khi xác nhận lại.

### 9.2. Tích hợp máy-máy cần hợp đồng tương tự

Client tự động cũng cần phân biệt lỗi có thể retry nguyên lệnh với xung đột đòi hỏi một quyết định mới.

Nếu một dịch vụ có quyền ra quyết định tự động, việc đánh giá lại phải theo policy và được ghi nhận như thiết kế. Không dùng vòng retry chung để vô tình cấp cho client quyền đổi điều kiện nghiệp vụ.

## 10. Quyền theo đối tượng và giới hạn tiết lộ

Một trình tự khái niệm có thể là:

~~~text
Kiểm tra cấu trúc request
    -> xác thực
    -> xác định phạm vi tenant đã xác minh
    -> tìm đối tượng trong phạm vi được phép
    -> kiểm tra quyền và điều kiện tác nhân
    -> đánh giá điều kiện phiên bản và state machine
    -> cập nhật có kiểm soát cạnh tranh
    -> xác định kết quả transaction
    -> ánh xạ phản hồi
~~~

Trình tự thực tế có thể khác do framework hoặc kiến trúc, nhưng phải bảo đảm điều kiện HTTP và chi tiết conflict không trở thành đường vòng qua quyền.

Ví dụ, một người không được đọc R-420 không nên nhận “R-420 đang APPROVED, version 9, do manager-42 duyệt” chỉ vì họ gửi version 8.

Nếu hệ thống dùng 404 để che giấu tài nguyên trái quyền, cần áp dụng nhất quán ở các nhánh xem, cập nhật và xử lý conflict. Không cần hứa thời gian phản hồi bằng nhau tuyệt đối, nhưng cũng không nên tạo khác biệt thông báo rõ ràng giúp dò sự tồn tại.

Với quan hệ đại diện, actor thực tế và chủ thể hiệu lực phải được kiểm tra theo chính sách. Đổi effective subject không được biến tự phê duyệt thành một xung đột có thể “khắc phục” bằng thử lại dưới danh tính khác.

## 11. Conflict, rollback và tác động ngoài transaction

### 11.1. Phân biệt lỗi trước commit và lỗi sau commit

Có ba thời điểm khác nhau:

1. **Chưa tạo tác động:** điều kiện bị chặn, không có thay đổi nghiệp vụ đã commit.
2. **Đã commit:** dữ liệu đã thay đổi, nhưng client có thể chưa nhận response.
3. **Chưa xác định:** ranh giới hệ thống hoặc lỗi kết nối làm chưa biết tác động cuối cùng.

Nếu serialization của response lỗi sau commit, không thể quay lại nói lệnh chưa áp dụng. Nếu client bị timeout, nó không biết đang ở trường hợp nào chỉ từ việc không nhận response.

Đây là lý do cần command reference, idempotency và đường tra cứu kết quả.

### 11.2. Không thực hiện tác động không đảo ngược trước khi biết điều kiện

Nếu ứng dụng gửi tiền rồi mới kiểm tra version, trả 409 sau đó không hoàn tác tiền đã gửi.

Cần thiết kế thứ tự và state machine để điều kiện được bảo vệ trước khi phát lệnh có tác động. Với hệ thống ngoài transaction database, thường phải có ý định bền vững, giao nhận có kiểm soát, idempotency tại ranh giới thích hợp và đối chiếu kết quả.

Không tuyên bố một transaction cục bộ có thể rollback toàn bộ hành động ở dịch vụ ngoài nếu kiến trúc không cung cấp khả năng đó.

### 11.3. Audit phải phản ánh kết quả thật

Một bản ghi có thể ghi nhận:

- Ai gửi lệnh và phạm vi đã xác minh.
- Version được yêu cầu và dữ kiện quan sát được phép ghi.
- Mã lý do nội bộ.
- Kết quả transaction hoặc trạng thái chưa xác định.
- Liên kết command, request và tác động gốc khi replay.

Bản ghi từ chối cần đường lưu phù hợp để không mất theo rollback. Sự kiện khẳng định phê duyệt thành công phải nhất quán với commit, chẳng hạn qua outbox cùng transaction.

Audit nội bộ có thể chi tiết hơn phản hồi công khai, nhưng vẫn phải có quyền đọc và giới hạn dữ liệu rõ ràng.

## 12. Quan sát conflict mà không nhầm với hành vi tấn công

Conflict có thể đến từ:

- Hai người thao tác hợp lệ cùng lúc.
- Client dùng dữ liệu cũ.
- Retry do timeout.
- Một lỗi tích hợp dùng sai idempotency key.
- Cố tình vượt state machine hoặc dò đối tượng.

Vì vậy, số lượng 409 tăng chưa đủ chứng minh có lạm dụng. Cần phân loại mã nghiệp vụ và đối chiếu với operation, retry, độ trễ và thay đổi triển khai.

Metric tổng hợp có thể dùng các nhãn hữu hạn như:

~~~text
operation = refund.approve
conflict_kind = VERSION | STATE | IDEMPOTENCY | IN_PROGRESS | OTHER
result_status = NOT_APPLIED | PENDING | UNKNOWN
~~~

Chỉ dùng các tổ hợp có ý nghĩa theo hợp đồng. Không gắn user ID, refund ID, request ID hoặc key nguyên bản vào nhãn metric. Các định danh đó thuộc sự kiện chi tiết với quyền truy vấn phù hợp.

Đồng thời theo dõi lỗi hạ tầng riêng. Nếu mọi exception đều bị đổi thành 409, dashboard có thể trông như nhiều xung đột hợp lệ trong khi database thực sự đang lỗi.

Cần quan sát cả mức độ phục hồi: client có tải lại đúng không, có retry vô hạn không, có tạo key mới liên tục không và có tác động trùng sau timeout không.

## 13. Tình huống kiểm thử khi triển khai

Các tình huống dưới đây dùng để thiết kế kiểm thử cho một triển khai thực tế; ví dụ trong bài chưa phải mã đã được chạy.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Hai lệnh khác nhau cùng expectedVersion | Không tạo hai chuyển trạng thái trái invariant; phản hồi đúng kết quả từng lệnh |
| Version cũ trong body | Phản hồi theo hợp đồng conflict, không tự nâng version |
| If-Match không thỏa khi được áp dụng | Phản hồi điều kiện phù hợp, không ghi dữ liệu |
| expectedVersion sai kiểu | Lỗi validation, không trình bày như cạnh tranh phiên bản |
| Tài nguyên đã CANCELLED | Không phê duyệt qua retry hoặc endpoint thay thế trái state machine |
| Người tạo tự phê duyệt | Bị chặn theo chính sách tác nhân, không nhận thông tin vượt quyền |
| Người ngoài tenant gửi ID hợp lệ | Không lộ trạng thái, version hoặc actor của đối tượng |
| Cùng key, cùng payload, kết quả đã có | Replay kết quả theo quyền, không tạo tác động mới |
| Cùng key, payload khác | Không thay nội dung lệnh gốc; trả xung đột idempotency phù hợp |
| Cùng key, lệnh còn chạy | Theo dõi cùng lệnh; không tạo nhiều tác động vì xử lý đồng thời |
| Lệnh của A đã thành công, B gọi sau | Không ghi sai B là người tạo phê duyệt cũ |
| Quyền đọc kết quả đã bị thu hồi | Không lộ kết quả chỉ vì caller biết key |
| Outbox lỗi sau bước cập nhật trong transaction | Rollback theo thiết kế; không báo một conflict nghiệp vụ giả |
| Lỗi cạnh tranh chỉ xuất hiện lúc commit | Mapper vẫn phản ánh đúng kết quả transaction |
| Commit thành công nhưng response bị mất | Retry cùng lệnh không tạo tác động thứ hai |
| Dịch vụ ngoài timeout sau khi có thể nhận lệnh | Không khẳng định NOT_APPLIED khi chưa có bằng chứng |
| Client tự thay version khi retry | Không vô tình duyệt dữ liệu mới mà chưa có quyết định phù hợp |
| Constraint không liên quan nghiệp vụ bị lỗi | Không bắt chung thành 409 hoặc lộ thông tin database |
| Bản ghi từ chối được ghi trước rollback | Đường audit vẫn giữ được bằng chứng theo hợp đồng |
| Cache hoặc thông báo lỗi qua nhiều người dùng | Không phục vụ chi tiết conflict của người này cho người khác |

Cần đối chiếu response với database, outbox, idempotency store và tác động ngoài hệ thống nếu có. Chỉ kiểm tra status code không phát hiện được trường hợp trả 409 nhưng tiền đã được chuyển, hoặc trả thành công mà lịch sử actor bị ghi sai.

## 14. Checklist thiết kế conflict response

Trước khi triển khai cho hành động sửa giá, phê duyệt, chuyển tiền hoặc thay đổi quyền, hãy xác định:

1. Xung đột gắn với version, state, ràng buộc hay idempotency?
2. Trường hợp nào thật sự là lỗi quyền, validation hoặc hạ tầng thay vì conflict?
3. Điều kiện có được thực thi nguyên tử với cập nhật, thay vì chỉ kiểm tra trước rồi ghi sau không?
4. Hệ thống có bằng chứng để nói chưa áp dụng, đã áp dụng hay chưa biết kết quả không?
5. Mã công khai và thông điệp có ổn định, không lộ dữ liệu trái quyền không?
6. Client cần tải lại, xem xét, dùng kết quả cũ hay theo dõi cùng lệnh?
7. Retry có giữ nguyên ý định và điều kiện, hay đang âm thầm tạo một quyết định mới?
8. Cách dùng key có ngăn replay thành tác động mới và ngăn payload khác ghi đè lệnh cũ không?
9. Mapper lỗi có quan sát được commit, rollback và tác động ngoài transaction không?
10. Audit và metric có phân biệt cạnh tranh hợp lệ, lỗi tích hợp và nỗ lực vượt quy tắc không?

Một conflict response có giá trị khi client hiểu cách phục hồi mà vẫn giữ nguyên các giới hạn nghiệp vụ. Thiết kế tốt giúp tránh ghi đè dữ liệu, phê duyệt nhầm phiên bản và xử lý trùng, đồng thời giữ chính xác quyền theo đối tượng, nguồn gốc quyết định và kết quả thực tế.
