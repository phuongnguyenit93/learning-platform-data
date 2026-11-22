# Theo dõi GC statistics bằng jstat

## 1. jstat là gì?

`jstat` là công cụ dòng lệnh trong JDK dùng để đọc các số liệu hiệu năng và tài nguyên từ một Java HotSpot Virtual Machine (JVM) đang chạy. Với bài toán Garbage Collection (GC), `jstat` cho biết dung lượng và mức sử dụng các vùng heap, tỷ lệ sử dụng các memory pool, số lần GC, thời gian GC tích lũy và nguyên nhân của lần GC gần nhất.

Các số liệu này hữu ích khi:

- Kiểm tra heap có đang sử dụng gần hết dung lượng hay không.
- Quan sát Eden tăng rồi giảm sau young GC.
- Theo dõi old generation sau mỗi lần collection.
- Phát hiện số lần GC hoặc thời gian GC tăng nhanh.
- Kiểm tra Metaspace và Compressed Class Space.
- So sánh trạng thái JVM trước và sau khi thay đổi heap hoặc GC configuration.
- Thu thập mẫu định kỳ trong lúc ứng dụng đang chạy.

`jstat` đọc instrumentation data do JVM cung cấp. Công cụ không tự kích hoạt GC, không sửa heap và không thay thế GC log hoặc profiler. Nó cung cấp các snapshot số liệu để người vận hành nhận diện xu hướng.

## 2. Điều kiện và xác định JVM đích

`jstat` giám sát một JVM đã được khởi chạy. Cần xác định đúng Virtual Machine Identifier (VMID) trước khi lấy mẫu.

Dùng `jcmd` để liệt kê Java process:

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
10312 GCStatsDemo
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Trong trường hợp local đơn giản, VMID thường là PID của process. Theo đặc tả, local VM identifier thường nhưng không phải lúc nào cũng chính là operating-system PID.

Có thể đối chiếu với công cụ hệ điều hành:

~~~bash
# Linux
ps -ef | grep java

# Windows PowerShell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" |
    Select-Object ProcessId, CommandLine
~~~

Các điều kiện thực tế:

- Dùng JDK có công cụ `jstat` và JVM đích thuộc HotSpot có instrumentation tương thích.
- Người chạy công cụ cần quyền đọc dữ liệu monitoring của JVM đích.
- Trong container, kiểm tra PID namespace và user của process.
- Nếu nhiều JDK được cài, gọi đúng `jstat` từ JDK phù hợp với JVM đang được giám sát.
- Không suy đoán PID từ tên ứng dụng; xác nhận bằng `jcmd -l` hoặc công cụ hệ điều hành.

Kiểm tra các chế độ thống kê được cài đặt hỗ trợ:

~~~bash
jstat -options
~~~

Trong JDK 24.0.2 của bài thực hành, danh sách trả về gồm:

~~~text
-class
-compiler
-gc
-gccapacity
-gccause
-gcmetacapacity
-gcnew
-gcnewcapacity
-gcold
-gcoldcapacity
-gcutil
-printcompilation
~~~

Danh sách thực tế có thể khác theo JDK, JVM vendor và nền tảng. Hãy dùng `jstat -options` trên môi trường cần giám sát thay vì giả định mọi bản cài đều hỗ trợ cùng một tập option.

## 3. Cú pháp jstat

Cú pháp tổng quát:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Trong đó:

| Thành phần | Ý nghĩa |
|---|---|
| `-<option>` | Chọn nhóm số liệu, ví dụ `-gc` hoặc `-gcutil`. |
| `-t` | Thêm cột timestamp tính từ lúc JVM khởi động. |
| `-h<lines>` | Lặp lại dòng header sau mỗi số lượng sample được chỉ định. |
| `<vmid>` | Định danh JVM cần giám sát, thường là PID với local JVM. |
| `<interval>` | Khoảng thời gian giữa hai sample. |
| `<count>` | Số sample cần lấy trước khi kết thúc. |

Ví dụ:

~~~bash
# Một snapshot
jstat -gc 18420

# Lấy 5 snapshot, mỗi snapshot cách nhau 1 giây
jstat -gc 18420 1s 5

# Lấy 10 snapshot theo tỷ lệ sử dụng và thêm timestamp
jstat -gcutil -t 18420 1s 10

# In lại header sau mỗi 5 sample
jstat -gc -t -h5 18420 1s 12
~~~

Khoảng thời gian có thể dùng đơn vị milliseconds (`ms`) hoặc seconds (`s`). Nếu không ghi hậu tố, đơn vị mặc định là milliseconds. Ví dụ `1000` tương đương 1000 ms; `1s` cũng là một giây.

