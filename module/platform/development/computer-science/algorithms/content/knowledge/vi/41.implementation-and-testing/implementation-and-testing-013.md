# Đo thời gian, bộ nhớ và tách chi phí chuẩn bị dữ liệu

Khi so sánh hai thuật toán, câu hỏi **“thuật toán nào nhanh hơn, dùng ít bộ nhớ hơn?”** chỉ có ý nghĩa nếu ta biết **đã đo những công đoạn nào**, **đầu vào có tương đương không**, **môi trường thực thi ra sao** và **đơn vị đo đại diện cho điều gì**. Một thuật toán truy vấn rất nhanh nhưng cần xây chỉ mục tốn thời gian có thể thua cách quét trực tiếp khi chỉ hỏi một lần; một phương pháp có bộ nhớ cuối thấp không nhất thiết có **đỉnh bộ nhớ (peak)** thấp; và một lần chạy Java có thể bị ảnh hưởng mạnh bởi JIT, GC, cache, hệ điều hành.

Bài thuộc nhóm **Cài đặt và kiểm thử** của **Computer Science Algorithms**, chủ đề **Đo thời gian, bộ nhớ và tách chi phí chuẩn bị dữ liệu**. Mục tiêu là thiết kế phép đo **có thể tái hiện, công bằng, giải thích được**, không phải đọc một con số nanosecond rồi vội kết luận.

Ta sẽ phân biệt bốn phạm vi đo:
1. **Chuẩn bị dữ liệu:** sinh/đọc input, parse, clone, validate, chuẩn hóa và tạo tập truy vấn.
2. **Tiền xử lý hoặc xây cấu trúc:** sort, nén tọa độ, xây prefix sums, index, graph adjacency, sieve, DP table, cache.
3. **Xử lý truy vấn hoặc nhân thuật toán:** chạy cùng một tập query trên cấu trúc đã có, tách khỏi build.
4. **End-to-end:** từ input thô đến kết quả cuối cùng, gồm các công đoạn mà người sử dụng thực sự phải trả.

Bài có ví dụ **quét đoạn trực tiếp** và **prefix sum** để minh họa việc tách chi phí, chương trình **Java 17 chạy độc lập**, stdout xác định, thời gian thực ghi riêng vào stderr vì thay đổi theo máy, kiểm chứng từng query bằng oracle và checklist dành cho bài thi thuật toán, thư viện, backend và benchmark.

## 1. Định nghĩa chính xác thứ đang đo

Một công việc thường có sơ đồ:

~~~text
raw input
   |
   v
load / parse / generate / normalize / copy / validate
   |                          T_prep
   v
build index / preprocessing / allocate data structures
   |                          T_build
   v
run Q queries / compute answer
   |                          T_query
   v
format / serialize / write result
                              T_output
~~~

Với một lượt xử lý, phương trình khái niệm là:

\[
T_{\mathrm{total}}
\approx T_{\mathrm{prep}}+T_{\mathrm{build}}+
T_{\mathrm{query}}+T_{\mathrm{output}}+T_{\mathrm{overhead}}.
\]

Dấu **xấp xỉ** quan trọng: các pha có thể chồng lấp trong pipeline song song, chi phí nền như GC không dễ gán vào một công đoạn, và tổng các **median của các lần đo riêng biệt** không bắt buộc bằng median của phép đo **end-to-end độc lập**.

**Hỏi trước khi đo:**
- So sánh **một query**, **100.000 query**, hay toàn bộ quá trình chạy từ file tới output?
- Input đã có sẵn ở RAM hay phải đọc từ disk/network?
- Thuật toán được phép giữ index giữa nhiều request hay phải build mới mỗi request?
- Build chạy khi khởi động hệ thống, khi cập nhật dữ liệu, hay trước mỗi query?
- Đáp án được tiêu thụ thế nào để trình biên dịch không loại bỏ công việc?
- Cần đo **wall-clock latency**, **CPU time**, **throughput**, **allocation**, **retained heap**, hay **peak RSS**?

Không ghi rõ phạm vi khiến kết luận dễ bị đổi nghĩa. Ví dụ “prefix sum trả lời nhanh hơn quét” có thể đúng về **query-only** nhưng sai về **single-query end-to-end**.

## 2. Một ví dụ chuẩn: tổng đoạn bằng quét và prefix sum

Giả sử có mảng số nguyên a độ dài n và q truy vấn tổng đoạn nửa mở `[l,r)`, nghĩa là lấy các chỉ số l,l+1,...,r−1.

**Cách A — quét trực tiếp cho từng query:**

~~~text
rangeSumScan(a,l,r):
    sum=0
    for i in [l,r):
        sum += a[i]
    return sum
~~~

Tiền xử lý gần như không có, mỗi query có thời gian \(O(r-l)\). Tổng q truy vấn có thời gian:

\[
T_A=O\left(n_{\mathrm{load}}+\sum_{j=1}^q(r_j-l_j)\right).
\]

Ký hiệu \(n_{\mathrm{load}}\) chỉ phần chi phí nạp/chuẩn bị nếu cần; trong **query-only** sau khi input đã sẵn có, chi phí là tổng chiều dài các đoạn.

**Cách B — prefix sum:**

~~~text
prefix[0]=0
prefix[i+1]=prefix[i]+a[i]

rangeSumPrefix(prefix,l,r):
    return prefix[r]-prefix[l]
~~~

Xây index \(O(n)\) thời gian và O(n) bộ nhớ bổ sung; mỗi truy vấn \(O(1)\). Nếu tất cả query dùng **cùng mảng bất biến**:

\[
T_B=O(n+q).
\]

Không có một cách **luôn tốt hơn**. Với n=100.000 và một query dài 10 phần tử, quét 10 phần tử thường đáng hơn việc build 100.001 số prefix. Với 100.000 query dài trung bình 1.000 phần tử trên cùng mảng, xây prefix một lần thường có lợi rất lớn. Đây là nhận định **về khối lượng phép toán theo mô hình**, không phải lời hứa thời gian chạy tuyệt đối cho mọi phần cứng.

### 2.1. Công thức điểm hòa vốn

Đặt:
- \(B\): chi phí build prefix thực, tính theo cùng đơn vị thời gian;
- \(s\): thời gian một query quét trung bình;
- \(f\): thời gian một query prefix trung bình;
- \(q\): số query trên một phiên bản input.

Nếu chỉ xét build + query:

\[
T_A(q)\approx q\,s,\quad
T_B(q)\approx B+q\,f.
\]

Khi \(s>f\), prefix bắt đầu có lợi theo mô hình gần đúng nếu:

\[
\boxed{q>\frac{B}{s-f}}.
\]

Nếu \(s\le f\), mô hình này không cho điểm hòa vốn tích cực cho prefix. **Chỉ nên ước lượng B,s,f bằng phép đo có kiểm soát** hoặc bằng cost model có kiểm chứng; thay \(B\) bằng số nanosecond của một lần chạy đơn lẻ là rất nhiễu.

**Khi input bị cập nhật:** prefix snapshot có thể không còn phù hợp; nếu mỗi query có một lần update cần build lại, tổng chi phí thay đổi. Fenwick tree/segment tree hỗ trợ update và range query với đánh đổi O(log n) và bộ nhớ khác. Phải phân tích **tỷ lệ query/update** thay vì đánh đồng mọi workload.

## 3. Chi phí chuẩn bị dữ liệu: cần đo riêng và đúng phạm vi

“Chuẩn bị” có thể bao gồm:
- Tạo mảng, sinh dữ liệu giả có seed xác định;
- Đọc tệp, parse JSON/CSV/binary, giải nén;
- Tạo đồ thị từ edge list, chuẩn hóa chỉ số, loại trùng cạnh;
- Clone input để giữ hợp đồng không được mutate;
- Tạo danh sách truy vấn, random shuffle, lọc trường hợp hợp lệ;
- Chuyển `List<Integer>` sang `int[]`, chuyển string sang char/codepoint;
- Sort, coordinate compression, map key -> ID;
- Khởi tạo buffer, thread pool, connection, object cache.

Phải quyết định thao tác nào là **chuẩn bị chung cho mọi thuật toán** và thao tác nào là **tiền xử lý bắt buộc riêng của một phương án**. Không được âm thầm đưa **sort của thuật toán A ra ngoài vùng đo** rồi đưa **build index của thuật toán B vào trong**, vì so sánh end-to-end sẽ thiên vị A.

**Hai kiểu câu hỏi hợp lệ nhưng khác nhau:**

