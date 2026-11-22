# Tách agent entry point, transformer, helper và phần thu thập dữ liệu

> **Mục tiêu:** Thiết kế và đóng gói một Java instrumentation agent sao cho **entry point**, **class-file transformer**, **helper được bytecode ứng dụng gọi**, và **phần thu thập/xuất dữ liệu** có trách nhiệm, phụ thuộc, class loader và vòng đời riêng. Hiểu cách lắp ghép các thành phần bằng Java 17+, tránh đưa exporter hoặc thư viện bytecode vào hot path, tránh lỗi class loading và triển khai được một bộ `agent.jar` + `bridge.jar` tối thiểu. Có bài lab hoàn chỉnh, lệnh `javac`/`jar`/`java`, stdout có thể kiểm chứng và các bước QA đóng gói.

Bài thuộc nhóm **Đóng gói và triển khai** của Java Advanced Instrumentation. “Tách” không đơn thuần là chuyển bốn class sang bốn file. Phải tách **hướng dependency**, **quyền nhìn thấy class**, **hợp đồng dữ liệu**, **nhiệm vụ được thực thi trên luồng nào**, **cách khởi tạo/dừng** và **artifacts được giao cho JVM**.

## 1. Vì sao một class `Agent` chứa tất cả thường trở thành vấn đề?

Trong bản thử nghiệm đầu tiên, người viết agent có thể đặt mọi thứ vào `premain`:

```text
premain
  ├─ cấu hình
  ├─ đăng ký ClassFileTransformer
  ├─ viết code ASM/Byte Buddy
  ├─ tạo helper
  ├─ gửi HTTP metrics/traces
  └─ đóng stream / flush
```

Thiết kế này khó phát triển vì bốn công việc có thời điểm hoạt động khác nhau:

- **Entry point** được JVM gọi khi agent khởi động; nhiệm vụ của nó là thiết lập hệ thống.
- **Transformer** được JVM gọi khi định nghĩa/redefine/retransform class; nó tạo hoặc không tạo **byte[]** classfile, không phải chỗ gửi network request.
- **Helper** nằm trên đường thực thi của **method đã instrument**; một phương thức nghiệp vụ có thể gọi helper hàng triệu lần.
- **Collector/exporter** xử lý mẫu đo, batching, retry, metric snapshot, file/network I/O và shutdown ngoài đường nóng.

Nếu helper gọi trực tiếp exporter nặng, mọi request của ứng dụng có thể phải chịu serialization/network latency. Nếu transformer giữ thư viện/exporter làm dependency bắt buộc cho bootstrap class, một custom class loader có thể không nhìn thấy type và gây `NoClassDefFoundError`. Nếu entry point khởi tạo lung tung, callback có thể xảy ra khi collector còn chưa sẵn sàng.

**Kết luận kiến trúc:** Tách **control plane** (setup, policy, lifecycle, transformer) khỏi **data plane** (callsite helper rất nhanh, collector xử lý dữ liệu) và xác định một interface nhỏ nối hai bên.

## 2. Mô hình bốn khối và đường đi của dữ liệu

```text
               java -javaagent:agent.jar=bridge.jar
                              │
                              ▼
                    [1] AgentEntry.premain
                     │                   │
          append bootstrap JAR      start collector
          configure/filter         configure policy
                     │                   │
                     ▼                   ▼
              [2] Transformer      [4] Collector / Exporter
              (class load time)        (background)
                     │                   ▲
             tạo bytecode gọi          đọc counter /
              ProbeBridge.hit()        drain queue
                     │                   ▲
                     ▼                   │
          Class ứng dụng đã load         │
                     │                   │
            method thực thi              │
                     ▼                   │
              [3] Minimal helper ────────┘
              (bootstrap-visible,
               không network I/O)
```

Có **hai thời điểm** khác nhau cần phân biệt:

1. **Class-load time:** JVM gọi transformer với `classfileBuffer`. Transformer có thể trả `null` (không sửa) hoặc trả mảng bytes class mới hợp lệ.
2. **Business-execution time:** JVM thực thi method ứng dụng đã nạp. Nếu transformer thực sự chèn callsite, `ProbeBridge.hit()` chạy lúc method được gọi — **không phải** mỗi lần transformer callback xuất hiện.

Đừng đặt tên metric `requests_total` cho số lần callback `transform(...)`: một class load có thể tương ứng hàng triệu method invocations, còn một redefine có thể kích hoạt transformer mà không có request nghiệp vụ nào.

Bài lab bên dưới **mô phỏng callsite bằng lời gọi helper có sẵn trong source ứng dụng**; transformer được đăng ký và xác nhận nhìn thấy class nhưng trả `null`. Đây là lựa chọn có chủ đích để tự chạy chỉ với JDK 17, không đánh đồng “đăng ký transformer” với “đã chèn bytecode”.

## 3. Trách nhiệm cụ thể của từng thành phần

| Thành phần | Trách nhiệm chính | Điều nên tránh | Nơi nạp thường gặp |
| --- | --- | --- | --- |
| **Agent entry point** | `premain`/`agentmain`, đọc config, chuẩn bị helper, khởi tạo sink, đăng ký transformer, shutdown | Sinh bytes hoặc export từng event ngay trong entry method; lưu mọi thứ vào static global tùy tiện | System loader hoặc loader quản lý agent |
| **Transformer** | Lọc class, parse input, áp dụng transformation, trả bytes hoặc `null` | Gọi HTTP, block queue, dùng mutable writer chung, load lại chính class đang define | Agent core loader |
| **Minimal helper/bridge** | Nhận probe call ở runtime; ghi nhận nhanh, schema nhỏ, thread-safe | Import SDK/agent core, làm network I/O, giữ class loader/request object vô hạn | Bootstrap hoặc loader mà target chắc chắn nhìn thấy |
| **Collector/exporter** | Snapshot/drain/batch/sampling, flush, retry, gửi backend, đo lỗi xuất dữ liệu | Chạy đồng bộ từ mọi business thread, coi in-memory queue là log bền vững | Agent core loader / worker riêng |

Một ranh giới tốt không bắt buộc bốn thread hoặc bốn JVM. Đây là **bốn vai trò thiết kế**; một collector có thể là một background thread trong cùng process, hoặc một sidecar/collector remote có giao thức rõ ràng. Entry point và transformer thường ở cùng `agent.jar`; helper có thể ở một JAR riêng vì ràng buộc class loader.

### Những dữ liệu được trao đổi qua từng ranh giới

- `premain` → transformer: immutable filter rules, implementation/config references và `Instrumentation` khi cần.
- Transformer → JVM: `byte[]` classfile output hoặc `null`; **không** truyền event nghiệp vụ qua giá trị return của transformer.
- Bytecode ứng dụng → helper: lời gọi static/interface với owner/name/descriptor ổn định; arguments nên nhỏ và ít nhạy cảm.
- Helper → collector: snapshot từ counter, bounded queue hoặc một bridge interface có quy tắc backpressure rõ.
- Collector → backend: batch/stream/metric protocol; phải có retry, timeouts, observability, retention/privacy theo yêu cầu.

## 4. Entry point: “composition root” của một Java agent

Với startup Java agent, JAR manifest dùng `Premain-Class`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.AgentEntry

