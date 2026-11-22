# Hiệu năng khi tải tăng và dữ liệu lệch phân bố

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một hệ thống chạy nhanh ở tải nhỏ vẫn có thể chậm hoặc mất ổn định khi số yêu cầu, kích thước dữ liệu và mức đồng thời tăng.
2. Phân biệt **thông lượng (throughput)**, **độ trễ (latency)**, **độ trễ đuôi (tail latency)**, **mức sử dụng tài nguyên (utilization)** và **điểm bão hòa (saturation)**.
3. Nhận diện **dữ liệu lệch phân bố (data skew)**, **hot key**, **hot partition**, **khóa có kích thước nhóm bất thường** và những truy vấn bị ảnh hưởng bởi phân bố dữ liệu.
4. Đọc biểu đồ tải, phân vị p95/p99, độ dài hàng đợi, CPU, bộ nhớ và số kết nối để tìm điểm nghẽn thay vì chỉ nhìn thời gian trung bình.
5. Lựa chọn cách đo, kiểm thử tải và phương án cải thiện phù hợp trong Java; giải thích những đánh đổi với tính đúng đắn, tính công bằng và khả năng bảo trì.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã nguồn được xem xét qua những thuộc tính quyết định mã **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Hiệu năng cũng góp phần vào chất lượng: một thao tác đúng nhưng mất quá nhiều thời gian, giữ quá nhiều tài nguyên hoặc chỉ chạy ổn với dữ liệu mẫu đều có thể khiến sản phẩm không đáp ứng nhu cầu.

**Ý chính:** Hiệu năng phải được đánh giá khi **tải và phân bố dữ liệu thay đổi**, không chỉ khi chạy một yêu cầu đơn lẻ trên tập dữ liệu đều và nhỏ. Tăng số máy, tăng số thread hay đổi một vòng lặp chưa chắc xử lý được điểm nghẽn thực sự.

## 1. Vì sao kết quả benchmark ở tải nhỏ có thể đánh lừa?

Hãy hình dung dịch vụ tìm kiếm đơn hàng:

- Trong môi trường phát triển có 1.000 đơn, một truy vấn trả kết quả trong 10 ms.
- Trong môi trường thật có 10 triệu đơn, truy vấn có thể phải quét nhiều dữ liệu nếu thiếu chỉ mục hoặc bộ lọc không chọn lọc.
- Khi 300 người dùng truy vấn đồng thời, connection pool bị sử dụng hết và yêu cầu mới phải đợi.
- Một khách hàng lớn sở hữu 40% số đơn, trong khi đa số khách có vài đơn; truy vấn theo khách hàng lớn xử lý lượng dữ liệu khác biệt hoàn toàn.
- Khi có một đợt nhập dữ liệu hoặc chương trình khuyến mại, lưu lượng có thể dồn vào cùng một mã sản phẩm, một khóa cache hoặc một partition.

Những thay đổi trên không nhất thiết xuất hiện trong một unit test với ba đơn hàng hay một microbenchmark gọi một hàm 100 lần.

Hiệu năng có ít nhất **ba chiều phải quan sát cùng nhau**:

| Chiều | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kích thước đầu vào** | Một thao tác tốn gì khi số bản ghi hoặc kích thước payload tăng? | Truy vấn 10 nghìn hay 10 triệu bản ghi |
| **Mức tải và đồng thời** | Điều gì xảy ra khi nhiều thao tác cần tài nguyên cùng lúc? | 10 hay 500 yêu cầu đồng thời |
| **Phân bố dữ liệu và công việc** | Có những khóa, nhóm hoặc truy vấn nặng vượt trội số còn lại không? | Một tenant chiếm phần lớn traffic |

Đo cả ba mới giúp tránh kết luận quá sớm “hệ thống đã nhanh” chỉ vì kết quả trung bình trên dữ liệu thử nhỏ.

## 2. Những chỉ số cần hiểu đúng

### 2.1. Throughput: lượng công việc hoàn thành

**Thông lượng** là số công việc hoàn tất trên một đơn vị thời gian, chẳng hạn **request/giây**, **bản ghi/giây** hoặc **đơn hàng/phút**.

Thông lượng phải đi cùng **định nghĩa công việc**: một request đọc dữ liệu cache khác xa một request tổng hợp báo cáo lớn. Một dịch vụ có thể xử lý 1.000 request/giây ở bài test chỉ đọc cache nhưng chỉ xử lý được 100 request/giây ở kịch bản ghi nhiều dữ liệu.

Ngoài request đến, cần quan sát **request hoàn tất** và **tỷ lệ lỗi**. Việc chấp nhận được nhiều request vào queue không đồng nghĩa hệ thống đang xử lý được nhiều request thành công.

### 2.2. Latency: thời gian hoàn tất một công việc

**Độ trễ** thường được đo từ khi bắt đầu một hoạt động đến khi có kết quả theo hợp đồng. Với API, cần phân biệt:

- Thời gian client quan sát, gồm truyền mạng và các tầng trung gian.
- Thời gian request ở service, gồm đợi queue, gọi phụ thuộc và xử lý nội bộ.
- Thời gian riêng từng đoạn như truy vấn DB, khóa đồng bộ, serialization hoặc cache.

Một tối ưu làm phần tính toán giảm từ 8 ms xuống 4 ms có thể không cải thiện đáng kể trải nghiệm nếu request còn phải đợi database 300 ms. Để biết nên sửa ở đâu, phải **đo và chia nhỏ thời gian**.

### 2.3. Mean, median, p95 và p99

Nếu một trăm request gồm 99 request mất 10 ms và một request mất 1.000 ms:

- **Trung bình** = (99 × 10 + 1 × 1.000) / 100 = **19,9 ms**.
- **Trung vị** (p50) = **10 ms**.
- Có **một request rất chậm**, dù trung bình nhìn vẫn khá nhỏ.

**p95** và **p99** là các phân vị: theo một quy ước tính cụ thể, p99 gần giá trị mà khoảng 99% quan sát không vượt quá. Các thư viện/biểu đồ có thể dùng cách nội suy và cửa sổ tổng hợp khác nhau nên con số chính xác ở mẫu nhỏ không nhất thiết giống nhau.

Độ trễ đuôi quan trọng vì người dùng vẫn phải trải qua những request chậm, đặc biệt khi một trang gọi nhiều dịch vụ. Nếu một thao tác phải chờ tất cả các lời gọi song song, xác suất gặp ít nhất một nhánh chậm tăng khi số nhánh tăng, trong giả định độc lập phù hợp. Trong thực tế các nhánh thường **có tương quan**, ví dụ cùng dùng database hoặc cùng chịu một sự cố mạng.

### 2.4. Utilization và saturation

**Mức sử dụng** mô tả phần năng lực tài nguyên đang bận: CPU, worker thread, connection, bộ nhớ hoặc I/O.

**Bão hòa** xảy ra khi nhu cầu đến gần/vượt khả năng xử lý, làm queue kéo dài, độ trễ tăng hoặc lỗi/từ chối xuất hiện. CPU chưa đạt 100% không chứng minh hệ thống còn dư năng lực: connection pool có thể đầy, các thread đang đợi mạng, một lock bị tranh chấp hoặc một partition đơn lẻ đã bão hòa.

Ví dụ: một pool chỉ có 20 kết nối DB. Dù CPU ứng dụng đang ở 30%, 100 request đồng thời cần kết nối có thể khiến nhiều request chờ lấy connection. **Đo đúng tài nguyên bị tranh chấp** quan trọng hơn chỉ nhìn CPU.

### 2.5. Các chỉ số nên đi cùng nhau

