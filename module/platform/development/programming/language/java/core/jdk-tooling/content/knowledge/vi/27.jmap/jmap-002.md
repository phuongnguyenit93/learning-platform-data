# Heap summary của JVM với jmap và jcmd

## 1. Heap summary là gì?

**Heap summary** là bản tóm tắt trạng thái vùng nhớ Java Heap tại một thời điểm. Nó cho biết heap đang được tổ chức ra sao, garbage collector (GC) đang sử dụng, dung lượng heap đã dùng và dung lượng đã được JVM cấp phát hoặc đặt trước.

Heap summary thường giúp trả lời:

- JVM đang dùng garbage collector nào?
- Heap hiện có bao nhiêu dung lượng đã dùng?
- JVM đã commit bao nhiêu bộ nhớ cho heap?
- Heap có thể mở rộng tới mức nào?
- Với collector chia generation hoặc region, các vùng Eden, Survivor, Old hoặc G1 region đang ở trạng thái nào?
- Metaspace và Compressed Class Space đang sử dụng bao nhiêu?

Heap summary là ảnh chụp tại thời điểm truy vấn. Nó giúp đánh giá nhanh áp lực bộ nhớ, nhưng một kết quả đơn lẻ không đủ để kết luận ứng dụng bị memory leak.

## 2. jmap -heap và thay đổi giữa các JDK

Trong các tài liệu và bản JDK cũ, bạn có thể gặp lệnh:

~~~bash
jmap -heap <pid>
~~~

Lệnh này từng được dùng để in thông tin GC, cấu hình heap và mức sử dụng của từng generation/space. Tuy nhiên, tùy chọn có thể khác nhau theo JDK release và nền tảng.

Trên JDK 24.0.2 được kiểm tra trong môi trường hiện tại:

- jmap -h không liệt kê tùy chọn -heap.
- Chạy jmap -heap <pid> kết thúc với exit code 1 và thông báo: Cannot connect to core dump or remote debug server. Use jhsdb jmap instead.
- Đối với JVM đang chạy, lệnh được khuyến nghị để lấy heap summary là jcmd <pid> GC.heap_info.

Vì vậy, trước khi dùng cú pháp từ tài liệu cũ, hãy xem help của đúng JDK:

~~~bash
jmap -h
jcmd -h
jhsdb jmap --help
~~~

Oracle đánh dấu jmap là công cụ experimental và unsupported, đồng thời khuyến nghị dùng jcmd cho chẩn đoán mới vì có nhiều diagnostic command hơn và giảm performance overhead.

## 3. Lấy heap summary từ JVM đang chạy bằng jcmd

Quy trình cơ bản:

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Kiểm tra command mà JVM đích hỗ trợ:

~~~bash
jcmd <pid> help GC.heap_info
~~~

Lấy heap summary:

~~~bash
jcmd <pid> GC.heap_info
~~~

Ví dụ, nếu PID của ứng dụng là 12345:

~~~bash
jcmd 12345 GC.heap_info
~~~

Trên JDK 24.0.2, GC.heap_info được mô tả là cung cấp thông tin tổng quát về Java heap. Help của command báo Impact: Medium; hãy cân nhắc tác động trước khi chạy trên production và tránh gọi liên tục với tần suất cao.

jcmd phải chạy trên cùng máy với JVM đích và dùng cùng effective user/group đã khởi chạy JVM. Nếu không tìm thấy process hoặc attach thất bại, kiểm tra PID, user, container namespace và cấu hình Attach mechanism.

## 4. Tạo JVM mẫu để thực hành

Tạo file **HeapSummaryProbe.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapSummaryProbe {
    private static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 24; i++) {
            KEEP.add(new byte[1024 * 1024]);
        }

        System.out.println(
                "HeapSummaryProbe ready; pid=" +
                ProcessHandle.current().pid());
        System.out.println("retainedMiB=" + KEEP.size());

        Thread.sleep(120_000);
    }
}
~~~

Chương trình giữ lại 24 mảng byte, mỗi mảng 1 MiB, để heap có dữ liệu thực tế trong lúc quan sát. Thread.sleep giữ JVM chạy trong hai phút.

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 HeapSummaryProbe.java
~~~

