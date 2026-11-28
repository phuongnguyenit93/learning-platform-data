# Thu hồi class và trả vùng nhớ metaspace không dùng về hệ điều hành

## 1. Elastic Metaspace giải quyết vấn đề gì?

Mỗi class Java được JVM nạp đều cần metadata để mô tả cấu trúc và hành vi của class. HotSpot lưu phần metadata này trong vùng native memory gọi là Metaspace. Khi ứng dụng tạo nhiều class, đặc biệt qua nhiều class loader ngắn hạn như plugin, ứng dụng server hoặc hệ thống triển khai lại module, lượng metadata có thể tăng đáng kể.

Trước JDK 16, cơ chế quản lý Metaspace có thể giữ lại nhiều vùng nhớ đã được giải phóng để tái sử dụng nội bộ. Điều đó hữu ích cho các lần nạp class tiếp theo, nhưng có thể khiến bộ nhớ đã không còn cần thiết vẫn được giữ ở trạng thái committed.

JEP 387, được tích hợp trong JDK 16, tái thiết kế bộ cấp phát Metaspace với tên gọi **Elastic Metaspace**. Mục tiêu là giảm overhead của metadata và trả các vùng nhớ không còn cần dùng về hệ điều hành kịp thời hơn sau khi class được unload. Lợi ích dễ thấy trong ứng dụng tạo và hủy nhiều class loader nhỏ, chẳng hạn hệ thống plugin hoặc môi trường triển khai ứng dụng nhiều lần.

Đây vẫn là cơ chế nền tảng trong HotSpot hiện đại. Việc thu hồi thực tế phụ thuộc vào vòng đời class loader, khả năng class unloading của GC và cấu trúc các vùng nhớ đã cấp phát.

## 2. Metaspace lưu gì và nằm ở đâu?

Metaspace chứa metadata nội bộ của class như cấu trúc class, method, runtime constant pool và thông tin cần thiết để JVM thực thi. Vùng nhớ này nằm trong native memory của tiến trình, tách biệt với Java heap.

Điều này tạo ra hai điểm cần nhớ:

- Tăng hoặc giảm Java heap bằng `-Xms`/`-Xmx` không trực tiếp tăng hoặc giảm giới hạn Metaspace.
- Một ứng dụng có thể còn nhiều heap trống nhưng vẫn gặp `OutOfMemoryError: Metaspace` nếu vùng metadata bị giới hạn hoặc native memory không còn đủ.

Trên HotSpot, metadata được quản lý theo các vùng/chunk gắn với class loader. Class loader yêu cầu không gian để chứa metadata của những class mà nó định nghĩa. Khi loader được thu hồi, các chunk liên quan có thể được tái sử dụng hoặc trả lại cho hệ thống quản lý bộ nhớ của Metaspace.

Không nên đồng nhất Metaspace với bộ nhớ heap hoặc tổng RSS của tiến trình. RSS còn bao gồm Java heap, code cache, thread stack, thư viện native, direct buffer và nhiều vùng native khác.

## 3. Vòng đời class gắn với class loader

Một class không được unload chỉ vì không còn biến nào đang giữ một instance của class đó. Điều kiện quan trọng là **defining class loader** của class phải có thể được garbage collector thu hồi.

Quy trình khái quát:

1. Class loader nạp class.
2. JVM tạo metadata cho class trong Metaspace.
3. Class loader và các class do nó định nghĩa được dùng trong suốt vòng đời tính năng hoặc plugin.
4. Khi không còn đường tham chiếu mạnh từ GC roots tới class loader, loader có thể trở thành đối tượng đủ điều kiện thu hồi.
5. Trong một chu kỳ GC có thực hiện class unloading, JVM có thể unload các class do loader đó định nghĩa.
6. Metadata của các class được unload được giải phóng khỏi arena/chunk của loader.
7. Các chunk trống được tái sử dụng; những vùng đủ điều kiện có thể được uncommit và trả bộ nhớ về hệ điều hành.

Theo Java Language Specification, một implementation có thể unload class khi và chỉ khi defining class loader có thể được garbage collector thu hồi. Class do bootstrap class loader định nghĩa không được unload. Việc unload là tối ưu hóa của JVM, vì vậy chương trình không được phụ thuộc vào thời điểm class bị unload.

Điều này giải thích vì sao class loader của ứng dụng chính thường sống đến khi JVM kết thúc, còn class loader dành cho plugin có thể được thu hồi sau khi plugin dừng và mọi tham chiếu liên quan được giải phóng.

## 4. Elastic Metaspace trả bộ nhớ về hệ điều hành như thế nào?

