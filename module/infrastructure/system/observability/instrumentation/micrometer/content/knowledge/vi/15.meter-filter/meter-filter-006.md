# maximumAllowableMetrics để giới hạn số meter được đăng ký

## Giới hạn số meter trong một registry

Micrometer cho phép ứng dụng tạo meter động theo tên và tag. Điều này linh hoạt khi cần phân loại metrics theo HTTP method, outcome, queue, region hoặc loại thao tác. Tuy nhiên, nếu mỗi tổ hợp tag tạo ra một meter mới, số meter trong registry có thể tăng rất nhanh. Những tag có giá trị không giới hạn như request ID, user ID, order ID hoặc URL đầy đủ có thể làm số lượng meter tăng theo lưu lượng và thời gian chạy.

**MeterFilter.maximumAllowableMetrics(...)** cung cấp một giới hạn tổng số meter được phép đăng ký trong registry. Khi số meter đã đạt ngưỡng, các danh tính meter mới sẽ bị từ chối. Những meter đã được chấp nhận vẫn tiếp tục hoạt động.

Bộ lọc này là một hàng rào bảo vệ ở cấp registry. Nó giúp hạn chế sự tăng trưởng không kiểm soát của số meter, nhưng không thay thế thiết kế tag có cardinality thấp. Khi chạm ngưỡng, một số metrics mới có thể bị bỏ qua, kể cả khi chúng có ích cho vận hành.

## Vì sao cần giới hạn số meter?

### Tag tạo ra các meter riêng biệt

Micrometer định danh meter bằng tên, loại và tập tag. Cùng một tên nhưng khác tag có thể tạo ra các meter khác nhau.

Ví dụ:

~~~java
registry.counter("http.requests", "method", "GET");
registry.counter("http.requests", "method", "POST");
registry.counter("http.requests", "method", "DELETE");
~~~

Ba lời gọi trên tạo các meter riêng biệt vì mỗi meter có giá trị tag method khác nhau. Với tag có tập giá trị hữu hạn như HTTP method, số lượng meter có thể dự đoán được.

Nếu dùng request ID:

~~~java
registry.counter("http.requests", "request_id", requestId);
~~~

Mỗi request có thể tạo một giá trị request_id mới và do đó tạo thêm một meter. Khi lưu lượng tăng, registry có thể tích lũy hàng nghìn hoặc hàng triệu meter. Mỗi meter tiêu thụ bộ nhớ trong ứng dụng và có thể tạo thêm dữ liệu khi xuất sang backend.

### Hậu quả của số meter tăng không giới hạn

Số meter lớn có thể gây ra nhiều vấn đề:

- Tăng bộ nhớ mà registry sử dụng để giữ meter và metadata.
- Tăng thời gian thu thập hoặc scrape vì có nhiều meter phải duyệt và xuất.
- Tăng số chuỗi dữ liệu và dung lượng lưu trữ ở backend.
- Làm truy vấn và dashboard chậm hơn.
- Tăng chi phí ingest hoặc chi phí tính theo cardinality ở nền tảng giám sát.
- Khiến các metrics quan trọng khó được quan sát giữa lượng dữ liệu nhiễu.

Giới hạn số meter giúp đặt một trần cho số danh tính meter được chấp nhận. Tuy nhiên, nếu nguyên nhân gốc là tag không kiểm soát, filter chỉ chặn phần vượt ngưỡng; những meter được tạo trước khi chạm ngưỡng vẫn tồn tại và có thể đã tiêu tốn đáng kể tài nguyên.

## Cách hoạt động của maximumAllowableMetrics

### Khai báo giới hạn

Có thể cài filter trực tiếp trên registry:

~~~java
registry.config()
    .meterFilter(MeterFilter.maximumAllowableMetrics(1000));
~~~

Trong ví dụ, registry chấp nhận tối đa 1.000 danh tính meter qua filter này. Sau khi đạt giới hạn, những meter mới không nằm trong tập đã được chấp nhận sẽ bị từ chối.

