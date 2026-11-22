# Phân biệt phép đo cục bộ với hành vi toàn ứng dụng

> **Chương:** Hiệu năng và tài nguyên  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **đo một phương thức/đoạn mã trong môi trường có kiểm soát** và **đo hành vi của một ứng dụng dưới lưu lượng thực tế**.
2. Chọn đúng đại lượng: **độ trễ (latency)**, **thông lượng (throughput)**, **thời gian CPU**, **phân bổ bộ nhớ**, **bộ nhớ giữ lại**, **số thao tác I/O**, **tỷ lệ lỗi** và mức sử dụng tài nguyên.
3. Nhận diện các yếu tố làm phép đo Java sai lệch: **JIT**, warmup, tối ưu bỏ công việc không quan sát được, **GC**, cache, contention và môi trường chạy.
4. Dùng **JMH** cho microbenchmark, đồng thời hiểu vì sao kết quả `ns/op` không tự suy ra được p95/p99 của API hoặc năng lực toàn hệ thống.
5. Thiết kế đo lường cấp ứng dụng với lưu lượng, dữ liệu, mức đồng thời và trạng thái phụ thuộc phù hợp; đọc đúng p50/p95/p99 và dấu hiệu bão hòa.
6. Dùng profiling, metrics và tracing để nối **vấn đề quan sát từ người dùng** với **nút thắt có bằng chứng**, rồi kiểm tra lại tính đúng đắn và chi phí tài nguyên sau tối ưu.

## 1. Hai phép đo đều đúng nhưng có thể kể hai câu chuyện khác nhau

Giả sử nhóm Java thay một hàm cộng giá trị trong giỏ hàng bằng phiên bản chạy nhanh hơn. Benchmark cục bộ báo thời gian trung bình của hàm giảm từ **200 ns xuống 100 ns**. Tuy nhiên, khi gọi API đặt hàng, p95 vẫn ở khoảng **250 ms** và một số request còn chậm hơn trước.

Hai kết quả này **không tự mâu thuẫn**:

- Microbenchmark đang đo thời gian của **một thao tác nhỏ**, với dữ liệu và điều kiện riêng.
- API đặt hàng còn phải xác thực, gọi database, kiểm tra tồn kho, xử lý thanh toán, đợi tài nguyên, serialize JSON và đi qua mạng.
- Khi có nhiều yêu cầu đồng thời, thời gian **xếp hàng và tranh chấp tài nguyên** có thể lớn hơn nhiều so với chi phí của hàm cộng.
- Chi phí tạo đối tượng, lưu cache, garbage collection hoặc thay đổi cách dùng thread có thể ảnh hưởng tới hệ thống dù đoạn mã riêng lẻ nhanh hơn.

Các con số trên chỉ là **tình huống minh họa**, không phải kết quả đo của dự án. Bài học chính là:

> **Kết quả cục bộ trả lời “đoạn mã này chạy thế nào trong điều kiện benchmark?”; kết quả toàn ứng dụng trả lời “người dùng và hệ thống quan sát được điều gì khi nhiều thành phần hoạt động cùng nhau?”**

Từ góc nhìn chất lượng mã, tối ưu hóa đúng chỗ cải thiện hiệu năng mà vẫn giữ tính đúng đắn, dễ hiểu và khả năng bảo trì. Tối ưu hóa chỉ dựa trên một con số đẹp nhưng không tác động tới rủi ro sản phẩm có thể làm mã khó đọc hơn mà không tạo lợi ích thực.

## 2. Hiểu đối tượng đo trước khi đọc kết quả

Có thể chia đo lường thành những phạm vi sau. Chúng bổ sung cho nhau chứ không thay thế nhau.

| Phạm vi | Câu hỏi chính | Công cụ hoặc cách tiếp cận | Điều chưa chứng minh |
| --- | --- | --- | --- |
| **Microbenchmark** | Phương thức/thuật toán mất bao lâu với đầu vào định trước? | JMH, benchmark harness phù hợp | Toàn bộ API sẽ nhanh hơn tương ứng |
| **Benchmark thành phần** | Một service/component xử lý được bao nhiêu công việc khi tích hợp những phụ thuộc được chọn? | Test component, tải có kiểm soát, metrics | Hạ tầng và toàn hành trình thật đều ổn |
| **Integration benchmark** | Tương tác thật với DB/cache/message broker có chi phí gì? | Tải cùng dependency thật hoặc môi trường gần thật | Người dùng cuối có cùng độ trễ |
| **Load/system test** | Ứng dụng đáp ứng ra sao ở mức lưu lượng và đồng thời cụ thể? | Công cụ tạo tải, metrics hệ thống, tracing | Mọi mùa vụ và mọi trường hợp cực đoan đều đã được kiểm tra |
| **Quan sát production** | Người dùng thực gặp độ trễ/lỗi và bão hòa ở đâu? | Metrics, logs, distributed tracing, profiling được kiểm soát | Nguyên nhân đã được chứng minh chỉ từ tương quan |

Từ “benchmark” không tự nói rõ phạm vi: hãy luôn ghi **đơn vị thao tác, cấu hình chạy, dữ liệu, mức đồng thời, các thành phần thật/giả và chỉ số báo cáo**.

Một phép đo có thể lặp lại chính xác nhưng **không đại diện** cho hành vi cần cải thiện. Ngược lại, quan sát thực tế có thể đại diện tốt nhưng cần thêm profiling hoặc thử nghiệm có kiểm soát mới xác định được nguyên nhân.

### Ví dụ về “đơn vị thao tác”

- `ns/op`: số nanosecond cho **một thao tác được benchmark định nghĩa**; thao tác đó có thể chỉ là một phép biến đổi.
- `ms/request`: thời gian hoàn thành **một yêu cầu HTTP** đo ở một điểm xác định.
- `requests/second`: thông lượng trong một khoảng thời gian và tải cụ thể.
- `bytes/op`: bộ nhớ được cấp phát tính theo một thao tác trong môi trường benchmark, nếu phép đo cung cấp dữ liệu này.
- `CPU-seconds/second` hoặc `% CPU`: lượng CPU tiêu thụ trong một khoảng, cần biết số core và cách công cụ định nghĩa phần trăm.
- `connections in use`, `queue depth`: số tài nguyên đang được sử dụng hoặc công việc đang chờ.

Không được lấy `ns/op` rồi tự đổi thành “API xử lý được X request/s” nếu một request gồm nhiều thao tác, có I/O và nhiều giới hạn khác.

## 3. Thời gian chạy, độ trễ và thông lượng là những đại lượng khác nhau

### 3.1. Latency không chỉ là CPU time

Một request có thể trải qua nhiều khoảng:

~~~text
Client
  ↓ thời gian mạng
API nhận request
  ↓ chờ đến lượt / thread / connection
