# Phân biệt chỉ báo mức dịch vụ (SLI), mục tiêu mức dịch vụ (SLO) và ngưỡng cảnh báo

> Phạm vi: thiết kế phép đo và cảnh báo khi vận hành ứng dụng Spring Boot Actuator 3.3.x. Các tỷ lệ, cửa sổ thời gian và chính sách phân loại sự kiện trong bài là ví dụ cụ thể; cần chọn lại theo trải nghiệm người dùng và dữ liệu thực tế của dịch vụ.

## 1. Từ một số đo đến một quyết định vận hành

Giả sử màn hình giám sát cho biết 99,97% yêu cầu trong 30 ngày không gặp lỗi phía máy chủ. Con số đó mô tả kết quả đã đo. Muốn kết luận dịch vụ đạt yêu cầu hay chưa, bạn cần một mục tiêu. Muốn biết có cần gọi người trực ngay không, bạn còn cần điều kiện cảnh báo và hành động tương ứng.

Ba khái niệm giải quyết ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Chỉ báo mức dịch vụ — SLI (Service Level Indicator) | Chúng ta đo chất lượng phục vụ bằng gì, kết quả hiện tại là bao nhiêu? | Tỷ lệ yêu cầu đủ điều kiện không trả HTTP 5xx |
| Mục tiêu mức dịch vụ — SLO (Service Level Objective) | Kết quả nào được xem là đạt, trên phạm vi và khoảng thời gian nào? | Ít nhất 99,9% yêu cầu đó đạt trong cửa sổ trượt 30 ngày |
| Ngưỡng và quy tắc cảnh báo | Khi nào hệ thống cần yêu cầu người vận hành hành động? | Tỷ lệ lỗi vượt một mức ở cả cửa sổ dài và ngắn, rồi duy trì đủ thời gian quy định |

