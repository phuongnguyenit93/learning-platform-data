# Kiểm tra chi phí quan sát trong điều kiện tải thực tế với Aspect-Oriented Programming (AOP)

## 1. Vấn đề: chính hoạt động quan sát cũng tiêu tốn tài nguyên

Aspect-Oriented Programming (AOP) giúp gắn những hành vi cắt ngang như metrics, tracing, audit hoặc logging vào nhiều điểm thực thi mà không phải sửa từng phương thức nghiệp vụ. Nhưng mỗi advice được gọi cũng tiêu thụ **CPU, bộ nhớ, băng thông, thời gian chờ và khả năng đồng bộ hóa giữa các thread**. Nếu aspect được áp dụng tại một phương thức rất nóng, một chi phí nhỏ cho mỗi lần gọi có thể trở thành nút nghẽn lớn khi hệ thống chịu lưu lượng thực tế.

Bài toán không chỉ là “một lời gọi chậm thêm bao nhiêu nano giây”. Phải kiểm tra xem **hệ thống còn đáp ứng được số lượng request, độ trễ, tỷ lệ lỗi và giới hạn tài nguyên đã cam kết khi bật quan sát hay không**, đặc biệt ở ngưỡng tải cao, lúc downstream chậm và khi kênh thu thập telemetry trục trặc.

Ví dụ: một advice làm phát sinh thêm 5 µs trên một lần gọi có thể không đáng kể với một thao tác I/O 100 ms. Nhưng nếu một request đi qua 20 join point cùng loại, chi phí trực tiếp danh nghĩa có thể lên tới khoảng 100 µs/request, chưa tính đồng bộ hóa, cấp phát, GC và việc ghi ra ngoài. Ở 20.000 request/giây, 100 µs/request tương ứng khoảng **2 CPU-second mỗi giây** chỉ cho lượng công việc bổ sung đó (ước lượng lý tưởng, không phải kết quả đo). Đây là lý do phải kiểm thử ở phạm vi workload thật.

### Kết quả học tập

Sau bài này, người học có thể:

- Liệt kê các nguồn overhead mà proxy, weaving và advice có thể gây ra.
- Xác định phép thử baseline và biến thể có thể so sánh được.
- Đo thông lượng, độ trễ phân vị, CPU, allocation, GC, queue và error rate khi bật/tắt instrumentation.
- Phân biệt microbenchmark đo cơ chế với kiểm thử tải đánh giá tác động toàn hệ thống.
- Nhận diện nhiễu do warm-up, môi trường, giới hạn tải, sampling và sai lệch cách đo.
- Xây dựng quyết định triển khai dựa trên ngân sách chi phí quan sát và đặc tính suy giảm khi quá tải.

## 2. Xác định đúng phạm vi quan sát của AOP

Trước khi đo chi phí, cần xác định **tập join point thực sự được instrument** và loại advice đang chạy. Proxy, bytecode weaving và instrumentation tại lúc tải lớp có những khoản chi phí riêng; do đó phép so sánh chỉ đáng tin khi phạm vi can thiệp được nêu rõ.

Các cơ chế này có bề mặt chi phí khác nhau:

| Thành phần | Nguồn chi phí có thể xuất hiện | Điều cần kiểm tra |
| --- | --- | --- |
| Proxy / gọi gián tiếp | Thêm bước chuyển tiếp lời gọi, dispatch qua reflection hoặc method handle, giảm cơ hội tối ưu/inlining trong một số trường hợp | Overhead trên hot path và mức tăng khi số join point tăng |
| Weaving / bytecode instrumentation | Thêm nhánh điều kiện, lệnh ghi timestamp, thay đổi kích thước mã, ảnh hưởng tối ưu JIT | Chi phí runtime; riêng chi phí khởi động, nạp lớp và biên dịch |
| Around advice | Đo thời gian, xử lý exception, mở/đóng scope, thay đổi call stack | p50/p95/p99 và chi phí khi lỗi |
| Metrics | Cập nhật counter, histogram, nhãn, map/registry | Contention, tạo series mới, cấp phát và chi phí export |
| Tracing | Tạo span, truyền context, ghi attributes/events, kết thúc span | Số span/request, cấp phát, sampling và độ trễ |
| Logging / audit | Format chuỗi, stack trace, serialize, append queue, file/network I/O | Throughput, backpressure, chính sách đầy hàng đợi |
| Thu thập bất đồng bộ | Queue, batch, worker, kết nối tới collector | Memory/queue depth, retry, mất telemetry và chi phí nền |

**Quan sát ở đâu quyết định đo cái gì.** Advice bao quanh phương thức đồng bộ có thể đo toàn thời gian gọi. Với phương thức trả về một `CompletionStage`, `Future` hoặc publisher sự kiện, thời gian từ lúc gọi đến lúc trả về chỉ là thời gian **khởi tạo/trả đối tượng**, không phải thời gian xử lý bất đồng bộ đến kết quả cuối. Muốn đo vòng đời, instrumentation phải bám vào completion/cancellation/subscription/terminal signal tương ứng.

