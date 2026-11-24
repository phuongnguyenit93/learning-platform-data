# Bằng chứng kiểm soát tài chính (Financial control evidence)

Trong chương **Compliance** của module bảo vệ logic nghiệp vụ, **financial control evidence** là bằng chứng giúp người có thẩm quyền kiểm tra rằng một kiểm soát liên quan đến tiền đã được thiết kế, thực thi và theo dõi đúng phạm vi. Ví dụ: khoản hoàn có đúng phê duyệt không, hạn mức có được giữ khi chạy đồng thời không, một ý định có tạo tiền trùng không và các giao dịch bên ngoài đã được đối soát chưa.

Một bảng tổng hợp có số dư đẹp hoặc một log ghi `ALLOW` chưa đủ trả lời các câu hỏi ấy. Bằng chứng phải nối được **quy tắc nghiệp vụ → quyết định có thẩm quyền → thay đổi đã commit → hiệu ứng thực tế → kết quả kiểm tra và xử lý ngoại lệ**. Chuỗi này cần bảo vệ quyền theo đối tượng, state machine, transaction và idempotency, đồng thời cho phép phát hiện sửa giá, bỏ qua phê duyệt, thao tác sai quyền hoặc xử lý trùng.

Bài học tập trung vào cách xây dựng bằng chứng kỹ thuật cho kiểm soát tài chính trong ứng dụng. Các số tiền, schema, định danh và kỳ báo cáo là ví dụ tổng hợp; yêu cầu kiểm soát và lưu giữ phải lấy từ chính sách có thẩm quyền áp dụng cho hệ thống. Một gói bằng chứng kỹ thuật riêng lẻ không tự tạo ra kết luận đáp ứng mọi nghĩa vụ tuân thủ.

## 1. Bằng chứng phải gắn với một khẳng định có thể kiểm tra

### 1.1. Phân biệt thiết kế, vận hành và kết quả

| Loại bằng chứng | Khẳng định nó hỗ trợ | Ví dụ | Điều chưa được chứng minh chỉ từ nguồn này |
|---|---|---|---|
| Thiết kế kiểm soát | Hệ thống có quy tắc và cơ chế bảo vệ được xác định | Đặc tả phê duyệt gắn với amount/version, ràng buộc database | Chưa chứng minh mọi giao dịch trong kỳ đã đi qua cơ chế ấy |
| Kiểm thử kiểm soát | Cơ chế hoạt động trong các kịch bản được kiểm tra | Test đổi amount sau duyệt, test callback trùng | Chưa chứng minh toàn bộ dữ liệu vận hành không có ngoại lệ |
| Thực thi trong kỳ | Những hành động cụ thể đã được kiểm soát như thế nào | Snapshot được duyệt, quyết định quyền, transaction/outbox đã commit | Chưa tự chứng minh tiền bên ngoài đã chuyển thành công |
| Kết quả và đối soát | Ghi nhận nội bộ khớp hiệu ứng thực tế, sai lệch đã được nhận diện | Provider transaction, posting, báo cáo đối soát, hồ sơ ngoại lệ | Không hợp thức hóa một lệnh tiền vốn thiếu thẩm quyền |
| Rà soát và xử lý ngoại lệ | Người/cơ chế được giao đã đánh giá và xử lý vấn đề | Kết luận, phê duyệt điều chỉnh, bằng chứng kiểm tra lại | Việc đóng ticket không tự chứng minh sai lệch đã hết |

Một kiểm soát có thể được thiết kế đúng nhưng bị bỏ qua ở API quản trị hoặc batch. Test đạt cũng có thể chỉ kiểm tra một worker trong khi môi trường vận hành có nhiều worker chạy đồng thời. Gói bằng chứng nên chỉ rõ mỗi tài liệu hỗ trợ lớp khẳng định nào.

### 1.2. Thuộc tính của bằng chứng hữu ích

- **Liên quan:** trả lời đúng mục tiêu kiểm soát, đúng đối tượng và loại hành động.
- **Có nguồn gốc:** biết dữ liệu đến từ đâu, được thu thập thế nào và bởi ai/cơ chế nào.
- **Đủ phạm vi:** có cơ sở xác định tập giao dịch cần kiểm tra, không chỉ các dòng thuận tiện lấy được.
- **Chính xác:** amount, currency, identity, trạng thái và phép tổng hợp được diễn giải đúng.
- **Đúng mốc:** phân biệt thời điểm xảy ra, commit, quan sát và thời điểm trích xuất.
- **Có thể truy lại:** nối được số tổng với giao dịch chi tiết và bằng chứng gốc.
- **Được bảo vệ:** giới hạn sửa/xóa và truy cập; phát hiện thay đổi theo cơ chế đã chọn.
- **Có thể lặp lại:** người rà soát có thể tái hiện phép tính hoặc hiểu vì sao kết quả thay đổi khi nguồn cập nhật.

Không có log lỗi không đồng nghĩa không có sai lệch. Có chữ ký hoặc hash cũng không tự chứng minh dữ liệu đầu vào là sự thật nghiệp vụ. Các thuộc tính trên bổ sung cho nhau.

## 2. Mô hình xuyên suốt: hoàn tiền có phê duyệt và hạn mức

### 2.1. Chốt các quy tắc cần chứng minh

Giả sử đơn `order-42` thuộc `tenant-A`, đã thu 1.000.000 VND. Trong mô hình này:

