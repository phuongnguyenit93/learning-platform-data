# Quan sát class unloading và tránh kết luận từ một lần gọi `System.gc()`

## 1. Mục tiêu và bản chất của class unloading

**Class unloading** (dỡ lớp) là việc JVM có thể loại bỏ định nghĩa lớp/giao diện đã nạp cùng metadata liên quan khi chúng không còn cần thiết. Đây là một hoạt động quản lý vòng đời lớp và bộ nhớ, khác với **class loading** (nạp lớp), **linking** (liên kết), **initialization** (khởi tạo tĩnh) và việc thu gom các object thông thường trên heap.

Trong Java, danh tính của một lớp không chỉ là tên nhị phân như `lesson.UnloadTarget`, mà còn gắn với **defining class loader** đã định nghĩa lớp đó. Hai class loader độc lập có thể định nghĩa hai lớp cùng tên nhưng chúng vẫn là hai kiểu khác nhau ở runtime. Khi làm ứng dụng có plugin, hot reload, redeploy hoặc tạo nhiều class loader động, việc loader cũ có được thu hồi hay không quyết định liệu các lớp do nó định nghĩa có thể được dỡ hay không.

Các điều kiện và giới hạn cần nhớ:

- **Một object của lớp đã nạp còn sống** có thể giữ lớp và defining loader còn reachable. Một tham chiếu mạnh trực tiếp tới `Class<?>`, `Method`, `Constructor`, instance, loader, hoặc cấu trúc runtime liên quan cũng có thể ngăn loader được thu hồi.
- Với lớp được định nghĩa bởi **class loader do ứng dụng tạo**, JVM chỉ có thể dỡ lớp khi điều kiện về khả năng thu hồi defining loader thỏa mãn. Chỉ gọi `close()` trên `URLClassLoader` là đóng tài nguyên như JAR/file handle; **không phải lệnh unload lớp**.
- Lớp do bootstrap loader định nghĩa thường tồn tại theo vòng đời JVM; không nên dùng ví dụ `java.lang.String` để kiểm chứng unload của một plugin.
- Trạng thái “đã hết tham chiếu mạnh từ ứng dụng” chỉ làm loader **có thể** được thu hồi. Thời điểm GC, thời điểm unloading và việc trả lại bộ nhớ vật lý cho hệ điều hành phụ thuộc JVM/collector/cấu hình.

Một đường giữ tham chiếu thường gặp:

```text
GC root
  └── static cache thuộc ứng dụng/loader sống lâu
        └── instance của plugin
              └── lớp plugin / defining class loader
```

Nếu cache, thread đang chạy hoặc thread context class loader vẫn giữ plugin, vòng đời của plugin **chưa kết thúc về mặt reachability** dù mã ứng dụng đã “undeploy” nó.

## 2. Vì sao một lần `System.gc()` không chứng minh được gì?

`System.gc()` là **lời đề nghị JVM nỗ lực thực hiện garbage collection**, không phải cam kết “GC xong, mọi lớp đủ điều kiện đã unload”. Đặc tả API không bảo đảm thu hồi một số object nhất định, không bảo đảm một `Reference` cụ thể được clear, cũng không bảo đảm hoàn tất ở thời điểm trả về. HotSpot có thể được cấu hình bỏ qua explicit GC (ví dụ `-XX:+DisableExplicitGC`). Cơ chế và thời điểm xử lý class unloading còn phụ thuộc garbage collector và chu kỳ thu gom tương ứng.

Phải phân biệt bốn câu:

1. **“Đã gọi `System.gc()`”**: chỉ biết code thực thi lời đề nghị.
2. **“Đã có GC”**: cần GC log/JFR hoặc bằng chứng quan sát thực sự; vẫn **không đồng nghĩa** một class loader đã chết.
3. **“Class loader không còn strong reachability”**: là tiền đề để loader có thể bị GC; không đồng nghĩa JVM đã dỡ lớp ngay lúc đó.
4. **“Đã có class unload”**: cần sự kiện unloading, hoặc tín hiệu trực tiếp khác có phạm vi diễn giải rõ ràng.

Do đó hai kết luận sau đều sai:

- “Gọi `System.gc()` một lần mà không thấy unload, vậy chắc chắn bị leak.”
- “Gọi `System.gc()` xong heap/metaspace giảm, vậy lớp plugin X chắc chắn đã được dỡ.”

Heap object collection, class unloading và giảm `metaspace committed` là các hiện tượng liên quan nhưng **không phải ba phép đo thay thế cho nhau**. Sau unloading, bộ cấp phát metaspace còn có thể giữ phần bộ nhớ để tái sử dụng; mức committed/reserved không nhất thiết giảm ngay.

## 3. Quan sát bằng những tín hiệu nào?

Trên **HotSpot JDK 17+**, sử dụng phối hợp log sự kiện, thống kê JVM và kiểm tra tham chiếu. Không áp dụng nguyên xi cú pháp cờ cho mọi bản triển khai JVM.

| Tín hiệu | Nó xác nhận được gì? | Giới hạn cần ghi trong kết luận |
|---|---|---|
| Log `-Xlog:class+unload=info` xuất hiện tên lớp plugin | Bằng chứng trực tiếp JVM đã ghi nhận sự kiện unload lớp đó | Phải bật log trước thời điểm sự kiện; thiếu dòng log chưa tự động chứng minh leak |
| `WeakReference<ClassLoader>.get() == null` | Tham chiếu yếu tới loader đã được GC clear; hữu ích để kiểm tra loader không còn được giữ sống | Không thay cho timestamp/sự kiện unload của từng lớp; một kết quả chưa clear không chứng minh leak |
| `ClassLoadingMXBean.getUnloadedClassCount()` tăng | Có các lớp được JVM ghi nhận là đã unload kể từ lúc khởi động | Đếm trên **toàn JVM**, không khẳng định chính lớp đang khảo sát |
| `jcmd <pid> VM.classloader_stats` ở nhiều thời điểm | Thống kê class loader/lớp tại từng thời điểm khảo sát | Snapshot; khác biệt có thể do đồng thời nạp thêm loader/lớp |
| `jcmd <pid> VM.metaspace` và GC log | Xu hướng vùng metadata, thời điểm GC và áp lực bộ nhớ | Dung lượng không đổi hoặc giảm không đủ để kết luận một lớp cụ thể đã unload |

Để ghi log từ lúc khởi chạy:

```bash
java -Xlog:class+unload=info,gc*=info -cp . UnloadingProbe
```

Với ứng dụng thật có nhiều log, có thể chuyển sang file:

```bash
java -Xlog:class+unload=info,gc*=info:file=class-gc.log:time,uptime,level,tags -jar app.jar
```

Giá trị của log nằm ở **sự kiện và mốc thời gian thực tế**, không phải suy đoán “sau khi chạy câu lệnh GC”. Các lệnh `jcmd` yêu cầu JDK và quyền attach phù hợp; có thể kiểm tra lệnh JVM hỗ trợ bằng `jcmd <pid> help`.

## 4. Thí nghiệm Java 17+: nạp lớp qua loader riêng rồi quan sát

Thí nghiệm dùng hai file Java và thư mục chứa plugin được biên dịch riêng. Mục tiêu là tạo điều kiện để loader có thể được thu hồi, sau đó đọc bằng chứng. Kết quả thu hồi/unload **không được ép phải xảy ra trong mọi lần chạy**.

### Bước 1: tạo lớp plugin

File **`plugin-src/lesson/UnloadTarget.java`**:

```java
package lesson;

public class UnloadTarget {
    public static String answer() {
        return "ready";
    }
}
```

### Bước 2: tạo chương trình điều khiển

