# So sánh vòng lặp, Stream tuần tự và Stream song song công bằng

## Mục tiêu

Trong Java Stream API, ba cách xử lý cùng một tập dữ liệu thường được đặt cạnh nhau: vòng lặp `for`, **Stream tuần tự** và **Stream song song** (`parallelStream()` hoặc `parallel()`). Câu hỏi «cách nào nhanh hơn?» chỉ có ý nghĩa khi chúng giải quyết **cùng một công việc**, chạy dưới điều kiện đo tương đương và được đánh giá bằng chỉ số phù hợp. Bài học thuộc chương **Hiệu năng và bộ nhớ** này hướng dẫn thiết kế một phép so sánh có thể kiểm chứng, đọc kết quả và quyết định khi nào nên dùng từng cách.

Sau bài học, bạn có thể:

- Phân biệt chi phí duyệt, chi phí pipeline, chi phí tách và gộp tác vụ của ba cách xử lý.
- Tạo benchmark công bằng bằng **JMH (Java Microbenchmark Harness)** và tránh kết luận sai từ `System.nanoTime()` chạy một lần.
- Đánh giá thời gian, throughput, cấp phát bộ nhớ và tác động của kích thước dữ liệu, mức độ tính toán cùng số lõi CPU.
- Nhận diện trường hợp kết quả khác nhau vì ngữ nghĩa, chẳng hạn thứ tự, phép toán không kết hợp hoặc tác dụng phụ.

## 1. Ba cách xử lý thực sự khác nhau ở đâu?

| Cách xử lý | Cơ chế | Chi phí đáng chú ý | Thường thích hợp |
| --- | --- | --- | --- |
| Vòng lặp `for` | Duyệt dữ liệu và thực hiện điều kiện/phép tính trực tiếp | Chi phí vòng lặp thấp; có thể được JIT tối ưu rất tốt | Đường xử lý ngắn, dữ liệu nhỏ, đoạn mã nhạy hiệu năng |
| Stream tuần tự | Xây pipeline `filter` → `map` → terminal operation; chỉ thực thi khi có terminal operation | Thiết lập pipeline, gọi/ghép các stage; mức độ tối ưu tùy JVM và workload | Biến đổi dữ liệu dễ đọc, kết hợp các thao tác rõ ràng |
| Stream song song | Dùng `Spliterator` chia đầu vào, xử lý các phần qua Fork/Join rồi gộp kết quả | Chia việc, lên lịch, đồng bộ/gộp, tranh chấp CPU, có thể tăng cấp phát | Dữ liệu đủ lớn, dễ chia, phép tính độc lập và đủ nặng, phần gộp hiệu quả |

`parallel()` **không bảo đảm nhanh hơn** `sequential()`. Với vài trăm phần tử, thời gian tổ chức tác vụ có thể lớn hơn thời gian tính toán. Với hàng triệu phần tử và phép tính tốn CPU, nhiều lõi có thể đem lại lợi ích. Tuy nhiên kết quả còn phụ thuộc phần cứng, cách chia nguồn dữ liệu, độ phức tạp của mỗi phần tử, locality bộ nhớ, trạng thái GC và mức tải máy.

Cần phân biệt **độ trễ** (*latency*: một lần xử lý mất bao lâu) với **thông lượng** (*throughput*: xử lý được bao nhiêu lần hoặc phần tử mỗi giây). Một Stream song song có thể giảm độ trễ cho một yêu cầu lớn nhưng chiếm nhiều lõi hơn, khiến thông lượng của cả ứng dụng giảm khi có nhiều yêu cầu đồng thời.

## 2. Điều kiện để phép so sánh công bằng

Trước khi đo, hãy xác định bài toán và ghi lại những điều kiện sau:

1. **Cùng đầu vào.** Dùng cùng mảng, cùng số phần tử, cùng phân bố giá trị và cùng trạng thái dữ liệu; không để một phương án phải đọc tệp hoặc tạo dữ liệu còn phương án khác chỉ tính toán trên mảng có sẵn.
2. **Cùng kết quả và ngữ nghĩa.** Ba cách phải lọc, biến đổi và tổng hợp cùng các phần tử. Nếu cần giữ thứ tự, so sánh các cách đều giữ thứ tự; không đem `findFirst()` của cách này so với `findAny()` của cách khác rồi kết luận về hiệu năng.
3. **Cùng loại dữ liệu.** So sánh vòng lặp trên `int[]` với `IntStream`, tránh vô tình so với `Stream<Integer>` có thêm boxing/unboxing. Nếu muốn đo chi phí boxing, hãy thiết kế một thí nghiệm riêng.
4. **Cùng phạm vi thời gian đo.** Chỉ đo công việc được nghiên cứu. Khởi tạo mảng, phát sinh số ngẫu nhiên, ghi log, `println`, xác thực kết quả và khởi động ứng dụng nên nằm ngoài phần đo nếu không thuộc bài toán.
5. **Có khởi động JIT và nhiều mẫu đo.** JVM cần warmup để biên dịch, inline và tối ưu code; kết quả lần chạy đầu không đại diện cho trạng thái ổn định. Dùng nhiều iteration và nhiều fork JVM.
6. **Kiểm soát môi trường.** Dùng cùng JDK, cờ JVM, kích thước heap, máy, giới hạn CPU/cgroup và mức tải nền. Ghi số lõi logic mà JVM nhìn thấy và tránh chạy nhiều benchmark cạnh tranh CPU cùng lúc.
7. **Đo nhiều kích thước và mức độ tính toán.** Chẳng hạn 1.000, 100.000, 1.000.000 phần tử; thử phép tính nhẹ và nặng trong các thí nghiệm riêng. Điểm mà Stream song song bắt đầu có lợi không cố định.
8. **Đo cả tài nguyên.** Ngoài `ms/op`, theo dõi `B/op`, GC, mức sử dụng CPU và độ biến thiên giữa các lần chạy. Thời gian ngắn hơn nhưng dùng nhiều bộ nhớ hoặc nhiều lõi hơn có thể không phù hợp với hệ thống thật.

**Lưu ý về “cùng công việc”:** Nếu mục tiêu là tính tổng của các giá trị chẵn sau khi biến đổi, cả ba phiên bản phải tính đúng cùng công thức. Nếu mục tiêu là lấy 10 phần tử đầu tiên, vòng lặp phải có quyền dừng sớm giống `limit(10)`; việc bắt một phiên bản đi hết nguồn khiến kết quả thiên lệch.

## 3. Ví dụ benchmark có thể chạy bằng JMH

Thí nghiệm dưới đây dùng cùng một `int[]`. Mỗi phương án lọc số chẵn, gọi hàm thuần `work(int)` trên từng phần tử được chọn, rồi cộng kết quả kiểu `long`. Hàm `work` có nhiều bước tính toán để tạo workload CPU rõ ràng và **không có trạng thái chia sẻ hoặc tác dụng phụ**. Cả ba benchmark trả kết quả để JMH giữ lại giá trị tính toán.

```java
import java.util.Arrays;
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
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
@Threads(1)
public class LoopStreamBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = i;
        }

        // Kiểm chứng bên ngoài khoảng thời gian JMH đo.
        long expected = loop();
        if (sequentialStream() != expected || parallelStream() != expected) {
            throw new IllegalStateException("Ket qua ba phuong an khac nhau");
        }
    }

    // Hàm thuần: cùng một đầu vào luôn có cùng kết quả.
    private static long work(int value) {
        long x = value;
        for (int i = 0; i < 32; i++) {
            x = (x * 1_103_515_245L + 12_345L) & 0x7fff_ffffL;
        }
        return x;
    }

    @Benchmark
    public long loop() {
        long sum = 0L;
        for (int value : values) {
            if ((value & 1) == 0) {
                sum += work(value);
            }
        }
        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return Arrays.stream(values)
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopStreamBenchmark::work)
                .sum();
    }

    @Benchmark
    public long parallelStream() {
        return Arrays.stream(values)
                .parallel()
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopStreamBenchmark::work)
                .sum();
    }
}
```

Những điểm chủ đích trong ví dụ:

- `@Param` chạy các kích thước dữ liệu khác nhau; không cần tạo mảng trong mỗi lần gọi benchmark.
- `@Setup` tạo dữ liệu và đối chiếu ba kết quả **ngoài khoảng đo**, phát hiện lỗi ngữ nghĩa trước khi so sánh tốc độ.
- `@Threads(1)` nghĩa là chỉ một luồng JMH gọi benchmark tại một thời điểm. Riêng `parallelStream()` vẫn có thể sử dụng các worker của `ForkJoinPool.commonPool()`; vì vậy số luồng xử lý thực tế của phương án song song có thể lớn hơn một.
- `@Fork(2)` tạo các tiến trình JVM riêng để giảm phụ thuộc vào trạng thái JIT của một tiến trình. Năm lượt warmup và năm lượt measurement trong mỗi fork tạo nhiều mẫu hơn cách bấm giờ thủ công.
- Cả ba phiên bản đều sử dụng mảng nguyên thủy, cùng `filter`, cùng `work` và cùng `sum`. Thí nghiệm này đo **độ trễ xử lý trọn một mảng**, không đo riêng chi phí khởi tạo một Stream rỗng.

JMH là thư viện benchmark riêng: dự án cần khai báo `jmh-core` và bộ xử lý annotation `jmh-generator-annprocess` cùng phiên bản, rồi cấu hình build tạo JAR benchmark. Với cấu hình Maven JMH thông dụng sinh `target/benchmarks.jar`, có thể chạy:

```bash
java -jar target/benchmarks.jar '.*LoopStreamBenchmark.*' -prof gc -rf json -rff results.json
```

Trên môi trường dùng shell khác, cú pháp dấu nháy cho bộ lọc tên benchmark có thể khác; đường dẫn JAR cũng phụ thuộc Maven/Gradle. Tùy chọn `-prof gc` giúp quan sát cấp phát/GC; `-rf json -rff results.json` lưu kết quả để đối chiếu giữa các lần thử. Ghi lại phiên bản JDK, cờ JVM, CPU, giới hạn container và mức tải nền cùng tệp kết quả. Bài học này cung cấp benchmark để người học chạy trên môi trường của mình; **không có số liệu đo thực tế được giả định sẵn**.

### Đọc kết quả cho đúng

Trong ví dụ, `@BenchmarkMode(Mode.AverageTime)` và `@OutputTimeUnit(MILLISECONDS)` có nghĩa:

- **`ms/op`**: thời gian trung bình để xử lý **toàn bộ mảng một lần**; càng thấp càng nhanh với cùng kích thước `size`.
- **Sai số và độ phân tán**: quan sát khoảng tin cậy hoặc mức thay đổi giữa các fork/iteration; hai con số chênh rất ít có thể không đủ chứng cứ để kết luận.
- **`gc.alloc.rate.norm` (B/op)** nếu profiler hỗ trợ: lượng bộ nhớ cấp phát chuẩn hóa theo **một lần xử lý mảng**, không phải theo một phần tử. Giá trị bằng 0 hoặc rất nhỏ có thể xuất hiện nhờ tối ưu của JVM; đừng mặc định cứ dùng Stream là tạo một object cho mỗi phần tử.
- **Thông lượng phần tử** nếu cần so sánh ở cùng `size`: xấp xỉ `size * 1000 / (ms/op)` phần tử đầu vào/giây. Không dùng phép đổi này để gộp kết quả của các kích thước khác nhau mà thiếu giải thích.

Ví dụ về cách diễn giải, không phải số liệu đo: nếu `loop` thắng rõ ở `size=1000`, nhưng `parallelStream` có `ms/op` thấp hơn khi `size=1000000`, hãy xem đây là dấu hiệu của **ngưỡng bù chi phí chia/gộp** cho workload và máy đang đo. Cần đo lại với phép tính nhẹ hơn, tải CPU khác và ứng dụng thực tế trước khi áp dụng quyết định chung.

## 4. Vì sao kết quả thay đổi theo workload?

### Kích thước dữ liệu và chi phí cố định

Vòng lặp có ít lớp điều phối. Stream tuần tự thêm pipeline; JIT có thể inline/fuse nhiều stage nhưng không bảo đảm triệt tiêu mọi chi phí. Stream song song phải tách nguồn, đưa tác vụ vào Fork/Join, xử lý trên các worker rồi gộp kết quả. Với tập nhỏ, chi phí cố định dễ chiếm ưu thế; với tập lớn, chi phí đó có thể được chia nhỏ so với lượng tính toán hữu ích.

### Độ nặng của mỗi phần tử

Nếu mỗi phần tử chỉ cộng `1` hoặc kiểm tra một bit, việc phân phối tác vụ thường khó đem lại lợi ích. Nếu mỗi phần tử làm tính toán CPU độc lập và tốn thời gian, chạy đồng thời có thể cải thiện độ trễ. Hãy **giữ nguyên logic của cả ba phương án** khi chuyển từ workload nhẹ sang nặng; đừng tăng số phép toán cho riêng một phương án.

### Đặc tính nguồn và phép gộp

Mảng và `ArrayList` có `Spliterator` dễ chia tương đối đều. Một số nguồn khó chia hoặc phải đi tuần tự để lấy phần tử có thể không mở rộng hiệu quả. Các phép tổng hợp như `sum()` có cách gộp gọn; ngược lại, collector phải giữ thứ tự, cần khóa hoặc gộp cấu trúc lớn có thể trở thành nút thắt. Những stage có trạng thái như `sorted()`, `distinct()` hoặc một số trường hợp `limit()` trên Stream có thứ tự có thể cần đệm hoặc đồng bộ thêm khi song song.

### Cạnh tranh tài nguyên và áp lực bộ nhớ

Song song không tạo thêm băng thông bộ nhớ vô hạn. Khi các lõi cùng đọc một vùng dữ liệu lớn, cache miss hoặc băng thông RAM có thể giới hạn tốc độ. Nhiều tác vụ cũng có thể tăng số đối tượng trung gian, hoạt động GC hoặc tranh chấp với các request khác. Để hiểu lợi ích thực tế, đo cả mức tiêu thụ CPU và thời gian khi ứng dụng có số lượng request đồng thời như môi trường vận hành.

## 5. Những phép so sánh dễ dẫn đến kết luận sai

| Cách đo gây lệch | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chạy `System.nanoTime()` một lần cho mỗi cách | Bị ảnh hưởng bởi JIT chưa warmup, GC, scheduling và nhiễu hệ thống | Dùng JMH với warmup, measurement, fork và đọc sai số |
| Tạo `List`/mảng bên trong chỉ một phương án | Đang đo thêm cấp phát và khởi tạo dữ liệu | Chuẩn bị cùng dữ liệu ở phần setup |
| So `for (int x : int[])` với `Stream<Integer>` | Boxing/unboxing và kiểu nguồn khác nhau | Dùng `IntStream`; khảo sát boxing riêng nếu cần |
| So `findFirst()` với `findAny()` | Cam kết thứ tự và khả năng dừng sớm khác nhau | Dùng cùng yêu cầu thứ tự và cùng điều kiện dừng |
| Thêm `.peek(System.out::println)` vào một pipeline | I/O và đồng bộ console làm sai bản chất workload | Bỏ log khỏi phần đo |
| Benchmark song song trong lúc các benchmark khác cũng chạy | Cạnh tranh `commonPool` và CPU khiến số đo thay đổi | Chạy tuần tự các benchmark trên máy ít nhiễu; ghi lại cấu hình |
| Chỉ nhìn `ms/op` mà bỏ qua số lõi và `B/op` | Có thể thắng độ trễ nhưng dùng nhiều tài nguyên hơn | Xem latency, throughput của hệ thống, CPU và bộ nhớ |
| Suy ra «Stream luôn chậm» hoặc «parallel luôn nhanh» từ một kích thước | Điểm giao phụ thuộc nguồn, workload, JDK và phần cứng | Đo nhiều kích thước và chạy lại trên môi trường đích |

**Chú ý về tính đúng:** `forEach()` trên Stream song song không đảm bảo thứ tự thực thi; nếu yêu cầu thứ tự, phải dùng API và thuật toán tương ứng, chẳng hạn `forEachOrdered()`, rồi mới đo. Biến đếm chia sẻ được cập nhật trong lambda là lỗi cạnh tranh dữ liệu, không phải một cách gộp kết quả hợp lệ. Hãy ưu tiên reduction hoặc collector phù hợp.

Với số dấu phẩy động, phép cộng không có tính kết hợp tuyệt đối do làm tròn: `(a + b) + c` có thể khác `a + (b + c)`. Stream song song có thể thay đổi thứ tự nhóm khi gộp. Nếu so các tổng `double`, phải xác định ngưỡng sai số chấp nhận được và đo hiệu năng chỉ khi kết quả đáp ứng tiêu chí chính xác của bài toán; không chỉ so bằng `==`. Ví dụ JMH phía trên cố ý dùng kết quả nguyên `long` để tránh gây nhiễu bởi vấn đề đó.

## 6. Quy trình đánh giá trong dự án thực tế

1. **Đặt mục tiêu:** Ví dụ «giảm p95 thời gian xử lý 1.000.000 bản ghi, không tăng cấp phát quá mức chấp nhận và không làm giảm throughput khi 8 request đồng thời».
2. **Tạo baseline đúng:** Viết ba phiên bản tương đương, có kiểm chứng kết quả; dùng tập dữ liệu và kích thước đại diện cho sản xuất.
3. **Chạy microbenchmark:** Dùng JMH trên cùng máy/JDK, nhiều fork và nhiều kích thước; ghi `ms/op`, sai số và chỉ số cấp phát.
4. **Thử trong ngữ cảnh ứng dụng:** Đo throughput, p95/p99, CPU và GC khi có nhiều yêu cầu đồng thời, vì JMH một benchmark đơn lẻ chưa phản ánh toàn bộ hệ thống.
5. **Ra quyết định có điều kiện:** Chọn cách đáp ứng mục tiêu hiệu năng, độ chính xác và khả năng bảo trì. Ghi các điều kiện mà kết luận đúng để lần nâng cấp JDK hoặc thay phần cứng có thể đo lại.

### Tự kiểm tra

- Vì sao một phép đo `nanoTime()` duy nhất không đủ kết luận vòng lặp nhanh hơn Stream?
- Vì sao benchmark `parallelStream()` có `@Threads(1)` vẫn có thể sử dụng nhiều lõi CPU?
- Nếu `parallelStream()` giảm `ms/op` nhưng throughput của máy chủ giảm khi nhiều request chạy cùng lúc, bạn nên đánh giá điều gì tiếp theo?
- Với pipeline có `sorted()` hoặc `findFirst()`, cần đối chiếu ngữ nghĩa nào trước khi so hiệu năng?

**Điểm cần nhớ:** Phép so sánh công bằng bắt đầu bằng kết quả và ngữ nghĩa tương đương, tiếp theo là phép đo có warmup và kiểm soát môi trường, cuối cùng mới là lựa chọn cách triển khai. Vòng lặp, Stream tuần tự và Stream song song đều có phạm vi phù hợp; benchmark cung cấp bằng chứng cho **bài toán cụ thể**, không tạo ra thứ hạng đúng cho mọi chương trình Java.
# So sánh vòng lặp, Stream tuần tự và Stream song song công bằng

## 1. Mục tiêu bài học

Trong module **`JAVA_STREAM_API`**, Java Stream API cho phép mô tả xử lý dữ liệu theo kiểu khai báo với các bước lazy như `filter`, `map`, rồi kết thúc bằng `reduce`, `sum` hoặc `collect`. Các pipeline còn có thể chạy theo chế độ tuần tự hoặc song song. Tuy nhiên, một câu hỏi thường xuất hiện khi tối ưu ứng dụng là:

> Vòng lặp `for`, Stream tuần tự hay Stream song song nhanh hơn, dùng ít bộ nhớ hơn và phù hợp hơn cho cùng một nhiệm vụ?

Không có một đáp án đúng cho mọi chương trình. Kết quả phụ thuộc **dữ liệu, chi phí mỗi phần tử, đặc tính nguồn, hoạt động của JIT, bộ nhớ, tải CPU và cách đo**. So sánh công bằng không phải viết ba đoạn code trông giống nhau rồi bấm đồng hồ; phải xác định **hợp đồng tính đúng** và kiểm soát các biến độc lập.

Bài thuộc chương **Hiệu năng và bộ nhớ**, kết nối với pipeline lazy, kiểu primitive, `Spliterator`, reduce/collector, xử lý song song và các giới hạn tài nguyên của Java Stream API.

Sau bài học, bạn có thể:

1. Thiết kế ba triển khai **tương đương về đầu vào, đầu ra và lượng công việc**.
2. Biết vì sao không thể dùng một lần `System.nanoTime()` để kết luận phương án nào nhanh hơn.
3. Dùng JMH với warm-up, measurement, fork và trạng thái đầu vào ổn định.
4. Phân biệt **thời gian trung bình**, **throughput**, **allocation rate**, **GC** và **latency**.
5. Nhận diện chi phí boxing, tạo pipeline, chia nguồn, phối hợp worker và ghép kết quả.
6. Biết khi nào tính song song bị giới hạn bởi nguồn, thứ tự, trạng thái chia sẻ hoặc băng thông bộ nhớ.
7. Xây dựng checklist và bộ test để một kết quả benchmark có thể được kiểm tra và tái lập.

## 2. "Công bằng" nghĩa là so sánh cùng hợp đồng

Một phép so sánh hợp lệ cần bảo đảm ba phiên bản tính **cùng một hàm** trên **cùng một tập dữ liệu**.

Ví dụ nghiệp vụ: với mảng số nguyên kiểu `long`, chỉ lấy số chẵn, bình phương từng số rồi tính tổng:

\[
S=\sum_{\substack{x\in A\\x\bmod 2=0}} x^2
\]

Để kết quả không tràn `long` trong thí nghiệm, ta giới hạn giá trị đầu vào trong khoảng **1 đến 10.000** và số phần tử tối đa ở mức **1.000.000**. Khi đó tổng các bình phương không thể vượt `100.000.000.000.000`, nhỏ hơn `Long.MAX_VALUE`.

Ta sẽ so sánh:

- **Vòng lặp:** duyệt mảng bằng `for`, kiểm tra tính chẵn, cộng bình phương.
- **Stream tuần tự:** `Arrays.stream(data).filter(...).map(...).sum()`.
- **Stream song song:** cùng pipeline, thêm `parallel()`.

Cả ba dùng **chính mảng `long[]`**. Nhờ đó, kết quả không bị lẫn với khác biệt giữa `ArrayList` và `LinkedList`, hay giữa `long` primitive và `Long` boxed.

### 2.1. Các điều kiện phải thống nhất

| Yếu tố | Quy tắc so sánh |
| --- | --- |
| Dữ liệu đầu vào | Cùng một mảng/nguồn, cùng giá trị và phân phối dữ liệu. |
| Kiểu dữ liệu | Cùng `long[]` và `LongStream`; không tráo `Stream<Long>` vào một nhánh. |
| Công việc | Cùng lọc số chẵn, cùng bình phương, cùng cộng. |
| Kiểu kết quả | Cùng `long`, tránh khác biệt làm tròn số thực. |
| Phạm vi tính thời gian | Đo đúng hàm xử lý, không nhét tạo dữ liệu vào riêng một nhánh. |
| Đầu ra | Kết quả được sử dụng, tránh tối ưu hóa loại bỏ tính toán không quan sát được. |
| Môi trường | Cùng máy, JDK, JVM flags, tải nền và chính sách đo. |
| Số lần đo | Có warm-up, nhiều lần đo, nhiều fork nếu dùng microbenchmark. |
| Tính song song | Ghi nhận số lõi, tải CPU và tác động của pool chung. |
| Kết luận | Chỉ kết luận cho workload và điều kiện đã đo, không tổng quát vô căn cứ. |

**Không nhất thiết ba cách phải có cùng số dòng lệnh.** Mục tiêu là so sánh các **lựa chọn triển khai thực tế** cho cùng một yêu cầu, không ép vòng lặp tạo đối tượng thừa để trông giống Stream.

### 2.2. Những so sánh không công bằng

Ví dụ sai về phương pháp:

```java
// Nhánh A dùng primitive long[].
for (long value : data) {
    // ...
}

// Nhánh B dùng Stream<Long> và boxing.
listOfLong.stream()
    .filter(...)
    .map(...)
    .reduce(...);

// Nhánh C dùng nguồn khác và công việc khác.
java.util.stream.LongStream.range(0, data.length)
    .parallel()
    .sum();
```

Ba nhánh trên khác **biểu diễn nguồn, boxing và phép tính**. Nếu đo được chênh lệch, không thể nói chênh lệch đó chỉ đến từ "vòng lặp so với Stream".

Cũng không công bằng nếu một nhánh chỉ đếm phần tử, nhánh khác tính bình phương, hoặc một nhánh in từng phần tử ra console. I/O của `System.out.println` có thể chi phối hoàn toàn thời gian chạy.

## 3. Ba triển khai tương đương trên `long[]`

Chương trình dưới đây sử dụng **Java 8+** và chỉ cần thư viện chuẩn. Tạo file `FairStreamComparison.java`:

```java
import java.util.Arrays;
import java.util.SplittableRandom;

public class FairStreamComparison {
    static long withLoop(long[] data) {
        long sum = 0L;
        for (long value : data) {
            if ((value & 1L) == 0L) {
                sum += value * value;
            }
        }
        return sum;
    }

    static long withSequentialStream(long[] data) {
        return Arrays.stream(data)
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    static long withParallelStream(long[] data) {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    static long[] createData(int size) {
        if (size < 0) {
            throw new IllegalArgumentException(
                "size phai >= 0");
        }

        long[] data = new long[size];
        SplittableRandom random =
            new SplittableRandom(20261118L);

        for (int i = 0; i < data.length; i++) {
            // Gia tri 1..10000, tong binh phuong khong tran.
            data[i] = random.nextInt(1, 10_001);
        }

        return data;
    }

    static void verify(long[] data) {
        long a = withLoop(data);
        long b = withSequentialStream(data);
        long c = withParallelStream(data);

        if (a != b || a != c) {
            throw new AssertionError(
                "Sai khac ket qua: "
                + a + ", " + b + ", " + c);
        }
    }

    public static void main(String[] args) {
        verify(new long[0]);
        verify(new long[] {1});
        verify(new long[] {2});
        verify(new long[] {1, 2, 3, 4, 5, 6});
        verify(new long[] {-4, -3, -2, -1, 0, 1, 2, 3, 4});
        verify(new long[] {9_999, 10_000});

        for (int size : new int[] {
                1, 10, 128, 10_000, 1_000_000}) {
            verify(createData(size));
        }

        System.out.println("PASS: ba cach cho cung ket qua");
    }
}
```

Nếu chạy đúng:

```text
PASS: ba cach cho cung ket qua
```

Đây là **bộ kiểm tra tính đúng**, chưa phải benchmark. Chương trình cố ý **không in số nano-giây**, vì chạy ba hàm một lần liên tiếp sẽ bị ảnh hưởng bởi JIT warm-up và thứ tự gọi.

### 3.1. Vì sao `Arrays.stream(data)`?

Đối với mảng `long[]`, `Arrays.stream(data)` tạo `LongStream`, tránh boxing `long` thành `Long` ở mỗi phần tử.

So sánh các pipeline:

```java
// LongStream: xử lý primitive.
long sum1 = Arrays.stream(data)
    .filter(x -> x % 2L == 0L)
    .map(x -> x * x)
    .sum();

// Stream<Long>: có boxing, cần đánh giá riêng.
long sum2 = Arrays.stream(data)
    .boxed()
    .filter(x -> x % 2L == 0L)
    .mapToLong(x -> x * x)
    .sum();
```

Hai nhánh có cùng kết quả, nhưng **không cùng chi phí biểu diễn**. Khi câu hỏi là "vòng lặp so với Stream primitive", dùng nhánh `LongStream` làm baseline. Khi câu hỏi là "pipeline object cần boxing bao nhiêu", hãy tạo **một thí nghiệm thứ hai** có nhãn rõ ràng.

### 3.2. Vì sao kết quả trả về `long`?

Nếu một phương thức benchmark tính xong rồi bỏ kết quả, JIT có thể tối ưu những tính toán không quan sát được trong một số trường hợp. Trả về `long` cho harness benchmark như JMH giúp kết quả được **sử dụng**, giảm nguy cơ đo nhầm một phép tính đã bị loại bỏ.

Tránh benchmark kiểu:

```java
static void notUseful(long[] data) {
    long total = Arrays.stream(data)
        .filter(x -> x % 2 == 0)
        .map(x -> x * x)
        .sum();

    // total khong duoc su dung.
}
```

Không có nghĩa mọi lời gọi trên chắc chắn bị JIT xóa; đó là **rủi ro cần kiểm soát**, không phải dự đoán một tối ưu cụ thể của mọi JVM.

## 4. Đúng kết quả trước, đo hiệu năng sau

Hãy kiểm tra các tính chất độc lập:

1. **Nguồn rỗng:** tổng phải là 0.
2. **Một phần tử lẻ:** tổng 0.
3. **Một phần tử chẵn:** bình phương phần tử đó.
4. **Hỗn hợp số âm/dương:** toán tử kiểm tra chẵn cho kết quả đúng.
5. **Dữ liệu lặp:** mỗi phần tử được tính đúng số lần xuất hiện.
6. **Nguồn lớn:** ba cách trả cùng kết quả và không có overflow theo miền đã đặt.
7. **Không sửa đầu vào:** gọi các hàm không làm thay đổi mảng.
8. **Kết quả ổn định:** cùng dữ liệu, không dùng biến trạng thái ngoài lambda.

### 4.1. Test độc lập với một kết quả đã tính tay

```java
long[] sample = {1, 2, 3, 4, 5, 6};

// 2² + 4² + 6² = 4 + 16 + 36 = 56
if (FairStreamComparison.withLoop(sample) != 56L) {
    throw new AssertionError("Loop sai");
}
if (FairStreamComparison.withSequentialStream(sample) != 56L) {
    throw new AssertionError("Sequential sai");
}
if (FairStreamComparison.withParallelStream(sample) != 56L) {
    throw new AssertionError("Parallel sai");
}
```

Một kiểm tra độc lập giúp tránh trường hợp cả ba cách dùng chung một công thức sai và vẫn cho ra **cùng một giá trị sai**.

### 4.2. Đừng dùng so sánh `double` bằng `==` một cách tùy tiện

Nếu bài toán đổi sang `double`, phép cộng dấu phẩy động không có tính kết hợp chính xác ở mức bit:

```text
(a + b) + c  có thể khác  a + (b + c)
```

