# Đo riêng chi phí khám phá, biên dịch, khởi tạo và gọi sau khi làm nóng

## 1. Vì sao phải tách phép đo hiệu năng?

Trong Java có runtime extensibility (SPI, plugin JAR, custom class loader, JavaCompiler, reflection hoặc JShell), một con số “thời gian tải và chạy plugin” thường trộn lẫn nhiều thao tác:

- **Khám phá (discovery):** tìm danh sách provider, metadata, descriptor hoặc module plugin để biết có thể dùng loại extension nào.
- **Biên dịch (compilation):** dịch source Java thành bytecode (nếu plugin được biên dịch lúc chạy); không phải plugin JAR đã đóng gói nào cũng cần pha này.
- **Khởi tạo (initialization):** có thể bao gồm nạp/link class, chạy static initializer, tìm constructor/factory, tạo object và lifecycle hook; phải nói rõ đo phần nào.
- **Gọi sau khi làm nóng (warmed invocation):** thực thi operation trên **instance đã có** sau khi JVM có cơ hội profile và JIT compile đường chạy nóng.

Nếu đo tất cả trong một đoạn `System.nanoTime()` rồi gọi là “giá một lần invoke” sẽ sai phạm vi. Khám phá hay biên dịch thường là **setup cost**, còn gọi method có thể lặp hàng triệu lần. Hai dạng chi phí tác động khác nhau đến startup SLA và throughput.

Mục tiêu bài này là **định nghĩa rõ bốn ranh giới đo**, viết chương trình Java 17+ chạy độc lập, kiểm tra đầu ra có ý nghĩa, phân biệt cold/warm, nhận biết bẫy microbenchmark và biết khi nào chuyển sang JMH/JFR.

## 2. Vẽ ranh giới trước khi chọn timer

~~~text
JAR / source / plugin manifest
    |
    +--> A. Discovery: enumerate names/types (chưa tạo instance)
    |
    +--> B. Compilation: source -> byte[] (nếu runtime compile)
    |
    +--> C. Class preparation / constructor / provider activation
    |
    +--> D. Invoke trên instance đã được warm-up
~~~

Bốn đường trên là **hệ thống phân loại chi phí**, không phải một thứ tự bắt buộc. Ví dụ một plugin Java source có thể được biên dịch **trước** khi được đăng ký để discovery; một hệ thống `ServiceLoader` dùng iterator có thể **khám phá và khởi tạo provider trong cùng vòng lặp**. Khi lập phép đo, phải tách các operation đó thành công việc cụ thể.

Đặt bốn câu hỏi trước khi đo:

1. **Một operation là gì?** Một lượt quét một provider hay tất cả provider? Một lần compiler task hay build toàn dự án? Một lần `newInstance()` hay toàn bộ hook `start()`? Một lần `apply()` hay một request gồm network I/O?
2. **Cold hay warm?** JVM mới chạy, class chưa load, OS cache chưa có, JIT chưa compile hay đã chạy nhiều lần?
3. **Bao gồm và loại trừ gì?** Filesystem scan, đọc JAR, metadata, classloading, constructor reflection lookup, GC, logging, network, test harness?
4. **Metric nào phù hợp?** Median/p95 latency, số ops/s, allocation bytes/op, CPU utilization, GC pauses, startup-to-ready?

Một báo cáo chỉ có “12 ns” nhưng không nói đơn vị operation, JVM/CPU, số lần lặp và đoạn code được đo gần như không thể sử dụng để ra quyết định.

## 3. Pha khám phá: đừng nhầm tạo `ServiceLoader` với liệt kê provider

`ServiceLoader` có cơ chế lazy discovery. Lời gọi:

~~~java
ServiceLoader<Task> serviceLoader =
        ServiceLoader.load(Task.class, apiLoader);
~~~

chỉ tạo loader dịch vụ, chưa nhất thiết đã tìm hết các implementation. Đây là đoạn mã tích hợp (cần `Task`, `apiLoader` và import `java.util.ServiceLoader`).

Nếu mục tiêu là **quét metadata provider nhưng chưa khởi tạo provider**:

~~~java
List<Class<?>> types = ServiceLoader.load(Task.class, apiLoader)
        .stream()
        .map(ServiceLoader.Provider::type)
        .toList();
~~~

`Provider.type()` cung cấp provider type; không gọi `Provider.get()`. Quá trình enumerate có thể đọc `META-INF/services`, phân tích tên, tải type metadata, kiểm tra provider hợp lệ và hưởng cache class/resource. Nó **không phải** thao tác “đọc một chuỗi tên thuần túy”, nhưng tránh cố ý thêm constructor execution vào timed discovery.

