# Dùng các GC command của `jcmd` để chẩn đoán JVM

`jcmd` là công cụ dòng lệnh trong JDK dùng để gửi diagnostic command đến một Java Virtual Machine (JVM) đang chạy. Nhóm lệnh `GC.*` cung cấp thông tin về heap, thống kê đối tượng, hàng đợi finalization, yêu cầu garbage collection và tạo heap dump để phân tích bộ nhớ.

Các lệnh thường gặp:

| Command | Mục đích |
|---|---|
| `GC.heap_info` | Xem thông tin tổng quát về Java heap |
| `GC.class_histogram` | Thống kê số lượng và dung lượng đối tượng theo class |
| `GC.heap_dump` | Tạo heap dump định dạng HPROF |
| `GC.run` | Gọi `System.gc()` trên JVM đích |
| `GC.finalizer_info` | Xem thông tin hàng đợi finalization |
| `GC.run_finalization` | Gọi `System.runFinalization()` |

Không phải tất cả lệnh đều chỉ đọc dữ liệu. `GC.heap_info` là chẩn đoán tổng quát; `GC.class_histogram` và `GC.heap_dump` có thể tạo tải đáng kể; `GC.run` có thể yêu cầu một đợt GC; heap dump có thể gây pause và tạo file lớn. Hãy chọn lệnh theo câu hỏi cần trả lời, kiểm tra impact và thực hiện trên đúng JVM.

Toolchain được kiểm tra cho bài này là Zulu/OpenJDK 24.0.2. Danh sách command và tùy chọn phụ thuộc phiên bản JDK, JVM đích và collector; luôn dùng `jcmd <pid> help` để xem khả năng thực tế của process.

## 1. `jcmd` gửi lệnh đến JVM như thế nào?

`jcmd` giao tiếp với JVM thông qua cơ chế attach và diagnostic command framework. Mỗi JVM đang chạy có một process ID (PID); người vận hành chọn PID rồi gửi command mà JVM đó hỗ trợ.

Cú pháp tổng quát:

~~~text
jcmd <pid> <command> [arguments]
~~~

Các dạng sử dụng:

~~~text
jcmd -l
jcmd <pid> help
jcmd <pid> help GC.heap_info
jcmd <pid> GC.heap_info
~~~

- `jcmd -l`: liệt kê JVM mà công cụ nhìn thấy trên máy hiện tại.
- `jcmd <pid> help`: liệt kê command mà JVM đích hỗ trợ.
- `jcmd <pid> help <command>`: xem cú pháp, tùy chọn và mức impact của command cụ thể.
- `jcmd <pid> <command>`: gửi command đến process đã chọn.

Nếu truyền PID `0`, `jcmd` gửi command đến tất cả Java process mà nó quản lý được. Tránh dùng PID `0` với các lệnh tạo heap dump hoặc yêu cầu GC vì có thể tác động đồng thời nhiều ứng dụng.

`jcmd` chạy trên cùng máy với JVM đích. Công cụ thường cần chạy dưới cùng tài khoản người dùng với process; cơ chế attach có thể bị vô hiệu hóa hoặc bị giới hạn bởi môi trường bảo mật. Trong container, hãy chạy từ đúng container/PID namespace hoặc môi trường có thể nhìn thấy process đích.

## 2. Tìm đúng Java process

Bắt đầu bằng:

~~~text
jcmd -l
~~~

Ví dụ output minh họa:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
31552 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider
~~~

PID thay đổi theo mỗi lần khởi chạy. Không sao chép PID ví dụ vào môi trường thật; hãy lấy PID từ output hiện tại.

Có thể dùng tên main class để tìm process:

~~~text
jcmd OrderService help
~~~

Tuy nhiên, khi có nhiều process cùng main class hoặc tên gần giống nhau, PID là lựa chọn rõ ràng hơn.

Sau khi tìm PID, xác nhận đúng JVM trước khi chạy command có impact cao:

~~~text
jcmd 18240 VM.command_line
jcmd 18240 VM.version
jcmd 18240 VM.info
~~~

Các lệnh `VM.*` này giúp kiểm tra command line, phiên bản và thông tin runtime của process. Chúng không thay thế việc xác nhận owner, môi trường và mục đích vận hành.

## 3. Xem danh sách GC command và trợ giúp chi tiết

