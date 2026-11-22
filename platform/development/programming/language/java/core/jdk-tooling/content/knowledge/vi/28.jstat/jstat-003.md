# Theo dõi Heap statistics bằng jstat

## 1. jstat là gì?

**jstat** (JVM Statistics Monitoring Tool) là công cụ dòng lệnh trong JDK dùng để đọc các bộ đếm instrumentation của Java HotSpot VM đang chạy. Công cụ cung cấp số liệu về garbage collection (GC), dung lượng các vùng heap, Metaspace và một số hoạt động runtime khác.

Với chủ đề **Heap statistics**, jstat giúp trả lời:

- Eden, Survivor và Old space đang dùng bao nhiêu bộ nhớ?
- Dung lượng hiện tại và dung lượng tối đa của các generation là bao nhiêu?
- Tỷ lệ sử dụng heap thay đổi thế nào theo thời gian?
- Young GC và Full GC đã xảy ra bao nhiêu lần?
- Tổng thời gian GC đang tăng nhanh hay chậm?
- GC gần nhất được kích hoạt bởi nguyên nhân nào?

jstat đặc biệt hữu ích khi cần quan sát một JVM qua nhiều mẫu liên tiếp. Một lần đọc chỉ là snapshot; chuỗi mẫu mới cho thấy allocation, GC và mức sử dụng bộ nhớ thay đổi như thế nào.

jstat theo dõi JVM HotSpot đã được instrument. Instrumentation tích hợp được bật mặc định và thông thường không cần khởi chạy ứng dụng với một JVM flag đặc biệt chỉ để dùng jstat.

## 2. Kiểm tra jstat và các option có sẵn

jstat được phân phối cùng JDK. Kiểm tra help:

~~~bash
jstat -help
~~~

Liệt kê các nhóm thống kê mà bản JDK hiện tại hỗ trợ:

~~~bash
jstat -options
~~~

Trên JDK 24.0.2 trong môi trường kiểm thử, danh sách gồm:

~~~text
-class
-compiler
-gc
-gccapacity
-gccause
-gcnew
-gcnewcapacity
-gcold
-gcoldcapacity
-gcmetacapacity
-gcutil
-printcompilation
~~~

Các option có thể khác giữa JDK release, vendor hoặc nền tảng. Hãy xem jstat -options của chính JDK đang dùng thay vì giả định mọi bản đều có cùng danh sách.

## 3. Cú pháp tổng quát

Cú pháp:

~~~text
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Ý nghĩa:

| Thành phần | Mô tả |
|---|---|
| option | Loại thống kê cần hiển thị, ví dụ -gc hoặc -gcutil. |
| vmid | Định danh JVM đích. Với JVM cục bộ, thường là lvmid. |
| interval | Khoảng thời gian giữa các mẫu. |
| count | Số mẫu cần lấy. |
| -t | Thêm cột thời gian tính từ lúc JVM khởi động. |
| -hN | Lặp lại dòng tiêu đề sau mỗi N mẫu. |

Ví dụ lấy 5 mẫu GC, mỗi mẫu cách nhau 1 giây:

~~~bash
jstat -gc 12345 1s 5
~~~

Khoảng thời gian cũng có thể ghi bằng milliseconds:

~~~bash
jstat -gc 12345 500ms 10
~~~

Nếu không ghi interval, jstat lấy một mẫu. Nếu có interval nhưng bỏ count, công cụ tiếp tục lấy mẫu cho tới khi JVM kết thúc hoặc người dùng dừng lệnh bằng Ctrl+C.

Đơn vị mặc định của interval là milliseconds. Interval và count phải là số nguyên dương.

## 4. Tìm đúng JVM và VMID

Trước khi chạy jstat, cần xác định đúng JVM. Có thể dùng:

~~~bash
jcmd -l
jps -l
~~~

Ví dụ:

~~~text
12345 com.example.orders.OrderApplication
~~~

Trong lệnh jstat:

~~~bash
jstat -gc 12345 1s 5
~~~

