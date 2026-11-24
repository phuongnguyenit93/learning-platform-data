# Abuse metric — Đo lường dấu hiệu lạm dụng logic nghiệp vụ

## 1. Abuse metric cần trả lời câu hỏi nào?

**Abuse metric** là chỉ số được thiết kế để quan sát dấu hiệu một chức năng nghiệp vụ bị sử dụng sai mục đích, vượt quy tắc hoặc tạo tác động không được phép. Ví dụ: nhiều lần tự phê duyệt hoàn tiền, cố sửa giá do máy chủ tính, truy cập đối tượng ngoài phạm vi quyền hoặc tạo lại một tác động bằng yêu cầu trùng.

Một metric hữu ích phải nối được tín hiệu với **quy tắc nghiệp vụ cụ thể**. Số request tăng, số lỗi HTTP tăng hoặc số lần retry tăng chưa tự chứng minh có lạm dụng.

Trong module bảo mật logic nghiệp vụ, mục tiêu là biết:

- Quy tắc nào đang bị thử vượt qua?
- Các kiểm soát đã chặn được bao nhiêu lần?
- Có tác động nào thực sự vi phạm invariant hay không?
- Tín hiệu tập trung ở hành động, kênh hoặc nhóm đối tượng nào?
- Có đủ dữ liệu để điều tra mà không đưa danh tính nhạy cảm vào hệ thống metric không?
- Khi không có cảnh báo, đó là do không thấy dấu hiệu hay do đường quan sát bị hỏng?

Metric là dữ liệu tổng hợp phục vụ phát hiện và theo dõi. Nó không thay thế kiểm tra quyền, transaction, idempotency hoặc audit. Nó cũng không tự xác định được người có ý đồ xấu: một lỗi client cũ có thể tạo ra cùng mã từ chối với một hành vi cố tình sửa giá.

## 2. Ví dụ xuyên suốt: lạm dụng chức năng hoàn tiền

Giả sử hoàn tiền chỉ được phê duyệt khi:

1. Đang ở trạng thái PENDING_APPROVAL.
2. Người thực hiện có quyền theo tenant và đối tượng.
3. Người tạo không tự phê duyệt.
4. Số tiền được duyệt khớp dữ liệu có thẩm quyền.
5. Một lệnh chỉ tạo số lần tác động được phép theo hợp đồng nghiệp vụ.

Có thể xuất hiện các tình huống:

| Tình huống | Điều hệ thống quan sát được | Cách diễn giải ban đầu |
|---|---|---|
| Người tạo tự phê duyệt 40 lần | Tăng số quyết định từ chối SELF_APPROVAL | Có dấu hiệu thử vượt quy tắc; chưa có phê duyệt trái phép |
| Client gửi số tiền khác máy chủ | Tăng số từ chối AMOUNT_MISMATCH | Có thể là sửa dữ liệu hoặc client dùng dữ liệu cũ |
| Người dùng đổi refund ID sang tenant khác | Tăng từ chối OBJECT_SCOPE_DENIED | Cần kiểm tra quyền và mẫu truy cập đối tượng |
| Client retry do timeout | Tăng số trả lại kết quả idempotency | Có thể là hoạt động bình thường của cơ chế phục hồi |
| Hai bản thanh toán cùng một business reference | Phát hiện tác động trùng trong dữ liệu có thẩm quyền | Có thể là vi phạm invariant thực tế, cần xác minh và xử lý nhanh |
| Lượng từ chối tăng sau triển khai | Mã lý do thay đổi theo phiên bản client hoặc policy | Có thể là lỗi triển khai, thay đổi quyền hoặc hành vi lạm dụng |

Một dashboard chỉ có tổng số HTTP 403 sẽ trộn nhiều trường hợp khác nhau. Một dashboard chỉ có HTTP 500 có thể bỏ sót việc sửa giá bị từ chối bằng HTTP 400, hoặc một tác động sai được API trả HTTP 200.

Điểm bắt đầu phải là kết quả kiểm tra và tác động nghiệp vụ, không phải chỉ mã phản hồi mạng.

## 3. Phân biệt lần thử, quyết định và tác động

Đây là bước quan trọng để tránh đếm đúng dữ liệu nhưng kết luận sai.

### 3.1. Lần thử thực hiện

Một request hoặc một lần nhận message có thể là một lần thử. Cần định nghĩa ranh giới: nhận tại gateway, vào command handler hay bắt đầu xử lý một thông điệp.

Trong ví dụ này, lần thử được tính khi đi vào handler nghiệp vụ đã chọn. Retry vào lại handler được tính là một lần thử mới. Một request bị gateway chặn có thể nằm trong metric an ninh khác, không tự xuất hiện trong metric này.

### 3.2. Quyết định policy

Một lần thử có thể dẫn đến quyết định ALLOW hoặc DENY trên một hành động và đối tượng. Hệ thống có nhiều kiểm tra nội bộ nhưng nên quy định rõ metric đang đếm:

- Quyết định cuối cùng cho hành động, hay
- Từng lần đánh giá một rule.

Không trộn hai đơn vị trong cùng metric. Nếu mỗi request chạy năm rule mà mỗi rule đều tăng counter quyết định cuối cùng, mẫu số sẽ bị phóng đại.

ERROR hoặc UNKNOWN khi không đánh giá được policy cũng không được âm thầm biến thành DENY. Hành vi xử lý có thể là từ chối thao tác theo thiết kế, nhưng tín hiệu “không đánh giá được” phải phân biệt với “đã đánh giá và từ chối”.

### 3.3. Tác động nghiệp vụ đã commit

Một quyết định ALLOW chưa chứng minh tác động thành công. Transaction có thể rollback, cập nhật có thể xung đột hoặc bước thanh toán vẫn đang chờ.

Tác động đã commit cần dựa trên nguồn dữ liệu có thẩm quyền hoặc sự kiện gắn nhất quán với commit. Ví dụ: chuyển trạng thái hoàn tiền đã commit và một lệnh thanh toán có định danh nghiệp vụ đã được ghi nhận.

Không cộng số lần trả lại kết quả cũ vào số lần phê duyệt mới.

### 3.4. Vi phạm invariant thực tế

Cần phân biệt:

~~~text
Bị chặn vì định tự phê duyệt
    khác với
Đã tồn tại một phê duyệt mà người tạo cũng là người duyệt

Nhận lại cùng message
    khác với
Đã phát sinh hai tác động không được phép cho cùng nghiệp vụ
~~~

Một metric về vi phạm thực tế phải nêu nguồn xác minh và điều kiện xác nhận. Nếu dữ liệu đối chiếu còn trễ hoặc chưa đầy đủ, có thể ghi nhận một tín hiệu nghi ngờ riêng thay vì gắn ngay nhãn CONFIRMED.

Việc hệ thống có nhiều lần thử bị chặn cho thấy kiểm soát đang hoạt động trên các lần đó. Nó không chứng minh toàn bộ đường thực thi đều an toàn.

## 4. Xây dựng danh mục metric có hợp đồng rõ ràng

Bảng sau là thiết kế minh họa. Tên metric và nhãn do ứng dụng định nghĩa, không phải một bộ tên bắt buộc.

| Metric | Loại | Đơn vị được đếm hoặc đo | Nhãn giới hạn gợi ý |
|---|---|---|---|
| business_command_attempts_total | Counter | Một lần vào handler nghiệp vụ trong phạm vi đã định nghĩa | operation, channel |
| business_policy_decisions_total | Counter | Một quyết định cuối cùng đã đánh giá xong | operation, decision, reason |
| business_attempt_outcomes_total | Counter | Một kết quả được quan sát khi kết thúc lần xử lý ở ranh giới đo | operation, outcome |
| business_effects_total | Counter | Một tác động đã commit được ghi nhận từ nguồn đã định nghĩa | operation, effect |
| business_idempotency_events_total | Counter | Một kết quả kiểm tra idempotency | operation, result |
| business_invariant_violations_total | Counter | Một vi phạm thực tế đã được xác nhận, có chống đếm lặp | invariant |
| abuse_pipeline_lag_seconds | Gauge | Độ trễ của đường đánh giá hiện tại theo cách tính đã định nghĩa | pipeline |
| abuse_detector_errors_total | Counter | Một lỗi xử lý của bộ phát hiện | stage, error_class |

Ví dụ các tập giá trị:

~~~text
operation:
  refund.approve
  order.change_price
  payment.execute
  OTHER

decision:
  ALLOW
  DENY

reason:
  POLICY_ALLOW
  SELF_APPROVAL
  OBJECT_SCOPE_DENIED
  INVALID_STATE
  AMOUNT_MISMATCH
  DELEGATION_SCOPE_DENIED
  OTHER

outcome:
  COMMITTED
  REPLAYED_RESULT
  DENIED
  ACCEPTED_PENDING
  FAILED
  UNKNOWN

idempotency result:
  NEW
  REPLAY
  PAYLOAD_CONFLICT
  IN_FLIGHT
~~~

Các tập này chỉ minh họa. Mỗi hệ thống phải định nghĩa ý nghĩa và vị trí phát metric của mình.

### 4.1. Counter phải được đọc theo khoảng thời gian

Counter là số tích lũy, không phải số sự kiện của riêng phút hiện tại. Muốn phân tích một cửa sổ, cần dùng lượng tăng hoặc tốc độ tăng và xử lý việc tiến trình khởi động lại theo công cụ quan sát đang dùng.

Không lấy giá trị tích lũy từ lúc khởi động rồi so trực tiếp với một ngưỡng “mỗi 10 phút”. Nếu dữ liệu bị thiếu hoặc counter reset không được xử lý, kết quả có thể sai.

### 4.2. Các tổng không bắt buộc bằng nhau

Số lần thử, số quyết định và số tác động có thể khác nhau một cách hợp lệ:

- Một lần thử bị lỗi trước khi đánh giá policy.
- Một lần thử nhận lại kết quả đã có.
- Một lệnh bất đồng bộ đã được nhận nhưng chưa tạo tác động.
- Một quyết định cho phép bị rollback.
- Một bước nghiệp vụ tạo ra nhiều loại tác động được mô hình cho phép.

Không dùng một phép so tổng đơn giản để kết luận mất dữ liệu. Cần hiểu hợp đồng của từng metric và các quan hệ kỳ vọng giữa chúng.

## 5. Chọn nhãn để không tạo lỗ hổng quan sát

### 5.1. Chỉ dùng tập giá trị hữu hạn, có kiểm soát

Mỗi tổ hợp giá trị nhãn có thể tạo một chuỗi thời gian riêng. Nhãn có số lượng giá trị tăng không giới hạn gây tăng bộ nhớ, storage và chi phí truy vấn.

Không dùng trực tiếp các giá trị sau làm nhãn metric tổng hợp:

- User ID, email hoặc số điện thoại.
- Refund ID, order ID hoặc business reference.
- Request ID, trace ID hoặc idempotency key.
- URL nguyên bản có ID đối tượng.
- Địa chỉ IP hoặc User-Agent nguyên bản.
- Reason do client nhập hoặc nội dung exception tùy ý.
- Tenant ID khi số tenant lớn, tăng liên tục hoặc có thể do nguồn không tin cậy tạo ra.

Ngay cả ID đã băm vẫn có thể tạo cardinality không giới hạn. Băm dữ liệu không làm số lượng chuỗi thời gian tự giảm.

Nên dùng operation chuẩn hóa, route template, channel từ tập cố định và reason code do máy chủ tạo. Giá trị lạ được phân loại vào OTHER và có tín hiệu theo dõi lỗi ánh xạ, thay vì trở thành nhãn mới.

### 5.2. Không tạo toàn bộ tích Descartes nếu không cần

Ví dụ có 20 operation, 10 reason, 5 channel, 6 outcome, 8 vùng triển khai và 4 phiên bản client. Một metric gắn mọi nhãn có thể có rất nhiều tổ hợp, ngay cả khi từng tập riêng lẻ đều hữu hạn.

Tách các câu hỏi quan sát thành metric phù hợp. Metric quyết định không nhất thiết cần outcome của transaction; metric kết quả idempotency không nhất thiết cần mọi reason của policy.

Nếu cần so sánh theo phiên bản policy, có thể dùng thông tin đánh dấu triển khai hoặc truy vấn sự kiện chi tiết. Không mặc nhiên gắn mọi commit hash hoặc phiên bản phát hành từng xuất hiện vào tất cả metric.

### 5.3. Phân tích theo actor cần một tầng khác

Phát hiện một actor thử nhiều đối tượng thường cần sự kiện chi tiết hoặc bộ tổng hợp có trạng thái theo cửa sổ. Không giải quyết bằng cách thêm actorId vào nhãn của counter toàn hệ thống.

Một kiến trúc thường tách:

~~~text
Metric tổng hợp:
    Phát hiện operation hoặc lớp lý do bất thường

Sự kiện có cấu trúc:
    Phân tích actor, tenant, đối tượng và chuỗi hành động

Audit có thẩm quyền:
    Đối chiếu quyết định, commit và bằng chứng điều tra
~~~

Nếu dùng định danh giả danh để nhóm actor, cần quản lý khả năng liên kết, quyền tra cứu và vòng đời khóa. Hash đơn giản của ID dễ đoán không tự bảo vệ danh tính. Thay đổi khóa hoặc định danh giữa cửa sổ cũng có thể làm đứt chuỗi phân tích; đó phải là lựa chọn có chủ đích.

## 6. Tỷ lệ, mẫu số và cửa sổ đo

### 6.1. Tỷ lệ từ chối phải có mẫu số tương ứng

Với hành động refund.approve:

~~~text
blocked_self_approval_ratio =
    số quyết định DENY với reason SELF_APPROVAL trong cửa sổ
    /
    tổng quyết định ALLOW hoặc DENY của refund.approve trong cùng cửa sổ
~~~

Mẫu số phải cùng phạm vi hành động, thời gian và nguồn dữ liệu. Không lấy số tự phê duyệt bị chặn chia cho tổng request toàn hệ thống: lưu lượng đọc danh mục có thể che khuất tín hiệu.

Cũng không dùng tổng tác động commit làm mẫu số cho tỷ lệ quyết định từ chối nếu chưa giải thích ý nghĩa khác biệt.

Nếu không có quyết định nào, tỷ lệ là **không có dữ liệu để tính**, không phải bằng chứng tỷ lệ lạm dụng bằng 0. Dashboard có thể hiển thị N/A và số mẫu bằng 0.

### 6.2. Ví dụ truy vấn từ sự kiện chuẩn hóa

Giả sử normalized_policy_decision có đúng một dòng cho mỗi quyết định cuối cùng, đã chống trùng theo event ID. Mã SQL minh họa dùng tham số thời gian do ứng dụng cung cấp:

~~~sql
SELECT
    SUM(
        CASE
            WHEN decision = 'DENY'
             AND reason_code = 'SELF_APPROVAL'
            THEN 1 ELSE 0
        END
    ) AS blocked_self_approval,
    COUNT(*) AS evaluated_decisions,
    1.0 * SUM(
        CASE
            WHEN decision = 'DENY'
             AND reason_code = 'SELF_APPROVAL'
            THEN 1 ELSE 0
        END
    ) / NULLIF(COUNT(*), 0) AS blocked_self_approval_ratio
FROM normalized_policy_decision
WHERE operation = :operation
  AND decided_at >= :window_start
  AND decided_at < :window_end
  AND decision IN ('ALLOW', 'DENY');
~~~

Ở đây operation được truyền là refund.approve. Cú pháp gắn tham số cụ thể phụ thuộc thư viện truy cập dữ liệu; ví dụ chỉ mô tả phép tổng hợp.

Khoảng thời gian dạng [bắt đầu, kết thúc) giúp các cửa sổ kề nhau không đếm cùng một sự kiện ở cả hai phía. Khi sự kiện đến trễ, cần quy định lúc nào cửa sổ được điều chỉnh và lúc nào số liệu được coi là hoàn tất.

### 6.3. Dùng đồng thời số tuyệt đối và tỷ lệ

| Cửa sổ minh họa | Số tự phê duyệt bị chặn | Số quyết định được đánh giá | Tỷ lệ |
|---|---:|---:|---:|
| A | 40 | 200 | 20% |
| B | 40 | 10.000 | 0,4% |
| C | 2 | 2 | 100% |
| D | 0 | 0 | Không tính được |

A có tỷ lệ đáng chú ý. B vẫn có 40 lần thử cùng loại dù bị lưu lượng hợp lệ làm tỷ lệ thấp đi. C có tỷ lệ rất cao nhưng mẫu nhỏ. D không chứng minh đã quan sát thấy không có hành vi lạm dụng.

Cần nhìn cả số lượng, tỷ lệ, quy mô mẫu và mức tập trung theo actor hoặc đối tượng ở tầng phân tích chi tiết.

### 6.4. Đếm distinct cũng cần định nghĩa

“Số actor có dấu hiệu” khác với “số lần bị chặn”. Một người retry nhiều lần không tương đương nhiều người độc lập.

Tuy nhiên, số actor distinct cũng có giới hạn:

- Chỉ nên coi danh tính đã xác minh là actor đã xác minh.
- Kẻ tấn công có thể dùng nhiều tài khoản.
- Một hệ thống tích hợp có thể dùng một service principal cho nhiều người.
- Ước lượng distinct gần đúng có sai số và không chỉ ra danh tính cụ thể.

Nếu dùng cấu trúc ước lượng để tiết kiệm tài nguyên, cần công bố sai số và giới hạn ứng dụng. Không dùng một ước lượng gần đúng làm bằng chứng duy nhất để khóa một người cụ thể.

## 7. Các nhóm tín hiệu cần thiết kế riêng

### 7.1. Thử vượt business invariant

Ví dụ: tự phê duyệt, sửa số tiền, chuyển trạng thái không hợp lệ.

Tín hiệu có thể là số quyết định bị chặn theo reason, tốc độ tăng và chuỗi thử trên nhiều đối tượng. Cần phân biệt các mã lý do đủ cụ thể để điều tra nhưng không làm lộ dữ liệu nhạy cảm qua API.

Một quyết định INVALID_STATE cũng có thể do client giữ dữ liệu cũ hoặc hai tác vụ hợp lệ chạy đồng thời. Không đặt tên metric như “fraud_user_total” chỉ từ một quyết định này.

### 7.2. Lạm dụng quyền theo đối tượng

Một actor liên tục thử đối tượng ngoài phạm vi tenant có thể đáng chú ý hơn nhiều lỗi không tìm thấy đơn lẻ.

Metric tổng hợp cho biết xu hướng OBJECT_SCOPE_DENIED. Tầng sự kiện mới phân tích được số đối tượng khác nhau, chuỗi ID, actor và các mối liên hệ liên quan.

Không cần tải dữ liệu trái quyền để làm giàu tín hiệu. Có thể ghi định danh được yêu cầu đã kiểm soát định dạng và kết quả kiểm tra phạm vi; không ghi dữ liệu của đối tượng mà tác nhân không được phép đọc chỉ để điền dashboard.

### 7.3. Replay và xung đột idempotency

REPLAY thường là kết quả mong đợi của retry. PAYLOAD_CONFLICT, chẳng hạn cùng key nhưng nội dung khác, có ý nghĩa khác với replay đúng nội dung.

Tỷ lệ replay tăng cùng timeout và độ trễ mạng có thể là lỗi hạ tầng. Một chuỗi key xung đột với nhiều payload có thể cần phân tích sâu hơn.

Metric phải tách hai loại. Không lấy mọi lần nhận lại message làm số lần “tấn công trùng”.