Không nên đoán command hoặc option theo một JDK khác. Hỏi trực tiếp JVM đích:

~~~text
jcmd 18240 help
~~~

Lọc các lệnh liên quan đến GC trong output, ví dụ:

~~~text
GC.class_histogram
GC.finalizer_info
GC.heap_dump
GC.heap_info
GC.run
GC.run_finalization
~~~

Sau đó xem help riêng:

~~~text
jcmd 18240 help GC.class_histogram
jcmd 18240 help GC.heap_dump
~~~

Help của command cho biết:

- Cú pháp chính xác.
- Các option được hỗ trợ.
- Kiểu dữ liệu của option.
- Giá trị mặc định.
- Mức impact do JVM mô tả.

Trên JDK 24.0.2, `GC.class_histogram` và `GC.heap_dump` được đánh dấu impact High; `GC.heap_info`, `GC.run`, `GC.finalizer_info` và `GC.run_finalization` có mức impact Medium. Mức impact là hướng dẫn để lập kế hoạch, không phải cam kết về thời gian thực thi.

## 4. `GC.heap_info`: xem tổng quan Java heap

Dùng:

~~~text
jcmd 18240 GC.heap_info
~~~

Command trả về thông tin tổng quát về Java heap của JVM đích. Tùy collector và phiên bản, output có thể chứa:

- Heap capacity hoặc tổng dung lượng vùng heap.
- Dung lượng đang sử dụng và còn trống.
- Thông tin region của G1.
- Kích thước generation hoặc pool mà collector công bố.
- Một số số liệu nội bộ liên quan đến heap.

Ví dụ output mang tính minh họa:

~~~text
Garbage-First (G1) Heap
regions: ...
Heap Usage:
   ...
~~~

Không dùng các con số minh họa để dự đoán memory usage của ứng dụng. Tên trường, đơn vị và cấu trúc output phụ thuộc collector.

### Khi nào nên dùng?

- Kiểm tra heap đang sử dụng ở mức tổng quan.
- So sánh trạng thái trước và sau một thao tác vận hành.
- Xác nhận JVM có heap gần giới hạn cấu hình hay không.
- Thu thập dữ liệu ban đầu trước khi quyết định tạo histogram hoặc heap dump.

`GC.heap_info` không cho biết object nào đang giữ bộ nhớ. Nếu cần tìm class chiếm nhiều dung lượng, dùng `GC.class_histogram`; nếu cần phân tích object graph và retaining path, cần heap dump cùng công cụ phân tích phù hợp.

## 5. `GC.class_histogram`: thống kê object theo class

Dùng:

~~~text
jcmd 18240 GC.class_histogram
~~~

Command tạo histogram của các object trong Java heap. Output thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| `num` | Thứ tự dòng trong báo cáo |
| `#instances` | Số instance của class |
| `#bytes` | Tổng số byte được tính cho các instance |
| `class name` | Tên class; có thể kèm module |

Ví dụ cấu trúc output:

~~~text
 num        #instances          #bytes  class name (module)
   1:             ...             ...  [B (java.base)
   2:             ...             ...  java.lang.String (java.base)
   3:             ...             ...  java.util.HashMap$Node (java.base)
 ...
 Total             ...             ...
~~~

Dấu `...` là phần số liệu thay đổi theo process. Histogram là thống kê tại thời điểm thu thập, không phải số đo allocation rate theo thời gian.

### 5.1. Tùy chọn `-all`

Theo help của JDK 24.0.2:

- Mặc định `-all=false`: không yêu cầu kiểm tra toàn bộ object kể cả object unreachable.
- `-all=true`: kiểm tra cả object unreachable.
- `-parallel=0`: để JVM tự chọn số thread kiểm tra; `1` tắt parallelism; giá trị khác yêu cầu số thread tương ứng nhưng JVM có thể dùng ít hơn.

Ví dụ:

~~~text
jcmd 18240 GC.class_histogram -all=true
jcmd 18240 GC.class_histogram -parallel=1
~~~

`-all=true` thay đổi tập object được thống kê, vì vậy kết quả không nên so sánh trực tiếp với histogram mặc định mà không ghi rõ option.

### 5.2. Cách đọc histogram

Nếu một class có số instance lớn, hãy đặt câu hỏi:

- Có phải ứng dụng chủ động cache nhiều object?
- Có collection tăng không giới hạn?
- Có object được giữ bởi static field hoặc singleton?
- Có chuỗi, byte array hoặc buffer được giữ lâu hơn dự kiến?
- Có nhiều instance nhỏ tạo ra tổng dung lượng lớn không?

Histogram không hiển thị đầy đủ quan hệ tham chiếu. Một class có tổng byte lớn chưa chắc là nguyên nhân gốc; cần phân tích ai đang giữ object. Dùng heap dump để xem dominator tree, retained size và reference path khi cần.

`GC.class_histogram` có impact High vì phải kiểm tra heap. Trên heap lớn, lệnh có thể tiêu tốn CPU và gây pause đáng kể. Tránh chạy liên tục trong production chỉ để quan sát định kỳ.

## 6. `GC.heap_dump`: tạo heap dump HPROF

Dùng:

~~~text
jcmd 18240 GC.heap_dump D:\diagnostics\orders.hprof
~~~

Trên macOS/Linux:

~~~text
jcmd 18240 GC.heap_dump /var/tmp/orders.hprof
~~~

Heap dump chứa thông tin object và quan hệ tham chiếu trong heap tại thời điểm chụp. Có thể mở file bằng Eclipse MAT, VisualVM hoặc công cụ hỗ trợ định dạng HPROF.

Theo help của JDK 24.0.2, `GC.heap_dump` có các tùy chọn:

| Option | Công dụng |
|---|---|
| `-all` | Dump cả object unreachable |
| `-gz=1` | Ghi dump gzip; mức 1 nhanh nhất |
| `-gz=9` | Nén mạnh hơn, tốn CPU hơn |
| `-overwrite=true` | Cho phép ghi đè file dump đã tồn tại |
| `-parallel=1` | Yêu cầu một thread tạo heap dump |

Ví dụ tạo file gzip:

~~~text
jcmd 18240 GC.heap_dump -gz=1 D:\diagnostics\orders.hprof.gz
~~~

### 6.1. Tác động của heap dump

Heap dump là thao tác impact High:

- Có thể mất nhiều thời gian tùy heap size và số lượng object.
- Có thể gây safepoint pause hoặc ảnh hưởng latency.
- Cần đủ dung lượng đĩa; file có thể rất lớn.
- Theo mặc định, JVM yêu cầu một full GC trước khi dump, trừ khi dùng `-all`.
- Nếu dùng `-all`, dump bao gồm cả object unreachable và không yêu cầu full GC theo hành vi được mô tả trong help.
- File dump được tạo trên máy/namespace của JVM đích, theo quyền của process đó.

Không tạo heap dump trên đường dẫn dùng chung không đủ dung lượng. Dùng đường dẫn tuyệt đối, kiểm tra quyền ghi và xác nhận file đích chưa tồn tại nếu không muốn ghi đè.

### 6.2. Bảo vệ dữ liệu trong heap dump

Heap dump có thể chứa:

- Access token, session ID và API key.
- Mật khẩu hoặc dữ liệu xác thực còn trong memory.
- Thông tin cá nhân của người dùng.
- Nội dung request/response và dữ liệu nghiệp vụ.
- Dữ liệu nhạy cảm trong cache hoặc buffer.

Xem heap dump là dữ liệu nhạy cảm. Hạn chế quyền truy cập, lưu ở vị trí được phê duyệt, mã hóa khi lưu/truyền, quy định thời hạn lưu giữ và xóa theo chính sách sau khi phân tích. Không đính kèm dump trực tiếp vào ticket công khai.

## 7. `GC.run`: yêu cầu JVM chạy garbage collection

Dùng:

~~~text
jcmd 18240 GC.run
~~~

Theo help, command này gọi:

~~~java
System.gc();
~~~

Đây là yêu cầu GC tường minh. Nó không bảo đảm mọi object không còn được tham chiếu sẽ được thu hồi ngay, và hành vi thực tế phụ thuộc collector cùng cấu hình JVM.

Lưu ý:

- `System.gc()` có thể bị bỏ qua nếu JVM được chạy với `-XX:+DisableExplicitGC`.
- Collector có thể thực hiện full GC hoặc hành động khác theo implementation.
- Một đợt GC có thể gây pause, tăng CPU và làm thay đổi latency.
- Chạy lặp lại không phải cách sửa memory leak.
- Bộ nhớ đã thu hồi trong heap không nhất thiết được trả ngay về hệ điều hành.

Không dùng `GC.run` như một bước “dọn bộ nhớ” định kỳ trong production. Nếu nghi ngờ memory leak, hãy thu thập metrics, histogram hoặc heap dump để xác định object đang được giữ bởi reference nào.

## 8. `GC.finalizer_info` và `GC.run_finalization`

Hai command này liên quan đến cơ chế finalization cũ của Java.

### 8.1. Xem hàng đợi finalization

~~~text
jcmd 18240 GC.finalizer_info
~~~

Command cung cấp thông tin về Java finalization queue. Nó hữu ích khi điều tra ứng dụng còn phụ thuộc vào `finalize()` hoặc hàng đợi finalizer tăng bất thường.

Không dùng số lượng finalizer như thước đo tổng quát của garbage collection. Finalization là cơ chế riêng, có thời điểm thực thi không xác định và có thể làm chậm việc thu hồi object.

### 8.2. Yêu cầu chạy finalization

~~~text
jcmd 18240 GC.run_finalization
~~~

Command gọi `System.runFinalization()`. Nó yêu cầu JVM chạy các finalizer đang chờ theo khả năng của runtime; không bảo đảm mọi finalizer được chạy ngay hoặc theo thứ tự cụ thể.

Finalization đã bị deprecated for removal từ Java 18. Code mới nên dùng `AutoCloseable`, `try-with-resources`, `Cleaner` khi thật sự cần hoặc API quản lý tài nguyên tường minh. Không dựa vào `GC.run_finalization` để đóng file, socket hoặc native resource trong luồng vận hành bình thường.

## 9. Chọn GC command theo câu hỏi cần trả lời

| Câu hỏi | Command phù hợp | Tác động cần cân nhắc |
|---|---|---|
| Heap hiện dùng bao nhiêu? | `GC.heap_info` | Medium |
| Class nào có nhiều instance hoặc chiếm nhiều byte? | `GC.class_histogram` | High |
| Object nào giữ bộ nhớ và reference path là gì? | `GC.heap_dump` rồi phân tích HPROF | High |
| Có thể yêu cầu JVM chạy GC để kiểm tra giả thuyết? | `GC.run` | Medium; có thể gây pause |
| Hàng đợi finalization có vấn đề không? | `GC.finalizer_info` | Medium |
| Có cần yêu cầu xử lý finalizer cũ? | `GC.run_finalization` | Medium; không dùng làm cleanup strategy |

Một luồng điều tra memory pressure hợp lý:

1. Thu thập metrics và GC log để xác định xu hướng.
2. Dùng `GC.heap_info` để xem heap tổng quát.
3. Nếu cần phân loại object, chạy `GC.class_histogram` trong thời điểm phù hợp.
4. Nếu cần reference graph, lên kế hoạch heap dump.
5. Phân tích retained size và dominator tree bằng công cụ HPROF.
6. Xác định code giữ object, sửa nguyên nhân và đo lại.

Không bắt đầu bằng heap dump trong mọi sự cố. Dùng thao tác có impact thấp hơn nếu chúng đã đủ trả lời câu hỏi.

## 10. Ví dụ Java 17: tạo JVM để thực hành GC command

Tạo file `GcDemo.java`:

~~~java
public final class GcDemo {
    private static byte[][] retained;

    private GcDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        retained = new byte[8][];
        for (int i = 0; i < retained.length; i++) {
            retained[i] = new byte[1024 * 1024];
        }

        System.out.println(
                "GC demo ready; retained arrays=" + retained.length);

        Thread.sleep(300_000);
    }
}
~~~

