# Điều khiển Java Flight Recorder bằng jcmd

## 1. JFR command trong jcmd là gì?

Java Flight Recorder (JFR) là hệ thống ghi nhận sự kiện của JVM và ứng dụng Java. JFR thu thập dữ liệu về garbage collection, allocation, thread, lock contention, class loading, JIT compilation, file I/O, socket I/O và nhiều hoạt động runtime khác. Dữ liệu được lưu trong file nhị phân `.jfr` để phân tích sau.

`jcmd` là công cụ chẩn đoán đi kèm JDK. Nó gửi diagnostic command tới một JVM đang chạy trên cùng máy. Nhóm lệnh `JFR.*` cho phép điều khiển recording trực tiếp mà không cần khởi động lại ứng dụng:

- `JFR.start` bắt đầu một recording.
- `JFR.check` xem các recording đang chạy và cấu hình event.
- `JFR.dump` chụp dữ liệu recording ra file trong khi recording vẫn tiếp tục.
- `JFR.stop` dừng recording và lưu dữ liệu ra file.
- `JFR.configure` xem hoặc cấu hình tài nguyên và repository của JFR.
- `JFR.view` hiển thị các bảng phân tích dựng sẵn từ dữ liệu JFR.

Cần phân biệt hai công cụ:

| Công cụ | Vai trò |
|---|---|
| `jcmd PID JFR.start`, `JFR.dump`, `JFR.stop` | Điều khiển recording bên trong JVM đang chạy. |
| `jfr summary`, `jfr print`, `jfr view` | Đọc và phân tích file recording `.jfr` sau khi đã dump. |

Một quy trình điều tra phổ biến là xác định PID, bắt đầu recording, kiểm tra cấu hình, chụp snapshot hoặc dừng recording, rồi phân tích file bằng công cụ `jfr` hoặc JDK Mission Control.

## 2. Điều kiện để jcmd kết nối tới JVM

Trước khi chạy lệnh JFR, cần xác định đúng tiến trình Java:

~~~bash
jcmd -l
~~~

Output có dạng:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Số đầu tiên là process ID (PID). Dùng PID cụ thể cho các lệnh tiếp theo:

~~~bash
jcmd 18420 help
jcmd 18420 help JFR.start
~~~

Các điều kiện quan trọng:

- `jcmd` chạy trên cùng máy với JVM đích; đây không phải công cụ điều khiển JVM từ xa qua mạng.
- Người chạy `jcmd` thường phải là cùng user/effective user đã khởi chạy JVM đích.
- JVM đích phải cho phép Attach mechanism. Nếu Attach bị tắt, công cụ có thể không kết nối được.
- Tiến trình trong container có thể có PID namespace riêng; cần dùng PID nhìn thấy từ môi trường có quyền attach.
- Các diagnostic command có thể khác nhau theo JDK và JVM vendor. Luôn dùng `jcmd PID help` để xem lệnh mà JVM đích thực sự hỗ trợ.

Không dùng PID 0 một cách tùy tiện. Theo trợ giúp của `jcmd`, PID 0 gửi command tới tất cả Java process có thể nhận lệnh. Với thao tác bắt đầu hoặc dừng recording, hãy chỉ định PID của đúng ứng dụng.

## 3. Xem các JFR command được hỗ trợ

Liệt kê command của một JVM:

~~~bash
jcmd 18420 help
~~~

Xem cú pháp và mức tác động của lệnh cụ thể:

~~~bash
jcmd 18420 help JFR.start
jcmd 18420 help JFR.check
jcmd 18420 help JFR.dump
jcmd 18420 help JFR.stop
jcmd 18420 help JFR.configure
jcmd 18420 help JFR.view
~~~

Trợ giúp của command cho biết:

- Tên và mục đích command.
- Các tham số tùy chọn.
- Giá trị mặc định.
- Định dạng thời gian hoặc đường dẫn được chấp nhận.
- Mức impact dự kiến của command trên JVM.

