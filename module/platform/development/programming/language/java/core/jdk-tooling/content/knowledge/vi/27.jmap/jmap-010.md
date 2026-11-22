# jmap và jcmd trong chẩn đoán bộ nhớ Java

**`jmap`** và **`jcmd`** là hai công cụ dòng lệnh của JDK giúp kiểm tra một Java Virtual Machine (JVM) đang chạy. Cả hai có thể hỗ trợ phân tích heap, thống kê object và tạo heap dump. `jcmd` còn cung cấp một hệ thống diagnostic command rộng hơn, bao gồm thread dump, VM flags, classloader, Java Flight Recorder (JFR) và native memory.

Trong quy trình mới, nên ưu tiên **`jcmd`** vì đây là giao diện chẩn đoán được Oracle khuyến nghị. `jmap` vẫn hữu ích khi làm việc với lệnh cũ hoặc cần cú pháp chuyên biệt cho heap histogram/heap dump, nhưng tài liệu JDK đánh dấu công cụ này là experimental và unsupported.

## 1. Vai trò của jmap và jcmd

Hai công cụ đều kết nối tới một JVM cục bộ đang chạy để thu thập dữ liệu chẩn đoán.

**`jmap`** tập trung vào thông tin bộ nhớ và heap:

- Thống kê số lượng object và dung lượng theo class.
- Tạo heap dump ở định dạng HPROF.
- Xem thống kê classloader.
- Xem object đang chờ finalization trên các JDK còn hỗ trợ command này.

**`jcmd`** gửi diagnostic command tới JVM đích. Nhóm command rộng hơn:

- Heap: `GC.heap_info`, `GC.class_histogram`, `GC.heap_dump`.
- Classloader: `VM.classloader_stats`, `VM.classes`.
- Thread: `Thread.print`.
- JVM: `VM.flags`, `VM.command_line`, `VM.system_properties`, `VM.info`.
- JFR: `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- Native memory: `VM.native_memory` khi Native Memory Tracking đã được bật.

Cả hai công cụ đều có thể tạo ra thao tác tốn tài nguyên. Heap histogram và heap dump có thể làm JVM tạm dừng, chạy GC hoặc sử dụng nhiều CPU và I/O. Chọn lệnh theo câu hỏi chẩn đoán cụ thể và đọc mức Impact trước khi chạy.

## 2. So sánh nhanh jmap và jcmd

| Tiêu chí | `jmap` | `jcmd` |
| --- | --- | --- |
| Phạm vi | Chủ yếu heap và classloader | Heap, GC, thread, JFR, VM flags, classloader, native memory và nhiều nhóm khác |
| Chọn tiến trình | PID | PID hoặc main class; có thể liệt kê JVM |
| Liệt kê JVM | Không có chế độ `-l` tương đương | `jcmd -l` |
| Heap histogram | `jmap -histo` | `GC.class_histogram` |
| Heap dump | `jmap -dump` | `GC.heap_dump` |
| Classloader stats | `jmap -clstats` | `VM.classloader_stats` |
| Thread dump | Không phải chức năng chính | `Thread.print` |
| JFR | Không | `JFR.start/check/dump/stop` |
| Native memory | Không phải chức năng chính | `VM.native_memory` |
| Hướng sử dụng | Hữu ích cho thao tác heap truyền thống | Ưu tiên cho quy trình chẩn đoán hiện đại |

Oracle đánh dấu `jmap` là experimental/unsupported và khuyến nghị `jcmd` cho chẩn đoán JVM. Các command cụ thể vẫn phụ thuộc phiên bản JDK, JVM vendor và trạng thái process.

## 3. Kiểm tra phiên bản và trợ giúp

Dùng công cụ từ cùng JDK hoặc JDK tương thích với JVM đích. Kiểm tra phiên bản:

```bash
java -version
jmap -h
jcmd -h
```

Trợ giúp `jmap` hiển thị các nhóm lệnh chính:

```text
jmap -clstats <pid>
jmap -finalizerinfo <pid>
jmap -histo[:[<histo-options>]] <pid>
jmap -dump:<dump-options> <pid>
```

Trợ giúp `jcmd` cho biết cú pháp tổng quát:

```text
jcmd <pid | main class> <command ...>
jcmd -l
jcmd -h
```

`jcmd` không có một danh sách command cố định áp dụng cho mọi JVM. Hãy hỏi chính JVM đích:

```bash
jcmd 18420 help
jcmd 18420 help GC.heap_info
jcmd 18420 help GC.class_histogram
jcmd 18420 help GC.heap_dump
```

Lệnh `help <command>` còn cung cấp cú pháp, tùy chọn và thông tin Impact của command. Đây là bước cần làm trước khi chạy một lệnh có thể tác động mạnh đến production.

## 4. Tìm đúng JVM cần chẩn đoán

Dùng `jcmd -l` để liệt kê JVM mà tài khoản hiện tại có thể quan sát:

```bash
jcmd -l
```

Output minh họa:

```text
18420 com.example.app.Main
29116 org.apache.catalina.startup.Bootstrap
```

`jmap` thường nhận PID:

```bash
jmap -histo:live 18420
```

`jcmd` nhận PID hoặc tên main class:

```bash
jcmd 18420 VM.uptime
jcmd com.example.app.Main VM.uptime
```

Ưu tiên PID khi có nhiều instance cùng chạy một main class. PID trong ví dụ chỉ minh họa; hãy lấy PID mới từ môi trường thực tế.

Có thể dùng target `0` với `jcmd` để gửi command đến tất cả JVM được phát hiện. Không dùng cách này trong thao tác thông thường vì command có thể ảnh hưởng nhiều ứng dụng cùng lúc.

Attach phụ thuộc user, quyền hệ điều hành, PID namespace và cấu hình JVM. Với Docker/Kubernetes, có thể cần chạy công cụ trong cùng container hoặc PID namespace với tiến trình đích.

## 5. Xem tổng quan Java heap

`jcmd GC.heap_info` cung cấp thông tin tổng quan về heap và một số vùng nhớ liên quan:

```bash
jcmd 18420 GC.heap_info
```

Output minh họa với G1:

```text
18420:
 garbage-first heap   total reserved 30932992K, committed 2113536K, used 23419K
 region size 16384K, 2 young (32768K), 0 survivors (0K)
 Metaspace       used 1349K, committed 1536K, reserved 1114112K
 class space    used 85K, committed 192K, reserved 1048576K
```

Ý nghĩa:

- **Reserved:** vùng địa chỉ JVM đã dành trước.
- **Committed:** phần bộ nhớ đã commit để JVM sử dụng.
- **Used:** phần đang được sử dụng theo thống kê của collector.
- **Metaspace:** vùng native memory lưu metadata của class.
- **Class space:** vùng dành cho compressed class pointers khi JVM dùng cơ chế này.

Các con số và cách trình bày phụ thuộc collector, phiên bản JVM và trạng thái ứng dụng.

`GC.heap_info` hữu ích để xem nhanh heap đang dùng bao nhiêu. Nó không cho biết object nào đang giữ bộ nhớ và không thay thế heap dump hoặc histogram.

## 6. Tạo class histogram bằng jmap

Class histogram thống kê số instance và dung lượng object theo class. Dùng `jmap`:

```bash
jmap -histo 18420
```

Theo trợ giúp JDK 24, nếu không chỉ định `live` hoặc `all`, `jmap -histo` mặc định thống kê tất cả object trong heap.

Chỉ thống kê live object:

```bash
jmap -histo:live 18420
```

Chỉ định rõ tất cả object:

```bash
jmap -histo:all 18420
```

Lưu histogram ra file:

```bash
jmap -histo:live,file=histogram.txt 18420
```

Có thể điều chỉnh số thread dùng khi kiểm tra heap:

```bash
jmap -histo:live,parallel=1 18420
```

Output minh họa:

```text
 num     #instances         #bytes  class name