1. Mỗi refund intent có identity bền vững và nội dung gồm order, tenant, amount, currency, version.
2. Người có quyền phải duyệt đúng snapshot nội dung; người tạo không tự duyệt.
3. Khi chấp nhận thực hiện, hệ thống kiểm tra quyền theo đối tượng, hiệu lực phê duyệt và điều kiện trạng thái theo hợp đồng.
4. Tiền đang chờ kết quả được giữ chỗ; kết quả chưa xác định không được tự coi là thất bại cuối cùng.
5. Cùng intent chỉ được tạo một khoản hoàn thành công trong mô hình này.
6. Khi provider xác nhận thành công, ghi nhận nội bộ phải phản ánh đúng giao dịch ấy, kể cả khi phát hiện lệnh gốc có vi phạm.

Gọi `R` là tổng hạn mức hoàn được phép của đơn, `F` là tổng đã ghi nhận hoàn thành công và `P` là tổng đang giữ chỗ:

```text
R = 1.000.000 VND trong fixture
F >= 0
P >= 0
F + P <= R
Khả dụng để chấp nhận hoàn thêm = R - F - P
```

Đây là bất biến quản lý hạn mức nội bộ. Vẫn phải đối chiếu `F` với hiệu ứng bên ngoài để phát hiện khoản đã hoàn nhưng chưa ghi sổ hoặc khoản ghi sổ mà bên ngoài chưa xác nhận phù hợp.

### 2.2. Một bộ dữ liệu minh họa tại mốc chốt

| Hồ sơ | Nội dung | Trạng thái tại mốc chốt | Ghi nhận và giữ chỗ kỳ vọng |
|---|---|---|---|
| `refund-1` | Duyệt và thực hiện 40.000 VND | Provider thành công, local `SUCCEEDED` | Một nhóm posting hoàn 40.000; không còn giữ chỗ |
| `refund-2` | Duyệt và gửi 50.000 VND | Kết quả bên ngoài chưa xác định, local `PENDING` | Chưa ghi nhận thành công; giữ chỗ 50.000 và còn việc đối soát |
| `refund-3` | Duyệt 20.000 VND | Provider xác nhận thất bại cuối cùng phù hợp | Không có posting hoàn thành công; giữ chỗ đã giải phóng đúng một lần |
| Lần thử `attempt-denied-4` | Dùng approval 40.000 để yêu cầu 400.000 VND | Bị chặn trước khi chấp nhận thực hiện | Không có lệnh provider/outbox thực hiện hoặc giữ chỗ phát sinh từ lần thử này |

Tại mốc đó, local phải có `F = 40.000`, `P = 50.000`, khả dụng 910.000 VND. Khoản 50.000 chưa rõ kết quả không được cộng vào số hoàn thành công đã xác nhận, cũng không được coi là không có nghĩa vụ để giải phóng tùy tiện.

Lần thử bị chặn có thể chỉ có hồ sơ request/decision, chưa tạo refund intent. Vì vậy, “tất cả intent” không phải mẫu số đầy đủ cho kiểm soát ghi nhận các lần từ chối.

## 3. Lập ma trận kiểm soát và bằng chứng

### 3.1. Từ mục tiêu đến nguồn kiểm tra

| Mục tiêu kiểm soát | Quy tắc cần kiểm tra | Bằng chứng chính | Dấu hiệu cần điều tra |
|---|---|---|---|
| Thực hiện đúng thẩm quyền | Subject được phép với action và đúng tenant/resource tại mốc quy định | Quyết định quyền, lịch sử quyền/ủy quyền và snapshot đối tượng | `ALLOW` cho resource sai tenant; thiếu căn cứ quyền cần thiết |
| Giữ nguyên nội dung đã duyệt | Intent/version/amount/currency thực hiện khớp snapshot được duyệt | Approval snapshot và payload thực thi bền vững | Duyệt 40.000 nhưng gửi 400.000; dùng approval đã hủy |
| Phân tách nhiệm vụ | Người tạo và người duyệt đáp ứng hợp đồng | Danh tính hiệu lực, chuỗi ủy quyền, quyết định duyệt | Tự duyệt qua tài khoản/đường xử lý không được phép |
| Không vượt hạn mức | Kiểm tra và cập nhật hạn mức được bảo vệ trước tranh chấp | Reservation, tổng hợp đúng mốc, transaction/version, test đồng thời | Âm giữ chỗ, `F + P > R`, hai worker cùng dùng một phần hạn mức |
| Không tạo hiệu ứng trùng | Cùng intent có số giao dịch tiền đúng hợp đồng | Business identity, attempt, idempotency scope và lịch sử provider | Hai giao dịch thành công cho một intent |
| Ghi nhận đầy đủ và đúng | Hiệu ứng đã xác nhận có ghi nhận tương ứng đúng nội dung | Provider transaction, nhóm posting và liên kết nguồn | Giao dịch ngoài sổ; posting sai amount/currency |
| Không bỏ sót sai lệch | Đối soát đúng tập và có xử lý các trường hợp chưa khớp | Manifest phạm vi, kết quả từng identity, watermark và ngoại lệ | Báo cáo chỉ chứa dòng khớp; checkpoint đi qua hồ sơ chưa xử lý |
| Sửa hậu quả đúng quyền | Điều chỉnh có phê duyệt và không áp dụng trùng | Hồ sơ ngoại lệ, quyết định điều chỉnh, liên kết giao dịch gốc | Sửa approval hồi tố; xóa posting để che sai lệch |

Mỗi dòng cần có người/nhóm chịu trách nhiệm, cách kiểm tra, tần suất theo chính sách, phạm vi dữ liệu và tiêu chí đạt/không đạt/chưa đủ bằng chứng. Không tự chọn một chu kỳ rà soát hoặc thời hạn lưu giữ rồi coi đó là yêu cầu chung cho mọi hệ thống.

### 3.2. Định nghĩa kết luận trước khi tạo báo cáo

