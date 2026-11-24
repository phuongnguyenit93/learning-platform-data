# Thiết kế phép đo kích thước dữ liệu với DistributionSummary

Trong bài thực hành này, bạn sẽ instrument một luồng upload để đo phân phối kích thước payload bằng Micrometer DistributionSummary. Kết quả cần cho biết có bao nhiêu payload được tiếp nhận, tổng dung lượng đã quan sát, kích thước trung bình, giá trị lớn nhất trong cửa sổ thống kê và phân phối theo các ngưỡng kích thước.

DistributionSummary phù hợp khi cần ghi nhận phân phối của một đại lượng số không phải thời gian, chẳng hạn kích thước request, kích thước file, số item trong batch hoặc số byte được xử lý. Timer dành cho thời lượng; Counter chỉ đếm số lần hoặc tổng số lượng tăng thêm. Trong bài này, mỗi lần upload ghi nhận một mẫu kích thước vào DistributionSummary.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Xác định chính xác đại lượng và ranh giới cần đo.
- Phân biệt DistributionSummary với Timer và Counter.
- Tạo meter có tên, description, base unit và tags rõ ràng.
- Cấu hình histogram và các ngưỡng SLO theo byte.
- Ghi nhận payload size đúng một lần tại ranh giới đã chọn.
- Kiểm thử count, total amount, max và dữ liệu đầu vào không hợp lệ.
- Đọc dữ liệu được xuất ra Prometheus và viết query cho average/p95.
- Kiểm soát cardinality bằng tags có tập giá trị hữu hạn.

*Thời lượng gợi ý: 60–90 phút.*

## 2. Bối cảnh và yêu cầu nghiệp vụ

Một dịch vụ nhận file từ ứng dụng web và đối tác. Nhóm vận hành muốn biết:

1. Kích thước file được tiếp nhận thường nằm trong khoảng nào?
2. Payload trung bình và p95 có tăng sau một lần release không?
3. Có bao nhiêu payload vượt ngưỡng 1 MiB?
4. Luồng upload từ web và partner có phân phối kích thước khác nhau không?

Ta chọn metric contract sau:

| Thuộc tính | Giá trị |
| --- | --- |
| Meter name | app.upload.payload.size |
| Meter type | DistributionSummary |
| Base unit | bytes |
| Mỗi sample | Kích thước của một payload được tiếp nhận |
| Tag cố định | operation=upload |
| Tag tùy chọn | channel=web hoặc channel=partner |
| Histogram/SLO boundaries | 1 KiB, 10 KiB, 100 KiB, 1 MiB |

Trong bài này, phép đo được ghi sau khi payload đã qua kiểm tra đầu vào cơ bản và được chấp nhận vào use case upload. Nó phản ánh kích thước payload được tiếp nhận, kể cả khi bước lưu trữ phía sau thất bại. Nếu sản phẩm cần thống kê riêng dung lượng lưu thành công, hãy tạo metric có semantics riêng và chỉ ghi sau khi storage xác nhận thành công.

### Xác định chính xác byte nào được đo

Trước khi viết code, phải chốt ranh giới:

- byte[] chứa body đã được ứng dụng nhận: đo payload.length.
- String.length(): đo số đơn vị UTF-16 trong chuỗi, không phải số byte UTF-8.
- Multipart file: MultipartFile.getSize() đo kích thước phần file, không bao gồm toàn bộ multipart boundary và header.
- HTTP body có content encoding: quyết định đo số byte trên wire hay số byte sau giải nén.
- Streaming body: cộng số byte thực sự đọc được và ghi một sample khi stream hoàn tất.

Không trộn các cách đo khác nhau dưới cùng một metric name. Ví dụ, kích thước file sau giải nén và kích thước body trên wire là hai đại lượng khác nhau nếu compression được bật.

## 3. Chuẩn bị project

Ví dụ sử dụng Spring Boot và Micrometer. Nếu project đã có Actuator, registry và MeterRegistry được cấu hình, có thể bỏ qua phần dependency tương ứng.

Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.micrometer:micrometer-core")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

spring-boot-starter-actuator cung cấp tích hợp Micrometer cho ứng dụng Spring Boot. Trong test, SimpleMeterRegistry thuộc Micrometer core và có thể dùng để kiểm tra dữ liệu trong bộ nhớ. Để xuất Prometheus, cần registry Prometheus tương ứng với dòng Spring Boot/Micrometer đang dùng.

Không tự đặt version riêng cho các artifact Micrometer nếu Spring Boot BOM đã quản lý chúng.

## 4. Thiết kế DistributionSummary

