# Histogram có bucket tường minh hoặc dạng hàm mũ theo hỗ trợ phiên bản

Micrometer OTLP có thể xuất phân phối của Timer và DistributionSummary thành hai dạng histogram: histogram có bucket tường minh (Explicit Bucket Histogram) hoặc histogram hàm mũ cơ số 2 (Base2 Exponential Histogram). Cả hai đều biểu diễn count, sum và phân phối quan sát, nhưng cách xác định ranh giới bucket khác nhau.

Histogram tường minh dùng các ranh giới số cụ thể do Micrometer tạo hoặc do ứng dụng khai báo qua SLO. Histogram hàm mũ dùng một công thức cơ số 2 cùng tham số scale để phân bố bucket trên miền giá trị rộng. Cách thứ hai hữu ích khi dữ liệu trải dài qua nhiều bậc độ lớn và muốn giới hạn số bucket mà vẫn giữ độ phân giải tương đối.

Khả năng chọn histogram flavor phụ thuộc phiên bản Micrometer. Explicit Bucket Histogram là mặc định; lựa chọn Base2 Exponential Histogram được bổ sung từ Micrometer 1.14.0. Cấu hình riêng theo từng meter và giới hạn bucket riêng theo tên meter có từ 1.15.0. Ngoài ra, khi cấu hình SLO tùy chỉnh, Micrometer luôn dùng bucket tường minh vì Exponential Histogram không biểu diễn được các ranh giới SLO tùy ý.

## 1. Hai dạng histogram trong OTLP

Histogram là cách biểu diễn một tập giá trị quan sát bằng các thống kê tổng hợp và các bucket. Ví dụ, một Timer ghi nhận thời lượng request có thể lưu:

- Tổng số request.
- Tổng thời gian xử lý.
- Các bucket đếm số request nằm trong từng khoảng thời gian.
- Giá trị nhỏ nhất/lớn nhất nếu loại dữ liệu và aggregation temporality hỗ trợ.

OTLP định nghĩa hai dạng dữ liệu histogram:

| Dạng OTLP | Cấu trúc bucket | Phù hợp khi |
|---|---|---|
| Histogram (Explicit Bucket) | Ranh giới bucket được liệt kê rõ ràng | Cần ngưỡng cố định, SLO cụ thể hoặc backend yêu cầu explicit bounds |
| Exponential Histogram | Ranh giới suy ra từ scale và chỉ số bucket cơ số 2 | Miền dữ liệu rộng, cần độ phân giải tương đối và giới hạn số bucket |

Với explicit histogram, ví dụ các ranh giới có thể là 100 ms, 300 ms và 1 giây. Trong OTLP, `bucketCounts` là số lượng riêng của từng khoảng, không phải số tích lũy:

| Khoảng giá trị | `bucketCounts` |
|---|---:|
| `(-Inf, 100 ms]` | 120 |
| `(100 ms, 300 ms]` | 140 |
| `(300 ms, 1 s]` | 35 |
| `(1 s, +Inf)` | 5 |

Tổng bốn bucket là 300 quan sát. Điểm này khác với histogram kiểu Prometheus classic, nơi bucket được xuất theo số tích lũy. Collector hoặc exporter có thể chuyển đổi cách biểu diễn khi đưa dữ liệu sang một backend khác.

Với exponential histogram, ứng dụng không gửi một danh sách ranh giới tùy ý. Dữ liệu gửi scale, offset và các dãy bucket count dương/âm cùng zero bucket. Backend suy ra ranh giới từ công thức chung.

## 2. Micrometer ánh xạ meter sang OTLP histogram

Trong OTLP registry, các meter thời gian và phân phối được ánh xạ sang những data point phù hợp:

| Micrometer meter | OTLP data point | Ghi chú |
|---|---|---|
| Timer | Histogram hoặc Exponential Histogram | Có count, sum và bucket khi histogram được bật |
| DistributionSummary | Histogram hoặc Exponential Histogram | Dành cho đại lượng số không phải thời gian |
| LongTaskTimer | Histogram hoặc Summary | Không nằm trong nhóm Exponential Histogram của Micrometer |
| FunctionTimer | Histogram | Chỉ xuất sum và count, không có phân phối bucket từ nguồn |