1. *Query-only:* giả sử dữ liệu và index đã sẵn sàng, một truy vấn mất bao lâu?
2. *End-to-end:* từ dữ liệu chưa có cấu trúc tới tất cả đáp án mất bao lâu, kể cả xây index?

Kết quả query-only không thay thế được kết quả end-to-end. Hai phép đo cần **đặt tên khác nhau**, tránh gọi chung là “runtime thuật toán”.

### 3.1. Chuẩn bị dữ liệu không được tạo bias

Giả sử A cần array đã sort, B chạy trực tiếp trên unsorted array. Nếu chỉ A nhận mảng đã sort từ bên ngoài mà không tính thời gian sort, đây không còn so sánh hai pipeline đầu vào tương đương.

Nếu hai phương án đều nhận một input **bất biến đã chuẩn hóa** theo hợp đồng, việc đo build/query riêng là công bằng vì chuẩn bị chung đã được công bố. Nếu hợp đồng người dùng là input thô, phải đo **toàn bộ pipeline** hoặc giải thích rõ điều kiện loại trừ.

**Đối với benchmark có mutation:** mỗi phương án phải nhận bản dữ liệu tương đương trước mỗi trial. Không để thuật toán in-place sort/sửa input rồi dùng chính input đã biến đổi cho phương án tiếp theo. Có thể clone có chủ đích và tính thời gian clone vào pha setup hoặc vào pipeline tùy hợp đồng; nêu rõ trong báo cáo.

## 4. `System.nanoTime()` dùng thế nào cho đúng?

Java cung cấp:

~~~java
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
~~~

`System.nanoTime()` phù hợp để đo **khoảng thời gian trôi qua (elapsed time)** trong cùng JVM. Giá trị tuyệt đối của nó không phải Unix timestamp và không được giải thích là “đã chạy lúc mấy giờ”. Độ phân giải hiển thị bằng **nanosecond** không có nghĩa đồng hồ đạt **độ chính xác tuyệt đối 1 ns**.

**Đừng dùng `System.currentTimeMillis()` cho benchmark ngắn:** đây là wall-clock time có thể bị đồng bộ/chỉnh giờ và độ phân giải thường kém hơn. `nanoTime()` đo **thời gian thực trôi qua**, bao gồm cả lúc thread bị OS tạm ngừng, chờ lock, GC pause hoặc block I/O.

**Ba loại thời gian khác nhau:**

| Chỉ số | Nó trả lời | Điều không thể suy ra |
| --- | --- | --- |
| Wall-clock/elapsed | Người dùng chờ bao lâu từ start tới finish | Không chỉ riêng thời gian CPU |
| Thread CPU time | Một thread dùng bao nhiêu thời gian CPU | Không bao quát worker threads khác |
| Process CPU time | Tất cả thread của process tiêu tốn bao nhiêu CPU | Không phải tổng thời gian chờ của người dùng |

Trong chương trình đa luồng, process CPU time có thể **lớn hơn** wall-clock vì nhiều core làm việc cùng lúc. Một thread đang chờ I/O có wall time tăng nhưng CPU time có thể thấp. `ThreadMXBean` có thể cung cấp CPU time **nếu JVM hỗ trợ và đã bật**, nhưng không mặc nhiên đại diện cho toàn process; để profile chuẩn cần công cụ phù hợp.

## 5. JIT, warm-up, tiered compilation và dead-code elimination

Java code thường không có chi phí ổn định ngay từ vòng chạy đầu. Khi JVM hoạt động, JIT có thể:
- Biên dịch bytecode nóng thành mã máy;
- Inline method;
- Tối ưu vòng lặp và range checks;
- Chuyên biệt theo profile của các nhánh đã thấy;
- Thay đổi garbage collection/caches khi allocation tăng.

Vì vậy đo một lần từ lúc process mới khởi động và kết luận chắc chắn thuật toán A “nhanh gấp 3” thường không đáng tin.

**Warm-up** chạy công việc trước các trial đo để tạo profile và giảm ảnh hưởng biên dịch JIT. Warm-up không bảo đảm mọi tầng JIT đã ổn định; so sánh nghiêm túc nên dùng nhiều **JVM forks** độc lập, nhiều iterations và kiểm tra độ biến thiên.

### 5.1. Nguy cơ bị tối ưu bỏ công việc

Benchmark sai:

~~~java
long t = System.nanoTime();
for (int i = 0; i < 100000; i++) {
    somePureComputation(i); // ket qua bi bo qua
}
long elapsed = System.nanoTime() - t;
~~~

Nếu kết quả không được quan sát, JVM có thể loại bỏ hoặc tái cấu trúc đáng kể phép tính. Tốc độ đo được có thể là tốc độ của **vòng lặp đã bị tối ưu**, không phải thuật toán định đo.

Trong demo, kết quả query được **cộng thành checksum**, kiểm tra với oracle và đưa vào một field **`volatile` sink** để làm kết quả có thể quan sát. Điều này giảm nguy cơ dead-code elimination, nhưng vẫn **không đảm bảo** một benchmark vi mô không bị các tối ưu khác tác động. Đối với phép đo nanosecond nghiêm túc, **JMH** thích hợp hơn một vòng `nanoTime()` tự viết, vì nó xử lý warm-up, forks, benchmark state và cách tiêu thụ kết quả chuyên biệt.

### 5.2. Gọi nhiều lần trong một sample

Nếu một query chỉ tốn rất ít nanosecond, chi phí gọi đồng hồ có thể cùng bậc hoặc lớn hơn công việc cần đo. Hãy đo **một batch đủ lớn**:

~~~text
start = nanoTime()
repeat R times:
    process all Q queries
elapsed = nanoTime() - start
average_approx = elapsed / (R * Q)
~~~

Giá trị `average_approx` là **trung bình trong batch**, không phải phân vị latency từng request, và không phản ánh queue/lock/GC của production nếu các yếu tố đó chưa được mô phỏng.

Một batch vẫn có cache/JIT effects; cần chọn workload đủ thực, số samples đủ, và tránh in ra console **bên trong** vùng đo. I/O console thường đắt và khó dự đoán hơn phép tính nhỏ.

## 6. Chạy nhiều trial, dùng median và phân vị đúng nghĩa

Một quy trình đơn giản:
1. Chuẩn bị bộ input/query cố định, có seed rõ.
2. Kiểm correctness trước khi benchmark.
3. Warm-up cả A và B.
4. Đo nhiều trial độc lập; **đổi thứ tự A/B** để hạn chế bias vì thermal/caches/JIT.
5. Ghi raw samples, median/p50, min và một phân vị cao phù hợp.
6. Nếu muốn kết luận thống kê, tăng số lần chạy và dùng confidence intervals/thử nghiệm nhiều JVM forks.

**Median/p50** là mẫu giữa sau khi sort thời gian đo, ít nhạy với outlier hơn mean. **p95** là giá trị tại một thứ hạng theo định nghĩa phân vị mà ta chọn; với **chỉ 7 samples**, nearest-rank p95 thực chất gần như **max** và không nên coi đó là ước lượng ổn định cho p95 production.

**Đọc số liệu có ngữ cảnh:** nếu median A=8 ms, B=7,9 ms nhưng độ dao động mỗi bên ±2 ms, không được diễn giải bằng lời chắc chắn “B nhanh hơn”. Cần tăng cỡ mẫu, kiểm sự khác nhau về dataset, GC/JIT và đặt cận ý nghĩa thực tế.

### 6.1. Những yếu tố làm trial khó tái hiện

| Yếu tố | Ảnh hưởng | Cách kiểm soát hoặc công bố |
| --- | --- | --- |
| JIT compilation | Những trial đầu có thể chậm hơn | Warm-up, nhiều JVM forks |
| GC | Pause, heap footprint thay đổi | Ghi collector/heap, GC logs/JFR |
| CPU scaling/thermal | Xung nhịp biến thiên | Máy ít nhiễu, test xen kẽ |
| OS scheduling | Thread bị preempt | Lặp trials, môi trường ổn định |
| Data distribution | Branch/cache/độ dài đoạn khác | Seed, histogram và input cố định |
| Order bias | Cách chạy sau hưởng cache nóng | Đảo thứ tự hoặc randomize balanced |
| Allocations | Memory pressure/GC khác nhau | Đo allocation và retained memory riêng |
| Dead-code elimination | Công việc biến mất | Checksum/blackhole/JMH |
| I/O/serialization | Che chi phí thuật toán | Đo end-to-end và kernel riêng |
| JVM flags/JDK | Optimizer/GC khác nhau | Ghi JDK, OS, flags |
| Background load | Nhiễu CPU/disk | Công bố môi trường, test lại |
| Worker/thread count | Throughput khác latency | Phân biệt wall/CPU, báo concurrency |

