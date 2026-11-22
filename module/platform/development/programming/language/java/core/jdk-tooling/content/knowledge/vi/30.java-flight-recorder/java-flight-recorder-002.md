# Bắt đầu recording với Java Flight Recorder

## 1. Recording trong JFR là gì?

Java Flight Recorder (JFR) ghi lại các event xảy ra trong JVM và ứng dụng Java theo thời gian. Một recording có thể chứa dữ liệu về garbage collection, object allocation, CPU sampling, thread, lock contention, class loading, JIT compilation, file I/O, socket I/O và các hoạt động runtime khác.

Mỗi recording là một phiên thu thập dữ liệu có cấu hình riêng. Khi bắt đầu recording, JVM áp dụng event settings đã chọn và bắt đầu lưu event vào bộ nhớ hoặc disk repository. Recording có thể được dừng thủ công hoặc tự kết thúc theo thời lượng đã đặt để tạo file nhị phân `.jfr`.

Bắt đầu recording là bước đầu của quy trình điều tra hiệu năng:

1. Xác định JVM cần quan sát.
2. Chọn thời điểm bắt đầu và cấu hình event.
3. Đặt thời lượng, giới hạn dung lượng và nơi lưu dữ liệu.
4. Xác nhận recording đang chạy.
5. Kết thúc recording và giữ file để phân tích.

Có ba cách phổ biến để bắt đầu:

| Cách | Thời điểm | Công cụ |
|---|---|---|
| Khi JVM khởi chạy | Ngay từ đầu vòng đời ứng dụng. | `-XX:StartFlightRecording` |
| Khi JVM đang chạy | Attach vào process mà không cần restart. | `jcmd PID JFR.start` |
| Từ code Java | Ứng dụng tự điều khiển recording. | `jdk.jfr.Recording` API |

Nếu cần thu thập cả giai đoạn startup, dùng JVM option hoặc Java API trước khi workload bắt đầu. Nếu sự cố xuất hiện sau khi ứng dụng đã chạy lâu, attach bằng `jcmd` thường thuận tiện hơn.

## 2. Điều kiện trước khi bắt đầu recording

Trước khi khởi động recording, xác định đúng JVM và kiểm tra môi trường:

- Dùng JDK có JFR và công cụ `jcmd`, `jfr` phù hợp với runtime.
- JVM đích phải hỗ trợ JFR và không bị tắt tính năng này.
- Khi attach bằng `jcmd`, công cụ phải chạy trên cùng máy với JVM đích.
- User chạy `jcmd` thường phải trùng với user chạy JVM.
- JVM phải cho phép Attach mechanism.
- Trong container, PID nhìn từ host có thể khác PID bên trong container; dùng PID đúng namespace.
- User chạy JVM phải có quyền ghi vào thư mục chứa recording file.

Tìm Java process:

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Số ở đầu dòng thường là PID local. Đối chiếu main class hoặc command line để chọn đúng ứng dụng. Không dùng PID 0 cho thao tác bắt đầu recording trên production vì PID 0 có thể gửi diagnostic command tới nhiều JVM có thể nhận lệnh.

Xác nhận command JFR được JVM hỗ trợ:

~~~bash
jcmd 18420 help JFR.start
jcmd 18420 help JFR.check
jcmd 18420 help JFR.stop
~~~

Trợ giúp của JVM đích là nguồn chính xác cho cú pháp, giá trị mặc định và impact trên đúng phiên bản JDK đang chạy.

## 3. Chọn cấu hình event: default, profile và none

JDK cung cấp các cấu hình mẫu trong thư mục `JAVA_HOME/lib/jfr`:

| Cấu hình | Nội dung | Trường hợp sử dụng |
|---|---|---|
| `default.jfc` | Tập event được chọn sẵn với overhead thấp. | Recording liên tục hoặc quan sát production dài hơn. |
| `profile.jfc` | Thu thập nhiều dữ liệu hơn, thường có sampling và stack trace chi tiết hơn. | Điều tra hiệu năng trong khoảng thời gian ngắn. |
| `none` | Không nạp cấu hình event dựng sẵn. | Tự bật chính xác các event cần thiết. |

Nếu bỏ `settings` trong `JFR.start`, cấu hình mặc định là `default.jfc`.

Ví dụ dùng cấu hình nhẹ:

~~~bash
jcmd 18420 JFR.start name=continuous-observation settings=default
~~~

