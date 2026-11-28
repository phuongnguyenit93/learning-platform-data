# Xác minh hỗ trợ collector và công cụ chẩn đoán trên bản JDK phân phối

Khả năng chọn garbage collector (GC) và dùng công cụ chẩn đoán phụ thuộc vào JVM implementation, nhà cung cấp JDK, phiên bản, hệ điều hành và cách runtime được đóng gói. Hai bản JDK cùng ghi Java 25 không nhất thiết có cùng collector hoặc cùng bộ công cụ. Trước khi cấu hình production, cần xác định VM thực tế, kiểm tra các tùy chọn được hỗ trợ, xác nhận collector đang chạy và thử các lệnh chẩn đoán trên đúng tiến trình ứng dụng.

Các ví dụ HotSpot trong bài sử dụng những collector và công cụ còn được duy trì trên JDK hiện đại. Java 16 là feature release đã qua thời gian hỗ trợ thông thường; với production, hãy dùng JDK LTS còn được nhà cung cấp duy trì và kiểm tra tài liệu của đúng bản phân phối. Không áp dụng máy móc các cờ HotSpot cho OpenJ9 hoặc một JVM implementation khác.

## 1. Vì sao phải xác minh trên đúng bản phân phối JDK?

JDK là một bản phân phối gồm JVM, thư viện Java và các công cụ. Nhà cung cấp có thể chọn HotSpot hoặc một VM implementation khác, bật/tắt một số tính năng theo nền tảng, và đóng gói bộ công cụ khác nhau giữa JDK đầy đủ, JRE và runtime image tối giản.

Các khác biệt thường gặp:

- **VM implementation:** HotSpot và OpenJ9 có tập cờ GC, cơ chế log và diagnostic command khác nhau.
- **Collector được build:** một bản HotSpot có thể cung cấp Shenandoah, trong khi bản phân phối khác không tích hợp collector này.
- **OS/CPU:** một collector có thể chỉ được nhà cung cấp hỗ trợ trên một số tổ hợp Linux, Windows, macOS, x64 hoặc ARM64.
- **Bộ công cụ:** JDK đầy đủ thường có `jcmd`, `jfr` và các công cụ khác; JRE hoặc runtime image được tạo tối giản có thể không có.
- **Phiên bản:** cờ và chế độ GC có thể thay đổi giữa các major release. Ví dụ, ZGC trên JDK hiện đại chỉ còn chế độ generational.

Do đó, cần lưu lại vendor, version, VM name, OS/architecture và danh sách công cụ khi tạo image hoặc triển khai service.

## 2. Xác định JVM implementation và phiên bản đang chạy

Chạy các lệnh sau trên chính môi trường sẽ chạy ứng dụng:

```sh
java -version
java -XshowSettings:properties -version
```

Các thông tin quan trọng gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `java.vendor` | Nhà cung cấp JDK |
| `java.runtime.version` | Phiên bản runtime đầy đủ |
| `java.vm.name` | Tên VM implementation, thường nhận diện được HotSpot hoặc OpenJ9 |
| `java.vm.vendor` | Nhà cung cấp VM |
| `os.name` | Hệ điều hành |
| `os.arch` | Kiến trúc tiến trình Java đang chạy |
| `java.home` | Runtime thực tế được JVM sử dụng |

Trên PowerShell, có thể lọc các thuộc tính:

```powershell
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.vendor|java.runtime.version|java.vm.name|java.vm.vendor|java.home|os.name|os.arch'
```

Trên Linux/macOS:

```sh
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.vendor|java.runtime.version|java.vm.name|java.vm.vendor|java.home|os.name|os.arch'
```

Nếu `java.vm.name` không cho biết HotSpot, không dùng các ví dụ `-XX:+UseG1GC`, `-Xlog:gc*` hoặc lệnh `jcmd` đặc thù HotSpot trước khi kiểm tra tài liệu của VM đó. Tên lệnh `java` giống nhau không có nghĩa mọi JVM đều dùng chung tùy chọn.

## 3. Những collector HotSpot còn được dùng trên JDK hiện đại

