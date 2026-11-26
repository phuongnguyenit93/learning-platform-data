# Tránh tạo partition quá nhỏ trong Spring Batch

Khi muốn tăng tốc một Spring Batch job, phản xạ phổ biến là tăng số partition: “8 worker thì chia 8.000 partition để cân bằng tải tốt hơn”. Nhưng mỗi partition không chỉ chứa công việc nghiệp vụ. Framework còn phải tạo `StepExecution`, lưu metadata, chuẩn bị `ExecutionContext`, khởi tạo reader và transaction, xếp lịch worker, ghi checkpoint và tổng hợp kết quả. Nếu mỗi partition chỉ xử lý vài trăm bản ghi, chi phí quản lý có thể chiếm phần lớn tổng thời gian, khiến **nhiều partition hơn nhưng job chậm hơn**.

Bài học **“Tránh tạo partition quá nhỏ”** thuộc chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán dựa trên số đo bottleneck, thread safety, retry/restart, tài nguyên thực tế và SLA. Trọng tâm ở đây là **chọn độ hạt partition hợp lý**, không cố tìm một con số cố định cho mọi workload.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **partition count**, **worker concurrency**, **chunk size** và **đơn vị dữ liệu vật lý**.
2. Liệt kê chi phí cố định khi khởi tạo/đóng mỗi partition ở local và remote partitioning.
3. Dùng số đo để xác định khi nào partition quá nhỏ so với overhead.
4. Ước lượng số partition mục tiêu theo tổng khối lượng xử lý, SLA, concurrency và độ lệch tải.
5. Gộp các shard nhỏ thành **logical partition** mà vẫn giữ đầy đủ coverage và không chồng lấn.
6. Xử lý trường hợp partition lớn bất thường, ranh giới record, hot keys và nguồn dữ liệu thay đổi.
7. Thiết kế `Partitioner` dựa trên **manifest bất biến** và restart ổn định.
8. Benchmark và quan sát đúng chỉ số để tìm điểm cân bằng giữa throughput, skew, latency và chi phí metadata.
9. Chọn thời điểm chuyển từ local sang remote partitioning mà không lạm dụng số partition.

## 2. Partition càng nhiều có luôn nhanh hơn?

Không. Partitioning cho phép chạy **nhiều worker StepExecution** trên những phần dữ liệu độc lập. Nếu mọi worker đều còn dữ liệu và hạ tầng còn năng lực, tăng độ song song có thể cải thiện tổng thời gian. Tuy nhiên, chia nhỏ vượt mức có ích sẽ tạo **overhead trên mỗi partition**.

Một `Partitioner` thông thường trả về:

~~~java
Map<String, ExecutionContext> partition(int gridSize);
~~~

Mỗi phần tử của map có tên partition và context riêng. Splitter tạo/khôi phục một worker `StepExecution` dựa trên tên, còn `PartitionHandler` thực thi các StepExecution đó trong một JVM hoặc phân phối sang JVM khác.

~~~mermaid
flowchart TB
    P["Partitioner tạo N logical partitions"] --> S["StepExecutionSplitter"]
    S --> JR[("JobRepository<br/>StepExecution + ExecutionContext")]
    S --> H["PartitionHandler"]
    H --> Q["Executor / Broker / Worker queue"]
    Q --> W1["Worker A: open → chunks → close"]
    Q --> W2["Worker B: open → chunks → close"]
    Q --> W3["Worker C: open → chunks → close"]
    W1 --> JR
    W2 --> JR
    W3 --> JR
~~~

**Một logical partition không đồng nghĩa một thread hay một transaction.** Trong ví dụ worker step có `chunk(500)`, partition 100.000 bản ghi có thể thực thi hàng trăm chunk transaction tuần tự trong chính worker đó.

### 2.1. Ba biến dễ nhầm

| Biến | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `P` — số partition logic | Số phần việc có tên/context riêng | `P = 80` |
| `C` — worker concurrency | Số worker StepExecution có thể chạy cùng lúc | `C = 8` |
| `K` — chunk size | Số item đầu vào mỗi chunk thông thường trong một worker step | `K = 500` |

Với `P = 80`, `C = 8`, `K = 500`, tối đa khoảng 8 **worker StepExecution** cùng hoạt động trong cấu hình local partitioning minh họa. Mỗi worker xử lý các chunk 500 item; **không** có 80 thread hoặc 80 × 500 item cùng nằm trong một transaction.

Một `gridSize(80)` trên manager step chỉ là **gợi ý** dành cho partitioner/splitter; không bắt buộc partitioner trả đúng 80 phần tử. `TaskExecutor`, consumer concurrency và tài nguyên downstream mới quyết định số worker đang chạy. Trong remote partitioning, số pod còn là một giới hạn riêng.

## 3. Chi phí cố định của một partition đến từ đâu?

Một partition thường có hai nhóm chi phí:

- **Công việc hữu ích:** đọc, biến đổi và ghi item mà nghiệp vụ cần.
- **Chi phí điều phối/khởi tạo:** mọi hoạt động cần có để một partition được tạo, lên lịch, chạy, theo dõi và đóng.

| Lớp | Ví dụ overhead | Khi tăng partition count |
| --- | --- | --- |
| Manager/partitioner | Tạo key, tính context, validate manifest | Thường tăng theo số partition và độ phức tạp plan |
| JobRepository | Ghi `StepExecution`, `ExecutionContext`, status/counters | Nhiều records, metadata writes và truy vấn |
| Scheduler/executor | Submit task, queue, context switch, tracking | Queue lớn, chi phí điều phối tăng |
| Worker step lifecycle | `beforeStep`, khởi tạo scoped beans, `ItemStream.open/close` | Lặp lại cho mỗi StepExecution |
| Reader | Mở file/cursor, tạo query, thiết lập fetch state | Nhiều file opens, queries và connection setup |
| Writer/transaction | Tạo prepared statement, commit các chunk, flush/log | Tăng overhead đặc biệt với partition rất ít item |
| Remote middleware | Serialize request/context, broker publish/consume/ACK/reply | Tăng messages, network RTT và lỗi có thể xảy ra |
| Monitoring | Log/metrics per partition, tracing, aggregation | Cardinality và khối lượng log tăng |
| Failure/restart | Theo dõi nhiều StepExecution, xử lý nhiều kết quả nhỏ | Lợi ích restart mịn hơn nhưng metadata phình ra |

Không có “một overhead cố định 100 ms” áp dụng cho mọi hệ thống. Một worker đọc JDBC nhanh có thể mất vài mili giây khi khởi động, trong khi mở file từ object storage hoặc gọi API cấp token có thể mất hàng trăm mili giây.

