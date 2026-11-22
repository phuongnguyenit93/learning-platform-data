# JFR, heap dump và đường tham chiếu giữ class loader

Trong ứng dụng Java có plugin, application server, hot redeploy, script engine hoặc custom `URLClassLoader`, việc **tạo loader mới không đồng nghĩa loader cũ sẽ được garbage collector (GC) thu hồi ngay**. Class loader có thể còn được giữ bởi một đối tượng trong cache tĩnh, một worker thread giữ thread context class loader (TCCL), `ThreadLocal`, provider của `ServiceLoader`, listener, MBean, callback, JNI reference hoặc một đường tham chiếu bất ngờ.

Nếu các deployment đã dừng vẫn còn loader/class metadata ở **Metaspace**, JVM có thể tốn thêm bộ nhớ, tích lũy nhiều thế hệ class cùng tên và về lâu dài phát sinh áp lực GC hoặc `OutOfMemoryError: Metaspace`. Tuy nhiên, **thấy loader tồn tại chưa đủ để kết luận leak**: loader có thể còn đang phục vụ tác vụ hợp lệ, GC chưa đủ điều kiện chạy, hoặc số liệu đang phản ánh cached metadata theo vòng đời dự kiến.

Cách điều tra có hệ thống là kết hợp:

1. **JDK Flight Recorder (JFR)** để quan sát hiện tượng theo **thời gian**: class loading/unloading, class loader statistics, allocation/old-object samples và GC.
2. **`jcmd`/thống kê class loader** để xem snapshot tình trạng loader, số class và xu hướng.
3. **Heap dump HPROF** để thấy đồ thị đối tượng tại **một thời điểm**.
4. **Path to GC Roots / Dominator Tree** trong Eclipse Memory Analyzer (MAT) để xác định **tham chiếu mạnh nào đang giữ loader hay object thuộc plugin**.
5. **Sửa nguyên nhân và đo lại theo cùng kịch bản**, không chỉ tăng `-XX:MaxMetaspaceSize` hoặc ép `System.gc()`.

Bài tập trung vào Java 17+ và HotSpot khi giới thiệu lệnh diagnostic. Tên command, event JFR, quyền attach hoặc kết quả GC có thể khác giữa nhà cung cấp JVM/OS; cần xác minh bằng `jcmd <PID> help` và cấu hình thực tế. Các log, PID, địa chỉ object và trạng thái GC là dữ liệu động, **không nên công bố stdout cố định nếu runtime không bảo đảm**.

## 1. Những thứ phải phân biệt trước khi tìm leak

| Khái niệm | Ý nghĩa | Kết luận không được suy vội |
| --- | --- | --- |
| **Class loader còn reachable** | Có đường tham chiếu đang giữ object loader. | Không tự chứng minh một leak; có thể là loader còn được sử dụng. |
| **Class còn loaded** | JVM còn định nghĩa Class/type metadata có thể sử dụng. | Không có nghĩa loader đã leak vĩnh viễn. |
| **Class unloading** | JVM thu hồi metadata của class/loader khi điều kiện reachability và GC thích hợp. | Không bắt buộc diễn ra ngay sau `close()` hoặc `System.gc()`. |
| **Heap used** | Bộ nhớ Java heap của instances, maps, arrays, Class objects và object khác. | Không đồng nhất với toàn bộ Metaspace/native memory. |
| **Metaspace** | Vùng native memory JVM quản lý nhiều loại class metadata (HotSpot). | Tăng Metaspace không tự chứng minh một plugin loader bị giữ. |
| **Shallow heap** | Kích thước bản thân một object trong heap. | Không nói hết bộ nhớ nó gián tiếp giữ. |
| **Retained heap** | Lượng heap có thể giải phóng nếu bỏ đi một object/dominator theo đồ thị. | Không đồng nghĩa toàn bộ native memory/Metaspace do loader chiếm. |

**Bất biến cần nhớ:** class được định danh bằng **binary name và defining class loader**. Hai phiên bản `com.acme.plugin.Worker` cùng tên nhưng loader khác nhau là hai type JVM khác nhau. Khi mỗi lần redeploy tạo một loader mới, số class/data của deployment cũ có thể tiếp tục tồn tại nếu loader cũ còn reachable.

### Khi nào một loader có thể được thu hồi?

Để loader và những class được nó định nghĩa trở nên đủ điều kiện thu gom/unloading, không thể còn những **tham chiếu mạnh giữ chúng sống** theo GC/runtime: object instance của class plugin, `Class<?>`, phản chiếu/method handles, loader object, thread đang chạy code của class đó, JNI global references hoặc những thành phần khác có thể tiếp tục giữ class/loader. Sau khi đủ điều kiện, JVM vẫn quyết định **khi nào** và **có** thực hiện GC/class unloading theo collector/cấu hình hiện hành hay không.

**`URLClassLoader.close()` chỉ đóng tài nguyên loader**, chẳng hạn JAR handles được quản lý theo API, **không tự xóa Class objects và không cưỡng bức class unloading**. Tương tự, bỏ một biến cục bộ hoặc gọi `System.gc()` không tạo hợp đồng rằng loader phải biến mất ngay.

## 2. Đường tham chiếu (retention path) là trọng tâm chẩn đoán

