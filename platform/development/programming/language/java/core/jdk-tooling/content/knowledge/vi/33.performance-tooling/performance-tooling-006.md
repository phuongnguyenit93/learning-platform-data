# Profiling sampling trong Java

Profiling sampling là cách quan sát chương trình bằng cách lấy mẫu stack trace của các thread theo chu kỳ. Mỗi sample cho biết thread đang thực thi ở method nào tại thời điểm lấy mẫu. Khi thu thập đủ nhiều sample trong một workload đại diện, tần suất xuất hiện của method giúp ước lượng nơi JVM dành nhiều CPU time nhất.

Java Flight Recorder (JFR) có sẵn trong JDK và phân tích được bằng JDK Mission Control (JMC). Khi cần thêm các chế độ CPU, wall-clock, allocation hoặc lock profiling, async-profiler là một lựa chọn phổ biến của bên thứ ba. Hai công cụ dùng các cơ chế thu thập khác nhau; hãy chọn theo loại câu hỏi cần trả lời.

## 1. Sampling profiler hoạt động như thế nào?

Một sampling profiler định kỳ yêu cầu hoặc thu thập stack trace của thread đang chạy. Ví dụ, với chu kỳ lấy mẫu 10 ms, trong một cửa sổ 10 giây, một thread chạy liên tục có thể được lấy mẫu xấp xỉ 1.000 lần. Mỗi sample chứa stack trace tại thời điểm đó.

Nếu method `calculatePrice()` xuất hiện trong 400 trên 1.000 sample của một thread, ước lượng ban đầu là khoảng 40% thời gian CPU của thread đó được dành ở method hoặc các frame được quy về method đó. Đây là ước lượng thống kê, không phải phép đo chính xác số lần gọi hay thời gian tuyệt đối của method.

### 1.1. Sampling và instrumentation

| Cách đo | Cơ chế | Điểm mạnh | Giới hạn |
|---|---|---|---|
| Sampling | Lấy stack theo chu kỳ | Thường có overhead thấp, phù hợp để tìm hotspot trên ứng dụng đang chạy | Có sai số thống kê; method rất ngắn hoặc hiếm có thể không xuất hiện |
| Instrumentation | Gắn probe vào method/event và ghi mỗi lần xảy ra | Có thể đếm invocation hoặc đo từng lần gọi | Probe làm tăng chi phí; có thể thay đổi hành vi và timing của chương trình |
| Benchmark | Chạy workload có kiểm soát để đo thời gian/throughput | So sánh phiên bản code trong điều kiện tái lập | Không thay thế profiling ứng dụng dưới tải thực |

Sampling phù hợp để tìm nơi cần tối ưu trước. Sau khi tìm được hotspot, dùng benchmark có kiểm soát để đo xem thay đổi có cải thiện kết quả hay không.

### 1.2. Từ sample count đến ước lượng CPU

Giả sử profiler ghi được 2.000 sample CPU:

| Method/nhóm stack | Sample | Tỷ lệ mẫu |
|---|---:|---:|
| `parseRequest()` | 900 | 45% |
| `calculateTax()` | 700 | 35% |
| `formatResponse()` | 300 | 15% |
| Các method khác | 100 | 5% |

Tỷ lệ mẫu gần đúng tỷ lệ CPU time của các stack trong cửa sổ profiling, với điều kiện sample được thu thập đủ đại diện. Không được hiểu 45% là `parseRequest()` được gọi trong 45% request hoặc chiếm 45% request latency.

Nếu một method xuất hiện trong nhiều stack trace, nó có thể là frame cha của nhiều đường gọi. Khi đọc Hot Methods, Call Tree hoặc flame graph, cần xác định đang xem top frame, self time hay inclusive time.

### 1.3. Sai số và kích thước mẫu

Sample càng ít thì ước lượng càng dao động. Với một tỷ lệ mẫu `p` và `n` sample độc lập, sai số chuẩn gần đúng là:

\[
SE \approx \sqrt{\frac{p(1-p)}{n}}
\]

Ví dụ, nếu `p = 0.4` và `n = 400`, sai số chuẩn khoảng 2,45 điểm phần trăm. Khoảng 95% rất gần đúng là khoảng ±4,8 điểm phần trăm quanh tỷ lệ quan sát. Đây là trực giác thống kê; sample thực tế có thể tương quan do chu kỳ, tải và scheduler nên không nên xem công thức này như bảo đảm chính xác.

