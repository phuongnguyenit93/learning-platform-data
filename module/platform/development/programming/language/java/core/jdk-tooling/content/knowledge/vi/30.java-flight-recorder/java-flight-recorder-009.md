# Vận hành Java Flight Recorder (JFR) trong production

Java Flight Recorder (JFR) là hệ thống ghi nhận sự kiện bên trong JVM. Nó thu thập dữ liệu runtime theo thời gian như CPU sampling, allocation, garbage collection, lock contention, I/O, exception, class loading, thread và safepoint. File recording có định dạng `.jfr`, có thể phân tích bằng Java Mission Control (JMC), `jfr` command-line tool hoặc các công cụ tương thích.

JFR phù hợp với production vì cấu hình `default.jfc` được thiết kế để thu thập thông tin với overhead thấp và có thể chạy liên tục. Cấu hình `profile.jfc` thu thập chi tiết hơn, nhưng tạo nhiều dữ liệu và có tác động hiệu năng lớn hơn; nên dùng trong khoảng thời gian ngắn khi cần điều tra sâu.

Hai công cụ có vai trò khác nhau:

- `jcmd <PID> JFR.*`: điều khiển recording trên JVM đang chạy.
- `jfr ...`: xem, lọc, cấu hình hoặc xử lý file `.jfr`.

Bài này sử dụng Zulu/OpenJDK 24.0.2 để kiểm tra cú pháp, tùy chọn và một recording thực tế. Các lệnh vẫn cần được xác nhận bằng help của JDK đích vì event và option có thể thay đổi giữa các phiên bản.

## 1. Khi nào nên dùng JFR trong production?

JFR giúp trả lời các câu hỏi về hành vi của JVM trong một khoảng thời gian cụ thể.

| Triệu chứng | Dữ liệu JFR hữu ích |
|---|---|
| CPU tăng cao | Execution samples, hot methods, compiler và thread CPU |
| GC pause hoặc allocation tăng | Garbage collection, heap summary, allocation samples |
| Request chậm hoặc lock contention | Java monitor enter/wait, thread park, stack trace |
| I/O chậm | Socket read/write, file read/write và thời gian event |
| Exception tăng | Exception/error events và stack trace nếu được bật |
| Thread tăng bất thường | Thread start/end, thread count và thread dump events |
| Class loading bất thường | Class load/unload, class loader statistics |
| Virtual thread bị pin | Virtual thread pinned events và stack trace |
| nghi ngờ memory leak | Old object samples và path to GC roots khi cần |

JFR ghi nhận sự kiện trong JVM, không phải distributed trace hoàn chỉnh. Nếu một request chậm do nhiều service, database hoặc message broker, hãy ghép JFR với trace ID, application log, database metrics và telemetry của các service liên quan.

## 2. Mô hình recording: liên tục và theo phiên điều tra

Có hai cách dùng phổ biến.

### 2.1. Continuous recording

Chạy `default` settings trong thời gian dài, giới hạn dữ liệu bằng `maxage` và `maxsize`. JVM giữ recording trong disk repository và loại bỏ dữ liệu cũ khi giới hạn retention bị vượt qua.

Ví dụ:

~~~text
jcmd <PID> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=1G dumponexit=true
~~~

- `name=continuous`: tên recording để tham chiếu ở các lệnh tiếp theo.
- `settings=default`: cấu hình ít overhead, phù hợp với recording liên tục.
- `disk=true`: ghi dữ liệu xuống disk repository trong khi recording chạy.
- `maxage=6h`: chỉ giữ dữ liệu trong khoảng thời gian tối đa được chỉ định.
- `maxsize=1G`: giới hạn dung lượng dữ liệu recording trên disk.
- `dumponexit=true`: ghi recording ra file khi JVM shutdown bình thường.

Continuous recording giúp lưu lại dữ liệu trước thời điểm alert. Khi sự cố xảy ra, có thể dump một cửa sổ thời gian gần đây mà không cần đợi sự cố tái diễn.

`maxage` và `maxsize` chỉ có ý nghĩa khi recording ghi xuống disk. Kiểm tra dung lượng repository và nơi chứa file dump; không đặt retention lớn hơn dung lượng thực tế của volume.

### 2.2. Recording ngắn cho incident

Khi cần thêm chi tiết, dùng `profile` trong thời gian giới hạn:

~~~text
jcmd <PID> JFR.start name=incident settings=profile duration=5m filename=incident.jfr
~~~

`profile.jfc` thường bật nhiều event hơn, tăng mức sampling hoặc giảm threshold so với `default.jfc`. Nó hữu ích khi cần xác định hot method, allocation site, lock wait hoặc I/O chậm. Hãy giới hạn thời gian và dung lượng, sau đó quay lại cấu hình nhẹ hơn.

Không nên chạy nhiều profile recording chồng lên nhau nếu chưa hiểu event set và overhead của từng recording. `JFR.start` có impact Medium; tác động thực tế phụ thuộc cấu hình và workload.

## 3. Chọn `default.jfc` hay `profile.jfc`

JDK cung cấp hai cấu hình phổ biến trong thư mục `JAVA_HOME/lib/jfr`.

| Nhóm cấu hình | `default.jfc` | `profile.jfc` |
|---|---|---|
| Mục tiêu | Quan sát liên tục, overhead thấp | Điều tra ngắn, nhiều chi tiết hơn |
| GC | `normal` | `detailed` |
| Allocation profiling | `low` | `medium` |
| Compiler | `normal` | `detailed` |
| Method profiling | `normal` | `high` |
| Memory leak | `types` | `stack-traces` |
| Locking threshold | `20ms` | `10ms` |
| File/socket threshold | `20ms` | `10ms` |
| Exceptions | `errors` | `errors` |

Các giá trị trên được xác nhận từ `jcmd <PID> help JFR.start` trên JDK 24.0.2. Chúng là cấu hình mặc định của phiên bản được kiểm tra; bản JDK khác có thể thay đổi.

Một số nguyên tắc lựa chọn:

- Bắt đầu bằng `default` khi cần recording liên tục.
- Dùng `profile` trong một cửa sổ ngắn khi cần stack trace và dữ liệu chi tiết hơn.
- Hạ event threshold chỉ khi câu hỏi chẩn đoán cần dữ liệu có thời lượng ngắn hơn.
- Bật stack trace cho event có mục tiêu rõ ràng; stack trace làm tăng kích thước file và chi phí thu thập.
- Không bật tất cả event với tần suất cao chỉ vì có thể bật.

## 4. Khởi động JFR cùng ứng dụng

Có thể cấu hình recording ngay khi JVM khởi chạy:

~~~text
java -XX:StartFlightRecording=name=continuous,settings=default,disk=true,maxage=6h,maxsize=1g,dumponexit=true -jar application.jar
~~~

JVM sẽ bắt đầu recording theo cấu hình đã chỉ định. Cách này hữu ích khi muốn bảo đảm JFR được bật từ lúc service start.

Có thể đặt `filename` để chỉ định nơi ghi file khi recording được dump hoặc dừng:

~~~text
java -XX:StartFlightRecording=name=continuous,settings=default,disk=true,maxage=6h,maxsize=1g,dumponexit=true,filename=/var/log/myapp/jfr/continuous-%p-%t.jfr -jar application.jar
~~~

Trong tên file:

- `%p` được thay bằng PID.
- `%t` được thay bằng timestamp dạng `yyyy_MM_dd_HH_mm_ss`.

Thư mục đích phải tồn tại và user chạy JVM phải có quyền ghi. Trên Windows, dùng đường dẫn phù hợp với môi trường, ví dụ `D:\logs\myapp\jfr`.

Có thể kiểm tra cú pháp startup option trên đúng JDK bằng tài liệu `java` và thử trong môi trường staging trước khi đưa vào deployment manifest.

## 5. Điều khiển recording trên JVM đang chạy bằng `jcmd`

Trước tiên tìm PID:

~~~text
jcmd -l
~~~

Sau đó kiểm tra các command JFR mà JVM hỗ trợ:

~~~text
jcmd <PID> help JFR.start
jcmd <PID> help JFR.check
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
jcmd <PID> help JFR.configure
~~~

### 5.1. Bắt đầu recording

~~~text
jcmd <PID> JFR.start name=incident settings=default
~~~

Recording có thể được cấu hình thêm:

~~~text
jcmd <PID> JFR.start name=incident delay=10s duration=5m settings=profile filename=incident.jfr
~~~

