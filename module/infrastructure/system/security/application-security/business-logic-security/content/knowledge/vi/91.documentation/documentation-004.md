# Tài liệu hóa chính sách phê duyệt nghiệp vụ (Approval policy documentation)

“Đơn giá trị lớn phải được quản lý duyệt” nghe rõ ràng với người viết nhưng vẫn để lại nhiều cách hiểu: lớn là từ bao nhiêu, quản lý của tenant nào, duyệt trước hay sau khi thu tiền, và người tạo yêu cầu có được tự duyệt bằng tài khoản khác không? Nếu tài liệu không trả lời, từng API, worker và công cụ vận hành có thể thực thi một chính sách khác nhau.

Trong chương **Documentation** của module Business Logic Security, approval policy documentation là việc mô tả chính sách phê duyệt nghiệp vụ đủ chính xác để người vận hành hiểu, developer triển khai và tester kiểm chứng. Nó phải liên kết quyền trên đối tượng, business invariants, state machine, nội dung được duyệt, transaction và idempotency.

Bài học tập trung vào tài liệu cho việc duyệt **thao tác nghiệp vụ**, chẳng hạn hoàn tiền, sửa giá hoặc phát hành đơn. Việc ai phê duyệt chính tài liệu/chính sách là một quy trình quản trị khác, cũng cần được ghi rõ nhưng không thay thế approval của từng giao dịch.

## 1. Một chính sách tốt phải tạo ra quyết định kiểm chứng được

### 1.1. Viết đủ để hai người độc lập có cùng kết luận

Với cùng actor, object, trạng thái, dữ liệu và phiên bản policy, người đọc phải xác định được hành động có được phép không, còn thiếu approval nào và dữ liệu nào khiến quyết định thay đổi.

| Câu mơ hồ | Điều chưa rõ | Cách viết có thể kiểm chứng |
|---|---|---|
| Quản lý được duyệt hoàn tiền | Quản lý nào, quyền trên đơn nào? | Principal có FINANCE_MANAGER trong tenant của refund và đáp ứng điều kiện độc lập mới được tính cho slot manager |
| Giao dịch lớn cần hai lần duyệt | Hai lần hay hai người? | Hai principal độc lập theo identity key, khác maker; mỗi người chỉ lấp một slot |
| Đã duyệt thì được chạy | Duyệt phiên bản nào, còn hiệu lực không? | Chỉ dispatch khi approval gắn đúng protected revision, còn hạn và đủ điều kiện tại execution gate |
| Sửa dữ liệu phải duyệt lại | Field nào, sửa comment có tính không? | Thay amount, currency, payment reference hoặc nội dung lý do bắt buộc làm tăng approval revision và vô hiệu approval cũ |
| Có lỗi thì thử lại | Retry approval hay refund? | Retry cùng ý định tìm lại cùng decision/operation theo scope; timeout provider không cho tạo nghĩa vụ refund mới |
| Quá hạn sẽ tự xử lý | Quá hạn chờ ai, có tự duyệt không? | Hết hạn trước dispatch chuyển EXPIRED; quá SLA chỉ cảnh báo/escalate, không tự tạo approval |

Những con số và role cụ thể trong bài là **policy giả định dùng để học**, không phải yêu cầu chung cho mọi tổ chức hoặc ngành.

### 1.2. Tài liệu cần nêu cả điều được phép và điều bị cấm

Một approval matrix chỉ liệt kê role được phép chưa thể hiện hết quy tắc. Phải ghi cả các điều kiện phủ định: khác tenant, tự duyệt, approval hết hạn, đối tượng sai version, tổng tiền vượt nghĩa vụ hoặc operation đã dispatch.

Theo [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), quyền cần được kiểm tra nhất quán, theo nguyên tắc đặc quyền tối thiểu và mặc định từ chối. Khi chuyển thành tài liệu nghiệp vụ, cần mô tả rõ subject, resource, action và điều kiện; chỉ ghi tên role hoặc chỉ ẩn nút giao diện là chưa đủ.

## 2. Chuẩn hóa thuật ngữ trước khi lập bảng duyệt

| Thuật ngữ | Định nghĩa sử dụng trong bài |
|---|---|
| Maker/requester | Người tạo hoặc gửi ý định nghiệp vụ cần phê duyệt |
| Approver | Người có quyền đưa ra quyết định cho đúng scope và đáp ứng điều kiện độc lập |
| Quorum | Tập slot/quyết định cần đủ, gồm role và số người độc lập, không chỉ số lần click |
| Protected revision | Phiên bản của các trường mà approval bảo vệ; khác với mọi lần cập nhật kỹ thuật của row |
| Approval snapshot | Nội dung và ngữ cảnh được đưa cho approver xác nhận |
| Decision | Một lần approve/reject có actor, object, revision, policy và outcome cụ thể |
| Execution gate | Kiểm tra cuối trước khi chấp nhận thực thi nghĩa vụ được duyệt |
| Operation | Định danh durable của ý định thực thi, tồn tại qua retry và restart |
| Delegation | Ủy quyền có phạm vi và thời gian; phải được policy cho phép rõ ràng |
| Break-glass | Quy trình ngoại lệ khẩn cấp được kiểm soát riêng, nếu tổ chức cho phép |

Authentication xác định danh tính; authorization xác định quyền; approval là quyết định nghiệp vụ trong workflow. Đăng nhập lại hoặc hoàn thành MFA không tự thay cho một quyết định approve gắn với đúng nội dung.

