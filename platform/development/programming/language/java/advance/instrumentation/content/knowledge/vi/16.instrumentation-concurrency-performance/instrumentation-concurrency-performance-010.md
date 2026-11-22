# Đo overhead bằng nhóm chạy có agent và không có agent trong cùng điều kiện

**Câu hỏi kỹ thuật:** Sau khi thêm một Java instrumentation agent vào JVM bằng `-javaagent`, ứng dụng mất bao nhiêu hiệu năng? Một số liệu như “agent chậm 7%” chỉ có ý nghĩa nếu biết **7% của đại lượng nào**, workload nào, phiên bản JVM nào, độ đồng thời bao nhiêu, agent bật những probes nào và kết quả có vượt nhiễu đo hay không.

Phương pháp cốt lõi là một **thí nghiệm A/B có nhóm đối chứng**:

- **A – No agent:** cùng ứng dụng, JVM được khởi động **không có `-javaagent`**.
- **B – With agent:** chính ứng dụng đó, cùng cấu hình, **có `-javaagent` và instrumentation thực sự hoạt động**.
- **Giữ mọi biến khác tương đương:** JDK, JVM flags, code artifact, dữ liệu, tài nguyên máy, request mix, độ đồng thời, warm-up, cửa sổ đo, backend.
- **Chạy nhiều JVM độc lập**, xen kẽ hoặc randomize thứ tự A/B, ghi số liệu theo cặp và đánh giá cả biến thiên.
- **Xác nhận tính đúng đắn:** hai nhóm phải hoàn thành cùng loại công việc với cùng chất lượng, lỗi, kết quả/checksum; một nhánh bỏ qua công việc không được gọi là “nhanh hơn”.

Bài học này đi từ thiết kế phép thử, định nghĩa **startup/steady-state/throughput/latency/memory/GC overhead**, công thức so sánh đến một **benchmark Java 17+ chạy được**: agent dùng `ClassFileTransformer` đổi một đường gọi từ no-op sang probe `LongAdder`, còn app JAR **giữ nguyên 100% giữa hai nhóm**. Cuối bài là quy trình chạy nhiều process, cách phân tích số liệu và các sai lầm thường gặp khi đo Java instrumentation.

## 1. Overhead không phải một con số duy nhất

Một agent có thể tác động đến nhiều thành phần:

| Chỉ số | Đo thứ gì? | Đơn vị thường dùng |
|---|---|---|
| Startup duration | Từ lúc start JVM đến lúc sẵn sàng phục vụ | ms, s |
| Latency / duration | Thời gian hoàn thành một operation/request | ns, µs, ms |
| p50/p95/p99 latency | Phân bố latency, đặc biệt những request chậm nhất | ms |
| Throughput | Số operations/requests thành công mỗi giây | ops/s, req/s |
| CPU time | Tổng thời gian CPU dùng để hoàn thành lượng việc | CPU-s / 1.000 req |
| CPU utilization | Mức sử dụng CPU ở một tải xác định | % |
| Allocation rate | Tốc độ tạo object/telemetry data | bytes/op, MiB/s |
| GC impact | Tần suất GC, pause time, tác động tới latency | count, ms |
| Heap / metaspace / RSS | Các lớp sử dụng bộ nhớ khác nhau | MiB |
| Class-loading / transformer time | Chi phí tải/parse/biến đổi/verify class | ms, số class |
| Exporter impact | Buffering, logging, network, retry và dropped events | events/s, bytes/s, % |

Một lời kết luận đầy đủ có thể là: **“Ở cùng offered load 500 req/s, B tăng p95 latency 4% và CPU/1.000 req 7%; startup chậm thêm 250 ms, error rate không đổi.”** Đây là **ví dụ định dạng báo cáo**, không phải kết quả đo của bài.

Phải đặt câu hỏi **trước khi đo**: bạn cần đánh giá hot-path overhead per method, latency của service dưới load, chi phí startup hay capacity lúc bão hòa? Những phép thử khác nhau có thể cho kết quả khác nhau mà không mâu thuẫn.

## 2. Hai nhóm phải thực sự “giống nhau trừ agent”

Đây là bảng preflight cho phép thử công bằng:

| Yếu tố | Quy tắc A/B |
|---|---|
| Application build | **Cùng app JAR, class files và Git commit** |
| JVM | Cùng Java vendor, Java version, architecture, JIT và GC implementation |
| Heap / GC flags | Cùng `-Xms`, `-Xmx`, GC collector, module flags, tuning flags |
| CPU/memory limits | Cùng machine type, số vCPU, cgroup quota, RAM |
| Payload và dữ liệu | Cùng seed, data snapshot, request mix, DB state |
| Throughput driver | Cùng arrival rate, connections, worker threads, think time |
| Agent | Chỉ B thêm **đúng agent JAR**, cùng config sampling/exporter/filter |
| Warm-up | Cùng chính sách warm-up và tiêu chí đánh giá ổn định |
| Measurement | Cùng thời lượng, nguồn timestamp, công cụ đo và unit |
| Network/backend | Cùng topology, cache policy và phiên bản dependencies |
| Background noise | Theo dõi tiến trình nền, CPU throttling, nhiệt độ, scaling |
| Correctness | Cùng checksum, success count, error/timeout policy |

Điều kiện phải thay đổi có chủ đích là **agent có mặt hay không**. Bản thân “agent có mặt” có thể làm nạp thêm class/JAR, tạo thread và sửa JIT; tất cả đều là phần effect cần đo. Không được che effect thật bằng cách tắt từng thành phần tùy tiện sau đó tuyên bố đó là full-agent overhead.

**Sai lầm dễ gặp:** chạy A trên JDK 17 với heap 512 MiB nhưng B trên JDK 24 với heap 2 GiB. Chênh lệch có thể do GC/JIT và memory pressure, không thể quy cho agent.

Khi không thể giữ hạ tầng tuyệt đối giống nhau, phải ghi điều kiện khác biệt, dùng **matching, randomization hoặc hoán đổi host**, thay vì giả định nguyên nhân đã được kiểm soát.