**Không “xóa” tùy tiện outlier** chỉ vì chúng khiến biểu đồ xấu. Đối với latency thật, GC pause hoặc contention có thể chính là thứ cần đo. Nếu đo microkernel và loại outlier do sự kiện ngoài phạm vi, phải định nghĩa quy tắc trước khi xem kết quả.

## 7. Bộ nhớ: ít nhất bốn khái niệm khác nhau

Một phép đo “RAM dùng bao nhiêu?” có thể đề cập bốn đại lượng rất khác:

1. **Logical payload / kích thước dữ liệu logic:** tổng byte của các primitive elements theo cấu trúc đã khai báo. Chưa tính headers, alignment, references, allocator, JIT, metadata.
2. **Allocated bytes:** tổng byte đã được JVM cấp phát qua toàn bộ thời gian đo; một chương trình có thể allocate hàng GB đối tượng ngắn sống nhưng retained heap cuối thấp.
3. **Live/retained heap:** những đối tượng còn reachable/sống sau một mốc hoặc sau một lần GC; khác với tổng đã allocate.
4. **Peak heap / process RSS:** mức bộ nhớ tối đa JVM heap hoặc bộ nhớ resident toàn process trong một khoảng; bao gồm/không bao gồm các vùng khác nhau tùy công cụ.

Ví dụ prefix sum `long[n+1]` có **payload** `(n+1)*8` bytes, nhưng Java array thực còn **header, length, alignment** và có thể phải cấp phát thêm trong quá trình xây. Không được coi chính xác payload là “đỉnh RAM của chương trình”.

### 7.1. `Runtime.totalMemory()-freeMemory()` đo gì?

Trong Java:

~~~java
Runtime runtime = Runtime.getRuntime();
long usedHeapEstimate =
    runtime.totalMemory() - runtime.freeMemory();
~~~

Đây là một **ước lượng snapshot của heap đang sử dụng** theo báo cáo JVM. Nó **không** phải:
- Số byte object một đoạn code vừa allocate;
- **Đỉnh heap** trong suốt một thao tác;
- Native/off-heap memory của direct buffers;
- Thread stacks, JIT code cache hay toàn bộ process RSS;
- Bảo đảm chính xác byte retained sau một lần build;
- Thước đo ổn định khi GC diễn ra giữa hai lần gọi.

Chênh lệch `usedHeapAfter−usedHeapBefore` **có thể âm** nếu GC thu gom đối tượng giữa hai snapshot. Không nên kết luận “thuật toán trả lại RAM” từ một delta âm. Không dùng `System.gc()` như một lệnh “bắt buộc dọn sạch và đo chính xác”: đó chỉ là lời đề nghị tới JVM và có thể làm thay đổi hành vi benchmark.

**Công cụ đúng mục tiêu:** Memory profiler/heap dump khi cần retained objects; JFR để quan sát allocation/GC và sự kiện runtime; JMH GC profiler khi đo microbenchmark allocations; Native Memory Tracking và công cụ OS để phân tích vùng ngoài heap hoặc process footprint (nếu môi trường hỗ trợ). Phải hiểu phạm vi số đo mỗi công cụ.

### 7.2. Ví dụ payload chính xác nhưng không phải footprint

Chương trình cuối bài dùng:
- `int[20000] data`: \(20.000\times4=80.000\) payload bytes.
- `int[10000] left`: \(10.000\times4=40.000\) bytes.
- `int[10000] right`: thêm 40.000 bytes.
- `long[20001] prefix`: \(20.001\times8=160.008\) bytes.

Tổng **primitive-array payload**:

\[
80.000+40.000+40.000+160.008
=\boxed{320.008\ \text{bytes}}.
\]

Đây là **lower bound theo element payload** cho bốn mảng này, **không** phải tổng RAM của tiến trình và không phải peak heap. `Workload` object, headers/alignment và mã runtime chưa được tính.

### 7.3. Tiền xử lý có thể cần đỉnh bộ nhớ lớn hơn đầu ra

Ví dụ sort out-of-place tạo một array mới; build adjacency từ edge list có thể tạm giữ cả edge list và adjacency; build trie/index có thể tạo nhiều node rồi bỏ các bản trung gian. Dù kết quả cuối nhỏ, trong giai đoạn build có thể cả input, copy, temporary buffers, hash table và index tồn tại đồng thời.

Nếu hệ thống có giới hạn RAM, cần đo **peak trong toàn pipeline**, không chỉ “đầu chương trình” và “cuối chương trình”. Đặt `-Xmx` là một giới hạn **Java heap**, không phải giới hạn RSS tổng tiến trình.

## 8. Độ phức tạp không phải con số benchmark

Big-O mô tả tốc độ tăng tiệm cận theo kích thước input; nó **không** dự đoán trực tiếp một con số nanosecond. Hai thuật toán O(n) có thể khác hằng số hàng chục lần vì locality, allocation, branch prediction hoặc vectorization. Một thuật toán O(n log n) có thể thắng O(n²) ở n đủ lớn nhưng thua ở n rất nhỏ.

**Khi trình bày kết quả, nên có hai bảng riêng:**

| Phần lý thuyết | Quét trực tiếp | Prefix sum |
| --- | --- | --- |
| Chuẩn bị mảng/truy vấn | O(n+q) trong demo | O(n+q) giống nhau |
| Xây cấu trúc bổ sung | Không có | O(n) |
| Một query `[l,r)` | O(r−l) | O(1) |
| q query | O(tổng độ dài các đoạn) | O(q) sau khi build |
| Bộ nhớ bổ sung cho cấu trúc | O(1) | O(n) |
| Khi data update | Đọc trực tiếp data mới | Phải rebuild hoặc dùng cấu trúc động khác |

Bảng runtime đo thực cần ghi **machine/JDK**, `N`, `Q`, phân phối độ dài query, `warmup`, `trials`, số repetitions, phạm vi từng metric, kết quả ở đơn vị rõ. Không chép lại cột complexity rồi gọi đó là đo thực.

### 8.1. Không so hai bài toán khác nhau

Nếu A đếm cả parse input còn B nhận sẵn mảng đã xử lý, kết luận “B nhanh hơn A” không công bằng. Nếu A tính đúng cho mọi input còn B giả định input sorted/unique nhưng không validate, cũng không cùng contract.

Benchmark nên dùng **cùng tập queries, cùng expected answers**, kiểm bằng oracle trước khi đo. Đối với randomness, **cố định seed** cho khả năng tái hiện, đồng thời dùng **nhiều seed/phân phối** khi muốn đánh giá khái quát.

## 9. Đo query-only và end-to-end trong cùng chương trình

Ta sẽ đo hai pipeline cho **mảng bất biến trong cả batch**:
- **Scan-only**: tạo data/query, không build index, trực tiếp quét.
- **Prefix-based**: tạo đúng data/query đó, build prefix, trả cùng queries.

Chương trình dùng `n=20000`, `q=10000`, độ dài đoạn tối đa 512. Data tại i bằng `(i*17+3)%101−50`, và hai endpoint mỗi query sinh bởi một LCG 32-bit có seed **2026**. Tập query giống hệt ở tất cả trial, nên không có tình huống phương án này nhận range dài hơn phương án kia.

**Dữ kiện toán học của workload:**

| Đại lượng | Giá trị kiểm độc lập |
| --- | ---: |
| n | 20.000 |
| q | 10.000 |
| maxLen | 512 |
| Tổng giá trị trong data | −77 |
| Tổng số phần tử được quét trên tất cả query | 2.538.192 |
| Độ dài đoạn trung bình | 253,8192 |
| Checksum có trọng số mỗi query | 36.641.646 |
| Payload 4 mảng primitive | 320.008 byte |

**Checksum** tính:

\[
H=\sum_{j=0}^{q-1}(j+1)\,
\operatorname{rangeSum}(l_j,r_j).
\]

Dùng trọng số `(j+1)` làm kết quả nhạy hơn với thứ tự query so với tổng đơn giản. Nó **không** phải hash mật mã; hai chương trình còn kiểm **từng query**, không chỉ checksum, để tránh kết luận nhầm vì va chạm checksum.

### 9.1. Các pha đo cụ thể

