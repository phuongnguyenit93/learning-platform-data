# Ngữ nghĩa cumulative hoặc delta và khả năng hỗ trợ phía nhận

## Mục tiêu

OTLP có thể truyền metrics theo hai cách diễn đạt dữ liệu tích lũy theo thời gian: **cumulative** và **delta**. Hai cách này có thể cùng mô tả một lượng request, byte hoặc thời gian đã ghi nhận, nhưng mỗi điểm dữ liệu mang ý nghĩa khác nhau. Nếu ứng dụng gửi delta đến backend chỉ hiểu cumulative, hoặc ngược lại, receiver có thể từ chối dữ liệu, tính sai rate hoặc cộng dồn sai.

Micrometer OtlpMeterRegistry cho phép chọn aggregation temporality khi xuất metrics. Giá trị mặc định là cumulative; có thể chọn delta nếu hệ thống nhận hỗ trợ đúng loại metric và semantics tương ứng. Tuy nhiên, một endpoint nhận OTLP không đồng nghĩa backend hỗ trợ mọi loại data point và mọi temporality.

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa cumulative và delta.
- Hiểu vai trò của start timestamp, end timestamp, reset và khoảng dữ liệu bị thiếu.
- Cấu hình aggregation temporality trong Micrometer OTLP.
- Xác định những loại meter được chuyển thành OTLP data point nào.
- Đánh giá receiver, OpenTelemetry Collector và backend trước khi chọn temporality.
- Kiểm thử dữ liệu đầu vào, dữ liệu lưu trữ và truy vấn sau khi đổi temporality.

## Aggregation temporality là gì?

Aggregation temporality mô tả một data point biểu diễn lượng dữ liệu trong khoảng thời gian như thế nào. Trong OTLP, các loại dữ liệu cộng dồn như Sum, Histogram và ExponentialHistogram có thể dùng cumulative hoặc delta. Gauge biểu diễn giá trị tại một thời điểm nên không dùng hai chế độ temporality này theo cùng cách.

Giả sử một dịch vụ xử lý request và bộ đếm tăng thêm 100, 60 rồi 80 request trong ba khoảng thời gian liên tiếp:

| Khoảng thời gian | Request mới trong khoảng | Giá trị cumulative | Giá trị delta |
|---|---:|---:|---:|
| T0 đến T1 | 100 | 100 | 100 |
| T1 đến T2 | 60 | 160 | 60 |
| T2 đến T3 | 80 | 240 | 80 |

Hai chuỗi biểu diễn cùng lượng công việc. Cumulative lặp lại tổng từ mốc bắt đầu; delta chỉ chứa lượng tăng thêm trong từng khoảng không chồng lấn.

## Cumulative: tổng từ một mốc bắt đầu

Với cumulative temporality, mỗi điểm dữ liệu chứa tổng lượng đã ghi nhận kể từ một start time. Các điểm tiếp theo giữ nguyên start timestamp và cập nhật end timestamp cùng giá trị tích lũy.

Ví dụ:

~~~text
StartTime = T0, Time = T1, value = 100
StartTime = T0, Time = T2, value = 160
StartTime = T0, Time = T3, value = 240
~~~

Receiver có thể tính phần tăng thêm bằng cách so sánh hai điểm liên tiếp:

- T1 đến T2: 160 - 100 = 60 request.
- T2 đến T3: 240 - 160 = 80 request.

### Ưu điểm

- Khi một lần export bị bỏ lỡ, điểm cumulative tiếp theo vẫn chứa tổng mới. Receiver có thể tính phần tăng trong khoảng dài hơn nếu có đủ thông tin về start time và reset.
- Phù hợp với mô hình counter tích lũy quen thuộc của Prometheus.
- Có thể chuyển thành rate hoặc delta ở phía nhận nếu cần.
- Dễ kiểm tra tổng lượng đã xảy ra kể từ khi tiến trình hoặc meter bắt đầu.

### Chi phí và giới hạn

