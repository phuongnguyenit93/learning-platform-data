# Tái sử dụng loader so với tạo loader cho từng yêu cầu

## 1. Bài toán: vòng đời ClassLoader nên gắn với cái gì?

Trong ứng dụng Java có plugin, rule engine, application server hay hệ thống nạp mã từ JAR, một class có thể phục vụ hàng nghìn yêu cầu. Có hai cách tổ chức:

- **Reuse loader:** tạo một `ClassLoader` cho môi trường code của một plugin/version, dùng lại nó cho nhiều request; mỗi request có thể tự tạo object mới.
- **Loader-per-request:** mỗi request tạo một `ClassLoader` riêng, nạp class qua nó, xử lý yêu cầu rồi đóng hoặc loại bỏ loader.

Sự khác biệt không chỉ là chi phí của toán tử `new`. Nó ảnh hưởng đến **class identity, bộ nhớ metaspace, verification/linking/initialization, static state, resource/JAR handles, tốc độ warm-up, JIT, khả năng reload và các lỗi cast**.

~~~text
REUSE THEO PLUGIN VERSION

Plugin v1 --> Loader L1 --> demo.Worker (Class A)
                         |         |         |
                      Request 1  Request 2  Request 3
                      object #1  object #2  object #3


LOADER THEO TỪNG REQUEST

Request 1 --> Loader L1 --> demo.Worker (Class A)
Request 2 --> Loader L2 --> demo.Worker (Class B)
Request 3 --> Loader L3 --> demo.Worker (Class C)

Nếu mỗi child tự define Worker:
Class A != Class B != Class C
~~~

**Khuyến nghị mặc định:** tái sử dụng class loader **theo phiên plugin/version hoặc môi trường nạp mã**, không tạo loader mới cho từng HTTP/job request nếu các request dùng chung code và classpath. Điều này không đồng nghĩa phải chia sẻ một service instance có trạng thái mutable; **vòng đời loader và vòng đời object là hai quyết định độc lập**.

Cũng không phải mọi trường hợp đều nên dùng một loader duy nhất cho cả JVM. Nếu các versions, tenants hay modules thực sự cần code khác nhau, ranh giới loader phải phản ánh ranh giới đó.

## 2. ClassLoader không phải object thông thường

Trong JVM, runtime class identity gồm **binary name + defining class loader**. Vì vậy tạo một loader mới *có thể* tạo một bản `demo.Worker` mới với static state, initialization và metadata riêng, ngay cả khi bytes giống hệt.

~~~text
Loader A defines demo.Worker -> Class A
Loader B defines demo.Worker -> Class B
Class A != Class B
~~~

**Điều kiện thiết yếu:** hai loader mới không nhất thiết tạo hai classes. Nếu parent-first tìm thấy `demo.Worker` ở parent, cả hai child có thể trả cùng runtime class ấy. Khi so reuse với loader-per-request, phải kiểm tra `type.getClassLoader()` và `typeA == typeB`, thay vì chỉ đếm `new URLClassLoader`.

Với class do child tự định nghĩa, mỗi generation có static fields và initialization riêng; `Class<?>`, reflection metadata hay instance của generation cũ còn bị giữ có thể ngăn GC/unloading. Do đó quyết định reuse ảnh hưởng cả CPU, identity và vòng đời tài nguyên.

## 3. Tái sử dụng loader có thể tiết kiệm chi phí nào?

Trong lần đầu nạp code riêng, một loader có thể phải đi qua delegation/lookup, đọc class bytes từ directory/JAR, định nghĩa class và thực hiện verification, linking, initialization tại những thời điểm JVM yêu cầu. Khi dùng lại cùng runtime class, không phải định nghĩa lại nó mỗi request.

