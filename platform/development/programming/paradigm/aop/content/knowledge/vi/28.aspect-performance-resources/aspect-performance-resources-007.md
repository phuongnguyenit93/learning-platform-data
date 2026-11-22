# Thiết kế đo đạc AOP có đường cơ sở và điều kiện tải đại diện

Một aspect có thể làm mã nghiệp vụ gọn hơn nhưng vẫn tiêu thụ CPU, bộ nhớ, thời gian và tài nguyên dùng chung. Chi phí đó phụ thuộc vào cách áp dụng aspect (dệt mã khi biên dịch, khi nạp lớp, hoặc chặn lời gọi qua proxy), loại advice, tần suất join point và tải thực tế. Bởi vậy, kết luận “AOP nhanh/chậm” chỉ có ý nghĩa khi **so sánh các cấu hình tương đương dưới cùng điều kiện tải, có đường cơ sở (baseline) và cách đo lặp lại được**.

Bài này tập trung vào phương pháp đo hiệu năng và tài nguyên của **Aspect-Oriented Programming (AOP) nói chung**: thiết kế thí nghiệm, xây dựng baseline, tái hiện tải và đọc kết quả. Ví dụ Java chỉ minh họa một cơ chế chặn lời gọi; kết quả của nó không đại diện cho mọi công nghệ dệt aspect.

## 1. Xác định chính xác chi phí cần đo

Trong AOP, *join point* là điểm thực thi có thể được mở rộng; *pointcut* chọn các điểm phù hợp; *advice* thực thi logic bổ sung ở trước, sau hoặc bao quanh join point; *weaving* đưa hành vi aspect vào chương trình. Một lời gọi có advice có thể phát sinh nhiều lớp chi phí:

1. **Khởi tạo hoặc dệt mã:** thời gian build, nạp lớp, khởi động, tăng số lớp/bytecode hoặc bộ nhớ metadata. Đây có thể là chi phí một lần, khác với chi phí mỗi lời gọi.
2. **Định tuyến/khớp pointcut:** kiểm tra điều kiện, dispatch, proxy, truy cập reflection hoặc ngăn tối ưu hóa inlining, tùy cơ chế áp dụng.
3. **Bản thân advice:** đo đồng hồ, ghi log, kiểm tra điều kiện, thu thập metric, tạo span, sao chép tham số, bắt và phát lại ngoại lệ.
4. **Hệ quả hệ thống:** cấp phát đối tượng, áp lực GC, tranh chấp khóa/counter, I/O của logger/exporter, queue đầy, áp lực CPU và độ trễ đuôi.

Phải xác định đơn vị đo: **chi phí mỗi join point**, **độ trễ toàn yêu cầu**, **thông lượng hệ thống**, hay **tài nguyên trên mỗi công việc**. Các đơn vị này trả lời những câu hỏi khác nhau. Advice chạy rất nhanh ở một join point vẫn có thể đắt nếu một yêu cầu đi qua hàng trăm join point; ngược lại, overhead mỗi lời gọi có thể nhỏ so với thao tác I/O kéo dài hàng chục mili giây.

Đặt câu hỏi thí nghiệm có thể bác bỏ, ví dụ:

> “Với hỗn hợp tải dự kiến ở 1.000 yêu cầu/giây, bật advice ghi nhận thời gian làm p95 tăng tối đa 5%, throughput đạt không thấp hơn 97% baseline và không đẩy CPU vượt ngưỡng vận hành.”

Các ngưỡng trên chỉ là **ví dụ về tiêu chí chấp nhận**. Giá trị dùng thật phải đến từ SLO và ngân sách tài nguyên của hệ thống.

## 2. Xây dựng baseline và các biến thể có thể so sánh

Để tách nguyên nhân, tối thiểu nên có các biến thể sau:

| Ký hiệu | Cấu hình | Câu hỏi giải đáp |
| --- | --- | --- |
| B0 | Logic nghiệp vụ chạy không qua cơ chế chặn/dệt aspect cần đánh giá | Đường cơ sở của công việc |
| B1 | Cùng cơ chế chặn/dệt và cùng tập join point, advice rỗng hoặc gần như rỗng | Phần chi phí do cơ chế AOP/dispatch |
| B2 | Cơ chế như B1, bật đúng advice dự kiến (ví dụ timer/counter) nhưng không thêm các tác vụ ngoài phạm vi | Chi phí tăng thêm từ advice |
| B3 | Cấu hình vận hành thật: nhiều aspect, sampling, xuất telemetry, cấu hình exporter/queue thực tế | Ảnh hưởng tổng hợp ở mức hệ thống |