Chạy với heap giới hạn 128 MiB và G1 GC:

~~~bash
java -Xms64m -Xmx128m -XX:+UseG1GC -Dprobe.heap=summary HeapSummaryProbe
~~~

Stdout có dạng:

~~~text
HeapSummaryProbe ready; pid=12345
retainedMiB=24
~~~

PID thay đổi theo mỗi lần chạy. Mở terminal thứ hai, lấy PID vừa in ra rồi thực hiện:

~~~bash
jcmd 12345 GC.heap_info
~~~

Sau khi hoàn thành kiểm tra, quay lại terminal thứ nhất và nhấn Ctrl+C để dừng chương trình mẫu.

Ví dụ này đã được biên dịch với javac --release 17 và kiểm tra bằng JDK 24.0.2.

## 5. Ví dụ heap summary với G1 GC

Một kết quả đại diện từ JVM thử nghiệm trên JDK 24.0.2:

~~~text
12345:
 garbage-first heap   total reserved 131072K, committed 83968K, used 50900K
 region size 1024K, 2 young (2048K), 1 survivors (1024K)
 Metaspace       used 337K, committed 512K, reserved 1114112K
  class space    used 21K, committed 128K, reserved 1048576K
~~~

Giá trị thực tế thay đổi theo thời điểm, JDK, collector, cấu hình và số lượng object. Địa chỉ vùng nhớ có thể được in thêm ở cuối dòng heap.

Các trường chính:

- **total reserved:** vùng địa chỉ heap mà JVM đã reserve. Đây là vùng địa chỉ ảo, không đồng nghĩa toàn bộ lượng RAM vật lý đã được sử dụng.
- **committed:** lượng bộ nhớ JVM đã commit cho heap và có thể dùng cho allocation.
- **used:** lượng heap hiện đang được sử dụng bởi các object và cấu trúc heap.
- **region size:** kích thước một region của G1.
- **young:** số region hiện thuộc young generation và tổng dung lượng của chúng.
- **survivors:** số region survivor và dung lượng tương ứng.
- **Metaspace:** bộ nhớ native dùng để lưu class metadata.
- **class space:** vùng Compressed Class Space dùng cho class metadata khi cơ chế compressed class pointers được áp dụng.

Trong ví dụ, G1 có tổng vùng reserved 131072K (128 MiB), committed 83968K và used 50900K. Region size là 1024K (1 MiB).

Không nên hiểu reserved là RAM đã tiêu thụ. Phân biệt reserved, committed và used giúp tránh kết luận sai khi so sánh heap với mức RAM mà hệ điều hành báo cáo.

## 6. Đọc committed, used và maximum heap

Ba khái niệm thường bị nhầm:

| Giá trị | Ý nghĩa |
|---|---|
| Initial heap (-Xms) | Dung lượng heap ban đầu JVM được cấu hình. |
| Maximum heap (-Xmx) | Giới hạn heap tối đa được cấu hình cho JVM. |
| Committed heap | Dung lượng JVM đã commit để dùng cho heap tại thời điểm truy vấn. |
| Used heap | Dung lượng đang được dùng trong heap tại thời điểm truy vấn. |
| Reserved heap | Vùng địa chỉ ảo JVM đã đặt trước cho heap. |

Để xem các VM flags liên quan:

~~~bash
jcmd 12345 VM.flags
~~~

Với chương trình mẫu chạy bằng -Xms64m -Xmx128m, output có thể chứa:

~~~text
-XX:InitialHeapSize=67108864
-XX:MaxHeapSize=134217728
-XX:+UseG1GC
~~~

Các số byte tương ứng:

- 67108864 bytes = 64 MiB.
- 134217728 bytes = 128 MiB.

VM.flags cho biết cấu hình flag, còn GC.heap_info cho biết trạng thái heap. Dùng hai command cùng nhau để phân biệt giới hạn được cấu hình với dung lượng đã commit và đang sử dụng.

Không giả định committed luôn bằng -Xmx. JVM có thể commit heap dần theo nhu cầu, trong khi giới hạn tối đa vẫn lớn hơn.

## 7. Metaspace không nằm trong Java Heap

