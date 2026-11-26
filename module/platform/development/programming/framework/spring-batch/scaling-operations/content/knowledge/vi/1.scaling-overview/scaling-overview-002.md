# Đo baseline trước khi tối ưu

**Chương:** Tổng quan scaling  
**Phạm vi:** SPRING_BATCH_SCALING_OPERATIONS

Một job Spring Batch đang chạy quá lâu chưa đủ để kết luận rằng cần thêm thread, partition hoặc worker phân tán. Job có thể chậm do truy vấn thiếu index, DataSource pool cạn, ghi dữ liệu từng dòng, contention trên database, xử lý CPU nặng, gọi API bên ngoài hoặc chờ một partition cuối cùng. Nếu chưa đo, việc tăng concurrency có thể chỉ chuyển hàng đợi sang tài nguyên khác và làm thời gian hoàn tất dài hơn.

Trong bài này, **baseline** là bộ số liệu đầu tiên, có thể lặp lại và đối soát được, mô tả *một cấu hình Spring Batch xử lý một workload xác định trong điều kiện xác định*. Nó là điểm xuất phát để quyết định có cần **multi-threaded step**, **parallel steps**, **partitioning**, **remote chunking** hay **remote partitioning** hay không, và để đánh giá một thay đổi có thực sự mang lại lợi ích.

Mục tiêu học tập: xác định KPI theo batch window, thiết kế phép đo đáng tin cậy, thu thập số liệu ở lớp Batch/JVM/database/hạ tầng, tìm nút thắt, đặt mục tiêu cải thiện và so sánh sau tối ưu mà vẫn bảo đảm **thread safety, retry/restart và tính đúng đắn dữ liệu**.

## 1. Baseline là gì và cần chứng minh điều gì?

Baseline là một **mốc đo hiệu năng có ngữ cảnh**, không đơn thuần là số giây từ lúc job bắt đầu đến lúc kết thúc.

Một baseline hữu ích trả lời đồng thời năm câu hỏi:

1. **Đang xử lý cái gì?** Kích thước input, độ phức tạp bản ghi, tỷ lệ dữ liệu lỗi và phân bố theo nguồn, ngày hoặc partition.
2. **Đang chạy bằng cấu hình nào?** Phiên bản Spring Batch/JDK, số step, chunk size, thread/worker, connection pool, JVM và tài nguyên database.
3. **Mất thời gian ở đâu?** Khởi tạo, đọc, xử lý, ghi, commit, chờ DB hoặc API, chờ queue và kết thúc.
4. **Hoàn thành được bao nhiêu công việc đúng?** Read/write/filter/skip, rollback, item thất bại, kết quả đối soát.
5. **Có đáp ứng yêu cầu vận hành không?** Batch window, tài nguyên, mức độ ổn định và khả năng phục hồi khi lỗi.

**Ví dụ:** “Job mất 150 phút” chưa cho biết khối lượng dữ liệu, có lọc bỏ 10% item hay không, CPU và database có đang bão hòa không, hoặc kết quả có bị ghi trùng không. Mô tả “6 triệu giao dịch, 150 phút, một worker, chunk 500, không skip, DB CPU 45%, thời gian chờ ghi chiếm phần lớn, đủ 6 triệu khóa nghiệp vụ duy nhất” có ích hơn nhiều.

### 1.1. Baseline không đồng nghĩa profiling

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Baseline** | Hệ thống hiện tại xử lý được bao nhiêu, với chi phí nào? | 6 triệu item / 151 phút; DB pool max 12 |
| **Monitoring** | Khi job chạy, tình trạng thay đổi ra sao? | Throughput theo phút; số connection chờ |
| **Profiling** | Đoạn mã/phương thức nào tiêu tốn CPU, heap hoặc thời gian? | Hàm chuyển đổi dữ liệu chiếm 68% CPU sampled |
| **Benchmark** | Cấu hình nào tốt hơn trong điều kiện thử nghiệm kiểm soát? | 1, 2, 4, 8 worker cùng dataset |
| **Load/stress test** | Hệ thống phản ứng thế nào khi tăng tải vượt mức bình thường? | Tăng số item, partition, request hoặc replica đến ngưỡng DB |

Baseline có thể kết hợp monitoring và profiling, nhưng không nên xem một lần profiling trên vài nghìn item là đại diện cho job chạy nhiều giờ với hàng triệu item.

## 2. Bắt đầu từ yêu cầu nghiệp vụ và batch window

Cần ghi rõ **SLO thực tế** trước khi đo. Một job chạy nhanh hơn 20% nhưng vẫn vượt hạn chót có thể chưa giải quyết bài toán; ngược lại, không cần nhân tám worker nếu cấu hình hiện tại hoàn thành với nhiều dư địa.

Các yêu cầu tối thiểu:

- **Khối lượng bắt buộc:** số item, file, byte hoặc đơn vị nghiệp vụ cần xử lý; trường hợp công việc không có tỷ lệ 1 item : 1 bản ghi đầu ra.
- **Batch window:** thời gian từ lúc đủ điều kiện chạy đến hạn chót; bao gồm khởi tạo, đọc, xử lý, ghi, kiểm tra kết quả và dọn dẹp nếu chúng chiếm thời gian vận hành.
- **Mức độ hoàn tất:** phải xử lý đủ mọi item hợp lệ, cho phép skip một số lỗi nghiệp vụ hay cần 100% thành công.
- **SLO lỗi và hồi phục:** tối đa bao lâu để restart, được phép replay bao nhiêu, kết quả có phải idempotent không.
- **Ngân sách tài nguyên:** CPU, heap, connection pool, khả năng DB, quota API, I/O và giới hạn broker trong thời gian chạy.
- **Tải nền:** các job, API hoặc dịch vụ khác cùng dùng database và hạ tầng.

