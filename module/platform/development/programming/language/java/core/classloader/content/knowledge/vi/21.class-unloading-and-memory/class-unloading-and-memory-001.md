# Điều kiện để lớp và defining loader có thể được thu gom

## 1. Vì sao “object đã hết dùng” không đồng nghĩa “class đã được dỡ”?

Trong Java, vòng đời của **instance**, **runtime class** và **class loader object** là ba chuyện khác nhau. Garbage collector (GC) có thể thu hồi một instance khi nó không còn reachable, trong khi metadata của class tạo ra instance ấy vẫn tồn tại vì JVM còn cần class đó. Muốn một class do custom loader định nghĩa trở thành ứng viên **class unloading**, điều kiện liên quan đến **defining loader** của class.

Theo **Java Language Specification 17, `12.7`**:

- Một triển khai Java **có thể** unload class/interface.
- Một class/interface **chỉ có thể được unload nếu và chỉ nếu defining class loader của nó có thể được garbage collector thu hồi**.
- Class/interface do **bootstrap loader** nạp không được unload.
- Unloading là **tối ưu bộ nhớ**, không phải thao tác mà chương trình Java có thể yêu cầu rồi chờ một thời điểm chắc chắn.

Đây là điều kiện về **khả năng đủ điều kiện**, không phải lời hứa GC chắc chắn xảy ra. Ngay khi mọi tham chiếu tới custom loader đã hết, JVM vẫn có thể trì hoãn hoặc không thực hiện class unloading trong một khoảng chạy cụ thể.

Một mô hình tư duy:

```text
Ứng dụng còn giữ instance / Class<?> / loader / method handle
                         |
                         v
          Custom defining loader còn reachable
                         |
                         v
         Classes của loader chưa đủ điều kiện unload

Ứng dụng thả mọi strong roots tới plugin + loader
                         |
                         v
      Defining loader có thể trở nên unreachable
                         |
                         v
      Classes của loader có thể đủ điều kiện unload
                         |
                         v
           JVM/GC có thể thực hiện unloading
          (không bảo đảm thời điểm hay số lần)
```

Cần phân biệt **điều kiện cần/đủ theo khả năng** với **quyết định thực thi**: chỉ khi defining loader có thể reclaim thì class mới có thể unload, nhưng việc loader có thể reclaim **không bắt buộc** VM unload ngay.

## 2. Defining loader là gì, khác initiating loader thế nào?

JVM xác định runtime class bằng **binary name + defining class loader**. Ví dụ cùng `plugin.Task` có thể được custom loader A và B định nghĩa thành hai class khác nhau:

```text
("plugin.Task", LoaderA) ≠ ("plugin.Task", LoaderB)
```

Trong đó:

- **Defining loader**: loader trực tiếp định nghĩa runtime class (thường thông qua `defineClass`, hoặc cơ chế VM tương ứng).
- **Initiating loader**: loader được VM ghi nhận đã khởi xướng việc nạp class; có thể chỉ ủy quyền cho parent.
- **Parent loader**: loader mà một `ClassLoader` thường hỏi trước theo parent delegation.

Ví dụ `child.loadClass("java.lang.String")` có thể trả về chính `String.class` do bootstrap định nghĩa. Child là nơi code gọi lookup nhưng **không trở thành defining loader** của `String`. Class unloading liên quan **defining loader thực sự**, không đơn giản loader từng trả `Class<?>`.

Với ordinary class:

```java
ClassLoader owner = someClass.getClassLoader();
```

`someClass` phải là `Class<?>` được lấy hợp lệ. Phương thức trên giúp biết defining loader mà Java API cho phép quan sát; `null` biểu thị bootstrap đối với class thường do bootstrap định nghĩa. Với primitive/void/array có quy tắc riêng, nên không suy ra luôn có một class file mà bootstrap đã đọc.

### Vì sao loader còn sống thì không unload class của nó?