Một class loader bị giữ khi có **đường tham chiếu giữ sống** từ một **GC root** (hoặc điều kiện root của JVM) tới loader, hoặc tới một object/class mà sự sống của nó kéo theo loader.

Ví dụ:

~~~text
GC Root: class host tồn tại suốt JVM
    |
    v
HostRegistry.CACHE (static Map)
    |
    v
HashMap entry -> plugin instance
    |
    v
demo.plugin.Payload instance
    |
    v
Class metadata của demo.plugin.Payload
    |
    v
defining URLClassLoader
    |
    v
metadata/các class thuộc deployment cũ
~~~

Trong heap analysis, đường từ **instance → class → class loader** có thể được MAT thể hiện bằng quan hệ class/loader do công cụ mô hình hóa; đó không nhất thiết là một field Java thông thường bạn có thể gọi bằng reflection.

Các root hoặc holder thường gặp:

| Holder/đường giữ | Ví dụ sai về lifecycle | Hướng xử lý |
| --- | --- | --- |
| **Static cache của host** | Map/singleton ở loader sống lâu giữ plugin object, `Class<?>`, method handle. | Xóa entry khi undeploy; tránh global strong cache không có policy. |
| **Thread.contextClassLoader** | Worker pool của host còn TCCL trỏ `OldPluginLoader`. | Ghi nhớ và restore TCCL bằng `finally`; dừng các worker riêng. |
| **ThreadLocalMap** | Long-lived thread giữ `ThreadLocal` value thuộc plugin. | `remove()` trong đúng thread; scope hóa context; cleanup executors. |
| **Scheduler/executor queue** | `Runnable`/`Callable`/`CompletableFuture` callback capture instance plugin. | Ngừng nhận việc, cancel/drain queue, shutdown đúng lifecycle. |
| **Listeners/registries** | Event bus, JDBC driver manager, JMX MBean, logging manager giữ handler của plugin. | Unregister/deregister vào lifecycle hook. |
| **ServiceLoader cache** | Host lưu `ServiceLoader` hoặc provider instances qua nhiều deployment. | Bỏ reference tới loader/provider cũ; tạo loader theo deployment. |
| **Reflection/caches** | Cache `Class<?>`, `Constructor<?>`, `Method`, `MethodHandle` hoặc proxy metadata. | Scope cache theo deployment, sử dụng weak keys đúng thiết kế khi phù hợp. |
| **JNI/global/native hooks** | Native component giữ global reference tới plugin object. | Release JNI refs/native registrations theo API. |

**ThreadLocal key yếu nhưng value mạnh:** `ThreadLocalMap` dùng weak reference cho key, song value có thể được giữ mạnh bởi entry của worker còn sống, kể cả khi key mất tham chiếu. Không kết luận “ThreadLocal yếu nên tự an toàn”.

**Class loader không phải rò rỉ chỉ vì có một path:** GC root path mô tả **vì sao còn sống**. Phải đối chiếu liệu path có còn **cần thiết về nghiệp vụ** sau khi plugin/deployment kết thúc. Một loader đang xử lý request có thể tồn tại hợp lệ, trong khi loader phiên bản cũ qua mười lần redeploy và không còn công việc là tín hiệu nghi ngờ rõ hơn.

## 3. JFR: quan sát thay đổi theo thời gian

**JDK Flight Recorder (JFR)** ghi nhận các event của JVM và ứng dụng theo thời gian, thay vì chỉ chụp một heap snapshot. Với class loader leak, JFR hữu ích để trả lời:

- Bao nhiêu class/loader được tạo khi load hoặc redeploy plugin?
- Sau khi undeploy và GC, có dấu hiệu **class unload** hay không?
- Loader statistics và Metaspace/GC thay đổi thế nào?
- Có object sống lâu được sampling bắt gặp không?
- Những allocation stack nào tương quan với thời điểm bùng nổ instances?

### 3.1. Ghi recording ngắn với jcmd

Giả sử một JVM HotSpot Java 17 đang chạy với PID đã xác định:

~~~bash
jcmd <PID> JFR.start name=loaderdiag settings=profile
~~~

Đây là **lệnh shell có placeholder `<PID>`**: thay bằng số PID thực tế, không gõ dấu `<`/`>` như ký tự literal trong shell. Để xem recording nào đang chạy:

~~~bash
jcmd <PID> JFR.check
~~~

Khi đã thực hiện load/undeploy hoặc tái hiện nghi ngờ, ghi ra file:

~~~bash
jcmd <PID> JFR.dump name=loaderdiag filename=loaderdiag.jfr
~~~

Nếu cần điều tra suspected memory leak và có ngân sách pause cho phép, bản `jcmd` Java 17 cung cấp tùy chọn (lưu ý **tên option theo command**):

~~~bash
jcmd <PID> JFR.dump name=loaderdiag filename=loader-roots.jfr path-to-gc-root=true
~~~

**Chú ý chính tả:** Tùy chọn của `JFR.dump` trên tài liệu JDK 17 là `path-to-gc-root` (số ít). Trong các cách khởi động recording như `-XX:StartFlightRecording`/cấu hình JFR lại có thể thấy `path-to-gc-roots` (số nhiều). Luôn chạy `jcmd <PID> help JFR.dump` trên đúng JVM để biết option hỗ trợ; không đoán theo một bài hướng dẫn khác phiên bản.

