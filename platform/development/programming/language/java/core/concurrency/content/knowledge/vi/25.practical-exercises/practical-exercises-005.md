# Thực hành: Tính tổng mảng bằng Fork/Join và so benchmark trong Java

## 1. Mục tiêu và đề bài

Cho một mảng `int[]` có `N` phần tử, hãy tính tổng bằng hai cách: **vòng lặp tuần tự** và **Fork/Join song song**. Kiểm tra hai kết quả giống nhau, sau đó đo thời gian trên nhiều kích thước mảng, ngưỡng chia task và số worker để xác định **khi nào Fork/Join đáng dùng**.

Bài tập này dùng Java/JDK thuần (Java 17+), không phụ thuộc Spring hay framework khác. Sau khi làm xong, bạn cần giải thích được cơ chế `RecursiveTask<Long>`, `fork()`, `compute()`, `join()`, work-stealing, ngưỡng `threshold`, chi phí scheduling, tính đúng với mảng rỗng và nguy cơ tràn `int`. Quan trọng nhất: biết so benchmark mà không khẳng định “song song luôn nhanh hơn”.

**Yêu cầu đầu ra:** kết quả tổng chính xác, code độc lập biên dịch được, một bảng thời gian đo trên máy thật và phần giải thích dựa trên số liệu. Các con số thời gian trong bài học chỉ là ví dụ cách đọc số liệu, không phải benchmark thực tế.

## 2. Thiết kế thuật toán và bất biến

Phạm vi mỗi task là **đoạn nửa mở** `[from, to)`: gồm `from` và không gồm `to`. Do đó số phần tử của task là `to - from`. Hai nhánh khi tách ở `mid` phải là `[from, mid)` và `[mid, to)`: không bỏ, không đếm trùng phần tử.

- **Bản tuần tự:** khởi tạo `long sum = 0L`, lần lượt cộng tất cả phần tử, trả sum.
- **Task lá:** nếu số phần tử `<= threshold`, dùng vòng lặp trực tiếp cộng một đoạn rồi trả `long`.
- **Task phân nhánh:** lấy `mid = from + (to-from)/2`, tạo hai task. `fork` một nhánh, tính nhánh còn lại trên worker hiện tại, `join` nhánh đã fork rồi cộng hai kết quả.
- **Điều kiện dừng:** yêu cầu `threshold > 0`. Đoạn rỗng `[0,0)` có tổng bằng `0L`.

~~~text
N = 16, threshold = 4

[0,16)
   ├─ [0,8)
   │    ├─ [0,4)    -> tính lá
   │    └─ [4,8)    -> tính lá
   └─ [8,16)
        ├─ [8,12)   -> tính lá
        └─ [12,16)  -> tính lá

S(0,16) = S(0,4) + S(4,8) + S(8,12) + S(12,16)
~~~

**Chứng minh ngắn:** một lá cộng mỗi phần tử của nó đúng một lần. Khi chia, hai đoạn con rời nhau và hợp thành đúng đoạn cha, nên tổng hai nhánh bằng tổng đoạn cha. Đệ quy dừng vì mỗi đoạn đủ lớn được chia thành hai đoạn ngắn hơn và `threshold` dương. Tổng mảng bằng kết quả root task `[0, N)`.

### Vì sao phải dùng `long`?

`int` tràn khi tổng nằm ngoài khoảng `-2_147_483_648` đến `2_147_483_647`. Chẳng hạn `Integer.MAX_VALUE + Integer.MAX_VALUE` đúng về toán học là **4.294.967.294**, ngoài miền `int`. Dùng `long sum` **ngay trong task lá**, rồi trả `RecursiveTask<Long>` để duy trì tổng chính xác. `long` cũng có giới hạn; nếu bài toán có thể vượt miền `long`, dùng `Math.addExact` để phát hiện tràn hoặc `BigInteger` theo yêu cầu nghiệp vụ.

