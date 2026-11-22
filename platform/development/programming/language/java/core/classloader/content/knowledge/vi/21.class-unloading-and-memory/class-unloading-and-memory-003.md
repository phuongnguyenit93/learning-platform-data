# Phân biệt mất tham chiếu đối tượng, đóng loader và class unloading

Trong một ứng dụng Java có plugin, ba hiện tượng sau dễ bị nhầm thành một:

1. **Mất tham chiếu tới một object:** code không còn giữ đối tượng qua một đường tham chiếu mạnh (*strong reference*) nào đó. Nếu object không còn được giữ sống theo quy tắc reachability, garbage collector (GC) **có thể** thu hồi object đó.
2. **Đóng một URLClassLoader:** gọi `loader.close()` để ngừng việc tìm class/resource mới từ URL search path của loader và đóng các file/JAR handles mà loader đã mở. Việc đóng **không hủy object hoặc class đã load**.
3. **Class unloading:** JVM **có thể** dỡ metadata/trạng thái liên quan class nếu **defining class loader** của class đủ điều kiện được GC thu hồi. Đây là hoạt động tùy JVM, không có lệnh Java SE đảm bảo “unload ngay”.

**Không tồn tại suy luận tự động `object = null` ⇒ `loader.close()` ⇒ `class unloaded`.** Đây là ba vấn đề thuộc các tầng quản lý bộ nhớ, tài nguyên và kiểu runtime khác nhau.

Bài thuộc nhóm **Dỡ lớp và bộ nhớ** của Java core – classloader. Mục tiêu là hiểu điều kiện thật sự để class có thể unload, thấy tận mắt `close()` không xóa class, dùng `WeakReference` và công cụ JVM đúng cách, nhận diện rò rỉ class loader trong hệ thống plugin/hot reload và quản lý lifecycle theo thứ tự an toàn.

## 1. So sánh nhanh ba hành động

| Tiêu chí | Object mất tham chiếu | `URLClassLoader.close()` | Class unloading |
| --- | --- | --- | --- |
| Đối tượng chính | Instance trên heap, loader object hoặc object khác | Một `URLClassLoader` cụ thể | Runtime definition/metadata của class hoặc interface |
| Bản chất | Reachability thay đổi | Đóng những nguồn class/resource và file handles loader quản lý | Tối ưu thu hồi class do JVM quyết định |
| Có phải GC? | Không: mất reference khác với đã thu hồi; GC có thể chạy sau | Không | Gắn với khả năng thu hồi defining loader |
| Có xảy ra ngay? | Reference có thể bị bỏ ngay; thu hồi không được bảo đảm | Lời gọi diễn ra ngay, có thể ném I/O exception | Không có thời hạn bảo đảm |
| Có ngăn dùng object cũ không? | Object còn reference khác thì vẫn dùng được | Không tự vô hiệu hóa object/class đã nạp | JVM không được unload class khi loader còn potentially reachable |
| Có đóng resource riêng của plugin không? | Không | Chỉ những resource thuộc trách nhiệm URL loader | Không phải API cleanup tổng quát |
| Có làm class mới được nạp không? | Không trực tiếp | Sau close không tìm/define class mới từ URL search path của loader | Unloading không phải class loading |
| Bằng chứng phù hợp | GC roots, heap dump, WeakReference có giới hạn | Quan sát close, handles và lookup sau close | Class unloading logs, classloader stats, GC analysis |

Từ bảng này, hãy tách hai câu hỏi thường gặp: **“JAR đã được đóng chưa?”** và **“Các class của plugin đã được unload chưa?”**. Câu trả lời cho câu đầu không quyết định câu thứ hai.

## 2. Mất tham chiếu object: không đồng nghĩa object đã bị thu hồi

Ví dụ Java:

```java
Object a = new Object();
Object b = a;
a = null;
System.out.println(b != null);
```

Stdout:

```text
true
```

`a = null` chỉ xóa **một** tham chiếu. Biến `b` vẫn có reference tới object ban đầu nên ta vẫn có thể dùng object ấy.

Ngay cả khi không còn reference mạnh nào, GC cũng không có nghĩa vụ thu hồi object vào thời điểm bạn chỉ định. JVM có thể tối ưu liveness, phân loại references (strong/soft/weak/phantom) và quyết định lúc nào cần thực hiện GC. Đừng đánh đồng kết thúc scope của một biến với sự kiện giải phóng heap diễn ra ngay tức thì.

