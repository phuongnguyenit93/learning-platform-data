# Lựa chọn giải pháp khi dữ liệu không vừa bộ nhớ

Khi dữ liệu lớn hơn RAM có thể dành cho một tiến trình, câu hỏi quan trọng không chỉ là thuật toán nào có độ phức tạp CPU tốt nhất, mà là cách tổ chức truy cập dữ liệu để không phải giữ toàn bộ dữ liệu cùng lúc trong bộ nhớ. Một phép sắp xếp O(N log N) có thể chậm nếu liên tục truy cập đĩa ngẫu nhiên; một phép hash join rất nhanh nếu bảng build vừa RAM nhưng có thể thất bại khi bảng hash vượt giới hạn; một lượt quét tuần tự đôi khi tốt hơn việc xây index nếu chỉ chạy truy vấn một lần.

Bài thuộc chủ đề **Thực hành tổng hợp**, tập trung vào cách chọn giải pháp theo kích thước dữ liệu, mẫu truy cập, tính chính xác, số lần truy vấn, RAM khả dụng, dung lượng đĩa, I/O, độ lệch phân phối và độ trễ. Các lựa chọn chính gồm streaming, external merge sort, external hash partitioning, sort-merge join, chỉ mục/database, thuật toán xấp xỉ và xử lý phân tán.

Bài có chương trình **Java 17+ external merge sort thực sự đọc/ghi file**, tạo các run đã sắp xếp trong RAM giới hạn, rồi gộp nhiều lượt với fan-in giới hạn. Chương trình kiểm tra kết quả với oracle độc lập trên 10.003 số nguyên, có số âm, trùng lặp, file rỗng và file sai kích thước. Đây là ví dụ file-backed cho bản ghi số nguyên 32-bit cố định; nó giúp học thiết kế và giới hạn bộ nhớ, không phải một engine sản xuất cho mọi định dạng dữ liệu.

## 1. Trước hết, xác định “không vừa bộ nhớ” nghĩa là gì

Có nhiều tình huống khác nhau thường bị gom chung:

- Toàn bộ input không vừa RAM, nhưng có thể đọc tuần tự từng phần.
- Input vừa RAM, nhưng cấu trúc phụ trợ như HashMap, sort buffer hoặc index không vừa.
- Dữ liệu vừa heap Java nhưng không vừa ngân sách bộ nhớ thực tế sau khi tính các tiến trình khác, page cache và native memory.
- Dữ liệu không vừa RAM của một máy nhưng không vừa giới hạn heap/container được cấp cho ứng dụng.
- Dữ liệu không vừa RAM nhưng vừa đĩa cục bộ; hoặc cả đĩa cục bộ cũng không đủ.
- Dữ liệu không quá lớn nhưng truy vấn yêu cầu truy cập ngẫu nhiên dày đặc khiến paging/thrashing.
- Dữ liệu hiện tại vừa RAM, nhưng số lần truy vấn, cập nhật và yêu cầu đồng thời khiến một chỉ mục hay database phù hợp hơn.

**Không dùng tổng RAM vật lý làm ngân sách thuật toán.** Cần ước lượng bộ nhớ mà tiến trình thực sự được phép dùng và để lại khoảng an toàn cho JVM, OS, cache, thread stacks, buffer, object headers, GC và các tiến trình khác.

### 1.1. Các đại lượng nên đo

| Ký hiệu | Ý nghĩa | Đơn vị ví dụ |
| --- | --- | --- |
| N | Tổng số bản ghi hoặc tổng kích thước dữ liệu | records, bytes |
| s | Kích thước trung bình một bản ghi sau khi decode | bytes/record |
| M | Số bản ghi hoặc số byte thực sự có thể giữ cho thuật toán | records hoặc bytes |
| B | Số bản ghi hoặc số byte đọc/ghi trong một block | records/block hoặc bytes/block |
| C | Số bản ghi tối đa xử lý trong một chunk/run | records |
| R | Số run ban đầu, xấp xỉ ceil(N/C) | runs |
| F | Fan-in: số run được gộp đồng thời | runs |
| P | Số lượt merge cần thiết | passes |
| Z | Kích thước output, có thể lớn hơn input | bytes |
| H | Số khóa phân biệt hoặc kích thước hash state | keys/bytes |

Nếu N=100 triệu nhưng mỗi bản ghi khi giải mã chiếm 200 byte, dữ liệu trong RAM có thể cần khoảng 20 GB trước khi tính overhead của đối tượng và cấu trúc. File nén 3 GB **không có nghĩa** dữ liệu sau decode chỉ cần 3 GB.

### 1.2. Đừng nhầm file size với heap footprint

Một dòng CSV dài 80 byte khi parse thành Java String, object record, map entry và references có thể chiếm nhiều lần dung lượng file. HashMap có bucket array, node object và slack do load factor; mỗi String/object còn có header và alignment tùy JVM. Cần đo footprint trên workload đại diện hoặc dùng primitive/columnar representation khi phù hợp.

Ví dụ:

```text
File input: 4 GB.
Decoded objects: có thể lớn hơn đáng kể 4 GB.
Temporary sort buffers: cần thêm RAM.
Output/index/merge buffers: cần thêm RAM hoặc đĩa.
```

**Tính toàn bộ peak memory**, không chỉ mảng input.

## 2. Chọn theo công việc cần làm

Trước khi chọn thuật toán, trả lời các câu hỏi sau:

1. Chỉ cần một lượt quét hay phải truy vấn lặp lại?
2. Có cần output được sắp xếp chính xác không?
3. Có cần kết quả chính xác tuyệt đối hay có thể chấp nhận sai số?
4. Có thể gom nhóm theo key bằng phép tổng hợp kết hợp được không?
5. Có cần join hai tập lớn? Bảng nhỏ hơn có vừa RAM không?
6. Có cần truy vấn point/range ngẫu nhiên nhiều lần?
7. Khóa có phân phối lệch, có hot keys hay dữ liệu trùng lặp lớn không?
8. Dữ liệu có thể chia partition theo key/range không?
9. Dung lượng đĩa tạm và số file descriptor có đủ không?
10. Một máy còn đủ I/O/CPU hay cần phân tán?

### 2.1. Bảng quyết định nhanh

| Nhu cầu | Giải pháp thường phù hợp | Điều kiện/điểm cần kiểm tra |
| --- | --- | --- |
| Một lượt đọc, tính sum/count/min/max | Streaming | State tổng hợp nhỏ; số học không overflow |
| Lọc/chuyển đổi tuần tự | Streaming pipeline | Backpressure, kích thước record, output |
| Cần sắp xếp toàn bộ chính xác | External merge sort | Có đĩa tạm, block I/O, fan-in và RAM chunk |
| Group by chính xác, key partitions vừa RAM | External hash partition + aggregate | Hash distribution và skew |
| Group by, dữ liệu đã sorted hoặc cần thứ tự | Sort + streaming aggregation | Chi phí sort có đáng cho query không |
| Join, một bên vừa RAM | Hash join | Ước lượng bộ nhớ sau khi build hash table |
| Join hai bên đều lớn | Grace hash join hoặc sort-merge join | Partition fit, skew, thứ tự dữ liệu |
| Nhiều truy vấn point/range lặp lại | Database/index | Chi phí build/update index, selectivity |
| Quét phân tích nhiều cột | Columnar storage, predicate pushdown | Đọc đúng cột/partition cần thiết |
| Ước lượng cardinality/tần suất | HyperLogLog, Count-Min Sketch | Sai số chấp nhận được, không dùng thay exact answer |
| Chọn mẫu đại diện | Reservoir sampling | Mục tiêu thống kê và phân phối dữ liệu |
| Một máy thiếu CPU/I/O/dung lượng | Distributed processing | Network shuffle, skew, coordination |

