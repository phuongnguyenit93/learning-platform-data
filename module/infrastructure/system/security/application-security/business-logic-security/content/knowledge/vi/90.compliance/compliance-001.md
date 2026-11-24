# Control objective mapping

## 1. Ánh xạ mục tiêu kiểm soát để làm gì?

Trong chương **Compliance**, control objective mapping là việc liên kết các yêu cầu cần đáp ứng với mục tiêu kiểm soát, cơ chế thực thi và bằng chứng cho thấy cơ chế đó bảo vệ đúng quy tắc nghiệp vụ trong phạm vi đã xác định.

Với bảo mật logic nghiệp vụ, một nhãn như “đã có phân quyền” chưa trả lời được hệ thống có chặn người dùng hoàn tiền cho đơn của người khác hay không. Một dòng “có idempotency” cũng chưa chứng minh rằng retry sau timeout không tạo hai khoản hoàn. Ánh xạ tốt biến những khẳng định chung đó thành chuỗi có thể kiểm tra:

```text
Yêu cầu -> Rủi ro -> Mục tiêu kiểm soát -> Invariant nghiệp vụ
        -> Kiểm soát cụ thể -> Đường thực thi -> Kiểm thử và bằng chứng
```

Kết quả giúp đội phát triển biết phải bảo vệ điều gì, người vận hành biết phải theo dõi gì và người đánh giá có thể lần ngược từ kết luận về bằng chứng. Bảng ánh xạ chỉ ghi tên công nghệ mà không chỉ ra hành vi được ngăn chặn sẽ khó phát hiện lỗ hổng thực tế.

Bài học sử dụng một hệ thống hoàn tiền giả định. Mọi mã yêu cầu, mục tiêu và kiểm soát trong bài là **mã nội bộ minh họa**. Chúng không phải số điều khoản của một tiêu chuẩn, quy định hay chứng nhận bên ngoài. Khi tổ chức cần ánh xạ tới một bộ yêu cầu cụ thể, phải dùng đúng tài liệu, phiên bản, phạm vi áp dụng và cách diễn giải đã được người có trách nhiệm xác nhận.

## 2. Phân biệt yêu cầu, mục tiêu, invariant và kiểm soát

| Thành phần | Trả lời điều gì? | Ví dụ trong luồng hoàn tiền |
| --- | --- | --- |
| Requirement — yêu cầu | Tổ chức cần đáp ứng điều gì và trong phạm vi nào? | Chỉ người được phép mới được thực hiện hoàn tiền của tenant mình |
| Risk — rủi ro | Hành vi nào có thể gây tổn thất? | Nhân viên thay payment ID để hoàn tiền giao dịch của tenant khác |
| Control objective — mục tiêu kiểm soát | Kết quả bảo vệ nào cần đạt? | Mọi lệnh hoàn tiền được ràng buộc với quyền trên giao dịch đích |
| Business invariant | Điều kiện nghiệp vụ nào luôn phải đúng? | Actor có quyền thao tác payment trong đúng tenant ở thời điểm quyết định |
| Control — kiểm soát | Cơ chế nào duy trì hoặc phát hiện vi phạm điều kiện đó? | Kiểm tra quyền theo payment, tenant và thao tác trên máy chủ |
| Implementation — triển khai | Kiểm soát nằm ở đâu, được bật như thế nào? | Guard trong command handler dùng chung cho API và worker quản trị |
| Test — kiểm thử | Làm sao chủ động kiểm tra kiểm soát? | Gửi refund với payment của tenant khác và xác nhận không có side effect |
| Evidence — bằng chứng | Điều gì chứng minh thiết kế và hoạt động trong phạm vi đánh giá? | Kết quả test gắn build, cấu hình thực tế, dấu vết quyết định và giao dịch |

Mục tiêu mô tả **kết quả**, còn kiểm soát mô tả **cách thực hiện**. “Sử dụng annotation phân quyền” là một lựa chọn triển khai; “ngăn mọi refund vượt quyền trên giao dịch đích” mới là kết quả cần bảo vệ.

Một mục tiêu có thể cần nhiều kiểm soát. Chẳng hạn, chống hoàn tiền lặp cần khóa yêu cầu ở API, định danh ổn định khi gọi provider, ràng buộc dữ liệu, xử lý kết quả lặp và đối soát khi chưa rõ kết quả. Ngược lại, một kiểm soát quyền theo đối tượng có thể hỗ trợ nhiều mục tiêu ở các thao tác tạo, duyệt, hủy và xem hoàn tiền.