12345 là ví dụ lvmid. LVMID thường trùng với PID của hệ điều hành nhưng không được bảo đảm luôn luôn giống nhau. Khi cần xác minh OS PID, đối chiếu bằng công cụ quản lý process của hệ điều hành.

VMID có thể có dạng:

~~~text
<lvmid>
<lvmid>@<hostname>[:<port>]
~~~

Phần lvmid là thành phần bắt buộc; hostname và port được dùng cho cơ chế giám sát từ xa. jstat chỉ quan sát những JVM mà tài khoản và môi trường hiện tại có quyền truy cập.

## 5. Tạo JVM mẫu để thực hành

Tạo file **JstatHeapProbe.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class JstatHeapProbe {
    private static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 20; i++) {
            KEEP.add(new byte[1024 * 1024]);
        }

        System.out.println(
                "JstatHeapProbe ready; pid=" +
                ProcessHandle.current().pid());

        long end = System.nanoTime() + 120_000_000_000L;
        while (System.nanoTime() < end) {
            for (int i = 0; i < 12; i++) {
                byte[] temporary = new byte[512 * 1024];
                if (temporary.length == 0) {
                    throw new AssertionError();
                }
            }
            Thread.sleep(80);
        }
    }
}
~~~

Chương trình giữ lại 20 mảng byte, mỗi mảng 1 MiB, đồng thời tạo các allocation tạm thời để hoạt động GC có thể quan sát được. ProcessHandle.current().pid() in ra PID của JVM mẫu. Chương trình chạy tối đa hai phút để có thời gian lấy nhiều mẫu.

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 JstatHeapProbe.java
~~~

Chạy với heap giới hạn 128 MiB và G1 GC:

~~~bash
java -Xms64m -Xmx128m -XX:+UseG1GC JstatHeapProbe
~~~

Ví dụ stdout:

~~~text
JstatHeapProbe ready; pid=12345
~~~

PID là giá trị động. Mở terminal thứ hai, thay 12345 bằng PID thực tế rồi thử:

~~~bash
jstat -gc 12345 500ms 5
jstat -gcutil 12345 500ms 5
~~~

Mẫu Java này đã được biên dịch bằng javac --release 17 và chạy trên JDK 24.0.2; jstat đã quan sát được các bộ đếm Young GC tăng trong lúc allocation tiếp diễn. Sau khi thực hành, dừng process mẫu bằng Ctrl+C.

## 6. Dùng -gc để xem dung lượng từng vùng

Option **-gc** hiển thị dung lượng và mức sử dụng của các vùng heap, cùng một số bộ đếm GC.

Chạy:

~~~bash
jstat -gc 12345
~~~

Ví dụ output thu được từ JVM thử nghiệm trên JDK 24.0.2:

~~~text
S0C    S1C    S0U   S1U      EC      EU       OC       OU     MC    MU    CCSC CCSU YGC YGCT FGC FGCT CGC CGCT GCT
0.0  1024.0  0.0  99.5  16384.0  4096.0  56320.0  42096.8  320.0 83.4 128.0 6.7 2 0.001 0 0.000 2 0.001 0.002
~~~

Các cột dung lượng bộ nhớ của option này dùng đơn vị KB.

| Cột | Ý nghĩa |
|---|---|
| S0C, S1C | Dung lượng hiện tại của Survivor space 0 và 1. |
| S0U, S1U | Dung lượng đang sử dụng của Survivor space 0 và 1. |
| EC | Dung lượng hiện tại của Eden space. |
| EU | Dung lượng Eden đang sử dụng. |
| OC | Dung lượng hiện tại của Old space. |
| OU | Dung lượng Old space đang sử dụng. |
| MC | Dung lượng Metaspace đã commit. |
| MU | Dung lượng Metaspace đang sử dụng. |
| CCSC | Dung lượng Compressed Class Space đã commit. |
| CCSU | Dung lượng Compressed Class Space đang sử dụng. |
| YGC | Số lần Young GC kể từ khi JVM khởi động. |
| YGCT | Tổng thời gian Young GC, tính bằng giây. |
| FGC | Số lần Full GC kể từ khi JVM khởi động. |
| FGCT | Tổng thời gian Full GC, tính bằng giây. |
| GCT | Tổng thời gian GC theo bộ đếm của JVM, tính bằng giây. |

