# Đo overhead và khả năng phục hồi khi phần xuất sự kiện bị chậm

**Ngữ cảnh:** Java Advance → instrumentation → **Thực nghiệm agent**.

Java agent thu thập traces, metrics hay events thường chèn một hook ngắn vào method nghiệp vụ. Đằng sau hook có thể là serialization, hàng đợi, batch, network exporter và collector. Nếu exporter chậm hoặc không phản hồi, một thiết kế thiếu backpressure có thể biến **lỗi telemetry** thành **lỗi ứng dụng**: thời gian đáp ứng tăng, thread pool kẹt, out-of-memory hoặc business exception bị che bởi lỗi exporter.

Bài học xây một thí nghiệm có thể tái lập để trả lời:

1. **Overhead:** bật agent làm throughput, latency p50/p95/p99 và CPU/GC thay đổi ra sao?
2. **Khi exporter chậm:** thread nghiệp vụ có chờ không? Hàng đợi có đầy không, memory có giới hạn không?
3. **Khi exporter dừng hẳn:** nghiệp vụ có còn chạy và số event bị bỏ được hạch toán không?
4. **Khi exporter hồi phục:** events còn tồn đọng có được xử lý, worker có sống sau exception, shutdown có deadline không?
5. **Độ tin cậy:** counts của business, events đã nhận, đã gửi, lỗi và pending có khớp với hợp đồng đã chọn không?

Ví dụ chính sử dụng **JDK 17+, Maven, ASM và Java agent `-javaagent` thực sự chèn hook**. Exporter chỉ là sink mô phỏng bằng worker thread và `Thread.sleep` có thể điều khiển, nên không phải cấu hình collector ngoài. Các số đo nanosecond/throughput cần chạy trên máy cụ thể; tài liệu chỉ công bố **stdout xác định theo logic** và công thức để tự tính overhead, không bịa kết quả đo.

> **Chính sách của lab:** fail-open cho telemetry. Nếu exporter bị kẹt, ứng dụng **không chờ queue trống**; event không thể xếp hàng bị bỏ và ghi `dropped`. Đây là lựa chọn phù hợp để minh họa tracing/metrics, **không phải lựa chọn mặc định cho sự kiện audit bắt buộc không mất**.

## 1. So sánh hai kiến trúc xuất sự kiện

### 1.1. Xuất đồng bộ trên request thread

```text
Request
  -> Service.work()
       -> instrumentation hook
            -> encode event
            -> send HTTP to exporter
            -> await ACK/timeout
       -> execute original method
  -> response
```

Nếu exporter chờ 300 ms, hook có thể giữ request thêm 300 ms. Chỉ riêng một `Future.get()`, `CompletableFuture.join()`, `BlockingQueue.put()` hoặc `CountDownLatch.await()` đặt trên request path cũng đủ tạo thời gian đợi.

Ví dụ anti-pattern (fragment, không phải chương trình độc lập):

```java
public static void onEntry() {
    exporter.sendSynchronously(buildEvent());
    // Method nghiệp vụ phải chờ exporter.
}
```

Một tên class như `AsyncExporter` không đảm bảo không block: hãy kiểm tra **lệnh thực tế trên thread ứng dụng**, cả serializer/logging/callback.

### 1.2. Xuất qua bounded queue và worker riêng

```text
Business thread A, B, C...         Worker export thread
       │                                    │
       ▼                                    ▼
  Agent.onEntry()                      poll event
       │                                    │
  ArrayBlockingQueue.offer(event)         send
       │                              ┌─────┴──────┐
       ├── accepted                   │            │
       │       └─────────────► bounded queue      │
       └── dropped nếu đầy            success      failure
                                       │            │
                                    exported       failed

Business path tiếp tục dù queue đầy.
```

`ArrayBlockingQueue.offer(E)` không chờ cho tới khi có chỗ: khi đầy nó trả `false`. Nhưng queue có khóa nội bộ, nên **không phải lock-free** và không bảo đảm thời gian thực tuyệt đối. Vẫn cần đo cấp phát `Long`, `System.nanoTime()`, atomic counters, GC và CPU tranh chấp.

Lab giới hạn queue **256 phần tử**, dùng một exporter worker. Khi backlog kéo dài, event mới sẽ bị bỏ, không mở rộng RAM vô hạn.

## 2. Các số liệu cần tách biệt

| Metric | Định nghĩa | Chú ý |
| --- | --- | --- |
| `businessCalls` | Số lần thân `HotService.work` thật sự thực hiện trong pha đo | Không gộp các lời gọi warmup |
| `attempted` | Số event hook cố enqueue khi recording bật | Kiểm tra tính hiệu lực transformer |
| `accepted` | Event đã vào queue | **Chưa có nghĩa** gửi thành công |
| `dropped` | Event bị queue từ chối khi đầy | Loss theo chính sách |
| `exported` | Event được simulated sink xử lý thành công | Chỉ thành công trong mô phỏng |
| `failed` | Event được worker xử lý nhưng sink ném exception | Không tính là exported |
| `pending` | Event đã accepted nhưng chưa thành công/thất bại tại mốc thống kê | Có thể đang queued hoặc in-flight |
| `queued` | Số event vẫn nằm trong queue | Có thể nhỏ hơn pending một đơn vị |
| `latency p50/p95/p99` | Phân vị duration của business method được lấy mẫu | Không phải toàn bộ request latency |
| `throughput` | Business invocations hoàn tất mỗi giây của pha đo | Không trộn thời gian drain exporter |
| `drop rate` | `dropped/attempted` | Chỉ tính khi denominator lớn hơn 0 |
| `export lag` | Thời gian từ tạo event tới thành công ở collector | Lab chưa có collector thật |

Khi tất cả producer threads đã dừng, chúng ta kiểm tra:

```text
attempted == accepted + dropped
accepted  == exported + failed + pending
pending  >= 0
queued   <= 256

Agent mode:
  attempted == businessCallsMeasured

Không có agent:
  attempted = 0
```

**Vì sao pending không nhất thiết bằng queued?** Worker gọi `poll` lấy event khỏi queue rồi chờ/sleep/send. Event đó đã ở trạng thái **in-flight**, chưa được count `exported` hoặc `failed` nhưng cũng không còn trong queue.

### 2.1. Công thức overhead

