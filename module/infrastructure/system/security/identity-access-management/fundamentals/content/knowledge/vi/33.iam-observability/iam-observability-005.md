# Authorization denial rate

## 1. Tỷ lệ từ chối cấp quyền cho biết điều gì?

**Authorization denial rate** là tỷ lệ quyết định từ chối trên tổng số quyết định cấp quyền hợp lệ trong một phạm vi và khoảng thời gian xác định. Chỉ số này giúp đội vận hành IAM quan sát cách các chính sách quyền tác động đến hoạt động thực tế: ai đang không thực hiện được hành động mong muốn, phần nào của hệ thống xuất hiện nhiều yêu cầu vượt quyền, và thay đổi chính sách có tạo ra gián đoạn hay không.

Một người dùng đã đăng nhập bằng MFA vẫn có thể bị từ chối khi sửa hóa đơn của bộ phận khác. Một workload có danh tính hợp lệ vẫn có thể bị từ chối khi đọc secret ngoài namespace được cấp. Đây là kết quả của **authorization**, không tự động có nghĩa là xác thực thất bại hoặc hệ thống IAM bị lỗi.

Tỷ lệ từ chối cũng không phải thước đo càng thấp càng tốt. Chính sách ít quyền nhất cần chặn những yêu cầu không được phép. Một đợt dò quét bị chặn có thể làm tỷ lệ tăng trong khi cơ chế bảo vệ hoạt động đúng. Ngược lại, tỷ lệ giảm đột ngột có thể xuất phát từ việc vô tình cấp quyền quá rộng, bỏ qua điểm kiểm tra quyền hoặc mất dữ liệu giám sát.

Mục tiêu khi theo dõi chỉ số là **giải thích được biến động và tác động**, không phải giảm mọi quyết định từ chối bằng cách nới quyền.

## 2. Định nghĩa công thức và phạm vi đo

Trong cửa sổ thời gian `W`, đặt:

- `A(W)`: số quyết định cuối cùng cho phép, ký hiệu `allow`.
- `D(W)`: số quyết định cuối cùng từ chối theo chính sách, ký hiệu `deny`.
- `E(W)`: số lần đánh giá gặp lỗi kỹ thuật, ký hiệu `error`.
- `I(W)`: số lần đánh giá không xác định được quyết định theo hợp đồng của hệ thống, ký hiệu `indeterminate`.

Trong bài này, tỷ lệ từ chối cấp quyền được định nghĩa là:

```text
authorization_denial_rate(W) = D(W) / [A(W) + D(W)]

authorization_denial_percent(W) = authorization_denial_rate(W) × 100%
```

Mẫu số gồm các quyết định `allow` và `deny` hợp lệ. `error` và `indeterminate` được theo dõi bằng chỉ số riêng để tránh gộp lỗi vận hành với kết quả chính sách. Một hệ thống có thể chọn định nghĩa khác, nhưng tên chỉ số, tài liệu và dashboard phải công bố rõ mẫu số; không so sánh hai tỷ lệ có hợp đồng đo khác nhau.

Ví dụ, trong 5 phút tại điểm kiểm tra quyền của dịch vụ hóa đơn:

| Kết quả | Số lượng |
| --- | ---: |
| `allow` | 9.600 |
| `deny` | 400 |
| `error` | 50 |
| `indeterminate` | 50 |

Tỷ lệ từ chối theo định nghĩa trên là `400 / 10.000 = 4%`. Tỷ lệ đánh giá lỗi hoặc không xác định là `100 / 10.100 ≈ 0,99%` nếu mẫu số của chỉ số thứ hai gồm cả bốn nhóm.

Nếu cả 100 kết quả lỗi/không xác định đều bị chặn theo cơ chế fail closed, số lần thực thi bị chặn là 500. Tỷ lệ bị chặn khi thực thi khi đó là `500 / 10.100 ≈ 4,95%`. Con số này trả lời câu hỏi khác với tỷ lệ `deny` theo chính sách.

