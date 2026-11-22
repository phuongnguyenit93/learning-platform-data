# Đánh đổi giữa số loader, mức cô lập và dung lượng metaspace

> **Java Core → ClassLoader → Hiệu năng.** Trong kiến trúc plugin, nhiều `ClassLoader` có thể giúp các module dùng dependency khác phiên bản, nạp/hủy riêng từng thế hệ và bảo vệ định danh kiểu giữa các plugin. Nhưng nếu mỗi loader **tự định nghĩa lại hàng nghìn runtime classes**, JVM phải giữ thêm metadata cho những class definitions ấy. Bài học phân tích trade-off giữa **số lượng loader**, **granularity của isolation**, **Metaspace đã dùng/committed/reserved**, **class unloading**, chi phí heap/JIT/I/O và cách benchmark đúng trên Java 17+ (HotSpot). Mục đích là chọn ranh giới loader theo nhu cầu thực tế, không mặc định “một loader luôn tốt” hoặc “càng nhiều loader càng tốt”.

## 1. Ba biến cần cân bằng

Một plugin system thường phải đạt ba mục tiêu:

1. **Cô lập:** tránh xung đột binary names và versions giữa các plugins, có khả năng thay plugin mà không restart toàn JVM.
2. **Bộ nhớ:** giới hạn số classes/metadata trùng lặp, heap caches, JIT-compiled code, class-loading infrastructure và số JAR handles.
3. **Vận hành:** khởi tạo đủ nhanh, shutdown/unload được, định danh shared APIs luôn đúng và chẩn đoán được khi có leak.

Sơ đồ khái niệm:

~~~text
       ÍT LOADER                             NHIỀU LOADER
            |                                      |
  +--------------------+               +------------------------+
  | Loader chung       |               | Loader P1  | Loader P2  |
  | plugin A + B + C   |               | lib 1.0    | lib 2.0    |
  +--------------------+               +------------+-----------+
            |                                      |
  + Ít định nghĩa trùng                     + Isolate versions/ABI
  + Ít overhead loader/JAR                  + Retire P1 độc lập
  - Khó unload A riêng                      - Class metadata có thể trùng
  - Dễ đụng version                        - Thêm loaders, caches, locks,
                                              lifecycle/resource owners
~~~

**Không thể kết luận dung lượng chính xác chỉ từ `loaderCount`.** Cần biết mỗi loader định nghĩa bao nhiêu classes, classes lớn đến đâu, số dependencies shared hay private, có module layer/generated classes hay không và bao nhiêu generations cũ còn reachable.

## 2. Cơ chế gốc: runtime type identity

Theo JVM Specification, một runtime class/interface được xác định bởi **binary name và defining class loader**.

~~~java
Class<?> a = loaderA.loadClass("plugins.Widget");
Class<?> b = loaderB.loadClass("plugins.Widget");
boolean sameType = a == b;
~~~

Đây là snippet minh họa; `sameType` **có thể true** nếu cả A và B delegate tới một parent đã định nghĩa `plugins.Widget`. Nó **false** nếu mỗi loader tự `defineClass` ra `plugins.Widget`. Vì vậy số **loader objects** không bằng số **class definitions**.

### 2.1. Hai trường hợp phải phân biệt

**Trường hợp parent sharing:**

~~~text
               SharedParentLoader
                 define api.Service
                 define common.JsonCodec
                   /        \
          PluginLoaderA   PluginLoaderB
          define AImpl    define BImpl
                   \        /
                   shared API classes
~~~

Với parent-first delegation, các child loaders có thể trả về cùng `api.Service.class` và `common.JsonCodec.class`, nên không cần tự nhân đôi metadata cho **các runtime classes được parent định nghĩa**.

**Trường hợp duplicate private definitions:**

~~~text
         PluginLoaderA                 PluginLoaderB
       define vendor.Parser          define vendor.Parser
       define vendor.Model           define vendor.Model
       define vendor.Util            define vendor.Util

         vendor.Parser@A != vendor.Parser@B
~~~

Mỗi loader có một class definition riêng, static fields riêng và identity khác nhau. VM có thể tái sử dụng hoặc chia sẻ một số dữ liệu ở những cấp khác tùy implementation, nhưng **không xem hai runtime classes như một type duy nhất**, và phải quản lý metadata của từng definition.

**Quan trọng:** Một runtime `Class<?>` nạp qua child delegation vẫn có `getClassLoader()` trỏ về **defining parent**, không phải nhất thiết child phát lệnh `loadClass` (initiating loader). Khi đo duplication, nên đếm **definitions theo defining loaders**, không chỉ số lần `loadClass` được gọi.

## 3. Metaspace chứa gì, khác Java heap thế nào?