Cần ghi chính xác số điểm được chọn: một request đi qua API, service và repository có thể kích hoạt nhiều advice. Ba phép đo riêng không có nghĩa là ba request người dùng. Nếu tăng số join point, phải biết tăng do phạm vi đo thay đổi hay do mỗi advice đắt hơn.

## 3. Chi phí nào cần đo?

### 3.1 Độ trễ và thông lượng

- **Latency**: thời gian để một thao tác hoàn tất, đo theo điểm đầu/cuối rõ ràng. Theo dõi p50, p95, p99; có thể bổ sung p99.9 nếu đủ mẫu và yêu cầu phù hợp.
- **Throughput**: số thao tác hoàn tất trong một đơn vị thời gian, chẳng hạn request/giây. Phân biệt tốc độ yêu cầu *được gửi vào* với tốc độ *thực sự xử lý xong*.
- **Concurrency / in-flight**: số thao tác đang xử lý. Với cùng lưu lượng, nếu latency tăng, số thao tác đồng thời có thể tăng, khiến thread pool, connection pool và hàng đợi bão hòa.
- **Error rate và timeout rate**: fraction thao tác thất bại trên tập thao tác có trạng thái kết thúc, với cùng định nghĩa trạng thái ở baseline và variant.
- **Queueing delay**: thời gian chờ trước khi thực thi, có thể tăng mạnh khi tải tiệm cận khả năng phục vụ.

Đối với cùng một workload, một hệ thống có thể giữ throughput gần như không đổi nhưng p99 tăng mạnh trước khi bắt đầu xuất hiện timeout. Vì vậy chỉ so sánh request/giây là chưa đủ.

### 3.2 CPU, memory, GC và vận hành

Theo dõi ít nhất các nhóm sau nếu môi trường có khả năng đo:

- CPU utilization, CPU time và số core hiệu dụng; với máy ảo/container, kiểm tra quota/throttling để không nhầm thiếu CPU với overhead của advice.
- Tốc độ cấp phát bộ nhớ (`bytes allocated per request`), heap live set, heap sau GC, số lần và thời gian GC pause; thay đổi allocation có thể làm p99 xấu đi dù CPU trung bình chưa cao.
- Số thread, trạng thái blocked/waiting, contention trên lock/atomic, context switching; một metrics registry hoặc logger có lock nóng có thể tạo đuôi trễ dài.
- I/O và network tới hệ thống thu thập, số event/span/log mỗi giây, kích thước batch, độ sâu queue, số lần retry và số bản ghi telemetry bị loại.
- Startup time, thời gian class loading/JIT và memory footprint trong trường hợp instrumentation ảnh hưởng giai đoạn khởi động.

**Không suy diễn nguyên nhân chỉ từ một đường biểu đồ.** CPU tăng có thể do thêm tính toán; p99 tăng có thể do GC, contention, I/O telemetry hoặc đã vượt khả năng phục vụ. Nên kết hợp số liệu từ ứng dụng, runtime và hệ thống giám sát.

### 3.3 Chỉ số riêng của hệ thống quan sát

Thêm số đo về chính công cụ đo:

- `aspect_invocations_total`: số lần advice thực sự chạy, theo tên thao tác đã chuẩn hóa.
- `telemetry_events_enqueued_total`, `telemetry_events_dropped_total`: đếm lượng đã đưa vào queue và lượng bị bỏ.
- `telemetry_export_latency`, `telemetry_export_failures_total`: độ trễ/lỗi xuất dữ liệu.
- `telemetry_queue_size`, `telemetry_queue_capacity`: độ đầy và giới hạn queue.
- `sampled_traces_total` hoặc tỷ lệ sampling áp dụng theo cấu hình.

Nếu chỉ đo “tracing bật khiến request chậm hơn” mà không biết queue/logging hoạt động thế nào, khó phân biệt chi phí cố định của advice với chi phí tăng do collector nghẽn.

## 4. Mô hình tính overhead và cách diễn giải

Giả sử cùng một workload và cùng điểm đo:

`delta_latency = latency_instrumented − latency_baseline`

`relative_overhead = (latency_instrumented − latency_baseline) / latency_baseline × 100%`

Ví dụ minh họa (các giá trị là giả định, **không phải benchmark thực tế**):

| Chỉ số | Baseline (tắt advice quan sát) | Variant (bật advice quan sát) | Diễn giải |
| --- | ---: | ---: | --- |
| p50 latency | 8,0 ms | 8,3 ms | Tăng 0,3 ms, tương đương 3,75% |
| p95 latency | 20 ms | 22 ms | Tăng 2 ms, tương đương 10% |
| p99 latency | 42 ms | 61 ms | Tăng 19 ms, tương đương ~45,2% |
| Throughput | 9.800 req/s | 9.300 req/s | Giảm 500 req/s, tương đương ~5,1% |
| CPU | 62% | 76% | Tăng 14 **điểm phần trăm** |
| GC pause p99 | 15 ms | 24 ms | Có tín hiệu cần khảo sát allocation/GC |

