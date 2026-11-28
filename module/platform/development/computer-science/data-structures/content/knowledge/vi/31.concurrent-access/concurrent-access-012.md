# Giới hạn của đo hiệu năng khi bỏ qua tranh chấp hoặc cấp phát

Một phép đo cho thấy stack dùng CAS mất 25 ns cho mỗi lần `push`, còn stack dùng khóa mất 35 ns. Có thể kết luận stack CAS nhanh hơn trong hệ thống có 16 luồng hay không? **Chưa thể.** Nếu phép đo chỉ chạy một luồng, nó không thể hiện chi phí tranh chấp khi nhiều luồng cùng cập nhật `head`. Nếu bỏ qua việc tạo nút mới và thu hồi nút cũ, kết quả cũng có thể không phản ánh chi phí bộ nhớ thực tế.

Trong chương **Truy cập đồng thời**, cần đánh giá cấu trúc dữ liệu bằng cả **tính đúng đắn**, **bất biến**, **độ phức tạp thời gian/bộ nhớ** và **hành vi khi nhiều luồng dùng chung tài nguyên**. Một phép đo hiệu năng có giá trị khi nó tái hiện được những đặc điểm có ảnh hưởng đến quyết định chọn mảng, danh sách liên kết, stack, queue, bảng băm, cây hoặc phiên bản bất biến của chúng.

Bài học này phân tích vì sao bỏ qua **tranh chấp (contention)** hoặc **cấp phát (allocation)** thường dẫn tới kết luận sai, cách thiết kế phép đo phù hợp và cách đọc kết quả với các giới hạn rõ ràng.

## 1. Benchmark trả lời câu hỏi nào?

**Benchmark** là phép đo hành vi của một chương trình trong những điều kiện nhất định. Một kết quả kiểu “8 triệu thao tác/giây” chỉ có ý nghĩa nếu người đọc biết ít nhất:

- **Thao tác:** `push`, `pop`, `get`, `put`, quét cây hay hỗn hợp nhiều thao tác?
- **Mô hình tải:** một luồng hay nhiều luồng, đọc/ghi theo tỷ lệ nào, thao tác phân bố trên những khóa nào?
- **Kích thước và trạng thái:** cấu trúc đang chứa bao nhiêu phần tử, có thường xuyên rỗng hoặc đầy không?
- **Bộ nhớ:** phép đo có bao gồm tạo nút, sao chép, bộ thu gom rác, thu hồi và giới hạn dung lượng không?
- **Máy và runtime:** CPU, số lõi, NUMA, hệ điều hành, JVM/compiler, cấu hình GC và trạng thái khởi động?
- **Chỉ số kết quả:** throughput, latency trung vị, đuôi phân phối hay lượng bộ nhớ cấp phát?

Chẳng hạn, hai queue cùng cho kết quả đúng theo FIFO nhưng khác nhau về khả năng chặn luồng và chính sách khi queue đầy. So sánh số lần `offer` trên queue không giới hạn với số lần `offer` được chấp nhận trên queue hữu hạn là so sánh **hai lượng công việc khác nhau** nếu không kiểm soát trường hợp queue đầy.

**Không có phép đo duy nhất đại diện cho mọi workload.** Microbenchmark giúp trả lời một câu hỏi hẹp về thao tác; thử nghiệm tích hợp và tải thực tế mới cho thấy tác động của các thao tác lên toàn hệ thống.

## 2. Vì sao một luồng thường che giấu tranh chấp?

Tranh chấp xuất hiện khi nhiều luồng cùng muốn dùng một tài nguyên, chẳng hạn mutex, một ô nhớ nguyên tử, một cache line, bộ cấp phát hoặc hàng đợi dùng chung.

### 2.1. Lock: thời gian chờ nằm ngoài vùng tới hạn

Xét bộ đếm dùng khóa:

```java
public final class LockedCounter {
    private long value;

    public synchronized void increment() {
        value++;
    }

    public synchronized long get() {
        return value;
    }
}
```

Nếu chỉ có một luồng, thời gian mỗi lần `increment` chủ yếu là chi phí vào/ra monitor và tăng biến. Khi nhiều luồng cùng gọi `increment`, chúng phải **tuần tự hóa** trên cùng monitor. Một luồng có thể dành nhiều thời gian **chờ được vào** `increment` dù phần công việc bên trong vẫn rất nhỏ.