### Hiểu reachability qua GC roots

```text
GC roots
  |
  +-- Java thread stack -> local variable -> Object A
  |
  +-- Host static field -> registry -> Object B
  |
  +-- JNI global ref ---------------------> Object C

Object D ----> Object E
   ^                |
   +----------------+
   (không còn đường mạnh từ GC root)
```

- A, B, C có thể còn được giữ sống do đường reference xuất phát từ root.
- D và E có thể đủ điều kiện thu hồi nếu thực sự không còn đường giữ sống nào khác.
- Chu trình `D → E → D` tự nó **không** chứng minh memory leak: GC có thể thu hồi cả cụm không còn reachable.
- Một object bị bỏ khỏi biến local nhưng còn nằm trong collection/static registry vẫn có thể reachable.

Khi chẩn đoán, câu hỏi là **“còn đường từ root tới object không?”**, không chỉ “đã thấy dòng `variable = null` chưa?”.

### `System.gc()` có bắt buộc thu hồi không?

Không. `System.gc()` biểu thị yêu cầu GC; JVM có chính sách quyết định việc thực hiện và thời điểm. Đừng viết chương trình dựa trên giả định:

```java
plugin = null;
System.gc();
// Sai nếu tin rằng class plugin chắc chắn đã unload từ đây.
```

Đây là **đoạn minh họa**, giả định biến `plugin` đã được khai báo. Muốn dừng plugin đúng cách, phải quản lý tasks, callbacks, resources và loader trước; GC không phải lifecycle API.

## 3. `URLClassLoader.close()`: đóng URL source và handles, không xóa định nghĩa class

Trong Java 17, `java.net.URLClassLoader` là class loader tìm class/resource từ URL tới thư mục hoặc JAR. Nó triển khai `Closeable`, có method:

```java
public void close() throws IOException
```

Hợp đồng API Java SE 17 nói:

- Sau close, URL loader không còn được dùng để nạp class/resource **mới do chính loader đó định nghĩa từ nguồn URL**.
- Class/resource **đã nạp** còn có thể được truy cập.
- Các class/resource do **parent** định nghĩa vẫn có thể được truy cập qua delegation.
- Với các `jar:`/`file:` URL, loader cố đóng các file/JAR mà nó đã mở.
- Nếu một thread đang load class **đồng thời** với lúc thread khác gọi close, kết quả lần load đang chạy là **không được xác định** theo JavaDoc. Host phải điều phối stop/await trước khi đóng.
- Close có thể ném `IOException`; đóng lại một loader đã đóng không tạo thêm tác dụng.

Điều `close()` **không làm**: xóa `Class<?>`, xóa instance, reset static fields, ngừng execution của method đã nạp, dừng executor/threads của plugin, đóng mọi socket/DB connection, hoặc yêu cầu GC/class unloading ngay.

### Vì sao method của class cũ vẫn chạy?

Vì bytecode và runtime metadata của class đã nạp không nằm trong “stream còn mở của JAR” theo cách khiến đóng file đồng nghĩa vô hiệu hóa object. Có thể JVM đã load/link class, tạo object và resolve method cần gọi.

Tuy nhiên, **không phải mọi method của một class cũ đều chắc chắn thành công sau close**. JVM có thể chỉ resolve một class phụ thuộc khi method được gọi lần đầu. Nếu dependency ấy chưa nạp và chỉ có trong URL của loader đã đóng, chương trình có thể nhận `NoClassDefFoundError` hoặc lỗi liên kết phù hợp.

Phân biệt:

- **Class A đã load:** thường vẫn có thể truy cập sau close.
- **Class B chỉ có file trên đĩa nhưng chưa load:** loader đã close không thể tìm mới B từ URL đó.
- **Class từ parent:** có thể tiếp tục truy cập sau close nếu parent cung cấp.
- **Object vẫn được tham chiếu:** không tự biến thành `null` hoặc “đã destroy”.

## 4. Class unloading: điều kiện của JLS 17

Java Language Specification `12.7` quy định rằng một class/interface **có thể được unload nếu và chỉ nếu defining class loader của nó có thể được GC thu hồi**. Class/interface do **bootstrap loader** nạp không được unload theo quy tắc này.

