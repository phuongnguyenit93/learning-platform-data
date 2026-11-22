# Đọc nguyên nhân, thời gian và mức sử dụng heap trong nhật ký GC — G1 Full GC song song

## 1. Vì sao phải đọc đúng nhật ký Garbage Collection?

**Garbage Collection (GC)** là cơ chế JVM tìm và thu hồi bộ nhớ chứa đối tượng Java không còn reachable. Trong ứng dụng chạy lâu, các lần GC có thể tác động đến **độ trễ (latency)**, thông lượng, áp lực cấp phát và mức sử dụng Java heap. Với **G1 (Garbage-First Garbage Collector)**, ta cần phân biệt những lần **Young GC**, **Mixed GC**, các pha đánh dấu đồng thời và **Full GC**.

Một tình huống cần phân tích: ứng dụng đột nhiên ngừng phản hồi trong vài trăm mili giây hoặc vài giây. Log có thể ghi:

~~~text
[0.106s][info][gc] GC(0) Pause Full (System.gc()) 9M->3M(64M) 4.042ms
~~~

Dòng này chứa nhiều thông tin, nhưng cũng có nhiều điều **không thể** suy ra chỉ từ một dòng:

- `Pause Full`: đây là **một lần Full GC**, khác Young/Mixed GC.
- `System.gc()`: **nguyên nhân được JVM báo** là yêu cầu GC tường minh, không phải bằng chứng thiếu heap do ứng dụng cấp phát quá nhiều.
- `9M->3M`: mức **heap used trước/sau** sự kiện, được hiển thị với đơn vị và độ chính xác theo log.
- `(64M)`: **sức chứa heap ở thời điểm sự kiện**, không có nghĩa 64 MiB đều đã được dùng và cũng không luôn đồng nghĩa với `-Xmx` trong mọi cấu hình.
- `4.042ms`: **thời lượng dừng được báo cho sự kiện GC** trong ví dụ, không phải thời gian CPU của một luồng.
- `GC(0)`: định danh sự kiện để nối các dòng `gc,start`, `gc,task`, `gc,phases`, `gc,heap` và `gc,cpu`.

Trong ngữ cảnh **“G1 Full GC song song”**, từ **Java 10**, **JEP 307** cải tiến G1 bằng cách dùng nhiều GC workers cho đường Full GC. Tuy nhiên, **Full GC vẫn là stop-the-world (STW)**: các luồng Java application không được chạy song song với các tác vụ Full GC đó trong khoảng dừng tương ứng. “Song song” là **các luồng GC làm việc cùng nhau**, không phải “ứng dụng vẫn chạy bình thường trong Full GC”.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc chính xác **nguyên nhân, loại GC, thời lượng, heap before/after/capacity** trong dòng log G1.
2. Dùng **`GC(n)`** để nhóm các dòng cùng một GC, thay vì ghép nhầm những sự kiện khác nhau.
3. Biết cách bật `-Xlog:gc`, `-Xlog:gc*` và những tag chuyên sâu `gc+heap`, `gc+phases`, `gc+task`, `gc+cpu` trên JDK hiện đại.
4. Phân biệt **Full GC song song** với **Parallel GC collector** và với **concurrent marking** của G1.
5. Đọc worker count, các pha Mark/Prepare/Adjust/Compact và thời gian pause mà không cộng nhầm thời lượng pha.
6. Nhận biết các nguyên nhân thường gặp: `System.gc()`, áp lực cấp phát, evacuation failure, humongous objects và Full GC như phương án cuối.
7. Không nhầm Java heap với committed/reserved memory, metaspace, direct memory hoặc RSS của process/container.
8. Chạy ví dụ Java 17+, tạo log thật, rồi so sánh với minh họa và đề xuất cách điều tra sự cố.
9. Tránh giả định các con số trong log mẫu cố định trên mọi JDK, OS, CPU hay workload.
10. Viết báo cáo phân tích GC có phạm vi và bằng chứng, không kết luận quá mức từ một dòng.

**Special Note — chỉ kiến thức hiện hành:** Bài sử dụng **Unified Logging `-Xlog`** và tài liệu G1/JDK còn hiệu lực. Không dùng các cờ logging đã lỗi thời để hướng dẫn vận hành mới.

## 2. Bối cảnh Java 10: JEP 307 cải thiện Full GC của G1

G1 là collector có thiết kế chủ yếu để hạn chế các **pause lớn** bằng cách dọn dẹp những vùng heap theo các chu kỳ young/mixed và marking đồng thời. Nhưng khi áp lực heap quá cao, không còn vùng thích hợp để di chuyển đối tượng, hoặc có yêu cầu GC tường minh theo cấu hình, JVM có thể cần **Full GC**.

Trước cải tiến trong **Java 10**, đường Full GC của G1 từng có phần thực thi chủ yếu theo một luồng, khiến Full GC trên heap lớn có thể kéo dài. **JEP 307 — Parallel Full GC for G1** thay đổi đường Full GC để tận dụng **các GC threads làm việc song song**, với số worker được lựa chọn bởi HotSpot theo tài nguyên và cấu hình.

Các khái niệm cần phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **G1** | Bộ thu gom rác Garbage-First, chọn vùng heap để tối ưu mục tiêu pause và throughput. |
| **Young GC** | Thu gom chủ yếu young generation; không đồng nghĩa quét toàn bộ heap. |
| **Mixed GC** | Một collection của G1 có tập vùng young và một số vùng old đủ điều kiện. |
| **Concurrent marking** | Một số công việc đánh dấu diễn ra đồng thời với ứng dụng. |
| **Full GC (G1 Compaction Pause)** | Đường thu gom/compact toàn heap khi G1 cần; thường tốn kém, **STW**. |
| **Parallel Full GC (G1)** | Các worker GC thực hiện một số pha Full GC song song — cải tiến từ Java 10. |
| **Parallel GC / `-XX:+UseParallelGC`** | **Một collector khác**, không phải cách gọi “G1 Full GC dùng nhiều worker”. |

**Câu hỏi QA quan trọng:** Khi thấy “Using 2 workers of 2 for full compaction”, đó là **đường Full GC của G1 dùng hai worker**, không có nghĩa JVM đã chuyển sang collector `UseParallelGC`.

### 2.1. Full GC vẫn là stop-the-world

Với Full GC của G1:

- Các luồng chạy Java application phải dừng cho hoạt động thu gom của sự kiện STW.
- Nhiều GC workers có thể phối hợp để làm các bước của Full GC nhanh hơn.
- Thời lượng dừng vẫn ảnh hưởng trực tiếp tới độ trễ xử lý request.
- Tăng số worker không bảo đảm pause luôn ngắn hơn: còn overhead, CPU quota, kích thước live set, cấu trúc heap và mức độ song song thực tế.

**Không** kết luận “Parallel Full GC = concurrent with application”. **Parallel** nói về nhiều worker GC, còn **concurrent** nói về công việc GC được thực hiện trong khi application threads tiếp tục chạy.

## 3. Bật nhật ký G1 GC theo cách hiện đại

HotSpot hỗ trợ **Java Unified Logging**:

~~~text
-Xlog:<tag-selector>=<level>:<output>:<decorators>:<output-options>
~~~

Với GC, các mức thường dùng:

| Cờ | Thông tin điển hình | Khi nào dùng |
| --- | --- | --- |
| `-Xlog:gc` | Sự kiện GC ở mức tổng quan, nguyên nhân, before/after/capacity và duration. | Bắt đầu điều tra, log tương đối gọn. |
| `-Xlog:gc*` | Tất cả các tag set chứa `gc` ở mức mặc định, thường thêm heap/phases/task/cpu. | Xem chi tiết G1. |
| `-Xlog:gc*=debug` | Nhiều hoạt động GC ở mức debug. | Chẩn đoán chuyên sâu, thời gian giới hạn. |
| `-Xlog:gc+heap=info` | Một số thay đổi vùng heap của G1. | Xem Eden/Survivor/Old/Humongous. |
| `-Xlog:gc+heap=debug` | Thêm snapshot heap trước/sau theo hỗ trợ của HotSpot. | Khi cần byte/KB/capacity chi tiết hơn. |
| `-Xlog:gc+phases=info` | Các pha bên trong pause. | Xác định pha tốn thời gian. |
| `-Xlog:gc+task=info` | Thông tin worker GC. | Xem mức song song thực tế. |
| `-Xlog:gc+cpu=info` | User/Sys/Real time trong một số event. | Đối chiếu CPU time với elapsed time. |

