# 1.6 Phân biệt quan sát, profiling, debugging và thay đổi cấu hình đang chạy

## Mục tiêu học tập

Khi một ứng dụng Java đang chạy có độ trễ tăng, CPU cao, lỗi gián đoạn hoặc hành vi bất thường, người vận hành có bốn nhóm thao tác dễ bị nhầm lẫn: **quan sát (observation/monitoring)**, **profiling**, **debugging** và **thay đổi cấu hình lúc chạy (runtime configuration change)**. Sau bài này, bạn có thể:

- Chọn đúng cách tiếp cận theo câu hỏi chẩn đoán và mức can thiệp chấp nhận được.
- Phân biệt dữ liệu chỉ ra **triệu chứng**, dữ liệu định vị **điểm tiêu tốn tài nguyên**, bằng chứng giải thích **trạng thái/luồng điều khiển**, và hành động **thay đổi hệ thống**.
- Dùng các công cụ phổ biến của JDK 17+/21 như JMX, `jcmd`, Java Flight Recorder (JFR) và JDWP theo đúng mục đích.
- Đánh giá chi phí quan sát, độ tin cậy của kết luận, quyền truy cập, tác động lên production và khả năng hoàn tác.

## 1. Bốn khái niệm và ranh giới cốt lõi

| Hoạt động | Câu hỏi chính | Tín hiệu/thao tác điển hình | Mức ảnh hưởng thường gặp | Kết quả mong muốn |
| --- | --- | --- | --- | --- |
| **Quan sát** | *Hệ thống đang diễn ra điều gì, khi nào, ở đâu?* | Metrics, logs, distributed traces, health/status, JMX, vài thread dump tại những thời điểm xác định | Thấp nếu thu thập có kiểm soát; không mặc nhiên bằng 0 | Nhận diện triệu chứng, xu hướng, phạm vi, thời điểm và tương quan |
| **Profiling** | *CPU, bộ nhớ, allocation, lock hoặc thời gian đang tập trung ở đâu?* | JFR events/samples, CPU/alloc profiler, flame graph, contention profile | Từ thấp đến đáng kể tùy sampling, events, tần suất và thời lượng | Xác định hotspot, phân bố chi phí và giả thuyết tối ưu |
| **Debugging** | *Tại sao nhánh này chạy, biến này có giá trị đó, thread này dừng tại đây?* | Breakpoint, step into/over, stack frame, inspect/evaluate expression qua debugger/JDWP | Có thể lớn: tạm dừng thread, đổi lịch chạy, ảnh hưởng trạng thái | Giải thích một đường thực thi cụ thể và tìm lỗi logic |
| **Thay đổi cấu hình đang chạy** | *Nếu điều chỉnh tham số/đặc tính được hỗ trợ, hành vi có thay đổi như mong đợi không?* | Đổi log level, một số MBean/feature flag, `jcmd VM.log`, VM flag được phép sửa | Là **can thiệp**; có thể làm đổi tải, hành vi, bảo mật hoặc tài nguyên | Giảm thiểu sự cố hay thử một thay đổi có kiểm soát và đo hiệu quả |

Một thao tác có thể phục vụ nhiều mục đích: JFR với cấu hình `default` thường được dùng để quan sát có dòng thời gian, còn JFR `profile` dùng để phân tích sâu hơn. Bật thêm log là **thay đổi cấu hình để tăng khả năng quan sát**; hành động bật log vẫn là can thiệp. Thu thập một thread dump là ảnh chụp trạng thái, chưa phải profiling thống kê nếu chưa có đủ mẫu.

**Trình tự mặc định khi xử lý production:** quan sát để khoanh vùng → profiling có giới hạn để kiểm chứng hotspot → debugging trong môi trường tái hiện khi cần giải thích logic → chỉ thay đổi cấu hình đang chạy khi có mục tiêu, mức rủi ro và đường hoàn tác rõ ràng. Có thể quay lại quan sát ở mọi bước để kiểm tra kết quả.

## 2. Quan sát: thấy triệu chứng mà không vội kết luận nguyên nhân

