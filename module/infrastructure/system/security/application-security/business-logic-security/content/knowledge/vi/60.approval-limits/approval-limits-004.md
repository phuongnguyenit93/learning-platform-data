# Threshold aggregation: Cộng gộp giá trị để áp dụng hạn mức phê duyệt

## 1. Vì sao kiểm tra từng yêu cầu là chưa đủ?

Một hệ thống quy định người quản lý cấp một được phê duyệt tối đa 100 triệu đồng. Nếu API chỉ so sánh giá trị của từng yêu cầu với 100 triệu, người dùng có thể chia một giao dịch 120 triệu thành ba yêu cầu 40 triệu để đi qua luồng phê duyệt thấp hơn.

Mỗi yêu cầu đều hợp lệ về định dạng, quyền gọi API và giá trị riêng lẻ. Tuy nhiên, chuỗi hành động đã vi phạm ý định của chính sách.

**Threshold aggregation** là việc cộng gộp các giao dịch thuộc một phạm vi nghiệp vụ xác định, rồi dùng tổng đó để lựa chọn thẩm quyền hoặc quy trình phê duyệt.

Cơ chế này cần bảo vệ đồng thời:

- Tổng được tính trên đúng đối tượng và đúng khoảng thời gian.
- Không thể chia nhỏ, đổi tài khoản hoặc đổi cách định danh để tránh cộng gộp.
- Các yêu cầu đồng thời không cùng sử dụng một phần hạn mức còn lại.
- Sửa giá trị, hủy, hoàn tiền hoặc retry không làm sai tổng.
- Phê duyệt gắn với đúng nội dung và không tiếp tục hợp lệ sau thay đổi quan trọng.

Trong bài này, hạn mức là chính sách nội bộ của ứng dụng. Các con số minh họa không phải quy định pháp lý hay khuyến nghị tài chính.

## 2. Phải định nghĩa “tổng” trước khi viết phép SUM

Câu “cộng các yêu cầu trong ngày” còn thiếu nhiều quyết định:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Chủ thể | Cộng theo người khởi tạo, pháp nhân, đơn vị, dự án hay đối tác? |
| Mục đích | Những yêu cầu nào thuộc cùng nhu cầu hoặc hợp đồng? |
| Thời gian | Ngày nghiệp vụ, tháng, cửa sổ trượt hay toàn vòng đời? |
| Trạng thái | Có tính yêu cầu chờ duyệt, đã duyệt, đang thực hiện không? |
| Giá trị | Trước thuế, sau thuế, phí vận chuyển hoặc giá trị quy đổi? |
| Dấu | Hoàn tiền có được trừ tổng không? |
| Biên | Tổng bằng ngưỡng có cần cấp cao hơn không? |
| Mức phê duyệt | Xét từng giao dịch, tổng lũy kế hay đồng thời nhiều điều kiện? |
| Điểm quyết định | Tính khi gửi, khi duyệt hay ngay trước thực hiện? |
| Thay đổi | Sửa người nhận, số tiền hoặc kỳ có làm mất hiệu lực duyệt không? |

Ví dụ chính sách minh họa:

~~~text
Phạm vi:
  tenant + legal_entity + requester_group + business_day + currency

Giá trị:
  tổng giá trị dương đã thực hiện trong kỳ
  + giá trị đang chờ duyệt hoặc đã duyệt nhưng chưa thực hiện

Biên:
  tổng <= 100.000.000 VND: cấp L1 có thể duyệt
  tổng > 100.000.000 VND: cần ít nhất cấp L2

Điều kiện bổ sung:
  vẫn phải đáp ứng hạn mức riêng từng giao dịch
  và quyền trên đơn vị, dự án, người thụ hưởng
~~~

Đây là một hợp đồng cụ thể. Một hệ thống khác có thể yêu cầu cấp cao hơn ngay khi bằng ngưỡng hoặc cộng theo hợp đồng thay vì theo ngày. Cần thể hiện khác biệt đó trong dữ liệu chính sách và kiểm thử.

