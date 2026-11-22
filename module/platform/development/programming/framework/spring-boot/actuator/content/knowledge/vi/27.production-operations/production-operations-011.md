# Tổ chức quy trình chẩn đoán từ cảnh báo đến metrics, trace, log và chứng cứ liên quan

## 1. Quy trình chẩn đoán cần trả lời điều gì?

Khi hệ thống báo “thanh toán chậm”, người trực vận hành cần xác định người dùng bị ảnh hưởng ra sao, lỗi bắt đầu khi nào, nằm ở đâu và hành động nào có thể giảm tác động. Một biểu đồ đỏ hoặc một dòng lỗi chưa trả lời đủ các câu hỏi đó.

**Chẩn đoán là quá trình thu hẹp giả thuyết bằng chứng cứ có cùng phạm vi và thời gian.** Mỗi lần mở một công cụ phải phục vụ một câu hỏi cụ thể. Quy trình thường đi từ cảnh báo đến số liệu tổng hợp (metrics), dấu vết thực thi (trace), nhật ký (log), rồi đến chứng cứ về triển khai, tài nguyên hoặc hệ thống phụ thuộc. Có thể quay lại bước trước khi dữ liệu mới làm thay đổi giả thuyết.

Các thuật ngữ cần nắm:

| Thành phần | Câu hỏi chính | Giới hạn cần nhớ |
| --- | --- | --- |
| Cảnh báo | Điều kiện nào cần con người xử lý đã xảy ra? | Ngưỡng bị vượt không tự chỉ ra nguyên nhân |
| Metric | Mức độ, xu hướng và phạm vi ảnh hưởng là gì? | Số liệu tổng hợp không tái dựng đầy đủ từng yêu cầu |
| Trace | Một yêu cầu đã đi qua những thao tác nào, chờ ở đâu? | Chỉ thấy phần được đo đạc, thu thập và lưu giữ |
| Span | Một thao tác trong trace bắt đầu, kết thúc và liên hệ với thao tác khác thế nào? | Tên span hoặc thời lượng riêng lẻ chưa chứng minh nguyên nhân gốc |
| Log | Tại thời điểm cụ thể, mã đã ghi nhận sự kiện và lỗi gì? | Có thể thiếu, trùng, đến muộn hoặc mất ngữ cảnh |
| Chứng cứ bổ sung | Có thay đổi, giới hạn hay sự kiện nào giải thích được biểu hiện? | Quan hệ cùng thời điểm vẫn cần được kiểm chứng |
| Runbook | Ai kiểm tra gì, bằng cách nào, và khi nào chuyển hướng? | Phải gắn với hệ thống thực tế, có người chịu trách nhiệm |

Trace gồm các span có quan hệ cha–con hoặc liên kết; nó giúp thấy đường đi của một hoạt động qua các thành phần đã được gắn đo đạc. Xem [mô hình trace của OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/).

Một quy trình tốt phân biệt ba mức kết luận:

- **Quan sát:** “Tỷ lệ HTTP 5xx của checkout-api tăng trong cửa sổ 5 phút.”
- **Giả thuyết:** “Các yêu cầu có thể đang chờ dịch vụ thanh toán.”
- **Kết luận có căn cứ:** “Trong các trace lỗi đã kiểm tra, thời gian chờ tập trung ở lời gọi payment; log cùng trace ghi nhận timeout; phía payment có chứng cứ hàng đợi tăng trong đúng khoảng thời gian đó.”

Không đổi “có thể” thành “đã chứng minh” chỉ vì có một ảnh chụp màn hình.

## 2. Vai trò của Actuator trong chuỗi quan sát

Trong ứng dụng Spring Boot, Actuator cung cấp các điểm kiểm tra của chính tiến trình ứng dụng. Với bộ đo đạc phù hợp, Micrometer tạo metrics; bộ truy vết và nơi tiếp nhận trace phục vụ việc tìm đường đi của yêu cầu; hệ thống log tập trung lưu các sự kiện. Dashboard và công cụ cảnh báo khai thác dữ liệu đã được thu thập.

Luồng dữ liệu khác với luồng điều tra:

```text
Luồng dữ liệu:
Ứng dụng → bộ thu metrics → kho chuỗi thời gian → dashboard/cảnh báo
         → bộ xuất trace → kho trace
         → đầu ra log → bộ thu log → kho log

Luồng điều tra:
Cảnh báo → xác minh ảnh hưởng → metrics → trace đại diện → log liên quan
         → chứng cứ triển khai/tài nguyên/phụ thuộc
         → giảm tác động → kiểm tra phục hồi → điều tra tiếp
```