- `prep_once_ns`: thời gian sinh mảng data và hai mảng endpoint **một lần**.
- `prefix_build_once_ns`: thời gian xây prefix **một lần**, không bao gồm prep.
- `query_only`: đo trên workload và prefix **đã tạo**, warm-up rồi chạy nhiều lần, báo median/p95.
- `full_pipeline_scan`: **mỗi trial** tạo workload mới rồi trả q query bằng quét.
- `full_pipeline_prefix`: **mỗi trial** tạo workload mới, build prefix rồi trả q query bằng index.

Trong end-to-end demo, ta chưa có file I/O hoặc serialization output, nên **end-to-end ở đây nghĩa là toàn pipeline tính toán từ generator tới checksum**, không phải end-to-end của hệ thống đọc file và gửi network thật. Scope này được công bố rõ để không gây hiểu nhầm.

`query_only` có ý nghĩa khi index có thể được tái sử dụng. `full_pipeline_*` cho biết trade-off khi phải tự tạo dữ liệu và index từ đầu mỗi lần. **Không cộng các median của từng pha để suy ra median total**; dùng phép đo full pipeline riêng.

### 9.2. Mã Java 17 hoàn chỉnh

Lưu toàn bộ code dưới đây trong **BenchmarkPreparationDemo.java**. Mọi stdout đều là giá trị xác định từ workload và phép kiểm; các **con số thời gian/heap đo thực xuất ra stderr** vì không thể biết trước.

~~~java
import java.util.Arrays;
import java.util.Locale;

public class BenchmarkPreparationDemo {
    static final int N = 20_000;
    static final int Q = 10_000;
    static final int MAX_LEN = 512;
    static final int WARMUPS = 3;
    static final int TRIALS = 7;
    static final int REPEATS = 8;

    // Lam ket qua benchmark co the quan sat tu ben ngoai.
    static volatile long blackhole;

    static final class Workload {
        final int[] data;
        final int[] left;
        final int[] right;

        Workload(int[] data, int[] left, int[] right) {
            this.data = data;
            this.left = left;
            this.right = right;
        }
    }

    static Workload generate() {
        int[] data = new int[N];
        int[] left = new int[Q];
        int[] right = new int[Q];

        for (int i = 0; i < N; i++)
            data[i] = (i * 17 + 3) % 101 - 50;

        // LCG voi arithmetic modulo 2^32 (mask explicit).
        long state = 2026L;
        for (int i = 0; i < Q; i++) {
            state = (state * 1_664_525L
                + 1_013_904_223L) & 0xffff_ffffL;
            int from = (int) (state % N);

            state = (state * 1_664_525L
                + 1_013_904_223L) & 0xffff_ffffL;
            int width = 1 + (int) (state % MAX_LEN);

            left[i] = from;
            right[i] = Math.min(N, from + width);
        }
        return new Workload(data, left, right);
    }

    static void checkRange(int n, int l, int r) {
        if (l < 0 || l > r || r > n)
            throw new IllegalArgumentException(
                "Invalid half-open interval");
    }

    static long rangeScan(int[] data, int l, int r) {
        checkRange(data.length, l, r);
        long result = 0L;
        for (int i = l; i < r; i++)
            result += data[i];
        return result;
    }

    static long[] buildPrefix(int[] data) {
        long[] pref = new long[data.length + 1];
        for (int i = 0; i < data.length; i++)
            pref[i + 1] = Math.addExact(pref[i], data[i]);
        return pref;
    }

    static long rangePrefix(long[] pref, int l, int r) {
        checkRange(pref.length - 1, l, r);
        return Math.subtractExact(pref[r], pref[l]);
    }

    static long scanAll(Workload w) {
        long checksum = 0L;
        for (int i = 0; i < w.left.length; i++) {
            long sum = rangeScan(
                w.data, w.left[i], w.right[i]);
            checksum = Math.addExact(
                checksum, Math.multiplyExact(sum, i + 1L));
        }
        return checksum;
    }

    static long prefixAll(Workload w, long[] pref) {
        long checksum = 0L;
        for (int i = 0; i < w.left.length; i++) {
            long sum = rangePrefix(
                pref, w.left[i], w.right[i]);
            checksum = Math.addExact(
                checksum, Math.multiplyExact(sum, i + 1L));
        }
        return checksum;
    }

    static int verifyEveryRange(Workload w, long[] pref) {
        for (int i = 0; i < w.left.length; i++) {
            long expected = rangeScan(
                w.data, w.left[i], w.right[i]);
            long actual = rangePrefix(
                pref, w.left[i], w.right[i]);
            if (expected != actual)
                throw new AssertionError(
                    "Query mismatch at " + i);
        }
        return w.left.length;
    }

    static long sumData(int[] data) {
        long total = 0L;
        for (int x : data) total += x;
        return total;
    }

    static long sumWidths(Workload w) {
        long total = 0L;
        for (int i = 0; i < w.left.length; i++)
            total += w.right[i] - w.left[i];
        return total;
    }

    static long usedHeapEstimate() {
        Runtime rt = Runtime.getRuntime();
        return rt.totalMemory() - rt.freeMemory();
    }

    // Nearest-rank p95; voi 7 trial no gan nhu max.
    static long percentile95(long[] values) {
        long[] copy = values.clone();
        Arrays.sort(copy);
        int rank = (int) Math.ceil(0.95 * copy.length);
        return copy[Math.max(0, rank - 1)];
    }