Cụm “**có thể**” rất quan trọng:

- **Đủ điều kiện không phải bắt buộc.** JVM có thể chưa chạy GC, chưa thực hiện class unloading hoặc giữ memory committed để tái sử dụng.
- **Đóng loader không phải điều kiện đủ.** Một `URLClassLoader` đã closed vẫn có thể reachable từ host objects, thread pool hoặc cache.
- **Mất reference instance không phải điều kiện đủ.** Loader vẫn có thể định nghĩa nhiều class khác và vẫn được host giữ.
- **Không được unload khi defining loader còn potentially reachable.** Nếu VM unload class trong lúc loader còn sống, class có thể phải nạp lại, phá vỡ tính nhất quán của static state, object identity và native interactions.
- **Không có Java SE method `Class.unload()` hay `loader.unloadClass(name)`** cho ứng dụng gọi để buộc dỡ một class riêng trong loader còn sống.

### Loader nhận yêu cầu không nhất thiết là defining loader

```java
Class<?> stringType = pluginLoader.loadClass("java.lang.String");
System.out.println(stringType.getClassLoader() == null);
```

Đây là **đoạn minh họa**, giả định `pluginLoader` tồn tại và method xử lý checked exception. Trong Java SE thông thường, stdout là `true`: `String` được bootstrap định nghĩa dù lời yêu cầu khởi đầu ở plugin loader. Việc đóng plugin loader không làm `String` bị unload.

Với `plugin.Widget` thực sự do `PluginLoader` định nghĩa, VM mới xét điều kiện thu hồi **PluginLoader** để quyết định class có thể unload.

**Type identity** trong JVM phụ thuộc vào **binary class name + defining class loader**. Vì vậy hai loader độc lập có thể định nghĩa hai class cùng tên nhưng tạo hai runtime types khác nhau. Hot reload bằng loader mới có thể khiến bản v1 và v2 **cùng tồn tại**, nếu loader v1 chưa đủ điều kiện thu hồi.

## 5. Ví dụ Java 17+ có stdout đã kiểm chứng

Ví dụ này cố ý **giữ** các reference đến instance/class/loader ngay cả sau close, nhằm chứng minh close không xóa class cũ. Không dùng ví dụ này để tuyên bố đã đo class unloading.

### Cấu trúc project

```text
loader-lifetime-demo/
├── src/plugin/
│   ├── Alive.java
│   └── Later.java
├── LoaderLifetimeDemo.java
├── plugin-classes/       (output class của plugin)
└── host-classes/         (output class của host)
```

Tạo hai thư mục output nếu chưa có và chạy lệnh từ `loader-lifetime-demo`. Khi chạy host, **không đưa `plugin-classes` vào `-cp`**.

### Class plugin đã nạp trước close

`src/plugin/Alive.java`:

```java
package plugin;

public final class Alive {
    private final int value = 41;

    public int plusOne() {
        return value + 1;
    }
}
```

`src/plugin/Later.java`:

```java
package plugin;

public final class Later {
    public static String text() {
        return "late";
    }
}
```

`Alive` sẽ được tìm và tạo instance trước close. File `Later.class` tồn tại trên đĩa nhưng chưa được yêu cầu load.

### Host và URLClassLoader

`LoaderLifetimeDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.Method;

public class LoaderLifetimeDemo {
    public static void main(String[] args) throws Exception {
        URL directory = Path.of("plugin-classes").toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[]{directory},
                ClassLoader.getPlatformClassLoader());

        Class<?> type = loader.loadClass("plugin.Alive");
        Object instance = type.getConstructor().newInstance();
        Method method = type.getMethod("plusOne");

        System.out.println("plugin defining loader="
                + (type.getClassLoader() == loader));
        System.out.println("before close=" + method.invoke(instance));

        loader.close();

        System.out.println("after close=" + method.invoke(instance));
        System.out.println("cached class="
                + (loader.loadClass("plugin.Alive") == type));

        try {
            loader.loadClass("plugin.Later");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("unloaded? no; new class not found");
        }

        System.out.println("instance still alive="
                + (instance.getClass() == type));
    }
}
```