- `delay`: chờ trước khi bắt đầu.
- `duration`: thời gian ghi; `0s` có nghĩa là không giới hạn.
- `settings`: tên profile hoặc đường dẫn file `.jfc`.
- `filename`: file sẽ được ghi khi recording dừng hoặc hoàn tất.

Nếu không chỉ định tên, JVM tạo tên recording tự động. Hãy lưu tên hoặc ID mà command trả về để dùng cho `JFR.check`, `JFR.dump` và `JFR.stop`.

### 5.2. Kiểm tra recording

~~~text
jcmd <PID> JFR.check
jcmd <PID> JFR.check name=incident verbose=true
~~~

`JFR.check` cho biết recording nào đang chạy. `verbose=true` hiển thị event settings; output có thể dài vì bao gồm nhiều event. Khi cần xác nhận một event custom hoặc threshold, lọc output ở phía terminal sau khi command hoàn tất.

### 5.3. Dump dữ liệu mà không dừng recording

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-snapshot.jfr
~~~

Dump tạo một file `.jfr` từ recording hiện tại. Recording vẫn tiếp tục, vì vậy có thể lấy snapshot khi incident đang diễn ra rồi tiếp tục quan sát.

Có thể chỉ lấy một khoảng thời gian:

~~~text
jcmd <PID> JFR.dump name=continuous filename=last-window.jfr begin=-15m end=-5m
~~~

`begin` và `end` chấp nhận thời gian local, ISO timestamp hoặc thời gian tương đối như `-15m`, `-30s`, `-2h`. Ví dụ trên lấy dữ liệu từ 15 phút trước đến 5 phút trước thời điểm dump.

### 5.4. Dừng recording

~~~text
jcmd <PID> JFR.stop name=incident filename=incident-final.jfr
~~~

Khi dừng, chỉ định `filename` nếu muốn giữ dữ liệu thành file. Theo help của JDK 24.0.2, nếu không cung cấp đường dẫn, dữ liệu recording bị loại bỏ khi stop.

Nếu đã dump snapshot trước đó, file snapshot vẫn tồn tại độc lập với recording đang chạy.

## 6. Quản lý dung lượng, repository và retention

JFR dùng repository để lưu các chunk dữ liệu trước khi tạo file recording hoàn chỉnh. Repository mặc định nằm trong thư mục temporary của hệ điều hành.

Các tham số chính của recording:

| Option | Ý nghĩa |
|---|---|
| `disk=true` | Ghi recording xuống disk repository |
| `maxage=1h` | Giới hạn tuổi dữ liệu giữ lại |
| `maxsize=512M` | Giới hạn dung lượng dữ liệu giữ lại |
| `dumponexit=true` | Dump khi JVM shutdown |
| `filename=...` | Đường dẫn file recording khi dump/stop |

`maxsize` phải không nhỏ hơn `maxchunksize` được cấu hình cho JFR. Trên JDK 24.0.2, `maxchunksize` mặc định là 12 MB; ví dụ `maxsize=32M` hợp lệ.

### 6.1. Cấu hình repository và bộ nhớ JFR

Xem cấu hình hiện tại:

~~~text
jcmd <PID> JFR.configure
~~~

Các tùy chọn đáng chú ý:

- `repositorypath`: thư mục chứa repository tạm.
- `dumppath`: thư mục ghi recording khi JVM gặp lỗi nghiêm trọng.
- `memorysize`: tổng bộ nhớ buffer JFR.
- `maxchunksize`: kích thước chunk tối đa.
- `stackdepth`: độ sâu stack trace.
- `thread_buffer_size`: buffer cục bộ của mỗi thread.
- `preserve-repository`: giữ repository sau khi JVM kết thúc.

Ví dụ:

~~~text
jcmd <PID> JFR.configure repositorypath=/var/lib/myapp/jfr-repository dumppath=/var/lib/myapp/jfr-crash preserve-repository=true
~~~

Một số tham số như `memorysize`, `maxchunksize`, `stackdepth` và `thread_buffer_size` không thể thay đổi sau khi JFR đã được khởi tạo. Nếu cần tùy chỉnh các giá trị này, hãy cấu hình sớm trong vòng đời JVM và kiểm tra help của đúng phiên bản.

`preserve-repository=true` có thể giúp điều tra sau crash, nhưng các chunk còn lại sẽ chiếm dung lượng. Cần có quy trình thu thập, kiểm tra và dọn repository sau khi hoàn thành điều tra.

