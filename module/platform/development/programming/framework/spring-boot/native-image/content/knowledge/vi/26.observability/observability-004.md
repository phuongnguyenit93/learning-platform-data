# JFR, heap dump và khả năng giám sát theo phiên bản, nền tảng

Khi chạy Spring Boot trên JVM, nhóm vận hành thường quen dùng JDK Flight Recorder (JFR), heap dump, JMX và các công cụ chẩn đoán của HotSpot. Khi biên dịch ứng dụng thành **GraalVM Native Image**, các khả năng này vẫn có thể tồn tại, nhưng không mặc nhiên được bật và không có cùng phạm vi trên mọi phiên bản hoặc hệ điều hành.

Native Image có runtime riêng, không chạy bên trong HotSpot. Những tính năng chẩn đoán như JFR, heap dump, Native Memory Tracking (NMT), Java Diagnostic Command (jcmd) và JVMStat cần được đưa vào binary ở thời điểm build. Sau đó ứng dụng mới có thể bật recording, tạo dump hoặc nhận lệnh chẩn đoán khi chạy.

Bài học này giải thích cách bật và sử dụng JFR, heap dump, NMT và jcmd cho Spring Boot Native Image; phân biệt heap của Java với bộ nhớ tiến trình; chỉ ra các giới hạn theo phiên bản và nền tảng; đồng thời kết hợp chúng với metrics, logs và traces của Spring Boot Actuator để xây dựng quy trình quan sát production.

## 1. Vì sao cần phân biệt công cụ quan sát?

Mỗi công cụ trả lời một câu hỏi khác nhau. Dùng sai công cụ có thể khiến nhóm vận hành kết luận sai nguyên nhân sự cố.

| Công cụ | Câu hỏi chính | Dữ liệu nhận được |
|---|---|---|
| JFR | CPU, allocation, GC, thread và event thay đổi như thế nào theo thời gian? | Bản ghi sự kiện có timestamp, stack trace ở những event hỗ trợ |
| Heap dump | Những object nào đang còn sống trong Java heap tại thời điểm chụp? | Snapshot object graph ở định dạng HPROF |
| NMT | Runtime Native Image đang theo dõi những vùng native memory nào và dùng bao nhiêu? | Báo cáo phân loại native memory được runtime theo dõi |
| jcmd | Có thể yêu cầu process cung cấp thông tin hoặc thực hiện thao tác chẩn đoán nào? | Thread dump, heap dump, JFR control, VM information và NMT report |
| Actuator/Micrometer | Service đang xử lý bao nhiêu request, latency/error ra sao và metric biến động thế nào? | Metrics định kỳ và dữ liệu có thể export sang monitoring backend |
| Logs và traces | Request cụ thể đi qua những thành phần nào và lỗi xuất hiện ở đâu? | Log events và distributed traces |

JFR phù hợp để tìm thời điểm CPU tăng, GC dày hoặc allocation bất thường. Heap dump hữu ích khi cần tìm object giữ tham chiếu và làm Java heap tăng. NMT giúp quan sát phần native memory mà runtime có thể theo dõi. Metrics và traces của Spring Boot phù hợp để giám sát liên tục ở cấp service.

Không có một file dump nào thay thế được tất cả các nguồn dữ liệu trên.

## 2. Các tính năng chẩn đoán phải được bật lúc build

Native Image chỉ chứa những tính năng monitoring đã được chọn khi chạy native-image builder. Ví dụ:

~~~bash
native-image \
  --enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat \
  -jar application.jar
~~~

Tùy chọn `--enable-monitoring` nhận danh sách tính năng, phân cách bằng dấu phẩy. Các giá trị thường dùng:

| Tính năng | Giá trị | Mục đích |
|---|---|---|
| JDK Flight Recorder | `jfr` | Ghi event và profiling |
| Heap dump | `heapdump` | Tạo snapshot Java heap |
| Native Memory Tracking | `nmt` | Theo dõi native memory mà runtime hỗ trợ |
| Java Diagnostic Command | `jcmd` | Nhận lệnh chẩn đoán qua công cụ jcmd |
| JVMStat | `jvmstat` | Hỗ trợ công cụ phát hiện và liệt kê process, ví dụ VisualVM hoặc jcmd -l |
| JMX server/client | `jmxserver`, `jmxclient` | Kết nối JMX trong các tình huống được hỗ trợ; cần kiểm tra giới hạn và tính experimental |

Các giá trị được hỗ trợ có thể thay đổi theo GraalVM version và distribution. Hãy kiểm tra tài liệu của đúng toolchain trước khi cấu hình.

