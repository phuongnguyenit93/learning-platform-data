# False sharing và cache-line contention trong Java concurrency

## 1. Bài toán: hai thread không dùng chung biến nhưng vẫn cản nhau

Giả sử hai thread thực hiện công việc độc lập: thread A liên tục cập nhật bộ đếm A, thread B liên tục cập nhật bộ đếm B. Hai bộ đếm **khác vị trí lưu trữ** và mỗi bộ đếm chỉ có một thread ghi, nên nhìn từ logic chương trình, chúng không cần tranh nhau một lock. Vậy tại sao chương trình vẫn có thể chạy chậm khi hai thread chạy đồng thời trên hai CPU core?

Một nguyên nhân là **false sharing**: hai biến độc lập nằm trên **cùng một cache line**, trong khi ít nhất một thread liên tục ghi vào phần dữ liệu của mình. Giao thức nhất quán cache (cache coherence) quản lý quyền sở hữu ở mức *cache line*, chứ không ở mức từng biến Java. Vì vậy các core có thể phải liên tục chuyển quyền ghi đối với cùng một line, mặc dù không hề sửa cùng một biến.

Đây là vấn đề **hiệu năng** của việc đặt dữ liệu trong bộ nhớ và truy cập đồng thời; không đồng nghĩa với *data race* hoặc lỗi Java Memory Model (JMM).

**Mục tiêu bài học:** hiểu cơ chế cache line, phân biệt false sharing với true sharing, nhận diện các mẫu truy cập dễ gặp trong Java, đo đạc có kiểm soát và chọn giải pháp tương xứng với chi phí.

## 2. Cache line là gì?

CPU thường không tải riêng lẻ mỗi biến `long` 8 byte từ bộ nhớ chính vào cache; nó trao đổi dữ liệu theo những khối bộ nhớ liên tiếp gọi là **cache line**. Nhiều hệ thống x86-64 hiện đại dùng line **64 byte**, nhưng kích thước và chi tiết giao thức phụ thuộc kiến trúc CPU. **Không có cam kết trong ngôn ngữ Java rằng mọi máy đều dùng cache line 64 byte.**

Ví dụ minh họa một cache line 64 byte (sơ đồ logic, không phải bảo đảm bố trí đối tượng JVM):

```text
                  CACHE LINE (64 byte, minh họa)
byte offset       0       8      16      24      32       ...    63
                  +-------+-------+-------+-------+---------------+
Thread A ghi ---> |   A   |   B   | dữ liệu khác trong cùng line   |
                  +-------+-------+-------+-------+---------------+
                          ^
                          |
                      Thread B ghi

A và B là hai long độc lập (mỗi long thường chiếm 8 byte).
```

Một mô hình đơn giản của hiện tượng trên máy nhiều core:

1. Core 0 lấy line chứa A và B ở trạng thái cho phép ghi, rồi cập nhật A.
2. Core 1 muốn ghi B. Do B nằm trên **cùng line**, core 1 phải giành trạng thái/quyền sở hữu thích hợp của line đó theo giao thức nhất quán cache.
3. Core 0 tiếp tục ghi A, nên lại cần quyền ghi của line. Quyền sở hữu line có thể chuyển qua lại giữa các core; lưu lượng coherence và thời gian chờ tăng.
4. Càng nhiều lần cập nhật xen kẽ, chi phí chuyển line càng lớn so với phép cộng đơn giản ở mức logic.

Các giao thức như MESI/MOESI là mô hình hữu ích để hình dung, nhưng không nên khẳng định mọi CPU hoặc mọi lần ghi luôn thực hiện cùng một chuỗi thông điệp. Đó cũng không nhất thiết là việc copy về DRAM sau mỗi lần cập nhật: chuyển dữ liệu/quyền sở hữu có thể diễn ra giữa các cache trong hệ phân cấp bộ nhớ.

**Vấn đề nằm ở hạt độ nhất quán của cache:** hardware không biết rằng A và B là hai trường dữ liệu độc lập về mặt nghiệp vụ. Nó phải bảo vệ tính nhất quán của toàn bộ line.

## 3. Phân biệt true sharing, false sharing và contention do lock

