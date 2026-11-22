# Thiết kế so sánh JIT có kết quả được sử dụng và dữ liệu đại diện

## 1. Mục tiêu và ý nghĩa trong JIT phân tầng

Trong HotSpot JVM hiện hành, **JIT phân tầng (tiered compilation)** kết hợp chạy thông dịch, biên dịch nhanh để thu thập hồ sơ thực thi (thường liên quan C1), và biên dịch tối ưu hơn (thường liên quan C2). Mã chạy càng lâu, nhánh được đi qua và kiểu dữ liệu quan sát được có thể khiến JVM **thay đổi mã máy ngay trong quá trình thử nghiệm**.

Điều đó tạo ra một bẫy phổ biến: hai đoạn Java nhìn có vẻ làm cùng một phép tính, nhưng cách viết benchmark khiến JVM loại bỏ phép tính, tính trước hằng số hoặc tối ưu theo dữ liệu nhân tạo. Kết quả đo rất nhanh song **không phản ánh công việc thực sự của ứng dụng**.

Bài này hướng dẫn thiết kế một phép so sánh có thể tin cậy hơn:

1. **Công việc phải có kết quả được sử dụng** để JIT không thể hợp pháp loại bỏ toàn bộ tính toán.
2. **Dữ liệu đầu vào phải đại diện** cho kích thước, tỷ lệ nhánh, cấu trúc và cách truy cập của bài toán thật.
3. **Hai phương án phải được kiểm tra đúng cùng ngữ nghĩa** và chạy dưới điều kiện JVM, tài nguyên, warmup, measurement tương đương.
4. **Kết luận phải dựa trên nhiều lần đo**, hiểu vai trò tiered compilation, GC và độ biến thiên hệ thống.

Ví dụ dùng **Java 17+** và **OpenJDK Java Microbenchmark Harness (JMH)**, công cụ benchmark JVM hiện hành. Không sử dụng cờ/tiện ích JIT nội bộ đã lỗi thời.

## 2. Vì sao benchmark Java dễ đo sai?

### 2.1. Dead-code elimination (DCE): kết quả không dùng thì công việc có thể biến mất

Xem đoạn mã *minh họa sai* dưới đây:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    int result = (i * 31) ^ (i >>> 3);
    // result không thoát khỏi vòng lặp và không ảnh hưởng trạng thái quan sát được.
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Đoạn trên là **minh họa nằm trong một phương thức**, không phải chương trình độc lập. Dù nguồn có một triệu vòng lặp, Java compiler/JIT có thể nhận thấy giá trị `result` không được dùng; phép tính có thể bị giản lược hoặc xóa hoàn toàn. Đồng hồ vẫn đo khoảng thời gian, nhưng khoảng đó **không còn nhất thiết chứa công việc cần so sánh**.

Ngay cả với mã có `return`, cần nghĩ về ngữ cảnh: nếu toàn bộ đầu vào là hằng số biết trước, JVM có thể **constant fold**, loop optimize hoặc chuyên biệt hóa code cho trường hợp quá dễ, thay vì xử lý dữ liệu thực. Một lần chạy có kết quả “0 ns/op” hoặc cực nhỏ là tín hiệu cần kiểm tra, không tự động chứng minh thuật toán nhanh phi thường.

**Nguyên tắc cốt lõi:** phép tính phải tạo ra **giá trị quan sát được** từ những đầu vào phù hợp. Đồng thời đừng tạo side effect đắt đỏ chỉ nhằm ngăn DCE, vì sẽ chuyển benchmark thành đo side effect đó.

### 2.2. Constant folding, inlining và profile đặc thù

Ví dụ `Math.max(10, 20)` không phải bài kiểm tra hữu ích để suy ra hiệu năng phân nhánh trên dữ liệu sản xuất; JVM có thể xác định kết quả là `20` ngay khi tối ưu. JIT cũng có thể inline lời gọi phương thức, loại nhánh không xảy ra, hoặc dùng profile để tối ưu đường đi thường gặp.

**Inlining là hành vi bình thường và nên được cho phép** nếu ứng dụng thật cũng chạy trong điều kiện ấy. Điều cần tránh là một benchmark chỉ cung cấp **một bộ dữ liệu hằng bất thường**, khiến profile không đại diện. Không nên tắt hàng loạt tối ưu JIT để “công bằng”: nếu không có mục tiêu phân tích riêng, bạn sẽ đo một JVM khác với JVM vận hành.

