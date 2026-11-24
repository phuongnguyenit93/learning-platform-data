# Recovery alert thresholds

## 1. Ngưỡng cảnh báo recovery phải dẫn tới hành động nào?

Ngưỡng cảnh báo là điều kiện chuyển một tín hiệu quan sát thành việc cần được xử lý. Với khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, mục tiêu là phát hiện người dùng hợp lệ đang bị cản trở, luồng recovery có dấu hiệu bị lạm dụng hoặc một bất biến an toàn đã bị vi phạm.

Một con số như “trên 100 lỗi mỗi phút” chưa đủ tạo thành quy tắc tốt. Cần biết:

- Lỗi nào được đếm?
- Tổng lượng yêu cầu là bao nhiêu?
- Tín hiệu kéo dài trong bao lâu?
- Bao nhiêu người dùng hoặc bước recovery bị ảnh hưởng?
- Người nhận cảnh báo phải làm gì?
- Dữ liệu đo có đang đầy đủ và đáng tin không?

Ví dụ, nhiều token sai có thể là một chiến dịch dò recovery, trong khi nhiều timeout ở dịch vụ xác minh có thể là sự cố hạ tầng. Hai tình huống cần người xử lý và hành động khác nhau.

Các số liệu, cửa sổ và ngưỡng trong bài là ví dụ giả lập để giải thích cách thiết kế. Chúng không phải cấu hình mặc định áp dụng cho mọi sản phẩm.

## 2. Phân loại tín hiệu trước khi chọn ngưỡng

| Nhóm | Ví dụ | Mục tiêu cảnh báo |
| --- | --- | --- |
| Độ tin cậy vận hành | Timeout, lỗi phụ thuộc, hàng đợi tồn đọng | Khôi phục khả năng phục vụ |
| Trải nghiệm recovery | Chờ quá lâu, tỷ lệ bỏ dở tăng | Tìm điểm gây khó cho người dùng hợp lệ |
| Lạm dụng | Nhiều lần thử mã, yêu cầu dàn trải, gửi thông báo hàng loạt | Điều tra và áp dụng chính sách chống lạm dụng |
| Bất biến an toàn | Có bằng chứng quyền dùng một lần được chấp nhận lặp | Xử lý sự cố an toàn ưu tiên cao |
| Chất lượng quan sát | Thiếu metric, audit chậm, bộ thu thập lỗi | Khôi phục khả năng đánh giá hệ thống |

Không gộp tất cả vào “recovery failed”. Một lần từ chối đúng chính sách là hành vi mong đợi của hệ thống, dù người yêu cầu không đạt mục tiêu.

Ngược lại, tỷ lệ từ chối tăng bất thường vẫn có thể là dấu hiệu chính sách lỗi hoặc công cụ xác minh gặp vấn đề. Cần theo dõi bằng chỉ số riêng, có phân đoạn và ngữ cảnh.

Một sự kiện “thu hồi session đã được yêu cầu” cũng không thay thế tín hiệu “thu hồi đã có hiệu lực theo hợp đồng”. Ngưỡng phải dựa trên đúng trạng thái cần bảo đảm.

## 3. Định nghĩa phép đo và mẫu số

### 3.1. Đơn vị đo phải rõ ràng

Recovery có thể được đo ở cấp request HTTP, lần thử xác minh, thao tác nghiệp vụ hoặc toàn bộ yêu cầu. Các cấp này không thể dùng thay nhau.

```text
HTTP request          = một lần gọi API
verification attempt = một lần thử tại bước xác minh
logical operation    = một thao tác có thể được retry
recovery request     = toàn bộ hồ sơ khôi phục
```

Một logical operation được retry ba lần không nhất thiết là ba người dùng bị lỗi. Nếu đo tải hạ tầng, cả ba lần gọi có thể cần đếm. Nếu đo số thao tác nghiệp vụ thất bại, cần chống đếm lặp theo quy tắc của thao tác.

Định danh phục vụ chống trùng có thể được xử lý nội bộ; không cần đưa mọi operation ID thành nhãn metric.

### 3.2. Tách lỗi kỹ thuật khỏi từ chối hợp lệ

Ví dụ một SLI cho API xử lý quyết định:

```text
technical_error_ratio =
    số lần xử lý không đạt hợp đồng kỹ thuật
    / tổng số lần xử lý thuộc phạm vi SLI
```

Phạm vi và hợp đồng phải được xác định trước. Một quyết định từ chối được trả đúng cách, đúng hạn có thể là xử lý tốt về mặt kỹ thuật.

Nếu timeout khiến kết quả nghiệp vụ chưa rõ, lần xử lý vẫn có thể vi phạm hợp đồng thời gian của API. Điều đó không cho phép ghi kết quả nghiệp vụ là thất bại khi tác động bên ngoài có thể đã xảy ra.

Không loại khỏi mẫu số mọi lần xử lý chưa xác định được tài khoản hoặc bị lỗi khó phân loại chỉ để tỷ lệ đẹp hơn. Với endpoint công khai, có thể cần SLI riêng cho khả năng xử lý phản hồi chung an toàn.

### 3.3. Conversion cần cohort, không chia hai bộ đếm tùy ý

Công thức sau dễ gây hiểu nhầm:

```text
số recovery hoàn tất trong 5 phút
/ số recovery bắt đầu trong cùng 5 phút
```

Những yêu cầu vừa hoàn tất có thể bắt đầu từ trước, còn yêu cầu mới có thể cần chờ phê duyệt lâu hơn. Tỷ lệ trên không phải conversion của cùng một nhóm.

Để phân tích hoàn tất, theo dõi cohort theo thời điểm bắt đầu, loại recovery và thời gian đã đủ để quan sát. Tách các yêu cầu còn đang chờ hợp lệ khỏi yêu cầu đã quá hạn dự kiến.

Không dùng conversion làm chỉ số duy nhất cho độ tin cậy. Một đợt bot tạo nhiều yêu cầu giả có thể làm conversion giảm mạnh dù người dùng hợp lệ vẫn được phục vụ bình thường.

## 4. Kết hợp tỷ lệ, số lượng và mức tác động

Giả sử hai khu vực có số liệu:

| Khu vực | Số xử lý được đo | Lỗi kỹ thuật | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A | 10.000 | 200 | 2% |
| B | 2 | 1 | 50% |

Khu vực B có tỷ lệ cao nhưng rất ít mẫu. Khu vực A có tỷ lệ thấp hơn nhưng ảnh hưởng nhiều thao tác.

Một quy tắc vận hành thường cần kết hợp:

- Tỷ lệ lỗi vượt ngưỡng.
- Số mẫu tối thiểu để diễn giải tỷ lệ.
- Số tác động tuyệt đối hoặc thời gian chờ.
- Phạm vi ảnh hưởng và mức nghiêm trọng.

Ngưỡng mẫu tối thiểu giúp giảm cảnh báo tỷ lệ do một vài mẫu, nhưng có thể làm bỏ sót sự cố ở luồng ít lưu lượng. Cần tín hiệu bổ sung như kiểm tra khả dụng được kiểm soát, tuổi công việc quá hạn hoặc lỗi phụ thuộc kéo dài.

Không áp dụng yêu cầu “phải đủ nhiều mẫu” cho mọi bất biến an toàn. Một vi phạm đã được xác nhận có thể cần xử lý ngay, dù chỉ xảy ra một lần.

### Không lấy trung bình các tỷ lệ tùy ý

Tỷ lệ lỗi toàn hệ thống cần lấy tổng số lỗi chia tổng số xử lý tương ứng. Trung bình 2% và 50% không phản ánh đúng dữ liệu trong bảng.

Tuy nhiên, tỷ lệ toàn hệ thống cũng có thể che một khu vực nhỏ bị gián đoạn hoàn toàn. Cần cả góc nhìn tổng thể và phân đoạn có ý nghĩa.

## 5. Chọn cửa sổ theo tốc độ thay đổi

Cửa sổ ngắn phát hiện nhanh nhưng dễ bị dao động. Cửa sổ dài ổn định hơn nhưng phản ứng chậm.

Một cách tổ chức:

| Cửa sổ | Vai trò |
| --- | --- |
| Ngắn | Xác định vấn đề còn đang diễn ra |
| Dài hơn | Xác định vấn đề có đủ mức kéo dài hoặc tích lũy |
| Lịch sử nền | So sánh theo giờ, ngày hoặc chu kỳ vận hành |

