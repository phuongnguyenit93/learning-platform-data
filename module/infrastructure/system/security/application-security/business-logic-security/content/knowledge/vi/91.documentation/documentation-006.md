# Operational runbook — Hướng dẫn vận hành bảo vệ logic nghiệp vụ

## 1. Mục tiêu của runbook trong bảo mật logic nghiệp vụ

Trong chương **Documentation**, **operational runbook** là tài liệu hướng dẫn người vận hành thực hiện một công việc có điều kiện bắt đầu, phạm vi, thẩm quyền, các bước thao tác, kết quả mong đợi, điểm dừng và bằng chứng xác nhận.

Với bảo mật logic nghiệp vụ, mục tiêu không chỉ là đưa dịch vụ trở lại trạng thái trả HTTP 200. Runbook phải giúp xử lý sự cố mà vẫn giữ đúng quyền theo đối tượng, giá trị được phê duyệt, state machine, ngân sách giao dịch và idempotency.

Ví dụ, hệ thống phát hiện một nghĩa vụ hoàn tiền có thể được thực hiện nhiều lần qua API và worker. Người trực ca cần biết cách ngăn tác dụng mới, xác định khoản nào đã hoàn tất, giữ nguyên nhận diện lệnh khi kết quả chưa rõ và phục hồi backlog mà không tạo thêm hoàn tiền trùng.

Sau bài học, bạn có thể:

- Phân biệt runbook với mô tả kiến trúc, playbook điều tra và bản ghi incident.
- Viết bước vận hành có đầu vào, kết quả kỳ vọng và cách readback độc lập.
- Thiết kế quy trình cho sự cố bỏ qua phê duyệt, sửa giá, sai quyền và xử lý lặp.
- Giữ đúng ranh giới transaction local và tác dụng tại nhà cung cấp ngoài.
- Xác định điều kiện dừng, escalation, rollback và hành động bù.
- Kiểm thử runbook, quản lý version và bàn giao để người khác tiếp tục an toàn.

Bài sử dụng một tình huống hoàn tiền để minh họa. Tên bảng, request điều khiển, trạng thái và công cụ trong ví dụ là hợp đồng giả định; cần thay bằng thành phần đã được kiểm chứng của hệ thống trước khi dùng trong vận hành thực tế.

## 2. Runbook trả lời câu hỏi nào?

### 2.1. Tách tài liệu hướng dẫn khỏi trạng thái sự cố

| Tài liệu | Câu hỏi chính |
| --- | --- |
| Kiến trúc và thiết kế | Hệ thống được cấu thành và bảo vệ bởi những cơ chế nào? |
| Đặc tả quy tắc nghiệp vụ | Điều gì được phép, bởi ai, với dữ liệu và trạng thái nào? |
| Playbook | Khi có loại dấu hiệu này, cần điều tra và ra quyết định theo những nhánh nào? |
| Runbook | Với tình huống và điều kiện đã xác định, thực hiện từng bước thế nào, kiểm tra gì, khi nào dừng? |
| Bản ghi incident | Trong lần xử lý này, ai đã làm gì, kết quả nào thực sự được quan sát? |
| Báo cáo sau sự cố | Vì sao xảy ra, tác động là gì và cần thay đổi điều gì? |

Một runbook có thể được playbook gọi tới. Ví dụ, nhánh “nghi hoàn tiền trùng” chọn runbook khoanh vùng và đối soát hoàn tiền. Runbook không nên bắt người trực ca tự đọc toàn bộ source code để đoán lệnh cần dùng.

Tài liệu hướng dẫn có version riêng. Bản ghi incident phải ghi version runbook đã sử dụng cùng các sai lệch thực tế; không sửa tài liệu rồi làm mất khả năng biết người vận hành đã nhìn thấy hướng dẫn nào.

### 2.2. Một bước phải có thể đánh giá kết quả

“Kiểm tra dữ liệu và xử lý queue” không đủ để thực hiện an toàn. Một bước tốt cần cho biết:

1. Mục đích và điều kiện trước khi chạy.
2. Môi trường, tenant, đối tượng và version đang nhắm tới.
3. Quyền cần có và căn cứ thực hiện.
4. Thao tác hoặc công cụ đã được kiểm chứng.
5. Dữ liệu đầu ra mong đợi.
6. Cách kiểm tra sau thao tác.
7. Hành vi khi timeout, kết quả không khớp hoặc phát hiện rủi ro mới.
8. Bằng chứng cần ghi vào incident.

Điều kiện “không đủ dữ liệu để tiếp tục” cũng là một kết quả hợp lệ. Runbook phải có nhánh giữ trạng thái an toàn và escalation thay vì buộc operator chọn thành công hoặc thất bại chắc chắn.

## 3. Xác định bất biến và ranh giới tác dụng

### 3.1. Những điều phải tiếp tục đúng trong khi vận hành

Với hoàn tiền, có thể đặt:

| ID | Bất biến cần giữ |
| --- | --- |
| O1 | Một nghĩa vụ không tạo hai tác dụng hoàn tiền ngoài hợp đồng |
| O2 | Tổng đã hoàn và còn có thể hoàn tất từ reservation không vượt số tiền đủ điều kiện |
| O3 | Chỉ người có quyền trên tenant và đối tượng được thực hiện hành động |
| O4 | Approval phải áp dụng cho đúng revision số tiền, tiền tệ và người thụ hưởng |
| O5 | Freeze có hiệu lực phải chặn lần thực thi local mới trong phạm vi đã cam kết |
| O6 | Timeout không tự chứng minh provider chưa nhận lệnh |
| O7 | Replay không đổi nghĩa vụ, payload hoặc idempotency key tùy tiện |
| O8 | Dữ liệu và audit không bị sửa để che hoặc hợp thức hóa sai lệch |
| O9 | Phục hồi không làm sống lại quyền, token hoặc approval đã hết hiệu lực |

Runbook cần tham chiếu những bất biến liên quan ở từng bước. Ví dụ, khi cân nhắc giải phóng reservation của lệnh UNKNOWN, O2 và O6 là điều kiện quyết định, không chỉ là lời nhắc chung về cẩn thận.

### 3.2. Phân biệt các loại “đã xong”

```text
Đã nhận yêu cầu điều khiển
!= thay đổi điều khiển đã commit
!= mọi worker đã tuân theo thay đổi
!= mọi attempt bên ngoài đã dừng
!= dữ liệu và tác động đã được đối soát
```

Nếu runbook dùng nút freeze, cần biết nó chặn tiếp nhận, allocation, dispatch hay tác dụng local nào. Không dùng một thông báo “request accepted” để kết luận không còn giao dịch đang bay.

Tương tự, queue rỗng không chứng minh mọi nghĩa vụ đã hoàn tất. Job có thể bị xóa, đẩy sang dead-letter hoặc chuyển thành trạng thái UNKNOWN.

## 4. Metadata, quyền và công cụ cần chuẩn bị

### 4.1. Thông tin nhận diện một runbook

Một mẫu phần đầu:

```text
Runbook ID: BLS-RB-REFUND-DUPLICATE
Purpose: khoanh vùng và phục hồi sự cố hoàn tiền trùng
Owner: đội chịu trách nhiệm nghiệp vụ và vận hành
Version: version tài liệu đã được duyệt
Verified against: build, policy version, schema và tool version
Last exercised: thời điểm/lần diễn tập có bằng chứng
Review trigger: thay API, state machine, provider, quyền hoặc policy
Scope: loại hành động và môi trường hỗ trợ
Entry conditions: dấu hiệu đủ để dùng quy trình
Excluded cases: tình huống phải chuyển runbook khác
Escalation route: vai trò trực ca và phương thức đã kiểm chứng
Evidence location: kho có quyền truy cập phù hợp
```

Các giá trị cần được điền và kiểm tra trước khi công bố tài liệu sẵn sàng sử dụng. Link dashboard không còn mở được hoặc tên đội không còn phụ trách là lỗi vận hành của runbook.

Cần có cách truy cập bản đã kiểm chứng khi dịch vụ chính, hệ thống quản trị hoặc đăng nhập thông thường gặp sự cố. Bản dự phòng phải có nguồn tin cậy, version và quyền phù hợp; không dùng một bản sao không rõ xuất xứ.

### 4.2. Vai trò không tự cấp quyền ngoài phạm vi

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident lead | Điều phối, xác định ưu tiên, phạm vi và người chịu trách nhiệm |
| Operations lead/operator | Thực hiện hành động đã được phân quyền, readback và ghi kết quả |
| Business/control owner | Quyết định các lựa chọn nghiệp vụ, ngoại lệ và điều kiện mở lại thuộc thẩm quyền |
| Data/reconciliation owner | Đối soát nghĩa vụ, ledger và bằng chứng provider |
| Communications owner | Cập nhật thông tin qua kênh và đối tượng được phép |
| Reviewer khi policy yêu cầu | Kiểm tra một thay đổi cụ thể trước khi thực hiện |

Tài liệu Google SRE nhấn mạnh phân vai rõ và giữ bản ghi làm việc trong khi xử lý incident. Có thể áp dụng cách tổ chức đó để tránh các nhóm thao tác chồng chéo mà không biết kết quả của nhau. [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/).

Incident lead không mặc định có quyền hoàn tiền hoặc sửa ledger. Quyền ứng phó khẩn cấp, nếu có, cần được chuẩn bị với phạm vi và audit; runbook không tự tạo ra quyền đó.

### 4.3. Kiểm tra công cụ trước khi cần dùng

Công cụ điều khiển nên hỗ trợ đúng tenant, expected version/epoch, command ID, preview phù hợp và kết quả có thể tra cứu. Người vận hành cần biết thao tác nào chỉ đọc, thao tác nào ghi và thao tác nào có tác dụng ngoài hệ thống.

