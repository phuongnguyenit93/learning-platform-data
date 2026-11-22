# jstat và metric runtime trong Java

## Mục tiêu

Sau bài này, bạn có thể dùng jstat để lấy mẫu thống kê của một HotSpot JVM đang chạy; chọn đúng nhóm metric cho garbage collection, heap, metaspace, class loading và JIT compiler; đọc các cột dung lượng, mức sử dụng và bộ đếm tích lũy; phân biệt snapshot với xu hướng theo thời gian; phát hiện dấu hiệu GC pressure hoặc memory growth; thu thập metric bằng Java Management Extensions (JMX) và Platform MXBeans; kết hợp jstat với jcmd, Java Flight Recorder (JFR), JDK Mission Control (JMC) và GC logs; và xây dựng quy trình theo dõi runtime có thể lặp lại.

## 1. jstat là gì?

**jstat** (Java Virtual Machine Statistics Monitoring Tool) là công cụ dòng lệnh trong JDK dùng để đọc các performance counter do Java HotSpot VM cung cấp. Công cụ lấy số liệu về tài nguyên và hoạt động runtime của một JVM đang chạy, đặc biệt hữu ích khi điều tra heap sizing, garbage collection, class loading và JIT compilation.

jstat có thể giúp trả lời:

- Eden, survivor và old generation đang được sử dụng đến mức nào?
- Số lần young GC và full GC tăng ra sao?
- Tổng thời gian JVM đã dành cho GC là bao nhiêu?
- Metaspace và compressed class space có đang tăng không?
- JVM đã load/unload bao nhiêu class?
- JIT compiler đã biên dịch bao nhiêu method?
- Một đợt GC hoặc thay đổi heap có xảy ra giữa hai lần lấy mẫu không?

jstat đọc instrumentation có sẵn trong HotSpot. Theo Troubleshooting Guide của Java SE 26, bạn không cần khởi động JVM với một tùy chọn đặc biệt để bật instrumentation này; nó được bật mặc định. Tuy nhiên, instrumentation không truy cập được trên filesystem FAT32.

jstat chủ yếu là công cụ quan sát thống kê. Nó không cho biết đầy đủ object nào giữ heap, method nào tạo allocation, thread nào đang gây latency hay request nào đang chậm. Để tìm nguyên nhân, thường phải kết hợp với GC log, JFR/JMC, JMX, thread dump, heap dump hoặc metric của hệ điều hành.

## 2. Trạng thái hỗ trợ và khác biệt giữa các phiên bản

Troubleshooting Guide Java SE 26 vẫn có mục mô tả jstat và cách sử dụng công cụ. Trang này liên kết tới tài liệu lệnh jstat trong bộ Tool Specifications; liên kết hiện chuyển tới tài liệu Java SE 17. Tài liệu lệnh đó đánh dấu jstat là **experimental and unsupported**, đồng thời cảnh báo các option và chức năng có thể thay đổi hoặc bị loại bỏ ở các phiên bản sau.

Điều này có hai hệ quả thực tế:

1. jstat vẫn hữu ích để đọc hệ thống hiện có và quan sát nhanh HotSpot runtime khi JDK đang cài cung cấp công cụ.
2. Không nên xây hệ thống monitoring mới phụ thuộc cứng vào một bộ cột hoặc format jstat. Hãy kiểm tra option thực tế bằng jstat -options trên đúng JDK và ưu tiên JMX/JFR/metrics có contract rõ ràng khi cần tích hợp lâu dài.

Không nhầm jstat với jcmd. jstat hiển thị các bảng thống kê dựa trên performance counter. jcmd gửi diagnostic command tới JVM, ví dụ xem heap info, in thread dump hoặc điều khiển JFR. Hai công cụ bổ sung cho nhau.

## 3. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
jstat [generalOption]
jstat outputOption [-t] [-h lines] [-J javaOption] vmid [interval[s|ms] [count]]
~~~

Trong đó:

- generalOption: tùy chọn trợ giúp hoặc liệt kê các nhóm thống kê.
- outputOption: một nhóm metric, ví dụ -gcutil, -gc, -class hoặc -compiler.
- -t: thêm cột Timestamp, biểu diễn số giây đã trôi qua kể từ khi JVM đích khởi động.
- -h n: lặp lại hàng tiêu đề sau mỗi n mẫu.
- -J javaOption: truyền tùy chọn cho JVM chạy chính công cụ jstat, không phải JVM đích.
- vmid: Virtual Machine Identifier dùng để xác định JVM cần theo dõi.
- interval: khoảng cách giữa hai lần lấy mẫu; đơn vị mặc định là millisecond, có thể ghi rõ s hoặc ms.
- count: số mẫu cần in; nếu bỏ qua, jstat tiếp tục lấy mẫu cho tới khi JVM kết thúc hoặc người dùng dừng lệnh.

Ví dụ lấy 10 mẫu, mỗi mẫu cách nhau một giây:

~~~bash
jstat -gcutil <PID> 1000 10
~~~

Có thể viết khoảng thời gian bằng đơn vị rõ ràng:

~~~bash
jstat -gcutil <PID> 1s 10
~~~

Theo tài liệu, interval và count phải là số nguyên dương. Nếu không truyền count, lệnh chạy liên tục; nhấn Ctrl+C để dừng.

### Xem trợ giúp và danh sách option

~~~bash
jstat -help
jstat -options
~~~

jstat -options liệt kê những stat option mà bản jstat đang chạy hỗ trợ. Các option có thể khác theo JDK release, vendor và platform. Luôn kiểm tra trên đúng máy đích trước khi dùng một lệnh trong tài liệu cũ.

Các nhóm thường gặp gồm:

- -class: thống kê class loader.
- -compiler: thống kê JIT compiler.
- -gc: dung lượng và mức sử dụng các vùng heap.
- -gccapacity: dung lượng tối thiểu, tối đa và hiện tại của generation/space.
- -gccause: thống kê GC kèm nguyên nhân của lần GC gần nhất và lần hiện tại nếu có.
- -gcnew: thống kê new generation.
- -gcnewcapacity: dung lượng new generation.
- -gcold: thống kê old generation và metaspace.
- -gcoldcapacity: dung lượng old generation.
- -gcmetacapacity: dung lượng metaspace và compressed class space.
- -gcutil: tóm tắt mức sử dụng theo phần trăm và bộ đếm GC.
- -printcompilation: thống kê method compilation gần nhất.

Nếu một option không xuất hiện trong jstat -options, đừng giả định JVM đó hỗ trợ nó.

## 4. Xác định JVM đích bằng VMID

jstat dùng VMID (Virtual Machine Identifier) để xác định JVM. Thành phần cần thiết nhất là LVMID (Local Virtual Machine Identifier). LVMID thường là process ID của hệ điều hành, nhưng không phải lúc nào cũng vậy.

### Tìm LVMID

Dùng jps:

~~~bash
jps -l
~~~

Hoặc dùng jcmd:

~~~bash
jcmd -l
~~~

Trên Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Ví dụ jps hiển thị:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

Trong trường hợp này, 4128 có thể là LVMID của OrderService. Hãy xác nhận đúng process trước khi thu thập dữ liệu.

Trong Docker hoặc container có PID namespace riêng, công cụ chạy từ host có thể không nhìn thấy JVM bên trong. Hãy tìm PID từ đúng namespace/container và chạy công cụ tại môi trường có thể truy cập JVM đó.

### Cấu trúc VMID

Cấu trúc tổng quát được mô tả như sau:

~~~text
[protocol:][//]lvmid[@hostname[:port][/servername]]
~~~

- protocol: giao thức giao tiếp; nếu không chỉ định và chỉ theo dõi local JVM, jstat dùng giao thức local tối ưu theo platform.
- lvmid: ID của JVM đích.
- hostname: tên host hoặc IP của máy đích.
- port: cổng RMI registry khi dùng giao thức RMI.
- servername: tên remote object, phụ thuộc implementation.

Với local JVM, thường chỉ cần PID/LVMID:

~~~bash
jstat -gcutil 4128 1000 10
~~~

## 5. Lấy mẫu định kỳ và đọc output

Output của jstat là bảng văn bản. Mỗi dòng là một lần lấy mẫu; hàng đầu tiên chứa tên cột.

Ví dụ:

~~~bash
jstat -gcutil -t -h 5 4128 1s 12
~~~

Lệnh trên:

- Chọn nhóm thống kê -gcutil.
- Thêm Timestamp bằng -t.
- Lặp lại tiêu đề sau mỗi 5 mẫu bằng -h 5.
- Theo dõi JVM có LVMID 4128.
- Lấy mẫu mỗi giây.
- Dừng sau 12 mẫu.

Timestamp là thời gian đã trôi qua tính bằng giây từ lúc JVM đích khởi động, không phải ngày giờ tuyệt đối. Độ phân giải có thể thay đổi khi máy chịu tải cao.

Không lấy một dòng duy nhất để kết luận có memory leak hoặc GC bất thường. Hãy quan sát nhiều mẫu, so sánh các bộ đếm tích lũy và đối chiếu với thời điểm request, deploy hoặc thay đổi tải.

## 6. Theo dõi GC bằng -gcutil

-gcutil là một trong những option hữu ích nhất để quan sát nhanh garbage collection. Nó hiển thị mức sử dụng của các space dưới dạng phần trăm cùng số lần và thời gian GC.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| S0 | Phần trăm sử dụng survivor space 0 |
| S1 | Phần trăm sử dụng survivor space 1 |
| E | Phần trăm sử dụng Eden |
| O | Phần trăm sử dụng old space |
| M | Phần trăm sử dụng Metaspace |
| CCS | Phần trăm sử dụng Compressed Class Space, nếu runtime hiển thị |
| YGC | Số young generation GC kể từ khi JVM bắt đầu |
| YGCT | Tổng thời gian young generation GC, thường tính bằng giây |
| FGC | Số full GC kể từ khi JVM bắt đầu |
| FGCT | Tổng thời gian full GC, thường tính bằng giây |
| GCT | Tổng thời gian GC tích lũy, thường tính bằng giây |

Tập cột cụ thể có thể khác giữa các JDK và VM. Một số output của JDK 26 không hiển thị CCS; hãy dựa vào header thực tế.

Ví dụ:

~~~bash
jstat -gcutil 2834 250 7
~~~

Output minh họa theo Oracle:

~~~text
S0     S1      E      O      M     YGC    YGCT    FGC    FGCT    GCT
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
~~~

Đây là output minh họa từ tài liệu, không phải số liệu của ứng dụng hiện tại.

### Cách đọc xu hướng

- E tăng nhanh rồi giảm sau young GC là hành vi bình thường khi ứng dụng tạo object ngắn hạn.
- YGC tăng cho biết có thêm young collection xảy ra.
- O tăng sau các lần GC có thể cho thấy object được promote hoặc live set đang tăng.
- O luôn cao và tăng dần sau các chu kỳ GC là tín hiệu cần điều tra, nhưng chưa đủ chứng minh memory leak.
- FGC tăng liên tục hoặc FGCT tăng nhanh có thể là dấu hiệu áp lực bộ nhớ hoặc cấu hình cần xem xét.
- GCT là tổng thời gian tích lũy; hãy lấy chênh lệch giữa hai mẫu rồi chia cho khoảng thời gian quan sát để ước lượng phần thời gian đã dành cho GC.

Các bộ đếm YGC, YGCT, FGC, FGCT và GCT là giá trị tích lũy kể từ khi JVM chạy. Đừng đọc chúng như số sự kiện chỉ xảy ra trong một dòng mẫu. Muốn tính trong một khoảng, lấy giá trị mẫu sau trừ giá trị mẫu trước.

## 7. Xem dung lượng và mức sử dụng bằng -gc

-gc hiển thị dung lượng và mức sử dụng của các vùng heap dưới dạng KB. Nó hữu ích khi cần biết tỷ lệ sử dụng cao là do vùng nhỏ hay do dung lượng thực tế lớn.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| S0C / S1C | Dung lượng hiện tại của survivor space 0/1, KB |
| S0U / S1U | Dung lượng đang sử dụng của survivor space 0/1, KB |
| EC | Dung lượng Eden hiện tại, KB |
| EU | Dung lượng Eden đang sử dụng, KB |
| OC | Dung lượng old space hiện tại, KB |
| OU | Dung lượng old space đang sử dụng, KB |
| MC | Metaspace committed, KB |
| MU | Metaspace đang sử dụng, KB |
| CCSC | Compressed class space committed, KB |
| CCSU | Compressed class space đang sử dụng, KB |
| YGC / YGCT | Số lần và tổng thời gian young GC |
| FGC / FGCT | Số lần và tổng thời gian full GC |
| GCT | Tổng thời gian GC |

Ví dụ:

~~~bash
jstat -gc <PID> 1000 10
~~~

Nếu EU gần EC, Eden sắp đầy và có thể sớm xảy ra young GC. Đây không phải dấu hiệu xấu tự thân; điều quan trọng là GC có giải phóng đủ dung lượng và ứng dụng có đáp ứng latency mục tiêu hay không.

Nếu OU tăng liên tục qua nhiều chu kỳ GC, hãy xem thêm histogram, heap dump hoặc JFR để biết object nào còn sống và allocation site nào tạo chúng.

## 8. Xem nguyên nhân GC bằng -gccause

-gccause hiển thị summary tương tự -gcutil và thêm nguyên nhân của GC gần nhất cùng GC hiện tại nếu có.

Các cột bổ sung:

- LGCC: nguyên nhân của lần garbage collection gần nhất.
- GCC: nguyên nhân của garbage collection hiện tại, nếu có.

Ví dụ:

~~~bash
jstat -gccause <PID> 1s 20
~~~

Option này giúp liên hệ sự thay đổi bộ nhớ với lý do GC được kích hoạt. Tuy nhiên, đây chỉ là thông tin tóm tắt; nó không thay thế GC log khi cần biết từng event, phase, pause time và nguyên nhân chi tiết.

## 9. Theo dõi generation và metaspace

### -gcnew

-gcnew hiển thị thống kê new generation:

| Cột | Ý nghĩa |
|---|---|
| S0C / S1C | Dung lượng survivor space |
| S0U / S1U | Dung lượng survivor space đang dùng |
| TT | Tenuring threshold hiện tại |
| MTT | Maximum tenuring threshold |
| DSS | Desired survivor size, KB |
| EC | Eden capacity, KB |
| EU | Eden utilization, KB |
| YGC | Số young GC |
| YGCT | Tổng thời gian young GC |

Ví dụ:

~~~bash
jstat -gcnew -h 5 <PID> 250 20
~~~

TT là ngưỡng tuổi object để được promote từ survivor space sang old generation theo cơ chế của collector. Nếu survivor space không đủ chứa lượng object sống sót, JVM có thể điều chỉnh tenuring threshold. Đừng cố ép TT bằng tay chỉ dựa trên một snapshot; hãy xem GC log và hành vi của collector.

### -gcold

-gcold hiển thị thống kê old generation cùng metaspace. Các cột thường gặp gồm MC, MU, CCSC, CCSU, OC, OU, YGC, FGC, FGCT và GCT.

Ví dụ:

~~~bash
jstat -gcold <PID> 1s 20
~~~

### -gcmetacapacity

-gcmetacapacity hiển thị dung lượng tối thiểu, tối đa và committed của metaspace cùng compressed class space.

~~~bash
jstat -gcmetacapacity <PID> 2s 15
~~~

Metaspace lưu metadata của class và được quản lý ngoài Java heap. Nếu metaspace tăng liên tục, cần xem class loading/unloading và class loader lifecycle. Heap occupancy bình thường không loại trừ vấn đề metaspace.

## 10. Theo dõi dung lượng bằng các option capacity

Các option capacity cho biết generation hoặc space có thể tăng tới đâu.

| Option | Mục đích |
|---|---|
| -gccapacity | Dung lượng generation và space |
| -gcnewcapacity | Dung lượng new generation và survivor/Eden |
| -gcoldcapacity | Dung lượng old generation |
| -gcmetacapacity | Dung lượng metaspace và compressed class space |

Ví dụ:

~~~bash
jstat -gccapacity <PID> 1s 10
jstat -gcnewcapacity <PID> 1s 10
jstat -gcoldcapacity -t <PID> 1s 10
jstat -gcmetacapacity <PID> 1s 10
~~~

Các cột như NGCMN, NGCMX, NGC, OGCMN, OGCMX, OGC, MCMN, MCMX và MC thể hiện minimum, maximum hoặc current capacity theo từng vùng.

Một generation có capacity tăng không đồng nghĩa memory leak. JVM có thể mở rộng heap để đáp ứng allocation và promotion demand rồi giữ capacity đó để tái sử dụng. Hãy so sánh capacity với utilization và GC behavior.

## 11. Theo dõi class loading bằng -class

-class hiển thị hoạt động của class loader.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| Loaded | Số class đang được load/đã load theo counter |
| Bytes | Số KB class data đã load |
| Unloaded | Số class đã unload |
| Bytes | Số KB class data đã unload |
| Time | Tổng thời gian dành cho load/unload |

Ví dụ:

~~~bash
jstat -class <PID> 2s 15
~~~

Các counter loaded/unloaded là thống kê tích lũy. Nếu class loading tiếp tục tăng trong lúc ứng dụng xử lý workload bình thường, điều đó có thể hợp lý. Nếu số class tăng liên tục sau mỗi lần deploy/reload, hãy điều tra class loader leak, dynamic proxy, generated class hoặc plugin lifecycle.

Class unload chỉ xảy ra khi class loader và class có thể được thu hồi theo quy tắc của JVM. Không kết luận leak chỉ vì Loaded lớn; hãy xem Unloaded, classloader statistics và metaspace.

## 12. Theo dõi JIT compiler bằng -compiler và -printcompilation

### -compiler

-compiler hiển thị thống kê của HotSpot Just-in-Time compiler.

| Cột | Ý nghĩa |
|---|---|
| Compiled | Số compilation task đã thực hiện |
| Failed | Số compilation task thất bại |
| Invalid | Số compilation task bị invalidated |
| Time | Tổng thời gian compilation |
| FailedType | Loại compilation thất bại gần nhất |
| FailedMethod | Class/method của compilation thất bại gần nhất |

Ví dụ:

~~~bash
jstat -compiler <PID> 1s 10
~~~

### -printcompilation

-printcompilation hiển thị thống kê method compilation gần nhất, thường gồm:

- Compiled: số thứ tự hoặc số compilation task của method gần nhất.
- Size: kích thước bytecode.
- Type: loại compilation.
- Method: class và method được biên dịch.

~~~bash
jstat -printcompilation <PID> 1s 10
~~~

Các số liệu này hữu ích khi điều tra warm-up, compilation activity hoặc method compilation. Chúng không thay thế JFR khi cần biết method nào tiêu tốn CPU trong thời gian thực hay stack trace của allocation.

## 13. Ví dụ thực hành: tạo JVM có allocation để theo dõi

Ví dụ này giữ tối đa 32 byte array trong một queue và liên tục tạo array mới. Chương trình tạo allocation đều đặn nhưng giữ một lượng dữ liệu sống có giới hạn, nhờ đó bạn có thể quan sát Eden, survivor và old generation thay đổi theo thời gian.

Tạo file JstatTarget.java:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public class JstatTarget {
    private static final Deque<byte[]> retained = new ArrayDeque<>();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("jstat-target-ready");

        while (true) {
            if (retained.size() == 32) {
                retained.removeFirst();
            }

            retained.addLast(new byte[128 * 1024]);
            Thread.sleep(100);
        }
    }
}
~~~