Counter và FunctionCounter được ánh xạ sang Sum; Gauge, TimeGauge và MultiGauge được ánh xạ sang Gauge.

Với OTLP registry, Timer và DistributionSummary mặc định được xuất dưới dạng Histogram data point. Nếu chỉ cấu hình `publishPercentiles(...)`, OTLP có thể xuất Summary chứa percentile đã tính ở phía ứng dụng. Summary là dạng cũ trong mô hình OTLP và không phải lựa chọn được khuyến nghị cho ứng dụng mới. Khi bật histogram, dữ liệu Histogram/Exponential Histogram được ưu tiên thay cho Summary.

## 3. Khác biệt giữa explicit và exponential

### Explicit Bucket Histogram

Explicit histogram dùng một danh sách ranh giới được xác định trước. Với cùng tập quan sát ở phần trên, OTLP gửi số lượng riêng theo từng bucket:

| Khoảng giá trị | Số quan sát |
|---|---:|
| `(-Inf, 100 ms]` | 120 |
| `(100 ms, 300 ms]` | 140 |
| `(300 ms, 1 s]` | 35 |
| `(1 s, +Inf)` | 5 |

Backend có thể chuyển các số đếm riêng này thành dạng cumulative khi cần biểu diễn theo quy ước của Prometheus classic histogram. Không nên nhầm cấu trúc bucket của OTLP với cấu trúc đã được chuyển đổi ở backend.

Ưu điểm:

- Có thể đặt bucket đúng tại các ngưỡng SLO.
- Dễ đọc và dễ kiểm tra vì ranh giới có ý nghĩa trực tiếp với người vận hành.
- Phù hợp với backend hoặc pipeline chỉ hỗ trợ histogram tường minh.
- Có thể kiểm soát độ chi tiết tại các vùng quan trọng bằng cách chọn ranh giới.

Hạn chế:

- Cần chọn ranh giới trước.
- Một tập ranh giới không phù hợp có thể thiếu độ phân giải ở vùng cần quan sát.
- Nhiều bucket làm tăng số lượng dữ liệu được xuất.
- Khi các hệ thống dùng ranh giới khác nhau, việc tổng hợp histogram có thể cần chuyển đổi hoặc chuẩn hóa.

### Base2 Exponential Histogram

Exponential Histogram dùng ranh giới được xác định theo lũy thừa của một cơ số. Với scale s, cơ số được tính theo:

\[
\text{base} = 2^{2^{-s}}
\]

Bucket có chỉ số (i) biểu diễn một khoảng được xác định bởi các lũy thừa liên tiếp của base. Cấu trúc có dải bucket dương, dải bucket âm và zero bucket.

Ví dụ:

- Scale 0 tạo base bằng 2, các bucket rộng hơn.
- Scale 4 tạo base xấp xỉ 1,04427, các bucket hẹp hơn.
- Scale càng lớn, số bucket giữa hai lũy thừa của 2 càng nhiều và độ phân giải càng cao.

Ưu điểm:

- Tự phân bố bucket trên miền giá trị rộng mà không cần khai báo hàng trăm ranh giới thủ công.
- Giữ độ phân giải tương đối trên các bậc độ lớn.
- Có thể giảm scale để hạ độ phân giải và hợp nhất bucket mà không cần tạo một bộ ranh giới tùy ý mới.
- Hữu ích cho độ trễ hoặc kích thước có phân phối trải dài trên nhiều bậc độ lớn.

Hạn chế:

- Không thể khai báo các ranh giới SLO tùy ý như explicit histogram.
- Độ phân giải phụ thuộc scale và giới hạn bucket.
- Backend, collector và công cụ truy vấn phải hỗ trợ OTLP Exponential Histogram.
- Cần kiểm tra khả năng hiển thị và chuyển đổi của toàn bộ pipeline trước khi triển khai.