Nếu bỏ `count`, `jstat` tiếp tục lấy mẫu cho tới khi JVM kết thúc hoặc người dùng dừng command. Dùng `Ctrl+C` để kết thúc phiên theo dõi liên tục.

`-t` hiển thị thời gian đã trôi qua kể từ lúc JVM đích khởi động, tính bằng giây. Đây không phải timestamp theo lịch. `-h5` yêu cầu in lại header sau mỗi năm dòng dữ liệu, giúp đọc output dài mà không phải kéo lên đầu terminal.

Có thể xem trợ giúp:

~~~bash
jstat -help
~~~

Các general option như `-help` và `-options` được chạy riêng, không ghép thêm VMID hoặc output option trong cùng command.

## 4. Chọn chế độ thống kê phù hợp

Các option quan trọng được chia theo mục tiêu:

| Option | Dữ liệu chính | Khi nên dùng |
|---|---|---|
| `-gc` | Dung lượng và mức sử dụng các vùng heap, Metaspace, GC counters. | Phân tích memory theo KB. |
| `-gcutil` | Tỷ lệ sử dụng các pool và GC counters. | Theo dõi xu hướng nhanh. |
| `-gccause` | Số liệu như `-gcutil` và nguyên nhân GC. | Tìm lý do collection gần nhất. |
| `-gccapacity` | Dung lượng min/max/current của generation và space. | Kiểm tra cấu hình và khả năng mở rộng heap. |
| `-gcnew` | Eden, Survivor và thông tin tenuring của young generation. | Điều tra young GC và promotion. |
| `-gcnewcapacity` | Dung lượng của new generation và survivor. | Kiểm tra giới hạn vùng young. |
| `-gcold` | Old generation cùng Metaspace và Compressed Class Space. | Theo dõi old space và class metadata. |
| `-gcoldcapacity` | Dung lượng old generation. | Kiểm tra old generation có thể mở rộng tới đâu. |
| `-gcmetacapacity` | Dung lượng Metaspace và Compressed Class Space. | Điều tra metadata và class loading. |
| `-class` | Class loading/unloading. | Kiểm tra hoạt động class loader. |
| `-compiler` | Thống kê JIT compilation. | Kiểm tra compiler. |
| `-printcompilation` | Method được compile gần nhất. | Xem hoạt động biên dịch JIT gần đây. |

Khi điều tra GC, thường bắt đầu với `-gcutil` để nhận diện xu hướng, chuyển sang `-gc` để xem dung lượng và số liệu chi tiết, rồi dùng `-gccause` hoặc các option capacity khi cần tìm nguyên nhân.

## 5. Đọc output của jstat -gc

`-gc` hiển thị heap statistics và các bộ đếm GC. Một output JDK 24.0.2 có dạng:

~~~text
S0C S1C S0U S1U EC EU OC OU MC MU CCSC CCSU YGC YGCT FGC FGCT CGC CGCT GCT
0.0 0.0 0.0 0.0 29696.0 2048.0 35840.0 7361.3 320.0 81.7 128.0 6.1 0 0.000 1 0.003 0 0.000 0.003
~~~

Các giá trị ở trên là một snapshot minh họa từ môi trường thử nghiệm. Chúng thay đổi theo heap size, collector, hoạt động ứng dụng và thời điểm lấy mẫu.

### Nhóm Eden và Survivor

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `S0C` | Dung lượng hiện tại của Survivor space 0. | KB |
| `S1C` | Dung lượng hiện tại của Survivor space 1. | KB |
| `S0U` | Dung lượng đang sử dụng của Survivor space 0. | KB |
| `S1U` | Dung lượng đang sử dụng của Survivor space 1. | KB |
| `EC` | Dung lượng hiện tại của Eden. | KB |
| `EU` | Dung lượng Eden đang sử dụng. | KB |

Eden thường tăng khi ứng dụng tạo object. Khi young GC xảy ra, object còn sống được chuyển tới Survivor hoặc được promotion lên old generation tùy tuổi object, ngưỡng tenuring và trạng thái heap.

Vì vậy, `EU` có thể tăng dần rồi giảm mạnh sau một young GC. Đây là hành vi bình thường nếu collection diễn ra nhanh và mức sử dụng sau GC ổn định.

### Nhóm Old Generation

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `OC` | Dung lượng hiện tại của old space. | KB |
| `OU` | Dung lượng old space đang sử dụng. | KB |

`OU` tăng có thể do object sống lâu được promotion từ young generation hoặc do ứng dụng giữ lại nhiều object. Nếu mức sử dụng old space tiếp tục tăng sau nhiều lần GC, cần điều tra object retention và khả năng memory leak.

