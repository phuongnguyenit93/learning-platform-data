# Đo thời gian sẵn sàng và dung lượng bộ nhớ để đánh giá lợi ích khởi động

## 1. Khởi động nhanh là cải thiện điều gì?

Tối ưu khởi động Java không đơn giản là làm cho dòng `public static void main` được thực hiện sớm hơn vài mili-giây. Một dịch vụ có thể in “Started” nhưng chưa mở cổng, đã mở cổng nhưng chưa nạp cấu hình, hoặc nhận kết nối mà chưa phục vụ thành công yêu cầu thực tế. Tương tự, giảm heap used không nhất thiết giảm **RAM thực** hoặc giới hạn bộ nhớ cần cấp cho container.

Để đánh giá lợi ích khởi động của một ứng dụng Java 17, cần trả lời ít nhất ba câu hỏi:

1. **Bao lâu ứng dụng thật sự sẵn sàng phục vụ?** Đo từ một mốc bên ngoài JVM đến **readiness condition** có ý nghĩa nghiệp vụ, không chỉ đến dòng log tùy ý.
2. **Ứng dụng sử dụng bao nhiêu bộ nhớ tại thời điểm đó và sau khi ổn định?** Phân biệt **heap used**, **heap committed**, **non-heap/metaspace**, **native memory**, **RSS**, giới hạn cgroup và peak.
3. **Đổi lấy gì?** Startup nhanh hơn có thể khiến steady-state throughput giảm, GC nhiều hơn, RSS tăng, container dễ bị OOMKilled hoặc first-request latency xấu đi.

Bài này tập trung **đo đạc và đánh giá bằng thực nghiệm** cho HotSpot/OpenJDK Java 17: định nghĩa điểm sẵn sàng, tạo baseline, chạy lặp nhiều process, thu thập chỉ số thời gian và bộ nhớ, so sánh có kiểm soát, tìm nguồn sai lệch và đưa ra quyết định dựa trên mục tiêu triển khai. Các ví dụ độc lập dùng **Java 17**, công cụ JDK `java`, `javac`, `jcmd`, `jstat` và công cụ hệ điều hành khi cần.

**Phân biệt:** Java SE bảo đảm hành vi Java ở cấp ngôn ngữ/JVM, không tiêu chuẩn hóa một chỉ số “startup time” thống nhất cho mọi ứng dụng. Những options như CDS, compiler tier, GC và Native Memory Tracking là **cơ chế phụ thuộc bản JVM/JDK**. Các con số thời gian/RSS giả định dùng trong ví dụ được dán nhãn rõ, không giả là dữ liệu đã đo.

## 2. Các mốc thời gian: process started khác application ready

Một timeline hữu ích:

```text
T0             T1                 T2                  T3                T4
|--------------|------------------|-------------------|-----------------|
Launcher       JVM initialized    Framework/app       Socket opened     Endpoint /ready
process begins                    initialization                        returns success
                                                                        + dependencies OK

T5: yêu cầu nghiệp vụ đầu tiên thật sự hoàn tất thành công
T6: throughput/latency sau warm-up đạt điều kiện steady state

T0→T4: startup to readiness (mục tiêu vận hành thường quan trọng)
T0→T5: first-successful-request latency
T4→T6: thời gian làm nóng sau ready, nếu có
```

Các mốc là mô hình; quá trình thật có thể khác thứ tự hoặc chạy song song một phần.

Những điểm kết thúc thường bị trộn:

- **Process created:** hệ điều hành tạo Java process; chưa chứng minh JVM/app sẵn sàng.
- **`main` entered:** JVM đã tải/khởi tạo các lớp cần để gọi `main`; nhiều framework/dependency chưa hoàn tất.
- **Application init complete:** một callback/framework event báo hoàn tất; có thể chưa bảo đảm dependencies hoặc endpoint thực tế đáp ứng.
- **Port bound/listening:** hệ điều hành nhận socket; handler nghiệp vụ vẫn có thể trả 503.
- **Readiness endpoint trả 200:** tốt hơn nếu endpoint kiểm tra đúng điều kiện cần nhận traffic.
- **First business request succeeds:** đo đường end-to-end mà người dùng thật thấy, có thể bao gồm lazy initialization, JIT warm-up, connection establishment.
- **Steady-state throughput/latency:** đo một tính chất khác hẳn startup, không được lấy thay cho readiness.

**Lựa chọn định nghĩa phải phục vụ yêu cầu:** với HTTP service, “sẵn sàng” thường là endpoint health/readiness trả success theo tiêu chí áp dụng trước khi load balancer bắt đầu chuyển traffic. Với CLI tool, mốc hợp lý có thể là **ra kết quả đúng và exit**. Với batch worker, mốc ready có thể là **đã kết nối queue và sẵn sàng nhận job**, không phải lệnh `main` return.

## 3. Cần một điểm bắt đầu đo ở ngoài JVM

Để tính **process-start-to-ready**, công cụ đo phải lấy timestamp gần lúc **khởi tạo process**. Nếu đặt:

```java
long started = System.nanoTime(); // đầu main
initialize();
long elapsed = System.nanoTime() - started;
```

thì bạn chỉ đo **main-to-init**, bỏ qua:

- OS process launch và Java launcher.
- JVM runtime setup và các native libraries cần trước `main`.
- Class loading/initialization xảy ra trước điểm đánh dấu.
- Một số startup hooks, agents và premain logic.
- Chênh lệch thời gian cho subprocess startup của môi trường.

Mốc trong `main` vẫn hữu ích để **chia nhỏ giai đoạn**, nhưng không nên đặt tên nó là **total process startup time**. Để đo tổng, cần một harness ngoài process gọi Java và nhận tín hiệu readiness.

### `System.nanoTime()` và `currentTimeMillis()`

- `System.nanoTime()` được thiết kế đo khoảng thời gian trôi qua bằng hiệu giữa hai lần gọi **trong phạm vi phù hợp**; không được dùng giá trị tuyệt đối làm Unix epoch.
- `System.currentTimeMillis()` phản ánh wall clock thời gian lịch, có thể bị chỉnh theo đồng hồ hệ thống; không phải lựa chọn tốt nhất để đo duration ngắn.
- **Không trừ hai giá trị `nanoTime` lấy từ hai Java processes độc lập** rồi giả định chúng có cùng điểm gốc; mỗi process/runtime/OS có thể có origin riêng.
- Harness nên tự dùng monotonic clock của mình cho T0→ready, ví dụ Python `time.monotonic_ns()` hoặc clock tương ứng của hệ điều hành.

Một **log timestamp** giúp phân tích timeline, nhưng một dòng có timestamp trễ do buffered logging chưa chắc phản ánh chính xác thời điểm endpoint có thể phục vụ.

## 4. Readiness contract phải được viết trước khi benchmark

Một readiness endpoint chỉ đúng khi nó phản ánh khả năng phục vụ traffic theo kiến trúc:

- Server đã bắt đầu nhận requests.
- Các cấu hình, certificates và resource pools cần thiết đã có.
- Những dependencies **bắt buộc để phục vụ phần lớn requests** đã được khởi tạo/kiểm tra theo timeout phù hợp.
- Nếu có database, queue hoặc remote APIs, xác định rõ **khi nào chúng cần thiết cho readiness** và chính sách degraded mode.
- Worker chưa bị đánh dấu shutting down.
- Nếu app sử dụng lazy initialization, định nghĩa ready có chấp nhận **first-request penalty** không; nếu không, phải warm đúng path trước ready.

**Liveness** và **readiness** khác nhau:

- **`/live`:** tiến trình còn khả năng hoạt động; một database outage không nhất thiết làm liveness thất bại hoặc buộc restart loop.
- **`/ready`:** hệ thống có nên gửi requests nghiệp vụ vào instance **ngay lúc này** hay không.
- **`/startup`:** một số nền tảng orchestration hỗ trợ startup probe để ứng dụng có thêm thời gian khởi động trước khi bị restart bởi liveness; contract phụ thuộc nền tảng.

Dùng một endpoint trả 200 ngay khi Java HTTP server accept requests là **tín hiệu transport**, không đủ đại diện cho một ứng dụng thực tế nếu database/cache/schema vẫn chưa sẵn sàng.