    static long median(long[] values) {
        long[] copy = values.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2]; // TRIALS=7 (odd).
    }

    static long queryTrial(
            Workload w, long[] pref, boolean indexed,
            long expected) {
        long start = System.nanoTime();
        long combined = 0L;
        for (int r = 0; r < REPEATS; r++) {
            long value = indexed
                ? prefixAll(w, pref) : scanAll(w);
            if (value != expected)
                throw new AssertionError("Timed query mismatch");
            combined = Math.addExact(combined, value);
        }
        long elapsed = System.nanoTime() - start;
        blackhole = combined;
        return elapsed;
    }

    // Moi full pipeline sinh workload moi, cung seed/cung data.
    static long fullPipelineTrial(
            boolean indexed, long expected) {
        long start = System.nanoTime();
        Workload w = generate();
        long value = indexed
            ? prefixAll(w, buildPrefix(w.data))
            : scanAll(w);
        if (value != expected)
            throw new AssertionError(
                "Full pipeline produced wrong answer");
        long elapsed = System.nanoTime() - start;
        blackhole = value;
        return elapsed;
    }

    static void edgeCases() {
        int[][] inputs = {
            {}, {0}, {-5, -1, -3}, {2, -1, 4, 3}
        };
        for (int[] data : inputs) {
            long[] pref = buildPrefix(data);
            for (int l = 0; l <= data.length; l++) {
                for (int r = l; r <= data.length; r++) {
                    if (rangeScan(data, l, r)
                        != rangePrefix(pref, l, r))
                        throw new AssertionError(
                            "Edge-case range mismatch");
                }
            }
        }

        boolean scanRejected = false;
        boolean prefixRejected = false;
        try {
            rangeScan(new int[]{1}, 1, 0);
        } catch (IllegalArgumentException expected) {
            scanRejected = true;
        }
        try {
            rangePrefix(new long[]{0L, 1L}, -1, 1);
        } catch (IllegalArgumentException expected) {
            prefixRejected = true;
        }
        if (!scanRejected || !prefixRejected)
            throw new AssertionError("Invalid range accepted");
    }

    public static void main(String[] args) {
        // A. PREPARATION (one cold observation).
        long prepStart = System.nanoTime();
        Workload w = generate();
        long prepNs = System.nanoTime() - prepStart;

        int[] originalData = w.data.clone();
        int[] originalLeft = w.left.clone();
        int[] originalRight = w.right.clone();

        // B. INDEX BUILD (one cold observation).
        long heapBeforeBuild = usedHeapEstimate();
        long buildStart = System.nanoTime();
        long[] pref = buildPrefix(w.data);
        long buildNs = System.nanoTime() - buildStart;
        long heapAfterBuild = usedHeapEstimate();

        // C. CORRECTNESS, not inside timed hot loop.
        int checked = verifyEveryRange(w, pref);
        long scan = scanAll(w);
        long indexed = prefixAll(w, pref);
        if (scan != indexed)
            throw new AssertionError("Checksum mismatch");
        edgeCases();

        boolean inputUnchanged =
            Arrays.equals(originalData, w.data)
            && Arrays.equals(originalLeft, w.left)
            && Arrays.equals(originalRight, w.right);
        if (!inputUnchanged)
            throw new AssertionError("Input was mutated");

        long payloadBytes = N * (long) Integer.BYTES
            + 2L * Q * Integer.BYTES
            + (N + 1L) * Long.BYTES;

        System.out.println(
            "n=20000, queries=10000, maxLen=512");
        System.out.println("dataSum=" + sumData(w.data));
        System.out.println("queriedElements=" + sumWidths(w));
        System.out.println("scanChecksum=" + scan);
        System.out.println("prefixChecksum=" + indexed);
        System.out.println("rangeChecks=" + checked);
        System.out.println("edgeCases=PASS");
        System.out.println(
            "inputArraysUnchanged=" + inputUnchanged);
        System.out.println(
            "primitivePayloadBytes=" + payloadBytes);

        // D. WARM-UP: ca query-only va end-to-end.
        for (int i = 0; i < WARMUPS; i++) {
            if (scanAll(w) != scan
                || prefixAll(w, pref) != indexed)
                throw new AssertionError("Warmup changed answer");
            fullPipelineTrial(false, scan);
            fullPipelineTrial(true, scan);
        }

        // E. QUERY-ONLY: data + prefix da duoc tao.
        long[] scanQueryNs = new long[TRIALS];
        long[] prefixQueryNs = new long[TRIALS];

        // F. END-TO-END: generate again for EACH trial.
        long[] scanFullNs = new long[TRIALS];
        long[] prefixFullNs = new long[TRIALS];

        for (int trial = 0; trial < TRIALS; trial++) {
            // Dao thu tu de giam bias vi cache/nhiet/JIT.
            if (trial % 2 == 0) {
                scanQueryNs[trial] =
                    queryTrial(w, pref, false, scan);
                prefixQueryNs[trial] =
                    queryTrial(w, pref, true, scan);
                scanFullNs[trial] =
                    fullPipelineTrial(false, scan);
                prefixFullNs[trial] =
                    fullPipelineTrial(true, scan);
            } else {
                prefixQueryNs[trial] =
                    queryTrial(w, pref, true, scan);
                scanQueryNs[trial] =
                    queryTrial(w, pref, false, scan);
                prefixFullNs[trial] =
                    fullPipelineTrial(true, scan);
                scanFullNs[trial] =
                    fullPipelineTrial(false, scan);
            }
        }

        System.out.println(
            "benchmarkConfig=warmups=3,trials=7,repeats=8");
        System.out.println("fullPipelineChecks=PASS");
        System.out.println(
            "variableMeasurements=stderr");
        System.out.println("verification=PASS");

        // So do qua thuc te KHONG co stdout co dinh.
        System.err.printf(Locale.ROOT,
            "observed_ns_once prep=%d prefixBuild=%d%n",
            prepNs, buildNs);
        System.err.printf(Locale.ROOT,
            "observed_query_ns p50_scan=%d p50_prefix=%d "
            + "p95_scan=%d p95_prefix=%d%n",
            median(scanQueryNs), median(prefixQueryNs),
            percentile95(scanQueryNs),
            percentile95(prefixQueryNs));
        System.err.printf(Locale.ROOT,
            "observed_full_ns p50_scan=%d p50_prefix=%d "
            + "p95_scan=%d p95_prefix=%d%n",
            median(scanFullNs), median(prefixFullNs),
            percentile95(scanFullNs),
            percentile95(prefixFullNs));
        System.err.printf(Locale.ROOT,
            "observed_heap_used_bytes beforeBuild=%d "
            + "afterBuild=%d delta=%d%n",
            heapBeforeBuild, heapAfterBuild,
            heapAfterBuild - heapBeforeBuild);
    }
}
~~~

### 9.3. Biên dịch và chạy

~~~bash
javac BenchmarkPreparationDemo.java
java BenchmarkPreparationDemo
~~~

Có thể chạy với giới hạn heap Java cố định nếu muốn nghiên cứu ảnh hưởng kích cỡ heap:

~~~bash
java -Xms256m -Xmx256m BenchmarkPreparationDemo
~~~

Nhưng phải công bố các JVM flags đã dùng, không thay đổi giữa hai thuật toán mà vẫn gọi là phép so công bằng. `-Xmx256m` là giới hạn Java heap, **không** đồng nghĩa tổng bộ nhớ process chỉ tối đa 256 MB.

### 9.4. Stdout chính xác theo dữ liệu và oracle

**Stdout** của Java demo được thiết kế là các giá trị xác định:

~~~text
n=20000, queries=10000, maxLen=512
dataSum=-77
queriedElements=2538192
scanChecksum=36641646
prefixChecksum=36641646
rangeChecks=10000
edgeCases=PASS
inputArraysUnchanged=true
primitivePayloadBytes=320008
benchmarkConfig=warmups=3,trials=7,repeats=8
fullPipelineChecks=PASS
variableMeasurements=stderr
verification=PASS
~~~

**Stderr** có bốn dòng nhóm số đo `observed_ns_once`, `observed_query_ns`, `observed_full_ns`, `observed_heap_used_bytes`. Các giá trị thay đổi theo JDK/CPU/GC/hệ điều hành, nên không có một con số mẫu nào có thể được coi là **stdout đo thời gian chuẩn**. Khi mở terminal, stdout và stderr có thể xen kẽ tùy buffering; đây không phải đổi thứ tự của các phép tính.

### 9.5. Vì sao ví dụ này kiểm chứng được mà không bịa số đo?

- Data do công thức xác định sinh ra; queries dùng seed LCG và mask modulo 2³² rõ ràng.
- Mỗi truy vấn được tính bằng **quét thật trên array** và bằng **hiệu hai số prefix**, sau đó so **từng kết quả**.
- Tổng 10.000 query quét đúng 2.538.192 phần tử; giá trị input sum là −77.
- Checksum có trọng số của hai thuật toán đều là 36.641.646; đây là số học **xác định**, không phụ thuộc tốc độ máy.
- Các mảng input được clone để so lại bằng `Arrays.equals`, đảm bảo hai thuật toán không vô tình sửa workload.
- `edgeCases()` kiểm mảng rỗng, một phần tử, toàn âm, dữ liệu hỗn hợp, đoạn rỗng và hai đoạn invalid.
- Query-only chạy trên **cùng data và prefix đã build**. Full pipeline tạo lại dataset xác định cho mỗi trial; không để một thuật toán dùng input đã bị phương án khác biến đổi.
- Các phép đo ghi ra stderr đều có nhãn **observed**, không được dùng để khẳng định thời gian tuyệt đối ở máy người khác.

Trong lúc biên soạn, công thức và mọi query đã được đối chiếu bằng một mô hình JavaScript độc lập; mã Java 17 được rà soát tĩnh. Không tuyên bố đã biên dịch/chạy Java bằng `javac` trên máy người dùng.

## 10. Tại sao chỉ đo phần query có thể làm đổi kết luận?

Giả sử thời gian đo trên một môi trường giả định:

| Hạng mục | Quét trực tiếp | Prefix |
| --- | ---: | ---: |
| Chuẩn bị chung | 5 ms | 5 ms |
| Build cấu trúc | 0 ms | 8 ms |
| 1.000 query | 4 ms | 0,2 ms |
| End-to-end không output | 9 ms | 13,2 ms |
| 100.000 query, nếu phân phối không đổi | khoảng 400 ms | khoảng 20 ms + 8 ms build |

**Đây là con số minh họa được giả định**, không phải kết quả đo từ Java demo. Nó chỉ cho thấy:
- Với ít query, thời gian build prefix có thể **lớn hơn** phần query tiết kiệm được.
- Với nhiều query trên **cùng input snapshot**, chi phí build được **amortized** qua nhiều query.
- Nếu mỗi request xây index lại, advantage query-only dễ bị hiểu sai.
- Nếu input cập nhật nhiều lần, cần tính lại chi phí bảo trì index.

Đối với ứng dụng thực, cần đo cả **latency một request**, **throughput nhiều request**, và **batch build + query** theo tỷ lệ cập nhật thực; không chỉ dựa một trục Q.

### 10.1. Amortized cost theo vòng đời dữ liệu

Nếu một index mất B để build, được tái sử dụng cho q query, thì chi phí build bình quân trên một query là B/q. Tổng chi phí bình quân:

\[
\frac{B+qf}{q}=\frac{B}{q}+f.
\]

Đây là **amortized time** theo giả thiết đã build một lần rồi dùng lại. Nếu input thay đổi làm phải build lại sau mỗi m query, chi phí build bình quân thực gần B/m thay vì B/q. Đừng lấy q là tổng query của cả ứng dụng nếu index không tồn tại qua toàn bộ chúng.