Giả sử loader L còn reachable. Sau đó code có thể yêu cầu L nạp một class D chưa được nạp, D lại tham chiếu class C từng tồn tại. Nếu JVM trước đó đã unload C nhưng vẫn giữ L, việc nạp lại C có thể tạo thay đổi không quan sát được một cách trong suốt: static state, initialization side effects, native state, hoặc `Class<?>` identity có thể khác. JLS `12.7` vì vậy gắn điều kiện unloading của class với khả năng reclaim **defining loader**.

Điểm suy ra quan trọng:

- **Không thể yêu cầu unload một class đơn lẻ tùy ý trong loader vẫn sống** bằng cách xóa một biến reference.
- **Một loader dùng lâu dài** thường giữ tập class đã định nghĩa cho vòng đời của loader đó.
- **Để nạp phiên bản mới** của cùng binary name, hệ plugin thường tạo **defining loader mới**, không cố định nghĩa lại class trong loader cũ.

## 3. Thế nào là “có thể được GC thu gom”?

Một Java object đủ điều kiện GC khi không còn reachable từ các **GC roots** theo cơ chế reachability của VM, có xét những quy tắc đặc biệt của references. Class loader cũng là một object. Nếu có **đường strong reachability** tới loader hoặc tới object/class khiến loader phải được giữ sống, loader chưa thể được thu gom.

Các nguồn giữ loader còn sống thường gặp:

| Nguồn giữ tham chiếu | Ví dụ | Vì sao ảnh hưởng class unloading? |
|---|---|---|
| Biến/cấu trúc dữ liệu ứng dụng sống lâu | `static Map<String, ClassLoader>` | Registry ở host giữ strong reference tới loader |
| Instance của class do plugin loader định nghĩa | Plugin instance còn nằm trong host cache | Object còn sống cần runtime class tương ứng |
| `Class<?>` token | `static Class<?> cached = pluginClass;` | Class metadata/token đang được code sống tham chiếu |
| Reflection handles | `Method`, `Constructor`, `Field`, method handle hoặc lookup gắn với plugin class | Có thể giữ declaring class/related types reachable |
| Thread context class loader (TCCL) | Worker thread `setContextClassLoader(pluginLoader)` rồi không restore | Thread còn sống giữ loader |
| Thread-local state | `ThreadLocal` value chứa plugin instance | Worker sống lâu tiếp tục giữ object |
| Thread do plugin tạo | `Runnable`/stack/callback hoặc thread state còn tham chiếu plugin | Code/object thuộc plugin còn được dùng |
| Executor/scheduled task | Job/callback lambda thuộc plugin còn trong queue | Scheduled reference giữ classes/instances/loader |
| Event listeners | Host listener registry chứa plugin listener | Host trở thành root tới plugin |
| JVM/native integrations | JNI global references, native handles còn lưu Java objects | Reference từ native side có thể giữ loader graph |
| Cache ở thư viện dùng chung | Singleton host giữ reflection metadata hoặc proxy của plugin | Parent/shared code giữ references tới class của child |

**Không phải mọi reference đều mạnh.** `WeakReference` tới loader/class **không tự** giữ referent sống. `SoftReference` và `PhantomReference` có semantics khác nhau; không nên coi chúng như một cơ chế xác nhận unload tức thì. Một `WeakReference` chỉ hỗ trợ **quan sát** GC, không ra lệnh GC.

### Đường reachability thường là gián tiếp

Không cần một biến có tên `pluginLoader` vẫn còn sống. Đường giữ loader có thể qua nhiều objects:

```text
GC root
   |
   v
Host static Registry
   |
   v
Plugin listener instance
   |
   v
Runtime Class của listener
   |
   v
Defining PluginClassLoader
```

Trong hệ thống thật, đường có thể phức tạp hơn do reflection, class mirrors, method handles, class-loader data và cấu trúc JVM. Mấu chốt là **toàn bộ graph**, không phải chỉ tên biến của loader.

## 4. Instance đã được thu gom nhưng class vẫn còn là chuyện bình thường

Giả sử:

```java
PluginTask task = new PluginTask();
task.run();
task = null;
```