Xác thực & tính toán
  ↓ chờ DB / cache / dịch vụ ngoài
Xử lý tiếp, serialize kết quả
  ↓ truyền response
Client nhận kết quả
~~~

Thời gian đo ở phía client thường bao gồm mạng và xử lý ở server; thời gian đo trong service chỉ bao gồm ranh giới mà service lựa chọn. **Không so sánh hai số như cùng một đại lượng nếu điểm bắt đầu/kết thúc khác nhau.**

Phân biệt:

- **Wall-clock/elapsed time:** thời gian thực trôi qua giữa hai mốc; có thể bao gồm chờ I/O, scheduler, lock hoặc network.
- **CPU time:** thời gian CPU thực hiện công việc của thread/process theo phạm vi công cụ đo; có thể thấp dù request chờ lâu.
- **Queueing time:** thời gian đợi được phục vụ trước khi bắt đầu thao tác.
- **Service/processing time:** thời gian phục vụ sau khi được nhận theo định nghĩa của thành phần; có thể vẫn gồm thời gian đợi dependency.

Cụm từ “service time” có nhiều định nghĩa giữa các công cụ. Khi viết báo cáo, hãy nêu **ranh giới** thay vì suy từ tên metric.

### 3.2. Throughput không phải nghịch đảo trực tiếp của latency

Nếu một benchmark đơn luồng xử lý một phép tính trong 1 ms, ta **không thể kết luận** ứng dụng xử lý được 1.000 request/s. Một request có thể dùng nhiều phép tính, các tác vụ chạy đồng thời, tranh chấp CPU hoặc chờ I/O; số thread/connection và nhu cầu từ client cũng khác.

Thông lượng thường được ghi là `requests/s`, `jobs/minute`, `messages/s`. Nó cần được đọc **cùng độ trễ, tỷ lệ lỗi và trạng thái tài nguyên**.

Ví dụ minh họa:

| Tải yêu cầu | Throughput xử lý xong | p95 latency | Lỗi | Cách hiểu |
| ---: | ---: | ---: | ---: | --- |
| 50 request/s | 50 request/s | 80 ms | 0% | Dưới tải này hệ thống đáp ứng tốt |
| 200 request/s | 198 request/s | 230 ms | 0,5% | Độ trễ tăng, cần xem phân bố và tài nguyên |
| 400 request/s | 250 request/s | 2.000 ms | 12% | Có dấu hiệu bão hòa; không thể coi 400 là năng lực phục vụ |

**Bảng chỉ minh họa**, không phải benchmark thật. Giá trị lỗi, throughput và p95 còn phụ thuộc thời lượng tải, cách đếm request được gửi/hoàn tất và chính sách timeout. Cần ghi đủ phương pháp để không diễn giải sai.

### 3.3. Tail latency quan trọng với người dùng

**p50** là trung vị; **p95** và **p99** là các phân vị phản ánh phần đuôi của phân bố. Ví dụ, p99 ở 900 ms nói rằng khoảng 99% giá trị đo được **không vượt quá** 900 ms theo quy ước tính phân vị của công cụ; nó **không** bảo đảm tuyệt đối cho mọi request, và phần còn lại có thể chậm hơn nhiều.

Hai bản build có thể có cùng trung bình nhưng phân bố rất khác:

| Bản build (minh họa) | p50 | p95 | p99 | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| A | 70 ms | 190 ms | 420 ms | Đuôi độ trễ ngắn hơn |
| B | 60 ms | 280 ms | 1.500 ms | Trung vị tốt hơn, nhưng nhóm request chậm nhất chịu ảnh hưởng nặng |

Khi so sánh p99, cần đủ mẫu, cùng cửa sổ thời gian và cùng phân nhóm yêu cầu. Không thể lấy **trung bình các p99** của nhiều instance rồi coi đó là p99 toàn hệ thống; muốn tổng hợp đúng cần thông tin phân bố/histogram hoặc dữ liệu đủ chi tiết và phương pháp thích hợp.

**Không cộng p99 của từng dependency để suy ra p99 end-to-end.** Các bước có thể chạy song song, có tương quan và phân vị không có tính cộng như trung bình trong điều kiện đơn giản.

## 4. Vì sao microbenchmark Java dễ cho kết quả gây hiểu nhầm?

JVM không chỉ thực thi từng câu lệnh theo thời gian cố định. Những cơ chế chạy và điều kiện môi trường khiến thời gian của cùng một phương thức thay đổi đáng kể.

### 4.1. JIT và warmup

JVM có thể biên dịch và tối ưu đường mã “nóng” trong quá trình chạy. Lần gọi đầu còn có thể bao gồm tải lớp, khởi tạo, giải mã metadata hoặc hoạt động chưa được tối ưu. Vì thế, đo ngay lần gọi đầu rồi kết luận hiệu năng ổn định thường không đáng tin.

Benchmark cần có **giai đoạn warmup**, đo chính thức, số lượt lặp và lần chạy tách biệt phù hợp. Một vòng warmup cũng không có nghĩa mọi dạng tải sản phẩm đều giống; sự thay đổi phân bố dữ liệu hoặc hot path có thể khiến quyết định JIT khác đi.

### 4.2. Dead-code elimination và constant folding

Nếu kết quả tính toán không được sử dụng, JIT có thể loại bỏ một phần hoặc toàn bộ công việc:

~~~java
// Phản ví dụ: kết quả không được quan sát, không phù hợp để tự đo tốc độ.
for (int i = 0; i < 1_000_000; i++) {
    int ignored = 42 * 42;
}
~~~

Đoạn này không chứng minh một triệu phép nhân có chi phí tương ứng với số vòng. JMH hỗ trợ việc quan sát kết quả benchmark (trả giá trị hoặc dùng `Blackhole`) để tránh một số tối ưu làm phép đo vô nghĩa.

Một giá trị không đổi còn có thể được tính trước. Benchmark với dữ liệu từ một hằng số không giống thực tế nhận dữ liệu từ request, database hoặc mạng.

### 4.3. Phân bổ đối tượng, escape analysis và GC

Một biến thể code trông như tạo nhiều object có thể được JIT tối ưu trong phạm vi nhất định, hoặc ngược lại tạo áp lực cấp phát, tăng tần suất GC. Số allocation và bộ nhớ sống sau GC không phải cùng một đại lượng.

Muốn hiểu ảnh hưởng:

- Theo dõi **allocation rate**, số byte cấp phát theo thao tác khi công cụ hỗ trợ.
- Phân biệt **heap used**, **live set**, **committed heap**, **RSS/process memory** và **off-heap/direct buffer**.
- Kiểm tra thời gian/tần suất **GC pause** và tác động lên tail latency, không chỉ thời gian của hàm nhỏ.
- Xác định liệu tối ưu local có làm tăng bộ nhớ giữ lại hoặc tạo nhiều object tồn tại lâu không.