```

JVM gọi một dạng `premain` hợp lệ, phổ biến nhất:

```java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Lắp ghép các thành phần agent.
}
```

Đoạn trên là **chữ ký minh họa**, chưa phải chương trình Java độc lập. `-javaagent:/path/to/agent.jar=options` truyền chuỗi sau `=` vào `agentArgs`. Không tự `new Instrumentation()` được; JVM cung cấp object này.

Entry point nên thực hiện theo thứ tự hợp lý:

1. Kiểm tra tham số và nguồn artifact/config đáng tin cậy.
2. Thiết lập class-loader visibility cho helper, **trước** khi class mục tiêu cần resolve nó.
3. Khởi tạo helper/collector và kiểm tra API version/hợp đồng cần thiết.
4. Chuẩn bị transformer và cấu hình immutable.
5. Đăng ký transformer bằng `inst.addTransformer(transformer, false)` hoặc `true` khi capability cho phép.
6. Đăng ký shutdown/flush có giới hạn.
7. Log trạng thái startup **sau khi** hoàn thành bước liên quan; nếu mandatory resource không sẵn sàng, fail rõ ràng theo chính sách.

### `premain` khác `agentmain`

- `Premain-Class` dùng khi JVM bắt đầu với `-javaagent`.
- `Agent-Class` dùng trong trường hợp runtime hỗ trợ nạp agent sau khi JVM đã chạy; entry point tương ứng thường là `agentmain`.
- Với attach muộn, một số class đã được định nghĩa **trước** khi transformer được đăng ký. Việc đăng ký **không phát lại** class-load callback cũ; muốn xử lý class đã nạp cần capability `retransformClasses`/`redefineClasses` và kiểm tra riêng.
- Java instrumentation class thường được system class loader nạp, nhưng production có thể có hệ loader/module phức tạp. Không biến assumption của bài lab thành quy tắc cho mọi runtime.

Không tự bật khả năng retransform/redefine chỉ vì agent có transformer. Nếu lab chỉ xử lý **class load mới** và `addTransformer(..., false)`, manifest **không cần** `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`.

## 5. Transformer: biến đổi bytes, không phải thư viện telemetry

`ClassFileTransformer` có callback Java 9+:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {
    // ...
}
```

Đây là **method minh họa** với body chưa đầy đủ. Khi `transform` trả `null`, JVM giữ bytes hiện hành của tầng này. Khi trả bytes mới, JVM chuyển chúng cho transformer phía sau rồi kiểm tra classfile cuối. **Không sửa `classfileBuffer` tại chỗ**.

Transformer cần:

- **Filter sớm** theo class/package/loader/module, tránh agent/helper và SDK.
- Tạo bytecode writer/visitor/buffer **mỗi invocation**; nhiều thread có thể cùng gọi transformer.
- Tránh tham chiếu tới class đang được định nghĩa bằng `Class.forName`, vì có thể tạo recursion/circularity.
- Giữ mapping class → transform rule đủ chặt, có version/idempotence để tránh chèn probe lặp qua redefine.
- Không thực hiện HTTP, flush file hoặc chờ worker thread dưới class-loading lock.
- Giữ logic transform testable thuần túy: `transform(inputBytes, config) → newBytes|null`.
- Kiểm chứng output classfile và tương thích với các transformer khác trong chain.

Nếu dùng ASM/Byte Buddy trên Java 17, các thư viện đó thuộc **agent core**, không nên bị “shade” vào bootstrap helper. Với JDK 24+, Class-File API chuẩn `java.lang.classfile` có thể thay một phần bytecode library, nhưng bài lab chọn Java 17+ nên **không giả định** JDK 17 đã có API đó.

### `ClassFileTransformer` có chắc chạy đúng một lần mỗi class?

Không. Một class có thể đi qua callback trong lần load ban đầu và trong các lần redefine/retransform theo capability. Transformer `canRetransform=false` vẫn callback khi **redefine**; với **retransform**, output incapable được JVM tái áp dụng mà không gọi lại callback incapable. Không nên dùng callback count làm business event count hoặc kết luận bytes đã được cài thành công chỉ từ log callback.

## 6. Helper: API nhỏ được bytecode ứng dụng thực sự nhìn thấy

Một transformer có thể chèn symbolic reference:

```text
invokestatic demo/bridge/ProbeBridge.hit:()V
```

Đây là **mô tả instruction**, không phải dòng Java source có thể chạy trực tiếp. Khi method ứng dụng thực thi, chính loader/module của class đã instrument phải resolve `demo.bridge.ProbeBridge`. Agent chạy được trên system loader **không đồng nghĩa** custom app loader cũng nhìn thấy mọi class của agent.

Tách `bridge.jar` có ưu điểm:

- Chỉ chứa những class thật sự cần thiết cho callsite.
- Cho phép đưa helper vào bootstrap search mà **không đưa cả agent core** vào đó.
- Giảm nguy cơ lớp bootstrap vô tình nạp phiên bản thư viện JSON/logging sai.
- Có thể ổn định ABI helper độc lập với các thay đổi exporter/SDK.
- Thuận lợi cho `jdeps`, kiểm tra classpath và QA package collision.

API helper nên gồm vài method rõ kiểu: `hit():void`, `record(long):void` hoặc `record(int,long):void`. Tránh truyền request object của webapp, raw `ClassLoader`, custom SDK objects hay `Throwable` nguyên bản vào một helper bootstrap giữ static references.

**Bootstrap helper phải chỉ liên kết với các class do bootstrap loader định nghĩa.** JDK nói rõ không có bảo đảm mọi platform class đều được bootstrap định nghĩa. Một bridge chỉ dùng `java.lang.*` và `java.util.concurrent.atomic.LongAdder` của `java.base` là case dễ kiểm thử hơn bridge import rich exporter.

### `appendToBootstrapClassLoaderSearch`

Entry point có thể gọi:

```java
// Mã minh họa trong premain đã có inst và JarFile jar.
inst.appendToBootstrapClassLoaderSearch(jar);
```

JAR được thêm vào đường tìm kiếm bổ sung của bootstrap loader. Đây là **append**, không ghi đè class đã định nghĩa hay retroactively sửa một symbolic reference từng resolve thất bại. Javadoc cảnh báo chỉ đưa classes/resources dành cho bootstrap vào JAR ấy; nếu một class package-private của ứng dụng bị bootstrap định nghĩa nhầm do trùng tên, có thể phát sinh `IllegalAccessError`.

Chọn package bridge độc nhất (chẳng hạn `com.company.instrumentation.bridge.v1`) và **append trước khi lớp ứng dụng đầu tiên cần nó**. Khi thực sự dùng bootstrap helper, `Class.forName("demo.bridge.ProbeBridge", false, null)` thành công và `getClassLoader()==null` là bằng chứng hữu ích về loader identity.

**Không phải mọi helper đều bắt buộc ở bootstrap.** Nếu chỉ instrument một class loader có thể thấy helper JAR bằng parent delegation hoặc injection đúng loader, có thể không cần mở rộng bootstrap search. Quyết định dựa trên topology thực tế của ứng dụng.

### JPMS

Helper được bootstrap định nghĩa trong bài lab thuộc **unnamed module của bootstrap loader**, không phải module `java.base`. Với **named modules**, Java instrumentation có quy tắc bổ sung read edges cho các module của class được transform nhằm hỗ trợ helper. Việc đọc được helper **không tự cho phép** deep reflection vào mọi package; nếu agent cần opens/exports riêng phải kiểm tra `Instrumentation.redefineModule` hoặc cấu hình phù hợp.

Lab dưới đây dùng **classpath/unnamed module**, nên không thể dùng nó làm chứng cứ mọi tổ hợp module-path/loader đều hoạt động không cần thay đổi.

## 7. Collector: đi khỏi hot path và giữ semantics rõ ràng

Collector chịu trách nhiệm biến tín hiệu nội bộ thành dữ liệu sử dụng được. Có ít nhất ba kiểu:

| Dữ liệu cần | Bridge có thể giữ | Collector làm gì | Giới hạn |
| --- | --- | --- | --- |
| Tổng số method calls | `LongAdder` | Snapshot định kỳ, export cumulative counters | Không giữ từng lần gọi; `sum()` không atomic khi concurrent |
| Từng sự kiện rút gọn | Bounded queue hoặc bridge interface | Drain batch, retry, gửi backend | `offer` thành công không đảm bảo backend đã lưu |
| Chẩn đoán JVM timeline | Custom `jdk.jfr.Event` | JFR recording/stream/file analysis | Phụ thuộc event enabled/threshold/retention |

Trong bài lab, helper **chỉ tăng `LongAdder`**, còn collector đọc giá trị theo chu kỳ trên **daemon worker**, sau đó flush khi JVM shutdown bình thường. Đó là pipeline tối giản và dễ kiểm chứng. **Không có remote exporter**: một counter trong JVM chưa tự xuất hiện trong Prometheus/OpenTelemetry/backend cho đến khi thực sự thêm exporter.

### Phân biệt “collect” với “deliver”

```text
ProbeBridge.hit()
    → counter increment (trong JVM)
    → collector snapshot (trong JVM)
    → exporter encode/batch (nếu triển khai)
    → network/file sink (nếu triển khai)
    → backend chấp nhận dữ liệu (cần xác nhận riêng)
```

Một số dự án nhầm `counter.increment()` với “đã gửi metrics”. Nếu queue full hoặc backend down, dữ liệu có thể bị drop/stale. Cần đo tách `attempted`, `accepted`, `dropped`, `exported`, `exportFailed`, và số lần retry theo ngữ nghĩa chính xác.

### Về thread và shutdown

- Không tạo **một thread cho mỗi event**.
- Collector worker nên được quản lý vòng đời và giới hạn concurrency.
- Nếu dùng daemon worker, JVM **không chờ** worker hoàn tất khi chỉ còn daemon; cần hook flush hoặc cơ chế dừng đã thiết kế.
- Shutdown hook không chạy khi process bị `SIGKILL`, crash nghiêm trọng hoặc bị dừng cưỡng bức; in-memory telemetry có thể mất.
- Trong shutdown hook không nên block vô hạn vì network sink; đặt timeout/quota và có phương án drop/flush best effort.
- Đừng giữ references mạnh tới `ClassLoader`/`Class<?>` của plugin trong static helper, vì có thể gây leak khi app redeploy.

## 8. Lab Java 17+ hoàn chỉnh: entry + transformer + bridge + collector

Chúng ta xây một mẫu **đúng ranh giới class loader**, có thể chạy với JDK 17+ và **không cần thư viện ngoài**. Nó gồm:

1. `AgentEntry`: được JVM gọi qua `premain`, append `bridge.jar`, khởi tạo collector, đăng ký transformer.
2. `WatchingTransformer`: chỉ quan sát việc lớp `DemoApp` được JVM định nghĩa, giữ một cờ atomic; **không sửa class bytes**.
3. `ProbeBridge`: bootstrap helper, chỉ có `LongAdder` và hai public static methods.
4. `CounterCollector`: background sampler trên daemon worker; khi shutdown đọc counter cuối và in kết quả.
5. `DemoApp`: ba lần gọi `ProbeBridge.hit()` từ source để **mô phỏng callsite sau instrumentation**.

Với thiết kế này, transformer không tạo bytecode mới. Đó là **giới hạn chủ ý** của ví dụ: nó minh họa đóng gói, loader linkage và pipeline quan sát; để thực sự chèn `invokestatic` cần một bytecode transformation hợp lệ (ASM/Byte Buddy hoặc Class-File API từ JDK 24) cùng integration tests khác.

### 8.1. Cấu trúc thư mục

```text
four-part-agent-demo/
├── agent.mf
├── bridge-src/
│   └── demo/bridge/ProbeBridge.java
├── agent-src/
│   └── demo/agent/
│       ├── AgentEntry.java
│       ├── WatchingTransformer.java
│       └── CounterCollector.java
└── app-src/
    └── demo/app/DemoApp.java
```

Sau build có các artifacts:

```text
out/
├── bridge/           # class tạm để đóng bridge.jar
├── agent/            # class tạm để đóng agent.jar
├── app/              # app classes, không bao gồm helper lúc chạy
├── bridge.jar
└── agent.jar
```

Hai JAR có trách nhiệm rõ: `bridge.jar` **chỉ** chứa class bootstrap helper; `agent.jar` chứa entry point, transformer, collector (và những library agent cần nếu phiên bản thực tế). Application chạy với `-cp out/app`, không thêm bridge hoặc agent JAR vào runtime app classpath.

### 8.2. `bridge-src/demo/bridge/ProbeBridge.java`

```java
package demo.bridge;

import java.util.concurrent.atomic.LongAdder;

public final class ProbeBridge {
    private static final LongAdder HITS = new LongAdder();

    private ProbeBridge() {
    }

    public static void hit() {
        HITS.increment();
    }

    public static long total() {
        return HITS.sum();
    }
}
```

Điểm quan trọng:

- Helper không import `demo.agent.*`, JSON library, metrics SDK hoặc HTTP client.
- `LongAdder` thuộc `java.base`, có thể dùng ở bootstrap.
- `hit()` chỉ increment, có chi phí rất nhỏ và không block network.
- `total()` là snapshot counter phục vụ telemetry; `LongAdder.sum()` không cung cấp một phép đọc nguyên tử xuyên các updates đang diễn ra.
- Không tạo class loader, thread, serializer hoặc network connection trong static initialization.

API gồm `hit:()V` và `total:()J`, dễ để transformer thực tế sinh callsite chính xác. Không đặt helper trong package `java.*` hay các package chung dễ va chạm; `demo.bridge` chỉ để thử nghiệm, trong sản phẩm nên có tên riêng theo tổ chức.

### 8.3. `agent-src/demo/agent/WatchingTransformer.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WatchingTransformer
        implements ClassFileTransformer {

    private final AtomicBoolean sawApp = new AtomicBoolean();

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("demo/app/DemoApp".equals(className)) {
            sawApp.set(true);
        }

        // Không sửa classfileBuffer; JVM dùng bytes hiện tại.
        return null;
    }

    public boolean sawApp() {
        return sawApp.get();
    }
}
```

`AtomicBoolean` bảo đảm cờ quan sát được từ collector/shutdown thread. Transformer **không** in log hoặc gửi metrics bên trong callback. Lọc chính xác tên nội bộ `demo/app/DemoApp` thay vì scan toàn bộ JVM. Nếu JVM gọi callback với `className==null` trong tình huống đặc biệt, phép gọi `"literal".equals(className)` vẫn an toàn.

Khi transformer được đăng ký trước khi `DemoApp` nạp, lần load class thông thường sẽ gọi callback và đặt `sawApp=true`. `return null` nghĩa là không can thiệp bytes. **Không** được báo lab này đã inject bytecode thành công.

### 8.4. `agent-src/demo/agent/CounterCollector.java`

```java
package demo.agent;