| Chỉ số | Cho biết | Dễ hiểu sai khi chỉ nhìn riêng |
| --- | --- | --- |
| Request hoàn tất/giây | Năng lực phục vụ thực | Không cho biết tỷ lệ thành công hoặc độ trễ |
| p50/p95/p99 | Trải nghiệm đa số và đuôi chậm | Phụ thuộc khoảng thời gian, mẫu và nhóm request |
| Số yêu cầu đang xử lý | Mức concurrency | Có thể tăng do chờ I/O, không chỉ do tính toán |
| Queue depth và queue wait | Mức công việc bị tích tụ | Queue lớn không tạo thêm công suất |
| Connection pool active/wait | Cạnh tranh kết nối | Cần xét cả độ trễ truy vấn và thời gian giữ connection |
| CPU, GC, heap, phân bổ bộ nhớ | Áp lực tài nguyên JVM | Không phải mọi chậm trễ đều do JVM |
| Lock contention | Chờ khóa hoặc cạnh tranh dữ liệu | Có thể chỉ xuất hiện với một hot key |
| Lỗi, timeout, từ chối | Độ tin cậy khi tải lớn | Throughput cao có thể đạt được bằng cách trả lỗi nhanh |
| Tỷ trọng tải theo key/tenant/partition | Mức lệch phân bố | Giá trị trung bình trên toàn cụm che giấu điểm nóng |

## 3. Khi tải tăng, độ trễ thường không tăng tuyến tính

Một dịch vụ có năng lực xử lý hữu hạn. Khi tốc độ request đến thấp hơn đáng kể khả năng phục vụ, hầu hết request bắt đầu xử lý ngay. Khi tải tiến gần giới hạn, **thời gian chờ** thường tăng nhanh và biến động lớn hơn.

Mô hình khái niệm:

~~~mermaid
flowchart LR
    A[Yêu cầu đến] --> B[Queue giới hạn]
    B --> C[Worker hoặc connection pool]
    C --> D[Database / dịch vụ khác]
    D --> E[Phản hồi]
    F[Tải tăng] -.-> B
    G[Phụ thuộc chậm] -.-> C
~~~

Nếu công việc đến nhanh hơn công việc hoàn tất trong thời gian dài, backlog tiếp tục tăng cho đến khi hệ thống giới hạn, từ chối hoặc cạn tài nguyên. Không có giải pháp nào khiến một hàng đợi vô hạn tự tạo ra năng lực xử lý.

### 3.1. Định luật Little và điều kiện sử dụng

Với một hệ thống ở **trạng thái ổn định**, định luật Little liên hệ:

\[
L = \lambda \times W
\]

Trong đó:
- \(L\): số công việc trung bình trong hệ thống;
- \(\lambda\): tốc độ hoàn tất trung bình của công việc ở trạng thái ổn định;
- \(W\): thời gian trung bình một công việc ở trong hệ thống, bao gồm cả chờ và xử lý.

Ví dụ minh họa, hệ thống hoàn tất 200 request/giây với thời gian trung bình 0,25 giây, số request trong hệ thống trung bình xấp xỉ **50**. Nếu thời gian tăng thành 1 giây nhưng tốc độ hoàn tất vẫn giữ được 200 request/giây, số request đang chờ/xử lý trung bình xấp xỉ **200**.

Không được áp dụng phép tính một cách máy móc trong giai đoạn queue đang tăng không ổn định. Khi tải đến vượt năng lực hoàn tất, các giả định dùng để suy từ ba đại lượng ổn định không còn đáp ứng.

### 3.2. Tăng concurrency không đồng nghĩa tăng throughput vô hạn

Thêm thread có thể tăng số request chạy song song khi hệ thống đang chưa dùng hết CPU hoặc tài nguyên I/O. Nhưng sau một ngưỡng:

- CPU phải chuyển ngữ cảnh nhiều hơn.
- Thread/connection cạnh tranh lock hoặc cùng một bảng dữ liệu.
- GC chịu thêm áp lực từ object tồn tại lâu.
- Database hoặc dịch vụ ngoài đạt quota/tốc độ tối đa.
- Tail latency tăng, khiến các request giữ tài nguyên lâu hơn.

Vì vậy, số thread, connection và concurrency nên được lựa chọn bằng **load test** và giới hạn của phụ thuộc, không theo công thức “càng nhiều càng nhanh”.

### 3.3. Deadline và từ chối có kiểm soát

Khi service đã quá tải, nhận thêm mọi request và để chúng chờ quá deadline có thể tạo lãng phí. **Bounded queue**, **concurrency limit**, **backpressure** và **load shedding** giúp hệ thống không nhận vượt khả năng.

Tuy nhiên, từ chối là một phần của hợp đồng vận hành: client phải biết request **chưa được chấp nhận**, không được báo thành công giả. Với công việc nền quan trọng cần bảo đảm xử lý, có thể cần hàng đợi bền vững và cơ chế giao nhận khác với queue RAM.

## 4. Dữ liệu lệch phân bố là gì?

**Data skew** xảy ra khi dữ liệu hoặc công việc không được phân bổ gần đều như mô hình thiết kế đã giả định. Một số khóa, nhóm, phân vùng hay truy vấn tập trung phần lớn bản ghi và chi phí.

Ví dụ, một bảng có một triệu đơn hàng:
- 90% khách hàng có dưới 10 đơn.
- Một khách hàng doanh nghiệp có 300.000 đơn.
- Những khách còn lại chia sẻ phần dữ liệu khác.

Một truy vấn theo **customerId** có thể rất nhanh cho khách hàng bình thường nhưng chậm đối với khách lớn nếu ứng dụng trả toàn bộ đơn hoặc phải tính tổng mà không giới hạn. Chỉ lấy thời gian trung bình trên các khách nhỏ sẽ bỏ sót vấn đề.

**Skew không chỉ là số lượng bản ghi.** Một số bản ghi có payload rất lớn; một loại request phải gọi thêm dịch vụ ngoài; một khách hàng có 1.000 request nhẹ, người khác có 50 request rất nặng. Phân bố **chi phí thực thi** có thể lệch khác phân bố số request.

### 4.1. Những kiểu skew thường gặp

| Kiểu lệch | Biểu hiện | Hậu quả |
| --- | --- | --- |
| **Hot key** | Một khóa nhận phần lớn truy vấn/cập nhật | Lock contention, cache stampede, một partition quá tải |
| **Hot partition/shard** | Dữ liệu hoặc request tập trung vào một phân vùng | Một node nghẽn dù toàn cụm còn tài nguyên |
| **Nhóm có cardinality lớn** | Một customer/category có rất nhiều bản ghi | Group by, join hoặc truy vấn theo khóa rất nặng |
| **Bản ghi kích thước bất thường** | Một số payload lớn hơn nhiều so với bình thường | Tăng bộ nhớ, băng thông, serialization và GC |
| **Skew do quan hệ join** | Một khóa xuất hiện rất nhiều ở cả hai phía join | Số dòng kết quả có thể phình lớn, tràn bộ nhớ |
| **Skew theo thời gian** | Tải dồn vào giờ cao điểm hoặc cùng thời khắc | Queue tăng đột ngột, thundering herd |
| **Skew theo tenant** | Một khách hàng dùng nhiều tài nguyên hơn đa số | Người dùng nhỏ bị ảnh hưởng bởi “noisy neighbor” |
| **Skew theo loại thao tác** | Một số request tốn CPU/I/O gấp nhiều lần | Số request/giây không còn đại diện cho chi phí |

Một phân phối thường được gọi là **long-tailed** hoặc **heavy-tailed** khi có một số giá trị cực lớn so với phần lớn còn lại; trong các hệ thống có độ phổ biến theo hạng, đôi khi gặp phân bố gần Zipf. Không nên mặc định dữ liệu thật luôn tuân theo một phân phối toán học cụ thể; hãy **đo dữ liệu và tải của hệ thống**.

