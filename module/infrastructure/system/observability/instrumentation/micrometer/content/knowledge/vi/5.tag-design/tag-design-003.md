# Phân biệt số meter trong JVM với số chuỗi tại hệ thống nhận

Khi thêm instrumentation Micrometer vào ứng dụng, số meter mà ứng dụng đăng ký trong JVM không nhất thiết bằng số chuỗi thời gian mà hệ thống giám sát lưu trữ. Một `Counter` thường tạo ra một chuỗi cho mỗi tổ hợp tên và tag ở mỗi instance; một `Timer` có thể được xuất thành nhiều chuỗi như số lần, tổng thời gian, giá trị cực đại và các bucket histogram. Hệ thống nhận còn có thể gắn nhãn của target như `instance`, `job` hoặc `pod`, khiến cùng một meter trong mã nguồn xuất hiện thành nhiều chuỗi trên toàn cụm.

Phân biệt hai con số này giúp đánh giá đúng cardinality, tìm nguyên nhân tăng chi phí lưu trữ và chọn biện pháp giới hạn phù hợp. Đếm meter trong JVM hữu ích để kiểm tra instrumentation tại một tiến trình; đếm chuỗi ở backend mới cho biết quy mô dữ liệu mà hệ thống giám sát thực sự xử lý.

## Meter trong JVM là gì?

Một meter là đối tượng Micrometer dùng để ghi nhận một đại lượng, chẳng hạn số lần hoàn tất đơn hàng, thời gian xử lý request hoặc số phần tử hiện có trong hàng đợi. Meter được đăng ký trong một `MeterRegistry` và có một định danh (`Meter.Id`). Định danh này chủ yếu được xác định bởi tên meter cùng tập tag của nó.

Ví dụ, hai lần truy cập registry với cùng tên và cùng tag sẽ dùng chung một meter:

```java
Counter webOrders = registry.counter(
        "orders.created",
        "channel", "web");

Counter webOrdersAgain = registry.counter(
        "orders.created",
        "channel", "web");

Counter mobileOrders = registry.counter(
        "orders.created",
        "channel", "mobile");
```

`webOrders` và `webOrdersAgain` tham chiếu cùng một meter trong registry đó. `mobileOrders` có giá trị tag khác nên là một meter có định danh riêng. Nếu mã ứng dụng tạo một `Counter` mới cho mỗi `orderId`, mỗi mã đơn hàng có thể tạo ra một meter riêng và làm số lượng meter trong tiến trình tăng liên tục.

Có thể xem số meter mà một registry đang quản lý bằng `getMeters()`:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

