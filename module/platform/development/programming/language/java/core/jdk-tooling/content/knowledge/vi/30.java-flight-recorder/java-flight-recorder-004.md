# Recording profile trong Java Flight Recorder

## 1. Recording profile là gì?

Java Flight Recorder (JFR) là framework thu thập sự kiện runtime được tích hợp trong JDK. JFR ghi các sự kiện có timestamp về JVM và ứng dụng, ví dụ CPU sampling, method execution, allocation, garbage collection, lock contention, thread, I/O và class loading.

Một **recording profile** là tập hợp cấu hình sự kiện dùng khi tạo JFR recording. Cấu hình quyết định:

- Event nào được bật hoặc tắt.
- Event duration chỉ được ghi khi vượt ngưỡng nào.
- Event định kỳ được lấy mẫu theo chu kỳ nào.
- Event có kèm stack trace hay không.
- Mức độ chi tiết của dữ liệu thu thập.

Trong JDK, cấu hình được lưu dưới dạng file `.jfc` (JFR configuration). File recording kết quả có phần mở rộng `.jfr`. Hai file có vai trò khác nhau: `.jfc` quyết định dữ liệu cần thu thập; `.jfr` chứa dữ liệu đã ghi để phân tích.

Recording profile hữu ích khi cần điều tra có mục tiêu, chẳng hạn tìm method tiêu tốn CPU, vị trí cấp phát object, lock contention hoặc hoạt động GC trong một khoảng thời gian xác định.

## 2. Hai cấu hình có sẵn: default.jfc và profile.jfc

JDK cung cấp hai cấu hình chính trong thư mục:

~~~text
<JAVA_HOME>/lib/jfr/
    default.jfc
    profile.jfc
~~~

`default.jfc` là cấu hình mặc định khi bắt đầu JFR recording mà không chỉ định settings. Cấu hình này thu thập tập dữ liệu cân bằng, overhead thấp và phù hợp với continuous recording.

`profile.jfc` bật nhiều dữ liệu profiling hơn, ví dụ method execution sampling, allocation profiling và các sự kiện runtime chi tiết hơn. Cấu hình này hữu ích khi cần tìm bottleneck trong một khoảng thời gian ngắn; đổi lại, file recording có thể lớn hơn và ảnh hưởng hiệu năng nhiều hơn.

| Tiêu chí | `default.jfc` | `profile.jfc` |
|---|---|---|
| Mục đích | Theo dõi liên tục và điều tra ban đầu | Profiling có mục tiêu |
| Mức dữ liệu | Tập sự kiện cân bằng | Nhiều sự kiện và chi tiết hơn |
| Overhead | Thấp; mô tả của JDK thường dưới 1% | Cao hơn; mô tả của JDK 24 thường khoảng 2% |
| Allocation/method profiling | Cấu hình nhẹ hơn | Chi tiết hơn |
| Thời lượng phù hợp | Có thể chạy liên tục | Nên chạy trong khoảng ngắn |
| Tình huống | Ghi nhận lịch sử gần nhất để phân tích sau | Tìm CPU hotspot, allocation hoặc lock bottleneck |

Các tỷ lệ overhead chỉ là mô tả tham khảo của cấu hình JDK, không phải cam kết cho mọi ứng dụng. Tải CPU, số thread, event được bật, stack trace, collector và phần cứng đều ảnh hưởng chi phí thực tế.

**Cách chọn nhanh:** bắt đầu với `default` để quan sát lâu dài. Khi đã có giả thuyết cần kiểm tra sâu hơn, chạy `profile` trong thời gian ngắn, tái hiện workload rồi dừng recording.

## 3. Hiểu event settings bên trong một profile

Mỗi JFR event có thể có các setting chính:

| Setting | Ý nghĩa |
|---|---|
| `enabled` | Có ghi event hay không |
| `threshold` | Chỉ ghi duration event khi thời lượng đạt ngưỡng |
| `period` | Chu kỳ phát event đối với event định kỳ |
| `stackTrace` | Có gắn stack trace vào event hay không |

Ví dụ:

~~~xml
<event name="jdk.JavaMonitorEnter">
  <setting name="enabled">true</setting>
  <setting name="stackTrace">true</setting>
  <setting name="threshold">10 ms</setting>
</event>
~~~

Cấu hình này ghi sự kiện thread phải chờ lấy Java monitor nếu thời gian chờ vượt 10 ms, đồng thời lưu stack trace để biết vị trí code gây contention.