```text
p99 overhead (%) =
  100 * (p99_agent - p99_baseline) / p99_baseline

Throughput degradation (%) =
  100 * (throughput_baseline - throughput_agent)
       / throughput_baseline

Drop rate (%) = 100 * dropped / attempted
```

Đây là **cách tính**, không phải số đo tự có. Cần đưa thêm **chênh lệch tuyệt đối**, số lượng mẫu, JDK/GC/CPU configuration và độ biến thiên giữa các lần chạy. Nếu baseline chỉ vài chục ns, `System.nanoTime()` và JIT/scheduler có thể gây nhiễu rất lớn.

## 3. Ma trận thí nghiệm

| Case | Agent | Exporter | Dấu hiệu cần thấy |
| --- | --- | --- | --- |
| A — baseline | Không | Không có queue events | Business đúng, `attempted=0` |
| B — fast | Có | `delayMs=0` | So overhead hook + queue + worker |
| C — slow | Có | `delayMs=10`/event | Queue đầy, loss và tail latency |
| D — stalled | Có | Chặn worker bằng `CountDownLatch` đến khi business xong | Loss xảy ra **chắc chắn** khi calls vượt capacity+1; business không block vì chờ queue |
| E — failure | Có | Lỗi một lần sau mỗi N send attempts | Worker tiếp tục, lỗi exporter không đổi return value |
| F — recovery | Có | Mở gate sau khi producer hoàn thành và cho drain có deadline | `exported` tiến triển, `pending` có thể giảm |

Điểm khác giữa slow và stalled: một worker chậm **vẫn tiến**, còn worker bị khóa không xuất được event nào trước khi mở gate. Case D làm drop deterministic, tránh viết test dựa trên giả định tốc độ CPU.

## 4. Dự án Java 17+ có agent và exporter thật sự được gọi

### 4.1. Cấu trúc

```text
slow-exporter-lab/
├── pom.xml
└── src/main/java/demo/
    ├── HotService.java
    ├── Probe.java
    ├── TraceAgent.java
    └── Bench.java
```

Cần JDK 17+, Maven 3.x và ASM dependencies từ Maven Central hoặc cache nội bộ. Không cần HTTP server hay mạng cho exporter mô phỏng. **Cùng một JAR** được chạy hai lần với hoặc không có `-javaagent`, giúp giữ nguyên business bytecode trước khi agent can thiệp.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>slow-exporter-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.TraceAgent</Premain-Class>
                  </manifestEntries>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

Maven Shade gộp `asm` và `asm-commons` để transformer hoạt động trong `premain`. Một agent JAR thiếu ASM trên classpath của agent có thể lỗi `NoClassDefFoundError` trước application `main`. Không cần `Can-Retransform-Classes` trong lab vì hook được gắn ở **load time**, không yêu cầu retransformation.

### 4.3. `src/main/java/demo/HotService.java`

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;

public final class HotService {
    private final AtomicLong calls = new AtomicLong();

    public long work(int input) {
        calls.incrementAndGet();
        return input * 31L + 7L;
    }

    public long calls() {
        return calls.get();
    }
}
```

`work(int)` rất nhỏ để overhead của hook dễ thấy. `AtomicLong` tăng bên trong business method giúp phát hiện trường hợp agent vô tình gọi lại method hoặc bỏ một invocation. Giá trị trả về là hàm xác định:

```text
Nếu một thread gọi work(i) với i = 0..n-1:
  checksum = 31 * n * (n - 1) / 2 + 7*n

Nếu T threads gọi cùng dãy:
  calls    = T*n
  checksum = T * (31*n*(n-1)/2 + 7*n)