B0 → B1 giúp ước lượng chi phí cấu trúc của đường gọi; B1 → B2 giúp nhận diện chi phí logic advice; B2 → B3 giúp thấy chi phí tích hợp, tương tác giữa nhiều advice và đầu ra dữ liệu. Các chênh lệch **không nhất thiết cộng tuyến tính** vì JIT, GC, tranh chấp và hàng đợi có thể thay đổi theo cấu hình.

**Giữ tính tương đương ngữ nghĩa:** mỗi biến thể phải trả về cùng kết quả, lan truyền cùng ngoại lệ và thực hiện cùng công việc nghiệp vụ. Nếu advice có tác dụng nghiệp vụ bắt buộc (ủy quyền, giao dịch, kiểm tra dữ liệu), không được tắt nó trong môi trường vận hành để gọi đó là kết quả tương đương. Hãy dựng một workload thí nghiệm an toàn và chỉ cô lập phần cần nghiên cứu. Nếu đổi cách dệt từ compile-time sang proxy runtime, ghi đó là **một biến thí nghiệm khác**, không trộn vào so sánh “bật/tắt advice”.

**Kiểm soát phạm vi pointcut:** ghi lại join point nào thực sự bị áp dụng, số lần advice chạy và thứ tự aspect. Pointcut rộng hơn dự kiến hoặc advice gọi vào chính hạ tầng đo có thể gây lặp, double-count hoặc làm số liệu lệch. Baseline phải giữ nguyên mã nghiệp vụ, tham số, dữ liệu, tối ưu build, cấu hình JVM và tài nguyên máy.

## 3. Thiết kế tải đại diện trước khi đo

“Tải đại diện” gồm **loại công việc, phân phối tần suất, kích thước dữ liệu, nhịp đến và mức đồng thời**, không đơn thuần là chọn một con số requests/second.

- **Phân phối đường chạy:** đo tỷ lệ yêu cầu ngắn/dài, thành công/lỗi, hit/miss cache, đường đi có ít/nhiều join point. Ví dụ tải tham chiếu có 60% truy vấn nhẹ, 30% xử lý trung bình, 10% xử lý nặng thì cả B0–B3 phải nhận đúng hỗn hợp này.
- **Kích thước và dữ liệu:** dùng phân phối đầu vào thực tế (không chỉ một input cố định). Trộn payload nhỏ/lớn, số phần tử, dữ liệu có/không có cache và cả ngoại lệ nếu chúng xuất hiện ngoài đời.
- **Nhịp đến:** tải đều, tăng dần, burst và thời gian yên lặng sau burst có thể tạo kết quả khác nhau. Nếu lưu lượng thực được quyết định bởi nguồn bên ngoài, ưu tiên mô hình *open-loop* với tốc độ đến định trước; hệ thống phát tải kiểu *closed-loop* có thể tự giảm số yêu cầu phát ra khi phản hồi chậm và che giấu nghẽn.
- **Mức đồng thời:** đo ở tải thấp, tải thường ngày, gần ngưỡng công suất và quá ngưỡng ngắn hạn. Khi CPU hoặc queue đã bão hòa, một ít overhead có thể kéo p99 tăng mạnh.
- **Đặc trưng advice:** số join point mỗi request, tỷ lệ sampling, độ dài thông điệp log, số thuộc tính/span, cardinality của nhãn metric, batch size và tốc độ xuất telemetry.
- **Môi trường:** CPU quota, RAM, phiên bản JDK, GC, JVM flags, số worker/thread, bộ nhớ heap, cấu hình mạng/disk và đặc điểm máy phát tải phải ổn định, có ghi nhận.

Một ma trận thử nghiệm khả thi:

| Kịch bản | Mức tải gợi ý | Điều cần quan sát |
| --- | --- | --- |
| S1 — nhàn rỗi/cold start | Khởi động mới rồi phát ít yêu cầu | Thời gian nạp/dệt lớp, startup, class metadata; tách khỏi số đo steady-state |
| S2 — vận hành bình thường | Tải đều ở lưu lượng mục tiêu; đúng hỗn hợp request | Độ trễ p50/p95/p99, throughput, CPU, GC, allocations |
| S3 — cao điểm | Lưu lượng cao hơn mức thường ngày, có burst | Queue, timeout, lỗi, tranh chấp, độ trễ đuôi và điểm bão hòa |
| S4 — duy trì | Tải ổn định lâu hơn, đủ quan sát chu kỳ GC/exporter | Tăng heap, backlog, rò rỉ tài nguyên, chi phí định kỳ |