### 2.1. Ví dụ xác định mục tiêu thông lượng

Giả sử job đối soát cần xử lý **6.000.000 giao dịch** trước khi cửa sổ **90 phút** kết thúc.

Thông lượng tối thiểu theo lý thuyết:

\[
Q_{\text{min}}=\frac{N}{T}
=\frac{6\,000\,000}{90\times60}
\approx 1\,111\ \text{item/giây}
\]

Nếu chỉ dự định sử dụng **80% cửa sổ** (72 phút) để dự phòng khởi động, biến động hoặc xử lý sự cố:

\[
Q_{\text{target}}=\frac{6\,000\,000}{72\times60}
\approx 1\,389\ \text{item/giây}
\]

Đây là **mục tiêu lập kế hoạch**, chưa phải mức ứng dụng hiện tại đạt được. Không giả định tăng từ 1 lên 2 worker sẽ nhân đôi throughput: DB hoặc I/O chung có thể giới hạn mức tăng thực.

Nếu mỗi input item bị lọc/skip khác nhau, KPI cần định nghĩa rõ: **input item/giây**, **output item/giây** và **item nghiệp vụ hoàn tất đúng/giây** không nhất thiết bằng nhau.

## 3. Thiết kế workload đại diện trước khi chạy đo

Một kết quả đo chỉ có giá trị trong điều kiện đã đo. Cấu hình tối ưu cho 10.000 giao dịch giả lập thường không thể suy rộng sang 10 triệu giao dịch có nhiều loại bản ghi và khóa ngoại.

### 3.1. Đóng băng dữ liệu thử

Ghi lại một **định danh dataset/snapshot** và mô tả:

| Thuộc tính | Cách ghi nhận | Vì sao quan trọng |
| --- | --- | --- |
| Tổng item/file/byte | 6.000.000 item, 24 file, 18 GB | Quy mô ảnh hưởng I/O và memory |
| Phân bố kích thước | Median/P95 payload, file lớn/nhỏ | Payload lớn tạo tail latency và GC |
| Độ phức tạp | % item cần lookup, phép tính hoặc gọi API | Item “nặng” làm lệch thời gian xử lý |
| Khóa phân vùng | ID, ngày, tenant, file | Dự đoán khả năng chia partition |
| Tỷ lệ bất thường | Null, duplicate, skip, retry dự kiến | Lỗi/skip có thể làm throughput trông cao giả |
| Trạng thái DB đích | Bảng rỗng, bảng đã có dữ liệu, index và constraint | Chi phí insert/update và lock khác nhau |
| Dữ liệu thay đổi khi chạy | Snapshot bất biến hoặc live data | Ảnh hưởng đọc lặp/bỏ sót và restart |

Nếu bài toán xử lý hàng chục triệu giao dịch nhưng chỉ đo 10 nghìn giao dịch, phép đo có thể bị chi phối bởi **startup, JIT, khởi tạo pool và cache nóng/lạnh**, không phản ánh trạng thái chạy dài.

Một bộ thử nghiệm thường cần ít nhất: dữ liệu **quy mô gần production**, dữ liệu có phân bố **khó nhất**, và trường hợp **lỗi/restart**. Không nên nhân dữ liệu ngẫu nhiên mà đánh mất tỷ lệ key trùng, record lớn hay hot key.

### 3.2. Khống chế trạng thái trước mỗi lần chạy

Để so sánh công bằng, cần xác định việc khôi phục môi trường:

1. Cùng commit ứng dụng và bộ dependency.
2. Cùng dataset đầu vào, phiên bản schema, index và dữ liệu tham chiếu.
3. Cùng mục tiêu ghi đầu ra: xóa/khôi phục bảng thử nghiệm hợp lệ hoặc dùng namespace riêng để tránh trùng record.
4. Cùng giới hạn CPU/RAM, connection pool, JVM options và số replica.
5. Cùng cấu hình chunk, transaction và policy retry, trừ tham số đang thử.
6. Cùng mức tải nền hoặc ghi rõ tải nền khác biệt.
7. Cùng cách xác định **job bắt đầu/kết thúc** và khoảng đo.

**Chạy lại trên output đã được ghi sẵn không tương đương chạy lần đầu.** Upsert có thể đổi từ insert sang update; cache và index cũng thay đổi. Nếu không thể restore môi trường, phải ghi rõ đây là baseline của trạng thái DB nào, tránh so sánh trực tiếp các lần chạy khác điều kiện.

### 3.3. Cold run và warm run

- **Cold run:** cache chưa được làm nóng; JVM, DB buffer cache, connection pool có thể đang khởi tạo.
- **Warm run:** hệ thống đã chạy một thời gian; có thể được hưởng lợi từ JIT, cache và connection reuse.

Nếu production thường chạy một job duy nhất ban đêm trên instance vừa khởi động, cold start là một phần thực tế. Nếu hệ thống xử lý nhiều job liên tiếp trên cùng process, cần thêm warm run. **Không loại bỏ startup khỏi SLO** chỉ để biểu đồ đẹp hơn.

## 4. Bộ KPI tối thiểu cho baseline

### 4.1. KPI end-to-end