Ví dụ giả lập: cảnh báo khi tỷ lệ lỗi kỹ thuật vượt 5% trong cả cửa sổ 5 phút và 30 phút, đồng thời mỗi cửa sổ có đủ mẫu theo cấu hình.

Điều kiện kép giúp tránh một đỉnh ngắn đã hết hoặc một trung bình dài còn cao sau khi hệ thống phục hồi. Nó cũng có thể làm chậm phát hiện một sự cố mới; vì vậy cần nhánh phát hiện nhanh riêng khi tác động rất lớn.

Không chọn cửa sổ theo thói quen. Thời gian người dùng chịu được, độ trễ thu thập metric và tốc độ tăng tác động phải quyết định cửa sổ phù hợp.

Với bước phê duyệt thủ công có thời gian chờ chủ đích, không cảnh báo chỉ vì yêu cầu chưa hoàn tất trong vài phút. Đo mức quá hạn so với thời điểm bước đó thực sự phải được xử lý.

## 6. Dùng error budget để liên hệ với mục tiêu dịch vụ

Giả sử một SLO minh họa cho phép 99,5% lần xử lý thuộc phạm vi đáp ứng hợp đồng trong kỳ đo.

```text
allowed_bad_ratio = 1 - 0,995 = 0,005

burn_rate =
    observed_bad_ratio
    / allowed_bad_ratio
```

Nếu tỷ lệ xấu quan sát là 5%:

```text
burn_rate = 0,05 / 0,005 = 10
```

Hệ thống đang tiêu thụ phần ngân sách lỗi theo mỗi đơn vị lưu lượng ở tốc độ gấp 10 lần mức trung bình cho phép.

Không diễn giải con số này thành thời gian cạn ngân sách chính xác khi chưa biết phần ngân sách còn lại và lưu lượng tương lai. Nếu lưu lượng thay đổi, tốc độ tiêu thụ theo thời gian cũng thay đổi.

Có thể xây hai nhánh:

- Nhánh nhanh cho mức tiêu thụ rất cao và tác động đang tiếp diễn.
- Nhánh chậm cho suy giảm nhỏ hơn nhưng kéo dài.

SLO về độ tin cậy không cấp phép vi phạm bất biến an toàn. Không chấp nhận dùng lại token hoặc bỏ kiểm tra rủi ro chỉ vì hệ thống vẫn còn error budget.

## 7. Ngưỡng cho độ trễ và công việc tồn đọng

### 7.1. Percentile cần đủ dữ liệu và đúng phạm vi

P95 hoặc p99 có thể giúp nhận biết đuôi độ trễ, nhưng phải biết phép đo bắt đầu và kết thúc tại đâu.

Ví dụ:

```text
challenge_issue_latency =
    thời gian từ lúc tiếp nhận yêu cầu đủ điều kiện
    tới lúc challenge được lưu bền vững theo hợp đồng
```

Chỉ số này không đồng nghĩa thời gian người dùng nhận được email.

Không lấy trung bình p95 của nhiều instance để gọi là p95 toàn hệ thống. Nếu cần percentile tổng hợp, dùng dữ liệu phân phối có khả năng tổng hợp và cấu hình ranh giới phù hợp.

Khi ít mẫu, quan sát thêm số lần vượt mốc độ trễ, timeout và tác động thực tế. Một percentile đơn lẻ không đủ giải thích mọi trường hợp.

### 7.2. Đo tuổi quá hạn thay vì tuổi tồn tại

Một yêu cầu đang chờ thời gian bảo vệ theo chính sách không phải backlog lỗi. Một công việc đã đến hạn nhưng chưa được xử lý mới là tín hiệu cần xem xét.

```text
overdue_age = max(0, now - expected_processing_due_at)
```

Có thể theo dõi số công việc quá hạn, tuổi quá hạn lớn nhất và tốc độ xử lý so với tốc độ đến.

Đừng chỉ đo độ dài hàng đợi. Một hàng đợi ngắn vẫn có thể chứa một tác động an toàn quan trọng bị kẹt lâu, chẳng hạn thu hồi quyền recovery tạm.