Cần phân biệt:

```text
Độ trễ một lời gọi = chờ tài nguyên
                    + xử lý trong vùng tới hạn
                    + các chi phí môi trường khác
```

Đo riêng phần `value++` rồi suy ra độ trễ của lời gọi có tranh chấp sẽ bỏ sót phần chờ có thể lớn hơn rất nhiều.

### 2.2. CAS: không chờ khóa vẫn có retry

Xét bộ đếm nguyên tử:

```java
import java.util.concurrent.atomic.AtomicLong;

public final class CasCounter {
    private final AtomicLong value = new AtomicLong();

    public long increment() {
        while (true) {
            long oldValue = value.get();
            long newValue = oldValue + 1;
            if (value.compareAndSet(oldValue, newValue)) {
                return newValue;
            }
        }
    }
}
```

Với một luồng, CAS thường thành công ngay. Với nhiều luồng cùng đọc `oldValue`, chỉ một luồng có thể công bố thay đổi đầu tiên; các luồng còn lại cần đọc lại giá trị và thử tiếp. Retry tốn thời gian và tạo thêm lưu lượng truy cập bộ nhớ chia sẻ.

CAS không nhất thiết bị hệ điều hành đưa vào trạng thái ngủ như chờ mutex, nhưng các luồng có thể **cạnh tranh cùng cache line**, chuyển quyền sở hữu dòng cache giữa các lõi và lặp CAS thất bại. Vì vậy, **lock-free không đồng nghĩa nhanh hơn**, cũng không cho cận độ trễ riêng cho mỗi lời gọi.

Một kết quả đo một luồng có thể cho thấy CAS nhanh hơn lock, trong khi phép đo 16 luồng lại cho kết quả ngược hoặc cả hai đều kém đi. Đây là hiện tượng bình thường theo tải, **không phải mâu thuẫn** giữa hai phép đo.

### 2.3. Cache coherence và false sharing

Không phải cứ không dùng chung một biến logic là hết tranh chấp bộ nhớ. Hai bộ đếm độc lập có thể nằm trên **cùng cache line**. Nếu các lõi liên tục ghi hai ô đó, giao thức nhất quán cache vẫn có thể buộc cache line chuyển quyền sở hữu qua lại. Hiện tượng này gọi là **false sharing**.

```text
Cùng cache line 64 byte (ví dụ minh họa):

+-------------------------------+
| counterA | counterB | ...     |
+-------------------------------+
    Lõi 1      Lõi 2

Hai biến khác nhau, nhưng mỗi lần ghi có thể làm tranh chấp
quyền sở hữu của cùng một cache line.
```

Kích thước dòng cache phụ thuộc kiến trúc; con số 64 byte chỉ là ví dụ phổ biến. False sharing có thể làm sai kết luận về thuật toán nếu cách bố trí trường dữ liệu tình cờ khác nhau. Khi đánh giá, cần xem mức chia sẻ cache và bố trí bộ nhớ, không chỉ số khóa hoặc CAS.

## 3. Vì sao cấp phát làm thay đổi bức tranh?

Mỗi lần cập nhật một cấu trúc dữ liệu có thể cần tạo phần tử hoặc nút mới. Chi phí này thường bị bỏ sót nếu benchmark:

- Tạo sẵn toàn bộ nút rồi chỉ đo bước đổi con trỏ.
- Đo thao tác trên một đối tượng nhỏ mà bộ biên dịch có thể loại bỏ cấp phát.
- Chạy quá ngắn nên chưa thấy áp lực từ garbage collection (GC) hoặc cơ chế thu hồi.
- Đếm `pop` thành công nhưng không tính lượng bộ nhớ do các `push` trước đó tạo ra.
- Không tính phiên bản cũ còn sống do reader giữ snapshot.

### 3.1. Danh sách liên kết và stack

Một stack liên kết thường có `push` như sau:

```text
newNode = allocate(value, oldHead)
CAS(head, oldHead, newNode)
```

Phần cập nhật `head` về mặt cấu trúc là `O(1)`, nhưng **cấp phát nút** đi cùng từng lần `push`. Nếu CAS thất bại, một số triển khai còn có thể cấp phát lại khi thử tiếp. Khi có GC, chi phí không nhất thiết trả ngay trong lời gọi hiện tại: nó có thể chuyển sang các đợt GC sau đó.

