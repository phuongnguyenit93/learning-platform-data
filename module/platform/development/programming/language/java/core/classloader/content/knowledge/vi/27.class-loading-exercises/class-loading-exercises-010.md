# Điều tra một tình huống rò rỉ class loader trong Java

## 1. Tình huống thực tế: reload plugin nhiều lần, metaspace vẫn tăng

Giả sử một ứng dụng Java chạy lâu dài có cơ chế tải plugin từ JAR riêng bằng `URLClassLoader`. Mỗi khi triển khai phiên bản mới, host tạo loader mới, tải implementation mới, chuyển request sang phiên bản mới rồi đóng loader cũ.

Sau hàng trăm lượt reload, giám sát ghi nhận:

- Số class loader hoặc classes đã nạp tăng, nhưng số classes được unload ít.
- Metaspace có xu hướng tăng theo số lần reload và không trở về mức ổn định.
- Heap dump cho thấy nhiều `URLClassLoader` cũ vẫn reachable.
- Máy chạy lâu có thể gặp `OutOfMemoryError: Metaspace` hoặc độ trễ GC tăng; tuy nhiên không phải mọi lần tăng metaspace đều dẫn đến lỗi.
- File JAR cũ có thể vẫn bị giữ trên Windows nếu resource handles chưa được đóng — **đây là lỗi tài nguyên khác** với việc ClassLoader còn sống trong heap.

Câu hỏi của bài thực hành không phải “làm sao gọi `System.gc()` để ép unload?”, mà là:

> **Tham chiếu mạnh nào từ một GC root đang giữ loader của phiên plugin đã nghỉ, và ai phải xóa tham chiếu ấy trong vòng đời plugin?**

Trong ví dụ sẽ tự tạo hai đường giữ loader có thể quan sát chắc chắn:

1. Một registry `static` của host giữ `Class<?>` thuộc plugin loader.
2. Một worker thread sống lâu của host giữ loader qua **thread context class loader (TCCL)**.

Ta sẽ đóng URLClassLoader, chứng minh **close không tự cắt hai reference**, rồi dọn registry/TCCL, nhưng **không khẳng định rằng GC/class unloading đã diễn ra ngay lập tức**.

## 2. Một loader còn sống chỉ là leak khi đã hết vòng đời dự kiến

Mỗi plugin generation thường có defining loader riêng, và `Class<?>` cũng mang runtime identity của loader đó. Nếu một generation đã dừng nhưng `Class<?>`, plugin object hay TCCL còn được host giữ, JVM có thể không thu hồi loader và metadata tương ứng.

Ba sự kiện **không đồng nghĩa**:

| Sự kiện | Bảo đảm | Không bảo đảm |
| --- | --- | --- |
| `URLClassLoader.close()` | Bắt đầu giải phóng các URL/JAR resources do loader mở; không tìm nguồn riêng mới theo contract | Không xóa classes, stop threads hoặc ép GC |
| Host bỏ strong references | Cắt các đường giữ mà host kiểm soát | Có thể còn GC roots khác; không đảm bảo unload ngay |
| GC/class unloading | JVM thu hồi metadata khi điều kiện phù hợp | Không có deadline do `System.gc()` đặt |

**Metaspace tăng/committed chưa giảm sau một lần GC không đủ kết luận leak.** Bằng chứng mạnh hơn là một loader *đã retire*, không còn request hợp lệ, nhưng vẫn reachable từ GC roots qua host cache, worker TCCL hoặc listener. Bài lab tạo và dọn chính hai đường đầu, còn việc GC diễn ra lúc nào là vấn đề quan sát riêng.

## 3. GC roots và đường dẫn giữ loader

Để kết luận leak, cần tìm **đường tham chiếu mạnh từ GC root** tới loader hoặc tới class/object do loader định nghĩa.

Ví dụ 1 — Registry của host:

~~~text
GC Root
   |
   v
java.lang.Class<host.LeakLab>
   |
   v
static CACHE: Map<String, Class<?>>
   |
   v
Class<plugin.Greeter> (do loader L1 định nghĩa)
   |
   v
Defining ClassLoader L1
~~~

Đường trên minh họa retention qua class metadata. Trên heap dump, liên kết thực tế từ Class tới loader có thể được công cụ hiển thị khác nhau tùy JVM; hãy dựa vào **path to GC roots** và class-loader grouping, không giả định tên field nội bộ cố định.

Ví dụ 2 — Thread context loader:

~~~text
GC Root
   |
   v
Worker Thread trong pool sống lâu
   |
   v
Thread.contextClassLoader
   |
   v
URLClassLoader L1
   |
   v
Các class/resources của plugin đã định nghĩa
~~~