Không lưu credential trong runbook. Tài liệu chỉ chỉ dẫn cách dùng cơ chế cấp quyền/bí mật đã được phê duyệt. Nếu lệnh trả dữ liệu nhạy cảm, cần biết cách ghi bằng chứng bằng tham chiếu hoặc đầu ra đã che dữ liệu.

## 5. Mẫu cấu trúc cho từng procedure

Một procedure có thể dùng bảng sau:

| Trường | Nội dung cần ghi |
| --- | --- |
| Procedure ID | Định danh ổn định để incident tham chiếu |
| Goal | Kết quả cụ thể cần đạt |
| Preconditions | State, dữ liệu, quyền, phạm vi và phụ thuộc bắt buộc |
| Inputs | Các ID đã xác minh, thời gian, version, manifest |
| Diagnostics | Truy vấn/tra cứu chỉ đọc cần làm trước |
| Action | Thao tác cụ thể với tham số bị giới hạn |
| Expected result | Trạng thái hoặc bằng chứng sau thao tác |
| Verification | Readback từ nguồn phù hợp, ngoài kết quả trả về ban đầu |
| Stop conditions | Sai phạm vi, version xung đột, UNKNOWN, bất biến vi phạm hoặc công cụ lỗi |
| Escalation | Giao cho vai trò nào với thông tin gì |
| Rollback/compensation | Khả năng đảo thay đổi local hoặc hành động bù riêng |
| Evidence | Command ID, before/after, actor, version và kết quả |
| Completion | Điều kiện đủ để chuyển bước tiếp theo |

Tham số bắt buộc không được mặc định thành “mọi tenant”. Lệnh phải từ chối input còn placeholder, danh sách rỗng bị hiểu thành toàn bộ hoặc môi trường chưa xác định.

Nếu có preview, phải biết preview đang kiểm tra điều gì và có thật sự không tạo tác dụng không. Preview không giữ nguyên snapshot mãi mãi; lúc apply vẫn cần kiểm tra version và điều kiện hiện tại.

Runbook cũng phải chỉ rõ ai được phép thay đổi phạm vi. Khi operator phát hiện tenant mới bị ảnh hưởng, việc mở rộng cần quyết định và bằng chứng theo policy, không chỉ sửa một biến trong shell rồi chạy tiếp.

## 6. Điều kiện kích hoạt và chẩn đoán ban đầu

### 6.1. Tín hiệu kích hoạt mẫu

Có thể dùng runbook hoàn tiền trùng khi:

- Một refund có bằng chứng nhiều tác dụng tiền ra ngoài mô hình cho phép.
- Hai request cùng dùng ngân sách hoàn tiền dẫn tới vượt số đủ điều kiện.
- API và batch cho kết quả authorization khác nhau trên cùng đối tượng.
- Một yêu cầu đã đổi số tiền/người thụ hưởng nhưng approval cũ vẫn được dùng.
- Tỉ lệ UNKNOWN hoặc replay bất thường cho thấy nguy cơ tạo lệnh trùng.

Ngưỡng cảnh báo, mức độ incident và thời gian escalation cần do tổ chức xác định theo tác động. Không suy ra mức nghiêm trọng chỉ từ số lượng HTTP 500 hoặc một ngưỡng minh họa trong tài liệu.

### 6.2. Những thông tin tối thiểu phải xác minh

Ghi incident ID, môi trường, nguồn cảnh báo, tenant/object đã xác minh, loại hành động, khoảng thời gian điều tra và bất biến có nguy cơ bị phá vỡ.

Đối chiếu actor và tenant từ nguồn có thẩm quyền. Không tin tenant ID hoặc trạng thái chỉ vì nó nằm trong request do người dùng gửi.

Thu thập trước các bằng chứng tối thiểu có thể lấy nhanh. Nếu tác dụng gây hại đang tiếp diễn, không đợi xuất toàn bộ dữ liệu mới ngăn thiệt hại; các hoạt động bảo toàn bằng chứng đầy đủ có thể được phân công song song.

### 6.3. Chẩn đoán theo câu hỏi nghiệp vụ

| Câu hỏi | Nguồn quan sát |
| --- | --- |
| Nghĩa vụ nào bị ảnh hưởng? | Lệnh nghiệp vụ, refund/payment và revision |
| Ai có quyền tại bước liên quan? | Authorization/audit và policy version |
| Nội dung nào được duyệt? | Approval và revision bất biến |
| Tác dụng local nào đã commit? | Reservation, execution, ledger, outbox |
| Provider đã nhận/thực hiện gì? | Operation ID, truy vấn provider, callback đã xác thực |
| Đường nào còn tạo tác dụng mới? | API, batch, dispatcher, worker, replay và công cụ nội bộ |

Log “success” chưa đủ thay cho dữ liệu đã commit hoặc xác nhận provider. Phân biệt phát hiện thực tế, giả thuyết và thông tin chưa biết trong bản ghi incident.