Một snapshot có `OU` cao chưa đủ để kết luận memory leak. Hãy xem xu hướng sau collection, heap capacity, allocation rate và dữ liệu object trong heap dump hoặc JFR.

### Nhóm Metaspace và Compressed Class Space

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `MC` | Dung lượng Metaspace đã commit. | KB |
| `MU` | Metaspace đang sử dụng. | KB |
| `CCSC` | Dung lượng Compressed Class Space đã commit. | KB |
| `CCSU` | Compressed Class Space đang sử dụng. | KB |

Metaspace lưu metadata của class và được cấp phát trong native memory. Nó không phải một vùng object heap thông thường.

Compressed Class Space chứa metadata class được quản lý bằng compressed class pointers khi tính năng này được bật. Nếu số class loaded tăng liên tục, Metaspace có thể tăng. Hãy kiểm tra class loader và số class unloaded trước khi kết luận có classloader leak.

Trong Java 8 trở lên, Metaspace thay thế Permanent Generation (PermGen) của các phiên bản Java cũ. Không áp dụng cách đọc cột PermGen từ tài liệu JDK cũ cho runtime hiện đại.

### Nhóm bộ đếm GC

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `YGC` | Số young generation GC events. | Lần |
| `YGCT` | Tổng thời gian young GC. | Giây |
| `FGC` | Số full GC events. | Lần |
| `FGCT` | Tổng thời gian full GC. | Giây |
| `GCT` | Tổng thời gian GC được thống kê. | Giây |

Các bộ đếm là số liệu tích lũy kể từ khi JVM khởi động. Khi theo dõi hai snapshot, hãy so sánh chênh lệch của bộ đếm trong khoảng thời gian đó thay vì chỉ nhìn giá trị tuyệt đối.

Một số build JDK, bao gồm môi trường JDK 24.0.2 đã kiểm chứng, còn hiển thị `CGC` và `CGCT` cho số lần và thời gian concurrent GC. Các cột này có thể không xuất hiện trong mọi bản build hoặc tài liệu option. Luôn đọc header thực tế từ JVM đích.

Thời gian GC trong `jstat` là bộ đếm tổng hợp, không phải danh sách từng pause. Với collector concurrent, thời gian concurrent GC không đồng nghĩa với thời gian ứng dụng bị stop-the-world. Dùng GC log hoặc JFR khi cần thời điểm và duration của từng event.

## 6. Đọc jstat -gcutil: tỷ lệ sử dụng

`-gcutil` hiển thị tỷ lệ phần trăm dung lượng đang dùng của các pool thay vì số KB.

Output ví dụ:

~~~text
Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT CGC CGCT GCT
2.3       -  -  20.69 20.54 25.54 4.74 0 0.000 1 0.003 0 0.000 0.003
3.4       -  -  75.86 20.54 25.54 4.74 0 0.000 1 0.003 0 0.000 0.003
4.4       -  -  27.27 17.24 40.08 5.54 1 0.002 2 0.006 0 0.000 0.007
~~~

Ý nghĩa:

| Cột | Ý nghĩa |
|---|---|
| `S0` | Phần trăm Survivor space 0 đang dùng. |
| `S1` | Phần trăm Survivor space 1 đang dùng. |
| `E` | Phần trăm Eden đang dùng. |
| `O` | Phần trăm old space đang dùng. |
| `M` | Phần trăm Metaspace đang dùng. |
| `CCS` | Phần trăm Compressed Class Space đang dùng. |

Các cột phần trăm được tính theo dung lượng hiện tại của từng pool, không phải tỷ lệ trên tổng heap. Không cộng `E`, `O`, `M` và `CCS` thành một tỷ lệ tổng.

Trong thử nghiệm JDK 24.0.2 với G1 GC, `S0` và `S1` hiển thị dấu `-`. Với collector hoặc memory pool không được biểu diễn bằng các cột truyền thống này, `jstat` có thể không cung cấp giá trị tương ứng. Hãy hiểu dấu `-` là dữ liệu không có/không áp dụng trong output đó, không phải bằng chứng rằng không còn object sống trong Survivor.

Với G1, cần xem các số liệu theo collector thực tế và kết hợp GC log/JFR khi muốn hiểu chi tiết các region. Không nên suy luận trạng thái heap chỉ từ một cột Survivor.

## 7. Xem nguyên nhân GC bằng jstat -gccause

`-gccause` hiển thị cùng nhóm tỷ lệ và counters như `-gcutil`, đồng thời thêm hai cột:

| Cột | Ý nghĩa |
|---|---|
| `LGCC` | Nguyên nhân của lần garbage collection gần nhất. |
| `GCC` | Nguyên nhân của GC hiện tại nếu đang diễn ra. |

Chạy:

~~~bash
jstat -gccause 18420 1s 10
~~~

Ví dụ output trong môi trường thử nghiệm:

~~~text
S0 S1 E O M CCS YGC YGCT FGC FGCT CGC CGCT GCT LGCC       GCC
-  -  22.22 19.57 40.95 5.54 2 0.003 3 0.009 0 0.000 0.012 System.gc() No GC
~~~

Trong ví dụ:

- `LGCC=System.gc()` cho biết lần GC gần nhất được kích hoạt bởi lời gọi `System.gc()`.
- `GCC=No GC` cho biết tại thời điểm sample không có GC đang diễn ra.

Một số nguyên nhân có thể gặp gồm allocation failure, metadata threshold, explicit GC hoặc các nguyên nhân phụ thuộc collector. Tên chính xác phụ thuộc JVM và loại collection.

Lời gọi `System.gc()` chỉ là yêu cầu GC. JVM có thể bỏ qua yêu cầu này nếu cấu hình cho phép, chẳng hạn khi explicit GC bị vô hiệu hóa. Không dùng `System.gc()` trong ứng dụng production chỉ để ép số liệu thay đổi.

## 8. Xem dung lượng generation bằng jstat -gccapacity

`-gccapacity` tập trung vào dung lượng min/max/current của các generation và space.

~~~bash
jstat -gccapacity 18420
~~~

Các cột thường gặp:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `NGCMN` | Dung lượng tối thiểu của new generation. | KB |
| `NGCMX` | Dung lượng tối đa của new generation. | KB |
| `NGC` | Dung lượng hiện tại của new generation. | KB |
| `S0C`, `S1C` | Dung lượng hiện tại của Survivor spaces. | KB |
| `EC` | Dung lượng Eden hiện tại. | KB |
| `OGCMN` | Dung lượng tối thiểu của old generation. | KB |
| `OGCMX` | Dung lượng tối đa của old generation. | KB |
| `OGC` | Dung lượng hiện tại của old generation. | KB |
| `OC` | Dung lượng old space hiện tại. | KB |
| `MCMN` | Dung lượng tối thiểu của Metaspace. | KB |
| `MCMX` | Dung lượng tối đa của Metaspace. | KB |
| `MC` | Metaspace đã commit. | KB |
| `CCSMN` | Dung lượng tối thiểu của Compressed Class Space. | KB |
| `CCSMX` | Dung lượng tối đa của Compressed Class Space. | KB |
| `CCSC` | Compressed Class Space đã commit. | KB |

Ví dụ từ thử nghiệm:

~~~text
NGCMN NGCMX NGC S0C S1C EC OGCMN OGCMX OGC OC MCMN MCMX MC CCSMN CCSMX CCSC YGC FGC CGC
0.0   65536.0 31744.0 0.0 0.0 31744.0 0.0 65536.0 33792.0 33792.0 0.0 1114112.0 320.0 0.0 1048576.0 128.0 4 5 0
~~~

Dung lượng hiện tại không nhất thiết bằng dung lượng tối đa. Collector có thể điều chỉnh kích thước generation theo heap configuration và trạng thái runtime.

Không cộng mọi capacity column để tự tính tổng heap nếu không hiểu cách collector ánh xạ generation và space. Dùng `jcmd PID GC.heap_info` hoặc GC log để xác nhận cách bố trí heap của collector đang chạy.

## 9. Theo dõi Young Generation bằng jstat -gcnew

`-gcnew` hiển thị số liệu riêng của new generation:

~~~bash
jstat -gcnew 18420
~~~

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `S0C`, `S1C` | Dung lượng Survivor 0 và Survivor 1, KB. |
| `S0U`, `S1U` | Mức sử dụng Survivor 0 và Survivor 1, KB. |
| `TT` | Tenuring threshold hiện tại. |
| `MTT` | Tenuring threshold tối đa. |
| `DSS` | Desired survivor size, KB. |
| `EC` | Dung lượng Eden, KB. |
| `EU` | Eden đang sử dụng, KB. |
| `YGC` | Số young GC. |
| `YGCT` | Tổng thời gian young GC, giây. |

Tenuring threshold quyết định tuổi object liên quan tới việc promotion từ Survivor lên old generation. JVM có thể điều chỉnh threshold theo lượng survivor thực tế và mục tiêu survivor size.

