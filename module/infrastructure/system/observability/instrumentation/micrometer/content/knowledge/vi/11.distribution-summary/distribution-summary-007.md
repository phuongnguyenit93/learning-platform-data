# Cửa sổ thống kê và tác động khi không có quan sát mới

## DistributionSummary ghi nhận phân phối của các giá trị

Micrometer cung cấp **DistributionSummary** để ghi nhận phân phối của một đại lượng số không nhất thiết là thời gian. Ví dụ thường gặp là kích thước request hoặc response, dung lượng file, số phần tử trong một lô, số bản ghi xử lý mỗi batch, hoặc giá trị tải được tính cho từng lần thực thi.

Mỗi lần gọi **record(value)** tạo một quan sát. Từ các quan sát đó, DistributionSummary cung cấp các thống kê như số lượng mẫu (count), tổng các giá trị (total amount), giá trị lớn nhất (max) và, nếu được cấu hình, percentile hoặc histogram.

Ví dụ:

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("http.request.payload.size")
    .description("Kich thuoc request payload")
    .baseUnit("bytes")
    .register(registry);

payloadSize.record(1024);
payloadSize.record(2048);
payloadSize.record(4096);
~~~

Trong ví dụ này có ba quan sát. Count là 3, tổng giá trị là 7.168 byte, trung bình là khoảng 2.389,33 byte và max là 4.096 byte. Các con số này mô tả những gì registry hiện đang lưu hoặc xuất theo mô hình thống kê của nó.

Một điểm cần chú ý là không phải mọi thống kê đều có cùng phạm vi thời gian. Count và tổng giá trị thường có tính tích lũy trong registry dạng cumulative; max và percentile của Micrometer có thể được tính theo cửa sổ thời gian. Registry dạng step hoặc backend có thể xuất dữ liệu theo khoảng thu thập riêng. Vì vậy, cần hiểu phạm vi của từng phép đo trước khi diễn giải dashboard.

## Hai loại phạm vi thống kê

### Thống kê tích lũy

Count và total amount thường phản ánh tổng số quan sát và tổng giá trị đã ghi nhận kể từ khi meter bắt đầu hoạt động trong một registry cumulative.

Ví dụ, nếu ba lần ghi lần lượt là 10, 20 và 30, count là 3 và total amount là 60. Nếu sau đó không có quan sát mới, các giá trị tích lũy này không tự giảm về 0; chúng giữ nguyên cho đến khi có quan sát tiếp theo hoặc vòng đời registry/tiến trình kết thúc.

Từ count và total amount có thể tính trung bình:

`mean = totalAmount / count`

Nếu count bằng 0, không có trung bình có ý nghĩa để tính. Không nên coi 0 là một quan sát thực tế trong trường hợp chưa có dữ liệu.

### Thống kê theo cửa sổ thời gian

Một số thống kê như max và percentile trong Micrometer được thiết kế để phản ánh các quan sát gần đây. Điều này giúp số đo vận hành phản ứng với trạng thái hiện tại thay vì bị chi phối mãi mãi bởi một giá trị cực đại từ rất lâu trước đó.

Micrometer hỗ trợ cấu hình thời gian hết hạn của thống kê phân phối thông qua **distributionStatisticExpiry** và số vùng đệm qua **distributionStatisticBufferLength**. Các cấu hình này ảnh hưởng cửa sổ mà những thống kê theo thời gian giữ lại dữ liệu.

Nếu expiry là 1 phút và buffer length là 3, cửa sổ lưu trữ xấp xỉ 3 phút. Khi các vùng đệm luân phiên, dữ liệu cũ hết hạn dần và không còn ảnh hưởng đến max hoặc percentile của cửa sổ hiện tại.

Không nên hiểu expiry là chu kỳ scrape. Expiry điều khiển vòng đời của thống kê trong Micrometer; scrape hoặc push điều khiển thời điểm backend thu thập dữ liệu. Hai khoảng thời gian này có thể khác nhau.

## Cửa sổ thống kê được cấu hình như thế nào?

### Expiry và buffer length

**distributionStatisticExpiry** xác định thời gian tồn tại của một vùng thống kê. **distributionStatisticBufferLength** xác định số vùng được giữ trong cấu trúc cửa sổ. Tổng cửa sổ xấp xỉ bằng tích hai giá trị:

`windowDuration = expiry × bufferLength`

Ví dụ:

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("http.request.payload.size")
    .baseUnit("bytes")
    .distributionStatisticExpiry(Duration.ofMinutes(1))
    .distributionStatisticBufferLength(3)
    .register(registry);
~~~