```

Số `n` được giới hạn trong chương trình để phép tính `long` không overflow.

## 5. Bounded exporter: code và giải thích

### 5.1. `src/main/java/demo/Probe.java`

```java
package demo;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class Probe {
    public static final int CAPACITY = 256;

    private static final int DELAY_MS =
            Math.max(0, Integer.getInteger("export.delayMs", 0));
    private static final int FAIL_EVERY =
            Math.max(0, Integer.getInteger("export.failEvery", 0));
    private static final boolean STALLED =
            Boolean.getBoolean("export.stall");

    private static final ArrayBlockingQueue<Long> QUEUE =
            new ArrayBlockingQueue<>(CAPACITY);
    private static final LongAdder ACCEPTED = new LongAdder();
    private static final LongAdder DROPPED = new LongAdder();
    private static final LongAdder EXPORTED = new LongAdder();
    private static final LongAdder FAILED = new LongAdder();
    private static final AtomicLong SEND_ATTEMPTS = new AtomicLong();

    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicBoolean STOPPING = new AtomicBoolean();
    private static volatile boolean recording;
    private static final Thread WORKER;

    static {
        if (!STALLED) {
            RELEASE.countDown();
        }
        WORKER = new Thread(Probe::exportLoop, "demo-exporter");
        WORKER.setDaemon(true);
        WORKER.start();
    }

    private Probe() {}

    public static void beginRecording() {
        recording = true;
    }

    // Chạy trên business thread. Không đợi exporter.
    public static void onEntry() {
        if (!recording) {
            return; // bỏ qua warmup
        }
        if (QUEUE.offer(System.nanoTime())) {
            ACCEPTED.increment();
        } else {
            DROPPED.increment();
        }
    }

    private static void sendToSimulatedExporter(Long timestamp) {
        long n = SEND_ATTEMPTS.incrementAndGet();
        if (FAIL_EVERY > 0 && n % FAIL_EVERY == 0) {
            throw new IllegalStateException("simulated exporter failure");
        }
        // Event được giả lập là đã xử lý; không mở network.
    }

    private static void exportLoop() {
        while (!STOPPING.get() || !QUEUE.isEmpty()) {
            try {
                Long event = QUEUE.poll(50, TimeUnit.MILLISECONDS);
                if (event == null) {
                    continue;
                }
                RELEASE.await();
                if (DELAY_MS > 0) {
                    Thread.sleep(DELAY_MS);
                }
                sendToSimulatedExporter(event);
                EXPORTED.increment();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            } catch (RuntimeException exporterFailure) {
                FAILED.increment();
                // Lỗi exporter không ném sang business thread.
                // Worker tiếp tục xử lý event kế tiếp.
            }
        }
    }

    public record Snapshot(
            long accepted,
            long dropped,
            long exported,
            long failed,
            int queued) {

        public long attempted() {
            return accepted + dropped;
        }

        public long pending() {
            return accepted - exported - failed;
        }
    }

    public static Snapshot snapshot() {
        return new Snapshot(
                ACCEPTED.sum(), DROPPED.sum(),
                EXPORTED.sum(), FAILED.sum(), QUEUE.size());
    }

    public static Snapshot releaseAndStop(long waitMillis)
            throws InterruptedException {
        recording = false;
        RELEASE.countDown();
        STOPPING.set(true);
        WORKER.join(waitMillis);
        return snapshot();
    }
}
```

### 5.2. Tại sao không block?

`onEntry` chỉ gọi `offer`, không có `put`, `join` hoặc `sleep`. Trong điều kiện queue đầy, `offer` trả `false` và tăng `DROPPED`. Worker có ngủ 10 ms hay giữ gate cả phút thì business thread **không đợi capacity**.

Điều này không loại bỏ các chi phí khác: boxing `long` thành `Long`, `nanoTime`, locks ngắn của queue, `LongAdder` và scheduling/GC. Một thí nghiệm overhead vẫn phải đo CPU/latency trên máy cụ thể, không tự kết luận bằng 0.

### 5.3. Tại sao dùng gate và worker daemon?

`STALLED=true` khiến `CountDownLatch` khởi đầu ở 1; exporter có thể lấy tối đa một event khỏi queue rồi đợi `RELEASE.await()`. Khi workloads kết thúc, `releaseAndStop` gọi `countDown()`, cho phép exporter hoạt động trở lại.

Nếu đã có hơn `CAPACITY + 1` events được tạo, **chắc chắn ít nhất một event bị drop** khi gate còn đóng, bất kể worker đã kịp lấy event đầu tiên hay chưa. Đây là tiêu chí kiểm thử deterministic.

Worker là **daemon** và shutdown chỉ chờ một timeout hữu hạn. Nếu queue còn events khi JVM kết thúc, chúng **có thể bị mất**; `pending` phải được báo. Một in-memory daemon queue **không phải durable export system**.

### 5.4. Xử lý lỗi exporter

Khi `-Dexport.failEvery=4`, cứ lần gọi `sendToSimulatedExporter` thứ tư sẽ ném một `IllegalStateException` ở **worker thread**. Vòng lặp bắt `RuntimeException`, tăng `FAILED` rồi tiếp tục. Không retry nghiệp vụ. Với lỗi ngoài phạm vi như `OutOfMemoryError` hoặc crash native, **không thể đảm bảo fail-open tuyệt đối**; cần resource budget và health checks trong sản phẩm thật.

### 5.5. Kế toán event

Giả sử queue đầy và worker đã lấy một event nhưng chưa gửi:

```text
accepted = 257
exported = 0
failed   = 0
queued   = 256
pending  = 257
```

Đây là **một trạng thái minh họa**, không phải giá trị hardcode cho mỗi JVM. Nếu worker chưa được scheduler chạy, có thể `accepted=256` và `queued=256`. Do đó không nên assert `accepted==257` hay `pending==queued`.

Nếu worker được nhả và thành công gửi 100 events, pending giảm còn 157, **không thay đổi accepted**. Nếu nó gửi lỗi 10 events, `failed` tăng 10 và pending giảm 10. Không gộp `failed` vào `dropped`: một bên event vào queue rồi xử lý lỗi, bên còn lại event bị từ chối ngay.

## 6. ASM Java agent chỉ chọn method nghiệp vụ

### 6.1. `src/main/java/demo/TraceAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class TraceAgent {
    private TraceAgent() {}

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new HookTransformer());
    }

    private static final class HookTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> beingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"demo/HotService".equals(className)) {
                return null;
            }

            try {
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor =
                        new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access, String name, String desc,
                            String signature, String[] exceptions) {
                        MethodVisitor next = super.visitMethod(
                                access, name, desc,
                                signature, exceptions);

                        if (next == null
                                || !"work".equals(name)
                                || !"(I)J".equals(desc)) {
                            return next;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9, next, access,
                                name, desc) {
                            @Override
                            protected void onMethodEnter() {
                                visitMethodInsn(
                                        Opcodes.INVOKESTATIC,
                                        "demo/Probe",
                                        "onEntry",
                                        "()V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            } catch (RuntimeException transformerFailure) {
                // Không biến đổi; benchmark sẽ FAIL vì thiếu hook.
                return null;
            }
        }
    }
}
```

Các điểm QA:

- Agent `premain` đăng ký transformer **trước application main**.
- Chỉ instrument class có internal name `demo/HotService` và method `work(I)J`. Các helpers `Probe`/`Bench`/JDK classes không bị can thiệp.
- `AdviceAdapter` chèn đúng **một `INVOKESTATIC`** ở method entry. Không gọi lại nghiệp vụ, không thay return value.
- `ClassWriter.COMPUTE_MAXS` tính lại stack requirement cho thay đổi nhỏ này. Khi thêm branches/handlers hoặc đổi control flow phức tạp, cần xử lý frames/verifier phù hợp, không xem `COMPUTE_MAXS` là giải pháp tổng quát.
- `ClassFileTransformer` nhận `classfileBuffer` từ JVM; không được sửa nó trực tiếp. Trả một `byte[]` mới hoặc `null` nếu không transform.
- Java 17 vẫn hỗ trợ overload `transform` năm tham số; overload sáu tham số thêm `Module` trên JDK 9+ mặc định chuyển tiếp.
- Nếu transformer fail, JVM có thể tiếp tục với bytes cũ. Do đó app đo phải **assert số hook attempts bằng số business invocations** khi bật agent, không báo PASS giả khi agent không hoạt động.

Ở production, cần thêm kiểm tra class-loader identity, module visibility, tránh reentrant loading và idempotency nếu retransform nhiều lần. Lab chỉ thực hiện transform một lớp ở load time.

## 7. Chương trình đo với warmup, nhiều threads và assertions

### 7.1. `src/main/java/demo/Bench.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Bench {
    private static final int SAMPLE_EVERY = 32;

    private Bench() {}

    private record TaskResult(long checksum, long[] samples) {}

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError("Invariant failed: " + message);
        }
    }

    private static long percentile(
            long[] sorted, double fraction) {
        int index = Math.max(0,
                (int) Math.ceil(sorted.length * fraction) - 1);
        return sorted[index];
    }

    public static void main(String[] args) throws Exception {
        int threads = Integer.getInteger("bench.threads", 4);
        int n = Integer.getInteger("bench.ops", 20_000);
        boolean agent = Boolean.getBoolean("bench.agent");

        require(threads >= 1 && threads <= 16, "threads range");
        require(n >= 1 && n <= 250_000, "operations range");

        HotService service = new HotService();
        for (int i = 0; i < 20_000; i++) {
            service.work(i); // warmup, chưa ghi events
        }
        long beforeCalls = service.calls();

        if (agent) {
            Probe.beginRecording();
        }

        ExecutorService executor =
                Executors.newFixedThreadPool(threads);
        CountDownLatch gate = new CountDownLatch(1);
        List<Future<TaskResult>> futures = new ArrayList<>();

        for (int t = 0; t < threads; t++) {
            futures.add(executor.submit(() -> {
                long sum = 0;
                long[] samples = new long[
                        (n + SAMPLE_EVERY - 1) / SAMPLE_EVERY];
                int index = 0;
                gate.await();

                for (int i = 0; i < n; i++) {
                    if (i % SAMPLE_EVERY == 0) {
                        long start = System.nanoTime();
                        long value = service.work(i);
                        samples[index++] = System.nanoTime() - start;
                        sum += value;
                    } else {
                        sum += service.work(i);
                    }
                }
                return new TaskResult(
                        sum, Arrays.copyOf(samples, index));
            }));
        }

        long start = System.nanoTime();
        gate.countDown();

        int samplesPerWorker =
                (n + SAMPLE_EVERY - 1) / SAMPLE_EVERY;
        long[] latencies = new long[threads * samplesPerWorker];
        long sum = 0;
        int position = 0;

        try {
            for (Future<TaskResult> future : futures) {
                TaskResult r = future.get();
                sum += r.checksum();
                System.arraycopy(
                        r.samples(), 0, latencies, position,
                        r.samples().length);
                position += r.samples().length;
            }
        } finally {
            executor.shutdownNow();
        }

        long durationNanos = System.nanoTime() - start;
        long calls = service.calls() - beforeCalls;
        long expectedCalls = (long) threads * n;
        long expectedSum = (long) threads
                * (31L * n * (n - 1) / 2 + 7L * n);

        require(calls == expectedCalls, "business calls");
        require(sum == expectedSum, "business checksum");

        Arrays.sort(latencies);
        long p50 = percentile(latencies, 0.50);
        long p95 = percentile(latencies, 0.95);
        long p99 = percentile(latencies, 0.99);

        Probe.Snapshot beforeRelease = null;
        Probe.Snapshot afterDrain = null;

        if (agent) {
            beforeRelease = Probe.snapshot();
            long waitMs = Math.max(1,
                    Integer.getInteger("export.awaitMs", 250));
            afterDrain = Probe.releaseAndStop(waitMs);

            require(afterDrain.attempted() == expectedCalls,
                    "agent hook entries");
            require(afterDrain.accepted()
                    == afterDrain.exported()
                    + afterDrain.failed()
                    + afterDrain.pending(),
                    "event conservation");
            require(afterDrain.pending() >= 0,
                    "pending not negative");
            require(afterDrain.queued() <= Probe.CAPACITY,
                    "queue is bounded");

            if (Boolean.getBoolean("export.stall")
                    && expectedCalls > Probe.CAPACITY + 1) {
                require(afterDrain.dropped() > 0,
                        "stall must produce drops");
            }
        }

        double seconds = durationNanos / 1_000_000_000.0;
        double throughput = expectedCalls / seconds;

        System.out.println("MODE="
                + (agent ? "AGENT" : "BASELINE"));
        System.out.println("BUSINESS_CALLS=" + calls);
        System.out.println("CHECKSUM_OK=true");
        System.out.printf(Locale.ROOT,
                "LATENCY_NS=p50:%d,p95:%d,p99:%d%n",
                p50, p95, p99);
        System.out.printf(Locale.ROOT,
                "THROUGHPUT_OPS_PER_SEC=%.2f%n", throughput);

        if (agent) {
            System.out.println("PRE_RELEASE=accepted:"
                    + beforeRelease.accepted()
                    + ",dropped:" + beforeRelease.dropped()
                    + ",queued:" + beforeRelease.queued());
            System.out.println("EVENTS=attempted:"
                    + afterDrain.attempted()
                    + ",accepted:" + afterDrain.accepted()
                    + ",dropped:" + afterDrain.dropped()
                    + ",exported:" + afterDrain.exported()
                    + ",failed:" + afterDrain.failed()
                    + ",pending:" + afterDrain.pending()
                    + ",queued:" + afterDrain.queued());
        } else {
            System.out.println(
                    "EVENTS=attempted:0,accepted:0,dropped:0,"
                    + "exported:0,failed:0,pending:0,queued:0");
        }
        System.out.println("ASSERTIONS=PASS");
    }
}
```

### 7.2. Kiểm tra logic của benchmark

- **Warmup:** `service.work` chạy 20.000 lần trước khi bật `Probe.recording`; không cộng warmup vào `calls` của pha đo. Trên agent run, hook có thể đã được chèn nhưng `onEntry` trả ngay khi recording false.
- **Start gate:** worker threads cùng chờ `CountDownLatch` trước khi tính `durationNanos`; không đo lần lượt từng thread một cách chủ ý.
- **Giữ kết quả:** `checksum` tính từ giá trị `work` trả về; agent nếu gọi lại business hoặc sửa kết quả sẽ làm assertions fail.
- **Sampling:** chỉ 1 trong mỗi 32 invocations được đo elapsed time trực tiếp để giảm overhead measurement. Đây là latency của method được lấy mẫu, không phải end-to-end HTTP request.
- **Phân vị:** chương trình sort samples và lấy nearest-rank p50/p95/p99. Với lượng mẫu nhỏ kết quả tail thiếu ổn định; hãy tăng ops và dùng nhiều JVM forks.
- **Business throughput:** chỉ tính phần hoàn tất business tasks, không cộng thời gian `releaseAndStop` chờ exporter drain.
- **Kiểm tra hiệu lực agent:** khi `bench.agent=true`, `attempted == measured businessCalls`. Nếu thiếu `-javaagent`, benchmark fail thay vì báo overhead sai.
- **Stall deterministic:** khi gate đóng và events nhiều hơn 257, `dropped>0` phải đúng vì không có đường export trước khi nhả gate.

### 7.3. Chính xác đến đâu?

Code này là **thí nghiệm dạy cơ chế**, không phải bộ benchmark đạt chuẩn production: JIT, GC, timer resolution, CPU quotas, background processes, `AtomicLong` contention và safepoints vẫn gây nhiễu. Không kết luận overhead cố định theo ns từ một lượt chạy. Với microbenchmark nên dùng JMH; với service production cần load test request end-to-end.

## 8. Build và chạy từng case

Build một lần tại thư mục `slow-exporter-lab`:

```bash
mvn -q -DskipTests package
```

Maven Shade tạo JAR dự kiến `target/slow-exporter-lab-1.0.0.jar`. Lệnh tạo thành công khi có JDK17+, Maven 3.x và các dependencies. Các lệnh sau sử dụng **chính JAR đó**.

### 8.1. Baseline không agent

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Các dòng stdout **xác định theo logic**:

```text
MODE=BASELINE
BUSINESS_CALLS=80000
CHECKSUM_OK=true
```

Phía sau ba dòng ấy là `LATENCY_NS` và `THROUGHPUT_OPS_PER_SEC` với **số đo thực tế**. Cuối output:

```text
EVENTS=attempted:0,accepted:0,dropped:0,exported:0,failed:0,pending:0,queued:0
ASSERTIONS=PASS
```

Không có agent, không có event enqueue. Các giá trị latency/througput **không thể báo trước chính xác**.

### 8.2. Agent với exporter nhanh

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.delayMs=0 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Stdout bắt đầu:

```text
MODE=AGENT
BUSINESS_CALLS=80000
CHECKSUM_OK=true
```

Lệnh còn in `PRE_RELEASE` và `EVENTS`, trong đó `attempted=80000`; `accepted`, `dropped`, `exported`, `pending` do tốc độ producer/worker quyết định. **Ngay cả `delayMs=0`, queue 256 phần tử vẫn có thể đầy** nếu producer nhanh hơn exporter, nên không hứa `dropped=0`.

### 8.3. Agent với exporter chậm

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.delayMs=10 \
    -Dexport.awaitMs=3000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

`delayMs=10` mô phỏng khoảng 10ms mỗi event trên worker. Với 80k calls, worker thường chậm hơn nhiều so với producer và queue dễ đầy; nhưng không **hardcode số drops** vì scheduler/CPU/JIT có ảnh hưởng. Lệnh `export.awaitMs=3000` cho phép chờ drain tối đa 3 giây sau nghiệp vụ. Nếu `pending>0` khi hết thời gian, phải báo rõ backlog chưa xong.

### 8.4. Agent với exporter bị giữ hoàn toàn

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.stall=true \
    -Dexport.delayMs=10 -Dexport.awaitMs=4000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Khi `export.stall=true`, worker không thể gửi trước khi `Bench` gọi `releaseAndStop`, tức là **sau khi toàn bộ 80k business calls đã hoàn thành**. Queue chỉ chứa tối đa 256 và một event có thể in-flight. Vì vậy **`dropped>0` là bất biến xác định**; chương trình assert điều đó.

Sau mở gate, worker tiếp tục xử lý. Với thời gian chờ 4 giây và `delayMs=10`, backlog nhỏ có thể được giải quyết hết trên một máy ít nhiễu, nhưng nếu còn `pending` thì không được ghi là exported. Mục tiêu là kiểm tra **business không chờ exporter** trong pha đo và **export pipeline có đường phục hồi**, không ép số pending cố định.

### 8.5. Exporter ném lỗi theo tần suất

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.failEvery=4 \
    -Dexport.awaitMs=2000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Nếu worker xử lý ít nhất bốn events, `failed` sẽ tăng; nó vẫn xử lý các events tiếp theo theo loop `catch(RuntimeException)`. Business checksum và calls phải pass. `failed` không làm tăng `dropped` vì event đã được queue nhận và gửi thất bại ở worker.

**Windows PowerShell:** ghi các lệnh `java` trên một dòng thay vì dùng dấu `\` tiếp dòng của Bash. Không cần mở collector thật.

## 9. Phân tích bảng số đo

Điền kết quả **thực tế** sau khi chạy nhiều lần:

| Case | Throughput ops/s | p50 ns | p95 ns | p99 ns | Drop rate | Pending | Business PASS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A baseline | *đo* | *đo* | *đo* | *đo* | 0 | 0 | yes/no |
| B fast | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | yes/no |
| C slow | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | yes/no |
| D stalled | *đo* | *đo* | *đo* | *đo* | **>0** | *đo* | yes/no |
| E failure | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | yes/no |

Không điền số ms giả rồi tính tỷ lệ. Cần **nhiều JVM forks** và ghi rõ version/GC flags, warmup duration, sample count, CPU quota/heap. Vì một method quá nhỏ, overhead của `nanoTime`/sampling có thể đáng kể và diễn giải p99 khó; khi cần con số hiệu năng chính thức, bổ sung **JMH** và load test end-to-end.

### 9.1. Đọc pipeline accounting

Ví dụ **chỉ minh họa**, không phải output đã đo:

```text
attempted=1000
accepted=257
dropped=743
exported=200
failed=10
pending=47
```

Kiểm tra: `257 + 743 = 1000` và `200 + 10 + 47 = 257`. Nếu một report chỉ in `exported=200`, người đọc không biết đang có 743 events bị bỏ và 47 chưa xử lý. Nếu application p99 giữ tốt nhưng event loss cao, hãy báo **business được bảo vệ, telemetry fidelity giảm** chứ không tuyên bố mọi thứ ổn.

### 9.2. Mô hình tốc độ đến và tốc độ xử lý

```text
Arrival rate  λ = events/s do ứng dụng tạo
Service rate  μ = events/s exporter xử lý