Một phép đo `ns/op` rất tốt nhưng khiến ứng dụng phải giữ cache vô hạn có thể là lựa chọn tệ về tổng thể.

### 4.4. Cache, branch prediction, contention và môi trường

Kết quả còn phụ thuộc kích thước dữ liệu so với cache CPU, phân bố nhánh, bộ lập lịch hệ điều hành, thay đổi tần số CPU, nhiệt độ máy, số core và các tiến trình khác. Ở ứng dụng nhiều thread còn có lock contention, false sharing và giới hạn thread pool.

Một benchmark một thread trong điều kiện bộ nhớ nóng **không đại diện** cho workload 200 request đồng thời với dữ liệu lớn. Vì vậy phải ghi cấu hình và chọn dữ liệu đại diện cho mục tiêu.

## 5. Dùng JMH để đo cục bộ một cách có chủ đích

**JMH (Java Microbenchmark Harness)** là framework benchmark cho Java/JVM, cung cấp cơ chế warmup, vòng đo, fork, state và xử lý kết quả benchmark. Cần thêm dependency và chạy bằng harness JMH theo thiết lập dự án; khối mã sau **không phải** chương trình Java độc lập chỉ cần `javac` là chạy.

Ví dụ benchmark cộng các khoản tiền biểu diễn bằng `long`; mục đích là đo chi phí vòng lặp trong phạm vi dữ liệu đã chuẩn bị, **không đo checkout API**:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(2)
@Warmup(iterations = 4)
@Measurement(iterations = 6)
public class SumBenchmark {
    @Param({"16", "1024"})
    public int size;

    private long[] amounts;

    @Setup(Level.Trial)
    public void prepare() {
        amounts = new long[size];
        for (int i = 0; i < size; i++) {
            amounts[i] = i + 1L;
        }
    }

    @Benchmark
    public long sumAmounts() {
        long total = 0L;
        for (long amount : amounts) {
            total += amount;
        }
        return total; // Harness quan sát kết quả benchmark.
    }
}
~~~

Ở đây:

- `@Param` buộc đo ít nhất hai kích thước đầu vào, tránh kết luận từ duy nhất một trường hợp.
- `@State(Scope.Thread)` tạo state riêng cho thread benchmark; nó **không** đo tranh chấp giữa các thread.
- `@Setup(Level.Trial)` chuẩn bị mảng ngoài vùng thời gian của thao tác benchmark; nếu ứng dụng thực **phải tự tạo mảng mỗi request**, cần một phép đo khác có tính cả chi phí đó.
- `@Fork(2)` chạy phép đo ở các tiến trình JVM riêng theo cấu hình JMH; giảm ảnh hưởng trạng thái đã tích lũy từ benchmark khác, không làm biến thiên biến mất hoàn toàn.
- `@Warmup` và `@Measurement` tạo các giai đoạn riêng để JVM ổn định và thu số liệu.
- Giá trị trả về giúp ngăn tính toán hoàn toàn không được quan sát; nếu benchmark xử lý output khác, dùng `Blackhole` đúng cách.

**Điều phép đo trả lời:** “Trong môi trường đã định, thao tác cộng trên mảng dài 16 hay 1.024 phần tử có chi phí trung bình trên một lần benchmark là bao nhiêu?”

**Điều nó không trả lời:** “API đặt hàng sẽ nhanh hơn bao nhiêu?”, “có chịu được lưu lượng cao không?”, “tổng bộ nhớ app giảm không?”, hoặc “số tiền thanh toán có còn đúng quy tắc nghiệp vụ không?”.

### Lưu ý về correctness trong ví dụ

Hàm minh họa dùng phép cộng `long` bình thường, nên nếu tổng vượt giới hạn của `long` sẽ tràn. Dữ liệu trong benchmark đã chọn không gây tràn, nhưng mã sản phẩm tính tiền cần **kiểm tra miền giá trị, đơn vị và chính sách số học**. Một phiên bản nhanh hơn nhưng sai với dữ liệu hợp lệ **không phải tối ưu hóa đạt yêu cầu**.

Nếu mục tiêu so sánh hai thuật toán dùng trong sản phẩm, cần đảm bảo **hai phiên bản cho cùng kết quả đúng** trên tập dữ liệu đại diện, đặc biệt ở giá trị biên. Kết quả benchmark chỉ có ý nghĩa khi hai thao tác đang thực hiện công việc tương đương.

### Tránh dùng vòng đo tay làm bằng chứng duy nhất

~~~java
long start = System.nanoTime();
for (int i = 0; i < 100_000; i++) {
    calculate();
}
long elapsed = System.nanoTime() - start;
~~~

Đây không đủ để kết luận tốc độ của `calculate()`: kết quả có thể bị bỏ đi, dữ liệu không đổi, JIT xử lý khác, các vòng lặp ảnh hưởng nhau, GC hoặc hoạt động hệ thống xen vào. `System.nanoTime()` phù hợp để đo **khoảng thời gian trôi qua** trong một tiến trình, nhưng việc tự viết vòng đo không thay cho harness benchmark đáng tin cậy.

## 6. Từ nhanh hơn cục bộ tới nhanh hơn tổng thể: giới hạn Amdahl

Một công thức hữu ích để giữ kỳ vọng thực tế là **định luật Amdahl**, trong mô hình công việc có một phần được tăng tốc còn phần còn lại không đổi:

\[
S_{\text{overall}}=\frac{1}{(1-p)+p/s}
\]

Trong đó:

- `p` là phần thời gian tổng thể do đoạn có thể tối ưu chiếm trước thay đổi;
- `s` là hệ số tăng tốc của đoạn đó;
- `S_overall` là hệ số tăng tốc tối đa theo mô hình giả định.

**Ví dụ minh họa:** nếu hàm tính tổng chỉ chiếm **5%** thời gian trên đường xử lý đang đo, và làm nó chạy **nhanh gấp đôi**, hệ số tổng thể là:

\[
S_{\text{overall}}=\frac{1}{0.95+0.05/2}
                 \approx 1.0256
\]

Tức chỉ nhanh hơn khoảng **2,56%** theo mô hình, trước khi xét thay đổi khác.

Kết quả thực có thể thấp hơn hoặc khác đi do contention, GC, cache, I/O, các đoạn chạy song song và thay đổi workload. **Không được lấy p bằng “5% CPU” nếu đang muốn suy latency end-to-end mà phần lớn thời gian là chờ I/O**; cần xác định cùng một mẫu số/thước đo.

### Cùng một tối ưu có thể cải thiện throughput dù không giảm latency đáng kể

Nếu một thao tác CPU nhỏ được gọi rất nhiều lần trong hệ thống đang **bão hòa CPU**, giảm chi phí CPU trên mỗi request có thể tăng năng lực phục vụ. Khi đó chỉ nhìn latency ở tải thấp có thể chưa thấy lợi ích.

