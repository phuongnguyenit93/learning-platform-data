# Lệnh jcmd: chẩn đoán JVM đang chạy

## 1. jcmd là gì?

`jcmd` là công cụ dòng lệnh đi kèm JDK để gửi diagnostic command đến một Java Virtual Machine (JVM) đang chạy trên máy cục bộ. Bạn có thể hỏi JVM về phiên bản, tham số khởi động, flags, heap, thread, bộ nhớ native và ghi Java Flight Recorder (JFR).

Khác với `javac` hoặc `java`, `jcmd` thường làm việc với một tiến trình Java đã tồn tại. Công cụ gửi yêu cầu đến JVM đích; chính JVM đó thực hiện lệnh và trả kết quả.

Các tình huống thường dùng:

- Xác định tiến trình Java và phiên bản JVM đang chạy.
- Kiểm tra lệnh khởi động, classpath và VM flags.
- Chụp thread dump để tìm deadlock hoặc thread bị chờ lâu.
- Xem thông tin heap và native memory.
- Thu thập JFR recording để phân tích hiệu năng.
- Kiểm tra các diagnostic command mà một JVM cụ thể hỗ trợ.

`jcmd` là công cụ chẩn đoán tại máy chạy JVM. Nó không phải công cụ quản lý tiến trình từ xa qua mạng và không thay thế profiler, log, metrics hoặc kiểm thử ứng dụng.

## 2. Cú pháp và cách tìm JVM

Cú pháp tổng quát:

~~~bash
jcmd <pid | main-class> <command> [arguments]
~~~

Trong đó:

- `pid` là process ID của JVM.
- `main-class` là tên class chính được dùng để khởi chạy Java; công cụ có thể khớp tên đầy đủ hoặc một phần.
- `command` là diagnostic command mà JVM đích hỗ trợ.
- `arguments` là các tùy chọn riêng của command đó.

Xem trợ giúp của công cụ:

~~~bash
jcmd -h
~~~

Liệt kê các JVM trên máy:

~~~bash
jcmd -l
~~~

Nếu không truyền tùy chọn, `jcmd` cũng liệt kê các tiến trình Java, tương đương `jcmd -l`.

Ví dụ đầu ra:

~~~text
24816 demo.DiagnosticsTarget
39120 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

Trong ví dụ, `24816` là PID của ứng dụng cần kiểm tra. PID thực tế thay đổi theo mỗi lần chạy.

Sau khi có PID, xem các lệnh mà JVM đích hỗ trợ:

~~~bash
jcmd 24816 help
~~~

Xem cú pháp và mức ảnh hưởng của một command cụ thể:

~~~bash
jcmd 24816 help Thread.print
jcmd 24816 help GC.heap_dump
jcmd 24816 help JFR.start
~~~

Danh sách command phụ thuộc vào phiên bản JDK, loại JVM và cấu hình tiến trình. Luôn dùng `help` của chính JVM đích trước khi chạy một lệnh chưa quen.

## 3. Ví dụ Java chạy liên tục để thực hành jcmd

Tạo file `src/demo/DiagnosticsTarget.java`:

~~~java
package demo;

