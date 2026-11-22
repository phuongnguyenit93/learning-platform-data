# Đánh đổi throughput với khả năng phục hồi trong Spring Batch

## 1. Bài toán thiết kế: xử lý nhanh hay phục hồi dễ?

Một batch job phải nạp hàng triệu giao dịch trong cửa sổ xử lý ban đêm. Khi tăng kích thước chunk, gom SQL và chạy nhiều worker, job có thể hoàn tất nhanh hơn. Nhưng nếu JVM chết, một partition mất kết nối hoặc một writer gọi API ngoài bị timeout, hệ thống cần biết **phần nào đã hoàn tất, phần nào phải xử lý lại và liệu lần chạy lại có tạo dữ liệu trùng không**.

Đó là sự đánh đổi giữa **throughput** (khả năng xử lý nhiều công việc trong một đơn vị thời gian) và **recoverability** (khả năng tiếp tục hoặc phục hồi đúng sau sự cố). Trong Spring Batch, hai mục tiêu này liên quan chặt chẽ đến commit interval, transaction boundaries, `JobRepository`, `ExecutionContext`, `ItemStream`, retry/skip, idempotency và concurrency.

```text
                        Thiết kế batch
                             |
               +-------------+-------------+
               |                           |
         Tăng throughput              Tăng khả năng phục hồi
               |                           |
       Ít commit hơn                  Checkpoint thường xuyên
       Batch I/O lớn hơn               Transaction ngắn hơn
       Xử lý song song                 Input bất biến
       Giảm overhead                  Idempotent output
               |                           |
               +-------------+-------------+
                             |
                     Đo và lựa chọn
                   theo SLA, rủi ro lỗi,
                   chi phí replay thực tế
```

Không có cấu hình “nhanh nhất và luôn phục hồi tốt nhất” cho mọi workload. Một job chỉ ghi vào cùng một database transactional rất khác một job gửi payment API, xuất file lên object storage hoặc gọi nhiều hệ thống không chia sẻ transaction.

**Mục tiêu của bài học** không phải chọn sẵn `chunkSize=100` hay `chunkSize=1000`, mà là xây dựng cách ra quyết định có thể giải thích, kiểm thử và vận hành được.

## 2. Những chỉ tiêu phải định nghĩa trước khi tối ưu

| Chỉ tiêu | Câu hỏi cần trả lời | Cách xác định |
|---|---|---|
| Throughput | Một giây xử lý hoàn tất bao nhiêu đơn vị công việc? | Số record **đã được chấp nhận/commit** trên thời gian thực chạy. |
| Makespan | Một batch chạy mất bao lâu từ lúc bắt đầu đến lúc sẵn sàng sử dụng kết quả? | Tính cả chuẩn bị, xử lý, xác minh và publish output. |
| RTO (*Recovery Time Objective*) | Sau sự cố, tối đa bao lâu được phép khôi phục dịch vụ/job? | Sự phát hiện lỗi + điều tra/ra quyết định + restart/replay + kiểm tra kết quả. |
| RPO (*Recovery Point Objective*) | Chấp nhận mất bao nhiêu kết quả **không thể khôi phục**? | Định nghĩa theo nghiệp vụ, nguồn dữ liệu và khả năng tái xử lý. |
| Replay window | Khi crash, tối đa bao nhiêu work có thể phải chạy lại? | Phụ thuộc commit interval, checkpoint, partition và side effect. |
| Duplicate tolerance | Có chấp nhận xử lý lại cùng một input không? | Định nghĩa idempotency/unique constraint hoặc cơ chế đối soát. |
| Failure rate | Sự cố thường xuất hiện ở tần suất nào? | Đo từ production, staging hoặc workload tương tự. |
| Latency từng item | Một item cần được hiển thị/commit trong bao lâu? | Phụ thuộc SLA cập nhật dữ liệu, không chỉ throughput toàn job. |
| Cost | Có thể dùng bao nhiêu CPU, RAM, DB connections và I/O? | Giới hạn tài nguyên và tác động tới hệ thống khác. |

**RPO không phải là `chunkSize`.** Với nguồn input bất biến được lưu bền và writer có thể chạy lại an toàn, một chunk chưa commit có thể phải xử lý lại nhưng không nhất thiết tạo **mất dữ liệu vĩnh viễn**. Ngược lại, một job gửi side effect ra ngoài trước khi lưu checkpoint có thể tạo trạng thái không rõ ràng ngay cả với chunk size bằng 1.

Trong vận hành, nên tách rõ:

- **Dữ liệu đã commit**: kết quả được hệ thống đích xác nhận bền vững.
- **Checkpoint đã persist**: vị trí/state mà reader/writer có thể sử dụng để chạy lại.
- **Dữ liệu đã xử lý trong RAM**: có thể mất khi process chết.
- **Side effect ngoài transaction**: có thể thành công dù metadata batch chưa ghi nhận.

Khi báo cáo throughput, phải chọn **tử số nhất quán**. `StepExecution.getReadCount()` là số item reader báo đã đọc, `getWriteCount()` phản ánh xử lý item của framework, còn số row thực tế được thay đổi bởi SQL tùy ý có thể khác. Với processor trả `null`, item bị filter; với retry/skip, work có thể lặp lại. Đừng gọi mọi count là “record đã commit”.

## 3. Spring Batch ghi trạng thái phục hồi ở đâu?

Spring Batch tách **công việc nghiệp vụ** khỏi **metadata thực thi**. Với JDBC `JobRepository`, metadata được lưu trong các bảng `BATCH_*`, ví dụ:

| Thành phần | Vai trò khi phục hồi |
|---|---|
| `JobInstance` | Định danh công việc logic bằng tên job và các identifying `JobParameters`. |
| `JobExecution` | Một lần thực thi của job; restart có thể tạo execution mới thuộc cùng instance. |
| `StepExecution` | Trạng thái step, thời gian, read/write/skip/commit/rollback counts. |
| `ExecutionContext` cấp step | State/checkpoint cho reader, writer hoặc step đang thực thi. |
| `ExecutionContext` cấp job | State chia sẻ ở phạm vi job, phụ thuộc thiết kế. |
| `ItemStream` | Hợp đồng `open`, `update`, `close` để khôi phục trạng thái của thành phần đọc/ghi có state. |

```text
JobInstance(batchId=2026-11-16)
       |
       +-- JobExecution 501 -> FAILED
       |       |
       |       +-- StepExecution 801 -> FAILED, checkpoint A
       |
       +-- JobExecution 502 -> COMPLETED
               |
               +-- StepExecution 809 -> COMPLETED, resume từ A
```

**Cùng `JobInstance` không có nghĩa cùng `JobExecution`.** Khi khởi động lại sau một failure có kiểm soát, framework có thể tạo một execution mới, xét những step đã hoàn thành và mở lại những step cần chạy. `ExecutionContext` chỉ hữu ích nếu được lưu đúng và reader/writer biết sử dụng nó. Một code tự giữ offset trong biến local sẽ mất offset khi JVM chết.

Schema metadata `BATCH_*` không thay thế các business tables, outbox hoặc hàng đợi đảm bảo chống trùng. Một job có metadata hoàn chỉnh nhưng writer không idempotent vẫn có nguy cơ duplicate sau restart.

## 4. Chunk, transaction và checkpoint tạo ra đánh đổi gì?

Với **chunk-oriented step**, Spring Batch đọc và xử lý các item, gom thành chunk, đưa đến writer rồi commit theo `PlatformTransactionManager`. Ví dụ `chunk(100)`:

```text
Transaction / Chunk #1
  read + process items 1..100
  writer.write(chunk)
  ItemStream.update(executionContext)
  commit

Transaction / Chunk #2
  read + process items 101..200
  writer.write(chunk)
  ItemStream.update(executionContext)
  commit

Transaction / Chunk #3
  read + process items 201..300
  writer.write(chunk)
  -> crash trước commit

Sau crash: kết quả #1 và #2 đã commit; #3 có thể cần replay.
```

Trong mô hình thông thường, framework cập nhật trạng thái `ItemStream` trước commit để checkpoint có thể đi cùng ranh giới transaction phù hợp. **Đảm bảo atomic giữa metadata và dữ liệu nghiệp vụ phụ thuộc cấu hình transaction và các tài nguyên tham gia**. Không được mặc nhiên cho rằng dùng hai database khác nhau hoặc một writer gọi HTTP sẽ được rollback cùng `ExecutionContext`.

### 4.1. Chunk nhỏ

Ưu điểm:

- Ít item đang xử lý dở trong một transaction; thường ít work cần replay hơn khi crash.
- Giữ row locks trong thời gian ngắn hơn với workload ghi database.
- Giảm footprint của các item được gom trong chunk.
- Item đã hoàn thành có thể commit sớm hơn, phù hợp yêu cầu latency thấp.
- Khi có lỗi ở cuối chunk, phạm vi rollback và xử lý lại thường nhỏ hơn.

Hạn chế:

- Mỗi item/nhóm rất nhỏ phải trả overhead mở/commit transaction nhiều lần.
- JDBC batch writer khó tận dụng batching khi chunk size quá nhỏ.
- Nhiều lần cập nhật checkpoint/metadata, listener callbacks và DB log flush hơn.
- Với hàng triệu item, log theo từng chunk cũng có thể trở thành bottleneck.

### 4.2. Chunk lớn

Ưu điểm:

- Phân bổ transaction overhead cho nhiều item hơn, thường cải thiện throughput khi chi phí commit cố định đáng kể.
- Cho writer cơ hội gom câu lệnh JDBC hoặc bulk I/O.
- Ít checkpoint/commit hơn trên cùng lượng input.

Hạn chế:

- Transaction dài, lock giữ lâu và khả năng deadlock/timeout có thể tăng.
- Nhiều item/intermediate object nằm trong bộ nhớ; heap/GC có thể tăng.
- Khi rollback hoặc JVM crash, phần chunk chưa commit cần xử lý lại.
- Side effect ngoài transaction có nguy cơ bị phát lại nhiều hơn nếu không có idempotency.
- Thời gian từ khi nhận item đến khi dữ liệu được commit có thể dài hơn.

**Một chunk lớn không có nghĩa writer tự giảm số API requests.** Nếu writer vẫn gọi HTTP một lần cho mỗi item, chỉ số transaction của Spring Batch thay đổi nhưng số request HTTP gần như không đổi. Cần xem writer có thực sự hỗ trợ bulk operation không.

## 5. Mô hình định lượng: throughput và chi phí replay

Với một workload tuần tự và giả định chi phí mỗi item gần ổn định, ta có thể dùng mô hình ước lượng:

\[
T_{run}(N,C) \approx N\,t_{item}
  + \left\lceil\frac{N}{C}\right\rceil t_{commit}
  + T_{startup} + T_{other}
\]

Trong đó:

- `N` là số item cần xử lý.
- `C` là chunk size.
- `t_item` là chi phí trung bình cho một item (đọc, xử lý, ghi theo giả định mô hình).
- `t_commit` là overhead tương đối cố định mỗi chunk (transaction, checkpoint, commit, một phần round-trip).
- `T_other` bao gồm thời gian không được tách ở trên.

Khi **chunk tăng**, số commit xấp xỉ `ceil(N/C)` giảm. Tuy nhiên công thức chỉ mang tính trực giác: `t_item` và `t_commit` có thể thay đổi theo batch size, kích thước SQL, cache, network, lock, concurrency và database. Chúng **không phải hằng số thật** cho mọi giá trị C.

### 5.1. Ví dụ 1 triệu item

Giả sử *để minh họa*, `t_item = 0,3 ms`, overhead cố định mỗi chunk `t_commit = 3 ms` và chưa tính các thành phần khác:

| Chunk size C | Số chunk ước lượng | Chi phí theo item | Overhead cố định | Tổng ước lượng |
|---|---:|---:|---:|---:|
| 1 | 1.000.000 | 300 giây | 3.000 giây | 3.300 giây |
| 10 | 100.000 | 300 giây | 300 giây | 600 giây |
| 100 | 10.000 | 300 giây | 30 giây | 330 giây |
| 500 | 2.000 | 300 giây | 6 giây | 306 giây |
| 2.000 | 500 | 300 giây | 1,5 giây | 301,5 giây |

Ở ví dụ này, tăng từ 1 lên 100 có lợi rất lớn; tăng từ 500 lên 2.000 chỉ cải thiện ít về mặt số học. Nếu size 2.000 làm tăng GC, lock waits hay rollback work, tổng thời gian thực tế còn có thể **chậm hơn** 500.

### 5.2. Mô hình work phải replay sau lỗi

Trong một transaction có `C` item, nếu crash xảy ra ở vị trí ngẫu nhiên phân bố tương đối đều trong lúc đang xử lý chunk, số item đã làm nhưng **chưa commit** có thể nằm từ 0 tới gần C. Một xấp xỉ trực giác là:

\[
E[\text{item cần replay cho một crash}] \approx \frac{C}{2}
\]

Giả định này **không phải bảo đảm hay thống kê của Spring Batch**. Nó chỉ hợp lý khi item có thời gian xử lý tương tự, crash không thiên lệch theo thời điểm commit và không có retry/side effect phức tạp. Với file cực lớn hoặc một item xử lý rất lâu, phân bố mất work có thể khác hoàn toàn.

| Chunk size | Work chưa commit có thể cần replay (giới hạn gần đúng) | Trung bình giả định crash đều trong chunk |
|---|---:|---:|
| 10 | Đến khoảng 10 item | Khoảng 5 item |
| 100 | Đến khoảng 100 item | Khoảng 50 item |
| 500 | Đến khoảng 500 item | Khoảng 250 item |
| 2.000 | Đến khoảng 2.000 item | Khoảng 1.000 item |

Với một job chỉ cập nhật cùng database transactional, replay có thể chủ yếu là **tốn thời gian**. Với writer phát external payment, message hoặc file, replay có thể tạo **rủi ro nghiệp vụ** nếu những tác dụng phụ đó đã xảy ra trước khi checkpoint bền vững được ghi. Khi đó ưu tiên chống trùng cao hơn lợi ích giảm vài giây commit.

### 5.3. Đánh đổi phải xét cả xác suất lỗi

Một hàm mục tiêu khái niệm là:

\[
E[T_{end\text{-}to\text{-}end}] \approx T_{run}
  + E[\text{số failure}]\times
    (T_{detect} + T_{recover} + T_{replay})
\]

Không nên thay `E[số failure]` bằng một số đoán. Với job chạy lâu, crash có thể đến từ OOM, deadlock, node eviction, remote API instability hoặc deploy; tần suất thay đổi theo chunk size và concurrency. **Chunk lớn có thể làm xác suất lỗi tăng** nếu dẫn đến OOM/timeout, nên throughput đo trong happy path chưa đủ để tối ưu expected completion time.

## 6. Xây dựng vùng chunk size phù hợp

Với một job mới, có thể bắt đầu bằng các mốc thử `10, 50, 100, 250, 500, 1.000` tùy kích thước item, DB và SLA. Đây chỉ là **khoảng benchmark gợi ý**, không phải quy tắc Spring Batch.