Trên HotSpot hiện đại, Metaspace dùng vùng native memory để quản lý nhiều loại **class metadata** (ví dụ representations của classes, methods và constant-pool metadata). Java heap và Metaspace là các miền khác nhau trong phân tích hiệu năng.

| Thành phần | Khu vực/vòng đời khái niệm | Hệ quả khi nhân bản plugin |
| --- | --- | --- |
| Runtime class metadata | HotSpot Metaspace; gắn với class loader data/lifetime | Định nghĩa cùng bytecode ở nhiều loaders có thể tăng metadata |
| Compressed class pointers/class metadata | Có thể nằm trong compressed class space trên HotSpot với cấu hình tương ứng | Có reserved virtual space lớn nhưng committed ít |
| `Class<?>` mirrors, instances, arrays, static object graphs | Heap và runtime VM references | Static cache/instances cũng có thể tăng với mỗi generation |
| Dynamic proxies/lambda-generated classes | Runtime class definitions + heap instances | Có thể tăng cả metadata, JIT/code cache và object counts |
| Compiled methods | Code cache / JIT-managed native memory | Hot methods của từng runtime class có thể cần compilation riêng |
| Loader objects / URLs / cache structures | Java heap | Phụ thuộc loader implementation và số resources |
| `JarFile`/open streams/file handles | VM/OS resources | Phụ thuộc lifecycle và URLClassLoader.close() |
| Threads/executors | Heap + native stacks/OS resources | Plugin per-loader thread pools có thể rất tốn chi phí khác Metaspace |

### 3.1. Ba số khác nhau: used, committed, reserved

Các thống kê HotSpot/JMX thường phân biệt:

- **Used:** dung lượng metadata mà allocator đang dùng theo phép đo tương ứng.
- **Committed:** dung lượng physical/virtual-memory backing đã được commit cho pool; có thể lớn hơn used vì allocator có khoảng trống/quản lý chunks.
- **Reserved:** dải **virtual address space** đã đặt trước để có thể commit về sau; không đồng nghĩa process thực dùng lượng RAM tương đương.

Ví dụ một dòng `reserved = 1 GiB` cho compressed class space **không nói JVM đang dùng 1 GiB RAM cho class metadata**. Phải so used/committed, và với memory pressure kiểm tra thêm process RSS/cgroup, GC/JIT/thread/native allocations.

**Không cộng bừa** JMX Metaspace pool và mọi Native Memory Tracking (NMT) buckets như hai khoản độc lập: các công cụ có thể đang mô tả **cùng** allocations ở mức phân loại/chi tiết khác nhau.

### 3.2. Metaspace không phải PermGen

Java 8 bỏ PermGen và giới thiệu Metaspace trong HotSpot (JEP 122). Java 17/21/25 không nên cấu hình `-XX:MaxPermSize` hay dùng PermGen như cách gọi cho metadata hiện đại. Tuy nhiên “Metaspace” là một đặc điểm **HotSpot JVM implementation**, không phải JLS bắt buộc mọi JVM có pool với đúng tên và layout này.

Bộ nhớ tăng trong plugin system không phải lúc nào cũng ở Metaspace: `static byte[]` lớn tăng **heap**, thread stacks tăng **native memory**, còn JIT compiled code làm tăng **code cache**.

## 4. Mô hình ước lượng: không có số MB cố định cho mỗi loader

Một mô hình tư duy (không phải công thức HotSpot chính thức):

\[
M_{\mathrm{metadata}} \approx M_{\mathrm{shared}} +
  \sum_{i=1}^{N} M_{\mathrm{classes\ defined\ by\ loader}\ i}
  + M_{\mathrm{allocator\ overhead}}
\]

Mỗi `M_classes` phụ thuộc class count, methods/fields/constant pool, invokedynamic/generated classes và tình trạng live. Loader có thể tạo **0** class definitions (toàn bộ delegation); loader khác định nghĩa hàng chục nghìn types.

Ví dụ **để lập luận, không phải benchmark**:

- 10 loaders, mỗi loader chỉ định nghĩa 3 classes riêng và dùng 1.000 classes từ parent: duplication thấp.
- 10 loaders, mỗi loader định nghĩa độc lập 1.000 classes tương tự: có thể có khoảng 10.000 runtime definitions plugin-side thay vì 1.000.
- 100 loaders mà mỗi loader giữ JAR scan caches, URL streams và threads riêng: tăng tổng footprint ở nhiều khu vực khác Metaspace.

**Không được nhân “số loader × 1 MB” rồi công bố là kết quả đo.** Một vài lớp cực lớn có thể tốn hơn nhiều lớp nhỏ; đồng thời allocator fragmentation, GC events và JVM flags khiến used/committed khác nhau.

### 4.1. Sharing nào vẫn khả thi?