public void inspectRegistry(MeterRegistry registry) {
    System.out.println("Registered meters = " + registry.getMeters().size());

    for (Meter meter : registry.getMeters()) {
        Meter.Id id = meter.getId();
        System.out.println(
                id.getName() + " " + id.getType() + " " + id.getTags());
    }
}
```

Con số này là số meter mà registry đang quản lý trong tiến trình hiện tại. Nó hữu ích để phát hiện code tạo meter theo dữ liệu động, nhưng không cho biết trực tiếp backend sẽ lưu bao nhiêu chuỗi. Với `CompositeMeterRegistry`, cần hiểu registry đang được quan sát là registry tổng hợp hay một registry con; các registry con có thể xuất dữ liệu theo quy tắc riêng.

## Chuỗi thời gian ở hệ thống nhận là gì?

Ở backend kiểu Prometheus, một chuỗi thời gian được nhận diện bởi tên metric và toàn bộ tập nhãn của mẫu. Hai mẫu có cùng tên metric nhưng khác một nhãn, chẳng hạn `instance`, là hai chuỗi khác nhau. Hai mẫu có cùng nhãn nhưng tên metric khác nhau cũng là hai chuỗi khác nhau.

Ví dụ một counter Micrometer có tên `orders.created` và tag `channel=web` có thể được Prometheus registry xuất thành metric như `orders_created_total` với nhãn `channel="web"`. Nếu Prometheus scrape hai instance của cùng dịch vụ, nó thường bổ sung nhãn target như `job` và `instance`:

```text
orders_created_total{channel="web", job="checkout", instance="10.0.0.11:8080"}
orders_created_total{channel="web", job="checkout", instance="10.0.0.12:8080"}
```

Hai tiến trình có cùng một định nghĩa meter trong mã nguồn nhưng backend lưu hai chuỗi, vì nhãn `instance` khác nhau. Nếu có sáu instance, cùng một tổ hợp meter và tag ứng dụng thường tạo ra sáu chuỗi counter tương ứng ở Prometheus.

Định dạng metric thực tế phụ thuộc registry và backend. Tên meter có thể được chuẩn hóa, thêm hậu tố đơn vị hoặc hậu tố loại số đo; một số loại meter còn được mở rộng thành nhiều metric khi xuất.

## Vì sao một meter có thể tạo nhiều chuỗi?

Mức mở rộng phụ thuộc loại meter, cấu hình phân phối và định dạng của registry. Với Prometheus, một số trường hợp thường gặp như sau:

| Meter trong Micrometer | Dữ liệu thường được xuất | Số chuỗi có thể phát sinh cho mỗi tổ hợp tag và mỗi target |
|---|---|---|
| `Counter` | Tổng số lần sự kiện | Thường một chuỗi counter |
| `Gauge` | Giá trị hiện tại | Thường một chuỗi gauge |
| `Timer` | Số lần, tổng thời gian, có thể có giá trị cực đại | Thường nhiều chuỗi metric như `_count`, `_sum`, `_max` |
| `DistributionSummary` | Số lượng, tổng giá trị, có thể có cực đại | Thường nhiều chuỗi metric như `_count`, `_sum`, `_max` |
| `Timer` hoặc `DistributionSummary` bật histogram | Các bucket, số lượng và tổng giá trị; có thể có cực đại | Một chuỗi cho mỗi bucket cùng các chuỗi tổng hợp khác |
| Meter xuất percentile phía client | Các percentile được tính trong tiến trình | Có thể có một chuỗi cho mỗi percentile được xuất |

Các số lượng trong bảng là cách hình dung, không phải cam kết cố định cho mọi backend. Registry có thể đổi tên hoặc bỏ một số measurement; backend có thể biểu diễn histogram theo cấu trúc khác. Hãy kiểm tra exposition hoặc dữ liệu nhận thực tế của registry đang sử dụng.

### Timer và histogram làm số chuỗi tăng

Một `Timer` cơ bản đã chứa ít nhất hai thống kê quan trọng: số lần thực hiện và tổng thời gian. Với Prometheus, chúng thường xuất thành các metric có hậu tố `_count` và `_sum`; một số cấu hình còn có `_max`.

Khi bật `publishPercentileHistogram()`, Micrometer xuất thêm các bucket để backend có thể tổng hợp phân phối giữa nhiều instance. Mỗi ranh giới bucket tạo một chuỗi có nhãn `le` khác nhau; bucket vô cực `+Inf` cũng được biểu diễn. Vì vậy, một timer có thể tạo ra hàng chục chuỗi cho một tổ hợp tag trên một target, dù trong JVM vẫn chỉ là một meter `Timer`.

Ví dụ một histogram có 12 bucket hữu hạn và bucket `+Inf` có thể tạo 13 chuỗi bucket, cộng các chuỗi `_count`, `_sum` và có thể `_max`. Cấu hình bucket thực tế, các ngưỡng SLO bổ sung và registry quyết định con số cuối cùng.

```java
Timer requestTimer = Timer.builder("http.server.request")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
        .register(registry);