Một decision table:

| Điều kiện workload | Ưu tiên ban đầu | Điều cần đo trước khi chọn |
|---|---|---|
| Item nhỏ, JDBC batch writer, một database transactional | Thử chunk vừa/lớn để giảm commit overhead | DB round-trip, throughput, lock wait, checkpoint cost. |
| Item lớn, nhiều dữ liệu trung gian | Thử chunk vừa/nhỏ | Heap live set, GC, OOM risk. |
| Lỗi dữ liệu/rate retry cao | Tránh chunk quá lớn ngay lập tức | Rollback, retry calls, replay work, failure rate. |
| Writer gửi external API từng item | Ưu tiên idempotency và API batching thật | Duplicate behavior, API latency/rate limit, failure ambiguity. |
| SLA latency từng item thấp | Commit thường xuyên hơn | End-to-end latency và DB load. |
| Chạy trên DB đang phục vụ giao dịch online | Tránh transaction khóa dài | p95/p99 lock wait, impact lên OLTP. |
| Nguồn file không đảm bảo bất biến | Bảo vệ snapshot/input trước khi tuning | Checksum/object version, restart test. |
| Partitioning nhiều worker | Tối ưu cùng concurrency và DB capacity | Tổng connections, contention, memory và partition skew. |

**Cách quyết định:** chọn mức size đáp ứng throughput yêu cầu và cho **chi phí recovery chấp nhận được**; không nhất thiết là size nhanh nhất ở một lần benchmark. Nếu size 500 xử lý 10.000 item/s và size 2.000 xử lý 10.100 item/s nhưng làm rollback/restart khó hơn, size 500 có thể là lựa chọn vận hành tốt hơn.

## 7. Cấu hình commit interval trong Spring Batch 5.x

