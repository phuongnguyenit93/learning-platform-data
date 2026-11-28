# Ghi lại môi trường, phần cứng và tiêu chí đánh giá

## Mục tiêu

Sau bài học này, bạn có thể:

- Lập hồ sơ môi trường chạy Java đủ chi tiết để người khác tái lập một lần đo.
- Phân biệt tài nguyên vật lý của máy với tài nguyên thực tế JVM được cấp trong container hoặc máy ảo.
- Thu thập thông tin JDK, JVM, hệ điều hành, phần cứng, ứng dụng và workload bằng công cụ phù hợp.
- Xây dựng phép đo riêng cho startup, warmup, throughput, latency, GC và mức sử dụng tài nguyên.
- Ghi đúng trạng thái tính năng Java 26 là chính thức, preview hay incubator cùng các cờ biên dịch và chạy cần thiết.

## 1. Vì sao phải ghi lại môi trường?

Một kết quả benchmark chỉ có ý nghĩa khi biết nó được tạo ra trong điều kiện nào. Cùng một JAR có thể cho kết quả khác đáng kể khi đổi JDK build, nhà cung cấp JDK, CPU, giới hạn container, hệ điều hành, GC, heap, dữ liệu đầu vào hoặc số luồng đồng thời.

Ví dụ, nếu một lần chạy Java 26 nhanh hơn Java 25, chưa thể kết luận nguyên nhân là JDK mới. Máy chạy Java 26 có thể được cấp nhiều CPU hơn, dùng bản JDK đã vá khác, có dữ liệu trong filesystem cache hoặc nhận workload nhẹ hơn. Khi nhiều yếu tố đổi cùng lúc, kết quả không còn chỉ ra được thay đổi nào tạo ra khác biệt.

Một hồ sơ benchmark nên trả lời được năm câu hỏi:

1. **Chạy cái gì?** Mã nguồn, commit, artifact, thư viện và cấu hình ứng dụng nào?
2. **Chạy ở đâu?** JDK, JVM, hệ điều hành, CPU, RAM, ổ đĩa và môi trường ảo hóa nào?
3. **Được cấp bao nhiêu tài nguyên?** Số CPU và giới hạn bộ nhớ thực tế mà tiến trình được phép sử dụng là bao nhiêu?
4. **Chạy theo cách nào?** Cấu hình JVM, workload, dữ liệu, mức đồng thời và trạng thái cache ra sao?
5. **Đánh giá bằng gì?** Chỉ số, cách lấy mẫu, số lần lặp và điều kiện đạt yêu cầu là gì?

Nên lưu hồ sơ cùng kết quả đo, mã nguồn benchmark và log. Khi chạy lại sau một bản cập nhật JDK hoặc thay đổi cấu hình, có thể so sánh hai hồ sơ để xác định nguyên nhân.

## 2. Ghi lại phần cứng và hệ điều hành

### CPU

Ghi tối thiểu:

- Tên và model CPU, kiến trúc (x86-64, AArch64...), thế hệ hoặc vi kiến trúc nếu xác định được.
- Số lõi vật lý và số CPU logic; ghi rõ có SMT/Hyper-Threading hay không.
- Tần số cơ bản và khả năng tăng xung; chế độ quản lý điện năng và nguy cơ thermal throttling.
- Cấu trúc NUMA nếu máy có nhiều node.
- Tập lệnh CPU có liên quan đến workload, đặc biệt các phần mở rộng SIMD nếu đánh giá Vector API.
- Giới hạn CPU do máy ảo, container hoặc bộ lập lịch áp dụng.

Không lấy số CPU logic làm số lõi vật lý. Cũng không mặc định JVM được dùng toàn bộ CPU của máy chủ. Một container có thể chạy trên máy 64 CPU nhưng chỉ được cấp quota tương đương 2 CPU.

### RAM

Ghi dung lượng RAM vật lý, dung lượng khả dụng khi bắt đầu thử nghiệm, tốc độ hoặc cấu hình bộ nhớ nếu cần phân tích hiệu năng, swap/pagefile và giới hạn bộ nhớ của container.

Phân biệt ba đại lượng:

- **RAM máy:** bộ nhớ vật lý được cài đặt trên host.
- **Giới hạn tiến trình/container:** mức bộ nhớ mà môi trường cho phép sử dụng.
- **Bộ nhớ JVM:** heap tối đa, heap đang dùng và bộ nhớ native ngoài heap.

Heap không bao gồm toàn bộ RSS của tiến trình. Metaspace, code cache, thread stack, direct buffer, thư viện native và các vùng native khác cũng dùng RAM. Vì vậy, chỉ ghi `-Xmx` là chưa đủ để đánh giá nguy cơ hết bộ nhớ.

### Lưu trữ

Ghi model hoặc loại ổ đĩa (NVMe, SSD SATA, HDD), filesystem, mount options đáng chú ý, dung lượng trống và vị trí của JDK, artifact, log cùng dữ liệu thử nghiệm.

Startup có thể bị ảnh hưởng bởi thời gian đọc JAR, lớp, thư viện native và AOT cache. Cần phân biệt lần chạy lạnh (dữ liệu chưa có trong filesystem page cache) với lần chạy ấm (dữ liệu đã được hệ điều hành giữ trong cache). Không xóa page cache trên máy dùng chung hoặc máy production chỉ để tạo phép đo lạnh; hãy dùng môi trường kiểm thử cô lập và mô tả rõ cách chuẩn bị trạng thái cache.

### Hệ điều hành và môi trường ảo hóa

Ghi tên, phiên bản, bản build và kiến trúc hệ điều hành; kernel trên Linux; loại máy ảo hoặc hypervisor nếu có; phiên bản runtime container; timezone và cấu hình đồng hồ nếu workload phụ thuộc thời gian.

Đối với benchmark mạng hoặc HTTP, cần ghi thêm vùng triển khai, đường mạng, DNS, proxy, độ trễ tới máy chủ và trạng thái TLS. Đối với benchmark CPU thuần, cần giữ máy ở cùng chế độ nguồn và tránh tác vụ nền gây tranh chấp CPU.

## 3. Thu thập thông tin trên từng hệ điều hành

Chạy lệnh trong đúng máy hoặc container nơi ứng dụng thực sự chạy. Các lệnh dưới đây chỉ thu thập thông tin; một số lệnh có thể cần quyền đọc hệ thống.

### Windows PowerShell

~~~powershell
Get-ComputerInfo |
  Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture, CsSystemType

Get-CimInstance Win32_Processor |
  Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed

Get-CimInstance Win32_OperatingSystem |
  Select-Object TotalVisibleMemorySize, FreePhysicalMemory

Get-CimInstance Win32_PhysicalMemory |
  Measure-Object -Property Capacity -Sum

Get-CimInstance Win32_DiskDrive |
  Select-Object Model, MediaType, InterfaceType, Size

Get-Volume |
  Select-Object DriveLetter, FileSystem, Size, SizeRemaining

Get-Process java |
  Select-Object Id, CPU, WorkingSet64, StartTime
~~~

Lệnh đo dung lượng RAM theo từng thanh trả về tổng ở thuộc tính `Sum` (đơn vị byte). `WorkingSet64` là working set hiện tại của tiến trình, không phải tổng bộ nhớ mà JVM đã cam kết sử dụng.

### Linux

~~~bash
uname -a
lscpu
free -h
lsblk -o NAME,MODEL,SIZE,ROTA,TRAN
df -hT
nproc
~~~

Nếu dùng cgroup v2, kiểm tra thêm các giới hạn sau (đường dẫn có thể khác theo cách cấu hình container):

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
~~~

Trong `cpu.max`, hai giá trị lần lượt là quota và period theo microsecond; ví dụ `200000 100000` tương đương giới hạn trung bình 2 CPU. Giá trị `max` biểu thị không đặt quota ở cấp đó. `memory.max` có thể là `max` nếu không có giới hạn tại cgroup đang đọc. Cgroup v1 có các đường dẫn và file giới hạn khác.

### macOS

~~~bash
sw_vers
uname -a
sysctl -n hw.model
sysctl -n hw.physicalcpu
sysctl -n hw.logicalcpu
sysctl -n hw.memsize
system_profiler SPHardwareDataType SPStorageDataType
df -h
~~~