| Tình huống | Hai thread cùng truy cập gì? | Điều gì tranh chấp? | Hướng xử lý thường gặp |
| --- | --- | --- | --- |
| **True sharing** | Cùng bộ đếm/địa chỉ; ít nhất một thread ghi | Giá trị chung và quyền ghi line chứa giá trị | Giảm tần suất cập nhật, phân mảnh/striping, gom kết quả |
| **False sharing** | Hai bộ đếm/địa chỉ khác nhau, nhưng cùng cache line | Quyền sở hữu **line**, dù không dùng chung giá trị | Tách vị trí nóng ra các line khác nhau; gom cập nhật cục bộ |
| **Lock contention** | Cùng monitor/`Lock` hoặc vùng critical section | Cơ chế đồng bộ/đợi lock; đôi khi kèm tác động cache | Thu ngắn vùng lock, giảm số thread cạnh tranh, đổi thiết kế đồng bộ |
| **Read-only sharing** | Nhiều core chỉ đọc dữ liệu không đổi | Thường không có luồng ghi liên tục làm line ping-pong | Có thể hoàn toàn bình thường; tránh tối ưu vô ích |

Ba nguyên nhân hiệu năng có thể **đồng thời tồn tại**. Ví dụ hai lock khác nhau đặt cạnh nhau có thể tạo false sharing ở metadata, trong khi các thread lại còn cạnh tranh thật sự trên một lock khác.

False sharing chỉ có ý nghĩa khi có mẫu **ghi lặp lại** đủ lớn để chi phí coherence đáng kể. Hai biến đứng cạnh nhau nhưng chỉ đọc, hoặc mỗi biến chỉ ghi một lần, không tự động gây vấn đề thực tế.

## 4. Ví dụ Java 17+: cập nhật AtomicLongArray ở chỉ số gần và xa

`AtomicLongArray` cung cấp các phép đọc/ghi nguyên tử cho từng phần tử; mỗi lần `getAndIncrement(index)` thực hiện một cập nhật nguyên tử tại **chỉ số riêng**. Ta có thể tạo hai thread, mỗi thread sở hữu một chỉ số, nên không có tranh chấp logic trên cùng bộ đếm.

Hai cấu hình để quan sát:

- **near:** hai thread ghi vào các chỉ số `0` và `1`, thường là hai `long` ở sát nhau trong vùng lưu trữ mảng.
- **far:** hai thread ghi vào `0` và `32`; khoảng cách theo phần tử là 256 byte, xa hơn nhiều so với cache line 64 byte điển hình.

**Điều kiện quan trọng:** JVM và phần cứng không cam kết địa chỉ/alignment hay cache line size cho ví dụ, nên đây là một **thí nghiệm minh họa** chứ không phải một benchmark có thể chứng minh false sharing trên mọi máy. Bản thân atomic increment cũng có chi phí; khác biệt thời gian không được tự động quy hết cho false sharing.

Tạo tệp `FalseSharingDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLongArray;

public final class FalseSharingDemo {
    private static final int ITERATIONS = 2_000_000;

    private record Measurement(long elapsedNanos, long left, long right) {}

    private static Thread worker(
            AtomicLongArray counters,
            int index,
            CountDownLatch ready,
            CountDownLatch start) {
        return new Thread(() -> {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            for (int i = 0; i < ITERATIONS; i++) {
                counters.getAndIncrement(index);
            }
        }, "counter-" + index);
    }

    private static Measurement runCase(int leftIndex, int rightIndex)
            throws InterruptedException {
        AtomicLongArray counters = new AtomicLongArray(64);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Thread leftThread = worker(counters, leftIndex, ready, start);
        Thread rightThread = worker(counters, rightIndex, ready, start);
        leftThread.start();
        rightThread.start();

        // Bắt đầu đo khi cả hai thread đều đã sẵn sàng.
        ready.await();
        long begin = System.nanoTime();
        start.countDown();

        leftThread.join();
        rightThread.join();
        long elapsed = System.nanoTime() - begin;

        long left = counters.get(leftIndex);
        long right = counters.get(rightIndex);
        if (left != ITERATIONS || right != ITERATIONS) {
            throw new AssertionError("Counter value is incorrect");
        }
        return new Measurement(elapsed, left, right);
    }

    public static void main(String[] args) throws InterruptedException {
        Measurement near = runCase(0, 1);
        Measurement far = runCase(0, 32);

        System.out.println("near counts: " + near.left() + " / " + near.right());
        System.out.println("far counts: " + far.left() + " / " + far.right());
        System.out.printf("near: %.3f ms; far: %.3f ms%n",
                near.elapsedNanos() / 1_000_000.0,
                far.elapsedNanos() / 1_000_000.0);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FalseSharingDemo.java
java FalseSharingDemo
```