Trên JDK 24.0.2 được kiểm tra, output còn có CGC và CGCT cho bộ đếm số lần và thời gian hoạt động concurrent GC mà JVM/collector cung cấp. Các cột này không xuất hiện trong mọi phiên bản hoặc mọi cấu hình; luôn đọc header thực tế của output.

MC, MU, CCSC và CCSU mô tả vùng lưu metadata của class. Chúng không phải dung lượng Java object heap.

## 7. Dùng -gcutil để xem tỷ lệ phần trăm

Option **-gcutil** hiển thị mức sử dụng các vùng dưới dạng phần trăm dung lượng hiện tại.

~~~bash
jstat -gcutil 12345
~~~

Ví dụ output từ JVM G1 thử nghiệm:

~~~text
S0  S1     E      O      M     CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   0.00  92.82  62.76  16.64  24  0.011   0  0.000   2  0.000  0.011
~~~

Ý nghĩa các cột phần trăm:

| Cột | Ý nghĩa |
|---|---|
| S0 | Tỷ lệ sử dụng Survivor space 0. |
| S1 | Tỷ lệ sử dụng Survivor space 1. |
| E | Tỷ lệ sử dụng Eden. |
| O | Tỷ lệ sử dụng Old space. |
| M | Tỷ lệ sử dụng Metaspace. |
| CCS | Tỷ lệ sử dụng Compressed Class Space. |

Các cột YGC, YGCT, FGC, FGCT và GCT là bộ đếm/số thời gian tích lũy, không phải phần trăm.

Dấu - có nghĩa cột đó không có giá trị được báo cáo trong cấu hình hoặc collector hiện tại. Ví dụ, output G1 trên JDK 24.0.2 có thể hiển thị - cho S0 và S1. Không diễn giải dấu này thành 0% sử dụng.

-gcutil phù hợp để nhận diện vùng nào đang tăng tỷ lệ sử dụng. Khi cần biết dung lượng tuyệt đối tương ứng với phần trăm, dùng thêm -gc.

## 8. Dùng các option capacity

Các option capacity cho biết dung lượng tối thiểu, tối đa và hiện tại của generation hoặc memory space.

| Option | Thông tin |
|---|---|
| -gccapacity | Capacity của New Generation, Old Generation, Survivor, Eden và Metaspace. |
| -gcnewcapacity | Capacity của New Generation và các space thuộc vùng này. |
| -gcoldcapacity | Capacity của Old Generation. |
| -gcmetacapacity | Capacity của Metaspace và Compressed Class Space. |

Ví dụ:

~~~bash
jstat -gccapacity 12345
jstat -gcnewcapacity 12345
jstat -gcoldcapacity 12345
jstat -gcmetacapacity 12345
~~~

Một số cột thường gặp trong -gccapacity:

- NGCMN: dung lượng tối thiểu của New Generation.
- NGCMX: dung lượng tối đa của New Generation.
- NGC: dung lượng New Generation hiện tại.
- OGCMN: dung lượng tối thiểu của Old Generation.
- OGCMX: dung lượng tối đa của Old Generation.
- OGC: dung lượng Old Generation hiện tại.
- EC, S0C, S1C, OC: dung lượng hiện tại của từng space.
- MCMN, MCMX, MC: dung lượng Metaspace tối thiểu, tối đa và đã commit.

Các capacity này giúp hiểu JVM có thể mở rộng generation đến đâu. Chúng không thay thế việc kiểm tra -Xms và -Xmx; khi cần xác nhận các JVM flag đó, dùng:

~~~bash
jcmd 12345 VM.flags
~~~

## 9. Dùng -gcnew và -gcold để tập trung vào từng generation

Khi cần điều tra một vùng cụ thể, có thể thu hẹp output.