## 5. Java 17: một server có readiness endpoint để thực hành đo

Tạo file **`StartupReadyServer.java`**. Demo dùng module `jdk.httpserver` có sẵn trong nhiều phân phối **full JDK 17**, không cần thư viện HTTP ngoài:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class StartupReadyServer {
    private static volatile boolean ready;
    private static volatile long checksum;

    private static void reply(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(code, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        long mainStart = System.nanoTime();
        int port = args.length == 0 ? 18080 : Integer.parseInt(args[0]);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/live",
                e -> reply(e, 200, "alive\n"));
        server.createContext("/ready", e -> {
            if (ready) {
                reply(e, 200, "ready\n");
            } else {
                reply(e, 503, "not-ready\n");
            }
        });
        server.createContext("/work", e -> {
            if (!ready) {
                reply(e, 503, "not-ready\n");
            } else {
                reply(e, 200, "checksum=" + checksum + "\n");
            }
        });
        server.setExecutor(Executors.newFixedThreadPool(2));

        long result = 0;
        for (int i = 0; i < 10_000; i++) {
            result += i % 10;
        }
        checksum = result;

        server.start();
        ready = true;
        long elapsedMs = (System.nanoTime() - mainStart) / 1_000_000;
        System.out.println("READY port=" + port);
        System.out.println("mainToReadyMs=" + elapsedMs);
    }
}
```

Biên dịch và khởi động bằng **JDK 17**:

```bash
javac --release 17 --add-modules jdk.httpserver StartupReadyServer.java
java --add-modules jdk.httpserver StartupReadyServer 18080
```

Trong **terminal khác** khi server còn chạy:

```bash
curl -i http://127.0.0.1:18080/live
curl -i http://127.0.0.1:18080/ready
curl -i http://127.0.0.1:18080/work
```

Sau khi đã sẵn sàng, phần **body** lần lượt là:

```text
alive
ready
checksum=45000
```

Còn dòng `mainToReadyMs=...` chứa **số đo động**, không có expected time cố định. Lệnh `curl -i` còn in status code và headers, cũng thay đổi theo HTTP server/runtime. Demo không có cơ chế tự shutdown: dùng **Ctrl+C** sau khi kết thúc đo. Cổng 18080 phải trống; nếu bận thì chọn cổng khác ở cả lệnh Java và lệnh curl.

### Vì sao readiness trong demo là tín hiệu tốt hơn “main đã chạy”?

- `/ready` trả **503** trước khi flag `ready` chuyển true.
- `server.start()` đã được gọi trước khi cho ready.
- Dữ liệu nghiệp vụ đơn giản (`checksum`) được chuẩn bị trước ready.
- Request `/work` trả result có thể kiểm tra được, không chỉ xác nhận socket mở.

Đây vẫn chỉ là **mô hình nhỏ**: một dịch vụ thật có thể cần DB migrations, external dependencies, certificate loading, JIT warm-up hoặc queue subscription trước khi readiness hợp lệ. Trong demo, `ready=true` có thể xảy ra trước khi client poll thực sự kết nối được; vì vậy mốc tốt để harness đo là **lần response 200 đầu tiên từ endpoint**.

## 6. Hai điểm thời gian đo trong demo có ý nghĩa khác nhau

| Metric | Bắt đầu | Kết thúc | Bao gồm |
| --- | --- | --- | --- |
| `mainToReadyMs` | Đầu `main` | Sau `server.start()` và `ready=true` | Chỉ initialization bên trong `main` từ mốc đánh dấu |
| `processToReadyMs` | Trước khi harness tạo subprocess | Poll HTTP `/ready` lần đầu 200 | Launcher, JVM startup, app init, HTTP accept, poll overhead |
| `processToWorkMs` | Trước subprocess | HTTP `/work` trả đúng result | Đường đầu tiên của một request nghiệp vụ |
| `readyToWarmMs` | Ready HTTP 200 | Đạt điều kiện throughput/latency warm đã định nghĩa | Lazy init, JIT, caches sau ready |
| `coldStartToFirstByte` | Trước subprocess hoặc lúc request kích hoạt start | Client nhận first response byte | Có thể gồm orchestration/router/network và request processing |

**Không cộng các durations tùy ý** nếu chúng đã chứa nhau. Ví dụ `processToWorkMs` có thể bao gồm `processToReadyMs` nếu harness kiểm tra readiness trước, nhưng không nhất thiết nếu request đi theo một đường khác.

### Poll interval làm sai số thời gian ready

Nếu harness kiểm tra mỗi 100 ms, app có thể thực sự ready giữa hai probes. Thời điểm ghi nhận 200 đầu tiên sẽ **muộn hơn** thời điểm sẵn sàng thật trong một khoảng phụ thuộc polling/scheduling/network. Để so các biến thể, dùng **cùng probe interval**, endpoint và timeout, rồi ghi độ phân giải/overhead của cách đo.

## 7. Ví dụ harness ngoài JVM: đo process-to-readiness nhiều lần

Ví dụ dưới đây dùng **Python 3 standard library** để launch Java 17 riêng cho mỗi trial và đo thời gian bằng monotonic clock. Python là **công cụ đo ngoài JVM**, không phải source Java SE. Tạo file **`measure_ready.py`** cùng thư mục chứa `StartupReadyServer.class`:

```python
import statistics
import subprocess
import time
import urllib.error
import urllib.request

JAVA_CMD = [
    "java",
    "--add-modules", "jdk.httpserver",
    "StartupReadyServer",
    "18080",
]
URL = "http://127.0.0.1:18080/ready"
RUNS = 5
TIMEOUT_S = 30

def one_run():
    started = time.monotonic_ns()
    proc = subprocess.Popen(
        JAVA_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ready_ms = None
    try:
        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    "JVM exited before readiness; inspect app logs"
                )
            try:
                with urllib.request.urlopen(URL, timeout=0.2) as response:
                    if response.status == 200 and response.read() == b"ready\n":
                        ready_ms = (time.monotonic_ns() - started) / 1e6
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(0.02)
        if ready_ms is None:
            raise TimeoutError("Application did not become ready")
        return ready_ms
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