Với bài toán thực hiện **một lần duy nhất**, đo end-to-end gần với người dùng hơn. Với hệ thống có cache/index dùng lại hàng triệu lần, query-only và throughput query quan trọng hơn, nhưng chi phí build lúc startup hoặc sau update vẫn cần báo riêng.

## 11. Đo bộ nhớ trước, trong và sau preprocessing

Khi xây cấu trúc, có thể tạo tạm nhiều array/map/node hơn lượng còn lại khi kết thúc. Một phép đo đầu-cuối có thể không quan sát được **peak** trong giữa.

**Các chỉ tiêu nên tách riêng:**
- **Input retained:** memory của dữ liệu đầu vào phải giữ lâu.
- **Index retained:** memory cấu trúc phụ sau build, ví dụ `long[n+1]`.
- **Temporary allocation:** tổng cấp phát để tạo index, có thể rất lớn.
- **Peak live set:** lượng object cần sống cùng lúc, quan trọng khi giới hạn heap.
- **Peak RSS:** resident memory toàn process, gồm vùng ngoài Java heap.
- **Allocation rate:** byte/s hoặc byte/operation, dự báo áp lực GC.

Nếu bảng benchmark chỉ có `usedHeapAfter−usedHeapBefore`, chưa đủ để kết luận mảng prefix thật “cấp phát đúng từng ấy byte”. Chênh lệch có thể bị GC, class loading, compilation và những allocation khác chi phối.

### 11.1. Cách dùng profiler hợp lý

- **JFR (Java Flight Recorder):** quan sát allocations, GC pauses, thread activity, hotspot theo sự kiện runtime khi cấu hình phù hợp.
- **Heap dump / memory profiler:** tìm object còn giữ, retained sizes và đường tham chiếu.
- **JMH GC profiler:** hữu ích cho allocation/operation trong microbenchmark; phải hiểu profiler thu thập metric nào.
- **OS process tools:** RSS/working set/peak ở cấp tiến trình, không nhầm với heap.
- **Native Memory Tracking khi có hỗ trợ:** xem một số phần bộ nhớ native mà JVM theo dõi, không phải mọi byte toàn hệ thống.

Nếu mục tiêu là **giới hạn 128 MB trong online judge**, nên test toàn pipeline với input tối đa, đo đỉnh nhớ thực tế dưới memory limit và có dư địa cho runtime/JVM; không chỉ tính byte của một mảng.

## 12. Những sai lầm làm benchmark trông “quá đẹp”

### 12.1. Khởi tạo dữ liệu trong vùng đo của chỉ một thuật toán

~~~java
long a = System.nanoTime();
int[] data = generate();
algorithmA(data);
long elapsedA = System.nanoTime() - a;

int[] dataB = alreadyPrepared;
long b = System.nanoTime();
algorithmB(dataB);
long elapsedB = System.nanoTime() - b;
~~~

Đây là **so hai phạm vi khác nhau**. Muốn so query-only, chuẩn bị chung trước cả A/B. Muốn so end-to-end, cả hai phải nhận input thô tương đương và chịu cùng loại chi phí chuẩn bị.

### 12.2. Cho thuật toán này input đã được thuật toán kia sửa

Nếu A sort array in-place rồi B query array đã sort, B có thể được “miễn phí” preprocessing hoặc thậm chí nhận **bài toán khác**. Mỗi trial cần data snapshot tương đương, kiểm input ownership, clone/regen khi cần.

### 12.3. Không dùng kết quả tính toán

Nếu result bị bỏ qua, JIT có thể loại bỏ/tối giản công việc. Dùng checksum, kiểm correctness, blackhole. Đừng xem `volatile` đơn lẻ là một phép màu; vẫn cần phương pháp benchmark chuẩn.

### 12.4. In/log hoặc allocate vô tình bên trong vòng đo

`System.out.println`, format string, tạo random mới, clone array hay dựng `List` trong một phương án nhưng không trong phương án kia sẽ làm phép đo chủ yếu phản ánh logging/allocation. Nếu việc đó là phần **contract người dùng** thì đưa vào end-to-end; nếu đang đo kernel, tách nó ra.

### 12.5. Chỉ chạy một lần, chỉ xem thời gian nhỏ nhất

Giá trị min có thể phản ánh một trial may mắn, không đại diện cho phân phối latency. Median giúp giảm nhạy outlier nhưng không thay confidence interval. P95 với bảy samples không đáng tin cho production SLO.

### 12.6. Đo nhầm độ phân giải đồng hồ với độ chính xác

`nanoTime` trả đơn vị ns nhưng hệ thống có timer resolution và jitter; con số `17 ns` không có nghĩa phép đo đúng ±1 ns. Hãy gom đủ phép toán trong một batch hoặc dùng JMH.

### 12.7. Đọc `Runtime.freeMemory()` như RSS

Heap đang dùng, heap committed và process RSS là các metric khác. Heap có thể giảm sau GC còn process RSS không giảm tương ứng; điều đó không phải memory leak tự động.

### 12.8. Dùng `System.gc()` làm chuẩn hóa bộ nhớ

`System.gc()` không bảo đảm đã dọn hết object ngay lập tức. Gọi GC trước từng trial có thể làm benchmark đo chính hiệu ứng GC thay vì chi phí thuật toán. Để biết allocation/retained, dùng profiler hoặc phương pháp đã chuẩn hóa.

### 12.9. Kiểm bằng checksum duy nhất

Hai chuỗi output khác nhau có thể vô tình cho cùng tổng hoặc checksum; cần so từng query trên input nhỏ với oracle, như ví dụ Java đã làm. Với thuật toán phức tạp, nên thêm randomized differential test và property-based assertions.

### 12.10. Nhầm throughput và latency

Bổ sung thread có thể tăng throughput nhưng làm **tail latency** xấu vì queue/GC/lock. Một số đo tổng thời gian batch không tự mô tả P95 của request riêng. Phân biệt `operations/sec`, `latency/op`, `wall time toàn batch` và `CPU seconds`.

## 13. Tính công bằng khi benchmark đa luồng

Với nhiều worker, cần xác định:
- **Thời điểm bắt đầu**: lúc submit toàn bộ task hay lúc mỗi worker bắt đầu thực sự?
- **Thời điểm kết thúc**: khi submit xong, hay khi Future/CountDownLatch của **tất cả task** đã hoàn tất?
- **Warm-up thread pool**: tạo worker có overhead startup, phải tách startup khỏi steady-state nếu đo lâu dài.
- **Số CPU core thực dụng**: P thread không có nghĩa có P core rảnh và băng thông vô hạn.
- **Synchronization**: khóa/queue/atomic có thể chi phối runtime.
- **Fair scheduling**: một worker bận nền làm tail dài dù thuật toán đúng.
- **Đường găng**: tổng CPU work cao nhưng DAG dependencies làm wall-clock không thể giảm dưới span.

**Sai lầm điển hình:**

~~~java
long start = System.nanoTime();
for (Runnable task : tasks)
    executor.submit(task);
long elapsed = System.nanoTime() - start;
// elapsed chi la THOI GIAN SUBMIT, KHONG phai makespan.
~~~

Muốn wall-time toàn batch, phải chờ **tất cả Future** hoặc synchronization primitive phù hợp:

~~~java
long start = System.nanoTime();
List<Future<?>> futures = new ArrayList<>();
for (Runnable task : tasks)
    futures.add(executor.submit(task));
for (Future<?> f : futures)
    f.get(); // cho moi task hoan tat (hoac nem loi)
long elapsed = System.nanoTime() - start;
~~~

Đây là **mã minh họa**, không phải một chương trình đầy đủ độc lập. Đừng quên shutdown executor phù hợp, xử lý exception và input không bị sửa đồng thời. Nếu muốn đo riêng phần kernel worker, có thể đồng bộ start bằng barrier và vẫn phải công bố phạm vi.

## 14. Đo thời gian khi có chuẩn bị bằng I/O

Với dữ liệu đọc từ file/database/network, thời gian chuẩn bị có thể lấn át phần thuật toán:

~~~text
file -> parse -> validate -> build index -> query -> serialize
 35ms    20ms      5ms         15ms      2ms      10ms
~~~

Các số này chỉ minh họa. Nếu mục tiêu là xử lý một file duy nhất, end-to-end gồm 87 ms, không nên chỉ báo “query mất 2 ms” rồi xem đó là thời gian hoàn thành bài toán.