### 7.4. Vi phạm thực tế sau commit

Ví dụ:

- Hai bút toán không được phép cùng business reference.
- Hoàn tiền vượt số tiền tối đa theo dữ liệu có thẩm quyền.
- Phê duyệt tồn tại mà vi phạm điều kiện độc lập đã xác định.
- Một tác động xảy ra mà không có quyết định hoặc lệnh hợp lệ theo thiết kế.

Tín hiệu loại này thường cần mức ưu tiên khác với lần thử đã bị chặn. Tuy vậy, cần xác nhận nguồn dữ liệu đủ hoàn chỉnh, quy tắc đúng và không đếm lặp một vi phạm trong mọi lần quét.

Một lần quét định kỳ phát hiện lại cùng cặp bút toán không nên làm counter “số vi phạm mới” tăng vô hạn. Cần violation ID ổn định hoặc trạng thái quản lý phát hiện tương ứng.

## 8. Đặt điểm đo đúng trong luồng nghiệp vụ

~~~mermaid
flowchart TD
    A["Lần thử vào handler"] --> B["Xác thực và xác minh phạm vi"]
    B --> C["Đánh giá policy và invariant khi cần"]
    C --> D{"Quyết định"}
    D -- "Từ chối" --> E["Ghi quyết định DENY và kết quả lần thử"]
    D -- "Cho phép" --> F["Xử lý nghiệp vụ hoặc trả kết quả đã có"]
    F --> G{"Kết quả"}
    G -- "Replay" --> H["Ghi REPLAYED_RESULT, không tăng tác động mới"]
    G -- "Chờ xử lý" --> I["Ghi ACCEPTED_PENDING"]
    G -- "Rollback hoặc lỗi" --> J["Ghi FAILED hoặc UNKNOWN đúng nghĩa"]
    G -- "Commit" --> K["Lưu thay đổi và sự kiện nhất quán"]
    K --> L["Tổng hợp tác động đã commit"]
    E --> M["Metric tổng hợp và sự kiện phân tích"]
    H --> M
    I --> M
    J --> M
    L --> M
~~~

Sơ đồ là luồng khái niệm. Thứ tự tra idempotency và các phép kiểm tra có thể khác theo thiết kế. Trước khi trả kết quả cũ vẫn phải kiểm tra quyền nhận kết quả trong phạm vi tương ứng. Không dùng replay để bỏ qua quyền theo đối tượng.

### 8.1. Quyết định từ chối không được mất theo rollback

Nếu bản ghi quyết định nằm trong cùng transaction rồi transaction rollback vì bị từ chối, tín hiệu có thể biến mất. Cần đường quan sát phù hợp cho nhánh từ chối, chẳng hạn journal hoặc pipeline riêng có mức bảo đảm đã xác định.

Counter trong bộ nhớ có thể giúp quan sát nhanh nhưng không phải bằng chứng bền vững. Cần biết sự cố tiến trình có thể làm mất số liệu nào.

### 8.2. Tác động thành công không được đếm trước commit

Tăng business_effects_total ngay trước khi gọi save có thể đếm cả giao dịch đã rollback. Với xử lý bất đồng bộ, HTTP 202 cũng không phải một tác động hoàn tất.

Nếu cần số liệu gắn chặt với commit, có thể lưu sự kiện vào outbox trong cùng transaction với dữ liệu nghiệp vụ, sau đó tổng hợp từ sự kiện đã commit hoặc đối chiếu với dữ liệu có thẩm quyền.

### 8.3. Giao nhận ít nhất một lần có thể làm metric tăng lặp

Outbox không tự tạo ngữ nghĩa đếm chính xác một lần ở mọi nơi. Publisher hoặc consumer có thể nhận lại cùng sự kiện.

Nếu consumer chỉ tăng counter trong bộ nhớ rồi ghi “đã xử lý event ID”, crash giữa hai bước có thể tạo đếm lặp hoặc thiếu. Để có số tổng hợp bền vững, cần cơ chế chống trùng và cập nhật rollup có quan hệ nguyên tử phù hợp, hoặc một thiết kế checkpoint và khôi phục tương đương.

Có thể chọn hai mức phục vụ khác nhau:

- Metric vận hành gần thời gian thực, có sai số và giới hạn đã biết.
- Số liệu đối chiếu hoặc bằng chứng chính xác hơn từ rollup bền vững và dữ liệu có thẩm quyền.

Không gọi một counter best-effort là “số tiền gian lận chính xác” hoặc “số giao dịch vi phạm tuyệt đối”.

## 9. Sự kiện có cấu trúc phục vụ điều tra

Một sự kiện quyết định tối thiểu có thể có dạng:

~~~json
{
  "schemaVersion": 1,
  "eventId": "decision-5f21",
  "eventType": "BUSINESS_POLICY_DECISION",
  "decidedAt": "2026-11-22T08:15:30Z",
  "operation": "refund.approve",
  "decision": "DENY",
  "reasonCode": "SELF_APPROVAL",
  "actorReference": "actor-ref-731",
  "tenantReference": "tenant-ref-26",
  "resourceReference": "refund-ref-420",
  "commandId": "command-882",
  "requestId": "request-391",
  "policyVersion": "refund-approval-v7",
  "sourceService": "refund-api"
}
~~~

Các reference có thể là định danh nội bộ hoặc định danh giả danh theo thiết kế. Chúng vẫn phải được bảo vệ; đổi tên trường thành reference không tự làm dữ liệu vô hại.

Từ sự kiện này, metric chỉ lấy các trường giới hạn như operation, decision và reasonCode. Actor, tenant, resource và request ID nằm ở tầng truy vấn chi tiết có kiểm soát quyền.

Không ghi access token, cookie phiên, mật khẩu, OTP, raw authorization header hoặc toàn bộ request body để “phân tích sau”. Những dữ liệu đó làm tăng nguy cơ lộ thông tin mà không cần thiết cho nhiều câu hỏi phát hiện lạm dụng.

### 9.1. Chuẩn hóa ở phía máy chủ

Mã Java minh họa dưới đây chỉ thể hiện việc giới hạn nhãn, không triển khai pipeline hay thư viện metric cụ thể:

~~~java
enum AbuseReason {
    POLICY_ALLOW,
    SELF_APPROVAL,
    OBJECT_SCOPE_DENIED,
    INVALID_STATE,
    AMOUNT_MISMATCH,
    DELEGATION_SCOPE_DENIED,
    OTHER
}

AbuseReason toMetricReason(PolicyReason internalReason) {
    return switch (internalReason) {
        case ALLOWED -> AbuseReason.POLICY_ALLOW;
        case APPROVER_IS_REQUESTER -> AbuseReason.SELF_APPROVAL;
        case RESOURCE_OUTSIDE_SCOPE -> AbuseReason.OBJECT_SCOPE_DENIED;
        case STATE_NOT_APPROVABLE -> AbuseReason.INVALID_STATE;
        case CLIENT_AMOUNT_DIFFERS -> AbuseReason.AMOUNT_MISMATCH;
        case DELEGATION_NOT_PERMITTED ->
            AbuseReason.DELEGATION_SCOPE_DENIED;
        default -> AbuseReason.OTHER;
    };
}
~~~

PolicyReason là kiểu do ứng dụng tự định nghĩa. Không lấy chuỗi reason do client gửi rồi đưa thẳng vào nhãn. Việc chuẩn hóa không làm mất sự cần thiết phải lưu lý do chi tiết phù hợp ở audit hoặc sự kiện có quyền truy cập riêng.

### 9.2. Nguồn sự kiện phải có độ tin cậy rõ ràng

Client có thể gửi telemetry giả. Một message trong broker cũng không mặc nhiên có nguồn gốc đáng tin nếu quyền producer quá rộng.

Metric về quyết định máy chủ phải được phát từ thành phần có thẩm quyền, bảo vệ đường chuyển tiếp và phân biệt với dữ liệu client tự báo. Nếu hợp nhất nhiều nguồn, cần tránh đếm hai lần cùng một quyết định ở gateway và backend.

## 10. Thiết kế điều kiện phát hiện và ngưỡng

### 10.1. Bắt đầu từ câu hỏi và giả thuyết

Ví dụ giả thuyết: “Một chức năng hoàn tiền đang bị thử tự phê duyệt nhiều hơn thông thường”.

Một quy tắc minh họa có thể yêu cầu trong cửa sổ 10 phút:

~~~text
blockedSelfApproval >= 30
AND evaluatedDecisions >= 100
AND blockedSelfApprovalRatio >= 0.20
~~~

Các số này chỉ minh họa cấu trúc kết hợp số lượng, cỡ mẫu và tỷ lệ. Chúng không phải ngưỡng khuyến nghị cho mọi hệ thống.

Có thể yêu cầu điều kiện kéo dài qua nhiều lần đánh giá để giảm nhiễu. Tuy nhiên, điều đó làm tăng thời gian phát hiện. Với một vi phạm tác động thực tế đã được xác nhận, thiết kế có thể cần phản ứng ngay mà không chờ đủ lượng lớn.

### 10.2. Một ngưỡng toàn hệ thống có thể bỏ sót nhiều kiểu tấn công

- **Lưu lượng lớn che tỷ lệ:** nhiều request hợp lệ làm tỷ lệ từ chối thấp dù số lần thử xấu tăng.
- **Chậm và kéo dài:** mỗi cửa sổ ngắn có ít sự kiện nhưng chuỗi nhiều giờ đáng chú ý.
- **Phân tán:** nhiều tài khoản hoặc kênh chia nhỏ hành vi.
- **Lưu lượng thấp:** một số ít tác động có giá trị cao nhưng không đủ ngưỡng số lượng.
- **Thao túng mẫu số:** nguồn không tin cậy tạo thêm các request trông hợp lệ để làm loãng tỷ lệ.

