# Phân biệt độ trễ khởi động với chi phí lời gọi sau khi đã nạp

## 1. Đừng đánh đồng cold start với steady-state execution

Trong Java, **lần đầu cần một class** và **một lần gọi method khi class đã sẵn sàng** là hai workloads khác nhau. JVM có thể cần tìm class bytes, hỏi parent classloader, tạo runtime `Class<?>`, verify/link class, thực thi static initializer và nạp thêm dependencies ở lần dùng đầu. Sau đó các lời gọi cùng method thường **không** lặp lại toàn bộ quá trình nạp, định nghĩa và khởi tạo class ấy.

Cần phân biệt ba câu hỏi:

1. **Độ trễ khởi động (startup latency):** từ một mốc bắt đầu được định nghĩa đến khi JVM/app/plugin đạt điều kiện sẵn sàng.
2. **Độ trễ lần dùng đầu (cold/first-use latency):** một feature đã được gọi lần đầu, có thể kéo theo lazy loading, initialization, resource I/O và provider discovery.
3. **Chi phí sau khi đã nạp (warm/steady-state invocation):** khi class, object và tài nguyên phù hợp đã sẵn sàng, một method/request hoạt động nhanh đến đâu.

Cả ba đều quan trọng nhưng **không nên đo một rồi đặt tên là cái khác**. Một ứng dụng lazy khởi động rất nhanh có thể khiến request đầu chậm; một ứng dụng eager startup lâu hơn có thể bảo đảm p99 sau readiness ổn định hơn.

**Điểm cốt lõi:** nếu `loader.loadClass("plugin.Action")` lần đầu mất nhiều thời gian hơn `action.execute()` trong vòng lặp nóng, điều đó không chứng minh ClassLoader “làm chậm mọi method call”. Hai phép đo đã bao gồm công việc khác nhau.

## 2. Bản đồ chi phí từ khi tạo JVM tới request nóng

~~~text
OS launches java process
          |
          v
JVM bootstrap + app/bootstrap code
          |
          v
Tạo classloader/module layer + tìm JARs/resources
          |
          v
Loading: delegation, findClass, defineClass
          |
          v
Linking: verify, prepare, resolve khi cần
          |
          v
Initialization: static fields/blocks (<clinit>)
          |
          v
SPI/ServiceLoader discovery + constructor + config I/O
          |
          v
FIRST SUCCESSFUL FEATURE RESPONSE
          |
          v
JIT profiling/compilation + caches warming
          |
          v
WARM REQUEST/INVOCATION (steady state)
~~~

Đây là **mô hình phân tích**, không phải một chuỗi tuyệt đối cho mọi ứng dụng. JVM có thể giải quyết symbolic references muộn; code có thể lazy-load plugin sau readiness; JIT có thể compile/recompile khi ứng dụng đã nhận traffic. Những điểm đo phải mô tả **đúng công việc được thực hiện**.

| Thành phần | Cold/first-use | Mỗi lời gọi method nóng? |
|---|---|---|
| JVM bootstrap | Thường có ở process startup | Không |
| Tạo `URLClassLoader`/`ModuleLayer` | Khi tạo generation | Không nếu dùng lại |
| Đọc class bytes từ JAR/URL | Khi class cần định nghĩa | Không cho class đã loaded trong loader đó |
| Parent delegation/class definition | Khi class cần loaded | Không lặp toàn bộ pipeline mỗi method call |
| Verification/linking | Khi class/reference cần xử lý | Không phải chi phí cố định cho mỗi invocation |
| `<clinit>` | Khi class initialize lần đầu | Một lần thành công trên mỗi runtime class |
| `ServiceLoader` provider discovery | Thường khi iterate lần đầu | Không nhất thiết nếu cache/provider reused |
| Đọc/parse config resource | First use/cache miss | Phụ thuộc cache strategy |
| JIT compilation/profiling | Warm-up và tùy VM | Không tương đương một lần compile mỗi call |
| Business logic/allocations/locks | Có | Có theo workload |
| Method dispatch | Có | Có, có thể được inline/tối ưu |

**Không có hằng số “mỗi class loading tốn N ms”** áp dụng mọi JDK, CPU, JAR và classloader policy.

## 3. Định nghĩa chính xác mốc startup

