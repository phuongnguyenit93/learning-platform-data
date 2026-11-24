# Dependency health metric

## 1. Sức khỏe dependency trong bảo mật logic nghiệp vụ

**Dependency health metric** là chỉ số giúp đánh giá một thành phần phụ thuộc có cung cấp được kết quả đủ tin cậy, đúng thời hạn và đúng hợp đồng để hệ thống thực thi nghiệp vụ hay không. Dependency có thể là dịch vụ phân quyền, nguồn chính sách, dịch vụ giá, kho tồn, cơ sở dữ liệu, bộ lưu idempotency, cổng thanh toán hoặc đường lưu bằng chứng audit.

Trong chương **Observability** của module bảo vệ logic nghiệp vụ, câu hỏi không chỉ là “dependency có đang chạy?”. Cần biết sự suy giảm của nó đang ảnh hưởng thế nào đến các quy tắc như không bỏ qua phê duyệt, không dùng sai giá, không thao tác ngoài quyền và không cấp quyền lợi trùng.

Ví dụ, nguồn chính sách trả HTTP 200 rất nhanh nhưng đang phục vụ phiên bản hết hạn. Nếu ứng dụng dùng kết quả đó để cho phép hoàn tiền, biểu đồ HTTP có thể xanh trong khi kiểm soát nghiệp vụ đã suy yếu. Ngược lại, dịch vụ phân quyền trả quyết định `DENY` hợp lệ cho người không có quyền là hoạt động đúng, không phải sự cố dependency.

Một thiết kế cần phân biệt ba câu hỏi:

1. Dependency có phản hồi và phản hồi đó có dùng được theo hợp đồng không?
2. Luồng nghiệp vụ có hoàn thành an toàn trong ngân sách thời gian không?
3. Hệ thống có làm yếu bất biến để che sự cố dependency không?

Metric cung cấp tín hiệu tổng hợp để phát hiện và vận hành. Metric không thay thế kiểm tra quyền, transaction, state machine hay bằng chứng audit cho từng hành động.

## 2. Lập bản đồ dependency theo bất biến cần bảo vệ

Không nên bắt đầu bằng cách gom tất cả dependency vào một cờ `healthy`. Trước hết, xác định mỗi dependency bảo vệ hoặc hỗ trợ quy tắc nào và khi nó lỗi thì ứng dụng được phép làm gì.

| Dependency | Vai trò trong nghiệp vụ | Rủi ro khi suy giảm | Hành vi an toàn cần định nghĩa |
|---|---|---|---|
| Dịch vụ phân quyền theo đối tượng | Xác định actor có quyền trên đúng tài nguyên và tenant | Tự cho phép khi timeout, dùng quyết định của đối tượng khác | Không thực hiện thay đổi nếu thiếu căn cứ quyền hợp lệ |
| Nguồn chính sách phê duyệt | Cung cấp hạn mức, yêu cầu phân tách nhiệm vụ và revision | Dùng quy tắc cũ để bỏ bước duyệt | Kiểm tra phiên bản, hiệu lực và chính sách dùng bản lưu |
| Dịch vụ giá | Cung cấp giá và điều kiện chiết khấu từ máy chủ | Chấp nhận giá client gửi khi nguồn giá lỗi | Giữ báo giá hợp lệ theo hợp đồng hoặc chưa cho chốt đơn |
| Kho tồn hoặc quota | Giữ giới hạn cấp phát trong cạnh tranh | Bán vượt, cấp quota trùng | Dùng cơ chế ghi có điều kiện và bất biến tại nguồn có thẩm quyền |
| Bộ lưu idempotency | Ràng buộc command với nội dung và kết quả đã lưu | Retry tạo hiệu ứng lặp khi mất bộ nhớ chống trùng | Không dựa vào cache tạm như bằng chứng duy nhất đã xử lý |
| Cổng thanh toán | Tạo hoặc xác nhận hiệu ứng tiền tệ | Timeout bị hiểu thành chưa thanh toán, gửi lại lệnh mới | Giữ trạng thái chưa rõ kết quả và đối soát theo command ổn định |
| Đường audit bắt buộc | Lưu bằng chứng gắn với thay đổi | Có hiệu ứng nhưng mất bằng chứng theo chính sách | Phân biệt lỗi lưu tại nguồn và trễ chuyển tiếp khi bản gốc vẫn bền vững |

Mức trọng yếu phụ thuộc hành động. Cùng một nguồn giá có thể chỉ ảnh hưởng thông tin tham khảo ở trang danh mục nhưng là điều kiện bắt buộc khi xác nhận đơn hàng.

OWASP nhấn mạnh việc suy ra giá trị liên quan bảo mật ở phía máy chủ, thực thi workflow rõ ràng và bảo vệ các bất biến nghiệp vụ. Vì vậy, khi dependency lỗi, thay kết quả đáng tin bằng giá hoặc quyền do client khai sẽ làm mất chính kiểm soát đang cần bảo vệ. Xem [OWASP Business Logic Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html).

## 3. Định nghĩa đơn vị đo và kết quả trước khi đặt tên metric

### 3.1. Phân biệt operation, attempt và command

Trong bài này, các thuật ngữ được dùng như sau:

| Đơn vị | Ý nghĩa | Ví dụ |
|---|---|---|
| Command nghiệp vụ | Một lệnh có định danh và bất biến riêng | Phê duyệt `refund-42` |
| Dependency operation | Một lần phía gọi cần kết quả từ một dependency cho một mục đích | Lấy quyết định quyền để phê duyệt hồ sơ |
| Attempt | Một lần thực sự gọi dependency trong operation | Gọi HTTP lần đầu hoặc một lần retry |
| Fallback | Một đường thay thế được chính sách cho phép | Dùng snapshot chính sách còn hiệu lực |
| Hiệu ứng nghiệp vụ | Thay đổi quyền lợi hoặc trạng thái thực sự | Ghi nhận phê duyệt hoặc nhà cung cấp xác nhận hoàn tiền |