Quan sát thu thập tín hiệu liên tục hoặc theo đợt để trả lời **cái gì, bao lâu, ảnh hưởng tới ai, bắt đầu từ lúc nào**.

**Ba nguồn ứng dụng phổ biến:**

1. **Metrics** là số đo có trục thời gian: throughput, error rate, latency p50/p95/p99, queue length, heap used, GC pause, live thread count, CPU process, file descriptors. Counter phải đọc theo *tốc độ tăng trong khoảng thời gian* nếu cần rate; một giá trị tích lũy tự nó chưa cho biết tốc độ hiện tại.
2. **Logs** mô tả sự kiện với thời gian, mức độ, ngữ cảnh và lý do xử lý. ID tương quan (request/trace ID), tên component, loại lỗi và duration hữu ích hơn các dòng `debug` tràn lan. Cần giới hạn dữ liệu cá nhân, token và payload nhạy cảm.
3. **Traces** nối các span trong một yêu cầu xuyên các lớp/dịch vụ, cho biết thời gian phân bổ theo nhánh, RPC, DB hay queue. Một span chậm phản ánh nơi thời gian được ghi nhận; không tự chứng minh CPU của span cao.

**Tầng JVM và hệ điều hành:** qua JMX/MXBeans có thể quan sát memory pool, GC, threads, class loading; qua công cụ hệ điều hành quan sát CPU, RSS, disk I/O, network, giới hạn container. Đối chiếu nhiều tầng: heap ổn định không đồng nghĩa RSS ổn định; CPU process cao không đồng nghĩa mọi request đều dùng CPU.

Ví dụ: `p99` tăng từ 120 ms lên 900 ms cùng lúc lượng request tăng. Điều có thể khẳng định là **đuôi phân phối latency xấu đi trong khoảng đo**. Chưa thể kết luận do GC, lock, DB hay CPU. Nếu biểu đồ GC pause ổn định nhưng thread chờ connection pool tăng, hướng điều tra thay đổi. Phải so sánh cùng khoảng thời gian, cùng lưu lượng và cùng nhóm endpoint/phiên bản.

**Quan sát cũng gây ảnh hưởng:** thu quá nhiều metrics nhãn có cardinality lớn, log đồng bộ dày đặc, sampling trace quá cao, dump liên tục hoặc truy vấn JMX nặng đều có overhead. Thread dump phản ánh thời điểm chụp, có thể bỏ lỡ lỗi hiếm. Cần nêu độ phân giải, sampling và giới hạn của nguồn đo.

## 3. Profiling: định vị chỗ tiêu tốn tài nguyên

Profiling phân tích **phân bố chi phí** trong quá trình thực thi, thường qua mẫu ngăn xếp (sampling) hoặc sự kiện được JVM/công cụ ghi lại (events/instrumentation).

- **CPU profile:** thread/method nào xuất hiện nhiều trong mẫu lúc thực thi trên CPU; hữu ích khi CPU process cao. CPU time khác **wall-clock latency**: request chờ lock/I/O có thể chậm nhưng dùng ít CPU.
- **Wall-clock/lock profile:** thời gian bị chặn, chờ lock, park hoặc I/O; hữu ích khi request chậm dù CPU không cao. Không suy ra nguyên nhân từ một stack trace đơn lẻ.
- **Allocation profile:** vị trí tạo object/byte nhiều nhất; không đồng nghĩa object đó sống lâu hoặc gây memory leak. Để tìm giữ tham chiếu/leak cần xét heap, retained size, vòng đời object, GC và bằng chứng tăng trưởng qua thời gian.
- **GC profile:** tần suất, thời lượng pause, tốc độ cấp phát, sức ép heap; pause lớn là bằng chứng về GC tại thời điểm đó nhưng cần đối chiếu latency và workload.
- **Flame graph:** bề rộng khung biểu thị tỷ lệ mẫu/cost theo cấu hình profiler; nó không phải sơ đồ số lần method được gọi hay bằng chứng nhân quả tuyệt đối. Phân biệt thời gian *inclusive* (bao gồm hàm con) và *exclusive/self* (chỉ phần của hàm đó).

