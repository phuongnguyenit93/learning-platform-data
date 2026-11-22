# Metaspace, metadata lớp và vòng đời ClassLoader trong Java

Khi JVM nạp một class, nó tạo các cấu trúc runtime để quản lý tên kiểu, field, method, constant pool, quan hệ kế thừa và các thông tin cần cho linking và thực thi. Trên HotSpot, phần lớn **class metadata** được quản lý trong native memory gọi là **Metaspace**. Vòng đời metadata gắn với **defining ClassLoader**: nếu loader còn được giữ sống, các class do nó định nghĩa thường vẫn còn được giữ; khi loader có thể được GC thu hồi và JVM thực hiện class unloading, metadata liên quan có thể được giải phóng.

Ba khái niệm phải tách biệt:

- **Java Heap** chứa object ứng dụng, instance, array, object `Class<?>` và object `ClassLoader`.
- **Metaspace** là cách HotSpot quản lý phần lớn metadata class trong native memory. Đây là chi tiết triển khai HotSpot, không phải một vùng vật lý bắt buộc của mọi JVM.
- **Class unloading** phụ thuộc khả năng thu hồi defining loader. Bỏ một biến `Class<?>` hoặc gọi `URLClassLoader.close()` không tự ép JVM unload class ngay.

Bài tập trung vào Java hiện đại và HotSpot: cấu trúc metadata, delegation, class identity, classloader leak, Elastic Metaspace từ JDK 16 và công cụ chẩn đoán đang được duy trì. Các khác biệt phiên bản được ghi rõ.

## 1. Class metadata là gì?

Class metadata là thông tin JVM cần để hiểu và vận hành một kiểu đã được nạp. Tùy implementation, các cấu trúc liên quan có thể gồm:

- Tên nhị phân và thông tin định danh class.
- Class cha, interface và quan hệ kiểu.
- Mô tả field, method, constructor, modifier và descriptor.
- Runtime constant pool cùng các symbolic reference cần resolve.
- Annotation, generic signature và dữ liệu hỗ trợ reflection.
- Thông tin nội bộ cho dispatch method, linking, verification và runtime.
- Metadata của array class, hidden class hoặc class được sinh động.

File `.class` trên đĩa là **đầu vào** của quá trình loading. JVM đọc bytecode, xác minh và tạo cấu trúc runtime. Không đồng nhất dung lượng file class với dung lượng metadata sau khi nạp: representation nội bộ, số method/field, annotation, constant pool và cấu trúc VM có thể làm mức sử dụng bộ nhớ khác nhau.

Ứng dụng sinh nhiều class động (proxy, adapter, class do framework hoặc expression compiler tạo ra) có thể làm số class và metadata tăng. **Số class tăng không tự chứng minh memory leak**; cần quan sát trong cùng workload và sau khi ứng dụng ổn định.

## 2. Method Area trong JVMS và Metaspace của HotSpot

Đặc tả JVM định nghĩa **Method Area** là vùng nhớ runtime logic được chia sẻ giữa các thread. Nó chứa cấu trúc theo class như runtime constant pool, dữ liệu field/method và code của method/constructor. Đặc tả không bắt buộc mọi JVM đặt vùng logic đó ở cùng một vị trí vật lý hoặc dùng cùng allocator.

**Metaspace là cách HotSpot triển khai việc quản lý class metadata**, không phải tên khác chính xác cho Method Area trên mọi JVM. Trên HotSpot hiện đại, class metadata được cấp phát trong native memory, qua các arena/chunk gắn với dữ liệu class loader. JVM implementation khác có thể tổ chức vật lý khác mà vẫn đáp ứng JVMS.

| Khái niệm | Ý nghĩa |
| --- | --- |
| `Method Area` | Vùng runtime logic theo JVMS |
| `Metaspace` | Cơ chế/vùng quản lý class metadata của HotSpot |
| `Java Heap` | Vùng chứa object và array |
| `Code Cache` | Vùng riêng cho mã máy được JIT compiler sinh ra |

Native memory vẫn tiêu thụ address space, committed pages và RAM của process/container. Nó không nằm ngoài giới hạn tài nguyên của tiến trình.

## 3. Heap và Metaspace giữ những gì?

| Thành phần | Nội dung điển hình | Ghi chú |
| --- | --- | --- |
| Java Heap | Instance, array, object `Class<?>`, object `ClassLoader` | GC thu hồi theo reachability |
| Metaspace | Metadata class do HotSpot quản lý | Native memory; gắn với defining loader |
| Compressed Class Space | Một loại metadata class khi compressed class pointers bật | Có giới hạn riêng trong HotSpot |
| Code Cache | Mã máy đã biên dịch bởi JIT | Không phải class metadata |
| Native memory khác | Thread stack, GC structures, direct/native allocations | Không phải tất cả đều là Metaspace |