Nếu policy yêu cầu hai người, định nghĩa “người độc lập” theo identity key được tổ chức quản lý. Hai account khác nhau của cùng một người không mặc nhiên đáp ứng quorum. Tài khoản dùng chung làm suy yếu khả năng chứng minh độc lập và quy trách nhiệm; tài liệu cần ghi giới hạn hoặc cấm sử dụng theo mô hình đã chọn.

## 3. Cấu trúc một tài liệu approval policy

### 3.1. Metadata quản trị

Tài liệu nên có policy ID, version, trạng thái quản trị, owner, người phê duyệt policy, ngày hiệu lực, phạm vi và các phiên bản bị thay thế. Ghi rõ đây là chính sách chuẩn tắc đã được chấp nhận hay bản draft chưa áp dụng.

Trạng thái của tài liệu không phải trạng thái của giao dịch. Một file mang nhãn “published” không làm refund trở thành APPROVED; một refund APPROVED cũng không chứng minh policy hiện hành đã được triển khai đúng ở mọi entry point.

### 3.2. Các nội dung phải tra được

1. Mục đích, thao tác và đối tượng nằm trong scope; các trường hợp không hỗ trợ.
2. Business invariants và hậu quả cần ngăn chặn.
3. Nguồn dữ liệu tin cậy, đơn vị tiền, cách tính ngưỡng và quy tắc tổng hợp.
4. Actor/role/relationship, scope tenant/object và điều kiện độc lập.
5. Approval matrix với ngưỡng và biên rõ ràng.
6. State machine, guard, side effect và điểm approval bị tiêu thụ hoặc vô hiệu.
7. Protected fields, thời hạn, thu hồi, thay đổi quyền và policy migration.
8. Hợp đồng transaction, concurrency, idempotency và xử lý kết quả unknown.
9. Ngoại lệ, delegation, timeout/SLA và escalation.
10. Audit/evidence, dữ liệu nhạy cảm và liên kết rule → implementation → test.

Nếu một mục chưa được giải quyết, ghi câu hỏi mở, owner và ảnh hưởng. Không ngầm dùng “admin xử lý được” làm câu trả lời cho mọi trường hợp thiếu rule.

## 4. Ví dụ xuyên suốt: chính sách duyệt hoàn tiền

### 4.1. Fixture và phạm vi

Policy giả định REFUND-APPROVAL version 3 áp dụng cho refund bằng VND về phương thức thanh toán gốc, trong cùng tenant. Hoàn khác currency hoặc chuyển sang người nhận/phương thức khác bị từ chối trong scope này; nếu nghiệp vụ cần, phải có policy riêng.

Fixture có:

- Order ORD-900 thuộc tenant T1, khoản thu đã xác minh là 5.000.000 VND.
- Các refund đã xác nhận tổng cộng 500.000 VND; ban đầu không có reservation refund khác.
- Maker A tạo refund RF-63 số tiền 1.500.000 VND.
- B có FINANCE_REVIEWER, C có FINANCE_MANAGER trong T1; A, B, C là ba identity key khác nhau.
- Approver phải được hiển thị order/payment reference, amount, currency, phương thức hoàn, lý do và revision đang duyệt.

Các role và số tiền chỉ dành cho fixture. Không suy từ tên role rằng B hoặc C có quyền trên mọi tenant hay mọi chức năng hoàn tiền.

### 4.2. Invariant của policy mẫu

```text
AP-01: Maker không được tự approve ý định do mình tạo/gửi.
AP-02: Mọi decision và execution phải thuộc đúng tenant/object scope.
AP-03: Quorum phải đủ slot bằng những identity key độc lập được phép.
AP-04: Approval chỉ có hiệu lực cho protected revision và policy đã ghi nhận.
AP-05: Tiền đã hoàn + tiền đang reserve không vượt khoản thu có thể hoàn.
AP-06: Một refund operation có tối đa một hiệu lực hoàn tiền được phép.
AP-07: Không dispatch từ trạng thái chưa được duyệt hợp lệ hoặc đã hết hạn.
AP-08: Không đổi nghĩa của retry để tạo operation/decision mới ngoài ý định gốc.
```

### 4.3. Định nghĩa số tiền và tổng hợp chống chia nhỏ

Trong fixture, amount là số nguyên VND dương do server kiểm tra; không nhận số âm, phần thập phân hoặc currency khác rồi âm thầm ép kiểu. Dữ liệu khoản thu/refund/reservation đến từ trạng thái durable đã đối soát, không lấy tổng do client gửi.

Hai công thức phục vụ hai mục đích khác nhau:

```text
availableRefund = capturedRefundableAmount
                - confirmedRefundAmount
                - activeReservationAmountOfOtherRequests

approvalBasis = confirmedRefundAmount
              + activeReservationAmountOfOtherRequests
              + requestedRefundAmount
```

`availableRefund` kiểm tra còn đủ nghĩa vụ để hoàn; `approvalBasis` chọn cấp duyệt theo tổng tích lũy của order trong policy mẫu. Các reservation khác gồm yêu cầu đã submit, đã approve, đã dispatch hoặc đang unknown mà chưa được kết thúc/giải phóng hợp lệ. Draft chưa submit không chiếm reservation trong mô hình này.