Khi `A(W) + D(W) = 0`, tỷ lệ từ chối là **không xác định**, không phải 0%. Dashboard cần thể hiện không có quyết định hợp lệ, đồng thời kiểm tra lưu lượng và độ đầy đủ của telemetry.

### 2.1. Phân biệt các loại thất bại

| Tình huống | Nhóm quan sát phù hợp | Có tính vào `D` trong bài này? |
| --- | --- | --- |
| Token hết hạn, yêu cầu dừng trước bước kiểm tra quyền | Lỗi xác thực/token | Không |
| Người dùng đã xác thực nhưng thiếu quyền `invoice.approve` | Từ chối theo chính sách | Có |
| Thuộc tính phòng ban hợp lệ không thỏa điều kiện ABAC | Từ chối theo chính sách | Có |
| Không có grant phù hợp và quy tắc mặc định của chính sách là deny | Từ chối theo chính sách | Có |
| PDP timeout, PEP chặn yêu cầu theo fail closed | Lỗi đánh giá và kết quả thực thi bị chặn | Không; ghi `error` cùng thông tin fail closed |
| Thiếu thuộc tính bắt buộc | Phụ thuộc hợp đồng đánh giá | Chỉ có nếu chính sách định nghĩa đây là một `deny` hợp lệ |
| WAF chặn mẫu tấn công trước khi vào luồng IAM | Chỉ số bảo vệ biên | Không, trừ khi phạm vi đo đã quy định rõ bao gồm lớp này |

`PDP` là nơi đưa ra quyết định chính sách; `PEP` là nơi thực thi quyết định. Cần thống nhất cách ánh xạ kết quả của engine chính sách vào các nhóm quan sát. Chẳng hạn, cùng một tình huống thiếu thuộc tính có thể được engine này biểu diễn là `deny`, engine khác biểu diễn là `indeterminate`. Không tự phân loại lại chỉ để làm đẹp tỷ lệ.

Mã HTTP là tín hiệu hỗ trợ, không thay thế hợp đồng trên. `401` thường liên quan xác thực và `403` thường liên quan từ chối truy cập, nhưng ứng dụng có thể dùng `404` để che giấu sự tồn tại của tài nguyên hoặc dùng `403` cho một giới hạn nghiệp vụ. Đếm mọi `403` thành authorization deny sẽ làm sai chỉ số nếu chưa xác minh nguồn phát sinh.

## 3. Chọn đơn vị đếm trước khi tạo dashboard

### 3.1. Một quyết định không nhất thiết là một API request

Một API có thể kiểm tra quyền ở gateway, ở service và trên từng đối tượng dữ liệu. Một yêu cầu đọc danh sách 100 hóa đơn có thể tạo nhiều quyết định quyền ở mức đối tượng. Vì vậy:

```text
Tỷ lệ quyết định bị từ chối ≠ tỷ lệ API request bị từ chối
```

Nếu muốn đo trải nghiệm của người gọi, cần thêm chỉ số ở mức request: số request cuối cùng bị chặn vì authorization chia cho số request thuộc phạm vi có kiểm tra authorization. Chỉ số này phải có quy tắc riêng cho phản hồi một phần, xử lý hàng loạt và nhiều lần kiểm tra trong cùng request.

Trong phần còn lại, đơn vị đếm là **một quyết định cuối cùng tại một điểm thực thi quyền xác định**. Một request có hai phép kiểm tra quyền thực sự khác nhau được tính thành hai quyết định nếu chúng đều thuộc phạm vi quan sát.

### 3.2. Không cộng trùng các bản ghi của cùng một quyết định

PDP có thể ghi log khi tính toán, PEP ghi log khi thực thi, gateway ghi access log và ứng dụng ghi audit log. Bốn bản ghi không có nghĩa là bốn quyết định độc lập.

Nên chọn nguồn đếm chính, chẳng hạn metric tại PEP sau khi đã xác định kết quả cuối cùng. PDP vẫn có metric riêng cho tải đánh giá và độ trễ, nhưng không cộng trực tiếp metric PDP với metric PEP để tính tỷ lệ chung.