File **`UnloadingProbe.java`**, nằm tại thư mục làm việc gốc, **không** nằm trong `plugin-classes`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadingProbe {
    private static WeakReference<ClassLoader> loadOnce() throws Exception {
        URL pluginDirectory =
                Path.of("plugin-classes").toAbsolutePath().toUri().toURL();

        // Parent platform loader không thấy class plugin trong plugin-classes.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginDirectory },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> pluginClass =
                    Class.forName("lesson.UnloadTarget", true, loader);
            Object result = pluginClass.getMethod("answer").invoke(null);
            System.out.println("Plugin: " + result);

            // Chỉ trả về weak reference: không giữ Class, instance,
            // Method hay loader bằng strong reference ở phương thức gọi.
            return new WeakReference<>(loader);
        } // close() giải phóng tài nguyên; không tự unload class.
    }

    public static void main(String[] args) throws Exception {
        ClassLoadingMXBean counter =
                ManagementFactory.getClassLoadingMXBean();
        long unloadedBefore = counter.getUnloadedClassCount();

        WeakReference<ClassLoader> loaderRef = loadOnce();

        for (int attempt = 0;
             attempt < 20 && loaderRef.get() != null;
             attempt++) {
            System.gc(); // Đề nghị, KHÔNG phải cam kết.
            byte[] temporary = new byte[256 * 1024];
            temporary[0] = (byte) attempt;
            Thread.sleep(100);
        }

        System.out.println(
                "Loader weak reference cleared: " + (loaderRef.get() == null));
        System.out.println(
                "JVM-wide unloaded classes delta: "
                + (counter.getUnloadedClassCount() - unloadedBefore));
    }
}
```

**Giải thích quyết định thiết kế:**

- `plugin-classes` phải nằm ngoài classpath của chương trình điều khiển, để `lesson.UnloadTarget` thực sự được định nghĩa bởi `URLClassLoader` riêng. Nếu lớp được parent loader nạp trước, thí nghiệm không còn đo đúng loader mong muốn.
- `loadOnce()` tách thành một phương thức riêng để các biến cục bộ `pluginClass`, reflection result và loader hết phạm vi; JVM/JIT có quyền giữ một số tham chiếu tạm thời lâu hơn dự đoán, nên vẫn phải quan sát thực nghiệm.
- `WeakReference` không giữ loader sống bằng strong reference. `URLClassLoader.close()` chỉ đóng resource. Vòng lặp cho JVM nhiều **cơ hội** GC hơn một lần gọi, nhưng số lần lặp cũng không biến unloading thành việc bảo đảm.
- Bộ đếm từ `ClassLoadingMXBean` là toàn JVM. Ngoài plugin, JVM có thể load/unload lớp khác; vì vậy delta lớn hơn 0 là dấu hiệu hỗ trợ, **không nhận dạng lớp cụ thể**.
- Không gọi `System.exit()` để “xác minh” vì khi process kết thúc mọi bộ nhớ process được OS thu hồi; đó không phải class unloading **trong JVM đang chạy**.

### Bước 3: biên dịch và chạy

Tạo trước các thư mục `plugin-src/lesson` và `plugin-classes`. Từ thư mục chứa hai file nêu trên, chạy trên JDK 17+:

```bash
javac -d plugin-classes plugin-src/lesson/UnloadTarget.java
javac UnloadingProbe.java
java -Xlog:class+unload=info -cp . UnloadingProbe
```

**Lưu ý:** Không thêm `plugin-classes` vào `-cp` của `UnloadingProbe`; chương trình chủ chỉ cần `.`. Trên Windows, dấu phân tách classpath có thể khác khi dùng nhiều entry, nhưng ví dụ chỉ dùng một entry nên `-cp .` dùng được trên cả Windows và Unix.

Output ứng dụng **chắc chắn bắt đầu bằng**:

```text
Plugin: ready
```

Hai dòng ứng dụng cuối có **giá trị phụ thuộc lần chạy**:

```text
Loader weak reference cleared: true
JVM-wide unloaded classes delta: 1
```

Đây là **một ví dụ output có thể xảy ra**, **không phải output được bảo đảm**. Giá trị đầu có thể là `false`; số delta có thể bằng 0 hoặc lớn hơn 1. Nếu có sự kiện dỡ lớp, log HotSpot có thể chứa dòng có tag `[class,unload]` và tên `lesson.UnloadTarget`; prefix/timestamp/địa chỉ nội bộ là động. Log này là bằng chứng sát với câu hỏi “lớp plugin có unload không?” hơn việc thấy `System.gc()` đã được gọi.

Chạy lại với cấu hình HotSpot bỏ qua explicit GC để quan sát khác biệt về hành vi; đây là **thử nghiệm so sánh**, không phải cách buộc JVM unload hay chứng minh leak:

```bash
java -XX:+DisableExplicitGC -Xlog:class+unload=info -cp . UnloadingProbe
```

Ngay cả khi explicit GC bị bỏ qua, **GC tự nhiên do áp lực bộ nhớ vẫn có thể xảy ra**. Không dùng việc không thấy một dòng unload ở lần chạy này làm kết luận cuối.

## 5. Cách diễn giải kết quả theo tình huống

**Tình huống A — Có log unload cho `lesson.UnloadTarget`.** Có thể kết luận JVM đã ghi nhận unload lớp thử nghiệm. Nên lưu thời điểm, cờ JVM, log tương ứng và loader đã nạp lớp để có thể lặp lại/khoanh vùng.

**Tình huống B — `loaderRef.get() == null` nhưng chưa thấy dòng unload.** Đây là tín hiệu loader đã được GC clear qua weak reference. Kiểm tra log có bật đủ sớm/đúng tag hay không, thời gian quan sát và JVM đang dùng. Đừng suy ra “đã có log unload” nếu thực tế không có.

**Tình huống C — Loader reference vẫn chưa clear sau vòng lặp.** Chưa đủ cơ sở để gắn nhãn leak. Có thể chưa có chu kỳ GC phù hợp, explicit GC bị bỏ qua, JIT còn giữ tham chiếu tạm thời, hoặc có strong reference thật sự. Tăng cửa sổ quan sát và xác minh đồ thị tham chiếu trước khi chẩn đoán.

**Tình huống D — Delta bộ đếm dương nhưng không có log lớp cần quan sát.** Chỉ có thể khẳng định có **một số lớp nào đó** trong process unload. Không được gán nhầm kết quả toàn JVM cho plugin X.

**Tình huống E — Metaspace committed chưa giảm.** Không đủ chứng minh classes không unload. Bộ cấp phát có thể giữ chunk để tái sử dụng, và các loader khác có thể đang nạp class mới đồng thời.

## 6. Quy trình theo dõi ở ứng dụng plugin/redeploy thực tế

1. **Đặt giả thuyết chính xác.** Ví dụ: “Sau khi plugin phiên bản A dừng và rời cache, loader A không còn root giữ sống; lớp `com.example.plugin.Handler` dự kiến có thể unload sau một số chu kỳ GC”.
2. **Ghi baseline trước hành động:** JVM/JDK version, collector, cờ GC, thời điểm, log class unload và snapshot loader/metaspace; đặt tên hoặc ghi lại danh tính loader thay vì chỉ dựa vào class name.
3. **Thực hiện thao tác vòng đời:** ngừng task/timer, unregister listener/MBean/driver, giải phóng cache, đóng tài nguyên loader rồi bỏ strong reference. Kiểm tra xem phần mềm có thực sự giải phóng loader cũ không.
4. **Quan sát theo khoảng thời gian và nhiều chu kỳ GC thực tế** trong điều kiện tải có kiểm soát; thu log unload và snapshot tại ít nhất các mốc trước tải plugin, sau unload logic, sau giai đoạn quan sát. Không dùng riêng một lần `System.gc()` làm ranh giới.
5. **Đối chiếu ít nhất hai nguồn bằng chứng độc lập:** log unload có class/loader mục tiêu; weak reference loader hoặc phân tích GC roots; thống kê toàn JVM chỉ là dữ liệu bối cảnh.
6. **Nếu có dấu hiệu giữ loader lâu bất thường**, truy ngược từ GC roots tới loader/plugin. So sánh các chu kỳ load→use→dispose lặp lại để phân biệt một vòng đời dài hợp lệ với tăng trưởng tích lũy.

Các lệnh chẩn đoán HotSpot thường dùng khi ứng dụng còn chạy:

```bash
jcmd
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> help
```

Lệnh `jcmd` xem snapshot, không “kích hoạt class unloading”. Trong container, attach có thể cần quyền cùng user/JVM namespace và công cụ JDK hiện diện; hãy lưu context cùng kết quả.

Với chương trình chạy lâu, có thể lấy thông tin tải lớp thông qua `ManagementFactory.getClassLoadingMXBean()`:

- `getLoadedClassCount()`: số lớp hiện được load (snapshot).
- `getTotalLoadedClassCount()`: tổng lớp từng được load kể từ lúc JVM khởi động.
- `getUnloadedClassCount()`: tổng lớp từng được unload kể từ lúc JVM khởi động.

Không trừ `totalLoaded - unloaded` để “xác định loader X” và không coi xu hướng metadata tăng là leak nếu không kiểm soát lưu lượng nạp lớp, số plugin và chu kỳ GC.

## 7. Vì sao plugin đã đóng vẫn không unload?

Đóng loader không xóa **host references**. Khi không thấy class unload event, kiểm tra `path to GC roots` qua static caches/`Class<?>`, callbacks/listeners, `ServiceLoader` providers, thread TCCL/`ThreadLocal`, pending executor tasks và registries của JMX/JDBC/logging.

Nhưng **không thấy sự kiện unload không chứng minh leak**: VM có thể chưa chọn thực hiện unloading. Phải đối chiếu loader generations, event logs và heap retaining paths theo nhiều chu kỳ hoạt động.

## 8. Những kết luận cần tránh và cách nói đúng

| Suy luận vội | Kết luận có cơ sở hơn |
|---|---|
| “`System.gc()` trả về nên lớp đã unload.” | “Đã yêu cầu GC; cần sự kiện class unloading hoặc bằng chứng reachability/loader riêng.” |
| “Một lần `System.gc()` không có event, chắc chắn memory leak.” | “Trong cửa sổ quan sát đó chưa ghi nhận event; cần khảo sát GC/roots và lặp lại.” |
| “`URLClassLoader.close()` dỡ lớp ngay.” | “`close()` đóng resource của loader; tham chiếu và GC quyết định khả năng thu hồi.” |
| “Weak reference chưa null nghĩa là JVM không unload được.” | “Loader còn được quan sát là reachable/chưa bị clear ở thời điểm đọc; chưa biết nguyên nhân.” |
| “`unloadedClassCount` tăng nên plugin vừa được dỡ.” | “Số lớp unload toàn JVM tăng; cần nhận dạng chính lớp/loader qua log hoặc bằng chứng bổ sung.” |
| “Metaspace không giảm tức là classes còn sống.” | “Metaspace sử dụng/commit có thể không giảm tức thời hoặc bị lớp mới bù vào.” |

Một báo cáo quan sát tốt nên ghi rõ: **JDK/JVM, collector và flags; tên lớp + defining loader; thao tác release; mốc thời gian; số lần/chu kỳ GC thực tế; log `class+unload`; trạng thái weak reference; snapshot stats; phần chưa thể kết luận**.

## 9. Tự kiểm tra

1. Tại sao cùng binary name có thể được hai loader nạp thành hai runtime type khác nhau?
2. Tại sao việc ngắt sử dụng plugin và gọi `close()` chưa đủ để khẳng định unload?
3. Nếu counter unload tăng từ 100 lên 105 nhưng không thấy event plugin, có thể nói gì?
4. Nếu sau lần gọi `System.gc()` đầu tiên `WeakReference` vẫn chưa clear, cần kiểm tra những giả thuyết nào trước khi nói “leak”?
5. Bằng chứng nào đủ cụ thể hơn cho câu hỏi “`lesson.UnloadTarget` có unload hay chưa”: GC log chung, thay đổi metaspace, hay log `class+unload` có tên lớp?

**Đáp án định hướng:** (1) Kiểu runtime được xác định bởi tên và defining loader; (2) strong references còn có thể giữ loader và `close` không unload; (3) chỉ biết toàn JVM có 5 lớp unload; (4) thời điểm/kiểu GC, JVM flags, tham chiếu mạnh, stack/JIT/debugger; (5) event `class+unload` mang tên lớp quan tâm, kết hợp nhận dạng loader khi cần.

## Tài liệu chuẩn để đối chiếu

- [Java SE 17 — `System.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): tài liệu nêu rõ giới hạn bảo đảm của yêu cầu GC.
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): bộ đếm loaded/unloaded toàn JVM.
- [JDK 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.metaspace` và lệnh chẩn đoán HotSpot.
- [Java Language Specification `12.7`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): unloading của class và interface.