Việc ánh xạ vì vậy thường là quan hệ nhiều-nhiều. Không ép một ô kiểm soát thành lời giải đầy đủ cho mọi yêu cầu có chứa từ “access”, “transaction” hoặc “audit”.

## 3. Ví dụ nghiệp vụ và các điều kiện phải bảo vệ

Giả sử hệ thống có chính sách nội bộ sau:

- Hoàn tiền chỉ áp dụng cho khoản thu đã xác nhận và đúng tenant.
- Mỗi lệnh phải có người yêu cầu và người có quyền duyệt theo mức tiền. Khoản hoàn trên **1.000.000 VND** cần quản lý độc lập phê duyệt; người yêu cầu không được tự duyệt.
- Phê duyệt gắn với đúng giao dịch gốc, số tiền, tiền tệ và phiên bản yêu cầu. Thay đổi dữ liệu đã được duyệt phải đi qua quy trình phù hợp trước khi thực hiện.
- Tổng tiền đã hoàn cùng phần tiền đang giữ chỗ cho refund chưa kết thúc không vượt khoản thu hợp lệ có thể hoàn.
- Gửi lại cùng một ý định hoàn tiền không tạo một khoản hoàn độc lập khác.
- Mọi chuyển trạng thái quan trọng và kết quả tiền tệ phải có dấu vết để đối soát.

Các ngưỡng và điều kiện này là giả định của ví dụ, không phải quy tắc chung cho mọi sản phẩm.

Với mô hình đơn giản chưa có phí, tranh chấp hoặc điều chỉnh khác:

```text
available_to_refund = captured_amount
                    - confirmed_refunded_amount
                    - reserved_pending_or_unknown_refund_amount
```

Ví dụ đã thu 2.000.000 VND, đã hoàn 300.000 VND và có một refund 200.000 VND chưa rõ kết quả. Phần còn có thể giữ chỗ cho yêu cầu mới là 1.500.000 VND. Yêu cầu 1.200.000 VND vừa phải qua kiểm tra ngân sách này vừa cần quản lý độc lập duyệt. Yêu cầu 1.600.000 VND phải bị chặn vì vượt phần còn lại, kể cả khi có phê duyệt quản lý.

Khi refund thành công, transaction nội bộ phải chuyển phần giữ chỗ sang số đã hoàn mà không tính hai lần. Chỉ giải phóng phần giữ chỗ khi đã xác minh không có khoản hoàn được thực hiện. Timeout không phải bằng chứng đủ để giải phóng, vì provider có thể đã hoàn tiền rồi nhưng phản hồi bị mất.

Tiền được biểu diễn bằng số nguyên theo đơn vị mà tích hợp quy định. Máy chủ lấy khoản thu và số đã hoàn từ nguồn đáng tin cậy; không nhận tổng tiền còn lại do client tự tính làm căn cứ quyết định.

## 4. Quy trình xây dựng ánh xạ

### 4.1. Chốt phạm vi trước khi kết luận độ bao phủ

Phạm vi cần nêu sản phẩm, tenant hoặc loại tenant liên quan, môi trường, phiên bản dịch vụ, giai đoạn nghiệp vụ và thời kỳ đánh giá. Liệt kê toàn bộ đường có thể tạo cùng hiệu ứng:

- API người dùng và API quản trị.
- Worker nhận message hoặc webhook.
- Tác vụ theo lô, công cụ hỗ trợ và script vận hành.
- Đường phục hồi sau sự cố hoặc đối soát.

Hai đường cùng gọi provider nhưng chỉ một đường đi qua command handler có kiểm soát là một khoảng trống. Ẩn nút hoàn tiền trên giao diện không bảo vệ đường API, script hoặc message có thể được gọi trực tiếp.

### 4.2. Viết mục tiêu kiểm tra được

Một mục tiêu hữu ích nêu đối tượng, hành vi và kết quả mong đợi. So sánh:

| Mô tả quá chung | Mô tả có thể kiểm tra |
| --- | --- |
| Hệ thống phải an toàn | Refund chỉ được thực hiện trên payment mà actor có quyền thao tác trong đúng tenant |
| Có phê duyệt | Refund trên ngưỡng chỉ chuyển sang thực hiện nếu phê duyệt độc lập khớp phiên bản payload |
| Có transaction | Hai yêu cầu đồng thời không giữ chỗ vượt phần tiền có thể hoàn |
| Có log | Có thể truy ngược một refund từ yêu cầu, phê duyệt, lệnh provider đến kết quả ghi sổ |