### New Generation

~~~bash
jstat -gcnew 12345
~~~

Các cột thường gặp:

- S0C, S1C: capacity của hai Survivor space.
- S0U, S1U: dung lượng Survivor đang dùng.
- TT: tenuring threshold hiện tại.
- MTT: maximum tenuring threshold.
- DSS: desired survivor size.
- EC, EU: capacity và mức sử dụng Eden.
- YGC, YGCT: số lần và tổng thời gian Young GC.

TT là ngưỡng tuổi object liên quan đến việc object được giữ trong Survivor hay được promote sang Old Generation. Giá trị có thể thay đổi theo hành vi GC.

### Old Generation

~~~bash
jstat -gcold 12345
~~~

Option này tập trung vào Old space và Metaspace:

- OC, OU: dung lượng và mức sử dụng Old space.
- MC, MU: Metaspace committed và used.
- CCSC, CCSU: Compressed Class Space committed và used.
- YGC, FGC, FGCT, GCT: các bộ đếm GC tương ứng.

Không phải collector nào cũng biểu diễn heap theo các generation truyền thống. Đọc các cột thực tế được target JVM cung cấp.

## 10. Dùng -gccause để xem nguyên nhân GC

Option **-gccause** hiển thị thống kê tương tự -gcutil, đồng thời bổ sung nguyên nhân GC gần nhất và nguyên nhân GC hiện tại nếu có.

~~~bash
jstat -gccause 12345
~~~

Hai cột bổ sung:

- LGCC: nguyên nhân của lần GC gần nhất.
- GCC: nguyên nhân của GC hiện tại nếu đang có hoạt động GC; nếu không, có thể hiển thị No GC.

Ví dụ nguyên nhân có thể gồm allocation failure hoặc các sự kiện liên quan tới collector. Tên nguyên nhân phụ thuộc JVM và collector.

Option này hữu ích khi tỷ lệ sử dụng tăng hoặc bộ đếm GC thay đổi và cần thêm bối cảnh để hiểu vì sao GC được kích hoạt.

## 11. Lấy nhiều mẫu với interval, count, timestamp và header

Một mẫu đơn lẻ chỉ cho biết trạng thái tại một thời điểm. Để theo dõi xu hướng, lấy nhiều mẫu.

Ví dụ 10 mẫu, mỗi giây một lần:

~~~bash
jstat -gcutil 12345 1s 10
~~~

Thêm timestamp tính từ lúc JVM khởi động:

~~~bash
jstat -gcutil -t 12345 1s 10
~~~

Lặp lại header sau mỗi 5 mẫu:

~~~bash
jstat -gcutil -t -h5 12345 1s 10
~~~

Ý nghĩa:

- -t: thêm cột Timestamp, tính bằng giây kể từ lúc JVM khởi động.
- -h5: in lại header sau mỗi 5 mẫu để output dài dễ đọc.
- 1s: khoảng cách giữa hai lần lấy mẫu.
- 10: tổng số mẫu cần lấy.

Trong JDK 24.0.2, lệnh sau đã được kiểm thử thành công:

~~~bash
jstat -gcutil -t -h2 12345 250ms 4
~~~

Nếu bỏ count, jstat tiếp tục in mẫu cho đến khi JVM kết thúc hoặc người dùng dừng lệnh. Khi theo dõi production, chọn interval vừa đủ để quan sát và tránh tạo quá nhiều output.

## 12. Hiểu bộ đếm GC tích lũy

Các cột YGC, FGC và thời gian GC thường là bộ đếm tích lũy từ lúc JVM bắt đầu chạy.

Ví dụ:

| Mẫu | YGC | YGCT | FGC | FGCT | GCT |
|---|---:|---:|---:|---:|---:|
| T1 | 20 | 0.120 | 1 | 0.030 | 0.150 |
| T2 | 24 | 0.145 | 1 | 0.030 | 0.175 |
| T3 | 30 | 0.190 | 2 | 0.060 | 0.250 |

Từ T1 đến T2:

- Có thêm 4 Young GC.
- Tổng thời gian Young GC tăng 0.025 giây.
- Không có Full GC mới.
- Tổng thời gian GC tăng 0.025 giây.

Từ T2 đến T3:

- Có thêm 6 Young GC.
- Có thêm 1 Full GC.
- Tổng thời gian GC tăng 0.075 giây.

Bảng trên là số liệu minh họa để giải thích cách lấy hiệu giữa hai mẫu; không phải output cố định của một JVM.

Để đánh giá xu hướng, tính chênh lệch giữa các mẫu:

- Delta YGC = YGC mẫu sau trừ YGC mẫu trước.
- Delta FGC = FGC mẫu sau trừ FGC mẫu trước.
- Delta GCT = GCT mẫu sau trừ GCT mẫu trước.

Tỷ lệ Delta GCT trên thời gian thực giữa hai mẫu có thể giúp ước lượng phần thời gian tích lũy được báo cáo cho GC. Đây không phải phép đo pause time chính xác, đặc biệt với collector có concurrent phase. Dùng GC log hoặc Java Flight Recorder khi cần phân tích pause và từng phase.

## 13. Phân tích heap statistics để tìm vấn đề

Một số dấu hiệu có thể dùng để định hướng điều tra:

### Eden tăng nhanh và YGC tăng liên tục

Ứng dụng có thể đang tạo object với tốc độ cao. Điều này có thể là hành vi bình thường của workload hoặc biểu hiện allocation pressure.

Kiểm tra allocation rate, object lifetime và GC log trước khi kết luận có vấn đề.

### Old space tăng qua nhiều chu kỳ GC

Nếu Old space tăng liên tục và không giảm đáng kể sau các chu kỳ GC tương đương, có thể có nhiều object được promote hoặc object còn được giữ tham chiếu lâu.

Hãy xem xét cache, session, queue, collection tĩnh và object retention.

### FGC hoặc FGCT tăng mạnh

Full GC có thể gây pause dài và ảnh hưởng latency. Kiểm tra nguyên nhân bằng -gccause, GC logs và JFR.

Một lần FGC không đủ để kết luận ứng dụng đang lỗi; cần xem tần suất, thời gian và workload.

### Metaspace tăng

Metaspace tăng có thể liên quan đến tải class mới, dynamic class generation hoặc class loader không được giải phóng.

Metaspace không phải Java Heap. Nếu nghi ngờ class loader leak, cần thêm class loading/unloading statistics và heap analysis.

### Tỷ lệ sử dụng cao nhưng ổn định

Một vùng heap có tỷ lệ sử dụng cao không nhất thiết là vấn đề nếu ứng dụng ổn định, GC hoạt động tốt và còn đủ capacity. Cần kết hợp latency, allocation, GC frequency và giới hạn heap.

Không kết luận memory leak từ một snapshot hoặc chỉ dựa vào phần trăm sử dụng.

## 14. Collector ảnh hưởng cách đọc số liệu

Tên cột của jstat được xây dựng theo các memory pool và generation mà JVM cung cấp. Cách diễn giải có thể khác theo collector.

- Với collector có Eden, Survivor và Old Generation rõ ràng, các cột S0/S1/E/O dễ liên hệ với các vùng này.
- Với G1, heap được chia thành regions và các region được phân loại động. Một số cột S0/S1 có thể hiển thị dấu - hoặc không phản ánh trực tiếp từng G1 region.
- Với ZGC hoặc Shenandoah, mô hình heap khác với generation truyền thống; không nên áp dụng máy móc cách đọc Eden/Survivor/Old.
- Metaspace và Compressed Class Space là vùng metadata riêng, không phải các generation của Java Heap.

Trước khi diễn giải, kiểm tra collector đang dùng bằng:

~~~bash
jcmd 12345 VM.flags
~~~

Tìm các flag như UseG1GC, UseSerialGC, UseParallelGC, UseZGC hoặc UseShenandoahGC nếu có. Đọc header và tài liệu đúng JDK/collector đang chạy.

