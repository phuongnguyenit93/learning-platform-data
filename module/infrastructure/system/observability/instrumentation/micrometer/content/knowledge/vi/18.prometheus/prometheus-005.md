# Các chuỗi count, sum, max và bucket từ một Timer

## Một Timer được Prometheus biểu diễn thành nhiều chuỗi

Micrometer cung cấp Timer để đo thời lượng và số lần một thao tác được thực hiện. Khi dùng Prometheus registry, một Timer không nhất thiết xuất hiện dưới dạng một metric duy nhất. Registry ánh xạ dữ liệu của Timer thành nhiều chuỗi Prometheus, mỗi chuỗi phục vụ một phép phân tích khác nhau.

Với Timer tên là checkout.payment, Prometheus thường nhận các chuỗi có dạng:

| Chuỗi | Ý nghĩa | Kiểu dữ liệu thường gặp |
|---|---|---|
| checkout_payment_seconds_count | Số lần thao tác đã được ghi nhận | Counter tích lũy |
| checkout_payment_seconds_sum | Tổng thời gian của các lần ghi nhận, tính bằng giây | Counter tích lũy |
| checkout_payment_seconds_max | Thời lượng lớn nhất theo thống kê max của Micrometer | Gauge |
| checkout_payment_seconds_bucket | Số quan sát nằm trong bucket có giới hạn le | Histogram bucket, các bucket tích lũy |

Tên thực tế phụ thuộc tên Timer, NamingConvention và phiên bản registry. Dấu chấm trong tên meter thường được chuyển thành dấu gạch dưới; Timer dùng đơn vị thời gian cơ sở là giây trong Prometheus. Vì vậy, một Timer được ghi bằng mili giây trong mã Java vẫn thường được xuất theo giây ở Prometheus.

Không nên coi bốn chuỗi này là bốn cách viết khác nhau của cùng một giá trị. Count cho biết có bao nhiêu lần ghi nhận; sum cho biết tổng thời gian; max phản ánh cực đại theo cửa sổ thống kê của Micrometer; bucket mô tả phân phối thời lượng theo các ngưỡng. Mỗi chuỗi có semantics và cách truy vấn riêng.

## Đăng ký Timer cho Prometheus

### Tạo Timer trong ứng dụng

Có thể đăng ký Timer thông qua MeterRegistry được Spring Boot inject:

~~~java
Timer paymentTimer = Timer.builder("checkout.payment")
    .description("Thoi gian xu ly thanh toan")
    .tag("outcome", "success")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Sau đó ghi thời lượng:

~~~java
paymentTimer.record(() -> paymentService.charge(command));
~~~

Timer tự đo thời gian thực thi và ghi nhận một observation khi khối lệnh kết thúc. Có thể dùng Timer.Sample nếu cần tách thời điểm bắt đầu và kết thúc hoặc chỉ biết tag outcome sau khi xử lý.

Trong ví dụ, publishPercentileHistogram yêu cầu registry xuất histogram phù hợp để Prometheus có thể tính percentile từ bucket. Các ngưỡng serviceLevelObjectives bổ sung các ranh giới bucket phục vụ mục tiêu dịch vụ. Cấu hình cụ thể và khả năng xuất còn phụ thuộc phiên bản Micrometer Prometheus registry.

Không cần gọi increment riêng cho count hoặc cộng sum bằng tay. Timer quản lý count và tổng thời gian từ các lần record.

### Prometheus scrape endpoint

Với Spring Boot Actuator và dependency Prometheus registry tương ứng, ứng dụng thường cung cấp endpoint metrics để Prometheus scrape, ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    prometheus:
      access: read-only
~~~

Cấu hình cụ thể phụ thuộc phiên bản Spring Boot. Prometheus scrape endpoint được expose bởi Actuator; cần bảo vệ endpoint theo chính sách mạng và bảo mật của môi trường triển khai.

Ví dụ cấu hình scrape ở Prometheus:

~~~yaml
scrape_configs:
  - job_name: "checkout-service"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["checkout-service:8080"]
~~~