Tại submit, server kiểm tra số dư và tạo reservation cùng việc ghi basis/quorum requirement. Việc tính tổng và reserve phải được bảo vệ khỏi concurrency. Nếu tính cả reservation của request hiện tại thêm lần nữa, hệ thống sẽ đếm trùng; tài liệu và test phải nêu rõ loại trừ nó khi đánh giá lại.

Với RF-63:

```text
availableRefund = 5.000.000 - 500.000 - 0 = 4.500.000 VND
approvalBasis   = 500.000 + 0 + 1.500.000 = 2.000.000 VND
```

Policy mẫu vì vậy cần tier cao ở mục 5. Việc “giao dịch lớn” được tính theo tổng tích lũy của order là một lựa chọn nghiệp vụ của fixture; tài liệu thực tế phải ghi nếu dùng cách khác như mỗi request, mỗi khách hàng hoặc cửa sổ thời gian.

## 5. Viết approval matrix và quyền theo đối tượng

### 5.1. Điều kiện chung áp dụng trước mọi hàng của matrix

Decision chỉ được chấp nhận nếu actor đang hoạt động, có quyền trong tenant của refund, có scope trên object, khác maker và chưa lấp slot khác của cùng protected revision. Caller không được tự gửi role, approver ID hoặc policy version để buộc server chấp nhận.

Nếu điều kiện chung không đạt, kết quả là từ chối; không tìm một hàng matrix khác để lách điều kiện. System account gọi provider không được tính vào số người phê duyệt trong fixture.

### 5.2. Ma trận giả định

| Điều kiện do server xác định | Quorum tối thiểu | Điều không được phép |
|---|---|---|
| `0 < approvalBasis <= 1.000.000 VND` và đủ số dư | Một FINANCE_REVIEWER hợp lệ | Maker tự duyệt hoặc dùng service account thay approver |
| `approvalBasis > 1.000.000 VND` và đủ số dư | Một FINANCE_REVIEWER và một FINANCE_MANAGER, là hai identity key khác nhau | Một người có cả hai role tự lấp hai slot |
| Amount không hợp lệ, vượt availableRefund, sai currency hoặc khác phương thức gốc | Không có đường approve trong policy này | Quản lý dùng quyền approve để bỏ qua invariant số tiền |
| Thiếu thông tin quyền/policy/đối tượng cần kiểm chứng | Chặn approve/dispatch và ghi lỗi/đường xử lý | Tự giảm quorum hoặc mặc định cho qua khi service quyền bị lỗi |

Đúng 1.000.000 VND thuộc tier thấp; 1.000.001 VND thuộc tier cao. Với tier cao, fixture cho phép reviewer và manager đưa quyết định theo bất kỳ thứ tự nào, nhưng chỉ APPROVED khi đã có đủ hai slot hợp lệ.

Người có cả hai role có thể được tính cho **một slot được ghi nhận rõ**, không cho cả hai. Điều kiện đủ quorum là tồn tại cách gán các approver độc lập vào các slot yêu cầu; đếm số row approval hoặc số role trong token là chưa đủ.

### 5.3. Chống chia nhỏ và thay đổi basis

Hai yêu cầu mỗi cái 800.000 VND trên một order chưa có refund có thể rơi vào tier khác nhau: request đầu reserve 800.000; request sau có basis 1.600.000. Request sau không được coi là tier thấp chỉ vì amount riêng nhỏ hơn ngưỡng.

Policy mẫu quy định mức yêu cầu của mỗi request **không tự hạ** sau khi submit. Tại execution gate, server tính lại basis hiện hành và yêu cầu tier ít nhất bằng mức cao hơn giữa tier đã ghi nhận và tier hiện tại. Nếu tier tăng, request chưa dispatch chuyển NEEDS_REAPPROVAL và chưa được thực thi cho tới khi đủ điều kiện mới.

Vì vậy một request đã có một approval có thể cần bổ sung quorum khi reservation khác làm tổng tăng. Các approval có thể được giữ làm lịch sử, nhưng việc chúng có được tính cho requirement revision mới phải được quy định; trong fixture này, tăng requirement revision vô hiệu bộ approval cũ và yêu cầu duyệt lại toàn bộ.

### 5.4. Tách quyền duyệt và quyền thực thi

| Hành động | Actor trong fixture | Guard bổ sung |
|---|---|---|
| Tạo/sửa draft | Maker có quyền tạo refund trên order | Chưa tạo hiệu lực ngoài hoặc approval |
| Submit | Maker được phép trong tenant/object scope | Amount hợp lệ, đủ số dư, tạo reservation và snapshot |
| Approve/reject | Reviewer/manager hợp lệ theo slot | Đúng revision, độc lập, còn thời hạn |
| Dispatch | Worker được cấp quyền thực thi đúng operation | Execution gate kiểm tra quorum, snapshot, policy và invariant |
| Hủy trước dispatch | Maker hoặc người được cấp quyền hủy | Chưa qua ranh giới chấp nhận thực thi; giải phóng reservation nguyên tử |
| Retry/reconcile operation | Worker/vận hành đúng scope | Giữ nguyên định danh và nội dung; không tạo approval giả |
| Sửa policy/delegation/exception | Chủ thể có quyền quản trị tương ứng | Quy trình thay đổi policy riêng, có version và audit |

Role manager không tự có quyền đổi người nhận tiền, sửa amount đã duyệt hoặc bỏ qua execution gate. Tài liệu phải nêu rõ các quyền độc lập thay vì dựa vào suy đoán từ cấp bậc.

## 6. Tài liệu hóa state machine và dữ liệu được duyệt