Một operation có thể gồm hai attempt và một lần xét fallback. Counter operation phải tăng một lần khi operation kết thúc; counter attempt có thể tăng hai lần. Không lấy tổng attempt làm tổng số command hoặc tổng số quyền lợi đã cấp.

Với cache hit không cần gọi mạng, operation vẫn tồn tại nhưng có thể không có attempt mạng. Với circuit breaker đang mở, operation có thể kết thúc ngay mà không tạo attempt nào.

### 3.2. Phân loại kết quả theo khả năng sử dụng

Bài sử dụng tập kết quả tự định nghĩa:

| `outcome` | Định nghĩa |
|---|---|
| `usable` | Có kết quả hợp lệ cho đúng phạm vi và mục đích, còn hiệu lực, được chấp nhận trong deadline của operation |
| `unavailable` | Không có kết quả đủ dùng; phía gọi không được tiếp tục nghiệp vụ dựa trên kết quả đó |
| `indeterminate` | Chưa xác định được một hiệu ứng bên ngoài có xảy ra hay không, cần đối soát |

Với phép đọc chính sách không gây hiệu ứng, timeout thường dẫn đến `unavailable` nếu không có fallback hợp lệ. Với lệnh hoàn tiền đã có thể đến nhà cung cấp, timeout có thể dẫn đến `indeterminate`. Không áp cùng một kết luận cho mọi kiểu timeout.

Quyết định `ALLOW` và `DENY` đều có thể là `usable` nếu được xác thực, đúng đối tượng, đúng chính sách và đúng hạn. Tỷ lệ bị từ chối quyền tăng có thể là tín hiệu lạm dụng hoặc thay đổi nghiệp vụ, nhưng không tự chứng minh dependency đang lỗi.

Phản hồi HTTP 200 có schema sai, thiếu revision, sai tenant hoặc đã hết hiệu lực phải bị phân loại là không dùng được. Không dùng mã HTTP làm định nghĩa duy nhất của thành công.

### 3.3. Nguồn kết quả và thời điểm ghi

Metric operation trong bài có `source` thuộc tập:

- `primary`: kết quả được chấp nhận từ nguồn chính.
- `cache`: bản lưu được chấp nhận theo đúng hợp đồng hiệu lực và phạm vi.
- `safe_default`: giá trị mặc định được chính sách của loại nghiệp vụ đó cho phép.
- `none`: không có kết quả được chấp nhận, bao gồm kết quả chưa xác định.

`safe_default` không có nghĩa được phép mặc định cấp quyền. Một mặc định an toàn cho dữ liệu trang trí giao diện có thể phù hợp; “nguồn quyền lỗi thì cho phép” là thay đổi kiểm soát bảo mật.

Operation hoàn tất được đếm tại một điểm duy nhất. Thời lượng dùng đồng hồ đơn điệu, gồm thời gian đợi, gọi mạng, retry/backoff, xác minh dữ liệu và xét fallback trong phạm vi operation. Việc đo riêng thời gian của attempt cuối sẽ che thời gian người gọi đã thực sự chờ.

