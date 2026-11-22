# Phân tách chi phí tạo tiến trình, nạp lớp, khởi tạo và warm-up

## 1. Vấn đề: “Java khởi động chậm” không chỉ là một con số

Khi một ứng dụng Java được khởi chạy, nhiều công đoạn có thể góp vào thời gian trước khi nó phục vụ kết quả hữu ích: hệ điều hành tạo tiến trình, launcher/JVM khởi tạo runtime, class loading và linking, class initialization, framework/application bootstrap, kết nối đến dependencies, và sau đó **JIT warm-up** để đạt hiệu năng vận hành ổn định.

Một câu “startup 2 giây” chỉ hữu ích khi đã trả lời **tính từ đâu đến đâu**. Chẳng hạn:

- **Process creation:** thời gian OS bắt đầu một tiến trình thực thi Java; liên quan scheduling, executable, environment, dynamic libraries.
- **VM/launcher startup:** Java launcher đọc flags/module/classpath, JVM tạo các runtime structures, memory areas và threads cần thiết trước khi gọi `main`.
- **Loading/linking:** tìm bytecode, tạo class representation, verification, preparation và resolution theo chính sách runtime.
- **Class initialization:** chạy static field initializers và static initialization blocks tương ứng, được biên dịch thành `<clinit>`.
- **Application initialization:** tạo DI container, scan annotations, init serializers, mở pools, đọc config, migrations, nạp dữ liệu.
- **First useful response/readiness:** thời điểm business flow đầu tiên hoặc readiness endpoint thực sự hoạt động.
- **Warm-up:** profiling, tiered compilation C1/C2, method linking, lazy classes, JIT inlining/deoptimization, cache và GC trạng thái dần thay đổi.
- **Steady state:** khoảng hệ thống có throughput/latency/GC/CPU tương đối ổn định dưới workload đại diện.

**Không được cộng tất cả bằng cách lấy thời gian của một câu `System.nanoTime()` đặt trong `main`**. Đoạn Java đó đã bỏ lỡ toàn bộ OS process creation và phần JVM startup trước `main`, và thời điểm class initializer của main class cũng có thể xảy ra trước câu đầu tiên của `main`.

> **Mục tiêu của bài:** phân rã các mốc có thể đo, chỉ ra ranh giới đo đạc, minh họa **load khác init**, và thiết kế benchmark tách **cold-start / first response / warm-up / steady-state**, thay vì gộp thành “JVM launch mất bao nhiêu ms”.

## 2. Timeline đầy đủ: OS launch đến peak/steady throughput

~~~text
mốc ngoài tiến trình                                    bên trong JVM
t0: OS nhận yêu cầu tạo process
       |
       v
[OS process startup + java launcher + JVM bootstrap]
       |
       v
[JVM khởi tạo runtime, hệ thống classloader, GC/JIT runtime]
       |
       v
[Load/Link/Initialize main class] ─────> t_main: vào main()
       |
       v
[Application/bootstrap: config, DI, pools, external dependencies]
       |
       +──────────────> t_first: first useful result
       |
       +──────────────> t_ready: readiness đạt tiêu chí
       |
       v
[Realistic warm-up: JIT compilation, caches, lazy class init, GC]
       |
       v
t_steady: candidate steady-state windows
       |
       v
[Optional saturation / peak / long-soak measurements]
~~~

Sơ đồ chỉ là **các nhóm công việc**. Trong hệ thống thực, chúng có thể chồng lắp:

- Thread pools và background tasks có thể làm application init **song song**.
- JIT compilation có thể xảy ra **trong lúc** bootstrap, trước first response.
- Lazy initialization có thể dời đến **sau readiness**, gây cold-path latency.
- CDS có thể rút ngắn một số class-loading work nhưng không loại toàn bộ linker, `<clinit>` hoặc application bootstrap.
- Một service báo ready trước khi “nóng” hoàn toàn; app latency có thể tiếp tục cải thiện sau readiness.
- `t_first` và `t_ready` không buộc theo một thứ tự tuyệt đối; phụ thuộc protocol và workload.
- Hệ thống có dynamic request mix có thể thay đổi workload liên tục và **không có một steady-state toàn cục duy nhất**.

**Những time windows phải được gắn nhãn theo mục đích**, không gộp thành “JVM start” rồi kết luận GC/JIT là nguyên nhân.

## 3. Công đoạn A — chi phí tạo tiến trình OS và khởi động JVM

### 3.1. Trước `main()` đã có điều gì?

Khi người dùng gọi:

~~~bash
java -cp app.jar com.example.Main
~~~

Hệ điều hành và launcher thực hiện công việc khởi tạo process và nạp chương trình. Sau đó HotSpot phải chuẩn bị VM runtime: parsing options, runtime libraries, hệ thống class loading, memory management, thread/runtime structures, GC/JIT services và chuẩn bị thực thi main class.

Những phần cụ thể phụ thuộc OS, Java vendor, JDK build, flags, filesystem, classpath/module path và thiết kế launcher. Không viết một “trình tự nano giây” bất biến cho mọi JVM.

**Không nhầm `javac` với `java`:** `javac` biên dịch source thành bytecode `.class` trước khi ứng dụng chạy. Khi launch bình thường bằng `java Main`, JVM **không tự gọi lại `javac` cho tất cả files**. JIT có thể biên dịch **bytecode thành native code** trong lúc chạy, đó là hoạt động khác hẳn javac.

### 3.2. Tại sao `System.nanoTime()` đầu `main()` không đo process creation?

~~~java
public static void main(String[] args) {
    long start = System.nanoTime();
    // Đo từ đây, không phải từ lúc OS tạo process.
}
~~~