- **Đạt trong phạm vi đã kiểm tra:** đủ bằng chứng và quy tắc kiểm soát được thỏa mãn.
- **Có ngoại lệ đã xác nhận:** có bằng chứng một điều kiện bị vi phạm; phải chỉ rõ identity, tác động và cách xử lý.
- **Chưa đủ bằng chứng:** thiếu nguồn, mốc chốt hoặc liên kết cần thiết để đưa ra kết luận.
- **Chưa đến điều kiện kết luận cuối:** ví dụ giao dịch đang xử lý trong khoảng thời gian được hợp đồng chấp nhận; vẫn cần kiểm tra giữ chỗ, tuổi hồ sơ và lịch xử lý tiếp.

Một trạng thái `PENDING` hợp lệ tại mốc chốt không tự là thất bại của mọi kiểm soát. Nhưng một record treo quá điều kiện theo chính sách hoặc không còn việc đối soát bền vững có thể là ngoại lệ. Hãy nêu điều kiện thay vì tô tất cả màu xanh hoặc coi mọi trạng thái trung gian là sai.

## 4. Sinh bằng chứng tại đúng ranh giới transaction

### 4.1. Nối các identity có ý nghĩa

```text
tenant + resource + business intent + version
    → approval snapshot + authorization decision
    → transaction/reservation + outbox work
    → attempt + provider/merchant scope + external transaction
    → posting group + reconciliation result
    → exception/remediation decision nếu có
```

Giữ riêng requester, người duyệt, danh tính thực thi và người áp dụng điều chỉnh. Worker có quyền kỹ thuật gọi provider không thay thế quyết định nghiệp vụ cho phép hoàn tiền. Nếu có ủy quyền hoặc impersonation hợp lệ, cần theo được danh tính gốc, danh tính hiệu lực và phạm vi hành động theo hợp đồng.

Không dùng `traceId` làm identity duy nhất của intent; retry hoặc callback có thể mang trace khác. Provider transaction ID cần kèm phạm vi mà ID ấy duy nhất, chẳng hạn provider và merchant account.

### 4.2. Ghi ý định và bằng chứng chấp nhận cùng thay đổi local

Với mô hình các bản ghi liên quan nằm trong cùng database transaction, một luồng chấp nhận có thể được đặc tả như sau:

```text
BEGIN TRANSACTION
    đọc/khóa hoặc kiểm tra version của intent và dữ liệu hạn mức
    xác minh tenant, quyền, state và snapshot được duyệt
    kiểm tra F + P + amount_mới <= R
    ghi intent thực thi với payload đã chấp nhận
    ghi giữ chỗ
    ghi outbox công việc gửi lệnh
    ghi bản ghi/sự kiện bền vững về quyết định chấp nhận
COMMIT

worker đọc outbox đã commit
    → gọi provider theo identity/idempotency contract
    → ghi nhận kết quả bằng giao thức được đặc tả
```

Sự kiện chấp nhận ở đây chứng minh quyết định và dữ liệu local đã commit khi nó thực sự nằm trong transaction ấy; không chứng minh provider đã hoàn tiền. Ghi một log `SUCCESS` trước commit rồi transaction rollback sẽ tạo bằng chứng sai nếu báo cáo không phân biệt.

Nếu đẩy audit sang hệ khác bất đồng bộ, cần chỉ rõ nguồn bền vững gốc, khả năng phát lại, phát hiện thiếu và kiểm soát độ trễ. Outbox có thể được giao nhiều lần; consumer cần giữ identity sự kiện để xử lý lặp đúng semantics. Không coi “gửi message một lần” là bảo đảm mọi hệ lưu trữ cùng commit nguyên tử.

Đối với request bị từ chối, transaction nghiệp vụ có thể rollback hoặc chưa bắt đầu. Nếu bằng chứng từ chối là yêu cầu của kiểm soát, đường ghi đó cần được thiết kế để không bị mất cùng rollback. Hành vi khi không ghi được bằng chứng tối thiểu phải có chính sách rõ, kiểm thử được và không âm thầm làm mất khả năng rà soát.

### 4.3. Trường dữ liệu cần đủ để kiểm tra, không thu thập tràn lan

Một sự kiện minh họa cho kết quả đối soát:

```json
{
  "eventId": "recon-event-72",
  "eventType": "REFUND_RECONCILED",
  "schemaVersion": 1,
  "tenantId": "tenant-A",
  "intentId": "refund-1",
  "intentVersion": 3,
  "approvalId": "approval-11",
  "policyVersion": "refund-policy-6",
  "amountMinor": 40000,
  "currency": "VND",
  "providerScope": "provider-X/merchant-A",
  "providerTransactionId": "provider-refund-91",
  "postingGroupId": "posting-refund-1",
  "result": "MATCHED",
  "observedAt": "2026-11-01T02:00:00Z",
  "evidenceRefs": ["provider-extract-91", "posting-snapshot-31"]
}
```

Trong fixture này, đơn vị nhỏ nhất được dùng cho VND là một đồng. Với currency khác phải lấy quy tắc biểu diễn từ hợp đồng dữ liệu; không mặc định mọi currency cùng có hai chữ số thập phân. Dùng kiểu số chính xác hoặc số nguyên theo đơn vị đã thống nhất, không dùng số thực dấu phẩy động để cộng tiền.

`result: MATCHED` cần đi cùng khả năng kiểm tra lại hai phía, không phải chỉ một nhãn. Không ghi credential, token, dữ liệu thẻ đầy đủ hoặc thông tin cá nhân không cần thiết vào sự kiện. Tham chiếu tới nguồn được kiểm soát truy cập thường phù hợp hơn sao chép toàn bộ payload nhạy cảm vào mọi log.

## 5. Chứng minh phạm vi và tính đầy đủ của tập dữ liệu

### 5.1. Chọn tập giao dịch và mốc thời gian rõ ràng

Các tập dưới đây có thể khác nhau:

| Tập kiểm tra | Câu hỏi phù hợp |
|---|---|
| Intent được chấp nhận trong kỳ | Các quyết định chấp nhận của kỳ có đúng quyền/phê duyệt không? |
| Giao dịch bên ngoài phát sinh trong kỳ | Mọi hiệu ứng tiền của kỳ đã được nhận diện và đối chiếu chưa? |
| Hồ sơ chưa kết thúc tại mốc chốt, kể cả nhận từ kỳ trước | Tiền giữ chỗ và nghĩa vụ chưa xác định có được quản lý đúng không? |
| Các lần yêu cầu bị từ chối trong kỳ | Những lần từ chối có bằng chứng và có thật sự không tạo hiệu ứng không? |
| Điều chỉnh được áp dụng trong kỳ | Hậu quả có được sửa đúng quyền, đúng nội dung, không trùng không? |

Đừng lấy tập intent tạo trong kỳ rồi tuyên bố đã bao phủ mọi khoản hoàn phát sinh trong kỳ. Intent cũ có thể được thực hiện muộn; giao dịch bên ngoài cũng có thể chưa có cặp local do lỗi hoặc phục hồi dữ liệu.

Quy định cửa sổ, ví dụ `[period_start, period_end)`, múi giờ và ý nghĩa timestamp dùng lọc. Phân biệt `occurred_at`, `committed_at`, `observed_at` và thời điểm xuất dữ liệu. Dùng mốc đầu bao gồm/cuối loại trừ giúp tránh đếm một ranh giới vào hai kỳ, nhưng không tự giải quyết dữ liệu đến muộn hoặc lệch đồng hồ.

### 5.2. Đối chiếu nhiều hướng, không chỉ liệt kê các cặp khớp

Ít nhất cần xem các hướng liên quan đến mục tiêu kiểm soát:

```text
Intent local → approval/authorization → provider → posting
Provider effect → intent local và posting tương ứng
Posting tài chính → nguồn nghiệp vụ và bằng chứng hiệu ứng phù hợp
Request bị từ chối → kiểm tra không có hiệu ứng trái phép liên quan
Ngoại lệ → quyết định xử lý và kết quả kiểm tra lại
```

Quét từ local sang provider tìm kết quả cho những intent đã biết. Quét từ provider về local giúp phát hiện giao dịch ngoài sổ, bao gồm trường hợp dữ liệu local bị mất. Quét từ posting về nguồn giúp tìm khoản ghi nhận không có căn cứ thích hợp. Chỉ dùng phép join trả về các dòng khớp sẽ loại khỏi báo cáo chính các sai lệch cần nhìn thấy.

Khi hệ thống ngoài có độ trễ công bố, xác định watermark, khoảng quét bù và cách phát hiện bản cập nhật muộn theo hợp đồng. Giữ record chưa rõ trong tập cần theo dõi; không coi một lần `NOT_FOUND` là bằng chứng chắc chắn chưa có hiệu ứng.

### 5.3. Snapshot và checkpoint cũng là một phần của bằng chứng

Đọc intent, reservation và posting ở các thời điểm khác nhau có thể tạo một tổ hợp chưa từng tồn tại. Dùng snapshot nội bộ phù hợp hoặc lưu đủ thông tin version/mốc để diễn giải. Giữa database và provider thường không có một transaction đọc chung, nên báo cáo phải chỉ rõ mốc chốt, độ trễ và trường hợp chưa thể đối chiếu cuối cùng.

Với job theo batch, checkpoint phải cho biết phần nào đã xử lý và phần nào còn việc bền vững để quay lại. Nếu job dừng giữa batch, chạy tiếp không được bỏ sót identity hoặc áp dụng lại điều chỉnh. Đối chiếu tập identity kỳ vọng, không chỉ tổng số lượt xử lý: hai lần đếm một intent có thể che việc bỏ mất một intent khác.

## 6. Kiểm tra số tiền và ghi nhận mà không suy diễn quá bằng chứng

### 6.1. Phân biệt request, hiệu ứng và dòng sổ

Một intent có thể có nhiều request do retry, nhưng vẫn chỉ một giao dịch hoàn thành công. Một lần ghi nhận nghiệp vụ có thể gồm nhiều dòng debit/credit. Vì vậy cần xác định rõ đang đếm:

- Số intent duy nhất theo phạm vi tenant/nghiệp vụ.
- Số attempt hoặc delivery.
- Số giao dịch bên ngoài thực sự thành công theo phạm vi provider/merchant.
- Số nhóm posting nghiệp vụ và các dòng sổ cấu thành.

Hai request không tự có nghĩa hai khoản hoàn; một posting group không tự chứng minh bên ngoài chỉ có một giao dịch. Đếm đúng lớp là điều kiện để báo cáo có ý nghĩa.

### 6.2. Ví dụ truy vấn phát hiện thiếu ghi nhận

Giả sử bản trích xuất có `refund_intent` và `refund_posting_group`, với identity intent duy nhất trong tenant. Truy vấn minh họa sau tìm các intent được chấp nhận trong kỳ, hiện đánh dấu thành công nhưng thiếu nhóm posting hoàn thành công:

```sql
SELECT
    i.tenant_id,
    i.intent_id,
    i.amount_minor,
    i.currency,
    i.accepted_at,
    i.state
FROM refund_intent i
WHERE i.accepted_at >= :period_start
  AND i.accepted_at < :period_end
  AND i.state = 'SUCCEEDED'
  AND NOT EXISTS (
      SELECT 1
      FROM refund_posting_group p
      WHERE p.tenant_id = i.tenant_id
        AND p.intent_id = i.intent_id
        AND p.posting_type = 'REFUND_SUCCESS'
  )
ORDER BY i.accepted_at, i.tenant_id, i.intent_id;
```

