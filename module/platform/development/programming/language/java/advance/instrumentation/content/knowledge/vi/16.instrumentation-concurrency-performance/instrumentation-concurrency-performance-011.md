# Đánh giá tính đúng đắn bên cạnh thông lượng và phân vị độ trễ

## 1. Vì sao instrumentation nhanh chưa chắc là instrumentation đúng?

Một Java agent được đánh giá chỉ bằng **throughput** (số thao tác mỗi giây) và các phân vị **p50/p95/p99 latency** có thể trông rất tốt nhưng lại âm thầm làm sai hành vi ứng dụng hoặc bỏ mất dữ liệu quan sát.

Ví dụ:

- Một hook tracing bỏ qua 8% sự kiện để giảm overhead. **Throughput tốt lên** nhưng hệ thống không còn đáp ứng hợp đồng *mỗi request hợp lệ phải có một event*.
- Một hook ném `RuntimeException` **sau khi** nghiệp vụ đã ghi dữ liệu. Caller thấy thất bại và retry, nhưng side effect đã xảy ra; có thể xuất hiện thanh toán trùng hoặc bản ghi không nhất quán.
- Một exporter hàng đợi không chặn thread nghiệp vụ nên p99 của request vẫn thấp, nhưng queue đầy làm mất traces. Đo p99 mà không đo dropped events sẽ bỏ qua lỗi.
- Một transformer chèn mã vào cả class helper của chính nó, gây **reentrancy** hoặc class-loading recursion khi tải lớn. Test đơn luồng có thể đúng, còn tải đồng thời làm treo JVM.
- Cài agent làm thay đổi timing, khiến một race condition khó thấy xuất hiện thường xuyên hơn — hoặc ngược lại che mất race do lock tình cờ.

**Kết luận:** hiệu năng chỉ là một trục đánh giá. Instrumentation phải **giữ được hợp đồng nghiệp vụ, tính nhất quán đồng thời và tính đầy đủ/đúng ngữ nghĩa của telemetry**, rồi mới so sánh tốc độ.

Bài nằm trong nhóm **Đồng thời và hiệu năng** của Java instrumentation. Mục tiêu là xây phương pháp kiểm thử kết hợp correctness + throughput + latency distributions, không lẫn “benchmark chạy nhanh” với “behavior đúng”.

### 1.1. Bốn lớp kết quả cần báo cáo riêng

| Lớp đánh giá | Câu hỏi |
|---|---|
| **Business correctness** | Giá trị trả về, exception, side effects, thứ tự và trạng thái có giống hợp đồng trước khi instrument không? |
| **Telemetry correctness** | Số sự kiện, nội dung, correlation IDs, thứ tự, sampling và lỗi exporter có đúng hợp đồng quan sát không? |
| **Concurrency correctness** | Các thao tác đồng thời có giữ atomicity, happens-before, visibility, liveness, không deadlock/livelock, không reentrant recursion không? |
| **Performance** | Throughput, p50/p95/p99/p99.9, error rate, resource consumption, GC và độ trễ khi bão hòa thay đổi ra sao? |

Đánh giá một agent là một **AND condition**: business vẫn đúng **và** telemetry đúng **và** concurrency đúng **và** hiệu năng chấp nhận được. Không dùng một điểm hiệu năng cao để “bù” lỗi dữ liệu.

## 2. Định nghĩa các thước đo trước khi chạy benchmark

### 2.1. Throughput là số gì trên một giây?

Có ít nhất hai cách báo khác nhau:

~~~text
offeredRate    = số request được phát tới hệ thống / thời gian
completedRate  = số request có kết quả hoàn tất / thời gian
successRate    = số request thành công theo hợp đồng / thời gian
~~~

Một agent làm 20% requests thất bại nhanh có thể báo **completed throughput** cao nhưng **successful throughput** thấp. Nếu biểu đồ không phân biệt, dễ đánh giá sai.

Trong demo bên dưới, `throughput` là **attempted completed operations mỗi giây** trên một lượt gồm 1.200 request IDs. Kết quả **bao gồm cả request ném exception**. Giá trị này không đồng nghĩa số giao dịch nghiệp vụ thành công.

Khi tải đồng thời:

- Nếu đưa vào nhiều hơn khả năng xử lý, hàng đợi có thể tăng không giới hạn.
- Nếu client chặn không phát request mới cho đến khi request cũ hoàn tất, tốc độ phát tự giảm khi hệ thống chậm; kết quả latency có thể trông “đẹp” vì bỏ qua những requests lẽ ra phải được phát.
- Nếu requests bị timeout, hủy hoặc reject trước khi được server nhận, phải ghi nhận mẫu số và trạng thái rõ ràng.
- Một throughput cao trong thời gian ngắn không chứng minh có thể duy trì tải đó lâu dài.

### 2.2. p50, p95, p99 nghĩa là gì?

Cho các thời gian quan sát (bao gồm các thao tác được định nghĩa trong tập đo), sắp tăng dần:

~~~text
sorted = sort(latencies)
p50 = giá trị ở xấp xỉ vị trí 50% của phân phối
p95 = giá trị ở xấp xỉ vị trí 95%
p99 = giá trị ở xấp xỉ vị trí 99%
~~~

Ví dụ **minh họa** với 100 thao tác: p99 là vùng gần thao tác chậm nhất. Nó thể hiện “tail” tốt hơn mean, nhưng **không tự chứng minh** không có deadlock hoặc rare pauses.

Các thư viện/thống kê có nhiều định nghĩa nội suy percentile. Demo chọn **nearest-rank**:

~~~text
index(p) = max(0, ceil(p * numberOfSamples) - 1)  // zero-based
percentile(p) = sorted[index(p)]
~~~

Chọn cùng một định nghĩa khi so các run; đừng đối chiếu p99 của hai công cụ có phương pháp lấy mẫu khác nhau mà không ghi rõ.

### 2.3. Cần biết bạn đang đo latency nào