```

Các ngưỡng SLO thêm bucket ranh giới phù hợp cho mục tiêu vận hành. Mỗi bucket mới có thể tăng số chuỗi được xuất. Vì thế chỉ bật histogram cho những metric thực sự cần phân tích phân phối hoặc percentile ở backend.

### Percentile phía client cũng có chi phí riêng

Micrometer có thể tính percentile ngay trong tiến trình và xuất các giá trị như p50, p95 hoặc p99. Với định dạng Prometheus, các giá trị này thường được biểu diễn bằng nhãn `quantile`. Mỗi percentile được cấu hình có thể tạo thêm một chuỗi cho mỗi tổ hợp tag và target.

Percentile phía client được tính độc lập ở từng JVM. Backend không thể cộng p95 của các instance để tạo p95 toàn dịch vụ. Nếu mục tiêu là percentile có thể tổng hợp giữa các instance, histogram bucket thường là lựa chọn phù hợp hơn. Tránh bật đồng thời nhiều kiểu phân phối nếu dashboard và cảnh báo không sử dụng chúng.

## Cardinality phụ thuộc vào tổ hợp tag

Cardinality là số lượng tổ hợp định danh khác nhau mà hệ thống quan sát phải quản lý. Với một meter name, mỗi tổ hợp giá trị tag được ghi nhận là một định danh meter riêng trong registry. Khi xuất ra backend, mỗi định danh có thể tạo ra một hoặc nhiều chuỗi tùy loại meter.

Giả sử meter `http.server.requests` có ba tag:

- `method`: 4 giá trị (`GET`, `POST`, `PUT`, `DELETE`).
- `status`: 5 nhóm (`2xx`, `3xx`, `4xx`, `5xx`, `other`).
- `uri`: 20 route template.

Số tổ hợp tối đa theo tích Descartes là:

\[
4 \times 5 \times 20 = 400
\]

Đây là giới hạn trên nếu mọi tổ hợp đều xuất hiện. Số tổ hợp thực tế có thể thấp hơn nếu một số method không dùng cho một số route hoặc status. Nếu dịch vụ chạy 8 instance, backend scrape từng instance và mỗi tổ hợp được xuất từ mọi instance, số nhóm chuỗi tương ứng có thể lên tới:

\[
400 \times 8 = 3.200
\]

Nếu mỗi tổ hợp đó là một `Timer` bật histogram tạo khoảng 16 chuỗi xuất ra, tổng quy mô có thể xấp xỉ:

\[
3.200 \times 16 = 51.200\text{ chuỗi}
\]

Phép tính trên nhằm ước lượng quy mô. Số thực tế còn phụ thuộc bucket, tag target, filter, registry, mức độ xuất dữ liệu và cách backend biểu diễn histogram. Các nhãn target như `instance` không nhất thiết tạo thêm meter trong JVM, nhưng chúng phân biệt chuỗi ở backend.

### Một tag động có thể làm cardinality mất kiểm soát

Các giá trị như `userId`, `orderId`, `sessionId`, email, địa chỉ IP hoặc URL chứa ID thường có số lượng rất lớn. Nếu gắn `userId` vào counter request, mỗi người dùng có thể tạo một tổ hợp tag mới. Khi một JVM tiếp nhận request từ lượng người dùng rất lớn, một meter đơn giản có thể biến thành hàng triệu meter trong tiến trình đó và nhiều triệu chuỗi trên backend.

Đối với HTTP, không gắn URL đầy đủ có chứa ID tài nguyên làm tag `uri`. Hãy dùng route template:

| Giá trị không nên dùng | Giá trị đã chuẩn hóa |
|---|---|
| `/orders/10001` | `/orders/{orderId}` |
| `/orders/10002` | `/orders/{orderId}` |
| `/customers/abc-123/profile` | `/customers/{customerId}/profile` |

Tương tự, thay exception message tự do bằng nhóm lỗi hữu hạn như `validation`, `timeout`, `dependency` hoặc `unknown`. Nếu cần phân tích từng request hay từng người dùng, hãy dùng log hoặc trace với cơ chế lấy mẫu và kiểm soát dữ liệu phù hợp; metric nên giữ các chiều có tập giá trị nhỏ và ổn định.

## Các yếu tố làm số meter và số chuỗi khác nhau

Không chỉ tag do mã nghiệp vụ tạo ra mới ảnh hưởng đến cardinality. Cần xem xét cả các lớp chuyển đổi trên đường xuất dữ liệu:

1. **Common tags:** tag chung như `application`, `region` hoặc `environment` được áp dụng cho nhiều meter. Chúng hữu ích để lọc và nhóm dữ liệu, nhưng nếu giá trị thay đổi giữa các tiến trình hoặc môi trường thì backend sẽ có thêm các tổ hợp nhãn.
2. **MeterFilter:** filter có thể từ chối meter, đổi tên, đổi tag hoặc giới hạn số tag. Filter làm thay đổi tập meter được đăng ký hoặc định danh được xuất; cần cấu hình trước khi meter được tạo.
3. **Loại meter và cấu hình phân phối:** histogram, SLO bucket và percentile có thể làm một meter mở rộng thành nhiều chuỗi.
4. **Số instance:** cùng một meter được xuất từ nhiều JVM sẽ tạo chuỗi riêng khi backend phân biệt target bằng `instance`, `pod` hoặc nhãn tương tự.
5. **Exporter và backend:** registry có quy tắc chuyển đổi tên và đơn vị riêng; backend có thể bổ sung nhãn target, relabel hoặc loại bỏ một số chuỗi trước khi lưu.
6. **Vòng đời dữ liệu:** registry trong JVM phản ánh meter đang đăng ký; backend có thể vẫn giữ chuỗi cũ trong thời gian retention sau khi một meter hoặc instance đã ngừng xuất dữ liệu.

Vì vậy, không thể suy ra chính xác số chuỗi lưu trữ chỉ từ `registry.getMeters().size()`. Con số đó là một tín hiệu ở lớp ứng dụng, cần kết hợp với thống kê exporter và backend.

## Kiểm soát cardinality tại ứng dụng

### Chọn tag có tập giá trị hữu hạn

Trước khi thêm tag, xác định các giá trị có thể xuất hiện và lý do cần chiều phân tích đó. `method`, nhóm status, tên vùng hoặc route template thường có tập giá trị hữu hạn. Các ID của người dùng, đơn hàng, request hoặc giá trị tự do thường không phù hợp làm tag metric.

### Chuẩn hóa route và kết quả

Chuẩn hóa đường dẫn về route template thay vì đường dẫn thực tế. Chuẩn hóa trạng thái lỗi về nhóm có ý nghĩa vận hành. Việc chuẩn hóa phải diễn ra trước khi đăng ký meter, để các request tương đương dùng chung định danh.

### Dùng MeterFilter để đặt giới hạn

Micrometer cho phép cấu hình filter để từ chối meter khi số giá trị của một tag vượt giới hạn. Ví dụ sau giới hạn tối đa 100 giá trị `uri` cho meter `http.server.requests`:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()));
```