Đây là truy vấn chỉ đọc trên schema tổng hợp; dùng tham số và quyền truy cập được phép. `NOT EXISTS` tránh nhân dòng khi một bảng có nhiều bản ghi liên quan. Truy vấn không chứng minh amount của nhóm posting đang có là đúng, không tìm mọi giao dịch provider ngoài sổ, và không tái hiện trạng thái tại cuối kỳ nếu đang đọc dữ liệu hiện tại. Muốn kiểm tra lịch sử cần snapshot hoặc lịch sử trạng thái theo đúng mốc đã chọn.

Nếu giao thức ghi sổ cho phép bước bất đồng bộ, thiếu posting có thể là trạng thái trung gian trong giới hạn hợp đồng. Kết luận phải xét tuổi hồ sơ, trạng thái công việc và mốc dữ liệu trước khi phân loại ngoại lệ. Một truy vấn trả về 0 dòng chỉ hỗ trợ điều kiện hẹp mà nó đã kiểm tra.

### 6.3. Những phép tổng hợp cần thận trọng

Không cộng lẫn currency; quy đổi để báo cáo phải có quy tắc, nguồn tỷ giá và thời điểm đã được phê chuẩn cho mục đích ấy. Tách principal, fee, tax, adjustment và các trạng thái chờ/thành công theo mô hình sổ, không tự ép mọi chênh lệch về một cột “refund amount”.

Sổ cân bằng debit/credit không chứng minh giao dịch được cấp phép: một khoản hoàn trái phép vẫn có thể được ghi bằng bút toán cân bằng. Tương tự, hai sai lệch ngược chiều có thể làm tổng cuối kỳ khớp. Cần kiểm tra liên kết và nội dung từng giao dịch bên cạnh số tổng.

## 7. Đóng gói bằng chứng để người khác có thể kiểm tra lại

### 7.1. Gói bằng chứng cần có cả dữ liệu và cách tạo dữ liệu

| Thành phần | Nội dung cần giữ |
|---|---|
| Phạm vi và tiêu chí | Mục tiêu kiểm soát, tập giao dịch, mốc chốt, múi giờ, tiêu chí kết luận |
| Nguồn trích xuất | Snapshot/version, nguồn hệ thống, thời điểm lấy, watermark, giới hạn đã biết |
| Dữ liệu chi tiết | Identity, nội dung được duyệt, hành động, giao dịch ngoài, nhóm posting và kết quả liên kết |
| Phương pháp | Query/script version, tham số, ánh xạ trạng thái/currency, quy tắc đếm và tổng hợp |
| Kết quả | Các kiểm tra đã chạy, số tổng theo lớp, dòng đạt, ngoại lệ, hồ sơ chưa đủ bằng chứng |
| Rà soát | Người/cơ chế tạo, người có trách nhiệm kiểm tra, kết luận và tham chiếu quyết định |
| Tính toàn vẹn | Danh mục artifact, kích thước/digest, cơ chế bảo vệ và lịch sử phiên bản |
| Xử lý tiếp | Chủ thể phụ trách ngoại lệ, việc cần làm, hạn theo chính sách và kết quả kiểm tra lại |

Một PDF chụp màn hình báo cáo có thể hỗ trợ trình bày, nhưng thường thiếu tập chi tiết và phương pháp để tái hiện. Giữ đường truy từ dòng tổng tới identity và nguồn được phép truy cập, thay vì yêu cầu người rà soát tin vào ảnh chụp.

### 7.2. Manifest minh họa

Ví dụ dưới đây mô tả một gói tổng hợp cho kỳ tháng 10 theo UTC. Bộ ba intent và một lần thử bị chặn ở phần trước được đặt trong kỳ này; thông tin provider/local được thu thập sau mốc chốt để dựng lại trạng thái theo hợp đồng dữ liệu.

```json
{
  "evidencePackageId": "financial-evidence-2026-10-r1",
  "controlSetVersion": "refund-controls-3",
  "periodStart": "2026-10-01T00:00:00Z",
  "periodEndExclusive": "2026-11-01T00:00:00Z",
  "asOf": "2026-11-01T00:00:00Z",
  "generatedAt": "2026-11-01T02:05:00Z",
  "populationRuleVersion": "refund-populations-2",
  "querySetVersion": "financial-evidence-query-7",
  "localSnapshotRef": "local-snapshot-13",
  "providerExtractRef": "provider-extract-13",
  "integrityInventoryRef": "artifact-inventory-13",
  "acceptedIntentCount": 3,
  "deniedRequestCount": 1,
  "confirmedSuccessfulExternalRefundCount": 1,
  "unknownExternalResultIntentCount": 1,
  "openFollowUpRefs": ["follow-up-refund-2"],
  "limitations": [
    "refund-2 chưa xác định kết quả bên ngoài tại mốc chốt"
  ]
}
```

Các con số có mẫu số khác nhau nên không được cộng tùy ý. Một giao dịch đã xác nhận thành công không có nghĩa tổng giao dịch thành công thực sự cuối cùng chỉ là một: `refund-2` vẫn chưa rõ. `asOf` khác `generatedAt`; báo cáo phải nêu dữ liệu nào đủ khả năng tái hiện mốc chốt và phần nào còn chưa xác định.

Danh mục tính toàn vẹn cần liệt kê artifact thật và digest được tính từ đúng byte đã lưu. Nếu artifact được biến đổi để chuẩn hóa hoặc che dữ liệu, lưu phiên bản/quy tắc biến đổi và quan hệ với nguồn. Không điền một chuỗi hash tượng trưng rồi coi như đã có kiểm tra tính toàn vẹn.

### 7.3. Chạy lại phải có semantics rõ