Object `Class<?>` là đại diện runtime của class trong Java API và nằm trong heap; nó liên kết tới class loader đã định nghĩa class. Metadata nội bộ mà HotSpot dùng để mô tả class được quản lý riêng trong Metaspace/class space. Vì vậy heap dump có thể cho thấy object loader hoặc Class mirror đang bị giữ, còn VM diagnostics giúp nhìn phần metadata.

Không cộng trực tiếp heap used với Metaspace used rồi coi đó là toàn bộ RSS của process. Reserved, committed, resident memory và các native allocation khác là những đại lượng khác nhau.

## 4. ClassLoader và mô hình delegation

`java.lang.ClassLoader` chịu trách nhiệm tìm hoặc tạo định nghĩa class từ binary name. Mặc định, việc tìm class diễn ra theo hướng:

1. Kiểm tra class đã được loader này nạp chưa bằng `findLoadedClass`.
2. Delegation sang parent loader (nếu parent null thì dùng loader built-in của VM).
3. Nếu parent không tìm thấy, loader hiện tại tìm class qua `findClass`.
4. Khi có class và yêu cầu resolve, loader gọi `resolveClass`.

Parent-first giúp các class nền tảng và dependency dùng chung được định nghĩa nhất quán. Runtime JDK hiện đại có bootstrap loader, platform loader và system/application loader. Bootstrap loader thường được biểu diễn bằng `null` khi gọi `Class.getClassLoader()`.

Với custom loader, thường nên override `findClass(String)` để cung cấp nguồn class riêng và giữ delegation mặc định. Chỉ override `loadClass` khi có lý do rõ ràng như child-first loading; khi đó cần quản lý `findLoadedClass`, `defineClass`, `resolveClass`, package/module boundary và loader constraints chính xác.

### Class loading không chỉ là đọc file

Một class có thể được tạo từ byte array, tải từ network, module, JAR hoặc nguồn do ứng dụng tự định nghĩa. `defineClass` biến byte array thành định nghĩa class gắn với loader gọi nó. Loader cũng có thể tìm resources như file cấu hình hoặc tài nguyên đóng gói cùng plugin.

### ClassLoader và module

Trên JDK hiện đại, module và `ModuleLayer` phối hợp với class loader để tổ chức khả năng đọc, export và open package. Module layer có thể dùng các loader được chỉ định khi định nghĩa module. Module không làm biến mất khái niệm defining loader hoặc quy tắc class identity.

## 5. Class identity: cùng tên vẫn có thể là hai kiểu khác nhau

Định danh runtime của class không chỉ dựa vào tên nhị phân. **Tên class và defining class loader cùng xác định identity của kiểu.** Nếu hai loader định nghĩa cùng binary name, JVM có hai đối tượng `Class<?>` khác nhau.

~~~text
loader A -> defines "plugin.Service" -> Class A
loader B -> defines "plugin.Service" -> Class B

Class A != Class B
Class A is not assignment-compatible with Class B
~~~

Đây là lý do plugin có thể gặp `ClassCastException` dù log cho thấy hai object có cùng tên class. Chúng đến từ hai namespace class loader khác nhau. Hai bản thư viện cùng tên package/class nhưng được định nghĩa bởi loader khác nhau cũng không tự động là cùng kiểu.

`Class.getClassLoader()` trả defining loader của class. Không nhầm loader khởi đầu yêu cầu loading với loader thực sự định nghĩa class sau delegation.

## 6. Vòng đời class: load, link, initialize và sử dụng

Có thể hình dung vòng đời theo các bước:

1. **Loading:** tìm bytecode hoặc tạo representation, rồi tạo đối tượng `Class<?>`.
2. **Linking:** verification kiểm tra tính hợp lệ; preparation chuẩn bị dữ liệu class; resolution có thể diễn ra eager hoặc lazy.
3. **Initialization:** chạy initializer tĩnh và khởi tạo static fields theo quy tắc Java.
4. **Use:** instance được tạo, method được gọi, reflection và runtime references có thể tiếp tục giữ class/loader sống.
5. **Unloading eligibility:** defining loader có thể trở nên unreachable từ GC roots.
6. **Class unloading:** nếu JVM chọn unload trong quá trình GC, class và metadata gắn với loader có thể được thu hồi.

Loading, linking và initialization là các giai đoạn khác nhau. Một class đã load chưa chắc đã initialize. Ví dụ `Class.forName(name, false, loader)` yêu cầu load mà không yêu cầu initialize theo overload đó; `true` yêu cầu initialize.

Không dựa vào thứ tự chi tiết của mọi thao tác resolve để viết business logic. Đặc tả cho phép một số hoạt động linking diễn ra lazy, miễn chương trình giữ semantics đã quy định.

