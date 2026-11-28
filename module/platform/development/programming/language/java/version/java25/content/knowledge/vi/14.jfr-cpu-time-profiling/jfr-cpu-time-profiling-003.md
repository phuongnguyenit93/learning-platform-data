# Kiểm tra hỗ trợ nền tảng và điều kiện kích hoạt bộ lấy mẫu CPU

> **Chương:** CPU-time profiling  
> **Phạm vi:** JFR CPU-time profiling trong JDK 25 (JEP 509, experimental).  
> **Mục tiêu:** Xác định runtime có hỗ trợ bộ lấy mẫu CPU-time hay không, bật đúng event `jdk.CPUTimeSample`, chọn mức sampling phù hợp và kiểm tra recording có đủ mẫu để phân tích.

## 1. Xác định đúng bộ lấy mẫu CPU đang nói tới

JDK 25 có hai cách lấy mẫu method cần phân biệt:

- **Execution-time sampling:** event `jdk.ExecutionSample` lấy mẫu các thread đang thực thi Java code tại những khoảng thời gian thực (wall-clock). Nó dùng được trên các nền tảng JFR hỗ trợ, nhưng không cho biết trực tiếp thread đã tiêu thụ bao nhiêu CPU time. Thread đang chờ I/O, ngủ hoặc chờ lock không được lấy mẫu; code đang chạy native cũng không được thể hiện như Java execution sample.
- **CPU-time sampling:** event `jdk.CPUTimeSample` của JEP 509 lấy mẫu theo lượng CPU time thread thực sự tiêu thụ. Cơ chế này dùng Linux per-thread CPU timer và tín hiệu `SIGPROF`, nên có thể ghi sample cho thread đang chạy Java code hoặc native code.

Một method có thể mất 100 ms wall-clock nhưng chỉ tiêu thụ 2 ms CPU vì phần lớn thời gian chờ network. Ngược lại, một method xử lý dữ liệu trong 20 ms có thể tiêu thụ gần hết 20 ms CPU. Execution-time profile và CPU-time profile trả lời hai câu hỏi khác nhau.

| Cơ chế | Event | Cách lấy mẫu | Phạm vi |
|---|---|---|---|
| JFR execution-time sampler | `jdk.ExecutionSample` | Khoảng thời gian thực | Các nền tảng JFR hỗ trợ; chỉ Java code |
| JFR CPU-time sampler | `jdk.CPUTimeSample` | Khoảng CPU time của từng thread | Linux; Java code và native code |
| CPU usage tổng thể | `jdk.CPULoad` | Event CPU load định kỳ | Quan sát JVM và máy, không thay thế method profile |
| CPU load theo thread | `jdk.ThreadCPULoad` | Event CPU load định kỳ theo thread | Quan sát mức sử dụng, không thay thế stack sample CPU-time |

**Điểm cần nhớ:** JEP 509 không thay thế `jdk.ExecutionSample`. Hai event có thể được ghi đồng thời trong cùng recording; mỗi event cho một góc nhìn khác nhau.

## 2. Nền tảng nào hỗ trợ CPU-time sampler?

**Chỉ hỗ trợ Linux.**

Trong JDK 25, CPU-time sampler của JEP 509 chỉ được triển khai trên **Linux**. Tính năng sử dụng CPU-time timer của Linux để phát tín hiệu theo CPU time đã tiêu thụ, thay vì lấy mẫu theo khoảng thời gian thực.