Nếu `TT` giảm, object có thể được promotion sớm hơn. Promotion tăng có thể làm `OU` tăng. Tuy nhiên, không nên kết luận promotion problem chỉ từ một sample; hãy xem chuỗi sample và collector configuration.

## 10. Kiểm tra dung lượng Young Generation

`-gcnewcapacity` cho biết giới hạn và dung lượng hiện tại của new generation:

~~~bash
jstat -gcnewcapacity 18420
~~~

Các cột thường gặp:

- `NGCMN`, `NGCMX`, `NGC`: minimum, maximum và current new generation capacity.
- `S0CMX`, `S0C`: maximum và current Survivor 0 capacity.
- `S1CMX`, `S1C`: maximum và current Survivor 1 capacity.
- `ECMX`, `EC`: maximum và current Eden capacity.
- `YGC` và `FGC`: số lần young GC và full GC.

Dữ liệu này hữu ích khi kiểm tra young generation có thể mở rộng đến đâu và dung lượng hiện tại có thay đổi trong quá trình chạy hay không.

Các cột generation/space phụ thuộc collector. Với G1, region-based heap không nhất thiết tương ứng trực tiếp với mô hình Eden/Survivor cố định trong mọi cột truyền thống. Đọc output theo collector và JDK thực tế.
## 11. Theo dõi Old Generation và Metaspace

`-gcold` cung cấp thông tin old generation và Metaspace:

~~~bash
jstat -gcold 18420
~~~

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `MC` | Metaspace committed, KB. |
| `MU` | Metaspace used, KB. |
| `CCSC` | Compressed Class Space committed, KB. |
| `CCSU` | Compressed Class Space used, KB. |
| `OC` | Old space capacity, KB. |
| `OU` | Old space used, KB. |
| `YGC`, `FGC` | Số young GC và full GC. |
| `FGCT`, `GCT` | Thời gian full GC và tổng GC, giây. |

Dung lượng old generation:

~~~bash
jstat -gcoldcapacity 18420
~~~

Các cột chính:

- `OGCMN`: old generation minimum capacity.
- `OGCMX`: old generation maximum capacity.
- `OGC`: old generation current capacity.
- `OC`: old space current capacity.
- `YGC`, `FGC`, `FGCT` và `GCT`: các counters liên quan GC.

Theo dõi Metaspace:

~~~bash
jstat -gcmetacapacity 18420
~~~

Các cột gồm `MCMN`, `MCMX`, `MC`, `CCSMN` và `CCSMX` cùng các GC counters.

Metaspace tăng có thể là kết quả của việc nạp class bình thường. Nếu số class loaded tăng nhưng không unload trong một ứng dụng có nhiều class loader động, hãy kiểm tra class loader lifecycle và class unloading. Chỉ số Metaspace đơn lẻ không chứng minh leak.

## 12. Các thống kê bổ sung: class loading và JIT

`jstat` còn có một số option không trực tiếp đo GC nhưng hữu ích khi phân tích hoạt động JVM.

### Class loader

~~~bash
jstat -class 18420
~~~

Các cột:

- `Loaded`: số class đã load.
- `Bytes` đầu tiên: dung lượng KB của class đã load.
- `Unloaded`: số class đã unload.
- `Bytes` thứ hai: dung lượng KB class đã unload.
- `Time`: thời gian dành cho thao tác load/unload class.

Nếu `Loaded` tăng liên tục, hãy so sánh `Unloaded` và Metaspace. Trong ứng dụng dùng nhiều dynamic proxy, plugin hoặc class loader tùy chỉnh, class loading/unloading là một hướng điều tra đáng xem xét.

### JIT compiler

~~~bash
jstat -compiler 18420
~~~

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `Compiled` | Số compilation task đã thực hiện. |
| `Failed` | Số compilation task thất bại. |
| `Invalid` | Số compilation task bị invalidated. |
| `Time` | Thời gian thực hiện compilation. |
| `FailedType` | Kiểu compilation của lần thất bại gần nhất. |
| `FailedMethod` | Class và method của lần thất bại gần nhất. |

Xem method được compile gần nhất:

~~~bash
jstat -printcompilation 18420
~~~

Các cột gồm `Compiled`, `Size`, `Type` và `Method`. Đây là thông tin về method compilation gần nhất, không phải danh sách đầy đủ mọi method trong code cache.

## 13. Ví dụ Java 17 tạo allocation để quan sát GC