Đây là điểm xuất phát, không phải luật tuyệt đối. Nếu dữ liệu đã có thứ tự và chỉ cần aggregate, sort lại toàn bộ là lãng phí. Nếu bảng build vừa RAM, hash join thường đơn giản hơn external join. Nếu truy vấn chỉ chạy một lần, scan tuần tự có thể rẻ hơn tạo index.

## 3. Streaming: giải pháp đầu tiên nên xét

Streaming xử lý từng bản ghi hoặc từng batch nhỏ, giữ trạng thái cần thiết trong RAM:

```text
read batch
    -> validate/filter
    -> transform
    -> update bounded state
    -> emit result
    -> discard batch
```

### 3.1. Khi streaming phù hợp

- Tổng hợp sum/count/min/max.
- Lọc bản ghi theo điều kiện.
- Chuyển định dạng, chuẩn hóa hoặc mã hóa.
- Tính checksum/hash của stream.
- Tính thống kê có state nhỏ.
- Pipeline xử lý record độc lập.
- Đọc tuần tự từ file, object storage hoặc message stream.

Ví dụ tổng hợp:

```java
long count = 0;
long sum = 0;
while (hasNextRecord()) {
    int value = readNextValue();
    count = Math.addExact(count, 1);
    sum = Math.addExact(sum, value);
}
```

Đoạn này giữ O(1) state theo số bản ghi, nhưng vẫn có giới hạn số học long. Nếu tổng có thể vượt long, cần BigInteger hoặc một hợp đồng giới hạn khác.

### 3.2. Streaming không giải quyết mọi bài toán chính xác

Một số công việc cần giữ nhiều thông tin:

- **Sort toàn cục chính xác:** cần sắp thứ tự các bản ghi; streaming một chiều với bộ nhớ cố định không thể tùy ý phát bản ghi tiếp theo mà vẫn bảo đảm thứ tự cho mọi input.
- **Exact distinct count:** số khóa phân biệt có thể tăng tới O(N); HashSet không còn bounded khi key cardinality rất lớn.
- **Exact median/quantile:** muốn biết phần tử ở vị trí giữa chính xác thường phải lưu/partition/sort dữ liệu hoặc dùng external selection.
- **Join tổng quát:** cần tìm các bản ghi khớp giữa hai stream; có thể phải lưu một bên, spill hoặc dùng thứ tự/index.
- **Group by với mọi khóa tùy ý:** state có thể tỷ lệ với số khóa.
- **Random access:** stream đã đi qua không tự cung cấp khả năng truy vấn lại.

Nếu thuật toán dùng một HashMap có kích thước tăng theo số khóa, việc đọc input theo stream **không tự động làm thuật toán bounded-memory**.

### 3.3. Backpressure và batch size

Trong pipeline nhiều stage, stage đọc nhanh có thể tạo hàng đợi vô hạn nếu stage ghi/chuyển đổi chậm. Cần bounded queue hoặc backpressure để giới hạn số batch đang chờ.

Batch quá nhỏ tăng số lần gọi I/O, allocation và scheduling. Batch quá lớn tăng peak memory và độ trễ. Hãy chọn theo throughput, latency và memory budget.

## 4. External memory model: tối ưu block I/O

Khi dữ liệu lớn hơn RAM, chi phí di chuyển block giữa storage và RAM thường quan trọng hơn số phép so sánh CPU. Một mô hình đơn giản:

- N: số bản ghi.
- M: số bản ghi có thể giữ trong RAM.
- B: số bản ghi trong một block.
- Giả định M lớn hơn B và thao tác I/O đọc/ghi block là đơn vị chi phí.

Một lượt quét tuần tự cần xấp xỉ:

```text
scan I/O = ceil(N/B) block reads.
```

Một thuật toán có hàng triệu lần đọc ngẫu nhiên một record có thể rất chậm dù chỉ đọc tổng cộng N record, vì mỗi lần có latency và có thể gây seek/cache miss. Đọc theo block lớn, tuần tự và tận dụng locality thường hiệu quả hơn.

### 4.1. RAM phải chứa dữ liệu làm việc, không chỉ input

Một thuật toán external sort còn cần chunk sort buffer, merge input buffers, output buffer và priority queue. Hash partition cần hash table và metadata. Join cần cả partition của hai phía hoặc block buffer. Cần chừa ngân sách cho những thành phần này.

### 4.2. Sequential I/O và random I/O

**Sequential I/O:** đọc/ghi các vùng liên tiếp. External merge sort tận dụng kiểu truy cập này.

**Random I/O:** nhảy giữa các vị trí. B-tree index, lookup và nested-loop join có thể tạo nhiều random reads; cần xem số lookup, cache hit và thiết bị lưu trữ.

SSD giảm một số chi phí seek so với HDD, nhưng không biến hàng triệu random reads thành miễn phí. Page cache có thể giúp workload lặp lại, song không nên giả định toàn bộ dataset luôn được cache.

## 5. External merge sort: lựa chọn khi cần thứ tự toàn cục chính xác

Nếu N bản ghi không vừa RAM, chia thành các **run** đủ nhỏ để sort trong RAM, ghi từng run đã sắp xếp xuống đĩa, rồi merge các run.

### 5.1. Hai pha chính

**Pha 1 — Run generation:**

```text
while input remains:
    read at most C records
    sort chunk in memory
    write one sorted run to disk
```

Số run ban đầu:

```text
R = ceil(N/C).
```

Mỗi chunk chứa tối đa C record. Các chunk cuối có thể ngắn hơn.

**Pha 2 — Multi-way merge:**

Đọc một buffer/head từ mỗi run trong nhóm tối đa F run. Dùng min-heap giữ bản ghi nhỏ nhất hiện tại. Mỗi lần:

1. Lấy record nhỏ nhất trong heap.
2. Ghi record vào output.
3. Đọc record tiếp theo từ đúng run vừa lấy.
4. Đưa record mới vào heap nếu run còn dữ liệu.
5. Tiếp tục tới khi mọi run trong nhóm cạn.

Nếu R lớn hơn F, ghi run kết quả của lượt này xuống đĩa và tiếp tục merge theo nhiều lượt.

### 5.2. Vì sao fan-in phải bị giới hạn?

Merge F run cùng lúc cần ít nhất F input streams/buffers và một output buffer. Mỗi file mở còn tiêu thụ file descriptor và metadata. Nếu mở hàng chục nghìn run cùng lúc, có thể hết file descriptors hoặc vượt RAM vì buffer.

Do đó F cần thỏa cả:

```text
F * inputBufferBytes
    + outputBufferBytes
    + heap/metadata
    <= mergeMemoryBudget

F + otherOpenFiles <= fileDescriptorBudget.
```

Trong mô hình external-memory cổ điển, F thường có cỡ M/B; thực tế phải tính buffer size, JVM, OS và giới hạn file descriptors.

### 5.3. Số lượt merge

Với R run ban đầu và fan-in F≥2:

```text
P = ceil(log_F(R))       nếu R>1
P = 0                    nếu R<=1.
```

Mỗi lượt làm số run giảm xấp xỉ một hệ số F:

```text
R_next = ceil(R/F).
```

Ví dụ R=79, F=3:

```text
79 -> 27 -> 9 -> 3 -> 1
```

Cần 4 lượt merge.

### 5.4. Chi phí I/O

Mỗi lần run generation đọc input N record và ghi N record ra runs. Mỗi lượt merge thường đọc và ghi toàn bộ N record thêm một lần. Với B record/block:

```text
Run generation: 2 * ceil(N/B) block transfers.
Each merge pass: about 2 * ceil(N/B) transfers.
```

**Implementation Java ở cuối bài** lưu run cuối xuống scratch rồi copy sang output đích, vì thế có thêm một lần đọc/ghi toàn bộ run cuối:

```text
I/O upper estimate for this demo:
    2 * (N/B) * (P + 2) block transfers.
```

Bỏ qua block cuối không đầy, metadata và singleton run được move không cần đọc/ghi. Một engine tối ưu có thể stream lượt merge cuối trực tiếp vào output để tiết kiệm một cặp read/write:

```text
Typical direct-final-merge estimate:
    2 * (N/B) * (P + 1).
```

Đừng dùng công thức của engine direct-final-merge để mô tả chính xác số lượt của code demo này.

### 5.5. Ví dụ ước lượng

Giả sử:

```text
N = 1,000,000,000 records
C = 10,000,000 records
R = ceil(N/C) = 100 runs
F = 64
P = ceil(log_64(100)) = 2 passes
B = 65,536 records per block
```

Input có một tỷ record; nếu mỗi record là int 4 byte thì file khoảng 4 GB. Code demo với final copy cần xấp xỉ:

```text
2 * (N/B) * (P+2)
= 8 * N/B
≈ 122,100 block transfers.
```

Đây là ước lượng theo block, không phải giây. Thời gian thực còn phụ thuộc tốc độ storage, queue depth, cache, filesystem, block size, buffer, CPU sort/merge và workload khác.

### 5.6. CPU và RAM

Run generation sort từng chunk:

```text
CPU ≈ O(N log C) comparisons.
```

Mỗi merge pass dùng heap tối đa F phần tử, chi phí merge xấp xỉ O(N log F) comparisons. Qua P lượt:

```text
CPU merge ≈ O(P * N log F).
```

Bộ nhớ làm việc chính của demo:

```text
Run generation:
    4*C bytes for int[] chunk
    + input/output buffers.

Merge:
    F input buffers
    + 1 output buffer
    + O(F) heap heads and stream metadata.
```

Đây là mô hình thành phần, chưa tính object headers, JVM, filesystem cache và native allocations. Chương trình không giữ một danh sách tất cả đường dẫn run trong RAM; tên run được sinh từ chỉ số, để metadata path không tăng O(R) trong heap.

### 5.7. Ổ đĩa tạm

Run generation tạo một bản sorted runs có kích thước xấp xỉ input. Khi merge, thế hệ run cũ và thế hệ mới có thể cùng tồn tại; scratch có thể cần gần **2 lần kích thước dữ liệu**. Sau đó còn output cuối. Hãy tính riêng:

- Input gốc.
- Scratch runs cũ và mới.
- Output đích.
- Khoảng trống cho filesystem, metadata và tiến trình khác.

Nếu input, scratch và output cùng volume, một ngân sách bảo thủ cho ví dụ là khoảng **3 lần kích thước file input**, cộng margin. Con số thực phụ thuộc pass, move/copy, vị trí input/output và filesystem.

## 6. External hash partitioning: khi cần GROUP BY hoặc hash join

Nếu bài toán tổng hợp theo key hoặc join có thể chia theo hash, ta có thể partition trước, rồi xử lý từng partition trong RAM.

### 6.1. Hash aggregation

Giả sử cần GROUP BY key và SUM value. Không thể giữ HashMap toàn cục nếu số key quá lớn. Chia dữ liệu:

```text
partition = hash(key) mod P
append record to partition file
```

Mọi record có cùng key được đưa vào cùng partition. Sau khi partition xong, lần lượt đọc một partition, build HashMap và aggregate; nếu partition đủ nhỏ thì map vừa RAM.

```text
Input scan:
    read records
    route each record to hash partition

Partition processing:
    read one partition
    aggregate by key
    emit grouped result
```

### 6.2. Điều kiện đúng

Hàm partition phải nhất quán: cùng key luôn có cùng partition. Nếu dùng hash seed, seed phải giống nhau giữa các record và mọi phía join của cùng một partitioning stage. Nếu normalize key khác nhau ở hai nơi, các bản ghi logic cùng key có thể bị tách.

Đầu ra phải giữ đúng semantics của GROUP BY: key equality, null handling, case sensitivity, Unicode normalization và kiểu số học của aggregate cần được định nghĩa. Ví dụ SUM(long) có thể overflow dù HashMap không overflow.

### 6.3. Skew và heavy hitters

Hash partition không đảm bảo kích thước các partition bằng nhau. Nếu một key chiếm 40% input, mọi record của key ấy đi vào một partition. Partition đó có thể không vừa RAM dù các partition khác rất nhỏ.

Cách xử lý:

- Ước lượng phân phối key trước bằng sampling hoặc statistics.
- Dành partition riêng cho heavy hitters nếu phép tổng hợp cho phép.
- Dùng recursive repartition với hash seed khác cho partition quá lớn.
- Chuyển partition skew sang external sort + streaming aggregate.
- Đặt giới hạn bộ nhớ và spill thay vì để tiến trình OOM.

**Đổi hash seed không chia được cùng một key thành nhiều partition độc lập** nếu mục tiêu là GROUP BY chính xác; các record cùng key vẫn phải được hợp nhất cuối cùng. Có thể partial aggregate theo subpartition rồi reduce kết quả của key sau đó, nếu phép gộp associative/commutative và không làm mất semantics.

## 7. Chọn thuật toán join cho dữ liệu lớn

### 7.1. Hash join khi một phía vừa RAM

Nếu bảng nhỏ hơn sau khi giải mã và xây hash table vẫn vừa bộ nhớ, build hash table từ phía nhỏ, rồi scan phía lớn và probe:

```text
build hash table from smaller side
for each row in larger side:
    probe matching key
    emit join result
```

Không lấy file size nén làm tiêu chí duy nhất. Hash table thường tốn nhiều RAM hơn raw records. Cần tính key, value, bucket/node, duplicates và load factor.

### 7.2. Grace hash join khi cả hai phía lớn

Chia cả R và S theo cùng hash function:

```text
partition R by hash(key)
partition S by hash(key)

for each partition i:
    load smaller R_i or S_i into memory
    hash join against the other partition
    emit matches
```

Cặp record khớp phải có cùng partition vì cùng key được hash giống nhau. Nếu một cặp partition không vừa RAM, cần recursive partition hoặc fallback.

Một mô hình I/O một lượt Grace hash join thường khoảng:

```text
partition phase:
    read R and S, write partitions R and S

join phase:
    read partitions R and S

I/O ≈ 3*(|R|+|S|)/B block transfers,
excluding output, assuming one partitioning level.
```

Skew, recursive repartition, spill, output lớn hoặc nhiều lượt làm chi phí tăng.

### 7.3. Sort-merge join

Nếu hai input được sort theo key (hoặc external sort có thể thực hiện), dùng hai con trỏ/stream để merge:

```text
read next key from R and S
advance the side with smaller key
when keys match:
    emit all matching combinations for that key
```

Ưu điểm: đọc tuần tự, bounded memory cho các nhóm nhỏ; phù hợp khi input đã sorted hoặc cần thứ tự kết quả. Nhược điểm: phải sort cả hai bên nếu chưa có thứ tự, và nhóm duplicate rất lớn có thể tạo output Cartesian product lớn.

### 7.4. Nested-loop join

Block nested-loop join có thể hợp lý khi một phía rất nhỏ hoặc không có hash/order phù hợp. Đọc một block của phía ngoài vào RAM, quét phía trong và so khớp; lặp lại cho block tiếp theo.

Nếu phía trong phải quét lại nhiều lần, I/O có thể lớn. Không dùng nested loop cho hai bảng lớn mà không tính số lượt scan.

### 7.5. Output có thể lớn hơn input

Nếu một key xuất hiện r lần ở R và s lần ở S, equijoin có thể tạo r*s cặp. Dù input vừa chiến lược partition, output có thể cực lớn. Cần tính Z, ghi streaming, kiểm soát backpressure và kiểm tra có thực sự cần materialize toàn bộ join result không.

## 8. Database và chỉ mục: khi truy vấn lặp lại

Nếu cần nhiều lần point lookup hoặc range query trên cùng dữ liệu, một database/index thường tốt hơn việc tự quét toàn bộ file mỗi lần.

### 8.1. B-tree