Ngược lại, nếu nút thắt nằm ở connection pool của database, giảm vài microsecond CPU có thể không cải thiện năng lực phục vụ. Đây là lý do cần đo **tốc độ, tài nguyên và mức tải** cùng nhau.

## 7. Hàng đợi và mức đồng thời có thể chi phối toàn ứng dụng

Khi tốc độ yêu cầu đến gần năng lực phục vụ, thời gian chờ tài nguyên có thể tăng nhanh. Một hàm bản thân không chậm vẫn có thể nằm trong request chậm nếu nó phải đợi thread, connection, lock hoặc hàng đợi.

~~~mermaid
flowchart LR
    A["Lưu lượng yêu cầu"] --> Q["Hàng đợi / thread pool"]
    Q --> S["Business logic"]
    S --> DB["Connection pool / database"]
    DB --> EXT["Dịch vụ ngoài"]
    EXT --> R["Phản hồi"]
    Q -. "Đợi tăng khi bão hòa" .-> M["p95 / p99 tăng"]
    DB -. "Giới hạn connection" .-> M
~~~

### Định luật Little và cách diễn giải đúng

Ở hệ thống ổn định trong khoảng đo, **định luật Little** liên hệ số công việc trung bình trong hệ, tốc độ hoàn tất/đến trung bình và thời gian trong hệ trung bình:

\[
L=\lambda W
\]

Ví dụ nếu hệ thống ổn định xử lý **200 request/s**, mỗi request trung bình ở trong ranh giới đo **0,25 s**, thì số request đang có trong phạm vi ấy trung bình là:

\[
L=200\times 0.25=50
\]

Điều này giúp đối chiếu in-flight requests, throughput và thời gian đáp ứng. Tuy nhiên, công thức **không phải phép tính dung lượng tối đa**, không tự cho p99 và cần cùng ranh giới đo, số liệu đủ ổn định; khi lưu lượng tăng liên tục và backlog chưa ổn định, không nên áp dụng máy móc.

### Đừng nhầm concurrency với throughput

Tăng thread từ 20 lên 200 có thể giúp nếu workload đang chờ I/O và dependency còn năng lực. Nhưng cũng có thể làm:

- Tranh chấp lock nhiều hơn;
- DB connection pool cạn;
- CPU tốn thêm context switch;
- Bộ nhớ stack và các object đang sống tăng;
- Queue và timeout lớn hơn;
- Áp lực lên hệ thống bên ngoài vượt giới hạn.

Một cấu hình “nhiều thread hơn” không đồng nghĩa nhanh hơn. Phải quan sát **mức bão hòa tại nút thắt** và giới hạn phụ thuộc.

## 8. Đo toàn ứng dụng cần tải và dữ liệu đại diện

Muốn đánh giá một API phục vụ người dùng, cần mô tả rõ **workload** thay vì chỉ nêu “bắn 10.000 request”.

Một bản mô tả tối thiểu nên có:

| Thành phần thử nghiệm | Điều cần ghi |
| --- | --- |
| **Mục tiêu** | Ví dụ: p95 checkout dưới 300 ms tại 150 request/s với tỷ lệ lỗi dưới 0,5% |
| **Điểm đo** | Phía client, gateway hay server; bao gồm những bước nào? |
| **Phân bố hành động** | Tỷ lệ đọc, ghi, checkout, tra cứu, upload và thao tác quản trị |
| **Dữ liệu** | Số lượng đơn, giỏ hàng nhỏ/lớn, cache nóng/lạnh, tỷ lệ user mới |
| **Lưu lượng** | Mức request/s hoặc mô hình người dùng ảo, ramp-up, burst, steady state |
| **Concurrency** | Số in-flight, thread, connection, tenant và giới hạn phụ thuộc |
| **Môi trường** | Phiên bản JVM, số core, memory limit, DB, mạng, cấu hình pool, GC |
| **Thời lượng** | Giai đoạn warmup, giai đoạn đo ổn định và điều kiện kết thúc |
| **Metrics** | p50/p95/p99, throughput, lỗi, timeout, CPU, heap, GC, queue, DB |
| **Tiêu chí kết luận** | Khi nào gọi là cải thiện, hồi quy hay cần thử lại vì thiếu dữ liệu? |

Các ngưỡng ở bảng là **giả định minh họa**, không phải mục tiêu mặc định cho mọi ứng dụng.

### Open-loop và closed-loop: cẩn thận với cách phát tải

- **Closed-loop:** nhóm client ảo gửi yêu cầu, chờ response rồi mới gửi tiếp. Khi server chậm, **tốc độ gửi cũng giảm**. Điều này có ích cho vài mô hình người dùng, nhưng có thể che khả năng phục vụ dưới tốc độ yêu cầu đến cố định.
- **Open-loop:** lịch gửi cố gắng tuân theo một tốc độ đến đã định, độc lập với thời gian hoàn thành request. Có thể phản ánh tốt hơn một luồng đến bên ngoài được xác định, nhưng load generator phải đủ năng lực duy trì lịch.

Một số công cụ báo latency bị **coordinated omission** nếu chỉ ghi request đã thực sự gửi và bỏ qua khoảng thời gian người dùng/lịch tải lẽ ra vẫn có yêu cầu đến khi server đang chậm. Muốn diễn giải tail latency, phải hiểu cách công cụ lên lịch, ghi nhận yêu cầu chậm, timeout và request không được gửi.

### Cache nóng khác cache lạnh

Benchmark ứng dụng khởi động mới có thể thấy chi phí tải dữ liệu/JIT/cache chưa ổn định. Benchmark chỉ dùng 100 ID lặp lại cũng có thể khiến cache rất hiệu quả, không giống hàng triệu ID ngoài thực tế.

Cần chọn kịch bản dựa trên mục tiêu: **cold start**, hoạt động ổn định, burst sau cache invalidation, hoặc dữ liệu truy vấn chưa từng được cache. Không gộp tất cả vào một con số “trung bình”.

## 9. Kết nối metrics với profiling và tracing

Giả sử dashboard cho thấy p99 API `GET /orders` tăng từ 300 ms lên 1.200 ms trong giờ cao điểm. Ta chưa thể kết luận lỗi nằm ở thuật toán Java hay database.

Một chuỗi điều tra có căn cứ:

1. **Xác minh hiện tượng:** route nào, nhóm request nào, thời gian nào, mức lỗi và throughput ra sao?
2. **Kiểm tra tài nguyên:** CPU saturation, GC, heap, queue depth, thread pool, connection pool, DB latency, network, rate limit.
3. **Dùng tracing để phân đoạn ranh giới:** thời gian ở service, repository, dịch vụ ngoài và các khoảng chờ đo được.
4. **Dùng profiling thích hợp:** CPU profile nếu nghi CPU; allocation profile nếu nghi cấp phát; thread/lock diagnostics nếu nghi tranh chấp.
5. **Tạo giả thuyết có thể bác bỏ:** ví dụ “mỗi request đọc 50 dòng và thực hiện thêm 50 truy vấn DB”.
6. **Thử thay đổi tối thiểu:** batching hoặc query phù hợp trong môi trường có kiểm soát.
7. **Đo lại ở cùng workload:** xem latency, throughput, lỗi, bộ nhớ và hành vi đúng/sai có thay đổi không.

### Chọn tín hiệu đo tương ứng với giả thuyết

| Triệu chứng | Tín hiệu nên kiểm tra | Giả thuyết khả dĩ |
| --- | --- | --- |
| CPU cao và latency tăng | CPU profile, hot methods, saturation | Thuật toán, serialization, vòng lặp hoặc tranh chấp CPU |
| CPU thấp nhưng request chậm | Trace spans, thread state, pool wait | DB/network/lock/queue đang chờ |
| p99 có các đỉnh bất thường | GC pauses, safepoints, dependency outliers, queue | Stop-the-world, spike từ dependency hoặc timeout |
| RSS tăng theo thời gian | Heap retained/live set, native/off-heap, thread count | Cache giữ dữ liệu lâu, native allocation hoặc leak |
| DB connection hết | Pool active/idle/pending, query duration | Query chậm, connection leak hoặc pool quá nhỏ |
| App tăng throughput rồi đột ngột lỗi | Queue, error code, CPU, dependency quota | Bão hòa hoặc giới hạn từ bên ngoài |
| Startup chậm | Class loading, initialization, JIT, cache warmup | Chi phí khởi tạo, dependency health hoặc khởi động đồng thời |

**Quan sát tương quan không tự chứng minh nguyên nhân.** Ví dụ GC tăng và p99 tăng cùng lúc có thể do hai tác động của lượng request lớn, không chắc GC là nguyên nhân duy nhất. Nên kết hợp trace, profile và phép thử thay đổi có kiểm soát.

### Tracing không thay thế metrics toàn hệ thống

Trace theo từng request cho biết hành trình và điểm chờ được instrument; sampling có thể bỏ lỡ các request hiếm. Metrics histogram giúp thấy phân bố trên một tập lớn hơn theo cửa sổ đo; logs giúp điều tra sự kiện cụ thể. Một hệ thống đáng quan sát thường **kết hợp** ba loại tín hiệu theo rủi ro, với chi phí instrumentation được quản lý.

Không ghi ID người dùng, order ID hoặc payload nhạy cảm thành metric label có cardinality rất cao. Điều đó vừa tăng chi phí hệ thống giám sát vừa có thể làm lộ dữ liệu.

## 10. Ví dụ xuyên suốt: phép tính nhanh, nhưng API vẫn chậm

Một service Java hiển thị danh sách 50 đơn hàng. Nó tính tổng tiền từng đơn rất nhanh nhưng API vẫn chậm khi tải cao.

### 10.1. Đo cục bộ

JMH cho thấy thuật toán tính tổng mới có thể nhanh hơn đáng kể với mảng 50 giá trị. Điều đó chỉ là bằng chứng về **vòng lặp tính toán**.

### 10.2. Quan sát toàn ứng dụng

Distributed trace có thể cho thấy dạng thực thi sau (các con số **giả định**, không cộng dồn như phép đo thực tế cho mọi request):

~~~text
GET /orders
  ├─ Xác thực / kiểm tra quyền                 5 ms
  ├─ Query danh sách đơn                      30 ms
  ├─ Với mỗi đơn: query chi tiết từng dòng  ~50 × 8 ms
  ├─ Tính tổng trong Java                     <1 ms
  └─ Serialize và trả kết quả                  3 ms
~~~

Dấu hiệu đáng chú ý là **N+1 queries**: lấy một danh sách rồi truy vấn riêng từng mục. Thay vì chỉ tối ưu vòng lặp nhanh hơn, cần kiểm tra khả năng lấy chi tiết bằng query/batch phù hợp, tránh chuyển lỗi thành truy vấn có khối lượng dữ liệu quá lớn.

Mã mô tả luồng có vấn đề:

~~~java
// Mã giả: interfaces/kiểu được lược bỏ để nhìn rõ số lần gọi I/O.
List<Order> orders = orderRepository.findRecentOrders(50);

for (Order order : orders) {
    List<OrderLine> lines = lineRepository.findByOrderId(order.id());
    long total = totalCalculator.sum(lines);
    // Gắn tổng vào response.
}
~~~

Phương án cần đánh giá:

~~~java
// Mã giả: adapter cần thực thi đúng quy tắc phân quyền và phân trang.
List<Order> orders = orderRepository.findRecentOrders(50);
Map<Long, List<OrderLine>> linesByOrder =
        lineRepository.findByOrderIds(
                orders.stream().map(Order::id).toList());

for (Order order : orders) {
    List<OrderLine> lines =
            linesByOrder.getOrDefault(order.id(), List.of());
    long total = totalCalculator.sum(lines);
    // Gắn tổng vào response.
}
~~~

Đây chỉ là ví dụ về **rủi ro I/O và ranh giới dữ liệu**, không phải code hoàn chỉnh chạy được; các kiểu repository và calculator chưa được khai báo. Một query batch có thể làm tăng lượng dữ liệu trả về, bộ nhớ giữ lại hoặc thay đổi thứ tự/phân trang nếu thiết kế không đúng. Khi áp dụng thực tế cần kiểm tra:

- Query có giữ **đúng tenant và quyền đọc** không?
- Đơn và dòng hàng có bị lặp do join hoặc fetch strategy không?
- Kết quả cho đơn rỗng và đơn nhiều dòng có đúng không?
- Có gây tăng heap khi trả quá nhiều dòng không?
- Chỉ số `queries/request`, DB time, p95/p99 và tải database thay đổi ra sao?

### 10.3. Lập phép đo để xác nhận giả thuyết

| Thước đo | Trước thay đổi (minh họa) | Sau thay đổi (minh họa) | Ý nghĩa cần xem |
| --- | --- | --- | --- |
| Query DB trên một request | 51 | 2 | Có loại bỏ N+1 theo các kịch bản được đo không? |
| CPU tính tổng | 1,0 ms | 0,5 ms | Chỉ là phần nhỏ của request |
| p95 API ở cùng mức tải | 600 ms | 190 ms | Có cải thiện với tải và dữ liệu tương đương không? |
| p99 API ở cùng mức tải | 1.400 ms | 390 ms | Đuôi giảm, cần kiểm tra số mẫu/độ ổn định |
| Peak heap/RSS | Mốc ban đầu | Cần đo | Batch có làm giữ dữ liệu quá nhiều không? |
| Tỷ lệ lỗi và kết quả nghiệp vụ | Mốc ban đầu | Phải không hồi quy | Không đánh đổi tốc độ lấy dữ liệu sai |