Lúc code đầu `main` chạy, **VM đã được tạo đủ để gọi main**, main class đã đạt điều kiện class initialization. Vì vậy lấy số thời gian từ `start` tới `READY` chỉ đo **một phần application init**, không đo được chi phí OS spawn và các bước VM xảy ra trước `main`.

Muốn đo end-to-end từ bên ngoài, dùng một tiến trình cha hoặc load generator:

~~~bash
time java -cp . StartupPhasesDemo
~~~

Ví dụ PowerShell (Windows):

~~~powershell
Measure-Command { java -cp . StartupPhasesDemo | Out-Null }
~~~

Lệnh `time` hoặc `Measure-Command` đo **toàn thời gian process chạy tới exit**, gồm process launch, VM boot, work trong `main`, shutdown và overhead wrapper. Đây **không riêng là startup latency** nếu ứng dụng tiếp tục làm việc lâu.

**Đối với server sống lâu:** không đợi process exit mới lấy số; công cụ bên ngoài nên đo từ **lúc spawn/start request** đến khi nhận tín hiệu **first useful response** hoặc **readiness** theo điều kiện được định nghĩa.

### 3.3. Tách OS, launcher và VM startup có tuyệt đối được không?

Công cụ Java đơn lẻ thường **không đủ** để chia tách hoàn toàn time trước `main` thành `OS spawn`, `dynamic loader`, `VM create`, `classloader init` mà không đụng nhau. Cần instrument theo đúng cấp:

| Muốn đo | Quan sát thích hợp |
| --- | --- |
| OS process start → process exit | Shell external timer |
| Process start → first useful result | Parent-process timestamp / external probe |
| Process start → ready | Orchestrator event + health/ready protocol, hoặc external poll |
| OS spawn/exec and library loading | OS profiler, process tracing phù hợp với platform |
| VM startup trước `main` | Runtime-specific startup diagnostics/JFR + external measurement |
| Code trong `main` | `System.nanoTime()` milestones |
| Class loading cụ thể | HotSpot Unified Logging, JFR nếu bật |
| Class initialization cụ thể | Logs class-init + marker trong `<clinit>` |
| JIT warm-up | Compilation events, throughput time windows, JFR |

Không cộng trực tiếp những duration từ **khác clocks, khác mốc hoặc phase chồng lắp**. Nếu `mainElapsedMs=20`, external `time java` đo 55 ms, phần chênh 35 ms **không được tự gắn nhãn hoàn toàn là JVM bootstrap**: nó còn shell/OS process handling, output, shutdown và những khoảng đo không tương đương.

## 4. Công đoạn B — nạp lớp, liên kết và khởi tạo là ba bước khác nhau

Java Language Specification (JLS 17, Chương 12) tách:

- **Loading:** tìm dạng nhị phân class/interface, dùng class loader phù hợp để tạo representation của type.
- **Linking:** gồm **verification**, **preparation**, và **resolution** có thể được làm sớm hoặc lazy theo giới hạn specification.
- **Initialization:** thực thi các class-variable initializers và static initializer blocks, tương ứng `<clinit>` khi compiler tạo ra.

Không được hiểu rằng “class vừa được load thì static initializer chắc đã chạy”. Không được đồng nhất **preparation** với **initialization**.

### 4.1. Loading: tìm bytecode và tạo class representation

Classpath/module path, resource lookup, đọc `.class`, classloader delegation, verification dependencies và built-in/custom class loaders có thể ảnh hưởng chi phí. Một framework scan hàng chục nghìn classes hoặc đọc annotation metadata theo nhiều chiến lược có thể tốn startup time, nhưng **không phải mọi lần metadata scan đều thực sự initialize toàn bộ classes**.

Loading cost còn liên quan disk/page cache và archive. Lần mở đầu classpath JAR trên OS cache lạnh khác hẳn khi OS đã cache file. Đó là lý do benchmark startup cần kiểm soát **cold/warm filesystem state** nếu nó ảnh hưởng workload thực.

### 4.2. Linking: verify, prepare, resolve

| Bước | Ý nghĩa |
| --- | --- |
| Verification | Xác minh bytecode/formats/type constraints đáp ứng yêu cầu JVM |
| Preparation | Cấp phát/đặt giá trị mặc định cho `static` fields và một số cấu trúc metadata |
| Resolution | Chuyển symbolic references trong constant pool sang thực thể runtime thích hợp |

**Resolution có thể lazy.** Class đã được load, verify và chuẩn bị nhưng một số symbolic references chỉ được resolve khi đường code tương ứng thực sự được sử dụng. Vì thế khi một route mới lần đầu được gọi, thêm linking work có thể xuất hiện **sau startup/ready**.

JLS/JVMS áp đặt hành vi và lỗi hợp lệ nhưng không định nghĩa một chi phí mili giây cố định cho tất cả classes.

### 4.3. Initialization: `<clinit>`

Các static field initializers không phải compile-time constants, và `static { ... }`, thường được compiler sắp vào method đặc biệt `<clinit>`.

~~~java
final class Expensive {
    static int[] table = buildTable();
    static {
        System.out.println("Expensive initialized");
    }
}
~~~

Đây là **class minh họa**, `buildTable()` do application định nghĩa. Khi lần sử dụng chủ động yêu cầu initialization, JVM chạy `<clinit>` theo quy tắc một lần trên mỗi **class identity** trong một JVM execution, với synchronization semantics được specification quy định.

**Một class identity** gồm binary name và defining class loader; hai classloaders khác nhau có thể tạo hai `Class` objects khác nhau với initialization state riêng. Không được phát biểu “static initializer chỉ chạy một lần trên toàn bộ mọi process/JVM và classloaders”.

### 4.4. Các trigger khởi tạo class quan trọng

Trong nhiều trường hợp, class initialization được kích hoạt trước:

- Tạo instance bằng `new` của class cần init.
- Truy cập/ghi `static` field không phải constant variable theo JLS.
- Gọi `static` method.
- Reflection hoặc method handles trong những thao tác có active-use semantics.
- Khởi tạo main class trước khi JVM gọi `main()`.

Một điểm kinh điển:

~~~java
static final int CONST = 7; // constant variable nếu khởi tạo bằng constant expression
static int counter = 7;     // không phải constant variable
~~~

Truy cập một **constant variable** có thể không buộc class khai báo được initialize, trong khi truy cập `counter` có thể kích hoạt initialization. Không dùng `static final` đơn thuần làm tiêu chí: `static final int X = parse(...)` không phải compile-time constant.

`SomeType.class`, `ClassLoader.loadClass(name)` hoặc `Class.forName(name, false, loader)` **có thể có class representation mà không bắt buộc chạy `<clinit>` ngay**. Nhưng một `Class.forName(name)` overload mặc định **thường yêu cầu initialization**.

## 5. Java 17 runnable: nạp lớp mà chưa khởi tạo

Tạo file **`StartupPhasesDemo.java`**:

~~~java
public final class StartupPhasesDemo {
    static class InitProbe {
        static {
            System.out.println("probe=<clinit>");
        }
        static int value = 41;
    }