### 2.3. Warmup và tiered compilation

Thời gian chạy phương thức có thể thay đổi vì:

- Lần đầu chạy qua interpreter, khởi tạo lớp, liên kết phương thức, nạp dữ liệu.
- JVM thu thập thông tin nhánh/kiểu và biên dịch sang các mức tối ưu khác nhau.
- Code được biên dịch lại, bị **deoptimize** khi giả định profile không đúng, rồi có thể được tối ưu trở lại.
- JIT compiler threads tranh CPU với workload; GC, thread scheduling, thermal throttling cũng ảnh hưởng.

Vì thế, một phép đo `System.nanoTime()` thực hiện đúng một lần thường trộn lẫn startup, warmup và steady state. JMH giải quyết phần lớn việc dựng vòng chạy, warmup, measurement, fork JVM và tiêu thụ kết quả đo. Nó **không tự sửa một bài toán benchmark thiết kế sai**.

## 3. Kết quả phải được sử dụng đúng cách

JMH cung cấp hai cách phổ biến để kết quả không trở thành dead code.

### 3.1. Trả về kết quả từ phương thức có @Benchmark

```java
@Benchmark
public long countMatches() {
    return count(data);
}
```

Đây là **đoạn minh họa JMH**, giả định lớp có trường `data` và hàm `count(...)`; ví dụ đầy đủ ở phần 5. JMH tạo harness xung quanh phương thức và **tiêu thụ giá trị trả về** để kết quả có tác dụng quan sát được. Khi benchmark chỉ tạo một kết quả, `return` thường là lựa chọn đơn giản nhất.

### 3.2. Dùng Blackhole khi có nhiều kết quả

```java
@Benchmark
public void evaluateBoth(Blackhole blackhole) {
    blackhole.consume(firstOperation(input));
    blackhole.consume(secondOperation(input));
}
```

Đây là đoạn **minh họa** có `Blackhole` từ `org.openjdk.jmh.infra.Blackhole` và các hàm chưa định nghĩa. `Blackhole.consume(...)` tạo một điểm tiêu thụ để JIT không thể coi kết quả là hoàn toàn vô dụng. Nhưng nếu muốn **so sánh firstOperation với secondOperation**, không được dùng chính `evaluateBoth` làm số đo riêng cho hai thuật toán: hãy viết **hai @Benchmark độc lập**, mỗi phương thức dùng kết quả của thuật toán tương ứng.

**Không dùng thay thế tùy tiện:**

- `System.out.println(result)` trong đường đo: làm chi phí I/O chi phối kết quả.
- Ghi kết quả vào một trường `volatile` mỗi vòng chỉ để ngăn DCE: chi phí memory ordering/ghi nhớ có thể đáng kể; chỉ dùng nếu đó là hành vi thật cần benchmark.
- Tạo thread, kết nối DB, tạo ngẫu nhiên hay gọi `Thread.sleep(...)` **bên trong** đoạn benchmark nếu chúng không phải phần mục tiêu đang đo.
- `Blackhole` không phải phép màu bảo đảm tính thực tế; nó chỉ giải quyết một nhóm vấn đề loại bỏ công việc.

## 4. Dữ liệu đại diện: biến phụ thuộc quan trọng hơn số vòng lặp

Một benchmark tìm kiếm, lọc, parse hay phân nhánh phụ thuộc rất mạnh vào **đặc tính dữ liệu**. Với phép đếm số nguyên `value >= 50`, hãy cân nhắc:

| Chiều của dữ liệu | Tình huống cần thử | Điều gì ảnh hưởng JIT và kết quả? |
| --- | --- | --- |
| **Kích thước** | 1.024 phần tử so với 65.536 phần tử hoặc cỡ thực tế | Cache locality, traversal cost, độ nhạy với overhead phương thức/Stream. |
| **Tỷ lệ nhánh** | Khoảng 50% đúng, 90% đúng, 10% đúng | Branch predictor, profile của HotSpot và kết quả biên dịch. |
| **Phân phối giá trị** | Dữ liệu đều/ngẫu nhiên, dữ liệu phân cụm, dữ liệu đã sắp xếp | Tính dự đoán của nhánh, truy cập bộ nhớ, tiền điều kiện thuật toán. |
| **Tỷ lệ trường hợp biên** | Array rỗng, giá trị sát ngưỡng, null/Unicode nếu áp dụng | Đường xử lý đặc biệt và kiểm tra điều kiện. |
| **Tính biến đổi theo thời gian** | Dataset ổn định hay theo từng lô thay đổi | Profile dễ trở nên quá chuyên biệt; hiệu ứng cold/hot cache. |
| **Số thread** | 1 thread, số thread thực tế, có tranh chấp | Scheduler, contention, false sharing, GC và cấu trúc dữ liệu dùng chung. |

**Dữ liệu đại diện không đồng nghĩa ngẫu nhiên hoàn toàn.** Nếu production thường có 90% bản ghi thỏa điều kiện, chỉ dùng bộ test 50/50 có thể xếp hạng hai cách cài đặt khác với thực tế. Nếu production quét mảng đã sắp xếp, dữ liệu ngẫu nhiên hoàn toàn cũng không đại diện. Hãy mô tả rõ tỷ lệ, kích thước, thứ tự và chế độ đọc/ghi được mô phỏng.

### 4.1. Sinh dữ liệu ngoài thời gian đo

Với JMH, dùng `@State` và `@Setup(Level.Trial)` để tạo dữ liệu **trước khi đo**, miễn là việc sinh dữ liệu không phải thao tác kinh doanh cần so sánh. Cùng một `@Param` và seed cố định giúp hai thuật toán nhận dữ liệu tương đương. Sinh `new Random()` hay `SplittableRandom.nextInt()` trong `@Benchmark` sẽ vô tình đo cả bộ sinh số ngẫu nhiên.

**Seed cố định giúp tái lập**, nhưng không tự tạo mẫu đại diện; nên dùng nhiều tỷ lệ và kích thước, hoặc dữ liệu đã ẩn danh từ tập thực được phép sử dụng. Tránh để benchmark dùng tập dữ liệu dễ dàng bị JIT coi như hằng số compile-time.

### 4.2. Đọc cùng dữ liệu cũng có giới hạn

Nếu mỗi invocation luôn quét lại một mảng nhỏ, dữ liệu có thể nằm trong CPU cache. Đây là phép đo hợp lệ cho **working set nhỏ, truy cập lặp**, nhưng không dự đoán được chi phí khi production đọc dữ liệu lớn hơn cache, tạo object graph, hoặc gặp I/O. Hãy có các bộ data size phản ánh working set thật và định nghĩa scope rõ: đo riêng thuật toán xử lý dữ liệu đã ở bộ nhớ, hay đo cả việc nạp/sinh dữ liệu?

## 5. Ví dụ JMH hoàn chỉnh trên Java 17+: so sánh loop và Stream

Ví dụ so sánh **vòng for** với **IntStream** khi đếm số phần tử đạt điều kiện `value >= 50`. Đây là hai cách cài đặt cùng một phép tính; JIT có thể tối ưu chúng khác nhau. Toàn bộ kết quả được `return` để JMH tiêu thụ; đầu vào tạo ngoài khoảng đo và được kiểm tra đúng ngữ nghĩa.

### 5.1. Tạo dự án benchmark

Cần JDK 17+ và Maven. Trong một thư mục trống **không nằm trong một dự án Maven đang chạy**, dùng archetype JMH hiện hành `1.37` (phiên bản có trên Maven Central):

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=example.bench -DartifactId=jit-compare -Dversion=1.0
```

Dự án mới là `jit-compare/`. Archetype tạo sẵn cấu hình **JMH annotation processor**, code sinh tự động cho harness và phần đóng gói `target/benchmarks.jar`. Chỉ thêm `jmh-core` vào một dự án bất kỳ mà không chạy annotation processor sẽ **không đủ** để JMH hoạt động đúng.

Tạo tệp `jit-compare/src/main/java/example/bench/RepresentativeBench.java` sau. Nếu archetype tạo một benchmark mẫu khác, có thể bỏ benchmark mẫu ấy khỏi tập đo để kết quả chỉ chứa hai phương án đang nghiên cứu.

### 5.2. Mã nguồn

```java
package example.bench;