Giới hạn được áp dụng trên registry mà filter được cài đặt. Nó không tự tạo một ngân sách chung cho tất cả registry trong tiến trình. Nếu ứng dụng có nhiều registry độc lập, cần hiểu filter được gắn vào registry nào và mỗi registry có cấu hình riêng ra sao.

### Meter đã được chấp nhận vẫn tiếp tục hoạt động

Khi một meter đã được đăng ký thành công, các lần lấy lại cùng danh tính sẽ tiếp tục dùng meter đó. Filter không từ chối mỗi lần gọi increment hoặc record; nó kiểm soát việc đăng ký danh tính meter mới.

Ví dụ, nếu meter http.requests với method=GET đã được chấp nhận, những lần gọi lại:

~~~java
Counter requests = registry.counter("http.requests", "method", "GET");
requests.increment();
~~~

sẽ tiếp tục cập nhật meter hiện có. Việc đạt ngưỡng không làm meter GET đã đăng ký ngừng hoạt động.

Ngược lại, nếu method=PATCH chưa từng được đăng ký và giới hạn đã đạt, đăng ký meter cho PATCH sẽ bị từ chối. Mã ứng dụng vẫn có thể nhận một đối tượng meter no-op và gọi increment, nhưng phép đo không được lưu trong registry.

### Danh tính mới tiêu thụ ngân sách

Các tổ hợp tên và tag khác nhau tạo ra các danh tính khác nhau. Ví dụ, hai meter cùng tên http.requests nhưng có method=GET và method=POST được tính là hai meter riêng.

Việc gọi builder hoặc registry nhiều lần với cùng danh tính không nên được xem là nhiều meter mới. Điều cần kiểm soát là số danh tính khác nhau được đăng ký, đặc biệt là các tổ hợp tag động.

Bộ lọc giới hạn tổng số meter qua nó, không giới hạn riêng từng tên meter. Nếu cần ngân sách khác nhau theo nhóm hoặc tên meter, cần kết hợp với filter chọn lọc hoặc một MeterFilter tùy chỉnh.

## Meter bị từ chối có hành vi gì?

Khi một meter bị filter từ chối, Micrometer không đăng ký meter đó vào registry. Thông thường, lời gọi tạo meter trả về một implementation no-op tương ứng để mã ứng dụng vẫn có thể tiếp tục gọi các phương thức như increment hoặc record mà không cần xử lý ngoại lệ cho từng lần ghi.

Điều này giúp filter hoạt động như một hàng rào bảo vệ, nhưng cũng có nghĩa metrics bị từ chối có thể biến mất một cách âm thầm khỏi backend. Ứng dụng không nên dựa vào việc gọi meter thành công để kết luận phép đo đã được lưu.

Vì vậy, cần có chiến lược quan sát việc chạm ngưỡng:

- Theo dõi số meter đã đăng ký trong registry.
- Kiểm tra log hoặc cơ chế chẩn đoán khi cấu hình filter.
- Kiểm thử các meter dự kiến được giữ và các meter có thể bị từ chối.
- Chọn ngưỡng có đủ khoảng dự phòng cho meter mới hợp lệ.
- Tránh đặt ngưỡng thấp đến mức làm mất những metrics thiết yếu trong quá trình khởi động.

Không nên giả định maximumAllowableMetrics tự phát cảnh báo nghiệp vụ khi đạt ngưỡng. Filter chủ yếu quyết định có cho phép đăng ký hay không; việc giám sát tình trạng chạm ngưỡng cần được thiết kế riêng.

## Giới hạn meter không đồng nghĩa giới hạn time series

Một meter Micrometer có thể được backend biểu diễn thành nhiều chuỗi dữ liệu. Ví dụ, Timer hoặc DistributionSummary có thể xuất count, sum, max, histogram bucket và percentile tùy registry cùng cấu hình.

