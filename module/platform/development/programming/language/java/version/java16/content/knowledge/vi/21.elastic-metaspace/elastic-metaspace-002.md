# Phân biệt heap, metaspace, compressed class space và RSS

Khi theo dõi bộ nhớ của một tiến trình Java, bốn số liệu thường bị nhầm lẫn là **Java heap**, **Metaspace**, **Compressed Class Space** và **RSS**. Chúng mô tả những phạm vi khác nhau: heap chứa object Java; Metaspace lưu metadata của class trong native memory; Compressed Class Space là vùng dành riêng cho một phần metadata khi JVM dùng compressed class pointers; còn RSS là lượng trang bộ nhớ của toàn tiến trình hiện đang cư trú trong RAM theo cách đo của hệ điều hành.

Không thể cộng bốn con số này để ra tổng bộ nhớ tiến trình. Compressed Class Space thuộc vùng quản lý metadata của Metaspace, còn RSS có thể bao gồm các trang của heap, Metaspace và nhiều vùng khác. Muốn chẩn đoán đúng, cần hiểu từng vùng, phân biệt **used**, **committed** và **reserved**, rồi đối chiếu số liệu JVM với số liệu hệ điều hành.

## 1. Bốn khái niệm đo bốn phạm vi khác nhau

| Khái niệm | Chứa hoặc đo gì? | Nằm ở đâu? | Công cụ quan sát chính |
| --- | --- | --- | --- |
| **Java heap** | Object và array được tạo trong ứng dụng Java | Vùng heap do JVM quản lý | GC log, MemoryMXBean, jcmd GC.heap_info |
| **Metaspace** | Metadata nội bộ của class và cấu trúc liên quan do class loader quản lý | Native memory do HotSpot quản lý | MemoryPoolMXBean, NMT, jcmd VM.classloader_stats |
| **Compressed Class Space (CCS)** | Một phần metadata kiểu Klass khi dùng compressed class pointers | Vùng địa chỉ riêng trong cơ chế Metaspace | Memory pool Compressed Class Space, NMT và JVM flags |
| **RSS** | Các trang bộ nhớ của tiến trình đang cư trú trong RAM | Góc nhìn của hệ điều hành | ps, /proc, Task Manager hoặc công cụ OS tương ứng |

Java heap và Metaspace là hai vùng quản lý bộ nhớ khác nhau trong HotSpot. RSS là số đo ở cấp tiến trình, vì vậy nó có thể bao gồm trang của cả hai vùng cùng với thread stack, code cache, cấu trúc GC, thư viện native, direct buffer và memory-mapped file.

## 2. Java heap: nơi chứa object và array

Java heap là vùng bộ nhớ JVM dùng để cấp phát object và array. Ví dụ:

~~~java
byte[] payload = new byte[1024 * 1024];
List<String> names = new ArrayList<>();
names.add("Order");
names.add("Payment");
~~~

Các object byte array, ArrayList và String được quản lý trong heap. Garbage Collector thu hồi vùng nhớ của những object không còn reachable theo quy tắc của collector.

Ba số liệu heap cần phân biệt:

- **Used:** dung lượng heap hiện đang được sử dụng cho object.
- **Committed:** dung lượng JVM đã cam kết để heap có thể sử dụng.
- **Max:** giới hạn heap tối đa mà JVM cho phép trong cấu hình hiện tại.

Các tùy chọn thường dùng:

~~~bash
java -Xms256m -Xmx2g -jar application.jar
~~~

- **-Xms256m** đặt kích thước heap ban đầu.
- **-Xmx2g** đặt giới hạn heap tối đa.

**-Xmx2g** không có nghĩa tiến trình lập tức chiếm 2 GB RAM. Đây là giới hạn heap; heap có thể được mở rộng theo nhu cầu và các trang bộ nhớ chỉ xuất hiện trong RSS khi chúng thực sự được đưa vào RAM.

Nếu heap used tăng liên tục sau các chu kỳ GC, cần điều tra object còn được giữ tham chiếu, cache không giới hạn hoặc cấu trúc dữ liệu tăng không kiểm soát. Nhưng nếu RSS tăng trong khi heap used ổn định, nguyên nhân có thể nằm ở Metaspace, thread, native allocation hoặc các vùng khác.