| KPI | Cách hiểu | Lưu ý |
| --- | --- | --- |
| **Elapsed time** | Thời gian thực từ mốc bắt đầu đến mốc kết thúc | Không đồng nghĩa tổng CPU time của các thread |
| **Input throughput** | `readCount / elapsedSeconds` | Có thể gồm cả item bị filter/skip; định nghĩa rõ |
| **Successful output throughput** | `writeCount / elapsedSeconds` | Dễ bị hiểu sai nếu writer biến đổi 1:N hoặc upsert |
| **Completion ratio** | Item nghiệp vụ hoàn tất đúng / item phải xử lý | Cần nguồn kiểm chứng ngoài các counter |
| **Error/retry/rollback rate** | Lỗi, item skip, retry, rollback trên đơn vị xử lý/thời gian | Một job “nhanh” vì bỏ qua item không được chấp nhận |
| **SLO adherence** | Job hoàn tất và đối soát trước deadline? | Tính cả khởi động và hậu kiểm nếu nằm trong batch window |
| **Recovery time** | Từ lúc lỗi đến lúc kết quả hoàn tất sau restart | Quan trọng với job có deadline |

Ví dụ công thức (cần đo cùng một phạm vi):

\[
\text{Throughput (item/s)}=\frac{\text{item hoàn tất đúng}}{\text{elapsedSeconds}}
\]

\[
\text{Speedup}=\frac{T_{\text{baseline}}}{T_{\text{thử nghiệm}}}
\]

\[
\text{Scaling efficiency}=\frac{\text{Speedup}}{\text{số đơn vị xử lý tương đối}}
\]

Nếu từ một worker lên bốn worker, tốc độ nhanh hơn 2,8 lần thì hiệu quả theo đơn vị worker là \(2,8/4 = 70\%\). Kết quả này cần được kiểm tra cùng chi phí tài nguyên, vì số worker chưa chắc đồng nghĩa số CPU core được cấp bằng nhau.

### 4.2. KPI từng step và từng partition

Spring Batch có **JobExecution** và **StepExecution** với các dữ liệu như trạng thái, thời điểm, số item đã đọc/ghi, số item bị filter/skip, commit và rollback. Số liệu step nên lưu kèm **job name, job instance/execution ID, step name, partition name**, cấu hình concurrency và dataset ID.

Cần tránh nhầm:

- **Read count** là số item đọc ở cấp step, không mặc định bằng số record dữ liệu nguồn có sẵn.
- **Write count** biểu diễn item được ghi theo cơ chế Batch; không phải lúc nào cũng phản ánh số dòng DB bị tác động sau logic upsert hay write 1:N.
- **Filter count** là item processor trả về null và bị lọc; **skip count** là item bị bỏ qua theo chính sách lỗi. Chúng không giống nhau.
- **Commit count** là số chunk transaction commit, **rollback count** là số rollback ở step; không nên xem từng commit là một item.
- Khi job retry/restart, không cộng bừa counter của nhiều JobExecution rồi kết luận có bao nhiêu bản ghi duy nhất trong DB.

Với **partitioning**, cần xem phân bố thời gian chứ không chỉ tổng:

\[
T_{\text{partitioned job}}\gtrsim \max(T_{p_1},T_{p_2},...,T_{p_k})+\text{chi phí điều phối}
\]

Đây là cận dưới trực giác nếu các partition được xử lý đồng thời và không có tranh chấp. Thực tế một số partition phải đợi slot worker, nên tổng thời gian có thể lớn hơn đáng kể. Nếu 15 partition xong sau 5 phút nhưng partition cuối cần 40 phút, việc tăng thread không nhất thiết chữa được **skew**.

## 5. Đo công đoạn để tìm nút thắt

Một chunk-oriented step thường gồm đọc, xử lý, ghi và commit. Cần phân biệt **thời gian công đoạn** với **thời gian end-to-end**.