## 7. Procedure A — Khoanh vùng và ngăn tác dụng mới

### 7.1. Mục đích và tiền điều kiện

Mục đích là giảm nguy cơ tác dụng mới trong phạm vi đã xác định, đồng thời giữ dữ liệu để đối soát. Trước thao tác cần có:

- Tenant, loại hành động và môi trường đã được xác minh.
- Người thực hiện có quyền điều khiển phù hợp.
- Hiểu rõ freeze chặn ở đâu và những đường chưa được bảo vệ.
- Expected epoch/version hiện tại cùng command ID cho quyết định cụ thể.

Nếu chưa khoanh vùng đủ mà tác động đang lan, dùng cơ chế đóng rộng hơn đã được chuẩn bị và được phép. Ghi rõ lý do và ảnh hưởng dự kiến.

### 7.2. Hợp đồng request điều khiển minh họa

Đây là dữ liệu giả định để mô tả yêu cầu của công cụ; không phải endpoint hoặc lệnh có sẵn trong hệ thống:

```json
{
  "incidentId": "INC-EXAMPLE-001",
  "tenantId": "TENANT-EXAMPLE-001",
  "operationClass": "MONEY_OUT",
  "action": "FREEZE",
  "expectedEpoch": 41,
  "commandId": "FREEZE-COMMAND-EXAMPLE-001",
  "reasonCode": "SUSPECTED_DUPLICATE_REFUND"
}
```

Công cụ phải kiểm tra quyền, state, version và lưu quyết định theo transaction đã thiết kế. Khi response bị mất, tra cứu cùng command ID trước khi quyết định gửi lại; retry không tự trở thành một quyết định freeze mới.

### 7.3. Readback và tiêu chí hoàn thành

Đọc gate từ nguồn có thẩm quyền sau commit. Ghi scope thực tế, mode, epoch, actor và command ID. Kiểm tra từng đường tạo tác dụng trong scope đã dừng cấp execution/dispatch mới theo cam kết.

Không tạo giao dịch tiền thật tùy ý để thử freeze. Dùng kết quả kiểm chứng đã thiết kế: kiểm tra policy, dữ liệu từ chối của các lệnh thực, probe không tạo tác dụng hoặc cơ chế kiểm thử được chấp thuận.

Nếu readback còn OPEN, epoch khác dự kiến, dữ liệu chỉ từ cache hoặc một worker vẫn cấp lệnh mới, procedure chưa đạt. Giữ thông tin giới hạn và escalation tới người phụ trách control plane/đường thực thi.

### 7.4. Tác dụng đang bay được theo dõi riêng

Freeze local không hủy lệnh provider đã nhận. Tách danh sách attempt đã dispatch, đang chờ kết quả và UNKNOWN; giao người đối soát.

Không tự giải phóng reservation hoặc đổi tất cả IN_FLIGHT thành FAILED. Những thao tác đó có thể làm cùng nguồn tiền được sử dụng hai lần trong khi provider vẫn hoàn tất lệnh cũ.

## 8. Procedure B — Bảo toàn bằng chứng và lập tập đối soát

### 8.1. Chuỗi dữ liệu cần nối

```text
business command
-> tenant/object/revision
-> approval và policy
-> idempotency record
-> reservation/execution
-> ledger và dispatch intent
-> attempt/provider operation
-> callback/kết quả đã xác minh
```

Ghi thời điểm lấy dữ liệu và mức nhất quán của nguồn. Một truy vấn replica có thể chưa thấy commit mới. Hai báo cáo local/provider ở hai thời điểm khác nhau không tự tạo thành một snapshot nhất quán toàn hệ thống.

Nếu cần snapshot database nhất quán, dùng cơ chế đã kiểm chứng cho database và công cụ đang dùng. Tránh giữ transaction hoặc khóa vận hành quá lâu chỉ để chờ mọi nguồn bên ngoài khớp nhau.

### 8.2. Lập manifest từ nguồn nghiệp vụ

Manifest cần định danh đối tượng, version quan sát, phân loại, bằng chứng, hành động đề xuất và owner. Nguồn chọn đối tượng có thể gồm lệnh mới, replay, execution hoặc callback trong khoảng điều tra, rồi mở rộng tới lịch sử liên quan.

Không chỉ chọn các job còn trong queue: job bị mất/xóa sẽ không xuất hiện. Không chỉ đếm execution nằm trong cửa sổ cảnh báo: một tác dụng trùng có thể có tác dụng đầu tiên xảy ra từ trước cửa sổ đó.

Với mỗi nghĩa vụ đã chọn, kiểm tra toàn bộ tác dụng liên quan theo định danh nghiệp vụ và quy tắc lưu trữ. Những phần lịch sử không còn truy cập được phải được ghi là giới hạn bằng chứng.

### 8.3. Truy vấn chẩn đoán chỉ đọc minh họa

