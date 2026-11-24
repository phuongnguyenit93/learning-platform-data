# Production rule checklist — Checklist vận hành quy tắc nghiệp vụ trên production

Bài học thuộc chương **Deployment Operations** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung hướng dẫn xây checklist trước, trong và sau khi đưa một quy tắc nghiệp vụ lên production, với bằng chứng đủ để quyết định mở rộng, dừng hoặc khôi phục luồng xử lý.

Một bản phát hành có thể không có lỗi HTTP 500 nhưng vẫn cho phép sai người phê duyệt, thực hiện một hoàn tiền hai lần hoặc áp dụng giá cũ sau khi dữ liệu đã đổi. Endpoint health xanh chỉ cho biết một phần khả năng hoạt động của ứng dụng; nó chưa chứng minh các bất biến nghiệp vụ vẫn được giữ.

**Production rule checklist** là danh sách các điều kiện có thể xác minh để một thay đổi rule được vận hành đúng phạm vi, đúng dữ liệu và có thể kiểm soát khi xảy ra sự cố. Mỗi mục cần nêu yêu cầu, bằng chứng, người chịu trách nhiệm và hành động khi không đạt. Checklist không thay thế policy, transaction, kiểm thử hoặc runbook; nó nối các thành phần đó thành một quyết định triển khai có căn cứ.

Sau bài học, bạn cần có thể:

- Biến bất biến nghiệp vụ thành các cổng kiểm tra trước khi kích hoạt rule.
- Kiểm tra toàn bộ đường vào, quyền theo đối tượng, version và trạng thái liên quan.
- Đánh giá tương thích giữa code, policy, schema, worker và dữ liệu đang xử lý.
- Chuẩn bị chống trùng, quan sát, canary và điều kiện dừng theo tác động nghiệp vụ.
- Phân biệt rollback phần mềm với xử lý những tác động đã xảy ra bên ngoài.
- Hoàn thiện một checklist có bằng chứng, không chỉ đánh dấu "đã kiểm tra".

Các bảng và cấu hình dưới đây là mẫu học tập cần điều chỉnh theo hệ thống. Chúng không xác nhận một môi trường production cụ thể đã được kiểm tra hoặc triển khai.

## 1. Bắt đầu từ thay đổi nghiệp vụ và các bất biến

### 1.1. Tình huống xuyên suốt

Giả sử hệ thống chuẩn bị thay policy thực thi hoàn tiền từ `refund.execute.r8` sang `refund.execute.r9`. Rule mới yêu cầu request VND có số tiền **lớn hơn** ngưỡng minh họa phải có hai checker độc lập trước khi được xếp lệnh thực thi. Request không vượt ngưỡng cần một checker theo mô hình ví dụ. Mọi checker vẫn phải có thẩm quyền, khác maker và duyệt đúng revision.

Ngưỡng là tham số nghiệp vụ do hệ thống sở hữu, không phải giá trị client được quyền chọn. Con số trong ví dụ không phải khuyến nghị cho một sản phẩm thực tế. Với currency khác, cần policy riêng; không so sánh các giá trị khác đơn vị hoặc tự coi là được miễn phê duyệt.

Một mô tả phát hành minh họa, không phải cấu hình của framework cụ thể:

~~~yaml
change_id: refund-two-checkers-example
protected_action: refund.execute
previous_policy: refund.execute.r8
candidate_policy: refund.execute.r9
example_currency: VND
high_value_threshold_minor: 10000000
threshold_operator: greater_than
high_value_required_checkers: 2
other_in_scope_required_checkers: 1
approval_identity: trusted_person_identity
approval_binding: tenant_request_content_revision
activation_scope: explicitly_selected_cohort
in_flight_requests: explicit_migration_contract_required
~~~

Đơn vị `minor` phải được định nghĩa theo hợp đồng tiền tệ ứng dụng. Không mặc định mọi currency có hai chữ số thập phân. Action thêm một approval khác action thực thi: cần cho phép tạo approval thứ nhất mà chưa đòi hỏi request đã có đủ hai approval.

### 1.2. Viết bất biến dưới dạng có thể kiểm chứng

~~~text
Không actor nào hành động trên request ngoài scope được phép.
Maker không tự phê duyệt bằng account khác cùng person identity.
Execution chỉ được tạo khi đủ approval hợp lệ cho đúng revision.
Sửa số tiền, currency hoặc người nhận làm thay đổi binding của approval.
Một operation nghiệp vụ không tạo tác động provider trùng trái hợp đồng.
Hạn mức tổng không bị vượt do hai transaction cạnh tranh.
Policy thiếu, dữ kiện bắt buộc không xác định hoặc version không tương thích
không tự biến thành quyền cho phép.
~~~

OWASP nhấn mạnh việc lấy lại các giá trị liên quan bảo mật từ phía server, cưỡng chế workflow và coi cạnh tranh dữ liệu là tình huống cần xử lý. Checklist phải chỉ ra nơi giữ các yêu cầu đó thay vì chỉ dựa vào UI hoặc role tổng quát. [OWASP: Business Logic Security](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html).

Với mỗi bất biến, ghi rõ nơi cưỡng chế và cách phát hiện vi phạm. Ví dụ "đủ hai checker" cần guard tại bước tạo execution, cơ chế bảo vệ dữ liệu phê duyệt khi cạnh tranh và bằng chứng có thể đối soát; một bộ đếm trên màn hình không đủ.

### 1.3. Xác định phạm vi ảnh hưởng

| Phạm vi | Câu hỏi trước khi phát hành |
|---|---|
| Action | Thay rule khi submit, approve, execute hay đọc kết quả? |
| Đối tượng | Áp dụng tenant, sản phẩm, currency và loại request nào? |
| Đường vào | HTTP, API cũ, batch, consumer, callback và công cụ quản trị nào có thể tạo tác động? |
| Thời gian | Rule mới áp dụng cho request mới, request đang chờ hay execution đã được chấp nhận? |
| Dữ liệu đang xử lý | Có approval cũ, lệnh trong queue, retry, DLQ hoặc callback đến muộn nào? |
| Tác động ngoài | Có provider, email, quota, inventory hoặc ledger không rollback cùng database? |

Nếu chưa quyết định cách xử lý request đang dở, chưa đủ căn cứ kích hoạt rule. Không mặc định tất cả approval cũ đều tương đương approval mới, cũng không tự thêm approval để "hoàn tất migration".