## 3. Metaspace: metadata của class trong native memory

Metaspace lưu metadata mà HotSpot cần để biểu diễn class đã được nạp. Metadata này không phải object thông thường mà ứng dụng tạo bằng new; JVM và class loader quản lý nó.

Từ JDK 8, HotSpot cấp phát class metadata trong native memory. Dung lượng này không nằm trong Java heap và có giới hạn riêng qua tùy chọn:

~~~bash
java -XX:MaxMetaspaceSize=512m -jar application.jar
~~~

Nếu không đặt **MaxMetaspaceSize**, giới hạn này mặc định không bị ràng buộc bởi một giá trị nhỏ cố định; khả năng cấp phát vẫn chịu giới hạn tài nguyên native và hệ điều hành.

HotSpot quản lý Metaspace theo class loader. Khi class loader được thu hồi và các class do nó định nghĩa có thể được unload, phần metadata tương ứng có thể được giải phóng, tái sử dụng hoặc trả lại cho hệ điều hành.

### Những tình huống làm Metaspace tăng

- Ứng dụng nạp ngày càng nhiều class.
- Framework sinh proxy hoặc class động với số lượng tăng theo thời gian.
- Plugin hoặc module được nạp bằng class loader riêng.
- Ứng dụng triển khai lại module nhưng class loader cũ vẫn còn được tham chiếu.
- Cache, thread context class loader hoặc registry giữ class loader lâu hơn dự kiến.

Điểm cần kiểm tra không chỉ là số class đã nạp, mà còn là số class loader và vòng đời của chúng. Một class loader còn reachable có thể giữ lại metadata của các class do nó định nghĩa.

## 4. Elastic Metaspace từ Java 16

Java 16 đưa **JEP 387: Elastic Metaspace** vào HotSpot. Thay đổi này cải tiến bộ cấp phát Metaspace để giảm lãng phí bộ nhớ, đặc biệt trong ứng dụng tạo nhiều class loader nhỏ. Khi class được unload, các vùng Metaspace không còn cần thiết có thể được uncommit và trả lại hệ điều hành với mức hạt nhỏ hơn.

Điều này giúp Metaspace linh hoạt hơn khi ứng dụng nạp rồi unload class theo vòng đời plugin hoặc module. Tuy nhiên, không nên kỳ vọng RSS giảm ngay lập tức hoặc giảm đúng bằng lượng used đã giảm:

- Metadata được giải phóng khi class loader và class liên quan đủ điều kiện unload.
- Các chunk có thể được tái sử dụng trước khi cần trả lại hệ điều hành.
- Metaspace committed có thể giảm khi JVM uncommit vùng trống.
- RSS còn phản ánh heap, thread stack, native memory, thư viện và các trang khác.

Vì vậy, sau khi unload class, hãy theo dõi đồng thời used, committed của Metaspace và RSS theo thời gian. Một lần chụp số liệu đơn lẻ không đủ để kết luận có rò rỉ.

## 5. Compressed Class Space là gì?

Trên HotSpot 64-bit, khi **compressed class pointers** được sử dụng, JVM có thể biểu diễn con trỏ tới metadata class bằng offset 32-bit thay vì địa chỉ đầy đủ. Điều này giúp giảm kích thước tham chiếu class trong những cấu hình phù hợp.

Vùng **Compressed Class Space** là không gian địa chỉ dành cho phần metadata kiểu Klass được quản lý theo cơ chế compressed class pointers. Đây là vùng liên quan đến Metaspace, không phải một Java heap riêng.

Tùy chọn liên quan:

- **-XX:+UseCompressedClassPointers:** bật cơ chế compressed class pointers khi cấu hình JVM hỗ trợ.
- **-XX:CompressedClassSpaceSize=size:** đặt kích thước vùng địa chỉ dành cho compressed class space.
- **-XX:MaxMetaspaceSize=size:** đặt giới hạn tổng cho phần Metaspace committed, bao gồm committed compressed class space và metadata Metaspace còn lại.