Đây là **cấu trúc thí nghiệm**, không phải bốn con số tải dùng cho mọi ứng dụng. Nên chạy mỗi kịch bản cho B0, B1, B2 và B3. Nếu dữ liệu thực tế chưa có, ghi rõ giả định và thử nhiều hỗn hợp tải để biết kết luận nhạy với giả định nào.

## 4. Chọn chỉ số và điểm đặt phép đo

**Đo bên ngoài hệ thống được kiểm tra** để thu nhận chi phí end-to-end, bao gồm dispatch, advice, ghi metric, thread scheduling và queue. Dùng đồng hồ đơn điệu của bộ phát tải hoặc công cụ benchmark đáng tin, kết hợp số liệu trong tiến trình để giải thích nguyên nhân. Không chỉ lấy thời gian mà chính advice tự ghi nhận, vì phép đo nội bộ có thể bỏ sót phần trước/sau timer và chính thao tác xuất dữ liệu đo.

| Lớp quan sát | Chỉ số | Cách dùng |
| --- | --- | --- |
| Chất lượng dịch vụ | throughput hoàn thành, offered rate, tỉ lệ lỗi/timeout, p50/p95/p99 latency | Đối chiếu tác động người dùng; xem cả lỗi và yêu cầu bị bỏ |
| CPU và JVM | CPU process/host, CPU time, GC count/pause, heap used, allocation rate/bytes per operation | Giải thích overhead xử lý và cấp phát |
| Đồng thời | thread hoạt động, lock contention, queue depth, wait time | Xác định tắc nghẽn khi advice dùng tài nguyên chung |
| AOP | số lần advice/join point, tỷ lệ lời gọi có advice, số span/log/metric tạo và được xuất | Kiểm tra cùng phạm vi instrumentation và số lần phát sinh |
| Vòng đời | startup time, load/weave time, footprint sau khởi động | Tách chi phí một lần khỏi steady-state |

Với các yêu cầu đủ điều kiện đo, lưu histogram/phân phối và kích thước mẫu; **không dùng một trung bình đơn lẻ** để kết luận về tail latency. p95 của B2 trừ p95 của B0 là độ dịch của hai phân vị, **không phải thời gian overhead p95 chính xác của cùng một yêu cầu**. Muốn đo overhead ở cấp join point, cần thí nghiệm vi mô được cô lập hoặc dữ liệu so cặp phù hợp; còn ở cấp hệ thống, chênh lệch phân vị vẫn hữu ích cho SLO.

Chuẩn hóa đơn vị khi báo cáo: milliseconds/request, completed requests/second, CPU-seconds per 1.000 requests, bytes allocated/operation. Với phép đo dương và baseline khác 0, tỷ lệ thay đổi một chỉ số có thể tính:

```text
Thay đổi tương đối (%) = 100 × (giá trị biến thể − giá trị baseline) / giá trị baseline
```

Với latency, CPU, allocations: tăng thường là bất lợi. Với throughput đạt được ở tải cạnh tranh tương đương: giảm thường là bất lợi. Luôn báo cả **giá trị tuyệt đối, tỷ lệ thay đổi và độ biến thiên**; con số phần trăm lớn của một phép gọi cực ngắn đôi khi có tác động tổng rất nhỏ.

## 5. Quy trình thí nghiệm để giảm sai lệch