Một số thuộc tính CPU khác nhau giữa máy Intel và Apple Silicon. Nếu một khóa `sysctl` không tồn tại, dùng thông tin từ `system_profiler` để ghi model và cấu hình tương ứng.

## 4. Ghi lại JDK, JVM và cấu hình chạy

Không chỉ ghi “Java 26”. Cần ghi nhà cung cấp, phiên bản đầy đủ, build number, kiến trúc, đường dẫn JDK và loại JVM. Hai bản JDK cùng số phiên bản nhưng khác vendor hoặc patch build vẫn có thể khác về sửa lỗi, tối ưu và cấu hình mặc định.

### Lệnh thu thập cơ bản

~~~bash
java -version
javac -version
java -XshowSettings:properties -version
java -XshowSettings:system -version
java --list-modules
~~~

Các lệnh giúp xác nhận phiên bản runtime/compiler, thuộc tính như `java.vendor`, `java.version`, `os.arch`, cấu hình hệ thống mà JVM nhận biết và các module có sẵn. Không cần lưu toàn bộ output công khai nếu nó chứa đường dẫn hoặc thông tin môi trường nội bộ; hãy lọc và che dữ liệu nhạy cảm trước khi chia sẻ.

Kiểm tra đường dẫn thực thi để tránh trường hợp terminal đang dùng một JDK khác với IDE hoặc service:

~~~powershell
Get-Command java | Select-Object Source
$env:JAVA_HOME
~~~

~~~bash
command -v java
echo "$JAVA_HOME"
~~~

Ghi lại các tùy chọn JVM thực tế: heap min/max, GC được chọn, cờ preview, module bổ sung, AOT cache, agents, system properties có ảnh hưởng đến ứng dụng, encoding, timezone và các cờ thử nghiệm. Có thể lưu danh sách cờ mặc định và cờ đã bật:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Đối với một JVM đang chạy, dùng `jcmd` từ cùng JDK và tài khoản có quyền attach phù hợp:

~~~bash
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> GC.heap_info
~~~

Thay `<pid>` bằng PID thực tế. Lệnh `VM.command_line` và system properties có thể chứa đường dẫn, token hoặc thông tin nhạy cảm; không đăng nguyên output lên issue hoặc báo cáo công khai. Không chạy attach diagnostics trong môi trường bị cấm attach hoặc khi thao tác có thể ảnh hưởng SLA.

### Trạng thái tính năng Java 26

JDK 26 là một feature release. Không nên giả định nó có thời hạn hỗ trợ LTS; thời gian cập nhật và hỗ trợ phụ thuộc nhà cung cấp JDK. Hồ sơ cần ghi rõ vendor, build, kênh phát hành và chính sách cập nhật của môi trường sử dụng.

Khi thử tính năng mới, ghi trạng thái của tính năng ngay trong hồ sơ:

| Trạng thái | Cách nhận biết và cách chạy | Điều cần lưu |
|---|---|---|
| Đã được chuẩn hóa (final) | Thuộc Java SE; không cần bật preview chỉ để sử dụng tính năng đó. | JDK tối thiểu, API và cấu hình liên quan. |
| Preview | Có thể cần `--enable-preview` khi biên dịch và chạy; chỉ có hiệu lực với đúng release hỗ trợ preview đó. | JDK release/build, lệnh compile/run, cảnh báo và giới hạn preview. |
| Incubator | API nằm trong module incubator; cần thêm module tương ứng, ví dụ `--add-modules jdk.incubator.vector`. | Tên module, phiên bản API, cờ module và cảnh báo incubator. |

Ví dụ, khi đo Vector API, ghi rõ module `jdk.incubator.vector`, cờ `--add-modules`, CPU và khả năng SIMD thực tế. Khi đo một tính năng preview như Structured Concurrency ở release đang thử nghiệm, ghi rõ `--enable-preview` trong cả bước biên dịch và chạy nếu yêu cầu của release đó quy định như vậy. Không lấy kết quả từ một bản preview để kết luận API đã ổn định hoặc tương thích với release sau.

## 5. Ghi lại ứng dụng và workload

Thông tin phần cứng và JDK vẫn chưa đủ nếu không biết chương trình đang được đo. Hồ sơ cần ghi:

- Repository, commit hash, nhánh và trạng thái working tree.
- Artifact (JAR hoặc image), checksum SHA-256, thời điểm build và phiên bản build tool.
- Phiên bản thư viện, plugin, native library và cấu hình ứng dụng.
- Dữ liệu đầu vào hoặc cách sinh dữ liệu, kích thước dữ liệu và seed ngẫu nhiên.
- Số request, số tác vụ, độ đồng thời, phân bố kích thước request và tỷ lệ lỗi.
- Cấu hình JVM, biến môi trường có liên quan và giới hạn tài nguyên.
- Endpoint, máy chủ phụ thuộc, cơ sở dữ liệu, cache, broker và dịch vụ bên ngoài được gọi trong phép đo.

Không đưa password, access token, private key, cookie, dữ liệu cá nhân hoặc nội dung bí mật vào hồ sơ. Ghi tên biến và nguồn cấu hình; thay giá trị bí mật bằng dấu che hoặc tham chiếu tới secret manager.

Cần giữ workload giống nhau khi so sánh. Một phép đo xử lý 10.000 request nhỏ không thể so trực tiếp với phép đo xử lý 10.000 request lớn. Nếu workload được sinh ngẫu nhiên, ghi seed và thuật toán sinh để có thể tái tạo.

## 6. Tiêu chí đánh giá hiệu năng

Chọn chỉ số dựa trên mục tiêu của ứng dụng. Không dùng một con số throughput để đại diện cho mọi khía cạnh hiệu năng.

| Chỉ số | Cách hiểu | Khi cần theo dõi |
|---|---|---|
| Startup to ready | Thời gian từ lúc tiến trình bắt đầu đến khi ứng dụng thực sự sẵn sàng nhận việc. | Khởi động service, autoscaling, serverless và AOT. |
| Warmup time | Thời gian để hiệu năng đạt vùng ổn định sau khi bắt đầu nhận workload. | JIT, profile và workload chạy lâu. |
| Throughput | Số tác vụ hoặc request hoàn tất trong một đơn vị thời gian. | Xử lý batch, server và workload đồng thời. |
| Latency p50/p95/p99 | Phân vị thời gian phản hồi; p99 phản ánh phần đuôi chậm của phân bố. | API, hệ thống tương tác và yêu cầu SLA. |
| CPU utilization | Mức CPU dùng trong khi chạy; cần đặt cạnh throughput. | Phân tích chi phí và khả năng mở rộng. |
| Heap, RSS, allocation rate | Bộ nhớ heap, bộ nhớ tiến trình và tốc độ cấp phát. | Workload tạo nhiều object, container có giới hạn RAM. |
| GC pause và GC CPU | Thời gian dừng, tần suất và CPU dành cho GC. | Đánh giá collector, độ trễ và throughput. |
| Error rate | Tỷ lệ lỗi, timeout, retry và request bị hủy. | Kiểm tra tính đúng và độ ổn định khi tải cao. |

Với phép đo startup, xác định mốc readiness bằng health check hoặc tín hiệu sẵn sàng của ứng dụng. Thời gian đến hàm `main` trả về không phản ánh đầy đủ thời điểm service có thể nhận request.

Với latency, ghi phân vị trên cùng một cách lấy mẫu và cùng khoảng đo. Không lấy trung bình của các p99 theo từng batch để suy ra p99 tổng; cần tính phân vị trên tập mẫu phù hợp hoặc dùng công cụ đo có khả năng tổng hợp histogram chính xác.

## 7. Thiết kế phép so sánh có thể tái lập

Một quy trình so sánh cơ bản:

1. **Đặt câu hỏi và giả thuyết.** Ví dụ: “JDK 26 giảm thời gian từ process start đến readiness với cùng workload và giới hạn CPU/RAM”.
2. **Chọn baseline.** Ghi rõ JDK, artifact, cấu hình và số liệu hiện tại.
3. **Chỉ thay đổi một nhóm yếu tố.** Nếu đồng thời đổi JDK, GC, heap và thư viện, không thể xác định yếu tố nào tạo ra kết quả.
4. **Giữ workload và dữ liệu tương đương.** Cố định seed, số request, độ đồng thời, thời gian chạy và điều kiện phụ thuộc.
5. **Tách cold start và warm start.** Mô tả cách chuẩn bị filesystem cache, AOT cache và trạng thái ứng dụng.
6. **Chạy warmup và đo lường riêng.** Không gộp các vòng JIT warmup vào kết quả steady-state nếu mục tiêu là hiệu năng ổn định.
7. **Lặp lại bằng process/fork độc lập.** Đổi thứ tự baseline và candidate để giảm ảnh hưởng của nhiệt độ, tải nền hoặc biến động tài nguyên.
8. **Phân tích độ biến thiên.** Báo cáo số lần chạy, median hoặc trung bình phù hợp, độ phân tán và khoảng tin cậy nếu có.
9. **Kiểm tra tính đúng.** So sánh kết quả đầu ra, lỗi, timeout và dữ liệu nghiệp vụ để chắc rằng phiên bản nhanh hơn vẫn thực hiện cùng công việc.
10. **Lưu hồ sơ và log.** Lưu JDK build, cờ JVM, workload, kết quả thô và commit cùng báo cáo.

Đối với microbenchmark Java, ưu tiên JMH thay vì tự viết vòng lặp dùng `System.nanoTime()`. JMH xử lý nhiều vấn đề như warmup, fork, dead-code elimination và cách tổng hợp phép đo. Một lệnh ví dụ với benchmark JMH đã build:

~~~bash
java -jar target/benchmarks.jar -wi 5 -i 10 -f 3
~~~

Các giá trị warmup, measurement và fork trong ví dụ chỉ là điểm khởi đầu. Hãy điều chỉnh theo thời lượng chạy, độ ổn định và đặc điểm benchmark. Microbenchmark chỉ trả lời câu hỏi hẹp về đoạn mã; nó không thay thế phép đo end-to-end với workload thực tế.

### Phân biệt các trạng thái chạy

- **Cold process:** tiến trình JVM mới, chưa có JIT profile trong tiến trình đó.
- **Warm JVM:** tiến trình đã chạy workload đủ lâu để JIT tối ưu một phần đường thực thi.
- **Cold filesystem cache:** dữ liệu cần đọc chưa nằm trong page cache của hệ điều hành.
- **Warm filesystem cache:** dữ liệu đã được hệ điều hành cache; lần đọc sau có thể nhanh hơn.
- **AOT cache available:** tệp AOT tồn tại và JVM có thể nạp; cần kiểm tra log để xác nhận cache thực sự được dùng.

Các trạng thái này độc lập. Một tiến trình JVM mới vẫn có thể đọc JAR từ filesystem cache ấm. Một lần chạy có AOT cache cũng không mặc nhiên là cold hoặc warm ở cấp filesystem. Báo cáo phải ghi rõ trạng thái nào đang được so sánh.

## 8. Tiêu chí riêng theo nhóm cải tiến Java 26

### HTTP và HTTP Client

Khi đánh giá HTTP, ghi protocol thực tế đã thương lượng (HTTP/1.1, HTTP/2 hoặc HTTP/3 nếu môi trường và client/server hỗ trợ), phiên bản TLS, ALPN, DNS, proxy, connection reuse, keep-alive, compression, kích thước payload và số kết nối đồng thời.

Giữ cùng endpoint, server build, vị trí mạng và dữ liệu. Phân biệt thời gian thiết lập kết nối/TLS với thời gian gửi request trên kết nối đã tái sử dụng. Nếu thử HTTP/3, xác nhận giao thức thực sự được dùng ở cả hai đầu và ghi lại việc fallback nếu xảy ra; chỉ đặt tùy chọn client không chứng minh request đã chạy bằng HTTP/3.

### Pattern matching

Dùng cùng tập dữ liệu và cùng phân bố kiểu đầu vào khi so sánh các cách xử lý. Ghi tỷ lệ mỗi nhánh được chọn, trường hợp null, kích thước tập dữ liệu và trạng thái preview của tính năng đang thử. Với nhánh hiếm, cần workload đủ lớn để kết quả phản ánh phân bố thực tế.

### Structured Concurrency