## 2. Thiết kế checklist có bằng chứng và người xử lý

### 2.1. Một mục checklist hợp lệ gồm gì?

~~~text
ID: RULE-EXEC-02
Yêu cầu: Worker không hiểu policy r9 không được thực thi lệnh r9.
Bằng chứng cần có: Kết quả kiểm tra mixed-version và hợp đồng từ chối/quarantine.
Phạm vi: Tất cả consumer tạo tác động provider trong cohort được kích hoạt.
Người phụ trách: Vai trò chịu trách nhiệm worker/queue của lần phát hành.
Kết quả: Chưa đánh giá.
Khi không đạt: Dừng kích hoạt cohort; xử lý tương thích hoặc chặn writer cũ.
~~~

Một link tới test suite không đủ nếu không biết suite nào, bản build nào, cấu hình nào và tình huống gì đã được kiểm tra. Bằng chứng cần gắn với artifact/policy/schema sẽ dùng và có thời điểm quan sát phù hợp.

Có thể dùng các kết quả sau trong hồ sơ phát hành của ứng dụng:

| Kết quả | Ý nghĩa |
|---|---|
| Chưa đánh giá | Chưa đủ bằng chứng để kết luận |
| Đạt | Có bằng chứng đáp ứng tiêu chí cụ thể trong phạm vi đã nêu |
| Chặn | Không đạt hoặc thiếu bằng chứng cho một điều kiện bắt buộc |
| Không áp dụng | Có lý do và phạm vi chứng minh mục đó không liên quan |

"Không áp dụng" không phải cách bỏ qua một kiểm soát chưa hiện thực. Các trạng thái ở đây chỉ là mẫu hồ sơ vận hành, không phải chỉ thị sửa metadata của tài liệu học tập.

### 2.2. Tách các cổng quyết định

~~~text
Định nghĩa thay đổi và bất biến
  → Đủ bằng chứng trước phát hành
  → Sẵn sàng code/schema/config/worker
  → Quan sát shadow nếu phù hợp
  → Kích hoạt cohort giới hạn
  → Mở rộng theo cổng đánh giá
  → Theo dõi tác động trễ và kết thúc giai đoạn chuyển tiếp
~~~

Bằng chứng ở cổng trước không tự thay thế cổng sau. Unit test đạt không chứng minh mọi worker đang chạy đã nhận đúng policy. Canary không lỗi trong vài phút không chứng minh job ban đêm hoặc replay từ queue cũ tương thích.

Quyền quyết định tiếp tục, dừng và mở lại luồng phải được xác định theo vai trò vận hành/nghiệp vụ của hệ thống. Checklist giúp làm rõ trách nhiệm; nó không biến một thay đổi code thành quyền tự quyết định mọi tác động tài chính.

## 3. Checklist đường gọi, actor và nguồn sự thật

### 3.1. Kiểm tra tất cả đường tạo tác động

| Mục cần xác minh | Bằng chứng phù hợp | Khi chưa đạt |
|---|---|---|
| HTTP và API phiên bản cũ dùng đúng guard | Ca gọi thật qua từng route và đối chiếu mutation | Chặn đường chưa có guard hoặc chưa mở rule mới |
| Batch/consumer không đi vòng use case | Bản đồ lời gọi và kiểm tra dữ liệu sau khi bị từ chối | Sửa ranh giới hoặc giới hạn quyền chạy |
| Service/proxy thực thi cơ chế đã thiết kế | Kiểm tra integration qua reference được ứng dụng sử dụng | Không chỉ dựa vào annotation nhìn thấy trong code |
| Công cụ quản trị và repair có kiểm soát | Quyền tối thiểu, scope, audit, quy trình xử lý cụ thể | Không dùng script tổng quát để bypass workflow |
| Quyền database không mở đường ghi tùy tiện | Mapping credential theo vai trò và phạm vi writer | Thu hẹp quyền theo thiết kế hạ tầng |

Một endpoint đã bỏ khỏi UI vẫn là đường vào nếu còn nhận request. Một consumer chạy bằng service account vẫn cần quyền theo loại lệnh/tenant và guard state/version; không fallback thành actor đặc quyền khi thiếu SecurityContext hoặc thiếu thông tin delegation.

### 3.2. Actor và quyền theo đối tượng

Checklist cần làm rõ:

- Actor/person identity được giải quyết từ principal và mapping đáng tin, không từ `actorId` trong body.
- Tenant được yêu cầu bằng URL/header đã được đối chiếu với membership; không coi header là bằng chứng có quyền.
- Query và mutation dùng cùng request ID, tenant và revision đã được kiểm tra.
- Authority tổng quát không thay quyền theo object, phân công, hạn mức hoặc phân tách maker/checker.
- Thu hồi membership, grant hoặc phân công có thời điểm hiệu lực rõ ràng; cache có giới hạn độ cũ và cơ chế kiểm soát phù hợp.
- Rule thiếu, config không nhận diện và dữ kiện quyền bắt buộc không sẵn sàng không dẫn đến mặc định cho phép.

Nếu có ngoại lệ supervisor hoặc khẩn cấp, ghi rõ điều kiện nào được thay thế. Một cờ `bypassRules=true` do client hoặc công cụ vận hành tùy ý gửi không phải một hợp đồng ngoại lệ an toàn.

### 3.3. Giá trị trọng yếu phải được xác định phía server

Số tiền, currency, người nhận, giá/chiết khấu và chủ sở hữu được tải hoặc tính lại theo dữ liệu có thẩm quyền. Expected version từ client chỉ để đối chiếu, không phải bằng chứng quyền.

Trong ví dụ r9, số checker cần thiết phải được xác định từ amount/currency/revision phía server theo policy đã chọn. Nếu request thay đổi sau khi duyệt, cần tăng revision hoặc hủy binding cũ theo quy tắc miền. Không để một luồng quản trị sửa người nhận mà giữ nguyên revision.

Cần chọn rõ thời hạn phê duyệt xét ở thời điểm tạo approval, chấp nhận execution hay gửi provider. Đồng bộ clock và nguồn thời gian là một phần của hợp đồng; không dùng thời gian client để kéo dài cửa sổ duyệt.

## 4. Checklist transaction, cạnh tranh dữ liệu và migration

### 4.1. Transaction không tự chứng minh bất biến