SLI là phép đo được định nghĩa cẩn thận; SLO đặt mục tiêu cho phép đo đó. Một tỷ lệ đứng riêng không mô tả đầy đủ cả hai. [Định nghĩa SLI và SLO của Google SRE](https://sre.google/sre-book/service-level-objectives/).

CPU vượt 80% trong 10 phút là một điều kiện vận hành có thể hữu ích. Nó chưa tự trở thành SLO cho trải nghiệm người dùng. Ngược lại, một dịch vụ có CPU thấp vẫn có thể trả lỗi cho mọi yêu cầu vì cấu hình sai.

## 2. Định nghĩa SLI: phải biết đang đếm điều gì

Với SLI dạng tỷ lệ sự kiện:

```text
SLI(W) = số sự kiện tốt trong W / tổng số sự kiện đủ điều kiện trong W
```

W là cửa sổ quan sát. Trước khi viết truy vấn, cần chốt:

1. **Đối tượng:** hành trình hoặc thao tác nào của người dùng?
2. **Sự kiện đủ điều kiện:** loại yêu cầu nào nằm trong mẫu số?
3. **Sự kiện tốt:** đáp ứng điều kiện gì để được đưa vào tử số?
4. **Điểm đo:** tại trình duyệt, cổng vào hay bên trong ứng dụng?
5. **Cửa sổ và cách tổng hợp:** 5 phút để điều tra, hay 30 ngày để đánh giá mục tiêu?
6. **Trạng thái thiếu dữ liệu:** xử lý thế nào khi chưa có yêu cầu hoặc mất khả năng quan sát?

Định nghĩa theo sự kiện tốt/tổng sự kiện giúp gắn phép đo với chất lượng phục vụ, đồng thời làm rõ phần không đạt. [Cách xây dựng SLI trong SRE Workbook](https://sre.google/workbook/implementing-slos/).

### Hai SLI có thể dùng cho cùng một API

Ví dụ minh họa xuyên suốt bài chọn GET vào route /api/orders/{id} của orders-api trong production. Đây là route mẫu, không dùng từng mã đơn hàng làm nhãn.

| SLI | Sự kiện đủ điều kiện | Sự kiện tốt |
| --- | --- | --- |
| Khả dụng theo mã HTTP | Yêu cầu GET đã được ứng dụng ghi nhận cho route đã chọn | Phản hồi không thuộc nhóm HTTP 5xx |
| Thành công đủ nhanh | Cùng tập yêu cầu trên | Phản hồi không thuộc HTTP 5xx và thời gian xử lý không quá 300 ms |

Trong chính sách minh họa này, 4xx không bị xem là lỗi khả dụng phía máy chủ. Điều đó không có nghĩa mọi 4xx đều có thể bỏ qua: nếu 429 thể hiện hệ thống không phục vụ được người dùng, hãy sửa định nghĩa sự kiện tốt cho phù hợp. Mã HTTP cũng có thể chưa phản ánh lỗi nghiệp vụ trả trong thân phản hồi.

Endpoint health hoặc prometheus không nằm trong hành trình đọc đơn hàng này. Đưa chúng vào mẫu số có thể làm tỷ lệ trông tốt hơn mà không cải thiện trải nghiệm của người dùng.

### Giới hạn của điểm đo trong ứng dụng

Số liệu Actuator phía máy chủ chỉ quan sát được những gì đã đi qua điểm ghi nhận của nó. Lỗi DNS, kết nối thất bại hoặc yêu cầu bị chặn trước ứng dụng có thể không xuất hiện trong bộ đếm HTTP của ứng dụng. Phải công bố đây là phép đo phía máy chủ và bổ sung điểm đo ở cổng vào hoặc kiểm tra từ bên ngoài nếu mục tiêu đòi hỏi trải nghiệm đầu cuối.

Vì vậy, /actuator/health trả thành công chưa chứng minh người dùng có thể hoàn tất thao tác nghiệp vụ.

## 3. Định nghĩa SLO: có mục tiêu, cửa sổ và phạm vi

Một SLO tham khảo có thể được viết như sau:

```text
Dịch vụ: orders-api
Môi trường: production
Thao tác: GET /api/orders/{id}
SLI: tỷ lệ yêu cầu đủ điều kiện không trả HTTP 5xx
Mục tiêu: >= 99,9%
Cửa sổ đánh giá: 30 ngày trượt
Điểm đo: bộ đo HTTP phía ứng dụng
```

Đây là mô tả chính sách, không phải cấu hình Spring Boot. Trong vận hành thực tế còn cần người chịu trách nhiệm, nguồn dữ liệu, ngoại lệ đã thống nhất và cách xử lý khi không đạt. [Ví dụ tài liệu SLO](https://sre.google/workbook/slo-document/).

Cửa sổ 30 ngày trượt và tháng lịch là hai lựa chọn khác nhau. Với cửa sổ trượt, dữ liệu cũ liên tục rời khỏi phạm vi đánh giá. Không thay đổi qua lại hai cách tính mà vẫn giữ nguyên lời diễn giải trên dashboard.

Đối với SLI đủ nhanh, một SLO khác có thể là ít nhất 99% yêu cầu vừa không lỗi phía máy chủ vừa có thời gian xử lý không quá 300 ms trong cùng cửa sổ. Khi đó:

- **300 ms** là ranh giới để phân loại từng sự kiện tốt hay không.
- **99%** là tỷ lệ mục tiêu của tập sự kiện.
- **30 ngày** là cửa sổ đánh giá mục tiêu.

Ba giá trị có vai trò khác nhau. Chỉ ghi 300 ms chưa đủ để định nghĩa một SLO.

## 4. Ngân sách lỗi: chuyển mục tiêu thành phần được phép không đạt

Với SLO dạng tỷ lệ và mục tiêu S nhỏ hơn 1:

```text
Tỷ lệ sự kiện xấu được phép = 1 - S
Ngân sách sự kiện xấu = (1 - S) * tổng sự kiện đủ điều kiện
Ngân sách còn lại = ngân sách sự kiện xấu - số sự kiện xấu thực tế
```

Ví dụ cùng một cửa sổ 30 ngày có đủ dữ liệu:

| Đại lượng | Giá trị |
| --- | --- |
| Tổng yêu cầu đủ điều kiện | 2.000.000 |
| SLO | 99,9% |
| Số yêu cầu xấu được phép theo tỷ lệ | 2.000 |
| Số yêu cầu xấu đã quan sát | 600 |
| SLI quan sát | 99,97% |
| Ngân sách đã dùng | 30% |
| Ngân sách còn lại | 1.400 yêu cầu xấu, tương ứng 70% |

Đây là phép đánh giá trên tổng yêu cầu đã biết của cửa sổ. Nếu lưu lượng thay đổi, tổng mẫu số và ngân sách tính theo số sự kiện cũng thay đổi. Không coi 2.000 là hạn mức cố định cho mọi giai đoạn hay mọi mức lưu lượng.

Đặc biệt, **SLO theo tỷ lệ yêu cầu không tự đổi thành số phút được ngừng phục vụ**. Cách quy đổi thời gian chỉ phù hợp với phép đo theo thời gian hoặc các giả định được nêu rõ về lưu lượng. Một phút cao điểm có thể ảnh hưởng nhiều yêu cầu hơn một giờ ít người dùng.

Nếu ngân sách còn lại âm, giữ thông tin vượt ngân sách để đánh giá; không ép số âm về 0 rồi làm mất mức độ vi phạm.

## 5. Ngưỡng cảnh báo: lựa chọn thời điểm cần hành động

Cảnh báo cần xác định biểu thức, cửa sổ đo, ngưỡng, thời gian duy trì, mức độ và hành động mong đợi. Trong Prometheus, for yêu cầu điều kiện tiếp tục đúng qua các lần đánh giá trong khoảng đó trước khi cảnh báo chuyển sang trạng thái firing. [Quy tắc cảnh báo của Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

Ví dụ:

```text
Điều kiện đo: tỷ lệ lỗi của 5 phút gần nhất
Ngưỡng: > 1%
Thời gian duy trì: 2 phút
Hành động dự kiến: yêu cầu người trực điều tra
```

Đây là một quy tắc cảnh báo minh họa, không phải SLO 99%. Cửa sổ 5 phút dùng để tính tỷ lệ; thời gian duy trì 2 phút dùng để quyết định trạng thái cảnh báo. Hai khoảng thời gian không thay thế nhau.

Hai tình huống cho thấy vì sao không dùng lẫn:

| Tình huống | SLO toàn cửa sổ | Cảnh báo hiện tại |
| --- | --- | --- |
| Đầu kỳ phục vụ tốt, hiện tại lỗi tăng rất nhanh | Có thể vẫn đạt | Có thể cần cảnh báo sớm để bảo vệ ngân sách |
| Vừa hồi phục sau sự cố lớn | Có thể vẫn không đạt | Cảnh báo về lỗi đang diễn ra có thể đã hết |

Đợi đến khi SLO của cả 30 ngày đã không đạt mới gọi người trực có thể quá muộn. Nhưng gọi người trực chỉ vì một con số vượt nhẹ trong một mẫu cũng có thể tạo nhiễu.

### Tốc độ tiêu hao ngân sách lỗi

Tốc độ tiêu hao, thường gọi là burn rate, so sánh tỷ lệ sự kiện xấu gần đây với tỷ lệ được phép:

```text
Burn rate(W) = tỷ lệ sự kiện xấu trong W / (1 - SLO)
```

Với SLO 99,9%, tỷ lệ xấu được phép là 0,1% = 0,001. Nếu tỷ lệ xấu gần đây là 1% = 0,01, burn rate bằng 10. Nếu là 2%, burn rate bằng 20.

Burn rate mô tả tốc độ hiện tại theo tỷ lệ; nó không phải phần trăm ngân sách đã dùng. Burn rate bằng 10 không có nghĩa đã dùng 10% ngân sách.

Trong giả định lưu lượng tương đối ổn định, có thể ước lượng phần ngân sách tiêu hao trong khoảng w của kỳ T bằng burn rate nhân w/T. Ví dụ T = 30 ngày = 720 giờ, burn rate 14,4 trong 1 giờ tương ứng khoảng 2% ngân sách theo giả định đó. Khi lưu lượng biến động mạnh, phải kiểm tra số sự kiện thực tế; không xem phép ước lượng thời gian này là đẳng thức cho mọi dữ liệu.

Một cách chọn điều kiện là kết hợp cửa sổ dài để đánh giá mức ảnh hưởng và cửa sổ ngắn để kiểm tra lỗi vẫn đang diễn ra. Các mức như 14,4 ở 1 giờ/5 phút là điểm tham khảo cần hiệu chỉnh, không phải hằng số của Spring Boot. [Cảnh báo theo ngân sách lỗi](https://sre.google/workbook/alerting-on-slos/).

## 6. Actuator cung cấp dữ liệu; cấu hình bucket chưa tạo mục tiêu

Trong ứng dụng Spring MVC thông thường, bộ đo HTTP có tên Micrometer là http.server.requests. Khi xuất sang Prometheus, có thể dùng các chuỗi dạng http_server_requests_seconds_count và các bucket histogram tương ứng.

Với ứng dụng đã có Actuator và registry Prometheus, phần cấu hình minh họa:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      service: orders-api
      environment: production
    distribution:
      slo:
        http.server.requests: 300ms
```

Đây là đoạn cấu hình ghép vào ứng dụng, chưa phải toàn bộ dự án. Dependency cần có gồm spring-boot-starter-actuator và io.micrometer:micrometer-registry-prometheus, cùng ngăn xếp web mà ứng dụng thực sự dùng.

Tên management.metrics.distribution.slo dễ gây hiểu lầm. Nó cấu hình histogram tích lũy với ranh giới đã chọn. Trong ví dụ, 300 ms là ranh giới bucket; cấu hình không khai báo mục tiêu 99%, cửa sổ 30 ngày hay người nhận cảnh báo. [Thuộc tính distribution.slo của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

Với histogram cổ điển Prometheus cho Timer, đơn vị thời gian là giây; mốc 300 ms tương ứng bucket le="0.3". Bucket tích lũy đó đếm các lần có thời gian không quá ranh giới. Phải kiểm tra dữ liệu xuất thực tế và bảo đảm mọi bản chạy tham gia phép tính đều có bucket này. [Histogram và ranh giới SLO trong Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

Không lấy trung bình các p95 của nhiều instance để suy ra p95 toàn dịch vụ. Nếu mục tiêu là tỷ lệ yêu cầu không quá 300 ms, đếm đúng bucket trên tổng sự kiện thường thể hiện hợp đồng trực tiếp hơn một percentile xấp xỉ. [Histogram và cách tính tỷ lệ theo bucket](https://prometheus.io/docs/practices/histograms/).

## 7. Một ví dụ quy tắc Prometheus có đủ tử số, mẫu số và cảnh báo

Ví dụ tiếp tục dùng chính sách khả dụng theo HTTP: mọi yêu cầu GET của route đã chọn nằm trong mẫu số; chỉ HTTP 5xx nằm trong số sự kiện xấu. Giả định dữ liệu các instance được thu thập đầy đủ, nhãn service/environment đã có và thời hạn lưu trữ đủ cho mục đích đánh giá.

Tệp rules minh họa sau tính tỷ lệ ở 5 phút và 1 giờ, rồi đặt một cảnh báo tiêu hao nhanh. Nó được nạp bởi Prometheus, không được Spring Boot tự đọc từ application.yml:

```yaml
groups:
  - name: orders-slo
    interval: 30s
    rules:
      - record: orders:requests:rate5m
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}"
            }[5m])
          )
      - record: orders:errors:rate5m
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}", status=~"5.."
            }[5m])
          )
          or on (service, environment)
          (0 * orders:requests:rate5m)
      - record: orders:errors:ratio5m
        expr: orders:errors:rate5m / orders:requests:rate5m
      - record: orders:requests:rate1h
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}"
            }[1h])
          )
      - record: orders:errors:rate1h
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}", status=~"5.."
            }[1h])
          )
          or on (service, environment)
          (0 * orders:requests:rate1h)
      - record: orders:errors:ratio1h
        expr: orders:errors:rate1h / orders:requests:rate1h
      - alert: OrdersAvailabilityFastBurn
        expr: |
          (orders:errors:ratio1h > 14.4 * 0.001)
          and on (service, environment)
          (orders:errors:ratio5m > 14.4 * 0.001)
          and on (service, environment)
          (orders:requests:rate5m > 0)
        for: 2m
        labels:
          severity: page
        annotations:
          summary: 'Ngân sách lỗi orders-api đang bị tiêu hao nhanh'
          description: 'Tỷ lệ lỗi vượt 1.44% ở cả cửa sổ 1 giờ và 5 phút.'