Do đó, giới hạn 1.000 meter không có nghĩa backend chắc chắn chỉ có 1.000 time series. Một meter có histogram có thể tạo nhiều chuỗi dữ liệu; số bucket, tag và loại exporter ảnh hưởng tổng số chuỗi được lưu.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Cơ chế kiểm soát |
|---|---|---|
| Meter | Một danh tính đo lường được đăng ký trong Micrometer | maximumAllowableMetrics |
| Tag value | Một giá trị của một chiều phân loại | maximumAllowableTags hoặc quy tắc tag |
| Time series | Một chuỗi dữ liệu được backend lưu sau khi exporter ánh xạ meter | Thiết kế tag, histogram, backend và chính sách ingest |
| Sample/observation | Một lần ghi giá trị hoặc một lần thu thập | Tần suất ghi, scrape/push và vòng đời dữ liệu |

maximumAllowableMetrics giới hạn số meter đăng ký. Nó không giới hạn trực tiếp số sample, không đặt giới hạn riêng cho số giá trị của một tag, và không đảm bảo số time series backend bằng số meter.

## So sánh với maximumAllowableTags

Micrometer còn có **MeterFilter.maximumAllowableTags(...)** để giới hạn số giá trị khác nhau của một tag key trên một nhóm meter theo tên.

Hai filter giải quyết hai phạm vi khác nhau:

~~~java
registry.config()
    .meterFilter(
        MeterFilter.maximumAllowableTags(
            "http.requests",
            "tenant",
            20,
            MeterFilter.deny()
        )
    )
    .meterFilter(MeterFilter.maximumAllowableMetrics(1000));
~~~

Trong ví dụ:

- maximumAllowableTags giới hạn số giá trị tenant cho meter có tên bắt đầu bằng http.requests.
- maximumAllowableMetrics đặt trần tổng số meter được chấp nhận qua filter trên registry.

Nếu chỉ dùng maximumAllowableMetrics, một tag có cardinality cao vẫn có thể tiêu thụ hết ngân sách bằng những meter đầu tiên được đăng ký. Nếu chỉ dùng maximumAllowableTags, những tên meter hoặc tổ hợp tag khác vẫn có thể làm tổng số meter tăng cao.

Kết hợp các filter phù hợp giúp kiểm soát ở nhiều lớp. Tuy nhiên, không nên xem filter là lý do để đưa định danh duy nhất vào tag. Thiết kế tốt vẫn là chọn các chiều có tập giá trị hữu hạn và có ý nghĩa tổng hợp.

## Thứ tự cấu hình filter và thời điểm áp dụng

### Đăng ký filter trước khi tạo meter

MeterFilter được áp dụng khi registry xử lý việc đăng ký meter. Nếu một số meter đã được tạo trước khi cài maximumAllowableMetrics, filter mới không tự xóa các meter cũ hoặc thu hồi bộ nhớ mà chúng đang sử dụng.

Vì vậy, hãy cấu hình filter sớm trong giai đoạn khởi tạo registry, trước khi component nghiệp vụ, thư viện hoặc auto-configuration bắt đầu đăng ký meter động.

Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
    .meterFilter(MeterFilter.maximumAllowableMetrics(500));

startApplicationComponents(registry);
~~~

Nếu registry đã có meter, hãy xem lại số meter hiện tại trước khi bật giới hạn. Đừng kỳ vọng việc thêm filter sau đó sẽ đưa registry đang vượt ngưỡng trở lại dưới giới hạn.

### Chú ý thứ tự giữa các filter

Các filter được áp dụng theo thứ tự cấu hình. Một filter trả về quyết định ACCEPT có thể kết thúc quá trình xét accept và khiến những filter phía sau không được gọi. Filter trả về DENY từ chối meter; NEUTRAL cho phép các filter tiếp theo tiếp tục đánh giá.

