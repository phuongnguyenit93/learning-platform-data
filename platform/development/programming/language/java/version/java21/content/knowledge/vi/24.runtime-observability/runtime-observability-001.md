# Thu thập Java Flight Recorder cho ứng dụng Java 21

Java Flight Recorder (JFR) là cơ chế ghi nhận sự kiện runtime được tích hợp trong JDK. JFR thu thập dữ liệu có dấu thời gian về JVM và ứng dụng, chẳng hạn CPU sampling, garbage collection, cấp phát bộ nhớ, thread, lock và I/O. Dữ liệu được lưu thành file `.jfr` để phân tích sau khi sự cố xảy ra hoặc để khảo sát một khoảng thời gian chạy cụ thể.

Với Java 21, có thể bắt đầu recording ngay khi JVM khởi động, yêu cầu một JVM đang chạy ghi recording bằng `jcmd`, hoặc điều khiển recording từ Java code qua `jdk.jfr.Recording`. Cách chọn phụ thuộc mục tiêu: theo dõi nền liên tục, bắt một sự cố đang diễn ra hay chủ động ghi một giai đoạn trong ứng dụng.

## 1. JFR thu thập loại dữ liệu nào?

JFR ghi các event xảy ra trong JVM và ứng dụng. Mỗi event có timestamp; một số event có duration, stack trace hoặc các trường mô tả bổ sung.

| Nhóm | Ví dụ thông tin | Câu hỏi có thể điều tra |
|---|---|---|
| CPU và execution | Thread samples, method stack, CPU load | Thread nào đang tiêu thụ CPU? |
| Garbage collection | GC event, pause, heap summary | Vì sao có pause dài hoặc GC thường xuyên? |
| Allocation và object | Allocation samples, class, stack trace | Object nào được tạo nhiều? |
| Thread và synchronization | Thread state, monitor enter, park | Thread đang chờ lock hoặc chờ tài nguyên ở đâu? |
| I/O | File read/write, socket read/write | Thời gian chờ đến từ filesystem hay mạng? |
| Class loading và compiler | Class load, compilation | Startup hoặc warm-up bị ảnh hưởng bởi điều gì? |
| Application event | Event do ứng dụng tự định nghĩa | Một bước nghiệp vụ cụ thể mất bao lâu? |

JFR là dữ liệu chẩn đoán có cấu trúc, không thay thế log nghiệp vụ, metrics hoặc distributed tracing. Ví dụ, CPU sample là dữ liệu lấy mẫu theo thời điểm, không phải trace đầy đủ của mọi lệnh đã chạy. Nếu cần liên kết một thao tác nghiệp vụ với event runtime, ứng dụng có thể bổ sung custom JFR event hoặc dùng trace/correlation ID phù hợp.

## 2. Chọn cấu hình recording

JDK 21 cung cấp hai cấu hình JFC dựng sẵn trong thư mục `<JAVA_HOME>/lib/jfr`:

| Cấu hình | Mục đích | Đặc điểm |
|---|---|---|
| `default.jfc` hoặc `default` | Theo dõi liên tục, vận hành nền | Thu thập tập event cân bằng với overhead thấp |
| `profile.jfc` hoặc `profile` | Điều tra có mục tiêu trong thời gian ngắn | Thu thập nhiều dữ liệu hơn, có thể ảnh hưởng hiệu năng nhiều hơn |

`default.jfc` là lựa chọn khởi đầu phù hợp cho continuous recording. `profile.jfc` phù hợp khi cần thêm thông tin về CPU, allocation hoặc lock để khoanh vùng vấn đề. Không nên bật profile ở thời gian dài mà không theo dõi dung lượng và tác động lên workload.

Lưu ý: continuous recording dùng `default.jfc` không thu thập heap statistics hoặc allocation profiling. Nếu đang điều tra mức tăng heap hay nơi cấp phát object, cần chọn `profile.jfc` hoặc tạo cấu hình riêng bật đúng event cần thiết; đồng thời theo dõi overhead và dung lượng tăng thêm.