## 4. Phiên bản Micrometer quyết định lựa chọn có sẵn

Không phải phiên bản nào của `micrometer-registry-otlp` cũng hỗ trợ cùng một histogram flavor.

| Micrometer | Khả năng liên quan |
|---|---|
| 1.13.x và cũ hơn | Có explicit histogram; chưa có cấu hình `histogramFlavor` để chọn Exponential Histogram |
| 1.14.0 trở lên | Có `histogramFlavor`, `maxScale` và `maxBucketCount`; hỗ trợ Base2 Exponential Histogram |
| 1.15.0 trở lên | Có thể chọn histogram flavor và giới hạn bucket theo từng meter bằng `histogramFlavorPerMeter` và `maxBucketsPerMeter` |

Mốc 1.14.0 là phiên bản của Micrometer, không đồng nghĩa với một phiên bản Spring Boot cụ thể. Spring Boot quản lý phiên bản Micrometer qua dependency management/BOM. Trước khi dùng cấu hình, hãy kiểm tra phiên bản thực tế được resolve trong runtime.

Gradle:

~~~shell
./gradlew dependencyInsight --dependency micrometer-registry-otlp --configuration runtimeClasspath
~~~

Maven:

~~~shell
mvn dependency:tree -Dincludes=io.micrometer:micrometer-registry-otlp
~~~

Nếu dự án đang dùng Micrometer 1.13.x, cấu hình `histogram-flavor` sẽ không tạo ra khả năng exponential histogram. Cần nâng phiên bản theo BOM tương thích và kiểm tra lại các module Micrometer để tránh lệch phiên bản.

## 5. Giá trị mặc định của OtlpConfig

Khi histogram được công bố, `OtlpConfig.histogramFlavor()` quyết định dạng được ưu tiên. Giá trị mặc định là:

`EXPLICIT_BUCKET_HISTOGRAM`

Để chọn exponential, cấu hình:

`BASE2_EXPONENTIAL_BUCKET_HISTOGRAM`

Các giá trị cấu hình tương ứng thường được biểu diễn trong properties bằng:

- `explicit-bucket-histogram`
- `base2-exponential-bucket-histogram`

Lựa chọn này chỉ ảnh hưởng đến meter có histogram được công bố. Nó không tự biến một Counter hoặc Gauge thành histogram, cũng không thay đổi `aggregationTemporality`.

Micrometer hỗ trợ biến môi trường `OTEL_EXPORTER_OTLP_METRICS_DEFAULT_HISTOGRAM_AGGREGATION` làm giá trị dự phòng cho histogram flavor khi không có cấu hình tương ứng trong `OtlpConfig`. Nếu ứng dụng dùng Spring Boot, nên cấu hình qua property được quản lý bởi framework để dễ quan sát và kiểm tra.

## 6. Bật exponential histogram bằng Spring Boot

Sau khi thêm dependency registry OTLP và cấu hình endpoint, bật percentile histogram cho meter cần theo dõi:

~~~properties
management.otlp.metrics.export.url=http://localhost:4318/v1/metrics
management.otlp.metrics.export.histogram-flavor=base2-exponential-bucket-histogram
management.otlp.metrics.export.max-scale=12
management.otlp.metrics.export.max-bucket-count=160

management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

Ý nghĩa:

- `url`: endpoint nhận metrics OTLP.
- `histogram-flavor`: chọn Base2 Exponential Histogram thay cho explicit bucket.
- `max-scale`: giới hạn scale tối đa; scale cao hơn cho độ phân giải tốt hơn nhưng có thể cần nhiều bucket hơn.
- `max-bucket-count`: giới hạn số bucket dùng cho exponential histogram.
- `percentiles-histogram`: yêu cầu Micrometer tạo histogram cho Timer có tên tương ứng.