Ghi số task, thời lượng task, độ lệch thời gian hoàn thành, tỷ lệ lỗi, timeout, hủy tác vụ và mức đồng thời. So sánh cùng semantics: thời điểm trả kết quả, quy tắc hủy, xử lý lỗi và thời gian chờ task con phải tương đương. Nếu API đang ở trạng thái preview, ghi JDK build và cờ preview; không kết luận về độ ổn định API từ benchmark.

### Vector API

Ghi CPU model, kiến trúc và tập lệnh SIMD được hỗ trợ, module incubator, loại vector được chọn và kích thước dữ liệu. Kiểm tra cả đường vector và đường scalar, xác nhận kết quả giống nhau và dữ liệu đủ lớn để lợi ích vector hóa có thể bù chi phí chuẩn bị. Một máy có CPU khác có thể chọn vector shape khác và cho kết quả khác.

### Bảo mật

Ghi security provider, thuật toán, kích thước khóa, loại keystore/truststore, TLS version, cipher suite và cấu hình xác thực. Đo riêng handshake mới với kết nối tái sử dụng; ghi chi phí mã hóa/giải mã, xác thực và kiểm tra chứng thư nếu đó là mục tiêu. Không ghi khóa, mật khẩu hoặc nội dung chứng thư riêng tư vào báo cáo.

### JVM và GC

Ghi GC được chọn, `-Xms`, `-Xmx`, số luồng, cờ JIT/AOT, các tùy chọn thay đổi object layout, container limits và log. Khi so sánh G1, ZGC hoặc collector khác, giữ workload và tài nguyên tương đương. Đo đồng thời throughput, tail latency, GC CPU, pause và RSS; một collector giảm pause nhưng tiêu thụ CPU hoặc RAM cao hơn có thể không phù hợp với mục tiêu triển khai.

## 9. Theo dõi runtime bằng JFR và log

Java Flight Recorder (JFR) có thể ghi sự kiện runtime như CPU, cấp phát, GC, thread và I/O với chi phí thường phù hợp cho phân tích hiệu năng. Ví dụ, bắt đầu một bản ghi ngắn trên tiến trình đang chạy:

~~~bash
jcmd <pid> JFR.start name=benchmark settings=profile filename=benchmark.jfr
# Run the representative workload, then stop the recording.
jcmd <pid> JFR.stop name=benchmark
jfr summary benchmark.jfr
~~~

Dùng cấu hình ghi phù hợp với mục tiêu và kiểm tra overhead của việc ghi. Không nên bật mọi sự kiện ở mức chi tiết cao trong phép đo cần độ chính xác tối đa nếu chưa đánh giá ảnh hưởng của profiler.

Để quan sát GC và safepoint, có thể bật unified logging:

~~~bash
java -Xlog:gc*,safepoint -jar app.jar
~~~

Khi so sánh, giữ cấu hình logging giống nhau ở baseline và candidate. Log có thể tăng I/O và làm thay đổi kết quả; nên có một lượt đo chính với instrumentation tối thiểu và lượt chẩn đoán riêng để tìm nguyên nhân.

## 10. Mẫu hồ sơ benchmark

Dùng mẫu dưới đây cho mỗi lần chạy. Có thể lưu dưới dạng Markdown hoặc YAML cùng artifact kết quả.

~~~yaml
benchmark:
  name: "java26-http-startup"
  objective: "Đo thời gian từ process start đến readiness"
  date_utc: "YYYY-MM-DDTHH:MM:SSZ"
  operator: "team-or-owner"

source:
  repository: "repository-url-or-name"
  commit: "git-commit"
  working_tree: "clean"
  artifact: "app.jar"
  sha256: "artifact-checksum"
  build_tool: "tool-and-version"

runtime:
  java_vendor: "vendor"
  java_version: "26"
  java_runtime_build: "full-build-string"
  java_home: "jdk-path"
  os_arch: "architecture"
  jvm: "HotSpot-or-other"
  gc: "selected-collector"
  jvm_args: ["-Xms...", "-Xmx..."]
  preview_flags: []
  incubator_modules: []
  aot_cache: "disabled-or-cache-identifier"