Mảng được giữ trong static field để các byte array vẫn reachable trong lúc process chờ. Chương trình chỉ tạo dữ liệu thử nghiệm, không truy cập mạng hoặc file.

Biên dịch:

~~~text
javac --release 17 GcDemo.java
~~~

Chạy trong terminal thứ nhất:

~~~text
java -Xms64m -Xmx128m GcDemo
~~~

Stdout:

~~~text
GC demo ready; retained arrays=8
~~~

Chương trình chờ tối đa năm phút để có thời gian gửi diagnostic command. Mở terminal thứ hai và tìm PID:

~~~text
jcmd -l
~~~

Tìm dòng có main class `GcDemo`, sau đó thay `<PID>` bằng PID thật trong các lệnh sau:

~~~text
jcmd <PID> help
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
jcmd <PID> GC.finalizer_info
~~~

Có thể tạo heap dump để thực hành phân tích:

~~~text
jcmd <PID> GC.heap_dump -gz=1 gc-demo.hprof.gz
~~~

Lệnh heap dump có impact cao và có thể yêu cầu full GC theo mặc định. Chỉ chạy khi đã chuẩn bị dung lượng lưu trữ và chấp nhận pause. Kết thúc chương trình bằng `Ctrl+C` ở terminal thứ nhất.