### 3.1. Local và remote có overhead khác nhau

**Local partitioning:** nhiều worker StepExecution chạy trong cùng JVM, thường qua `TaskExecutorPartitionHandler`. Không bắt buộc có broker, nhưng vẫn tốn lập lịch, thread/StepScope, reader open/close, metadata và transaction.

**Remote partitioning:** manager phân phối `StepExecutionRequest` cho worker JVM; worker tự đọc/xử lý/ghi shard. Ngoài chi phí kể trên còn có middleware, network, serialization, nhận request, cập nhật metadata từ xa và có thể có replies hoặc manager polling.

Vì vậy một partition 100 ms công việc hữu ích có thể chấp nhận được trong một số trường hợp local nhưng rất tệ nếu remote cần 150–300 ms setup/transport mỗi lần. Phải **đo tại hệ thống thực** thay vì suy theo loại kiến trúc.

## 4. Mô hình đơn giản về độ hạt

Đặt:

- `w`: thời gian hữu ích của một partition nếu chạy một mình.
- `h`: chi phí cố định trung bình của partition, có thể không song song hóa hoàn toàn.
- `C`: số worker thực sự chạy đồng thời.
- `P`: tổng số partition.

Tỷ lệ thời gian hữu ích lý tưởng của một partition:

\[
\eta_{\mathrm{useful}} = \frac{w}{w+h}.
\]

Ví dụ giả định `h = 150\,\text{ms}`:

| Công việc hữu ích/partition | Overhead | Tỷ lệ hữu ích | Nhận định |
| ---: | ---: | ---: | --- |
| 50 ms | 150 ms | 25% | Overhead chiếm phần lớn |
| 150 ms | 150 ms | 50% | Mỗi đơn vị work phải trả overhead tương đương |
| 1.350 ms | 150 ms | 90% | Tương đối hợp lý nếu skew không lớn |
| 5.000 ms | 150 ms | 97,1% | Overhead thấp, nhưng cần kiểm tra tail/skew |

**Đây là phép tính minh họa**, không phải ngưỡng của Spring Batch. Dùng tỷ lệ hữu ích khoảng 90–95% làm một giả thuyết thử nghiệm có thể hợp lý, nhưng không nên ép các partition thật lớn nếu một shard chậm đang làm kéo dài job hoặc khi cần restart mịn.

### 4.1. Gần đúng về tổng thời gian

Nếu tổng thời gian **công việc hữu ích tuần tự** là `W`, dữ liệu chia khá đều, overhead `h` trả cho mỗi partition và có `C` worker, mô hình lý tưởng là:

\[
T_{\mathrm{parallel}}
\gtrsim
\frac{W+P h}{C}.
\]

Công thức đơn giản này giả định cả work và overhead có thể phân phối gần đều cho C workers. Thực tế còn các chi phí **tuần tự ở manager**, thời gian xếp lịch, đường đi critical path, skew, giới hạn DB/API và thời gian publish. Vì thế nó là **lower-bound/ước lượng thô**, không phải công thức dự đoán production.

Một mô hình đáng ghi nhớ hơn:

\[
T_{\mathrm{job}}
\approx
T_{\mathrm{plan}}
+T_{\mathrm{dispatch}}
+T_{\mathrm{worker\ critical\ path}}
+T_{\mathrm{aggregate}}
+T_{\mathrm{validate/publish}}.
\]

Khi tăng P, `Tplan`, `Tdispatch` và overhead trên critical path có thể tăng, trong khi phần mất cân bằng có thể giảm. Mục tiêu là tìm **điểm cân bằng** của hai xu hướng.

### 4.2. Ví dụ 12 triệu bản ghi

Giả định:

- `N = 12.000.000` item.
- Một worker đạt `R = 5.000` item/s khi độc lập và chưa nghẽn downstream.
- `C = 8` worker.
- Overhead mỗi partition `h = 0,2` giây.
- Các partition cân bằng, không có contention hay retry.

Thời gian hữu ích tuần tự:

\[
W = \frac{12.000.000}{5.000}=2.400\text{ giây}.
\]

Giới hạn lý tưởng do tám workers:

\[
W/C = 300\text{ giây}.
\]

| Partition count `P` | Item trung bình/partition | Work/partition | Tổng overhead `P h` | Ước lượng gần đúng `(W+Ph)/C` |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 1.500.000 | 300 s | 1,6 s | 300,2 s |
| 80 | 150.000 | 30 s | 16 s | 302 s |
| 800 | 15.000 | 3 s | 160 s | 320 s |
| 8.000 | 1.500 | 0,3 s | 1.600 s | 500 s |

Đều là **số giả định lý tưởng**, không phải benchmark thực. Ở đây P=8 và P=80 gần như giống nhau nếu tải cân bằng tuyệt đối. Nhưng nếu có một số shard nặng bất thường, P=80 có thể đạt kết quả thực tốt hơn P=8 nhờ giảm tail/skew. P=8.000 làm overhead quá lớn nếu mọi điều kiện khác giữ nguyên.

Câu hỏi đúng không phải “nhiều nhất được bao nhiêu partition?”, mà là **“cần bao nhiêu phần việc độc lập để đủ giữ C worker bận và không trả quá nhiều overhead?”**

## 5. Mối quan hệ giữa số partition và độ lệch tải

Nếu chỉ tạo đúng `P=C` partition mà một partition mất 30 phút còn bảy partition mất 2 phút, các worker còn lại sẽ rảnh lâu. Job không thể hoàn tất trước partition chậm nhất.

~~~mermaid
gantt
    title Ví dụ minh họa: 4 worker với partition skew
    dateFormat  X
    axisFormat %s
    section Worker A
    partition A (nặng) : 0, 30
    section Worker B
    partition B       : 0, 4
    section Worker C
    partition C       : 0, 4
    section Worker D
    partition D       : 0, 4
~~~

Sơ đồ trên biểu diễn **đơn vị thời gian minh họa**, không phải lịch ngày thực tế. Với `P=C`, scheduler không thể chuyển nửa workload của A sang B nếu partition A là một StepExecution duy nhất chạy tuần tự.

Tạo nhiều partition **hơn C một cách vừa phải** giúp worker rảnh nhận phần việc tiếp theo, tăng khả năng cân bằng tải. Có thể thử tỷ lệ `P/C` bằng 2, 4 hoặc 8 khi work có skew, nhưng đây chỉ là **mức thử nghiệm**, không phải quy tắc của Spring Batch.

### 5.1. Đơn vị phân vùng nên dựa trên chi phí, không chỉ số record

100.000 dòng đơn hàng ngắn có thể xử lý nhanh hơn 10.000 dòng chứa JSON lớn hoặc phải gọi API chậm. Nếu chia đều số record nhưng khác độ khó, partition vẫn skew.