Chạy lại trên cùng snapshot, cùng phương pháp và cùng tham số phải cho cùng kết quả nghiệp vụ, trừ trường được xác định là metadata của lần chạy. Để đạt điều đó, cần thứ tự ổn định, quy tắc làm tròn/đếm rõ ràng và cách xử lý bản ghi trùng được đặc tả.

Chạy lại trên dữ liệu mới có thể thấy callback muộn hoặc kết quả provider mới. Khi đó tạo phiên bản gói mới, giải thích khác biệt và liên kết gói cũ. Không ghi đè âm thầm báo cáo trước để làm biến mất ngoại lệ đã từng được ghi nhận.

## 8. Bảo vệ bằng chứng và giới hạn quyền truy cập

### 8.1. Tính toàn vẹn không chỉ là thêm hash

Digest giúp phát hiện dữ liệu thay đổi so với digest tham chiếu đáng tin cậy. Nếu cùng một người có thể sửa cả dữ liệu lẫn danh mục digest mà không có dấu vết, cơ chế đó có giới hạn rõ ràng. Cần kết hợp quyền truy cập, lịch sử phiên bản, nguồn tham chiếu được bảo vệ và cơ chế theo dõi sửa/xóa phù hợp.

Nếu sử dụng chữ ký số, dấu thời gian hoặc cơ chế lưu không cho sửa trong thời hạn đã chọn, ghi rõ phạm vi bảo vệ và cách kiểm tra theo thiết kế. Những cơ chế này hỗ trợ xác thực nguồn/tính toàn vẹn trong mô hình tin cậy của chúng; chúng không chứng minh amount ban đầu được phê duyệt đúng, tập dữ liệu đã đầy đủ hoặc không có giao dịch ngoài sổ.

Tách quyền tạo nghiệp vụ, sửa dữ liệu vận hành, xuất bằng chứng, rà soát và áp dụng điều chỉnh theo mô hình kiểm soát đã phê chuẩn. Với quyền khẩn cấp, giữ lý do, phạm vi, thời điểm sử dụng và rà soát sau đó; không để một tài khoản có thể vừa sửa nguồn, xóa dấu vết và tự xác nhận mọi thứ hợp lệ mà không có kiểm soát bù phù hợp.

### 8.2. Bằng chứng đủ dùng không có nghĩa sao chép mọi dữ liệu

Người rà soát cần đúng dữ liệu cho nhiệm vụ được giao. Dùng định danh đã che hoặc tham chiếu khi đủ để đối chiếu; chỉ người có quyền thích hợp mới mở được chi tiết nhạy cảm. Giữ liên kết nhất quán giữa các artifact đã che để việc đối chiếu không bị phá vỡ.

Quyền tải báo cáo tổng không mặc nhiên cho phép tải payload thanh toán hoặc dữ liệu mọi tenant. Kiểm tra cả API xuất, file tải xuống, vị trí lưu và quyền chia sẻ gói bằng chứng. Log truy cập cũng không nên vô tình ghi lại secret trong tham số hoặc nội dung request.

Thời hạn lưu giữ, cách xóa và trường hợp phải giữ lại được quyết định theo chính sách/nghĩa vụ áp dụng đã được xác định. Áp dụng nhất quán cho nguồn, bản trích xuất, backup và artifact dẫn xuất liên quan. Chỉ giữ một bản tổng đã hết liên kết tới nguồn cần thiết có thể làm gói bằng chứng mất khả năng kiểm tra.

## 9. Rà soát ngoại lệ và chứng minh việc khắc phục

### 9.1. Bản báo cáo cần hiện cả kết quả không thuận lợi

Người/cơ chế rà soát cần kiểm tra phạm vi và chất lượng đầu vào trước khi đọc tỷ lệ khớp. Nếu provider extract thiếu một merchant account hoặc job mới quét nửa kỳ, tỷ lệ khớp cao trên phần đã đọc vẫn không chứng minh toàn bộ phạm vi.

Các ngoại lệ nên phân biệt được:

- Thiếu phê duyệt/quyền hoặc nội dung thực thi không khớp nội dung được phép.
- Giao dịch bên ngoài không có intent/posting tương ứng.
- Posting không có nguồn nghiệp vụ hoặc bằng chứng hiệu ứng phù hợp.
- Amount, currency, resource hoặc phạm vi merchant không khớp.
- Nhiều hiệu ứng thành công cho một intent chỉ được phép một khoản hoàn.
- Trạng thái chưa xác định, đối soát quá hạn hoặc mất công việc xử lý tiếp.
- Thiếu bằng chứng do trích xuất, liên kết, lưu giữ hoặc ghi nhận sự kiện.

Không gộp tất cả thành “reconciliation failed” rồi chỉ lưu số đếm. Mỗi hồ sơ cần identity, loại sai lệch, bằng chứng, mức chắc chắn về tác động và trách nhiệm xử lý.

### 9.2. Tách sự thật tài chính khỏi tính hợp lệ của hành động

Giả sử provider đã hoàn 400.000 dù approval chỉ cho phép 40.000. Hệ thống phải phản ánh đúng 400.000 thực sự đã đi ra theo mô hình sổ và ghi nhận vi phạm, thay vì sửa sổ thành 40.000 để khớp approval.

Nếu cần bù trừ hoặc điều chỉnh, tạo nghiệp vụ mới có thẩm quyền, lý do, liên kết giao dịch gốc và idempotency phù hợp. Không sửa approval hồi tố để biến giao dịch cũ thành “đã được duyệt”, không xóa posting để đóng ngoại lệ và không tự phát lệnh thu hồi tiền từ báo cáo.

Một kết quả đối soát “khớp provider” có thể đồng thời đi cùng ngoại lệ “lệnh gốc không được phép”. Kết luận theo từng kiểm soát tránh việc một nhãn `MATCHED` che mất vi phạm quyền hoặc quy trình phê duyệt.