Vì vậy, có thể cần cửa sổ ngắn và dài, số tuyệt đối, tỷ lệ, mức tập trung và tín hiệu về tác động thực tế. Không có một công thức duy nhất bao phủ mọi tình huống.

### 10.3. Baseline cần bối cảnh

So sánh với mức thông thường có thể xét giờ trong ngày, ngày trong tuần, chiến dịch hoặc nhóm kênh. Nhưng baseline cũng có thể bị nhiễm bởi sự cố kéo dài hoặc hành vi xấu đã tồn tại.

Cần quản lý giai đoạn xây baseline, ghi nhận thay đổi policy và tránh để việc tự thích nghi che đi một invariant đã bị vi phạm. Một xu hướng tăng dần không tự trở thành an toàn chỉ vì detector đã quen với nó.

Khi phát hành client hoặc thay đổi chính sách quyền, số từ chối có thể tăng hợp lệ hoặc do lỗi. Đánh dấu mốc triển khai giúp phân tích nguyên nhân; không nên tắt mọi cảnh báo chỉ vì đang có release.

### 10.4. Cảnh báo cần có khả năng hành động

Một cảnh báo hữu ích nên cho biết:

- Hành động và nhóm lý do đang bất thường.
- Cửa sổ thời gian, số lượng, tỷ lệ và mẫu số.
- Độ trễ hoặc trạng thái sức khỏe của dữ liệu.
- Đây là dấu hiệu bị chặn, nghi ngờ tác động hay vi phạm đã xác nhận.
- Liên kết tới truy vấn điều tra có kiểm soát quyền.
- Nhóm chịu trách nhiệm và các bước xác minh ban đầu.

Tránh đưa danh sách user ID, email hoặc nội dung request nhạy cảm vào kênh cảnh báo rộng. Không cần gửi hàng trăm cảnh báo cho cùng một chuỗi sự kiện; nhóm hoặc chống lặp cảnh báo theo tiêu chí đã xác định, đồng thời giữ được lịch sử điều tra.

## 11. Quan sát chính hệ thống phát hiện

“Không thấy abuse” có thể do không có tín hiệu, nhưng cũng có thể do producer ngừng phát, consumer bị lỗi hoặc dữ liệu đến chậm.

Cần theo dõi tối thiểu:

| Tín hiệu sức khỏe | Rủi ro được phát hiện |
|---|---|
| Lượng sự kiện đầu vào so với lượng handler theo hợp đồng | Một đường thực thi không phát dữ liệu hoặc sự kiện bị rơi |
| Độ trễ từ decidedAt đến lúc được đánh giá | Cảnh báo phản ánh quá khứ quá xa |
| Lỗi parse, schema hoặc ánh xạ reason | Sự kiện mới bị bỏ hoặc gom sai |
| Outbox và hàng đợi tồn đọng | Quyết định đã có nhưng chưa đến detector |
| Tỷ lệ event ID trùng | Giao nhận lặp đang làm sai số liệu nếu không xử lý |
| Số dữ liệu bị loại do sai thời gian | Đồng hồ hoặc nguồn thời gian có vấn đề |
| Độ phủ operation và channel | Chỉ quan sát API nhưng bỏ worker hoặc luồng quản trị |
| Trạng thái truy vấn và đánh giá cảnh báo | Metric tồn tại nhưng rule không chạy được |

Không sampling tùy ý rồi dùng số đếm như dữ liệu đầy đủ. Nếu chỉ giữ một phần sự kiện, cần biết chính sách lấy mẫu và sai số. Lấy mẫu theo trace có thể bỏ toàn bộ một chuỗi hiếm; lấy mẫu không đều theo outcome có thể làm tỷ lệ từ chối bị lệch.

Đối với invariant hiếm nhưng hậu quả cao, cần một nguồn ghi nhận phù hợp thay vì trông cậy vào log debug được lấy mẫu.

Khi dữ liệu thiếu, dashboard cần thể hiện tình trạng không biết hoặc độ phủ không đạt. Tự điền giá trị 0 có thể tạo cảm giác an toàn sai.

## 12. Từ tín hiệu đến điều tra và phản ứng

Một luồng xử lý thực tế có thể gồm:

1. Xác nhận cảnh báo dùng đúng cửa sổ, mẫu số và dữ liệu chưa bị trễ bất thường.
2. Kiểm tra có release, thay đổi policy, lỗi timeout hoặc lỗi tích hợp gần thời điểm đó không.
3. Xác định tín hiệu là lần thử bị chặn hay tác động đã commit.
4. Truy vấn sự kiện chi tiết theo quyền để xem mức tập trung, chuỗi đối tượng và actor đã xác minh.
5. Đối chiếu audit, trạng thái và ledger có thẩm quyền khi cần xác nhận hậu quả.
6. Chọn phản ứng theo mức độ chắc chắn và phạm vi ảnh hưởng.
7. Ghi nhận kết luận để hiệu chỉnh rule và kiểm soát nghiệp vụ.