Nếu host đổi TCCL của thread thành plugin loader rồi **quên khôi phục**, thread pool có thể giữ loader đó suốt tuổi thọ ứng dụng.

Ví dụ 3 — Callback/listener:

~~~text
Host singleton EventBus
   |
   v
List<Listener>
   |
   v
plugin.ListenerImpl
   |
   v
Class<plugin.ListenerImpl>
   |
   v
Plugin ClassLoader
~~~

Ngay cả nếu không giữ trực tiếp `ClassLoader`, một plugin instance hoặc `Class<?>` cũng có thể giữ cho loader reachable. Đây là lý do câu hỏi điều tra phải tìm **toàn bộ reference chain**, không chỉ grep mã có biến `ClassLoader`.

## 4. Chuẩn bị bài thực hành Java 17+

Bài dùng đúng **hai file source**, không cần thư viện bên ngoài JDK:

- `plugin.Greeter`: class plugin có phương thức static để chứng minh code được nạp.
- `LeakLab`: host tạo child `URLClassLoader`, lưu `Class<?>` vào static registry, gán loader làm TCCL trên một worker thread trong pool, đóng loader, rồi cleanup.

Mã chạy trên Java 17+.

### Cấu trúc thư mục

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── plugin/
│   │       └── Greeter.java
│   └── host/
│       └── LeakLab.java
└── out/
    ├── plugin/                 (tạo sau compile)
    │   └── plugin/Greeter.class
    └── host/                   (tạo sau compile)
        └── LeakLab.class
~~~

**Điều kiện rất quan trọng:** application classpath khi chạy **chỉ chứa `out/host`**. Không đặt `out/plugin` lên classpath của host, nếu không parent loader có thể nạp `plugin.Greeter` trước và phá điều kiện thí nghiệm.

### File src/plugin/plugin/Greeter.java

~~~java
package plugin;

public final class Greeter {
    public static String greet() {
        return "hello-plugin";
    }
}
~~~

Class được khai báo public, có một public static method để host gọi bằng reflection; plugin không cần dùng trực tiếp bất kỳ API riêng của host.

### File src/host/LeakLab.java

~~~java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LeakLab {
    private static final Map<String, Class<?>> CACHE = new HashMap<>();

    private static WeakReference<ClassLoader> loadAndRetain(
            Path root, ExecutorService pool) throws Exception {
        URL source = root.toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{source}, LeakLab.class.getClassLoader())) {

            Class<?> type = loader.loadClass("plugin.Greeter");

            // Đường giữ loader #1: registry sống lâu của host.
            CACHE.put("old-plugin", type);

            // Đường giữ loader #2: thread trong pool giữ TCCL.
            pool.submit(() ->
                    Thread.currentThread()
                            .setContextClassLoader(loader)).get();

            System.out.println("plugin defined by child: "
                    + (type.getClassLoader() == loader));
            System.out.println("plugin says: "
                    + type.getMethod("greet").invoke(null));

            return new WeakReference<ClassLoader>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "plugin classes root needed");
        }

        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Thread worker =
                    pool.submit(Thread::currentThread).get();
            ClassLoader original =
                    worker.getContextClassLoader();

            WeakReference<ClassLoader> weak =
                    loadAndRetain(Path.of(args[0]), pool);

            System.out.println("registry holds Class: "
                    + CACHE.containsKey("old-plugin"));

            System.out.println("worker TCCL points to loader: "
                    + (worker.getContextClassLoader() == weak.get()));

            System.out.println("closed loader still reachable: "
                    + (weak.get() != null));

            // Retire plugin: xóa những reference đã xác định.
            CACHE.clear();

            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(original)).get();

            System.out.println("registry cleaned: "
                    + CACHE.isEmpty());
            System.out.println("worker TCCL restored: "
                    + (worker.getContextClassLoader() == original));

            // Không kiểm thử tính kịp thời hoặc bảo đảm của GC.
            System.out.println("class unloading guaranteed: false");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Tại sao ví dụ được thiết kế như vậy?

1. `URLClassLoader` nhận **loader của host làm parent** và URL của thư mục chứa plugin class. Host không có `plugin.Greeter`, nên child thực sự là **defining loader**.
2. `loadAndRetain` lưu `Class<?>` của plugin trong `CACHE`, một static Map của class thuộc application loader sống lâu.
3. Một task trong single-thread executor cố ý gán TCCL của worker thread thành child loader; task kết thúc nhưng **thread trong pool vẫn tồn tại**.
4. `try-with-resources` đóng URLClassLoader khi rời phương thức; nhưng cache và TCCL **vẫn** giữ loader.
5. `WeakReference<ClassLoader>` cho phép thí nghiệm hỏi tham chiếu lúc đang được giữ mà không tự thêm một **strong reference từ WeakReference**. Tuy nhiên, việc gọi `weak.get()` ở một thời điểm không tự chứng minh GC đã chạy; ta chỉ dựa vào các strong references nhìn thấy bằng code.
6. `CACHE.clear()` xóa một đường giữ; gán lại TCCL cũ trên **đúng worker thread** xóa đường thứ hai.
7. `pool.shutdown()` bắt đầu quá trình đóng thread pool trong khối finally. Trong ứng dụng thực, cần thêm timeout/awaitTermination theo lifecycle nếu tác vụ bất đồng bộ vẫn chạy.
8. Chương trình **không khẳng định** class unloading đã xảy ra ngay sau cleanup. Không có vòng lặp `System.gc()` chờ đến khi weak reference trở thành null.

