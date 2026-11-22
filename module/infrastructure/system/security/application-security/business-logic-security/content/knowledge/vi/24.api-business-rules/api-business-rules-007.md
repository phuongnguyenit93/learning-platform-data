# API rule documentation: tài liệu hóa quy tắc nghiệp vụ của API

## 1. Mô tả endpoint chưa đủ để mô tả hợp đồng nghiệp vụ

Một tài liệu ghi:

```text
POST /expense-requests/{id}/approve
Yêu cầu đăng nhập.
Trả 200 khi thành công.
```

Người đọc vẫn chưa biết ai được duyệt, có được tự duyệt không, đang duyệt phiên bản nào, một phiếu có đủ hoàn tất workflow không và gửi lại sau timeout có tạo thêm quyết định hay không.

Những khoảng trống này dễ biến thành cách hiểu khác nhau giữa backend, frontend, worker và người kiểm thử. Một client có thể tưởng `200` nghĩa là đã được duyệt toàn bộ; một consumer có thể phát lệnh chi trả ngay khi mới có phiếu đầu tiên.

**API rule documentation** là việc mô tả những quy tắc, điều kiện và bảo đảm nghiệp vụ mà mỗi thao tác API phải thực thi, cùng giới hạn và cách quan sát kết quả của nó.

Trong bảo vệ logic nghiệp vụ, tài liệu cần giúp người đọc xác định được:

- Hành động nào đang được yêu cầu và ai được phép thực hiện.
- Dữ liệu nào do client đề nghị, dữ liệu nào bắt buộc do server quyết định.
- Bất biến nào phải giữ trước và sau thao tác.
- Trạng thái, version và căn cứ nào được dùng.
- Điều gì đã commit, điều gì còn chờ xử lý và điều gì chưa biết kết quả.
- Client phải làm gì khi lỗi, xung đột hoặc gửi lại.

Tài liệu không tự thực thi những điều đó. Giá trị của nó nằm ở hợp đồng đủ rõ để triển khai, kiểm thử và vận hành cùng một nghĩa.

## 2. Phân biệt schema, rule và bảo đảm thực thi

| Lớp mô tả | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Hợp đồng giao thức | Gọi method/đường dẫn nào, nhận response gì? | POST action, mã lỗi, header, định dạng body |
| Schema dữ liệu | Field nào có mặt, kiểu và giới hạn biểu diễn? | `expectedVersion`, note, định danh basis |
| Quy tắc nghiệp vụ | Trong ngữ cảnh nào dữ liệu/hành động được chấp nhận? | Không tự duyệt; đúng vòng và hạn mức |
| Bảo đảm nhất quán | Điều kiện được giữ tới đâu khi có cạnh tranh? | Decision và cập nhật tiến trình cùng transaction |
| Hợp đồng vận hành | Khi retry, lỗi dependency hoặc nhận event thì làm gì? | Replay không tạo phiếu mới; event có thể được giao lại |

### 2.1. Schema không tự biểu đạt hết ý nghĩa

`state` là enum hợp lệ không chứng minh client được gán trạng thái đó. `approvedBy` đúng kiểu ID không chứng minh người được ghi đã duyệt. Giá trị dương không chứng minh giá đúng nguồn.

Đặc tả như OpenAPI có thể mô tả cấu trúc, response và gắn tham chiếu tới business rule. Nhưng việc ghi rule trong mô tả hoặc custom extension không làm server tự thực thi rule nếu không có cơ chế triển khai tương ứng.

Ví dụ sau chỉ minh họa một liên kết tài liệu tùy dự án:

```yaml
operationId: recordExpenseApproval
x-business-rule-ids:
  - AUTH-01
  - AUTH-02
  - BASIS-01
  - QUORUM-01
  - IDEM-01
```

Các giá trị `x-business-rule-ids` không phải cơ chế phân quyền có sẵn. Tooling của dự án phải được thiết kế nếu muốn kiểm tra hoặc sinh tài liệu từ chúng.