**Không được trình bày các con số trong bảng như kết quả thực đo**: chúng chỉ minh họa loại bằng chứng cần thu thập. Trong một dự án thật, cần ghi số liệu từ cùng một workload, điều kiện vận hành, phiên bản và công cụ.

Bài học: một tối ưu local có thể có ích, nhưng nếu chi phí I/O chi phối, tối ưu ranh giới dữ liệu mới là thay đổi tác động lớn tới người dùng.

## 11. Đo thời gian trong ứng dụng Java: đúng điểm và đúng ngữ nghĩa

Khi instrument một thao tác đồng bộ, `System.nanoTime()` thích hợp để đo **khoảng thời gian trong một tiến trình**; không dùng giá trị tuyệt đối của nó như timestamp UTC.

Ví dụ Java 17 bao quanh một thao tác checkout **đồng bộ**:

~~~java
record CheckoutCommand(String customerId) {}
record Receipt(String orderId) {}

interface CheckoutOperation {
    Receipt execute(CheckoutCommand command);
}

interface DurationRecorder {
    void recordNanos(String operation, long elapsedNanos);
}

final class TimedCheckout {
    private final CheckoutOperation delegate;
    private final DurationRecorder recorder;

    TimedCheckout(CheckoutOperation delegate, DurationRecorder recorder) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
        this.recorder = java.util.Objects.requireNonNull(recorder);
    }

    Receipt execute(CheckoutCommand command) {
        long startedAt = System.nanoTime();
        try {
            return delegate.execute(command);
        } finally {
            long elapsed = System.nanoTime() - startedAt;
            recorder.recordNanos("checkout", elapsed);
        }
    }
}
~~~

Khối này minh họa **vị trí đo bao gồm cả đường thành công lẫn ngoại lệ**. Một `DurationRecorder` thực tế nên không chặn và không làm thất bại luồng nghiệp vụ nếu hệ thống metrics gặp vấn đề; cần bảo đảm hoặc xử lý lỗi ghi metric phù hợp. Ví dụ không tự thực hiện yêu cầu đó.

**Giới hạn quan trọng:**

- Nếu `delegate.execute` trả về `CompletableFuture`, việc đo tới lúc phương thức **trả future** sẽ không đo thời gian hoàn thành tác vụ bất đồng bộ. Phải kết thúc phép đo khi tương lai hoàn tất theo hợp đồng.
- Nếu mã chạy ở API server, số đo **không bao gồm** toàn bộ network latency phía client.
- Nếu ghi metric tăng chi phí lớn, chính hoạt động đo có thể ảnh hưởng hệ thống. Nên đánh giá overhead instrumentation.
- Đừng dùng wall-clock `Instant.now()` để tự đo micro-duration; nó có mục đích biểu diễn thời điểm và có thể chịu điều chỉnh đồng hồ hệ thống.

Để quan sát hệ thống, nên dùng **metric histogram** với đơn vị và bucket phù hợp thay vì chỉ lưu tổng và trung bình. Nếu bộ đo cung cấp tracing, hãy giữ mối liên hệ giữa span và metric mà không đưa thông tin nhạy cảm vào label.

## 12. Khác biệt giữa phép đo cục bộ của bộ nhớ và bộ nhớ ứng dụng

Giả sử một hàm được sửa để giảm cấp phát từ 200 byte/op xuống 80 byte/op theo một profiler hoặc benchmark thích hợp. Điều này có thể giảm áp lực GC; nhưng không tự bảo đảm RSS của ứng dụng sẽ giảm tương ứng.

Một số mức bộ nhớ cần phân biệt:

| Mức đo | Phản ánh điều gì? | Không nên suy ra |
| --- | --- | --- |
| **Allocated bytes/op** | Byte object được cấp phát cho một thao tác theo công cụ đo | Bộ nhớ thực còn được giữ sau khi thao tác xong |
| **Allocation rate** | Lượng cấp phát mỗi giây dưới một workload | Heap sẽ tăng mãi |
| **Live/retained heap** | Dữ liệu còn được tham chiếu ở thời điểm/phương pháp đo | Toàn bộ RAM của process |
| **Committed heap** | Dung lượng heap JVM đã cam kết với hệ điều hành | Mọi byte đều đang giữ object sống |
| **RSS/process memory** | Bộ nhớ vật lý gắn với process theo OS/container | Chỉ là heap Java; còn native, stack, code cache... |
| **GC pause/overhead** | Chi phí thu gom rác theo bộ thu gom/cấu hình | Mọi nguyên nhân gây p99 cao đều là GC |

Một cache lưu vĩnh viễn dữ liệu đã tính sẵn có thể giúp phép đo xử lý một lần nhanh hơn, nhưng lại làm tăng live set, chi phí khởi động, invalidation và nguy cơ dữ liệu cũ. Cần đo **hit rate, kích thước, thời gian sống, sự thay đổi dữ liệu và chi phí khi miss**.

**Tài nguyên không chỉ là RAM:** thread, file descriptor, socket, DB connection, disk bandwidth, network và quota dịch vụ ngoài đều có thể là nút thắt hoặc nguồn rò rỉ.

## 13. Thiết kế thí nghiệm so sánh trước/sau một thay đổi

Một báo cáo tốt phải cho phép người khác hiểu **đã đo điều gì, đo bằng cách nào và có thể kết luận đến đâu**.

### Quy trình thực tế

1. **Nêu câu hỏi và giả thuyết:** “Thao tác N+1 khiến p95 của GET /orders cao khi mỗi trang có 50 đơn”.
2. **Xác định chỉ số quyết định:** p95/p99 ở cùng request rate, số query/request, DB duration, error rate; thêm CPU và memory để bắt hồi quy phụ.
3. **Lập baseline:** ghi commit, cấu hình JVM/DB, dataset, vùng chạy, warmup, tải, thời gian đo và công cụ.
4. **Thay đổi nhỏ có mục tiêu:** tránh đồng thời thay cả thuật toán, pool, cache và schema nếu muốn tìm nguyên nhân.
5. **Chạy lặp có kiểm soát:** đo nhiều lượt khi phù hợp, tránh so một run lúc server rảnh với một run lúc có tác vụ nền.
6. **So sánh phân bố và chi phí:** không chỉ so trung bình; kiểm tra p95/p99, throughput, lỗi, CPU, GC, peak memory và giới hạn phụ thuộc.
7. **Kiểm tra correctness:** dữ liệu trả về, quyền truy cập, xử lý null/empty và các trường hợp biên không thay đổi ngoài đặc tả.
8. **Đánh giá môi trường thật:** load test kiểm soát không thay thế quan sát sau rollout; có thể dùng canary và rollback có tiêu chí rõ.
9. **Ghi kết luận có giới hạn:** “Trong cấu hình/tải X, số query/request giảm từ A xuống B và p95 cải thiện; chưa đánh giá cold start hoặc dataset gấp 100 lần”.