Trong cấu hình trên, `max-scale=12` là ví dụ để minh họa giới hạn scale. Không cần mặc định dùng 12 cho mọi hệ thống; hãy đo cardinality, bộ nhớ và độ chính xác cần thiết trước khi chọn.

Nếu muốn giữ explicit bucket, có thể cấu hình:

~~~properties
management.otlp.metrics.export.histogram-flavor=explicit-bucket-histogram
management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

Explicit là mặc định, vì vậy property đầu tiên có thể được bỏ qua nếu không có cấu hình khác ghi đè.

## 7. Bật explicit histogram với SLO boundaries

Khi cần theo dõi các ngưỡng SLO cụ thể, cấu hình ranh giới bằng `serviceLevelObjectives` hoặc property tương ứng:

~~~properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
~~~

Với Timer, các giá trị có thể khai báo bằng Duration như `100ms`, `300ms` hoặc `1s`. Với DistributionSummary, SLO boundaries là các giá trị số theo đơn vị của đại lượng được ghi nhận.

Khi một meter có SLO boundaries, Micrometer dùng explicit bucket histogram cho meter đó, kể cả khi registry đang được cấu hình:

`histogram-flavor=base2-exponential-bucket-histogram`

Lý do là Exponential Histogram không cho phép chỉ định các ranh giới SLO tùy ý. Nếu dashboard hoặc alert cần bucket đúng tại 300 ms, hãy dùng explicit histogram cho meter đó.

Ví dụ Timer:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1)
        )
        .register(registry);
~~~

Ví dụ DistributionSummary:

~~~java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload.size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .serviceLevelObjectives(1_024.0, 10_240.0, 102_400.0)
        .register(registry);
~~~

Trong ví dụ thứ hai, các ranh giới lần lượt là 1 KB, 10 KB và 100 KB. Không dùng các giá trị đó cho meter có đơn vị khác.

## 8. Phân biệt histogram flavor với aggregation temporality

Hai cấu hình này giải quyết hai vấn đề khác nhau:

- **Histogram flavor** quyết định cách chia miền giá trị thành bucket: explicit hoặc exponential.
- **Aggregation temporality** quyết định dữ liệu được biểu diễn tích lũy từ lúc bắt đầu hay theo delta của một khoảng thời gian.

| Cấu hình | Giá trị | Ý nghĩa |
|---|---|---|
| `histogramFlavor` | Explicit | Ranh giới bucket được liệt kê |
| `histogramFlavor` | Base2 exponential | Ranh giới bucket được suy ra từ scale |
| `aggregationTemporality` | Cumulative | Count/sum tích lũy từ thời điểm bắt đầu |
| `aggregationTemporality` | Delta | Count/sum của khoảng thu thập hiện tại |

Có thể kết hợp explicit + cumulative, explicit + delta, exponential + cumulative hoặc exponential + delta nếu registry và backend hỗ trợ. Chọn histogram flavor không tự động chuyển dữ liệu từ cumulative sang delta.

Một chi tiết của OTLP registry: trường `max` trên Histogram data point chỉ được hỗ trợ với delta temporality. Với cumulative temporality, min/max tích lũy dần ổn định theo vòng đời ứng dụng và ít hữu ích hơn cho từng khoảng quan sát. Nếu dashboard cần max theo từng cửa sổ, hãy xác minh temporality và cách backend xử lý trường này.

Trong OTLP registry, aggregation temporality mặc định là cumulative. Có thể cấu hình qua:

~~~properties
management.otlp.metrics.export.aggregation-temporality=cumulative
~~~

Hoặc:

~~~properties
management.otlp.metrics.export.aggregation-temporality=delta
~~~

Backend nhận phải hỗ trợ temporality đã chọn. Không thay đổi temporality chỉ để thử exponential histogram; hai quyết định cần được kiểm chứng độc lập.

## 9. Scale và giới hạn bucket của exponential histogram

Exponential histogram có hai giới hạn quan trọng:

- `maxScale`: scale tối đa, mặc định 20.
- `maxBucketCount`: số bucket tối đa, mặc định 160.

