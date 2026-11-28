# Chẩn đoán OutOfMemoryError Metaspace trước khi tăng giới hạn bộ nhớ

## 1. Đừng tăng MaxMetaspaceSize ngay khi thấy lỗi

`OutOfMemoryError: Metaspace` cho biết JVM không thể tiếp tục cấp phát metadata cho class. Đây là bộ nhớ native của tiến trình, tách khỏi Java heap. Lỗi có thể do giới hạn Metaspace được cấu hình quá thấp, do ứng dụng nạp ngày càng nhiều class, do class loader cũ không được thu hồi, hoặc do tiến trình đã thiếu native memory.

Tăng `-XX:MaxMetaspaceSize` có thể giúp ứng dụng tiếp tục chạy khi mức sử dụng hợp lệ vượt giới hạn hiện tại. Nhưng nếu nguyên nhân là class loader leak, việc tăng giới hạn chỉ trì hoãn lần lỗi tiếp theo và làm tiến trình tiêu thụ thêm bộ nhớ.

Trước khi thay đổi cấu hình, hãy trả lời bốn câu hỏi:

1. Lỗi thực sự là `Metaspace`, `Compressed class space` hay một dạng native-memory allocation failure khác?
2. Metaspace đang tăng theo số class hợp lệ hay tăng sau mỗi lần deploy/reload?
3. Class loader nào giữ metadata và vì sao loader đó chưa được thu hồi?
4. JVM còn đủ ngân sách native memory trong giới hạn máy/container hay không?

Bài này dùng các công cụ chẩn đoán HotSpot còn được hỗ trợ trên JDK hiện đại, đặc biệt `jcmd`, Native Memory Tracking (NMT), unified logging và các API quản lý JVM.

## 2. Hiểu chính xác loại OutOfMemoryError

Không phải mọi lỗi có chữ “memory” đều là lỗi Metaspace. Hãy đọc đầy đủ detail message:

| Detail message | Khu vực gặp vấn đề | Hướng điều tra đầu tiên |
| --- | --- | --- |
| `Metaspace` | Metadata class trong Metaspace | Giới hạn `MaxMetaspaceSize`, class loader và mức native memory |
| `Compressed class space` | Vùng chứa compressed class pointers trên HotSpot 64-bit khi cơ chế này được bật | `CompressedClassSpaceSize`, số class và class loader |
| `Java heap space` | Java object heap | Heap live set, object retention và `-Xmx` |
| `GC overhead limit exceeded` | GC dành phần lớn thời gian nhưng thu hồi quá ít heap | Heap live set và hiệu quả GC |
| `Cannot reserve ... bytes of ...` hoặc `Out of swap space?` | Có thể là native allocation hoặc virtual-memory reservation thất bại | Native memory, giới hạn tiến trình/container và log lỗi fatal |

`Compressed class space` là vùng riêng, không nên gộp mọi lỗi của nó vào `Metaspace`. Nếu thông báo là `Compressed class space`, kiểm tra `CompressedClassSpaceSize` và `UseCompressedClassPointers`; tăng `MaxMetaspaceSize` không trực tiếp sửa giới hạn của vùng này.

Nếu thông báo là `Java heap space`, tăng Metaspace không giải quyết vấn đề. Tương tự, heap dump hữu ích để tìm object giữ tham chiếu, nhưng bản thân nó không phải báo cáo dung lượng native Metaspace.

## 3. Thu thập bằng chứng trước khi khởi động lại

Khi lỗi xảy ra trong production, hãy lưu lại:

- Toàn bộ exception message và stack trace.
- Thời điểm lỗi, PID, phiên bản JDK, collector và JVM flags.
- Log GC/class loading/class unloading quanh thời điểm lỗi.
- Số class đang được nạp, số class đã unload và số class loader.
- Số liệu Metaspace `used`, `committed`, `reserved`.
- Native memory của tiến trình và mức sử dụng bộ nhớ của máy/container.
- Lịch deploy, reload plugin, sinh proxy hoặc thay đổi cấu hình gần thời điểm lỗi.

