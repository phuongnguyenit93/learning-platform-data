# Rà soát hành động không được phép (Unauthorized action review)

Trong chương **Incident Response** của module bảo vệ logic nghiệp vụ, một câu hỏi cần được trả lời bằng bằng chứng là: **hành động này có được phép thực hiện trên đúng đối tượng, với đúng nội dung và tại đúng thời điểm hay không?** Người gọi đăng nhập hợp lệ, API trả thành công hoặc service account có quyền chạy worker đều chưa đủ để kết luận nghiệp vụ được cấp phép đúng.

**Unauthorized action review** là quá trình rà soát hành động bị nghi thực hiện ngoài quyền hoặc ngoài điều kiện nghiệp vụ đã được chấp thuận. Mục tiêu là xác định quy tắc nào bị vi phạm, hiệu ứng nào đã xảy ra, phạm vi ảnh hưởng đến đâu và cần chặn/sửa điều gì. Việc rà soát phải giữ được bằng chứng về quyền theo đối tượng, state machine, transaction, idempotency và business invariants.

Bài học dùng ví dụ hoàn tiền có phê duyệt để minh họa. Mọi định danh, số tiền, schema và quy tắc bên dưới đều là dữ liệu tổng hợp cho việc học; khi áp dụng cần dùng hợp đồng nghiệp vụ và mô hình quyền thực tế của hệ thống.

## 1. Xác định chính xác điều đang được rà soát

### 1.1. Hành động không được phép có nhiều dạng

| Dạng vi phạm | Ví dụ trong logic nghiệp vụ |
|---|---|
| Sai quyền chức năng | Nhân viên chỉ được xem lại gọi chức năng thực hiện hoàn tiền |
| Sai quyền theo đối tượng | Người dùng tenant B thao tác đơn hàng của tenant A |
| Sai nội dung được duyệt | Khoản được duyệt là 40.000 VND nhưng lệnh thực hiện là 400.000 VND |
| Sai trạng thái hoặc thứ tự | Thực hiện khi chưa duyệt, hoặc dùng lại phê duyệt đã hủy |
| Sai điều kiện phân tách nhiệm vụ | Người tạo đề nghị tự phê duyệt trong quy trình cấm tự duyệt |
| Sai phạm vi ủy quyền | Tài khoản được ủy quyền xem hồ sơ lại thực hiện thay đổi tài chính |
| Sai thời hạn hoặc điều kiện thực thi | Dùng phê duyệt hết hạn khi hợp đồng yêu cầu phê duyệt còn hiệu lực lúc gửi lệnh |
| Lạm dụng lặp | Phát lại cùng ý định tạo thêm hiệu ứng vượt số lần được chấp thuận |

Một hành động có thể vi phạm đồng thời nhiều quy tắc. Không nên dừng ở nhãn chung “thiếu kiểm tra quyền” nếu bằng chứng cho thấy lỗi nằm ở liên kết approval với amount hoặc ở việc kiểm tra trạng thái không cùng transaction với thực thi.

### 1.2. Tách kết luận về quyền khỏi kết luận về hiệu ứng

Hai trục dưới đây cần được ghi riêng:

| Trục | Các kết luận có thể dùng |
|---|---|
| Quyền và điều kiện nghiệp vụ | Đã chứng minh được phép; đã chứng minh không được phép; chưa đủ bằng chứng |
| Mức độ thực hiện | Bị chặn trước hiệu ứng; đã commit thay đổi nội bộ; đã có hiệu ứng bên ngoài; chưa xác định kết quả |

Một request bị từ chối trước mọi thay đổi có thể là một **lần thử thao tác trái phép đã được chặn**. Nó khác hành động trái phép đã làm tiền đi ra. Ngược lại, phản hồi `403` hoặc lỗi `500` cũng không tự chứng minh không có hiệu ứng nếu kiểm tra quyền xảy ra muộn hoặc một bước bên ngoài đã chạy trước lỗi.

Nếu mất log quyết định quyền, kết luận ban đầu thường là chưa đủ bằng chứng, không tự động là “đã được phép” hoặc “đã bị tấn công”. Nếu đã có bằng chứng chắc chắn về một điều kiện bắt buộc bị vi phạm, thiếu một loại log khác không làm mất giá trị của bằng chứng vi phạm ấy. Vẫn phải chứng minh bằng chứng đó liên quan đúng hành động đang xét.

### 1.3. Đơn vị rà soát không chỉ là HTTP request

Phân biệt các định danh:

```text
business intent:  một ý định nghiệp vụ được chấp nhận
action:           một bước nghiệp vụ như tạo, duyệt, thực hiện hoặc hủy
attempt:          một lần thử xử lý action
request/event:    một lần chuyển giao qua HTTP, queue hoặc callback
external effect:  giao dịch thực sự tại hệ thống ngoài
```

Một intent có thể có nhiều attempt hợp lệ nhưng chỉ được tạo một hiệu ứng hoàn tiền. Một request cũng có thể khởi phát công việc chạy sau đó bằng danh tính worker khác. Dùng `traceId` làm khóa rà soát duy nhất sẽ dễ bỏ mất retry, callback hoặc job nền thuộc cùng chuỗi nghiệp vụ.