| Môi trường chạy JVM | Hỗ trợ `jdk.CPUTimeSample` trong JDK 25? | Hướng xử lý |
|---|---|---|
| Linux với HotSpot JDK 25 có tích hợp JEP 509 | Có, nếu kernel/runtime hỗ trợ CPU-time timer | Kiểm tra kernel, bật event và xác minh recording |
| Windows | Không | Dùng `jdk.ExecutionSample`, CPU load và công cụ profiling phù hợp Windows |
| macOS | Không | Dùng `jdk.ExecutionSample` hoặc profiler có hỗ trợ macOS |
| Linux container | Có thể, nếu JVM thực sự chạy trên Linux kernel phù hợp | Kiểm tra kernel từ bên trong container và JDK image đang chạy |
| Docker Desktop trên macOS/Windows | Phụ thuộc Linux VM bên dưới container | Kiểm tra `uname` bên trong container; không suy luận từ OS của máy host |
| JVM không phải HotSpot hoặc vendor build không tích hợp JEP 509 | Không thể mặc định là có | Kiểm tra JFR metadata và tài liệu của vendor/build |

JEP 509 dùng cơ chế CPU timer theo thread của Linux. Cơ chế timer CPU-time này đã có trong Linux kernel từ **2.6.12**. Đây là mốc nền tảng của cơ chế kernel; một bản phân phối hiện đại vẫn cần dùng JDK 25 build có JEP 509 và xác minh event thực tế trên runtime mục tiêu.

Không suy luận rằng mọi nền tảng đều hỗ trợ chỉ vì lệnh `java` có thể tạo file JFR. JFR recording thông thường có thể hoạt động trên Windows/macOS trong khi riêng `jdk.CPUTimeSample` không khả dụng ở đó.

## 3. Kiểm tra OS, kernel và JDK trước khi bật

Chạy các lệnh sau **trong đúng môi trường mà JVM ứng dụng sẽ chạy**:

~~~bash
uname -s
uname -r
uname -m
java --version
jcmd -l
~~~

Kết quả mong đợi về nền tảng:

- `uname -s` trả về `Linux`.
- `uname -r` cho biết kernel release; đối chiếu với điều kiện CPU-time timer của Linux.
- `uname -m` ghi lại kiến trúc CPU để đối chiếu với bản JDK được cài.
- `java --version` xác nhận JVM thực tế là JDK 25 hoặc bản mới hơn có tích hợp tính năng.
- `jcmd -l` xác nhận công cụ chẩn đoán có thể nhìn thấy JVM local khi cần điều khiển recording.

Có thể kiểm tra thuộc tính runtime của JVM:

~~~bash
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.vm.name|java.runtime.version|os.name|os.arch'
~~~

Đối chiếu `java.vm.name`, `java.runtime.version`, `os.name` và `os.arch`. Nếu máy có nhiều JDK, dùng đường dẫn tuyệt đối tới đúng bộ `java`, `jcmd` và `jfr` thuộc cùng JDK. Không dùng kết quả của terminal host để kết luận cho một JVM chạy bên trong container.

### Kiểm tra trong container

Ví dụ:

~~~bash
docker exec <container-name> sh -c 'uname -s; uname -r; uname -m; java --version'
~~~

Thay `<container-name>` bằng tên hoặc ID container. Lệnh này kiểm tra môi trường thực sự chứa JVM. Với container, kernel được chia sẻ từ host hoặc từ Linux VM mà container runtime sử dụng; image Linux không mang một kernel độc lập bên trong image.

Nếu `uname -s` không trả về Linux, bộ lấy mẫu CPU-time JEP 509 không phải lựa chọn phù hợp cho runtime đó. Nếu là Linux nhưng event không xuất hiện, tiếp tục kiểm tra JDK build và trạng thái event thay vì chỉ nhìn tên hệ điều hành.

## 4. Các điều kiện cần có để bật bộ lấy mẫu

Trước khi chạy recording, xác nhận các điều kiện sau:

1. JVM chạy trên Linux.
2. JDK 25 HotSpot build có tích hợp JEP 509 (hoặc bản JDK mới hơn có giữ tính năng).
3. Kernel cung cấp per-thread CPU-time timer của Linux; cơ chế này có từ Linux 2.6.12.
4. Recording JFR được khởi chạy hoặc điều khiển trên JVM đó.
5. Event `jdk.CPUTimeSample` được bật tường minh bằng `enabled=true`.
6. Có workload tiêu thụ CPU trong thời gian recording để tạo sample.
7. Sampling throttle được chọn phù hợp với số hardware threads, thời lượng recording và giới hạn dung lượng.