Khi endpoint được scrape, registry xuất các chuỗi đã ánh xạ từ Timer. Hãy truy cập dữ liệu exposition thực tế để xác nhận tên, đơn vị, tag/label và sự hiện diện của histogram bucket trước khi viết dashboard hoặc alert.

## Chuỗi count: số lần thao tác được ghi nhận

### Count là bộ đếm tích lũy

Chuỗi _count biểu diễn tổng số lần Timer đã ghi nhận. Với Prometheus registry, đây là một counter tích lũy. Mỗi lần Timer record hoàn tất, count tăng một.

Ví dụ, nếu ứng dụng ghi nhận 120 lần thanh toán, chuỗi checkout_payment_seconds_count có giá trị 120. Sau 30 lần tiếp theo, giá trị trở thành 150.

Nếu không có thao tác mới, count cumulative giữ nguyên ở lần scrape tiếp theo. Điều này không có nghĩa ứng dụng vẫn đang xử lý request; nó chỉ là tổng số quan sát đã được ghi nhận trong vòng đời series.

### Tính throughput bằng rate

Để tính tốc độ hoàn tất thao tác trung bình mỗi giây trong 5 phút gần nhất:

~~~promql
sum by (service) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

rate tính tốc độ từ mức tăng của counter trong cửa sổ và xử lý counter reset theo semantics của Prometheus. Khi tổng hợp nhiều instance, nên tính rate trên từng series trước rồi mới sum theo service. Nếu sum counter trước khi rate, một instance restart có thể làm mức giảm của nó bị che khuất bởi mức tăng của instance khác.

Để ước lượng số lần hoàn tất trong một giờ:

~~~promql
sum by (service) (
  increase(checkout_payment_seconds_count[1h])
)
~~~

increase trả về mức tăng ước lượng trong cửa sổ, có tính đến reset. Kết quả có thể là số thực do Prometheus nội suy theo khoảng mẫu; không nhất thiết là số nguyên chính xác của một bộ đếm sự kiện.

### Count không phải số thao tác đang chạy

Count chỉ tăng khi Timer ghi nhận observation. Với Timer.record, điều đó thường xảy ra khi khối xử lý kết thúc. Nó không cho biết số thao tác đang chạy ở thời điểm hiện tại.

Nếu cần số request đang hoạt động, hãy dùng Gauge hoặc instrumentation chuyên biệt cho active requests. Nếu cần theo dõi tác vụ dài đang chạy, cân nhắc LongTaskTimer. Không dùng _count để trả lời câu hỏi về concurrency hiện tại.

## Chuỗi sum: tổng thời gian đã ghi nhận

### Sum được xuất theo giây

Chuỗi _sum biểu diễn tổng thời gian của tất cả observation Timer đã ghi nhận. Trong Prometheus, thời gian thường được chuẩn hóa về giây.

Ví dụ, ba lần xử lý mất 100 ms, 200 ms và 700 ms có tổng thời gian là 1 giây. Count bằng 3, sum bằng 1.0 giây.

Nếu ứng dụng ghi một Duration bằng mili giây, Micrometer chuyển đổi sang đơn vị xuất của registry. Không tự nhân hoặc chia giá trị ở truy vấn nếu metric đã được chuẩn hóa thành giây.

### Tính tổng thời gian xử lý trong một cửa sổ

Để ước lượng tổng thời gian xử lý được ghi nhận trong 5 phút gần nhất:

~~~promql
sum by (service) (
  increase(checkout_payment_seconds_sum[5m])
)
~~~

Đây là tổng mức tăng của sum counter trong cửa sổ. Nó có đơn vị giây. Giá trị có thể lớn hơn độ dài cửa sổ nếu nhiều thao tác chạy đồng thời, vì sum cộng thời lượng của từng thao tác, không phải thời gian tường đồng hồ của toàn hệ thống.

### Tính thời gian trung bình

Mean duration trong 5 phút gần nhất có thể được tính bằng rate của sum chia cho rate của count:

~~~promql
sum by (service) (
  rate(checkout_payment_seconds_sum[5m])
)
/
sum by (service) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