Heap summary thường hiển thị Metaspace và Class Space cùng phần heap, nhưng hai vùng này không phải Java object heap.

- **Java Heap:** lưu các object và array được cấp phát bởi ứng dụng và JVM.
- **Metaspace:** lưu metadata liên quan đến class, method và runtime type.
- **Compressed Class Space:** vùng dành cho compressed class pointers khi JVM sử dụng cơ chế này.
- **Native memory:** còn bao gồm thread stacks, code cache, GC structures, direct buffers và các allocation native khác.

Một ứng dụng có thể có heap used thấp nhưng vẫn tiêu thụ nhiều native memory hoặc Metaspace. Vì vậy, không dùng heap summary để giải thích toàn bộ RSS hoặc mức RAM của process.

Nếu cần kiểm tra native memory, có thể dùng Native Memory Tracking (NMT) khi đã bật từ lúc khởi động JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó truy vấn:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT phải được bật từ lúc JVM khởi chạy. Nếu chưa bật, không thể bắt đầu thu thập đầy đủ dữ liệu hồi tố chỉ bằng một lệnh jcmd sau đó.

## 8. Heap summary phụ thuộc garbage collector

Cấu trúc output phản ánh cách collector quản lý heap. Không phải JVM nào cũng có cùng các generation hoặc space.

### G1 GC

G1 chia heap thành các region có kích thước bằng nhau. Các region được phân loại động theo vai trò như Eden, Survivor và Old.

Heap summary có thể hiển thị:

- Tổng reserved, committed và used.
- Region size.
- Số young region và survivor region.
- Metaspace và class space.

Số region young/survivor thay đổi theo allocation và chu kỳ GC. Không coi số region tại một thời điểm là cấu hình cố định.

### Serial GC

Với Serial GC, output có thể hiển thị các vùng generation truyền thống như DefNew, Eden, From Space, To Space và Tenured.

Ví dụ kết quả thực tế từ JVM thử nghiệm trên JDK 24.0.2:

~~~text
DefNew     total 19648K, used 10664K
 eden space 17472K, 48% used
 from space 2176K, 98% used
 to   space 2176K, 0% used
Tenured    total 43712K, used 15472K
 the space 43712K, 35% used
Metaspace  used 337K, committed 512K, reserved 1114112K
 class space used 21K, committed 128K, reserved 1048576K
~~~

Trong Serial GC:

- **Eden:** vùng thường nhận allocation object mới.
- **From Space / To Space:** hai vùng survivor luân phiên trong quá trình young collection.
- **Tenured:** vùng chứa object đã được promote sang old generation.

Tỷ lệ sử dụng thay đổi theo thời điểm chụp và chu kỳ GC.

### Parallel GC và các collector khác

Parallel GC cũng có mô hình young/old generation truyền thống, nhưng số thread và cách phân bổ space phụ thuộc cấu hình.

ZGC, Shenandoah và các collector khác có cách tổ chức và output riêng. Không nên áp dụng máy móc cách đọc Eden/Survivor/Old cho mọi collector.

Luôn xác nhận collector qua VM flags hoặc JVM configuration và đọc đúng các trường xuất hiện trong output của target.

## 9. Heap summary là snapshot, không phải báo cáo memory leak

Một lần chạy:

~~~bash
jcmd 12345 GC.heap_info
~~~

chỉ phản ánh trạng thái tại thời điểm command được xử lý.

Giá trị used có thể tăng do allocation bình thường, rồi giảm sau khi GC thu hồi object không còn được tham chiếu. Một heap có used cao trước GC không tự động có nghĩa ứng dụng bị leak.

Để điều tra xu hướng:

1. Thu thập heap summary ở nhiều thời điểm với khoảng cách hợp lý.
2. Ghi lại thời điểm, collector, -Xms, -Xmx và workload.
3. So sánh mức used sau các chu kỳ GC tương đương.
4. Kiểm tra xem live set sau GC có tăng liên tục hay không.
5. Kết hợp GC log hoặc Java Flight Recorder để xem allocation và thời gian GC.
6. Nếu cần xác định object giữ bộ nhớ, tạo heap dump theo quy trình được phê duyệt rồi phân tích bằng công cụ chuyên dụng.