Giả sử `refund_execution` lưu từng tác dụng tiền ra có định danh riêng, các lần callback trùng không tạo row mới, và mô hình cho phép tối đa một tác dụng REFUND chính cho một refund. Một truy vấn rà soát có thể là:

```sql
SELECT
    tenant_id,
    refund_id,
    COUNT(*) AS confirmed_effect_count
FROM refund_execution
WHERE tenant_id = :verified_tenant_id
  AND refund_id IN (:reviewed_refund_ids)
  AND effect_kind = 'REFUND'
  AND outcome = 'CONFIRMED'
GROUP BY tenant_id, refund_id
HAVING COUNT(*) > 1;
```

`:reviewed_refund_ids` là danh sách đã xác minh từ manifest, được bind theo thư viện database thực tế. Không nối chuỗi SQL từ ID hoặc log chưa tin cậy. Bảng, cột và quy tắc phân loại cần được thay bằng schema đã kiểm chứng.

Truy vấn không giới hạn confirmedAt theo cửa sổ cảnh báo để tránh bỏ tác dụng đầu tiên cũ hơn. Tuy nhiên, kết quả chỉ chỉ ra đối tượng cần điều tra theo mô hình đã giả định. Nó không tự phát hiện tác dụng chưa được local ghi nhận hoặc nghĩa vụ bị tạo trùng dưới hai refund ID khác nhau.

Chạy truy vấn với tài khoản chỉ đọc, phạm vi và ngân sách tài nguyên phù hợp. Nếu dữ liệu quá lớn hoặc kế hoạch truy vấn không đáp ứng điều kiện vận hành, chuyển sang công cụ/bản báo cáo đã chuẩn bị; không bỏ filter để quét rộng hơn tùy tiện.

### 8.4. Bảo vệ bằng chứng và đầu ra

Runbook cần quy định nơi lưu, quyền truy cập và dữ liệu phải che. Không đưa token, credential hoặc thông tin tài khoản đầy đủ vào bản ghi incident.

OWASP khuyến nghị log theo mục đích, ghi thuộc tính sự kiện phù hợp và loại trừ dữ liệu nhạy cảm không cần thiết. Đây là cơ sở hữu ích khi thiết kế đầu ra phục vụ điều tra và vận hành. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Nội dung từ log, payload, tên file và thông điệp lỗi có thể do bên ngoài kiểm soát. Xem chúng là dữ liệu bằng chứng; không sao chép vào shell để thực thi và không làm theo hướng dẫn xuất hiện trong payload.

## 9. Procedure C — Phân loại và đối soát kết quả

### 9.1. Bảng quyết định theo bằng chứng

| Nhóm | Tình trạng | Hành động tiếp theo |
| --- | --- | --- |
| Chưa tiếp nhận | Không có command/obligation đã commit | Giữ hành vi từ chối hoặc tiếp nhận theo chính sách hiện tại |
| Đã tiếp nhận, chưa thực thi | Có nghĩa vụ/outbox, chưa có attempt ngoài | HELD, chờ điều kiện phục hồi |
| Local chưa commit | Transaction chưa có kết quả bền vững | Xác định commit/rollback qua nguồn dữ liệu phù hợp |
| Đã dispatch, chưa rõ kết quả | Provider có thể đã nhận | UNKNOWN, tra cứu và giữ exposure phù hợp |
| Thành công đã xác minh | Có bằng chứng provider/ledger đúng hợp đồng | Bảo toàn kết quả, không replay tác dụng |
| Thất bại chắc chắn theo hợp đồng | Có bằng chứng lệnh không thể tiếp tục thực hiện | Xử lý retry/hủy/giải phóng theo chính sách |
| Trùng hoặc sai nội dung | Nhiều tác dụng hoặc sai số tiền/người nhận đã xác minh | Điều tra tác động, đề xuất lệnh bù riêng |
| Bằng chứng mâu thuẫn | Các nguồn không nhất quán | Giữ lại, ghi nguồn và owner đối soát, không chọn kết quả tiện xử lý |

Tên trạng thái cần được ánh xạ vào schema ứng dụng. Không gộp “chưa quan sát được” với “chưa xảy ra”.

### 9.2. Đối soát UNKNOWN

1. Giữ business command, idempotency key, provider account và operation ID đã biết.
2. Dùng khả năng tra cứu của provider theo hợp đồng thực tế.
3. Xác minh callback hoặc bằng chứng nhận được thuộc đúng account, tenant và nghĩa vụ.
4. Ghi thời điểm, nguồn và mức chắc chắn của kết quả.
5. Chỉ thực hiện bước tiếp theo khi đủ điều kiện cho hành động đó.

Nếu provider không hỗ trợ tra cứu hoặc bằng chứng còn mâu thuẫn, ghi phần chưa biết và escalation. Không đổi provider/key như một thao tác “thử xem có chạy không”: lệnh cũ có thể đã được nhận.

### 9.3. Đối soát số tiền và quyền

