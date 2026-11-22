# Phân biệt theo dõi bằng lấy mẫu với thu thập dữ liệu bằng mã được chèn

## 1. Mục tiêu và phạm vi

Trong Java, khi muốn hiểu chương trình đang tiêu tốn CPU ở đâu, một request mất bao lâu, hay một phương thức được gọi bao nhiêu lần, có hai cách thu thập bằng chứng thường gặp:

- **Theo dõi bằng lấy mẫu (sampling-based observation/profiling):** quan sát trạng thái của chương trình tại một số thời điểm hoặc một tập con sự kiện, rồi dùng các quan sát đó để ước lượng xu hướng.
- **Thu thập dữ liệu bằng mã được chèn (instrumentation-based collection):** đặt các điểm đo (*probe/hook*) tại những vị trí xác định trong luồng thực thi; khi chương trình đi qua điểm đo, mã thu thập chạy và ghi lại sự kiện, chỉ số hoặc khoảng thời gian.

Sau bài này, bạn cần phân biệt được **dữ liệu quan sát trực tiếp** với **ước lượng thống kê**, chọn cách đo theo câu hỏi cần trả lời, hiểu tác động lên JVM, và tránh nhầm giữa **lấy mẫu stack/CPU** với **lấy mẫu trace**.

Ở đây, "mã được chèn" bao gồm mã đo viết thủ công và mã được đưa vào bằng thư viện, AOP hoặc Java agent biến đổi bytecode. Nhà phát triển không nhất thiết phải sửa source code để có instrumentation.

## 2. Hai cơ chế hoạt động

### 2.1. Sampling: hỏi "chương trình đang làm gì tại thời điểm này?"

Một bộ lấy mẫu có thể thức dậy theo chu kỳ, quan sát thread đang chạy, thu stack trace hoặc trạng thái runtime, rồi cộng dồn số lần xuất hiện của từng phương thức/call path. Ví dụ:

~~~text
Thời gian:   0ms     10ms     20ms     30ms     40ms
             |--------|--------|--------|--------|
Công việc:   [   A   ][B][      A      ][   C   ]
Lấy mẫu:       ^        ^        ^        ^

Kết quả: số mẫu nhìn thấy A/B/C, không phải số lần thật sự gọi A/B/C.
~~~

Nếu phương thức A xuất hiện trong 70/100 mẫu CPU phù hợp, ta có **bằng chứng gợi ý** rằng A hoặc call path chứa A chiếm phần đáng kể thời gian CPU được quan sát. Không được kết luận "A được gọi 70 lần" hay "mỗi lời gọi A mất 70% thời gian".

Có hai lựa chọn phép đo khác nhau:

- **CPU/on-CPU sampling:** quan sát phần thực thi thực sự sử dụng CPU; phù hợp để tìm hot method, đường gọi tiêu tốn CPU. Công việc đang chờ I/O hoặc khóa có thể ít xuất hiện hoặc không xuất hiện trong loại mẫu này.
- **Wall-clock/elapsed-time sampling:** xét thời gian thực trôi qua, có thể quan sát cả chờ, ngủ hoặc blocked tùy công cụ và cấu hình. Hữu ích khi độ trễ cao mà CPU không cao.

Tần suất lấy mẫu, khoảng đo, cách chọn thread và loại stack quyết định ý nghĩa của kết quả. Khoảng lấy mẫu 10 ms không có nghĩa mọi thao tác kéo dài dưới 10 ms đều biến mất, nhưng các thao tác ngắn/hiếm **dễ bị bỏ sót**. Thay đổi tần suất không tự biến số mẫu thành phép đếm chính xác.

### 2.2. Instrumentation: hỏi "điều gì đã xảy ra tại điểm này?"

Giả sử muốn đo một request:

~~~text
request đến
    |
    +--> probe START: ghi thời điểm và ngữ cảnh
    |
    +--> xử lý nghiệp vụ / gọi DB / gọi HTTP
    |
    +--> probe END: tính duration, ghi status/error
    |
response trả về
~~~

Điểm đo có thể tạo:

- **Metric:** đếm lượt gọi/lỗi, ghi histogram thời gian, kích thước payload.
- **Trace/span:** thời điểm bắt đầu/kết thúc, quan hệ cha–con, thuộc tính và lỗi cho một thao tác.
- **Event/log:** sự kiện xác định như retry, cache miss, mở/đóng kết nối.