### 6.1. Trạng thái và điều kiện chuyển

| Từ trạng thái | Hành động/sự kiện | Sang trạng thái | Guard và hiệu lực cần ghi |
|---|---|---|---|
| DRAFT | Submit | PENDING_APPROVAL | Kiểm tra quyền/số dư, tạo reservation, chốt snapshot và requirement revision |
| PENDING_APPROVAL | Approve một slot | PENDING_APPROVAL hoặc APPROVED | Decision đúng scope/revision; chỉ APPROVED nếu đủ quorum hợp lệ |
| PENDING_APPROVAL hoặc APPROVED | Reject hợp lệ trước dispatch | REJECTED | Trong fixture, một quyết định reject kết thúc revision; giải phóng reservation khi chắc chắn chưa có hiệu lực ngoài |
| PENDING_APPROVAL hoặc APPROVED | Hủy hợp lệ trước dispatch | CANCELLED | Cạnh tranh với dispatch phải có điểm phân định; không hủy giả sau khi operation đã được chấp nhận |
| PENDING_APPROVAL hoặc APPROVED | Hết thời hạn trước dispatch | EXPIRED | Không dispatch; xử lý reservation trong transaction thích hợp |
| PENDING_APPROVAL hoặc APPROVED | Protected data/requirement thay đổi | NEEDS_REAPPROVAL | Tăng revision tương ứng, approval cũ không được tính cho bộ mới |
| NEEDS_REAPPROVAL | Submit lại hợp lệ | PENDING_APPROVAL | Kiểm tra lại policy/basis/số dư, snapshot và thời hạn mới có audit |
| APPROVED | Dispatch được chấp nhận | DISPATCHED | Execution gate đạt; tạo/claim operation và outbox theo ranh giới đã xác định |
| DISPATCHED | Có bằng chứng refund thành công | SUCCEEDED | Xác minh đúng operation/amount/currency, cập nhật ledger và reservation |
| DISPATCHED | Kết quả chưa rõ | EFFECT_UNKNOWN | Giữ đường đối soát, không tạo refund mới hoặc giải phóng nghĩa vụ tùy tiện |
| DISPATCHED hoặc EFFECT_UNKNOWN | Xác nhận thất bại không có hiệu lực | FAILED_NO_EFFECT | Có căn cứ theo hợp đồng provider; kết thúc operation và xử lý reservation |
| EFFECT_UNKNOWN | Có bằng chứng thành công | SUCCEEDED | Ghi nhận cùng effect, không chạy lại bước duyệt như một refund mới |

Các chuyển trạng thái không được liệt kê phải có rule bổ sung hoặc bị từ chối. Fixture không cho sửa protected data trong DISPATCHED/EFFECT_UNKNOWN; nếu cần thay đổi, phải giải quyết operation hiện tại và dùng workflow mới được xác định.

### 6.2. Protected fields và revision

Approval snapshot trong fixture bao gồm tenant, order/payment reference, requested amount, currency, phương thức hoàn gốc, lý do nghiệp vụ bắt buộc, policy version và requirement/basis đã chấp nhận. Tài liệu phải phân biệt version của snapshot với version kỹ thuật của row.

Sửa amount từ 1.500.000 xuống 900.000 không được mặc định giữ approval cũ chỉ vì “giảm rủi ro”. Đó vẫn là ý định khác; policy mẫu yêu cầu revision mới. Thêm một ghi chú nội bộ không ảnh hưởng quyết định có thể không tăng protected revision nếu được định nghĩa như vậy và được audit riêng.

Digest có thể giúp liên kết snapshot nhưng cần schema/canonicalization version và nội dung nguồn có thể kiểm chứng. Băm dữ liệu client tự gửi rồi gọi nó là “đã được server duyệt” không giải quyết việc xác thực nguồn hoặc quyền.

Nguyên tắc gắn quyền thực thi với dữ liệu quan trọng và kiểm tra cuối trước khi chạy được trình bày trong [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html). Trong mô hình nhiều approver ở đây, mỗi decision phải ràng buộc cùng ý định và execution gate phải kiểm chứng lại bộ quyết định đó.

### 6.3. Hạn hiệu lực, thu hồi và thay đổi quyền

Fixture quy định bộ approval chỉ có hiệu lực trong 30 phút từ lần submit hiện hành, với điều kiện `now < approval_valid_until` tại thời điểm dispatch được chấp nhận. Đúng thời điểm hết hạn không được dispatch. Retry không tự gia hạn; submit lại hợp lệ tạo revision/thời hạn mới có lịch sử.

Trước dispatch, actor có thể rút quyết định theo quyền được quy định; một withdrawal làm mất quorum phải đưa request ra khỏi APPROVED. Quyền approver trong fixture được kiểm tra khi quyết định và kiểm tra lại tại execution gate; approver đã bị thu hồi quyền trước gate không còn được tính.

Sau khi dispatch đã được chấp nhận nguyên tử, hết hạn approval hoặc thay đổi role không tự hủy hiệu lực ngoài đang chạy. Hệ thống tiếp tục đối soát cùng operation theo rule phục hồi. Nếu cần chặn cả operation đã dispatch trong tình huống khẩn cấp, phải tài liệu hóa cơ chế dừng/void/compensation riêng và giới hạn của nó.

## 7. Ghi hợp đồng transaction, concurrency và retry

### 7.1. Tài liệu phải chỉ ra ranh giới chấp nhận quyết định