| Loại latency | Bắt đầu / kết thúc | Rủi ro khi diễn giải |
|---|---|---|
| **Service-method latency** | Ngay trước và ngay sau method nghiệp vụ đã instrument | Không bao gồm thời gian request nằm trong hàng đợi trước khi method chạy |
| **Server end-to-end** | Server nhận yêu cầu đến khi trả response | Có thể không bao gồm mạng/client-side queuing |
| **Client observed** | Client phát yêu cầu đến khi nhận response, timeout hoặc failure | Có thể bị ảnh hưởng bởi client, network, retries và connection pool |
| **Exporter/event pipeline latency** | Tạo event đến khi collector lưu/ack | Không đồng nhất với độ trễ của request nghiệp vụ |
| **Class-load/transform latency** | Start → end của `ClassFileTransformer.transform` | Chỉ đo chi phí lúc load/redefine/retransform, không phải chi phí hook trong mỗi invocation |

**Chú ý:** startup agent `premain`, class transformation và per-invocation probe là **ba dạng overhead khác nhau**. Benchmark chỉ đo method calls có thể bỏ qua startup delay, attach/retransform pause hoặc transformer cost. Ngược lại, nếu test chỉ đo class load, không suy ra p99 của nghiệp vụ.

### 2.4. Error rate phải có taxonomy

Không nên đếm mọi “hoàn tất nhanh” thành thành công:

- **Functional error:** giá trị không đúng với oracle.
- **Application exception:** kiểu exception hoặc thời điểm ném khác hợp đồng.
- **Timeout/cancellation:** request không hoàn tất trong deadline.
- **Rejected/backpressure:** không được nhận xử lý, có thể đúng nếu được công bố rõ.
- **Telemetry drop/duplicate:** business vẫn đúng, nhưng số liệu observability sai.
- **Partial commit:** side effect xảy ra nhưng caller nhận lỗi; rất nguy hiểm khi retry.
- **Transformer/install error:** classfile không hợp lệ, verify/load lỗi hoặc thiếu coverage.
- **Liveness failure:** deadlock, livelock, thread starvation hoặc vô hạn chờ.

Có thể đặt một số **quality gates** theo yêu cầu, ví dụ:

~~~text
businessWrongResponses  = 0
businessMissingIDs       = 0
businessDuplicateIDs     = 0
unexpectedExceptions     = 0
unexpectedPartialCommits = 0

telemetryMissingEvents   = 0  // chỉ nếu hợp đồng yêu cầu full coverage
telemetryDuplicateEvents = 0  // chỉ nếu hợp đồng yêu cầu exactly once

throughputSuccess        >= ngưỡng dự án
p99ClientLatency         <= SLO đã phê duyệt
resourceOverhead         <= budget đã phê duyệt
~~~

Đây là **mẫu gate**, không phải một ngưỡng mặc định cho mọi tổ chức. Nếu thiết kế dùng **sampling**, yêu cầu `telemetryMissingEvents=0` trên mọi request là sai; oracle phải so đúng **tập IDs được chọn để sample**, xác suất và giới hạn mất dữ liệu được phép.

## 3. “Tính đúng đắn” của instrumentation gồm những gì?

### 3.1. Bảo toàn hành vi nghiệp vụ

Với cùng input và tiền điều kiện, so trước/sau agent:

1. **Return value:** giá trị, kiểu, metadata và các giá trị ngoại lệ có phù hợp không?
2. **Exception contract:** exception type/cause/ordering có bị hook thay đổi không?
3. **Side effects:** số lần commit, ghi DB, gửi message, cập nhật trạng thái có đúng không?
4. **Idempotency:** retry hoặc timeout có làm tạo side effect trùng không?
5. **Transaction context:** hook có chạy giữa commit và response rồi ném lỗi làm caller hiểu nhầm không?
6. **Resource lifecycle:** streams, locks, connections và files có được đóng ở mọi đường return/throw không?
7. **Security context:** principal, thread context class loader, transaction/tracing context có bị leakage sang request khác không?

Một hook “chỉ để đo” không nên trở thành lý do làm nghiệp vụ thất bại. **Fail-open** là lựa chọn thường thấy cho telemetry không thiết yếu: lỗi quan sát được xử lý riêng, có metric để không mất dấu, và không thay thế exception gốc. Tuy nhiên không bắt tùy tiện mọi `Throwable` ở mọi vị trí: `VirtualMachineError` và các lỗi nghiêm trọng cần chính sách riêng.

### 3.2. Tính đúng của telemetry

Nếu yêu cầu **một event/operation**, có thể kiểm tra:

- Mỗi request ID có event tương ứng, **không thiếu**.
- Không có hai events với cùng logical event ID khi chỉ nên có một.
- Payload có đúng request ID, span/trace ID, timestamp semantics, status, error details và parent relationships.
- Thứ tự trên **một causal chain** hợp lệ, không đòi total order vô lý giữa các threads.
- Event được xác nhận tới sink cuối nếu contract hứa **delivered**, không chỉ “đã đưa vào queue”.
- Khi sampling/drop được phép, metric `dropped` và thực tế quan sát phù hợp policy.
- Privacy/security: không vô tình thu token, mật khẩu, PII hoặc dữ liệu vượt phạm vi cho phép.

Đừng đánh đồng “hook được gọi”, “event đã enqueue” và “event đã được collector lưu”. Chúng là ba mốc khác nhau.

### 3.3. Concurrent correctness

Khi nhiều threads cùng gọi method instrumented, cần thử:

- Data races trong counters hoặc mutable config.
- Không dùng `HashMap`/`ArrayList` không đồng bộ làm shared event sink.
- Không giữ lock nghiệp vụ khi chờ network exporter, tránh deadlock và tail latency.
- Không gọi lại chính phương thức đã instrument từ helper/logging khiến recursion.
- Đúng `ThreadLocal`/trace context ở task handoff, virtual thread hoặc executor thread reuse.
- Không làm mất `InterruptedException`, cancellation flag hoặc deadline.
- Không phá happens-before, visibility và publication khi đổi runtime configuration.
- Không giả định callbacks của nhiều class loaders có thứ tự global cố định.
- Đúng behavior khi collector chậm, queue đầy, CPU saturation hoặc GC pause.