Thu thập đường tới GC roots có thể gây **pause/overhead đáng kể**, vì vậy chỉ bật khi đã nghi leak và đã cân nhắc tác động production. Một bản JFR thông thường có thể **không chứa đủ retention paths**; không coi `JFR.dump` mặc định là thay thế toàn diện cho HPROF.

Sau đó:

~~~bash
jfr summary loaderdiag.jfr
jfr print --events jdk.ClassLoaderStatistics,jdk.ClassLoad,jdk.ClassUnload loaderdiag.jfr
~~~

`jfr summary` liệt kê loại event thực sự có trong file. `jfr print --events ...` lọc event đã được ghi, **không khiến những event bị tắt từ trước xuất hiện trở lại**.

### 3.2. Bẫy quan trọng: profile không nhất thiết bật ClassLoad/ClassUnload

Trong cấu hình JFR của nhiều OpenJDK/HotSpot phiên bản 17, `settings=profile` bật thống kê như `jdk.ClassLoaderStatistics` nhưng có thể **không bật riêng** các event nhiều chi tiết `jdk.ClassLoad` và `jdk.ClassUnload`. Vì vậy:

**Không thấy `jdk.ClassUnload` trong file JFR có ít nhất hai khả năng rất khác nhau:** không có event được ghi **hoặc** loại event đó đang tắt. Không thể dựa riêng vào một recording chưa kiểm tra cấu hình để tuyên bố JVM không unload class.

Cần làm đúng:

1. Dùng `jfr summary` kiểm tra loại event/số event và metadata settings.
2. Kiểm tra tệp cấu hình `$JAVA_HOME/lib/jfr/default.jfc` hoặc `profile.jfc` của **đúng JDK** đang chạy.
3. Nếu cần theo dõi từng lần load/unload, tạo **custom `.jfc`** bật các event `jdk.ClassLoad`/`jdk.ClassUnload`, hoặc cấu hình event-setting được JVM hỗ trợ.
4. Thu recording **trước khi tái hiện**. Nếu JFR được start sau khi class đã load, sẽ không có sự kiện loading đã xảy ra trước đó chỉ bằng cách đợi.
5. Có thể bổ sung HotSpot unified logging khi cần sự kiện riêng:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp . LoaderRetentionDemo
~~~

Logging nạp lớp tạo nhiều dòng phụ thuộc JDK, classpath và thời điểm; **không có stdout cố định** cho lệnh này. Hãy xem việc unload của **loader/class cụ thể**, không chỉ tổng số dòng log.

### 3.3. OldObjectSample và path to GC roots

JFR có event như `jdk.OldObjectSample` để cung cấp dấu hiệu về **object sống lâu** (dựa trên sampling và cấu hình). Khi recording được setup thích hợp, JDK Mission Control (JMC) có thể cho bạn xem allocation stack và đôi khi đường giữ tới GC roots.

- Sampling **không liệt kê tất cả object** hoặc đảm bảo bắt được đúng plugin loader đang leak.
- Nếu event không có sample phù hợp, điều đó **không chứng minh không có leak**.
- `path-to-gc-root=true` trong JFR dump cần được bật rõ khi muốn capture roots (theo khả năng JVM); việc thu thập này có chi phí.
- Truy vết đường tham chiếu **đầy đủ cho một object cụ thể** thường thuận tiện hơn với HPROF và MAT, trong khi JFR mạnh ở **dòng thời gian và correlation**.
- Khi phân tích JFR, so snapshot/event giữa các vòng `deploy → use → undeploy → GC`, thay vì chỉ nhìn một thời điểm.

### 3.4. JFR, GC logs và classloader stats bổ trợ nhau

| Công cụ | Quan sát tốt | Giới hạn |
| --- | --- | --- |
| **JFR** | Timeline: allocation/GC/class loader stats và các events được bật. | Có sampling; event có thể tắt, không phải full object graph. |
| **`-Xlog:class+unload=info`** | Thông báo class unload trên HotSpot khi nó xảy ra. | Chỉ nói có unload, không chỉ ra trực tiếp mọi reference path. |
| **`jcmd VM.classloader_stats`** | Loader/class/metaspace snapshot. | Không tự xác định GC root giữ loader. |
| **`GC.heap_dump` + MAT** | Đồ thị object và đường tới GC roots tại một thời điểm. | Có chi phí pause/disk; dump không chứa lịch sử allocation đầy đủ. |
| **JMC** | Giao diện phân tích JFR, event correlation, leak suspects/old samples tùy cấu hình. | Chỉ phân tích evidence đã được ghi. |

## 4. Heap dump: chụp đồ thị object ở một thời điểm

Heap dump HPROF thường cho phép thấy **các object trên Java heap, fields, class/loader references và GC roots** tại lúc dump, tùy JVM và công cụ xuất. Dùng HotSpot Java 17:

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump loader-before.hprof
~~~

**Ý nghĩa:**