Ví dụ Java 17+, Spring Batch 5.2.x và Spring Boot 3.x, dùng các bean reader/processor/writer do ứng dụng định nghĩa:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class OrderBatchStepConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, NormalizedOrder> orderProcessor,
            ItemWriter<NormalizedOrder> orderWriter,
            @Value("${app.batch.import-orders.chunk-size:250}") int chunkSize) {

        if (chunkSize < 1) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, NormalizedOrder>chunk(chunkSize, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

Ví dụ giả định `Order`, `NormalizedOrder` và các bean xử lý có sẵn, dùng đúng datasource/transaction manager. `app.batch.import-orders.chunk-size` là **property do ứng dụng tự định nghĩa**, được truyền vào builder. Đặt trong `application.yml`:

```yaml
app:
  batch:
    import-orders:
      chunk-size: 250
```

Với cấu hình này, tăng số commit không tự làm `ItemReader` fetch nhiều row hơn hay thay đổi batch SQL của writer. Fetch size, page size, JDBC batching, connection pool và thread pool là những tầng điều chỉnh khác nhau.

### 7.1. Đừng thay size giữa một execution đang chạy

Tùy thiết kế, việc đổi cấu hình khi rollout hoặc restart có thể ảnh hưởng checkpoint/replay. Hãy ghi lại chunk size đã dùng cho mỗi execution trong thông tin vận hành (audit/job metadata được phép lưu) và có chính sách thay đổi rõ ràng. Với một restart quan trọng, cần kiểm thử việc dùng cùng cấu hình hoặc việc thay đổi có chủ đích; không giả định mọi reader/writer hỗ trợ đổi `chunkSize` giữa hai lần chạy mà không có tác dụng phụ.

### 7.2. `commitInterval` khác `fetchSize` và `pageSize`

```text
chunkSize             -> số item gom theo transaction của step
JdbcCursor.fetchSize  -> hint fetch hàng từ driver/database
JdbcPaging.pageSize   -> số row trong một trang reader
JDBC batch size       -> số câu lệnh writer gom cho executeBatch
partition gridSize    -> số partition/worker task theo cấu hình
```

Ví dụ reader có `pageSize=1.000` và step dùng `chunk(250)`: một trang reader có thể phục vụ nhiều chunk. Cấu hình này hợp lệ nếu sort key ổn định, reader hỗ trợ state/restart và transaction manager đúng. Không ép mọi thông số bằng nhau chỉ vì đều có chữ *size*.

## 8. Checkpoint đúng: `ItemStream` và `ExecutionContext`

Một reader/writer có state cần triển khai/tuân theo hợp đồng `ItemStream`:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Đây là chữ ký đã **lược bỏ throws** để diễn giải; API thật có `ItemStreamException` tương ứng. `open` khôi phục trạng thái, `update` đưa state vào context và `close` giải phóng tài nguyên. Với step chuẩn, Spring Batch quản lý lifecycle này khi stream được đăng ký đúng.

Ví dụ trạng thái logical sau chunk đã commit:

```text
input file revision: sha256:abc... (bất biến)
reader checkpoint: 5000
business rows committed: 5000 (giả định không filter/skip)

Reader đã đọc thêm đến vị trí 5200 khi JVM crash.

Restart: mở lại checkpoint 5000, xử lý lại phần chưa commit.
```

**Checkpoint chỉ có nghĩa nếu nguồn input có thể tái hiện.** Một file bị ghi đè, dữ liệu paging đổi thứ tự hoặc query dựa vào cột không duy nhất có thể làm offset cũ trỏ sang bản ghi khác. Khi đó chunk nhỏ vẫn không cứu được tính đúng đắn.

### 8.1. Reader file

Với `FlatFileItemReader`, cần cân nhắc:

- Đặt `name` duy nhất cho reader/stream trong cùng step để tránh trùng key trong context.
- `saveState=true` nếu cần lưu tiến độ và implementation hỗ trợ.
- Không thay file giữa các lần restart; lưu checksum/object version hoặc copy vào staging immutable.
- Giữ encoding, delimiter, schema version và quy tắc lọc dòng ổn định.
- Nếu reader được tạo trong `@StepScope`, bảo đảm các identifying `JobParameters` trỏ tới đúng phiên bản file.

### 8.2. JDBC paging/cursor

Với reader phân trang, sort key duy nhất và ổn định giúp tránh bị thiếu/trùng record khi dataset thay đổi. Nếu nguồn đang bị các service khác ghi thêm/sửa liên tục, cần một snapshot, cutoff ID hoặc trạng thái claim/lease đã thiết kế. `pageSize` lớn hay chunk nhỏ không tự đảm bảo snapshot consistency.

Với cursor reader, khả năng giữ cursor/connection phụ thuộc transaction isolation và driver. Nếu process chết, cursor trong RAM biến mất; restart cần mở lại nguồn và sử dụng cơ chế state/reposition của reader. Không dựa vào cursor còn sống trên database như checkpoint bền vững.

### 8.3. Delegate streams

Một `CompositeItemWriter` hoặc custom reader có `ItemStream` delegate bên trong có thể cần đăng ký delegate với step qua `.stream(delegate)` nếu framework không tự thấy được stream nested. Nếu stream không được mở/cập nhật, `ExecutionContext` có thể thiếu state cần cho restart dù chunk đã commit.

### 8.4. Stateless và stateful

Một processor thuần hàm `transform(input) -> output` dễ chạy lại vì không giữ state giữa các item. Processor dùng `AtomicLong`, cache thay đổi hoặc thao tác external side effect theo mỗi item có thể tạo state khó khôi phục. Khi buộc phải stateful, cần xác định cách persist và khôi phục state, đồng thời xử lý callback bị gọi lại do retry/rollback.

## 9. Transaction boundaries: đúng nơi commit quan trọng hơn size lớn

Một mô hình đơn giản dùng **cùng JDBC datasource và transaction manager**:

```text
Reader -> Processor -> JDBC Writer
               |         |
               +---- Transaction ----+
               |                     |
          business DB changes   checkpoint updates
               +---------- commit ---+
```

Khi tất cả resource được quản lý phù hợp trong một transaction, rollback của chunk có thể đưa business DB và checkpoint trở về trạng thái trước commit. Tuy nhiên, việc `JobRepository` dùng cùng datasource không tự được bảo đảm chỉ bằng tên bean; cần kiểm tra thiết kế transaction, connection và repository thực sự.

### 9.1. Hai datasource khác nhau

Nếu writer ghi vào `businessDb`, còn metadata nằm trong `batchMetaDb`, một local transaction manager thông thường không tự làm hai transaction commit atomically. Có cửa sổ:

```text
businessDb commit thành công
           |
           X  process crash
           |
batchMetaDb chưa lưu checkpoint mới
```

Khi restart, reader có thể replay cùng item dù business rows đã được ghi. Phương án an toàn thường cần **idempotent writer, unique business keys hoặc reconciliation**, thay vì giả định metadata và business DB luôn đồng bộ. Dùng distributed transaction/XA nếu thật sự cần cũng có chi phí, yêu cầu vận hành và tình huống failure riêng, nên cần đánh giá kiến trúc chứ không chỉ bật một property.

### 9.2. File, object storage, message và API ngoài

Một JDBC transaction không rollback được file đã upload, email đã gửi, HTTP payment đã thực hiện hoặc message mà hệ thống đích đã nhận. Ví dụ:

```text
1. Processor nhận order-42
2. Writer gọi POST /payments với order-42
3. API trả thành công; remote side effect đã tồn tại
4. JVM chết trước khi checkpoint được commit
5. Restart đọc lại order-42
6. API bị gọi lại -> nguy cơ tác động hai lần
```

Trong tình huống này, **chunk size bằng 1 vẫn không giải quyết được**. Cần idempotency key ổn định mà service đích thực sự hỗ trợ, outbox hoặc cơ chế xác nhận/đối soát kết quả trước khi phát lại.

### 9.3. Idempotent output là nền tảng của phục hồi

Ví dụ PostgreSQL dùng khóa duy nhất theo (`business_date`, `order_id`):

```sql
CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);

INSERT INTO imported_order (business_date, order_id, amount)
VALUES (:businessDate, :orderId, :amount)
ON CONFLICT (business_date, order_id)
DO NOTHING;
```

`DO NOTHING` chỉ phù hợp **nếu business rule chấp nhận một record đã tồn tại là xử lý xong**. Nếu cùng khóa nhưng `amount` khác là xung đột dữ liệu cần điều tra, đừng nuốt lỗi bằng `DO NOTHING`; hãy so sánh dữ liệu, dùng update có điều kiện hoặc báo lỗi đối soát. Một unique constraint chống trùng insert, nhưng không tự giải quyết mọi hình thức idempotency của workflow.

### 9.4. Outbox và idempotent consumer

Với nhu cầu xuất message sau khi ghi database, có thể dùng transactional outbox:

```text
Trong cùng business transaction:
  - Ghi kết quả nghiệp vụ
  - Ghi outbox(eventId ổn định, payload được phép)
Commit

Publisher riêng:
  - Đọc outbox, phát message
  - Đánh dấu đã gửi theo quy tắc an toàn

Consumer:
  - Dedupe theo eventId / idempotent processing
```

Outbox giảm cửa sổ không nhất quán giữa business DB và sự kiện cần phát, nhưng publisher có thể gửi lại khi crash sau publish trước khi đánh dấu. **Consumer vẫn cần idempotency**; không nên hứa exactly-once tuyệt đối chỉ bằng outbox.

## 10. Retry, skip và rollback: throughput happy path chưa đủ

Spring Batch hỗ trợ fault-tolerant step, retry và skip ở các tình huống thích hợp. Khi chunk có lỗi, framework có thể rollback và xử lý lại một phần work. Chunk lớn làm phạm vi work bị ảnh hưởng rộng hơn, nhưng số lần retry thực tế còn phụ thuộc ngoại lệ, stateful retry và cơ chế writer.

Ví dụ cấu hình Spring Batch 5.x:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, NormalizedOrder>chunk(250, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Đây là mẫu phần thân cấu hình: `InvalidOrderException` là class ứng dụng; `TransientDataAccessException` thuộc Spring DAO. Trong project thật cần phân loại exception chính xác và kiểm tra `skip/retry` ở từng giai đoạn reader/processor/writer, không sao chép mặc định. Retry sai với lỗi permanent có thể chỉ tốn thêm thời gian mà không có khả năng thành công.

| Chính sách | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Retry lỗi tạm thời | Không fail cả job vì lỗi ngắn hạn | Có thể kéo dài thời gian, replay work, tạo áp lực lên dịch vụ. |
| Exponential backoff | Giảm retry storm khi external service quá tải | Tăng elapsed time/recovery latency. |
| Skip lỗi dữ liệu cá biệt | Tiếp tục xử lý dữ liệu hợp lệ | Có thể vi phạm yêu cầu completeness nếu skip policy sai. |
| Fail fast với lỗi schema/input không hợp lệ | Bảo vệ chất lượng dữ liệu | Cần sửa input/contract trước khi tiếp tục. |
| Quarantine item lỗi | Giữ bằng chứng và phục vụ đối soát | Cần storage/transaction/idempotency riêng. |

**Skip limit lớn không đồng nghĩa recoverability tốt hơn.** Nếu file có schema sai, việc skip hàng triệu item rồi `COMPLETED` là thất bại về dữ liệu dù batch framework thành công. Cần phân biệt lỗi hợp đồng của toàn input với lỗi record riêng lẻ.

### 10.1. Vì sao phải benchmark cả ca lỗi?

Một job có 0% lỗi có thể chạy rất nhanh với chunk 2.000. Nhưng khi 1% records cần retry/skip, chunk lớn có thể rollback hoặc thực hiện thêm nhiều call, làm throughput giảm mạnh. Khi chọn chunk size, hãy kiểm thử cả dữ liệu sạch và dữ liệu lỗi đại diện.

## 11. Restart semantics và thiết kế job flow

Spring Batch thường bỏ qua step đã `COMPLETED` khi restart cùng `JobInstance`, trừ khi cấu hình `allowStartIfComplete(true)`. Những step dở dang cần được phép chạy lại và có state phù hợp.

Ví dụ với Spring Batch 5.x:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateInputStep,
              Step importOrdersStep,
              Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateInputStep)
            .next(importOrdersStep)
            .next(publishReportStep)
            .build();
}
```

| Step | Chính sách thường xét | Lý do |
|---|---|---|
| `validateInputStep` | Có thể `allowStartIfComplete(true)` nếu cần xác minh input immutable mỗi lần restart | Kiểm tra input không đổi, schema/version đúng. |
| `importOrdersStep` | Restartable, reader/writer có checkpoint và idempotency | Tiếp tục phần chưa hoàn thành. |
| `publishReportStep` | Thường chỉ chạy một lần khi kết quả sẵn sàng; publish phải idempotent | Tránh phát report/tệp hai lần khi restart sau crash. |

`startLimit(n)` giới hạn số lần step được phép bắt đầu; một giới hạn quá thấp có thể làm restart bị từ chối trong khi dữ liệu thực tế vẫn có thể phục hồi. `allowStartIfComplete(true)` cần được chọn có chủ đích: nó làm step đã hoàn thành **chạy lại** trong lần restart, nên không phù hợp với step có side effect không idempotent.

### 11.1. `JobParameters` phải phản ánh một công việc logic

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("inputRevision", "sha256:example-fixed-revision", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

Chuỗi revision ở trên chỉ minh họa. Cùng identifying parameters tương ứng cùng job instance logic. Nếu thêm `run.id` mới mỗi khi lỗi chỉ để vượt `JobExecutionAlreadyRunningException` hoặc `JobInstanceAlreadyCompleteException`, có thể tạo instance mới và bỏ qua checkpoint, làm tăng nguy cơ nhập trùng.

**Restart không giống re-run từ đầu.** Một job đã hoàn tất cần xử lý lại toàn bộ input thường phải có quy trình reprocessing riêng: version kết quả, cleanup/reconciliation, idempotency và lý do nghiệp vụ. Không đánh đồng reprocessing với restart của một execution bị lỗi.

## 12. Concurrency: thêm worker không làm recovery tự tốt lên

Khi một step đơn luồng không đủ throughput, có thể cân nhắc multi-threaded steps, partitioning hoặc remote chunking. Mỗi hướng thay đổi phạm vi state và rủi ro phục hồi.

### 12.1. Multi-threaded step

Một step có thể thực thi nhiều chunk đồng thời, nhưng reader/writer và các delegate phải phù hợp với concurrency. Một `ItemReader` có mutable cursor/state không tự an toàn khi nhiều thread gọi `read()` cùng lúc. `SynchronizedItemStreamReader` có thể đồng bộ việc đọc trong một số trường hợp, nhưng đồng bộ truy cập không tự bảo đảm restart semantics trong xử lý song song; khi item được xử lý/commit lệch thứ tự, checkpoint có thể không phản ánh chính xác work đã hoàn thành.

**Đừng dùng chung một counter, buffer hoặc MDC không tách theo execution** cho các step chạy đồng thời. Nếu cần state, hãy xác định rõ phạm vi bean và transaction.

### 12.2. Partitioning

Partitioning chia input thành những vùng độc lập. Mỗi worker thường có `StepExecution` và `ExecutionContext` riêng; khi một partition thất bại, có thể xét chạy lại phần tương ứng theo trạng thái repository.

```text
Manager step
    |
    +-- partition-0: IDs 1..100000     -> COMPLETED
    +-- partition-1: IDs 100001..200000 -> FAILED
    +-- partition-2: IDs 200001..300000 -> COMPLETED
```

Để partitioning thực sự tăng recoverability:

- Mỗi partition phải xử lý tập input **không trùng** và được xác định ổn định trên restart.
- Input phân vùng phải bất biến hoặc có snapshot/cutoff rõ.
- Worker writer cần idempotent, đặc biệt khi message delivery hoặc worker failure dẫn đến thực hiện lại.
- Tránh partition quá lớn gây replay rộng; tránh quá nhiều partition nhỏ làm overhead điều phối tăng.
- Theo dõi tổng throughput cùng database connection pool, lock contention và memory của tất cả workers.

### 12.3. Remote chunking

Remote chunking chuyển công việc qua messaging cho worker ở process khác. Nó có thể tăng throughput nhưng thêm ranh giới network, message acknowledgement và các tình huống gửi/nhận lại. Cần xem delivery semantics của broker, idempotency worker và điều kiện commit checkpoint. Không gọi remote chunking là exactly-once chỉ vì Spring Batch quản lý `StepExecution`.

### 12.4. Amdahl và bottleneck chia sẻ

Nếu 80% thời gian nằm ở một database writer dùng chung và chỉ 20% nằm ở processor có thể song song hóa, tăng số worker có thể sớm bão hòa. Tăng concurrency đồng thời với chunk size lớn có thể làm lock và DB connection starvation tăng, khiến cả recovery lẫn throughput xấu đi.

Một kế hoạch đo tốt thay đổi **từng nhóm thông số**: trước tiên tối ưu commit interval với concurrency cố định, sau đó thử số worker/partition, rồi xác nhận kết quả ở tải tổng gần production.

## 13. Hệ thống có nhiều tác dụng phụ cần một recovery protocol

Giả sử một job thực hiện:

```text
read order -> normalize -> update database
                           -> send Kafka event
                           -> upload report to storage
```

Không nên gộp cả ba side effects này trong một item writer rồi giả định chunk transaction sẽ rollback tất cả. Một kiến trúc an toàn hơn có thể tách:

1. **Ingest/stage** vào database transactional với unique business key.
2. **Verify/validate** số record, schema, đối soát totals; không publish khi dữ liệu chưa đạt tiêu chí.
3. **Publish** qua outbox hoặc một bước có idempotent key/atomic rename/object version phù hợp.
4. **Reconcile** kết quả và ghi trạng thái publish bền vững.

Phân tách này có thể làm throughput của một job nhìn bề ngoài thấp hơn vì thêm bước kiểm tra, nhưng **giảm chi phí xử lý sự cố và lỗi dữ liệu nghiêm trọng**, tăng khả năng hoàn tất đúng SLA tổng thể.

### 13.1. Không chắc kết quả commit khi lỗi mạng

Trong một số tình huống, database đã commit nhưng connection bị ngắt trước khi ứng dụng nhận phản hồi. Nếu framework coi chunk thất bại và retry, writer có thể nhận cùng item lần nữa. Điều này càng đòi hỏi unique keys/idempotency/reconciliation; không thể suy ra “không nhận được ACK nghĩa là DB chưa commit”.

### 13.2. Restart sau kill cưỡng bức

Với một exception Java được xử lý bình thường, Spring Batch thường có cơ hội ghi `BatchStatus.FAILED`. Khi JVM bị `SIGKILL`/OOM kill, repository có thể còn `STARTED`; không được gọi restart một cách mù quáng. Cần xác minh process/worker cũ đã chết, side effects và DB session ổn định, rồi dùng **quy trình recovery phù hợp phiên bản**.

Trong Spring Batch 6.x, `JobOperator.recover(JobExecution)` có thể phục hồi một execution kẹt `STARTED` sau abrupt shutdown bằng cách chuyển sang điều kiện cho restart. Với Spring Batch 5.x, quản trị execution kẹt yêu cầu thao tác metadata có kiểm soát theo tài liệu/phiên bản. Không đổi một cột `STATUS` bằng SQL tùy tiện vì `JobExecution`, `StepExecution`, exit status, optimistic locking version và context có liên hệ với nhau.

Một restart tự động chỉ nên chạy khi có **đủ bằng chứng** execution không còn sống và writer/idempotency đảm bảo an toàn. Thấy `LAST_UPDATED` cũ không tự chứng minh job đã chết; một tasklet dài có thể không ghi metadata liên tục.

## 14. Gracious shutdown, watchdog và khả năng khôi phục

Khi triển khai trên Kubernetes hoặc host orchestration, `SIGTERM` là cơ hội cho ứng dụng dừng có kiểm soát; `SIGKILL` không cho JVM chạy shutdown hooks. `JobOperator.stop(...)` là **yêu cầu dừng hợp tác**, không đồng nghĩa job đã chuyển thành `STOPPED` ngay lập tức.

Ví dụ cấu hình pod/container có grace period:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: import-orders
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 120
      containers:
        - name: batch
          image: example/import-orders:1.0
          resources:
            requests:
              memory: 512Mi
            limits:
              memory: 1Gi
```

Các giá trị là ví dụ. Grace period chỉ tạo **cơ hội** cleanup, không bảo đảm một chunk đang chờ external API 10 phút có thể kết thúc trong 120 giây. Nếu hết thời hạn, process có thể bị kill. Hãy đặt timeout hợp lý cho I/O, giữ metadata ở database bền, dùng readiness/termination hooks đúng và kiểm tra quy trình stop trên môi trường test.

**Kubernetes Job retry không đồng nghĩa Spring Batch job restart.** Pod mới có thể khởi động với cùng identifying parameters trong khi repository còn `STARTED`. Nếu dùng ID ngẫu nhiên để chạy một instance mới, kết quả có thể bị xử lý trùng. Cần thiết kế điều phối/scheduler và recovery ở cả hai tầng.

## 15. Chọn chiến lược theo loại workload

### 15.1. Ingest chỉ dùng một database transactional

Chiến lược thường hợp lý:

- Reader ổn định và `ItemStream` có state.
- Writer JDBC batch với unique business keys.
- Chunk vừa/lớn nếu đo chứng minh commit overhead đáng kể.
- Repository/transaction được kiểm tra nhất quán.
- Restart test sau khi có một số chunk commit.

Ở đây có thể ưu tiên throughput hơn vì replay work tương đối dễ và side effects chủ yếu là transactional.

### 15.2. Thanh toán hoặc thao tác irreversible

Chiến lược thường hợp lý:

- Idempotency key của API đích hoặc ledger theo business key.
- Không gọi side effect irreversible trực tiếp trong một transaction dài mà không có protocol xác nhận.
- Transaction/outbox/claim table với trạng thái có thể đối soát.
- Retry có backoff và trạng thái pending/unknown rõ ràng.
- Chunk size nhỏ/vừa có thể giúp giảm blast radius nhưng **không thay thế idempotency**.

Ở đây ưu tiên tính đúng đắn và phục hồi an toàn hơn một mức tăng throughput nhỏ.

### 15.3. Xuất file báo cáo cực lớn

Chiến lược thường hợp lý:

- Ghi file tạm hoặc nhiều phần output có định danh ổn định.
- Checkpoint/manifest theo segment, và tránh publish một file dở dang.
- Khi kết quả hoàn tất và được xác minh, publish qua rename hoặc object version theo khả năng atomic của storage.
- Chunk/segment size cân bằng memory, throughput I/O và replay cost.

File append có thể không rollback cùng database transaction; cần quy định truncate, resume hoặc regenerate phần output khi restart. Không tự giả định file `append` là exactly-once.

### 15.4. Backfill lịch sử

Một backfill nhiều tháng dữ liệu có thể phân vùng theo ngày hoặc dải ID, mỗi partition có output/idempotency độc lập. Phân vùng nhỏ vừa giúp chạy song song vừa dễ resume theo dải thất bại. Tuy nhiên cần bảo đảm không chạy cùng business date ở hai worker và dữ liệu nguồn được snapshot ổn định.

### 15.5. ETL gần real-time

Nếu SLA yêu cầu dữ liệu xuất hiện nhanh sau khi nhận, commit quá thưa có thể vi phạm latency dù throughput cao. Có thể chọn chunk nhỏ hơn hoặc completion policy kết hợp số item/thời gian; benchmark cả p95/p99 latency thay vì chỉ item/s.

## 16. Benchmark phải bao gồm recovery, không chỉ happy path

### 16.1. Đo thông số nào?

| Nhóm | Metric/quan sát | Mục đích |
|---|---|---|
| Throughput | Committed business rows/s, elapsed time, job duration | Đánh giá tốc độ xử lý thực tế. |
| Batch counters | `readCount`, `writeCount`, `filterCount`, `skipCount` | So sánh khối lượng work và chất lượng dữ liệu. |
| Transaction | `commitCount`, `rollbackCount`, transaction duration | Quan sát overhead và retry/rollback. |
| Resource | Heap, GC pause, CPU, connection pool, I/O | Phát hiện saturation khi chunk/concurrency tăng. |
| Database | Lock wait, deadlock, query latency, log/fsync pressure | Đo ảnh hưởng lên DB và các ứng dụng chia sẻ. |
| Recovery | Detection time, restart delay, replay count, time to catch up | Đánh giá RTO trong tình huống lỗi. |
| Correctness | Missing/duplicate records, wrong values, external side effects | Bảo đảm performance không đổi semantics. |
| Observability | Sự kiện log, metrics, correlation IDs | Đủ bằng chứng điều tra mà không log từng item. |

Trong Spring Batch 5.x, có thể đọc thống kê từ `StepExecution` khi job kết thúc:

```java
for (StepExecution step : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s status=%s read=%d write=%d "
                    + "commits=%d rollbacks=%d skips=%d%n",
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getSkipCount());
}
```

Đoạn minh họa giả định đã có `JobExecution jobExecution` và import `StepExecution`. Không lấy object còn đang chạy của một `JobLauncher` bất đồng bộ rồi suy ra số liệu cuối cùng; hãy chờ completion hoặc đọc lại repository.

### 16.2. Ma trận benchmark đề xuất

Thử nhiều giá trị chunk size với cùng workload, sau đó lặp lại ở các failure modes:

| Kịch bản | Điều quan sát | Kết luận cần rút ra |
|---|---|---|
| Happy path, một worker | Throughput, commit overhead | Size nào bão hòa lợi ích giảm commit? |
| Có lỗi dữ liệu 1% | Retry/skip/rollback counts, elapsed time | Size lớn có làm tăng work lặp lại đáng kể không? |
| DB transient failure | Thời gian hồi phục, backoff, deadlocks | Retry policy có gây quá tải hoặc phản ứng chậm? |
| Kill giữa chunk | Phạm vi replay và dữ liệu đã commit | Checkpoint có đúng và output có idempotent không? |
| Gửi event/API rồi crash | Tính chống trùng của side effect | Có kết quả ambiguous khiến phát lặp không? |
| Chạy 4–8 partitions | Tổng throughput, DB locks, RAM | Concurrency có thực sự tăng khả năng xử lý hay chỉ tăng contention? |

Giữ nguyên input, schema/index, JVM resources, transaction manager, connection pool và logger level khi so sánh **riêng chunk size**. Chạy nhiều lượt, có warm-up và tách kết quả benchmark khỏi các thay đổi khác như thêm index hoặc chuyển driver. Với batch rất lớn, một bài performance test trên vài chục item không phản ánh chi phí commit theo quy mô thật.

### 16.3. Chọn theo SLA thay vì điểm số đơn giản

Có thể xây một bảng quyết định:

| Phương án | Throughput đo được | Replay sau crash | Lock/heap | Đánh giá vận hành |
|---|---:|---|---|---|
| Chunk 50 | Thấp hơn | Nhỏ | Nhẹ | Phù hợp nếu latency/recovery là ưu tiên cao. |
| Chunk 250 | Tốt | Vừa | Chấp nhận được | Ứng viên cân bằng. |
| Chunk 1.000 | Tốt hơn một ít | Lớn | Có thể tăng | Chỉ chọn nếu lợi ích có ý nghĩa và đã test rollback/restart. |

Không đưa ra kết luận từ các nhãn trên; chúng là **khung so sánh**, kết quả thực tế cần đo ở môi trường phù hợp. Với một hệ thống thanh toán, một lỗi trùng giao dịch có thể nghiêm trọng hơn cả việc job chậm thêm vài phút.

## 17. Kiểm thử phục hồi trong Spring Batch

### 17.1. Integration test gây failure có kiểm soát

Để kiểm tra restart semantics, có thể dùng `@SpringBatchTest`, `@SpringBootTest`, `JobLauncherTestUtils`, datasource test bền trong vòng đời test và một processor/writer chủ động ném lỗi sau khi một số chunk đã commit.

Quy trình:

```text
1. Seed 1.000 records bất biến vào database test.
2. Launch job với businessDate cố định và chunk size 100.
3. Cho 2 chunk đầu thành công, chunk thứ 3 ném exception.
4. Xác minh JobExecution đầu FAILED, output đã commit đúng phần kỳ vọng.
5. Giữ nguyên JobRepository và StepExecutionContext.
6. Tắt cơ chế gây lỗi, restart cùng identifying JobParameters.
7. Xác minh JobExecution mới thuộc cùng JobInstance.
8. Đối soát 1.000 output, không trùng/thiếu record.
```

**Đừng xóa metadata giữa hai lần launch** nếu mục tiêu là test restart. Xóa metadata hoặc dùng identifying `run.id` mới biến bài test thành chạy một instance khác. Nếu dữ liệu có filter/skip, expected output phải tính theo business rule, không mặc định bằng `readCount`.

Ví dụ phần assertions (giả định job/launcher và fixture đã được cấu hình):

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("sourceRevision", "fixture-v1", true)
        .toJobParameters();

JobExecution failed = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, failed.getStatus());