Không cần mọi invariant trở thành một công thức. Tuy nhiên, phải có cách quan sát điều kiện đúng hoặc sai và xác định tác động khi nó bị phá vỡ.

### 4.3. Tìm cơ chế và bằng chứng ở từng đường thực thi

Với mỗi mục tiêu, xác định nơi thực thi, chủ sở hữu, điều kiện kích hoạt, xử lý đồng thời, hành vi khi dependency lỗi và các lối đi ngoại lệ. Sau đó liên kết test cùng bằng chứng phù hợp.

Đánh dấu mức hỗ trợ của từng liên kết, chẳng hạn:

- `DIRECT`: kiểm soát trực tiếp thực thi một phần điều kiện bảo vệ đã nêu.
- `SUPPORTING`: hỗ trợ phát hiện, vận hành hoặc xác minh, nhưng không tự duy trì invariant.
- `PARTIAL`: phạm vi hoặc điều kiện chỉ được bao phủ một phần, có giới hạn cụ thể.
- `UNMAPPED`: chưa có kiểm soát phù hợp hoặc chưa xác định được nơi thực thi.

Đây là quy ước nội bộ cần định nghĩa nhất quán. Một liên kết `DIRECT` không tự chứng minh toàn bộ mục tiêu đã đạt; mục tiêu còn có thể cần nhiều điều kiện và nhiều đường xử lý khác.

## 5. Ma trận ánh xạ cho luồng hoàn tiền

Bảng dưới mô tả các thành phần chính. Các kiểm soát là một tập phối hợp; cột bằng chứng chỉ nêu loại bằng chứng cần có, không khẳng định hệ thống giả định đã cung cấp chúng.

| Mục tiêu nội bộ | Invariant cần bảo vệ | Kiểm soát trực tiếp chủ yếu | Kiểm thử và bằng chứng cần liên kết |
| --- | --- | --- | --- |
| `OBJ-AUTHZ` — quyền đúng đối tượng | Actor có quyền hoàn payment của đúng tenant | `C-OBJECT-AUTHZ`: kiểm tra quyền ở server trên đối tượng đã resolve, áp dụng cho mọi command entry point | Test khác tenant, khác owner, vai trò bị thu hồi; cấu hình và dấu vết quyết định có object reference |
| `OBJ-APPROVAL` — phê duyệt đúng ý định | Khoản trên ngưỡng có người duyệt độc lập và payload còn khớp | `C-APPROVAL-BINDING`: tách người yêu cầu/người duyệt, ràng buộc approval với phiên bản và dữ liệu quan trọng | Test tự duyệt, đổi amount sau duyệt, dùng lại approval của refund khác; bản ghi duyệt và phiên bản yêu cầu |
| `OBJ-LIMIT` — không vượt phần tiền hợp lệ | Tổng hoàn đã xác nhận và giữ chỗ không vượt khoản thu có thể hoàn | `C-REFUND-RESERVATION`: tính tiền phía server, giữ chỗ nguyên tử bằng khóa hoặc cập nhật có điều kiện | Test hai refund đồng thời; bằng chứng transaction, số dư trước/sau và đối soát provider |
| `OBJ-STATE` — chuyển bước hợp lệ | Chỉ refund đủ điều kiện mới đi tới lệnh thực hiện | `C-STATE-GUARD`: state machine phía server, kiểm tra phiên bản và điều kiện khi chuyển trạng thái | Test gọi thẳng bước submit, submit sau hủy, xử lý thông báo cũ; lịch sử chuyển trạng thái |
| `OBJ-ONCE` — không tạo khoản hoàn trùng | Một ý định chỉ tạo một hiệu ứng hoàn tiền hợp lệ | `C-REQUEST-DEDUPE`, `C-PROVIDER-IDEMPOTENCY`, `C-RESULT-DEDUPE` và `C-RECONCILIATION` phối hợp | Test retry, mất phản hồi, worker chết, callback lặp; định danh operation, khoản hoàn provider và ghi sổ nội bộ |
| `OBJ-TRACE` — giải thích được giao dịch | Có thể liên kết người yêu cầu, người duyệt, quyết định và kết quả | `C-AUDIT-LINKAGE`: lưu liên kết có kiểm soát truy cập; bảo vệ lịch sử cần thiết | Test truy vết một refund xuyên suốt, kiểm tra dữ liệu thiếu và quyền sửa log; manifest cùng mẫu audit được rà soát |

Ví dụ `C-AUDIT-LINKAGE` hỗ trợ điều tra `OBJ-AUTHZ`, nhưng audit log không trực tiếp ngăn refund vượt quyền. Không thay thế kiểm soát phòng ngừa bằng log rồi tuyên bố hai cơ chế có hiệu lực tương đương.