## 15. So sánh jstat với jcmd và các công cụ khác

| Công cụ | Phù hợp khi |
|---|---|
| jstat -gc | Cần theo dõi dung lượng và mức sử dụng các vùng heap qua nhiều mẫu. |
| jstat -gcutil | Cần xem nhanh tỷ lệ phần trăm và xu hướng GC. |
| jstat -gccapacity | Cần xem capacity min/max/current của generation và space. |
| jstat -gccause | Cần biết nguyên nhân GC gần nhất/hiện tại. |
| jcmd GC.heap_info | Cần snapshot heap tổng quát tại một thời điểm. |
| jcmd VM.flags | Cần xem cấu hình heap và GC flag đang hiệu lực. |
| GC logs / JFR | Cần phân tích sâu thời gian pause, phase, allocation và xu hướng. |

jstat rất tiện cho việc lấy mẫu nhanh, còn jcmd cung cấp diagnostic command theo yêu cầu. Không dùng heap summary của jcmd thay cho chuỗi thời gian nếu mục tiêu là theo dõi xu hướng.

## 16. Quyền truy cập và theo dõi JVM từ xa

Đối với JVM cục bộ:

- Chạy jstat trên cùng máy với JVM đích.
- Dùng user có quyền truy cập instrumentation của JVM.
- Dùng lvmid vừa xác định bằng jps hoặc công cụ hệ điều hành.
- Với Docker, chạy công cụ trong container hoặc PID namespace có thể nhìn thấy JVM.

jstat hỗ trợ VMID từ xa thông qua hostname và RMI khi máy đích chạy jstatd. Ví dụ cú pháp:

~~~bash
jstat -gcutil 12345@remote.example 1s 10
~~~

Tuy nhiên, jstatd trên JDK 24 được đánh dấu experimental, unsupported và deprecated. jstatd không xác thực client từ xa; nó có thể làm lộ instrumentation của mọi JVM mà tài khoản chạy jstatd có quyền quan sát cho người dùng trên mạng.

Không bật jstatd trên production hoặc mạng không tin cậy nếu chưa có đánh giá bảo mật, giới hạn network access và chính sách phù hợp. Khi chỉ cần chẩn đoán tại máy, ưu tiên dùng jstat cục bộ.

## 17. Giới hạn và lưu ý khi dùng jstat

jstat được Oracle đánh dấu **experimental và unsupported**. Các option và chức năng có thể thay đổi hoặc bị loại bỏ trong các bản JDK tương lai.

Định dạng output cũng có thể thay đổi. Tài liệu JDK khuyến cáo không xây dựng script production phụ thuộc vào cách parse output jstat. Nếu buộc phải parse, cần chấp nhận rằng script có thể phải sửa khi nâng JDK.

Một số lưu ý khác:

- jstat theo dõi HotSpot VM đã instrument, không phải mọi process có tên java.
- LVMID thường nhưng không phải luôn là OS PID.
- Dữ liệu phụ thuộc collector và JDK version.
- jstat không cho biết toàn bộ RAM của process; native memory, direct buffer, thread stack và code cache cần được xem riêng.
- Một sample không đủ để kết luận memory leak hoặc GC bottleneck.
- Dùng interval hợp lý; tránh polling quá dày trên production.
- Output có thể phản ánh dữ liệu cấu hình và vận hành nhạy cảm; kiểm tra trước khi chia sẻ.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jstat is not recognized | JDK bin chưa nằm trong PATH hoặc chỉ cài runtime tối giản. | Kiểm tra JAVA_HOME, PATH và thư mục bin của JDK. |
| jstat -options không có option cần dùng | JDK/vendor/platform hiện tại không cung cấp option đó. | Dùng đúng option được liệt kê bởi jstat -options. |
| Invalid argument hoặc interval lỗi | Interval/count không phải số nguyên dương hoặc sai hậu tố. | Dùng dạng 250ms, 1s và count dương. |
| Could not find VM | Sai lvmid, JVM đã dừng hoặc user không có quyền. | Chạy jps -l, xác minh process và user. |
| Attach hoặc instrumentation failure | Khác user, namespace hoặc instrumentation không truy cập được. | Dùng cùng service account và đúng môi trường process. |
| Một số cột hiển thị dấu - | Collector hoặc memory pool không cung cấp cột đó. | Đọc các cột còn lại và kiểm tra collector. |
| Dung lượng không khớp -Xmx | jstat hiển thị capacity từng pool, không phải lúc nào cũng là maximum heap tổng. | Kiểm tra jcmd VM.flags và phân biệt current/max capacity. |
| YGC/FGC tăng nhưng heap used không giảm | Allocation liên tục, object được giữ tham chiếu hoặc promotion. | Theo dõi nhiều mẫu và xem GC logs/JFR. |
| GCT tăng nhưng latency không tương ứng | Bộ đếm thời gian GC không phải phép đo đầy đủ pause/latency. | Phân tích GC logs hoặc JFR. |
| jstat remote không kết nối được | jstatd/RMI registry chưa chạy, sai host/port hoặc firewall chặn. | Kiểm tra dịch vụ và chính sách mạng; không mở remote monitoring tùy tiện. |

## 19. Quy trình theo dõi heap statistics

Một quy trình dễ lặp lại:

1. Xác định JDK version và JVM đích.
2. Chạy jstat -options để biết các option có sẵn.
3. Dùng jps -l hoặc jcmd -l để tìm lvmid.
4. Chạy jstat -gc để xem dung lượng theo KB.
5. Chạy jstat -gcutil để xem tỷ lệ sử dụng theo phần trăm.
6. Dùng -gccapacity, -gcnew hoặc -gcold khi cần chi tiết vùng cụ thể.
7. Dùng -gccause để kiểm tra nguyên nhân GC.
8. Thêm -t, interval và count để lấy chuỗi mẫu có thời gian.
9. So sánh delta của bộ đếm và mức sử dụng qua nhiều chu kỳ GC.
10. Dùng jcmd VM.flags để xác nhận cấu hình heap/collector.
11. Dùng GC logs hoặc JFR nếu cần phân tích sâu.
12. Ghi nhận JDK, collector, workload và thời điểm lấy mẫu khi báo cáo.

## 20. Checklist trước khi kết luận heap có vấn đề

- [ ] Đã xác định đúng JVM và lvmid.
- [ ] Đã kiểm tra các option có sẵn bằng jstat -options.
- [ ] Đã hiểu đơn vị KB của -gc và phần trăm của -gcutil.
- [ ] Đã phân biệt capacity hiện tại với maximum capacity.
- [ ] Đã hiểu YGC, FGC và thời gian GC là bộ đếm tích lũy.
- [ ] Đã xem xét collector trước khi diễn giải S0/S1/E/O.
- [ ] Đã lấy nhiều mẫu với interval/count phù hợp.
- [ ] Đã kiểm tra nguyên nhân GC nếu bộ đếm tăng bất thường.
- [ ] Đã phân biệt Java Heap với Metaspace và native memory.
- [ ] Đã so sánh xu hướng sau các chu kỳ GC tương đương.
- [ ] Đã dùng GC logs/JFR nếu cần phân tích pause hoặc allocation.
- [ ] Đã xem xét quyền truy cập và rủi ro của jstatd khi theo dõi từ xa.
- [ ] Đã ghi nhận jstat là công cụ experimental/unsupported và output có thể thay đổi.

## 21. Tài liệu tham khảo

- Oracle JDK 24 — The jstat Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jstatd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstatd.html

jstat giúp theo dõi heap và hoạt động GC qua nhiều mẫu liên tiếp. Khi chọn đúng option, hiểu đơn vị và bộ đếm tích lũy, xét đến collector và so sánh xu hướng thay vì một snapshot, bạn có thể nhận diện allocation pressure và dấu hiệu bất thường để điều tra sâu hơn bằng jcmd, GC logs hoặc Java Flight Recorder.