samples = [one_run() for _ in range(RUNS)]
print("runs=", RUNS)
print("medianReadyMs=", round(statistics.median(samples), 2))
print("minReadyMs=", round(min(samples), 2))
print("maxReadyMs=", round(max(samples), 2))
```

**Lệnh:**

```bash
javac --release 17 --add-modules jdk.httpserver StartupReadyServer.java
python3 measure_ready.py
```

Các số `medianReadyMs`/`minReadyMs`/`maxReadyMs` là **số đo phải lấy trên máy thực**, không có stdout số thời gian dự đoán. `RUNS=5` chỉ phù hợp **bài tập minh họa**; benchmark báo cáo đáng tin thường cần nhiều trials hơn, phân bổ thứ tự variants và có tiêu chí dừng/độ tin cậy.

**Chú ý giới hạn của harness mẫu:**

- Dùng cổng cố định 18080: không chạy song song với server khác trên cùng cổng.
- Mỗi trial giết process cũ trước khi launch trial tiếp; không thay port khi server chưa tắt.
- Poll interval ~20 ms cộng chi phí connection/read tạo độ phân giải và sai số.
- Không ghi stderr/stdout để giảm ảnh hưởng log, nên khi startup fail hãy chạy Java thủ công để xem lỗi.
- Không gồm network/orchestrator khi thực tế triển khai ở Kubernetes/cloud khác máy client.
- OS file page cache/JIT shared archive có thể **warm** sau trial đầu; kết quả không nhất thiết là **cold boot từ đĩa**.
- Script tạo process riêng mỗi trial nhưng không xóa OS cache, DNS cache, shared filesystem cache hay thay đổi CPU frequency.
- Nếu process cũ còn giữ cổng hoặc bị kill chưa sạch, trial có thể fail.
- `Popen` tương ứng thời điểm harness yêu cầu process, không phải timestamp chính xác nanosecond mà kernel đầu tiên thực hiện Java instructions.

Không dùng script này để tuyên bố benchmark production đủ chuẩn; nó là **bộ khung đo được, có đúng mốc readiness**, có thể mở rộng logging và statistics.

## 8. Định nghĩa cold start và warm start theo môi trường

Một ứng dụng Java có nhiều mức “lạnh”:

- **Fresh JVM process:** mỗi run là một process Java mới, nhưng OS page cache còn warm.
- **Cold class/JIT state:** process mới, chưa có runtime in-memory JIT profile/code cache; dữ liệu thư viện ở disk cache vẫn có thể warm.
- **Cold application caches:** ứng dụng chưa precompute caches/pools/connections.
- **Cold OS file/page cache:** trang của JAR/JDK files chưa nằm trong filesystem cache; tái lập khó và cần kiểm soát OS.
- **Cold container image/node:** node mới phải pull image, mount layers, start container, setup namespace/cgroup; không giống fresh Java process trên host warm.
- **Scale-to-zero request:** còn có load balancer/router, DNS/TLS/sidecar, scheduling và image distribution, có thể lớn hơn JVM init rất nhiều.

Mỗi report phải nói rõ **mốc bắt đầu** và cái gì đã warm. Không gọi vòng lặp launch process trên cùng laptop là “cold container startup” nếu image đã cached và JVM libs đã resident trong page cache.

### Test cold startup một cách an toàn

Đừng tự ý dùng lệnh drop kernel page caches trên production/shared machine chỉ để tạo “cold” condition. Nó thay đổi toàn host, ảnh hưởng dịch vụ khác và không phản ánh chắc môi trường thật. Với cloud/container, có thể đo bằng node/pod mới có kiểm soát hoặc reset môi trường thử nghiệm độc lập; ghi rõ chi phí image pull/scheduler thuộc phạm vi metric hay không.

## 9. Dung lượng bộ nhớ: sáu con số thường bị nhầm

| Chỉ số | Nó đo gì | Không có nghĩa |
| --- | --- | --- |
| **Heap used** | Bytes đang được JVM heap cấp cho objects/structures theo quản lý heap và GC telemetry | RAM process đang dùng |
| **Heap committed** | Heap memory JVM đã cam kết có thể dùng; thường khác used | Tất cả committed pages chắc resident vật lý |
| **Heap max** / `-Xmx` | Giới hạn heap mà JVM cố không vượt qua theo cấu hình/ergonomics | Giới hạn RSS toàn process |
| **Non-heap used/committed** | Metaspace, code cache và các pools được JMX phân loại non-heap | Toàn bộ native memory |
| **RSS** | Resident Set Size: số trang đang resident trong physical memory tính vào process theo OS | Dung lượng Java heap used; cũng không phải unique private bytes |
| **PSS** (Linux) | Proportional Set Size: phần resident shared pages được chia theo số process, hữu ích khi chia memory shared | Một API Java SE portable có ở mọi OS |

Còn các đại lượng:

- **Virtual Size / VSZ:** vùng địa chỉ ảo đã map/reserve; thường lớn hơn RSS, không bằng RAM thực.
- **USS/private resident:** phần resident mà process giữ riêng, hữu ích khi nhiều JVM chia sẻ libraries/CDS.
- **NMT reserved/committed:** view của HotSpot Native Memory Tracking về allocations/areas VM theo subsystem; khác RSS và có phạm vi giới hạn.
- **Container/cgroup `memory.current`:** tổng memory usage mà cgroup hạch toán, có thể gồm process memory, page cache và các phần khác; **không được đồng nhất với RSS của Java PID**.
- **Peak RSS / peak cgroup:** đỉnh memory trong một khoảng; readiness snapshot có thể bỏ lỡ peak.
- **Swap:** memory pages có thể được swap out, làm RSS thấp nhưng latency xấu; phải quan sát thêm nếu môi trường cho phép.

**Quan trọng nhất:** `-Xmx512m` **không** có nghĩa Java process chỉ dùng 512 MiB RAM. HotSpot còn cần native thread stacks, metaspace, code cache, GC metadata, direct buffers, JNI/native libraries và các regions runtime khác.

## 10. Heap used, committed, max: demo Java 17 độc lập

Tạo file **`HeapSnapshotDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public class HeapSnapshotDemo {
    static volatile byte[] retained;

    static void printMemory(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        System.out.println(label
                + " usedMiB=" + heap.getUsed() / (1024 * 1024)
                + " committedMiB=" + heap.getCommitted() / (1024 * 1024)
                + " maxMiB=" + heap.getMax() / (1024 * 1024));
    }

    public static void main(String[] args) {
        printMemory("before");

        retained = new byte[8 * 1024 * 1024];
        retained[0] = 1;
        retained[retained.length - 1] = 2;

        printMemory("after");
        System.out.println("arrayBytes=" + retained.length);
        System.out.println("endpoints="
                + (retained[0] + retained[retained.length - 1]));
    }
}
```

```bash
javac --release 17 HeapSnapshotDemo.java
java -Xms32m -Xmx128m HeapSnapshotDemo
```

**Hai dòng cuối stdout xác định:**

```text
arrayBytes=8388608
endpoints=3
```

Hai dòng `before/after` ghi các số **động**, khác JDK build/GC/heap layout và thời điểm runtime; không bịa expected used/committed. Với G1 region size/heap constraints, allocation có thể được quản lý khác với collector khác. Array có object header/padding nên **heap allocation thực có thể lớn hơn `arrayBytes`** (payload length).

Đọc số đo đúng:

- `getUsed()` là heap used tại thời điểm snapshot, **không phải bytes đã allocate cộng dồn**.
- `getCommitted()` là dung lượng JVM cam kết cho heap, có thể khác `used`.
- `getMax()` có thể là `-1` với một số memory pool/usage contexts không xác định maximum; đối với tổng heap trên JVM phổ biến sẽ liên hệ giới hạn heap.
- Cả ba **không** cho biết resident physical pages của process.
- Biến `retained` cố giữ reference mạnh tới array để demo có dữ liệu còn sống tới cuối chương trình; một phép đo thực tế cần tránh code bị dead-code elimination.

### Một ví dụ mô hình về sự khác biệt

Giả sử (số giả định):

```text
heap max        = 512 MiB
heap committed  = 256 MiB
heap used       = 120 MiB

native + mapped resident + other categories = 95 MiB
RSS OS          = 280 MiB

Kết luận hợp lý:
  heap used ≠ committed ≠ heap max ≠ RSS.
```

Các số không phải số đo từ `HeapSnapshotDemo`; chúng minh họa lý do **không** tính RSS bằng cách cộng một phép ước lượng native vào heap used mà không kiểm tra actual mappings/pages.

## 11. Đo non-heap và metaspace qua JMX Java SE

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` có thể trả aggregate non-heap used/committed. Nếu cần biết từng pool, đọc `MemoryPoolMXBean`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

public class NonHeapPoolsDemo {
    public static void main(String[] args) {
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            System.out.println(pool.getName()
                    + " -> " + pool.getUsage());
        }
    }
}
```

```bash
javac --release 17 NonHeapPoolsDemo.java
java NonHeapPoolsDemo
```

**Không có stdout cố định:** tên memory pools, số liệu và cách phân chia non-heap phụ thuộc collector, JVM implementation và version; HotSpot 17 thường có các pools cho **Metaspace**, **Compressed Class Space** (khi dùng) và **CodeHeap** segments.

**Đừng đọc Metaspace pool rồi cho rằng đã biết toàn bộ native memory.** Direct buffers, thread stacks, JVM internal arenas và native allocations khác không nhất thiết nằm trong JMX non-heap pools.

## 12. Đo RSS trên Linux và macOS/Windows

### Linux

Khi Java PID đang chạy:

```bash
ps -o pid,rss,vsz,comm -p <PID>
cat /proc/<PID>/status
cat /proc/<PID>/smaps_rollup
```

`<PID>` là **placeholder**; thay bằng PID thực. Các fields thường thấy:

- `VmRSS` trong `/proc/<PID>/status`: RSS của process theo kernel.
- `VmHWM`: high-water mark RSS (đỉnh resident do kernel báo) trong đời process.
- `Rss` và `Pss` trong `smaps_rollup`: resident và proportional resident cho các mappings phù hợp.
- `ps rss` trên nhiều Linux distributions báo **KiB** (kiểm tra man page), không tự coi bytes.

`smaps_rollup` có thể cần permissions/kernel hỗ trợ; việc đọc sâu trên production có chi phí. RSS có thể gồm file-backed mapped libraries/JDK archive pages shared với các process khác, không chỉ private Java pages.

### GNU time: peak RSS lúc process kết thúc

Với GNU `/usr/bin/time`:

```bash
/usr/bin/time -v java -Xms64m -Xmx256m HeapSnapshotDemo
```

`Maximum resident set size (kbytes)` là **peak RSS** theo công cụ/OS trong thời gian process chạy, không phải RSS đúng vào readiness. Nếu ứng dụng server không kết thúc, phải stop server trong môi trường test rồi đọc kết quả; và cần thống nhất thời điểm stop giữa variants.

**Cẩn thận:** shell builtin `time`, GNU `/usr/bin/time` và các hệ Unix khác có output/options khác nhau; `-v` không phải option chung cho mọi hệ.

### Windows PowerShell

Có thể quan sát process Java:

```powershell
Get-Process -Name java |
    Select-Object Id, WorkingSet64, PeakWorkingSet64,
                  PrivateMemorySize64, VirtualMemorySize64