Với tác động bắt buộc trước hoàn tất, trạng thái chưa xác nhận quá lâu cần cảnh báo theo hợp đồng của tác động đó, không đợi tỷ lệ thành công toàn module giảm rõ rệt.

## 8. Ngưỡng cho lạm dụng recovery

Lưu lượng thất bại tăng có thể đến từ bot, lỗi nhập của người dùng, thay đổi giao diện hoặc lỗi dịch vụ phụ thuộc. Một tín hiệu đơn lẻ thường chỉ đủ tạo nghi vấn.

Có thể kết hợp:

| Tín hiệu | Ngữ cảnh cần bổ sung |
| --- | --- |
| Nhiều yêu cầu khôi phục | Tài khoản, tenant, nguồn phát sinh và mức phân tán |
| Nhiều mã xác minh không được chấp nhận | Loại challenge, số lần thử hợp lệ và tuổi challenge |
| Nhiều tài khoản bị nhắm tới | Quan hệ nguồn, thiết bị và chiến dịch |
| Nhiều lần gửi lại challenge | Số lần gửi thực sự, kênh nhận và giới hạn áp dụng |
| Tỷ lệ từ chối rủi ro tăng | Phiên bản chính sách, cohort và tác động tới người dùng hợp lệ |
| Thay đổi credential sau recovery bất thường | Chuỗi xác minh, phê duyệt và kết quả có thẩm quyền |

Không coi mọi request từ cùng IP là cùng một người. Mạng dùng chung có thể tạo lưu lượng cao hợp lệ, còn một chiến dịch có thể phân tán trên nhiều nguồn.

Các bộ đếm theo tài khoản có thể nằm trong hệ thống phát hiện hoặc chống lạm dụng được bảo vệ. Không nhất thiết xuất mọi tài khoản thành nhãn trong kho metric chung.

Cảnh báo lạm dụng và cơ chế rate limit có vai trò khác nhau. Rate limit có thể thực thi tự động theo chính sách; cảnh báo giúp phát hiện mẫu vượt qua giới hạn cục bộ hoặc tác động không mong muốn.

Một ngưỡng cảnh báo bị vượt không tự cho phép tắt MFA, bỏ thời gian chờ hoặc cấp thêm quyền recovery. Hành động tự động phải là một phần chính sách được thiết kế riêng.

## 9. Ngưỡng cho bất biến an toàn

Có những điều không nên chờ đạt một tỷ lệ lớn mới xử lý:

- Có bằng chứng một quyền dùng một lần tạo ra nhiều tác động được chấp nhận trái chính sách.
- Một tác động recovery được xác nhận vượt ranh giới tenant hoặc chủ thể.
- Credential bị thay đổi dù điều kiện phê duyệt bắt buộc chưa đạt.
- Recovery được đánh dấu hoàn tất trong khi tác động an toàn bắt buộc được xác nhận là chưa đáp ứng.
- Secret xác thực xuất hiện trong kênh quan sát không được phép.

Cần phân biệt sự kiện nghi vấn và vi phạm đã được xác nhận.

Hai HTTP response thành công cho cùng operation ID có thể là retry trả lại kết quả cũ. Hai lần kiểm tra token hợp lệ cũng chưa chứng minh token đã tạo hai tác động. Nguồn phát hiện phải đối chiếu chuyển trạng thái và tác động có thẩm quyền.

Một quy tắc khái niệm:

```text
Nếu có ít nhất một vi phạm mới đã được xác nhận,
tạo cảnh báo an toàn với tham chiếu bằng chứng đã giảm dữ liệu.
```

Cơ chế nhận sự kiện cần chống đếm lặp. Không tạo hàng trăm cảnh báo chỉ vì cùng một sự kiện được vận chuyển lại.

Nếu mới có nghi vấn do dữ liệu chưa đầy đủ, cảnh báo phải ghi mức chắc chắn và hướng đối soát. Không ghi “chiếm đoạt tài khoản đã xảy ra” chỉ từ một chênh lệch timestamp.

Việc chưa có sự kiện vi phạm cũng không chứng minh hệ thống an toàn nếu nguồn phát hiện đang không hoạt động. Vì vậy, chất lượng quan sát cần ngưỡng riêng.