**Điểm cú pháp:** `-Xlog:gc` không tương đương `-Xlog:gc*`. Dấu `*` là wildcard chọn các tổ hợp tag có chứa `gc`; các nhóm `gc,heap` hoặc `gc,task` có thể không được chọn chỉ bằng selector `gc` đơn lẻ.

### 3.1. Lệnh gọn để thu log vào file

~~~bash
java -XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Đây là **mẫu cho ứng dụng thật**, yêu cầu `app.jar` thực sự chạy được bằng `-jar`. Các thành phần:

- `-XX:+UseG1GC`: lựa chọn G1 một cách tường minh.
- `gc*`: bao gồm các tag sets liên quan GC.
- `file=gc.log`: ghi ra file, không trộn log GC với stdout ứng dụng.
- `time,uptime,level,tags`: cung cấp timestamp, uptime, level và tag.
- `filecount=5,filesize=20M`: cấu hình rotation để giới hạn log tăng vô hạn.

Không nên bật debug/trace chi tiết trong production vô thời hạn; có thể tăng I/O, tiêu thụ đĩa và làm log khó đọc.

### 3.2. Khi cần tách chỉ số chi tiết để tái hiện

Trong lab của bài này, cú pháp **đã chạy thành công**:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:ParallelGCThreads=2 -Xlog:gc*,gc+heap=debug,gc+task=debug:file=gc.log:uptime,level,tags -cp . G1GcLogDemo
~~~

Lệnh sau sử dụng **một JVM HotSpot** với heap được cố định 64 MiB trong lab, yêu cầu hai worker GC tối đa, đồng thời ghi chi tiết heap/task trong `gc.log`.

**Không** bê nguyên `-Xms64m -Xmx64m` vào production của một ứng dụng lớn: heap quá nhỏ có thể gây GC liên tục hoặc `OutOfMemoryError`. Những giá trị này chỉ phục vụ thí nghiệm ngắn, không phải gợi ý cấu hình phổ quát.

### 3.3. Tránh những cờ logging legacy

Tài liệu launcher hiện hành hướng dẫn dùng **`-Xlog`** để thay các cờ ghi GC log cũ. Khi cấu hình mới, không lấy bộ cờ cũ của thời JDK 8 làm nền; hãy chọn tag/level/output theo **JDK đang sử dụng**.

Kiểm tra trực tiếp HotSpot:

~~~bash
java -Xlog:help
~~~

Lệnh này hiển thị tag, level, decorator và output option thực sự có trong bản runtime. Đây là cách phù hợp khi chuyển giữa các JDK/VM khác nhau.

## 4. Chương trình Java 17+ hoàn chỉnh tạo một sự kiện Full GC để học

**Mục đích lab:** tạo lượng đối tượng tạm, giữ lại một đối tượng còn reachable, yêu cầu GC tường minh và xem log để tập đọc **cause, duration, heap usage và worker count**.

**Cảnh báo:** `System.gc()` ở đây chỉ dùng để **làm bài lab dễ tái hiện**; không phải khuyến nghị chèn vào ứng dụng production để “tối ưu bộ nhớ”. `System.gc()` chỉ là một **yêu cầu**; JDK flags có thể bỏ qua hoặc đổi sang concurrent cycle. Chương trình không nên dùng GC như điều kiện logic cần thiết để chạy đúng.