Một method xuất hiện 2/20 sample chưa đủ cơ sở để kết luận nó là hotspot. Hãy tăng thời gian recording, thu thập thêm sample và lặp lại dưới workload tương tự.

## 2. CPU sampling và các chế độ profiling khác

Trước khi chọn profiler, xác định điều bạn cần biết:

| Câu hỏi | Chế độ phù hợp | Dữ liệu cần xem |
|---|---|---|
| Code Java/native nào đang tiêu thụ CPU? | CPU sampling | Stack của thread đang chạy, Hot Methods, Call Tree |
| Thread đang dành thời gian ở đâu kể cả lúc chờ? | Wall-clock sampling | Stack của thread ở trạng thái running, sleeping hoặc blocked |
| Code nào tạo nhiều object/heap pressure? | Allocation profiling | Call site và lượng allocation |
| Thread chờ lock nào và bao lâu? | Lock contention profiling | Lock/monitor, thread chờ, stack site |
| Thread bị chặn bởi I/O hay GC? | Wall-clock + JFR duration events | Socket/file I/O, monitor wait, park, GC pause |

### 2.1. CPU sampling

CPU sampling lấy stack của thread khi thread đang thực thi. JFR dùng event `jdk.ExecutionSample` cho method sampling Java và `jdk.NativeMethodSample` cho native method sampling. Những thread đang ngủ, chờ I/O hoặc blocked không phải đối tượng của execution sampling tại thời điểm chúng không chạy.

Vì vậy, CPU profile trả lời câu hỏi “CPU đang làm việc gì?”. Nó không tự giải thích toàn bộ thời gian một request bị chậm. Nếu request mất 900 ms nhưng thread chỉ chạy CPU 80 ms, cần điều tra thời gian chờ bằng wall-clock profile, JFR duration events, tracing hoặc metrics của dependency.

### 2.2. Wall-clock sampling

Wall-clock sampling lấy mẫu theo thời gian thực và có thể quan sát thread ở trạng thái running, sleeping hoặc blocked. Nó giúp tìm nơi thread dành thời gian, kể cả khi không tiêu thụ CPU.

Async-profiler hỗ trợ wall-clock mode qua `-e wall`. Khi xem wall-clock profile, một thread chờ queue hoặc I/O có thể xuất hiện nhiều sample ở stack chờ. Một worker đang ngủ vì không có việc không tự động là bottleneck; hãy xác định thread có thuộc critical path của request hay không.

### 2.3. Allocation và lock profiling

Allocation profiling tìm call site tạo nhiều object hoặc tạo heap pressure. Một ứng dụng có CPU profile không quá cao vẫn có thể chậm do allocation rate lớn dẫn đến GC thường xuyên.

Lock profiling tìm các lần chờ lock. JFR có thể ghi các event như `jdk.JavaMonitorEnter` và `jdk.ThreadPark`; async-profiler có lock mode để tổng hợp thời gian chờ lock. Dùng dữ liệu này để xác định thread chờ, lock bị tranh chấp và stack site giữ lock.

Các chế độ allocation và lock có ngữ nghĩa, cách lấy mẫu và overhead khác CPU sampling. Không so sánh trực tiếp phần trăm của hai loại profile như thể chúng là cùng một đại lượng.

## 3. JFR method sampling trong JDK

JFR là bộ ghi sự kiện hiệu năng tích hợp trong HotSpot JDK. Có thể bật recording khi khởi chạy JVM hoặc attach vào JVM đang chạy bằng `jcmd`.

Hai template có sẵn:

- `default.jfc`: thu thập tập dữ liệu cơ bản với overhead thấp, phù hợp recording liên tục.
- `profile.jfc`: thu thập nhiều thông tin hơn để điều tra trong khoảng ngắn; overhead và dung lượng recording có thể cao hơn.

Các template và event setting thay đổi theo JDK/vendor. Kiểm tra file `JAVA_HOME/lib/jfr/default.jfc` hoặc `profile.jfc` của chính runtime đang chạy trước khi giả định sample period.

### 3.1. Xem sample period trong template

Mở `JAVA_HOME/lib/jfr/profile.jfc` và tìm event `jdk.ExecutionSample`:

~~~xml
<event name="jdk.ExecutionSample">
  <setting name="enabled">true</setting>
  <setting name="period">10 ms</setting>
</event>
~~~