## 7. Tùy chỉnh event và threshold

JFR event có các setting phổ biến:

- `enabled`: bật hoặc tắt event.
- `threshold`: chỉ ghi event có thời lượng đạt ngưỡng.
- `period`: chu kỳ ghi event định kỳ.
- `stackTrace`: có thu thập stack trace hay không.
- `throttle`: giới hạn tần suất event trong một số loại event.

Cú pháp event setting:

~~~text
<event-name>#<setting-name>=<value>
~~~

Ví dụ chỉ ghi monitor contention từ 5 ms trở lên:

~~~text
jcmd <PID> JFR.start name=locks settings=default jdk.JavaMonitorEnter#threshold=5ms
~~~

Có thể tạo `.jfc` riêng để tái sử dụng:

~~~text
jfr configure gc=high method-profiling=high jdk.JavaMonitorEnter#threshold=5ms --output production.jfc
~~~

Khởi chạy recording bằng file vừa tạo:

~~~text
jcmd <PID> JFR.start name=custom-profile settings=C:\diagnostics\production.jfc
~~~

`jfr configure` cũng cho phép thêm event setting mới bằng tiền tố `+`, ví dụ:

~~~text
jfr configure +com.example.OrderEvent#enabled=true +com.example.OrderEvent#stackTrace=true --output app-events.jfc
~~~

Không hạ threshold một cách tùy tiện. Threshold càng thấp thì càng nhiều event được ghi, file có thể lớn hơn và chi phí thu thập tăng. Hãy chọn event dựa trên giả thuyết cần kiểm tra.

## 8. Tạo custom JFR event cho ứng dụng

Ứng dụng có thể định nghĩa event riêng để ghi nhận hoạt động nghiệp vụ. Custom event giúp nối thời gian thực thi của một thao tác với các event JVM như allocation, GC, lock và CPU sample.

Ví dụ file `JfrProdDemo.java`:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderEvent")
@Label("Order Operation")
@Category({"Application", "Orders"})
class OrderEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Order ID")
    long orderId;
}

public final class JfrProdDemo {
    private JfrProdDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("JFR_DEMO_READY");
        long orderId = 0;

        while (true) {
            OrderEvent event = new OrderEvent();
            event.begin();
            event.operation = "reserve";
            event.orderId = ++orderId;

            byte[] payload = new byte[16 * 1024];
            payload[0] = 1;

            event.commit();
            Thread.sleep(100);
        }
    }
}
~~~

`OrderEvent` là duration event vì code gọi `begin()` và `commit()`. JFR ghi thời điểm bắt đầu, duration, field nghiệp vụ, event thread và stack trace nếu setting cho phép.

Biên dịch:

~~~text
javac --release 17 JfrProdDemo.java
~~~

Chạy:

~~~text
java JfrProdDemo
~~~

Stdout:

~~~text
JFR_DEMO_READY
~~~

Mở terminal thứ hai, lấy PID bằng `jcmd -l`, sau đó bật recording và custom event:

~~~text
jcmd <PID> JFR.start name=prod-lab settings=default disk=true maxage=5m maxsize=32M +com.example.OrderEvent#enabled=true +com.example.OrderEvent#stackTrace=true
~~~

Custom event chỉ xuất hiện trong recording nếu event được bật. Có thể kiểm tra bằng:

~~~text
jcmd <PID> JFR.check name=prod-lab verbose=true
~~~

Trong code production, chỉ thêm field cần cho phân tích. Tránh ghi password, token, dữ liệu cá nhân hoặc request body. Nếu tạo event ở đường code có tần suất cao, cân nhắc `event.isEnabled()` và `event.shouldCommit()` trước khi tính toán payload tốn kém.

## 9. Phân tích file `.jfr` bằng command-line tool

Sau khi dump file:

~~~text
jfr summary prod-lab.jfr
~~~

`summary` hiển thị JFR version, thời lượng, số chunk, số lượng event và kích thước theo event type. Dùng để kiểm tra file có dữ liệu trong khoảng thời gian mong muốn và event cần phân tích có được ghi hay không.

In event cụ thể:

~~~text
jfr print --events com.example.OrderEvent prod-lab.jfr
~~~

Lọc các event CPU và GC:

~~~text
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection prod-lab.jfr
~~~

Giới hạn độ sâu stack trace:

~~~text
jfr print --events jdk.JavaMonitorEnter --stack-depth 32 prod-lab.jfr
~~~

Xuất JSON:

~~~text
jfr print --json --events jdk.CPULoad,jdk.GarbageCollection prod-lab.jfr
~~~

Các lệnh hữu ích khác:

~~~text
jfr metadata prod-lab.jfr
jfr view hot-methods prod-lab.jfr
jfr view allocation-by-class prod-lab.jfr
jfr view gc-pauses prod-lab.jfr
~~~

`jfr metadata` hiển thị event metadata và field layout. `jfr view` tạo bảng phân tích có sẵn, ví dụ hot methods, allocation theo class, GC pause hoặc lock contention.

Có thể lọc theo category:

~~~text
jfr print --categories "GC,JVM,Java*" prod-lab.jfr
~~~

Đối với file lớn, tránh in toàn bộ event ra terminal. Bắt đầu bằng `summary` và `view`, sau đó chỉ in event type và khoảng thời gian liên quan.

## 10. Đọc những event thường gặp

| Event | Ý nghĩa khi điều tra |
|---|---|
| `jdk.ExecutionSample` | Stack sample để tìm method tiêu tốn CPU |
| `jdk.ObjectAllocationSample` | Mẫu allocation để tìm class/site cấp phát đáng chú ý |
| `jdk.GarbageCollection` | Sự kiện GC và duration |
| `jdk.GCHeapSummary` | Heap usage quanh các sự kiện GC |
| `jdk.JavaMonitorEnter` | Thời gian chờ monitor |
| `jdk.JavaMonitorWait` | Thread chờ monitor |
| `jdk.ThreadPark` | Thread park, thường liên quan synchronizer hoặc executor |
| `jdk.SocketRead` / `jdk.SocketWrite` | Thời gian socket I/O |
| `jdk.FileRead` / `jdk.FileWrite` | Thời gian file I/O |
| `jdk.JavaExceptionThrow` | Exception được throw khi event được bật |
| `jdk.ClassLoad` | Class loading |
| `jdk.SafepointBegin` | Safepoint và thời gian dừng đồng bộ VM |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin trong native/monitor context theo định nghĩa event |

Allocation sample là dữ liệu lấy mẫu, không phải danh sách đầy đủ từng object allocation. Không cộng số event sample rồi coi đó là tổng số byte được cấp phát. Dùng allocation profiling và các event tương ứng để hiểu xu hướng, sau đó đối chiếu heap/GC metrics.

Với lock contention, xem event duration, thread, stack trace và vị trí code. Một event monitor wait dài có thể do lock owner bận, I/O trong synchronized block hoặc critical section quá rộng.

## 11. Dùng Java Mission Control để phân tích

Java Mission Control (JMC) là công cụ giao diện đồ họa để mở file `.jfr` và phân tích theo các trang chuyên biệt.

Workflow phổ biến:

1. Thu file `.jfr` từ JVM.
2. Mở file bằng JMC.
3. Kiểm tra Overview và recording duration.
4. Xem Automated Analysis để tìm vấn đề nổi bật.
5. Mở các trang JVM Internals, Threads, Memory, Garbage Collections, I/O và Lock Instances theo triệu chứng.
6. Dùng event timeline để tương quan CPU, allocation, GC, lock và I/O.
7. Mở stack trace và quay lại source code.
8. Ghi lại giả thuyết, event evidence, thời điểm và thay đổi cần kiểm chứng.

JMC là công cụ phân tích; nó không tự sửa nguyên nhân trong ứng dụng. Khi so sánh hai recording, hãy giữ workload, JDK version, collector, heap sizing và thời gian ghi tương đương.

## 12. Chụp dữ liệu quanh thời điểm incident

Với continuous recording đã chạy, khi nhận alert có thể kiểm tra recording:

~~~text
jcmd <PID> JFR.check
~~~

Dump 10 phút ngay trước incident:

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-before.jfr begin=-10m
~~~

Nếu cần xem một cửa sổ cụ thể trước thời điểm hiện tại:

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-window.jfr begin=-20m end=-5m
~~~

Nếu cần thêm chi tiết, bắt đầu profile recording trong thời gian ngắn:

~~~text
jcmd <PID> JFR.start name=incident-profile settings=profile duration=3m filename=incident-profile.jfr
~~~

