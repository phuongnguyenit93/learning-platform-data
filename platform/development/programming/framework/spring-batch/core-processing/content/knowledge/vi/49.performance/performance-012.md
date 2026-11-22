# Benchmark dữ liệu đại diện trong Spring Batch

Một Spring Batch Job có thể xử lý 10.000 bản ghi thử nghiệm rất nhanh nhưng chậm hơn nhiều khi chạy với hàng triệu bản ghi thực tế, đặc biệt nếu dữ liệu có giá trị trùng lặp, khóa phân bố lệch, bản ghi lớn, nhiều bản ghi lỗi hoặc thường xuyên phải ghi vào cùng một nhóm dữ liệu. Vì thế, khi đánh giá hiệu năng của **Spring Batch Core Processing**, việc chọn **dữ liệu đại diện** quan trọng không kém việc đo thời gian thực thi.

**Benchmark dữ liệu đại diện** là quá trình xây dựng bộ tải thử phản ánh những đặc điểm có ảnh hưởng đến chi phí xử lý thực tế, chạy Job trong môi trường và quy trình có kiểm soát, rồi đo kết quả bằng các chỉ số nhất quán. Mục tiêu không chỉ là tìm ra “Job chạy mất bao nhiêu giây”, mà còn hiểu **tại sao tốc độ thay đổi, hệ thống nghẽn ở đâu và cấu hình nào đáp ứng yêu cầu vận hành**.

Bài học này thuộc nhóm **Performance**. Nội dung đi từ xác định tải đại diện, chuẩn bị fixture, tổ chức phép đo end-to-end, phân tích kết quả Job/Step và hạ tầng, đến thử nghiệm cấu hình chunk, transaction và chạy song song.

## 1. Benchmark khác test chức năng và stress test như thế nào?

| Loại kiểm thử | Câu hỏi chính | Dữ liệu và kết quả |
| --- | --- | --- |
| **Functional test** | Job có đọc, xử lý và ghi đúng không? | Fixture nhỏ, tập trung vào điều kiện nghiệp vụ và assertion. |
| **Benchmark đại diện** | Với dữ liệu giống vận hành, Job chạy nhanh đến đâu và sử dụng tài nguyên như thế nào? | Volume, tỷ lệ lỗi, phân phối khóa, kích thước bản ghi và hạ tầng phản ánh tải mục tiêu. |
| **Load test** | Hệ thống đáp ứng tải bình thường hoặc tải đỉnh dự kiến không? | Thử các mức tải và tần suất Job có ý nghĩa vận hành. |
| **Stress test** | Điểm bão hòa nằm ở đâu và hệ thống thất bại như thế nào? | Tăng tải vượt mức thiết kế, theo dõi lỗi/timeout/rollback. |
| **Soak test** | Chạy liên tục nhiều chu kỳ có gây rò rỉ bộ nhớ hoặc suy giảm tốc độ không? | Chạy dài hạn, theo dõi heap, GC, connection, metadata và disk. |
| **Regression benchmark** | Phiên bản mới có chậm hơn baseline đáng kể không? | Cùng quy trình và dataset, so sánh phân phối thời gian và tài nguyên. |

Benchmark tập trung vào **so sánh có thể tái lập**. Một lần chạy nhanh bất thường không đủ chứng minh cấu hình tốt hơn; một lần chạy chậm do database vừa backup cũng không chứng minh code kém hơn.

Với Batch, kết quả đúng vẫn là điều kiện bắt buộc. Nếu Job “tối ưu” bằng cách bỏ qua 20% bản ghi, throughput nhìn có vẻ tăng nhưng kết quả benchmark không hợp lệ.

## 2. Thế nào là dữ liệu đại diện?

“Có một triệu bản ghi” chưa đảm bảo đại diện. Hai tập một triệu dòng có thể tạo tải hoàn toàn khác nhau.

Ví dụ Job `importPaymentsJob` đọc giao dịch, kiểm tra định dạng, tra thông tin tài khoản, tính trạng thái và ghi vào PostgreSQL. Các yếu tố sau đều có thể làm thay đổi hiệu năng:

| Đặc điểm dữ liệu | Câu hỏi cần trả lời | Tác động thường gặp |
| --- | --- | --- |
| Số bản ghi (`row count`) | Ngày thường bao nhiêu, ngày cao điểm bao nhiêu? | Thời gian đọc, xử lý, ghi, chi phí commit. |
| Kích thước mỗi dòng | Payload trung bình và P95/P99 dài bao nhiêu? | I/O, bộ nhớ, serialization, network. |
| Phân phối khóa | Giao dịch có tập trung vào ít tài khoản/merchant không? | Hot partitions, cache miss, tranh chấp lock. |
| Tính duy nhất và trùng lặp | Tỷ lệ duplicate business key là bao nhiêu? | Index lookup, dedup, upsert, unique constraint. |
| Tỷ lệ null/invalid | Có bao nhiêu bản ghi thiếu trường hoặc sai định dạng? | Validation, skip/retry, log và đường xử lý lỗi. |
| Tỷ lệ filter | Bao nhiêu bản ghi bị `ItemProcessor` loại bỏ? | `readCount` có thể khác `writeCount`, chi phí xử lý thay đổi. |
| Cardinality | Số customer/product/account khác nhau bao nhiêu? | Hiệu quả cache, join/index, bộ nhớ lookup. |
| Phân bố giá trị | Có khóa “nóng”, giá trị cực lớn, chuỗi dài, nhóm rất đông? | Tranh chấp, độ lệch giữa partition, worst-case. |
| Sắp xếp đầu vào | Input đã được sort hay lộn xộn? | Locality của page cache, index lookup, phân phối chunk. |
| Quan hệ dữ liệu | Có parent-child, foreign key, dữ liệu tham chiếu không? | Join, validation, transaction và deadlock. |
| Dữ liệu tồn tại trước | Bảng đích đang trống hay đã có hàng chục triệu dòng? | B-tree/index size, khóa, insert so với update. |
| Biến thiên theo thời gian | Dữ liệu cao điểm cuối tháng, cuối năm khác ngày thường không? | Năng lực đáp ứng SLA trong điều kiện xấu. |

Một bộ fixture tốt được định nghĩa bằng **cấu hình workload** (workload profile) gồm nhiều thông số, chứ không chỉ bằng tên file CSV.

### Tránh benchmark với dữ liệu quá “sạch”

Nếu dữ liệu tạo ngẫu nhiên đều, mọi ID là duy nhất, payload dài như nhau và không có bản ghi lỗi, benchmark có thể bỏ qua phần tốn tài nguyên nhất ở production: lookup trên hot key, validation, retry, skip, batch update, hoặc kiểm tra unique constraint.

Ngược lại, bộ dữ liệu chứa 80% lỗi cũng không đại diện nếu production bình thường chỉ có 0,2% lỗi. Cần phân biệt **kịch bản cơ sở** với **kịch bản biên** thay vì trộn tất cả vào một điểm đo.