### Compile và chạy trên Linux/macOS

Đứng trong thư mục `example`:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
    src/plugin/plugin/Greeter.java

javac --release 17 -d out/host \
    src/host/LeakLab.java

java -cp out/host LeakLab out/plugin
~~~

### Compile và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host |
    Out-Null

javac --release 17 -d out\plugin src\plugin\plugin\Greeter.java
javac --release 17 -d out\host src\host\LeakLab.java

java -cp out\host LeakLab out\plugin
~~~

Lưu ý `src/plugin/plugin/Greeter.java` có hai thư mục mang tên plugin do cách tổ chức source root và package; output binary name vẫn chỉ là `plugin.Greeter`.

### Stdout chính xác đã được kiểm chứng

~~~text
plugin defined by child: true
plugin says: hello-plugin
registry holds Class: true
worker TCCL points to loader: true
closed loader still reachable: true
registry cleaned: true
worker TCCL restored: true
class unloading guaranteed: false
~~~

Mã nguồn đầy đủ đã được biên dịch bằng `javac --release 17`, thực thi trên JDK và so khớp chính xác tám dòng stdout.

**Diễn giải:**

- **plugin defined by child: true**: điều kiện experiment đúng, class do URLClassLoader riêng định nghĩa.
- **plugin says: hello-plugin**: class plugin hoạt động và được gọi qua reflection.
- **registry holds Class: true**: static registry của host đang giữ Class của plugin.
- **worker TCCL points to loader: true**: một thread sống lâu vẫn giữ trực tiếp plugin loader.
- **closed loader still reachable: true**: dù `try-with-resources` đã gọi `close()`, tham chiếu tới loader vẫn còn.
- **registry cleaned: true**: host đã loại bỏ Class khỏi registry.
- **worker TCCL restored: true**: TCCL trên đúng worker thread đã được khôi phục về giá trị cũ.
- **class unloading guaranteed: false**: sau cleanup, chương trình không khẳng định JVM đã GC/unload class.

Thí nghiệm này chỉ chứng minh **nguồn retention và hành động cắt hai đường retention chủ động**. Không nên dùng nó như benchmark metaspace, kiểm thử memory leak tự động hoặc cam kết class unloading thời gian thực.

## 5. Vì sao close() rồi vẫn còn rò rỉ?

`URLClassLoader.close()` có phạm vi rõ: nó chấm dứt khả năng nạp class/resource mới **do loader tự định nghĩa**, cố gắng đóng file handles mà nó mở, và không hủy classes/objects đã nạp. Parent loader vẫn có thể cung cấp classes của parent theo cơ chế delegation.

Các lời gọi sau **không đồng nghĩa**:

~~~java
loader.close();       // Đóng tài nguyên của URLClassLoader.
loader = null;        // Bỏ một biến strong reference cụ thể.
System.gc();          // Gợi ý GC, không có timing bảo đảm.
~~~

Đây là đoạn **minh họa**: biến `loader` phải không phải `final` và có thể ném `IOException`. Kể cả sau khi biến cục bộ bằng null, các đường như `CACHE → Class<?> → loader` hoặc `Thread → contextClassLoader → loader` vẫn tồn tại.

Nếu bạn thấy lỗi không xóa được JAR trên Windows, có thể là leak handle chứ không phải heap/class metadata. `JarURLConnection` cache, một `JarFile`/`ZipFile` mở độc lập, custom loader/framework hoặc process khác cũng có thể giữ file. Phải điều tra **ai sở hữu handle**, không suy từ metaspace.

### Rò rỉ loader và rò rỉ heap objects có quan hệ gì?

Loader còn reachable có thể làm những class metadata tương ứng còn sống. Nhưng không phải mọi instance có type thuộc loader đều sẽ được giữ chỉ vì loader tồn tại; object thường vẫn được GC theo reachability riêng. Ngược lại, một **instance** còn được host giữ là đủ tạo một đường giữ runtime class/loader.