**Sampling và instrumentation khác nhau:** sampling định kỳ thu stack với overhead thường thấp hơn nhưng bỏ sót đường hiếm; instrumentation có thể đo chi tiết lời gọi/sự kiện nhưng gây overhead hoặc thay đổi timing nhiều hơn. Mức overhead của JFR tùy events và settings: `default` hướng tới thu thập nhẹ, `profile` thu nhiều dữ liệu hơn; phải đo trên workload thực tế, giới hạn thời lượng và dung lượng.

**Quy trình lấy profile đáng tin:**

1. Chốt câu hỏi cụ thể, ví dụ “Trong 60 giây CPU tăng, code Java nào chiếm mẫu CPU nhiều nhất?”.
2. Ghi phiên bản, JVM/JDK, cấu hình, tải, thời điểm bắt đầu/kết thúc và baseline trước khi lấy mẫu.
3. Chọn đúng loại profile (CPU, allocation, lock, GC); lấy mẫu đủ lâu để có tính đại diện, tránh gộp cả giai đoạn warm-up nếu mục tiêu là steady-state.
4. Phân tích phân phối và đối chiếu metrics/logs/traces; xác minh bằng lần đo lặp lại hoặc phép thử có kiểm soát trước khi tối ưu.
5. Kết thúc recording, dọn file và xử lý quyền truy cập: file `.jfr` có thể chứa tên class/method, path và dữ liệu vận hành nhạy cảm.

**Giới hạn suy luận:** không thấy method trong profile không chứng minh method không chạy; sự xuất hiện nhiều lần trong mẫu chỉ cho biết tính tập trung của hoạt động dưới điều kiện đo. Profiling giúp **định vị** hotspot, còn giải thích tại sao logic đưa tới trạng thái đó có thể cần debug hoặc phân tích code.

## 4. Debugging: giải thích trạng thái và đường thực thi cụ thể

Debugger (thường giao tiếp với JVM qua **Java Debug Wire Protocol – JDWP**) có thể đặt breakpoint, xem stack frame, biến cục bộ, thứ tự lời gọi, step và evaluate expression. Hữu ích khi có một input tái hiện được lỗi: “Tại sao điều kiện này trả `true`?” hoặc “Biến bị ghi đè ở nhánh nào?”.

**Điểm khác profiling:** một breakpoint cho biết một lần chạy cụ thể đang ở đâu và giá trị biến lúc đó; nó không cho biết method ấy chiếm bao nhiêu phần trăm CPU tổng thể. Ngược lại, một CPU flame graph không cho biết tất cả giá trị biến tại lần chạy gây lỗi.

**Tác động cần hiểu trước khi gắn debugger:**

- Breakpoint với chế độ suspend **All** có thể ngừng toàn JVM hoặc phần lớn luồng ứng dụng; suspend **Thread** có thể vẫn gây deadlock/timing bất thường khi các thread khác chờ nó. Timeout ở upstream có thể xuất hiện do chính debugger.
- Evaluate expression, method invocation, set value, hot swap có thể **làm thay đổi trạng thái**; đừng coi mọi thao tác debugger là read-only.
- Tạm dừng làm đổi lịch thread, có thể che lỗi race condition hoặc tạo lỗi mới. Với lỗi concurrency, ưu tiên logs theo correlation ID, JFR lock/park events và nhiều thread dump tại thời điểm liên quan.
- JDWP mở quyền điều khiển tiến trình; chỉ bật ở môi trường tin cậy, giới hạn địa chỉ mạng và quyền truy cập. Không để cổng debug công khai trên production.

Khi cần xác nhận lỗi logic, hãy tạo một test tái hiện trong development/staging với cùng input, phiên bản thư viện và điều kiện quan trọng; dùng breakpoint ở vị trí hẹp, ghi lại bước suy luận, sau đó bỏ debug settings. Trong production, ưu tiên snapshot và instrumentation được kiểm soát trước khi cân nhắc debugger.