ClassLoader delegation giúp **runtime class identity** được chia sẻ ở parent. Nếu plugins cần dùng `api.Plugin` và các DTO ở boundary, chia sẻ chúng qua parent không chỉ tiết kiệm metadata mà còn tránh `ClassCastException` kiểu “X cannot be cast to X”.

Tuy nhiên sharing **không đồng nghĩa** parent phải giữ mọi thư viện. Khi hai plugin yêu cầu binary-incompatible versions của một library, nếu đưa cả library vào một parent-first shared loader, host có thể gặp `NoSuchMethodError`, `ClassNotFoundException`, `IllegalAccessError` hoặc behavior sai. Với dependency version conflict có thật, **isolation đáng trả giá**.

## 5. Các phương án thiết kế và trade-off

| Cấu hình | Isolation | Chi phí bộ nhớ dự kiến | Vòng đời/reload |
| --- | --- | --- | --- |
| Một loader cho host + tất cả plugins | Thấp | Ít duplicated definitions | Khó unload plugin độc lập; thường cần restart |
| Shared parent API + một loader cho mỗi plugin | Tốt giữa implementations | Metadata riêng cho private classes, shared API không nhân bản | Thay/retire từng plugin tương đối rõ |
| Một loader cho mỗi tenant có cùng bộ bytecode | Rất cao giữa tenants | Có thể nhân bản rất nhiều definitions/caches | Tách tenant đời ngắn, nhưng dễ OOM |
| Một loader cho mỗi plugin generation | Tách V1/V2 | **Peak overlap** khi V1 và V2 cùng tồn tại | Phù hợp rolling update; phải drain V1 |
| Group loader cho các plugins tin cậy, dependency tương thích | Trung bình | Giảm duplication trong group | Unload một plugin khó hơn; coupling tăng |
| Một loader mới cho mỗi request | Rất cao nhưng thường không cần | Startup/link/JIT/metadata churn lớn | Hầu như không hợp lý cho service request thông thường |
| Plugin trong process/JVM riêng | Boundary mạnh hơn classloader | Tổng JVM baselines lớn hơn | Quản lý độc lập, có thể giới hạn RAM/CPU theo OS |

Không có một lựa chọn thắng mọi cột. Tùy yêu cầu **bảo mật, ABI, tenant isolation, release cadence, Metaspace budget, latency SLO và độ tin cậy của cleanup**.

### 5.1. Khi nên dùng một loader mỗi plugin?

Hợp lý khi:

- Plugin có dependencies riêng (kể cả versions xung đột).
- Cần hot swap plugin V1/V2 mà không restart ứng dụng.
- Muốn có resource ownership/routing boundaries rõ.
- Số plugins và số class definitions còn trong ngân sách bộ nhớ.
- Shared API types nằm ở loader sống ổn định và được versioning.

Đây là lựa chọn mặc định tốt cho nhiều plugin managers, **nhưng phải đo** với workload và số plugins thật, không coi là “miễn phí”.

### 5.2. Khi nên group loaders?

Có thể group khi nhiều modules dùng **cùng phiên bản dependencies** và phải luôn deploy/retire cùng nhau. Ưu điểm là bớt duplicate classes và JAR scan metadata. Nhược điểm:

- Một group loader là một namespace; không thể nạp hai phiên bản cùng binary name.
- Static singletons và mutable state trong group có thể bị dùng chung ngoài dự kiến.
- Reload một module có thể buộc thay cả group.
- Sai hỏng liên quan class initialization của một type có thể ảnh hưởng nhiều modules trong group.

Chọn group **theo compatibility và lifecycle coupling**, không chỉ theo mong muốn tiết kiệm vài MB.

### 5.3. Một loader mỗi tenant: cẩn thận hệ số nhân

Giả sử hệ SaaS có 500 tenants dùng bytecode plugin giống nhau. Nếu mỗi tenant có loader riêng và định nghĩa lại toàn bộ framework/dependencies, class metadata/caches có thể tăng theo số tenants dù business logic giống hệt.

Nếu không yêu cầu **runtime type identity isolation**, thường tốt hơn:

- Shared application/plugin classes cho các tenants.
- Isolate mutable tenant state ở **objects và request contexts**, không tạo mới ClassLoader.
- Giới hạn quyền ở API/business boundary (authorization/capabilities), không coi ClassLoader là sandbox bảo mật.
- Nếu thật sự cần tenant-level security/process limits, xem xét process/container isolation và measure baseline costs.

**ClassLoader không là security boundary đầy đủ.** Từ JDK 24, Java Security Manager đã bị vô hiệu hóa vĩnh viễn (JEP 486); custom loader không tự ngăn plugin đọc file/network trong cùng process.

## 6. Peak Metaspace khi rolling update và hot reload