Nếu cần ánh xạ sang bộ yêu cầu bên ngoài, thêm quan hệ riêng:

```text
requirement_source + requirement_version + requirement_id
    -> phạm vi và cách diễn giải đã xác nhận
    -> objective_id
    -> control_id cùng mức hỗ trợ và giới hạn
```

Giữ trích dẫn hoặc tham chiếu đủ để người đánh giá tìm đúng yêu cầu. Không lấy một mã điều khoản từ phiên bản khác, tìm từ khóa giống nhau rồi mặc định kiểm soát kỹ thuật đáp ứng đầy đủ nghĩa vụ của điều khoản đó. Một yêu cầu có thể bao gồm quy trình quản trị, con người hoặc đánh giá định kỳ ngoài phạm vi mã nguồn.

## 6. Đặc tả kiểm soát đủ cụ thể để kiểm tra

Mỗi kiểm soát cần có ít nhất: mục tiêu hỗ trợ, rủi ro xử lý, phạm vi, nơi thực thi, chủ sở hữu, điều kiện đúng/sai, hành vi khi lỗi, test, bằng chứng và giới hạn đã biết.

Ví dụ hồ sơ sau tập trung vào chống lặp ở phía provider. YAML là nội dung minh họa của bài học, không phải metadata trạng thái của bài:

```yaml
control_id: C-PROVIDER-IDEMPOTENCY
objective_ids:
  - OBJ-ONCE
mapping_strength: PARTIAL
scope:
  operation: execute_refund
  environment: production
  paths:
    - refund_worker
    - refund_recovery_worker
owner_role: payments_engineering
rule:
  key_created_before_first_send: true
  key_stable_per_refund_operation: true
  provider_payload_immutable: true
  check_provider_retention_contract: true
failure_behavior:
  uncertain_result: keep_unknown_and_reconcile
  protection_window_expired: do_not_resend_without_resolution
test_refs:
  - T-REFUND-TIMEOUT-AFTER-EFFECT
  - T-REFUND-WORKER-RESTART
  - T-REFUND-KEY-EXPIRY
evidence_refs:
  - provider_contract_version
  - build_bound_test_result
  - sampled_operation_to_provider_reconciliation
known_limits:
  - does_not_authorize_the_user
  - does_not_prevent_a_second_distinct_business_operation
  - requires_result_deduplication_and_reconciliation
```

Những giá trị `true` trong hồ sơ là yêu cầu thiết kế cần xác minh, không phải bằng chứng thực thi. Cần kiểm tra khóa đã được lưu bền vững trước lần gọi mạng đầu tiên, payload thật sự bất biến và phạm vi bảo vệ của provider có đúng như giả định không.

Khi hết thời hạn idempotency mà kết quả refund vẫn chưa rõ, việc gửi lại dưới khóa cũ có thể không còn được chống trùng. Kiểm soát phải chỉ rõ đường đối soát hoặc xử lý ngoại lệ; không tự tạo khóa mới rồi gọi đó là retry an toàn.

Với `C-APPROVAL-BINDING`, hồ sơ cần nêu những trường được ràng buộc: payment gốc, amount, currency, phiên bản yêu cầu và đích hoàn tiền nếu sản phẩm cho phép lựa chọn. Không chỉ lưu một boolean `approved=true` rồi cho phép thay các trường đó trước submit.

Cũng phải định nghĩa mốc hiệu lực của quyền và phê duyệt. Chẳng hạn, quyết định có thẩm quyền được kiểm tra khi chuyển nguyên tử từ `APPROVED` sang chấp nhận lệnh thực hiện và ghi outbox. Nếu cần thu hồi lệnh sau mốc này, phải có quy trình rõ ràng, vì một yêu cầu bên ngoài có thể đã được gửi. Không hứa rằng thay đổi quyền cục bộ luôn có thể hủy một thao tác provider đã thực hiện.

## 7. Gắn kiểm soát với kiểm thử lạm dụng

Kiểm thử cần cố phá điều kiện nghiệp vụ, không chỉ gọi đường thành công. Mỗi test phải liên kết tới mục tiêu và kiểm soát mà nó đánh giá, đồng thời kiểm tra side effect tương ứng.