λ < μ : backlog có thể giảm khi burst qua đi
λ > μ : backlog có xu hướng tăng tới capacity
        và cần drop, sampling hoặc block
```

Đây là mô hình đơn giản để suy luận saturation, không phải bảo đảm định lượng về scheduler/JVM. Với queue tăng vô hạn, tình trạng `λ > μ` kéo dài có nguy cơ gây `OutOfMemoryError`. Queue lớn hơn chỉ mua thêm **thời gian**, không giải quyết chênh lệch tốc độ bền vững.

## 10. Chọn backpressure policy theo dữ liệu

| Policy | Ảnh hưởng business | Ảnh hưởng telemetry | Phù hợp |
| --- | --- | --- | --- |
| **Drop newest** khi queue đầy | Không chờ capacity | Mất event mới, cần dropped metric | Tracing/metric chấp nhận sampling/loss |
| Drop oldest | Không chờ capacity nếu cài đúng | Mất event cũ, có bias | Chỉ khi policy cho phép |
| Block producer `put` | Có thể tăng p99/timeout | Giữ event tốt hơn trong giới hạn memory | Chỉ khi yêu cầu consistency cho phép |
| Timed offer | Chặn tối đa timeout mỗi event | Có thể drop sau timeout | Cần latency budget rõ |
| Head sampling | Giảm chi phí trước khi tạo event | Có sampling bias được công bố | Tải cao, cần cost control |
| Tail sampling | Quyết định sau khi thấy kết quả trace | Cần giữ state tạm thời, memory budget | Cần giữ rare errors/spans |
| Batching | Không chặn producer nếu ở worker | Có latency/event size tradeoff | Exporter network |
| Retry/backoff | Chỉ nên chạy trên exporter worker | Có thể tăng queue và duplicate attempts | Collector lỗi tạm thời |
| Durable WAL/outbox | Có chi phí transaction/disk | Có thể giữ events qua restart | Audit/financial compliance |

### 10.1. Tại sao không dùng queue vô hạn?

Một `LinkedBlockingQueue` không đặt capacity có thể tích backlog khi collector down hàng giờ. Mỗi event có thể giữ objects, strings, stack traces và classloaders; heap tăng, GC kéo dài, cuối cùng JVM chết. **Bounded queue** cùng drop/sampling/durable policy là một phần bảo vệ tài nguyên.

### 10.2. Event payload ảnh hưởng memory thế nào?

Lab chỉ dùng `Long` timestamp. Agent thật có thể giữ `Throwable` graph, request headers, user data, `Class<?>` hoặc servlet request object. Một event nặng 4 KiB và queue 100.000 phần tử đã cần hàng trăm MiB trước overhead của queue/GC. Đừng giữ references tới toàn bộ object graph khi chỉ cần một vài IDs và attributes đã redacted.

### 10.3. Recovery không đồng nghĩa “không mất dữ liệu”

Khi exporter hồi phục, các events **đã dropped** không tự quay lại. Nó chỉ xử lý những events còn accepted/pending hoặc được sinh về sau. Muốn giảm mất dữ liệu cần upstream sampling phù hợp, tăng capacity có kiểm soát, thêm worker/batching hoặc sử dụng storage bền vững. Không quảng cáo exactly-once chỉ nhờ retry: mất ACK có thể khiến một event được gửi nhiều lần.

## 11. Lỗi exporter không được đổi nghiệp vụ

Nếu hook ném exception trên request thread, caller có thể thấy lỗi telemetry thay vì business result. Trong lab, exporter failure được tạo **trên worker** và caught ở đó. `Probe.onEntry` chỉ enqueue; vẫn còn rủi ro ở static initialization/CPU/memory pressure mà thí nghiệm không chứng minh loại trừ tuyệt đối.

Ví dụ fragment đối lập:

```java
// Sai: sendBlocking có thể ném exception vào caller.
public static void badHook() {
    remoteExporter.sendBlocking(event);
}