**Lưu ý đặc biệt về `ClassFileTransformer`:** transformer callback dùng trong class load/redefine/retransform không phải request hook. Nếu một transformer ném exception, Javadoc `ClassFileTransformer` cho biết các transformers còn lại vẫn được gọi, và lần load/redefine/retransform vẫn được thử; ném exception ở đây có tác dụng như `return null` đối với transform ấy. Điều đó **khác** với một method hook đã được chèn vào bytecode nghiệp vụ: exception không được xử lý từ hook có thể truyền tới caller và làm thay đổi semantics.

## 4. So sánh đúng: baseline, agent an toàn và các tình huống lỗi

Để chứng minh tính cần thiết của các gates, ta xét bốn chế độ:

| Chế độ | Thay đổi quan sát | Business correctness | Telemetry correctness |
|---|---|---|---|
| `BASELINE` | Không tạo event | Phải đúng | Event không được yêu cầu |
| `SAFE` | Ghi một event cho mỗi request bằng cấu trúc thread-safe | Phải đúng | Đủ event, không trùng |
| `DROP` | Lặng lẽ bỏ mọi ID chia hết cho 13 | Nghiệp vụ vẫn đúng | **Sai** nếu hợp đồng yêu cầu đủ events |
| `THROW` | Hook ném exception với mọi ID chia hết cho 11 **sau commit** | **Sai**: caller thấy lỗi sau side effect | **Sai**: thiếu events của các IDs ấy |

Có thể xảy ra trường hợp throughput của `DROP` hoặc `THROW` cao hơn `SAFE` vì nó **làm ít việc hơn hoặc kết thúc bằng exception sớm**. Đó không phải chiến thắng hiệu năng: một phép so sánh như vậy đã thay đổi loại công việc thành công và vi phạm quality gates.

### 4.1. Các bất biến trong demo

Với `REQUESTS = 1200` và `THREADS = 4`, mỗi worker nhận 300 IDs phân biệt, từ 0 đến 1199:

~~~text
For every id:
    business executes exactly once
    correct response is id + 1

For SAFE:
    one telemetry event per id

For BASELINE:
    no telemetry required

For DROP:
    no telemetry event if id % 13 == 0

For THROW:
    business commits, then hook throws if id % 11 == 0
~~~

Số IDs chia hết cho 13 trong `[0,1199]` là **93**, gồm ID 0. Số IDs chia hết cho 11 là **110**, gồm ID 0. Hai con số này không phụ thuộc scheduler nên là oracle ổn định cho negative tests.

Chúng ta sẽ đo **cả request thành công lẫn request ném exception**; trong `THROW`, 110 operations bị xem là failed dù business side effects của chúng đã xảy ra. Đó là phép thử phát hiện **partial commit**.

## 5. Ví dụ Java 17+ hoàn chỉnh: chạy tải đồng thời và kiểm tra bất biến

### 5.1. Phạm vi thí nghiệm

Ví dụ sau là một Java program **độc lập**, không cần Maven, Java agent JAR hay thư viện ngoài. Phần “instrumentation” được **mô phỏng bằng hook rõ ràng trong `Service.handle`** để tập trung vào đo correctness và latency mà không cần bytecode rewriting.

Trong hệ thống thật, `ClassFileTransformer` hoặc một công cụ instrument khác có thể chèn hook ở cùng vị trí; các bất biến phải kiểm chứng **không đổi**. **Đừng gọi ví dụ này là demonstration of bytecode injection**: nó không đăng ký transformer, không thay classfile, không đo chi phí class-loading callback và không tự tìm GC-root graphs.

Với `ConcurrentHashMap.newKeySet()`, `AtomicIntegerArray`, `AtomicInteger` và `CountDownLatch`, chương trình có thể tái hiện các điều kiện logic đồng thời một cách có kiểm soát. Số liệu throughput và percentiles được in ra nhưng **chỉ phục vụ quan sát cơ chế**, không phải benchmark production đã qua warm-up, fork/isolation và thống kê.

### 5.2. File `InstrumentationQualityDemo.java`

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicIntegerArray;

public final class InstrumentationQualityDemo {
    private static final int THREADS = 4;
    private static final int REQUESTS = 1200;
    private static final int PER_THREAD = REQUESTS / THREADS;

    enum Mode { BASELINE, SAFE, DROP, THROW }

    private static final class Service {
        final Mode mode;
        final AtomicIntegerArray executed = new AtomicIntegerArray(REQUESTS);
        final Set<Integer> events = ConcurrentHashMap.newKeySet();
        final AtomicInteger emissions = new AtomicInteger();

        Service(Mode mode) { this.mode = mode; }

        int handle(int id) {
            // Business operation: one commit per ID.
            executed.incrementAndGet(id);

            // Simulated instrumentation starts after the business commit.
            if (mode == Mode.THROW && id % 11 == 0) {
                throw new IllegalStateException("observer failed");
            }
            if (mode == Mode.SAFE || mode == Mode.THROW
                    || (mode == Mode.DROP && id % 13 != 0)) {
                emissions.incrementAndGet();
                events.add(id);
            }
            return id + 1;
        }
    }

    private static final class WorkerResult {
        final int successes;
        final int errors;
        final int wrongResponses;
        final int errorsAfterCommit;
        final long[] latencies;

        WorkerResult(int successes, int errors, int wrongResponses,
                int errorsAfterCommit, long[] latencies) {
            this.successes = successes;
            this.errors = errors;
            this.wrongResponses = wrongResponses;
            this.errorsAfterCommit = errorsAfterCommit;
            this.latencies = latencies;
        }
    }