| Tình huống | Điều cần kiểm tra |
|---|---|
| Hai checker cùng duyệt | Lock/version/constraint ngăn số approval hoặc transition trái policy |
| Một actor gửi hai request trùng | Dữ liệu định danh người và operation được giữ nhất quán khi ghi |
| Hai request tiêu cùng hạn mức tổng | Bảo vệ tài nguyên tổng bằng cơ chế đồng thời thích hợp, không chỉ khóa từng request |
| Request đổi nội dung lúc đang duyệt | Write ràng buộc đúng version/revision đã đánh giá |
| Ghi evidence/outbox thất bại | Mutation và ý định/bằng chứng cần nguyên tử không commit một phần |
| Transaction thất bại sau khi đã gọi provider | Có đối soát và xử lý kết quả ngoài database; không giả định rollback thu hồi provider |

Ví dụ PostgreSQL phân biệt các mức isolation và yêu cầu ứng dụng xử lý retry khi có serialization failure ở các trường hợp liên quan. Chọn isolation cần dựa trên bất biến thật; một annotation transaction không tự tạo chính sách khóa hoặc retry đúng. [PostgreSQL 18: Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html).

Retry transaction phải bắt đầu lại phần quyết định cần thiết trên dữ liệu thích hợp. Không chỉ gửi lại câu lệnh cuối dựa vào kết quả allow cũ, và không đặt tác động ngoài có thể bị lặp tùy ý trong callback được retry.

### 4.2. Schema và dữ liệu cũ

Trước khi thêm cột policy/revision, trạng thái mới hoặc constraint, cần xác định:

1. Code cũ đọc dữ liệu mới thế nào; code mới xử lý dữ liệu thiếu field thế nào.
2. Writer cũ có thể tiếp tục tạo bản ghi không đủ binding hay không.
3. Backfill dùng nguồn nào, có kiểm tra sau ghi và có thể chạy lại sau gián đoạn không.
4. Dữ liệu trùng/sai hiện có được xử lý trước khi kích hoạt constraint ra sao.
5. Migration có thời gian khóa, tiêu thụ tài nguyên và kế hoạch dừng phù hợp không.
6. Khi rollback binary, schema và dữ liệu đã chuyển có còn đọc/ghi đúng nghĩa không.

Có thể triển khai theo hướng mở rộng schema trước, đưa reader/writer tương thích vào hoạt động, chuyển dữ liệu có kiểm soát, rồi mới loại bỏ biểu diễn cũ. Thứ tự cụ thể tùy hệ thống, nhưng không xóa trạng thái/cột cũ khi queue hoặc phiên bản còn chạy vẫn phụ thuộc chúng.

Không chữa lỗi migration bằng cách tắt unique constraint, bỏ tenant filter hoặc tự đánh dấu approval hợp lệ hàng loạt. Nếu dữ liệu lịch sử không đủ bằng chứng cho r9, phải giữ trạng thái cần xử lý theo hợp đồng đã chọn.

### 4.3. Mixed-version là một tình huống bắt buộc

Một API mới ghi `policy_version = r9` chưa đủ nếu worker cũ chỉ nhìn `APPROVED` rồi gửi provider. Cần bằng chứng rằng worker không hiểu r9 sẽ từ chối/quarantine đúng cách, hoặc đã bị ngăn nhận/tạo tác động trên operation r9.

Một epoch/version trong bản ghi chỉ bảo vệ khi mọi đường ghi/thực thi liên quan thật sự kiểm tra nó tại ranh giới cần thiết. Sticky routing hỗ trợ giữ một workflow trong cohort, nhưng không thay một cơ chế ngăn writer cũ xử lý nhầm.

Dữ liệu cần tương thích gồm cả message trong queue, outbox chưa phát, DLQ, snapshot cache, job trì hoãn và callback đến muộn. Số replica API đã cập nhật không phản ánh đầy đủ các thành phần đó.

### 4.4. Bảng xử lý request đang dở khi chuyển policy

Một checklist chuyển rule cần phân loại dữ liệu đang dở bằng trạng thái và bằng chứng thực tế. Chỉ đếm số request mang nhãn `APPROVED` không cho biết request đã có operation hay provider đã nhận lệnh chưa.

Giả sử chủ nghiệp vụ chọn hợp đồng minh họa: **các request chưa được chấp nhận execution trong cohort phải đáp ứng r9 tại lần chấp nhận tiếp theo**. Operation đã được chấp nhận cần hợp đồng chuyển tiếp riêng; rule mới không tự sửa ngược quyết định lịch sử. Trước khi kích hoạt cohort, hoàn thành bảng sau:

| Nhóm tại thời điểm chuyển | Cách xử lý theo hợp đồng minh họa | Bằng chứng để cho phép tiếp tục |
|---|---|---|
| Request chưa có execution, chưa đủ approval r9 | Tiếp tục luồng lấy approval; chưa cho tạo execution | Amount/currency/revision hiện tại, số checker hợp lệ và reason khi bị chặn |
| Request chưa có execution, có approval từ r8 | Đánh giá khả năng dùng lại từng approval theo r9; nếu không chứng minh được thì yêu cầu duyệt lại | Identity, quyền, revision, thời hạn và những yêu cầu r9 mà approval cũ phải đáp ứng |
| Đã có operation r8 và chứng minh chưa gửi provider | Giữ lệnh cho đến khi có quyết định chuyển tiếp rõ ràng: tiếp tục r8 nếu được phép, hoặc chuyển binding qua luồng kiểm soát | Chứng cứ chưa gửi, quyết định của người có thẩm quyền, policy sẽ thực thi và lịch sử chuyển đổi |
| Đã gửi hoặc chưa xác định provider có nhận hay không | Giữ danh tính operation để thu nhận kết quả/đối soát; chưa tạo execution thay thế | Provider reference hoặc key đã lưu, lịch sử lần gửi và kết quả tra cứu |
| Đã hoàn tất | Giữ kết quả và evidence lịch sử; chỉ đối soát hoặc điều chỉnh bằng operation có quyền riêng | Kết quả provider/ledger và liên kết đến quyết định tại thời điểm chấp nhận |

Đây là một lựa chọn chuyển tiếp cho ví dụ, không phải mặc định áp dụng cho mọi sản phẩm. Nếu r9 khắc phục một đường lạm dụng đã xác nhận, việc cho operation r8 tiếp tục cũng phải được đánh giá theo rủi ro đó; không lấy lý do “đã xếp hàng” để bỏ qua điều kiện dừng.