// Mô hình tốt hơn khi policy là fail-open:
public static void safeHook() {
    boolean accepted = boundedQueue.offer(event);
    if (!accepted) {
        droppedCounter.increment();
    }
}
```

Đây là **pseudocode** vì `remoteExporter`, `event`, `boundedQueue` và `droppedCounter` chưa được định nghĩa trong file độc lập. Không được hiểu rằng `safeHook` tuyệt đối miễn nhiễm mọi `OutOfMemoryError`/`LinkageError`. Hãy khởi tạo helper sớm, giới hạn allocation, tránh recursive instrumentation và thiết kế health indicator.

**Tách retry:** retry event ở worker có thể hợp lệ; retry **business method** chỉ vì telemetry thất bại sẽ sinh thêm side effects và có thể rất nguy hiểm. Dữ liệu audit/transaction có yêu cầu cao phải theo một contract bền vững riêng.

## 12. So sánh microbenchmark và load test thật

### 12.1. Microbenchmark với JMH

Khi chỉ đo vài ns/call, benchmark tự viết có thể gặp JIT dead-code elimination, dead-code/code hoisting, timing resolution và sampling bias. **JMH** hỗ trợ forks/warmup/measurement và `Blackhole`; dùng nó để định lượng chi phí hook/queue/serialization ở cấp method.

Tuy nhiên JMH không thay thế load test toàn service với thread pool/HTTP/DB/network. Một hook chỉ thêm vài chục ns trong microbench vẫn có thể đẩy p99 request cao khi exporter chiếm CPU hoặc logging gây contention.

### 12.2. End-to-end load test

Bên cạnh toy lab, theo dõi:

- Request rate, completed requests/s, reject/timeout/error counts.
- Request latency p50/p95/p99/p99.9 theo loại endpoint.
- CPU utilization, throttling trong container, heap allocation/op và GC pauses.
- Export queue high-water mark, queue utilization, drops/s, failed sends/s.
- Export lag từ lúc tạo event tới collector acknowledgement.
- Thời gian drain backlog và số pending/lost lúc shutdown.
- Số business method calls, DB writes, messages và return/exception contract.

Kiểm thử nhiều chu kỳ: **healthy → slow → outage → recovery → shutdown**. Một exporter nhanh chỉ trong 10 giây đầu chưa cho biết hệ thống chịu outage 30 phút thế nào.

### 12.3. Thiết kế so sánh công bằng

Giữ cùng JDK vendor/version, GC/heap flags, CPU quota, inputs, artifacts và mức tải. Chạy nhiều forks, đảo thứ tự baseline/agent giữa các lần và tránh debug/profilers chỉ bật ở một nhóm. Báo median/band trên các runs, không chọn một run đẹp nhất. Lưu lại khi container CPU bị throttled hoặc GC pause bất thường.

## 13. Kiểm thử exception, async và concurrency

Thêm vào lab các biến thể nghiệp vụ:

1. **Method ném ngoại lệ:** kiểm tra `Throwable` type/message/cause theo hợp đồng vẫn giữ nguyên khi exporter fail. Hook entry-only vẫn phải không tạo exception thay thế.
2. **Method trả `CompletableFuture`:** lỗi xuất event không được `join` future trên request thread, thay kết quả hoặc thay cancellation/exceptional completion.
3. **Nhiều business threads:** với 4/8/16 threads, `AtomicLong` count và checksum vẫn chính xác; `LongAdder` event metrics không được mất do race trong counter.
4. **Method đệ quy:** một logical request có thể tạo nhiều method-entry events. Phân biệt **invocations** với **requests** để tính sampling.
5. **Transformer lặp:** nếu retransform sau load, bảo đảm không chèn cùng hook hai lần. Lab chỉ load-time, không tự chứng minh idempotency.
6. **Exporter reentrant:** không instrument chính `Probe` hoặc logging helper, nếu không có thể tạo recursion/`StackOverflowError` hoặc deadlock.
7. **Tắt exporter:** nếu worker chết, producer vẫn phải có timeout/queue policy rõ, không lặng lẽ tiêu thụ vô hạn RAM.

Đồng thời hãy test cả return value, static/instance state và external effects. Latency tốt không phải bằng chứng business correctness.

## 14. Những giới hạn của lab cần nói rõ

- **Không có exporter HTTP thật:** `Thread.sleep` và injected `RuntimeException` không mô phỏng mọi network failure, TLS handshake, retry jitter, 429/503, partial ACK hay duplicate delivery.
- **Không có độ bền:** daemon thread + queue RAM có thể mất pending khi JVM dừng/crash.
- **Không có hard real-time:** `offer` không đợi capacity nhưng có lock tranh chấp và allocation/JIT/GC.
- **Không đo tất cả calls:** latency chỉ được sample mỗi 32 invocations; call counts thì tính đủ.
- **Warmup chưa bảo đảm steady-state:** JIT, GC và branch profile có thể tiếp tục thay đổi.
- **Một service rất ngắn:** `AtomicLong` và hook có thể chiếm tỷ trọng lớn hơn ứng dụng thực.
- **Shutdown bounded:** nếu `pending>0` sau `join(timeout)`, worker daemon còn chạy cho tới process exit; không coi đó là flush hoàn tất.
- **Mẫu process riêng:** mỗi case Java command bắt đầu JVM mới. Không so số `nanoTime` tuyệt đối giữa processes; chỉ tính durations.
- **Không thử fatal VM errors:** fail-open chỉ được chứng minh cho những lỗi exporter mô phỏng trên worker, không phải lỗi bộ nhớ/hệ điều hành nặng.
- **Không xác nhận một con số overhead trước khi thực chạy:** stdout time phụ thuộc máy, cần tự đo.

## 15. Chẩn đoán hiện tượng bất thường

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `bench.agent=true` nhưng attempted=0 | Hook không được cài, sai manifest/name hoặc transformer fail | `-javaagent`, `Premain-Class`, ASM transform; assertion phải fail |
| Business p99 tăng cùng exporter delay | Export đồng bộ, `put`, `get`, `join`, lock hoặc sync logging trên request | Thread dump và call path producer |
| Throughput giảm dù p99 mẫu ổn | CPU/GC/queue contention ngoài sampled calls | CPU/op, allocations, throughput end-to-end |
| `attempted != businessCalls` | Hook thiếu/trùng, warmup tính sai, sample policy khác | Method owner/descriptor và recording window |
| `accepted + dropped != attempted` | Hạch toán sai hoặc snapshot cạnh tranh | Đo sau producers hoàn tất, phân biệt attempts |
| `accepted != exported + failed + pending` | Bỏ event không hạch toán, retry trùng, snapshot sai | Trạng thái in-flight, counters, terminal outcomes |
| `queued != pending` | Có event đang trong worker | Đây có thể là hợp lệ |
| Không drop khi exporter stall | Gate mở quá sớm, recording chưa bật hoặc hook không chạy | Kiểm tra `export.stall`, số calls, capacity |
| Worker chết sau một exporter exception | `catch` ở sai phạm vi hoặc lỗi không bắt | Exception handling theo event, worker health |
| `failed=0` trong failure case | Chưa có đủ send attempts hoặc worker chưa được nhả | `export.awaitMs`, send attempts và queue |
| Agent gây `VerifyError` | Sai ASM frames/stack/method descriptor | `-Xverify:all`, test VM đích |
| Agent làm business counter tăng gấp đôi | Instrumenter gọi lại method, hook chèn trùng | Dump class bytes, method count |
| JVM hết heap | Unbounded queue/payload lớn hoặc leak classloader | Bounded capacity, heap dump, allocation analysis |
| Recovery chậm dù backend khỏe | Backlog lớn hoặc retry storm | Pending age, batching và concurrency |
| Shutdown treo | Chờ flush vô hạn | Deadline và loss reporting |
| Drop ít nhưng error nhiều | Worker liên tục failed sends | Thêm backoff/circuit breaker/alerts |
| Drop nhiều nhưng business vẫn PASS | Fail-open đúng về nghiệp vụ, fidelity của telemetry kém | Báo cả hai mặt; chỉnh sampling/capacity |
| Output số đo không ổn định | JIT/GC/CPU noise/samples nhỏ | Tăng workload, nhiều forks và JMH |

## 16. Checklist thực nghiệm

- [ ] Có baseline không agent và agent fast; dùng cùng JAR/JDK/configuration.
- [ ] Có slow exporter, stalled exporter và failure injection.
- [ ] Business return/checksum/call count vẫn đúng ở mọi case.
- [ ] Agent mode phải có `attempted == businessCallsMeasured`, tránh PASS giả.
- [ ] Queue có capacity hữu hạn và phân biệt `offer` với `put`.
- [ ] Có đếm riêng attempted/accepted/dropped/exported/failed/pending.
- [ ] Stalled exporter với >257 events làm `dropped>0`, không giữ business thread chờ capacity.
- [ ] Sau mở gate, worker có đường tiếp tục; pending được báo chứ không giả thành exported.
- [ ] Exporter exception không truyền sang business thread.
- [ ] Không chạy lại business method để retry telemetry.
- [ ] Đo throughput và p50/p95/p99 trong pha nghiệp vụ; tách drain time.
- [ ] Bảo đảm warmup/sampling/forks được ghi rõ.
- [ ] Đo CPU allocation/GC và contention, không chỉ xem latency.
- [ ] Với tracing production, đo event lag, collector ACK và drop rate.
- [ ] Có rate limiting, backoff, sampling hay circuit breaker phù hợp.
- [ ] Với audit không được mất event, không dùng in-memory drop queue thay durable storage.
- [ ] Có timeout shutdown, health alert và khả năng disable/rollback agent.
- [ ] Test nhiều agents/retransform để loại duplicate hooks.
- [ ] Bảo vệ event payload không chứa secrets hoặc giữ request objects quá lâu.
- [ ] Không tuyên bố số nanosecond đã đo khi chưa có thực nghiệm.

## 17. Câu hỏi tự kiểm tra

1. **Exporter chậm 500ms mà hook gọi `sendBlocking` trên request thread: có tác động?**  
   Có. Latency business có thể chịu gần như toàn bộ thời gian đợi, gây timeout/thread starvation.

2. **`ArrayBlockingQueue.offer` có block khi đầy giống `put` không?**  
   Không chờ capacity; nó trả `false`. Nhưng vẫn có lock overhead ngắn, không phải lock-free.

3. **`attempted=1000, accepted=257, dropped=743` có hợp lệ không?**  
   Có: 257+743=1000. Cần xem exported, failed, pending của 257 accepted.

4. **`accepted=257, exported=200, failed=10` thì `pending` bằng bao nhiêu?**  
   47; không được báo 257 events đã gửi thành công.

5. **Vì sao `pending` lớn hơn `queueSize`?**  
   Worker có thể đã poll một event khỏi queue và đang xử lý nó.

6. **Tại sao stalled gate tạo dropped>0 chắc chắn khi có 80k calls?**  
   Queue chỉ 256, worker bị giữ nên tối đa thêm một event in-flight; những events còn lại không có chỗ.

7. **Exporter failure có nên retry business method không?**  
   Không. Retry phải ở telemetry delivery, không gây side effect nghiệp vụ lần hai.

8. **Một agent với `delayMs=0` có chắc drop=0?**  
   Không. Producers có thể vượt tốc độ worker dù không sleep.

9. **Vì sao không cộng 4 giây drain vào throughput business?**  
   Ta muốn đo tốc độ hoàn tất method nghiệp vụ; exporter flush là metric riêng.

10. **Nếu worker gửi event thất bại và tiếp tục, có thể bảo toàn business không?**  
    Có trong policy fail-open cho lỗi đã xử lý trên worker; cần kiểm tra business assertions và resource pressure.

11. **JMH có thay load test HTTP end-to-end không?**  
    Không. JMH đo micro-cost, còn tail request latency liên quan thread pool/GC/network/concurrency.

12. **Queue vô hạn giúp tránh drops, có chắc tốt hơn không?**  
    Không. Khi exporter mất kết nối lâu, backlog có thể ăn hết heap và làm ứng dụng sập.

13. **`pending=0` có chứng minh chưa mất event nào?**  
    Không. Có thể nhiều events đã `dropped` hoặc `failed`; phải xem tất cả counters.

14. **Vì sao status "agent loaded" không chứng minh đã có overhead đo chính xác?**  
    Transformer có thể không chọn đúng class hoặc fail; cần assert probe attempts khớp business invocations.

15. **Nếu app dùng tracing sampling, `attempted` nên có nghĩa gì?**  
    Định nghĩa rõ đó là hook attempts hay event candidates sau sampling; tách `sampledOut` khỏi capacity dropped.

16. **Với audit bắt buộc không mất, có nên bỏ event khi queue đầy để giữ p99?**  
    Không tự quyết định. Phải dùng durable pipeline/transactional outbox và chính sách giao dịch/latency được phê duyệt.

17. **Overhead âm trong một benchmark run có chứng minh agent tăng hiệu năng?**  
    Không. Đó có thể là JIT/GC/scheduler noise; cần nhiều forks và phân tích độ biến thiên.

18. **Có thể coi exporter hồi phục nếu chỉ log một dòng “resumed”?**  
    Không. Cần thấy exported tiến, pending giảm, business giữ SLA và loss accounting đúng.

## 18. Tài liệu chuẩn

1. Oracle JDK 17 — **`ArrayBlockingQueue`** và `offer`/`put`/`poll`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
2. Oracle JDK 17 — **`CountDownLatch`**, one-shot gate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
3. Oracle JDK 17 — **`ClassFileTransformer`**, `classfileBuffer`, return `null` hoặc bytes mới: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. Oracle JDK 17 — **`Instrumentation`**, `addTransformer`, retransform rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
5. Oracle JDK 17 — **`java.lang.instrument` package**, `Premain-Class` và `premain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
6. Oracle JDK 17 — **`LongAdder`**, counters đa luồng: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
7. Oracle JDK 17 — **`Future`/`ExecutorService`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
8. Oracle JDK 17 — **`System.nanoTime()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
9. ASM — **`AdviceAdapter`**, `ClassWriter` và visitor API: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
10. ASM — versions/releases: https://asm.ow2.io/
11. OpenJDK **JMH** microbenchmark: https://github.com/openjdk/jmh
12. Oracle JDK 17 — **`ThreadPoolExecutor`**, unbounded/bounded queues: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html

**Kết luận:** Để agent có thể chịu exporter chậm, phải thiết kế **bounded queue, backpressure policy cụ thể, tách lỗi exporter khỏi business path, hạch toán event loss/pending và shutdown có deadline**. Đo bằng baseline/fast/slow/stalled/failure runs, kiểm tra business correctness và latency/throughput cùng lúc. Khi exporter hồi phục, chỉ những events còn accepted/pending mới có thể tiếp tục gửi; events đã dropped **không tự quay lại**.