Các collector phổ biến của HotSpot có mục tiêu khác nhau. Tên và cờ dưới đây là cờ HotSpot; chỉ sử dụng khi bản JDK phân phối có hỗ trợ collector đó.

| Collector | Cờ chọn trên HotSpot | Đặc điểm chính | Workload thường cân nhắc |
|---|---|---|---|
| Serial GC | `-XX:+UseSerialGC` | GC chạy tuần tự trên một luồng; footprint và overhead thấp | Ứng dụng nhỏ, heap nhỏ hoặc môi trường ít CPU |
| Parallel GC | `-XX:+UseParallelGC` | Dừng ứng dụng trong các pha GC nhưng tận dụng nhiều luồng để tăng throughput | Batch, xử lý nền hoặc workload ưu tiên throughput |
| G1 GC | `-XX:+UseG1GC` | Thu gom theo region, kết hợp xử lý song song và concurrent; cân bằng throughput với pause time | Server application tổng quát; thường là lựa chọn mặc định trên máy server-class của HotSpot |
| ZGC | `-XX:+UseZGC` | Collector concurrent, hướng đến pause rất ngắn; có thể tiêu thụ thêm CPU để đạt độ trễ thấp | Dịch vụ nhạy latency, heap lớn hoặc yêu cầu pause thấp |
| Shenandoah | `-XX:+UseShenandoahGC` | Collector concurrent với mục tiêu pause thấp; mức hỗ trợ tùy bản build | Dịch vụ cần pause thấp khi JDK phân phối có Shenandoah |

G1 thường là mặc định trên cấu hình server-class của HotSpot, còn Serial có thể được chọn ở cấu hình nhỏ hơn. Không nên giả định mặc định giống nhau ở mọi máy hoặc mọi vendor; hãy xem cờ runtime và GC initialization log.

### Các cập nhật cần biết ở JDK hiện đại

- ZGC có chế độ generational từ JDK 21; generational trở thành mặc định ở JDK 23 và chế độ non-generational đã bị loại bỏ ở JDK 24. Trên JDK 24+, `-XX:+UseZGC` chọn ZGC generational.
- Generational Shenandoah trở thành product feature trong JDK 25. Nếu bản JDK có hỗ trợ, có thể bật bằng `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational`.
- Shenandoah không có trong mọi bản phân phối. Ví dụ, một số bản JDK của nhà cung cấp có thể không tích hợp nó dù cùng dựa trên OpenJDK/HotSpot.
- CMS và các cờ liên quan như `-XX:+UseConcMarkSweepGC` thuộc hướng dẫn cũ; CMS đã bị loại khỏi HotSpot từ JDK 14. Không sao chép cấu hình CMS/ParNew từ tài liệu Java cũ vào runtime hiện nay.

## 4. Chọn collector theo mục tiêu, không theo tên gọi

Collector không có một thứ hạng hiệu năng cố định. Cần đo trên workload đại diện, với cùng heap, CPU limit, tốc độ cấp phát, tập dữ liệu sống và mức tải.

| Mục tiêu chính | Điểm bắt đầu để thử | Chỉ số cần theo dõi |
|---|---|---|
| Footprint thấp, ứng dụng nhỏ | Serial | RSS, heap committed, thời gian pause và CPU |
| Throughput cao, chấp nhận pause dài hơn | Parallel | Requests/second hoặc records/second, CPU, tổng thời gian GC |
| Cân bằng cho service tổng quát | G1 | p95/p99 latency, pause distribution, throughput, heap occupancy |
| Pause thấp cho service nhạy latency | ZGC hoặc Shenandoah nếu có | p99/p999 latency, pause max, CPU overhead, allocation rate và footprint |

Quy trình lựa chọn:

1. Chạy với collector mặc định của JDK và ghi nhận baseline.
2. Đặt heap limit thực tế, bao gồm giới hạn container và native memory.
3. Thu GC log hoặc JFR trong cùng một kịch bản tải.
4. Thử collector khác khi baseline không đáp ứng mục tiêu.
5. So sánh throughput, latency tail, CPU, RSS, allocation rate và pause time.
6. Lặp lại trên đúng JDK vendor, kiến trúc và runtime image sẽ triển khai.