Stream song song có thể nhóm tổng cục bộ theo thứ tự khác. Kết quả dấu phẩy động có thể khác ở vài bit cuối dù mỗi cách hợp lệ theo hợp đồng API. Test cần tiêu chí dung sai (và chính sách với NaN, vô cực, ±0) phù hợp, hoặc dùng một phép tính có quy tắc chính xác riêng.

Thí nghiệm chính dùng `long` trong miền không tràn để **giảm biến nhiễu** khi đánh giá tốc độ, không phải vì Stream chỉ phù hợp với số nguyên.

## 5. Phân biệt microbenchmark và đo ứng dụng thực

**Microbenchmark** đo một thao tác nhỏ trong môi trường được kiểm soát; **benchmark ứng dụng** đo cả luồng nghiệp vụ (đọc nguồn, parse, xử lý, serialize, gửi kết quả...). Cả hai có ích nhưng trả lời câu hỏi khác nhau.

| Loại đo | Câu hỏi trả lời | Điều không thể suy ra |
| --- | --- | --- |
| Microbenchmark ba hàm | Một lần tính trên mảng sẵn có tốn bao lâu? | Toàn API thực tế có nhanh lên tương ứng không? |
| Benchmark end-to-end | Một yêu cầu xử lý dữ liệu hoàn chỉnh tốn bao lâu? | Chính xác phần nào gây chậm nếu thiếu profiling. |
| Đo allocation/GC | Có bao nhiêu byte/object được cấp phát, tác động GC? | CPU nhanh hơn chỉ vì allocation thấp hơn? |
| Đo throughput nhiều yêu cầu | Hệ thống hoàn thành bao nhiêu tác vụ mỗi giây? | Latency p95/p99 chắc chắn cũng tốt hơn? |
| Profiling | CPU/hot methods, waiting, memory allocation ở đâu? | Một phép đo profile luôn giống môi trường production? |

Mục tiêu bài này là xây một microbenchmark **công bằng và đáng tin cậy**, sau đó giải thích cách xác nhận kết luận ở mức ứng dụng.

### 5.1. Điều kiện của phép đo

- Cùng một phiên bản JDK, cấu hình JVM và cách GC.
- Máy ở trạng thái tương đối ổn định, không chạy đồng thời nhiều tác vụ nặng.
- Ghi CPU vật lý/ảo, số lõi hiệu dụng, giới hạn container và giới hạn bộ nhớ.
- Nguồn dữ liệu giống nhau, tạo trước khi đo.
- Không đưa `println` hoặc file/network I/O vào hàm benchmark.
- Không thay đổi kích thước nguồn giữa các lần chạy một phép đo.
- Đo nhiều vòng, báo phân tán kết quả, tránh chỉ dùng "lần nhanh nhất".
- Đổi trạng thái benchmark hoặc fork để hạn chế ảnh hưởng thứ tự gọi và profile JIT.
- Nếu dữ liệu nằm gọn trong cache so với lớn hơn cache, đánh giá như hai workload **khác nhau**.

### 5.2. Vì sao `System.nanoTime()` một lần dễ đánh lừa?

Ví dụ:

```java
long start = System.nanoTime();
long result = FairStreamComparison.withSequentialStream(data);
long elapsed = System.nanoTime() - start;

System.out.println(result);
System.out.println(elapsed);
```

Đoạn trên cho thời gian của **một lần thực hiện trong một trạng thái JVM cụ thể**. Nó có thể chịu ảnh hưởng của:

- Nạp lớp và khởi tạo lần đầu.
- JIT biên dịch, deoptimization và tiered compilation.
- Tần số CPU, nhiệt độ, scheduler, hoạt động nền.
- GC, phân trang bộ nhớ và cache.
- Nhiễu từ lần benchmark trước.
- Chi phí đọc đồng hồ chiếm tỷ lệ lớn khi hàm quá ngắn.

Số nano-giây thu được không vô nghĩa; nó **chưa đủ để so sánh công bằng** hoặc đưa ra kết luận tổng quát. Hãy dùng harness benchmark như **JMH** để giảm những rủi ro thường gặp.


## 6. Dùng JMH để đo có kiểm soát

**JMH (Java Microbenchmark Harness)** là bộ công cụ benchmark dành cho JVM. Nó giúp tổ chức warm-up, thời gian đo, fork, số thread và cách tiêu thụ kết quả. Đây không phải thành phần của `java.base`: muốn chạy mẫu JMH cần **thêm dependency và annotation processor JMH** theo hướng dẫn của phiên bản JMH được dự án sử dụng.

JMH giải quyết nhiều sai sót kỹ thuật thường gặp, nhưng **không tự làm cho một workload không tương đương trở nên công bằng**. Người viết benchmark vẫn phải giữ cùng đầu vào, cùng ngữ nghĩa và hiểu phần nào đang nằm trong thời gian đo.

### 6.1. Ví dụ benchmark Java 8+ dùng cùng nguồn

Tạo lớp `LoopVsStreamBenchmark.java` trong một **module hoặc project benchmark riêng đã cấu hình JMH**:

```java
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
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1,
        timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1,
        timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class LoopVsStreamBenchmark {

    // Trải nghiệm ba quy mô khác nhau.
    @Param({"128", "10000", "1000000"})
    public int size;

    private long[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = new long[size];

        SplittableRandom random =
            new SplittableRandom(20261118L);

        for (int i = 0; i < data.length; i++) {
            data[i] = random.nextInt(1, 10_001);
        }
    }

    @Benchmark
    public long loop() {
        long sum = 0L;

        for (long value : data) {
            if ((value & 1L) == 0L) {
                sum += value * value;
            }
        }

        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return Arrays.stream(data)
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    @Benchmark
    public long parallelStream() {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }
}
```

**Các điểm thiết kế công bằng:**

- `@Param` thay đổi **kích thước mảng**, ba phương án luôn nhận cùng một mảng với cùng giá trị trong mỗi trial.
- `@Setup(Level.Trial)` tạo dữ liệu **ngoài phần đo của `@Benchmark`**.
- `SplittableRandom` với seed cố định làm dữ liệu **có thể tái hiện**; không cần RNG bên trong benchmark.
- `@Benchmark` trả `long` để harness quan sát kết quả.
- `@Warmup` cho JVM thời gian tối ưu các đoạn code thường chạy.
- `@Measurement` đo nhiều vòng; không lấy đúng một con số của lần chạy đầu.
- `@Fork(2)` yêu cầu **hai JVM fork riêng** cho mỗi cấu hình, giảm phụ thuộc vào trạng thái của đúng một JVM.
- `@BenchmarkMode(Mode.AverageTime)` đo **thời gian trung bình cho một operation** của benchmark.
- `@OutputTimeUnit(TimeUnit.MICROSECONDS)` chọn đơn vị hiển thị. Nó **không quyết định độ chính xác tuyệt đối** của phép đo.

Với `@State(Scope.Benchmark)`, mảng dữ liệu được chia sẻ cho các thread benchmark cùng trial. Ở đây các phương thức **chỉ đọc mảng**, nên không có race trên dữ liệu nguồn. Mẫu được thiết kế cho một tác vụ độc lập tại một thời điểm; khi đo tải đa yêu cầu cần thiết lập số thread và điều kiện tương ứng riêng.

### 6.2. Cấu hình dự án JMH

Để biên dịch mã có `org.openjdk.jmh.annotations`, cần:

1. Thư viện JMH core tương ứng với JDK và hệ build.
2. Bộ sinh mã annotation processor của JMH.
3. Cách đóng gói/chạy benchmark do build tool hướng dẫn.

Không thể chỉ dùng lệnh `javac LoopVsStreamBenchmark.java` **mà chưa cấu hình JMH** rồi kỳ vọng thành công, vì các lớp annotation không thuộc JDK.

Một cấu hình Maven/Gradle chuẩn cho JMH thường tạo runner hoặc gói benchmark riêng. Sau khi đóng gói theo hướng dẫn của cấu hình đó, có thể chạy những phép thử theo tên benchmark và thêm profiler phân bổ bộ nhớ như `-prof gc`. Đường dẫn JAR và version cụ thể tùy project, vì vậy không nên hardcode một tên file không tồn tại.

**Lưu ý:** Bài này cung cấp ví dụ học tập; không khẳng định đã thực thi hay biên dịch JMH trên máy của người học.

### 6.3. Đọc một dòng kết quả JMH

Đầu ra của JMH thường gồm benchmark, tham số, mode, số lần/đơn vị đo, điểm đo và sai số ước lượng.

Ví dụ **cấu trúc bảng kết quả cần ghi**, các ô còn trống vì chưa đo:

| size | Cách xử lý | Average time / operation | Độ phân tán | Allocation / operation |
| ---: | --- | ---: | ---: | ---: |
| 128 | Vòng lặp | Cần đo | Cần đo | Cần đo |
| 128 | Stream tuần tự | Cần đo | Cần đo | Cần đo |
| 128 | Stream song song | Cần đo | Cần đo | Cần đo |
| 10.000 | Vòng lặp | Cần đo | Cần đo | Cần đo |
| 10.000 | Stream tuần tự | Cần đo | Cần đo | Cần đo |
| 10.000 | Stream song song | Cần đo | Cần đo | Cần đo |
| 1.000.000 | Vòng lặp | Cần đo | Cần đo | Cần đo |
| 1.000.000 | Stream tuần tự | Cần đo | Cần đo | Cần đo |
| 1.000.000 | Stream song song | Cần đo | Cần đo | Cần đo |

**Không điền số tùy đoán** vào bảng rồi coi là bằng chứng "Stream chậm x lần" hay "parallel nhanh y lần". Những số đó cần xuất phát từ JMH thực tế, có mô tả môi trường và cách chạy.

### 6.4. Average time và throughput khác nhau

Với benchmark đo thời gian trung bình:

- Điểm đo **nhỏ hơn** thường là nhanh hơn cho một operation.
- Nếu đo `Mode.Throughput`, điểm đo **lớn hơn** thường là tốt hơn vì đó là số operation hoàn thành mỗi đơn vị thời gian.
- Hai mode dùng đơn vị và cách diễn giải khác; không so trực tiếp số "microseconds/op" với "ops/s".

Nếu một yêu cầu ứng dụng gồm nhiều bước, thời gian benchmark một hàm có thể **không tỷ lệ** với thời gian phản hồi toàn yêu cầu. Vì vậy, có thể cần benchmark end-to-end sau khi đã chọn được các hướng triển khai hợp lý.