Hai dòng đầu của stdout khi chạy bình thường sẽ là:

```text
near counts: 2000000 / 2000000
far counts: 2000000 / 2000000
```

Dòng cuối in `near: <thời gian> ms; far: <thời gian> ms`; **giá trị thay đổi theo lần chạy/máy**, vì vậy không có con số stdout cố định cho dòng này. Nếu thấy `near` chậm hơn `far`, đây là dấu hiệu phù hợp với giả thuyết false sharing, **chưa phải bằng chứng kết luận**. Có lần hai trường hợp bằng nhau hoặc đảo chiều do JIT, scheduler, số core, trạng thái CPU, nhiễu hệ thống và cách bố trí mảng.

Tại sao dùng `CountDownLatch` và `join()`?

- `ready` giúp cả hai thread sẵn sàng trước khi thả `start`, giảm chênh lệch thời điểm khởi chạy; vẫn không loại bỏ toàn bộ nhiễu.
- `join()` đợi hai thread kết thúc trước khi đọc bộ đếm. Cả tính nguyên tử của `AtomicLongArray` và quan hệ *happens-before* của thread termination/`join` giúp kiểm tra kết quả đúng.
- Mỗi index được **chỉ một thread cập nhật**. Kết quả đúng ở cả hai case; khác biệt nếu có là chi phí thực thi, không phải dữ liệu mất cập nhật.
- Mỗi lần `getAndIncrement` dùng primitive nguyên tử nên overhead có thể khác workload dùng write bình thường. Không dùng tỷ số hai lần chạy của demo để khẳng định mức tăng tốc cụ thể cho sản phẩm.

## 5. Cơ chế chính xác hơn: độ gần của dữ liệu và mẫu truy cập

### Vị trí dữ liệu quan trọng hơn tên biến

Hai field cùng khai báo trong một class **không bảo đảm** nằm cạnh nhau theo đúng thứ tự source code. JVM có thể bố trí lại field, thêm header, alignment và padding; kiểu đối tượng, chế độ VM và các tối ưu khác cũng tác động. Tương tự, hai object Java được tạo liên tiếp **không có cam kết** nằm ở hai cache line khác nhau (hoặc chung một line).

Trong ví dụ mảng, các phần tử kiểu nguyên thủy của cùng mảng được lưu theo vùng liên tiếp về mặt layout điển hình. Vì vậy dùng các chỉ số gần/xa có ý nghĩa thực nghiệm hơn giả định rằng hai object được `new` lần lượt sẽ cách nhau đúng 64 byte. Tuy vậy, **đừng biến giả định layout/64 byte thành quy tắc Java portable**.

### Tần suất đọc/ghi quyết định cường độ

Một line có thể được nhiều core cache ở trạng thái shared khi chúng chỉ đọc. Khi core ghi, nó cần trạng thái cho phép ghi và các bản sao khác phải được xử lý theo coherence protocol. False sharing đặc biệt tốn kém với **các cập nhật ghi liên tục, luân phiên trên nhiều core**. Nếu một thread ghi xong rồi thread khác mới ghi, hoặc hai thread được xếp trên cùng core và không chạy thực sự đồng thời, hiệu ứng có thể ít nổi bật hơn.

### Java Memory Model và cache coherence không phải một thứ

JMM xác định các quy tắc visibility, ordering và *happens-before* mà chương trình Java được phép dựa vào. Cache coherence là cơ chế hardware bên dưới để giữ nhất quán giữa các cache. JMM **không hứa rằng hai biến logic độc lập được bố trí trên hai line riêng**.