Nếu JVM vẫn còn chạy, thu thập chẩn đoán trước khi restart:

~~~powershell
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
jcmd 12345 VM.version
~~~

Thay `12345` bằng PID thật. `jcmd -l` liệt kê các JVM mà công cụ có thể nhìn thấy. `VM.command_line` cho biết lệnh khởi chạy; `VM.flags -all` cho phép kiểm tra các flag hiện tại và giá trị của chúng.

Chạy `jcmd` trên cùng máy với JVM và bằng cùng effective user/group đã khởi chạy tiến trình. Trong container riêng, cần xác định PID trong đúng PID namespace; danh sách từ host có thể không hiển thị tiến trình container theo cách mong đợi.

Nếu JVM đã thoát, giữ lại fatal error log, GC log, log ứng dụng và số liệu container/OS đã thu thập. Không thể truy vấn `jcmd` vào một tiến trình đã kết thúc.

## 4. Kiểm tra giới hạn và flag Metaspace đang áp dụng

Hai flag thường bị nhầm:

| Flag | Vai trò | Có phải giới hạn tối đa không? |
| --- | --- | --- |
| `-XX:MetaspaceSize` | Ngưỡng metadata ban đầu khiến JVM cân nhắc GC lần đầu khi vượt ngưỡng; JVM điều chỉnh ngưỡng này theo mức metadata sử dụng | Không |
| `-XX:MaxMetaspaceSize` | Giới hạn tối đa native memory dành cho class metadata | Có |

Theo mặc định, `MaxMetaspaceSize` không bị giới hạn bằng một con số cố định; lượng metadata thực tế còn phụ thuộc ứng dụng và native memory sẵn có. Nếu hệ thống đặt `MaxMetaspaceSize` thấp, lỗi có thể xuất hiện dù máy vẫn còn bộ nhớ.

Kiểm tra giá trị flag trong JVM đang chạy:

~~~powershell
jcmd 12345 VM.flags -all
~~~

Tìm các flag:

- `MetaspaceSize`
- `MaxMetaspaceSize`
- `CompressedClassSpaceSize`
- `UseCompressedClassPointers`
- `ClassUnloading`

Đừng đọc một file startup script rồi giả định nó chính là cấu hình đang chạy. Flag có thể được truyền qua launcher, biến môi trường, service manager, container entrypoint hoặc file cấu hình của nền tảng triển khai.

`MetaspaceSize` là ngưỡng kích hoạt GC thích ứng, không phải dung lượng đã cấp phát. Không tăng flag này với kỳ vọng tạo thêm sức chứa tối đa. `MaxMetaspaceSize` mới là giới hạn trên cần xem xét sau khi đã đo nhu cầu thực tế và loại trừ leak.

## 5. Đo Metaspace bằng jcmd VM.metaspace

`VM.metaspace` là diagnostic command chuyên biệt để xem thống kê Metaspace:

~~~powershell
jcmd 12345 VM.metaspace
~~~

Lấy tóm tắt cơ bản:

~~~powershell
jcmd 12345 VM.metaspace basic=true
~~~

Tách mức sử dụng theo class loader:

~~~powershell
jcmd 12345 VM.metaspace show-loaders=true
~~~

Liệt kê cả class do từng loader nạp:

~~~powershell
jcmd 12345 VM.metaspace show-loaders=true show-classes=true
~~~

Có thể xem thêm phân loại chunk hoặc không gian ảo khi cần:

~~~powershell
jcmd 12345 VM.metaspace by-chunktype=true
jcmd 12345 VM.metaspace by-spacetype=true
jcmd 12345 VM.metaspace vslist=true
~~~