**Runtime flag không thể bổ sung tính năng đã bị loại khỏi binary.** Ví dụ, truyền `-XX:StartFlightRecording` khi binary được build không có JFR support không làm JFR xuất hiện. Nếu cần JFR hoặc heap dump sau khi phát hành, phải build lại artifact với tính năng tương ứng.

Không nhất thiết bật tất cả tính năng cho mọi service. Chọn theo nhu cầu vận hành, kích thước binary, chi phí build và nền tảng triển khai.

## 3. Cấu hình monitoring trong Gradle

Nếu dự án dùng GraalVM Native Build Tools Gradle plugin, thêm các build argument vào binary chính:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

Sau đó build native executable:

~~~bash
./gradlew nativeCompile
~~~

Nếu dự án dùng Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

Đây là cấu hình ở build time. Nếu chỉ muốn JFR trong một biến thể chẩn đoán, có thể tạo build profile hoặc binary riêng, miễn là pipeline quản lý rõ artifact nào được triển khai. Cần tránh để test và production vô tình dùng hai binary khác nhau mà không biết tính năng monitoring nào đã được đưa vào.

## 4. Cấu hình monitoring trong Maven

Với GraalVM Native Build Tools Maven plugin, thêm build argument vào cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Build theo profile native của dự án:

~~~bash
./mvnw -Pnative package
~~~

Ví dụ trên giả định dự án đã cấu hình plugin và profile native. Nếu plugin được kế thừa từ parent POM, hãy kiểm tra cách merge `buildArgs` để chắc chắn tùy chọn không bị ghi đè. Native Build Tools yêu cầu mỗi `buildArg` là một biểu thức tùy chọn Native Image; không gộp nhiều lệnh shell vào cùng một phần tử.

## 5. JDK Flight Recorder trong Native Image

JFR ghi lại event theo thời gian để hỗ trợ phân tích CPU, allocation, GC, thread, lock contention và hoạt động của process. Native Image hỗ trợ API `jdk.jfr.Event` cùng nhiều event hệ thống, nhưng tập event không hoàn toàn giống HotSpot.

Để bật JFR, binary phải được build với:

~~~text
--enable-monitoring=jfr
~~~

Khởi động ứng dụng và bắt đầu recording:

~~~bash
./application \
  -XX:StartFlightRecording="filename=/diagnostics/orders.jfr,duration=5m,maxsize=256M,dumponexit=true"
~~~

Các tham số quan trọng:

- `filename`: đường dẫn file recording.
- `duration`: thời lượng recording, ví dụ `5m` hoặc `300s`.
- `maxsize`: giới hạn dung lượng file.
- `maxage`: giới hạn thời gian lưu event.
- `dumponexit`: dump recording khi process kết thúc.
- `settings`: file cấu hình JFR như `default.jfc` hoặc `profile.jfc`, nếu profile đó tương thích với runtime.

Thư mục `/diagnostics` phải tồn tại và user chạy container phải có quyền ghi. Với container production, nên mount volume riêng để lưu file thay vì ghi vào filesystem tạm hoặc layer container có thể bị xóa.

## 6. Đọc và phân tích file JFR

Sau khi có file `orders.jfr`, dùng công cụ `jfr` đi kèm JDK để xem tổng quan:

~~~bash
jfr summary /diagnostics/orders.jfr
~~~

In các event cần phân tích:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection /diagnostics/orders.jfr
~~~

Có thể mở file bằng JDK Mission Control hoặc VisualVM để xem timeline, method profile, allocation và thread. JFR snapshot từ Native Image có thể chứa stack trace cho các event hỗ trợ; event streaming lại có giới hạn riêng.

Một quy trình phân tích cơ bản:

1. Xác định khoảng thời gian người dùng báo latency tăng.
2. Tìm event `jdk.ExecutionSample` để xem method nào tiêu thụ CPU.
3. Xem event GC và heap summary để xác định GC có xảy ra thường xuyên hoặc pause kéo dài không.
4. Kiểm tra allocation sample để tìm nơi tạo nhiều object.
5. Đối chiếu thread, lock và socket events với log/trace của request.
6. So sánh cùng workload trước và sau khi thay đổi code hoặc cấu hình.

Không kết luận ứng dụng bị memory leak chỉ từ một snapshot có heap lớn. Cần so sánh nhiều thời điểm, quan sát xu hướng object sống lâu và xác minh đường tham chiếu giữ object.

## 7. Những giới hạn cần biết của JFR