Đăng ký filter trong lúc cấu hình registry, trước khi các meter nghiệp vụ được tạo. Filter là lớp bảo vệ bổ sung; thiết kế tag đúng từ đầu vẫn là biện pháp chính. Khi filter từ chối meter, metric tương ứng có thể không xuất hiện, vì vậy cần theo dõi log và kiểm thử hành vi khi chạm ngưỡng.

Có thể dùng `MeterFilter.maximumAllowableMetrics(...)` để đặt giới hạn tổng số meter được chấp nhận trong registry. Giới hạn này giúp bảo vệ tiến trình trước việc tạo meter quá mức, nhưng không thay thế việc tính cardinality của từng metric family ở backend.

### Chọn histogram theo nhu cầu

Histogram hữu ích khi cần percentile có thể gộp hoặc kiểm tra số quan sát vượt các ngưỡng SLO. Hãy xác định trước dashboard và cảnh báo cần bucket nào, sau đó bật histogram trên đúng meter cần thiết. Một histogram với nhiều bucket nhân lên theo số tổ hợp tag và số instance, vì vậy cấu hình rộng cho mọi meter có thể làm tăng đáng kể dung lượng chuỗi thời gian.

## Đo hai lớp ở đâu?

Để điều tra cardinality, hãy thu thập số liệu từ cả registry và backend:

| Câu hỏi | Nơi kiểm tra | Ý nghĩa |
|---|---|---|
| Một JVM đang quản lý bao nhiêu meter? | `registry.getMeters().size()` | Số meter đã đăng ký trong registry đang kiểm tra |
| Meter nào đang tạo nhiều định danh? | Duyệt `Meter.Id` và thống kê theo tên/tag | Tìm meter có tag động hoặc số tổ hợp lớn |
| Một meter được xuất thành những metric nào? | Endpoint scrape hoặc exposition của exporter | Xác định suffix, bucket, quantile và đơn vị |
| Backend đang lưu bao nhiêu chuỗi cho metric? | Thống kê cardinality hoặc truy vấn của backend | Quy mô chuỗi sau khi thêm nhãn target và áp dụng quy tắc ingest |
| Số chuỗi tăng theo instance hay tag? | Nhóm theo `instance`, `pod`, `uri`, `status` hoặc nhãn liên quan | Khoanh vùng chiều làm số tổ hợp tăng |

Với Prometheus, có thể đếm số chuỗi đang có mẫu trong vector cho một nhóm metric bằng PromQL:

```promql
count({__name__=~"http_server_requests_seconds_.*"})
```

Để xem số chuỗi theo tên metric:

```promql
count by (__name__) ({__name__=~"http_server_requests_seconds_.*"})
```