Parent ở đây là platform class loader: nó có thể giúp tìm core platform classes nhưng không có `plugin.Alive`/`plugin.Later`. Nhờ vậy `Alive` được chính child URL loader định nghĩa.

### Biên dịch/chạy (JDK 17+)

```bash
javac --release 17 -d plugin-classes src/plugin/Alive.java src/plugin/Later.java
javac --release 17 -d host-classes LoaderLifetimeDemo.java
java -cp host-classes LoaderLifetimeDemo
```

Stdout chính xác đã được biên dịch/chạy xác minh:

```text
plugin defining loader=true
before close=42
after close=42
cached class=true
unloaded? no; new class not found
instance still alive=true
```

### Giải thích dòng output

1. `plugin defining loader=true`: plugin class do URL loader tạo/define thật.
2. `before close=42`: instance hoạt động trước close.
3. `after close=42`: instance và method sẵn có vẫn chạy được sau close.
4. `cached class=true`: loader tra cứu lại class đã nạp; nó không phải nạp định nghĩa mới từ URL.
5. `unloaded? no; new class not found`: class `Later` chưa từng load, nên sau close không có nguồn URL để tìm class mới; parent cũng không có class ấy. Đây **không phải chứng cứ** `Alive` đã unload.
6. `instance still alive=true`: object và `Class<?>` vẫn hiện diện, đồng thời các biến `loader`, `type`, `instance`, `method` còn tham chiếu trong code.

**Kết luận của test giới hạn:** close không tương đương unload. Test **không hề buộc hoặc chứng minh** có sự kiện class unloading.

## 6. Object, Class<?> và ClassLoader liên kết tới nhau

Một object instance có runtime class riêng; `instance.getClass()` trả `Class<?>` mirror của định nghĩa đó; `Class.getClassLoader()` cho biết **defining loader** (có thể `null` cho bootstrap). Nếu host còn giữ instance hoặc mirror của plugin, JVM phải duy trì runtime type tương ứng.

Ví dụ đường retention: `host registry → instance → class → plugin defining loader`. Tuy nhiên **mất một reference** tới instance không đủ chứng minh không còn đường từ GC roots; bài về quan hệ `Class`–instance–loader đi sâu vào graph và type identity.

## 7. WeakReference: quan sát, không ép unload

`WeakReference<ClassLoader>` **không giữ loader sống bằng tham chiếu mạnh**. Nó có thể giúp quan sát loader còn được GC giữ hay referent đã bị clear; nhưng **không chứng minh** unloading qua một lần chạy.

Chương trình minh họa Java 17 có thể biên dịch nếu `plugin-classes/plugin/Alive.class` đã tạo ở demo trên:

```java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class UnloadProbe {
    static WeakReference<ClassLoader> runAndRelease(URL[] urls)
            throws Exception {
        URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader());

        try {
            Class<?> type = loader.loadClass("plugin.Alive");
            Object instance = type.getConstructor().newInstance();
            type.getMethod("plusOne").invoke(instance);
        } finally {
            loader.close();
        }

        return new WeakReference<>(loader);
    }

    public static void main(String[] args) throws Exception {
        URL[] urls = {
            Path.of("plugin-classes").toUri().toURL()
        };

        WeakReference<ClassLoader> ref = runAndRelease(urls);
        System.gc(); // Chỉ là GC request/hint.

        System.out.println("loader cleared? " + (ref.get() == null));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -d host-classes UnloadProbe.java
java -cp host-classes UnloadProbe
```

Output **không được bảo đảm**: có thể in `loader cleared? true` hoặc `loader cleared? false`.

Tại sao?

- `System.gc()` không cam kết sẽ chạy và dọn loader vào thời điểm kiểm tra.
- Loader có thể còn được giữ bởi reference trong JVM, task/registry khác, hoặc chưa đủ điều kiện thu hồi.
- JIT và runtime liveness có thể ảnh hưởng thời điểm các local references được coi là cần thiết.
- Ngay cả khi weak referent đã clear, đó **không phải phép đo trực tiếp** mọi bytes class metadata/metaspace hoặc mọi OS handles đã trả về.

### Cách diễn giải đúng