Ví dụ, trong JDK 24.0.2, `JFR.check` có impact thấp, `JFR.dump` có impact thấp, còn `JFR.start` có impact trung bình và phụ thuộc cấu hình recording. `JFR.view` cũng có thể có impact trung bình.

Mức impact không phải cam kết rằng lệnh luôn không ảnh hưởng hiệu năng. Hãy đọc trợ giúp của đúng JVM đích và chọn event settings phù hợp với thời gian điều tra.

## 4. Bắt đầu recording bằng JFR.start

Cú pháp:

~~~bash
jcmd 18420 JFR.start [options]
~~~

Bắt đầu recording với cấu hình mặc định:

~~~bash
jcmd 18420 JFR.start name=incident-recording settings=default
~~~

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `name` | Đặt tên recording để dùng lại trong `JFR.check`, `JFR.dump` và `JFR.stop`. |
| `settings` | Chọn file cấu hình event, thường là `default`, `profile` hoặc `none`. |
| `duration` | Thời gian ghi; ví dụ `30s`, `5m` hoặc `1h`. Giá trị `0s` nghĩa là ghi không giới hạn thời gian. |
| `delay` | Chờ một khoảng thời gian rồi mới bắt đầu ghi. |
| `filename` | Đường dẫn file recording được ghi khi recording hoàn tất. |
| `maxage` | Giới hạn thời gian dữ liệu được giữ trong disk repository. |
| `maxsize` | Giới hạn dung lượng dữ liệu recording trên disk. |
| `disk` | Cho phép ghi dữ liệu recording ra disk; mặc định là `true`. |
| `dumponexit` | Ghi recording ra file khi JVM shutdown. |
| `path-to-gc-roots` | Thu thập đường dẫn từ object tới GC roots để điều tra memory leak; thao tác này có thể tốn thời gian và gây pause. |

Thời gian có thể dùng đơn vị giây, phút hoặc giờ. Ví dụ:

~~~bash
jcmd 18420 JFR.start name=short-check duration=30s settings=default
jcmd 18420 JFR.start name=delayed-check delay=2m duration=5m settings=default
~~~

Nếu bỏ `duration`, recording chạy cho tới khi được dừng hoặc JVM kết thúc. Hãy đặt `name` rõ ràng khi quản lý nhiều recording cùng lúc.

## 5. Chọn cấu hình default, profile hoặc none

JDK cung cấp các cấu hình JFR mẫu trong thư mục `JAVA_HOME/lib/jfr`:

| Cấu hình | Mục đích | Mức dữ liệu và overhead |
|---|---|---|
| `default.jfc` | Theo dõi liên tục hoặc quan sát production trong thời gian dài. | Ít overhead hơn, tập trung vào thông tin thiết yếu. |
| `profile.jfc` | Điều tra hiệu năng trong một khoảng thời gian ngắn. | Nhiều event và stack trace hơn, overhead cao hơn. |
| `none` | Bắt đầu recording không nạp cấu hình event dựng sẵn. | Chỉ thu thập những event được bật tường minh. |

Ví dụ recording ngắn để điều tra sâu:

~~~bash
jcmd 18420 JFR.start name=profile-incident settings=profile duration=2m
~~~

Ví dụ recording nhẹ để theo dõi lâu hơn:

~~~bash
jcmd 18420 JFR.start name=continuous-monitor settings=default maxage=1h maxsize=512M
~~~

`default` thường phù hợp cho recording kéo dài. `profile` nên dùng có thời hạn khi cần thêm thông tin về allocation, method profiling hoặc contention.

Không chọn `profile` chỉ vì nó thu được nhiều dữ liệu hơn. Event và stack trace chi tiết hơn có thể làm tăng overhead, dung lượng file và chi phí phân tích.

## 6. Giới hạn dung lượng và tự động lưu file

Đối với recording ghi ra disk, có thể đặt giới hạn thời gian và dung lượng:

~~~bash
jcmd 18420 JFR.start name=bounded-recording settings=default maxage=30m maxsize=256M
~~~