## 7. Warm-up, JIT và trạng thái của JVM

JVM không nhất thiết thực thi toàn bộ Java code theo cùng một cách từ lần đầu tới lần cuối. JIT có thể biên dịch lại phương thức "nóng", inline lambda, tối ưu biểu thức, hoặc thay đổi chiến lược sau khi quan sát kiểu dữ liệu.

### 7.1. Vì sao đo ba cách lần lượt dễ sai?

Sai về phương pháp:

```java
long a = time(loop);
long b = time(sequential);
long c = time(parallel);
```

Ở đây `time` chỉ là ký hiệu minh họa một hàm đo; nếu tạo ba lần đo liên tiếp trong cùng JVM, nhánh chạy đầu tiên có thể chịu chi phí nạp lớp/JIT mà nhánh sau không chịu. Nếu đổi thứ tự gọi, kết quả có thể đảo chiều.

Warm-up và fork không loại hết mọi nhiễu, nhưng giúp giảm nhầm lẫn giữa **tác dụng của JIT** với **chi phí thật của thuật toán**.

### 7.2. Warm-up không phải một con số thần kỳ

Năm iteration là một lựa chọn minh họa cho JMH, **không phải giá trị tối ưu mặc định**:

- Workload rất ngắn có thể cần nhiều vòng để đạt trạng thái tương đối ổn định.
- Workload có nhiều code path hoặc dữ liệu phân nhánh phức tạp cần đảm bảo các nhánh quan trọng được chạy.
- Quá nhiều warm-up trong benchmark nặng có thể làm máy nóng, thay đổi xung CPU hoặc tạo áp lực GC.
- Nên kiểm tra kết quả giữa các fork và mức phân tán, thay vì chỉ tăng số iteration cho tới khi có con số mong muốn.

Một bản báo cáo đo có trách nhiệm nên ghi cấu hình warm-up, measurement, fork, tham số và điều kiện tải.

### 7.3. Đầu vào ngẫu nhiên phải được tạo ngoài vùng đo

Sai:

```java
@Benchmark
public long bad() {
    SplittableRandom random = new SplittableRandom();
    long[] values = new long[1_000_000];

    for (int i = 0; i < values.length; i++) {
        values[i] = random.nextLong();
    }

    return Arrays.stream(values).sum();
}
```

Nếu mục tiêu là đo **chỉ việc xử lý mảng đã có**, ví dụ trên đo cả cấp phát và sinh dữ liệu. Điều đó không sai nếu bài toán thực tế yêu cầu **tạo mảng + xử lý**, nhưng không công bằng khi nhánh vòng lặp được nhận mảng có sẵn.

Tùy câu hỏi, có thể thiết kế hai benchmark riêng:

- **Processing-only:** cả ba dùng cùng mảng tạo trong `@Setup`.
- **End-to-end:** cả ba đo toàn chuỗi tạo/đọc/biến đổi, với công việc tạo nguồn tương đương.

Đừng trộn hai phép đo vào một bảng mà không ghi phạm vi.

## 8. Lỗi loại bỏ tính toán và tối ưu hóa quá mức

Trong benchmark nhỏ, compiler có thể tối ưu các phép tính chỉ dùng hằng số hoặc không có đầu ra quan sát được. Vì thế:

```java
@Benchmark
public void ineffective() {
    long result = 1L + 2L + 3L;
    // Khong su dung result.
}
```

không đo công việc cộng như kỳ vọng. Ngược lại:

```java
@Benchmark
public long observable() {
    return 1L + 2L + 3L;
}
```

có kết quả được quan sát nhưng compiler vẫn có thể **constant-fold** thành hằng số 6. Đây là bài kiểm tra khả năng tối ưu phép tính hằng, không phải workload xử lý dữ liệu.

Benchmark của bài tránh lỗi này bằng:

- Đọc một mảng được khởi tạo trước từ trạng thái JMH.
- Kết quả phụ thuộc nội dung mảng.
- Trả về `long` cho harness.
- Thay đổi kích thước mảng bằng `@Param` để đo nhiều ngưỡng công việc.

Dù vậy, không có cách nào đảm bảo compiler **không thực hiện một tối ưu hợp lệ**. Benchmark tốt không cố "cấm JIT tối ưu", mà cố đo phương án thực tế sau tối ưu hóa, với dữ liệu và điều kiện đại diện.

Nếu phương thức cần nhiều kết quả hoặc có nhiều output, JMH cung cấp `Blackhole` để tiêu thụ giá trị thay vì in ra console. Chỉ dùng Blackhole khi hiểu nó cần thiết; không thêm một thao tác tiêu thụ tốn kém khác nhau giữa các nhánh.

## 9. Đừng tạo lợi thế không công bằng bằng cách thay đổi thuật toán

Ba phiên bản chính cùng lọc và bình phương. Nhưng có thể tối ưu một cách:

```java
// Một cách tính khác nếu nguồn là dãy 1..N
// có thể dùng công thức số học đóng.
// Điều này không còn là cùng triển khai xử lý mảng bất kỳ.
```

Một thuật toán khác có thể nhanh hơn rất nhiều. Đó là **so sánh thuật toán**, không thuần túy là **so sánh cấu trúc vòng lặp/Stream**.

Tương tự, nếu một nhánh dùng `sum()`, nhánh khác dùng `collect(toList())` rồi tính tổng trong vòng lặp thứ hai, ta đang đo cả việc cấp phát list trung gian. Kết quả có ý nghĩa nếu nhiệm vụ **thực sự cần list đó**, nhưng không công bằng cho bài toán chỉ yêu cầu tổng.

### 9.1. Tránh materialization khác nhau

Với bài toán chỉ tính tổng:

```java
// Chi phi bo sung khong can thiet:
List<Long> squared = Arrays.stream(data)
    .filter(x -> (x & 1L) == 0L)
    .map(x -> x * x)
    .boxed()
    .collect(Collectors.toList());

long result = squared.stream()
    .mapToLong(Long::longValue)
    .sum();
```

Pipeline này tạo collection trung gian và boxing. Không dùng nó làm đại diện cho hiệu năng `LongStream` nếu mục tiêu là so sánh terminal `sum`.

### 9.2. Cẩn thận với `count()` và tính lazy

`LongStream.count()` có thể dùng thông tin kích thước nguồn và bỏ qua những bước không làm thay đổi số phần tử. Ví dụ, một phép `map` có tác dụng phụ không nhất thiết được chạy chỉ vì terminal `count` được gọi.

Do đó nếu benchmark kỳ vọng tính chi phí `map` nhưng kết thúc bằng `count()`, rất có thể đang đo **một pipeline không thực thi phần công việc muốn đo**.

```java
// KHÔNG NÊN dùng để đo chi phí tính toán trong map:
long count = Arrays.stream(data)
    .map(x -> expensiveCalculation(x))
    .count();
```

Trong ví dụ, `expensiveCalculation` chỉ là tên hàm minh họa. Nếu `map` không thay đổi số lượng, `count` có thể không đánh giá mapper. Hãy chọn một terminal operation thực sự cần **giá trị đầu ra của mapper**, như `sum` trong benchmark chính.

### 9.3. Không lẫn chi phí khởi tạo mảng vào một phương án

So sánh sai:

```java
// Nhánh A: mảng có sẵn.
long a = FairStreamComparison.withLoop(data);

// Nhánh B: tạo bản sao rồi mới chạy.
long b = FairStreamComparison.withSequentialStream(
    Arrays.copyOf(data, data.length));
```

Nhánh B đang đo thêm một bước sao chép O(n). Nếu yêu cầu ứng dụng thực tế đòi snapshot để an toàn khi dùng song song, hãy đưa **chi phí snapshot** vào báo cáo riêng, không coi đó là chi phí cố hữu của mọi Stream.

## 10. Một phép đo công bằng có thể vẫn cho kết quả không mong đợi

Kết quả có thể thay đổi đáng kể theo kích thước:

- **Dữ liệu rất nhỏ:** chi phí tạo pipeline và điều phối song song có thể lớn so với một vòng lặp đơn giản.
- **Dữ liệu vừa:** JIT có thể tối ưu nhiều phần của Stream tuần tự; chênh lệch với loop không phải lúc nào cũng đáng kể.
- **Dữ liệu lớn, độc lập, CPU-bound:** Stream song song có cơ hội dùng nhiều lõi hiệu quả hơn, nhưng vẫn phải trả chi phí split/combine.
- **Dữ liệu rất lớn so với cache:** băng thông bộ nhớ có thể trở thành giới hạn, nên thêm thread không cải thiện tuyến tính.
- **Dữ liệu có lọc phức tạp hoặc phân bố lệch:** chi phí mỗi phần tử khác nhau có thể gây mất cân bằng tải.

Đó là các **khả năng cần kiểm chứng**, không phải thứ tự xếp hạng cố định. Nếu benchmark cho thấy Stream tuần tự ngang hoặc nhanh hơn vòng lặp trong một workload, đừng sửa số liệu để khớp định kiến. Kiểm tra tính đúng, noise và môi trường, sau đó báo cáo điều quan sát được.

### 10.1. Không suy từ microbenchmark sang "mọi ứng dụng"

Nếu toàn ứng dụng dành 90% thời gian chờ database, tối ưu phần xử lý CPU chiếm 10% **không thể tự làm tốc độ toàn ứng dụng tăng theo cùng tỷ lệ**.

Định luật Amdahl cho một ước tính trực quan:

\[
Speedup_{\text{total}}
=\frac{1}{(1-p)+p/s}
\]

Trong đó `p` là tỷ phần thời gian có thể cải thiện, `s` là mức tăng tốc của phần đó. Với `p = 0,10` và `s = 4`:

\[
Speedup_{\text{total}}=\frac{1}{0,9+0,1/4}
\approx 1,081
\]

Mặc dù phần tính toán đó nhanh hơn bốn lần, toàn ứng dụng chỉ cải thiện lý thuyết khoảng **8%** nếu những điều kiện mô hình giữ nguyên.

Công thức là **mô hình giới hạn**; tải thực có thể thay đổi, các tác vụ tranh chấp tài nguyên hoặc giảm throughput. Không dùng nó để thay phép đo end-to-end.


## 11. Đo chi phí bộ nhớ và GC thay vì chỉ đo thời gian

Cùng trả một kết quả không có nghĩa ba cách có cùng **allocation** hoặc áp lực lên garbage collector.