### 2.2. Tách điều bắt buộc, lựa chọn và ví dụ

Phát biểu bắt buộc cần đủ cụ thể: “server không ghi decision nếu actor thuộc tập maker bị loại của basis hiện tại”.

Một khuyến nghị như “nên dùng idempotency” chưa mô tả hợp đồng endpoint. Cần nói header có bắt buộc không, scope, fingerprint và hành vi replay là gì.

Ví dụ payload hỗ trợ hiểu rule nhưng không thay rule. Không để một con số, role hoặc trạng thái trong ví dụ trở thành giới hạn ngầm mà code/test mỗi nơi suy ra khác nhau.

## 3. Xây danh mục rule có định danh và phạm vi

### 3.1. Một rule nên có những thông tin nào?

Một mục quy tắc có thể gồm:

```text
ruleId và phiên bản
mục tiêu/bất biến cần bảo vệ
action và loại đối tượng áp dụng
tenant/scope và chủ thể liên quan
dữ liệu đầu vào có thẩm quyền
điều kiện cho phép hoặc điều kiện cấm
thời điểm kiểm tra và giới hạn nhất quán
outcome khi không đạt hoặc chưa đánh giá được
ngoại lệ có chủ ý nếu có
tham chiếu tới triển khai và kiểm thử
```

Không cần biến mọi câu mô tả thành một hệ thống cấu hình phức tạp. Mục tiêu là có đủ thông tin để không còn phải đoán các điều kiện an ninh quan trọng.

### 3.2. Ví dụ danh mục cho action ghi phiếu duyệt

| Rule ID | Phát biểu chuẩn tắc trong ví dụ |
|---|---|
| `AUTH-01` | Lệnh mới chỉ được ghi khi actor có quyền duyệt hiện hành trong tenant và phạm vi của hồ sơ |
| `AUTH-02` | Actor thuộc tập maker bị loại theo chính sách không được duyệt basis đó, kể cả qua account/đại diện mà policy yêu cầu đối chiếu |
| `BASIS-01` | Decision chỉ áp dụng cho basis package và vòng duyệt được xác nhận; không kế thừa ngầm sang nội dung mới |
| `STATE-01` | Lệnh mới yêu cầu hồ sơ ở `IN_REVIEW`, vòng hiện tại còn mở và version phù hợp |
| `QUORUM-01` | Hồ sơ chỉ đủ duyệt khi tập decision hợp lệ đáp ứng số người độc lập và vai trò được yêu cầu |
| `TX-01` | Decision, tiến trình hồ sơ, audit thành công và outbox bắt buộc được commit hoặc rollback cùng nhau trong phạm vi transaction được thiết kế |
| `IDEM-01` | Gửi lại cùng ý định theo idempotency contract không tạo thêm decision nghiệp vụ |

Những rule này là ví dụ cho bài học, không phải khẳng định hệ thống cụ thể đã triển khai chúng.

### 3.3. Viết theo ý nghĩa, không khóa cứng vào một dòng code

“Không tự duyệt theo danh tính được chính sách xác định” bền vững hơn “kiểm tra hai field khác nhau ở dòng X”. Cách triển khai có thể đổi nhưng bất biến vẫn cần giữ.

Ngược lại, phát biểu “phân quyền đúng” quá mơ hồ để kiểm thử. Cần nêu rõ quan hệ, phạm vi và điều kiện bị cấm.

## 4. Mẫu hợp đồng cho một endpoint cụ thể

### 4.1. Mục đích và ý nghĩa thành công

Giả sử endpoint ghi **một quyết định phê duyệt của actor** cho vòng/basis hiện tại. Workflow minh họa cần hai người độc lập ở những vai trò đã được cấu hình.

```http
POST /tenants/{tenantId}/expense-requests/{expenseId}/approve
Content-Type: application/json
Idempotency-Key: client-command-key

{
  "expectedVersion": 12,
  "basisPackageId": "basis-4",
  "note": "Đã đối chiếu chứng từ"
}
```