Tạo một lớp chuyên trách ghi nhận kích thước payload:

~~~java
package com.example.upload.metrics;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.Objects;

@Component
public class UploadPayloadMetrics {

    private final DistributionSummary payloadSize;

    public UploadPayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary
            .builder("app.upload.payload.size")
            .description("Kích thước payload upload được tiếp nhận")
            .baseUnit("bytes")
            .tag("operation", "upload")
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                1_024,
                10_240,
                102_400,
                1_048_576
            )
            .register(registry);
    }

    public void record(byte[] payload) {
        Objects.requireNonNull(payload, "payload must not be null");
        recordBytes(payload.length);
    }

    public void recordBytes(long sizeInBytes) {
        if (sizeInBytes < 0) {
            throw new IllegalArgumentException(
                "Payload size must not be negative"
            );
        }

        payloadSize.record(sizeInBytes);
    }
}
~~~

Giải thích cấu hình:

- app.upload.payload.size mô tả đại lượng cần đo, không chứa ID của một file cụ thể.
- description giải thích semantics để người vận hành hiểu sample đại diện cho điều gì.
- baseUnit("bytes") khai báo đơn vị dữ liệu.
- operation=upload là tag cố định với một giá trị hữu hạn.
- publishPercentileHistogram() yêu cầu histogram phù hợp với registry hỗ trợ.
- serviceLevelObjectives(...) thêm các ranh giới quan trọng cho bài toán vận hành.
- register(registry) lấy meter từ registry; các lần gọi với cùng tên và tags trong cùng registry dùng chung meter identity.

DistributionSummary.record(double) nhận giá trị số. Lớp wrapper kiểm tra số âm trước khi gọi Micrometer để dữ liệu sai không bị âm thầm bỏ qua. Kích thước bằng 0 vẫn có thể là một mẫu hợp lệ, ví dụ payload rỗng được chấp nhận.

## 5. Vì sao dùng DistributionSummary?

| Công cụ | Đại lượng phù hợp | Ví dụ |
| --- | --- | --- |
| Counter | Số lần sự kiện hoặc tổng lượng tăng đơn điệu | Số upload được tiếp nhận |
| Timer | Thời lượng của một operation | Thời gian lưu file |
| DistributionSummary | Phân phối của các giá trị số | Kích thước payload theo byte |
| Gauge | Trạng thái tại thời điểm đọc | Số upload đang hoạt động |

DistributionSummary cung cấp các thống kê như count, total amount và max; cấu hình phân phối có thể bổ sung histogram hoặc percentile tùy registry. Với payload size:

- count() là số payload đã ghi nhận.
- totalAmount() là tổng kích thước của các payload đã ghi nhận.
- max() là kích thước lớn nhất trong cửa sổ thống kê mà implementation đang duy trì.
- Trung bình có thể tính bằng totalAmount / count khi count lớn hơn 0.

max() không nên được hiểu là giá trị lớn nhất vĩnh viễn. Một số registry/implementation duy trì max theo cửa sổ thời gian; sau khi cửa sổ hết hạn, max có thể giảm hoặc trở về 0.

## 6. Gắn phép đo vào use case upload

Lớp nghiệp vụ gọi metrics component tại đúng ranh giới đã thống nhất:

~~~java
package com.example.upload;

import com.example.upload.metrics.UploadPayloadMetrics;
import org.springframework.stereotype.Service;

import java.util.Objects;

@Service
public class UploadService {

    private static final int MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

    private final UploadPayloadMetrics payloadMetrics;
    private final ObjectStorage storage;

    public UploadService(
        UploadPayloadMetrics payloadMetrics,
        ObjectStorage storage
    ) {
        this.payloadMetrics = payloadMetrics;
        this.storage = storage;
    }

    public UploadReceipt upload(byte[] payload) {
        Objects.requireNonNull(payload, "payload must not be null");

        if (payload.length > MAX_UPLOAD_BYTES) {
            throw new UploadTooLargeException();
        }

        // Ghi một sample sau khi payload được chấp nhận.
        payloadMetrics.record(payload);

        // Storage có thể thất bại; metric này vẫn mô tả payload đã tiếp nhận.
        return storage.store(payload);
    }
}
~~~

ObjectStorage, UploadReceipt và UploadTooLargeException là các kiểu thuộc ứng dụng minh họa. Trong project thật, thay bằng abstraction storage và exception hiện có.

Không ghi sample ở cả controller lẫn service cho cùng một payload. Nếu cả hai nơi cùng gọi record, một file sẽ được tính hai lần. Chọn một owner cho measurement boundary, thường là use case service vì nó biết chính xác payload nào đã được chấp nhận.