Ví dụ điều tra sâu trong khoảng ngắn:

~~~bash
jcmd 18420 JFR.start name=short-profile settings=profile duration=2m
~~~

Ví dụ bắt đầu với cấu hình rỗng:

~~~bash
jcmd 18420 JFR.start name=selected-events settings=none
~~~

`default` phù hợp để quan sát thường xuyên vì chỉ bật tập event được chọn để giảm overhead. `profile` ghi thêm dữ liệu, nhưng tăng lượng event, stack trace, dung lượng file và tác động hiệu năng. Không dùng profile vô thời hạn chỉ vì muốn có nhiều dữ liệu hơn.

`none` hữu ích khi chỉ cần một vài event cụ thể. Nếu không bật event, recording có thể chỉ chứa metadata và các event nền tảng; hãy cấu hình event trước khi kỳ vọng file có dữ liệu cần phân tích.

## 4. Cú pháp JFR.start bằng jcmd

Cú pháp tổng quát:

~~~bash
jcmd <pid> JFR.start [options] [event-settings]
~~~

Ví dụ đơn giản:

~~~bash
jcmd 18420 JFR.start
~~~

Ví dụ có tên, cấu hình và thời lượng:

~~~bash
jcmd 18420 JFR.start name=api-investigation settings=default duration=10m
~~~

Các tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| `name` | Tên recording để nhận diện khi kiểm tra hoặc dừng. |
| `settings` | File cấu hình event, ví dụ `default`, `profile`, `none` hoặc đường dẫn tới file `.jfc`. |
| `duration` | Thời lượng ghi. Mặc định `0s` nghĩa là không giới hạn thời gian. |
| `delay` | Khoảng chờ trước khi bắt đầu ghi. |
| `filename` | Đường dẫn file recording khi recording hoàn tất hoặc được dừng. |
| `disk` | Có ghi dữ liệu recording ra disk repository trong lúc chạy hay không; mặc định `true`. |
| `maxage` | Thời gian tối đa giữ dữ liệu trong disk repository. |
| `maxsize` | Dung lượng tối đa giữ trên disk. |
| `dumponexit` | Tự lưu recording khi JVM shutdown. |
| `path-to-gc-roots` | Thu thập đường dẫn từ object tới GC roots khi recording kết thúc. |

`name` là tùy chọn. Nếu không đặt tên, JVM tạo tên tự động và trả về tên/ID trong kết quả command. Đặt tên dễ đọc giúp tránh nhầm recording khi có nhiều phiên cùng chạy.

Ví dụ:

~~~bash
jcmd 18420 JFR.start name=checkout-latency settings=default
jcmd 18420 JFR.start name=allocation-profile settings=profile duration=90s
~~~

JFR cho phép nhiều recording tồn tại đồng thời. Mỗi recording có thể dùng tên, thời lượng và cấu hình khác nhau; tuy nhiên overhead và dung lượng lưu trữ sẽ tăng theo các recording đang hoạt động.

## 5. Đặt thời lượng và thời điểm bắt đầu

### duration

`duration` quyết định recording kéo dài bao lâu:

~~~bash
# Ghi trong 30 giây
jcmd 18420 JFR.start name=quick-check duration=30s settings=default

# Ghi trong 5 phút
jcmd 18420 JFR.start name=service-check duration=5m settings=default

# Ghi trong 1 giờ
jcmd 18420 JFR.start name=long-check duration=1h settings=default
~~~

Đơn vị hợp lệ là giây (`s`), phút (`m`) và giờ (`h`). Giá trị `0s` có nghĩa là recording chạy cho tới khi được dừng hoặc JVM kết thúc.

Nếu chỉ muốn thu thập một cửa sổ sự cố, nên đặt duration cụ thể để recording tự kết thúc. Nếu cần theo dõi liên tục, có thể bỏ duration nhưng phải quản lý dung lượng và thời điểm dừng.

### delay

`delay` trì hoãn thời điểm bắt đầu ghi:

~~~bash
jcmd 18420 JFR.start name=scheduled-profile delay=2m duration=5m settings=profile
~~~

Trong ví dụ, JVM chờ hai phút rồi mới bắt đầu ghi trong năm phút. Delay hữu ích khi muốn chuẩn bị recording trước một đợt tải đã lên lịch hoặc đồng bộ với một thao tác kiểm thử.