“Chứng minh chưa gửi” phải dựa vào cơ chế thực thi có thể kiểm soát. Thiếu provider reference trong database local chưa đủ: worker có thể đã gửi rồi chết trước khi ghi reference. Khi không loại trừ được khả năng đã gửi, chuyển sang nhóm cần đối soát. Việc giữ lệnh cũng phải chặn worker/đường replay tương ứng, không chỉ đổi nhãn trên màn hình.

Nếu cho phép migration binding của operation chưa gửi, phải bảo vệ cạnh tranh với worker, giữ lịch sử và định danh operation, đồng thời đánh giá lại các điều kiện mà hợp đồng yêu cầu. Không đổi amount/người nhận của một operation đã ràng buộc fingerprint rồi coi đó là cùng nội dung. Thay đổi nội dung nghiệp vụ cần luồng sửa/hủy/tạo mới được định nghĩa riêng và kiểm tra nguy cơ đã có tác động.

Bảng kiểm kê là ảnh chụp tại một thời điểm. Trong khi rollout, writer cũ hoặc retry có thể tiếp tục tạo dữ liệu thuộc nhóm cũ. Checklist cần nêu cơ chế chặn nguồn phát sinh hoặc tiếp tục kiểm kê, mốc kết thúc chuyển tiếp và người xử lý từng nhóm còn lại. Không xóa cơ chế tương thích chỉ vì lần kiểm kê đầu tiên trả về số lượng bằng không.

## 5. Checklist chống trùng và tác động ngoài hệ thống

### 5.1. Phân biệt request gửi lại với operation nghiệp vụ

Một request HTTP, một message và một lần gọi provider có thể là ba lần vận chuyển của cùng một operation. Ngược lại, hai request có payload giống nhau đôi khi là hai operation hợp lệ. Vì vậy, không suy ra danh tính nghiệp vụ chỉ từ hash payload hoặc số lần endpoint được gọi.

Trong ví dụ hoàn tiền, cần xác định `refund_operation_id` gắn với một ý định hoàn tiền đã được chấp nhận. Nếu hợp đồng chỉ cho phép một operation thực thi cho mỗi refund request, phải có cơ chế cưỡng chế quan hệ đó trong database. Nếu cho phép hoàn tiền từng phần, cần định danh từng phần và bảo vệ tổng số tiền đã hoàn/còn giữ chỗ theo bất biến của khoản thanh toán gốc.

| Điều cần xác minh | Bằng chứng cần có |
|---|---|
| Phạm vi idempotency key rõ ràng | Hợp đồng tenant, caller, action và namespace; test hai tenant dùng cùng key |
| Một key không đổi được nội dung | Fingerprint từ dữ liệu đã chuẩn hóa; cùng key nhưng khác amount/currency/recipient bị từ chối |
| Hai key không vượt quy tắc của cùng operation | Constraint hoặc cơ chế đồng thời bảo vệ danh tính nghiệp vụ, không chỉ bảo vệ key |
| Hai lần gửi đồng thời không cùng tạo lệnh mới | Kết quả kiểm tra cạnh tranh qua đường gọi thật và số operation/outbox thực tế |
| Dữ liệu chống trùng sống đủ lâu | Chính sách lưu giữ gắn với retry, replay, đối soát và thời hạn phía provider |
| Lặp lại response không lộ dữ liệu | Kiểm tra lại quyền đọc kết quả; không dùng key như một bearer token |

Idempotency không thay kiểm tra quyền. Một người từng có quyền tạo operation có thể đã bị thu hồi quyền khi gọi lại. Hệ thống cần quy định cách trả kết quả cho lần gọi lại mà vẫn bảo vệ dữ liệu và không tạo thêm tác động. Tương tự, thay idempotency key không cho phép vượt hạn mức, bỏ approval hoặc thực thi lại một request đã hoàn tất.

Fingerprint cần bao phủ những giá trị mà thay đổi sẽ làm thay đổi ý nghĩa operation. Nếu key và payload được lưu trước khi hoàn tất chuẩn hóa hoặc tính tiền phía server, cần thiết kế rõ thời điểm ràng buộc; tránh cùng một ý định lại được so sánh bằng hai biểu diễn tiền tệ khác nhau.

### 5.2. Tách chấp nhận lệnh khỏi hoàn tất hoàn tiền

Một luồng minh họa:

~~~text
Trong transaction chấp nhận execution:
  1. Tải request trong đúng tenant và bảo vệ cạnh tranh theo thiết kế.
  2. Xử lý mapping idempotency/operation dưới cơ chế đồng thời tương ứng.
  3. Nếu là operation đã tồn tại, không tạo tác động mới;
     chỉ trả trạng thái/kết quả mà caller hiện được phép xem.
  4. Nếu là operation mới, đánh giá quyền, state, revision, policy,
     approval và hạn mức từ dữ liệu có thẩm quyền.
  5. Giữ chỗ hạn mức nếu hợp đồng yêu cầu.
  6. Ghi operation, chuyển state và ghi outbox trong cùng transaction.
  7. Commit; response mô tả lệnh đã được chấp nhận, chưa mặc định thành công.

Sau commit:
  Worker kiểm tra hợp đồng thực thi, gửi provider bằng định danh ổn định,
  rồi ghi nhận kết quả theo state machine và cơ chế chống trùng.
~~~

Đây là thứ tự logic để thiết kế checklist, không phải thuật toán khóa dùng được cho mọi database. Nếu approval, grant hoặc hạn mức nằm ngoài transaction, cần nêu rõ mô hình nhất quán và cách phát hiện dữ liệu đã đổi. Không giả định một transaction local có thể khóa cả dịch vụ quyền hoặc provider.

Tại ranh giới gửi provider, cần quyết định điều kiện nào đã được chốt khi chấp nhận lệnh, điều kiện nào phải còn đúng tại lúc gửi. Ví dụ approval hết hạn hoặc quyền bị thu hồi sau khi lệnh được chấp nhận có thể được xử lý khác nhau theo hợp đồng sản phẩm. Worker phải thực thi đúng hợp đồng đó; việc tự bỏ qua hoặc tự đánh giá lại theo một policy ngẫu nhiên đều có thể làm sai nghiệp vụ.

### 5.3. Timeout là trạng thái chưa biết, không phải bằng chứng thất bại