Tạo file `GCStatsDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public class GCStatsDemo {
    public static void main(String[] args) throws Exception {
        Deque<byte[]> retained = new ArrayDeque<>();
        long cycle = 0;

        System.out.println("GCStatsDemo ready");

        while (true) {
            for (int i = 0; i < 12; i++) {
                retained.addLast(new byte[256 * 1024]);

                if (retained.size() > 24) {
                    retained.removeFirst();
                }
            }

            cycle++;

            if (cycle % 8 == 0) {
                System.gc();
                System.out.println("requested explicit GC at cycle " + cycle);
            }

            Thread.sleep(250);
        }
    }
}
~~~

Chương trình tạo object theo từng đợt, giữ lại một số array để tạo live set ổn định và loại bỏ array cũ để tiếp tục tạo allocation. Mỗi tám vòng, chương trình yêu cầu explicit GC nhằm giúp quan sát cột GC cause trong lab.

Đây là chương trình thực hành có vòng lặp vô hạn. Lời gọi `System.gc()` chỉ phục vụ quan sát; không dùng nó như cách tối ưu GC trong ứng dụng production.

Biên dịch:

~~~bash
mkdir -p out
javac --release 17 -d out src/GCStatsDemo.java
~~~

Chạy với heap cố định 64 MB và G1 GC:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -cp out GCStatsDemo
~~~

Stdout bắt đầu bằng:

~~~text
GCStatsDemo ready
requested explicit GC at cycle 8
requested explicit GC at cycle 16
~~~

Các dòng tiếp theo xuất hiện theo thời gian. Thời điểm và số cycle cụ thể có thể thay đổi theo tốc độ máy.

## 14. Quy trình thực hành jstat end-to-end

Mở terminal thứ hai trong lúc `GCStatsDemo` đang chạy.

Tìm PID:

~~~bash
jcmd -l
~~~

Giả sử PID là `10312`.

Lấy một snapshot heap:

~~~bash
jstat -gc 10312
~~~

Theo dõi tỷ lệ sử dụng qua năm sample:

~~~bash
jstat -gcutil -t 10312 1s 5
~~~

Theo dõi nguyên nhân GC:

~~~bash
jstat -gccause 10312 1s 10
~~~

Kiểm tra capacity:

~~~bash
jstat -gccapacity 10312
jstat -gcmetacapacity 10312
~~~

Kiểm tra young và old generation:

~~~bash
jstat -gcnew 10312
jstat -gcnewcapacity 10312
jstat -gcold 10312
jstat -gcoldcapacity 10312
~~~

Xem class loading và compiler:

~~~bash
jstat -class 10312
jstat -compiler 10312
jstat -printcompilation 10312
~~~

In timestamp và lặp header:

~~~bash
jstat -gc -t -h5 10312 1s 12
~~~

Đối chiếu heap summary với `jcmd`:

~~~bash
jcmd 10312 GC.heap_info
jcmd 10312 VM.flags
~~~

Trong thử nghiệm JDK 24.0.2, `jstat` đã hiển thị Eden/old/metaspace usage, capacity, young/full GC counters, thời gian GC và nguyên nhân `System.gc()`. `jcmd GC.heap_info` xác nhận heap G1 có tổng committed/reserved 64 MB trong cấu hình lab.

Khi hoàn tất, dừng chương trình demo bằng `Ctrl+C` ở terminal chạy Java. Không để tiến trình thử nghiệm chạy nền ngoài thời gian cần thiết.

## 15. Cách đọc xu hướng GC thay vì một con số riêng lẻ

Một snapshot chỉ cho biết trạng thái tại một thời điểm. Để nhận diện vấn đề, hãy so sánh nhiều sample và quan sát điều gì xảy ra trước/sau collection.

### Eden tăng nhanh rồi giảm sau young GC

Nếu `E` tăng đều và giảm sau khi `YGC` tăng, ứng dụng đang tạo object và JVM đang thu hồi hoặc di chuyển object trong young generation. Điều này thường là hành vi bình thường.

Cần điều tra thêm nếu young GC diễn ra quá dày, thời gian GC tăng hoặc throughput giảm.

### Old space tăng sau nhiều collection

Nếu `O` hoặc `OU` tiếp tục tăng sau nhiều young GC, có thể nhiều object sống sót và được promotion. Nếu old occupancy vẫn cao sau full GC, cần kiểm tra object retention, cache không giới hạn hoặc memory leak.

Không kết luận leak chỉ từ old space tăng trong một khoảng ngắn. Một workload có thể đang warm up hoặc giữ cache có chủ đích.

### GC counters tăng nhanh

`YGC`, `FGC` và các counter collector-specific là bộ đếm tích lũy. Tính delta giữa hai sample:

- `ΔYGC`: số young GC mới xảy ra trong khoảng theo dõi.
- `ΔFGC`: số full GC mới xảy ra trong khoảng theo dõi.
- `ΔYGCT` và `ΔFGCT`: thời gian GC tăng thêm trong khoảng đó.

Nếu số lần GC tăng nhanh cùng với latency, allocation pressure hoặc CPU cao, cần xem GC logs/JFR để biết loại collection và pause cụ thể.

### Metaspace tăng

Nếu `MU` và `M` tăng, xem class loading, class unloading và class loader lifecycle. Metaspace có thể tăng trong quá trình ứng dụng nạp thêm class; mức tăng chỉ đáng lo khi không ổn định hoặc không thu hồi trong workload lặp lại.

### Capacity thay đổi

`-gccapacity` cho biết current capacity cùng min/max. Nếu heap hoặc generation tăng capacity, điều đó có thể là JVM đang điều chỉnh vùng nhớ theo allocation/promotion demand. Cần đối chiếu với `-Xms`, `-Xmx`, collector và GC logs.

## 16. Những giới hạn cần hiểu khi đọc số liệu

**Tỷ lệ pool không phải tỷ lệ tổng heap.** `E` và `O` là phần trăm trên capacity của từng pool. Không cộng chúng để tính tổng heap utilization.

**Bộ đếm là tích lũy.** `YGC` và `FGC` thường tăng dần từ lúc JVM khởi động. Hãy so sánh delta theo thời gian.

**GC time không phải pause log.** `YGCT`, `FGCT` và `GCT` là thời gian tổng hợp. Chúng không cho biết chính xác từng pause bắt đầu lúc nào, kéo dài bao lâu và thread ứng dụng bị dừng ra sao.

**Collector có cách biểu diễn khác nhau.** Một số cột truyền thống như Survivor 0/1 có thể không có giá trị trong một số cấu hình. Dấu `-` không có nghĩa là toàn bộ object trong vùng đó đã biến mất.

**Metaspace không nằm trong Java heap.** `MC` và `MU` là số liệu metadata trong native memory. Không cộng Metaspace vào heap occupancy như thể đó là một pool object heap.

**Số liệu có thể thay đổi theo JDK.** Header, tên cột và tập option không phải giao diện ổn định cho mọi bản phát hành.

**jstat không cho biết object nào đang sống.** Nếu nghi ngờ memory leak, cần dùng heap dump, class histogram, JFR hoặc công cụ phân tích heap để xác định object và reference giữ chúng.

## 17. Giám sát JVM từ xa bằng VMID

Ngoài local PID, VMID có thể chứa hostname và cổng RMI. Ví dụ:

~~~bash
jstat -gcutil 40496@remote.domain 1s 10
~~~

Remote monitoring thường cần `jstatd` và RMI registry trên máy đích. Việc cấu hình remote service phải tuân thủ chính sách mạng và bảo mật của tổ chức.

Một số điểm cần lưu ý:

- Remote VMID không có nghĩa `jstat` tự kết nối tới mọi JVM qua IP.
- Remote monitoring cần server instrumentation phù hợp và kết nối RMI được cấu hình.
- Kiểm soát firewall, port và quyền truy cập.
- Không mở RMI monitoring rộng ra Internet.
- Với container, xác định VMID trong môi trường có thể truy cập đúng JVM.

Nếu chỉ giám sát JVM local, dùng PID/VMID local là cách đơn giản nhất.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jstat` không tìm thấy command | JDK bin chưa nằm trong PATH. | Kiểm tra `JAVA_HOME` và chạy đúng executable trong `bin`. |
| Không tìm thấy VMID | PID sai, JVM đã kết thúc hoặc VMID không phải local PID. | Chạy `jcmd -l` và xác nhận process. |
| Không có option thống kê mong muốn | JDK/vendor hiện tại không cung cấp option đó. | Chạy `jstat -options` trên đúng môi trường. |
| Output có dấu `-` ở S0/S1 | Collector hoặc memory pool không cung cấp giá trị tương ứng. | Đọc collector và các cột khác; không coi dấu gạch là zero live data. |
| Eden luôn gần 100% | Ứng dụng allocation nhanh và sắp có young GC. | Quan sát sample kế tiếp, YGC và thời gian GC. |
| Old occupancy tăng | Object được promotion hoặc giữ lại lâu. | Theo dõi sau GC và điều tra object retention bằng JFR/heap dump. |
| Metaspace tăng | Class được nạp hoặc class loader chưa được giải phóng. | Xem Loaded/Unloaded, class loader lifecycle và Metaspace trend. |
| Không thấy GCC cause mong muốn | GC không diễn ra trong sample hoặc collector không cung cấp cause như mong đợi. | Lấy nhiều sample và đối chiếu GC log. |
| Sample không đều | Máy tải cao hoặc lịch scheduling làm chậm command. | Dùng timestamp, tăng interval và tránh sample quá dày. |
| jstat không kết nối được trong container | PID namespace, user hoặc perfdata visibility khác. | Chạy trong đúng namespace/user và kiểm tra JVM instrumentation. |
| Script phân tích output bị lỗi sau khi nâng JDK | Header hoặc định dạng output thay đổi. | Không phụ thuộc parser cột tự viết; dùng API monitoring ổn định hơn. |