- `volatile` và atomic operations có bảo đảm visibility/ordering theo hợp đồng Java, nhưng không tránh false sharing nếu hai vị trí độc lập đặt chung line.
- `synchronized` và `Lock` giải quyết điều kiện đồng bộ logic; thêm lock không giải quyết gốc false sharing, đôi khi còn tăng contention.
- `long[]` với hai thread chỉ ghi **hai index khác nhau** cũng có thể gặp vấn đề hardware tương tự mà không nhất thiết có data race trên cùng phần tử. Dùng `AtomicLongArray` trong demo để các thao tác update thực sự diễn ra dưới primitive atomic, dễ quan sát hiệu ứng hơn; **không phải** vì mọi mảng nguyên thủy đều cần atomic.

## 6. Những mẫu Java hay gặp

### 6.1. Một mảng counter theo worker

Ví dụ một hệ thống dành `counters[workerId]` cho từng worker. Logic tránh true sharing, nhưng các counter nằm sát nhau. Nếu mỗi worker tăng counter hàng triệu lần mỗi giây trên những core khác nhau, line chứa nhiều counter có thể ping-pong. Đây là ví dụ false sharing điển hình của bố trí dữ liệu sát nhau.

### 6.2. Nhiều biến volatile trạng thái đặt gần nhau

Hai thread có thể liên tục cập nhật `volatile long sequenceA` và `volatile long sequenceB` độc lập. Nếu layout đặt các field trên cùng line, chúng có thể tranh quyền ghi. Nhưng chỉ nhìn source code không đủ để chứng minh chúng chia sẻ line: cần khảo sát layout và đo ở workload thực tế.

### 6.3. Queue/ring buffer có sequence cursor

Trong các cấu trúc hiệu năng cao, thread producer và consumer có thể cập nhật các chỉ số riêng, chẳng hạn publish/consume sequence. Hai cursor ghi thường xuyên và nằm chung line có thể gây cache-line contention, dù mỗi phía có trách nhiệm riêng. Cần đo cùng với chi phí synchronization bắt buộc để bảo đảm publish/consume đúng thứ tự; **không được xóa volatile/atomic chỉ để giảm coherence traffic nếu điều đó phá visibility**.

### 6.4. Trộn dữ liệu nóng và lạnh

Một field trạng thái thường xuyên ghi nằm cùng line với dữ liệu mà thread khác thường xuyên đọc có thể khiến reader phải nạp lại line hoặc mất hiệu quả cache. Đây là vấn đề bố trí dữ liệu và invalidation. Không phải trường hợp nào cũng là mẫu hai writer đối xứng, nhưng cùng nguyên lý coherence ở hạt độ line.

## 7. Giảm false sharing: chọn giải pháp theo workload

### A. Giảm số lần ghi vào dữ liệu chia sẻ

Nếu nghiệp vụ cho phép, mỗi thread có thể cộng số đếm vào biến cục bộ trong một batch, rồi định kỳ flush tổng vào vị trí chia sẻ. Ví dụ thay vì mỗi sự kiện gọi `counter.incrementAndGet()`, có thể cộng 100 hoặc 1.000 sự kiện vào biến cục bộ và publish phần tổng sau. Giảm số write/atomic operation thường có tác dụng lớn hơn việc chỉ căn padding.

Nhưng batch làm thay đổi độ mới của metric, rủi ro mất số đếm chưa flush khi crash và semantics của thời điểm quan sát. Phải nêu rõ hợp đồng đúng đắn trước khi áp dụng.

### B. Phân bố dữ liệu nóng sang line khác nhau

Với bộ đếm theo worker dạng mảng, có thể dùng stride đủ lớn theo kiến trúc đã đo, ví dụ chỉ số `workerId * 16` với `long[]` (16 phần tử = 128 byte). Điều này **thường** tránh hai giá trị nóng cùng line 64 byte, nhưng tốn bộ nhớ và không tạo cam kết portable về kích thước line/alignment. Với `AtomicLongArray`, tăng khoảng cách index cũng tương tự ví dụ `far`.

Nếu dùng stride, hãy bọc mapping trong một abstraction nhỏ thay vì để phép nhân rải khắp code. Kiểm tra tràn index, chi phí cấp phát và cache footprint. Đặc biệt, không được để hai thread ghi cùng một index vì tính toán sai chỉ số.

### C. Dùng dữ liệu cục bộ rồi tổng hợp