- `maxage=30m` giữ tối đa dữ liệu trong khoảng 30 phút.
- `maxsize=256M` giới hạn dữ liệu recording trên disk ở mức 256 MB.
- Các giới hạn này áp dụng khi recording ghi dữ liệu ra disk.
- `maxsize` phải đáp ứng giới hạn tối thiểu theo `maxchunksize` của JFR.

Có thể tự động lưu recording khi JVM shutdown:

~~~bash
jcmd 18420 JFR.start name=shutdown-recording settings=default dumponexit=true
~~~

Nếu không chỉ định filename, JVM tạo tên file chứa PID, recording ID và timestamp trong thư mục làm việc của tiến trình.

Nếu chỉ định filename, các placeholder được hỗ trợ gồm:

- `%p` được thay bằng PID.
- `%t` được thay bằng timestamp theo định dạng `yyyy_MM_dd_HH_mm_ss`.

Ví dụ:

~~~bash
jcmd 18420 JFR.start name=service-recording settings=default filename=recordings/service-%p-%t.jfr dumponexit=true
~~~

Đảm bảo thư mục đích tồn tại và user chạy JVM có quyền ghi. Với recording cần lưu chắc chắn trước khi ứng dụng kết thúc, hãy dùng `JFR.dump` hoặc `JFR.stop` với filename rõ ràng.

## 7. Kiểm tra recording đang chạy bằng JFR.check

Xem tất cả recording hiện tại:

~~~bash
jcmd 18420 JFR.check
~~~

Output có dạng:

~~~text
Recording 1: name=incident-recording maxsize=256.0MB maxage=30m (running)
~~~

Xem chi tiết event settings:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

Lọc theo tên:

~~~bash
jcmd 18420 JFR.check name=incident-recording
~~~

`verbose=true` hiển thị event settings của recording, chẳng hạn event nào đang enabled, threshold bao nhiêu và stack trace có được thu thập hay không.

Nếu command trả về `No available recordings`, có thể recording chưa được bắt đầu, đã tự kết thúc theo duration hoặc đã được dừng. Dùng `JFR.start` để bắt đầu recording mới nếu cần.

## 8. Dump snapshot mà không dừng recording

`JFR.dump` sao chép dữ liệu hiện có của recording ra file. Recording tiếp tục chạy sau khi dump.

Cú pháp cơ bản:

~~~bash
jcmd 18420 JFR.dump name=incident-recording filename=recordings/incident-snapshot.jfr
~~~

Điều này hữu ích khi:

- Cần lấy bằng chứng trước khi sự cố biến mất.
- Muốn phân tích dữ liệu hiện có nhưng vẫn tiếp tục quan sát ứng dụng.
- Muốn tạo nhiều snapshot ở các thời điểm khác nhau.
- Cần lưu một khoảng thời gian của recording dài.

Có thể giới hạn thời gian dữ liệu trong file dump:

~~~bash
# Lấy dữ liệu trong 15 phút gần nhất
jcmd 18420 JFR.dump name=incident-recording begin=-15m filename=recordings/recent-15m.jfr

# Lấy một khoảng thời gian cụ thể
jcmd 18420 JFR.dump name=incident-recording begin=2026-11-10T10:00:00 end=2026-11-10T10:15:00 filename=recordings/incident-window.jfr
~~~

`begin` và `end` có thể dùng local time, timestamp hoặc thời gian tương đối âm như `-15m`, `-30s`. Giá trị được đối chiếu với timestamp bên trong recording.

Dump có thể dùng thêm `maxage` và `maxsize` để giới hạn dữ liệu xuất ra. `path-to-gc-roots=true` có thể bổ sung thông tin hữu ích cho memory leak, nhưng việc thu thập GC roots có thể khiến ứng dụng pause; chỉ bật khi có giả thuyết memory leak cụ thể.

## 9. Dừng recording và lưu dữ liệu bằng JFR.stop

Dừng một recording theo tên và lưu ra file:

~~~bash
jcmd 18420 JFR.stop name=incident-recording filename=recordings/incident-final.jfr
~~~

Output có dạng:

~~~text
Stopped recording "incident-recording", 516.9 kB written to:
recordings/incident-final.jfr
~~~