Một câu “kiểm tra rồi approve” chưa nói được điều gì xảy ra nếu dữ liệu đổi giữa hai bước. Hợp đồng cần mô tả việc kiểm tra revision/quyền/slot, ghi decision và cập nhật trạng thái nằm trong ranh giới nhất quán nào.

Các cập nhật cục bộ liên quan phải cùng đạt điều kiện hoặc cùng thất bại theo mô hình transaction. Ví dụ, không commit decision cho revision 5 rồi cập nhật request revision 6 thành APPROVED. Cơ chế có thể là conditional update, khóa, constraint hoặc phương án tương đương; policy nêu kết quả bắt buộc, tài liệu thiết kế chỉ ra cách thực hiện và bằng chứng test.

Những lịch cạnh tranh cần mô tả:

- Hai approver cùng gửi quyết định cho các slot khác nhau.
- Cùng một approver gửi lặp hoặc hai account cùng identity key gửi song song.
- Maker sửa protected data trong lúc approver đang xem snapshot cũ.
- Một request mới làm basis tăng trong lúc request khác sắp dispatch.
- Reject, cancel, withdrawal hoặc expiry cạnh tranh với dispatch.
- Quyền approver bị thu hồi trong lúc worker đang đánh giá điều kiện.

Với rule kiểm tra quyền hiện hành tại gate, tài liệu kiến trúc phải giải thích nguồn quyền, version/freshness và cơ chế phối hợp với thu hồi. Một kết quả từ cache hoặc service quyền được đọc từ trước không tự bảo đảm semantics tức thời. Nếu hệ thống chỉ hỗ trợ độ trễ thu hồi có giới hạn, cần ghi và đánh giá sự khác biệt, không âm thầm tuyên bố đã đáp ứng rule mạnh hơn.

### 7.2. Điểm dispatch phải có kết quả rõ

Trong fixture, một transaction cục bộ chấp nhận dispatch sẽ:

```text
kiểm tra request còn APPROVED, đúng protected/requirement revision
kiểm tra quorum, scope, quyền hiện hành và approval deadline
kiểm tra tier/basis, số dư và reservation theo cơ chế concurrency

ghi/claim refund operation với định danh ổn định
chuyển request sang DISPATCHED
ghi outbox yêu cầu refund gắn operation và snapshot
ghi decision/execution audit cần thiết
COMMIT
```

Nếu gate phát hiện tier tăng, transaction không dispatch; nó ghi trạng thái/yêu cầu duyệt lại theo nhánh đã thiết kế. Không vừa vô hiệu approval vừa gửi refund từ snapshot cũ.

Outbox worker gọi provider ngoài transaction này. Việc commit DISPATCHED chỉ xác nhận hệ thống đã chấp nhận thực thi, không chứng minh provider đã hoàn tiền. Approval policy cần ghi sự khác biệt để API và người vận hành không diễn giải nhầm.

### 7.3. Phân biệt idempotency của decision và của hiệu lực

| Thao tác | Định danh/scope cần mô tả | Replay hợp lệ không được tạo thêm |
|---|---|---|
| Submit request | Tenant, maker, action, key và fingerprint | Request/reservation mới cho cùng ý định |
| Approve/reject | Tenant, approver identity, request, revision, loại decision và key | Decision mới được tính thêm vào quorum |
| Dispatch | Business operation và execution claim tương ứng | Refund operation hoặc outbox logic mới cho cùng lần thực thi |
| Gọi provider | Provider account, operation/action và external key ổn định | Hiệu lực refund thứ hai |
| Callback/reconcile | Provider event/effect ID cùng scope | Payment/refund record hoặc chuyển trạng thái logic trùng |

Cùng key nhưng đổi request, revision, amount hoặc loại quyết định phải bị xử lý xung đột theo hợp đồng, không sửa ý định cũ. Replay cached response vẫn cần kiểm tra quyền xem/kết quả theo policy; key không phải bằng chứng sở hữu.

Khác key cũng không được cho phép một người tự lấp hai slot hoặc một operation hoàn tiền hai lần. State machine, uniqueness và ràng buộc theo đối tượng là lớp độc lập với chống trùng theo key.

### 7.4. Timeout, unknown và lỗi nguồn quyết định

Nếu decision đã commit nhưng API mất response, caller phải có cách tra cứu hoặc replay cùng ý định. Không yêu cầu người dùng bấm approve lần nữa rồi tính đó là một người độc lập khác.

Nếu provider đã hoàn tiền rồi mất response, giữ EFFECT_UNKNOWN và đối soát cùng operation. Không trả reservation về khả dụng chỉ vì HTTP timeout; nếu làm vậy, yêu cầu khác có thể được phép hoàn vượt nghĩa vụ.

Khi policy/quyền không xác minh được, chặn decision/dispatch mới trong phạm vi đó và ghi đường phục hồi. Đừng trộn việc này với phục hồi operation đã dispatch hợp lệ: nghĩa vụ cũ vẫn cần được đối soát, không được bỏ quên chỉ vì service policy tạm lỗi.

## 8. Ghi bằng chứng của đúng quyết định

### 8.1. Decision record phải đủ ngữ cảnh

Ví dụ dưới là dữ liệu giả cho decision của B trên RF-63. Đây là một approval cho slot reviewer, chưa đủ để tier cao trở thành APPROVED.