Thành công của command nghĩa là decision đã được ghi theo hợp đồng. Nó không tự có nghĩa hồ sơ đã đạt quorum, đã chi trả hoặc tác động ngoài hệ thống đã hoàn tất.

### 4.2. Tài liệu hóa từng field và nguồn thẩm quyền

| Field/dữ kiện | Nguồn | Quy tắc trong mẫu |
|---|---|---|
| `tenantId` trên route | Client chọn, server xác minh | Không tạo membership hay quyền chỉ vì xuất hiện trên URL |
| `expenseId` | Client chỉ định mục tiêu | Nạp trong tenant/scope được phép |
| `expectedVersion` | Client khai căn cứ muốn thao tác | Số nguyên không âm; server đối chiếu version hiện tại |
| `basisPackageId` | Client chọn căn cứ muốn xác nhận | ID mờ phân biệt hoa/thường theo hợp đồng, phải khớp basis hiện tại |
| `note` | Client cung cấp | Không bắt buộc trong ví dụ, tối đa 500 Unicode code point |
| Actor, role, hạn mức | Ngữ cảnh/nguồn server đã xác minh | Không nhận từ body để quyết định quyền |
| Người duyệt, thời gian, trạng thái kết quả | Server | Được tạo sau các kiểm tra cần thiết |

Giới hạn note là ví dụ có đơn vị đo rõ; triển khai phải kiểm tra đúng đơn vị đã công bố. Không ghi “tối đa 500 ký tự” rồi để các lớp hiểu khác nhau về byte, code point hoặc đơn vị chuỗi.

Mẫu chọn từ chối field ngoài hợp đồng. Nếu dự án chọn bỏ qua unknown field để tương thích, phải ghi rõ và bảo đảm chúng không được mapper phía sau áp dụng.

### 4.3. Ghi rõ những field không được cập nhật ở action này

Endpoint không chấp nhận thay `amount`, `currency`, `ownerId`, `approvedBy`, `state`, role hoặc cờ bỏ qua phê duyệt. Muốn thay căn cứ cần lệnh và quyền riêng.

Không mô tả endpoint bằng một entity rộng rồi hy vọng người đọc biết field nào chỉ để hiển thị. Request và response có vai trò khác nhau.

## 5. Authorization, trạng thái và căn cứ duyệt

### 5.1. Mô tả quyền theo hành động và đối tượng

“Yêu cầu role APPROVER” chưa đủ. Cần nói actor có phạm vi phòng ban/đơn vị nào, hạn mức và loại tiền nào, quan hệ nào bị loại, quyền đại diện được xét ra sao.

Nếu một người thuộc nhiều tenant, quyền phải được lấy trong tenant mục tiêu. Nếu nhiều account cùng một người cần bị coi là một danh tính, tài liệu phải nêu namespace và nguồn liên kết theo mô hình của hệ thống.

Không mặc định từ tên `ADMIN` rằng được bỏ qua mọi bất biến. Ngoại lệ, nếu có, cần thẩm quyền, phạm vi và dấu vết riêng.

### 5.2. State transition phải gắn với ý nghĩa action

Ví dụ một phần hợp đồng workflow:

| Action | Trạng thái nguồn | Kết quả | Điều kiện đáng chú ý |
|---|---|---|---|
| Ghi approve | `IN_REVIEW` | Vẫn `IN_REVIEW` hoặc sang `APPROVED` | Đúng basis/vòng, actor độc lập, đủ bằng chứng; chỉ hoàn tất khi đủ quorum |
| Ghi reject | `IN_REVIEW` | `REJECTED` | Người có thẩm quyền, lý do theo policy; đóng vòng theo quy tắc |
| Withdraw | `IN_REVIEW` | `DRAFT` | Người được rút; trong ví dụ chưa có quyết định kết thúc; vô hiệu hóa vòng cũ |

Nếu đã có một phiếu approve nhưng chưa đủ quorum, policy của ví dụ cho rút và giữ phiếu cũ làm lịch sử không còn được tính. Đây là một lựa chọn cần ghi rõ, không phải mặc định chung.