Thời gian delay và duration đều dùng hậu tố `s`, `m` hoặc `h`. Khi dùng cả hai, ghi rõ chúng trong command và xác nhận recording bằng `JFR.check`.

### Kết hợp duration với filename

~~~bash
jcmd 18420 JFR.start name=timed-profile settings=profile duration=4s filename=recordings/profile.jfr
~~~

Sau khoảng bốn giây, recording tự hoàn tất và file được ghi. File không nhất thiết xuất hiện ngay khi command bắt đầu; thời điểm ghi file phụ thuộc việc recording kết thúc hoặc được dump.

## 6. Đặt tên và đường dẫn file

Khi cần giữ recording, hãy chỉ định `filename` rõ ràng:

~~~bash
jcmd 18420 JFR.start name=incident settings=default filename=recordings/incident.jfr
~~~

Đường dẫn tương đối được giải quyết trong môi trường của JVM đích. Trong production, nên dùng đường dẫn tuyệt đối để tránh nhầm thư mục làm việc.

JFR hỗ trợ hai placeholder trong filename:

- `%p` được thay bằng PID của JVM.
- `%t` được thay bằng timestamp theo định dạng `yyyy_MM_dd_HH_mm_ss`.

Ví dụ:

~~~bash
jcmd 18420 JFR.start name=service-profile settings=profile duration=3m filename=recordings/service-%p-%t.jfr
~~~

Đảm bảo thư mục đã tồn tại và user chạy JVM có quyền ghi. Với đường dẫn chứa khoảng trắng, đặt giá trị tham số trong dấu nháy phù hợp với shell đang dùng.

Nếu không chỉ định filename, JVM có thể tạo tên file dựa trên PID và ngày giờ theo quy tắc của command và thời điểm lưu. Để quy trình vận hành dễ dự đoán, hãy cung cấp filename rõ ràng.

## 7. Lưu recording khi JVM shutdown

`dumponexit` yêu cầu JVM lưu recording khi shutdown:

~~~bash
jcmd 18420 JFR.start name=shutdown-capture settings=default dumponexit=true
~~~

Mặc định `dumponexit=false`. Nếu bật `true` và không đặt filename, JVM tạo tên file tự động trong thư mục làm việc của process. Có thể đặt filename cụ thể:

~~~bash
jcmd 18420 JFR.start name=shutdown-capture settings=default filename=recordings/shutdown.jfr dumponexit=true
~~~

Tùy chọn này hữu ích khi ứng dụng có thể kết thúc trước lúc người vận hành kịp dump dữ liệu. Tuy nhiên, file chỉ được ghi khi JVM shutdown; nếu process chạy lâu, không thể dùng dumponexit thay cho việc chủ động lưu recording.

Với recording có duration, filename được chỉ định sẽ được dùng khi recording tự kết thúc. Với recording không giới hạn thời gian, có thể dùng `dumponexit` hoặc chủ động dừng và cung cấp filename.

## 8. Giới hạn dung lượng và disk repository

Khi `disk=true`, JFR ghi dữ liệu vào disk repository trong lúc recording chạy. Đây là mặc định và phù hợp cho recording dài hơn.

Có thể giới hạn thời gian và dung lượng dữ liệu được giữ:

~~~bash
jcmd 18420 JFR.start name=bounded-recording settings=default maxage=30m maxsize=256M
~~~

- `maxage=30m` giới hạn dữ liệu được giữ trong repository ở khoảng 30 phút gần nhất.
- `maxsize=256M` giới hạn dung lượng dữ liệu trên disk ở mức 256 MB.
- `maxage=0s` nghĩa là không giới hạn tuổi dữ liệu.
- `maxsize=0` nghĩa là không giới hạn dung lượng.

`maxage` và `maxsize` chỉ hợp lệ khi `disk=true`. `maxsize` hỗ trợ hậu tố `M`/`m` cho megabytes và `G`/`g` cho gigabytes. Giá trị phải không nhỏ hơn `maxchunksize` được cấu hình cho JFR; mặc định trong JDK 24 là 12 MB.

Có thể kiểm tra cấu hình JFR:

~~~bash
jcmd 18420 JFR.configure
~~~

Không đặt maxsize quá thấp so với lượng dữ liệu event cần thu thập. Nếu repository đầy hoặc dữ liệu quá cũ bị loại bỏ, recording có thể không còn chứa cửa sổ thời gian cần điều tra.