Không để request tự gửi khóa cộng gộp đã tính sẵn. Server phải xác định phạm vi từ dữ liệu có thẩm quyền.

## 3. Phân biệt cộng gộp theo luồng tiền và theo mức đang cam kết

Hai phép cộng có thể cùng dùng số tiền nhưng phục vụ mục tiêu khác nhau:

| Loại tổng | Ý nghĩa | Tác động của hủy hoặc hoàn |
| --- | --- | --- |
| Tổng giá trị dương trong kỳ | Đo mức hoạt động đã hoặc đang yêu cầu trong kỳ | Hoàn tiền không mặc nhiên xóa hoạt động đã thực hiện |
| Mức đang cam kết | Đo nghĩa vụ đang tồn tại | Có thể giảm khi nghĩa vụ thực sự được giải phóng |
| Tổng theo nhu cầu/hợp đồng | Đo toàn bộ phần việc thuộc cùng mục đích | Chia thành nhiều ngày hoặc nhiều chứng từ chưa chắc làm giảm tổng |
| Tổng giá trị tuyệt đối | Đo tổng hoạt động hai chiều | Không bù trừ dương và âm với nhau |

Nếu mục tiêu là chống chia nhỏ, dùng tổng ròng có thể tạo lỗ hổng:

~~~text
Giao dịch dương: 90 triệu
Yêu cầu hoàn:   -80 triệu
Giao dịch dương tiếp: 90 triệu

Tổng ròng = 100 triệu
Tổng giao dịch dương = 180 triệu
~~~

Yêu cầu hoàn còn có thể chưa hoàn tất hoặc không liên quan đến giao dịch ban đầu. Không cho phép một số âm do client khai báo tự mở thêm quyền phê duyệt.

Bài này dùng mô hình tổng gồm:

~~~text
aggregate =
  gross_executed
  + reserved_pending
~~~

Trong đó:

- `gross_executed` giữ giá trị dương đã thực hiện trong phạm vi kỳ.
- `reserved_pending` giữ giá trị của yêu cầu đã gửi và còn chiếm cam kết.
- Khi thực hiện thành công, chuyển giá trị từ pending sang executed; tổng không tăng thêm lần nữa.
- Khi từ chối hoặc hủy hợp lệ trước thực hiện, giải phóng pending đúng một lần.
- Sau thực hiện, hoàn tiền đi qua quy trình riêng; không tự giảm gross của chính sách này.

Nếu nghiệp vụ chọn định nghĩa khác, phải thay đổi cả bất biến, state machine và cách đối soát.

## 4. Chống chia nhỏ bằng phạm vi nghiệp vụ phù hợp

### 4.1. Theo người dùng có thể chưa đủ

Một người có thể có nhiều tài khoản; một phòng ban có thể gửi qua nhiều nhân viên. Nếu chính sách thực sự giới hạn theo đơn vị, cộng theo `user_id` sẽ bỏ lọt.

Tương tự, một đối tác có thể có nhiều mã hồ sơ hoặc tên hiển thị khác nhau. Cần định danh nghiệp vụ chuẩn hóa, có kiểm soát thay đổi và quyền quản lý.

Tuy nhiên, không tự coi hai chủ thể là một chỉ vì tên gần giống. Có thể dùng tín hiệu liên quan để đưa vào xem xét, còn ràng buộc bắt buộc cần dựa trên danh tính hoặc quan hệ có thẩm quyền.

### 4.2. Theo thời gian có thể chưa đủ

Ba yêu cầu cho cùng hợp đồng được gửi vào ba ngày khác nhau có thể tránh một ngưỡng theo ngày. Nếu chính sách cấm chia nhỏ toàn bộ hợp đồng, cần thêm phạm vi theo hợp đồng hoặc mục đích.

Một thiết kế có thể xét nhiều chiều:

~~~text
required_level = mức cao nhất trong:
  mức theo giá trị riêng từng yêu cầu
  mức theo tổng của đơn vị trong ngày
  mức theo tổng của hợp đồng
  mức theo tổng đang cam kết trên dự án
~~~

Trong hệ thống có nhóm quyền phức tạp, kết quả không nhất thiết chỉ là một con số cấp bậc. Có thể phải thỏa mãn đồng thời chữ ký của bộ phận tài chính và chủ ngân sách.

### 4.3. Không để người gửi chọn chiều có lợi

Các trường như dự án, pháp nhân, đối tác hoặc loại chi phí cần được kiểm tra quan hệ và quyền. Nếu chỉ đổi `project_id` là tạo bucket mới, người dùng có thể làm sạch tổng bằng cách thay mã dự án.

Việc sửa phạm vi sau gửi phải là một nghiệp vụ được kiểm soát, cập nhật cả phạm vi cũ và mới trong cùng transaction và đánh giá lại yêu cầu phê duyệt.

## 5. Các bất biến cần giữ

Với mỗi phạm vi cộng gộp:

~~~text
reserved_pending >= 0
gross_executed >= 0

aggregate = reserved_pending + gross_executed

reserved_pending =
  tổng contribution đang ACTIVE trong phạm vi

gross_executed =
  tổng contribution đã EXECUTED theo chính sách của kỳ
~~~

Các bất biến về quyền:

1. Yêu cầu được thực hiện phải có đủ phê duyệt theo chính sách áp dụng.
2. Phê duyệt phải khớp phiên bản nội dung của yêu cầu.
3. Người duyệt có quyền trên đúng pháp nhân, dự án và đối tượng.
4. Không tự duyệt nếu chính sách yêu cầu tách người tạo và người duyệt.
5. Việc cấp quyền không chỉ dựa trên trường `required_level` do client hoặc cache cung cấp.
6. Một yêu cầu chỉ đóng góp một lần cho mỗi chiều cộng gộp.
7. Retry không đặt thêm cam kết và không giải phóng thêm cam kết.
8. Mọi thao tác thay đổi tổng phải cùng tuân thủ giao thức đồng thời.

Một ngưỡng chọn cấp phê duyệt không luôn là trần cứng. Tổng 120 triệu có thể được phép tồn tại ở trạng thái chờ L2. Điều cần cấm là thực hiện tổng đó chỉ bằng thẩm quyền L1.

Nếu ứng dụng còn có trần ngân sách tuyệt đối, phải kiểm tra nó riêng. Không nhầm “cần người duyệt cao hơn” với “không được phép vượt trong mọi trường hợp”.

## 6. Mô hình dữ liệu và vòng đời đóng góp

Một mô hình tối thiểu:

~~~text
approval_request
  id, tenant_id
  requester_id, legal_entity_id, project_id
  beneficiary_id, business_purpose_id
  amount, currency
  content_version, content_fingerprint
  state
  submitted_at, policy_version

aggregation_bucket
  id
  tenant_id, dimension_type, scope_key, period_key, currency
  reserved_pending, gross_executed
  version

aggregation_contribution
  request_id, bucket_id
  amount
  state: ACTIVE | RELEASED | EXECUTED
  request_content_version

approval_decision
  request_id, content_version
  approver_id, authority_reference
  policy_version, decision_basis
  decision_at, outcome

idempotency_record
  tenant_id, actor_id, operation, key
  request_fingerprint, result_reference
~~~

Cần khóa duy nhất cho danh tính bucket và cho `(request_id, bucket_id)` trong mô hình mỗi yêu cầu có một contribution trên mỗi bucket.

Quan hệ tenant phải được bảo vệ ở truy vấn và ràng buộc phù hợp. ID bucket hoặc request khó đoán không thay thế kiểm tra quyền.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING: Gửi và ghi contribution ACTIVE
    PENDING --> APPROVED: Đủ phê duyệt cho phiên bản hiện tại
    PENDING --> REJECTED: Giải phóng ACTIVE
    PENDING --> CANCELLED: Hủy hợp lệ và giải phóng ACTIVE
    APPROVED --> PENDING: Thay đổi quan trọng hoặc cần duyệt lại
    APPROVED --> EXECUTED: Chuyển ACTIVE sang EXECUTED
    APPROVED --> CANCELLED: Hủy trước thực hiện nếu được phép
    REJECTED --> [*]
    CANCELLED --> [*]
    EXECUTED --> [*]