Trong C/C++, nếu dùng bộ cấp phát và thu hồi thủ công, chi phí `malloc/free` hoặc pool cấp phát có thể trở thành điểm tranh chấp. Với thuật toán lock-free, việc **thu hồi an toàn** còn phải giải quyết nguy cơ reader vẫn giữ con trỏ tới nút đã gỡ; hazard pointers, epoch-based reclamation hoặc cơ chế tương đương cũng tiêu tốn thời gian và bộ nhớ.

Một benchmark cố tình chỉ đo CAS có thể hữu ích để tìm chi phí của primitive, nhưng **không đại diện cho `push` hoàn chỉnh** nếu ứng dụng thực tế luôn tạo nút mới.

### 3.2. Ảnh chụp bất biến và copy-on-write

Xét bảng băm lưu cấu hình có `n` phần tử. Phương án tạo bản sao toàn bộ rồi công bố snapshot mới có đặc điểm:

```text
read:   snapshot = current; lookup(snapshot, key)
write:  newMap = copy(current)    // O(n)
        change(newMap, key)
        publish(newMap)
```

Lượt đọc có thể rất nhẹ vì không cần chờ luồng ghi; nếu chỉ benchmark `read`, phương án này có vẻ vượt trội. Nhưng mỗi `write` phải sao chép `O(n)` phần tử và các snapshot cũ có thể được giữ lại khi reader đang sử dụng. Với bảng lớn hoặc nhiều update, **phân bổ bộ nhớ và đỉnh bộ nhớ** có thể chi phối hiệu năng toàn hệ thống.

Ngược lại, cấu trúc bất biến có **chia sẻ cấu trúc** như cây cân bằng hoặc trie có thể chỉ tạo `O(log n)` nút trên đường cập nhật, đổi lại nhiều cấp con trỏ và chi phí truy cập khác. Chọn cấu trúc nào phụ thuộc vào kích thước `n`, tỷ lệ đọc/ghi, thời gian giữ snapshot và bộ nhớ cho phép.

### 3.3. Vòng đời bộ nhớ cũng là một thành phần của hiệu năng

Cần tách ít nhất bốn yếu tố:

| Khía cạnh | Câu hỏi cần đo |
| --- | --- |
| **Allocation rate** | Mỗi giây hoặc mỗi thao tác tạo bao nhiêu byte mới? |
| **Live set / retained memory** | Bao nhiêu byte còn phải giữ vì các luồng hoặc snapshot chưa kết thúc? |
| **Reclamation / GC** | Thu hồi tốn bao nhiêu CPU, tạo bao nhiêu pause hoặc ảnh hưởng độ trễ? |
| **Peak memory** | Ở cao điểm tranh chấp, bao nhiêu nút retired hoặc phiên bản cũ cùng tồn tại? |

**`O(1)` cấp phát không đồng nghĩa chi phí bằng không**. Ngay cả khi mỗi thao tác chỉ tạo một nút nhỏ, hàng triệu thao tác mỗi giây vẫn có thể tạo lượng đối tượng lớn. Đặc biệt, tốc độ cấp phát và tốc độ thu hồi phải được xét cùng nhau: queue không giới hạn có thể đạt throughput `enqueue` tốt trong vài giây nhưng làm bộ nhớ tăng liên tục khi consumer chậm.

## 4. Kết quả có thể đảo chiều theo workload

Giả sử A là một bảng cấu hình dạng snapshot bất biến, B là bảng dùng mutex để bảo vệ dữ liệu có thể thay đổi. Bảng sau là **ví dụ giả định để lập luận**, không phải kết quả đo thực nghiệm:

| Workload | A: immutable snapshot | B: mutable + mutex | Điều phép đo cần giải thích |
| --- | --- | --- | --- |
| 100% đọc, một luồng | Đọc tham chiếu và tra cứu, ít đồng bộ | Có chi phí lấy khóa | A có thể lợi thế |
| 99% đọc, 1% ghi; nhiều luồng | Đọc nhanh; write sao chép phiên bản | Reader và writer tranh chấp khóa | Phải đo cả chi phí write và GC |
| 50% đọc, 50% ghi; bảng rất lớn | Nhiều bản sao lớn, dễ tăng cấp phát | Ghi tại chỗ, nhưng lock contention cao | Ưu/nhược không thể suy ra từ một dòng `get` |
| Reader giữ snapshot lâu | Bản cũ bị giữ lại | Không có snapshot theo cùng cơ chế | A có thể tăng live set/peak memory |