## 3. Xây dựng workload profile trước khi tạo dữ liệu

Giả sử hệ thống xử lý giao dịch thanh toán mỗi ngày. Một tài liệu cấu hình dữ liệu benchmark có thể mô tả:

| Thông số | Ngày bình thường (ví dụ) | Ngày cao điểm (ví dụ) | Kịch bản bất thường (ví dụ) |
| --- | ---: | ---: | ---: |
| Số giao dịch | 500.000 | 3.000.000 | 1.000.000 |
| Dung lượng đầu vào | 250 MB | 1,5 GB | 650 MB |
| Tỷ lệ dữ liệu không hợp lệ | 0,2% | 0,4% | 5% |
| Tỷ lệ business key trùng | 0,5% | 1% | 10% |
| Tỷ lệ giao dịch thuộc nhóm hot accounts | 50% | 70% | 90% |
| Chiều dài trường mô tả P95 | 200 ký tự | 400 ký tự | 1.000 ký tự |
| Dữ liệu sẵn có trong bảng đích | 5 triệu hàng | 30 triệu hàng | 30 triệu hàng |
| Mục tiêu hoàn thành | Dưới 10 phút | Dưới 40 phút | Không áp SLA thông thường |

**Tất cả số liệu trong bảng là minh họa**, không phải thống kê của một hệ thống có thật. Khi làm việc trên dự án thực tế, hãy lấy chúng từ dữ liệu vận hành đã được thống kê và cho phép sử dụng.

Mỗi profile nên chứa:

1. **Phiên bản schema** của input và output.
2. **Nguồn thống kê**: cửa sổ quan sát, cách sampling, ngày cao điểm, mức tin cậy.
3. **Khối lượng và phân phối**: tổng số bản ghi, kích thước, skew, duplicates, nulls, invalids.
4. **Seed** hoặc mã dataset để có thể tạo lại đúng đầu vào.
5. **Trạng thái hệ thống đích**: empty, partially populated, heavily indexed, cold/warm cache.
6. **Các tham số Job**: nghiệp vụ nào được chạy, cửa sổ nào, mode insert/update, chunk size.
7. **Bất biến đầu ra**: số bản ghi mong đợi, tập ID duy nhất, số bản ghi skip/filter cho phép.

Nên tách profile theo workload thật như “ngày thường”, “cuối tháng” và “dữ liệu có nhiều lỗi”; tránh lấy trung bình của mọi tình huống thành một dataset mà không tình huống thực tế nào có hình dạng tương tự.

## 4. Nguồn dữ liệu: snapshot, dữ liệu đã khử định danh hay dữ liệu tổng hợp?

Có ba hướng tiếp cận thường gặp.

### 4.1. Snapshot đã được phép sử dụng

Một bản snapshot từ môi trường đại diện có thể giữ được phân phối, số quan hệ và kích thước thực tế. Tuy nhiên, cần có quyền sử dụng rõ ràng và cơ chế bảo vệ dữ liệu; không tự động copy dữ liệu production có thông tin khách hàng vào môi trường benchmark.

Nếu sử dụng dữ liệu thật, phải thực hiện các thao tác khử định danh/che giấu phù hợp và kiểm tra rằng quá trình này **không làm biến dạng** những thuộc tính cần benchmark. Ví dụ thay mọi mã khách hàng thành cùng một chuỗi sẽ làm thay đổi cardinality, skew và hành vi unique index.

### 4.2. Dữ liệu tổng hợp (synthetic)

Sinh dữ liệu bằng chương trình có seed cố định là lựa chọn phổ biến khi cần chia sẻ fixture, tái lập kết quả và điều khiển các kịch bản biên. Điều cần giữ không chỉ là số dòng, mà cả tương quan giữa các cột.

Ví dụ: số giao dịch của một tài khoản có thể liên quan đến vùng địa lý, loại sản phẩm và kích thước giao dịch. Nếu sinh từng cột độc lập một cách ngẫu nhiên, query planner và cache có thể thấy một workload không giống hệ thống thật.

### 4.3. Bộ fixture kết hợp

Một chiến lược thực tế là dùng snapshot đã được xử lý an toàn để thống kê các phân phối, rồi sinh dữ liệu tổng hợp theo những phân phối đó. Bổ sung fixture riêng cho các tình huống ít gặp: một bản ghi cực lớn, lỗi encoding, hot key hoặc retry kéo dài.

Các thông số tạo dữ liệu cần được lưu trong version control cùng với mã generator. Không cần commit file nhiều gigabyte vào repository nếu có thể sinh lại một cách xác định.

## 5. Sinh dữ liệu tổng hợp có seed cố định

Ví dụ Java dưới đây tạo CSV với tập ID có phân phối lệch: phần lớn giao dịch tập trung vào một nhóm tài khoản nhỏ. Các giá trị và tỷ lệ chỉ nhằm minh họa kỹ thuật tạo dữ liệu.

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.SplittableRandom;

public final class PaymentCsvFixtureGenerator {