Một con số overhead trung bình không thay thế được toàn bộ bảng. p99 có thể suy giảm nặng hơn p50 vì lock, queue hoặc GC. Chênh lệch **tỷ lệ phần trăm** và **điểm phần trăm** cũng khác nhau: CPU từ 62% lên 76% là +14 điểm phần trăm, hay tăng tương đối khoảng 22,6%.

Khi so sánh percentiles, phải lấy p99 trên **cùng loại operation, cửa sổ đo và phân phối workload**. Chênh lệch hai giá trị p99 giữa hai mẫu không phải “p99 của overhead ở từng request”; muốn đo phân phối overhead theo lời gọi cần cách ghép mẫu tương ứng hoặc thiết kế thí nghiệm riêng.

### Khi một request có nhiều điểm cắt

Mô hình đơn giản:

`estimated_extra_cpu ≈ request_rate × invocations_per_request × cpu_cost_per_advice`

Công thức chỉ là **ước lượng bậc độ lớn** trong tình huống chi phí gần cộng tính, không thay thế đo tải. Nó không mô tả nonlinearity do contention, cache, GC, queue, branch prediction hoặc JIT. Đặc biệt, một advice không đồng bộ có thể chuyển chi phí CPU ra background worker; request latency giảm không có nghĩa tổng chi phí tài nguyên biến mất.

## 5. Thiết kế phép thử có thể kết luận được

### Bước 1: Xác định câu hỏi và ngưỡng chấp nhận

Trước khi đo, viết rõ:

- Điều kiện tải nào quan trọng: tải bình thường, tải đỉnh, burst, hoặc khi downstream bị chậm?
- Mức tăng p95/p99, CPU, allocation, số log thất lạc hoặc throughput giảm bao nhiêu được chấp nhận?
- Chỉ đo một advice, tập pointcut, hay toàn bộ pipeline telemetry?
- Cần đạt đồng thời mục tiêu độ trễ, tỷ lệ lỗi, chi phí phần cứng và tính đầy đủ của audit không?

Ví dụ một **tiêu chí nội bộ minh họa**, không phải chuẩn chung: “Ở 5.000 req/s trong 30 phút, p99 tăng dưới 5 ms, throughput đáp ứng tốc độ đến, lỗi không tăng quá 0,1 điểm phần trăm, CPU còn dư ít nhất 20%, queue không tích lũy liên tục, telemetry drop dưới ngưỡng đã quy định.” Ngưỡng thực tế phụ thuộc SLO và khả năng chấp nhận mất telemetry.

### Bước 2: Tạo baseline và variant

Dùng **cùng phiên bản ứng dụng, cùng máy/CPU quota, heap, GC, JDK, cấu hình thread pool, dữ liệu thử, trạng thái cache và traffic generator**. Khác biệt chủ động phải là cấu hình instrumentation:

- **A – Baseline:** giữ business code và workload; không gắn advice quan sát đang đánh giá.
- **B – Aspect enabled:** gắn đúng tập pointcut/advice; xác nhận advice thực sự được gọi và metric/traces được tạo.
- Khi cần phân rã chi phí: thêm các biến thể độc lập như **proxy-only**, **timestamp/counter-only**, **logging-only**, **tracing with sampling**, và **full export**. Tránh bật/tắt cùng lúc quá nhiều yếu tố rồi không biết yếu tố nào gây tăng chi phí.

Nếu có thể dùng một binary với cờ bật/tắt và phần codepath tương đương để hạn chế khác biệt build, phải kiểm tra cờ tắt có còn tốn chi phí dispatch/branch hay không. “Disable export nhưng vẫn tạo span” **không đồng nghĩa** với tắt toàn bộ instrumentation.

### Bước 3: Giữ workload đại diện cho sản xuất

Thử với các đặc tính đã được ẩn danh và tổng hợp:

- Tỷ lệ read/write, API nóng/lạnh, kích thước payload, độ phức tạp truy vấn, số downstream call, cache-hit rate.
- Phân bố thời gian giữa request, mức đồng thời, session think time và burst; không chỉ một vòng lặp gọi đồng loạt.
- Những kịch bản gây lỗi, timeout, retry, cancellation; đường lỗi đôi khi phát sinh stack trace và log nhiều hơn đường thành công.
- Môi trường tương tự production về latency network, database/queue, kích thước thread pool, JIT warm-up và runtime.
- Đặt **load generator** trên tài nguyên độc lập hoặc theo dõi CPU của nó để chắc chắn bên tạo tải chưa trở thành nút nghẽn.

Không sao chép dữ liệu định danh hay bí mật người dùng vào workload. Có thể dùng dữ liệu tổng hợp tái hiện phân bố tải quan sát được.

### Bước 4: Chạy nhiều mức tải

Không chỉ thử một mốc. Xem ít nhất:

1. **Idle / thấp:** biết chi phí cố định và nền tài nguyên.
2. **Tải điển hình:** đo overhead trong điều kiện thường ngày.
3. **Tải đỉnh hợp lệ:** kiểm tra SLO và tài nguyên còn dư.
4. **Tiệm cận bão hòa:** tìm điểm gãy của latency, queue, CPU, error; xác định liệu instrumentation làm giảm capacity.
5. **Burst và recovery:** kiểm tra queue telemetry có phình ra, retry dồn, hoặc mất nhiều thời gian mới trở lại ổn định không.
6. **Collector chậm hoặc ngắt kết nối:** xem advice, exporter và bộ đệm phản ứng thế nào mà không gây tràn bộ nhớ hoặc chặn business thread.

Không nhất thiết cố ý gây quá tải trong môi trường đang phục vụ người dùng. Thực hiện thử nghiệm có giới hạn và isolation thích hợp.

### Bước 5: Warm-up, đo steady state và lặp lại

JVM có JIT, class loading, tối ưu bộ nhớ và cache. Một lần chạy đầu có thể chậm bất thường hoặc nhanh bất thường so với steady state. Khởi động ứng dụng, đưa qua workload warm-up có đại diện, rồi đo các khoảng bằng nhau.

Nên thử nhiều cặp A/B qua nhiều lần chạy, thay đổi thứ tự A/B hoặc luân phiên theo một kế hoạch cố định để giảm tác động của nhiệt độ, tài nguyên và thời gian; ghi lại thứ tự, cấu hình, build hash, runtime, đặc tính máy và thời gian đo. Tránh lấy một lần A vào buổi sáng rồi một lần B khi máy đang chạy nhiều tác vụ khác.

Thu thập kết quả có độ biến thiên: median qua nhiều run, phạm vi sai số hoặc khoảng tin cậy khi đủ dữ liệu. Sự khác biệt vài phần trăm có thể chỉ là nhiễu nếu không chứng minh được kết quả ổn định.

### Bước 6: Kiểm tra đúng workload thực sự đã chạy

Một phép thử chỉ có ý nghĩa khi A/B xử lý số yêu cầu và nội dung tương đương:

- So sánh **offered load** (lượng yêu cầu đưa vào) và **achieved throughput** (lượng được hoàn tất).
- Kiểm tra số lượng kết quả thành công/lỗi, payload, checksum hoặc invariant nghiệp vụ.
- Xác nhận không có retry/timeout ẩn, không thay đổi cache-hit ratio và không bỏ request ở load generator.
- Với phép thử thời gian cố định, đo throughput; với số lượng thao tác cố định, đo thời gian hoàn thành. Cả hai hữu ích nhưng kết luận khác nhau.

### Open-loop, closed-loop và coordinated omission

Trong mô hình **closed-loop**, client chỉ gửi request mới sau khi request trước hoàn thành. Khi server chậm, client cũng giảm tốc độ gửi, vô tình che khuất queueing và tail latency. **Open-loop** phát sinh request theo lịch độc lập với completion, gần hơn với nguồn tải bên ngoài trong nhiều hệ thống, nhưng phải đo cả request bị từ chối và chậm trễ khi generator hoặc queue bị quá tải.

**Coordinated omission** xảy ra khi phép đo bỏ qua khoảng thời gian request *đáng ra* được gửi nhưng không được gửi vì bộ tạo tải đang chờ. Để tránh kết luận p99 quá đẹp, cần cấu hình generator và cách ghi thời điểm arrival/completion phù hợp mô hình lưu lượng mong muốn. Hãy xác định rõ đang đo **service time**, **end-to-end latency**, hay **latency gồm thời gian nằm trong queue**.

## 6. Ví dụ Java 17+: so sánh lời gọi thường với lời gọi qua advice

Đoạn Java sau là một **minh họa giáo dục có thể chạy độc lập** về cách xây dựng baseline và variant. Sử dụng JDK dynamic proxy cho lời gọi qua interface: trong advice có hai lần đọc `System.nanoTime()`, cập nhật `LongAdder` và chuyển tiếp ngoại lệ gốc. Driver dùng nhiều thread, cổng bắt đầu chung và cùng dữ liệu đầu vào; so sánh checksum để phát hiện lỗi ngữ nghĩa.

**Điều quan trọng:** đây là một **load experiment nhỏ để học cơ chế**, không phải bộ benchmark đủ chính xác để kết luận overhead sản xuất. Nếu cần microbenchmark đáng tin cậy, dùng harness như JMH để quản lý warm-up, fork, dead-code elimination và đo phân phối; nếu cần quyết định về SLO, chạy kiểm thử end-to-end ở workload gần production.

**Tệp: `AopObservationCostDemo.java`**

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAdder;

public class AopObservationCostDemo {
    interface Work {
        long compute(int input);
    }

    static final class PlainWork implements Work {
        @Override
        public long compute(int input) {
            long value = input;
            for (int i = 0; i < 64; i++) {
                value = (value * 1664525L + 1013904223L) & 0x7fffffffL;
            }
            return value;
        }
    }

    static final class Metrics {
        final LongAdder calls = new LongAdder();
        final LongAdder failures = new LongAdder();
        final LongAdder durationNanos = new LongAdder();

        void record(long elapsed, boolean failed) {
            durationNanos.add(Math.max(0L, elapsed));
            if (failed) {
                failures.increment();
            }
            calls.increment();
        }
    }