B-tree giữ key theo thứ tự và các trang có thể được đọc theo từng block. Phù hợp với equality lookup, range scan và dữ liệu cần sắp thứ tự. Index có chi phí build, storage, update và cache; mỗi index bổ sung làm write path tốn thêm.

### 8.2. LSM-tree

Log-Structured Merge tree thường phù hợp workload write-heavy: ghi tuần tự vào memtable/log, sau đó flush/compact thành các file sorted runs. Nó đổi random writes thành sequential writes nhưng có write amplification và compaction I/O. Khi đọc, có thể phải kiểm tra nhiều thành phần/level; Bloom filters và index giúp giảm đọc không cần thiết.

### 8.3. Columnar storage và predicate pushdown

Nếu truy vấn phân tích chỉ cần 3 cột trong bảng 100 cột, columnar storage có thể đọc ít dữ liệu hơn row-oriented scan. Partition pruning, column projection và predicate pushdown giảm I/O. Định dạng như Parquet có metadata/statistics theo row group, giúp bỏ qua vùng không thỏa điều kiện.

### 8.4. Dùng database engine trước khi tự xây spill

Nếu dữ liệu nằm trong PostgreSQL, DuckDB, Spark SQL hoặc hệ thống tương tự, query planner có thể chọn sort/hash/merge, dùng temporary files và quản lý memory/spill. Hãy xem execution plan và memory setting trước khi viết một engine mới.

Cần kiểm tra engine có thật sự spill cho operation đó, giới hạn memory theo query/session ra sao, temporary storage ở đâu, và liệu một operator có thể giữ state lớn ngoài dự kiến không. “Dùng SQL” không tự loại bỏ giới hạn RAM; execution engine vẫn cần cấu hình và theo dõi.

## 9. Approximate algorithms khi bài toán cho phép sai số

Nếu yêu cầu là ước lượng, không nhất thiết phải lưu mọi key/record:

| Công cụ | Mục tiêu | Giới hạn cần ghi |
| --- | --- | --- |
| HyperLogLog | Ước lượng số phần tử phân biệt | Có sai số thống kê; không trả exact count |
| Bloom filter | Kiểm tra khả năng một phần tử đã được thêm | Có false positive; chuẩn không có false negative nếu insert đầy đủ |
| Count-Min Sketch | Ước lượng tần suất key | Với cập nhật không âm, ước lượng có thể cao hơn thật; phụ thuộc width/depth |
| Reservoir sampling | Lấy mẫu đều từ stream có độ dài chưa biết | Mẫu không chứa toàn bộ dữ liệu; phải lưu seed/size nếu cần tái lập |
| Quantile sketch | Ước lượng percentile | Sai số/rank guarantee tùy thuật toán và tham số |

Không thay exact distinct count bằng HyperLogLog mà không nói rõ sai số. Không dùng Bloom filter như bằng chứng chắc chắn một key tồn tại, vì false positive. Nếu hệ thống quyết định xóa dữ liệu dựa trên một membership check, false positive có thể gây mất dữ liệu.

### 9.1. Khi approximate không phù hợp

- Đối soát tài chính/pháp lý cần exact result.
- Xác định chính xác record nào thiếu hoặc trùng.
- Kết quả là điều kiện quyết định quyền truy cập hoặc an toàn.
- Đề bài yêu cầu số lượng chính xác.
- Sai số nhỏ vẫn có thể làm thay đổi quyết định ngưỡng.

Có thể dùng approximate sketch để ước lượng trước, rồi exact processing để xác nhận phần quan trọng.

## 10. Phân tán: chỉ mở rộng khi một máy không đủ

Chia dữ liệu trên nhiều worker có thể tăng CPU, RAM và băng thông aggregate, nhưng phải trả chi phí network, serialization, shuffle, coordination và retry.

### 10.1. Partition by key/range

Hash partition phân phối key; range partition giữ thứ tự theo miền key, hữu ích cho range query hoặc sort. Hash dễ phân phối nhưng không giữ global order; range giữ order nhưng dễ skew nếu boundary không cân bằng.

### 10.2. Shuffle là chi phí lớn

GROUP BY, join hoặc global sort thường cần shuffle dữ liệu giữa workers. Cần tính:

- Bao nhiêu byte rời worker ban đầu?
- Bao nhiêu bản ghi bị serialize?
- Có thể aggregate/filter trước shuffle không?
- Một worker có nhận quá nhiều hot keys không?
- Có cần replicate small dimension table không?
- Network bandwidth và concurrency có đủ không?

Giảm dữ liệu trước shuffle thường hiệu quả hơn tăng worker một cách mù quáng.

### 10.3. Distributed không tự động nhanh hơn

Nếu input chỉ 2 GB và một máy có SSD/RAM đủ, việc tạo cluster có thể tốn nhiều hơn thời gian xử lý. Nếu partition skew nặng, một worker chậm sẽ kéo dài toàn stage. Chọn phân tán khi có lý do đo được về throughput, capacity, availability hoặc thời gian hoàn thành.

## 11. Ngân sách RAM, disk, file descriptor và an toàn vận hành

### 11.1. RAM budget

Đặt:

```text
R_available =
    process memory limit
    - JVM/runtime baseline
    - safety margin
    - other concurrent work.
```

Với external sort int32, chunk chiếm khoảng 4*C bytes. Merge có F input buffers và một output buffer:

```text
run generation ≈ 4*C + 2*bufferBytes + runtime overhead.
merge           ≈ (F+1)*bufferBytes + O(F) metadata.
```

Chọn C và F sao cho peak của từng pha nhỏ hơn R_available. Không cộng/ước lượng theo heap array rồi quên native buffer và OS.

Trong Java, -Xmx là giới hạn heap, không phải giới hạn RSS toàn tiến trình. Direct buffers, thread stacks, metaspace, code cache và native allocations cũng dùng memory.

### 11.2. Disk budget

Với input size S:

- Runs ban đầu khoảng S.
- Khi merge, run generation cũ và thế hệ mới có thể đồng thời chiếm gần 2S scratch.
- Output cuối khoảng S.
- Input gốc vẫn tồn tại cho tới khi job hoàn tất.

Dự trù ít nhất gần 2S scratch, cộng input/output và margin. Nếu tất cả cùng volume, một ngân sách bảo thủ khoảng 3S tổng dung lượng đang dùng trong các pha cao điểm của demo là hợp lý; workload thực tế cần cộng file khác, block allocation và output Z.

### 11.3. File descriptor

Nếu fan-in F, merge thường mở F input streams và một output stream. Cộng log, socket, file khác. Giới hạn file descriptor thấp có thể khiến merge fail dù RAM đủ.

### 11.4. Temp directory và quyền truy cập

Chọn scratch location có dung lượng và throughput phù hợp, kiểm tra quota, quyền ghi, filesystem và giới hạn file count. Code demo tạo temp directory cạnh output để cùng filesystem; môi trường production có thể cần một volume scratch chuyên dụng.

### 11.5. Crash, retry và output an toàn

Code demo dọn temp directory trong finally khi process kết thúc bình thường hoặc có exception. Nếu tiến trình bị kill/power loss, temp directory có thể còn sót. Production nên:

- Đặt tên job/run ID và manifest.
- Ghi trạng thái pass, input identity và output checksum.
- Ghi output vào file tạm, verify xong rồi atomic rename nếu filesystem hỗ trợ.
- Dọn temp files cũ theo tuổi/job state có kiểm soát.
- Không xóa input gốc trước khi output được xác nhận.
- Có chính sách retry/idempotency và xử lý disk full.

Không xóa dữ liệu nguồn chỉ vì một pass đã chạy thành công.

## 12. Một quy trình chọn giải pháp có thể lặp lại