import demo.bridge.ProbeBridge;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class CounterCollector {
    private final WatchingTransformer transformer;
    private final AtomicLong lastSample = new AtomicLong();

    private final ScheduledExecutorService worker =
            Executors.newSingleThreadScheduledExecutor(task -> {
                Thread thread = new Thread(
                        task, "agent-counter-collector");
                thread.setDaemon(true);
                return thread;
            });

    public CounterCollector(WatchingTransformer transformer) {
        this.transformer = transformer;
    }

    public void start() {
        // Work định kỳ ở thread riêng, không ở business callsite.
        worker.scheduleAtFixedRate(
                () -> lastSample.set(ProbeBridge.total()),
                0, 200, TimeUnit.MILLISECONDS);
    }

    public void stopAndReport() {
        worker.shutdownNow();

        // Đọc lần cuối sau khi application main đã hoàn tất.
        long finalCount = ProbeBridge.total();
        lastSample.set(finalCount);

        System.out.println(
                "collector: saw-app=" + transformer.sawApp());
        System.out.println(
                "collector: total-hits=" + finalCount);
    }
}
```

Những chi tiết cần hiểu:

- `CounterCollector` **là class rich agent-side**; nó có thể phụ thuộc bridge API, nhưng bridge **không phụ thuộc ngược** vào collector.
- `AtomicLong lastSample` chứa giá trị gần nhất background worker đọc. Ở production có thể đưa nó sang exporter; bài lab chỉ kiểm chứng pipeline nội bộ.
- Worker là **daemon thread** để không giữ JVM sống sau khi ứng dụng kết thúc.
- Chu kỳ 200 ms chỉ là tham số cho lab, **không** phải khuyến nghị scrape interval production.
- `stopAndReport()` gọi `shutdownNow()`, rồi lấy `finalCount` trực tiếp từ helper. Nhờ vậy stdout **không phụ thuộc** việc background worker có kịp chạy một chu kỳ hay không.
- `shutdownNow()` chỉ yêu cầu task dừng, không phải lời hứa nó đã kết thúc tức thời; bài lab worker chỉ đọc counter, không có network flush cần chờ. Production exporter cần một giao thức close/awaitTermination có timeout và xác nhận đã flush theo policy.
- Không nên báo số cuối bằng `lastSample.get()` khi background worker có thể chậm: số đó có thể stale. Dùng giá trị `finalCount` đọc sau các lời gọi nghiệp vụ ở bài lab.

### 8.5. `agent-src/demo/agent/AgentEntry.java`

```java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class AgentEntry {
    private static JarFile bridgeJar;

    public static void premain(String options, Instrumentation inst)
            throws Exception {

        if (options == null || options.isBlank()) {
            throw new IllegalArgumentException(
                    "Agent option must be a bridge.jar path");
        }

        // 1. Đặt helper vào bootstrap search TRƯỚC app load.
        bridgeJar = new JarFile(Path.of(options).toFile());
        inst.appendToBootstrapClassLoaderSearch(bridgeJar);

        // 2. Xác nhận loader thật, không chỉ nhìn vị trí JAR.
        Class<?> bridge = Class.forName(
                "demo.bridge.ProbeBridge", false, null);
        if (bridge.getClassLoader() != null) {
            throw new IllegalStateException(
                    "ProbeBridge must be bootstrap-defined");
        }
        System.out.println("agent: bridge-loader=bootstrap");

        // 3. Khởi tạo collector trước khi đăng ký transformer.
        WatchingTransformer transformer = new WatchingTransformer();
        CounterCollector collector = new CounterCollector(transformer);
        collector.start();
        System.out.println("agent: collector=started");

        // 4. Dừng collector khi JVM shutdown bình thường.
        Runtime.getRuntime().addShutdownHook(
                new Thread(collector::stopAndReport,
                        "agent-shutdown"));

        // 5. Đăng ký transformer cho class-load events mới.
        inst.addTransformer(transformer, false);
        System.out.println("agent: transformer=registered");
    }
}
```

Đoạn code cho thấy rõ **entry point là nơi lắp ghép**, không cần chứa bytecode generation, mutable global queue hay exporter code. `JarFile` được giữ bằng static reference trong demo; **không đóng sớm** trước khi bootstrap search không còn cần JAR. Với hệ thống thực tế phải thiết kế vòng đời và quản lý open file handles phù hợp.

Khi `premain` thất bại vì path/JAR không hợp lệ, JVM khởi động agent có thể thất bại **trước** application `main`. Điều này là fail-fast cho cấu hình bắt buộc của lab. Không biến một lỗi thiếu bridge nghiêm trọng thành log vô hại rồi tiếp tục nạp class instrumented có symbolic reference không giải quyết được.

### 8.6. `app-src/demo/app/DemoApp.java`

```java
package demo.app;

import demo.bridge.ProbeBridge;

public final class DemoApp {
    public static void main(String[] args) {
        System.out.println(
                "app: bridge-loader=" +
                (ProbeBridge.class.getClassLoader() == null
                        ? "bootstrap" : "other"));

        // Mô phỏng 3 callsites mà transformer thật có thể chèn.
        ProbeBridge.hit();
        ProbeBridge.hit();
        ProbeBridge.hit();

        System.out.println(
                "app: hits=" + ProbeBridge.total());
    }
}
```

Lời gọi helper ở đây được `javac` biên dịch trực tiếp vào `DemoApp`. Nó **không** do `WatchingTransformer` thêm vào, vì transformer của bài lab trả `null`. Điều đó không làm giảm giá trị kiểm chứng ranh giới: cả application và collector rich side cùng nhìn thấy **một helper do bootstrap định nghĩa**.

### 8.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.AgentEntry

```

Giữ dòng trống cuối manifest main section. Không khai báo capability retransform/redefine vì không sử dụng chúng. Nếu sau này agent cần xử lý class đã load, phải đánh giá việc thêm `Can-Retransform-Classes`/`Can-Redefine-Classes`, kiểm tra `Instrumentation.is*Supported()` và các giới hạn schema/JVM.

Trong lab, path `bridge.jar` được truyền qua **agent options**; chúng ta không đặt `Boot-Class-Path` trong manifest. Đây là một cách triển khai minh bạch để người học thấy đúng thời điểm `appendToBootstrapClassLoaderSearch` xảy ra.

### 8.8. Build và chạy trên Bash (Linux/macOS/Git Bash)

Từ thư mục `four-part-agent-demo`:

```bash
mkdir -p out/bridge out/agent out/app

# Biên dịch helper độc lập, chỉ với JDK.
javac -encoding UTF-8 -d out/bridge \
    bridge-src/demo/bridge/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

# Compile agent core với bridge.jar trên COMPILE classpath.
javac -encoding UTF-8 -cp out/bridge.jar -d out/agent \
    agent-src/demo/agent/WatchingTransformer.java \
    agent-src/demo/agent/CounterCollector.java \
    agent-src/demo/agent/AgentEntry.java

# Đóng gói chỉ agent classes; không copy bridge vào agent.jar.
jar --create --file out/agent.jar \
    --manifest agent.mf -C out/agent .

# App thấy bridge API lúc compile.
javac -encoding UTF-8 -cp out/bridge.jar -d out/app \
    app-src/demo/app/DemoApp.java

# Runtime app classpath KHÔNG có bridge.jar hoặc agent.jar.
java -javaagent:out/agent.jar=out/bridge.jar \
    -cp out/app demo.app.DemoApp
```

Bước compile **agent core** và **app** đều cần bridge API. Nhưng việc đặt bridge JAR trên **compile classpath** khác với việc nạp runtime: ở lệnh `java`, bridge chỉ được giới thiệu qua `-javaagent` options rồi entry point append vào bootstrap. Điều này giúp demo phát hiện lỗi packaging/loader thay vì vô tình tìm helper từ app classpath.

