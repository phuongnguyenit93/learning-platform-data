# Xử lý tên chỉ số hoặc tag khác nhau giữa metrics endpoint và exporter

## 1. Vì sao cùng một phép đo lại có nhiều cách gọi?

Bạn thấy `http.server.requests` trong `/actuator/metrics`, nhưng truy vấn tên đó trong Prometheus không ra dữ liệu. Hoặc metrics endpoint có tag `order.type`, còn dữ liệu xuất ra dùng label `order_type`. Đây có thể là chuyển đổi bình thường, không phải ứng dụng đã đánh mất phép đo.

**Tên meter trong Micrometer và tên chuỗi dữ liệu ở hệ thống giám sát thuộc hai lớp biểu diễn khác nhau.** Khi chẩn đoán, cần xác định tên và nhãn ở từng điểm, thay vì lấy tên nhìn thấy ở một công cụ áp thẳng vào công cụ khác.

Các khái niệm cần phân biệt:

| Khái niệm | Vai trò |
| --- | --- |
| Meter | Đối tượng đo đạc như Counter, Timer hoặc Gauge |
| Tên meter | Tên dùng khi đăng ký với Micrometer, thường theo dạng chữ thường phân tách bằng dấu chấm |
| Tag | Khóa–giá trị mô tả chiều phân loại, ví dụ `result=success` |
| MeterRegistry | Nơi đăng ký, ghi nhận và cung cấp meter cho một hệ thống đo đạc |
| Exporter/registry xuất dữ liệu | Thành phần chuyển meter thành định dạng hệ thống giám sát nhận |
| Label trong Prometheus | Khóa–giá trị gắn với một chuỗi thời gian |
| Chuỗi thời gian | Một tên chỉ số cùng một tập giá trị label cụ thể, có các mẫu đo theo thời gian |