Có thể dùng recording ID thay cho tên khi cần, nhưng dùng tên dễ đọc giúp script và log dễ theo dõi.

**Luôn chỉ định filename khi cần giữ dữ liệu.** Trợ giúp `JFR.stop` của JDK 24 nêu rằng nếu không cung cấp filename, dữ liệu recording sẽ bị loại bỏ khi dừng.

Sau khi dừng:

~~~bash
jcmd 18420 JFR.check
~~~

Recording đã dừng sẽ không còn xuất hiện trong danh sách active recordings. File đã lưu có thể được phân tích độc lập với JVM.

## 10. Tùy chỉnh event khi bắt đầu recording

`JFR.start` cho phép thay đổi cấu hình event trực tiếp bằng cú pháp:

~~~text
<event-name>#<setting-name>=<value>
~~~

Ví dụ giảm threshold cho event lock contention:

~~~bash
jcmd 18420 JFR.start name=lock-investigation settings=default jdk.JavaMonitorEnter#threshold=1ms
~~~

Bật thêm stack trace cho event:

~~~bash
jcmd 18420 JFR.start name=lock-stacks settings=default jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true
~~~

Để thêm cấu hình cho một event tùy chỉnh, đặt dấu `+` trước event name:

~~~bash
jcmd 18420 JFR.start name=custom-event-recording settings=none +com.example.OrderProcessed#enabled=true +com.example.OrderProcessed#stackTrace=true
~~~

Các setting có thể gồm `enabled`, `threshold`, `period` và `stackTrace` tùy event. Không phải event nào cũng hỗ trợ tất cả setting.

JFR có thể nạp nhiều file `.jfc` bằng cách lặp lại tham số `settings`. Khi một tham số command line xung đột với cấu hình trong `.jfc`, tham số command line có độ ưu tiên cao hơn.

Để biết tên event và setting hợp lệ, xem `jcmd PID help JFR.start`, tài liệu `jdk.jfr` và metadata của recording.

## 11. Xem dữ liệu trực tiếp bằng JFR.view

`JFR.view` hiển thị các bảng tổng hợp dựng sẵn trong JVM, không cần dump file trước.

Ví dụ:

~~~bash
# Các thông tin GC
jcmd 18420 JFR.view gc

# Các method tiêu tốn CPU theo sampling
jcmd 18420 JFR.view hot-methods

# Phân bổ object theo class
jcmd 18420 JFR.view allocation-by-class

# Contention theo thread
jcmd 18420 JFR.view contention-by-thread
~~~

Có thể thay đổi độ rộng và hiển thị chi tiết query:

~~~bash
jcmd 18420 JFR.view width=160 hot-methods
jcmd 18420 JFR.view verbose=true allocation-by-class
~~~

Liệt kê các view và event type mà JVM hỗ trợ:

~~~bash
jcmd 18420 JFR.view all-views
jcmd 18420 JFR.view all-events
jcmd 18420 JFR.view types
~~~

Một số view hữu ích khác gồm `gc-pauses`, `thread-count`, `exception-by-type`, `file-reads-by-path`, `socket-reads-by-host` và `memory-leaks-by-class`.

Tên view phụ thuộc JDK. Nếu view không tồn tại, chạy `jcmd PID help JFR.view` để xem danh sách của đúng JVM. View cần có dữ liệu event phù hợp; bảng trống không nhất thiết có nghĩa là JFR bị lỗi.

## 12. Cấu hình tài nguyên và repository bằng JFR.configure

`JFR.configure` quản lý cấu hình tài nguyên JFR của JVM:

~~~bash
jcmd 18420 JFR.configure
~~~

Một số tham số:

| Tham số | Mục đích |
|---|---|
| `memorysize` | Tổng bộ nhớ dành cho JFR buffers. |
| `maxchunksize` | Kích thước tối đa của một data chunk. |
| `repositorypath` | Thư mục repository tạm chứa dữ liệu recording trước khi dump ra file. |
| `dumppath` | Thư mục lưu file dump khi JVM gặp lỗi nghiêm trọng. |
| `stackdepth` | Độ sâu stack trace tối đa. |
| `thread_buffer_size` | Kích thước local buffer cho mỗi thread. |
| `preserve-repository` | Giữ lại repository files sau khi JVM kết thúc. |