~~~mermaid
stateDiagram-v2
    [*] --> APPROVED
    APPROVED --> EXECUTION_PENDING: Chấp nhận đủ điều kiện và ghi outbox
    EXECUTION_PENDING --> SUCCEEDED: Có bằng chứng hoàn tất
    EXECUTION_PENDING --> FAILED_FINAL: Có bằng chứng thất bại cuối cùng
    EXECUTION_PENDING --> RECONCILING: Timeout hoặc kết quả chưa xác định
    RECONCILING --> SUCCEEDED: Đối soát xác nhận hoàn tất
    RECONCILING --> FAILED_FINAL: Đối soát xác nhận thất bại cuối cùng
~~~

Sơ đồ chỉ minh họa phần thực thi; tên state và các transition được phép phải theo mô hình của hệ thống. Trong khi `RECONCILING`, không trả request về trạng thái có thể tạo một execution khác chỉ vì đã hết thời gian chờ HTTP. `FAILED_FINAL` cũng không có nghĩa là được tạo operation thay thế mà không kiểm tra lại bất biến liên quan.

Checklist provider cần trả lời:

- Provider hỗ trợ idempotency theo phạm vi và thời hạn nào; có ràng buộc nội dung với key không?
- Khi retry cùng operation, hệ thống có dùng lại định danh ổn định đã lưu trước lần gửi đầu không?
- Nếu worker chết sau khi provider nhận lệnh nhưng trước khi local ghi kết quả, tiến trình mới tra cứu/đối soát theo định danh nào?
- Nếu thời hạn chống trùng phía provider đã hết, có chặn việc gửi lại mù quáng và chuyển sang đối soát không?
- Callback được xác thực, gắn với đúng tài khoản provider, tenant, operation, amount và currency như thế nào?
- Callback trùng hoặc đến sai thứ tự có bị ngăn tạo thêm credit, giải phóng hạn mức hai lần hoặc làm lùi state đã hoàn tất không?

Outbox bảo vệ tính nguyên tử giữa ghi dữ liệu local và ý định gửi; nó không tự bảo đảm provider chỉ thực hiện một lần. Dedup message cũng không chứng minh tác động ngoài duy nhất. Nếu provider không có hợp đồng chống trùng hoặc cách tra cứu đủ tin cậy, cần giữ trường hợp chưa rõ để xử lý theo quy trình, thay vì tuyên bố bảo đảm exactly-once.

## 6. Checklist quan sát và bằng chứng vận hành

### 6.1. Quan sát quyết định, trạng thái và kết quả thực tế

HTTP success rate giúp quan sát khả năng phục vụ nhưng không cho biết hoàn tiền có đúng người nhận hay đúng approval. Cần liên kết ba lớp bằng chứng:

| Lớp | Dữ liệu cần quan sát | Câu hỏi trả lời được |
|---|---|---|
| Quyết định rule | Action, policy version, reason code, revision, cohort và correlation ID | Vì sao yêu cầu được chấp nhận hoặc từ chối? |
| Mutation/transition | Operation ID, state trước/sau, revision và thời điểm commit | Quyết định đã tạo thay đổi nào? |
| Tác động nghiệp vụ | Provider reference, ledger entry, số tiền và kết quả đối soát | Tác động thực tế có khớp với ý định đã chấp nhận không? |

Thông tin danh tính, tenant, số tiền và dữ liệu kiểm toán chi tiết cần được lưu trong hệ thống có kiểm soát truy cập, thời hạn lưu và chính sách bảo vệ phù hợp. Không đưa token, bí mật xác thực, toàn bộ payload thanh toán hoặc thông tin người nhận không cần thiết vào log. Quyền xem audit và quyền thay đổi dữ liệu nên được phân tách theo nhu cầu vận hành.

Metric label nên có tập giá trị hữu hạn như action, policy version đang hỗ trợ, cohort được quản lý và reason code đã chuẩn hóa. Request ID, person ID, idempotency key hoặc thông báo lỗi tự do phù hợp hơn với trace/audit có kiểm soát; đưa chúng vào metric label vừa khó vận hành vừa có thể lộ dữ liệu.

### 6.2. Tín hiệu cần có trước khi kích hoạt

Các tên dưới đây là đề xuất cho ứng dụng, không phải metric có sẵn:

~~~text
rule_decision_total{action, policy, cohort, outcome, reason}
execution_accepted_total{policy, cohort}
execution_reconciling_age_seconds
outbox_oldest_pending_age_seconds
unsupported_policy_total{component, policy}
invariant_violation_total{invariant, action}
~~~

Chỉ số số lần quyết định có thể tăng do retry; không được coi nó là số operation duy nhất. Khi tính tỷ lệ, phải định nghĩa mẫu số: số lần thử, số request nghiệp vụ, số operation được chấp nhận hay số tác động provider. Khi so canary và nhóm đối chứng, cần xét khác biệt loại giao dịch, thời điểm và phân bố số tiền.

Một số bất biến cần kiểm tra bằng đối soát dữ liệu, không thể suy ra từ counter do cùng code quyết định ghi ra. Ví dụ:

- Execution r9 có amount vượt ngưỡng phải có đủ approval hợp lệ cho revision được chấp nhận theo hợp đồng.
- Tổng tác động provider và ledger cho cùng operation phải khớp giới hạn được phép; ghi rõ cách xử lý kết quả chưa xác định.
- Tổng số tiền đã hoàn và đang giữ chỗ không vượt phần có thể hoàn theo quy tắc miền.
- Không có execution được tạo từ đường gọi ngoài scope hoặc từ worker không tương thích.

Query đối soát phải hiểu sự khác biệt giữa dữ liệu cuối cùng và dữ liệu đang hội tụ. Một outbox chưa phát trong cửa sổ xử lý cho phép không đồng nghĩa vi phạm; một provider reference thứ hai trái hợp đồng cho cùng operation là tín hiệu nghiêm trọng hơn. Kiểm tra có thể chạy chậm hơn tác động, nên cần nêu rõ độ trễ phát hiện và người xử lý.

### 6.3. Định nghĩa điều kiện dừng trước khi mở cohort

Không đợi đến khi dashboard có bất thường mới thống nhất thế nào là phải dừng. Hồ sơ phát hành cần phân biệt:

| Loại tín hiệu | Hành động đã chuẩn bị |
|---|---|
| Xác nhận vi phạm bất biến trọng yếu | Dừng mở rộng; đóng đường tạo tác động thuộc phạm vi ảnh hưởng và mở xử lý sự cố |
| Không quan sát được quyết định/kết quả cần thiết | Giữ hoặc thu hẹp cohort; khôi phục bằng chứng trước khi tiếp tục |
| Tăng từ chối hợp lệ hoặc backlog vượt ngân sách | Giữ cohort, phân tích reason và năng lực xử lý; không tự tắt guard |
| Tăng kết quả provider chưa xác định | Hạn chế phát sinh mới theo runbook; ưu tiên đối soát và kiểm tra retry |

Ngưỡng số lượng, tỷ lệ, tuổi backlog và thời gian quan sát phải do hệ thống xác định theo tác động và lưu lượng. Với hoàn tiền trái phép đã được xác nhận, không cần đợi đủ mẫu để tính ý nghĩa thống kê mới cô lập đường gây lỗi. Ngược lại, một counter tăng chưa được đối chiếu không tự chứng minh đã có chuyển tiền trái phép.

## 7. Checklist shadow, canary và mở rộng phạm vi

### 7.1. Shadow phải có ranh giới không tạo tác động

Ở chế độ shadow, policy đang áp dụng vẫn quyết định hành động; policy ứng viên chỉ tính kết quả so sánh trên dữ liệu được phép sử dụng. Nhánh shadow không được ghi approval, giữ chỗ hạn mức, tạo outbox, gửi provider hoặc làm thay đổi kết quả thật qua cache dùng chung.

Nếu policy ứng viên cần dữ kiện chưa có ở policy cũ, kết quả phải thể hiện thiếu dữ kiện, không tự suy ra allow. Ghi khác biệt theo reason và phạm vi để giải thích: r9 từ chối request có một checker là khác biệt dự kiến đối với nhóm vượt ngưỡng, nhưng từ chối mọi request VND do đọc sai đơn vị tiền là lỗi cấu hình.

Shadow giúp đánh giá khác biệt quyết định. Nó không chứng minh các transition mới, ràng buộc database, đường retry hay tác động provider đã đúng, vì chúng chưa được thực thi ở nhánh ứng viên.

### 7.2. Cohort phải ổn định theo workflow

Canary theo phần trăm request ngẫu nhiên có thể khiến bước approve dùng r8 còn execute dùng r9 mà không có hợp đồng chuyển đổi. Nên chọn đơn vị cohort phù hợp như tenant hoặc workflow, phân nhóm phía server, và lưu binding cần thiết để xử lý retry/consumer nhất quán.

Feature flag chỉ có ý nghĩa bảo vệ khi mọi đường tạo tác động liên quan thực sự kiểm tra hoặc nhận binding từ ranh giới có thẩm quyền. Không tin header `useNewRule` do client gửi. Cache flag cũng cần cách phát hiện phiên bản cũ và hành vi khi không đọc được cấu hình, đặc biệt với kill switch yêu cầu hiệu lực nhanh.

Một thứ tự triển khai có thể đưa vào checklist:

1. Mở rộng schema và triển khai code/worker hiểu hợp đồng mới, chưa kích hoạt r9.
2. Xác minh mọi writer/consumer liên quan đã tương thích hoặc được chặn khỏi phạm vi r9.
3. Chạy shadow nếu phù hợp và giải thích các khác biệt trọng yếu.
4. Kích hoạt cohort giới hạn; xác nhận policy thực tế tại cả API và worker.
5. Quan sát đủ các đường xử lý, bao gồm hoàn tất, timeout, retry, đối soát và job có độ trễ.
6. Mở rộng sau khi cổng đánh giá có bằng chứng và người chịu trách nhiệm xác nhận.
7. Kết thúc giai đoạn chuyển tiếp khi dữ liệu cũ, queue và các đường replay đã được xử lý theo hợp đồng.

Khoảng quan sát không chỉ là số phút chờ. Với lưu lượng ít hoặc hoàn tiền giá trị cao hiếm xuất hiện, vài phút không lỗi có thể chưa đi qua nhánh quan trọng nào. Cần kết hợp kiểm tra trước phát hành với bằng chứng vận hành đủ đại diện, và ghi rõ phần chưa quan sát được.

## 8. Checklist dừng luồng, rollback và khôi phục

### 8.1. Kill switch phải dừng đúng tác động

Runbook cần chỉ ra vị trí chặn: chấp nhận execution mới, phát outbox, worker gửi provider hay một phạm vi tenant/action. Cần biết các lệnh đã vượt ranh giới đó sẽ tiếp tục thế nào. Một flag chỉ tắt nút trên UI không ngăn API, queue hoặc job tiếp tục gửi.

Khi dừng phát sinh tác động mới, vẫn cần cho phép các đường thu nhận kết quả và đối soát hợp lệ hoạt động nếu thiết kế cho phép. Tắt luôn callback có thể khiến hệ thống không ghi nhận khoản hoàn tiền provider đã thực hiện. Không xóa outbox hoặc DLQ chỉ để dashboard hết backlog; giữ danh tính operation và bằng chứng cần khôi phục.

Việc dừng cũng có cạnh tranh: worker có thể đã đọc flag trước khi có lệnh dừng. Checklist phải mô tả độ trễ hiệu lực, các lệnh đang gửi và cách nhận diện chúng. Nếu dùng epoch/fencing để thu hồi quyền gửi, phải xác minh thành phần tại ranh giới gửi thật sự cưỡng chế nó; chỉ ghi epoch vào log không chặn được worker cũ.

### 8.2. Rollback code không xóa tác động nghiệp vụ

| Thành phần | Cần quyết định khi rollback |
|---|---|
| Binary | Phiên bản trước có hiểu state, field và message đã tạo không? |
| Policy | Quay về rule cũ có mở lại đường lạm dụng mà r9 vừa chặn không? |
| Schema | Giữ phần mở rộng hay có migration riêng; writer cũ có còn an toàn không? |
| Execution đang chờ | Tiếp tục theo binding cũ, giữ để xử lý hay chuyển đổi có bằng chứng? |
| Provider/ledger | Đối soát tác động đã xảy ra và ghi điều chỉnh theo nghiệp vụ nào? |
| Evidence | Giữ được lịch sử quyết định, version và liên kết operation hay không? |