Với stack hoặc queue, cũng không thể chỉ đo trường hợp *không tranh chấp* rồi tuyên bố một cách cài đặt là tối ưu cho mọi mục tiêu. Số luồng, tỷ lệ producer/consumer, kích thước queue, chính sách blocking khi đầy và vòng đời nút đều có thể làm thứ hạng thay đổi.

Bài học phương pháp luận: **thay đổi một tham số tải có thể thay đổi cả điểm nghẽn**, nên một phương án không có “tốc độ duy nhất” độc lập với workload.

## 5. Những chỉ số cần báo cáo

### 5.1. Throughput và latency nói về hai mặt khác nhau

- **Throughput:** số thao tác *hoàn thành* trong một đơn vị thời gian, thường là ops/s.
- **Latency:** thời gian từ khi thao tác được yêu cầu đến khi hoàn thành, nên bao gồm thời gian chờ, retry và những giai đoạn liên quan theo mục tiêu đo.
- **Tail latency:** p95, p99, p99.9; cho biết điều gì xảy ra với nhóm lời gọi chậm nhất, vốn có thể gây mất ổn định ứng dụng.
- **Khả năng mở rộng (scaling):** throughput và latency thay đổi thế nào khi tăng số luồng, không chỉ tại một cấu hình cố định.
- **CPU usage / efficiency:** throughput tăng có cần sử dụng thêm bao nhiêu CPU; vòng lặp CAS thất bại liên tục có thể tốn CPU dù số thao tác hoàn thành ít.
- **Memory:** cấp phát byte/op, số object, lượng bộ nhớ giữ lại, thời gian GC hoặc thu hồi, đỉnh RAM.

Chỉ số `ops/s` có thể đẹp khi chỉ thực hiện nhanh một loại thao tác nhưng phần việc ứng dụng cần lại là toàn bộ chuỗi `enqueue -> xử lý -> dequeue`. Cần xác định **mẫu số** chính xác: số thao tác được gọi, số thao tác thành công hay số yêu cầu nghiệp vụ hoàn tất.

Không thể lấy `1 / throughput` làm latency của một lời gọi khi có nhiều thao tác đồng thời. Với `N` worker chạy song song, số lời gọi hoàn thành trong một giây có thể rất lớn trong khi mỗi lời gọi vẫn phải chờ lâu.

### 5.2. Trung bình che khuất đuôi phân phối

Ví dụ giả định: 990 lời gọi mất 1 ms, 10 lời gọi mất 100 ms. Trung bình xấp xỉ 1,99 ms, nhưng p99 có thể ở gần vùng 100 ms, tùy định nghĩa percentile và cách lấy mẫu. Đối với hệ thống có yêu cầu phản hồi, một số ít lời gọi bị chặn do GC, scheduler hoặc lock có thể quan trọng hơn cải thiện vài nanosecond ở trường hợp phổ biến.

Khi báo cáo p99, cần nêu **số mẫu, cửa sổ thời gian và phân bố tải**; p99 từ vài trăm lời gọi ít có ý nghĩa hơn từ mẫu đủ lớn, ổn định.

### 5.3. Closed-loop và open-loop

Microbenchmark theo kiểu **closed-loop** thường cho mỗi worker gửi thao tác tiếp theo ngay khi thao tác trước hoàn tất. Khi hệ thống chậm đi, tốc độ phát sinh yêu cầu cũng tự giảm. Kiểu đo này phù hợp với throughput bão hòa, nhưng có thể che giấu độ trễ của hệ thống phải nhận lưu lượng từ bên ngoài.

Trong mô hình **open-loop**, yêu cầu đến theo lịch hoặc tốc độ được đặt trước, gần hơn với tình huống người dùng gửi request độc lập. Nếu tốc độ đến cao hơn năng lực xử lý, queue sẽ tích tụ và latency tăng. Một công cụ đo latency chỉ khi worker rảnh để bắt đầu yêu cầu có thể gặp **coordinated omission**: bỏ sót những khoảng thời gian mà yêu cầu đã phải chờ trước khi được đo.