PID và số liệu heap thay đổi theo máy, JDK và collector; chỉ dòng stdout do chương trình in ra là cố định.

## 11. Chạy một nhóm diagnostic command trong PowerShell

Có thể thu thập một số thông tin chẩn đoán trong một script. Dùng biến `$javaPid` thay vì `$pid`, vì PowerShell đã có biến tự động `$PID`.

~~~powershell
$javaPid = 18240

jcmd $javaPid VM.version
jcmd $javaPid VM.command_line
jcmd $javaPid GC.heap_info
jcmd $javaPid GC.class_histogram
~~~

Mỗi lệnh được gửi riêng và output xuất hiện trong terminal. Histogram có impact High; hãy cân nhắc thời điểm chạy trước khi thêm vào script tự động.

Nếu cần lưu output, redirect từng lệnh vào file có quyền truy cập phù hợp. Với heap dump, dùng một lệnh riêng và đặt đường dẫn rõ ràng:

~~~powershell
jcmd $javaPid GC.heap_dump -gz=1 D:\diagnostics\app.hprof.gz
~~~

Không chạy đồng thời nhiều heap dump trên cùng JVM nếu chưa đánh giá ảnh hưởng đến pause, CPU và disk I/O.

## 12. Quyền truy cập, container và giới hạn attach

Nếu `jcmd -l` không thấy JVM mong muốn, kiểm tra:

- `jcmd` đang chạy trên đúng máy host.
- User chạy `jcmd` có quyền attach vào JVM đích.
- JVM và `jcmd` nằm trong cùng PID namespace/container phù hợp.
- Process chưa kết thúc và PID chưa bị tái sử dụng.
- Attach mechanism không bị tắt bằng `-XX:+DisableAttachMechanism`.
- Chính sách bảo mật hoặc runtime environment không chặn attach listener.

Trong container, PID hiển thị từ host có thể khác PID bên trong container. Chạy `jcmd -l` và `jcmd` trong cùng container hoặc namespace là cách dễ xác định đúng PID nhất.

Một số môi trường serverless, hardened container hoặc process chạy với attach disabled có thể không cho phép dùng `jcmd`. Khi đó, dựa vào GC log, JFR, metrics và cơ chế diagnostics được nền tảng hỗ trợ.

## 13. GC command, GC log và JFR khác nhau thế nào?

`jcmd GC.*` là thao tác chẩn đoán hoặc yêu cầu hành động tại một thời điểm. GC log và JFR phù hợp hơn để quan sát xu hướng theo thời gian.

### GC logging

Có thể bật log khi khởi chạy JVM:

~~~text
-Xlog:gc*
~~~

GC log giúp xem tần suất GC, pause time, heap occupancy và thông tin collector theo từng sự kiện. Với ứng dụng production, cấu hình log rotation và vị trí lưu file ngay từ đầu.

### Java Flight Recorder

JFR ghi nhận sự kiện runtime như GC, allocation, thread, lock và nhiều sự kiện khác. JFR phù hợp khi cần liên hệ memory behavior với hoạt động của ứng dụng trong một khoảng thời gian.

`jcmd` cũng cung cấp các command `JFR.*` trên nhiều JDK, nhưng chúng không phải command thuộc nhóm `GC.*`. Xem `jcmd <pid> help JFR.start` trước khi sử dụng.

Không dùng một histogram hoặc heap dump đơn lẻ để kết luận về allocation rate hay pause distribution. Kết hợp nhiều nguồn quan sát sẽ giúp xác định nguyên nhân tốt hơn.

## 14. Troubleshooting GC command

### `No such process`

**Nguyên nhân:** PID không tồn tại, process đã thoát hoặc PID được lấy từ namespace khác.