    static Work observed(Work target, Metrics metrics) {
        InvocationHandler advice = (Object proxy, Method method, Object[] args) -> {
            if (method.getDeclaringClass() == Object.class) {
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException ex) {
                    throw ex.getCause();
                }
            }

            long start = System.nanoTime();
            boolean failed = true;
            try {
                Object result = method.invoke(target, args);
                failed = false;
                return result;
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            } finally {
                metrics.record(System.nanoTime() - start, failed);
            }
        };

        return (Work) Proxy.newProxyInstance(
            Work.class.getClassLoader(),
            new Class<?>[] { Work.class },
            advice
        );
    }

    record Trial(long elapsedNanos, long checksum) {}

    static Trial run(Work work, int threads, int callsPerThread)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Long>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < threads; t++) {
                Callable<Long> task = () -> {
                    ready.countDown();
                    start.await();
                    long checksum = 0L;
                    for (int i = 0; i < callsPerThread; i++) {
                        checksum += work.compute(i);
                    }
                    return checksum;
                };
                tasks.add(pool.submit(task));
            }

            ready.await();
            long beganAt = System.nanoTime();
            start.countDown();

            long checksum = 0L;
            for (Future<Long> task : tasks) {
                checksum += task.get();
            }
            return new Trial(System.nanoTime() - beganAt, checksum);
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        final int threads = 4;
        final int callsPerThread = 20_000;

        Work plain = new PlainWork();

        // Làm nóng cả hai đường thực thi; bỏ số đo của giai đoạn này.
        Work warmObserved = observed(plain, new Metrics());
        for (int i = 0; i < 2; i++) {
            run(plain, threads, 2_000);
            run(warmObserved, threads, 2_000);
        }

        Metrics metrics = new Metrics();
        Work withAdvice = observed(plain, metrics);

        Trial a = run(plain, threads, callsPerThread);
        Trial b = run(withAdvice, threads, callsPerThread);

        boolean equal = a.checksum() == b.checksum();
        long expected = (long) threads * callsPerThread;

        System.out.printf(
            Locale.ROOT,
            "calls=%d failures=%d equal=%s expected=%d%n",
            metrics.calls.sum(), metrics.failures.sum(), equal, expected
        );

        double msA = a.elapsedNanos() / 1_000_000.0;
        double msB = b.elapsedNanos() / 1_000_000.0;
        double extraNsPerCall =
            (b.elapsedNanos() - a.elapsedNanos()) / (double) expected;

        System.out.printf(
            Locale.ROOT,
            "plain=%.3f ms observed=%.3f ms delta=%.1f ns/call%n",
            msA, msB, extraNsPerCall
        );

        if (!equal || metrics.calls.sum() != expected) {
            throw new IllegalStateException("Incorrect observation");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AopObservationCostDemo.java
java AopObservationCostDemo
~~~

Dòng stdout đầu tiên (với lần chạy thành công bình thường) có giá trị xác định:

~~~text
calls=80000 failures=0 equal=true expected=80000
~~~

Dòng tiếp theo có dạng:

~~~text
plain=<số đo> ms observed=<số đo> ms delta=<số đo> ns/call
~~~

Ba số ở dòng thứ hai **thay đổi theo máy, JIT, scheduler, tải và cách đo**. Chúng thậm chí có thể cho delta âm trong một lần chạy do nhiễu; không được sửa kết quả âm thành bằng chứng “advice tăng tốc”. Cần chạy nhiều lần, đảo thứ tự baseline/variant và quan sát phân phối trước khi rút kết luận.

Mỗi thread cộng kết quả của tất cả lời gọi `compute(i)`, rồi chương trình cộng checksum của các thread. Khi baseline và biến thể có cùng checksum, hai đường đã tính ra cùng kết quả cho workload này. Counter của advice chỉ được đọc **sau khi toàn bộ `Future` hoàn tất**, nên `LongAdder.sum()` phản ánh đủ 80.000 lần gọi của biến thể trong đoạn đo. Thời gian `Trial` đo theo đồng hồ bao ngoài cả nhóm thread; nó không phải p99 latency của từng lần `compute`.

**Vì sao code không tự động là một phép đo chuẩn?**

- Baseline dùng lời gọi trực tiếp, variant thêm proxy/reflection/timestamp/counter; phép đo gộp các chi phí này.
- Warm-up rất ngắn, không có fork hay cách ly tác vụ nền; thứ tự A trước B có thể gây bias.
- Không tạo traffic từ nhiều máy, network/database, log exporter, phân phối request hay áp lực GC thực tế.
- Không đo p95/p99, allocation, throughput ổn định, tình trạng bão hòa, queue hay lỗi xuất telemetry.

Hãy xem mẫu như một bộ khung để hiểu **đo cái gì và vì sao cần đối chứng**. Nó giúp chứng minh aspect hoạt động đúng, rồi mới bước sang benchmark và load test đủ điều kiện.

## 7. Tách các nguồn overhead để tìm nguyên nhân

Một chuỗi phép thử từ tối thiểu đến đầy đủ giúp phân tách chi phí:

1. **Business only:** thao tác gốc.
2. **Proxy/weaving only:** gắn cơ chế chặn nhưng advice rỗng hoặc chỉ chuyển tiếp một lần.
3. **Counting:** cập nhật counter, không format log hoặc gửi network.
4. **Timing:** thêm timestamp và histogram.
5. **Tracing:** tạo scope/span, ghi attribute, áp dụng sampling.
6. **Logging / serialization:** dựng thông điệp và ghi vào pipeline log.
7. **Exporter end-to-end:** batch, queue, network, retry và collector.

Chênh lệch giữa các bước giúp khoanh vùng nguồn chi phí, nhưng chỉ hợp lệ nếu điều kiện tải và cấu hình giữ nguyên. Khi bước 7 xấu đi mạnh so với bước 6, cần đo queue/export/backpressure chứ không vội quy lỗi cho chi phí ghi `nanoTime()`.

### Metrics không phải luôn “rẻ”

Cập nhật một `LongAdder` thường phù hợp hơn một khóa toàn cục tại hot path có nhiều thread, nhưng vẫn có chi phí; registry có thể phát sinh phân bổ bản ghi mỗi khi tạo series. Histogram có thể dùng nhiều bucket, cập nhật nhiều cấu trúc, hoặc cạnh tranh trên bộ nhớ dùng chung. Nếu dùng nhãn động theo user ID/URL tùy ý, số lượng series tăng không giới hạn, làm tăng CPU và heap cho cả ứng dụng lẫn backend lưu metrics.

Nên định nghĩa nhãn có số giá trị hữu hạn như operation chuẩn hóa, outcome và loại exception đã gom nhóm. ID request, email hoặc tham số nghiệp vụ chi tiết phù hợp hơn với trace/log được kiểm soát quyền truy cập. Cần đo số series và memory của registry khi workload thay đổi, không chỉ khi có vài giá trị nhãn.

### Trace sampling và ảnh hưởng tới phép đo

**Head sampling** chọn trace sớm; **tail sampling** có thể cần giữ thêm dữ liệu trong bộ nhớ trước khi quyết định. Sampling có thể giảm chi phí export nhưng đôi khi vẫn tốn chi phí tạo context/span nội bộ; mức tiết kiệm phụ thuộc điểm sampling và pipeline. Test ít nhất sampling thấp, sampling thiết kế cho production và tình huống tracing dày đặc. Ghi rõ xác suất sampling và những sự kiện vẫn luôn được thu thập.

Không nhầm “chỉ lưu 1% trace” với “chỉ có 1% advice chạy”. Nếu advice vẫn chạy cho 100% request, phép đo proxy dispatch và kiểm tra cờ sampling vẫn tác động lên 100% hot path.

### Logging, I/O và hàng đợi

Log đồng bộ trực tiếp tới file/network có thể chặn thread xử lý request. Đưa log sang queue riêng giúp giảm độ trễ trên request khi queue còn chỗ, nhưng cần giới hạn kích thước. Nếu collector chậm hơn tốc độ sinh log trong thời gian dài, queue sẽ đầy. Phải quyết định: block caller, bỏ bản ghi, giảm sampling, ghi fallback hay backpressure nguồn. Lựa chọn nào cũng có trade-off về độ trễ, độ tin cậy và đầy đủ của bằng chứng audit.

Nếu yêu cầu bảo đảm mọi audit event được lưu, không thể mặc định chọn bỏ log. Chi phí độ bền dữ liệu và chính sách lỗi phải được đưa vào điều kiện chấp nhận và thiết kế kiến trúc ngay từ đầu.

## 8. Đọc kết quả khi hệ thống bão hòa

Trước ngưỡng bão hòa, advice có thể khiến CPU tăng mà latency chỉ tăng nhẹ. Khi chạm giới hạn CPU, thread pool, connection pool hoặc queue, chỉ một thay đổi nhỏ về nhu cầu tài nguyên có thể làm p99, timeout và queueing tăng rất mạnh. Vì thế một phép thử chỉ ở mức tải 10% sẽ khó dự đoán điều xảy ra tại đỉnh 90%.

Xét mô hình đơn giản của hàng đợi:

- Tốc độ đến `λ` (requests/giây).
- Tốc độ xử lý tối đa `μ` (requests/giây), với giả định mô hình có ý nghĩa cho hệ đang xét.
- Khi `λ` tiến gần `μ`, queue và thời gian chờ thường nhạy cảm hơn nhiều với mỗi phần chi phí mới.
- Khi `λ` vượt khả năng phục vụ bền vững, tồn đọng sẽ tăng hoặc hệ thống phải từ chối/giảm tải.

Không áp dụng một công thức queue đơn giản như quy luật phổ quát cho mọi kiến trúc. Nhưng về thực hành, luôn phải vẽ **đường cong tải → p95/p99 → throughput → error → CPU/queue**, để thấy điểm cong gãy của baseline và variant. Instrumentation được xem là có vấn đề nếu điểm gãy chuyển xuống mức tải nằm trong phạm vi vận hành cần hỗ trợ.

**Little's Law** ở trạng thái ổn định (`L = λ × W`) giúp kiểm tra tính hợp lý giữa số request trung bình đang trong hệ, throughput và thời gian chờ trung bình, miễn là tập request và ranh giới đo nhất quán. Đây là quan hệ trung bình ở hệ ổn định, không phải công thức suy ra p99 hoặc cam kết về queue khi đang biến động mạnh.

## 9. Thí nghiệm lỗi có chủ đích với đường telemetry

Một aspect quan sát có thể hoạt động tốt ở trạng thái bình thường nhưng gây sự cố thứ cấp khi hệ giám sát chậm hoặc mất kết nối. Trong môi trường test có kiểm soát, hãy thử:

| Điều kiện | Dấu hiệu cần quan sát | Hành vi thiết kế mong muốn |
| --- | --- | --- |
| Collector phản hồi chậm | Queue tăng, exporter latency tăng | Có giới hạn queue, timeout và chiến lược đầy |
| Collector ngắt kết nối | Retry tăng, thread nền tồn tại, heap thay đổi | Retry có giới hạn, không tích lũy vô hạn |
| Số log/span đột biến khi lỗi | Logging làm CPU và network tăng | Quota/sampling/batch hoặc năng lực dự phòng thích hợp |
| Backend từ chối dữ liệu | Số event xuất thất bại | Metric drop/error chính xác và thông báo trạng thái |
| Lỗi trong logic advice | Exception instrumentation ảnh hưởng request | Chính sách cách ly hoặc fail-closed được định nghĩa |
| Thread pool/queue telemetry đầy | p99 và throughput nghiệp vụ biến đổi | Không đẩy công việc vô giới hạn lên request path |
| Ứng dụng shutdown/redeploy | Flush bị ngắt, event còn trong queue | Timeout và chính sách flush/at-least-once rõ ràng |

Nếu quan sát chỉ phục vụ vận hành, phần lớn ứng dụng muốn telemetry failure không tự thay đổi kết quả nghiệp vụ; tuy vậy một số kiểm soát bảo mật/audit có thể yêu cầu ngừng xử lý khi ghi nhận không thành công. **Không có một chính sách fail-open/fail-closed áp dụng cho mọi trường hợp**. Bài đo cần đánh giá đúng hợp đồng đã chọn.

## 10. Tính đúng đắn vẫn là điều kiện đầu tiên

Chi phí thấp nhưng thay đổi kết quả chương trình là thất bại. Kiểm thử trước/sau instrumentation phải đảm bảo:

- Cùng kết quả, cùng side effect và đúng số lần gọi thao tác gốc; advice ghi đo không tự gọi lại, retry hoặc lọc response.
- Caller vẫn nhận đúng exception gốc và cancellation/timeout semantics phù hợp.
- Không mất context khi chuyển thread, không rò rỉ scope hoặc `ThreadLocal` giữa các request.
- Với nguồn sự kiện có backpressure, không tự gọi thêm `request(n)`, không tạo subscriber mới và không thêm queue không giới hạn.
- Không có recursion vì pointcut vô tình chọn chính thư viện telemetry, cũng không ghi nhận sai vì self-invocation đi vòng ngoài cơ chế proxy.
- Counter chính xác theo đơn vị logic đã chọn: per-attempt, per-method, per-request hoặc per-subscription. Không cộng chồng những đại lượng khác đơn vị.

Cũng phải kiểm chứng dữ liệu **của chính phép đo**: counter đã bắt đủ hot path chưa, metric có đang đo từng phương thức hay cả luồng bất đồng bộ, sample có đại diện cho cả success lẫn failure, exporter drop đã được tính, nhãn có bị trộn giữa các nhóm workload không.

## 11. Báo cáo kiểm thử và tiêu chí ra quyết định

Một báo cáo hữu ích cần có cấu trúc có thể tái hiện. Ví dụ:

~~~text
Scope: around advice cho operation catalog.lookup
Runtime: JDK 17, cấu hình CPU/heap/GC được ghi kèm
Scenario: traffic hỗn hợp theo phân bố request định nghĩa trước
A: chưa bật advice quan sát
B: bật cùng một bộ pointcut + counter + histogram + tracing/export
Load: 500 / 2.000 / 5.000 / 8.000 req/s; burst và collector chậm
Warm-up: theo tiêu chí steady state đã kiểm chứng
Measurement: nhiều lần, cùng khoảng đo; thứ tự A/B được ghi lại
Business correctness: checksum, success/failure, retry và timeout
Performance: achieved throughput, p50/p95/p99, errors, CPU, allocation, GC
Telemetry: span/log volume, queue depth, drop, export error/latency
Decision: đạt/không đạt theo ngưỡng đã đặt trước; ghi rõ bất định
~~~

Đây là **khung báo cáo minh họa**, không phải kết quả thí nghiệm đã được thực thi.

Để tránh kết luận thiếu bằng chứng, kết quả cuối cần trả lời bốn câu hỏi:

1. **Bao nhiêu?** Chi phí tuyệt đối và tương đối là bao nhiêu tại từng mức tải, với độ dao động ra sao?
2. **Ở đâu?** Chi phí xuất hiện ở dispatch, advice, bộ đếm, histogram, trace, log, exporter, GC hay queue?
3. **Khi nào?** Overhead ổn định ở tải thường nhưng có làm điểm bão hòa đến sớm hoặc tăng p99 trong burst không?
4. **Đổi lấy điều gì?** Giá trị quan sát đạt được có tương xứng với tài nguyên, rủi ro, tổn thất telemetry hoặc sai lệch semantics không?

Chỉ thay đổi một nhóm cấu hình mỗi vòng điều tra. Chẳng hạn nếu instrumentation quá tốn kém, thử thu hẹp pointcut, giảm nhãn cardinality, giới hạn attributes và stack trace, điều chỉnh sampling, tổng hợp số đo cục bộ rồi batch export; sau mỗi thay đổi phải đo lại dưới cùng workload. Không tối ưu bằng cách làm mất dữ liệu bắt buộc mà chưa thống nhất chính sách.

## 12. Các lỗi suy luận phổ biến

**“Trong bài đo một thread advice chỉ tốn 50 ns, vậy lên production cũng chỉ tốn 50 ns.”** Không đúng: multi-thread contention, JIT, GC, exporter, I/O và queue có thể thay đổi rất lớn; microbenchmark chỉ trả lời câu hỏi ở cấu hình của nó.

**“Throughput giữ nguyên nên không có overhead.”** Không đúng: khi còn dư CPU, throughput có thể giữ nguyên dù CPU và tail latency tăng; mức dư công suất đã bị bào mòn.

**“Bật asynchronous logging sẽ không ảnh hưởng request.”** Không đúng: enqueue vẫn có chi phí; khi queue đầy có thể block/drop; worker/exporter vẫn dùng tài nguyên chung.

**“Bật tracing 1% thì chi phí chính xác là 1%.”** Không đúng: quyết định sampling, propagation, context và một phần tạo dữ liệu có thể chạy trên mọi request.

**“Bảo đảm 100% log nhưng khi collector chết cứ để queue vô hạn.”** Không đúng: queue không giới hạn đẩy rủi ro sang OOM. Nếu audit không được mất, cần kiến trúc và tài nguyên phù hợp để bảo đảm độ bền, hoặc đưa quyết định xử lý lỗi ra cấp nghiệp vụ.

**“p99 của toàn hệ thống bằng trung bình p99 của các instance.”** Không đúng: percentiles không cộng/trung bình trực tiếp. Cần histogram hoặc thuật toán có hỗ trợ gộp phân phối với cùng quy ước.

**“Bản thử A chạy sáng, B chạy chiều nên B chậm là do advice.”** Chưa đủ bằng chứng: môi trường và profile tải có thể thay đổi. Cần lặp cặp đối chứng, quản lý nhiễu và ghi lại điều kiện.

**“Chỉ cần đo duration do advice báo.”** Không đủ: đồng hồ ngay trong advice thường không bao gồm chi phí dispatch, đo, export, GC hoặc queue ảnh hưởng từ bên ngoài. Đối chiếu số đo của client và hệ thống giúp tránh quan sát chỉ những gì instrumentation chọn ghi.

## 13. Checklist thực hành

- [ ] Pointcut và tập join point đã được xác minh; biết số advice invocation trên một request logic.
- [ ] Baseline/variant có cùng business code, workload và điều kiện tài nguyên.
- [ ] Có warm-up, nhiều lần chạy và đủ thời lượng đo steady state.
- [ ] Load generator không thành nút nghẽn; offered load và achieved throughput được tách biệt.
- [ ] Đã đo p50/p95/p99, throughput, lỗi/timeout, CPU, allocation, GC và queue quan trọng.
- [ ] Đã quan sát mức tải bình thường, tải đỉnh, bão hòa, burst và collector trục trặc.
- [ ] Có phân rã proxy/weaving, counter, histogram, tracing, logging và exporter.
- [ ] Biết giới hạn telemetry buffer, backpressure, sampling, số series và chính sách xử lý khi đầy.
- [ ] Business semantics, exception, retry, cancellation và context còn đúng.
- [ ] Ngưỡng quyết định được viết trước; kết luận nêu kèm biến thiên và giới hạn thí nghiệm.

## 14. Kết luận

**Chi phí quan sát là chi phí thực của hệ thống**, dù được tách vào một aspect hay chạy trên worker nền. Cần kiểm tra nó bằng phép so sánh có đối chứng và tải đại diện, quan sát cả độ trễ đuôi, công suất, CPU, memory, GC, queue, lỗi và khả năng phục hồi khi backend telemetry suy giảm. Microbenchmark giúp hiểu chi phí trên một join point; load test và fault test mới cho biết hiệu ứng tổng thể ở ngưỡng sử dụng thực tế. Chỉ coi việc quan sát là đạt yêu cầu khi **các phép đo chính xác, hành vi nghiệp vụ được giữ nguyên và ngân sách hiệu năng/tài nguyên đáp ứng được yêu cầu vận hành**.