```text
Request
  → PEP yêu cầu đánh giá quyền
  → PDP xử lý, có thể retry nội bộ
  → PEP nhận hoặc xác lập kết quả cuối cùng
  → tăng counter một lần cho phép kiểm tra quyền đó
  → cho phép hoặc chặn thao tác
```

Retry kỹ thuật bên trong một lần đánh giá không làm tăng counter quyết định cuối cùng nhiều lần. Nếu client gửi lại request và hệ thống thực hiện một lần kiểm tra mới, đó có thể là một quyết định mới theo đơn vị đếm đã chọn. Khi cần đo tác động lên thao tác nghiệp vụ duy nhất, phải xây thêm phép đo có quy tắc chống trùng ở mức nghiệp vụ.

`decision_id` có thể hỗ trợ liên kết hoặc chống trùng sự kiện. Không dùng nó làm nhãn metric. Nếu tổng hợp từ event stream có khả năng giao lại sự kiện, pipeline cần chống trùng theo định danh và quy tắc lưu giữ phù hợp.

### 3.3. Cache cũng cần giữ nguyên ý nghĩa đo

Nếu PEP dùng quyết định từ cache, vẫn tính kết quả cuối cùng được thực thi cho phép kiểm tra đó. Chỉ đếm cache miss sẽ khiến tỷ lệ thay đổi theo hit rate, dù trải nghiệm thực tế không đổi.

Có thể phân biệt nguồn quyết định trong dữ liệu chẩn đoán để kiểm tra cache và khả năng thu hồi quyền. Tuy nhiên, cache hit không được tự động hiểu là một lần PDP vừa đánh giá lại chính sách mới.

## 4. Thiết kế telemetry đủ để giải thích biến động

### 4.1. Metric tổng hợp dùng tập nhãn hữu hạn

Một counter minh họa:

```text
iam_authorization_decisions_total{
  environment="production",
  service="invoice-api",
  enforcement_point="service",
  action_group="invoice_write",
  result="deny"
}
```

Các giá trị của `result` trong hợp đồng này là `allow`, `deny`, `error`, `indeterminate`. Counter tăng theo số quyết định cuối cùng, không đặt lại về 0 sau mỗi chu kỳ thu thập; công cụ giám sát tính chênh lệch theo thời gian và xử lý counter reset khi tiến trình khởi động lại.

Những chiều thường có ích là môi trường, dịch vụ, điểm thực thi và nhóm hành động. Có thể bổ sung loại danh tính như người dùng/workload khi đã đánh giá chi phí chuỗi thời gian. Mỗi nhãn cần có tập giá trị hữu hạn, được kiểm soát.

Không đặt user ID, token, email, `request_id`, `decision_id`, resource ID hoặc đường dẫn URL chứa ID động vào nhãn. Các giá trị đó tạo số lượng chuỗi thời gian rất lớn và có thể làm lộ dữ liệu. `tenant_id` cũng không nên mặc định trở thành nhãn toàn hệ thống; khi cần phân tích theo tenant, dùng hệ thống log có phân quyền hoặc một cơ chế tổng hợp đã giới hạn số lượng và phạm vi truy cập.

Phiên bản chính sách và nguyên nhân chi tiết thường phù hợp với event/log hơn. Nếu đưa vào metric, phải kiểm soát số giá trị, vòng đời và khả năng kết hợp với các nhãn khác. Chỉ một tập nhãn nhỏ ở từng chiều cũng có thể tạo nhiều chuỗi khi nhân với nhau.

### 4.2. Sự kiện chẩn đoán giữ ngữ cảnh của một quyết định

Một sự kiện minh họa, dùng định danh giả:

```json
{
  "event_type": "authorization_decision",
  "timestamp": "2026-01-15T08:30:00Z",
  "environment": "production",
  "service": "invoice-api",
  "enforcement_point": "service",
  "decision_id": "dec-example-017",
  "trace_id": "trace-example-912",
  "subject_ref": "subj-pseudo-42",
  "subject_type": "human",
  "action": "invoice.approve",
  "resource_type": "invoice",
  "result": "deny",
  "reason_class": "missing_permission",
  "policy_version": "invoice-policy-v17",
  "decision_source": "pdp",
  "enforcement_outcome": "blocked",
  "evaluation_duration_ms": 7
}
```