Trên cấu hình HotSpot 64-bit thông thường của JDK 16, compressed class pointers được bật mặc định khi điều kiện cho phép. Kích thước mặc định của compressed class space là 1 GB. Đây là kích thước **reserved**, không có nghĩa JVM lập tức dùng 1 GB RAM; vùng này được commit theo nhu cầu.

### CCS không chứa toàn bộ metadata của class

Không phải mọi metadata đều nằm trong Compressed Class Space:

- Metadata kiểu Klass nằm trong class space khi compressed class pointers được bật.
- Các metadata class khác nằm trong phần Metaspace còn lại.
- Nếu không dùng compressed class pointers, vùng class space riêng có thể không được sử dụng theo cách này.

Do đó, khi xem báo cáo Metaspace, cần hiểu dòng class space là một phần cấu thành trong phạm vi metadata, không cộng nó lần thứ hai vào tổng Metaspace.

### Phân biệt compressed class pointers và compressed oops

Hai khái niệm có mục đích khác nhau:

| Cơ chế | Nén loại tham chiếu nào? |
| --- | --- |
| **Compressed oops** | Tham chiếu tới object Java trên heap |
| **Compressed class pointers** | Tham chiếu tới metadata class trong HotSpot |

Không nên coi hai flag này là một. Chúng có thể cùng được bật trong một cấu hình HotSpot, nhưng kiểm soát hai loại tham chiếu khác nhau.

## 6. Reserved, committed và used

Đây là ba khái niệm quan trọng khi đọc báo cáo JVM:

| Trạng thái | Ý nghĩa | Có đồng nghĩa với RAM đang dùng không? |
| --- | --- | --- |
| **Reserved** | JVM giữ trước một vùng địa chỉ ảo để có thể sử dụng sau | Không |
| **Committed** | JVM đã commit một phần vùng nhớ để phục vụ cấp phát | Không nhất thiết toàn bộ đang resident trong RAM |
| **Used** | Phần dung lượng hiện được allocator sử dụng cho dữ liệu hoặc metadata | Không nhất thiết bằng RSS |

Ví dụ, Compressed Class Space có thể reserve 1 GB địa chỉ ảo nhưng mới commit một phần nhỏ. Con số reserved lớn không có nghĩa tiến trình đã chiếm từng ấy RAM vật lý.

Tương tự, heap có max 2 GB nhưng committed chỉ 512 MB và used 300 MB. Không thể lấy max làm số RAM mà tiến trình đang sử dụng.

Với Metaspace, used mô tả metadata đã được cấp phát; committed là phần vùng nhớ JVM đã commit; reserved là vùng địa chỉ được dành trước. Các con số này giúp phân biệt nhu cầu metadata thực tế với dung lượng JVM đang giữ sẵn.

## 7. RSS: lượng bộ nhớ tiến trình đang cư trú trong RAM

**RSS (Resident Set Size)** là số trang bộ nhớ của tiến trình hiện đang nằm trong RAM theo cách đo của hệ điều hành. RSS không phải một vùng bộ nhớ riêng do JVM quản lý.

RSS của tiến trình Java có thể bao gồm các trang resident từ:

- Java heap.
- Metaspace và Compressed Class Space đã commit, có trang resident.
- Thread stack.
- JIT code cache.
- Cấu trúc dữ liệu của Garbage Collector.
- Direct byte buffers và native allocations.
- JNI hoặc thư viện native bên thứ ba.
- Shared libraries và memory-mapped files.

RSS không bằng **-Xmx**, không bằng heap committed, cũng không bằng tổng NMT committed. Các hệ điều hành có cách trình bày số liệu và xử lý trang dùng chung khác nhau; RSS là một chỉ số để quan sát tiến trình từ phía OS.

### Xem RSS trên Linux

~~~bash
ps -o pid,rss,vsz,comm -p <pid>
~~~

- **rss:** Resident Set Size, thường được hiển thị theo KB.
- **vsz:** kích thước không gian bộ nhớ ảo của tiến trình.