Ví dụ xem và điều chỉnh repository:

~~~bash
jcmd 18420 JFR.configure repositorypath=/var/tmp/jfr-repository
~~~

Một số tham số, như `memorysize`, `maxchunksize` và `stackdepth`, không thể thay đổi sau khi JFR đã được khởi tạo. Hãy kiểm tra cấu hình sớm trong vòng đời JVM và đọc trợ giúp trước khi thay đổi trên production.

Không tùy tiện đổi buffer size hoặc stack depth để xử lý recording bị thiếu. Những tham số này có thể ảnh hưởng hiệu năng và mức sử dụng bộ nhớ của JVM.

## 13. Phân tích file bằng công cụ jfr

Sau khi dump hoặc stop recording, dùng công cụ `jfr` để phân tích offline.

Tóm tắt recording:

~~~bash
jfr summary recordings/incident-final.jfr
~~~

Output hiển thị phiên bản recording, số chunk, thời gian bắt đầu, duration và số lượng từng event type.

In một số event cụ thể:

~~~bash
jfr print --events CPULoad,GarbageCollection recordings/incident-final.jfr
~~~

In event theo category:

~~~bash
jfr print --categories "GC,JVM,Java*" recordings/incident-final.jfr
~~~

In dạng JSON:

~~~bash
jfr print --json --events CPULoad recordings/incident-final.jfr
~~~

Xem bảng phân tích dựng sẵn từ file:

~~~bash
jfr view hot-methods recordings/incident-final.jfr
~~~

`jfr summary` giúp kiểm tra file có dữ liệu và event nào được ghi. `jfr print` phù hợp khi cần xem từng event; `jfr view` giúp tổng hợp dữ liệu thành bảng.

## 14. Tạo cấu hình .jfc tùy chỉnh

Khi cần cấu hình event lặp lại nhiều lần, có thể tạo file `.jfc` thay vì truyền nhiều event setting trong từng lệnh.

Dùng wizard tương tác:

~~~bash
jfr configure --interactive
~~~

Hoặc tạo file từ cấu hình đầu vào:

~~~bash
jfr configure --input default.jfc --output incident.jfc jdk.JavaMonitorEnter#threshold=1ms
~~~

Dùng cấu hình vừa tạo:

~~~bash
jcmd 18420 JFR.start name=custom-profile settings=incident.jfc
~~~

File `.jfc` mô tả event nào được bật, threshold, period và stack trace. Hãy lưu cấu hình cùng source control của hệ thống vận hành nếu nó là một phần của quy trình chẩn đoán được chuẩn hóa.

Kiểm tra file cấu hình trên đúng phiên bản JDK mục tiêu. Event hoặc setting có thể khác giữa các bản JDK.

## 15. Ví dụ hoàn chỉnh: điều tra một JVM đang chạy

Tạo ứng dụng mẫu `src/demo/JfrCommandDemo.java`:

~~~java
package demo;