JEP 509 được đánh dấu **experimental**. Các event liên quan mang trạng thái experimental, nhưng **không cần** thêm `-XX:+UnlockExperimentalVMOptions` để bật CPU-time sampler. Cần bật chính event JFR `jdk.CPUTimeSample`.

Đây là một tính năng runtime experimental của HotSpot, không phải Java language preview; không cần `--enable-preview`. Oracle JDK 26 Migration Guide vẫn liệt kê JFR CPU-time profiling là experimental, vì vậy hãy kiểm tra trạng thái event trên đúng JDK mục tiêu và tiếp tục áp dụng quy trình đánh giá experimental khi triển khai.

### Event tắt mặc định

`jdk.CPUTimeSample` không bật mặc định. Chỉ tạo recording bằng `settings=profile` hoặc `settings=default` không phải điều kiện đủ để khẳng định CPU-time sampler đang hoạt động. Hãy đặt rõ:

~~~text
jdk.CPUTimeSample#enabled=true
~~~

Event `jdk.CPUTimeSamplesLost` ghi nhận số sample bị mất do giới hạn nội bộ của sampler. Khi điều tra độ tin cậy của profile, phải kiểm tra cả event này, không chỉ đếm `jdk.CPUTimeSample`.

### Không nhầm với perf_event

JEP 509 dựa trên Linux CPU-time timer và `SIGPROF`; đây không phải quy trình yêu cầu chạy lệnh `perf record` hoặc cài JVMTI profiler bên ngoài. Không bắt đầu bằng việc thay đổi `perf_event_paranoid` hay cấp quyền root để bật JEP 509. Nếu runtime không phát được event, hãy kiểm tra kernel, JDK build, cấu hình recording và môi trường tín hiệu của tiến trình.

## 5. Bật CPU-time sampler khi JVM khởi động

Cách đơn giản nhất là bật event trong tùy chọn JFR lúc khởi động ứng dụng.

~~~bash
java '-XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr' \
  -jar app.jar
~~~

Thay `app.jar` bằng artifact thật. Tùy chọn này bật recording và yêu cầu JFR ghi event CPU-time vào `cpu-time.jfr`.

### Chọn throttle để giới hạn lượng sample

Có thể thêm `throttle` vào event setting:

~~~bash
java '-XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=500/s,filename=cpu-time.jfr' \
  -jar app.jar
~~~

Hoặc dùng khoảng CPU-time cho mỗi thread:

~~~bash
java '-XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms,filename=cpu-time.jfr' \
  -jar app.jar
~~~

Hai cách cấu hình có ý nghĩa khác nhau:

| Giá trị throttle | Ý nghĩa | Hệ quả |
|---|---|---|
| `500/s` | Giới hạn tốc độ phát event ở mức tối đa khoảng 500 event/giây cho recording | Mức trần tổng dễ kiểm soát hơn khi số hardware threads thay đổi |
| `10ms` | Lấy mẫu thread sau mỗi 10 ms CPU time mà thread tiêu thụ | Số event tối đa tăng theo số hardware threads; phù hợp profiling chi tiết hơn nhưng có thể tạo nhiều dữ liệu |

Ví dụ với `10ms`, một thread CPU-bound có thể phát khoảng 100 sample/giây. Trên máy có nhiều hardware threads cùng chạy CPU-bound, tổng event rate có thể tăng đáng kể. Với `500/s`, sampler điều chỉnh chu kỳ theo số hardware threads để giữ giới hạn rate tổng.

Không chọn throttle quá dày ngay trên production. Bắt đầu bằng rate có giới hạn, đo overhead và dung lượng file, sau đó mới tăng độ chi tiết nếu cần.