`basic=true` in tóm tắt cơ bản và không cần safepoint. Các chế độ chi tiết phụ thuộc số class đang nạp; chọn mức chi tiết phù hợp để tránh tạo thêm tải chẩn đoán trong lúc hệ thống đang quá tải.

Từ JDK 25, phần lớn thông tin Metaspace trước đây in cùng GC heap information đã được chuyển sang Metaspace-specific logging và command `VM.metaspace`. Không dựa vào `jcmd GC.heap_info` để lấy đầy đủ số liệu Metaspace trên JDK 25 trở lên.

## 6. Đọc đúng used, committed và reserved

Các số liệu Metaspace cần được hiểu theo đúng ý nghĩa:

| Chỉ số | Ý nghĩa | Không nên kết luận |
| --- | --- | --- |
| `used` | Metadata đang được sử dụng | Không nhất thiết bằng tổng số byte native memory của tiến trình |
| `committed` | Vùng nhớ JVM đã commit để dùng cho Metaspace | Không đồng nghĩa toàn bộ committed là metadata đang sống |
| `reserved` | Không gian địa chỉ ảo JVM đã reserve | Không đồng nghĩa toàn bộ vùng reserved đang chiếm RAM vật lý |
| `free`/capacity trong chunk | Phần trống còn có thể sử dụng trong các vùng đã cấp | Không tự động là leak nếu vẫn còn cao |

Ví dụ minh họa:

~~~text
Metaspace:
  used      = 180 MB
  committed = 220 MB
  reserved  = 1 GB
~~~

Trong ví dụ, JVM đang dùng khoảng 180 MB metadata và đã commit 220 MB. Một GB reserved không có nghĩa tiến trình đang dùng một GB RAM cho Metaspace.

Khi class được unload, `used` có thể giảm. `committed` có thể giảm sau khi các vùng không còn cần thiết được uncommit, hoặc giữ nguyên để JVM tái sử dụng chunk cho class loader khác. Vì vậy:

- `used` giảm nhưng `committed` không giảm chưa đủ chứng minh có leak.
- `reserved` không giảm không phải bằng chứng tiến trình đang giữ RAM vật lý tương ứng.
- `used` tăng đều sau nhiều chu kỳ tải/xả ổn định đáng chú ý hơn một ảnh chụp riêng lẻ.
- `committed` hoặc RSS tăng trong khi `used` ổn định có thể liên quan tới subsystem native khác; cần đối chiếu NMT và công cụ OS.

So sánh cùng chỉ số, cùng đơn vị, cùng workload và cùng giai đoạn warm-up. Không so số liệu Metaspace của một JVM mới khởi động với một JVM đã chạy tải production nhiều giờ rồi kết luận có leak.

## 7. Tìm class loader giữ metadata

Metaspace chứa metadata của class; class loader còn reachable thì các class do loader định nghĩa không thể được unload. Vì vậy, class loader statistics là một trong những bằng chứng quan trọng nhất khi điều tra lỗi Metaspace.

Lấy thống kê tất cả class loader:

~~~powershell
jcmd 12345 VM.classloader_stats
~~~

Xem cây class loader:

~~~powershell
jcmd 12345 VM.classloaders
~~~

Nếu cần danh sách class và thông tin chi tiết:

~~~powershell
jcmd 12345 VM.classloaders show-classes=true verbose=true
~~~

Hoặc dùng `VM.metaspace show-loaders=true` để xem mức sử dụng metadata theo loader. Đối chiếu số class, dung lượng chunk và tên/loại loader với kiến trúc ứng dụng.

Hãy chú ý các dấu hiệu:

- Mỗi lần deploy/reload lại xuất hiện thêm một loader cùng loại.
- Loader cũ vẫn tồn tại sau khi chức năng hoặc plugin đã dừng.
- Số class tăng đều qua nhiều chu kỳ nhưng workload không tăng tương ứng.
- Một framework tạo proxy/generated class liên tục và không tái sử dụng loader hoặc class.