Các tín hiệu dùng để ước tính trọng số:

- Số item dự kiến.
- Tổng bytes cần đọc/ghi.
- Độ phức tạp processor (loại record, số phép join, số API calls).
- Thời gian trung bình/p95 trên dữ liệu mẫu.
- Số và loại bản ghi dễ retry, khóa ghi nóng.
- Data locality, shard/tenant affinity và giới hạn per-key ordering.

Có thể định nghĩa **estimated work units**:

\[
\widehat{W_i}
= a\cdot\text{items}_i
+b\cdot\text{bytes}_i
+c\cdot\text{expectedExternalCalls}_i.
\]

Các hệ số `a, b, c` phải được **calibrate bằng benchmark**. Không giả định rằng byte size luôn tỷ lệ tuyến tính với CPU time.

### 5.2. Một file quá lớn không thể tự “cắt đôi” bằng cách đổi tên

Nếu đầu vào là một file 50 GB và hàng trăm file vài KB, gộp file nhỏ giải quyết được phần overhead ở file nhỏ nhưng **không chia được file lớn**. Muốn tách file lớn cần reader hỗ trợ split ở ranh giới record, đồng bộ encoding/newline, checkpoint đúng và snapshot bất biến. Với CSV có quoted newline hoặc format nén không hỗ trợ seek, chia byte range tùy tiện có thể làm sai dữ liệu.

Với bảng DB, range ID nửa mở `[minInclusive, maxExclusive)` có thể là lựa chọn nếu index và snapshot phù hợp. Tránh cắt theo offset thay đổi liên tục khi source bị insert/delete.

## 6. Quy trình quyết định số partition

Một quy trình thực tế nên chạy theo thứ tự:

1. **Chốt SLA:** N item/bytes cần hoàn tất trong bao nhiêu phút xử lý sau khi trừ setup, validation, publish và recovery buffer?
2. **Đo baseline:** một worker đọc–xử lý–ghi được bao nhiêu item/s, p95 chunk duration, chi phí khởi tạo StepExecution và overhead metadata?
3. **Xác định trần concurrency `C`:** CPU cores, I/O, Hikari connections, API quotas, broker và database locks.
4. **Đo độ lệch công việc:** histogram theo file/range/tenant và dự báo cost per shard.
5. **Chọn P ban đầu:** đủ lớn để có work queue cho C workers, nhưng mỗi partition chứa lượng work đáng kể so với `h`.
6. **Đánh giá restart:** shard rất lớn làm phải phục hồi dài khi lỗi; shard rất nhỏ làm metadata/dispatch phình ra.
7. **Benchmark nhiều P:** giữ C và chunk size cố định khi quét P, rồi thử C theo dữ liệu đo được.
8. **Xác minh output:** throughput đã commit và reconciliation phải đúng, không chỉ job báo `COMPLETED`.

### 6.1. Ước lượng target work per partition từ overhead

Nếu muốn overhead chiếm không quá tỷ lệ mục tiêu `\alpha` của thời gian partition khi chạy bình thường:

\[
\frac{h}{w+h}\le\alpha
\quad\Rightarrow\quad
w\ge h\left(\frac{1}{\alpha}-1\right).
\]

Ví dụ `h=200` ms và mục tiêu overhead tối đa 5%:

\[
w\ge0,2\times(20-1)=3,8\text{ giây}.
\]

Đây là một **cận tối thiểu theo mô hình đơn giản**. Nó không đảm bảo rằng chọn work per partition = 3,8 giây đã tối ưu: p99 setup, skew, DB contention và headroom restart có thể đòi hỏi thay đổi.

### 6.2. Ước lượng số partition khả thi

Giả sử tổng thời gian xử lý tuần tự `W=2.400` giây, với mục tiêu mỗi partition có ít nhất 3,8 giây work thì:

\[
P\lesssim \frac{2.400}{3,8}\approx631.
\]

Nếu có 8 worker, thử ban đầu P=32 hoặc P=64 có thể hợp lý hơn P=600 vì vẫn đủ nhiều phần việc cho scheduling mà tránh overhead không cần thiết. Đây chỉ là **điểm khởi đầu để đo**; nếu có vài hot ranges, cần xử lý skew hơn là áp số P từ công thức.

### 6.3. Vì sao “partition size” không nên đồng nhất với “chunk size”?

Với chunk size 500:

- Partition chứa 50 item thường xử lý **một chunk nhỏ**, nhưng vẫn phải tạo StepExecution, mở reader và commit metadata.
- Partition chứa 500 item thường xử lý khoảng một chunk dữ liệu.
- Partition chứa 50.000 item có thể xử lý khoảng 100 chunk trong cùng worker step.

Một khuyến nghị thực dụng là tránh tạo hàng nghìn partition mà mỗi partition chỉ xử lý vài chục item khi chi phí start/stop đã cao. Tuy nhiên, **không có quy tắc Spring Batch rằng partition phải chứa ít nhất X chunk**. Cần đo bằng thời gian/bytes/work units thực.

## 7. Gộp shard vật lý nhỏ thành logical partition

Một cách giảm overhead là phân biệt:

- **Physical shard:** file nhỏ, partition DB, object-storage object hoặc một khoảng ID nhỏ do nguồn dữ liệu tạo sẵn.
- **Logical partition:** đơn vị công việc Spring Batch nhận `StepExecution` riêng; có thể gồm **nhiều physical shards**.

Ví dụ 10.000 file CSV rất nhỏ:

~~~text
Không gộp:
  10.000 file -> 10.000 StepExecution
  mỗi step mở 1 file, chạy 1 chunk, đóng

Có gộp:
  10.000 file -> 100 logical partitions
  mỗi step xử lý danh sách ~100 file
  reader chuyển file bên trong một StepExecution
~~~

Worker của logical partition cần hỗ trợ đọc tuần tự nhiều file, ví dụ `MultiResourceItemReader` hoặc custom reader theo một manifest group, đồng thời checkpoint **vị trí file và vị trí record** đúng. Không nên chỉ đặt một string URI ngẫu nhiên vào context mà bỏ qua các file còn lại.

### 7.1. Không gộp bất kỳ thứ gì vào một khoảng ID lớn

Giả sử một group gồm `[1,1000]` và `[5000,6000]`, nhưng các ID `[1001,4999]` thuộc group khác. Nếu worker của group đầu chạy:

~~~sql
-- SAI nếu group chỉ được gán hai range rời nhau:
SELECT * FROM orders
WHERE order_id BETWEEN 1 AND 6000;
~~~