Không nên gán một chiều giản đơn “loader giữ tất cả object từng được tạo” hoặc “GC thu object thì loader chắc chắn được unload”. Đây là hai tập điều kiện reachability cần phân tích bằng GC roots.

## 6. Quy trình điều tra thực tế từng bước

Một cuộc điều tra production cần dữ kiện trước/sau và kết luận có thể kiểm chứng, không chỉ cảm giác “metaspace tăng”.

### Bước 1 — Xác định triệu chứng và baseline

Ghi lại ít nhất:

- JDK version/build, GC, JVM flags, max metaspace nếu có.
- Số lần plugin reload và số plugin versions **đáng lẽ** còn hoạt động.
- Số loader classes đang sống theo type/identity, không chỉ số instances `URLClassLoader` đã tạo từ đầu.
- Loaded/unloaded class counts (nếu có), metaspace used/committed, heap memory và GC activity.
- Các phiên plugin đã ngừng nhưng vẫn có references nào được biết trong host registry/task scheduler.

Ví dụ bảng quan sát:

| Thời điểm | Loader version đang phục vụ | Loader retired còn thấy | Dấu hiệu cần điều tra |
| --- | --- | --- | --- |
| Trước reload | v1 | 0 | Baseline |
| Sau chuyển sang v2 | v2 | v1 tạm thời | Có thể bình thường khi request v1 chưa xong |
| Sau khi v1 đã stop/retire | v2 | v1 vẫn reachable | Cần tìm GC root paths |
| Sau nhiều lượt reload | v10 | v1…v9 vẫn giữ | Mạnh hơn về bằng chứng retention bất thường |

Bảng chỉ là **kịch bản giả định**, không phải số đo hệ thống hiện có. Đừng coi việc loader v1 xuất hiện ngay sau cutover là leak nếu vẫn còn request hợp lệ đang chạy.

### Bước 2 — Khẳng định định danh class loader

Từ class plugin:

~~~java
Class<?> type = pluginInstance.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

Đây là code minh họa trong phương thức có `pluginInstance`. `getClassLoader()` thường quan trọng hơn tên class string. Hai class có binary name giống nhau nhưng defining loaders khác có thể là hai phiên khác nhau. Nếu loader thực tế là application loader (do plugin JAR nằm trên host classpath), khả năng retire từng phiên riêng sẽ không đúng như kiến trúc mong đợi.

### Bước 3 — Thu thập công cụ JVM thích hợp

Trên HotSpot JDK 21 có thể dùng `jcmd`. Trước tiên tìm PID hoặc gọi help để xác minh lệnh cụ thể của JVM:

~~~bash
jcmd -l
jcmd <pid> help
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace basic
~~~

Những dòng trên là **mẫu shell với `<pid>` phải thay bằng PID thật**, không phải chương trình chạy nguyên xi. `jcmd` thường phải chạy cùng máy và quyền user/group thích hợp với process đích.

Chức năng chính:

- `VM.classloader_stats`: thống kê loader/class metadata để xem quy mô các class loaders đang tồn tại.
- `VM.classloaders`: xem class loader hierarchy; một số options hỗ trợ hiển thị classes cụ thể.
- `VM.metaspace`: kiểm tra metaspace usage, có tùy chọn bổ sung tùy JVM.
- `GC.heap_dump`: tạo heap dump để phân tích refs; có thể ảnh hưởng đáng kể đến vận hành, dung lượng đĩa và pause.
- `GC.class_histogram`: thống kê đối tượng trên heap, nhưng không thay thế path-to-root analysis.

**Cảnh báo vận hành:** heap dump thường chứa dữ liệu ứng dụng nhạy cảm như token, thông tin người dùng hoặc payload. Lưu trong vị trí bảo vệ truy cập, không gửi dump lên nơi công khai và áp dụng retention/deletion policy thích hợp. Không chạy lệnh nặng trên production ở giờ tải cao mà không đánh giá impact.

### Bước 4 — Thu heap dump đúng cách

Sau khi xác định PID và vị trí ghi phù hợp:

~~~bash
jcmd <pid> GC.heap_dump /secure/path/after-reload.hprof
~~~

Đây là mẫu lệnh; hãy kiểm tra help theo JVM và đảm bảo đủ không gian đĩa/quyền ghi. Một heap dump có thể rất lớn, gây pause/impact, và cách JVM xử lý GC trước dump phụ thuộc options.

Nếu cần so sánh retention, có thể chụp trước và sau nhiều lượt reload với quy trình lặp được kiểm soát. Không so hai dump khác workload rồi kết luận leak chắc chắn chỉ từ số bytes tăng.

### Bước 5 — Phân tích “Path to GC Roots”

Mở dump trong Eclipse Memory Analyzer Tool (MAT) hoặc công cụ heap analysis tương thích. Tìm:

1. Instances `java.net.URLClassLoader` hoặc subclass custom của plugin loader.
2. Những loader có tên/identifier của **version đã retired**.
3. Classes được định nghĩa bởi loader đó, ví dụ `plugin.Greeter`.
4. **Paths to GC Roots**, ưu tiên strong references (có thể chọn *exclude weak/soft/phantom references* khi phân tích nguyên nhân mạnh).
5. Retained set/dominator tree để đánh giá object graph bị giữ.
6. Các nút là host static field, Thread.contextClassLoader, ThreadLocal, listener, logger, scheduler hoặc cache.

Với bài mẫu, hai nghi phạm là:

~~~text
GC Root -> Host class -> static CACHE
                      -> Class<plugin.Greeter>
                      -> URLClassLoader old

GC Root -> executor worker Thread
                      -> contextClassLoader
                      -> URLClassLoader old
~~~

Một snapshot có thể không cho thấy đường nối chính xác như sơ đồ giản lược trên do cách JVM/MAT biểu diễn Class mirror và native metadata; yếu tố quyết định là **đường giữ loader từ roots**, không phải tên field nội bộ cố định.

### Bước 6 — Tìm owner của reference

Không chỉ thấy root “Thread” rồi xóa tùy tiện:

- Thread này do **host** hay plugin tạo?
- Nếu host thread pool, task nào đã đổi TCCL? Có thể khôi phục bằng một hành động chạy trên chính worker không?
- Registry được host cache để lookup class/provider theo key gì? Có xóa entry theo version lúc retire không?
- Listener nào đã được đăng ký nhưng không unregister?
- ThreadLocal được gán trên thread nào và đã remove trong đúng thread chưa?
- Có app/framework static field giữ `Method`, `Constructor`, proxy, `Class<?>`, service instance hoặc lambda của plugin không?

Cần chỉ ra **đối tượng sở hữu**, hành vi tạo tham chiếu, thời điểm phải dọn và phép kiểm tra sau khi dọn.

### Bước 7 — Sửa và xác minh qua nhiều chu kỳ

Khi đã xác định root:

1. Thêm cleanup vào plugin lifecycle: `start → running → quiesce → stop → close → retire`.
2. Dừng nhận requests mới từ plugin cũ, đợi requests đang chạy xong.
3. Unregister callbacks, cancel tasks, shutdown executors, đóng streams/JarFile.
4. Xóa host registry/cache entries theo version, không phá bản mới.
5. Khôi phục TCCL trong `finally` cho các threads mà app đã thay đổi.
6. Đóng URLClassLoader (cần tránh concurrent class loading).
7. Bỏ strong references tới old `Class<?>`/plugin object/loader.
8. Chạy chuỗi reload lặp với tải đại diện, đối chiếu loader counts/metaspace và paths-to-roots.
9. Không đặt điều kiện pass là “GC phải unload ngay trong 100 ms”; nên kiểm tra **tính đúng của cleanup và xu hướng dữ liệu**.

Khi cần dùng phiên bản cũ song song để hoàn thành request, giữ loader cũ có chủ đích trong giai đoạn drain là đúng; chỉ label retired sau khi hợp đồng lifecycle kết thúc.

## 7. Dùng WeakReference đúng mục đích

`WeakReference<ClassLoader>` thường được dùng trong test để quan sát loader có thể được JVM thu gom sau khi các đường strong reference đã biến mất.

~~~java
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);
~~~

Đây là đoạn minh họa. **WeakReference không giữ strong reference tới referent**, nhưng nếu biến `pluginLoader`, `Class<?>` hay một thread vẫn giữ loader thì `weak.get() != null` là điều bình thường.

Cẩn trọng:

- `weak.get() != null` trước cleanup **không cần gọi GC** mới chứng minh rằng loader vẫn đang reachable, nếu còn mạnh references rõ ràng.
- `weak.get() == null` sau một lần GC có thể hỗ trợ quan sát rằng referent đã được thu gom, nhưng không phải phép đo tổng memory đã trở về baseline.
- `weak.get() != null` ngay sau cleanup **không chứng minh leak**. GC chưa chắc chạy, hoặc một strong reference tạm từ stack/debugger/test vẫn tồn tại.
- Không viết vòng lặp vô hạn `while (weak.get() != null) System.gc();`.
- Nếu cần integration test, đặt timeout rộng/có kiểm soát, loại bỏ strong refs trong một helper scope, và kết hợp heap analysis khi fail thay vì assertion tuyệt đối dựa trên timing GC.
- Dùng `ReferenceQueue` nếu muốn quan sát thông báo khi JVM xử lý tham chiếu yếu, nhưng cũng không nhận được lời hứa thời điểm xử lý cụ thể.