| Test minh họa | Thao tác thử | Assertion có ý nghĩa |
| --- | --- | --- |
| `T-AUTHZ-CROSS-TENANT` | Actor tenant A gửi refund cho payment tenant B | Không có refund, giữ chỗ hoặc lệnh provider cho payment B; phản hồi không lộ thông tin ngoài quyền |
| `T-APPROVAL-SELF` | Người yêu cầu tự duyệt khoản trên ngưỡng | Chuyển trạng thái bị chặn, không tạo ý định thực hiện |
| `T-APPROVAL-MUTATION` | Duyệt 1.200.000 VND rồi sửa payload thành 1.500.000 VND | Phiên bản phê duyệt cũ không cho phép thực hiện payload mới |
| `T-LIMIT-CONCURRENT` | Hai request cùng tranh phần còn lại 1.500.000 VND và mỗi request đòi 1.000.000 VND | Không thể giữ chỗ đồng thời cả hai khoản nếu tổng vượt ngân sách |
| `T-STATE-SKIP` | Gọi thẳng submit khi thiếu phê duyệt bắt buộc | State guard phía server chặn dù client bỏ qua giao diện |
| `T-REFUND-TIMEOUT-AFTER-EFFECT` | Provider hoàn tiền rồi mất phản hồi; worker retry | Không có khoản hoàn độc lập thứ hai; giữ chỗ không bị giải phóng chỉ vì timeout |
| `T-REFUND-WORKER-RESTART` | Dừng worker sau hiệu ứng provider, trước commit kết quả nội bộ | Khởi động lại dùng định danh đã lưu; đối soát khôi phục một kết quả tiền tệ |
| `T-RESULT-REDELIVERY` | Gửi callback trùng và hai event ID về cùng refund | Ghi sổ một lần, không nhân tiền đã hoàn hoặc phát side effect kép |
| `T-ADMIN-ALTERNATE-PATH` | Thực hiện cùng hành vi qua công cụ hỗ trợ hoặc batch | Các invariant tương đương vẫn được thực thi; ngoại lệ được định nghĩa và kiểm tra riêng |

HTTP 403 trong test quyền là một tín hiệu, nhưng assertion phải xác nhận không có tác động tiền tệ hoặc dữ liệu ngoài quyền. HTTP 200 trong test retry cũng chưa chứng minh không hoàn hai lần: cần kiểm tra sổ provider hoặc fake provider độc lập cùng dữ liệu merchant.

Kiểm thử đồng thời nên dùng barrier để hai thao tác chạm đúng điểm tranh chấp. Kiểm thử giữ chỗ và unique constraint nên có bằng chứng với cơ sở dữ liệu thực của môi trường test. Một mock trả về giá trị mong muốn không kiểm chứng được cơ chế khóa hoặc isolation.

Đối với thông báo đến sai thứ tự, state machine cần giữ sự thật đã xác minh. Ví dụ callback pending đến sau succeeded không được làm refund quay về trạng thái có thể thực hiện lần nữa. Khi kết quả đáng tin cậy mâu thuẫn, cần đối soát và xử lý ngoại lệ, không áp dụng quy tắc “sự kiện đến sau luôn thắng”.

## 8. Bằng chứng thiết kế và bằng chứng vận hành

### 8.1. Đừng đánh đồng bốn kết luận khác nhau

| Kết luận | Bằng chứng phù hợp | Điều chưa được chứng minh |
| --- | --- | --- |
| Kiểm soát đã được thiết kế | Đặc tả invariant, phạm vi, state machine, threat scenario | Mã nguồn thực tế có thực hiện đúng hay không |
| Kiểm soát đã được triển khai | Code reference gắn commit, cấu hình, nơi gọi và điều kiện bật | Build đó đang chạy đúng cấu hình ở production hay không |
| Kiểm soát vượt qua kiểm thử | Test result gắn build, môi trường, dữ liệu và assertion | Hoạt động liên tục trong toàn kỳ đánh giá |
| Kiểm soát hoạt động trong phạm vi vận hành được đánh giá | Bằng chứng triển khai, quan sát theo kỳ, mẫu giao dịch, đối soát và xử lý ngoại lệ | Mọi luồng ngoài phạm vi hoặc mọi thời điểm không có dữ liệu |

Một file test tồn tại trong repository chưa chứng minh test đã chạy. Báo cáo test từ build cũ chưa chứng minh build mới giữ nguyên hiệu lực. Log đầy đủ trong một ngày cũng không tự chứng minh cả quý có cùng cấu hình và độ bao phủ.

### 8.2. Chuỗi bằng chứng cho một refund

Với một operation được lấy mẫu, người đánh giá nên lần được:

```text
Refund request + actor + tenant + payment
  -> quyết định quyền và dữ liệu tiền phía server
  -> approval gắn payload/version khi cần
  -> transaction giữ chỗ và chuyển trạng thái
  -> outbox + provider idempotency key/reference
  -> kết quả provider hoặc trạng thái chưa rõ
  -> ghi sổ + giải quyết giữ chỗ + lịch sử đối soát
```

Điều này không đòi hỏi mọi dữ liệu nằm trong một bảng. Cần liên kết ổn định, có quyền truy cập phù hợp và hiểu nguồn nào chứng minh điều gì. Dòng log “refund started” chỉ chứng minh bước bắt đầu được ghi nhận; nó không xác nhận provider đã hoàn tiền hay transaction đã commit.

Nếu thao tác chưa rõ kết quả, bằng chứng phải thể hiện công việc đối soát đang tồn tại và khoản giữ chỗ còn được bảo vệ. Không thay `UNKNOWN` bằng `FAILED` để làm báo cáo sạch hơn.

### 8.3. Chất lượng, thời kỳ và khả năng kiểm tra lại

Hồ sơ bằng chứng cần ghi nguồn, cửa sổ thời gian, cách chọn mẫu, phiên bản dịch vụ và cấu hình, thời điểm thu thập, kết quả cùng giới hạn. Nếu chỉ lấy mẫu giao dịch thành công, có thể bỏ lỡ refund bị từ chối sai, retry trùng hoặc đường phục hồi bỏ qua quyền.

Chọn mẫu theo rủi ro nên bao gồm trường hợp trên ngưỡng, thao tác quản trị, tenant khác, retry, timeout và xử lý ngoại lệ khi chúng xuất hiện trong kỳ. Không phát sinh trong kỳ không tự chứng minh nhánh đó đúng; có thể cần bằng chứng test phù hợp và phải ghi rõ giới hạn của bằng chứng vận hành.

Bảo vệ bằng chứng khỏi sửa đổi trái phép, giữ tham chiếu nguồn và ghi nhận truy cập. Hash giúp phát hiện bản trích xuất thay đổi sau khi lưu, nhưng không tự chứng minh nguồn ban đầu đúng hoặc đầy đủ. Hạn chế dữ liệu cá nhân và không đưa secret, CVV, token có thể dùng lại hay payload thanh toán nhạy cảm vào bảng ánh xạ.

## 9. Đánh giá độ bao phủ và trách nhiệm chia sẻ

### 9.1. Đếm theo mục tiêu và phạm vi có ý nghĩa

Số hàng trong ma trận không phải thước đo an toàn. Một mục tiêu có mười liên kết log vẫn có thể thiếu kiểm soát trực tiếp. Một kiểm soát có nhiều test tương tự vẫn có thể bỏ sót script quản trị.

Một đơn vị rà soát thực dụng là:

```text
mục tiêu × đường thực thi × môi trường × phiên bản liên quan
```

Với từng đơn vị, ghi riêng:

- Mức hoàn chỉnh của ánh xạ: đã tìm được kiểm soát phù hợp hay còn trống.
- Trạng thái triển khai: đã triển khai và bật trong phạm vi đó hay chưa.
- Kết quả đánh giá: có bằng chứng hiệu lực, có lỗi hoặc chưa đủ dữ liệu.
- Ngoại lệ và rủi ro còn lại: điều gì chưa được bảo vệ, ai chịu trách nhiệm xử lý.

Ví dụ có tám đường tạo refund, bảy đường kiểm tra quyền trên payment, còn script xử lý theo lô chỉ kiểm tra vai trò nhân viên. Tỷ lệ bảy trên tám giúp nhận ra một khoảng trống, nhưng không chứng minh mục tiêu quyền đã đạt ở cấp sản phẩm. Nếu script có thể hoàn tiền không giới hạn cho mọi tenant, đường thiếu đó có mức rủi ro rất lớn dù tỷ lệ có vẻ cao.

Đặt các trạng thái chưa biết cạnh trạng thái lỗi thay vì gộp vào “đạt”. Không có bằng chứng không nhất thiết đồng nghĩa kiểm soát chắc chắn hỏng, nhưng cũng chưa tạo căn cứ kết luận kiểm soát hoạt động hiệu quả.

### 9.2. Kiểm soát dùng chung cần có điều kiện kế thừa

Một command handler dùng chung có thể thực thi quyền và state machine cho nhiều entry point. Muốn kế thừa kết quả đánh giá, cần chứng minh các đường đó thực sự đi qua handler, truyền đúng principal/tenant và không có cờ bỏ qua điều kiện kiểm tra.