Nếu **mọi** lời gọi đều đi qua probe và phép ghi nhận không bị bỏ, bộ đếm tại probe phản ánh số lần đi qua vị trí đó; phép đo duration phản ánh khoảng thời gian tại ranh giới được chọn. Nó vẫn có sai lệch do chi phí đo, điểm đặt probe, clock, đồng thời và mất dữ liệu khi xuất telemetry.

Instrumentation có thể được thêm theo nhiều cách:

1. **Thủ công:** gọi timer/counter hoặc OpenTelemetry API ngay trong Java.
2. **Thư viện/framework:** interceptor, filter, aspect hoặc decorator bọc thao tác.
3. **Java agent:** dùng cơ chế Instrumentation API và bytecode transformation ở lúc load/retransform class để đưa hook vào method. Đây là *zero-code* đối với source ứng dụng nhưng vẫn là instrumentation tại runtime.

## 3. So sánh theo điều bạn thực sự đo được

| Góc nhìn | Lấy mẫu | Mã được chèn |
|---|---|---|
| Đơn vị dữ liệu | Snapshot/stack/event được chọn tại một thời điểm | Một lần đi qua probe, span, metric observation hoặc event |
| Câu hỏi mạnh | "CPU tập trung ở call path nào?", "xu hướng trong khoảng đo?" | "Đã có bao nhiêu lỗi?", "request này qua bước nào?", "thời lượng thao tác là bao nhiêu?" |
| Phương thức rất ngắn/hiếm | Có thể không xuất hiện trong mẫu | Có thể được ghi nếu đường đi được instrument |
| Tổng số lần gọi | Không suy trực tiếp từ số mẫu | Có thể đếm gần đúng/đúng tại điểm đo, tùy cấu hình và đường xuất |
| Chi tiết nghiệp vụ | Thường hạn chế nếu chỉ có stack | Có thể thêm status, loại lỗi, tên operation, trace context |
| Chi phí thường phụ thuộc | Số mẫu/giây, loại stack, số thread, thời gian ghi | Tần suất đi qua probe, lượng dữ liệu, đồng bộ, cấp phát, exporter |
| Ảnh hưởng chương trình | Có thể làm lệch mẫu, tốn CPU/bộ nhớ khi lấy quá dày | Có thể làm chậm hot path, thay đổi JIT/inlining và đặc điểm đồng thời |
| Thiết lập ban đầu | Thường thuận tiện để khảo sát vùng chưa biết | Cần chọn điểm đo; agent/framework có thể tự động thêm nhiều điểm |
| Kết luận an toàn | Phân bố/ước lượng có độ bất định | Sự kiện đã quan sát tại ranh giới đã instrument |

**Không có quy tắc rằng sampling luôn rẻ hơn hoặc instrumentation luôn chính xác hơn.** Một profiler lấy mẫu quá dày, ghi stack nặng có thể gây overhead lớn; một counter tối giản có thể rất nhẹ. Ngược lại, trace từng lời gọi trong vòng lặp hàng triệu lượt có thể tốn kém hơn sampling nhiều lần.

## 4. Ví dụ định lượng: cùng một chương trình, hai cách nhìn

Giả sử trong 60 giây dịch vụ thực hiện 100.000 request, trong đó 250 request bị lỗi:

- Nếu đặt **counter** tại đúng điểm kết thúc request, ghi mọi request và lỗi không bị mất, ta nhận được tổng lượt, tổng lỗi và tỷ lệ lỗi: 250 / 100.000 = 0,25%.
- Nếu chỉ lấy **100 stack sample CPU**, không thể suy ra 250 request lỗi. Stack mẫu không chứa phép đếm request và nhiều request quá ngắn để được nhìn thấy.
- Nếu ghi **span cho mỗi request** rồi chọn lưu 10% trace, số span đã lưu cũng không bằng tổng số request. Có thể kết hợp counter cho toàn bộ request với trace sampling để giảm chi phí lưu trace.

Giả sử một call path xuất hiện trong 60/100 mẫu CPU. Cách diễn giải đúng là "khoảng 60% mẫu CPU thu được thuộc call path này trong cửa sổ và cấu hình đang đo". Đây là tín hiệu ưu tiên điều tra, **không** phải thời gian tuyệt đối hay số lượt gọi chính xác.