Nếu muốn đo dung lượng upload lưu thành công, chuyển lời gọi metrics đến sau storage.store(payload) hoặc tạo một meter khác với tên thể hiện rõ stored. Không đổi semantics của meter hiện tại một cách âm thầm.

## 7. Kiểm thử với SimpleMeterRegistry

Test xác minh số lượng sample, tổng kích thước và max:

~~~java
package com.example.upload.metrics;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

class UploadPayloadMetricsTest {

    @Test
    void recordsPayloadSizeDistribution() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        UploadPayloadMetrics metrics = new UploadPayloadMetrics(registry);

        metrics.recordBytes(512);
        metrics.recordBytes(1_024);
        metrics.recordBytes(2_048);

        DistributionSummary summary = registry
            .find("app.upload.payload.size")
            .tag("operation", "upload")
            .summary();

        assertThat(summary).isNotNull();
        assertThat(summary.count()).isEqualTo(3);
        assertThat(summary.totalAmount()).isEqualTo(3_584);
        assertThat(summary.max()).isEqualTo(2_048);

        registry.close();
    }

    @Test
    void rejectsNegativePayloadSize() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        UploadPayloadMetrics metrics = new UploadPayloadMetrics(registry);

        assertThatIllegalArgumentException()
            .isThrownBy(() -> metrics.recordBytes(-1));

        DistributionSummary summary = registry
            .find("app.upload.payload.size")
            .tag("operation", "upload")
            .summary();

        assertThat(summary.count()).isZero();
        registry.close();
    }

    @Test
    void acceptsAnEmptyPayloadAsAZeroByteSample() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        UploadPayloadMetrics metrics = new UploadPayloadMetrics(registry);

        metrics.record(new byte[0]);

        DistributionSummary summary = registry
            .find("app.upload.payload.size")
            .tag("operation", "upload")
            .summary();

        assertThat(summary.count()).isEqualTo(1);
        assertThat(summary.totalAmount()).isZero();
        registry.close();
    }
}
~~~

Test dùng registry mới cho từng trường hợp để không chia sẻ state giữa các test. SimpleMeterRegistry phù hợp để kiểm tra aggregation cơ bản; nó không thay thế test cho Prometheus naming convention hoặc histogram exposition.

### Kiểm thử tại service boundary

Ngoài test metrics component, test UploadService nên xác minh:

- Payload hợp lệ được ghi đúng một sample.
- Payload vượt giới hạn bị từ chối trước khi ghi sample theo contract của bài.
- Storage thất bại vẫn giữ semantics “payload đã được tiếp nhận”.
- Một request không bị ghi ở cả controller và service.
- Payload rỗng được xử lý theo chính sách nghiệp vụ đã định nghĩa.

Có thể inject SimpleMeterRegistry vào test service, gọi upload rồi kiểm tra count(). Với storage, dùng fake hoặc mock để chủ động mô phỏng thành công và thất bại.

## 8. Thêm chiều channel nhưng giữ cardinality thấp

Nếu cần so sánh nguồn upload web và partner, có thể thêm tag channel. Giá trị phải được chuẩn hóa thành một tập hữu hạn:

~~~java
public enum UploadChannel {
    WEB("web"),
    PARTNER("partner");

    private final String metricValue;

    UploadChannel(String metricValue) {
        this.metricValue = metricValue;
    }

    public String metricValue() {
        return metricValue;
    }
}
~~~

Có thể tạo một DistributionSummary cho mỗi channel khi khởi tạo component:

~~~java
private final Map<UploadChannel, DistributionSummary> summaries;

public UploadPayloadMetrics(MeterRegistry registry) {
    EnumMap<UploadChannel, DistributionSummary> byChannel =
        new EnumMap<>(UploadChannel.class);

    for (UploadChannel channel : UploadChannel.values()) {
        DistributionSummary summary = DistributionSummary
            .builder("app.upload.payload.size")
            .description("Kích thước payload upload được tiếp nhận")
            .baseUnit("bytes")
            .tag("operation", "upload")
            .tag("channel", channel.metricValue())
            .publishPercentileHistogram()
            .serviceLevelObjectives(1_024, 10_240, 102_400, 1_048_576)
            .register(registry);

        byChannel.put(channel, summary);
    }

    this.summaries = Map.copyOf(byChannel);
}

public void record(long sizeInBytes, UploadChannel channel) {
    if (sizeInBytes < 0) {
        throw new IllegalArgumentException("size must not be negative");
    }
    summaries.get(Objects.requireNonNull(channel)).record(sizeInBytes);
}
~~~