`System.nanoTime()` ở dòng đầu `main()` chỉ cho thấy khoảng đo **sau khi `main` đã bắt đầu**. Nó bỏ qua phần JVM launcher/bootstrap trước đó. Vì vậy, muốn đo startup thực:

- Với CLI: có thể đo bên ngoài process từ lúc gọi `java` tới kết quả/exit.
- Với HTTP service: đo từ start process/container tới **readiness endpoint thực sự phản ánh công việc bắt buộc**, và tới response đầu tiên nếu SLA yêu cầu.
- Với plugin runtime: đo từ activation request tới lúc plugin registered, dependencies initialized và thực hiện call contract thành công.
- Với modular runtime: nếu tạo `ModuleLayer` hoặc resolve modules trong activation, phải tính đó vào workload nếu sản phẩm thật cũng thực hiện như vậy.

Một cột mốc `health=200` được trả **trước** khi các plugin bắt buộc sẵn sàng không nên được dùng để tuyên bố startup nhanh hơn. Phải so cùng định nghĩa “ready”.

### First use không nhất thiết trùng startup

Một feature hiếm dùng có thể chỉ lần đầu được gọi sau một tuần mới:

- Gọi `Class.forName` hoặc `ServiceLoader`.
- Parse config.
- Load JNI library.
- Mở network connection.
- Kích hoạt code path JIT chưa warm.

Độ trễ của request ấy là **feature cold path**, không phải JVM process startup. Cần log separate spans để thấy đúng nguyên nhân.

## 4. ClassLoader.loadClass lần đầu và lần sau

Trong implementation mặc định, ClassLoader làm gần như:

~~~text
loadClass(name)
     |
     v
getClassLoadingLock(name)
     |
     v
findLoadedClass(name)
     |
     +-- Có -> return existing Class<?>
     |
     +-- Không -> parent/bootstrap delegation
                       |
                       +-- tìm thấy -> return parent's Class
                       |
                       +-- không -> findClass(name)
                                      |
                                      v
                                defineClass(bytes)
                                      |
                                      v
                                 Class<?>
~~~

Nếu lần trước class đã được load thành công, gọi lại cùng tên thông qua cùng loader có thể trả **cùng runtime `Class<?>`**.

~~~java
Class<?> first = loader.loadClass("plugin.Action");
Class<?> second = loader.loadClass("plugin.Action");
System.out.println(first == second);
~~~

Đây là **mảnh minh họa**, cần biến `loader` đúng và class tồn tại; theo hợp đồng class loading của trường hợp đó, kết quả là `true`.

**Không suy ra** `loadClass` lặp lại là không tốn CPU: vẫn có method call, kiểm tra và đồng bộ tùy implementation. Tuy nhiên nó **không đồng nghĩa phải đọc JAR lại hoặc define class mới**. Nếu plugin object đã có, business code nên gọi qua shared interface/object ấy thay vì `Class.forName` theo string cho mọi request mà không có lý do.

### Loader generation mới làm thay đổi ý nghĩa benchmark

~~~text
Generation A: ("plugin.Action", LoaderA)
Generation B: ("plugin.Action", LoaderB)
~~~

Hai runtime classes khác nhau ngay cả khi bytecode/binary name trùng. Nếu mỗi vòng benchmark tạo một loader mới, phép đo đang bao gồm **class loading/linking/initialization và lifecycle generation**, không chỉ invocation.

## 5. Loading, linking, initialization và gọi method khác nhau

Các lời gọi dưới đây **đo những phạm vi khác nhau**; đặt chúng cùng tên “chi phí class loading” sẽ khiến kết quả sai ý nghĩa:

~~~java
Class<?> a = loader.loadClass("plugin.Action");
Class<?> b = Class.forName("plugin.Action", false, loader);
Class<?> c = Class.forName("plugin.Action", true, loader);
~~~

- `loadClass` yêu cầu tìm/nạp class theo delegation, **không chủ động khởi tạo** class.
- `Class.forName(..., false, ...)` có thể load/link, nhưng **không yêu cầu chạy `<clinit>`**.
- `Class.forName(..., true, ...)` yêu cầu initialization nếu class chưa initialized; số đo có thể bao gồm static initializer và side effects.
- `action.execute()` trên một instance đã sẵn sàng đo business invocation, có thể chịu JIT/GC/I/O nhưng không định nghĩa lại runtime class ấy ở mỗi call.

