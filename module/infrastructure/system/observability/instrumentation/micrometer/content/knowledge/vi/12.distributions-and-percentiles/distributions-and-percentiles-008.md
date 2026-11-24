# Đánh đổi độ chính xác, bộ nhớ và số chuỗi công bố

Micrometer có thể công bố phân phối của thời lượng hoặc giá trị đo thông qua percentile, histogram và các ngưỡng Service Level Objective (SLO). Mỗi cách cung cấp một góc nhìn khác nhau. Percentile phía ứng dụng thuận tiện khi chỉ cần một số phân vị đã chọn; histogram cho backend dữ liệu theo bucket để tính phân vị và tổng hợp giữa nhiều instance; SLO bucket tập trung vào những ngưỡng vận hành cụ thể.

Bật càng nhiều thống kê thì chi phí bộ nhớ, lượng dữ liệu xuất và số chuỗi thời gian càng tăng. Thiết kế tốt bắt đầu từ câu hỏi vận hành cần trả lời, sau đó chọn số percentile hoặc bucket cần thiết, giới hạn phạm vi giá trị và giữ tag có cardinality thấp. Không có một cấu hình tối đa phù hợp cho mọi meter.

## 1. Phân phối và percentile trả lời câu hỏi gì?

Một giá trị trung bình có thể che khuất nhóm request chậm. Ví dụ, phần lớn request hoàn tất trong 100 ms nhưng một nhóm nhỏ mất vài giây. Trung bình có thể vẫn trông chấp nhận được trong khi người dùng gặp độ trễ cao.

Percentile mô tả vị trí của một giá trị trong phân phối. Với p95 bằng 400 ms, khoảng 95% số quan sát trong tập dữ liệu và cửa sổ tính toán có thời lượng không vượt quá mức xấp xỉ 400 ms; khoảng 5% còn lại cao hơn mức đó. Đây không phải là thời lượng trung bình và cũng không có nghĩa mọi request đều hoàn tất trong 400 ms.

| Thống kê | Câu hỏi trả lời | Hạn chế |
|---|---|---|
| Count | Có bao nhiêu lần đo? | Không cho biết thời lượng |
| Total time | Tổng thời gian tích lũy là bao nhiêu? | Không cho biết phân phối |
| Mean | Thời lượng trung bình là bao nhiêu? | Có thể che khuất đuôi phân phối |
| Max | Giá trị lớn nhất trong phạm vi lưu giữ là bao nhiêu? | Nhạy với một quan sát cực đoan và phụ thuộc cửa sổ |
| p50 | Mốc giữa phân phối nằm ở đâu? | Không mô tả nhóm chậm nhất |
| p95 / p99 | Đuôi phân phối có chậm đến mức nào? | Cần đủ mẫu và hiểu phạm vi tính toán |
| Histogram | Có bao nhiêu quan sát nằm trong các khoảng giá trị? | Số bucket ảnh hưởng kích thước dữ liệu |

Với Timer, đại lượng được phân phối là thời lượng. Với DistributionSummary, đại lượng là giá trị số được ứng dụng ghi nhận, chẳng hạn kích thước payload, số bản ghi trong batch hoặc lượng dữ liệu xử lý. Timer và DistributionSummary có thể hỗ trợ thống kê phân phối, nhưng đơn vị và cách diễn giải khác nhau.

## 2. Hai cách công bố percentile

Micrometer hỗ trợ hai cách tiếp cận phổ biến: tính percentile ở phía ứng dụng và công bố histogram để backend tính percentile.

### Percentile phía ứng dụng

Dùng cấu hình publishPercentiles để yêu cầu meter công bố một số phân vị đã chọn:

~~~java
Timer requestTimer = Timer.builder("http.server.requests.duration")
    .publishPercentiles(0.50, 0.95, 0.99)
    .register(meterRegistry);
~~~

Registry tính các giá trị phân vị trong phạm vi dữ liệu mà meter giữ và công bố chúng dưới dạng các chuỗi số liệu riêng. Cách này phù hợp khi dashboard chỉ cần một số percentile cố định và không cần tính lại phân vị từ bucket ở backend.