Một hệ thống có V1 active và đang chuẩn bị V2:

~~~text
Time ----->
      V1 active metadata
      |===========================|
                        V2 prepare/live metadata
                        |===========================|
                        ^ cutover         ^ V1 có thể GC/unload sau drain

Khoảng OVERLAP:
  V1 metadata + V2 metadata + associated heap/resources
~~~

Ở thời điểm cutover, code V1 có thể vẫn xử lý **in-flight requests**. Nếu V2 được prewarm với nhiều classes, peak Metaspace có thể cao hơn trạng thái ổn định. Trong trường hợp V1 chưa unload vì cache/TCCL/listener/stack còn giữ loader, generations tích lũy và mức dùng tăng qua các lượt reload.

### 6.1. Ví dụ tính capacity không giả số liệu giả

Giả sử đo thực tế:

- `M_live`: committed metadata khi một generation active ổn định.
- `Delta_prepare`: phần committed metadata tăng thêm khi load/prewarm V2.
- `Delta_overlap_other`: heap/code cache/thread/JAR native memory tăng ở overlap.
- `Headroom`: memory margin cho GC/JIT/traffic bursts.

Sau khi xác lập baseline và đo lặp, cần ngân sách ít nhất đủ cho **steady state + peak overlap + margin**, và không vượt giới hạn process/cgroup/host. Nếu các thông số chưa đo, **không** gán số MB tùy ý cho chúng.

### 6.2. Vì sao chỉ `active = newGeneration` không giải phóng V1?

References có thể còn từ:

- Request đang thực thi method của V1.
- `Thread.currentThread().getContextClassLoader()` (TCCL) của pool worker.
- `ThreadLocal` value, static map trong host, reflection `Class/Method/MethodHandle` caches.
- `ServiceLoader` provider caches và DI/framework registries.
- Executor tasks, event listeners, logging/JDBC registrations, JNI references.
- `ModuleLayer` hoặc `ClassLoader` được registry còn giữ.

Phải **quiesce → drain → unregister/close → clear caches/restore TCCL → close loader → release strong references**. `URLClassLoader.close()` giải phóng các JAR/file handles do loader quản lý; không trực tiếp hủy các `Class<?>` đã nạp và không ép JVM class unload.

## 7. Elastic Metaspace và điều không nên hứa

JEP 387 **Elastic Metaspace** (tích hợp từ JDK 16) cải tiến cách HotSpot quản lý và **uncommit memory không còn cần** sau class unloading. Nó giúp một workload tạo/hủy nhiều loader generations có cơ hội trả một phần committed memory về hệ điều hành linh hoạt hơn trước.

Nhưng:

- JEP 387 **không có nghĩa** mọi byte class metadata từ loader cũ sẽ lập tức biến mất sau `close()`.
- Đầu tiên loader cần **eligible for GC**; còn strong roots thì metadata vẫn cần tồn tại.
- JVM/GC có thể chưa chạy unload cycle; allocator có thể giữ chunks để tái sử dụng hoặc còn committed phần đang dùng.
- **Reserved virtual space** có thể lớn và ổn định dù committed/used giảm; không nhầm điều đó với native RAM leak.
- Cấu hình collector, version, flags như `-XX:MetaspaceReclaimStrategy`, compressed class space và OS ảnh hưởng reclamation/metrics; đừng lấy một flag làm thuốc chữa classloader leak.

**Nên tối ưu nguyên nhân** (loader reuse hợp lý, sharing, cleanup) trước khi tăng giới hạn memory. Nếu có retention path từ host, tăng `-XX:MaxMetaspaceSize` chỉ trì hoãn sự cố chứ không xóa root.

## 8. Lab 1 Java 17+: cùng bytecode, hai defining loaders

Bài lab so sánh một loader dùng lại và hai loader thực sự định nghĩa cùng binary name. Chạy Java 17+; **không** đưa plugin JAR lên application classpath.

### 8.1. Cây thư mục

~~~text
loader-tradeoff-lab/
├─ plugin-src/demo/plugin/Action.java
├─ host-src/LoaderIdentityDemo.java
└─ build/
   ├─ plugin/      (tạo khi build)
   ├─ host/
   └─ action.jar
~~~

**`plugin-src/demo/plugin/Action.java`**

~~~java
package demo.plugin;

public final class Action {
    public String name() {
        return "action";
    }
}
~~~