Nếu cần một filter từ chối meter nhiễu trước khi meter đó tiêu thụ ngân sách, hãy cấu hình filter chọn lọc trước giới hạn tổng. Đồng thời tránh một filter ACCEPT sớm đứng trước maximumAllowableMetrics nếu muốn mọi meter đều đi qua giới hạn này.

Ví dụ về ý tưởng thứ tự:

~~~java
registry.config()
    .meterFilter(MeterFilter.denyNameStartsWith("debug."))
    .meterFilter(MeterFilter.maximumAllowableMetrics(1000));
~~~

Các meter debug.* bị từ chối trước khi tới filter giới hạn. Những meter còn lại tiếp tục được đánh giá và tiêu thụ ngân sách nếu được chấp nhận.

Hãy kiểm tra thứ tự filter thực tế trong phiên bản Micrometer đang dùng, đặc biệt khi có filter tùy chỉnh hoặc filter do framework và thư viện khác cung cấp.

## Chọn ngưỡng phù hợp

Không nên chọn một con số tùy ý mà không đo quy mô meter thực tế. Ngưỡng nên dựa trên:

1. Số meter cố định được đăng ký khi ứng dụng khởi động.
2. Số tổ hợp tag hợp lệ tối đa.
3. Số meter do thư viện hoặc auto-configuration tạo ra.
4. Số meter động được phép xuất hiện trong một vòng đời.
5. Dự phòng cho tính năng hoặc thành phần sẽ được thêm sau này.
6. Giới hạn bộ nhớ, ingest và chi phí của backend.

Ví dụ, nếu ứng dụng có 300 meter cố định và tối đa 200 meter theo các tổ hợp tag hữu hạn, ngưỡng 700 có thể tạo khoảng dự phòng. Nhưng cần đo bằng registry thật và môi trường triển khai, không suy ra chỉ từ số dòng code đăng ký meter.

Ngưỡng quá thấp có thể làm mất metrics quan trọng khi khởi động vì thứ tự đăng ký quyết định meter nào được chấp nhận trước. Ngưỡng quá cao không bảo vệ được bộ nhớ và backend trước cardinality bất thường. Nên quan sát số meter thực tế qua các phiên bản triển khai rồi điều chỉnh ngưỡng có kiểm soát.

## Ngân sách là cơ chế chặn, không phải chính sách ưu tiên

maximumAllowableMetrics áp dụng một giới hạn tổng. Nó không hiểu meter nào quan trọng hơn về mặt nghiệp vụ. Nếu các meter động hoặc ít quan trọng được đăng ký trước và tiêu thụ hết ngân sách, meter quan trọng được đăng ký sau có thể bị từ chối.

Để bảo vệ metrics thiết yếu:

- Từ chối sớm các nhóm meter không cần thiết hoặc có cardinality rủi ro.
- Đăng ký meter cốt lõi trong giai đoạn khởi tạo.
- Dành khoảng dự phòng cho các meter xuất hiện sau.
- Dùng giới hạn theo tag hoặc filter tùy chỉnh khi cần chính sách theo nhóm.
- Kiểm thử thứ tự đăng ký trong các đường khởi động thực tế.

Không nên phụ thuộc hoàn toàn vào thứ tự khởi tạo ngẫu nhiên giữa các bean hoặc thư viện. Nếu cần bảo đảm một nhóm meter luôn được giữ, hãy thể hiện chính sách đó bằng filter có điều kiện rõ ràng và kiểm thử.

## Tích hợp MeterFilter trong Spring Boot

Trong Spring Boot, có thể khai báo một bean MeterFilter để áp dụng giới hạn cho các registry do auto-configuration quản lý:

~~~java
@Configuration
public class MetricsConfiguration {

    @Bean
    MeterFilter maximumMetricsFilter() {
        return MeterFilter.maximumAllowableMetrics(2000);
    }
}
~~~