Tử số có đơn vị giây mỗi giây; mẫu số có đơn vị thao tác mỗi giây. Tỷ số có đơn vị giây mỗi thao tác, tức thời lượng trung bình của một thao tác trong cửa sổ.

Cần xử lý trường hợp không có thao tác hoàn tất trong cửa sổ. Khi rate của count bằng 0 hoặc không có series, phép chia không tạo ra mean có ý nghĩa. Dashboard nên hiển thị không có dữ liệu hoặc trạng thái phù hợp, không diễn giải thành latency bằng 0.

Nếu cần nhóm theo outcome hoặc route, hãy giữ cùng các label trong cả tử số và mẫu số:

~~~promql
sum by (service, outcome) (
  rate(checkout_payment_seconds_sum[5m])
)
/
sum by (service, outcome) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

Hai phía của phép chia phải được tổng hợp theo cùng tập chiều để mỗi nhóm được chia với đúng count tương ứng.

## Chuỗi max: cực đại theo thống kê của Micrometer

### Max không phải counter tích lũy

Chuỗi _max thường được Prometheus registry xuất dưới dạng Gauge. Nó biểu diễn giá trị lớn nhất trong phạm vi thống kê max mà Micrometer duy trì, thường gắn với expiry và buffer length của distribution statistics.

Khác với count và sum, max không tăng đơn điệu. Khi observation lớn nhất cũ hết hạn khỏi cửa sổ thống kê, max có thể giảm hoặc trở về 0 nếu không còn observation trong cửa sổ. Giá trị này không nhất thiết là max lifetime của mọi thao tác kể từ khi tiến trình khởi động.

Ví dụ, nếu một request mất 2 giây và đó là observation lớn nhất trong cửa sổ, _max có thể là 2.0. Sau khi cửa sổ hết hạn mà không có observation mới, max có thể trở về 0. Điều đó không có nghĩa ứng dụng vừa ghi nhận một request mất 0 giây; nó có nghĩa cửa sổ hiện không còn mẫu đóng góp cho max.

### Truy vấn max theo service

Nếu cần xem max hiện tại trong từng service, có thể dùng:

~~~promql
max by (service) (
  checkout_payment_seconds_max
)
~~~

Phép max ở đây lấy giá trị lớn nhất của các Gauge max từ những series thuộc cùng service tại thời điểm truy vấn. Nó không tạo ra max lifetime nếu từng instance chỉ giữ max theo cửa sổ.

Không dùng rate hoặc increase trên _max vì đây là Gauge, không phải counter. Cũng không dùng sum để biểu diễn độ trễ lớn nhất. Nếu cần cực đại của các observation trong một khoảng truy vấn, cần dữ liệu phù hợp cho phép tính đó, thường là histogram hoặc một metric max có semantics cửa sổ được hiểu rõ.

### Cấu hình expiry và buffer length

Micrometer có các tùy chọn như distributionStatisticExpiry và distributionStatisticBufferLength để điều chỉnh thời gian thống kê phân phối giữ ảnh hưởng của observation cũ. Cửa sổ xấp xỉ bằng expiry nhân buffer length.

Ví dụ:

~~~java
Timer timer = Timer.builder("checkout.payment")
    .distributionStatisticExpiry(Duration.ofMinutes(1))
    .distributionStatisticBufferLength(3)
    .register(registry);
~~~

Cấu hình này giữ thống kê theo cửa sổ xấp xỉ ba phút. Thời gian chính xác và cách áp dụng phụ thuộc implementation của Micrometer và registry. Không nhầm expiry với scrape interval của Prometheus: expiry điều khiển thống kê nội bộ của meter, còn scrape interval điều khiển thời điểm Prometheus đọc endpoint.

## Histogram bucket: phân phối số lần quan sát theo ngưỡng

### Bucket biểu diễn số quan sát không vượt quá ngưỡng

Khi histogram được bật, Prometheus nhận các chuỗi có hậu tố _bucket và label đặc biệt le (less than or equal). Giá trị bucket là số observation có thời lượng nhỏ hơn hoặc bằng ngưỡng le.

Ví dụ minh họa một histogram:

~~~text
checkout_payment_seconds_bucket{le="0.1"}  40
checkout_payment_seconds_bucket{le="0.3"}  85
checkout_payment_seconds_bucket{le="1.0"}  98
checkout_payment_seconds_bucket{le="+Inf"} 100
checkout_payment_seconds_count             100
~~~

Diễn giải:

- 40 observation có thời lượng không quá 0,1 giây.
- 85 observation có thời lượng không quá 0,3 giây.
- 98 observation có thời lượng không quá 1 giây.
- 100 observation có thời lượng bất kỳ, vì bucket +Inf bao phủ toàn bộ mẫu.

Bucket của histogram Prometheus là bucket tích lũy. Giá trị ở ngưỡng 0,3 giây đã bao gồm các observation nằm trong bucket 0,1 giây. Không cộng 40 và 85 để suy ra số observation dưới 0,3 giây; số đó đã là 85.

Với histogram cổ điển, bucket +Inf phải tương ứng tổng số observation và khớp với _count. Nếu dữ liệu không khớp, hãy kiểm tra cách exporter ánh xạ histogram hoặc dữ liệu bị thiếu trong pipeline.

### Bật histogram cho Timer

Có thể yêu cầu Micrometer xuất histogram:

~~~java
Timer timer = Timer.builder("checkout.payment")
    .publishPercentileHistogram()
    .register(registry);
~~~

Có thể bổ sung SLO boundaries:

~~~java
Timer timer = Timer.builder("checkout.payment")
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Các ngưỡng SLO giúp có bucket tại những ranh giới nghiệp vụ quan trọng. Nếu bật percentile histogram, registry có thể xuất thêm các bucket dựa trên dải cấu hình của Micrometer; tập bucket và số lượng chuỗi phụ thuộc registry và cấu hình.

Histogram hữu ích khi cần tổng hợp phân phối giữa nhiều instance. Các bucket cùng ngưỡng có thể được cộng theo label còn lại rồi dùng histogram_quantile để ước lượng percentile toàn hệ thống.

### Tính p95 từ histogram

Ví dụ tính p95 độ trễ theo service:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(checkout_payment_seconds_bucket[5m])
  )
)
~~~

Trình tự quan trọng:

1. rate tính tốc độ tăng của từng bucket cumulative trong cửa sổ 5 phút.
2. sum cộng các bucket tương ứng giữa các instance theo le và service.
3. histogram_quantile ước lượng phân vị 95 từ histogram đã tổng hợp.

Không bỏ label le trước khi gọi histogram_quantile, vì le chứa ranh giới bucket cần thiết để nội suy phân vị. Nếu muốn phân vị theo outcome, thêm outcome vào nhóm tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, outcome) (
    rate(checkout_payment_seconds_bucket[5m])
  )
)
~~~

Kết quả là ước lượng từ các bucket, không phải percentile chính xác tuyệt đối của từng observation. Độ chính xác phụ thuộc ranh giới bucket và phân phối dữ liệu. Nếu bucket quá thưa quanh vùng p95, sai số nội suy có thể lớn.

### Bucket phải tương thích giữa các instance

Để tổng hợp histogram giữa nhiều instance, chúng cần có cùng ranh giới bucket và cùng đơn vị. Nếu một instance xuất bucket 0,1; 0,3; 1,0 giây nhưng instance khác dùng các ngưỡng khác, phép cộng theo le có thể tạo ra histogram sai hoặc thiếu bucket.

Cần cấu hình thống nhất percentile histogram và SLO boundaries trên mọi instance thuộc cùng dịch vụ. Cũng cần kiểm tra khi rollout phiên bản mới để tránh một khoảng thời gian các instance dùng cấu hình bucket khác nhau.

## Percentile phía client khác histogram bucket

Micrometer có thể xuất percentile được tính ở phía ứng dụng bằng publishPercentiles(...). Những giá trị này thường được xuất dưới dạng series có tag quantile.

Ví dụ:

~~~java
Timer timer = Timer.builder("checkout.payment")
    .publishPercentiles(0.5, 0.95, 0.99)
    .register(registry);