Cần chọn mô hình đúng cho câu hỏi muốn trả lời và ghi rõ phương pháp đo thời gian chờ.

## 6. Một ví dụ JMH: đo tranh chấp của bộ đếm

**JMH (Java Microbenchmark Harness)** giúp thực hiện warmup, fork, đo lặp và giảm nhiều sai lầm thường gặp khi benchmark Java. Ví dụ này so sánh hai cách tăng bộ đếm chia sẻ giữa các luồng: `AtomicLong` và `LongAdder`.

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)               // TẤT CẢ thread cùng dùng hai counter.
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class CounterContentionBench {
    private final AtomicLong atomic = new AtomicLong();
    private final LongAdder striped = new LongAdder();

    @Benchmark
    public void atomicIncrement() {
        atomic.incrementAndGet();
    }

    @Benchmark
    public void stripedIncrement() {
        striped.increment();
    }
}
```

JMH phải được chạy bằng môi trường benchmark có dependency JMH và annotation processor thích hợp; chỉ đặt đoạn mã vào project Java thông thường chưa đủ để có một chương trình benchmark hoàn chỉnh. Sau khi đóng gói benchmark thành `benchmarks.jar`, có thể chạy **riêng mỗi phương án** ở nhiều mức luồng:

```bash
java -jar benchmarks.jar CounterContentionBench -t 1  -prof gc
java -jar benchmarks.jar CounterContentionBench -t 2  -prof gc
java -jar benchmarks.jar CounterContentionBench -t 4  -prof gc
java -jar benchmarks.jar CounterContentionBench -t 8  -prof gc
java -jar benchmarks.jar CounterContentionBench -t 16 -prof gc
```

Các tham số `@Warmup`, `@Measurement` và `@Fork` chỉ là cấu hình minh họa; thời gian/độ dài lặp phải được điều chỉnh khi phép đo còn nhiễu. Không có số throughput nào ở đây được giả định trước; chính kết quả đo mới xác định phương án nhanh hơn trên máy và workload đang dùng.

### Kết quả nào có thể rút ra?

- `AtomicLong.incrementAndGet()` cập nhật một ô nguyên tử; nhiều thread có thể tranh chấp ô nhớ đó.
- `LongAdder.increment()` phân tán cập nhật trên các ô nội bộ khi có tranh chấp, thường giúp giảm áp lực vào một điểm nóng.
- Hai phương án **không tương đương mọi ngữ nghĩa**: `AtomicLong.get()` đọc một giá trị nguyên tử, còn `LongAdder.sum()` không bảo đảm một snapshot nguyên tử khi có cập nhật đồng thời. Vì vậy, kết quả `increment()` không đủ để chọn `LongAdder` cho một bài toán yêu cầu đọc tổng tuyến tính hóa.
- `@State(Scope.Benchmark)` là điều kiện then chốt: nếu đổi thành `Scope.Thread`, mỗi luồng có bộ đếm riêng và bài kiểm tra **mất tranh chấp cần đo**.
- Các phép đo này **chưa đánh giá allocation của queue hoặc stack liên kết**; cần benchmark thao tác tạo/gỡ nút riêng, kèm bộ nhớ và GC.

Lưu ý: bộ đếm trong benchmark được dùng lại qua nhiều phép gọi, nhằm đo tốc độ cập nhật vào trạng thái chia sẻ. Trong hệ thống thật có thể cần đo cả khởi tạo, reset hoặc đọc tổng nếu những phần việc đó thuộc đường xử lý nghiệp vụ.

## 7. Lỗi benchmark Java thường gặp

### 7.1. Để compiler loại bỏ công việc

Ví dụ:

```java
// Không phải benchmark đáng tin: biến có thể chỉ sống trong phạm vi lời gọi.
void test() {
    int sum = 0;
    for (int i = 0; i < 1000; i++) {
        sum += i;
    }
}
```

JIT có thể tối ưu phép tính hoặc cả vòng lặp vì kết quả không được sử dụng. Ngay cả `System.nanoTime()` đo quanh đoạn code này cũng không biến nó thành phép đo đáng tin. Hãy sử dụng harness có cơ chế nhận đầu ra như `Blackhole` hoặc trả về kết quả được quan sát đúng cách, đồng thời kiểm tra tối ưu hóa thoát (*escape analysis*) có làm biến mất cấp phát hay không.

### 7.2. Cấp phát bị tối ưu đi

Một benchmark gọi `new Node(...)` nhưng không cho đối tượng thoát khỏi phạm vi mà JIT nhận diện có thể không thực sự cấp phát vào heap như triển khai stack liên kết. Kết quả cực thấp không chứng minh chi phí allocation trong ứng dụng bằng không.

Cần thiết kế benchmark sao cho đối tượng đi qua **đúng luồng sở hữu và vòng đời** như hệ thống thật; đồng thời kiểm tra `gc.alloc.rate.norm` hoặc thông số tương đương trong profiler. Một phép đo “byte/op = 0” cần được hiểu cùng với khả năng JIT đã khử cấp phát.

### 7.3. Đo cả thiết lập ngoài ý muốn, hoặc không đo phần cần thiết

Nếu tạo một bảng băm triệu phần tử **bên trong** vòng đo `get`, kết quả chủ yếu đo dựng bảng, không đo `get`. Nếu tạo sẵn toàn bộ nút rồi chỉ đo `push` bằng cách nối con trỏ, kết quả lại bỏ sót allocation vốn thuộc `push` thực tế.

Không có quy tắc luôn phải đo hay bỏ thiết lập. Hãy đặt ranh giới theo **thao tác nghiệp vụ muốn đánh giá**, dùng setup ngoài vùng đo khi chuẩn bị dữ liệu không thuộc thao tác, và cố tình giữ phần cấp phát/thu hồi nằm trong phép đo nếu nó thực sự xảy ra trên đường xử lý.

### 7.4. Thay đổi workload giữa hai phương án

Bảng băm được thử ở 100 phần tử không thể so trực tiếp với cây được thử ở một triệu phần tử. Queue A trả lỗi khi đầy còn queue B âm thầm thêm phần tử cũng không thể so throughput thành công bằng tổng số lần gọi.

Cần dùng **cùng dữ liệu đầu vào, cùng tiêu chuẩn thành công và ngữ nghĩa tương thích**. Với queue hữu hạn, nên báo cáo cả số lần `offer` thất bại hoặc bị chặn, độ sâu queue và thời gian chờ của producer/consumer.

### 7.5. Không tách warmup, GC và nhiễu hệ thống

Benchmark Java cần thời gian khởi động để JIT tối ưu các đường chạy. Dừng GC, đổi tần số CPU, tải từ tiến trình khác, nhiệt độ máy, thay đổi lịch thread hoặc di chuyển giữa các vùng NUMA cũng có thể làm kết quả dao động.

Cần thử nhiều lần, nhiều fork, công bố độ biến thiên và môi trường thực thi. Không nên tùy tiện loại các lần chạy chậm chỉ vì chúng “xấu”, đặc biệt khi chính mục tiêu đo là tail latency hoặc chi phí thu hồi bộ nhớ.

## 8. Thiết kế ma trận thử nghiệm có tranh chấp và cấp phát

Để đánh giá một queue, stack hay bảng băm, có thể thiết kế phép đo theo các trục sau:

| Trục thử nghiệm | Giá trị gợi ý | Vì sao cần |
| --- | --- | --- |
| **Số luồng** | 1, 2, 4, 8, 16 và mức sát số lõi vật lý | Xác định đường cong scaling và điểm bão hòa |
| **Tỷ lệ đọc/ghi** | 100/0, 95/5, 50/50, 5/95 | Reader và writer tranh chấp khác nhau; COW bị ảnh hưởng bởi write |
| **Phân bố khóa** | Đồng đều, một số khóa nóng, một khóa cực nóng | Phơi bày contention vào cùng bucket, khóa hoặc cache line |
| **Kích thước cấu trúc** | Nhỏ, vừa, lớn; thay đổi số phần tử đang sống | Bộc lộ chi phí sao chép, cache miss và footprint |
| **Trạng thái queue** | Rỗng, tải cân bằng, gần đầy, quá tải | Thể hiện semantics khi rỗng/đầy và độ sâu hàng đợi |
| **Vòng đời nút** | Tạo mới, pool, GC/retire thực tế | Phân biệt chi phí logic với cấp phát và reclamation |
| **Mẫu reader** | Đọc ngắn, duyệt dài, giữ snapshot lâu | Phát hiện live set và phiên bản cũ không được thu hồi |
| **Đặc điểm phần cứng** | Một socket, đa socket khi có thể | Phát hiện cache coherence, NUMA và giới hạn băng thông |

Không nhất thiết chạy tích Descartes của tất cả giá trị. Hãy chọn **vài kịch bản có chủ đích** phù hợp với workload mục tiêu, sau đó thay đổi một trục tại một thời điểm để xác định nguyên nhân khác biệt.

Ví dụ với bảng băm dùng đồng thời:

- **Kịch bản A – đọc cấu hình:** 99,9% `get`, 0,1% cập nhật, ít khóa, reader rất ngắn.
- **Kịch bản B – cập nhật dữ liệu:** 50% `get` và 50% `put`, nhiều writer cùng cập nhật một nhóm khóa nóng.
- **Kịch bản C – snapshot sống lâu:** 99% `get`, các lượt đọc có thể giữ một phiên bản trong hàng giây, writer đều đặn tạo phiên bản mới.

Một cấu trúc có thể dẫn đầu ở A nhưng dùng bộ nhớ không phù hợp ở C hoặc tranh chấp cao ở B. Cần báo cáo phạm vi mà kết luận áp dụng, thay vì đặt nhãn “nhanh nhất” cho mọi hoàn cảnh.

## 9. Đọc đúng đồ thị scaling

Để biết một thuật toán có khả năng tận dụng thêm luồng hay không, lập bảng và vẽ đường cong **throughput theo số luồng**. Một đồ thị giả định có thể có dạng:

```text
Throughput
  ^
  |                      _____ B
  |             ________/
  |       ____/
  |   ___/  \____ A
  |__/          \________
  +--------------------------------> Số luồng
      1     2      4    8    16