Nếu used tăng liên tục sau các chu kỳ GC tương đương và không trở về mức nền, đó là dấu hiệu cần điều tra. Vẫn phải xem workload, cache, session, queue và object retention trước khi kết luận memory leak.

Không ép Full GC chỉ để làm một con số used đẹp hơn. Việc ép GC có thể làm tăng pause và thay đổi hành vi ứng dụng.

## 10. Khi nào cần heap histogram hoặc heap dump?

Heap summary cho biết tổng quan dung lượng, nhưng không chỉ ra class nào chiếm bộ nhớ.

### Heap histogram

Histogram cho biết số lượng instance và tổng byte theo class.

Có thể dùng jmap:

~~~bash
jmap -histo 12345
~~~

Hoặc dùng jcmd:

~~~bash
jcmd 12345 GC.class_histogram
~~~

Histogram hữu ích khi muốn tìm class có số lượng object hoặc dung lượng lớn. Nó không cung cấp đầy đủ object reference graph để xác định vì sao object còn được giữ.

### Heap dump

Heap dump lưu nội dung object heap để phân tích sâu:

~~~bash
jcmd 12345 GC.heap_dump filename=heap.hprof
~~~

Heap dump có thể rất lớn, làm tăng I/O và gây pause đáng kể. File có thể chứa password, token, dữ liệu cá nhân và nội dung ứng dụng đang xử lý. Cần có đủ dung lượng đĩa, quyền truy cập hạn chế và chính sách lưu trữ phù hợp.

Heap dump không phải heap summary. Chỉ tạo khi cần phân tích object retention và đã đánh giá tác động vận hành.

## 11. jhsdb jmap --heap và core dump

JDK 24 cung cấp jhsdb jmap --heap để in heap summary trong quy trình Serviceability Agent. Với postmortem analysis, có thể đọc core dump:

~~~bash
jhsdb jmap --heap --core core.12345 --exe /path/to/java
~~~

Trong đó:

- --heap: yêu cầu in Java heap summary.
- --core: đường dẫn core dump.
- --exe: executable Java tương ứng với core dump đó.

Hai tùy chọn --core và --exe phải được cung cấp cùng nhau. Executable phải phù hợp với JVM đã tạo ra core; không tùy tiện dùng một binary Java khác phiên bản.

Help cũng có --pid để attach vào JVM đang chạy:

~~~bash
jhsdb jmap --heap --pid 12345
~~~

Tuy nhiên, jhsdb là công cụ experimental và unsupported. Tài liệu JDK cảnh báo attach vào process đang chạy có thể khiến process bị treo và có thể crash khi debugger detach. Vì vậy, dùng jcmd GC.heap_info cho live heap summary thông thường; dành jhsdb jmap --heap cho core dump/postmortem khi có yêu cầu phân tích phù hợp.

## 12. Quyền truy cập và tác động khi chạy diagnostic command

Để jcmd kết nối JVM:

- Chạy trên cùng máy với JVM đích.
- Dùng cùng effective user/group đã khởi chạy JVM.
- Xác minh PID còn tồn tại và thuộc đúng ứng dụng.
- Kiểm tra Attach mechanism chưa bị vô hiệu hóa.
- Với container, chạy trong đúng PID namespace và môi trường có thể truy cập JVM.

Xem impact của heap command:

~~~bash
jcmd 12345 help GC.heap_info
~~~

Trên JDK 24.0.2, command được báo Impact: Medium. Không nên chạy theo vòng lặp dày đặc hoặc gắn vào mọi JVM mà không có mục tiêu rõ ràng.

jmap và jhsdb là các công cụ experimental/unsupported trong tài liệu JDK 24. Với quy trình vận hành mới, ưu tiên diagnostic command của jcmd và kiểm tra help của chính JVM đích.