Có thể xem thêm trong:

~~~bash
cat /proc/<pid>/status
~~~

Các dòng thường quan tâm:

- **VmRSS:** resident set size hiện tại.
- **VmHWM:** mức RSS cao nhất đã ghi nhận.
- **VmSize:** kích thước không gian bộ nhớ ảo.

VmRSS là số liệu tổng hợp ở cấp OS; không thể dùng nó để suy ra riêng heap hoặc Metaspace. Trên Linux, trường VmRSS là số liệu xấp xỉ; khi cần phân tích mapping chi tiết hơn, có thể xem smaps hoặc smaps_rollup. Các trang shared library có thể được tính vào RSS của nhiều tiến trình, vì vậy không nên cộng RSS của nhiều tiến trình rồi coi kết quả là lượng RAM vật lý duy nhất đã sử dụng.

### Xem bộ nhớ tiến trình trên Windows

Trong PowerShell:

~~~powershell
Get-Process -Id <pid> |
    Select-Object Id, WorkingSet64, PrivateMemorySize64, VirtualMemorySize64
~~~

**WorkingSet64** biểu diễn working set của tiến trình, tức lượng trang hiện diện trong bộ nhớ vật lý theo cách Windows báo cáo. **VirtualMemorySize64** là số liệu không gian bộ nhớ ảo; không đồng nghĩa RAM đang dùng.

### Xem RSS trên macOS

Có thể dùng:

~~~bash
ps -o pid,rss,vsz,comm -p <pid>
~~~

Cần đọc đơn vị và ý nghĩa theo công cụ của hệ điều hành đang sử dụng. Khi so sánh giữa máy hoặc nền tảng khác nhau, hãy giữ cùng phương pháp đo.

## 8. Vì sao RSS có thể lớn hơn heap?

Giả sử một JVM có heap used 400 MB và committed 600 MB. RSS của tiến trình vẫn có thể là 850 MB vì tiến trình còn cần:

- Metaspace và class space.
- Stack của các thread.
- Code cache chứa mã JIT đã biên dịch.
- Cấu trúc nội bộ của GC.
- Direct buffer hoặc native memory.
- Các trang thư viện và file được ánh xạ vào tiến trình.

Đây là tình huống bình thường. RSS đo toàn tiến trình, trong khi heap used chỉ đo object Java đang chiếm heap.

Ngược lại, RSS có thể thấp hơn tổng số reserved rất nhiều vì vùng địa chỉ ảo được reserve không nhất thiết có trang vật lý tương ứng.

Không nên dùng công thức:

~~~text
RSS = Heap + Metaspace + Compressed Class Space
~~~

Công thức này sai vì CCS không phải một vùng độc lập để cộng thêm vào Metaspace, và RSS còn chứa nhiều thành phần ngoài heap cùng metadata.

## 9. Quan sát heap bằng jcmd và JMX

Trên JDK 16, có thể dùng jcmd để xem thông tin heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Lệnh này cung cấp thông tin tổng quan về Java heap. Đây là số liệu JVM, không phải RSS của tiến trình.

Trong ứng dụng, dùng **MemoryMXBean** để lấy thông tin heap:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage heap =
    ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

System.out.println("Heap used: " + heap.getUsed());
System.out.println("Heap committed: " + heap.getCommitted());
System.out.println("Heap max: " + heap.getMax());
~~~

getMax() có thể trả về -1 nếu không xác định được giới hạn tối đa. Không nên giả định mọi collector hoặc runtime đều trả về cùng một giá trị.

## 10. Quan sát Metaspace và Compressed Class Space

Có thể dùng **MemoryPoolMXBean** để liệt kê các memory pool mà JVM cung cấp:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

