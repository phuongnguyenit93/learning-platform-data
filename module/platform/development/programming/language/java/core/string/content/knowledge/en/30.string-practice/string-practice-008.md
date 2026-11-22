# Đối chiếu hiệu năng các cách ghép chuỗi trên cùng dữ liệu trong Java

## 1. Mục tiêu thực hành

Trong Java, có nhiều cách tạo một chuỗi từ nhiều phần: toán tử `+`/`+=`, `StringBuilder`, `StringJoiner`, `String.join` và `Collectors.joining`. Những API này có cùng khả năng tạo kết quả văn bản, nhưng **số lần tạo đối tượng, thao tác sao chép, lượng cấp phát, overhead của luồng xử lý và khả năng tối ưu của JVM** có thể khác nhau.

Một bài so sánh đáng tin cần trả lời **hai câu hỏi tách biệt**:

1. **Đúng chức năng không?** Các cách ghép phải tạo *cùng một chuỗi*, cùng dấu phân cách, cùng thứ tự, xử lý giống nhau với mảng rỗng/một phần tử và các giá trị đầu vào đã định nghĩa.
2. **Hiệu năng có khác không?** Đo nhiều lần trong môi trường kiểm soát được, trên cùng dữ liệu, cùng công việc và cùng điều kiện chạy; phân biệt thời gian với lượng cấp phát.

**Mục tiêu bài này:** xây dựng bộ dữ liệu tái lập được, triển khai sáu cách ghép, xác nhận kết quả đồng nhất, sau đó đưa vào benchmark JMH để tự đối chiếu. Không có một con số “`StringBuilder` luôn nhanh hơn X lần” đúng cho mọi Java/JVM/kích thước dữ liệu.

## 2. Chọn đúng bài toán chung trước khi so sánh

Ta có mảng `String[] values` không chứa `null`, gồm các phần tử có định dạng `v0_0`, `v1_1`, ... Đầu ra mong muốn là:

```text
values = ["v0_0", "v1_1", "v2_2"]
result = "v0_0|v1_1|v2_2"
```

Quy tắc cố định:

- Dùng dấu `|` **chỉ giữa hai phần tử**; không có dấu phân cách ở đầu hoặc cuối.
- Giữ đúng thứ tự ban đầu và toàn bộ ký tự của từng phần tử.
- Mảng rỗng cho `""`; mảng một phần tử cho chính phần tử đó.
- Bài thực hành dùng phần tử **không null**; cách xử lý `null` trong dữ liệu thật phải được quy định riêng, không được để một phương pháp có chính sách khác mà vẫn tính là “cùng công việc”.
- Không tính thời gian **sinh mảng dữ liệu** vào thời gian ghép. Với `StringBuilder` có dung lượng ước tính, phải nói rõ chi phí tính dung lượng được tính trong bài thử chức năng hay được chuẩn bị trước trong benchmark.

Đầu vào được tạo theo công thức xác định, không lấy ngẫu nhiên trong đoạn mã đo thời gian:

```java
static String[] input(int size) {
    String[] values = new String[size];
    for (int i = 0; i < size; i++) {
        values[i] = "v" + i + "_" + (i % 17);
    }
    return values;
}
```

Đây là phương thức minh họa, được đưa vào chương trình độc lập ở phần sau. Việc mọi phương pháp cùng đọc một mảng `String[]` giúp loại bỏ khác biệt do đọc file, truy vấn cơ sở dữ liệu, tạo chuỗi ngẫu nhiên hoặc chuẩn hóa dữ liệu.

## 3. Sáu phương pháp được đối chiếu

| Cách | Cơ chế chính | Điểm cần chú ý khi đo |
| --- | --- | --- |
| `+=` trong vòng lặp | Mỗi bước yêu cầu một giá trị `String` mới theo ngữ nghĩa nối | Có thể sao chép lại phần kết quả tích lũy qua nhiều bước |
| `StringBuilder` mặc định | Thêm nhiều đoạn vào bộ đệm chuỗi có thể thay đổi | Bộ đệm có thể mở rộng nhiều lần |
| `StringBuilder` có `capacity` | Chuẩn bị sức chứa dự kiến rồi `append` | Cần biết/ước tính đúng dung lượng; tính toán capacity cũng có chi phí |
| `StringJoiner` | Thêm các phần tử với delimiter do API quản lý | Khớp trực tiếp bài toán “nối có phân cách” |
| `String.join` | API tiện lợi trên mảng/`Iterable` | Có thể có overhead riêng tùy JVM và triển khai |
| `Arrays.stream(...).collect(Collectors.joining(...))` | Đường ống stream, collector ghép chuỗi | Có thể phát sinh thêm chi phí tạo và vận hành stream |