| Quan sát | Điều kết luận được | Điều không thể khẳng định |
| --- | --- | --- |
| `ref.get() != null` | Loader chưa bị clear ở thời điểm đọc | Không chắc có leak; có thể GC chưa xử lý |
| `ref.get() == null` | Weak referent đã bị clear qua reference processing hoặc do chính code clear | Không khẳng định mọi metaspace/native memory đã trả OS |
| Không có class unload log | Chưa quan sát unload event tương ứng | Không chứng minh close sai |
| Heap giảm sau GC | Heap objects có thay đổi theo thống kê đang đo | Không chứng minh class loader/class metadata đã unload |

Để kiểm tra class unloading, phối hợp **loader liveness**, **heap retaining-path analysis** và **VM class unloading events/stats** thay vì chỉ WeakReference.

## 8. Heap, metaspace và JAR handles không cùng một tài nguyên

| Loại tài nguyên | Ví dụ | Cơ chế xử lý chính |
| --- | --- | --- |
| **Java heap** | Instances, arrays, `URLClassLoader` object, collection/cache | GC khi objects không còn được giữ sống |
| **Class metadata/metaspace** | Metadata của các class do loader định nghĩa, trên HotSpot | JVM class unloading và quản lý metaspace |
| **JAR/file handles** | `plugin.jar` do `URLClassLoader` mở | `URLClassLoader.close()` theo contract |
| **Network/database/file của plugin** | `Socket`, DB connection, `FileInputStream` plugin tự mở | Plugin phải close theo API của tài nguyên |
| **Threads/executors** | Worker, scheduler, task queue | Cancel/stop/shutdown/await theo lifecycle |
| **JNI/native resources** | Native allocations, JNI global refs, library state | JNI/native subsystem cleanup; không dựa vào class unload tự động |
| **JIT/code cache** | Compiled native instructions và VM caches | VM quản lý, không tương đương `Runtime.freeMemory()` |

Metaspace là thuật ngữ/cơ chế phổ biến của **HotSpot**; Java SE không bắt buộc mọi JVM phải sử dụng cách tổ chức bộ nhớ giống HotSpot.

Ngay cả nếu class metadata được unload, process RSS hoặc số committed/reserved memory có thể **không giảm ngay**, do VM còn giữ memory để dùng lại. Vì vậy:

**`Runtime.getRuntime().freeMemory()` tăng/giảm không phải phép đo trực tiếp class unloading.** Nó liên quan heap, không thay thế classloader statistics, GC logs và kiểm tra retaining paths.

## 9. Cách đo class unloading trên Java 17+

Với HotSpot/OpenJDK tương thích, có thể bật unified logging:

```bash
java -Xlog:class+load=info,class+unload=info -cp host-classes LoaderLifetimeDemo
```

Giải thích:

- `class+load` ghi class-loading events.
- `class+unload` ghi events khi JVM thực sự unload class.
- Demo ngắn có thể **không in event unload** vì references còn sống và GC chưa tiến hành.
- Không dùng “đã thấy class+load” làm bằng chứng “đã unload”.
- Các tag/logging capabilities và format cụ thể phụ thuộc bản JVM.

Nếu đang có một JVM server chạy lâu, công cụ `jcmd` có thể hỗ trợ:

```bash
jcmd <PID> VM.classloader_stats
```

Đây là **cú pháp minh họa**: thay `<PID>` bằng process ID thật; công cụ và lệnh chỉ có khi bản JDK/runtime hỗ trợ và bạn có quyền attach tương ứng.

Nên kết hợp:

1. **Classloader statistics:** số loaders/classes, metadata/metaspace usage trước và sau nhiều lần deploy.
2. **Heap dump:** tìm **retaining path từ GC root tới PluginClassLoader** hoặc instance/class.
3. **Thread inspection:** thread pool, scheduler, TCCL, ThreadLocal đang giữ loader nào.
4. **JFR (nếu phù hợp):** class-loading/unloading events với recording settings thích hợp.
5. **OS file handles:** xác minh file/JAR còn bị thành phần nào mở.
6. **GC logs/metrics:** hiểu thời điểm thu hồi và phân biệt class unloading với object collection.

Đừng để test quan sát tự tạo leak: một static debug list chứa `Class<?>` hay loader sẽ làm class cũ khó được thu hồi.

## 10. Mất references trong plugin host: các nguồn leak thường gặp