Điểm giới hạn quan trọng là percentile tính ở từng meter instance hoặc từng chuỗi tag không thể cộng gộp chính xác để tạo percentile của toàn bộ nhóm. Ví dụ, không thể lấy trung bình p95 của ba instance để suy ra p95 của cả dịch vụ. Muốn có percentile tổng hợp đúng cách, cần dữ liệu histogram có thể tổng hợp ở backend.

Percentile phía ứng dụng cũng làm tăng số chuỗi được xuất theo số quantile đã chọn. Nếu mỗi meter có nhiều tổ hợp tag, số chuỗi percentile tăng tương ứng.

### Histogram bucket phía backend

Dùng publishPercentileHistogram để công bố các bucket phân phối:

~~~java
Timer requestTimer = Timer.builder("http.server.requests.duration")
    .publishPercentileHistogram()
    .register(meterRegistry);
~~~

Backend nhận số lượng quan sát tích lũy theo bucket và có thể tính percentile bằng truy vấn của hệ thống đó. Với Prometheus, có thể dùng histogram_quantile trên các bucket rate đã tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_duration_seconds_bucket[5m])
  )
)
~~~

Giá trị percentile do histogram trả về là ước lượng dựa trên ranh giới bucket và phép nội suy của backend; nó không khôi phục từng mẫu thô. Bucket càng phù hợp và đủ chi tiết quanh vùng cần quan sát thì ước lượng càng hữu ích, nhưng thêm bucket làm tăng chi phí. Vì vậy, cần chọn độ phân giải dựa trên ngưỡng và vùng phân phối quan trọng.

Tên metric ví dụ phụ thuộc NamingConvention và registry đang dùng. Với nhiều instance, việc cộng các bucket theo nhãn bucket boundary trước khi tính quantile cho phép backend tính phân vị trên tổng phân phối. Nếu muốn phân tích theo route hoặc method, giữ các chiều đó trong phép nhóm; chỉ giữ những nhãn thực sự cần thiết.

Histogram phía backend phù hợp khi cần tổng hợp giữa instance, thay đổi percentile trong truy vấn hoặc dùng cùng dữ liệu cho nhiều dashboard. Đổi lại, mỗi bucket tạo thêm dữ liệu và chuỗi thời gian. Không bật histogram cho mọi meter một cách mặc định nếu chưa có nhu cầu.

## 3. Percentile và histogram không thể thay thế nhau trong mọi trường hợp

| Tiêu chí | Percentile phía ứng dụng | Histogram phía backend |
|---|---|---|
| Cách cấu hình | Chọn quantile như p50, p95, p99 | Bật percentile histogram hoặc khai báo bucket SLO |
| Nơi tính percentile | Trong ứng dụng/registry | Trong backend truy vấn |
| Tổng hợp nhiều instance | Không thể gộp percentile riêng thành percentile chính xác | Có thể tổng hợp bucket trước khi tính |
| Linh hoạt truy vấn | Chỉ các quantile đã cấu hình được công bố | Có thể tính quantile khác từ bucket có sẵn |
| Dữ liệu xuất | Một chuỗi cho mỗi quantile và tổ hợp tag | Một chuỗi cho mỗi bucket và tổ hợp tag |
| Chi phí | Bộ đệm thống kê phía ứng dụng và các chuỗi percentile | Bộ nhớ/cấu trúc histogram và nhiều chuỗi bucket |
| Khi phù hợp | Dashboard cố định, một meter instance hoặc không cần gộp percentile | Dịch vụ nhiều instance, truy vấn linh hoạt, SLO và phân tích phân phối tổng |

Có thể bật cả hai nếu có lý do rõ ràng, nhưng làm vậy sẽ cộng thêm chi phí của cả hai cách. Hãy tránh bật đồng thời chỉ vì muốn “có đủ dữ liệu”. Mỗi cấu hình cần gắn với một truy vấn, cảnh báo hoặc quyết định vận hành cụ thể.

## 4. SLO bucket là ngưỡng cần kiểm tra