Đây là đoạn minh họa, cần class `PluginTask` và xử lý `run()` phù hợp. Dòng `task = null` chỉ thay giá trị **một biến**, không chứng minh không còn reference khác tới object. Kể cả instance đó thực sự được GC, defining loader vẫn có thể được giữ bởi registry, code đang chạy, các `Class<?>` tokens khác, instance khác cùng loader, v.v.

Tương tự, một class được loader định nghĩa có thể không hề có instance nào mà vẫn không unload, vì defining loader còn reachable.

| Trạng thái | Suy luận có căn cứ |
|---|---|
| Object bị GC | Object đó hết reachable, **không** chứng minh class unload |
| Không còn instances quan sát được | **Không đủ**, còn `Class<?>`/loader/code/cache |
| `Class<?>` strong reference còn sống | Class chưa thể biến mất một cách gây sai semantics; thường giữ defining loader |
| Defining loader còn strong reachable | Các class do nó định nghĩa **không đủ điều kiện** unload theo JLS |
| Defining loader đã có thể reclaim | Classes do loader định nghĩa **có thể** đủ điều kiện; VM quyết định |
| `System.gc()` được gọi | Chỉ yêu cầu GC, **không bảo đảm** đã chạy, đã unload hoặc đã trả RAM cho OS |

Đừng dùng một biến `null` làm bằng chứng class unloading; hãy xác định **strong GC roots** tới loader và classes.

## 5. Static fields có luôn làm class loader bị leak không?

**Không.** Một static field thuộc class do plugin loader định nghĩa có thể giữ các object trong cùng vòng đời; nếu toàn bộ nhóm này không còn reachable từ GC roots thì reference cycle nội bộ không tự tạo leak. Trường hợp nguy hiểm là **host hoặc thư viện sống lâu** giữ class, instance, `Method` hoặc callback của plugin trong static registry/cache.

Ví dụ đường tham chiếu gây retention: `host static map → plugin instance → runtime class → defining loader`. Bỏ biến local `pluginLoader` không cắt đường này. Bài về static field và reflection cache phân tích thêm `WeakHashMap`, `ClassValue` và cache theo generation.

## 6. ClassLoader.close không phải class unloading

`URLClassLoader.close()` chủ yếu ngăn đọc những class/resource mới từ URL nguồn do loader quản lý và giải phóng file/JAR handles tương ứng. **Các class đã nạp và object hiện có vẫn có thể hoạt động**; việc JVM có unload class tùy thuộc khả năng reclaim defining loader và quyết định GC.

Cần phân biệt `close` ở mức I/O/resource với eligibility ở mức runtime class. Bài phân biệt mất tham chiếu, `close()` và unloading kiểm chứng ba hành động này bằng thí nghiệm chạy được.

## 7. Metaspace liên quan gì tới class unloading?

Trên **HotSpot JDK 17+**, class metadata phần lớn được quản lý trong Metaspace, khác Java heap chứa các object instance và `Class<?>` mirrors. Nếu mỗi lần reload tạo thêm defining loader mà những loader cũ vẫn reachable, class metadata có thể tích lũy và dẫn tới áp lực Metaspace.

Unloading, khi JVM thực hiện, có thể giải phóng/reuse metadata của generation cũ; không có bảo đảm mức `committed` hoặc RSS giảm ngay. **Method area** của JVMS là khái niệm logic, còn **Metaspace** là chi tiết triển khai HotSpot. Bài Metaspace riêng giải thích `used/committed/reserved`, NMT và điều tra OOME.

## 8. Java 17 demo: tạo custom defining loader, chỉ giữ WeakReference khi rời phạm vi

Demo sau nạp một class **chỉ tồn tại ở URL path của plugin**, lấy `WeakReference` tới loader và `Class<?>`, sau đó thoát khỏi method để bỏ các strong local references. Việc VM có collect/unload trong lần chạy cụ thể là **không xác định**.

### 8.1. Cấu trúc thư mục