## 2. Tình huống xuyên suốt: phê duyệt đúng nhưng thực hiện sai nội dung

Đơn `order-42` thuộc `tenant-A` đã thu 1.000.000 VND và chưa hoàn tiền. Quy trình tổng hợp quy định:

1. Nhân viên tạo refund intent với amount và currency cụ thể.
2. Người có quyền phê duyệt, khác người tạo, duyệt đúng phiên bản nội dung ấy.
3. Khi thực hiện, hệ thống kiểm tra lại approval đang có hiệu lực theo hợp đồng, liên kết đúng intent/version và đúng nội dung.
4. Worker chỉ gửi nội dung đã được phép và giữ chỗ trong giới hạn hoàn của đơn.
5. Cùng intent không được tạo hai khoản hoàn thành công.

Trong sự cố, `approval-8` duyệt `refund-17` phiên bản 3 với **40.000 VND**. Sau đó intent bị sửa thành phiên bản 4 với **400.000 VND**. Luồng thực hiện chỉ kiểm tra “có approval mang trạng thái APPROVED” rồi lấy amount mới để gửi provider.

Giới hạn hoàn 1.000.000 chưa bị vượt, nhưng điều đó không làm khoản 400.000 trở thành được phép. Có ít nhất hai lớp bất biến độc lập:

```text
Tổng đã hoàn + tổng đang giữ chỗ <= tổng hạn mức hoàn được phép của đơn

Nội dung thực hiện phải khớp nội dung và phiên bản được phê duyệt
```

Rà soát cần chứng minh amount gửi đi, nội dung được duyệt và mối liên kết giữa chúng. Chỉ thấy cùng một `approvalId` xuất hiện trong hai log chưa đủ chứng minh approval đó cấp phép cho phiên bản đã được thực hiện.

## 3. Thu thập bằng chứng mà không làm mất trạng thái sự cố

### 3.1. Các nguồn phục vụ những câu hỏi khác nhau

| Nguồn bằng chứng | Câu hỏi nó giúp trả lời | Giới hạn cần ghi nhận |
|---|---|---|
| Audit tạo/sửa intent và lịch sử phiên bản | Nội dung nào đã tồn tại, ai/cơ chế nào thay đổi? | Bảng hiện tại có thể đã ghi đè giá trị cũ |
| Quyết định authorization và cấu hình policy | Đã kiểm tra subject, resource, action, điều kiện nào? | `ALLOW` không tự chứng minh điều kiện kiểm tra đầy đủ hoặc đúng dữ liệu |
| Lịch sử role, membership, delegation và thu hồi | Chủ thể có quyền/phạm vi gì ở mốc cần kiểm tra? | Role hiện tại không tái hiện quyền trong quá khứ |
| Approval và snapshot được duyệt | Đã duyệt nội dung, version, người duyệt nào? | Trạng thái `APPROVED` hiện tại có thể thiếu lịch sử hủy/hết hạn |
| Database transaction, ledger và reservation | Thay đổi nội bộ nào đã commit? | Log “đang ghi” không chứng minh commit thành công |
| Outbox, inbox và lịch sử attempt | Ý định nào đã được chuyển cho worker, có phát lại không? | ACK hoặc `SENT` không tự chứng minh kết quả tiền |
| Provider transaction/báo cáo có phạm vi tài khoản rõ ràng | Hiệu ứng bên ngoài nào đã thực sự xảy ra? | Thành công bên ngoài không chứng minh nghiệp vụ được cấp phép đúng |
| Gateway, phiên và dấu vết vận hành | Request đi qua đâu, dùng session/service identity nào? | IP, user agent hoặc subject ID chưa đủ quy kết người thật đã thao tác |

Đọc dữ liệu từ nguồn được phép, lưu truy vấn và phạm vi thời gian của bản trích xuất. Với bằng chứng cần giữ phục vụ điều tra, ghi nguồn, thời điểm thu thập, người/cơ chế thu thập, cách kiểm tra tính toàn vẹn và nơi lưu có kiểm soát truy cập. Băm bản trích xuất giúp phát hiện thay đổi sau khi thu thập; nó không tự chứng minh dữ liệu gốc đã chính xác hoặc đầy đủ.

Không xóa intent, sửa approval, đổi chủ sở hữu đối tượng hoặc cập nhật hàng loạt trạng thái để “làm sạch” trước khi giữ được bằng chứng cần thiết. Thực hiện thao tác gây hiệu ứng thật chỉ để tái hiện sẽ làm thay đổi phạm vi sự cố; tái hiện bằng fixture trong môi trường kiểm thử cô lập.

### 3.2. Gói bằng chứng tối thiểu theo từng hành động

Một cấu trúc minh họa cho hồ sơ rà soát:

```json
{
  "reviewId": "review-21",
  "actionId": "action-execute-17",
  "intentId": "refund-17",
  "attemptIds": ["attempt-1", "attempt-2"],
  "tenantId": "tenant-A",
  "resource": {"type": "order", "id": "order-42"},
  "action": "REFUND_EXECUTE",
  "requestedBy": "staff-12",
  "executedBy": "refund-worker",
  "approvalId": "approval-8",
  "approvedVersion": 3,
  "executedVersion": 4,
  "approvedAmount": 40000,
  "executedAmount": 400000,
  "currency": "VND",
  "policyVersion": "refund-policy-6",
  "providerScope": "provider-X/merchant-A",
  "providerTransactionId": "provider-refund-91",
  "permissionFinding": "UNAUTHORIZED_CONFIRMED",
  "effectFinding": "EXTERNAL_SUCCESS_CONFIRMED",
  "evidenceRefs": ["approval-snapshot-8", "provider-record-91"]
}
```

Đây là hồ sơ tổng hợp, không phải danh sách dữ liệu bắt buộc phải ghi vào mọi log. Các `evidenceRefs` cần trỏ tới bằng chứng có thể kiểm tra trong kho phù hợp. Amount phải dùng đơn vị đã thống nhất và biểu diễn chính xác. Không đưa token, credential, toàn bộ thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết vào hồ sơ.

`requestedBy` và `executedBy` mô tả hai vai trò khác nhau trong chuỗi xử lý. Worker thực hiện theo một intent không có nghĩa worker có quyền tự tạo ý định tiền mới; ngược lại, chỉ nhìn requester cũng bỏ qua khả năng payload bị thay đổi sau khi chuyển giao.

## 4. Dựng timeline và chọn đúng thời điểm đánh giá quyền

### 4.1. Timeline phải nối được quyết định với hiệu ứng

| Thứ tự logic | Sự kiện | Bằng chứng cần đối chiếu |
|---|---|---|
| 1 | Tạo intent v3, 40.000 VND | Snapshot, actor, tenant, resource |
| 2 | Duyệt v3 bằng `approval-8` | Nội dung được duyệt, quyền người duyệt, quy tắc khác người tạo |
| 3 | Sửa thành v4, 400.000 VND | Lịch sử sửa, quyền sửa, cách approval được vô hiệu hóa hoặc giữ lại |
| 4 | Chấp nhận lệnh thực hiện v4 | Quyết định authorization, kiểm tra state/version, transaction giữ chỗ |
| 5 | Worker gửi lệnh 400.000 | Payload bền vững, identity, merchant scope, attempt |
| 6 | Provider hoàn thành công | Giao dịch và amount/currency thực tế |
| 7 | Ghi nhận kết quả hoặc xử lý retry | Posting, trạng thái, số hiệu ứng trên cùng intent |

Timestamp từ các hệ thống khác nhau có thể lệch đồng hồ hoặc phản ánh thời điểm nhận thay vì thời điểm xảy ra. Ghi rõ ý nghĩa của từng timestamp, dùng sequence/version/quan hệ nhân quả khi có, và nêu khoảng không chắc chắn. Thứ tự hiển thị trong file log không tự là thứ tự commit.

### 4.2. Quyền hiện tại không phải oracle cho quyền quá khứ

Việc một nhân viên hiện bị thu hồi quyền không chứng minh họ không có quyền lúc tạo yêu cầu. Việc họ hiện có quyền cũng không hợp thức hóa một hành động trước lúc được cấp quyền.

Cần xác định hợp đồng cho từng mốc:

- Lúc tạo intent: ai được đề nghị nghiệp vụ trên đối tượng nào?
- Lúc duyệt: ai được duyệt, với hạn mức, phạm vi và quy tắc phân tách nhiệm vụ nào?
- Lúc chấp nhận thực hiện: approval/version có còn phù hợp và điều kiện bắt buộc có được kiểm tra nguyên tử với thay đổi local không?
- Lúc worker phát lệnh: điều kiện nào bắt buộc kiểm tra lại, điều kiện nào được thừa nhận từ quyết định đã chấp nhận trước đó?
- Lúc ghi nhận kết quả: có đang ghi lại một hiệu ứng đã xảy ra hay đang tạo thêm nghiệp vụ mới?

Một số nghiệp vụ cho phép worker hoàn tất một intent đã được chấp nhận dù requester đổi role sau đó; nghiệp vụ khác đòi hỏi thu hồi/hạn chế có hiệu lực trước lúc phát lệnh. Không tự chọn một trong hai chính sách khi rà soát. Nếu hợp đồng thiếu, ghi thành khoảng trống thiết kế cần quyết định và giữ rõ những gì bằng chứng hiện có đã chứng minh.

Provider xác nhận đã hoàn tiền là sự thật cần được phản ánh trong sổ dù lệnh ban đầu trái phép. Ghi nhận sự thật đó không phải phê duyệt hồi tố cho hành động đã gây ra nó.

## 5. Đánh giá hành động theo các điều kiện bắt buộc

### 5.1. Từ câu hỏi chung thành danh sách kiểm tra có bằng chứng