Không chọn ZGC hoặc Shenandoah chỉ vì tên gọi “low pause”. Collector concurrent có thể sử dụng nhiều CPU hơn và làm thay đổi throughput. Kết quả cần được đánh giá theo SLO của ứng dụng.

## 5. Xác minh collector có trong bản JDK

### Liệt kê các cờ GC

HotSpot có thể in danh sách VM flags:

```sh
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseSerialGC|UseParallelGC|UseG1GC|UseZGC|UseShenandoahGC|ShenandoahGCMode'
```

Trên PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String 'UseSerialGC|UseParallelGC|UseG1GC|UseZGC|UseShenandoahGC|ShenandoahGCMode'
```

Danh sách flag giúp biết VM có công bố tùy chọn tương ứng hay không và giá trị mặc định hiện tại. Tuy nhiên, việc một tên flag xuất hiện không thay thế cho bước khởi chạy thử collector trên đúng nền tảng.

### Thử khởi động VM với từng collector

Có thể kiểm tra khả năng nhận flag bằng lệnh `java -version`:

```sh
java -XX:+UseG1GC -Xlog:gc+init=info -version
java -XX:+UseParallelGC -Xlog:gc+init=info -version
java -XX:+UseSerialGC -Xlog:gc+init=info -version
java -XX:+UseZGC -Xlog:gc+init=info -version
```

Nếu bản build có Shenandoah và hỗ trợ chế độ generational trên JDK 25+:

```sh
java -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc+init=info \
  -version
```

Kết quả thành công cần cho thấy VM khởi động và log khởi tạo xác nhận collector mong muốn. Nếu xuất hiện `Unrecognized VM option`, `Option ... not supported` hoặc thông báo collector không có trong build, không dùng cờ đó trong cấu hình production. `-version` chỉ là kiểm tra khởi tạo cơ bản; sau đó vẫn cần chạy ứng dụng thử và quan sát collector thực tế.

### Xác minh cờ được chọn bởi VM

`PrintCommandLineFlags` hiển thị một số flag được VM chọn hoặc đặt qua ergonomics:

```sh
java -XX:+PrintCommandLineFlags -version
```

Khi ứng dụng đang chạy, có thể xem cờ của tiến trình bằng `jcmd` ở phần tiếp theo. Dùng GC initialization log để xác nhận collector thực sự được khởi tạo, đặc biệt khi cấu hình có nhiều cờ hoặc script launcher bổ sung tùy chọn.

## 6. Công cụ chẩn đoán có trong JDK

Trên HotSpot JDK, các công cụ thường dùng gồm:

| Công cụ | Công dụng |
|---|---|
| `jcmd` | Gửi diagnostic command đến JVM đang chạy; xem flags, heap, thread, JFR và thông tin VM |
| `jfr` | Tóm tắt và xuất nội dung file Java Flight Recorder |
| `jps` | Liệt kê JVM process có thể nhận diện trong môi trường hiện tại |
| `jstat` | Đọc một số bộ đếm GC/performance của HotSpot; hữu ích trong một số workflow giám sát hiện có |
| `jconsole` | Giám sát JVM qua JMX |
| `jhsdb` | Phân tích nâng cao, thường dùng cho core dump hoặc tiến trình bị treo |

Không phải mọi runtime image đều có đủ công cụ trên. JRE hoặc runtime image được tạo bằng `jlink` có thể đã lược bỏ các module công cụ để giảm kích thước. Hãy kiểm tra thư mục `bin` của runtime thực tế:

Linux/macOS:

```sh
command -v java
command -v jcmd
command -v jfr
command -v jps
```

Windows PowerShell:

```powershell
Get-Command java, jcmd, jfr, jps -ErrorAction SilentlyContinue |
    Select-Object Name, Source