    public static void generate(
            Path destination, long numberOfRows, long seed)
            throws IOException {

        SplittableRandom random = new SplittableRandom(seed);

        try (BufferedWriter writer =
                Files.newBufferedWriter(
                        destination, StandardCharsets.UTF_8)) {

            writer.write("payment_id,account_id,amount_cents,status,note");
            writer.newLine();

            for (long i = 1; i <= numberOfRows; i++) {
                // 65% giao dịch tập trung vào 1.000 tài khoản.
                long accountId = random.nextDouble() < 0.65
                        ? random.nextLong(1, 1_001)
                        : random.nextLong(1_001, 100_001);

                long amountCents = random.nextLong(100, 500_001);

                // 1% bản ghi cần xử lý theo nhánh INVALID.
                String status = random.nextDouble() < 0.01
                        ? "INVALID" : "VALID";

                // Mô tả ngắn/dài theo một phân phối có kiểm soát.
                int descriptionLength = random.nextDouble() < 0.95
                        ? 20 : 500;

                String note = "x".repeat(descriptionLength);

                writer.write(i + "," + accountId + ","
                        + amountCents + "," + status + "," + note);
                writer.newLine();
            }
        }
    }
}
```

Cách gọi:

```java
PaymentCsvFixtureGenerator.generate(
        Path.of("build/benchmark/payments.csv"),
        1_000_000,
        20261116L
);
```

Mã trên dùng Java 17 trở lên. File đầu ra chứa header và một triệu dòng. Seed cố định cùng tham số tạo dữ liệu giúp tái lập **chuỗi bản ghi giống nhau** khi cùng mã generator được dùng.

Trong dự án thực tế, generator có thể mở rộng để tạo:

- Tỷ lệ duplicate business key có kiểm soát.
- Bản ghi thiếu trường, null, giá trị vượt miền hoặc encoding đặc biệt.
- Dữ liệu cha/con và khóa tham chiếu hợp lệ.
- Phân phối có đuôi dài (*heavy tail*) cho payload hoặc số bản ghi trên một merchant.
- Các ngày nghiệp vụ với thay đổi theo mùa hoặc sự kiện.
- File nén, định dạng JSON/Avro/Parquet nếu Job xử lý các định dạng đó.

Nếu benchmark Job xử lý file ở cloud storage, việc sinh một CSV local rồi đọc trên cùng SSD không đại diện cho độ trễ mạng, object storage và cơ chế tải về. Nguồn dữ liệu phải có **đường đi I/O phù hợp mục tiêu đo**.

### Xác minh fixture trước khi đo

Cần biết chính xác số dòng được sinh, tỷ lệ invalid, số khóa unique và kích thước file. Với workload quan trọng, lưu cùng dataset một **manifest** có seed, schema version, checksums, số dòng, tỷ lệ phân phối và thời điểm tạo.

Việc thống kê fixture nên thực hiện **trước vùng đo thời gian Job**, để chi phí kiểm tra dữ liệu đầu vào không làm nhiễu kết quả benchmark.

## 6. Chuẩn bị môi trường chạy có thể so sánh

Hai lần chạy trên những môi trường khác nhau có thể cho kết quả không so sánh được dù dùng cùng CSV.

Cần ghi lại tối thiểu:

| Thành phần | Thông tin cần cố định hoặc ghi nhận |
| --- | --- |
| Java/JVM | JDK vendor/version, heap size, GC, các JVM options quan trọng. |
| Spring Boot/Spring Batch | Phiên bản, cấu hình Job, reader/processor/writer. |
| Database | Engine/version, cấu hình CPU/RAM/storage, transaction isolation, index và statistics. |
| JDBC/pool | Driver, pool size, timeout, fetch size, batch writer settings. |
| Máy chạy Job | Số vCPU, memory, container limits, node placement. |
| File và network | Local SSD, network drive, object storage, băng thông và latency. |
| Workload | Dataset ID/checksum, row count, phân phối, trạng thái bảng đích. |
| Job | Chunk size, commit interval, thread count, partitioning, retry/skip policy. |
| Background load | Job khác, database maintenance, backup, autoscaling, antivirus, monitoring. |
| Cách đo | Warm-up, số lần lặp, phạm vi timer, cách tính percentile. |

Benchmark môi trường shared CI có thể dùng để phát hiện suy giảm lớn, nhưng khó đưa ra kết luận chính xác về thay đổi chỉ vài phần trăm nếu máy chủ và database đang chịu tải biến thiên. Với những quyết định tối ưu có ảnh hưởng lớn, nên dùng môi trường ổn định hoặc lặp đủ nhiều và xem cả biến thiên kết quả.

### Cold cache và warm cache là hai tình huống khác nhau

- **Cold run:** dữ liệu và page cache ít được làm nóng; có thể tăng chi phí I/O.
- **Warm run:** dữ liệu, kết nối và JIT có thể đã được làm nóng từ các lượt trước.

Đừng trộn cold run với warm run rồi báo một “thời gian trung bình” duy nhất. Có thể đo riêng “first run after deployment” và “steady state daily run”, tùy mục tiêu vận hành.

Việc xóa page cache cấp hệ điều hành trên một máy dùng chung thường không phù hợp và có thể ảnh hưởng hệ thống khác. Nếu cần thử cold-cache thật, tổ chức môi trường kiểm soát riêng thay vì can thiệp máy production.

## 7. Xác định ranh giới phép đo thời gian

Một Job có nhiều phần chi phí:

```text
Prepare fixture ── Launch Job ── Read ── Process ── Write/Commit ── End
      |               |                                      |        |
      A               B                                      C        D
```

Tùy mục đích, có thể đo các khoảng:

- **End-to-end latency (B → D):** từ khi ứng dụng bắt đầu yêu cầu khởi chạy đến khi Job thực sự kết thúc và kết quả có thể quan sát được.
- **Job processing duration:** từ lúc Job bắt đầu vào pipeline đến khi xử lý xong.
- **Step duration:** thời gian từng Step.
- **Chunk latency:** thời gian để xử lý và commit một chunk.
- **Preparation time (A → B):** sinh/nhập fixture, làm sạch bảng, chạy migration; thường nên báo riêng nếu không thuộc SLA production.

Điều bắt buộc là **mô tả ranh giới đo**. Nếu một nhóm đo riêng phần `ItemProcessor` còn nhóm khác đo cả việc ghi DB, không thể so sánh throughput như thể hai phép đo giống nhau.

### Cẩn thận với launcher bất đồng bộ

Trong Spring Batch, launcher/operator có thể dùng `TaskExecutor` bất đồng bộ. Khi đó, lời gọi chạy Job có thể trả về ở trạng thái `STARTING` hoặc `STARTED`. Lấy thời gian trước và ngay sau lời gọi launch trong trường hợp này chỉ đo **thời gian gửi yêu cầu**, không phải thời gian Job xử lý xong.

Để benchmark thời gian end-to-end:

1. Ghi `System.nanoTime()` trước khi gọi launcher.
2. Khởi chạy Job và lấy `jobExecutionId`.
3. Nếu launcher bất đồng bộ, chờ trạng thái cuối với timeout bằng `JobExplorer` hoặc cơ chế hoàn tất được kiểm soát.
4. Ghi thời gian kết thúc khi trạng thái đã thực sự terminal.
5. Assert `BatchStatus` và kết quả nghiệp vụ trước khi nhận số đo.

`System.nanoTime()` thích hợp để đo khoảng thời gian trong một JVM. Không dùng hai timestamp từ hai máy chưa đồng bộ để tính độ trễ chính xác ở mức millisecond.

## 8. Một quy trình benchmark Spring Batch có thể tái lập

Quy trình đề xuất:

```text
Chọn workload profile và tiêu chí đạt
             |
             v
Sinh/khởi tạo fixture + đo kích thước/phân phối
             |
             v
Cố định môi trường, cấu hình Job và trạng thái bảng đích
             |
             v
Warm-up (tách khỏi số liệu báo cáo)
             |
             v
Lặp N lần:
  ├─ Reset/khởi tạo dữ liệu đầu vào và đích (ngoài timer)
  ├─ Tạo JobParameters của lượt chạy
  ├─ Start timer
  ├─ Chạy Job đến trạng thái cuối
  ├─ Stop timer
  ├─ Assert trạng thái + dữ liệu đầu ra
  └─ Ghi metrics và cleanup cho lượt kế tiếp
             |
             v
Tính p50, p95, min/max, throughput, độ biến thiên
             |
             v