- `VM.classloader_stats`: in thống kê class loader và class metadata. Dùng để xác định số loader cùng loại tăng qua các vòng redeploy; tên loader hoặc con số không phải bằng chứng leak độc lập.
- `GC.class_histogram`: số instance/size theo class trong heap; giúp nhìn nhóm object đáng ngờ. Nó không trực tiếp trả lời “ai giữ loader”.
- `GC.heap_dump`: tạo file HPROF để phân tích bằng MAT. Theo JDK 17 HotSpot, lệnh này có **tác động cao** và thường yêu cầu **full GC** trừ khi bật `-all`.

**Không nên dùng `-all` khi đang cố chứng minh object sống sau GC**: tùy chọn này có thể đưa cả object **unreachable** vào snapshot và có thể không thực hiện full GC trước. Vì vậy, việc object xuất hiện trong HPROF `-all` **không tự chứng minh nó được giữ mạnh**.

Nếu có hai giai đoạn:

~~~text
before: sau khi plugin tạo/còn được host cache giữ
after:  sau khi undeploy, xóa cache, dừng tasks và có cơ hội GC
~~~

có thể thu:

~~~bash
jcmd <PID> GC.heap_dump loader-before.hprof
jcmd <PID> VM.classloader_stats
~~~

Sau cleanup, thu ở thời điểm khác:

~~~bash
jcmd <PID> GC.heap_dump loader-after.hprof
jcmd <PID> VM.classloader_stats
~~~

**Không có số đếm loader/class cố định** giữa hai file. Một loader có thể chưa bị thu gom dù không còn strong references bởi thời điểm GC, chính sách class unloading, active stack hoặc reference ngoài kịch bản. Kết luận phải căn cứ đường giữ và điều kiện lifecycle đã thực sự kết thúc.

### Cảnh báo vận hành và quyền riêng tư

- Heap dump có thể **rất lớn**, tạo pause đáng kể và làm tăng áp lực disk/memory lúc capture.
- Dump có thể chứa **passwords, tokens, customer data, sessions, secret keys, request payloads** còn ở heap. Coi HPROF như dữ liệu nhạy cảm: phân quyền file, encryption, retention hạn chế, xóa an toàn theo policy, không gửi lên hệ thống công cộng.
- `jcmd` thường cần quyền attach phù hợp tới JVM đích và công cụ JDK/OS tương thích; container và security policy có thể chặn attach.
- Không tạo heap dump hàng loạt trên production khi chưa có kế hoạch disk capacity và tác động latency.

## 5. MAT: lần theo Path to GC Roots đúng cách

**Eclipse Memory Analyzer (MAT)** là công cụ phổ biến để mở `.hprof` và tìm những đối tượng giữ lại bộ nhớ. Cách điều tra:

1. Mở `loader-before.hprof` trong MAT.
2. Vào **Histogram** hoặc **Class Loader Explorer** để tìm `java.net.URLClassLoader`, custom loader `PluginClassLoader` hoặc class plugin như `demo.plugin.Payload`.
3. Lọc instance của class plugin hoặc loader suspect, xem trường và retained/shallow sizes.
4. Trên loader hoặc instance, chọn **Path To GC Roots**, ưu tiên tùy chọn **exclude weak/soft/phantom references** khi muốn tìm **strong retention path**.
5. Đọc **chuỗi sở hữu** ngược tới GC root. Ví dụ `system-loaded HostRegistry.static CACHE → HashMap entry → plugin instance → class/loader`.
6. Dùng **Dominator Tree** để xem object nào là accumulation point. Dominator không nhất thiết là object ở đầu một đường GC-root ngắn nhất; cần diễn giải retained heap đúng định nghĩa.
7. So với file `loader-after.hprof` và trạng thái thực tế sau cleanup để xem holder còn tồn tại hay đã được loại bỏ.
8. Gắn phát hiện với code đăng ký/khởi tạo và **hook cleanup** chứ không chỉ báo “URLClassLoader còn sống”.

### Path to GC Roots không phải “đường gọi hàm”

`Path to GC Roots` là **đồ thị tham chiếu tới object**, không phải stack trace cho biết loader được tạo ở file/dòng nào. Heap dump **không tự cung cấp lịch sử allocation hoàn chỉnh**. Muốn biết “ai tạo object” cần JFR allocation stack/profiler hoặc logging/instrumentation từ lúc tạo.

Một đường tham chiếu rút gọn trong MAT có thể trông như:

~~~text
GC Root: class của LoaderRetentionDemo (system loader)
    |
    v
static HOST_CACHE
    |
    v
java.util.HashMap
    |
    v
HashMap$Node.value
    |
    v
demo.plugin.Payload instance
    |
    v
class demo.plugin.Payload
    |
    v
java.net.URLClassLoader
~~~

**Đây là sơ đồ giải thích**; giao diện MAT có thể sắp xếp các node hoặc biểu diễn Class/loader edges khác tùy phiên bản. Điểm quan trọng là **host static cache giữ plugin instance**, và plugin instance khiến defining loader chưa thể được thu gom.

### Những câu hỏi phải trả lời sau mỗi root path