```text
src/
  plugin/
    demo/
      Entry.java
  host/
    UnloadEligibilityDemo.java
out/
  plugin/
  host/
```

File `src/plugin/demo/Entry.java`:

```java
package demo;

public final class Entry {
    public static String value() {
        return "plugin-alive";
    }
}
```

File `src/host/UnloadEligibilityDemo.java`:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadEligibilityDemo {
    private record Watch(
            WeakReference<ClassLoader> loader,
            WeakReference<Class<?>> type) {
    }

    private static Watch loadOnce() throws Exception {
        URL directory = Path.of("out/plugin").toUri().toURL();
        ClassLoader parent =
                UnloadEligibilityDemo.class.getClassLoader();

        URLClassLoader pluginLoader = new URLClassLoader(
                "plugin-v1", new URL[]{directory}, parent);

        try (pluginLoader) {
            Class<?> type = Class.forName(
                    "demo.Entry", true, pluginLoader);

            WeakReference<ClassLoader> loaderRef =
                    new WeakReference<>(pluginLoader);
            WeakReference<Class<?>> classRef =
                    new WeakReference<>(type);

            System.out.println("Defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            System.out.println("Class lookup reused: "
                    + (pluginLoader.loadClass("demo.Entry") == type));

            System.out.println("Method: "
                    + type.getMethod("value").invoke(null));

            System.out.println("Weak refs populated before return: "
                    + (loaderRef.get() != null
                       && classRef.get() != null));

            // Đảm bảo strong references còn live tới điểm này.
            Reference.reachabilityFence(type);
            Reference.reachabilityFence(pluginLoader);

            return new Watch(loaderRef, classRef);
        }
    }

    public static void main(String[] args) throws Exception {
        Watch watch = loadOnce();
        System.out.println("Returned from loader scope");

        // Đây CHỈ là một yêu cầu GC, không phải lệnh unload.
        System.gc();

        System.out.println("Loader weak ref cleared: "
                + (watch.loader().get() == null));
        System.out.println("Class weak ref cleared: "
                + (watch.type().get() == null));
    }
}
```

### 8.2. Biên dịch và chạy

Trên Linux/macOS, đứng tại thư mục chứa `src`:

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/Entry.java
javac -d out/host src/host/UnloadEligibilityDemo.java
java -cp out/host UnloadEligibilityDemo
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/demo/Entry.java
javac -d out/host src/host/UnloadEligibilityDemo.java
java -cp out/host UnloadEligibilityDemo
```

**Rất quan trọng:** chỉ `out/host` nằm trong application classpath khi chạy. Không thêm `out/plugin` vào `-cp`, vì parent loader có thể tìm `demo.Entry` trước custom `URLClassLoader`, làm ví dụ không còn chứng minh class do pluginLoader định nghĩa.

### 8.3. Kết quả nào xác định, kết quả nào không?

Bốn dòng đầu của stdout:

```text
Defined by plugin loader: true
Class lookup reused: true
Method: plugin-alive
Weak refs populated before return: true
Returned from loader scope
```

**Hai dòng cuối phụ thuộc GC/JVM/timing** và có dạng:

```text
Loader weak ref cleared: false
Class weak ref cleared: false
```

hoặc có thể in `true` cho một/both trường hợp nếu collector đã reclaim referent tương ứng trước lúc đọc. **Không có stdout duy nhất được Java specification đảm bảo cho hai boolean cuối**, kể cả có `System.gc()`. Đây là chủ đích của ví dụ: đo hiện tượng chứ không giả định GC đã thực hiện một lời hứa unload.

Phân tích:

1. `Class.forName("demo.Entry", true, pluginLoader)` khiến `pluginLoader` tìm và định nghĩa class `demo.Entry` từ `out/plugin` vì parent không thấy tên ấy.
2. `type.getClassLoader() == pluginLoader` true chứng minh **defining loader**.
3. Gọi `loadClass` lần sau trả cùng runtime `Class<?>`; không định nghĩa lặp.
4. `type.getMethod("value").invoke(null)` trả chuỗi đã khai báo trong plugin code.
5. Weak references được tạo trong lúc mạnh references còn sống; chúng không tự giữ class/loader.
6. Sau khi `loadOnce()` trả về, strong local references trong method đó hết phạm vi cần thiết; chỉ còn các weak references mà `Watch` đang giữ **trong thiết kế ví dụ**.
7. `try-with-resources` đã đóng URLClassLoader, nhưng nó không kích hoạt class unloading như một lệnh đồng bộ.
8. `System.gc()` gửi yêu cầu GC. Nếu loader weak reference chưa cleared, đó **chưa** là bằng chứng leak — VM có thể chưa reclaim tại thời điểm kiểm tra.

Với chương trình quá ngắn, VM có thể kết thúc trước khi việc class unloading quan sát được diễn ra. Không nên sửa code thành một vòng lặp vô hạn gọi `System.gc()` để “bắt buộc” xuất hiện `true`.

### Một điều cần phân biệt khi quan sát WeakReference

Nếu `watch.loader().get() == null`, weak referent loader đã được collector xử lý là không còn strongly reachable theo semantics của `WeakReference`. Điều đó là **quan sát về loader referent**, không tự chứng minh một sự kiện class-unload log cụ thể đã xuất hiện cùng thời điểm, và cũng không nói OS đã trả lại bao nhiêu RAM.

Nếu class token weak ref chưa cleared ở một lần quan sát, không được khẳng định VM chắc chắn có leak. Trạng thái GC và lifetime liveness không phải deterministically controllable từ Java user code.

## 9. Ví dụ Java 17: TCCL của thread có thể giữ loader sống

Một worker thread lâu sống có thể chứa `contextClassLoader` vẫn trỏ tới plugin loader sau khi plugin dừng. Đường `GC root → live Thread → TCCL → plugin loader` có thể giữ generation đó sống.

Trong tác vụ đặt TCCL tạm thời, khôi phục loader trước trong `finally`; dọn `ThreadLocal` trên **chính worker thread** đã lưu value và ngừng các task chưa kết thúc. Bài Thread/ThreadLocal/TCCL triển khai thí nghiệm độc lập trên executor để kiểm chứng retention này.

## 10. Class unloading không đồng nghĩa hot reload class trong cùng loader

Ví dụ plugin A đã load `plugin.Entry` version 1 bởi loader L1. Sau khi triển khai code mới ở cùng đường dẫn file, ứng dụng gọi:

```java
Class<?> next = L1.loadClass("plugin.Entry");
```

Trong loader được thiết kế đúng, lời gọi này thường trả **class đã ghi nhận** bởi L1, không nạp lại bytecode version 2. Một defining loader không được định nghĩa lặp class cùng binary name thành hai runtime classes độc lập trong chính loader đó; nỗ lực `defineClass` trùng có thể gây `LinkageError`.

Một chu kỳ reload đúng thường:

```text
Version 1:
  L1 -> plugin.Entry v1
  Host dùng plugin v1
  Host dừng plugin, bỏ references và close tài nguyên L1
  L1 có thể trở nên unreachable

Version 2:
  L2 (loader mới) -> plugin.Entry v2
  Host dùng plugin v2 qua shared API
  L2 có runtime class identity riêng

Class unloading của L1 (nếu có) không cần diễn ra
trước khi L2 load class cùng binary name.
```

**Không cần đợi L1 đã được GC mới có thể tạo L2.** Hai runtime classes cùng binary name có thể tồn tại song song nếu defining loaders khác nhau và các loading constraints/app contracts vẫn được tuân thủ.

Ngược lại, nếu host giữ `Class<?>` hoặc instance từ L1 sau khi chuyển sang L2, class metadata của cả hai thế hệ có thể tồn tại lâu dài. Đây là nguồn Metaspace growth trong hot deployment.

## 11. Những nguồn leak rất dễ bỏ sót