Những nguồn tham chiếu thường gặp là host static registries/caches, listener/callback, reflection metadata, worker threads (TCCL và `ThreadLocal`), pending jobs, `ServiceLoader` và framework registrations. Mỗi nguồn phải được gỡ tại owner thực sự; gọi `close()` không tự dọn chúng.

Hãy điều tra `path to GC roots` của **loader generation cũ** và đối chiếu vòng đời plugin. Những bài cache, thread và listener trong chương cung cấp cách kiểm tra chuyên sâu.

## 11. Lifecycle đúng để plugin có cơ hội được unload

**Quiesce → Stop/clean up → Close URL loader → Release references → Observe.** Chặn tác vụ mới, xử lý công việc đang chạy và unregister callback trước khi đóng loader; dọn `ThreadLocal` trên đúng thread, đóng resource riêng, sau đó bỏ registry/caches của generation cũ.

Trình tự này giúp loader **có thể đủ điều kiện reclaim** khi toàn bộ retaining graph được cắt. Không có lời hứa JVM sẽ unload trong một chu kỳ GC nhất định.

## 12. Hot reload: tạo loader mới, không “reset loader cũ”

Đổi file `.class` hoặc JAR trên đĩa không cập nhật định nghĩa runtime đã được loader cũ nạp. Để dùng bytecode mới cho cùng binary name, ứng dụng thường dùng **defining loader mới**, chuyển traffic sang generation mới rồi retire generation cũ.

Các instance cũ vẫn gắn với runtime class cũ; chúng không tự đổi kiểu chỉ vì loader hoặc file nguồn đã đóng/thay.

## 13. Bảng tình huống và sai lầm phổ biến

| Tình huống | Kết luận đúng |
| --- | --- |
| `object = null`, heap chưa giảm | Có thể vẫn còn references hoặc chưa GC; không đồng nghĩa loader leak |
| `loader.close()` thành công, method plugin vẫn chạy | Đúng contract; close không tự unload object/class |
| Sau close, `loadClass` cho class chưa nạp thất bại | Loader đã đóng nguồn URL cho class mới; **không** chứng minh class cũ unload |
| JAR vẫn bị khóa dù close | Có thể handles do thành phần khác giữ hoặc close gặp I/O error |
| `System.gc()` chạy, WeakReference vẫn non-null | Chưa đủ kết luận; tìm strong retaining paths và GC timing |
| WeakReference cleared nhưng RSS cao | JVM có thể giữ committed native/metaspace memory để tái sử dụng |
| Metaspace tăng qua hàng trăm lần reload | Nghi classloader leak hoặc unloading chưa theo kịp; đo loaders/classes/roots |
| Object plugin mất nhưng `Class<?>` ở host cache còn | `Class<?>` vẫn có thể giữ defining loader sống |
| Loader cũ và loader mới chứa class cùng tên | Khác runtime types nếu được hai loaders khác nhau define |
| Module/plugin interface duplicate gây `ClassCastException` | Chia sẻ API qua parent loader, không trông chờ close/GC sửa |
| Object Java được thu hồi nhưng socket không đóng đúng lúc | Quản lý external resources bằng explicit close/stop |
| Unloading không có log trong demo ngắn | Không bắt buộc xảy ra; không có event ≠ close thất bại |

## 14. Hỏi–đáp và bài tập tự kiểm tra

**Q1.** `Object a = new Object(); Object b = a; a = null;` Object ban đầu đã đủ điều kiện GC chưa?

*Trả lời:* Khi `b` còn là live strong reference, không thể nói object đã mất mọi reference. `a = null` chỉ xóa một đường tham chiếu.

**Q2.** Vì sao `method.invoke(instance)` sau `loader.close()` vẫn thành công trong demo?

*Trả lời:* Class, method và instance đã được nạp/tạo; close không hủy chúng hay xóa bytecode runtime.

**Q3.** Nếu `loader.loadClass("plugin.Later")` sau close ném `ClassNotFoundException`, có thể kết luận `plugin.Alive` đã unload?

*Trả lời:* Không. `Later` là class chưa từng load, còn `Alive` vẫn được giữ và sử dụng. Không tìm được class mới chỉ chứng tỏ URL lookup đã đóng.

**Q4.** `loader = null; System.gc();` có đảm bảo class unloading?