```

Các giá trị thường ở bytes. `WorkingSet64` tương tự khái niệm resident working set nhưng **không bằng Linux RSS/PSS một cách hoàn hảo**. `PrivateMemorySize64` khác Java heap used. Dùng `Get-Process -Id <PID>` nếu nhiều Java processes. PowerShell labels/behaviors có thể khác theo phiên bản OS.

### macOS

`ps -o rss` và `vmmap <PID>` có thể hỗ trợ điều tra footprint nhưng định nghĩa/công cụ khác Linux. Đừng trộn numbers từ Windows WorkingSet, Linux RSS và macOS footprint trong một báo cáo so sánh ngang hàng mà không giải thích.

## 13. Native Memory Tracking (NMT) để phân tích bộ nhớ HotSpot

HotSpot có **Native Memory Tracking (NMT)** nhằm ước lượng/ghi nhận những categories native memory do VM quản lý. Kích hoạt **trước khi khởi động JVM**:

```bash
java -XX:NativeMemoryTracking=summary \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

Ở terminal khác với Java PID thích hợp:

```bash
jcmd <PID> VM.native_memory summary
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
```

`jcmd` cần JDK tools, cùng user/permissions thích hợp và process còn sống. NMT phải bật từ startup; không giả định có thể bật đầy đủ mọi cấp độ tracking giữa vòng đời process.

Có thể dùng baseline/diff khi runtime hỗ trợ:

```bash
jcmd <PID> VM.native_memory baseline
# Thực hiện một workload định nghĩa rõ
jcmd <PID> VM.native_memory summary.diff
```

**NMT reserved/committed không phải RSS:**

- **Reserved:** vùng địa chỉ ảo hoặc memory ranges đã dự trữ; không có nghĩa tất cả đã backed bằng physical pages.
- **Committed:** vùng đã cam kết theo allocator/VM; không nhất thiết bằng resident ngay tức thì.
- NMT chủ yếu theo dõi native allocations của **HotSpot/JVM**, **không bao trọn mọi native allocation từ third-party JNI libraries** hoặc memory phía OS.
- NMT có memory/CPU overhead và có thể làm biến động startup timing; muốn đo hiệu năng startup “clean” phải có lượt không NMT.
- `NativeMemoryTracking=detail` cho chi tiết hơn `summary` nhưng tăng overhead và volume dữ liệu; chỉ dùng khi cần.

### Tại sao so NMT với RSS có thể lệch?

RSS còn tính resident pages của mapped files/shared libraries, heap pages và native areas theo chính sách OS; NMT hạch toán ở categories reserved/committed trong runtime, có thể không theo dõi mọi native subsystem. Không yêu cầu tổng “NMT committed” bằng đúng “RSS”; đây là hai mô hình đo khác nhau.

## 14. Container memory: RSS chưa phải toàn bộ memory budget

Nếu Java chạy trong Linux container/cgroup v2, chỉ số thường gặp:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
```

Đường dẫn chỉ áp dụng khi process ở cgroup có mount/path tương ứng; trong môi trường có nested cgroups hoặc v1, phải xác định chính xác path controller. Một số files (như `memory.peak`) không tồn tại trên kernel/cgroup setup cũ.

Ý nghĩa:

- `memory.current`: usage theo cgroup accounting ở thời điểm đọc, có thể gồm nhiều processes và page cache theo kernel.
- `memory.max`: hard limit khi được cấu hình; giá trị `max` nghĩa không có limit cgroup đó theo file.
- `memory.peak`: high-water mark usage của cgroup phù hợp.
- `memory.events`: những sự kiện như OOM/OOM kill theo cgroup, cần đọc counter semantics.
- Container metric không nhất thiết bằng Java PID RSS; sidecar/native helpers/shared page cache có thể góp phần.

### Vì sao container bị OOMKilled khi heap used còn thấp?

Java heap chỉ là một phần memory footprint. Native thread stacks, metaspace, direct buffers, JIT/code cache, JVM internals, JNI, mapped files và page cache có thể làm cgroup chạm limit. Một process còn có thể bị kill bởi cgroup **mà không kịp ném `java.lang.OutOfMemoryError`** trong Java heap.

Nếu đo lợi ích startup trong container, báo cả **cgroup peak** và **process RSS** (khi thu được) thay vì chỉ dùng `MemoryMXBean.getHeapMemoryUsage().getUsed()`.

## 15. Peak, snapshot và steady-state: cần thu cả ba

Một service có thể:

1. Cần nhiều memory để parse cấu hình/truyền data vào các objects.
2. Giải phóng nhiều temporary objects sau startup.
3. JVM vẫn giữ heap committed.
4. RSS giảm chậm hoặc không giảm theo heap used vì page commitment/GC/OS policy.
5. Khi có traffic thật, thread stacks, caches và direct buffers tăng mạnh.

Vì vậy cần thu ít nhất:

- **Peak during startup:** đỉnh RSS/cgroup trong khoảng từ process start tới readiness.
- **At readiness:** RSS, heap used/committed, non-heap, NMT (nếu cần), process CPU time.
- **Steady state:** memory sau một workload/warm-up định nghĩa rõ (ví dụ sau 5 phút hoặc N requests) cùng throughput/p99.
- **After idle:** tùy mục tiêu serverless hoặc scale-to-zero; memory footprint sau thời gian nhàn rỗi.
- **Peak under traffic:** nếu ứng dụng có burst hoặc lazy initialization.

Một snapshot ở T4 **có thể bỏ lỡ peak xảy ra ở T2**. Một metric high-water mark ở process exit **không cho biết peak thuộc startup hay serving** nếu không có timeline.

## 16. Tại sao tăng `-Xms` có thể làm hiểu nhầm startup memory?

`-Xms` điều chỉnh kích thước heap ban đầu, còn `-Xmx` giới hạn heap tối đa. Thay đổi các flags có thể tác động:

- Memory committed từ đầu và khả năng heap mở rộng.
- GC ergonomics và điều kiện chọn cấu hình heap.
- RSS thực nếu các committed pages được chạm trong startup (không đồng nhất committed với resident).
- Startup timing vì page commitment/initialization và GC overhead.
- Throughput/tail latency sau ready.

Ví dụ thử nghiệm:

```bash
java -Xms64m -Xmx512m --add-modules jdk.httpserver StartupReadyServer 18080
```

So sánh với một cấu hình khác sau khi stop process cũ:

```bash
java -Xms256m -Xmx512m --add-modules jdk.httpserver StartupReadyServer 18080
```

**Không đưa ra kết luận trước khi đo**: `-Xms64m` có thể giảm committed heap tại ready nhưng làm heap growth/GC khác, không bảo đảm process-to-ready nhanh hơn hay RSS thấp hơn một tỷ lệ cố định. Đặc biệt `-XX:+AlwaysPreTouch` có thể khiến các trang committed được pre-touch, đổi mạnh chi phí startup và resident pages; nếu so sánh phải kiểm soát flag ấy.

**Không thay đồng thời `-Xms`, `-Xmx`, collector và concurrency** rồi đổ mọi thay đổi cho một biến. Chạy A/B có kỷ luật.

## 17. Class Data Sharing (CDS) và memory sharing

**Class Data Sharing (CDS)** của HotSpot có thể dùng một archive chứa metadata/class data đã xử lý để giảm một số chi phí class loading và cho phép chia sẻ mapped pages giữa nhiều Java processes. Điều này có thể liên quan tới cả **startup time** lẫn footprint, nhưng phải xem JVM/runtime thực tế.

Một cách **quan sát**, không ép kết quả:

```bash
java -Xshare:auto -Xlog:cds=info -version
```

Trong các HotSpot builds phổ biến, `-Xshare:auto` cho JVM dùng archive nếu khả dụng; khi không thể dùng archive có thể fallback theo semantics của flag. `-Xshare:on` có chính sách khắt khe hơn và có thể làm JVM exit nếu shared archive không dùng được. Không tự suy cứ có `-Xshare:auto` là archive chắc đã được sử dụng.

### CDS, AppCDS và shared pages

- **Default CDS archive:** có thể được JDK cung cấp/khởi tạo tùy distribution và cách cài.
- **Application CDS (AppCDS):** cần quy trình tạo/sử dụng archive theo đúng app/class path/module path/build; chỉ nên dùng khi đã có workload/class list thích hợp.
- **Shared mapped pages:** hai JVM processes dùng cùng CDS/JDK libraries có thể share resident pages, khiến tổng RSS của từng process **đếm lặp** shared pages.
- **PSS/USS** hữu ích hơn RSS đơn lẻ khi muốn biết incremental memory cost của nhiều replicas, nhưng mỗi metric có constraints.

**Không kết luận “CDS giảm RSS bằng X MiB” dựa trên một lần chạy**. Trên một process, mapped shared archive pages có thể vẫn làm RSS trông lớn, trong khi memory thực tăng thêm cho replica thứ hai lại thấp hơn. So **startup-to-ready** và **PSS/incremental cgroup footprint** theo mô hình deployment.

## 18. JIT và tiered compilation trade-off với startup

Đối với những ứng dụng chạy vài trăm mili-giây rồi exit, chi phí nạp class/JIT có thể chiếm đáng kể. Đối với server chạy hàng giờ, C2 optimized code có thể tiết kiệm CPU đáng kể sau warm-up.

Một flag HotSpot hay dùng trong **thử nghiệm riêng**:

```bash
java -XX:TieredStopAtLevel=1 \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