failureSwitch.disableFailure(); // Thành phần giả lập lỗi của test.

JobExecution restarted = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
assertEquals(failed.getJobInstance().getInstanceId(),
             restarted.getJobInstance().getInstanceId());

// Bổ sung assertion DB thực tế: đúng số record, không duplicate.
```

Đây là **mẫu test ở cấp ý tưởng**: `failureSwitch` và job bean là thành phần do test tự cung cấp. Việc `launchJob(params)` ở lần thứ hai thực sự được phép restart phụ thuộc trạng thái lần trước và cấu hình JobRepository. Với trường hợp production dùng `JobOperator.restart(...)`, cần thêm test cho API điều hành và permission nếu đó là đường thực thi thật.

### 17.2. Crash test dùng process riêng

Exception được framework bắt không mô phỏng việc JVM bị `SIGKILL`. Một crash test thực tế cần:

- Chạy batch trong **process/container con** tách khỏi JVM JUnit runner.
- Dùng database test bền qua hai lần khởi động; H2 in-memory trong process chết thường không phù hợp.
- Đợi một số chunk commit, sau đó kill đúng process/container test bằng công cụ điều phối.
- Xác minh process cũ đã chết và metadata có thể vẫn kẹt `STARTED`.
- Phục hồi execution theo quy trình phù hợp Spring Batch 5.x/6.x.
- Restart cùng business identity và đối soát DB/file/API outputs.

Không chạy `Runtime.halt`, `System.exit` hoặc `kill -9` lên JVM chứa toàn bộ test suite; thao tác đó chấm dứt chính test runner. Với external side effects, cần test trường hợp success response bị mất sau khi bên nhận đã thực hiện.

### 17.3. Test replay và idempotency độc lập

Một unit/integration test có thể gọi writer **hai lần với cùng input**, rồi kiểm tra output cuối không nhân đôi. Đây là test quan trọng ngay cả khi chunk checkpoint hoạt động. Hãy thêm ca cùng business key nhưng payload khác để xem hệ thống có phát hiện xung đột hay chỉ âm thầm bỏ qua dữ liệu mới.

### 17.4. Test dữ liệu nguồn thay đổi

Để bảo vệ reader restart, chạy lần đầu rồi thay nội dung file hoặc thay đổi thứ tự các rows của input paging trước lần restart. Hệ thống cần từ chối input revision không khớp hoặc đảm bảo snapshot cũ vẫn còn. Nếu job tiếp tục từ offset cũ trên dữ liệu đã thay đổi, kết quả có thể thiếu/trùng dù metadata checkpoint chính xác.

## 18. Monitoring và runbook phục hồi

Một hệ thống thiết kế tốt phải giúp người vận hành phát hiện sớm và phục hồi an toàn, không chỉ cố gắng để job “ít khi fail”.

Nên quan sát:

| Tín hiệu | Ý nghĩa |
|---|---|
| `jobName`, `jobInstanceId`, `jobExecutionId`, `stepExecutionId` | Phân biệt các lần chạy và restart. |
| Step `BatchStatus` và `ExitStatus` | Biết trạng thái thực thi/nhánh flow. |
| Read/write/filter/skip counts | Nắm tiến độ và chất lượng dữ liệu. |
| Commit/rollback counts | Phát hiện transaction overhead, retry storm. |
| Last metadata update, heartbeat, worker liveness | Điều tra stuck execution sau crash. |
| Heap/GC, DB locks, pool waits, queue backlog | Phân biệt size quá lớn với bottleneck hạ tầng. |
| Duplicate/error counters của writer | Quan sát hiệu quả idempotency và dữ liệu bất thường. |
| Recovery time và số lần retry/restart | Kiểm chứng SLO/RTO thực tế. |

Khi gặp crash, runbook có thể theo thứ tự:

1. Xác minh không còn worker/process nào đang xử lý cùng input/partition.
2. Đọc `JobRepository` và kiểm tra `JobInstance`, executions, step statuses, checkpoint.
3. Đối soát dữ liệu đã commit và external side effects, xác định phần ambiguous.
4. Chặn lịch tự chạy trùng và chọn recovery action có kiểm soát.
5. Phục hồi metadata nếu kẹt ở trạng thái running sau kill, theo đúng version.
6. Restart **đúng instance** và theo dõi tới trạng thái cuối.
7. Đối soát dữ liệu, xử lý quarantine/duplicate nếu có; ghi nhận kết quả incident.

**Không dùng thời gian `LAST_UPDATED` quá cũ làm bằng chứng duy nhất để tự restart.** Một step xử lý chunk dài hoặc I/O bị treo có thể chưa commit/checkpoint nhưng process vẫn còn sống. Nên kết hợp heartbeat, liveness từ orchestration và xác minh owner thực sự.

## 19. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chunk size 1 gây throughput rất thấp | Commit/checkpoint theo item, không tận dụng JDBC batching | Benchmark size vừa, đo DB overhead và writer batch I/O. |
| Chunk tăng từ 250 lên 2.000 mà job không nhanh hơn | Lợi ích commit bão hòa, bottleneck ở processor/DB/network | Profile pipeline; chọn vùng ổn định thay vì size lớn nhất. |
| Size lớn làm OOM/GC lâu | Giữ quá nhiều item/intermediate objects | Giảm size, giảm allocations, theo dõi heap live set. |
| Job chậm khi nhiều workers cùng chạy | Lock contention, pool/database saturation | Tách benchmark concurrency, điều chỉnh partition và transaction. |
| Restart ghi trùng record | Writer không idempotent hoặc nguồn thay đổi | Unique business keys, immutable input, reconciliation. |
| API bị gọi hai lần sau lỗi mạng | Side effect thành công nhưng checkpoint chưa ghi | API idempotency key, outbox hoặc trạng thái đối soát. |
| Job FAILED nhưng không restart được | `preventRestart`, `startLimit`, state lỗi hoặc execution khác đang running | Kiểm tra cấu hình flow, trạng thái và ownership. |
| Process kill nhưng repository vẫn STARTED | Không có callback cleanup/metadata finalization | Xác minh process chết, thực hiện version-specific recovery. |
| Job được chạy lại thành instance mới thay vì resume | Tự thêm run.id/timestamp identifying để né lỗi | Giữ identifying business parameters và quy trình restart đúng. |
| FlatFile reader tiếp tục sai offset | File bị thay thế hoặc stream state không persist | Pin revision và dùng ItemStream/saveState đúng. |
| Step đã COMPLETED vẫn chạy lại và phát email lần hai | `allowStartIfComplete(true)` trên step có side effect | Đặt chính sách hợp lý hoặc làm publish idempotent. |
| Retry tăng failure pressure | Retry permanent errors hoặc backoff quá ngắn | Phân loại exception, exponential backoff, giới hạn retry. |
| Throughput nhìn cao nhưng dữ liệu thiếu | Đo readCount thay vì kết quả đã commit/đối soát | Định nghĩa numerator đúng và assert business output. |
| Test exception thành công nhưng kill test thất bại | Không thử crash giữa commit và checkpoint, hoặc ngoại tác ngoài DB | Thêm crash test process riêng với database bền. |
| Job tự restart khi không còn worker nhưng side effect vẫn chưa rõ | Thiếu kiểm tra liveness và reconciliation | Chặn automatic retry mù; phân tích trạng thái ambiguous. |

## 20. Khung quyết định kiến trúc

Khi thiết kế một job mới, có thể đặt các câu hỏi theo thứ tự:

1. **Phạm vi transaction:** Writer ghi vào một database, nhiều database hay service không transactional?
2. **Tính bất biến của input:** Có thể đọc lại cùng byte/row snapshot sau restart không?
3. **Tính idempotent của output:** Chạy cùng item hai lần có còn cho kết quả đúng không?
4. **Yêu cầu SLA:** Tối đa bao lâu job hoàn thành? Tối đa bao lâu sau failure được khôi phục?
5. **Chi phí commit:** Có phải transaction overhead đang là bottleneck đã đo được?
6. **Khả năng chịu replay:** Một chunk chưa commit có thể được đọc/ghi lại an toàn trong bao lâu?
7. **Bộ nhớ và database:** Size lớn có vượt heap, transaction timeout, lock budget hay JDBC limits không?
8. **Dữ liệu xấu:** Có retry/skip thường xuyên không? Có cần quarantine không?
9. **Concurrency:** Partition boundaries có ổn định và disjoint không? Worker chết có thể được chạy lại độc lập không?
10. **Vận hành:** Có runbook và crash test thật, hay chỉ có happy-path integration test?

Nếu **input không ổn định** hoặc **writer không idempotent**, hãy xử lý vấn đề correctness trước khi tối ưu chunk size và concurrency. Khi đã xác lập recovery protocol, mới nên tinh chỉnh size để tăng throughput trong giới hạn tài nguyên và RTO.

### 20.1. Gợi ý hướng chọn, không phải quy tắc cứng

```text
Writer có external side effects?
    |
    +-- Có -> Có idempotency/reconciliation chưa?
    |            |
    |            +-- Chưa -> Thiết kế lại boundary và output trước.
    |            +-- Rồi -> Benchmark size với failure scenarios.
    |
    +-- Không -> Input có thể replay chính xác?
                 |
                 +-- Không -> Snapshot/pin revision trước.
                 +-- Có -> Benchmark commit interval và writer batching.