~~~

Percentile phía client được tính riêng ở từng instance. Không thể cộng hoặc lấy trung bình p95 của các instance để có p95 toàn hệ thống. Một instance có ít request và một instance có nhiều request không đóng góp ngang nhau; hơn nữa percentile không phải đại lượng cộng được.

Histogram bucket khác ở chỗ dữ liệu bucket có thể được cộng giữa các instance nếu ranh giới bucket tương thích. Sau đó Prometheus tính percentile từ histogram đã tổng hợp.

| Đặc điểm | Percentile phía client | Histogram bucket |
|---|---|---|
| Nơi tính percentile | Trong ứng dụng/registry | Trong Prometheus qua truy vấn |
| Tổng hợp nhiều instance | Không thể cộng percentile để ra percentile toàn hệ thống | Có thể cộng bucket tương thích |
| Độ chính xác | Phụ thuộc thuật toán và cấu hình client | Ước lượng theo ranh giới bucket |
| Chi phí | Tính toán và lưu thống kê trong ứng dụng | Tăng số chuỗi dữ liệu và chi phí backend |
| Phù hợp | Quan sát phân vị cục bộ | Phân vị tổng hợp và SLO toàn dịch vụ |

Không bật cả percentile phía client và histogram nếu dashboard không sử dụng cả hai. Mỗi chiều thống kê bổ sung có thể làm tăng bộ nhớ và số chuỗi dữ liệu.

## Tổng hợp đúng các chuỗi Timer

### Throughput

~~~promql
sum by (service) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

Cho biết số thao tác hoàn tất trung bình mỗi giây trong cửa sổ 5 phút.

### Mean latency

~~~promql
sum by (service) (
  rate(checkout_payment_seconds_sum[5m])
)
/
sum by (service) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

Cho biết thời lượng trung bình của các thao tác hoàn tất trong cửa sổ. Đơn vị là giây mỗi thao tác.

### p95 latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(checkout_payment_seconds_bucket[5m])
  )
)
~~~

Cho biết p95 ước lượng từ histogram bucket đã tổng hợp. Cần bật histogram và giữ bucket tương thích.

### Current max window

~~~promql
max by (service) (
  checkout_payment_seconds_max
)
~~~

Cho biết giá trị max đang được từng instance công bố, sau đó lấy max giữa các instance. Phạm vi thời gian phụ thuộc expiry và buffer length của Micrometer.

### Tổng số thao tác trong một giờ

~~~promql
sum by (service) (
  increase(checkout_payment_seconds_count[1h])
)
~~~

Cho biết mức tăng count ước lượng trong một giờ, có xử lý reset của counter theo Prometheus.

Không dùng một truy vấn duy nhất cho tất cả các chuỗi. Count và sum là cumulative counter; max là gauge; bucket là các bộ đếm tích lũy theo từng ngưỡng. Viết query theo đúng loại dữ liệu giúp tránh rate sai, cộng nhầm hoặc diễn giải sai cửa sổ.

## Xử lý counter reset và vòng đời tiến trình

Count và sum của Timer trong Prometheus được xuất theo semantics counter tích lũy. Khi tiến trình restart, giá trị có thể bắt đầu lại. Prometheus rate và increase được thiết kế để xử lý counter reset trong một series.

Khi tổng hợp nhiều instance, nên áp dụng rate hoặc increase cho từng series trước khi sum. Ví dụ:

~~~promql
sum by (service) (
  rate(checkout_payment_seconds_count[5m])
)
~~~

Cách này giữ khả năng nhận diện reset của từng instance. Nếu sum raw counter trước rồi mới rate, một instance giảm về 0 có thể bị mức tăng ở instance khác che khuất.

Nếu instance label thay đổi sau restart, Prometheus có thể coi đó là series mới. Khi instance identity được tái sử dụng, cần hiểu cách backend nhận diện reset. Không dùng _max để phát hiện reset vì max là gauge và có thể giảm tự nhiên khi cửa sổ thống kê hết hạn.

## Tag, label và cardinality của Timer