Cấu hình chỉ định event nào được bật và các setting tương ứng, ví dụ:

- `enabled`: có ghi event hay không.
- `threshold`: chỉ ghi duration event khi thời gian vượt ngưỡng.
- `period`: chu kỳ của event dạng sampling hoặc periodic.
- `stackTrace`: có đính kèm stack trace hay không.

Có thể tạo file cấu hình riêng từ cấu hình chuẩn bằng `jfr configure` hoặc JDK Mission Control (JMC). Hãy giữ nguyên file cấu hình có sẵn của JDK và tạo bản tùy chỉnh riêng để dễ kiểm soát thay đổi.

Ví dụ tạo một cấu hình riêng với ngưỡng ghi monitor contention:

~~~bash
jfr configure --input profile.jfc --output app-profile.jfc jdk.JavaMonitorEnter#threshold=5ms
~~~

Sau đó dùng file `app-profile.jfc` làm settings cho recording. Đường dẫn phải trỏ tới file cấu hình có thể đọc được bởi JVM.

## 3. Bắt đầu recording ngay khi ứng dụng khởi động

Dùng `-XX:StartFlightRecording` khi muốn thu thập dữ liệu từ lúc JVM bắt đầu chạy. Cách này hữu ích khi điều tra startup, warm-up hoặc lỗi xảy ra rất sớm.

Ví dụ ghi một profile trong 5 phút:

~~~bash
java -XX:StartFlightRecording=name=startup-profile,settings=profile,duration=5m,filename=recordings/startup.jfr -jar app.jar
~~~

Các tham số quan trọng:

- `name`: tên recording để nhận diện trong các lệnh điều khiển.
- `settings`: cấu hình event, ví dụ `default` hoặc `profile`.
- `duration`: thời lượng recording; khi hết thời lượng, recording dừng.
- `filename`: file JFR được ghi khi recording dừng.
- `dumponexit`: yêu cầu ghi recording ra file khi JVM shutdown.
- `maxage` và `maxsize`: giới hạn lượng dữ liệu giữ lại khi recording ghi ra disk.

Nếu cần giữ dữ liệu nền trong 6 giờ gần nhất và dump khi JVM shutdown:

~~~bash
java -XX:StartFlightRecording=name=continuous,settings=default,disk=true,maxage=6h,maxsize=512m,dumponexit=true,filename=recordings/continuous.jfr -jar app.jar
~~~

`maxage` và `maxsize` giúp giới hạn dữ liệu giữ lại. Khi đạt giới hạn, JFR loại bỏ các chunk cũ để dành chỗ cho dữ liệu mới. Đây là cách duy trì cửa sổ dữ liệu gần nhất thay vì để file tăng vô hạn.

`dumponexit` hữu ích khi JVM kết thúc bình thường. Không nên coi nó là bảo đảm rằng file cuối cùng luôn được ghi đầy đủ khi process bị kill cưỡng bức, máy chủ mất điện hoặc storage gặp lỗi.

## 4. Bắt đầu recording trên JVM đang chạy bằng jcmd

Khi ứng dụng đã chạy, không cần khởi động lại chỉ để bắt đầu JFR. Dùng `jcmd` đi kèm JDK 21.

Trước hết, tìm process Java:

~~~bash
jcmd -l
~~~

Sau đó dùng PID của ứng dụng để bắt đầu recording:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile
~~~

Ví dụ này để recording chạy cho đến khi chủ động dump hoặc stop. Nếu muốn tự dừng sau một khoảng thời gian và ghi file khi kết thúc, có thể thêm `duration=5m filename=/tmp/incident.jfr`.

Kiểm tra recording đang chạy:

~~~bash
jcmd <PID> JFR.check name=incident verbose=true
~~~

Nếu muốn recording tiếp tục chạy nhưng cần lấy ngay một snapshot dữ liệu gần đây, dùng `JFR.dump`:

~~~bash
jcmd <PID> JFR.dump name=incident filename=/tmp/incident-snapshot.jfr maxage=10m
~~~