~~~

Việc chuyển `APPROVED -> PENDING` trong mô hình này không tạo thêm contribution. Cam kết vẫn được giữ, trừ khi nghiệp vụ có một bước thay đổi hoặc giải phóng được định nghĩa rõ.

Gửi lại một yêu cầu đã đóng có thể cần tạo phiên bản hoặc yêu cầu mới. Không tái sử dụng trạng thái cuối để vô tình cộng hai lần.

## 7. Tính tiền và chuẩn hóa đơn vị

Không dùng số thực nhị phân để cộng tiền và so sánh ngưỡng. Có thể dùng số nguyên theo đơn vị nhỏ nhất được quy định hoặc kiểu thập phân chính xác với scale và quy tắc làm tròn rõ ràng.

Ví dụ:

~~~text
amount_minor = giá trị đã chuẩn hóa theo currency
threshold_minor = ngưỡng theo cùng currency và cùng đơn vị

projected_total = aggregate_before + new_contribution
requires_L2 = projected_total > threshold_minor
~~~

Cần kiểm soát:

- Số âm, số không và giá trị vượt miền cho phép.
- Tràn số khi cộng.
- Thuế, phí và chiết khấu có thuộc giá trị hạn mức không.
- Làm tròn theo từng dòng hay sau khi cộng.
- Giá trị client gửi khác tổng chứng từ server tính.

Nếu dùng `long` trong Java, `Math.addExact` giúp phát hiện tràn số; bắt lỗi không có nghĩa được tự cắt hoặc quay vòng giá trị để tiếp tục duyệt.

Không cộng trực tiếp 50 triệu VND với 2.000 USD. Có thể tách bucket theo tiền tệ hoặc dùng một đồng tiền chính sách với tỷ giá do nguồn có thẩm quyền cung cấp.

Nếu quy đổi, lưu số tiền gốc, tiền tệ gốc, tỷ giá/phiên bản, thời điểm và giá trị chuẩn hóa. Phải quy định giá trị được cố định lúc gửi hay đánh giá lại sau đó. Đổi tỷ giá sau khi duyệt có thể làm thay đổi mức cần duyệt; không được âm thầm thay cơ sở phê duyệt.

Bài toán ở đây là thực thi chính sách phê duyệt, không phải chỉ trình bày một tổng tiền trên giao diện.

## 8. Transaction cho ghi nhận và đánh giá tổng

### 8.1. Lỗi đọc tổng rồi ghi độc lập

Giả sử tổng hiện tại là 80 triệu và L1 được duyệt đến 100 triệu:

~~~text
Request A đọc 80, thêm 15 => dự kiến 95, chọn L1
Request B đọc 80, thêm 15 => dự kiến 95, chọn L1

Sau khi cả hai được ghi:
tổng = 110 triệu
~~~

Nếu chỉ có một câu `SUM` rồi insert ở bước khác, hai quyết định có thể cùng dùng một ảnh chụp cũ. Việc SQL tự cộng đúng 110 sau đó không sửa được thẩm quyền đã cấp sai.

### 8.2. Một giao thức khóa dễ kiểm chứng

Trong mô hình một yêu cầu mỗi thao tác, chọn thứ tự chung:

1. Khóa hàng request.
2. Xác định bucket từ nội dung đã khóa và dữ liệu có thẩm quyền.
3. Tạo nếu chưa có và khóa các bucket theo thứ tự khóa ổn định.
4. Kiểm tra contribution hiện tại.
5. Tính tổng và mức phê duyệt.
6. Ghi request, contribution, bộ đếm, idempotency và outbox.
7. Commit.