1. **Định nghĩa output:** exact/approximate, order, duplicates, no-result, update semantics.
2. **Đo input:** bytes on disk, decoded footprint, N, key cardinality, distribution, record width.
3. **Đo tài nguyên:** memory limit thực, scratch capacity, IOPS/bandwidth, file descriptors, concurrent jobs.
4. **Chọn pattern truy cập:** scan, sort, group, join, point lookup, range lookup, repeated query.
5. **Chọn thuật toán:** streaming, external sort, hash partition, database index, sketch hoặc distributed.
6. **Tính peak resource:** RAM, temp disk, open files, output size, passes và network shuffle.
7. **Nêu giả thiết/skew:** key distribution, sortedness, nonnegative, exactness, input immutable.
8. **Thử trên sample có phân phối xấu:** hot key, duplicate nhiều, record dài, empty, partial block, partition lệch.
9. **Đo end-to-end:** wall time, bytes read/written, peak RSS, heap, GC, queue wait, spill, retry.
10. **Đối chiếu correctness:** oracle độc lập, count, checksum, sorted order, duplicate semantics.
11. **Kiểm tra failure:** disk full, interrupted job, corrupt run, file descriptor limit, output exists.
12. **Chốt giới hạn:** ngưỡng kích thước, loại file, cấu hình C/F, số lượt, storage assumptions và fallback.

### 12.1. Benchmark cần so công bằng

Đừng so in-memory sort trên dữ liệu cache nóng với external sort đọc từ storage lạnh rồi kết luận một thuật toán luôn nhanh hơn. Cần ghi rõ:

- Input size và decoded footprint.
- CPU, RAM/container limit, storage type và filesystem.
- JVM, heap, GC, warm-up và số lần lặp.
- Buffer size, chunk capacity, fan-in.
- Disk cache warm/cold và có tiến trình khác dùng I/O không.
- Tổng bytes read/written, temp space peak và output validation.
- Thời gian chuẩn bị dữ liệu có được tính vào hay không.

Mục tiêu không phải một con số đẹp; mục tiêu là biết workload thật bị giới hạn bởi CPU, memory bandwidth, storage I/O, network hay skew.

## 13. Java 17+: external merge sort file-backed

Tệp ExternalMemoryChoiceDemo.java triển khai external merge sort cho **bản ghi số nguyên signed 32-bit cố định 4 byte**, theo binary big-endian mà DataInputStream.readInt()/DataOutputStream.writeInt() sử dụng.

### 13.1. Hợp đồng và giới hạn của chương trình

**Preconditions:**

- Input file tồn tại và không bị sửa trong khi sort.
- File size là bội số của 4 byte.
- Input và output là hai file khác nhau.
- maxRecordsInMemory>=1, fanIn>=2, bufferBytes>=4.
- Output parent có quyền tạo file/temp directory và đủ dung lượng.

**Postconditions khi hàm trả thành công:**

- Output chứa chính xác mọi int record trong input.
- Output được sắp xếp tăng dần.
- Số record không đổi.
- File rỗng tạo output rỗng.
- Output cũ ở đường dẫn đích được thay thế.

**Invariant:**

- Mỗi run được ghi ra đều sorted.
- Các run cùng một generation phân hoạch input, không bỏ/thêm record.
- Trong merge, heap chứa head nhỏ nhất hiện tại của mỗi run chưa cạn.
- Mỗi lần lấy head nhỏ nhất, output prefix vẫn sorted và chứa đúng các record đã lấy.
- Mỗi pass giảm số run bằng nhóm tối đa fan-in; với F>=2, cuối cùng còn tối đa một run.

**Limitations:**

- Chỉ đọc binary int32, không parse CSV/JSON/Parquet.
- Không bảo toàn thứ tự ban đầu của các record bằng nhau; với int primitive, giá trị bằng nhau không phân biệt được. Record production cần tie-breaker sequence ID nếu stable sort quan trọng.
- Không hỗ trợ checksum, resume sau process crash hoặc atomic publish.
- Nếu input bị thay đổi đồng thời, kết quả không được bảo đảm.
- Temp files cần dung lượng; lỗi I/O có thể khiến hàm throw.
- maxRecordsInMemory là giới hạn số phần tử trong chunk, không phải hard cap toàn bộ RSS JVM; phải tính buffers/runtime.

### 13.2. Mã Java đầy đủ