## 5. Ví dụ: số request không phản ánh toàn bộ lượng việc

Giả sử API xử lý ba tenant trong một cửa sổ thời gian:

| Tenant | Số request | Chi phí trung bình ước lượng mỗi request | Tổng đơn vị công việc ước lượng |
| --- | ---: | ---: | ---: |
| A | 700 | 3 | 2.100 |
| B | 150 | 1 | 150 |
| C | 150 | 1 | 150 |
| **Tổng** | **1.000** | — | **2.400** |

Tenant A chiếm **70% số request** nhưng chiếm **87,5% đơn vị công việc ước lượng**. Nếu hệ thống chia đều request mà bỏ qua độ nặng, có thể vẫn không cân bằng tài nguyên.

Đơn vị công việc ở đây là một **ước lượng có trọng số**, không phải kết quả đo CPU chính xác. Trong thực tế, trọng số có thể được suy từ thời gian CPU, số bản ghi duyệt, kích thước payload, chi phí DB hoặc metric theo loại request. Không nên cộng trực tiếp những đại lượng có đơn vị khác nhau mà không có mô hình rõ ràng.

### 5.1. Code Java 17 để tóm tắt mức lệch

Ví dụ dưới đây không tối ưu hệ thống tự động; nó minh họa cách **đọc phân bố tải** thay vì chỉ nhìn tổng request.

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class WorkloadSkewAnalyzer {

    // estimatedCostPerRequest là đơn vị công việc tương đối,
    // không được giả định là mili giây hoặc CPU time thực đo.
    record Sample(
            String key,
            long requests,
            long estimatedCostPerRequest) {
        Sample {
            Objects.requireNonNull(key, "key");
            if (key.isBlank()
                    || requests <= 0
                    || estimatedCostPerRequest <= 0) {
                throw new IllegalArgumentException("invalid sample");
            }
        }
    }

    record Summary(
            long totalRequests,
            long totalWork,
            String hottestKey,
            long hottestWork) {

        double hottestWorkShare() {
            return (double) hottestWork / totalWork;
        }
    }

    static Summary analyze(List<Sample> samples) {
        Objects.requireNonNull(samples, "samples");
        if (samples.isEmpty()) {
            throw new IllegalArgumentException("empty sample set");
        }

        Map<String, Long> workByKey = new HashMap<>();
        long totalRequests = 0;
        long totalWork = 0;

        for (Sample sample : samples) {
            Objects.requireNonNull(sample, "sample");
            long work = Math.multiplyExact(
                    sample.requests(),
                    sample.estimatedCostPerRequest());

            totalRequests = Math.addExact(
                    totalRequests, sample.requests());
            totalWork = Math.addExact(totalWork, work);
            workByKey.merge(
                    sample.key(),
                    work,
                    (left, right) -> Math.addExact(left, right));
        }

        String hottestKey = null;
        long hottestWork = 0;
        for (var entry : workByKey.entrySet()) {
            if (entry.getValue() > hottestWork) {
                hottestKey = entry.getKey();
                hottestWork = entry.getValue();
            }
        }

        return new Summary(
                totalRequests, totalWork, hottestKey, hottestWork);
    }
}
~~~

Với bộ mẫu minh họa:

~~~java
var summary = WorkloadSkewAnalyzer.analyze(List.of(
        new WorkloadSkewAnalyzer.Sample("A", 700, 3),
        new WorkloadSkewAnalyzer.Sample("B", 150, 1),
        new WorkloadSkewAnalyzer.Sample("C", 150, 1)));

System.out.println(summary.totalRequests());   // 1000
System.out.println(summary.totalWork());       // 2400
System.out.println(summary.hottestKey());      // A
System.out.println(summary.hottestWorkShare()); // 0.875
~~~

**Điểm quan trọng:** Giả sử mỗi record đại diện một tenant trong một cửa sổ thời gian. Đoạn mã cho phép nhiều sample cùng key và sẽ cộng tổng công việc của chúng. **Math.multiplyExact** và **Math.addExact** báo lỗi nếu số lượng ước lượng vượt khả năng của kiểu long thay vì âm thầm tràn số.

Trong sản phẩm thật, thuật toán gom toàn bộ key vào **HashMap** sẽ dùng bộ nhớ tỷ lệ với số key duy nhất. Với cardinality cực lớn, có thể cần tổng hợp phía nguồn, sampling, top-k hoặc thuật toán streaming có sai số được kiểm soát. Dữ liệu định danh tenant cũng cần bảo vệ khi đưa vào log, dashboard hoặc báo cáo.

### 5.2. Unit test bảo vệ phân tích dữ liệu

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class WorkloadSkewAnalyzerTest {

    @Test
    void identifiesDominantWorkRatherThanOnlyRequestCount() {
        var summary = WorkloadSkewAnalyzer.analyze(List.of(
                new WorkloadSkewAnalyzer.Sample("A", 700, 3),
                new WorkloadSkewAnalyzer.Sample("B", 150, 1),
                new WorkloadSkewAnalyzer.Sample("C", 150, 1)));

        assertEquals(1000L, summary.totalRequests());
        assertEquals(2400L, summary.totalWork());
        assertEquals("A", summary.hottestKey());
        assertEquals(0.875, summary.hottestWorkShare(), 1e-9);
    }

    @Test
    void combinesMultipleSamplesOfTheSameKey() {
        var summary = WorkloadSkewAnalyzer.analyze(List.of(
                new WorkloadSkewAnalyzer.Sample("A", 2, 10),
                new WorkloadSkewAnalyzer.Sample("A", 3, 10),
                new WorkloadSkewAnalyzer.Sample("B", 4, 1)));

        assertEquals(5L + 4L, summary.totalRequests());
        assertEquals(54L, summary.totalWork());
        assertEquals("A", summary.hottestKey());
        assertEquals(50L, summary.hottestWork());
    }

    @Test
    void rejectsInvalidWorkEstimate() {
        assertThrows(IllegalArgumentException.class,
                () -> new WorkloadSkewAnalyzer.Sample("A", 0, 1));
    }
}
~~~

Test dùng **JUnit Jupiter (JUnit 5)** và kiểm tra cả phép cộng cùng key. Nó **không chứng minh** rằng ước lượng chi phí tương đối tương ứng chính xác với CPU hoặc độ trễ trong production. Việc thiết lập trọng số cần quan sát workload thực tế.

### 5.3. Từ số liệu tới hành động

Nếu tenant A thực sự chiếm phần lớn tải, nhóm cần hỏi tiếp:

- A có nhiều request nhẹ hay ít request nặng?
- A bị dồn vào một partition vì cách tạo khóa không?
- Có thể cache phần đọc thường xuyên và có chính sách vô hiệu hóa rõ ràng không?
- Có thể phân trang/batch hoặc tách xử lý nền không?
- Hành vi theo key có đòi hỏi thứ tự, transaction hoặc tính chính xác tức thời không?
- Có cần giới hạn concurrency theo tenant để bảo vệ người dùng khác không?

Chỉ kết luận “A là hot key” chưa chỉ ra cách sửa. Một phương án tối ưu phải phù hợp với **ngữ nghĩa nghiệp vụ** và **ràng buộc dữ liệu**.

## 6. Hot partition: vì sao thêm máy vẫn chưa chắc giải quyết được?

Giả sử dữ liệu được chia partition theo **hash(customerId) % N**. Mỗi customer luôn rơi vào cùng một partition để giữ dữ liệu liên quan gần nhau.

Nếu một khách doanh nghiệp chiếm 40% yêu cầu, toàn bộ tải của khách đó có thể vẫn đi tới **một partition**, dù hệ thống tăng từ 4 node lên 8 node. Những node khác ít bận hơn không làm partition nóng tự chạy nhanh hơn.