### Tránh các phép so sánh thiếu căn cứ

- Không so laptop A với container B rồi quy mọi khác biệt cho code.
- Không dùng cache lạnh cho baseline nhưng cache nóng cho candidate mà không ghi rõ.
- Không chỉ chọn lượt chạy đẹp nhất rồi bỏ các lượt có lỗi.
- Không kết luận từ một khoảng đo quá ngắn khi phân vị đuôi rất ít mẫu.
- Không thay đổi dữ liệu test giữa hai bản mà không xét sự khác biệt.
- Không tối ưu thông lượng bằng cách âm thầm trả lỗi nhanh hơn; **error rate là một phần kết quả**.
- Không bỏ qua chi phí tài nguyên hoặc tính đúng đắn chỉ vì thời gian request giảm.

### Bản ghi thí nghiệm tối thiểu

~~~text
Mục tiêu:
  Giảm p95 GET /orders ở mức 150 requests/s, không tăng lỗi.

Ranh giới đo:
  Phía client thử nghiệm, thời điểm gửi -> nhận response.

Môi trường:
  JVM/DB/container và cấu hình cố định theo bản ghi thí nghiệm.

Workload:
  Trang 50 đơn, phân bố tenant và dữ liệu như mô tả, tải 10 phút
  sau warmup; dùng cùng dữ liệu hoặc điều kiện tương đương.

Chỉ số:
  p50/p95/p99, throughput hoàn tất, error rate, queries/request,
  CPU, DB pool wait, GC, RSS.

Kết luận:
  Chỉ chấp nhận khi đáp ứng mục tiêu và không có hồi quy về dữ liệu,
  bảo mật, tỷ lệ lỗi hoặc chi phí tài nguyên đã xác định.
~~~

Đây là **mẫu tài liệu đo**, không phải báo cáo đã chạy.

## 14. Tối ưu cục bộ có thể làm toàn hệ thống tệ hơn

Một thay đổi vi mô còn có thể gây hậu quả ngược khi được nhân lên bởi nhiều request.

### 14.1. Tối ưu bằng cache không giới hạn

Hàm tra cứu nhanh hơn ở lần thứ hai, nhưng cache giữ rất nhiều kết quả → heap lớn, GC lâu hơn, RAM tăng, dữ liệu có thể lỗi thời. Đánh giá cần xét latency **khi hit và miss**, TTL, giới hạn kích thước và invalidation.

### 14.2. Giảm khóa bằng cách tạo thêm thread

Thao tác local tránh chờ lock nhưng tổng số thread tăng → CPU context switching, memory stack, DB pool contention. p99 toàn hệ thống có thể xấu hơn dù một đoạn đo riêng nhanh hơn.

### 14.3. Batch quá lớn

Giảm số round-trip I/O nhưng mỗi batch giữ nhiều object, tăng thời gian giữ connection và làm chậm các request nhỏ. Cần đo **độ lớn batch thích hợp** theo workload, không đặt mức tối đa chỉ từ benchmark một lời gọi.

### 14.4. Bỏ validation để giảm thời gian CPU

Bỏ kiểm tra đầu vào có thể làm hàm chạy nhanh hơn vài nanosecond nhưng cho phép dữ liệu sai hoặc hành động không được phép. **Tính đúng đắn và bảo mật là ràng buộc**, không phải chi phí được phép tự loại bỏ nếu mục tiêu hiệu năng chưa quy định.

### 14.5. Đổi cấu trúc dữ liệu làm tăng chi phí vận hành

Dùng cấu trúc chuyên biệt có thể giảm thời gian truy cập nhưng tăng bộ nhớ, khiến dữ liệu khó serialize hoặc làm code khó bảo trì. Cần xác định lợi ích đo được có xứng với độ phức tạp mới.

**Nguyên tắc review:** mỗi tối ưu nên kèm câu trả lời “nút thắt ở đâu, bằng chứng nào xác nhận, giới hạn của phép đo là gì, và có hồi quy gì về đúng đắn/tài nguyên/bảo trì hay không?”.

## 15. Checklist review và chẩn đoán hiệu năng

Trước khi kết luận “đoạn mã này nhanh/chậm”, hãy kiểm tra:

- [ ] Tôi biết **phạm vi đo**: hàm, component, API server, client hay toàn hành trình.
- [ ] Tôi biết đơn vị metric và ranh giới bắt đầu/kết thúc.
- [ ] Tôi phân biệt elapsed time, CPU time, queue wait, throughput và latency.
- [ ] Tôi ghi rõ input, kích thước dữ liệu, trạng thái cache, mức đồng thời và tỷ lệ lỗi.
- [ ] Với microbenchmark Java, tôi đã xét JIT/warmup, fork, dữ liệu, dead-code elimination và JMH.
- [ ] Tôi không suy trực tiếp `ns/op` thành requests/s hoặc p99 của hệ thống.
- [ ] Tôi xem p50/p95/p99 cùng throughput, lỗi và mức bão hòa.
- [ ] Tôi hiểu cách công cụ tạo tải, có nguy cơ coordinated omission hoặc load generator quá tải không.
- [ ] Tôi kiểm tra CPU, heap, GC, connection pool, thread, I/O hoặc tài nguyên phù hợp với giả thuyết.
- [ ] Tôi có trace/profile/metric để định vị nút thắt thay vì chỉ đoán từ tên phương thức.
- [ ] Tôi so baseline và candidate ở điều kiện có thể so sánh, nhiều lượt nếu cần.
- [ ] Tôi kiểm tra thay đổi không làm sai dữ liệu, quyền truy cập, xử lý lỗi hay tài nguyên.
- [ ] Tôi có tiêu chí đo lại sau rollout và đường quay lại nếu có hồi quy.

Một phép đo thiếu ranh giới hoặc điều kiện tải **không thể được dùng làm lời hứa hiệu năng**. Ghi rõ thiếu sót giúp nhóm ra quyết định chính xác hơn.

## 16. Những ngộ nhận phổ biến

**“Hàm nhanh gấp đôi thì API nhanh gấp đôi.”** Chỉ đúng trong các giả định rất đặc biệt; xem tỷ trọng đường xử lý và nút thắt thực.

**“JMH cho kết quả tốt là production sẽ tốt.”** JMH đo một thao tác theo điều kiện benchmark; production còn queue, IO, concurrency, dữ liệu và GC.