**Cách xử lý:** chạy lại `jcmd -l` trong đúng môi trường và xác nhận PID trước khi gửi lệnh.

### `AttachNotSupportedException` hoặc không attach được

**Nguyên nhân:** khác user, attach mechanism bị tắt, container/PID namespace không phù hợp hoặc môi trường bảo mật chặn attach.

**Cách xử lý:** chạy dưới user phù hợp, kiểm tra `-XX:+DisableAttachMechanism` và thực thi từ đúng host/container. Không tự ý nới quyền bảo mật của process.

### `Unknown diagnostic command`

**Nguyên nhân:** JVM đích không hỗ trợ command đó hoặc command có tên khác ở JDK hiện tại.

**Cách xử lý:** chạy `jcmd <PID> help`, sau đó xem `help <command>` trên đúng JVM đích.

### `GC.class_histogram` chạy lâu

**Nguyên nhân:** heap lớn, số lượng object cao hoặc heap inspection tạo tải đáng kể.

**Cách xử lý:** chọn thời điểm ít tải, xem metrics trước, hạn chế số lần chạy và cân nhắc `-parallel` theo help của JVM.

### `GC.heap_dump` thất bại

**Nguyên nhân:** thiếu dung lượng, đường dẫn không tồn tại, process không có quyền ghi hoặc file đã tồn tại mà không bật overwrite.

**Cách xử lý:** dùng đường dẫn tuyệt đối, kiểm tra dung lượng/quyền và chỉ bật `-overwrite=true` khi chủ đích ghi đè đã được xác nhận.

### Heap dump làm ứng dụng pause lâu

**Nguyên nhân:** dump phải duyệt lượng lớn object và mặc định có thể yêu cầu full GC.

**Cách xử lý:** lên lịch trong cửa sổ bảo trì, cân nhắc chi phí pause, dùng `-gz` để giảm dung lượng lưu trữ và chỉ dùng `-all` khi cần object unreachable.

### `GC.run` không làm heap giảm như mong đợi

**Nguyên nhân:** object vẫn reachable, explicit GC bị tắt, collector quyết định khác hoặc heap chưa trả vùng nhớ cho OS.

**Cách xử lý:** kiểm tra reference/retained size bằng histogram và heap dump; xem GC log. Không lặp lại `GC.run` để che dấu memory leak.

### Histogram thay đổi giữa hai lần chạy

**Nguyên nhân:** workload, allocation, GC và thời điểm chụp khác nhau.

**Cách xử lý:** so sánh trong điều kiện tải tương đương, ghi nhận option `-all`, thời điểm và collector; không xem hai snapshot khác thời điểm như phép đo hoàn toàn tương đương.

## 15. Checklist trước khi chạy GC command trên production

- [ ] Đã xác định đúng host, container, PID và owner của JVM.
- [ ] Đã xác nhận JDK/JVM version và command được hỗ trợ bằng `jcmd <PID> help`.
- [ ] Đã đọc impact và options của command cụ thể.
- [ ] Đã xác định câu hỏi chẩn đoán cần trả lời.
- [ ] Đã cân nhắc pause, CPU và memory overhead.
- [ ] Chỉ chạy `GC.run` khi có lý do rõ ràng; không dùng như biện pháp chữa memory leak.
- [ ] Chỉ chạy histogram/heap dump khi đã đánh giá tải.
- [ ] Heap dump có đường dẫn, dung lượng đĩa và quyền truy cập phù hợp.
- [ ] File dump được bảo vệ như dữ liệu nhạy cảm.
- [ ] Không dùng PID `0` cho command có thể tác động nhiều JVM.
- [ ] Output được lưu kèm thời điểm, PID, JDK version và command line.
- [ ] Kết quả được đối chiếu với GC log, metrics hoặc JFR trước khi kết luận.
- [ ] Đã có kế hoạch dọn dữ liệu dump theo chính sách lưu giữ.

Các GC command của `jcmd` giúp kiểm tra heap và thu thập bằng chứng khi điều tra memory issue. Dùng `GC.heap_info` để bắt đầu, `GC.class_histogram` để phân loại object và `GC.heap_dump` khi cần phân tích reference graph. Hiểu impact, xác nhận đúng JVM và bảo vệ dữ liệu dump sẽ giúp chẩn đoán an toàn hơn trên cả môi trường phát triển lẫn production.