Mọi đường sửa, hủy, từ chối và thực hiện đều theo cùng thứ tự. Worker quét ứng viên không được khóa bucket trước rồi mới khóa request nếu API làm ngược lại.

Với thao tác theo lô, phải mở rộng quy tắc thứ tự cho tất cả request và bucket; không giả định quy tắc cho một request tự đúng cho mọi batch.

Hàng bucket cần khóa duy nhất trên danh tính phạm vi. Nếu bucket chưa tồn tại, hai transaction không được tạo hai hàng đại diện cùng phạm vi. Có thể dùng insert chống trùng rồi khóa hàng thực sự tồn tại; xử lý xung đột theo cơ chế của hệ quản trị.

Khóa một tập contribution hiện có chưa chắc ngăn contribution mới xuất hiện. Một hàng bucket ổn định giúp tạo điểm phối hợp cho mọi writer.

### 8.3. Giả mã gửi yêu cầu

~~~java
return transaction.execute(() -> {
    ApprovalRequest request = requests.lockForUpdate(
        principal.tenantId(), requestId
    );
    authorization.requireSubmit(principal, request);

    Optional<SubmitResult> previous = idempotency.findSameIntent(
        principal, operationKey, requestFingerprint
    );
    if (previous.isPresent()) {
        return previous.get();
    }

    request.requireDraft();
    request.validateContentAndAmount();

    Policy policy = policies.resolveImmutableVersion(request);
    List<ScopeKey> keys = scopeResolver.resolveFromTrustedData(
        request, policy
    );
    List<Bucket> buckets = bucketRepository.lockOrCreateInOrder(keys);

    contributions.requireNotAlreadyRegistered(request.id());

    for (Bucket bucket : buckets) {
        Money contribution = policy.amountFor(request, bucket);
        bucket.reserve(contribution);
        contributions.addActive(request, bucket, contribution);
    }

    ApprovalRequirement requirement = policy.evaluate(
        request, buckets
    );

    request.submit(requirement, policy.version());
    requests.save(request);
    bucketRepository.saveAll(buckets);

    SubmitResult result = SubmitResult.pending(request.id(), requirement);
    idempotency.save(operationKey, requestFingerprint, result);
    outbox.addSubmitted(request);

    return result;
});
~~~

Các kiểu và hàm trên là giả mã. Tổng trong `buckets` đã bao gồm contribution mới, vì vậy `policy.evaluate` không được cộng số tiền request thêm lần nữa.

Nếu ngưỡng chỉ chọn tuyến duyệt, request vượt ngưỡng có thể commit ở trạng thái chờ người có thẩm quyền cao hơn. Nếu có trần cứng khác bị vi phạm, toàn bộ phần reserve phải rollback hoặc đi vào trạng thái không chiếm cam kết theo hợp đồng rõ ràng.

Bản ghi idempotency cần ràng buộc duy nhất theo phạm vi thao tác. Khi gặp trùng do hai request đồng thời, phải rollback toàn bộ lần ghi mới trước khi trả kết quả đã tồn tại. Không giữ lại bộ đếm tăng thêm chỉ vì đã tìm thấy một key cũ.

## 9. Đánh giá tại lúc duyệt và trước thực hiện

Một tuyến duyệt được tính lúc gửi có thể lỗi thời. Trong mô hình minh họa, hệ thống kiểm tra lại yêu cầu phê duyệt tại lúc duyệt và tại thời điểm cho phép thực hiện.

Ví dụ:

| Bước | Tổng sau bước | Hệ quả |
| --- | --- | --- |
| A gửi 40 triệu | 40 triệu | L1 có thể đáp ứng |
| B gửi 40 triệu | 80 triệu | L1 có thể đáp ứng |
| C gửi 40 triệu | 120 triệu | Tổng cần L2 |
| A vẫn chờ thực hiện | Tổng hiện tại 120 triệu | Không được dựa riêng vào nhãn L1 đã tính lúc gửi |