Scale càng cao thì bucket càng hẹp và độ phân giải tương đối càng tốt. Tuy nhiên, khi miền giá trị trải rộng, nhiều bucket hơn có thể cần thiết. Giới hạn bucket giúp kiểm soát kích thước dữ liệu và bộ nhớ.

Micrometer có thể giảm scale khi cần tuân thủ giới hạn bucket. Vì vậy, `maxScale` là mức trần chứ không phải cam kết histogram luôn dùng đúng scale đó. Độ phân giải thực tế phụ thuộc miền giá trị quan sát và số bucket được phép sử dụng.

Quy trình lựa chọn:

1. Xác định miền giá trị thường gặp và phần đuôi cần quan sát.
2. Chọn scale tối đa đủ độ phân giải cho câu hỏi vận hành.
3. Đặt giới hạn bucket phù hợp với ngân sách bộ nhớ và payload.
4. Ghi nhận phân phối thực tế ở môi trường thử nghiệm.
5. Kiểm tra scale và số bucket trong OTLP payload.
6. Điều chỉnh khi dữ liệu hoặc nhu cầu truy vấn thay đổi.

Không tăng `maxScale` và `maxBucketCount` lên mức cao nhất chỉ để có nhiều bucket. Histogram càng lớn thì payload, bộ nhớ và chi phí xử lý càng tăng.

## 10. Cấu hình flavor riêng theo meter từ Micrometer 1.15.0

Từ Micrometer 1.15.0, `OtlpConfig` hỗ trợ `histogramFlavorPerMeter` để chọn flavor cho từng nhóm meter. Cấu hình này ghi đè giá trị mặc định của `histogramFlavor`.

Ví dụ YAML:

~~~yaml
management:
  otlp:
    metrics:
      export:
        histogram-flavor: explicit-bucket-histogram
        histogram-flavor-per-meter:
          http.server: base2-exponential-bucket-histogram
          database: explicit-bucket-histogram
        max-bucket-count: 160
~~~

Trong ví dụ:

- Các meter bắt đầu bằng `http.server` ưu tiên exponential histogram.
- Các meter bắt đầu bằng `database` dùng explicit histogram.
- Meter không khớp prefix nào dùng flavor mặc định là explicit.

Khi nhiều prefix khớp, Micrometer chọn prefix phân tách bằng dấu chấm dài nhất. Ví dụ, nếu map có cả `http` và `http.server`, meter `http.server.requests` dùng cấu hình `http.server`.

Tính năng per-meter hữu ích khi phần lớn metric cần explicit SLO, nhưng một nhóm Timer có miền giá trị rộng lại phù hợp với exponential histogram.

## 11. Giới hạn bucket riêng theo meter

Micrometer 1.15.0 cũng hỗ trợ `maxBucketsPerMeter` để ghi đè giới hạn bucket cho một số tên meter:

~~~yaml
management:
  otlp:
    metrics:
      export:
        max-bucket-count: 160
        max-buckets-per-meter:
          http.server.requests: 200
          database.query: 80
~~~

Trong ví dụ, các meter không có cấu hình riêng dùng giới hạn mặc định 160; `http.server.requests` có giới hạn 200; `database.query` có giới hạn 80.

Thiết lập này chỉ ảnh hưởng đến meter thực sự dùng exponential histogram. Nó không thay đổi số bucket của explicit histogram. Hãy kiểm tra phiên bản Spring Boot đang dùng có expose các property map này hay không; nếu framework chưa hỗ trợ binding, cấu hình trực tiếp qua `OtlpConfig` hoặc nâng phiên bản framework phù hợp.

## 12. Khi nào nên chọn explicit?

Chọn explicit histogram khi:

1. Dashboard hoặc SLO cần bucket đúng tại các ngưỡng đã thỏa thuận.
2. Backend chỉ hỗ trợ OTLP Histogram với explicit bounds.
3. Phân phối tập trung trong một miền đã biết và cần độ phân giải tùy chỉnh tại một vài vùng.
4. Cần đối chiếu bucket với quy tắc cảnh báo hoặc báo cáo hiện có.