## 10. Ngưỡng cho sức khỏe telemetry

Thiếu dữ liệu không đồng nghĩa giá trị bằng 0.

```text
error_count = 0 với nguồn đang hoạt động
```

khác với:

```text
không nhận được error_count vì bộ thu thập đã dừng
```

Theo dõi những tín hiệu như:

- Tuổi mẫu metric mới nhất.
- Tình trạng bộ thu thập hoặc đường xuất metric.
- Độ trễ từ sự kiện tại nguồn tới kho audit.
- Tồn đọng outbox và sự kiện chuyển tiếp thất bại.
- Chênh lệch giữa số sự kiện nguồn và số được tiếp nhận khi có cơ chế đối soát phù hợp.

Một luồng ít hoạt động có thể không tạo business event trong thời gian dài. Không dùng “không có recovery mới” làm bằng chứng telemetry hỏng. Cần tín hiệu sức khỏe độc lập hoặc cơ chế phân biệt không có lưu lượng với không có dữ liệu.

Nếu cảnh báo đang firing rồi metric biến mất, không tự coi là đã phục hồi. Chuyển sang trạng thái thiếu dữ liệu hoặc tạo cảnh báo sức khỏe theo chính sách.

Thiếu dữ liệu là một bất định cần được ghi rõ, đặc biệt khi đang đánh giá hiệu lực thu hồi hoặc phát hiện dùng lại quyền recovery.

## 11. Phân đoạn và giới hạn cardinality

Ngưỡng tổng thể dễ che vấn đề ở một khu vực, một nhà cung cấp hoặc một loại recovery.

Các chiều phân đoạn hữu ích có thể gồm:

```text
environment
region
recovery_type
step
dependency_class
provider
outcome_category
```

Tập giá trị phải được kiểm soát. Không dùng token, email, số điện thoại, recovery ID, session ID hoặc thông báo lỗi tự do làm nhãn metric.

Với tenant, cân nhắc chi phí và quyền truy cập. Có thể dùng nhóm dịch vụ hoặc tập tenant được quản lý rõ ràng trong hệ thống phù hợp, thay vì tự động sinh không giới hạn chuỗi thời gian cho mọi ID.

Một metric phân đoạn chỉ có ý nghĩa nếu mẫu số tương ứng thuộc cùng phân đoạn. Không chia lỗi của một provider cho tổng yêu cầu của mọi provider rồi diễn giải là tỷ lệ lỗi của provider đó.

Giữ một góc nhìn tổng và các lát cắt quan trọng. Không chỉ nhìn trung bình toàn hệ thống, cũng không tạo một cảnh báo riêng cho mọi tổ hợp nhãn có thể có.

## 12. Ví dụ một quy tắc cảnh báo vận hành

Ví dụ sau là cấu hình khái niệm, không phải cú pháp của một sản phẩm giám sát cụ thể:

```yaml
rule: recovery_step_technical_errors
signal_scope:
  unit: measured_step_execution
  excludes:
    - expected_policy_denial
    - expected_invalid_challenge_rejection

fire_when:
  short_window:
    duration: 5m
    minimum_samples: 30
    technical_error_ratio_at_least: 0.05
  long_window:
    duration: 30m
    minimum_samples: 200
    technical_error_ratio_at_least: 0.05
  combine_windows: AND
  condition_persists_for: 2m

clear_when:
  both_window_error_ratios_below: 0.02
  valid_observation_persists_for: 5m
  telemetry_required: true

routing:
  owner: recovery_service_oncall
  group_by:
    - environment
    - region
    - step
  runbook: recovery_step_dependency_degradation
```

Phần loại trừ chỉ áp dụng khi những kết quả đó đã được xác định đúng theo hợp đồng đo. Không gắn mọi lỗi chưa rõ nguyên nhân thành “policy denial” để giảm cảnh báo.

Giả sử số liệu cùng một bước:

| Cửa sổ | Tổng mẫu | Lỗi kỹ thuật | Tỷ lệ |
| --- | ---: | ---: | ---: |
| 5 phút | 100 | 8 | 8% |
| 30 phút | 1.000 | 60 | 6% |