    static class LazyService {
        static {
            System.out.println("lazy=<clinit>");
        }
        static String work() {
            return "READY";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main=entered");
        Class<?> type = Class.forName(
                "StartupPhasesDemo$InitProbe",
                false,
                StartupPhasesDemo.class.getClassLoader());
        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("aboutToInitialize=true");
        System.out.println("probeValue=" + InitProbe.value);
        System.out.println("serviceResult=" + LazyService.work());
        System.out.println("end=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 StartupPhasesDemo.java
java StartupPhasesDemo
~~~

**Stdout chính xác đã biên dịch và chạy thực tế trên JDK 24 với `--release 17`:**

~~~text
main=entered
loaded=InitProbe
aboutToInitialize=true
probe=<clinit>
probeValue=41
lazy=<clinit>
serviceResult=READY
end=true
~~~

### Tại sao output theo thứ tự này?

1. Vào `main()` ⇒ main class đủ điều kiện đã initialize (nó không có static block in marker).
2. `Class.forName(binaryName, false, loader)` yêu cầu find/load/link type tương ứng **nhưng không yêu cầu initialize** nó; vì vậy chưa in `probe=<clinit>`.
3. `type.getSimpleName()` có thể đọc metadata để trả `InitProbe`, không kích hoạt static block của chính `InitProbe` trong ví dụ này.
4. Lần đầu đọc `InitProbe.value` là **active use** của static nonconstant field, nên JVM khởi tạo `InitProbe` trước ⇒ in `probe=<clinit>` rồi `probeValue=41`.
5. Lần đầu gọi `LazyService.work()` cũng kích hoạt initialization của `LazyService` ⇒ in `lazy=<clinit>`, rồi method trả `READY`.
6. Hai classes có thể đã được load/link vào những thời điểm khác nhau; **mốc in marker chỉ phản ánh initialization**, không phải toàn bộ chi phí trước đó.

**Không đem đoạn này kết luận mọi JVM sẽ đọc JAR tại thời điểm `Class.forName` được gọi.** Class có thể đã loaded, dữ liệu nằm trong CDS archive/OS page cache hoặc JVM đã resolve liên quan sớm. Ví dụ chứng minh **phân biệt hai hành vi API**, không phải đo cost ổ cứng.

### `Class.forName` nhiều overload khác nhau

~~~java
Class.forName("pkg.Type");                        // initialize theo API contract
Class.forName("pkg.Type", false, someClassLoader); // không yêu cầu initialize
~~~

Đây là **mảnh code minh họa**, `pkg.Type` và `someClassLoader` cần tồn tại thật. Không dùng overload có boolean sai rồi tin rằng mình đã đo riêng class load.

## 6. Instrument class loading và class initialization bằng HotSpot logs

Trên HotSpot Java 17+, **Unified Logging** có tags cho class load và class init. Ví dụ:

~~~bash
java '-Xlog:class+load=info,class+init=info' StartupPhasesDemo
~~~

Đây là mẫu cú pháp Bash; trên PowerShell, có thể đặt cùng option trong single quotes. JVM cụ thể nên được xác minh bằng:

~~~bash
java -Xlog:help
~~~

- `class+load=info` cho biết nhiều classes được load và nguồn/loader tương ứng, thường có timestamp decorations.
- `class+init=info` cho các initialization events khi VM phát log ở mức tương ứng.
- `class+resolve=debug` hoặc những tags khác có thể giúp xem resolution khi bản JVM hỗ trợ, nhưng log volume lớn.
- Dùng `file=...:uptime,level,tags` để ghi log và so mốc startup theo uptime.
- `PrintCompilation` giúp quan sát JIT events, nhưng **không phải class loading**.

**Lưu ý quan trọng:** log markers khác với timers phase hoàn chỉnh. Một dòng `class+load` thường chỉ là **event** ghi class, không cung cấp đầy đủ “load class này tốn N ms độc lập hoàn toàn”. Logger cũng có overhead, đặc biệt khi có hàng nghìn events.

Có thể chạy:

~~~bash
java '-Xlog:class+load=info:file=classes.log:uptime,level,tags' StartupPhasesDemo
~~~

Sau đó tìm binary names `StartupPhasesDemo$InitProbe` và `StartupPhasesDemo$LazyService`; trên lần kiểm chứng JDK 24, log thực tế ghi được cả hai classes. Nhưng class log **không tự chứng minh** initialization cost; cần init events hay markers khác.

### Dùng JFR trong các bài điều tra thật

Java Flight Recorder (JFR) có các class load, class define, compilation, GC, CPU và thread events tùy **recording settings, event thresholds và JVM build**. Ví dụ:

~~~bash
java '-XX:StartFlightRecording=filename=startup.jfr,settings=profile' StartupPhasesDemo
~~~

Sau khi file tồn tại:

~~~bash
jfr summary startup.jfr
jfr print --events jdk.ClassLoad,jdk.Compilation startup.jfr
~~~

Một recording rất ngắn có thể không chứa events mong muốn, hoặc profile settings không bật từng event; **không được suy luận rằng việc không thấy `jdk.ClassLoad` nghĩa JVM không nạp lớp**. Khi cần phân tích sâu, bật những events phù hợp trong `.jfc`, kiểm soát overhead và quan sát đủ thời gian.

## 7. Công đoạn C — application/framework initialization

Tách **class initialization** của JLS ra khỏi **application bootstrap**. Một Spring/Quarkus/microservice hoặc CLI tool có thể tự thực hiện:

- Parse configuration, environment, YAML, certificate/key stores.
- Khởi tạo dependency injection context và object graphs.
- Quét classpath, tìm annotations, load configuration classes.
- Khởi tạo logging, metrics registry, tracing/exporters.
- Khởi động thread pools và scheduler.
- Tạo JDBC/HTTP connection pools, handshake TLS.
- Chạy DB migrations, kiểm tra schema, lấy secrets hoặc config qua network.
- Preload caches, load dictionaries/models/templates/rules.
- Start server socket, đăng ký routes và health probes.
- Thực hiện readiness checks hoặc chờ dependencies sẵn sàng.

Những công việc này **không phải mặc nhiên là `<clinit>`**. Chúng có thể chạy trong constructors, methods, container lifecycle hooks, background tasks hoặc startup scripts.

### Tại sao cần phân tách rõ?

Hai ứng dụng dùng đúng một JDK và tập thư viện tương tự có thể có “startup” rất khác nhau vì **bootstrap logic**. Nếu 1,2 giây nằm trong connect DB timeout thì đổi GC collector hoặc tăng JIT compiler threads khó giải quyết nguyên nhân.

### Instrument semantic milestones

Có thể đặt application-defined markers:

~~~text
process_spawn_requested
main_entered
config_loaded
di_context_created
db_pool_ready
http_listener_bound
first_successful_business_request
readiness_accepted
~~~

Sau đó đo đồng hồ monotonic **giữa các mốc phát từ cùng một process**. Với milestones thuộc process bên ngoài, phải correlate qua wall timestamps/protocol spans một cách đúng clock.

Để các logs đáng dùng:

1. Ghi phase name ổn định và run ID riêng, tránh trộn nhiều processes.
2. Ghi cả duration/clock source, không chỉ `"finished"`.
3. Hạn chế instrumentation nặng trong hot startup.
4. Tách synchronous critical path và asynchronous work.
5. Đánh dấu khi readiness trả về **trước khi** background tasks hoàn tất.
6. Ghi failures/timeouts và retries, không chỉ successful startup.

**Không lấy tổng thời gian của các sub-tasks chạy song song rồi so với end-to-end elapsed**: tổng CPU/task durations có thể lớn hơn wall-clock critical path.

## 8. Công đoạn D — JIT warm-up và trạng thái ổn định

HotSpot thường bắt đầu với interpreter và dùng tiered compilation (C1/C2, tùy VM flags) khi profiling cho thấy một đoạn code đủ hot. Vùng mã chưa được gọi có thể chưa JIT compile. JVM còn có OSR cho loops dài và khả năng deoptimization/recompilation nếu giả định profiling thay đổi.

Vì vậy `main()` hoặc first request hoàn tất **không đồng nghĩa JIT warm-up hoàn tất**. Một app có 20 routes có thể làm nóng 2 routes phổ biến trước; 18 routes còn lại vẫn gặp cold-path loading/JIT khi traffic lần đầu chạm vào.

### Tác động không chỉ JIT

Bên cạnh JIT, throughput/latency có thể thay đổi vì:

- Lazy class initialization/late linking.
- Pool/cache warm state.
- GC allocation rate, heap occupancy và promotion.
- OS filesystem page cache.
- Database page cache, prepared statements, query plan.
- TLS handshake/session resumption.
- CPU frequency scaling, scheduler, resource contention.
- JIT background compiler threads tranh CPU quota với request threads.

**Một batch thứ hai nhanh hơn batch thứ nhất không tự chứng minh code đã được C2 compile**, vì còn vô số hiệu ứng khác. Muốn biết JIT activity, dùng `-XX:+PrintCompilation`, JFR compilation events và, nếu thật sự cần kiểm chứng native optimization, công cụ compiler IR/assembly phù hợp build.

### “Steady state” là khái niệm vận hành, không phải trạng thái do JVM hứa

Có thể gọi một measurement window là **candidate steady state** khi:

1. Same offered load và request mix đại diện.
2. Throughput, p99, CPU/GC và heap live set không còn trend chuyển tiếp rõ.
3. Không có compiler/classloading bursts đủ lớn làm biến dạng kết quả.
4. External dependencies/caches ổn định.
5. Các cửa sổ lặp lại cho kết quả tương đối nhất quán và có đủ samples.

Không có public API `Jvm.isSteadyState()` bảo đảm chương trình đã đạt “peak”. Vì vậy warm-up policy cần được xác định dựa trên dữ liệu đo, không chọn một số giây tùy ý cho mọi ứng dụng.

## 9. Java 17 runnable: đo class-loading marker, init marker và warm-up batches

Tạo file **`WarmupPhasesDemo.java`**:

~~~java
import java.util.Locale;

public final class WarmupPhasesDemo {
    static class Kernel {
        static final int[] values = new int[1024];

        static {
            for (int i = 0; i < values.length; i++) {
                values[i] = i * 7 + 1;
            }
            System.out.println("kernel=<clinit>");
        }

        static long compute(int seed) {
            long sum = seed;
            for (int value : values) {
                sum += value ^ seed;
            }
            return sum;
        }
    }

    public static void main(String[] args) throws Exception {
        long enteredMain = System.nanoTime();
        System.out.println("main=entered");

        long beforeLoad = System.nanoTime();
        Class.forName("WarmupPhasesDemo$Kernel", false,
                WarmupPhasesDemo.class.getClassLoader());
        long afterLoad = System.nanoTime();
        System.out.println("loadWithoutInit=done");

        long beforeInit = System.nanoTime();
        int size = Kernel.values.length;
        long afterInit = System.nanoTime();
        System.out.println("kernelSize=" + size);

        long checksum = 0;
        for (int batch = 0; batch < 3; batch++) {
            long beforeBatch = System.nanoTime();
            for (int i = 0; i < 3000; i++) {
                checksum += Kernel.compute(batch * 3000 + i);
            }
            long elapsed = System.nanoTime() - beforeBatch;
            System.out.printf(Locale.ROOT,
                    "batch%dMs=%.3f%n", batch, elapsed / 1_000_000.0);
        }
        System.out.println("checksum=" + checksum);
        System.out.printf(Locale.ROOT, "loadingMs=%.3f%n",
                (afterLoad - beforeLoad) / 1_000_000.0);
        System.out.printf(Locale.ROOT, "initMs=%.3f%n",
                (afterInit - beforeInit) / 1_000_000.0);
        System.out.printf(Locale.ROOT, "mainElapsedMs=%.3f%n",
                (System.nanoTime() - enteredMain) / 1_000_000.0);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WarmupPhasesDemo.java
java WarmupPhasesDemo
~~~

**Các dòng bất biến đã kiểm chứng trên JDK 24 với target Java 17, theo thứ tự xuất hiện:**

~~~text
main=entered
loadWithoutInit=done
kernel=<clinit>
kernelSize=1024
~~~

Tiếp theo chương trình in:

~~~text
batch0Ms=<thời gian môi trường>
batch1Ms=<thời gian môi trường>
batch2Ms=<thời gian môi trường>
checksum=44137339276
loadingMs=<thời gian môi trường>
initMs=<thời gian môi trường>
mainElapsedMs=<thời gian môi trường>
~~~

Dấu `<thời gian môi trường>` mô tả những số **không cố định**; không phải stdout nguyên văn. Trong một lần chạy thử, `batch0Ms` lớn hơn `batch1Ms` và `batch2Ms`, nhưng kết quả này **không được dùng làm bằng chứng mỗi máy sẽ warm-up theo đúng tỷ lệ**.

### Giải thích các mốc

- `enteredMain` chỉ đo từ thời điểm đã ở trong main.
- `Class.forName(..., false, ...)` chỉ yêu cầu class được load/link theo API contract; không kích hoạt `<clinit>` của `Kernel`.
- `Kernel.values.length` là active use của nonconstant static array field: JVM initialize Kernel trước khi đọc giá trị, nên marker `kernel=<clinit>` xuất hiện trước `kernelSize=1024`.
- `initMs` đo cả overhead quanh static field access, việc chạy `<clinit>` và những chi phí runtime/JIT liên quan, **không phải “thời gian mọi static initialization trong app”**.
- `loadingMs` là elapsed của **một lời gọi Class.forName tại một lần chạy**; ngoài class loader work còn có call overhead, logging nếu bật và ảnh hưởng OS/JIT. Nó không phải toàn bộ class-loading cost của process.
- `batch0Ms`, `batch1Ms`, `batch2Ms` là các khoảng đo tính toán; không khẳng định batch thứ ba đạt steady state.
- `checksum` giữ kết quả observable để giảm nguy cơ dead-code elimination; vẫn không thay thế chuẩn benchmark.
- `mainElapsedMs` đo toàn bộ section sau `enteredMain`, **bao gồm** các khoảng đã đo con và output/formatting. **Không cộng `mainElapsedMs + initMs + loadingMs`** vì sẽ đếm lặp.

**Đọc code có chủ đích:** chương trình chèn `System.out.println` giữa các mốc để người học nhìn rõ thứ tự. Trong microbenchmark nghiêm túc, printing có thể ảnh hưởng timings; nên tách measurement khỏi output khi đo từng operation.

## 10. Quan sát JIT: warm-up khác class init

Trong Java 17 HotSpot, có thể chạy:

~~~bash
java -XX:+PrintCompilation WarmupPhasesDemo
~~~

Diagnostics có thể ghi phương thức `WarmupPhasesDemo$Kernel::compute` được compile ở một hoặc nhiều tiers. Có thể chạy đối chiếu:

~~~bash
java -Xint WarmupPhasesDemo
~~~

`-Xint` chạy interpreter-only: useful để hiểu vai trò JIT, nhưng **không phải mô phỏng startup của JVM có JIT mặc định**. Code cold trên JVM mặc định vẫn được quyền JIT compile khi đủ hot.

Không coi mỗi dòng `PrintCompilation` như một lời hứa compilation đã hoàn thành cho mọi hot path. HotSpot có C1/C2, OSR, deoptimization, inlining và tier policies; dấu hiệu compilation cần phân tích với current build.

### Các con số batch không thể thay một load test

Một app xử lý 9.000 lần `Kernel.compute` trong 3 batches không đo:

- Process spawn → first useful response.
- Sự sẵn sàng của DB, TLS, HTTP connections.
- Request queueing và p99/p99.9 trên arrival rate cố định.
- Dynamic route/class loading và memory retention theo thời gian.
- GC full/concurrent behavior trên workload dài.
- CPU quota/backpressure của dịch vụ trong container.

Vì vậy dùng ví dụ cho **phân tách khái niệm**, không dùng nó xếp hạng JDK hoặc framework.

## 11. Phân biệt cold start và lazy first hit

Đây là một bẫy rất thực tế trong framework:

~~~text
Process starts
       |
       +-- load Main, init DI context, bind HTTP port
       |
       +-- /health GET 200 ⇒ readiness OK
       |
       +-- /report request lần đầu
             +-- class ReportRenderer được load
             +-- static fields/serializer registry initialize
             +-- template compile, DB query plan/cache load
             +-- JIT/profile hot route bắt đầu
             +-- FIRST_HIT_LATENCY cao
       |
       +-- /report request lần sau ⇒ có thể nhanh hơn
~~~

Một service có thể đạt **readiness** sớm nhưng chưa đáp ứng **first-hit latency SLO** cho route quan trọng. Các lựa chọn:

1. Thêm warm-up bằng **đúng request mix** có ý nghĩa.
2. Preload những classes/static data thực sự quan trọng.
3. Dời công việc ít dùng sang lazy init để **giảm startup critical path**, chấp nhận cold first hit.
4. Tách “ready to accept basic traffic” và “ready for critical workload” nếu cần.
5. Bật tracing theo request route để tìm class/init/JIT/DB costs.

**Không phải cứ preload tất cả class là tốt.** Eager init có thể tăng startup duration, heap footprint và CPU burst; lazy init lại làm first-hit latency cao. Đây là trade-off theo SLO/lifecycle, không phải một tối ưu duy nhất cho mọi hệ thống.

## 12. CDS và AppCDS: tối ưu một phần của class loading

**Class Data Sharing (CDS)** cho phép JVM sử dụng một archive chứa metadata của những classes đã được chuẩn bị/chia sẻ, giảm một phần startup work và memory footprint. Oracle JDK 17 có **default CDS archive** với selected core classes; **Application CDS (AppCDS)** có thể mở rộng phạm vi cho classes từ ứng dụng.

Tác động tiềm năng:

- Một phần metadata có thể được memory-map từ archive.
- Nhiều JVM trên cùng host có thể chia sẻ read-only pages tương ứng.
- Giảm một số bytecode parsing/loading/preparation-related work.
- Có lợi nhất khi class loading là phần đáng kể của startup, tùy app/JDK/config.

**CDS không tự chạy hết `<clinit>` của ứng dụng, không thay business bootstrap, không mở DB connection sẵn, không tự làm nóng C2 compiled code của mọi route.** Không gọi CDS “giải pháp warm-up hoàn toàn”.

### Bật/tắt CDS trong thí nghiệm có kiểm soát

Ví dụ trên HotSpot Oracle/OpenJDK 17 phù hợp:

~~~bash
java -Xshare:auto StartupPhasesDemo
java -Xshare:off StartupPhasesDemo
~~~

`-Xshare:auto` cho JVM dùng archive khi phù hợp, `-Xshare:off` tắt CDS cho diagnostic comparison. Cần nhiều repetitions, cùng JDK/classpath/filesystem cache, process mới mỗi run. Không kết luận sự chênh lệch của một lần chạy là tác động riêng của CDS vì OS cache và scheduler noise.

`-Xshare:on` ép dùng archive và có thể khiến JVM fail khi archive không phù hợp; tài liệu Oracle cảnh báo **không dùng như default production option** trong môi trường archive/config không chắc chắn.

AppCDS có thể được tạo từ class list hoặc **dynamic archive** (HotSpot flag `-XX:ArchiveClassesAtExit=...`) phù hợp JVM version. Cần tuân thủ constraints archive và deployment, không đưa một đường dẫn archive thử nghiệm vào production mà không kiểm tra compatibility/version.

## 13. Những flags HotSpot thường hữu ích để phân tích startup

| Tùy chọn/công cụ | Mục đích | Hạn chế |
| --- | --- | --- |
| `-Xlog:class+load=info` | Ghi load class events | Không phải phase duration độc lập |
| `-Xlog:class+init=info` | Xem class init events khi được hỗ trợ | Logger có overhead, không tự bằng tổng `<clinit>` elapsed |
| `-XX:+PrintCompilation` | Biết JIT compile methods nào, tiers/timing | Không đo OS spawn/class loading |
| `-Xint` | Chạy interpreter-only để so cơ chế | Không phải baseline cold JVM mặc định |
| `-Xshare:auto/off` | So CDS effect | Phải cùng JDK, process forks và caching |
| `-Xlog:gc=info` | Ghi GC activity, pauses | Không đo full startup |
| `jfr`, JFR settings | Correlate CPU, class, compiler và allocation events | Phải bật đúng events, overhead |
| `jcmd PID VM.flags` | Xem JVM flags của process | Dùng PID thật, permissions phù hợp |
| `jcmd PID VM.command_line` | Xác minh lệnh launch | Process có thể đã exit khi đo startup ngắn |

### Ghi log ảnh hưởng kết quả

Startup của app vốn rất ngắn có thể bị log I/O chi phối nếu bật `class+load=trace` và in hàng chục nghìn classes. Vì thế nên có:

- **Diagnostic runs** bật logging để xác định nguyên nhân.
- **Benchmark runs** dùng cấu hình logging giống production hoặc giống giữa các candidates.
- Ghi rõ logger configuration trong báo cáo, tránh so run A `trace` với run B `off`.
- Nếu cần `file=...`, chọn file names riêng, rotation, quyền truy cập và không trộn processes.
- Khi xuất JFR/dumps/logs, lưu ý classnames/path/credentials có thể là dữ liệu nhạy cảm.

## 14. JVM process spawn đo một lần không đủ để kết luận

Mô tả một quy trình đo ngắn:

1. `N` lần gọi một **process Java mới** cho mỗi ứng viên, mỗi lần đo từ bên ngoài.
2. Randomize thứ tự ứng viên (A/B/B/A) để giảm bias của OS filesystem cache, thermal/CPU changes.
3. Ghi `java -version`, vendor/build, OS, CPU quota, heap flags, CDS settings, classpath, working directory.
4. Tách **cold filesystem/cache** và **warm OS cache** thành hai kịch bản nếu quan trọng; không mặc định mỗi JVM mới là OS cache lạnh.
5. Báo median/p95/p99 startup, min/max và variability, không chỉ fastest run.
6. Với server, dùng external first-response/readiness instrumentation thay `time java` đợi process exit.
7. Test startup failure/timeouts và retries, không chỉ instances thành công.
8. Thu class-load/JIT/JFR/OS metrics ở một số run diagnostic để giải thích từng phase.
9. Phân biệt main-internal elapsed với process external elapsed; không cộng durations đếm trùng.
10. Kiểm thử tiếp sau startup: first-hit latency và steady-state throughput, vì một tối ưu có thể chuyển chi phí sang nơi khác.

### OS caches và working set

Nếu lần đầu mở JAR mất lâu vì filesystem page faults nhưng lần thứ hai nhanh hơn nhờ page cache, **không được quy ngay tất cả delta cho JIT**. Một JVM process mới không có native code cache “nóng” từ process trước theo nghĩa ứng dụng, nhưng OS file cache và external DB cache có thể được tái sử dụng.

Nếu chạy trong container, thêm image start/cgroup scheduling, CPU throttling, memory pressure và network startup vào bối cảnh. `-XX:ActiveProcessorCount` **không tự cấp CPU quota**; chỉ ảnh hưởng JVM ergonomics, trong khi OS/container thực thi giới hạn tài nguyên.

## 15. Cold vs warm, startup vs throughput: chọn KPI nào?

| Workload | KPI startup | KPI sau startup | Điều cần nhấn mạnh |
| --- | --- | --- | --- |
| CLI chạy dưới một giây | Full process elapsed / time-to-result | Ít ý nghĩa nếu process exit sớm | VM boot, classloading, init quan trọng |
| Batch job chạy vài phút | Time-to-first-batch + total job time | Throughput khi batch steady | Startup có thể nhỏ so với toàn job |
| API server chạy dài | Ready time, first useful request | p99/p99.9, throughput, GC, memory | Lazy routes và JIT warm-up |
| Serverless/short-lived function | Cold invocation latency | Warm invocation latency | Startup lặp lại nhiều lần |
| Autoscaling pod | Process/deploy → ready; traffic ramp | SLO-constrained throughput | Cold pods cần ramp/backpressure |
| Desktop/interactive GUI | First interactive render | UI responsiveness | Không coi process-created là ready |

**Một phương án “startup nhanh” không tự là phương án “throughput cao”.** Ví dụ giảm compilation work ban đầu có thể cải thiện first response nhưng làm peak throughput kém; eager initialize có thể làm ready muộn nhưng giảm first-hit spikes. Đó là trade-off cần đo **theo vòng đời và SLO thực**.

### Tổng work trên vòng đời ngắn

Với function sống 2 giây, giảm 0,5 giây startup có thể rất có giá trị ngay cả khi steady-state CPU throughput không đổi. Với process sống 24 giờ, 0,5 giây startup có thể ít giá trị hơn nếu tăng CPU 10% trong suốt ngày.

**Không áp một mục tiêu “tối ưu startup bằng mọi giá” cho cả hai.**

## 16. Những sai lầm phổ biến cần tránh

1. **“Đặt `nanoTime()` đầu main thì đo được OS spawn.”** Sai; process/JVM đã init đủ để gọi main.
2. **“Class được load thì `<clinit>` lập tức chạy.”** Sai; load/link/init tách biệt.
3. **“Preparation chính là chạy static initializer.”** Sai; preparation khác initialization.
4. **“Mọi symbolic reference đều resolve tại startup.”** Sai; resolution có thể lazy.
5. **“Class.forName(..., false, ...) bắt buộc chạy static blocks.”** Sai.
6. **“`static final` nào cũng là compile-time constant.”** Sai; chỉ constant variables theo JLS.
7. **“Thời gian `Class.forName` bằng toàn bộ JVM classloading cost.”** Sai.
8. **“Có `JIT` thì phải compile tất cả classes trước khi ready.”** Sai.
9. **“Tốc độ batch hai nhanh chứng minh C2 compiled.”** Chưa đủ bằng chứng.
10. **“CDS có nghĩa không còn class initialization.”** Sai.
11. **“CDS archive làm nóng DB pool/JIT/HTTP routes.”** Sai.
12. **“Main in READY là server đã đáp ứng SLO.”** Không, trừ khi marker gắn đúng contract.
13. **“First successful response = steady state.”** Sai.
14. **“Một process mới luôn cold filesystem cache.”** Sai.
15. **“Tổng subphase durations bằng wall time nếu tasks song song.”** Sai, có thể đếm trùng.
16. **“`-Xint` mô phỏng y hệt cold JIT app.”** Sai.
17. **“GC log tắt là không có GC.”** Sai, chỉ không có log tương ứng.
18. **“JFR profile luôn bật mọi ClassLoad/Compilation event.”** Sai.
19. **“Fastest run đáng báo hơn median hay p99.”** Không có đủ cơ sở.
20. **“Gộp startup, warm-up và long-run throughput thành một số ms.”** Không có ý nghĩa đo lường.
21. **“Một tối ưu lazy init không có chi phí.”** Sai; chi phí có thể chuyển sang request đầu tiên.
22. **“Nhờ JIT mà OS process creation rẻ đi.”** Sai; hai lớp chi phí khác nhau.
23. **“So Java17 và Java24 mà không ghi phiên bản thì kết luận chung được.”** Sai, JVM đã thay đổi.
24. **“Readiness vừa thành công thì mọi route đã class-init và compiled.”** Sai.

## 17. Checklist để điều tra một ứng dụng Java startup chậm

- [ ] Định nghĩa **external start** và **response/readiness end** trước khi đo.
- [ ] Kiểm tra command line, Java vendor/build, OS, classpath, JAR size, CDS state.
- [ ] Phân biệt *process start → main* với *main → app ready* và *ready → warm throughput*.
- [ ] Chạy 5–10 lần độc lập, process mới, đo median/variance và ghi filesystem cache state.
- [ ] Bật `class+load` và `class+init` trong diagnostic runs để tìm lazy/eager classes.
- [ ] Với Java `<clinit>`, xác định trigger active use, không đánh đồng loading.
- [ ] Instrument phase durations của config/DI/DB/TLS/cache/HTTP bootstrap.
- [ ] Nếu có background init, đo critical path và readiness dependency thật.
- [ ] Kiểm tra JIT events nếu warm-up throughput/latency thay đổi.
- [ ] Kiểm tra GC/class loading/OS CPU và page faults, không quy tất cả cho JIT.
- [ ] Kiểm tra CDS/AppCDS trên cùng JDK/build, không nhầm với class init.
- [ ] Với server, đo first business request, first-hit từng route và p99 sau ready.
- [ ] Đo plateau bằng windows, không chỉ một batch nhanh.
- [ ] Với container, ghi CPU quota, memory limit, I/O/network startup.
- [ ] Phân biệt chi phí được loại bỏ với chi phí được **dời sang first request**.
- [ ] Không phá correctness: static init side effects, connection readiness và data consistency vẫn phải đúng.
- [ ] Ghi failure/timeout và các trường hợp process chết lúc bootstrap.
- [ ] Kết luận từ nhiều nguồn dữ liệu, không chỉ một log timestamp.

## 18. Tự kiểm tra: 18 câu và đáp án ngắn

1. Đặt timer ở câu đầu `main()` có đo OS process creation không? **Không**.
2. Loading, linking, initialization có thể diễn ra ở những thời điểm khác nhau không? **Có**.
3. Classloader load class xong `<clinit>` có bắt buộc đã chạy chưa? **Chưa**.
4. `Class.forName(name, false, loader)` có yêu cầu initialize class không? **Không**.
5. Đọc static nonconstant field có thể kích hoạt initialization không? **Có**.
6. Trong ví dụ `StartupPhasesDemo`, marker `probe=<clinit>` in trước hay sau `loaded=InitProbe`? **Sau**.
7. JLS preparation có phải chạy `static {}` không? **Không**.
8. Resolution luôn eager trước main? **Không**, có thể lazy.
9. App readiness có bằng time-to-C2-peak không? **Không**.
10. Static init trigger có thể nằm ở first request không? **Có**, nếu class đó được dùng lần đầu ở route.
11. CDN/CDS archive có làm sẵn TLS/DB session cho mọi app không? **Không**.
12. Default CDS archive trong JDK17 có thể tiết kiệm phần nào? **Một số class loading/metadata work và memory sharing**, tùy environment.
13. `time java Program` chạy tới exit có đo duy nhất JVM bootstrap không? **Không**, còn main work và shutdown.
14. Một process mới có nghĩa OS page cache chắc lạnh? **Không**.
15. Batch thứ hai nhanh hơn có chứng minh JIT level 4 không? **Không**.
16. Nếu first HTTP route chậm dù `/health` báo ready, nên xem gì? **Lazy class/init, pools, serializers, network, JIT và cache trên route đó**.
17. Chạy `java -Xint` có phải mô phỏng cold JIT startup chuẩn không? **Không**.
18. Với CLI 300 ms, tối ưu phần nào thường đáng xem trước? **Full process-to-result time**, không chỉ throughput hot path.

## 19. Nguồn chính thống Java 17

- **JLS 17, Chapter 12 — Execution**, loading/linking/initialization và VM startup: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **JVMS 17, Chapter 5 — Loading, Linking and Initializing**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **`Class.forName` Java SE 17**, overload initialize boolean: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)
- **`ClassLoader` Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Oracle JDK 17 java command** (`-Xlog`, `-Xint`, `-XX:+PrintCompilation`, CDS flags): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 Class Data Sharing**, default CDS archive và AppCDS: https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html
- **Oracle JDK 17 `jcmd`**, VM flags, JFR diagnostic tools: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Oracle JDK 17 `jfr` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **OpenJDK JMH project**, tránh sai lệch khi đo Java micro-workload: https://openjdk.org/projects/code-tools/jmh/

**Kết luận kỹ thuật:** Quá trình đưa một ứng dụng Java tới trạng thái hữu ích cần nhìn như **nhiều chi phí có ranh giới đo khác nhau**: OS process creation → launcher/JVM boot → class load/link → class init → application bootstrap/first response/readiness → JIT/cache/GC warm-up → steady state. Timer trong `main` bỏ sót mọi bước trước `main`; class được load **không đồng nghĩa đã init**; CDS có thể giảm một phần class-loading cost **không có nghĩa làm sẵn `<clinit>` hoặc JIT peak**. Hãy kết hợp **external milestones, class/JIT/GC logs, JFR và application tracing** trên cùng workload/JDK/resources, đo nhiều runs và báo riêng cold start, first-hit latency, readiness, warm-up ramp và steady-state SLO.