JEP 387 chuyển sang cách quản lý Metaspace dựa trên chunk linh hoạt hơn. Có thể hình dung theo các bước:

1. Mỗi class loader có vùng cấp phát metadata riêng.
2. Khi cần thêm metadata, vùng cấp phát nhận các chunk từ bộ quản lý chung.
3. Khi class loader bị thu hồi, các chunk của nó được trả về bộ quản lý chung.
4. Chunk rảnh có thể được cấp lại cho class loader khác mà không cần yêu cầu thêm bộ nhớ từ hệ điều hành.
5. Khi các chunk rảnh có thể hợp nhất thành vùng phù hợp, JVM có thể uncommit các granule không còn cần thiết.

Vì vậy, có hai kết quả khác nhau:

- **Tái sử dụng nội bộ:** chunk được giải phóng khỏi loader cũ nhưng vẫn được giữ committed để loader khác dùng sau này.
- **Trả về hệ điều hành:** vùng nhớ được uncommit, làm giảm lượng Metaspace committed mà JVM đang giữ.

Không phải mọi class unload đều khiến RSS của tiến trình giảm ngay. Nếu một chunk còn chứa metadata đang dùng, hoặc vùng rảnh chưa thể hợp nhất thành đơn vị có thể uncommit, JVM có thể giữ lại để tái sử dụng. Cơ chế elastic giúp thu hồi linh hoạt hơn, nhưng không bảo đảm mọi byte được trả ngay sau mỗi lần unload.

## 5. Phân biệt used, capacity, committed và reserved

Khi đọc log hoặc kết quả chẩn đoán Metaspace, cần hiểu đúng các chỉ số:

| Chỉ số | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| `used` | Metadata đang được sử dụng bởi các class đã nạp | Gần với lượng metadata sống |
| `capacity` | Không gian có thể dùng trong các chunk hiện được cấp | Có thể lớn hơn `used` vì còn chỗ trống trong chunk |
| `committed` | Bộ nhớ đã commit để JVM dùng cho Metaspace | Phần JVM đang giữ sẵn để cấp phát metadata |
| `reserved` | Không gian địa chỉ ảo đã reserve | Không có nghĩa toàn bộ vùng này đang chiếm RAM vật lý |

Ví dụ log có thể có dạng:

~~~text
Metaspace used 18M, committed 24M, reserved 1G
~~~

Con số chỉ mang tính minh họa. `reserved 1G` không có nghĩa ứng dụng đang dùng 1 GB RAM cho Metaspace. Khi class unload:

- `used` có thể giảm vì metadata của class đã được giải phóng.
- `capacity` có thể giảm hoặc thay đổi khi chunk được thu hồi/tái cấu trúc.
- `committed` có thể giảm khi JVM uncommit vùng không cần nữa; cũng có thể giữ nguyên nếu vùng trống được giữ để tái sử dụng.
- `reserved` có thể vẫn giữ nguyên vì JVM vẫn giữ vùng địa chỉ ảo cho các lần cấp phát sau.

Do đó, không kết luận có memory leak chỉ vì `reserved` không giảm. Hãy theo dõi xu hướng `used`, số class/class loader còn sống và `committed` sau các chu kỳ tải/xả ổn định.

## 6. Vì sao class loader leak ngăn Metaspace được thu hồi?

Nếu một class loader vẫn reachable, các class do nó định nghĩa không thể được unload. Một tham chiếu còn sót lại có thể giữ cả loader và metadata của hàng nghìn class.

Các nguồn giữ tham chiếu thường gặp:

- **Static registry/cache:** class thuộc application loader giữ lại instance, `Class<?>`, reflection object hoặc callback của plugin loader.
- **Thread context class loader:** thread pool sống lâu giữ context class loader trỏ tới loader của plugin đã dừng.
- **ThreadLocal:** giá trị trong ThreadLocal của thread dùng chung giữ object hoặc class thuộc loader cũ.
- **Thread chưa dừng:** thread được plugin tạo vẫn chạy, stack hoặc context của thread giữ class loader.
- **Listener/callback chưa đăng ký hủy:** framework hoặc event bus giữ listener được tạo bởi plugin.
- **MBean, logging handler hoặc shutdown hook:** đăng ký toàn cục vẫn giữ class/instance thuộc loader cũ.
- **JNI global reference:** mã native giữ tham chiếu tới object hoặc class Java.
- **Cache của framework:** cache giữ class, method handle, proxy hoặc metadata reflection mà không có cơ chế xóa theo vòng đời loader.

Một class loader leak thường biểu hiện bằng số class loader hoặc số class tăng dần sau mỗi lần deploy/reload, dù chức năng cũ đã dừng.