Số lượng class tăng không tự động là leak. Ứng dụng có thể có nhiều class hợp lệ do framework, ORM, dependency injection, proxy hoặc bytecode generation. Điều quan trọng là xu hướng sau khi workload ổn định và sau khi các tính năng được dỡ bỏ.

## 8. Những tham chiếu thường làm class loader không thể thu hồi

Một class loader cũ có thể bị giữ lại bởi:

- Static map/cache của class loader cha giữ `Class<?>`, instance, `Method`, `MethodHandle` hoặc callback của plugin.
- Thread pool dùng chung giữ thread context class loader trỏ về loader cũ.
- Thread do plugin tạo chưa kết thúc; stack hoặc context của thread giữ class/loader.
- `ThreadLocal` trên thread sống lâu giữ object thuộc class loader đã dừng.
- Listener, event bus, MBean, logging handler hoặc shutdown hook chưa được deregister.
- Cache reflection, proxy hoặc serializer giữ metadata của class.
- JNI global reference giữ object/class Java từ mã native.

Quy trình đóng plugin cần dừng thread/executor, xóa ThreadLocal phù hợp, gỡ listener và MBean, deregister callback, xóa cache và đóng tài nguyên của loader. Gọi `URLClassLoader.close()` chỉ đóng resource/JAR mà loader đã mở; nó không trực tiếp unload class và không đảm bảo Metaspace được thu hồi ngay.

Không gọi `System.gc()` sau mỗi lần deploy như một cách sửa leak. Đây chỉ là yêu cầu GC cân nhắc thu gom; JVM có thể bỏ qua và việc ép full GC có thể gây pause lớn. Trước hết phải loại bỏ các tham chiếu giữ class loader.

## 9. Theo dõi class load và class unload

Unified logging có thể ghi lại sự kiện class được nạp và unload:

~~~powershell
java -Xlog:class+load=info,class+unload=info -jar app.jar
~~~

Để theo dõi thêm Metaspace, cú pháp tag thay đổi từ JDK 25:

| Phiên bản JDK | Ví dụ cấu hình log |
| --- | --- |
| JDK 16–24 | `-Xlog:class+unload=info,gc+metaspace=info` |
| JDK 25 trở lên | `-Xlog:class+unload=info,metaspace=info` |

Ví dụ JDK 25 trở lên, ghi log ra file có rotation:

~~~powershell
java "-Xlog:class+unload=info,metaspace=info:file=logs/metaspace.log:time,level,tags:filecount=5,filesize=10M" -jar app.jar
~~~

Với JDK 16–24, thay tag `metaspace` bằng `gc+metaspace`. Từ JDK 25, Metaspace logging được tách khỏi GC logging; đây là thay đổi cách quan sát, không thay đổi nguyên tắc class unloading.

Khi kiểm tra, hãy ghép thời điểm reload plugin với log class unload. Nếu loader đã dừng nhưng không thấy class unload sau các chu kỳ GC phù hợp, kiểm tra reachability, collector và flag `ClassUnloading`. Không phụ thuộc vào một mốc thời gian cố định để kết luận unload phải xảy ra ngay.

## 10. Dùng Native Memory Tracking để đối chiếu toàn bộ native memory

Metaspace là một phần native memory. Nếu số liệu Metaspace không giải thích được mức tăng bộ nhớ tiến trình, hãy xem các subsystem khác bằng Native Memory Tracking (NMT).

NMT phải được bật khi JVM khởi động; không thể bật hồi tố cho một tiến trình đang chạy mà trước đó không theo dõi. Có hai mức:

- `summary`: thống kê tổng hợp theo subsystem.
- `detail`: thêm thông tin allocation theo call site và virtual-memory region.

Khởi chạy ứng dụng với summary:

~~~powershell
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Hoặc dùng detail khi cần điều tra sâu:

~~~powershell
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Lấy báo cáo:

~~~powershell
jcmd 12345 VM.native_memory summary scale=MB
~~~