~~~mermaid
flowchart TD
    A[Request theo customerId] --> H[Hash partition key]
    H --> P1[Partition 1 - rất nóng]
    H --> P2[Partition 2]
    H --> P3[Partition 3]
    H --> P4[Partition 4]
    K[Khách hàng lớn A] -.-> P1
~~~

**Hash tốt giúp phân tán nhiều key**, nhưng không thể chia một key đơn lẻ thành nhiều key nếu mọi yêu cầu của nó phải cùng đích. Muốn xử lý hot key, có thể cần đổi mô hình công việc, cách đặt khóa hoặc chính sách phục vụ.

### Các lựa chọn xử lý và đánh đổi

| Giải pháp | Khi có thể phù hợp | Rủi ro hoặc điều kiện cần xem xét |
| --- | --- | --- |
| **Cache đọc** | Nhiều request đọc cùng dữ liệu ổn định | Dữ liệu cũ, cache stampede, invalidation |
| **Phân trang / giới hạn kết quả** | Một key có số lượng bản ghi rất lớn | Thay hợp đồng trả dữ liệu; phải có thứ tự phân trang ổn định |
| **Tách batch hoặc tác vụ nền** | Một request phải quét/xử lý lượng dữ liệu lớn | Cần trạng thái tiến trình, retry, idempotency và kết quả cuối |
| **Giới hạn concurrency theo key/tenant** | Muốn ngăn một khách chiếm hết tài nguyên | Có thể từ chối/chờ nhiều request của khách nóng; cần chính sách công bằng |
| **Sharding một key thành nhiều subkey** | Công việc có thể xử lý song song độc lập | Khó giữ thứ tự, tổng hợp và giao dịch nguyên tử; có chi phí fan-out |
| **Đổi partition key** | Key hiện tại có phân bố quá lệch | Migration, truy vấn lại, tương thích và dữ liệu liên quan |
| **Tiền tổng hợp (pre-aggregation)** | Nhiều lần đọc cùng kết quả tổng hợp | Đồng bộ bản cập nhật, tính mới của dữ liệu, sửa sai khi replay |
| **Đọc bản sao / replica** | Tải chủ yếu là đọc và hệ lưu trữ hỗ trợ | Độ trễ đồng bộ, dữ liệu có thể stale; không giúp mọi loại ghi |

**Không dùng salted key hoặc subkey một cách máy móc.** Nếu tất cả giao dịch trên một tài khoản phải giữ thứ tự tuyệt đối và kiểm tra số dư nguyên tử, chia chúng ra nhiều partition có thể phá hợp đồng. Cách điều chỉnh partition phải bắt đầu từ yêu cầu nhất quán và khả năng kết hợp kết quả.

## 7. Skew cũng xuất hiện trong database và truy vấn

### 7.1. Một cột có nhiều giá trị lặp

Giả sử bảng giao dịch có cột **status**, phần lớn bản ghi là **COMPLETED**, chỉ 0,1% là **PENDING**. Truy vấn lọc theo trạng thái PENDING có thể chọn rất ít dòng, còn COMPLETED chọn gần như toàn bảng.

Nếu chỉ đo một giá trị status hiếm, nhóm có thể nghĩ chỉ mục luôn hiệu quả. Với giá trị phổ biến, kế hoạch truy vấn và chi phí I/O có thể khác.

**Selectivity** là mức bộ lọc thu hẹp dữ liệu. Chỉ mục có thể hữu ích hoặc không tùy phân bố, thống kê, điều kiện truy vấn và khả năng dùng index của hệ quản trị. Không thể khẳng định “cứ có index thì truy vấn nhanh” mà không xem **execution plan** và dữ liệu thực.

### 7.2. Bản ghi cùng khóa ở hai phía join

Nếu bảng A có 1.000 dòng cùng khóa **K** và bảng B có 500 dòng cùng khóa **K**, một join theo đúng khóa đó có thể tạo **1.000 × 500 = 500.000** cặp dòng chỉ cho K, nếu không có điều kiện khác thu hẹp.

Hậu quả có thể là:
- Kết quả lớn hơn nhiều lần so với dự kiến.
- Tăng CPU, bộ nhớ trung gian, truyền dữ liệu.
- Phép tổng hợp phía sau bị nhân đôi giá trị nghiệp vụ.
- Một partition xử lý join mất lâu hơn các partition khác.

Cần kiểm tra **cardinality và tính duy nhất của khóa**, không chỉ cú pháp SQL. Giải pháp có thể là sửa khóa join, giới hạn phiên bản bản ghi, lọc trước khi join hoặc thiết kế bước tổng hợp phù hợp. Nếu quan hệ nhiều-nhiều là yêu cầu nghiệp vụ thật, không thể “loại trùng” tùy tiện mà không làm sai kết quả.

### 7.3. Truy vấn theo một tenant rất lớn

Nếu một API trả toàn bộ 300.000 đơn của một tenant dưới dạng một JSON response, vấn đề không chỉ nằm ở SQL. Nó còn liên quan tới:
- Số hàng phải đọc và giữ trong bộ nhớ.
- Cách ánh xạ ORM, có gây **N+1 query** không.
- Serialization, kích thước response và băng thông.
- Timeout phía client và gateway.
- Khả năng người dùng có thật sự cần xem toàn bộ dữ liệu cùng lúc không.

Trong trường hợp đó, **phân trang theo khóa ổn định, lọc theo thời gian, API xuất dữ liệu nền** có thể mang lại lợi ích lớn hơn một micro-optimization trong Java.

### 7.4. Xem execution plan trên dữ liệu đại diện

Khi tối ưu database, nên quan sát:
- Số hàng dự tính và số hàng thực tế ở các bước truy vấn.
- Thời gian từng bước, số hàng được lọc hoặc join.
- Index scan, full scan, sort, hash join và spill ra disk, tùy DBMS.
- Phân bố giá trị cột và thống kê có còn phù hợp không.
- Số lần truy vấn do ứng dụng phát ra.

Cú pháp và chỉ số cụ thể khác nhau giữa PostgreSQL, MySQL và các DBMS khác. **Không đưa kết luận từ execution plan của một tập dữ liệu nhỏ** sang tập có phân bố lệch hàng triệu bản ghi mà không kiểm chứng.

## 8. Tail latency: khi số ít yêu cầu chậm chi phối trải nghiệm

Một vấn đề đặc biệt của hệ thống phân tán là một thao tác người dùng có thể gọi nhiều phụ thuộc:

~~~mermaid
flowchart TD
    A[API tổng hợp] --> B[Giá]
    A --> C[Tồn kho]
    A --> D[Khuyến mại]
    A --> E[Gợi ý]
    B --> F[Ghép kết quả]
    C --> F
    D --> F
    E --> F
~~~

Nếu API đợi tất cả nhánh, thời gian trả lời bị giới hạn bởi **nhánh chậm nhất** cộng chi phí kết hợp. Một phụ thuộc có p99 không tốt có thể ảnh hưởng đáng kể đến p99 của toàn luồng. Khi tất cả nhánh cùng chia sẻ một tài nguyên, các độ trễ có thể tăng **cùng lúc**, khiến giả định độc lập không còn phù hợp.

Những nguyên nhân thường gặp của tail latency:
- Một số payload hoặc nhóm dữ liệu lớn bất thường.
- Lỗi mạng ngắn, DNS, timeout, retry.
- GC pause hoặc áp lực bộ nhớ.
- Chờ lock, thread pool hoặc connection pool.
- Lưu lượng tăng đột biến tại một key.
- Cache miss hoặc truy vấn ít chọn lọc.
- Một instance hay shard chậm hơn phần còn lại.