Nếu từng thread sở hữu một counter, tốt nhất có thể là giữ counter cục bộ và tổng hợp tại ranh giới xử lý hoặc bằng cơ chế snapshot/merge phù hợp. Có thể dùng thread-local trong thread pool truyền thống, nhưng cần xét vòng đời thread, reset và cleanup để không giữ state ngoài mong muốn. Không mặc định một `ThreadLocal` là chiến lược tổng hợp tổng toàn cục có thể đọc tức thì.

### D. LongAdder cho một bộ đếm thực sự bị nhiều thread cùng tăng

Nếu **nhiều thread cùng cập nhật một counter logic**, `LongAdder` trong `java.util.concurrent.atomic` là lựa chọn đáng xem xét. Nó phân tán cập nhật vào các cell nội bộ khi có contention, sau đó `sum()` tổng hợp; điều này thường giảm true sharing trên một atomic duy nhất.

Tuy nhiên:

- `LongAdder` giải quyết một pattern **true sharing**; không phải thuốc chữa mọi false sharing giữa các biến độc lập.
- `sum()` không phải snapshot nguyên tử đối với cập nhật đồng thời. Không dùng `sum()` thay trực tiếp một phép đọc có tính tuyến tính hóa nếu nghiệp vụ bắt buộc snapshot nhất quán tức thời.
- Có thêm chi phí bộ nhớ và tổng hợp; kiểm chứng với workload thật.

### E. Padding hoặc `@Contended` ở lớp triển khai thích hợp

Một số thư viện hiệu năng cao chủ động tách field nóng bằng padding. Nhưng việc khai báo nhiều `long p1, p2, ...` **không bảo đảm** JVM giữ đúng thứ tự, kích thước hay khoảng cách như tưởng tượng; JIT và cấu trúc object có thể thay đổi kết quả. Việc tách các object bằng `new` riêng cũng **không bảo đảm** tách cache line.

HotSpot/JDK còn có annotation nội bộ `jdk.internal.vm.annotation.Contended` để đề nghị JVM padding field/class. Đây **không phải Java SE public API**: mã ứng dụng thường cần `--add-exports java.base/jdk.internal.vm.annotation=ALL-UNNAMED` khi biên dịch/chạy trong classpath và cấu hình HotSpot như `-XX:-RestrictContended` để annotation của mã người dùng có hiệu lực. Các cờ và hành vi có thể thay đổi theo JVM/JDK. Không áp dụng mù quáng trong thư viện portable; hãy xác minh đúng phiên bản JVM, layout và kết quả benchmark. Annotation này không biến từng phần tử `AtomicLongArray` thành field được padding riêng.

### F. Thay đổi cấu trúc công việc

Đôi khi thiết kế tốt hơn là gom quyền ghi một nhóm dữ liệu vào một thread/partition, gửi sự kiện qua queue rồi tổng hợp. Cách này có thể tránh nhiều core luân phiên ghi cùng vùng dữ liệu, đổi lấy chi phí queue, độ trễ truyền và cách xử lý backpressure. Quyết định phụ thuộc số thread, tần suất cập nhật, SLA và semantics cần thiết.

## 8. Đo đúng: một benchmark đơn lẻ không đủ

False sharing dễ bị nhầm với chi phí atomic, cache miss thông thường, migration giữa core hoặc scheduler. Một kết quả `near` chậm hơn `far` trong một lần chạy chỉ là **giả thuyết cần kiểm tra**.

Một quy trình đo có cơ sở:

1. **Giữ nguyên thuật toán và khối lượng công việc**, chỉ thay đổi khoảng cách/bố trí bộ đếm. Nếu đồng thời đổi lock, kiểu dữ liệu hoặc số phép atomic, không thể quy nguyên nhân riêng cho false sharing.
2. **Đảm bảo có ít nhất hai thread cập nhật thực sự**, lý tưởng chạy trên các core riêng khi muốn xem coherence giữa core; kiểm tra số core vật lý, thread scheduling, affinity nếu môi trường cho phép.
3. **Warm up JVM/JIT**, chạy nhiều vòng, nhiều JVM fork, đo median/phân phối thay vì chỉ một kết quả. Đảo thứ tự case, vì case chạy trước/sau có thể chịu hiệu ứng nhiệt độ, frequency scaling và cache.
4. **Quan sát cả throughput và latency**, tránh chỉ đọc một số nanosecond. Khi so sánh production, phải gắn với tải và tỷ lệ thread thực tế.
5. **Kiểm soát nhiễu:** GC, cấp phát, CPU scaling, background processes, NUMA, giới hạn CPU của container, tối ưu dead-code elimination, memory bandwidth và các phụ thuộc dữ liệu khác.
6. **Kiểm chứng layout** trên JDK/CPU thật khi giả thuyết dựa vào offset; kết hợp hardware performance counters/profiling khi được hỗ trợ. Một thread dump đơn thuần thường không nói được line nào đang bị tranh.
7. **Đánh giá trade-off:** padding làm tăng RAM/cache footprint; tối ưu một số counter có thể làm chậm chỗ khác hoặc không cải thiện throughput cuối cùng.