## 9. Chọn disk hoặc in-memory recording

Tham số `disk` điều khiển việc ghi dữ liệu ra disk trong lúc recording:

~~~bash
jcmd 18420 JFR.start name=memory-recording settings=default disk=false duration=30s
~~~

Khi `disk=false`, JFR không ghi dữ liệu recording liên tục vào disk repository. Chế độ này phù hợp với recording ngắn và có giới hạn bộ nhớ. Các tùy chọn `maxage` và `maxsize` không hợp lệ khi disk bị tắt.

Khi cần thu thập trong thời gian dài hoặc giữ một cửa sổ dữ liệu ổn định, dùng `disk=true` và đặt giới hạn maxage/maxsize phù hợp. Hãy xem trợ giúp của JFR trên đúng JDK để hiểu giới hạn bộ nhớ và cách xuất dữ liệu của chế độ in-memory trong phiên bản đang dùng.

## 10. Tùy chỉnh event ngay khi bắt đầu recording

Ngoài chọn file settings, `JFR.start` cho phép thay đổi event setting ngay trên command line.

Cú pháp:

~~~text
<event-name>#<setting-name>=<value>
~~~

Ví dụ giảm threshold cho event monitor contention:

~~~bash
jcmd 18420 JFR.start name=lock-profile settings=default jdk.JavaMonitorEnter#threshold=1ms
~~~

Bật stack trace cho event:

~~~bash
jcmd 18420 JFR.start name=lock-stacks settings=default jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true
~~~

Khi dùng `settings=none`, thêm dấu `+` trước event name để tạo event setting mới:

~~~bash
jcmd 18420 JFR.start name=custom-events settings=none +jdk.JavaMonitorEnter#enabled=true +jdk.JavaMonitorEnter#threshold=1ms +jdk.JavaMonitorEnter#stackTrace=true
~~~

Các setting phổ biến gồm:

| Setting | Ý nghĩa |
|---|---|
| `enabled` | Bật hoặc tắt event. |
| `threshold` | Chỉ ghi event có thời gian vượt ngưỡng. |
| `period` | Chu kỳ lấy mẫu cho event hỗ trợ period. |
| `stackTrace` | Thu thập stack trace cùng event. |

Không phải event nào cũng hỗ trợ tất cả setting. Tên event và giá trị hợp lệ phải được kiểm tra theo metadata của JDK đang dùng.

JFR cũng hỗ trợ option mức cấu hình như `gc`, `allocation-profiling`, `method-profiling`, `locking-threshold` và `socket-threshold`. Khi option command line xung đột với setting trong file `.jfc`, tham số command line có độ ưu tiên cao hơn.

## 11. Tạo file cấu hình .jfc tùy chỉnh

Khi cần dùng cùng một tập event nhiều lần, tạo file `.jfc` bằng `jfr configure`.

Ví dụ tăng chi tiết GC và method profiling:

~~~bash
jfr configure gc=high method-profiling=high --output incident.jfc
~~~

Ví dụ cấu hình lock event:

~~~bash
jfr configure jdk.JavaMonitorEnter#threshold=1ms --output locks.jfc
~~~

Bắt đầu recording bằng file vừa tạo:

~~~bash
jcmd 18420 JFR.start name=incident-profile settings=incident.jfc duration=3m
~~~

File cấu hình mô tả event nào được bật, threshold, period và stack trace. Nếu file không nằm trong thư mục `JAVA_HOME/lib/jfr`, truyền đường dẫn tới file:

~~~bash
jcmd 18420 JFR.start name=custom-profile settings=recordings/incident.jfc
~~~

Có thể kết hợp nhiều file settings bằng cách lặp lại tham số `settings`. Dùng file `.jfc` đã được kiểm tra trên đúng phiên bản JDK để tránh event hoặc setting không tương thích.

## 12. Bắt đầu recording ngay khi JVM khởi chạy

JVM option `-XX:StartFlightRecording` bật recording trước khi ứng dụng bắt đầu xử lý workload.

Ví dụ:

~~~bash
java -XX:StartFlightRecording=name=boot-recording,settings=default,duration=3m,filename=recordings/boot.jfr -jar app.jar
~~~

Các giá trị được phân cách bằng dấu phẩy. Có thể đặt `name`, `settings`, `duration`, `filename`, `dumponexit`, `maxage` và `maxsize` theo mục tiêu.