| Điều kiện | Câu hỏi rà soát | Ví dụ bằng chứng vi phạm |
|---|---|---|
| Danh tính và ủy quyền | Chủ thể hiệu lực là ai, đang hành động cho ai? | Worker nhận yêu cầu không có nguồn gốc hợp lệ hoặc delegation ngoài phạm vi |
| Quyền chức năng | Chủ thể có quyền thực hiện action tại mốc quy định không? | Policy đang có hiệu lực cấm action trên role ấy |
| Quyền theo đối tượng | Subject có quyền với đúng tenant/resource không? | Resource thuộc tenant khác, không có quan hệ chia sẻ được phép |
| Phê duyệt và nội dung | Approval có ràng buộc đúng intent/version/amount/currency không? | Snapshot duyệt 40.000 nhưng lệnh đã gửi 400.000 |
| State machine | Chuyển trạng thái có được phép không? | Gửi lệnh khi approval đã bị hủy theo mốc có hiệu lực |
| Phân tách nhiệm vụ | Người tạo, người duyệt, người áp dụng có đáp ứng hợp đồng không? | Cùng chủ thể tự duyệt trong quy trình cấm điều đó |
| Bất biến tiền và số lần | Có vượt hạn mức hoặc tạo hiệu ứng trùng không? | Hai giao dịch thành công cho intent chỉ được phép một khoản hoàn |
| Tính nguyên tử/đồng thời | Điều kiện được kiểm tra có còn đúng lúc commit/thực thi không? | Hai worker cùng dùng một phần hạn mức mà không có bảo vệ phù hợp |

Gắn từng câu trả lời với nguồn và mốc thời gian. `ALLOW` trong log chỉ là bằng chứng một bộ phận đã cho phép theo đầu vào của nó. Cần kiểm tra bộ phận ấy có kiểm tra đúng điều kiện bắt buộc và đúng snapshot hay không.

### 5.2. Quy tắc kết luận tránh suy diễn từ dữ liệu thiếu

Mã giả cho phần tổng hợp kết luận:

```text
điều_kiện = các_quy_tắc_bắt_buộc_của_action_theo_hợp_đồng()

nếu có điều_kiện bị_vi_phạm_đã_được_chứng_minh
    và bằng_chứng_được_liên_kết_chắc_chắn_với_action:
        kết_luận_quyền = KHÔNG_ĐƯỢC_PHÉP_ĐÃ_XÁC_NHẬN
ngược_lại_nếu còn thiếu bằng_chứng_bắt_buộc hoặc có mâu_thuẫn_chưa_giải_quyết:
        kết_luận_quyền = CHƯA_ĐỦ_BẰNG_CHỨNG
ngược_lại_nếu mọi điều_kiện_bắt_buộc_được_chứng_minh_thỏa_mãn:
        kết_luận_quyền = ĐƯỢC_PHÉP_ĐÃ_XÁC_NHẬN

đánh_giá_hiệu_ứng_riêng_từ_commit_local_và_bằng_chứng_bên_ngoài()
ghi_riêng_mức_chắc_chắn_về_danh_tính_người_thật()
```

Một phiên bị chiếm dụng có thể mang subject của nhân viên hợp lệ. Kết luận “credential của staff-12 được dùng” khác kết luận “staff-12 chủ ý thực hiện hành động”. Giữ sự phân biệt này trong báo cáo, ngay cả khi vi phạm nghiệp vụ đã được xác nhận.

## 6. Truy vấn hồ sơ rà soát mà không tự tạo kết luận sai

### 6.1. Ví dụ truy vấn chỉ đọc

Giả sử bản trích xuất kiểm soát có các bảng minh họa `business_action`, `authorization_decision` và `approval_snapshot`. Khóa quyết định là duy nhất trong tenant; snapshot approval được định danh bằng tenant, approval và version. Những ràng buộc này là giả định của ví dụ, phải kiểm tra trước khi dùng cấu trúc join tương tự trên dữ liệu thật.

```sql
SELECT
    a.action_id,
    a.intent_id,
    a.tenant_id,
    a.resource_id,
    a.accepted_at,
    a.requested_by,
    a.executed_by,
    a.intent_version AS executed_version,
    a.amount AS executed_amount,
    a.currency AS executed_currency,
    d.outcome AS recorded_decision,
    d.policy_version,
    d.resource_id AS checked_resource_id,
    p.intent_id AS approved_intent_id,
    p.intent_version AS approved_version,
    p.amount AS approved_amount,
    p.currency AS approved_currency,
    p.approved_by
FROM business_action a
LEFT JOIN authorization_decision d
    ON d.tenant_id = a.tenant_id
   AND d.decision_id = a.authorization_decision_id
LEFT JOIN approval_snapshot p
    ON p.tenant_id = a.tenant_id
   AND p.approval_id = a.approval_id
   AND p.intent_version = a.approval_version_used
WHERE a.action_type = 'REFUND_EXECUTE'
  AND a.accepted_at >= :window_start
  AND a.accepted_at < :window_end
ORDER BY a.accepted_at, a.action_id;
```

Tham số cửa sổ phải được truyền theo cơ chế tham số hóa của công cụ. Chỉ truy vấn dữ liệu mà vai trò điều tra được phép tiếp cận. Nếu đọc từ replica hoặc bản trích xuất, ghi độ trễ/mốc chốt để không nhầm dữ liệu chưa xuất hiện với dữ liệu không tồn tại.

`LEFT JOIN` giữ lại action không tìm thấy bằng chứng đi kèm để có thể điều tra khoảng trống. Đổi sang `INNER JOIN` ngay từ đầu có thể làm biến mất chính các action thiếu quyết định quyền hoặc thiếu snapshot cần rà soát.