### Java Microbenchmark Harness (JMH)

JMH phù hợp hơn vòng lặp `System.nanoTime()` tự viết vì hỗ trợ warmup, đo lặp, fork và tiêu thụ kết quả. Ví dụ phác thảo dưới đây **cần dự án đã cài dependency JMH và annotation processor**; nó không phải file Java độc lập để chạy bằng mỗi lệnh `javac`:

```java
import java.util.concurrent.atomic.AtomicLongArray;
import org.openjdk.jmh.annotations.*;

@State(Scope.Group)
public class CounterLayoutBenchmark {
    private final AtomicLongArray values = new AtomicLongArray(64);

    @Benchmark
    @Group("adjacent")
    @GroupThreads(1)
    public long adjacentLeft() {
        return values.incrementAndGet(0);
    }

    @Benchmark
    @Group("adjacent")
    @GroupThreads(1)
    public long adjacentRight() {
        return values.incrementAndGet(1);
    }

    @Benchmark
    @Group("separated")
    @GroupThreads(1)
    public long separatedLeft() {
        return values.incrementAndGet(0);
    }

    @Benchmark
    @Group("separated")
    @GroupThreads(1)
    public long separatedRight() {
        return values.incrementAndGet(32);
    }
}
```

Với `@Group` và `@GroupThreads(1)`, mỗi case có hai phương thức được gọi bởi hai benchmark thread; `@State(Scope.Group)` cho phép các thread trong group dùng chung một đối tượng state của group. Cần cấu hình số thread/core, forks, warmup và iterations nhất quán; kiểm tra nhóm `adjacent` so với `separated` trong nhiều lần đo. Kết quả vẫn phụ thuộc cache-line layout thực tế và overhead atomic. Nếu dùng `Mode.Throughput`, hiểu rõ đơn vị kết quả và cách JMH tính operations cho group trước khi đưa ra kết luận.

Các công cụ khảo sát layout đối tượng như JOL có thể hỗ trợ xem field offsets theo JVM. Hardware profiler (tùy CPU/OS) có thể cung cấp thông tin coherence/cache-to-cache transfer hoặc HITM; tuy nhiên việc suy ra false sharing từ một bộ đếm phần cứng duy nhất dễ sai. Kết hợp **layout + access pattern + cải thiện khi tách dữ liệu + phép đo lặp** mới tạo bằng chứng thuyết phục.

## 9. Các hiểu lầm và lỗi tối ưu phổ biến

**“Mỗi thread một biến nên chắc chắn không có contention.”** Không đúng. Không cùng biến chỉ loại một phần contention ở mức logic; hai biến vẫn có thể cùng cache line.

**“Dùng `volatile`/atomic thì không có false sharing.”** Các primitive đó bảo đảm thao tác và visibility theo mô hình Java; chúng không tự tách địa chỉ lưu trữ. Trên workload ghi dày đặc, atomic read-modify-write còn làm chi phí line ownership dễ quan sát.

**“Cứ đặt các field trong các object khác nhau là xong.”** Không có bảo đảm object cách nhau một cache line. Phải kiểm chứng layout/đường truy cập thực tế.

**“Cứ thêm padding 64 byte là portable.”** Cache line size, object header, alignment, field layout và padding rules không phải hợp đồng cố định của Java SE. Padding cũng tăng footprint và có thể làm giảm cache locality với workload đọc tuần tự.