Micrometer cung cấp quy ước đặt tên theo từng hệ thống giám sát. Quy ước có thể chuẩn hóa tên meter và khóa tag để phù hợp đích đến. Xem [Naming Meters của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Một meter cũng có thể sinh nhiều chuỗi dữ liệu: Timer không chỉ là “một số thời gian”, mà có thể cung cấp số lần ghi nhận, tổng thời gian và các thống kê khác. Vì vậy không có quy tắc chung rằng mỗi tên trong metrics endpoint phải xuất hiện đúng một lần, nguyên văn trong mọi exporter.

## 2. Vẽ đúng đường đi trước khi đối chiếu

Có thể tổ chức việc kiểm tra thành ba điểm quan sát:

```text
Mã đo đạc → registry và các bộ lọc
                ├── metrics endpoint: tên meter, measurements, tags
                └── registry xuất dữ liệu: tên/nhãn/đơn vị theo backend
                           ↓
                  dữ liệu xuất từ ứng dụng
                           ↓
                 bộ thu, relabel, lưu trữ
                           ↓
                    truy vấn/dashboard
```

Sơ đồ này là mô hình chẩn đoán. Trong ứng dụng có composite registry và nhiều registry con, các bộ lọc hoặc cách cấu hình có thể khác nhau. Metrics endpoint không nhất thiết là bản sao văn bản của dữ liệu một exporter cụ thể.

Ba phép so sánh trả lời ba câu hỏi khác nhau:

1. **Trong ứng dụng có meter mong đợi chưa?** Xem tên đăng ký, kiểu meter, tag và dữ liệu tại registry mà endpoint sử dụng.
2. **Ứng dụng thực sự xuất gì?** Xem phản hồi từ endpoint xuất hoặc dữ liệu gửi ra của đúng exporter.
3. **Hệ thống giám sát đã lưu gì?** Xem tên, label và mẫu dữ liệu sau thu thập/chuyển đổi.

Nếu ứng dụng đã xuất đúng nhưng truy vấn không thấy, cần kiểm tra từ bộ thu trở đi. Nếu chưa thấy trong dữ liệu xuất, chưa có lý do sửa PromQL bằng hàng loạt tên đoán thử.

## 3. Những khác biệt bình thường cần nhận ra

### 3.1. Tên meter, đơn vị và hậu tố thống kê

Ví dụ thường gặp khi dùng Micrometer với Prometheus:

| Tên/kiểu trong ứng dụng | Dạng chuỗi thường gặp ở Prometheus | Ý nghĩa cần đọc |
| --- | --- | --- |
| Counter `shop.checkout.completed` | `shop_checkout_completed_total` | Bộ đếm tích lũy |
| Timer `shop.checkout.duration` | `shop_checkout_duration_seconds_count` | Số lần ghi nhận thời gian |
| Cùng Timer đó | `shop_checkout_duration_seconds_sum` | Tổng thời gian, theo giây |
| Cùng Timer, khi có thống kê tương ứng | `shop_checkout_duration_seconds_max` | Thống kê thời gian lớn nhất theo cơ chế cửa sổ của meter |
| Cùng Timer, khi xuất classic histogram | `shop_checkout_duration_seconds_bucket` | Các bucket phân bố thời gian |
| Gauge `queue.depth` không đặt đơn vị bổ sung | `queue_depth` | Giá trị hiện tại |
| Meter có đơn vị byte | Tên xuất có thể có hậu tố `_bytes` | Đơn vị là một phần cần đối chiếu |

Bảng là các ví dụ theo cấu hình và quy ước Prometheus tương ứng, không phải thuật toán đổi tên dùng chung cho mọi exporter, kiểu meter hoặc phiên bản. Tên gốc cũng có thể đã chứa một phần hậu tố.

Với Micrometer 1.13, việc chuẩn hóa tên ở registry Prometheus và việc client thêm hậu tố counter là các phần khác nhau. Không nên tự viết quy tắc “thêm `_total` vào mọi tên trong code”. Có thể đối chiếu [PrometheusNamingConvention của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusNamingConvention.java) khi cần xác minh phiên bản cụ thể.

Đọc đơn vị trước khi kết luận số liệu sai. `250 ms` và `0.25 s` là cùng khoảng thời gian. Không thêm hệ số 1.000 vào truy vấn nếu dashboard đã đổi đơn vị trình bày một lần.

Một Timer cung cấp ít nhất số lần ghi nhận và tổng thời gian; đơn vị xuất tùy backend. Các thống kê như max, phân vị và histogram còn phụ thuộc khả năng cùng cấu hình. Xem [Timers của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 3.2. Khóa tag và giá trị tag không phải cùng thứ

Ví dụ:

```text
Trong meter:
    order.type = web-v2
    result     = success

Trong dữ liệu Prometheus theo quy ước đang xét:
    order_type = web-v2
    result     = success
```

Khóa `order.type` được chuẩn hóa thành `order_type`; không được tự suy ra giá trị `web-v2` cũng đổi thành `web_v2`. Một bộ lọc hoặc pipeline có thể chủ động đổi giá trị, nhưng phải có chứng cứ cho phép biến đổi đó.

Không suy ngược một tên label thành tên tag gốc chỉ bằng cách thay mọi dấu gạch dưới thành dấu chấm. Hai tên gốc khác nhau có thể chuẩn hóa về cùng một dạng; còn một khóa như `response_code` có thể vốn đã chứa dấu gạch dưới.

Thứ tự label trong văn bản không tạo ra một loại chuỗi mới. Hai mẫu cùng tên và cùng tập khóa–giá trị có ý nghĩa định danh như nhau dù các label được in theo thứ tự khác.

### 3.3. Có label do thống kê tạo ra

Classic histogram có label `le` mô tả cận trên bucket. Các phân vị được xuất theo dạng phù hợp có thể có `quantile`. Đây không nhất thiết là tag nghiệp vụ mà bạn đã gọi `tags(...)` khi đăng ký meter.

Do đó, việc thấy thêm `le` trong một chuỗi `_bucket` không đủ để kết luận tag bị thêm sai. Trước tiên xác định đang đọc bộ đếm, tổng thời gian, bucket hay phân vị.

## 4. Quy trình kiểm tra một chỉ số cụ thể

### Bước 1 — Cố định đối tượng và thời điểm

Ghi lại tên ứng dụng, instance, phiên bản, loại exporter và khoảng thời gian. Tránh gọi metrics endpoint của instance A nhưng so với dữ liệu exporter của instance B sau một lần cân bằng tải.

Đảm bảo hoạt động tạo meter đã xảy ra. Một meter chỉ đăng ký khi có yêu cầu đầu tiên có thể chưa tồn tại ngay sau khởi động. Một instance vừa restart cũng không có cùng giá trị tích lũy với instance chạy nhiều ngày.

### Bước 2 — Tìm tên gốc ở metrics endpoint

Với ứng dụng đã cấu hình và bảo vệ đường quản trị, giả sử URL quản trị là `http://127.0.0.1:9091`. Dùng Bash:

```bash
curl -fsS http://127.0.0.1:9091/actuator/metrics
curl -fsS http://127.0.0.1:9091/actuator/metrics/shop.checkout.completed
```

Tên dùng để chọn tại metrics endpoint là tên meter trong ứng dụng, không phải tên đã chuẩn hóa cho Prometheus. Xem [Metrics Endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Ví dụ JSON sau chỉ minh họa các trường đang đối chiếu, không trình bày toàn bộ phản hồi:

```json
{
  "name": "shop.checkout.completed",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3.0
    }
  ]
}
```

Việc gọi `/actuator/metrics/shop_checkout_completed_total` không phải cách thay thế tương đương cho tên gốc trong ví dụ.

Các URL trong bài là giả định phòng thử nghiệm. Nếu hệ thống đổi cổng, context path hoặc base path, dùng URL thực tế; dùng cơ chế xác thực đang được phép thay vì mở endpoint công khai.

### Bước 3 — Thu hẹp bằng tag của meter

Đọc `availableTags` nếu phản hồi cung cấp, rồi dùng đúng khóa và giá trị đã quan sát. Ví dụ:

```bash
curl -fsS --get \
  --data-urlencode 'tag=order.type:web-v2' \
  --data-urlencode 'tag=result:success' \
  http://127.0.0.1:9091/actuator/metrics/shop.checkout.completed
```

`--data-urlencode` giúp truyền query parameter đúng cách. Không đổi `order.type` thành `order_type` trong lệnh này chỉ vì exporter dùng dạng đó.

Khi chưa lọc đầy đủ, endpoint có thể tổng hợp measurements từ nhiều meter cùng tên và các tổ hợp tag khác nhau. Vì vậy, so `COUNT` chưa lọc ở endpoint với một chuỗi Prometheus đã lọc riêng `result="success"` có thể tạo chênh lệch hoàn toàn bình thường.

### Bước 4 — Xem dữ liệu xuất thực tế

Với registry Prometheus và endpoint đã có sẵn:

```bash
curl -fsS http://127.0.0.1:9091/actuator/prometheus
```

Tìm nhóm liên quan `shop_checkout_completed` và `shop_checkout_duration`. Một trích đoạn minh họa có thể là:

```text
shop_checkout_completed_total{order_type="web-v2",result="success"} 3.0
shop_checkout_duration_seconds_count{order_type="web-v2",result="success"} 1
shop_checkout_duration_seconds_sum{order_type="web-v2",result="success"} 0.25
```

Các dòng này minh họa tên và nhãn, không cam kết toàn bộ thứ tự dòng, cách định dạng số hoặc metadata của mọi phiên bản client. Counter được tăng ba đơn vị, còn Timer trong ví dụ chỉ ghi nhận một lần; hai số đếm không bắt buộc bằng nhau vì code đã đo hai việc riêng.

Ghi cả tên chuỗi, label, đơn vị, kiểu thống kê và thời điểm lấy dữ liệu. Không chỉ chụp một dòng `HELP` hoặc `TYPE`: tên family trong metadata và tên mẫu counter có thể được trình bày khác nhau tùy định dạng.

### Bước 5 — Kiểm tra trong hệ thống giám sát

Giả sử đã xác minh target có nhãn `job="checkout-api"` và `instance="10.0.0.7:9091"`. Truy vấn tên xuất thực tế:

```promql
shop_checkout_completed_total{
  job="checkout-api",
  instance="10.0.0.7:9091",
  order_type="web-v2",
  result="success"
}
```

Tên job và instance ở đây là ví dụ, phải thay bằng nhãn target thực tế. Nếu truy vấn không có dữ liệu, đối chiếu cấu hình target, lần scrape gần nhất, thời gian và các bước chuyển đổi trước khi thêm nhiều bộ lọc khác.

Phân biệt truy vấn tức thời với truy vấn tốc độ. Một chuỗi có thể hiện được ở truy vấn tức thời nhưng `rate(...[5m])` chưa ra kết quả khi chưa có đủ mẫu thích hợp trong cửa sổ.

### Bước 6 — Kết luận sự khác biệt xuất hiện tại đâu

- Tên khác giữa meter và dữ liệu xuất: kiểm tra naming convention, đơn vị, kiểu meter và bộ lọc ở registry.
- Tag khác ngay trong dữ liệu xuất: kiểm tra đăng ký meter, common tags và bộ lọc.
- Dữ liệu xuất đúng nhưng kho giám sát khác: kiểm tra bộ thu, relabel, pipeline và truy vấn.
- Chỉ dashboard khác: kiểm tra recording rule, phép tổng hợp, biến dashboard và tên trường hiển thị.

Mục tiêu là tìm **điểm đầu tiên** dữ liệu thay đổi ngoài kỳ vọng, không phải đổi đồng thời mọi lớp cho tới khi biểu đồ có số.

## 5. Đối chiếu cả ngữ nghĩa, không chỉ tên

### 5.1. Một meter không nhất thiết tương ứng một chuỗi

Để hỏi số sự kiện của Timer, dùng chuỗi `_count` phù hợp. Để hỏi tổng thời gian, dùng `_sum`. Để hỏi thời gian trung bình trong cửa sổ, có thể lấy tỷ lệ tốc độ tăng của tổng thời gian và số lần ghi nhận.

Ví dụ với các chuỗi thời gian đã xác minh:

```promql
sum(rate(shop_checkout_duration_seconds_sum{
  job="checkout-api", result="success"
}[5m]))
/
sum(rate(shop_checkout_duration_seconds_count{
  job="checkout-api", result="success"
}[5m]))
```

Kết quả có đơn vị giây. Cần có dữ liệu đủ mới và mẫu số có ý nghĩa; khi không có sự kiện, không coi kết quả thiếu hoặc không xác định là độ trễ bằng 0.

Tên `_max` không phải p95. Cũng không áp dụng `rate` lên một gauge chỉ vì tên nhìn giống counter. Xác minh loại dữ liệu và cách exporter trình bày trước khi chọn phép tính.

### 5.2. Không so snapshot với tốc độ hoặc cửa sổ khác

`COUNT=300` ở một instance không mâu thuẫn với biểu đồ `2 request/s` của toàn dịch vụ. Một bên là số tích lũy tại thời điểm lấy, bên kia là tốc độ trên cửa sổ và có thể tổng hợp nhiều instance.

Trước khi nói “tag bị sai nên số không khớp”, xác nhận:

- Cùng instance hay đã tổng hợp nhiều instance?
- Cùng bộ lọc tuyến, kết quả và loại sự kiện?
- Giá trị tích lũy, tốc độ hay mức tăng trong cửa sổ?
- Cùng đơn vị?
- Có restart, chậm scrape hoặc khoảng trống dữ liệu không?
- Đang so count với count hay count với số bucket?

Một histogram có nhiều bucket nên số dòng xuất không phải số lần ghi nhận. Bucket classic có tính tích lũy; không cộng mọi bucket để tìm tổng số yêu cầu.

## 6. Khi khác biệt đến từ registry và bộ lọc

Một ứng dụng có thể dùng composite registry và nhiều registry con. Hãy kiểm tra code đang ghi vào registry nào, registry nào được endpoint sử dụng và registry nào thực sự xuất dữ liệu.

Các tình huống đáng kiểm tra:

| Tình huống | Vì sao tạo khác biệt |
| --- | --- |
| Code tự tạo một registry riêng | Meter có thể nằm ngoài registry mà endpoint/exporter đang dùng |
| Bộ lọc chỉ áp dụng cho một registry con | Tên, tag hoặc sự có mặt của meter có thể khác giữa các đường xuất |
| Bộ lọc loại bỏ một nhóm meter | Code vẫn gọi meter nhưng đường xuất không có dữ liệu mong đợi |
| Bộ lọc đổi tên hoặc bỏ tag | Tên/chiều phân loại mới khác với kỳ vọng ban đầu |
| Common tags được cấu hình khác nhau | Một đường xuất có thêm nhãn ứng dụng/vùng mà đường khác không có |
| Cấu hình được áp dụng quá muộn | Meter đã đăng ký trước đó không tự trở thành tập meter mới như kỳ vọng |

`MeterFilter` có thể từ chối meter, biến đổi ID hoặc cấu hình thống kê. Thứ tự bộ lọc có ý nghĩa. Xem [Meter Filters của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

Ví dụ đoạn cấu hình trong một ứng dụng đã có registry:

```java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
        MeterFilter.renameTag("shop.", "order.type", "channel"));
```

Đây là mảnh cấu hình, không phải chương trình độc lập. Nó cần được áp dụng trước khi đăng ký các meter liên quan; phạm vi tác dụng còn phụ thuộc registry nhận bộ lọc. Khi đó `channel` có thể là khóa tag cần tìm ở đường đo tương ứng, không phải một lần đổi dấu chấm thành gạch dưới.

Tương tự, cấu hình common tag trong Spring Boot có thể là:

```yaml
management:
  metrics:
    tags:
      application: checkout-api
```

Không giả định tên ứng dụng tự động trở thành label `application` ở mọi nơi nếu chưa có cấu hình hoặc thành phần bổ sung tương ứng.

Khi một label vắng mặt, kiểm tra nơi nó phải được tạo. Chỉnh PromQL không thể làm xuất hiện một chiều dữ liệu chưa từng được ghi nhận.

## 7. Khi label thay đổi sau khi rời ứng dụng

### 7.1. Label của target khác với tag do ứng dụng đăng ký

Prometheus thường gắn `job` và `instance` khi scrape target. Vì vậy, dữ liệu trong kho có thể chứa hai label này dù chúng không xuất hiện trong JSON metrics endpoint hoặc trong văn bản ứng dụng tự xuất. Xem [Jobs and instances của Prometheus](https://prometheus.io/docs/concepts/jobs_instances/).

Một số label môi trường cũng có thể được tạo bởi cấu hình target hoặc service discovery. Khi thấy thêm `cluster`, `namespace` hay `region`, cần xác định nguồn bổ sung thực tế; không mặc định tất cả đều đến từ Micrometer.

Nếu ứng dụng cũng xuất `job` hoặc `instance`, cách xử lý xung đột phụ thuộc `honor_labels`. Trong cách xử lý tương ứng khi `honor_labels=false`, label xung đột từ dữ liệu scrape có thể được đổi thành `exported_job` hoặc `exported_instance`, rồi gắn label của target.

Đây là một lời giải thích có thể kiểm tra cho câu hỏi “vì sao label của tôi đổi tên trong Prometheus nhưng endpoint vẫn in tên cũ?”. Không đổi `honor_labels` chỉ để làm biến mất một tiền tố trước khi hiểu hệ quả định danh target.

### 7.2. Relabel và bộ thu có thể đổi hoặc loại dữ liệu

Ví dụ mảnh cấu hình trong một scrape job Prometheus:

```yaml
metric_relabel_configs:
  - source_labels: [__name__, order_type]
    regex: 'shop_checkout_completed_total;(.*)'
    target_label: channel
    replacement: '$1'
    action: replace
```

Với chuỗi khớp biểu thức, cấu hình minh họa sao chép giá trị `order_type` sang label `channel` trước khi lưu. Nó **không tự xóa** `order_type`. Nếu dữ liệu trong kho chỉ còn `channel`, phải kiểm tra thêm bước loại nhãn hoặc một phép chuyển đổi khác.

`metric_relabel_configs` tác động lên mẫu trước khi đưa vào lưu trữ. Cấu hình cũng có thể loại chuỗi, nên “có trong dữ liệu xuất nhưng không có trong kho” không nhất thiết do tên metric. Xem [cấu hình Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Đừng nhầm target relabel với metric relabel. Chúng tác động ở các điểm khác nhau. Khi có bộ thu trung gian, OpenTelemetry Collector hoặc đường remote write, tiếp tục kiểm tra các bước processor/relabel ở đúng pipeline.

Ghi nhận thay đổi bằng chứng cứ hai phía:

```text
Trước thu thập:
    shop_checkout_completed_total
    order_type=web-v2

Sau pipeline đã cấu hình:
    shop_checkout_completed_total
    order_type=web-v2
    channel=web-v2

Giải thích:
    Có bước sao chép label, chưa có chứng cứ label gốc bị xóa.
```

### 7.3. Dashboard có thể không truy vấn chuỗi gốc

Recording rule có thể tạo tên mới cho một phép tổng hợp. Truy vấn `sum by (...)` cũng loại những chiều không được giữ lại trong kết quả. Tên legend trên dashboard lại có thể chỉ là một chuỗi hiển thị do người thiết kế đặt.

Vì vậy, cần mở biểu thức truy vấn thật:

- Đang dùng chuỗi gốc hay tên được recording rule sinh ra?
- Có phép cộng gộp làm mất `instance` hoặc tag nghiệp vụ không?
- Có biến dashboard thêm bộ lọc không khớp giá trị thực không?
- Kho dữ liệu và khoảng thời gian đang chọn có đúng không?

Một label không xuất hiện trong kết quả tổng hợp không chứng minh exporter chưa từng xuất label đó.

## 8. Phiên bản và định dạng exporter là một phần của hồ sơ

Đối chiếu ít nhất phiên bản Spring Boot, Micrometer, module registry và client của backend. Không chỉ ghi “đang dùng Prometheus”.

Micrometer có đường tích hợp Prometheus dùng client mới và đường `prometheus-simpleclient` dùng client cũ. Chúng không bảo đảm mọi chi tiết định dạng hay quy tắc tên giống nhau. Khi nâng phiên bản, đọc thay đổi tương ứng và kiểm tra dữ liệu xuất thực tế, đặc biệt với hậu tố hoặc quy tắc kiểm tra tên.

Định dạng Prometheus text và OpenMetrics cũng có khác biệt ở metadata, cách biểu diễn counter hoặc dữ liệu bổ sung. Đừng lấy một đoạn output của phiên bản khác làm chuỗi chuẩn tuyệt đối để kiểm tra bằng phép so sánh văn bản toàn bộ.

Các ví dụ `_seconds_count`, `_seconds_sum` và `_bucket` trong bài nói về cách biểu diễn Prometheus tương ứng. Với exporter khác:

- Tên có thể dùng một quy ước khác.
- Tag có thể được ánh xạ sang thuộc tính hoặc chiều dữ liệu khác.
- Đơn vị và cách biểu diễn thống kê có thể khác.
- Một số thông tin có thể nằm ở metadata/resource thay vì thành label trên từng điểm dữ liệu.

Cách làm bền vững là giữ tên nghiệp vụ trong code theo quy ước Micrometer, đồng thời duy trì ánh xạ đã xác minh cho từng đường xuất. Không đổi toàn bộ tên meter trong code thành tên Prometheus chỉ vì một dashboard đang dùng sai tên.

## 9. Những lỗi thiết kế khiến việc đối chiếu khó hơn

### 9.1. Cùng tên nhưng bộ khóa tag không nhất quán

Ví dụ cần tránh trong một thiết kế phục vụ Prometheus:

```java
registry.counter("shop.checkout.completed", "channel", "web").increment();
registry.counter("shop.checkout.completed", "result", "success").increment();
```

Hai lần đăng ký dùng cùng tên nhưng bộ khóa tag khác nhau. Registry/client có thể cảnh báo hoặc xử lý không như bạn kỳ vọng; cần đọc log đăng ký meter và ràng buộc của phiên bản đang dùng.

Thiết kế nhất quán hơn là cùng bộ khóa và giá trị có nghĩa rõ ràng cho từng trường hợp:

```java
registry.counter("shop.checkout.completed",
        "channel", "web", "result", "success").increment();
registry.counter("shop.checkout.completed",
        "channel", "batch", "result", "failure").increment();
```

Đây là các mảnh code trong ứng dụng đã có registry. Không dùng giá trị giả chỉ để lấp tag nếu nó làm sai ý nghĩa đo; hãy xác định trước hợp đồng nhãn của chỉ số. Tham khảo [Micrometer Prometheus về tính nhất quán của tag và định dạng xuất](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

### 9.2. Tên khác nhau chuẩn hóa về cùng dạng

`shop.checkout` và `shop_checkout` có thể trở thành những tên khó phân biệt sau chuẩn hóa. Tương tự, hai khóa tag được chuẩn hóa về cùng tên có thể tạo xung đột.

Khi đó, kiểm tra log cảnh báo, danh sách meter đã đăng ký và output thực tế. Không chỉ thêm một lần thay dấu trong PromQL. Cần sửa thiết kế tên hoặc quy tắc ánh xạ để tránh nhiều khái niệm cùng chiếm một định danh.

Cũng phải xét kiểu meter: đăng ký cùng định danh cho Counter và Timer không tạo ra hai phép đo độc lập theo cách mong muốn. Tên, kiểu và nhãn phải có quan hệ rõ ràng.

### 9.3. Số tổ hợp nhãn tăng không kiểm soát

Mỗi tổ hợp giá trị label có thể tạo chuỗi mới. Không thêm mã đơn hàng, trace ID, email hoặc URL chứa ID biến đổi chỉ để “dễ tìm tag”.

Với tuyến HTTP, ưu tiên mẫu tuyến như `/orders/{id}` theo quy ước đo đạc của ứng dụng thay vì đường dẫn chứa từng mã đơn cụ thể. Những thông tin riêng từng yêu cầu thường phù hợp với log hoặc trace có chính sách dữ liệu tương ứng.

Nếu cần sửa một tag bị sai, cân nhắc cả việc giảm số chiều lẫn nguy cơ gộp các chuỗi khác nhau thành cùng định danh. Bỏ tag có thể làm mất khả năng phân biệt nguồn đo; với dữ liệu đã xuất, loại nhãn không có kế hoạch có thể tạo xung đột.

### 9.4. Đổi tên production mà quên người tiêu thụ

Một thay đổi tên hoặc tag ảnh hưởng dashboard, recording rule, alert và báo cáo. Trước khi đổi:

1. Xác định hợp đồng nào đang sai: tên trong ứng dụng, ánh xạ exporter hay truy vấn.
2. Liệt kê các bộ tiêu thụ cần cập nhật.
3. Thử trên dữ liệu đại diện, kiểm tra đơn vị và kiểu thống kê.
4. Triển khai theo kế hoạch có thể đối chiếu trước–sau.
5. Nếu có giai đoạn tương thích, quy định phạm vi và thời điểm kết thúc.

Không duy trì vô thời hạn hai counter cùng nghĩa rồi cộng cả hai trong truy vấn, vì có thể đếm đôi cùng hoạt động.

## 10. Ví dụ Java 17+: phân biệt tên gốc và quy ước tên

Chương trình sau chạy độc lập với Micrometer Core 1.13.0. Nó dùng `SimpleMeterRegistry` và gọi trực tiếp quy ước snake case để quan sát tên. Nó không khởi động Spring Boot, không mở cổng HTTP và không giả lập toàn bộ exporter Prometheus.

### 10.1. Chuẩn bị dependency

Tạo thư mục mới với:

```text
meter-naming-demo/
├── pom.xml
└── src/main/java/MeterNamingDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-naming-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Với ứng dụng Spring Boot, thường để BOM của Boot quản lý phiên bản dependency phù hợp. POM độc lập này cố định phiên bản để tái hiện chương trình nhỏ.

### 10.2. Chương trình đầy đủ

Nội dung `src/main/java/MeterNamingDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.NamingConvention;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterNamingDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter completed = Counter.builder("shop.checkout.completed")
                    .tags("order.type", "web-v2", "result", "success")
                    .register(registry);
            completed.increment(3);

            Timer duration = Timer.builder("shop.checkout.duration")
                    .tags("order.type", "web-v2", "result", "success")
                    .register(registry);
            duration.record(Duration.ofMillis(250));

            System.out.println("counter.name=" + completed.getId().getName());
            System.out.println("counter.count=" + (long) completed.count());
            System.out.println("tag.order.type=" + completed.getId().getTag("order.type"));
            System.out.println("snake.name=" + NamingConvention.snakeCase.name(
                    completed.getId().getName(), Meter.Type.COUNTER));
            System.out.println("snake.tag=" + NamingConvention.snakeCase.tagKey("order.type"));
            System.out.println("timer.count=" + duration.count());
            System.out.println("timer.total.seconds=" + duration.totalTime(TimeUnit.SECONDS));
        } finally {
            registry.close();
        }
    }
}
```

### 10.3. Biên dịch, chạy và đối chiếu stdout

Từ thư mục chứa POM, dùng Bash:

```bash
mvn -q compile dependency:copy-dependencies
java -cp "target/classes:target/dependency/*" MeterNamingDemo
```

Maven tải dependency khi cần và biên dịch với release 17. Nếu muốn gọi trình biên dịch trực tiếp sau bước Maven đã tạo các thư mục và tải dependency:

```bash
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes src/main/java/MeterNamingDemo.java
```

Trên Windows, phần classpath của lệnh chạy dùng dấu chấm phẩy:

```powershell
java -cp "target/classes;target/dependency/*" MeterNamingDemo
```

Stdout của chương trình:

```text
counter.name=shop.checkout.completed
counter.count=3
tag.order.type=web-v2
snake.name=shop_checkout_completed
snake.tag=order_type
timer.count=1
timer.total.seconds=0.25
```

Giải thích:

- `getId().getName()` vẫn cho tên đăng ký trong registry đang dùng.
- Khóa tag gốc vẫn là `order.type`; giá trị vẫn là `web-v2`.
- Gọi quy ước snake case tạo cách biểu diễn tên và khóa tag khác, không tự sửa đối tượng meter đang được đọc.
- `snake.name` chưa có `_total`: chuẩn hóa ký tự chưa bao gồm toàn bộ công việc trình bày một counter của exporter/client.
- Timer ghi đúng một khoảng 250 ms, nên khi yêu cầu tổng thời gian bằng giây nhận `0.25`.

Chương trình kiểm chứng phần phân biệt tên gốc, quy ước và đơn vị. Để xác minh tên chuỗi của một exporter production, vẫn cần đọc dữ liệu xuất của chính registry và phiên bản đang dùng.

## 11. Ghi lại ánh xạ để lần sau không phải đoán

Một hồ sơ ngắn cho chỉ số ví dụ có thể là:

| Trường cần lưu | Giá trị minh họa |
| --- | --- |
| Ý nghĩa nghiệp vụ | Số checkout hoàn thành theo loại đơn và kết quả |
| Tên Micrometer | `shop.checkout.completed` |
| Kiểu meter | Counter |
| Khóa tag ở ứng dụng | `order.type`, `result` |
| Tên Prometheus đã đối chiếu | `shop_checkout_completed_total` |
| Khóa label trong dữ liệu xuất | `order_type`, `result` |
| Giá trị đang kiểm tra | `web-v2`, `success` |
| Label do target cung cấp | `job`, `instance` theo cấu hình scrape |
| Biến đổi sau thu thập | Có hoặc không; ghi cụ thể rule nếu có |
| Phạm vi chứng cứ | Instance, phiên bản, thời điểm và định dạng dữ liệu |

Đừng biến bảng minh họa thành hợp đồng cho một hệ thống chưa kiểm tra. Khi tạo hồ sơ thật, điền từ chứng cứ quan sát được ở từng điểm.

Trước khi sửa, cần trả lời được: “Tôi đang sửa tên meter, ánh xạ exporter, rule thu thập hay truy vấn?”. Sau khi sửa, so cùng một instance và cùng tổ hợp nhãn; xác nhận các cảnh báo liên quan vẫn phản ánh đúng ngữ nghĩa.

## 12. Tự thực hành chẩn đoán

### Tình huống 1: dùng tên xuất tại metrics endpoint

Trong ứng dụng có meter `shop.checkout.completed`. Prometheus đang có chuỗi `shop_checkout_completed_total`. Bạn gọi:

```text
/actuator/metrics/shop_checkout_completed_total
```

và không tìm được meter mong đợi.

**Đối chiếu:** dùng tên meter quan sát được trong registry, tức `shop.checkout.completed`, khi truy vấn metrics endpoint. Dùng tên chuỗi đã xuất khi truy vấn Prometheus. Không cần đổi tên meter trong code chỉ để hai URL cùng sử dụng một chuỗi ký tự.

### Tình huống 2: giá trị tag bị thay nhầm

Dữ liệu xuất có:

```text
shop_checkout_completed_total{order_type="web-v2",result="success"} 3.0
```

Truy vấn dùng `order_type="web_v2"` không trả dữ liệu.

**Đối chiếu:** trong ví dụ, khóa đã được chuẩn hóa nhưng giá trị vẫn là `web-v2`. Sửa điều kiện lọc theo giá trị thực tế. Nếu pipeline có biến đổi giá trị ở một môi trường khác, phải xác minh riêng, không áp dụng quy tắc thay ký tự một cách suy đoán.

### Tình huống 3: dữ liệu xuất đúng nhưng label trong kho có thêm tiền tố

Ứng dụng tự xuất label `job="business-worker"`, nhưng Prometheus lưu `exported_job="business-worker"` cùng label `job` của target.

**Đối chiếu:** kiểm tra xử lý xung đột label và cấu hình `honor_labels`. Đây có thể là thay đổi ở bước scrape, không phải việc Micrometer đổi tên tag trong ứng dụng. Giữ nguyên chứng cứ hai phía trước khi điều chỉnh chính sách.

### Tình huống 4: tổng thời gian lệch 1.000 lần

Một phép ghi nhận là 250 ms. Dữ liệu timer xuất theo giây có tổng thời gian 0,25; dashboard lại hiển thị 0,25 ms.

**Đối chiếu:** kiểm tra đơn vị chuỗi và đơn vị hiển thị. Giá trị 0,25 giây tương ứng 250 mili giây. Chỉ đổi cách trình bày hoặc quy đổi tại một điểm đã xác định; không nhân/chia ở nhiều lớp rồi vô tình tạo sai lệch mới.

Kết quả chẩn đoán đạt yêu cầu khi chỉ ra được tên gốc, tên xuất, khóa/giá trị nhãn, đơn vị và điểm biến đổi cụ thể. Sự khác nhau về cách viết chỉ là dấu hiệu ban đầu; điều cần bảo toàn là ý nghĩa của phép đo và khả năng truy vấn đúng dữ liệu.
