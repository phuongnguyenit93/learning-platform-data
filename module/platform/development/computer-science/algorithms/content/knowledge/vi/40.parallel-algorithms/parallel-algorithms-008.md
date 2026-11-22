# Chi phí đồng bộ, truyền dữ liệu và tạo tác vụ

**Thuật toán song song** không tự động chạy nhanh khi tăng số lõi hoặc chia một vòng lặp thành nhiều công việc. Thời gian thực tế còn chịu chi phí **tạo và quản lý tác vụ**, **chờ đồng bộ**, **truyền/di chuyển dữ liệu**, **tranh chấp bộ nhớ** và **mất cân bằng tải**. Các chi phí này có thể lớn hơn lượng tính toán tiết kiệm được, đặc biệt khi chia việc quá nhỏ, dùng quá nhiều tác vụ, trao đổi thông điệp liên tục hoặc bắt các luồng chờ nhau tại nhiều barrier.

Bài thuộc chủ đề **Thuật toán song song**. Mục tiêu là biết cách mô hình hóa, phân tích và thiết kế giảm **overhead** mà vẫn đảm bảo **tính đúng của chương trình có nhiều luồng hoặc tiến trình**. Ta sẽ phân biệt các đại lượng `work W`, `span S`, thời gian `T_P`, lượng dữ liệu trao đổi, số thông điệp, số tác vụ, số lượt đồng bộ; giải thích **Amdahl**, **work–span**, mô hình truyền thông `α+βn`, các nguồn tranh chấp và kỹ thuật chọn độ hạt tác vụ (*task granularity*).

Bài có chương trình **Java 17+ độc lập** dùng `ExecutorService`, `Future`, `CountDownLatch`, `CyclicBarrier` để cộng dãy số theo chunk và theo pha. Chương trình cũng có một **mô hình chi phí minh họa hoàn toàn xác định**: nó không đo nanosecond thực mà chỉ tính các tham số giả định, giúp thấy tại sao `grain=1` và `grain=N` đều có điểm yếu. Kết quả tổng được kiểm tra với oracle tuần tự trên các dữ liệu xác định/ngẫu nhiên.

## 1. Điều gì được tính là chi phí song song?

Giả sử ta có `N` công việc độc lập, `P` worker xử lý. Một phép tính lý tưởng có thể chia đều tải:

```text
useful computation ≈ total useful work / P.
```

Nhưng khi triển khai, thời gian còn gồm:

```text
T_parallel ≈ useful computation on critical path
           + task creation / scheduling
           + synchronization / waiting
           + communication / data movement
           + contention / memory stalls
           + any remaining serial processing.
```

Đây là **sơ đồ phân loại**, không phải đẳng thức cộng chính xác cho mọi chương trình: các phần có thể **chồng lấp** (ví dụ truyền dữ liệu bất đồng bộ cùng tính toán), và một số overhead đã khiến span tăng, nên cộng lại thiếu cẩn thận có thể **đếm trùng**.

Ví dụ, khi một worker bị chậm:

- Các worker khác có thể không có việc để làm (*idle*).
- Barrier khiến mọi worker đợi worker cuối.
- Worker tạo quá nhiều task làm nghẽn hàng đợi.
- Nhiều worker cùng cập nhật một counter gây tranh chấp lock.
- Dữ liệu bị chuyển qua NUMA nodes hoặc qua mạng.

**Tăng số worker chỉ cải thiện thời gian nếu phần việc song song đủ lớn và chi phí ngoài tính toán được kiểm soát.**

### 1.1. Cần tách thuật toán và hệ thống thực thi

Một thuật toán có thể có work/span tốt nhưng vẫn triển khai chậm vì runtime hoặc bố trí dữ liệu. Ngược lại, một phép đo nhanh không tự chứng minh độ phức tạp lý thuyết tốt hơn: cache state, CPU turbo, JIT, JVM warm-up, hệ điều hành, kích thước input và compiler đều ảnh hưởng.

Để học đúng, hãy ghi hai lớp:

1. **Mô hình thuật toán:** số phép toán, đường găng, số task, số lượt đồng bộ, số message và byte.
2. **Phép đo hệ thống:** thời gian wall-clock, CPU usage, throughput, queue wait, cache miss, network bandwidth, contention, allocation/GC.

Chương trình Java ở cuối chứng minh tính đúng của chia việc và **đếm mô hình**. Nó **không** cố giả vờ rằng một công thức “toyCostNs” là benchmark CPU thật.

## 2. Work `W`, span `S` và thời gian dùng P worker

Trong mô hình **computation DAG** (*directed acyclic graph*, đồ thị phụ thuộc tác vụ):

- `W` (*work* hay `T_1`) là **tổng lượng tính toán** nếu thực hiện tuần tự toàn bộ các nút DAG, thường đo bằng đơn vị thao tác.
- `S` (*span*, *critical-path length*, `T_∞`) là **tổng chi phí trên đường phụ thuộc dài nhất**; ngay cả vô hạn processor cũng không rút ngắn đường này.
- `P` là số processor/worker được dùng.
- `T_P` là thời gian chạy với P worker trong mô hình hoặc trên hệ thống cụ thể.

Hai cận dưới cơ bản của lịch thực thi không trùng chồng một công việc là:

```text
T_P >= W/P
T_P >= S

=> T_P >= max(W/P, S).
```

Đầu tiên vì P worker trong thời gian T không thể làm quá P*T đơn vị công việc. Thứ hai vì một chuỗi phụ thuộc dài S phải thực hiện theo thứ tự. Đây là **cận dưới**, không phải công thức luôn cho thời gian thực tế.

### 2.1. Parallelism vốn có

Đại lượng:

```text
parallelism = W/S
```

là mức song song trung bình lý tưởng. Nếu `W/S=8`, dùng 64 worker không thể kỳ vọng speedup 64 chỉ nhờ chia lịch, vì đường găng giới hạn speedup theo cận này.

Ví dụ cây cộng 8 số bằng 7 phép cộng:

```text
level 1: 4 phép cộng độc lập
level 2: 2 phép cộng độc lập
level 3: 1 phép cộng

work = 7 phép cộng.
span = 3 vòng cộng.
```

Nếu mỗi phép cộng có cùng chi phí và truyền dữ liệu bỏ qua, cây này có thể thực hiện trong 3 vòng với đủ worker. So với cộng tuần tự cần 7 phép cộng liên tiếp, nó giảm đường găng, nhưng phải sắp xếp/đồng bộ những vòng phụ thuộc.

### 2.2. Công việc không song song hóa được

Nếu 10% thời gian tuần tự bắt buộc thực hiện theo chuỗi, phần còn lại có thể chia đều hoàn hảo cho P worker và **bỏ qua overhead**, định luật Amdahl cho:

```text
speedup_ideal(P)
   = 1 / (s + (1-s)/P),

s = phần thời gian không song song hóa.
```

Với `s=0.10`, `P=4`:

```text
speedup = 1 / (0.10 + 0.90/4)
        = 1 / 0.325
        ≈ 3.076923.
```

Khi P tiến tới vô hạn, speedup có cận trên `1/s=10`, dù hệ thống có hàng nghìn lõi. Thực tế overhead còn làm speedup thấp hơn (hoặc có những hiệu ứng cache đặc biệt khiến phép so thực nghiệm khác giả định của Amdahl).

### 2.3. Amdahl và Gustafson không mâu thuẫn

**Amdahl** thường xét **kích thước bài toán cố định** và tỷ lệ công việc tuần tự cố định. **Gustafson** xét kịch bản tăng lượng công việc song song hóa khi tăng P, nhằm giữ thời gian giải ở một mức hữu ích. Một dạng scaled speedup với phần tuần tự đo trong thời gian song song là:

```text
S_scaled(P) = P - s*(P-1).
```

Không hoán đổi hai công thức nếu chưa xác định `s` được đo theo thời gian nào và có giữ input size không. Cả hai đều bỏ qua một số hiệu ứng hệ thống nếu chỉ sử dụng công thức lý tưởng.

## 3. Chi phí tạo, gửi và hoàn tất tác vụ

**Tác vụ** (*task*) là một đơn vị công việc có thể lập lịch. Nó khác với **luồng hệ điều hành** (*OS thread*).

Trong Java:

```text
Executors.newFixedThreadPool(4)
```

tạo một pool có tối đa bốn worker threads; mỗi lần:

```text
pool.submit(callable)
```

**gửi một tác vụ** tới pool. Gửi 4096 tác vụ **không đồng nghĩa** tạo 4096 thread. Tuy nhiên, mỗi task thường vẫn phải trả phí cho object/closure, queueing, dispatch, future/result và bookkeeping.

### 3.1. Mô hình chi phí task đơn giản

Đặt:

```text
K   = số task.
tau = thời gian chi phí trung bình cho mỗi lần tạo/gửi task.
C   = chi phí tính toán hữu ích tổng cộng.
P   = số worker.
```

Một mô hình sơ lược:

```text
T ≈ C/P + K*tau + overhead_other.
```

Ở đây `K*tau` giả định chi phí gửi/điều phối có một phần **tuần tự đáng kể**. Nếu scheduling được phân tán hoặc chồng lấp, không nên đếm toàn bộ `K*tau` như một đoạn tuần tự chắc chắn. Ngược lại, nếu một thread duy nhất tạo mọi task vào một queue nóng, hệ số này có thể gây nghẽn thật.