Ở chương trình mẫu, ta cố ý **không** gọi GC, để người học tập trung vào hai root paths do host tạo ra và việc cleanup xác định.

## 8. Những nguồn leak thường gặp hơn chỉ một static Map

| Điểm giữ tham chiếu | Một đường root hay gặp | Biện pháp cleanup |
| --- | --- | --- |
| Host static cache `Class<?>`/`Method`/`Constructor` | Static field → reflective metadata → class/loader | Clear cache theo plugin version; tránh global unbounded map. |
| Thread context class loader | Thread pool worker → TCCL → loader | Lưu và restore TCCL trong finally trên đúng thread. |
| ThreadLocal | Worker thread → ThreadLocalMap → plugin object | Remove/clear trong đúng thread, đừng chỉ null biến ở request khác. |
| Listener/event bus | Host singleton → listener implementation của plugin | Unregister bằng registration token trong stop hook. |
| Executor/scheduled task | Queue/task/runnable → plugin class/object | Cancel futures, shutdown executor, drain tasks. |
| Thread do plugin tự tạo | Live Thread → Runnable/context loader | Stop bằng protocol có kiểm soát và join/await termination. |
| JDBC driver registration | Global DriverManager registry → driver từ plugin | Deregister driver đúng owner khi retire, nếu phù hợp. |
| MBean/JMX | MBeanServer → MBean instance plugin | Unregister name lúc plugin stop. |
| Logger/appender/callback | Logger context/listener → plugin object | Gỡ plugin appender/handler/callback bằng API chính thức. |
| SPI provider caching | Long-lived ServiceLoader/list → provider Class hoặc instance | Bỏ registry/loader hoặc tạo ServiceLoader mới theo phiên. |
| Java shutdown hooks | Runtime hooks → Thread/lambda plugin | Remove hook khi còn được phép và lifecycle hợp lệ. |
| Heap/native resources | Resource stream hoặc JarFile/ZipFile | Đóng đúng owner; memory leak và file-handle leak cần phân tích riêng. |

Đặc biệt, **static field của plugin** thường bị hiểu lầm: một object graph chỉ nằm hoàn toàn bên trong plugin loader, không có root từ host hay external thread, có thể cùng trở thành unreachable và được thu gom. Ngược lại, chỉ một reference từ host static field vào plugin object/class cũng có thể giữ cả thế hệ loader.

## 9. Phân biệt tăng metaspace bình thường với leak thật

Đánh giá thận trọng:

| Quan sát | Kết luận hợp lý |
| --- | --- |
| Metaspace used tăng sau request đầu | Có thể là class loading bình thường. |
| Metaspace committed chưa giảm sau GC | Không tự chứng minh loader vẫn reachable; JVM quản lý vùng đã commit riêng. |
| URLClassLoader.close() đã gọi | Chứng minh cleanup resource đã được yêu cầu, **không** chứng minh class unloading. |
| Heap dump thấy nhiều retired loaders cùng strong GC root paths | Bằng chứng mạnh về retention bất thường nếu các phiên đã ngừng đúng nghĩa. |
| Số loader sống tăng gần tuyến tính qua nhiều lần reload đã drain | Dấu hiệu điều tra leak đáng tin cậy hơn một snapshot. |
| GC/class unloading logs cho thấy loader cũ được thu gom | Hỗ trợ kết luận đã có unloading trong lần đó; không bảo đảm reload lần sau cũng giống hệt. |
| File JAR không xóa được trên Windows | Phải điều tra file handles, không kết luận ngay là metaspace leak. |

Trong đánh giá production, đo **used vs committed metaspace**, number of classes/loader instances, heap-retained objects, GC behavior và plugin lifecycle. Không dùng một con số metaspace ngẫu nhiên làm ngưỡng chung cho mọi workload.

## 10. Quy trình sửa code trong host/plugin

### Không rò rỉ TCCL: luôn dùng finally

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi code/framework có hợp đồng cần TCCL của plugin.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là snippet minh họa với `pluginLoader` đã tạo. Nó đúng khi tác vụ được xử lý trong một worker thread: **khôi phục trong chính thread đã đổi** trước khi trả thread về pool.

Đừng từ thread quản trị cố xóa ThreadLocal values ở thread khác bằng cách sửa những field private JVM; thay vào đó xây lifecycle/task cleanup hợp lệ trên thread sở hữu.

### Không rò rỉ registry: remove theo key version

~~~java
Map<PluginId, PluginHandle> handles = ...;

// Khi retire đúng phiên plugin:
PluginHandle old = handles.remove(retiredPluginId);
if (old != null) {
    old.stopAndClose();
}
~~~