import java.util.Arrays;
import java.util.SplittableRandom;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 4, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 6, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
@Threads(1)
public class RepresentativeBench {
    @Param({"1024", "65536"})
    public int size;

    @Param({"balanced", "mostlyPass", "mostlyFail"})
    public String distribution;

    private int[] data;

    @Setup(Level.Trial)
    public void prepare() {
        SplittableRandom random = new SplittableRandom(2026L + size);
        data = new int[size];

        for (int i = 0; i < size; i++) {
            int bucket = random.nextInt(100);
            if ("mostlyPass".equals(distribution)) {
                data[i] = bucket < 90
                        ? 50 + random.nextInt(50)
                        : random.nextInt(50);
            } else if ("mostlyFail".equals(distribution)) {
                data[i] = bucket < 10
                        ? 50 + random.nextInt(50)
                        : random.nextInt(50);
            } else {
                data[i] = bucket;
            }
        }

        // Kiểm tra cùng ngữ nghĩa trước khi JMH bắt đầu đo.
        if ((long) countLoop(data) != countStream(data)) {
            throw new IllegalStateException("Hai thuật toán trả kết quả khác nhau");
        }
    }

    private static int countLoop(int[] values) {
        int count = 0;
        for (int value : values) {
            if (value >= 50) {
                count++;
            }
        }
        return count;
    }

    private static long countStream(int[] values) {
        return Arrays.stream(values)
                .filter(value -> value >= 50)
                .count();
    }

    @Benchmark
    public int loop() {
        return countLoop(data);
    }