Tính riêng từng tenant, payment, tiền tệ và nghĩa vụ theo mô hình. Xác định khoản đã hoàn, reservation còn exposure và các khoản điều chỉnh; không cộng khác currency hoặc bỏ khoản UNKNOWN khỏi tổng chỉ để báo cáo hết sai lệch.

Với approval, so nội dung được duyệt với revision đã thực thi. Với quyền, xác định policy nào áp dụng tại bước cần kiểm tra. Một trạng thái APPROVED không chứng minh số tiền và người thụ hưởng sau sửa vẫn đã được duyệt.

### 9.4. Sai lệch cần hành động bù

Nếu xác minh đã hoàn sai, runbook phải chuyển tới quy trình bù/điều chỉnh được phép với nghĩa vụ riêng, reviewer theo policy và idempotency riêng.

Không xóa ledger, xóa execution trùng hoặc sửa approval lịch sử để làm dữ liệu trông hợp lệ. Các hành động điều chỉnh phải giữ liên kết với sự kiện gốc và incident.

## 10. Procedure D — Chuẩn bị phục hồi và replay

### 10.1. Điều kiện trước khi mở lại

Một checklist mẫu:

- Đường lạm dụng hoặc lỗi đã được sửa, vô hiệu hóa hoặc có hàng rào đủ phạm vi.
- Quyền/credential bị xâm phạm đã được xử lý theo quy trình.
- Các đường API, batch, worker và replay đã được kiểm chứng.
- Backlog được phân loại từ dữ liệu nguồn, không chỉ từ queue.
- Có quyết định cho dữ liệu stale, approval hết hạn và nghĩa vụ UNKNOWN.
- Có manifest phục hồi với đối tượng, expected version và hành động cụ thể.
- Người thực hiện có quyền; reviewer đã chấp thuận nội dung khi policy yêu cầu.
- Có điều kiện dừng, giới hạn từng đợt và cơ chế freeze lại.

Không bắt buộc tất cả phạm vi độc lập phải chờ cùng một trạng thái. Nếu mở một phạm vi khác trong khi còn UNKNOWN, cần chứng minh không dùng chung nghĩa vụ/ngân sách rủi ro theo cách phá bất biến.

### 10.2. Manifest phục hồi minh họa

```text
incidentId, recoveryRunId, manifestRevision
tenantId, objectId, businessCommandId
expectedObjectVersion, expectedPolicyVersion
classification, proposedAction
approval/evidenceReference
idempotencyReference, providerOperationReference
operator, reviewer nếu cần
outcome, outcomeReference, nextOwner
```

Không cho một manifest chung chung như “replay toàn bộ job lỗi” thay cho danh sách đã phân loại. Preview cần cho thấy đúng đối tượng và tác động dự kiến. Khi apply phải kiểm tra lại version; preview cũ không cấp quyền ghi lên đối tượng đã đổi.

### 10.3. Replay là tiếp tục nghĩa vụ có kiểm soát

- Giữ nhận diện logic của lệnh khi đang tiếp tục cùng nghĩa vụ.
- Kiểm tra lại quyền, state, revision, approval và thời hạn cần còn hiệu lực.
- Không cấp reservation hoặc tiêu thụ quota lần hai nếu đã có allocation tương ứng.
- Không chạy lại tác dụng đã CONFIRMED.
- Không tự phát lệnh mới cho UNKNOWN trước khi có quyết định an toàn theo hợp đồng.
- Lưu tiến độ sau khi các thay đổi bắt buộc đã commit.

Nếu phải đổi payload vì một quyết định nghiệp vụ mới, đó là lệnh hoặc revision mới theo policy. Không tái dùng cùng key cho nội dung khác để “giữ chống lặp”.

## 11. Procedure E — Phục hồi theo đợt và kiểm chứng sau thao tác

### 11.1. Chạy một đợt có giới hạn

Bắt đầu từ tập nhỏ đã được duyệt theo ngân sách của hệ thống. Kích thước đợt, tần suất và deadline cần được xác định trước khi áp dụng, không lấy mặc định từ một ví dụ tài liệu.

Sau mỗi đợt:

1. Đọc kết quả lệnh đã commit trong ngữ cảnh mới.
2. Đối chiếu manifest với execution, ledger, outbox và provider khi cần.
3. Kiểm tra bất biến, số lượng, số tiền và đối tượng ngoài phạm vi.
4. Phân loại lại HELD/UNKNOWN/conflict; gán owner cho phần chưa kết thúc.
5. Chỉ chuyển đợt sau khi đạt tiêu chí của đợt hiện tại.

Rate limit giúp kiểm soát tải và phạm vi tác động; nó không thay thế authorization, validation hoặc idempotency.

### 11.2. Điều kiện dừng và hướng xử lý