Mỗi tag của Timer trở thành một chiều label trong Prometheus. Ví dụ outcome=success hoặc outcome=failure tạo các series riêng cho count, sum, max và từng bucket.

Số chuỗi có thể tăng nhanh khi kết hợp nhiều chiều. Nếu Timer có 5 giá trị method, 4 giá trị outcome, 8 giá trị region và 20 bucket, histogram có thể tạo số series lớn theo tích các chiều này, cộng thêm các chuỗi count/sum/max.

Nên dùng tag có tập giá trị hữu hạn:

- method: GET, POST, PUT, DELETE.
- outcome: success, failure, timeout.
- region: các vùng triển khai được cấu hình.
- operation: nhóm thao tác nghiệp vụ ổn định.

Tránh request ID, user ID, order ID, session ID, URL đầy đủ hoặc exception message. Các giá trị duy nhất làm cardinality tăng theo từng request và có thể gây quá tải Prometheus.

Khi dùng histogram, cần tính cả số bucket trong ngân sách cardinality. Bật percentile histogram cho một Timer có nhiều tag không giới hạn có thể tạo ra lượng time series rất lớn.

## Kiểm tra dữ liệu exposition thực tế

Tên và chuỗi cụ thể có thể thay đổi theo phiên bản Micrometer, Prometheus registry, NamingConvention và cấu hình histogram. Vì vậy, sau khi tích hợp cần kiểm tra endpoint exposition.

Ví dụ một phần dữ liệu có thể trông như sau:

~~~text
# HELP checkout_payment_seconds Timer duration histogram
# TYPE checkout_payment_seconds histogram
checkout_payment_seconds_bucket{outcome="success",service="checkout",le="0.1"} 40
checkout_payment_seconds_bucket{outcome="success",service="checkout",le="0.3"} 110
checkout_payment_seconds_bucket{outcome="success",service="checkout",le="+Inf"} 120
checkout_payment_seconds_count{outcome="success",service="checkout"} 120
checkout_payment_seconds_sum{outcome="success",service="checkout"} 8.42

# HELP checkout_payment_seconds_max
# TYPE checkout_payment_seconds_max gauge
checkout_payment_seconds_max{outcome="success",service="checkout"} 0.31
~~~

Đây là ví dụ minh họa hình dạng dữ liệu. Trong exposition thực tế, HELP/TYPE và tên metric histogram có thể được nhóm hoặc xuất theo định dạng cụ thể của registry. Hãy dùng chính dữ liệu tại endpoint của ứng dụng để xác nhận.

Kiểm tra ít nhất:

1. Count tăng một lần cho mỗi lần Timer ghi nhận.
2. Sum tăng theo tổng thời lượng đã chuẩn hóa thành giây.
3. Max phản ánh thống kê max hiện hành và có thể giảm khi dữ liệu hết hạn.
4. Bucket có label le và giá trị tích lũy không giảm theo ngưỡng.
5. Bucket +Inf khớp count của histogram.
6. Các label có tập giá trị đúng và cardinality được kiểm soát.
7. Query rate, mean và histogram_quantile trả về kết quả có đơn vị và phạm vi đúng.

## Tích hợp kiểm thử với Prometheus registry

Có thể tạo PrometheusMeterRegistry trong kiểm thử và đọc exposition để xác minh các chuỗi được xuất. Cách khởi tạo cụ thể phụ thuộc phiên bản Micrometer Prometheus registry đang dùng.

Ví dụ minh họa:

~~~java
PrometheusMeterRegistry registry = new PrometheusMeterRegistry(
    PrometheusConfig.DEFAULT
);

Timer timer = Timer.builder("checkout.payment")
    .publishPercentileHistogram()
    .register(registry);

timer.record(Duration.ofMillis(100));
timer.record(Duration.ofMillis(300));

String exposition = registry.scrape();

assertThat(exposition)
    .contains("checkout_payment_seconds_count")
    .contains("checkout_payment_seconds_sum")
    .contains("checkout_payment_seconds_bucket");
~~~

Test này xác nhận các chuỗi quan trọng xuất hiện trong exposition. Để xác minh giá trị chính xác, nên parse exposition hoặc kiểm tra mẫu có label cụ thể thay vì chỉ tìm chuỗi con.