### Biên dịch

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 JstatTarget.java
~~~

### Khởi chạy JVM đích

Terminal A:

~~~bash
java JstatTarget
~~~

Output chính xác:

~~~text
jstat-target-ready
~~~

Giữ chương trình chạy. Nó tiếp tục cấp phát và loại bỏ array theo vòng lặp; không cần tạo OutOfMemoryError.

### Tìm PID

Terminal B:

~~~bash
jps -l
~~~

Tìm dòng JstatTarget và ghi lại LVMID/PID.

### Lấy mẫu GC utilization

~~~bash
jstat -gcutil <PID> 1s 15
~~~

Quan sát E, S0, S1, O, M, YGC, YGCT, FGC, FGCT và GCT. Giá trị sẽ thay đổi theo JDK, collector, tải máy và thời điểm bắt đầu lấy mẫu.

### Lấy mẫu dung lượng theo KB

~~~bash
jstat -gc -t <PID> 1s 15
~~~

Dùng EC/EU, OC/OU và các cột capacity/utilization để hiểu tỷ lệ phần trăm trong -gcutil đến từ dung lượng thực tế nào.

### Xem nguyên nhân GC

~~~bash
jstat -gccause <PID> 1s 15
~~~

### Xem class loading và JIT

~~~bash
jstat -class <PID> 2s 10
jstat -compiler <PID> 2s 10
~~~