```java
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class ExternalMemoryChoiceDemo {
    record Head(int value, int run) {}
    record SortStats(long records, long initialRuns, int mergePasses) {}

    @FunctionalInterface
    interface IOAction {
        void run() throws Exception;
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static boolean expectFailure(
            Class<? extends Throwable> expected, IOAction action)
            throws Exception {
        try {
            action.run();
            return false;
        } catch (Throwable error) {
            if (expected.isInstance(error)) return true;
            throw new AssertionError("Unexpected exception: " + error);
        }
    }

    static String runName(long index) {
        return String.format(Locale.ROOT, "run-%020d.bin", index);
    }

    static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (Stream<Path> paths = Files.walk(root)) {
            Iterator<Path> iterator =
                    paths.sorted(Comparator.reverseOrder()).iterator();
            while (iterator.hasNext()) {
                Files.deleteIfExists(iterator.next());
            }
        }
    }

    static void mergeRuns(Path inputDir, long firstRun, int runCount,
            Path output, int bufferBytes) throws IOException {
        DataInputStream[] inputs = new DataInputStream[runCount];
        long[] remaining = new long[runCount];
        PriorityQueue<Head> queue = new PriorityQueue<>(
                Comparator.comparingInt(Head::value)
                        .thenComparingInt(Head::run));
        try {
            for (int i = 0; i < runCount; i++) {
                Path path = inputDir.resolve(runName(firstRun + i));
                long bytes = Files.size(path);
                if (bytes % Integer.BYTES != 0) {
                    throw new IOException("Corrupt run file: " + path);
                }
                remaining[i] = bytes / Integer.BYTES;
                inputs[i] = new DataInputStream(new BufferedInputStream(
                        Files.newInputStream(path), bufferBytes));
                if (remaining[i] > 0) {
                    queue.add(new Head(inputs[i].readInt(), i));
                    remaining[i]--;
                }
            }
            try (DataOutputStream out = new DataOutputStream(
                    new BufferedOutputStream(
                            Files.newOutputStream(output), bufferBytes))) {
                while (!queue.isEmpty()) {
                    Head head = queue.remove();
                    out.writeInt(head.value());
                    int source = head.run();
                    if (remaining[source] > 0) {
                        queue.add(new Head(inputs[source].readInt(), source));
                        remaining[source]--;
                    }
                }
            }
        } finally {
            IOException closeFailure = null;
            for (DataInputStream input : inputs) {
                if (input != null) {
                    try {
                        input.close();
                    } catch (IOException error) {
                        if (closeFailure == null) closeFailure = error;
                        else closeFailure.addSuppressed(error);
                    }
                }
            }
            if (closeFailure != null) throw closeFailure;
        }
    }

    // File-backed external merge sort for fixed-width signed 32-bit records.
    // RAM is bounded by one chunk, fanIn input buffers, one output buffer,
    // and O(fanIn) merge heads; run-path metadata is generated by index.
    static SortStats sort(Path input, Path output, int maxRecordsInMemory,
            int fanIn, int bufferBytes) throws IOException {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(output, "output");
        if (maxRecordsInMemory < 1 || fanIn < 2 || bufferBytes < 4) {
            throw new IllegalArgumentException(
                    "Need chunk>=1, fanIn>=2 and buffer>=4");
        }
        Path source = input.toAbsolutePath().normalize();
        Path destination = output.toAbsolutePath().normalize();
        if (source.equals(destination)
                || (Files.exists(destination)
                    && Files.isSameFile(source, destination))) {
            throw new IllegalArgumentException(
                    "Input and output must be different files");
        }
        long bytes = Files.size(source);
        if (bytes % Integer.BYTES != 0) {
            throw new IOException(
                    "Input must contain complete 4-byte integer records");
        }
        long totalRecords = bytes / Integer.BYTES;
        Path parent = destination.getParent();
        Files.createDirectories(parent);
        Path work = Files.createTempDirectory(parent, ".external-sort-");
        try {
            Path currentDir = Files.createDirectory(work.resolve("runs-0000"));
            long runCount = 0;
            long remainingRecords = totalRecords;
            try (DataInputStream in = new DataInputStream(
                    new BufferedInputStream(
                            Files.newInputStream(source), bufferBytes))) {
                while (remainingRecords > 0) {
                    int count = (int) Math.min(
                            (long) maxRecordsInMemory, remainingRecords);
                    int[] chunk = new int[count];
                    for (int i = 0; i < count; i++) {
                        chunk[i] = in.readInt();
                    }
                    Arrays.sort(chunk);
                    Path run = currentDir.resolve(runName(runCount));
                    try (DataOutputStream out = new DataOutputStream(
                            new BufferedOutputStream(
                                    Files.newOutputStream(run), bufferBytes))) {
                        for (int value : chunk) out.writeInt(value);
                    }
                    runCount++;
                    remainingRecords -= count;
                }
            }

            long initialRuns = runCount;
            int mergePasses = 0;
            while (runCount > 1) {
                Path nextDir = Files.createDirectory(
                        work.resolve(String.format(
                                Locale.ROOT, "runs-%04d", mergePasses + 1)));
                long nextRunCount = runCount / fanIn
                        + (runCount % fanIn == 0 ? 0 : 1);
                long groupStart = 0;
                long outputIndex = 0;
                while (groupStart < runCount) {
                    int groupSize = (int) Math.min(
                            (long) fanIn, runCount - groupStart);
                    Path target = nextDir.resolve(runName(outputIndex++));
                    if (groupSize == 1) {
                        Files.move(currentDir.resolve(runName(groupStart)),
                                target);
                    } else {
                        mergeRuns(currentDir, groupStart, groupSize,
                                target, bufferBytes);
                    }
                    groupStart += groupSize;
                }
                deleteTree(currentDir);
                currentDir = nextDir;
                runCount = nextRunCount;
                mergePasses++;
            }

            if (runCount == 0) {
                try (OutputStream ignored = Files.newOutputStream(
                        destination, StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE)) {
                    // Empty input has an empty output.
                }
            } else {
                Files.copy(currentDir.resolve(runName(0)), destination,
                        StandardCopyOption.REPLACE_EXISTING);
            }
            return new SortStats(totalRecords, initialRuns, mergePasses);
        } finally {
            deleteTree(work);
        }
    }

    static void writeInts(Path path, int[] values) throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(Files.newOutputStream(path)))) {
            for (int value : values) out.writeInt(value);
        }
    }

    static boolean equalsExpected(Path path, int[] expected)
            throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(path)))) {
            for (int value : expected) {
                if (in.readInt() != value) return false;
            }
            return in.read() == -1;
        }
    }

    static void examples() throws Exception {
        Path demo = Files.createTempDirectory("external-memory-choice-demo-");
        try {
            Path input = demo.resolve("input.bin");
            Path output = demo.resolve("sorted.bin");
            int[] values = new int[10_003];
            SplittableRandom random = new SplittableRandom(5592026L);
            for (int i = 0; i < values.length; i++) {
                values[i] = random.nextInt(-1001, 1002);
            }
            int[] expected = values.clone();
            Arrays.sort(expected);
            writeInts(input, values);

            SortStats stats = sort(input, output, 127, 3, 1024);
            check(stats.records() == values.length, "Record count mismatch");
            check(stats.initialRuns() == 79, "Initial run count mismatch");
            check(stats.mergePasses() == 4, "Merge pass count mismatch");
            check(equalsExpected(output, expected),
                    "External result differs from in-memory oracle");
            System.out.println("External sort: records=" + stats.records()
                    + ", initialRuns=" + stats.initialRuns()
                    + ", mergePasses=" + stats.mergePasses()
                    + ", fanIn=3");
            System.out.println("Output oracle: PASS, first=" + expected[0]
                    + ", last=" + expected[expected.length - 1]);

            Path emptyInput = demo.resolve("empty.bin");
            Path emptyOutput = demo.resolve("empty-sorted.bin");
            Files.createFile(emptyInput);
            SortStats emptyStats = sort(
                    emptyInput, emptyOutput, 8, 2, 128);
            check(emptyStats.records() == 0
                    && Files.size(emptyOutput) == 0,
                    "Empty input handling failed");
            System.out.println("Empty input: records=0, outputBytes=0");

            Path invalid = demo.resolve("invalid.bin");
            Files.write(invalid, new byte[] {1, 2, 3});
            boolean badWidthRejected = expectFailure(IOException.class,
                    () -> sort(invalid, demo.resolve("bad-out.bin"),
                            8, 2, 128));
            check(badWidthRejected, "Partial integer record not rejected");
            System.out.println("Invalid 3-byte input rejected: "
                    + badWidthRejected);

            boolean samePathRejected = expectFailure(
                    IllegalArgumentException.class,
                    () -> sort(input, input, 8, 2, 128));
            check(samePathRejected, "Same input/output must be rejected");
            System.out.println("Same input/output path rejected: "
                    + samePathRejected);
            System.out.println(
                    "Random oracle QA: PASS (10003 exact records; "
                    + "multi-pass merge; empty and invalid cases)");
        } finally {
            deleteTree(demo);
        }
    }

    public static void main(String[] args) throws Exception {
        examples();
    }
}
```

### 13.3. Biên dịch và chạy

Dùng JDK 17 trở lên. Lưu đúng tên file:

```bash
javac ExternalMemoryChoiceDemo.java
java ExternalMemoryChoiceDemo
```

**Stdout chính xác:**

```text
External sort: records=10003, initialRuns=79, mergePasses=4, fanIn=3
Output oracle: PASS, first=-1001, last=1001
Empty input: records=0, outputBytes=0
Invalid 3-byte input rejected: true
Same input/output path rejected: true
Random oracle QA: PASS (10003 exact records; multi-pass merge; empty and invalid cases)
```

### 13.4. Giải thích chương trình

**Run generation:** Đọc tối đa 127 số mỗi chunk, sort trong một int[], rồi ghi run binary. 10.003 record tạo:

```text
ceil(10003/127) = 79 initial runs.
```

**Multi-way merge:** Fan-in 3, mỗi nhóm mở tối đa 3 input runs. Heap chứa head hiện tại của các run. Các lượt:

```text
79 -> 27 -> 9 -> 3 -> 1
```

nên có 4 merge passes. Run đơn lẻ ở nhóm cuối được move sang generation mới mà không cần merge record.

**Không giữ danh sách toàn bộ path:** Run path được sinh từ chỉ số long; bộ nhớ không cần List<Path> kích thước R. Thư mục vẫn có nhiều file metadata trên filesystem, nên giới hạn file count và performance directory vẫn cần theo dõi.

**Oracle độc lập:** Test harness giữ một mảng nhỏ 10.003 phần tử, clone và dùng Arrays.sort để tạo kết quả chuẩn; sau đó đọc output file tuần tự và so từng giá trị. Mảng oracle chỉ dùng trong test, không nằm trong thuật toán external sort.

**File rỗng:** Không có run nào; chương trình tạo output file 0 byte.

**File 3 byte:** Không chứa đủ một int32 record, nên bị từ chối bằng IOException.

**Input/output trùng:** Bị từ chối để tránh ghi đè nguồn trước khi xử lý xong.

### 13.5. Độ phức tạp và ngân sách của code

Gọi N là số record, C là maxRecordsInMemory, F là fan-in, B là số record mỗi block và R=ceil(N/C):

```text
Initial runs: R = ceil(N/C).
Merge passes: P = ceil(log_F R), for R>1.

Run generation CPU: O(N log C).
Each merge pass CPU: O(N log F).
All merge passes: O(P*N log F).

Run generation RAM:
    O(C + bufferBytes) records/bytes, plus output buffer.

Merge RAM:
    O(F*bufferBytes + F) plus output buffer.

Heap/path metadata:
    O(F) for a merge group; run index is scalar long.
```