`JFR.dump` ghi dữ liệu ra file và recording vẫn tiếp tục. Điều này hữu ích khi muốn chụp dữ liệu trong lúc sự cố đang xảy ra rồi tiếp tục theo dõi.

Khi muốn dừng recording và ghi file cuối cùng:

~~~bash
jcmd <PID> JFR.stop name=incident filename=/tmp/incident-final.jfr
~~~

Các lệnh `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop` có tác động thấp theo phân loại của tài liệu `jcmd`. Dù vậy, hãy chọn thời lượng, cấu hình và nơi lưu phù hợp với tải thực tế.

`jcmd` cần chạy trên cùng máy với JVM và thông thường phải dùng cùng effective user/group đã khởi chạy JVM. Với ứng dụng trong container, hãy chạy công cụ trong môi trường container/PID namespace phù hợp và bảo đảm user có quyền attach tới process.

Nếu không chắc cú pháp của một lệnh trên bản JDK đang chạy, hỏi chính JVM:

~~~bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
~~~

## 5. Phân biệt JFR.start, JFR.dump và JFR.stop

Ba lệnh này có vòng đời khác nhau:

| Lệnh | Tác dụng | Recording sau lệnh |
|---|---|---|
| `JFR.start` | Bắt đầu một recording mới | Đang chạy |
| `JFR.dump` | Ghi dữ liệu hiện có ra file | Vẫn tiếp tục chạy |
| `JFR.stop` | Dừng recording và có thể ghi ra file | Đã dừng |

Nếu `JFR.stop` không có đích file trong lệnh hoặc cấu hình recording, dữ liệu có thể bị loại bỏ khi recording đóng. Vì vậy, trong quy trình điều tra, hãy chỉ rõ `filename` khi muốn lưu file.

Có thể kiểm tra toàn bộ recording đang hoạt động bằng:

~~~bash
jcmd <PID> JFR.check
~~~

Đặt tên recording rõ ràng như `startup`, `incident-2026-11-16` hoặc `baseline` giúp phân biệt nhiều recording cùng JVM.

## 6. Continuous recording và cửa sổ dữ liệu gần nhất

Continuous recording thường chạy với `default.jfc`, ghi dữ liệu ra disk repository và giới hạn lịch sử bằng tuổi dữ liệu hoặc dung lượng.

Ví dụ khởi động ứng dụng với cửa sổ dữ liệu 6 giờ:

~~~bash
java -XX:StartFlightRecording=name=runtime-history,settings=default,disk=true,maxage=6h,maxsize=512m -jar app.jar
~~~

Khi phát hiện latency tăng, dump một khoảng dữ liệu gần thời điểm hiện tại:

~~~bash
jcmd <PID> JFR.dump name=runtime-history filename=/var/log/app/incident.jfr maxage=30m
~~~

Cần phân biệt:

- Disk repository là vùng JFR dùng để lưu các chunk trong khi recording hoạt động.
- File JFR là bản recording được dump ra để lưu trữ hoặc phân tích.
- `maxage`/`maxsize` giới hạn dữ liệu còn được giữ trong recording; chúng không tự tạo một file archive vĩnh viễn cho mọi lần dump.

Nếu muốn thay đổi thư mục repository, có thể cấu hình `-XX:FlightRecorderOptions` khi khởi động JVM. Chọn filesystem có dung lượng và quyền truy cập phù hợp; tránh để repository chiếm đầy volume chứa dữ liệu ứng dụng.

## 7. Điều khiển recording từ Java code

Khi ứng dụng cần tự bắt đầu hoặc dừng recording theo một mốc nghiệp vụ, có thể dùng API `jdk.jfr`.

Ví dụ ghi một khoảng ngắn bằng cấu hình `default`:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