- **Root thuộc về ai?** system class/static field, live thread, native/JNI reference hay object framework?
- **Quan hệ strong hay weak/soft?** Một weak reference không phải bằng chứng nó giữ referent sống mãi.
- **Path có hợp lý theo lifecycle?** Nếu plugin còn active, cache tồn tại có thể là đúng. Nếu plugin đã undeploy, cần giải thích vì sao holder không được dọn.
- **Có nhiều path khác không?** Xóa một cache nhưng còn TCCL/thread pool hoặc listener sẽ không giải phóng loader.
- **Có class/instance/reference từ phiên bản cũ nào không?** Chỉ so tên binary name không đủ; so **defining loader identity** và deployment marker.
- **Có JNI/global reference hoặc active frame không?** Những path ngoài Java field thông thường cũng có thể giữ classloader.

## 6. Ví dụ Java 17 tự chạy: host static cache giữ plugin class loader

Chương trình sau tạo `demo.plugin.Payload` bằng `JavaCompiler` của JDK, nạp class bằng **URLClassLoader mới**, tạo một plugin instance rồi đặt instance vào một **static Map của host class**. Nó cố ý giữ loader thông qua instance để bạn quan sát bằng JFR và MAT.

Để không phải dùng `System.gc()` làm điều kiện kiểm thử, stdout chỉ kiểm tra **những điều Java bảo đảm**: loader đã định nghĩa class, cache có một entry, weak reference vẫn có referent **khi cache còn giữ mạnh**, và cache trống sau `clear()`. Chương trình **không tuyên bố loader đã unload ngay sau clear**, vì quyết định thực tế thuộc GC/JVM.

### Tệp duy nhất: LoaderRetentionDemo.java

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LoaderRetentionDemo {
    private static final Map<String, Object> HOST_CACHE = new HashMap<>();

    private static Path compilePlugin() throws Exception {
        Path root = Files.createTempDirectory("loader-retention-");
        Path src = root.resolve("src/demo/plugin/Payload.java");
        Path classes = root.resolve("classes");

        Files.createDirectories(src.getParent());
        Files.createDirectories(classes);
        Files.writeString(src,
                "package demo.plugin; " +
                "public final class Payload { " +
                "public String id() { return \"plugin\"; } }");

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK");
        }

        int status = compiler.run(null, null, null,
                "--release", "17",
                "-d", classes.toString(), src.toString());

        if (status != 0) {
            throw new IllegalStateException("Plugin compilation failed");
        }
        return classes;
    }

    private static WeakReference<ClassLoader> install(Path classes)
            throws Exception {
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { classes.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> type =
                    pluginLoader.loadClass("demo.plugin.Payload");
            Object instance =
                    type.getDeclaredConstructor().newInstance();

            HOST_CACHE.put("plugin", instance);

            System.out.println("Plugin class: " + type.getName());
            System.out.println("Defined by child: "
                    + (type.getClassLoader() == pluginLoader));

            return new WeakReference<>(pluginLoader);
        }
    }

    public static void main(String[] args) throws Exception {
        Path classes = compilePlugin();
        BufferedReader console = new BufferedReader(
                new InputStreamReader(System.in));

        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Press ENTER to load plugin");
        console.readLine();

        WeakReference<ClassLoader> weak = install(classes);

        System.out.println("Cache entries before cleanup: "
                + HOST_CACHE.size());
        System.out.println("Loader reachable while cached: "
                + (weak.get() != null));

        System.out.println("Press ENTER to clear cache");
        console.readLine();

        HOST_CACHE.clear();
        System.out.println("Cache entries after cleanup: "
                + HOST_CACHE.size());

        System.out.println("Press ENTER to exit");
        console.readLine();
    }
}
~~~

**Biên dịch và chạy trên Java 17 trở lên:**

~~~bash
javac --release 17 LoaderRetentionDemo.java
java LoaderRetentionDemo
~~~

Sau mỗi prompt, nhấn **ENTER** một lần. `ProcessHandle.current().pid()` in PID thực của process, nên dòng đầu **thay đổi theo mỗi lần chạy**. Các dòng chức năng ổn định là:

~~~text
PID: <số PID thực tế>
Press ENTER to load plugin
Plugin class: demo.plugin.Payload
Defined by child: true
Cache entries before cleanup: 1
Loader reachable while cached: true
Press ENTER to clear cache
Cache entries after cleanup: 0
Press ENTER to exit
~~~

Đây là **output mẫu có đúng một dòng PID động**; không thể in cùng một con số PID ở mọi máy. Chương trình được kiểm tra bằng `javac --release 17` và chạy trên OpenJDK; `false` không xuất hiện ở dòng `Loader reachable while cached` vì map đang giữ **strong reference** tới instance plugin.

### Vì sao đây là ví dụ retention chứ không đơn thuần giữ biến local?