| Nhóm chi phí | Reuse loader | Tạo loader per request |
| --- | --- | --- |
| Tạo và cấu hình loader | Một lần cho phiên code | Lặp lại mỗi request |
| Tìm class/JAR entries | Có thể tận dụng class đã loaded/lookup metadata | Có thể tìm lại theo loader mới |
| Define, verify, link | Bản runtime class đã tồn tại | Có thể lặp nếu child mới tự define |
| Static initialization | Một lần trên mỗi runtime class | Có thể lặp trên mỗi bản class mới |
| Metadata/metaspace | Ít bản class riêng hơn khi đúng lifecycle | Có thể tạo nhiều bản class trong thời gian ngắn |
| JIT profiling/code cache | Có cơ hội warm up và tái sử dụng methods cùng class | Nhiều bản class/method riêng có thể tăng áp lực |
| File/JAR handles | Giữ và đóng theo plugin lifecycle | Phải mở/đóng thường xuyên và đúng owner |
| Cleanup | Đóng khi retire version | Đóng trên mọi request, khó kiểm soát khi bất đồng bộ |
| Type identity | Ổn định giữa request cùng version | Có thể khác theo request |

Không được hiểu bảng này là tốc độ nhanh hơn được bảo đảm theo một tỷ lệ nào đó. Nếu request tốn phần lớn thời gian vì network/database, hoặc class thực tế đều do parent loader trả về, khác biệt có thể nhỏ. Nếu request luôn nạp hàng trăm implementation classes qua JAR riêng, chi phí lặp lại có thể đáng kể.

Một mô hình minh họa, không phải phép đo:

~~~text
N = số request trong một plugin version
S = chi phí khởi tạo loader + load/link cần thiết
W = công việc nghiệp vụ cho một request
L = lookup/cache overhead khi dùng lại lớp
R = chi phí cleanup một loader

Reuse:           T ≈ S + N × (W + L) + R
Loader/request:  T ≈ N × (S + W + R)
~~~

Đây là biểu thức đơn giản hóa; thực tế có caching của OS/JVM, initialization lazy, compilation và GC. Nó cho thấy **setup có thể được amortize** khi reuse loader, không phải một khẳng định định lượng.

### Reuse Class không có nghĩa reuse instance

~~~text
Loader L
    |
    +--> Class<demo.Worker>
             |
             +--> instance per request #1
             +--> instance per request #2
             +--> instance per request #3
~~~

Bạn có thể load `Class<?>` hoặc tạo factory một lần, nhưng mỗi request vẫn dùng object riêng. Đây thường là lựa chọn tốt hơn việc tạo một runtime class mới chỉ để tách dữ liệu request.

## 4. Cache và findLoadedClass

Thuật toán mặc định của `ClassLoader.loadClass(String, boolean)` kiểm tra `findLoadedClass(name)` trước, sau đó delegate tới parent rồi mới dùng `findClass` của child khi cần.

~~~java
Class<?> first = loader.loadClass("demo.Worker");
Class<?> again = loader.loadClass("demo.Worker");
System.out.println(first == again);
~~~

Đây là đoạn minh họa bên trong method có biến `loader`. Với class loading hợp lệ, hai lần lookup cùng binary name qua cùng initiating loader trả về cùng `Class<?>`, không define class mới ở lần thứ hai.

**Đừng nhầm cache này với một Map do ứng dụng viết.** `findLoadedClass` và JVM quản lý identity của runtime classes. Một `Map<String, Class<?>>` tự tạo vẫn có thể giữ strong references tới loader sau reload và gây retention. Nếu cache theo class, cần có **lifecycle clear** hoặc mô hình weak references thích hợp; không giả định GC tự thu dọn map static của host.

`ClassLoader.loadClass` còn có khóa nạp lớp để tránh race khi cùng tên được yêu cầu đồng thời. Dùng một loader chung không có nghĩa một request có thể define cùng class tùy tiện nhiều lần; JVM và loader phối hợp quản lý class loading. Với custom loader, phải tuân thủ `getClassLoadingLock(name)` và parallel-capable rules khi override.

## 5. Ví dụ Java 17+ tái hiện sự khác nhau

Ví dụ biên dịch hai file riêng biệt:

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── demo/Worker.java
│   └── host/
│       └── LoaderReuseDemo.java
└── out/
    ├── plugin/       (output bytecode plugin)
    └── host/         (output bytecode host)