Nhưng nếu cùng index được phục vụ hàng triệu queries sau khi build, người dùng quan tâm cả **2 ms mỗi query** và **75 ms startup chuẩn bị/build trước khi phục vụ**, tùy workload.

**Phân biệt caching:** file có thể nằm trong OS page cache từ trial thứ hai; database có buffer pool; mạng có connection reuse; JVM có JIT/loaded classes. Cần công bố đo **cold-start** hay **warm-cache** và cách tạo điều kiện lặp lại. Không tuyên bố “đọc disk 1 ms” nếu toàn bộ file đã được OS cache sẵn.

**Tách parse và algorithm:** nếu A và B dùng chung format, có thể parse một lần rồi so kernel để nghiên cứu algorithmic difference. Nhưng báo cáo end-to-end phải cộng vào hoặc đo pipeline đầy đủ khi ứng dụng thực cần parse.

## 15. Thiết kế báo cáo benchmark đúng

Một báo cáo có thể tái hiện nên bao gồm các trường:

| Hạng mục | Nội dung nên ghi |
| --- | --- |
| Bài toán và correctness | Loại query, oracle, kết quả kiểm tính đúng |
| Input size | n, q, số cạnh, độ dài dữ liệu, phân phối kích thước |
| Input generation | Seed, công thức, nguồn dữ liệu, cold/warm cache |
| Máy/JVM | CPU, RAM, OS, JDK version, flags, GC |
| Đơn vị | ns, µs, ms, bytes, MiB, ops/s |
| Pha đo | prep, build, query-only, end-to-end, output |
| Warm-up/trials | Số warmups, samples, số repetitions, forks |
| Thống kê | Raw samples, median/p50, p95 nếu đủ dữ liệu, độ biến thiên |
| Bộ nhớ | Payload, allocation, retained heap, peak/RSS, đo bằng công cụ nào |
| Correctness | Per-query equality, input mutation, edge cases, overflow |
| Giới hạn | Chỗ dùng input giả, single-thread, thiếu I/O, noisy GC |
| Kết luận | Với workload nào A/B tốt, điều kiện đổi chiều kết luận |

**Ví dụ diễn giải đúng:**

> “Với 20.000 phần tử và 10.000 truy vấn có độ dài trung bình khoảng 254, xét mô hình query-only trên dữ liệu đã chuẩn bị, prefix sum có O(1) mỗi query trong khi quét cần duyệt tổng 2.538.192 phần tử. Thời gian thực của hai pipeline sẽ được đo tách riêng ở stderr khi chạy trên máy mục tiêu; chưa có con số tốc độ tuyệt đối nào được suy từ Big-O.”

**Ví dụ diễn giải thiếu cơ sở:** “Prefix sum luôn nhanh hơn quét 100 lần và chỉ dùng 160.008 byte RAM”. Số 160.008 chỉ là payload của riêng mảng prefix ở n=20.000; không tính input, endpoints hay overhead Java.

## 16. Chẩn đoán kết quả bất thường

**A nhanh hơn ở lần đầu, chậm hơn ở lần thứ 20.** Xem JIT/warm-up, cache, GC, thermal và test order; không vội thay code.

**Mỗi query chỉ mất 0 ns hoặc vài ns phi lý.** Kiểm dead-code elimination, constant folding, clock resolution, batch size và việc có thật đang tính query hay không.

**Sau build, usedHeap giảm.** Có thể GC xảy ra giữa hai snapshot. Dùng profiler để theo allocation/retained, không diễn giải delta âm là số byte index “âm”.

**Index thắng query-only nhưng thua full pipeline.** Hoàn toàn có thể đúng: build tốn thời gian được trả một lần. Tính điểm hòa vốn theo q.

**Một input random đạt hiệu năng tốt, input thật rất xấu.** Chi phí của thuật toán có thể phụ thuộc phân phối range lengths, số cạnh, độ phân nhánh, key collisions, độ sâu recursion hoặc dữ liệu bị lệch. Cần benchmark **nhiều shape và adversarial cases**, không chỉ uniform random.

**Tăng worker mà wall-time không giảm.** Kiểm serial fraction, critical path, memory bandwidth, contention, thread count và task granularity; tổng CPU time tăng có thể là overhead.

**RSS tăng mãi dù heap used ổn định.** Có thể do heap committed, native/direct buffers, thread stacks, JIT hoặc allocator. Cần công cụ OS + JVM diagnostics, không kết luận memory leak chỉ từ RSS.

**Benchmark đôi khi fail correctness.** Dừng diễn giải performance cho đến khi xác định race, mutation, overflow hoặc input mismatch; thuật toán sai không được công nhận “nhanh hơn”.

## 17. Checklist trước khi công bố kết quả

1. [ ] Viết rõ **đang đo query-only hay end-to-end**, có tính build/index/copy/parse không.
2. [ ] Xác định input size, distribution và số query/update.
3. [ ] Hai thuật toán nhận cùng một **hợp đồng input/output**.
4. [ ] Sinh data ngoài vùng timed kernel khi đo query-only.
5. [ ] Tính chi phí chuẩn bị riêng; không miễn phí preprocessing cho một phương án nếu so full pipeline.
6. [ ] Nếu dữ liệu mutable, clone/regenerate để không làm ô nhiễm phương án chạy sau.
7. [ ] Kiểm tính đúng bằng oracle độc lập, từng query nếu kích thước cho phép.
8. [ ] Dùng `System.nanoTime()` cho khoảng elapsed trong cùng JVM.
9. [ ] Không suy đơn vị nanosecond thành độ chính xác tuyệt đối nanosecond.
10. [ ] Warm-up cả hai phương án; chạy nhiều trial và cân bằng thứ tự A/B.
11. [ ] Ghi phiên bản JDK, flags, CPU, OS, GC và mức tải nền.
12. [ ] Dùng checksum/blackhole hoặc công cụ JMH để giảm nguy cơ bị tối ưu bỏ công việc.
13. [ ] Tránh logging, format output hoặc allocate ngẫu nhiên trong timed kernel nếu không thuộc scope.
14. [ ] Báo raw samples + median, phân vị cao chỉ khi có đủ sample.
15. [ ] Phân biệt elapsed/wall, CPU time và throughput.
16. [ ] Phân biệt payload arrays, allocation, retained heap, peak heap và RSS.
17. [ ] Không lấy `totalMemory−freeMemory` làm số byte vừa cấp phát.
18. [ ] Không dùng một lần `System.gc()` làm bằng chứng bộ nhớ đã sạch.
19. [ ] Dùng profiler phù hợp nếu câu hỏi là peak memory hoặc allocation.
20. [ ] Tính amortized build cost theo **số query dùng chung một phiên bản index**.
21. [ ] Nếu benchmark đa luồng, chờ **tất cả** task hoàn tất trước khi lấy kết quả.
22. [ ] Đo nhiều kích thước input để nhìn crossover, không chỉ một điểm.
23. [ ] Thử input nhỏ, input sát giới hạn và input lệch phân phối.
24. [ ] Viết rõ giới hạn của demo và không bịa thời gian thực khi chưa chạy trên máy đích.

## 18. Bài tập có đáp án

**Bài 1.** Vì sao không thể chỉ so thời gian một query của prefix sum với quét trực tiếp rồi kết luận phương pháp nào tốt nhất cho toàn bài?

*Đáp án:* Prefix sum tốn O(n) để build. Kết luận full pipeline phụ thuộc q, độ dài các đoạn và vòng đời index.

**Bài 2.** Bốn pha chủ đạo trong bài là gì?

*Đáp án:* Chuẩn bị data, build/preprocess, query/compute và output/end-to-end (end-to-end bao gồm các pha cần thiết).

**Bài 3.** `System.nanoTime()` đo được gì?

*Đáp án:* Dùng để đo elapsed-time interval giữa hai lần gọi; không phải thời gian lịch Unix.

**Bài 4.** Nanosecond unit có đảm bảo clock chính xác đến 1 ns không?

*Đáp án:* Không. Cần xét timer resolution, jitter và quy mô batch.

**Bài 5.** Vì sao nên warm-up Java benchmark?

*Đáp án:* Để giảm ảnh hưởng JIT/class-loading và đưa mã nóng vào trạng thái điển hình hơn.

**Bài 6.** Warm-up một lần có đảm bảo JIT hoàn toàn ổn định không?

*Đáp án:* Không; nên dùng nhiều iterations, forks và công cụ phù hợp khi cần kết luận nghiêm túc.

**Bài 7.** Dead-code elimination ảnh hưởng benchmark ra sao?