- `install(...)` tạo loader, nạp class, tạo instance, chèn instance vào **static `HOST_CACHE`** và trả về **`WeakReference`**. Khi method trả về, biến local `pluginLoader` và `type` không còn nằm trong stack frame ấy.
- Method `install` dùng `try-with-resources` nên đã gọi `URLClassLoader.close()`. Nhưng `close()` **không** giải phóng một defining loader còn được tham chiếu bởi những class/object sống.
- `HOST_CACHE` nằm trên **host/application class loader** và sống lâu hơn plugin. Object `Payload` được map giữ mạnh, từ đó giữ class/loader tương ứng.
- `WeakReference<ClassLoader>` được giữ trên stack của `main` chỉ dùng làm **quan sát viên yếu**. Nó **không tự giữ loader sống**. Giá trị `weak.get() != null` khi cache còn giữ object là `true` theo thiết kế.
- Sau `HOST_CACHE.clear()`, đường giữ từ static map bị loại. **Chưa có khẳng định loader sẽ lập tức biến mất**: còn phụ thuộc GC và những references khác.
- Tạm dừng bằng `BufferedReader.readLine()` giúp bạn đủ thời gian chụp JFR/heap dump ở cả hai giai đoạn. Trên PowerShell và Bash, dùng terminal tương tác để nhấn ENTER; không cần background process để nhập nhiều bước.

### Trình tự chạy và thu chứng cứ

**Terminal A — chạy demo.** Chương trình in PID và dừng ở `Press ENTER to load plugin`.

**Terminal B — bắt đầu recording trước khi load plugin:**

~~~bash
jcmd <PID> JFR.start name=loaderdiag settings=profile
~~~

Quay lại Terminal A, nhấn ENTER **lần thứ nhất**. Lúc này plugin class được load và `HOST_CACHE` có một entry. Không nhấn ENTER lần thứ hai ngay; giữ chương trình đứng ở `Press ENTER to clear cache`.

**Terminal B — snapshot trước cleanup:**

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.heap_dump loader-before.hprof
jcmd <PID> JFR.dump name=loaderdiag filename=loader-before.jfr
~~~

Trong MAT, mở `loader-before.hprof`, tìm `demo.plugin.Payload` hoặc loader `java.net.URLClassLoader` của nó. Lần theo Path To GC Roots sẽ có một đường thể hiện static `HOST_CACHE` của `LoaderRetentionDemo` giữ một `Payload` instance. Nếu công cụ mô hình hóa loader/class edges khác đi, vẫn phải tìm được **host cache là holder mạnh**.

**Terminal A — nhấn ENTER lần thứ hai** để xóa map, rồi giữ chương trình ở `Press ENTER to exit`.

**Terminal B — snapshot sau cleanup:**

~~~bash
jcmd <PID> GC.heap_dump loader-after.hprof
jcmd <PID> VM.classloader_stats
jcmd <PID> JFR.dump name=loaderdiag filename=loader-after.jfr
~~~

So sánh HPROF, class loader statistics và JFR theo vòng đời thực tế. Nếu loader đã đủ điều kiện cho class unloading, một lần GC thích hợp có thể thu gom; nếu chưa thấy unload ngay, không dùng kết quả duy nhất đó để kết luận fix thất bại. Kiểm tra lại các roots khác, GC policy và có active stack/plugin tasks không.

Cuối cùng nhấn ENTER lần thứ ba để demo thoát. Thư mục tạm chứa ClassFile sinh động có thể được dọn riêng; chương trình không tự xóa file nguồn/class tạo trong temp folder.

## 7. Hướng dẫn thực hành MAT với chính ví dụ trên

Khi mở `loader-before.hprof`:

1. **Histogram →** tìm `demo.plugin.Payload` và instance của nó.
2. Chọn instance đó, xem **Path To GC Roots** và đặt **exclude weak/soft/phantom references** (theo tùy chọn của MAT).
3. Xác nhận chain đại ý `LoaderRetentionDemo.HOST_CACHE → HashMap entry → Payload instance`. Trong MAT có thể có node bổ sung cho class/static field.
4. Chọn defining loader của `Payload` để xem các class được nó định nghĩa và instance counts. Chỉ có một `Payload` vì demo đơn giản, còn JVM có thể có nhiều loader khác.
5. Xem **Dominator Tree** để hiểu `HOST_CACHE`/holder nào chi phối object graph; lưu ý retained heap không nhất thiết đại diện toàn bộ Metaspace.
6. Mở `loader-after.hprof`. Tìm lại `Payload` và loader; nếu đã bị GC thu gom, chúng có thể không còn trong live snapshot. Nếu vẫn tồn tại, yêu cầu **Path To GC Roots mới** thay vì giả định map cũ vẫn giữ.
7. Đối chiếu kết quả với source: đường tham chiếu trực tiếp của `HOST_CACHE` bị xóa sau `clear()`. Bản dump trước cleanup chứng minh đường giữ ban đầu; bản sau giúp xem còn holder nào khác hoặc retention ngoài dự kiến.

### Nếu thấy loader còn trong heap sau clear?

Các giải thích khác nhau:

- **Không còn strong path** nhưng ảnh chụp gồm unreachable objects do tùy chọn dump hoặc cơ chế GC; kiểm tra cách capture.
- **JVM chưa unload** do GC timing/class unloading policy; không ép một deadline tự tạo.
- **Vẫn còn reference mạnh** từ thread/TCCL, JNI, listener, class/instance, cache khác hoặc instrumentation.
- **Bản dump/loader đối tượng khác**: có nhiều loader cùng loại/tên, nên phải đối chiếu identity, owner/class instance và deployment id.

Bằng chứng quyết định là **root path** và lifecycle. Một thống kê “metaspace chưa giảm” đơn lẻ có thể do allocator vẫn giữ committed memory hoặc do class khác vẫn loaded; không khẳng định leak chỉ dựa trên một biểu đồ.

