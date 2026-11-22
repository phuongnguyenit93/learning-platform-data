# 15.6 Phân tích execution sample, cây lời gọi và tỷ trọng mẫu trong JFR

## 1. Mục tiêu của phân tích execution sample

Một API có p99 tăng, process CPU cao; trong JDK Mission Control (JMC), bảng Hot Methods hiển thị `parse() 42%`, `hash() 28%` và `serialize() 12%`. Các tỷ lệ này thường được tính từ **số stack samples được quan sát**, không tự động có nghĩa từng hàm tiêu thụ đúng ngần ấy **CPU time của toàn máy** hoặc phần trăm **wall-clock latency** của request.

Bài này giải thích cách dùng `jdk.ExecutionSample` để:

- Xác định phương thức đang thực thi Java code xuất hiện nhiều trong mẫu.
- Dựng **call tree** theo caller→callee, lần theo đường gọi dẫn đến hot method.
- Phân biệt **self/exclusive samples** và **inclusive/total samples**.
- Tính **tỷ trọng mẫu** với mẫu số, phạm vi thời gian và thread filter rõ ràng.
- Nhận ra sampling bias, khoảng thiếu coverage, tác dụng của JIT/inlining, stack depth, native code và blocking.
- Xác nhận giả thuyết bằng số đo CPU/GC/I/O và thử nghiệm trước–sau.

**Nguyên tắc:** execution sampling là ảnh chụp thống kê về *mã Java đang chạy tại thời điểm được lấy mẫu*, không phải đồng hồ đo thời gian thực thi chính xác của từng method call.

## 2. Một `jdk.ExecutionSample` gồm những gì?

Java Flight Recorder (JFR) ghi các event có thời gian và metadata. Với `jdk.ExecutionSample`, những trường thường hữu ích là:

| Trường | Ý nghĩa | Cần tránh nhầm |
| --- | --- | --- |
| `startTime` | Thời điểm một mẫu được thu | Không phải thời điểm bắt đầu lời gọi method |
| `sampledThread` | Thread có stack bị lấy mẫu | Không mặc định đồng nhất với thread quản lý recorder |
| `stackTrace` | Dãy frame phương thức có mặt trên stack | Không phải trace của toàn bộ các lần gọi đã xảy ra |
| `state` | Thread state được event mô tả (tùy phiên bản JDK/viewer) | Không thể từ một state suy ra toàn bộ thời gian blocked/runnable |
| Event count | Số lần quan sát phù hợp bộ lọc | Không phải invocation count, nanoseconds CPU hoặc số request |

Một stack sample có thể giống:

~~~text
(top: đang ở điểm thực thi)
com.example.Tokenizer.scan()
com.example.JsonParser.parse()
com.example.Controller.handle()
com.example.Dispatcher.dispatch()
(bottom: caller gốc)
~~~

Khi dựng cây từ caller tới callee, đọc **từ bottom lên top**:

`Dispatcher.dispatch() → Controller.handle() → JsonParser.parse() → Tokenizer.scan()`.

Mỗi event **đếm một mẫu**. Một phương thức chạy 1 triệu lần nhưng mỗi lần rất ngắn có thể ít xuất hiện; một phương thức chạy liên tục lâu có thể xuất hiện rất nhiều. Số frame của một stack không phải số mẫu mới.

### Phân biệt event liên quan