Đây là snippet minh họa trong một host có các kiểu `PluginId` và `PluginHandle` do ứng dụng định nghĩa. Nếu vừa chạy v1 và v2, phải remove **đúng version**, không gọi clear toàn bộ rồi vô tình xóa plugin đang phục vụ.

### Lifecycle được quản lý

Một `PluginHandle` điển hình nên sở hữu loader, instance/provider, subscriptions, tasks và tài nguyên riêng. Tạo API:

~~~text
start()
  -> acceptRequests()

quiesce()
  -> stopAcceptingNewRequests()
  -> awaitInFlightRequests()

stop()
  -> unregisterListeners()
  -> cancelJobs()
  -> clearCaches()
  -> restoreThreadContexts()
  -> closeStreamsAndJars()
  -> closeClassLoader()

retire()
  -> removeHostStrongReferences()
~~~

Đây là sơ đồ **logic**, không phải code Java thực thi. Mục tiêu là ownership rõ và hành động idempotent khi stop/cleanup có exceptions.

Nếu plugin có lazy dependencies, **không** đóng loader trước khi các requests đang chạy hoàn tất. Với URLClassLoader, việc một thread gọi `close()` khi thread khác đang load class có kết quả không xác định theo tài liệu API.

### Classloader riêng không phải sandbox bảo mật

Đừng nhầm cô lập class namespaces với cô lập quyền. Một `URLClassLoader` riêng **không** làm code plugin mất quyền filesystem/network/process của JVM theo mặc định. Nếu phải chạy code không tin cậy, cân nhắc process/container isolation và những kiểm soát ngoài cơ chế nạp lớp.

## 11. Cách tạo một test regression đáng tin hơn

Một test chống rò rỉ nên có ít nhất hai lớp kiểm tra:

**Lớp chức năng, tất định:**

- Plugin được child loader define như mong đợi.
- Plugin operation chạy đúng.
- Khi phiên được đánh dấu retired, registry/callback entries được remove.
- TCCL của mọi host worker bị tác động được restore.
- Thread/executor do plugin tạo được stop/shutdown.
- Các resource owners gọi close theo hợp đồng; exceptions được log/propagate.

**Lớp khả năng unload, quan sát JVM:**

- Chạy nhiều lượt reload trong isolated test process.
- Không giữ `Class<?>` hoặc loader ở biến test/static cache quá tuổi thọ phiên.
- Quan sát WeakReference/ClassLoadingMXBean/logs/heap snapshot **theo giới hạn và điều kiện thực tế**.
- Nếu loader chưa được thu gom, lấy heap dump và path-to-roots thay vì kết luận mù.
- Không viết assertion “loader phải GC trong X ms” như quy tắc JVM phổ quát.

Một cấu trúc test data:

~~~text
Iteration 1: load v1 -> use -> quiesce -> close -> cleanup
Iteration 2: load v2 -> use -> quiesce -> close -> cleanup
Iteration 3: load v3 -> use -> quiesce -> close -> cleanup
...
Compare number of intentionally active plugin versions and reachable retired loaders
~~~

Nếu số retired loaders reachable tiếp tục tăng sau cleanup, mới đào sâu root paths. Nếu count giảm nhưng metaspace committed chưa giảm, phân biệt chính sách cấp phát và fragmentation với retention.

### Vì sao không dùng một test chỉ gọi System.gc()?

`System.gc()` là yêu cầu gợi ý; một runtime có thể bỏ qua hoặc xử lý theo chính sách khác. Các references trên stack, JIT scopes, debugger và những biến tạm trong test còn có thể giữ loader sống. Không dùng một kết quả “weak.get vẫn khác null” đơn lẻ để kết luận application có leak.

## 12. Case study: kết luận nguyên nhân và hành động

### Triệu chứng

Sau mỗi lần reload plugin, class loader thế hệ trước vẫn có trong heap dump; số lượng retired loaders tăng dù plugin manager đã gọi `close()`.

### Bằng chứng trong bài lab

- Một cache trong host giữ `Class<plugin.Greeter>`.
- Một thread của executor giữ child loader làm TCCL.
- Loader đã `close()` nhưng hai đường retention không bị tự động xóa.
- Cleanup code chủ động `CACHE.clear()` và restore TCCL ở worker thread.

### Root cause

**Vòng đời reference dài hơn vòng đời plugin**. Host quên thực hiện cleanup các registration/context sau khi version cũ retired. Không phải do JVM nạp lại cùng tên class là bug, cũng không phải vì GC “bị hỏng”.

### Sửa lỗi

- Registry/cache theo phiên, clear khi phiên nghỉ.
- TCCL được thay tạm trong scope có `try/finally`, không để lại trong thread pool.
- Plugin lifecycle đảm bảo quiesce, stop tasks, unregister, đóng resources rồi mới retire loader.
- Có regression test cho đường retention, không chỉ test rằng `close()` được gọi.