Actuator không tự biến thành kho lưu metrics dài hạn, máy chủ trace hoặc hệ thống tìm kiếm log. Endpoint `metrics` giúp xem các meter của một instance; endpoint `prometheus` xuất dữ liệu để Prometheus thu thập và cần `micrometer-registry-prometheus`. Việc bật một endpoint, công bố nó qua HTTP và cấp quyền truy cập là những điều kiện khác nhau. Xem [Actuator Endpoints cho Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`/actuator/health` trả về `UP` chỉ cho biết kết quả những kiểm tra sức khỏe đang được cấu hình. Nó không chứng minh mọi luồng nghiệp vụ đạt mục tiêu độ trễ, không có lỗi hoặc tất cả người dùng truy cập thành công. Health là một chứng cứ trong quy trình, không phải phán quyết duy nhất.

## 3. Chuẩn bị để các công cụ nối được với nhau

Trước sự cố, thống nhất bộ thông tin dùng khi chuyển giữa các nguồn:

| Thông tin | Cách dùng trong điều tra |
| --- | --- |
| Tên dịch vụ, môi trường, vùng triển khai | Tránh ghép metrics production với log staging hoặc nhầm vùng |
| Instance/pod và thời gian tồn tại | Phân biệt bản sao lỗi, bản sao đã thay thế và tiến trình vừa khởi động |
| Phiên bản ứng dụng, mã build, thời điểm triển khai | So sánh trước–sau và nhóm phiên bản |
| Tuyến nghiệp vụ, phương thức, loại kết quả | Khoanh vùng thao tác đang ảnh hưởng người dùng |
| Thời gian có múi giờ | Giữ cùng cửa sổ khi đổi dashboard, kho trace và kho log |
| Trace ID, span ID khi có | Nối từ một hoạt động sang span và các log đúng ngữ cảnh |
| Mã sự cố | Gom câu hỏi, hành động, chứng cứ và người chịu trách nhiệm |

Dùng UTC hoặc ghi rõ độ lệch múi giờ; phân biệt thời điểm sự kiện với thời điểm dữ liệu được tiếp nhận. Log đến muộn không có nghĩa sự kiện vừa xảy ra. Máy lệch đồng hồ có thể làm thứ tự giữa các dịch vụ trông vô lý; khi nghi ngờ, ghi nhận sai lệch thay vì ép các mốc thời gian khớp nhau.

Không bắt mọi nguồn dùng nhãn hoàn toàn giống nhau. Ví dụ `service.name` trong hệ thống trace có thể tương ứng với `application` trong metrics và `service` trong log. Runbook cần chỉ rõ cách ánh xạ thực tế. Không giả định Prometheus tự thêm `env`, `version` hoặc tên ứng dụng nếu pipeline chưa cấu hình chúng.

Giữ số lượng tổ hợp nhãn metric (cardinality) có kiểm soát. Tên dịch vụ, phương thức và mẫu tuyến như `/orders/{id}` có thể dùng để phân nhóm. Trace ID, mã đơn hàng, email hoặc URL chứa ID biến đổi không nên trở thành nhãn metric thông thường. Những khóa riêng cho từng yêu cầu phù hợp hơn với log/trace có chính sách dữ liệu tương ứng.

## 4. Bước đầu: xác minh cảnh báo và mức ảnh hưởng

Khi nhận cảnh báo, lưu ngay biểu thức truy vấn, điều kiện, khoảng đánh giá, thời gian bắt đầu và đường dẫn hướng dẫn xử lý. “Độ trễ cao” không đủ rõ nếu thiếu tuyến, đơn vị, phân vị và cửa sổ tính.

Thực hiện theo trình tự:

1. **Xác minh đúng đối tượng:** dịch vụ, môi trường, vùng và tuyến nghiệp vụ nào?
2. **Xác minh tín hiệu còn mới:** bộ thu có đang nhận dữ liệu không, có thiếu mẫu, mất target hoặc chậm tiếp nhận không?
3. **Xác minh ảnh hưởng:** tỷ lệ thành công, số yêu cầu, độ trễ phía người dùng hoặc tại gateway thay đổi thế nào?
4. **Đặt phạm vi thời gian:** chọn một khoảng trước sự cố và một khoảng đang lỗi; giữ chúng khi chuyển công cụ.
5. **Phân công:** một người điều phối, người kiểm tra ứng dụng, người kiểm tra phụ thuộc khi mức ảnh hưởng cần nhiều người.
6. **Ghi giả thuyết đầu tiên cùng phép kiểm tra tiếp theo:** chưa cần tuyên bố nguyên nhân.

Ví dụ một cảnh báo có thể kiểm tra được:

```text
Dịch vụ: checkout-api
Môi trường: production, vùng: vn-a
Triệu chứng: p95 POST /checkout > 1 giây, kéo dài 10 phút
Cửa sổ tính p95: 5 phút
Cần đối chiếu: lưu lượng, tỷ lệ lỗi, độ mới dữ liệu
Khoảng điều tra: 09:45–10:15 UTC
```

Các giá trị này là giả định của bài học, không phải ngưỡng production dùng chung. Ngưỡng thực tế phải dựa trên mục tiêu chất lượng dịch vụ (SLO), lưu lượng và tác động nghiệp vụ.

Khung bốn tín hiệu thường hữu ích là độ trễ, lưu lượng, lỗi và mức bão hòa tài nguyên. Đây là cách đặt câu hỏi tổng quát; không phải cứ CPU cao là phải đánh thức người trực. Xem [Monitoring Distributed Systems của Google SRE](https://sre.google/sre-book/monitoring-distributed-systems/).

Nếu metrics biến mất và cảnh báo độ trễ chuyển sang “không có dữ liệu”, chưa được kết luận hệ thống đã phục hồi. Cần phân biệt lỗi ứng dụng với lỗi đường thu thập quan sát.

## 5. Dùng metrics để thu hẹp phạm vi

### 5.1. Từ toàn dịch vụ đến nhóm bất thường

Đầu tiên xem số yêu cầu, tỷ lệ lỗi và độ trễ trên cùng phạm vi. Sau đó tách theo tuyến, vùng, instance hoặc phiên bản để tìm nơi khác biệt.

Các câu hỏi có thứ tự:

- Tất cả tuyến đều chậm hay chỉ một tuyến?
- Tất cả instance đều lỗi hay chỉ một nhóm?
- Lưu lượng tăng, giảm hoặc phân bố lại từ thời điểm nào?
- Lỗi 5xx tăng cùng độ trễ hay độ trễ tăng trong khi vẫn trả 2xx?
- Có dấu hiệu bão hòa như hàng đợi tăng, thiếu kết nối, chờ luồng hoặc GC kéo dài không?
- Số liệu phía gateway và phía ứng dụng có cùng xu hướng không?

Chênh lệch giữa gateway và ứng dụng có giá trị: yêu cầu có thể bị từ chối trước khi vào ứng dụng, bị timeout ở proxy, hoặc đang kẹt nên chưa xuất hiện trong thống kê yêu cầu đã hoàn thành. Cũng có thể hai phía đang đếm theo phạm vi khác nhau. Kiểm tra định nghĩa trước khi quy lỗi cho một thành phần.

### 5.2. Ba truy vấn dùng để đặt câu hỏi

Giả sử Prometheus đã thu thập bộ đếm HTTP và **classic histogram** của ứng dụng. Ví dụ dùng nhãn `job="checkout-api"`, `env="prod"`; đây là hợp đồng của bộ dữ liệu ví dụ, không phải nhãn mặc định được đảm bảo. Khi dùng thực tế, thêm phạm vi cluster/vùng cần thiết và kiểm tra tên metric, nhãn trong dữ liệu xuất.

Lưu lượng yêu cầu hoàn thành mỗi giây, theo mẫu tuyến:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="checkout-api", env="prod"
  }[5m])
)
```

Tỷ lệ 5xx trên tổng yêu cầu hoàn thành của toàn dịch vụ:

```promql
sum(rate(http_server_requests_seconds_count{
  job="checkout-api", env="prod", status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="checkout-api", env="prod"
}[5m]))
```

Kết quả `0.04` nghĩa là 4%, không phải 0,04%. Với hệ thống không tạo chuỗi 5xx khi chưa từng có lỗi, tử số có thể rỗng; với lưu lượng bằng 0, phép chia không cho tỷ lệ có ý nghĩa. Dashboard/rule cần xử lý rõ trạng thái không dữ liệu và không lưu lượng, kiểm tra sức khỏe bộ thu; không tô xanh mọi kết quả trống bằng cách thay tất cả thành 0.

p95 theo tuyến, gộp các instance:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="checkout-api", env="prod"
    }[5m])
  )
)
```