Với implementation này, I/O upper estimate gồm run generation, P merge passes và final copy:

```text
about 2*(N/B)*(P+2) block transfers.
```

Đây là ước lượng khi các lượt đọc/ghi quét toàn bộ dữ liệu; singleton run move và partial block có thể làm số thực tế thấp hơn. Engine ghi trực tiếp lượt merge cuối vào output có thể bỏ cặp read/write final copy.

## 14. Các lỗi phổ biến khi xử lý dữ liệu vượt RAM

1. So sánh file size với RAM mà không tính decoded object footprint.
2. Dùng tổng RAM máy thay cho memory limit thực của process/container.
3. Quên heap, native/direct buffers, thread stacks, GC và page cache.
4. Parse toàn bộ file vào một ArrayList rồi gọi đó là streaming.
5. Đọc stream nhưng giữ HashMap có số key tăng không giới hạn.
6. Cho rằng exact distinct count luôn có thể tính với O(1) memory.
7. Dùng approximate sketch mà không ghi sai số và semantics.
8. Dùng Bloom filter như bằng chứng chắc chắn key tồn tại.
9. Chọn external sort khi dữ liệu đã sorted và chỉ cần aggregate một lần.
10. Chọn hash aggregation khi cần output theo thứ tự key.
11. Dùng hash join khi build-side hash table thực tế không vừa RAM.
12. Ước lượng build-side theo file nén thay vì decoded hash footprint.
13. Mở tất cả run cùng lúc, vượt file descriptor limit.
14. Chọn fan-in lớn mà quên F input buffers.
15. Chọn chunk quá lớn, gây OOM hoặc GC pressure.
16. Chọn chunk quá nhỏ, tạo quá nhiều run và merge passes.
17. Quên tính chi phí đọc/ghi từng lượt merge.
18. Dùng công thức I/O không tính final copy của implementation đang viết.
19. Coi một block transfer là một millisecond cố định trên mọi storage.
20. Dùng random reads dày đặc mà không tính latency/cache miss.
21. Coi memory mapping làm dữ liệu lớn tự động vừa RAM.
22. Không dự trù scratch space khi old/new generations cùng tồn tại.
23. Xóa run cũ trước khi thế hệ mới được ghi hoàn tất.
24. Không có cleanup cho temp files sau crash.
25. Ghi đè input bằng output trước khi xử lý xong.
26. Không kiểm tra file size có phải bội record width không.
27. Đọc record variable-length mà không validate length/truncation.
28. Không kiểm tra số record hoặc checksum sau sort/merge.
29. Không bảo toàn duplicate records khi merge.
30. Giả định tie ordering ổn định dù comparator không có sequence ID.
31. Hash partition nhưng dùng hash seed/key normalization không nhất quán.
32. Cho rằng hash partition bảo đảm partition size bằng nhau.
33. Không xử lý heavy hitter/skew.
34. Repartition cùng một key mà không có bước partial aggregation/reduce đúng.
35. Dùng hash join cho skewed key tạo output Cartesian product khổng lồ mà không tính Z.
36. Dùng nested-loop join cho hai bảng lớn mà không tính số lần scan.
37. Sort cả hai bên để sort-merge join dù một bên đã có index/order hữu ích.
38. Không tính serialization/network shuffle khi phân tán.
39. Tăng worker mà không đo network và storage bottleneck.
40. Không dùng predicate pushdown/partition pruning khi scan dữ liệu columnar.
41. Tạo index cho một query chạy một lần mà không tính build cost.
42. Không tính update/compaction/write amplification của index/LSM.
43. Không đặt bounded queue/backpressure trong streaming pipeline.
44. Chỉ đo CPU time mà bỏ bytes read/written và spill.
45. Benchmark với cache nóng/lạnh không nhất quán.
46. Dùng test oracle in-memory trên input production khổng lồ.
47. Không test empty file, partial block, duplicate-heavy và skew.
48. Không kiểm tra disk full, permission, temp quota và interrupted I/O.
49. Coi code demo fixed-width int32 là parser tổng quát cho CSV/JSON.
50. Tuyên bố RAM bounded nhưng vẫn giữ List<Path> cho hàng tỷ run.
51. Không ghi rõ input có được phép mutate trong lúc chạy không.
52. Coi random test PASS là chứng minh mọi input/file corruption đều đúng.
53. Không phân biệt giới hạn correctness với giới hạn throughput/capacity.
54. Không tính output Z có thể lớn hơn input.
55. Không ghi rõ output được overwrite hay append.
56. Không có kế hoạch retry/idempotency khi một pass thất bại.
57. Xóa nguồn trước khi output được verify/publish.
58. Dùng approximate result trong nghiệp vụ cần exact answer.
59. Chọn distributed processing khi overhead cluster lớn hơn workload.
60. Không ghi các giả thiết, bất biến và giới hạn của chính implementation.

## 15. Bài tập tự luyện kèm đáp án

**Bài 1.** Vì sao file nén 4 GB có thể cần nhiều hơn 4 GB RAM khi parse?

**Đáp án:** Object/string/map representation có overhead và dữ liệu sau decode có thể lớn hơn file nén.

**Bài 2.** Streaming phù hợp nhất với công việc nào?

**Đáp án:** Một lượt scan, filter/transform hoặc aggregation có state bị chặn.

**Bài 3.** Vì sao đọc file theo stream nhưng giữ mọi key trong HashMap vẫn có thể OOM?

**Đáp án:** HashMap state tăng theo cardinality; stream chỉ giới hạn input buffer, không giới hạn state.

**Bài 4.** Khi nào exact sort cần external processing?

**Đáp án:** Khi toàn bộ tập cần sắp xếp không thể giữ cùng lúc trong RAM khả dụng.

**Bài 5.** Run generation của external merge sort làm gì?

**Đáp án:** Đọc từng chunk vừa RAM, sort chunk và ghi sorted run xuống storage.

**Bài 6.** N=10003, C=127, có bao nhiêu run ban đầu?

**Đáp án:** ceil(10003/127)=79.

**Bài 7.** R=79, F=3 cần bao nhiêu merge passes?

**Đáp án:** 4: 79→27→9→3→1.

**Bài 8.** Vì sao fan-in không nên tăng vô hạn?

**Đáp án:** Mỗi run cần buffer/stream và file descriptor; RAM và giới hạn OS sẽ bị vượt.

**Bài 9.** Mỗi merge pass đọc và ghi dữ liệu ra sao?

**Đáp án:** Thường đọc toàn bộ các run đầu vào và ghi các run kết quả, xấp xỉ 2N/B block transfers.

**Bài 10.** Vì sao code demo có P+2 thay vì P+1 trong công thức I/O?

**Đáp án:** Nó ghi run cuối xuống scratch rồi copy run ấy sang output, thêm một lượt đọc/ghi.

**Bài 11.** Nếu merge cuối ghi trực tiếp output, tiết kiệm gì?

**Đáp án:** Bỏ một lần đọc và một lần ghi toàn bộ run cuối.

**Bài 12.** Với C=10 triệu int, riêng chunk array chiếm khoảng bao nhiêu?

**Đáp án:** Khoảng 40 triệu byte (xấp xỉ 38,1 MiB), chưa tính JVM overhead.

**Bài 13.** Merge fan-in 64 với buffer 64 KiB mỗi input cần bao nhiêu input buffer?

**Đáp án:** 4 MiB cho 64 input buffers, cộng output buffer và metadata.

**Bài 14.** Vì sao cần tính file descriptor?

**Đáp án:** Mỗi input run đang merge cần một file stream mở; quá nhiều có thể vượt giới hạn OS.

**Bài 15.** Hash partition GROUP BY cần bất biến gì?

**Đáp án:** Mọi record có cùng key phải vào cùng partition.