~~~mermaid
flowchart LR
    A["Input / DataSource"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E["Commit"]
    E --> F["Output"]
    B -.-> M["Metrics read / process / write"]
    C -.-> M
    D -.-> M
    E -.-> M
    M --> G["Baseline theo StepExecution"]
~~~

Ví dụ một **step chạy tuần tự**, số đo ở một job hoàn tất trong 151 phút có thể được phân bổ xấp xỉ:

| Công đoạn | Thời gian cộng dồn minh họa | Nhận xét |
| --- | ---: | --- |
| Khởi tạo / kết thúc | 7 phút | Startup, reader open/close, hậu kiểm |
| Đọc | 14 phút | Đọc file hoặc SQL |
| Xử lý | 20 phút | CPU, chuyển đổi và lookup |
| Ghi + commit | 110 phút | Có thể bao gồm lock wait và transaction |
| **Tổng** | **151 phút** | Chỉ cộng trực tiếp khi các khoảng đo không chồng lấn |

Nếu step đã có concurrency, **tổng thời gian gọi processor của nhiều thread có thể lớn hơn thời gian job**; khi đó tổng các timer không thể cộng như một timeline. Cần đo critical path, thời gian chờ và throughput đầu-cuối để tránh kết luận sai.

### 5.1. Khi Reader chậm

Quan sát:

- Thời gian gọi `read()`, số trang/truy vấn, rows fetched/giây.
- SQL execution plan, index scan/table scan, lock waits, network latency.
- Đọc file tuần tự, throughput đĩa, kích thước buffer và độ trễ nguồn bên ngoài.
- Chi phí mở connection/cursor; chi phí fetch và khả năng paging.

Một Reader yếu có thể làm **remote chunking** nghẽn ở manager. Tăng worker xử lý phía sau không giúp nếu manager không cung cấp đủ item.

### 5.2. Khi Processor chậm

Quan sát:

- CPU theo thread, allocation rate và GC pressure.
- Thời gian tính toán so với thời gian chờ lookup DB/API.
- Các bản ghi đặc biệt tốn thời gian; tỷ lệ cache hit/miss.
- Cách chia dữ liệu có để một worker nhận toàn item “nặng” không.

Nếu tính toán CPU độc lập và còn core trống, multi-threaded processing hoặc partitioning có thể phù hợp. Nhưng nếu Processor giữ trạng thái dùng chung hoặc gọi dịch vụ giới hạn rate, tăng concurrency cần kiểm chứng thread safety và quota.

### 5.3. Khi Writer/commit chậm

Quan sát:

- Thời gian `write()`, số SQL statements, batch size, transaction/commit duration.
- Lock waits, deadlocks, index update, WAL/redo log, IOPS và replication lag.
- Connection pool active/pending, thời gian mượn connection.
- Các retry/rollback tăng do ghi cạnh tranh.

Tăng thread có thể khiến Writer bị tranh chấp nhiều hơn. Trước tiên kiểm tra batching, SQL, transaction boundary và khả năng xử lý của database.

### 5.4. Khi các bước phụ thuộc nhau

Một job có các step A → B → C thì thời gian tổng gần bằng tổng các phần nối tiếp (cộng overhead). Chỉ có thể chạy **parallel steps** khi chúng thực sự không phụ thuộc dữ liệu hay kết quả của nhau. Baseline phải có thời gian từng step, không chỉ tổng job, để đánh giá cơ hội tách flow.

## 6. Đo hạ tầng song song với số liệu Batch

**Chỉ đo StepExecution là chưa đủ.** Cùng một step chậm có thể do CPU hoặc DB, cần đối chiếu nguồn quan sát tại cùng thời điểm.

| Tầng | Chỉ số nên thu | Câu hỏi cần trả lời |
| --- | --- | --- |
| JVM | CPU, heap used/max, allocation, GC pause, live threads | Có thiếu CPU/RAM hoặc bị pause dài không? |
| TaskExecutor | Active threads, queue depth, task rejected, thời gian chờ | Số worker thực sự đang làm việc? |
| DataSource pool | Active, idle, pending, acquire/hold time, timeout | Worker đang chờ connection? |
| Database | Query latency/P95, active sessions, lock waits, IOPS, CPU, transaction duration | DB là nút thắt thực tế? |
| Filesystem | Read/write bandwidth, latency, lỗi I/O | Đọc file có đạt tốc độ yêu cầu? |
| Network/API | Request rate, latency, timeout, 429/5xx, quota | Có bị upstream/downstream giới hạn? |
| Broker (nếu có) | Queue depth, oldest message age, in-flight, redelivery, DLQ | Remote worker có nhận và hoàn tất kịp? |
| OS/container | CPU throttling, memory limit, restarts, disk saturation | Thông lượng thấp do giới hạn container? |

**Đồng bộ timestamp** là yêu cầu quan trọng: nếu job giảm throughput lúc 02:14 và DB lock wait cũng tăng lúc 02:14, có thể lập giả thuyết liên quan. Một snapshot CPU trung bình trong 3 giờ sẽ che mất nghẽn trong vài phút.

### 6.1. Spring Batch observability theo phiên bản

Spring Batch có metadata JobRepository và hỗ trợ metrics/observation tích hợp với Micrometer theo cấu hình thích hợp. Tuy nhiên tên metric/tag và cách cấu hình có thể thay đổi giữa **Spring Batch 4/5/6**; cần xem tài liệu versioned, kiểm tra metric đang được xuất thực tế, rồi mới xây dashboard.

Có thể kết hợp:

- JobRepository / `JobExplorer` để đọc trạng thái và counter của những lần thực thi.
- Micrometer timers/observations cho khoảng thời gian gọi reader, processor, writer và step.
- HikariCP metrics cho pool JDBC khi ứng dụng dùng Hikari.
- JVM/process/container metrics qua Micrometer, JMX hoặc nền tảng giám sát.
- Traces/log có cùng execution ID để liên kết job, partition và downstream.

Không tăng log per-item trong bài đo hàng triệu item nếu log I/O tự trở thành nút thắt. Dùng số liệu tổng hợp theo khoảng thời gian (ví dụ 10–30 giây) và sampling khi cần truy vết item đặc biệt.

### 6.2. Mẫu log tóm tắt StepExecution

Đối với **Spring Batch 5.x**, có thể dùng listener ghi thông tin khi step kết thúc:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BaselineStepListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BaselineStepListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        LocalDateTime start = step.getStartTime();
        LocalDateTime end = step.getEndTime();
        double seconds = start != null && end != null
                ? Math.max(0.001, Duration.between(start, end).toMillis() / 1000.0)
                : Double.NaN;

        long reads = step.getReadCount();
        long writes = step.getWriteCount();
        double readPerSecond = reads / seconds;

        log.info("baseline step={} executionId={} status={} " +
                 "durationSec={} read={} write={} filter={} " +
                 "skip={} commit={} rollback={} readPerSec={}",
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                seconds,
                reads,
                writes,
                step.getFilterCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount(),
                readPerSecond);

        return null; // Giữ nguyên ExitStatus của step.
    }
}
~~~

Mã trên là **mẫu instrumentation cho API Batch 5.x**; Spring Batch 6 có thay đổi package/domain API, vì vậy cần điều chỉnh import và xác nhận chữ ký theo Javadoc đúng phiên bản. Listener cần được **đăng ký với step**; chỉ tạo một bean chưa bảo đảm mọi step dùng nó. Không phát sinh truy vấn ngoài hoặc gọi API chậm trong listener kết thúc nếu muốn số đo phản ánh chính xác công việc Batch.