Đối chiếu baseline + kiểm tra DB/JVM bottleneck
```

Nên có ít nhất một lượt warm-up trước khi thu số liệu; với hệ thống có JIT, connection pool, cache và các dependency lớn, số lượt warm-up cần được quyết định theo độ ổn định quan sát được.

Số lần lặp cũng tùy thời gian Job: một benchmark kéo dài 40 phút có thể phải chạy ít lần hơn bài 20 giây, nhưng khi đó cần ghi rõ độ không chắc chắn của kết quả và tránh so sánh thay đổi rất nhỏ như thể đã được chứng minh.

## 9. Ví dụ benchmark tích hợp với Spring Batch 5.x

Ví dụ sử dụng **Spring Batch 5.x**, **Spring Boot 3.x**, JUnit Jupiter, AssertJ và `spring-batch-test`. Giả sử ứng dụng đã định nghĩa bean `importPaymentsJob` và một dịch vụ fixture `PaymentBenchmarkFixture` có các phương thức:

- `resetAndLoad(int rowCount, long seed)`: dọn dữ liệu cũ và nạp input **trước khi bắt đầu đo**.
- `assertProcessed(int rowCount)`: kiểm tra kết quả theo hợp đồng nghiệp vụ **sau khi dừng timer**.

`PaymentBenchmarkFixture` là thành phần test **do dự án triển khai**, không phải lớp có sẵn của Spring Batch.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportPaymentsBenchmarkIT {

    private static final int ROWS = 100_000;
    private static final long SEED = 20261116L;
    private static final int WARMUP_RUNS = 2;
    private static final int MEASURED_RUNS = 8;

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importPaymentsJob")
    private Job job;

    @Autowired
    private PaymentBenchmarkFixture fixture;

    @Test
    void benchmarkWithRepresentativeFixture() throws Exception {
        jobLauncherTestUtils.setJob(job);
        List<Long> durationsMs = new ArrayList<>();

        for (int run = 0;
                run < WARMUP_RUNS + MEASURED_RUNS;
                run++) {

            // Ngoài khoảng đo: dữ liệu đầu vào giống nhau mỗi lượt.
            fixture.resetAndLoad(ROWS, SEED);

            // Mỗi lượt độc lập tạo JobInstance riêng.
            JobParameters params = new JobParametersBuilder()
                    .addString(
                            "benchmarkRunId",
                            UUID.randomUUID().toString(),
                            true)
                    .addString("dataset", "payments-100k", false)
                    .toJobParameters();

            long startedNanos = System.nanoTime();
            JobExecution execution =
                    jobLauncherTestUtils.launchJob(params);
            long elapsedNanos = System.nanoTime() - startedNanos;

            assertThat(execution.getStatus())
                    .isEqualTo(BatchStatus.COMPLETED);
            fixture.assertProcessed(ROWS);

            if (run >= WARMUP_RUNS) {
                durationsMs.add(
                        TimeUnit.NANOSECONDS.toMillis(elapsedNanos));
            }
        }

        Collections.sort(durationsMs);

        long p50 = percentileNearestRank(durationsMs, 0.50);
        long p95 = percentileNearestRank(durationsMs, 0.95);

        System.out.printf(
                "rows=%d samples=%d p50Ms=%d p95Ms=%d%n",
                ROWS, durationsMs.size(), p50, p95
        );
    }

    private static long percentileNearestRank(
            List<Long> sortedSamples, double quantile) {
        if (sortedSamples.isEmpty()) {
            throw new IllegalArgumentException("No measurements");
        }

        int rank = (int) Math.ceil(quantile * sortedSamples.size());
        int index = Math.max(0, Math.min(
                rank - 1, sortedSamples.size() - 1));

        return sortedSamples.get(index);
    }
}
```

Bài test trên minh họa **benchmark harness**, chưa bao gồm mã fixture phụ thuộc vào database/file cụ thể. Phải bảo đảm `PaymentBenchmarkFixture` thực sự nạp lại cùng input, reset trạng thái bảng đích và xác nhận đúng kết quả của Job. Không dùng fixture chỉ assert row count nếu các bản ghi có thể bị trùng business key.

Ví dụ sử dụng launcher **đồng bộ**. Nếu Job dùng launcher bất đồng bộ, cần sửa khoảng đo theo mục 7 để chờ trạng thái cuối với timeout; nếu không, số đo chỉ phản ánh thời gian submit.

### Vì sao phải có `benchmarkRunId` mới?

`JobInstance` được xác định bằng tên Job và identifying JobParameters. Nếu dùng lại chính xác parameters của lần Job đã `COMPLETED`, Spring Batch có thể từ chối lần tiếp theo bằng `JobInstanceAlreadyCompleteException`.

`benchmarkRunId` ở ví dụ là identifying parameter để mỗi lượt benchmark độc lập. Đối với benchmark **restart**, cần một kịch bản khác giữ nguyên identifying parameters giữa lần lỗi và lần restart.

### Không trộn chi phí reset vào vùng đo

`fixture.resetAndLoad(...)` có thể xóa và ghi hàng trăm nghìn dòng; nếu nó nằm giữa `startedNanos` và `elapsedNanos`, kết quả không còn là thời gian riêng của Spring Batch Job. Trong production, nếu Job có bước tự staging hoặc tải input, bước đó cần được đưa vào phạm vi timer một cách có chủ đích.

### Không xóa metadata quá sớm

Sau khi Job kết thúc, cần giữ lại `JobExecution`/`StepExecution` đủ lâu để thu thập thông tin và chẩn đoán nếu benchmark bất thường. Khi dọn metadata, chỉ dùng repository test riêng và công cụ phù hợp như `JobRepositoryTestUtils`. Không dọn metadata khi Job bất đồng bộ còn đang chạy.

Dữ liệu nghiệp vụ cần được reset độc lập với metadata Spring Batch. Việc rollback transaction của một test method không nhất thiết rollback được các transaction mà Job thực hiện qua chunk.

## 10. Những chỉ số quan trọng cho benchmark

### 10.1. Throughput

Throughput thường tính bằng:

\[
\text{Throughput} = \frac{\text{Số item được xử lý}}{\text{Thời gian đo (giây)}}
\]

Ví dụ Job xử lý 1.000.000 bản ghi trong 125 giây:

\[
\frac{1.000.000}{125} = 8.000\ \text{item/giây}
\]

**Phải nói rõ “số item” là số đọc, số ghi hay số nghiệp vụ thành công.** Nếu 30% input bị filter hoặc skip, throughput theo `readCount` sẽ khác throughput theo `writeCount`. Cả hai có thể hữu ích, nhưng không được đánh tráo mẫu số.

Có thể thêm:

- Bytes processed/second cho Job đọc payload có kích thước biến thiên.
- Rows written/second cho Job chủ yếu ghi database.
- Business entities completed/second cho Job xử lý nhóm nhiều bản ghi.
- Scheduled windows/hour nếu một Job xử lý theo cửa sổ thời gian.

### 10.2. Latency

- **Job wall-clock duration:** khoảng thời gian thực tế người vận hành chờ để nhận kết quả.
- **Step duration:** giúp tìm Step chiếm nhiều thời gian nhất.
- **Chunk duration:** cho thấy commit hoặc một nhóm item có bị chậm bất thường.
- **Per-item latency:** hữu ích nếu processor gọi API ngoài, nhưng thường không phản ánh trực tiếp toàn bộ chi phí chunk/transaction.