`reason_class` nên thuộc danh mục ổn định như `missing_permission`, `attribute_mismatch`, `explicit_deny`, `default_deny`, `dependency_timeout`. Danh mục thực tế phải phù hợp với hệ thống. Tránh ghi nguyên văn biểu thức chính sách, token, cookie, secret hoặc toàn bộ hồ sơ thuộc tính chỉ để giải thích một lần từ chối.

Định danh giả vẫn có thể liên kết tới một người hoặc workload, vì vậy cần phân quyền truy cập, thời hạn lưu giữ và kiểm soát truy vấn. Nội dung trả về cho client cũng không nhất thiết phải tiết lộ chi tiết giống log nội bộ.

### 4.3. Đo cả độ đầy đủ của dữ liệu

Một tỷ lệ đẹp từ pipeline bị mất sự kiện không phản ánh đúng tình trạng hệ thống. Cần quan sát thêm lỗi xuất telemetry, số sự kiện bị loại, độ trễ pipeline và tình trạng thu thập metric.

Metric tổng hợp và log có thể có mức độ lấy mẫu khác nhau. Nếu giữ tất cả log deny nhưng chỉ giữ một phần log allow, không được tính tỷ lệ bằng số log thô đã lưu. Sử dụng counter đầy đủ là lựa chọn dễ giải thích hơn; nếu phải ước lượng từ mẫu thì cần biết xác suất lấy mẫu, trọng số và giới hạn sai số.

## 5. Ví dụ tính bằng PromQL

Các truy vấn dưới đây giả định counter được phát tại nguồn đếm đã chọn và có các nhãn nêu trên. Mỗi phép tổng hợp giữ cùng tập nhãn ở tử và mẫu.

### 5.1. Tỷ lệ từ chối theo dịch vụ trong 5 phút

```promql
100 *
sum by (service, environment) (
  rate(iam_authorization_decisions_total{result="deny"}[5m])
)
/
sum by (service, environment) (
  rate(iam_authorization_decisions_total{result=~"allow|deny"}[5m])
)
```

Kết quả có đơn vị phần trăm. Lấy `rate()` trên từng counter rồi mới `sum()` giúp xử lý reset của các tiến trình riêng biệt trước khi cộng.

Nếu cần so sánh gateway với service, thêm `enforcement_point` vào **cả hai** mệnh đề `sum by`. Chỉ thêm vào tử sẽ gây lệch chiều hoặc lỗi ghép chuỗi thời gian. Không cộng hai điểm kiểm tra để diễn giải thành tỷ lệ request nếu cùng một request có thể qua cả hai.

Truy vấn cần được hiển thị cùng số quyết định hợp lệ trong cửa sổ:

```promql
sum by (service, environment) (
  increase(iam_authorization_decisions_total{result=~"allow|deny"}[5m])
)
```

`increase()` là ước lượng theo dữ liệu scrape và có thể cho số không nguyên. Nó thích hợp cho dashboard/cảnh báo vận hành, không thay thế sổ audit cần đối soát từng sự kiện.

### 5.2. Theo dõi lỗi đánh giá riêng

```promql
100 *
sum by (service, environment) (
  rate(iam_authorization_decisions_total{result=~"error|indeterminate"}[5m])
)
/
sum by (service, environment) (
  rate(iam_authorization_decisions_total[5m])
)
```

Phần mẫu số bao gồm bốn nhóm kết quả của counter. Nếu hệ thống bổ sung nhóm mới, cần cập nhật hợp đồng và truy vấn; không để thay đổi schema làm tỷ lệ âm thầm đổi nghĩa.

### 5.3. Cảnh báo minh họa có điều kiện lưu lượng

Giả sử một dịch vụ đã thống nhất ngưỡng minh họa: tỷ lệ deny lớn hơn 5% và có hơn 1.000 quyết định hợp lệ trong cửa sổ 5 phút. Biểu thức có thể là:

```promql
(
  sum by (service, environment) (
    rate(iam_authorization_decisions_total{result="deny"}[5m])
  )
  /
  sum by (service, environment) (
    rate(iam_authorization_decisions_total{result=~"allow|deny"}[5m])
  )
  > 0.05
)
and on (service, environment)
(
  sum by (service, environment) (
    increase(iam_authorization_decisions_total{result=~"allow|deny"}[5m])
  ) > 1000
)
```

Ngưỡng `0.05` dùng tỷ lệ từ 0 đến 1, vì biểu thức cảnh báo chưa nhân 100. Có thể đặt thời gian duy trì như `for: 10m` trong rule để tránh cảnh báo vì một biến động ngắn. Điều này nghĩa là điều kiện phải liên tục đúng trong thời gian đó, không phải tự động thay cửa sổ tính toán thành 10 phút.

Các số 5%, 1.000 và 10 phút chỉ minh họa cơ chế. Ngưỡng thực tế phụ thuộc lưu lượng, hành động, mức độ quan trọng và baseline. Với thao tác đặc quyền ít được gọi, điều kiện 1.000 có thể che mất một vấn đề nghiêm trọng; khi đó cần rule riêng dựa trên số lần thất bại, tổng hợp thời gian dài hơn hoặc tín hiệu nghiệp vụ.

Nếu một kết quả chưa từng xuất hiện, thư viện metric có thể chưa tạo chuỗi tương ứng. Có thể khởi tạo trước các tổ hợp nhãn hữu hạn cần thiết hoặc xử lý rõ trường hợp thiếu chuỗi. Không dùng một giá trị 0 mặc định không có nhãn để che tình trạng mất dữ liệu; đồng thời phải cảnh báo riêng khi mất thu thập hoặc khi mẫu số bằng 0 trong lúc hệ thống đáng lẽ có tải.

## 6. Đọc tỷ lệ cùng với số lượng và thành phần lưu lượng

### 6.1. Tỷ lệ tăng chưa chắc số lần từ chối tăng

| Cửa sổ | Allow | Deny | Denial rate |
| --- | ---: | ---: | ---: |
| Trước | 9.900 | 100 | 1% |
| Sau | 900 | 100 | 10% |

Số deny vẫn là 100; tỷ lệ tăng vì lượng allow giảm. Có thể một luồng nghiệp vụ hợp lệ dừng hoạt động hoặc cấu trúc lưu lượng thay đổi. Nếu chỉ nhìn phần trăm, đội vận hành dễ kết luận nhầm rằng số lượt vượt quyền tăng gấp mười.

### 6.2. Không lấy trung bình đơn giản của các phần trăm

Giả sử dịch vụ A có 1 deny trong 10 quyết định, dịch vụ B có 90 deny trong 990 quyết định. Tỷ lệ toàn bộ là:

```text
(1 + 90) / (10 + 990) = 9,1%
```

Không lấy `(10% + 9,09%) / 2` để tính tỷ lệ tổng. Cần cộng số lượng tử và mẫu rồi mới chia. Đây cũng là lý do nên giữ counter gốc thay vì chỉ lưu một gauge phần trăm đã tính sẵn.

### 6.3. Tỷ lệ tổng có thể che khuất một nhóm bị ảnh hưởng

Nếu phần lớn lưu lượng là đọc tài liệu công khai, một lỗi làm nhóm kế toán không duyệt được hóa đơn có thể không làm tỷ lệ toàn hệ thống thay đổi đáng kể. Cần phân tách theo nhóm hành động và dịch vụ quan trọng trước khi kết luận hệ thống bình thường.

Khi tỷ lệ biến động, kiểm tra xem thành phần lưu lượng có thay đổi không: tỷ trọng người dùng/workload, hành động đọc/ghi, API mới, kiểm thử âm tính, giờ làm việc hoặc tác vụ batch. Chỉ so sánh những cửa sổ có ý nghĩa tương đồng, đồng thời đánh dấu thời điểm triển khai ứng dụng, đổi chính sách và đồng bộ quyền.