- Nguồn phải duy trì trạng thái tích lũy cho từng chuỗi metric.
- Bộ nhớ phía gửi tăng theo số lượng series/cardinality.
- Receiver phải nhận biết reset khi ứng dụng khởi động lại hoặc chuỗi metric bắt đầu một vòng đời mới.
- Với histogram cumulative, min và max có thể dần ổn định theo vòng đời dài, khiến chúng kém hữu ích để mô tả cửa sổ gần đây.

Nếu tiến trình khởi động lại, cumulative value có thể trở về thấp hơn. Receiver cần dùng StartTimeUnixNano và thông tin thời gian để phân biệt reset hợp lệ với dữ liệu bị sai thứ tự. Không nên xem mọi giá trị giảm là một lượng âm.

## Delta: lượng tăng trong một khoảng không chồng lấn

Với delta temporality, mỗi điểm dữ liệu chỉ chứa lượng được ghi nhận trong một khoảng thời gian. Start timestamp của điểm kế tiếp nối tiếp end timestamp của điểm trước.

Ví dụ:

~~~text
StartTime = T0, Time = T1, value = 100
StartTime = T1, Time = T2, value = 60
StartTime = T2, Time = T3, value = 80
~~~

Mỗi giá trị đã là phần tăng trong khoảng tương ứng. Receiver có thể cộng các delta để tạo tổng hoặc tính rate từ lượng trong từng khoảng và độ dài khoảng đó.

Ví dụ, delta point ghi nhận 60 request trong một khoảng 30 giây. Tốc độ của khoảng đó là 60 / 30 = 2 request mỗi giây. Nếu các khoảng export có độ dài khác nhau, hãy dùng timestamp thực tế để tính thời lượng; không mặc định mọi delta point luôn đại diện cho cùng một số giây.

### Ưu điểm

- Nguồn không cần giữ một tổng cumulative cho mọi series chỉ để xuất các điểm delta.
- Mỗi điểm thể hiện rõ lượng phát sinh trong khoảng thời gian cụ thể.
- Receiver có thể tổng hợp các khoảng hoặc chuyển sang cumulative nếu cần.
- Hữu ích khi muốn chuyển chi phí giữ trạng thái/cardinality từ tiến trình sang collector hoặc backend.

### Chi phí và giới hạn

- Receiver cần cộng dồn nếu backend hoặc truy vấn yêu cầu chuỗi cumulative.
- Việc chuyển delta sang cumulative cần giữ trạng thái theo từng series ở phía nhận.
- Nếu một delta point bị mất và không có cơ chế retry hoặc buffering, lượng của khoảng đó không thể được khôi phục chỉ từ delta point tiếp theo.
- Các khoảng phải liên tục và không chồng lấn; dữ liệu gửi sai thứ tự hoặc trùng khoảng có thể làm tổng bị sai.

Delta không có nghĩa là mỗi lần record() tạo một request OTLP riêng. Micrometer vẫn gom dữ liệu theo chu kỳ export; delta point mô tả lượng được tổng hợp trong khoảng giữa các lần export.

## Vai trò của timestamp và reset

Mỗi OTLP data point có TimeUnixNano để biểu diễn thời điểm điểm dữ liệu có hiệu lực. Với Sum, Histogram và ExponentialHistogram, StartTimeUnixNano được khuyến nghị mạnh vì receiver cần biết chuỗi đã tích lũy từ khi nào để xử lý rate, restart và khoảng trống dữ liệu.

Quy tắc cơ bản:

- Cumulative: các điểm liên tiếp của cùng chuỗi giữ nguyên start timestamp.
- Delta: start timestamp của điểm tiếp theo bằng end timestamp của điểm trước.
- Khi một tiến trình bắt đầu vòng đời mới, start timestamp mới giúp receiver nhận ra reset.
- Khi thiếu một khoảng dữ liệu, timestamp giúp receiver nhận biết chuỗi có gap thay vì giả định rằng không có sự kiện xảy ra.

Ví dụ, cumulative counter tăng từ 100 lên 160. Nếu tiến trình restart rồi gửi giá trị 5 với start timestamp mới, receiver có thể xem đây là một chuỗi mới. Nếu chỉ nhìn giá trị số, nó có thể nhầm 5 là reset bất thường hoặc một phép trừ âm.