*Đáp án:* JVM có thể bỏ phép tính không có kết quả quan sát được; số đo không còn đại diện thuật toán.

**Bài 8.** Vì sao giữ checksum?

*Đáp án:* Để kiểm correctness và buộc output có thể quan sát, giảm nguy cơ loại bỏ toàn bộ tính toán.

**Bài 9.** Checksum bằng nhau đã đủ chứng minh mọi query giống nhau chưa?

*Đáp án:* Không; có thể collision. Demo còn so từng query.

**Bài 10.** Với mảng n=100.000 và một query dài 10, query-only cách nào ít phép cộng hơn?

*Đáp án:* Prefix O(1) ở query nhưng phải có prefix sẵn; nếu tính build từ đầu, quét chỉ 10 phần tử thường hợp lý hơn.

**Bài 11.** Nếu có q query dài trung bình L, tổng phần quét có bậc gì?

*Đáp án:* Khoảng O(qL), chính xác theo tổng độ dài \(\sum_j(r_j-l_j)\).

**Bài 12.** Prefix sum cần bao nhiêu thời gian để build và mỗi query?

*Đáp án:* O(n) build, O(1) mỗi query sau build.

**Bài 13.** Prefix sum cần bao nhiêu bộ nhớ bổ sung?

*Đáp án:* O(n) phần tử, thường n+1 số prefix.

**Bài 14.** Điểm hòa vốn gần đúng khi scan/query s, prefix/query f, build B là gì?

*Đáp án:* Với s>f, khoảng q>B/(s−f).

**Bài 15.** Nếu dữ liệu đổi sau mỗi 10 query, tính amortized build theo q tổng toàn hệ thống có đúng không?

*Đáp án:* Không. Build thực được trả theo mỗi phiên bản dữ liệu, gần B/10 mỗi query trong giả thiết này.

**Bài 16.** Với n=20.000, q=10.000 của demo, payload bốn mảng primitive là bao nhiêu?

*Đáp án:* 320.008 bytes, chưa tính headers/alignment hay VM overhead.

**Bài 17.** Mảng `long[20001]` có payload bao nhiêu?

*Đáp án:* 20.001×8=160.008 bytes.

**Bài 18.** Có thể kết luận peak heap bằng chênh lệch `usedHeapAfter−usedHeapBefore` không?

*Đáp án:* Không. Snapshot không ghi lại đỉnh và GC có thể thay đổi đối tượng sống.

**Bài 19.** Nếu delta heap âm, có nghĩa cấu trúc build “tốn âm bộ nhớ” không?

*Đáp án:* Không. Có thể GC hoặc các biến động heap khác xen giữa.

**Bài 20.** RSS có phải Java heap không?

*Đáp án:* Không. RSS là resident memory cấp tiến trình, có thể chứa heap, stack, JIT/native và vùng khác.

**Bài 21.** Tổng **allocated bytes** và **retained heap** có giống nhau không?

*Đáp án:* Không. Nhiều object được allocate rồi thu gom có thể làm allocated lớn nhưng retained nhỏ.

**Bài 22.** Vì sao nên đảo thứ tự A/B qua các trial?

*Đáp án:* Để giảm thiên lệch do phương án chạy sau hưởng warm-cache/JIT hoặc chịu thermal ảnh hưởng khác.

**Bài 23.** Với 7 samples, nearest-rank p95 có ổn định như p95 production không?

*Đáp án:* Không; nó gần như lấy max của bảy sample và có độ bất định cao.

**Bài 24.** Median của prep đo riêng + median query đo riêng có bắt buộc bằng median full pipeline không?

*Đáp án:* Không. Cần đo full pipeline riêng vì phân phối và tương quan của các pha khác nhau.

**Bài 25.** Data sum và checksum của demo là bao nhiêu?

*Đáp án:* Data sum −77; weighted query checksum 36.641.646 ở cả scan và prefix.

**Bài 26.** Demo quét tổng bao nhiêu phần tử qua 10.000 query?

*Đáp án:* 2.538.192 phần tử.

**Bài 27.** `rangeSum(l,r)` nửa mở với l=r trả bao nhiêu?

*Đáp án:* 0 cho cả scan và prefix.

**Bài 28.** Vì sao demo kiểm mọi query trước khi đo?

*Đáp án:* Để bảo đảm so hai thuật toán trả cùng kết quả, không so độ nhanh của code sai.

**Bài 29.** Nếu chỉ đo thời gian `submit` 10.000 task rồi kết thúc timer, đã đo makespan chưa?

*Đáp án:* Chưa. Phải chờ mọi Future/task hoàn tất.

**Bài 30.** Vì sao in log bên trong timed loop làm benchmark sai lệch?

*Đáp án:* Chi phí I/O/format có thể lấn át tính toán; trừ khi logging là một phần hợp đồng cần đo.

**Bài 31.** Khi nào nên chọn JMH thay một vòng `nanoTime()` đơn giản?

*Đáp án:* Khi đo microbenchmark rất ngắn, cần forks/warm-up/blackhole và kiểm soát optimizer đáng tin hơn.

**Bài 32.** `Runtime.totalMemory()-freeMemory()` có tính direct buffer/native memory không?

*Đáp án:* Không; nó nói về Java heap ước lượng ở một thời điểm.

**Bài 33.** Khi build index cần rất nhiều mảng tạm, metric nào quan trọng để tránh OOM?

*Đáp án:* Peak live heap/peak process memory trong toàn pipeline, không chỉ size index cuối.

**Bài 34.** Nếu B query-only nhanh hơn A nhưng full pipeline B chậm hơn, liệu có mâu thuẫn?

*Đáp án:* Không. Chi phí build/prepare của B có thể lớn hơn phần query tiết kiệm được trong workload đó.

**Bài 35.** Một trial chạy nhanh hơn 1% khi jitter ±10% cho phép kết luận chắc chắn không?

*Đáp án:* Không. Cần nhiều trial, môi trường ổn định và đánh giá độ bất định.

**Bài 36.** Nếu hai phiên bản dùng input random khác nhau, phép đo có công bằng không?

*Đáp án:* Không đủ cơ sở. Cần input/query tương đương hoặc kiểm soát phân phối, seed và workload.

**Bài 37.** CPU time và elapsed time khác nhau như thế nào khi thread bị block I/O?

*Đáp án:* Elapsed tăng trong lúc chờ; CPU time của thread thường không tăng tương ứng.

**Bài 38.** Đặt `-Xmx256m` có bảo đảm RSS tiến trình không vượt 256 MB không?

*Đáp án:* Không. Xmx chỉ giới hạn heap Java, không phải toàn bộ process.

**Bài 39.** Vì sao `System.gc()` không phải cách đo allocation chuẩn?

*Đáp án:* Nó là đề nghị GC, không bảo đảm thời điểm hay số object dọn sạch, đồng thời gây nhiễu benchmark.

**Bài 40.** Cần ghi thêm gì ngoài thời gian median khi công bố kết quả?

*Đáp án:* Bài toán, input/query distribution, scope phases, JDK/máy/flags, warm-up, số samples, correctness, memory metric, phương pháp đo và giới hạn ngoại suy.

## Tổng kết

**Đo thuật toán** cần bắt đầu từ **hợp đồng và phạm vi**, không phải từ một lời gọi timer. Với cùng đầu vào, tách **chuẩn bị**, **xây cấu trúc**, **truy vấn** và **end-to-end** sẽ giải thích vì sao một thuật toán thắng trong query-only nhưng thua khi phải tự xây dữ liệu từ đầu. Khi index được dùng lại nhiều lần, đưa chi phí build vào phân tích **amortized** theo số query trên đúng một phiên bản dữ liệu.

Trong Java, `System.nanoTime()` thích hợp cho elapsed interval nhưng cần warm-up, repeated batches, nhiều trial và tiêu thụ kết quả để chống phép tính bị optimizer loại bỏ. Các số đo nanosecond thực **phụ thuộc máy**; không được bịa stdout benchmark. Đối với bộ nhớ, **payload arrays, allocations, retained heap, peak heap và RSS** là các đại lượng khác nhau; delta của hai lần `totalMemory−freeMemory` không thay thế profiler/peak measurement.

Một báo cáo tin cậy gồm **thuật toán đúng, workload tương đương, công đoạn đo minh bạch, nhiều lần lấy mẫu, kiểm soát JIT/GC và kết luận có điều kiện**. Đây là nền tảng để tối ưu hóa mà không tự đánh lừa mình bằng một con số “nhanh hơn” thiếu phạm vi.