### 8.9. Build và chạy trên PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/bridge, out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/bridge `
    bridge-src/demo/bridge/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -cp out/bridge.jar -d out/agent `
    agent-src/demo/agent/WatchingTransformer.java `
    agent-src/demo/agent/CounterCollector.java `
    agent-src/demo/agent/AgentEntry.java

jar --create --file out/agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app `
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar `
    -cp out/app demo.app.DemoApp
```

PowerShell dùng backtick để nối dòng. Không thêm `out/bridge.jar` vào `-cp` ở bước runtime vì sẽ che đi mục tiêu test bootstrap bridge. Cả `java`, `javac`, `jar` phải là công cụ của JDK 17+ hoặc JDK tương thích; không chạy đoạn nguồn Java 17 bằng JDK 8.

### 8.10. Stdout kỳ vọng trong môi trường lab bình thường

```text
agent: bridge-loader=bootstrap
agent: collector=started
agent: transformer=registered
app: bridge-loader=bootstrap
app: hits=3
collector: saw-app=true
collector: total-hits=3
```

Vì sao output được thiết kế xác định?

1. `premain` append và kiểm tra `ProbeBridge` **trước khi application main chạy**.
2. Collector khởi tạo **trước** `addTransformer`, không phụ thuộc vào callback sau.
3. `DemoApp` là một class load mới sau `premain`, tên nội bộ khớp filter của `WatchingTransformer`.
4. `ProbeBridge` có counter tĩnh dùng chung vì cùng class bootstrap-defined.
5. App gọi `hit()` **ba lần tuần tự** và in số 3.
6. Agent cài shutdown hook; khi JVM dừng bình thường, hook đọc counter cuối và cờ transformer rồi in hai dòng collector.
7. Worker daemon định kỳ **không in log**, vì vậy thứ tự stdout không phụ thuộc vào chu kỳ 200 ms.

Nếu runtime bị dừng cưỡng bức, JAR sai, startup agent lỗi hoặc có những agent khác in log, stdout thực tế có thể khác. Đó không phải lý do để viết một “kỳ vọng cứng” cho môi trường chưa xác nhận. Nếu app tạo thêm thread gọi `hit()` đồng thời hoặc gọi lại `main`, counter cuối có thể thay đổi.

### 8.11. Kiểm tra artifacts và dependency graph

Dùng chính công cụ JDK:

```bash
jar --list --file out/bridge.jar
jar --list --file out/agent.jar
jdeps -verbose:class out/bridge.jar
javap -classpath out/bridge.jar -p demo.bridge.ProbeBridge
javap -classpath out/app -c demo.app.DemoApp
```

Các bất biến mong đợi:

- `bridge.jar` chứa `demo/bridge/ProbeBridge.class` và metadata JAR tối thiểu; **không** chứa `demo/agent/`, `net/bytebuddy/`, JSON/HTTP libraries.
- `agent.jar` chứa `demo/agent/AgentEntry.class`, `WatchingTransformer.class`, `CounterCollector.class`, manifest với `Premain-Class`; **không** chứa `demo/bridge/ProbeBridge.class`.
- `jdeps` trên bridge báo dependency vào các class `java.base`, không kéo rich exporter.
- `javap -c demo.app.DemoApp` cho thấy các lời gọi `invokestatic demo/bridge/ProbeBridge.hit:()V` từ source app, **không được transformer chèn**.
- `Class.getClassLoader()==null` ở agent và app xác nhận helper bootstrap-defined tại runtime.

`jdeps` chỉ khảo sát dependencies tĩnh trong bytecode. Nó **không** phát hiện đầy đủ mọi dynamic reflection, resource lookup hoặc dependency do plugin framework nạp lúc chạy. Vẫn phải smoke-test trên class loaders/modules mục tiêu.

## 9. Bốn thành phần cần bốn nhóm kiểm thử riêng

### Entry point

- Thiếu `Premain-Class`, tên class sai, method `premain` không hợp lệ.
- Agent options sai hoặc helper JAR không tồn tại.
- Có thể mở bootstrap JAR và xác nhận canonical helper loader?
- Có ghi nhận startup status đúng sau khi thành phần sẵn sàng?
- Nếu thành phần bắt buộc thất bại, JVM/app xử lý theo fail-open/fail-closed policy nào?

### Transformer

- Filter đúng class name, loader, module, method descriptor?
- Đăng ký trước khi target class được nạp?
- `return null` thực sự không làm biến đổi bytes?
- Với transformer tạo bytes: output hợp lệ, giữ labels/stack maps, annotations và method behavior?
- Thread safety khi class loading đồng thời; không dùng mutable bytecode writer chung?
- Idempotence khi redefine/retransform nhiều lần và nhiều agent cùng tham gia?
- Không instrument package của chính agent/helper/exporter?

### Helper

- Bootstrap hoặc target loader thấy đúng một class `ProbeBridge`?
- Public method descriptor khớp symbolic references ở bytecode?
- Không import rich agent classes/SDK?
- Không block, không allocation quá mức, không gọi network trong hot path?
- Tương thích ABI khi nâng cấp; không tạo static cache giữ plugin class loader?
- Thread-safe khi nhiều method invocations đồng thời?

### Collector/exporter

- Snapshot/drain đúng dữ liệu và đơn vị đo?
- Worker không giữ JVM sống không cần thiết; shutdown hook/flush có timeout?
- Exporter lỗi, timeout, backend down, queue full thì dữ liệu nào mất?
- Có metrics cho attempted/dropped/failed/retry?
- Không gửi PII/secrets và không giữ dữ liệu quá retention policy?
- Collector không làm thay exception/return của method nghiệp vụ?

**Chỉ test rằng agent startup thành công không đủ.** Cũng không đủ khi thấy `transform(...)` callback nhưng chưa test callsite helper. Cần test **từng biên** và cả chuỗi thực thi.

## 10. Các mô hình truyền dữ liệu giữa helper và collector

### 10.1. Pull: collector đọc counter/histogram trong bridge

```text
Business thread ──> ProbeBridge.hit() ──> LongAdder
                                             ▲
                                        periodic poll
                                             │
                                      CounterCollector
```

Ưu điểm: rất ít dependency và allocation; helper bootstrap có thể đứng một mình. Hạn chế: chỉ giữ aggregate; `LongAdder.sum()` không tuyến tính hóa chính xác mọi update đang diễn ra. Với metrics production, thường xuất cumulative counters và backend tính rate theo cửa sổ thời gian; phải xử lý restart/reset.

### 10.2. Push: helper enqueue event nhỏ

```text
Business thread ──> ProbeBridge.offer(code, elapsed)
                             │
                       bounded queue
                             │
                             ▼
                      worker/exporter
```

Nếu yêu cầu giữ từng event, một queue giới hạn dung lượng có thể phù hợp. Nhưng không dùng `BlockingQueue.put()` trong hot path mà không phân tích backpressure: khi queue đầy, business thread có thể bị chặn. `offer()` không chờ nhưng có thể trả `false`; cần counter dropped, sampling hoặc policy rõ. Bản ghi enqueue trong heap **không phải** cam kết backend đã lưu, mất điện/crash có thể xóa dữ liệu chưa gửi.

Bridge có thể định nghĩa một interface nhỏ `BridgeSink` và agent rich side implement một sink chỉ enqueue. **Thận trọng:** gọi interface đó từ helper chạy trên business thread; nếu implementation làm HTTP đồng bộ thì việc tách JAR không giải quyết latency. Một `static` sink reference có thể giữ agent/plugin loader sống; phải có vòng đời `install/uninstall` và đồng bộ JMM phù hợp.

### 10.3. Runtime diagnostic: JFR Event