### 11.1. Những chỗ có thể phát sinh cấp phát

- **Vòng lặp trên `long[]`:** có thể chỉ cần vài biến primitive cục bộ; bản thân vòng lặp không buộc tạo list hay đối tượng mỗi phần tử.
- **`LongStream` tuần tự:** tạo cấu trúc mô tả pipeline, một số đối tượng nội bộ; JIT có thể tối ưu/cấp phát khác nhau tùy JVM và code path.
- **`LongStream.parallel()`:** ngoài pipeline còn có hoạt động chia công việc, quản lý tác vụ và ghép kết quả, tùy nguồn và triển khai.
- **`Stream<Long>`:** có thể thêm boxing/unboxing và áp lực bộ nhớ so với `LongStream`; các tối ưu JIT có thể làm chi phí thực tế thay đổi.
- **`collect(toList())`:** phải giữ các phần tử kết quả trong một collection, khác hẳn `sum()` chỉ tạo một số tổng.
- **`sorted`, `distinct`, `groupingBy`:** là những ví dụ có thể cần cấu trúc trung gian đáng kể; không đưa ngầm vào một nhánh duy nhất.

Không nên khẳng định "Stream luôn cấp phát N đối tượng" hay "loop luôn cấp phát 0 byte" trên mọi JVM. Điều cần báo cáo là **số liệu đo trên cấu hình cụ thể**, kể cả khả năng JIT loại bỏ một số allocation.

### 11.2. Dùng JMH GC profiler

Sau khi cấu hình JMH và đóng gói benchmark runner theo quy trình của dự án, có thể kích hoạt profiler GC bằng tùy chọn:

```text
-prof gc
```

Một số chỉ số JMH thường hiển thị gồm:

| Chỉ số | Ý nghĩa | Giới hạn diễn giải |
| --- | --- | --- |
| `gc.alloc.rate.norm` | Số byte được cấp phát chuẩn hóa theo một operation | Không phải số byte còn sống sau GC. |
| `gc.alloc.rate` | Tốc độ cấp phát theo thời gian | Phụ thuộc throughput và mode đo. |
| `gc.count` | Số lần GC trong khoảng đo | Có thể bằng 0 trong một phép thử ngắn. |
| `gc.time` | Thời gian GC ghi nhận | Không tự phản ánh toàn bộ chi phí bộ nhớ hay latency. |

Các chỉ số phụ thuộc phiên bản JMH, JDK và profiler khả dụng. Nếu profiler không cung cấp một chỉ số, hãy báo là **không có số liệu**, đừng tự suy ra số 0.

### 11.3. Allocation khác live heap và RSS

Ba khái niệm hay bị nhầm:

1. **Allocated bytes:** tổng byte được cấp phát trong một khoảng thời gian; đối tượng có thể chết nhanh.
2. **Live heap:** bộ nhớ heap đang được giữ bởi các đối tượng còn sống.
3. **RSS/process memory:** bộ nhớ vật lý mà tiến trình chiếm dụng; còn có stack thread, native buffers, metadata và những vùng ngoài heap.

Một pipeline có thể cấp phát nhiều đối tượng ngắn hạn nhưng live heap thấp. Ngược lại, một `collect` giữ danh sách lớn có thể tạo **live heap** đáng kể dù tốc độ cấp phát tại một thời điểm không cao.

Nếu cần hiểu tác động production, có thể bổ sung **JFR (Java Flight Recorder)**, heap profiling hoặc công cụ quan sát allocation phù hợp với môi trường. Không dùng một ảnh chụp Task Manager làm bằng chứng đủ cho hiệu năng bộ nhớ của từng phương án.

## 12. Boxing và cách chọn baseline dữ liệu

`LongStream` và `Stream<Long>` không cùng đặc điểm bộ nhớ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

long[] data = {2L, 3L, 4L, 5L};

// Primitive pipeline.
long primitiveSum = Arrays.stream(data)
    .filter(x -> x % 2L == 0L)
    .map(x -> x * x)
    .sum();

// Object pipeline với boxed Long.
long boxedSum = Arrays.stream(data)
    .boxed()
    .filter(x -> x % 2L == 0L)
    .mapToLong(x -> x * x)
    .sum();

System.out.println(primitiveSum); // 20
System.out.println(boxedSum);     // 20
```

Hai nhánh cho cùng giá trị. Nhưng `boxed()` có thể sinh đối tượng `Long` và `mapToLong` phải làm việc với giá trị từ wrapper. Với dữ liệu lớn, overhead có thể đáng kể, nhưng hãy đo thay vì mặc định một hệ số chậm cố định.

Nếu nghiệp vụ vốn đã lưu `List<Long>`, việc chuyển toàn bộ dữ liệu sang `long[]` cũng có chi phí. Lúc đó có thể thực hiện **hai nhóm thí nghiệm**:

- **Cùng nguồn `long[]`:** so loop với `LongStream` tuần tự/song song.
- **Cùng nguồn `List<Long>`:** so loop qua list với `list.stream().mapToLong(...)` và `list.parallelStream().mapToLong(...)`.

Đừng lấy thời gian của loop trên mảng so với Stream trên list rồi kết luận riêng "Stream chậm". Cả **bố cục dữ liệu** và **truy cập bộ nhớ** đã thay đổi.

### 12.1. Không tạo list trung gian chỉ để benchmark tổng

`Collectors.toList()` lưu toàn bộ đầu ra; `sum()` chỉ cần giá trị tổng hợp. Đó là hai **hợp đồng kết quả khác nhau**. Nếu ứng dụng thực cần list để hiển thị, benchmark nên trả list hoặc tính phí xây list cho **cả ba** cách. Nếu chỉ cần tổng, cả ba nên chỉ trả tổng.

## 13. Vì sao `parallel()` có thêm chi phí?

Một parallel stream thường có các giai đoạn khái niệm:

```text
                long[] nguồn
                     |
                Spliterator
                     |
             chia phần công việc
              /      |      \
           vùng A  vùng B   vùng C
              |      |      |
           filter + map + tổng cục bộ
              \      |      /
                ghép tổng
                     |
                một giá trị long
```

Trong những triển khai JDK thông dụng, Stream song song thường sử dụng cơ chế fork/join và có thể sử dụng `ForkJoinPool.commonPool()`. Nhưng API Stream **không hứa** một số thread cố định, cách chia cố định hay việc mỗi phần tử thuộc một thread riêng.

Chi phí có thể gồm:

- `Spliterator.trySplit()` và tổ chức các vùng dữ liệu.
- Tạo, lập lịch, di chuyển và ghép các tác vụ.
- Đồng bộ, phối hợp hoặc chờ các phần công việc khác hoàn thành.
- Tương tác cache CPU và băng thông bộ nhớ.
- Chi phí của các thao tác stateful và ràng buộc encounter order.

Vì thế, `parallel()` trên một mảng 128 phần tử với phép nhân đơn giản **có thể chậm hơn** tuần tự. Với một triệu phần tử và mỗi phần tử cần xử lý độc lập đáng kể, nó **có cơ hội** nhanh hơn. Tuy nhiên, không có ngưỡng kích thước "luôn nên song song" dùng được cho mọi máy và workload.

### 13.1. `Spliterator` quyết định khả năng chia

| Nguồn | Đặc tính thường gặp | Ý nghĩa khi đo song song |
| --- | --- | --- |
| `long[]`, `IntStream.range` | Có thể chia nhanh thành các đoạn với kích thước biết trước | Thuận lợi hơn cho công việc CPU-bound độc lập. |
| `ArrayList` | Có khả năng chia theo vùng chỉ số | Thường là nguồn tốt để thử song song. |
| `LinkedList` | Không có truy cập chỉ số nhanh như mảng | Cách chia theo lô có overhead khác; cần đo. |
| `Stream.iterate` | Có thể phụ thuộc phần tử trước, khó chia cân bằng trong một số trường hợp | Không tự động suy ra hiệu năng tốt khi song song. |
| `Files.lines` hoặc iterator I/O | Có thể cần đọc tuần tự và gắn với tài nguyên | Song song không tự làm việc đọc tệp hay mạng nhanh hơn. |

Không nên so sánh vòng lặp dùng truy cập ngẫu nhiên với Stream trên nguồn có `Spliterator` khó chia rồi quy mọi khác biệt cho `parallel()`.

### 13.2. Chi phí mỗi phần tử không đồng đều

Nếu nửa đầu mảng xử lý rất nhẹ, nửa sau xử lý rất nặng, chia thành hai vùng bằng số lượng **không có nghĩa cân bằng tải**. Runtime có thể tách thêm phần việc, nhưng không có bảo đảm giải quyết hết sự lệch tải.

Ngoài số lượng phần tử, còn phải xem **phân phối thời gian xử lý**, mức tranh chấp tài nguyên và giới hạn số lõi thực tế.

## 14. Tác động của thứ tự và thao tác có trạng thái

Trong benchmark chính, phép lọc số chẵn và ánh xạ bình phương là các thao tác stateless; phép `sum()` không cần thứ tự các phần tử. Đây là workload thuận lợi để **tách và ghép**.

Nhưng một pipeline nghiệp vụ có thể chứa:

| Thao tác | Ràng buộc/chi phí thường gặp |
| --- | --- |
| `map`, `filter` thuần | Các phần tử có thể xử lý độc lập. |
| `sorted` | Cần phối hợp sắp xếp, có thể dùng bộ nhớ trung gian lớn. |
| `distinct` trên ordered stream | Giữ phần tử xuất hiện đầu có thể cần phối hợp nhiều hơn. |
| `limit(n)`, `skip(n)` trên ordered parallel stream | Xác định đúng vị trí có thể tốn công phối hợp. |
| `findFirst` | Tôn trọng phần tử đầu theo encounter order, có thể hạn chế song song. |
| `findAny` | Có thể trả phần tử phù hợp bất kỳ, cho phép giảm một số ràng buộc. |
| `groupingBy` | Có thể phải tạo map cục bộ và ghép map. |
| `groupingByConcurrent` | Có thể tích lũy đồng thời trong điều kiện phù hợp, nhưng có tranh chấp và ảnh hưởng thứ tự. |

Kết quả benchmark `filter/map/sum` **không dự đoán** hiệu năng của `sorted/distinct/groupingBy`. Nếu hệ thống sử dụng nhiều pipeline khác nhau, hãy chọn vài **workload đại diện** thay vì một benchmark "tổng quát" không đại diện.

### 14.1. Đừng bỏ `ORDERED` chỉ để thắng benchmark

`unordered()` có thể cho phép những tối ưu hóa nhất định. Nhưng nếu nghiệp vụ cần **phần tử đầu tiên**, **top-k theo một thứ tự cụ thể**, hoặc **báo cáo theo thứ tự**, việc bỏ encounter order đã thay đổi hợp đồng.

Không hợp lệ:

```java
// Nhánh tuần tự giữ đúng các phần tử đầu.
// Nhánh song song bỏ ORDERED để nhanh hơn.
//
// Đây không còn là phép so sánh cùng ngữ nghĩa.
```

Nếu yêu cầu nghiệp vụ thực sự **không quan tâm thứ tự**, hãy ghi rõ từ đầu; có thể đo cả lựa chọn `unordered` như một phương án hợp lệ, với cùng hợp đồng ở mọi nhánh.

## 15. Trạng thái chia sẻ có thể làm sai cả tính đúng lẫn benchmark

Ví dụ sai:

```java
import java.util.ArrayList;
import java.util.List;