## 5. Thay đổi cấu hình đang chạy: hành động kiểm soát hệ thống

Đổi cấu hình lúc chạy **không chỉ là quan sát**. Nó thay đổi dữ liệu đầu vào, độ chi tiết chẩn đoán hoặc chính hành vi của tiến trình đang phục vụ traffic.

Phân biệt ba lớp:

1. **Cấu hình ứng dụng:** một số hệ thống có log level thay đổi qua API/JMX, feature flag, ngưỡng cache hay thread pool được thiết kế để cập nhật an toàn. Chỉ có hiệu lực nếu ứng dụng thật sự hỗ trợ reload/đọc giá trị mới; sửa một file cấu hình trên đĩa không đảm bảo process tự nạp lại.
2. **Cấu hình JVM/JDK:** `jcmd VM.log` có thể xem hoặc điều chỉnh **JVM Unified Logging** lúc chạy; `jcmd VM.set_flag` chỉ có thể đổi **các flag mà JVM cho phép ghi động**. Các tùy chọn khởi động như `-Xmx`, classpath, module path hoặc Java agent không mặc nhiên chỉnh được trên tiến trình hiện tại.
3. **Cấu hình môi trường/deployment:** thay environment variable, `-D...` trong command line hay cấu hình container mới thường chỉ ảnh hưởng một tiến trình **được khởi động lại**; JVM đang chạy không tự nhận thay đổi đó. `System.setProperty` trong code là trường hợp riêng và chỉ có ý nghĩa nếu thành phần liên quan đọc lại property.

**Ví dụ ranh giới:** chạy `jcmd ... JFR.start` bật cơ chế thu thập chẩn đoán, không sửa thuật toán nghiệp vụ; chạy `jcmd ... VM.log` đổi hành vi logging và có thể làm tăng I/O; đổi feature flag có thể đổi đường đi của request. Cả ba đều là thao tác điều khiển runtime với độ rủi ro khác nhau.

Trước thay đổi: lưu giá trị hiện tại, chỉ ra đối tượng/phạm vi/thời lượng, lý do và metric thành công; kiểm tra quyền vận hành, ảnh hưởng hiệu năng và rollback. Trong thay đổi: áp dụng **một biến** khi có thể, đánh dấu thời điểm change, theo dõi error rate, latency, throughput, CPU và logs. Sau thay đổi: xác minh cấu hình thực sự có hiệu lực, đo cùng cửa sổ tải, hoàn tác nếu vượt ngưỡng, và quyết định cần ghi vào cấu hình triển khai lâu dài hay không. Đổi trong process có thể **mất sau restart**.

Cần tách hai câu hỏi: “Thay đổi này có được API/JVM hỗ trợ không?” và “Thay đổi này có an toàn ở thời điểm hiện tại không?”. Được hỗ trợ kỹ thuật chưa có nghĩa nên làm trên production.

## 6. Thực hành nhỏ với Java 17+: một JVM, nhiều cách nhìn

Tạo tệp **`DiagnosticsLab.java`** với nội dung sau. Đây là chương trình Java độc lập, chạy liên tục để có thời gian quan sát và thu profile:

```java
public final class DiagnosticsLab {
    private static volatile double lastResult;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        long rounds = 0;

        while (true) {
            double sum = 0;
            for (int i = 1; i <= 1_000_000; i++) {
                sum += Math.sqrt(i);
            }
            lastResult = sum;
            rounds++;

            if (rounds % 20 == 0) {
                System.out.println("rounds=" + rounds);
            }
            Thread.sleep(100);
        }
    }
}
```

Biến `lastResult` được ghi `volatile` để giữ kết quả tính toán có thể quan sát từ ngoài luồng; vòng lặp sinh một workload CPU nhỏ xen kẽ `sleep`. Con số PID, tốc độ in dòng `rounds=...` và tỷ lệ CPU **phụ thuộc môi trường**, nên không có một stdout cố định. Dừng demo bằng **Ctrl+C**.

Biên dịch và chạy từ thư mục chứa tệp (JDK 17 trở lên):