JFR trên Native Image không phải bản sao hoàn chỉnh của JFR trên HotSpot.

Một số giới hạn quan trọng:

- Một số event chỉ có khi dùng Serial GC; Serial GC là collector mặc định trong nhiều cấu hình Native Image.
- Các event Java được HotSpot tạo bằng bytecode instrumentation, ví dụ một số event file I/O hoặc exception, chưa có đầy đủ trên Native Image.
- `jdk.OldObjectSample` chỉ hỗ trợ một phần; thông tin đường đi tới GC root không có đầy đủ như mong đợi ở HotSpot.
- JFR event streaming có thể cung cấp callback liên tục, nhưng stack trace chưa có sẵn trong callback; stack trace trong file snapshot vẫn có thể hoạt động với event hỗ trợ.
- Remote JMX để điều khiển `FlightRecorderMXBean` cần bật riêng và được tài liệu mô tả là experimental.
- JFR profiling sampler phụ thuộc hệ điều hành và cơ chế lấy mẫu. Trên Windows, sampler dựa vào POSIX `SIGPROF` không có; runtime dùng cơ chế recurring-callback được tài liệu hỗ trợ.

Vì vậy, khi một event không xuất hiện, hãy kiểm tra event đó có được hỗ trợ trên phiên bản, GC và nền tảng đang chạy hay không trước khi nghi ngờ code ứng dụng.

## 8. Khác biệt JFR giữa các phiên bản và hệ điều hành

Khả năng JFR đã thay đổi qua các bản GraalVM. Tài liệu GraalVM 25.5 (Innovation) hiện ghi nhận Windows hỗ trợ recording cục bộ ra file `.jfr`. Remote JMX tới `FlightRecorderMXBean` và điều khiển JFR qua `jcmd` chưa có trên Windows. Tài liệu Oracle GraalVM cho JDK 25.0 vẫn có ghi chú rằng JFR recording chưa khả dụng trên Windows.

Điều này cho thấy không nên lấy một bảng hỗ trợ cũ áp dụng cho mọi distribution.

| Nền tảng | JFR local file | Remote JMX/JFR qua jcmd | Lưu ý |
|---|---|---|---|
| Linux | Có trong các bản GraalVM hỗ trợ JFR | Có khi build thêm tính năng tương ứng | Có thể dùng sampler dựa trên POSIX signal nếu phiên bản hỗ trợ |
| macOS | Có trong các bản GraalVM hỗ trợ JFR | Kiểm tra phiên bản và cấu hình JMX/jcmd | Kiểm tra quyền ghi file và profiler |
| Windows với GraalVM 25.5 | Có thể ghi local recording theo tài liệu 25.5 | Remote JMX và jcmd chưa có | Dùng recurring-callback sampler |
| Windows với một số bản GraalVM JDK 25.0 hoặc cũ hơn | Tài liệu tương ứng có thể ghi JFR chưa hỗ trợ | Không nên giả định có | Đối chiếu đúng distribution/version |

Khi nâng GraalVM, hãy chạy một smoke test JFR trên đúng OS/architecture của artifact phát hành. Đừng chỉ kiểm tra rằng native compilation thành công; cần xác nhận file recording thực sự được tạo và mở được bằng công cụ phân tích.

## 9. Heap dump trong Native Image

Heap dump là snapshot của các object trong **Java heap được quản lý bởi garbage collector**. Nó giúp trả lời:

- Object nào đang còn sống?
- Collection hoặc cache nào đang giữ nhiều object?
- Có nhiều object cùng kiểu bất thường không?
- Một object graph có giữ tham chiếu tới dữ liệu không còn cần thiết không?
- Sau một chu kỳ xử lý, heap có giảm khi GC chạy hay tiếp tục tăng?

Để bật heap dump support, build với:

~~~text
--enable-monitoring=heapdump
~~~

Heap dump native có thể được tạo theo một số cách: khi Java heap hết bộ nhớ, bằng công cụ quản trị, bằng tín hiệu hệ điều hành trên nền tảng hỗ trợ hoặc qua API của GraalVM.

**Heap dump không phải ảnh chụp toàn bộ RSS của process.** Nó tập trung vào object heap. Thread stack, executable image, shared library, memory mapping và một số vùng native memory cần được quan sát bằng NMT hoặc công cụ hệ điều hành.

## 10. Tự động dump khi OutOfMemoryError

Cách đơn giản nhất là bật `-XX:+HeapDumpOnOutOfMemoryError`:

~~~bash
./application \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/diagnostics/orders-heap.hprof
~~~

Khi native executable phát sinh `OutOfMemoryError` do Java heap không còn đủ chỗ, runtime sẽ cố gắng ghi heap dump. Theo tài liệu GraalVM, nếu không chỉ định đường dẫn, file mặc định có dạng `svm-heapdump-<PID>-OOME.hprof` trong working directory.

Hãy kiểm tra:

- Đường dẫn tồn tại.
- Process có quyền ghi.
- Volume có đủ dung lượng.
- Chính sách retention không xóa file trước khi điều tra.
- File dump được bảo vệ vì có thể chứa token, thông tin cá nhân, request payload hoặc dữ liệu nhạy cảm.

Heap dump có thể rất lớn và tạo thêm áp lực I/O. Đừng ghi nó vào volume production có dung lượng hạn chế mà không có quota/retention.

## 11. Tạo heap dump theo yêu cầu

Có thể yêu cầu dump heap ban đầu và thoát bằng:

~~~bash
./application -XX:+DumpHeapAndExit
~~~

Cách này hữu ích để xem object được đưa vào initial heap của image, ví dụ object được khởi tạo lúc build time. Nó không đại diện cho heap sau khi service xử lý traffic production.

Trên Linux và macOS, có thể gửi `SIGUSR1` tới process đang chạy để tạo heap dump:

~~~bash
kill -USR1 <PID>
~~~

Với Docker, có thể gửi signal tới process trong container:

~~~bash
docker kill --signal=USR1 orders-native
~~~

Cơ chế signal này không có trên Windows. Nó cũng yêu cầu Signal API của GraalVM; API được bật mặc định trong các trường hợp thông thường nhưng có thể khác khi build shared library.

Một ứng dụng có thể gọi API `org.graalvm.nativeimage.VMRuntime.dumpHeap` để tạo dump theo điều kiện do ứng dụng kiểm soát. Cách này phù hợp với diagnostic endpoint nội bộ hoặc thao tác quản trị được bảo vệ, nhưng cần kiểm tra API của GraalVM version đang dùng.

## 12. Dùng VisualVM để chụp heap dump

VisualVM có thể mở file HPROF được tạo bởi Native Image. Để VisualVM phát hiện process đang chạy, build thêm `jvmstat`:

~~~text
--enable-monitoring=heapdump,jvmstat
~~~

Trên Linux/macOS, VisualVM có thể liệt kê Native Image process và yêu cầu heap dump theo cách tương tự khi làm việc với ứng dụng JVM.

Trên Windows, VisualVM có thể mở file heap dump được tạo ở nền tảng khác, nhưng tài liệu Native Image JDK 25 nêu việc tạo heap dump từ process Native Image đang chạy trên Windows không được hỗ trợ. Đừng nhầm khả năng mở file HPROF với khả năng yêu cầu process Windows tạo file đó.

Khi điều tra, ghi lại thời điểm chụp, workload, số request, mức heap và trạng thái GC. Một heap dump không có bối cảnh thời gian rất khó so sánh với dump khác.

## 13. Phân tích heap dump và tránh kết luận sai

Sau khi mở file HPROF bằng VisualVM hoặc công cụ tương thích, có thể xem:

- Histogram theo class để tìm kiểu object chiếm nhiều instance/bytes.
- Dominator tree để tìm object giữ lượng dữ liệu lớn.
- Retained size để ước lượng vùng heap có thể giải phóng nếu một reference bị loại bỏ.
- Reference chain để tìm đường giữ object.
- So sánh hai snapshot ở cùng giai đoạn workload.

Ví dụ, nếu cache có hàng triệu entry, heap dump có thể cho thấy `ConcurrentHashMap` cùng object value chiếm phần lớn heap. Nhưng chưa đủ để kết luận cache bị leak: có thể cache được thiết kế không giới hạn hoặc test đang nạp dữ liệu lớn hơn bình thường.

Một quy trình tốt:

1. Chụp dump sau warm-up.
2. Chạy workload có kiểm soát trong một khoảng thời gian.
3. Chụp dump thứ hai sau khi workload kết thúc và GC đã có cơ hội chạy.
4. So sánh số lượng object và retained size.
5. Xác minh reference chain ở phía code giữ object.
6. Kiểm tra lại sau khi sửa và chạy cùng workload.

Nếu RSS tăng nhưng Java heap không tăng tương ứng, hãy xem NMT, native libraries, thread stacks, direct/native buffers và số liệu container thay vì chỉ dựa vào heap dump.