    @Benchmark
    public long stream() {
        return countStream(data);
    }
}
```

### 5.3. Giải thích vì sao ví dụ này có giá trị học tập

1. `@State(Scope.Thread)` cấp dữ liệu riêng cho thread chạy benchmark, tránh vô tình đo đồng bộ hóa giữa các worker. Khi cần benchmark contention thì đó là **thí nghiệm khác**, có thể dùng shared state và số thread tương ứng.
2. `@Param` tạo **6 bộ dữ liệu** từ hai kích thước × ba phân phối. JMH chạy hai phương án trên từng cấu hình; mọi dữ liệu được tạo bằng seed tái lập.
3. `@Setup(Level.Trial)` được thực hiện ngoài phép đo. Chi phí cấp phát mảng, tạo ngẫu nhiên và kiểm tra kết quả không bị tính thành chi phí phương pháp `loop` hay `stream`.
4. `countLoop` và `countStream` được kiểm tra cùng **kết quả số học**. Một thuật toán có kết quả khác không thể đem so điểm tốc độ để kết luận “nhanh hơn”.
5. `@Benchmark` **trả về** kết quả. Harness do JMH sinh sẽ tiêu thụ giá trị; JIT khó hợp pháp loại bỏ toàn bộ vòng quét như khi benchmark là `void` và bỏ kết quả.
6. `@Warmup` cho JVM thời gian chạy, thu thập profile và có thể biên dịch nhiều tầng. `@Measurement` chỉ số đo sau warmup vào báo cáo. `@Fork(3)` tạo nhiều tiến trình JVM riêng, giúp phát hiện chênh lệch do trạng thái JIT/GC và giảm phụ thuộc vào một lần chạy.
7. `@BenchmarkMode(Mode.AverageTime)` đo **thời gian trung bình mỗi invocation**. Đơn vị `MICROSECONDS` có nghĩa là microsecond trên mỗi phép gọi `@Benchmark` (mỗi phép gọi ở đây quét toàn bộ mảng), **không phải mỗi phần tử**.

**Giới hạn cố ý của ví dụ:** mỗi invocation duyệt cùng một mảng chỉ đọc; dữ liệu có thể nằm trong cache và nhánh có profile ổn định. Đó là workload **in-memory scan**; không thể dùng thẳng kết quả để phỏng đoán một pipeline có DB, mạng, cấp phát đối tượng, dữ liệu thay đổi liên tục hoặc xử lý file.

### 5.4. Chạy thực tế

```bash
cd jit-compare
mvn clean verify
java -jar target/benchmarks.jar RepresentativeBench -wi 4 -i 6 -f 3 -prof gc -rf json -rff jmh-results.json
```

Tùy archetype, `target/benchmarks.jar` là JAR tự chứa JMH. Lệnh trên dùng các pha warmup/measurement, chạy fork độc lập và bổ sung `-prof gc` để quan sát phân bổ/GC; `-rf json -rff ...` lưu số đo ở định dạng JSON, thuận tiện so sánh sau này.

Lệnh khởi đầu nhẹ để **kiểm tra cấu hình/mã có chạy được** (chưa đủ để kết luận hiệu năng):

```bash
java -jar target/benchmarks.jar RepresentativeBench -wi 1 -i 1 -f 1 -w 1s -r 1s
```

**Không có stdout số đo cố định.** JMH in bảng có tên benchmark, các giá trị `size`/`distribution`, số vòng đo, `Score`, `Error` và đơn vị như `us/op`; con số thực phụ thuộc CPU, JVM, hệ điều hành và tải máy. Ví dụ **chỉ mô tả cấu trúc cột**, không phải kết quả máy đo:

```text
Benchmark                     (distribution)  (size)  Mode  Cnt  Score  Error  Units
RepresentativeBench.loop      balanced         1024   avgt   ...    ...    ...  us/op
RepresentativeBench.stream    balanced         1024   avgt   ...    ...    ...  us/op
```

Đừng tự điền một tốc độ “chuẩn” cho các dòng này. Khi so sánh, lọc hai dòng có **cùng distribution, size, unit, JDK và điều kiện chạy**, sau đó xem khoảng sai số và tính lặp lại qua nhiều lần chạy.

### 5.5. Diễn giải kết quả cẩn thận

Giả sử ở cùng một cấu hình đo, `loop` nhanh hơn `stream` một chút. Kết quả **chỉ hỗ trợ** nhận định “đối với phép đếm này, bộ dữ liệu này và môi trường đo này, vòng for có thời gian trung bình thấp hơn trong thử nghiệm”. Nó không chứng minh `Stream` luôn chậm hơn trong ứng dụng Java, cũng không chắc rằng chênh lệch có ý nghĩa nếu sai số hai phía chồng lấn mạnh.

Dữ liệu size = 1.024 có thể chịu nhiều tác động từ overhead pipeline; ở size = 65.536, chi phí quét mảng và bộ nhớ chiếm tỷ trọng lớn hơn. Phân phối balanced/mostlyPass/mostlyFail có thể thay đổi thứ hạng. **Nếu thứ hạng thay đổi theo dữ liệu**, đó là phát hiện đáng quan tâm và cần đối chiếu dữ liệu production, chứ không phải lý do chọn một lần đo thuận lợi nhất.

## 6. Thực nghiệm về kết quả bị bỏ đi

Để thấy lỗi benchmark, xét một đoạn `@Benchmark` sai (mã **minh họa**, không thêm vào benchmark chính):

```java
@Benchmark
public void discardedResult() {
    countLoop(data); // Không return, không Blackhole, không tác dụng phụ.
}
```

Ở đây JIT có thể bỏ phép đếm. Thời gian của phương thức có thể tiến gần chi phí gọi harness hay chi phí rất nhỏ không còn thể hiện thuật toán.

Hai cách sửa, khi đo **một** phép đếm:

```java
@Benchmark
public int returnedResult() {
    return countLoop(data);
}