Truy vấn này chỉ lập danh sách đối chiếu; nó chưa đánh giá lịch sử role, hiệu lực hủy approval, hiệu ứng provider hay mọi business invariant. Cột `NULL` cũng có thể do sai liên kết, thiếu bản trích xuất, chính sách lưu giữ hoặc lỗi ghi log. Không gán trực tiếp mọi dòng `NULL` thành hành động trái phép.

### 6.2. Tránh lỗi liên kết và đếm trùng

- Không join chỉ bằng amount và timestamp gần nhau: nhiều hành động hợp lệ có thể giống nhau ở hai thuộc tính đó.
- Không dùng resource ID hoặc provider transaction ID ngoài phạm vi duy nhất được hợp đồng bảo đảm. Tenant, provider và merchant account có thể là một phần của identity.
- Nếu một action có nhiều attempt hoặc sự kiện, tách truy vấn chi tiết khỏi tổng hợp; join một-nhiều có thể nhân số dòng và nhân số tiền.
- Đếm action, intent, nhóm posting và giao dịch bên ngoài theo từng loại identity. Không coi một con số `COUNT(*)` là đồng thời đại diện cho cả bốn.
- Kiểm tra cả action đã commit nhưng thiếu audit và audit thực hiện nhưng chưa commit. Một hướng quét duy nhất có thể bỏ sót hướng còn lại.

Nếu cần thống kê, khử trùng theo khóa nghiệp vụ ở đúng lớp trước khi cộng. Việc này phục vụ đếm chính xác; không được dùng “khử trùng” để che hai giao dịch tiền khác nhau thực sự đã xảy ra cho cùng intent.

## 7. Khoanh vùng toàn bộ tập hành động có thể bị ảnh hưởng

### 7.1. Từ một mẫu đã xác nhận đến điều kiện tìm kiếm

Sau khi xác nhận luồng dùng approval cũ cho intent mới, tìm các action có đặc điểm của lỗi, chẳng hạn:

- Đi qua phiên bản code hoặc nhánh xử lý có kiểm tra approval thiếu ràng buộc.
- Được thực hiện trong khoảng triển khai và cấu hình/policy liên quan có hiệu lực.
- Có thay đổi nội dung sau approval hoặc có version thực hiện khác version được duyệt.
- Có action từ API quản trị, batch, worker hoặc kênh nội bộ dùng cùng hàm nghiệp vụ.
- Có retry/callback thuộc intent đã lọt vào phạm vi, kể cả khi lần gửi đầu ở ngoài cửa sổ truy vấn ban đầu.

Không chỉ tìm cùng user, IP, amount hoặc endpoint của mẫu đầu tiên. Một lỗi cấp quyền theo đối tượng có thể ảnh hưởng nhiều actor; một lỗi nằm trong service dùng chung có thể có nhiều đường vào.

Ghi rõ mốc bắt đầu/kết thúc được chứng minh và phần chỉ là ước lượng. Nếu không còn log đủ lâu, không tuyên bố “không có trường hợp trước đó” chỉ vì truy vấn không trả về dữ liệu.

### 7.2. Phân nhóm để không đánh đồng nghi vấn với thiệt hại

| Nhóm hồ sơ | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Đã xác nhận vi phạm, có hiệu ứng | Có bằng chứng quyền/điều kiện bị vi phạm và thay đổi đã xảy ra | Ưu tiên chặn tiếp diễn, ghi nhận tác động, xử lý hậu quả theo thẩm quyền |
| Đã xác nhận vi phạm, bị chặn trước hiệu ứng | Cơ chế chặn đã hoạt động trong phạm vi bằng chứng | Đánh giá hành vi thử lạm dụng và kiểm tra không có đường vòng |
| Đã xác nhận vi phạm, chưa rõ hiệu ứng | Vi phạm rõ nhưng kết quả gửi/commit chưa xác định | Đối soát kết quả, giữ kiểm soát idempotency và hạn mức |
| Chưa đủ bằng chứng về quyền hoặc tác động | Thiếu lịch sử, liên kết hoặc nguồn xác nhận cần thiết | Giữ danh sách cần điều tra, nêu rõ dữ liệu còn thiếu |
| Được phép theo bằng chứng đầy đủ | Tất cả điều kiện bắt buộc của trường hợp đã được chứng minh | Lưu căn cứ loại khỏi phạm vi vi phạm |

Lập tổng theo action/intent duy nhất, đối tượng bị ảnh hưởng và giao dịch thành công. Tách tiền thực sự đã đi ra, tiền đang chưa rõ kết quả và mức phơi nhiễm có thể có; không cộng lẫn thành một con số thiệt hại đã xác nhận.

Trong ví dụ, provider xác nhận khoản 400.000 đã đi ra là sự thật tài chính. Chênh lệch với khoản được duyệt là 360.000, nhưng không tự coi 360.000 là toàn bộ thiệt hại cuối cùng hay coi 40.000 chắc chắn hợp lệ để tách riêng. Approval 40.000 không cấp phép cho giao dịch 400.000; cách đánh giá và xử lý hậu quả còn phụ thuộc hợp đồng nghiệp vụ, các giao dịch khác và bằng chứng bổ sung.