```

Giải thích các lựa chọn:

- Tính rate trên từng bộ đếm trước rồi mới cộng các instance, để việc bộ đếm bị đặt lại khi khởi động lại được xử lý tại đúng chuỗi.
- Cộng tử số và mẫu số theo cùng service/environment, không trung bình các tỷ lệ instance.
- Khi chưa có chuỗi 5xx nhưng vẫn có mẫu số hợp lệ, nhánh 0 nhân mẫu số cho phép biểu diễn không có lỗi theo mô hình dữ liệu đã nêu.
- Nếu mẫu số bằng 0, phép chia không cho tỷ lệ hợp lệ; không tự biến trường hợp đó thành 100% tốt.
- Nếu mẫu số cũng mất, nhánh thay thế không tạo ra một dịch vụ khỏe giả. Tuy nhiên, mất dữ liệu một phần vẫn cần kiểm tra riêng.

Ý nghĩa rate và phép ghép or/on được định nghĩa trong PromQL. Nhánh thay thế chỉ đúng khi đã xác nhận cách xuất số liệu; nó không chứng minh rằng mọi lỗi thật đều được quan sát. [Hàm rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate), [Các toán tử tập hợp và ghép vector](https://prometheus.io/docs/prometheus/latest/querying/operators/#logical-set-binary-operators).

Ngưỡng 14,4 nhân 0,001 bằng 0,0144, tức tỷ lệ lỗi 1,44%. Quy tắc yêu cầu cả tỷ lệ 1 giờ và 5 phút vượt mức đó. for: 2m thêm thời gian chờ của ví dụ này; cần đánh giá độ trễ phát hiện mà lựa chọn đó tạo ra.

severity: page là nhãn để hệ thống định tuyến thông báo sử dụng. Chỉ đặt nhãn này chưa tự gọi điện hay gửi thông báo; cần cấu hình đường xử lý cảnh báo tương ứng.

Đây chỉ là một quy tắc tiêu hao nhanh để minh họa ranh giới giữa phép đo, mục tiêu và cảnh báo. Nó chưa phát hiện mọi kiểu suy giảm kéo dài, mất dữ liệu hoặc lỗi phía ngoài ứng dụng. Các truy vấn 5 phút/1 giờ này cũng **không phải phép tính đạt SLO của cả 30 ngày**.

### Đo tỷ lệ thành công đủ nhanh

Dựa trên cùng mẫu số, một truy vấn 5 phút minh họa có thể là:

```promql
(
  sum by (service, environment) (
    rate(http_server_requests_seconds_bucket{
      service="orders-api", environment="production",
      method="GET", uri="/api/orders/{id}",
      status!~"5..", le="0.3"
    }[5m])
  )
  or on (service, environment)
  (0 * orders:requests:rate5m)
)
/ orders:requests:rate5m
```

Tử số đòi hỏi đồng thời không lỗi 5xx và không quá 300 ms. Một phản hồi 503 rất nhanh vẫn không được tính là tốt trong SLI này. Truy vấn phụ thuộc vào recording rule mẫu số đã khai báo ở trên và bucket đúng trên mọi instance; phải kiểm tra dữ liệu trước khi diễn giải kết quả.

Nếu mục tiêu của SLI này là 99%, dùng ngân sách 1% cho nó. Không dùng nhầm ngân sách 0,1% của SLO khả dụng 99,9%.

## 8. Tổng hợp và thiếu dữ liệu có thể làm kết luận sai

### Cộng số sự kiện trước khi chia

Giả sử một nhóm có 10 yêu cầu, cả 10 tốt: SLI là 100%. Nhóm khác có 990 yêu cầu, 891 tốt: SLI là 90%. Trung bình đơn giản hai tỷ lệ cho 95%, nhưng toàn bộ có 901/1.000 yêu cầu tốt, tức 90,1%.

Cùng nguyên tắc đó áp dụng khi tổng hợp theo instance hoặc các khoảng thời gian có lưu lượng khác nhau. Để đánh giá SLO theo sự kiện của toàn cửa sổ, cần tỷ lệ tổng sự kiện tốt trên tổng sự kiện đủ điều kiện. Không thay nó bằng trung bình các SLI 5 phút nếu mục tiêu không định nghĩa trọng số thời gian như vậy.

### Phân biệt ba trạng thái

| Trạng thái | Có thể kết luận gì? |
| --- | --- |
| Có đủ dữ liệu, mẫu số dương, không ghi nhận sự kiện xấu | Có thể tính tỷ lệ tốt của phạm vi đã định nghĩa |
| Có dữ liệu nhưng không có yêu cầu trong cửa sổ | Không có tỷ lệ dựa trên yêu cầu để đánh giá; cần chính sách không lưu lượng |
| Thiếu dữ liệu hoặc không thu thập được | Không đủ bằng chứng để kết luận dịch vụ đạt |

Một ngưỡng tối thiểu về lưu lượng có thể giảm cảnh báo nhiễu nhưng cũng bỏ qua ảnh hưởng đến người dùng khi ít yêu cầu. Nếu dùng, phải nêu rõ sự đánh đổi và có cách quan sát bổ sung, chẳng hạn kiểm tra hành trình từ bên ngoài. Không chữa dữ liệu thiếu bằng cách gán mọi tỷ lệ không tồn tại thành 0% lỗi.

## 9. Chương trình Java kiểm chứng phép tính

Tệp SloBudgetDemo.java dưới đây dùng số sự kiện giả định đã biết để kiểm tra công thức. Nó không đọc Actuator hoặc chạy một hệ thống cảnh báo; không được dùng kết quả của nó làm bằng chứng ứng dụng thật đã đạt SLO.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Optional;

public class SloBudgetDemo {
    static Optional<BigDecimal> goodFraction(long total, long bad) {
        if (total < 0 || bad < 0 || bad > total) {
            throw new IllegalArgumentException("Invalid event counts");
        }
        if (total == 0) {
            return Optional.empty();
        }
        return Optional.of(
            BigDecimal.valueOf(total - bad).divide(
                BigDecimal.valueOf(total), 9, RoundingMode.HALF_UP
            )
        );
    }

    public static void main(String[] args) {
        long total = 2_000_000L;
        long bad = 600L;
        BigDecimal objective = new BigDecimal("0.999");
        BigDecimal allowedFraction = BigDecimal.ONE.subtract(objective);

        BigDecimal observed = goodFraction(total, bad).orElseThrow();
        BigDecimal allowedEvents = allowedFraction.multiply(
            BigDecimal.valueOf(total)
        );
        BigDecimal remainingEvents = allowedEvents.subtract(
            BigDecimal.valueOf(bad)
        );
        BigDecimal usedPercent = BigDecimal.valueOf(bad)
            .divide(allowedEvents, 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"));

        BigDecimal recentBadFraction = new BigDecimal("0.01");
        BigDecimal recentBurnRate = recentBadFraction.divide(
            allowedFraction, 2, RoundingMode.HALF_UP
        );

        System.out.println("SLI=" + observed
            .multiply(new BigDecimal("100"))
            .setScale(3, RoundingMode.HALF_UP).toPlainString() + "%");
        System.out.println("allowedBadEvents="
            + allowedEvents.stripTrailingZeros().toPlainString());
        System.out.println("remainingBadEvents="
            + remainingEvents.stripTrailingZeros().toPlainString());
        System.out.println("budgetUsed="
            + usedPercent.setScale(1, RoundingMode.HALF_UP)
                .toPlainString() + "%");
        System.out.println("sloMet=" + (observed.compareTo(objective) >= 0));
        System.out.println("recentBurnRate=" + recentBurnRate.toPlainString());
        System.out.println("zeroTraffic="
            + (goodFraction(0, 0).isEmpty() ? "NO_DATA" : "MEASURED"));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```powershell