`rate` tính tốc độ tăng theo giây của bộ đếm và xử lý reset bộ đếm; phải tính trên từng chuỗi trước khi cộng. Với classic histogram, giữ nhãn `le` khi cộng bucket. `histogram_quantile` cho giá trị ước lượng theo bucket, ở đây đơn vị là giây. Các biểu thức dựa trên [quy tắc hàm truy vấn của Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Chỉ dùng truy vấn thứ ba khi có chuỗi `_bucket`. Không lấy trung bình p95 của từng instance để gọi đó là p95 toàn dịch vụ. Ví dụ một instance phục vụ 10 yêu cầu và một instance phục vụ 10.000 yêu cầu không có trọng số tương đương. Histogram cho phép gộp phân bố trước khi ước lượng phân vị; phân vị tính sẵn phía ứng dụng không gộp theo cách đó. Xem [Histograms and Percentiles của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

Phân vị trên một cửa sổ ít yêu cầu có thể biến động mạnh. Luôn đặt số lượng yêu cầu cạnh biểu đồ độ trễ. Cửa sổ dài làm mượt nhưng có thể che đợt lỗi ngắn; cửa sổ quá ngắn so với chu kỳ thu thập có thể thiếu mẫu.

### 5.3. Kiểm tra Actuator tại một instance

Ví dụ dưới đây là mảnh cấu hình cho **ứng dụng web Spring Boot 3.3 có sẵn**, đã có `spring-boot-starter-actuator` và `micrometer-registry-prometheus`. Nó phục vụ phòng thử nghiệm trên cùng máy, không phải một ứng dụng độc lập hoặc cấu hình công bố production.

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Sau khi ứng dụng đã nhận yêu cầu web, dùng Bash với `curl` từ cùng máy:

```bash
curl -fsS 'http://127.0.0.1:9091/actuator/health'
curl -fsS 'http://127.0.0.1:9091/actuator/metrics/http.server.requests'
curl -fsS 'http://127.0.0.1:9091/actuator/prometheus'
```

Nếu ứng dụng có bảo mật, cần dùng cơ chế xác thực được phép của phòng thử nghiệm; các lệnh không tự vượt xác thực. Khi chạy trong container, địa chỉ loopback thuộc không gian mạng của container, không mặc nhiên là máy đang mở terminal.

Endpoint metrics dùng tên `http.server.requests`; tên được xuất sang Prometheus có thể được chuẩn hóa thành dạng dấu gạch dưới cùng đơn vị và hậu tố. Cấu hình histogram tạo điều kiện tính phân vị tổng hợp; hãy xác minh dữ liệu xuất thực tế thay vì đoán từ tên property. Xem [Metrics cho Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Đây là các thao tác đọc dữ liệu đang sống nên không có stdout cố định: số đo phụ thuộc tải, thư viện và thời điểm truy vấn. Kết quả mong đợi là phản hồi health dạng JSON, mô tả meter dạng JSON và dữ liệu metrics dạng văn bản; 401/403 cho biết cần kiểm tra quyền, còn 404 cần kiểm tra endpoint, đường dẫn, cổng và dependency.

Không dùng một lần gọi `/actuator/metrics` để thay cho lịch sử 5 phút trong Prometheus. Một instance vừa khởi động hoặc chưa xử lý tuyến đó có thể chưa có meter cần tìm; việc này khác với “tuyến không bao giờ lỗi”. Cũng không suy ra cổng nghiệp vụ hoạt động chỉ vì cổng quản trị riêng vẫn trả lời.

## 6. Chọn trace để kiểm tra một đường đi cụ thể

Sau metrics, câu hỏi phải hẹp hơn: “Vì sao POST /checkout ở vùng vn-a chậm trong 10:00–10:10 UTC?” Dùng chính khoảng thời gian và phạm vi đó để tìm trace, thay vì mở trace mới nhất một cách ngẫu nhiên.

Chọn một nhóm trace đại diện:

- Yêu cầu lỗi để thấy đường đi dẫn tới thất bại.
- Yêu cầu chậm nhưng thành công để phát hiện chờ đợi chưa vượt timeout.
- Yêu cầu bình thường cùng tuyến làm mẫu đối chiếu.
- Nếu nghi ngờ một instance hoặc phiên bản, so sánh cả nhóm bị nghi ngờ và nhóm còn lại.

Khi đọc một trace, kiểm tra thao tác đầu vào, quan hệ span, khoảng chờ và lời gọi phụ thuộc. Chú ý đường thực thi quyết định thời gian hoàn thành của yêu cầu. Các span chạy song song có thời gian chồng lấp, vì vậy không cộng mọi thời lượng span để suy ra độ trễ đầu cuối.

Ví dụ minh họa một yêu cầu chậm:

| Thao tác | Thời lượng quan sát | Câu hỏi tiếp theo |
| --- | --- | --- |
| POST /checkout | 2.400 ms | Người dùng chờ ở đoạn nào? |
| Đọc giỏ hàng | 35 ms | Có khác thường so với yêu cầu bình thường không? |
| HTTP client gọi payment | 2.200 ms | Chờ kết nối, mạng, xử lý phía payment hay thử lại? |
| Ghi kết quả | 40 ms | Thao tác có hoàn tất hay bị hủy? |

Đây là một trace giả định. Thời gian span HTTP client không đồng nghĩa toàn bộ 2.200 ms là CPU của payment. Nó có thể bao gồm thời gian chờ và các giai đoạn khác tùy cách đo đạc. Cần kiểm tra span phía nhận, log và số liệu của phụ thuộc.

Một span lớn cũng có thể đang bao trùm nhiều thao tác chưa được tách đo. Khi đó kết luận hợp lệ là “đã khoanh vùng vào đoạn gọi payment”, chưa phải “đã biết chính xác câu lệnh gây lỗi”.

### Khi không tìm được trace

Tách những khả năng sau:

1. Yêu cầu không được chọn lấy mẫu.
2. Bộ xuất hoặc bộ tiếp nhận trace bị lỗi, quá tải hay đang chậm.
3. Trace đã hết hạn lưu giữ.
4. Bộ lọc sai dịch vụ, múi giờ, vùng hoặc khoảng thời gian.
5. Ngữ cảnh truy vết bị mất khi qua HTTP client, hàng đợi hoặc tác vụ bất đồng bộ.
6. Đoạn cần xem chưa được gắn đo đạc.

Với Spring Boot 3.3, việc liên kết log với trace cần hạ tầng Micrometer Tracing phù hợp; Actuator đơn lẻ không tạo đầy đủ pipeline truy vết. Spring Boot có property `management.tracing.sampling.probability` điều khiển xác suất lấy mẫu của cấu hình tương ứng. Dùng các builder HTTP client do Spring Boot tự cấu hình để giữ hỗ trợ truyền ngữ cảnh; tự tạo client có thể làm đứt đường đi. Xem [Tracing cho Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Không tăng lấy mẫu lên 100% cho toàn production chỉ để “chắc chắn thấy lỗi”. Nếu cần thay đổi, phải xác định phạm vi, thời hạn, khả năng tiếp nhận dữ liệu và cách hoàn nguyên. Không có trace của một lỗi không chứng minh lỗi đó chưa từng xảy ra; tiếp tục bằng metrics, log và chứng cứ khác.

## 7. Từ trace sang log: tìm ngữ cảnh, không chỉ tìm chữ ERROR

Dùng trace ID đã chọn để tìm log trong đúng môi trường và khoảng thời gian. Thêm span ID khi cần thu hẹp một thao tác, nhưng không chỉ lọc một span nếu đang cần xem toàn bộ hành trình qua nhiều dịch vụ.

Các trường hữu ích gồm thời gian sự kiện, tên dịch vụ, instance, phiên bản, mức log, sự kiện nghiệp vụ, trace ID, span ID và loại lỗi. Giữ nguyên stack trace có liên quan nếu được phép thu thập; một thông điệp “failed” thường không đủ.

Ví dụ sau là **định dạng log do ứng dụng giả định tự thiết kế**, không phải JSON mặc định của Spring Boot 3.3:

```json
[
  {
    "timestamp": "2026-01-15T10:03:21.100Z",
    "service": "checkout-api",
    "instance": "checkout-2",
    "version": "1.8.2",
    "level": "WARN",
    "event": "payment_call_failed",
    "traceId": "0123456789abcdef0123456789abcdef",
    "spanId": "1111111111111111",
    "errorType": "ReadTimeout",
    "elapsedMs": 2200
  },
  {
    "timestamp": "2026-01-15T10:03:21.110Z",
    "service": "checkout-api",
    "instance": "checkout-2",
    "version": "1.8.2",
    "level": "ERROR",
    "event": "checkout_failed",
    "traceId": "0123456789abcdef0123456789abcdef",
    "spanId": "2222222222222222",
    "httpStatus": 503
  }
]
```

Hai sự kiện cùng trace cho thấy lời gọi payment thất bại và checkout sau đó trả lỗi trong ví dụ. Hai span ID khác nhau không phải mất liên kết: một trace có thể chứa nhiều span. Cũng không được đếm hai dòng này thành hai yêu cầu lỗi độc lập.

Đọc theo câu hỏi:

- Lỗi đầu tiên có liên quan nằm ở đâu, hay các dòng sau chỉ là hậu quả?
- Timeout xảy ra khi chờ lấy kết nối, khi kết nối hay khi chờ phản hồi?
- Có thử lại không, bao nhiêu lần, có làm tăng tải lên phụ thuộc không?
- Lỗi thuộc một instance hay nhiều instance?
- Log bình thường của cùng tuyến khác ở điểm nào?

Số dòng ERROR không thay thế tỷ lệ yêu cầu thất bại. Một ngoại lệ có thể được ghi ở nhiều tầng; ngược lại một lần trả 5xx có thể không có log ERROR nào.

Nếu log không có trace ID, thu hẹp bằng thời gian, dịch vụ, instance và mã tương quan đã được thiết kế trước. Ghi rõ đây là phép ghép yếu hơn, không tuyên bố hai dòng cùng yêu cầu chỉ vì chúng cách nhau vài mili giây. Với tác vụ bất đồng bộ, kiểm tra cách truyền và khôi phục ngữ cảnh thay vì chỉ thêm một chuỗi ID tùy ý vào thông điệp.

Khi thu thập log, không ghi token, mật khẩu, dữ liệu thẻ hoặc toàn bộ body nhạy cảm để đổi lấy khả năng chẩn đoán. Chỉ lưu trường cần thiết, che dữ liệu theo chính sách và giới hạn quyền truy cập hồ sơ sự cố.

## 8. Bổ sung chứng cứ theo giả thuyết

Chỉ thu chứng cứ có khả năng phân biệt các giả thuyết. Một gói dữ liệu lớn nhưng không rõ nguồn, thời gian hoặc instance rất khó dùng.

| Giả thuyết | Chứng cứ nên đối chiếu | Điều chưa thể kết luận từ một dấu hiệu |
| --- | --- | --- |
| Lỗi gắn với bản triển khai mới | Thời điểm rollout, phiên bản theo instance, thay đổi cấu hình, nhóm chưa nâng cấp | Deploy xảy ra gần sự cố chưa đủ chứng minh deploy gây lỗi |
| Phụ thuộc phản hồi chậm | Span client/server, timeout, hàng đợi và tài nguyên phía phụ thuộc | Client chờ lâu không tự chứng minh server dùng CPU cao |
| Thiếu kết nối cơ sở dữ liệu | Số kết nối hoạt động/chờ, thời gian lấy kết nối, truy vấn và khóa phía DB | Pool đầy có thể là hậu quả truy vấn chậm hoặc giữ kết nối quá lâu |
| Luồng bị chặn hoặc tranh chấp khóa | Nhiều thread dump cách nhau theo kế hoạch, trạng thái luồng, số liệu hàng đợi | Một ảnh chụp thấy WAITING không tự chứng minh deadlock |
| Bộ nhớ/GC gây gián đoạn | Đường bộ nhớ, thời gian GC, restart/OOM và log liên quan | Bộ nhớ đang cao không tự chứng minh rò rỉ |
| Lỗi mạng hoặc định tuyến | Chứng cứ gateway, DNS/TLS, connect timeout, thay đổi route | Không thấy log ứng dụng không có nghĩa yêu cầu chưa được gửi |
| Đường thu thập quan sát bị lỗi | Trạng thái scrape/export, độ trễ tiếp nhận, dung lượng kho, bộ lọc | Thiếu telemetry không đồng nghĩa không có ảnh hưởng |

Actuator có thể hỗ trợ bằng `threaddump`, `loggers`, `info` hoặc các endpoint chẩn đoán khác khi đã được cấu hình và cấp quyền phù hợp. Không mặc định mọi endpoint đều tồn tại, có dữ liệu hoặc được phép truy cập. Thông tin build trong `info` cũng cần nguồn tạo dữ liệu tương ứng.

Thread dump, heap dump và việc đổi mức log có chi phí và độ nhạy cảm khác nhau. Heap dump có thể lớn, gây áp lực tài nguyên và chứa dữ liệu trong bộ nhớ. Không tải dump hàng loạt trên hệ thống đang suy giảm nếu chưa xác định được câu hỏi cần trả lời. Ưu tiên dữ liệu sẵn có; thu thập bổ sung theo quy trình vận hành của hệ thống.

Nếu cần DEBUG tạm thời, giới hạn đúng logger, instance và thời gian, ghi lại mức cũ và người hoàn nguyên. Kiểm tra dung lượng, độ trễ và nguy cơ lộ dữ liệu. Việc tăng log toàn ứng dụng có thể làm sự cố nặng thêm và tạo nhiễu.

## 9. Ghi hồ sơ chứng cứ có thể kiểm tra lại

Mỗi chứng cứ nên đi kèm:

- Nguồn và phạm vi: dịch vụ, môi trường, vùng, instance, phiên bản.
- Khoảng thời gian, múi giờ, thời điểm lấy dữ liệu.
- Truy vấn và các bộ lọc; đơn vị, cửa sổ tổng hợp nếu là metrics.
- Đường dẫn truy cập hoặc bản trích đã được bảo vệ; thời hạn lưu giữ.
- Quan sát trực tiếp, cách diễn giải và điều còn chưa biết.
- Người thu thập, hành động liên quan và thời điểm hành động.

Ảnh biểu đồ giúp trao đổi nhanh nhưng nên giữ cả truy vấn và khoảng thời gian. Nếu link trỏ tới “15 phút gần nhất”, người mở lại ngày mai sẽ thấy dữ liệu khác. Dùng khoảng thời gian cố định hoặc lưu bản trích phù hợp, đồng thời bảo toàn quyền truy cập.

Ví dụ một ghi nhận đủ rõ:

```text
Sự cố: INC-042
Phạm vi: checkout-api, production, vn-a, POST /checkout
Khoảng quan sát: 2026-01-15 10:00–10:10 UTC
Quan sát: tỷ lệ 5xx xấp xỉ 5%; p95 xấp xỉ 2,4 giây
Nguồn: truy vấn metrics lưu trong hồ sơ, nhóm theo tuyến
Trace mẫu: 0123456789abcdef0123456789abcdef
Quan sát trong mẫu: span gọi payment mất 2.200 ms rồi timeout
Log liên quan: payment_call_failed và checkout_failed cùng trace
Giả thuyết: thời gian chờ payment góp phần làm checkout thất bại
Chưa biết: nguyên nhân chậm bên trong payment; mức đại diện của mẫu
Kiểm tra tiếp: đối chiếu hàng đợi và thay đổi cấu hình phía payment
```

Các con số là dữ liệu minh họa. “Xấp xỉ” được dùng cho số liệu dashboard/ước lượng; không biến chúng thành phép đếm chính xác nếu nguồn không cung cấp độ chính xác đó.

## 10. Giảm tác động và xác minh phục hồi

Không cần chờ biết nguyên nhân gốc mới giảm ảnh hưởng nghiêm trọng. Tuy nhiên, mỗi hành động cần một giả thuyết, phạm vi, người thực hiện và điều kiện hoàn nguyên.

Ví dụ: nếu chứng cứ chỉ ra một phiên bản mới gây lỗi và phiên bản cũ vẫn tương thích với dữ liệu hiện tại, có thể chọn rollback theo quy trình triển khai. Nếu một phụ thuộc quá tải, biện pháp có thể là giảm tải có kiểm soát hoặc tạm ngừng chức năng không thiết yếu. Việc chọn biện pháp phụ thuộc kiến trúc và quyền vận hành thực tế.

Không coi tăng timeout hoặc tăng pool là cách sửa mặc định. Timeout dài hơn có thể giữ tài nguyên lâu hơn; thêm kết nối có thể tăng áp lực lên DB; thử lại đồng loạt có thể khuếch đại tải. Đánh giá cả tác động dây chuyền và tính an toàn nghiệp vụ, đặc biệt với thao tác có thể tạo giao dịch lặp.

Trước một thay đổi, lưu phần chứng cứ nhẹ có nguy cơ mất nếu điều kiện cho phép. Không trì hoãn cứu hệ thống chỉ để có bộ hồ sơ hoàn hảo. Ghi rõ thời điểm restart, rollback hoặc chuyển tải vì các hành động này cũng làm thay đổi dữ liệu quan sát.

Sau hành động, xác minh trên nhiều mặt:

1. Tỷ lệ lỗi và độ trễ trở lại mức chấp nhận trong cửa sổ quan sát đã thống nhất.
2. Lưu lượng hoặc phép kiểm tra nghiệp vụ cho thấy yêu cầu vẫn được phục vụ, không chỉ là không còn người dùng.
3. Hàng đợi, backlog và tài nguyên ổn định; không chuyển vấn đề sang dịch vụ khác.
4. Bộ thu metrics/log/trace vẫn hoạt động, nên trạng thái “hết cảnh báo” có ý nghĩa.
5. Giao dịch dở dang được đối soát theo quy trình nghiệp vụ.
6. Các thay đổi chẩn đoán tạm thời được hoàn nguyên hoặc có người nhận theo dõi.

Phục hồi sau restart chỉ chứng minh triệu chứng đã giảm trong hoàn cảnh mới. Nó chưa giải thích được vì sao hệ thống suy giảm. Tách thời điểm khôi phục dịch vụ khỏi kết luận nguyên nhân gốc.

## 11. Tình huống xuyên suốt: checkout chậm vì chờ payment

Toàn bộ tình huống sau là giả định để luyện tổ chức điều tra.

### 11.1. Nhận cảnh báo và khoanh vùng

Lúc 10:05 UTC, cảnh báo báo p95 của POST /checkout vượt 1 giây. Người trực mở khoảng 09:45–10:15 UTC, xác nhận dữ liệu mới và kiểm tra lưu lượng thực tế.

| Dữ liệu trong cửa sổ đang lỗi | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| Số yêu cầu hoàn thành được đối chiếu trong nguồn đếm | 30.000 | Cần biết mẫu số trước khi nói tỷ lệ |
| Số yêu cầu 5xx trong cùng phạm vi đếm | 1.500 | Tỷ lệ là 1.500 / 30.000 = 5% |
| p95 POST /checkout | Khoảng 2,4 giây | Phần đuôi phân bố chậm hơn bình thường |
| GET /catalog | Gần mức bình thường | Phạm vi có thể tập trung vào checkout |
| CPU checkout | Không tăng rõ | Chưa có căn cứ coi CPU checkout là nút thắt |
| Nhiều instance checkout | Cùng xu hướng xấu | Cần kiểm tra thành phần dùng chung |

Các số đếm trong bảng được giả định là đã đối chiếu trong cùng khoảng; không yêu cầu `rate` hay `increase` luôn tái hiện đúng các số nguyên đó.

### 11.2. Nối trace, log và phía phụ thuộc

Người trực chọn 10 trace lỗi, 5 trace chậm thành công và 5 trace bình thường. Trong 8/10 trace lỗi đã chọn, phần chờ đáng kể nằm ở lời gọi payment. Đây là đặc điểm của **mẫu được chọn**, không được đổi thành tuyên bố “80% mọi yêu cầu đều lỗi tại payment”.

Log cùng trace ghi nhận timeout. Vì vậy nhóm kiểm tra thêm payment thay vì tăng pool checkout ngay lập tức.

Phía payment cung cấp hai chứng cứ mới trong đúng khoảng thời gian:

- Hàng đợi xử lý tăng từ 10:00 UTC, trong khi tải đầu vào gần mức trước đó.
- Một thay đổi cấu hình lúc 09:59 UTC giảm số tác vụ xử lý đồng thời từ 32 xuống 8.

Nhóm đặt giả thuyết: năng lực xử lý giảm làm hàng đợi tăng, kéo dài thời gian chờ payment và gây timeout ở checkout. Để kiểm tra, họ so sánh với cấu hình đã triển khai, biểu đồ hàng đợi và khoảng thời gian khỏe trước sự cố; đồng thời xác minh không có dấu hiệu khác đang mâu thuẫn.

### 11.3. Hành động và kết luận có giới hạn

Theo quy trình đã được cho phép trong tình huống, nhóm hoàn nguyên riêng thay đổi cấu hình payment, ghi mốc 10:12 UTC và theo dõi quá trình thoát hàng đợi.

Sau đó hàng đợi giảm, p95 checkout và tỷ lệ 5xx trở về mức nền trong khi lưu lượng vẫn tương đương. Chuỗi chứng cứ này **ủng hộ mạnh** giả thuyết giảm năng lực xử lý là yếu tố gây sự cố. Hồ sơ vẫn cần giải thích vì sao cấu hình sai được đưa vào, kiểm thử nào thiếu và việc có thay đổi đồng thời nào khác hay không.

Kết luận hữu ích là một chuỗi có thể kiểm tra: thay đổi cấu hình → giảm năng lực xử lý → tăng thời gian chờ → timeout ở checkout. “Payment có vấn đề” quá chung; “đã rollback nên chắc chắn tìm được mọi nguyên nhân” lại khẳng định quá mức.

## 12. Runbook ngắn cho cùng loại cảnh báo

Một runbook áp dụng cho tình huống trên có thể tổ chức như sau:

| Giai đoạn | Việc làm | Điều kiện chuyển bước |
| --- | --- | --- |
| Tiếp nhận | Ghi dịch vụ, vùng, tuyến, ngưỡng, thời gian và người điều phối | Đã xác định đúng cảnh báo và phạm vi |
| Xác minh | Kiểm tra độ mới telemetry, lưu lượng, lỗi và độ trễ | Phân biệt được ảnh hưởng thật với lỗi quan sát |
| Khoanh vùng | So sánh tuyến, instance, phiên bản và gateway | Có một vài giả thuyết cụ thể |
| Xem trace | Chọn mẫu lỗi, chậm và bình thường trong cùng cửa sổ | Đã xác định đoạn cần kiểm tra sâu hoặc ghi rõ thiếu trace |
| Xem log | Tìm theo trace ID và phạm vi; đọc chuỗi nguyên nhân/hậu quả | Có sự kiện hoặc loại lỗi cần đối chiếu |
| Bổ sung chứng cứ | Kiểm tra triển khai, cấu hình, hàng đợi hoặc phụ thuộc theo giả thuyết | Có căn cứ chọn hành động hoặc bác bỏ giả thuyết |
| Giảm tác động | Thực hiện phương án được phép, ghi thời điểm và cách hoàn nguyên | Đã triển khai biện pháp và biết cách đánh giá |
| Xác minh | Kiểm tra chất lượng phục vụ, tải, backlog và pipeline quan sát | Đạt điều kiện ổn định đã thống nhất |
| Bàn giao | Lưu hồ sơ, phần chưa biết, người theo dõi và việc hoàn nguyên | Người nhận nắm được việc tiếp theo |

Nếu tác động tăng nhanh hoặc vượt năng lực người trực, chuyển ngay tới đầu mối vận hành/phụ thuộc đã quy định. Không dành quá lâu cho một giả thuyết mà không có chứng cứ mới; đặt giới hạn thời gian kiểm tra phù hợp mức khẩn cấp và cập nhật hồ sơ khi đổi hướng.

## 13. Tự thực hành và kiểm tra cách suy luận

### Bài tập

Dùng dữ kiện giả định sau, không cần gây sự cố trên hệ thống thật:

- Cửa sổ quan sát 14:00–14:10 UTC có 12.000 yêu cầu hoàn thành, 240 yêu cầu 5xx.
- p95 tăng ở POST /checkout; các tuyến đọc gần như ổn định.
- Trace có sẵn của một yêu cầu lỗi dành phần lớn thời gian cho lời gọi payment.
- Log cùng trace ghi nhận timeout nhưng chưa có chứng cứ phía payment.
- Một instance vừa khởi động lại và có ít dữ liệu lịch sử.
- Dashboard không tìm thấy trace của một yêu cầu lỗi khác.

Hãy viết một ghi nhận điều tra gồm tỷ lệ lỗi, điều đã quan sát, giả thuyết, điều chưa biết và phép kiểm tra tiếp theo. Sau đó giải thích vì sao chưa nên kết luận “payment hết CPU” hoặc “yêu cầu không có trace là yêu cầu thành công”.

### Hướng đối chiếu

Tỷ lệ lỗi là `240 / 12.000 = 0,02 = 2%` trong phạm vi đếm đã cho. Quan sát về trace chỉ cho biết một yêu cầu đang chờ ở đường gọi payment. Giả thuyết có thể là phụ thuộc chậm, chờ kết nối hoặc vấn đề mạng; chưa có dữ liệu để chọn riêng giả thuyết CPU.

Bước tiếp theo hợp lý là chọn thêm mẫu chậm/bình thường, đối chiếu metrics và log phía payment, kiểm tra thời điểm triển khai và độ mới dữ liệu. Instance vừa restart cần được phân biệt với instance hoạt động suốt cửa sổ; không so bộ đếm tích lũy của chúng như thể cùng thời gian sống.

Yêu cầu không có trace có thể nằm ngoài mẫu hoặc thiếu dữ liệu trong pipeline. Giữ thông tin thiếu đó trong hồ sơ và dùng các nguồn còn lại. Nếu quyết định giảm tác động, nêu biện pháp cụ thể cùng điều kiện xác minh, không tuyên bố đã biết nguyên nhân gốc.

Một bài điều tra đạt yêu cầu khi người khác có thể lần lại từ cảnh báo tới truy vấn, mẫu trace, log và chứng cứ bổ sung; đồng thời nhận ra rõ đâu là dữ kiện, đâu là giả thuyết và vì sao hành động được chọn.