Cấu hình này giữ các thống kê theo cửa sổ trong khoảng xấp xỉ ba phút. Các quan sát cũ được loại dần khi vùng thống kê tương ứng hết hạn.

Giá trị mặc định của expiry thường dựa trên step của registry nếu registry có step; nếu không có step, Micrometer sử dụng một khoảng mặc định. Buffer length mặc định thường là 3. Cấu hình cụ thể có thể được điều chỉnh bởi registry, cấu hình toàn cục hoặc MeterFilter, nên cần kiểm tra giá trị thực tế của ứng dụng thay vì giả định mọi backend có cùng cửa sổ.

### Tác động của việc chọn cửa sổ

Cửa sổ ngắn giúp max và percentile phản ánh nhanh các thay đổi gần đây. Tuy nhiên, nếu lưu lượng thưa hoặc quan sát đến không đều, cửa sổ có thể nhanh chóng không còn mẫu để tính thống kê.

Cửa sổ dài giữ lại nhiều quan sát hơn và làm số đo ổn định hơn, nhưng một đỉnh bất thường có thể tiếp tục ảnh hưởng đến max hoặc percentile trong thời gian lâu hơn.

Buffer length lớn hơn giữ nhiều vùng thời gian hơn, đồng thời tăng bộ nhớ và chi phí lưu trữ nội bộ. Không nên tăng buffer chỉ để cố giữ dữ liệu lịch sử dài hạn; DistributionSummary không thay thế hệ thống lưu trữ metrics hoặc dữ liệu sự kiện.

Hãy chọn expiry và buffer length theo mục tiêu:

- Muốn phát hiện biến động gần đây nhanh: dùng cửa sổ ngắn, phù hợp với tần suất thu thập.
- Muốn percentile ổn định hơn khi lưu lượng không đều: cân nhắc cửa sổ dài hơn.
- Muốn giữ lịch sử trong nhiều giờ hoặc nhiều ngày: dựa vào backend metrics có retention phù hợp, không dựa vào buffer của một meter trong bộ nhớ.
- Muốn kiểm soát tài nguyên: đo số meter, cardinality và chi phí histogram trước khi mở rộng cửa sổ.

## Điều gì xảy ra khi không có quan sát mới?

Đây là điểm dễ gây hiểu nhầm khi đọc DistributionSummary.

Giả sử ứng dụng ghi nhận một payload lớn 8 MiB, sau đó không có request nào trong vài phút. Count và total amount của một registry cumulative vẫn phản ánh quan sát đã xảy ra. Nhưng max theo cửa sổ có thể trở về 0 khi vùng thống kê chứa giá trị đó hết hạn. Các percentile theo cửa sổ cũng không còn phản ánh mẫu cũ sau khi các vùng tương ứng hết hạn; cách giá trị được biểu diễn hoặc xuất có thể phụ thuộc registry và backend.

Như vậy, dashboard có thể đồng thời hiển thị:

- Count vẫn giữ tổng số quan sát đã ghi.
- Total amount vẫn giữ tổng giá trị tích lũy.
- Max theo cửa sổ trở về 0 sau khi không còn mẫu trong cửa sổ.
- Percentile theo cửa sổ không còn đại diện cho phân phối cũ khi dữ liệu đã hết hạn.

Điều này không nhất thiết là lỗi hoặc dữ liệu bị xóa khỏi backend. Đó là khác biệt giữa thống kê tích lũy và thống kê có thời hạn. Khi đọc biểu đồ, phải biết mỗi series biểu diễn loại thống kê nào và có phạm vi thời gian ra sao.

Với registry dạng step, count và total amount có thể được xuất theo từng step thay vì tích lũy toàn bộ vòng đời. Khi không có quan sát trong step mới, giá trị của step đó có thể bằng 0, dù tổng lịch sử ở backend vẫn còn nếu backend lưu các điểm trước đó. Vì vậy, không nên khẳng định count và sum luôn là lifetime cumulative trên mọi registry.

### Không có mẫu không đồng nghĩa giá trị đo bằng 0

Nếu không có request mới, không có nghĩa payload size bằng 0. Nó chỉ có nghĩa không có quan sát payload mới trong khoảng đó.

Tương tự, không có batch mới không có nghĩa số bản ghi mỗi batch bằng 0. Nếu ứng dụng ghi một DistributionSummary chỉ khi batch hoàn tất, khoảng không có batch sẽ không tạo thêm mẫu.

Dashboard nên phân biệt:

- **Không có quan sát:** không có mẫu mới trong khoảng thời gian.
- **Có quan sát bằng 0:** ứng dụng thực sự gọi record(0) và giá trị 0 là hợp lệ.
- **Series không còn được xuất:** có thể do meter bị gỡ, registry dừng, scrape thất bại hoặc backend áp dụng chính sách xử lý dữ liệu cũ.