**“Cứ dùng `System.nanoTime()` trong vòng lặp là benchmark đáng tin.”** JIT có thể tối ưu bỏ công việc; warmup, dữ liệu và nhiễu môi trường phải được kiểm soát.

**“Thời gian CPU thấp nghĩa là hệ thống nhanh.”** Request có thể chờ DB, mạng, lock hoặc connection pool rất lâu dù CPU không bận.

**“Latency trung bình đủ mô tả trải nghiệm.”** p95/p99 và số lượng request lỗi/chờ lâu có thể quan trọng hơn giá trị trung bình.

**“Tăng concurrency luôn tăng throughput.”** Khi nút thắt đã bão hòa, thêm request đang chờ có thể tăng tail latency và timeout.

**“Giảm số object được tạo chắc chắn giảm RAM của process.”** Cấp phát, live heap, committed heap và RSS là các chỉ số khác nhau.

**“Một lần chạy benchmark nhanh nhất phản ánh hiệu năng thật.”** Phải xét biến thiên, môi trường và phương pháp thống kê/phân vị phù hợp.

**“E2E chậm chứng minh lỗi của hàm vừa sửa.”** Chậm toàn ứng dụng là hiện tượng; cần trace/profiling và thử nghiệm để tìm nguyên nhân.

**“Tối ưu luôn là thay thuật toán Java.”** Nút thắt có thể là query, cache miss, network, DB pool, lock hoặc cấu hình triển khai.

**“Chỉ cần latency giảm, tỷ lệ lỗi không quan trọng.”** Một hệ thống trả lỗi nhanh hơn có thể trông nhanh hơn nhưng không phục vụ tốt hơn.

## 17. Bài tập thực hành

### Bài tập A — diễn giải một benchmark

Một JMH benchmark cho thấy:

~~~text
Phiên bản A: 300 ns/op
Phiên bản B: 120 ns/op
Đầu vào: mảng 32 số long
Benchmark: 1 thread, dữ liệu chuẩn bị ngoài phép đo
~~~

Hãy trả lời:

1. Có thể kết luận gì về **thao tác benchmark**?
2. Những thông tin nào còn thiếu để đánh giá độ tin cậy thống kê của kết quả?
3. Vì sao chưa thể kết luận p95 của endpoint sẽ giảm tương ứng?
4. Nếu số liệu cho thấy hàm này chiếm khoảng 2% thời gian xử lý đang xem xét, Amdahl gợi ý giới hạn cải thiện nào?
5. Test tính đúng đắn nào cần có trước khi thay phiên bản A bằng B trong mã sản phẩm?

### Bài tập B — định vị nút thắt

API trả trang 100 đơn mất 900 ms. CPU ứng dụng thấp, DB pool gần cạn, trace cho thấy 101 truy vấn trên một request. Bạn sẽ:

1. Đưa ra **giả thuyết có thể kiểm tra** nào?
2. Đo thêm những gì để phân biệt N+1, query chậm và pool contention?
3. Thử cách thay đổi nhỏ nào trước?
4. Theo dõi **rủi ro phụ** nào khi chuyển sang batch/fetch?
5. Viết tiêu chí chấp nhận kết quả theo p95/p99, throughput, lỗi và dữ liệu đúng thế nào?

### Bài tập C — đọc một kết quả tải

Một nhóm báo cáo: “Hệ thống chịu 500 request/s vì công cụ được cấu hình gửi 500 request/s.” Trong kết quả lại có 320 request/s hoàn tất, 15% timeout và p99 rất cao.

Hãy phân biệt **tốc độ gửi**, **thông lượng hoàn tất**, **latency** và **tỷ lệ lỗi**, sau đó giải thích vì sao con số 500 chưa chứng minh năng lực của hệ thống.

### Bài tập D — tối ưu bộ nhớ

Một cache làm hàm lookup nhanh hơn 80%, nhưng RSS của container tăng dần đến giới hạn rồi bị khởi động lại. Hãy đề xuất những chỉ số bộ nhớ/cache cần đo, chính sách giới hạn và cách test hồi quy để cân bằng tốc độ với độ tin cậy.

## 18. Câu hỏi tự kiểm tra

1. Microbenchmark và system/load test trả lời hai câu hỏi khác nhau như thế nào?
2. Vì sao `ns/op` không thể tự biến thành p95 latency hay số request/s của API?
3. JIT, constant folding và dead-code elimination ảnh hưởng phép đo Java ra sao?
4. Vì sao phải mô tả dữ liệu đầu vào và cache state khi so hai thuật toán?
5. Phân biệt wall-clock time, CPU time và queueing time bằng một request đang chờ database.
6. Tại sao giảm p50 có thể đi kèm p99 tăng? Điều này ảnh hưởng quyết định tối ưu thế nào?
7. Nếu một đoạn chiếm 5% thời gian, nhanh gấp đôi thì theo Amdahl tổng thể có thể cải thiện bao nhiêu trong mô hình đơn giản?
8. Khi thông lượng không tăng nữa nhưng queue và p99 tăng mạnh, bạn sẽ kiểm tra tài nguyên nào?
9. Định luật Little giúp liên hệ ba đại lượng nào và vì sao không dùng nó để tự suy ra capacity?
10. Load generator closed-loop có thể che một dạng vấn đề latency như thế nào?
11. Trong ví dụ N+1, vì sao tối ưu query có thể quan trọng hơn tăng tốc hàm cộng giá?
12. Allocation rate giảm có nhất thiết làm RSS giảm không? Hãy nêu hai nguyên nhân làm câu trả lời là “không”.
13. Một kết quả benchmark có p99 thấp nhưng tỷ lệ lỗi cao có được coi là cải thiện không? Vì sao?
14. Khi tracing cho thấy DB span dài, cần thêm bằng chứng gì trước khi khẳng định database là nguyên nhân gốc?
15. Hãy viết mẫu ghi chú thí nghiệm gồm mục tiêu, môi trường, workload, metrics, baseline, candidate, giới hạn và cách kiểm chứng đúng đắn.

## Ghi nhớ

**Phép đo cục bộ và hành vi toàn ứng dụng thuộc hai cấp bằng chứng khác nhau.** Microbenchmark giúp hiểu chi phí một thao tác trong điều kiện kiểm soát; đo toàn hệ thống cho biết tác động của I/O, hàng đợi, đồng thời, GC, tài nguyên và trải nghiệm người dùng. Hãy bắt đầu từ rủi ro hoặc triệu chứng thực, đo đúng ranh giới, tìm nút thắt có chứng cứ, thay đổi có kiểm soát và đo lại cả latency, throughput, lỗi, tài nguyên lẫn tính đúng đắn. Hiệu năng chỉ là cải thiện chất lượng khi **lợi ích quan sát được xứng với chi phí và không phá vỡ những thuộc tính đáng tin cậy khác**.