## 14. Native Memory Tracking để quan sát phần ngoài Java heap

Native Memory Tracking (NMT) theo dõi native memory mà runtime Native Image quản lý. Đây là phần quan trọng khi RSS của process lớn hơn nhiều so với Java heap.

Bật NMT lúc build:

~~~text
--enable-monitoring=nmt
~~~

In báo cáo khi process kết thúc:

~~~bash
./application -XX:+PrintNMTStatistics
~~~

Trong Native Image, NMT được bật khi đã đưa vào build và không có cơ chế bật/tắt runtime giống HotSpot. NMT có overhead tương đối nhỏ so với JFR theo tài liệu GraalVM.

Giới hạn hiện hành cần nhớ:

- Native Image hỗ trợ NMT summary; detailed mode và baseline comparison của HotSpot chưa có đầy đủ.
- NMT chỉ theo dõi các vùng allocation mà runtime có thể quan sát.
- Lệnh `malloc` trực tiếp từ code native hoặc thư viện JNI có thể không được tính vào báo cáo.
- NMT không thay thế số đo RSS/cgroup từ hệ điều hành.

Vì vậy, hãy kết hợp NMT với container metrics và hệ điều hành khi điều tra memory footprint.

## 15. Kết hợp NMT với JFR

Native Image có thể phát event JFR về native memory khi cả JFR và NMT đều được bật:

~~~text
--enable-monitoring=jfr,nmt
~~~

Một số event liên quan:

- `jdk.NativeMemoryUsage`
- `jdk.NativeMemoryUsageTotal`
- `jdk.NativeMemoryUsagePeak`
- `jdk.NativeMemoryUsageTotalPeak`

Hai event có hậu tố Peak là event riêng của Native Image và được tài liệu đánh dấu experimental. Công cụ như JDK Mission Control có thể cần bật hiển thị experimental events.

Có thể lọc event trong recording:

~~~bash
jfr print --events jdk.NativeMemoryUsage,jdk.NativeMemoryUsagePeak /diagnostics/orders.jfr
~~~

Nếu không thấy event native memory, xác minh NMT có được bật khi build không và event đó có sẵn trong phiên bản GraalVM đang dùng không.

## 16. Dùng jcmd để điều khiển process native

Native Image hỗ trợ một tập lệnh Java Diagnostic Command (jcmd) trong các phiên bản có tính năng này. Tính năng bị tắt mặc định và phải được bật lúc build:

~~~text
--enable-monitoring=jcmd
~~~

Có thể kết hợp nhiều tính năng:

~~~text
--enable-monitoring=jcmd,jfr,heapdump,nmt,jvmstat
~~~

Lấy PID process rồi xem các lệnh được hỗ trợ:

~~~bash
jcmd <PID> help
~~~

Một số lệnh thường gặp:

| Lệnh | Tính năng build cần có | Công dụng |
|---|---|---|
| `Thread.print` | `jcmd` | In thread và stack trace |
| `Thread.dump_to_file` | `jcmd` | Ghi thread dump ra file |
| `GC.heap_dump` | `jcmd,heapdump` | Tạo HPROF heap dump |
| `JFR.start` | `jcmd,jfr` | Bắt đầu JFR recording |
| `JFR.stop` | `jcmd,jfr` | Dừng recording |
| `JFR.check` | `jcmd,jfr` | Xem recording đang hoạt động |
| `JFR.dump` | `jcmd,jfr` | Dump recording ra file |
| `VM.native_memory` | `jcmd,nmt` | In báo cáo native memory |
| `VM.command_line` | `jcmd` | Xem command line của process |
| `VM.system_properties` | `jcmd` | Xem system properties |
| `VM.uptime` | `jcmd` | Xem uptime |

Ví dụ bắt đầu và dump JFR:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile
jcmd <PID> JFR.dump name=incident filename=/diagnostics/incident.jfr
jcmd <PID> JFR.stop name=incident
~~~

Để `jcmd -l` tìm process dễ hơn, có thể bật thêm `jvmstat`. Trên Windows, tài liệu GraalVM hiện hành nêu jcmd Native Image chưa được hỗ trợ.

## 17. Khác biệt nền tảng của heap dump và jcmd

Các khả năng dưới đây là giới hạn đáng chú ý trong tài liệu GraalVM JDK 25/25.5 hiện hành. Hãy xác minh lại với distribution và patch version cụ thể.