Với sự kiện hiếm, còn có rủi ro không bắt gặp. Trong mô hình đơn giản, nếu xác suất bắt gặp một trạng thái ở một lần lấy mẫu độc lập là p, xác suất thấy ít nhất một lần sau n mẫu là 1 − (1 − p)^n. Công thức chỉ là minh họa trực giác: mẫu thực tế có thể tương quan theo thời gian nên không áp dụng máy móc để cam kết độ tin cậy.

## 5. Ví dụ Java 17+: instrumentation thủ công

Lưu nội dung sau thành **InstrumentedDemo.java**:

~~~java
public class InstrumentedDemo {
    // Ví dụ chỉ chạy một thread; counter này chưa an toàn cho đa luồng.
    private static long calls;
    private static long failures;
    private static long totalNanos;

    static int square(int n) {
        long start = System.nanoTime(); // Đồng hồ đo khoảng thời gian.
        try {
            if (n < 0) {
                throw new IllegalArgumentException("negative value");
            }
            return n * n;
        } catch (RuntimeException ex) {
            failures++;
            throw ex;
        } finally {
            calls++;
            totalNanos += System.nanoTime() - start;
        }
    }

    public static void main(String[] args) {
        int sum = square(2) + square(3);
        try {
            square(-1);
        } catch (IllegalArgumentException expected) {
            // Giữ chương trình tiếp tục để xem số liệu.
        }

        System.out.println("sum=" + sum);
        System.out.println("calls=" + calls);
        System.out.println("failures=" + failures);
        // totalNanos là số đo runtime, thay đổi giữa các lần chạy.
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 InstrumentedDemo.java
java InstrumentedDemo
~~~

Stdout:

~~~text
sum=13
calls=3
failures=1
~~~

**Giải thích:** Lời gọi lỗi vẫn được tính trong **finally**; phép đo duration dùng **System.nanoTime()** (để tính khoảng thời gian, không phải timestamp theo lịch). Giá trị **totalNanos** phụ thuộc máy/JIT/tải hiện tại nên không có stdout số nanosecond cố định. Đặt timer ở đâu sẽ quyết định nó bao gồm những công việc nào.

Trong ứng dụng đa luồng, thay các biến dùng chung bằng cơ chế an toàn như **LongAdder**, histogram/metric SDK hoặc bộ thu chuyên dụng. Không in log hay đồng bộ khóa tốn kém mỗi lần một phương thức cực nóng chạy. Muốn tính p95/p99, cần quan sát **phân bố độ trễ** bằng histogram/phương pháp thống kê phù hợp; chỉ có tổng thời gian và số lượt thì mới tính được trung bình, chưa suy được percentile.

## 6. Ví dụ Java 17+: lấy mẫu stack định kỳ

Ví dụ sau tự cài một sampler nhỏ để nhìn thấy khác biệt về *cơ chế*. Nó **không** thay thế JFR hoặc profiler production. Lưu thành **SamplingDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SamplingDemo {
    private static volatile boolean recording = true;
    private static volatile long workResult;

    static void busyForMillis(long millis) {
        long end = System.nanoTime() + millis * 1_000_000L;
        long n = 0;
        while (System.nanoTime() < end) {
            n++;
        }
        workResult = n;
    }

    public static void main(String[] args) throws InterruptedException {
        Thread target = Thread.currentThread();
        AtomicInteger hits = new AtomicInteger();

        Thread sampler = new Thread(() -> {
            while (recording) {
                for (StackTraceElement frame : target.getStackTrace()) {
                    if (frame.getClassName().equals("SamplingDemo")
                            && frame.getMethodName().equals("busyForMillis")) {
                        hits.incrementAndGet();
                        break;
                    }
                }

                try {
                    Thread.sleep(10);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        });

        sampler.start();
        busyForMillis(300);
        recording = false;
        sampler.join();

        System.out.println("finished=true");
        System.out.println("busySamples=" + hits.get());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SamplingDemo.java
java SamplingDemo
~~~

Dòng đầu luôn là **finished=true** khi chương trình kết thúc bình thường; dòng thứ hai là **busySamples=...**, số nguyên thay đổi theo lịch chạy thread và thời điểm quan sát (có thể bằng 0 nếu sampler không kịp chạy). Đây **không phải số lần gọi**: **busyForMillis** chỉ được gọi **một lần** nhưng có thể xuất hiện ở nhiều snapshot.

**Tại sao chỉ để minh họa?** **Thread.getStackTrace()** và **Thread.sleep(10)** có chi phí, độ phân giải và sai lệch riêng; việc quan sát thread cũng có thể làm nhiễu kết quả. Profiler thực tế chọn cơ chế lấy mẫu JVM/OS và định dạng dữ liệu thích hợp. Số mẫu nhiều không bảo đảm phép đo tốt nếu sai CPU-vs-wall mode hoặc thời điểm thu thập không đại diện.

## 7. Công cụ JVM: nhận biết chiến lược thu thập

### 7.1. Java Flight Recorder (JFR)

JFR nằm trong JDK và thu nhiều loại sự kiện. Khi bật event lấy mẫu thực thi như **jdk.ExecutionSample**, ta phân tích phân bố stack/method theo mẫu. JFR cũng có các **event theo thời điểm hoặc khoảng thời gian** (ví dụ một số sự kiện khóa, GC, I/O) và hỗ trợ **custom event** từ ứng dụng.

Vì thế, gọi toàn bộ JFR là "chỉ sampling" sẽ sai: **một công cụ có thể kết hợp sampling và event instrumentation**. Loại event, chế độ ghi và settings mới quyết định dữ liệu có ý nghĩa gì.

Có thể thử với một JVM đang chạy (thay PID thật, giữ recording đủ thời gian và bảo đảm quyền truy cập):

~~~bash
jcmd <PID> JFR.start name=investigate settings=profile duration=30s filename=profile.jfr
jfr summary profile.jfr
jfr print --events jdk.ExecutionSample profile.jfr
~~~

Đọc **jfr summary** để kiểm tra loại event thực sự có trong recording. Không có sample trong file chưa đủ chứng minh phương thức không bao giờ chạy; có thể do cấu hình, khoảng đo, thread state hoặc tần suất.

### 7.2. Async-profiler và các profiler lấy mẫu

CPU profiler như async-profiler thường hữu ích để tìm hot stack trên JVM với chi phí được kiểm soát theo cấu hình. Cần đọc rõ chế độ **CPU**, **wall**, **allocation** hoặc **lock**: cùng một tên công cụ nhưng ý nghĩa sample thay đổi theo sự kiện được chọn. Flame graph từ stack sample biểu diễn phân bố mẫu theo đường gọi, không trực tiếp là biểu đồ số lần method được gọi.

### 7.3. Java agent, interceptor và OpenTelemetry

Java agent hoặc interceptor có thể thêm probe lúc vào/ra HTTP handler, truy vấn DB hay lời gọi thư viện. OpenTelemetry có cả **zero-code instrumentation** (thường qua agent) và **code-based instrumentation** (API viết trong ứng dụng) để tạo telemetry như metrics/traces/logs.

**Phân biệt hai kiểu "sampling" dễ gây nhầm:**

- **Stack/CPU sampling:** chọn thời điểm quan sát call stack, phục vụ profiling.
- **Trace sampling:** quyết định trace/span nào được ghi/xuất/giữ lại, ví dụ theo tỷ lệ hoặc sau khi biết kết quả. Nó có thể áp dụng **sau khi code đã được instrument** và không tự biến trace thành CPU profile.

Do đó, hệ thống hoàn toàn có thể **instrument 100% request để đếm metric**, **lấy mẫu một phần trace** để giảm dung lượng, đồng thời **lấy mẫu stack CPU** khi điều tra hiệu năng.

## 8. Độ chính xác, độ phủ và overhead

### 8.1. Đúng câu hỏi trước, đúng thiết bị sau

- **CPU nóng:** dùng CPU sampling trong khoảng đại diện; đọc stack inclusive/exclusive đúng cách và kiểm tra nhiều lần.
- **Latency cao nhưng CPU thấp:** xem wait/blocked/I/O/lock, wall-clock sampling và instrumentation thời gian request/DB.
- **Số request, số lỗi, tỷ lệ retry:** counter tại các ranh giới đã định nghĩa; xác minh đường lỗi và async path đều được tính.
- **Một request cụ thể đi đâu:** distributed trace có span và context propagation qua thread/service; stack profile không thay thế quan hệ nhân quả xuyên dịch vụ.

### 8.2. Lập ngân sách chi phí

Với sampling, tổng số lượt quan sát thường xấp xỉ **tần suất mẫu × thời gian × số thực thể được quan sát**, còn chi phí mỗi mẫu phụ thuộc loại stack/sự kiện và cách lưu. Với instrumentation, tổng lượt thực thi probe gần với **số lần đường code đi qua điểm đo**. Đừng gắn các hệ số này với một con số overhead cố định cho mọi JVM.

Các nguồn tác động thường gặp:

- Probe nằm trong vòng lặp/hot method, tạo object, ghi log đồng bộ hoặc khóa chung.
- Stack capture quá thường xuyên, nhiều thread, export quá nhiều dữ liệu.
- Bytecode weaving thay đổi cấu trúc call path/JIT inlining; profiler và việc ghi JFR cũng có chi phí.
- Ghi thuộc tính có cardinality cao (user ID, request ID, raw URL) làm tăng bộ nhớ, series metric hoặc dung lượng backend.
- Telemetry được buffer, batch, sample hay drop khi quá tải; số liệu đã xuất có thể ít hơn sự kiện thực xảy ra.

Khi so benchmark, phải thống nhất workload, warm-up JIT, phân bổ bộ nhớ, GC, số thread và môi trường; đo baseline so với các cấu hình thu thập khác nhau. **Không suy luận rằng công cụ không ảnh hưởng chương trình chỉ vì nó không sửa source.**

### 8.3. "Chính xác" cần có điều kiện

Instrumentation đo chính xác **tại ranh giới probe** nếu mọi đường gọi được đi qua và dữ liệu không mất; nó không tự động chứng minh nguyên nhân chậm bên trong. Duration của request có thể bao gồm chờ mạng, queue hoặc downstream. Nếu chỉ đo trong controller, có thể bỏ qua thời gian trước controller và sau khi response được commit.

Sampling cung cấp **ước lượng phân bố**, chịu bất định do số mẫu, phạm vi thread, bias và thời đoạn. Top frame cho biết điểm đang chạy tại sample; inclusive stack cho biết chuỗi caller chứa điểm đó. Sai lầm khi gộp hai loại là quy mọi frame trong stack thành "mỗi method dùng bằng ấy CPU" hoặc coi số mẫu là tổng số call.

## 9. Chọn cách đo theo tình huống

| Tình huống | Ưu tiên ban đầu | Vì sao |
|---|---|---|
| Không biết vùng CPU nóng trong dịch vụ | CPU sampling/JFR profiler | Khảo sát diện rộng mà không phải đo trước từng method |
| Cần đếm request, lỗi, retry, cache miss | Counter/event instrumentation | Đơn vị quan sát là mỗi sự kiện cần đếm |
| Cần p95/p99 latency API | Timer/histogram tại ranh giới request | Cần phân bố duration, bao gồm cả request không được trace |
| Cần nhìn một hành trình qua nhiều service | Trace instrumentation + trace context | Cần sự kiện có liên kết cha–con/nhân quả |
| Chỉ một nhánh rất nhanh gây lỗi hiếm | Probe/log có kiểm soát hoặc event chủ đích | Snapshot định kỳ dễ bỏ lỡ nhánh ngắn |
| Độ trễ cao nhưng CPU không cao | Metric duration + wait/lock/I/O events, wall profiling | CPU profile đơn lẻ có thể che khuất thời gian chờ |
| Muốn giữ chi phí telemetry | Giảm tần suất sampling, giới hạn probe, batch/sample traces | Cần cân bằng độ phủ và chi phí, dựa trên phép đo thực tế |

Một quy trình hiệu quả: **(1)** nêu câu hỏi và đơn vị đo; **(2)** dùng sampling để tìm vùng nghi vấn khi chưa biết điểm nóng; **(3)** đặt instrumentation tại ranh giới cần định lượng; **(4)** đối chiếu metrics, traces, profiler và tải hệ thống; **(5)** giảm/chỉnh probe sau điều tra. Nên dùng nhiều nguồn bằng chứng khi kết luận nguyên nhân gốc.

## 10. Sai lầm phổ biến và cách sửa

1. **"100 mẫu ở phương thức X nghĩa là X được gọi 100 lần."** Sai: một lần gọi dài có thể được lấy nhiều mẫu; một triệu lời gọi ngắn có thể chỉ xuất hiện trong vài mẫu.
2. **"Không thấy stack thì code không chạy."** Sai: có thể bỏ lỡ vì tần suất, thời đoạn, trạng thái thread hoặc event không bật.
3. **"Instrumentation luôn thu tất cả."** Sai: probe có thể thiếu đường đi, trace bị sample/drop, agent bỏ qua class/method hoặc ứng dụng crash trước khi flush.
4. **"Trace sampling và CPU sampling là một."** Sai: cái đầu quyết định dữ liệu trace nào được giữ; cái sau chọn thời điểm để quan sát stack/CPU.
5. **"JFR chỉ lấy mẫu."** Sai: JFR có sample event, timed/duration event và custom event; cần kiểm tra từng loại.
6. **"Ghi duration là biết CPU time."** Sai: **System.nanoTime()** trong ví dụ đo thời gian trôi qua, bao gồm cả chờ; muốn CPU time cần phép đo phù hợp.
7. **"Thêm log vào mọi method giúp quan sát miễn phí."** Sai: I/O, string formatting, allocation, lock và exporter có thể thay đổi hệ thống đáng kể.
8. **"Thấy p99 thay đổi thì đã biết nguyên nhân."** Chưa đủ: cần kiểm tra workload, baseline, GC, lock/I/O và telemetry overhead.

## 11. Bài thực hành tự kiểm chứng

**Thử nghiệm A — thấy sampling bỏ lỡ hoặc đếm lặp:** chạy **SamplingDemo** nhiều lần, thay **Thread.sleep(10)** bằng **Thread.sleep(100)** và giảm **busyForMillis(300)** xuống **busyForMillis(20)**. Quan sát **busySamples** thay đổi mạnh; đó là số snapshot, không phải số lời gọi. Kết quả không cố định theo máy.

**Thử nghiệm B — instrumentation ghi cả lỗi:** chạy **InstrumentedDemo** và đổi số lượt gọi. Dù một lời gọi ném exception, **finally** vẫn tăng **calls**; **failures** ghi đúng theo nhánh catch trong ví dụ. Nếu chuyển code sang nhiều thread, hãy thay counter thường bằng công cụ đồng bộ thích hợp trước khi khẳng định số đếm chính xác.

**Câu hỏi kiểm tra:**

- Một API có 1 triệu request nhưng chỉ giữ 1% trace. Có thể dùng số trace đã lưu làm tổng request không? **Không**; hãy dùng counter request phù hợp.
- Một flame graph chứa nhiều mẫu ở parser. Có đủ kết luận parser được gọi nhiều nhất không? **Không**; nó gợi ý parser chiếm nhiều mẫu theo chế độ profiler.
- Muốn biết lần gọi DB cụ thể nào chậm và nằm trong request nào, chọn gì? **Span/timer ở ranh giới DB, gắn trace context**, sau đó đối chiếu profiling nếu cần.
- CPU profile ít mẫu nhưng p99 latency tăng. Nên bỏ qua sự cố? **Không**; điều tra wait/lock/I/O, queue và sự kiện đo thời gian.

## 12. Ghi nhớ

**Sampling trả lời "trong các lần quan sát, chương trình thường ở đâu?"** Nó rất hữu ích để tìm vùng thực thi nóng và xu hướng, với điều kiện đọc kết quả như **ước lượng**.

**Instrumentation trả lời "điều gì xảy ra khi code đi qua điểm đo đã chọn?"** Nó phù hợp cho counter, duration, trace và chi tiết nghiệp vụ, với điều kiện hiểu **độ phủ probe và đường xuất dữ liệu**.

Hai cách **bổ sung cho nhau**: profiling để tìm vấn đề, instrumentation để đo hành vi quan trọng, trace sampling để kiểm soát chi phí lưu trace. Đánh giá kết luận dựa trên câu hỏi đo, ngữ nghĩa dữ liệu, khoảng thời gian và overhead thực tế.

### Tài liệu đối chiếu

- [Oracle — Java Flight Recorder API Programmer's Guide (JDK 17)](https://docs.oracle.com/en/java/javase/17/jfapi/)
- [Oracle — Using Java Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/7/user-guide/using-jdk-flight-recorder.html)
- [OpenTelemetry — Instrumentation](https://opentelemetry.io/docs/concepts/instrumentation/)