**Điểm quan trọng:** Một bài toán có `N` phép cộng đơn giản nhưng tạo `N` task một phép cộng có thể tốn tiền scheduling nhiều hơn chính phép cộng.

### 3.2. Độ hạt tác vụ (*grain size*)

`grain` là số đơn vị xử lý mỗi task. Với N phần tử và mỗi chunk tối đa g phần tử:

```text
K = ceil(N/g).
```

Hai cực đoan:

- **g quá nhỏ**: K rất lớn, nhiều enqueue/dequeue/Future, nhiều kết quả phải tổng hợp; overhead chiếm ưu thế.
- **g quá lớn**: K quá nhỏ so với P, nhiều worker nhàn rỗi, độ cân bằng tải kém và không dùng được tài nguyên.

Một quy tắc thực dụng là **mỗi task phải có lượng tính toán hữu ích đủ lớn để amortize chi phí task**, đồng thời nên có đủ số task để cân bằng tải (thường nhiều hơn P nếu thời lượng task biến động). Không có một g tối ưu duy nhất cho mọi CPU, JVM, loại công việc và dữ liệu.

### 3.3. Task count, thread count và task queue khác nhau

| Đại lượng | Vai trò | Sai lầm hay gặp |
| --- | --- | --- |
| Số thread pool P | Worker thực sự có thể chạy đồng thời | Coi nó bằng số task |
| Số task K | Số đơn vị scheduling được gửi | Coi task luôn miễn phí |
| Grain g | Khối lượng công việc mỗi task | Coi g=1 luôn nhiều song song hơn |
| Queue length | Số task đang chờ | Coi queue dài là CPU đang làm tốt |
| Pending `Future` | Kết quả chưa được thu | Coi `get()` luôn trả ngay |
| Thread creation | Tạo worker OS/JVM | Coi `submit()` luôn tạo thread mới |

Thực hành tốt: **tái sử dụng thread pool**, hạn chế số task quá nhỏ, dùng bounded work queues khi backpressure quan trọng và đo độ dài/độ trễ hàng đợi trên tải thật.

## 4. Chi phí đồng bộ: locks, atomics, barriers, futures

**Đồng bộ** đảm bảo các thread nhìn thấy dữ liệu/đi qua các pha theo một thứ tự cần thiết. Nó có vai trò bảo đảm **correctness** và **memory visibility**, nhưng cũng tạo chi phí.

### 4.1. Tranh chấp khóa (*lock contention*)

Ví dụ không tốt:

```java
synchronized (lock) {
    globalSum += value;
}
```

nếu mọi worker khóa lại **cho từng phần tử**. Một triệu phần tử có thể tạo một triệu lượt lock/unlock và các worker tranh quyền vào đoạn critical section. Nếu lock giữ quá lâu, phần này gần như bị tuần tự hóa.

Thiết kế tốt hơn cho phép cộng:

```text
Mỗi worker tính localSum trong biến riêng.
Cuối cùng chỉ hợp nhất P partial sums.
```

Lúc đó số thao tác cần đồng bộ/gộp giảm từ N lần cập nhật chia sẻ xuống cỡ P kết quả. Tuy nhiên phải lưu ý **tràn số**, **thứ tự tính toán dấu phẩy động** và tính kết hợp của toán tử.

### 4.2. Atomic không có nghĩa miễn phí

`AtomicLong.incrementAndGet()` tránh một số vấn đề dữ liệu race, nhưng nhiều worker cập nhật **cùng một vị trí atomic** vẫn có thể gây tranh chấp cache line và serialization do thao tác atomic/read-modify-write. Với tần suất cao, dùng **local aggregation**, `LongAdder` trong những tình huống phù hợp, hoặc sharding counters có thể giảm tranh chấp.

**Không đổi AtomicLong thành long thường** trên dữ liệu chia sẻ có nhiều writer rồi hy vọng xác suất race thấp. Điều đó làm sai tính đúng. Thay đổi kỹ thuật đồng bộ phải đi kèm một lý do memory-safety/happens-before cụ thể.

### 4.3. Barrier — mọi worker đợi worker chậm nhất

Một **barrier** giữa các pha yêu cầu tất cả P worker **đến điểm hẹn** trước khi bất kỳ worker nào tiếp tục sang pha sau. Nếu thời gian công việc của worker j trong pha t là `C_{t,j}`, thì kể cả overhead barrier bằng 0:

```text
duration of phase t >= max_j C_{t,j}.
```

Các worker hoàn thành sớm phải chờ. Cộng nhiều pha:

```text
T >= SUM_t max_j C_{t,j}
```

trong mô hình các pha tuần tự. Nếu có q barrier thực tế, thêm chi phí đồng bộ, thức dậy và scheduling tùy runtime. Có thể hình dung:

```text
T_phase ≈ max_j(C_j) + T_barrier(P).
```

Đây là mô hình mô tả, không phải hằng số bảo đảm. Dữ liệu lệch và work imbalance làm `max_j` lớn hơn trung bình, tăng thời gian chờ của những worker khác.

### 4.4. Barrier trong Java

`CyclicBarrier(P)` cho P worker gọi `await()` để chuyển qua pha kế tiếp. Nó khác:

- `CountDownLatch`: cổng **một lần**; các thread chờ cho đến khi số đếm giảm về 0, không reset tự động.
- `Future.get()`: đợi **một tác vụ cụ thể** hoàn tất và lấy kết quả (hoặc ngoại lệ).
- `Phaser`: đồng bộ pha linh hoạt hơn khi số bên tham gia có thể thay đổi theo cơ chế đăng ký/hủy đăng ký.

Trong mã mẫu:

```text
4 workers
4 phases
=> 16 lần worker đến barrier
=> 4 barrier completions.
```

Đây là số sự kiện **logic** đã kiểm tra bằng `AtomicInteger`, không phải số nanosecond chờ.

### 4.5. Đồng bộ bảo đảm thứ tự, không bảo đảm nhanh

Barrier có thể cần thiết để đảm bảo mọi worker hoàn thành pha tính trước khi dùng kết quả pha ấy. Bỏ barrier mà không thay bằng dependency management phù hợp có thể làm thuật toán đọc dữ liệu chưa sẵn sàng.

Ngược lại, thêm barrier vào mỗi phép cộng sẽ đồng bộ quá mức. Hãy đặt barrier ở **ranh giới phụ thuộc thực sự**, không dùng nó làm cách “an toàn tuyệt đối” cho mọi đoạn code.

## 5. Chi phí truyền dữ liệu: mô hình `alpha–beta`

Trong hệ phân tán hoặc parallel computing có truyền thông điệp, một mô hình cổ điển cho một thông điệp chứa b byte:

```text
T_message(b) ≈ alpha + beta*b.
```

Trong đó:

- `alpha` là **latency khởi động** một thông điệp (*message startup/latency*).
- `beta` là **thời gian truyền trên một byte**, liên quan nghịch đảo băng thông hiệu dụng.
- `b` là số byte payload trong thông điệp.

Nếu có q thông điệp với tổng payload D byte và không có chồng lấp:

```text
T_comm ≈ q*alpha + D*beta.
```

**Nhiều thông điệp nhỏ** có thể đắt vì phải trả `alpha` nhiều lần. **Gộp thông điệp** thường giảm số lần startup, nhưng phải cân bằng thêm độ trễ chờ gom và mức độ song song truyền tải.

### 5.1. Ví dụ số học minh họa

Giả sử **chỉ để làm ví dụ**, không phải đo mạng thật:

```text
q = 6 messages.
D = 4096 bytes total.
alpha = 1500 ns/message.
beta  = 2 ns/byte.
```

Khi đó:

```text
startup = 6 * 1500 = 9000 ns.
payload = 4096 * 2 = 8192 ns.

T_comm_model = 17192 ns.
```

**Cảnh báo:** `alpha=1500 ns`, `beta=2 ns/byte` là giả định do người thiết kế mô hình chọn. Một JVM ứng dụng, mạng Ethernet, InfiniBand, NVLink hoặc bộ nhớ NUMA không thể tự nhận các con số này là giá trị thật. Để dự báo thời gian phải hiệu chuẩn bằng đo đạc theo kích thước message và topology.

### 5.2. Gộp message có ích khi nào?

Giả sử cần gửi 1000 bản ghi tới cùng một máy. Gửi từng record thành message riêng sẽ phát sinh khoảng 1000 lần `alpha`. Nếu gom thành 10 message mỗi message 100 record, startup chỉ còn 10 lần. Tuy nhiên, nếu chờ gom đủ một batch làm tăng latency xử lý từng record, cách gom quá lớn có thể không phù hợp với hệ thống thời gian thực.

**Tối ưu thông điệp** cần xét cùng lúc: tổng byte, số message, latency nhạy cảm, throughput, backpressure và khả năng chồng lấp transmission/computation.

### 5.3. Shared memory khác distributed memory

Trong `ExecutorService` trên **một JVM**, các task có thể đọc chung một `int[]` mà không có thông điệp mạng và không cần sao chép toàn bộ mảng cho mỗi task. Tuy vậy:

- Dữ liệu vẫn phải được đưa qua **cache hierarchy**.
- Các worker ở NUMA nodes khác nhau có thể chịu chi phí truy cập bộ nhớ không đồng nhất.
- Nhiều writer có thể tạo **cache-coherence traffic**.
- Cache line bị ping-pong khi các core sửa cùng vùng nhớ.
- Sao chép mảng hoặc serialize data vẫn tạo CPU/memory bandwidth overhead.