Đoạn code là phần mở rộng thay cho field payloadSize đơn lẻ ở ví dụ trước. Cần thêm import EnumMap, Map và Objects. Việc tạo meter theo enum giới hạn trước số lượng tag value.

Không dùng các giá trị sau làm tag:

- Tên file hoặc object key.
- User ID, tenant ID hoặc customer ID.
- Request ID, trace ID hoặc UUID.
- URL đầy đủ hoặc exception message.

Các giá trị đó có thể khác nhau theo từng request và làm cardinality tăng theo lượng traffic. Nếu cần điều tra một file cụ thể, dùng log hoặc trace có correlation ID theo chính sách bảo mật.

## 9. Kiểm tra Prometheus exposition

Để xem histogram trong Prometheus, registry cần hỗ trợ histogram và meter phải được cấu hình publish histogram hoặc SLO boundaries. Ví dụ cấu hình ở bài này đã gọi publishPercentileHistogram() và serviceLevelObjectives(...).

Trong Spring Boot, bật endpoint Prometheus theo cấu hình của ứng dụng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Dependency micrometer-registry-prometheus phải có trong runtime classpath và được quản lý version bởi BOM đang dùng. Endpoint cần được bảo vệ phù hợp với môi trường triển khai. Khi ứng dụng chạy, truy cập:

~~~text
GET /actuator/prometheus
~~~

Với meter canonical app.upload.payload.size và base unit bytes, exposition Prometheus thường có các series tương ứng như:

~~~text
app_upload_payload_size_bytes_count
app_upload_payload_size_bytes_sum
app_upload_payload_size_bytes_bucket
~~~

Tên chính xác và tập series phụ thuộc phiên bản registry, NamingConvention và cấu hình histogram. Hãy kiểm tra endpoint thực tế thay vì giả định hậu tố luôn giống ví dụ.

## 10. Viết PromQL để đọc phân phối kích thước

Các query dưới đây giả định metric được xuất theo tên minh họa ở phần trước.

### Số payload mỗi giây

~~~promql
sum(rate(app_upload_payload_size_bytes_count[5m]))
~~~

Query dùng count của DistributionSummary để tính tốc độ payload được ghi nhận.

### Kích thước trung bình theo byte

~~~promql
sum(rate(app_upload_payload_size_bytes_sum[5m]))
/
sum(rate(app_upload_payload_size_bytes_count[5m]))
~~~

Đây là tổng tốc độ byte chia cho tốc độ sample trong cùng cửa sổ. Cần xử lý trường hợp không có sample để tránh kết quả rỗng hoặc NaN trong dashboard.

### p95 kích thước payload

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_upload_payload_size_bytes_bucket[5m])
  )
)
~~~

Histogram được tổng hợp trước khi tính quantile. Nếu có tag channel, có thể giữ chiều đó:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, channel) (
    rate(app_upload_payload_size_bytes_bucket[5m])
  )
)
~~~

Không tính p95 riêng từng instance rồi lấy trung bình để suy ra p95 toàn service. Histogram buckets cho phép tổng hợp các quan sát trước khi tính quantile.

### Tỷ lệ payload không vượt 1 MiB

Nếu bucket 1 MiB được xuất do SLO boundary, hãy dùng đúng giá trị le hiển thị trong exposition. Ví dụ dưới đây giả định registry xuất giá trị le là 1048576:

~~~promql
sum(rate(app_upload_payload_size_bytes_bucket{le="1048576"}[5m]))
/
sum(rate(app_upload_payload_size_bytes_count[5m]))
~~~

Query cho tỷ lệ sample có kích thước không vượt 1 MiB trong cửa sổ. Kiểm tra bucket có thực sự được xuất và label le có giá trị mong đợi.

## 11. Thực hành mở rộng

Sau khi hoàn thành phần cơ bản, thực hiện các thay đổi sau:

### Bài tập A — So sánh hai channel

Thêm tag channel chỉ nhận web hoặc partner. Gửi một nhóm payload khác nhau qua mỗi channel và kiểm tra:

- Có đúng hai meter identity theo channel.
- Count của mỗi channel đúng với số payload.
- p95 theo channel được tính từ histogram tương ứng.
- Không xuất tag chứa user ID hoặc file name.

### Bài tập B — Phân biệt bytes nhận và bytes lưu

Tạo hai metric với semantics rõ ràng:

- app.upload.payload.received.size: payload đã được tiếp nhận.
- app.upload.payload.stored.size: payload được lưu thành công.