~~~

**Chỉ out/host được đưa vào application classpath** khi chạy. Out/plugin được nạp bằng một URLClassLoader riêng; nếu lỡ thêm plugin vào host classpath, parent có thể định nghĩa Worker trước và làm thay đổi điều kiện thí nghiệm.

### File src/plugin/demo/Worker.java

~~~java
package demo;

public final class Worker {
    private static int constructions;

    public Worker() {
        constructions++;
    }

    public String work() {
        return "ok";
    }

    public static int constructions() {
        return constructions;
    }
}
~~~

Bộ đếm static chỉ để thấy state theo class loader. `constructions++` **không thread-safe**; ví dụ chạy một thread để đầu ra xác định. Trong chương trình concurrent, cần dùng cơ chế đồng bộ/atomic phù hợp, không lấy đoạn này làm mã production.

### File src/host/LoaderReuseDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderReuseDemo {
    public static void main(String[] args) throws Exception {
        URL url = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        ClassLoader parent = LoaderReuseDemo.class.getClassLoader();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url}, parent)) {
            Class<?> type = loader.loadClass("demo.Worker");
            Object first = type.getDeclaredConstructor().newInstance();
            type.getDeclaredConstructor().newInstance();

            System.out.println("reuse same class: "
                    + (type == loader.loadClass("demo.Worker")));
            System.out.println("reuse work: "
                    + type.getMethod("work").invoke(first));
            System.out.println("reuse constructions: "
                    + type.getMethod("constructions").invoke(null));
        }

        Class<?> previous = null;
        boolean distinct = false;
        for (int request = 1; request <= 2; request++) {
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{url}, parent)) {
                Class<?> type = loader.loadClass("demo.Worker");
                type.getDeclaredConstructor().newInstance();

                if (previous != null) {
                    distinct = previous != type;
                }
                System.out.println("fresh " + request + " constructions: "
                        + type.getMethod("constructions").invoke(null));
                previous = type;
            }
        }
        System.out.println("fresh types differ: " + distinct);
    }
}
~~~

**Kịch bản reuse:** duy nhất một loader nạp Worker. Hai instances làm static count tăng thành 2; lookup lặp về cùng `Class<?>`.

**Kịch bản per-request:** mỗi request tạo và đóng một loader. Mỗi loader định nghĩa riêng Worker nên bộ đếm bắt đầu lại; hai bản Worker khác Class identity.

Biến `previous` cố ý giữ tham chiếu tới một Class cũ để so sánh. Vì vậy ví dụ **không** chứng minh class unloading đã xảy ra ngay khi đóng loader.

### Compile và chạy Linux/macOS

Đứng trong thư mục example:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
  src/plugin/demo/Worker.java

javac --release 17 -d out/host \
  src/host/LoaderReuseDemo.java

java -cp out/host LoaderReuseDemo out/plugin
~~~

### Compile và chạy Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host | Out-Null
javac --release 17 -d out\plugin src\plugin\demo\Worker.java
javac --release 17 -d out\host src\host\LoaderReuseDemo.java
java -cp out\host LoaderReuseDemo out\plugin
~~~

### Stdout chính xác đã chạy thử

~~~text
reuse same class: true
reuse work: ok
reuse constructions: 2
fresh 1 constructions: 1
fresh 2 constructions: 1
fresh types differ: true
~~~

Ví dụ biên dịch bằng `javac --release 17` và đã chạy thực tế trên JDK; kết quả khớp sáu dòng trên.

### Những gì thí nghiệm chứng minh

1. Tạo hai Worker objects trong **cùng loader** không tạo hai bản runtime Worker Class.
2. Static counter được chia sẻ giữa những objects của một runtime class.
3. Loader mới tự define Worker tạo static state mới cho mỗi bản class.
4. Hai `Class<?>` từ các defining loaders khác nhau có identity khác nhau.
5. `URLClassLoader.close()` được gọi bằng try-with-resources khi từng phiên kết thúc.