### 10.3. Reliability và kết quả

- `BatchStatus` và `ExitStatus` cuối.
- `readCount`, `writeCount`, `filterCount`, `skipCount`.
- `commitCount`, `rollbackCount`, số lần retry và lỗi theo loại.
- Số bản ghi duy nhất ở bảng đích, kiểm tra checksum hoặc business key.
- Khả năng restart và không ghi trùng khi xảy ra lỗi.

Một cấu hình nhanh hơn nhưng có thêm rollback, deadlock hoặc dữ liệu sai không được xem là cải thiện hiệu năng hợp lệ.

### 10.4. Tài nguyên hạ tầng

| Lớp | Chỉ số quan sát | Dấu hiệu thường gặp |
| --- | --- | --- |
| JVM | Heap used, allocation rate, GC pause, CPU, thread count | Tạo đối tượng nhiều, memory pressure, thread contention. |
| Database | CPU, active sessions, locks, slow queries, buffer hits, WAL/redo | Query/index nghẽn, commit đắt, tranh chấp khóa. |
| Connection pool | Active/idle/pending connections, thời gian chờ connection | Pool quá nhỏ hoặc database không đủ khả năng phục vụ. |
| File/storage | Read/write throughput, IOPS, latency, file cache | Reader/Writer bị giới hạn bởi I/O. |
| Network | Latency, throughput, retry, socket timeout | API/object store hoặc DB qua mạng là nút nghẽn. |
| Spring Batch | Step status, counters, số chunk, commit, rollback | Chi phí xử lý, quy mô transaction, lỗi trên từng bước. |

Số liệu từ Micrometer, Java Flight Recorder (JFR), database monitoring, connection pool metrics và log Job/Step hỗ trợ giải thích kết quả. Không cần bật mọi loại profiling cho mọi lần chạy chuẩn, vì profiler có thể bổ sung overhead; cần ghi rõ benchmark nào được chạy có profiler.

## 11. Instrumentation bằng `JobExecutionListener`

Một listener gắn ở Job có thể đo khoảng thời gian thực thi **từ `beforeJob` đến `afterJob`**. Đây là phép đo nội bộ, không hoàn toàn bằng end-to-end duration tính từ lớp launcher.

Ví dụ cho Spring Batch 5.x:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public final class JobTimingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobTimingListener.class);

    private final ConcurrentMap<Long, Long> startedAt =
            new ConcurrentHashMap<>();

    @Override
    public void beforeJob(JobExecution execution) {
        startedAt.put(execution.getId(), System.nanoTime());
    }

    @Override
    public void afterJob(JobExecution execution) {
        Long start = startedAt.remove(execution.getId());
        if (start == null) {
            return;
        }

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );

        log.info(
                "batch.job.timing jobName={} jobExecutionId={} "
                    + "jobInstanceId={} status={} durationMs={}",
                execution.getJobInstance().getJobName(),
                execution.getId(),
                execution.getJobInstance().getInstanceId(),
                execution.getStatus(),
                elapsedMs
        );
    }
}
```

Cần đăng ký listener vào Job khi tạo Job builder. `@Component` giúp Spring tạo bean nhưng không tự đảm bảo Job gọi listener đó.

Vì listener là singleton, `ConcurrentHashMap` tránh ghi đè đồng hồ đo khi có nhiều JobExecution cùng chạy. `remove(...)` trong callback kết thúc giải phóng trạng thái. Nếu JVM bị kill đột ngột, `afterJob` có thể không chạy; không dựa vào listener đơn lẻ để bảo đảm audit hoặc retention của mọi phép đo.

Nếu chỉ cần đo được từ metadata, có thể lấy `startTime` và `endTime` của JobExecution sau khi Job kết thúc. Tuy nhiên độ chính xác và thời điểm lưu timestamp phụ thuộc phiên bản/schema; để so sánh từng thay đổi nhỏ, đồng hồ monotonic trong cùng JVM thường phù hợp hơn.

### Log định danh, tránh cardinality cao cho metrics

Trong log có thể thêm `jobExecutionId` để điều tra lần chạy chậm. Nhưng nếu xuất metrics qua Micrometer/Prometheus, **không nên gắn `jobExecutionId` thành tag**: mỗi execution tạo một giá trị mới, khiến số chuỗi thời gian tăng rất lớn.

Tag hữu ích thường là `jobName`, `stepName`, `status`, `environment` và một số profile benchmark được định nghĩa hữu hạn. Để phân tích một execution, dùng log/tracing thay cho tag metric không giới hạn.

## 12. Tách chi phí theo Step và chunk

Một Job có thể hoàn tất trong 15 phút, nhưng chưa rõ thời gian bị tiêu thụ ở đâu:

```text
Job importPaymentsJob            15 phút
├── validateInputStep              1 phút
├── loadReferenceDataStep          1 phút
├── transformAndWriteStep         12 phút
└── finalizeStep                   1 phút
```

Trong ví dụ, Step thứ ba chiếm phần lớn thời gian. Tiếp tục đo:

- Thời gian `read()`: đọc file, query DB, parse, deserialize.
- Thời gian `process()`: validation, lookup, biến đổi, gọi dịch vụ.
- Thời gian `write()`: JDBC batch insert/upsert, gửi API, serialize.
- Thời gian commit transaction: ghi WAL/redo, flush, lock.
- Thời gian chờ: pool connection, thread queue, API downstream, filesystem.

Không nên kết luận “processor chậm” chỉ vì Step chunk-oriented chậm. Step duration bao gồm cả reader, writer, transaction, retry, skip và nhiều chi phí khác.

### Các listener dùng cho quan sát

Spring Batch cung cấp các điểm mở rộng như `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `ChunkListener` và `StepExecutionListener`. Chúng có thể ghi metric chi tiết theo giai đoạn.

Tuy nhiên, callback có thể được gọi với tần suất rất cao. Nếu một triệu item kích hoạt một log INFO cho từng read/process/write, overhead từ logging có thể làm benchmark đo **chi phí logging** thay vì chi phí xử lý thật.

Thường nên:

1. Thu thập số liệu bằng counter/timer tối giản.
2. Tổng hợp theo Step/chunk hoặc theo khoảng thời gian.
3. Ghi log theo mẫu (sampling) nếu cần debug từng item.
4. So sánh một lần có instrumentation và một lần với logging production tương ứng để hiểu overhead.

Khi Step chạy đa luồng hoặc partitioning, bộ đo phải thread-safe và không dựa vào thứ tự callback của các thread.

## 13. Benchmark chunk size và commit interval

Trong chunk-oriented processing, Spring Batch thường thực hiện chu kỳ:

```text
read -> process -> read -> process -> ... [đủ chunk]
                       |
                       v
                    write(...)
                       |
                       v
                commit transaction
                       |
                       v
                  chunk tiếp theo
```

Cấu hình chunk size ảnh hưởng đến:

| Chunk nhỏ | Chunk lớn |
| --- | --- |
| Commit thường xuyên hơn. | Commit ít lần hơn với cùng số bản ghi. |
| Transaction ngắn hơn. | Transaction có thể giữ tài nguyên lâu hơn. |
| Bộ nhớ cho buffer chunk thường thấp hơn. | Bộ nhớ cần cho chunk có thể tăng. |
| Overhead transaction có thể cao. | Khi rollback, công việc của chunk lớn hơn có thể phải xử lý lại. |
| Có thể làm batch write kém hiệu quả. | Có thể tăng hiệu quả ghi nhưng chạm giới hạn DB/driver. |

Không tồn tại chunk size tối ưu cho mọi Job. Các cấu hình thường được thử có thể là 100, 500 và 1.000 item/chunk, nhưng con số đó chỉ là **ứng viên**, phải đo với workload thật và hạn chế bộ nhớ.

Ví dụ ma trận thử nghiệm:

| Thử nghiệm | Chunk size | Thread count | Reader/Writer | Dataset |
| --- | ---: | ---: | --- | --- |
| A | 100 | 1 | Cấu hình cố định | Profile ngày thường |
| B | 500 | 1 | Cấu hình cố định | Cùng profile, cùng seed |
| C | 1.000 | 1 | Cấu hình cố định | Cùng profile, cùng seed |

Giữ các tham số còn lại nhất quán để có thể quy nguyên nhân khác biệt cho chunk size. Sau khi tìm mức phù hợp, mới thử thêm concurrency hoặc thay đổi writer.

Ở Spring Batch 5.x, ví dụ một Step:

```java
@Bean
Step processPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ItemProcessor<Payment, Payment> processor,
        ItemWriter<Payment> writer) {

    return new StepBuilder("processPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Payment` và các bean reader/processor/writer thuộc dự án tự định nghĩa. Không chỉnh chunk size mà bỏ qua nghiệp vụ retry/skip và giới hạn transaction; nếu quá nhiều retry hoặc rollback, cấu hình có throughput trung bình cao hơn vẫn có thể gây tác động vận hành tệ hơn.

## 14. Benchmark chạy song song: thread count và partitioning

Sau khi xác định baseline tuần tự, có thể thử multi-threaded Step hoặc partitioning để tận dụng nhiều CPU hoặc I/O song song.

Một phép thử có thể sử dụng:

| Cấu hình | Chunk size | Threads | Partitioning | Mục tiêu |
| --- | ---: | ---: | --- | --- |
| Baseline | 500 | 1 | Không | Thời gian xử lý tuần tự. |
| Parallel 2 | 500 | 2 | Không | Xem hiệu quả khi tăng worker. |
| Parallel 4 | 500 | 4 | Không | Phân biệt bottleneck CPU, DB, I/O. |
| Partition 4 | 500 | Theo executor | 4 partition | Tách các tập dữ liệu độc lập. |

**Tăng thread không đảm bảo tăng throughput tuyến tính.** Nếu database chỉ cấp 4 connection mà các service khác đang dùng 3, thêm 16 worker có thể chủ yếu làm chúng chờ connection. Tương tự, writer cập nhật cùng hot rows có thể gây lock contention, retry hoặc deadlock.

Khi benchmark song song, cần quan sát:

- CPU utilization của Job và database.
- Active/pending connection pool.
- Số transaction và thời gian chờ lock.
- Queue depth của executor, active workers.
- Số rollback/retry/skip.
- Tính an toàn của `ItemReader`, `ItemWriter` và những state dùng chung.
- Số business key duy nhất và tính đúng đắn của dữ liệu kết quả.

Nếu `ItemReader` không thread-safe, benchmark multi-threaded có thể cho ra kết quả sai hoặc không ổn định. Trước khi so tốc độ, phải xác nhận thiết kế concurrent đọc/ghi phù hợp hoặc chuyển sang partitioning có vùng dữ liệu độc lập.

### Phân phối lệch gây mất cân bằng partition

Giả sử 4 partition được chia theo merchant, nhưng 70% giao dịch thuộc merchant 1:

```text
Partition 1: ███████████████████████ 70%
Partition 2: ███                      10%
Partition 3: ███                      10%
Partition 4: ███                      10%
```

Dù có 4 worker, 3 worker có thể hoàn tất sớm rồi chờ worker còn lại. Benchmark dataset có phân phối đều 25%/partition sẽ **đánh giá quá cao** khả năng tăng tốc.

Do đó, benchmark đại diện phải giữ skew thực tế hoặc thử riêng hai profile đều và lệch để đánh giá chiến lược chia partition.

## 15. Tính các thống kê kết quả benchmark

Giả sử một Job chạy trên cùng dataset 100.000 bản ghi trong 8 lần sau warm-up, thu được:

```text
Thời gian (giây):
12.1, 11.9, 12.4, 13.0, 12.0, 12.2, 12.5, 13.7
```

**Đây là số giả định** để minh họa cách báo cáo, không phải phép đo thực tế.

Các thống kê phổ biến:

- **Min/Max:** khoảng thời gian nhanh nhất/chậm nhất.
- **Median (P50):** giá trị giữa sau khi sắp xếp, ít nhạy với outlier hơn mean.
- **P95:** mốc mà khoảng 95% mẫu nằm dưới hoặc bằng, dùng để quan sát đuôi chậm.
- **Mean:** tổng thời gian chia số lượt chạy, hữu ích nhưng bị outlier ảnh hưởng.
- **Standard deviation hoặc IQR:** mức biến thiên giữa các lần chạy.
- **Throughput:** số item xử lý hoặc ghi thành công chia thời gian của từng lần chạy.

Với số mẫu nhỏ như 8, **P95 gần như là lần chạy chậm nhất** theo cách tính nearest-rank. Không nên đưa ra cam kết SLA P95 chỉ dựa vào vài lượt thử. Nếu cần tin cậy vào percentile đuôi, hãy thu thập đủ nhiều mẫu trên nhiều chu kỳ vận hành hoặc áp dụng phương pháp thống kê phù hợp.

### Bảng báo cáo một benchmark

| Chỉ số | Baseline (ví dụ) | Candidate (ví dụ) | Diễn giải |
| --- | ---: | ---: | --- |
| Dataset | 1.000.000 records | 1.000.000 records | Cùng seed/phân phối |
| Chunk size | 100 | 500 | Thay đổi chính |
| Threads | 1 | 1 | Giữ nguyên |
| Median duration | 150 s | 125 s | Candidate nhanh hơn ở trung vị |
| Throughput từ median | ≈6.667 rows/s | 8.000 rows/s | Cần định nghĩa rows processed |
| P95 duration | 175 s | 140 s | Candidate ít chậm hơn ở các lượt đuôi |
| Max heap | 1,1 GB | 1,6 GB | Candidate cần thêm bộ nhớ |
| Rollback count | 0 | 0 | Không thay đổi về lỗi transaction |
| Kết quả dữ liệu | Đúng | Đúng | Cả hai phải cùng hợp đồng nghiệp vụ |