static Path captureRecording() throws IOException {
    Path directory = Path.of("recordings");
    Files.createDirectories(directory);

    Path output = directory.resolve("application.jfr");

    try (Recording recording =
             new Recording(Configuration.getConfiguration("default"))) {

        recording.setName("application-diagnostic");
        recording.setMaxAge(Duration.ofMinutes(30));
        recording.setMaxSize(256L * 1024 * 1024);

        recording.start();

        // Thực hiện hoặc chờ phần workload cần quan sát.
        runWorkloadToObserve();

        recording.stop();
        recording.dump(output);
    }

    return output;
}
~~~

`Recording` hỗ trợ cấu hình, bắt đầu, dừng và dump dữ liệu. Ví dụ trên dừng recording trước khi ghi file. API cũng cho phép dump khi recording đang chạy; nếu muốn lấy snapshot mà không dừng recording, cần thiết kế vòng đời recording phù hợp và giới hạn dung lượng dữ liệu.

Không nên để mọi request tự tạo một recording riêng. Recording tạo thêm dữ liệu và chi phí quản lý; nên điều khiển bằng một cơ chế vận hành có quyền truy cập hạn chế, theo khoảng thời gian hoặc điều kiện rõ ràng.

## 8. Phân tích file JFR bằng công cụ đi kèm JDK

JDK 21 có công cụ dòng lệnh `jfr` trong thư mục `<JAVA_HOME>/bin`. Một số lệnh hữu ích:

Xem thống kê tổng quan:

~~~bash
jfr summary incident.jfr
~~~

Xem danh sách view có sẵn:

~~~bash
jfr view all-views incident.jfr
~~~

Xem các event theo view:

~~~bash
jfr view <view-name> incident.jfr
~~~

In một số event cụ thể:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample incident.jfr
~~~

In event liên quan đến virtual thread:

~~~bash
jfr print --events jdk.VirtualThreadPinned incident.jfr
~~~

In metadata của các event trong recording:

~~~bash
jfr metadata incident.jfr
~~~

`jfr summary` giúp kiểm tra recording có dữ liệu hay không, số lượng event và dung lượng từng nhóm. `jfr print` hữu ích khi cần lọc event cụ thể hoặc xuất JSON/XML để xử lý tiếp. Với recording lớn, tránh in toàn bộ event ra terminal vì output có thể rất lớn; hãy lọc theo event hoặc category.

## 9. Phân tích bằng JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện trực quan cho file JFR. JMC không nằm trong cài đặt JDK thông thường; cài đặt riêng phiên bản tương thích với môi trường cần phân tích.

Quy trình cơ bản:

1. Mở JMC.
2. Mở file recording JFR.
3. Xem Automated Analysis Results để nhận gợi ý ban đầu.
4. Chọn vùng thời gian có vấn đề.
5. Kiểm tra các trang Code, Memory, Garbage Collections, Threads, Locks và I/O.
6. Đi từ biểu đồ tổng quan tới event và stack trace cụ thể.
7. Đối chiếu thời điểm event với log, metrics và trace của ứng dụng.

Ví dụ cách định hướng:

| Triệu chứng | Khu vực JMC nên xem |
|---|---|
| CPU tăng nhưng throughput không tăng | CPU usage, Execution Samples, Code |
| GC pause dài | Garbage Collections, Heap, Allocation |
| Request chậm và nhiều thread chờ | Threads, Locks, I/O |
| Monitor contention | Locks, Java Monitor Enter |
| Nhiều virtual thread bị pin | Virtual thread events, Threads và stack trace |
| Startup chậm | Class Loading, Compilation, Code |

Không kết luận chỉ từ một biểu đồ. Ví dụ CPU load thấp có thể đi cùng latency cao nếu request đang chờ database hoặc network. Cần kết hợp event, stack trace, thời gian chờ và metrics của hệ thống phụ thuộc.

## 10. JFR event liên quan đến virtual thread trong Java 21

JFR có các event để quan sát vòng đời và trạng thái pinning của virtual thread:

| Event | Ý nghĩa | Mặc định |
|---|---|---|
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu | Disabled |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc | Disabled |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin lâu hơn threshold | Enabled, threshold mặc định 20 ms |
| `jdk.VirtualThreadSubmitFailed` | Không thể submit hoặc unpark virtual thread | Enabled |