## 7. Khi nào class được unload?

Theo Java Language Specification, JVM implementation **có thể** unload class. Một class/interface chỉ đủ điều kiện unload khi defining class loader của nó có thể được garbage collector thu hồi. Class do bootstrap loader định nghĩa thì không unload.

Hệ quả:

- Không unload riêng một class chỉ vì không còn biến local giữ `Class<?>`.
- Nếu loader vẫn reachable, các class do loader định nghĩa không đủ điều kiện unload theo quy tắc này.
- Nếu loader trở nên reclaimable, JVM có thể thu hồi class/metadata liên quan trong quá trình GC.
- Đặc tả không yêu cầu GC unload ngay ở chu kỳ kế tiếp; class unloading là optimization.
- `System.gc()` chỉ là lời yêu cầu GC, không bảo đảm class unload hoặc Metaspace giảm ngay.
- Không thiết kế semantics ứng dụng phụ thuộc vào việc class được unload tại một thời điểm cụ thể.

Một loader có thể không còn được dùng về nghiệp vụ nhưng vẫn sống vì reference gián tiếp. Tìm đường tham chiếu giữ loader sống thường quan trọng hơn việc tăng giới hạn Metaspace.

## 8. ClassLoader leak là gì?

Classloader leak xảy ra khi loader của module/plugin không còn cần thiết nhưng vẫn có strong reference từ một vùng sống lâu. Khi loader không được thu hồi, các class nó định nghĩa và metadata liên quan cũng có thể tiếp tục chiếm bộ nhớ.

| Nguồn giữ | Ví dụ | Hướng kiểm tra |
| --- | --- | --- |
| Static registry ở parent loader | Giữ plugin instance, `Class<?>`, `Method` hoặc callback | Xóa/unregister khi dừng plugin |
| Thread sống lâu | Context class loader trỏ tới loader plugin | Khôi phục context loader và kết thúc thread |
| ThreadLocal | Value là object thuộc class plugin | Gọi `remove()` trong finally |
| Executor/scheduler | Task hoặc worker giữ class plugin | Hủy task và shutdown executor do plugin sở hữu |
| Listener/event bus | Listener plugin chưa unregister | Gỡ listener khi undeploy |
| MBean/JMX hoặc registry | Object plugin đã đăng ký nhưng chưa deregister | Unregister khi dừng module |
| Shutdown hook | Hook giữ class hoặc instance plugin | Gỡ hook khi vòng đời cho phép |
| Cache/reflection | `Class`, `MethodHandle`, proxy hoặc metadata cache | Kiểm tra owner và chính sách eviction |
| JNI/native reference | Native code giữ global reference tới object Java | Kiểm tra JNI lifecycle và release global refs |

Một thread pool của host có thể sống lâu hơn plugin. Nếu task, ThreadLocal value hoặc context class loader của thread pool giữ object thuộc plugin, loader có thể không unload dù JAR đã đóng.

### Static field có luôn ngăn unload không?

Không. Static field thuộc class do loader định nghĩa nằm trong đồ thị runtime của loader. Nếu toàn bộ loader và đồ thị class của nó không còn đường strong reference từ GC roots, cả nhóm có thể được thu hồi. Vấn đề thường xuất hiện khi **một object bên ngoài nhóm**, chẳng hạn static field của class do parent loader định nghĩa, giữ class/instance/plugin loader.

## 9. Dọn dẹp plugin và `URLClassLoader.close()`

`URLClassLoader` là API hiện hành để nạp class/resources từ URL như directory hoặc JAR. `close()` đóng file/resource mà loader đã mở và ngăn loader tiếp tục nạp class/resource mới từ URL của chính nó. Các class đã nạp và class từ parent vẫn có thể dùng được.

**`close()` không ép class unloading.** Sau khi close, nếu còn object, Class, thread, listener hoặc reference khác giữ loader, class metadata vẫn có thể ở lại. Đóng loader là bước dọn resource; làm cho loader unreachable là bước khác.

~~~java
URLClassLoader loader = new URLClassLoader(
        pluginUrls, ClassLoader.getSystemClassLoader());

try {
    Class<?> pluginType = Class.forName(
            "example.Plugin", true, loader);
    // Khởi tạo và sử dụng plugin theo contract của host.
} finally {
    loader.close();
}
~~~

Đây là snippet tích hợp; `pluginUrls` do ứng dụng tạo và plugin lifecycle cần xử lý thêm. Trước khi đóng, host nên gọi lifecycle stop, unregister listener/MBean/driver theo contract, dừng executor/thread do plugin sở hữu, xóa cache/ThreadLocal thích hợp và khôi phục context class loader. Sau khi mọi strong reference biến mất, GC mới có cơ hội thu hồi loader.