Sau đó:
  - Đo throughput, locks, heap, error/retry, replay time.
  - Chọn vùng size tốt và kiểm tra restart bằng same JobInstance.
  - Kiểm tra toàn pipeline dưới tải/đồng thời thực tế.
```

## 21. Bài tập thực hành

### Bài 1 — Tính trade-off ở mô hình đơn giản

Một job đọc 2.000.000 item, chi phí item giả định 0,5 ms và commit overhead 5 ms/chunk. Tính `T_run` tương đối cho chunk size 1, 50, 200, 1.000; ước lượng số item phải replay khi crash giữa chunk theo mô hình `C/2`. Giải thích vì sao mô hình không xét GC/locking/retry và vì sao không nên chọn size lớn nhất chỉ từ kết quả này.

### Bài 2 — Benchmark JDBC writer

Tạo step đọc từ bảng staging, chuẩn hóa dữ liệu và ghi sang bảng output bằng `JdbcBatchItemWriter`. Thử các size 10, 100, 250, 500 với cùng 100.000 item, đo commit count, rows/s, heap, transaction waits và p95 chunk duration. Tạo bảng so sánh, chọn vùng size cân bằng và trình bày lý do.

### Bài 3 — Restart giữa chunk

Cho một step dùng chunk 250, gây lỗi ở chunk thứ ba sau khi hai chunk trước commit. Giữ `JobRepository` và `ExecutionContext`, restart cùng identifying parameters. Assert output không trùng, step được resume đúng và các business keys được ghi đầy đủ.

### Bài 4 — Side effect ngoài transaction

Viết một fake payment gateway trả thành công ở lần gọi đầu nhưng client nhận timeout. Restart/retry cùng input và quan sát nguy cơ gửi lệnh lần hai. Thêm idempotency key ổn định theo business transaction ID, kiểm tra không phát sinh kết quả trùng, rồi xác định có thể tăng chunk size an toàn đến đâu.

### Bài 5 — Partitioning và sự cố worker

Chia một triệu item thành bốn partition có dải ID disjoint; kill một worker giữa chừng bằng process/container test riêng. Kiểm tra các partition đã hoàn thành không bị xử lý lại trái phép, partition lỗi được resume/replay an toàn và output cuối không thiếu/trùng.

### Bài 6 — Decision record

Viết một *architecture decision record* ngắn cho job thực tế: mục tiêu throughput, RTO/RPO, kiểu input, transaction boundary, chiến lược idempotency, chunk size đã benchmark, failure scenarios đã test và runbook. Nếu chưa có bằng chứng đo, đánh dấu các mục còn phải xác minh thay vì coi chúng là sự thật.

## 22. Nguyên tắc ghi nhớ

- **Throughput và recoverability là hai mục tiêu cùng quan trọng**, không thể tối ưu chỉ bằng một thuộc tính `chunkSize`.
- **Chunk nhỏ** thường trả nhiều transaction overhead nhưng có thể giảm work chưa commit và giữ lock ngắn.
- **Chunk lớn** thường tăng throughput khi writer có batch I/O, nhưng có thể tăng heap, transaction duration và replay cost.
- **Checkpoint phải bền và input phải replay được**; `ExecutionContext` không cứu được dữ liệu nguồn đã bị thay đổi.
- **Idempotency quyết định mức an toàn khi chạy lại**, nhất là khi side effect nằm ngoài transaction của Spring Batch.
- **Retry, skip và concurrency thay đổi bài toán hiệu năng**, nên benchmark cả lỗi và crash, không chỉ happy path.
- **Restart cùng `JobInstance` khác với chạy một job instance mới**; không thêm identifying `run.id` để né trạng thái cũ mà bỏ qua rủi ro trùng dữ liệu.
- **RTO thực tế** bao gồm phát hiện, quyết định recovery, replay và reconciliation; batch chạy nhanh hơn trong điều kiện bình thường chưa chắc có RTO tốt hơn.
- **Chọn vùng cấu hình ổn định có bằng chứng đo**, bảo toàn dữ liệu, dễ điều tra và đáp ứng SLA tổng thể.

## 23. Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): mô hình xử lý item, chunk và transaction.
- [Spring Batch Reference — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): chi phí transaction và cách cấu hình commit interval.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext` và checkpoint.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `startLimit` và `allowStartIfComplete`.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault tolerance và skip behavior.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong chunk processing.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, partitioning và remote chunking.
- [Spring Batch Reference — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, trạng thái và hoạt động điều hành job.
- [Spring Batch 6.x API — JobOperator](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): `recover` execution sau abrupt shutdown trong phiên bản hỗ trợ.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): metrics cho job/step/chunk và quan sát vận hành.