### 9.3. Đóng ngoại lệ phải có kiểm tra lại

Hồ sơ đóng cần nêu nguyên nhân, quyết định xử lý, người/cơ chế có quyền áp dụng, thay đổi thực tế và bằng chứng kiểm tra sau thay đổi. Nếu một phần chưa giải quyết được, giữ trạng thái mở hoặc bàn giao rõ theo chính sách; không dùng “đã tạo ticket” thay cho “đã xử lý”.

Trước khi áp dụng một đề xuất, kiểm tra lại version, trạng thái, quyền và bằng chứng hiện hành. Hai người áp dụng cùng đề xuất hoặc job chạy lại không được tạo hai điều chỉnh. Người có quyền xem/rà soát bằng chứng không mặc nhiên có quyền thực hiện giao dịch tiền.

Phân biệt người tạo gói, người rà soát, người phê duyệt xử lý và người áp dụng nếu mô hình yêu cầu. Thời điểm rà soát phải có ý nghĩa: một chữ ký xác nhận trước khi dữ liệu được chốt không chứng minh đã rà soát tập dữ liệu cuối cùng.

## 10. Kiểm thử chính đường tạo bằng chứng

### 10.1. Cơ chế kiểm soát và báo cáo đều có thể lỗi

| Kịch bản kiểm thử | Điều phải chứng minh |
|---|---|
| Transaction chấp nhận rollback | Không có bằng chứng “đã chấp nhận/đã hoàn” sai và không có outbox thực hiện từ transaction bị hủy |
| Commit thành công nhưng caller mất phản hồi | Có thể đọc lại quyết định bền vững bằng identity; không tạo intent thay thế chỉ vì timeout |
| Audit sink tạm ngừng | Nguồn bền vững và việc phát lại theo thiết kế không mất sự kiện; độ trễ/thiếu bằng chứng được phát hiện |
| Outbox/event giao trùng hoặc đảo thứ tự | Báo cáo không nhân hiệu ứng tiền hoặc kéo trạng thái cuối lùi theo sự kiện cũ |
| Provider thành công nhưng local mất kết quả | Gói bằng chứng giữ trạng thái chưa xác định rồi cập nhật theo bằng chứng mới; không suy ra thất bại từ timeout |
| Thiếu một merchant account trong extract | Báo cáo đánh dấu phạm vi thiếu, không đưa kết luận toàn bộ kiểm soát đạt |
| Giao dịch ngoài sổ và posting thiếu nguồn | Các lượt quét ngược tìm được đúng identity, không biến mất do join chỉ lấy dòng khớp |
| Hai sai lệch bù nhau về số tổng | Kiểm tra chi tiết vẫn phát hiện cả hai, dù tổng cuối trông khớp |
| Callback đến sau mốc chốt | Báo cáo áp dụng đúng quy tắc cutoff/late arrival và quản lý phiên bản kết quả |
| Job dừng sau một record nhưng trước checkpoint | Chạy lại không bỏ sót identity và không áp dụng điều chỉnh trùng |
| Artifact bị sửa sau khi đóng gói | Kiểm tra toàn vẹn phát hiện thay đổi theo cơ chế đã thiết kế |
| Người tenant B tải gói của tenant A | Kiểm soát quyền xuất/xem chặn truy cập ngoài phạm vi |

Fake provider cần giữ lịch sử giao dịch độc lập để test hiệu ứng ngoài sổ. Một mock luôn trả lại chính amount từ database local không kiểm tra được khả năng phát hiện hai nguồn khác nhau.

### 10.2. Dùng tập kỳ vọng độc lập

Với fixture ở phần 2, harness biết trước ba intent đã chấp nhận và một lần thử bị chặn. Kiểm tra tập identity xuất hiện trong từng danh sách, không chỉ tổng số dòng. Khi cố tình bỏ `refund-2` khỏi đầu vào hoặc nhân đôi attempt của `refund-1`, pipeline phải phát hiện thiếu hoặc không đếm trùng sai lớp.

Kiểm tra đồng thời các giá trị local `F = 40.000`, `P = 50.000`, khả dụng 910.000, cùng bằng chứng một khoản hoàn thành công 40.000 đã xác nhận. Khoản 50.000 chưa rõ được trình bày riêng và còn việc đối soát; không khẳng định tổng hiệu ứng bên ngoài cuối cùng chỉ là 40.000.

Các oracle này đến từ kịch bản được dựng độc lập với hàm tổng hợp của báo cáo. Không dùng chính kết quả query cần kiểm tra làm dữ liệu kỳ vọng cho query ấy.

### 10.3. Kiểm tra tính lặp lại và việc sửa báo cáo

Chạy hai lần trên cùng snapshot/phương pháp phải giữ cùng tập identity, kết luận và số tiền nghiệp vụ. Thử thay đổi snapshot bằng cách bổ sung kết quả cuối của `refund-2`; báo cáo mới phải giải thích được khác biệt, giữ bản cũ và không bỏ dấu vết hồ sơ từng chưa xác định.

Nếu hai lần chạy khác nhau chỉ vì thứ tự dòng hoặc thời điểm tạo gói, không nhầm đó là thay đổi tài chính. Ngược lại, cùng số tổng nhưng đổi identity hoặc trạng thái của các giao dịch vẫn là khác biệt cần kiểm tra.

## 11. Đọc một gói bằng chứng minh họa

### 11.1. Kết luận theo từng hồ sơ