Tạo file **`G1GcLogDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1GcLogDemo {
    private static final List<byte[]> retained = new ArrayList<>();

    private static int allocateTemporary() {
        List<byte[]> temporary = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            temporary.add(new byte[256 * 1024]);
        }
        return temporary.size();
    }

    public static void main(String[] args) {
        retained.add(new byte[1024 * 1024]);
        System.out.println(
                "temporary-arrays=" + allocateTemporary());

        System.gc();

        System.out.println(
                "retained-arrays=" + retained.size());
    }
}
~~~

**Giải thích code:**

- `retained` là `static final List<byte[]>`: reference tới danh sách giữ một `byte[]` sống qua lần GC. `final` ở đây **không** có nghĩa phần tử của danh sách là immutable.
- `allocateTemporary()` tạo 16 mảng, mỗi mảng `256 * 1024` byte; khi phương thức trả về, danh sách tạm không còn được giữ theo logic chương trình.
- Chương trình có thể nạp thêm một số lớp và đối tượng runtime, nên **heap used không bằng đúng tổng byte của các mảng**.
- `System.gc()` dùng để yêu cầu JVM thực hiện GC, không trả một `GcResult` hoặc cho biết số byte được thu hồi.
- Hai dòng stdout phản ánh giá trị từ code, **không phải phép đo mức heap**. Để xem heap, đọc log JVM.
- Việc compiler/JIT kéo dài hay rút ngắn lifetime của object, layout đối tượng và region sizing có thể làm số liệu heap khác giữa các lần chạy.

### 4.1. Biên dịch và chạy trên JDK 17+

~~~bash
javac -encoding UTF-8 G1GcLogDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:ParallelGCThreads=2 -Xlog:gc*,gc+heap=debug,gc+task=debug:file=gc.log:uptime,level,tags G1GcLogDemo
~~~

**Stdout đã kiểm chứng bằng HotSpot JDK 24.0.2:**

~~~text
temporary-arrays=16
retained-arrays=1
~~~

Có thể dùng `-cp .` trước tên class nếu cần chạy từ thư mục hiện tại:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:ParallelGCThreads=2 -Xlog:gc*,gc+heap=debug,gc+task=debug:file=gc.log:uptime,level,tags -cp . G1GcLogDemo
~~~

Lưu ý máy có thể không cho tạo file `gc.log` tại working directory nếu thiếu quyền. Trong container hoặc CI, hãy chọn đường dẫn ghi được hoặc hướng log ra stdout được quản lý.

### 4.2. Một log thực nghiệm đã được kiểm chứng trên JDK 24

Các dòng dưới đây là **trích log của cùng sự kiện GC(0)** từ lần chạy lab, không phải giá trị “cần phải thấy” trên mọi máy:

~~~text
[0.033s][info ][gc     ] Using G1
[0.034s][info ][gc,init] Heap Region Size: 1M
[0.035s][info ][gc,init] Heap Initial Capacity: 64M
[0.035s][info ][gc,init] Heap Max Capacity: 64M
[0.102s][info ][gc,start] GC(0) Pause Full (System.gc())
[0.103s][debug][gc,heap] GC(0) Heap before GC invocations=0 (full 0):
[0.103s][debug][gc,heap] GC(0)  garbage-first heap total reserved 65536K, committed 65536K, used 8304K
[0.103s][info ][gc,task] GC(0) Using 2 workers of 2 for full compaction
[0.103s][info ][gc,phases,start] GC(0) Phase 1: Mark live objects
[0.105s][info ][gc,phases] GC(0) Phase 1: Mark live objects 1.898ms
[0.105s][info ][gc,phases] GC(0) Phase 2: Prepare compaction 0.135ms
[0.105s][info ][gc,phases] GC(0) Phase 3: Adjust pointers 0.427ms
[0.106s][info ][gc,phases] GC(0) Phase 4: Compact heap 0.149ms
[0.106s][info ][gc,phases] GC(0) Phase 5: Reset Metadata 0.226ms
[0.106s][info ][gc,heap] GC(0) Eden regions: 7->0(14)
[0.106s][info ][gc,heap] GC(0) Survivor regions: 0->0(0)
[0.106s][info ][gc,heap] GC(0) Old regions: 2->3
[0.106s][info ][gc,heap] GC(0) Humongous regions: 2->2
[0.106s][debug][gc,heap] GC(0)  garbage-first heap total reserved 65536K, committed 65536K, used 3317K
[0.106s][info ][gc] GC(0) Pause Full (System.gc()) 9M->3M(64M) 4.042ms
[0.106s][info ][gc,cpu] GC(0) User=0.00s Sys=0.00s Real=0.00s
~~~

**Lưu ý về trích log:** Để dễ học, các dòng dài về địa chỉ heap, số ký tự padding của log tag, các thống kê metaspace và các đoạn debug khác đã được rút bớt; các giá trị chính như `8304K`, `3317K`, worker count, phases và pause summary được lấy từ thử nghiệm. Không dùng đoạn trích này thay thế log gốc khi phân tích production.

### 4.3. Những điều **không được** suy ra từ output lab

- `4.042ms` **không** là thời gian Full GC cố định của G1.
- `9M->3M` **không** nghĩa mọi lần gọi `System.gc()` đều thu hồi khoảng 6 MiB.
- `2 workers` **không** là giá trị mặc định ở mọi máy. Nó bị tác động bởi flag lab, kích thước heap, CPU/quota và heuristics.
- `GC(0)` chỉ là ID trong tiến trình thử nghiệm, không phải số lần Full GC trên mọi lần chạy của ứng dụng.
- `Using G1` xác định collector thực tế ở log này; **không** có nghĩa mọi Java runtime đều mặc định chọn G1 trong mọi hoàn cảnh.

## 5. Mổ xẻ dòng tổng kết GC: loại, cause, heap, thời gian

Xét:

~~~text
[0.106s][info][gc] GC(0) Pause Full (System.gc()) 9M->3M(64M) 4.042ms
~~~

| Phần log | Cách đọc đúng | Không nên hiểu là |
| --- | --- | --- |
| `0.106s` | JVM uptime tại thời điểm log được phát. | Thời lượng GC. |
| `info` | Mức logging. | Mức độ nghiêm trọng của pause. |
| `gc` | Tag log. | Tên thuật toán cụ thể. |
| `GC(0)` | ID liên kết những dòng cùng sự kiện GC. | Số thứ tự Full GC độc lập. |
| `Pause Full` | Đây là lần Full GC stop-the-world. | Young GC hay concurrent mark. |
| `System.gc()` | Cause JVM báo cho lần GC. | Bằng chứng heap chắc chắn đang thiếu. |
| `9M` | Heap used trước sự kiện (đã làm tròn theo log). | Sức chứa heap tối đa. |
| `3M` | Heap used sau sự kiện. | Tổng RAM của tiến trình. |
| `(64M)` | Heap capacity/size mà summary báo tại sự kiện. | Số byte đã cấp phát thành đối tượng sống. |
| `4.042ms` | GC pause duration được báo, đơn vị milliseconds. | Tổng CPU seconds của tất cả GC workers. |

### 5.1. Dạng tổng quát

~~~text
GC(<id>) <GC-type> (<cause>) <used-before>-><used-after>(<heap-capacity>) <duration-ms>ms
~~~

Đây là **mẫu điển hình**, không phải một grammar bất biến của mọi JDK/collector. Một số loại event có nhiều dấu ngoặc mô tả như `Pause Young (Normal) (G1 Evacuation Pause)`, nên parser không nên giả định chỉ đúng một cặp ngoặc.

### 5.2. ID `GC(0)` là chìa khóa nối log

Trong file `gc.log`, tìm `GC(0)` sẽ tập hợp:

- Dòng `gc,start` mô tả sự kiện bắt đầu.
- Dòng `gc,task` về GC workers.
- Dòng `gc,phases` về pha xử lý.
- Dòng `gc,heap` về mức sử dụng vùng heap.
- Dòng `gc` tổng kết before/after và duration.
- Dòng `gc,cpu` về thống kê thời gian CPU nếu được ghi.

**Không** ghép `GC(1)` vào `GC(0)` chỉ vì chúng cùng gần thời điểm. Khi có nhiều sự kiện GC, phải phân nhóm theo ID **trong cùng một JVM/log stream**; ID của những JVM khác nhau có thể trùng.

## 6. Cách đọc **nguyên nhân** Full GC: cause không phải chẩn đoán cuối cùng

Trong log:

~~~text
GC(0) Pause Full (System.gc())
~~~

Cause được báo là `System.gc()`. Đây là **lời yêu cầu thu gom tường minh** từ code, thư viện hoặc một cơ chế gọi tương đương. Nó có thể xuất hiện dù heap chưa gần hết.

Trong sự cố production, cần phân biệt những nhóm:

| Dấu hiệu | Giải thích hợp lý | Cần xem thêm |
| --- | --- | --- |
| `Pause Full (System.gc())` | Có yêu cầu GC tường minh và JVM xử lý thành Full GC trong cấu hình này. | Code, library, tool đã gọi; flags `DisableExplicitGC`, `ExplicitGCInvokesConcurrent`. |
| `Pause Full (G1 Compaction Pause)` | G1 phải đi đường Full GC compaction, thường dưới áp lực cấp phát/thu hồi. | Các GC ngay trước, evacuation failures, old/humongous occupancy. |
| `Evacuation Failure: Allocation` trước Full | G1 thiếu không gian cho một số thao tác evacuation. | Tỷ lệ cấp phát, live set, số old/humongous regions, marking progress. |
| `G1 Humongous Allocation` trong log | Cấp phát đối tượng lớn, có thể kích hoạt một số hoạt động G1. | Không tự kết luận dòng này **chính nó** là Full GC. |
| `Metadata GC Threshold` hoặc dấu hiệu metadata | Áp lực bộ nhớ metadata hoặc request thích hợp, tùy collector/JDK. | Metaspace/classloading, cause event cụ thể và các dòng kế cận. |
| `Pause Young (Normal) (G1 Evacuation Pause)` | Young GC thông thường. | **Không** đếm thành Full GC. |
| `Pause Young (Mixed)` | Mixed collection chọn thêm vùng old. | **Không** đồng nhất với Full GC. |

**Đọc đúng từ log thực tế:** Không phải mọi nguyên nhân đều được thể hiện bằng một nhãn giống nhau trên mọi JDK. Ví dụ `Pause Full (G1 Compaction Pause)` mô tả loại Full GC; lý do áp lực bộ nhớ thường phải suy từ **chuỗi sự kiện trước đó**, không được tự gán một “cause” duy nhất nếu log không có chứng cứ.

### 6.1. `System.gc()` không có nghĩa heap thiếu

Trong demo, với heap 64 MiB, chương trình chủ động gọi `System.gc()`. Một Full GC xuất hiện sau lời gọi đó không chứng minh heap đã chạm `-Xmx` hoặc sắp OOM.

Trong ứng dụng thật, lời gọi có thể đến từ:

- Code ứng dụng gọi tường minh.
- Thư viện hoặc framework.
- Công cụ ngoài JVM có quyền yêu cầu thu gom.
- Một thao tác giám sát/diagnostics.

Phải tìm **nguồn lời yêu cầu** trước khi tăng heap hoặc thay GC tuning.

### 6.2. Những cờ có thể thay đổi hành vi yêu cầu GC

Trên HotSpot/G1 hiện đại:

- `-XX:+DisableExplicitGC`: có thể cho JVM bỏ qua lời gọi `System.gc()`.
- `-XX:+ExplicitGCInvokesConcurrent`: có thể cho G1 khởi phát chu trình concurrent thay vì trực tiếp đi Full GC cho yêu cầu tường minh theo cấu hình.

Do đó, code gọi `System.gc()` **không cam kết** mọi JVM sẽ tạo log `Pause Full (System.gc())`. Demo được kiểm chứng trên JDK 24 với các flags đã nêu, không nên biến hành vi này thành hợp đồng của ngôn ngữ Java.

### 6.3. Nguyên nhân do thiếu bộ nhớ cần nhìn chuỗi sự kiện

Một Full GC dưới áp lực allocation thường có bối cảnh:

1. Heap occupancy ở old hoặc các vùng humongous cao.
2. Young/mixed GC chưa giải phóng đủ vùng.
3. Evacuation failure hoặc áp lực cấp phát kéo dài.
4. G1 phải dùng Full GC compact như biện pháp cuối.
5. Nếu sau Full GC live set vẫn quá lớn, ứng dụng có thể gặp lỗi cấp phát hoặc OOME.

**Không đảo ngược thành kết luận tuyệt đối:** thấy một Full GC không có nghĩa chắc chắn đã có `OutOfMemoryError`, và một `OutOfMemoryError` cũng không bảo đảm luôn có Full GC ngay trước đó trong mọi cấu hình.

## 7. Đọc **thời gian GC**: timestamp, pause duration và CPU time

Giả sử:

~~~text
[0.102s][info][gc,start] GC(0) Pause Full (System.gc())
...
[0.106s][info][gc] GC(0) Pause Full (System.gc()) 9M->3M(64M) 4.042ms
~~~

Ở log này:

- `0.102s` và `0.106s` là những mốc uptime khi log được viết.
- `4.042ms` là duration được JVM báo chính thức cho pause.
- Không lấy `0.106s - 0.102s = 4ms` rồi bảo đó là phép đo chính xác hơn `4.042ms` — hai uptime values được **làm tròn** tới độ chính xác của decorator.
- Khi một ứng dụng có nhiều Full GCs, cần xem **tần suất**, **max**, **p95/p99 pause** và **tổng thời gian STW** chứ không chỉ duration của một sự kiện.

### 7.1. `gc,cpu` khác `gc` summary

Dòng:

~~~text
[info][gc,cpu] GC(0) User=0.00s Sys=0.00s Real=0.00s
~~~

trên JDK 24 đã thử có ba trường:

| Trường | Ý nghĩa |
| --- | --- |
| `User` | CPU time ở user mode được ghi nhận trong phạm vi sự kiện. |
| `Sys` | CPU time ở kernel/system mode. |
| `Real` | Elapsed (wall-clock) time được tóm tắt cho thống kê CPU, thường in theo giây với độ chính xác hạn chế. |

Trong ví dụ, GC pause ~**4 ms**, nên `Real` được in `0.00s` do quy tắc làm tròn/định dạng. **Không được diễn giải `0.00s` là GC mất đúng 0 ms.**

Với nhiều workers song song, tổng **User CPU time** có thể lớn hơn **Real elapsed time**. Điều này không mâu thuẫn: nhiều worker chạy đồng thời có thể tiêu thụ CPU trên nhiều core. Tuy nhiên, **không dùng tỷ lệ User/Real như thước đo chính xác số workers** vì còn hệ điều hành, scheduler và độ chính xác log.

### 7.2. Phân biệt các pha và tổng pause

Các dòng từ demo:

~~~text
GC(0) Phase 1: Mark live objects 1.898ms
GC(0) Phase 2: Prepare compaction 0.135ms
GC(0) Phase 3: Adjust pointers 0.427ms
GC(0) Phase 4: Compact heap 0.149ms
GC(0) Phase 5: Reset Metadata 0.226ms
~~~

Các pha giúp xác định **bước nào tốn thời gian** trong Full GC. Trong ví dụ, **Mark live objects** chiếm một phần đáng kể của các pha được báo.

Nhưng **không được cộng tất cả số ms của mọi dòng phase rồi giả định phải bằng chính xác duration cuối**:

- Có chi phí tổ chức/đồng bộ workers và công việc ngoài các phase đang được in.
- Có log tổng cha/con, nếu cộng cả hai sẽ **đếm trùng**.
- Một số phase nội bộ có thể được chạy song song; thời gian từng worker không tương đương elapsed time.
- Phần trang trí thời gian và độ chính xác tùy cấp độ log/JDK.

Để phân tích pause, lấy **summary duration** làm nguồn tổng, còn **phase durations** để tìm điểm nóng (bottleneck) trong đúng JVM/collector version.

### 7.3. `MaxGCPauseMillis` không bảo đảm Full GC nằm dưới ngưỡng

G1 có mục tiêu pause `-XX:MaxGCPauseMillis` ở trạng thái thông thường. Đây là **mục tiêu mềm**, không phải hard real-time guarantee. Full GC là đường fallback STW nặng, có thể vượt mục tiêu đáng kể, đặc biệt khi live set lớn.

Không kết luận JVM lỗi chỉ vì Full GC pause lớn hơn giá trị target. Cần xem vì sao rơi vào Full GC và cách giảm khả năng kích hoạt nó.

## 8. Đọc **mức heap**: `usedBefore->usedAfter(capacity)`

Trong summary:

~~~text
9M->3M(64M)
~~~

nghĩa là:

- **Before:** mức dùng heap ngay trước lần GC, hiện thị khoảng 9 MiB.
- **After:** mức dùng heap sau lần GC, hiện thị khoảng 3 MiB.
- **Capacity:** kích thước heap được JVM báo trong sự kiện, khoảng 64 MiB.

Bảng tách riêng các đại lượng:

| Đại lượng | Trong log | Ý nghĩa |
| --- | --- | --- |
| `usedBefore` | `9M` | Byte heap đang dùng trước khi GC. |
| `usedAfter` | `3M` | Byte heap còn dùng sau khi GC. |
| `capacity` | `64M` | Kích thước heap trong summary tại thời điểm ấy. |
| `reclaimedApprox` | `9M - 3M ≈ 6M` | **Ước lượng** giảm mức used theo số đã làm tròn, không phải bộ đếm byte chính xác. |
| `freeAfterApprox` | `64M - 3M ≈ 61M` | Ước lượng free trong heap capacity được log, không phải tổng RAM OS còn trống. |

**Chú ý đơn vị:** Trên HotSpot GC log, hậu tố `K/M/G` theo quy ước dung lượng nhị phân thường tương ứng 1024 đơn vị cho mỗi bậc. Không được coi `9M` là một phép đo byte chính xác đến byte: log dạng tổng kết đã làm tròn.

### 8.1. Dùng `gc+heap=debug` để xem chi tiết hơn

Demo có:

~~~text
GC(0) ... reserved 65536K, committed 65536K, used 8304K
...
GC(0) ... reserved 65536K, committed 65536K, used 3317K
~~~

Đây là **snapshot heap** ở mức debug, mang độ chi tiết cao hơn summary `9M->3M(64M)`. Không nhầm các đại lượng:

- `reserved`: vùng địa chỉ ảo đã được dành trước cho heap.
- `committed`: dung lượng heap mà JVM cam kết để có thể sử dụng; không phải cứ committed là toàn bộ trang vật lý resident.
- `used`: phần heap đang được đánh dấu sử dụng theo accounting của runtime ở snapshot đó.
- `-Xmx`: mức tối đa được cấu hình, không luôn bằng capacity hiện tại.

Trong lab đặt `-Xms64m -Xmx64m`, nên reserved/committed/capacity cùng 64 MiB ở lần thử. Trên JVM có `-Xms` nhỏ hơn `-Xmx`, **capacity có thể tăng/giảm**, vì vậy đừng lấy con số trong ngoặc của một sự kiện làm “heap được cố định mãi mãi”.

### 8.2. Heap used giảm không đồng nghĩa live set giảm đúng bấy nhiêu đối tượng

Từ `9M->3M` chỉ có thể biết **mức heap used giảm**. Không có bằng chứng rằng:

- Chính xác 6 MiB Java objects đã bị thu hồi, tới từng byte.
- Mọi đối tượng ở vùng young đã chết.
- Không có đối tượng nào được di chuyển sang old region.
- 3 MiB còn lại là toàn bộ memory footprint của process.
- Ứng dụng không có memory leak.
- GC đã giải quyết vĩnh viễn áp lực heap.

Với một lỗi memory leak, sau Full GC `usedAfter` có thể tiếp tục tăng qua nhiều chu kỳ. Để kết luận, xem **xu hướng sau GC** cùng workload, heap dump/JFR, retention paths và số liệu phân bổ, không chỉ một dòng GC.

### 8.3. Heap không phải metaspace, native memory hay RSS

G1 log có thể kèm:

~~~text
GC(0) Metaspace: 122K(320K)->122K(320K)
~~~

Metaspace là bộ nhớ **metadata lớp** và không phải cùng đại lượng `9M->3M(64M)` của Java heap. Ngoài heap, JVM có stacks, code cache, direct buffers, native allocations và những vùng khác.

Trong container, memory usage của process/cgroup cũng không đơn giản bằng heap used. **Không** dùng dòng GC summary để khẳng định “container chỉ dùng 3 MiB RAM”.

## 9. Đọc G1 regions: Eden, Survivor, Old, Humongous

G1 chia heap thành **regions**, có các vai trò như Eden, Survivor, Old và Humongous. Với `-Xlog:gc+heap=info`, có thể thấy:

~~~text
GC(0) Eden regions: 7->0(14)
GC(0) Survivor regions: 0->0(0)
GC(0) Old regions: 2->3
GC(0) Humongous regions: 2->2
~~~

Cách đọc:

- `Eden regions: 7->0(14)`: số vùng Eden thay đổi từ 7 xuống 0; số trong ngoặc là **thông tin target/size** theo ngữ nghĩa của dòng log và JDK, không phải heap bytes.
- `Survivor regions: 0->0(0)`: số vùng Survivor theo thống kê đó không đổi.
- `Old regions: 2->3`: số vùng Old sau GC có thể tăng do **đối tượng sống được sắp xếp/chuyển vị trí**; không có mâu thuẫn khi **tổng heap used lại giảm**.
- `Humongous regions: 2->2`: số vùng được G1 dành cho các đối tượng lớn theo cơ chế humongous không đổi trong sự kiện.

**Không** đọc “Old regions 2->3” thành “old heap đã tăng đúng 1 MiB live data” nếu thiếu dữ liệu. Region count, số byte dùng và residency là các đại lượng khác nhau.

### 9.1. Humongous allocation có thể tăng áp lực

Đối tượng rất lớn trong G1 có thể được đặt trực tiếp trong một số vùng dành cho **humongous objects**. Điều này có thể gây áp lực lên những vùng lớn liền kề, đặc biệt trong các workload cấp phát mảng lớn.

Nếu log có Full GC liên quan áp lực allocation, hãy xem:

- `Humongous regions: X->Y`.
- `Old regions: X->Y`.
- Dòng `Evacuation Failure: Allocation` nếu có.
- Dòng GC trước đó và tình trạng concurrent marking.
- Heap region size thực tế, ví dụ dòng `Heap Region Size: 1M` trong lab.

**Không khuyến nghị thay `-XX:G1HeapRegionSize` ngay** chỉ vì thấy humongous regions. Hãy kiểm chứng allocation profile, heap sizing và tài liệu tuning của JDK hiện hành.

### 9.2. Region size không phải “mỗi object dùng nguyên một region”

Region là đơn vị quản lý của G1, không phải mỗi Java object đều chiếm đúng một region. Những vùng thông thường chứa nhiều đối tượng, trong khi humongous objects có quy tắc khác. Không nhân “số live objects × region size” để tính heap.

## 10. Xác minh **Full GC song song** từ nhật ký workers

Một dòng đặc biệt quan trọng của lab:

~~~text
GC(0) Using 2 workers of 2 for full compaction
~~~

Ý nghĩa:

- Sự kiện `GC(0)` đang sử dụng **hai worker** cho công việc full compaction.
- Đây là **G1 Full GC** theo dòng `Pause Full (System.gc())` cùng ID.
- Flag `-XX:ParallelGCThreads=2` trong lab góp phần giới hạn/định hình số worker.
- Việc dùng nhiều workers là một **đặc tính được JEP 307 phát triển từ Java 10** và vẫn liên quan trong JDK hiện đại.

**Không** suy ra rằng “số workers luôn bằng `ParallelGCThreads`”. JVM có thể dùng ít workers hơn mức tối đa tùy heap size, số CPU được nhìn thấy, quota và lượng việc. Dòng log **Using N workers of M** phản ánh lựa chọn thực tế của **sự kiện đó**.

### 10.1. Ba cờ/thông số rất dễ nhầm

| Tùy chọn | Vai trò | Không nên hiểu là |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn collector **G1**. | Bật một Full GC cụ thể. |
| `-XX:ParallelGCThreads=N` | Điều chỉnh số GC workers dùng cho các pause song song, theo heuristics. | Buộc mọi pause có đúng N threads hoặc đổi collector thành Parallel GC. |
| `-XX:ConcGCThreads=N` | Điều chỉnh số worker cho công việc GC **concurrent** (nếu hỗ trợ/áp dụng). | Thay thế `ParallelGCThreads` để điều khiển full compaction. |
| `-XX:+UseParallelGC` | Chọn **Parallel GC collector** khác. | Bật “G1 Parallel Full GC” trên G1. |

Nếu đang chẩn đoán Full GC của G1, cần biết **collector hiện dùng** và đọc `gc,task` cho **đúng GC ID**. Không so sánh worker count của Young GC với Full GC mà không phân biệt event.

### 10.2. Nhiều workers không bảo đảm throughput hoặc latency tốt hơn

- Tăng worker count có thể gây overhead đồng bộ.
- CPU quota trong container có thể nhỏ hơn số core trên host.
- Nếu live set thấp, nhiều workers có thể không tận dụng đủ.
- Full GC vẫn dừng application threads.
- Hiệu năng còn phụ thuộc layout heap, memory bandwidth, cache và tốc độ xử lý của JVM.

Chỉ thay worker flags khi có **benchmark và lý do rõ ràng**; đừng coi tăng `ParallelGCThreads` là “thuốc chữa” mọi Full GC dài.

## 11. Phân biệt Young/Mixed/Full/Concurrent trong một timeline

Một log G1 production có thể gồm nhiều loại sự kiện. Những chuỗi nhận diện thường gặp:

~~~text
Pause Young (Normal) (G1 Evacuation Pause)
Pause Young (Concurrent Start) ...
Concurrent Mark Cycle
Pause Young (Mixed) ...
Pause Full (G1 Compaction Pause)
Pause Full (System.gc())
~~~

**Không được đếm tất cả các dòng có chữ `Pause` là Full GC.** Một số G1 pauses liên quan Young/Mixed hoặc giai đoạn của chu trình marking, và đều có cấu trúc riêng.

| Loại | Tính chất chung | Quan tâm khi phân tích |
| --- | --- | --- |
| Young collection | STW pause cho young regions. | Tần suất, young size, allocation rate, pause ms. |
| Mixed collection | STW pause thu cả young và một số old regions. | Old occupancy, tiến trình reclaimed space. |
| Concurrent Mark Cycle | Có công việc concurrent với ứng dụng cùng các pause ngắn. | Marking có hoàn thành kịp trước áp lực heap không? |
| Full GC | STW xử lý/compact heap trên đường fallback hoặc yêu cầu tường minh. | Cause, trước/sau heap, duration, workers, sự kiện trước đó. |

**Quan trọng:** Không nên lập biểu đồ “Full GC rate” bằng cách tìm mỗi chuỗi `GC(`. Mỗi GC ID có thể sinh rất nhiều dòng; cần chọn **summary events** và **loại sự kiện**.

## 12. Đọc **heap pressure** từ một chuỗi GC, không từ một ảnh tĩnh

Một Full GC dài có thể xuất phát từ áp lực old generation hoặc mất khả năng evacuation. Cách điều tra đúng:

1. Tìm `Pause Full` summary và ghi **GC ID, cause, duration, usedBefore/After/capacity**.
2. Xem **5–10 sự kiện GC trước đó** (hoặc khoảng thời gian phù hợp) để biết heap có liên tục tăng và dọn không hiệu quả không.
3. Quan sát `usedAfter` ở các GC liên tiếp: live set có đang leo thang không?
4. Tìm cảnh báo `Evacuation Failure: Allocation`, các dòngเกี่ยว tới humongous regions và concurrent marking.
5. Kiểm tra `-Xmx`, container limits, allocation rate và workload vào thời điểm sự cố.
6. Đối chiếu application logs/APM: timeout, request backlog, retry storm hay batch lớn có cùng timestamp không?
7. Nếu cần, thu JFR/heap dump có kiểm soát và xem retention paths.

**Không** kết luận memory leak chỉ từ một Full GC. Memory leak cần bằng chứng về các đối tượng bị giữ không cần thiết qua thời gian; GC logs giúp nhận diện áp lực và xu hướng, nhưng không tự chỉ ra reference chain gây giữ đối tượng.

### 12.1. Đọc `usedAfter` qua nhiều GC

Giả sử ba lần GC cuối đều là Full GC và ghi:

~~~text
GC(101) Pause Full (...) 850M->700M(1024M) 310ms
GC(205) Pause Full (...) 910M->790M(1024M) 480ms
GC(308) Pause Full (...) 990M->920M(1024M) 720ms
~~~

**Đây là dữ liệu giả định để luyện phân tích, không phải log thực nghiệm của demo.**

Có thể rút ra:

- Mức `usedAfter` tăng 700→790→920 MiB trong chuỗi được quan sát.
- Mức pause cũng tăng trong ba sự kiện.
- Cần điều tra vì sao ngày càng nhiều heap còn sống sau Full GC: workload hợp lệ tăng, cache giữ đối tượng, hoặc memory leak.

**Không được tự kết luận** chỉ có leak hoặc chỉ do Full GC. Cần thêm thời gian, input và dữ liệu object retention.

### 12.2. Tình huống heap gần đầy nhưng GC giải phóng ít

Nếu `usedBefore≈usedAfter≈capacity` trong các Full GCs, phần lớn dung lượng có thể đang bị giữ bởi các đối tượng còn reachable hoặc GC không đủ điều kiện thu hồi. Hệ thống có thể tiếp tục gặp áp lực allocation/OOME.

Nhưng phải xác định **capacity đang thay đổi không**, collector, nguyên nhân Full GC và giới hạn container. Không dùng một tỉ lệ đơn lẻ để quyết định tăng heap hay sửa code.

## 13. Làm sao tìm đúng sự kiện trong log bằng lệnh shell?

Sau khi có `gc.log`:

Linux/macOS:

~~~bash
grep 'Pause Full' gc.log
grep 'full compaction' gc.log
grep 'GC(0)' gc.log
~~~

Windows PowerShell:

~~~powershell
Select-String -Path gc.log -Pattern 'Pause Full'
Select-String -Path gc.log -Pattern 'full compaction'
Select-String -Path gc.log -Pattern 'GC\(0\)'
~~~

**Chú ý:** Cú pháp PowerShell `-Pattern` dùng regex. Muốn tìm các dấu ngoặc của `GC(0)` như ký tự thường, cần escape thành `GC\(0\)` trong pattern; còn `grep` không dùng `-E` với pattern đơn giản có thể có quy tắc khác tùy grep flavor.

### 13.1. Tách summary và worker/phases bằng đúng GC ID

Một quy trình:

1. Tìm `Pause Full` để lấy **GC(n)**.
2. Lọc **GC(n)** để xem các dòng cùng sự kiện.
3. Tìm `Using N workers ... full compaction` trong nhóm.
4. Đọc các pha `Mark live objects`, `Prepare compaction`, `Adjust pointers`, `Compact heap`, `Reset Metadata`.
5. Đọc `gc+heap` trước và sau.
6. Ghi lại **cause, before/after/capacity, pause ms**.
7. Đối chiếu với các sự kiện khác theo timeline.

**Đừng** viết parser bằng cách lấy ngẫu nhiên chuỗi đầu tiên chứa `M->` mà chưa biết đó là GC nào và đang là summary hay region metric.

### 13.2. Khi định viết parser tự động

GC log có thể thay đổi định dạng giữa các bản JDK, các collector và log levels; tài liệu Oracle cũng lưu ý format chi tiết **không được cam kết bất biến**. Vì vậy:

- Lưu đầy đủ JDK vendor/version, collector và command line của tiến trình.
- Tách theo **GC ID** và tag/message type.
- Xử lý nhiều event với nhiều cặp ngoặc trong reason.
- Xác định rõ đơn vị `K/M/G` và làm tròn.
- Không ép mọi collector vào cùng regex.
- Dùng thư viện phân tích GC logs có hỗ trợ phiên bản JVM tương ứng khi cần production analytics.

Nếu chỉ cần xác minh thủ công, `grep` hoặc `Select-String` thường đủ; parser phức tạp không phải yêu cầu của bài học này.

## 14. Tổng hợp số liệu phục vụ báo cáo sự cố

Một bảng sự kiện hữu ích:

| Trường | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| `jvm_id`/PID | Tiến trình Java được phân tích. | text/ID |
| `event_id` | `GC(n)` trong JVM. | số |
| `time` | Uptime hoặc timestamp gắn vào sự kiện. | s/ISO time |
| `collector` | G1 hay collector khác. | text |
| `event_type` | Full / Young / Mixed / concurrent. | text |
| `cause` | Nhãn cause thực sự trong log. | text |
| `used_before` | Mức heap used trước sự kiện. | byte/MiB |
| `used_after` | Mức heap used sau sự kiện. | byte/MiB |
| `heap_capacity` | Sức chứa heap lúc sự kiện. | byte/MiB |
| `pause_ms` | Wall-clock pause duration. | ms |
| `workers` | GC workers báo dùng cho Full GC nếu có. | số |
| `notable_phases` | Pha tốn thời gian, theo log. | ms |
| `context` | Evacuation failure, humongous, marking, workload. | text |

**Không lấy GC IDs từ hai process khác nhau ghép thành một timeline duy nhất** mà thiếu PID/timestamp; `GC(0)` có thể có ở hàng nghìn JVM khác nhau.

### 14.1. Tính tỉ lệ giảm heap

Trong demo:

~~~text
before≈9 MiB
after≈3 MiB
reclaimed≈6 MiB
reclaimed_ratio≈(9-3)/9 ≈ 66.7%
~~~

Đây là **minh họa tính toán từ số hiển thị đã làm tròn**, không phải kết quả chính xác tới byte hoặc hiệu quả thực tế của GC. Với phân tích tự động, ưu tiên lấy dữ liệu có độ chính xác cao hơn nếu log cung cấp và giải thích rõ cách chuyển đơn vị.

Không đánh giá GC là “tốt” chỉ vì reclaimed ratio cao: việc thu hồi nhiều byte có thể vẫn mất quá lâu, còn usedAfter tăng có thể phù hợp với workload hiện tại.

### 14.2. Kết hợp pause duration và mức heap

Đối với incident review:

- **Duration dài + usedAfter thấp:** có thể dọn được nhiều nhưng pause ảnh hưởng latency; cần xem loại GC, cause và phases.
- **Duration dài + usedAfter gần capacity:** đáng lo về live set/pressure và khả năng tiếp tục allocation.
- **Full GC do `System.gc()` lặp lại:** ưu tiên xác định nguồn gọi tường minh; đừng tự kết luận thiếu heap.
- **Evacuation failures + Full GC dưới tải:** xem allocation pressure, humongous objects, marking không kịp và heap size.
- **Duration tăng cùng live set:** có thể làm Full GC nặng hơn, nhưng cần thêm dữ liệu để phân biệt tác động CPU/quota và cấu trúc heap.

## 15. Điều chỉnh G1: ưu tiên bằng chứng, không chạy theo một cờ

Oracle Garbage-First tuning guide khuyến nghị **bắt đầu từ cấu hình G1 mặc định**, thường chỉ cấu hình heap maximum `-Xmx` và mục tiêu pause nếu thật sự cần. Khi gặp nhiều Full GCs, đừng tăng hàng loạt mọi flags theo một danh sách trên mạng.

Hướng điều tra:

1. **Xác nhận cause:** System.gc hay áp lực allocation?
2. **Xem old/humongous occupancy** trước các Full GCs.
3. **Xem marking và mixed collection** có thu hồi đủ không.
4. **Xem allocation rate** và lượng object sống lâu.
5. **Kiểm tra giới hạn heap/container** — heap có đủ thời gian và không gian để hoàn thành concurrent marking?
6. **Đo lại** sau thay đổi code/workload hoặc cấu hình.

### 15.1. Với áp lực Full GC do cấp phát

Các hướng có thể đáng cân nhắc **sau khi có bằng chứng**:

- Giảm những đối tượng được giữ lâu ngoài nhu cầu.
- Giảm allocation rate, batch size hoặc vòng đời object tạm quá lớn.
- Xem lại các mảng lớn/humongous allocations.
- Tăng heap nếu dữ liệu live set và giới hạn RAM cho phép, để G1 có thêm thời gian marking.
- Kiểm tra tốc độ concurrent marking và chính sách kích hoạt marking sớm.
- Điều chỉnh mục tiêu pause trong phạm vi hợp lý, benchmark trên tải thực.

Không có một cấu hình chung cho mọi ứng dụng. Việc thay đổi `-XX:ParallelGCThreads`, `-XX:ConcGCThreads` hoặc `-XX:G1HeapRegionSize` cần lý do và dữ liệu, không phải phản ứng đầu tiên cho mỗi lần Full GC.

### 15.2. Với `System.gc()` lặp lại

- Tìm lớp/phần code hay công cụ phát yêu cầu.
- Bỏ lời gọi nếu không có lý do nghiệp vụ chính đáng.
- Nếu không sửa được source, đánh giá các cờ `DisableExplicitGC` hoặc `ExplicitGCInvokesConcurrent` trên HotSpot/G1 và kiểm thử tác động.
- Không khẳng định cờ nào “tốt nhất” khi thiếu thông tin về libraries có semantics hoặc resource management đặc thù.

### 15.3. Khi `OutOfMemoryError` xuất hiện

Dòng `Pause Full` không phải chứng cứ đầy đủ cho nguyên nhân OOME. Phải xác định loại lỗi: `Java heap space`, `Metaspace`, `Direct buffer memory`, `unable to create native thread` hoặc container OOM kill có bản chất khác nhau.

GC log giúp biết heap events; các lỗi liên quan native memory hoặc cgroup cần additional diagnostics. Không tăng `-Xmx` tùy tiện nếu container đang bị OOM kill do tổng RAM vượt giới hạn.

## 16. Những sai lầm khi đọc GC log

| Ngộ nhận | Vì sao sai | Cách đọc đúng |
| --- | --- | --- |
| `Pause Full` nghĩa là JVM đã hết heap. | Full GC có thể do `System.gc()` tường minh. | Đọc **cause** và sự kiện trước đó. |
| `System.gc()` luôn bắt buộc Full GC ở mọi JVM. | JVM/flags có thể bỏ qua hoặc chuyển sang concurrent. | Xem GC log thực tế của môi trường. |
| G1 Full GC song song nghĩa là application threads vẫn chạy. | **Parallel workers** khác **concurrent with app**. | Full GC là STW. |
| `-XX:+UseParallelGC` là cách bật parallel Full GC cho G1. | Flag này chọn một collector khác. | Dùng G1 và đọc `gc,task`; JEP 307 đã có từ Java 10. |
| `Using 2 workers` nghĩa mọi GC đều có đúng 2 threads. | Worker count phụ thuộc từng event và heuristics. | Đọc worker count cùng `GC(n)`. |
| `9M->3M(64M)` nghĩa “đã tiết kiệm chính xác 6 MiB RAM hệ thống”. | Đây là heap used đã làm tròn, không phải RSS. | Tách heap accounting với process/container memory. |
| `(64M)` luôn là `-Xmx`. | Heap capacity có thể tăng/giảm. | Đọc initial/max/committed/reserved riêng. |
| `4.042ms` là CPU time của một worker. | Là elapsed pause duration. | Xem `gc,cpu` khi cần CPU. |
| `Real=0.00s` nghĩa dừng 0 ms. | Log giây làm tròn; pause vài ms vẫn có thể in 0.00s. | Tin summary duration ms cho pause. |
| Cộng mọi phase time luôn bằng Full GC pause. | Có overhead/parent-child phase/parallel work. | Dùng summary tổng và phase để tìm bottleneck. |
| Có nhiều `GC(0)` nên đã có nhiều GC. | Một GC ID có thể xuất hiện ở nhiều dòng. | Nhóm theo ID trong **một JVM**. |
| `Eden regions 7->0` nghĩa 7 đối tượng bị xóa. | Region là đơn vị vùng bộ nhớ, không phải object. | Đọc region count đúng nghĩa. |
| `Old regions 2->3` chắc chắn memory leak. | Có thể do sắp xếp đối tượng sống. | Xem `usedAfter` và xu hướng qua nhiều lần. |
| G1 Mixed GC và Full GC tương đương. | Mixed chỉ chọn một số vùng old + young. | Phân loại đúng event_type. |
| Chỉ nhìn một dòng Full GC để kết luận heap leak. | Thiếu xu hướng retention và input. | Kết hợp nhiều GC, JFR/heap dump nếu cần. |
| Bật `-Xlog:gc*=debug` suốt đời ứng dụng không có chi phí. | Log có overhead, dữ liệu lớn. | Bật khi cần, rotation và bảo mật. |
| Chỉ cần GC pause log để chứng minh request latency. | Request có nhiều thành phần và lịch chạy. | Ghép APM, timestamp, PID và workload. |
| Full GC dài hơn `MaxGCPauseMillis` là lỗi JVM. | Mục tiêu pause là soft goal, Full GC fallback. | Điều tra trigger và giảm Full GC. |

## 17. Bài tập thực hành và đáp án

### Câu 1 — Giải mã summary

Cho:

~~~text
GC(7) Pause Full (System.gc()) 800M->500M(1024M) 120.5ms
~~~

**Đáp án:** GC ID 7; Full GC STW; cause JVM báo `System.gc()`; heap used khoảng 800 MiB trước và 500 MiB sau; heap capacity khoảng 1024 MiB; pause duration 120.5ms. Không được kết luận OOME hay đã thu hồi đúng 300 MiB physical RAM.

### Câu 2 — Vì sao 2 workers không phải Parallel GC collector?

~~~text
GC(7) Using 2 workers of 2 for full compaction
~~~

**Đáp án:** Đây là số workers thực hiện full compaction của một GC event. Nếu collector là **G1**, nó phản ánh cơ chế parallel Full GC của G1 (Java 10+); `UseParallelGC` là tên **collector khác**.

### Câu 3 — STW và parallel

G1 chạy Full GC với 8 workers. Application threads có tiếp tục chạy đồng thời không?

**Đáp án:** Không trong thời gian Full GC stop-the-world. 8 GC workers có thể làm một số công việc Full GC song song với nhau; không có nghĩa Java application threads tiếp tục chạy như khi G1 concurrent marking.

### Câu 4 — Uptime không phải duration

Một event có start log `[2.100s]` và summary `[2.109s] ... 8.713ms`. Nên báo pause duration nào?

**Đáp án:** **8.713ms** từ summary. Uptime được in với độ chính xác hạn chế; hiệu hai mốc in không nhất thiết chính xác bằng duration nội bộ.

### Câu 5 — `Real=0.00s`

Summary ghi pause `4.042ms` nhưng `gc,cpu` ghi `Real=0.00s`. Có mâu thuẫn không?

**Đáp án:** Không. CPU log in giây với độ chính xác làm tròn; vài ms có thể hiện `0.00s`. Dùng pause duration ms để đánh giá STW.

### Câu 6 — Used before/after

Log `900M->300M(1200M)` cho biết mức heap used sau GC còn bao nhiêu?

**Đáp án:** Khoảng **300 MiB** theo độ chính xác của log. `1200M` là capacity, không phải used. Không suy ra tổng RAM của container còn 900 MiB.

### Câu 7 — Old regions tăng

Sau Full GC, `Old regions: 2->3` nhưng `9M->3M`. Có mâu thuẫn không?

**Đáp án:** Không. Region counts và tổng heap bytes đo hai khía cạnh khác nhau; Full GC có thể sắp xếp lại những đối tượng sống trong old regions.

### Câu 8 — Khi nào xem `gc+task`?

Muốn xác nhận Full GC dùng mấy worker, cần log gì?

**Đáp án:** Bật `-Xlog:gc*` hoặc `-Xlog:gc+task=info` trong cấu hình phù hợp và tìm dòng `Using N workers ... full compaction` cho đúng `GC(n)`.

### Câu 9 — Khi nào xem `gc+phases`?

Pause tăng từ 100ms lên 500ms. Cần xác định pha nào tốn nhiều hơn.

**Đáp án:** Xem `gc+phases` cùng GC ID, chú ý các pha Mark/Prepare/Adjust/Compact; so với summary duration. Không cộng trùng parent-child phases.

### Câu 10 — Evacuation failure

Log có `Evacuation Failure: Allocation` rồi một `Pause Full (G1 Compaction Pause)`. Có thể nghi ngờ điều gì?

**Đáp án:** G1 gặp khó khăn khi di chuyển đối tượng do thiếu không gian phù hợp, sau đó phải Full GC. Cần xem old/humongous occupancy, marking, allocation rate và heap size; chưa thể quy kết memory leak từ hai dòng.

### Câu 11 — System.gc và thiếu heap

Lab có `Pause Full (System.gc())` trong heap 64 MiB. Có được khẳng định heap đã hết không?

**Đáp án:** Không. Đây là yêu cầu tường minh trong demo, không phải bằng chứng memory pressure. Phải nhìn heap used/capacity và source của yêu cầu.

### Câu 12 — Young GC khác Full GC

~~~text
GC(10) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

Có nên đếm vào Full GC count?

**Đáp án:** Không. Event type là Young; dù cũng STW pause, nó khác đường Full GC toàn heap.

### Câu 13 — So GC IDs

Trong một GC log có 10 dòng `GC(17)`, có nghĩa 10 lần GC?

**Đáp án:** Không. Thường đó là nhiều thông điệp cho **một** GC ID; phải nhóm đúng event và chỉ đếm summary GC events.

### Câu 14 — Memory leak hay workload tăng?

`usedAfter` của các Full GCs tăng 200→350→600 MiB trong vài phút. Có thể kết luận gì?

**Đáp án:** Đây là dấu hiệu tăng live set/retained heap cần điều tra. Chưa biết nguyên nhân là cache hợp lệ, workload tăng, reference retention không mong muốn hay leak. Cần thêm application context và heap analysis.

### Câu 15 — Log và container

GC log ghi `3M` after GC, nhưng container báo dùng 200 MiB. JVM sai không?

**Đáp án:** Không. Container memory bao gồm nhiều thành phần khác Java heap used, như metaspace, native buffers, stacks, code cache, JVM runtime và page cache theo accounting của OS.

### Câu 16 — `-XX:ParallelGCThreads`

Có nên tăng worker từ 2 lên 32 ngay khi một Full GC mất 100ms?

**Đáp án:** Không. Số workers hiệu quả phụ thuộc CPU quota, live set, overhead và heap. Phải xem worker count thực tế, phases, workload rồi benchmark trước/sau thay đổi.

## 18. Checklist khi đọc GC log của một sự cố

- [ ] Tôi biết đúng **JVM process**, JDK vendor/build, OS/container và collector đang chạy.
- [ ] Tôi xác minh collector thực tế là **G1**, không chỉ suy từ tên class hoặc flags tài liệu.
- [ ] Tôi phân loại **Pause Full**, Young, Mixed và concurrent events chính xác.
- [ ] Tôi lấy **GC ID** để nhóm dòng summary, workers, phases, heap và CPU của cùng event.
- [ ] Tôi đọc **cause** đúng như JVM báo, không tự đặt nguyên nhân thiếu heap khi chỉ có `System.gc()`.
- [ ] Tôi đọc **duration ms** từ summary thay vì chỉ lấy hiệu uptime đã làm tròn.
- [ ] Tôi không nhầm **User/Sys/Real CPU** với summary pause duration.
- [ ] Tôi hiểu `before->after(capacity)` là số liệu **Java heap**, không phải RSS/native memory.
- [ ] Tôi kiểm tra `reserved`, `committed`, `used` khi cần phân biệt heap sizing.
- [ ] Tôi không tự coi số trong ngoặc luôn bằng `-Xmx` nếu heap có thể resize.
- [ ] Tôi xem **Old/Humongous regions** và các evacuation failures khi điều tra áp lực Full GC.
- [ ] Tôi xác định số workers thực tế từ `gc+task` nếu đang đánh giá G1 Parallel Full GC.
- [ ] Tôi nhớ **parallel GC workers không biến Full GC thành concurrent với ứng dụng**.
- [ ] Tôi không cộng bừa mọi phase durations để suy total pause.
- [ ] Tôi xem **xu hướng nhiều GC** và application workload, không chỉ một lần Full GC.
- [ ] Tôi biết `MaxGCPauseMillis` là mục tiêu mềm, Full GC có thể vượt ngưỡng.
- [ ] Tôi không dùng `System.gc()` trong production như giải pháp thường trực cho memory pressure.
- [ ] Tôi dùng `-Xlog` hiện đại và giới hạn mức debug/rotation phù hợp.
- [ ] Tôi không dựa vào một log GC để kết luận memory leak, OOME hoặc số RAM container chính xác.
- [ ] Tôi đánh giá hiệu quả tuning bằng benchmark đa lượt và chỉ thay flags có lý do.
- [ ] Tôi ghi rõ những con số nào là **thực nghiệm trên JDK 24** và những ví dụ nào **giả định**.

## 19. Tài liệu chính thức vẫn còn áp dụng

1. [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): cải tiến đường Full GC của G1 bằng xử lý song song từ Java 10.
2. [Oracle Java SE 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): ví dụ log `Pause Full (System.gc())`, ý nghĩa `usedBefore->usedAfter(capacity)`, duration, các GC phases và Unified Logging.
3. [Oracle Java SE 25 — Garbage-First Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): hoạt động của G1, Young/Mixed/Full, concurrent marking, humongous regions và workers.
4. [Oracle Java SE 25 — Garbage-First GC Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): Full GC, evacuation failure, memory pressure, humongous allocations, `System.gc()`, `DisableExplicitGC`, `ExplicitGCInvokesConcurrent` và hướng chẩn đoán.
5. [Oracle Java SE 25 — java launcher: Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): `-Xlog`, selectors, wildcard, levels, decorators và file rotation.
6. [Oracle Java SE 25 — java launcher: GC logging flags](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#convert-gc-logging-flags-to-xlog): chuyển từ cờ legacy sang `-Xlog` trong HotSpot hiện đại.
7. [Oracle Java SE 25 — java launcher: -XX:ParallelGCThreads](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cấu hình số workers cho hoạt động GC song song, phân biệt với tên collector `UseParallelGC`.
8. [OpenJDK JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271): cơ sở cho hệ thống nhật ký GC dựa trên Unified Logging.

**Kết luận:** Khi phân tích **G1 Parallel Full GC** (Java 10+), bắt đầu với một dòng `Pause Full` để ghi rõ **cause, pause ms và heap before→after(capacity)**. Sau đó dùng **GC ID** nối các dòng `gc+task` để xác minh số workers, `gc+phases` để tìm pha tốn thời gian, `gc+heap` để xem các vùng và snapshot heap, `gc+cpu` để hiểu CPU vs elapsed time. Full GC vẫn **STW** dù có nhiều GC workers. Một log `Pause Full (System.gc())` không tự chứng minh heap thiếu, và số `9M->3M(64M)` không phải phép đo chính xác RAM container hay memory leak. Kết luận chỉ nên được rút ra sau khi đối chiếu **chuỗi sự kiện GC**, workload và số liệu ứng dụng thực tế.