### 7.3. Ghi mức bao phủ của cuộc rà soát

Một báo cáo nên cho biết đã kiểm tra những tenant/kênh/phiên bản nào, dữ liệu tới mốc nào, bao nhiêu hồ sơ còn thiếu bằng chứng và nguồn nào chưa truy cập được. “Không tìm thấy thêm trong tập đã kiểm tra” có phạm vi chứng minh rõ hơn “không còn hành động trái phép”.

## 8. Ngăn tiếp diễn và sửa hậu quả theo đúng quyền

### 8.1. Chặn đường gây lỗi trước khi mở lại nghiệp vụ

Biện pháp kiềm chế phải gắn với cơ chế gây sự cố đã biết. Với ví dụ approval, có thể tạm dừng gửi các intent có approval/version không khớp, vô hiệu hóa nhánh thực thi lỗi hoặc đưa trường hợp nghi vấn vào luồng chờ được kiểm soát.

Nếu có dấu hiệu credential bị chiếm dụng, xử lý phiên/credential theo quy trình được cấp quyền và kiểm tra hiệu lực thu hồi trên các đường thực thi liên quan. Việc thu hồi danh tính không thay thế bản sửa ràng buộc approval; người gọi khác vẫn có thể gặp hoặc lạm dụng lỗi logic ấy.

Ghi lại biện pháp, thời điểm áp dụng, phạm vi và bằng chứng đã có hiệu lực. Với job nền đã nhận việc trước lúc chặn, cần kiểm tra chúng có còn phát lệnh được không. Một giao diện đã tắt chưa chứng minh queue, API quản trị và worker cùng bị chặn.

### 8.2. Không sửa lịch sử để hợp thức hóa hành động

Không đổi approval thành 400.000 sau khi sự cố xảy ra rồi tuyên bố giao dịch đã được duyệt. Không xóa posting hoặc sửa amount của giao dịch gốc để làm số tổng trông đúng. Những thao tác đó làm mất bằng chứng và có thể tạo sai lệch mới.

Nếu cần điều chỉnh hoặc bù trừ, lập một nghiệp vụ mới có lý do, quyền, điều kiện, liên kết với giao dịch gốc và idempotency riêng. Ghi nhận giao dịch đã xảy ra, đánh dấu vi phạm và xử lý hậu quả là các quyết định khác nhau; chúng cần được liên kết nhưng không thay thế nhau.

Khi kết quả bên ngoài chưa rõ, không giải phóng giữ chỗ hay gửi một khoản thay thế chỉ vì requester đã bị khóa hoặc intent bị gắn cờ sự cố. Trước hết cần xác định hiệu ứng của lệnh cũ, giữ bất biến tiền và áp dụng đúng hợp đồng xử lý chưa xác định.

### 8.3. Kiểm tra lại quyết định khi áp dụng sửa chữa

Một bản đề xuất xử lý có thể dựa vào dữ liệu đã cũ. Trước khi áp dụng, kiểm tra lại version, trạng thái hiện tại, quyền và các điều kiện bắt buộc; bảo vệ thay đổi local bằng cơ chế transaction/đồng thời phù hợp. Chạy lại cùng đề xuất hoặc thao tác đồng thời không được tạo hai điều chỉnh cho cùng hậu quả ngoài hợp đồng.

Tài khoản có quyền rà soát không mặc nhiên có quyền phát sinh giao dịch bù trừ. Tách khả năng xem hồ sơ, đề xuất xử lý, phê duyệt và áp dụng theo mô hình vận hành thực tế. Mọi quyết định ngoại lệ phải có dấu vết thay vì mở một cờ bỏ qua authorization chung.

## 9. Từ phát hiện sang kiểm thử bản sửa

### 9.1. Mỗi quy tắc vi phạm cần một oracle cụ thể

| Kịch bản kiểm thử bằng dữ liệu tổng hợp | Kết quả phải chứng minh |
|---|---|
| Intent v3 được duyệt 40.000, sau đó sửa thành v4 400.000 | Không dùng approval v3 để gửi v4; không phát sinh hiệu ứng ngoài; dữ liệu giữ chỗ/ngoại lệ đúng hợp đồng |
| Người tenant B gọi action trên đơn tenant A | Không đọc/sửa ngoài quyền; không tạo outbox hay hiệu ứng ẩn cho đối tượng ấy |
| Người tạo tự duyệt khi bị cấm | Bị chặn tại bước duyệt và không thể thực hiện bằng đường API khác |
| Approval bị hủy trước mốc bắt buộc kiểm tra | Không thực hiện bằng quyết định cũ; kết luận dựa đúng hợp đồng thời điểm |
| Hai worker cùng thực hiện một intent đã duyệt | Số hiệu ứng và ghi nhận đúng giới hạn; không dùng cùng approval để nhân khoản hoàn |
| Replay cùng key với nội dung khác | Không tạo ý định thay thế hoặc âm thầm chấp nhận payload mới |
| Provider thành công rồi mất phản hồi | Đối soát ghi nhận đúng giao dịch cũ; không tạo khoản hoàn mới để “sửa” timeout |
| Chạy lại đề xuất bù trừ đã áp dụng | Không tạo điều chỉnh trùng; có thể truy về quyết định đã thực hiện |
| Gọi từ batch, API quản trị và worker thay vì giao diện | Các đường thực thi đều giữ cùng quy tắc bắt buộc |
| Yêu cầu hợp lệ, đúng tenant và đúng snapshot được duyệt | Nghiệp vụ hợp lệ vẫn thực hiện đúng; bản sửa không khóa toàn bộ luồng |