Flag này giới hạn tiered compilation ở cấp C1 level 1 theo policy HotSpot phổ biến; nó **không đồng nghĩa Java chạy interpreter-only**. Nó có thể giảm một số overhead của profiling/C2 compilation và cải thiện vài chỉ số startup ở workloads phù hợp, nhưng có thể **giảm throughput hoặc tăng latency CPU-bound về lâu dài**.

Những phép đo cần so:

1. Process-to-readiness median/p95.
2. First business request duration.
3. Compilation CPU cost trong startup (diagnostic run).
4. RSS/committed/code cache ở ready.
5. 5–15 phút throughput/CPU/p99 sau ready, nếu app sống lâu.
6. Peak RAM khi nhiều replicas scale cùng lúc.

Không chọn cấu hình tối ưu startup mà chỉ dựa một microbenchmark method tính số: **điểm ready thực tế có thể nằm ở framework init/network/DB**, không phải JIT.

## 19. GC collector có ảnh hưởng startup không?

Collector khác nhau có thể thay đổi:

- JVM/GC initialization work.
- Metadata, native memory và background threads.
- Heap sizing/commit policies.
- Young/old GC pause behavior khi app khởi động.
- Memory footprint và throughput khi phục vụ traffic.

Ví dụ thử nghiệm **chỉ một biến mỗi lần**:

```bash
java -XX:+UseSerialGC -Xms64m -Xmx512m \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

So với default collector **trên cùng JDK 17/container/heap**. `SerialGC` có thể phù hợp với process nhỏ, CPU-constrained hoặc short-lived workloads nhưng không phải “luôn nhanh nhất khi khởi động”; GC pauses và throughput dưới tải phải được đo.

**Lưu ý:** không chạy `UseSerialGC` và `UseG1GC` cùng lúc như thể có thể dùng hai collectors. JVM flag/ergonomics của mỗi JDK và container có thể chọn collector khác. Ghi `-XX:+PrintFlagsFinal` và `-Xlog:gc*=info` trong **diagnostic run** nếu cần biết collector thực đang dùng.

## 20. Giảm dependencies và lazy initialization: cẩn thận dời chi phí

Các kỹ thuật giúp giảm việc phải làm trước ready:

- Bỏ dependencies/framework modules không được dùng.
- Tránh classpath scanning quá rộng khi có cấu hình chính xác hơn.
- Bỏ eager initialization của caches không cần cho request đầu tiên.
- Khởi tạo client/database pools theo nhu cầu và cấu hình connection timeouts.
- Dùng lazy initialization cho feature ít dùng.
- Giảm số synchronous external calls bắt buộc ở startup.
- Dùng CDS/AppCDS trong những môi trường phù hợp.
- Giảm work logging/diagnostics không thiết yếu trước ready.

Nhưng rất dễ **dời chi phí sang lần request đầu**:

```text
Before:
  startup-to-ready = 800 ms
  first-request    = 30 ms

After lazy initialization (mô hình):
  startup-to-ready = 500 ms
  first-request    = 380 ms