**Quan trọng:** `StringBuilder` là **mutable**, còn `String` là **immutable**. Nhưng từ bytecode `invokedynamic` (trên `javac` Java 9+) không thể suy ra chính xác lượng cấp phát của mọi phép `+`. JVM có thể tối ưu mạnh trong các ngữ cảnh nhất định; cần benchmark thay vì kết luận hoàn toàn bằng trực giác.

Trong một biểu thức ngắn như `"id=" + id + ",name=" + name`, compiler hiện đại thường có khả năng tối ưu tốt. **`+=` lặp nhiều lần để tăng một chuỗi tích lũy** là bài toán khác, thường có nguy cơ lặp lại công việc sao chép khi kích thước kết quả tăng.

## 4. Chương trình Java 17+ xác minh tất cả phương pháp cho cùng kết quả

Tạo tệp `ConcatCases.java`:

```java
import java.util.Arrays;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class ConcatCases {
    static String plusLoop(String[] values) {
        String result = "";
        for (int i = 0; i < values.length; i++) {
            if (i > 0) result += "|";
            result += values[i];
        }
        return result;
    }

    static String builder(String[] values) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) out.append('|');
            out.append(values[i]);
        }
        return out.toString();
    }

    static String builderSized(String[] values) {
        int capacity = Math.max(0, values.length - 1);
        for (String value : values) capacity += value.length();
        StringBuilder out = new StringBuilder(capacity);
        for (int i = 0; i < values.length; i++) {
            if (i > 0) out.append('|');
            out.append(values[i]);
        }
        return out.toString();
    }

    static String joiner(String[] values) {
        StringJoiner out = new StringJoiner("|");
        for (String value : values) out.add(value);
        return out.toString();
    }

    static String joining(String[] values) {
        return String.join("|", values);
    }

    static String stream(String[] values) {
        return Arrays.stream(values).collect(Collectors.joining("|"));
    }

    static String[] input(int size) {
        String[] values = new String[size];
        for (int i = 0; i < size; i++) values[i] = "v" + i + "_" + (i % 17);
        return values;
    }

    public static void main(String[] args) {
        for (int n : new int[] {0, 1, 8, 128, 1024}) {
            String[] data = input(n);
            String expected = String.join("|", data);
            String[] actual = {
                plusLoop(data), builder(data), builderSized(data),
                joiner(data), joining(data), stream(data)
            };
            for (String candidate : actual) {
                if (!expected.equals(candidate)) {
                    throw new AssertionError("Different output at n=" + n);
                }
            }
            System.out.println("n=" + n + " methods=6 identical=true chars="
                    + expected.length());
        }
    }
}
```