## 7. Đóng URLClassLoader không đồng nghĩa class đã unload

`URLClassLoader` triển khai `Closeable`. Gọi `close()` đóng các JAR/file resource mà loader đã mở và ngăn loader mở thêm resource từ các URL đó. Tuy nhiên, `close()` không trực tiếp unload class và không bảo đảm Metaspace được thu hồi ngay.

Ví dụ quản lý vòng đời plugin:

~~~java
import java.net.URL;
import java.net.URLClassLoader;

public class PluginRunner {
    public static void runPlugin(URL[] pluginUrls) throws Exception {
        try (URLClassLoader loader = new URLClassLoader(
                pluginUrls,
                PluginRunner.class.getClassLoader())) {

            Class<?> pluginType = Class.forName(
                    "com.example.plugin.EntryPoint", true, loader);

            Object plugin = pluginType.getDeclaredConstructor()
                    .newInstance();

            // Gọi API plugin và hoàn tất công việc trước khi rời scope.
            pluginType.getMethod("run").invoke(plugin);
        }
    }
}
~~~

Sau khi method kết thúc, local reference trong scope không còn được dùng. Tuy nhiên, loader chỉ đủ điều kiện thu hồi nếu không có tham chiếu nào khác giữ nó, class hoặc instance của nó. Nếu plugin đăng ký thread, listener hoặc object vào registry toàn cục, cần hủy đăng ký và dọn dẹp các tài nguyên đó trước khi kết thúc vòng đời plugin.

Trong ứng dụng thật, nên có lifecycle API rõ ràng như `start()`/`stop()` hoặc `close()` để plugin có thể dừng thread, đóng executor, gỡ listener, deregister MBean và xóa cache.

## 8. Không thể dùng System.gc() để bảo đảm unload ngay

Gọi `System.gc()` chỉ là yêu cầu JVM cân nhắc thực hiện garbage collection. JVM có thể bỏ qua yêu cầu, và việc chạy full GC chỉ để cố unload class có thể gây pause hoặc ảnh hưởng throughput.

Class unloading diễn ra trong chu kỳ GC phù hợp khi defining class loader có thể được thu hồi và cơ chế class unloading được bật. Không có API Java chuẩn để yêu cầu unload một class cụ thể ngay lập tức.

HotSpot theo dõi ngưỡng cấp phát metadata và có thể khởi chạy GC khi mức sử dụng chạm high-water mark. Sau GC, ngưỡng này được điều chỉnh theo lượng metadata thu hồi được. Vì vậy, việc đóng plugin không làm class unload đồng bộ ngay tại lệnh `close()`; thời điểm thu hồi phụ thuộc vào khả năng reachability và chu kỳ GC.

Với HotSpot hiện đại, class unloading được bật mặc định. Không tắt nó bằng `-XX:-ClassUnloading` trong ứng dụng thông thường, vì điều đó ngăn JVM thu hồi class metadata của các loader đã không còn dùng. Nếu cấu hình collector hoặc VM khác mặc định, hãy kiểm tra tài liệu của collector và giá trị flag đang chạy.

Đối với ứng dụng plugin, mục tiêu đúng là giải phóng mọi tham chiếu và tài nguyên thuộc plugin. Hãy để GC thực hiện thu hồi theo chu kỳ phù hợp thay vì buộc full GC sau mỗi lần reload.

## 9. Theo dõi class unloading bằng unified logging

Có thể bật log class load/unload để xác nhận class thực sự được unload:

~~~powershell
java -Xlog:class+unload=info -jar app.jar
~~~

Để xem thêm hoạt động Metaspace, cú pháp log phụ thuộc phiên bản JDK:

| Phiên bản | Log class unload và Metaspace |
| --- | --- |
| JDK 16–24 | `-Xlog:class+unload=info,gc+metaspace=info` |
| JDK 25 trở lên | `-Xlog:class+unload=info,metaspace=info` |

Từ JDK 25, log Metaspace được tách khỏi nhóm GC logging và dùng tag `metaspace`. Nội dung log vẫn cung cấp thông tin Metaspace nhưng không còn được trình bày như một phần của heap logging. Khi nâng JDK, cần cập nhật cấu hình log và parser tương ứng.

Có thể ghi log ra file và giới hạn dung lượng:

~~~powershell
java "-Xlog:class+unload=info,metaspace=info:file=logs/metaspace.log:time,level,tags:filecount=5,filesize=10M" -jar app.jar
~~~