- **`jdk.ExecutionSample`:** lấy mẫu thread đang thực thi mã Java. Thread đang chờ I/O/monitor/park hoặc đang thực thi native code có thể không hiện trong event này.
- **`jdk.NativeMethodSample`:** event lấy mẫu các thread đang ở native code, có phạm vi và ý nghĩa khác, không biến `ExecutionSample` thành profiler native đầy đủ.
- **`jdk.CPULoad`/`jdk.ThreadCPULoad` và process CPU OS metrics:** cho biết CPU load nhưng không thay cho stack-path analysis.
- **Duration/wait events:** `jdk.SocketRead`, `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, GC-related events giúp điều tra chậm do chờ, lock và pause. Việc bật/threshold ảnh hưởng đến event count.

Các template và bản JDK có thể dùng period khác nhau. `20 ms` hay `10 ms` là **cấu hình yêu cầu lấy mẫu**, không đảm bảo mỗi thread có đúng một event sau từng khoảng ấy. Đừng nhân `sampleCount × 10 ms` để lấy CPU time thật. Với virtual thread, nhiều tác vụ đang unmount chờ I/O có thể hoàn toàn không xuất hiện trong execution samples dù chúng đóng góp lớn vào response latency.

## 3. Cây lời gọi: inclusive khác self như thế nào?

**Top-down call tree** gộp các stack samples có cùng tiền tố đường gọi, từ caller ở đáy stack đến frame đang thực thi. Cách đếm hai cột:

- **Inclusive/total sample count tại node:** số mẫu mà đường gọi đi qua node, gồm các mẫu rơi vào descendant của node.
- **Self/exclusive sample count tại node:** số mẫu rơi tại chính node, không thuộc các descendant được thể hiện. Tưởng tượng frame trên cùng đang nằm ở phương thức node đó.
- **Caller/parent:** phương thức đã gọi node; một method có thể xuất hiện dưới **nhiều caller** và tạo nhiều node trong call tree.

Ví dụ hoàn toàn giả định, sau khi lọc chỉ còn **100 mẫu hợp lệ** của một workload:

~~~text
Worker.run                      100 inclusive,  0 self
├── Api.handle                   70 inclusive,  0 self
│   ├── Parser.decode            45 inclusive, 15 self
│   │   └── Parser.scan           30 inclusive, 30 self
│   └── Validator.verify         25 inclusive, 25 self
└── Batch.handle                 30 inclusive,  5 self
    └── Encoder.encode           25 inclusive, 25 self
~~~

**Cách đọc đúng:**

1. `Api.handle` chiếm **70/100 = 70% inclusive**; điều đó có nghĩa 70 mẫu có call path đi qua API, không phải code riêng của `handle` tự tiêu thụ 70% CPU.
2. `Parser.decode` có **45 inclusive**, gồm **15 self** và **30** ở `Parser.scan`. Nếu chỉ xem hot leaf, `Parser.scan` có 30 mẫu tự thân; nếu xem caller branch, cần nhìn cả `Parser.decode`.
3. `Batch.handle` có **30 inclusive**, gồm **5 self** và **25 self** ở `Encoder.encode`.
4. Tổng self ở các node không chồng nhau bằng **15 + 30 + 25 + 5 + 25 = 100**. **Không cộng inclusive của cha và con**: cùng một mẫu được đếm ở mọi node trên đường stack, nên tổng các số inclusive lớn hơn 100.

Lưu ý: JMC có thể ẩn các frame JDK, nhóm theo package/method, hoặc hiển thị stack bị cắt. Khi cách nhóm thay đổi, self ở một node nhìn trên màn hình có thể đổi theo; luôn xem event stack hoặc lựa chọn aggregation để hiểu mẫu số.

### Top-down, bottom-up, Hot Methods và flame graph

- **Top-down/call tree:** trả lời “đường caller nào dẫn tới vùng code nóng?”. Nếu `HashUtil.hash()` nằm dưới `Api.authenticate()` và `Batch.index()`, hai nhánh cần đánh giá riêng.
- **Bottom-up/Hot Methods:** trả lời “method nào xuất hiện nhiều, các caller nào tạo ra số mẫu đó?”. Gộp cùng method từ nhiều đường gọi rồi mở **predecessors/callers** để truy ngược nguồn.
- **Flame graph:** mỗi stack được gom theo đường gọi; chiều rộng thường tỷ lệ **số mẫu**, không phải thời gian bắt đầu/kết thúc riêng của từng lời gọi. Chiều cao là độ sâu stack, không phải CPU load.

Khi cần tìm code để tối ưu, nhìn **self samples** và method thật đang làm việc. Khi cần xác định business path chịu trách nhiệm, nhìn **inclusive + caller tree**. Cả hai cần lọc đúng time window và các thread liên quan.

## 4. Tính tỷ trọng mẫu với mẫu số hợp lệ

Với tập `S` gồm `N` sự kiện `jdk.ExecutionSample` **được chọn và có stack hợp lệ**:

`selfPct(m) = 100 × selfCount(m) / N`

`inclusivePct(node) = 100 × inclusiveCount(node) / N`

Ví dụ `N=500`; node `Parser.decode` xuất hiện ở 125 stack, nhưng chỉ 40 lần là leaf:

- **Inclusive:** `125 / 500 = 25%`.
- **Self:** `40 / 500 = 8%`.

Nếu GUI đang lọc còn `100` mẫu của riêng một API, phần trăm phải tính theo `N=100`, không so ngang 25% của toàn process với 25% của riêng API. Ghi rõ **event type**, **recording**, **time window**, **thread filter**, **stack availability**, **node/method grouping** và tổng `N`.

Cách phát biểu an toàn là “`Parser.scan` xuất hiện trong **30% execution samples của tập đang chọn**”. Câu “`Parser.scan` sử dụng đúng **30% CPU của hệ thống**” không được phép suy ra chỉ từ dữ liệu này. Tương tự, nếu `parse` chiếm 40% mẫu, tối ưu nó không đảm bảo giảm p99 40%.

### Tại sao tỷ trọng thay đổi mà hiệu năng có thể không đổi?

Tỷ trọng là **tỷ số tương đối**. Giả sử trong hai recording:

| Recording | Mẫu của `parse` | Toàn bộ mẫu được chọn | Tỷ trọng |
| --- | ---: | ---: | ---: |
| Trước | 300 | 750 | 40% |
| Sau | 350 | 1.750 | 20% |

Có thể nhìn 40% → 20% rồi tuyên bố `parse` “nhanh gấp đôi”, nhưng số mẫu còn phụ thuộc thời lượng recording, period, số thread, workload và CPU quota; phần còn lại có thể đã nóng hơn. **Không dùng tỷ trọng để thay thế CPU time/request, throughput, latency và benchmark cùng điều kiện.**

Với tỷ lệ nhỏ từ **8 mẫu** chẳng hạn, 5/8 = 62,5% có thể dao động mạnh giữa hai lần chạy. Các mẫu lấy gần nhau cũng có thể tương quan; không áp dụng sai công thức thống kê coi chúng là những phép thử độc lập tuyệt đối.

## 5. Giới hạn và sai lệch của execution sampling

1. **Tác vụ short-lived:** một method chạy vài microsecond rất nhiều lần có thể xuất hiện ít do xác suất chụp đúng frame thấp; sample count không nói số lần gọi.
2. **Waiting và native code:** `jdk.ExecutionSample` không thể đại diện toàn wall-clock latency khi thread chủ yếu chờ DB, socket, lock, semaphore hoặc chạy native code. Đối chiếu duration events, `NativeMethodSample` và OS/native profiler nếu phù hợp.
3. **Không đều giữa các thread:** period không đồng nghĩa mỗi thread được lấy mẫu với tần suất như nhau. Thread scheduling, sampler behavior, số thread và CPU quota ảnh hưởng xác suất được chọn.
4. **JIT/inlining:** frame interpreted/compiled/inlined/lambda có thể được giải mã/hiển thị khác nhau theo JDK và viewer; không xem tên method là call graph tĩnh luôn đúng.
5. **Stack thiếu/cắt:** stack trace có thể bị hạn chế độ sâu khi **ghi** hoặc chỉ khi **in**, hai giới hạn này khác nhau. Call tree thiếu caller sâu sẽ làm sai bối cảnh.
6. **Lựa chọn khoảng thời gian:** startup/JIT, GC, idle, warm-up và peak traffic có profile khác nhau; chỉ so các cửa sổ tải tương đương.
7. **Thiên lệch trong cách tổng hợp:** filter thread, package, method, loại event và việc loại mẫu stack rỗng làm mẫu số `N` thay đổi. Cần ghi lại bộ lọc khi báo phần trăm.
8. **Suy luận nguyên nhân:** call path nóng là **manh mối**. Nó có thể do helper quá chậm, caller gọi quá thường xuyên hoặc lượng dữ liệu/thuật toán sai. Cần thử nghiệm để phân biệt.

Không nên điều chỉnh period cực nhỏ không giới hạn trên production: volume và chi phí profiling có thể tăng; chọn đủ mẫu cho mục đích điều tra, đo overhead và ưu tiên recording hữu hạn khi có thể.

## 6. Thu recording bằng `jcmd` và đọc bằng `jfr`

Với JDK 17+ có JFR, xác định PID của JVM cần đo và dùng công cụ cùng JDK tương thích:

~~~bash
jcmd <PID> JFR.start name=cpu-probe settings=profile duration=60s filename=cpu-probe.jfr
~~~

Chọn `settings=profile` để có template tập trung vào profiling. Cần **kiểm tra cấu hình thực tế** của `jdk.ExecutionSample` trên bản JDK/template đang dùng, không mặc định period một giá trị bất biến. Sau khi recording hoàn tất và file đã sẵn sàng:

~~~bash
jfr summary cpu-probe.jfr
jfr print --events jdk.ExecutionSample --stack-depth 32 cpu-probe.jfr
~~~

`jfr summary` liệt kê các event type và event count, giúp biết có đủ mẫu để xem không. `jfr print` hiện từng event/stack. `--stack-depth 32` giới hạn số frame **được in ra**; nó không tái tạo frame vốn chưa được ghi. Không dump hàng triệu event ra terminal; mở JMC hoặc dùng parser tuần tự/bộ lọc.

Trong **JDK Mission Control (JMC)**, mở `cpu-probe.jfr` và đi tới màn hình Method Profiling/Hot Methods/Call Tree tương ứng với version của JMC. Cách làm thực tế:

1. Chọn **time window** có CPU/p99 bất thường, loại idle/warm-up nếu đó không phải phạm vi cần phân tích.
2. Chọn **thread scope** và `jdk.ExecutionSample`; xem số event sau filter.
3. Đọc **Hot Methods/self** để tìm nơi đang chạy, rồi mở **call tree/inclusive** để tìm đường gọi chiếm phần lớn mẫu.
4. Chọn một leaf, đi ngược caller: đoạn code hay luồng xử lý nào thường dẫn đến leaf đó?
5. Đối chiếu CPU load, GC, lock/I/O events; không mặc định mọi request chậm đều do CPU.
6. Chọn một tối ưu nhỏ có bằng chứng (giảm parse lặp, batch hợp lý, tránh thừa thao tác), đo lại cùng tải và cùng JFR settings.

Tên view có thể khác theo JMC release. Trong JFR recording, `sampledThread` là đối tượng được lấy mẫu; cần cẩn thận khi thread pool có thể chạy nhiều loại request trên cùng worker.

## 7. Lab Java 17+: tự ghi JFR, đọc mẫu và tính tỷ trọng

Lab này chỉ cần **JDK 17+** (module `jdk.jfr` thuộc JDK), chạy một worker CPU với hai call path chung hàm `busyLoop()`. `apiPath()` tính toán khoảng **2,4 giây**, `batchPath()` tính khoảng **0,8 giây**, sau đó worker ngủ **0,4 giây**. Nó chủ động bật `jdk.ExecutionSample` với requested period **10 ms**, lọc theo `sampledThread`, đếm những stack chứa path A/B và tính phần trăm trong **worker samples có stack**.

**File `ExecutionSampleLab.java`:**

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class ExecutionSampleLab {
    private static volatile long sink;

    private static void busyLoop(long millis) {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(millis);
        long value = 0x9e3779b97f4a7c15L;
        while (System.nanoTime() < deadline) {
            value ^= value << 13;
            value ^= value >>> 7;
            value ^= value << 17;
        }
        sink = value;
    }

    private static void apiPath() {
        busyLoop(2_400);
    }

    private static void batchPath() {
        busyLoop(800);
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("execution-sample-lab.jfr");

        try (Recording recording = new Recording()) {
            recording.enable("jdk.ExecutionSample")
                    .withPeriod(Duration.ofMillis(10))
                    .withStackTrace();
            recording.start();

            Thread worker = new Thread(() -> {
                apiPath();
                batchPath();
                try {
                    Thread.sleep(400);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "jfr-cpu-worker");
            worker.start();
            worker.join();

            recording.stop();
            recording.dump(output);
        }

        long workerSamples = 0;
        long pathA = 0;
        long pathB = 0;

        for (RecordedEvent event : RecordingFile.readAllEvents(output)) {
            if (!event.getEventType().getName()
                    .equals("jdk.ExecutionSample")) {
                continue;
            }
            RecordedThread sampled = event.getThread("sampledThread");
            if (sampled == null ||
                    !"jfr-cpu-worker".equals(sampled.getJavaName())) {
                continue;
            }
            RecordedStackTrace trace = event.getStackTrace();
            if (trace == null || trace.getFrames().isEmpty()) {
                continue;
            }

            boolean hasA = false;
            boolean hasB = false;
            for (RecordedFrame frame : trace.getFrames()) {
                if (frame.getMethod() == null) {
                    continue;
                }
                String method = frame.getMethod().getName();
                if (method.equals("apiPath")) {
                    hasA = true;
                }
                if (method.equals("batchPath")) {
                    hasB = true;
                }
            }

            workerSamples++;
            if (hasA) {
                pathA++;
            }
            if (hasB) {
                pathB++;
            }
        }

        System.out.printf(
                "workerSamples=%d pathA=%d pathB=%d other=%d%n",
                workerSamples, pathA, pathB,
                workerSamples - pathA - pathB);
        if (workerSamples > 0) {
            System.out.printf("A=%.1f%% B=%.1f%%%n",
                    100.0 * pathA / workerSamples,
                    100.0 * pathB / workerSamples);
        }
    }
}
~~~

Chạy từ thư mục chứa file Java:

~~~bash
javac ExecutionSampleLab.java
java ExecutionSampleLab
jfr summary execution-sample-lab.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 execution-sample-lab.jfr
~~~

**Dạng kết quả**, không phải stdout cố định:

~~~text
workerSamples=<N> pathA=<A> pathB=<B> other=<O>
A=<a.a>% B=<b.b>%
~~~

Các biến `N/A/B/O` phụ thuộc môi trường và sampler; nếu `N=0`, chương trình cố ý không in dòng tỷ trọng. Trên một lần chạy JDK 24, ví dụ có thể chỉ được **8 mẫu** cho toàn đoạn CPU hơn 3 giây, nên phần trăm dao động mạnh. Đừng ép đúng **75:25** dù hai pha CPU có thời lượng khoảng 3:1; tăng thời gian test hoặc lặp recording nếu cần mẫu đủ lớn.

**Điểm cần hiểu trong code:**

- `Recording.enable("jdk.ExecutionSample")` và `withPeriod(10 ms)` cấu hình thu mẫu; không phải phép đo tự động CPU time.
- `getThread("sampledThread")` lọc đúng worker; event của thread khác không thuộc mẫu số.
- `getFrames()` chứa stack; kiểm tra sự hiện diện của `apiPath`/`batchPath` trong bất kỳ frame nào tức là đếm **inclusive theo call path**, không phải self samples tại hai method.
- `busyLoop` chung giữa A và B dễ chiếm hot leaf; để tìm bên nào tạo tải, phải xem **caller path** của nó.
- `Thread.sleep(400)` tăng wall-clock thời gian worker nhưng không tương ứng tăng execution samples cho phần chờ. Điều này giúp phân biệt CPU sampling và latency.
- `RecordingFile.readAllEvents` giữ mọi event trong bộ nhớ, thích hợp lab ngắn. Với recording lớn, dùng `RecordingFile` tuần tự hoặc JMC để tránh tải dữ liệu quá lớn.

Để tính **self** tại một method, xác định event có **frame ở đỉnh stack** chính là method đó, sau đó đếm. Khi `busyLoop` là frame đang thực thi và `apiPath` chỉ nằm bên dưới, `apiPath` có inclusive +1 còn self của `apiPath` không tăng. Nếu các frame bị cắt hoặc JIT inlining làm thay đổi cách viewer hiển thị, phải kiểm tra stack trace cụ thể trước khi kết luận.

## 8. Đọc kết quả trong ba tình huống

### A. Hot method lớn vì caller gọi lặp không cần thiết

Hot Methods: `JsonParser.parse` chiếm 38% self samples. Caller tree cho thấy phần lớn các mẫu đến từ một request mapper parse lại payload đã parse ở tầng trước. Hướng tối ưu hợp lý có thể là **xóa parse lặp** hoặc tái sử dụng kết quả đúng phạm vi request, thay vì viết lại parser. Kiểm tra semantics, benchmark và regression test.

### B. Request chậm nhưng không xuất hiện trong CPU samples

Request mất 1,5 giây, phần lớn chờ connection pool hoặc socket; CPU Java thực thi rất ngắn. `jdk.ExecutionSample` có thể không thấy đủ để giải thích p99. Lúc này xem `SocketRead`, `ThreadPark`, pool metrics, DB query tracing, timeout và call path của request. **Ít execution samples không chứng minh request nhanh.**

### C. Một helper dùng ở nhiều luồng xử lý

`HashUtil.hash` chiếm 35% samples của toàn process, nhưng caller tree cho thấy phần lớn đến từ batch indexing, một phần nhỏ từ API xác thực. Nếu mục tiêu là cải thiện API p99, việc tối ưu batch có thể không tác động trực tiếp. Chọn đúng caller, workload và time window, rồi đo lại sau thay đổi.

## 9. Checklist trước khi báo một hot spot

- [ ] Có JDK version, JFR template/period, duration và CPU quota.
- [ ] `jdk.ExecutionSample` được bật; có đủ sample event và phần trăm stack hợp lệ.
- [ ] Đã xác định time window, thread filter, event type và **mẫu số N**.
- [ ] Đã hiểu stack: top là điểm thực thi, bottom là caller; cây top-down đi ngược lại chiều đọc stack.
- [ ] Đã phân biệt **inclusive** (cả subtree) với **self** (vị trí thực thi tại node).
- [ ] Không cộng inclusive của các node cha/con, không xem sample % là CPU time % hay response latency % chính xác.
- [ ] Đã mở callers/bottom-up nếu hot method là helper dùng nhiều nơi.
- [ ] Đã kiểm tra native, blocking, GC/JIT, short-lived methods và thiếu mẫu/truncated stack.
- [ ] Có thử nghiệm cùng tải cho throughput, CPU time/request, p95/p99 và error rate sau tối ưu.

### Nguồn tham khảo

- OpenJDK JEP 328 — Flight Recorder: https://openjdk.org/jeps/328
- Oracle JDK 21 — công cụ `jfr`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — công cụ `jcmd`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK Mission Control — đọc profiling và recordings: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html
- Oracle JFR API — `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html

**Tiêu chí kết luận:** Một hot path được hỗ trợ bởi `jdk.ExecutionSample` là **ứng viên tối ưu dựa trên tỷ trọng mẫu của tập quan sát được**. Chỉ kết luận ảnh hưởng đến CPU, throughput hoặc SLA sau khi đối chiếu với các chỉ số đó và xác nhận bằng phép thử trước/sau.