Đặt baseline sau khi ứng dụng đã warm-up:

~~~powershell
jcmd 12345 VM.native_memory baseline
~~~

Sau một khoảng workload ổn định, so sánh:

~~~powershell
jcmd 12345 VM.native_memory summary.diff scale=MB
~~~

Nếu đã bật detail:

~~~powershell
jcmd 12345 VM.native_memory detail.diff scale=MB
~~~

NMT có thể phân loại native memory như `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Other` và `Symbol`. Trong category `Class`, báo cáo có thể tách Metadata và Class space; dùng số liệu này để xác định phần nào đang tăng.

NMT có overhead. Tài liệu Oracle ghi nhận mức ảnh hưởng hiệu năng khoảng 5–10% tùy workload và mức tracking; hãy cân nhắc trước khi bật `detail` trên production. NMT cũng không theo dõi allocation do native code bên ngoài JVM thực hiện, chẳng hạn một số thư viện JNI hoặc native dependency.

## 11. Khi nào phải dùng công cụ của hệ điều hành?

Nếu RSS/container memory tăng nhưng Metaspace `used` và category `Class` của NMT không tăng tương ứng, nguyên nhân có thể nằm ở native allocation ngoài JVM hoặc subsystem khác.

Đối chiếu:

| Môi trường | Công cụ/số liệu cần xem |
| --- | --- |
| Linux | `/proc/<pid>/smaps`, `pmap`, process RSS, cgroup memory |
| Windows | Process/Private Bytes trong Performance Monitor, giới hạn Job Object/container |
| macOS | Activity Monitor, `vmmap` và memory footprint của tiến trình |
| Container/orchestrator | Memory limit, current usage, peak usage và trạng thái OOM của container/pod |

NMT chỉ phản ánh allocation mà HotSpot theo dõi. Nếu thư viện JNI tự gọi `malloc`, native allocator hoặc GPU/codec API, hãy dùng profiler hoặc công cụ của nền tảng để điều tra phần đó.

Không cộng `reserved` của NMT với RSS như thể hai số cùng biểu thị RAM vật lý. Reserved là không gian địa chỉ ảo; committed và resident memory có ý nghĩa khác nhau. Trong container, cần so với giới hạn cgroup thực tế vì tiến trình có thể bị kill do container OOM dù chưa chạm `MaxMetaspaceSize`.

## 12. Kiểm tra class loading metrics trong ứng dụng

Ứng dụng có thể ghi nhận xu hướng class loading bằng API quản lý chuẩn:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public class ClassLoadingMetrics {
    public static void print() {
        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("Currently loaded: "
                + bean.getLoadedClassCount());
        System.out.println("Total loaded: "
                + bean.getTotalLoadedClassCount());
        System.out.println("Total unloaded: "
                + bean.getUnloadedClassCount());
    }
}
~~~

`getLoadedClassCount()` là số class hiện đang được JVM nạp; `getTotalLoadedClassCount()` là tổng số class đã nạp kể từ khi JVM bắt đầu; `getUnloadedClassCount()` là tổng số class đã unload. Theo dõi ba giá trị này qua nhiều chu kỳ deploy/reload có thể cho thấy class có thực sự được thu hồi hay không.

Các số liệu aggregate không xác định loader nào đang giữ class. Khi thấy xu hướng bất thường, kết hợp với `jcmd VM.classloader_stats` và `jcmd VM.metaspace show-loaders=true`.

## 13. Khi nào cần heap dump?

Heap dump không chứa toàn bộ native Metaspace, nhưng có thể hữu ích khi cần tìm object/reference chain đang giữ class loader:

~~~powershell
jcmd 12345 GC.heap_dump filename=metaspace-investigation.hprof
~~~

Phân tích dump bằng công cụ phù hợp để tìm các instance của `ClassLoader`, object của plugin, thread context class loader, ThreadLocal, registry hoặc cache đang giữ tham chiếu.