Không nên thay dữ liệu thiếu bằng số 0 nếu điều đó làm thay đổi ý nghĩa thống kê. Một hệ thống không nhận request và một hệ thống nhận request có payload rỗng là hai trạng thái khác nhau.

## Ví dụ theo dõi cửa sổ và giá trị max

Có thể cấu hình DistributionSummary với expiry và buffer length để kiểm soát cửa sổ thống kê:

~~~java
DistributionSummary batchSize = DistributionSummary
    .builder("import.batch.records")
    .description("So ban ghi trong moi batch import")
    .baseUnit("records")
    .distributionStatisticExpiry(Duration.ofSeconds(30))
    .distributionStatisticBufferLength(2)
    .register(registry);

batchSize.record(100);
batchSize.record(250);
batchSize.record(180);
~~~

Với cấu hình trên, cửa sổ thống kê xấp xỉ 60 giây. Trong khoảng cửa sổ còn chứa các quan sát này, max là 250. Nếu không có quan sát mới và các vùng thống kê chứa những mẫu này hết hạn, max theo cửa sổ có thể trở về 0.

Count và total amount của registry cumulative vẫn phản ánh ba quan sát và tổng 530 records. Nếu dùng registry dạng step, cách xuất count và total có thể theo step của registry, nên cần đối chiếu với backend đang sử dụng.

Không nên viết kiểm thử bằng cách chờ thời gian thật để xác nhận expiry. Hãy dùng clock có thể điều khiển nếu phiên bản Micrometer và fixture kiểm thử cho phép, hoặc kiểm thử cấu hình và hành vi tại tầng registry phù hợp.

## Percentile và histogram trong cửa sổ thống kê

### Percentile theo cửa sổ

Có thể yêu cầu Micrometer tính percentile phía ứng dụng:

~~~java
DistributionSummary summary = DistributionSummary
    .builder("import.batch.records")
    .publishPercentiles(0.5, 0.95, 0.99)
    .distributionStatisticExpiry(Duration.ofMinutes(1))
    .distributionStatisticBufferLength(3)
    .register(registry);
~~~

Các percentile p50, p95 và p99 được tính từ phân phối quan sát trong phạm vi thống kê của meter. Khi không có mẫu mới và dữ liệu cũ hết hạn khỏi cửa sổ, percentile không còn mô tả các quan sát trước đó. Giá trị cụ thể mà API hoặc backend xuất cho cửa sổ rỗng có thể phụ thuộc loại registry; không nên diễn giải nó như một percentile bằng 0 nếu không có mẫu.

Percentile phía ứng dụng hữu ích để xem phân phối cục bộ của một instance. Không thể cộng hoặc lấy trung bình p95 của nhiều instance để tạo p95 chính xác toàn hệ thống.

### Histogram và ranh giới bucket

Có thể xuất histogram để backend tổng hợp các quan sát theo bucket:

~~~java
DistributionSummary summary = DistributionSummary
    .builder("http.request.payload.size")
    .baseUnit("bytes")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        1024,
        4096,
        16384
    )
    .register(registry);
~~~

Trong ví dụ, các ngưỡng SLO được biểu diễn theo byte: 1 KiB, 4 KiB và 16 KiB. Cần bảo đảm giá trị ghi vào summary cũng được chuẩn hóa về byte.

Histogram có thể giúp tổng hợp phân phối giữa nhiều instance nếu backend hỗ trợ và các instance dùng cùng cấu hình bucket. Tuy nhiên, cách histogram được xuất và lưu có thể khác theo registry. Một backend có thể cung cấp bucket tích lũy; registry hoặc backend khác có thể áp dụng cửa sổ hoặc step riêng.

Không đồng nhất cửa sổ percentile phía client với cửa sổ truy vấn của backend. Một truy vấn trong 5 phút ở Prometheus không tự động làm cho percentile phía client trở thành percentile 5 phút; dữ liệu percentile đã được tính tại ứng dụng theo cửa sổ của meter.

## Count, total amount, max và mean

Bốn đại lượng thường được dùng để diễn giải DistributionSummary:

| Thống kê | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Count | Số quan sát đã ghi nhận | Có bao nhiêu lần ghi nhận? |
| Total amount | Tổng các giá trị đã ghi nhận | Tổng dung lượng hoặc số lượng đã xử lý là bao nhiêu? |
| Max | Giá trị lớn nhất trong phạm vi thống kê mà registry áp dụng | Quan sát lớn nhất gần đây là bao nhiêu? |
| Mean | Total amount chia cho count trong cùng phạm vi | Giá trị trung bình của các quan sát là bao nhiêu? |