Để kiểm tra khả năng reclaim defining loader, hãy truy vết từ **GC roots** tới loader thay vì chỉ tìm một biến `loader`. Các đường tham chiếu thường gặp gồm host static `Map<String, Class<?>>` hoặc `Map<String, Method>`, event listener/callback, `ServiceLoader` cache, thread/TCCL/`ThreadLocal`, pending `CompletableFuture`/executor task, và JDBC/JMX/logging registries.

**Không có một lệnh cleanup chung cho mọi framework.** Gỡ chính xác registration handles, cache entries và thread state theo owner của mỗi resource. Các bài về static cache, threads và ServiceLoader giải thích riêng từng nhóm, cách đo và tình huống thất bại.

## 12. Parent–child loader: hướng tham chiếu quyết định khả năng thu gom

Một custom loader thường giữ parent:

```text
Child PluginLoader ---> Parent SharedApiLoader
```

Điều này **không bắt buộc** parent giữ child. Nếu chỉ có mũi tên từ child sang parent, parent còn sống **không tự** làm child còn sống.

Nhưng một registry/layer/framework có thể tạo đường ngược:

```text
Host root
   |
   v
PluginManager
   |
   v
Child PluginLoader
   |
   v
SharedApiLoader (parent)
```

Đường `Host → PluginManager → Child` là lý do child không GC, không phải riêng quan hệ `Child → Parent`.

Với JPMS `ModuleLayer`, các layer/loader objects có graph reference phụ thuộc cách tạo và giữ. Nếu host còn giữ layer object, modules, service providers hoặc objects của plugin, không nên kỳ vọng chỉ `pluginLoader = null` là đủ. Cần phân tích **thực tế references do implementation giữ**, không khẳng định mọi layer đều có cùng cấu trúc retention.

## 13. Những classes nào không nên kỳ vọng unload trong ứng dụng bình thường?

Theo JLS `12.7`, **class/interface do bootstrap loader định nghĩa không unload**. Các class như `java.lang.String` trong JDK tiêu chuẩn thuộc nhóm core runtime này.

Với platform/application loader mặc định của một JVM đang chạy, loader thường là một phần sống dài của runtime/application. Vì thế những classes do chúng định nghĩa **thường không phải mục tiêu để unload giữa chừng**, trừ khi các điều kiện reachability đặc biệt của triển khai cho phép.

Điều này giải thích vì sao chương trình:

```java
for (int i = 0; i < 1000; i++) {
    Object o = new SomeClass();
}
```

có thể GC hàng nghìn instances mà `SomeClass` vẫn được loaded. `SomeClass` trong một app loader sống cùng chương trình không phải một class được unload mỗi khi hết instances.

Những ứng dụng hưởng lợi nhiều từ class unloading:

- Application servers có nhiều lần deploy/redeploy.
- Plugin managers tạo riêng loader cho từng plugin/version.
- Runtime tạo/định nghĩa dynamic proxies hoặc generated classes theo loader có vòng đời ngắn.
- Code evaluation frameworks, scripting/runtime tích hợp khi chúng dùng dynamic defining loaders.

**Không đồng nghĩa mọi ứng dụng nạp nhiều class đều có unloading**: nếu tất cả classes được định nghĩa bởi một loader sống đến hết process, việc drop vài instances không làm loader eligible.

## 14. Cách quan sát class unloading trên HotSpot JDK 17

Trên HotSpot có thể khởi động JVM với `-Xlog:class+load=info,class+unload=info` để quan sát sự kiện. Log unload xuất hiện là bằng chứng JVM đã unload một lớp cụ thể; **thiếu log trong một lần chạy** không chứng minh loader bị leak. `System.gc()` là request, không là bằng chứng.

Khi điều tra, kết hợp event logs, class-loader counts và heap retaining paths; so sánh nhiều lần reload có cùng workload. Bài quan sát unloading phân tích quy trình thử nghiệm, cách đọc counter và các giới hạn.

## 15. Quy trình stop/reload plugin an toàn hơn