Nếu traffic đến ngay sau ready, trải nghiệm có thể xấu hơn.
```

Đây là **số giả định để giải thích**, không phải kết quả benchmark. Một readiness contract tốt phải xác định những dependencies/cache paths nào cần được warm trước khi công bố 200.

### Lazy init và khả năng chịu lỗi

Nếu deferred initialization có thể fail ở first request, service đã đánh dấu ready dù chưa thể phục vụ một phần workload. Có thể chấp nhận với optional feature và graceful degradation, nhưng không chấp nhận nếu dependency ấy bắt buộc cho mọi request. **Định nghĩa “ready” là quyết định vận hành**, không chỉ optimization trick.

## 21. Ứng dụng CLI và batch: readiness có thể là completion

Đối với một CLI utility chạy Java, mốc ý nghĩa có thể là:

- Từ OS spawn tới stdout có **kết quả đúng**.
- Từ OS spawn tới **exit code 0** sau khi hoàn tất job.
- Từ dispatch task ở queue tới worker nhận job; hoặc thời gian xử lý xong job.
- Từ container create tới batch hoàn tất (bao gồm image pull nếu đó là mục tiêu).

Ví dụ không nên làm:

```bash
time java -version
```

Lệnh này đo launcher/JVM version-print path, **không đại diện startup của một ứng dụng nghiệp vụ có nhiều dependencies**. Có thể dùng làm một baseline thấp mang tính thông tin, nhưng không lấy nó thay performance của service thật.

Đối với CLI, kết quả giả nhanh do JVM không thực thi logic cần thiết sẽ đánh lừa hoàn toàn. Bảo đảm **output đúng, code path giống production** và dữ liệu input tương đương trước khi đọc timing.

## 22. So sánh baseline và candidate phải giống mọi yếu tố khác

Bảng thiết kế A/B:

| Dimension | Baseline A | Candidate B |
| --- | --- | --- |
| Source/application release | Cùng commit/build logic | Cùng commit nếu chỉ so JVM flag |
| JDK vendor/version/build | Java 17.0.x cụ thể | Giống A |
| CPU/cores, RAM, disk | Cùng machine/VM/container | Giống A |
| Cgroup memory/cpu limits | Cố định | Cố định |
| `-Xms/-Xmx` | Đã ghi rõ | Chỉ thay nếu là biến thử |
| CDS/GC/tiering | Ghi mọi flags | Chỉ thay chủ đích |
| Startup dependencies | DB/queue/network state kiểm soát | Tương đương A |
| Readiness definition | Cùng endpoint và response validation | Giống A |
| Probe interval/timeout | Cùng | Giống A |
| Run count/order | N trials, A/B xen kẽ | N trials, xen kẽ |
| Workload sau ready | Cùng input, concurrency, duration | Giống A |
| Output correctness | Required pass | Required pass |

Nếu mục đích so **hai JDKs**, đương nhiên JDK build là biến chủ đích; các yếu tố còn lại cố giữ tương đương. Nếu so **CDS**, archive/JAR/classpath phải được chuẩn bị đúng trên cả variants.

### Vì sao nên xen kẽ A/B?

Nếu chạy 20 lần A rồi 20 lần B, về cuối test OS page cache và CPU nhiệt độ có thể thay đổi, làm B có vẻ tốt hơn/xấu hơn do thứ tự. Xen kẽ hoặc randomize A/B giúp giảm **systematic drift**, nhưng không tự tạo tính độc lập tuyệt đối của samples. Ghi thời gian thứ tự, host load và các yếu tố môi trường.

## 23. Đọc thống kê: median, p95, variance, CI

Startup time thường có phân bố không chuẩn: đôi khi spike vì JIT/GC, CPU scheduling, host noise hoặc remote dependency. Một bảng “chỉ mean” có thể che biến động.

- **Median (p50):** startup điển hình của sample set.
- **p90/p95/p99:** tail startup; cần đủ số samples để percentile có ý nghĩa.
- **Min/max:** giới hạn quan sát được; min thường được lợi bởi page cache/lucky scheduling.
- **Std deviation / IQR:** độ phân tán; diễn giải với distribution shape.
- **Bootstrap CI hoặc phương pháp phù hợp:** thể hiện độ bất định của ước lượng.
- **Outliers:** không tự loại chỉ vì “làm số xấu”; tìm nguyên nhân hoặc báo kèm phương pháp lọc được xác định trước.

**Đừng lấy `p99` từ 5 trials làm kết luận đáng tin.** Với sample nhỏ, percentile cực cao phần lớn phản ánh một vài quan sát và bất định rất lớn. Nên chọn số trials dựa vào độ nhiễu, budget và yêu cầu độ tin cậy, không dùng một số cố định cho mọi workload.

### Warm-up cho server benchmark khác startup test

Trong **mỗi trial startup**, process cần mới nếu muốn đo init/JIT từ cold process. Nhưng để đánh giá **steady state**, cần cho server chạy và warm workload trước khi đo throughput.

**Không warm-up JVM trước rồi tính thời gian từ đó và gọi đó là cold process startup**. Đồng thời không đo throughput ngay sau process ready rồi báo là đã đạt steady state nếu code lazy-init/JIT còn đang warm.

## 24. Công thức đánh giá lợi ích và trade-off

Với A là baseline và B là candidate:

```text
timeSavedMs = readyMsA - readyMsB

timeImprovementPct = (readyMsA - readyMsB) / readyMsA * 100

rssChangeMiB = rssB - rssA

rssChangePct = (rssB - rssA) / rssA * 100
```

Nếu metric càng thấp càng tốt (startup, RSS, p99 latency), dấu **dương của timeImprovementPct** nghĩa B cải thiện thời gian; dấu dương của `rssChangePct` nghĩa B **tốn RSS hơn**.

Ví dụ **hoàn toàn giả định**:

| Metric | Baseline A | Candidate B | Diễn giải |
| --- | ---: | ---: | --- |
| Median process-to-ready | 900 ms | 660 ms | Giảm 240 ms (~26,7%) |
| p95 process-to-ready | 1.200 ms | 970 ms | Giảm 230 ms |
| RSS tại ready | 120 MiB | 135 MiB | Tăng 15 MiB (12,5%) |
| Peak cgroup startup | 175 MiB | 185 MiB | Tăng 10 MiB |
| First request p95 | 45 ms | 70 ms | Tệ hơn 25 ms |
| Throughput steady state | 5.000 req/s | 4.400 req/s | Giảm 12% |

**Kết luận ví dụ:** B khởi động nhanh hơn nhưng tăng RAM và giảm throughput. Nếu mục tiêu serverless scale-to-zero có mức giới hạn RAM đủ rộng, trade-off có thể chấp nhận **khi first-request penalty được xét kỹ**. Nếu service luôn chạy và cần throughput cao, B có thể kém lợi.

**Không có một “startup score” universal**. Định nghĩa trước ngưỡng vận hành/SLO: “ready p95 dưới N giây, RSS peak dưới M MiB, steady-state throughput không giảm quá K%, correctness pass”. SLO tùy sản phẩm, không bịa N/M/K chung cho mọi hệ thống.

## 25. Java 17: chương trình tính phần trăm không phụ thuộc JVM timing

Tạo file **`StartupBenefitMath.java`**:

```java
public class StartupBenefitMath {
    static double improvementPct(double oldValue, double newValue) {
        if (oldValue <= 0) {
            throw new IllegalArgumentException("baseline must be positive");
        }
        return (oldValue - newValue) * 100.0 / oldValue;
    }

    public static void main(String[] args) {
        double beforeMs = 900.0;
        double afterMs = 660.0;
        double beforeRss = 120.0;
        double afterRss = 135.0;

        System.out.printf(java.util.Locale.ROOT,
                "timeSavedMs=%.0f%n", beforeMs - afterMs);
        System.out.printf(java.util.Locale.ROOT,
                "timeImprovement=%.1f%%%n",
                improvementPct(beforeMs, afterMs));
        System.out.printf(java.util.Locale.ROOT,
                "rssChangeMiB=%.0f%n", afterRss - beforeRss);
        System.out.printf(java.util.Locale.ROOT,
                "rssChange=%.1f%%%n",
                (afterRss - beforeRss) / beforeRss * 100);
    }
}
```

```bash
javac --release 17 StartupBenefitMath.java
java StartupBenefitMath
```

**Stdout xác định:**

```text
timeSavedMs=240
timeImprovement=26.7%
rssChangeMiB=15
rssChange=12.5%
```

Những số 900/660/120/135 đều là **số giả định để dạy cách tính**. Chương trình **không tự đo** startup hay RSS; muốn đánh giá app phải lấy số từ harness và OS/container tools rồi tính cùng công thức.

## 26. Đo memory mà không làm lệch startup timing

Một sai lầm phổ biến là bật mọi diagnostics lúc baseline nhưng tắt khi đo candidate. NMT, JFR, log class loading và thread dumps đều có thể tác động startup/memory.

Thiết kế nên có **hai đường thí nghiệm**:

1. **Clean performance runs:** tối thiểu instrumentation, cùng metrics probe bên ngoài, cùng JVM flags ngoại trừ biến thử; thu time-to-ready và RSS/cgroup sampling ngoài process.
2. **Diagnostic runs:** bật NMT/JFR/GC logs/class-load logs để giải thích tại sao; chấp nhận overhead nhưng không trộn trực tiếp numbers vào clean A/B.

Ví dụ bật JFR **từ JVM startup**:

```bash
java -XX:StartFlightRecording=filename=startup.jfr,dumponexit=true,settings=profile \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

Recording với `dumponexit=true` ghi lại khi JVM thoát phù hợp; phải stop demo bằng Ctrl+C/signal và kiểm tra file `startup.jfr` thật sự được tạo. JFR có overhead và event configuration phụ thuộc JDK build; không hứa chính xác một event sẽ luôn có.

**JFR giúp tìm class load, compilation, GC, thread/events, CPU samples theo event availability**, nhưng không thay được external readiness marker hoặc OS RSS. Khi cần memory chính xác lúc ready, thu snapshot trực tiếp hoặc sampler ngoài process.

## 27. Warm-up vẫn quan trọng sau khi ứng dụng đã ready

Một server có thể mở cổng và trả 200 khi compiler mới chạy C1, chưa JIT optimized hot routes. Nếu đưa traffic ngay lúc ấy:

- First requests có thêm lazy class loading, dependency resolution.
- JIT profiling, C2 compilation hoặc deoptimization có thể tăng CPU.
- TLS/JDBC caches chưa warm.
- Garbage collector chưa có đủ activity để ổn định GC ergonomics.
- Tail latency cao hơn sau khi warm.