Chạy tại thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 ConcatCases.java
java ConcatCases
```

Kết quả **đã kiểm chứng bằng biên dịch và thực thi**, không phải số liệu benchmark:

```text
n=0 methods=6 identical=true chars=0
n=1 methods=6 identical=true chars=4
n=8 methods=6 identical=true chars=39
n=128 methods=6 identical=true chars=834
n=1024 methods=6 identical=true chars=7501
```

Chương trình báo `methods=6 identical=true` vì **sáu cách đều cho giá trị `String` khớp từng ký tự** với kết quả chuẩn ở từng kích thước. Điều này loại được lỗi phổ biến như dấu `|` thừa ở cuối, sai thứ tự phần tử hoặc bỏ qua phần tử đầu tiên. Đây là *kiểm tra chức năng*, chưa phải chứng cứ cách nào nhanh nhất.

### Vì sao phải kiểm tra cả `n = 0` và `n = 1`?

- `n=0` có kết quả `""`. Một hàm ghép sai có thể tự thêm delimiter dù không có phần tử.
- `n=1` không được thêm bất cứ delimiter nào. Một số cách triển khai ghép thủ công dễ để thừa dấu `|` ở đầu/cuối.
- `n=8` giúp quan sát khối dữ liệu nhỏ thường gặp trong biểu mẫu, thông báo hoặc một dòng log.
- `n=128` và `n=1024` kiểm tra khi kết quả dài dần, phát hiện chi phí tích lũy và thay đổi cấu trúc bộ đệm.

Khi dữ liệu thực tế có `null`, Unicode dài, dấu phân cách bên trong giá trị hay giới hạn chiều dài, cần thêm lớp test tương ứng và **thống nhất kết quả mong muốn** giữa các phương pháp trước khi đo.

## 5. Vì sao kết quả nối đúng chưa đủ để so hiệu năng?

Một cách ghép có thể cho cùng kết quả nhưng:

- Tốn nhiều CPU hơn để sao chép đoạn kết quả tích lũy.
- Tạo nhiều đối tượng trung gian hoặc bộ đệm hơn, làm tăng áp lực garbage collector (GC).
- Phải mở rộng dung lượng bộ đệm theo từng giai đoạn.
- Có overhead do tạo stream, collector hoặc lớp điều phối API.
- Được JIT tối ưu khác nhau sau khi chạy nóng; cách đo quá ngắn dễ đánh giá sai.

Có thể hình dung với `n` đoạn có độ dài tương tự, nếu mỗi bước nối `+=` phải sao chép lại toàn bộ nội dung đã tích lũy, lượng dữ liệu cần sao chép có thể tăng theo tổng:

\[
1 + 2 + \cdots + n = \frac{n(n+1)}{2}
\]

Đây là giải thích trực quan cho nguy cơ tăng **xấp xỉ bậc hai theo số phần tử** trong cách nối tích lũy ngây thơ, khi độ dài mỗi phần tử tương tự nhau. Nó **không phải một cam kết về độ phức tạp thực tế của mọi trình biên dịch và JVM**: compiler/JIT có thể thực hiện một số tối ưu, đặc biệt trong ngữ cảnh xác định được.

Trong khi đó, `StringBuilder` có thể tích lũy vào một vùng đệm rồi tạo `String` kết quả, nên thường hạn chế việc tạo lại toàn bộ chuỗi qua từng bước. Khi đặt `capacity` đủ lớn trước, nó còn tránh một số lần mở rộng buffer. Nhưng nếu phải quét tất cả giá trị để tính độ dài, lần quét đó cũng là **chi phí**; không nên tính toàn bộ chi phí cho một phương pháp mà lại loại khỏi phương pháp khác khi mục tiêu là so tổng chi phí công việc từ đầu đến cuối.

## 6. Đo có kiểm soát với JMH

Để so hiệu năng microbenchmark trong Java, nên dùng **JMH (Java Microbenchmark Harness)** thay vì lấy hiệu `System.nanoTime()` quanh một lần nối. JMH hỗ trợ warmup, nhiều phép đo, fork JVM và tiêu thụ kết quả hợp lý để giảm tác động của dead-code elimination và tối ưu không mong muốn.

### Tạo dự án JMH

Cần cài JDK và Maven, dùng archetype JMH (ví dụ phiên bản `1.37`):

```bash
mvn archetype:generate -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=org.example \
  -DartifactId=concat-bench \
  -Dversion=1.0
```

Khối lệnh trên dùng ký hiệu nối dòng `\` của shell POSIX (Linux/macOS). Trên PowerShell, có thể viết **một dòng duy nhất** với các tham số tương tự và bỏ dấu `\` nối dòng. Archetype thiết lập phần cần thiết để JMH chạy như một dự án Maven. Đặt class benchmark `ConcatBenchmark.java` trong `concat-bench/src/main/java/org/example/`, dùng package `org.example` như ví dụ sau.

### Class JMH benchmark đầy đủ

```java
package org.example;