Chỉ được giả định các task đọc mảng ổn định. Nếu một luồng khác sửa `data[i]` trong lúc tính, kết quả không còn là một snapshot nhất quán. Hãy hoàn tất tạo dữ liệu trước khi bắt đầu và không ghi vào mảng cho đến khi các task kết thúc.

## 3. Code Java 17 hoàn chỉnh: `ArraySumForkJoinDemo.java`

Ví dụ sau xây dựng bộ dữ liệu xác định, đối chiếu tổng tuần tự và Fork/Join, kiểm tra ca mảng rỗng/tràn `int`, rồi chạy **phép đo thời gian minh họa**. Không cần thêm dependency.

~~~java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public class ArraySumForkJoinDemo {
    private static final int N = 1_000_000;
    private static final int THRESHOLD = 16_384;
    private static final int WARMUP = 5;
    private static final int ROUNDS = 11;
    private static volatile long sink;

    private static long sequentialSum(int[] a) {
        long sum = 0L;
        for (int x : a) {
            sum += x;
        }
        return sum;
    }

    private static final class SumTask extends RecursiveTask<Long> {
        private final int[] a;
        private final int from;
        private final int to;
        private final int threshold;

        private SumTask(int[] a, int from, int to, int threshold) {
            this.a = a;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int length = to - from;
            if (length <= threshold) {
                long sum = 0L;
                for (int i = from; i < to; i++) {
                    sum += a[i];
                }
                return sum;
            }

            int mid = from + length / 2;
            SumTask left = new SumTask(a, from, mid, threshold);
            SumTask right = new SumTask(a, mid, to, threshold);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    private static long forkJoinSum(
            ForkJoinPool pool, int[] a, int threshold) {
        if (threshold <= 0) {
            throw new IllegalArgumentException("threshold must be > 0");
        }
        return pool.invoke(new SumTask(a, 0, a.length, threshold));
    }

    private static double medianMillis(
            LongSupplier operation, long expected) {
        for (int i = 0; i < WARMUP; i++) {
            long value = operation.getAsLong();
            if (value != expected) {
                throw new AssertionError("Incorrect warmup result");
            }
            sink = value;
        }

        long[] samples = new long[ROUNDS];
        for (int i = 0; i < ROUNDS; i++) {
            long start = System.nanoTime();
            long value = operation.getAsLong();
            samples[i] = System.nanoTime() - start;
            if (value != expected) {
                throw new AssertionError("Incorrect measured result");
            }
            sink = value;
        }

        Arrays.sort(samples);
        return samples[ROUNDS / 2] / 1_000_000.0;
    }

    public static void main(String[] args) throws InterruptedException {
        int[] data = new int[N];
        for (int i = 0; i < N; i++) {
            data[i] = (i % 1_000) - 500;
        }

        // Một nhóm 1000 số có tổng -500; có 1000 nhóm.
        long expected = -500_000L;
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            if (sequentialSum(data) != expected
                    || forkJoinSum(pool, data, THRESHOLD) != expected) {
                throw new AssertionError("Sum mismatch");
            }

            int[] largeValues = {
                    Integer.MAX_VALUE, Integer.MAX_VALUE
            };
            long largeSum = 4_294_967_294L;
            if (sequentialSum(largeValues) != largeSum
                    || forkJoinSum(pool, largeValues, 1) != largeSum) {
                throw new AssertionError("Overflow-case mismatch");
            }

            int[] empty = new int[0];
            if (sequentialSum(empty) != 0L
                    || forkJoinSum(pool, empty, 1) != 0L) {
                throw new AssertionError("Empty-array mismatch");
            }

            System.out.printf(
                    "n=%d, expected=%d, workers=%d, threshold=%d%n",
                    data.length, expected,
                    pool.getParallelism(), THRESHOLD);
            System.out.println("correctness=PASS");

            double seqMs = medianMillis(
                    () -> sequentialSum(data), expected);
            double fjMs = medianMillis(
                    () -> forkJoinSum(pool, data, THRESHOLD), expected);

            System.out.printf("sequential medianMs=%.3f%n", seqMs);
            System.out.printf("forkjoin   medianMs=%.3f%n", fjMs);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Lưu đúng tên file `ArraySumForkJoinDemo.java`. Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ArraySumForkJoinDemo.java
java ArraySumForkJoinDemo
~~~

Hai dòng đầu của stdout **xác định** (trên một lần chạy thành công):

~~~text
n=1000000, expected=-500000, workers=4, threshold=16384
correctness=PASS
~~~

Sau đó là hai dòng `sequential medianMs=...` và `forkjoin   medianMs=...`. Không thể xác định trước thời gian của máy khác, vì vậy **không bịa con số cho phần này**. Nếu thay `N`, quy tắc sinh dữ liệu hoặc số worker, cần cập nhật `expected`/thông báo tương ứng.

### Giải thích điểm then chốt trong code

1. **`RecursiveTask<Long>`:** một công việc có kết quả. `RecursiveAction` chỉ phù hợp khi công việc không cần giá trị trả về.
2. **`left.fork()`:** đưa một nhánh vào lịch xử lý của pool; không tạo một OS thread riêng cho từng task. Worker rảnh có thể lấy task qua work-stealing.
3. **`right.compute()`:** làm nhánh còn lại trên worker hiện tại, giảm số tác vụ chỉ được đưa vào hàng đợi.
4. **`left.join()`:** lấy kết quả task đã fork, có thể phải chờ; trong ForkJoinPool cơ chế chờ phối hợp với việc thực thi task khác theo khả năng runtime.
5. **`pool.invoke(root)`:** giao root task vào pool và đợi kết quả (hoặc exception). Không cần tự tạo luồng cho mỗi nhánh.
6. **`threshold=16_384`:** chỉ là điểm khởi đầu cho thí nghiệm, **không phải giá trị tối ưu**.
7. **`volatile sink` và phép so expected:** đảm bảo chương trình có sử dụng kết quả, hạn chế JIT tối ưu bỏ công việc trong ví dụ đo. Đây vẫn chưa phải một benchmark đầy đủ.
8. **`shutdown()` và `awaitTermination()`:** quản lý vòng đời private pool; không để worker sống không cần thiết sau khi main kết thúc.

Đoạn code không cập nhật một biến tổng shared. Mỗi task lá tạo tổng cục bộ, rồi kết hợp sau `join`; do đó không cần `synchronized` hay `AtomicLong` cho phép cộng. Nếu thay bằng một `AtomicLong` dùng chung, các worker có thể phát sinh contention và benchmark một thuật toán khác.

## 4. Work-stealing, độ phức tạp và nguồn overhead

`ForkJoinPool` quản lý worker và các task có thể chia nhỏ. Khi một worker không còn việc, nó có thể lấy công việc sẵn có của worker khác (**work-stealing**). Điều này có ích khi các nhánh có lượng việc khác nhau và có đủ task song song.

| Khái niệm | Điều nên hiểu |
| --- | --- |
| `fork()` | Lên lịch một task có thể chạy song song; **không** cam kết nó chạy tức thì. |
| `compute()` | Thực hiện trên luồng hiện tại; thường tính một nửa tại chỗ. |
| `join()` | Nhận kết quả task con, chờ hoặc phối hợp xử lý theo cơ chế Fork/Join. |
| `invoke()` | Giao task gốc và lấy kết quả cuối cùng. |
| `getParallelism()` | Mức song song cấu hình cho pool, không khẳng định đã dùng đúng số core vật lý. |

Tổng số phép cộng vẫn là **O(N)**; cách chia cân bằng giúp mức sâu cây đệ quy khoảng `O(log(N / threshold))` khi `N > threshold`. Tổng thời gian có thêm chi phí chia vùng, khởi tạo task, lập lịch, `join`, đóng gói `Long`, và truy cập bộ nhớ. Do đó lý thuyết có nhiều worker không đồng nghĩa tăng tốc tuyến tính.

Phép cộng phần tử `int[]` là phép tính rất rẻ. Với mảng đủ lớn, thời gian thường bị giới hạn bởi **băng thông đọc bộ nhớ**, nơi các worker phải chia sẻ tài nguyên cache/bus/memory. Kết quả là 8 worker có thể không nhanh gấp đôi 4 worker. Ngược lại, mảng quá nhỏ có thể chậm rõ rệt vì overhead của Fork/Join lớn hơn chính phép cộng.

**Amdahl’s law** đưa ra một mô hình giới hạn: nếu tỷ lệ tuần tự là `s` và có `p` worker, tốc độ tăng lý thuyết xấp xỉ `1 / (s + (1-s)/p)`, còn chưa tính overhead. Trong bài tổng mảng, giới hạn băng thông và scheduler có thể làm kết quả thấp hơn mô hình này.

### Chi phí threshold

- **Threshold quá lớn:** cây có ít task, không khai thác được các worker; gần như tuần tự nhưng vẫn có chi phí pool.
- **Threshold quá nhỏ:** tạo rất nhiều task, tốn scheduling, fork/join và phân bổ object.
- **Threshold vừa phải:** mỗi lá đủ lớn để phí tạo task nhỏ so với việc duyệt mảng, đồng thời có đủ nhánh độc lập. Giá trị tốt nhất phụ thuộc N, CPU, JVM và workload.

Số lá xấp xỉ `N / threshold` khi cây cân bằng (ước lượng), không phải số worker. Hàng trăm task có thể được xử lý bởi bốn worker, không tạo hàng trăm thread.

## 5. Kiểm chứng tính đúng trước benchmark

Benchmark không có giá trị nếu một bên tính sai. Dùng baseline tuần tự cùng input để đối chiếu trước và trong các lần đo.

| Dữ liệu | Kết quả | Nội dung kiểm tra |
| --- | ---: | --- |
| `[]` | `0L` | Đoạn rỗng, điều kiện dừng. |
| `[7]` | `7L` | Một phần tử. |
| `[-3, 10, -2]` | `5L` | Không giả định toàn số dương. |
| `[Integer.MAX_VALUE, Integer.MAX_VALUE]` | `4_294_967_294L` | Tràn `int`, dùng `long`. |
| Kích thước bằng threshold | Giống tuần tự | Ranh giới task lá. |
| Kích thước bằng threshold + 1 | Giống tuần tự | Bắt đầu chia task. |
| Kích thước lẻ, không là lũy thừa 2 | Giống tuần tự | Không bỏ hoặc đếm trùng cuối mảng. |
| Mảng lớn, nhiều worker | Giống tuần tự | Không có shared mutable total. |

Khi viết test tự động, dùng `Future.get(timeout, unit)` hoặc timeout của test runner để tìm deadlock/livelock; đừng chỉ dùng `Thread.sleep` để đoán rằng một lịch chạy đã diễn ra. Với benchmark, dữ liệu phải chuẩn bị **ngoài vùng được đo**, không vừa sinh mảng vừa cộng rồi kết luận Fork/Join chậm.

**Không chạy benchmark cùng lúc với chương trình tạo tải lớn hoặc benchmark khác.** CPU throttling, JIT, GC và scheduling đều có thể làm sai khác kết quả. Nếu chạy trong container, ghi rõ hạn mức CPU và bộ nhớ.

## 6. So thời gian và đọc speedup

Chương trình `ArraySumForkJoinDemo` cung cấp phép đo học tập: 5 lần warmup, 11 lần đo, lấy median thời gian đơn vị mili giây. `System.nanoTime()` dùng để tính khoảng thời gian trôi qua, không phải đồng hồ ngày tháng.

Để hiểu tốc độ, dùng:

~~~text
speedup = time_sequential / time_forkjoin
efficiency ≈ speedup / số worker
~~~

Ví dụ **chỉ để minh họa cách diễn giải**, không phải kết quả đã đo:

| Cấu hình | Thời gian giả định | Kết luận nếu đo đáng tin |
| --- | ---: | --- |
| Sequential | 2,0 ms | Mốc baseline |
| Fork/Join 4 worker | 1,5 ms | Speedup 2,0/1,5 ≈ 1,33× |
| Fork/Join với threshold quá nhỏ | 3,0 ms | 2,0/3,0 ≈ 0,67×, nghĩa là chậm hơn |

Thời gian trên máy thật có thể hoàn toàn khác. `speedup > 1` cho thấy bản song song nhanh hơn trong điều kiện đo; `speedup < 1` cho thấy chậm hơn. `efficiency` là ước lượng hiệu quả theo mô hình, **không phải** số đo CPU utilization. Không nêu speedup mà bỏ qua độ dao động.

**Hạn chế của harness tự viết:** JIT có thể warm khác nhau, kết quả phụ thuộc thứ tự đo, JVM có thể tối ưu một số đường mã, thời gian tạo/đánh thức worker và tình trạng cache khác nhau, một tiến trình JVM không đủ thể hiện biến động giữa lần chạy. Để đánh giá nghiêm túc, dùng **JMH**.

## 7. Benchmark có warmup/fork bằng JMH

JMH (*Java Microbenchmark Harness*) là công cụ đo microbenchmark Java, hỗ trợ warmup, measurement, fork JVM và tiêu thụ kết quả benchmark. Bài này có thể xây một dự án **Maven riêng** để so tuần tự với Fork/Join trên đúng cùng input.

Cấu trúc:

~~~text
forkjoin-bench/
├── pom.xml
└── src/main/java/example/SumBenchmark.java
~~~

Đây là dự án có dependency JMH, vì vậy **không thể dùng `javac` độc lập chỉ với JDK** như ví dụ đầu tiên. Cần Maven có thể tải dependency.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>forkjoin-bench</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/SumBenchmark.java`:**

~~~java
package example;

import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.TearDown;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SumBenchmark {
    @Param({"100000", "1000000", "10000000"})
    public int size;

    @Param({"4096", "65536"})
    public int threshold;

    private int[] a;
    private ForkJoinPool pool;

    private static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int from;
        final int to;
        final int limit;

        Task(int[] a, int from, int to, int limit) {
            this.a = a;
            this.from = from;
            this.to = to;
            this.limit = limit;
        }

        @Override
        protected Long compute() {
            if (to - from <= limit) {
                long sum = 0L;
                for (int i = from; i < to; i++) {
                    sum += a[i];
                }
                return sum;
            }

            int mid = from + (to - from) / 2;
            Task left = new Task(a, from, mid, limit);
            Task right = new Task(a, mid, to, limit);
            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    private long sequential() {
        long sum = 0L;
        for (int value : a) {
            sum += value;
        }
        return sum;
    }

    private long parallel() {
        return pool.invoke(new Task(a, 0, a.length, threshold));
    }

    @Setup
    public void setup() {
        a = new int[size];
        for (int i = 0; i < size; i++) {
            a[i] = (i % 1_000) - 500;
        }
        pool = new ForkJoinPool(4);
        if (sequential() != parallel()) {
            throw new AssertionError("Incorrect parallel result");
        }
    }

    @TearDown
    public void tearDown() throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
        }
    }

    @Benchmark
    public long sequentialBenchmark() {
        return sequential();
    }

    @Benchmark
    public long forkJoinBenchmark() {
        return parallel();
    }
}
~~~

Chạy trong thư mục `forkjoin-bench`:

~~~bash
mvn -q -DskipTests package
java -jar target/forkjoin-bench-1.0.0.jar '.*SumBenchmark.*' -t 1
~~~

JMH sinh báo cáo `avgt` với đơn vị `ms/op` (**nhỏ hơn là tốt hơn**). Trong ví dụ này, JMH dùng **1 thread gọi phép đo** vì `-t 1`, nhưng `ForkJoinPool` riêng dùng **4 worker** để tính phép cộng. Thiết kế đó đo **một request tính tổng** của mỗi thuật toán. Muốn đo nhiều request đồng thời, phải thiết kế benchmark workload khác và công bố mức cạnh tranh cụ thể.

`@Setup` chuẩn bị mảng và private pool trước vòng đo, tránh tính cả chi phí tạo input vào từng phép cộng. Hai `@Benchmark` trả `long` để JMH có thể tiêu thụ kết quả, giảm nguy cơ JVM tối ưu xóa công việc. `@Fork(2)` chạy hai JVM fork, warmup/measurement dùng thông số đã khai báo.

**Lưu ý khi đọc kết quả:** threshold là tham số cho Fork/Join, nhưng JMH cũng chạy baseline tuần tự lặp lại theo từng giá trị threshold dù baseline không dùng nó. Khi so, ghép đúng **cùng size** và chỉ dùng một baseline tuần tự tương ứng; không nhân đôi dữ liệu thống kê.

## 8. Ma trận thí nghiệm nên thực hiện

| Tham số | Các mức gợi ý | Ý nghĩa |
| --- | --- | --- |
| `N` | 100.000; 1.000.000; 10.000.000 | Tìm kích thước đủ lớn để có lợi từ chia task. |
| `threshold` | 4.096; 16.384; 65.536 | Đánh đổi số task với khả năng song song. |
| Pool parallelism | 1; 2; 4; 8 nếu máy cho phép | Tìm mức song song có ích trên máy. |
| JVM fork | Ít nhất 2 | Nhận diện chênh lệch giữa lần chạy độc lập. |
| Warmup/measurement | Ví dụ 3/5 iteration, mỗi iteration 1 giây | Giảm ảnh hưởng chạy nguội và nhiễu. |

Mẫu JMH trên đã dùng nhiều `size` và threshold. Muốn thử nhiều số worker, thêm `@Param({"1","2","4","8"}) public int workers;` rồi dùng `new ForkJoinPool(workers)` trong `setup()`; thay đổi này sẽ làm tăng số tổ hợp benchmark cần chạy. Cần ghi cấu hình CPU thực và tránh oversubscription khi chạy trong container có quota.

Trong báo cáo ghi **JDK version, CPU, core/threads, RAM, OS, giới hạn container/VM, JMH version, N, threshold, parallelism, score và error bars**. Kết luận tốc độ từ kết quả thực tế, không lấy một giá trị timing của ví dụ hoặc một lần chạy ngẫu nhiên làm căn cứ.

### Khi nào Fork/Join có thể nhanh, khi nào có thể chậm?

Fork/Join có cơ hội tốt khi đầu vào đủ lớn, lá có lượng tính toán đáng kể, các nhánh độc lập và máy còn tài nguyên xử lý. Nó dễ chậm khi:

- Dữ liệu quá nhỏ: overhead task và pool lớn so với vòng for.
- Threshold quá nhỏ: task quá nhiều, tăng chi phí fork/join/scheduling.
- Threshold quá lớn: không đủ task để worker cùng xử lý.
- Bộ nhớ đã bão hòa: thêm worker không tăng băng thông đọc `int[]`.
- CPU ít core hoặc đang bị hạn chế bởi workload khác.
- Benchmark tính cả phân bổ mảng, tạo pool hoặc GC không đồng đều.

Mỗi kết quả phải giải thích bằng đặc tính workload và điều kiện máy, không chỉ bằng số worker.

## 9. Các lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `int sum` ở lá | Tràn tổng khi nhiều số lớn. | Cộng vào `long` ngay từ đầu. |
| Chia `[from,mid]` và `[mid,to]` | Đếm trùng vị trí mid. | Dùng hai đoạn `[from,mid)` và `[mid,to)`. |
| Không kiểm tra `threshold > 0` | Có thể đệ quy vô hạn trên đoạn 1 phần tử. | Kiểm tra threshold đầu vào và điều kiện lá. |
| Tạo task cho từng phần tử | Overhead scheduling lớn. | Gom đủ phần tử mỗi lá, tune threshold. |
| Fork cả hai nhánh rồi join ngay | Đưa nhiều task vào lịch không cần thiết. | Fork một nhánh, compute nhánh kia, rồi join. |
| Dùng biến tổng chung với `AtomicLong` hoặc lock | Contention/race, sai mục tiêu divide-and-conquer. | Task trả tổng cục bộ rồi kết hợp. |
| Mảng bị ghi đồng thời khi đang đọc | Kết quả không nhất quán. | Giữ snapshot hoặc dữ liệu read-only đến khi tính xong. |
| Tạo pool mới trong mỗi lần benchmark | Đo cả chi phí tạo worker. | Tạo pool trước vùng đo và tái sử dụng. |
| Dùng common pool có workload khác | Kết quả bị nhiễu. | Private pool hoặc ghi rõ sự chia sẻ. |
| Không kiểm tra tổng trước khi đo | “Nhanh” nhưng có thể sai. | So với baseline, test empty/overflow/odd N. |
| Tạo dữ liệu trong vòng đo | Đo cả setup, không chỉ tính tổng. | Chuẩn bị input trước benchmark. |
| Xem một phép `nanoTime()` là kết luận | JIT/GC/OS gây nhiễu lớn. | Dùng JMH, nhiều iteration/fork và báo sai số. |

## 10. Bài tập mở rộng

**Bài A — Mảng lẻ:** thử `N=1_000_003` và thay giá trị `expected` bằng kết quả `sequentialSum(data)` trước khi so Fork/Join. Vì sao không được giữ `-500_000L` sau khi đổi N? Kiểm chứng các task không bỏ phần tử cuối.

**Bài B — Ngưỡng phân nhánh:** đo `N=100_000` và `N=10_000_000` với threshold 1.024, 4.096, 16.384, 65.536, 262.144. Lập bảng JMH score và độ dao động. Giải thích vì sao tối ưu cho N này chưa chắc tối ưu cho N khác.

**Bài C — Một worker:** chạy `new ForkJoinPool(1)` và so với vòng lặp tuần tự. Phân tích overhead của task/đệ quy khi gần như không có tính song song.

**Bài D — Tổng giá trị lớn:** thử `int[] {Integer.MAX_VALUE, Integer.MAX_VALUE, -1}`. Kết quả đúng là `4_294_967_293L`. Đổi `long sum` thành `int sum` trong một bản sao thử nghiệm để thấy sai số do overflow; khôi phục mã đúng sau test.

**Bài E — So một API có sẵn:** thêm `Arrays.stream(data).asLongStream().parallel().sum()`. Nó thường chạy trên common Fork/Join pool, có cấu hình và mức tranh chấp khác private pool; ghi rõ sự khác biệt khi so, đừng coi mọi phép “parallel” là cùng thuật toán và cùng worker count.

## 11. Checklist nghiệm thu

- [ ] Có vòng lặp tuần tự và `RecursiveTask<Long>` Fork/Join; hai kết quả đúng bằng nhau.
- [ ] Đoạn `[from,to)` không trùng/khuyết; threshold dương; xử lý được mảng rỗng, mảng lẻ và tràn `int`.
- [ ] Các task chỉ đọc mảng, mỗi lá tính tổng cục bộ, không có shared mutable total.
- [ ] Sử dụng `fork()`/`compute()`/`join()` đúng cách và đóng pool khi xong.
- [ ] Dữ liệu được chuẩn bị trước benchmark; kết quả được sử dụng/kiểm tra.
- [ ] Đo nhiều N, threshold và số worker; có warmup, nhiều iteration; ưu tiên JMH nếu cần kết luận hiệu năng.
- [ ] Có ghi cấu hình máy/JDK và sai số; không mặc định Fork/Join luôn nhanh hơn.

**Điểm rút ra:** Fork/Join giúp chia bài toán lớn thành các task có thể chạy song song rồi ghép kết quả, nhưng với tổng mảng, bản tuần tự rất tối ưu và bộ nhớ có thể thành nút thắt. Khả năng đánh giá đúng bài này đến từ **chứng minh tính đúng, đo có kiểm soát và giải thích khi nào Fork/Join thắng hoặc thua**.