Với JDK 17+, custom event `jdk.jfr.Event` có thể ghi thông tin duration/fields khi JFR recording bật. JFR phù hợp chẩn đoán JVM và tương quan với GC/locks/threads; không phải exporter metrics HTTP hay durable audit log. Việc tạo event/commit nên có enabled/threshold guard và kiểm soát payload. Nếu cần dùng JFR trong helper bootstrap, phải kiểm tra **loader/module visibility của `jdk.jfr`** thay vì mặc định mọi platform module được bootstrap định nghĩa. Giữ bridge tối thiểu giúp giảm rủi ro.

## 11. Tách nguồn và hướng phụ thuộc ở Maven/Gradle

Một project lớn có thể tổ chức thành:

```text
project/
  agent-bridge/          # bridge.jar, java.base only
  agent-core/            # AgentEntry, Transformer, Collector
  agent-integration/     # test JVM chạy -javaagent và custom loader
  example-app/           # app chỉ cần API bridge lúc compile
```

Dependency rule:

```text
agent-core ──(compile API)──> agent-bridge
example-app ──(compile API)──> agent-bridge

agent-bridge ──X──> agent-core
agent-bridge ──X──> Byte Buddy / JSON / HTTP / telemetry SDK
```

Đừng dùng `implementation`/fat-JAR configuration một cách vô thức làm build tool copy `ProbeBridge.class` vào **cả hai JAR**. Trong một project Gradle có thể chọn `compileOnly` hoặc cấu hình dependency scope khác tùy cách đóng gói; Maven có `provided` cho một số trường hợp. **Không có một scope mặc định đúng cho mọi build tool**: cái cần kiểm chứng là output artifact và runtime class-loader behavior, không chỉ tên scope.

Nếu agent core dùng shading/relocation để tránh xung đột ASM/Byte Buddy/JSON library với app, hãy áp dụng ở **rich agent JAR** với quy tắc resource/service-loader phù hợp. **Không** đưa nguyên shaded fat agent JAR vào bootstrap search. Nếu dùng multi-release JAR để hỗ trợ nhiều JDK, kiểm tra `Multi-Release: true`, class-file versions và lựa chọn class thực tế trên JDK mục tiêu; lab này không dùng multi-release.

### Manifest là một phần của artifact, không chỉ là file text

Đối với agent JAR, JVM đọc `META-INF/MANIFEST.MF`. Một JAR có thể chứa `AgentEntry.class` nhưng không có `Premain-Class`, khiến `-javaagent` thất bại. Kiểm tra manifest **sau khi đóng gói**, không chỉ xem `agent.mf` trên source tree.

Tương tự, nếu dùng `Boot-Class-Path` thay cho `appendToBootstrapClassLoaderSearch`, các đường dẫn tương đối được giải theo đặc tả và cần thử với **vị trí triển khai thực tế** của agent.jar và bridge.jar. Di chuyển một JAR sau khi build mà không cập nhật path có thể làm agent khởi động khác mong đợi.

## 12. Những điểm triển khai dễ gây lỗi ở production

### 12.1. Bản bridge không tương thích ABI

Lời gọi đã được chèn có thể là:

```text
invokestatic demo/bridge/ProbeBridge.hit:()V
```

Nếu phiên bản mới đổi thành `hit(int)` và xóa method cũ, class đã instrument có thể gặp `NoSuchMethodError` khi JVM resolve callsite. Hãy giữ API bridge ổn định hoặc version package/triển khai theo migration có kiểm soát. `appendToBootstrapClassLoaderSearch` không thay class cùng tên đã được bootstrap định nghĩa trước đó.

### 12.2. Helper chỉ được system loader nhìn thấy

Agent JAR có `ProbeBridge` nhưng class ở custom loader có parent bootstrap/platform vẫn không thấy nó. **Đừng giả định** `-javaagent` làm mọi class loader tự đọc thư viện agent. Nếu cần nhiều loader, dùng bootstrap helper tối thiểu hoặc cơ chế injection vào đúng loader đã được kiểm chứng.

### 12.3. Sai thứ tự khởi tạo

Nếu transformer đã chèn callsite `ProbeBridge.hit()` nhưng bridge chưa có trong loader search, JVM có thể thất bại khi link. Nếu helper gọi collector trước khi collector sẵn sàng, có thể `NullPointerException` hoặc mất event. Chọn fallback được định nghĩa rõ và append/init trước khi đăng ký transformer.

### 12.4. Trùng class giữa artifacts

Cùng binary name ở hai defining loaders có thể tạo hai static counters hoặc gây `ClassCastException`/loader constraint errors. Giữ bridge JAR canonical và không copy class bridge vào rich JAR. Dùng `jar --list` và `Class.getClassLoader` để chứng minh thay vì chỉ nhìn POM.

### 12.5. Collector làm hỏng nghiệp vụ

Nếu helper gọi exporter/network, một backend timeout có thể làm method nghiệp vụ chậm hoặc thất bại. Chuyển xử lý nặng ra worker. Với best-effort telemetry, định nghĩa fail-open và dropped counter. Với dữ liệu bắt buộc về pháp lý/tài chính, telemetry best-effort không đủ: cần durable transactional record và giao nhận đáng tin cậy.

### 12.6. Agent tự instrument chính mình

Transformer dùng package filter quá rộng, instrument logger/serializer/helper, rồi một callback export lại gọi method được instrument, tạo recursion/`StackOverflowError` hoặc class-loading deadlock. Exclude agent/bridge/bytecode SDK/sink packages, kiểm tra reentrancy và bootstrap load order.

### 12.7. Vòng đời shutdown không đúng

Đừng giả định mọi JVM stop đều gọi shutdown hook. `kill -9`, hard crash hoặc container bị kill cưỡng bức có thể làm mất dữ liệu. Không cho shutdown hook block vô hạn. Gỡ transformer cũng không tự xóa probe đã chèn khỏi class đang chạy; helper ABI có thể cần tồn tại cho tới khi JVM restart.

### 12.8. Tách class nhưng vẫn chung mutable global state

Bốn file riêng vẫn có thể tạo một thiết kế kém nếu tất cả dùng `static HashMap` không thread-safe hoặc cùng giữ một `ByteArrayOutputStream` khi nhiều transformer callbacks. Classfile writer phải per invocation; counters dùng atomic/concurrent structures; config dùng immutable snapshots. `ConcurrentHashMap` có thể tránh corrupt map nhưng không tự giải quyết unbounded cardinality và memory leak.

## 13. Lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Có thể do | Kiểm tra |
| --- | --- | --- |
| `Premain-Class` không tìm thấy | Agent JAR manifest hoặc class package sai | `jar --list`, xem `META-INF/MANIFEST.MF` |
| Agent không khởi động | `-javaagent` path/options sai, `premain` ném lỗi | Kiểm tra startup stderr và JAR deployment |
| `ClassNotFoundException` khi bootstrap lookup | `bridge.jar` sai path hoặc thiếu class entry | `JarFile`, `jar --list`, internal/binary name |
| `NoClassDefFoundError` tại probe | Loader của target không thấy helper hoặc dependency của helper | `getClassLoader`, `jdeps`, bootstrap append timing |
| `IllegalAccessError` | Runtime package/module/loader khác dự kiến | Class access flags, JPMS read/opens/exports |
| `NoSuchMethodError` | Helper ABI khác callsite | `javap`, owner/name/descriptor, version skew |
| App có counter nhưng collector không thấy | Hai bản helper ở hai loader hoặc collector đọc sai registry | In loader identity, kiểm tra JAR trùng |
| `collector: saw-app=false` trong lab | Transformer đăng ký muộn, class name sai hoặc agent không chạy theo hướng dẫn | Kiểm tra registration trước app load và filter |
| `collector: total-hits=0` | Callsite không tồn tại, app không gọi helper, helper khác identity | `javap -c`, `getClassLoader`, call count |
| Metric tăng nhưng backend trống | Chưa có exporter hoặc exporter bị lỗi | Phân biệt in-process counter với remote delivery |
| Startup chậm | Class parser/exporter chạy đồng bộ trong transformer | Profiling/JFR, giảm lock/I/O |
| JVM không dừng | Collector non-daemon còn sống, shutdown không đúng | Worker thread factory, `shutdown`/timeout |
| Mất event khi crash | In-memory state/queue chưa được flush | Bền vững/retention/ack policy |
| Trùng probe sau redefine | Transformer không idempotent | So output bytecode/marker và chain order |
| Memory leak sau redeploy | Static helper/collector giữ `ClassLoader`, `Class<?>`/plugin object | Heap dump, weak/eviction/close |
| Có callback nhưng không có probe | Transformer trả `null` hoặc output không đổi | Phân biệt callback và bytecode transformation |