**Không kết luận** từ ví dụ rằng per-request chậm hơn bao nhiêu phần trăm, đã phát sinh bao nhiêu bytes metaspace hay class unload ngay tức thì. Để đo performance cần benchmark có warmup, concurrency và theo dõi JVM memory phù hợp.

## 6. Vì sao tạo loader mới mỗi request có thể gây hậu quả ngoài CPU?

### Class identity và lỗi cast

Nếu host giữ một `Class<?>` Worker của loader A, rồi cố dùng object Worker từ loader B như thể cùng concrete type, JVM có thể ném `ClassCastException` dù binary name giống nhau.

~~~text
Loader A defines demo.Worker -> Worker A
Loader B defines demo.Worker -> Worker B

WorkerA.class != WorkerB.class
~~~

Để trao đổi giữa các plugin/request loaders, cần một **shared API interface** do loader cha định nghĩa, ví dụ `api.Task`. Hai bản Worker riêng có thể cùng triển khai **một interface host** nếu chúng delegate đúng interface về parent.

Nếu chính interface cũng bị đóng gói và define trong từng child, tên `api.Task` giống nhau chưa đủ, cast sang API của host vẫn có thể thất bại. Đây là lý do per-request isolation đòi hỏi thiết kế kỹ type boundary, không chỉ performance benchmark.

### Static initialization và state

Khi một loader khác tự define Worker, static initialization áp dụng cho **class mới**. Việc static cache/counter/reset không phải reset một instance trước đó; nó là **một bản class runtime khác**.

Tạo loader mới chỉ để tránh state bị rò giữa các requests thường là biện pháp quá nặng. Nên ưu tiên thiết kế request-scoped data hoặc instance lifecycle rõ ràng. Nếu service có static mutable state thật sự phải reset, hãy thiết kế cache/session ownership chính xác; không dùng class loader như object pool.

### Metaspace và class unloading

Mỗi bản class definition có metadata do JVM quản lý. Nếu có nhiều loaders với cùng hàng trăm classes đang sống, peak metaspace và class counts có thể tăng. Sau khi close loader, class unloading **không diễn ra tức thì**: class/loader phải thỏa điều kiện reachability và JVM thực hiện GC/unloading thích hợp.

Nếu host giữ một `Class<?>`, Method, Constructor, instance, thread context class loader (TCCL), ThreadLocal, listener hoặc map reference từ loader cũ, nó có thể vẫn reachable. Loader-per-request mà không quản lý reference sẽ tăng churn, thậm chí gây memory leak.

### JIT/warm-up

JVM có thể thu thập profiling và biên dịch methods của các runtime classes. Tạo nhiều định nghĩa Worker riêng liên tục có thể làm những lợi ích warm-up của bản class đang sống khó phát huy, đồng thời tăng áp lực metadata/code cache. Nhưng tác động **phụ thuộc JVM, workload và tối ưu hóa runtime**; không đưa ra con số speedup nếu chưa đo.

## 7. Benchmark công bằng: cần đo những gì?

Để quyết định trên dữ liệu thực tế, nên phân biệt ít nhất:

| Metric | Ý nghĩa |
| --- | --- |
| Cold-start latency | Thời gian từ tạo loader đến xử lý xong request đầu |
| Steady-state p50/p95/p99 | Latency sau warmup trong tải tương đương |
| Throughput | Số requests mỗi giây tại concurrency định sẵn |
| Allocations | Object allocations và garbage collection pressure |
| Class counts/metaspace | Các runtime class definitions và memory metadata |
| CPU/JIT/code cache | Phần thời gian JVM xử lý class loading, optimization |
| JAR/file handles | Số resource handles còn mở trong vòng đời |
| Reload duration | Thời gian chuyển version và retire loader cũ |

### Kịch bản thử nghiệm hợp lý