## 3. Baseline thật không được nạp agent

Ba trạng thái cần phân biệt:

~~~text
A. no-agent
    JVM không có -javaagent, không load Agent JAR.

B0. agent-loaded nhưng probe disabled
    JVM vẫn load agent, chạy premain, có thể có helper/exporter threads.

B1. agent-loaded, probe enabled
    JVM chạy premain, transform class, hot path được instrument.
~~~

**B0 không phải A**. Chuyển `agent.enabled=false` ở runtime chỉ có thể đánh giá chi phí bật/tắt probe, **không** xóa overhead của agent startup, classloader, background tasks hoặc những biến đổi đã xảy ra.

Để trả lời câu hỏi đề bài, phép đo chính phải là **A so với B1 theo đúng cấu hình agent sẽ dùng thực tế**. B0 là nhóm điều tra bổ sung giúp phân tách chi phí.

Một thí nghiệm trên cùng JVM “tắt agent lúc 10:00, bật lúc 10:05” còn bị ảnh hưởng bởi JIT/GC state cũ, class đã transform và SDK threads. **Dùng process JVM mới cho mỗi run**.

## 4. Tách startup overhead và steady-state overhead

`Premain-Class` trong manifest được JVM gọi **trước application `main`** khi dùng `-javaagent`.

Khi startup, agent có thể:

- Tải agent JAR và dependencies.
- Đăng ký `ClassFileTransformer` và parse/generate class files.
- Tải helper classes, mở exporter/scheduler threads.
- Làm thay đổi class loading, verification, JIT warm-up và metaspace.
- Yêu cầu module reads/opens, bootstrap helper paths hoặc hỗ trợ retransform.

**Startup benchmark** phải có thời điểm bắt đầu **bên ngoài process JVM** (launcher/process orchestrator), rồi đợi **readiness signal**. Bắt đầu `System.nanoTime` ở đầu `main` **không bao gồm `premain`**, vì vậy không đo đủ startup overhead.

**Steady-state benchmark** warm up và chờ workload ổn định rồi mới đo:

~~~text
A: process launch → class loading → warm-up → [measurement] → stop
B: process launch → premain + transform → warm-up → [measurement] → stop
                    ^ startup riêng                 ^ steady-state
~~~

Có thể có **cold-start**, **warm-start**, **first-request** và **steady-state** metrics khác nhau. Đừng trộn chúng vào cùng một giá trị ms/op nếu mục tiêu là so chi phí hot path.

## 5. Công thức overhead theo đúng mẫu số

Với **latency/time per operation**:

~~~text
A = trung bình hoặc trung vị thời gian/op của nhóm không agent
B = cùng định nghĩa ở nhóm có agent

delta = B - A
time_overhead_% = 100 × (B / A - 1)
~~~

Với **throughput**:

~~~text
Q_A = operations/second không agent
Q_B = operations/second có agent

throughput_loss_% = 100 × (1 - Q_B / Q_A)
~~~

Đặt điều kiện A và Q_A phải dương; các metric phải có cùng unit và đo cùng workload.

**Ví dụ số học giả định**:

~~~text
Q_A = 20.000 ops/s
Q_B = 18.000 ops/s

Sụt throughput = 100 × (1 - 18.000 / 20.000) = 10%

Thời gian trung bình mỗi op:
A ≈ 50 µs/op
B ≈ 55,56 µs/op

Tăng thời gian/op ≈ 100 × (20.000/18.000 - 1) = 11,11%
~~~

**10% sụt throughput không bằng 10% tăng thời gian/op**, vì mẫu số khác nhau. Nếu đo **p95 latency**, không lấy nghịch đảo của p95 để tính throughput; trong dịch vụ có queue/concurrency, các đại lượng đó không có quan hệ nghịch đảo đơn giản.

### Đừng làm tròn trước khi tính

Giữ `elapsedNanos` và `operations` ở độ chính xác gốc, rồi tính:

~~~text
ns_per_op = elapsedNanos / operations
ops_per_second = operations × 1_000_000_000 / elapsedNanos
~~~

Với `elapsedNanos <= 0` (do cửa sổ đo quá ngắn hoặc dữ liệu lỗi), **bỏ sample đó theo quy tắc lỗi đã đặt trước** và kéo dài workload. Không gán nó thành `Infinity ops/s`.

## 6. Warm-up: không biến thời điểm JIT đang học thành kết luận

Đặc tính Java/JVM khiến benchmark ngắn rất dễ sai:

- Ban đầu code có thể chạy interpreted/C1, sau đó JIT C2, inlining và optimization thay đổi.
- Bật agent có thể thêm `invokestatic`, tạo object, ảnh hưởng escape analysis hoặc inlining.
- Transformer có thể được gọi khi class load, làm xuất hiện class initialization và verification trong lần đo đầu.
- GC phụ thuộc allocation history và heap occupancy.
- CPU frequency scaling, thermal throttling, OS scheduling gây dao động.
- Nếu kết quả tính toán bị compiler nhận ra là không được sử dụng, JIT có thể loại bỏ phần lớn workload.

Vì vậy:

1. **Warm-up đúng workload**, không warm-up bằng một vòng lặp khác hành vi.
2. Giữ warm-up policy nhất quán A/B; nếu B cần thời gian ổn định lâu hơn, hãy ghi riêng.
3. Dùng các **measurement windows đủ dài**, không đo một lần gọi rồi báo ns/op.
4. Tạo **nhiều JVM forks độc lập**, không chỉ 100 iterations trong một process.
5. Đảm bảo có observable result/Blackhole để tránh dead-code elimination.
6. Đừng lọc bỏ một sample “vì xảy ra GC” nếu GC chính là effect mà agent gây ra.
7. Dùng **JMH** cho microbenchmark cần độ tin cậy ở mức nanosecond; vòng tự viết chỉ là minh họa.