Một nguyên tắc chẩn đoán: **xác định lỗi xảy ra ở ranh giới nào trước khi sửa**. Nếu lỗi ở bootstrap class visibility, tăng retry của exporter không giúp. Nếu lỗi ở network sink, sửa ASM stack maps không giải quyết. Bốn thành phần được tách giúp phát hiện đúng nơi phát sinh.

## 14. Quy trình QA và release checklist

### Bước A — Kiểm tra source/architecture

1. Entry point không import triển khai helper không cần thiết trước bước bootstrap setup.
2. Transformer không tham chiếu application runtime classes bằng class loader sai.
3. Helper không import agent core hoặc thư viện không bootstrap-visible.
4. Collector sở hữu worker, exporter/serializer và lifecycle; không có I/O trong helper `hit`.
5. Public helper API có method descriptors được version hóa và review.
6. Config/filter được công bố thread-safe, transformer writer/context per invocation.

### Bước B — Kiểm tra build artifacts

1. `bridge.jar` chỉ chứa bridge classes/resources dự kiến.
2. `agent.jar` có đúng `Premain-Class` và đủ agent classes.
3. Không trùng bridge class giữa agent/bridge JAR.
4. Dùng `jdeps` để kiểm tra dependency tĩnh của bridge.
5. `javap` classfile của app/test để xem owner/name/descriptor callsites.
6. Kiểm tra class-file major version tương thích JDK production.
7. Nếu có shading/relocation, test service resource và package collisions.
8. Ký/xác minh checksums nếu deployment yêu cầu; chỉ nạp agent được tin cậy.

### Bước C — Kiểm tra runtime

1. App chạy **không có bridge trong runtime `-cp`**, bridge được append sớm.
2. In/test loader identity của helper để xác nhận canonical bootstrap class.
3. Transformer thấy class mục tiêu; app vẫn có hành vi như trước khi instrument.
4. Counter/helper từ app và collector rich side phản ánh cùng state.
5. Test với custom loader/named module nếu production dùng chúng.
6. Với transformer thực, verify class bytes, stack maps và exception paths.
7. Benchmark latency, CPU, allocation, GC và class-load overhead.
8. Test concurrency, redefine/retransform, nhiều agent và error/failover.

### Bước D — Kiểm tra vận hành

1. Các cấu hình endpoint/credential không nằm trong bootstrap helper.
2. Collector có timeout, retry/backpressure/retention và giám sát lỗi.
3. Có metric dropped/export failure; không coi `offer(true)` là delivery ack.
4. Worker thread/shutdown hook không treo JVM vô hạn.
5. Không gửi PII, request body hoặc secrets trừ khi có policy rõ.
6. Có canary/rollback và biết giới hạn của `removeTransformer`.
7. Không ghi log mọi class JVM hoặc toàn bộ bytes theo mặc định.
8. Có tài liệu về bộ JDK/agent/bridge phiên bản nào tương thích.

## 15. Những hiểu nhầm cần loại bỏ

**Hiểu nhầm 1: “Đổi một class `Agent` thành bốn class là đã tách kiến trúc.”**  
Sai. Nếu bridge vẫn import exporter hoặc class được chèn vẫn gọi rich agent trực tiếp, dependency boundary chưa thay đổi.

**Hiểu nhầm 2: “Class transformer được gọi mỗi lần method ứng dụng chạy.”**  
Sai. `transform` xử lý class definition/update; helper callsite nằm trong business execution path.

**Hiểu nhầm 3: “`-javaagent` làm mọi custom class loader thấy mọi class agent.”**  
Sai. Cần tính đúng bootstrap/system/custom loader visibility.

**Hiểu nhầm 4: “`appendToBootstrapClassLoaderSearch` nên nhận nguyên fat agent JAR.”**  
Sai. Javadoc cảnh báo chỉ append classes/resources dành cho bootstrap; fat JAR dễ tạo lỗi package/version/loader.

**Hiểu nhầm 5: “Helper càng nhiều khả năng càng tốt.”**  
Sai. API helper càng rộng thì càng nhiều dependency, overhead, bảo mật và vấn đề tương thích.

**Hiểu nhầm 6: “`addTransformer` thành công tức code ứng dụng đã được sửa.”**  
Sai. Callback có thể không xảy ra với class đã load; nó có thể trả `null` và không tạo output mới.

**Hiểu nhầm 7: “Counter tăng tức metrics đã gửi lên backend.”**  
Sai. Collector/exporter và remote delivery là những bước khác.

**Hiểu nhầm 8: “Daemon collector chắc chắn flush khi process thoát.”**  
Sai. Daemon thread không giữ JVM sống; shutdown hook chỉ best effort khi shutdown bình thường.

**Hiểu nhầm 9: “`LongAdder.sum()` là snapshot nguyên tử trong mọi tình huống.”**  
Sai. Nó có thể không bao gồm updates đang diễn ra; phù hợp metric tổng hợp, không phải transaction ledger.

**Hiểu nhầm 10: “Để collector chạy ngay trong `ProbeBridge.hit()` sẽ đơn giản hơn và đủ nhanh.”**  
Không mặc nhiên. Network/serialization có thể block business thread, gây tail latency và recursion.

**Hiểu nhầm 11: “Có bridge JAR thì không còn vấn đề JPMS.”**  
Sai. Loader visibility, module read edges, access/opens là các điều kiện riêng.

**Hiểu nhầm 12: “Bỏ transformer sẽ hoàn nguyên mọi lớp đã instrument.”**  
Sai. `removeTransformer` không tự undo bytes đã được JVM áp dụng.

**Hiểu nhầm 13: “Bài lab đã có bytecode injection thật vì transformer đăng ký thành công.”**  
Sai. `WatchingTransformer` trả `null`, còn `DemoApp` gọi helper từ source. Lab tập trung vào packaging và 4-way separation.

**Hiểu nhầm 14: “Thay `hit():void` bằng `hit(int):void` không ảnh hưởng class cũ.”**  
Sai. Bytecode còn gọi `hit:()V` có thể lỗi `NoSuchMethodError`.

**Hiểu nhầm 15: “Cùng tên helper trong hai JAR luôn chia sẻ static state.”**  
Sai. Nếu chúng do hai loader khác nhau định nghĩa, đó có thể là hai runtime types và counters độc lập.

## 16. Tình huống chọn cách đóng gói

### Tình huống A — Agent metrics đơn giản, chỉ cần tổng số request