Với trường hợp từ chối, kiểm tra mã phản hồi chỉ là một phần. Cần kiểm tra dữ liệu đã commit, công việc bền vững, reservation và lịch sử provider để chứng minh không có hiệu ứng bị che phía sau phản hồi lỗi.

### 9.2. Test cuộc đua giữa phê duyệt, sửa và thực thi

Một test có điểm dừng kiểm soát có thể đi theo trình tự:

```text
1. Duyệt intent v3, amount 40.000.
2. Đường thực thi A đọc approval v3 rồi dừng trước bước chấp nhận/commit.
3. Đường sửa B cố đổi intent thành v4, amount 400.000.
4. Cho A tiếp tục; chạy các công việc đã commit tới mốc kiểm tra.
5. Đọc trạng thái bền vững, outbox, reservation và lịch sử fake provider.
```

Thiết kế có thể cấm B sửa khi intent đang thực hiện, hoặc cho sửa nhưng vô hiệu hóa approval cũ và buộc A phát hiện version đã đổi. Oracle phải khớp thiết kế đã chọn. Điều bắt buộc trong mô hình này là không được gửi 400.000 dựa trên phê duyệt cho 40.000.

Nếu A đã chấp nhận nguyên tử một snapshot 40.000 trước khi B tạo phiên bản mới, worker có thể được phép hoàn tất snapshot ấy theo hợp đồng. Test cần xác minh payload thực thi bất biến và liên kết với quyết định đã chấp nhận, thay vì mặc định mọi thay đổi xảy ra sau đó phải hủy được lệnh đã phát ra ngoài.

Một lock trong bộ nhớ của một tiến trình không chứng minh an toàn khi có nhiều worker. Một kiểm tra version cũng chỉ có tác dụng nếu đường cập nhật thực sự kiểm tra version và xử lý thất bại đúng cách. Kiểm thử tại database/ranh giới thực thi thật của cơ chế bảo vệ, dùng fake provider có lưu lịch sử hiệu ứng riêng.

### 9.3. Xác minh khả năng rà soát sau bản sửa

Ngoài chặn hành động sai, tạo một hành động hợp lệ và một hành động bị chặn để kiểm tra hồ sơ điều tra có nối được:

```text
requester/delegation → intent/version → approval snapshot
    → authorization decision → transaction/outbox
    → attempt/provider effect → posting/result
```

Không bắt buộc mọi mắt xích nằm trong một log. Điều cần chứng minh là bằng chứng có thể liên kết đáng tin cậy, được bảo vệ truy cập và có thể truy xuất trong phạm vi lưu giữ đã quy định. Khi một mắt xích bị mất trong test, quy trình phải báo thiếu bằng chứng thay vì tự kết luận hợp lệ.

## 10. Viết kết luận sự cố để người khác kiểm tra được

### 10.1. Những mục cần có trong hồ sơ kết luận

| Mục | Nội dung cụ thể |
|---|---|
| Hành động và đối tượng | Action/intent có phạm vi tenant, resource, amount/currency, các identity liên quan |
| Quy tắc áp dụng | Policy/hợp đồng, version, mốc đánh giá và điều kiện bắt buộc |
| Phát hiện về quyền | Điều kiện nào đạt/vi phạm/chưa xác định, kèm bằng chứng |
| Hiệu ứng thực tế | Commit local, posting, reservation và giao dịch ngoài đã xác nhận/chưa rõ |
| Phạm vi | Cửa sổ, kênh, phiên bản đã rà soát; số hồ sơ theo từng nhóm kết luận |
| Nguyên nhân | Cơ chế cụ thể khiến điều kiện bị bỏ qua hoặc dữ liệu kiểm tra khác dữ liệu thực thi |
| Xử lý và xác minh | Biện pháp chặn, bản sửa, kiểm thử và cách xử lý hậu quả đã được phép |
| Điểm còn mở | Dữ liệu thiếu, giả định, hồ sơ chờ đối soát, người/nhóm chịu trách nhiệm tiếp theo |

### 10.2. Ví dụ kết luận cho một hành động

> `action-execute-17` đã gửi 400.000 VND cho `refund-17` v4 thuộc `tenant-A/order-42`. Snapshot `approval-8` chỉ duyệt 40.000 VND ở v3. Hồ sơ provider trong phạm vi `provider-X/merchant-A` xác nhận giao dịch `provider-refund-91` thành công 400.000 VND. Hành động được xác nhận vi phạm ràng buộc nội dung/version phê duyệt và đã có hiệu ứng bên ngoài. Log `ALLOW` hiện có không phủ định vi phạm vì nhánh thực thi chỉ kiểm tra sự tồn tại của approval. Bằng chứng hiện tại xác định credential/requester và worker liên quan; chưa đủ để quy kết người thật đã chủ ý sửa nội dung.