Tương tự, một provider hỗ trợ idempotency không tự làm ứng dụng trở nên idempotent. Merchant vẫn chịu trách nhiệm tạo khóa đúng scope, lưu trước khi gửi, giữ nguyên payload, hiểu thời hạn bảo vệ và đối soát kết quả. Nếu retry luôn sinh khóa mới, khả năng chống trùng của provider không được sử dụng cho cùng ý định nghiệp vụ.

Trong bảng ánh xạ, ghi rõ phần trách nhiệm thuộc ứng dụng, nền tảng dùng chung, vận hành và provider. Bằng chứng từ một dịch vụ bên ngoài chỉ hỗ trợ phần nằm trong phạm vi của bằng chứng đó; nó không tự chứng minh kiểm tra quyền, phê duyệt hoặc tính tiền ở merchant là đúng.

### 9.3. Kiểm soát phát hiện không tự thay thế kiểm soát phòng ngừa

Một cảnh báo “có refund vượt ngưỡng” có thể hỗ trợ phát hiện sai lệch, nhưng nếu tiền đã được hoàn trước cảnh báo thì mục tiêu ngăn thực hiện khi thiếu duyệt chưa được bảo vệ trực tiếp. Nếu thiết kế dựa vào phát hiện và can thiệp, phải mô tả độ trễ, hành động chặn hoặc khôi phục cùng rủi ro còn lại.

Rà soát thủ công có thể là một phần của hệ thống kiểm soát, nhưng cần bằng chứng người rà soát có đủ dữ liệu, thẩm quyền, tính độc lập và thực hiện đúng tần suất. Một dòng “ops sẽ kiểm tra” chưa phải cơ chế có thể đánh giá.

## 10. Quản lý khoảng trống và ngoại lệ

Mỗi khoảng trống nên liên kết lại mục tiêu, đường thực thi, rủi ro, kế hoạch sửa, người chịu trách nhiệm và thời hạn. Không chỉ thêm ghi chú chung ở cuối bảng rồi giữ nguyên trạng thái đạt.

| Khoảng trống phát hiện | Ý nghĩa nghiệp vụ | Hướng xử lý cụ thể |
| --- | --- | --- |
| Script quản trị bỏ qua quyền theo payment | Vai trò rộng có thể thao tác sai tenant | Đưa script qua kiểm soát dùng chung; giới hạn khả năng thực hiện trong lúc sửa |
| Approval chỉ gắn với refund ID, amount vẫn sửa được | Người dùng duyệt số nhỏ rồi thực hiện số lớn | Khóa hoặc kiểm tra phiên bản payload; yêu cầu duyệt lại khi dữ liệu quan trọng thay đổi |
| Kiểm tra ngân sách không có bảo vệ đồng thời | Hai request cùng tiêu phần tiền còn lại | Giữ chỗ nguyên tử, ràng buộc dữ liệu và test cạnh tranh trên database |
| Retry refund tạo provider key mới | Timeout có thể dẫn đến khoản hoàn độc lập thứ hai | Lưu khóa theo operation trước khi gọi; giữ trạng thái chưa rõ và đối soát |
| Chỉ có log khởi tạo refund | Không biết khoản tiền đã được thực hiện hay chưa | Bổ sung liên kết kết quả provider, ghi sổ và đối soát |
| Bằng chứng không bao phủ một vùng triển khai | Chưa biết cấu hình vùng đó có đúng hay không | Thu thập cấu hình, phiên bản và test/quan sát phù hợp với vùng còn thiếu |

Trong ví dụ script quản trị, biện pháp tạm thời có thể là chặn chức năng refund của script và chuyển các yêu cầu cần thiết qua luồng đã có kiểm soát. Nếu tổ chức chọn một biện pháp bù khác, cần chỉ rõ nó hỗ trợ mục tiêu nào, có giới hạn gì và bằng chứng vận hành ra sao.

Hồ sơ ngoại lệ thường cần: phạm vi, lý do, tác động có thể xảy ra, thời hạn, biện pháp giảm thiểu, chủ thể có thẩm quyền chấp nhận và điều kiện xem xét lại. Không để người triển khai tự ghi “chấp nhận rủi ro” thay cho quyết định đúng thẩm quyền.

Chấp nhận rủi ro không biến invariant bị vi phạm thành invariant đã được bảo vệ. Nó cũng không tự chứng minh yêu cầu bên ngoài cho phép ngoại lệ đó. Trong báo cáo, tách rõ tình trạng kiểm soát, quyết định xử lý rủi ro và kết luận đáp ứng yêu cầu.