/** A small process for practicing local JVM diagnostics. */
public final class DiagnosticsTarget {
    /**
     * Keeps the JVM alive for local inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the wait is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        while (true) {
            Thread.sleep(1000);
        }
    }
}
~~~

Biên dịch source tương thích Java 17:

~~~bash
javac --release 17 -d out src/demo/DiagnosticsTarget.java
~~~

Mở Terminal 1 và chạy:

~~~bash
java -cp out demo.DiagnosticsTarget
~~~

Stdout chính xác:

~~~text
READY
~~~

Tiến trình tiếp tục chạy và chờ. Giữ Terminal 1 mở để JVM còn tồn tại.

Mở Terminal 2, liệt kê tiến trình:

~~~bash
jcmd -l
~~~

Tìm dòng có class `demo.DiagnosticsTarget`, lấy PID thực tế rồi chạy:

~~~bash
jcmd 24816 VM.version
jcmd 24816 VM.command_line
jcmd 24816 GC.heap_info
jcmd 24816 Thread.print -l
~~~

Thay `24816` bằng PID hiển thị trên máy của bạn. Khi hoàn tất, quay lại Terminal 1 và nhấn Ctrl+C để dừng chương trình.

Ví dụ này chỉ dùng để thực hành trên tiến trình do chính bạn khởi chạy. Khi kiểm tra ứng dụng khác, hãy xác định đúng PID và quyền truy cập trước khi gửi command.

## 4. Xem thông tin JVM và tham số khởi động

Một số command cơ bản:

| Command | Thông tin |
|---|---|
| `VM.version` | Phiên bản JVM và JDK |
| `VM.uptime` | Thời gian JVM đã chạy |
| `VM.command_line` | Lệnh và tham số khởi động |
| `VM.flags` | Các VM flags hiện tại |
| `VM.system_properties` | System properties |
| `PerfCounter.print` | Performance counter được JVM công bố |

Ví dụ:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

`VM.command_line` giúp kiểm tra JVM đang chạy với classpath, main class hoặc tham số nào. `VM.flags` cho biết các tùy chọn VM như garbage collector và heap sizing đang có hiệu lực.

`VM.system_properties` có thể hiển thị đường dẫn, tên môi trường hoặc giá trị cấu hình nhạy cảm. Tham số dòng lệnh đôi khi cũng chứa token hoặc mật khẩu do ứng dụng cấu hình sai. Không đăng nguyên output lên ticket hoặc chat công khai nếu chưa rà soát và che dữ liệu nhạy cảm.

## 5. Kiểm tra heap và garbage collection

### GC.heap_info

Xem thông tin tổng quát về Java heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Output thường có heap reserved, committed, used, region hoặc generation tùy garbage collector. Đây là ảnh chụp trạng thái tại thời điểm command chạy; không phải số liệu liên tục và không tự giải thích nguyên nhân tăng bộ nhớ.

### GC.class_histogram

Thống kê số lượng instance và dung lượng theo class:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Kết quả có thể giúp tìm class đang chiếm nhiều heap. Tuy nhiên, command này được JVM đánh dấu **Impact: High**; chi phí phụ thuộc kích thước và nội dung heap. Không chạy lặp liên tục trên production chỉ để lấy số liệu.

### GC.heap_dump

Tạo heap dump định dạng HPROF:

~~~bash
jcmd <pid> GC.heap_dump /var/tmp/application-heap.hprof
~~~

Heap dump hữu ích khi phân tích memory leak hoặc object retention bằng công cụ như Java Mission Control hoặc Eclipse MAT. JVM đánh dấu command này **Impact: High** và có thể yêu cầu full GC trước khi dump, trừ khi dùng tùy chọn `-all`.

Heap dump có thể rất lớn, làm tăng I/O và chứa dữ liệu nhạy cảm đang nằm trong memory như thông tin cá nhân, token hoặc nội dung request. Hãy kiểm tra dung lượng đĩa, quyền truy cập file và chính sách dữ liệu trước khi tạo hoặc chia sẻ.

### GC.run

~~~bash
jcmd <pid> GC.run
~~~

Command này gọi `System.gc()`. Nó không phải cách sửa memory leak; full GC có thể làm ứng dụng tạm dừng và không đảm bảo giải phóng object còn được tham chiếu. Chỉ dùng khi có mục tiêu chẩn đoán cụ thể.

## 6. Chụp thread dump với Thread.print

Thread dump cho biết thread đang chạy, chờ monitor, chờ condition hoặc bị block tại thời điểm chụp.

Lệnh cơ bản:

~~~bash
jcmd <pid> Thread.print
~~~

Hiển thị thêm thông tin lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

Một phần output minh họa:

~~~text
"main" #1 prio=5 os_prio=0
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.DiagnosticsTarget.main(DiagnosticsTarget.java:12)
~~~

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa khái quát |
|---|---|
| RUNNABLE | Thread đang chạy hoặc sẵn sàng chạy trong JVM |
| BLOCKED | Chờ lấy intrinsic monitor |
| WAITING | Chờ một thread hoặc điều kiện khác |
| TIMED_WAITING | Chờ có giới hạn thời gian |
| TERMINATED | Thread đã kết thúc |

Khi điều tra deadlock hoặc request bị treo:

1. Chụp một thread dump.
2. Chờ một khoảng ngắn phù hợp với sự cố.
3. Chụp thêm một hoặc hai dump.
4. So sánh stack trace, trạng thái và lock giữa các lần.
5. Tìm thread có stack không đổi, lock bị giữ lâu hoặc chuỗi chờ vòng tròn.

Một dump đơn lẻ chỉ là ảnh chụp tại một thời điểm. So sánh nhiều dump giúp phân biệt thread đang xử lý bình thường với thread bị kẹt lâu dài. `Thread.print` có mức ảnh hưởng Medium và chi phí phụ thuộc số lượng thread.

## 7. Theo dõi native memory với Native Memory Tracking

Java heap không phải toàn bộ bộ nhớ mà tiến trình JVM sử dụng. JVM còn dùng native memory cho metaspace, thread stack, code cache, GC structures và các thành phần runtime khác.

`VM.native_memory` xem số liệu Native Memory Tracking (NMT):

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT phải được bật khi JVM khởi động. Ví dụ:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Có thể dùng chế độ `detail` để thu thập thông tin chi tiết hơn, đổi lại có thêm chi phí theo dõi.

Nếu NMT chưa được bật, command có thể trả:

~~~text
Native memory tracking is not enabled
~~~

Không thể bật NMT lần đầu bằng cách gọi `jcmd` sau khi ứng dụng đã chạy. Cần khởi động lại JVM với tùy chọn phù hợp.

Có thể lấy baseline và so sánh thay đổi:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

NMT phản ánh vùng bộ nhớ native mà HotSpot theo dõi; không nên xem nó là số đo đầy đủ cho mọi allocation native do thư viện bên ngoài hoặc hệ điều hành quản lý.

## 8. Ghi Java Flight Recorder bằng jcmd

Java Flight Recorder (JFR) thu thập event của JVM và ứng dụng để phân tích CPU, allocation, GC, thread, lock, I/O và nhiều hoạt động khác.

Bắt đầu một recording có thời hạn:

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=default duration=60s filename=diagnostic.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Xuất snapshot khi recording đang chạy:

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
~~~

Dừng recording theo tên:

~~~bash
jcmd <pid> JFR.stop name=diagnostic
~~~

Các điểm cần biết:

- `settings=default` dùng cấu hình thu thập có overhead thấp hơn và phù hợp theo dõi dài hơn.
- `settings=profile` thu thập nhiều dữ liệu hơn nhưng có thể tăng overhead; phù hợp đợt profiling ngắn.
- `duration=60s` tự kết thúc recording sau khoảng thời gian đã chỉ định.
- File recording được ghi theo quyền và thư mục của tiến trình JVM đích; chọn đường dẫn mà tiến trình có quyền ghi.
- `JFR.start` có mức ảnh hưởng Medium (Impact: Medium); đọc `help JFR.start` để xem các tùy chọn theo JDK hiện tại.

Có thể mở file `.jfr` bằng Java Mission Control hoặc công cụ phân tích JFR phù hợp. Một recording cho thấy sự kiện trong khoảng thời gian thu thập; hãy ghi lại thời điểm và tải công việc để liên hệ với triệu chứng thực tế.

## 9. Thay đổi VM flag trong lúc chạy

`VM.flags` xem các flag đang có hiệu lực:

~~~bash
jcmd <pid> VM.flags
~~~

Một số JVM cho phép thay đổi flag khi đang chạy bằng:

~~~bash
jcmd <pid> VM.set_flag <flag-name> <value>
~~~

Không phải mọi flag đều có thể thay đổi sau khi JVM khởi động. `help VM.set_flag` mô tả cú pháp, còn khả năng thay đổi phụ thuộc flag và JVM cụ thể.

Thay đổi flag có thể làm thay đổi GC, memory, compiler hoặc hành vi runtime. Hãy hiểu rõ tác động, lưu lại giá trị ban đầu và có kế hoạch khôi phục. Đối với cấu hình quan trọng, thay đổi ở lần khởi động tiếp theo thường dễ kiểm soát và tái lập hơn.

## 10. Mức ảnh hưởng của diagnostic command

Mỗi command có chi phí khác nhau. Có thể xem mức ảnh hưởng bằng:

~~~bash
jcmd <pid> help <command>
~~~

Trên JDK 24.0.2, một số mức được hiển thị như sau:

| Command | Impact hiển thị | Lưu ý |
|---|---|---|
| `VM.version` | Thấp | Thông tin phiên bản |
| `JFR.check` | Thấp | Xem recording đang chạy |
| `JFR.dump` | Thấp | Sao chép dữ liệu recording |
| `Thread.print` | Trung bình | Phụ thuộc số lượng thread |
| `GC.heap_info` | Trung bình | Đọc trạng thái heap |
| `VM.native_memory` | Trung bình | Phụ thuộc cấu hình NMT |
| `JFR.start` | Trung bình | Phụ thuộc event settings |
| `GC.class_histogram` | Cao | Phụ thuộc kích thước heap |
| `GC.heap_dump` | Cao | Có thể gây full GC và I/O lớn |

Mức impact là thông tin do JVM cung cấp, không phải cam kết về thời gian dừng cố định. Cùng một command có thể tốn chi phí khác nhau trên ứng dụng có heap, thread hoặc tải khác nhau.

Trước khi chạy command trên production:

- Đọc `help <command>` để xem cú pháp và impact.
- Xác định mục tiêu chẩn đoán và thời điểm chạy.
- Kiểm tra CPU, heap, disk và dung lượng lưu output.
- Tránh lặp lại command impact cao trong vòng lặp tự động.
- Ghi nhận thời điểm, PID và lệnh đã chạy để đối chiếu với metrics.

## 11. Quyền truy cập và attach mechanism

`jcmd` cần attach được vào JVM đích. Một số điều kiện thường gặp:

- Tiến trình Java phải ở trên máy mà công cụ có thể attach tới.
- Người chạy `jcmd` thường cần cùng user hoặc quyền hệ điều hành phù hợp với tiến trình đích.
- JVM phải cho phép attach; tùy chọn `-XX:+DisableAttachMechanism` vô hiệu hóa cơ chế này.
- Môi trường container hoặc PID namespace có thể làm tiến trình không xuất hiện trong danh sách hoặc không thể attach từ namespace khác.
- Dùng JDK có công cụ `jcmd` và chọn command mà JVM đích hỗ trợ.

Không gửi command tới một PID chưa xác định. `jcmd 0` có nghĩa gửi command đến tất cả Java process mà công cụ có thể tiếp cận; tránh dùng PID 0 trừ khi thật sự muốn broadcast.

Diagnostic command có thể đọc thông tin runtime nhạy cảm hoặc tạo file chứa dữ liệu trong memory. Hãy giới hạn quyền sử dụng và bảo vệ output như dữ liệu vận hành của ứng dụng.

## 12. Lỗi thường gặp và cách xử lý

### jcmd không được nhận diện

`jcmd` thuộc JDK. Kiểm tra đang dùng JDK thay vì runtime tối giản, hoặc gọi công cụ bằng đường dẫn trong thư mục `bin` của JDK.

### Không tìm thấy PID trong jcmd -l

Kiểm tra ứng dụng còn chạy, có đúng máy/PID namespace không và bạn có quyền nhìn thấy tiến trình không. Nếu chạy trong container, thực hiện chẩn đoán từ môi trường có thể nhìn thấy PID của JVM đó.

### AttachNotSupportedException hoặc không thể attach

Kiểm tra user chạy công cụ, quyền hệ điều hành, attach mechanism và tùy chọn `-XX:+DisableAttachMechanism`. Một số JVM hoặc môi trường bảo mật có thể chủ động chặn attach.

### Unknown diagnostic command

Command có thể không tồn tại trong phiên bản hoặc loại JVM đích. Chạy `jcmd <pid> help` rồi `jcmd <pid> help <command>` để xem danh sách và cú pháp thật.

### Native memory tracking is not enabled

Khởi động lại JVM với `-XX:NativeMemoryTracking=summary` hoặc `detail` nếu cần NMT. Không thể bật lần đầu sau khi JVM đã chạy.

### Heap dump không ghi được

Kiểm tra đường dẫn được JVM đích nhìn thấy, quyền ghi của user chạy JVM và dung lượng ổ đĩa. Heap dump có thể lớn và chứa dữ liệu nhạy cảm.

### JFR không tạo file

Kiểm tra recording đã bắt đầu chưa bằng `JFR.check`, file path có thể ghi được không, recording đã tự kết thúc chưa và tên recording có đúng không. Dùng `help JFR.start`, `help JFR.dump` và `help JFR.stop` theo JDK đang chạy.

## 13. Quy trình chẩn đoán JVM thực tế

Một quy trình nhẹ để bắt đầu:

1. Dùng `jcmd -l` xác định đúng JVM và PID.
2. Chạy `VM.version`, `VM.uptime`, `VM.command_line` và `VM.flags` để nắm môi trường.
3. Dùng `GC.heap_info` nếu nghi ngờ heap tăng hoặc GC bất thường.
4. Dùng `Thread.print -l` nếu request bị treo, thread bị block hoặc có dấu hiệu deadlock.
5. Nếu cần phân tích theo thời gian, ghi JFR trong một khoảng ngắn với settings phù hợp.
6. Chỉ tạo class histogram hoặc heap dump khi đã đánh giá impact, dung lượng và quyền truy cập.
7. Lưu output cùng timestamp, PID, phiên bản JDK và triệu chứng để đối chiếu.
8. Sau khi thu thập đủ dữ liệu, dừng recording và xử lý file chẩn đoán theo chính sách lưu trữ.

Không chạy mọi diagnostic command cùng lúc theo một script mặc định. Chọn lệnh dựa trên giả thuyết cần kiểm tra; command có impact cao chỉ nên chạy khi dữ liệu nhẹ hơn chưa đủ trả lời câu hỏi.

## 14. Checklist sử dụng jcmd an toàn và hiệu quả

- [ ] Dùng `jcmd -h` và `jcmd -l` để khám phá công cụ và JVM cục bộ.
- [ ] Xác nhận đúng PID hoặc main class trước khi gửi command.
- [ ] Dùng `jcmd <pid> help` để biết command mà JVM đích hỗ trợ.
- [ ] Dùng `help <command>` để kiểm tra cú pháp, tham số và mức impact.
- [ ] Dùng `VM.version`, `VM.command_line`, `VM.flags` để hiểu cấu hình runtime.
- [ ] Dùng `GC.heap_info` và `Thread.print` cho kiểm tra ban đầu.
- [ ] Bật NMT từ lúc khởi động nếu cần phân tích native memory.
- [ ] Dùng JFR recording có thời hạn và settings phù hợp.
- [ ] Đánh giá tác động trước `GC.class_histogram`, `GC.heap_dump` hoặc `GC.run`.
- [ ] Kiểm tra quyền ghi, dung lượng và độ nhạy của heap dump/JFR output.
- [ ] Không dùng PID `0` nếu không muốn gửi command tới mọi JVM có thể attach.
- [ ] Lưu lại lệnh và timestamp để kết quả có thể đối chiếu, tái lập.

`jcmd` giúp quan sát một JVM đang chạy mà không cần sửa source hoặc khởi động lại ứng dụng cho các kiểm tra cơ bản. Dùng PID chính xác, đọc help theo JVM đích và đánh giá impact trước khi chạy sẽ giúp thu thập thông tin hữu ích mà vẫn kiểm soát được rủi ro vận hành.