Ví dụ in các event này nếu recording đã bật chúng:

~~~bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed incident.jfr
~~~

`jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` bị tắt mặc định vì số lượng event có thể rất lớn trong workload tạo nhiều virtual thread. Chỉ bật chúng khi cần phân tích vòng đời hoặc số lượng task; hãy theo dõi kích thước recording.

`jdk.VirtualThreadPinned` hữu ích khi điều tra blocking xảy ra trong vùng `synchronized` hoặc native/foreign call trên Java 21. Event chỉ được ghi khi thời gian pin vượt threshold. Không thấy event không đồng nghĩa không có pinning ngắn hơn threshold.

## 11. Tạo cấu hình riêng và kiểm soát độ chi tiết

Nếu cấu hình mặc định không thu thập event cần thiết, hãy tạo JFC riêng. Không sửa trực tiếp `default.jfc` hoặc `profile.jfc` trong thư mục JDK vì cập nhật JDK hoặc thay môi trường có thể làm mất thay đổi.

Ví dụ, bắt đầu từ `profile.jfc` rồi giảm threshold của monitor contention:

~~~bash
jfr configure --input profile.jfc --output app-profile.jfc jdk.JavaMonitorEnter#threshold=5ms
~~~

Dùng cấu hình mới:

~~~bash
jcmd <PID> JFR.start name=lock-investigation settings=/opt/app/jfr/app-profile.jfc duration=3m filename=/var/log/app/locks.jfr
~~~

Cấu hình event cần cân bằng giữa độ chi tiết và chi phí:

- Threshold thấp hơn sẽ ghi nhiều duration event hơn.
- Bật stack trace có thể làm recording lớn hơn và tăng chi phí thu thập.
- Period sampling ngắn hơn tạo nhiều mẫu hơn.
- Bật các event tần suất cao có thể làm file tăng nhanh.

Một recording chỉ có giá trị khi biết cấu hình nào đã tạo ra nó. Hãy lưu tên settings, phiên bản JDK, thời điểm capture và workload đang chạy cùng metadata của incident.

## 12. Overhead, dung lượng và tác động vận hành

JFR được thiết kế để thu thập dữ liệu với overhead thấp, nhưng không có cấu hình nào đảm bảo không ảnh hưởng tới ứng dụng trong mọi workload.

Các yếu tố làm tăng chi phí:

- Dùng `profile.jfc` trong thời gian dài.
- Bật event tần suất cao hoặc giảm threshold quá thấp.
- Thu stack trace cho nhiều event.
- Giữ recording quá lâu hoặc không giới hạn `maxage`/`maxsize`.
- Dump recording lớn vào filesystem chậm hoặc đang gần đầy.
- Thu thập thêm thông tin nặng, ví dụ path to GC roots khi điều tra memory leak.

Một quy trình an toàn:

1. Bắt đầu với `default.jfc` cho continuous recording.
2. Dùng `profile.jfc` trong khoảng thời gian ngắn để điều tra.
3. Đặt giới hạn tuổi và dung lượng dữ liệu.
4. Kiểm tra dung lượng repository và nơi lưu file dump.
5. So sánh latency/throughput trước và trong thời gian capture.
6. Tắt hoặc dừng recording chuyên sâu khi đã có đủ dữ liệu.

Tùy chọn `path-to-gc-root` có thể giúp điều tra object bị giữ lại, nhưng việc thu thập đường dẫn tới GC root có thể làm JVM pause trong một khoảng thời gian. Chỉ bật khi có nghi ngờ memory leak và đã cân nhắc tác động.

## 13. Bảo vệ dữ liệu trong file recording

File JFR có thể chứa thông tin nhạy cảm tùy event được bật và dữ liệu ứng dụng tự ghi vào custom event. Ví dụ: tên thread, class/method, stack trace, hostname, đường dẫn file, thông tin môi trường hoặc dữ liệu do ứng dụng gắn vào event.

