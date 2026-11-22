# Theo dõi nạp, dỡ lớp và số loader bằng công cụ chẩn đoán JVM

## 1. Vì sao phải quan sát class loading trong hệ thống plugin?

Mỗi lần hệ thống Java tìm, liên kết và định nghĩa một class có thể phát sinh chi phí CPU, I/O và bộ nhớ metadata. Trong kiến trúc plugin, mỗi plugin thường sở hữu một `ClassLoader` riêng để cô lập dependency; khi hot-reload, loader cũ cần hết tham chiếu để JVM có thể thu hồi những class mà loader đó định nghĩa. Nếu loader cũ còn bị giữ bởi thread, listener hoặc cache, metaspace có thể tăng dần sau nhiều lần reload.

Có ba chỉ số thường bị nhầm:

- **Số class đang được nạp**: số class metadata còn tồn tại hoặc được JVM thống kê tại thời điểm quan sát.
- **Số class đã nạp/dỡ tích lũy**: counter tăng dần theo thời gian, hữu ích để thấy churn nhưng không phải live count.
- **Số class loader**: số loader object hoặc loader data còn sống trong JVM; không đồng nghĩa số plugin hoặc số class.

Để chẩn đoán chính xác, cần kết hợp JVM unified logging, `jcmd` và Java Flight Recorder (JFR). Không có một con số đơn lẻ nào đủ chứng minh class loader leak.

## 2. Cơ chế class loading và unloading

Một class trong JVM được định danh bởi **binary name + defining class loader**. Do đó hai loader có thể định nghĩa hai class cùng tên nhưng JVM vẫn coi chúng là hai kiểu khác nhau. Điều này cho phép plugin V1 và V2 tồn tại đồng thời, song cũng có thể tạo `ClassCastException` nếu hợp đồng API bị nạp trùng.

Class unloading phụ thuộc reachability và hoạt động của garbage collector. Về nguyên tắc, JVM chỉ có thể thu hồi metadata của class/loader khi những điều kiện về reachability và unloading của runtime được thỏa mãn. `URLClassLoader.close()` giải phóng tài nguyên như JAR handles, **không bắt JVM unload class ngay lập tức**. `System.gc()` không bảo đảm có full GC hoặc unloading, đặc biệt nếu runtime tắt explicit GC hay dùng cấu hình collector khác.

Những nguồn tham chiếu dễ giữ loader cũ:

1. Thread còn chạy, `Thread.contextClassLoader` hoặc `ThreadLocal` chứa class/object của plugin.
2. Static collections và service registries của host lưu `Class<?>`, provider instances hoặc callbacks.
3. Executor, scheduler, timer, listener, shutdown hook chưa hủy.
4. Proxy, `MethodHandle`, reflection cache, serialization framework và logging adapters.
5. Native library, JNI reference, event bus và resource pool chưa đóng.

Trong phân tích, phải chứng minh **loader còn reachable từ GC roots** rồi tìm điểm giữ tham chiếu; không kết luận chỉ từ việc metaspace chưa giảm ngay sau một lần `close()`.

## 3. Unified logging: thấy class load/unload trong HotSpot

Từ Java 9, HotSpot hỗ trợ unified JVM logging qua `-Xlog`. Trên OpenJDK/HotSpot 17, bắt đầu bằng:

```bash
java -Xlog:class+load=info,class+unload=info -cp app.jar com.example.Main
```

Lệnh trên là **ví dụ cấu hình**, không chạy độc lập nếu thiếu `app.jar` và `com.example.Main`. Log load thường có class name và source (JAR hoặc module); log unload xuất hiện khi JVM thực sự dỡ class.

Để ghi log ra file với timestamp, uptime và tag:

```bash
java -Xlog:class+load=info,class+unload=info:file=class-events.log:time,uptime,level,tags \
     -cp app.jar com.example.Main
```

Trong production cần giới hạn kích thước và vòng quay log để tránh disk fill. Cấu hình file rotation của unified logging có thể dùng các option `filecount` và `filesize`; cú pháp và hỗ trợ thực tế kiểm tra bằng `java -Xlog:help`. Không bật class load logging mức quá chi tiết liên tục mà không đánh giá overhead và lượng dữ liệu.

### 3.1. Đọc log đúng

Ví dụ dạng log minh họa:

```text
[0.060s][info][class,load] java.lang.Object source: shared objects file
[0.185s][info][class,load] demo.plugins.Greeter source: file:/.../plugin-v1.jar
[5.290s][info][class,unload] unloading class demo.plugins.Greeter 0x...
```

Đường dẫn, địa chỉ, định dạng và timestamp thực tế phụ thuộc JDK/collector. Một class xuất hiện hai lần trong load log có thể do hai defining loaders khác nhau, không nhất thiết Java đọc cùng file hai lần do lỗi.

Nếu không thấy unload event, có thể JVM chưa chạy GC có unloading, loader vẫn còn reachable, collector/configuration chưa thực hiện unloading hoặc log đã bật sau thời điểm quan tâm. Vì vậy hãy kiểm tra GC timeline và loader statistics trước khi quy nguyên nhân.

## 4. jcmd: xem class loader hierarchy và thống kê

`jcmd` có trong JDK hỗ trợ chẩn đoán các JVM đang chạy trên cùng máy (tùy OS permissions và khả năng attach). Đầu tiên tìm PID:

```bash
jcmd -l
```

Rồi xem các lệnh khả dụng với runtime cụ thể:

```bash
jcmd <PID> help
```

`<PID>` là số tiến trình thật, không phải chuỗi gõ nguyên văn. Một số command hữu ích trên HotSpot/JDK 17:

```bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.classloaders
jcmd <PID> GC.class_histogram
jcmd <PID> VM.metaspace
```

Không phải mọi JDK build hoặc môi trường attach đều cung cấp giống nhau; nếu command vắng mặt, dùng `jcmd <PID> help` để xác minh và lựa chọn nguồn dữ liệu khác.

### 4.1. VM.classloader_stats

Thường cho biết từng class loader data, số classes liên quan và chi phí metadata/byte. Đây là điểm khởi đầu để phát hiện loader cũ tồn tại sau nhiều vòng plugin reload. Khi ghi nhận, nên so sánh các snapshot cùng một JVM, cùng phiên bản và cùng workload thay vì so raw bytes giữa các JDK khác nhau.

Ví dụ bảng diễn giải tự tạo, không phải stdout chuẩn:

| Thời điểm | Plugin đã reload | Loader cũ còn thấy trong stats | Metaspace |
|---|---:|---:|---:|
| T0 | 0 | 0 | 80 MiB |
| T1 | 10 | 1 | 86 MiB |
| T2 | 50 | 28 | 132 MiB |

Nếu workload/heap/GC tương tự, số loader cũ tăng liên tục qua các lần GC đáng chú ý hơn một lần tăng metaspace đơn lẻ. Dữ liệu giả định chỉ minh họa cách đọc xu hướng.

### 4.2. VM.classloaders

Hiển thị thông tin topology/class loader hierarchy trên runtime hỗ trợ. Hữu ích để tìm plugin loader nằm dưới application loader, loader nào sở hữu module/class và xem cấu trúc parent delegation. Với đồ thị có custom layer hoặc child-first loader, cần kết hợp mã ứng dụng in loader identity; tên hiển thị/hierarchy không phải bằng chứng đầy đủ cho mọi quan hệ class ownership.

### 4.3. VM.metaspace

Cho biết các số liệu metaspace, committed/reserved/used và một số chi tiết allocation hoặc class space tùy tùy chọn. Đừng nhầm committed/reserved bytes với live class metadata; JVM có thể giữ committed memory cho tái sử dụng dù class đã được unload.

### 4.4. GC.class_histogram và heap dump

`GC.class_histogram` hỗ trợ xem object count theo class. Muốn tìm class loader object bị giữ, có thể lọc `URLClassLoader`, custom plugin loader, `Thread`, các registry objects và provider instances. Histogram chỉ là snapshot object types, không hiển thị trực tiếp đường dẫn retention.

Nếu sự cố kéo dài, dùng heap dump với công cụ phân tích heap để truy GC roots và retained size. Heap dump có thể chứa mật khẩu, token, dữ liệu cá nhân và nội dung request; phải bảo vệ quyền truy cập, mã hóa, thời hạn lưu và cơ chế xóa theo chính sách tổ chức.

## 5. Java Flight Recorder (JFR)

JFR giúp thu thập sự kiện JVM theo thời gian với overhead tương đối thấp khi cấu hình phù hợp. Nó có thể cung cấp sự kiện class loading/unloading, class loader statistics, allocation và GC tùy JDK, profile và event settings.