## 7. Những nguyên nhân thường gặp trong IAM

| Mẫu quan sát | Giả thuyết cần kiểm chứng | Dữ liệu đối chiếu |
| --- | --- | --- |
| Deny tăng ngay sau thay đổi RBAC | Mapping role/permission thiếu hoặc thay đổi có chủ đích | Phiên bản chính sách, lịch sử gán role, nhóm hành động |
| Một nhóm người dùng mới bị deny | Cấp phát tài khoản hoặc đồng bộ group chưa hoàn tất | Sự kiện provisioning, trạng thái membership, thời điểm đồng bộ |
| Chỉ hành động ABAC bị ảnh hưởng | Thuộc tính sai, thiếu hoặc cũ | Nguồn thuộc tính, thời điểm cập nhật, lớp nguyên nhân |
| Workload vừa triển khai bị deny | Binding service identity hoặc quyền tài nguyên sai | Danh tính workload thực tế, namespace, cấu hình binding |
| Error tăng, deny theo chính sách ổn định | PDP hoặc nguồn dữ liệu quyền gặp lỗi | Timeout, độ trễ, sức khỏe phụ thuộc, kết quả fail closed |
| Deny tăng trên nhiều tài nguyên không liên quan | Dò quét hoặc hành vi vượt quyền | Mẫu hành động, trace, audit, ngữ cảnh nguồn gọi đã được kiểm soát |
| Deny tăng sau thu hồi quyền | Có thể là kết quả mong muốn | Yêu cầu thu hồi, thời điểm hiệu lực, cache và phiên còn sử dụng |
| Deny giảm mạnh sau deploy | Có thể do cấp quyền rộng hoặc bỏ qua kiểm tra | Độ phủ kiểm tra, phiên bản ứng dụng, policy, telemetry |

Mỗi hàng là một giả thuyết, không phải kết luận tự động. Chẳng hạn, thu hồi quyền đúng có thể tạo deny nhưng cũng có thể bộc lộ ứng dụng tiếp tục dùng một credential đáng lẽ đã được thay. Cần ghép dấu vết quyết định với vòng đời danh tính và thay đổi quyền.

## 8. Phân biệt deny đúng với deny gây gián đoạn

Trong vận hành có ít nhất hai câu hỏi khác nhau:

1. Hệ thống có đang chặn những gì chính sách yêu cầu phải chặn không?
2. Người dùng hoặc workload đáng lẽ được phép có đang bị chặn không?

Metric deny thô trả lời về tần suất kết quả, chưa trả lời đầy đủ hai câu hỏi này. Để xác định một deny gây gián đoạn, cần bằng chứng độc lập: yêu cầu nghiệp vụ được phê duyệt, trạng thái role hợp lệ, chính sách dự kiến, ca kiểm thử hoặc xác nhận của chủ tài nguyên.

Không suy ra “đáng lẽ phải được phép” chỉ vì cùng người dùng đó từng được phép trước đây. Quyền có thể vừa bị thu hồi đúng quy trình, tài nguyên đã chuyển chủ sở hữu hoặc điều kiện truy cập đã thay đổi.

Một bộ kiểm tra tổng hợp có thể gồm:

- Danh tính kiểm thử được phép đọc tài nguyên thử nghiệm và phải nhận allow.
- Danh tính kiểm thử không có quyền ghi và phải nhận deny.
- Tình huống qua ranh giới tenant phải bị chặn.
- Tình huống phụ thuộc đánh giá quyền gặp lỗi phải tuân thủ chế độ thực thi đã được thiết kế.

Các phép thử cần dùng dữ liệu và tài khoản chuyên dụng. Gắn dấu hiệu kiểm thử bằng cách có thể phân biệt trong phân tích, tránh để số lần deny chủ động làm thay đổi ý nghĩa dashboard người dùng thực. Không mở quyền chỉ để phép thử luôn xanh.