Tất cả số liệu trong bảng là **minh họa**. Không báo một candidate “tăng 20% hiệu năng” chỉ dựa trên một bảng không có số lần lặp, môi trường, mức biến thiên và điều kiện workload rõ ràng.

### Độ khác biệt có ý nghĩa vận hành

Giảm thời gian trung vị từ 125 giây còn 123 giây có thể không đáng tin cậy nếu độ biến thiên mỗi lần chạy là ±10 giây. Nhưng giảm thời gian từ 40 phút xuống 20 phút trên nhiều lần chạy với dữ liệu tương đương thường đáng chú ý hơn.

Cần so sánh cả **chi phí tài nguyên**. Một cấu hình chạy nhanh hơn 10% nhưng dùng gấp ba database connection có thể không phù hợp nếu nhiều Job cùng chạy trong cửa sổ batch.

## 16. Phát hiện bottleneck từ số liệu

Không nên tối ưu chỉ bằng cách tăng chunk size hoặc số thread. Hãy nối kết quả đo với giới hạn thực tế.

### 16.1. Reader hoặc file I/O

Dấu hiệu:

- CPU thấp, reader mất nhiều thời gian.
- Độ trễ file/object store cao.
- Throughput tăng rõ khi dữ liệu được cache.
- `fetchSize` hoặc query pagination chưa phù hợp.

Hướng điều tra: file encoding, nén, I/O buffering, query plan, fetch size, index, mạng đến storage và cách reader quản lý cursor.

### 16.2. Processor sử dụng CPU

Dấu hiệu:

- JVM CPU cao trong khi database và I/O còn dư.
- Allocation/GC tăng, nhiều thao tác parse, regex hoặc serialize.
- Thời gian trên mỗi item tương đối ổn định theo kích thước input.

Hướng điều tra: JFR hoặc profiler CPU, tạo đối tượng không cần thiết, thuật toán lookup, cache tham chiếu và concurrency nếu logic thread-safe.

### 16.3. Writer hoặc database

Dấu hiệu:

- DB CPU, I/O hoặc transaction latency cao.
- Connection pool pending tăng.
- Lock waits/duplicate checks/index updates tăng.
- Các chunk lớn tạo nhiều rollback hoặc transaction kéo dài.

Hướng điều tra: JDBC batching, query plan, index, schema constraint, locking, batch upsert, commit interval và kích thước pool. Không tắt ràng buộc dữ liệu chỉ để benchmark trông nhanh hơn nếu production phải giữ chúng.

### 16.4. Dữ liệu phân bố lệch

Dấu hiệu:

- Một partition chạy lâu hơn hẳn các partition còn lại.
- Một số business key bị tranh chấp.
- Mở rộng thread count không cải thiện tốc độ.

Hướng điều tra: phân phối khóa trong dataset, chiến lược partition, cơ chế phân đoạn công việc và các hàng bị cập nhật nóng.

### 16.5. Retry, skip hoặc external API

Dấu hiệu:

- Job nhanh khi dữ liệu sạch, chậm mạnh khi tỷ lệ lỗi tăng.
- Nhiều `rollbackCount`, timeout, backoff.
- External API có rate limit.

Hướng điều tra: tỷ lệ lỗi thực tế, chính sách skip/retry, exponential backoff, circuit breaker, giới hạn downstream. Không tăng concurrency vượt rate limit chỉ vì chỉ số throughput riêng của Job trong test trở nên đẹp hơn.

## 17. Bảo đảm tính công bằng khi so hai phiên bản

Khi đo trước/sau một thay đổi:

1. **Giữ nguyên workload profile và seed** hoặc dùng những bộ dataset đã chuẩn hóa tương đương.
2. **Giữ nguyên schema và data state** trước mỗi lượt thử, bao gồm index và số hàng sẵn có.
3. **Ghi commit hash/build version** của ứng dụng và phiên bản Java/database.
4. **Giữ nguyên giới hạn tài nguyên**, container limits, pool và cấu hình executor trừ biến đang thử.
5. **Warm-up nhất quán**, phân biệt kết quả cold/warm.
6. **Chạy nhiều lượt** theo thứ tự có kiểm soát; cân nhắc xen kẽ A/B để giảm ảnh hưởng drift môi trường.
7. **Xác minh kết quả dữ liệu** của mỗi lần chạy trước khi nhận thời gian đo.
8. **Ghi lại outlier cùng hoàn cảnh** (backup DB, GC dài, pod bị reschedule) thay vì âm thầm xóa chúng.
9. **Kiểm tra trạng thái JobRepository** để không tái sử dụng JobInstance đã hoàn thành ngoài ý muốn.
10. **Lưu báo cáo số đo thô**, không chỉ p50 hoặc một con số “nhanh hơn”.

Không thay nhiều tham số cùng lúc nếu mục tiêu là hiểu nguyên nhân. Ví dụ đổi chunk size, thread count và index DB trong một thí nghiệm có thể tạo cải thiện, nhưng không biết thành phần nào đã mang lại kết quả.

### Phân biệt kiểm thử hiệu năng trên một lượt và sản xuất liên tục

Một Job có thể chạy nhanh trong môi trường test khi được toàn bộ CPU của database phục vụ, nhưng lúc vận hành phải chia tài nguyên với API và các Job khác. Benchmark “một Job đơn lẻ” nên đi kèm workload profile “nhiều Job trùng cửa sổ” nếu đó là tình huống production.

## 18. Dữ liệu đại diện cho restart, skip và failure

Benchmark chỉ đo đường thành công chưa phản ánh một hệ thống Batch cần restart và xử lý dữ liệu lỗi.

### Kịch bản skip/filter

Nếu Job cho phép skip bản ghi invalid, cần đo riêng profile có tỷ lệ invalid đại diện. Assert cả `skipCount`, `filterCount`, `readCount` và `writeCount` sau khi chạy.

### Kịch bản retry

Nếu writer gọi API hoặc database có lỗi tạm thời, thử nghiệm cần tạo lỗi với tần suất và thời lượng có kiểm soát. Thời gian retry/backoff có thể chiếm phần đáng kể tổng Job duration. Không để network lỗi ngẫu nhiên khiến so sánh giữa baseline và candidate thiếu công bằng.

### Kịch bản restart

Benchmark restart cần:

1. Chạy Job bằng identifying parameters cố định cho một đơn vị công việc.
2. Cố ý tạo lỗi ở checkpoint có xác định.
3. Ghi lại JobExecution `FAILED` và metadata cần restart.
4. Sửa điều kiện lỗi và chạy lại với **cùng identifying parameters**.
5. Đo thời gian restart và tổng thời gian phục hồi.
6. Kiểm tra dữ liệu không mất/trùng sau restart.
7. Chỉ dọn metadata sau khi hoàn tất kịch bản.

Không dùng `benchmarkRunId` mới ở lần restart vì điều đó có thể tạo JobInstance khác. Không xóa bảng metadata giữa hai lần chạy vì sẽ mất checkpoint.

