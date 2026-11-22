# Đo kiểm trước khi chọn Stream song song cho bài toán cụ thể

## 1. Tại sao không thể mặc định `parallel()` nhanh hơn?

Trong Java Stream API, ta có thể chuyển pipeline tuần tự sang xử lý song song khá dễ dàng:

~~~java
long sequential = numbers.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallel = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Hoặc trên cùng loại nguồn:

~~~java
long total = Arrays.stream(values)
        .parallel()
        .mapToLong(x -> x * 2L)
        .sum();
~~~

**Dễ viết không có nghĩa luôn hiệu quả hơn.** Xử lý song song có chi phí phân chia công việc, lập lịch, tạo/phối hợp các tác vụ và ghép kết quả. Với dữ liệu ít hoặc phép biến đổi quá đơn giản, tổng chi phí có thể lớn hơn phần thời gian tiết kiệm được. Trên máy nhiều lõi, tốc độ cũng bị giới hạn bởi bandwidth bộ nhớ, số CPU thực sự sẵn có, tải hệ thống và đặc điểm nguồn dữ liệu.

Vì vậy, trước khi chọn `parallel()` trong sản phẩm thật, cần trả lời bằng **đo kiểm trên workload đại diện**, không bằng cảm giác hoặc một lần bấm chạy:

1. Pipeline song song có cho **kết quả đúng** như tuần tự theo yêu cầu nghiệp vụ không?
2. Dữ liệu thật lớn đến đâu, phân bố và tính chọn lọc của `filter` như thế nào?
3. Chi phí tính toán trên mỗi phần tử đủ lớn để bù overhead không?
4. Đo **latency**, **throughput** hay cả hai? Với tải đồng thời, kết quả có thay đổi không?
5. Cần bao nhiêu CPU, heap và băng thông bộ nhớ để đạt mức cải thiện?
6. Kết quả có lặp lại qua warmup, nhiều lần đo và môi trường triển khai thực tế không?

Bài này dùng Java 17+, cung cấp quy trình benchmark, ví dụ chạy được và các lỗi khiến phép đo bị sai lệch.

## 2. Hiểu hai chế độ thực thi trước khi đo

### 2.1. Stream tuần tự

~~~java
int sum = Arrays.stream(new int[]{1, 2, 3})
        .map(x -> x * x)
        .sum();
~~~

Thông thường, pipeline tuần tự thực thi công việc trên một luồng gọi terminal operation. Các bước `map`/`filter` là intermediate operations có tính lazy: terminal operation như `sum`, `toList` hoặc `collect` mới yêu cầu duyệt nguồn.

### 2.2. Stream song song

~~~java
int sum = Arrays.stream(new int[]{1, 2, 3})
        .parallel()
        .map(x -> x * x)
        .sum();
~~~

`parallel()` đặt chế độ thực thi song song của pipeline; nó **không** tự khởi chạy tính toán khi được gọi. Khi terminal chạy, triển khai có thể chia nguồn qua `Spliterator`, phân công tác vụ trên cơ chế fork/join và kết hợp kết quả.

Trong các trường hợp phổ biến, parallel streams dùng **common ForkJoinPool** của JVM. Tuy nhiên, không nên xây dựng giả định rằng mọi ngữ cảnh, mọi callback đều luôn chạy đúng N thread trong pool hoặc mỗi phép xử lý có pool riêng. Chính sách pool, ngữ cảnh gọi, môi trường JVM và các tác vụ khác có thể ảnh hưởng cách thực thi.

### 2.3. Hai biến thể nguồn

~~~java
// Với Collection:
List<Integer> list = List.of(1, 2, 3);
long a = list.stream().parallel()
        .mapToLong(Integer::longValue)
        .sum();
long b = list.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

// Với mảng nguyên thủy:
int[] array = {1, 2, 3};
long c = Arrays.stream(array).parallel()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Trên `Collection`, `parallelStream()` tạo stream ở chế độ song song ngay từ nguồn. `stream().parallel()` chuyển chế độ của pipeline. Về cách chọn chiến lược, điểm quan trọng là đo pipeline tương đương và **không vô tình so một luồng mảng nguyên thủy với một luồng đối tượng có boxing**.

## 3. Mô hình thời gian: overhead và tốc độ lý tưởng

Một mô hình đơn giản để hình dung:

\[
T_{\mathrm{sequential}}\approx T_{\mathrm{work}},
\]

\[
T_{\mathrm{parallel}}\approx
T_{\mathrm{split}}+
T_{\mathrm{schedule}}+
T_{\mathrm{work\ on\ workers}}+
T_{\mathrm{combine}}+
T_{\mathrm{contention}}.
\]

Đây là mô hình giải thích, **không phải công thức dự báo chính xác** cho một ứng dụng cụ thể. Nếu phần công việc nhỏ, `T_split` + `T_schedule` + `T_combine` có thể chiếm tỷ trọng lớn. Nếu mỗi phần tử tốn nhiều CPU và nguồn chia đều được, phần công việc trên các worker có thể giảm đáng kể.

**Speedup** được định nghĩa:

\[
S = \frac{T_{\mathrm{sequential}}}{T_{\mathrm{parallel}}}.
\]

- `S > 1`: parallel nhanh hơn theo phép đo đang xét.
- `S = 1`: thời gian tương đương.
- `S < 1`: parallel chậm hơn.

Ví dụ giả định: tuần tự 120 ms, song song 50 ms thì speedup là `120/50 = 2,4` lần. Những con số này chỉ minh họa phép tính, **không phải benchmark thực tế từ máy người học**.

Không nên kỳ vọng dùng bốn lõi thì nhất định nhanh gấp bốn. Có phần công việc không thể song song, và tốc độ bị giới hạn bởi các tài nguyên chung. Amdahl's law là khung tư duy về trần speedup khi chỉ một phần của công việc có thể song song; mức trần thực tế còn chịu overhead và nhiều yếu tố hệ thống.

## 4. Chỉ đo sau khi bảo đảm hai pipeline tương đương

Phép đo chỉ có ý nghĩa nếu so cùng yêu cầu nghiệp vụ.

~~~java
long sequential = Arrays.stream(values)
        .mapToLong(Work::compute)
        .sum();

long parallel = Arrays.stream(values)
        .parallel()
        .mapToLong(Work::compute)
        .sum();

if (sequential != parallel) {
    throw new AssertionError("Different results");
}
~~~

`Work::compute` biểu diễn một hàm thuần tính toán nhận `int` và trả `long`; ví dụ đầy đủ ở phần 10 định nghĩa hàm này. Với phép cộng `long`, overflow theo arithmetic Java có hành vi xác định (modulo 64-bit), nên tổng các giá trị không phụ thuộc cách ghép khi xét cùng toán tử cộng `long`. Tuy nhiên, yêu cầu nghiệp vụ có thể không chấp nhận overflow; khi ấy cần chọn kiểu và thuật toán khác.

Một số phép tổng hợp **không bảo đảm kết quả y hệt** nếu đổi thứ tự nhóm:

~~~java
// Ví dụ nguy hiểm nếu mong phép trừ giữ nguyên ngữ nghĩa:
int result = IntStream.of(20, 3, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Phép trừ không kết hợp, nên reduction như trên không đáp ứng yêu cầu đại số của `reduce`. Với `double`, cộng số thực có sai số làm tròn và có thể cho kết quả khác theo thứ tự kết hợp; kiểm tra bằng **ngưỡng sai số phù hợp**, không mặc định so bitwise tuyệt đối.

Với dữ liệu có encounter order và yêu cầu danh sách đúng thứ tự, đừng thay tùy tiện `toList()` bằng `forEach` có side effect rồi kết luận nhanh hơn. Nếu hai pipeline có hợp đồng đầu ra khác nhau, đó không phải phép so công bằng.

## 5. Chọn dữ liệu kiểm thử đại diện

### 5.1. Kích thước nguồn (N)

Một benchmark chỉ có `N = 100` có thể kết luận khác hoàn toàn với `N = 1_000_000`. Hãy chọn các mức gần với dữ liệu thực tế và thêm vùng nhỏ để tìm điểm chuyển tiếp nơi parallel bắt đầu có lợi:

~~~text
N = 100
N = 10_000
N = 100_000
N = 1_000_000
~~~

Các kích thước trên là **kịch bản mẫu**, không phải ngưỡng chung cho Java. Ngưỡng thực tế thay đổi theo công việc mỗi phần tử, nguồn và máy.

### 5.2. Chi phí tính toán trên mỗi phần tử

So sánh hai loại workload:

~~~java
// Công việc rất nhẹ:
.mapToLong(x -> x + 1L)

// Công việc CPU-heavy hơn:
.mapToLong(x -> expensivePureCalculation(x))
~~~

Một thao tác cộng đơn giản thường không đủ công việc để amortize overhead song song. Một hàm nhiều vòng tính toán có thể có cơ hội hưởng lợi, nhưng vẫn phải đo. Không dùng `Thread.sleep` để giả lập tải CPU: sleep là chờ, không phải CPU-bound; parallelizing blocking I/O/sleep trên common pool có các rủi ro riêng.

### 5.3. Khả năng chia nguồn

`Arrays.stream(int[])` và `IntStream.range(...)` có nguồn chia tương đối thuận lợi. Một nguồn được sinh qua iterator hoặc Spliterator chia không đều có thể hạn chế khả năng parallel. Một số nguồn như xử lý dòng dữ liệu, tokenization hay I/O thường có phần thao tác mang tính tuần tự hoặc chi phí đồng bộ.

Hãy ghi rõ **nguồn** trong benchmark, không chỉ số phần tử và phép map. Đổi từ `ArrayList<Integer>` sang `int[]` còn thay boxing, locality và footprint bộ nhớ, nên đó là một thay đổi khác ngoài “sequential hay parallel”.

### 5.4. Tính chọn lọc và phân bố dữ liệu

`filter(x -> condition(x))` với 1% phần tử đạt điều kiện có thể có hành vi khác 99% đạt. `findAny`, `anyMatch` và `findFirst` có tính short-circuit: vị trí phần tử thỏa điều kiện làm thay đổi lượng công việc cần thực hiện. Hãy kiểm thử cả trường hợp “khớp sớm”, “khớp muộn”, “không khớp” nếu chúng xảy ra trong sản phẩm.

## 6. Thiết kế benchmark cho JVM: warmup, nhiều lần đo, thống kê

Chạy một lần bằng `System.nanoTime()` rồi lấy kết quả làm kết luận là không đủ, vì JVM có JIT compilation, class loading, garbage collection, CPU scaling và hệ điều hành đang xử lý nhiều việc.

### 6.1. Warmup

Chạy cùng workload một số lần trước khi đo để giảm ảnh hưởng của JIT chưa tối ưu và tải lớp:

~~~java
for (int i = 0; i < 10; i++) {
    result = operation.getAsLong();
}
~~~

**Số 10 chỉ minh họa.** Warmup đủ hay chưa cần xem độ ổn định của kết quả và công cụ benchmark; không có một hằng số phù hợp mọi JVM và bài toán.

### 6.2. Đo nhiều vòng

Thực hiện nhiều vòng đo, phân tích các đại lượng như median và độ phân tán, không chỉ một con số nhỏ nhất. Chạy lại cả chương trình hoặc benchmark forks để quan sát biến động giữa các tiến trình.

### 6.3. Xen kẽ thứ tự đo

Nếu luôn đo tuần tự trước và song song sau, sự thay đổi nhiệt độ CPU, warmup, cache và tải nền có thể thiên lệch một phương. Nên luân phiên thứ tự, hoặc dùng framework benchmark kiểm soát thử nghiệm nhiều lần/fork.

### 6.4. Tránh tối ưu bỏ kết quả (dead-code elimination)

Nếu kết quả phép tính không được quan sát, JIT có thể loại bỏ một số việc mà bạn đang tưởng mình đo. Với ví dụ đơn giản, có thể lưu vào một **`volatile` sink** hoặc sử dụng kết quả trong kiểm tra đúng/sai; với benchmark chuẩn, hãy dùng cơ chế chống tối ưu hóa sai lệch của JMH (ví dụ `Blackhole`) theo thiết kế framework.

### 6.5. Đừng đưa công việc chuẩn bị dữ liệu vào phép đo một cách vô ý

Nếu mục tiêu là so **chi phí pipeline**, hãy tạo mảng dữ liệu trước khi đo. Nếu mục tiêu là latency của **toàn bộ request**, hãy đo cả chuyển đổi dữ liệu, tạo pipeline và serialization cần thiết. Cả hai đều có thể đúng, nhưng trả lời hai câu hỏi khác nhau.

## 7. Latency, throughput, CPU và bộ nhớ: không chỉ có một metric

| Thước đo | Câu hỏi | Lưu ý |
| --- | --- | --- |
| Latency mỗi lần xử lý | Một request hoàn thành nhanh đến đâu? | Đo p50/p95/p99 nếu có nhiều request |
| Throughput | Xử lý được bao nhiêu request/giây? | Parallel per-request có thể tranh CPU với request khác |
| CPU utilization | Dùng bao nhiêu tài nguyên CPU? | Tốc độ tăng nhưng chiếm nhiều lõi hơn không phải lúc nào cũng tốt |
| Allocation/GC | Có tạo nhiều object và gây GC hơn không? | Phân biệt primitive streams với boxed streams |
| Độ ổn định | Kết quả có biến động theo tải/hardware? | Chạy nhiều trial, nhiều quy mô và thời điểm |
| Độ đúng | Kết quả có đúng về tập phần tử, thứ tự và số học? | Bắt buộc kiểm tra trước khi xét hiệu năng |

Ví dụ: một request chạy từ 100 ms xuống 60 ms nhờ dùng hầu hết CPU của máy, nhưng hệ thống nhận 20 request đồng thời có thể giảm tổng throughput vì các request tranh cùng common pool/CPU. Khi chọn parallel trong dịch vụ server, cần đánh giá **toàn hệ thống dưới mức đồng thời dự kiến**, không chỉ một request đơn lẻ.

Nếu phần xử lý rất nhỏ so với network/database I/O, việc tối ưu `stream().parallel()` có thể không mang lại cải thiện đáng kể cho latency toàn request. Dùng profiling để xác định nút thắt thực tế.

## 8. Những yếu tố khiến parallel chậm hơn

### 8.1. Overhead phân chia và gộp

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .filter(x -> x >= 0)
        .count();
~~~

Với 100 phần tử và điều kiện đơn giản, chi phí tạo/phối hợp tác vụ có thể lấn át lợi ích. Đừng dùng ví dụ này để tuyên bố một tỷ lệ chậm cố định; cần đo trên máy và JVM cụ thể.

### 8.2. Boxing và đối tượng trung gian

~~~java
// Primitive pipeline:
long sum = IntStream.range(0, n)
        .parallel()
        .mapToLong(i -> i * 2L)
        .sum();

// Reference pipeline có boxing:
long sum2 = IntStream.range(0, n)
        .boxed()
        .parallel()
        .mapToLong(i -> i * 2L)
        .sum();
~~~

Nếu chỉ cần số nguyên, duy trì primitive stream có thể giảm boxing và allocation. Khi so sánh sequential/parallel, đừng đồng thời thay đổi chiến lược dữ liệu; như vậy không còn cách cô lập nguyên nhân.

### 8.3. Stateful operations và ràng buộc thứ tự

Các thao tác như `sorted`, `distinct` và một số thao tác có tính trạng thái có thể buộc phối hợp/đệm dữ liệu. `limit` và `skip` trên nguồn có thứ tự trong parallel stream cũng có thể tốn kém nếu phải duy trì encounter order.

~~~java
List<Integer> topTen = numbers.parallelStream()
        .sorted()
        .limit(10)
        .toList();
~~~

Pipeline này có mục tiêu cụ thể nhưng không thể suy rằng việc thêm `parallel()` chắc chắn làm nó nhanh. Việc sắp xếp, giữ thứ tự và cắt số phần tử có thể chiếm ưu thế hơn phép map song song.

**Không dùng `unordered()` chỉ để tăng tốc nếu ứng dụng cần thứ tự.** Loại bỏ ràng buộc encounter order có thể đổi ngữ nghĩa kết quả, đặc biệt với `findFirst` hoặc `limit`.

### 8.4. Chi phí synchronization và contention

~~~java
// Tránh chia sẻ mutable state giữa các callback:
List<Integer> result = new ArrayList<>();

// Không an toàn khi parallel:
// numbers.parallelStream().forEach(result::add);
~~~

`ArrayList` không thread-safe cho thêm phần tử đồng thời. Dùng `collect` hoặc `toList` sẽ phù hợp hơn:

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(x -> x > 0)
        .toList();
~~~

Dùng khóa đồng bộ quanh `result.add` có thể giảm rủi ro race nhưng lại tạo contention, có thể triệt tiêu lợi ích parallel. Nếu correctness chỉ có được bằng một điểm khóa toàn cục, nên xem lại thiết kế.

### 8.5. CPU thực sự khả dụng

`Runtime.getRuntime().availableProcessors()` chỉ cung cấp số processor JVM báo cáo ở thời điểm gọi, không phải một cam kết rằng ứng dụng luôn có lượng CPU rảnh tương đương. Container quota, giới hạn tài nguyên, tải của các process khác, nhiệt độ, turbo boost và bộ nhớ đều tác động phép đo.

Để so giữa hai môi trường, hãy ghi rõ phiên bản JDK, số CPU báo cáo, giới hạn container nếu có, RAM, OS, cài đặt JVM và mức tải chung.

## 9. Phân biệt CPU-bound và blocking I/O

Parallel Stream thường phù hợp nhất để cân nhắc khi **mỗi phần tử có công việc CPU-bound độc lập** và nguồn có thể chia tương đối đều.

Nếu callback truy vấn HTTP, gọi database hoặc đợi filesystem:

~~~java
// Chỉ là ví dụ về việc KHÔNG nên mặc nhiên chuyển sang parallel:
// urls.parallelStream().map(this::fetchRemote).toList();
~~~

Đó là thao tác **blocking I/O**. Những lời gọi chờ có thể chiếm worker của common pool trong thời gian dài, ảnh hưởng workload khác và không cung cấp giới hạn concurrency, timeout, backpressure theo cách một client I/O chuyên dụng cần. Hãy thiết kế rõ thread pool, giới hạn request song song, timeout, retry và cơ chế quản lý tài nguyên phù hợp; không dùng `parallelStream` như một giải pháp async tổng quát.

**Không benchmark bằng `Thread.sleep(10)` rồi kết luận parallel stream tối ưu cho CPU-heavy.** Sleep làm tăng thời gian chờ; phép thử không đại diện chi phí tính toán thực.

## 10. Chương trình Java 17+ hoàn chỉnh để thử nghiệm ban đầu

Ví dụ dưới đây cố ý **không in một thời gian cụ thể**: thời gian là dữ liệu thực nghiệm thay đổi theo máy và lượt chạy. Chương trình tự kiểm tra kết quả giữa tuần tự và song song, warmup, chạy một vài vòng so sánh và chỉ in số đo được định dạng.

Đây là **microbenchmark minh họa cách nghĩ**, chưa phải benchmark đáng tin cậy như JMH. Hãy dùng nó để quan sát nguy cơ sai lệch và lập giả thuyết trước khi thiết lập phép đo nghiêm túc.

Tạo tệp **`ParallelMeasurementDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.function.LongSupplier;

public class ParallelMeasurementDemo {
    // Làm cho kết quả được quan sát; không thay thế JMH Blackhole.
    private static volatile long sink;

    // Hàm tính toán thuần khiết, độc lập cho mỗi phần tử.
    static long compute(int input) {
        long x = input + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 64; i++) {
            x ^= (x >>> 13);
            x *= 0xBF58476D1CE4E5B9L;
            x ^= (x >>> 17);
        }
        return x;
    }

    static long sequential(int[] input) {
        return Arrays.stream(input)
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    static long parallel(int[] input) {
        return Arrays.stream(input)
                .parallel()
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    static long measureNanos(LongSupplier task, int repeats) {
        long total = 0L;
        for (int i = 0; i < repeats; i++) {
            long start = System.nanoTime();
            long value = task.getAsLong();
            long elapsed = System.nanoTime() - start;
            sink = value;
            total += elapsed;
        }
        return total / repeats;
    }

    public static void main(String[] args) {
        int n = 100_000;
        int[] data = new int[n];
        for (int i = 0; i < n; i++) {
            data[i] = i * 31 + 7;
        }

        // Kiểm tra correctness trước mọi so sánh tốc độ.
        long expected = sequential(data);
        long parallelValue = parallel(data);
        if (expected != parallelValue) {
            throw new AssertionError("Mismatch");
        }
        System.out.println("resultsEqual=true");
        System.out.println("elements=" + data.length);

        // Warmup cả hai nhánh trước khi đo.
        for (int i = 0; i < 12; i++) {
            sink = sequential(data);
            sink = parallel(data);
        }

        // Đo luân phiên thứ tự; ví dụ đơn giản, không thay JMH.
        long sequentialTotal = 0;
        long parallelTotal = 0;
        int rounds = 6;
        for (int i = 0; i < rounds; i++) {
            if (i % 2 == 0) {
                sequentialTotal += measureNanos(() -> sequential(data), 1);
                parallelTotal += measureNanos(() -> parallel(data), 1);
            } else {
                parallelTotal += measureNanos(() -> parallel(data), 1);
                sequentialTotal += measureNanos(() -> sequential(data), 1);
            }
        }

        double seqMillis = sequentialTotal / (rounds * 1_000_000.0);
        double parMillis = parallelTotal / (rounds * 1_000_000.0);
        System.out.printf(Locale.ROOT,
                "sequentialAvgMs=%.3f%n", seqMillis);
        System.out.printf(Locale.ROOT,
                "parallelAvgMs=%.3f%n", parMillis);
        System.out.println("speedupDependsOnEnvironment=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ParallelMeasurementDemo.java
java ParallelMeasurementDemo
~~~

**Những dòng kết quả có thể kiểm chứng độc lập với máy:**

~~~text
resultsEqual=true
elements=100000
sequentialAvgMs=<số đo thực tế>
parallelAvgMs=<số đo thực tế>
speedupDependsOnEnvironment=true
~~~

Hai dòng `<số đo thực tế>` là ký hiệu mô tả **chứ không phải stdout nguyên văn**; chương trình sẽ in số thập phân thực như `123.456` theo môi trường đang chạy. Không có một số ms duy nhất đúng cho mọi máy. Vì mô phỏng workload CPU có vòng lặp, thời gian và speedup đặc biệt nhạy với JIT, bộ xử lý và tải nền.

### 10.1. Điều gì được và chưa được kiểm soát?

Được kiểm soát phần nào:

- Nguồn `int[]` tạo trước, không bao gồm thời gian khởi tạo dữ liệu trong từng phép đo.
- Hai pipeline khác nhau chủ yếu ở `parallel()`.
- Hàm `compute` không dùng I/O hoặc sửa trạng thái bên ngoài.
- Kết quả được kiểm tra bằng giá trị `long` và ghi vào `volatile sink`.
- Có warmup và thay đổi thứ tự chạy đo giữa các vòng.

Chưa được kiểm soát đầy đủ:

- Không có nhiều JVM forks độc lập.
- Không dùng JMH để giảm ảnh hưởng của compiler, sampling và dead-code elimination.
- Số vòng và warmup được chọn để **minh họa**, chưa chứng minh đã hội tụ.
- Kết quả dùng **trung bình cộng**, chưa có phân phối hay confidence interval.
- Common pool có thể bị các tác vụ khác trong cùng JVM chia sẻ.
- Không đo CPU time, allocation rate, GC, throughput dưới tải hoặc tail latency.

Đây là lý do không nên dùng một chương trình thủ công như trên làm bằng chứng duy nhất để bật `parallel()` trong production.

## 11. Dùng JMH cho microbenchmark đáng tin cậy hơn

**JMH (Java Microbenchmark Harness)** là công cụ benchmark dành cho Java/JVM của OpenJDK, thường được dùng để đo những đoạn mã ngắn có nhiều rủi ro sai lệch do JIT. JMH không phải thành phần mặc định của JDK: phải thêm dependency/plugin hoặc tạo dự án JMH riêng.

Ví dụ skeleton **minh họa, không phải tệp Java độc lập với JDK thuần**:

~~~java
@State(Scope.Thread)
public class StreamBenchmark {
    private int[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = new int[100_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i * 31 + 7;
        }
    }

    @Benchmark
    public long sequential() {
        return Arrays.stream(data)
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    @Benchmark
    public long parallel() {
        return Arrays.stream(data)
                .parallel()
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }
}
~~~

Đoạn JMH trên **giả định**:

- Đã thiết lập dependencies/imports JMH, chẳng hạn `org.openjdk.jmh.annotations.*`.
- Hàm `ParallelMeasurementDemo.compute` được đưa vào cùng project hoặc thay bằng hàm tính toán được định nghĩa trong benchmark; ví dụ này chỉ dùng để làm rõ cấu trúc, không phải mã copy-paste độc lập.
- Benchmark được chạy bằng runner và cấu hình JMH thích hợp.

Các khái niệm cần cấu hình:

| JMH concept | Vai trò |
| --- | --- |
| `@Benchmark` | Đánh dấu phương thức cần đo |
| `@State` | Quản lý dữ liệu và phạm vi chia sẻ |
| `@Setup` | Chuẩn bị fixture trước khi đo |
| Warmup iterations | Làm nóng JVM và mã đo |
| Measurement iterations | Thu thập mẫu sau warmup |
| Forks | Chạy JVM mới để giảm ảnh hưởng của trạng thái process trước đó |
| Benchmark mode | Chọn AverageTime, Throughput hoặc chế độ phù hợp |
| `Blackhole`/return value | Làm kết quả được tiêu thụ, hạn chế tối ưu hóa không mong muốn |

Điểm đặc biệt khi đo **parallel stream**: mỗi benchmark invocation có thể kích hoạt nhiều worker, nên hai benchmark “cùng một thread gọi hàm” không có cùng mức sử dụng CPU. Khi đo throughput nhiều benchmark threads, việc mỗi invocation dùng thêm pool sẽ khiến contention phức tạp hơn. Phải phân biệt rõ benchmark của một request đơn với benchmark throughput nhiều request chạy đồng thời.

**Chọn JMH khi mục tiêu là microbenchmark một thao tác Java; chọn load test end-to-end khi mục tiêu là tối ưu toàn dịch vụ.** Cần cả hai nếu thay đổi ảnh hưởng tới tail latency hoặc tranh tài nguyên giữa các request.

## 12. Thiết kế ma trận benchmark trước khi kết luận

Thay vì một cặp kết quả, hãy lập ma trận các trường hợp có ý nghĩa:

| Trường hợp | Số phần tử | Công việc/phần tử | Nguồn | Điều cần xác minh |
| --- | ---: | --- | --- | --- |
| Nhỏ, nhẹ | 100 | `x + 1` | `int[]` | Parallel overhead có thể lấn át |
| Vừa, nhẹ | 10.000 | `x + 1` | `int[]` | Có điểm hòa vốn hay không |
| Lớn, CPU-heavy | 100.000 | Hàm tính nhiều vòng | `int[]` | Có lợi ích song song thật |
| Rất lớn, CPU-heavy | 1.000.000 | Hàm tính nhiều vòng | `int[]` | Bộ nhớ/CPU trở thành nút thắt nào |
| Dữ liệu boxed | 100.000 | Hàm tính nhiều vòng | `List<Integer>` | Boxing và locality thay đổi |
| Stateful pipeline | 100.000 | `sorted` hoặc `distinct` | Nguồn đại diện | Chi phí phối hợp/thứ tự |
| Nhiều request | Theo workload sản phẩm | CPU-heavy | Môi trường server | Throughput, tail latency, contention |

Các kích thước và mô tả này là **gợi ý thiết kế phép thử**, không phải kết quả đo hay ngưỡng quyết định. Với mỗi trường hợp, giữ pipeline tuần tự và song song cùng nguồn, predicate, kết quả và môi trường.

Chỉ so sánh phiên bản code như nhau ngoại trừ chế độ thực thi; nếu muốn kiểm tra tối ưu hóa boxing hay đổi collector, hãy tách thành **thí nghiệm khác**.

### 12.1. So sánh nhiều môi trường

Có thể thử local developer machine và môi trường staging/production-like, nhưng đừng coi kết quả local có thể áp thẳng lên container giới hạn CPU. Nên ghi lại:

- JDK vendor/version, JVM flags, heap/GC configuration.
- CPU vật lý/logic và CPU quota/container giới hạn.
- Hệ điều hành, kiến trúc CPU, tình trạng tải nền.
- Kích thước nguồn, kiểu dữ liệu và distribution.
- Số lần warmup, số measurement iterations, số forks.
- Số benchmark threads/request đồng thời.
- Median/mean, phân tán, allocation, GC, throughput và tail latency khi áp dụng.

## 13. Phân tích tình huống lựa chọn

### 13.1. Tình huống A — dữ liệu ít, mapper nhẹ

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Có ba phần tử và mỗi mapper ngắn. Nhu cầu parallel không rõ ràng và overhead rất có thể không đáng. **Ưu tiên tuần tự** cho đến khi có số đo đại diện chứng minh khác.

### 13.2. Tình huống B — rất nhiều phép tính độc lập

~~~java
long total = Arrays.stream(largeIntArray)
        .parallel()
        .mapToLong(this::expensivePureCalculation)
        .sum();
~~~

Nếu `expensivePureCalculation` là hàm CPU-bound, stateless, mỗi phần tử độc lập và nguồn lớn, parallel có cơ hội tăng tốc. Nhưng kết quả chỉ hợp lệ nếu hàm không dùng mutable shared state và phép tổng hợp phù hợp tính kết hợp. Cần benchmark đủ quy mô và tải thực.

### 13.3. Tình huống C — cần thứ tự phần tử chính xác

~~~java
List<String> labels = names.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

Trên nguồn `List` có encounter order, `toList()` giữ thứ tự. Tuy vậy, những thao tác như `forEach` có thể có thứ tự thực hiện khác; nếu cần xuất kết quả theo thứ tự, không thể đổi terminal tùy tiện. Ràng buộc giữ thứ tự có thể giảm khả năng tăng tốc, nhất là với các thao tác có trạng thái như `limit`.

### 13.4. Tình huống D — hệ thống server đang bận

Một REST request tự bật parallel stream để “mượn” nhiều CPU có thể giảm latency của request trong lúc một mình, nhưng tranh tài nguyên khi hàng chục request chạy đồng thời. Đừng chỉ tối ưu một request ở chế độ không tải. Hãy đo throughput và p95/p99 dưới traffic đại diện, chú ý common pool có thể là tài nguyên chung với code khác.

### 13.5. Tình huống E — callback truy cập database

Không giả định `parallelStream` là giải pháp để gọi nhiều query đồng thời. Query có chi phí mạng và hệ thống database có pool connection/giới hạn riêng; mở nhiều request đồng thời có thể làm chậm database hoặc gây quá tải. Tối ưu N+1 queries, batching, caching và điều khiển concurrency thường quan trọng hơn đổi Stream mode.

## 14. Lỗi benchmark và diễn giải phổ biến

| Sai lầm | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Đo một lần rồi kết luận | JIT/GC/OS gây biến thiên lớn | Warmup, đo nhiều lần và forks |
| Chỉ nhìn thời gian tốt nhất | Chọn mẫu may mắn, không đại diện | Báo median/mean và độ phân tán |
| Không kiểm tra kết quả | Pipeline có thể đổi thứ tự hoặc sai reduction | Test correctness trước đo |
| Bỏ qua cost chuẩn bị dữ liệu | Đo khác câu hỏi end-to-end | Xác định phạm vi phép đo |
| Tạo List boxed ở bản song song, int[] ở bản tuần tự | Nguồn khác nhau, kết quả không cô lập | Cố định nguồn và kiểu |
| Dùng `Thread.sleep` để giả lập CPU work | Đo blocking, không phải CPU computation | Dùng workload thật hoặc CPU-bound gần thực |
| Dùng `map` có side effect để đếm | Callback có thể bị tối ưu hóa hoặc chạy khác thứ tự | Dùng terminal/collector có nghĩa rõ |
| Lấy `parallel()` làm bảo đảm nhiều lõi | Phụ thuộc Spliterator, pool, quota, workload | Đo và kiểm tra môi trường |
| Chỉ đo một request, bỏ qua tải nhiều request | Tranh CPU/common pool dưới đồng thời | Load-test throughput và tail latency |
| Giả định mọi phép reduce kết hợp | Phép trừ, floating point có vấn đề | Chọn phép tổng hợp hợp lệ/sai số |
| Dùng `unordered()` để tối ưu mà không xét correctness | Có thể thay đổi chọn phần tử và thứ tự | Giữ semantics nghiệp vụ |
| Diễn giải speedup > 1 là luôn nên bật | Có thể tiêu tốn nhiều tài nguyên hơn | Đánh giá cả CPU, GC, latency, throughput |
| Benchmark với dữ liệu không giống thật | Cache và phân bố sai làm sai kết luận | Dùng dataset/kích thước đại diện |
| Đo JMH nhưng không kiểm soát benchmark threads | Parallel trong mỗi invocation dùng nhiều worker | Tách workload 1 request và tải đồng thời |

## 15. Quy trình ra quyết định có thể lặp lại

1. **Định nghĩa mục tiêu:** tối ưu latency một thao tác, throughput dịch vụ, hay hiệu quả CPU?
2. **Viết baseline tuần tự** đúng ngữ nghĩa, ưu tiên hàm thuần khiết và primitive streams nếu phù hợp.
3. **Tạo bản song song chỉ khác chế độ**, không thay đổi logic, nguồn hoặc cách xây kết quả.
4. **Kiểm chứng correctness** trên dữ liệu rỗng, nhỏ, lớn, chứa biên và phân bố thực tế. Với floating point, định nghĩa tolerance hợp lý.
5. **Benchmark micro** bằng JMH nếu thao tác đủ nhỏ và cần so sánh chi tiết; bảo đảm warmup, measurement, forks và kết quả được quan sát.
6. **Benchmark end-to-end** khi thao tác nằm trong request/ứng dụng có I/O và cạnh tranh tài nguyên.
7. **Quan sát metric khác tốc độ** như throughput, p95/p99, CPU, allocation/GC, bộ nhớ.
8. **Xem xét chi phí và độ phức tạp:** nếu lợi ích nhỏ hơn nhiễu phép đo hoặc gây giảm throughput dưới tải, giữ bản tuần tự.
9. **Ghi lại quyết định:** workload, môi trường, phương pháp đo, số liệu, ngưỡng chấp nhận và điều kiện cần benchmark lại.
10. **Đo lại khi thay đổi** JDK, hardware, CPU quota, dữ liệu hoặc code; đừng giả định hiệu năng cố định theo thời gian.

Điều kiện bật parallel nên là kết quả của một **thí nghiệm có thể lặp lại**, không phải một “quy tắc kích thước 10.000 phần tử” truyền miệng.

## 16. Bài tập tự kiểm tra

**Câu 1.** Vì sao `IntStream.range(0,100).parallel().sum()` không nhất thiết nhanh hơn `IntStream.range(0,100).sum()`?

**Đáp án:** Công việc tổng hợp rất nhỏ, trong khi parallel thêm overhead phân chia, lập lịch và ghép kết quả. Cần đo, không có bảo đảm tăng tốc.

**Câu 2.** Với hai pipeline giống nhau ngoại trừ `parallel()`, điều gì phải kiểm tra trước khi so thời gian?

**Đáp án:** Hai pipeline phải cho kết quả tương đương đúng nghiệp vụ, kể cả thứ tự cần thiết và quy tắc số học; không có side effect/race phá tính đúng.

**Câu 3.** Tại sao phép đo đầu tiên bằng `System.nanoTime()` dễ sai lệch?

**Đáp án:** Class loading, JIT, warmup, GC, CPU scaling và tiến trình nền có thể làm thời gian khác các lượt ổn định. Nên dùng warmup, nhiều iteration và JMH cho microbenchmark nghiêm túc.

**Câu 4.** Benchmark song song một request chạy nhanh hơn 30% có đủ để chọn nó trong REST service không?

**Đáp án:** Chưa. Cần đo throughput và latency dưới nhiều request đồng thời, mức dùng CPU và tác động của common ForkJoinPool, GC/heap. Lợi ích đơn lẻ có thể làm cả hệ thống chậm hơn.

**Câu 5.** Vì sao không nên đo một pipeline tuần tự bằng `int[]` và bản parallel bằng `List<Integer>`?

**Đáp án:** Khác biệt boxing, locality, nguồn, chi phí cấp phát và Spliterator khiến khó kết luận mức tăng/giảm do parallelization.

**Câu 6.** `findAny` chạy parallel luôn trả phần tử khác nhau mỗi lần và nhanh hơn `findFirst` không?

**Đáp án:** Không. `findAny` không cam kết kết quả ngẫu nhiên hay tốc độ nhanh hơn; nó chỉ được tự do chọn phần tử phù hợp mà không phải giữ yêu cầu “đầu tiên” theo encounter order. Đo workload thật và kiểm tra lựa chọn có chấp nhận được không.

**Câu 7.** Khi pipeline gọi HTTP cho mỗi phần tử, dùng `parallelStream` có phải cách tốt nhất để kiểm soát concurrency không?

**Đáp án:** Không nên mặc định. Blocking I/O, common pool, giới hạn kết nối, timeout và retry cần thiết kế riêng. Benchmark end-to-end và dùng mô hình I/O/concurrency phù hợp.

**Câu 8.** Nếu hai bản đều đúng nhưng parallel nhanh hơn 5% trong một lượt đo duy nhất, có đủ chứng cứ để bật không?

**Đáp án:** Không. Mức khác biệt có thể nằm trong nhiễu; cần lặp lại, báo độ biến thiên và đánh giá tác động dưới tải. Nếu lợi ích thiếu ổn định hoặc làm tăng tiêu hao tài nguyên, giữ bản đơn giản hơn.

## 17. Ghi nhớ

**Quyết định dùng parallel Stream là quyết định dựa trên số liệu, không dựa trên cú pháp.** Hãy nhớ:

- `parallel()` không làm mọi pipeline nhanh hơn; overhead có thể lớn hơn phần thời gian tiết kiệm.
- **Correctness trước, hiệu năng sau.** Chỉ so hai pipeline tương đương về dữ liệu, thứ tự và phép tổng hợp.
- So sánh trên dữ liệu và phép tính **đại diện cho production**, gồm nhiều kích thước nguồn và tải đồng thời.
- Warmup JVM, đo nhiều lần, kiểm soát tối ưu hóa sai lệch; dùng **JMH** cho microbenchmark nghiêm túc và load-test cho hệ thống.
- Đánh giá thêm throughput, tail latency, CPU, heap, allocation/GC; speedup riêng một request không kể toàn bộ câu chuyện.
- Cân nhắc chi phí phân chia, boxing, nguồn khó split, stateful operations, giữ thứ tự, contention và common pool.
- Không dùng parallel Stream như giải pháp mặc định cho blocking I/O hoặc side effects mutable.
- Ghi lại điều kiện đo và kiểm tra lại khi dữ liệu/hardware/JVM thay đổi.

Nếu chưa có kết quả benchmark đáng tin cho trường hợp cụ thể, **ưu tiên bản tuần tự đơn giản, đúng và dễ bảo trì**, sau đó chỉ bật song song khi bằng chứng cho thấy lợi ích thực sự đáng giá.