**Bài 16.** Hash partition có bảo đảm mọi partition bằng kích thước nhau không?

**Đáp án:** Không; skew và heavy hitters có thể tạo partition lớn.

**Bài 17.** Đổi hash seed có luôn chia được một hot key thành nhiều partition độc lập không?

**Đáp án:** Không; cùng key vẫn phải được hợp nhất đúng. Có thể partial aggregate rồi reduce nếu phép gộp cho phép.

**Bài 18.** Khi nào Grace hash join phù hợp?

**Đáp án:** Cả hai phía lớn, có thể partition cùng hash key và từng cặp partition xử lý được trong RAM hoặc có recursive spill.

**Bài 19.** Điều kiện partition của hai phía join là gì?

**Đáp án:** Cùng hash function, seed và key normalization để các key khớp rơi vào cùng partition.

**Bài 20.** Vì sao join output có thể lớn hơn hai input?

**Đáp án:** Nếu một key xuất hiện r lần ở R và s lần ở S, join có thể tạo r*s cặp.

**Bài 21.** Khi nào sort-merge join đáng cân nhắc?

**Đáp án:** Khi input đã sorted hoặc cần thứ tự, và scan tuần tự hai phía có lợi.

**Bài 22.** Khi nào hash join in-memory phù hợp?

**Đáp án:** Khi hash table của phía build vừa memory budget sau khi tính object overhead.

**Bài 23.** Nested-loop join có thể hợp lý khi nào?

**Đáp án:** Một phía rất nhỏ hoặc block nested loop giúp tái sử dụng block trong RAM; phải tính số lượt scan.

**Bài 24.** Khi nào nên dùng B-tree index?

**Đáp án:** Nhiều point/range lookups lặp lại, và chi phí build/update/storage index được bù bởi truy vấn.

**Bài 25.** LSM-tree thường tối ưu workload nào?

**Đáp án:** Workload ghi nhiều, gom writes và flush/compact thành sorted runs; đổi lại có compaction/write amplification.

**Bài 26.** Predicate pushdown giúp gì?

**Đáp án:** Đẩy điều kiện lọc xuống storage/query scan để bỏ qua record/partition/column không cần đọc.

**Bài 27.** HyperLogLog trả exact distinct count không?

**Đáp án:** Không, nó ước lượng với sai số thống kê.

**Bài 28.** Bloom filter có thể có false positive không?

**Đáp án:** Có; membership có thể báo “có thể có” dù key chưa được thêm.

**Bài 29.** Count-Min Sketch với cập nhật không âm có tính chất ước lượng nào?

**Đáp án:** Ước lượng tần suất thường không thấp hơn tần suất thật, với sai số phụ thuộc tham số và giả thiết.

**Bài 30.** Vì sao không dùng approximate count cho đối soát cần exact?

**Đáp án:** Sai số có thể làm thay đổi quyết định hoặc không đáp ứng yêu cầu chính xác.

**Bài 31.** Phân tán có luôn nhanh hơn một máy?

**Đáp án:** Không; network shuffle, serialization, skew và coordination có thể lớn hơn lợi ích.

**Bài 32.** Cần đo gì ngoài CPU time khi external sort?

**Đáp án:** Bytes read/written, số pass, peak scratch, peak RSS, heap, GC, I/O wait và throughput storage.

**Bài 33.** Vì sao memory mapping không giải quyết tự động dữ liệu lớn hơn RAM?

**Đáp án:** Trang dữ liệu vẫn được paging từ storage; access pattern xấu có thể gây page faults/thrashing.

**Bài 34.** Nếu old và new merge generations cùng tồn tại, cần dự trù gì?

**Đáp án:** Scratch có thể gần 2 lần kích thước dataset, cộng input/output và margin.

**Bài 35.** Vì sao code demo không giữ List<Path> của mọi run?

**Đáp án:** Tránh heap metadata tăng theo R; path được sinh từ chỉ số run.

**Bài 36.** Nếu record là CSV variable-length, code int32 demo dùng trực tiếp được không?

**Đáp án:** Không; cần parser/record framing, length validation và buffer cho record variable-length.

**Bài 37.** Nếu cần stable sort record trùng key, phải thêm gì?

**Đáp án:** Sequence ID hoặc original position làm tie-breaker trong comparator và được lưu cùng record.

**Bài 38.** Nếu file input có 3 byte trong định dạng int32, hành vi đúng?

**Đáp án:** Từ chối vì file không chứa số nguyên record hoàn chỉnh.

**Bài 39.** Vì sao phải verify record count sau sort?

**Đáp án:** Để phát hiện mất/thêm record trong run generation hoặc merge; có thể bổ sung checksum/multiset validation.

**Bài 40.** Nêu ba điều kiện trước khi đưa external algorithm vào production.

**Đáp án:** RAM/scratch/file descriptor được dự trù, correctness được kiểm với oracle/checksum, và failure/retry/cleanup/output publish có hợp đồng rõ.

## 16. Checklist quyết định và triển khai

- [ ] Đã định nghĩa exactness, ordering, duplicates và output semantics?
- [ ] Đã đo N, record width, decoded footprint và key cardinality?
- [ ] Đã xác định RAM budget thực của process/container?
- [ ] Đã tính object/HashMap/buffer/thread/native overhead?
- [ ] Công việc có thể giải bằng một lượt streaming state nhỏ?
- [ ] Nếu cần sort, đã tính C, R, F và số merge passes?
- [ ] Fan-in thỏa RAM buffer và file descriptor limits?
- [ ] I/O estimate có tính run generation, mỗi merge pass và final copy?
- [ ] Scratch space đủ cho old/new generations, input và output?
- [ ] Output Z có thể lớn hơn input và đã được dự trù?
- [ ] Nếu hash partition, đã phân tích skew/heavy hitters?
- [ ] Nếu join, đã tính build-side footprint và output cardinality?
- [ ] Nếu query lặp, đã so scan với index/database build cost?
- [ ] Nếu approximate, đã ghi sai số và false-positive/overestimate semantics?
- [ ] Nếu distributed, đã tính network shuffle, serialization và retry?
- [ ] Pipeline có bounded queue/backpressure?
- [ ] File format, encoding, record width/length và checksum rõ?
- [ ] Input có được giữ immutable trong lúc xử lý?
- [ ] Có kế hoạch temp cleanup, crash recovery và idempotent retry?
- [ ] Output được verify trước khi publish hoặc xóa nguồn?
- [ ] Có test empty, duplicates, negative values, skew, partial record, disk errors?
- [ ] Oracle độc lập và test sample không vượt RAM budget của test harness?
- [ ] Benchmark có ghi phần cứng, cache, buffer, heap và bytes I/O?
- [ ] Đã ghi rõ giới hạn của code mẫu so với production engine?

## Kết luận

Khi dữ liệu không vừa bộ nhớ, hãy chọn thuật toán theo mẫu công việc và mô hình I/O:

- **Streaming** cho scan một lượt và state nhỏ.
- **External merge sort** khi cần thứ tự chính xác trên toàn tập.
- **External hash partition** cho GROUP BY/hash join khi partition có thể được xử lý trong RAM, đồng thời phải xử lý skew.
- **Sort-merge join** khi có thứ tự hoặc cần sequential scans.
- **Database/index/columnar storage** cho truy vấn lặp lại, point/range access và analytic scans.
- **Approximate sketches** chỉ khi sai số được chấp nhận.
- **Distributed processing** khi capacity/throughput của một máy thực sự không đủ sau khi đã tính network overhead.

Quyết định tốt cần dựa trên RAM khả dụng, decoded footprint, block size, số pass, fan-in, file descriptor, scratch space, output size và phân phối dữ liệu. Chương trình Java trong bài minh họa một cách triển khai **external merge sort file-backed**, giữ chunk và merge buffers trong giới hạn đã cấu hình, xác minh output với oracle độc lập và nêu rõ những giới hạn của định dạng cùng môi trường chạy.