**`host-src/LoaderIdentityDemo.java`**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build", "action.jar")
                .toAbsolutePath().toUri().toURL();

        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader shared =
                     new URLClassLoader(new URL[] {jar}, parent);
             URLClassLoader isolatedA =
                     new URLClassLoader(new URL[] {jar}, parent);
             URLClassLoader isolatedB =
                     new URLClassLoader(new URL[] {jar}, parent)) {

            Class<?> shared1 = shared.loadClass("demo.plugin.Action");
            Class<?> shared2 = shared.loadClass("demo.plugin.Action");
            Class<?> separateA = isolatedA.loadClass("demo.plugin.Action");
            Class<?> separateB = isolatedB.loadClass("demo.plugin.Action");

            System.out.println("one loader, same class="
                    + (shared1 == shared2));
            System.out.println("different loaders, same class="
                    + (separateA == separateB));
            System.out.println("same binary name="
                    + separateA.getName().equals(separateB.getName()));
            System.out.println("different defining loaders="
                    + (separateA.getClassLoader()
                        != separateB.getClassLoader()));
        }
    }
}
~~~

### 8.2. Biên dịch và chạy (POSIX shell)

~~~bash
mkdir -p build/plugin build/host

javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Action.java

jar --create --file build/action.jar -C build/plugin .

javac --release 17 -d build/host \
    host-src/LoaderIdentityDemo.java

java -cp build/host LoaderIdentityDemo
~~~

**Stdout kỳ vọng:**

~~~text
one loader, same class=true
different loaders, same class=false
same binary name=true
different defining loaders=true
~~~

Điều lab **chứng minh**: cùng một binary name có thể chỉ có một runtime type trong shared loader, nhưng có **hai runtime types** khi mỗi isolated loader tự define bytes của JAR. Điều lab **không tự đo**: số byte Metaspace tăng chính xác, thời gian nạp class, throughput hay GC class unloading.

`try-with-resources` đóng loader-owned JAR handles. Các `Class<?>` local variables vẫn tồn tại trong scope, và loader classes có thể tiếp tục sống sau close nếu còn references khác; không khẳng định “đóng xong là trả hết Metaspace”.

### 8.3. Shared API trong thiết kế thực tế

Khi host và plugins cần cast object về một interface chung, **parent phải define shared API**. Một plugin class khác defining loader có thể có cùng tên interface nhưng **không assignable** với interface host nếu child tự define lại. Vì vậy sharing `api.PluginService` vừa tiết kiệm metadata vừa bảo vệ type identity; plugin-specific implementation vẫn nên để child tự define.

## 9. Lab 2 Java 17+: quan sát ClassLoadingMXBean và Metaspace MXBean

Dùng Java Management API đọc được **loaded class count**, số classes đã unload và các memory pools hiện có. Giá trị là runtime observations; **không có stdout số cố định giữa JDK/OS/GC**.

**`host-src/LoaderMetrics.java`**

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.MemoryType;

public final class LoaderMetrics {
    public static void main(String[] args) {
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("loaded-now=" +
                classes.getLoadedClassCount());
        System.out.println("loaded-total=" +
                classes.getTotalLoadedClassCount());
        System.out.println("unloaded-total=" +
                classes.getUnloadedClassCount());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                continue;
            }
            System.out.printf("%s: used=%d committed=%d max=%d%n",
                    pool.getName(), usage.getUsed(),
                    usage.getCommitted(), usage.getMax());
        }
    }
}
~~~

~~~bash
javac --release 17 -d build/host host-src/LoaderMetrics.java
java -cp build/host LoaderMetrics
~~~

**Không có expected numerical stdout**: tên pools, counts và values khác nhau tùy JVM/startup; `getMax()` trả giới hạn ước tính của pool hoặc `-1` nếu không xác định. **Nhãn `max` là giới hạn pool do `MemoryUsage.getMax()` trả về (hoặc `-1` nếu không xác định), không phải reserved address space.** `MemoryUsage` trả `init, used, committed, max`, **không có trường reserved**.

### 9.1. Kết hợp metrics vào phép so sánh hợp lệ

Thực hành đúng:

1. Chạy workload A với một shared loader trong một JVM riêng; warm up ổn định.
2. Chạy workload B với K isolated loaders trong một JVM khác, cùng JDK/heap/GC flags, cùng set classes đã dùng.
3. Lặp nhiều lần, chụp JMX/class count/Metaspace metrics tại **các mốc tương đương**.
4. Đo cả `System.nanoTime` cho từng phase load/initialization, latency/throughput, CPU, allocations và file handles nếu đây là bottleneck.
5. Với benchmark có nhiều loaders, mỗi class nên thực sự được định nghĩa bởi loader cần test, không vô tình delegate implementation về host.
6. Trừ/so baseline và mô tả jitter; không so hai giá trị đọc liên tiếp mà mặc định tất cả biến động chỉ do loader count.

**Lưu ý:** `ClassLoadingMXBean.getTotalLoadedClassCount()` là cumulative từ khi VM chạy, **không phải số đang sống**; `getLoadedClassCount()` là số currently loaded. Khi đánh giá leak, theo dõi xu hướng **current loaded classes/loaders** và class unloading sau nhiều vòng, không chỉ cumulative count luôn tăng theo tự nhiên.