Vì thế `alpha–beta` mô hình message **không tự thay thế** phân tích memory bandwidth/cache trong shared-memory parallelism. Cần nói rõ hệ thống đang là threads cùng bộ nhớ, tiến trình khác bộ nhớ, hay cluster nhiều máy.

## 6. False sharing, cache coherence và locality

**False sharing** xảy ra khi hai thread sửa **những biến khác nhau** nhưng chúng cùng nằm trong **một cache line**. Dù không có data race logic trên cùng biến, cache-coherence protocol có thể buộc cache line liên tục chuyển quyền sở hữu giữa cores, khiến chương trình chậm.

Ví dụ:

```text
Worker A ghi counters[0].
Worker B ghi counters[1].

Nếu hai phần tử thuộc cùng cache line,
có thể xảy ra false sharing.
```

Đây là **rủi ro hiệu năng**, không tự làm kết quả sai. Còn **true sharing** là nhiều thread thực sự truy cập/cập nhật cùng một vị trí dữ liệu, có thể đòi lock/atomic.

Biện pháp thường dùng:

- Dùng **thread-local partial counters** rồi reduction ở cuối.
- Phân tách hot writable data theo cache lines nếu profiling xác nhận false sharing.
- Giảm số lần ghi chia sẻ, dùng immutable input và kết quả theo worker.
- Cân nhắc padding/alignment khi dữ liệu lớn và hotspot rõ ràng.
- Đo performance counters/cache misses trên runtime thực.

**Không tự khẳng định** Java object/array luôn có alignment nhất định hoặc mọi cặp `long[]` liền nhau chắc chắn cùng cache line. Bố trí vật lý do JVM/CPU quyết định; cần đo để xác nhận.

### 6.1. Truyền dữ liệu có thể lớn hơn lượng tính toán

Nhân ma trận hoặc phép biến đổi tensor có thể có lượng tính toán rất lớn và dùng blocking/tiling để tăng reuse, trong khi phép cộng đơn giản một mảng thường bị giới hạn bởi băng thông bộ nhớ sau một số lõi. Khi tăng P vượt **memory bandwidth saturation**, tổng throughput không còn tăng tuyến tính, dù các phép tính độc lập.

Định lý work–span dựa trên **đơn vị cost được mô hình hóa**; nếu không tính bandwidth/cache thì cận work/span vẫn là khung lý thuyết nhưng không dự đoán đầy đủ thời gian phần cứng.

## 7. Cây reduction và số lượt đồng bộ

Cộng P giá trị từ P worker có ít nhất P−1 phép cộng để tạo một tổng (với toán tử cộng hai ngôi), nhưng **đường găng** có thể được rút ngắn bằng cây:

```text
P=8 partial sums:

Round 1:
  (0+1), (2+3), (4+5), (6+7)
  => 4 kết quả.

Round 2:
  sum01 + sum23
  sum45 + sum67
  => 2 kết quả.

Round 3:
  sum0123 + sum4567
  => 1 tổng cuối.
```

Một cây nhị phân cân bằng trên P=8 đầu vào có:

```text
combine operations = 7.
dependency rounds  = log2(8) = 3.
```

Nếu thực hiện trên nhiều tiến trình có message, một tree gather đơn giản có thể truyền tổng **P−1 messages**, còn số vòng trên **critical path** chỉ cỡ `ceil(log2 P)`. Tổng messages và số vòng **khác đại lượng**, không được coi đều bằng P−1.

### 7.1. Thông tin truyền có thể nhỏ

Nếu mỗi worker giữ local sum kiểu `long`, ta chỉ cần gửi **một số 8 byte** cho mỗi bước gộp, thay vì gửi toàn bộ phần dữ liệu mà worker đã xử lý. Local aggregation giảm khối lượng truyền thông.

Tuy nhiên, đối với `GROUP BY` trên khóa rất đa dạng, partial result có thể là một bảng lớn chứ không chỉ một long. Khi đó chi phí serialize, hash-map merge và network bytes cần được tính riêng.

### 7.2. Cây giảm span nhưng vẫn cần dependency

Không thể cộng level 3 trước khi các tổng của level 2 hoàn thành. Nếu thực thi đa luồng, phải quản lý đúng mối phụ thuộc, ví dụ barrier theo level hoặc futures phụ thuộc. Một cây tính **tuần tự** trong Java chỉ mô phỏng reduction DAG; số “3 vòng” của cây **không có nghĩa** bản thân hàm mô phỏng đang dùng 8 threads.

## 8. Mất cân bằng tải và work stealing

Cho P worker với lượng việc hữu ích `C_1,...,C_P`. Nếu không thể chuyển việc giữa workers:

```text
T_compute ≈ max_j C_j
```

và tổng mức sử dụng hữu ích có thể rất kém khi một worker xử lý gần như toàn bộ dữ liệu. Cân bằng bằng cách chia nhiều chunk cho scheduler có thể giảm imbalance, nhưng lại tăng **K*tau**.

Một số runtime dùng **work stealing**: worker hết việc có thể lấy task từ hàng đợi của worker khác. Nó giúp giải quyết work imbalance trong nhiều DAG nhưng:

- Steal có chi phí queue/synchronization.
- Task quá nhỏ vẫn làm scheduling overhead lớn.
- Dữ liệu đi theo task có thể mất locality.
- Một nhánh phụ thuộc dài vẫn giới hạn span.

Không nên nói “work stealing luôn đạt cân bằng hoàn hảo” hoặc “cứ tạo hàng triệu task nhỏ là scheduler sẽ tự giải quyết”.

### 8.1. Phân chia tĩnh vs động

**Static scheduling** thường phù hợp nếu chi phí mỗi phần tử gần giống nhau và dữ liệu được phân bố đều; có lợi cho locality, ít overhead.

**Dynamic scheduling** thường phù hợp nếu thời lượng task biến động mạnh; mỗi worker lấy công việc tiếp theo khi rảnh, giúp cân bằng tốt hơn nhưng cần scheduler/queue.

Trong Java demo, mỗi task xử lý một chunk số nguyên; chi phí mỗi phần tử gần đồng đều. Việc tăng số task đến 4096 là để quan sát mô hình overhead, **không phải vì dữ liệu này cần cân bằng động phức tạp**.

## 9. Chọn grain theo ngân sách và mô hình đơn giản

Giả sử:

```text
N = 4096 integers.
P = 4 worker threads.

c   = 10 ns / record (toy useful-work cost).
tau = 200 ns / submitted task (toy serialized overhead).
b   = 1000 ns / barrier (toy overhead).
q   = 2 barriers.
```

Với chunk g, số task K:

```text
K = ceil(N/g).
```

Mô hình minh họa **có tính bi quan**:

```text
T_toy(g) =
    ceil(K/P)*g*c
    + K*tau
    + q*b.
```

Giải thích điều kiện:

1. `ceil(K/P)*g*c` tính **cận trên thô** cho thời gian tính nếu các task gần như đầy g record và được chia theo từng wave P task.
2. `K*tau` giả định toàn bộ overhead gửi task bị **tuần tự hóa** ở một nguồn gửi.
3. `q*b` gộp chi phí hai barrier lý thuyết, không cộng chênh lệch chờ vì load imbalance riêng.
4. Bỏ qua cache, JIT, GC, CPU turbo, I/O và truyền dữ liệu khác.

Vì vậy kết quả **không được** gọi là thời gian chạy thật hoặc benchmark. Nó là một ví dụ số học cho việc tồn tại **điểm cân bằng grain**.

| Grain g | Task K | Khối lượng tính trên đường găng theo mô hình | Phí gửi task | Barrier | Tổng toy ns |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4096 | 10.240 | 819.200 | 2.000 | 831.440 |
| 64 | 64 | 10.240 | 12.800 | 2.000 | 25.040 |
| 512 | 8 | 10.240 | 1.600 | 2.000 | 13.840 |
| 4096 | 1 | 40.960 | 200 | 2.000 | 43.160 |

**Đọc bảng:** g=1 chia cực nhỏ nhưng phải trả 4096 lần phí gửi; g=4096 chỉ có một task nên **ba worker còn lại không thể chia phần việc đó**; g=512 cho tám task, đủ hai wave cho bốn worker và phí gửi thấp trong **mô hình giả định này**.

Đừng tự suy “g=512 luôn tối ưu” từ bảng. Trên workload có cache miss, độ lệch task, CPU load, `ForkJoinPool` hoặc GPU, grain tốt nhất có thể khác. Cần đo bằng benchmark nghiêm túc.

### 9.1. Tại sao grain tốt phụ thuộc chi phí mỗi phần tử?

Nếu mỗi record tốn nhiều phép xử lý (ví dụ giải mã nén, xử lý ảnh), `g*c` lớn nên phí `tau` dễ amortize ngay cả khi grain tương đối nhỏ. Nếu record chỉ là một phép cộng, tạo một task mỗi record gần như luôn không hợp lý trên JVM thông thường.

Một nguyên tắc ban đầu:

```text
useful work per task >> typical scheduling cost
```

nhưng tỷ lệ “>>” cần chọn theo latency, tính biến động và mục tiêu throughput. Không có công thức kì diệu chỉ từ N, P mà bỏ qua c, tau và locality.

## 10. Ví dụ thực: 4096 số nguyên và bốn luồng

Dữ liệu minh họa:

```text
data[i] = (i mod 17) - 8
for i=0..4095.
```

Các giá trị chạy từ −8 tới 8. Cứ đủ 17 phần tử, tổng bằng 0; 4096 = 17×240 +16 nên 16 phần tử cuối có tổng −8. Do đó:

```text
sequentialSum(data) = -8.
```

Đây là kết quả **có thể chứng minh bằng tay**, không phụ thuộc thứ tự thread.

### 10.1. Chia chunk và dùng `Future`

Giả sử `grain=64`:

```text
Task 0: data[0..63]
Task 1: data[64..127]
...
Task 63: data[4032..4095]
```

Có đúng:

```text
K=ceil(4096/64)=64 tasks.
```

Mỗi task tính `long localSum` trong phạm vi riêng. `Future<Long>` giữ kết quả của task đó. Thread gửi task duyệt danh sách future và cộng các kết quả theo thứ tự vào một biến `sum` cục bộ.

**Không có nhiều worker cùng ghi một `globalSum`**, nên không cần lock theo từng phần tử. `Future.get()` đợi hoàn thành và truyền kết quả, có quan hệ *happens-before* phục vụ visibility theo hợp đồng Java Concurrency.

### 10.2. Một `CountDownLatch` không phải 64 barriers

Trong demo có:

```java
CountDownLatch start = new CountDownLatch(1);
```

Các task đợi latch trước khi xử lý chunk. Sau khi submit, thread chính gọi `start.countDown()` để mở cổng cho tất cả. Đây là một **one-shot start gate**, không phải barrier cuối mỗi chunk. Nhiều task có thể hoàn thành trong bất kỳ thứ tự nào; thread chính lấy `Future.get()` khi thu kết quả.

Lưu ý: một latch này **không bảo đảm mọi task cùng bắt đầu đúng một nanosecond**; pool có bốn worker, nên các task còn lại chỉ được chạy khi worker rảnh. Nó cũng không biến chương trình thành benchmark đo đồng bộ chuẩn.

### 10.3. Barrier cho nhiều pha

Một ví dụ thứ hai có:

```text
4 workers.
4 phases.
Mỗi worker xử lý một chunk độc lập trong mỗi phase.
Mỗi phase kết thúc bằng barrier.await().
```

Sau 4 pha có 16 lượt worker đi tới barrier và 4 barrier completions. Mỗi worker cộng vào `partials[id]` riêng của mình; cuối cùng thread chính lấy kết quả từ futures và cộng bốn partials. Không có tình huống hai worker cố ý ghi cùng một ô partial.

**Điều kiện cực quan trọng:** Nếu tạo pool chỉ có **2 threads** nhưng barrier cần **4 parties** và bốn task dài hạn cùng nằm trong pool đó, hai task chạy có thể chờ hai task chưa được scheduled — tạo nguy cơ deadlock/starvation. Demo dùng đúng `workers` thread pool cho đúng `workers` long-lived task tham gia barrier.

## 11. Bài toán có giao tiếp: giảm dữ liệu trước khi truyền

Trong hệ có nhiều máy, đưa toàn bộ dữ liệu về một coordinator để cộng có thể gây **communication bottleneck**. Một thiết kế tốt hơn:

```text
Map / local process:
    read assigned records
    localSum = sum(records)
    send one localSum

Reduction:
    combine partial sums in a tree
```

Nếu mỗi worker có N/P số nguyên 8 byte, gửi toàn bộ dữ liệu về coordinator có thể truyền cỡ `8N` byte. Gửi một số `long` từ mỗi worker có payload chỉ `8P` byte, giảm lượng dữ liệu khi `N>>P`. Đổi lại phải đảm bảo dữ liệu đã được đặt tại worker hợp lý và phép cộng/aggregation có nghĩa.

### 11.1. Cây truyền không đồng nghĩa 0 overhead

Một reduction tree vẫn có:

- Serialization hoặc encoding partials.
- Message startup.
- Truyền payload qua các link.
- Đồng bộ phụ thuộc giữa các vòng gộp.
- Phần kết quả cuối có thể cần **broadcast** ngược lại mọi worker.
- Cân bằng node và lỗi mạng nếu hệ phân tán thực.

Đối với mô hình đơn giản, `P=8` có 7 lần combine, đường găng 3 round. Nếu mỗi round truyền một long 8 byte và alpha/beta cố định, một cận minh họa cho **critical-path communication** là `3*(alpha + 8*beta)` khi không overlap. Tổng payload toàn cây khác số byte trên một đường găng; cần tránh nhầm hai loại chỉ số.

### 11.2. Broadcast và all-reduce

**Reduce:** thu partials về một root hoặc một nơi sở hữu kết quả.

**Broadcast:** phát một giá trị từ root cho các tiến trình khác.

**All-reduce:** mọi tiến trình cần kết quả gộp cuối. Nó thường đòi trao đổi nhiều hơn reduce một chiều, tùy thuật toán/tree/ring và topology. Không thể chỉ dùng công thức một-way reduction rồi tuyên bố đã đo all-reduce.

Trong môi trường MPI/NCCL/RPC, các collective có thuật toán nội bộ khác nhau; phải đo hoặc mô hình đúng primitive đang sử dụng.

## 12. Overhead của di chuyển dữ liệu và cache

Ngay cả khi chia task lý tưởng, dữ liệu có thể không ở nơi worker xử lý:

- Dữ liệu cache trước đó thuộc lõi khác.
- Thread di chuyển giữa CPUs, làm mất warm cache.
- NUMA node remote tốn thêm latency/bandwidth.
- Cấu trúc dữ liệu theo con trỏ gây nhiều cache misses.
- Nhiều worker cạnh tranh memory controller.
- Mỗi task sao chép input lớn vào mảng riêng.
- Output được ghi vào một shared structure dẫn tới coherence traffic.

**Giảm task overhead không giải quyết tất cả vấn đề**: một task quá lớn có thể không dùng được P cores; task nhỏ nhưng có locality tốt có thể chạy hiệu quả trong runtime với batching; task vừa cỡ nhưng gửi qua mạng toàn bộ dữ liệu cũng có thể thua xử lý tại nơi dữ liệu đang lưu.

### 12.1. Tính toán gần dữ liệu

Một nguyên tắc quan trọng của data locality:

```text
Move computation toward data
instead of moving huge data toward computation
```

Ví dụ trong phân tán, nếu các shard đã chứa dữ liệu, hãy tính partial aggregates tại shard rồi gửi kết quả nhỏ. Trong shared memory, chia mảng theo các đoạn liên tục giúp cache/prefetch tốt hơn so với truy cập vòng quanh các phần tử phân tán.

### 12.2. Không tự nghĩ network là “miễn phí” vì async

Một API gửi bất đồng bộ cho phép **overlap** nhưng không làm mất băng thông hữu hạn hoặc startup latency. Nếu thuật toán chờ `Future.get()` ngay sau mỗi send, nó gần như biến thông điệp async thành synchronous. Để overlap thật, cần có **công việc độc lập** thực thi trong lúc message đang di chuyển.

## 13. Synchronization correctness: data race, visibility, deadlock

Hiệu năng chỉ có ý nghĩa nếu kết quả đúng. Ba loại lỗi quan trọng:

### 13.1. Data race

Nếu nhiều worker làm:

```java
counter++;
```

trên cùng biến thường, phép đọc–cộng–ghi không nguyên tử. Có thể mất cập nhật (*lost update*). Nếu không có quan hệ đồng bộ phù hợp, mã còn có vấn đề visibility theo Java Memory Model. **Không sửa bằng cách chạy test nhiều lần và thấy số đúng**.

Giải pháp: lock/atomic phù hợp, hoặc tốt nhất với phép cộng là **worker-local partials rồi reduce**.

### 13.2. Thiếu happens-before

Một worker sửa shared array rồi worker khác đọc mà không có đồng bộ hoặc publication phù hợp có thể đọc trạng thái không như dự tính. `Future.get()`, latch, barrier, lock và volatile/atomic có các cơ chế memory ordering cụ thể. Hãy dùng đúng primitive cho dependency.

Không nói barrier “đẩy mọi cache line về RAM vật lý”. Java Memory Model nêu **thứ tự nhìn thấy thao tác**, không hứa một kiến trúc cache vật lý cố định.

### 13.3. Deadlock hoặc thread-pool starvation

Một task chạy trên pool kích thước 1 rồi submit task thứ hai vào **cùng pool** và gọi `get()` để đợi task thứ hai; task thứ hai không được scheduled vì thread duy nhất đang bị chiếm. Đây là **thread-pool starvation deadlock**.

Tương tự, barrier yêu cầu nhiều parties hơn số task có thể đang chạy là nguy hiểm nếu các task không thể thoát khỏi await. Cần thiết kế pool, dependency và barrier parties nhất quán, hoặc dùng framework fork/join hỗ trợ blocking/dependencies đúng cách.

### 13.4. Exception trong task không nên bị mất

`ExecutorService.submit()` có thể lưu exception của task trong `Future`. Nếu bỏ qua `get()`, chương trình có thể chỉ thấy “chưa có kết quả” mà không biết task đã thất bại. Trong ví dụ, tất cả futures đều được `get()` nên lỗi/exception được báo ra, thay vì âm thầm coi tổng thiếu là kết quả đúng.

## 14. Đo performance song song đúng cách

Một mô hình chi phí minh họa khác với một benchmark. Nếu muốn benchmark chính xác trên JVM:

1. Chọn input đại diện và đủ lớn để không bị startup/JIT chi phối hoàn toàn.
2. Khởi động/warm-up trước khi đo, phân biệt setup/thread-pool creation và phần việc muốn so.
3. Dùng công cụ benchmark phù hợp như **JMH** cho microbenchmark khi có thể.
4. Đảm bảo kết quả được tiêu thụ/kiểm chứng để tránh compiler tối ưu bỏ việc.
5. Đo nhiều lần, nhiều kích thước và báo phân bố (median/percentiles), không chỉ một số nhỏ nhất.
6. Giữ nguyên số cores, CPU governor/turbo/thermal, heap, GC, container limits và tải nền.
7. Đo **T1**, **TP**, speedup, throughput, CPU usage, context switches, task queue và memory/cache traffic nếu có công cụ.
8. Với mạng, đo alpha/beta thực tế theo message size, concurrency, topology, serialization.
9. Báo rõ warm/cold cache và placement của dữ liệu.
10. So sánh **bản tuần tự tốt** với bản song song, không cố làm bản tuần tự kém để có speedup đẹp.

### 14.1. Speedup và efficiency

Với cùng công việc đầu vào:

```text
speedup(P)    = T1 / TP
efficiency(P) = speedup(P) / P.
```

Nếu `T1=100 ms`, `TP=40 ms` với P=4:

```text
speedup = 2.5
efficiency = 2.5/4 = 0.625 = 62.5%.
```

Hiệu quả dưới 100% không tự cho biết **nguồn** chi phí: có thể do serial fraction, sync, memory bandwidth, queueing hoặc workload imbalance. Cần profiling/measurement cụ thể.

### 14.2. Có thể thấy superlinear speedup?

Trong một số phép đo, `speedup(P)>P` xảy ra do input cache fit tốt hơn khi chia, paging khác đi hoặc so bản tuần tự/bản song song có hiệu ứng bộ nhớ khác. Điều đó **không mâu thuẫn** một cận lý tưởng `W/P` nếu mô hình W và đơn vị cost của phép đo đã thay đổi do memory behavior. Trước khi tuyên bố cải tiến thuật toán, cần kiểm tra tính công bằng và thiết kế phép đo.

### 14.3. Không đo ns thật bằng `toyCostNs`

Trong chương trình minh họa:

```text
toyCostNs = giả định c, tau, b
```

Không có lời gọi `System.nanoTime()` để đo hiệu năng. Kết quả luôn giống nhau ở mọi máy vì **chỉ tính mô hình số học**, không phải vì Java chạy với tốc độ không đổi. Dùng các giá trị ấy để **lý giải trade-off**, rồi đo thật riêng nếu cần chọn cấu hình production.

## 15. Java 17+ độc lập: chia chunk, barrier và mô hình chi phí

Tên tệp **`ParallelOverheadDemo.java`**. Mã chỉ dùng Java standard library, không cần Maven hoặc thư viện bên ngoài.

### 15.1. Những thành phần quan trọng

- `sequentialSum`: oracle tuần tự dùng `long`, phép cộng `Math.addExact`, không làm tràn âm thầm.
- `parallelChunkSum`: chia mảng thành những chunk liên tục, gửi vào `Executors.newFixedThreadPool(workers)`, dùng `CountDownLatch` làm start gate, cộng `Future<Long>` sau khi task hoàn thành, giải phóng pool.
- `parallelPhases`: dùng đúng `workers` long-lived tasks trong đúng số thread của pool. Mỗi task xử lý phần việc riêng ở từng pha, đến `CyclicBarrier.await()`; barrier action tăng số lượt complete trong `AtomicInteger`.
- `modelNanoseconds`: **mô hình chi phí toy**, không phải profiler. Phân biệt số task, wave, phí submit và barrier.
- `communicationNs`: tính `q*alpha + bytes*beta` với số nguyên kiểm tra overflow.
- `treeReduce`: mô phỏng tuần tự **DAG reduction hình cây**; không giả vờ đã chạy 8 thread.
- `randomOracleTests`: 180 mảng ngẫu nhiên, số worker/grain khác nhau, so với oracle; 200 cây reduction trên mảng độ dài lũy thừa của hai, so với tổng tuần tự.

**Hợp đồng của demo:**

- `workers>=1`, `grain>=1`.
- Phép cộng dùng `long`; các giá trị trong ví dụ được chọn để không overflow, và `Math.addExact` phát hiện nếu có.
- Với `parallelPhases`, kích thước mảng phải chia hết `workers*phases` cho ví dụ căn chỉnh đơn giản này; phiên bản production có thể xử lý chunk cuối không đầy.
- Bộ dữ liệu được đọc chung, không bị worker sửa, nên không cần copy cả mảng cho mỗi task.
- Các kết quả in deterministic. **Không in thời gian thực/CPU benchmark**, vì thứ tự scheduling và hiệu năng phụ thuộc môi trường.