Lưu ý:

- `GC.heap_dump` có impact cao và mặc định yêu cầu full GC nếu không dùng tùy chọn `-all`.
- Heap dump có thể rất lớn; cần đủ dung lượng đĩa và kiểm soát thời gian pause.
- Dump có thể chứa dữ liệu nhạy cảm của ứng dụng; lưu trữ và chia sẻ theo chính sách bảo mật.
- Heap dump giúp tìm đường tham chiếu trong Java heap; dùng `VM.metaspace` và NMT để phân tích native memory.

Chỉ tạo dump khi số liệu class loader cho thấy có khả năng leak và cần tìm chính xác đối tượng giữ loader.

## 14. Phân biệt nhu cầu class hợp lệ với class loader leak

Không phải Metaspace tăng là lỗi. Một ứng dụng có thể tăng metadata hợp lệ khi:

- Khởi tạo framework, ORM, serializer hoặc dependency injection.
- Sinh proxy/class cho nhiều entity, endpoint hoặc schema.
- Nạp plugin/module mới theo yêu cầu nghiệp vụ.
- Tăng số tenant hoặc cấu hình làm phát sinh thêm class.

Hãy đo trong một chu kỳ có thể lặp lại:

1. Khởi động ứng dụng và warm-up theo cùng kịch bản.
2. Ghi baseline `VM.metaspace`, class loader stats và class loading metrics.
3. Chạy workload cố định.
4. Dừng hoặc reload plugin/module theo quy trình thật.
5. Đợi GC tự nhiên và ghi lại class unload.
6. Lặp lại nhiều lần dưới cùng mức tải.

Diễn giải:

| Kết quả sau nhiều chu kỳ | Hướng kết luận |
| --- | --- |
| `used` tăng trong warm-up rồi ổn định | Có thể là nhu cầu khởi tạo bình thường |
| `used` giảm sau unload, `committed` còn cao | Chunk có thể được giữ để tái sử dụng; chưa đủ bằng chứng leak |
| Loader cũ và class count tăng qua từng reload | Điều tra tham chiếu giữ class loader |
| `used` tăng liên tục nhưng số loader ổn định | Kiểm tra class generation/proxy và số class trong loader hiện hữu |
| Metaspace ổn định nhưng RSS tăng | Đối chiếu các category NMT và native memory ngoài JVM |
| `Compressed class space` chạm giới hạn | Điều tra riêng class space và compressed class pointers |

Không kết luận leak từ một ảnh chụp hoặc chỉ từ RSS. Dùng xu hướng sau warm-up, sau các chu kỳ GC và sau workload tương đương.

## 15. Khi nào mới nên tăng MaxMetaspaceSize?

Chỉ xem xét tăng giới hạn khi đã có bằng chứng:

- `MaxMetaspaceSize` hiện tại đang đặt thấp hơn nhu cầu metadata hợp lệ.
- Số class và class loader đạt mức ổn định theo workload dự kiến.
- Các class loader cũ được unload đúng vòng đời; không có xu hướng tăng sau mỗi deploy/reload.
- `VM.metaspace` cho thấy metadata sống cao nhưng ổn định.
- Máy/container còn ngân sách native memory đủ để cấp thêm.
- Tác động tới tổng memory limit, heap, thread stacks, code cache và native libraries đã được tính đến.

Nếu đủ điều kiện, tăng giới hạn theo bước có kiểm soát và đo lại:

~~~powershell
java -XX:MaxMetaspaceSize=512m -jar app.jar
~~~

`512m` chỉ là ví dụ minh họa, không phải giá trị khuyến nghị chung. Chọn giới hạn dựa trên số liệu peak của workload thật, headroom cần thiết và memory limit của tiến trình/container.

Nếu JVM không đặt `MaxMetaspaceSize` mà vẫn gặp allocation failure, tăng giới hạn này có thể không giúp gì. Khi đó cần kiểm tra native memory toàn tiến trình, giới hạn container/OS và allocation từ native library.