## 7. Mỗi lần chạy A/B phải là một JVM riêng

Một trình tự sai:

~~~text
A A A A A A
B B B B B B
~~~

Nếu laptop nóng dần, CPU bị giới hạn hoặc backend load tăng theo thời gian, B có thể bị bất lợi chỉ vì chạy sau.

Trình tự tốt hơn:

~~~text
Pair 1: A → B
Pair 2: B → A
Pair 3: A → B
Pair 4: B → A
...
~~~

Hoặc hoán đổi ABBA / BAAB, randomize order với seed cố định để tái lập. Mỗi **pair** gồm hai **tiến trình JVM mới**. Nếu có hai host tương đương, có thể chạy A và B song song **trên hai host tách tài nguyên**, sau đó hoán đổi arm giữa các host; không nên đặt hai JVM tranh cùng CPU quota nhỏ rồi quy chênh lệch cho agent.

**Đơn vị thống kê độc lập chủ yếu là fork/pair**, không phải mỗi operation trong cùng một fork. Nếu một JVM gọi `compute` 5.000.000 lần, đó không phải 5.000.000 quan sát độc lập về “tác động của agent” vì chúng chia sẻ JIT, heap, OS và thread scheduling.

## 8. Ví dụ runnable Java 17+: một agent thực sự thay đổi hot path

Thí nghiệm dùng **app JAR không thay đổi** giữa hai nhóm. Class `lab.Work` luôn gọi `Hook.empty()` theo source. Ở nhóm B, agent có `ClassFileTransformer` sửa đúng một constant-pool entry tên method từ **`empty` → `count`** (hai tên ASCII đều 5 byte), khiến JVM thực sự gọi `Hook.count()` và tăng `LongAdder`.

Nó đo được chi phí của **một probe được bật bằng bytecode transformation**, đồng thời chứng minh kết quả tính toán vẫn tương đương. Đây là **điểm chèn có sẵn**, khác với agent production có khả năng chèn thêm toàn bộ method instructions. Bài học không coi parser đơn giản này là công cụ bytecode production.

Cấu trúc:

~~~text
overhead-lab/
├── src/
│   ├── app/lab/
│   │   ├── Hook.java
│   │   ├── Work.java
│   │   └── BenchMain.java
│   └── agent/agent/
│       ├── CpPatch.java
│       └── ProbeAgent.java
├── AGENT.MF
└── out/
    ├── app/
    └── agent/
~~~

### 8.1. `src/app/lab/Hook.java`

~~~java
package lab;

import java.util.concurrent.atomic.LongAdder;

public final class Hook {
    private static final LongAdder EVENTS = new LongAdder();

    private Hook() { }

    public static void empty() { }

    public static void count() {
        EVENTS.increment();
    }

    public static long calls() {
        return EVENTS.sum();
    }
}
~~~

`empty()` không có side effect và được JVM/JIT tối ưu rất mạnh. `count()` tạo side effect lên một `LongAdder`. Với bài đo **đơn luồng**, ta đọc counter sau khi workload kết thúc. Trong ứng dụng đồng thời, `LongAdder.sum()` không phải snapshot atomic nếu các thread vẫn đang increment, nên chỉ dùng counter để xác minh khi tất cả worker đã xong.

### 8.2. `src/app/lab/Work.java`

~~~java
package lab;

public final class Work {
    private Work() { }

    public static long compute(int value) {
        long x = value * 0x9E3779B1L + 17;
        x ^= x >>> 13;
        x *= 0x85EBCA6BL;
        x ^= x >>> 16;
        Hook.empty();
        return x;
    }
}
~~~

Mọi phép toán trả kết quả không phụ thuộc việc increment counter. Dùng checksum để kiểm tra A/B làm cùng phần tính toán. **Không phải** một ứng dụng thực tế có sẵn instrumentation production; đây là mô hình đơn giản để quan sát overhead.

### 8.3. `src/app/lab/BenchMain.java`

~~~java
package lab;

import java.util.Locale;

public final class BenchMain {
    private static volatile long sink;

    private static long round(int operations, int seed) {
        long sum = 0;
        for (int i = 0; i < operations; i++) {
            sum += Work.compute(i ^ seed);
        }
        sink = sum;
        return sum;
    }

    public static void main(String[] args) {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: BenchMain <label> <operations> <warmups> <samples>");
        }
        String label = args[0];
        int operations = Integer.parseInt(args[1]);
        int warmups = Integer.parseInt(args[2]);
        int samples = Integer.parseInt(args[3]);
        if (operations <= 0 || warmups < 0 || samples <= 0) {
            throw new IllegalArgumentException("invalid run config");
        }

        for (int w = 0; w < warmups; w++) {
            round(operations, 1000 + w);
        }

        for (int s = 0; s < samples; s++) {
            long start = System.nanoTime();
            long checksum = round(operations, 2000 + s);
            long elapsed = System.nanoTime() - start;
            double throughput = operations * 1_000_000_000.0 / elapsed;
            System.out.printf(Locale.ROOT,
                    "RESULT,%s,%d,%d,%d,%.2f,%d%n",
                    label, s + 1, operations, elapsed, throughput, checksum);
        }
        System.out.println("HOOK_CALLS=" + Hook.calls());
        System.out.println("SINK=" + sink);
    }
}
~~~

**Giải thích hành vi:**

- `round` chạy đúng số `operations` đã được cung cấp. `seed` của sample xác định dữ liệu đầu vào và **giống nhau giữa A/B cùng sample index**.
- `System.nanoTime()` là nguồn elapsed tương đối **trong cùng JVM**; chỉ hiệu `end-start` có ý nghĩa.
- `warmups` chạy thật nhưng không in `RESULT`. Chi phí warm-up vẫn nằm trong `HOOK_CALLS`.
- Kết quả phép tính được dùng để tính `checksum`, rồi ghi vào `volatile sink` nhằm giảm nguy cơ dead-code elimination. Đây vẫn chưa phải harness tối ưu như JMH.
- In `RESULT` nằm **ngoài phần đo** để không đưa chi phí console I/O từng sample vào elapsed. Đừng in mỗi operation.
- Mỗi dòng `RESULT` gồm: marker, label A/B, sample, operations, `elapsedNs`, `opsPerSec`, checksum. `elapsedNs` và `opsPerSec` **không ổn định** giữa các lần chạy.
- Với 200.000 ops, 2 warmups và 2 measured samples, B phải ghi **800.000 probe calls**, A phải ghi **0**.