Trong hợp đồng này, một phê duyệt L1 trước đó chưa đủ để thực hiện nếu tại điểm quyết định hiện tại tổng đã yêu cầu L2. Hệ thống có thể chủ động đưa yêu cầu về chờ duyệt, nhưng đường thực hiện vẫn phải kiểm tra ngay cả khi tác vụ cập nhật tuyến duyệt chưa chạy.

Các giao dịch đã thực hiện hợp lệ trước đó không tự bị đảo ngược. Khi C làm tổng vượt ngưỡng, C và các yêu cầu chưa thực hiện được đánh giá theo quy tắc hiện tại.

Đây là lựa chọn chính sách có tác động vận hành. Một thiết kế khác có thể cấp một quyền sử dụng hạn mức đã được giữ và phê duyệt cho từng phiên bản, bảo vệ nó trước yêu cầu gửi sau. Khi chọn cách đó, phải mô hình hóa quyền đã cấp, dung lượng đã giữ và điều kiện hết hiệu lực; không chỉ lưu một cờ `approved = true`.

Tại điểm duyệt:

- Contribution của chính request đã nằm trong tổng; không cộng lại.
- Người duyệt phải có đủ thẩm quyền theo tổng và các chiều liên quan.
- Chữ ký hoặc quyết định gắn với `content_version` và phạm vi chính sách.
- Việc ủy quyền, hết hạn quyền hoặc tách người tạo/người duyệt được kiểm tra theo hợp đồng.
- Phản hồi thành công chỉ được trả khi quyết định đã được lưu nguyên tử.

Trước thực hiện, kiểm tra lại phiên bản nội dung, trạng thái, quyền phê duyệt và điều kiện cần thiết trong transaction bảo vệ dữ liệu.

Nếu thực hiện nằm hoàn toàn trong cơ sở dữ liệu, có thể chuyển pending sang executed cùng transaction. Nếu gọi hệ thống ngoài, cần trạng thái trung gian và giao thức outbox/idempotency phù hợp. Không giảm cam kết ngay khi vừa gửi lệnh ra ngoài; kết quả chưa rõ phải tiếp tục được theo dõi để tránh sử dụng lại cùng hạn mức.

## 10. Sửa, hủy, từ chối và retry

### 10.1. Sửa số tiền

Với contribution đang active:

~~~text
delta = new_amount - old_amount
reserved_pending_new = reserved_pending_old + delta
~~~

Cập nhật phải nằm trong transaction khóa request và mọi bucket liên quan. Số tiền mới được server xác minh, không lấy `delta` do client gửi làm căn cứ.

Thay đổi quan trọng làm tăng `content_version`, đánh giá lại yêu cầu duyệt và vô hiệu hóa phê duyệt không còn khớp nội dung. Việc tăng từ 40 lên 140 triệu không được giữ nguyên phê duyệt cho 40 triệu.

Giảm số tiền cũng cần chính sách: nó có thể cho phép tuyến thấp hơn, nhưng không được âm thầm thay đổi nội dung mà người duyệt đã ký.

### 10.2. Sửa phạm vi

Chuyển dự án hoặc pháp nhân có thể cần giải phóng contribution cũ và ghi contribution mới. Khóa các bucket cũ và mới theo thứ tự ổn định, thực hiện toàn bộ trong một transaction.

Kiểm tra quyền ở cả nơi chuyển đi và nơi chuyển đến. Không cho phép thay mã mục đích tùy ý để né tổng theo hợp đồng.

### 10.3. Hủy hoặc từ chối

Chỉ contribution `ACTIVE` mới được giải phóng. Chuyển `ACTIVE -> RELEASED` và giảm pending đúng một lần.

Retry hủy, hai người cùng từ chối hoặc worker cùng xử lý không được giảm thêm. Nếu request đã được thực hiện, không dùng đường hủy trước thực hiện để xóa gross.

### 10.4. Retry thực hiện

Chuyển contribution từ active sang executed không được cộng giá trị vào cả hai phần:

~~~text
reserved_pending -= amount
gross_executed += amount
aggregate không đổi
~~~

Retry sau commit trả kết quả cũ. Nếu lần đầu rollback, lần mới đọc lại dữ liệu và điều kiện hiện hành. Không suy luận rằng mất response đồng nghĩa giao dịch chưa xảy ra.

## 11. Kỳ cộng gộp, chính sách và hệ thống phân tán

### Kỳ phải do server xác định

Ngày nghiệp vụ phải được tính bằng nguồn thời gian và múi giờ đã quy định. Trường `business_day` tùy ý trong request không được tạo một bucket mới.

Chọn rõ ngày được gán khi gửi, khi duyệt hay khi thực hiện. Nếu gán khi gửi, lưu kỳ và không cho client tự chuyển sang kỳ khác.

Một ngưỡng theo ngày có thể hợp lệ khi reset qua ngày mới. Nhưng nếu ý định là chống chia nhỏ cùng hợp đồng, chỉ đổi ngày không được xóa chiều cộng gộp theo hợp đồng.

### Cam kết chưa hoàn tất không tự biến mất lúc nửa đêm

Nếu pending phải tiếp tục chiếm mức đang cam kết, cần bucket hoặc chiều cộng gộp cho các nghĩa vụ còn mở. Không reset một biến tổng về zero rồi bỏ quên request cũ.

Đối với chính sách theo ngày gửi, phải quy định yêu cầu còn chờ qua kỳ có được duyệt không, có hết hiệu lực hoặc cần đánh giá lại không. Không để một phê duyệt cũ trở thành đường thực hiện không còn bị kiểm tra.

### Thay đổi chính sách

Lưu phiên bản chính sách hoặc bằng chứng bất biến đủ tái hiện quyết định. Khi đổi ngưỡng, xác định yêu cầu đang chờ dùng phiên bản cũ hay phải đánh giá lại.

Không dùng `policy_version` làm một phần khóa bucket theo cách tự chia đôi tổng mỗi lần cập nhật cấu hình. Hai phiên bản chính sách chưa chắc đại diện hai phạm vi kinh tế độc lập.

### Nhiều service hoặc nhiều vùng

Nếu một service chỉ có bản sao tổng trễ, nó không nên tự cấp quyền dựa trên tổng đó khi yêu cầu cần nhất quán chặt.

Các lựa chọn gồm đưa quyết định về một nơi có thẩm quyền, phối hợp cập nhật có tính nguyên tử phù hợp hoặc phân bổ phần hạn mức rõ ràng cho từng nơi. Mỗi cách cần chứng minh không cấp vượt theo chính sách.

Cache phục vụ hiển thị và gợi ý tuyến duyệt; quyền thực hiện phải dựa trên dữ liệu được bảo vệ. Tổng trên dashboard chưa phải bằng chứng đủ cho một quyết định mới.