Sau khi điều tra, dừng recording không còn cần:

~~~text
jcmd <PID> JFR.stop name=continuous filename=continuous-final.jfr
~~~

Chỉ dừng continuous recording khi đã lưu snapshot cần thiết và có kế hoạch khôi phục. Nếu chỉ cần dump một phần dữ liệu, dùng `JFR.dump` để recording tiếp tục chạy.

## 13. Thu thập path to GC roots khi nghi ngờ memory leak

JFR có thể thu thập đường dẫn từ object tới GC roots để điều tra vì sao object còn reachable.

Ví dụ:

~~~text
jcmd <PID> JFR.dump name=continuous filename=memory-leak.jfr path-to-gc-roots=true
~~~

Hoặc bật `path-to-gc-roots=true` khi bắt đầu recording theo help của JVM.

Tác vụ này có thể tốn thời gian và làm ứng dụng pause trong một khoảng ngắn. Chỉ bật khi có giả thuyết memory leak và đã đánh giá ảnh hưởng. Không bật liên tục cho mọi production recording.

Kết hợp Old Object Sample, allocation stack trace, heap dump và dominator/retained-size analysis để xác định object nào đang giữ bộ nhớ. JFR path to GC roots bổ sung bằng chứng; nó không thay thế mọi dạng heap analysis.

## 14. Bảo vệ file recording và dữ liệu nhạy cảm

File `.jfr` có thể chứa nhiều thông tin hơn một file log thông thường:

- Initial environment variables và system properties.
- JVM arguments, class path, tên process và thông tin hệ thống.
- Thread name, stack trace, class và method nội bộ.
- File path, socket endpoint, hostname hoặc URL.
- Giá trị field trong custom event do ứng dụng tự ghi.
- Thông tin về tải và hành vi nghiệp vụ tại thời điểm ghi.

Hãy coi `.jfr` là dữ liệu vận hành nhạy cảm:

1. Ghi vào volume có quyền truy cập hạn chế.
2. Mã hóa khi lưu và khi truyền theo chính sách tổ chức.
3. Không đính kèm trực tiếp recording vào ticket hoặc chat công khai.
4. Xác định thời hạn lưu giữ và xóa file sau khi kết thúc điều tra.
5. Redact hoặc scrub event nhạy cảm trước khi chia sẻ.
6. Tránh đưa token, password, request body hoặc dữ liệu cá nhân vào custom event.

Có thể loại một số event nhạy cảm khỏi file trước khi chia sẻ:

~~~text
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty,InitialSecurityProperty original.jfr sanitized.jfr
~~~

Có thể lọc theo event, category hoặc thread:

~~~text
jfr scrub --include-categories "GC,JVM" original.jfr gc-only.jfr
jfr scrub --exclude-threads "health-check*" original.jfr filtered.jfr
~~~

Scrub chỉ loại những event được chọn. Nó không tự nhận diện mọi secret nằm trong stack trace, URL, custom field hoặc các event khác. Hãy kiểm tra file đầu ra trước khi chia sẻ.

## 15. Khôi phục và xử lý file recording

Một số command hữu ích khi vận hành recording:

~~~text
jfr assemble C:\jfr-repository recovered.jfr
~~~

`jfr assemble` ghép các chunk còn lại trong disk repository thành file `.jfr`, hữu ích khi cần xử lý dữ liệu repository sau sự cố.

Chia file lớn thành các phần nhỏ:

~~~text
jfr disassemble --output C:\jfr-parts --max-size 100M large-recording.jfr
~~~

Các file chunk có thể được phân tích riêng hoặc chuyển qua hệ thống lưu trữ. Khi ghép lại, giữ thứ tự và metadata của chunk.

Trước khi xóa repository, xác nhận recording đã được dump và file mở được bằng `jfr summary`.

## 16. Overhead và nguyên tắc vận hành an toàn

JFR được thiết kế cho chẩn đoán production, nhưng không có recording nào hoàn toàn miễn phí.

Tác động phụ thuộc vào:

- Settings profile và số event được bật.
- Sampling frequency và event threshold.
- Có thu stack trace hay không.
- Số thread và tốc độ phát sinh event.
- Thời gian recording và tốc độ ghi disk.
- Kích thước buffer và cấu hình repository.
- Có yêu cầu path to GC roots hay không.

Một số mức impact trong help của JDK 24.0.2:

| Command | Impact được JVM công bố |
|---|---|
| `JFR.start` | Medium, tùy settings có thể từ thấp đến cao |
| `JFR.check` | Low |
| `JFR.dump` | Low |
| `JFR.stop` | Low |
| `JFR.configure` | Low |
| `JFR.view` | Medium |

Để giảm ảnh hưởng:

- Dùng `default` cho recording liên tục.
- Dùng `profile` trong cửa sổ ngắn.
- Đặt `maxage` và `maxsize` theo disk budget.
- Chỉ bật stack trace và event chi tiết khi có mục tiêu.
- Không đặt threshold quá thấp trên event tần suất cao nếu chưa thử nghiệm.
- Không bật path to GC roots trừ khi điều tra memory leak.
- Tránh chạy nhiều recording profile trùng nhau.
- Theo dõi disk usage và kiểm tra file dump sau khi tạo.
- Đánh giá overhead trên staging với workload tương tự production.

Help của JDK 24.0.2 cũng lưu ý khi sửa default event settings, overhead có thể vượt 1%. Không dùng một con số overhead cố định để cam kết cho mọi ứng dụng.

## 17. Troubleshooting

### JVM không hỗ trợ command JFR

**Nguyên nhân:** runtime quá cũ, không có JFR, recording bị tắt hoặc JVM đích không hỗ trợ command được yêu cầu.

**Cách xử lý:** kiểm tra `jcmd <PID> help`, `jcmd <PID> help JFR.start` và JDK vendor/version. Không giả định mọi runtime đều có cùng event set.

### `JFR.start` báo recording đã tồn tại hoặc tên trùng

**Nguyên nhân:** recording cùng tên đang chạy hoặc một recording trước đó chưa dừng.

**Cách xử lý:** chạy `JFR.check`, dùng tên khác hoặc dừng recording cũ sau khi đã lưu dữ liệu cần thiết.

### `JFR.dump` không tìm thấy recording

**Nguyên nhân:** sai tên/ID hoặc recording đã bị dừng.

**Cách xử lý:** kiểm tra `JFR.check`, xác định đúng tên/ID và dùng `JFR.dump name=<recording-name>`.

### Không tìm thấy file `.jfr`

**Nguyên nhân:** JVM ghi file vào working directory khác, `filename` là relative path, quyền ghi không đủ hoặc lệnh stop không chỉ định filename.

**Cách xử lý:** dùng absolute path, kiểm tra quyền và dùng `JFR.dump filename=...` để lưu snapshot rõ ràng.

### File recording quá lớn

**Nguyên nhân:** dùng `profile`, threshold quá thấp, stack trace nhiều hoặc recording kéo dài không giới hạn.

**Cách xử lý:** kiểm tra `JFR.check verbose=true`, giảm event set, tăng threshold, đặt `maxage`/`maxsize` và chỉ ghi chi tiết trong khoảng ngắn.

### Không thấy event mong muốn

**Nguyên nhân:** event chưa enabled, threshold quá cao, recording bắt đầu sau thời điểm xảy ra sự kiện hoặc event không được JVM hỗ trợ.

**Cách xử lý:** kiểm tra event metadata bằng `jfr metadata`, xem settings bằng `JFR.check verbose=true`, bật event và điều chỉnh threshold trước lần capture kế tiếp.

### Custom event không xuất hiện

**Nguyên nhân:** tên `@Name` không khớp setting, event chưa enabled hoặc code chưa gọi `commit()`.

**Cách xử lý:** xác nhận tên event đầy đủ, bật `+com.example.OrderEvent#enabled=true`, kiểm tra `event.isEnabled()` và bảo đảm `commit()` được gọi.

### Recording bị thiếu dữ liệu cuối khi JVM crash

**Nguyên nhân:** JVM không shutdown bình thường để thực hiện `dumponexit`, hoặc disk repository không được giữ lại.

**Cách xử lý:** cấu hình `dumppath`/`preserve-repository` phù hợp, kiểm tra repository sau crash và dùng `jfr assemble` khi có chunk hợp lệ. Không giả định mọi dữ liệu buffer đều có thể phục hồi.

### Recording gây ảnh hưởng hiệu năng

**Nguyên nhân:** settings quá chi tiết, event threshold quá thấp, stack trace quá sâu hoặc recording nhiều event tần suất cao.