Một generation plugin chỉ có cơ hội retire đúng khi host **ngăn tác vụ mới → drain/cancel in-flight work → unregister listeners/registries → dọn thread, TCCL, `ThreadLocal`, caches → đóng resource và URL loader → bỏ strong references**.

Không dùng việc `close()` thành công hay số lần `System.gc()` đã gọi làm điều kiện xác nhận class unloading. Tùy kiến trúc, cần phối hợp thứ tự shutdown để tránh task khác đồng thời nạp class từ loader đang đóng.

## 16. Những hiểu lầm phổ biến

| Nhận định sai | Điều đúng |
|---|---|
| “Không còn instance thì class chắc chắn unload.” | Class unloading phụ thuộc **defining loader** có thể reclaim, không chỉ instance. |
| “Đặt `loader = null` là xong.” | Chỉ bỏ một reference; có thể còn registry, TCCL, Class<?>, listener, v.v. |
| “`URLClassLoader.close()` sẽ unload mọi class ngay.” | `close` quản lý resource/lookup; class unloading do GC/VM quyết định. |
| “Gọi `System.gc()` sẽ trả `true` ở WeakReference test.” | `System.gc()` là yêu cầu không có bảo đảm thời điểm/thực thi. |
| “Static field của plugin nào cũng gây leak.” | Cần strong path từ một root sống lâu; cycles nội bộ không tự pin graph. |
| “Class của bootstrap loader có thể unload nếu không có instances.” | JLS `12.7` loại trừ class/interface do bootstrap loader nạp. |
| “Tăng Metaspace là bằng chứng đủ của leak.” | Cần xét used/committed/reserved, workload và GC/loader stats. |
| “Class unload thì OS RSS giảm ngay từng byte tương ứng.” | VM allocator có thể giữ/reuse memory; RSS không phải thước đo class unload trực tiếp. |
| “Parent loader sống thì mọi child loaders sống.” | Child thường giữ parent; parent không mặc nhiên giữ child. |
| “TCCL không liên quan class unloading.” | Worker thread giữ loader qua TCCL là strong reference rất phổ biến. |
| “Cache Method không giữ class/plugin.” | Reflection metadata có thể giữ declaring class và loader graph reachable. |
| “Đặt tên loader giống nhau cho phép tái sử dụng class identity.” | Loader name không quyết định runtime identity. |
| “Unloading giống hot replacement trong cùng loader.” | Thường cần loader mới; class cũ vẫn có thể tồn tại cho đến khi GC. |
| “Không thấy unload log sau một lần chạy là leak.” | Unloading là tối ưu không có deadline, demo ngắn có thể kết thúc trước GC. |

## 17. Bài tập tự kiểm tra

**Câu 1.** Một `PluginTask` instance đã được GC, nhưng host vẫn giữ `Class<?>` của `PluginTask` trong static map. Class có đủ điều kiện unload chưa?

**Đáp án:** Chưa. `Class<?>` còn được giữ bởi host có thể tiếp tục giữ class/defining loader reachable. Mất instance riêng không đủ.

**Câu 2.** Defining loader của class có thể reclaim. JVM bắt buộc phải unload class ngay trong lần GC tiếp theo không?

**Đáp án:** Không. JLS `12.7` cho phép class unloading như tối ưu; **eligible** không bảo đảm thời điểm GC/unloading.

**Câu 3.** `URLClassLoader.close()` và `System.gc()` có phải hai cách tương đương để unload class không?

**Đáp án:** Không. `close()` đóng resources và ảnh hưởng lookup; `System.gc()` yêu cầu GC nhưng không bảo đảm thực thi; class unloading là cơ chế VM riêng dựa trên eligibility.

**Câu 4.** Nếu child loader giữ parent loader, parent còn sống có tự giữ child sống không?

**Đáp án:** Không mặc nhiên. Reference hướng từ child sang parent không tương đương từ parent sang child. Cần có đường strong reference từ root tới child.

**Câu 5.** Static field trong plugin giữ một object khác cũng thuộc plugin. Có tự ngăn GC mọi class của plugin không?