```

Nếu runtime production không chứa công cụ, có thể dùng JDK diagnostic image riêng hoặc công cụ tương ứng từ cùng vendor/major version và cùng kiến trúc. Công cụ phải có quyền attach đến JVM mục tiêu và chạy trong môi trường nhìn thấy process đó.

## 7. Dùng jcmd làm điểm bắt đầu chẩn đoán

`jcmd` là công cụ ưu tiên cho nhiều tác vụ chẩn đoán HotSpot hiện đại. Nó cho phép hỏi chính tiến trình JVM về các lệnh mà VM đó hỗ trợ.

Liệt kê process:

```sh
jcmd -l
```

Xem lệnh có sẵn của một process:

```sh
jcmd 12345 help
```

Xem trợ giúp chi tiết của một lệnh:

```sh
jcmd 12345 help GC.heap_info
```

Các lệnh thường hữu ích:

```sh
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.info
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
```

Ý nghĩa:

- `VM.version`: phiên bản VM đang chạy.
- `VM.command_line`: đối số khởi động JVM.
- `VM.flags`: flag đang dùng; có thể dùng `VM.flags -all` để xem thêm trạng thái flag.
- `VM.info`: thông tin tổng quan của VM, hữu ích khi xác minh cấu hình runtime.
- `GC.heap_info`: thông tin heap và collector theo khả năng của VM.
- `Thread.print`: thread dump để tìm thread bị block, deadlock hoặc chờ tài nguyên.

Danh sách lệnh thay đổi theo JVM và phiên bản. Luôn dùng `jcmd PID help` trước khi dựa vào một diagnostic command cụ thể.

`jcmd` phải chạy trên cùng máy với JVM và thường cần cùng effective user/group với tiến trình mục tiêu. Trong container, `jcmd -l` trên host có thể không thấy JVM ở PID namespace riêng; chạy công cụ trong container hoặc cấu hình quyền/namespace phù hợp. Không mở quyền attach rộng hơn cần thiết trong production.

## 8. Bật GC log bằng Unified Logging

Với HotSpot JDK hiện đại, Unified Logging là cách chuẩn để ghi log GC và safepoint. Ví dụ:

```sh
java \
  -Xms2g -Xmx2g \
  -XX:+UseG1GC \
  '-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags' \
  -jar app.jar
```

Log có thể giúp trả lời:

- Collector nào được khởi tạo?
- Young, mixed hoặc full collection xảy ra khi nào?
- Pause kéo dài bao lâu và có ảnh hưởng đến latency không?
- Heap occupancy trước/sau collection thay đổi ra sao?
- Có allocation failure, evacuation failure hoặc concurrent cycle kéo dài không?
- Safepoint nào làm ứng dụng dừng và trong bao lâu?

Không nên bật mức log quá chi tiết trong thời gian dài nếu chưa đo overhead và dung lượng log. Cấu hình rotation/retention phù hợp, bảo đảm thư mục log có quyền ghi và không làm đầy filesystem.

Unified Logging với `-Xlog` là cú pháp HotSpot. Một JVM implementation khác có thể dùng cơ chế log riêng; không chuyển nguyên cấu hình `-Xlog:gc*` sang OpenJ9 hoặc VM khác nếu chưa kiểm tra tài liệu.

## 9. Dùng Java Flight Recorder để phân tích GC và ứng dụng

JDK Flight Recorder (JFR) ghi sự kiện runtime như GC, allocation, thread scheduling, lock contention, class loading và nhiều hoạt động khác. Có thể bắt đầu một recording trên JVM đang chạy bằng `jcmd`:

```sh
jcmd 12345 JFR.start \
  name=GCProfile \
  settings=profile \
  duration=60s \
  filename=gc-profile.jfr
```

Sau khi recording hoàn tất, xem tóm tắt:

```sh
jfr summary gc-profile.jfr
```

Lọc các sự kiện GC thường quan tâm:

```sh
jfr print \
  --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary \
  gc-profile.jfr
```

`settings=profile` thu thập nhiều dữ liệu hơn cấu hình mặc định; hãy đo overhead trên workload thực tế và tránh ghi dữ liệu nhạy cảm vào file recording. JFR có thể chứa thông tin về class, thread, đường dẫn hoặc hoạt động ứng dụng; bảo vệ file `.jfr` như một artifact vận hành có thể chứa dữ liệu nội bộ.

Một workflow thường dùng là bật GC log để quan sát liên tục, sau đó ghi JFR trong một khoảng thời gian tái hiện được vấn đề. Dùng JDK Mission Control (JMC) hoặc công cụ đọc JFR phù hợp để phân tích sâu hơn. JMC là công cụ riêng, không nên giả định mọi runtime image đều cài sẵn.

## 10. Native Memory Tracking và heap diagnostics

### Native Memory Tracking

Native Memory Tracking (NMT) của HotSpot theo dõi các nhóm cấp phát bộ nhớ nội bộ của JVM. Cần bật từ lúc khởi động:

```sh
java \
  -XX:NativeMemoryTracking=summary \
  -jar app.jar