List<Long> result = new ArrayList<>();

Arrays.stream(data)
    .parallel()
    .filter(x -> (x & 1L) == 0L)
    .forEach(result::add);
```

`ArrayList` không an toàn khi nhiều thread cùng sửa; kết quả có thể mất, lặp hoặc xảy ra lỗi. Không đo performance của một triển khai **không đúng về ngữ nghĩa** rồi coi nó là ứng viên tối ưu.

Thay bằng collector hoặc terminal operation phù hợp:

```java
List<Long> result = Arrays.stream(data)
    .parallel()
    .filter(x -> (x & 1L) == 0L)
    .boxed()
    .collect(java.util.stream.Collectors.toList());
```

Ví dụ này trả list và có boxing, nên chỉ so sánh với vòng lặp **cũng phải xây list kết quả tương đương**. Đó là một benchmark khác với phép tổng của bài.

### 15.1. `AtomicLong` không thay cho `sum()`

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong total = new AtomicLong();

Arrays.stream(data)
    .parallel()
    .forEach(x -> total.addAndGet(x));
```

Cách này có thể cho kết quả tổng đúng theo mô hình số nguyên, nhưng nhiều thread cùng cập nhật **một biến chia sẻ**, tạo tranh chấp. `AtomicLong` giải quyết một phần an toàn ghi, **không làm phép tổng này tương đương về chi phí** với `LongStream.sum()`.

Nếu nghiệp vụ chỉ cần tính tổng, dùng:

```java
long sum = Arrays.stream(data)
    .parallel()
    .sum();
```

`sum` có thể dùng tổng cục bộ rồi ghép, tránh việc mỗi phần tử phải cập nhật một điểm chia sẻ. Benchmark chính đã dùng `sum` ở cả hai chế độ Stream.

### 15.2. Side effect còn khiến phép đo không lặp lại được

Các lambda cập nhật bộ đếm toàn cục, ghi log hoặc gọi I/O có thể làm thời gian đo phụ thuộc mức tranh chấp và tải bên ngoài. Nếu đó là yêu cầu nghiệp vụ thật, phải đo **chính yêu cầu đó**; nếu mục tiêu là đo chi phí pipeline thuần, hãy bỏ chúng khỏi cả ba cách.

## 16. Parallel stream và workload đồng thời trong server

Một microbenchmark với một lời gọi `parallelStream` riêng lẻ không thể tự trả lời việc một dịch vụ xử lý **100 yêu cầu đồng thời** có nhanh hơn không.

Khi nhiều yêu cầu cùng khởi chạy parallel stream:

- Các pipeline có thể cùng dùng cơ chế worker/pool chung.
- Số tác vụ tăng nhưng số lõi CPU hữu dụng không tăng tương ứng.
- Có thể tăng tranh chấp cache, băng thông bộ nhớ và thời gian chờ.
- Thời gian một yêu cầu có thể giảm trong điều kiện riêng lẻ nhưng throughput toàn dịch vụ lại giảm.
- Trong container, số CPU quota hoặc giới hạn cgroup có thể khác số lõi được JVM/OS báo ở một số cấu hình.

Với công việc **blocking** như gọi HTTP, JDBC hoặc chờ tệp, không mặc định dùng parallel stream để thay thế một mô hình quản lý I/O có giới hạn concurrency/backpressure. Việc giữ worker chờ tài nguyên có thể gây ảnh hưởng cho những tác vụ khác.

### 16.1. Cần hai mức đo cho ứng dụng dịch vụ

1. **Mức hàm:** JMH so loop/sequential/parallel trên cùng dữ liệu với một hoặc nhiều kích thước nguồn.
2. **Mức dịch vụ:** load test với lưu lượng và số yêu cầu đồng thời thực tế, đo throughput, latency p50/p95/p99, CPU, GC và áp lực I/O.

Nếu cả hai mức đo đều cho lợi ích ổn định và ứng dụng bảo toàn tính đúng, thay đổi mới có cơ sở để triển khai. Không quyết định chỉ từ microbenchmark chạy trên laptop rảnh CPU.

## 17. Bộ nhớ cache, locality và băng thông

Một mảng `long[]` thường có tính **locality** tốt vì các phần tử primitive nằm liên tiếp theo cách Java quản lý mảng. Vòng lặp và `LongStream` đều có thể tận dụng đặc tính nguồn đó.

Với các kích thước:

- **128 phần tử:** dữ liệu rất nhỏ, có thể nằm trong cache; chi phí khởi tạo pipeline/split có tỷ trọng lớn.
- **10.000 phần tử:** chi phí xử lý và cache bắt đầu khác tùy CPU.
- **1.000.000 phần tử:** cần đọc lượng dữ liệu lớn hơn; băng thông bộ nhớ có thể hạn chế tốc độ.

Các giá trị này chỉ là **quy mô thí nghiệm**, không tương ứng cứng với mức cache L1/L2/L3 trên mọi CPU.

Khi đo song song, phân biệt:

- **CPU-bound:** phần lớn thời gian dùng để tính toán.
- **Memory-bound:** chờ dữ liệu từ bộ nhớ hoặc bị giới hạn băng thông.
- **Synchronization-bound:** nhiều worker chờ lock hoặc tranh chấp dữ liệu dùng chung.
- **I/O-bound:** chờ nguồn/đích ngoài CPU.

Một pipeline đọc mảng và làm rất ít phép toán mỗi phần tử có thể nhanh chóng bị giới hạn bởi bộ nhớ. Thêm thread chỉ giúp tới một mức nhất định. Nếu dùng `List<Long>`, việc theo các tham chiếu tới object có thể làm locality khác mảng primitive.

## 18. Cách diễn giải kết quả benchmark có trách nhiệm

Một báo cáo nên nêu:

- **Mục tiêu:** tính tổng bình phương số chẵn trên mảng `long[]`, dữ liệu 1..10.000.
- **Biến thay đổi:** vòng lặp, Stream tuần tự, Stream song song.
- **Thông số:** các size, số iteration warm-up/measurement, số fork, mode/đơn vị JMH.
- **Môi trường:** hệ điều hành, JDK, JVM options, CPU, heap, giới hạn container và tải nền.
- **Kết quả:** số đo thực tế, độ phân tán và allocation/GC nếu có.
- **Tính đúng:** mọi nhánh trả cùng kết quả, có kiểm tra riêng bằng giá trị tính tay.
- **Giới hạn:** chỉ áp dụng cho workload và cách đo; chưa kết luận các pipeline khác.
- **Quyết định:** chọn phương án nào cho workload đó và lý do, không chỉ vì giá trị nhanh nhất.

### 18.1. Tỷ lệ tăng tốc nên tính như thế nào?

Nếu hai giá trị thời gian **được đo trong cùng điều kiện và cùng đơn vị**, có thể tính:

```text
speedup = thời_gian_baseline / thời_gian_candidate
```

Ví dụ **toán học giả định**, không phải số liệu đo:

```text
baseline = 40 microseconds/op
candidate = 20 microseconds/op
speedup = 40 / 20 = 2.0
```

Trường hợp đó candidate chạy nhanh gấp hai lần **cho operation được đo**. Nếu `speedup = 0,5`, candidate chậm gấp hai lần baseline. Với throughput, cách suy diễn tỷ lệ phải dùng chính đơn vị **operations/second**, không đảo lộn hướng tốt/xấu.

Nếu chênh lệch nhỏ hơn mức nhiễu hoặc độ phân tán đáng kể, không nên tuyên bố chắc chắn một phương án nhanh hơn. Nên chạy thêm phép đo hoặc kết luận rằng **chưa có bằng chứng đủ mạnh** về khác biệt.

### 18.2. Đừng chỉ chọn giá trị trung bình nhỏ nhất

Cần xem:

- Kết quả giữa các fork có nhất quán không?
- Có outlier bất thường do GC, throttling hoặc tải nền không?
- Tỷ lệ allocation có thay đổi lớn không?
- Kết quả có giữ đúng khi size tăng/giảm không?
- Có gây xấu đi latency hoặc throughput khi nhiều yêu cầu đồng thời không?
- Mức lợi ích có đủ lớn để đánh đổi độ phức tạp của code không?

Không chọn `parallel()` chỉ vì nó thắng 1/10 lần chạy. Cũng không bỏ Stream tuần tự chỉ vì một benchmark nhỏ cho thấy nó chậm hơn vài micro-giây nhưng pipeline nghiệp vụ dễ bảo trì hơn và không nằm trong hot path.

## 19. Bài tập thực hành

### Bài 1 — Tìm phép so sánh không công bằng

Một người so vòng lặp trên `long[]` với `Stream<Long>` tạo từ `List<Long>` rồi kết luận mọi Stream đều chậm hơn. Hãy chỉ ra ít nhất ba biến không được kiểm soát.

### Bài 2 — Kiểm chứng tính đúng

Với `data = [1,2,3,4,5,6]`, tính tổng bình phương của các số chẵn. Viết cả vòng lặp và `LongStream`, xác nhận kết quả.

### Bài 3 — Tạo dữ liệu đúng chỗ

Vì sao không nên gọi `new SplittableRandom()` và `new long[1_000_000]` ngay trong một hàm `@Benchmark` nếu chỉ muốn đo chi phí filter/map/sum?

### Bài 4 — JMH warm-up và fork