import java.util.Arrays;
import java.util.StringJoiner;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ConcatBenchmark {
    @Param({"8", "128", "1024"})
    public int n;

    private String[] data;
    private int exactCapacity;

    @Setup(Level.Trial)
    public void setup() {
        data = new String[n];
        int chars = Math.max(0, n - 1);
        for (int i = 0; i < n; i++) {
            data[i] = "v" + i + "_" + (i % 17);
            chars += data[i].length();
        }
        exactCapacity = chars;

        String expected = String.join("|", data);
        if (!expected.equals(plusLoop())
                || !expected.equals(builder())
                || !expected.equals(builderSized())
                || !expected.equals(joiner())
                || !expected.equals(joining())
                || !expected.equals(streamJoining())) {
            throw new IllegalStateException("Different concatenation outputs");
        }
    }

    @Benchmark
    public String plusLoop() {
        String result = "";
        for (int i = 0; i < data.length; i++) {
            if (i > 0) result += "|";
            result += data[i];
        }
        return result;
    }

    @Benchmark
    public String builder() {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < data.length; i++) {
            if (i > 0) out.append('|');
            out.append(data[i]);
        }
        return out.toString();
    }

    @Benchmark
    public String builderSized() {
        StringBuilder out = new StringBuilder(exactCapacity);
        for (int i = 0; i < data.length; i++) {
            if (i > 0) out.append('|');
            out.append(data[i]);
        }
        return out.toString();
    }

    @Benchmark
    public String joiner() {
        StringJoiner out = new StringJoiner("|");
        for (String value : data) out.add(value);
        return out.toString();
    }

    @Benchmark
    public String joining() {
        return String.join("|", data);
    }

    @Benchmark
    public String streamJoining() {
        return Arrays.stream(data).collect(Collectors.joining("|"));
    }
}
```

Điểm thiết kế quan trọng của benchmark:

- `@State(Scope.Thread)` cung cấp dữ liệu cho từng thread benchmark.
- `@Param` chạy cả ba kích thước dữ liệu trong các trường hợp đo riêng.
- `@Setup(Level.Trial)` tạo mảng và tính `exactCapacity` **ngoài đoạn đo**. Nhờ vậy đo riêng chi phí nối, không lẫn việc tạo dữ liệu.
- `builderSized()` được dùng một dung lượng đã biết trước, phản ánh kịch bản có thể biết trước chiều dài kết quả. Đây là **lợi thế có điều kiện**: nếu ứng dụng thực phải quét mảng tính dung lượng, hãy tạo thêm benchmark end-to-end tính cả chi phí đó.
- Mỗi `@Benchmark` trả về `String` kết quả, giúp harness quan sát giá trị trả về và tránh một số hình thức loại bỏ phép tính khi kết quả không được dùng.
- `@Fork(2)` chạy ở hai JVM fork độc lập; `@Warmup` và `@Measurement` giảm sự nhiễu của giai đoạn khởi động JIT.
- Không in console, đọc file, sinh mảng hoặc tạo dữ liệu ngẫu nhiên trong phương thức benchmark, vì đó không phải chi phí đang cần đo.

### Chạy JMH

Từ thư mục dự án `concat-bench`:

```bash
mvn clean verify
java -jar target/benchmarks.jar ConcatBenchmark
```

Mỗi combination giữa kích thước và phương pháp sẽ cho thống kê thời gian riêng. Các tùy chọn `@Warmup`, `@Measurement` và `@Fork` ở trên tương đối tốn thời gian vì cần làm nóng và đo nhiều lượt; khi thử nhanh có thể giảm số lần bằng tùy chọn command line, rồi dùng cấu hình đầy đủ cho báo cáo chính thức.

Ví dụ chạy thêm **GC allocation profiling**:

```bash
java -jar target/benchmarks.jar ConcatBenchmark -prof gc
```

Tùy profiler/JDK, output có thể gồm `gc.alloc.rate.norm` (byte cấp phát chuẩn hóa trên mỗi operation) và các metric GC liên quan. Số liệu cấp phát có thể phản ánh tối ưu của JIT và độ lớn output; không nên suy ra tổng heap retained chỉ từ số byte cấp phát. Nếu profiler không khả dụng trong môi trường đang dùng, chỉ báo phần này chưa đo, không tự điền số.

**Không đưa số μs/op cố định vào bài học**: JMH phải chạy trên máy, JDK, heap, CPU, trạng thái GC và workload cụ thể. Một bảng “kết quả” điền số trước khi đo sẽ khiến người học tin vào thứ hạng không được chứng minh.

## 7. Cách trình bày bảng đối chiếu kết quả

Sau khi chạy, hãy ghi rõ ít nhất `java -version`, loại CPU, JMH version, JVM options, số fork, số lần warmup/measurement, dataset, độ dài kết quả và đơn vị đo. Dùng một bảng cho **cùng một `n`**:

| Phương pháp | Avg time (μs/op) | Error/CI | Alloc (B/op) nếu có | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| `plusLoop` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | Nối tích lũy `+=` |
| `builder` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | Dung lượng mặc định |
| `builderSized` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | Dung lượng chuẩn bị sẵn |
| `joiner` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | API delimiter |
| `joining` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | API `String.join` |
| `streamJoining` | Điền từ JMH | Điền từ JMH | Điền từ `-prof gc` | Stream + collector |

Đây là **mẫu bảng kết quả cần đo**, không phải phép đo giả lập. Với chế độ `AverageTime`, số `μs/op` **thấp hơn** nghĩa là tốn ít thời gian hơn trong workload đo. Cột độ bất định hoặc error giúp tránh suy luận từ khác biệt rất nhỏ nằm trong sai số.

Khi so nhiều kích thước `n=8`, `128` và `1024`, không gộp tất cả thành một con số “trung bình” để xếp hạng. Xu hướng có thể đổi khi kích thước thay đổi: một cách ngắn gọn với chi phí khởi tạo nhỏ có thể phù hợp dữ liệu ít phần tử, trong khi cách tích lũy vào một buffer thường có lợi thế hơn ở workload dài.

### Ví dụ đọc kết quả cho đúng

Giả sử một kết quả thực nghiệm cụ thể cho thấy `builderSized` ít μs/op hơn `builder` khi `n=1024`, bạn có thể kết luận **trong benchmark đó**, dung lượng đã biết trước giúp giảm chi phí. Chưa thể kết luận toàn bộ ứng dụng sẽ nhanh hơn, vì thực tế có thể phải tính capacity, parse input, truy cập mạng hoặc ghi file.

Nếu `streamJoining` gần bằng `joining` trong cùng sai số, không đủ căn cứ gọi một cách nhanh hơn. Cũng đừng suy luận chỉ số `B/op` thấp luôn đồng nghĩa latency thấp; CPU, cấp phát, bộ nhớ và GC liên quan nhưng không phải cùng một đại lượng.

## 8. Những cái bẫy làm benchmark thiếu công bằng

1. **Không cùng đầu ra:** một phiên bản có delimiter cuối, một phiên bản không; hoặc một phiên bản bỏ qua phần tử rỗng. Phải so khớp kết quả trước khi đo.
2. **Tạo dữ liệu trong một benchmark nhưng tạo sẵn ở benchmark khác:** sẽ vô tình đo cả sinh dữ liệu, làm sai phép so.
3. **Một bên biết trước capacity, bên kia phải tự đi tính:** có thể là hai kịch bản hợp lệ, nhưng phải tách rõ benchmark đo **chỉ phép nối** với benchmark đo **tổng chi phí tạo output**.
4. **Dùng `System.nanoTime()` một lần rồi xếp hạng:** nhiễu từ JIT compilation, class loading, GC, scheduler và CPU có thể lớn hơn sự khác biệt thực.
5. **Không tiêu thụ kết quả:** JVM có thể loại bỏ phép tính không ảnh hưởng đến hành vi quan sát được. JMH hỗ trợ return value hoặc `Blackhole`.
6. **Để console I/O trong đoạn đo:** lệnh `System.out.println` có chi phí lớn, làm phép so không còn tập trung vào nối chuỗi.
7. **Benchmark trên mảng quá ngắn hoặc quá dài mà không đại diện ứng dụng:** chỉ một kích thước chưa đủ để rút ra quy luật.
8. **Lẫn độ dài String và byte UTF-8:** `String.length()` đo UTF-16 code units; số byte UTF-8 thay đổi theo nội dung. Nếu workload có Unicode thực tế, tạo tập dữ liệu tương ứng.
9. **Chỉ nhìn trung bình mà bỏ sai số và GC:** cần quan sát độ biến thiên, allocation/GC và lặp lại với cấu hình hợp lý.
10. **Thay một biểu thức `+` ngắn thành nối trong vòng lặp:** đó là hai workload khác nhau. Không dùng benchmark `+=` trong vòng lặp để kết luận mọi toán tử `+` đều chậm.
11. **Quên cấu hình JVM/JDK:** compiler phát bytecode và JIT runtime ảnh hưởng lớn. Nên ghi version của cả JDK biên dịch và JDK chạy benchmark.
12. **Kết luận từ một lần chạy trên máy đang tải nặng:** chạy các fork độc lập, ưu tiên môi trường ổn định, báo rõ giới hạn khi có nhiễu.

### Đối chiếu cả đầu ra lẫn độ phức tạp

Khi kết quả tương đương, hãy hỏi thêm về chuỗi kết quả **dài thêm như thế nào**. Một vòng lặp `+=` với `n` giá trị càng dài có thể khiến lượng nội dung trung gian cần sao chép tăng mạnh. Với `StringBuilder`, nhiều `append` thường làm việc trên một vùng đệm có thể tăng kích thước; do đó mức tăng chi phí thường dễ kiểm soát hơn. Nhưng những mô tả này là **mô hình giải thích**, không thay cho số liệu JMH của ứng dụng đang sử dụng.

## 9. Nên chọn cách nào trong mã Java thật?

- **Nối vài biểu thức cố định:** ưu tiên `+` vì dễ đọc. `javac` Java 9+ thường biểu diễn nhiều phép nối động qua `invokedynamic` và `StringConcatFactory`; không tự chuyển sang `StringBuilder` nếu chưa có lý do.
- **Tích lũy nhiều phần trong vòng lặp:** `StringBuilder` là lựa chọn rõ ràng, tránh phụ thuộc vào việc JVM nhận diện và tối ưu được phép `+=` lặp.
- **Có delimiter và danh sách/mảng sẵn:** `String.join(delimiter, values)` rất dễ đọc; `StringJoiner` phù hợp khi thêm từng phần tử theo quá trình xử lý.
- **Đang ở pipeline stream:** `Collectors.joining(delimiter)` tích hợp tự nhiên; cần đo nếu đoạn này là hot path, đặc biệt khi chỉ nối các phần tử mà không có bước biến đổi stream khác.
- **Đã biết tương đối chính xác độ dài kết quả:** có thể đặt capacity cho `StringBuilder` để giảm mở rộng bộ đệm; tính luôn chi phí chuẩn bị capacity khi đánh giá end-to-end.
- **Dữ liệu rất lớn:** cân nhắc streaming output trực tiếp vào `Writer`/`OutputStream` theo charset phù hợp nếu không bắt buộc tạo toàn bộ `String` trong bộ nhớ. Đây là bài toán khác với trả về một chuỗi duy nhất và phải benchmark riêng.

Người đọc mã nên ưu tiên **đúng ngữ nghĩa, dễ bảo trì, rồi đo các đoạn thực sự là bottleneck**. JMH giúp nhìn rõ ảnh hưởng của từng kỹ thuật, nhưng một tối ưu nhỏ của nối chuỗi không cứu được thiết kế vốn tốn phần lớn thời gian ở I/O, truy vấn hoặc xử lý khác.

## 10. Checklist hoàn thành bài thực hành

- Sáu cách đều nhận **cùng mảng dữ liệu** và tạo chính xác một chuỗi có `|` giữa các phần tử.
- Đã xác nhận `n=0`, `1`, `8`, `128`, `1024` cho cùng nội dung, không chỉ cùng độ dài.
- Dataset được tạo ngoài đoạn đo JMH; mọi thử nghiệm có chung logic tạo phần tử.
- Có các lần warmup, measurement, fork JVM và phương thức tiêu thụ kết quả.
- Báo cáo riêng từng kích thước, đơn vị `μs/op`, độ bất định và nếu có thì `B/op`.
- Phân biệt benchmark `builderSized` có capacity biết trước với kịch bản phải tính capacity trong mỗi lần xử lý.
- Tránh suy luận hiệu năng của mọi biểu thức `+` từ benchmark `+=` trong vòng lặp.
- Chỉ kết luận nhanh/chậm theo **bằng chứng đo thực tế**, có môi trường và giới hạn rõ ràng.

**Ghi nhớ:** một phép so sánh hiệu năng ghép chuỗi chỉ có ý nghĩa khi **sáu phương pháp cho đầu ra giống nhau trước khi đo**. Với công việc nối nhiều phần, `StringBuilder` và các API nối có delimiter là lựa chọn thực tế cần đối chiếu; `+=` trong vòng lặp có nguy cơ tốn chi phí sao chép đáng kể. Thứ hạng và mức chênh lệch cuối cùng phải được xác nhận bằng benchmark đúng cách trên workload phù hợp.