Percentile trả lời một câu hỏi theo thứ hạng trong phân phối. SLO bucket đếm số quan sát nằm dưới các ngưỡng đã định trước. Ví dụ, đội vận hành có thể quan tâm có bao nhiêu request hoàn tất trong 100 ms, 300 ms hoặc 1 giây.

Với Timer, có thể cấu hình các ngưỡng bằng Duration:

~~~java
Timer.builder("checkout.duration")
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(meterRegistry);
~~~

Với DistributionSummary, các ngưỡng là giá trị số theo đơn vị nghiệp vụ của meter:

~~~java
DistributionSummary.builder("import.batch.records")
    .serviceLevelObjectives(100, 500, 1_000)
    .register(meterRegistry);
~~~

Các SLO boundary giúp backend biết số quan sát nằm trong hoặc dưới từng ngưỡng. Ví dụ, nếu có 10.000 request và bucket 300 ms chứa 9.700 quan sát, có thể suy ra khoảng 97% request không vượt quá ngưỡng đó trong tập dữ liệu được đo.

Khi backend nhận đúng bucket SLO tại ngưỡng 300 ms, số quan sát trong bucket đó là số đo trực tiếp cho điều kiện không vượt quá 300 ms. Đây khác với percentile được ước lượng giữa hai bucket; độ chính xác của phép kiểm tra ngưỡng phụ thuộc việc boundary cần thiết đã được xuất hay chưa.

SLO bucket không tự định nghĩa chính sách SLO hoàn chỉnh. Đội vận hành vẫn cần xác định cửa sổ đánh giá, điều kiện loại trừ, mẫu số, mục tiêu tỷ lệ và cách xử lý thiếu dữ liệu. Bucket chỉ cung cấp dữ liệu để truy vấn những điều kiện đó.

Cũng cần phân biệt SLO bucket với percentile. Một ngưỡng 300 ms trả lời có bao nhiêu request nằm trong giới hạn; p95 trả lời giá trị tại vị trí 95% của phân phối. Hai thông tin bổ sung cho nhau.

## 5. Giới hạn phạm vi giá trị kỳ vọng

Histogram cần biết khoảng giá trị đáng quan tâm. Với Timer, có thể giới hạn khoảng thời lượng kỳ vọng bằng minimumExpectedValue và maximumExpectedValue. Với DistributionSummary, các giá trị này nằm trong đơn vị của đại lượng được đo.

~~~java
Timer.builder("database.query.duration")
    .publishPercentileHistogram()
    .minimumExpectedValue(Duration.ofMillis(1))
    .maximumExpectedValue(Duration.ofSeconds(10))
    .register(meterRegistry);
~~~

Ví dụ với DistributionSummary:

~~~java
DistributionSummary.builder("message.payload.bytes")
    .publishPercentileHistogram()
    .minimumExpectedValue(1)
    .maximumExpectedValue(1_000_000)
    .register(meterRegistry);
~~~

Khoảng kỳ vọng nên dựa trên dữ liệu thực tế và mục tiêu phân tích. Nếu đặt giới hạn quá rộng, histogram có thể cần nhiều bucket hơn và tạo thêm dữ liệu. Nếu đặt giới hạn quá hẹp, độ chi tiết ở vùng quan trọng hoặc cách biểu diễn các giá trị ngoài khoảng có thể không đáp ứng mục tiêu. Hành vi chi tiết với giá trị ngoài khoảng và tập bucket được tạo phụ thuộc implementation, registry và phiên bản; hãy kiểm chứng dữ liệu xuất thực tế thay vì giả định mọi backend xử lý giống nhau.

Không đặt maximumExpectedValue chỉ dựa trên một request bình thường nếu hệ thống có thể gặp batch hoặc payload lớn hợp lệ. Hãy xem xét cả trường hợp hiếm nhưng hợp lệ, giới hạn nghiệp vụ và những giá trị cần cảnh báo.

## 6. Bộ đệm theo thời gian và độ ổn định thống kê

Một số thống kê phân phối, đặc biệt percentile và max, có phạm vi lưu giữ theo cửa sổ thời gian thay vì là lịch sử vô hạn. Micrometer cung cấp cấu hình expiry và bufferLength cho các thống kê dạng time-window.