Ví dụ, một API có SLO 300 ms và 1 giây cần các bucket ở đúng hai ranh giới đó. Exponential histogram có thể có bucket gần các giá trị này nhưng không bảo đảm trùng chính xác.

## 13. Khi nào nên chọn exponential?

Chọn Base2 Exponential Histogram khi:

1. Giá trị trải rộng qua nhiều bậc độ lớn, ví dụ từ microsecond đến hàng chục giây.
2. Không cần các ranh giới SLO tùy ý trong chính histogram đó.
3. OTLP receiver và backend hỗ trợ Exponential Histogram.
4. Muốn kiểm soát số bucket bằng scale và max bucket count.
5. Cần một cấu trúc histogram có thể giảm độ phân giải theo scale để tổng hợp ở độ phân giải thấp hơn.

Ví dụ, một dịch vụ xử lý nhiều loại payload có kích thước từ vài byte đến hàng chục megabyte. Exponential histogram có thể biểu diễn miền rộng đó với bucket được phân bố theo tỷ lệ.

Nếu yêu cầu vận hành là tỷ lệ payload dưới 100 KB, có thể dùng explicit SLO boundary cho meter này. Nếu chỉ muốn quan sát phân phối tổng quát qua nhiều bậc kích thước, exponential có thể phù hợp hơn.

## 14. Ảnh hưởng của publishPercentiles và publishPercentileHistogram

Micrometer có các cấu hình phân phối khác nhau. Với OTLP, kết quả data point thay đổi theo cấu hình:

| Cấu hình Timer/DistributionSummary | OTLP data point |
|---|---|
| Chỉ `publishPercentiles` | Summary chứa percentile tính phía ứng dụng |
| `publishPercentileHistogram` | Histogram hoặc Exponential Histogram theo OtlpConfig |
| `publishPercentiles` và `publishPercentileHistogram` | Histogram/Exponential Histogram được ưu tiên |
| `serviceLevelObjectives` | Histogram explicit |
| `publishPercentiles` và `serviceLevelObjectives` | Histogram explicit |

Không nên bật `publishPercentiles` chỉ vì muốn có p95 ở backend. Percentile tính phía ứng dụng không thể tổng hợp chính xác giữa nhiều instance bằng cách cộng hoặc lấy trung bình. Histogram buckets cho phép backend tổng hợp các bucket tương ứng trước khi tính percentile.

Với OTLP, Summary được xem là dạng cũ và không được khuyến nghị cho ứng dụng mới. Khi cần percentile tổng hợp, ưu tiên histogram phù hợp với backend.

## 15. Những meter nào có exponential histogram?

Micrometer OTLP hiện hỗ trợ Exponential Histogram cho:

- Timer.
- DistributionSummary.

Các meter khác có ánh xạ OTLP riêng:

- LongTaskTimer có thể được xuất dưới dạng Histogram hoặc Summary, nhưng không nằm trong danh sách exponential histogram.
- FunctionTimer xuất count và sum; không có bucket phân phối từ nguồn.
- Counter và FunctionCounter xuất Sum.
- Gauge, TimeGauge và MultiGauge xuất Gauge.

Không giả định `histogram-flavor` biến tất cả meter thành exponential. Nó chỉ có ý nghĩa với meter và cấu hình histogram mà OTLP registry hỗ trợ.

## 16. Tương thích với OTLP receiver và backend

OTLP là giao thức trung lập với nhà cung cấp, nhưng khả năng tiếp nhận và lưu trữ từng data point vẫn phụ thuộc collector, exporter và backend.

Trước khi chọn Exponential Histogram, hãy kiểm tra:

1. OTLP receiver có nhận ExponentialHistogram data point không?
2. Collector processor có giữ nguyên data point hay chuyển đổi nó?
3. Exporter phía sau có hỗ trợ exponential histogram không?
4. Backend lưu trữ có thể truy vấn percentile từ exponential histogram không?
5. Dashboard có hiển thị đúng count, sum, scale và bucket không?