    private static WorkerResult processPartition(Service service, int worker,
            CountDownLatch ready, CountDownLatch go) throws InterruptedException {
        ready.countDown();
        go.await();
        int successes = 0, errors = 0, wrong = 0, afterCommit = 0;
        long[] durations = new long[PER_THREAD];

        for (int j = 0; j < PER_THREAD; j++) {
            int id = worker * PER_THREAD + j;
            long began = System.nanoTime();
            try {
                int result = service.handle(id);
                successes++;
                if (result != id + 1) wrong++;
            } catch (RuntimeException ex) {
                errors++;
                if (service.executed.get(id) != 0) afterCommit++;
            } finally {
                durations[j] = Math.max(0L, System.nanoTime() - began);
            }
        }
        return new WorkerResult(successes, errors, wrong, afterCommit, durations);
    }

    private static double percentileMillis(long[] sorted, double p) {
        int index = Math.max(0, (int) Math.ceil(p * sorted.length) - 1);
        return sorted[index] / 1_000_000.0;
    }

    private static void runOnce(Mode mode) throws Exception {
        Service service = new Service(mode);
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        CountDownLatch ready = new CountDownLatch(THREADS);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<WorkerResult>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < THREADS; worker++) {
                final int w = worker;
                futures.add(pool.submit((Callable<WorkerResult>)
                        () -> processPartition(service, w, ready, go)));
            }
            ready.await();
            long wallStart = System.nanoTime();
            go.countDown();

            int successes = 0, errors = 0, wrong = 0, afterCommit = 0;
            long[] latencies = new long[REQUESTS];
            int copied = 0;
            for (Future<WorkerResult> future : futures) {
                WorkerResult r = future.get();
                successes += r.successes;
                errors += r.errors;
                wrong += r.wrongResponses;
                afterCommit += r.errorsAfterCommit;
                System.arraycopy(r.latencies, 0, latencies, copied,
                        r.latencies.length);
                copied += r.latencies.length;
            }
            long elapsedNs = System.nanoTime() - wallStart;

            int missingBusiness = 0, duplicateBusiness = 0;
            for (int id = 0; id < REQUESTS; id++) {
                int times = service.executed.get(id);
                if (times == 0) missingBusiness++;
                if (times > 1) duplicateBusiness += times - 1;
            }

            boolean telemetryRequired = mode != Mode.BASELINE;
            int missingEvents = telemetryRequired
                    ? REQUESTS - service.events.size() : 0;
            int duplicateEvents = service.emissions.get()
                    - service.events.size();
            boolean passed = successes + errors == REQUESTS
                    && errors == 0 && wrong == 0
                    && missingBusiness == 0 && duplicateBusiness == 0
                    && (!telemetryRequired
                        || (missingEvents == 0 && duplicateEvents == 0));

            Arrays.sort(latencies);
            System.out.printf(Locale.ROOT,
                    "%s pass=%s success=%d errors=%d afterCommitErrors=%d"
                    + " missingBusiness=%d duplicateBusiness=%d"
                    + " missingEvents=%d duplicateEvents=%d%n",
                    mode, passed, successes, errors, afterCommit,
                    missingBusiness, duplicateBusiness, missingEvents,
                    duplicateEvents);

            System.out.printf(Locale.ROOT,
                    "%s throughput=%.0f ops/s p50=%.3f ms"
                    + " p95=%.3f ms p99=%.3f ms%n",
                    mode, REQUESTS / (elapsedNs / 1_000_000_000.0),
                    percentileMillis(latencies, 0.50),
                    percentileMillis(latencies, 0.95),
                    percentileMillis(latencies, 0.99));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        for (Mode mode : Mode.values()) {
            runOnce(mode);
        }
    }
}
~~~

### 5.3. Biên dịch và chạy

Mở terminal trong folder có `InstrumentationQualityDemo.java`. Với JDK 17 trở lên:

~~~bash
javac --release 17 InstrumentationQualityDemo.java
java InstrumentationQualityDemo
~~~

Không cần `--enable-preview`, `--add-opens` hoặc JVM agent; các API `java.util.concurrent` và `System.nanoTime()` có trong Java 17. Việc công cụ demo **không yêu cầu agent thật** là deliberate: test harness tập trung vào **behavior của hook sau khi được gọi**, không giả định API tạo transformer.

### 5.4. Kết quả correctness cố định đã kiểm thử

Chương trình đã được biên dịch với `javac --release 17` và chạy thực tế trên JDK 24; bốn dòng **correctness** in ra:

~~~text
BASELINE pass=true success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=0 duplicateEvents=0
SAFE pass=true success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=0 duplicateEvents=0
DROP pass=false success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=93 duplicateEvents=0
THROW pass=false success=1090 errors=110 afterCommitErrors=110 missingBusiness=0 duplicateBusiness=0 missingEvents=110 duplicateEvents=0
~~~

Bên cạnh mỗi dòng trên, chương trình in **một dòng throughput/p50/p95/p99** dạng:

~~~text
BASELINE throughput=<thay đổi theo lần chạy> ops/s p50=<thay đổi> ms p95=<thay đổi> ms p99=<thay đổi> ms
SAFE throughput=<thay đổi theo lần chạy> ops/s p50=<thay đổi> ms p95=<thay đổi> ms p99=<thay đổi> ms
DROP throughput=<thay đổi theo lần chạy> ops/s p50=<thay đổi> ms p95=<thay đổi> ms p99=<thay đổi> ms
THROW throughput=<thay đổi theo lần chạy> ops/s p50=<thay đổi> ms p95=<thay đổi> ms p99=<thay đổi> ms
~~~

**Bốn dòng trên là minh họa định dạng, không phải stdout literal và không phải số benchmark cố định.** Thông lượng, percentiles chịu ảnh hưởng scheduler, CPU, JIT, GC và độ phân giải của timer. Không lấy số từ một lần chạy làm ngưỡng mặc định. Các kết quả correctness được thiết kế xác định bằng số request IDs và điều kiện drop/throw.

### 5.5. Vì sao `DROP` phải fail dù mọi business operations thành công?