### Tối ưu p99 khác tối ưu thời gian trung bình

Nếu p50 là 10 ms, p99 là 2.000 ms, tối ưu 2 ms trong code path nhanh có thể không giải quyết trải nghiệm chậm. Trước tiên cần phân tích **những request thuộc đuôi chậm có điểm chung gì**: key, tenant, loại endpoint, kích thước payload, phiên bản instance, trạng thái cache hoặc thời gian chờ phụ thuộc.

Không nên chỉ tính p99 chung cho tất cả endpoint. Nếu gom một API nhẹ với một API xuất báo cáo nặng, phân vị chung có thể che khuất vấn đề riêng. Nên nhóm theo **operation**, mức tải, loại dữ liệu và các thuộc tính có cardinality phù hợp, đồng thời tránh đưa ID người dùng duy nhất vào nhãn metric gây bùng nổ cardinality.

## 9. Các điểm nghẽn thường gặp trong JVM/Java

Phân bố tải lệch có thể khuếch đại những chi phí nhỏ trong mã Java:

| Khu vực | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| **Object allocation / GC** | Young GC nhiều, GC pause hoặc phân bổ bộ nhớ tăng theo tải | Allocation profile, kích thước object, vòng đời dữ liệu |
| **Lock contention** | Nhiều thread chờ một synchronized block hoặc lock | Thread dump, Java Flight Recorder, contention profile |
| **Thread pool** | Active threads chạm ngưỡng, queue tăng | Tách phần đợi I/O với phần CPU, giới hạn queue |
| **HTTP/DB connection pool** | Chờ lấy connection cao trong khi CPU rảnh | Pool metrics, thời gian giữ connection, giới hạn phụ thuộc |
| **Serialization** | Response lớn, CPU và bytes tăng | Kích thước payload, giới hạn trang, format và streaming |
| **Collections** | Bộ nhớ tăng theo số key hoặc số bản ghi | Data structure, cardinality, vòng đời Map/cache |
| **Hot key trong cache** | Nhiều request cùng tính lại khi cache hết hạn | Single-flight/coalescing, TTL jitter, giới hạn fan-out |
| **Blocking I/O** | Thread sống lâu nhưng ít CPU | Timeout, concurrency limit, cấu trúc async nếu phù hợp |
| **Tạo nhiều truy vấn nhỏ** | Số query tăng theo số dòng | N+1, batching, chọn dữ liệu trước khi ánh xạ |

### Chọn công cụ đo đúng câu hỏi

- **JDK Flight Recorder (JFR)** và **Java Mission Control** giúp quan sát phân bổ bộ nhớ, GC, lock, CPU và hoạt động JVM tùy cấu hình.
- **Thread dump** hỗ trợ phát hiện thread đang chờ lock hoặc I/O, nhưng cần xem nhiều mẫu và biết trạng thái không đồng nghĩa nguyên nhân cuối cùng.
- **Profiler** giúp xác định phần CPU hoặc allocation đáng kể.
- **Micrometer/OpenTelemetry** hoặc hệ metric/tracing tương tự có thể đo request, phụ thuộc và tài nguyên trong ứng dụng.
- **JMH** thích hợp cho microbenchmark đoạn Java nhỏ; nó không thay thế load test cả dịch vụ.

Khi điều tra, tránh chạy profiler quá nặng trực tiếp trong giờ cao điểm mà không đánh giá tác động. Cần sử dụng cấu hình đo và môi trường phù hợp.

## 10. Lựa chọn thuật toán và cấu trúc dữ liệu phải xét phân bố thật

Hai thuật toán có cùng độ phức tạp Big O vẫn có thể khác đáng kể về:
- Hằng số chi phí và cache locality.
- Phân bổ bộ nhớ.
- Kích thước đầu vào điển hình so với cực trị.
- Mức độ tương tranh.
- Độ chọn lọc dữ liệu và khóa trùng.
- Chi phí I/O bên ngoài.

Ví dụ, dùng **HashMap** để nhóm theo key có thời gian kỳ vọng tốt cho nhiều thao tác, nhưng cần bộ nhớ tỷ lệ với **số key khác nhau**. Nếu số key có thể tăng vô hạn theo dữ liệu người dùng, việc gom toàn bộ vào RAM có thể không phù hợp.

Nếu dùng **ConcurrentHashMap<String, LongAdder>** để đếm lượt xuất hiện từng key, thao tác tăng một bộ đếm nóng có thể hưởng lợi từ LongAdder trong một số tình huống cạnh tranh. Nhưng:
- LongAdder không tự giới hạn số key được tạo.
- **sum()** không phải snapshot nguyên tử với các cập nhật đồng thời.
- Việc đếm theo key không giải quyết một công việc cực nặng nằm sau key đó.
- Chỉ số kiểu counter có thể phù hợp cho thống kê, nhưng không nhất thiết phù hợp làm số dư hoặc trạng thái giao dịch cần tính nhất quán chặt.

**Không chọn cấu trúc dữ liệu chỉ dựa trên lời khuyên “nhanh hơn”.** Bảo vệ hợp đồng đúng đắn trước, sau đó đo trên workload có dữ liệu và phân bố đại diện.

## 11. Tăng tài nguyên hay giảm công việc?

Khi hệ thống chậm, nhóm thường nghĩ tới tăng instance, CPU hoặc kích thước pool. Có thể đúng nếu công việc **chia được** và điểm nghẽn là tài nguyên có thể bổ sung. Nhưng trước đó cần hỏi liệu ứng dụng đang làm **công việc không cần thiết** hay không.

Một số câu hỏi:

1. Có truy vấn lại cùng dữ liệu trong một request không?
2. Có trả toàn bộ danh sách trong khi UI chỉ hiển thị 20 bản ghi không?
3. Có tạo một object/SQL query cho từng dòng thay vì batch không?
4. Có gọi dịch vụ ngoài theo thứ tự khi các lời gọi độc lập có thể chạy song song không?
5. Có dùng cache cho dữ liệu đủ ổn định, với invalidation và TTL phù hợp không?
6. Có phải mọi request đều đọc một tập dữ liệu lớn để tính cùng một chỉ số không?
7. Có thể chuyển công việc nặng sang job bất đồng bộ với hợp đồng kết quả rõ ràng không?

Giảm lượng công việc mỗi request có thể cải thiện cả throughput lẫn độ trễ. Nhưng **giảm không đúng** có thể làm sai kết quả, ví dụ bỏ qua kiểm tra quyền để tiết kiệm thời gian hoặc trả dữ liệu cache đã lỗi thời ở nghiệp vụ cần nhất quán tức thời.

### Phân biệt scale up, scale out và tối ưu luồng

- **Scale up:** thêm CPU/RAM cho instance, hữu ích khi máy hiện tại bị giới hạn và phần mềm sử dụng được tài nguyên đó.
- **Scale out:** tăng instance/partition, hữu ích khi công việc có thể chia và hạ tầng chung chưa trở thành điểm nghẽn.
- **Giảm công việc:** tối ưu truy vấn, batching, caching, pre-aggregation, phân trang và giảm fan-out khi không cần thiết.
- **Điều tiết:** quota, concurrency limit hoặc ưu tiên công việc để tránh một nguồn tải chiếm hết năng lực.

Những lựa chọn này có thể kết hợp, nhưng mỗi lựa chọn giải quyết một loại vấn đề. Một hot partition không tự được chia nhỏ bằng cách thêm node; một truy vấn N+1 không trở nên tốt chỉ vì thêm RAM.

## 12. Cách kiểm thử khi tải tăng và dữ liệu lệch phân bố

Một bài load test hữu ích cần mô phỏng đúng **mức đến, độ đồng thời, kích thước và độ lệch dữ liệu**. Không chỉ tăng số request tới một endpoint với cùng payload giả.