Giải thích tác dụng của `@Warmup`, `@Measurement`, `@Fork` và `@Param` trong ví dụ benchmark. Mỗi cơ chế xử lý loại rủi ro nào?

### Bài 5 — Đọc số liệu allocation

Một phương án có thời gian trung bình thấp hơn nhưng `gc.alloc.rate.norm` cao hơn đáng kể. Có thể kết luận nó luôn tốt hơn trong ứng dụng dịch vụ không? Cần đo thêm gì?

### Bài 6 — `count()` có đo được phép `map` không?

Vì sao `Arrays.stream(data).map(expensive).count()` có thể không đo chi phí của hàm `expensive`? Nêu một terminal operation phù hợp hơn khi cần dùng kết quả `map`.

### Bài 7 — Song song trên nguồn nhỏ

Với 64 số và mỗi phần tử chỉ thực hiện một phép cộng, vì sao `parallel()` có thể chậm hơn loop? Những khoản overhead nào có thể chiếm ưu thế?

### Bài 8 — Song song và nguồn I/O

Một dịch vụ gọi database cho từng bản ghi trong `parallelStream()`. Những giới hạn về connection pool, latency và worker có thể làm kết quả xấu đi như thế nào?

### Bài 9 — Đánh giá kiểu dữ liệu

Thiết kế một thí nghiệm riêng để so `LongStream` và `Stream<Long>` về tốc độ và allocation mà không nhầm với chênh lệch giữa mảng và list.

### Bài 10 — Phân tích kết quả ngược dự đoán

Một JMH cho thấy Stream tuần tự nhanh hơn loop trong một số cấu hình. Bạn sẽ kiểm tra những điểm nào trước khi khẳng định nguyên nhân?

### Bài 11 — Thứ tự và tính đúng

Một pipeline `sorted().limit(20)` cần lấy 20 giá trị nhỏ nhất. Có được thêm `unordered()` hoặc chuyển `limit` lên trước `sorted` chỉ để tăng tốc không? Vì sao?

### Bài 12 — Microbenchmark và ứng dụng

Một microbenchmark CPU-bound cho speedup 4x, nhưng ứng dụng dành phần lớn thời gian chờ mạng. Vì sao không thể suy ra toàn ứng dụng nhanh hơn 4x?

## 20. Đáp án tham khảo

**Bài 1.** Nguồn `long[]` và `List<Long>` khác bố cục/truy cập bộ nhớ; object stream có boxing/unboxing; có thể khác cách cấp phát nguồn và khởi tạo; còn có thể khác terminal operation. Muốn so loop/Stream, giữ cùng nguồn và primitive type.

**Bài 2.** Tổng là `2² + 4² + 6² = 56`:

```java
long[] data = {1, 2, 3, 4, 5, 6};

long loopSum = 0L;
for (long x : data) {
    if ((x & 1L) == 0L) {
        loopSum += x * x;
    }
}

long streamSum = Arrays.stream(data)
    .filter(x -> (x & 1L) == 0L)
    .map(x -> x * x)
    .sum();

System.out.println(loopSum == streamSum); // true
```

**Bài 3.** Như vậy benchmark đo cả cấp phát mảng và sinh dữ liệu. Dùng `@Setup(Level.Trial)` để tạo dữ liệu trước, rồi ba hàm benchmark chỉ xử lý cùng mảng.

**Bài 4.** Warm-up cho JIT có cơ hội tối ưu code nóng; measurement tập hợp số liệu nhiều iteration; fork chạy trong những JVM riêng để giảm ảnh hưởng trạng thái của một JVM; `@Param` tổ chức nhiều kích thước dữ liệu với cùng logic kiểm thử.

**Bài 5.** Chưa. Allocation cao hơn có thể tăng áp lực GC, giảm throughput hoặc tăng latency ở tải lớn. Cần đo thêm số liệu GC, live heap, RSS, throughput và latency end-to-end trong tải thực tế.

**Bài 6.** `count` có thể suy ra kích thước từ nguồn và bỏ qua mapper không làm đổi số phần tử. Khi benchmark muốn tính `map`, dùng terminal operation như `sum`, `reduce` hay `collect` thực sự cần các giá trị mapper tạo ra.

**Bài 7.** Chia nguồn, lập lịch, điều phối, ghép kết quả và khởi tạo pipeline có thể tốn nhiều hơn 64 phép cộng. Kích thước nhỏ không đủ bù overhead; cần đo trên máy cụ thể.

**Bài 8.** Các lời gọi blocking có thể giữ worker chờ, gây tranh chấp connection pool, queueing và timeout. Nhiều yêu cầu đồng thời có thể tranh tài nguyên với nhau; cần quản lý concurrency và backpressure, không coi parallel stream là giải pháp I/O mặc định.

**Bài 9.** Giữ nguồn `long[]` cho cả hai nhánh. Nhánh primitive gọi `Arrays.stream(data)`, nhánh boxed gọi `Arrays.stream(data).boxed()` rồi cùng filter/map và sum. Đo thời gian và allocation; ghi rõ kết quả phản ánh chi phí **boxing + thay đổi loại stream**, không chỉ một biến thuần túy.

**Bài 10.** Xác nhận kết quả đúng, input giống nhau, benchmark không đo tạo dữ liệu khác nhau, số liệu đủ ổn định, warm-up/fork hợp lý, JDK flags giống nhau, không có hoạt động nền, compiler không tối ưu nhánh khác hợp đồng, và workload có đại diện hay không. Nếu các điều kiện đạt, báo cáo số liệu quan sát được, không ép kết luận theo định kiến.

**Bài 11.** Không được thay đổi thứ tự nếu nghiệp vụ cần 20 giá trị nhỏ nhất **trong toàn nguồn**. `limit(20).sorted()` chỉ sắp 20 phần tử đầu nguồn, khác với `sorted().limit(20)`. `unordered()` còn có thể bỏ ràng buộc encounter order; cần đánh giá kỹ ngữ nghĩa thay vì chỉ nhìn thời gian.

**Bài 12.** Microbenchmark chỉ đo phần CPU được tối ưu; phần lớn thời gian chờ mạng không biến mất. Amdahl giới hạn speedup toàn hệ thống theo tỷ lệ thời gian có thể cải thiện; cần benchmark end-to-end và đo tải thực tế.

## 21. Checklist trước khi công bố kết luận

- [ ] Mô tả **cùng một nhiệm vụ** và kết quả đúng cho mọi phương án.
- [ ] Dùng cùng nguồn và kiểu dữ liệu, không trộn `long[]` với `List<Long>` nếu không phải mục tiêu đo.
- [ ] Kiểm soát tràn số, số thực, thứ tự và chính sách dữ liệu lỗi.
- [ ] Dữ liệu được tạo ngoài vùng đo nếu chỉ muốn đo xử lý.
- [ ] Có test nguồn rỗng, một phần tử, đầu vào biên và dữ liệu lớn.
- [ ] Không in log hay gọi I/O trong hàm benchmark nếu không thuộc workload.
- [ ] Không đặt side effect bắt buộc trong `map`, `peek` hay `forEach` song song.
- [ ] Kết quả được sử dụng; không đo một phép tính có thể bị loại bỏ.
- [ ] Có warm-up, measurement, fork và tham số quy mô phù hợp.
- [ ] Ghi version JDK, JVM flags, số lõi, cấu hình máy và tải nền.
- [ ] Đã đo ít nhất vài kích thước, không chỉ một mảng.
- [ ] Có xem độ phân tán/outlier, không chọn tùy ý kết quả tốt nhất.
- [ ] Có đo allocation/GC khi bài toán liên quan bộ nhớ.
- [ ] Phân biệt allocated bytes, live heap và RSS.
- [ ] Đánh giá chi phí chia/ghép và sự phù hợp của `Spliterator`.
- [ ] Không bỏ encounter order hoặc thay thuật toán chỉ để làm đẹp số đo.
- [ ] Không khẳng định `parallel()` luôn nhanh hơn, nhất là với nguồn nhỏ hoặc blocking I/O.
- [ ] Nếu là ứng dụng dịch vụ, đã kiểm tra throughput và latency dưới tải đồng thời.
- [ ] Nếu chênh lệch nhỏ hơn nhiễu, ghi nhận **chưa đủ bằng chứng**.
- [ ] Quyết định triển khai xét cả tính đúng, độ rõ ràng của code, hiệu năng và khả năng vận hành.

## 22. Tổng kết

Bài toán so sánh vòng lặp, Stream tuần tự và Stream song song phải bắt đầu bằng **một hợp đồng chung**, không phải một chiếc đồng hồ:

```java
// Cùng một long[] và cùng phép tính:
long a = FairStreamComparison.withLoop(data);
long b = FairStreamComparison.withSequentialStream(data);
long c = FairStreamComparison.withParallelStream(data);

// Cả ba phải đúng trước khi đo tốc độ.
if (a != b || a != c) {
    throw new AssertionError("Ket qua khong tuong duong");
}
```

Ghi nhớ:

1. **Công bằng:** cùng nguồn, kiểu, dữ liệu, phép toán và kết quả.
2. **Đúng trước nhanh:** kiểm chứng ca biên và miền số trước benchmark.
3. **Đo đúng:** dùng JMH và hiểu warm-up, fork, measurement, loại bỏ tính toán và phạm vi đo.
4. **Bộ nhớ:** xem boxing, allocation, GC và live heap, không chỉ thời gian.
5. **Song song:** có overhead split/combine, pool/worker và giới hạn CPU/băng thông; không có speedup mặc định.
6. **Ngữ nghĩa quan trọng hơn số đẹp:** không thay đổi thứ tự, side effect hay phép gộp để thắng benchmark.
7. **Quyết định theo workload:** một microbenchmark tốt là bằng chứng cho tác vụ được đo; hiệu quả trong ứng dụng thực cần thêm đo end-to-end.

Vòng lặp thường dễ dự đoán chi phí cho công việc nhỏ và đơn giản; Stream tuần tự giúp diễn đạt pipeline rõ ràng; Stream song song có cơ hội cải thiện tác vụ CPU-bound độc lập, nguồn dễ chia và đủ lớn. Nhưng lựa chọn đúng phải xuất phát từ **kết quả đo có thể tái hiện, tính đúng nghiệp vụ và giới hạn tài nguyên thực tế**, chứ không từ khẩu hiệu rằng một phong cách Java luôn nhanh hơn phong cách còn lại.