Các truy vấn trên đếm chuỗi được chọn trong phạm vi dữ liệu hiện có tại thời điểm truy vấn. Chúng không nhất thiết bằng tổng số chuỗi đã từng được lưu trong toàn bộ thời gian retention. Tên metric phải khớp với định dạng thực tế mà Prometheus registry xuất ra.

## Ví dụ điều tra chênh lệch

Giả sử một ứng dụng checkout báo cáo `registry.getMeters().size()` bằng 120 trên mỗi JVM. Backend cho thấy khoảng 7.000 chuỗi có tên bắt đầu bằng `http_server_requests`. Không nên kết luận có 7.000 meter trong từng tiến trình.

Hãy kiểm tra theo trình tự:

1. Duyệt các `Meter.Id` trong registry để tìm meter request và số tổ hợp `method`, `status`, `uri` đang có.
2. Kiểm tra exposition của Prometheus registry để xác định timer có `_count`, `_sum`, `_max` và bao nhiêu `_bucket`.
3. Nhóm chuỗi ở Prometheus theo `instance` để xem số target đang scrape.
4. Nhóm tiếp theo `uri` và `status` để tìm các giá trị tag có cardinality cao.
5. Đối chiếu với cấu hình histogram, common tags và filter trong ứng dụng.

Ví dụ, nếu mỗi JVM có 120 meter nhưng 8 instance cùng xuất dữ liệu, một meter timer có 15 bucket và các chuỗi tổng hợp khác có thể tạo ra hàng trăm chuỗi ở backend. Chênh lệch này là hệ quả của cách xuất và cách backend nhận dữ liệu; nó không nhất thiết chỉ ra registry bị rò rỉ meter.

Ngược lại, nếu `registry.getMeters().size()` tăng đều theo thời gian trong một JVM, hãy tìm code đăng ký meter với tag nhận giá trị động. Nếu số meter trong JVM ổn định nhưng chuỗi backend tăng, hãy xem xét số instance, bucket, percentile, nhãn scrape và retention.

## Những nhầm lẫn cần tránh

- **Một meter không đồng nghĩa một chuỗi:** timer và histogram có thể tạo nhiều metric series cho một định danh meter.
- **Một meter name không đồng nghĩa một meter:** mỗi tổ hợp tag khác nhau tạo ra một định danh khác.
- **Số meter trong một JVM không phải số meter toàn cụm:** mỗi instance có registry và vòng đời riêng.
- **Nhãn target không nhất thiết là tag Micrometer:** Prometheus có thể thêm `instance`, `job` hoặc `pod` khi scrape.
- **Số chuỗi hiện tại không phải toàn bộ chuỗi lịch sử:** backend giữ dữ liệu theo retention và có thể vẫn lưu chuỗi đã ngừng cập nhật.
- **Giới hạn số meter không bảo đảm giới hạn số chuỗi:** một timer có histogram có thể tạo nhiều chuỗi dù chỉ chiếm một meter ID.

## Checklist thiết kế và vận hành

- [ ] Đã phân biệt số meter đang đăng ký trong từng JVM với số chuỗi backend lưu trữ.
- [ ] Tag của từng meter có tập giá trị hữu hạn và có mục đích phân tích rõ ràng.
- [ ] Route, status và loại lỗi được chuẩn hóa trước khi ghi nhận.
- [ ] Không dùng ID, email, token, địa chỉ IP hoặc URL chứa dữ liệu định danh làm tag.
- [ ] Histogram và percentile chỉ bật cho metric có nhu cầu vận hành cụ thể.
- [ ] Common tags và nhãn target được tính vào ước lượng cardinality toàn cụm.
- [ ] MeterFilter được cấu hình trước khi meter được tạo và có kiểm tra khi chạm giới hạn.
- [ ] Đã kiểm tra exposition của exporter và thống kê chuỗi tại backend.
- [ ] Đã theo dõi xu hướng số meter trong JVM và số chuỗi ở backend theo thời gian.

Thiết kế tag quyết định số định danh meter mà ứng dụng tạo ra; loại meter và exporter quyết định số chuỗi được biểu diễn; số instance cùng nhãn target quyết định quy mô dữ liệu toàn cụm. Theo dõi cả ba lớp sẽ giúp xác định đúng nguồn cardinality và giữ chi phí quan sát trong giới hạn vận hành.