Một tỷ lệ từ chối toàn hệ thống tăng không đủ căn cứ để tự động khóa mọi tài khoản. Nếu có phản ứng tự động như giảm tốc độ hoặc yêu cầu xác thực bổ sung, cần thiết kế riêng điều kiện, phạm vi, thời hạn, khả năng phục hồi và tín hiệu đánh giá tác dụng phụ.

Đối với vi phạm đã tạo tác động, ưu tiên còn có thể gồm ngăn tác động tiếp diễn, giữ bằng chứng và xử lý dữ liệu nghiệp vụ theo quy trình có thẩm quyền. Metric không thay thế quyền quyết định sửa giao dịch.

## 13. Tình huống kiểm thử khi triển khai

Các tình huống sau dùng để thiết kế kiểm thử cho một hệ thống thực tế; mã minh họa trong bài chưa phải triển khai đã được chạy.

| Tình huống | Điều cần xác minh |
|---|---|
| Một request chạy nhiều rule | Chỉ tăng một quyết định cuối cùng nếu hợp đồng metric quy định như vậy |
| Policy không đánh giá được | Không âm thầm phân loại thành quyết định từ chối đã đánh giá |
| ALLOW nhưng transaction rollback | Không tăng số tác động đã commit |
| API nhận việc bất đồng bộ | Ghi ACCEPTED_PENDING, không ghi tác động hoàn tất |
| Retry hợp lệ nhận kết quả cũ | Tăng tín hiệu replay phù hợp, không tăng tác động mới |
| Cùng key nhưng payload khác | Phân biệt PAYLOAD_CONFLICT với replay thông thường |
| Cùng event được giao hai lần | Rollup hoặc detector không đếm hai vi phạm mới cho cùng bằng chứng |
| Một vi phạm xuất hiện ở nhiều lần quét | Có định danh hoặc trạng thái chống đếm lặp |
| Không có quyết định trong cửa sổ | Tỷ lệ không bị diễn giải thành bằng chứng an toàn bằng 0 |
| Một actor gửi reason và URL tùy ý | Không tạo nhãn có số giá trị không giới hạn |
| Hai tenant có dữ liệu điều tra | Quyền truy vấn không làm lộ dữ liệu chéo tenant |
| Pipeline ngừng hoặc trễ | Có tín hiệu sức khỏe thay vì dashboard im lặng |
| Tiến trình phát metric khởi động lại | Phép tính cửa sổ xử lý reset theo hợp đồng công cụ |
| Lượng hợp lệ tăng mạnh | Không chỉ dựa vào tỷ lệ đã bị pha loãng |
| Tấn công chậm hoặc phân tán | Kiểm tra thêm cửa sổ dài và tầng phân tích chuỗi |
| Client cũ gây AMOUNT_MISMATCH | Có thể phân tích nguồn lỗi mà không mặc định kết luận gian lận |
| Sự kiện đến ngoài thứ tự | Cửa sổ và số liệu điều chỉnh theo quy tắc đã xác định |
| Sampling hoặc mất sự kiện | Sai số và độ phủ được thể hiện, không trình bày như số tuyệt đối đầy đủ |

Ngoài việc kiểm tra counter có tăng, cần đối chiếu với kết quả nghiệp vụ thực tế. Một bài kiểm thử có thể cho thấy metric ghi một tác động dù database rollback; đó là lỗi ngữ nghĩa quan sát, không phải chỉ lỗi dashboard.

## 14. Checklist thiết kế abuse metric

Trước khi đưa một chỉ số vào dashboard hoặc cảnh báo, hãy trả lời:

1. Nó gắn với invariant, quyền theo đối tượng hoặc kiểu lạm dụng nào?
2. Đơn vị đếm là lần thử, quyết định, tác động hay vi phạm đã xác nhận?
3. Điểm phát nằm trước hay sau commit, và nhánh từ chối có bị mất theo rollback không?
4. Retry, replay, giao nhận lặp và quét lại được xử lý thế nào?
5. Mẫu số có cùng phạm vi, cửa sổ và nguồn dữ liệu với tử số không?
6. Nhãn có tập giá trị giới hạn và tránh định danh nhạy cảm không?
7. Có thể điều tra chi tiết qua sự kiện và audit mà không mở rộng quyền truy cập không?
8. Ngưỡng có xét số lượng, tỷ lệ, cỡ mẫu, baseline và thời gian phát hiện không?
9. Pipeline thiếu hoặc trễ dữ liệu có được biểu hiện rõ không?
10. Người nhận cảnh báo có biết cần xác minh gì và phản ứng trong phạm vi nào không?

Một abuse metric có giá trị khi người vận hành hiểu chính xác điều nó đo, điều nó chưa chứng minh và cách đi từ tín hiệu đến bằng chứng. Khi được đặt đúng chỗ, nó giúp phát hiện nỗ lực vượt quy tắc và hậu quả thực tế, đồng thời kiểm tra xem các kiểm soát transaction, state machine, quyền và idempotency có đang hoạt động như thiết kế hay không.