### Dừng chương trình

Quay lại terminal A và nhấn Ctrl+C. jstat chỉ đọc thống kê; lệnh này không thay đổi heap hoặc dừng JVM đích.

## 14. Đọc metric runtime bằng Java Management Extensions (JMX)

jstat thuận tiện để lấy mẫu nhanh từ terminal. Khi ứng dụng cần xuất metric cho dashboard, alert hoặc monitoring backend, JMX Platform MXBeans cung cấp API quản lý có cấu trúc hơn.

Các MXBean quan trọng:

| MXBean | Dữ liệu |
|---|---|
| MemoryMXBean | Heap và non-heap memory usage |
| MemoryPoolMXBean | Usage, peak usage và threshold theo memory pool |
| GarbageCollectorMXBean | Collection count và collection time theo GC |
| ClassLoadingMXBean | Loaded, total loaded và unloaded class count |
| CompilationMXBean | Thời gian JIT compilation nếu VM hỗ trợ |
| ThreadMXBean | Thread count, peak count, thread CPU time và deadlock detection |
| RuntimeMXBean | Uptime, input arguments và JVM/system properties |
| OperatingSystemMXBean | Thông tin hệ điều hành và processor; extension phụ thuộc JDK |

ManagementFactory cung cấp các factory method để lấy MXBean trong chính JVM hoặc tạo proxy để truy cập MXBean từ một MBeanServerConnection từ xa.

### Ví dụ Java: đọc metric từ MXBeans