```json
{
  "decision_id": "DEC-201",
  "request_id": "RF-63",
  "tenant_id": "T1",
  "action": "refund.approve",
  "decision": "APPROVE",
  "decision_time": "2026-11-23T03:05:00Z",
  "policy_id": "REFUND-APPROVAL",
  "policy_version": 3,
  "protected_revision": 5,
  "requirement_revision": 2,
  "maker_identity_key": "PERSON-A",
  "approver": {
    "principal_id": "USER-B",
    "identity_key": "PERSON-B",
    "slot": "FINANCE_REVIEWER",
    "authorization_decision_ref": "AUTHZ-81"
  },
  "approved_snapshot": {
    "order_id": "ORD-900",
    "payment_reference": "PAY-900",
    "refund_amount": 1500000,
    "currency": "VND",
    "amount_unit": "VND_integer",
    "destination": "ORIGINAL_PAYMENT_METHOD",
    "reason_code": "ITEM_RETURNED",
    "approval_basis": 2000000,
    "required_slots": ["FINANCE_REVIEWER", "FINANCE_MANAGER"]
  },
  "approval_valid_until": "2026-11-23T03:30:00Z",
  "outcome": "RECORDED_QUORUM_INCOMPLETE",
  "correlation_id": "REQ-APPROVE-81"
}
```

Trong fixture này, lần submit hiện hành lúc 03:00Z nên hạn 03:30Z không được kéo thành 03:35Z chỉ vì B duyệt lúc 03:05Z. Decision của C phải gắn cùng protected/requirement revision và còn hợp lệ khi execution gate chấp nhận dispatch.

Schema, policy version và identity key trong ví dụ cần được định nghĩa và bảo vệ tương ứng. Không lưu mật khẩu, OTP, bearer token hoặc dữ liệu tài khoản/thẻ đầy đủ trong decision record chỉ để “chứng minh đã duyệt”.

### 8.2. Audit phải phân biệt attempt, commit và effect

Tài liệu cần quy định ít nhất các event:

- Approve/reject/withdraw được yêu cầu và kết quả chấp nhận/từ chối.
- Protected/requirement revision thay đổi, approval cũ bị vô hiệu và lý do.
- Policy/version được áp dụng, actor/scope và nguồn quyết định quyền.
- Quorum đủ, mất quorum hoặc hết hạn.
- Dispatch được chấp nhận, operation được tạo/claim và kết quả gọi ngoài.
- Retry, conflict, callback trùng, compensation và can thiệp vận hành.

Log “approver clicked Approve” chỉ là dấu vết tương tác; không chứng minh decision đã commit hoặc refund đã có hiệu lực. Audit cho phép tái dựng phải liên kết tới dữ liệu durable và chỉ ra outcome có thể xác minh.

Lịch lưu, quyền truy cập và dữ liệu tối thiểu của decision/audit phải được xác định theo chính sách áp dụng. Tránh giữ chỉ tên role hiện tại mà làm mất policy/decision context cần để hiểu một quyết định trong quá khứ.

## 9. Tài liệu hóa ngoại lệ, ủy quyền và escalation

### 9.1. Chọn rõ hỗ trợ hay không hỗ trợ

Policy mẫu không hỗ trợ delegation hoặc break-glass cho refund; thiếu người duyệt phải chờ người đủ quyền hoặc đi qua quy trình thay đổi chính sách được phê duyệt. Đây là lựa chọn của fixture, không phải quy tắc chung cho mọi hệ thống.

Nếu một hệ thống thực tế hỗ trợ delegation, tài liệu cần chỉ rõ:

- Ai được cấp/thu hồi ủy quyền và người nhận phải có điều kiện nền nào.
- Tenant/object/action, hạn mức, thời gian bắt đầu/kết thúc và khả năng ủy quyền tiếp.
- Quyết định được ghi dưới danh tính ai, ai trực tiếp thực hiện và ai được đại diện.
- Maker có bị loại khỏi cả đường đại diện không; một người đại diện nhiều role có được tính nhiều slot không.
- Thu hồi/expiry tác động thế nào lên decision chưa dispatch và operation đã dispatch.

Delegation không được tự tạo thêm số người độc lập. Nếu cùng một người duyệt trực tiếp rồi đại diện manager, vẫn phải áp dụng định nghĩa identity/quorum của policy.

### 9.2. Không biến SLA thành auto-approve

SLA xác định thời điểm cảnh báo, chuyển hàng chờ hoặc gọi người phụ trách. Approval rule xác định ai được quyết định. Quá SLA không tự cấp quyền cho requester, bot hoặc operator tự đánh dấu APPROVED.

Nếu có auto-approval cho trường hợp rủi ro thấp, phải là một nhánh policy có scope, guard, ngưỡng, actor service, audit và test riêng. Không mô tả bằng câu “hệ thống tự xử lý khi không có người phản hồi”.

### 9.3. Break-glass cần giữ invariant còn bắt buộc

Khi được phép trong chính sách thực tế, ngoại lệ phải nêu reason/case, người yêu cầu, người cho phép, scope, thời hạn, các điều kiện được thay thế và các invariant vẫn không được bỏ qua. Ví dụ, giảm yêu cầu chờ manager không mặc nhiên cho hoàn quá số tiền có thể hoàn hoặc thực hiện lại cùng operation.

Cần ghi cách ngừng ngoại lệ, giám sát và hậu kiểm; hậu kiểm không phải bằng chứng rằng giao dịch trước đó đã được phê duyệt theo policy thông thường. Tránh các tham số client như `skipApproval=true` hoặc đường admin/batch không qua guard được xác định.