Đoạn trên minh họa cách một template có thể cấu hình period. Giá trị thật phụ thuộc bản JDK. Trên JDK 24.0.2 Zulu đã kiểm thử, `profile.jfc` đặt `jdk.ExecutionSample` là 10 ms và `default.jfc` là 20 ms. Đây là giá trị của runtime đó, không phải hằng số bắt buộc cho mọi bản JDK.

### 3.2. Bắt đầu recording cho JVM đang chạy

Tìm PID:

~~~bash
jcmd -l
~~~

Bắt đầu recording trong 30 giây:

~~~bash
jcmd 12345 JFR.start name=cpu-profile settings=profile duration=30s filename=cpu-profile.jfr
~~~

Thay `12345` bằng PID thật. Kiểm tra trạng thái:

~~~bash
jcmd 12345 JFR.check name=cpu-profile verbose=true
~~~

Khi recording hoàn tất, xem summary:

~~~bash
jfr summary cpu-profile.jfr
~~~

In execution samples:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 cpu-profile.jfr
~~~

`jdk.ExecutionSample` thường chỉ ghi thread đang chạy Java code tại thời điểm lấy mẫu. `jdk.NativeMethodSample` cung cấp sample trong native method nếu template bật event đó.

### 3.3. Thay đổi sampling period

Có thể thay period của event trong một recording mà không sửa template gốc:

~~~bash
jcmd 12345 JFR.start name=cpu-5ms settings=profile duration=30s filename=cpu-5ms.jfr jdk.ExecutionSample#period=5ms
~~~

Lệnh trên yêu cầu period 5 ms cho `jdk.ExecutionSample`. Số sample thực tế có thể khác kỳ vọng do thread không chạy liên tục, scheduling, runtime và giới hạn của cơ chế lấy mẫu. Hạ period sẽ tăng số sample, kích thước recording và có thể tăng overhead.

Tạo file `.jfc` riêng nếu cần tái sử dụng cấu hình:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output cpu-sampling.jfc jdk.ExecutionSample#period=5ms
~~~

Sau đó dùng file đó:

~~~bash
jcmd 12345 JFR.start name=cpu-profile settings=/path/to/cpu-sampling.jfc duration=30s filename=cpu-profile.jfr
~~~

Xem cú pháp đúng với runtime:

~~~bash
jcmd 12345 help JFR.start
jfr help configure
~~~

### 3.4. Continuous recording và profiling ngắn

Một recording nhẹ có thể chạy liên tục:

~~~bash
jcmd 12345 JFR.start name=continuous settings=default disk=true maxage=1h maxsize=512m
~~~

Khi có spike, dump cửa sổ gần nhất:

~~~bash
jcmd 12345 JFR.dump name=continuous filename=incident.jfr maxage=10m
~~~

Continuous recording với `default.jfc` phù hợp để giữ bối cảnh trước sự cố. Khi cần nhiều stack sample và event chi tiết hơn, tạo recording `profile` ngắn trong cửa sổ có tải đại diện.

Không chạy nhiều recording `profile` dày đặc mà không đo overhead. `jcmd` báo mức impact của JFR tùy cấu hình; hãy xem help của JFR trên đúng JVM.

## 4. Đọc CPU profile bằng JDK Mission Control

Mở file `.jfr` bằng JDK Mission Control (JMC). Các khu vực thường hữu ích:

1. **Automated Analysis:** cảnh báo ban đầu và các điểm cần kiểm tra.
2. **Code → Hot Methods:** các method xuất hiện nhiều trong execution samples.
3. **Code → Call Tree:** xem method nóng trong quan hệ caller/callee.
4. **Threads:** xem thread nào đang chạy và stack của nó.
5. **Method Profiling / Execution Samples:** lọc sample theo thời gian, thread và stack.
6. **Flame Graph:** xem stack tổng hợp theo chiều sâu; bề rộng thể hiện trọng số sample.

### 4.1. Hot Methods và Call Tree

Hot Methods giúp tìm method có nhiều sample. Call Tree giúp trả lời method đó được gọi từ đâu. Ví dụ, `parseJson()` có nhiều sample có thể do một endpoint gọi nó rất thường xuyên, hoặc vì một lần gọi xử lý payload quá lớn.

Đừng chỉ tối ưu method đứng đầu bảng. Kiểm tra caller, workload, input size và self time. Một method xuất hiện nhiều ở stack nhưng chỉ là frame cha có thể đang tổng hợp thời gian của các method con.