### 15.2. Mã Java chạy đầy đủ

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ParallelOverheadDemo {
    record SumResult(long sum, int tasks, int workers, int grain) {}

    static long sequentialSum(int[] data) {
        long sum = 0;
        for (int x : data) sum = Math.addExact(sum, x);
        return sum;
    }

    static SumResult parallelChunkSum(
            int[] data, int workers, int grain) throws Exception {
        if (workers < 1 || grain < 1) {
            throw new IllegalArgumentException("workers/grain must be positive");
        }
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Long>> results = new ArrayList<>();
        try {
            for (int from = 0; from < data.length; from += grain) {
                final int lo = from;
                final int hi = Math.min(data.length, from + grain);
                results.add(pool.submit(() -> {
                    start.await();
                    long local = 0;
                    for (int i = lo; i < hi; i++) {
                        local = Math.addExact(local, data[i]);
                    }
                    return local;
                }));
            }
            start.countDown();
            long sum = 0;
            for (Future<Long> f : results) {
                sum = Math.addExact(sum, f.get());
            }
            return new SumResult(sum, results.size(), workers, grain);
        } finally {
            start.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Tasks did not terminate");
            }
        }
    }

    record BarrierResult(long sum, int phases, int arrivals, int trips) {}

    static BarrierResult parallelPhases(
            int[] data, int workers, int phases) throws Exception {
        if (workers < 1 || phases < 1
                || data.length % (workers * phases) != 0) {
            throw new IllegalArgumentException("Need aligned worker phases");
        }
        AtomicInteger trips = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                workers, trips::incrementAndGet);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        long[] partials = new long[workers];
        List<Future<?>> jobs = new ArrayList<>();
        int chunk = data.length / (workers * phases);
        try {
            for (int worker = 0; worker < workers; worker++) {
                final int id = worker;
                jobs.add(pool.submit(() -> {
                    try {
                        for (int phase = 0; phase < phases; phase++) {
                            int lo = (phase * workers + id) * chunk;
                            long local = 0;
                            for (int i = lo; i < lo + chunk; i++) {
                                local = Math.addExact(local, data[i]);
                            }
                            partials[id] = Math.addExact(partials[id], local);
                            barrier.await();
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    } catch (BrokenBarrierException ex) {
                        throw new RuntimeException(ex);
                    }
                }));
            }
            for (Future<?> f : jobs) f.get();
            long sum = 0;
            for (long value : partials) sum = Math.addExact(sum, value);
            return new BarrierResult(
                    sum, phases, phases * workers, trips.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Phase tasks not terminated");
            }
        }
    }

    // Toy cost model, not a JVM timing benchmark.
    // ceil(tasks/workers) whole chunks lie on the critical worker;
    // all task submission overhead is pessimistically serialized.
    static long modelNanoseconds(int n, int workers, int grain,
            long computeNsPerItem, long taskSubmitNs,
            int barriers, long barrierNs) {
        if (n < 0 || workers <= 0 || grain <= 0
                || computeNsPerItem < 0 || taskSubmitNs < 0
                || barriers < 0 || barrierNs < 0) {
            throw new IllegalArgumentException("Invalid model input");
        }
        long tasks = ((long) n + grain - 1) / grain;
        long waves = (tasks + workers - 1) / workers;
        return Math.addExact(
                Math.addExact(
                        Math.multiplyExact(
                                Math.multiplyExact(waves, grain),
                                computeNsPerItem),
                        Math.multiplyExact(tasks, taskSubmitNs)),
                Math.multiplyExact((long) barriers, barrierNs));
    }

    static long communicationNs(long messages, long bytes,
            long startupNsPerMessage, long nsPerByte) {
        if (messages < 0 || bytes < 0
                || startupNsPerMessage < 0 || nsPerByte < 0) {
            throw new IllegalArgumentException("Negative model input");
        }
        return Math.addExact(
                Math.multiplyExact(messages, startupNsPerMessage),
                Math.multiplyExact(bytes, nsPerByte));
    }

    // Sequential SIMULATION of a binary parallel reduction tree.
    static long treeReduce(long[] input) {
        if (input.length == 0
                || Integer.bitCount(input.length) != 1) {
            throw new IllegalArgumentException("Need positive power of two");
        }
        long[] work = input.clone();
        for (int stride = 1; stride < work.length; stride *= 2) {
            for (int i = 0; i < work.length; i += 2 * stride) {
                work[i] = Math.addExact(work[i], work[i + stride]);
            }
        }
        return work[0];
    }

    static void check(boolean b, String reason) {
        if (!b) throw new AssertionError(reason);
    }

    static void example() throws Exception {
        int[] data = new int[4096];
        for (int i = 0; i < data.length; i++) data[i] = i % 17 - 8;
        long oracle = sequentialSum(data);
        check(oracle == -8L, "Sequential oracle was unexpected");
        System.out.println("Reference sum: " + oracle
                + ", records=" + data.length + ", workers=4");

        for (int grain : new int[] {1, 64, 512, 4096}) {
            SumResult got = parallelChunkSum(data, 4, grain);
            check(got.sum() == oracle, "Parallel sum mismatch");
            long predicted = modelNanoseconds(
                    data.length, 4, grain, 10, 200, 2, 1000);
            System.out.println("grain=" + grain
                    + ": tasks=" + got.tasks()
                    + ", sum=" + got.sum()
                    + ", toyCostNs=" + predicted);
        }

        BarrierResult phases = parallelPhases(data, 4, 4);
        check(phases.sum() == oracle
                && phases.arrivals() == 16
                && phases.trips() == 4,
                "Barrier phases or result mismatch");
        System.out.println("Four barrier phases: sum="
                + phases.sum() + ", arrivals="
                + phases.arrivals() + ", completedBarriers="
                + phases.trips());

        long[] eight = {1, 2, 3, 4, 5, 6, 7, 8};
        check(treeReduce(eight) == 36, "Tree sum wrong");
        System.out.println("Tree reduction: workers=8, rounds=3, "
                + "combineMessages=7, sum=" + treeReduce(eight));

        long communication = communicationNs(6, 4096, 1500, 2);
        check(communication == 17192, "Communication model wrong");
        System.out.println("Communication toy model: messages=6, "
                + "bytes=4096, startupNs=9000, byteNs=8192, "
                + "totalNs=" + communication);
        System.out.printf(Locale.ROOT,
                "Amdahl: serialFraction=0.10, workers=4, "
                + "idealSpeedup=%.6f%n", 1.0 / (0.1 + 0.9 / 4));
    }

    static void randomOracleTests() throws Exception {
        SplittableRandom random = new SplittableRandom(5292026L);
        for (int trial = 0; trial < 180; trial++) {
            int n = random.nextInt(0, 301);
            int[] data = new int[n];
            for (int i = 0; i < n; i++) {
                data[i] = random.nextInt(-10_000, 10_001);
            }
            int grain = random.nextInt(1, 65);
            int workers = random.nextInt(1, 5);
            SumResult r = parallelChunkSum(data, workers, grain);
            check(r.sum() == sequentialSum(data),
                    "Random parallel sum wrong");
            check(r.tasks() == (n + grain - 1) / grain,
                    "Wrong task count");
        }
        for (int trial = 0; trial < 200; trial++) {
            int k = random.nextInt(1, 9);
            int len = 1 << k;
            long[] data = new long[len];
            long sum = 0;
            for (int i = 0; i < len; i++) {
                data[i] = random.nextInt(-1000, 1001);
                sum = Math.addExact(sum, data[i]);
            }
            check(treeReduce(data) == sum,
                    "Random reduction tree wrong");
        }
        System.out.println(
                "Random oracle QA: PASS (180 parallel arrays, "
                + "200 reduction trees)");
    }

    public static void main(String[] args) throws Exception {
        example();
        randomOracleTests();
    }
}
```

### 15.3. Biên dịch và chạy

Lưu toàn bộ mã thành `ParallelOverheadDemo.java`. Dùng JDK 17 hoặc mới hơn:

```bash
javac ParallelOverheadDemo.java
java ParallelOverheadDemo
```

**Stdout chính xác trong lần thử với seed đã định:**

```text
Reference sum: -8, records=4096, workers=4
grain=1: tasks=4096, sum=-8, toyCostNs=831440
grain=64: tasks=64, sum=-8, toyCostNs=25040
grain=512: tasks=8, sum=-8, toyCostNs=13840
grain=4096: tasks=1, sum=-8, toyCostNs=43160
Four barrier phases: sum=-8, arrivals=16, completedBarriers=4
Tree reduction: workers=8, rounds=3, combineMessages=7, sum=36
Communication toy model: messages=6, bytes=4096, startupNs=9000, byteNs=8192, totalNs=17192
Amdahl: serialFraction=0.10, workers=4, idealSpeedup=3.076923
Random oracle QA: PASS (180 parallel arrays, 200 reduction trees)
```

### 15.4. Cách hiểu kết quả

**Reference sum:** Dãy 4096 phần tử có tổng −8 xác định được bằng phép cộng tuần tự. Dùng cùng một input bất biến để đối chiếu các cách chia task.

**Grain lines:** Tất cả cách chia đều tạo cùng tổng −8. Số task tương ứng là 4096, 64, 8 và 1. `toyCostNs` là **giá trị từ công thức c=10, tau=200, hai barrier mỗi cái 1000**, không phải thời gian JIT/JVM thực. Đó là thí nghiệm **mô hình lý thuyết**, không phải phép đo tốc độ máy.

**Four barrier phases:** Đúng 4 worker x 4 pha, 16 lượt worker đến điểm đồng bộ. `completedBarriers=4` được tính bởi action của `CyclicBarrier` và kiểm tra. Tổng vẫn là −8.

**Tree reduction:** Hàm `treeReduce` **thực thi tuần tự một mô phỏng cây** với 8 số, kết quả 36. Dòng này ghi **cấu trúc logic** 3 round và 7 combine operations; không có 8 OS threads trong hàm ấy và không phát 7 network messages thật.

**Communication:** 17192 ns là **công thức toy** từ 6 startup giả định cùng 4096 bytes payload, không đo đường truyền vật lý. Giá trị 9000+8192 cho phép học cách phân biệt message startup với payload size.

**Amdahl:** Speedup lý tưởng 3.076923 với s=10% và 4 workers, chưa tính overhead thực. Không dùng nó để khẳng định chương trình Java đã chạy nhanh hơn 3.076923 lần.

**Random oracle QA:** 180 mảng random, độ dài 0..300, nhiều grain và số worker, mọi kết quả cộng song song đúng oracle tuần tự. Thêm 200 phép giảm cây với số phần tử là lũy thừa của hai, đều khớp phép cộng tuyến tính. Các kiểm thử này chứng minh cài đặt trong mẫu **đúng trên các trường hợp đã thử**, không chứng minh mọi lời gọi trên mọi hệ thống tự động nhanh hơn tuần tự.

## 16. Phân tích độ phức tạp của mã Java

Gọi N là số phần tử, g là grain, K=`ceil(N/g)`, P là số worker.

### 16.1. `parallelChunkSum`

Phần tính toán thực sự:

```text
O(N) tổng số phép đọc/cộng hữu ích.
```

Số task được tạo và số future:

```text
K = ceil(N/g).
```

Một mô hình bậc lớn cho overhead tạo task và thu kết quả:

```text
O(K) tác vụ và Future objects.
```

Bộ nhớ phụ bên ngoài mảng đầu vào:

```text
O(K + P) cho futures, task metadata và worker state,
```

bỏ qua chi phí stack/pool, runtime/GC thực. Vì tất cả partial được cộng vào một biến thread chính, không tạo một array kết quả kích thước N trừ khi K gần N. Với g=1, K=N nên memory task metadata có thể đáng kể.

**Thời gian lý tưởng** khi chia đều N phép cộng:

```text
O(N/P + K)
```

nếu coi tạo/thu K task là công việc tuần tự O(K) và đồng bộ bỏ qua các hằng số. Trong thực tế scheduler, memory bandwidth, contention và khác biệt task durations làm thời gian khác; **không tuyên bố Big-O này là thời gian wall-clock chính xác**. Mã tạo lại pool cho từng lần gọi (để dễ chạy độc lập), vì vậy thời gian thật còn có **pool startup/shutdown overhead**; hệ production thường tái sử dụng pool.

### 16.2. `parallelPhases`

Có `P` long-lived task, mỗi task thực hiện `phases` đoạn với tổng N record. Các worker ghi phần riêng. Số lượt barrier arrival:

```text
P * phases
```

và số barrier completion:

```text
phases.
```

Tổng công việc tính vẫn O(N); số pha tăng có thể tạo overhead đồng bộ `O(phases)` lần trên mỗi worker, nhưng nếu mỗi pha có rất ít work thì overhead sẽ trội hơn.

### 16.3. `treeReduce`

Với n là lũy thừa hai:

```text
work: n-1 phép cộng.
span của DAG: log2(n) rounds.
```

Cài đặt `treeReduce` trong Java là **sequential simulation** của cây:

```text
time executed by this method: O(n),
space: O(n) do clone array.
```

Không được lấy span `O(log n)` của DAG rồi báo rằng hàm Java này tự chạy trong `O(log n)` thời gian trên **một thread**.

### 16.4. `modelNanoseconds` và `communicationNs`

Hai hàm tính công thức số học, nên O(1) về số phép toán (trong mô hình số nguyên long 64-bit cố định). Chúng dùng `Math.multiplyExact` và `Math.addExact` để phát hiện overflow thay vì âm thầm trả chi phí âm. Đầu ra **số học của mô hình**, không đo hardware.

## 17. Chứng minh tính đúng của chia chunk và reduction

### 17.1. Phủ hết đúng một lần

Với `grain=g>0`, các chunk có dạng:

```text
[0,g), [g,2g), [2g,3g), ...
```

với biên cuối được giới hạn bởi N:

```text
[lo,min(lo+g,N)).
```

Các chunk **không chồng lấn**, và hợp tất cả chunk bằng `[0,N)`. Vì vậy mỗi phần tử được xử lý **đúng một lần** trong một task.

### 17.2. Tính đúng của tổng

Mỗi task tính tổng giá trị trong chunk của mình bằng `long`. Tổng các kết quả chunk bằng tổng toàn dãy do tính kết hợp của phép cộng số nguyên toán học, với điều kiện không xảy ra overflow. Mã dùng `Math.addExact` để **phát hiện và báo lỗi** nếu phạm vi long không chứa tổng trung gian. Trong dữ liệu test, các giá trị nhỏ nên không có overflow.

Các future được duyệt theo thứ tự gửi task để tạo output deterministic, nhưng các task **có thể hoàn thành khác thứ tự**. Tính đúng của kết quả không dựa vào thứ tự hoàn thành.

### 17.3. Đồng bộ visibility

Các task trong `parallelChunkSum` chỉ đọc `data` bất biến và tạo kết quả local, nên không tranh ghi vào cùng vị trí. Kết quả từ `Callable` được lấy qua `Future.get()` sau khi task hoàn tất; dữ liệu công bố theo hợp đồng Future có quan hệ visibility phù hợp. Trong `parallelPhases`, mỗi `partials[id]` chỉ được ghi bởi worker id tương ứng; thread chính đọc sau khi mọi future đã hoàn thành.

**Điều kiện ngoại lệ:** Nếu có thread bên ngoài sửa `data` đồng thời mà không đồng bộ, lập luận “input bất biến” không còn đúng. Cần snapshot hoặc cơ chế publication/lock phù hợp.

### 17.4. Tính đúng của cây reduction

Ở mức `stride=s`, mỗi vị trí đầu nhóm `i` giữ tổng của các phần tử trong đoạn độ dài s đã gộp từ các mức trước. Gộp `work[i]` với `work[i+s]` tạo tổng đoạn độ dài 2s. Quy nạp theo s=1,2,4,... tới n/2 chứng minh `work[0]` cuối là tổng n phần tử. Số phép gộp n−1 và số mức log2 n khi n là lũy thừa hai.

## 18. Thiết kế chiến lược giảm overhead

### 18.1. Giảm số task và tái sử dụng worker

Thay vì tạo một task cho mỗi record:

```text
task per chunk.
```

Chọn grain đủ lớn để task chạy nhiều phép hữu ích. Dùng thread pool/ForkJoinPool phù hợp, tránh tạo và hủy thread trên mỗi thao tác. Nếu cần chia load động, để K nhiều hơn P nhưng không khổng lồ so với work hữu ích.

### 18.2. Giảm chờ đồng bộ

Dùng local partial results, giảm critical sections, chỉ đặt barrier ở ranh giới dependency. Nếu phụ thuộc có thể biểu diễn bằng futures/dag task dependencies thì tránh global barrier buộc worker không liên quan cũng phải chờ.

### 18.3. Giảm data movement

Tính toán tại nơi dữ liệu đã có, dùng contiguous chunks, hạn chế copy, gom message nhỏ, local aggregation trước khi gửi. Nếu cần truyền nhiều dữ liệu, có thể gửi theo batch và xử lý pipeline để overlap nhưng phải kiểm soát backpressure.

### 18.4. Chống load imbalance

Dùng dynamic scheduling/work stealing khi duration của công việc khó dự đoán. Với lượng việc đều và dữ liệu liên tục, static partitions có thể đơn giản và hiệu quả hơn. Đừng chỉ xem số task đã hoàn thành; đo thời gian worker idle và phase max.

### 18.5. Tránh oversubscription

Nếu máy chỉ có 8 logical CPU cores mà tạo hàng trăm CPU-bound threads đồng thời, context switching và cache contention có thể làm chậm. Có thể nhiều thread vẫn phù hợp cho I/O-bound workloads, nhưng với CPU-bound hãy chọn P theo tài nguyên thực và workload, không dùng một hằng số áp dụng mọi hệ.

## 19. Các lỗi phổ biến

1. Cho rằng chia một vòng lặp thành P task thì thời gian chắc chắn giảm đúng P lần.
2. Nhầm số task với số OS thread.
3. Coi `pool.submit()` hoàn toàn miễn phí.
4. Tạo một task cho mỗi phép cộng đơn giản mà không tính scheduling overhead.
5. Tạo một task khổng lồ rồi mong nhiều worker cùng xử lý nó.
6. Quên số task K=`ceil(N/g)` và chunk cuối có thể ngắn hơn g.
7. Đếm dữ liệu trùng/thiếu ở ranh giới chunk.
8. Quên join hoặc lấy `Future.get()` trước khi đọc kết quả task.
9. Bỏ exception trong task rồi dùng tổng chưa hoàn chỉnh.
10. Dùng `globalCounter++` từ nhiều thread không đồng bộ.
11. Thay lock/atomic bằng biến thường mà không có quan hệ happens-before đúng.
12. Dùng lock cho từng record dù có thể local aggregate rồi reduce.
13. Cho rằng atomic contended sẽ scale tuyến tính.
14. Coi barrier là miễn phí khi P tăng.
15. Thêm barrier sau mọi thao tác nhỏ, làm thời gian đợi chiếm phần lớn.
16. Tính thời gian một pha bằng trung bình worker thay vì worker chậm nhất.
17. Tạo barrier đợi P parties nhưng pool không thể cho đủ P task chạy.
18. Submit task con vào fixed pool đang bị chiếm hết rồi block đợi task con.
19. Không có chính sách xử lý interruption/broken barrier.
20. Coi cache-coherence traffic bằng 0 vì các thread ở cùng máy.
21. Không phân biệt true sharing với false sharing.
22. Nói false sharing làm sai kết quả thay vì làm xấu performance.
23. Tuyên bố một array layout JVM chắc chắn cùng cache line mà không đo.
24. Bỏ giới hạn memory bandwidth khi tăng số worker.
25. Coi `alpha` và `beta` là hằng số chung cho mọi network/hardware.
26. Đánh đồng số thông điệp với tổng byte đã truyền.
27. Bỏ chi phí startup của hàng nghìn message nhỏ.
28. Gộp mọi message thành một batch cực lớn mà bỏ latency deadline.
29. Dùng công thức truyền thông nối tiếp khi network và compute thực sự overlap mà không điều chỉnh.
30. Coi shared-memory array access như một RPC trên mạng.
31. Coi all-reduce có chi phí y hệt reduce một chiều.
32. Quên output serialization và truyền dữ liệu result.
33. Nhầm P−1 tổng combine operations với log2 P vòng trên đường găng.
34. Gọi sequential tree simulation là chương trình dùng P threads thật.
35. Báo `T_P=W/P` như đẳng thức mà bỏ span.
36. Không phân biệt Amdahl fixed-size với Gustafson scaled-size.
37. Bỏ serial fraction khi dự đoán speedup với P rất lớn.
38. Coi work stealing luôn giải quyết mọi imbalance miễn phí.
39. Không xét locality khi task bị đưa tới worker/NUMA node khác.
40. Coi kết quả toy `modelNanoseconds` là số nanosecond JVM đã đo.
41. Đo microbenchmark một lần với input quá nhỏ rồi chốt grain tối ưu.
42. Không kiểm soát JIT warm-up, GC, CPU frequency và tải nền.
43. Dùng một bản tuần tự cố tình kém để báo speedup “ấn tượng”.
44. Bỏ qua pool creation/shutdown overhead khi so các hàm demo.
45. Coi speedup >P đo trên máy thật là chứng minh phá cận W/P trong cùng mô hình.
46. Không thử N=0, chunk cuối, số task ít hơn worker và nhiều worker/grain.
47. Dùng `int` cho tổng lớn và để overflow.
48. Không đối chiếu kết quả song song với oracle tuần tự độc lập.
49. Không kiểm tra exception/task cancellation khi có timeout.
50. Tuyên bố chương trình song song đúng chỉ vì một lần chạy cho kết quả kỳ vọng.

## 20. Bài tập tự luyện có đáp án

**Bài 1.** Work W là gì?

**Đáp án:** Tổng lượng công việc (tổng cost các nút DAG); thường đồng nhất với chi phí một lịch thực thi tuần tự tương đương.

**Bài 2.** Span S là gì?

**Đáp án:** Chi phí của đường phụ thuộc dài nhất trong DAG, còn gọi critical path.

**Bài 3.** Với W=120 đơn vị, P=4, cận dưới thời gian do work là bao nhiêu?

**Đáp án:** `W/P=30`.

**Bài 4.** Nếu W=120, S=50, P=4, cận dưới nào mạnh nhất?

**Đáp án:** `max(120/4,50)=50`.

**Bài 5.** Work/span parallelism khi W=1000, S=100?

**Đáp án:** `W/S=10`.

**Bài 6.** Nếu s=0.10 và P=4, speedup Amdahl lý tưởng?

**Đáp án:** `1/(0.1+0.9/4)≈3.076923`.

**Bài 7.** Với s=0.10, speedup Amdahl khi P vô hạn có cận bao nhiêu?

**Đáp án:** `1/s=10`.

**Bài 8.** Định luật Gustafson thường xét thay đổi gì so với Amdahl?

**Đáp án:** Bài toán có thể được scale lớn hơn khi tăng P, thay vì giữ workload cố định.

**Bài 9.** N=4096, grain=64, số task?

**Đáp án:** `ceil(4096/64)=64`.

**Bài 10.** N=4096, grain=1, số task?

**Đáp án:** 4096.

**Bài 11.** N=4096, grain=4096, có thể chia task cho 4 worker chạy cùng lúc không?

**Đáp án:** Chỉ có một task, nên trong mô hình task không bị chia nhỏ chỉ một worker có hữu ích; ba worker còn lại không xử lý cùng task ấy.

**Bài 12.** Tại sao grain quá nhỏ có thể làm chậm?

**Đáp án:** Có nhiều task, queue/future/scheduling overhead có thể lớn hơn tính toán hữu ích.

**Bài 13.** Grain quá lớn gây nguy cơ nào?

**Đáp án:** Ít task, load imbalance và giảm khả năng dùng nhiều worker.

**Bài 14.** `Executors.newFixedThreadPool(4)` và `submit()` 1000 lần tạo 1000 thread không?

**Đáp án:** Không; gửi 1000 task vào pool tối đa bốn worker threads.

**Bài 15.** Nếu lock được lấy cho từng phần tử trong một vòng 1 triệu record, có thể tối ưu thế nào?

**Đáp án:** Cộng local theo worker rồi hợp nhất partial sums, giảm số lần tranh lock.

**Bài 16.** `counter++` trên biến thường shared giữa các workers có an toàn không?

**Đáp án:** Không, vì read-modify-write không atomic và có data race/visibility issues.

**Bài 17.** Atomic contended có luôn scale tuyến tính?

**Đáp án:** Không; nhiều workers cập nhật cùng một cache line có thể tranh chấp và serialize.

**Bài 18.** Nếu một pha có worker times [3,5,12,4], chưa tính barrier, duration tối thiểu?

**Đáp án:** 12 đơn vị vì tất cả phải đợi worker chậm nhất.

**Bài 19.** Bốn workers qua bốn phases, tổng barrier arrivals?

**Đáp án:** 16 arrivals, và 4 barrier completions nếu mọi phase thành công.

**Bài 20.** `CountDownLatch` khác `CyclicBarrier` thế nào?

**Đáp án:** Latch là cổng đếm xuống một lần; barrier là điểm hẹn cho số parties cố định, có thể tái sử dụng theo nhiều pha.

**Bài 21.** Hai task ghi hai biến khác nhau cùng cache line gây hiện tượng gì?

**Đáp án:** Có thể gây false sharing (chi phí coherence), không nhất thiết gây data race logic.

**Bài 22.** Một thông điệp 1000 byte có chi phí theo alpha–beta?

**Đáp án:** `alpha + 1000*beta`.

**Bài 23.** q thông điệp tổng D byte không overlap có tổng communication toy time?

**Đáp án:** `q*alpha + D*beta`.

**Bài 24.** q=6, D=4096, alpha=1500ns, beta=2ns/byte, tính kết quả?

**Đáp án:** `9000+8192=17192 ns` theo mô hình đã đặt.

**Bài 25.** Vì sao gửi 1000 message 8 byte có thể đắt hơn 10 message 800 byte?

**Đáp án:** Tổng payload bằng nhau nhưng số startup alpha lớn hơn rất nhiều ở phương án 1000 message.

**Bài 26.** Gộp message có thể gây mặt trái gì?

**Đáp án:** Tăng độ trễ chờ đủ batch, memory buffering và giảm tính phản hồi.

**Bài 27.** Shared-memory threads có nhất thiết truyền message RPC khi đọc cùng một mảng không?

**Đáp án:** Không; chúng cùng address space, nhưng vẫn chịu cache/coherence/memory bandwidth costs.

**Bài 28.** Cây reduction tám phần tử có bao nhiêu phép combine?

**Đáp án:** 7.

**Bài 29.** Span logic của cây reduction tám phần tử cân bằng?

**Đáp án:** `log2(8)=3` vòng cộng.

**Bài 30.** Cây reduction trên P tiến trình có P−1 message tổng nhưng path log P. Có mâu thuẫn không?

**Đáp án:** Không; tổng công việc/messages khác critical-path rounds.

**Bài 31.** Mỗi worker gửi một `long` thay vì toàn bộ dữ liệu có lợi gì?

**Đáp án:** Có thể giảm payload từ cỡ O(N) record xuống O(P) partial values khi phép tổng hợp phù hợp.

**Bài 32.** Speedup và efficiency được định nghĩa thế nào?

**Đáp án:** `speedup=T1/TP`, `efficiency=speedup/P` cùng workload.

**Bài 33.** T1=100ms, T4=40ms thì speedup/efficiency?

**Đáp án:** 2.5 và 62.5%.

**Bài 34.** Toy grain=1 cho 831440ns, grain=512 cho 13840ns có chứng minh wall-clock Java nhanh đúng tỷ lệ này không?

**Đáp án:** Không; đó là kết quả mô hình với các hằng số giả định, không phải benchmark.

**Bài 35.** Tại sao `Future.get()` quan trọng trong bài cộng song song?

**Đáp án:** Đợi task hoàn thành, lấy giá trị/exceptions và cung cấp quan hệ visibility/happens-before phù hợp.

**Bài 36.** Nếu input có độ dài 0, `parallelChunkSum` trả tổng gì?

**Đáp án:** Tổng rỗng bằng 0, số task 0 (pool được tạo nhưng không có task).

**Bài 37.** Nếu N=10, g=4, các chunk giới hạn nào?

**Đáp án:** `[0,4)`, `[4,8)`, `[8,10)`.

**Bài 38.** Tại sao một `CyclicBarrier(4)` trong pool 2 threads có thể nguy hiểm khi cả bốn task cần chờ barrier?

**Đáp án:** Hai task đang chạy chờ hai task chưa được scheduled vì pool không có thêm threads, gây starvation deadlock.

**Bài 39.** Work stealing có thể làm giảm chi phí gì và thêm chi phí gì?

**Đáp án:** Giảm load imbalance/idle time, nhưng thêm overhead lấy task, contention và có thể giảm locality.

**Bài 40.** Nêu ba điều kiện để khẳng định một cấu hình song song hữu ích trong production.

**Đáp án:** Kết quả đúng so oracle, speedup đo công bằng trên workload đại diện, và overhead (queue/barrier/communication/bandwidth) được theo dõi để biết nguyên nhân.

## 21. Checklist trước khi tối ưu thuật toán song song

- [ ] Có DAG phụ thuộc đúng và phân biệt work W, span S?
- [ ] Có cận `T_P>=max(W/P,S)` và xác định serial fraction?
- [ ] Tính đúng N, P, grain g và số task `ceil(N/g)`?
- [ ] Task có đủ lượng tính toán hữu ích để amortize scheduling?
- [ ] Có đủ task để cân bằng tải nhưng không tạo hàng triệu task cực nhỏ?
- [ ] Thread pool được tái sử dụng phù hợp; không nhầm task với thread?
- [ ] Input được chia không chồng lấn và không bỏ rơi chunk cuối?
- [ ] Shared writable state có lock/atomic hoặc worker-local reduction đúng?
- [ ] Barriers chỉ đặt tại dependency boundaries cần thiết?
- [ ] Số barrier parties khớp số worker task có thể chạy, tránh starvation?
- [ ] Có xử lý exception, cancellation và interruption khi cần?
- [ ] Có tính load imbalance theo worker chậm nhất tại mỗi pha?
- [ ] Có đo queue wait, worker idle, lock contention khi chậm?
- [ ] Có phân biệt shared-memory với message passing?
- [ ] Mô hình alpha–beta có tách số message và tổng bytes?
- [ ] Có xem xét batch size, data locality và overlap?
- [ ] Có giảm dữ liệu trước khi truyền bằng local aggregation nếu phù hợp?
- [ ] Có xét cache line sharing, NUMA và memory bandwidth saturation?
- [ ] Có phân biệt tree work (P−1) với span (log P)?
- [ ] Có đối chiếu kết quả song song với tuần tự trên cả input cạnh biên?
- [ ] Các mô hình toy có nhãn **giả định**, không trình bày thành benchmark?
- [ ] Benchmark thật có kiểm soát JIT, GC, cache, input size và tải nền?
- [ ] Mọi thay đổi grain/scheduler vẫn bảo toàn tính đúng?

## Kết luận

Hiệu quả của một thuật toán song song phụ thuộc không chỉ vào `P`, mà còn vào **đường găng S**, **số task K**, **độ hạt g**, **số điểm đồng bộ**, **số thông điệp** và **lượng dữ liệu truyền**.

Những công thức cần nhớ:

```text
Work–span lower bound:
    T_P >= max(W/P, S).

Chunk count:
    K = ceil(N/g).

Amdahl ideal speedup:
    1 / (s + (1-s)/P).

Simple communication model:
    T_comm ≈ q*alpha + D*beta.

Simple balanced reduction tree:
    work = P-1 combines;
    span = ceil(log2 P) levels.
```

Khi **g quá nhỏ**, phí tạo/gửi/thu task có thể áp đảo tính toán. Khi **g quá lớn**, số task không đủ dùng hết worker. Barrier buộc các worker chờ người chậm nhất; locks và atomics hot có thể làm đoạn cập nhật bị tuần tự hóa; message quá nhỏ làm tăng startup, còn copy/NUMA/cache-coherence có thể khiến memory-bound tasks không scale.

Kỹ thuật thực hành quan trọng nhất là **đo và tối ưu đúng nguồn overhead**, với chương trình vẫn đúng: dùng local partials và reduction, tăng locality, chia chunk có chủ đích, giảm barriers không cần thiết, gộp messages khi hợp lý, và kiểm thử bằng oracle. Chương trình Java minh họa tất cả số đếm chính xác và cho thấy một **mô hình chi phí** có thể giải thích trade-off; muốn lựa chọn cấu hình chạy thật cần đo trên dữ liệu và hardware mục tiêu.