## 6. Bật event bằng file cấu hình JFR

Nếu muốn lưu cấu hình để tái sử dụng trong CI hoặc môi trường vận hành, tạo một JFC riêng thay vì chỉnh file cấu hình gốc trong JDK.

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output cpu-time-profile.jfc \
  jdk.CPUTimeSample#enabled=true \
  jdk.CPUTimeSample#throttle=500/s
~~~

File `cpu-time-profile.jfc` chứa cấu hình profiling cùng event CPU-time đã bật.

Chạy ứng dụng với cấu hình vừa tạo:

~~~bash
java '-XX:StartFlightRecording:settings=cpu-time-profile.jfc,filename=cpu-time.jfr,duration=60s' \
  -jar app.jar
~~~

Nếu `JAVA_HOME` chưa trỏ tới JDK đang dùng, hãy dùng đường dẫn thật tới thư mục `lib/jfr` của JDK 25. Không sửa trực tiếp `default.jfc` hoặc `profile.jfc`; lưu custom file cùng cấu hình triển khai để có thể kiểm tra và tái tạo.

## 7. Bật recording trên JVM đang chạy

Nếu ứng dụng đã chạy trên Linux/JDK 25, có thể tạo custom JFC trước rồi dùng `jcmd` để bắt đầu recording:

~~~bash
jcmd -l
jcmd <PID> JFR.start settings=/absolute/path/cpu-time-profile.jfc duration=60s filename=cpu-time-live.jfr
~~~

Thay `<PID>` bằng process ID của đúng JVM và thay `/absolute/path/cpu-time-profile.jfc` bằng đường dẫn tuyệt đối tới file JFC mà tiến trình đích có thể đọc. Lệnh `JFR.start` sử dụng cấu hình đã bật `jdk.CPUTimeSample`.

Kiểm tra recording đang chạy:

~~~bash
jcmd <PID> JFR.check
~~~

Sau khi recording kết thúc, file `cpu-time-live.jfr` có thể được đọc bằng `jfr` CLI hoặc JDK Mission Control.

Nếu JVM chạy trong container, chạy `jcmd` trong đúng container hoặc đúng PID namespace và cùng user phù hợp với tiến trình Java. Không dùng PID host thay cho PID trong namespace mà công cụ đang truy cập.

## 8. Xác minh event thật sự được ghi

Không kết luận bộ lấy mẫu hoạt động chỉ vì JVM khởi động thành công hoặc file `.jfr` tồn tại. Sau recording, kiểm tra theo thứ tự:

~~~bash
jfr summary cpu-time.jfr
jfr metadata --events jdk.CPUTimeSample cpu-time.jfr
jfr print --events jdk.CPUTimeSample cpu-time.jfr
jfr print --events jdk.CPUTimeSamplesLost cpu-time.jfr
~~~

Dùng các view chuyên biệt của JDK 25:

~~~bash
jfr view cpu-time-hot-methods cpu-time.jfr
jfr view cpu-time-statistics cpu-time.jfr
~~~

Ý nghĩa:

- `cpu-time-hot-methods`: các method đứng đầu stack nhiều nhất theo CPU-time samples.
- `cpu-time-statistics`: tổng hợp số sample thành công, thất bại, bị bias và bị mất.
- `jdk.CPUTimeSamplesLost`: cho biết sampler đã mất bao nhiêu sample trong các đợt ghi nhận.
- `jdk.CPUTimeSample`: chứa thread, stack trace, sampling period và trạng thái lấy mẫu.

Nếu `jfr metadata` không thấy event `jdk.CPUTimeSample`, kiểm tra JDK build và platform. Nếu metadata có nhưng recording không có event, kiểm tra event đã được bật chưa và workload có thực sự tiêu thụ CPU không.

### Các trường cần quan sát