Khởi chạy một recording bằng `jcmd`:

```bash
jcmd <PID> JFR.start name=plugin-diagnostics settings=profile duration=120s filename=plugin.jfr
```

Đọc summary và event type bằng công cụ JDK:

```bash
jfr summary plugin.jfr
jfr metadata plugin.jfr
```

Để quan sát class load/unload, cần chắc chắn các sự kiện tương ứng được bật trong settings của recording. Các tên như `jdk.ClassLoad`, `jdk.ClassUnload` và `jdk.ClassLoaderStatistics` phụ thuộc event availability/configuration; một recording `profile` mặc định không bảo đảm có đủ mọi event chi tiết.

Có thể dùng Java Mission Control (JMC) phân tích timeline, class loading và GC; liên hệ các spike với chính thời điểm deploy/reload plugin. Đừng bật mọi event ở mức detail cao trên production nếu chưa đánh giá storage/CPU overhead.

## 6. Công cụ Java MXBean: quan sát counters từ trong ứng dụng

JDK cung cấp `ClassLoadingMXBean` để lấy số class hiện tại và bộ đếm tích lũy. Dùng nó để tạo metrics đơn giản của host mà không cần parse JVM log.

Ví dụ Java 17+ **chạy độc lập**, file `ClassLoadingMetrics.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class ClassLoadingMetrics {
    public static void main(String[] args) {
        ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
        int live = bean.getLoadedClassCount();
        long total = bean.getTotalLoadedClassCount();
        long unloaded = bean.getUnloadedClassCount();

        System.out.println("live classes >= 0: " + (live >= 0));
        System.out.println("total >= live: " + (total >= live));
        System.out.println("unloaded >= 0: " + (unloaded >= 0));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac ClassLoadingMetrics.java
java ClassLoadingMetrics
```

Stdout dự kiến:

```text
live classes >= 0: true
total >= live: true
unloaded >= 0: true
```

Với HotSpot bình thường, các điều kiện trên hợp lý; con số class thực tế luôn thay đổi theo JVM, JDK, thư viện và thời điểm lấy mẫu. `getLoadedClassCount()` là số hiện tại; `getTotalLoadedClassCount()` và `getUnloadedClassCount()` là counter từ lúc JVM khởi động. Không lấy một counter tích lũy rồi diễn giải là số live loaders.

### 6.1. Tính delta qua thời gian

Ví dụ exporter quan sát mỗi khoảng lấy mẫu:

```java
long loadedBefore = bean.getTotalLoadedClassCount();
long unloadedBefore = bean.getUnloadedClassCount();
// ... plugin reload workload diễn ra ở đây ...
long loadedDelta = bean.getTotalLoadedClassCount() - loadedBefore;
long unloadedDelta = bean.getUnloadedClassCount() - unloadedBefore;
```

Đây là **mảnh mã** cần `bean` đã khai báo. Delta này mô tả số class load/unload trong khoảng đo, không trực tiếp cho biết loader cụ thể nào leak. Thêm metrics về plugin reload count, active plugin instances, class loader references và metaspace committed/used để có bức tranh đầy đủ.

## 7. Thực nghiệm class loader mới và rò rỉ loader

Một thí nghiệm nhỏ giúp thấy class identity và retention:

1. Tạo `URLClassLoader` cho một JAR plugin versioned.
2. Nạp một class bằng `Class.forName` và tạo instance nếu cần.
3. Ghi lại identity của loader, loaded class count và metaspace.
4. Dừng plugin, xóa listeners, tasks, registries và thread-local references.
5. Đóng loader, bỏ strong references tới class/loader/instance.
6. Để GC hoạt động theo runtime; quan sát logs/JFR/jcmd xem liệu class unload có diễn ra.
7. Lặp lại nhiều lần trong điều kiện workload có kiểm soát.

**Cẩn thận:** `WeakReference<ClassLoader>` có thể được dùng để quan sát liệu loader còn reachable hay không, nhưng `weakRef.get() == null` chỉ là bằng chứng đối tượng đã được GC thu hồi ở thời điểm đó. Ngược lại, weak ref vẫn có giá trị sau một lần GC chưa chứng minh leak. Một class có thể còn giữ loader qua static caches hoặc stack đang chạy.

Đoạn Java minh họa identity của loader:

```java
ClassLoader loader = pluginInstance.getClass().getClassLoader();
System.out.println("loader identity: " + System.identityHashCode(loader));
System.out.println("module: " + pluginInstance.getClass().getModule());
```