1. Cố định JDK, JVM options, machine, plugin JAR, business logic và các dependencies.
2. Scenario A: **một loader cho cùng plugin version**, khởi tạo trước rồi xử lý N requests bằng object riêng.
3. Scenario B: **một loader cho mỗi request**, cùng số requests và cùng business logic.
4. Đo **cold startup riêng**; warm up trước khi đo steady-state.
5. Với latency/throughput cần nhiều vòng đo, nhiều JVM forks nếu thích hợp; không suy từ một lần chạy.
6. Giữ concurrency, input và classpath giống nhau; đảm bảo server logging/background tasks không làm sai lệch.
7. **Kiểm tra defining loader** để chắc scenario B thực sự define class riêng, chứ không chỉ đều trả Class của parent.
8. Đo memory/metaspace cùng thời gian, không chỉ wall-clock latency.
9. Báo p95/p99, throughput, allocations và chính xác workload; không gán một hằng số overhead chung cho mọi Java application.

Có thể dùng **JMH** cho microbenchmark JVM vì nó hỗ trợ warmup, forks, measurement và các biện pháp tránh lỗi đo thường gặp. Nhưng ngay cả JMH cũng cần benchmark mô phỏng đúng lifecycle (setup + load + instance + work + close), không chỉ đo constructor URLClassLoader.

### Vì sao System.nanoTime một lần dễ gây sai?

~~~java
long start = System.nanoTime();
// Một thao tác bạn muốn đo.
long nanos = System.nanoTime() - start;
~~~

Đây chỉ là đoạn minh họa. Thời gian có thể bị ảnh hưởng bởi JIT warmup, class initialization, OS file cache, GC, thread scheduling hoặc CPU frequency. Nếu benchmark không làm kết quả tính toán quan sát được, JVM cũng có thể tối ưu bỏ một số phép tính.

**Đo công việc tương đương:** đối với per-request, phải tính cả load/link/instance/close. Đối với reuse, phải tính setup vào cold-start và chia chi phí trên số request thích hợp khi đánh giá tổng chi phí. Không so lượt chạy cold của A với steady-state của B rồi rút kết luận.

### JVM diagnostics

Với JDK hỗ trợ unified logging, có thể chạy:

~~~bash
java -Xlog:class+load=info -cp out/host LoaderReuseDemo out/plugin
~~~

Log có thể nhiều dòng và thay đổi theo môi trường, không nên chép thành stdout mẫu. Có thể xem thêm JFR/Java Mission Control, heap dumps và JVM metrics, class unloading logs khi phân tích memory/loader retention. **Đừng coi class unloading logs đồng nghĩa JAR handles đã được đóng**: đây là hai tài nguyên khác nhau.

## 8. Concurrency: reuse loader không đồng nghĩa reuse mutable object

Một ClassLoader được nhiều threads dùng để nạp class vẫn phải tuân thủ đồng bộ/locking của `loadClass`. Nhưng các objects và static state mà nó định nghĩa **không tự động thread-safe**.

Trong ví dụ:

~~~java
private static int constructions;

public Worker() {
    constructions++;
}
~~~

Nếu nhiều threads cùng tạo Worker, phép `++` không atomic, có thể mất updates. Một lựa chọn minh họa:

~~~java
private static final java.util.concurrent.atomic.AtomicInteger
        COUNT = new java.util.concurrent.atomic.AtomicInteger();

public Worker() {
    COUNT.incrementAndGet();
}
~~~

Hai đoạn này là thành phần của class, không phải chương trình độc lập. Với real service, có thể dùng immutable values, request-scoped objects, pooling thích hợp, locks hoặc concurrent collections tùy bài toán.

**Không giải quyết thread safety bằng cách mở một URLClassLoader mỗi request** nếu các requests chia sẻ tài nguyên khác như database/file/host registry. Nó có thể tách một số static fields, nhưng không thay một thiết kế concurrency đúng.

### Có cần một pool ClassLoader?

Pool nhiều class loaders cho cùng plugin/version có thể làm tăng số runtime class definitions, static copies và JAR resources; object từ loader A có thể không cast sang concrete Class của loader B. Nếu không cần cô lập namespace, thường không có lý do để tạo pool loaders lớn. Hãy cân nhắc pool **service instances** thay vì pool loader objects khi có bottleneck thực sự.