| Event/field | Ý nghĩa | Cách diễn giải |
|---|---|---|
| `jdk.CPUTimeSample` | Một mẫu stack theo CPU time | Số mẫu tương đối giúp tìm method tiêu thụ CPU |
| `eventThread` | Thread được lấy mẫu | Xác định thread đang tiêu thụ CPU |
| `stackTrace` | Stack tại thời điểm lấy mẫu | Xác định call path dẫn đến hot method |
| `samplingPeriod` | Khoảng CPU-time thực tế dùng cho sample | Kiểm tra throttle thực tế |
| `failed` | Không lấy được stack trace | Sample thất bại không có stack để phân tích |
| `biased` | Sample chịu ảnh hưởng safepoint bias | Cân nhắc khi đánh giá chất lượng profile |
| `jdk.CPUTimeSamplesLost.lostSamples` | Số mẫu bị mất | Tỷ lệ mất cao làm profile kém đầy đủ |

Không diễn giải số sample như số lần gọi method chính xác. Đây là dữ liệu lấy mẫu; method xuất hiện nhiều trong profile cho thấy nó chiếm tỷ trọng CPU đáng kể trong cửa sổ quan sát, không phải một bộ đếm invocation.

## 9. Workload và mức sampling ảnh hưởng tới chất lượng dữ liệu

CPU-time sampler chỉ có dữ liệu hữu ích khi thread thực sự tiêu thụ CPU trong khoảng recording. Một ứng dụng chỉ chờ socket hoặc ngủ có thể tạo rất ít CPU-time samples dù wall-clock time của request dài.

Để kiểm tra cấu hình:

1. Chạy một workload CPU-bound có thời lượng đủ dài trong môi trường test.
2. Bắt đầu recording với `jdk.CPUTimeSample#enabled=true`.
3. Kiểm tra `cpu-time-hot-methods` có các method dự kiến.
4. Kiểm tra `cpu-time-statistics` và `jdk.CPUTimeSamplesLost`.
5. Giảm rate hoặc rút ngắn recording nếu event volume/overhead quá lớn.
6. Lặp lại cùng workload với throttle khác để so sánh độ chi tiết và tác động.

Ví dụ workload đơn giản để tạo CPU activity:

~~~java
public class CpuWorkload {
    static long calculate(long limit) {
        long result = 0;
        for (long i = 1; i < limit; i++) {
            result += (i * 31) ^ (i >>> 3);
        }
        return result;
    }

    public static void main(String[] args) {
        long end = System.nanoTime() + 30_000_000_000L;
        long result = 0;

        while (System.nanoTime() < end) {
            result ^= calculate(2_000_000);
        }

        System.out.println(result);
    }
}
~~~

Biên dịch và chạy trên Linux/JDK 25:

~~~bash
javac CpuWorkload.java
java '-XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=500/s,filename=cpu-workload.jfr' \
  CpuWorkload
~~~

Đây chỉ là workload kiểm tra tính năng; không dùng nó thay cho benchmark ứng dụng thực tế.

### Chọn throttle theo mục đích

| Mục đích | Cấu hình bắt đầu | Lưu ý |
|---|---|---|
| Smoke test xem event có hoạt động | `500/s` | Giữ lượng event ở mức giới hạn |
| Tìm hot method trong một workload ngắn | `10ms` | Dữ liệu chi tiết hơn, theo dõi overhead |
| Quan sát liên tục | Rate giới hạn và recording có max age/max size | Kiểm soát file và overhead |
| Máy nhiều core/thread | Rate tổng như `500/s` | Tránh để số sample tăng tuyến tính quá cao theo hardware threads |

Không có một throttle tối ưu cho mọi ứng dụng. Chọn mức lấy mẫu dựa trên số core, số thread CPU-bound, thời gian recording, overhead cho phép và khả năng lưu trữ.

## 10. Khi không hỗ trợ Linux CPU-time sampler

Trên Windows và macOS, dùng JFR execution-time sampler:

~~~bash
java '-XX:StartFlightRecording:jdk.ExecutionSample#enabled=true,filename=execution-samples.jfr' \
  -jar app.jar