| Dấu hiệu | Hành vi cần có |
| --- | --- |
| Sai tenant, sai manifest hoặc sai object version | Dừng phần liên quan; xác minh lại phạm vi, không tự bỏ điều kiện |
| Xuất hiện execution/ledger trùng mới | Dừng cấp tác dụng mới, giữ bằng chứng và đánh giá freeze lại |
| Tổng nghĩa vụ vượt giới hạn | Dừng; đối soát ngân sách và tác dụng đang bay |
| UNKNOWN tăng ngoài ngân sách cho phép | Dừng/giảm xử lý theo policy, giao đối soát |
| Công cụ trả timeout khi apply | Tra cứu cùng command ID và readback, không kết luận rollback |
| Dữ liệu nguồn không truy cập được | Giữ trạng thái an toàn, không thay bằng phỏng đoán từ cache |
| Phát hiện đường bỏ qua quyền | Chặn đường đó và escalation; chưa coi phục hồi hoàn tất |
| Điều kiện hợp lệ bị từ chối hàng loạt | Dừng mở rộng, kiểm tra policy và tương thích dữ liệu |

Runbook phải phân biệt “dừng đợt hiện tại”, “freeze lại toàn phạm vi” và “escalation cho quyết định khác”. Không để operator tự suy ra một hành vi có tác động lớn từ chữ “abort”.

### 11.3. Rollback khác với bù tác dụng

Nếu thay đổi cấu hình local có thể rollback, ghi điều kiện, version cần đối chiếu và cách xác nhận. Rollback code không đảo ngược giao dịch đã được provider nhận.

Nếu quay về build cũ có thể mở lại lỗ hổng, giữ containment hoặc hàng rào tương ứng. Không gỡ constraint, hạ policy hoặc reset key như một phần rollback mặc định.

Tác dụng tiền đã xảy ra cần được xử lý bằng lệnh nghiệp vụ riêng có thẩm quyền và bằng chứng. Runbook nên liên kết tới procedure đó thay vì gọi mọi việc là “undo”.

## 12. Ghi nhận, truyền thông và bàn giao

### 12.1. Bản ghi hành động tối thiểu

```text
incidentId, runbookId, runbookVersion, procedureId
environment, verifiedScope, manifestRevision
actor, authority/approvalReference khi cần
commandId, expectedVersion, requestTime
beforeStateReference, resultReference, readbackReference
observedOutcome, uncertainty, stopReason
nextAction, nextOwner, handoffTime
```

Ghi cả thao tác thất bại và thao tác không rõ kết quả. Một command timeout có thể đã commit; bỏ nó khỏi timeline sẽ làm người tiếp theo gửi lại như một lệnh mới.

Phân biệt thời điểm yêu cầu, thời điểm quan sát, thời điểm commit có bằng chứng và thời điểm provider ghi nhận. Không sắp mọi sự kiện từ nhiều nguồn chỉ theo timestamp rồi khẳng định quan hệ nhân quả chắc chắn.

### 12.2. Thông tin bàn giao cần đủ để người khác tiếp tục

Bàn giao phải nêu phạm vi đang bị chặn, gate epoch thực tế, những bước đã hoàn tất, manifest đang dùng, lệnh đang chạy, UNKNOWN còn lại, quyền khẩn cấp đang hiệu lực và điều kiện dừng.

Người nhận cần xác nhận trạng thái từ nguồn phù hợp trước khi tiếp tục thao tác có tác dụng. Không dựa hoàn toàn vào câu “đã freeze rồi” của ca trước.

Đối với cập nhật tình hình, dùng người và kênh được giao nhiệm vụ. Nội dung phải phản ánh đúng mức chắc chắn: đã chặn lần thực thi local mới khác với đã đối soát hết tác dụng ngoài. Không đưa dữ liệu nhạy cảm hoặc giả thuyết chưa xác minh vào thông báo rộng.

### 12.3. Điều kiện kết thúc runbook

Có thể hoàn thành procedure vận hành khi đạt tiêu chí đã định và phần còn lại được giao rõ owner. Không cần xóa sự không chắc chắn khỏi báo cáo để đổi trạng thái.

Một tiêu chí kết thúc phục hồi mẫu gồm: hàng rào đang hoạt động đúng, không có vi phạm mới trong phạm vi quan sát theo kế hoạch, manifest đã có kết quả cho từng mục và các khoản còn mở có quyết định theo dõi.

Đóng incident, đóng runbook execution và hoàn tất mọi công việc khắc phục là các mốc có thể khác nhau. Cần ghi chính xác mốc nào đã đạt.

## 13. Kiểm thử và duy trì runbook

### 13.1. Diễn tập bằng tình huống có lỗi thật

Một tài liệu đọc mạch lạc chưa chắc có thể thực thi. Cần diễn tập để kiểm tra quyền truy cập, link, truy vấn, tham số, đầu ra và nhánh lỗi.