**Giới hạn của ví dụ:** tính `readPerSec` từ số đọc và toàn bộ thời gian step cho biết thông lượng trung bình, chưa chỉ ra độ trễ của Reader hoặc thời gian chờ DB. Ngoài ra, timer dựa trên timestamp metadata có sai số và không phù hợp đo microsecond của từng phương thức; dùng Micrometer timer hoặc công cụ profile phù hợp khi cần chi tiết.

## 7. Thu thập baseline theo pha và theo thời gian

Một job chạy hai giờ không phải lúc nào cũng có cùng throughput. Có thể tăng tốc sau warm-up rồi giảm mạnh khi DB lock contention, GC hoặc queue backlog xuất hiện.

Phân tách thời gian chạy thành:

1. **Startup:** khởi tạo Spring context nếu trong batch window, kết nối DB, chuẩn bị nguồn.
2. **Warm-up:** JIT/cache/connection pool ổn định.
3. **Steady state:** throughput và tài nguyên tương đối ổn định trên khoảng đo.
4. **Tail:** các partition còn lại, dữ liệu khó, flush/batch write, checkpoint cuối.
5. **Finalization:** đối soát, xuất báo cáo, đóng resource, trạng thái hoàn tất.

Đo **elapsed time toàn job** để kiểm tra SLO, đồng thời xem thông lượng theo từng khoảng để giải thích sự thay đổi. Không lấy chỉ số steady state ấn tượng nhất làm đại diện cho toàn job.

### 7.1. Ví dụ đo theo từng khoảng 15 phút

| Khoảng | Input item/giây | Pool pending | DB lock wait | Nhận xét |
| --- | ---: | --- | --- | --- |
| 00–15 phút | 550 | Thấp | Thấp | Khởi tạo/cold cache |
| 15–30 phút | 730 | Thấp | Thấp | Gần steady state |
| 30–45 phút | 720 | Thấp | Thấp | Ổn định |
| 45–60 phút | 470 | Cao | Cao | Có tải cạnh tranh hoặc contention |
| 60–75 phút | 700 | Thấp | Thấp | Phục hồi sau thời điểm nghẽn |

Đây là **số liệu minh họa**, chưa phải kết luận nhân quả. Phải đối chiếu số lần commit/rollback, tải DB và sự kiện hệ thống ở thời điểm throughput giảm.

### 7.2. Percentile và độ lệch

Trung bình giúp ước lượng năng lực dài hạn nhưng che giấu tail latency. Một API downstream trung bình 50 ms nhưng P99 = 5 giây có thể giữ connection hoặc thread rất lâu theo từng đợt.

Nên lưu:

- Median (P50), P95/P99 của SQL, API, thời gian acquire connection và chunk nếu có histogram đúng.
- Số lần timeout, retry và rollback trong khoảng đo.
- Kích thước/độ khó của partition chậm nhất.
- Độ dao động giữa nhiều lần chạy toàn job.

Không suy ra P95/P99 đáng tin cậy từ vài mẫu hoặc các histogram có số mẫu quá ít.

## 8. Ví dụ baseline đầy đủ và quyết định bước kế tiếp

Giả sử job nhập **6.000.000 giao dịch** với một chunk-oriented step tuần tự. Cửa sổ 90 phút, mục tiêu có 20% thời gian dự phòng là 72 phút. Ba lần chạy cùng dataset và cấu hình tạo số liệu:

| Run | Elapsed | Throughput \(\approx N/T\) | Đối soát | Kết quả |
| --- | ---: | ---: | --- | --- |
| B-01 | 148 phút | 676 item/giây | Đủ 6 triệu khóa duy nhất | COMPLETED |
| B-02 | 151 phút | 662 item/giây | Đủ 6 triệu khóa duy nhất | COMPLETED |
| B-03 | 155 phút | 645 item/giây | Đủ 6 triệu khóa duy nhất | COMPLETED |

Đây là **dữ liệu giả định để minh họa cách phân tích**, không phải benchmark của Spring Batch.

- **Median elapsed:** 151 phút.
- **Median throughput:** khoảng 662 item/giây.
- **Mức tối thiểu cần đạt cửa sổ 90 phút:** khoảng 1.111 item/giây.
- **Mục tiêu có dự phòng 20% thời gian:** khoảng 1.389 item/giây.
- **Hệ số cải thiện cần thiết so với baseline median:** khoảng \(1389/662 \approx 2{,}10\) lần.

Chúng ta có **vấn đề công suất thật**, nhưng chưa biết giải pháp là thêm worker.

### 8.1. Đối chiếu metrics để tìm giả thuyết

Giả sử từ ba run, dữ liệu cho thấy:

| Quan sát | Giải thích có thể xảy ra | Kiểm chứng tiếp |
| --- | --- | --- |
| Reader chiếm khoảng 14/151 phút, CPU Processor thấp | Đọc không phải nút thắt chính | Kiểm tra query/fetch để chắc chắn |
| Writer + commit chiếm khoảng 110/151 phút | Ghi có thể đang giới hạn throughput | SQL batching, DB locks, IOPS, index |
| DB lock waits tăng ở cuối giờ | Có cạnh tranh với job khác | So lịch job và DB activity |
| Pool có nhiều connection idle | Chưa có bằng chứng pool là giới hạn chính | Theo dõi active/pending khi throughput giảm |
| Không có skip, rollback ít, đối soát đủ | Baseline có tính đúng đắn | Giữ tiêu chí này ở mọi thử nghiệm sau |

Nếu Writer là điểm nghẽn, nên **tối ưu câu lệnh ghi và transaction trước**, hoặc điều chỉnh lịch tải DB. Tăng số thread trong một step có thể làm lock contention tăng. Sau khi xác định DB còn dư địa mới thử partitioning hay parallelism phù hợp.