### Xác nhận sau sửa

Các đường strong-reference do host kiểm soát được cắt; ứng dụng có thể tiếp tục đo sau nhiều lượt reload xem class loaders cũ còn reachable từ GC roots nào khác. **Không tự khẳng định GC đã unload**, vì JVM không bảo đảm thời điểm.

## 13. Các lỗi chẩn đoán phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Thấy metaspace tăng một lần rồi gọi là leak | Class loading/JIT và allocation policy có thể tăng bình thường | So trend và retired loaders reachable qua nhiều chu kỳ |
| Cho rằng `URLClassLoader.close()` tự unload class | Close quản lý lookup/resource handles, không buộc GC | Cắt references rồi quan sát JVM |
| Dùng `System.gc()` như fix production | Không giải quyết GC root giữ loader | Tìm owner và clear references |
| Không phân biệt Class và class name | Hai loaders có thể define cùng binary name | In `Class.getClassLoader()`, compare runtime Class |
| Chỉ đọc exception hoặc log tên loader | Log có thể mơ hồ | Dùng heap dump + paths-to-GC-roots |
| Dọn static cache nhưng quên TCCL | Thread pool tiếp tục giữ loader | Khôi phục context trên đúng worker |
| Dùng `ThreadLocal.remove()` trong sai thread | ThreadLocalMap nằm trong từng thread | Dọn từ thread sở hữu hoặc kết thúc thread đúng cách |
| Thấy WeakReference không null ngay sau cleanup | Chưa chắc JVM đã chạy GC | Không kết luận từ timing thiếu bảo đảm |
| Heap dump đưa công khai để hỏi lỗi | Dump có thể chứa secrets/user data | Bảo vệ file, giới hạn truy cập và retention |
| Đóng loader khi vẫn có request in flight | Concurrent load/close không được đảm bảo | Quiesce và đợi trước close |
| Xóa JAR thất bại rồi quy lỗi metaspace | File handle leak là tài nguyên khác | Theo dõi open handles và chủ sở hữu thật |
| Chuyển mọi class vào system loader để tránh unload issue | Làm mất khả năng retire classes riêng, dễ xung đột version | Dùng loader per version và shared API parent |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Đã gọi `URLClassLoader.close()`, liệu loader chắc chắn không còn trong heap?

**Đáp:** Không. Class/objects đã loaded có thể vẫn được host/thread/registry giữ; `close()` không xóa strong references.

**Câu 2.** Vì sao static `Map<String, Class<?>>` của host có thể giữ cả plugin loader?

**Đáp:** Map giữ Class của plugin, Class gắn với runtime type được defining loader định nghĩa; đường root từ host static cache có thể làm loader reachable.

**Câu 3.** Vì sao TCCL trên worker thread là một điểm nghi vấn?

**Đáp:** Worker thread sống lâu hơn một request/plugin version; contextClassLoader là strong reference tới plugin loader nếu code gán nó và không restore.

**Câu 4.** Xóa cache và restore TCCL có chứng minh class đã unload ngay không?

**Đáp:** Không. Đó là dọn hai root paths đã biết; còn có thể có đường khác, và JVM/GC không có cam kết unload tức thì.

**Câu 5.** WeakReference vẫn trả loader ngay sau cleanup có luôn nghĩa leak?

**Đáp:** Không. GC có thể chưa chạy, test/debugger còn giữ refs hoặc có roots khác. Cần xem heap/paths-to-root và lifecycle, không chỉ timing.

**Câu 6.** Công cụ nào giúp xem class loaders và GC roots?

**Đáp:** `jcmd VM.classloader_stats`/`VM.classloaders` hỗ trợ thống kê hierarchy (HotSpot); heap dump với MAT giúp lần theo GC root paths và dominators.

**Câu 7.** Tại sao không đóng loader ngay khi nhận lệnh reload?

**Đáp:** Các request đang chạy có thể còn cần lazy class/resource loading; concurrent close và load có behavior không được API đảm bảo. Phải quiesce/stop trước.

**Câu 8.** Thấy file JAR không thay được trên Windows có chắc là classloader leak trong metaspace?

**Đáp:** Không. Một file handle có thể do URLClassLoader, JarURLConnection, JarFile hoặc process khác giữ. File handle và reachability của class loader cần đo riêng.

## Tài liệu tham khảo

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): close(), truy cập các class/resource đã nạp và concurrency.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation và runtime class identity.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): getContextClassLoader()/setContextClassLoader().
- [Java SE 21 — WeakReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html): semantics của weak reachability.
- [Java SE 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM.classloader_stats, VM.classloaders, VM.metaspace, GC.heap_dump.
- [JVMS Java SE 21 §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class loading và defining loader.