*Trả lời:* Không. Registry, `Class<?>`, instances, TCCL, ThreadLocal hoặc native references khác có thể còn giữ loader. GC/unloading cũng không có deadline.

**Q5.** Static map trong class do host system loader define đang giữ `plugin.Entry.class`. Làm sao sửa?

*Trả lời:* Xóa entry liên quan ở host static cache/registry khi dừng deployment, sau đó xác nhận không còn retaining references tới loader cũ.

**Q6.** Vì sao JVM không thể unload class khi defining loader vẫn potentially reachable?

*Trả lời:* Loader có thể được dùng để resolve/load class tham chiếu class cũ. Tự ý unload sẽ tạo nguy cơ class reloading làm thay đổi identity, static state và side effects, trái yêu cầu transparency của JLS.

**Q7.** `String.class` có bị unload do đóng một plugin loader con không?

*Trả lời:* Không. `String` thường do bootstrap loader định nghĩa; JLS không cho unload bootstrap-defined classes.

**Q8.** WeakReference tới loader đã được clear có khẳng định toàn bộ metaspace đã trả về OS?

*Trả lời:* Không. Đây chỉ là tín hiệu referent đã bị clear; class unloading/committed memory cần đo bằng JVM diagnostics riêng.

**Q9.** Vì sao `Runtime.freeMemory()` không nên dùng để kết luận class unloading?

*Trả lời:* Nó phản ánh trạng thái heap, không trực tiếp đo HotSpot metaspace hoặc events unload.

**Q10.** Plugin JAR muốn bị xóa/cập nhật trên Windows. Đã close URLClassLoader có đủ chưa?

*Trả lời:* Close là bước quan trọng giải phóng file/JAR handles do loader mở; nhưng các streams/handles khác cũng có thể đang giữ file. Stop work, close owned resources và điều tra OS locks nếu vẫn không xóa được.

**Q11.** Một thread pool worker giữ TCCL = oldPluginLoader sau undeploy. Hậu quả?

*Trả lời:* Nó có thể giữ old loader sống, gây classloader leak và làm service discovery của tác vụ khác dùng sai namespace. Phải restore trong worker bằng `finally`.

**Q12.** Sau reload, cùng `plugin.Widget` có hai phiên bản và xảy ra `ClassCastException`. Vì sao?

*Trả lời:* Class identity gồm binary name + defining loader. Hai loaders define hai types riêng. Dùng shared interfaces/DTO ở parent để host và plugin giao tiếp qua contract chung.

## 15. Checklist khi chuẩn bị dỡ plugin

Trước khi retire, xác định defining loader, bảo đảm API chung vẫn dùng một runtime type nhất quán; chặn new work, drain tasks, unregister listeners và caches; dọn TCCL/`ThreadLocal` tại đúng threads; đóng I/O handles và URL loader; bỏ strong roots giữ generation cũ.

Cuối cùng theo dõi log/heap retaining path qua nhiều chu kỳ để kiểm tra điều kiện unload. Không biến việc `System.gc()` trả về thành điều kiện pass.

## Kết luận

**Mất tham chiếu object** là câu chuyện **reachability**; **`URLClassLoader.close()`** là câu chuyện **đóng class/resource search path và file handles của loader**; **class unloading** là câu chuyện **JVM có thể thu hồi định nghĩa class khi defining loader đủ điều kiện GC**. Không có mũi tên suy diễn bắt buộc từ một sự kiện sang sự kiện tiếp theo.

Trong hệ thống plugin/hot reload, phương pháp bền vững là **stop → unregister và cleanup threads/resources → restore context → close loader → release strong references → quan sát GC/unloading nếu cần**. Đừng lấy một lần `System.gc()`, một biến local được gán `null`, hay một JAR đã được close thành bằng chứng class metadata lập tức biến mất.

**Tài liệu chuẩn Java SE 17:**

- [`URLClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, class/resource đã nạp và file/JAR handles.
- [JLS 17 `12.7` — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): quy tắc về defining loader có thể được GC thu hồi.
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass` và parent delegation.
- [`WeakReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability và clearing.
- [`System` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `gc()` và giới hạn của việc yêu cầu GC.
- [Java 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): chẩn đoán các JVM đang chạy khi môi trường hỗ trợ.