Trong ví dụ r9, quay binary về phiên bản chỉ yêu cầu một checker có thể khôi phục khả năng phục vụ nhưng làm mất yêu cầu phê duyệt mới. Nếu không giữ được guard tương đương, lựa chọn vận hành có thể là tạm giữ execution của phạm vi đó và sửa tiến thay vì mở lại r8.

Không restore toàn bộ database từ trước phát hành rồi giả định provider cũng quay về thời điểm đó. Dữ liệu local sẽ mất liên kết với tác động đã xảy ra, có thể dẫn đến gửi lại. Khi cần bù trừ, phải dùng operation điều chỉnh được định danh, phân quyền và kiểm toán; không sửa lịch sử thành chưa từng có sự cố.

### 8.3. Trình tự khôi phục một lỗi logic

1. Cô lập đường gây tác động và ghi lại phạm vi thời gian, policy, cohort, worker có liên quan.
2. Giữ bằng chứng và danh sách operation, bao gồm cả trường hợp đang chưa xác định kết quả.
3. Đối chiếu dữ liệu local với provider/ledger; phân biệt đã hoàn tất, thất bại chắc chắn và cần đối soát tiếp.
4. Chuẩn bị bản sửa hoặc cách giữ guard an toàn; xử lý dữ liệu sai bằng luồng repair có quyền và nhật ký.
5. Xác minh điều kiện mở lại trên bản sửa, dữ liệu và các lệnh tồn đọng, không chỉ trên process mới khởi động.
6. Mở lại theo phạm vi kiểm soát, theo dõi tác động trễ và hoàn tất xử lý các operation còn giữ.

Replay là một hành động nghiệp vụ có khả năng tạo tác động, không phải thao tác vận hành vô hại. Cần xác định replay tiếp tục operation cũ hay tạo operation mới, giữ key nào và dùng policy nào. Không thay operation ID để né lỗi dedup hoặc cưỡng ép một request đi qua.

## 9. Ma trận tình huống tấn công logic cần có bằng chứng

Bảng sau là kế hoạch kiểm thử cho ứng dụng, không phải kết quả đã chạy trên một môi trường cụ thể. Mỗi ca cần quan sát cả response, mutation, outbox và tác động giả lập/đối soát; response bị từ chối chưa chứng minh transaction không để lại dữ liệu sai.

| Tình huống | Kỳ vọng nghiệp vụ | Bằng chứng cần lưu |
|---|---|---|
| Gọi execute thẳng khi chưa đủ approval | Không chấp nhận execution và không phát sinh ý định gửi | State, operation/outbox và reason code |
| Amount bằng ngưỡng và vượt ngưỡng một đơn vị hợp đồng | Áp đúng toán tử `greater_than`, đúng currency và đơn vị | Dữ liệu server, policy, số checker yêu cầu |
| Sửa amount hoặc recipient sau khi được duyệt | Approval cũ không cho thực thi nội dung mới | Revision/binding trước sau, kết quả guard |
| Maker dùng account khác cùng person identity để duyệt | Không tính thành checker độc lập | Mapping identity tin cậy và bản ghi approval |
| Thay tenant/request ID trong URL hoặc body | Không đọc/sửa object ngoài scope | Kết quả quyền và kiểm tra dữ liệu hai tenant |
| Thu hồi grant khi execution đang chờ | Tuân theo thời điểm hiệu lực đã định nghĩa | Mốc thu hồi, binding quyền và quyết định thực thi |
| Hai checker hoặc hai execution cạnh tranh | Không vượt transition, số operation hay hạn mức được phép | Timeline transaction và trạng thái commit cuối |
| Hai request khác nhau cùng tiêu hạn mức còn lại | Tổng được bảo vệ dưới cạnh tranh | Số dư/giữ chỗ và kết quả cả hai transaction |
| Cùng key nhưng payload khác; khác key cùng operation | Không đổi nội dung key, không tạo execution trùng trái hợp đồng | Mapping key/fingerprint và constraint nghiệp vụ |
| Provider nhận lệnh rồi worker timeout/chết | Giữ khả năng đối soát, không gửi operation mới mù quáng | Provider reference/key, state local và đường phục hồi |
| Callback trùng, giả mạo hoặc đảo thứ tự | Chỉ nhận nguồn hợp lệ, không lặp tác động hoặc lùi state trái phép | Xác thực callback, dedup và lịch sử transition |
| Worker cũ nhận message r9 | Không tạo tác động bằng cách hiểu thiếu policy | Quarantine/từ chối hoặc bằng chứng không được nhận lệnh |
| API cũ, batch, repair tool cố bỏ guard | Guard vẫn có hiệu lực hoặc đường đó bị chặn trong phạm vi | Ca qua từng đường vào và mutation sau xử lý |
| Mất config/policy hoặc dependency quyền | Hành vi lỗi đúng hợp đồng, không fallback sang allow | Reason, response/state và cảnh báo |
| Dừng cohort rồi có retry/DLQ đến muộn | Không vượt cơ chế dừng; operation cũ được xử lý đúng danh tính | Binding cohort/policy và dấu vết replay |

Các ca race phải có điểm đồng bộ đủ để tạo cạnh tranh thật; chạy tuần tự hai request không chứng minh an toàn đồng thời. Với tác động ngoài, nên có mô hình provider cho phép tái hiện timeout sau khi đã nhận lệnh và callback đến muộn. Không tạo khoản hoàn tiền thật trên production chỉ để đánh dấu checklist hoàn thành.

## 10. Mẫu checklist dùng trong hồ sơ phát hành

Mẫu này tập hợp cổng quyết định; các phần trước giải thích cách đánh giá từng mục. Mọi kết quả ban đầu đều là **chưa đánh giá** cho đến khi có bằng chứng của lần phát hành. Vai trò trong bảng cần được gán người/nhóm cụ thể theo tổ chức.