### 4.2. Flame graph

Flame graph biểu diễn stack trace đã gộp:

- Trục ngang biểu thị trọng số sample của các stack.
- Trục dọc biểu thị chiều sâu lời gọi.
- Khối rộng biểu thị nhiều sample hơn.
- Khối hẹp biểu thị ít sample hơn.

Đọc từ frame gốc lên frame lá để hiểu đường gọi. Khối rộng ở một method cho thấy nhiều sample đi qua method đó; không có nghĩa method luôn chạy liên tục hoặc được gọi một số lần cố định.

JMC và các công cụ khác có cách đặt tên view khác nhau theo phiên bản. Nếu không thấy Flame Graph, dùng Hot Methods và Call Tree hoặc xuất profile sang công cụ hỗ trợ flame graph.

## 5. Sampling bằng async-profiler

Async-profiler là profiler sampling của bên thứ ba dành cho HotSpot JVM. Công cụ hỗ trợ CPU, wall-clock, allocation, lock contention, native memory và một số hardware/software performance events. Nó có thể thu thập Java, native và kernel frames tùy nền tảng/cấu hình.

Cần cài đúng bản async-profiler cho OS, kiến trúc CPU và JVM. Lệnh `asprof` bên dưới giả định profiler đã được cài và nằm trong `PATH`; cú pháp/khả năng có thể khác giữa các phiên bản.

### 5.1. CPU profile

~~~bash
asprof -e cpu -d 30 -f cpu.html 12345
~~~

Lấy CPU stack trong 30 giây và ghi flame graph vào `cpu.html`.

### 5.2. Wall-clock profile

~~~bash
asprof -e wall -t -i 50ms -d 30 -f wall.html 12345
~~~

Lấy mẫu tất cả thread theo wall clock, mỗi khoảng 50 ms, trong 30 giây. `-t` chia profile theo thread. Dùng khi muốn xem thread dành thời gian ở đâu kể cả lúc sleeping hoặc blocked.

### 5.3. Allocation profile

~~~bash
asprof -e alloc --alloc 500k -d 30 -f allocation.html 12345
~~~

`--alloc 500k` đặt khoảng lấy mẫu allocation trung bình theo lượng byte được cấp phát. Profile cho biết call site tạo áp lực allocation. Đây không phải số lần gọi constructor chính xác; interval và loại allocation được hỗ trợ tùy JVM/profiler version.

### 5.4. Lock profile

~~~bash
asprof -e lock --lock 5ms -d 30 -f locks.html 12345
~~~

Lock mode giúp tìm thời gian chờ lock contention và stack site liên quan. Ngưỡng `5ms` lọc các lần chờ ngắn hơn ngưỡng được cấu hình; xem tài liệu phiên bản profiler trước khi sử dụng option cụ thể.

### 5.5. Xuất JFR và nhiều event

Async-profiler cũng có thể xuất JFR:

~~~bash
asprof -e cpu -f cpu-profile.jfr 12345
~~~

Có thể kết hợp CPU, allocation và lock trong một file JFR nếu phiên bản profiler hỗ trợ multi-event:

~~~bash
asprof -e cpu,alloc,lock -f combined-profile.jfr 12345
~~~

Một số output đa event chỉ hỗ trợ JFR. Kiểm tra `asprof --help` và tài liệu `ProfilerOptions.md` của đúng release.

### 5.6. Quyền hệ điều hành và môi trường container

CPU profiling bằng hardware performance counters trên Linux có thể cần `perf_event` permissions hoặc cấu hình kernel phù hợp. Trong container, quyền truy cập counter có thể bị giới hạn bởi host, seccomp hoặc capability. Async-profiler có cơ chế và lựa chọn khác nhau theo nền tảng; đọc hướng dẫn cài đặt/profiling trong container trước khi thay đổi quyền hệ thống.

Không cấp quyền root rộng chỉ để thử profiler. Xác định quyền tối thiểu cần thiết trên host và kiểm thử ở môi trường staging.

## 6. Hiểu sampling interval và overhead

Sampling interval quyết định tần suất profiler thu thập stack. Chọn interval là một đánh đổi:

| Interval | Đặc điểm | Dùng khi |
|---|---|---|
| 1–5 ms | Nhiều sample, chi tiết hơn, chi phí và dữ liệu tăng | Điều tra ngắn, cần phân biệt các hotspot gần nhau |
| 10–20 ms | Mức cân bằng thường dùng trong nhiều template | Profiling tổng quát |
| 50–100 ms | Ít sample, overhead/dung lượng thấp hơn | Quan sát dài hoặc workload ít biến động |

Đây là khoảng tham khảo, không phải quy tắc cho mọi profiler. Kiểm tra period mặc định, giới hạn và overhead của công cụ cụ thể. Với workload ngắn hoặc method rất nhanh, interval dài có thể bỏ lỡ method đó.

### 6.1. Sample period không phải thời gian chạy method

Nếu một sample cách nhau 10 ms và stack cho thấy `calculate()` đang chạy, không có nghĩa `calculate()` chạy đúng 10 ms. Sample chỉ ghi trạng thái tại một thời điểm. Nhiều sample rơi vào cùng method cho thấy method đó chiếm phần đáng kể thời gian thực thi trong cửa sổ đo.

Tương tự, một method không xuất hiện không chứng minh nó không chạy. Method có thể quá ngắn, hiếm, không được sample trúng hoặc bị JIT inline vào caller.

### 6.2. Safepoint bias và sampling bias

Một số profiler truyền thống thu thập stack chủ yếu tại safepoint. Nếu code thường xuyên đi qua safepoint khác code hiếm khi đi qua, profile có thể bị lệch về các vị trí dễ được sample.

Async-profiler được thiết kế để giảm safepoint bias bằng cách kết hợp `perf_events` với `AsyncGetCallTrace` trên HotSpot. Dù vậy, mọi profiler đều có giới hạn: native frame, JIT inline frame, platform và cấu hình có thể ảnh hưởng stack thu được. Hãy hiểu cơ chế của công cụ thay vì xem flame graph là bản đồ tuyệt đối của mọi lệnh CPU.

### 6.3. Aliasing với workload tuần hoàn

Nếu workload lặp đúng chu kỳ và sampler cũng lấy mẫu theo chu kỳ tương tự, các sample có thể rơi vào cùng pha và bỏ lỡ phần còn lại. Để giảm rủi ro:

- Ghi đủ lâu để bao phủ nhiều chu kỳ.
- Chạy nhiều recording ở các thời điểm khác nhau.
- Dùng workload có nhịp và dữ liệu gần với production.
- So sánh với metrics, trace và các chế độ profile khác.

Không cố tình tăng tần suất vô hạn để khắc phục sai số; điều đó có thể làm overhead lớn và thay đổi workload đang đo.

### 6.4. Stack depth và JIT inlining

Stack quá nông có thể bỏ mất caller quan trọng. Stack quá sâu làm file lớn và bảng khó đọc. Dùng `--stack-depth` của `jfr print` hoặc `-j` của async-profiler khi cần.

JIT có thể inline method, nên method nguồn không nhất thiết xuất hiện thành một frame độc lập trong mọi sample. Dùng symbol/debug information và tùy chọn hiển thị inline frame của profiler khi cần; không tắt JIT chỉ để có stack đẹp nếu mục tiêu là đo hiệu năng production.

## 7. Quy trình profiling đáng tin cậy

1. Xác định câu hỏi: CPU hotspot, wall-clock wait, allocation hay lock contention.
2. Chọn JVM/PID đúng và kiểm tra JDK, GC, CPU, OS và profiler version.
3. Xác định workload đại diện, request rate, concurrency, dataset và thời điểm cần đo.
4. Warm up JVM nếu đang đo steady state để class loading và JIT compilation không chi phối toàn bộ kết quả.
5. Bắt đầu với interval vừa phải và thời lượng đủ dài để có nhiều sample.
6. Thu một baseline dưới cùng workload trước khi sửa code.
7. Đọc Hot Methods/Call Tree/flame graph; xác định self time, inclusive time, caller và thread.
8. Nếu CPU thấp nhưng request chậm, chuyển sang wall-clock, lock, I/O và distributed tracing.
9. Thay đổi một nguyên nhân đã có bằng chứng; chạy lại cùng workload và so sánh.
10. Lặp lại recording nếu chênh lệch nhỏ hoặc kết quả không ổn định.

### 7.1. Kiểm soát điều kiện đo

Để so sánh hai phiên bản:

- Dùng cùng JDK/vendor, JVM flags và GC.
- Dùng cùng CPU/máy hoặc ghi rõ khác biệt môi trường.
- Dùng cùng dữ liệu, request mix, concurrency và thời gian warm-up.
- Đo nhiều lần và so sánh cả throughput lẫn p50/p95/p99.
- Không chạy benchmark khác đồng thời trên cùng host nếu nó làm nhiễu CPU.
- Lưu file JFR/profile, command line và thông tin phiên bản để tái lập.

Sampling profile cho biết nơi CPU được tiêu thụ; benchmark/metrics mới cho biết thay đổi có cải thiện hiệu năng người dùng hay không.

## 8. Thực hành Java 17+: tạo hai hot path để profile

Ví dụ này tạo hai thread CPU-bound với hai phương thức tính toán khác nhau và một thread ngủ. Mục tiêu là tạo stack sample có thể nhận diện; tỷ lệ method thực tế thay đổi theo CPU, JIT và lịch thread.

Tạo file `ProfilingSamplingFixture.java`:

~~~java
public final class ProfilingSamplingFixture {
    private static volatile long blackhole;

    public static void main(String[] args) throws Exception {
        Thread hotA = new Thread(() -> {
            long value = 1;
            while (!Thread.currentThread().isInterrupted()) {
                value = hotPathA(value);
                blackhole = value;
            }
        }, "fixture-hot-a");

        Thread hotB = new Thread(() -> {
            long value = 2;
            while (!Thread.currentThread().isInterrupted()) {
                value = hotPathB(value);
                blackhole ^= value;
            }
        }, "fixture-hot-b");

        Thread waiter = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(40);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "fixture-waiter");

        hotA.setDaemon(true);
        hotB.setDaemon(true);
        waiter.setDaemon(true);
        hotA.start();
        hotB.start();
        waiter.start();