## 9. Reuse đúng vòng đời: per plugin, per version, đôi khi per tenant

Một lựa chọn kiến trúc thông dụng:

~~~text
Application Loader
  ├── api.Task       (shared contract)
  └── PluginManager
           |
           +-- Plugin "pricing" v1 --> Loader L1
           |                           Request A/B/C
           |
           +-- Plugin "pricing" v2 --> Loader L2
                                       Request D/E/F
~~~

Ưu điểm: các request của cùng version chia sẻ một code namespace, còn v1/v2 không bị ép chia cùng concrete Class identity.

Với hot reload:

1. Đặt JAR mới dưới tên file riêng theo version, tránh ghi đè file đang được loader cũ giữ.
2. Tạo loader mới L2 và kiểm tra plugin/service readiness.
3. Chuyển routing request mới sang v2; request cũ có thể hoàn thành ở v1.
4. Khi v1 quiesced, dừng plugin tasks/threads/callbacks, đóng InputStreams, JarFile/ZipFile riêng.
5. Đóng URLClassLoader v1 khi không còn hoạt động nạp class đồng thời.
6. Xóa strong references tới L1, old Class/Method caches, registry entries, ThreadLocals/TCCL khi appropriate.
7. Dọn file JAR cũ khi các file handles đã được giải phóng.

`URLClassLoader.close()` có contract riêng: nó đóng những file do loader mở và hạn chế nạp class/resource mới, nhưng không hủy mọi instances/classes đã được định nghĩa. Nếu có thread đang loading khi close, kết quả không được bảo đảm; do đó quản lý request-in-flight và stop lifecycle là cần thiết.

**Đừng reuse mãi một loader cho mọi version.** Khi Worker đã được loader L1 định nghĩa, thay JAR trên ổ đĩa không làm JVM định nghĩa lại Worker v2 trong L1. Loader mới là một ranh giới version hợp lý.

### Trường hợp cần nhiều loaders hơn

- Tenant A và B có code/classpath/dependencies thực sự khác nhau.
- Plugin versions khác nhau cần tồn tại song song.
- Những batch dynamic code có lifecycle unload độc lập.
- Named module configurations/ModuleLayers được resolve khác nhau.
- Test class loading policy hoặc class identity.

Khi đó hãy tạo loader **theo ranh giới cô lập cần thiết**, quản lý số lượng và thời điểm retire rõ ràng. Loader riêng không phải sandbox bảo mật cho code không tin cậy: class loader không tự cô lập process, filesystem, network hoặc CPU.

## 10. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo URLClassLoader cho mỗi request không cần thiết | Repeated setup/loading, allocation & cleanup churn | Reuse theo plugin/version |
| Chia sẻ một service instance mutable cho nhiều requests | Race condition/state leakage | Instance riêng hoặc service thread-safe |
| Giả định loader mới luôn trả Class mới | Parent có thể define class, benchmark sai | So sánh Class object và defining loader |
| Coi static field là biến dùng chung toàn JVM | Class copies có static state riêng | Dùng API/shared state ở parent hoặc explicit store |
| Đóng loader ngay sau loadClass rồi trả instance sử dụng lâu | Lỗi lazy class/resource loading | Giữ loader sống theo phiên phục vụ |
| Không close loader/stream sau retire | JAR file handles và resource leakage | Try-with-resources/lifecycle shutdown |
| Cache Class/Method trong singleton host không xóa khi reload | Loader cũ không được GC | Cache có version scope và clear |
| Đưa plugin JAR vào host application classpath | Parent-first phá expected isolation/reload | Tách source plugin khỏi -cp host |
| Dùng per-request loader như security sandbox | Không cô lập quyền OS | Process/container isolation thích hợp |
| Benchmark chỉ đo new URLClassLoader | Không bao gồm class lookup, initialize và close | Đo trọn request lifecycle |
| Benchmark một lần trên JVM cold | Lẫn startup, GC và JIT | Warmup, forks, multiple runs |
| Dùng một loader cho v1 và v2 rồi sửa file JAR | Class bytecode đã define không tự cập nhật | Tạo loader mới cho version mới |
| Dùng child-first cho shared API | Hai bản API runtime, ClassCastException | Parent-first cho contract package |