## 8. JFR + heap dump: cách đọc theo timeline

Giả sử bạn chạy lại plugin 5 lần:

~~~text
T0: baseline sau startup, loader count ổn định
T1: deploy #1 → nạp 80 classes
T2: undeploy #1 → đóng tài nguyên, dừng tasks
T3: deploy #2 → tạo loader mới, nạp 80 classes
T4: undeploy #2 → ...
T5: sau vài lần GC phù hợp → đo live loaders/metaspace
~~~

Hai trường hợp:

**Tình huống kỳ vọng:** các loader cũ không còn strong path sau undeploy; class unloading có thể diễn ra sau GC, số live plugin loaders không tăng mãi cùng số vòng deploy.

**Tình huống nghi leak:** mỗi lần deploy tạo một loader mới; sau undeploy vẫn có loader cũ được giữ qua một cache/thread root, số live loaders/classes theo thế hệ tăng qua nhiều vòng và không có đường cleanup tương ứng.

Nhưng **JFR không tự cung cấp kết luận cuối**. Class loading metrics tăng có thể do lazy startup bình thường; class unload event có thể bị tắt. Vì thế:

- Dùng **JFR** để chỉ ra **khi nào** load/redeploy/GC xảy ra và thay đổi nào đáng ngờ.
- Dùng **`VM.classloader_stats`** để biết **những loader nào** vẫn được JVM nhìn thấy và số liệu về class.
- Dùng **heap dump/MAT** để tìm **ai giữ** loader cụ thể đó.
- Dùng code/lifecycle logs để quyết định holder còn hợp lệ hay là leak.
- Dùng **kịch bản lặp có điều kiện so sánh giống nhau** để đánh giá fix.

## 9. Những nhầm lẫn gây kết luận sai

### 9.1. `System.gc()` rồi WeakReference vẫn khác null → chắc chắn leak

Không đúng. `System.gc()` không đảm bảo GC/class unloading diễn ra theo deadline mong đợi; trong một số môi trường explicit GC có thể bị vô hiệu. Một weak ref còn referent chưa đủ kết luận leak; một weak ref `null` cũng không chứng minh toàn bộ tài nguyên/plugin đã cleanup đúng.

Trong ví dụ, thứ **chắc chắn** trước cleanup là `HOST_CACHE` đang giữ instance mạnh. Sau cleanup, kiểm chứng qua root path/live set trên dump và nhiều chu kỳ phù hợp, không in một dòng `unloaded=true` tùy hứng.

### 9.2. `URLClassLoader.close()` gọi thành công → loader unload

Sai. `close()` giải phóng những resource handles liên quan, **không xóa** Class/instance/method handles còn reachable. Mẫu demo đóng loader ở `install` nhưng static cache vẫn giữ class loader.

### 9.3. Heap dump chỉ có heap, nên không điều tra được class loader

Không đúng. HPROF và MAT có thể biểu diễn các object `ClassLoader`, `Class<?>`, static fields và các reference paths tương ứng; MAT còn mô hình hóa liên hệ class→loader. Tuy nhiên heap dump **không đo toàn bộ Metaspace/native memory như heap bytes**. Cần dùng JFR/stats/metaspace tools khi phân tích native side.

### 9.4. Retained heap của loader = toàn bộ Metaspace của loader

Sai. **Retained heap** là đại lượng trên object graph của Java heap; nhiều class metadata sống ở Metaspace native. Một loader instance có shallow size nhỏ vẫn có thể gắn với nhiều class metadata và references đáng kể.

### 9.5. `JFR.dump` không thấy ClassUnload = không có unload

Sai nếu event `jdk.ClassUnload` chưa bật, recording không bao phủ thời gian diễn ra unload hoặc JVM chưa thực hiện GC ở giai đoạn quan sát. Kiểm tra event configuration và timeframe trước khi suy luận.

### 9.6. Heap snapshot sau cleanup vẫn có Payload → cache chưa clear

Chưa chắc. Có thể object vẫn được giữ ở root khác, dump dùng `-all`, active frame còn tồn tại hoặc GC chưa thu gom. Đừng bỏ qua `Path To GC Roots`.

### 9.7. ThreadLocal có weak key nên tự hết leak

Sai. Worker thread sống lâu có thể giữ value mạnh dù key weak bị dọn sau này. Cleanup cần chạy đúng ngữ cảnh thread và gắn với vòng đời task/deployment.

### 9.8. Chỉ tăng Metaspace là fix

Không. Tăng `-XX:MaxMetaspaceSize` có thể làm lỗi xảy ra muộn hơn, nhưng không xóa root references. Nếu leak tăng theo mỗi redeploy, sau đủ vòng vẫn tích lũy.

## 10. Quy trình chẩn đoán production có kiểm soát