1. **Đóng băng cấu hình:** cùng commit mã, bộ dữ liệu, số join point, JDK, GC, giới hạn tài nguyên, cấu hình máy, mạng và trình phát tải. Ghi rõ phương thức weaving, danh sách aspect và thứ tự advice.
2. **Chứng minh đúng chức năng:** kiểm tra kết quả, ngoại lệ, side effect và số lần advice bằng test độc lập. Các biến thể B0–B3 phải xử lý cùng một yêu cầu.
3. **Hiệu chuẩn máy phát tải:** bảo đảm máy phát tải và bộ thu telemetry không trở thành nút thắt. Ghi cả offered rate và completed rate; xác định timeout hoặc dropped requests.
4. **Warm-up:** cho JIT, class loading, pool, cache và kết nối đạt trạng thái tương đối ổn định; đo startup/cold riêng. Không gộp warm-up vào latency steady-state.
5. **Chạy theo cặp, lặp lại:** dùng nhiều lượt độc lập ở từng mức tải; luân phiên hoặc xáo trộn thứ tự B0/B1/B2/B3 để tránh thiên lệch theo thời gian và nhiệt độ máy. Có khoảng ổn định giữa lượt; lưu raw data, không chỉ ảnh chụp dashboard.
6. **Theo dõi nhiễu:** CPU throttling, GC bất thường, việc nền, thay đổi cache, network, clock và load của máy khác. Nếu môi trường mất ổn định, ghi sự cố và chạy lại có lý do.
7. **Phân tích biến thiên:** so trung vị giữa các lượt, khoảng biến thiên hoặc khoảng tin cậy; đối chiếu cả đồ thị latency/throughput theo thời gian và độ bão hòa. Không kết luận từ một lần chạy đẹp nhất.
8. **Kiểm chứng ở nhiều thang đo:** benchmark vi mô giúp chỉ ra chi phí dispatch/advice; load test giúp đánh giá ảnh hưởng tổng hợp. Hai loại phép đo bổ trợ, không thể thay thế nhau.

Đối với Java, nên dùng công cụ benchmark vi mô chuyên dụng như **JMH** khi cần đo ở mức nanosecond/microsecond và tránh nhiều bẫy JIT, dead-code elimination, constant folding. Một vòng lặp tự đo bằng System.nanoTime không đủ để chứng minh overhead vi mô. Load test end-to-end cần môi trường và công cụ phát tải riêng, đồng thời kiểm soát thời gian chờ và cách phát sinh yêu cầu.

## 6. Ví dụ Java 17: dựng B0/B1/B2 và kiểm tra cùng kết quả

Ví dụ sau minh họa ba đường gọi tương ứng: trực tiếp, proxy với advice rỗng, và proxy với advice ghi tổng thời gian. JDK dynamic proxy là **một kỹ thuật hiện thực hành vi giao cắt**, không bao quát mọi loại pointcut hoặc weaving; nó chặn các lời gọi qua interface. Mục đích của chương trình là xác nhận biến thể và số lần advice chạy trước khi thiết kế benchmark thực thụ.

Lưu thành **AopBaselineDemo.java**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.LongAdder;

public class AopBaselineDemo {
    public interface Calculator {
        int compute(int value);
    }

    private static final Calculator CORE = value -> value * 31 + 7;