```

Đây chỉ là sơ đồ khái niệm: A có thể tăng nhanh ở ít luồng rồi suy giảm do tranh chấp một điểm nóng, còn B có thể mở rộng tốt hơn ở mức tải cao. Để tìm nguyên nhân, đối chiếu đồng thời **CPU utilization, CAS failure/retry, lock wait, GC, allocation rate, cache miss, độ sâu queue** và những chỉ số có sẵn trên nền tảng.

Một số sai lầm khi phân tích:

- **Chỉ chọn mức luồng mà ứng viên mình thích thắng:** cần công bố dải luồng liên quan đến hệ thống mục tiêu.
- **Lấy tốc độ ở 16 luồng chia 16 để suy ra tốc độ của mỗi lời gọi:** điều này không phản ánh phân bố latency.
- **Nhầm throughput bão hòa với khả năng đáp ứng lưu lượng thực tế:** ứng dụng có thể cần dư công suất để giữ p99 thấp khi lưu lượng tăng đột ngột.
- **Quên giới hạn bộ nhớ:** throughput tốt trong phép đo ngắn chưa chắc bền vững khi số nút chờ thu hồi tăng liên tục.

## 10. Quy trình đo có thể tái lập

Một quá trình đánh giá cấu trúc dữ liệu đồng thời có thể thực hiện theo các bước:

1. **Khóa ngữ nghĩa và bất biến:** hai ứng viên phải giải cùng bài toán: FIFO/LIFO, tuyến tính hóa các thao tác cần thiết, chính sách khi rỗng/đầy và loại kết quả thành công.
2. **Định nghĩa workload:** ghi rõ số luồng, tỷ lệ thao tác, kích thước, phân bố khóa, thời gian reader giữ tham chiếu, tỷ lệ producer/consumer.
3. **Định nghĩa ranh giới phép đo:** nêu phần cấp phát và thu hồi nào thuộc thao tác, phần chuẩn bị nào được đặt ngoài.
4. **Làm nóng runtime và chạy lặp:** trên JVM có warmup, nhiều fork độc lập; trên môi trường khác cần kiểm soát compiler và cache tương ứng.
5. **Ghi nhiều chỉ số:** throughput, latency phân vị, retry, lock wait, allocation byte/op, GC, live set và mức sử dụng CPU.
6. **Tăng dần tranh chấp:** từ 1 luồng lên số luồng mục tiêu, thử nhóm khóa nóng và các trạng thái rỗng/đầy có ý nghĩa.
7. **Kiểm tra tính bền vững:** chạy đủ dài để nhìn thấy GC/retirement và dấu hiệu tăng bộ nhớ; giới hạn số yêu cầu hoàn thành hoặc thời lượng phải tương đương.
8. **Ghi điều kiện thực nghiệm:** mã nguồn, phiên bản JVM/compiler, CPU, số lõi, hệ điều hành, tham số GC, cấu hình JMH, độ biến thiên kết quả.

Nếu hệ thống có yêu cầu latency, nên bổ sung bài đo ở **tốc độ yêu cầu đến cố định** và thống kê thời gian yêu cầu chờ trước khi được xử lý, để tránh chỉ nhìn throughput trong hệ thống tự điều tiết tải.

## 11. Tình huống tự kiểm tra

**Tình huống 1.** Bench `push` cho stack liên kết bằng cách tạo sẵn một triệu nút; trong ứng dụng thật, mỗi lần `push` gọi `new Node`. Có thể dùng ns/op của benchmark làm độ trễ dự kiến trong production không?

*Phân tích:* Chưa. Benchmark đã bỏ qua allocation và khả năng xuất hiện GC/thu hồi. Nó chỉ đo chi phí cập nhật con trỏ theo giả định có sẵn nút. Cần đo thêm phiên bản tạo nút và vòng đời thực tế.

**Tình huống 2.** Một bộ đếm CAS có throughput rất cao ở 1 luồng, nhưng khi tăng lên 16 luồng throughput giảm và CPU vẫn gần 100%. Nguyên nhân cần kiểm tra đầu tiên là gì?

*Phân tích:* Tranh chấp ô nhớ nguyên tử, chuyển quyền sở hữu cache line và các lần CAS retry. Cũng cần kiểm tra scheduler, phân bố trên lõi vật lý và nhiễu hệ thống; chỉ CPU 100% chưa chứng minh tất cả CPU đang làm việc hữu ích.

**Tình huống 3.** Hai bản cài đặt queue được benchmark với tỷ lệ producer/consumer 8:1. Queue thứ nhất không giới hạn, queue thứ hai hữu hạn. Queue thứ nhất đạt số `offer`/s cao hơn, nhưng bộ nhớ tăng liên tục. Phương án nào tốt hơn?

*Phân tích:* Chưa đủ thông tin để kết luận. Phải xem throughput **xử lý hoàn tất**, độ sâu backlog, tác động quá tải, trường hợp queue đầy và giới hạn bộ nhớ. Thêm phần tử nhanh không đồng nghĩa phục vụ công việc nhanh.

**Tình huống 4.** Một cấu trúc COW có `get` cực nhanh ở 10 triệu phần tử; benchmark chỉ có read. Ứng dụng thật cập nhật 100 lần/giây và giữ nhiều snapshot cũ. Phải đo thêm điều gì?

*Phân tích:* Chi phí sao chép khi ghi theo `n`, allocation rate, số snapshot còn sống, live set/peak memory, GC và tail latency của cả đọc lẫn ghi. Benchmark `get` đơn lẻ không phản ánh những chi phí này.

**Tình huống 5.** Benchmark JMH hai counter dùng `@State(Scope.Thread)` và chạy `-t 16`. Kết quả có đại diện cho 16 luồng tranh chấp **một bộ đếm chung** không?

*Phân tích:* Không. Mỗi luồng có bản `State` riêng nên cập nhật vào các bộ đếm riêng biệt. Phải dùng trạng thái chia sẻ `Scope.Benchmark` hoặc thiết kế nhóm chia sẻ phù hợp để đo tranh chấp trên cùng tài nguyên.

**Điểm cần ghi nhớ:** Độ phức tạp `O(1)`, thuật toán lock-free hoặc một con số ns/op đẹp không tự chứng minh một cấu trúc dữ liệu sẽ nhanh trong hệ thống nhiều luồng. Phải đo cả **tranh chấp, retry, chờ khóa, cấp phát/thu hồi, GC, độ trễ đuôi và khả năng mở rộng**, trong workload có ngữ nghĩa tương đương và gần với ứng dụng cần phục vụ.