for (MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {

    String name = pool.getName();

    if (name.contains("Metaspace")
            || name.contains("Compressed Class Space")) {

        MemoryUsage usage = pool.getUsage();

        if (usage != null) {
            System.out.println("Pool: " + name);
            System.out.println("Used: " + usage.getUsed());
            System.out.println("Committed: " + usage.getCommitted());
            System.out.println("Max: " + usage.getMax());
        }
    }
}
~~~

Tên và tập memory pool phụ thuộc JVM implementation. Ví dụ trên minh họa các tên pool thường thấy ở HotSpot; không nên viết ứng dụng nghiệp vụ phụ thuộc cứng vào tên pool của một nhà cung cấp JVM.

Trên JDK 16, có thể xem thống kê class loader:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Lệnh này hữu ích khi nghi ngờ số class loader tăng liên tục hoặc class loader cũ chưa được giải phóng. Danh sách diagnostic command có thể thay đổi theo JVM; kiểm tra lệnh hỗ trợ bằng:

~~~bash
jcmd <pid> help
~~~

## 11. Dùng Native Memory Tracking để xem bộ nhớ HotSpot

**Native Memory Tracking (NMT)** theo dõi các vùng native memory nội bộ mà HotSpot quản lý. NMT không bật mặc định; cần bật khi khởi chạy JVM.

Ví dụ bật chế độ summary:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Sau đó lấy báo cáo:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
~~~

Báo cáo có tổng reserved và committed, cùng các nhóm như Java Heap, Class, Thread, Code, GC và Compiler. Nhóm **Class** giúp quan sát phần native memory liên quan tới class metadata.

Có thể lấy baseline sau khi ứng dụng đã khởi động và ổn định:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

Sau một khoảng thời gian hoặc sau khi chạy một workload:

~~~bash
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

Báo cáo diff cho thấy từng nhóm tăng hoặc giảm so với baseline. Nếu cần phân tích sâu hơn theo call site, bật chế độ detail ngay khi khởi chạy:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

NMT có giới hạn cần nhớ:

- NMT theo dõi allocation nội bộ của HotSpot, không theo dõi đầy đủ native allocation do thư viện bên thứ ba, JNI hoặc các thư viện class của JDK thực hiện.
- NMT không bao phủ hoàn toàn mọi vùng bộ nhớ liên quan đến CDS archive.
- NMT không phải công cụ đo RSS; số liệu reserved và committed không thể thay trực tiếp cho số liệu của OS.
- Tài liệu JDK 16 ghi nhận overhead hiệu năng khoảng 5–10% khi bật NMT; cần cân nhắc khi bật trong môi trường production.

NMT rất hữu ích để tìm nhóm bộ nhớ HotSpot tăng theo thời gian, nhưng nếu RSS tăng mà NMT không giải thích được, hãy kiểm tra thêm native library, JNI, direct buffer và số liệu hệ điều hành.

## 12. Đối chiếu số liệu để tìm nguyên nhân tăng bộ nhớ

Nên lấy số liệu ở cùng thời điểm hoặc trong cùng một khoảng thời gian:

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| Heap used tăng liên tục sau GC | Object bị giữ tham chiếu, cache hoặc collection tăng không giới hạn |
| Heap ổn định nhưng Metaspace used tăng | Số class tăng, class loader mới liên tục hoặc class loader không unload |
| CCS used tăng gần giới hạn | Số lượng metadata kiểu Klass tăng; kiểm tra class loading và class loader |
| Metaspace used giảm nhưng committed chưa giảm | JVM có thể giữ chunk để tái sử dụng; theo dõi thêm theo thời gian |
| Heap và Metaspace ổn định nhưng RSS tăng | Kiểm tra thread stack, direct/native allocation, JNI, thư viện và mapped files |
| NMT committed tăng ở Thread | Số lượng thread hoặc stack memory tăng |
| NMT không tăng tương ứng nhưng RSS tăng | Kiểm tra allocation ngoài phạm vi NMT và shared/native mappings |
| RSS cao nhưng reserved rất lớn | Kiểm tra trang resident thực tế; reserved không phải RAM đang dùng |

Không kết luận có memory leak chỉ vì RSS tăng sau khi chạy một workload. Cần so sánh qua nhiều chu kỳ, xác định nhóm bộ nhớ tăng và kiểm tra xem nó có giảm hoặc ổn định sau khi workload kết thúc hay không.

## 13. Phân biệt các loại OutOfMemoryError

Thông báo lỗi thường cho biết vùng cấp phát nào đã cạn:

| Thông báo | Vùng liên quan | Điều cần kiểm tra |
| --- | --- | --- |
| OutOfMemoryError: Java heap space | Java heap | Object retention, kích thước heap, workload |
| OutOfMemoryError: Metaspace | Class metadata trong Metaspace | Class loading, class loader lifecycle, MaxMetaspaceSize |
| OutOfMemoryError: Compressed class space | Vùng class metadata được nén | CCS capacity và số class metadata kiểu Klass |
| Native allocation failure hoặc lỗi hết bộ nhớ hệ thống | Native memory hoặc giới hạn hệ điều hành | NMT, JNI, direct memory, thread, OS/cgroup limits |

OutOfMemoryError: Compressed class space không có nghĩa Java heap đã đầy. Tăng -Xmx không trực tiếp giải quyết giới hạn của CCS. Tương tự, tăng MaxMetaspaceSize không làm một native allocation ngoài HotSpot tự động thành công.

## 14. Quy trình kiểm tra khi RSS tăng bất thường

1. Ghi lại RSS hoặc working set từ hệ điều hành cùng PID và thời điểm.
2. Lấy jcmd <pid> GC.heap_info để kiểm tra heap.
3. Lấy thống kê class loader bằng jcmd <pid> VM.classloader_stats.
4. Nếu JVM được khởi chạy với NMT, lấy VM.native_memory summary và so sánh baseline.
5. Kiểm tra memory pool Metaspace và Compressed Class Space qua JMX.
6. Kiểm tra số lượng thread, direct buffer và native library.
7. So sánh số liệu qua nhiều thời điểm sau khi workload đã ổn định.
8. Chỉ điều chỉnh -Xmx, MaxMetaspaceSize hoặc CompressedClassSpaceSize sau khi xác định đúng vùng đang đạt giới hạn.

Nếu cần bật NMT cho một lần điều tra mới, phải khởi động JVM với flag tương ứng; không thể bật lại NMT cho một tiến trình đang chạy chỉ bằng lệnh jcmd.

## 15. Kết luận

Java heap chứa object và array. Metaspace chứa class metadata trong native memory. Compressed Class Space là vùng dành cho một phần metadata kiểu Klass khi HotSpot dùng compressed class pointers; nó thuộc phạm vi quản lý Metaspace và không được cộng hai lần. RSS là số đo của hệ điều hành về các trang bộ nhớ tiến trình đang cư trú trong RAM, bao gồm nhiều thành phần ngoài heap và Metaspace.

Khi đọc số liệu, hãy tách used, committed và reserved: reserved là vùng địa chỉ được dành trước, committed là vùng JVM đã commit, còn used là phần đang được allocator sử dụng. Không số nào trong ba số đó tự động bằng RSS.

Java 16 với Elastic Metaspace có khả năng trả lại vùng metadata không còn cần thiết cho hệ điều hành sau khi class được unload. Để chẩn đoán, kết hợp GC.heap_info, VM.classloader_stats, JMX MemoryPoolMXBean, Native Memory Tracking và công cụ đo RSS của hệ điều hành. Đối chiếu theo thời gian sẽ giúp xác định đúng vùng tăng bộ nhớ và tránh điều chỉnh nhầm heap khi vấn đề thực tế nằm ở native memory hoặc class loading.

## Tài liệu tham khảo

- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387)
- [JDK 16 Release Notes — JEP 387: Elastic Metaspace](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [Java SE 16 Garbage Collection Tuning Guide — Class Metadata](https://docs.oracle.com/en/java/javase/16/gctuning/other-considerations.html)
- [Java SE 16 Troubleshooting Guide — OutOfMemoryError](https://docs.oracle.com/en/java/javase/16/troubleshoot/troubleshoot-memory-leaks.html)
- [Java SE 16 Java Virtual Machine Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/16/vm/java-virtual-machine-guide.pdf)
- [The jcmd Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jcmd.html)
- [The java Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [Linux Kernel Documentation — /proc process memory fields](https://www.kernel.org/doc/html/latest/filesystems/proc.html)