### 8.4. `src/agent/agent/CpPatch.java`

~~~java
package agent;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CpPatch {
    private CpPatch() { }

    public static byte[] replaceUtf8(
            byte[] source, String before, String after) {
        byte[] oldBytes = before.getBytes(StandardCharsets.UTF_8);
        byte[] newBytes = after.getBytes(StandardCharsets.UTF_8);
        if (oldBytes.length != newBytes.length) {
            throw new IllegalArgumentException("length mismatch");
        }

        byte[] result = source.clone();
        ByteBuffer b = ByteBuffer.wrap(result);
        if (b.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not a class");
        }
        b.getShort();
        b.getShort();
        int count = Short.toUnsignedInt(b.getShort());
        int changed = 0;

        for (int i = 1; i < count; i++) {
            int tag = Byte.toUnsignedInt(b.get());
            switch (tag) {
                case 1 -> {
                    int length = Short.toUnsignedInt(b.getShort());
                    int offset = b.position();
                    if (length == oldBytes.length
                            && Arrays.equals(
                                Arrays.copyOfRange(
                                    result, offset, offset + length),
                                oldBytes)) {
                        System.arraycopy(
                                newBytes, 0, result, offset, length);
                        changed++;
                    }
                    b.position(offset + length);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                    b.position(b.position() + 4);
                case 5, 6 -> {
                    b.position(b.position() + 8);
                    i++;
                }
                case 7, 8, 16, 19, 20 ->
                    b.position(b.position() + 2);
                case 15 ->
                    b.position(b.position() + 3);
                default -> throw new IllegalArgumentException(
                        "unexpected constant pool tag " + tag);
            }
        }
        if (changed != 1) {
            throw new IllegalArgumentException(
                    "expected 1 patch, found " + changed);
        }
        return result;
    }
}
~~~

**Giới hạn rõ ràng:** Đây là một **class-file patcher rất hẹp**, chỉ dùng với một UTF-8 constant-pool entry ASCII có độ dài không đổi. Nó không xử lý tổng quát modified UTF-8, thay đổi độ dài code, descriptors hay control flow. `clone()` tránh thay trực tiếp buffer JVM cung cấp.

Với agent thật, dùng ASM, Byte Buddy hoặc Java Class-File API (được chuẩn hóa từ JDK 24) để tạo bytes hợp lệ và giữ StackMapTable/exception table. Thí nghiệm chỉ cần thay tên `Hook.empty` thành `Hook.count`, cùng descriptor `()V`; số lần patch phải đúng **1**.

### 8.5. `src/agent/agent/ProbeAgent.java`

~~~java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ProbeAgent {
    public static void premain(
            String options, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String name,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {
                if (!"lab/Work".equals(name)) {
                    return null;
                }
                byte[] patched = CpPatch.replaceUtf8(
                        classfileBuffer, "empty", "count");
                System.err.println("transformedWork=true");
                return patched;
            }
        }, false);
    }
}
~~~

`premain` được gọi **trước `main`**, transformer đăng ký cho class load. Tên `"lab/Work"` là **JVM internal class name**. `return null` cho class khác nghĩa là không thay đổi class ấy.

Nếu agent JAR được nạp nhưng `transformedWork=true` không xuất hiện hoặc `HOOK_CALLS=0` ở B, không thể kết luận “overhead của probe bằng 0”; có thể filter không trúng, class đã load trước hoặc transform hỏng. Hợp đồng `ClassFileTransformer` cho phép JVM tiếp tục xử lý các transformer khác ngay cả khi một transformer ném exception; cần kiểm tra hành vi **cuối cùng**.

### 8.6. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: agent.ProbeAgent

~~~

Manifest có **dòng trống kết thúc**. Agent chỉ biến đổi class ở **initial load**, nên không cần manifest `Can-Retransform-Classes` hay `Can-Redefine-Classes` cho demo.

### 8.7. Biên dịch và chạy

Từ `overhead-lab`, tạo thư mục:

~~~bash
mkdir -p out/app out/agent
~~~

Biên dịch với JDK 17+:

~~~bash
javac --release 17 -d out/app \
  src/app/lab/Hook.java \
  src/app/lab/Work.java \
  src/app/lab/BenchMain.java

javac --release 17 -d out/agent \
  src/agent/agent/CpPatch.java \
  src/agent/agent/ProbeAgent.java

jar --create --file app.jar -C out/app .
jar --create --file agent.jar --manifest AGENT.MF -C out/agent .
~~~

Đóng gói **toàn bộ output** của agent (`-C out/agent .`) để không bỏ sót anonymous class `ProbeAgent$1.class`.

Chạy **hai process JVM riêng**, không sửa app.jar:

~~~bash
# Nhóm A
java -cp app.jar lab.BenchMain A 200000 2 2

# Nhóm B
java -javaagent:agent.jar -cp app.jar lab.BenchMain B 200000 2 2
~~~

**Kiểm chứng thực tế:** Java source đã được biên dịch với `javac --release 17`, app JAR/agent JAR đã đóng gói và hai lệnh đã chạy thành công trên Zulu OpenJDK 24.

Đây là **một lần thử đã ghi nhận**. Các số `elapsedNs`/`opsPerSec` chỉ mang tính quan sát, không phải kết quả cố định:

**A:**

~~~text
RESULT,A,1,200000,773800,258464719.57,-3469022496391967169
RESULT,A,2,200000,110200,1814882032.67,-3469022496391967169
HOOK_CALLS=0
SINK=-3469022496391967169
~~~