Spring Boot thu thập các bean MeterFilter và áp dụng chúng cho registry được cấu hình tự động theo cơ chế của phiên bản đang sử dụng. Nếu ứng dụng tự tạo registry hoặc có nhiều registry tùy chỉnh, cần xác nhận filter thực sự được gắn vào từng registry cần bảo vệ.

Có thể dùng MeterRegistryCustomizer để cấu hình registry khi cần điều chỉnh trực tiếp:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> metricsCustomizer() {
    return registry -> registry.config()
        .meterFilter(MeterFilter.maximumAllowableMetrics(2000));
}
~~~

Không nên đồng thời cài cùng một filter qua nhiều đường cấu hình nếu không hiểu rõ vòng đời và thứ tự áp dụng. Chọn một điểm cấu hình phù hợp với cách registry được tạo và kiểm tra số meter thực tế sau khi ứng dụng khởi động.

## Kiểm thử giới hạn số meter

Có thể dùng SimpleMeterRegistry để kiểm tra rằng registry không đăng ký thêm meter mới sau khi đạt ngưỡng:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
    .meterFilter(MeterFilter.maximumAllowableMetrics(2));

Counter first = registry.counter(
    "jobs.completed",
    "queue",
    "fast"
);
Counter second = registry.counter(
    "jobs.completed",
    "queue",
    "slow"
);
Counter overflow = registry.counter(
    "jobs.completed",
    "queue",
    "bulk"
);

first.increment();
second.increment();
overflow.increment();

assertThat(registry.getMeters()).hasSize(2);
~~~

Hai danh tính đầu tiên được đăng ký. Danh tính thứ ba vượt ngưỡng nên không được thêm vào registry; handle trả về cho lời gọi đó không ghi nhận dữ liệu.

Có thể kiểm thử thêm các trường hợp:

1. Gọi lại meter đã đăng ký không tiêu thụ thêm một slot mới.
2. Thay đổi tag tạo danh tính mới và cần slot mới.
3. Meter mới sau khi đạt ngưỡng bị từ chối.
4. Meter đã được chấp nhận vẫn tiếp tục ghi nhận.
5. Filter từ chối một nhóm meter trước giới hạn tổng nếu cấu hình như vậy.
6. Filter được cài trước khi component tạo meter.
7. Spring Boot áp dụng filter vào đúng registry cần bảo vệ.
8. Các meter quan trọng vẫn được đăng ký trong thứ tự khởi tạo thực tế.

Kiểm thử với SimpleMeterRegistry xác nhận hành vi filter ở lớp Micrometer. Với exporter thực tế, cần kiểm tra endpoint hoặc payload để xác nhận meter bị từ chối không xuất hiện và những meter đã được chấp nhận vẫn được backend nhận.

## Theo dõi việc chạm ngưỡng trong vận hành

Một giới hạn chỉ hữu ích khi đội vận hành biết registry có đang tiến gần đến ngưỡng hay không. Có thể quan sát số meter đã đăng ký và so sánh với ngân sách cấu hình. Cần phân biệt số meter trong registry với số time series mà backend nhận được.

Khi số meter tăng bất thường, hãy điều tra:

- Meter name nào tăng nhanh?
- Tag key nào tạo ra nhiều tổ hợp?
- Có tag nào chứa ID hoặc giá trị tự do không?
- Thư viện nào đăng ký meter động?
- Meter có được đăng ký lặp theo request hoặc theo từng object không?
- Histogram có tạo nhiều chuỗi dữ liệu hơn dự kiến không?

Không nên chỉ tăng ngưỡng để xử lý triệu chứng. Nếu một tag có giá trị duy nhất cho mỗi request, nâng giới hạn chỉ trì hoãn thời điểm registry và backend gặp vấn đề.

Nếu cần cảnh báo khi registry gần ngưỡng, có thể xuất một Gauge nội bộ cho số meter hiện có hoặc dùng cơ chế chẩn đoán phù hợp. Meter giám sát ngân sách cần được đăng ký theo cách không tự tiêu thụ quá nhiều slot và không tạo vòng lặp khi đo chính registry.