Ví dụ recording ngắn để điều tra startup:

~~~bash
java -XX:StartFlightRecording=name=startup-profile,settings=profile,duration=60s,filename=recordings/startup.jfr -jar app.jar
~~~

Ví dụ theo dõi liên tục và lưu khi process kết thúc:

~~~bash
java -XX:StartFlightRecording=name=continuous,settings=default,dumponexit=true -jar app.jar
~~~

`-XX:StartFlightRecording` phù hợp khi cần bắt đầu thu thập từ trước khi main method chạy. Nếu dùng `jcmd` sau khi ứng dụng đã khởi động, các event xảy ra trước thời điểm attach sẽ không có trong recording.

## 13. Bắt đầu recording bằng Java API

Ứng dụng có thể tạo recording bằng `jdk.jfr.Recording`. Cách này hữu ích khi recording phụ thuộc vào logic ứng dụng hoặc cần bật trong một đoạn code cụ thể.

Các bước chính:

1. Nạp cấu hình bằng `Configuration.getConfiguration("default")`.
2. Tạo `Recording`.
3. Đặt tên và giới hạn thời gian/dung lượng nếu cần.
4. Bật event bổ sung.
5. Gọi `start()` để bắt đầu thu thập.
6. Gọi `stop()` và `dump(Path)` để lưu file.