## 13. Lỗi thường gặp khi lấy heap summary

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jmap -heap báo lỗi | Tùy chọn cũ không được binary JDK hiện tại hỗ trợ. | Dùng jcmd PID GC.heap_info cho live JVM. |
| jcmd không tìm thấy PID | PID sai, process đã dừng hoặc đang ở namespace khác. | Chạy lại jcmd -l trong đúng môi trường. |
| Attach permission denied | User hiện tại không có quyền attach. | Dùng đúng service account và kiểm tra quyền OS. |
| GC.heap_info không được hỗ trợ | JVM/collector/vendor không cung cấp command tương ứng. | Chạy jcmd PID help và kiểm tra tool phù hợp. |
| Output khác ví dụ | Khác JDK, GC, flags hoặc thời điểm snapshot. | Đọc tên collector và các trường thực tế, không dựa vào vị trí dòng cố định. |
| Used thấp nhưng process RAM cao | Native memory, Metaspace, direct buffers, stacks hoặc code cache chiếm bộ nhớ. | Kiểm tra NMT, OS metrics và runtime configuration. |
| Heap used cao ở một snapshot | Allocation đang diễn ra hoặc GC chưa thu hồi object. | Theo dõi nhiều lần và so sánh sau GC tương đương. |
| Heap summary không chỉ ra class gây tốn bộ nhớ | Summary chỉ cung cấp số liệu tổng quát. | Dùng class histogram hoặc heap dump khi cần. |
| jhsdb làm process treo | Serviceability Agent attach vào live process. | Tránh dùng trên live process; ưu tiên jcmd hoặc phân tích core dump. |
| Heap dump hết dung lượng đĩa | File dump lớn hơn dung lượng trống. | Kiểm tra disk capacity và chính sách lưu trữ trước khi dump. |

## 14. Quy trình lấy và đọc heap summary

Một quy trình thực tế:

1. Xác định JDK và phiên bản JVM đang chạy.
2. Chạy jcmd -l để tìm đúng PID.
3. Kiểm tra jcmd PID help GC.heap_info.
4. Chạy jcmd PID GC.heap_info và lưu output nếu cần.
5. Đọc collector, reserved, committed, used, region/generation và Metaspace.
6. Dùng jcmd PID VM.flags để đối chiếu InitialHeapSize, MaxHeapSize và GC flags.
7. So sánh nhiều snapshot theo cùng workload và thời điểm tương đương.
8. Nếu nghi ngờ memory leak, dùng GC log/JFR và histogram để tìm hướng điều tra.
9. Chỉ tạo heap dump sau khi đánh giá pause, dung lượng đĩa và bảo mật dữ liệu.
10. Với JVM đã crash, dùng core dump và jhsdb jmap --heap --core ... --exe ....

Không đưa PID, heap size hoặc region count của một lần chạy vào cấu hình cố định. Các giá trị này phụ thuộc process và runtime.

## 15. Checklist trước khi kết luận heap đang thiếu bộ nhớ

- [ ] Đã xác nhận đúng JVM và PID.
- [ ] Đã kiểm tra JDK version và garbage collector.
- [ ] Đã dùng jcmd PID GC.heap_info cho live heap summary.
- [ ] Đã phân biệt reserved, committed, used và maximum heap.
- [ ] Đã kiểm tra -Xms, -Xmx bằng jcmd PID VM.flags.
- [ ] Đã phân biệt Java Heap với Metaspace và native memory.
- [ ] Đã xem xét cấu trúc generation/region phù hợp với collector.
- [ ] Đã so sánh nhiều snapshot thay vì kết luận từ một thời điểm.
- [ ] Đã đối chiếu GC logs hoặc JFR nếu cần tìm xu hướng.
- [ ] Đã dùng histogram/heap dump chỉ khi cần tìm class và object retention.
- [ ] Đã đánh giá impact, quyền attach, dung lượng đĩa và độ nhạy cảm dữ liệu.
- [ ] Đã tránh jhsdb attach trực tiếp vào live production process.

## 16. Tài liệu tham khảo

- Oracle JDK 24 — Diagnostic Tools, phần jmap và heap configuration/usage: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html

Heap summary giúp xác định nhanh trạng thái Java Heap và cách collector tổ chức vùng nhớ. Trên JDK hiện đại, jcmd PID GC.heap_info là lựa chọn phù hợp cho JVM đang chạy; hãy đọc các số liệu cùng collector, VM flags và xu hướng GC để đưa ra kết luận chính xác.