## 10. Mẫu tài liệu có thể dùng để bắt đầu

Mẫu sau là cấu trúc để điền và rà soát, chưa phải policy được phép chạy. Các mục có dấu `<...>` cần được giải quyết theo nghiệp vụ thực tế.

```text
Policy ID / version / trạng thái quản trị:
    <định danh, phiên bản, draft hay có hiệu lực>
Owner / người phê duyệt policy / ngày hiệu lực:
    <trách nhiệm và mốc triển khai>
Scope / ngoài scope:
    <tenant, object, action, currency, channel, batch/admin/worker>

Invariants:
    <rule ID, nội dung bắt buộc và lý do>
Nguồn dữ liệu và phép tính:
    <amount unit, authoritative source, aggregation, boundary>
Matrix:
    <điều kiện chung, tier, slot, distinct identity, điều kiện từ chối>
Snapshot và revision:
    <protected fields, schema, invalidation, safe metadata changes>
State machine:
    <from, action, actor, guard, to, side effect, terminal/unknown>
Thời hạn và thu hồi:
    <clock, biên, reset, quyền bị thu hồi, policy mới>
Thực thi và retry:
    <transaction boundary, execution gate, operation, idempotency>
Ngoại lệ:
    <delegation, break-glass, SLA, escalation hoặc không hỗ trợ>
Evidence:
    <decision/event schema, nguồn chứng minh, quyền xem, lịch lưu>
Traceability:
    <rule -> nơi thực thi -> test -> bằng chứng version triển khai>
Rollout/migration:
    <request cũ, approval cũ, mixed version, rollback>
Câu hỏi mở và giới hạn:
    <owner, thời điểm cần giải quyết, ảnh hưởng nếu chưa giải quyết>
```

Không cần nhồi mọi chi tiết implementation vào policy chính. Có thể liên kết tài liệu thiết kế và runbook, nhưng mỗi rule chuẩn tắc phải truy được tới guard, kiểm thử và người chịu trách nhiệm. Một link tới source code không thay cho việc giải thích nghĩa nghiệp vụ của rule.

## 11. Nối từng rule với kiểm thử và tình huống lạm dụng

### 11.1. Ma trận traceability

Tên API/component và test ID dưới đây là tham chiếu minh họa, không phải kết quả kiểm thử đã chạy cho một ứng dụng thực tế.

| Rule | Điểm thực thi cần có | Test đại diện | Bằng chứng mong đợi |
|---|---|---|---|
| AP-01 cấm tự duyệt | Approve service và mọi entry point tương đương | A approve yêu cầu của A; A dùng account khác cùng identity | Từ chối, không tăng quorum; audit reason rõ |
| AP-02 đúng scope | Lookup, authorization và decision/dispatch gate | Đổi tenant/object/approval ID của T1 khi caller thuộc T2 | Không đọc lộ snapshot, không ghi decision hoặc refund |
| AP-03 quorum độc lập | Slot assignment và uniqueness theo revision | B có cả hai role, click hai lần hoặc dùng key khác | Tối đa một slot cho identity B |
| AP-04 đúng revision | Decision commit và execution gate | Duyệt revision 5, đổi amount sang revision 6 rồi dispatch | Decision cũ không có hiệu lực cho revision mới |
| AP-05 bảo toàn tiền | Submit reservation, basis và gate | Hai refund đồng thời vượt số dư hoặc chia nhỏ ngưỡng | Không vượt tiền; không dùng tier thấp sai tổng |
| AP-06 không refund trùng | Operation ledger/provider adapter | Provider refund thành công rồi response bị mất | Cùng operation/effect, không có lần hoàn thứ hai |
| AP-07 đúng state/hạn | State machine và dispatch transaction | Gọi dispatch từ draft, thiếu manager, expired hoặc rejected | Không tạo outbox/operation có quyền thực hiện |
| AP-08 replay đúng ý định | Idempotency và fingerprint check | Cùng key đổi revision/action; replay bằng người khác | Conflict hoặc deny đúng hợp đồng; không thêm decision/effect |

### 11.2. Các case biên phải ghi cụ thể

- Basis 999.999, 1.000.000 và 1.000.001 VND, với fixture đủ tiền và không có điều kiện chặn khác.
- Amount 0, âm, vượt số dư, khác currency và dữ liệu số không được hỗ trợ.
- Đúng thời điểm hết hạn, ngay trước hết hạn và khi worker chậm sau dispatch.
- Hai decision cho hai slot tới đồng thời; hai decision cùng identity tới đồng thời.
- Maker đổi protected field khi approver đang mở màn hình cũ.
- Role approver bị thu hồi trước gate và sau khi dispatch đã được chấp nhận.
- Reservation khác làm tier tăng; reservation bị hủy không tự giảm requirement đã chốt.
- Reject/cancel/withdraw cạnh tranh với dispatch.
- Retry sau restart, callback trùng và provider effect unknown.
- Đường bulk import, admin, API cũ và background worker có cùng guard nghiệp vụ.

Một test phải assert dữ liệu durable và hiệu lực, không chỉ HTTP status. “403” nhưng decision đã commit hoặc outbox đã được phát vẫn là vi phạm; “timeout” không chứng minh provider chưa hoàn tiền.

### 11.3. Ví dụ acceptance scenario