### 12.1. Xác định mục tiêu trước khi chạy

Ví dụ giả định:
- Ở 200 request/giây, ít nhất 99,5% yêu cầu nghiệp vụ thành công.
- p95 nhỏ hơn 300 ms và p99 nhỏ hơn 1 giây cho endpoint tương tác.
- Không để queue chờ tăng liên tục trong giai đoạn tải ổn định.
- Tỷ lệ lỗi và số công việc bị từ chối không vượt ngân sách đã đặt.
- Không có một tenant chiếm toàn bộ connection pool khiến các tenant khác mất khả năng phục vụ.

Các con số trên **chỉ để minh họa**, không phải ngưỡng mặc định. SLO cần xuất phát từ trải nghiệm người dùng, ràng buộc sản phẩm và khả năng phụ thuộc.

### 12.2. Xây các tập dữ liệu thử

| Kịch bản | Phân bố dữ liệu | Mục tiêu |
| --- | --- | --- |
| **Uniform baseline** | Các key có tần suất gần đều | Kiểm tra trường hợp lý tưởng và năng lực nền |
| **Hot-key** | 1 key nhận 50–90% request theo kịch bản | Phát hiện lock/partition/cache contention |
| **Heavy tenant** | Một tenant có số bản ghi lớn hơn nhiều | Kiểm tra truy vấn, phân trang và bộ nhớ |
| **Large payload** | Một số request có dữ liệu rất lớn | Kiểm tra serialization, queue và giới hạn kích thước |
| **Burst** | Lưu lượng tăng mạnh trong thời gian ngắn | Kiểm tra autoscaling, queue, từ chối và thời gian phục hồi |
| **Soak/endurance** | Tải ổn định kéo dài | Phát hiện leak, tích tụ bộ nhớ hoặc suy giảm theo thời gian |
| **Mixed read/write** | Tỷ lệ đọc/ghi và key bị cập nhật giống thực tế | Kiểm tra contention, cache invalidation và DB |
| **Dependency slow/failure** | Một phụ thuộc chậm hoặc trả lỗi tạm thời | Kiểm tra timeout, retry budget, bulkhead và tail latency |

Cần xác định **seed** hoặc cách tái tạo tập dữ liệu để so sánh trước/sau. Một bộ dữ liệu “ngẫu nhiên” quá đều có thể làm biến mất hot key vốn là đặc điểm quan trọng của hệ thống.

### 12.3. Open-loop và closed-loop load generation

Hai kiểu tạo tải phổ biến cần phân biệt:

- **Closed-loop:** một client đợi request hoàn tất rồi mới gửi tiếp. Khi server chậm, tốc độ gửi request có thể tự giảm, khiến tải phát sinh không còn giống lượng request thực muốn đến.
- **Open-loop:** request được phát theo lịch hoặc tốc độ đến được xác định độc lập tương đối với thời gian phản hồi. Kiểu này giúp quan sát điều gì xảy ra khi khách hàng vẫn gửi yêu cầu dù service chậm.

Việc chọn mô hình phụ thuộc mục tiêu. Một bài test chỉ có số user đồng thời cố định có thể không phát hiện đầy đủ **saturation dưới tốc độ đến cao**. Đồng thời, công cụ tạo tải cũng có giới hạn CPU, socket và kết nối; nếu load generator nghẽn thì số liệu về server có thể bị sai.

Cần lưu ý **coordinated omission**: nếu quá trình đo không tính đúng những yêu cầu lẽ ra phải đến trong lúc server đang chậm, độ trễ đuôi có thể bị báo thấp hơn thực tế. Chọn công cụ và cách phát tải có thể phản ánh lịch request dự kiến khi cần đo hiện tượng này.

### 12.4. Warm-up và điều kiện chạy

Với Java, thời gian chạy đầu có thể khác giai đoạn ổn định do JIT compilation, class loading và cache. Ngược lại, cache được làm nóng quá mức với tập dữ liệu nhỏ có thể khiến bài test thiếu đại diện.

Nên mô tả:
- JVM và tham số heap/GC.
- Số instance, vCPU, RAM, connection/worker pool.
- Dữ liệu thử, số key, tỉ lệ key nóng, kích thước payload.
- Thời gian warm-up và đo.
- Tỷ lệ lỗi, retry, timeout và cách tính latency.
- Các yếu tố bên ngoài: DB, network, shared resource, quota.

Để so sánh hai phiên bản, giữ cấu hình và phân bố dữ liệu tương đương; tránh đồng thời thay nhiều biến rồi gán mọi cải thiện cho một đoạn code.

## 13. Phân tích kết quả: tìm nguyên nhân thay vì đổ lỗi cho “Java chậm”

Giả sử một bài test cho thấy:

| Tải đến | Request thành công/giây | p95 | p99 | Queue trung bình |
| --- | ---: | ---: | ---: | ---: |
| 50 req/s | 50 | 60 ms | 100 ms | 0 |
| 100 req/s | 100 | 90 ms | 160 ms | 1 |
| 150 req/s | 149 | 250 ms | 700 ms | 20 |
| 200 req/s | 152 | 1.800 ms | 4.500 ms | 300 |

Đây là **số liệu giả định** minh họa hành vi bão hòa. Khi tải đến tăng từ 150 lên 200 req/s, thông lượng hoàn tất không tăng tương ứng nhưng p95/p99 và queue tăng mạnh. Có thể hệ thống đã đến gần **năng lực phục vụ hiện tại**.

Chưa thể chỉ ra nguyên nhân bằng bảng này. Các giả thuyết cần kiểm chứng:

- DB query chậm theo dữ liệu hoặc pool kết nối đầy.
- Một tenant hoặc key nóng chiếm nhiều worker.
- Một lock trở thành điểm tranh chấp.
- CPU đạt giới hạn, hoặc GC tăng mạnh.
- Lời gọi ngoài có timeout quá dài khiến worker bị giữ.
- Một số request kích thước lớn làm p99 xấu đi.

### Quy trình điều tra thực dụng

1. **Khoanh thời điểm và operation** có p99/tỷ lệ lỗi tăng.
2. **Xác định đâu là chờ và đâu là xử lý**: queue wait, DB wait, network wait, CPU và GC.
3. **Chia dữ liệu thành nhóm**: tenant, loại endpoint, kích thước request, partition, hit/miss cache, lỗi phụ thuộc. Cân nhắc riêng tư và cardinality metric.
4. **Tìm tương quan**: chỉ một shard nóng, hay toàn bộ instance chậm như nhau?
5. **Đưa ra một giả thuyết có thể bác bỏ**: “Index thiếu khiến truy vấn tenant lớn quét quá nhiều hàng”, thay vì “SQL có vẻ chậm”.
6. **Đo lại sau một thay đổi có mục tiêu** với cùng cấu hình và workload.
7. **Giữ test đúng đắn và kiểm thử tải hồi quy** để tránh tối ưu bằng cách bỏ chức năng.

Không nhất thiết phải xây hệ thống đo hoàn hảo trước khi sửa một lỗi đã rõ. Nhưng khi nguyên nhân chưa rõ, **đo đúng chỗ** thường tiết kiệm thời gian hơn nhiều vòng refactor phỏng đoán.

## 14. Những đánh đổi khó tránh

### 14.1. Cache giúp nhanh nhưng không miễn phí

Cache hữu ích với dữ liệu đọc nhiều và ít đổi. Nhưng tăng cache có thể:
- Làm người dùng nhận dữ liệu cũ.
- Tốn bộ nhớ, tăng GC hoặc tạo hiệu ứng eviction.
- Gây **cache stampede** nếu nhiều request cùng tính lại một giá trị khi TTL hết.
- Tạo hot key trên chính cache hoặc tại cơ chế khóa chống tính lại.