## Những sai lầm thường gặp

**Coi maximumAllowableMetrics là giới hạn time series.** Filter giới hạn meter registration trong Micrometer. Một Timer có thể xuất nhiều series do count, sum, max và histogram.

**Chỉ dùng giới hạn tổng để xử lý tag cardinality.** Các giá trị tag không kiểm soát vẫn chiếm những slot đầu tiên. Dùng tag hữu hạn và maximumAllowableTags khi cần.

**Cài filter sau khi ứng dụng đã tạo meter.** Filter không tự xóa các meter đã đăng ký. Cài trước khi instrumentation bắt đầu tạo meter.

**Nghĩ rằng meter bị từ chối sẽ ném exception.** Registry thường trả meter no-op. Mã vẫn có thể chạy nhưng dữ liệu không được lưu; cần kiểm tra registry và exporter.

**Đặt ngưỡng quá thấp.** Các meter thiết yếu đăng ký sau có thể bị từ chối. Dựa trên số meter thực tế và dành khoảng dự phòng.

**Đặt ngưỡng quá cao.** Hàng rào không còn bảo vệ hiệu quả trước sự tăng trưởng bất thường. Đo bộ nhớ và cardinality backend để chọn giới hạn.

**Cho rằng filter tự ưu tiên meter quan trọng.** Filter không hiểu ý nghĩa nghiệp vụ. Cần kiểm soát thứ tự, từ chối nhóm nhiễu và đăng ký meter cốt lõi sớm.

**Đăng ký meter theo từng request hoặc object ngắn hạn.** Số danh tính tăng theo workload và có thể làm cạn ngân sách. Đăng ký meter theo nhóm ổn định.

**Giả định nhiều registry dùng chung một ngân sách.** Filter gắn với registry được cấu hình. Kiểm tra từng registry độc lập trong ứng dụng nhiều backend.

## Checklist triển khai maximumAllowableMetrics

Trước khi bật giới hạn, hãy xác minh:

1. Số meter cố định và số meter động tối đa đã được ước lượng chưa?
2. Ngưỡng có đủ chỗ cho các meter thiết yếu và khoảng dự phòng không?
3. Filter được cài trước khi instrumentation đăng ký meter chưa?
4. Các filter từ chối meter nhiễu có đứng trước giới hạn tổng không?
5. Có filter ACCEPT sớm nào có thể bỏ qua giới hạn không?
6. Các tag có tập giá trị hữu hạn và không chứa định danh duy nhất không?
7. Có cần maximumAllowableTags hoặc filter theo tên bổ sung không?
8. Đã phân biệt số meter với số time series backend chưa?
9. Đã kiểm thử meter hiện có, meter mới và meter bị từ chối chưa?
10. Đã xác nhận filter được áp dụng cho tất cả registry cần bảo vệ chưa?
11. Có cách theo dõi số meter và phát hiện tiến gần ngưỡng không?
12. Khi chạm ngưỡng, đội vận hành biết metrics nào có thể bị mất không?

## Kết luận

MeterFilter.maximumAllowableMetrics đặt giới hạn tổng số danh tính meter được đăng ký qua filter trong một registry. Khi đạt ngưỡng, meter mới bị từ chối trong khi các meter đã được chấp nhận tiếp tục hoạt động. Cơ chế này giúp giới hạn mức tăng trưởng của registry và giảm rủi ro từ việc tạo meter động quá nhiều.

Hãy cài filter trước khi instrumentation đăng ký meter, chọn ngưỡng dựa trên số meter thực tế và khoảng dự phòng, đồng thời kiểm soát tag bằng các quy tắc phù hợp. Phân biệt meter với time series, kiểm tra thứ tự filter và bảo vệ các meter thiết yếu để giới hạn không làm mất những số đo quan trọng.