### 8.2. Thiết kế thử nghiệm thay đổi từng yếu tố

Một ma trận giả định:

| Thử nghiệm | Thay đổi | Elapsed | Ý nghĩa |
| --- | --- | ---: | --- |
| B-02 | Baseline: một worker, writer hiện tại | 151 phút | Mốc so sánh |
| E-01 | Tối ưu batch write, giữ một worker | 112 phút | Giảm chi phí write |
| E-02 | Giữ write đã tối ưu; local partitioning 2 worker | 78 phút | Tăng concurrency có lợi |
| E-03 | Giữ write đã tối ưu; 4 worker | 68 phút | Đạt mục tiêu 72 phút |
| E-04 | Giữ write đã tối ưu; 8 worker | 72 phút | Bão hòa tài nguyên/contend |
 
**Lưu ý:** E-02 và E-03 có thể là các bước đo tiếp theo sau khi E-01 đã hoàn tất; các kết quả minh họa không đủ để kết luận nguyên nhân nếu điều kiện thử thay đổi. Ở mức 8 worker mà thời gian tăng, cần xem DB lock waits, connection pool, CPU throttling và phân bố partition trước khi điều chỉnh.

Một thay đổi chỉ được coi là thành công nếu **đối soát đúng, retry/restart không bị suy giảm và ngân sách tài nguyên chấp nhận được**, chứ không chỉ nhanh hơn vài phút.

## 9. Baseline theo từng kiến trúc scaling

Không phải mô hình nào cũng có cùng đơn vị công việc. Khi thử kiến trúc mới, giữ **cùng mục tiêu nghiệp vụ** nhưng đo thêm các giới hạn đặc thù.

| Mô hình | Cần đo thêm | Nút thắt dễ bị che |
| --- | --- | --- |
| **Multi-threaded step** | Executor active/queue, mức thread safety Reader/Processor/Writer, số chunk đang chạy | Shared state, Reader bị khóa đồng bộ, DB pool cạn |
| **Parallel steps** | Timeline từng flow, phụ thuộc dữ liệu, số step chạy đồng thời | DB shared contention, một flow dài quyết định tổng |
| **Local partitioning** | Số partition được tạo/đang chạy, skew, thời gian chậm nhất, grid size và executor concurrency | Một partition quá lớn, truy vấn hot key |
| **Remote partitioning** | Worker/pod throughput, request/reply latency, JobRepository load, queue depth | Metadata DB, dữ liệu lệch, worker chết hoặc thiếu slot |
| **Remote chunking** | Read throughput ở manager, số chunk in-flight, broker latency, worker process/write throughput | Manager Reader, payload lớn, reply chậm, broker |
| **Khởi chạy nhiều job đồng thời** | JobExecutor/scheduler, pool chung, quota DB và I/O theo tổng các job | Job riêng lẻ ổn nhưng tổng vượt capacity |

**Cẩn trọng về version:** từ Spring Batch 5.x sang 6.x, API và một số ngữ nghĩa chunk/concurrency có thể khác. Khi so baseline giữa các version, phải ghi rõ version và xác nhận vị trí đọc, xử lý, ghi và transaction. Một lời gọi `taskExecutor(...)` ở hai version không bảo đảm cùng topology thực thi.

### 9.1. Partition skew

Giả sử chia 8 partition theo dải ID với thời gian ước lượng:

~~~text
p0  ███          8 phút
p1  ████        10 phút
p2  ███          9 phút
p3  ███████████ 29 phút
p4  ████        11 phút
p5  ███          9 phút
p6  ████        10 phút
p7  ███          8 phút
~~~

Nếu cả 8 partition chạy cùng lúc, elapsed phần xử lý vẫn phải chờ ít nhất khoảng 29 phút của p3 (chưa kể điều phối và transaction). **Throughput trung bình theo worker** có thể cao nhưng cả job bị chậm bởi partition cuối.

Baseline partition cần lưu **số item, kích thước dữ liệu, thời gian và số retry của từng partition**. Có thể phải thay cách chia key/range hoặc tái cân bằng workload thay vì tăng thread.

### 9.2. Nút thắt database chung khi tăng worker

Khi tăng từ 4 lên 8 worker, số kết nối tối đa của các JVM/replica có thể cũng tăng. Đo cả:

\[
\text{Tổng pool limit đến DB}=\sum_{i=1}^{R}\text{maxPoolSize}_i
\]

Tổng giới hạn phải nằm trong ngân sách kết nối của DB đã trừ cho dịch vụ khác và dự phòng. Tuy nhiên **DB có thể bão hòa CPU, lock hoặc I/O trước khi chạm max connections**. Không dùng connection count như proxy duy nhất cho năng lực database.

## 10. Tính đúng đắn và khả năng restart phải nằm trong baseline

Spring Batch cung cấp quản lý metadata, checkpoint và transaction, nhưng concurrency và phân tán đặt thêm yêu cầu:

- **Đối soát input/output:** số business key duy nhất, tổng tiền, checksum hoặc aggregate nghiệp vụ; quan sát cả record thiếu, trùng, bị filter và skip.
- **Idempotency:** thử xử lý lại cùng item/chunk/partition; writer không được phát sinh tác động trùng sai.
- **Retry:** đo số lần, lỗi và thời gian phát sinh; phân biệt retry trong step, retry ở broker và restart cả job.
- **Restart:** thử lỗi sau một số chunk đã commit, rồi chạy lại với đúng JobParameters và dữ liệu snapshot.
- **Concurrency safety:** kiểm tra Reader/Writer có state dùng chung, thứ tự bắt buộc, giao dịch nhiều luồng và ranh giới partition.
- **Hệ thống bên ngoài:** API request, message/event hoặc email có thể không rollback cùng transaction JDBC; cần idempotency key/outbox hoặc cơ chế đối soát thích hợp.