```text
Given:
    RF-63 thuộc T1, maker A, protectedRevision=5, requirementRevision=2
    amount=1.500.000 VND, basis=2.000.000 VND
    có decision hợp lệ của B cho reviewer, chưa có manager

When:
    worker yêu cầu dispatch

Then:
    RF-63 chưa được chuyển DISPATCHED
    không tạo refund effect hoặc outbox có quyền gọi provider
    decision của B vẫn là bằng chứng một slot, không tự thành đủ quorum

When:
    C độc lập với A và B approve cùng revision, còn hạn
    execution gate kiểm tra lại và chấp nhận dispatch

Then:
    có một operation và một ý định outbox logic theo thiết kế
    retry cùng ý định tìm lại operation đó
    provider effect được theo dõi riêng tới kết quả cuối
```

Scenario này cần được bổ sung bằng test revision và concurrency. Một happy path có B rồi C không chứng minh hai slot luôn độc lập hoặc gate không thể bị bỏ qua.

## 12. Quản lý phiên bản policy và giữ tài liệu khớp hệ thống

### 12.1. Ghi hành vi của request đang chờ khi đổi policy

Thay threshold, role, protected field hoặc aggregation là thay đổi có thể làm approval cũ mất ý nghĩa. Tài liệu phát hành cần chọn rõ cách xử lý từng cohort: request chưa submit, đang pending, đã approved nhưng chưa dispatch, và operation đã dispatch/unknown.

Một lựa chọn có thể là giữ version cũ cho request đang chờ trong phạm vi được chấp nhận; lựa chọn khác là chuyển sang NEEDS_REAPPROVAL dưới version mới. Không có mặc định phù hợp mọi hệ thống. Quyết định phải có căn cứ, audit, quy tắc chuyển đổi và test.

Operation đã dispatch cần tiếp tục được đối soát theo ý định đã chấp nhận. Không tạo operation mới chỉ vì policy version hiện hành thay đổi; nếu cần dừng hoặc bù, dùng workflow riêng đã định nghĩa.

### 12.2. Đừng để mixed version tạo đường bypass

API node, worker, policy engine và công cụ admin có thể chạy khác version trong rollout. Ghi version/generation được truyền theo request/operation, hành vi khi node không hiểu schema mới và điều kiện phải chặn thực thi.

Đổi tài liệu trước hoặc sau deploy đều cần trạng thái hiệu lực rõ. Báo cáo rollout nên phân biệt policy đã được duyệt, implementation đã deploy ở scope nào và kiểm thử nào xác minh hành vi đó. Không dùng ngày sửa file làm bằng chứng hệ thống đã thực thi policy mới.

Rollback code cũng không tự hoàn tác decision/refund đã commit. Cần kiểm tra code cũ đọc được revision/schema/policy mới và không quay lại rule yếu hơn cho request đã được nâng yêu cầu.

### 12.3. Review tài liệu bằng câu hỏi có thể trả lời

Trước khi đưa policy vào sử dụng, người review nên xác định được:

1. Một caller cụ thể có quyền đọc, submit, approve, reject, cancel hoặc dispatch object nào?
2. Quorum được tính theo người và slot thế nào, có đường tự duyệt hoặc đại diện lách độc lập không?
3. Amount/basis lấy từ đâu, tính biên và chống chia nhỏ như thế nào?
4. Những thay đổi nào làm approval hết hiệu lực, và gate nào bảo đảm không chạy snapshot cũ?
5. Reject/expiry/revocation/cancel cạnh tranh với dispatch được giải quyết ở ranh giới nào?
6. Retry tạo lại response/decision/operation hay tìm về ý định cũ; unknown được đối soát thế nào?
7. Ngoại lệ có thay thế điều kiện nào, invariant nào vẫn bắt buộc và ai có thẩm quyền?
8. Có thể tìm rule ID, nơi thực thi, test và bằng chứng version đã triển khai mà không suy đoán không?

Những câu chưa trả lời được cần trở thành hạng mục có owner và ảnh hưởng cụ thể. Không thay bằng các từ “an toàn”, “đủ quyền” hoặc “hợp lệ” mà không định nghĩa điều kiện tương ứng.

## 13. Bài tập áp dụng

1. Viết lại câu “đơn lớn cần quản lý duyệt” thành rule có scope, công thức số tiền, ngưỡng, slot, distinct identity, hạn và outcome khi thiếu dữ liệu.
2. Với RF-63 trong fixture, giải thích vì sao decision của B chưa đủ. Nếu C cũng là maker A dưới account khác, hệ thống phải xử lý thế nào?
3. Thiết kế protected field list cho luồng sửa giá. Phân biệt thay đổi phải duyệt lại với ghi chú không ảnh hưởng snapshot.
4. Viết hai lịch chạy cho cancel và dispatch cạnh tranh; chỉ ra transaction/guard quyết định bên nào thắng và nghĩa vụ ngoài còn lại.
5. Mô tả việc nâng policy từ version 3 lên version 4 khi còn request APPROVED và operation EFFECT_UNKNOWN. Nêu cohort, migration và test cần có.
6. Chọn một rule, lập liên kết rule → entry points → guard → test âm tính/concurrency → evidence. Chỉ ra dữ liệu nào cần giữ để giải thích quyết định sau này.

Một tài liệu đạt mục tiêu phải cho phép trả lời **ai được quyết định, trên ý định nào, với điều kiện gì, có hiệu lực tới đâu và bằng chứng nào chứng minh hệ thống đã thực thi đúng quyết định đó**.