| ID | Điều kiện bắt buộc trước cổng tương ứng | Bằng chứng gắn với lần phát hành | Vai trò phụ trách |
|---|---|---|---|
| P01 | Action, scope, bất biến và toán tử ngưỡng được xác định | Hợp đồng rule và bộ ví dụ biên | Chủ nghiệp vụ và nhóm dịch vụ |
| P02 | Actor, tenant, object, identity và ngoại lệ có nguồn tin cậy | Mapping quyền và ca kiểm tra scope | Nhóm dịch vụ và phụ trách quyền |
| P03 | Mọi đường vào tạo tác động đã được kiểm soát | Danh sách route/consumer/tool và kết quả tương ứng | Nhóm dịch vụ |
| P04 | State, revision và approval binding được cưỡng chế | Ca bỏ bước, sửa nội dung, cạnh tranh | Nhóm dịch vụ và kiểm thử |
| P05 | Transaction bảo vệ cả tài nguyên tổng cần thiết | Thiết kế đồng thời và kết quả race | Nhóm dịch vụ và dữ liệu |
| P06 | Operation/key/fingerprint/retention có hợp đồng chống trùng | Ca retry, key xung đột, execution trùng | Nhóm dịch vụ |
| P07 | Provider timeout, callback và đối soát có đường xử lý | Kịch bản lỗi và bằng chứng phục hồi | Nhóm tích hợp |
| P08 | Code, schema, policy, config và worker tương thích | Manifest phiên bản, migration, kiểm tra mixed-version | Nhóm phát hành và dữ liệu |
| P09 | Request đang dở, outbox, queue và DLQ có cách xử lý | Kiểm kê phạm vi và hợp đồng chuyển tiếp | Nhóm dịch vụ và vận hành |
| P10 | Audit, metric, đối soát và cảnh báo quan sát được | Dashboard/query, quyền truy cập và chủ nhận cảnh báo | Nhóm vận hành |
| P11 | Cohort, shadow, điều kiện mở rộng và dừng rõ ràng | Kế hoạch kích hoạt và tiêu chí theo tác động | Nhóm phát hành và chủ nghiệp vụ |
| P12 | Kill switch, rollback/roll-forward và repair khả thi | Runbook, kết quả diễn tập phù hợp và người có quyền | Nhóm vận hành và dịch vụ |
| R01 | Trước mở cohort: runtime thực tế dùng đúng artifact/policy | Quan sát phiên bản tại API, worker và binding dữ liệu | Nhóm phát hành |
| R02 | Trước mở rộng: không có vi phạm trọng yếu chưa xử lý | Đối soát, reason, backlog và kết quả canary đủ phạm vi | Chủ cổng phát hành |
| R03 | Trước kết thúc chuyển tiếp: tác động trễ và lệnh cũ đã được quản lý | Danh sách operation/queue còn lại cùng chủ xử lý | Nhóm dịch vụ và vận hành |

Với mỗi hàng, thêm kết quả, thời điểm, liên kết bằng chứng và hành động khi không đạt. Không đánh dấu toàn bộ P01–P12 là đạt bằng một kết quả build xanh. Không để R03 bị bỏ quên chỉ vì đã mở hết traffic.

Một hồ sơ quyết định tối thiểu có thể viết như sau:

~~~yaml
# Mẫu minh họa; không khẳng định môi trường nào đã đạt.
change_id: refund-two-checkers-example
candidate_policy: refund.execute.r9
artifact_identity: TO_BE_RECORDED
schema_compatibility_evidence: TO_BE_LINKED
cohort_definition: TO_BE_RECORDED
in_flight_contract: TO_BE_LINKED
gate: before_first_cohort
result: NOT_EVALUATED
required_evidence:
  - invariant_and_scope_contract
  - attack_and_concurrency_scenarios
  - mixed_version_and_migration_checks
  - idempotency_and_provider_reconciliation
  - observation_stop_and_recovery_readiness
open_blockers: TO_BE_ASSESSED
decision_owner: TO_BE_ASSIGNED
observation_window: TO_BE_DEFINED
stop_action: TO_BE_LINKED
recovery_runbook: TO_BE_LINKED
~~~

### 10.1. Ví dụ quyết định khi thiếu một điều kiện

Giả sử kết quả kiểm tra trước phát hành cho thấy API r9 đã yêu cầu hai checker, nhưng còn một consumer r8 có thể nhận lệnh từ cùng queue và gửi provider chỉ dựa vào state `APPROVED`.

Hàng P08/P09 chưa đạt dù các ca HTTP đều xanh. Quyết định là chưa kích hoạt r9 trên phạm vi mà consumer cũ có thể xử lý. Việc cần hoàn thành là cập nhật consumer hoặc tạo ranh giới cưỡng chế để consumer đó không thể nhận/thực thi operation r9, rồi bổ sung bằng chứng qua đường queue. Thêm cảnh báo cho consumer cũ không đủ thay thế việc ngăn tác động.

Nếu trong canary xuất hiện một execution ở trạng thái chưa rõ sau timeout provider, không kết luận ngay r9 sai hoặc operation thất bại. Giữ định danh operation, đối soát theo runbook và đánh giá điều kiện dừng đã định nghĩa. Nếu xác nhận đã tạo hai khoản hoàn tiền trái hợp đồng, cô lập đường gây lỗi, dừng mở rộng và xử lý tác động đã xảy ra; không chữa bằng cách xóa một dòng local.

## 11. Những lỗi checklist thường che khuất

- **Chỉ kiểm tra thao tác trên UI:** bỏ sót API cũ, consumer, callback và công cụ repair.
- **Chỉ kiểm tra role:** không ràng buộc actor với tenant, object, maker/checker và revision.
- **Có transaction nên coi là an toàn:** bỏ sót tài nguyên tổng, race hoặc tác động provider ngoài transaction.
- **Có idempotency key nên cho retry tùy ý:** không kiểm tra scope, fingerprint, thời hạn hoặc danh tính operation.
- **Shadow không có khác biệt nên mở toàn bộ:** chưa có bằng chứng thực thi transition, retry và phục hồi.
- **Canary ít lỗi nên coi là đạt:** không biết đã gặp nhánh giá trị cao, job trễ hoặc timeout hay chưa.
- **Rollback là quay binary về trước:** quên policy cũ, dữ liệu mới và các khoản provider đã thực hiện.
- **Dùng quyền quản trị để vượt rule khi có backlog:** chuyển sự cố vận hành thành lạm dụng logic nghiệp vụ.
- **Đánh dấu đạt mà không có bằng chứng:** người trực sau không thể xác định phiên bản và phạm vi đã kiểm tra.

Một production rule checklist hữu ích phải dẫn từ bất biến đến nơi cưỡng chế, bằng chứng và hành động vận hành cụ thể. Với bảo mật logic nghiệp vụ, điều kiện để tiếp tục phát hành là giữ đúng quyền, state, giá trị, số lần tác động và khả năng xử lý khi chưa biết kết quả; health check xanh chỉ đóng góp một phần bằng chứng.