Query này lấy cả vùng giữa, có thể đọc trùng dữ liệu của group khác. Worker phải giữ danh sách các đoạn không liên tiếp trong **manifest group** và query theo từng đoạn, hoặc chọn cách nhóm bảo toàn dải liên tục.

Ví dụ đúng theo hai range của group:

~~~sql
SELECT order_id, amount
FROM orders
WHERE (order_id BETWEEN 1 AND 1000)
   OR (order_id BETWEEN 5000 AND 6000)
ORDER BY order_id;
~~~

Với hàng nghìn range, không nhất thiết nối hàng nghìn điều kiện `OR` vào một query. Có thể dùng bảng staging chứa mapping `groupId → range` hoặc reader đọc từng đoạn; đánh giá execution plan/index và transaction theo database thực.

### 7.2. Giữ thứ tự theo khóa nghiệp vụ

Nếu các record của cùng tài khoản phải được xử lý theo thứ tự, không gộp/chia theo cách làm hai worker khác nhau cùng cập nhật tài khoản không có quy tắc version. Có thể nhóm theo `customerId`/hash bucket ổn định và dùng writer kiểm soát version, optimistic lock hoặc serialization per key.

Gộp shard giải quyết **overhead điều phối**, không tự giải quyết thứ tự commit hoặc idempotency.

## 8. Thiết kế partition plan bất biến trước khi chạy

Để gộp shard mà vẫn restart an toàn, cách dễ kiểm soát là tạo một **immutable work-group manifest** trước khi manager split job.

Ví dụ bảng kế hoạch:

| snapshot_id | group_key | group_manifest_uri | estimated_items | estimated_work_ms |
| --- | --- | --- | ---: | ---: |
| `daily-2026-11-25-v1` | `group-000` | `store://snapshot/v1/groups/000.json` | 125.000 | 30.000 |
| `daily-2026-11-25-v1` | `group-001` | `store://snapshot/v1/groups/001.json` | 118.000 | 28.000 |
| `daily-2026-11-25-v1` | `group-002` | `store://snapshot/v1/groups/002.json` | 130.000 | 32.000 |

Mỗi `group_manifest_uri` mô tả một danh sách shard nhỏ không trùng nhau. Worker StepExecution chỉ cần biết `snapshotId`, `groupKey` và URI/version, rồi đọc đúng group ấy. Không nhồi danh sách hàng chục nghìn file vào `ExecutionContext` vì context cần được serialize/persist trong JobRepository, có giới hạn kích thước và gây chi phí metadata.

### 8.1. Tạo manifest ở thời điểm nào?

- Chốt input cutoff/snapshot.
- Xây thống kê kích cỡ/estimated work theo physical shard.
- Chia/gộp thành work groups theo quy tắc xác định, có version.
- Kiểm chứng coverage/disjointness và khóa immutable manifest.
- **Sau đó** khởi chạy JobInstance có identifying `snapshotId`.

Không nên tạo lại plan khác mỗi lần `partition(gridSize)` được gọi khi restart. Nếu manifest cần đổi vì workload tăng trưởng, áp dụng cho **JobInstance mới** hoặc thực hiện quy trình migration/reprocess có đối soát riêng.

### 8.2. Tên group phải ổn định

Nên dùng tên có thể tìm lại: `group-000`, `group-001`… gắn với một manifest version cố định. Không dùng `UUID.randomUUID()` hoặc thứ tự `File.listFiles()` không xác định khi restart. `PartitionNameProvider` có thể giúp lấy danh sách tên nhanh hơn khi restart mà không tính lại kế hoạch nhóm, nhưng không thay thế `Partitioner` ở lần đầu.

**Quan trọng:** số worker/pod có thể thay đổi khi restart; điều đó **không có nghĩa** thay partition key hoặc phân phối lại các shard trong plan cũ. `JobRepository` gắn checkpoint với StepExecution identity của từng partition.

## 9. Thuật toán gộp shard nhỏ theo estimated work

Giải pháp đơn giản là **gộp các shard liên tiếp trong một danh sách đã sắp xếp ổn định** cho đến khi đạt target work units. Thuật toán này ưu tiên tính xác định và dễ kiểm chứng, không tuyên bố cân bằng tối ưu như các thuật toán bin packing phức tạp.

Giả sử đầu vào:

~~~text
shard-A:  80 work units
shard-B: 120
shard-C:  20
shard-D: 200
shard-E:  40
shard-F: 140
target per group: khoảng 200 units
~~~

Một kế hoạch hợp lý:

~~~text
group-000 -> [A, B]      = 200
group-001 -> [C, D]      = 220
group-002 -> [E, F]      = 180
~~~

Với physical shard quá lớn so với target, thuật toán gộp không chia nhỏ nó: cần xử lý riêng nếu muốn giảm skew.

### 9.1. Ví dụ Java tính nhóm

Code sau hoạt động độc lập với API Spring Batch và sử dụng Java 17+:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class WorkGroupPlanner {

    public record SourceShard(String id, long estimatedUnits) {}

    public record PlannedGroup(String key,
                               List<SourceShard> shards,
                               long estimatedUnits) {}

    public static List<PlannedGroup> coalesce(
            List<SourceShard> input, long targetUnits) {

        if (targetUnits <= 0) {
            throw new IllegalArgumentException("targetUnits must be > 0");
        }

        List<SourceShard> ordered = input.stream()
                .sorted(Comparator.comparing(SourceShard::id))
                .toList();

        List<PlannedGroup> groups = new ArrayList<>();
        List<SourceShard> pending = new ArrayList<>();
        long weight = 0;

        for (SourceShard shard : ordered) {
            if (shard.id() == null || shard.id().isBlank()
                    || shard.estimatedUnits() < 0) {
                throw new IllegalArgumentException("Invalid shard");
            }

            // Đã có việc và thêm shard này sẽ vượt mục tiêu:
            // tạo group mới. Đây là heuristic, không phải tối ưu toàn cục.
            if (!pending.isEmpty() && weight > 0
                    && shard.estimatedUnits() > targetUnits - weight) {
                groups.add(makeGroup(groups.size(), pending, weight));
                pending = new ArrayList<>();
                weight = 0;
            }

            pending.add(shard);
            weight = Math.addExact(weight, shard.estimatedUnits());
        }

        if (!pending.isEmpty()) {
            groups.add(makeGroup(groups.size(), pending, weight));
        }
        return List.copyOf(groups);
    }

    private static PlannedGroup makeGroup(
            int index, List<SourceShard> shards, long weight) {
        return new PlannedGroup(
                "group-%05d".formatted(index),
                List.copyOf(shards), weight);
    }
}
~~~

**Hợp đồng của ví dụ:**