Approve và withdraw chạy đồng thời phải giữ thứ tự/cạnh tranh theo version và transaction đã thiết kế. Không được vừa rút thành công vừa để phiếu cũ tiếp tục có hiệu lực trái quy tắc.

### 5.3. Phân biệt version và basis

Một phiếu mới có thể làm tăng request version nhưng không đổi nội dung basis. Một thay đổi số tiền hoặc người nhận có thể buộc tạo basis và vòng mới.

Tài liệu cần nêu dữ liệu nào làm đổi từng loại version và client xử lý xung đột thế nào. Không chỉ ghi một field `version` rồi để mọi người tự suy nó bao phủ cả ledger, bảng con và nguồn quyền.

### 5.4. Điều kiện bằng chứng phải kiểm tra được

“Có đủ chứng từ” cần tham chiếu tới tập requirement xác định: đúng đối tượng, loại bằng chứng, phiên bản, kết quả xác minh và thời hạn khi áp dụng.

Nếu requirement thay đổi trong vòng đang mở, cần quy tắc chuyển tiếp. Không đếm phiếu theo hai bộ điều kiện khác nhau mà không xác định chúng có cùng đáp ứng hợp đồng không.

## 6. Tài liệu hóa response và lỗi theo ý nghĩa

### 6.1. Response thành công nêu đúng điều đã xảy ra