## 11. Checklist chẩn đoán hiệu năng

1. Mỗi request có thực sự cần **code namespace mới** không, hay chỉ cần instance/state mới?
2. Mỗi plugin/version tạo bao nhiêu loaders? Có hạn mức và owner không?
3. Class plugin được **loader nào định nghĩa**? `type.getClassLoader()` và `Class<?>` identity có đúng không?
4. Parent đã định nghĩa class từ trước hay child tự define?
5. Thời gian nạp/verify/link/initialize lần đầu so với xử lý request steady-state thế nào?
6. Metaspace/class counts, heap allocations, JIT/GC có tăng khi tạo nhiều loaders?
7. TCCL, ThreadLocal, task queues, registries hoặc static caches có giữ loaders cũ?
8. Có resource/JAR handle còn mở, hoặc file bị lock trên Windows sau reload không?
9. Loader có còn bị requests sử dụng khi gọi `close()` không?
10. Shared API/interfaces có nằm ở parent và dùng cùng Class identity giữa plugins không?
11. Test load/cast/reload có trường hợp concurrent request và nhiều versions không?
12. Benchmark có đo cùng workload, N requests, concurrency, warm-up và ghi p95/p99/throughput không?

## 12. Tự kiểm tra kiến thức

**Câu 1.** Một loader nạp `demo.Worker` rồi gọi `loadClass("demo.Worker")` thêm 100 lần. JVM có tạo 100 Class objects khác nhau không?

**Đáp:** Không theo hợp đồng class loading thông thường. Cùng binary name và initiating loader sẽ có Class identity nhất quán; có thể còn lookup overhead nhưng không define mới cho mỗi lần gọi.

**Câu 2.** Hai URLClassLoader khác nhau cùng đọc Worker.class có bắt buộc trả hai runtime Class khác nhau không?

**Đáp:** Không. Nếu đều delegate về parent đã định nghĩa Worker, chúng có thể cùng trả bản parent. Nếu mỗi child thực sự tự define Worker, lúc đó hai Class identities khác nhau.

**Câu 3.** Reuse loader có bắt buộc dùng chung một service object giữa requests không?

**Đáp:** Không. Nhiều request có thể tạo instances riêng từ cùng một runtime Class.

**Câu 4.** Vì sao static counter khởi đầu lại ở mỗi loader mới?

**Đáp:** Khi child mới tự định nghĩa bản Worker runtime riêng, mỗi Class có static storage/initialization riêng.

**Câu 5.** Đóng loader per request có đảm bảo class unload lập tức không?

**Đáp:** Không. Unloading phụ thuộc reachability và JVM GC; `close()` chủ yếu quản lý nguồn class/resource loading và file handles.

**Câu 6.** Khi nào cần tạo loader mới thay vì reuse?

**Đáp:** Khi muốn classpath/version/tenant/batch code namespace độc lập. Thường tạo theo **plugin version** hoặc ranh giới nạp mã, không phải per request.

**Câu 7.** Có thể kết luận reuse nhanh gấp mười lần chỉ từ ví dụ sáu dòng stdout không?

**Đáp:** Không. Ví dụ chứng minh runtime class identity và static state, **không đo performance**. Cần benchmark cold/steady-state, throughput, allocations và memory.

**Câu 8.** Vì sao reuse loader nhưng vẫn có thể gặp memory leak?

**Đáp:** Loader sống quá lâu, caches/threads/registries giữ old Class references qua nhiều versions, hoặc không close resources khi retire. Reuse phải đi cùng lifecycle rõ ràng.

## Tài liệu tham khảo chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, delegation và getClassLoadingLock.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): tìm class từ URL và `close()`.
- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime class identity và defining loader.
- [JVMS Java SE 21 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): static initialization.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): Class objects và `getClassLoader`.