| Khả năng | Linux | macOS | Windows |
|---|---|---|---|
| Heap dump support khi build với `heapdump` | Có | Có | Tài liệu JDK 25 ghi không hỗ trợ tạo heap dump |
| Heap dump theo `SIGUSR1` | Có | Có | Không có POSIX signal này |
| VisualVM yêu cầu heap dump từ process đang chạy | Có | Có | Không được hỗ trợ theo tài liệu JDK 25 |
| JFR local recording ở GraalVM 25.5 | Có | Có | Có, ghi file `.jfr` |
| JFR remote JMX qua FlightRecorderMXBean | Có thể bật riêng; experimental | Có thể bật riêng; experimental | Chưa hỗ trợ |
| JFR điều khiển qua jcmd | Có khi build `jcmd,jfr` | Có khi build `jcmd,jfr` | Chưa hỗ trợ |
| Native Memory Tracking | Có trong các bản hỗ trợ | Có trong các bản hỗ trợ | Kiểm tra release/platform cụ thể |

Tài liệu Oracle GraalVM JDK 25.0 có ghi chú JFR recording chưa có trên Windows, trong khi tài liệu GraalVM 25.5 Innovation cập nhật hỗ trợ local recording trên Windows. Khi dự án dùng JDK 25.0 hoặc một distribution khác, không áp dụng kết luận của 25.5 một cách tự động.

Đối với container Linux, cần kiểm tra thêm signal có được chuyển tới process đúng cách, volume dump có writable và PID namespace có làm thay đổi PID cần gửi lệnh hay không.

## 18. Phân biệt JFR và heap dump với Spring Boot Actuator

Spring Boot Actuator/Micrometer và GraalVM diagnostics bổ sung cho nhau:

| Nhu cầu | Công cụ nên dùng |
|---|---|
| Theo dõi request rate, latency, error rate, connection pool | Actuator/Micrometer |
| Export metrics định kỳ sang Prometheus/OTLP/backend | Micrometer registry |
| Phân tích CPU, allocation, GC và thread theo timeline | JFR |
| Tìm object còn sống và reference giữ object | Heap dump |
| Điều tra native memory runtime đang theo dõi | NMT |
| Lấy thread dump hoặc điều khiển JFR từ xa | jcmd/JMX khi phiên bản hỗ trợ |

Spring Boot có thể xuất metrics qua `/actuator/metrics` hoặc `/actuator/prometheus` khi đã thêm registry và expose endpoint. Các meter có sẵn phụ thuộc runtime và dependency. Hãy kiểm tra meter thực tế trong Native Image, không giả định mọi metric mang tên JVM trên HotSpot đều có cùng ý nghĩa trong native runtime.

Đặc biệt, tài liệu Actuator mô tả endpoint `heapdump` với định dạng HPROF trên HotSpot JVM và PHD trên OpenJ9. Điều đó không tự chứng minh endpoint này sẽ tạo heap dump đúng cách trong Native Image. Với native executable, dùng cơ chế `--enable-monitoring=heapdump` và xác minh trên đúng binary.

## 19. Bảo vệ file chẩn đoán trong production

JFR và heap dump có thể chứa dữ liệu nhạy cảm. JFR có thể ghi system properties, environment variables, socket events và thông tin về hoạt động ứng dụng. Heap dump có thể chứa object giữ token, session, request payload, dữ liệu khách hàng và nội dung cache.

Trước khi bật diagnostic capture trong production:

- Chọn thư mục riêng, quyền truy cập giới hạn.
- Dùng volume có dung lượng và retention policy rõ ràng.
- Không đặt file dump trong thư mục được phục vụ tĩnh qua web server.
- Không mở endpoint dump cho internet công cộng.
- Giới hạn người được tải hoặc đọc file.
- Mã hóa khi lưu/truyền theo chính sách tổ chức.
- Xóa file sau thời hạn điều tra.
- Loại bỏ secrets khỏi log và metadata thu thập được khi có thể.

Không expose toàn bộ Actuator endpoint chỉ để lấy metrics hoặc heap dump. Chỉ mở endpoint cần thiết và bảo vệ bằng network policy hoặc Spring Security.

## 20. Runbook: điều tra tăng bộ nhớ trong Native Image

Giả sử container Spring Boot có RSS tăng dần sau nhiều giờ chạy. Thực hiện theo trình tự:

1. **Xác nhận số liệu:** đối chiếu RSS/cgroup memory, request rate, workload, heap metrics và thời điểm bắt đầu tăng.
2. **Xem JFR:** tìm allocation, GC, thread và event liên quan trong cùng khoảng thời gian.
3. **Chụp heap dump:** tạo hai snapshot ở hai thời điểm có workload tương đương.
4. **So sánh object graph:** tìm class tăng số lượng, retained size và reference chain.
5. **Kiểm tra NMT:** xác định phần native memory được runtime theo dõi có tăng tương ứng không.
6. **Kiểm tra JNI/native library:** nếu RSS tăng mà heap/NMT không giải thích được, điều tra allocation ở native code, direct buffer, mmap và thread stack.
7. **Đối chiếu metrics/traces:** tìm endpoint hoặc request tạo nhiều object, giữ session hoặc làm cache tăng.
8. **Sửa và chạy lại cùng workload:** xác nhận heap, RSS, latency và error rate ổn định hơn.

Không kết luận có memory leak chỉ vì RSS tăng. Native Image có thể giữ lại vùng heap đã reserve, allocator có thể không trả ngay memory cho OS và GC có thể làm RSS tăng tạm thời. Cần xem xu hướng qua nhiều chu kỳ và đối chiếu nhiều nguồn dữ liệu.

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `StartFlightRecording` không hoạt động | Binary không được build với `jfr` | Thêm `--enable-monitoring=jfr` và build lại |
| Không tạo được file JFR | Thư mục không tồn tại hoặc user không có quyền ghi | Kiểm tra path, volume và permission |
| JFR không có event mong đợi | Event không được hỗ trợ, GC khác hoặc code path chưa chạy | Kiểm tra event matrix và workload |
| Windows không kết nối được JFR qua jcmd | jcmd/JFR remote chưa hỗ trợ trên Windows | Ghi local JFR file nếu bản GraalVM hỗ trợ |
| Không tạo được heap dump khi OOME | Binary thiếu `heapdump` hoặc path không writable | Build với heapdump, kiểm tra HeapDumpPath |
| SIGUSR1 làm process kết thúc | Signal handler không được bật/hỗ trợ hoặc gửi sai PID | Xác minh Signal API, PID namespace và nền tảng |
| VisualVM không tìm thấy process | Thiếu jvmstat hoặc công cụ không tương thích | Build thêm jvmstat, kiểm tra local attach |
| Không thấy NMT report | Binary thiếu `nmt` hoặc chưa bật PrintNMTStatistics | Build với nmt và kiểm tra runtime flag |
| NMT thấp nhưng RSS cao | Allocation không được NMT theo dõi, ví dụ malloc trực tiếp trong JNI | Dùng OS/container metrics và native profiler |
| jcmd báo process không tồn tại | Sai PID, namespace hoặc thiếu jvmstat khi liệt kê | Lấy PID trong đúng host/container namespace |
| Actuator heapdump không hoạt động như mong đợi | Endpoint được tài liệu hóa cho HotSpot/OpenJ9 | Dùng native heapdump feature và test trực tiếp |

## 22. Bài thực hành: bật JFR, heap dump và NMT cho Spring Boot

Mục tiêu là tạo một native executable có đủ công cụ chẩn đoán để kiểm tra allocation, Java heap và native memory trên Linux.

### Bước 1 — Thêm monitoring options

Trong Gradle:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

Hoặc trong Maven:

~~~xml
<buildArgs>
    <buildArg>--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat</buildArg>
</buildArgs>
~~~

### Bước 2 — Build executable

~~~bash
./gradlew nativeCompile
~~~

Hoặc:

~~~bash
./mvnw -Pnative package
~~~

Ghi lại GraalVM version, JDK version, OS và architecture. Không dùng kết quả build trên một OS để kết luận công cụ hỗ trợ giống nhau trên OS khác.

### Bước 3 — Chạy JFR

~~~bash
mkdir -p diagnostics
./application \
  -XX:StartFlightRecording="filename=diagnostics/orders.jfr,duration=3m,maxsize=256M,dumponexit=true"
~~~

Gửi traffic test trong ba phút, sau đó xem:

~~~bash
jfr summary diagnostics/orders.jfr
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostics/orders.jfr
~~~

### Bước 4 — Kiểm tra heap dump khi OOME

Trong môi trường test riêng, chạy:

~~~bash
./application \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=diagnostics/orders-heap.hprof
~~~

Không cố tình làm production hết bộ nhớ để thử. Có thể dùng một workload test có giới hạn heap để xác nhận tính năng trước khi triển khai.

### Bước 5 — Kiểm tra NMT và jcmd

Khởi động ứng dụng với monitoring đã build, lấy PID rồi chạy:

~~~bash
jcmd <PID> help
jcmd <PID> VM.native_memory
jcmd <PID> Thread.print
~~~