1. **Xác định triệu chứng có thể đo:** loader instances, class counts, Metaspace committed/used, rate redeploy, GC/unloading logs, hoặc OOME stack/cause.
2. **Xác nhận thời điểm và scope:** JVM nào, application/deployment nào, loader thuộc plugin nào, từ trước hay sau undeploy.
3. **Thu JFR recording** đủ sớm, chọn `default`/`profile` hay custom `.jfc` phù hợp; biết event nào đang bật.
4. **Dùng `VM.classloader_stats`** (và có thể `VM.metaspace` tùy HotSpot/JDK) để xem tổng quan theo loader.
5. **Chọn thời điểm heap dump an toàn:** có đủ disk, pause budget, privacy controls; cân nhắc ảnh hưởng full GC; ghi lại JVM build/flags.
6. **Trong MAT**, tìm loader/objects của deployment cũ, Path To GC Roots excluding weak refs và Dominator Tree.
7. **Xác định root holder**: static cache, TCCL, ThreadLocal, service registry, listener, JNI global, active frame, task queue.
8. **Sửa tại lifecycle boundary:** unregister, `ThreadLocal.remove()`, restore TCCL bằng `finally`, shutdown executor, cancel delayed tasks, xóa map/registries, đóng loader resources.
9. **Đo lại qua nhiều vòng deploy/undeploy**, so snapshot và JFR stats với baseline có cùng workload. Không đặt kỳ vọng “GC phải unload ngay sau gọi `clear`”.
10. **Báo cáo bằng bằng chứng:** đường GC-root trước fix, root path sau fix, classloader stats/timeline, điều kiện test, chi phí vận hành và giới hạn kết luận.

### Mẫu xử lý TCCL trong worker

Đây là **fragment** áp dụng khi task thực sự cần loader plugin (các biến `pluginLoader`/`task` đã được khai báo):

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

thread.setContextClassLoader(pluginLoader);
try {
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

TCCL là **trạng thái của thread đang chạy**, không được executor tự truyền theo từng `submit`. Pattern trên tránh để worker của host giữ TCCL plugin sau task; nhưng nếu task còn ghi ThreadLocal hoặc đăng ký listener thì vẫn phải cleanup riêng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `URLClassLoader.close()` thành công có đồng nghĩa loader được GC ngay không?

**Đáp án:** Không. Nó đóng resource handles của loader; loader/class/instances có thể vẫn reachable từ root.

**Câu 2.** Một host static map giữ một plugin instance. Vì sao loader plugin có thể vẫn sống?

**Đáp án:** Instance có defining class và loader liên quan; map giữ instance mạnh qua GC root của host, nên lớp/loader không đủ điều kiện unload.

**Câu 3.** `JFR.dump` không có event `jdk.ClassUnload` chứng minh không có unload không?

**Đáp án:** Không. Event có thể chưa bật hoặc recording không bao phủ đúng thời điểm; kiểm tra `.jfc` và `jfr summary`.

**Câu 4.** Heap dump khác JFR ở đâu?

**Đáp án:** Heap dump là snapshot object graph/GC roots tại một thời điểm; JFR là event timeline/sampling. Kết hợp hai nguồn để biết cả “khi nào” và “ai giữ”.

**Câu 5.** MAT `Path To GC Roots` trả lời câu hỏi gì?

**Đáp án:** Chuỗi object/reference/root **đang giữ object sống**, không phải mặc định là stack trace nơi object được tạo.

**Câu 6.** Vì sao nên exclude weak/soft/phantom references khi tìm leak qua strong path?

**Đáp án:** Những đường tham chiếu yếu/mềm/phantom không có cùng ý nghĩa giữ sống như strong references; bỏ chúng giúp tập trung vào holder mạnh cần cleanup.

**Câu 7.** Vì sao `Metaspace used` tăng chưa đủ kết luận classloader leak?

**Đáp án:** Có thể do normal class loading, JIT/JVM allocator, workload hoặc thời điểm GC; cần evidence từ loader generations và root paths còn tồn tại sau lifecycle kết thúc.

**Câu 8.** Xóa cache rồi vẫn có một worker với TCCL=OldPluginLoader. Fix hoàn chỉnh chưa?

**Đáp án:** Chưa. TCCL là một strong reference từ live thread; cần restore/cleanup tại task boundary hoặc chấm dứt worker phù hợp.

## Ghi nhớ

**Class loader leak là vấn đề reachability và lifecycle, không phải chỉ là số byte heap hay một lệnh `close()`.** JFR cho timeline load/unload/GC, `VM.classloader_stats` cho snapshot loader/class, heap dump cho đồ thị object, còn MAT **Path To GC Roots** chỉ ra holder mạnh khiến loader/instance còn sống. Không coi absence of JFR event, one-time Metaspace growth hoặc một lần `System.gc()` là chứng cứ quyết định. Tìm **đường giữ**, gắn nó với nghiệp vụ đã kết thúc, xóa đúng tham chiếu và đo lại qua nhiều vòng deploy/undeploy.

**Tài liệu chính thức và công cụ tham khảo:**

- Oracle Java SE 17, `jcmd` (JFR.start/JFR.dump/GC.heap_dump/VM.classloader_stats): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java SE 17, `jfr` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle Java SE 17, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Oracle Java SE 17, `URLClassLoader.close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- OpenJDK/Java learning, JFR configuration: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/
- Eclipse Memory Analyzer, *Basic Tutorial* — Dominator Tree và Path to GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse MAT, *Path to GC Roots* và exclude weak references: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html