### Đo cả chi phí phục hồi

Với nghiệp vụ quan trọng, một cấu hình chạy nhanh nhưng khi lỗi phải xử lý lại hàng triệu bản ghi có thể kém hơn cấu hình chậm hơn một chút nhưng checkpoint hiệu quả. Thêm **recovery time** và khối lượng công việc phải xử lý lại vào tiêu chí hiệu năng.

## 19. Lưu kết quả và thiết lập baseline

Có thể lưu mỗi lần đo thành một record JSON:

```json
{
  "benchmarkId": "payments-normal-v1",
  "dataset": {
    "profile": "normal",
    "rows": 1000000,
    "seed": 20261116,
    "generatorVersion": "v1"
  },
  "environment": {
    "jdk": "17",
    "springBatchLine": "5.x",
    "database": "postgresql-test",
    "cpuLimit": "4 vCPU",
    "heap": "2 GiB"
  },
  "configuration": {
    "chunkSize": 500,
    "threads": 1
  },
  "result": {
    "jobStatus": "COMPLETED",
    "wallTimeMs": 125000,
    "readCount": 1000000,
    "writeCount": 1000000,
    "skipCount": 0,
    "outputValidated": true
  }
}
```

Đây là **mẫu định dạng báo cáo**, không phải dữ liệu đo thật. Nên bổ sung commit hash, DB schema version, checksum fixture, timestamp, warm-up policy, CPU/GC/DB metrics và file log raw khi áp dụng vào một dự án.

Một bảng tổng hợp theo lần chạy có thể có:

```text
benchmark_id,run_id,profile,rows,chunk_size,threads,status,
elapsed_ms,read_count,write_count,skip_count,commit_count,
rollback_count,peak_heap_mb,db_p95_ms,build_sha
```

Phân biệt **raw runs** với thống kê tổng hợp. Khi so baseline/candidate, báo cả số mẫu và phương pháp tính percentile. Nếu quá trình benchmark đang dùng một môi trường thay đổi tài nguyên tự động, kết quả cần ghi rõ điều kiện autoscaling.

### Cảnh báo regression theo ngưỡng

Có thể đặt chính sách kiểm tra:

- Thời gian median tăng quá một tỷ lệ đáng kể so với baseline đã chấp nhận.
- P95 vượt giới hạn cửa sổ Batch hoặc ngưỡng vận hành.
- Throughput giảm trong khi số bản ghi và kích thước dữ liệu giữ nguyên.
- Peak heap vượt giới hạn có nguy cơ OOM.
- Rollback/skip/error tăng ngoài hợp đồng.
- Dữ liệu đầu ra sai, dù thời gian nhanh.

Không nên để bài benchmark biến thành test CI bắt buộc với ngưỡng thời gian quá chặt trên runner không ổn định. Có thể tách smoke performance (phát hiện suy giảm lớn) và benchmark định kỳ trên môi trường hiệu năng chuyên dụng.

## 20. Bài tập thực hành: chọn cấu hình xử lý 2 triệu bản ghi

Giả sử `importOrdersJob` đọc 2.000.000 dòng đơn hàng, kiểm tra mã sản phẩm, tính giá và ghi vào PostgreSQL. Production có cả ngày bình thường và cuối tháng, khi một số mã sản phẩm xuất hiện nhiều hơn bình thường.

**Yêu cầu nghiệp vụ:** xử lý đủ các đơn hợp lệ trong cửa sổ 20 phút, không ghi trùng business key, giữ được khả năng restart sau lỗi. Không đổi ràng buộc dữ liệu hoặc chính sách retry/skip chỉ để cải thiện thời gian.

### Giai đoạn 1: Xây dựng dữ liệu

1. Tạo profile `normal` và `month-end`. Mỗi profile có 2 triệu bản ghi, nhưng khác tỷ lệ hot product, kích thước payload, số đơn trùng và tỷ lệ invalid.
2. Sử dụng seed cố định; lưu manifest schema, generator version, số dòng và checksum.
3. Chuẩn bị bảng sản phẩm và đơn hàng với index, foreign key và số hàng tồn tại trước giống điều kiện mục tiêu.
4. Xác minh số lượng bản ghi hợp lệ và các trường hợp skip/filter theo profile.

### Giai đoạn 2: Tạo baseline

1. Cố định JDK, Spring Batch version, database, pool, CPU/RAM limits và logging level.
2. Chạy Job với chunk size 100, một thread; warm-up trước khi lấy mẫu.
3. Lặp nhiều lần, reset dữ liệu giữa các lượt ở ngoài vùng timer.
4. Ghi end-to-end duration, throughput theo read/write, peak heap, GC, DB connection/lock wait, commit/rollback.
5. Assert đúng dữ liệu đích sau mỗi lượt.

### Giai đoạn 3: Thử cấu hình

1. Lặp với chunk size 500, giữ một thread.
2. Lặp với chunk size 1.000, giữ một thread.
3. Chọn một chunk size phù hợp rồi thử hai hoặc bốn worker nếu reader/writer thread-safe và database có đủ năng lực.
4. So sánh profile `normal` và `month-end`; quan sát khác biệt do hot keys hoặc dữ liệu bị skew.
5. Kiểm tra xem cấu hình tăng tốc ở workload bình thường có trở nên tệ hơn ở peak workload không.

### Giai đoạn 4: Kiểm thử phục hồi

1. Cố ý gây lỗi database ở khoảng giữa Job.
2. Xác nhận `JobExecution` đầu tiên `FAILED`, metadata và checkpoint được lưu phù hợp.
3. Khắc phục lỗi rồi restart cùng identifying parameters.
4. Đo thời gian phục hồi và assert không có bản ghi trùng.
5. So sánh trade-off giữa commit interval, throughput ổn định và khối lượng xử lý lại khi lỗi.

**Câu hỏi tự đánh giá:**

- Vì sao hai CSV cùng 2 triệu dòng có thể tạo ra throughput khác nhau rất lớn?
- Tại sao chỉ tăng `thread count` chưa chắc cải thiện Job duration?
- Nếu launcher bất đồng bộ, đoạn code đo thời gian ngay sau `launchJob(...)` đang đo đại lượng gì?
- Vì sao `readCount` không phải lúc nào cũng bằng `writeCount`?
- Benchmark nhanh hơn 15% nhưng peak heap tăng gấp đôi có luôn đáng chọn?
- Nếu P95 được tính từ 5 lần chạy, kết luận về độ tin cậy của percentile đó có hạn chế gì?
- Vì sao không được dọn metadata giữa hai lần chạy trong benchmark restart?

## 21. Tài liệu tham khảo

- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và các khái niệm nền.
- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): đọc/xử lý/ghi theo chunk và transaction.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): quan sát các chỉ số và thực thi Batch.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Steps, split flows và partitioning.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): công cụ kiểm thử Job và Step.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): timers, counters và hệ thống metrics.
- [OpenJDK – Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): thu thập thông tin CPU, allocation, GC và profile Java.