- Sort theo shard ID giúp kết quả không phụ thuộc thứ tự listing ngẫu nhiên.
- `Math.addExact` phát hiện overflow khi cộng estimated units.
- Với shard lớn hơn target, có thể tạo group vượt target: đó là tình huống cần xem xét split physical shard, không nên im lặng bỏ dữ liệu.
- Group cuối có thể rất nhỏ. Production có thể hợp nhất nhóm cuối với nhóm trước nếu không vi phạm giới hạn max size/memory và ràng buộc business.
- Algorithm hiện tại **không tự kiểm tra duplicate shard ID** trong input; bước validate manifest bắt buộc phải đảm bảo ID duy nhất và không có physical shard chồng lấn.
- Một estimated work unit bằng 0 không có nghĩa bỏ shard: các file 0 item vẫn có thể cần được ghi nhận hoặc loại bỏ theo chính sách dữ liệu trước khi lập plan.
- Tên `group-00000` ổn định **chỉ khi input list, estimatedUnits, targetUnits và thuật toán lập nhóm không đổi**. Cần **persist kết quả** và dùng lại plan đã chốt khi restart; đừng chạy lại heuristic trên tập dữ liệu sống rồi tin rằng tên/mapping vẫn an toàn.

### 9.2. Test coverage và tính xác định của planner

Với đầu vào hợp lệ, cần chứng minh:

~~~text
set(shard IDs trong tất cả groups)
    == set(shard IDs của snapshot)

Mỗi shard ID xuất hiện trong đúng một group.

Cùng immutable input + target + planner version
    -> cùng keys và cùng danh sách members của mỗi group.
~~~

Nếu hai shard IDs giống nhau trong manifest, `Set` có thể che mất duplicate; phải kiểm tra **tần suất xuất hiện** và unique constraint, không chỉ set equality.

## 10. Partitioner Spring Batch dùng work-group manifest

Sau khi lưu kết quả của `WorkGroupPlanner` thành **manifest bất biến**, `Partitioner` chỉ đọc các group đã chốt. Ví dụ một record đại diện cho group:

~~~java
public record WorkGroup(
        String key,
        String manifestUri,
        long estimatedUnits) {}

public interface WorkGroupStore {
    // Phải truy cập plan bất biến gắn với snapshotId.
    List<WorkGroup> groupsFor(String snapshotId);
    List<String> groupKeysFor(String snapshotId);
}
~~~

Triển khai `Partitioner` cùng `PartitionNameProvider` để tối ưu restart:

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.partition.support.PartitionNameProvider;
import org.springframework.batch.item.ExecutionContext;

public final class CoalescedPartitioner
        implements Partitioner, PartitionNameProvider {

    private final WorkGroupStore store;
    private final String snapshotId;

    public CoalescedPartitioner(
            WorkGroupStore store, String snapshotId) {
        this.store = store;
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        List<WorkGroup> groups = store.groupsFor(snapshotId);
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (WorkGroup group : groups) {
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("snapshotId", snapshotId);
            ctx.putString("groupKey", group.key());
            ctx.putString("manifestUri", group.manifestUri());
            ctx.putLong("estimatedUnits", group.estimatedUnits());

            if (result.putIfAbsent(group.key(), ctx) != null) {
                throw new IllegalStateException(
                        "Duplicate group key: " + group.key());
            }
        }

        if (result.isEmpty()) {
            throw new IllegalStateException(
                    "No partitions for snapshot " + snapshotId);
        }
        return result;
    }

    @Override
    public Collection<String> getPartitionNames(int gridSize) {
        List<String> keys = store.groupKeysFor(snapshotId);
        if (keys.isEmpty()
                || new LinkedHashSet<>(keys).size() != keys.size()) {
            throw new IllegalStateException(
                    "Invalid partition keys: " + snapshotId);
        }
        return List.copyOf(keys);
    }
}
~~~

### 10.1. Những điều phải bổ sung khi đưa vào production

- `WorkGroupStore` phải dùng **snapshot/plan immutable**, trả key hợp lệ và giữ thứ tự/identity đã chốt qua restart.
- Kiểm tra `group.key()`/`manifestUri()` nonblank, estimatedUnits hợp lệ và toàn bộ group manifest không thiếu/đè nhau.
- Có phiên bản planner và checksum manifest để phát hiện drift, thay vì tái tính plan dựa trên dữ liệu mới.
- Dùng `@StepScope` cho partitioner nếu cần lấy `snapshotId` qua `jobParameters` và tránh singleton mutable dùng chung nhiều job.
- `groupKeysFor` phải trả **tất cả key của kế hoạch gốc**, không chỉ group thất bại; splitter sẽ đối chiếu trạng thái trong `JobRepository`.
- Không trả context phình ra với danh sách hàng nghìn URI; context chỉ giữ tham chiếu và metadata nhỏ.
- Nếu input thực sự rỗng, định nghĩa chính sách “skip job/step với output rỗng” riêng, không mặc định coi thiếu manifest là thành công.
- `gridSize` có thể không được dùng trong ví dụ vì manifest đã chốt P. Điều này hợp lệ khi có lý do rõ ràng và tên nhóm ổn định.
- Khi chạy qua remote partitioning, worker cần đọc được group manifest trên shared/object storage và có quyền truy cập dữ liệu, không chỉ thấy đường dẫn trên manager.

### 10.2. Cấu hình manager và worker

Một manager step local partitioning có thể sử dụng partitioner đã tạo:

~~~java
@Bean
public Step orderManagerStep(
        JobRepository repository,
        @Qualifier("coalescedPartitioner") Partitioner partitioner,
        @Qualifier("orderWorkerStep") Step worker,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("orderManagerStep", repository)
            .partitioner("orderWorkerStep", partitioner)
            .step(worker)
            .gridSize(32) // hint; plan đã chốt có thể có số group khác
            .taskExecutor(executor)
            .build();
}
~~~

Ví dụ cấu hình này dành cho **Spring Batch 5.2.x**, bỏ qua phần wiring executor, worker reader/writer và bean dependencies để tập trung vào `Partitioner`. Worker step sử dụng `@StepScope` để lấy `manifestUri`, lần lượt xử lý từng physical shard thuộc group và checkpoint đúng cả **shard index + record index**.

Trong remote partitioning, `PartitionHandler` thay thế cách dispatch local bằng middleware/worker JVM nhưng **không** thay đổi hợp đồng logical partition hoặc yêu cầu checkpoint/idempotency.

## 11. Restart: gộp nhỏ để giảm overhead nhưng không phá metadata

Một partition có `StepExecution` và `ExecutionContext` riêng. Khi JobInstance lỗi, framework có thể dùng lịch sử trong `JobRepository` để chọn partition chưa hoàn tất cho lần restart.