@Benchmark
public void consumedResult(Blackhole blackhole) {
    blackhole.consume(countLoop(data));
}
```

Đây là **đoạn minh họa bên trong lớp benchmark có sẵn**; cần import `org.openjdk.jmh.infra.Blackhole` khi sử dụng. Với chỉ một giá trị, hãy ưu tiên `return`. Khi muốn biết riêng chi phí của từng thuật toán, giữ các benchmark độc lập; không cộng chi phí hai thuật toán vào cùng một lần đo.

**Lưu ý:** không nên kỳ vọng phiên bản `discardedResult` luôn trả về đúng 0.000 us/op trên mọi JVM; JIT có thể không loại hết vì các điều kiện môi trường hoặc mức biên dịch hiện tại. Vấn đề cốt lõi là **nội dung được đo không có hợp đồng bảo đảm thực hiện phép tính mong muốn**.

## 7. So sánh có kiểm soát trong bối cảnh JIT phân tầng

### 7.1. Đặt câu hỏi đo trước

Một giả thuyết đo tốt:

> Với mảng `int[]` có 65.536 phần tử và tỷ lệ `value >= 50` khoảng 90%, ở trạng thái đã warmup trên JDK 21/HotSpot, phép đếm bằng vòng `for` và `IntStream.filter().count()` có chênh lệch thời gian trung bình hay không?

Giả thuyết kém rõ: “Stream có nhanh hơn Java 7 không?” vì không xác định JVM nào, thuật toán gì, kích thước đầu vào, metric và điều kiện chạy.

### 7.2. Khóa các yếu tố so sánh

Giữ tương đương giữa hai phương án:

- Cùng JDK **distribution/vendor, version, architecture, heap, GC và JVM flags**; ghi nhận `java -version`.
- Cùng máy/CPU, số logical cores và chính sách CPU/cgroup; giảm nhiễu từ tải nền, nhiệt độ, power management, laptop tiết kiệm điện hoặc hypervisor.
- Cùng dữ liệu đầu vào, cách xác nhận đúng, số thread, đơn vị phép đo và số phép gọi.
- Cùng chiến lược warmup/measurement/forks, trừ khi **chính yếu tố đó** là biến đang thử.
- Nếu một phương án tạo thêm object còn phương án kia không, đó có thể là khác biệt hợp lệ về chi phí thuật toán, nhưng phải quan sát allocation/GC để diễn giải.

Không sửa nhiều biến cùng lúc rồi khẳng định chỉ do JIT tiering. Nếu thử `-XX:TieredStopAtLevel=1` hoặc `-XX:-TieredCompilation` trong một thí nghiệm nghiên cứu riêng trên HotSpot, hãy gọi rõ đó là **cấu hình JVM khác**, không phải tối ưu mặc định đề xuất cho sản phẩm. Các mức compiler, heuristic và tác động của flags có thể khác theo phiên bản và implementation.

### 7.3. Warmup đủ dài nhưng có căn cứ

Chọn warmup nhiều iteration và xem độ ổn định qua các vòng. Việc tiered compilation được bật mặc định trên HotSpot server JVM không có nghĩa một phương thức chắc chắn đạt tối ưu C2 đúng sau một số vòng cố định. Một phương thức quá “nguội”, một invocation quá nhỏ, code cache hay tải CPU đều có thể làm trạng thái biên dịch khác nhau.

Nếu quan tâm **startup/cold performance**, hãy định nghĩa một benchmark riêng về khởi động hoặc đo luồng chạy thực tế có startup: không dùng benchmark đã warmup để suy ra cold-start latency. Ngược lại, nếu cần peak steady-state throughput, đừng trộn số đo interpreter lúc khởi động với số đo sau khi JIT tối ưu.

### 7.4. Fork, iteration và thống kê

- **Iteration** gom nhiều lời gọi trong một khoảng đo; JMH dùng chúng để ước lượng score và độ biến thiên.
- **Fork** chạy workload ở tiến trình JVM riêng, tránh trộn profile/GC/JIT state từ các lần chạy trước trong cùng tiến trình.
- Chạy nhiều fork/lần đo để xem kết quả có ổn định giữa JVM độc lập không. Một score với error nhỏ không tự bảo đảm môi trường representative.
- Đọc `AverageTime` như thời gian trung bình mỗi invocation, `Throughput` như số thao tác mỗi đơn vị thời gian. Chỉ so cùng mode/unit.
- Nếu quan tâm **tail latency**, có thể dùng `Mode.SampleTime` trong JMH để lấy phân bố thời gian invocation, nhưng độ trễ p99 của request thật vẫn cần tracing/metrics production, vì microbenchmark không mô phỏng hàng đợi và network.

Với chênh lệch rất nhỏ, đừng vội gọi là cải thiện: so sánh nhiều vòng, kiểm tra noise, xem chi phí triển khai/bảo trì và đo lại trong workload tích hợp.

## 8. Quan sát JIT, allocation và các yếu tố gây nhiễu

### 8.1. JMH profiler và JVM diagnostics

`-prof gc` đi kèm JMH giúp quan sát các thông tin như allocation rate và GC count/time có sẵn cho profiler. Nếu một phương án tạo nhiều object hơn, phần GC có thể ảnh hưởng kết quả hoặc gây biến thiên ngoài dự kiến.

Để quan sát quá trình biên dịch trên **HotSpot**, có thể chạy một **thí nghiệm riêng** với `-XX:+PrintCompilation` trong JVM fork:

```bash
java -jar target/benchmarks.jar RepresentativeBench -wi 4 -i 4 -f 1 -jvmArgs "-XX:+PrintCompilation"
```

Log compilation chỉ cho biết activity của JIT trong lần chạy; không chứng minh một benchmark đúng ngữ nghĩa hay representative. Ghi log và diagnostic có thể tác động đến timing nên dùng cho chẩn đoán, rồi chạy lại phép đo **không bật log nặng**. Các công cụ như Java Flight Recorder (JFR), `jcmd` và profiler CPU có thể bổ sung bằng chứng khi cần.

### 8.2. Tiered C1/C2 và deoptimization

Ở HotSpot, tiered compilation có thể đi từ interpreter sang các dạng compiled code khác nhau; dữ liệu profile giúp JIT inline, chuyên biệt hóa đường đi nóng và tối ưu nhánh. Nếu sau warmup workload bất ngờ đổi từ **mostlyPass** sang **mostlyFail** trong cùng một tiến trình, code được tối ưu theo profile cũ có thể hoạt động khác, thậm chí bị deopt/recompile.

Do đó hãy xác định câu hỏi đo:

- Nếu production **ổn định theo một phân phối**, tách scenario theo `@Param` và đo steady-state cho từng phân phối là hợp lý.
- Nếu production **thường chuyển pha**, phải thiết kế một benchmark khác cố ý thay đổi dữ liệu/profile theo pha và đo chi phí chuyển pha; benchmark hiện tại chưa mô phỏng điều ấy.
- Nếu production là ứng dụng nhiều service/thread đồng thời, microbenchmark một thread **không** thay thế stress/load test trong hệ thống đầy đủ.

### 8.3. Những công việc không nên gộp vô ý vào benchmark

| Thứ có thể bị đo nhầm | Dấu hiệu | Cách kiểm soát |
| --- | --- | --- |
| Dựng dữ liệu | `new int[...]`, `Random.nextInt` chạy trong `@Benchmark` dù chỉ muốn đo filter | Đưa vào `@Setup`; chỉ đưa trở lại khi creation là phần yêu cầu. |
| Logging/console | `println` mỗi invocation | Kiểm tra ngoài đường đo; return/Blackhole để dùng kết quả. |
| Kiểm tra correctness | Assert hoặc kiểm thử nhiều thuật toán mỗi invocation | So sánh ngoài vùng đo, ví dụ trong `@Setup` hoặc test riêng. |
| Khởi động lớp/JVM | `nanoTime` chỉ đo lần chạy đầu | Warmup JMH; cold-start là bài kiểm tra khác. |
| Khác biệt semantics | Một thuật toán trả số đếm, thuật toán khác chỉ kiểm tra tồn tại | Xác minh cùng hợp đồng đầu vào/đầu ra trước khi đo. |
| Input quá nhỏ | Chi phí harness/invocation chiếm đa số | Tăng kích thước công việc hoặc dùng cách batching phù hợp, công bố đơn vị đo. |
| Contention, GC hoặc CPU throttling | Score dao động theo tải/threads/forks | Theo dõi profiler/host, giảm nhiễu, test trên tải representative. |
| JIT triệt tiêu computation | `@Benchmark void` không có side effect hay giá trị được dùng | `return` kết quả hoặc `Blackhole.consume(...)`. |

## 9. Quy trình làm bài và báo cáo kết quả

Một quy trình có thể lặp lại:

1. **Viết giả thuyết** theo workload thật: phương án A/B, dữ liệu, JVM, metric và kỳ vọng.
2. **Chứng minh cùng chức năng:** unit test cho edge cases, so sánh output, kiểm tra ngoại lệ/tác dụng phụ.
3. **Bảo đảm kết quả được dùng:** `return` hoặc `Blackhole`, không dùng println/volatile vô tội vạ.
4. **Thiết kế dữ liệu:** chọn kích thước, tỷ lệ nhánh và phân phối đại diện; xác định seed/corpus, tạo ngoài phạm vi đo nếu phù hợp.
5. **Đo bằng JMH:** state đúng scope, warmup đủ, measurement/fork độc lập; chạy smoke test rồi mới đo nghiêm túc.
6. **Quan sát nhiễu:** JIT, GC, allocation, CPU, scheduling; lưu JVM version và cấu hình.
7. **Diễn giải có điều kiện:** so sánh cùng tham số, score/error/phân phối và số lần chạy; không nâng microbenchmark thành kết luận production.
8. **Kiểm tra ở ứng dụng thật:** latency p95/p99, throughput, CPU, memory/GC và trải nghiệm người dùng trước khi chọn tối ưu.

Mẫu báo cáo nên ghi:

| Trường | Nội dung cần công bố |
| --- | --- |
| Đối tượng so sánh | Tên phương thức, ngữ nghĩa và version code |
| Dữ liệu | Nguồn, seed, kích thước, phân phối, tỷ lệ nhánh, cách chuẩn bị |
| Môi trường | JDK vendor/version, CPU, OS, vCPU/quota, bộ nhớ, cờ JVM |
| Phương pháp | JMH version, mode, time unit, thread count, warmup, measurement, forks |
| Kết quả | Score và error theo từng `@Param`, số chạy, dữ liệu thô/JSON |
| Ngữ cảnh | Allocation/GC, compiler warmup, sai số, outlier, hạn chế |
| Kết luận | Phương án phù hợp cho workload **cụ thể** nào, cần xác nhận thêm ở đâu |

## 10. Bài tập tự kiểm tra

1. Xóa `return` khỏi benchmark `loop` (tạo hàm benchmark `void` chỉ gọi `countLoop(data)`) và đo thử. Giải thích vì sao kết quả bất thường không chứng minh đã tăng tốc thuật toán.
2. Thêm benchmark tiêu thụ kết quả bằng `Blackhole.consume(countLoop(data))`, rồi so sánh với phương thức `return`. Hai kiểu có thể có overhead khác nhau; không bắt buộc số đo trùng hệt.
3. Chạy đủ ba phân phối balanced/mostlyPass/mostlyFail, kiểm tra liệu thứ hạng `loop`/`stream` có đổi theo distribution hay không. Nêu lý do dữ liệu đại diện ảnh hưởng quyết định.
4. Tăng `size` lên 1.048.576 và thực hiện benchmark trong môi trường đủ RAM. Vì sao tính chất CPU cache và memory bandwidth có thể khiến kết quả khác?
5. Chạy lại với số fork, warmup khác nhau rồi xem score biến động. Phân biệt trường hợp warmup chưa đủ với trường hợp workload thực sự thay đổi.
6. Viết giả thuyết cho ứng dụng có 90% request “hit”, 10% “miss”; định nghĩa dataset mô phỏng cả hai trường hợp và một bộ riêng cho cold-start.
7. Hãy chỉ ra ít nhất ba nguyên nhân khiến một phép đo nhanh hơn 20% trong JMH nhưng không cải thiện được p99 latency của dịch vụ.

## 11. Tài liệu tham khảo hiện hành

- [OpenJDK JMH — dự án và hướng dẫn tạo Maven archetype](https://github.com/openjdk/jmh): quy trình build JMH và chạy `target/benchmarks.jar`.
- [OpenJDK JMH — Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): khi nào dùng `return`, khi nào dùng `Blackhole.consume`.
- [OpenJDK JMH — State, Params và Setup](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): ví dụ chính thức về state scope, lifecycle, nhiều tham số và warmup.
- [Oracle Java SE 21 — HotSpot Tiered Compilation](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html): vai trò các tầng biên dịch và profile.
- [Oracle Java SE 21 — java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): tham số `-XX:+TieredCompilation`, `-XX:TieredStopAtLevel`, `-XX:+PrintCompilation` và cờ HotSpot liên quan.

**Ghi nhớ:** Với JIT phân tầng, một benchmark tốt phải **đo công việc thật, trả/tiêu thụ kết quả thật và sử dụng dữ liệu giống tình huống cần tối ưu**. Warmup, fork, số liệu thống kê và công cụ JMH giúp đo có hệ thống, nhưng không cứu được phép so sánh sai ngữ nghĩa hoặc nguồn dữ liệu không đại diện.