Không giữ plugin instance, `Class<?>` hoặc `Method` trong static registry của host sau undeploy. Nếu host cần API ổn định, đặt interface/DTO trong loader cha dùng chung; implementation plugin nằm trong loader riêng.

## 10. Metaspace tăng vì sao?

Metaspace có thể tăng khi JVM nạp thêm class hoặc cần thêm metadata. Những tình huống bình thường:

- Ứng dụng khởi động, nạp framework, thư viện và class ứng dụng.
- Framework sinh proxy/adapter/class động theo cấu hình hoặc endpoint.
- Plugin/module được nạp thêm và vẫn đang hoạt động.
- Runtime mechanisms làm phát sinh cấu trúc hỗ trợ liên quan.
- Workload thực sự cần nhiều class hơn trước.

Dấu hiệu đáng điều tra là **số class/loader hoặc live metadata tiếp tục tăng qua nhiều chu kỳ GC dưới workload ổn định**, nhất là khi module đã undeploy nhưng loader vẫn tồn tại. Một ảnh chụp Metaspace lớn không đủ kết luận leak: ứng dụng có thể cần nhiều class hợp lệ hoặc giới hạn cấu hình quá thấp.

Metaspace là native memory, nên `-Xmx` không phải giới hạn trực tiếp của nó. Tuy vậy, heap, Metaspace và native memory cùng tiêu thụ tài nguyên/address space của process/container. Tăng heap có thể làm áp lực native memory tệ hơn nếu tổng giới hạn container cố định.

## 11. `OutOfMemoryError: Metaspace` và Compressed Class Space

Hai thông báo cần phân biệt trong HotSpot:

| Lỗi | Ý nghĩa | Hướng kiểm tra |
| --- | --- | --- |
| `OutOfMemoryError: Metaspace` | Không thể cấp thêm class metadata; có thể chạm `MaxMetaspaceSize` hoặc thiếu native memory | Kiểm tra giới hạn, native memory và loader/class growth |
| `OutOfMemoryError: Compressed class space` | Vùng compressed class metadata đã hết dung lượng | Kiểm tra `UseCompressedClassPointers` và `CompressedClassSpaceSize` |

Trên HotSpot 64-bit, khi `UseCompressedClassPointers` bật, VM có thể dành một vùng Compressed Class Space cho loại metadata `Klass`. Đây là vùng chuyên biệt của quản lý class metadata, không phải Java Heap và không đồng nghĩa `Compressed Oops` (compressed object references). Các loại class metadata khác vẫn được quản lý trong Metaspace.

Các tùy chọn HotSpot liên quan:

- `-XX:MaxMetaspaceSize`: giới hạn tối đa Metaspace.
- `-XX:MetaspaceSize`: ngưỡng ban đầu/high-water mark ảnh hưởng thời điểm VM kích hoạt GC metadata; không phải hard cap.
- `-XX:CompressedClassSpaceSize`: kích thước vùng compressed class space khi chế độ tương ứng được bật.
- `-XX:UseCompressedClassPointers`: bật/tắt compressed class pointers trên cấu hình HotSpot hỗ trợ.

Đây là **HotSpot implementation flags**, không phải bảo đảm portable cho mọi JVM vendor. Kiểm tra `java -XX:+PrintFlagsFinal -version` hoặc `jcmd <pid> VM.flags -all` trên runtime thực tế trước khi thay đổi. Không tăng giới hạn chỉ để che classloader leak; trước tiên xác định loader nào giữ class và vì sao.

## 12. Elastic Metaspace từ JDK 16

JEP 387 đưa **Elastic Metaspace** vào HotSpot từ **JDK 16**. Cải tiến này thay đổi cách VM quản lý chunk/commit của metadata: giảm fragmentation và cho phép phần Metaspace không còn cần được trả về hệ điều hành linh hoạt hơn. Lợi ích dễ thấy trong workload có nhiều class loader nhỏ và hoạt động load/unload thường xuyên.

Điểm cần hiểu đúng:

- Elastic Metaspace là thay đổi triển khai HotSpot, không đổi quy tắc class identity hoặc class unloading của Java.
- Khi loader được unload, chunk metadata có thể được tái sử dụng hoặc trả về hệ điều hành theo chính sách VM.
- Không có bảo đảm RSS của process giảm ngay đúng bằng số byte metadata vừa thu hồi.
- JDK 8 đến JDK 15 không có allocator Elastic Metaspace của JEP 387; không áp dụng chi tiết allocator JDK 16+ cho các runtime đó.

Cải tiến giúp quản lý native memory linh hoạt hơn. Nó không chữa leak khi ứng dụng vẫn giữ strong reference tới loader.

## 13. Đo class loading bằng `ClassLoadingMXBean`