Ví dụ này dùng tag Metaspace của JDK 25 trở lên. Nếu chạy JDK 16–24, thay bằng tag `gc+metaspace` theo bảng trên. Chỉ bật mức log chi tiết khi điều tra hoặc trong môi trường đã đánh giá overhead và dung lượng log.

## 10. Dùng jcmd để xem Metaspace và class loader

`jcmd` là công cụ chẩn đoán hiện hành để gửi lệnh tới JVM đang chạy. Chạy công cụ trên cùng máy và bằng cùng effective user/group đã khởi chạy tiến trình Java.

Liệt kê tiến trình Java:

~~~powershell
jcmd -l
~~~

Xem tóm tắt Metaspace:

~~~powershell
jcmd 12345 VM.metaspace basic=true
~~~

Xem mức sử dụng theo class loader:

~~~powershell
jcmd 12345 VM.metaspace show-loaders=true
~~~

Muốn xem thêm class được nạp bởi từng loader:

~~~powershell
jcmd 12345 VM.metaspace show-loaders=true show-classes=true
~~~

Thống kê riêng về class loader:

~~~powershell
jcmd 12345 VM.classloader_stats
~~~

Thay `12345` bằng PID thực tế. `VM.metaspace` có thể cung cấp tóm tắt, mức sử dụng theo loader, class, chunk và vùng địa chỉ ảo. Chọn mức chi tiết phù hợp vì việc liệt kê nhiều class có thể tạo thêm chi phí chẩn đoán.

## 11. Thay đổi chẩn đoán quan trọng từ JDK 25

Trước JDK 25, một phần thông tin Metaspace thường xuất hiện trong kết quả `jcmd GC.heap_info` cùng thông tin heap. Từ JDK 25, thông tin Metaspace được tách ra vì Metaspace nằm trong native memory, không phải Java heap.

Khi cần xem Metaspace trên JDK 25 trở lên, dùng:

~~~powershell
jcmd 12345 VM.metaspace
~~~

Không dựa vào `GC.heap_info` để lấy đầy đủ số liệu Metaspace trên JDK 25+. Dùng `VM.metaspace` để theo dõi vùng nhớ này và dùng `GC.heap_info` cho thông tin heap tương ứng.

Đây là thay đổi trong công cụ quan sát, không phải thay đổi cách class loader được thu hồi. JEP 387 vẫn là nền tảng của cơ chế Elastic Metaspace kể từ JDK 16.

## 12. Nhận biết class unloading hoạt động hay đang có leak

Một bài kiểm tra hữu ích cho ứng dụng plugin là lặp lại chu trình:

1. Nạp plugin bằng class loader riêng.
2. Chạy chức năng plugin.
3. Dừng plugin, đóng loader và gỡ mọi đăng ký/tài nguyên.
4. Đợi các chu kỳ GC tự nhiên trong điều kiện tải ổn định.
5. Ghi nhận log unload, số class loader, số class và Metaspace.
6. Lặp lại nhiều lần để so sánh xu hướng.

Các dấu hiệu cần phân biệt:

| Quan sát | Diễn giải có thể |
| --- | --- |
| Log có class unload, số loader giảm, `used` giảm | Loader đã được thu hồi; metadata tương ứng được giải phóng |
| `used` giảm nhưng `committed` giữ nguyên | Chunk rảnh được giữ lại để tái sử dụng; chưa đủ để kết luận leak |
| Số loader tăng sau mỗi lần reload | Có thể còn tham chiếu giữ loader cũ |
| Số class và `used` tăng đều qua nhiều chu kỳ | Có thể có class loader leak hoặc ứng dụng liên tục sinh class mới |
| `used` ổn định nhưng `committed` cao | JVM có thể đang giữ capacity để tái sử dụng |
| Không có class unload dù plugin đã dừng | Kiểm tra reachability, GC cycle và cấu hình class unloading |

Không kết luận từ một ảnh chụp duy nhất. Hãy so sánh sau nhiều chu kỳ tải/xả, cùng mức tải và cùng điều kiện GC.

## 13. Phân biệt OOME Metaspace với nhu cầu cấp phát hợp lệ

`OutOfMemoryError: Metaspace` có thể xuất hiện khi metadata cần thiết vượt giới hạn `-XX:MaxMetaspaceSize` hoặc JVM không thể cấp thêm native memory. Lỗi này không tự chứng minh ứng dụng có leak.

Các nguyên nhân thường gặp:

- Ứng dụng thật sự có số lượng class lớn, framework tạo proxy/bytecode nhiều.
- Nhiều class loader được tạo liên tục nhưng không được thu hồi.
- Class loader cũ bị giữ bởi thread, ThreadLocal, static cache, listener hoặc registry.
- `MaxMetaspaceSize` được đặt thấp hơn nhu cầu hợp lệ của ứng dụng.
- Tiến trình hoặc container thiếu native memory dù giới hạn Metaspace chưa chạm tới.

Hãy dùng `jcmd VM.metaspace` và class loader statistics để xác định số metadata đang sống, loader nào chiếm nhiều nhất và xu hướng sau GC. Nếu số class/loader tăng không ngừng, tìm và sửa leak trước khi chỉ tăng giới hạn.

`-XX:MaxMetaspaceSize` vẫn là tùy chọn hiện hành để giới hạn native memory dùng cho class metadata. Nếu ứng dụng có nhu cầu hợp lệ và đã xác minh không có leak, có thể đặt giới hạn phù hợp với ngân sách bộ nhớ của tiến trình/container. Không chọn một con số tùy ý chỉ để che cảnh báo.

Phân biệt với `-XX:MetaspaceSize`: tùy chọn này đặt high-water mark ban đầu để JVM cân nhắc GC do áp lực metadata, không phải dung lượng Metaspace được cấp cố định và cũng không phải giới hạn tối đa. `-XX:MaxMetaspaceSize` mới là giới hạn trên. Hãy giữ mặc định của JVM trừ khi số liệu tải thực tế cho thấy cần điều chỉnh.

## 14. Không dùng lại tùy chọn MetaspaceReclaimPolicy cũ

JDK 16 Release Notes từng giới thiệu `-XX:MetaspaceReclaimPolicy=(balanced|aggressive|none)` để tinh chỉnh cách thu hồi Metaspace. Tuy nhiên, tùy chọn này đã bị obsoleted trong JDK 21 và bị bỏ qua khi chạy; không dùng nó trong cấu hình JVM hiện đại.

Elastic Metaspace vẫn hoạt động mà không cần bật một reclaim policy riêng. Hãy dựa vào cơ chế mặc định, vòng đời class loader và số liệu quan sát. Nếu gặp vấn đề bộ nhớ, kiểm tra loader reachability, `used`/`committed` và giới hạn native memory thay vì thêm flag đã lỗi thời.

## 15. Quy trình thực hành chẩn đoán Metaspace

1. Ghi nhận phiên bản JDK, collector, PID và các JVM flags đang dùng.
2. Bật `-Xlog:class+unload=info`; thêm tag Metaspace phù hợp phiên bản JDK.
3. Dùng `jcmd PID VM.metaspace basic=true` để lấy baseline.
4. Dùng `jcmd PID VM.metaspace show-loaders=true` để tìm loader sử dụng nhiều metadata.
5. Dùng `jcmd PID VM.classloader_stats` để theo dõi số loader và số class.
6. Lặp lại chu trình deploy/reload plugin dưới tải ổn định.
7. Kiểm tra class unload log và xu hướng `used`, `committed` sau các chu kỳ GC.
8. Nếu loader cũ còn sống, tìm tham chiếu giữ loader và dọn thread, ThreadLocal, listener, registry hoặc cache.
9. Chỉ điều chỉnh `-XX:MaxMetaspaceSize` sau khi phân biệt nhu cầu hợp lệ với leak.
10. Trên JDK 25+, lấy số liệu bằng `VM.metaspace` thay vì trông chờ `GC.heap_info` hiển thị Metaspace.

**Ghi nhớ:** Elastic Metaspace từ JDK 16 giúp JVM tái sử dụng chunk và trả vùng committed không còn cần thiết về hệ điều hành sau class unloading. Class chỉ có thể unload khi defining class loader đủ điều kiện được GC thu hồi; vì vậy, dọn vòng đời plugin và loại bỏ tham chiếu giữ loader là điều kiện cốt lõi. Theo dõi `used`, `committed`, class unload log và thống kê loader; không nhầm `reserved` với RAM đang dùng. Trên JDK 25+, dùng log tag `metaspace` và `jcmd VM.metaspace`. Không dùng `MetaspaceReclaimPolicy` vì tùy chọn này đã bị obsoleted từ JDK 21.

## Nguồn tham khảo chính thức

- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387)
- [Consolidated JDK 16 Release Notes — JEP 387](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [Java Language Specification — Unloading of Classes and Interfaces, Section 12.7](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
- [HotSpot Virtual Machine Garbage Collection Tuning Guide — Class Metadata, JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/other-considerations.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Troubleshoot Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [JDK 21 Release Notes — MetaspaceReclaimPolicy Obsoleted](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [JDK 25 Release Notes — Metaspace Logging and jcmd Changes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html)