Một số loại event thường gặp trong profile:

- `jdk.ExecutionSample`: lấy mẫu stack của thread đang thực thi để phân tích CPU/method.
- `jdk.ObjectAllocationSample`: lấy mẫu allocation và stack trace cấp phát object.
- `jdk.JavaMonitorEnter`: ghi nhận thời gian chờ lấy monitor.
- `jdk.ThreadPark` và `jdk.ThreadSleep`: quan sát thread park hoặc sleep.
- `jdk.GarbageCollection` và các GC phase event: phân tích chu kỳ GC và pause.
- `jdk.Compilation`: theo dõi hoạt động JIT compilation.
- `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite`: tìm I/O chậm khi các event này được bật và đạt threshold.

`threshold` thấp hơn có thể ghi nhiều event hơn, giúp thấy các lần chờ ngắn nhưng cũng tăng lượng dữ liệu và overhead. `stackTrace=true` làm event hữu ích hơn cho việc truy ngược code, nhưng có thêm chi phí thu thập và lưu trữ.

## 4. Xem các preset option của profile

Dùng JDK tool để xem các option mà phiên bản đang cài hỗ trợ:

~~~bash
jfr help configure
~~~

Trên JDK 24.0.2 được kiểm tra, `jfr configure` có các option cấp cao sau:

| Option | Giá trị thường dùng | Tác động |
|---|---|---|
| `gc` | `off`, `normal`, `detailed`, `high`, `all` | Tăng chi tiết GC |
| `allocation-profiling` | `off`, `low`, `medium`, `high`, `maximum` | Điều chỉnh mức thu thập allocation |
| `compiler` | `off`, `normal`, `detailed`, `all` | Điều chỉnh dữ liệu compiler |
| `method-profiling` | `off`, `normal`, `high`, `max` | Điều chỉnh method profiling |
| `thread-dump` | `off`, `once`, `60s`, `10s`, `1s` | Bật thread dump định kỳ |
| `exceptions` | `off`, `errors`, `all` | Điều chỉnh dữ liệu exception |
| `memory-leaks` | `off`, `types`, `stack-traces`, `gc-roots` | Tăng dữ liệu phục vụ điều tra leak |
| `locking-threshold` | Timespan như `10ms` | Ngưỡng event lock |
| `file-threshold` | Timespan như `10ms` | Ngưỡng file I/O |
| `socket-threshold` | Timespan như `10ms` | Ngưỡng socket I/O |
| `class-loading` | `true`, `false` | Bật/tắt dữ liệu class loading |

Profile preset của JDK 24 đặt `gc=detailed`, `allocation-profiling=medium`, `compiler=detailed`, `method-profiling=high`, `memory-leaks=stack-traces` và các threshold lock/file/socket thấp hơn `default`. Giá trị preset có thể thay đổi theo phiên bản JDK; hãy đọc `jfr help configure` của chính môi trường đang dùng trước khi dựa vào chúng.

Không nên bật `gc=all` hoặc mọi event chỉ vì muốn “càng nhiều dữ liệu càng tốt”. Một số chế độ có thể tạo nhiều event, tăng dung lượng hoặc làm thay đổi hành vi ứng dụng. Hãy chọn event theo giả thuyết cần kiểm tra.

## 5. Bắt đầu recording với profile bằng jcmd

Có thể bắt đầu recording khi ứng dụng đã chạy mà không cần sửa source code hoặc khởi động lại JVM.

Tìm PID:

~~~bash
jps -l
~~~

Xem cú pháp mà JVM đích hỗ trợ:

~~~bash
jcmd <pid> help JFR.start
~~~

Bắt đầu recording dùng `profile.jfc`, tự kết thúc sau 60 giây và ghi ra file:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
~~~

Trong đó:

- `name=profile` đặt tên recording để dùng khi kiểm tra hoặc dừng.
- `settings=profile` chọn file cấu hình `profile.jfc` trong thư mục JDK.
- `duration=60s` giới hạn thời gian thu thập trong 60 giây.
- `filename=profile.jfr` chỉ định file output.

Nếu không chỉ định `settings`, JFR dùng `default.jfc`. Nếu không chỉ định `duration`, recording tiếp tục cho đến khi được dừng hoặc JVM kết thúc theo cấu hình lưu trữ.

Kiểm tra recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Hiển thị cả event settings:

~~~bash
jcmd <pid> JFR.check name=profile verbose=true
~~~

Khi recording đang chạy, có thể dump snapshot ra file mà không dừng recording:

~~~bash
jcmd <pid> JFR.dump name=profile filename=profile-snapshot.jfr
~~~

Dừng recording thủ công và ghi file:

~~~bash
jcmd <pid> JFR.stop name=profile filename=profile.jfr
~~~

Nếu đã đặt `duration`, JFR tự dừng và ghi file khi hết thời gian. Không cần chạy `JFR.stop` lần nữa sau khi recording đã kết thúc.

## 6. Bắt đầu profile ngay khi JVM khởi động

Nếu cần thu thập từ những giây đầu tiên, có thể cấu hình recording trong lệnh `java`:

~~~bash
java \
  -XX:StartFlightRecording:filename=profile.jfr,settings=profile,duration=60s \
  -jar application.jar
~~~

Các tham số có ý nghĩa tương tự `JFR.start`:

- `filename`: đường dẫn file recording.
- `settings=profile`: dùng profile preset.
- `duration=60s`: tự kết thúc sau 60 giây.

Nếu muốn ghi file khi JVM shutdown, có thể dùng:

~~~bash
java \
  -XX:StartFlightRecording:filename=profile.jfr,settings=profile,dumponexit=true \
  -jar application.jar
~~~

Khi không đặt `duration`, recording có thể tiếp tục đến khi JVM dừng. Với ứng dụng chạy lâu, hãy cân nhắc continuous recording dùng `default` và giới hạn dữ liệu bằng `maxage` hoặc `maxsize`.

## 7. Tạo custom recording profile bằng jfr configure

Hai preset có sẵn thường đủ dùng. Khi cần thu thập theo một giả thuyết cụ thể, hãy tạo file `.jfc` riêng dựa trên preset hiện có.

Ví dụ tạo profile custom từ `profile.jfc`, tăng chi tiết allocation/method và hạ threshold lock xuống 5 ms:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output custom-profile.jfc \
  allocation-profiling=medium \
  method-profiling=high \
  jdk.JavaMonitorEnter#threshold=5ms
~~~

Lệnh này tạo file `custom-profile.jfc` trong thư mục hiện tại. File mới giữ các setting của profile gốc và áp dụng các thay đổi đã chỉ định.

Dùng file custom khi bắt đầu recording:

~~~bash
jcmd <pid> JFR.start \
  name=custom \
  settings=/path/to/custom-profile.jfc \
  duration=60s \
  filename=custom-profile.jfr
~~~

Trên Windows PowerShell, có thể dùng đường dẫn đầy đủ đến file `.jfc`; nếu đường dẫn có khoảng trắng, đặt đối số `settings=...` trong dấu nháy kép.

Có thể chỉnh riêng một event mà không tạo file `.jfc` mới:

~~~bash
jcmd <pid> JFR.start \
  name=lock-profile \
  settings=profile \
  jdk.JavaMonitorEnter#threshold=5ms \
  duration=60s \
  filename=lock-profile.jfr
~~~

Cũng có thể thêm setting cho event bằng cú pháp `+EventName#setting=value` theo hướng dẫn của `jfr configure` và `jcmd JFR.start`. Event custom phải được định nghĩa trong ứng dụng hoặc thư viện; cấu hình chỉ điều khiển cách ghi event, không tự tạo instrumentation trong source code.

**Không sửa trực tiếp `default.jfc` hoặc `profile.jfc` trong JDK.** Hãy tạo file custom riêng hoặc dùng Template Manager của JDK Mission Control để sao chép và chỉnh template. Nhờ vậy cấu hình gốc vẫn có thể được dùng lại và nâng cấp JDK không làm mất các tùy chỉnh.

## 8. Tạo profile tối giản hoặc phối hợp nhiều setting

Nếu muốn bắt đầu từ cấu hình rỗng, `jfr configure` hỗ trợ `--input none`. Ví dụ:

~~~bash
jfr configure \
  --input none \
  --output minimal.jfc \
  +jdk.ExecutionSample#enabled=true \
  +jdk.ExecutionSample#period=20ms
~~~

Cách này chỉ bật những event đã chỉ định, phù hợp khi bạn biết rõ dữ liệu cần thu thập. Cấu hình rỗng không đồng nghĩa với profile chuẩn; nếu thiếu event cần thiết, file recording có thể không trả lời được câu hỏi điều tra.

Có thể phối hợp nhiều file cấu hình:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/default.jfc,team.jfc" \
  --output combined.jfc
~~~