## 11. Duy trì ánh xạ khi hệ thống thay đổi

Bảng ánh xạ cần được rà soát khi có thay đổi ảnh hưởng điều kiện bảo vệ, chẳng hạn:

- Thêm endpoint, worker, script hoặc đường phục hồi mới.
- Đổi ngưỡng duyệt, loại tiền tệ, mô hình tenant hoặc quyền ủy nhiệm.
- Thay provider, hợp đồng idempotency hoặc quy trình đối soát.
- Chuyển refund từ đồng bộ sang bất đồng bộ, thêm retry hoặc queue.
- Thay schema, isolation, cơ chế khóa hay nơi tính phần tiền có thể hoàn.
- Có sự cố hoặc kết quả test chứng minh một giả định cũ không đúng.

Một vòng cập nhật thực dụng gồm:

1. Xác định requirement, objective và invariant nào bị thay đổi.
2. Liệt kê các entry point và kiểm soát bị ảnh hưởng, kể cả thành phần dùng chung.
3. Cập nhật thiết kế, triển khai, test và giới hạn của ánh xạ.
4. Liên kết bằng chứng mới với build/cấu hình đã triển khai.
5. Ghi nhận phần chưa đánh giá lại và xử lý khoảng trống trước khi đưa ra kết luận mới.

Nếu chỉ đổi chính sách ngưỡng tiền từ 1.000.000 sang 2.000.000 VND, vẫn phải kiểm tra giá trị nào áp dụng cho yêu cầu đã tạo, phê duyệt đã cấp và worker đang chờ. Không để API dùng chính sách mới nhưng worker dùng ngưỡng cũ mà ma trận chỉ ghi chung “có approval”.

Với bằng chứng nhiều thời điểm, giữ phiên bản chính sách và khoảng hiệu lực. Có thể cần phân tích riêng trước và sau thay đổi thay vì dùng một ảnh chụp cấu hình cuối kỳ để mô tả toàn bộ thời kỳ.

Luôn kiểm tra theo cả hai hướng:

- Từ yêu cầu xuống triển khai: mỗi phần mục tiêu có kiểm soát, test và bằng chứng thích hợp không?
- Từ đường thực thi lên mục tiêu: endpoint, worker hoặc script nào tạo hiệu ứng nhạy cảm nhưng chưa nằm trong phạm vi ánh xạ?

Hướng thứ hai đặc biệt hữu ích với business logic security, vì một đường đi ngoại lệ có thể bỏ qua toàn bộ lớp bảo vệ của luồng chính.

## 12. Bài thực hành và tiêu chí hoàn thành

Hãy lập ánh xạ cho luồng hoàn tiền của ví dụ với ba đường: API quản trị, worker thực hiện refund và script khôi phục. Giả sử API đã kiểm tra quyền theo payment, worker dùng khóa provider ổn định, nhưng script nhận trực tiếp payment ID và amount từ người vận hành rồi gọi provider.

Sản phẩm thực hành cần thể hiện:

1. Phạm vi, giả định nghiệp vụ và các entry point có thể tạo hiệu ứng.
2. Các mục tiêu về quyền, phê duyệt, giới hạn tiền, trạng thái, chống lặp và truy vết.
3. Invariant, kiểm soát, mức hỗ trợ và chủ sở hữu cho từng mục tiêu.
4. Những liên kết thiếu hoặc chỉ bao phủ một phần, đặc biệt ở script khôi phục.
5. Test lạm dụng có assertion về dữ liệu và side effect, không chỉ mã HTTP.
6. Loại bằng chứng cần thu thập để đánh giá thiết kế, triển khai và vận hành.
7. Kế hoạch xử lý khoảng trống, ngoại lệ nếu có và điều kiện đánh giá lại.

Một nhận định phù hợp là: “Worker có cơ chế idempotency hỗ trợ chống gửi lặp của cùng operation; chưa đủ kết luận toàn luồng không hoàn tiền trùng vì script tạo operation riêng và thiếu đối soát.” Nhận định này mô tả được phần đã có và phần còn thiếu mà không suy diễn từ một tính năng đơn lẻ.

Trước khi hoàn thành ma trận, kiểm tra rằng người đọc có thể chọn bất kỳ mục tiêu nào và lần tới đúng kiểm soát, đường thực thi, test cùng bằng chứng. Họ cũng phải nhìn thấy các khoảng chưa biết, đường ngoại lệ và rủi ro còn lại. Một ánh xạ có giá trị là bản mô tả kiểm chứng được về cách hệ thống bảo vệ nghiệp vụ trong phạm vi cụ thể.