**Đáp án:** Không chỉ bởi quan hệ nội bộ ấy. Nếu toàn bộ graph không còn strong path từ roots bên ngoài, cycles nội bộ có thể được collector xử lý.

**Câu 6.** Một worker thread còn giữ `Thread.currentThread().getContextClassLoader() == oldPluginLoader` sau redeploy. Điều gì có thể xảy ra?

**Đáp án:** Thread còn sống giữ old loader reachable, khiến các classes của old loader chưa đủ điều kiện unload; nên restore TCCL đúng worker thread trong `finally`.

**Câu 7.** Trong demo `UnloadEligibilityDemo`, vì sao hai giá trị `Loader weak ref cleared` và `Class weak ref cleared` không có stdout cố định?

**Đáp án:** Chúng phụ thuộc GC/timing và trạng thái reachability tại thời điểm kiểm tra; `System.gc()` không cam kết collect/unload đồng bộ.

**Câu 8.** Plugin v1 và v2 có thể cùng tồn tại với cùng binary name `plugin.Entry` không?

**Đáp án:** Có, nếu hai defining loaders khác nhau và các shared API/loading constraints phù hợp. Không cần chờ class v1 unload mới được tạo loader v2.

**Câu 9.** `Class<?>` token, `Method` và `MethodHandle` của plugin nằm trong host cache có liên quan class unloading không?

**Đáp án:** Có. Chúng có thể giữ runtime classes/loader graph reachable, nên phải xem lifecycle của reflection/call-site caches.

**Câu 10.** Metaspace used giảm sau class unloading nhưng OS RSS giữ nguyên. Có mâu thuẫn không?

**Đáp án:** Không. VM allocator có thể giữ/commit memory để tái sử dụng; các metrics không đồng nhất.

**Câu 11.** Một chương trình không bật log unload nhưng thấy heap usage tăng theo từng lần reload. Cần kết luận gì?

**Đáp án:** Chưa kết luận được classloader leak. Phải xem GC roots, loader count, class metadata, heap cache, profiler và cấu hình logging/GC; heap tăng có nhiều nguyên nhân.

**Câu 12.** Vì sao JLS không cho unload class khi defining loader còn potentially reachable?

**Đáp án:** Loader còn sống có thể được yêu cầu resolve/nạp class về sau. Nếu một class bị unload rồi reload dưới cùng loader, sự khác nhau ở static state, initialization side effects, class identity hoặc native state có thể làm chương trình quan sát được việc unloading, trái yêu cầu transparency.

## 18. Tóm tắt và tài liệu chính thức

**Nắm chắc năm điều:**

1. **Class unloading chỉ có thể khi defining loader có thể reclaim**; đây là điều kiện về eligibility, không phải lời hứa JVM sẽ unload lập tức.
2. **Reachability phụ thuộc toàn bộ GC-root graph**: instances, `Class<?>`, reflection metadata, TCCL, threads, registries và caches đều đáng kiểm tra.
3. **Close resource ≠ unload class**: `URLClassLoader.close()` không giải phóng đồng bộ các runtime classes đã định nghĩa.
4. **Hot reload thường dùng loader mới** cho cùng binary name; loader cũ chỉ có cơ hội GC sau khi dọn mọi references còn sống.
5. **Quan sát nhiều tín hiệu, không đoán**: weak refs, class unload logs, loader stats và Metaspace numbers có vai trò khác nhau; không tín hiệu đơn lẻ nào thay thế phân tích GC roots.

**Tài liệu chuẩn:**

- [JLS 17 — `12.7` Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): điều kiện defining loader và giới hạn class unloading.
- [JVMS 17 — `5.3` Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader, initiating loader và class identity.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findLoadedClass`, `defineClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, class/resource lookup và tài nguyên URL/JAR.
- [Java SE 17 — WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak-reference reachability/clearing.
- [Java SE 17 — Reference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): `reachabilityFence` và reference operations.
- [Java SE 17 — java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+unload` và `-Xnoclassgc` trên HotSpot.