| Tình huống diễn tập | Điều cần chứng minh |
| --- | --- |
| Command freeze commit nhưng response mất | Operator tra cùng command và readback, không gửi một quyết định khác tùy tiện |
| Gate đã FROZEN nhưng worker cache OPEN | Runbook phát hiện đường chưa tuân theo, không báo containment hoàn tất |
| Provider nhận rồi timeout | Giữ UNKNOWN và exposure, không đổi key rồi replay |
| Manifest stale | Apply dừng theo expected version; không ghi đè dữ liệu mới |
| Một job đã bị xóa khỏi queue | Đối soát từ nghĩa vụ nguồn vẫn phát hiện thiếu kết quả |
| Approval hết hạn trong khi chờ | Phục hồi không coi approval cũ là giấy phép vĩnh viễn |
| Tài khoản ca trực thiếu quyền ghi | Có nhánh cấp quyền/escalation đã chuẩn bị, không dùng account chung tùy tiện |
| Audit hoặc kho bằng chứng lỗi | Không báo hoàn tất giả; xác định phần bị chặn và owner |
| Đợt phục hồi dừng giữa chừng | Có thể resume đúng phần chưa commit, không tạo lặp |
| Bàn giao khi còn UNKNOWN | Người nhận biết chính xác nghĩa vụ nào cần đối soát |

Các thử nghiệm tạo tác dụng cần chạy trong môi trường và phạm vi đã được phép. Fault injection ở môi trường thật chỉ dùng khi có kế hoạch, giới hạn và thẩm quyền phù hợp; một runbook minh họa không tự cấp quyền thử trên production.

### 13.2. Tiêu chí tài liệu sẵn sàng sử dụng

- Chủ thể ngoài nhóm viết có thể tìm đúng procedure và đi qua bài diễn tập.
- Mọi placeholder bắt buộc đã được ánh xạ hoặc công cụ từ chối khi chưa điền.
- Quyền và escalation route đã được kiểm tra.
- Các lệnh/truy vấn khớp build, schema, provider và policy đang hỗ trợ.
- Mỗi hành động ghi có readback, nhánh timeout và điều kiện dừng.
- Không có bước dựa vào xóa lịch sử, bỏ quyền hoặc đổi key để giải quyết UNKNOWN.
- Có bằng chứng diễn tập và danh sách giới hạn hiện biết.

Không đo chất lượng chỉ bằng độ dài hoặc số lượng câu lệnh. Một procedure ngắn có quyết định rõ thường hữu ích hơn trang dài yêu cầu người vận hành tự suy đoán.

### 13.3. Trigger cập nhật và cải tiến

Cập nhật runbook khi thay state machine, quyền, idempotency scope, schema, provider, control plane hoặc công cụ replay. Những thay đổi tưởng nhỏ như đổi ý nghĩa status SENT cũng có thể làm bước đối soát sai.

Sau incident hoặc diễn tập, đưa các bước không thực hiện được và các giả định sai thành action item có owner và bằng chứng hoàn thành. NIST SP 800-61 Rev. 3 đặt ứng phó sự cố trong hoạt động quản lý rủi ro rộng hơn, hỗ trợ việc cải tiến khả năng phát hiện, ứng phó và phục hồi theo thời gian. [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final).

Giữ lịch sử version để biết procedure nào đã được sử dụng. Khi runbook chưa còn phù hợp, đánh dấu giới hạn và cung cấp đường xử lý thay thế rõ thay vì để một tài liệu lỗi thời trông như vẫn sẵn sàng.

## 14. Bài tập áp dụng

Hệ thống có một alert cho biết refund R1 có hai tác dụng hoàn tiền. Refund R2 còn APPROVED trong queue nhưng approval thuộc revision cũ. Refund R3 đã được provider nhận, ứng dụng timeout và đang UNKNOWN. Một operator đề nghị xóa các job lỗi, reset idempotency key và chạy lại batch.

Hãy xây runbook cho tình huống này:

1. Viết điều kiện kích hoạt, phạm vi và bất biến phải giữ.
2. Xác định vai trò, quyền và các nguồn dữ liệu cần truy cập.
3. Soạn procedure freeze có expected epoch, command ID, readback và giới hạn bảo đảm bên ngoài.
4. Lập manifest từ dữ liệu nghiệp vụ và mô tả cách không bỏ sót tác dụng xảy ra trước cửa sổ alert.
5. Phân loại R1, R2, R3 và nêu dữ liệu cần xác minh cho từng quyết định.
6. Thiết kế điều kiện mở lại, replay và hành động bù; giữ đúng nhận diện nghĩa vụ.
7. Viết nhánh timeout, stale manifest, quyền thiếu và phát hiện sai tenant.
8. Xác định thông tin bàn giao và bằng chứng để tuyên bố procedure đã hoàn tất.
9. Diễn tập command commit nhưng mất response cùng trường hợp worker chưa tuân freeze.

Bài làm đạt phải giúp một người có đúng quyền thực hiện được các bước trong phạm vi rõ, đọc lại kết quả và dừng khi điều kiện không còn đúng. Thành công được chứng minh bằng trạng thái và tác dụng nghiệp vụ đã đối soát, cùng phần chưa biết được giao trách nhiệm rõ ràng.