## 19. Quy trình giám sát GC trong production

1. Xác định đúng PID, JDK version và collector đang chạy.
2. Kiểm tra cấu hình heap bằng `jcmd PID VM.flags`.
3. Lấy baseline bằng `jstat -gcutil -t PID 1s 10`.
4. Nếu thấy tỷ lệ hoặc counters bất thường, lấy chi tiết bằng `jstat -gc` và `jstat -gccause`.
5. Kiểm tra generation capacity bằng `jstat -gccapacity`.
6. Nếu nghi ngờ Metaspace, dùng `jstat -gcmetacapacity` và `jstat -class`.
7. So sánh counters theo delta trong cùng cửa sổ thời gian.
8. Đối chiếu với request latency, throughput, allocation rate, CPU và application logs.
9. Thu thập GC log hoặc JFR nếu cần pause duration, event timeline và nguyên nhân chi tiết.
10. Ghi lại collector, heap flags, thời gian lấy mẫu và phiên bản JDK cùng báo cáo điều tra.

### Bật GC logging khi cần chi tiết từng event

Với HotSpot hiện đại, có thể cấu hình Unified Logging lúc khởi chạy JVM:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

GC log cho biết các event và pause chi tiết hơn số liệu tổng hợp trong `jstat`. Thay đổi JVM option thường cần restart ứng dụng; hãy tuân thủ quy trình triển khai của hệ thống.