host:
  os: "name-version-build"
  kernel: "kernel-version-if-applicable"
  cpu_model: "processor-model"
  physical_cores: 0
  logical_cpus: 0
  memory_gib: 0
  storage: "device-and-filesystem"
  virtualization: "bare-metal-vm-container"

resource_limits:
  cpu_quota: "value-or-unlimited"
  cpu_set: "effective-cpu-set"
  memory_limit: "value-or-unlimited"
  swap_limit: "value-or-unlimited"

workload:
  scenario: "scenario-name"
  input_dataset: "dataset-version"
  seed: "fixed-seed-if-applicable"
  concurrency: 0
  duration_seconds: 0
  warmup_seconds: 0
  cache_state: "cold-or-warm-and-how-prepared"

results:
  startup_to_ready_ms: null
  warmup_to_target_seconds: null
  throughput_per_second: null
  latency_p50_ms: null
  latency_p95_ms: null
  latency_p99_ms: null
  cpu_percent: null
  rss_mib: null
  heap_max_mib: null
  allocation_rate: "value-and-unit"
  gc_pause_ms: null
  error_rate_percent: null

method:
  forks: 0
  repetitions: 0
  summary_statistic: "median-or-mean"
  variability: "standard-deviation-or-confidence-interval"
  logs: ["log-path"]
  notes: "known deviations and observations"
~~~

Thay các giá trị mẫu bằng dữ liệu thật. Nếu một trường không áp dụng, ghi `not-applicable`; nếu chưa thu thập, ghi `unknown`. Không để số 0 khiến người đọc hiểu nhầm là đã đo và kết quả bằng 0.

## 11. Đọc kết quả và quyết định

Một candidate chỉ nên được xem là cải thiện khi:

- Thực hiện cùng công việc và vượt qua kiểm tra tính đúng.
- Kết quả lặp lại được trong cùng điều kiện.
- Mức cải thiện lớn hơn độ nhiễu của phép đo.
- Đáp ứng mục tiêu quan trọng của hệ thống, chẳng hạn p99, startup hoặc throughput.
- Không tạo ra đánh đổi không chấp nhận được về CPU, RAM, lỗi, bảo mật hoặc khả năng vận hành.

Ví dụ, nếu startup giảm nhưng warmup dài hơn, cần xem mục tiêu triển khai có ưu tiên thời gian sẵn sàng ban đầu hay thời gian đạt hiệu năng ổn định. Nếu throughput tăng nhưng p99 xấu đi, hệ thống có thể không phù hợp với dịch vụ có SLA độ trễ nghiêm ngặt. Nếu benchmark chạy nhanh hơn trong máy phát triển nhưng chậm hơn trong container có quota thấp, phải đánh giá theo môi trường triển khai thực tế.

Khi kết quả không ổn định, kiểm tra tải nền, CPU throttling, GC, nhiệt độ, page cache, network jitter, DNS, kết nối phụ thuộc, dữ liệu đầu vào và sự khác nhau giữa các lần chạy. Không tùy tiện loại bỏ lần chạy chậm; hãy xác định nguyên nhân và ghi rõ quy tắc loại trừ trước khi thu thập dữ liệu.

## Kết luận

Một benchmark Java 26 có thể tái lập cần hồ sơ đầy đủ về JDK build, JVM flags, ứng dụng, hệ điều hành, CPU, RAM, storage, giới hạn container và workload. Tiêu chí đo phải khớp mục tiêu: startup đến readiness, warmup, throughput, latency, bộ nhớ, GC hoặc chi phí bảo mật. Với tính năng preview và incubator, cần ghi đúng release cùng cờ biên dịch/chạy và module; kết quả hiệu năng không chứng minh API đã ổn định. Khi giữ các điều kiện so sánh tương đương, lặp lại phép đo và lưu dữ liệu thô, nhóm có thể giải thích được thay đổi hiệu năng và đưa ra quyết định nâng cấp đáng tin cậy.

## Tài liệu tham khảo

- [JDK 26 Documentation](https://docs.oracle.com/en/java/javase/26/)
- [The java Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jcmd Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/26/jfapi/)
- [OpenJDK JMH](https://github.com/openjdk/jmh)
- [JEP 517: HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [JEP 525: Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525)
- [JEP 529: Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529)