`ManagementFactory.getClassLoadingMXBean()` trả MXBean để theo dõi hệ thống class loading. Các số liệu chính:

| Method | Ý nghĩa |
| --- | --- |
| `getLoadedClassCount()` | Số class hiện đang được load |
| `getTotalLoadedClassCount()` | Tổng số class đã load kể từ khi JVM chạy |
| `getUnloadedClassCount()` | Tổng số class đã unload kể từ khi JVM chạy |
| `isVerbose()` / `setVerbose(boolean)` | Trạng thái/bật tắt verbose class-loading output |

~~~java
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

int currentlyLoaded = bean.getLoadedClassCount();
long totalLoaded = bean.getTotalLoadedClassCount();
long totalUnloaded = bean.getUnloadedClassCount();

System.out.println("currently loaded=" + currentlyLoaded);
System.out.println("total loaded=" + totalLoaded);
System.out.println("total unloaded=" + totalUnloaded);
~~~

Cần `import java.lang.management.ClassLoadingMXBean;` và `import java.lang.management.ManagementFactory;`. Các bộ đếm này giúp nhận biết xu hướng class load/unload, nhưng **không cho biết trực tiếp byte Metaspace hoặc đường reference giữ loader sống**. Hãy kết hợp với VM diagnostics.

## 14. Dùng `jcmd` xem Metaspace và ClassLoader

`jcmd` gửi lệnh chẩn đoán tới JVM đang chạy. Chạy trên cùng máy và với quyền user/group phù hợp với tiến trình Java.

~~~bash
# Liệt kê các JVM mà jcmd có thể nhìn thấy
jcmd -l

# Thống kê Metaspace, có breakdown theo loader
jcmd <pid> VM.metaspace show-loaders=true scale=MB

# Thống kê tất cả ClassLoader
jcmd <pid> VM.classloader_stats

# Xem cây loader và class nếu cần chi tiết
jcmd <pid> VM.classloaders verbose=true show-classes=true
~~~

`VM.metaspace` có thể hiển thị basic summary, mức dùng theo loader, class và chunk/space breakdown. `VM.classloader_stats` cho thống kê các loader. `VM.classloaders` in hierarchy và có option mở rộng thông tin. Cú pháp option có thể khác theo JVM version; chạy `jcmd <pid> help VM.metaspace` hoặc `jcmd <pid> help VM.classloaders` trên process đích trước khi dùng option nâng cao.

Không bật mọi mức chi tiết liên tục trên production. Chọn lệnh phù hợp, đánh giá impact và thu thập ở thời điểm có hiện tượng.

## 15. Native Memory Tracking và log class load/unload

### Native Memory Tracking (NMT)

NMT theo dõi allocation nội bộ của HotSpot. Muốn dùng, phải khởi động JVM với tracking option:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau khi ứng dụng chạy ổn định, lấy baseline và so sánh:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
# Sau một khoảng thời gian/workload:
jcmd <pid> VM.native_memory summary.diff
~~~

Có thể chọn `detail` thay cho `summary` khi cần thông tin sâu hơn, nhưng tracking làm tăng overhead CPU/bộ nhớ; đo trong môi trường đại diện và cân nhắc chi phí. NMT không theo dõi mọi allocation từ thư viện native bên ngoài HotSpot, vì vậy nếu RSS tăng mà NMT không giải thích được, cần công cụ hệ điều hành hoặc profiler native.

### Unified logging cho class loading

Trên JDK 9+, có thể ghi sự kiện load/unload:

~~~bash
java -Xlog:class+load=info,class+unload=info -jar app.jar
~~~

Dùng log này để xác nhận class nào được nạp và class nào được unload. Nó hữu ích khi kiểm tra plugin lifecycle, nhưng log quá nhiều có thể làm tăng I/O và dung lượng file; cấu hình output/rotation phù hợp.

### Heap dump và đường reference

Nếu nghi loader bị giữ, heap dump và công cụ phân tích heap giúp tìm strong reference path từ GC roots tới object `ClassLoader`, `Class<?>` hoặc plugin instance. Kiểm tra dominator/path to GC roots, thread, ThreadLocal, static field và registry. Metaspace statistics cho biết mức sử dụng; heap graph giúp giải thích **ai đang giữ loader sống**.

## 16. Quy trình điều tra Metaspace tăng liên tục

Một quy trình thực tế:

1. **Xác định loại OOM:** `Java heap space`, `Metaspace`, `Compressed class space` hay native allocation failure. Không gộp tất cả thành “thiếu RAM”.
2. **Ghi baseline:** class loaded/unloaded count, Metaspace used/committed, số ClassLoader và mức dùng theo loader.
3. **Giữ workload ổn định:** quan sát sau các chu kỳ GC phù hợp, tránh so sánh hai thời điểm có số plugin/request khác hẳn.
4. **Tìm loader tăng bất thường:** `VM.classloader_stats` và `VM.metaspace show-loaders=true` giúp phát hiện nhiều loader tương tự hoặc một loader tăng class liên tục.
5. **Theo dõi load/unload:** unified logging hoặc class-loading MXBean cho thấy class có unload hay không.
6. **Tìm strong reference path:** heap dump, thread/context loader, ThreadLocal, static registry, executor và listener.
7. **Kiểm tra lifecycle cleanup:** undeploy plugin có dừng thread, unregister callback, clear cache, restore context loader và close URLClassLoader không?
8. **Chỉ sau đó mới xem tuning:** xác định giới hạn nào thực sự bị chạm và liệu mức class metadata cần thiết có hợp lý với workload.

Nếu số class tăng nhưng số loader ổn định, ứng dụng có thể đang sinh thêm class trong loader dài hạn. Nếu số loader tăng đều sau mỗi lần redeploy, nghi ngờ loader cũ bị giữ. Nếu class count ổn định nhưng native memory tổng tăng, nguyên nhân có thể ở vùng native khác chứ không phải Metaspace.

## 17. Ví dụ Java chạy được: cùng class name từ hai loader

Ví dụ dưới đây định nghĩa cùng binary name `PluginMarker` trong hai custom class loader. Kết quả cho thấy hai class có cùng tên nhưng khác identity và không assignment-compatible. Demo chỉ minh họa class identity; **nó không cố chứng minh GC đã unload loader**, vì class unloading không được bảo đảm xảy ra đúng lúc.