Khi nhiều cấu hình cùng đặt một setting, cấu hình được kết hợp theo thứ tự input và setting được ghi đè theo quy tắc của công cụ. Hãy xem output `--verbose` và kiểm tra file kết quả trước khi dùng trong môi trường thật.

## 9. Recording profile và recording duration

Cấu hình profile và kiểu recording trả lời hai câu hỏi khác nhau:

- **Profile/settings** quyết định event nào và mức chi tiết nào được ghi.
- **Duration/recording mode** quyết định recording chạy trong bao lâu và dữ liệu được lưu như thế nào.

### Time-fixed profiling recording

Đây là recording có thời lượng cố định, ví dụ 30 hoặc 60 giây. Thường dùng `profile.jfc` hoặc custom profile để thu thập nhiều event trong lúc tái hiện lỗi.

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=60s filename=incident.jfr
~~~

Khi hết thời gian, JFR dừng recording và ghi file. Đây là cách phù hợp để tìm CPU hotspot, allocation pressure, lock contention hoặc I/O chậm trong một tình huống có thể tái hiện.

### Continuous recording

Continuous recording thường dùng `default.jfc` để thu thập nền với overhead thấp. Có thể giới hạn dữ liệu lưu trên disk:

~~~bash
jcmd <pid> JFR.start \
  name=continuous \
  settings=default \
  disk=true \
  maxage=1h \
  maxsize=250M \
  dumponexit=true
~~~

`maxage` giới hạn tuổi dữ liệu và `maxsize` giới hạn dung lượng. Các tham số này áp dụng khi recording ghi ra disk. Khi cần lưu snapshot để điều tra:

~~~bash
jcmd <pid> JFR.dump name=continuous filename=recent.jfr
~~~

Continuous recording có thể giữ lại dữ liệu gần nhất để phân tích sau khi sự cố xảy ra. Nếu cần nhiều dữ liệu hơn, có thể dùng profile trong một khoảng ngắn song song với recording nền, nhưng cần đánh giá tổng overhead và dung lượng.

## 10. Phân tích file recording

Sau khi có file `.jfr`, dùng công cụ dòng lệnh để kiểm tra nhanh.

Xem tổng quan recording:

~~~bash
jfr summary profile.jfr
~~~

Xem event và stack trace của lock contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter profile.jfr
~~~

Xem allocation sample:

~~~bash
jfr print --events jdk.ObjectAllocationSample profile.jfr
~~~

Xem execution sample:

~~~bash
jfr print --events jdk.ExecutionSample profile.jfr
~~~

Có thể lọc nhiều event bằng danh sách phân cách dấu phẩy:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample,jdk.JavaMonitorEnter profile.jfr
~~~

Với recording lớn, dùng `jfr summary` trước để biết event nào có mặt và số lượng bao nhiêu. Sau đó lọc event cần thiết thay vì in toàn bộ file ra terminal.

### Phân tích bằng JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện để phân tích recording:

1. Mở file `.jfr` trong JMC.
2. Xem Automated Analysis Results để tìm cảnh báo đáng chú ý.
3. Dùng Threads và Locks để tìm thread bị block, park hoặc chờ monitor.
4. Dùng Method Profiling để tìm method tiêu tốn thời gian.
5. Dùng Memory/Allocation để tìm class và stack trace cấp phát nhiều object.
6. Dùng Garbage Collections để xem pause, heap usage và hoạt động collector.
7. Dùng I/O để xem socket/file operation có thời lượng dài.
8. Mở event chi tiết và kiểm tra timestamp, thread, duration, stack trace và bối cảnh.

Một event riêng lẻ chưa đủ để kết luận nguyên nhân. So sánh timestamp với request latency, log, metrics và workload thực tế trước khi thay đổi code hoặc cấu hình.

## 11. Ví dụ Java 17 hoàn chỉnh: tạo allocation và lock contention