Áp dụng các nguyên tắc sau:

- Lưu recording ở thư mục chỉ người vận hành được phân quyền mới đọc.
- Dùng quyền truy cập và mã hóa storage phù hợp với dữ liệu production.
- Không gửi file JFR lên nơi công khai hoặc đính kèm vào ticket mà chưa xem xét nội dung.
- Tránh đưa token, password, session ID hoặc payload nhạy cảm vào custom event.
- Xác định thời gian lưu trữ và xóa file sau khi hoàn thành điều tra.
- Nếu cần lọc event trước khi chia sẻ, có thể dùng `jfr scrub`, sau đó kiểm tra file đã lọc; không coi thao tác scrub là bảo đảm ẩn danh mọi dữ liệu.

JFR hữu ích cho điều tra sự cố, nhưng file recording cần được xử lý như một artifact vận hành có thể chứa dữ liệu nội bộ.

## 14. Quy trình capture khi có incident

Một quy trình ngắn có thể áp dụng khi production có CPU, latency hoặc GC bất thường:

1. Ghi nhận thời điểm bắt đầu và kết thúc hiện tượng theo timezone rõ ràng.
2. Xác định đúng PID và JVM đang phục vụ request lỗi.
3. Kiểm tra recording hiện có bằng `JFR.check`.
4. Nếu đã có continuous recording, dump cửa sổ dữ liệu bao quanh thời điểm incident.
5. Nếu chưa có recording, bắt đầu `JFR.start` với `profile` trong thời gian ngắn nếu vấn đề còn tái diễn.
6. Ghi lại tên file, settings, phiên bản JDK, replica và request/correlation ID liên quan.
7. Dùng `jfr summary` kiểm tra file, sau đó mở bằng JMC hoặc lọc bằng `jfr print`.
8. Đối chiếu findings với metrics, log và trace trước khi thay đổi cấu hình.
9. Dừng recording chuyên sâu và lưu artifact ở nơi được kiểm soát.

Nếu incident đã kết thúc và không có continuous recording, recording bắt đầu sau đó chỉ phản ánh trạng thái mới. Nó không thể khôi phục event đã xảy ra trước thời điểm capture.

## 15. Checklist thu thập JFR cho Java 21

- [ ] Chọn `default.jfc` cho continuous recording và `profile.jfc` cho profiling ngắn hạn.
- [ ] Quyết định bắt đầu recording lúc JVM startup hay khi process đang chạy.
- [ ] Đặt tên recording rõ ràng và lưu file vào vị trí có đủ dung lượng.
- [ ] Dùng `maxage`/`maxsize` để giới hạn lịch sử của continuous recording.
- [ ] Dùng `jcmd JFR.check` để xác minh recording đang hoạt động.
- [ ] Dùng `JFR.dump` nếu muốn lấy snapshot nhưng tiếp tục recording.
- [ ] Dùng `JFR.stop` khi muốn kết thúc recording và ghi file cuối.
- [ ] Dùng `jfr summary`, `jfr view`, `jfr print` hoặc JMC để phân tích.
- [ ] Chỉ bật event chi tiết, stack trace hoặc GC-root path khi có mục tiêu điều tra cụ thể.
- [ ] Theo dõi overhead, disk usage và quyền truy cập file JFR.
- [ ] Đối chiếu kết quả với metrics, logs và traces của cùng khoảng thời gian.
- [ ] Dừng recording chuyên sâu và xóa artifact khi hết thời hạn lưu trữ.

## Tài liệu tham khảo chính thức

- [Java SE 21 Troubleshooting Guide — Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Java SE 21 Tool Specifications — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java SE 21 Tool Specifications — jfr](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Java SE 21 Tool Specifications — java / StartFlightRecording](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 API — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Java SE 21 API — jdk.jfr.Configuration](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Configuration.html)
- [Java SE 21 Flight Recorder API Programmer's Guide — Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [Oracle Java 21 Core Libraries — Virtual Threads and JFR Events](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)