Phải bảo đảm count và total amount được lấy từ cùng phạm vi thời gian khi tính mean. Nếu count là count của step hiện tại nhưng total amount là tổng tích lũy, phép chia sẽ sai. Nếu max là time-window max còn count là lifetime count, không thể dùng chúng để suy ra một phân phối chung.

Ví dụ, count tích lũy là 1.000 và total amount tích lũy là 5.000.000 byte thì mean tích lũy là 5.000 byte. Max theo cửa sổ là 50.000 byte chỉ cho biết giá trị lớn nhất trong cửa sổ hiện tại, không phải giá trị lớn nhất trong toàn bộ 1.000 quan sát lịch sử.

## Tích hợp với Spring Boot

Trong Spring Boot, nên inject MeterRegistry và đăng ký DistributionSummary một lần trong component quản lý phép đo:

~~~java
@Component
public class BatchMetrics {

    private final DistributionSummary batchSize;

    public BatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary
            .builder("import.batch.records")
            .description("So ban ghi trong moi batch import")
            .baseUnit("records")
            .distributionStatisticExpiry(Duration.ofMinutes(1))
            .distributionStatisticBufferLength(3)
            .register(registry);
    }

    public void recordBatchSize(long records) {
        batchSize.record(records);
    }
}
~~~

Mỗi lần batch hoàn tất, component ghi một quan sát. Nếu không có batch mới, không có record nào được thêm. Những thống kê tích lũy và thống kê theo cửa sổ sẽ thay đổi theo quy tắc riêng của registry.

Có thể cấu hình chung các thống kê phân phối qua **MeterFilter** nếu muốn áp dụng expiry, buffer length, percentile hoặc histogram cho một nhóm meter. Tuy nhiên, nên tránh áp dụng cấu hình nặng cho mọi meter một cách mặc định. Histogram và nhiều percentile có thể làm tăng số chuỗi dữ liệu, bộ nhớ và chi phí backend.

Nếu ứng dụng chạy nhiều instance, cần dùng cùng quy ước đơn vị, tag, expiry, buffer length và cấu hình histogram cho các meter có ý nghĩa giống nhau. Sự khác biệt cấu hình có thể khiến dashboard so sánh các thống kê không cùng phạm vi.

## Kiểm thử khi không có quan sát mới

### Kiểm tra count và total amount

SimpleMeterRegistry có thể xác nhận count và total amount thay đổi khi record:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

DistributionSummary summary = DistributionSummary
    .builder("test.payload.size")
    .baseUnit("bytes")
    .register(registry);

summary.record(100);
summary.record(300);

assertThat(summary.count()).isEqualTo(2);
assertThat(summary.totalAmount()).isEqualTo(400.0);
~~~

Nếu không gọi record thêm, count và total amount của registry cumulative vẫn giữ nguyên. Kiểm thử này không chứng minh hành vi của registry dạng step.

### Kiểm tra max theo cửa sổ

Với cấu hình expiry và buffer length, max có thể hết hạn khi không còn quan sát mới trong cửa sổ. Để kiểm thử chính xác, cần kiểm soát clock mà registry dùng hoặc dùng fixture hỗ trợ thời gian giả lập. Không nên dùng Thread.sleep với thời lượng thật vì test chậm và dễ không ổn định.

Cần kiểm tra riêng:

1. Sau khi ghi các giá trị, max phản ánh giá trị lớn nhất trong cửa sổ.
2. Khi thời gian trôi qua và vùng chứa quan sát cũ hết hạn, max không còn bị giữ bởi giá trị cũ.
3. Khi có quan sát mới, thống kê cửa sổ phản ánh dữ liệu mới.
4. Count và total amount có hành vi phù hợp với loại registry cumulative hoặc step đang kiểm thử.
5. Exporter và backend biểu diễn dữ liệu rỗng hoặc series không có mẫu theo cách dự kiến.

SimpleMeterRegistry hữu ích cho logic meter cơ bản, nhưng không thay thế kiểm thử registry exporter. Với Prometheus, OTLP hoặc backend khác, cần kiểm tra payload và truy vấn thực tế vì naming convention, step, histogram và cách biểu diễn mẫu rỗng có thể khác nhau.

## Diễn giải dashboard khi lưu lượng ngừng

Khi hệ thống tạm ngừng nhận request hoặc batch, dashboard có thể cho thấy count và total amount giữ nguyên, trong khi max hoặc percentile theo cửa sổ giảm hoặc hết hiệu lực. Điều này phản ánh việc không có quan sát mới và dữ liệu trong cửa sổ đã hết hạn.