```

Sau đó lấy thống kê:

```sh
jcmd 12345 VM.native_memory summary
```

NMT có thể giúp phân biệt mức dùng heap với một số nhóm native memory do JVM quản lý. Nó không theo dõi mọi allocation do thư viện native bên ngoài JVM thực hiện; khi điều tra JNI/native leak, vẫn cần công cụ của hệ điều hành hoặc profiler phù hợp. NMT có overhead, vì vậy chỉ bật khi có nhu cầu đo và đánh giá chi phí trên môi trường mục tiêu.

### Heap histogram và heap dump

Các lệnh sau có thể hữu ích khi điều tra object giữ lại nhiều bộ nhớ:

```sh
jcmd 12345 GC.class_histogram
jcmd 12345 GC.heap_dump heap.hprof
```

Đây là thao tác có thể tốn thời gian, CPU, I/O và dung lượng; heap dump thường gây tác động lớn và có thể chứa dữ liệu nhạy cảm trong object. Không chạy tùy tiện trên hệ thống đang chịu tải cao. Xem `jcmd 12345 help GC.class_histogram` hoặc `help GC.heap_dump` để kiểm tra option của phiên bản VM.

## 11. Theo dõi collector qua Java Management API

Ứng dụng có thể đọc thống kê collector qua `GarbageCollectorMXBean`. Cách này hữu ích để thu thập count và time vào metrics, nhưng tên collector là thông tin do implementation cung cấp, không phải định danh chuẩn để điều khiển logic nghiệp vụ.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class GcMetricsSnapshot {
    public static void main(String[] args) {
        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(
                    "collector=%s, count=%d, timeMs=%d%n",
                    gc.getName(),
                    gc.getCollectionCount(),
                    gc.getCollectionTime());
        }
    }
}
```

`getCollectionCount()` và `getCollectionTime()` có thể trả về giá trị âm nếu VM không cung cấp thống kê tương ứng. Thời gian được báo cáo là thời gian collection tích lũy theo định nghĩa của VM, không nhất thiết bằng toàn bộ thời gian pause quan sát được của request. Dùng GC log/JFR khi cần phân tích pause và phase chi tiết.

## 12. Khác biệt giữa HotSpot và OpenJ9

Các ví dụ collector flag và Unified Logging trong bài là ví dụ HotSpot. Một số bản phân phối Java dùng Eclipse OpenJ9, có collector, cờ và công cụ riêng. OpenJ9 có các GC policy và diagnostic tooling khác; không nên giả định `UseG1GC`, `UseZGC`, `ShenandoahGCMode` hoặc mọi lệnh HotSpot đều có.

Quy trình an toàn:

1. Đọc `java.vm.name` và `java.vm.vendor`.
2. Xem `java -X` và `java -XX:+PrintFlagsFinal -version` nếu VM hỗ trợ cách liệt kê tương ứng.
3. Kiểm tra `jcmd PID help` trên đúng tiến trình.
4. Dùng hướng dẫn GC/diagnostics của nhà cung cấp và VM implementation.
5. Chạy thử cờ trong môi trường staging với workload đại diện.

Nếu dùng bản phân phối HotSpot, vẫn cần kiểm tra collector cụ thể có được build và hỗ trợ trên target OS/CPU hay không. “Dựa trên OpenJDK” không bảo đảm mọi collector hoặc công cụ đều có trong mọi binary.

## 13. Runtime image tối giản và diagnostic sidecar

Một runtime image được tạo bằng `jlink` chỉ chứa các module đã chọn. Khi chỉ thêm `java.base` và module ứng dụng, các công cụ như `jcmd` hoặc `jfr` có thể không được đóng gói. Các module liên quan gồm `jdk.jcmd` và `jdk.jfr`; kiểm tra module graph và nội dung image thực tế trước khi quyết định thêm chúng.