~~~

Sau đó xem sample:

~~~bash
jfr print --events jdk.ExecutionSample execution-samples.jfr
~~~

`jdk.ExecutionSample` là lựa chọn đa nền tảng hơn nhưng có giới hạn: chỉ lấy mẫu thread đang chạy Java code, không phản ánh trực tiếp CPU time đã tiêu thụ và không bao gồm phần native execution theo cách của `jdk.CPUTimeSample`.

Để quan sát mức sử dụng CPU tổng thể, có thể xem `jdk.CPULoad` và `jdk.ThreadCPULoad`. Các event này hữu ích để phân biệt JVM có đang dùng CPU hay không, nhưng chúng không thay thế stack profile theo CPU-time.

| Nhu cầu | Lựa chọn |
|---|---|
| CPU-time method profile trên Linux/JDK 25 | `jdk.CPUTimeSample` |
| Method execution samples trên Linux/Windows/macOS | `jdk.ExecutionSample` |
| JVM CPU và machine CPU load | `jdk.CPULoad` |
| CPU load theo thread | `jdk.ThreadCPULoad` |
| Điều tra native CPU trên nền tảng không hỗ trợ JEP 509 | Chọn profiler ngoài có hỗ trợ nền tảng đó, theo chính sách vận hành |

## 11. Chẩn đoán khi event không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `jdk.CPUTimeSample` không xuất hiện trong metadata | JDK build hoặc platform không hỗ trợ JEP 509 | Xác minh Linux, JDK 25 HotSpot build và event metadata |
| Event có trong metadata nhưng không có mẫu | Event vẫn tắt hoặc workload không tiêu thụ CPU | Bật `jdk.CPUTimeSample#enabled=true`, chạy CPU workload |
| Chạy trên Windows/macOS không có CPU-time samples | JEP 509 chỉ hỗ trợ Linux | Dùng `jdk.ExecutionSample` hoặc profiler tương thích OS |
| Linux container không có event | Kernel trong runtime container hoặc JDK image không đáp ứng | Chạy `uname -s`, `uname -r`, `java --version` ngay trong container |
| Recording có nhiều sample thất bại | Stack chưa lấy được ở một số trạng thái thread hoặc điều kiện runtime | Xem field `failed`, `biased` và thống kê; thử lại với workload ổn định |
| `jdk.CPUTimeSamplesLost` tăng | Queue nội bộ bị quá tải hoặc rate quá cao | Giảm sampling rate, rút ngắn recording và kiểm tra lại |
| File JFR lớn nhanh | Throttle quá dày hoặc ghi quá lâu | Chọn rate giới hạn như `500/s`, giới hạn thời lượng và dung lượng |
| `cpu-time-hot-methods` không có kết quả hữu ích | Không có CPU-bound workload trong recording | Chọn time window có tải CPU và chạy workload đại diện |
| Profile cho kết quả khác giữa hai lần chạy | Workload, throttle, số hardware threads hoặc môi trường thay đổi | Giữ workload và cấu hình cố định, so sánh nhiều lần |
| Ứng dụng dùng native library có hành vi signal riêng | Native code có thể can thiệp signal handler | Kiểm tra thư viện native và log JFR; tránh ghi đè handler `SIGPROF` của JVM |

### Quy trình khoanh vùng nhanh

~~~bash
uname -s
uname -r
java --version
jfr metadata --events jdk.CPUTimeSample
~~~

Sau đó chạy recording ngắn:

~~~bash
java '-XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=500/s,filename=cpu-check.jfr,duration=30s' \
  -jar app.jar

jfr summary cpu-check.jfr
jfr view cpu-time-statistics cpu-check.jfr
~~~

Nếu runtime Linux/JDK phù hợp nhưng không có event, kiểm tra log startup JFR và cấu hình event. Không bật các flag experimental/diagnostic không liên quan chỉ để thử vận may.