Static initializer thành công chỉ chạy một lần cho **mỗi runtime class**. Loader generation khác tự định nghĩa cùng binary name thì có class và initialization riêng. Symbolic references còn có thể resolve khi method dùng chúng, nên `loadClass` thành công **không đảm bảo tất cả lazy dependencies đã sẵn sàng**.

Ví dụ startup có static config reader chậm nên đặt timer tách `<clinit>` và first request, thay vì quy toàn bộ delay cho JAR/verification. Nếu static initialization có network I/O khó retry, cần lifecycle startup có kiểm soát, không dùng `Class.forName` lặp lại như retry.

## 6. Ví dụ Java 17+ chạy được: initialization một lần, method gọi nhiều lần

### File `StartupVsSteadyState.java`

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class StartupVsSteadyState {
    private static final AtomicInteger INIT_EVENTS =
            new AtomicInteger();

    public static final class Worker {
        static {
            INIT_EVENTS.incrementAndGet();
        }

        public static long calculate(int value) {
            return 31L * value + 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader =
                StartupVsSteadyState.class.getClassLoader();

        // Class literal không yêu cầu initialize Worker.
        String name = Worker.class.getName();

        long t0 = System.nanoTime();
        Class<?> type = Class.forName(name, false, loader);
        long t1 = System.nanoTime();

        System.out.println("after load(false): "
                + INIT_EVENTS.get());

        long t2 = System.nanoTime();
        Class.forName(name, true, loader);
        long t3 = System.nanoTime();

        System.out.println("after initialize: "
                + INIT_EVENTS.get());

        long checksum = 0;
        int iterations = 100_000;
        long t4 = System.nanoTime();

        for (int i = 0; i < iterations; i++) {
            checksum += Worker.calculate(i);
        }

        long t5 = System.nanoTime();

        System.out.println("after calls: "
                + INIT_EVENTS.get());
        System.out.println("same Class: "
                + (type == Worker.class));
        System.out.println("checksum positive: "
                + (checksum > 0));
        System.out.println("load_ns=" + (t1 - t0));
        System.out.println("init_ns=" + (t3 - t2));
        System.out.println("calls_ns=" + (t5 - t4));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac StartupVsSteadyState.java
java StartupVsSteadyState
~~~

**Năm dòng đầu có kết quả logic xác định:**

~~~text
after load(false): 0
after initialize: 1
after calls: 1
same Class: true
checksum positive: true
~~~

**Ba dòng cuối có định dạng sau, nhưng số chỉ để minh họa:**

~~~text
load_ns=123456
init_ns=45678
calls_ns=789012
~~~

Không có số `ns` cố định cho mọi JDK/CPU/chạy lại.

### Giải thích

1. `Worker.class.getName()` lấy binary name nhưng không tự yêu cầu initialize Worker.
2. `Class.forName(name,false,loader)` không kích hoạt initializer; `INIT_EVENTS` vẫn 0.
3. `Class.forName(name,true,loader)` chạy static block lần đầu; counter = 1.
4. Sau 100.000 lời gọi `calculate`, static block **không** chạy lại; counter vẫn 1.
5. `type == Worker.class` là `true` vì cùng classloader identity, không tạo generation mới.
6. Các khoảng `load_ns`/`init_ns`/`calls_ns` có scope đo **khác nhau** và còn noise/JIT effects.

### Tại sao `calls_ns / 100000` không phải p99 latency?

- Chỉ có một phép đo aggregate; percentile cần distribution nhiều samples.
- JVM có thể compile/inlining method trong vòng lặp.
- Loop có thể được tối ưu hóa/giảm chi phí theo biểu thức dễ đoán.
- Clock và compiler/scheduler/GC có ảnh hưởng.
- Một phép gọi tiny arithmetic khác xa request gồm I/O, allocations và concurrency.
- Dùng `checksum` giúp kết quả được quan sát nhưng chưa bảo đảm loại bỏ mọi dead-code elimination/loop transformation.

Chương trình chứng minh **lifecycle**, không thay thế công cụ benchmark chuyên nghiệp.

## 7. Ví dụ Java 17+: hai loader generation và hai runtime classes

Một test riêng cho thấy vì sao benchmark liên tục tạo classloader mới đo một workload khác.

### File `src/plugin/demo/PluginAction.java`

~~~java
package demo;

public final class PluginAction {
    static {
        System.out.println("plugin initialized");
    }

    public String call() {
        return "ok";
    }
}
~~~

### File `src/host/LoaderGenerations.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderGenerations {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderGenerations <plugin-dir>");
        }

        URL root = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        try (URLClassLoader loaderA = new URLClassLoader(
                    new URL[]{root},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderB = new URLClassLoader(
                    new URL[]{root},
                    ClassLoader.getPlatformClassLoader())) {

            String name = "demo.PluginAction";
            Class<?> first = loaderA.loadClass(name);
            Class<?> same = loaderA.loadClass(name);
            Class<?> second = loaderB.loadClass(name);

            System.out.println("repeat in A: " + (first == same));
            System.out.println("same binary name: "
                    + first.getName().equals(second.getName()));
            System.out.println("same runtime type: "
                    + (first == second));

            Object a = first.getConstructor().newInstance();
            Object b = second.getConstructor().newInstance();

            System.out.println("A call: "
                    + first.getMethod("call").invoke(a));
            System.out.println("B call: "
                    + second.getMethod("call").invoke(b));
        }
    }
}
~~~

Các lệnh Bash tại thư mục project:

~~~bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/PluginAction.java
javac -d out/host src/host/LoaderGenerations.java
java -cp out/host LoaderGenerations out/plugin
~~~

**Không đưa `out/plugin` vào application classpath.** Stdout khi dùng fixture trên:

~~~text
repeat in A: true
same binary name: true
same runtime type: false
plugin initialized
plugin initialized
A call: ok
B call: ok
~~~

Giải thích: `loaderA` định nghĩa class lần đầu rồi trả chính runtime `Class<?>` đó khi gọi lại; `loaderB` định nghĩa class **khác** với cùng binary name. Mỗi class được initialize khi tạo instance; do đó initializer in hai lần. Đây là chi phí **hai loader generations**, không phải của hai method calls vào cùng một instance.

## 8. Thiết kế phép đo theo đúng câu hỏi

| Câu hỏi | Mốc đo | Định nghĩa kết quả |
|---|---|---|
| JVM/app cold start? | Bên ngoài process: launch → readiness | Milliseconds, distribution qua nhiều fresh processes |
| Plugin activation? | Activation requested → plugin usable | Bao gồm loader, class, providers, resources và init bắt buộc |
| Class loading riêng? | Trước/sau explicit `loadClass` trên cold loader | Chỉ công việc của API đó; có thể lazy các bước sau |
| Static initialization? | Trước/sau first `Class.forName(...,true,loader)` | Bao gồm initializer side effects |
| Provider discovery? | Trước iterator → provider ready | Bao gồm lazy ServiceLoader work |
| Warm method invocation? | Receiver/object ổn định, method lặp với JMH | ns/op hoặc ops/s, phân tích thống kê |
| Real request p99? | HTTP/RPC end-to-end | Histogram theo concurrency và workload |
| Hot redeploy? | Stop old generation → new generation ready | Teardown, memory pressure, loader activation |

Không đặt `new URLClassLoader` bên trong measurement loop nếu mục tiêu chỉ là call một object đã tồn tại. Ngược lại, nếu ứng dụng thật phải tạo loader mỗi request, hãy **đưa chi phí đó vào benchmark** và đặt tên đúng.

## 9. Đo cold startup từ bên ngoài JVM

Để đo **process startup** phải bao gồm phần trước `main`, nên cần external harness hoặc instrumentation phù hợp:

~~~text
Harness:
  start monotonic timer
  launch java process
  wait for readiness marker / successful endpoint
  record elapsed time
  terminate process safely
  repeat in fresh process
~~~

Một lệnh shell `time java MyMain` đo khoảng process chạy đến kết thúc (phù hợp CLI nhỏ), **không tự là** thời gian server trở nên ready nếu server vẫn chạy mãi. Với HTTP server, cần readiness signal tường minh và timer bên ngoài.

Nên cố định:

- Cùng JDK/build/VM flags.
- Cùng artifact và module/classpath/JAR graph.
- Cùng CPU/quota, memory, OS và container limits.
- Cùng required/optional plugins.
- Cùng conditions của network/DNS/DB và secrets.
- Phân biệt warm/cold OS page cache.
- Nhiều fresh processes, không dùng duy nhất lần đầu có nhiều nhiễu.
- Báo median, p95/p99 nếu số samples đủ; không chọn fastest run.

Nếu variant A báo ready trước khi provider quan trọng initialized, còn variant B đợi provider usable, hai phép đo **không cùng định nghĩa** và không nên so như nhau.

## 10. JMH dành cho steady-state method benchmark

**Java Microbenchmark Harness (JMH)** hỗ trợ benchmark JVM với forks, warm-up, measurement iterations, state, result consumption và báo cáo thống kê.

Mảnh JMH **cần dependency JMH và class riêng**, không phải JDK thuần:

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class InvokeBenchmark {
    private final BusinessService service = new BusinessService();

    @Benchmark
    public long invoke() {
        return service.compute(42);
    }
}
~~~

`BusinessService` là type minh họa của ứng dụng; cần tự cung cấp implementation và cấu hình project JMH. Mấu chốt là **service được chuẩn bị ngoài method benchmark**, không tạo loader/plugin object mới cho mỗi invocation.

Quy trình JMH phù hợp:

1. Chạy warm-up iterations trước khi lấy số.
2. Fork process khi cần để tránh class/JIT state bị benchmark khác ảnh hưởng.
3. Chuẩn bị receiver/provider theo `@State` hoặc setup lifecycle phù hợp.
4. Consume kết quả để giảm rủi ro dead-code elimination.
5. Kiểm soát benchmark params/dataset để compiler không chỉ đo một constant-folded expression.
6. Chạy nhiều iterations/samples; ghi confidence/error bounds.
7. Phân biệt throughput và average time; microbenchmark không tự cho p99 request production.
8. Không so operation A gồm reflection lookup với B chỉ gồm direct invocation rồi nói “invocation chậm X” nếu scope khác nhau.

**JMH không thay thế load testing:** network, thread pools, GC, DB, queues và p99 real requests vẫn cần đo bằng công cụ thích hợp với production workloads.

## 11. Reflection, MethodHandle và direct interface calls

Plugin frameworks đôi khi tìm method bằng reflection:

~~~java
java.lang.reflect.Method method =
        type.getMethod("execute");
Object result = method.invoke(instance);
~~~

Đây là mảnh minh họa khi `type`/`instance` đã có. Có hai phần khác nhau:

- **Lookup:** `getMethod(...)`, access validation.
- **Invocation:** `method.invoke(...)`.

Nếu trong một variant đặt `getMethod` mỗi iteration, variant khác gọi trực tiếp `sharedInterface.execute()`, ta đang đo cả lookup cộng invoke so với chỉ invoke. Để so công bằng, cache `Method`/`MethodHandle` phù hợp trong setup, hoặc đo lookup riêng.

Một architecture có shared API ở parent thường cho phép host giữ một provider instance:

~~~java
MyService service = factory.create();
service.execute();
~~~

Đoạn trên chỉ minh họa mô hình; trong dự án thật cần khai báo `MyService`/`factory`. Caller sau đó không cần tìm class lại bằng binary name cho mọi request.

Hiệu năng dynamic dispatch phụ thuộc JIT, inline caches, polymorphism, interface implementations và workload, **không có một hằng số overhead classloader áp dụng mỗi lời gọi**.

## 12. JIT warm-up khác static class initialization

**Initialization** chạy `<clinit>` một lần trên runtime class nếu thành công. Còn **JIT** hoạt động khi JVM đánh giá các hot execution paths và có thể compile/recompile sau nhiều invocations.

~~~text
Class loaded & initialized
          |
Call 1: cold code/data caches
          |
Call N: profiling, tiered compilation
          |
Call later: optimized/inlined code possible
          |
Deoptimization/recompile possible if profile changes
~~~

Sơ đồ không khẳng định phải có đúng N calls hoặc mọi JVM mode luôn JIT compile. Trong `-Xint`, execution model khác với default HotSpot tiered compilation.

**Hệ quả:** chạy `Class.forName(name,true,loader)` sớm có thể giúp tránh static init ở request đầu, nhưng **không đảm bảo JIT và business data caches đã warm**. Nếu SLA yêu cầu first request nhanh, cần warm-up những critical request paths một cách có kiểm soát.

## 13. ServiceLoader và resource I/O là cold work riêng

### ServiceLoader lazy discovery

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
~~~

Đây là mảnh minh họa, yêu cầu `MyService`/`pluginLoader` tồn tại.

`ServiceLoader.load` tạo một ServiceLoader, trong khi nhiều bước tìm metadata/provider và instantiate diễn ra **khi iterate/stream**. Vì vậy, đo `ServiceLoader.load(...)` mà không duyệt providers có thể **không đo activation đầy đủ**.

Đặt mốc:

~~~text
create ServiceLoader
   |
iterate descriptors / module provider metadata
   |
load implementation class
   |
check runtime SPI assignability
   |
instantiate provider
   |
invoke provider startup method
~~~

Thêm hoặc xóa descriptor trong `META-INF/services`, TCCL/explicit loader hay named module setup có thể thay đổi work thực tế. Benchmark cần cùng artifact/provider behavior, không chỉ một API call giống tên.

### Resource lookup khác đọc/parsing

~~~java
URL location = pluginLoader.getResource("config/settings.properties");
~~~

`getResource` chỉ tìm URL (hoặc `null`); nó chưa tương đương đọc toàn bộ bytes, parse và validation. Nếu code tiếp tục `openStream()` rồi parse Properties, đó là phase I/O/CPU khác, có thể cache hoặc bị page cache ảnh hưởng.

Đừng dùng resource URL “trông đúng” để kết luận bản data của plugin đã được dùng; parent-first có thể che một file cùng tên ở child.

## 14. Quan sát class loading bằng ClassLoadingMXBean

JDK 17 có `ClassLoadingMXBean`:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

long total = bean.getTotalLoadedClassCount();
int current = bean.getLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

Đây là mảnh Java minh họa.

- `total` là **counter tích lũy** số class loaded kể từ lúc JVM khởi động.
- `current` là **gauge** số class hiện loaded.
- `unloaded` là **counter tích lũy** class đã unloaded.

Chúng giúp biết startup hoặc activation đã làm JVM load thêm class hay chưa, nhưng **không đo latency của từng class**. `total` tăng không tự chứng minh classloader leak hay method call chậm; cần xem trend, metaspace, loading logs/JFR và retained classloader references.

Khi tính delta, lấy samples trong **cùng một JVM**; mỗi process restart reset counters. Ghi thêm JVM process start time và timestamp để không tính delta âm giữa hai JVM thành “unloaded”.

## 15. JVM logs, JFR và tracing

Trên HotSpot JDK 17, bật class load/unload logs:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    StartupVsSteadyState
~~~

Lệnh chẩn đoán tạo thêm log, **không** còn stdout gọn như demo; tùy JVM có thể khác tag/format. Classloading logs cho biết event/sources nhưng không tự đưa ra p95/p99 business latency.

**Java Flight Recorder (JFR)** có thể giúp xem execution samples, allocation, GC, class loading và những events khác theo cấu hình JDK. Khi phân tích cold start:

- Bật recording sớm đủ để bao gồm startup/cold feature.
- Ghi timeline của plugin loader creation, class defined, first provider ready và request first response.
- So JIT/GC/I/O/locks cùng classloading activity.
- Không mặc định mọi JFR event đều bật, hoặc có đầy đủ stacktrace/duration.
- So sánh nhiều runs và bảo đảm JDK/flags giống nhau.

Application spans cũng hữu ích:

~~~text
process-started
required-services-ready
plugin-loader-created
plugin-class-found
plugin-initialized
provider-ready
first-successful-result
warm-request-completed
~~~

Để tính elapsed durations trong process dùng monotonic clock, kết hợp wall clock khi cần correlate distributed traces. Không cộng hai spans chạy song song rồi coi là total.

## 16. Class unloading và metaspace trong lifecycle benchmark

Một hệ thống hot redeploy liên tục có:

~~~text
Generation A -> Loader A -> Class A
Generation B -> Loader B -> Class B
Generation C -> Loader C -> Class C
~~~

Mỗi generation có runtime class objects riêng; nếu host cache `Class<?>`, plugin objects, TCCL, threads, callbacks hoặc JNI globals từ generation cũ, memory/class count có thể tăng.

`URLClassLoader.close()` đóng JAR/file handles của URL loader, **không bắt JVM unload class ngay**. `System.gc()` cũng không bảo đảm class unloading xảy ra lập tức.

Nếu workload thực sự là tạo/retire loaders liên tục, phải đo thêm:

- Load/activation time cho mỗi generation.
- Total/current/unloaded classes theo khoảng.
- Metaspace usage, heap và GC pauses.
- Thời gian đóng streams/JAR handles.
- Strong-reference retention và classloader leaks.
- Tail latency của request đang chạy khi redeploy.

Không dùng benchmark một loader trên fresh JVM để khẳng định app redeploy 100 lần sẽ không tăng bộ nhớ.

## 17. Chiến lược eager, lazy và warm-up theo SLA

| Chiến lược | Lợi ích | Đánh đổi |
|---|---|---|
| Eager loading/init trước readiness | Lỗi lộ sớm, first request nhanh hơn nếu đủ chuẩn bị | Startup lâu, footprint lớn |
| Lazy init khi feature được gọi | Ready nhanh, không nạp feature ít dùng | Cold request chậm, lỗi xuất hiện muộn |
| Targeted warm-up | Tập trung vào critical paths | Phải chọn đúng paths và đo real effect |
| Reuse loader/provider | Giảm repeated activation work | Cần lifecycle/cache consistency |
| New loader per generation | Hỗ trợ plugin version isolation | Chi phí load/GC/metaspace cao hơn |
| Separate process cho plugin | Cô lập mạnh hơn | IPC/process startup overhead |

Một thiết kế có thể đặt readiness:

~~~text
BOOTING -> REQUIRED_PLUGINS_READY ->
WARM_CRITICAL_PATHS -> SERVING
~~~

Optional feature có thể lazy, nhưng phải ghi rõ first-use SLA và fallback policy. Nếu chỉ chuyển một công việc nặng từ startup sang request đầu mà không đo p99, **chưa đủ bằng chứng** cải thiện tổng thể.

## 18. Bẫy benchmark thường gặp

| Ngộ nhận | Vì sao sai | Cách thay thế |
|---|---|---|
| First invocation chậm nên tất cả Java method calls chậm | Lẫn loading/init/JIT | Tách cold và warm |
| `Class.forName(..., true)` làm JIT đã warm | Initialization khác JIT | Warm đúng code paths |
| `loadClass` đọc JAR ở mọi call | Thường trả class đã loaded | Kiểm tra `findLoadedClass` và timing |
| Tạo new loader mỗi iteration là invoke benchmark | Đang đo generation | Reuse loader/receiver |
| Mean từ một loop là p99 | Mean khác distribution percentile | Histogram, nhiều samples |
| Một lần `nanoTime` là benchmark chuẩn | Noise/JIT/GC/scheduler | JMH + repeat/forks |
| Timing từ `main` là process startup đầy đủ | Bỏ JVM bootstrap | External harness |
| `ServiceLoader.load` đã đo mọi provider cost | Discovery lazy | Iterate/instantiate |
| `getResource` đã đọc config | Chỉ lookup URL | Đo open/read/parse |
| Reflection lookup+invoke so với direct invoke là công bằng | Extra work ở case reflection | Tách lookup khỏi invocation |
| Class total loaded tăng là leak chắc chắn | Counter tích lũy vốn tăng | Current/metaspace/retention trend |
| GC chưa unload ngay là leak | Không deterministic | Quan sát lifecycle/reference graph |
| “Chạy nhanh” nhưng provider fail vẫn đạt SLA | Correctness không bảo đảm | Xác nhận successful feature behavior |

## 19. Checklist trước khi kết luận

- [ ] Định nghĩa rõ startup/activation/first use/steady-state metric.
- [ ] Đo startup **từ ngoài process** nếu mục tiêu gồm JVM bootstrap.
- [ ] Dùng cùng JDK, flags, hardware và artifact khi so sánh.
- [ ] Cùng classpath/module path và loader policy.
- [ ] Dùng fresh JVM cho cold-start samples.
- [ ] Không tạo ClassLoader mỗi vòng của benchmark method đã loaded.
- [ ] Phân biệt `loadClass` với `Class.forName(..., true)`.
- [ ] Xác nhận static initializer chỉ chạy theo runtime class identity.
- [ ] Đo ServiceLoader provider iteration, không chỉ tạo object loader.
- [ ] Đo resource lookup riêng với đọc/parsing.
- [ ] Có warm-up và multiple forks khi đo tiny methods bằng JMH.
- [ ] Consume results, chống dead-code elimination.
- [ ] Báo distribution/tail latency cho request thật.
- [ ] Theo dõi JIT/GC/class count/metaspace khi cần.
- [ ] Verify startup/readiness đã thực sự phục vụ đúng tính năng.
- [ ] Kiểm soát TCCL/caches/streams và loader lifecycle khi redeploy.
- [ ] Không lấy một cấu hình benchmark để khẳng định mọi JVM.

## 20. Bài tập tự kiểm tra

**Câu 1.** `ClassLoader.loadClass` gọi lại cùng tên trên cùng loader có phải luôn định nghĩa class mới không?

**Đáp án:** Không. ClassLoader thông thường trả lại runtime class đã loaded; không gọi `defineClass` lần hai cho cùng binary name trong một loader.

**Câu 2.** `Class.forName(name, false, loader)` khác `true` ở khía cạnh nào?

**Đáp án:** `false` không yêu cầu initialize, `true` yêu cầu initialize class chưa initialized; chi phí static initializer có thể xuất hiện ở lần đầu.

**Câu 3.** Đo thời gian từ đầu `main` tới khi sẵn sàng có phải đo đủ JVM process startup không?

**Đáp án:** Không, đã bỏ thời gian JVM launcher/bootstrap trước `main`.

**Câu 4.** Vì sao hai URLClassLoader định nghĩa cùng `plugin.Action` có thể làm initializer chạy hai lần?

**Đáp án:** Vì đó là hai runtime classes khác defining loaders; mỗi class có lifecycle initialization riêng.

**Câu 5.** JMH đo 100.000 method invocations đã warm có phản ánh p99 HTTP request không?

**Đáp án:** Không. Real request còn network, queues, concurrency, allocations, I/O và GC.

**Câu 6.** `ServiceLoader.load(SPI.class)` hoàn thành nhanh có chứng minh provider instantiated không?

**Đáp án:** Không, provider discovery/instantiation có thể lazy khi iterate.

**Câu 7.** Nếu chuyển config read từ startup sang request đầu, startup có thể nhanh hơn. Có chắc tổng trải nghiệm tốt hơn không?

**Đáp án:** Không; first-use latency có thể tăng. Cần đo mốc readiness và p99 first requests.

**Câu 8.** Vì sao `getTotalLoadedClassCount()` không phải byte-size metaspace?

**Đáp án:** Đây là số lượng runtime classes từng loaded trong JVM, không phải memory usage; footprint/class không cố định.

**Câu 9.** Khi benchmark classloader hot redeploy, có cần xét GC/memory không?

**Đáp án:** Có. Những generations khác nhau tạo runtime types mới; retention/GC/metaspace có thể ảnh hưởng latency và throughput.

**Câu 10.** Nếu một method cực nhỏ chạy nhanh trong vòng loop sau warm-up, có chắc dynamic dispatch trên production cũng nhanh như vậy không?

**Đáp án:** Không. JIT có thể inline/constant fold, còn production nhiều implementations, concurrency và workload khác.

## 21. Cây quyết định

~~~text
Phát hiện Java/plugin chậm
              |
              v
Mốc nào?
 /             |              \
Startup     First use      Warm calls
   |            |               |
external    load/init,     JMH / real
harness     providers,     request traces
   |        config I/O          |
   |            |               |
   +------------+---------------+
                |
       Xác định bottleneck thật
                |
    Eager/lazy/warm-up/reuse loaders
                |
  Đo lại same JVM/artifact/workload
                |
      Correctness + tail latency
                |
      Memory/GC/lifecycle kiểm tra
~~~

**Kết luận:** **Startup**, **first use**, **warm-up** và **steady-state invocation** là những phase khác nhau. `ClassLoader` tạo runtime type identities, không chạy lại toàn bộ pipeline load/define/init mỗi khi một method đã nạp được gọi. Muốn tối ưu hiệu năng chính xác, hãy phân tách các mốc đo, tính đến lazy linking/provider/resource work, JIT và GC, chọn đúng công cụ (external startup harness, JMH, JFR, ClassLoadingMXBean, load testing), rồi xác nhận kết quả trên workload và artifact thật.

### Nguồn tham khảo

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [JVMS 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [OpenJDK — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)
- [Java 17 launcher / Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