    private static Object invokeTarget(
            Method method, Calculator target, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause(); // Giữ nguyên ngoại lệ từ mã nghiệp vụ.
        }
    }

    private static Calculator wrap(
            Calculator target,
            boolean recordTime,
            LongAdder invocations,
            LongAdder totalNanos) {
        return (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] { Calculator.class },
                (proxy, method, args) -> {
                    if (!recordTime) {
                        return invokeTarget(method, target, args); // B1
                    }

                    long started = System.nanoTime();
                    try {
                        return invokeTarget(method, target, args); // B2
                    } finally {
                        long elapsed = System.nanoTime() - started;
                        invocations.increment();
                        totalNanos.add(elapsed);
                    }
                });
    }

    public static void main(String[] args) {
        LongAdder count = new LongAdder();
        LongAdder nanos = new LongAdder();

        Calculator noOpAdvice = wrap(CORE, false, count, nanos);
        Calculator timedAdvice = wrap(CORE, true, count, nanos);

        int b0 = CORE.compute(10);
        int b1 = noOpAdvice.compute(10);
        int b2 = timedAdvice.compute(10);

        if (b0 != b1 || b1 != b2) {
            throw new AssertionError("Các biến thể khác kết quả");
        }

        System.out.println("Ba biến thể đồng nhất: " + (b0 == b1 && b1 == b2));
        System.out.println("Số lần advice đo thời gian: " + count.sum());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AopBaselineDemo.java
java AopBaselineDemo
```

Kết quả xác định:

```text
Ba biến thể đồng nhất: true
Số lần advice đo thời gian: 1
```

**Cách đọc ví dụ:** B0 gọi Calculator trực tiếp; B1 đi qua proxy nhưng không ghi thời gian; B2 đi qua đúng proxy đó và bổ sung timer/counter. Tổng nanos được thu thập nhưng cố ý không in thành “benchmark result”: một lần gọi duy nhất, JIT chưa ổn định và phép đo nằm trong advice nên không thể suy ra overhead chính xác. Timer đo phần gọi đích nhưng không bao trùm toàn bộ chi phí ghi counter hoặc dispatch bên ngoài nó. Khi benchmark thật, cần phát cùng phân phối đầu vào, warm-up, đo end-to-end bên ngoài đường gọi, lặp lượt và phân tích độ biến thiên.

Ví dụ không kiểm tra semantics của mọi kiểu join point; nếu dùng weaving ở mức method/constructor/field, phải xây dựng biến thể và phép xác nhận riêng đúng với join point được hỗ trợ.

## 7. Từ benchmark vi mô đến tải end-to-end

Nên tách hai câu hỏi:

**Vi mô — một join point giá bao nhiêu?** Chọn vài loại join point có chi phí nền khác nhau: method gần như rỗng, method CPU-bound, method cấp phát, lời gọi ném ngoại lệ. Trong JMH, tạo benchmark riêng cho B0/B1/B2, tách setup khỏi phương thức đo, dùng các tham số đầu vào để tránh tối ưu hằng, tiêu thụ kết quả đúng cách và đo cả allocation bằng profiler thích hợp. Giữ cùng dữ liệu/số lời gọi, chọn fork/warm-up/measurement phù hợp và báo phiên bản JDK, cơ chế weaving. Kết quả là chi phí tương đối trong điều kiện cô lập, không phải dự báo trực tiếp p99 HTTP.

**Hệ thống — tải người dùng bị ảnh hưởng thế nào?** Phát tải hỗn hợp đã định nghĩa vào ứng dụng hoàn chỉnh. Ghi dấu thời gian ở bên ngoài, đo throughput thực, latency phân vị, lỗi/timeout, CPU, GC và queue. Thực hiện B0–B3 trên từng mức tải; đối chiếu khả năng duy trì SLO khi hệ thống tiến gần bão hòa. Một lời gọi rất nhỏ có thể tăng chi phí tương đối cao mà ảnh hưởng request tổng thể ít; ngược lại advice ghi log chặn I/O có thể làm p99 tăng phi tuyến khi queue đầy.

Không lấy “requests/second của B0 khi CPU 30%” so trực tiếp với “requests/second B3 khi CPU 100%” rồi kết luận về chi phí mỗi advice. Cần xác định so ở **cùng offered load**, hay tìm **công suất cực đại trong cùng điều kiện SLO**. Đây là hai thí nghiệm và kết luận riêng.

## 8. Ví dụ phân tích kết quả (số liệu giả định)

Giả sử cùng máy, cùng nguồn phát ở **1.000 yêu cầu/giây**, cùng hỗn hợp endpoint; sau nhiều lượt đo thu được bản tóm tắt minh họa:

| Chỉ số | B0 — không AOP | B1 — advice rỗng | B2 — timer/counter | B3 — đầy đủ telemetry |
| --- | ---: | ---: | ---: | ---: |
| p95 latency (ms) | 12,0 | 12,2 | 12,8 | 16,4 |
| p99 latency (ms) | 21,0 | 21,5 | 23,0 | 31,0 |
| CPU process (%) | 42 | 43 | 46 | 62 |
| Lỗi/timeout (%) | 0,0 | 0,0 | 0,0 | 0,2 |
| Completed requests/s | 1.000 | 1.000 | 1.000 | 998 |

Từ bảng **giả định** này, B1 khác B0 ít hơn B3; tác động lớn có thể nằm ở logic advice hoặc pipeline xuất telemetry. Nhưng không thể quy toàn bộ chênh lệch cho một thành phần khi chưa có counters, allocation, exporter backlog, phương sai giữa các lượt và xác nhận môi trường ổn định. Chẳng hạn p95 của B3 so với B0 tăng khoảng 36,7%, là **mức tăng của phân vị p95**, không phải khẳng định mỗi yêu cầu chịu thêm 4,4 ms chính xác.

Để tìm nguyên nhân, làm các thí nghiệm tiếp theo chỉ thay **một chiều biến**: tắt xuất log nhưng giữ timer; thay sampling 1%/10%/100%; giảm cardinality nhãn; đổi batch size; tăng số join point; hoặc thay loại advice quanh thao tác CPU-bound và I/O-bound. Nếu p99 tăng mạnh cùng exporter queue, đó là tín hiệu cần kiểm tra backpressure và khả năng ghi bất đồng bộ. Nếu allocation tăng tỉ lệ số join point, xem xét đối tượng tạo cho mỗi lời gọi.

## 9. Các bẫy thường gặp và cách sửa

| Bẫy | Vì sao kết luận sai | Cách xử lý |
| --- | --- | --- |
| Chỉ chạy biến thể có aspect, không có B0/B1 | Không tách được chi phí nghiệp vụ, interception và advice | Dùng cấu hình đối chứng và xác nhận ngữ nghĩa |
| Test method rỗng rồi suy ra toàn hệ thống | Tỷ lệ overhead bị phóng đại, thiếu I/O, queue, sampling | Kết hợp microbenchmark với hỗn hợp tải thực |
| Chỉ báo trung bình latency | Che các đỉnh chậm và thời điểm nghẽn | Báo p50/p95/p99, lỗi, phân phối và thời gian |
| So cấu hình có tốc độ phát tải khác nhau | Queue và mức bão hòa không tương đương | Giữ offered load và mô tả đạt tải/độ trễ thực |
| Đo ngay khi khởi động | Class loading, weaving, JIT, pool và cache gây nhiễu | Đo cold start riêng; warm-up trước steady-state |
| Dùng đồng hồ trong advice làm thước đo duy nhất | Bỏ sót một phần interception, ghi/xuất metric, queue | Kết hợp đo bên ngoài và profiling bên trong |
| In log đồng bộ cho mọi join point | I/O và lock của logger trở thành điểm nghẽn | Đánh giá sampling/batching và tải exporter thực tế |
| Advice đệ quy hoặc pointcut quá rộng | Nhân số lời gọi và gây nhiễu số đo | Giới hạn pointcut, loại trừ hạ tầng telemetry, đếm invocations |
| Không đo trạng thái lỗi/ngoại lệ | Around advice có thể bỏ sót finally hoặc đổi hành vi | Dùng try/finally, bảo toàn ngoại lệ và đo error path |
| Dùng một lần chạy đẹp nhất | Bỏ qua nhiễu, GC và biến thiên giữa lượt | Lặp nhiều lần, luân phiên thứ tự, lưu raw results |

## 10. Mẫu thiết kế báo cáo có thể tái hiện

Mỗi kết luận về AOP nên đi kèm đủ thông tin để người khác lặp lại phép đo:

- **Giả thuyết và ngưỡng:** tác động được dự đoán, SLO, các giới hạn CPU/RAM/tail latency, tiêu chí thành công và cách tính.
- **Phiên bản và cơ chế:** commit, JDK/JVM flags, phần cứng/quota, loại weaving/dispatch, pointcut, advice order, số join point mỗi request, sampling và exporter.
- **Workload:** nguồn dữ liệu phân phối, loại request, tỷ lệ lỗi, offered load, concurrency, kích thước payload, chế độ open-/closed-loop, thời gian warm-up và đo.
- **Đối chứng:** cấu hình B0/B1/B2/B3, chứng cứ kết quả và ngoại lệ giống nhau, những khác biệt được phép.
- **Bằng chứng:** kết quả theo từng lượt (không chỉ giá trị gộp), p50/p95/p99, throughput, lỗi, CPU, allocation, GC, queue, số invocation, biến thiên giữa lượt và profile khi cần.
- **Kết luận có phạm vi:** tại mức tải nào advice đạt hay vượt ngưỡng; chi phí chủ yếu đến từ cơ chế AOP, bản thân advice hay pipeline phát dữ liệu; độ tin cậy và hạn chế của mẫu.
- **Hành động tiếp theo:** thu hẹp pointcut, giảm cấp phát, giảm cardinality, sampling, batch hoặc chuyển I/O ngoài đường request; **đo lại cùng workload** sau tối ưu.

Ví dụ câu kết luận đúng phạm vi: “Trong ba lượt tải đều của kịch bản S2, trên máy và phiên bản đã ghi, B2 làm p95 tăng trong khoảng đã quan sát so với B0 nhưng vẫn đạt SLO; ở S3, B3 vi phạm SLO do queue xuất telemetry tích lũy.” Câu này nói rõ điều kiện và nguồn tác động, tránh khẳng định toàn bộ AOP luôn nhanh hoặc chậm.

**Nguyên tắc cốt lõi:** baseline hợp lệ + biến thể chỉ khác yếu tố muốn nghiên cứu + tải phản ánh cách hệ thống được dùng + đo cả latency lẫn tài nguyên + lặp và lưu bằng chứng. Khi đủ năm yếu tố đó, số đo AOP mới có giá trị để quyết định pointcut, advice và cấu hình vận hành.