**Cách xử lý:** quay lại `default`, giới hạn duration, giảm event set, tăng threshold và kiểm thử lại trên workload tương tự.

### Không thể attach bằng `jcmd`

**Nguyên nhân:** PID sai, khác user, attach mechanism bị tắt, container/PID namespace không phù hợp hoặc process đã kết thúc.

**Cách xử lý:** xác nhận PID trên đúng host/container, chạy dưới user có quyền và kiểm tra `-XX:+DisableAttachMechanism`. Nếu không thể attach, dùng startup recording, GC log hoặc telemetry đã được cấu hình trước.

## 18. Runbook JFR cho production

Một quy trình vận hành có thể áp dụng:

1. Bật continuous recording với `settings=default`, `disk=true`, `maxage` và `maxsize` phù hợp.
2. Xác nhận recording bằng `jcmd <PID> JFR.check`.
3. Theo dõi disk repository và thời hạn lưu trữ.
4. Khi alert xảy ra, ghi nhận timestamp, PID, JDK version, workload và triệu chứng.
5. Dump cửa sổ thời gian trước/sau incident bằng `JFR.dump begin=... end=...`.
6. Nếu cần thêm chi tiết, chạy `profile` trong một khoảng ngắn có giới hạn.
7. Dừng recording incident và lưu file `.jfr`.
8. Chạy `jfr summary` để xác nhận duration và event count.
9. Mở bằng JMC hoặc dùng `jfr view`/`jfr print` để phân tích.
10. Đối chiếu event với application logs, distributed traces và metrics.
11. Ghi lại giả thuyết, bằng chứng, nguyên nhân và thay đổi cần kiểm chứng.
12. Scrub dữ liệu nhạy cảm trước khi chia sẻ và xóa file theo retention policy.

Mỗi recording nên có tên mô tả service, incident hoặc mục tiêu điều tra. Ghi lại thời điểm bắt đầu/kết thúc và settings được dùng để người khác có thể diễn giải kết quả.

## 19. Checklist trước khi bật JFR trong production

- [ ] Đã xác nhận JDK vendor/version và JFR command được hỗ trợ.
- [ ] Đã xác định mục tiêu quan sát: CPU, GC, allocation, lock, I/O hay thread.
- [ ] Đã chọn `default` cho continuous recording hoặc `profile` cho incident ngắn.
- [ ] Đã đặt recording name rõ ràng.
- [ ] Đã giới hạn `maxage`, `maxsize` và disk repository.
- [ ] Đã xác định `repositorypath`, `dumppath` và quyền ghi nếu cần.
- [ ] Đã kiểm tra `dumponexit` và `filename` theo cách shutdown của service.
- [ ] Đã kiểm tra event threshold, stack trace và event enablement.
- [ ] Đã đánh giá overhead trên staging với workload tương tự.
- [ ] Đã có quy trình `JFR.check`, `JFR.dump` và `JFR.stop`.
- [ ] Đã biết cách đọc `.jfr` bằng `jfr summary`, `jfr view`, `jfr print` hoặc JMC.
- [ ] Đã bảo vệ file recording như dữ liệu vận hành nhạy cảm.
- [ ] Custom event không ghi secret, credential hoặc dữ liệu cá nhân.
- [ ] Đã có retention, scrub và cleanup policy.
- [ ] Đã kiểm tra file dump có thể mở được trước khi kết thúc incident.

## 20. Tài liệu tham khảo

- Oracle JDK 24 — Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder.html
- Oracle JDK 24 — JFR Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `jcmd` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — JFR Event Settings: https://docs.oracle.com/en/java/javase/24/jfapi/event-settings.html
- Oracle JDK 24 — Custom Events: https://docs.oracle.com/en/java/javase/24/jfapi/custom-events.html
- Oracle Java Mission Control: https://www.oracle.com/java/technologies/jdk-mission-control.html

JFR trong production nên được vận hành theo hai lớp: continuous recording nhẹ để giữ dữ liệu trước incident và profile recording ngắn để điều tra sâu. `jcmd` điều khiển JVM đang chạy; `jfr` và JMC phân tích file đã thu thập. Giới hạn retention, chọn event theo giả thuyết, bảo vệ file và ghi lại thời điểm capture sẽ giúp biến recording thành bằng chứng có thể sử dụng trong điều tra hiệu năng.