Nếu xây dựng SLI cho “quyết định sai gây gián đoạn”, phải định nghĩa được nguồn xác nhận quyền dự kiến và độ phủ của phép đo. Không lấy `1 - denial_rate` rồi gọi đó là độ sẵn sàng IAM: nhiều deny là kết quả bảo vệ đúng, trong khi lỗi đánh giá bị chặn có thể không nằm trong tử số deny của định nghĩa này.

## 9. Thiết kế dashboard và cảnh báo có thể hành động

Một dashboard vận hành nên đặt cạnh nhau các thông tin sau:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Tỷ lệ deny theo thời gian | Có biến động so với hành vi bình thường không? |
| Số allow, deny và tổng quyết định hợp lệ | Tỷ lệ thay đổi do tử số hay mẫu số? |
| Tỷ lệ error/indeterminate và kết quả thực thi bị chặn | Có sự cố đánh giá quyền hoặc fail closed không? |
| Phân tách theo service, điểm thực thi, nhóm hành động | Phạm vi ảnh hưởng nằm ở đâu? |
| Mốc thay đổi ứng dụng, policy và provisioning | Biến động có đi cùng một thay đổi không? |
| Trạng thái thu thập và độ trễ telemetry | Dữ liệu hiện tại có đủ để tin cậy không? |

Nên kết hợp cửa sổ ngắn để phát hiện nhanh với cửa sổ dài để nhìn xu hướng. Với tải thấp, một deny trên một quyết định tạo ra 100% nhưng chưa đủ để suy ra xu hướng; với hành động đặc quyền, chính một sự kiện đó vẫn có thể cần điều tra. Mức độ quan trọng phải đến từ ngữ cảnh, không chỉ cỡ mẫu.

Tách cảnh báo trải nghiệm truy cập, cảnh báo lỗi hạ tầng đánh giá và cảnh báo nghi vấn vượt quyền khi chúng có người xử lý khác nhau. Cảnh báo cần có phạm vi, số lượng, thời gian bắt đầu, nhóm nguyên nhân, liên kết truy vấn nội bộ và runbook. Tránh đính kèm token, dữ liệu nhạy cảm hoặc danh sách định danh người dùng vào kênh cảnh báo rộng.

## 10. Quy trình điều tra một đợt tăng denial rate

### Bước 1: Xác minh tín hiệu

Kiểm tra cửa sổ thời gian, mẫu số, số deny tuyệt đối, counter reset, chuỗi thời gian bị thiếu và lỗi thu thập. Xác nhận dashboard đang đo quyết định quyền tại đúng điểm thực thi, không đếm tất cả mã HTTP lỗi.

### Bước 2: Khoanh vùng ảnh hưởng

Tách theo dịch vụ, nhóm hành động, loại danh tính và điểm thực thi. Từ dữ liệu có quyền truy cập phù hợp, xác định liệu nhiều người dùng hợp lệ bị ảnh hưởng hay chủ yếu một nguồn gọi đang thử các thao tác không được cấp.

### Bước 3: Đọc nguyên nhân và tương quan thay đổi

Lấy một tập sự kiện đại diện, liên kết bằng trace/decision ID và đối chiếu phiên bản chính sách. Kiểm tra lịch sử cấp phát, thay đổi group/role, thuộc tính ABAC, binding workload, cache và độ trễ đồng bộ. Đối chiếu phiên bản thực sự được đánh giá thay vì chỉ xem phiên bản đã khai báo trong hệ thống quản lý.

### Bước 4: Xác định kết quả mong muốn

Chủ tài nguyên hoặc nguồn quản trị quyền xác nhận những hành động nào phải được phép. Phân biệt thay đổi từ chối có chủ đích, cấu hình sai và lỗi phụ thuộc. Kiểm tra cả deny đúng để tránh sửa lỗi bằng cách mở rộng quyền cho mọi người.

### Bước 5: Khắc phục đúng phạm vi