Không nên phụ thuộc thứ tự dòng trong exposition vì registry có thể sắp xếp hoặc nhóm output khác nhau giữa các phiên bản. Nếu kiểm tra histogram, xác nhận bucket boundary và count thực tế, đồng thời kiểm tra cấu hình SLO có được phản ánh như mong đợi.

## Những sai lầm thường gặp

**Coi count và sum là gauge.** Đây là các counter tích lũy trong Prometheus exposition. Dùng rate hoặc increase để tính mức tăng theo thời gian.

**Dùng rate trên max.** _max là gauge có thể giảm khi cửa sổ hết hạn. Truy vấn trực tiếp hoặc tổng hợp max theo chiều phù hợp.

**Coi max là max lifetime.** Max của Micrometer thường chịu expiry và buffer length. Cần đọc đúng phạm vi thống kê.

**Cộng các percentile phía client giữa nhiều instance.** Percentile không cộng được. Dùng histogram bucket tương thích để tính percentile tổng hợp.

**Quên bật histogram nhưng vẫn truy vấn _bucket.** Nếu không cấu hình publishPercentileHistogram hoặc SLO phù hợp, bucket có thể không được xuất. Kiểm tra exposition trước khi viết histogram_quantile.

**Cộng các bucket khác ranh giới.** Bucket giữa các instance phải tương thích. Nếu không, histogram tổng hợp không còn đáng tin cậy.

**Nhầm le là bucket rời rạc.** Bucket Prometheus là tích lũy: bucket 0,3 giây đã bao gồm bucket 0,1 giây.

**Tính mean bằng sum lifetime chia count của cửa sổ.** Tử số và mẫu số phải cùng phạm vi thời gian. Dùng rate của sum chia rate của count cho mean trong cửa sổ.

**Sum counter trước khi rate.** Việc này có thể che giấu reset của một instance. Tính rate từng series rồi mới sum.

**Không tính cardinality của histogram.** Mỗi tổ hợp label nhân với nhiều bucket tạo ra nhiều time series. Giữ tag hữu hạn và chỉ bật histogram khi cần.

## Checklist khi đọc Timer trên Prometheus

Trước khi tạo dashboard hoặc alert, hãy xác minh:

1. Timer được xuất với tên metric thực tế nào?
2. Đơn vị thời gian ở Prometheus là giây hay đơn vị khác?
3. _count và _sum có phải cumulative counter không?
4. _max có phải gauge và expiry/buffer length được cấu hình thế nào?
5. Histogram bucket đã được bật chưa?
6. Bucket có label le và +Inf khớp count không?
7. Các instance có cùng bucket boundaries và đơn vị không?
8. Query rate/increase có xử lý counter reset đúng không?
9. Query mean dùng count và sum cùng cửa sổ không?
10. Query p95 dùng histogram_quantile trên bucket đã tổng hợp không?
11. Có tránh cộng percentile phía client không?
12. Tag có cardinality hữu hạn và histogram có nằm trong ngân sách series không?
13. Exposition thực tế đã được kiểm tra sau khi nâng phiên bản registry chưa?

## Kết luận

Prometheus registry thường biểu diễn một Timer thành các chuỗi count, sum, max và, khi bật histogram, các bucket. Count cho biết số lần hoàn tất; sum cho biết tổng thời gian theo giây; max là gauge phản ánh cực đại theo cửa sổ thống kê; bucket mô tả số quan sát không vượt quá từng ngưỡng.

Hãy dùng rate hoặc increase cho count và sum, đọc max như gauge, và dùng histogram_quantile trên bucket tương thích để tính percentile tổng hợp. Giữ đơn vị và label nhất quán, kiểm soát cardinality, xác minh endpoint exposition thực tế và viết truy vấn theo đúng semantics từng chuỗi. Khi hiểu rõ cách Timer được ánh xạ, dashboard và cảnh báo Prometheus sẽ phản ánh đúng throughput, mean latency, p95 và trạng thái độ trễ cực đại của dịch vụ.