`DROP` bỏ event khi `id % 13 == 0`, tức bỏ 93 IDs trên 1.200 IDs. Số business operations vẫn đúng, responses vẫn đúng, không có exception.

Nếu benchmark chỉ báo request throughput hoặc `p99` của `Service.handle`, `DROP` có thể trông bằng hoặc nhanh hơn `SAFE`, nhưng **telemetry contract bị vi phạm**. Kết quả hợp lệ là:

~~~text
businessCorrect = true
telemetryComplete = false
overallPass = false
~~~

Đây là ví dụ của **silent data loss**. Trong production, nếu sampling là có chủ đích, cần kiểm thử với oracle “IDs nào **được yêu cầu** được ghi”, không đòi toàn bộ IDs khi policy chỉ sample 10%.

### 5.6. Vì sao `THROW` nguy hiểm dù business committed đủ 1.200?

`THROW` luôn thực hiện `executed.incrementAndGet(id)` rồi mới chạy hook. Với 110 IDs chia hết cho 11, hook ném `IllegalStateException` **sau commit**:

- `businessMissing=0`: tất cả IDs được thực thi một lần.
- `errors=110`: callers nhận exception từ observer.
- `afterCommitErrors=110`: side effect đã xảy ra trước failure.
- `missingEvents=110`: hook chưa kịp phát event ở các IDs lỗi.
- `overallPass=false` vì không đáp ứng return/exception contract.

Đây là một failure mode rất khó nếu chỉ xem dashboard throughput: caller có thể tự retry do tưởng business request chưa được xử lý. Nếu request không idempotent, retry có thể tạo side effect trùng.

**Điểm phân biệt API:** `THROW` ở đây là exception của **hook trong method nghiệp vụ**. Nó không phải exception ném từ `ClassFileTransformer.transform` trong lúc định nghĩa class; hai nơi có exception-handling contract khác nhau.

### 5.7. Thời gian đo và phạm vi của benchmark nhỏ

- `CountDownLatch ready/go` bảo đảm bốn worker tasks sẵn sàng trước mốc bắt đầu, giảm sai lệch do tạo thread trong lúc đo.
- Mỗi worker xử lý một tập ID rời nhau, có một outcome cho mỗi ID.
- `System.nanoTime()` bao quanh **`Service.handle`**; các phép tính percentile nhận đủ 1.200 mẫu, **bao gồm cả các lời gọi ném exception**.
- Mốc elapsed wall time đo từ release latch đến khi thu tất cả `Future`; throughput ở đây là **completed attempted operations/time**, không phải successful outcomes/time.
- `AtomicIntegerArray` cho phép kiểm tra mọi ID business được thực thi đúng số lần.
- `ConcurrentHashMap.newKeySet` lưu event IDs theo identity value; đây là lưu **logical integer IDs**, không phải heap object identity. `emissions` giúp phát hiện trường hợp có nhiều lần phát cùng một ID mà `Set` sẽ che đi.
- `Arrays.sort` và nearest-rank giúp diễn giải `p50/p95/p99` minh bạch.
- Lớp `Service`/collections/counters **cũng gây overhead**; đây là test harness có chủ đích, không phải phép đo overhead tinh khiết của một Java agent thực.

**Lỗi đo cần tránh:** `p99` của 1.200 lời gọi rất nhanh có độ nhiễu lớn. Một lần chạy thiếu warm-up/forks/repetitions không đủ để kết luận chênh lệch 2–3% có ý nghĩa thống kê. Dùng công cụ và quy trình benchmark phù hợp khi ra quyết định về sản phẩm.

## 6. Khi chuyển bài demo sang agent thật

### 6.1. Kiểm thử ba tầng agent

Một Java agent thường có:

~~~text
Agent startup/attach
       |
       v
ClassFileTransformer.transform(...) 
       |  tạo/copy bytes hợp lệ, trả byte[] hoặc null
       v
Class definition / retransform được JVM chấp nhận
       |
       v
Instrumented business method được gọi
       |
       +--> probe/hook xử lý context và telemetry
       |
       +--> business return/exception/side effects
       v
Async queue / exporter -> collector / backend
~~~

Mỗi tầng có quality gate khác:

1. **Agent installation:** `premain/agentmain` có gọi được? Transformer được đăng ký đúng? `isRetransformClassesSupported`/`isModifiableClass` nếu cần sửa loaded classes?
2. **Bytecode correctness:** bytes hợp lệ, verifier chấp nhận, nhãn/StackMapTable/exception handlers đúng, class loader và modules thấy helper?
3. **Runtime correctness:** methods vẫn cho kết quả đúng, exceptions/locks/context bảo toàn, event đủ và đúng nội dung, exporter hoạt động khi bão hòa.

**Đừng dùng việc `addTransformer` trả về hoặc `transform` được gọi làm bằng chứng tất cả business methods đã được instrument.** Load-time transformer có thể chưa chạm các class đã nạp trước lúc agent attach; cần retransform nếu đủ capability và phạm vi thích hợp.

### 6.2. Kiểm tra đặc biệt với `ClassFileTransformer`

Các bài kiểm thử nên bao gồm:

- Class được load đồng thời trên nhiều thread, nhiều class loaders và named modules.
- Transformer filter chỉ chọn class cần thiết, không recurse vào chính helper/logging package.
- Không sửa input `classfileBuffer` in-place; tạo bản bytes mới nếu thay đổi, trả `null` khi không thay.
- Không chèn hook lặp lại khi retransform nhiều lần (idempotency).
- Không thay đổi return/exception/finally/monitor semantics khi viết lại bytecode.
- Thử class có overload, bridge methods, constructors, synchronized methods, `try/finally`, early return.
- Nếu transform ném exception, log/phân loại lỗi thay vì giả định JVM sẽ chặn class load: đặc tả cho phép tiếp tục với các transformers khác.
- Kiểm tra helper visibility theo loader/module target; `NoClassDefFoundError` sau instrument là correctness failure, bất kể p99 trước đó đẹp.

### 6.3. Thử hook với lifecycle và backpressure