```bash
javac DiagnosticsLab.java
java DiagnosticsLab
```

Trong terminal khác, dùng PID thực tế mà chương trình in ra. Các lệnh dưới đây minh họa với **PID 12345**; phải thay bằng PID của JVM demo và dùng `jcmd` từ JDK thích hợp trên cùng máy/tài khoản có quyền attach:

```bash
jcmd 12345 help
jcmd 12345 Thread.print
jcmd 12345 VM.flags
```

- `Thread.print`: một ảnh chụp stack/thread state; so sánh nhiều ảnh tại các thời điểm mới thấy xu hướng chờ/chạy. Không gọi đây là CPU profile.
- `VM.flags`: đọc cờ JVM hiện tại; không chứng minh mọi cờ đều sửa được động.
- `help`: xác minh diagnostic commands thực sự có trên JVM đích; công cụ có thể bị giới hạn bởi quyền, bản phân phối, cờ tắt attach hoặc ranh giới container.

**Thu profile ngắn bằng Java Flight Recorder:**

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check
```

Chờ recording đủ 60 giây rồi đọc tệp `triage.jfr` tại nơi JVM đích được phép ghi; với đường dẫn tương đối, cần xác định working directory của process đích. Có thể mở bằng **JDK Mission Control (JMC)** hoặc dùng:

```bash
jfr summary triage.jfr
jfr print --events jdk.ExecutionSample triage.jfr
```

`summary` thống kê loại/số lượng sự kiện; `jdk.ExecutionSample` hiển thị các CPU execution samples nếu recording thực sự có loại event này. Nội dung và số lượng event không cố định. Nếu dùng recording liên tục, `JFR.dump` ghi bản chụp mà **không tự dừng recording**; `JFR.stop` là lệnh riêng. `settings=profile` tăng chi tiết so với `default`, vì vậy chỉ dùng khoảng thu phù hợp trong production.

**Debug cùng chương trình ở môi trường local:** dừng tiến trình demo cũ rồi chạy lại với JDWP chỉ lắng nghe loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DiagnosticsLab
```

Trong IDE, attach Java debugger đến `127.0.0.1:5005`; đặt breakpoint tại `lastResult = sum;` và inspect `sum`, `rounds` để hiểu **một vòng chạy**. `suspend=n` cho phép ứng dụng khởi động ngay; breakpoint có thể tạm dừng tiến trình khi được chạm tới. Không dùng lệnh bật JDWP này như một thao tác chẩn đoán mặc định trên hệ thống production.

**Xem cơ chế đổi logging JVM tại runtime (chỉ thử trên JVM demo):**

```bash
jcmd 12345 VM.log list
jcmd 12345 VM.log output=stdout what=gc=debug
jcmd 12345 VM.log list
```

Dòng giữa thay đổi cấu hình **JVM GC logging**, không phải `java.util.logging`, Logback hay SLF4J của ứng dụng. Lệnh có thể không xuất ra log GC ngay nếu chưa có sự kiện phù hợp. Lưu kết quả `VM.log list` trước thay đổi và hoàn nguyên đúng cấu hình cũ sau thử nghiệm; không giả định dùng `disable` là rollback an toàn vì nó ảnh hưởng toàn bộ logging JVM. Muốn đổi flag cụ thể, phải kiểm tra cờ được phép cập nhật và rủi ro của nó; `VM.set_flag` không biến mọi startup option thành cấu hình động.

## 7. Cùng một sự cố, bốn loại hoạt động khác nhau

Giả sử service Java có **p99 latency tăng mạnh**, nhưng error rate chưa tăng:

| Bước | Thao tác | Bằng chứng hoặc quyết định |
| --- | --- | --- |
| 1. Quan sát | Đối chiếu p99 với request rate, GC pause, CPU, connection pool, số thread chờ và traces của endpoint bị ảnh hưởng | Xác nhận triệu chứng ở endpoint/khung giờ nào; phân biệt CPU bận với chờ tài nguyên |
| 2. Profiling | Lấy JFR ngắn khi tái hiện tải, xem CPU samples, lock contention, allocation và timeline | Xem hotspot xuất hiện ở xử lý CPU, synchronized/park hay tạo object; dùng nhiều bằng chứng để kiểm chứng |
| 3. Debugging | Viết test tái hiện request chậm; đặt breakpoint tại nhánh retry hoặc tranh chấp lock trên staging | Quan sát trạng thái biến và thứ tự lời gọi dẫn tới lỗi logic; lưu ý debugger làm thay đổi timing |
| 4. Thay đổi runtime | Chỉ khi phù hợp, tăng log level của component liên quan trong thời gian ngắn hoặc điều chỉnh một tham số có cơ chế runtime update | Theo dõi log/metric trước–sau, kiểm tra hiệu lực và revert; thay đổi không thay thế việc xác minh nguyên nhân gốc |

**Tình huống khác để chọn công cụ:**

- CPU 95% nhưng latency thấp ở phần lớn request: bắt đầu từ CPU process, load, threads; dùng **CPU profiler/JFR** để tìm hotspot. Đặt breakpoint ngay có thể làm mất workload cần đo.
- Request treo từng đợt, CPU thấp: xem traces, queue, thread state và lock events; **wall/lock profiling** hữu ích hơn chỉ nhìn CPU profile.
- Một input cụ thể trả kết quả sai dù tải bình thường: test tái hiện và **debugging** thường đem lại thông tin trực tiếp hơn profile hiệu năng.
- Cần thấy thêm nguyên nhân lỗi trong 5 phút: thay đổi **log level có kiểm soát**, theo dõi volume và trả về giá trị cũ. Việc đổi log level là runtime change; dòng log thu được mới là observation.
- Muốn “tăng heap ngay” vì RSS cao: trước hết phân biệt heap used, native memory, container RSS và GC; không giả định `-Xmx` đang chạy thay đổi được bằng `VM.set_flag`. Nếu cần startup option khác, lên kế hoạch restart/rollout riêng.

## 8. Quy trình chẩn đoán production có giới hạn tác động

1. **Định nghĩa triệu chứng và mốc thời gian:** SLI/SLO nào xấu đi, mức độ ảnh hưởng, bản phát hành nào, điều kiện tải nào? Lưu dấu thời điểm bắt đầu để tránh nhầm thay đổi do workload.
2. **Thu baseline ít can thiệp:** metrics JVM + OS, error/log correlation, traces đã có. Tách triệu chứng khỏi giả thuyết; tránh debug ngay khi chưa biết phạm vi.
3. **Đặt câu hỏi có thể đo:** “CPU Java hay chờ external service?”, “allocation cao ở method nào?”, “GC pause có trùng spike p99 không?”.
4. **Chọn công cụ và ngân sách overhead:** xác định loại dữ liệu, quyền attach, thời gian thu, tần suất, dung lượng đĩa, mức độ nhạy cảm của file và tiêu chí dừng. Heap dump đầy đủ có thể rất lớn, gây pause/tác động bộ nhớ; không coi là thao tác nhẹ.
5. **Thu bằng chứng có thời hạn:** dùng sampling/JFR hoặc snapshot phù hợp, gắn timestamp và phiên bản; kiểm tra dữ liệu thu có đúng cửa sổ sự cố. Nếu cần debugger, ưu tiên tái hiện ở staging.
6. **Giải thích và kiểm chứng:** phân biệt tương quan với nguyên nhân; kiểm tra triệu chứng qua ít nhất hai nguồn dữ liệu hoặc phép tái hiện. Không khẳng định tối ưu thành công chỉ vì flame graph nhìn khác.
7. **Nếu cần can thiệp:** ghi cấu hình gốc, phạm vi, owner, timeout, tín hiệu an toàn và phương án rollback; áp dụng nhỏ, quan sát trước–sau trong cửa sổ tải so sánh được.
8. **Kết thúc và học lại:** dừng recording/log debug, hoàn nguyên thử nghiệm, bảo vệ/xóa artifact theo quy định, ghi giả thuyết nào được xác nhận và cải thiện telemetry nào thiếu.