| Đoạn code | Thực tế có thể đo |
|---|---|
| Chỉ `ServiceLoader.load(...)` | Khởi tạo loader object, chưa duyệt provider |
| `stream().map(Provider::type).toList()` | Tìm provider types, không cố ý tạo instance |
| `for (Task provider : loader)` | Có thể kèm **tạo provider instances** do iterator |
| `Provider.get()` | Lấy/tạo instance, nên tính vào pha khởi tạo |
| Duyệt lại **cùng loader** | Có thể hưởng cache nội bộ, khác fresh discovery |
| `ServiceLoader.reload()` rồi duyệt | Xóa cache của instance; không reset JVM/classloading/JIT/OS cache |

**Đơn vị của demo:** mỗi `discovery operation` tạo `ServiceLoader` mới với loader SPI tường minh, duyệt toàn bộ provider **type** và kiểm tra tên. Một descriptor có một provider nên mỗi operation là **scan 1 provider**. Khi so với runtime khác, số provider phải giữ nhất quán.

**Đừng trộn phạm vi:** quét filesystem `plugins/*.jar`, duyệt `URLClassLoader` resources, JPMS service provider resolution và metadata parsing có thể là các pha con khác nhau. Đo đúng giải pháp đang triển khai; `ServiceLoader.loadInstalled` cũng không phải API quét thư mục plugin do ứng dụng tự quản lý.

## 4. Pha biên dịch: tách compiler task khỏi nạp/chạy class

Đối với dynamic Java source, có thể dùng `javax.tools.JavaCompiler` trong cùng JVM:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
Boolean ok = compiler.getTask(
        null, fileManager, diagnostics, compilerOptions,
        null, sourceFiles).call();
~~~