| Hồ sơ | Bằng chứng cần thấy | Kết luận hợp lý trong fixture |
|---|---|---|
| `refund-1` | Approval đúng 40.000, quyền/đối tượng đúng, provider thành công, posting đúng và hết giữ chỗ | Các kiểm soát tương ứng đạt nếu đủ toàn bộ bằng chứng bắt buộc |
| `refund-2` | Approval đúng 50.000, kết quả chưa rõ, giữ chỗ 50.000, việc đối soát và tuổi hồ sơ đúng chính sách | Kiểm soát giữ chỗ/xử lý chưa xác định có thể đạt; chưa có kết luận thành công cuối cùng |
| `refund-3` | Thất bại cuối cùng cho đúng identity, không có khoản hoàn thành công, giải phóng giữ chỗ đúng một lần | Kết thúc thất bại theo hợp đồng; không phải mọi thất bại nghiệp vụ đều là lỗi kiểm soát |
| `attempt-denied-4` | Nội dung 400.000 không khớp approval 40.000, bằng chứng từ chối, không có hiệu ứng từ lần thử | Kiểm soát ràng buộc nội dung đã chặn được trường hợp sai trong phạm vi kiểm tra |

Nếu chỉ có trạng thái `SUCCEEDED` cho `refund-1` mà không có bằng chứng quyền hoặc hiệu ứng cần thiết, chưa thể đánh dấu tất cả kiểm soát đạt. Nếu `refund-2` vượt điều kiện xử lý theo chính sách hoặc mất work item, phải chuyển kết luận phù hợp sang ngoại lệ dù số tổng hạn mức vẫn đúng.

### 11.2. Ví dụ kết luận có giới hạn rõ ràng

> Gói minh họa bao phủ ba refund intent đã chấp nhận trong kỳ và một lần yêu cầu bị từ chối theo tập fixture. Đã xác nhận một giao dịch bên ngoài 40.000 VND khớp nhóm posting tương ứng; một intent 50.000 VND vẫn chưa xác định kết quả và được giữ chỗ, có hồ sơ theo dõi. Local tại mốc chốt có tổng đã hoàn 40.000, giữ chỗ 50.000 và khả dụng 910.000 VND. Lần yêu cầu 400.000 dựa trên approval 40.000 bị chặn trước hiệu ứng. Kết luận đối với từng kiểm soát dựa trên nguồn, snapshot và giới hạn được liệt kê trong gói; chưa có kết luận thành công cuối cùng cho intent 50.000.

Người rà soát cần mở được tham chiếu để kiểm tra những khẳng định trên. Một đoạn tóm tắt đúng về số tiền nhưng không có tập dữ liệu và phương pháp hỗ trợ vẫn chưa phải gói bằng chứng đầy đủ.

### 11.3. Các dấu hiệu thường làm bằng chứng mất giá trị

- Chỉ cung cấp policy hoặc test, không có dữ liệu thực thi trong phạm vi cần đánh giá.
- Gán tất cả trạng thái trung gian thành thành công, hoặc loại chúng khỏi mẫu số mà không giải thích.
- Dùng role/approval hiện tại để kết luận về hành động trong quá khứ.
- Chỉ xuất các dòng đã khớp và bỏ giao dịch ngoài sổ, dòng thiếu bằng chứng hoặc tenant chưa thu thập.
- Cộng amount sau join một-nhiều, cộng khác currency hoặc lẫn principal với fee.
- Tin rằng sổ cân bằng, hash hợp lệ hoặc provider thành công là đủ chứng minh mọi kiểm soát đạt.
- Lưu `traceId` nhưng thiếu business identity, snapshot được duyệt và phạm vi provider cần thiết.
- Ghi đè gói cũ, sửa approval hồi tố hoặc đóng ticket mà không có bằng chứng kiểm tra lại.
- Cho người tạo nghiệp vụ tự sửa nguồn, xóa bằng chứng và tự xác nhận kết quả mà không có kiểm soát phù hợp.
- Không nêu truy vấn, tham số, mốc dữ liệu, quy tắc làm tròn/đếm hoặc khoảng trống còn lại.

## 12. Bài thực hành: xây gói bằng chứng cho luồng hoàn tiền

Từ fixture ở phần 2, thực hiện các bước:

1. Viết ma trận tối thiểu cho quyền theo đối tượng, phê duyệt đúng nội dung, hạn mức, chống trùng, ghi nhận và đối soát.
2. Chốt từng tập dữ liệu cần kiểm tra, cửa sổ/mốc chốt và cách xử lý intent từ kỳ trước hoặc dữ liệu đến muộn.
3. Thu thập snapshot tổng hợp của intent, approval, quyết định quyền, reservation, outbox, posting và lịch sử fake provider.
4. Đối chiếu hai chiều local/provider và truy từ posting về nguồn; lập danh sách đạt, ngoại lệ, chưa đủ bằng chứng và chưa có kết quả cuối.
5. Tạo manifest, phương pháp có version, tập chi tiết và danh mục artifact có kiểm tra toàn vẹn; bảo vệ quyền xem/xuất.
6. Cố tình thêm một giao dịch provider không có intent, bỏ một approval snapshot và tạo hai attempt cho cùng intent. Kiểm tra mỗi biến đổi được phản ánh đúng, không đếm trùng tiền.
7. Giả lập provider xác nhận kết quả cuối của `refund-2`; tạo phiên bản gói mới và giải thích thay đổi so với bản trước.
8. Lập một hồ sơ ngoại lệ cần điều chỉnh; chứng minh quyền phê duyệt/áp dụng, tính idempotent và kiểm tra sau xử lý theo thiết kế đã chọn.

Sản phẩm cần cho phép một người có quyền kiểm tra đi từ **khẳng định kiểm soát đến tập giao dịch, bằng chứng gốc, phép kiểm tra và quyết định xử lý**. Giá trị của financial control evidence nằm ở khả năng kiểm chứng chuỗi đó, bao gồm cả những điểm chưa xác định và ngoại lệ cần tiếp tục theo dõi.