**B:**

~~~text
transformedWork=true
RESULT,B,1,200000,1619200,123517786.56,-3469022496391967169
RESULT,B,2,200000,1175100,170198281.00,-3469022496391967169
HOOK_CALLS=800000
SINK=-3469022496391967169
~~~

`transformedWork=true` được agent in ra **stderr** khi class load; các dòng khác là stdout. Dùng mốc thời gian dài hơn nhiều trước khi so overhead. Sample A thứ hai chỉ `110200 ns` để làm 200.000 phép tính, một tín hiệu cho thấy JIT/clock/window ảnh hưởng rất lớn; **không rút kết luận phần trăm overhead từ hai dòng này**.

Điều đáng tin ở demo là:

- A: không có agent, `HOOK_CALLS=0`.
- B: agent đã transform đúng `Work`, `HOOK_CALLS=800000` theo tổng số lượt warm-up và measured.
- **Checksum giống nhau** trong A/B, nên phép tính nghiệp vụ vẫn bảo toàn.
- Measurement time có biến động; muốn ước lượng hiệu ứng cần đo lâu, nhiều forks và phương pháp thống kê phù hợp.

## 9. Script chạy nhiều lần và đảo thứ tự

Sau khi smoke test đúng, mới chạy một thí nghiệm A/B gồm nhiều JVM độc lập. Tạo file `run-ab.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

printf 'pair,marker,mode,sample,operations,elapsedNs,opsPerSec,checksum\n' > ab.csv

for pair in 1 2 3 4 5 6; do
  if (( pair % 2 == 1 )); then
    order=(A B)
  else
    order=(B A)
  fi

  for arm in "${order[@]}"; do
    if [[ "$arm" == A ]]; then
      java -Xms256m -Xmx256m -cp app.jar \
        lab.BenchMain A 5000000 5 4 |
        awk -F, -v p="$pair" '$1=="RESULT" { print p "," $0 }' >> ab.csv
    else
      java -Xms256m -Xmx256m -javaagent:agent.jar -cp app.jar \
        lab.BenchMain B 5000000 5 4 |
        awk -F, -v p="$pair" '$1=="RESULT" { print p "," $0 }' >> ab.csv
    fi
  done
done
~~~

Chạy trên Bash/Git Bash:

~~~bash
bash run-ab.sh
~~~

`set -o pipefail` giúp phát hiện lỗi từ Java ngay cả khi stdout đang được pipe qua `awk`. Script tạo `ab.csv` chỉ từ các dòng `RESULT`, thêm cột `pair` để ghép cặp. Output `HOOK_CALLS`/`SINK` không nằm trong CSV; **phải xác minh chúng qua smoke test** trước khi chấp nhận kết quả. Các messages của agent trên stderr cần được quan sát và không nhầm thành số liệu throughput.

Lưu ý:

- **Mỗi lần gọi `java` là một JVM fork riêng.** Không gọi nhiều arm trong cùng một process.
- Cả A/B dùng `-Xms256m -Xmx256m`. Mọi flag bổ sung phải được áp dụng **giống nhau** vào cả hai câu lệnh.
- `5000000` ops, 5 warmups và 4 measured samples là **thiết lập minh họa**, chưa chắc đủ thời lượng cho workload thực.
- Với hệ thống có độ nhiễu cao, tăng số pairs/forks và thời lượng measurement; có thể randomize order và lưu seed.
- Đây là **Bash script**. Trên PowerShell, chạy hai lệnh `java` giống cấu hình, ghi stdout ra file riêng; không chép cú pháp `awk`/arrays Bash nguyên xi.
- Không nên đo A/B đồng thời trên cùng CPU quota nhỏ. Test tuần tự hoặc tách host và hoán đổi host qua các lượt.

### Cách phân tích `ab.csv`

Mỗi hàng có các trường:

~~~text
pair,marker,mode,sample,operations,elapsedNs,opsPerSec,checksum
~~~

Với mỗi cặp A/B:

1. Kiểm tra `operations`/seed/workload giống nhau; checksum cần tương thích.
2. Tính `ns/op = elapsedNs / operations` cho từng measured sample.
3. Tổng hợp theo **mỗi fork JVM**, ví dụ median `ns/op` của 4 measurement windows.
4. Ghép hai forks A/B **cùng pair**, tính ratio `median_B / median_A`.
5. Tổng hợp các ratios giữa **các pairs độc lập** (median, geometric mean khi phù hợp), báo biến thiên và confidence interval nếu ước lượng được.
6. Không coi 4 samples trong mỗi fork là 4 forks độc lập; chúng có chung JIT/GC state.

Không nên chỉ gộp tất cả samples A vào một túi, tất cả B vào một túi rồi chạy t-test giả định từng operation/window độc lập. Nếu dùng bootstrap confidence intervals, cần sampling ở cấp **pair/fork**, không ở cấp từng operation.

## 10. Phân tích theo cặp và báo độ không chắc chắn

Đặt `L_Ai`, `L_Bi` là median `ns/op` trong hai forks của pair `i`:

~~~text
r_i = L_Bi / L_Ai
overhead_i = 100 × (r_i - 1)
~~~

Với throughput:

~~~text
q_i = Q_Bi / Q_Ai
throughputLoss_i = 100 × (1 - q_i)
~~~

Tính **ratio trên từng pair**, rồi mới tổng hợp. Cách này giúp giảm ảnh hưởng một số yếu tố thay đổi chậm theo thời gian giữa các cặp.

**Có thể dùng geometric mean** của các ratios dương để tóm tắt hiệu ứng nhân:

~~~text
geomean_ratio = exp(mean(log(r_i)))
aggregate_time_overhead_% = 100 × (geomean_ratio - 1)
~~~

**Đừng báo quá nhiều chữ số** nếu run-to-run variation lớn. Nếu median overhead là 0,8% nhưng thay đổi giữa forks thường ±3%, kết luận phù hợp là **chưa đủ cơ sở kết luận có overhead ổn định ở mức 0,8%**; cần thử nghiệm tốt hơn.

Báo cả:

- Số cặp/forks thực tế, measurement windows và tổng operation counts.
- Median, range/percentiles của per-pair ratios, và confidence interval khi thích hợp.
- Thứ tự A/B, host, JVM flags, heap, GC, offered load, thời gian chạy.
- Cảnh báo nếu cả A và B đang bão hòa CPU/DB hoặc bị request timeouts.
- Correctness checks, error rates và telemetry drops.

Một giá trị p95/p99 của mỗi instance **không thể được trung bình đơn giản** để suy ra p95/p99 toàn workload. Khi cần percentiles cho nhiều JVM hoặc hosts, phải tổng hợp raw latencies/histograms đúng phương pháp.

## 11. Thử nghiệm dưới độ đồng thời và tải sát production

Demo một thread giúp quan sát chi phí probe, nhưng agent có thể gây overhead do **lock contention, `ThreadLocal`/context propagation, allocation, GC, exporter queue và thread scheduling**. Những hiệu ứng đó thường chỉ rõ dưới nhiều threads.

Một ma trận tối thiểu:

| Mức tải | Mục tiêu |
|---|---|
| 1 thread | Chi phí hot path và JIT cơ bản |
| 4 threads | LongAdder contention, synchronization, GC |
| 16 threads | Scaling, CPU saturation, queueing |
| Tải thường của service | p50/p95/p99 latency, req/s, error rate |
| Gần công suất cực đại | Headroom, backlog, retries, dropped requests |
| Tải đỉnh hoặc bursts | Tail latency, exporter backpressure |

**Giữ cùng offered load** khi so sánh latency ở A và B. Nếu A nhận 200 req/s còn B nhận 500 req/s, p95 khác nhau có thể chỉ do B bị chất tải hơn.

Với dịch vụ HTTP/RPC, nên dùng **load generator ngoài JVM của ứng dụng**. Trình tạo tải cũng phải có đủ công suất để không tự là nút cổ chai. Cùng thời lượng ramp-up và measurement, cùng request mix, payload, users/think time và timeout rules.

### Closed-loop và open-loop

- **Closed-loop driver:** gửi request kế tiếp sau khi response của request trước trở về. Khi server chậm, driver **tự giảm** tốc độ gửi; throughput đo được chịu ảnh hưởng của latency.
- **Open-loop driver:** gửi theo arrival rate định trước, kể cả khi server chậm; phù hợp thử capability tại một tốc độ vào cụ thể, nhưng cần giới hạn backlog/capacity.
- **Coordinated omission:** nếu tool ngưng gửi request trong lúc server bị stall, các request **đáng lẽ phải đợi** có thể không xuất hiện trong dữ liệu, làm p99 giả thấp. Chọn công cụ/cấu hình có cách ghi latency và lịch request phù hợp SLA.

Không nên chỉ đo `mean latency` khi agent có exporter hay lock contention; p95/p99 có thể xấu hơn nhiều ngay khi mean còn ổn.

## 12. CPU, allocation, GC, heap và RSS

**CPU utilization không tự cho biết overhead**. 80% CPU ở A với 1000 req/s khác 80% CPU ở B với 700 req/s. Khi cần so hiệu quả, có thể đo **CPU-seconds/1000 successful requests** ở cùng offered load.

**Allocation rate** thường là dấu hiệu tốt để tìm overhead của tracing: span objects, tags, stacktraces và context copies. Báo `bytes/op` hoặc `MiB/s`, không chỉ “heap used” tại một thời điểm.

**GC impact**: agent tăng allocation có thể làm GC chạy nhiều hơn, tăng tail latency. Nếu đó là effect thật ở B, không được lọc bỏ các samples có GC để báo overhead đẹp hơn. Nhưng cả A và B nên có **cùng GC logging flags**.

Ví dụ dùng unified JVM logging (JDK 17+):

~~~bash
java -Xms512m -Xmx512m -Xlog:gc*:file=gc-A-%p.log \
  -cp app.jar lab.BenchMain A 200000 2 2

java -Xms512m -Xmx512m -Xlog:gc*:file=gc-B-%p.log \
  -javaagent:agent.jar -cp app.jar lab.BenchMain B 200000 2 2
~~~

`%p` giúp mỗi JVM dùng file log theo PID. Bật GC logging có overhead riêng, nhưng được áp dụng **đều ở A và B**. Với benchmark cực ngắn, việc ghi log có thể ảnh hưởng mạnh và không có đủ GC events để phân tích.

**Đừng đồng nhất các thước đo bộ nhớ**:

- **Heap used:** object đang dùng heap.
- **Heap committed/max:** vùng heap JVM đã cấp/có giới hạn.
- **Metaspace:** class metadata; agent có thể tải thêm nhiều helpers/proxies.
- **RSS:** bộ nhớ vật lý thực tế của process, còn gồm code cache, thread stacks, native memory, mmap, JNI và exporter buffers.

Có thể dùng GC logs, JFR, `jcmd` hoặc Native Memory Tracking cho phân tích chi tiết. Nếu bật `-XX:NativeMemoryTracking=summary`, nên bật **cả hai nhóm** trong phép đo đó, vì chính NMT có overhead; không dùng số RSS và heap used thay thế nhau.

## 13. Tách overhead của probe, sampling và exporter

Pipeline của agent sản phẩm thường là:

~~~text
JVM startup
  → load agent JAR
  → premain + transformer registration
  → class loading và bytecode generation
  → JIT/inlining/deoptimization ảnh hưởng
  → method entry/exit hooks
  → context propagation và tag extraction
  → sampling
  → batching, queues, aggregation
  → exporter network/retry
  → CPU, allocation, GC, thread contention
~~~

**Không thể quy tất cả overhead cho `System.nanoTime` hoặc callback `transform`**.

Nếu muốn phân tích nguyên nhân, tạo các nhánh phụ được kiểm soát:

1. **A:** no agent, baseline.
2. **B0:** agent loaded, probes disabled (đo startup/background overhead).
3. **B1:** probes enabled, export disabled (đo instrumentation cost).
4. **B2:** sampling chuẩn production, export bình thường.
5. **B3:** full tracing/metrics với exporter thực tế (đo tác động tổng).

Nhánh chính để đánh giá triển khai vẫn là **A so với cấu hình B thực tế**. Các nhánh phụ phục vụ **diagnostics**, không được thay đổi định nghĩa của A.

Sampling rate 10% không bảo đảm overhead chỉ bằng 10% của 100% sampling: agent có thể luôn tạo context/check flags trước khi quyết định sample, và exporter có fixed costs. Cần test đúng chính sách batching, queue capacity, backpressure, endpoint và sample rate của production.

Nếu reporter/agent drop telemetry khi quá tải, một phép thử có thể **trông nhanh hơn** vì công cụ bỏ qua records. Báo đồng thời **exported records, dropped records, errors/retries**, tránh chấp nhận performance tốt bằng cách hy sinh observability.

## 14. JMH cho benchmark độ hạt nhỏ

**JMH** là Java Microbenchmark Harness của dự án OpenJDK. Nó hỗ trợ:

- `@Warmup`, `@Measurement`, `@Fork` để giảm lỗi từ warm-up/forking.
- `@BenchmarkMode(Mode.Throughput)` hoặc `Mode.AverageTime`, `Mode.SampleTime`, `Mode.SingleShotTime`.
- `Blackhole` để giảm dead-code elimination.
- Profilers để quan sát allocation và GC.

Ví dụ **phụ thuộc JMH**, không biên dịch với mỗi JDK thuần:

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;
import java.util.concurrent.TimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class WorkBenchmark {
    @Benchmark
    public void compute(Blackhole bh) {
        bh.consume(lab.Work.compute(1234));
    }
}
~~~

Khi dùng JMH với agent, **forked benchmark JVM** phải nhận đúng `-javaagent`; không chỉ truyền agent cho process `java` chạy JMH coordinator. Group A fork không được có agent; group B fork phải có agent. Chạy hai nhóm trong cùng điều kiện workload, JDK, threads, heap và GC.

JMH không thay cho **service load test** với external dependencies, requests, connection pools và exporter thực tế.

## 15. Đọc kết quả đúng và phát hiện số liệu bất thường

**Các dấu hiệu cảnh báo:**

| Hiện tượng | Nguyên nhân khả dĩ | Phản ứng |
|---|---|---|
| `RESULT` A/B có checksum khác | Hai nhóm không cùng công việc | Dừng kết luận, điều tra semantics |
| B không có `transformedWork=true` | Agent không transform đúng class | Kiểm tra className, class loader, jar |
| B có `HOOK_CALLS=0` | Probe không thực sự được kích hoạt | Kiểm tra bytes được transform và method ref |
| Group A cũng có `HOOK_CALLS>0` | Baseline đã gọi recorder | Kiểm tra JAR, source và test isolation |
| Một sample A nhanh bất thường | JIT/loop optimization, quá ít thời gian | Kéo dài cửa sổ, dùng JMH |
| GC tăng ở B | Allocation probe/exporter cao hơn | Ghi nhận GC như overhead thật, profile |
| p99 xấu hơn nhưng mean gần như không đổi | Queue/exporter locks/GC tail | Đo histogram, backlog, errors |
| Throughput cao nhưng 5xx nhiều | Fail-fast thay vì làm cùng công việc | Xác minh successful operations |
| Chạy B sau tất cả A trên máy nóng | Thứ tự gây drift | Xen kẽ hoặc randomize forks |
| A/B trên JDK khác nhau | JIT/GC khác nhau | Dùng cùng JDK version/vendor |
| Cả hai cùng trên một host nhỏ và chạy đồng thời | Cạnh tranh CPU/cache/memory | Chạy tuần tự hoặc host tách biệt |
| Agent loader thay đổi class identity | Instrument sai class hoặc khác loader | Log classloader và filter đúng |
| Console output nằm trong hot method | I/O overhead lấn át probe | Dời log ngoài measurement |
| Dùng `currentTimeMillis()` cho microbenchmark | Độ phân giải thấp, wall-clock adjustments | Dùng hiệu `System.nanoTime()` |
| Lấy raw `nanoTime` giữa hai JVM rồi trừ | Origins khác nhau | Chỉ tính elapsed trong mỗi JVM |
| B lỗi không làm metrics hay exporter bị tắt | Kết luận overhead quá thấp | Kiểm tra enabled state và dropped events |

Một sample thời gian thấp hơn mức expected một cách phi lý có thể là tín hiệu **compiler optimization** hoặc **cửa sổ quá ngắn**; đừng sửa số bằng hệ số fudge. Tăng lượng việc, dùng JMH và xác nhận side effects/correctness.

## 16. Báo cáo hiệu năng có trách nhiệm

Một mẫu report cần có:

| Trường | Nội dung |
|---|---|
| Artifact | SHA/version app JAR và agent JAR, đúng config |
| Runtime | Java vendor/version, JVM flags, GC, OS, CPU quota/RAM |
| Workload | Data set, request mix, offered load, concurrency, duration |
| Protocol | Warm-ups, measurement windows, forks, thứ tự A/B, test hosts |
| Correctness | Checksum hoặc business assertions, errors, timeouts, retries |
| Core results | ns/op, throughput, p50/p95/p99, CPU, allocation, GC, RSS |
| Reliability | Variance across forks, paired ratios, confidence intervals |
| Instrumentation | Enabled probes, sampling/exporter config, dropped events |
| Decision | So với performance budget đã thống nhất, giới hạn phép đo |

**Ví dụ cách diễn đạt kết luận** (các số sau là giả định, không phải kết quả demo):

> Trong 8 cặp JVM độc lập dùng cùng JDK và tải, nhóm B có median throughput thấp hơn 4,2%, p95 latency cao hơn 5,8%. P99 chưa ổn định giữa các forks nên cần thêm measurement dưới tải lớn. Business result/error rate tương đương. Chi phí CPU/1.000 requests tăng rõ rệt khi exporter bật. Trước rollout, nhóm sẽ giảm số method probes và đo lại.

Nếu nhóm B chỉ chậm hơn 0,3% nhưng run-to-run jitter khoảng 2%, cách nói đúng là **“chưa có đủ bằng chứng để xác nhận overhead 0,3%”**, không phải một con số chính xác đến bốn chữ số.

## 17. Checklist trước khi chốt overhead

1. **Định nghĩa đúng đại lượng chính:** startup, steady-state ns/op, req/s, p95/p99 hay CPU/op?
2. **Đặt ngưỡng chấp nhận trước** khi nhìn kết quả, tránh chọn metric đẹp nhất sau test.
3. **Bắt buộc có nhóm A no-agent thực sự** và nhóm B với agent/config thật.
4. **Dùng cùng app/JDK/JVM flags** và resource limits.
5. **Dữ liệu/traffic tương đương**, cùng offered load, concurrency, backend state.
6. **Xác nhận agent B thực sự instrument** đúng target; cùng business results.
7. **Warm-up đủ và đo steady-state** ở cửa sổ dài, tách startup.
8. **Chạy nhiều JVM forks** và cân bằng thứ tự A/B.
9. **Dùng đúng công thức** latency overhead vs throughput loss.
10. **Lưu dữ liệu thô** per sample/fork/pair, không chỉ một số trung bình.
11. **Đánh giá variance và confidence**, không lấy mỗi operation làm fork độc lập.
12. **Quan sát p95/p99, errors, retries và backlog** ở độ đồng thời production.
13. **Đo CPU/allocation/GC/memory**, không chỉ latency.
14. **Ghi rõ sampling, exporter, filters** và dropped telemetry.
15. **Không loại bỏ effect thật** như GC do agent tạo chỉ để giảm overhead báo cáo.
16. **Đưa ra kết luận có điều kiện** và hành động tối ưu/test lại nếu vượt budget.

## 18. Câu hỏi tự kiểm tra

1. **Điểm khác biệt chủ yếu giữa A và B?** B nạp agent và chạy cấu hình instrumentation cần đánh giá; A không có agent từ JVM startup.
2. **Agent loaded nhưng disabled probes có phải nhóm A không?** Không.
3. **Vì sao phải cùng JDK/heap/GC flags?** Vì JVM và GC tự chúng có thể thay đổi kết quả.
4. **Thế nào là paired fork?** Một JVM A và một JVM B được chạy gần nhau/cùng điều kiện, mỗi run là process mới.
5. **Tại sao nên đảo A/B?** Để giảm tác động drift về CPU, thermal, backend.
6. **Một JVM chạy 1 triệu ops tạo 1 triệu bằng chứng thống kê độc lập?** Không.
7. **Tại sao cần warm-up?** JIT, class loading và GC chưa ổn định ở giai đoạn đầu.
8. **Sụt throughput 10% có bằng tăng latency/op 10%?** Không; nếu các điều kiện tuần tự áp dụng, time/op tăng khoảng 11,11%.
9. **`System.nanoTime` raw A trừ raw B có hợp lệ?** Không; origin mỗi JVM khác nhau.
10. **B có transformer nhưng không có hook count, đã đo probe overhead chưa?** Chưa; phải kiểm tra bytes/hot path.
11. **Checksum A/B cùng nhau đủ kết luận overhead?** Không; đó là một kiểm tra correctness.
12. **Vì sao tăng operations khi elapsed rất ngắn?** Để overhead của clock/JIT/scheduler không lấn át signal.
13. **JMH phù hợp khi nào?** Microbenchmark hot methods và biến thể bytecode.
14. **Load test ngoài JVM quan trọng khi nào?** Service concurrency/network/DB/exporter, theo offered load.
15. **B có p95 tốt hơn nhưng 5xx tăng, đã cải thiện hiệu năng?** Không; hiệu năng phải đi cùng correctness.
16. **Tail latency có thể xấu đi dù throughput gần như giữ nguyên?** Có, do GC/queue/locks/exporter.
17. **Coordinated omission là gì?** Driver không ghi nhận các request lẽ ra phải chờ khi server stall, làm latency bị đánh giá thấp.
18. **Khi agent tạo GC pauses, có được bỏ các samples ấy không?** Không, nếu GC là tác động thực của agent.
19. **Khác biệt nhỏ hơn run-to-run variation thì nên báo gì?** Bằng chứng chưa đủ, cần thêm forks/cải thiện điều kiện.
20. **Đơn vị report tối thiểu?** Luôn ghi rõ ns/op, ms/request, ops/s, CPU/op và định nghĩa measurement.

### Tài liệu chính thức

- [OpenJDK JMH](https://github.com/openjdk/jmh): benchmark harness với forks, warm-up, measurement, Blackhole.
- [JMH Sample: Benchmark Modes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_02_BenchmarkModes.java): throughput, average-time, sample-time và single-shot.
- [Oracle Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `Premain-Class`, lifecycle.
- [Oracle Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration và callbacks.
- [Oracle Java SE 21 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): elapsed, arbitrary origin, resolution.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog` để ghi JVM/GC metrics.
- [Oracle Java SE 21 — `LongAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): concurrent counters và `sum()`.

**Kết luận:** Để định lượng overhead của Java agent, hãy so sánh **cùng application/workload trong nhiều JVM độc lập**, một nhánh **không agent** và một nhánh **có agent thực sự instrument đúng**, kiểm soát warm-up/JIT/GC/CPU và độ đồng thời, tính latency/throughput theo đúng mẫu số, rồi báo **hiệu ứng cùng độ không chắc chắn**. Số đo chỉ có ý nghĩa khi thiết kế A/B công bằng và ứng dụng vẫn thực hiện **cùng công việc**.