Một pipeline có thể nhận OTLP thành công nhưng exporter phía sau không giữ nguyên loại histogram. Vì vậy, kiểm tra HTTP status của exporter chưa đủ; cần xác minh data point tại collector hoặc backend.

Nếu một thành phần trong pipeline chưa hỗ trợ Exponential Histogram, dùng explicit histogram cho meter đó hoặc nâng thành phần nhận. Không bật exponential cho toàn bộ ứng dụng trước khi xác nhận tương thích end-to-end.

## 17. Cardinality và chi phí

Histogram tạo thêm dữ liệu so với Counter đơn giản. Chi phí tăng theo:

- Số meter có bật histogram.
- Số tổ hợp tag của mỗi meter.
- Số instance.
- Số bucket hoặc scale/độ phân giải.
- Chu kỳ export và batch size.

Exponential histogram giới hạn số bucket bằng `maxBucketCount`, nhưng không loại bỏ cardinality do tag. Nếu mỗi request có một `request.id` khác nhau, số chuỗi thời gian vẫn tăng theo số request.

Các biện pháp kiểm soát:

1. Chỉ bật histogram cho Timer/DistributionSummary cần phân tích phân phối.
2. Dùng explicit SLO bucket khi có ngưỡng cụ thể; tránh tạo nhiều ranh giới không dùng.
3. Dùng scale và max bucket count vừa đủ cho exponential histogram.
4. Giữ tag có tập giá trị nhỏ như `method`, `outcome`, `region` hoặc nhóm dịch vụ.
5. Không đưa user ID, request ID, trace ID, order ID hoặc URL động vào tag.
6. Kiểm tra kích thước payload OTLP và bộ nhớ collector sau khi bật histogram.

Histogram flavor chỉ thay cấu trúc bucket. Nó không phải biện pháp kiểm soát cardinality của toàn bộ metric.

## 18. Kiểm thử lựa chọn histogram

Unit test với SimpleMeterRegistry có thể kiểm tra Timer/DistributionSummary ghi nhận count và thời lượng, nhưng không xác minh OTLP registry sẽ xuất explicit hay exponential histogram.

Để kiểm tra đúng loại data point, dùng một OTLP receiver thử nghiệm hoặc test server có thể giải mã payload:

1. Tạo OtlpMeterRegistry với cấu hình explicit.
2. Ghi một tập giá trị đã biết vào Timer hoặc DistributionSummary.
3. Chờ một chu kỳ publish hoặc kích hoạt publish theo cơ chế test.
4. Giải mã OTLP ExportMetricsServiceRequest ở receiver.
5. Xác minh data point là Histogram và có `explicitBounds` cùng `bucketCounts`.
6. Lặp lại với `BASE2_EXPONENTIAL_BUCKET_HISTOGRAM`.
7. Xác minh data point là ExponentialHistogram và có `scale`, `zeroCount`, dải bucket dương/âm.
8. Thử thêm cấu hình SLO và xác minh meter quay về explicit histogram.

Các giá trị kiểm thử nên tạo được bucket dễ xác định, ví dụ 50 ms, 200 ms, 700 ms cho Timer hoặc 1 KB, 8 KB, 64 KB cho DistributionSummary.

Ngoài loại data point, cần xác minh:

- Count và sum bằng tổng dữ liệu đã ghi.
- Đơn vị Timer được xuất đúng.
- Resource attributes có `service.name` mong muốn.
- Aggregation temporality là cumulative hoặc delta theo cấu hình.
- Scale và số bucket không vượt giới hạn đã chọn.
- Tag có cardinality được kiểm soát.

## 19. Các lỗi thường gặp

**Cho rằng exponential là mặc định.** OtlpConfig mặc định dùng explicit bucket histogram. Cần chọn `base2-exponential-bucket-histogram` khi muốn exponential.