-------------------------------------------------------
   1:          8769        8861376  [B
   2:          1858         229248  java.lang.Class
   3:          8680         208320  java.lang.String
   4:          1326         152624  [Ljava.lang.Object;
```

Cách đọc:

- `#instances`: số lượng instance của class.
- `#bytes`: tổng shallow size ước tính của các instance.
- `class name`: tên class hoặc dạng mảng; `[B` là byte array, `[I` là int array.

Histogram không cho biết retained size của object graph. Một class có tổng shallow size lớn chưa chắc là nguyên nhân gốc của memory leak. Muốn tìm object đang được giữ bởi reference nào, cần phân tích heap dump bằng công cụ như Eclipse Memory Analyzer (MAT).

Histogram live-only có thể yêu cầu GC để xác định object còn sống và làm ứng dụng tạm dừng. Đọc mức Impact của command và tránh chạy liên tục trong giờ cao điểm.

## 7. Tạo class histogram bằng jcmd

Command tương ứng trong `jcmd` là `GC.class_histogram`:

```bash
jcmd 18420 GC.class_histogram
```

Trong JDK 24 được kiểm tra, command có các tùy chọn:

- `-all`: bao gồm cả object unreachable; mặc định là `false`.
- `-parallel`: số thread song song dùng để kiểm tra heap.

Ví dụ chỉ định bao gồm cả object unreachable:

```bash
jcmd 18420 GC.class_histogram -all
```

Giảm mức song song:

```bash
jcmd 18420 GC.class_histogram -parallel=1
```

Trên JDK 24, trợ giúp của command ghi **Impact: High**, phụ thuộc kích thước và nội dung heap. Không chạy histogram liên tục trên JVM lớn nếu chưa đánh giá pause và CPU.

### Khác biệt mặc định cần nhớ

| Lệnh | Mặc định | Cách yêu cầu tất cả object |
| --- | --- | --- |
| `jmap -histo` | All objects | `jmap -histo:all` |
| `jmap -histo:live` | Live objects | Không cần thêm |
| `jcmd GC.class_histogram` | Chỉ live/reachable objects theo mặc định command | `jcmd PID GC.class_histogram -all` |

Khi so sánh kết quả hai công cụ, phải chọn cùng phạm vi object. Nếu một lệnh đếm all objects và lệnh kia chỉ đếm live objects, số instance và bytes có thể khác nhau dù cùng một JVM.

## 8. Tạo heap dump bằng jmap

Heap dump là bản ghi object graph trong heap, thường dùng định dạng HPROF. Dùng `jmap`:

```bash
jmap -dump:live,format=b,file=/var/tmp/heap-live.hprof 18420
```

Ý nghĩa:

- `-dump`: tạo heap dump.
- `live`: chỉ dump live objects.
- `format=b`: định dạng binary.
- `file=...`: đường dẫn file đầu ra.
- `18420`: PID JVM.

Dump tất cả object:

```bash
jmap -dump:all,format=b,file=/var/tmp/heap-all.hprof 18420
```

Trợ giúp JDK 24 còn hỗ trợ gzip compression:

```bash
jmap -dump:live,format=b,gz=1,file=/var/tmp/heap-live.hprof.gz 18420
```

Mức nén từ 1 đến 9; 1 ưu tiên tốc độ, 9 ưu tiên nén mạnh hơn.

Tùy chọn `live` và `all` xác định phạm vi object. Theo trợ giúp, `live` được ưu tiên nếu cả hai cùng xuất hiện; nếu không chỉ định, `jmap` mặc định dump all objects.

Heap dump có thể rất lớn, cần nhiều disk I/O và có thể gây pause đáng kể. Kiểm tra dung lượng ổ đĩa, quyền ghi và tác động đến workload trước khi thực hiện.

## 9. Tạo heap dump bằng jcmd

Command tương ứng trong `jcmd` là `GC.heap_dump`:

```bash
jcmd 18420 GC.heap_dump /var/tmp/heap-live-jcmd.hprof
```

Trong JDK 24, command mặc định yêu cầu full GC trước khi dump. Có thể chỉ định `-all` để bao gồm cả object unreachable và không yêu cầu full GC theo hành vi mặc định đó:

```bash
jcmd 18420 GC.heap_dump -all /var/tmp/heap-all-jcmd.hprof
```

Có thể dùng gzip:

```bash
jcmd 18420 GC.heap_dump -gz=1 /var/tmp/heap-live-jcmd.hprof.gz
```

Các tùy chọn cụ thể phụ thuộc JDK; kiểm tra:

```bash
jcmd 18420 help GC.heap_dump
```

### Lưu ý về đường dẫn file

`jcmd` phân tích phần command và arguments của diagnostic command. Dùng đường dẫn đơn giản, không có khoảng trắng để tránh bị tách thành nhiều arguments ngoài ý muốn:

Windows:

```powershell
New-Item -ItemType Directory -Force C:\\diagnostics | Out-Null
jcmd 18420 GC.heap_dump C:\\diagnostics\\heap-live.hprof
```

macOS/Linux:

```bash
mkdir -p /var/tmp/diagnostics
jcmd 18420 GC.heap_dump /var/tmp/diagnostics/heap-live.hprof
```

Đừng ghi dump vào thư mục dùng chung hoặc thư mục có quyền truy cập rộng. HPROF có thể chứa token, session, dữ liệu người dùng, nội dung request và các object nhạy cảm khác.

## 10. So sánh live objects và all objects

Hai chế độ có mục đích khác nhau:

**Live objects** là các object còn reachable theo quy tắc GC tại thời điểm kiểm tra. Đây thường là phạm vi phù hợp khi tìm object đang được ứng dụng giữ lại.

**All objects** bao gồm cả object unreachable nhưng chưa được thu gom. Phạm vi này có thể hữu ích khi cần nghiên cứu trạng thái heap đầy đủ hơn, nhưng số liệu không tương đương với bộ nhớ ứng dụng đang giữ sống.

Ví dụ:

```bash
jmap -histo:live 18420
jmap -histo:all 18420

jcmd 18420 GC.class_histogram
jcmd 18420 GC.class_histogram -all
```

Khi tạo heap dump:

```bash
jmap -dump:live,format=b,file=/var/tmp/live.hprof 18420
jmap -dump:all,format=b,file=/var/tmp/all.hprof 18420

jcmd 18420 GC.heap_dump /var/tmp/live-jcmd.hprof
jcmd 18420 GC.heap_dump -all /var/tmp/all-jcmd.hprof
```

Nếu mục tiêu là tìm memory leak, thường bắt đầu với live object histogram và heap dump. Sau đó dùng MAT để tìm dominator tree, retained size và GC roots.

## 11. Xem classloader statistics

Classloader statistics hữu ích khi điều tra:

- Metaspace tăng bất thường.
- Ứng dụng tạo nhiều classloader.
- Redeploy nhiều lần nhưng classloader cũ không được giải phóng.
- Framework/plugin nạp class động.
- Classloader leak.

Dùng `jmap`:

```bash
jmap -clstats 18420
```

Dùng `jcmd`:

```bash
jcmd 18420 VM.classloader_stats
```

Output có thể bao gồm classloader, parent, số class đã nạp và thống kê metaspace chunks/blocks.

Ví dụ output rút gọn:

```text
ClassLoader         Parent              CLD*               Classes   ChunkSz   BlockSz  Type
0x...               0x...               0x...               1185      4456448   1360928  <boot class loader>
0x...               0x...               0x...                  1         6144      2560  jdk.internal.loader.ClassLoaders$AppClassLoader
Total = 2
```

Cách trình bày phụ thuộc JDK. Số class hoặc dung lượng lớn không tự chứng minh leak; hãy so sánh theo thời gian và sau các chu kỳ deploy/undeploy.

## 12. Các command jcmd bổ sung ngoài phạm vi jmap

`jcmd` có thể làm nhiều việc hơn heap inspection.

### Thread dump

```bash
jcmd 18420 Thread.print -l
```

In stack trace của thread và thêm thông tin lock. Hữu ích khi điều tra deadlock hoặc thread contention.

### JVM flags và command line

```bash
jcmd 18420 VM.flags -all
jcmd 18420 VM.command_line
jcmd 18420 VM.system_properties
```

Dùng để kiểm tra cấu hình runtime, startup arguments và system properties. Output có thể chứa đường dẫn, endpoint hoặc bí mật nếu ứng dụng đặt thông tin nhạy cảm trong command line/property; lọc trước khi chia sẻ.

### Java Flight Recorder

Bắt đầu recording:

```bash
jcmd 18420 JFR.start name=incident settings=default duration=60s filename=/var/tmp/incident.jfr
```

Kiểm tra:

```bash
jcmd 18420 JFR.check name=incident
```

Xuất snapshot:

```bash
jcmd 18420 JFR.dump name=incident filename=/var/tmp/incident-snapshot.jfr
```

Dừng recording:

```bash
jcmd 18420 JFR.stop name=incident filename=/var/tmp/incident-final.jfr
```

`default` được thiết kế cho recording có overhead thấp hơn; `profile` thu thập nhiều dữ liệu hơn nhưng có overhead cao hơn. Chỉ dùng profile trong khoảng thời gian ngắn khi cần phân tích sâu.

### Native Memory Tracking

Nếu NMT được bật từ lúc JVM khởi động:

```bash
jcmd 18420 VM.native_memory summary
```

Có thể đặt baseline và so sánh:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

NMT không phải thống kê Java heap. Nó giúp xem native memory cho metaspace, thread, code cache, GC và các subsystem khác. Nếu JVM không bật NMT lúc khởi động, không thể bật đầy đủ hồi tố cho tiến trình đang chạy.

## 13. Phân tích heap dump bằng công cụ chuyên dụng

Heap dump là dữ liệu thô; cần công cụ phân tích để hiểu object graph.

Các công cụ thường dùng:

- **Eclipse Memory Analyzer (MAT):** mở HPROF, tìm leak suspects, dominator tree, retained size, GC roots và đường tham chiếu.
- **Java Mission Control (JMC):** phân tích JFR recording và dữ liệu runtime.
- **Công cụ HPROF khác:** có thể dùng để kiểm tra class histogram hoặc object references tùy khả năng hỗ trợ.

Một quy trình với MAT:

1. Mở file `.hprof`.
2. Chạy Leak Suspects Report để có gợi ý ban đầu.
3. Xem Histogram để tìm class có nhiều instance hoặc shallow size lớn.
4. Xem Dominator Tree để tìm object giữ nhiều memory.
5. Kiểm tra Path to GC Roots để biết vì sao object còn reachable.
6. Đối chiếu với source code, thread, cache và lifecycle của ứng dụng.
7. Lặp lại dump sau khi thay đổi để xác minh xu hướng.

Không kết luận memory leak chỉ từ một class có số instance lớn. Một cache hợp lệ cũng có thể giữ nhiều object; cần xác định object có đáng lẽ được giải phóng hay không.

## 14. Ví dụ thực hành Java 17: tạo heap có object được giữ lại

Ví dụ sau tạo một ứng dụng giữ một số byte array trong static list để histogram và heap dump có dữ liệu dễ nhận diện.

Cấu trúc:

```text
project/
  src/
    com/example/diagnostics/
      HeapTarget.java
  out/
```

Tệp **`src/com/example/diagnostics/HeapTarget.java`**:

```java
package com.example.diagnostics;

import java.util.ArrayList;
import java.util.List;

public final class HeapTarget {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private HeapTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Retained arrays=" + RETAINED.size());

        Thread.sleep(120_000);
    }
}
```

Biên dịch bằng Java 17:

```bash
javac --release 17 -d out src/com/example/diagnostics/HeapTarget.java
```

Chạy:

```bash
java -cp out com.example.diagnostics.HeapTarget
```

Output có dạng:

```text
PID=18420
Retained arrays=8
```

PID thay đổi theo lần chạy. Mảng byte được giữ trong static list nên vẫn reachable trong thời gian chương trình hoạt động.

Mở terminal thứ hai và tìm JVM:

```bash
jcmd -l
```

Giả sử PID là `18420`, xem heap:

```bash
jcmd 18420 GC.heap_info
```

Xem histogram bằng cả hai công cụ:

```bash
jmap -histo:live 18420
jcmd 18420 GC.class_histogram
```

Tạo heap dump:

```bash
jmap -dump:live,format=b,file=/var/tmp/heap-jmap.hprof 18420
jcmd 18420 GC.heap_dump /var/tmp/heap-jcmd.hprof
```

Mở một trong hai file HPROF bằng MAT để tìm các byte array và đường tham chiếu từ static field `RETAINED`.

Dừng chương trình bằng Ctrl+C ở terminal chạy `HeapTarget`. Ví dụ này là workload nhỏ để thực hành, không phải benchmark và không đại diện cho heap của ứng dụng production.

## 15. Mức tác động và an toàn vận hành

Trong JDK 24 được kiểm tra trên JVM thử nghiệm:

| Command | Impact theo trợ giúp JVM |
| --- | --- |
| `GC.heap_info` | Medium |
| `GC.class_histogram` | High, phụ thuộc heap size và content |
| `GC.heap_dump` | High, phụ thuộc heap size và content |
| `VM.classloader_stats` | Low |
| `VM.native_memory` | Medium |
| `JFR.start` | Medium; phụ thuộc settings, có thể từ low đến high |

Mức Impact có thể khác giữa JDK/vendor. Luôn dùng `jcmd <pid> help <command>` trên JVM đích.

Thực hành an toàn:

- Bắt đầu bằng `GC.heap_info` và thống kê nhẹ hơn trước khi dump.
- Không chạy histogram hoặc heap dump lặp lại không cần thiết.
- Dự trù dung lượng ổ đĩa và thời gian pause.
- Không dump heap vào ổ đĩa gần đầy.
- Bảo vệ file HPROF/JFR vì chúng có thể chứa dữ liệu ứng dụng nhạy cảm.
- Giới hạn quyền đọc và mã hóa khi lưu/truyền theo chính sách.
- Ghi lại PID, thời điểm, JDK version và command đã chạy.
- Không dùng `jcmd 0` trừ khi có chủ đích tác động đến mọi JVM được phát hiện.
- Dừng JFR recording khi đã thu thập đủ dữ liệu.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy JVM | Sai user, khác container/PID namespace hoặc process đã dừng | Chạy `jcmd -l` trong đúng môi trường |
| `AttachNotSupportedException` hoặc Access denied | Thiếu quyền attach hoặc attach mechanism bị tắt | Kiểm tra user, PID, JVM options và policy |
| Unknown diagnostic command | JVM đích không hỗ trợ command hoặc sai tên | Dùng `jcmd <pid> help` |
| Histogram chậm hoặc làm ứng dụng pause | Heap lớn, nhiều object hoặc command Impact High | Giảm tần suất, chọn thời điểm phù hợp |
| Heap dump không ghi được | Thiếu quyền, thư mục không tồn tại hoặc hết disk | Kiểm tra thư mục, quyền và dung lượng |
| JDK báo file argument bị tách | Đường dẫn `jcmd` chứa khoảng trắng và parser tách thành nhiều arguments | Dùng đường dẫn không có khoảng trắng, kiểm tra quoting theo JDK |
| HPROF quá lớn | Heap lớn hoặc dump all objects | Chọn live-only khi phù hợp, nén hoặc tăng dung lượng |
| Không thấy NMT summary | JVM chưa bật Native Memory Tracking lúc khởi động | Bật `-XX:NativeMemoryTracking=summary` trong lần restart tiếp theo |
| Histogram khác nhau giữa jmap và jcmd | Hai lệnh dùng live/all object scope khác nhau hoặc heap đã thay đổi | So sánh cùng scope và cùng thời điểm gần nhau |
| Không tìm được nguyên nhân leak từ histogram | Histogram chỉ cho shallow size, không có đường giữ object | Mở HPROF bằng MAT và xem dominator/GC roots |

## 17. Quy trình chọn công cụ

Chọn command theo câu hỏi cần trả lời:

| Câu hỏi | Công cụ/lệnh nên bắt đầu |
| --- | --- |
| Heap đang dùng bao nhiêu? | `jcmd PID GC.heap_info` |
| Class nào có nhiều instance? | `jcmd PID GC.class_histogram` |
| Cần thống kê theo cú pháp jmap truyền thống? | `jmap -histo:live PID` |
| Cần tìm object đang được giữ lại? | `jcmd PID GC.heap_dump` rồi phân tích bằng MAT |
| Cần classloader/metaspace statistics? | `jcmd PID VM.classloader_stats` |
| Thread nào đang chờ lock? | `jcmd PID Thread.print -l` |
| Cần ghi nhận hiệu năng theo thời gian? | `jcmd PID JFR.start ...` |
| Native memory tăng bất thường? | `jcmd PID VM.native_memory summary` nếu NMT đã bật |
| Cần xem VM flags và startup configuration? | `jcmd PID VM.flags -all` và `VM.command_line` |

Một quy trình chẩn đoán bộ nhớ thường bắt đầu bằng `jcmd -l`, sau đó `GC.heap_info`, rồi `GC.class_histogram`. Chỉ tạo heap dump khi histogram và metrics cho thấy cần phân tích object graph sâu hơn.

## 18. Ghi nhớ

- `jmap` chủ yếu phục vụ heap histogram, heap dump và classloader statistics.
- `jcmd` có phạm vi rộng hơn và là lựa chọn được Oracle khuyến nghị cho chẩn đoán JVM hiện đại.
- `jmap -histo:live` và `jcmd GC.class_histogram` có thể cho phạm vi live object; kiểm tra `-all` khi cần tính cả unreachable objects.
- Mặc định all/live của hai công cụ không giống nhau; phải so sánh cùng phạm vi.
- `jmap -dump` và `jcmd GC.heap_dump` tạo HPROF để phân tích bằng MAT.
- `jcmd GC.heap_dump` mặc định yêu cầu full GC; tùy chọn `-all` thay đổi phạm vi và hành vi đó trên JDK được kiểm tra.
- `jcmd` còn hỗ trợ JFR, thread dump, VM flags, classloader và native memory diagnostics.
- Histogram cho shallow size; heap dump/MAT giúp phân tích retained size và GC roots.
- Heap dump và histogram có thể tác động lớn đến JVM; kiểm tra Impact, disk và workload trước khi chạy.
- Bảo vệ HPROF/JFR vì chúng có thể chứa dữ liệu nhạy cảm.
- Kiểm tra `jcmd <pid> help <command>` trên đúng JVM trước khi dùng command.

Hiểu điểm mạnh và giới hạn của `jmap` và `jcmd` giúp bạn chọn đúng cách thu thập dữ liệu heap, phân tích object retention và chẩn đoán JVM có kiểm soát, đặc biệt khi xử lý memory pressure hoặc nghi ngờ memory leak.

## Tài liệu tham khảo

- [The jmap Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html)
- [The jcmd Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Java SE 24 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.html)