Ví dụ Java 17:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrApiStartDemo {
    public static void main(String[] args) throws Exception {
        try (Recording recording =
                 new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("api-start-recording");
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);

            recording.enable("jdk.JavaMonitorEnter")
                     .withThreshold(Duration.ofMillis(1))
                     .withStackTrace();

            recording.start();
            System.out.println("API recording started");

            for (int i = 0; i < 20; i++) {
                synchronized (JfrApiStartDemo.class) {
                    Thread.sleep(10);
                }
            }

            recording.stop();
            recording.dump(Path.of(args[0]));
            System.out.println("API recording saved");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out src/JfrApiStartDemo.java
java -cp out JfrApiStartDemo recordings/api-recording.jfr
~~~

Stdout:

~~~text
API recording started
API recording saved
~~~

Trong ví dụ, recording bắt đầu tại `recording.start()`. Event `jdk.JavaMonitorEnter` được bật với threshold 1 ms và stack trace. Sau khi dừng, `recording.dump()` ghi file JFR. Khối try-with-resources đóng recording khi hoàn tất.

Nếu chỉ cần bật recording theo điều kiện trong ứng dụng, có thể gọi `start()` khi điều kiện xảy ra và dừng/dump khi workload kết thúc. Tránh để recording không được đóng hoặc không có giới hạn khi không còn cần thu thập.

## 14. Kiểm tra recording đã bắt đầu

Sau khi dùng `jcmd JFR.start`, xác nhận recording đang chạy:

~~~bash
jcmd 18420 JFR.check
~~~

Output ví dụ:

~~~text
Recording 1: name=incident-recording maxsize=256.0MB maxage=30m (running)
~~~

Xem event settings:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

Verbose output cho biết event nào được bật, threshold, period và stack trace setting. Dùng kết quả này để xác nhận cấu hình trước khi chờ workload cần điều tra.

Nếu không thấy recording:

- Kiểm tra tên hoặc ID được trả về khi start.
- Xem duration có quá ngắn và recording đã tự kết thúc chưa.
- Xác nhận PID là đúng JVM.
- Kiểm tra command có bị từ chối do event setting hoặc file cấu hình không hợp lệ.

Sau khi recording kết thúc và file được ghi, xác nhận file bằng:

~~~bash
jfr summary recordings/incident.jfr
~~~

`jfr summary` cho biết phiên bản file, thời gian, duration, số chunk và số lượng event. Nếu file chưa xuất hiện trong lúc recording vẫn chạy, đó có thể là hành vi bình thường; file thường được hoàn thiện khi recording kết thúc hoặc được dump.

## 15. Ví dụ hoàn chỉnh: attach vào JVM đang chạy

Tạo file `src/JfrStartDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class JfrStartDemo {
    public static void main(String[] args) throws Exception {
        List<byte[]> retained = new ArrayList<>();

        System.out.println("JfrStartDemo ready");

        long until = System.nanoTime() + 30_000_000_000L;
        while (System.nanoTime() < until) {
            retained.add(new byte[64 * 1024]);

            if (retained.size() > 32) {
                retained.remove(0);
            }

            Thread.sleep(10);
        }

        System.out.println("JfrStartDemo complete");
    }
}
~~~

Biên dịch và chạy:

~~~bash
mkdir -p out recordings
javac --release 17 -d out src/JfrStartDemo.java
java -cp out JfrStartDemo
~~~

Stdout:

~~~text
JfrStartDemo ready
JfrStartDemo complete
~~~

Ứng dụng chạy khoảng 30 giây, tạo allocation trong lúc hoạt động. Mở terminal thứ hai và tìm PID:

~~~bash
jcmd -l
~~~

Giả sử PID là `18420`. Bắt đầu recording default:

~~~bash
jcmd 18420 JFR.start name=runtime-default settings=default maxage=2m maxsize=64M filename=recordings/runtime-default.jfr
~~~

Xác nhận recording:

~~~bash
jcmd 18420 JFR.check
~~~

Sau khoảng hai giây, dừng và lưu file:

~~~bash
jcmd 18420 JFR.stop name=runtime-default filename=recordings/runtime-default.jfr
~~~

Phân tích nhanh file:

~~~bash
jfr summary recordings/runtime-default.jfr
~~~

Kết quả đã kiểm chứng trên JDK 24.0.2:

- `JFR.start` trả về recording ID và trạng thái running.
- `JFR.check` liệt kê recording cùng tên và giới hạn dung lượng/thời gian.
- `JFR.stop` ghi file khoảng 244.5 KB trong lần chạy mẫu.
- `jfr summary` đọc được file với duration khoảng hai giây và danh sách event.

Nếu muốn recording tự kết thúc, dùng duration ngay khi start:

~~~bash
jcmd 18420 JFR.start name=runtime-profile settings=profile duration=4s filename=recordings/runtime-profile.jfr
~~~

Sau bốn giây, recording tự hoàn tất và file có thể được kiểm tra bằng `jfr summary`.

## 16. Ví dụ bắt đầu recording lúc startup

Dùng lại chương trình `JfrStartDemo` đã biên dịch:

~~~bash
java -XX:StartFlightRecording=name=startup-recording,settings=default,duration=3s,filename=recordings/startup-recording.jfr -cp out JfrStartDemo
~~~

JFR bắt đầu từ lúc JVM khởi động. Ứng dụng vẫn chạy sau khi recording kết thúc; recording được ghi vào file sau khoảng ba giây.

Xác minh:

~~~bash
jfr summary recordings/startup-recording.jfr
~~~

Trong thử nghiệm JDK 24.0.2, JVM hiển thị thông báo `Started recording 1`, chương trình in `JfrStartDemo ready` và `JfrStartDemo complete`, còn file startup recording được tạo và đọc thành công với duration ba giây.

Cách này phù hợp để ghi nhận startup, class loading ban đầu hoặc các event xảy ra trước khi có thể dùng `jcmd`.

## 17. Tác động hiệu năng và bảo vệ dữ liệu

`JFR.start` có impact được JDK 24 mô tả ở mức Medium; tác động thực tế có thể từ thấp tới cao tùy event settings. Một số nguyên tắc:

- Bắt đầu bằng `settings=default` cho recording dài hoặc theo dõi thường xuyên.
- Dùng `settings=profile` trong khoảng ngắn khi cần nhiều chi tiết hơn.
- Đặt `duration`, `maxage` và `maxsize` để giới hạn dữ liệu.
- Tránh bật quá nhiều event và stack trace khi chưa có giả thuyết điều tra.
- Không tăng stack depth hoặc buffer size tùy tiện.
- Theo dõi dung lượng file và quyền ghi trên disk.
- Xác nhận recording đã kết thúc khi không còn cần thu thập.

`path-to-gc-roots=true` thu thập đường dẫn từ object tới GC roots khi recording kết thúc. Đây là thao tác tốn thời gian; chỉ bật khi nghi ngờ memory leak. Với `settings=profile`, dữ liệu có thể bao gồm stack trace tại nơi object có khả năng bị giữ lại được cấp phát.

Recording có thể chứa command line, JVM flags, system properties, environment variables, tên thread, class, method, stack trace, đường dẫn file và thông tin host tùy event được bật. Bảo vệ file JFR như dữ liệu vận hành nội bộ: giới hạn quyền truy cập, thời gian lưu và nơi chia sẻ.

## 18. Lỗi thường gặp khi bắt đầu recording

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Unknown diagnostic command` | JVM đích không hỗ trợ command hoặc không phải HotSpot phù hợp. | Chạy `jcmd PID help` và kiểm tra JDK/JVM version. |
| `AttachNotSupportedException` | Attach mechanism bị tắt hoặc môi trường không cho attach. | Kiểm tra user, JVM option, PID namespace và quyền truy cập. |
| Không tìm thấy PID | Process đã kết thúc hoặc PID không thuộc namespace đang dùng. | Chạy `jcmd -l` và đối chiếu process. |
| File `.jfc` không tồn tại | Sai đường dẫn hoặc tên cấu hình. | Dùng đường dẫn đầy đủ và xác nhận file đã được tạo. |
| Event setting không hợp lệ | Sai event name, setting name hoặc giá trị. | Kiểm tra event metadata và trợ giúp của JFR. |
| Recording không có event mong muốn | Event bị tắt, threshold quá cao hoặc event không phát sinh. | Dùng `JFR.check verbose=true` và điều chỉnh settings. |
| File không xuất hiện ngay sau start | Recording vẫn đang chạy hoặc chưa được dump/kết thúc. | Kiểm tra `JFR.check`; dùng duration, filename hoặc quy trình stop có filename. |
| Dừng recording nhưng không có file | `JFR.stop` không có filename nên dữ liệu bị loại bỏ. | Dừng với `filename=...` trong `JFR.stop`. |
| `JFR.check` trả về `No available recordings` | Recording chưa bắt đầu, đã hết duration hoặc đã được dừng. | Xác nhận PID và tên recording, sau đó bắt đầu phiên mới nếu cần. |
| Lỗi ghi file | Thư mục không tồn tại hoặc user chạy JVM thiếu quyền ghi. | Tạo thư mục và kiểm tra quyền. |
| `maxsize` bị từ chối | Giá trị nhỏ hơn `maxchunksize`. | Kiểm tra `JFR.configure` và đặt maxsize đủ lớn. |
| Recording dừng trước khi workload xảy ra | Duration quá ngắn hoặc delay/duration đặt sai. | Điều chỉnh delay và duration, xác nhận bằng `JFR.check`. |
| Overhead tăng | Dùng profile quá lâu hoặc bật event/stack trace quá chi tiết. | Quay về default, giảm event và giới hạn thời gian. |

Lưu ý: theo trợ giúp `JFR.stop` của JDK 24, nếu không cung cấp filename khi dừng thì dữ liệu recording sẽ bị loại bỏ. Luôn cung cấp filename khi cần giữ file.

## 19. Checklist trước khi bắt đầu recording trên production

- Đã xác định đúng PID, host/container và JDK version.
- Đã xác nhận JVM hỗ trợ JFR và cho phép attach nếu dùng jcmd.
- Đã chọn đúng thời điểm: startup, runtime attach hoặc Java API.
- Đã chọn `default`, `profile`, `none` hoặc file `.jfc` theo mục tiêu.
- Recording có tên rõ ràng.
- Duration và delay phù hợp cửa sổ cần quan sát.
- Disk, maxage và maxsize phù hợp với thời gian lưu.
- Filename và thư mục đích đã xác định, user chạy JVM có quyền ghi.
- Đã bật dumponexit nếu cần giữ dữ liệu khi JVM shutdown.
- Đã kiểm tra event settings bằng `JFR.check verbose=true` khi attach runtime.
- Đã cân nhắc overhead của profile, stack trace và GC roots.
- File recording được bảo vệ theo chính sách dữ liệu nội bộ.
- Đã có kế hoạch dừng recording và lưu file bằng filename rõ ràng.
- Đã xác nhận file có thể đọc bằng `jfr summary`.

## 20. Tài liệu tham khảo

- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jfr Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [JDK Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

Bắt đầu recording JFR là việc chọn đúng JVM, thời điểm, event settings và giới hạn lưu trữ. Dùng `-XX:StartFlightRecording` khi cần thu thập từ startup, `jcmd PID JFR.start` khi JVM đã chạy, hoặc `jdk.jfr.Recording` khi ứng dụng cần tự điều khiển. Luôn xác nhận recording đang hoạt động, đặt đường dẫn lưu rõ ràng và kiểm tra file sau khi recording kết thúc.