Ở runtime, ngoài synthetic `SAFE`/`DROP`/`THROW`, tạo các tình huống:

| Fault injection | Điều cần xác nhận |
|---|---|
| Collector chậm 10–100 lần | Request vẫn đúng? Queue/sink có backpressure/drop theo policy? |
| Queue chạm giới hạn | Không OOM/unbounded growth; dropped metric chính xác |
| Exporter ném exception | Exception không đổi business contract nếu telemetry là best-effort |
| Event serialization lỗi | Đếm error, không gửi payload rỗng rồi thông báo success |
| Thread bị interrupt | Không mất interrupt/cancellation semantics |
| Sink cần lock đang được nghiệp vụ giữ | Không lock inversion/deadlock |
| Helper tự gọi method đã instrument | Không recursion/reentrancy vô hạn |
| Reload cấu hình lúc có traffic | Config visibility và policy nhất quán |
| Duplicate delivery/retry | Dedupe/idempotency đúng contract |
| Shutdown/redeploy | Flush deadline hợp lý, không giữ class loaders/threads sống vô hạn |

Nếu định nghĩa telemetry là **at-most-once** hoặc **best effort**, đừng kiểm thử “exactly-once delivery” sai hợp đồng. Điều kiện quan trọng là **hợp đồng viết ra trước**, rồi kiểm thử đúng hợp đồng, bao gồm dropped samples khi được phép.

## 7. Thiết kế thí nghiệm công bằng cho throughput và latency

### 7.1. Đưa tất cả biến số vào cùng bảng cấu hình

Một ma trận cơ bản:

| Yếu tố | Ví dụ |
|---|---|
| JVM/JDK | Cùng vendor, version, GC, heap, CPU limits |
| Workload | Cùng request mix, payload sizes, read/write ratio |
| Offered load | 100, 500, 1.000 req/s hoặc mức phù hợp hệ thống |
| Concurrency | 1, 4, 16, 64 in-flight; cùng queue/connection policy |
| Instrumentation | Baseline, agent bật, agent tắt, sampling, export enabled |
| Test phase | Warm-up, steady-state measurement, cooldown |
| Data dependencies | Cùng DB/cache state hoặc fixture được reset |
| Metrics | Success/errors, wrong outputs, p50/p95/p99, throughput, GC/CPU |
| Telemetry | Offered events, emitted, queued, dropped, exported, acknowledged |
| Repetitions | Nhiều run/forks, đảo thứ tự khi phù hợp để giảm bias |

**Đừng chạy baseline 1 lần khi CPU rảnh và agent 1 lần trong giờ tải cao rồi gọi chênh lệch là instrumentation overhead.** Thí nghiệm cần so trong điều kiện tương đương.

### 7.2. Warm-up và JIT ảnh hưởng kết quả

Java có tiered compilation, profiling, class initialization và GC. Chạy vài trăm thao tác đầu có thể đo nhiều chi phí không thuộc steady-state. Ví dụ runnable của bài **cố ý không phải benchmark khoa học**, vì test logic trước rồi quan sát số đo biến thiên.

Với microbenchmark một hook nhỏ, dùng **OpenJDK JMH** để quản lý warm-up, forks, iterations, blackhole/escape-analysis issues. JMH không thay việc kiểm thử concurrency correctness hoặc telemetry completeness.

Với end-to-end test, dùng load generator đo từ bên ngoài với offered-load control và server metrics, warm-up đủ lâu, capture GC/JFR, repeat và quan sát confidence intervals/distributions.

### 7.3. p99 có thể “tốt giả” vì chỉ đo success

Giả sử 1.000 requests:

~~~text
900 thành công nhanh
100 thất bại ngay lập tức do hook

Nếu chỉ báo p99 của 900 successes:
    có thể thấp hơn baseline.

Nếu báo tổng kết đúng:
    failure rate = 10%
    business contract = FAIL
~~~

Tương tự, nếu **timeout** không được ghi thành latency sample hoặc các requests nằm trong queue nhưng chưa được nhận, tail có thể bị ẩn. Cần tách metrics theo **attempted**, **succeeded**, **failed**, **timed-out** và **dropped/rejected**, đồng thời giải thích tập mẫu dùng cho percentile.

### 7.4. Coordinated omission

Một load generator kiểu closed loop thường chờ response rồi mới gửi tiếp. Khi server pause 1 giây, nó không phát các requests mới trong 1 giây đó. Nếu tính latency chỉ trên requests thực sự đã phát, nhiều delayed requests “lẽ ra tới” bị thiếu. Đây là dạng **coordinated omission**.

Muốn đo SLO theo một offered rate cố định, cần:

- Ghi **scheduled/request creation time** hoặc mô hình open-loop phù hợp với mục tiêu.
- Tách queue waiting khỏi service time.
- Đưa timeouts, rejections, missed scheduled requests vào báo cáo, không che mất.
- Dùng histogram/profiler có phương pháp accounting rõ ràng; một số thư viện như HdrHistogram hỗ trợ correction dựa trên expected sampling interval, nhưng phải hiểu giả định.

Một `p99` thấp từ client tự ngừng phát khi backend chậm không chứng minh trải nghiệm người dùng tốt.

### 7.5. Kiểm tra độ chính xác của phép đo

- Đo theo `System.nanoTime` cho elapsed duration thay vì `currentTimeMillis`; wall-clock có thể bị điều chỉnh bởi hệ thống.
- Timer có overhead, đặc biệt với method microsecond/nanosecond; đo/tách overhead khi cần.
- Percentiles cần đủ số samples: p99.9 không ổn định khi chỉ có vài trăm thao tác.
- Nếu dùng histogram buckets, thông tin tail phụ thuộc độ phân giải/bucket boundaries.
- GC, safepoints, CPU throttling và scheduling ảnh hưởng tail, cần log nguồn gây nhiễu.
- Khi nhiều threads cập nhật global histogram, contention của chính metric có thể làm chậm app; cân nhắc per-thread buffers/aggregation với giới hạn bộ nhớ.
- Độ trễ của exporter async không được giấu bằng cách chỉ đo enqueue; cần có metric delivered/ack latency nếu contract đòi.