**Dùng exponential với Micrometer 1.13 hoặc cũ hơn.** Các phiên bản này chưa có histogram flavor API. Nâng Micrometer lên 1.14.0 trở lên.

**Bật histogram flavor nhưng không bật histogram cho meter.** Flavor không thay thế cấu hình phân phối. Hãy bật `publishPercentileHistogram` hoặc cấu hình histogram phù hợp cho Timer/DistributionSummary.

**Kỳ vọng exponential giữ custom SLO boundaries.** Khi cấu hình `serviceLevelObjectives`, Micrometer dùng explicit histogram cho meter đó.

**Nhầm histogram flavor với aggregation temporality.** Explicit/exponential quyết định cấu trúc bucket; cumulative/delta quyết định khoảng thời gian của dữ liệu.

**Cho rằng maxScale là số bucket.** Scale điều khiển độ phân giải; maxBucketCount giới hạn số bucket.

**Dùng exponential cho LongTaskTimer hoặc FunctionTimer.** Micrometer chỉ hỗ trợ Exponential Histogram cho Timer và DistributionSummary.

**Chỉ kiểm tra exporter trả HTTP thành công.** Receiver có thể nhận nhưng backend downstream không hỗ trợ hoặc chuyển đổi data point. Kiểm tra payload và kết quả lưu trữ.

**Bật histogram cho mọi meter.** Bucket kết hợp với tag và số instance có thể làm tăng mạnh dữ liệu. Chỉ bật nơi có nhu cầu phân phối rõ ràng.

## 20. Checklist lựa chọn và triển khai

Trước khi đưa histogram vào môi trường vận hành, hãy xác minh:

- [ ] Micrometer version hỗ trợ histogram flavor mong muốn.
- [ ] Meter là Timer hoặc DistributionSummary nếu cần exponential histogram.
- [ ] Đã chọn explicit hoặc exponential theo yêu cầu SLO và miền giá trị.
- [ ] Đã hiểu explicit là mặc định.
- [ ] Đã bật histogram cho meter cần xuất bucket.
- [ ] Nếu dùng SLO boundaries, chấp nhận meter đó dùng explicit histogram.
- [ ] Nếu dùng exponential, đã chọn maxScale và maxBucketCount phù hợp.
- [ ] Nếu cấu hình per-meter, phiên bản Micrometer hỗ trợ từ 1.15.0.
- [ ] Đã phân biệt histogram flavor với aggregation temporality.
- [ ] OTLP receiver, collector và backend hỗ trợ data point đã chọn.
- [ ] Đã kiểm thử payload thực tế thay vì chỉ kiểm tra meter trong registry.
- [ ] Tag có cardinality thấp và payload nằm trong ngân sách.

## 21. Kết luận

Micrometer OTLP hỗ trợ explicit bucket histogram và Base2 Exponential Histogram cho Timer và DistributionSummary. Explicit histogram phù hợp khi cần bucket tại các ngưỡng SLO cụ thể; exponential histogram phù hợp với phân phối có miền giá trị rộng và cần giới hạn số bucket theo scale.

Explicit là lựa chọn mặc định. Khả năng chọn exponential có từ Micrometer 1.14.0; cấu hình flavor và số bucket riêng theo meter có từ 1.15.0. Khi khai báo SLO boundaries, Micrometer buộc dùng explicit histogram cho meter đó. Hãy phân biệt histogram flavor với cumulative/delta temporality, xác minh khả năng của receiver/backend và kiểm tra OTLP payload trước khi triển khai rộng.

## Tài liệu tham khảo

- [Micrometer – OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)
- [Micrometer 1.14 – OTLP Registry](https://docs.micrometer.io/micrometer/reference/1.14/implementations/otlp.html)
- [Micrometer – OtlpConfig](https://github.com/micrometer-metrics/micrometer/blob/main/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpConfig.java)
- [OpenTelemetry – Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
- [OpenTelemetry – Exponential Histograms](https://opentelemetry.io/blog/2022/exponential-histograms/)