### 10.1. Baseline cho retry/restart

Một baseline production nên có thêm **thử nghiệm lỗi có kiểm soát**, ví dụ:

1. Cho job chạy tới khi hoàn tất khoảng một phần ba công việc.
2. Tạo lỗi tạm thời ở Worker/DB trong môi trường thử nghiệm cô lập.
3. Ghi nhận thời gian phát hiện lỗi, trạng thái StepExecution, chunk đã commit và message in-flight nếu có.
4. Khôi phục dịch vụ rồi restart đúng JobInstance theo quy trình.
5. Đối soát dữ liệu, số item có tác động trùng và thời gian xử lý còn lại.

Khi nâng concurrency, baseline phục hồi cho biết giải pháp “nhanh hơn” có khiến thời gian restart hoặc số item cần replay tăng quá mức hay không.

**Không mặc định exactly-once:** một worker có thể commit dữ liệu rồi mất kết nối trước khi manager nhận xác nhận. Những hệ thống phân tán cần chính sách xử lý phát lại rõ ràng.

## 11. Cách ghi lại một phiếu baseline có thể so sánh

Mọi lần đo nên tạo một bản ghi đủ ngữ cảnh. Ví dụ:

~~~yaml
experiment:
  id: baseline-2026-11-26-a
  goal: "6,000,000 giao dịch trong tối đa 90 phút"
  dataset_id: "snapshot-transactions-6m-v1"
  output_validation: "6,000,000 khóa nghiệp vụ duy nhất, tổng tiền đối soát"
application:
  spring_batch_version: "Ghi phiên bản thực tế"
  spring_boot_version: "Ghi phiên bản thực tế"
  jdk_version: "Ghi phiên bản thực tế"
  commit: "Ghi commit thực tế"
execution:
  topology: "single-jvm, one chunk-oriented step"
  active_worker_limit: 1
  chunk_size: 500
  partitions: 1
  replicas: 1
  datasource_pool_max: 12
environment:
  cpu_limit: "Ghi CPU và quota thực"
  memory_limit: "Ghi RAM/heap thực"
  database: "Ghi loại DB, cấu hình và tải nền"
measurement:
  starts_at: "Job launch accepted"
  ends_at: "Job completed and reconciliation finished"
  runs: 3
  sampling_interval_seconds: 15
  record_cold_and_warm: true
metrics:
  job_elapsed_seconds: "Thu thập số thực sau mỗi run"
  read_count: "Thu thập từ StepExecution"
  write_count: "Thu thập từ StepExecution"
  skip_count: "Thu thập từ StepExecution"
  rollback_count: "Thu thập từ StepExecution"
  throughput_items_per_second: "Tính theo cùng mẫu số"
  cpu_peak: "Thu thập"
  db_lock_wait: "Thu thập"
  connection_pool_pending: "Thu thập"
~~~

Các giá trị trong ví dụ là **mẫu biểu**; không được coi chuỗi “Ghi phiên bản thực tế” là dữ liệu đo. Nếu có nhiều step, nhiều DataSource hoặc nhiều worker, lưu các số đo **theo từng thực thể** và tổng hợp chính xác ở cấp job.

Một kết quả tối thiểu cần có: **mã run, dataset, version/commit, cấu hình, trạng thái job, elapsed, count, throughput, sai lệch đối soát, tài nguyên và nhận xét**. Có thể bổ sung liên kết dashboard, profiler snapshot và trace theo `jobExecutionId`.

## 12. Quy trình thực hành từ baseline đến quyết định tối ưu

~~~mermaid
flowchart TD
    A["Xác định batch window, khối lượng và tiêu chí đúng"] --> B["Chốt dataset, build và hạ tầng"]
    B --> C["Chạy baseline nhiều lần"]
    C --> D["Thu Job/Step + JVM/DB/broker metrics"]
    D --> E{"Có sai lệch dữ liệu hoặc chạy lỗi?"}
    E -->|Có| F["Sửa tính đúng đắn, retry/restart rồi đo lại"]
    E -->|Không| G["Xác định bottleneck từ số liệu"]
    G --> H["Đề xuất một thay đổi có giả thuyết rõ"]
    H --> I["Chạy thử nghiệm cùng điều kiện"]
    I --> J{"Cải thiện throughput và vẫn đúng?"}
    J -->|Không| K["Giữ baseline, phân tích số liệu"]
    J -->|Có| L["Ghi baseline mới và kiểm thử lỗi"]
    K --> G
    F --> C
~~~

### Bước 1 — Xác định câu hỏi đo

Ví dụ: “Tại sao job đối soát vượt 90 phút?” hoặc “DB Writer hay CPU Processor mới là nút thắt khi tăng worker từ 2 lên 4?” Câu hỏi cụ thể quyết định metrics cần thu.

### Bước 2 — Chạy ít nhất vài lần đại diện

Nếu khả thi, đo **ít nhất ba lần** cùng điều kiện để có trung vị và độ dao động. Với workload rất tốn thời gian, ghi rõ hạn chế nếu chỉ chạy được một lần, tránh kết luận chắc chắn từ một mẫu duy nhất.

### Bước 3 — Kiểm tra tính đúng đắn trước hiệu năng