- **expiry** xác định thời gian của mỗi cửa sổ con.
- **bufferLength** xác định số cửa sổ được giữ.
- Cửa sổ lưu giữ tổng thể phụ thuộc tích của expiry và bufferLength.

Ví dụ, nếu expiry là một phút và bufferLength là ba, phạm vi lưu giữ xấp xỉ ba phút. Cấu hình mặc định phụ thuộc loại registry và step của nó; cần xem xét cách registry xuất dữ liệu trước khi thay đổi.

~~~java
Timer.builder("worker.execution.duration")
    .publishPercentiles(0.50, 0.95)
    .distributionStatisticExpiry(Duration.ofMinutes(1))
    .distributionStatisticBufferLength(3)
    .register(meterRegistry);
~~~

Cửa sổ ngắn phản ứng nhanh với thay đổi nhưng thống kê có thể biến động mạnh khi số mẫu ít. Cửa sổ dài ổn định hơn nhưng phản ứng chậm với tình trạng mới. Khi điều chỉnh expiry hoặc bufferLength, cần cân bằng nhu cầu phản ánh tình trạng gần đây với chi phí bộ nhớ và độ ổn định của số liệu.

Không nhầm cửa sổ thống kê phía ứng dụng với khoảng thời gian truy vấn ở backend. Ví dụ, Prometheus có thể truy vấn rate trong năm phút trong khi percentile phía ứng dụng giữ dữ liệu theo cửa sổ riêng. Hai kết quả có thể không đại diện cùng một tập quan sát.

## 7. Chi phí bộ nhớ và số chuỗi thời gian

Bật thống kê phân phối tạo thêm trạng thái ở phía ứng dụng và dữ liệu ở phía backend. Có hai loại chi phí cần xem riêng:

1. **Bộ nhớ trong ứng dụng**: histogram, bộ đệm percentile, cửa sổ thời gian và trạng thái của từng meter ID.
2. **Số chuỗi ở backend**: mỗi tổ hợp tên meter, tag và bucket hoặc percentile có thể trở thành một chuỗi riêng.

Số chuỗi có thể tăng nhanh khi nhân các chiều:

- Nhiều meter name.
- Nhiều tổ hợp tag.
- Nhiều percentile hoặc bucket.
- Nhiều instance hoặc target.
- Nhiều môi trường hoặc cluster.

Ví dụ, một meter có 4 giá trị route, 3 giá trị method, 2 giá trị status class và 20 bucket. Số tổ hợp tối đa trước khi tính các chiều target/instance là 4 × 3 × 2 × 20 = 480 chuỗi bucket. Nếu có 10 instance, backend có thể nhận khoảng 4.800 chuỗi. Con số thực tế phụ thuộc các tổ hợp xuất hiện và cách backend lưu histogram, nhưng phép nhân này giúp thấy vì sao tag và bucket cần được kiểm soát cùng nhau.

Với percentile phía ứng dụng, nếu có 3 quantile thay vì 20 bucket, riêng phần percentile có thể tạo khoảng 3 chuỗi cho mỗi tổ hợp tag. Tuy nhiên, meter vẫn có thể xuất count, total time, max và các chuỗi cơ sở khác tùy registry. Vì vậy, không so sánh số chuỗi chỉ bằng số percentile hoặc bucket.

## 8. Cardinality của tag và thống kê phân phối

Tag có cardinality cao làm tăng số meter ID trước khi histogram hoặc percentile nhân thêm chuỗi. Không dùng các giá trị như request ID, user ID, order ID, session ID hoặc URL chứa định danh làm tag cho Timer và DistributionSummary.

Nên dùng giá trị hữu hạn:

| Tag | Giá trị phù hợp | Giá trị cần tránh |
|---|---|---|
| method | GET, POST, PUT, DELETE | Tên method tùy ý từ đầu vào |
| route | /orders/{id}, /payments | URL đầy đủ chứa ID |
| result | success, failure, rejected | Nội dung exception tự do |
| region | ap-southeast, eu-west | Địa chỉ IP hoặc tọa độ riêng lẻ |
| payload.type | json, xml, binary | Tên file hoặc object ID |