## 10. Đo bằng jcmd, Native Memory Tracking và logging trên HotSpot

Các công cụ sau được tài liệu JDK 25 mô tả; **support và flags phụ thuộc JVM/distribution**:

~~~bash
# Với PID đã xác định từ jcmd -l:
jcmd <pid> help

# Thống kê class loaders:
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders

# Metaspace summary và breakdown theo loader (nếu hỗ trợ):
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.metaspace show-loaders

# Native Memory Tracking summary (nếu đã bật khi startup):
jcmd <pid> VM.native_memory summary

# Theo dõi class loading/unloading trong một lần chạy:
java -Xlog:class+load=info,class+unload=info \
    -cp build/host LoaderIdentityDemo
~~~

Đây là **mẫu lệnh chẩn đoán**, thay `<pid>` bằng PID thật và đảm bảo class files của lab có sẵn. Nếu command bị từ chối, chạy `jcmd PID help`/`jcmd PID help VM.metaspace` để xem options của runtime thật.

### 10.1. NMT phải bật trước khi đo

Khởi chạy ứng dụng với:

~~~bash
java -XX:NativeMemoryTracking=summary \
    -cp build/host LoaderIdentityDemo
~~~

Trong process chạy dài, bạn có thể dùng:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

**Không dùng chuỗi lệnh hai process ngắn để tin rằng PID còn tồn tại.** Lab trên kết thúc nhanh; các lệnh jcmd/NMT phải chạy với JVM sống đủ lâu, hoặc áp dụng vào service thực / harness giữ JVM chờ.

NMT theo dõi **JVM native memory**, không phải toàn bộ allocations của arbitrary native libraries do bên thứ ba tạo. NMT cũng có overhead runtime; không bật `detail` khắp production nếu chưa đo và có nhu cầu rõ. Các nhóm NMT như Class, Thread, Code, GC phản ánh các thành phần khác nhau của footprint.

### 10.2. Một biểu đồ capacity nên gồm gì?

Nếu hệ thống có dashboard, theo dõi ít nhất:

- Active plugin/tenant/generation count và số defining loaders còn live.
- Classes currently loaded, classes loaded/unloaded theo thời gian.
- Metaspace used/committed (và compressed class space nếu có).
- Native memory category Class/Code/Thread, process RSS và cgroup memory.
- Heap used/GC pause times, số JAR file handles, số threads, JIT/code cache.
- Hot reload latency: chuẩn bị generation, cutover, drain, resource close.
- 95th/99th percentile request latency trong lúc load/unload/rollout.
- Rate của `OutOfMemoryError: Metaspace`, class-loader retention và leaked generations.

Cần đánh dấu **deployment/reload events** để giải thích spikes; không coi mọi peak ngay lúc rollout là leak.

## 11. Cách xác minh classloader leak thay vì đoán

Nếu Metaspace tăng qua mỗi lần plugin reload:

~~~text
ClassLoadingMXBean current count tăng
       |
       v
Các generations cũ đã STOP thật chưa?
       |
       +-- No --> còn in-flight tasks/callbacks: hợp lệ hoặc lifecycle lỗi
       |
       +-- Yes --> thấy ClassLoader V1 trong heap dump?
                     |
                     +-- Host static Map -> Class/Method/instance
                     +-- Worker -> TCCL hoặc ThreadLocal value
                     +-- EventBus -> listener/captured lambda
                     +-- ServiceLoader/DI/serializer cache -> provider/type
                     +-- ModuleLayer/driver/JMX registry -> classes/handles
~~~

Các bước:

1. Log generation id và defining loader identity khi load/retire.
2. Quiesce requests, stop executors/timers và unregister listeners.
3. Dọn host caches/ThreadLocal, restore TCCL, close owned streams/JARs.
4. Bỏ references host tới `Class<?>`, `Method`, MethodHandle, instances, layer/loader cũ.
5. Quan sát qua **nhiều vòng GC/class unload**, không đòi một deadline.
6. Nếu generations vẫn reachable, dùng heap dump/dominator tree để tìm **path to GC root**.
7. Đo lại với cùng workload; một lần `System.gc()` không chứng minh có hoặc không có leak.

JLS `12.7` cho phép class unloading khi defining loader có thể reclaimed; không yêu cầu JVM unload ngay. `URLClassLoader.close()` không phải `ClassLoader.unloadClass`. Trên một số JDK, metaspace used có thể giảm nhưng committed/RSS không giảm tức thì vì allocator/OS pages và GC policies.

## 12. Tối ưu kiến trúc trước khi tối ưu flags

Trình tự ưu tiên hợp lý:

1. **Gỡ duplication không cần thiết**: shared parent loader cho APIs/dependencies mà tất cả plugins thật sự dùng cùng version và lifecycle.
2. **Tách đúng private packages**: dùng loader riêng nơi cần version conflict hoặc hot reload.
3. **Giảm số generations đồng thời**: prewarm V2 có giới hạn, drain V1 sớm nhưng không gây lỗi request.
4. **Giới hạn số plugins/tenants trong một JVM** dựa trên profile memory thực, không dựa trên một hằng số suy đoán.
5. **Giảm eager loading và reflection scanning** nếu plugin chỉ dùng một phần lớn số classes; đo latency trước khi lazy load mọi thứ.
6. **Dọn cache/resource roots**: ServiceLoader, DI metadata, Method/MethodHandle caches, TCCL, ThreadLocal, threads, JAR handles.
7. **Benchmark pool/group strategy** trên lượng plugin thật, không giả định một benchmark micro cho biết SLO production.
8. **Sau cùng** mới cân nhắc `-XX:MaxMetaspaceSize`, container limits và reclaim flags trên JVM cụ thể; thử nghiệm với service-level metrics.

**MaxMetaspaceSize** là một giới hạn có thể giúp fail-fast/lập ngân sách trên HotSpot nhưng quá nhỏ gây `OutOfMemoryError: Metaspace`, quá lớn có thể che retention. Đừng tăng vô hạn khi biết rõ classloader leak.

### 12.1. Khi class sharing có thể phá compatibility

Nếu `Plugin A` cần `lib.JsonParser` version 1, `Plugin B` cần version 2 và cả hai không binary-compatible, ép chúng cùng dùng một parent class `lib.JsonParser` có thể làm một plugin chạy sai. Đổi lại, nạp riêng library trong A và B chiếm thêm metadata nhưng **đảm bảo chính sách type identity riêng**, miễn là public host boundary không expose private library types.

Giải pháp đúng là chia:
- `api.*` và DTO/shared contracts: **shared parent**.
- `plugin.impl.*` và private versioned dependencies: **child**.
- Không chuyển class phụ thuộc API giữa loaders bằng cast theo tên; dùng shared interface hoặc serialization/schema rõ ràng.
- Nếu custom child-first, limit theo packages, bảo vệ `java.*` và shared contract; việc tự viết `loadClass` đòi locking/parent-delegation chính xác.

## 13. So sánh isolation theo mục tiêu thực sự

| Yêu cầu | Cần riêng ClassLoader? | Thay thế/cân nhắc |
| --- | --- | --- |
| Hai phiên bản cùng binary name trong một JVM | Thường **có** | Process riêng hoặc relocation nếu phù hợp |
| Hot reload độc lập từng plugin | Thường **có**, loader thế hệ mới | Restart JVM khi thay trọn application |
| Mỗi tenant có thông tin cấu hình riêng | **Không nhất thiết** | Separate instances/config context/authorization |
| Cách ly quyền filesystem/network với code không tin cậy | **Không đủ** | Process/container/OS boundary |
| Cần unloading một phần ứng dụng | Loader scope theo lifecycle giúp đạt được | Không giữ references, GC eligibility |
| Giảm tối đa class metadata cho thư viện chung | Shared loader hữu ích nếu phiên bản tương thích | CDS/archiving tùy JDK nhưng phải đo, không thay class identity |
| Rút ngắn startup plugin | Có thể giảm eager scanning/prewarm | Đo class loading costs và lazy init phù hợp |
| Tách crash của native code | ClassLoader không đủ | Process isolation |
| Tối ưu throughput nhiều plugin | Phụ thuộc workload | Locking, pool use, JIT, GC, bytecode generation |

**Kết luận thiết kế:** “Cách ly càng sâu” càng nên được chứng minh bằng requirement rõ ràng. Isolate **state** bằng objects khi chỉ cần nhiều tenants dùng một phiên bản code; isolate **code/version** bằng loaders khi thật sự có nhiều runtime definitions; isolate **trust/resource failure** bằng process/OS boundaries khi cần security và fault containment.

## 14. Bài tập tự kiểm tra