**“Tách các field nóng luôn nhanh hơn.”** Không hẳn. Nếu dữ liệu thường được một thread đọc cùng nhau và ít ghi, đặt gần nhau giúp tận dụng spatial locality. Tách line có thể tăng cache misses và tiêu thụ bộ nhớ.

**“Cache-line contention giống tranh lock.”** Không. Thread có thể đang `RUNNABLE`, không đợi monitor Java, nhưng phần lớn chu kỳ CPU bị tiêu tốn bởi memory/coherence stalls. Đừng tìm mỗi `BLOCKED` thread rồi kết luận không có false sharing.

**“Bài benchmark near/far một lần đã chứng minh nguyên nhân.”** Không. Cần đối chiếu thuật toán, layout, CPU topology, lịch chạy và hiệu ứng JIT. Chỉ thay đổi nhiều yếu tố cùng lúc làm kết luận không có giá trị.

**“LongAdder là tối ưu mặc định cho mọi field.”** Không. Nó hướng đến counter chung được tăng nhiều lần, dùng thêm bộ nhớ và `sum()` có semantics khác đọc snapshot nguyên tử.

## 10. Checklist khi review Java concurrency có cập nhật nóng

- Có **từ hai thread ghi** các vị trí khác nhau nhưng gần nhau trong bộ nhớ, với tần suất lớn không? Cùng cache line là khả năng cần kiểm chứng.
- Đây là **true sharing, false sharing, lock contention hay cache miss/GC**? Thu thập chứng cứ trước khi đổi code.
- Mẫu truy cập là **write-heavy** hay **read-mostly**? Có thể đổi sang local aggregation hoặc batch được không?
- Kết quả có phụ thuộc **JVM object layout, cache line size, CPU topology** không? Ghi rõ giả định môi trường.
- Việc dùng stride, padding hoặc đổi kiểu counter có giữ nguyên **visibility, atomicity, ordering và semantics** hiện có không?
- Có benchmark warmup/fork nhiều lần và theo dõi workload thật không? Mức cải thiện có lớn hơn chi phí thêm bộ nhớ/độ phức tạp không?

## 11. Bài tập suy luận

**Tình huống A.** Thread A tăng `array[0]`, thread B tăng `array[1]` một triệu lần, mỗi thread dùng index riêng; trên một hệ 64-byte cache line các phần tử tình cờ chung line. Có data race logic trên cùng phần tử không? Vì sao vẫn chậm?

**Trả lời:** không có hai thread cùng ghi vào một phần tử, nên không có tranh chấp logic trên cùng bộ đếm; tuy nhiên cả hai cùng cần quyền ghi line chứa hai phần tử, khiến ownership có thể đổi qua lại giữa core. Đây là false sharing nếu nó gây suy giảm hiệu năng.

**Tình huống B.** Hai thread cùng `AtomicLong.incrementAndGet()` một đối tượng duy nhất. Có nên gọi đó là false sharing?

**Trả lời:** đó là **true sharing** vì cả hai thực sự cập nhật cùng một biến. Có thể xem xét `LongAdder` nếu chỉ cần phép cộng với semantics `sum()` phù hợp.

**Tình huống C.** Một nhóm field chỉ đọc sau khi khởi tạo, nằm chung line. Có cần padding riêng cho từng field?

**Trả lời:** thường không; các core có thể chia sẻ các bản sao đọc mà không có luồng write ping-pong. Padding có thể khiến locality tệ hơn.

**Tình huống D.** Tách hai counter ra xa làm microbenchmark nhanh hơn 30%, nhưng throughput toàn hệ thống không đổi. Có nên áp dụng ngay?

**Trả lời:** chưa đủ cơ sở. Counter có thể không nằm trên critical path, hoặc bottleneck chính ở nơi khác; đổi layout còn có chi phí bộ nhớ. Cần dựa vào profile và workload đại diện để quyết định.

**Kết luận kỹ thuật:** tối ưu false sharing bắt đầu từ việc nhận ra **cache coherence diễn ra theo line**, rồi chứng minh rằng mẫu ghi đồng thời vào các vị trí độc lập đang tạo tranh chấp line đáng kể. Chỉ tách/padding dữ liệu sau khi đã giữ nguyên tính đúng đắn và đo được lợi ích trên môi trường phù hợp.