Kiểm tra module trong runtime:

```sh
runtime/bin/java --list-modules
```

Kiểm tra công cụ:

```sh
ls runtime/bin/jcmd runtime/bin/jfr
```

Trên Windows, dùng `Get-ChildItem` trong `runtime\bin` để kiểm tra file `.exe`. Nếu production image cần nhỏ và không nên chứa công cụ chẩn đoán, có thể duy trì một diagnostic image riêng với JDK cùng vendor/major version và kiến trúc, rồi chạy nó trong môi trường có quyền attach hợp lệ. Không copy ngẫu nhiên `jcmd.exe` hoặc thư viện từ một JDK khác vào runtime image.

## 14. Quy trình xác minh trước khi phát hành

1. Ghi nhận JDK vendor, version, VM name, OS và architecture.
2. Xác nhận VM implementation là HotSpot hay một VM khác.
3. Liệt kê GC flags và thử khởi động collector cần dùng trên đúng binary.
4. Ghi GC initialization log để xác nhận collector được khởi tạo.
5. Chạy workload đại diện và so sánh throughput, pause, latency tail, CPU và RSS.
6. Xác nhận `jcmd`, `jfr` và các công cụ cần thiết có trong JDK/runtime image hoặc diagnostic image.
7. Thử `jcmd PID help`, `VM.flags`, `GC.heap_info` và JFR recording trong staging.
8. Kiểm tra NMT nếu cần, và bật từ lúc khởi động.
9. Đánh giá tác động của heap dump/histogram trước khi dùng trên production.
10. Ghi vendor/version, cờ GC, kết quả benchmark và lệnh chẩn đoán vào runbook vận hành.

Không đưa cờ GC mới vào production chỉ vì VM chấp nhận chúng. Một lựa chọn collector chỉ nên được chốt sau khi đo bằng ứng dụng, dữ liệu và giới hạn tài nguyên tương tự production.

## 15. Ghi nhớ

- Collector và diagnostic command phụ thuộc VM implementation, vendor, JDK version, OS/CPU và cách đóng gói runtime.
- HotSpot phổ biến có Serial, Parallel, G1 và ZGC; Shenandoah chỉ có ở những bản build tích hợp nó.
- ZGC trên JDK 24+ là generational; generational Shenandoah trở thành product feature từ JDK 25 nếu bản phân phối có hỗ trợ.
- CMS đã bị loại khỏi HotSpot; không dùng hướng dẫn hoặc cờ CMS cũ.
- Xác minh collector bằng flag list, thử khởi động và GC initialization log.
- Dùng `jcmd` để hỏi lệnh có sẵn và kiểm tra JVM đang chạy; dùng JFR/GC log để phân tích.
- NMT phải bật lúc khởi động và không theo dõi mọi native allocation bên ngoài JVM.
- Heap histogram và heap dump có thể gây tác động lớn, cần kiểm soát quyền truy cập file.
- Runtime image tối giản có thể không chứa công cụ; kiểm tra hoặc duy trì diagnostic image riêng.
- Đo collector trên workload thực tế trước khi chọn cho production.

## Tài liệu tham khảo

- [JDK 25 HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html) — collector, ergonomics và cách chọn GC.
- [Available Collectors in HotSpot](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html) — Serial, Parallel, G1, ZGC và hướng dẫn lựa chọn.
- [JDK 25 Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) — `jcmd`, JFR, NMT và các công cụ chẩn đoán.
- [jcmd Command Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — cú pháp, quyền attach và diagnostic commands.
- [JEP 490: ZGC — Remove the Non-Generational Mode](https://openjdk.org/jeps/490) — ZGC generational-only từ JDK 24.
- [JEP 521: Generational Shenandoah](https://openjdk.org/jeps/521) — generational Shenandoah thành product feature trong JDK 25.
- [Java 25: Generational Shenandoah release notes](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_eclipse_temurin_25/openjdk25-features) — hỗ trợ và cách bật chế độ generational trong bản phân phối OpenJDK 25.