Đoạn kết luận cần đi cùng tham chiếu bằng chứng có thể kiểm tra. “Lỗi do user”, “worker có quyền admin” hoặc “HTTP trả thành công” không phải giải thích đủ cho cơ chế vi phạm.

### 10.3. Điều kiện kết thúc cuộc rà soát

Đặt điều kiện kết thúc theo phạm vi đã thỏa thuận: đường gây lỗi đã được chặn và kiểm tra, tập action đã xác định được phân loại, hiệu ứng quan trọng đã đối soát, hồ sơ sửa hậu quả đã có kết quả hoặc được bàn giao rõ ràng, và bằng chứng cùng quyết định được lưu đúng nơi.

Không nhất thiết đợi biết được người thật đứng sau mọi request mới xác nhận lỗi nghiệp vụ. Ngược lại, bản vá đã triển khai cũng không đủ để nói tác động lịch sử đã xử lý xong. Những mục chưa hoàn tất cần có trạng thái và trách nhiệm tiếp theo, không bị xóa khỏi kết luận.

## 11. Những sai lầm làm lệch cuộc rà soát

- **Chỉ kiểm tra đăng nhập hoặc role:** bỏ qua đối tượng, nội dung được duyệt, state machine và phạm vi ủy quyền.
- **Dùng dữ liệu hiện tại để xét quá khứ:** role hoặc approval đã đổi có thể làm kết luận đảo ngược sự thật tại mốc thực thi.
- **Tin tuyệt đối vào `ALLOW`:** đầu vào policy có thể sai, thiếu điều kiện hoặc khác snapshot thực sự được dùng.
- **Gộp mọi timeout thành không có tác động:** tiền có thể đã đi ra dù ứng dụng chưa biết kết quả.
- **Chỉ rà endpoint công khai:** cùng lỗi có thể tồn tại ở batch, queue consumer, tác vụ vận hành hoặc API quản trị.
- **Join thiếu phạm vi identity:** gắn nhầm bằng chứng giữa tenant, merchant hoặc các đối tượng trùng ID.
- **Cộng số tiền sau join một-nhiều:** nhiều attempt làm số ảnh hưởng bị nhân lên, hoặc phép khử trùng làm mất giao dịch trùng thật.
- **Coi không có log là không có hành động:** lỗi ghi log, chính sách lưu giữ và độ trễ đọc đều có thể tạo khoảng trống.
- **Sửa approval hoặc xóa posting để đóng hồ sơ:** che mất vi phạm và phá khả năng đối chiếu.
- **Quy kết chủ ý từ subject ID:** xác định credential đã dùng khác xác định người thực hiện và động cơ.

## 12. Bài thực hành: rà soát một chuỗi thực hiện sai phê duyệt

Chuẩn bị fixture có hai tenant, hai nhân viên khác vai trò, một worker và fake provider có lịch sử độc lập. Tạo ba intent tổng hợp:

1. `refund-A`: duyệt và thực hiện cùng version, 40.000 VND; provider thành công.
2. `refund-B`: duyệt 40.000 rồi sửa 400.000; luồng lỗi vẫn gửi 400.000; provider thành công nhưng phản hồi bị mất.
3. `refund-C`: không tìm thấy log quyết định authorization; chưa có đủ lịch sử để xác định quyền, và chưa biết có hiệu ứng bên ngoài hay không.

Thực hiện các bước:

1. Lập timeline theo intent/action/attempt; tách thời điểm xảy ra và thời điểm thu thập bằng chứng.
2. Ghi điều kiện bắt buộc theo hợp đồng tổng hợp, gồm quyền theo đối tượng, version phê duyệt và số hiệu ứng được phép.
3. Đối chiếu snapshot, transaction, outbox và provider; không lấy timeout của `refund-B` làm bằng chứng thất bại cuối cùng.
4. Phân loại quyền và hiệu ứng riêng cho từng intent. Chỉ đánh dấu `refund-A` được phép khi đủ bằng chứng cho các điều kiện bắt buộc; giữ rõ khoảng trống của `refund-C`.
5. Viết truy vấn tìm các action có cùng dấu hiệu version/nội dung không khớp; ghi giới hạn bao phủ và kiểm tra đếm trùng.
6. Đề xuất chặn đường gửi sai snapshot, giữ nguyên bằng chứng và lập phương án xử lý hậu quả theo đúng thẩm quyền.
7. Tạo test hồi quy cho sửa-sau-duyệt, cuộc đua lúc thực thi, quyền theo tenant, replay và luồng hợp lệ; kiểm tra cả dữ liệu bền vững lẫn hiệu ứng bên ngoài.

Sản phẩm gồm bảng bằng chứng cho từng điều kiện, danh sách hành động theo nhóm kết luận, báo cáo tác động có phân biệt phần đã xác nhận/chưa rõ, và kết quả kiểm thử bản sửa. Một hồ sơ đạt phải chỉ ra được **hành động nào vi phạm điều kiện nào, bằng chứng nào chứng minh, hiệu ứng nào đã xảy ra và cơ chế nào ngăn tái diễn**.