## 12. Checklist xác nhận điều kiện kích hoạt

- [ ] JVM thực sự chạy trên Linux.
- [ ] Kernel hỗ trợ per-thread CPU-time timer; mốc nền tảng của cơ chế Linux là 2.6.12.
- [ ] Runtime là HotSpot JDK 25 build có JEP 509 hoặc bản mới hơn giữ tính năng.
- [ ] Đã xác nhận `os.name`, `os.arch`, `java.vm.name` và JDK release từ đúng tiến trình.
- [ ] JFR recording được bật.
- [ ] Event `jdk.CPUTimeSample` được bật tường minh bằng `enabled=true`.
- [ ] Hiểu `@Experimental` không đồng nghĩa phải bật `-XX:+UnlockExperimentalVMOptions`; flag đó không cần cho JEP 509.
- [ ] Chọn throttle phù hợp với số hardware threads và overhead cho phép.
- [ ] Có workload CPU-bound trong khoảng recording.
- [ ] Đã kiểm tra `jdk.CPUTimeSample`, `jdk.CPUTimeSamplesLost` và `cpu-time-statistics`.
- [ ] Nếu runtime không phải Linux, đã chọn execution-time sampling hoặc profiler khác phù hợp.
- [ ] Đã ghi nhận rõ tính experimental trước khi dùng trong production.

### Bài tập thực hành

Một dịch vụ Java chạy trong container Linux. Trên máy phát triển Windows, nhóm không nhìn thấy CPU-time profile nhưng trên staging Linux có thể chạy JDK 25.

1. Xác minh `uname -s`, `uname -r`, `uname -m` trong staging container.
2. Kiểm tra `java --version` và `java.vm.name`.
3. Tạo recording có `jdk.CPUTimeSample#enabled=true` và throttle `500/s`.
4. Gửi workload CPU-bound 30 giây.
5. Chạy `jfr view cpu-time-hot-methods` và `jfr view cpu-time-statistics`.
6. Tăng độ chi tiết bằng throttle `10ms`, rồi so sánh event count, lost samples và overhead.
7. Giải thích vì sao không thể dùng cùng CPU-time sampler trên Windows, dù JFR execution samples vẫn có thể chạy.

## 13. Tài liệu chính thức và nguồn kỹ thuật

- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): thiết kế CPU-time sampler và trạng thái experimental.
- [Oracle — Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận JFR CPU-time profiling là tính năng experimental trên Linux.
- [Oracle — JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/jdk-migration-guide.pdf): tổng quan JEP 509 trong nhóm thay đổi monitoring.
- [Oracle — JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf): xác nhận JFR CPU-time profiling vẫn được mô tả là experimental ở JDK 26.
- [Oracle — The java Command (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `-XX:StartFlightRecording` và event-setting override.
- [OpenJDK — JEP 509 implementation](https://github.com/openjdk/jdk/pull/25302): quá trình tích hợp CPU-time sampler vào OpenJDK.
- [What's New for JFR in JDK 25 — Erik Gahlin](https://inside.java/2025/06/03/new-jfr-jdk25/): ví dụ bật `jdk.CPUTimeSample` và phân biệt với `jdk.ExecutionSample`.
- [Java 25's New CPU-Time Profiler — Johannes Bechberger](https://mostlynerdless.de/blog/2025/06/11/java-25s-new-cpu-time-profiler-1/): giải thích Linux CPU timer, throttle, sample loss và các view chuyên biệt.

> **Ghi nhớ:** JEP 509 trong JDK 25 là CPU-time sampler **experimental, Linux-only, tắt mặc định**. Kiểm tra Linux kernel và đúng HotSpot build, bật `jdk.CPUTimeSample#enabled=true`, chọn throttle, rồi xác minh cả hot methods lẫn lost samples. Trên Windows/macOS, dùng `jdk.ExecutionSample` hoặc profiler phù hợp nền tảng.