Có thể dùng TTL jitter, request coalescing/single-flight, prewarming hoặc phân cấp cache theo yêu cầu. Những giải pháp này cũng phải được kiểm tra về độ mới của dữ liệu và khả năng phục hồi sau lỗi.

### 14.2. Batch làm giảm overhead nhưng tăng độ trễ chờ

Gộp 100 bản ghi vào một batch có thể giảm số network round trip và số transaction. Nhưng:
- Bản ghi đầu tiên phải đợi đủ batch hoặc đến timeout flush.
- Một batch lỗi có thể cần tách, retry hoặc xử lý bản ghi riêng.
- Batch lớn có thể gây memory spike và lock lâu.
- Với dữ liệu skew, một batch chứa toàn job nặng có thể vượt deadline.

Cần chọn kích thước batch và chính sách flush dựa trên throughput, p99, bộ nhớ và hợp đồng độ trễ.

### 14.3. Parallelism có thể phá thứ tự hoặc tăng tranh chấp

Chạy song song những phép tính độc lập thường hữu ích. Nhưng nếu nhiều tác vụ cập nhật cùng tài khoản hoặc cùng inventory item, chúng có thể cạnh tranh lock; bỏ ràng buộc để tăng throughput có nguy cơ sai số liệu.

Không được chia nhỏ một hot key chỉ vì mục tiêu cân bằng tải nếu nghiệp vụ đòi thứ tự tuyệt đối hoặc transaction nguyên tử. Muốn scale, có thể cần thay đổi mô hình nghiệp vụ hoặc chọn một biện pháp bảo vệ khác.

### 14.4. Fairness và throughput

Một tenant rất lớn có thể xử lý hiệu quả khi dùng toàn bộ tài nguyên rảnh. Giới hạn cứng từng tenant có thể cải thiện tính công bằng nhưng làm giảm tận dụng công suất khi các tenant khác nhàn rỗi.

Có thể cân nhắc quota động, weighted fair queuing, giới hạn concurrency theo tenant hoặc ưu tiên loại công việc. Mục tiêu phải được diễn đạt rõ: **bảo vệ người dùng khác, đáp ứng SLO hay tối đa tổng công việc?** Các mục tiêu này có thể xung đột.

### 14.5. Tiền tổng hợp và tính nhất quán

Duy trì sẵn tổng doanh thu theo ngày giúp báo cáo nhanh hơn, nhưng cần cập nhật khi giao dịch bị hủy, hoàn tiền hoặc dữ liệu đến trễ. Nếu logic bù trừ sai, kết quả “nhanh” nhưng không đúng. Phải xác định khi nào kết quả cập nhật, cách đối soát với dữ liệu gốc và cơ chế tính lại khi cần.

## 15. Một checklist review mã nguồn trước khi tối ưu

Khi review một pull request có tuyên bố “cải thiện hiệu năng”, hãy tự hỏi:

1. **Vấn đề được đo ở đâu?** p95/p99, throughput, CPU, allocation, DB hay tài nguyên khác?
2. **Tải và dữ liệu đo có đại diện không?** Có key nóng, tenant lớn, payload bất thường và burst không?
3. **Nút thắt có nằm ở đoạn code được sửa không?** Có profiler, trace hoặc execution plan hỗ trợ không?
4. **Hợp đồng có giữ nguyên không?** Đầu vào/đầu ra, thứ tự, thời điểm, độ chính xác, lỗi, quyền và tác dụng phụ?
5. **Tối ưu có tăng chi phí bảo trì không?** Có thêm cache invalidation, trạng thái ngầm, cấu hình hoặc concurrency khó hiểu?
6. **Có biện pháp nào giảm lượng việc trước khi tăng tài nguyên?** Pagination, batching, cải thiện truy vấn hoặc bỏ thao tác lặp?
7. **Điểm nghẽn mới là gì?** Sau khi tối ưu một bước, DB, connection pool hoặc network có trở thành giới hạn?
8. **Khi tải vượt năng lực, hệ thống phản ứng thế nào?** Chờ vô hạn, từ chối có kiểm soát, hay có cơ chế điều tiết?
9. **Có khả năng đo lại và rollback không?** Cấu hình/feature flag, telemetry và test hồi quy phù hợp?
10. **Kết quả có đáng kể ở quy mô vận hành thực tế không?** Một microbenchmark nhanh hơn 20% có làm p99 của endpoint tốt hơn không?

Một tối ưu đáng tin không chỉ đi kèm một con số “nhanh hơn”, mà còn có **bối cảnh tải, phương pháp đo, kiểm chứng tính đúng đắn và phạm vi tác động**.

## 16. Tình huống thực hành: báo cáo theo khách hàng lớn

Một hệ thống quản lý đơn hàng có 500.000 khách hàng. Phần lớn khách có dưới 20 đơn; 20 khách doanh nghiệp có hơn 100.000 đơn mỗi người. API **GET /customers/{id}/orders** trả toàn bộ danh sách đơn trong một lần gọi.

Nhóm nhận thấy:

- p50 toàn API vẫn thấp, nhưng p99 vào giờ cao điểm tăng đến vài giây.
- Database CPU không luôn cao; đôi khi JVM dùng nhiều bộ nhớ để ánh xạ danh sách lớn.
- Các request của khách doanh nghiệp tập trung ở một số partition.
- Nhóm thử tăng kích thước thread pool gấp đôi nhưng p99 không giảm bền vững.
- Một chương trình nền đồng thời tổng hợp đơn hàng theo customerId, cũng gặp các key lớn.

### Câu hỏi

1. Những dấu hiệu nào cho thấy workload bị **skew**, không chỉ thiếu CPU?
2. Tại sao tăng thread pool có thể làm tình hình tệ hơn?
3. Bạn sẽ đo thêm những thông tin gì để tách nguyên nhân DB, bộ nhớ, serialization và queue?
4. Những thay đổi nào có thể giảm công việc mỗi request mà vẫn bảo vệ nhu cầu người dùng?
5. Nếu công việc tổng hợp phải giữ đúng tất cả giao dịch, có nên chia một customerId thành nhiều subkey ngay không?
6. Bạn sẽ thiết kế load test ra sao để chứng minh cải thiện cho cả khách thường và khách lớn?

### Hướng phân tích

**Skew:** Có ít khách với tập dữ liệu khổng lồ, một số partition nóng và p99 lớn hơn nhiều so với median. Cần xem phân bố số đơn/khách, thời gian truy vấn theo nhóm khách và số bản ghi thực được trả.

**Thread pool:** Tăng số thread không làm database hoặc bộ nhớ có thêm năng lực thực. Nó có thể tăng số request nặng chạy đồng thời, khiến GC, connection contention và queue tiếp tục xấu.

**Đo:** Dùng trace có kích thước tập kết quả, số hàng DB trả, thời gian truy vấn, pool wait, allocation, GC và thời gian serialization. Tách số liệu theo tenant size hoặc bucket, tránh xem một biểu đồ p99 toàn hệ thống.

**Giảm công việc:** Phân trang có thứ tự ổn định, lọc theo thời gian, truy vấn được index theo nhu cầu, API xuất dữ liệu bất đồng bộ và các bảng tổng hợp phù hợp. Việc đổi API phải xét client đang phụ thuộc vào hành vi cũ.

**Chia key:** Chỉ làm khi có thể bảo vệ thứ tự, transaction và cách tổng hợp kết quả. Đối với công việc đọc hoặc tính tổng có thể chia độc lập, fan-out rồi reduce có thể có ích; đối với cập nhật cần tuần tự, không được bỏ bảo đảm để chạy nhanh.