1. Hai `URLClassLoader` cùng URL và cùng parent sẽ **luôn** có hai runtime classes khi gọi `loadClass("X")`? **Không**; nếu parent define X, cả hai có thể delegate cùng class.
2. Hai loaders tự define cùng binary name có phải một runtime type không? **Không**, định danh gồm defining loader.
3. Số loader objects bằng số class definitions? **Không**, một loader có thể define nhiều, ít hoặc zero classes.
4. Nhiều loaders tự define cùng library có thể tăng Metaspace không? **Có**, vì metadata của runtime definitions không giống một shared Class.
5. Thêm loader có luôn tốn một số MB cố định? **Không**; footprint tùy definitions, allocator, dependencies.
6. `reserved=1GiB` có đồng nghĩa JVM giữ 1GiB RAM thực trong Metaspace không? **Không**; xem used/committed.
7. Dùng nhiều loaders có thể giúp unload một plugin mà không restart JVM không? **Có thể**, khi isolation và lifecycle/root cleanup đúng.
8. `URLClassLoader.close()` lập tức unload classes? **Không**.
9. `System.gc()` bảo đảm class unload? **Không**.
10. V1 và V2 cùng tồn tại lúc rollout có thể tăng peak Metaspace? **Có**, nếu cả hai generations live.
11. Một `Method` trong host static cache có thể giữ plugin loader V1 không? **Có**.
12. Static field của plugin chỉ tự tham chiếu trong unreachable cycle có nhất thiết pin loader không? **Không**.
13. NMT `summary` dùng để quan sát gì? **Các nhóm JVM native memory**, không phải mọi allocations native của thư viện bên ngoài.
14. `ClassLoadingMXBean.getTotalLoadedClassCount()` là số đang loaded? **Không**, là cumulative kể từ JVM startup.
15. `getLoadedClassCount()` và `getUnloadedClassCount()` khác gì? **Currently live và cumulative unloaded**.
16. Một loader mỗi tenant khi mọi tenant dùng cùng code có luôn tốt hơn shared classes? **Không**, có thể nhân metadata/caches không cần thiết.
17. Dùng một loader cho plugin A và B khác dependency version có thể gặp gì? **Binary compatibility/class name conflict**.
18. Tại sao `MaxMetaspaceSize` không nên tăng trước khi tìm leak? **Chỉ trì hoãn áp lực bộ nhớ nếu retention path còn nguyên**.
19. JEP 387 có làm loader đang pinned tự unload được không? **Không**, trước hết phải giải phóng strong roots.
20. ClassLoader có đủ để cô lập plugin không đáng tin ở mức OS permission không? **Không**.

## 15. Checklist review trước khi đưa vào production

- [ ] Biết **số defining class loaders và class definitions**, không chỉ số object `ClassLoader`.
- [ ] Phân loại shared API, versioned dependency và private implementation packages.
- [ ] Có giới hạn tối đa active plugins/tenants/generations theo capacity test.
- [ ] Đo Metaspace **used/committed** và không nhầm reserved với RSS.
- [ ] Đo heap, thread stacks, code cache, JAR handles bên cạnh metadata.
- [ ] Load tests cover steady state, burst plugin startup và V1/V2 overlap.
- [ ] Có shutdown protocol cho loader generation: quiesce, drain, unregister, close, release.
- [ ] Có test class identity `SharedApi.class == pluginVisibleSharedApiClass`.
- [ ] Không còn TCCL/ThreadLocal/reflection cache giữ V1 sau retirement.
- [ ] Có dashboard classloader stats/class unload events theo generation.
- [ ] Kiểm tra JVM vendor/version/GC và tác động của NMT/diagnostic flags.
- [ ] Khi OOM Metaspace, kiểm tra loader retention trước khi nâng memory limit.
- [ ] Không dùng ClassLoader làm security sandbox cho untrusted code.
- [ ] Ghi rõ trade-off group loader vs per-plugin loader vs process isolation trong quyết định kiến trúc.

## 16. Nguồn tham khảo

1. [JVMS `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): định danh runtime class theo binary name và defining loader.
2. [JLS `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): điều kiện GC eligibility trước khi class unloading.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `defineClass`, `findLoadedClass`.
4. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): close và giới hạn của loader/resource lifecycle.
5. [JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): cải thiện chunk allocation/uncommit memory khi class metadata được giải phóng.
6. [JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): PermGen → Metaspace.
7. [ClassLoadingMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): currently loaded, total loaded và total unloaded counts.
8. [MemoryPoolMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): đo pool used/committed/max.
9. [The jcmd Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`, `VM.native_memory`.
10. [Native Memory Tracking — JDK 25 Troubleshooting](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): NMT categories, baseline/diff và overhead.
11. [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): vì sao ClassLoader không thay sandbox.
12. [ManagementFactory — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html): truy vấn class-loading và memory-pool MXBeans.

**Ghi nhớ:** Tăng số loader không **tự động** tương đương tăng Metaspace theo một hệ số cố định; chi phí đến từ **những runtime class definitions, allocator/metadata và resources thực sự sống**. Chia sẻ các types tương thích qua parent để giảm nhân bản, dùng loader riêng cho nơi thật sự cần version isolation/hot reload, và đo **peak overlap, used/committed, classes loaded/unloaded và strong roots** thay vì suy từ loader count hay reserved virtual memory.