Tạo file RuntimeMetrics.java:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class RuntimeMetrics {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();

        System.out.printf("heap.used.bytes=%d%n", heap.getUsed());
        System.out.printf("heap.committed.bytes=%d%n", heap.getCommitted());
        System.out.printf("heap.max.bytes=%d%n", heap.getMax());

        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.printf("classes.current=%d%n",
                classes.getLoadedClassCount());
        System.out.printf("classes.total=%d%n",
                classes.getTotalLoadedClassCount());
        System.out.printf("classes.unloaded=%d%n",
                classes.getUnloadedClassCount());

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(
                    "gc.name=%s count=%d time.ms=%d%n",
                    gc.getName(),
                    gc.getCollectionCount(),
                    gc.getCollectionTime());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 RuntimeMetrics.java
java RuntimeMetrics
~~~

Output có giá trị phụ thuộc JVM, collector, thời điểm và workload; không có một stdout cố định cho mọi máy.

Ý nghĩa:

- heap.used.bytes: dung lượng heap đang sử dụng tại thời điểm đọc.
- heap.committed.bytes: dung lượng heap JVM đã commit.
- heap.max.bytes: giới hạn heap tối đa; một số VM có thể trả về -1 nếu không xác định.
- classes.current: số class hiện đang load.
- classes.total: tổng số class đã load kể từ khi JVM bắt đầu.
- classes.unloaded: số class đã unload.
- gc.count: số lần collection của collector tương ứng.
- gc.time.ms: thời gian collection tích lũy tính bằng millisecond.

Một số MXBean có thể trả -1 nếu metric không được hỗ trợ hoặc không có sẵn. GarbageCollectorMXBean có thể có nhiều instance vì JVM có thể có nhiều collector.

MXBean cung cấp snapshot tại thời điểm gọi. Để tạo time series, ứng dụng hoặc monitoring agent cần lấy mẫu định kỳ, thêm timestamp và export metric theo một schema ổn định.

## 15. Dùng jcmd, JFR và JMC để bổ sung dữ liệu

jstat cho biết các bộ đếm thay đổi ra sao. Khi cần hiểu nguyên nhân hoặc timeline chi tiết hơn, hãy dùng công cụ phù hợp.

### jcmd PerfCounter.print

~~~bash
jcmd <PID> PerfCounter.print
~~~

Lệnh in các performance counter mà process công bố. Nó hữu ích khi cần xem counter cấp thấp hoặc điều tra dữ liệu mà jstat tổng hợp.

### Xem heap và JVM status

~~~bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
~~~

GC.heap_info cho thông tin heap tổng quát; VM.uptime và VM.flags giúp đối chiếu trạng thái, thời gian chạy và cấu hình JVM.

### Thu thập JFR

~~~bash
jcmd <PID> JFR.start name=runtime settings=default duration=2m filename=runtime.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <PID> JFR.check
~~~

JFR thu thập event theo thời gian như GC, allocation, thread, lock, I/O và latency. Template default có overhead thấp hơn; profile thu thập nhiều dữ liệu hơn nhưng có thể tạo overhead lớn hơn.

Mở file runtime.jfr bằng JDK Mission Control để xem memory, GC, thread, method profiling và event timeline. JFR phù hợp khi cần biết điều gì đã xảy ra giữa hai mẫu jstat.

### JConsole

JConsole là công cụ JMX có trong JDK. Nó hiển thị heap/non-heap usage, memory pools, GC count/time, thread count, class loading và CPU usage ở dạng biểu đồ. JConsole có thể kết nối local hoặc remote JVM khi management agent được cấu hình phù hợp.

Không bật JMX remote trên production mà thiếu authentication, TLS, authorization, network binding và firewall phù hợp. Khi chỉ cần dữ liệu runtime, có thể dùng local attach hoặc monitoring agent đã được tổ chức cấu hình.

## 16. Phân biệt metric, counter và rate

Để tránh đọc sai dashboard, hãy phân loại dữ liệu:

### Gauge

Gauge là giá trị tại một thời điểm, có thể tăng hoặc giảm:

- Heap used.
- Eden utilization.
- Old generation utilization.
- Metaspace usage.
- Current loaded class count.
- Current live thread count.

### Counter

Counter thường tăng tích lũy kể từ khi process bắt đầu:

- YGC, FGC.
- YGCT, FGCT, GCT.
- Total loaded class count.
- Unloaded class count.
- Compilation count.

Muốn tính hoạt động trong một cửa sổ, lấy delta của hai lần đọc.

### Rate

Rate là tốc độ thay đổi theo thời gian:

- GC events per second.
- Allocation bytes per second.
- Class load rate.
- Compilation rate.
- GC time percentage trong một khoảng.

Ví dụ, nếu GCT tăng từ 12.0 giây lên 13.5 giây trong 30 giây thực, tổng GC time tăng 1.5 giây. Tỷ lệ thời gian GC gần đúng trong khoảng đó là 1.5 / 30 = 5%. Đây là phép ước lượng từ counter; không thay thế pause-time distribution hoặc JFR event.

Không lấy counter tích lũy làm gauge. Một giá trị GCT lớn có thể chỉ vì JVM đã chạy lâu; cần xem tốc độ tăng trong khoảng thời gian cụ thể.

## 17. Quy trình điều tra hiệu năng bằng runtime metric

### Tình huống A: heap tăng liên tục

1. Lấy jstat -gcutil ở khoảng thời gian đều nhau.
2. Quan sát E và O trước/sau young GC.
3. Nếu O sau GC tăng liên tục, kiểm tra GC logs và live set.
4. Lấy histogram để xem class nào tăng instance.
5. Tạo heap dump nếu cần tìm reference giữ object.
6. Dùng JFR để tìm allocation site và thời điểm tăng object.
7. Đối chiếu với cache, session, queue, listener và class loader lifecycle.

### Tình huống B: GC diễn ra quá thường xuyên

1. Theo dõi YGC/YGCT và Eden utilization.
2. Tính delta YGC trên một khoảng thời gian.
3. Quan sát allocation rate bằng JFR hoặc profiler.
4. Xem object ngắn hạn nào được tạo nhiều.
5. Kiểm tra throughput, request rate và heap sizing.
6. Tối ưu allocation hoặc cấu trúc dữ liệu trước khi chỉ tăng heap.

Young GC thường xuyên có thể là hệ quả bình thường của allocation throughput cao. Chỉ coi là vấn đề khi nó ảnh hưởng latency/throughput hoặc không đạt mục tiêu vận hành.

### Tình huống C: full GC tăng

1. Theo dõi FGC, FGCT và GCCause.
2. Đối chiếu thời điểm với GC log.
3. Kiểm tra old generation occupancy và promotion.
4. Xác định full GC do allocation pressure, explicit GC, metadata pressure hay lý do khác.
5. Nếu có nhiều full GC và pause lớn, thu JFR hoặc GC log chi tiết.
6. Chỉ thay đổi heap/collector sau khi hiểu workload và nguyên nhân.

### Tình huống D: class loading hoặc metaspace tăng

1. Theo dõi -class và -gcmetacapacity.
2. So sánh Loaded/Unloaded qua các lần deploy hoặc reload.
3. Kiểm tra số class loader bằng jcmd VM.classloader_stats.
4. Dùng VM.classloaders hoặc heap dump nếu cần tìm reference giữ loader.
5. Kiểm tra dynamic proxy, bytecode generation, plugin và application redeploy.

### Tình huống E: JVM chậm nhưng heap ổn định

jstat không cung cấp đủ CPU, lock contention, I/O hoặc request latency. Hãy kiểm tra:

- JFR CPU/thread/lock/I/O events.
- JConsole hoặc JMX OperatingSystemMXBean.
- Thread dump khi nghi ngờ block/deadlock.
- OS tools để xem CPU, memory, disk và network.
- Application metrics như request rate, latency percentile, queue depth và error rate.

Không kết luận GC là nguyên nhân chỉ vì heap metric thay đổi cùng thời điểm ứng dụng chậm.

## 18. Những giới hạn cần nhớ

- jstat đọc performance counter của HotSpot; không phải công cụ profiler tổng quát.
- Không cung cấp object graph hoặc retained heap.
- Không cho biết chính xác allocation stack trace của mọi object.
- Không phải mọi metric đều tồn tại trên mọi JDK/collector.
- Các cột generation cũ có thể không phản ánh đúng cấu trúc của mọi garbage collector.
- Format output và tên option có thể thay đổi hoặc bị loại bỏ.
- Không nên viết script parse output jstat như một API ổn định.
- Lấy mẫu quá thường xuyên không giúp chẩn đoán tốt hơn nếu không có giả thuyết; hãy chọn interval phù hợp.
- Trên FAT32, HotSpot instrumentation mà jstat sử dụng không truy cập được.
- Remote jstat dùng jstatd/RMI và cần cấu hình bảo mật; không nên mở RMI rộng ra mạng công cộng.

Nếu cần hệ thống monitoring dài hạn, ưu tiên JMX MXBeans, JFR, GC logs và metrics exporter có schema ổn định.

## 19. Theo dõi remote JVM bằng jstatd

jstat có thể theo dõi JVM từ xa thông qua jstatd, một RMI server daemon. VMID có thể bao gồm LVMID và hostname:

~~~bash
jstat -gcutil 40496@remote.domain 1000 10
~~~

Ví dụ này giả định jstatd đang chạy trên remote.domain và RMI registry có thể truy cập theo cấu hình. jstatd cho phép các công cụ như jps/jstat truy cập instrumentation của JVM trên host từ xa.

Trước khi dùng:

- Cấu hình jstatd theo tài liệu của đúng JDK.
- Dùng security policy tối thiểu cần thiết.
- Giới hạn interface và firewall chỉ cho máy monitoring được phép.
- Không công khai RMI registry hoặc remote object ra Internet.
- Xác nhận LVMID trong môi trường remote.
- Kiểm tra tương thích giữa client tool và target JVM.

Nếu không cần remote instrumentation, JMX exporter, JFR hoặc hệ thống observability của tổ chức có thể phù hợp hơn.

## 20. Lỗi thường gặp và cách xử lý

### jstat không tìm thấy JVM

**Dấu hiệu:** báo không tìm thấy VM hoặc không đọc được VMID.

**Nguyên nhân:** PID sai, JVM đã thoát, process nằm trong container/PID namespace khác hoặc user không truy cập được instrumentation.

**Cách xử lý:** xác định LVMID bằng jps -l hoặc công cụ OS trong đúng namespace; xác nhận JVM vẫn chạy và dùng đúng môi trường JDK.

### jstat báo option không hợp lệ

**Dấu hiệu:** công cụ không nhận -gcutil, -gcnew hoặc option khác.

**Nguyên nhân:** option không có trong bản jstat hiện tại hoặc khác biệt giữa JDK/vendor.

**Cách xử lý:** chạy jstat -options trên đúng runtime; không dùng bảng option của phiên bản khác như cam kết hỗ trợ.

### Không truy cập được instrumentation trên FAT32

**Dấu hiệu:** jstat không đọc được dữ liệu dù JVM đang chạy.

**Nguyên nhân:** HotSpot instrumentation không truy cập được trên FAT32.

**Cách xử lý:** dùng filesystem được hỗ trợ cho cơ chế instrumentation hoặc chọn JMX/JFR/GC logs phù hợp.

### Cột metric không giống tài liệu

**Dấu hiệu:** thiếu CCS, khác tên cột hoặc số liệu generation không như ví dụ.

**Nguyên nhân:** JDK release, vendor, collector hoặc VM implementation khác nhau.

**Cách xử lý:** đọc header output thực tế, kiểm tra jstat -options và đối chiếu collector đang dùng. Không suy diễn từ một output mẫu cũ.

### Counter tăng nhưng không biết mức độ trong khoảng

**Dấu hiệu:** YGC/FGC/GCT có số lớn.

**Nguyên nhân:** đây là counter tích lũy kể từ khi JVM bắt đầu.

**Cách xử lý:** lấy delta giữa hai mẫu, chia cho thời gian thực đã trôi qua và đối chiếu với latency/throughput.

### Script parse output bị lỗi sau khi nâng JDK

**Dấu hiệu:** cột thay đổi, header khác hoặc parser đọc nhầm giá trị.

**Nguyên nhân:** jstat output không phải format ổn định; tài liệu khuyến cáo không viết script phụ thuộc format này.

**Cách xử lý:** chuyển sang JMX MXBeans, JFR hoặc metrics exporter có schema rõ ràng. Nếu vẫn dùng jstat, giới hạn phạm vi script và kiểm thử lại mỗi lần nâng JDK.

### Remote jstat không kết nối được

**Dấu hiệu:** lỗi RMI, timeout hoặc không resolve được remote JVM.

**Nguyên nhân:** jstatd chưa chạy, RMI registry/port bị chặn, sai LVMID hoặc security policy không cho phép.

**Cách xử lý:** kiểm tra jstatd, RMI registry, firewall, policy và VMID; chỉ mở kết nối từ host monitoring được phép.

### jstat không giải thích được CPU hoặc latency

**Dấu hiệu:** heap/GC bình thường nhưng ứng dụng vẫn chậm.

**Nguyên nhân:** vấn đề có thể nằm ở CPU, lock, I/O, network, thread pool hoặc database.

**Cách xử lý:** thu JFR, thread dump, JMX/OS metrics và application metrics; không dùng GC statistic để kết luận nguyên nhân ngoài phạm vi GC.

## 21. Checklist vận hành

### Trước khi lấy mẫu

- [ ] Xác định JDK vendor/version và JVM HotSpot đích.
- [ ] Xác định LVMID/PID chính xác.
- [ ] Chạy jstat -options để kiểm tra stat option có sẵn.
- [ ] Chọn metric theo câu hỏi cần trả lời.
- [ ] Chọn interval/count phù hợp với workload.
- [ ] Xác nhận filesystem hỗ trợ instrumentation.
- [ ] Nếu remote, kiểm tra jstatd/RMI và security policy.

### Trong khi lấy mẫu

- [ ] Dùng -t nếu cần đối chiếu elapsed time.
- [ ] Dùng -h để lặp lại header khi lấy nhiều mẫu.
- [ ] Phân biệt gauge với counter tích lũy.
- [ ] Tính delta cho YGC, FGC, YGCT, FGCT và GCT.
- [ ] Quan sát nhiều mẫu thay vì kết luận từ một dòng.
- [ ] Không parse output như một API ổn định.

### Sau khi lấy mẫu

- [ ] Đối chiếu với GC log, JFR hoặc JMX khi cần thêm chi tiết.
- [ ] Ghi lại JDK version, collector, PID và thời gian thu thập.
- [ ] Kiểm tra xu hướng heap sau GC, không chỉ peak occupancy.
- [ ] Điều tra class loading/metaspace nếu counter tăng bất thường.
- [ ] Thu histogram/heap dump khi cần object-level evidence.
- [ ] Bảo vệ output nếu có thông tin môi trường hoặc dữ liệu nhạy cảm.
- [ ] Chỉ thay đổi heap/GC configuration khi có bằng chứng và kiểm thử.

## 22. Tài liệu tham khảo chính thức

- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — jstat utility, VMID, built-in instrumentation, các ví dụ GC và cách theo dõi runtime.
- [The jstat Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html) — cú pháp, interval/count, VMID, stat options, cột output và cảnh báo về tính experimental/unsupported của công cụ. Đây là trang mà liên kết jstat trong Troubleshooting Guide Java SE 26 hiện chuyển tới.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — diagnostic command, PerfCounter.print, heap info, JFR và các thao tác chẩn đoán bổ sung.
- [ManagementFactory — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html) — truy cập Platform MXBeans trong JVM và qua MBeanServer.
- [MemoryMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html) — heap/non-heap memory usage và memory notification.
- [ClassLoadingMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html) — thống kê class loading/unloading.
- [GarbageCollectorMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html) — collection count/time theo garbage collector.
- [Java SE Monitoring and Management Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/management/java-se-monitoring-and-management-guide.pdf) — Platform MXBeans, JMX và monitoring JVM.

jstat giúp quan sát nhanh các bộ đếm runtime của HotSpot, đặc biệt là heap, GC, class loading và JIT. Hãy chọn đúng stat option, đọc xu hướng qua nhiều mẫu, tính delta cho counter tích lũy và kết hợp JMX/JFR khi cần metric có cấu trúc hoặc nguyên nhân chi tiết.