Cả hai cửa sổ vượt ngưỡng và đủ mẫu. Nếu điều kiện tiếp tục trong thời gian giữ đã cấu hình, quy tắc chuyển sang firing.

Với SLO giả lập 99,5% ở phần trước, burn rate tương ứng là 16 và 12. Tuy nhiên, mức độ ưu tiên cuối cùng còn phụ thuộc tác động và cách đội vận hành dùng SLO.

Nếu chỉ có hai mẫu và một lỗi, quy tắc tỷ lệ này chưa đủ điều kiện. Nhánh lưu lượng thấp, kiểm tra khả dụng hoặc tín hiệu công việc quá hạn phải bổ sung khả năng phát hiện.

Nếu một sự cố mới làm cửa sổ ngắn tăng mạnh nhưng cửa sổ dài chưa vượt ngưỡng, quy tắc kép có thể chưa firing. Đó là lý do cần thiết kế nhánh phát hiện nhanh phù hợp, thay vì cho rằng một quy tắc duy nhất bao phủ mọi tình huống.

Điều kiện clear có ngưỡng thấp hơn fire để giảm dao động. Với cửa sổ dài 30 phút, việc clear có thể chậm hơn thời điểm lỗi thực tế dừng; cần chấp nhận hoặc điều chỉnh độ trễ này một cách có chủ đích.

Nếu lưu lượng dừng hoặc dữ liệu thiếu, phải xử lý theo trạng thái quan sát thực tế. Không chia cho 0, không xem tỷ lệ thiếu là 0% và không tự xác nhận phục hồi.

## 13. Mức độ cảnh báo, gom nhóm và chống nhiễu

Ngưỡng số học và mức độ ưu tiên là hai phần khác nhau.

| Mức tác động | Cách xử lý có thể phù hợp |
| --- | --- |
| Bất biến an toàn đã được xác nhận vi phạm | Chuyển ngay tới vai trò xử lý sự cố an toàn |
| Gián đoạn rộng hoặc tiêu thụ ngân sách lỗi rất nhanh | Đánh thức đội trực chịu trách nhiệm |
| Suy giảm kéo dài nhưng tác động thấp hơn | Tạo công việc xử lý theo mức khẩn cấp đã định |
| Thay đổi xu hướng chưa có tác động rõ | Theo dõi hoặc đưa vào phân tích định kỳ |

Tên mức cụ thể và đường nhận do tổ chức quy định. Điều cần tránh là mọi tín hiệu đều trở thành một cảnh báo khẩn cấp.

Gom các cảnh báo cùng sự cố theo những chiều ổn định, chẳng hạn môi trường, khu vực, bước và phụ thuộc. Giữ thông tin tác động để người xử lý biết những luồng nào liên quan.

Cooldown hoặc deduplication chỉ điều khiển việc gửi thông báo. Chúng không được xóa dữ liệu mới hoặc ngăn một mức tác động cao hơn được nâng cấp.

Khi một dependency chung bị lỗi, có thể gom hoặc giảm thông báo triệu chứng để tránh hàng loạt page. Tuy nhiên, không che một vi phạm an toàn độc lập chỉ vì đang có sự cố hạ tầng.

Hysteresis, thời gian giữ và điều kiện phục hồi giúp giảm flapping. Không giải quyết nhiễu bằng cách tăng mọi ngưỡng cho tới khi không còn cảnh báo.

## 14. Mỗi cảnh báo cần đủ ngữ cảnh để xử lý

Một thông báo cảnh báo nên có:

- Điều kiện nào đang vượt và trong cửa sổ nào.
- Giá trị hiện tại, mẫu số và mức tác động đã biết.
- Phân đoạn bị ảnh hưởng và thời điểm bắt đầu quan sát.
- Độ mới của dữ liệu, phần thiếu hoặc mức chắc chắn.
- Dashboard, tham chiếu sự kiện đã giảm dữ liệu và runbook phù hợp.
- Chủ sở hữu và hành động đầu tiên cần thực hiện.

Ví dụ thông báo giả lập:

```text
Recovery: lỗi kỹ thuật tăng tại bước xác minh MFA, khu vực R1.

5 phút: 8/100 lần xử lý, 8%.
30 phút: 60/1.000 lần xử lý, 6%.
Dữ liệu quan sát còn mới.
Từ chối challenge hợp lệ không nằm trong bộ đếm lỗi kỹ thuật.

Hành động đầu tiên:
đối chiếu sức khỏe phụ thuộc xác minh và các thay đổi triển khai gần đây.
Giữ nguyên điều kiện xác minh và chính sách recovery.
```

Runbook cần hướng dẫn kiểm tra nguồn đo, phạm vi tác động và dependency, rồi mới chọn biện pháp khắc phục được cấp quyền.

Không đưa token, địa chỉ email đầy đủ hoặc bằng chứng định danh vào thông báo gửi tới kênh vận hành rộng. Tham chiếu điều tra cũng phải có kiểm soát truy cập.

Không tự động đổi chính sách xác minh chỉ vì tỷ lệ thành công giảm. Một đợt từ chối tăng có thể chứng minh kiểm soát đang ngăn lạm dụng đúng cách.

## 15. Hiệu chỉnh ngưỡng bằng dữ liệu lịch sử

Chọn ngưỡng cần dựa trên phân phối dữ liệu, loại sự cố muốn phát hiện và chi phí báo nhầm hoặc bỏ sót.

Một quá trình hiệu chỉnh có thể gồm:

1. Xác định sự cố và hành động mà quy tắc cần hỗ trợ.
2. Xem dữ liệu qua các chu kỳ lưu lượng, ngày thấp điểm và đợt tăng tải.
3. Đối chiếu các khoảng sự cố đã biết với thời điểm quy tắc sẽ phát hiện.
4. Xem các lần vượt ngưỡng nhưng không có tác động cần xử lý.
5. Điều chỉnh cửa sổ, phân đoạn, mẫu tối thiểu và điều kiện phục hồi.
6. Theo dõi quy tắc ở chế độ quan sát có chủ sở hữu trước khi dùng để đánh thức đội trực.
7. Ghi phiên bản, lý do thay đổi và thời điểm áp dụng.

Ngưỡng thích nghi theo baseline có thể hữu ích với lưu lượng theo mùa. Nhưng baseline có thể bị nhiễm bởi một chiến dịch lạm dụng kéo dài hoặc một sự cố chưa được đánh dấu.

Không để hệ thống tự học rằng nhiều lần dùng sai token hoặc chậm thu hồi là “bình thường mới”. Các bất biến an toàn và giới hạn cứng phải được quản lý riêng.

Sau một thay đổi luồng recovery, chính sách hoặc provider, cần xem lại ý nghĩa phép đo. Không kết luận ngưỡng cũ vẫn phù hợp chỉ vì tên metric không đổi.

## 16. Các tình huống cần phân biệt

| Tình huống | Diễn giải và hướng quan sát |
| --- | --- |
| Token sai tăng, lỗi kỹ thuật không tăng | Xem tín hiệu lạm dụng; không mặc định dịch vụ hỏng |
| Timeout tăng ở một provider | Kiểm tra phụ thuộc và tác động theo đúng phân đoạn |
| Từ chối tăng sau đổi chính sách | Đối chiếu cohort và phiên bản, không trộn với timeout |
| Chỉ một vài yêu cầu trong ngày | Không dựa riêng vào tỷ lệ; bổ sung độ trễ quá hạn và khả dụng |
| Audit không nhận sự kiện mới | Kiểm tra sức khỏe đường vận chuyển trước khi kết luận không có hoạt động |
| Nhiều response thành công cho cùng operation | Đối chiếu idempotency và tác động commit trước khi báo dùng lặp |
| Session revocation được yêu cầu nhưng quá hạn xác nhận | Cảnh báo tác động đang chờ theo hợp đồng, không ghi đã thu hồi |
| Cảnh báo vừa hạ rồi tăng liên tục | Xem lại hysteresis, cửa sổ và điều kiện clear |

Một hệ thống cảnh báo tốt không phải hệ thống có nhiều quy tắc hoặc nhiều page. Nó phải phát hiện được tác động cần xử lý, diễn giải đúng dữ liệu và dẫn tới hành động bảo vệ khả năng khôi phục tài khoản mà vẫn giữ các điều kiện an toàn.