Với delta, mỗi điểm cần mô tả đúng khoảng mà nó bao phủ. Hai điểm cùng đại diện cho một khoảng sẽ gây cộng trùng; một khoảng bị bỏ trống sẽ tạo mất dữ liệu nếu không được gửi lại.

## Cấu hình temporality trong Micrometer OTLP

### Thêm registry OTLP

Khi dự án đã dùng BOM của Micrometer hoặc BOM của framework, có thể thêm registry mà không gán version riêng:

~~~kotlin
dependencies {
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Micrometer OtlpMeterRegistry mặc định gửi metrics qua HTTP dưới dạng OTLP protobuf. Endpoint HTTP phổ biến của OTLP metrics có đường dẫn /v1/metrics. Nếu receiver chỉ cung cấp gRPC, cần kiểm tra sender mà ứng dụng sử dụng; Micrometer không cung cấp sẵn một implementation gRPC của OtlpMetricsSender trong tài liệu hiện hành. Có thể tích hợp sender tùy chỉnh nếu cần.

### Cấu hình Spring Boot

Ví dụ dưới đây chọn cumulative temporality và gửi metrics mỗi 30 giây đến OpenTelemetry Collector:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        aggregationTemporality: "cumulative"
        step: 30s
        resourceAttributes:
          service.name: "orders-api"
~~~

Để chọn delta, thay giá trị aggregationTemporality:

~~~yaml
management:
  otlp:
    metrics:
      export:
        aggregationTemporality: "delta"
~~~

Micrometer cũng hỗ trợ biến môi trường OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE với giá trị cumulative hoặc delta. Nếu không cấu hình, mặc định là cumulative.

### Temporality khác với step

Hai cấu hình này giải quyết hai vấn đề khác nhau:

| Cấu hình | Ý nghĩa |
|---|---|
| aggregationTemporality | Mỗi điểm mang tổng từ start time hay lượng tăng trong một khoảng |
| step | Khoảng thời gian Micrometer xuất dữ liệu |

Ví dụ step: 30s không tự động có nghĩa là delta. Nếu aggregationTemporality là cumulative, mỗi lần export vẫn chứa tổng từ start time. Nếu là delta, mỗi lần export chứa lượng phát sinh trong khoảng tương ứng.

Micrometer OTLP mặc định dùng step một phút nếu không có cấu hình khác. Hãy chọn step theo yêu cầu độ phân giải, tải export và khả năng tiếp nhận của backend.

## Những loại meter Micrometer được ánh xạ sang OTLP

OTLP hỗ trợ nhiều loại metric data point. Micrometer ánh xạ meter của mình sang các loại này như sau:

| OTLP data point | Meter Micrometer |
|---|---|
| Sum | Counter, FunctionCounter |
| Gauge | Gauge, TimeGauge, MultiGauge |
| Histogram | Timer, DistributionSummary, LongTaskTimer, FunctionTimer |
| ExponentialHistogram | Timer, DistributionSummary |
| Summary | Timer, DistributionSummary, LongTaskTimer |

FunctionTimer chỉ xuất sum và count trong Histogram data point, không có bucket phân bố từng mẫu. Với Timer và DistributionSummary, Micrometer mặc định ưu tiên Histogram. Cấu hình publishPercentiles có thể tạo Summary data point chứa percentile đã tính phía ứng dụng; OTLP xem Summary là dạng legacy và không khuyến nghị cho ứng dụng mới. Cấu hình percentile histogram hoặc SLO tạo Histogram data point.

Gauge là giá trị tại thời điểm đọc, không phải lượng cộng dồn. Vì vậy, không áp dụng lựa chọn cumulative/delta cho Gauge theo cùng ý nghĩa của Sum hoặc Histogram.

### Max của Histogram và delta

Micrometer OTLP chỉ hỗ trợ trường max của Histogram data point khi dùng delta temporality. Lý do là max cumulative có xu hướng ổn định khi càng nhiều mẫu được ghi nhận trong suốt vòng đời ứng dụng; nó không còn mô tả tốt cực đại của một cửa sổ gần đây.

Nếu dashboard cần max theo từng khoảng export, delta histogram có thể giữ ý nghĩa đó tốt hơn. Tuy nhiên, receiver cũng phải hỗ trợ delta histogram và cách lưu trường max. Đừng chọn delta chỉ để có max nếu backend không thể tiếp nhận hoặc truy vấn đúng loại dữ liệu này.

## Khả năng hỗ trợ phía nhận

OTLP là giao thức trung lập với nhà cung cấp, nhưng khả năng ingest thực tế phụ thuộc receiver, collector pipeline, exporter và hệ thống lưu trữ phía sau. Một dịch vụ có endpoint OTLP chưa chắc hỗ trợ mọi data point và temporality.

Trước khi chọn cấu hình, hãy kiểm tra từng lớp:

| Lớp | Cần xác minh |
|---|---|
| Transport | Receiver nhận OTLP HTTP hay gRPC; URL/path, TLS, authentication và compression có phù hợp không? |
| Data point | Có nhận Sum, Gauge, Histogram, ExponentialHistogram và Summary mà ứng dụng xuất không? |
| Temporality | Có hỗ trợ cumulative, delta hay cả hai cho từng loại Sum/Histogram? |
| Reset và gap | Có xử lý start timestamp, restart, khoảng thiếu và dữ liệu gửi lại không? |
| Aggregation | Backend lưu delta trực tiếp, tự chuyển đổi hay yêu cầu cumulative? |
| Histogram | Có giữ bucket, sum, count và max theo đúng semantics không? |
| Resource/attributes | Có giữ service.name, service.instance.id và các attributes cần thiết để phân biệt nguồn không? |
| Query | Có tính rate, sum và percentile đúng theo temporality nhận được không? |

Hãy đọc tài liệu ingestion metrics của đúng phiên bản backend đang triển khai. Không suy ra hỗ trợ delta chỉ từ việc backend có thể nhận OTLP traces hoặc logs; ba tín hiệu có pipeline và khả năng khác nhau.

### Trường hợp receiver chỉ hỗ trợ cumulative

Nếu receiver hoặc hệ thống lưu trữ yêu cầu cumulative, hãy cấu hình Micrometer xuất cumulative. Nếu nguồn chỉ có delta, một collector có thể chuyển delta thành cumulative bằng cách cộng dồn trong bộ nhớ.

Việc chuyển đổi này có trạng thái theo từng chuỗi metric. Collector phải nhận liên tục các điểm của cùng chuỗi ở cùng một instance để giữ tổng chính xác. Khi collector restart hoặc load balancer chuyển cùng chuỗi sang collector khác, trạng thái có thể bị mất hoặc phân tán. Processor delta-to-cumulative trong OpenTelemetry Collector contrib hiện được đánh dấu alpha cho metrics; cần đánh giá độ ổn định và giới hạn state trước khi dùng production.

Processor này tích lũy các delta trong bộ nhớ và có các giới hạn như max_stale để loại bỏ chuỗi không còn dữ liệu mới, cùng max_streams để giới hạn số chuỗi đang giữ trạng thái. Khi vượt giới hạn số stream, dữ liệu của stream mới có thể bị loại bỏ. Vì vậy, delta-to-cumulative vẫn cần một ngân sách cardinality và chiến lược định tuyến rõ ràng ở collector.

### Trường hợp receiver chỉ hỗ trợ delta

Nếu backend yêu cầu delta nhưng ứng dụng gửi cumulative, OpenTelemetry Collector contrib có processor cumulative-to-delta cho monotonic sums, histograms và exponential histograms. Non-monotonic sums không được chuyển đổi; các điểm vốn đã là delta được chuyển tiếp.

Processor này cũng có trạng thái vì phải nhớ điểm cumulative trước đó để tính phần chênh lệch. Cùng một chuỗi phải được định tuyến đến cùng collector instance. Tài liệu Collector hiện đánh dấu processor này beta cho metrics; hãy kiểm tra version, trạng thái ổn định và giới hạn triển khai trước khi sử dụng.

Chuyển đổi temporality không phải phép đổi định dạng đơn giản. Nó cần state, timestamps và quy tắc xử lý điểm đầu tiên, reset, gap và dữ liệu đến trễ. Một pipeline có nhiều Collector cần định tuyến nhất quán theo identity của metric stream hoặc dùng kiến trúc có state được chia sẻ/đồng bộ phù hợp.

## Chọn cumulative hay delta?

Không có lựa chọn đúng cho mọi backend. Hãy dựa vào khả năng nhận và chi phí vận hành:

| Tiêu chí | Cumulative | Delta |
|---|---|---|
| Ý nghĩa mỗi điểm | Tổng từ start time | Lượng trong một khoảng không chồng lấn |
| Xử lý lần export bị bỏ lỡ | Điểm sau có thể bao gồm phần tăng trong khoảng thiếu | Khoảng bị mất khó khôi phục nếu không retry/buffer |
| Trạng thái phía gửi | Duy trì tổng tích lũy | Có thể giảm nhu cầu giữ tổng theo series |
| Trạng thái phía nhận | Có thể tính delta/rate từ các điểm liên tiếp | Cần cộng dồn nếu backend muốn cumulative |
| Max histogram | Cumulative max dần ổn định, ít hữu ích cho cửa sổ gần đây | Có thể biểu diễn max theo khoảng |
| Phù hợp khi | Backend theo mô hình counter tích lũy, ưu tiên chịu được khoảng scrape thiếu | Receiver hỗ trợ delta và muốn chuyển chi phí aggregation xuống collector/backend |

Với một hệ thống mới chưa có yêu cầu cụ thể từ backend, cumulative là điểm khởi đầu hợp lý vì đây là mặc định của Micrometer OTLP và tương thích với mô hình counter phổ biến. Chỉ chuyển sang delta sau khi đã xác nhận receiver hỗ trợ đúng loại data point, hiểu reset/gap và có cơ chế state/aggregation phù hợp.

## Kiểm thử khả năng tương thích end-to-end

Đừng chỉ xác minh ứng dụng gửi HTTP thành công. Một request OTLP được trả về thành công chưa chứng minh dữ liệu đã được lưu và truy vấn đúng.

Hãy kiểm thử theo trình tự:

1. Tạo một Counter tăng theo các khoảng đã biết, ví dụ 100, 60 và 80.
2. Xuất cùng metric với cumulative; xác nhận receiver thấy các điểm 100, 160 và 240 cùng start time.
3. Xuất với delta; xác nhận receiver thấy 100, 60 và 80 trên các khoảng không chồng lấn.
4. Kiểm tra Timer hoặc DistributionSummary có Histogram bucket, sum và count như cấu hình.
5. Nếu cần max theo cửa sổ, xác nhận delta Histogram được nhận và max không bị loại bỏ.
6. Khởi động lại ứng dụng để kiểm tra receiver nhận diện start timestamp mới.
7. Bỏ lỡ một chu kỳ export để kiểm tra cách backend xử lý gap.
8. Chạy nhiều instance để xác nhận resource attributes và series identity không bị nhập nhằng.
9. Nếu có processor chuyển đổi, kiểm tra định tuyến ổn định, restart collector và trạng thái state sau khi triển khai lại.
10. Viết truy vấn rate/throughput và đối chiếu với số thao tác đã tạo trong test.

Ví dụ kiểm tra cumulative:

~~~text
T1: count = 100, start = T0
T2: count = 160, start = T0
T3: count = 240, start = T0
~~~

Ví dụ kiểm tra delta:

~~~text
T1: count = 100, interval = (T0, T1]
T2: count = 60,  interval = (T1, T2]
T3: count = 80,  interval = (T2, T3]
~~~

Nếu backend hiển thị tổng 400 thay vì 240, có thể delta đã bị cộng trùng hoặc cumulative bị hiểu như delta. Nếu tổng chỉ là 80, receiver có thể đang giữ điểm cuối mà không tích lũy các delta trước đó. Hãy kiểm tra temporality ở từng bước của pipeline để tìm nơi diễn giải sai.

## Những lỗi thường gặp

**Nhầm step với temporality.** Step quyết định chu kỳ export; cumulative/delta quyết định giá trị mỗi điểm đại diện cho khoảng nào.

**Cho rằng mọi OTLP receiver đều hỗ trợ delta.** OTLP có định nghĩa delta, nhưng receiver và backend có thể chỉ hỗ trợ một số loại data point hoặc temporality.

**Chuyển đổi delta/cumulative mà không giữ state.** Cả hai chiều chuyển đổi đều cần thông tin điểm trước hoặc tổng đã tích lũy. Collector không có state phù hợp có thể tạo sai số hoặc mất dữ liệu.

**Chia cùng metric identity giữa nhiều collector khi conversion stateful.** Mỗi collector có lịch sử riêng, dẫn đến chênh lệch và reset giả. Hãy định tuyến ổn định hoặc chọn pipeline không cần conversion.

**Bỏ qua StartTimeUnixNano.** Receiver có thể không phân biệt được reset, gap và chuỗi mới, dẫn đến rate sai.

**Trộn cumulative và delta giữa các instance.** Các điểm cùng metric cần temporality và identity nhất quán. Khi rollout đổi cấu hình, hãy kiểm soát chuyển đổi để backend không gộp sai hai kiểu stream.

**Kỳ vọng max cumulative phản ánh max gần đây.** Với Histogram cumulative, max ổn định dần; Micrometer chỉ xuất max Histogram trong delta temporality.

**Chỉ kiểm tra HTTP 2xx.** Cần kiểm tra data point thực tế được ingest, lưu trữ và truy vấn đúng.

## Checklist trước khi bật OTLP trong production

1. Xác nhận receiver nhận đúng transport và endpoint OTLP metrics.
2. Liệt kê các meter thực tế và OTLP data point tương ứng.
3. Xác minh cumulative/delta cho từng loại Sum, Histogram và ExponentialHistogram.
4. Chọn temporality thống nhất cho các instance cùng service.
5. Kiểm tra start timestamp, reset, gap và dữ liệu gửi lại.
6. Chọn step phù hợp với độ phân giải và năng lực receiver.
7. Xác minh resource attributes, service identity và tag/attributes.
8. Nếu chuyển đổi tại Collector, kiểm tra statefulness, routing, restart và giới hạn cardinality.
9. Kiểm tra histogram bucket, sum, count và max theo temporality.
10. Đối chiếu dữ liệu đã ghi với truy vấn rate và tổng lượng trong test.

## Kết luận

Cumulative và delta mô tả hai cách khác nhau để biểu diễn lượng metric theo thời gian. Cumulative lặp lại tổng từ start time; delta chỉ chứa lượng phát sinh trong từng khoảng không chồng lấn. Micrometer OTLP mặc định xuất cumulative và cho phép chọn delta bằng aggregationTemporality; step vẫn là chu kỳ export riêng. Trước khi đổi temporality, cần xác minh receiver hỗ trợ đúng loại data point, hiểu reset/gap và có thể chuyển đổi stateful nếu cần. Kiểm thử từ ứng dụng qua collector đến backend mới chứng minh được metrics đang giữ đúng ngữ nghĩa.

## Tài liệu tham khảo

- [Micrometer - OTLP](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html): cấu hình aggregationTemporality, step, endpoint, mapping meter sang OTLP data point và giới hạn histogram max.
- [OpenTelemetry - Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): semantics cumulative/delta, timestamps, reset, gap, histogram và trade-off giữa state phía gửi/nhận.
- [OpenTelemetry Collector - Cumulative to Delta Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/cumulativetodeltaprocessor): phạm vi chuyển đổi và cảnh báo stateful.
- [OpenTelemetry Collector - Delta to Cumulative Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/deltatocumulativeprocessor): chuyển đổi bằng cách tích lũy state trong bộ nhớ và giới hạn vận hành.