Ví dụ 32 logical partitions:

~~~text
group-00000 ... group-00029 : COMPLETED
group-00030                   : FAILED
group-00031                   : COMPLETED

Restart cùng JobInstance:
  group-00000..00029 và 00031 -> bỏ qua theo mặc định
  group-00030                 -> worker chạy lại từ checkpoint
~~~

**Không được nhân cơ hội restart để đổi từ 32 group sang 128 group**, vì tên `StepExecution` và mapping từ group key tới physical shards/context sẽ thay đổi. Việc thay số worker threads/pods không đòi thay đổi plan; hãy giữ group keys ổn định và điều chỉnh concurrency trong handler/executor.

### 11.1. Gộp quá lớn cũng có chi phí phục hồi

Partition lớn giúp giảm overhead nhưng khi một worker lỗi:

- Có thể còn nhiều item phải xử lý trong partition đó.
- Worker giữ một reader hoặc cursor lâu, tăng rủi ro resource timeout.
- Một shard nặng gây tail latency.
- Mất `ExecutionContext` hoặc input không ổn định có thể khiến phải làm lại phần lớn partition.

Tuy nhiên, **partition lớn không bắt buộc chạy lại toàn bộ** nếu worker chunk-oriented lưu checkpoint hợp lệ. Cần phân biệt **đơn vị restart là partition StepExecution** và **vị trí resume là checkpoint của các chunk đã commit trong partition**. Chọn độ hạt phải dựa trên **thời gian phục hồi đo được**, không dựa vào giả định “cứ partition lớn là restart từ đầu”.

### 11.2. Độ ổn định của tên và plan

Khi ứng dụng implement `PartitionNameProvider`, `getPartitionNames(gridSize)` trên restart chỉ trả tên group đã chốt; Spring Batch lấy context cũ. Interface giúp tránh phải tính lại thuật toán gộp tốn kém, nhưng không tái tạo metadata nếu `JobRepository` mất.

Nếu plan bị sửa giữa hai JobExecution trong cùng JobInstance, dù tên vẫn giống nhau, mapping group-to-shards có thể sai. Vì vậy **immutable manifest phải là nguồn sự thật**, không cho sửa âm thầm.

## 12. Khi một group chứa nhiều physical shards, reader checkpoint thế nào?

Một logical partition có thể gồm 100 file nhỏ. Worker cần nhớ nó đang đọc **file thứ mấy** và **item thứ mấy trong file**. Ví dụ context khái niệm:

~~~text
groupKey         = group-00012
manifestUri      = store://snap/v42/groups/00012.json
currentShardIndex = 37
currentItemIndex  = 920
~~~

Các key `currentShardIndex` và `currentItemIndex` chỉ là ví dụ minh họa; tên key thực tế phụ thuộc reader implementation. Không tự ghi những key này mỗi lần `read()` vào context rồi kết luận đã checkpoint. `ItemStream.update(...)` phải phối hợp với cơ chế commit của Spring Batch để vị trí được lưu **nhất quán với dữ liệu đã ghi**.

Cân nhắc dùng `MultiResourceItemReader` kết hợp `FlatFileItemReader` khi dữ liệu là nhiều file; cần kiểm tra sort order, resource version, tên reader và `saveState` theo API phiên bản đang chạy. Nếu nguồn đến từ object storage, không để danh sách file đang thay đổi sau khi job bắt đầu.

### 12.1. Idempotency khi gộp file