Hai hướng design:

**A. Ready sớm:** chấp nhận một khoảng warm-up khi serving; phù hợp nếu first-request latency SLO cho phép, có prewarming từ load balancer hoặc traffic thấp.

**B. Ready sau khi warm một tập representative paths:** startup-to-ready dài hơn nhưng first-request latency ổn định hơn. Không chạy một vòng lặp artificial chỉ để kích JIT mà khác code path production; có thể làm profile lệch và không đại diện.

Nên báo hai metrics cùng nhau: **time to ready** và **time to first acceptable latency/throughput**, tránh tối ưu chỉ có một mốc.

## 28. Đo nhiều replicas: RSS cộng thẳng có thể đếm lặp

Nếu 10 JVM processes cùng map một CDS archive hoặc shared libraries, cộng `RSS(PID1)+...+RSS(PID10)` có thể **đếm lặp cùng physical pages**. Để ước lượng memory tổng của node/cgroup:

- Quan sát **cgroup memory.current/peak** cho nhóm processes (hiểu shared accounting).
- Quan sát **PSS** theo process trên Linux khi có quyền và kernel hỗ trợ.
- So **incremental node/cgroup memory** khi tăng replicas 1→2→N trên môi trường kiểm soát.
- Phân biệt app heap/private anonymous resident với file-backed/shared pages.
- Lưu ý memory cache, sidecars, GC threads và OS memory accounting.

**Ví dụ giả định:** RSS của mỗi JVM là 150 MiB, nhưng 30 MiB là shared pages của cùng JDK/lib archive; hai JVM không tự động tiêu 300 MiB physical private RAM. Tuy nhiên cũng không đơn giản lấy 2×(150−30)+30 nếu có những shared mappings khác, page cache và OS accounting khác; hãy đo thực.

## 29. Một hình mẫu benchmark sheet/CSV cần báo

Với mỗi trial, lưu các trường:

```text
experiment_id
variant
trial_index
jdk_vendor
jdk_version
jdk_build
jvm_flags
os_kernel
cpu_model
cpu_quota
memory_limit
container_image_digest
app_commit
process_start_monotonic_ns
readiness_http_status
ready_elapsed_ms
first_work_success_ms
rss_ready_kib
rss_startup_peak_kib
cgroup_memory_ready_bytes
cgroup_memory_peak_bytes
heap_used_ready_bytes
heap_committed_ready_bytes
native_memory_tracking_enabled
steady_state_rps
steady_state_p95_ms
steady_state_p99_ms
failure_reason
```

Đây là **định dạng cột đề xuất**, không phải một CSV kết quả thật. Chỉ những fields có thể thu một cách nhất quán mới nên dùng để so; điền missing khi không có số, **không tự thay bằng 0** vì 0 ngụ ý đã đo và thực sự không dùng memory/time.

Nếu startup fail (exit nonzero, readiness timeout, dependency unavailable), ghi **failure trial** và lý do. Không tùy ý bỏ trials fail rồi báo “startup nhanh và ổn định”.

## 30. Sai lệch do hệ điều hành và môi trường triển khai

Những nguồn nhiễu không phải bug Java:

- **OS page cache:** JAR/JDK classes có thể đã resident sau vài trials.
- **Filesystem/network storage:** container image layer hoặc network file mount làm thời gian đọc khác nhau.
- **CPU quota/throttling:** container bị giới hạn CPU có thể mất nhiều wall-clock time dù CPU work không đổi.
- **Host contention:** các processes khác chiếm CPU/cache/memory bandwidth.
- **CPU frequency/thermal:** turbo boost, power saving và nhiệt độ gây drift.
- **NUMA placement:** page faults/thread placement khác ở máy nhiều sockets.
- **DNS/TLS/database health:** external latency và timeouts có thể chi phối ready.
- **Logging/tracing/agents:** Java agents, JFR, NMT, class-load logging tăng overhead.
- **Image pull/scheduling:** tùy metric, có thể chiếm phần lớn total scale-to-zero latency.
- **Clock granularity/probe cadence:** polling quá thưa che cải thiện nhỏ.
- **GC timing and heap ergonomics:** initial heap/committed differences gây biến động.
- **Security/antivirus scanning:** có thể ảnh hưởng file loads trên desktop/Windows.
- **Stale processes/port collision:** poll nhầm endpoint của process cũ làm ready time gần 0 giả tạo.

### Đặc biệt: kiểm tra process identity khi poll

Một harness dùng cổng cố định có thể mắc lỗi: process cũ chưa tắt nhưng endpoint vẫn trả 200, khiến trial mới được ghi “ready” trước khi JVM mới thật sự startup. Bản mẫu ở trên **kết thúc process mỗi trial**, nhưng trong benchmark mạnh hơn nên:

- Dùng port mới cho mỗi trial hoặc process-specific token.
- Xác minh PID/process đang trả endpoint và port ownership.
- Đợi process cũ hoàn toàn exit, kiểm tra port được release.
- Ghi failure nếu subprocess mới thoát sớm.
- Không report success khi kết nối nhầm server khác.

Đây là loại lỗi thực tế có thể tạo “startup 0–20 ms” rất thuyết phục nhưng vô nghĩa.

## 31. Những kết luận sai về memory

| Kết luận sai | Điều đúng |
| --- | --- |
| “`-Xmx` bằng giới hạn RAM của JVM” | `-Xmx` chỉ giới hạn **Java heap**, không gồm native footprint |
| “Heap used thấp thì RSS cũng thấp” | Heap committed, metaspace, code cache, stacks, native allocations vẫn tốn |
| “Heap committed là toàn bộ RAM resident” | Committed khác resident physical pages |
| “VSZ 4 GiB nghĩa JVM ăn 4 GiB RAM” | Virtual reserved address space không bằng RSS |
| “RSS của 10 replicas cộng lại = unique physical RAM” | Shared mappings/CDS có thể bị đếm lặp |
| “NMT total committed phải bằng RSS” | NMT và OS RSS có coverage/accounting khác |
| “NMT theo dõi mọi JNI allocation” | NMT không bao trọn tất cả third-party native memory |
| “Metaspace bằng toàn bộ native memory” | Chỉ một vùng/cấu phần |
| “Container memory.current bằng một Java PID RSS” | cgroup có thể gồm nhiều processes/cache |
| “Readiness RSS đủ đại diện peak” | Startup có thể có temporary peak trước ready |
| “GC chạy thì RSS phải giảm ngay” | JVM/OS commit, page reclamation và GC policy quyết định |
| “Giảm -Xms luôn giảm startup time” | Chỉ là một trade-off, cần đo; GC/heap growth có thể đổi |
| “Đổi GC chỉ tác động pauses, không tác động footprint” | GC implementation có threads, metadata và sizing policies riêng |

## 32. Những kết luận sai về startup

| Kết luận sai | Điều đúng |
| --- | --- |
| “Java process tạo xong là app ready” | JVM và ứng dụng còn initialization work |
| “Đầu main là mốc total startup” | Bỏ qua launcher và phần JVM khởi tạo trước main |
| “Port listening nghĩa phục vụ được nghiệp vụ” | Endpoint có thể trả 503 hoặc dependencies chưa ready |
| “Log 'Started' là mốc tuyệt đối” | Log buffering/order không thay external readiness probe |
| “Latency first request chắc bằng ready time” | First request có lazy init, TLS, code warm-up khác |
| “Một trial nhanh hơn chứng minh tối ưu” | OS caches, scheduler, polling gây nhiễu |
| “JMH method benchmark đo process startup” | JMH đo microbenchmark hot/steady state theo harness |
| “Bật PrintCompilation không làm timing đổi” | Diagnostics có overhead |
| “CDS luôn giảm RSS của process” | Shared mappings có cách accounting khác, phải đo |
| “TieredStopAtLevel=1 luôn tốt hơn default” | Có thể giảm steady-state throughput |
| “SerialGC luôn là collector startup tốt nhất” | Phụ thuộc workload, heap, CPU và SLA |
| “Lazy init luôn cải thiện user experience” | Có thể chuyển chi phí sang first request và tăng failures |
| “Từ container start đến ready giống Java launch-to-ready” | Container setup/image pull/sidecar là phần khác |
| “p99 của năm trial đáng tin” | Sample size quá nhỏ để suy tail confidence |
| “Warm run trên host = cold startup” | OS page cache có thể còn warm |
| “Một flag thay đổi cùng lúc với JDK/app build vẫn phân tích được” | Confounding variables; phải kiểm soát design |