## 8. Dùng phép thử đúng đắn trước, sau đó mới ra quyết định hiệu năng

Một quyết định có thể theo quy trình:

~~~text
A. Chạy functional oracle và concurrency stress
       |
       +-- bất kỳ business invariant bị phá? --> REJECT
       |
       +-- telemetry completeness/contract sai? --> REJECT
       |
       +-- deadlock, starvation, leak, recursion? --> REJECT
       |
       v
B. Chạy benchmark có warm-up + repeated runs
       |
       +-- throughput success dưới SLO? --> REJECT/OPTIMIZE
       |
       +-- p95/p99/p99.9 vượt SLO? --> REJECT/OPTIMIZE
       |
       +-- CPU, GC, allocations, native memory vượt budget? --> REJECT/OPTIMIZE
       |
       v
C. Chạy fault injection + deploy/rollback test
       |
       +-- kết quả vẫn đáp ứng contract? --> ACCEPT
       +-- không đáp ứng?               --> REJECT/REDESIGN
~~~

**Bước A không chỉ chạy một lần single-thread.** Nó bao gồm stress nhiều threads, property-based tests và fault injection cho các đường exception, queue full, collector down, retransformation và shutdown khi có traffic.

### 8.1. Ngưỡng “đạt” phụ thuộc hợp đồng

Ví dụ một service quan trọng có thể quy định:

~~~text
Bắt buộc:
- wrong outputs = 0
- duplicate side effects = 0
- unexpected exceptions = 0
- required telemetry events missing = 0 (nếu full coverage)
- no deadlocks / leaked executor threads

Performance budget:
- p99 end-to-end latency tăng không quá X%
- successful throughput giảm không quá Y%
- CPU overhead tăng không quá Z%
- exporter queue bounded, drops trong quota nếu sampling
~~~

Các chữ `X/Y/Z` ở đây là **biến biểu diễn budget dự án**, **không phải số ngưỡng do Java/JVM quy định**. Trong bài thực tế, thay bằng SLO có chủ sở hữu, điều kiện tải và phương pháp thu thập rõ.

## 9. Một số anti-pattern của instrumentation benchmark

### 9.1. Chỉ đo throughput, không kiểm tra output

Một hook bỏ việc hoặc trả sớm có thể cải thiện throughput nhưng làm sai nghiệp vụ. Luôn cần correctness oracle (return/exception/side effects) và telemetry oracle riêng.

### 9.2. Chỉ xem p99 trên request thành công

Nếu hook làm request lỗi nhanh, phân vị của các successes còn lại có thể đẹp hơn. Báo error rate, partial commits, timeouts và latencies của failures theo cohort.

### 9.3. Cộng toàn bộ event count rồi kết luận “đủ”

Giả sử cần event cho IDs 1..100, nhưng có ID 7 bị gửi hai lần và ID 8 không được gửi. Tổng count vẫn 100, nhưng đúng nghĩa **mất một event và trùng một event**. Cần theo dõi per-ID coverage và uniqueness.

### 9.4. Dùng `HashMap` không thread-safe làm sink chung

Dưới concurrency, shared non-thread-safe map/list có thể gây loss, corruption hoặc exceptions. Chọn cấu trúc/concurrency policy phù hợp và test trên tải thực. Cũng chú ý `ConcurrentHashMap` không làm nhiều bước check-then-act tự động atomic nếu không dùng atomic operations đúng.

### 9.5. Log từ bên trong chính logging hook

Nếu hook gọi một method lại được instrument, có thể sinh recursion, stack overflow hoặc deadlock. Cần ignore packages/helpers và guard reentrancy theo đúng yêu cầu.

### 9.6. Benchmark chỉ một lần, không warm-up

Kết quả có thể phản ánh class initialization, JIT compilation, GC hoặc khác biệt tải máy. Không dùng một số p99 của benchmark tí hon để quyết định phát hành.

### 9.7. Không đo queue/exporter

Một agent async có thể làm request nhanh nhưng queue tăng mãi rồi mất dữ liệu hoặc OOM. Cần đo backlog, enqueue/reject, drop, flush, export errors và acknowledged delivery.

### 9.8. Không xem active frames và class transformation boundaries

Sau retransform/redefine, các active frames có thể tiếp tục dùng bytecode cũ; khi compare ngay sau rollout, chú ý thời điểm hook có hiệu lực. Class loaded trước khi attach có thể chưa được transform nếu chỉ mới gọi `addTransformer`.

### 9.9. Đếm sampling drop như corruption mà không hiểu policy

Nếu hợp đồng cho phép sampling 10%, việc 90% events không có là **policy**, không phải tự động là bug. Nhưng cần xác minh policy đúng, không bias theo request error/latency và metadata/loss metrics rõ ràng.

### 9.10. “Một lần không thấy deadlock” nghĩa là deadlock-free

Deadlock có thể cần scheduling hiếm. Test stress, fault injection và thread-dump watchdog; nếu có khả năng, dùng các công cụ race/lock analysis thích hợp. Không hứa chứng minh hình thức chỉ bằng một stress test.

## 10. Checklist thực nghiệm

### 10.1. Trước khi chạy

- [ ] Ghi rõ business return/exception/side effects contract.
- [ ] Ghi rõ telemetry contract: 1:1, sampled, at-most-once hay best effort.
- [ ] Định nghĩa độ trễ nào được đo: client/server/method/exporter.
- [ ] Phân biệt offered requests, completed attempts và successful outcomes.
- [ ] Chọn cùng workload, JVM/JDK, GC, heap, CPU quotas và backend fixtures.
- [ ] Chọn mức concurrency và offered load, không chỉ số threads.
- [ ] Thiết kế oracle per request ID, duplicate/missing, payload và status.
- [ ] Lên fault scenarios: exporter timeout, queue full, reentrant hooks, shutdown.