Mô phỏng storage thất bại và xác nhận count của hai metric khác nhau đúng theo contract. Không ghi cùng một tên metric cho hai trạng thái khác nhau.

### Bài tập C — Đo streaming payload

Nếu upload được đọc theo stream, không cần ghép toàn bộ dữ liệu vào một byte[] chỉ để đo. Cộng readableByteCount của từng chunk và ghi một sample khi stream hoàn tất.

Thiết kế cần xử lý riêng:

- Complete: ghi một sample tổng kích thước.
- Error: quyết định có ghi một metric riêng cho kích thước đã nhận trước lỗi hay không.
- Cancel: không ghi như một upload hoàn tất nếu semantics yêu cầu hoàn tất.
- Duplicate terminal signal: bảo đảm chỉ ghi sample một lần.

Không ghi một sample cho mỗi chunk vào cùng metric nếu mục tiêu là kích thước của toàn bộ payload; cách đó sẽ biến phân phối payload thành phân phối chunk.

### Bài tập D — Chọn SLO boundary theo sản phẩm

Thay các ngưỡng ví dụ bằng ngưỡng thực tế của hệ thống. Giải thích vì sao cần bucket 1 MiB hoặc một ngưỡng khác, rồi kiểm tra query tỷ lệ payload dưới ngưỡng đó.

## 12. Các lỗi cần tránh

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng String.length() làm byte size | Đo số đơn vị ký tự thay vì số byte | Đo từ byte array hoặc byte stream |
| Dùng Timer cho payload size | Sai semantics và đơn vị | Dùng DistributionSummary |
| Ghi ở controller và service | Một payload bị tính hai lần | Chọn một measurement owner |
| Dùng file name làm tag | Cardinality tăng theo số file | Dùng log/trace cho định danh |
| Đổi base unit nhưng không đổi giá trị | Dữ liệu sai scale | Chuyển đổi cả input và contract |
| Chỉ bật percentile client-side | Không thể tổng hợp percentile chính xác giữa instance | Dùng histogram buckets khi cần service-level quantile |
| Không cấu hình histogram/SLO | Không có bucket phù hợp để tính p95 hoặc tỷ lệ theo ngưỡng | Bật histogram và chọn boundaries |
| Ghi một sample cho từng chunk | Đo kích thước chunk thay vì payload | Cộng bytes và ghi một lần khi hoàn tất |
| Ghi metric sau mọi retry | Một payload có thể bị tính nhiều lần | Xác định logical upload và attempt semantics |

## 13. Tiêu chí hoàn thành

- [ ] Có metric app.upload.payload.size dùng DistributionSummary.
- [ ] Meter có description và base unit bytes.
- [ ] Có histogram/SLO boundaries phù hợp.
- [ ] Payload hợp lệ được ghi đúng một sample tại ranh giới đã chọn.
- [ ] Payload âm bị từ chối trước khi ghi.
- [ ] Test xác minh count, total amount và max.
- [ ] Payload rỗng được xử lý theo chính sách đã chọn.
- [ ] Tags chỉ chứa các giá trị có cardinality thấp.
- [ ] Prometheus exposition có series count, sum và bucket khi registry hỗ trợ.
- [ ] Có query tính average và p95 từ histogram.
- [ ] Không ghi cùng một payload hai lần ở nhiều tầng.

## 14. Câu hỏi tự kiểm tra

1. Vì sao DistributionSummary phù hợp hơn Timer khi đo kích thước payload?
2. count() và totalAmount() trả lời hai câu hỏi khác nhau nào?
3. Vì sao String.length() không phải cách đáng tin cậy để đo số byte?
4. Điều gì xảy ra nếu thêm fileName làm tag?
5. Vì sao cần tổng hợp histogram buckets trước khi tính p95 toàn service?
6. Nếu storage thất bại, metric “payload received” có nên được ghi không? Hãy trả lời theo measurement contract đã chọn.
7. Với stream bị cancel sau khi đọc một phần payload, có nên ghi sample vào metric hoàn tất không?

Một phép đo kích thước hữu ích bắt đầu từ định nghĩa rõ ràng về byte nào được tính và khi nào một payload được xem là đã tiếp nhận. DistributionSummary ghi nhận từng kích thước thành một sample, cung cấp count, total amount và phân phối để theo dõi average, p95 hoặc tỷ lệ theo ngưỡng. Khi kết hợp base unit, histogram boundaries, tags hữu hạn và test tại đúng measurement boundary, dữ liệu có thể dùng để so sánh tải upload qua các instance và phiên bản mà không làm sai semantics hoặc tăng cardinality ngoài kiểm soát.