Nếu một run COMPLETED nhưng đối soát thiếu bản ghi, loại nó khỏi phép so sánh “throughput xử lý đúng”. Một job ghi ít item có thể có elapsed time ngắn một cách giả tạo.

### Bước 4 — Đặt giả thuyết có thể bác bỏ

Ví dụ: “Thời gian ghi chiếm 70% elapsed và DB chưa bão hòa; đổi writer từ insert từng row sang JDBC batch sẽ giảm số round trip và rút ngắn elapsed time, không thay đổi dữ liệu.”

Giả thuyết tốt dự đoán **metric nào phải thay đổi**. Nếu số round trip giảm nhưng elapsed không giảm, cần xem transaction/lock/other work thay vì khẳng định thành công.

### Bước 5 — Thử nghiệm một biến rồi so với baseline

Giữ workload và điều kiện tương đương; sửa một yếu tố có thể kiểm soát như chunk size, batching, executor concurrency, partition strategy hoặc pool size. Sau đó:

- Tính elapsed, throughput, speedup và độ dao động.
- Kiểm tra CPU, DB waits, pool pending và chi phí worker.
- Đối soát dữ liệu và thử tình huống lỗi/restart có liên quan.
- Ghi lại cấu hình mới nếu kết quả thực sự tốt và ổn định.

Tối ưu một thành phần có thể chuyển bottleneck sang thành phần khác. **Baseline nên được đo lại** sau mỗi thay đổi kiến trúc đáng kể.

## 13. Các sai lầm thường làm baseline không còn giá trị

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đo trên vài nghìn item nhưng áp dụng cho hàng triệu | Overhead startup/cache lấn át phần xử lý dài hạn | Dùng dataset có quy mô và phân bố gần production |
| Không đối soát đầu ra | Job chạy nhanh do bỏ sót/filter/skip | Kiểm tra business key, checksum và tổng nghiệp vụ |
| Chỉ lấy một lần chạy | Không biết variance hay tải nền bất thường | Lặp lại nhiều lần và lưu điều kiện |
| Thử nhiều thay đổi cùng lúc | Không biết thay đổi nào có tác dụng | Kiểm soát một biến khi có thể |
| Chạy lần 2 trên DB đã có output của lần 1 | SQL insert/update, index và lock khác nhau | Restore dữ liệu hoặc dùng môi trường/namespace tương đương |
| Lấy CPU trung bình toàn ngày | Bỏ qua nghẽn trong lúc job chạy | Căn chỉnh metrics theo JobExecution và khoảng đo |
| Cộng thời gian nhiều thread rồi gọi là elapsed | Có thể lớn hơn wall time | Phân biệt tổng timer và thời gian đầu-cuối |
| Nhìn readCount nhưng bỏ qua skip/filter | Đánh giá sai mức xử lý thành công | Thu đủ counter và số liệu đối soát |
| Gộp tất cả partition thành một trung bình | Không phát hiện partition cuối kéo dài | Xem max/P95 thời gian partition và phân bố item |
| Tăng worker mà không tính các pool/replica | DB quá tải và job chậm hơn | Đo quota DB ở cấp toàn cụm |
| Chỉ thử happy path | Không biết độ an toàn khi restart | Thử fail/replay ở ranh giới commit |
| Dùng metric/tag giả định từ phiên bản khác | Dashboard thiếu số liệu hoặc hiểu sai | Kiểm tra API và metrics thực theo version |

## 14. Checklist baseline trước khi bắt đầu scaling

- [ ] Có **workload mục tiêu**, batch window và mục tiêu throughput rõ.
- [ ] Có **dataset ID**, kích thước, phân bố và kế hoạch reset output.
- [ ] Có phiên bản Spring Batch/Boot/JDK, commit, schema và cấu hình job/step.
- [ ] Có số worker/partition/executor concurrency, chunk size, transaction policy.
- [ ] Có giới hạn CPU, RAM, DataSource pool, DB connection/quota API và tải nền.
- [ ] Có thời gian **JobExecution** và **StepExecution**, count/read/write/filter/skip/commit/rollback.
- [ ] Có metrics JVM, DB, pool, OS và broker nếu dùng xử lý phân tán.
- [ ] Có thời gian Reader/Processor/Writer hoặc một cách khác để nhận diện nút thắt.
- [ ] Đã đo **nhiều lần** nếu khả thi, biết median và biến động.
- [ ] Đã đối soát dữ liệu và phân biệt thành công với việc chỉ kết thúc job.
- [ ] Đã ghi thời điểm lỗi, retry, restart và tác động sau commit nếu có.
- [ ] Đã đặt giả thuyết tối ưu dựa trên bằng chứng, cùng tiêu chí đánh giá sau thay đổi.

## 15. Ghi nhớ

**Đo baseline trước khi tối ưu** nghĩa là xây dựng một điểm xuất phát vừa **đo được**, vừa **lặp lại được** và **đúng dữ liệu**. Một baseline tốt cho Spring Batch kết hợp số liệu **Job/StepExecution**, throughput đầu-cuối, độ trễ từng công đoạn, metrics JVM/DB/connection pool và điều kiện tải của hệ thống.

Khi đã biết công việc nào đang chiếm thời gian và tài nguyên nào đang giới hạn throughput, việc chọn **tối ưu SQL/chunk size**, **multi-threaded step**, **parallel steps**, **local/remote partitioning** hoặc **remote chunking** mới dựa trên bằng chứng. Kết quả sau thay đổi phải được đo bằng **cùng workload, cùng định nghĩa KPI và cùng tiêu chí đối soát/restart**, thay vì chỉ so số thread hoặc số phút trên hai lần chạy không tương đương.