## 33. Một quy trình đánh giá có thể tái lập

**Bước 1 — Định nghĩa điều kiện thành công.** Viết rõ endpoint/operation trả gì, status code nào, dependencies nào cần sẵn sàng. Phân biệt liveness/ready/first request.

**Bước 2 — Định nghĩa mốc T0.** Java process created, container started, pod scheduled, hay request đến serverless platform? Không trộn các loại mốc.

**Bước 3 — Chốt môi trường.** Ghi JDK vendor/version, OS/CPU, cgroup limits, JAR/image digest, framework flags, dependencies state.

**Bước 4 — Chọn baseline A.** Lưu JVM flags đang dùng, heap initial/max, GC, CDS, tiered policy.

**Bước 5 — Chọn đúng một thay đổi B.** Ví dụ chỉ bật CDS, chỉ đổi `TieredStopAtLevel`, chỉ giảm eager initialization hoặc chỉ đổi `-Xms`.

**Bước 6 — Xây harness ngoài process.** Spawn JVM/process, poll readiness, có timeout, kiểm tra HTTP 200 + body/process identity, stop sạch và ghi lỗi.

**Bước 7 — Chạy nhiều trials độc lập.** Ghi cả những runs fail, xen kẽ thứ tự A/B, không coi một lần đo là benchmark.

**Bước 8 — Thu memory cùng mốc.** RSS tại ready, RSS peak lúc startup, heap used/committed (nếu cần), cgroup memory.current/peak. Không so sai đơn vị KiB/MiB.

**Bước 9 — Thu first-request metric.** Đảm bảo ứng dụng B không chỉ dời initialization sang request đầu.

**Bước 10 — Thu steady-state.** Với server dài hạn, đo throughput/CPU/p95/p99 sau representative warm-up.

**Bước 11 — Chạy diagnostics riêng.** Dùng JFR/NMT/GC/class load logs để giải thích nguyên nhân mà không làm lệch clean comparison.

**Bước 12 — Tính deltas và uncertainty.** Median/p95/time saved, RSS change/peak, failure rate và confidence; không chỉ báo “faster”.

**Bước 13 — Kiểm tra correctness.** Request thật/CLI output/batch result phải tương đương; readiness không được báo 200 quá sớm.

**Bước 14 — Quyết định theo SLO.** Startup nhanh hơn có đáng tăng RAM/giảm throughput không? Phù hợp scale-to-zero, batch hay service sống dài?

**Bước 15 — Kiểm tra regression.** Chạy trên môi trường gần production, với real image/build và constraints tương tự; giữ A/B logs để tái lập.

## 34. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `mainToReadyMs` không phải total startup?

Vì nó bắt đầu **sau** Java launcher/JVM initialization trước khi `main` được gọi.

**Câu 2:** Một server đã bind port, có chắc ready?

**Không.** Dependencies/handlers có thể chưa đáp ứng; cần readiness condition có nghĩa nghiệp vụ.

**Câu 3:** `-Xmx512m` có giới hạn process RSS ở 512 MiB không?

**Không.** Heap chỉ là một phần footprint.

**Câu 4:** Heap used = 100 MiB, committed = 300 MiB, RSS = 350 MiB có mâu thuẫn không?

**Không.** Ba metrics đo các khía cạnh khác nhau.

**Câu 5:** Vì sao cần peak RSS ngoài RSS tại ready?

Startup có thể cấp memory tạm thời rồi giải phóng trước ready, khiến snapshot bỏ sót peak.

**Câu 6:** NMT committed và OS RSS phải khớp từng byte?

**Không.** Có coverage và accounting khác nhau.

**Câu 7:** Vì sao `-XX:TieredStopAtLevel=1` có thể làm startup nhanh nhưng steady-state throughput xấu hơn?

Nó thay đổi JIT/tiering và không cho C2 tối ưu sâu theo policy thông thường, trade-off phụ thuộc workload.

**Câu 8:** CDS luôn giảm RSS trên một process?

**Không được bảo đảm.** Shared archive pages vẫn có thể tính trong RSS; PSS/incremental footprint có ý nghĩa khác.

**Câu 9:** Vì sao không dùng năm lần thử để khẳng định p99 startup?

Tail percentile cần đủ quan sát; năm trials có bất định quá lớn.

**Câu 10:** Tại sao `memory.current` không bằng `ps rss` của Java?

Cgroup có thể hạch toán nhiều processes/page cache và loại memory khác so với per-PID RSS.

**Câu 11:** Lazy initialization làm readiness nhanh hơn có chắc tốt?

**Không.** Nó có thể làm first request chậm hoặc fail, tăng peak và gây latency spikes.

**Câu 12:** Một harness poll mỗi 100 ms có đo được cải thiện 5 ms một cách chính xác không?

**Khó.** Poll quantization/scheduling có thể che cải thiện; cần thiết kế probe phù hợp.

**Câu 13:** Vì sao phải chạy clean và diagnostic runs riêng?

NMT/JFR/logging có overhead, có thể thay đổi chính startup timing/memory cần đo.

**Câu 14:** Muốn đo Java CLI tool, readiness endpoint có bắt buộc?

**Không.** Mốc thích hợp có thể là **kết quả nghiệp vụ đúng hoặc process exit thành công**.

**Câu 15:** Nếu B giảm ready 20% nhưng RSS +30% và first-request p95 xấu đi thì chọn B?

**Không thể quyết định chỉ từ % ready.** Phải xét SLO, RAM budget, traffic pattern, throughput và workload reality.

## 35. Tài liệu tham khảo Java 17 và công cụ liên quan

- [Oracle Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-Xshare`, `-XX` flags, GC logging, JFR startup.
- [Oracle Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.native_memory`, `VM.flags`, `JFR.start`/`dump`.
- [Oracle Java SE 17 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html): CDS, tiered compilation và tối ưu HotSpot.
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): mục tiêu CDS và cơ chế shared archive ở version này.
- [Oracle Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): `reserved`/`committed`, coverage và overhead.
- [Oracle Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): GC/heap ergonomics, trade-offs của collectors.
- [Java SE 17 — `Runtime.totalMemory`/`freeMemory`/`maxMemory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): heap capacity-related API.
- [Java SE 17 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html) và [`MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max trong heap và non-heap.
- [Java SE 17 — `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): các pools như Metaspace/CodeHeap (tùy JVM).
- [Java SE 17 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo duration, không diễn giải giá trị tuyệt đối.
- [Java SE 17 — `jdk.httpserver` module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): server demo và HTTP contexts.
- [OpenJDK JFR — Flight Recorder](https://openjdk.org/jeps/328): công cụ runtime profiling và startup recording.
- [Linux kernel cgroup v2 memory documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory): `memory.current`, `memory.max`, `memory.peak` và counters.
- [Linux proc `proc_pid_status`](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html) và [`proc_pid_smaps`](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): VmRSS/VmHWM/PSS và memory mapping accounting.
- [GNU time](https://www.gnu.org/software/time/): `/usr/bin/time -v` và peak RSS trên hệ hỗ trợ.

**Kết luận:** Một cải thiện khởi động chỉ đáng tin khi bạn **đo đúng thời gian từ process/container start tới readiness có nghĩa**, kiểm tra **request đầu tiên/steady-state trade-offs**, và báo **RSS hoặc cgroup peak** ngoài heap used/committed. Java 17 có đủ công cụ cho việc này: endpoint ready, harness monotonic ngoài JVM, `MemoryMXBean`, `jcmd` NMT/JFR và OS/container metrics. Hãy chạy nhiều trials trên điều kiện tương đương, giữ baseline, trình bày uncertainty, phân biệt số đo thật với ví dụ giả định và chỉ kết luận dựa trên **SLO cùng tổng cost của ứng dụng**.