Khi cần JFR qua jcmd:

~~~bash
jcmd <PID> JFR.start name=load-test settings=profile
jcmd <PID> JFR.dump name=load-test filename=diagnostics/load-test.jfr
jcmd <PID> JFR.stop name=load-test
~~~

### Bước 6 — Đọc kết quả và lưu bằng chứng

Ghi lại:

| Hạng mục | Bằng chứng |
|---|---|
| Native toolchain | GraalVM distribution, JDK, version |
| Target | OS, CPU architecture |
| Build flags | Các giá trị `--enable-monitoring` |
| JFR | File `.jfr`, thời lượng, event summary |
| Heap dump | File `.hprof`, thời điểm chụp, workload |
| NMT | Báo cáo native memory |
| jcmd | Các lệnh đã chạy và output |
| Runtime metrics | RSS/cgroup, heap, GC, latency, request rate |
| Bảo vệ dữ liệu | Vị trí lưu, quyền truy cập, retention |

## 23. Checklist trước khi phát hành native binary

- [ ] Đã xác định cần JFR, heap dump, NMT, jcmd hay chỉ metrics/logs.
- [ ] Đã thêm monitoring features vào build arguments.
- [ ] Đã build lại và kiểm tra đúng binary có chứa tính năng.
- [ ] Đã kiểm thử JFR trên đúng GraalVM version, OS và architecture.
- [ ] Đã xác minh heap dump hoạt động trên nền tảng mục tiêu.
- [ ] Đã kiểm tra jcmd/JMX và giới hạn remote access.
- [ ] Đã xác nhận volume, dung lượng và quyền ghi file diagnostics.
- [ ] Đã kiểm tra NMT không bị hiểu nhầm là toàn bộ RSS.
- [ ] Đã phân biệt Java heap, native memory và container memory.
- [ ] Đã kết hợp JFR/dump với Micrometer metrics, logs và traces.
- [ ] Đã giới hạn quyền truy cập và retention cho file chẩn đoán.
- [ ] Đã lưu version/toolchain/build flags cùng với artifact phát hành.

## 24. Ghi nhớ

JFR, heap dump, NMT và jcmd vẫn có thể hỗ trợ quan sát Spring Boot Native Image, nhưng cần được chọn và bật ở build time. JFR giúp phân tích event, CPU, allocation và GC theo thời gian; heap dump cho thấy object còn sống trong Java heap; NMT theo dõi một phần native memory; jcmd cung cấp các lệnh chẩn đoán mà binary đã chuẩn bị.

Khả năng hỗ trợ phụ thuộc GraalVM version, distribution và nền tảng. Đặc biệt, JFR local recording trên Windows đã thay đổi giữa tài liệu GraalVM JDK 25.0 và 25.5; heap dump native và jcmd vẫn có giới hạn Windows được tài liệu nêu rõ. Hãy test trên đúng artifact và môi trường triển khai.

Kết hợp các công cụ chẩn đoán sâu với Actuator/Micrometer, logs và traces. **Heap dump không phải toàn bộ process memory, NMT không theo dõi mọi allocation native, và JFR Native Image không có toàn bộ event của HotSpot.** Hiểu rõ phạm vi từng nguồn dữ liệu sẽ giúp nhóm vận hành tìm đúng nguyên nhân mà không đưa ra kết luận từ một chỉ số đơn lẻ.

### Tài liệu tham khảo

- GraalVM 25.5 — JDK Flight Recorder with Native Image: https://www.graalvm.org/jdk25.5/reference-manual/native-image/debugging-and-diagnostics/JFR/
- GraalVM 25.5 — Native Memory Tracking: https://www.graalvm.org/jdk25.5/reference-manual/native-image/debugging-and-diagnostics/NMT/
- Oracle GraalVM JDK 25.0 — JFR platform note: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/debugging-and-diagnostics/JFR/
- Oracle GraalVM JDK 25.0 — Heap dump platform note: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/guides/create-heap-dump/
- GraalVM — Create a Heap Dump from a Native Executable: https://www.graalvm.org/dev/reference-manual/native-image/guides/create-heap-dump/
- GraalVM — Java Diagnostic Command with Native Image: https://www.graalvm.org/dev/reference-manual/native-image/debugging-and-diagnostics/jcmd/
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html

Các tùy chọn monitoring và giới hạn nền tảng thay đổi theo GraalVM release. Khi triển khai, hãy pin toolchain và đối chiếu tài liệu đúng distribution/version đang dùng.