## 12. Kiểm thử tình huống lạm dụng

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Một yêu cầu ngay dưới, đúng bằng và ngay trên ngưỡng | Đúng toán tử biên theo chính sách |
| Ba yêu cầu 40 triệu với ngưỡng 100 triệu | Tổng 120 triệu được nhận diện và yêu cầu đủ thẩm quyền |
| Hai request cùng đọc phần còn lại 20 triệu, mỗi request thêm 15 triệu | Quyết định được tuần tự hóa; không cùng nhận thẩm quyền dựa trên tổng 95 triệu |
| Chia qua nhiều tài khoản thuộc cùng đơn vị | Vẫn cộng theo chủ thể chính sách quy định |
| Đổi tên đối tác hoặc bí danh | Không tạo phạm vi mới khi cùng danh tính nghiệp vụ |
| Gửi cùng hợp đồng qua nhiều ngày | Chiều theo hợp đồng vẫn hoạt động nếu chính sách yêu cầu |
| Nhiều request pending | Pending không bị bỏ khỏi tổng rồi cùng được duyệt |
| Retry gửi cùng key | Một contribution trên mỗi bucket |
| Cùng key nhưng đổi số tiền hoặc request | Bị từ chối |
| Sửa tiền sau khi duyệt | Phiên bản duyệt cũ không đủ cho nội dung mới |
| Chuyển phạm vi đồng thời với duyệt | Không mất contribution và không dùng thẩm quyền sai phạm vi |
| Hai lần hủy hoặc từ chối cùng request | Chỉ giải phóng một lần |
| Hoàn tiền chưa hoàn tất hoặc giá trị âm giả | Không tự mở thêm quyền phê duyệt |
| Thực hiện và hủy chạy đồng thời | Chỉ một kết quả cuối hợp lệ, bộ đếm nhất quán |
| Tỷ giá hoặc phiên bản chính sách thay đổi | Theo đúng hợp đồng cố định/đánh giá lại, có audit |
| Trùng lúc tạo bucket đầu tiên | Chỉ một bucket cho một danh tính phạm vi |
| Lỗi sau ghi contribution nhưng trước commit | Bộ đếm, request, idempotency và outbox cùng rollback |
| Cache cũ hoặc service đọc replica | Không dùng tổng lỗi thời để cấp quyền |
| Client đổi tenant, bucket, ngày hoặc người duyệt | Không vượt quyền hoặc thay cơ sở tổng |

Kiểm thử đồng thời phải dùng transaction độc lập và điều phối thứ tự bằng latch/barrier hoặc cơ chế tương đương. Sau khi các transaction kết thúc, kiểm tra cả contribution và bộ đếm, không chỉ response.

Với chuỗi thao tác ngẫu nhiên tạo, sửa, hủy, duyệt và thực hiện, đối chiếu tổng ledger với bucket sau mỗi chuỗi đã commit. Mô hình kỳ vọng phải dựa trên chính sách, không gọi lại cùng implementation để tự tính expected.

## 13. Audit, đối soát và khả năng giải thích

Một quyết định nên giải thích được:

~~~text
request_id, content_version
actor_id, approver_id, authority_reference
policy_version
các scope_key và period_key đã dùng
giá trị contribution theo từng chiều
tổng trước và sau hoặc tham chiếu ledger tương ứng
mức hoặc tập phê duyệt bắt buộc
decision_at, outcome, reason_code
correlation_id, idempotency_reference
~~~

Không cần ghi mọi dữ liệu cá nhân vào log. Cần đủ tham chiếu đến chứng cứ bền vững và quyền truy cập phù hợp.

Theo dõi các tín hiệu:

- Tần suất yêu cầu nằm sát dưới ngưỡng.
- Nhiều yêu cầu liên quan trong thời gian ngắn.
- Đổi phạm vi, hủy rồi tạo lại hoặc chuyển người khởi tạo.
- Độ trễ cập nhật tuyến duyệt và số lần bị yêu cầu duyệt lại.
- Chênh lệch giữa bucket và tổng contribution.
- Xung đột, deadlock hoặc retry tại bucket nóng.

Tín hiệu bất thường hỗ trợ rà soát; không thay thế ràng buộc nguyên tử tại đường ghi.

Đối soát cần ảnh chụp dữ liệu nhất quán hoặc giao thức khóa phù hợp. Nếu đọc ledger và bucket tại hai thời điểm khác nhau trong lúc có ghi, có thể tạo cảnh báo sai. Sửa sai phải có lịch sử và không được cộng trừ bù tùy ý trong khi các transaction khác vẫn thay đổi cùng phạm vi.

Threshold aggregation an toàn kết hợp đúng định nghĩa phạm vi, số tiền chuẩn hóa, ghi nhận cả cam kết liên quan, điều phối cập nhật đồng thời và kiểm tra thẩm quyền trên phiên bản nội dung. Phép cộng là phần dễ; phần quyết định bảo mật là bảo đảm không đường nghiệp vụ nào được đứng ngoài tổng và quy trình duyệt đã quy định.