Không chỉ cardinality của từng tag mới quan trọng. Tổ hợp nhiều tag nhỏ vẫn có thể tạo ra rất nhiều meter ID. Trước khi bật histogram, hãy ước lượng số tổ hợp tag đồng thời với số bucket và số instance.

## 9. Chọn cấu hình theo câu hỏi vận hành

Không nên bật tất cả thống kê cho mọi meter. Có thể bắt đầu bằng các lựa chọn sau:

| Nhu cầu | Cấu hình gợi ý | Lý do |
|---|---|---|
| Chỉ cần count và total time | Timer mặc định | Chi phí thấp hơn, đủ cho lưu lượng và tổng thời gian |
| Dashboard cần p50 và p95 cố định của một instance | publishPercentiles(0.50, 0.95) | Công bố trực tiếp quantile cần xem |
| Cần p95 tổng hợp trên nhiều instance | publishPercentileHistogram() | Backend tổng hợp bucket rồi tính quantile |
| Cần kiểm tra tỷ lệ request dưới 300 ms | serviceLevelObjectives(...) | Bucket bám sát ngưỡng SLO |
| Phân phối kích thước payload | DistributionSummary với histogram hoặc SLO | Đo giá trị số không phải thời gian |
| Chỉ cần một số ngưỡng cụ thể | SLO bucket, không nhất thiết bật toàn histogram | Giảm dữ liệu không cần thiết |
| Cần điều tra vùng đuôi hiếm | Histogram với phạm vi và bucket phù hợp | Có thể truy vấn nhiều quantile và ngưỡng |

Ví dụ cấu hình Timer kết hợp histogram và SLO:

~~~java
Timer.builder("checkout.duration")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .minimumExpectedValue(Duration.ofMillis(1))
    .maximumExpectedValue(Duration.ofSeconds(10))
    .register(meterRegistry);
~~~

Chỉ bật cả histogram và SLO khi có nhu cầu rõ ràng. Một số registry có thể kết hợp SLO boundary với bucket histogram, làm số bucket xuất tăng. Kiểm tra cấu hình hiệu lực và output của backend để biết chính xác số chuỗi.

## 10. Ví dụ truy vấn histogram và SLO trên Prometheus

Với Timer được xuất dưới dạng histogram Prometheus, có thể tính p95 trên tất cả instance bằng cách tổng hợp bucket trước:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_duration_seconds_bucket[5m])
  )
)
~~~

Nếu muốn p95 theo route, giữ route trong phép nhóm:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(checkout_duration_seconds_bucket[5m])
  )
)
~~~

Để tính tỷ lệ request không vượt quá 300 ms, dùng bucket tương ứng với ngưỡng 0,3 giây và tổng số request:

~~~promql
sum(rate(checkout_duration_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(checkout_duration_seconds_count[5m]))
~~~

Tên metric, đơn vị và nhãn bucket phải khớp dữ liệu thực tế được registry xuất. Nếu base time unit là giây thì ngưỡng 300 ms tương ứng 0,3 giây. Không sao chép truy vấn mà chưa xác minh tên metric và đơn vị ở backend.

Histogram bucket của Prometheus thường là bucket tích lũy: bucket có giới hạn lớn hơn bao gồm các quan sát thuộc bucket nhỏ hơn. Khi tổng hợp, cần giữ nhãn **le** để không trộn các ranh giới. Nếu xóa nhãn này trước khi tính histogram_quantile, backend không còn thông tin bucket để ước lượng phân vị.

## 11. Kiểm chứng cấu hình và dữ liệu thực tế

Cấu hình builder chỉ thể hiện ý định. Kết quả công bố cuối cùng còn phụ thuộc registry, backend, NamingConvention, phiên bản Micrometer và các MeterFilter được áp dụng.

Khi kiểm chứng, hãy:

1. Đăng ký meter với cấu hình mong muốn trong một registry đại diện cho môi trường sử dụng.
2. Ghi các giá trị mẫu ở gần minimum, các ngưỡng SLO, vùng giữa và gần maximum.
3. Kiểm tra count và total time hoặc total amount vẫn đúng.
4. Xem các percentile được công bố có đúng quantile đã chọn không.
5. Xem histogram bucket và SLO boundary thực tế ở endpoint/exporter.
6. Đếm số chuỗi sinh ra cho một tổ hợp tag và nhân với số instance dự kiến.
7. Kiểm tra truy vấn percentile sau khi tổng hợp nhiều instance.
8. Thử một meter có tag cardinality lớn trong môi trường kiểm thử để xác nhận giới hạn và cảnh báo, không dùng dữ liệu nhạy cảm thật.

Có thể dùng SimpleMeterRegistry để kiểm tra cấu hình meter và các phép đo cơ bản trong bộ nhớ, nhưng không nên xem nó là bằng chứng đầy đủ về số bucket hoặc cách xuất của một registry cụ thể. Kiểm thử tích hợp với backend đích là cần thiết khi quyết định phụ thuộc vào cấu trúc histogram được xuất.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Lấy trung bình p95 từ nhiều instance | Percentile tổng hợp sai | Tổng hợp histogram bucket rồi tính quantile |
| Bật histogram cho mọi meter | Tăng bộ nhớ và số chuỗi không cần thiết | Chỉ bật nơi có truy vấn hoặc SLO cần thiết |
| Chọn quá nhiều percentile | Tạo thêm chuỗi và trạng thái trong ứng dụng | Chỉ giữ quantile cần theo dõi |
| Đặt expected range quá rộng | Có thể tăng số bucket và chi phí | Chọn khoảng dựa trên dữ liệu và giới hạn nghiệp vụ |
| Đặt expected range quá hẹp | Mất độ chi tiết ở vùng giá trị quan trọng | Kiểm tra cả giá trị cực đoan hợp lệ |
| Dùng tag có ID riêng | Nhân cardinality với từng bucket/quantile | Dùng tag hữu hạn và trace cho chi tiết từng request |
| Nhầm SLO bucket với percentile | Đọc sai ý nghĩa dữ liệu | Phân biệt ngưỡng giá trị với thứ hạng phân phối |
| Truy vấn sai đơn vị | Kết quả ngưỡng và percentile sai | Đối chiếu base unit và tên metric xuất |
| So sánh các cửa sổ khác nhau | Kết luận không nhất quán | Ghi rõ phạm vi thời gian của thống kê và truy vấn |

## 13. Checklist thiết kế

- [ ] Đã xác định câu hỏi cần trả lời: percentile, histogram hay ngưỡng SLO.
- [ ] Chỉ bật percentile phía ứng dụng cho những quantile thực sự cần công bố.
- [ ] Dùng histogram khi cần tổng hợp phân phối giữa nhiều instance hoặc truy vấn linh hoạt.
- [ ] Chọn SLO boundary từ mục tiêu vận hành cụ thể.
- [ ] Đặt minimumExpectedValue và maximumExpectedValue theo phạm vi dữ liệu hợp lệ.
- [ ] Chọn expiry và bufferLength phù hợp với cửa sổ quan sát.
- [ ] Ước lượng số bucket hoặc quantile nhân với tổ hợp tag và instance.
- [ ] Giữ tag có cardinality thấp.
- [ ] Xác minh đơn vị và tên metric thực tế ở backend.
- [ ] Kiểm thử số liệu và số chuỗi với registry/backend đích trước khi mở rộng cấu hình.

Phân phối và percentile giúp nhìn thấy vùng chậm mà trung bình không thể hiện. Percentile phía ứng dụng đơn giản khi cần một số quantile cố định; histogram linh hoạt và có thể tổng hợp giữa các instance; SLO bucket đo trực tiếp những ngưỡng vận hành đã chọn. Mỗi thống kê đều tiêu tốn bộ nhớ hoặc số chuỗi, vì vậy hãy bắt đầu từ câu hỏi cần trả lời, giới hạn tag và bucket, rồi kiểm chứng dữ liệu thực tế trước khi áp dụng rộng rãi.