Gộp nhiều file thành một partition **không** loại bỏ khả năng chunk bị xử lý lại sau rollback/crash. Writer cần unique business key hoặc idempotency key nếu tác dụng nghiệp vụ có thể lặp.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO normalized_order(order_id, source_version, amount)
VALUES (:orderId, :sourceVersion, :amount)
ON CONFLICT (order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    amount = EXCLUDED.amount
WHERE normalized_order.source_version < EXCLUDED.source_version;
~~~

Writer này minh họa ngăn kết quả source version cũ ghi đè version mới và tránh tạo dòng trùng. Cần bổ sung xử lý trường hợp **cùng version nhưng payload khác** và quy tắc nghiệp vụ khác; đừng mặc định upsert giải quyết mọi tác dụng phụ như email hoặc chuyển tiền.

## 13. Benchmark để chọn độ hạt partition

Để biết P nào hợp lý, hãy thay **P** trong khi giữ **C**, chunk size và input snapshot cố định. Ví dụ giả định có tám worker, dữ liệu và DB giống nhau:

| Số partition P | P/C | Avg item/partition | Tổng thời gian job *giả định* | p95 partition setup | Nhận định |
| ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 1 | 1.500.000 | 9,5 phút | 200 ms | Skew làm worker rảnh |
| 32 | 4 | 375.000 | 6,3 phút | 210 ms | Cân bằng tốt |
| 64 | 8 | 187.500 | 6,1 phút | 210 ms | Có thể là điểm tốt |
| 256 | 32 | 46.875 | 6,7 phút | 230 ms | Bắt đầu tốn metadata |
| 2.048 | 256 | ~5.859 | 10,8 phút | 280 ms | Dispatch/setup quá nhiều |
| 8.192 | 1.024 | ~1.465 | 21,4 phút | 390 ms | Overhead áp đảo |

**Các số liệu hoàn toàn giả định** nhằm cho thấy đường cong U: ban đầu chia thêm giúp giảm skew, sau một điểm thì tạo thêm partition làm chậm job. Benchmark thật có thể tạo đường cong khác, nhất là khi writer DB bão hòa hoặc mỗi partition có thời gian cố định lớn.

### 13.1. Đo các thành phần nào?

| Nhóm | Metric cần ghi | Diễn giải |
| --- | --- | --- |
| Partition plan | `partition()` duration, số group, thời gian đọc manifest | Khâu lập kế hoạch có chiếm SLA không? |
| JobRepository | StepExecution create/update latency, metadata rows, DB connections | P cao có gây quá tải metadata DB không? |
| Worker startup | Từ dispatch đến first committed chunk, reader open time | Overhead trên mỗi partition bao nhiêu? |
| Useful work | Committed items/s, bytes/s, CPU time và DB write TPS | Work nghiệp vụ có tăng thực không? |
| Tail/skew | p50/p95/p99/max partition duration, longest partition | P lớn hơn có giảm straggler không? |
| Scheduler/transport | Executor queue, broker oldest request age, reply/poll lag | Quá nhiều task đang đợi hoặc message chậm |
| Resource saturation | CPU, heap, GC, Hikari pending, DB locks, IOPS, API 429 | Nút thắt nằm ở đâu? |
| Correctness | Unique IDs, expected totals, checksum và restart result | Có mất/trùng item sau khi gộp không? |
| SLA | End-to-end finish, validation/publish và recovery margin | Kiến trúc có đạt deadline thực tế không? |

Khi đo overhead, cố gắng phân biệt **queue wait** với **worker setup**; nếu một StepExecution nằm đợi 5 phút vì thread pool bận thì không thể kết luận bản thân reader open tốn 5 phút.

### 13.2. A/B thử nghiệm nên có những mức nào?

Ví dụ với `C=8`, thử `P=8, 16, 32, 64, 128` trước; chỉ thử hàng nghìn partition khi kết quả và workload cho thấy cần làm thế. Sau khi chọn vùng P thích hợp, mới tune C theo CPU/DB/API budget và chunk size theo commit overhead.

Nên thử **typical day, peak day, skewed day, backfill** và lỗi restart. Một lựa chọn đạt SLA trên ngày trung bình nhưng trễ ngày cuối tháng vẫn chưa đủ.

## 14. Database pool và giới hạn điều phối

Tăng P không trực tiếp tăng concurrency nếu `C` được giới hạn. Nhưng P quá cao vẫn gây tải metadata và mở/đóng reader thường xuyên; tăng C đồng thời còn gây thêm áp lực lên connection pool.

Giả sử có 8 worker concurrent, mỗi worker mở một JDBC cursor connection và cần connection khác để ghi chunk, trong khi `maximumPoolSize` của Hikari là 12. Có thể có nhiều worker đang chờ connection, dù CPU thấp. Cần đo **connection hold time**, Hikari active/pending và DB wait events; không suy rằng “8 worker luôn cần đúng 8 connection”.

Trong remote partitioning, tổng trần connection từ nhiều worker pods cộng dồn. Ví dụ 10 pods, mỗi pod pool tối đa 12, một manager pool tối đa 8 thì trần cấu hình là:

\[
C_{\mathrm{configured}}=10\times12+8=128
\]

chưa kể các ứng dụng khác. Không thiết kế 10.000 partition chỉ vì broker chịu được 10.000 message; database có thể không đủ năng lực ghi.

### 14.1. Chọn giữa giảm partition và giảm concurrency

- **P quá cao, C phù hợp:** overhead metadata/lifecycle tăng; xem xét **gộp shard** và giảm P.
- **P phù hợp, C quá cao:** connection/lock contention tăng; giảm worker concurrency hoặc tối ưu DB.
- **P quá thấp, C cao:** một phần workers không có việc; tăng P hoặc split hot shards.
- **P cao, C thấp nhưng stragglers nhiều:** cần đánh giá độ lệch tải và batching hơn là lập tức tăng C.
- **DB writer đã bão hòa:** tăng P hay C đều không bảo đảm tăng throughput; tối ưu transaction, write pattern hoặc capacity downstream.

## 15. Những rủi ro khi tối ưu sai

| Sai lầm | Hệ quả |
| --- | --- |
| “Càng nhiều partition càng tận dụng nhiều CPU.” | Khi P vượt mức cần thiết, overhead/scheduling tăng mà C không đổi. |
| “`gridSize` bằng số threads.” | `gridSize` chỉ là hint cho partitioner, concurrency do handler/executor. |
| “Mỗi file phải là một partition.” | Hàng nghìn file nhỏ tạo quá nhiều StepExecution; có thể gộp. |
| “Chunk size lớn sẽ chữa partition quá nhỏ.” | Chunk lớn không loại bỏ overhead StepExecution/open/close và có thể tăng memory/lock. |
| “Gộp nhiều range bằng min/max.” | Với range rời nhau có thể đọc cả bản ghi ngoài group. |
| “Chỉ cần các group có số item bằng nhau.” | Work CPU/I/O/API không tỷ lệ đều với item count. |
| “Group càng lớn càng tốt.” | Tail/skew và thời gian khôi phục có thể tăng; reader giữ tài nguyên lâu. |
| “Thay group keys trên restart sẽ cân bằng lại.” | Có thể phá metadata và checkpoint của JobInstance cũ. |
| “Lưu toàn bộ file list vào ExecutionContext.” | Metadata payload lớn, serialization/DB pressure cao, restart chậm. |
| “Partition đã COMPLETED thì output chắc chắn đúng.” | Vẫn phải đối soát coverage, checksum và business correctness. |
| “Khi DB nghẽn, tăng số worker sẽ giải quyết.” | Có thể tăng locks, timeouts và retry storm. |
| “Benchmark một lần với dữ liệu đều là đủ.” | Peak/skew/retry/remote latency có thể thay đổi điểm tối ưu. |

## 16. Kịch bản kiểm thử tính đúng đắn và hiệu năng

Giả sử một snapshot có **5.000 file** và 10 triệu item. Planner gộp thành 80 work groups; manager sử dụng tám workers.

| Kịch bản | Hành động | Kết quả cần xác minh |
| --- | --- | --- |
| Coverage | Kiểm tra mapping mọi file tới group | Không thiếu file; không file xuất hiện trong hai groups |
| Deterministic plan | Trộn thứ tự input listing rồi tạo plan | Nếu manifest/costs bất biến, kế hoạch nhóm không đổi |
| Duplicate shard ID | Đưa hai entry cùng ID vào manifest | Planner/validation phát hiện và fail |
| Big shard | Một file có work > target | Không bỏ dữ liệu; nhận diện group nặng để xử lý riêng |
| Tiny final group | Group cuối chỉ vài item | Có chính sách merge phù hợp hoặc chấp nhận có căn cứ |
| Reader multi-file | Kill worker giữa file thứ 37 | Restart dùng checkpoint file + item chính xác |
| DB multi-range | Group chứa hai range rời nhau | Worker không đọc toàn khoảng min–max |
| Restart lỗi | 79 group COMPLETED, 1 FAILED | Chỉ phần cần phục hồi chạy; kế hoạch/tên không đổi |
| Worker crash sau commit | Kill process rồi restart | Writer idempotent; không tác dụng nghiệp vụ trùng |
| Resource limits | Giảm DB pool, tăng C | Phát hiện saturation; không kết luận tăng P giúp |
| Performance | Thử P=8/32/80/320/2.000 với C=8 | Có biểu đồ throughput, setup overhead, metadata và tail |
| SLA | Tăng data volume/peak và thêm recovery test | End-to-end đạt deadline với headroom đã thỏa thuận |

### 16.1. Bất biến nghiệm thu

~~~text
1. Every approved physical shard belongs to exactly one logical group.
2. Every approved business item is read/committed as expected.
3. No item outside the approved snapshot/manifest is processed.
4. Restart uses the original group keys and saved ExecutionContext.
5. Final output after crash/restart equals a clean-run reference.
6. The chosen P improves end-to-end throughput without violating DB/API budgets.
7. Peak/skew scenarios still meet the agreed SLA and recovery policy.
~~~

Không chỉ assert `readCount == writeCount`: các item bị filter có thể làm hai số khác nhau hợp lệ, còn duplicate và missing item có thể triệt tiêu nhau về số lượng. Dùng unique business keys, checksum/tổng tiền và quy tắc xử lý lỗi đã được chấp nhận.

## 17. Checklist triển khai

- [ ] Đã đo baseline: thời gian worker hữu ích, overhead setup/dispatch và metadata.
- [ ] Đã định nghĩa `P`, `C` và `K` riêng, hiểu đúng ý nghĩa `gridSize`.
- [ ] Đã đo workload điển hình, peak, phân bố file/ID và độ khó processor.
- [ ] Đã chọn target work units dựa trên chi phí thực, không chỉ số record.
- [ ] Đã gộp shard nhỏ khi overhead quá cao, đồng thời có cách split shard lớn nếu cần.
- [ ] Mỗi physical shard thuộc đúng một logical group; không mất/trùng range.
- [ ] Đã lưu **immutable work-group manifest** theo snapshot/JobInstance.
- [ ] `ExecutionContext` chỉ giữ metadata/tham chiếu nhỏ, không nhồi dữ liệu lớn.
- [ ] Group keys và mapping ổn định qua restart; `PartitionNameProvider` nếu cần.
- [ ] Reader multi-file/multi-range lưu checkpoint đúng theo transaction.
- [ ] Writer có transaction/idempotency và đối soát business output.
- [ ] Đã đo saturation của JobRepository, DB/API và broker/worker pool.
- [ ] Benchmark P ở các mức khác nhau với C, chunk size và input cố định.
- [ ] Có test crash/restart, skew, overflow, duplicate shard và manifest drift.
- [ ] SLA bao gồm setup, xử lý, validation, publish và recovery buffer.

## 18. Câu hỏi tự kiểm tra

1. Vì sao 1.000 partition trên tám workers có thể chậm hơn 80 partition trên cùng tám workers?
2. `P`, `C`, `K` và `gridSize` khác nhau thế nào?
3. Với overhead `h=200` ms/partition và work `w=50` ms/partition, tỷ lệ hữu ích là bao nhiêu?
4. Nếu muốn overhead không quá 5% với `h=200` ms, cần tối thiểu bao nhiêu giây work/partition theo mô hình đơn giản?
5. Vì sao tạo đúng tám partition khi có tám workers có thể khiến bảy workers rảnh sau khi một hot partition chậm?
6. Muốn xử lý 10.000 file rất nhỏ, vì sao có thể gộp nhiều file thành một logical partition?
7. Vì sao không thể gộp các khoảng ID rời nhau chỉ bằng `BETWEEN minId AND maxId`?
8. Partition có 100 file và worker crash tại file thứ 37. Cần checkpoint những thông tin gì để resume?
9. Tại sao tăng worker pods từ 8 lên 16 khi restart không cho phép tùy tiện đổi group keys?
10. Một shard lớn hơn target work rất nhiều nên xử lý thế nào khi heuristic chỉ gộp shard nhỏ?
11. DB pool pending tăng và throughput đứng yên khi tăng concurrency; nên đo gì trước khi tăng thêm partition?
12. Test nào chứng minh planner không làm mất/trùng dữ liệu khi listing object storage đổi thứ tự?
13. Vì sao `readCount` tăng không đồng nghĩa throughput nghiệp vụ tăng?
14. Nếu `P=32`, `C=8` và mỗi worker step dùng `chunk(500)`, tối đa bao nhiêu StepExecution hoạt động cùng lúc trong ví dụ local? Chunk size có nghĩa 500 thread không?
15. Nên dùng chỉ số nào để tìm điểm tối ưu giữa quá ít partition và quá nhiều partition?

**Gợi ý trả lời:** (1) Mỗi partition tốn setup/metadata/dispatch; quá nhiều phần nhỏ khiến overhead lớn. (2) P là số phần logic, C là số workers đồng thời, K là item/chunk, gridSize là hint. (3) `50/(50+200)=20%`. (4) `0,2×(1/0,05−1)=3,8` giây. (5) Không chia lại workload của hot partition khi nó đang chạy tuần tự. (6) Giảm StepExecution/open/close overhead. (7) Query sẽ lấy cả vùng không thuộc group. (8) Snapshot/manifest version, chỉ số file và vị trí item/cursor đã commit. (9) Metadata/checkpoint gắn với tên và mapping cũ. (10) Split shard nếu format/reader hỗ trợ, hoặc chấp nhận hot shard và thiết kế quanh nó. (11) Hikari active/pending, DB locks, transaction duration, API quotas, CPU/IOPS. (12) So group membership và tần suất từng shard ID sau sắp xếp ổn định. (13) Có thể đọc trước, retry, rollback hoặc thiếu kết quả commit. (14) Khoảng tám StepExecution đồng thời; chunk size không phải threads. (15) End-to-end duration, committed throughput, per-partition setup overhead, p95/p99/max skew, metadata pressure và restart SLA.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, `gridSize`, manager/worker, `Partitioner` và các mô hình mở rộng.
- [Spring Batch 5.2 Reference — Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cách `PartitionHandler` dispatch worker StepExecution và các điều kiện restart.
- [Spring Batch API 5.2 — Partitioner](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/Partitioner.html): `partition(int gridSize)` trả `Map<String, ExecutionContext>`.
- [Spring Batch API 5.2 — PartitionNameProvider](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/PartitionNameProvider.html): hợp đồng trả tên partition khi restart.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): quản lý `ItemStream`, `ExecutionContext` và checkpoint.
- [Spring Batch Reference — Multi-file Input](https://docs.spring.io/spring-batch/reference/readers-and-writers/multi-file-input.html): các lựa chọn reader khi một logical partition xử lý nhiều file.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): giới hạn JDBC connection pool và năng lực DB khi tăng concurrency.

**Điểm cốt lõi:** Partition quá nhỏ không chỉ làm tăng số task mà còn tăng metadata, dispatch, reader lifecycle và transaction overhead. **Đừng đồng nhất `gridSize` với số workers hoặc chunk size.** Hãy đo chi phí cố định của partition, phân tích skew, gộp những physical shards nhỏ vào logical partitions có manifest bất biến và dùng checkpoint/idempotency khi restart. Số partition tốt là mức giúp worker đủ việc và hoàn tất đúng SLA **mà không tiêu tốn phần lớn thời gian vào việc điều phối chính các partition ấy**.