### Kết hợp JFR

JFR ghi nhận sự kiện runtime theo thời gian, hữu ích khi cần đối chiếu GC với allocation, thread, lock, class loading và hoạt động ứng dụng. Có thể dùng `jcmd PID JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop` để điều khiển recording nếu JVM hỗ trợ.

## 20. Lưu ý về tính ổn định của jstat

Tài liệu Oracle JDK 24 đánh dấu `jstat` là công cụ experimental và unsupported. Các option và chức năng có thể thay đổi hoặc bị loại bỏ trong các bản phát hành tương lai.

Tài liệu cũng khuyến cáo không viết script phụ thuộc vào việc parse output của `jstat` vì định dạng có thể thay đổi. Vì vậy:

- Dùng `jstat` cho chẩn đoán tương tác và kiểm tra nhanh.
- Không coi tên cột và thứ tự cột là API ổn định.
- Không xây dựng hệ thống alert production phụ thuộc parser output chưa được kiểm soát.
- Với monitoring lâu dài, ưu tiên JMX, metrics exporter, JFR hoặc nền tảng observability có schema ổn định.
- Kiểm tra lại output và option khi nâng JDK.

## 21. Checklist đọc GC statistics

- Đã xác nhận đúng JVM và VMID.
- Đã kiểm tra option được hỗ trợ bằng `jstat -options`.
- Đã chọn đúng giữa `-gc`, `-gcutil` và `-gccause`.
- Đã hiểu các cột capacity/used tính theo KB và các cột utilization tính theo %.
- Đã phân biệt Eden, Survivor, Old Generation, Metaspace và Compressed Class Space.
- Đã đọc YGC/FGC cùng thời gian tích lũy, không chỉ nhìn số đếm.
- Đã hiểu LGCC và GCC khi dùng `-gccause`.
- Đã kiểm tra collector trước khi diễn giải cột Survivor.
- Đã so sánh nhiều sample và dùng timestamp khi cần.
- Đã đối chiếu với heap flags, GC logs, JFR và application metrics.
- Không kết luận memory leak chỉ từ một snapshot.
- Không dùng `jstat` output làm định dạng parser ổn định cho production automation.

## 22. Tài liệu tham khảo

- [The jstat Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Java Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

`jstat` giúp quan sát GC statistics qua các snapshot của JVM: dung lượng heap, tỷ lệ sử dụng pool, số lần collection, thời gian GC và nguyên nhân GC gần nhất. Hãy đọc đúng đơn vị, theo dõi delta theo thời gian, xét tới collector và JDK đang chạy, rồi dùng GC logs hoặc JFR để xác nhận các vấn đề về pause, allocation và object retention.