Đây là đoạn API minh họa, chưa phải chương trình riêng. `ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi runtime image thiếu compiler; cần JDK 17+ với `jdk.compiler` khả dụng.

**Pha compile** nên được xác định theo phạm vi:

- **Compile task in-process:** `JavaCompiler.getTask().call()` và các đối tượng nguồn, diagnostics, file manager liên quan.
- **Compile in memory:** source và output `JavaFileObject` gắn với `String`/`ByteArrayOutputStream`; compiler **vẫn có thể truy cập classpath** để resolve dependencies.
- **Compile on disk:** ghi `.class` ra filesystem, có thêm I/O và filesystem cache.
- **Fork javac:** gọi một process `javac` mới; gồm process/JVM startup và các công việc ngoài compiler task.
- **Compile + load + instantiate:** nếu có nạp class/output và gọi constructor sau compile, không được đặt nhãn đơn giản “compilation”.

Trong demo, chương trình dùng `SimpleJavaFileObject` làm source trong bộ nhớ, `ForwardingJavaFileManager` giữ output `.class` thành byte array, kiểm tra bytes thực sự tồn tại, và **không load hoặc tạo instance của class vừa biên dịch**. Mỗi operation đo một compiler task với một class nguồn nhỏ.

Các yếu tố cần ghi lại: chiều dài source, số compilation units, classpath/module path, compiler flags, annotation processors, file manager reuse, JDK và cache state. Lệnh mẫu truyền `--release 17`, `-proc:none` và classpath của host; lựa chọn `-proc:none` tránh chạy annotation processors không cần thiết trong thí nghiệm.

## 5. Pha khởi tạo: đừng gộp class init và constructor

Từ “khởi tạo” trong Java có nhiều lớp ý nghĩa:

1. **Class loading:** loader tìm và định nghĩa type từ bytes.
2. **Linking/verification/resolution:** JVM kiểm tra và liên kết các symbolic references khi cần.
3. **Static class initialization (`<clinit>`):** chạy static initialization **một lần cho mỗi runtime class identity**.
4. **Object construction:** phân bổ instance, instance initialization và constructor **mỗi lần tạo object**.
5. **Plugin activation:** gọi `start()`, inject config, đăng ký listener, mở file/socket/connection tùy contract.

Để đo **per-instance constructor** một cách rõ ràng, demo chuẩn bị trước:

~~~java
Class<? extends Task> type =
        provider.type().asSubclass(Task.class);
Constructor<? extends Task> constructor = type.getConstructor();
Task stable = constructor.newInstance(); // ngoài timed measurement
~~~

Rồi đo **nhiều lần**:

~~~java
Task another = constructor.newInstance();
~~~

Lệnh `getConstructor()` và lần class initialization đầu không nằm trong timed constructor benchmark. `Constructor.newInstance()` vẫn có reflection overhead, allocation, code của constructor và ảnh hưởng `volatile` sink. Demo **không** khẳng định đây là cold-start time.

Muốn đo **first class initialization** phải chủ động tạo JVM hoặc class loader mới để class có identity chưa được initialize; không thể gọi lại `<clinit>` của cùng class đã được JVM khởi tạo. Nếu đo cả tạo loader, tìm bytecode, linking và lần `new` đầu, hãy báo `cold load+initialize+construct` chứ không gọi là chi phí constructor thuần.

Với một provider trong named module, `ServiceLoader.Provider.get()` có thể dùng constructor hoặc provider factory method. Nếu hệ thống thật dùng factory, hãy benchmark **factory path thực tế**; không coi `newInstance()` của demo là đại diện cho mọi SPI.

## 6. Pha gọi sau khi làm nóng: giữ instance ổn định

Khi đo invocation:

~~~java
Task prepared = constructor.newInstance(); // ngoài vùng đo

// Warm-up đúng operation và các đường chạy quan trọng
int result = prepared.apply(input);
~~~

Đây là đoạn minh họa, các biến phải khai báo trong method thực tế. **Không** gọi `ServiceLoader.load(...)`, `JavaCompiler.getTask(...)` hay `constructor.newInstance()` bên trong vòng lặp timed invocation nếu muốn tách chỉ số hot call.

Tại sao warm-up quan trọng?

- JVM/JIT thu thập profiling và biên dịch/tối ưu mã theo thời gian; lần gọi đầu có thể chạy bằng interpreter hoặc còn phải resolve dependencies.
- Call interface có thể được **devirtualize/inline** nếu JVM đã biết implementation; kết quả đo không còn đơn giản là một “phí gọi interface”.
- Garbage collection, safepoints, tiered compilation, deoptimization và CPU scheduling ảnh hưởng latency.
- JIT có thể loại bỏ tính toán nếu kết quả không quan sát được.

Trong demo, `CallJob` duy trì một input tăng dần và một checksum tích lũy; checksum được giữ lại cuối benchmark. Việc này giảm rủi ro kết quả bị loại bỏ hoàn toàn, nhưng phép đo **vẫn bao gồm** loop, cập nhật input và checksum, interface call và JIT optimizations. Nó là **chi phí invocation trên workload demo**, không phải một con số tuyệt đối cho `invokeinterface`.

## 7. Cách đọc đồng hồ và cách thống kê

`System.nanoTime()` được dùng bằng **hiệu hai giá trị** để đo elapsed time, không phải Unix timestamp. Với thao tác ngắn, bao nhiều invocation vào một batch:

~~~java
long start = System.nanoTime();
for (int i = 0; i < repetitions; i++) {
    job.run();
}
long elapsed = System.nanoTime() - start;
double nsPerOp = (double) elapsed / repetitions;
~~~

Đây là **đoạn minh họa tích hợp** với `Job job` đã được định nghĩa; một phép đo dùng được cần thêm warm-up, nhiều rounds, checks và thống kê.

**Quy trình có giá trị học tập:**

1. Chạy warm-up đúng operation trước khi tính thời gian.
2. Chạy nhiều measured rounds với **cùng kích thước batch**.
3. Tính elapsed `nanoTime` của **mỗi round**, không đo từng call bằng một cặp timer.
4. Dùng median của các rounds rồi chia số operations/batch để có ước lượng `ns/op`.
5. Báo units, số samples, JVM/JDK/CPU và trạng thái warm.
6. Khi tối ưu thật, dùng **JMH** và nhiều fork JVM, đồng thời báo variance/p95 khi latency tail là vấn đề.

Không cộng median của các pha đo ở những trạng thái khác nhau để suy ra chính xác end-to-end p99. Pha phụ thuộc cache, JIT, GC và scheduler có thể tương tác mạnh. `System.nanoTime` đo elapsed wall-clock time; không đồng nghĩa CPU cycles của riêng một thread.

## 8. Ví dụ hoàn chỉnh Java 17+: benchmark tách bốn pha

Demo dùng classpath SPI để dễ tái lập. Nó có một provider, compiler Java tích hợp và một method nhỏ. Bốn số timing là **biến động theo hệ thống**, còn các dòng xác minh về provider, class được biên dịch và checksum sẽ ổn định.

### 8.1. Cấu trúc dự án

~~~text
phase-bench/
  src/
    demo/
      spi/Task.java
      impl/BasicTask.java
      PhaseBench.java
  out/
    META-INF/services/demo.spi.Task
~~~

`out` được tạo bằng lệnh compile và tạo descriptor. Descriptor phải có tên file đúng là **fully qualified service interface name** `demo.spi.Task`, nội dung là binary name của provider.

### 8.2. Service API — `src/demo/spi/Task.java`

~~~java
package demo.spi;

public interface Task {
    int apply(int value);
}
~~~

`Task.apply(int)` là operation có output deterministic, không có network/disk I/O. Nó giúp minh họa việc lấy checksum và hot call.

### 8.3. Provider — `src/demo/impl/BasicTask.java`

~~~java
package demo.impl;

import demo.spi.Task;

public final class BasicTask implements Task {
    public BasicTask() {}

    @Override
    public int apply(int value) {
        return value * 3 + 1;
    }
}
~~~

Provider public, có public no-arg constructor và implement service interface chung. `ServiceLoader` classpath sẽ tìm nó từ descriptor đúng.

### 8.4. Host benchmark — `src/demo/PhaseBench.java`

~~~java
package demo;

import demo.spi.Task;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.reflect.Constructor;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.ServiceLoader;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class PhaseBench {
    private static volatile Object sink;
    private static final String DYNAMIC_SOURCE = """
            package demo.generated;
            import demo.spi.Task;
            public final class CompiledTask implements Task {
                public CompiledTask() {}
                public int apply(int value) { return value + 7; }
            }
            """;

    @FunctionalInterface
    interface Job {
        void run() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader apiLoader = Task.class.getClassLoader();
        List<ServiceLoader.Provider<Task>> providers =
                ServiceLoader.load(Task.class, apiLoader).stream().toList();
        if (providers.size() != 1) {
            throw new IllegalStateException("Expected exactly one provider");
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        Class<? extends Task> type =
                providers.get(0).type().asSubclass(Task.class);
        Constructor<? extends Task> constructor = type.getConstructor();
        Task stable = constructor.newInstance();
        CallJob callJob = new CallJob(stable);

        Job discovery = () -> {
            List<String> names = ServiceLoader.load(Task.class, apiLoader)
                    .stream().map(p -> p.type().getName()).toList();
            if (!names.equals(List.of("demo.impl.BasicTask"))) {
                throw new IllegalStateException("Discovery mismatch");
            }
            sink = names;
        };
        Job compilation = () -> compileOne(compiler);
        Job initialization = () -> sink = constructor.newInstance();

        double discoveryNs = medianNsPerOp(discovery, 3, 7, 40);
        double compilationNs = medianNsPerOp(compilation, 1, 5, 1);
        double initializationNs = medianNsPerOp(initialization, 3, 7, 20_000);
        double callNs = medianNsPerOp(callJob, 3, 7, 100_000);
        sink = callJob.checksum;

        System.out.println("providers=" + providers.size());
        System.out.println("compiled-class=demo.generated.CompiledTask");
        System.out.printf(Locale.ROOT, "discovery=%.1f ns/op%n", discoveryNs);
        System.out.printf(Locale.ROOT, "compilation=%.2f ms/compile%n",
                compilationNs / 1_000_000);
        System.out.printf(Locale.ROOT, "initialization=%.1f ns/newInstance%n",
                initializationNs);
        System.out.printf(Locale.ROOT, "warmed-call=%.1f ns/apply%n", callNs);
        System.out.println("checksum-positive=" + (callJob.checksum > 0));
    }

    private static double medianNsPerOp(
            Job job, int warmRounds, int measuredRounds, int batch)
            throws Exception {
        for (int r = 0; r < warmRounds; r++) {
            for (int i = 0; i < batch; i++) {
                job.run();
            }
        }
        long[] times = new long[measuredRounds];
        for (int r = 0; r < measuredRounds; r++) {
            long start = System.nanoTime();
            for (int i = 0; i < batch; i++) {
                job.run();
            }
            times[r] = System.nanoTime() - start;
        }
        Arrays.sort(times);
        return (double) times[measuredRounds / 2] / batch;
    }

    private static void compileOne(JavaCompiler compiler) throws Exception {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            MemoryFiles files = new MemoryFiles(standard);
            JavaFileObject source =
                    new Source("demo.generated.CompiledTask", DYNAMIC_SOURCE);
            Boolean ok = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none", "-classpath",
                            System.getProperty("java.class.path")),
                    null, List.of(source)).call();
            if (!Boolean.TRUE.equals(ok)) {
                throw new IllegalStateException(
                        "Compilation failed: " + diagnostics.getDiagnostics());
            }
            byte[] output = files.getBytes("demo.generated.CompiledTask");
            if (output == null || output.length == 0) {
                throw new IllegalStateException("Missing compiled class");
            }
            sink = output;
        }
    }

    private static final class CallJob implements Job {
        private final Task task;
        private int input;
        private long checksum;
        CallJob(Task task) {
            this.task = task;
        }
        @Override
        public void run() {
            checksum += task.apply(input++);
        }
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String source;
        Source(String name, String source) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class BinaryOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();
        BinaryOutput(String name, Kind kind) {
            super(URI.create("mem:///" + name.replace('.', '/')
                    + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return output;
        }
        byte[] getBytes() {
            return output.toByteArray();
        }
    }

    private static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, BinaryOutput> outputs = new HashMap<>();
        MemoryFiles(StandardJavaFileManager standard) {
            super(standard);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String name,
                JavaFileObject.Kind kind, FileObject sibling) {
            BinaryOutput target = new BinaryOutput(name, kind);
            outputs.put(name, target);
            return target;
        }
        byte[] getBytes(String name) {
            BinaryOutput output = outputs.get(name);
            return output == null ? null : output.getBytes();
        }
    }
}
~~~

### 8.5. Biên dịch, đăng ký provider và chạy

Đứng ở root `phase-bench/`, dùng Bash (Linux/macOS hoặc Git Bash):

~~~bash
mkdir -p out/META-INF/services

javac --release 17 -d out \
  src/demo/spi/Task.java \
  src/demo/impl/BasicTask.java \
  src/demo/PhaseBench.java

printf '%s\n' 'demo.impl.BasicTask' \
  > out/META-INF/services/demo.spi.Task

java -cp out demo.PhaseBench
~~~

Trên Windows PowerShell, lệnh tương đương để tạo descriptor:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -d out src/demo/spi/Task.java src/demo/impl/BasicTask.java src/demo/PhaseBench.java
[System.IO.File]::WriteAllText(
    "out/META-INF/services/demo.spi.Task",
    "demo.impl.BasicTask" + [Environment]::NewLine)
java -cp out demo.PhaseBench
~~~

**Điểm quan trọng:** `javac --release 17` biên dịch **host và provider** trên disk ở `out`. Đây là bước **chuẩn bị demo**, không phải pha B được đo. Pha B của chương trình gọi `JavaCompiler` **trong JVM đang chạy** để biên dịch `demo.generated.CompiledTask` thành output trong bộ nhớ. Chương trình **không đưa compiled class đó vào class loader hoặc tạo instance**, để không trộn pha B với C.

Cần runtime JDK 17+ có `jdk.compiler`. Chương trình dùng `System.getProperty("java.class.path")` làm classpath cho compilation task; với `java -cp out` nó tìm được SPI từ `out`. Nếu `ToolProvider.getSystemJavaCompiler()` trả `null`, chương trình cố ý từ chối.

### 8.6. Output nào đúng?

Trong cấu hình ví dụ có một descriptor và một provider, các dòng ổn định gồm:

~~~text
providers=1
compiled-class=demo.generated.CompiledTask
...
checksum-positive=true
~~~

Ba dòng trên có dấu `...` để **lược bỏ** bốn dòng timing ở giữa, không phải output nguyên văn của JVM. Bốn dòng timing thực tế mang định dạng:

~~~text
discovery=<number> ns/op
compilation=<number> ms/compile
initialization=<number> ns/newInstance
warmed-call=<number> ns/apply
~~~

`<number>` là **vị trí minh họa** cho giá trị đo được mỗi lần chạy; không có con số cố định để dùng làm expected output. Đã kiểm thử biên dịch bằng `javac --release 17` và chạy thành công trên OpenJDK 24: một provider, class được compiler tạo trong memory, cả bốn timing được in và `checksum-positive=true`.

Chỉ nên coi các dòng ổn định là assertions. Thời gian đo không được so như một “chuẩn” giữa các máy, vì phụ thuộc JDK, CPU/JIT, OS cache, GC và tiến trình nền.

### 8.7. Mỗi job đang bao gồm những gì?

| Job | Timed operation | Phần đã chủ động loại ra |
|---|---|---|
| `discovery` | Tạo ServiceLoader mới, duyệt provider type, xác minh tên, ghi sink | Không gọi `Provider.get()`, không compile, không constructor |
| `compilation` | Tạo diagnostics/file manager/source, compile bytecode trong memory, xác nhận output | Không load/instantiate class vừa biên dịch |
| `initialization` | Lặp `Constructor.newInstance()`, ghi `volatile` sink | Constructor lookup và static class init đầu đã nằm ngoài timed loop |
| `CallJob` | `Task.apply(input++)` trên một instance, cộng checksum | Không tạo provider hoặc compile/discover |

Đây là **scope của chính ví dụ**, không phải định nghĩa duy nhất cho mọi hệ thống. Với hệ thống production, initialization có thể bao gồm dependency injection, config, network connections và lifecycle; một benchmark chỉ đo constructor rỗng sẽ bỏ qua các phần đó.

### 8.8. Warm-up và measured rounds

Hàm `medianNsPerOp` warm-up rồi chạy các measured batches. Cấu hình demo:

| Pha | Warm-up rounds | Measured rounds | Operation mỗi measured round |
|---|---:|---:|---:|
| Discovery | 3 | 7 | 40 lượt scan |
| Compilation | 1 | 5 | 1 compiler task |
| Initialization | 3 | 7 | 20.000 constructor invocations |
| Invocation | 3 | 7 | 100.000 method invocations |

Chúng ta tính **median thời gian của batch**, sau đó chia số operation của batch. Đây là lựa chọn giảng dạy, không bảo đảm JIT đạt steady state với mọi workload. Đặc biệt compile có số vòng ít, còn hot call rất nhanh; dùng JMH cho số đo cần độ tin cậy kỹ thuật.

## 9. Sai lầm phổ biến khi đo riêng từng pha

### 9.1. `ServiceLoader.load` trông nhanh nhưng vì chưa làm việc

Vì discovery lazy, một benchmark chỉ tạo loader object sẽ đánh giá thấp tổng chi phí tìm service. Hãy duyệt đến type hoặc instance đúng theo câu hỏi đang đo.

### 9.2. Duyệt provider bằng iterator rồi gọi đó là discovery-only

Iterator có thể tạo provider instances. Nếu constructor nặng, kết quả bị gộp discovery+initialization. Dùng `Provider.type` cho phép tách mục tiêu đo metadata khỏi instantiation.

### 9.3. Khởi tạo class nhiều lần nhưng `<clinit>` chỉ chạy một lần

JVM không chạy static initializer lại trên cùng class identity. Với cold class-loading, phải dùng JVM mới hoặc loader/class identity mới theo thiết kế, và ghi rõ đã tính phí tạo loader chưa. `ServiceLoader.reload()` không reset class metadata, JIT hoặc OS filesystem cache.

### 9.4. Đo compilation bằng cách fork `javac` rồi so với `JavaCompiler.getTask`

Một bên tính JVM/process startup và I/O, bên kia là compiler task trong JVM đang chạy. Hai phép đo có câu hỏi khác nhau. Nếu workflow thật fork `javac` thì nên đo end-to-end fork; nếu compiler API chạy ở server thì đo in-process.

### 9.5. Đo một lời gọi siêu ngắn bằng hai `nanoTime`

Timer overhead có thể lớn bằng hoặc lớn hơn operation. Dùng batch để giảm tỷ lệ overhead, nhưng batch vẫn gồm loop, state và JIT effects; kết quả không tự động là “chi phí thuần của lệnh invoke”.

### 9.6. JIT loại bỏ workload không có kết quả quan sát

Ví dụ code hợp lệ nhưng dễ tối ưu mất:

~~~java
long total = 0;
for (int i = 0; i < 1_000_000; i++) {
    int unused = i * 3 + 1;
}
System.out.println(total);
~~~

`unused` không ảnh hưởng output, nên JIT có thể bỏ phép tính. Benchmark đúng nên có observable return/sink, workload đa dạng và kiểm tra tính đúng đắn; JMH cung cấp cơ chế hữu ích như return value và `Blackhole`.

### 9.7. Dùng một median để che giấu GC/p99

Constructor và compiler tạo allocations; median thấp không phủ nhận p99 spike do GC hoặc lock contention. Với yêu cầu SLA, theo dõi cả allocation rate, GC pauses, percentiles, CPU time và throughput.

### 9.8. So các hệ thống khác số provider hoặc input

Một lượt scan một provider không tương đương quét hàng trăm JAR. Biên dịch một class ngắn khác rất xa biên dịch module lớn. Một invocation nhỏ không đại diện HTTP/database. Cần cố định workload, số provider/JAR, classpath, compiler options và data set.

### 9.9. Nhầm warm-up của phương thức với warm-up của toàn hệ thống

Đã warm một call không có nghĩa module layer, network pool, serializer, compiler hoặc mọi nhánh logic đã warm. Hãy warm **đúng operation và đường chạy** cần đánh giá; với startup SLA vẫn phải đo cold path riêng.

### 9.10. Bật profiling/logging rồi so tuyệt đối với bản không bật

JFR/JVM classloading logs có overhead nhất định; bật logging chi tiết có thể thay timing. Dùng profiling để tìm nguyên nhân, rồi đo so sánh trong điều kiện nhất quán.

## 10. JMH: công cụ phù hợp khi cần kết luận microbenchmark

**JMH (Java Microbenchmark Harness)** của OpenJDK chuyên hỗ trợ warm-up, forks, measured iterations, state và các bẫy tối ưu JIT khi đo operation nhỏ.

Ví dụ skeleton **minh họa** (không compile được chỉ với JDK, cần dependency/plugin annotation processor JMH):

~~~java
import demo.spi.Task;
import demo.impl.BasicTask;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class TaskInvocationBenchmark {
    private Task cached;
    private int input;

    @Setup(Level.Trial)
    public void setup() {
        cached = new BasicTask();
    }

    @Benchmark
    public int invokeAfterWarmup() {
        return cached.apply(input++);
    }
}
~~~

Ở đây `@Setup(Level.Trial)` không nằm trong timed invocation method; `@Fork` chạy phép đo trên các JVM forks khác nhau, giúp tách một phần JIT state. Nhưng **JMH không tự sửa benchmark sai phạm vi**: nếu đặt compile hoặc provider construction vào `@Benchmark` thì bạn vẫn đang đo chúng. Benchmark discovery/compilation/initialization nên có state, sample, warmup/fork và result validation tương ứng với từng đơn vị operation.

Không suy ra “JMH score” từ output của `PhaseBench`; hai hệ đo có cấu trúc, thời lượng và cách thống kê khác nhau.

## 11. JFR và chẩn đoán nguyên nhân

**Java Flight Recorder (JFR)** giúp nhìn CPU, allocation, GC, thread/blocking và một số hoạt động classloading theo cấu hình. Ví dụ lệnh của JDK:

~~~bash
jcmd PID JFR.start name=plugin-bench settings=profile duration=30s filename=plugin-bench.jfr
~~~

`PID` là số process id Java có quyền attach. Đây là **lệnh minh họa**; demo chạy nhanh nên có thể kết thúc trước khi thu đủ dữ liệu. Với service đang xử lý traffic, tạo workload đủ dài và đánh dấu các mốc bắt đầu/kết thúc pha để đối chiếu JFR events.

Có thể dùng logging class load/GC khi debug:

~~~bash
java -Xlog:class+load=info,gc*=info -cp out demo.PhaseBench
~~~

Bật `-Xlog` sẽ tăng lượng log và có thể thay đổi chính đo timing; không dùng bản có log verbose làm cơ sở so tuyệt đối với bản không log. Công cụ `jcmd` và `javap` hữu ích khi cần xem JVM flags, bytecode, class descriptors và thông tin chẩn đoán. Dùng profiler để hiểu *vì sao* compiler/constructor/hot call chậm, thay vì chỉ dựa vào một số ns/op.

## 12. Chi phí một lần và chi phí mỗi request

Một mô hình kế toán xấp xỉ, chỉ khi các pha được định nghĩa **không chồng lấn**:

~~~text
T_lifetime ~= T_discovery + T_compilation
            + T_load_init + T_activate
            + number_of_calls * avg_T_warmed_call
~~~

Đây không phải công thức cộng p99, cũng không có nghĩa tất cả plugin đều cần compilation. Một plugin JAR được build sẵn thường có `T_compilation_at_runtime = 0`; nó vẫn có startup scan, classloading và initialization. Với dynamic plugin, compile có thể chiếm phần lớn startup.

- **Plugin tải một lần, gọi rất nhiều:** tăng tốc warmed invocation có thể giá trị về CPU/throughput; đồng thời startup latency vẫn có thể phụ thuộc compilation.
- **Plugin bị biên dịch/tạo mới mỗi request:** việc loại compile và constructor ra khỏi request path thường quan trọng hơn tối ưu method vài nanosecond.
- **Plugin scan thường xuyên theo polling:** discovery/cache có thể có ảnh hưởng; cần đo bằng đúng tần suất, số JAR và version churn.
- **SLA p99 end-to-end:** nên thu tracing/JFR, request latencies và GC, không lấy median hot method đại diện toàn dịch vụ.

Điểm quyết định tối ưu là **chi phí thực tế nhân tần suất thực tế**, không phải hạng mục nào có đơn vị ns đẹp hơn.

## 13. Checklist cho phép đo có thể tái hiện

1. Định nghĩa chính xác **operation** của mỗi pha và phạm vi bao gồm/loại trừ.
2. Ghi commit/code version, JDK vendor/version, OS, CPU và container quota.
3. Cố định số provider/JAR, source size, classpath/module graph, compiler options.
4. Phân biệt cold start, warm discovery, warm compiler, per-instance construction và hot invocation.
5. Không để code trong timed phase “rò” operation của pha khác.
6. Dùng warm-up, nhiều measured rounds, nhiều JVM forks nếu cần tính ổn định.
7. Xác minh kết quả có ý nghĩa và được giữ sống; không đo code đã bị JIT tối ưu mất.
8. Báo rõ units: `ns/op`, `ms/compile`, `ops/s`; không trộn đơn vị.
9. Ghi median, variance/percentiles, sample count và mức concurrency.
10. Kiểm tra profiler/JFR/GC khi thấy outlier hoặc thay đổi lớn.
11. Với plugin mới triển khai, kiểm tra classloader lifetime, cache, activation hooks và chi phí unload/reload.
12. Với mã biên dịch/thực thi động từ nguồn không tin cậy, cô lập ở cấp process/OS và giới hạn tài nguyên; benchmark không phải sandbox.

## 14. Tự kiểm tra

**1. Chỉ gọi `ServiceLoader.load(Task.class)` đã đo full discovery chưa?**  
Chưa. Discovery lazy, cần duyệt provider metadata hoặc provider instances theo mục tiêu.

**2. Dùng `for (Task t : loader)` để đo discovery-only có nguy cơ gì?**  
Có thể làm cả instantiation của provider, khiến hai pha bị trộn.

**3. Trong demo, kết quả compile có được class loader nạp và chạy không?**  
Không. Bytecode nằm trong memory output; đo compilation tách khỏi class loading và invocation.

**4. Phép đo `Constructor.newInstance()` sau warm-up có đại diện cold static class initialization không?**  
Không. Class đã được chuẩn bị và tạo instance trước timed loop.

**5. Pha hot invocation tạo provider mới ở mỗi lời gọi không?**  
Không. Sử dụng một `Task stable` đã tạo trước.

**6. Vì sao không in timing cố định trong expected stdout?**  
Số đo phụ thuộc JIT, OS, CPU, GC, filesystem, JVM version và load hệ thống; test chỉ nên assert nhãn/correctness.

**7. Khi muốn đo per-call vài nanosecond, có nên gọi `nanoTime` trước sau từng call không?**  
Không. Timer overhead dễ lấn át operation; dùng batch/JMH.

**8. `ServiceLoader.reload()` có làm JVM quay lại cold state không?**  
Không. Nó xóa cache của chính `ServiceLoader`, không reset JIT/classes/OS cache.

**9. JMH có đảm bảo mỗi benchmark đo đúng pha được đặt tên không?**  
Không. Nhà phát triển vẫn phải xác định unit of work và setup state đúng.

**10. Khi startup SLA bị vi phạm nhưng hot call rất nhanh, nên tối ưu gì?**  
Tách discovery/compile/load/init/activate rồi chọn pha thống trị startup latency.

**11. Một metric `ns/op` trung bình có thay thế p99 request latency không?**  
Không. Request có IO, contention và GC. Cần đo theo mục tiêu end-to-end.

**12. Với việc tối ưu compiler plugin, nên so sánh gì?**  
Source count/size, classpath, file manager, output mode, JDK, cache, annotation processors, time/compile và allocation/GC; không so một compiler task với toàn bộ forked build.

**Ghi nhớ:** tách **discovery = duyệt metadata provider**, **compilation = compiler task tạo bytecode**, **initialization = constructor/factory hoặc cold class init được định nghĩa riêng**, **warmed invocation = gọi trên instance có sẵn sau warm-up**. Luôn báo phạm vi, độ nóng của cache/JIT, đơn vị thao tác, kết quả correctness và độ biến thiên; sử dụng JMH/JFR khi muốn quyết định kỹ thuật có độ tin cậy.

## Tài liệu tham khảo

- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): lazy discovery, `Provider.type()` và `Provider.get()`, caching, `reload()`.
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): compiler task, `getTask()`, compiler file manager và diagnostics.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) và [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): class loading và reflective construction.
- [Java SE 17 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): microbenchmark harness, warm-up, measurement, forks và benchmark state.
- [Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JFR và JVM diagnostics.