Đoạn này không độc lập vì cần `pluginInstance`; `identityHashCode` không bảo đảm duy nhất tuyệt đối giữa mọi object. Khi logging production, nên cấp một plugin-loader-instance ID bằng counter/UUID và ghi cùng version để tương quan log chính xác.

## 8. Quy trình chẩn đoán class loader leak có hệ thống

### Bước A: Lập baseline

Trước khi reload, ghi `ClassLoadingMXBean`, `jcmd VM.classloader_stats`, `VM.metaspace`, heap/metaspace metrics, JFR timeline và số plugin đang hoạt động. Cố gắng ổn định workload/GC và lưu JDK flags.

### Bước B: Tạo tải kiểm soát

Reload cùng một plugin theo số vòng đã biết, ví dụ 20 lần; bảo đảm code plugin không cố tình tạo thread/resource vô hạn. Ghi timestamp và loader ID từng phiên bản.

### Bước C: Dừng và cleanup

Chờ request drain, gọi `stop/close`, hủy listener/callback/timer/executor, đóng loader khi phù hợp và xóa registry references. Sau đó quan sát qua nhiều chu kỳ GC có class unloading.

### Bước D: So sánh snapshot

Nếu số loader cũ còn sống và live class count tăng liên tục qua các vòng, kiểm tra heap dump để tìm GC roots. Nếu live count ổn định và loaded/unloaded counters đều tăng, có thể đang có class churn hợp lệ thay vì leak.

### Bước E: Xác nhận fix

Sau khi sửa retained reference, lặp thí nghiệm với cùng workload, cùng JDK và cấu hình GC; so sánh xu hướng loader count, live classes, metaspace used, heap retained size và thời gian reload.

## 9. Lỗi phổ biến khi dùng công cụ

| Nhận định sai | Vì sao sai | Cách sửa |
|---|---|---|
| `URLClassLoader.close()` nghĩa là class đã unload | `close()` chỉ xử lý tài nguyên loader, còn reachability mới quyết định GC/unload | Quan sát unload events, loader references và GC |
| Total loaded classes tăng là memory leak | Đây là counter tích lũy, không phải live count | Kết hợp live count và unloaded count |
| Không có unload log nghĩa là leak | GC/unloading chưa diễn ra hoặc logging chưa đủ | Bật log đúng, quan sát lâu hơn và kiểm tra GC |
| Metaspace committed không giảm nghĩa là leak | JVM có thể giữ memory để tái sử dụng | So metaspace used, class loader stats, heap roots |
| Có hai class cùng tên là duplicate bug | Hai loader định nghĩa cùng tên có thể là chủ đích isolation | Kiểm tra defining loader và contract API |
| Dùng `System.gc()` để test chắc chắn | JVM có thể bỏ qua hoặc không unload ngay | Dùng nhiều chu kỳ quan sát, JFR và heap analysis |
| Ghi hết class load logs production vô hạn | Gây I/O/CPU/disk overhead | Dùng duration ngắn, log rotation, sampling |

## 10. Checklist vận hành cho host có plugin

- [ ] Có metrics loaded/live/unloaded class counts và metaspace.
- [ ] Gắn plugin version, class loader instance ID vào log lifecycle.
- [ ] Có lệnh `jcmd`/JFR dùng được trong môi trường production có phân quyền.
- [ ] Có lịch quan sát trước/sau hot reload với workload kiểm soát.
- [ ] Dọn ThreadLocal, TCCL, executor, listener, registry và native resources trước khi giải phóng loader.
- [ ] Tránh giữ class/object/plugin loader cũ trong shared caches.
- [ ] Có quy trình heap dump và bảo vệ dữ liệu nhạy cảm trong dump.
- [ ] Alert dựa vào **xu hướng** của loader count, live classes và metaspace chứ không chỉ một snapshot.

**Kết luận:** Theo dõi nạp/dỡ class cần kết hợp counter `ClassLoadingMXBean`, event `-Xlog:class+load/unload`, thống kê `jcmd` và timeline JFR. Loader cũ chỉ có thể được thu hồi khi không còn tham chiếu giữ nó; việc đóng loader hoặc chạy GC một lần không bảo đảm unloading. Một chẩn đoán đáng tin phải liên hệ loader identity, vòng đời plugin, GC và đường dẫn retention trên heap.