Ví dụ phiếu đầu được ghi đồng bộ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "decisionId": "decision-81",
  "decisionRecorded": true,
  "workflowState": "IN_REVIEW",
  "requestVersion": 13,
  "basisPackageId": "basis-4"
}
```

Nếu đủ quorum, `workflowState` có thể là `APPROVED`. Không trả một cờ chung `success` rồi buộc client đoán nó có nghĩa ghi phiếu, duyệt toàn bộ hay chi trả xong.

Nếu API tạo tài nguyên decision có địa chỉ riêng và chọn `201`, mô tả `Location` và dữ liệu của tài nguyên mới. Nếu dùng `204`, không đưa một response body mâu thuẫn với hợp đồng không có nội dung.

### 6.2. Bảng lỗi cần cả nguyên nhân và bảo đảm tác động

| Nhóm | Mã minh họa | Hành vi trong hợp đồng |
|---|---|---|
| Sai cấu trúc/field ngoài hợp đồng | `400` | Không thực hiện lệnh nghiệp vụ |
| Chưa xác thực hợp lệ | `401` | Không mở dữ liệu/tác động cần danh tính |
| Thiếu quyền, tự duyệt | `403` hoặc cách che sự tồn tại đã chọn | Không tạo decision có hiệu lực |
| Không có đối tượng trong scope | `404` | Không tiết lộ dữ liệu ngoài phạm vi |
| Sai trạng thái, version hoặc basis | `409` | Không tự chấp nhận căn cứ mới thay người dùng |
| Precondition HTTP không thỏa mãn | `412` nếu dùng hợp đồng tương ứng | Client xử lý lại điều kiện theo API |
| Chưa đủ evidence/rule dữ liệu | `400` hoặc `422` theo lựa chọn dự án | Không ghi quyết định duyệt trái requirement |
| Dependency bắt buộc lỗi | Lỗi dịch vụ như `503` | Không coi chưa kiểm tra được là permit |

Chọn một hợp đồng cụ thể cho endpoint thật. Không để bảng tài liệu cho phép mọi mã thay thế nhau mà không nói khi nào dùng mã nào.

### 6.3. Không viết “mọi lỗi đều không có thay đổi”

Một response có thể thất bại sau khi transaction đã commit nhưng trước khi client nhận được kết quả. Timeout hoặc lỗi đường trả response không chứng minh command chưa chạy.

Tài liệu cần phân biệt lỗi xác định được trước commit với trạng thái kết quả chưa rõ. Client retry cùng ý định theo idempotency contract hoặc tra cứu kết quả được phép, không tự sinh key mới để thử lại một nghĩa vụ có thể đã thực hiện.

### 6.4. Từ chối authorization khác ghi quyết định reject

Một người không có quyền gọi approve không làm hồ sơ trở thành `REJECTED`. Ngược lại, người có quyền gọi action reject có thể nhận HTTP thành công trong khi kết quả nghiệp vụ là từ chối hồ sơ.

Cần phân biệt trong mã lỗi, response, event và audit, tránh để consumer hoặc UI hiểu sai.

## 7. Hợp đồng idempotency và retry phải đủ cụ thể

### 7.1. Những thông tin cần công bố

- Header/key có bắt buộc không và giới hạn biểu diễn là gì.
- Namespace của key và phạm vi chủ thể/tenant/action/đối tượng.
- Các field nào tham gia fingerprint, cùng quy tắc chuẩn hóa có ý nghĩa.
- Hành vi khi cùng key cùng nội dung, cùng key khác nội dung và request còn đang xử lý.
- Kết quả được giữ trong bao lâu hoặc được quản lý vòng đời theo quy tắc nào.
- Quyền cần có để nhận lại kết quả và hành vi sau khi key không còn được lưu.

Không có một thời gian lưu chung đúng cho mọi nghiệp vụ. Tài liệu API thật cần giá trị hoặc quy tắc xác định được, không chỉ để chữ “một khoảng thời gian”.

### 7.2. Mẫu semantics cho endpoint duyệt

Trong ví dụ, key được ràng buộc với tenant, chủ thể, action và hồ sơ. Fingerprint bao gồm các field có ý nghĩa của lệnh sau chuẩn hóa theo hợp đồng.

Replay hợp lệ trả kết quả đã commit, không ghi thêm phiếu và không bắt trạng thái nguồn cũ phải còn như một lệnh mới. Cùng key khác nội dung nhận xung đột theo hợp đồng.

Một lệnh mới yêu cầu quyền ghi phiếu hiện hành. Với replay, mẫu chọn kiểm tra quyền hiện tại để đọc biên nhận tương ứng; mất quyền approve không tự xóa lịch sử, nhưng cũng không tự cấp quyền xem mọi kết quả. Nếu dự án chọn yêu cầu vẫn còn quyền approve để nhận replay, phải ghi khác biệt đó rõ ràng.

### 7.3. Khác key không tạo quyền thực hiện thêm

Uniqueness theo vòng/danh tính và state machine vẫn phải ngăn một người được tính nhiều lần. Idempotency không thay bất biến domain.

Tài liệu cần nêu khi nào client đang retry một ý định và khi nào thay basis/nội dung tạo một ý định mới. Không bảo client đổi key sau mọi lỗi mà không biết kết quả lần trước.

### 7.4. Hướng dẫn retry theo loại outcome

Lỗi cấu trúc cần sửa request. Lỗi quyền không nên được retry bằng credential mạnh hơn tự động. Xung đột có thể cần đọc lại và xác nhận căn cứ. Lỗi tạm thời có thể retry có kiểm soát theo key cũ nếu vẫn là cùng ý định.

Các hướng dẫn này phải phù hợp với trạng thái lệnh đang xử lý và retention thực tế, không chỉ là một trường `retryable = true` thiếu ngữ cảnh.

## 8. Transaction, quyền hiện hành và tác động bất đồng bộ

### 8.1. Ghi rõ phạm vi nguyên tử

Ví dụ `TX-01` bao gồm decision, request version/state, audit thành công và outbox trong cùng transaction cục bộ. Nó không nói rằng transaction đó rollback được một khoản tiền đã chuyển ở hệ thống ngoài.

Cần mô tả những nguồn nằm ngoài phạm vi và cách phối hợp: operation, reservation, outbox/inbox, idempotency hoặc đối soát theo thiết kế.

### 8.2. Độ mới của quyền là một phần hợp đồng

“Kiểm tra quyền” cần được hiểu theo nguồn và thời điểm. Nếu dùng cache, cần xác định giới hạn cũ cho loại hành động. Nếu yêu cầu thu hồi ngăn commit dựa trên quyền cũ, phải có giao thức bảo vệ đủ mạnh giữa đường thu hồi và đường thực thi.

Không ghi “thu hồi có hiệu lực tức thời” chỉ vì có event invalidation hoặc vì đọc role trong transaction. Kho quyền ngoài hệ thống và sự kiện trễ cần được phản ánh trong bảo đảm thực tế.

### 8.3. 202 phải chỉ ra điều còn chờ

Nếu endpoint trả `202`, tài liệu cần nói đã tiếp nhận công việc gì, operation nào theo dõi được, các trạng thái cuối và quyền đọc kết quả.

Không dùng `202` chỉ vì workflow còn cần người duyệt tiếp theo trong khi lệnh ghi phiếu hiện tại đã commit hoàn tất. Đó là hai khái niệm khác nhau.

### 8.4. Event phải nói đúng mốc nghiệp vụ

| Event minh họa | Điều đã được xác nhận | Điều không tự suy ra |
|---|---|---|
| `ApprovalDecisionRecorded` | Một decision đã commit cho vòng/basis | Toàn bộ quorum đã đủ |
| `ExpenseApproved` | Điều kiện kết luận duyệt đã đạt theo policy | Đã chi tiền thành công |
| `PaymentRequested` | Có operation được chấp nhận để xử lý | Cổng ngoài đã thực hiện thành công |

Mô tả tenant, aggregate version, basis/round, operation và ý nghĩa chống trùng của event. Nếu có thể giao lại hoặc đảo thứ tự, ghi rõ trong hợp đồng consumer, không hứa thứ tự toàn cục khi hệ thống không bảo đảm.

### 8.5. Audit deny không cùng nghĩa với audit thành công

Audit thành công có thể nằm trong transaction nghiệp vụ. Audit từ chối cần cơ chế không mất theo rollback. Tài liệu vận hành nội bộ cần nêu yêu cầu liên quan và cách xử lý khi kênh quan sát lỗi.

Không coi việc ghi “đã cố thao tác” là quyết định nghiệp vụ, và không để thiếu audit biến thành lý do mở quyền.

## 9. Query, preview và dữ liệu cần client hiểu đúng

### 9.1. Tài liệu query phải nêu mức cam kết

Một query về eligibility hoặc capacity cần mô tả:

- Câu hỏi domain và nguồn dữ liệu được dùng.
- Có tính pending/reservation hay không và theo ngữ nghĩa nào.
- Đơn vị, loại tiền, công thức và quy tắc làm tròn khi liên quan.
- Độ mới, snapshot/version và cách hiểu `dataAsOf`.
- Có tạo reservation/cam kết không.
- Kết quả có được dùng như căn cứ cho command sau hay chỉ hỗ trợ quyết định.

Không để client hiểu `canApprove = true` là quyền dùng vĩnh viễn hoặc `refundable = 150000` là đã giữ 150.000 cho riêng họ.

### 9.2. Preview có tham chiếu không tự là capability

Một `previewId` hoặc response có chữ ký cần được mô tả đúng: nó tham chiếu phép tính hay trao một quyền có giới hạn? Nếu là cam kết, giữ điều gì, đến khi nào và dùng đồng thời ra sao?

Command vẫn phải kiểm tra điều kiện còn bắt buộc và quyền nhận/thực hiện. Không cho phép chỉ gửi lại response query rồi bỏ các guards.

### 9.3. Hướng dẫn client cần tránh tạo đường vòng

Ghi rõ trường UI chỉ để hiển thị, cache nào không có thẩm quyền và bước nào cần người dùng xác nhận lại khi căn cứ đổi.

Client không nên tự đổi version để ép command chạy, tự chọn role từ cache hoặc coi timeout là thất bại chắc chắn. Những điều này cần xuất hiện trong ví dụ luồng, không chỉ ở một ghi chú xa endpoint.

## 10. Tài liệu công khai, nội bộ và quản lý thay đổi

### 10.1. Công khai đủ để tích hợp, không lộ bí mật không cần thiết

Client cần biết điều kiện đầu vào, quyền theo ý nghĩa nghiệp vụ, outcome, lỗi và cách retry. Không cần công khai credential, khóa ký, dữ liệu owner riêng tư hoặc mọi ngưỡng phát hiện lạm dụng nội bộ.

Tài liệu nội bộ có thể bổ sung nguồn authority, thuật toán phối hợp, constraint, event, tracing và runbook. Quyền xem tài liệu đó phải phù hợp dữ liệu được mô tả.

Không dựa vào việc giấu tên role hoặc đường dẫn như hàng rào chính. Server vẫn phải kiểm tra đúng khi người gọi biết toàn bộ API contract.

### 10.2. Một nơi có thẩm quyền cho phát biểu rule

Có thể có rule catalog, mô tả endpoint và test liên kết bằng ID. Tránh sao chép cùng một quy tắc ở nhiều nơi rồi để mỗi bản trôi khác nhau.

Tài liệu endpoint nêu các rule áp dụng và semantics riêng; rule dùng chung có thể được tham chiếu. Cần biết bản nào là chuẩn khi phát hiện mâu thuẫn, thay vì để client tự chọn cách hiểu có lợi.

### 10.3. Tương thích nghiệp vụ rộng hơn tương thích JSON

Thêm một requirement chứng từ, đổi hạn mức hoặc đổi điều kiện người duyệt có thể khiến request cũ bị từ chối dù schema không đổi.

Khi thay rule, xác định phạm vi ảnh hưởng, thời điểm áp dụng, workflow đang mở, quote/approval đã chốt và client cũ. Không mặc định chỉ đổi version URL mới là thay hợp đồng đáng chú ý.

### 10.4. Giữ lịch sử rule và quyết định

Ghi policy/rule version giúp giải thích quyết định trước đây. Nó không tự cho phép lệnh mới dùng policy cũ để bỏ qua thu hồi hoặc điều kiện bắt buộc hiện tại.

Nếu đổi rule làm cần xử lý dữ liệu đang chạy, mô tả migration hoặc quy trình chuyển tiếp. Không sửa lịch sử để giả vờ một quyết định luôn được đưa ra theo policy mới.

### 10.5. Ngoại lệ phải là một hợp đồng có thể truy vết

Nếu có thao tác khẩn cấp hoặc override, ghi rõ ai được làm, điều kiện, phạm vi, hiệu lực, audit và kiểm tra bổ sung. Không để một cờ ẩn trong endpoint chung trở thành ngoại lệ không được tài liệu hóa.

Nếu invariant là tuyệt đối, tài liệu cũng cần nêu rằng không có đường admin bỏ qua trong phạm vi được thiết kế. Khả năng sửa trực tiếp dữ liệu bên dưới là một ranh giới đặc quyền khác cần được đánh giá riêng.

## 11. Liên kết rule, code và kiểm thử

### 11.1. Dùng định danh để truy vết, không thay triển khai

Ví dụ một interface có thể tham chiếu rule:

```java
interface ApprovalUseCase {
    /**
     * Records one approval for the current request basis.
     *
     * Rules: AUTH-01, AUTH-02, BASIS-01, STATE-01, QUORUM-01.
     * A successful result does not imply payment completion.
     * Idempotent replay is governed by IDEM-01.
     */
    ApprovalResult recordApproval(
            ActorContext actor,
            ExpenseRequestId requestId,
            ApproveExpenseCommand command);
}
```

Comment không làm method an toàn. Nó tạo một điểm để reviewer tìm được phát biểu chuẩn tắc và test chứng minh hành vi tương ứng.

### 11.2. Ma trận truy vết minh họa

| Rule | Thành phần cần thực thi | Kiểm thử có ý nghĩa |
|---|---|---|
| `AUTH-01` | Policy theo tenant/đối tượng | Role đúng nhưng sai tenant/phòng ban không ghi được phiếu |
| `AUTH-02` | Quan hệ maker–reviewer và danh tính | Maker đủ role vẫn bị chặn, account phụ không tạo độc lập giả |
| `BASIS-01` | Gói căn cứ và version | Sửa số tiền/người nhận không thừa hưởng decision trái policy |
| `STATE-01` | State machine và cập nhật có điều kiện | Approve sau reject/withdraw không ghi vào vòng đã kết thúc |
| `QUORUM-01` | Tập decision có hiệu lực | Phiếu đầu chưa hoàn tất; đủ người/vai trò mới đạt |
| `TX-01` | Transaction, repository, outbox | Lỗi ghi bắt buộc không commit một phần |
| `IDEM-01` | Ledger idempotency và uniqueness | Mất response sau commit rồi retry không thêm phiếu |

### 11.3. Viết ví dụ Given–When–Then đủ cô lập nguyên nhân

Ví dụ cho `AUTH-02`:

```text
Given:
    Actor là maker của basis hiện tại.
    Actor có role duyệt, đúng tenant/phạm vi và đủ hạn mức.
    Hồ sơ đang IN_REVIEW, version và evidence hợp lệ.