Prometheus khuyến nghị theo dõi số truy vấn, lỗi, độ trễ và có thể cả lượng đang xử lý; đồng thời cần nhất quán về thời điểm đếm. Có thể đối chiếu hướng dẫn tại [Prometheus Instrumentation](https://prometheus.io/docs/practices/instrumentation/). Tên và tập label bên dưới là thiết kế minh họa của bài.

## 4. Bộ metric tham chiếu

### 4.1. Các chỉ số cốt lõi

| Metric | Loại | Label nghiệp vụ có giới hạn | Ngữ nghĩa |
|---|---|---|---|
| `business_dependency_operations_total` | Counter | `dependency, operation, outcome, source` | Một lần tăng cho mỗi operation kết thúc |
| `business_dependency_operation_duration_seconds` | Histogram | `dependency, operation, outcome` | Thời lượng operation kết thúc, kể cả retry và fallback |
| `business_dependency_inflight` | Gauge | `dependency, operation` | Số operation hiện còn đang xử lý tại instance |
| `business_dependency_attempts_total` | Counter | `dependency, operation, outcome` | Kết quả của từng attempt gọi nguồn chính |
| `business_dependency_fallback_total` | Counter | `dependency, operation, mode, outcome` | Mỗi lần xét fallback, với mode và kết quả chấp nhận hoặc từ chối |
| `business_dependency_invalid_data_total` | Counter | `dependency, operation, reason` | Dữ liệu bị loại trong xác minh, theo mã lý do hữu hạn |

Label `outcome` thuộc hợp đồng riêng của từng metric. Với attempt, có thể dùng `usable_response, remote_error, invalid_response, timeout, transport_error, cancelled`. Với fallback, dùng `accepted, rejected`; `mode` là `cache` hoặc `safe_default`.

Không cộng counter invalid-data vào counter operation để suy ra tổng operation: một operation có thể nhận nhiều phản hồi không hợp lệ qua retry. Các counter mô tả những đơn vị quan sát khác nhau.

Ví dụ một timeout, retry nhận policy hết hạn, rồi cache hợp lệ:

```text
operations_total: +1 với outcome=usable, source=cache
attempts_total: +1 timeout, +1 invalid_response
invalid_data_total: +1 reason=expired
fallback_total: +1 mode=cache, outcome=accepted
operation_duration_seconds: quan sát tổng thời gian của operation
```

Dashboard chỉ nhìn `usable` sẽ thấy luồng còn phục vụ được, nhưng bộ chỉ số attempt và source cho thấy nguồn chính đang suy giảm. Cả hai kết luận đều cần thiết.

### 4.2. Chỉ số bổ sung theo loại dependency

| Metric | Loại | Phạm vi và ý nghĩa |
|---|---|---|
| `business_dependency_last_valid_refresh_timestamp_seconds` | Gauge | Theo `dependency, dataset`; thời điểm refresh thành công đã được xác minh của snapshot hoặc dataset được định nghĩa |
| `business_dependency_circuit_state` | Gauge | Theo `dependency, operation, state`; giá trị one-hot 0/1 cho `closed, open, half_open` tại từng instance |
| `business_dependency_pending_reconciliation` | Gauge | Theo `dependency, operation`; số command có hiệu ứng chưa xác định, lấy từ nguồn trạng thái bền vững |
| `business_dependency_oldest_pending_timestamp_seconds` | Gauge | Theo `dependency, operation`; timestamp command chờ đối soát lâu nhất; bằng 0 khi không có |
| `business_dependency_pool_in_use` và `business_dependency_pool_capacity` | Gauge | Mức dùng và sức chứa của pool được định nghĩa, không trộn với độ sâu hàng đợi |
| `business_security_guardrail_violations_total` | Counter | Theo `workflow, control`; vi phạm bất biến đã được phát hiện, không phải mọi lần yêu cầu bị chặn |

Ví dụ giá trị `control` có thể là `authorization_bypass`, `expired_policy_used`, `approval_skipped` hoặc `duplicate_effect`. Chỉ tăng khi điều kiện vi phạm theo hợp đồng thực sự được quan sát. Một lần cố bỏ phê duyệt đã bị chặn đúng không phải là một lần đã bỏ phê duyệt thành công.

Gauge pending phải được khôi phục từ nguồn có thẩm quyền sau restart. Đặt nó về 0 chỉ vì tiến trình vừa khởi động sẽ làm mất tín hiệu về những giao dịch đang cần đối soát.

Timestamp refresh không được cập nhật khi đọc cache hoặc khi một job chỉ “đã chạy”. Nó mô tả lần làm mới hợp lệ đã hoàn tất. Metric này cũng không chứng minh mọi entry trong một cache theo đối tượng đều mới; cần định nghĩa chính xác dataset và vẫn kiểm tra từng quyết định khi sử dụng.

### 4.3. Label, cardinality và dữ liệu nhạy cảm

Dùng tên dependency và operation từ danh mục có kiểm soát, ví dụ `policy/authorize_refund` hoặc `payment/execute_refund`. Không lấy tên dependency, URL, tenant hay operation từ một trường request tùy ý.

Không đưa `userId`, `orderId`, `refundId`, idempotency key, access token, toàn bộ URL hoặc thông điệp exception vào label. Định danh cần cho điều tra thuộc log/audit hoặc trace được phân quyền; metric chỉ giữ chiều tổng hợp có giới hạn.

Prometheus khuyến nghị tránh label với tập giá trị không giới hạn và dùng đơn vị cơ sở nhất quán trong tên metric. Xem [Metric and label naming](https://prometheus.io/docs/practices/naming/).

Label môi trường, job, cluster hoặc vùng có thể được gắn ở tầng thu thập theo thiết kế triển khai. Khi tổng hợp cần giữ những chiều giúp phát hiện sự cố cục bộ. Trung bình toàn hệ thống có thể che một vùng đang dùng fallback trái chính sách.

Nên khởi tạo các tổ hợp label hợp lệ đã biết ở giá trị 0 khi phù hợp. Không tạo toàn bộ tích Descartes vô ích và không tự coi chuỗi chưa xuất hiện là bằng 0 nếu chưa biết pipeline thu thập còn hoạt động.

## 5. Xây dựng SLI với tử số và mẫu số rõ ràng

### 5.1. Tỷ lệ kết quả không đủ dùng

Trong một cửa sổ thời gian và cùng phạm vi dependency/operation:

```text
completed = usable + unavailable + indeterminate

unusable_ratio = (unavailable + indeterminate) / completed

usable_ratio = usable / completed
```

Đây là SLI cho operation đã kết thúc, không phải tỷ lệ command nghiệp vụ thành công. Một quyết định quyền `DENY` hợp lệ vẫn đóng góp vào `usable`; nghiệp vụ bị chặn đúng quyền chưa chắc là sự cố.

Mẫu số bằng 0 có nghĩa không có operation hoàn tất trong phạm vi đo. Không được kết luận dependency khỏe 100%. Có thể không có lưu lượng, có thể request đang treo, hoặc metric đã mất; cần dùng inflight, deadline, probe và sức khỏe telemetry để phân biệt.

Việc chỉ đếm operation kết thúc cũng có thể khiến một nhóm request bị treo tạm thời biến mất khỏi tỷ lệ. Vì vậy, phải có deadline được thực thi và theo dõi lượng đang xử lý. Counter hoàn tất không thay thế giới hạn thời gian.

### 5.2. Đo riêng sức khỏe nguồn chính và mức phụ thuộc fallback

Ví dụ trong 5 phút, operation đọc policy có:

| Kết quả | Số operation |
|---|---:|
| Dùng được từ primary | 940 |
| Dùng được từ cache hợp lệ | 40 |
| Không có kết quả dùng được | 20 |
| Tổng kết thúc | 1.000 |

Tỷ lệ kết quả dùng được là 98%. Tỷ lệ kết quả dùng được phải dựa vào cache là `40 / 980`, khoảng 4,08%. Hai con số không mô tả cùng một việc.

Nguồn chính có thể còn lỗi nhiều hơn do các operation đã retry hoặc được cache cứu. Cần xem attempt theo kết quả, số lần retry và fallback, không suy sức khỏe primary từ tỷ lệ cuối của operation.

Với lệnh gây hiệu ứng, cần xem thêm lượng command chưa xác định đang chờ đối soát. Counter `indeterminate` mô tả quan sát đã xảy ra; gauge pending mô tả trạng thái còn tồn tại. Sau đối soát, gauge có thể giảm nhưng không sửa ngược counter lịch sử.

### 5.3. Độ trễ và độ mới

Nên xem cả độ trễ của kết quả dùng được và phân bố mọi kết quả. Nếu tất cả request lỗi đều bị từ chối rất nhanh, p95 chung có thể giảm dù khả năng phục vụ đang xấu đi.

Histogram cần có các bucket phù hợp deadline và mục tiêu vận hành. Không chỉ dùng trung bình vì một nhóm request rất chậm có thể bị che khuất. Không lấy trung bình p95 của từng instance để coi là p95 toàn hệ thống.

Độ mới có ít nhất hai nghĩa khác nhau:

- Lần đồng bộ hợp lệ gần nhất xảy ra khi nào.
- Quyết định hoặc dữ liệu cụ thể đang dùng còn hiệu lực theo hợp đồng hay không.

Một job vừa refresh thành công chưa đủ chứng minh mọi quyền thu hồi đã được áp dụng nếu giao thức đồng bộ không bảo đảm điều đó. TTL cũng không tự chứng minh có thể dùng quyền cũ sau thu hồi. Các bảo đảm về revision, lease, revocation và thời gian phải được xác định trong thiết kế quyền.

## 6. Ví dụ PromQL

Các truy vấn dùng metric tự định nghĩa ở mục 4 và **classic histogram**, giả định label `job="refund-api"` và `environment="prod"` đã được cấu hình ở tầng thu thập. Cửa sổ 5 phút là lựa chọn minh họa.

Các truy vấn tổng hợp theo dependency và operation trong phạm vi đó. Nếu cần phát hiện lỗi theo vùng hoặc cluster, phải giữ thêm chiều tương ứng hoặc lọc cụ thể trước khi tổng hợp.

### 6.1. Tỷ lệ operation không đủ dùng

```promql
sum by (dependency, operation) (
  rate(business_dependency_operations_total{
    job="refund-api",
    environment="prod",
    outcome=~"unavailable|indeterminate"
  }[5m])
)
/
sum by (dependency, operation) (
  rate(business_dependency_operations_total{
    job="refund-api",
    environment="prod"
  }[5m])
)
```

Các chuỗi kết quả hợp lệ cần được xuất nhất quán, gồm giá trị 0 cho loại lỗi đã biết khi phù hợp. Nếu một nhóm label chưa từng được xuất, tử số có thể vắng thay vì bằng 0. Cần xử lý từ hợp đồng instrumentation và expected-series; không tùy tiện thêm `or vector(0)` rồi che cả việc mất telemetry.

### 6.2. p95 của operation có kết quả dùng được

```promql
histogram_quantile(
  0.95,
  sum by (dependency, operation, le) (
    rate(business_dependency_operation_duration_seconds_bucket{
      job="refund-api",
      environment="prod",
      outcome="usable"
    }[5m])
  )
)
```

Prometheus yêu cầu giữ label `le` khi tổng hợp bucket của classic histogram; `rate` nên được tính trước khi cộng để xử lý reset counter đúng phạm vi. `histogram_quantile` cho giá trị ước lượng theo bucket, không phải thứ hạng chính xác từ mọi mẫu gốc. Xem [Prometheus Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Kết quả truy vấn này phải được đọc cùng tỷ lệ lỗi, inflight và lưu lượng. Không có kết quả dùng được thì p95 này không chứng minh độ trễ tốt. Truy vấn cũng không áp nguyên xi cho native histogram vì kiểu dữ liệu và cách tổng hợp khác.

### 6.3. Tỷ lệ kết quả dùng được đến từ đường thay thế

```promql
sum by (dependency, operation) (
  rate(business_dependency_operations_total{
    job="refund-api",
    environment="prod",
    outcome="usable",
    source=~"cache|safe_default"
  }[5m])
)
/
sum by (dependency, operation) (
  rate(business_dependency_operations_total{
    job="refund-api",
    environment="prod",
    outcome="usable"
  }[5m])
)
```

Tăng fallback có thể là dấu hiệu che khuất sự cố primary, không mặc định là vi phạm. Phải xem fallback đó có đúng hợp đồng cho operation hay không. Với một số thao tác bảo mật, cấu hình hợp lệ có thể hoàn toàn không cho phép `safe_default`.

### 6.4. Thời gian từ lần refresh hợp lệ gần nhất

```promql
time()
-
business_dependency_last_valid_refresh_timestamp_seconds{
  job="refund-api",
  environment="prod",
  dependency="policy",
  dataset="approval-policy"
}
```

Giữ chiều instance nếu mỗi instance có snapshot cục bộ. Lấy timestamp lớn nhất toàn cụm có thể che các instance không refresh được.

Gauge bằng 0 được quy định là chưa có refresh hợp lệ, không phải dữ liệu mới ở thời điểm bắt đầu epoch. Cần hiển thị trạng thái này rõ và không cho phép dùng snapshot chưa hợp lệ. Nếu timestamp nằm quá xa trong tương lai, phải xem vấn đề đồng hồ hoặc dữ liệu; không clamp về 0 rồi coi là mới.

### 6.5. Tuổi command chờ đối soát lâu nhất

```promql
(
  time()
  -
  business_dependency_oldest_pending_timestamp_seconds{
    job="refund-api",
    environment="prod"
  }
)
and
(
  business_dependency_pending_reconciliation{
    job="refund-api",
    environment="prod"
  } > 0
)
```

Hai gauge phải có cùng bộ label định danh phạm vi để phép ghép vector trên có nghĩa. Timestamp cần lấy từ thời điểm bắt đầu chờ đối soát bền vững, không đặt lại sau mỗi restart hoặc mỗi lần retry.

Không cộng gauge cùng một tập command được export đầy đủ bởi nhiều replica. Cần một exporter có thẩm quyền, phân vùng không trùng hoặc quy tắc tổng hợp được định nghĩa trước.

### 6.6. Phân biệt scrape lỗi và mất chuỗi metric

```promql
up{job="refund-api", environment="prod"} == 0
```

Truy vấn này phát hiện scrape thất bại đối với target đã biết. `up=1` chỉ cho biết lần scrape thành công, không chứng minh policy hoặc payment khỏe.

Ví dụ phát hiện cả nhóm metric của một dependency/operation không xuất hiện trong 10 phút:

```promql
absent_over_time(
  business_dependency_operations_total{
    job="refund-api",
    environment="prod",
    dependency="policy",
    operation="authorize_refund"
  }[10m]
)
```

Truy vấn trên chỉ nhận diện khi không còn bất kỳ chuỗi nào khớp toàn bộ bộ lọc trong cửa sổ. Nó không tự phát hiện từng instance hoặc từng dependency dự kiến bị thiếu nếu các chuỗi khác vẫn còn. Muốn kiểm tra đầy đủ từng cạnh phụ thuộc, cần inventory/expected-series và đối chiếu theo đúng label.

Không có lưu lượng nhưng counter được export ở giá trị 0 khác với không có chuỗi metric. Dashboard cần biểu diễn được cả hai tình huống.

## 7. Cảnh báo có gắn tác động nghiệp vụ

Không dùng cùng một ngưỡng cho nguồn dữ liệu trang trí giao diện và nguồn quyền quyết định hoàn tiền. Ngưỡng phải phản ánh deadline, mức trọng yếu, lưu lượng, lịch sử và hành vi suy giảm đã được chấp nhận.

Ví dụ cấu hình Prometheus dưới đây nằm trong tài liệu, không phải cấu hình đã triển khai. Các ngưỡng 2%, 100 operation và 10 phút chỉ để minh họa.

```yaml
groups:
  - name: business-dependency-health
    rules:
      - record: business_dependency:unusable_ratio5m
        expr: |
          sum by (dependency, operation) (
            rate(business_dependency_operations_total{
              job="refund-api",
              environment="prod",
              outcome=~"unavailable|indeterminate"
            }[5m])
          )
          /
          sum by (dependency, operation) (
            rate(business_dependency_operations_total{
              job="refund-api",
              environment="prod"
            }[5m])
          )

      - record: business_dependency:completed5m
        expr: |
          sum by (dependency, operation) (
            increase(business_dependency_operations_total{
              job="refund-api",
              environment="prod"
            }[5m])
          )

      - alert: BusinessDependencyDegraded
        expr: |
          (business_dependency:unusable_ratio5m > 0.02)
          and on (dependency, operation)
          (business_dependency:completed5m >= 100)
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Dependency không cung cấp đủ kết quả dùng được"

      - alert: BusinessSecurityGuardrailViolation
        expr: |
          sum by (workflow, control) (
            increase(business_security_guardrail_violations_total{
              job="refund-api",
              environment="prod"
            }[5m])
          ) > 0
        labels:
          severity: critical
        annotations:
          summary: "Đã phát hiện vi phạm bất biến nghiệp vụ"
```

Các recording rule trên lọc cố định một job và môi trường rồi chỉ giữ dependency/operation. Nếu dùng cho nhiều job hoặc môi trường, cần giữ thêm các label phạm vi trong recording rule và điều chỉnh phép ghép alert tương ứng để tránh trộn dữ liệu. Giá trị từ `increase` là ước lượng theo cửa sổ, không phải sổ đếm giao dịch chính xác.

Điều kiện đủ lưu lượng trong cảnh báo đầu giúp tránh phản ứng quá mức trước một tỷ lệ có mẫu rất nhỏ. Nó cũng có thể che lỗi ở luồng ít dùng, nên phải bổ sung probe phù hợp, giám sát trạng thái và tín hiệu nghiệp vụ riêng. Không đặt điều kiện tối thiểu 100 operation cho một vi phạm phân quyền đã được xác nhận chỉ vì rule availability dùng điều kiện đó.

Counter metric có thể mất các sự kiện giữa hai lần scrape nếu tiến trình dừng hoặc instrumentation không chạy. Cảnh báo guardrail trên là tín hiệu vận hành khi dữ liệu đã được thu thập; nó không bảo đảm bắt mọi vi phạm đơn lẻ. Sự kiện trọng yếu vẫn cần đường audit hoặc phát hiện bền vững thích hợp.

Trong hệ thống thực tế nên cân nhắc cửa sổ ngắn và dài, mục tiêu SLO và thời gian chấp nhận suy giảm. Tránh sao chép ngưỡng minh họa thành tiêu chuẩn bảo mật chung.

Google SRE phân biệt tín hiệu về triệu chứng người dùng thấy với tín hiệu bên trong giúp giải thích nguyên nhân, và sử dụng cả quan sát bên ngoài lẫn bên trong. Xem [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/). Trong bài này, tỷ lệ dependency lỗi giúp tìm nguyên nhân; command bị đình trệ, fallback trái chính sách hoặc tồn đọng đối soát thể hiện tác động cần xử lý.

## 8. Giữ nguyên kiểm soát khi dependency suy giảm

### 8.1. Metric không phải nguồn quyết định quyền

Một dashboard xanh không phải căn cứ để cho phép hành động. Quyền vẫn phải được kiểm tra trên đúng actor, đối tượng, tenant, hành động và phiên bản liên quan. Metric có thể bị trễ, mất scrape hoặc tổng hợp sai phạm vi.

Không xây logic “nếu tỷ lệ lỗi dưới ngưỡng thì bỏ qua kiểm tra còn thiếu”. Việc tiếp tục hay dừng phải dựa trên kết quả và chính sách suy giảm được áp dụng ngay trong đường xử lý.

| Trạng thái quan sát | Cách diễn giải | Hành vi cần giữ |
|---|---|---|
| Primary tốt, dữ liệu hợp lệ | Có căn cứ dùng kết quả | Vẫn áp dụng quyền, trạng thái và bất biến |
| Primary lỗi, cache được phép và còn hiệu lực | Hệ thống phục vụ trong chế độ suy giảm đã định nghĩa | Ghi nguồn cache, kiểm tra scope và hiệu lực mỗi lần dùng |
| Không có kết quả quyền hợp lệ | Không đủ căn cứ cho thay đổi cần quyền đó | Chưa thực hiện thay đổi; không mặc định cho phép |
| Hiệu ứng ngoài hệ thống chưa xác định | Cần đối soát, không đồng nghĩa chưa xảy ra | Giữ command và khóa nhà cung cấp ổn định, không cấp quyền lợi mới tùy tiện |
| Telemetry không rõ | Mất khả năng quan sát trong phạm vi đó | Khôi phục quan sát; không suy ra dependency khỏe hoặc tự tắt kiểm soát |

Cache quyền phải có khóa đúng phạm vi và hợp đồng hiệu lực phù hợp cơ chế thu hồi. Cache hit cao không chứng minh an toàn; cache hit sai đối tượng có thể vừa nhanh vừa nguy hiểm.

Nếu chính sách thay đổi giữa lúc lấy quyết định và lúc commit, hệ thống phải có cách bảo vệ khoảng đó, chẳng hạn kiểm tra revision trong điều kiện ghi hoặc dùng một hợp đồng hiệu lực đã được thiết kế. Timestamp mới và metric thành công không tự giải quyết cuộc đua kiểm tra rồi sử dụng.

### 8.2. Circuit breaker và retry không thay thế chính sách

Circuit breaker giúp hạn chế tiếp tục gọi một nguồn đang lỗi; nó không quyết định người dùng được phép làm gì. Khi breaker mở, metric attempt có thể giảm về 0 trong khi operation vẫn thất bại. Vì vậy, cần đếm operation bị chặn và theo dõi trạng thái breaker.

Retry phải nằm trong deadline và giới hạn tải. Retry đồng loạt có thể tăng số attempt, chiếm pool và làm mọi request khác chậm hơn. Cần phân biệt tỷ lệ operation tốt cuối cùng với chi phí để đạt kết quả đó.

Với thao tác gây hiệu ứng, không retry chỉ vì thấy timeout hoặc metric lỗi tăng. Cần hợp đồng idempotency với nhà cung cấp, nội dung command ổn định, trạng thái bền vững và bước đối soát. Nếu dùng cùng khóa nhưng đổi số tiền hoặc đối tượng, đó không còn là retry hợp lệ của cùng lệnh.

Nếu mất bộ lưu idempotency, không thay bằng một map trong RAM rồi coi cơ chế chống trùng vẫn được bảo đảm qua nhiều instance và restart.

### 8.3. Đối soát trạng thái chưa xác định

Một lệnh hoàn tiền có thể đã được nhà cung cấp thực hiện nhưng response bị mất. Hệ thống nên giữ trạng thái kiểu `PENDING_RECONCILIATION` theo thiết kế, thay vì chuyển ngay sang “chưa hoàn” và phát lệnh mới.

Các tín hiệu cần theo dõi gồm:

- Số command duy nhất đang chờ đối soát.
- Tuổi command chờ lâu nhất và phân bố tuổi nếu cần.
- Tốc độ nhận thêm và giải quyết trường hợp chưa xác định.
- Kết quả đối soát: đã xác nhận thành công, xác nhận không có hiệu ứng hoặc tiếp tục chưa rõ.
- Vi phạm bất biến phát hiện từ sổ nghiệp vụ hoặc dữ liệu nhà cung cấp, như hoàn vượt hoặc hiệu ứng trùng.

HTTP 202 chỉ có thể biểu diễn việc nhận yêu cầu theo hợp đồng API. Không tăng một counter “đã hoàn tiền thành công” nếu mới chỉ có bằng chứng nhà cung cấp đã tiếp nhận.

## 9. Ví dụ instrumentation trong ứng dụng Java

Ví dụ sau là **mã giả theo cú pháp Java** cho phép đọc quyết định quyền, không gây hiệu ứng bên ngoài. Các lớp `ObservedDependency`, `Deadline` và helper là khái niệm minh họa, không phải API của một thư viện cụ thể.

```java
PolicyDecision loadApprovalDecision(
        PolicyQuery query,
        TrustedContext ctx,
        Deadline deadline
) {
    try (ObservedDependency observation =
            telemetry.start("policy", "authorize_refund")) {
        try {
            // Helper quản lý attempt, deadline, retry có giới hạn,
            // kiểm tra schema, subject, tenant, action, revision và hiệu lực.
            PolicyDecision decision =
                    primary.readValidatedWithinBudget(query, ctx, deadline);

            // ALLOW và DENY hợp lệ đều là usable.
            observation.complete("usable", "primary");
            return decision;
        } catch (DependencyReadFailure failure) {
            // Chỉ nhận lỗi đọc dependency đã phân loại.
            // Không catch AccessDenied rồi thử một đường cấp quyền khác.
            if (fallbackPolicy.mayUseCache(query.action(), failure.code())) {
                PolicyDecision cached = cache.findExactScope(query, ctx);

                if (cached != null) {
                    Validation validation =
                            validator.check(cached, query, ctx, deadline);

                    if (validation.isUsable()) {
                        observation.fallback("cache", "accepted");
                        observation.complete("usable", "cache");
                        return cached;
                    }

                    observation.invalidCandidate(validation.reasonCode());
                }

                observation.fallback("cache", "rejected");
            }

            observation.complete("unavailable", "none");
            throw new DependencyUnavailable(failure);
        }
    }
}
```

Hợp đồng các helper trong ví dụ cần rõ:

1. `telemetry.start` tăng inflight; `close` luôn giảm inflight trong tiến trình còn chạy và ghi thời lượng bằng đồng hồ đơn điệu.
2. Một observation chỉ có một kết quả cuối. `complete` không được làm tăng counter nhiều lần nếu các nhánh gọi lặp.
3. Nếu phép đọc kết thúc do ngoại lệ chưa được ánh xạ, helper chốt kết quả không đủ dùng theo hợp đồng cho phép đọc này, đồng thời giữ nguyên ngoại lệ để bên gọi xử lý.
4. Helper gọi nguồn chính sở hữu counter attempt và invalid-data của phản hồi nguồn chính; đoạn xử lý cache chỉ ghi invalid-data của candidate cache. Tránh đếm một lỗi hai lần ở hai lớp.
5. `validator.check` kiểm tra cả deadline, actor/subject, tenant, object/action, revision và hiệu lực theo chính sách. Cache có entry chưa đồng nghĩa có kết quả dùng được.
6. `fallbackPolicy` được kiểm soát ở máy chủ; request không được tự bật fallback hoặc nới hạn hiệu lực.
7. Instrumentation không được biến lỗi nghiệp vụ thành thành công, nuốt quyết định từ chối hoặc làm phát sinh đường cấp quyền khi exporter lỗi.

Sau khi nhận `PolicyDecision`, bên gọi vẫn phải thực thi quyết định. Trả về một `DENY` hợp lệ không cho phép tiếp tục phê duyệt hồ sơ. Nếu quyết định là `ALLOW`, hệ thống vẫn cần state machine, kiểm tra phiên bản và transaction cho bước thay đổi.

Operation metric ở đây dừng khi có kết quả policy hoặc không có kết quả dùng được. Nó không khẳng định hồ sơ đã được phê duyệt hoặc transaction sau đó đã commit. Cần metric workflow và audit riêng cho hiệu ứng ấy.

Không áp dụng cách chốt `unavailable` của phép đọc này cho mọi lệnh thanh toán: nếu có thể đã gây hiệu ứng, ngoại lệ có thể cần phân loại `indeterminate` và đưa command vào đối soát.

Lỗi ghi metric nên được xử lý theo hợp đồng của thư viện telemetry để không ghi đè kết quả nghiệp vụ hay bỏ kiểm soát quyền. Việc mất telemetry cần tín hiệu độc lập. Chính sách audit bắt buộc, nếu có, là trách nhiệm khác và không nên bị gộp vào hành vi của exporter metric.

## 10. Dashboard và trình tự điều tra

### 10.1. Tổ chức dashboard theo câu hỏi

Một dashboard hữu ích có thể gồm các nhóm song song:

| Nhóm | Chỉ số cần xem | Câu hỏi hỗ trợ |
|---|---|---|
| Phạm vi và dữ liệu đo | Job, môi trường, vùng, scrape, expected-series | Có đang nhìn đúng nơi và còn thấy dữ liệu không? |
| Tác động nghiệp vụ | Command bị trì hoãn, đối soát tồn đọng, guardrail | Người dùng và bất biến đang chịu ảnh hưởng gì? |
| Khả năng cung cấp kết quả | Lưu lượng operation, usable/unavailable/indeterminate | Có nhận được kết quả đủ dùng không? |
| Nguồn chính | Attempt theo kết quả, timeout, breaker | Nguồn chính lỗi ở bước nào? |
| Chi phí chờ | p95/p99 theo kết quả, inflight, pool và hàng đợi | Có tắc nghẽn hoặc retry khuếch đại không? |
| Chế độ suy giảm | Fallback accepted/rejected, nguồn kết quả, refresh age | Hệ thống đang dựa vào đường nào để tiếp tục? |
| Đúng đắn dữ liệu | Invalid-data theo lý do, dùng policy hết hạn | HTTP thành công có đang che dữ liệu sai không? |

Không gộp mọi dependency và operation thành một tỷ lệ duy nhất. Nhiều phép đọc danh mục khỏe có thể che một lượng nhỏ thao tác thanh toán đang mất kiểm soát. Cũng không lấy trung bình trạng thái one-hot của circuit breaker rồi trình bày nó như xác suất một giao dịch sẽ thành công.

### 10.2. Kết hợp đo tại phía gọi và probe phù hợp

Metric phía gọi thể hiện đường đi thực sự của ứng dụng, gồm DNS, mạng, pool, credential, deadline và validator. Dependency tự báo khỏe chưa chắc phía gọi sử dụng được nó. So sánh hai phía giúp phân biệt nguồn lỗi.

Probe bên ngoài có thể bổ sung kiểm tra một đường đọc an toàn với dữ liệu kiểm thử có kiểm soát. Một probe phân quyền chỉ gọi endpoint liveness thì không chứng minh kiểm tra quyền theo đối tượng đang đúng.

Có thể kiểm tra cả quyết định được phép và bị từ chối trên các tài nguyên kiểm thử đã định nghĩa. Probe cần có nhãn nguồn riêng hoặc đường tổng hợp tách biệt để không làm tăng giả tỷ lệ thành công của lưu lượng thật.

Không tạo thanh toán hoặc quyền lợi thật định kỳ chỉ để lấy một biểu đồ xanh. Với luồng gây hiệu ứng, dùng môi trường hoặc phương thức kiểm chứng được thiết kế cho việc đó, cùng kiểm soát idempotency và dọn dữ liệu phù hợp.

Dependency suy giảm cũng không tự có nghĩa tiến trình ứng dụng cần restart. Gắn mọi lỗi ngoài hệ thống vào liveness có thể tạo vòng restart và xóa cache đang còn hợp lệ. Readiness, chấp nhận tải và phản hồi suy giảm cần được thiết kế theo vai trò của instance và chính sách phục vụ.

### 10.3. Trình tự xử lý một cảnh báo

Ví dụ cảnh báo policy tăng lỗi:

1. Xác định môi trường, vùng, operation và thời điểm; kiểm tra scrape và chuỗi metric dự kiến.
2. Xem tỷ lệ operation không đủ dùng cùng số lượng, inflight và deadline, để biết có lỗi hoàn tất hay request đang mắc lại.
3. So sánh attempt, timeout, breaker, nguồn kết quả và tuổi snapshot. Nếu primary lỗi nhưng cache còn dùng được, xác định thời gian hiệu lực còn lại theo hợp đồng.
4. Xem lỗi dữ liệu như sai tenant, thiếu revision hoặc hết hạn. Những lỗi này có thể cần xử lý bảo mật, không chỉ xử lý mạng.
5. Kiểm tra guardrail và command bị ảnh hưởng qua audit/trace có phân quyền. Chỉ dùng metric để khoanh vùng, không suy ra danh tính giao dịch từ một tỷ lệ tổng hợp.
6. Khôi phục nguồn hoặc áp dụng chế độ suy giảm đã định nghĩa; không chữa cảnh báo bằng cách cho phép mặc định hay kéo dài hiệu lực quyền ngoài chính sách.
7. Sau phục hồi, xác minh dữ liệu mới, backlog đối soát, lượng fallback và kết quả nghiệp vụ. Primary hết lỗi chưa chứng minh các command cũ đã được giải quyết.

Với timeout thanh toán, bước đối soát là trung tâm: giữ command ổn định, kiểm tra nguồn nhà cung cấp theo hợp đồng và chỉ chuyển trạng thái khi đủ bằng chứng. Không “sửa” tỷ lệ lỗi bằng cách ghi nhận thành công trước xác nhận.

## 11. Kiểm thử tính hữu ích và tính an toàn của metric

Bảng dưới mô tả các tiêu chí kiểm thử cho một triển khai thực tế. Các ví dụ trong tài liệu chưa được chạy trên một ứng dụng cụ thể.

| Tình huống | Hành vi nghiệp vụ cần giữ | Tín hiệu cần kiểm tra |
|---|---|---|
| Policy trả DENY hợp lệ | Không cho thay đổi trái quyền | Operation usable; chỉ số từ chối quyền riêng nếu có |
| Policy trả HTTP 200 nhưng sai tenant hoặc đối tượng | Không dùng quyết định | Invalid-data có lý do hữu hạn; không ghi primary usable |
| Phản hồi policy hết hạn | Không coi HTTP 200 là căn cứ cấp quyền | Invalid-data tăng; fallback chỉ được xét theo chính sách |
| Primary timeout, cache đúng scope và còn được phép | Chỉ dùng cache sau xác minh | Attempt timeout; fallback accepted; operation usable/cache |
| Primary timeout, cache hết hạn | Không bỏ kiểm tra hoặc kéo dài hiệu lực tùy ý | Fallback rejected; operation unavailable/none |
| Circuit breaker mở | Không gửi attempt không cần thiết, vẫn giữ kiểm soát | Operation được chốt; breaker open; attempt có thể bằng 0 |
| Hai lần retry rồi thành công | Không làm sai số command | Nhiều attempt, một operation; duration gồm toàn bộ thời gian |
| Request treo hoặc bị hủy | Không chiếm tài nguyên vô hạn | Deadline/cancellation được xử lý; inflight giảm khi kết thúc |
| Thanh toán timeout sau khi có thể đã gửi | Không phát lệnh mới thiếu kiểm soát | Indeterminate; pending reconciliation được lưu bền vững |
| Restart khi còn command chưa rõ kết quả | Không quên các command đó | Gauge pending phục hồi đúng; tuổi chờ không đặt lại |
| Không có lưu lượng thật | Không kết luận khỏe chỉ từ tỷ lệ | Counter 0, trạng thái không có mẫu, probe hoặc tín hiệu khác |
| Exporter/scrape lỗi | Không biến quyết định quyền thành cho phép | Cảnh báo telemetry; không nhầm thiếu dữ liệu với 0 lỗi |
| Một vùng lỗi, các vùng khác khỏe | Không che lỗi cục bộ bằng tổng hợp | Truy vấn theo vùng phát hiện đúng phạm vi |
| Client gửi ID/URL/exception rất đa dạng | Không tạo label vô hạn hoặc rò bí mật | Tập label giữ hữu hạn, dữ liệu chi tiết ở kênh phù hợp |
| Mất bộ lưu idempotency | Không tạo hiệu ứng trùng để tiếp tục phục vụ | Dependency không đủ dùng và tín hiệu tác động workflow |
| Quan sát thấy fallback đã bỏ kiểm tra quyền | Không coi đó là suy giảm availability thông thường | Guardrail và bằng chứng bền vững theo thiết kế |
| Nguồn chính phục hồi | Không mặc định backlog đã hết | Counter mới phục hồi nhưng pending, cache và refresh được kiểm tra riêng |

Kiểm thử instrumentation cần xác minh chính xác điểm tăng counter, chủ sở hữu từng metric, label, deadline và các đường ngoại lệ. Kiểm thử alert cần bao gồm counter reset, numerator vắng, mẫu số 0, target biến mất, thiếu một instance và lưu lượng thấp.

Không chỉ viết một test kiểm tra có gọi hàm `increment`. Mục tiêu là khi hệ thống suy giảm hoặc bị lạm dụng, metric giúp phân biệt được lỗi dependency, hành vi từ chối đúng và vi phạm bất biến.

## 12. Các lỗi thiết kế cần tránh

| Lỗi | Hệ quả |
|---|---|
| Chỉ theo dõi `/health` của dependency | Bỏ sót credential sai, timeout phía gọi hoặc dữ liệu sai nghĩa |
| Coi mọi HTTP 2xx là thành công nghiệp vụ | Chấp nhận policy hết hạn hoặc nhầm tiếp nhận với hiệu ứng hoàn tất |
| Tính DENY hợp lệ thành dependency failure | Tạo động lực nới quyền để làm biểu đồ đẹp |
| Chỉ nhìn kết quả sau retry/fallback | Che nguồn chính suy giảm và chi phí khuếch đại tải |
| Cộng attempt và operation | Làm sai mẫu số và số lần thực hiện nghiệp vụ |
| Thay dữ liệu thiếu bằng 0 ở mọi truy vấn | Làm mất khả năng phân biệt yên lặng, thiếu instrumentation và mất scrape |
| Dùng timestamp refresh toàn cụm để suy mọi cache đều mới | Che instance hoặc entry đang phục vụ dữ liệu cũ |
| Tự động tắt kiểm tra bảo mật khi metric xấu | Biến sự cố dependency thành đường vượt quyền |
| Dùng metric làm sổ giao dịch | Không đủ độ bền và chi tiết để chứng minh từng hiệu ứng |
| Đặt mọi ID nghiệp vụ vào label | Tăng cardinality, chi phí và nguy cơ lộ dữ liệu |

Một bộ dependency health metric có giá trị khi nó giúp người vận hành biết dependency nào đang suy giảm, kết quả nào còn đủ tin cậy, luồng nào bị ảnh hưởng và bất biến nào cần kiểm tra. Bảo vệ cuối cùng vẫn phải nằm trong đường thực thi: quyền theo đối tượng, kiểm tra phiên bản và trạng thái, transaction, idempotency cùng đối soát cho hiệu ứng chưa xác định.