public class JfrCommandDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        long count = 0;

        while (!Thread.currentThread().isInterrupted()) {
            byte[] payload = new byte[32 * 1024];

            synchronized (LOCK) {
                payload[0] = (byte) (count++ & 0xff);
            }

            Thread.sleep(25);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
mkdir -p out recordings
javac --release 17 -d out src/demo/JfrCommandDemo.java
java -cp out demo.JfrCommandDemo
~~~

Trong terminal khác, tìm PID:

~~~bash
jcmd -l
~~~

Giả sử PID là `18420`. Bắt đầu recording:

~~~bash
jcmd 18420 JFR.start name=lesson-recording settings=default maxage=10m maxsize=50M
~~~

Kiểm tra recording:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

Xem dữ liệu live:

~~~bash
jcmd 18420 JFR.view hot-methods
jcmd 18420 JFR.view allocation-by-class
~~~

Dump snapshot và tiếp tục ghi:

~~~bash
jcmd 18420 JFR.dump name=lesson-recording filename=recordings/jfr-snapshot.jfr
~~~

Dừng recording và lưu bản cuối:

~~~bash
jcmd 18420 JFR.stop name=lesson-recording filename=recordings/jfr-final.jfr
~~~

Phân tích file:

~~~bash
jfr summary recordings/jfr-final.jfr
jfr print --events CPULoad,GarbageCollection recordings/jfr-final.jfr
~~~

Kết quả quan sát được trong môi trường kiểm chứng JDK 24.0.2:

- `JFR.start` trả về ID recording.
- `JFR.check verbose=true` hiển thị recording đang chạy và event settings.
- `JFR.dump` tạo snapshot trong khi recording tiếp tục hoạt động.
- `JFR.stop` dừng recording và ghi file cuối.
- `jfr summary` đọc được file với thông tin version, chunk, duration và event count.
- `jfr print` hiển thị dữ liệu của các event được chọn.

Ví dụ dùng một recording có duration để tự dừng:

~~~bash
jcmd 18420 JFR.start name=timed-recording settings=default duration=3s filename=recordings/timed-recording.jfr
~~~

Sau khoảng ba giây, recording tự hoàn tất và file được ghi. Khi đó `JFR.check` không còn liệt kê recording này. Cách này hữu ích khi cần thu thập một cửa sổ thời gian cố định.

## 16. Đọc và xử lý dữ liệu nhạy cảm trong recording

JFR có thể ghi nhiều thông tin môi trường và ứng dụng, ví dụ:

- Command line, JVM flags và system properties.
- Environment variables được ghi trong các event tương ứng.
- Tên thread, class, method và stack trace.
- Đường dẫn file, thông tin I/O và host mạng tùy event được bật.
- Thông tin class loader, module, runtime và cấu hình hệ thống.

File `.jfr` vì vậy có thể chứa dữ liệu nhạy cảm hoặc thông tin nội bộ. Hạn chế quyền truy cập, thời gian lưu trữ và nơi chuyển file; review recording trước khi gửi ra ngoài tổ chức.

Nếu cần loại bỏ event hoặc thread khỏi file trước khi chia sẻ, có thể dùng `jfr scrub`:

~~~bash
jfr scrub --exclude-events "jdk.InitialEnvironmentVariable,jdk.InitialSystemProperty" input.jfr scrubbed.jfr
~~~

Cú pháp và bộ lọc scrub phụ thuộc phiên bản công cụ. Xem `jfr help scrub` trước khi chạy và xác minh file đầu ra bằng `jfr summary`. Scrub không thay thế quy trình phân loại dữ liệu; vẫn phải kiểm tra nội dung còn lại trước khi chia sẻ.

## 17. Mức tác động và lưu ý khi dùng trong production

JFR được thiết kế để hỗ trợ quan sát JVM với overhead thấp ở cấu hình phù hợp, nhưng mức tác động phụ thuộc event settings, thời gian ghi, số lượng stack trace và hoạt động của ứng dụng.

Một số nguyên tắc:

- Bắt đầu với `settings=default` khi theo dõi liên tục.
- Dùng `settings=profile` trong khoảng ngắn để điều tra sâu.
- Giới hạn recording bằng `duration`, `maxage` và `maxsize`.
- Dùng `JFR.check` để xác nhận recording nào đang chạy.
- Dùng `JFR.dump` để lấy snapshot mà không dừng recording.
- Dùng `JFR.stop` với filename rõ ràng để lưu dữ liệu cuối.
- Chỉ bật `path-to-gc-roots` khi điều tra memory leak vì việc thu thập có thể gây pause.
- Không chạy command trên PID 0 nếu không muốn gửi tới nhiều JVM.
- Kiểm tra impact trong `jcmd PID help COMMAND` trước khi dùng command trên hệ thống nhạy cảm về latency.

JFR không phải heap dump. Recording thường có kích thước nhỏ hơn và lưu chuỗi event theo thời gian; heap dump chụp trạng thái heap chi tiết tại một thời điểm và có thể tạo pause đáng kể. Chọn công cụ theo giả thuyết cần kiểm tra.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jcmd -l` không thấy JVM | Khác user, container PID namespace, JVM không attach được hoặc process đã kết thúc. | Kiểm tra user, namespace, PID và Attach mechanism. |
| `AttachNotSupportedException` | JVM tắt attach hoặc môi trường không cho phép attach. | Kiểm tra cấu hình JVM, quyền truy cập và môi trường chạy. |
| `Unknown diagnostic command` | JVM đích không hỗ trợ command hoặc tên command sai. | Chạy `jcmd PID help` và kiểm tra phiên bản JDK. |
| `JFR.start` báo recording đã tồn tại | Tên recording trùng hoặc recording đang chạy. | Chạy `JFR.check`, chọn tên khác hoặc xử lý recording hiện tại. |
| `JFR.check` báo không có recording | Recording chưa bắt đầu, đã hết duration hoặc đã bị dừng. | Chạy `JFR.start` và kiểm tra lại. |
| File dump không tồn tại | Đường dẫn sai, thư mục chưa tồn tại hoặc JVM không có quyền ghi. | Tạo thư mục, kiểm tra quyền và dùng đường dẫn tuyệt đối khi cần. |
| `JFR.stop` không giữ lại dữ liệu | Không chỉ định filename khi dừng. | Chạy lại quy trình và cung cấp `filename=...` trong `JFR.stop`. |
| File JFR quá lớn | Dùng profile, bật quá nhiều event hoặc ghi quá lâu. | Chuyển sang default, giới hạn duration, maxage và maxsize. |
| Recording không có event mong muốn | Event bị tắt, threshold quá cao hoặc không phát sinh trong khoảng ghi. | Kiểm tra `JFR.check verbose=true` và điều chỉnh event setting. |
| `JFR.view` không có dữ liệu | Recording chưa có event phù hợp hoặc view không có trong JDK này. | Kiểm tra recording, event và danh sách bằng `JFR.view all-views`. |
| Recording gây pause dài | Thu thập GC roots hoặc stack trace sâu, event có overhead cao. | Tắt tùy chọn đắt đỏ, dùng cấu hình nhẹ và thu thập trong khoảng ngắn. |
| Không thể phân tích file bằng jfr | File chưa được dump hoàn chỉnh hoặc bị hỏng. | Kiểm tra lại bằng `jfr summary`, dump lại recording và xem lỗi khi ghi file. |

## 19. Checklist trước khi kết thúc phiên điều tra

- Đã xác định đúng PID và user của JVM đích.
- Đã kiểm tra command JFR được hỗ trợ bằng `jcmd PID help`.
- Recording có tên rõ ràng và settings phù hợp mục tiêu.
- Duration, maxage và maxsize phù hợp với cửa sổ điều tra.
- Đã dùng `JFR.check` để xác nhận recording đang chạy.
- Đã dump snapshot nếu cần lưu bằng chứng trong lúc recording tiếp tục.
- Đã dừng recording bằng `JFR.stop` và cung cấp filename.
- File `.jfr` tồn tại và đọc được bằng `jfr summary`.
- Đã kiểm tra event cần thiết bằng `jfr print` hoặc `jfr view`.
- Đã xem xét dữ liệu nhạy cảm trước khi chia sẻ recording.
- Đã dừng recording không còn cần thiết để tránh thu thập ngoài dự kiến.
- Đã ghi lại JDK version, PID, thời gian ghi và cấu hình event cùng kết quả phân tích.

## 20. Tài liệu tham khảo

- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [JDK Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

`jcmd` cung cấp các lệnh JFR để điều khiển recording ngay trên JVM đang chạy: `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `JFR.configure` và `JFR.view`. Hãy chọn settings phù hợp, giới hạn thời gian và dung lượng, lưu recording bằng filename rõ ràng, rồi dùng `jfr` để kiểm tra dữ liệu trước khi kết thúc điều tra.