### 10.2. Trong khi chạy

- [ ] Đếm mọi request ID: submitted, completed, failed, timed out, rejected.
- [ ] Kiểm tra payload, return values, exception classes và side effects.
- [ ] Không chỉ so total event count: đối chiếu per-ID coverage.
- [ ] Thu p50/p95/p99 trên tập samples đã định nghĩa rõ, kể cả failures nếu phù hợp.
- [ ] Thu CPU, allocations, GC, thread contention, queue backlog và memory.
- [ ] Nếu sampling có chủ đích, dùng expected sampled IDs/rates để làm oracle.
- [ ] Lưu version của Java agent, transformer config và target classloader.
- [ ] Tránh logging/metrics của harness làm sai lệch chính workload.
- [ ] Ghi nhận timeout/deadlock bằng watchdog, không để test treo vô hạn.

### 10.3. Sau khi chạy

- [ ] Business invariants đều đạt?
- [ ] Telemetry invariants đều đạt theo contract?
- [ ] Liveness và data races đã được stress đủ sâu?
- [ ] Có đủ warm-up/repeat/fork để tin vào chênh lệch hiệu năng?
- [ ] Offered rate/queueing/coordinated omission được xét?
- [ ] Có so baseline và agent dưới cùng điều kiện?
- [ ] Đã tách throughput completions và throughput successes?
- [ ] Đã xác minh config reload, attach/retransform và rollback?
- [ ] Báo rõ giới hạn của benchmark: workload nhỏ, chỉ một host, không có collector, chưa đo network?

## 11. Tự đánh giá kiến thức

**1.** Vì sao `DROP` trong demo có thể đạt throughput cao nhưng `pass=false`?

> Vì nó bỏ 93 telemetry events trái hợp đồng full coverage. Nghiệp vụ vẫn đúng nhưng telemetry sai; performance không bù được correctness failure.

**2.** Trong `THROW`, `businessMissing=0` nhưng `errors=110`; ý nghĩa là gì?

> Business operations đã ghi nhận side effect, nhưng hook ném exception sau đó khiến 110 callers thấy failure. Đây là partial commit và có rủi ro retry trùng.

**3.** p99 thấp có chứng minh không xảy ra data loss không?

> Không. p99 chỉ mô tả distribution của những latencies được đo, không kiểm tra event identity/coverage hoặc content.

**4.** Tại sao không chỉ đếm tổng events?

> Duplicate một ID và missing một ID có thể làm tổng không đổi. Cần so từng logical ID và uniqueness.

**5.** Vì sao cần phân biệt completed throughput và successful throughput?

> Một chương trình có thể hoàn tất nhanh bằng cách trả lỗi nhanh. Chỉ successful throughput mới phản ánh capacity phục vụ request thành công theo contract.

**6.** `System.nanoTime` bao quanh `Service.handle` có đo thời gian request chờ trong queue không?

> Không. Đây là method latency từ khi worker bắt đầu gọi. Client end-to-end latency và queue waiting là phạm vi khác.

**7.** `ClassFileTransformer.transform` ném exception có giống exception từ hook đã chèn vào method không?

> Không. Javadoc cho phép transformer pipeline tiếp tục khi callback transform ném lỗi; exception từ hook thực thi nghiệp vụ có thể truyền tới caller và đổi hành vi nếu không xử lý đúng.

**8.** “Safe” trong demo có chứng minh agent production an toàn chưa?

> Chưa. Demo chỉ kiểm tra một mô hình nhỏ, không có bytecode rewrite, exporter, GC/JFR impact, module/classloader complexity, shutdown/race/deadlock fault paths.

**9.** Trong hệ thống có sampling 10%, oracle telemetry nên yêu cầu event cho tất cả IDs không?

> Không, trừ khi hợp đồng yêu cầu full capture. Cần xác minh đúng tập sample được chọn, tỷ lệ và drop policy, không áp dụng gate sai.

**10.** Tại sao benchmark nhỏ thiếu warm-up không thích hợp để quyết định overhead 2%?

> JIT compilation, GC, scheduler, cache warm-up và timer overhead có thể lớn so với chênh lệch; cần repeated runs/forks và phân tích distribution.

**11.** Coordinated omission là gì?

> Khi hệ thống chậm làm load generator ngừng/phát ít requests hơn, các requests lẽ ra xuất hiện trong khoảng chậm bị bỏ khỏi mẫu latency, khiến tail trông thấp hơn trải nghiệm theo offered load.

**12.** Instrumentation đo thành công nhưng telemetry exporter chưa gửi được tới collector: đã “delivered” chưa?

> Chưa. Hook invoked/enqueued/export acknowledged là các mốc khác nhau; status phải theo hợp đồng delivery thực sự.

**13.** Nếu Java agent dùng transformer và chỉ gọi `addTransformer` sau attach, class đã load có tự được instrument không?

> Không. Đăng ký không làm tự replay loaded classes; nếu cần xử lý class cũ, phải dùng cơ chế retransform/redefine phù hợp với capability/target.

**14.** Khi throughput/p99 của `DROP` tốt hơn `SAFE`, quyết định đúng là gì?

> Không coi DROP là thắng nếu full telemetry là yêu cầu. Cần sửa data loss trước, sau đó benchmark cấu hình đúng hợp đồng.

## 12. Nguồn tham khảo

- Java SE 17 — `java.lang.instrument.Instrumentation`: `addTransformer`, `retransformClasses`, agent runtime lifecycle: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17 — `ClassFileTransformer`: callback lúc load/redefine/retransform, exception semantics, `return null` và byte array constraints: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17 — `java.util.concurrent`: `CountDownLatch`, `ExecutorService`, `Future`, `ConcurrentHashMap`, `AtomicIntegerArray`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17 — `System.nanoTime()`: elapsed-time measurements: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
- HdrHistogram — histogram recording và coordinated omission correction concept: https://hdrhistogram.github.io/HdrHistogram/JavaDoc/