Dùng bridge bootstrap nhỏ có `LongAdder` hoặc histogram tối giản; rich collector đọc định kỳ rồi export. Không cần queue giữ từng event. Bài lab là nền tảng của thiết kế này. Đối với throughput rất cao, đo overhead lookup/counter trước khi thêm tags động.

### Tình huống B — Agent tracing muốn gửi từng event

Bridge nên có một `record(int code,long elapsedNanos)` với payload nhỏ hoặc interface/tiny bounded buffer. Rich collector drain và batch. Lọc/sampling/overflow là chính sách rõ ràng. Không chuyển raw `HttpServletRequest`/object của custom loader vào static bridge cache.

### Tình huống C — Instrument framework có nhiều class loaders

Tách bridge JAR bootstrap để target loaders có cơ hội resolve cùng public API; kiểm tra parent delegation, JPMS, helper identity. Bytecode transformer vẫn nằm agent core. Không dựa vào việc library exporter có trên system classpath để target luôn thấy được.

### Tình huống D — JFR diagnostic, không cần remote exporter ngay

Nếu chỉ cần chẩn đoán JVM, cân nhắc JFR Event với enabled/threshold và recording/stream, hạn chế custom data-plane. Tuy nhiên phải xác nhận module/class loader của supporting classes JFR trước khi đưa code vào bootstrap helper; không giả định helper có thể link tùy ý tới platform modules.

### Tình huống E — Agent attach vào JVM đã chạy

Đảm bảo `Agent-Class`/`agentmain`, startup support và capability đúng runtime. Class đã load không tự replay khi đăng ký transformer; phải chọn class mục tiêu và kiểm tra modifiability/capability trước khi thay đổi. Không coi mẫu startup-only với `premain` đã kiểm chứng attach scenario.

### Tình huống F — Cần audit giao dịch không được mất

Counter, in-memory queue hay JFR không phải nguồn sự thật bền vững. Chọn transaction log/transactional outbox/acknowledged durable sink phù hợp yêu cầu. Java agent có thể cung cấp dữ liệu chẩn đoán phụ trợ, nhưng không thay thế chính sách lưu trữ bắt buộc.

## 17. Câu hỏi tự kiểm tra

**1.** Bốn vai trò cần tách là gì?  
**Đáp:** Agent entry point, class-file transformer, helper gọi từ method đã instrument, và collector/exporter xử lý dữ liệu ngoài hot path.

**2.** Tại sao helper bootstrap không được import HTTP exporter trong agent core?  
**Đáp:** Bootstrap loader không mặc định nhìn thấy class system/agent loader; dependency đó có thể tạo lỗi link, đồng thời tăng chi phí business path.

**3.** Khi nào JVM gọi `premain`?  
**Đáp:** Khi khởi động bằng startup agent hợp lệ, trước application `main`.

**4.** `ClassFileTransformer.transform` có chạy trên mỗi request không?  
**Đáp:** Không. Nó xử lý class definition/update; probe/helper callsite chạy khi method nghiệp vụ chạy.

**5.** Vì sao trong lệnh runtime lab không có `bridge.jar` ở `-cp`?  
**Đáp:** Để chứng minh helper được JVM tìm qua bootstrap search do agent append, không bị system classpath che mất bài toán.

**6.** `ProbeBridge` được bootstrap định nghĩa có tự trở thành class của `java.base` không?  
**Đáp:** Không. Nó thuộc unnamed module của bootstrap loader.

**7.** `collector: total-hits=3` có chứng minh metrics đã lên một backend từ xa chưa?  
**Đáp:** Chưa. Lab chỉ snapshot/in số trong JVM, không có HTTP exporter.

**8.** Vì sao collector dùng daemon worker và shutdown hook?  
**Đáp:** Daemon không giữ JVM sống; hook đọc/flush số cuối khi JVM shutdown bình thường. Shutdown hook không chạy trong mọi tình huống kill/crash.

**9.** Vì sao `WatchingTransformer` có `AtomicBoolean sawApp`?  
**Đáp:** Cờ được callback class-loading thread cập nhật và collector/shutdown thread đọc, nên dùng state an toàn đồng thời.

**10.** Nếu `WatchingTransformer` trả `null`, class đã được chèn `ProbeBridge.hit()` chưa?  
**Đáp:** Chưa. Trong lab callsite được compile từ source ứng dụng; để inject thật cần transformer trả bytes mới hợp lệ.

**11.** Nếu muốn biến đổi class đã loaded trước `premain`/attach thì chỉ đăng ký transformer là đủ?  
**Đáp:** Không. Class-load event không tự replay; cần retransform/redefine khi được hỗ trợ và được phép.

**12.** Có được gộp cả agent core vào `bridge.jar` để deploy ít file hơn?  
**Đáp:** Không nên khi bridge được append bootstrap; Javadoc cảnh báo nguy cơ định nghĩa sai class và dependency không bootstrap-visible.

**13.** Nếu backend unavailable, nên xử lý ở đâu?  
**Đáp:** Collector/exporter chịu timeout/retry/drop/queue policy; không block trực tiếp trong helper hot path nếu telemetry best effort.

**14.** Cách kiểm tra bridge JAR không kéo thư viện ngoài?  
**Đáp:** Dùng `jar --list`, `jdeps` và runtime loader tests; không chỉ nhìn build configuration.

**15.** Vì sao static map trong bootstrap helper giữ `ClassLoader` của webapp nguy hiểm?  
**Đáp:** Nó có thể giữ deployment cũ không được GC sau redeploy, gây class-loader leak.

**16.** Nếu dùng Gradle/Maven, điều quan trọng hơn tên dependency scope là gì?  
**Đáp:** Artifacts thật và loader graph: bridge JAR chỉ có bridge classes, agent JAR không chứa bản trùng, runtime resolve đúng identity.

**17.** Vì sao không thể dùng một startup lab để kết luận attach hoặc named module đều hoạt động?  
**Đáp:** Attach có lifecycle/class đã loaded khác; named module có read/opens/exports riêng, cần integration tests đúng môi trường.

**18.** Chỉ có `transformer: registered` trong log đã đủ báo “instrumentation complete” chưa?  
**Đáp:** Chưa. Phải xác nhận callback, bytes được JVM chấp nhận, callsite được thực thi và dữ liệu được thu/xuất theo đúng yêu cầu.

## 18. Tài liệu tham khảo

- [JDK 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, `Boot-Class-Path`, `premain`/`agentmain`, class loaders, bootstrap supporting classes và JPMS.
- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, capability retransform/redefine và loader search limitations.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, chaining, `return null`, yêu cầu bảo toàn buffer input.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation và defining/initiating loaders.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter và giới hạn snapshot khi có update đồng thời.
- [JDK 17 — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): tác vụ lấy mẫu định kỳ và lifecycle của worker.
- [JDK 17 — `Runtime.addShutdownHook`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#addShutdownHook(java.lang.Thread)): hook shutdown và điều kiện hoạt động.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints và symbolic reference resolution.

**Ghi nhớ:** **Entry point lắp ghép**, **transformer xử lý classfile**, **helper làm ít việc nhất trên đường nóng**, và **collector xử lý dữ liệu ở ngoài đường nóng**. Với ứng dụng nhiều loader, đóng gói một bootstrap **bridge JAR tối thiểu** tách khỏi rich agent JAR; kiểm tra ABI, manifest, loader/module và startup order bằng test JVM thực tế. Một callback đã đăng ký, một bộ đếm đã tăng và một dữ liệu đã được backend chấp nhận là **ba bằng chứng khác nhau** — đừng gộp chúng thành một trạng thái “instrumentation OK”.