Một hệ thống có thể quan sát được mà vẫn chưa dễ debug; một profiler tốt không sửa được bug; một thay đổi runtime làm latency giảm chưa tự chứng minh được nguyên nhân ban đầu nếu không kiểm soát các biến khác.

## 9. Những nhầm lẫn thường gặp

- **“Monitoring và profiling giống nhau vì đều dùng JFR.”** Không hẳn: tên công cụ không quyết định mục đích. Theo dõi xu hướng/timeline là quan sát; phân bổ mẫu CPU/allocation/lock để tìm hotspot là profiling.
- **“Thread dump chứng minh một method dùng nhiều CPU.”** Một dump chỉ là một thời điểm; thread ở trạng thái `RUNNABLE` chưa chắc đang dùng CPU liên tục. Cần nhiều mẫu và đối chiếu CPU.
- **“Allocation nhiều tức là memory leak.”** Object tạo nhiều có thể được thu hồi nhanh; leak cần bằng chứng object bị giữ và live memory tăng theo thời gian.
- **“Debugger chỉ đọc dữ liệu nên an toàn trên production.”** Breakpoint có thể treo thread; evaluate expression/hot swap có thể làm thay đổi dữ liệu và timing.
- **“Tất cả JVM flags đều có thể chỉnh bằng `VM.set_flag`.”** Chỉ các tùy chọn được JVM hỗ trợ cập nhật động mới thay đổi được; xác minh trên JVM/version thực tế.
- **“Đổi file config hoặc biến môi trường là process đang chạy nhận ngay.”** Không có đảm bảo nếu không có cơ chế reload hoặc process restart; phải kiểm tra trạng thái có hiệu lực.
- **“Bật `debug` càng nhiều càng tốt.”** Log volume, CPU/I/O, cardinality và rò rỉ thông tin có thể làm sự cố nặng thêm. Thu hẹp phạm vi và đặt thời hạn.
- **“Sau khi đổi cấu hình thấy tốt hơn thì đã tìm được root cause.”** Có thể trùng thay đổi tải, cache warm-up hoặc yếu tố khác; vẫn cần đối chiếu baseline và bằng chứng kỹ thuật.

## 10. Tự kiểm tra cách lựa chọn

1. **CPU cao, cần biết method tiêu tốn nhất:** bắt đầu bằng observation xác nhận phạm vi, sau đó CPU profiling/JFR; không đặt breakpoint làm công cụ đo CPU.
2. **Sai kết quả chỉ với một input:** dựng test và debug nhánh xử lý; metrics giúp biết mức ảnh hưởng nhưng không thay thế quan sát biến.
3. **Muốn bật GC log trong 2 phút để kiểm chứng giả thuyết:** đó là runtime configuration change phục vụ observation; lưu cấu hình trước, kiểm soát volume, bật rồi hoàn nguyên.
4. **p99 cao nhưng CPU thấp, nhiều thread chờ:** dùng trace + thread state + lock/wall-clock profiling; một CPU flame graph trống không loại trừ bottleneck.
5. **Cần đổi heap limit của service đang chạy:** xác định JVM/startup option và chính sách deployment; đừng giả định thao tác đổi flag động khả dụng.

**Nguyên tắc nhớ lâu:** *Observation* xác định **hiện tượng và phạm vi**; *profiling* cho biết **chi phí tập trung ở đâu**; *debugging* giải thích **tại sao một lần thực thi diễn ra như vậy**; *runtime configuration change* là **hành động làm thay đổi tiến trình** và phải được kiểm chứng bằng quan sát sau đó.

### Tài liệu tham khảo chính thức (JDK 21)

- [Oracle — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): JFR, JMC, `jcmd`, hướng thu thập chẩn đoán.
- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cú pháp `JFR.start`, `JFR.dump`, `Thread.print`, `VM.flags`, `VM.log`, `VM.set_flag` và lưu ý impact.
- [Oracle — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog`, cấu hình JVM, các tùy chọn lúc khởi động.