When:
    Actor gửi lệnh approve cho basis đó.

Then:
    Request bị từ chối theo hợp đồng quyền.
    Không có decision có hiệu lực mới.
    Không đổi trạng thái/quorum hoặc phát event cho phép chi trả.
```

Nếu fixture không cấp role duyệt, test có thể xanh dù kiểm tra tự duyệt đã bị xóa. Tài liệu rule nên giúp tạo đúng fixture để chứng minh nguyên nhân.

### 11.4. Kiểm tra cả luồng hợp lệ và ranh giới thực thi

Cần có hai người độc lập đúng vai trò hoàn tất được workflow. Một implementation luôn trả lỗi không đáp ứng hợp đồng.

Kiểm thử qua HTTP để xác nhận schema/method/error mapping, qua cơ sở dữ liệu cho transaction/constraint và qua cổng tác động để kiểm tra event/operation. Không chỉ assert tên hàm policy đã được gọi.

### 11.5. Ví dụ tài liệu không phải bằng chứng đã chạy

Payload, bảng rule và test scenario trong tài liệu là mô tả. Muốn kết luận triển khai đạt, cần kết quả chạy tương ứng với code, cấu hình và nguồn dữ liệu của hệ thống đó.

Khi contract đổi, xem lại ví dụ, test và client behavior liên quan. Tránh giữ ví dụ cũ hứa một outcome mà implementation đã thay nghĩa.

## 12. Tự rà soát tài liệu rule của API

Trước khi coi một endpoint đã được mô tả đủ, hãy trả lời:

1. Người đọc có biết action thành công nghĩa là điều gì đã thực sự xảy ra không?
2. Quyền được mô tả theo tenant, đối tượng, danh tính và phân tách nhiệm vụ, hay chỉ là một tên role?
3. Nguồn thẩm quyền của từng dữ kiện và những field không được ghi có rõ không?
4. Trạng thái, basis, version và các requirement đã được xác định đủ để kiểm thử chưa?
5. Response/lỗi có phân biệt deny, conflict, quyết định reject và kết quả chưa rõ không?
6. Retry/idempotency có scope, fingerprint, vòng đời và quyền nhận kết quả cụ thể không?
7. Phạm vi transaction, độ mới quyền và giới hạn với hệ thống ngoài có được nói đúng không?
8. Query/preview, operation và event có bị hiểu nhầm là một cam kết rộng hơn không?
9. Có quy tắc chuyển tiếp khi policy thay đổi và đường ngoại lệ có chủ ý không?
10. Mỗi bất biến quan trọng có liên kết tới nơi thực thi và kiểm thử có ý nghĩa không?

Tài liệu API tốt làm cho quyền, quy tắc và bảo đảm của một thao tác trở nên kiểm chứng được. Nó phải nói đúng điều hệ thống cam kết, giới hạn điều chưa bảo đảm và giúp mọi thành phần giữ cùng một ý nghĩa nghiệp vụ.