**Kiểm thử:** Dùng cả khách thường, khách lớn, request lặp trên một key, nhiều khách lớn đồng thời và burst. So sánh p50/p95/p99, số request thành công, DB rows scanned, memory và tỷ lệ từ chối dưới cùng mức tải.

## 17. Bài tập tự luyện

### Bài tập 1 — Tính ảnh hưởng của một hot key

Một hệ thống nhận 10.000 request/phút theo 1.000 key. Một key chiếm 6.000 request, 999 key còn lại chia nhau 4.000 request.

Hãy trả lời:
- Key nóng chiếm bao nhiêu phần trăm số request?
- Nếu partition theo hash(key), thêm partition có tự phân tán được request của key đó không?
- Nếu mỗi request của key nóng đắt gấp ba request thường, tỷ trọng công việc tương đối của key nóng là bao nhiêu?

*Gợi ý:* Hot key chiếm **60% request**. Với cùng đơn vị công việc thường, công việc nóng là 18.000 đơn vị so với 4.000 đơn vị còn lại, nên tỷ trọng là **18.000 / 22.000 ≈ 81,8%**. Việc chia partition không tự tách một key nếu hợp đồng routing luôn đưa nó tới một partition.

### Bài tập 2 — Giải thích p99

Trong một bài test, p50 = 20 ms, p95 = 100 ms, p99 = 2.000 ms. Tỷ lệ request trả lỗi là 0,2%.

Hãy nêu ít nhất ba giả thuyết gây độ trễ đuôi và cách đo để phân biệt chúng. Giải thích vì sao chỉ cải thiện p50 từ 20 ms xuống 15 ms chưa chứng minh người dùng gặp ít request chậm hơn.

*Gợi ý:* Xem cache miss, payload lớn, hot partition, GC, lock contention, DB pool wait và timeout/retry. Đo theo từng loại request, theo kích thước và giai đoạn xử lý.

### Bài tập 3 — SQL join và cardinality

Bảng **orders** có 100 dòng cùng customerId = A; bảng **customer_labels** có 20 dòng cũng thuộc A. Một truy vấn join chỉ bằng customerId cho kết quả bao nhiêu cặp ở A nếu không có điều kiện khác?

*Gợi ý:* Có thể tạo **100 × 20 = 2.000** dòng kết quả cho A. Hãy xem đây có đúng quan hệ nghiệp vụ cần không; nếu không, cần sửa khóa/điều kiện chứ không chỉ thêm DISTINCT.

### Bài tập 4 — Thiết kế load test

Một API đơn hàng chạy ổn ở 300 req/s với các SKU ngẫu nhiên gần đều. Nhưng trong giờ bán hàng giới hạn, 70% request cùng hỏi một SKU.

Hãy đề xuất hai bài test có **cùng tốc độ đến**, một phân bố đều và một có hot key, rồi nêu chỉ số nên so sánh: p95/p99, cache hit/miss, DB query, lock, số connection và lỗi. Hãy giải thích vì sao hai bài test có cùng request/giây vẫn có thể cho kết quả rất khác.

### Bài tập 5 — Quyết định caching

Nhóm muốn cache số dư tài khoản vì mỗi truy vấn gốc mất 30 ms. Mọi người nói “cache luôn nhanh hơn nên cứ làm”.

Hãy nêu:
- Những yêu cầu nào về độ mới và tính chính xác của số dư phải xác định trước?
- Cache stale có thể gây hậu quả gì?
- Liệu nên cache dữ liệu trực tiếp hay chỉ những kết quả phụ không ảnh hưởng quyết định chuyển tiền?
- Cần đo gì trước khi chọn?

*Gợi ý:* Mục tiêu hiệu năng không được thay thế hợp đồng nhất quán và quyền truy cập. Tối ưu cần phù hợp rủi ro nghiệp vụ.

### Bài tập 6 — Đánh giá cấu trúc dữ liệu

Một service dùng **HashMap<String, List<Order>>** để nhóm tất cả đơn theo tenant trong RAM trước khi tính tổng. Với tenant lớn, mỗi List rất dài; với nhiều tenant, số key cũng lớn.

Hãy đề xuất cách điều tra và phương án khác có thể cân nhắc, như aggregation phía database, streaming/batch, external sort hoặc tiền tổng hợp. Phân biệt trường hợp dữ liệu phải lưu đủ chi tiết với trường hợp chỉ cần tổng.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Nếu CPU trung bình toàn cụm là 40%, hệ thống chắc chắn chưa bão hòa?

*Trả lời:* Không. Một partition, lock, connection pool hoặc phụ thuộc bên ngoài có thể là điểm nghẽn; CPU trung bình che giấu bất cân bằng giữa node.

**Câu 2.** Vì sao tốc độ 1.000 request/giây không mô tả đầy đủ tải?

*Trả lời:* Request có thể khác nhau về dữ liệu, CPU, I/O, payload và tác dụng phụ. Cần biết workload mix và phân bố theo key/tenant.

**Câu 3.** Một key có 80% lưu lượng. Tăng gấp đôi số partition theo cùng hàm hash(key) có giải quyết được hot key không?

*Trả lời:* Không tự động. Một key vẫn ánh xạ tới một partition theo quy tắc đó; cần xem có thể thay caching, công việc, routing hoặc chia key mà vẫn giữ hợp đồng không.

**Câu 4.** Vì sao cần đo p95/p99 ngoài trung bình?

*Trả lời:* Trung bình có thể che giấu một nhóm ít request rất chậm. Những request đó có thể ảnh hưởng trải nghiệm và giữ tài nguyên lâu.

**Câu 5.** Một query có index chắc chắn nhanh cho mọi giá trị của điều kiện lọc?

*Trả lời:* Không. Hiệu quả phụ thuộc độ chọn lọc, phân bố dữ liệu, thống kê, kế hoạch truy vấn và lượng dữ liệu phải đọc.

**Câu 6.** Load test với dữ liệu gần đều có thể bỏ sót điều gì?

*Trả lời:* Hot key, partition skew, nhóm dữ liệu lớn, lock contention, cache stampede và đuôi chậm của một số tenant.

**Câu 7.** LongAdder thích hợp với thống kê lượt gọi có thể dùng thay số dư giao dịch cần snapshot chính xác không?

*Trả lời:* Không nên suy luận như vậy. LongAdder tối ưu cho một số mẫu đếm đồng thời; **sum()** không phải snapshot nguyên tử khi có cập nhật, nên không đáp ứng mọi yêu cầu nhất quán giao dịch.

**Câu 8.** Làm sao biết một tối ưu Java thật sự giúp API?

*Trả lời:* Kiểm tra bằng profiler và số đo toàn luồng trên tải đại diện, đối chiếu p95/p99, throughput, tài nguyên, tỷ lệ lỗi và tính đúng đắn, không chỉ microbenchmark của một phương thức.

## Ghi nhớ

**Hiệu năng khi tải tăng và dữ liệu lệch phân bố** không thể đánh giá bằng một request nhanh hoặc một con số trung bình. Cần quan sát **thông lượng, độ trễ đuôi, mức bão hòa, hàng đợi, phụ thuộc và phân bố công việc theo key/tenant/partition**. Một hot key có thể làm một partition quá tải trong khi toàn cụm còn dư CPU; một nhóm dữ liệu lớn hoặc một phép join thiếu chọn lọc có thể làm p99 xấu đi dù phần lớn request vẫn nhanh. Cách cải thiện đáng tin cậy là **đo trên workload đại diện, xác định điểm nghẽn, giảm công việc không cần thiết, điều tiết tài nguyên và kiểm chứng lại tính đúng đắn**. Mỗi lựa chọn như cache, batching, partitioning hay tăng song song đều phải được xem xét theo hợp đồng nghiệp vụ và khả năng vận hành thực tế.