Một dashboard tốt nên:

- Hiển thị count hoặc rate để cho biết có quan sát mới hay không.
- Hiển thị total amount hoặc rate của tổng lượng nếu cần đo throughput.
- Ghi rõ max và percentile có phạm vi cửa sổ.
- Tránh hiển thị giá trị 0 như thể đã quan sát một payload rỗng khi thực tế không có mẫu.
- Phân biệt series không có dữ liệu, scrape thất bại và giá trị đo bằng 0.
- Đồng bộ khoảng truy vấn với expiry, buffer length và step của registry.

Nếu cần cảnh báo "không có quan sát mới", nên dựa trên count/rate hoặc một tín hiệu heartbeat phù hợp, không suy luận chỉ từ max bằng 0. Max bằng 0 có thể là hệ quả của cửa sổ đã hết hạn, hoặc cũng có thể là giá trị thực nếu ứng dụng ghi nhận các quan sát bằng 0. Phải xem count và ngữ cảnh thu thập cùng lúc.

## Những sai lầm thường gặp

**Cho rằng mọi thống kê có cùng phạm vi thời gian.** Count và total amount có thể tích lũy, trong khi max và percentile có thể theo cửa sổ. Đọc từng đại lượng theo đúng semantics của registry.

**Coi max trở về 0 là ứng dụng vừa ghi nhận giá trị 0.** Max theo cửa sổ có thể hết hạn khi không có quan sát mới. Kiểm tra count và khoảng thời gian cùng lúc.

**Coi không có quan sát là một quan sát bằng 0.** Không có request mới khác với request có payload rỗng. Không tự thay dữ liệu thiếu bằng số 0.

**Đặt expiry bằng chu kỳ scrape mà không xem xét buffer length.** Cửa sổ thống kê xấp xỉ expiry nhân buffer length. Cần tính tổng thời gian giữ mẫu và đối chiếu với mục tiêu vận hành.

**Dùng buffer dài để thay retention backend.** Buffer của meter phục vụ thống kê gần đây trong ứng dụng, không phải kho lịch sử dài hạn.

**So sánh percentile giữa các instance bằng phép trung bình.** Percentile phía client không cộng gộp chính xác. Dùng histogram có bucket tương thích nếu backend hỗ trợ tổng hợp.

**Không thống nhất đơn vị và cấu hình phân phối giữa các instance.** Dữ liệu cùng tên nhưng khác đơn vị hoặc bucket không thể so sánh đáng tin cậy.

**Dùng max để phát hiện không có traffic.** Max bằng 0 có thể do cửa sổ rỗng hoặc quan sát bằng 0. Dùng count/rate và tín hiệu hoạt động phù hợp.

## Checklist thiết kế DistributionSummary

Trước khi đưa DistributionSummary vào vận hành, hãy xác minh:

1. Đại lượng cần đo có phù hợp với DistributionSummary không?
2. Tên meter, description và base unit có mô tả đúng giá trị record không?
3. Giá trị đầu vào có được chuẩn hóa về cùng đơn vị không?
4. Count và total amount đang được backend xuất theo cumulative hay step?
5. Max và percentile có phạm vi cửa sổ nào?
6. Expiry và buffer length tạo ra tổng cửa sổ bao lâu?
7. Khi không có quan sát mới, dashboard phân biệt dữ liệu hết hạn và giá trị 0 như thế nào?
8. Percentile phía client hay histogram phía backend phù hợp với nhu cầu tổng hợp?
9. Các instance có dùng cùng đơn vị, tag và cấu hình phân phối không?
10. Kiểm thử có bao phủ cả trường hợp có mẫu, không có mẫu và dữ liệu hết hạn không?

## Kết luận

DistributionSummary ghi nhận các quan sát số và cung cấp count, total amount cùng các thống kê phân phối. Cần phân biệt thống kê tích lũy với thống kê theo cửa sổ: count và tổng giá trị thường giữ dữ liệu tích lũy trong registry cumulative, trong khi max và percentile có thể hết hạn khi không còn quan sát mới trong cửa sổ.

Expiry và buffer length quyết định khoảng thời gian các thống kê theo cửa sổ giữ ảnh hưởng của mẫu cũ. Khi không có quan sát mới, đừng vội diễn giải max bằng 0 hoặc percentile không còn giá trị như một quan sát bằng 0. Hãy kiểm tra count, total, loại registry, step, cấu hình histogram và cách backend xử lý mẫu rỗng. Hiểu đúng phạm vi thống kê giúp dashboard và cảnh báo phản ánh chính xác trạng thái của ứng dụng.