        System.out.println("ProfilingSamplingFixture ready");
        new java.util.concurrent.CountDownLatch(1).await();
    }

    private static long hotPathA(long x) {
        for (int i = 0; i < 1200; i++) {
            x = (x * 1664525L + 1013904223L) ^ (x >>> 13);
        }
        return x;
    }

    private static long hotPathB(long x) {
        for (int i = 0; i < 300; i++) {
            x = Long.rotateLeft(x + i * 31L, 7)
                * 0x9E3779B97F4A7C15L;
        }
        return x;
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 -d out ProfilingSamplingFixture.java
java -cp out ProfilingSamplingFixture
~~~

Stdout chính xác:

~~~text
ProfilingSamplingFixture ready
~~~

Ở terminal thứ hai, tìm PID:

~~~bash
jcmd -l
~~~

Ghi profile 5 giây với sample period 5 ms:

~~~bash
jcmd 12345 JFR.start name=sample-5ms settings=profile duration=5s filename=sample-5ms.jfr jdk.ExecutionSample#period=5ms
~~~

Sau khi recording kết thúc, xem số lượng event:

~~~bash
jfr summary sample-5ms.jfr
~~~

Xem method được sample nhiều:

~~~bash
jfr view hot-methods sample-5ms.jfr
~~~

In stack mẫu:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 16 sample-5ms.jfr
~~~

Trong lần kiểm thử fixture với JDK 24.0.2, recording 5 giây có 1.738 `jdk.ExecutionSample` và 48 `jdk.NativeMethodSample`. View Hot Methods xếp hai đường code nóng của fixture lên đầu. Các con số và phần trăm thay đổi theo máy và lần chạy; điều quan trọng là sample có thread name, trạng thái `STATE_RUNNABLE` và stack trace trỏ vào code đang chạy.

Một số method có thể bị JIT inline nên tên method xuất hiện trong Hot Methods có thể khác giữa các lần chạy. Đừng dùng tỷ lệ trong lần kiểm thử này làm ngưỡng chuẩn cho máy khác.

## 9. Chọn công cụ theo mục tiêu

| Công cụ | Có sẵn trong JDK? | Phù hợp nhất với |
|---|---|---|
| JFR + JMC | Có trong các JDK HotSpot hiện đại; JMC có thể cần cài riêng | CPU sample, GC, lock, I/O, allocation và timeline event |
| `jfr` CLI | Có trong JDK | Summary, lọc event, xem hot-method view nếu phiên bản hỗ trợ |
| async-profiler | Bên thứ ba | CPU, wall-clock, allocation, lock, native/kernel stack và flame graph |
| JMH | Thư viện benchmark | Microbenchmark method trong điều kiện kiểm soát |
| APM/distributed tracing | Nền tảng ứng dụng | End-to-end latency, dependency và request path |

Không có một profile nào trả lời mọi câu hỏi. Dùng CPU sampling để tìm code nóng; wall-clock và duration event để tìm chờ; allocation/lock profile cho các nguồn pressure cụ thể; APM để nối các bước của request.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy `jdk.ExecutionSample` | Template tắt method sampling hoặc recording quá ngắn | Kiểm tra `profile.jfc`, `JFR.check` và `jfr summary` |
| Sample count quá thấp | Interval dài, thời lượng ngắn hoặc workload ít CPU | Kéo dài recording và xác nhận workload đang chạy |
| Hot Methods thay đổi nhiều giữa các lần chạy | Workload không ổn định, sample ít hoặc JIT đang warm up | Chuẩn hóa warm-up, tăng thời lượng và lặp lại |
| Thread chờ không xuất hiện trong CPU profile | ExecutionSample chỉ lấy mẫu thread đang chạy | Dùng wall-clock profile, JFR lock/I/O events hoặc thread timeline |
| Method ngắn không xuất hiện | Method không được sample trúng hoặc đã inline | Thu thêm sample, xem caller và profile khác khi cần |
| Flame graph có nhiều native frame | Native library/JVM đang tiêu thụ CPU hoặc thiếu symbol | Kiểm tra native stack và cài debug symbols phù hợp |
| JFR file quá lớn | Interval thấp, recording dài hoặc bật nhiều event | Tăng interval, giới hạn duration/maxsize và chỉ bật event cần thiết |
| Profiling làm throughput giảm | Template chi tiết, sampling quá dày hoặc nhiều profiler chạy cùng lúc | Dùng `default` cho continuous, `profile` ngắn và đo overhead |
| `asprof` không attach được | Sai kiến trúc/JVM, thiếu quyền OS hoặc hạn chế container | Kiểm tra bản profiler, quyền perf_event và log attach |
| Không thấy view `hot-methods` | JDK release không cung cấp view đó | Chạy `jfr help view`, dùng `jfr print` hoặc mở JMC |

## 11. Checklist trước khi kết luận

- [ ] Đã xác định câu hỏi cần trả lời: CPU, wall-clock, allocation hay lock.
- [ ] Đúng PID, JVM, JDK/vendor và profiler version.
- [ ] Workload đại diện và có warm-up phù hợp.
- [ ] Recording đủ dài và có đủ sample để diễn giải.
- [ ] Đã kiểm tra period thực tế trong template hoặc lệnh recording.
- [ ] Không nhầm sample percentage với invocation count hoặc request latency.
- [ ] Đã xem cả caller, callee, self time và inclusive time.
- [ ] Đã kiểm tra JIT inlining và native frames khi cần.
- [ ] Đã dùng wall-clock/lock/I/O profile nếu CPU profile không giải thích latency.
- [ ] Đã so sánh với baseline dưới điều kiện tương đương.
- [ ] Đã đo throughput và latency sau khi thay đổi.
- [ ] Đã đánh giá overhead và bảo vệ file profile/JFR trước khi chia sẻ.

## 12. Ghi nhớ

Profiling sampling lấy stack trace theo chu kỳ để ước lượng nơi chương trình dành thời gian. CPU sampling tập trung vào thread đang chạy; wall-clock sampling còn quan sát thread ngủ hoặc chờ. Tỷ lệ sample là ước lượng thống kê, không phải số lần gọi method hay thời gian request chính xác.

Bắt đầu với JFR `profile` trong thời gian ngắn, xem `jdk.ExecutionSample`, Hot Methods và Call Tree trong JMC. Điều chỉnh `jdk.ExecutionSample#period` khi cần thêm sample và theo dõi overhead. Dùng async-profiler khi cần wall-clock, allocation, lock hoặc native profiling. Cuối cùng, xác nhận hotspot bằng workload/benchmark tái lập và đo lại latency/throughput trước khi kết luận đã cải thiện.

Tài liệu tham khảo:

- [Java Flight Recorder package — Settings and configuration (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Diagnostic Tools — Java SE 24](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [async-profiler — Profiling Modes](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md)
- [async-profiler — Profiler Options](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilerOptions.md)
- [async-profiler — Project and Downloads](https://github.com/async-profiler/async-profiler)