Tùy nguyên nhân, có thể sửa mapping role, khôi phục nguồn thuộc tính, hoàn tất provisioning, sửa binding workload hoặc phục hồi PDP. Rollback chính sách phải theo quy trình thay đổi và không vô tình phục hồi quyền vừa được thu hồi hợp lệ. Không tắt authorization hoặc chuyển sang fail open chỉ vì cần hạ tỷ lệ deny.

### Bước 6: Xác nhận tác động sau sửa

Kiểm tra các hành động hợp lệ đã hoạt động lại, các hành động vượt quyền vẫn bị chặn, tỷ lệ lỗi đánh giá giảm và telemetry đầy đủ. Theo dõi cả cửa sổ sau sửa đủ dài để thấy tác động của cache hoặc đồng bộ, rồi ghi lại nguyên nhân và phạm vi ảnh hưởng.

## 11. Tình huống minh họa: người duyệt hóa đơn bị từ chối

Dịch vụ hóa đơn có baseline khoảng 1% deny ở nhóm `invoice_write`. Sau một lần cập nhật chính sách, cửa sổ 5 phút ghi nhận 8.800 allow và 1.200 deny, tương ứng 12%. Lưu lượng hợp lệ cộng deny vẫn là 10.000, còn error/indeterminate không tăng.

Phân tích theo nhóm hành động cho thấy phần tăng tập trung vào `invoice.approve`; các thao tác đọc vẫn bình thường. Sự kiện có lớp nguyên nhân `missing_permission` và cùng phiên bản policy mới. Trace cho thấy người dùng đã xác thực thành công, bao gồm MFA theo yêu cầu, nên việc đăng nhập lại không giải quyết được nguyên nhân quyền.

Đối chiếu nguồn quản trị quyền cho thấy nhóm người duyệt đã được phê duyệt, nhưng mapping từ role kế toán sang `invoice.approve` bị thiếu trong bản chính sách mới. Đội vận hành sửa đúng mapping và kiểm tra hai phía: người duyệt hợp lệ được allow; người cùng phòng ban nhưng không có role duyệt vẫn bị deny.

Sau sửa, trong cửa sổ tương đương có 9.900 allow và 100 deny, tỷ lệ trở về 1%. Điều này củng cố kết quả khắc phục khi đi cùng ca kiểm thử và log quyết định. Chỉ nhìn tỷ lệ giảm sẽ chưa đủ, vì một cấu hình cho phép toàn bộ cũng có thể tạo ra biểu đồ tương tự.

## 12. Những cách diễn giải dễ gây sai lệch

- Xem mọi deny là sự cố: bỏ qua mục tiêu ít quyền nhất và các lần chặn đúng chính sách.
- Gộp timeout PDP vào policy deny: che khuất sự cố phụ thuộc và làm mất tín hiệu fail closed.
- Đếm cả log PDP lẫn log PEP: cộng trùng cùng một quyết định.
- Chỉ đếm cache miss: đo cách dùng cache thay vì toàn bộ quyết định được thực thi.
- Trung bình các tỷ lệ của nhiều dịch vụ: làm nhóm lưu lượng nhỏ có trọng số sai.
- So sánh hai khoảng thời gian có cơ cấu hành động khác nhau: quy nhầm biến động lưu lượng thành thay đổi chất lượng chính sách.
- Tính tỷ lệ từ log được lấy mẫu không đồng đều: làm mẫu số thiếu các quyết định allow.
- Ghi user/resource ID vào metric: tạo cardinality lớn và tăng phạm vi lộ dữ liệu.
- Coi mẫu số 0 là tỷ lệ 0%: báo bình thường khi thực tế không có dữ liệu đủ để tính.
- Hạ tỷ lệ bằng cách cấp quyền rộng: cải thiện con số nhưng làm suy yếu kiểm soát truy cập.

Authorization denial rate hữu ích khi định nghĩa đơn vị đếm, kết quả và mẫu số được giữ nhất quán. Kết hợp tỷ lệ với số lượng, nguyên nhân, độ đầy đủ của telemetry và quyền dự kiến giúp người vận hành phân biệt một cơ chế bảo vệ đang chặn đúng với một thay đổi IAM đang cản trở công việc hợp lệ.