Tạo file **`ClassLoaderLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;

public final class ClassLoaderLifecycleDemo {
    private static final String TARGET = "PluginMarker";

    private static final class ByteArrayClassLoader extends ClassLoader {
        private final byte[] classBytes;

        ByteArrayClassLoader(ClassLoader parent, byte[] classBytes) {
            super(parent);
            this.classBytes = classBytes.clone();
        }

        @Override
        protected synchronized Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            Class<?> loaded = findLoadedClass(name);
            if (loaded == null) {
                loaded = defineClass(name, classBytes, 0, classBytes.length);
            }
            if (resolve) {
                resolveClass(loaded);
            }
            return loaded;
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static byte[] readPluginBytes() throws IOException {
        String resource = TARGET + ".class";
        try (InputStream in = ClassLoaderLifecycleDemo.class
                .getClassLoader().getResourceAsStream(resource)) {
            if (in == null) {
                throw new IOException("Missing class resource: " + resource);
            }
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = readPluginBytes();
        ClassLoader parent = ClassLoaderLifecycleDemo.class.getClassLoader();

        ClassLoader loaderA = new ByteArrayClassLoader(parent, bytes);
        ClassLoader loaderB = new ByteArrayClassLoader(parent, bytes);

        Class<?> classA = Class.forName(TARGET, true, loaderA);
        Class<?> classB = Class.forName(TARGET, true, loaderB);

        boolean sameName = classA.getName().equals(classB.getName());
        boolean sameClass = classA == classB;
        boolean differentLoaders =
                classA.getClassLoader() != classB.getClassLoader();
        boolean usesLoaderA = classA.getClassLoader() == loaderA;
        boolean usesLoaderB = classB.getClassLoader() == loaderB;
        boolean notAssignable = !classA.isAssignableFrom(classB);

        System.out.println("same binary name: " + sameName);
        System.out.println("same Class object: " + sameClass);
        System.out.println("different defining loaders: " + differentLoaders);
        System.out.println("first uses loader A: " + usesLoaderA);
        System.out.println("second uses loader B: " + usesLoaderB);
        System.out.println("assignable across loaders: " + !notAssignable);

        check(sameName, "binary names");
        check(!sameClass, "distinct Class identities");
        check(differentLoaders && usesLoaderA && usesLoaderB, "defining loaders");
        check(notAssignable, "type identity includes defining loader");
        System.out.println("all checks passed");
    }
}

final class PluginMarker {
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 ClassLoaderLifecycleDemo.java
java ClassLoaderLifecycleDemo
~~~

**Stdout đã kiểm tra:**

~~~text
same binary name: true
same Class object: false
different defining loaders: true
first uses loader A: true
second uses loader B: true
assignable across loaders: false
all checks passed
~~~

Demo dùng custom loader child-first cho đúng một tên class để chứng minh hai định nghĩa riêng biệt. Custom loader thực tế cần policy rõ về delegation, package, module, parallel loading và bảo mật; không sao chép nguyên mẫu child-first này làm loader production cho mọi class.

## 18. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách hiểu/giải pháp |
| --- | --- | --- |
| Coi Metaspace là Java Heap | Hai vùng quản lý khác nhau | Phân tích heap và native metadata riêng |
| Coi Method Area trong JVMS luôn là Metaspace vật lý | Method Area là khái niệm logic; Metaspace là HotSpot implementation | Phân biệt đặc tả và VM vendor |
| Nghĩ file .class chính là metadata trong RAM | File class là binary input | Metadata runtime được tạo khi load/link |
| Nghĩ object `Class<?>` nằm trong Metaspace | Class mirror là object heap | Phân biệt mirror với VM metadata |
| Nghĩ `-Xmx` giới hạn Metaspace | Heap max không phải Metaspace max | Xem các vùng native/HotSpot flags |
| Nghĩ `MetaspaceSize` là hard cap | Nó ảnh hưởng ngưỡng GC metadata ban đầu | `MaxMetaspaceSize` mới là giới hạn max |
| Chỉ nhìn tổng Metaspace rồi kết luận leak | Chưa biết loader nào giữ class | Dùng breakdown theo ClassLoader |
| Bỏ biến Class rồi mong class unload | Defining loader có thể vẫn reachable | Tìm toàn bộ strong reference path |
| Gọi `System.gc()` và đòi unload ngay | GC/unloading không có thời điểm bảo đảm | Quan sát xu hướng và log unload |
| Gọi `URLClassLoader.close()` rồi coi loader đã unload | Close đóng resource, không ép GC | Dọn references và để loader unreachable |
| Cùng tên class thì chắc chắn cùng type | Defining loader tham gia identity | Kiểm tra `Class.getClassLoader()` |
| Mọi custom loader đều child-first | Có thể tạo duplicate core/API classes | Giữ parent-first trừ khi có thiết kế rõ |
| Chỉ shutdown thread mà quên context loader | Thread pool có thể sống lâu và giữ loader | Restore context class loader |
| Quên ThreadLocal value | Thread sống lâu giữ object/plugin class | Gọi `remove()` trong cleanup |
| Unregister listener nhưng bỏ MBean/registry khác | Reference còn ở một owner khác | Lập checklist cleanup toàn bộ registration |
| Nâng MaxMetaspaceSize ngay khi OOM | Có thể che leak và tăng áp lực native memory | Xác định root cause trước |
| Coi NMT bao phủ mọi native allocation | NMT chủ yếu theo dõi nội bộ HotSpot | Dùng thêm OS/native profiler khi cần |
| Dùng trace flags cũ cho class load/unload | Unified logging là cách hiện hành trên JDK 9+ | `-Xlog:class+load=info,class+unload=info` |
| Nghĩ Elastic Metaspace xóa được leak | Loader vẫn reachable thì metadata vẫn sống | Sửa lifecycle/strong references |
| Coi số class loaded là số byte Metaspace | Class có kích thước metadata khác nhau | Theo dõi cả counts và memory |
| Nghĩ class unloading bắt buộc xảy ra | JLS nói implementation may unload | Không phụ thuộc semantics vào unload timing |

## 19. Bài tập có đáp án

### Bài 1 — Metaspace nằm ở đâu?

**Đáp án:** Trong HotSpot, Metaspace quản lý class metadata trong native memory. Object `Class<?>` và `ClassLoader` vẫn là object trên Java Heap.

### Bài 2 — Method Area và Metaspace có giống nhau hoàn toàn?

**Đáp án:** Không. Method Area là vùng logic theo JVMS; Metaspace là cách HotSpot tổ chức class metadata. Đặc tả không bắt buộc mọi JVM dùng Metaspace.

### Bài 3 — Hai loader định nghĩa cùng class name

**Đáp án:** Hai class có thể khác identity, không assignment-compatible và gây `ClassCastException` khi trộn API/object giữa loader.

### Bài 4 — Điều kiện class unload

**Đáp án:** Defining class loader phải có thể được GC reclaim; JVM implementation có thể unload class. Bootstrap-loaded classes không unload.

### Bài 5 — `URLClassLoader.close()` có ép unload không?

**Đáp án:** Không. Nó đóng resource do loader mở và ngăn loader nạp thêm từ URL của nó. Cần loại bỏ strong references và chờ GC có cơ hội thu hồi loader.

### Bài 6 — Class count tăng sau redeploy

Một ứng dụng redeploy plugin nhiều lần, số loader tăng đều. Cần điều tra gì?

**Đáp án:** Tìm strong references từ static registry, ThreadLocal, context class loader, executor, listener, MBean, shutdown hook hoặc cache tới loader/plugin cũ.

### Bài 7 — `MetaspaceSize` và `MaxMetaspaceSize`

**Đáp án:** `MetaspaceSize` ảnh hưởng ngưỡng ban đầu kích hoạt GC metadata; `MaxMetaspaceSize` đặt giới hạn tối đa. Chúng là HotSpot flags.

### Bài 8 — Compressed Class Space là gì?

**Đáp án:** Vùng riêng cho một loại class metadata khi compressed class pointers được bật trên HotSpot. Nó có giới hạn `CompressedClassSpaceSize` và có thể báo OOM riêng.

### Bài 9 — Công cụ nào cho biết metadata theo loader?

**Đáp án:** `jcmd <pid> VM.metaspace show-loaders=true scale=MB` và `jcmd <pid> VM.classloader_stats`.

### Bài 10 — NMT phải bật lúc nào?

**Đáp án:** Khi khởi động JVM qua `-XX:NativeMemoryTracking=summary` hoặc `detail`. Sau đó dùng `jcmd VM.native_memory baseline` và `summary.diff` để so sánh.

### Bài 11 — Vì sao heap dump hữu ích?

**Đáp án:** Nó có thể cho đường strong reference từ GC roots tới loader, Class object, plugin instance, thread hoặc registry đang giữ loader sống. Metaspace summary một mình không chỉ ra chủ thể giữ reference.

### Bài 12 — Elastic Metaspace giải quyết vấn đề gì?

**Đáp án:** Từ JDK 16, JEP 387 cải tiến allocator/fragmentation và cho phép HotSpot thu hồi vùng metadata không dùng về OS linh hoạt hơn. Nó không sửa strong reference leak.

## 20. Checklist code review và vận hành

- [ ] Đã phân biệt JVMS Method Area, HotSpot Metaspace, Java Heap và Code Cache?
- [ ] Có hiểu Class mirror và ClassLoader instance là object heap?
- [ ] Đã xác định defining loader của class cần điều tra?
- [ ] Custom loader có delegation policy rõ ràng và tránh duplicate API/core types?
- [ ] Có phân biệt cùng binary name với cùng Class identity?
- [ ] Plugin undeploy có dừng thread/executor và task do plugin sở hữu?
- [ ] Context class loader có được restore về giá trị trước đó?
- [ ] ThreadLocal value có được remove trong finally?
- [ ] Listener, MBean, registry, callback, cache và shutdown hook có được unregister/clear?
- [ ] `URLClassLoader` được close để giải phóng resource khi phù hợp?
- [ ] Không nhầm close với class unloading?
- [ ] Không phụ thuộc `System.gc()` để unload ngay?
- [ ] Theo dõi current/total/unloaded class count và Metaspace theo thời gian?
- [ ] Đã dùng `jcmd VM.metaspace` và `VM.classloader_stats` khi cần?
- [ ] NMT đã được bật từ startup nếu cần native-memory baseline/diff?
- [ ] Có dùng unified logging hiện hành trên JDK 9+ khi điều tra class load/unload?
- [ ] Đã phân biệt OOM Metaspace với Compressed Class Space và native heap?
- [ ] Chỉ điều chỉnh giới hạn sau khi xác định loader growth và native memory?
- [ ] Đã test redeploy/reload lặp lại dưới workload ổn định?
- [ ] Có heap dump/path-to-GC-roots khi cần tìm reference giữ loader?
- [ ] Không giả định class unloading phải xảy ra tại một thời điểm cụ thể?

**Kết luận:** Metaspace là cách HotSpot quản lý class metadata trong native memory; vòng đời metadata phụ thuộc defining ClassLoader. Khi loader còn strong-reachable, các class do nó định nghĩa có thể tiếp tục giữ metadata dù plugin đã ngừng dùng. Giải quyết đúng cần hiểu class identity, dọn thread/context loader/ThreadLocal/registry, đóng resource và tìm reference path. Dùng `jcmd`, ClassLoadingMXBean, NMT và unified logging để xác định loader nào đang tăng; chỉ tuning Metaspace sau khi đã phân biệt giới hạn cấu hình với classloader leak.

### Tài liệu chính thức đang được duy trì

- [Java Language Specification, Chapter 12 — Execution](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html): loading, linking, initialization và điều kiện class unloading (`12.7).
- [Java Virtual Machine Specification, Chapter 2 — Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html): Method Area và Runtime Constant Pool ở mức đặc tả.
- [`ClassLoader` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): delegation, defining loader, loadClass/findClass/defineClass.
- [`URLClassLoader` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLClassLoader.html): close và vòng đời resource.
- [`ClassLoadingMXBean` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): số class loaded/unloaded.
- [The `jcmd` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): VM.metaspace, VM.classloader_stats, VM.classloaders và VM.native_memory.
- [Troubleshoot Memory Leaks — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html): OOM Metaspace, Compressed Class Space, NMT, class-loader statistics.
- [JDK 16 Release Notes — JEP 387 Elastic Metaspace](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): cải tiến quản lý và thu hồi Metaspace trong HotSpot từ JDK 16.