Không giảm `-Xmx` để “nhường chỗ” cho Metaspace trừ khi đã xác nhận heap có dư địa thực sự và đã đo tác động hiệu năng. Heap và Metaspace cùng nằm trong ngân sách bộ nhớ tiến trình; thay đổi một vùng có thể làm vùng khác thiếu headroom.

## 16. Những cách xử lý không nên dùng làm bước đầu

- Không tăng `MaxMetaspaceSize` trước khi kiểm tra class loader stats và native memory.
- Không gọi `System.gc()` lặp lại để ép class unload.
- Không tắt class unloading để né một biểu hiện bất thường.
- Không nhầm `MetaspaceSize` với giới hạn tối đa.
- Không nhầm `Compressed class space` với Metaspace thông thường.
- Không kết luận leak chỉ vì `reserved` hoặc `committed` chưa giảm ngay sau unload.
- Không dựa vào `GC.heap_info` để đọc Metaspace trên JDK 25 trở lên; dùng `VM.metaspace`.
- Không dùng `MetaspaceReclaimPolicy` trong cấu hình hiện đại; tùy chọn này đã bị obsoleted từ JDK 21.
- Không dùng NMT như bằng chứng đầy đủ cho native allocation do JNI/thư viện bên ngoài JVM thực hiện.

## 17. Quy trình runbook khi gặp OutOfMemoryError Metaspace

1. **Xác nhận lỗi:** đọc đúng detail message và phân biệt Metaspace với Compressed class space, heap hoặc native allocation failure.
2. **Giữ bằng chứng:** lưu stack trace, PID, JDK version, JVM flags, GC/class unload log và memory metrics.
3. **Kiểm tra cấu hình:** dùng `jcmd PID VM.flags -all` để xem `MaxMetaspaceSize`, `MetaspaceSize`, `CompressedClassSpaceSize` và class unloading.
4. **Đo Metaspace:** chạy `jcmd PID VM.metaspace basic=true`, sau đó `show-loaders=true` khi cần.
5. **Đếm loader:** chạy `jcmd PID VM.classloader_stats` và so sánh sau từng chu kỳ deploy/reload.
6. **Đối chiếu native memory:** nếu NMT đã bật, dùng `VM.native_memory summary` và baseline/diff; nếu không, bật cho lần khởi động kế tiếp.
7. **Tìm reference leak:** kiểm tra thread, ThreadLocal, listener, MBean, static cache, plugin registry và JNI global reference.
8. **Đối chiếu OS/container:** kiểm tra RSS, cgroup limit và native allocation bên ngoài JVM nếu số liệu HotSpot không giải thích được.
9. **Sửa nguyên nhân:** dọn vòng đời class loader, giảm class generation không cần thiết hoặc sửa cấu hình giới hạn quá thấp.
10. **Chỉ tăng giới hạn khi đủ bằng chứng:** chạy lại workload đại diện và xác nhận còn đủ headroom tổng bộ nhớ.

**Ghi nhớ:** `OutOfMemoryError: Metaspace` là tín hiệu cần chẩn đoán metadata và native memory, không phải chỉ thị tự động tăng `MaxMetaspaceSize`. Dùng `jcmd VM.metaspace` và `VM.classloader_stats` để tìm loader/class tăng bất thường; dùng NMT để đối chiếu native memory của HotSpot; dùng công cụ OS/container khi nghi ngờ allocation bên ngoài JVM. Chỉ tăng giới hạn khi metadata sống cao nhưng ổn định, class loader được thu hồi đúng và ngân sách native memory cho phép.

## Nguồn tham khảo chính thức

- [Troubleshoot Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The java Command: MaxMetaspaceSize and MetaspaceSize — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JDK 25 Release Notes — Metaspace Logging and jcmd Changes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html)
- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387)