Tạo file `src/demo/RecordingProfileDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Generates allocation and monitor-contention activity for JFR practice. */
public final class RecordingProfileDemo {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile long sink;

    private static void work() {
        while (!Thread.currentThread().isInterrupted()) {
            byte[] temporary = new byte[1024];
            sink += temporary.length;

            synchronized (LOCK) {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        Thread first = new Thread(RecordingProfileDemo::work, "worker-1");
        Thread second = new Thread(RecordingProfileDemo::work, "worker-2");
        first.start();
        second.start();

        System.out.println("READY retainedKiB=" + RETAINED.size() * 256);
        Thread.sleep(120_000);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/demo/RecordingProfileDemo.java
~~~

Mở Terminal 1 và chạy:

~~~bash
java -Xms32m -Xmx128m -cp out demo.RecordingProfileDemo
~~~

Stdout chính xác:

~~~text
READY retainedKiB=2048
~~~

Giữ JVM chạy. Mở Terminal 2 và tìm PID:

~~~bash
jps -l
~~~

Bắt đầu profile recording trong 5 giây:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=5s filename=profile.jfr
~~~

Khi recording kết thúc, xem event summary:

~~~bash
jfr summary profile.jfr
~~~

Xem lock contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter profile.jfr
~~~

Trong lần thử với Azul JDK 24.0.2, recording 5 giây ghi nhận 63 sự kiện `jdk.JavaMonitorEnter`. Output cho thấy thread `worker-1` và `worker-2` thay phiên giữ monitor, thời gian chờ có mẫu khoảng 20–80 ms và stack trace trỏ về `RecordingProfileDemo.work()`. Số event và thời lượng thay đổi theo CPU, scheduling và tải của máy.

Sau khi hoàn tất, quay lại Terminal 1 và nhấn Ctrl+C để dừng ứng dụng.

## 12. Đọc profile để tìm bottleneck

Một số dấu hiệu thường gặp:

| Dữ liệu trong recording | Hướng điều tra |
|---|---|
| `jdk.ExecutionSample` ở cùng stack xuất hiện nhiều | Kiểm tra method chiếm CPU và call path |
| Nhiều `jdk.ObjectAllocationSample` ở một class/stack | Kiểm tra allocation nóng, object tạm và copy không cần thiết |
| `jdk.JavaMonitorEnter` duration dài | Tìm lock owner, thread chờ và vùng synchronized |
| `jdk.SocketRead`/`jdk.SocketWrite` duration dài | Kiểm tra network latency, server phụ thuộc và timeout |
| `jdk.FileRead`/`jdk.FileWrite` duration dài | Kiểm tra storage, file size và I/O đồng bộ |
| GC pause dài hoặc xảy ra dày | Kiểm tra allocation rate, heap pressure và collector |
| `jdk.Compilation` tăng trong warm-up | Xem thời điểm ứng dụng nóng lên và ảnh hưởng đến latency |

Một profile chỉ ghi những event được bật và vượt threshold. Không thấy event trong file không chứng minh hiện tượng không xảy ra; event có thể bị tắt, threshold quá cao, sampling chưa bắt trúng hoặc thời gian recording không bao phủ sự cố.

Để so sánh trước/sau một thay đổi, giữ nguyên workload, thời gian recording và settings. Nếu đổi profile giữa hai lần đo, sự khác biệt trong lượng dữ liệu thu thập có thể làm kết luận sai lệch.

## 13. Dùng path-to-gc-roots khi nghi ngờ memory leak

JFR có tùy chọn thu thập đường tham chiếu từ GC roots:

~~~bash
jcmd <pid> JFR.start \
  name=leak-investigation \
  settings=profile \
  path-to-gc-roots=true \
  duration=60s \
  filename=leak-investigation.jfr
~~~

Dữ liệu này hữu ích khi cần tìm vì sao object vẫn reachable và nơi object tiềm năng gây leak được cấp phát. Với `settings=profile`, JFR có thể ghi kèm stack trace tại vị trí cấp phát của object được theo dõi.

Việc thu thập path to GC roots tốn thời gian và có thể làm JVM pause trong lúc xử lý. Chỉ bật khi đã có nghi ngờ memory leak và chấp nhận chi phí chẩn đoán. Đối với kiểm tra định kỳ, dùng profile thông thường trước.

## 14. Lỗi thường gặp và cách xử lý

### settings=profile không tìm thấy

Kiểm tra JDK đang chạy có thư mục `JAVA_HOME/lib/jfr/profile.jfc` hay không. Dùng `jfr help configure` và `jcmd <pid> help JFR.start` để kiểm tra đúng phiên bản.

### Custom .jfc không được nạp

Dùng đường dẫn đầy đủ trong `settings=/path/to/custom.jfc`. Kiểm tra file tồn tại, XML hợp lệ và user chạy JVM có quyền đọc.

### Recording có rất ít event

Kiểm tra event có `enabled=true`, threshold có quá cao, period có quá dài và workload có tái hiện đúng hiện tượng không. Dùng `jcmd <pid> JFR.check name=profile verbose=true` để xem setting thực tế.

### Recording file quá lớn

Giảm thời lượng, dùng `default` nếu phù hợp, tăng threshold cho event duration, giảm sampling frequency hoặc chỉ bật nhóm event cần thiết. Giới hạn continuous recording bằng `maxage` và `maxsize`.

### Overhead tăng sau khi bật profile

Profile thu thập nhiều dữ liệu hơn default. Rút ngắn thời gian, giảm allocation/method profiling, tăng threshold hoặc quay về default sau khi hoàn tất chẩn đoán.

### Không thấy lock contention

Kiểm tra có thread thực sự chờ monitor hay không, event `jdk.JavaMonitorEnter` có được bật và threshold có phù hợp không. `Thread.sleep` hoặc `Thread.park` không đồng nghĩa với monitor contention.

### jfr print không thấy event

Chạy `jfr summary` để xác nhận event có trong file. Nếu không có, xem lại settings, threshold, thời điểm recording và workload.

### jfr configure báo option không hợp lệ

Danh sách option phụ thuộc phiên bản JDK. Chạy `jfr help configure`, dùng đúng tên option và đúng giá trị được hỗ trợ. Không sao chép preset của JDK mới hơn sang JDK cũ mà chưa kiểm tra.

## 15. Bảo mật và vận hành

JFR recording có thể chứa stack trace, tên class/method, đường dẫn file, thông tin JVM, system properties, environment variables và event do ứng dụng tự định nghĩa. Một số event có thể tiết lộ dữ liệu vận hành hoặc thông tin nhạy cảm.

Trước khi chia sẻ file `.jfr`:

- Rà soát event settings và nội dung recording.
- Giới hạn quyền đọc file và thời gian lưu giữ.
- Dùng kênh chuyển file được tổ chức cho phép.
- Không đưa recording lên dịch vụ công cộng khi chưa kiểm tra dữ liệu.
- Giữ lại JDK version, PID, thời gian, settings và workload để kết quả có thể đối chiếu.

Khi chạy profile trên production, chọn cửa sổ tải phù hợp, giới hạn duration và kiểm tra CPU, disk, memory trước khi bắt đầu. Nếu có thể, tái hiện sự cố trên staging trước khi tăng mức thu thập.

## 16. Checklist chọn và dùng recording profile

- [ ] Hiểu `.jfc` là cấu hình và `.jfr` là file dữ liệu recording.
- [ ] Dùng `default` cho continuous recording hoặc quan sát nền.
- [ ] Dùng `profile` cho profiling có thời lượng giới hạn.
- [ ] Kiểm tra preset và event settings bằng `jfr help configure`.
- [ ] Kiểm tra cú pháp trên JVM đích bằng `jcmd <pid> help JFR.start`.
- [ ] Chọn event dựa trên giả thuyết cần kiểm tra.
- [ ] Điều chỉnh `enabled`, `threshold`, `period` và `stackTrace` khi cần.
- [ ] Tạo custom `.jfc` bằng `jfr configure` hoặc JMC Template Manager.
- [ ] Không sửa trực tiếp `default.jfc` và `profile.jfc`.
- [ ] Đặt `duration` cho profiling recording.
- [ ] Dùng `JFR.check`, `JFR.dump` và `JFR.stop` để quản lý recording đang chạy.
- [ ] Dùng `jfr summary`, `jfr print` hoặc JMC để phân tích.
- [ ] Chỉ bật `path-to-gc-roots` khi nghi ngờ memory leak.
- [ ] Bảo vệ file `.jfr` như dữ liệu vận hành có thể chứa thông tin nhạy cảm.

## 17. Tài liệu tham khảo

- [Oracle JDK 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html): vai trò của `default.jfc`, `profile.jfc`, vị trí file và cách tạo custom configuration.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): cú pháp `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `settings`, `duration` và `path-to-gc-roots`.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): tùy chọn `-XX:StartFlightRecording`, profile settings và startup recording.
- [Oracle JDK 24 — Configure Events and Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html): event settings `enabled`, `threshold`, `period` và `stackTrace`.
- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): time-fixed/continuous recording, template selection và phân tích bằng JMC.

Recording profile giúp điều chỉnh lượng dữ liệu JFR theo câu hỏi chẩn đoán. Chọn `default` cho theo dõi nền, dùng `profile` trong một khoảng ngắn khi cần thêm event và stack trace, rồi tinh chỉnh `.jfc` khi đã biết chính xác dữ liệu cần thu thập.