javac --release 21 -encoding UTF-8 SloBudgetDemo.java
java SloBudgetDemo
```

Stdout:

```text
SLI=99.970%
allowedBadEvents=2000
remainingBadEvents=1400
budgetUsed=30.0%
sloMet=true
recentBurnRate=10.00
zeroTraffic=NO_DATA
```

sloMet=true xét dữ liệu toàn cửa sổ có SLI 99,970%, cao hơn mục tiêu 99,9%. recentBurnRate=10.00 xét tỷ lệ lỗi gần đây 1%; đây là một đại lượng khác, không mâu thuẫn với việc toàn cửa sổ vẫn đạt. Mức 10 cũng chưa vượt ngưỡng 14,4 của quy tắc tiêu hao nhanh đã minh họa.

zeroTraffic=NO_DATA giữ khác biệt giữa không có yêu cầu và đạt 100%. BigDecimal giúp phép tính thập phân của ví dụ tránh sai số biểu diễn ở các mốc như 0,999. Khi xây công cụ thực tế, cần quy định thêm cách làm tròn, dữ liệu đến muộn và giới hạn mục tiêu; burn rate theo công thức trên cần ngân sách lớn hơn 0.

## 10. Kiểm tra thiết kế trước khi sử dụng

| Câu hỏi cần kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| SLI phản ánh đúng nhu cầu người dùng chưa? | Định nghĩa đối tượng, sự kiện tốt/xấu và điểm đo |
| SLO đã đầy đủ chưa? | Tỷ lệ mục tiêu, cửa sổ, phạm vi và người chịu trách nhiệm |
| Cảnh báo có dẫn đến hành động cụ thể không? | Điều kiện, mức độ và hướng điều tra rõ ràng |
| Actuator có đúng dữ liệu không? | Bộ đếm, nhãn route và bucket đã kiểm tra trên từng bản chạy |
| Không có yêu cầu được xử lý thế nào? | Trạng thái và chính sách riêng, không tự khẳng định khỏe |
| Mất dữ liệu được phát hiện không? | Kiểm tra thu thập và quan sát bổ sung |
| Triển khai nhiều instance có tính đúng không? | Cộng số sự kiện đúng trọng số, không trung bình percentile hoặc tỷ lệ tùy tiện |

Cần thử ít nhất các trường hợp: tất cả tốt, tất cả xấu, lỗi tăng đột ngột, phục hồi sau sự cố, lưu lượng rất thấp, mất số liệu, thiếu bucket ở một instance và khởi động lại bộ đếm. Việc tệp YAML hợp lệ chưa chứng minh cảnh báo đáp ứng đúng các tình huống đó.

## 11. Tự thực hành

1. Một mục tiêu nói 99% yêu cầu không quá 300 ms trong 30 ngày. Chỉ ra phần nào mô tả sự kiện tốt, phần nào là tỷ lệ mục tiêu và phần nào là cửa sổ.
2. Với 2.000.000 yêu cầu và SLO 99,9%, đổi số yêu cầu xấu trong chương trình thành 2.500. Giải thích SLI, ngân sách còn lại và trạng thái đạt mục tiêu.
3. Nếu một sự cố đã kết thúc nhưng SLI 30 ngày vẫn thấp hơn mục tiêu, vì sao cảnh báo lỗi đang diễn ra có thể hết trong khi đánh giá SLO vẫn không đạt?
4. Thay chính sách để HTTP 429 cũng là sự kiện xấu. Xác định những tử số, mô tả và truy vấn cần cập nhật đồng bộ.
5. Vì sao khai báo management.metrics.distribution.slo.http.server.requests=300ms chưa đủ để có SLO 99% và cảnh báo bảo vệ nó?

Bạn đã phân biệt đúng ba khái niệm khi có thể chỉ ra dữ liệu đang nói gì, mục tiêu yêu cầu gì và quy tắc nào quyết định lúc cần hành động, mà không dùng một con số để thay cho cả ba.
