# GC option trong Java

GC (Garbage Collection) là cơ chế JVM tự động thu hồi vùng nhớ heap đang được các đối tượng không còn được tham chiếu sử dụng. GC option là nhóm tùy chọn JVM dùng để lựa chọn bộ thu gom rác, điều chỉnh kích thước heap, đặt mục tiêu tạm dừng, cấu hình ghi log và bật các tính năng chẩn đoán liên quan đến bộ nhớ.

GC option là tham số của JVM, vì vậy phải đặt trước tên lớp chính hoặc trước tùy chọn -jar. Ứng dụng Java không nhận các tùy chọn này trong String[] args. Ví dụ:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc* -jar service.jar
~~~

Lệnh trên đặt heap ban đầu 256 MiB, heap tối đa 1 GiB, chọn G1 GC và bật GC logging. Các giá trị này chỉ minh họa cú pháp; cấu hình phù hợp phải dựa trên tải, giới hạn bộ nhớ, yêu cầu độ trễ và phiên bản JDK thực tế.

## 1. GC hoạt động ở đâu trong bộ nhớ JVM?

Các đối tượng Java thông thường được cấp phát trên heap. Khi một đối tượng không còn có thể truy cập từ các GC root, JVM có thể xem nó là rác và thu hồi vùng nhớ tương ứng.

GC root thường bao gồm tham chiếu từ stack của luồng đang hoạt động, biến static, JNI reference và một số cấu trúc nội bộ của JVM. Một đối tượng vẫn được giữ bởi bất kỳ chuỗi tham chiếu còn sống nào thì chưa thể thu hồi, dù ứng dụng không còn chủ động sử dụng nó.

Một số vùng nhớ thường được quan sát khi chẩn đoán:

- **Heap:** nơi lưu trữ phần lớn object và array Java.
- **Young generation:** trong các collector phân thế hệ, nơi đối tượng mới thường được cấp phát.
- **Old generation:** nơi chứa các đối tượng sống lâu hơn sau nhiều chu kỳ thu gom.
- **Metaspace:** lưu metadata của lớp; đây không phải vùng heap thông thường.
- **Thread stack, code cache, direct/native memory:** tiêu thụ bộ nhớ tiến trình nhưng không nằm trong Java heap.

GC chủ yếu quản lý heap. Tăng heap không tự động giải quyết việc Metaspace, thread stack, direct buffer hoặc native memory tăng bất thường. Khi tiến trình bị giới hạn bộ nhớ bởi container, tổng bộ nhớ sử dụng còn bao gồm các vùng ngoài heap.

## 2. Cách đặt GC option khi khởi chạy

Cú pháp tổng quát:

~~~bash
java [JVM options] -jar application.jar [application arguments]
~~~

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar application.jar --profile=prod
~~~

Trong ví dụ:

- **-Xms512m**: heap ban đầu là 512 MiB.
- **-Xmx2g**: heap tối đa là 2 GiB.
- **-XX:+UseG1GC**: yêu cầu JVM dùng G1.
- **--profile=prod**: tham số của ứng dụng, được chuyển tới main hoặc framework xử lý.

Phải phân biệt hai nhóm sau:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Heap sizing | -Xms, -Xmx | Đặt kích thước heap ban đầu và tối đa |
| Collector selection | -XX:+UseG1GC | Chọn thuật toán GC |
| GC tuning | -XX:MaxGCPauseMillis=200 | Đặt mục tiêu điều khiển GC |
| GC logging | -Xlog:gc* | Ghi sự kiện GC |
| Diagnostics | -XX:+HeapDumpOnOutOfMemoryError | Tạo dữ liệu phục vụ điều tra lỗi bộ nhớ |

Không có một bộ cờ GC tối ưu cho mọi ứng dụng. Cùng một cấu hình có thể tạo kết quả khác nhau khi thay đổi JDK, collector, kích thước heap, tốc độ cấp phát, phần cứng hoặc giới hạn container.

## 3. Các bộ thu gom rác phổ biến

HotSpot cung cấp nhiều collector với mục tiêu khác nhau. Chọn collector dựa trên đặc điểm workload và yêu cầu vận hành; không nên chỉ chọn theo tên gọi hoặc một bài benchmark không giống môi trường thật.

| Collector | Cờ chọn | Đặc điểm chính | Trường hợp phù hợp |
|---|---|---|---|
| Serial GC | -XX:+UseSerialGC | Thu gom bằng một luồng GC; đơn giản, có pause stop-the-world | Ứng dụng nhỏ, heap nhỏ, môi trường ít CPU |
| Parallel GC | -XX:+UseParallelGC | Dùng nhiều luồng GC để tối ưu thông lượng; các pha chính có pause | Batch hoặc workload ưu tiên tổng lượng công việc |
| G1 GC | -XX:+UseG1GC | Chia heap thành region, thu gom theo vùng; cân bằng thông lượng và pause | Ứng dụng server tổng quát |
| ZGC | -XX:+UseZGC | Collector đồng thời, hướng tới pause rất ngắn | Ứng dụng cần độ trễ thấp, heap lớn |
| Shenandoah | -XX:+UseShenandoahGC | Thu gom và di chuyển object đồng thời với ứng dụng | Workload cần giảm pause, trên JDK build có hỗ trợ |
| Epsilon GC | -XX:+UseEpsilonGC | Không thu hồi bộ nhớ | Benchmark hoặc tình huống đặc biệt có giới hạn cấp phát |

### Serial GC

Serial GC thực hiện các công việc thu gom bằng một luồng GC. Khi cần thực hiện các pha stop-the-world, luồng ứng dụng bị tạm dừng. Collector này có ít chi phí điều phối luồng và có thể phù hợp với chương trình nhỏ, heap nhỏ hoặc môi trường hạn chế CPU.

~~~bash
java -XX:+UseSerialGC -jar application.jar
~~~

Không nên chọn Serial chỉ vì nó đơn giản nếu ứng dụng server có nhiều luồng và tốc độ cấp phát cao. Pause có thể kéo dài khi heap lớn.

### Parallel GC

Parallel GC dùng nhiều luồng để thực hiện các pha thu gom. Mục tiêu thường là tối đa hóa throughput, tức tỷ lệ thời gian CPU dành cho ứng dụng so với thời gian dành cho GC.

~~~bash
java -XX:+UseParallelGC -jar application.jar
~~~

Collector này phù hợp với batch, xử lý nền hoặc workload ưu tiên hoàn thành nhiều công việc trong tổng thời gian ngắn. Nó vẫn có các pause stop-the-world; throughput cao không đồng nghĩa với latency thấp.

### G1 GC

G1 chia heap thành các region thay vì dựa hoàn toàn vào một vùng Young và một vùng Old liên tục. Nó có thể thu gom Young region và lựa chọn một tập Old region trong mixed collection. G1 thực hiện một số công việc đồng thời với ứng dụng và hướng tới mục tiêu pause có thể dự đoán tốt hơn.

~~~bash
java -XX:+UseG1GC -jar application.jar
~~~

Trên cấu hình HotSpot server-class phổ biến, G1 là collector mặc định từ các phiên bản JDK hiện đại. Tuy nhiên, default có thể phụ thuộc phiên bản, kiến trúc và ergonomics của JVM; hãy xác minh tiến trình thực tế thay vì giả định.

Một tùy chọn thường gặp:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar application.jar
~~~

**MaxGCPauseMillis** là mục tiêu mềm để G1 điều chỉnh hoạt động GC. Nó không phải cam kết mọi pause đều ngắn hơn 200 ms. Đặt mục tiêu quá thấp có thể khiến collector dành nhiều tài nguyên cho GC, làm giảm throughput hoặc tăng áp lực bộ nhớ.

Không nên bắt đầu bằng việc tự đặt hàng loạt cờ như G1HeapRegionSize, InitiatingHeapOccupancyPercent hoặc ParallelGCThreads. Hãy để ergonomics của JVM chọn giá trị mặc định trước, sau đó chỉ thay đổi khi GC log và phép đo chỉ ra một vấn đề cụ thể.

### ZGC

ZGC là collector hướng tới độ trễ thấp bằng cách thực hiện phần lớn công việc nặng đồng thời với luồng ứng dụng. Các pause thường ngắn, nhưng collector vẫn tiêu thụ CPU và bộ nhớ để thực hiện công việc đồng thời.

~~~bash
java -XX:+UseZGC -jar application.jar
~~~

Trong JDK 21, có thể bật Generational ZGC bằng:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar application.jar
~~~

Generational ZGC phân chia hoạt động theo tuổi đối tượng nhằm tận dụng đặc điểm nhiều object có vòng đời ngắn. Cờ và trạng thái mặc định thay đổi giữa các phiên bản JDK; hãy đọc tài liệu đúng phiên bản trước khi chuyển cấu hình giữa JDK 17, 21 và các bản mới hơn.

ZGC có thể hữu ích khi yêu cầu latency nghiêm ngặt hoặc heap lớn, nhưng không tự động nhanh hơn G1 trong mọi workload. Cần so sánh pause, CPU, throughput, mức sử dụng bộ nhớ và tail latency trên tải thực tế.

### Shenandoah

Shenandoah cũng hướng tới pause thấp bằng cách thực hiện phần lớn công việc thu gom và di chuyển object đồng thời với ứng dụng.

~~~bash
java -XX:+UseShenandoahGC -jar application.jar
~~~

Khả năng sử dụng Shenandoah phụ thuộc JDK distribution, nền tảng và cách nhà cung cấp build JVM. Nếu JVM không hỗ trợ collector, lệnh có thể thất bại khi khởi chạy. Không giả định mọi bản JDK đều chứa cùng một tập collector.

### Epsilon GC

Epsilon là collector không thu hồi bộ nhớ. Nó chỉ cấp phát cho tới khi hết heap; vì vậy không phải lựa chọn cho ứng dụng chạy lâu dài thông thường.

~~~bash
java -XX:+UseEpsilonGC -Xms256m -Xmx256m -jar allocation-benchmark.jar
~~~

Epsilon hữu ích trong một số benchmark hoặc kiểm thử nhằm đo chi phí cấp phát khi không có GC. Chỉ dùng khi workload được kiểm soát và có đủ heap cho toàn bộ thời gian chạy.

### Lưu ý về CMS

Concurrent Mark Sweep (CMS) đã bị deprecated từ JDK 9 và bị loại bỏ khỏi HotSpot trong JDK 14. Cờ cũ như -XX:+UseConcMarkSweepGC không phù hợp với JDK 17 hoặc JDK 21. Với ứng dụng cũ, cần chuyển sang collector được hỗ trợ và đo lại hành vi trước khi triển khai.

## 4. Heap sizing và giới hạn bộ nhớ

Hai tùy chọn cơ bản:

~~~bash
-Xms512m
-Xmx2g
~~~

- **-Xms** đặt kích thước heap ban đầu.
- **-Xmx** đặt kích thước heap tối đa.

Ví dụ cấu hình G1 với heap tối đa 2 GiB:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar application.jar
~~~

Heap quá nhỏ có thể gây GC thường xuyên, allocation failure hoặc OutOfMemoryError. Heap quá lớn có thể làm tăng footprint tiến trình, thời gian một số pha GC và cạnh tranh bộ nhớ với hệ điều hành hoặc container.

Có thể đặt heap theo tỷ lệ bộ nhớ mà JVM nhận diện được bằng các tùy chọn HotSpot:

~~~bash
java -XX:InitialRAMPercentage=20 -XX:MaxRAMPercentage=60 -jar application.jar
~~~

Các giá trị phần trăm trong ví dụ chỉ minh họa. JVM tính toán theo giới hạn RAM mà nó nhận diện, có thể khác dung lượng RAM vật lý của host. Trong môi trường container, cần kiểm tra giới hạn memory của container và cách JDK nhận diện cgroup.

Không cấp toàn bộ giới hạn container cho heap. Tiến trình còn cần bộ nhớ cho Metaspace, thread stack, code cache, direct buffer, thư viện native và các thành phần khác. Nếu đặt Xmx hoặc MaxRAMPercentage quá cao, tiến trình có thể bị hệ điều hành/container kill dù heap chưa chạm giới hạn.

Nên phân biệt:

- **Java heap usage:** số liệu bộ nhớ object mà GC quản lý.
- **Process RSS / container memory:** bộ nhớ thực tế mà tiến trình hoặc container đang sử dụng.
- **Native memory:** bộ nhớ ngoài heap, gồm nhiều nhóm cấp phát của JVM và thư viện.

Khi RSS tăng nhưng heap ổn định, hãy điều tra native memory, thread count, direct buffer và các thư viện native thay vì chỉ tăng Xmx.

## 5. Mục tiêu pause và các cờ tuning

Một số cờ điều chỉnh được dùng trong thực tế:

| Tùy chọn | Ý nghĩa | Lưu ý |
|---|---|---|
| -XX:MaxGCPauseMillis=200 | Mục tiêu pause cho collector hỗ trợ cờ này, thường gặp với G1 | Mục tiêu mềm, không phải SLA đảm bảo |
| -XX:ParallelGCThreads=N | Số luồng dùng cho các pha GC song song | Giá trị không phù hợp có thể tranh CPU với ứng dụng |
| -XX:ConcGCThreads=N | Số luồng dùng cho công việc GC đồng thời ở collector có hỗ trợ | Tác động tới CPU và tốc độ xử lý GC |
| -XX:+DisableExplicitGC | Bỏ qua yêu cầu GC tường minh như System.gc() | Có thể ảnh hưởng ứng dụng hoặc thư viện dựa vào yêu cầu đó |
| -XX:+UseStringDeduplication | Cho phép G1 loại bỏ bản sao nội dung backing storage của một số String | Có chi phí CPU; chỉ bật khi đo thấy phù hợp |

Không nên áp dụng các cờ trên theo một công thức cố định. Một giá trị tối ưu trên máy nhiều CPU có thể gây thiếu CPU trong container bị giới hạn quota. Cờ nội bộ hoặc cờ thử nghiệm còn có thể thay đổi hoặc bị loại bỏ giữa các phiên bản.

Đối với G1, hãy bắt đầu với cờ mặc định và mục tiêu pause phù hợp với yêu cầu dịch vụ. Nếu pause vượt ngưỡng, phân tích nguyên nhân từ GC log: lượng dữ liệu sống, tốc độ cấp phát, concurrent marking, evacuation failure, CPU throttling hay thiếu headroom của heap. Sau đó chỉ thay đổi một yếu tố mỗi lần và đo lại.

Không nên gọi System.gc() định kỳ để xử lý memory leak. GC không thể thu hồi object còn được tham chiếu; yêu cầu GC tường minh cũng không đảm bảo toàn bộ heap được thu gom ngay lập tức.

## 6. GC logging với Unified Logging

Từ JDK 9, JVM dùng Unified Logging. Tùy chọn cơ bản:

~~~bash
java -Xlog:gc -jar application.jar
~~~

Để ghi chi tiết hơn:

~~~bash
java -Xlog:gc* -jar application.jar
~~~

Để lưu log vào tệp có rotation:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10M -jar application.jar
~~~

Ý nghĩa:

- **gc*** chọn các tag bắt đầu bằng gc, gồm nhiều nhóm sự kiện liên quan.
- **file=gc.log** ghi ra tệp thay vì chỉ ghi ra console.
- **time** thêm thời gian theo đồng hồ hệ thống.
- **uptime** thêm thời gian JVM đã chạy.
- **level** hiển thị mức log.
- **tags** hiển thị nhóm tag của sự kiện.
- **filecount=5** giữ tối đa 5 tệp log đã xoay vòng.
- **filesize=10M** đặt ngưỡng kích thước cho mỗi tệp log.

Có thể kết hợp một số tag cụ thể khi muốn tập trung vào một nhóm dữ liệu:

~~~bash
java -Xlog:gc+heap=debug -jar application.jar
~~~

Cú pháp logging có nhiều thành phần; dấu hai chấm phân tách các phần what, output, decorators và output options. Khi cấu hình log trong script, hãy kiểm tra dấu nháy của shell và đường dẫn tệp trên hệ điều hành triển khai.

GC log thường cho biết:

- Thời điểm và thời lượng các sự kiện GC.
- Dung lượng heap trước và sau một số chu kỳ.
- Loại collection và pha hoạt động.
- Lý do JVM kích hoạt GC.
- Thông tin pause và các công việc GC đồng thời.

Không nên đánh giá chỉ bằng số lần GC. Cần xem thời gian pause, lượng bộ nhớ thu hồi, tốc độ cấp phát, heap sau GC và mức ảnh hưởng tới latency của ứng dụng. Tần suất GC cao có thể bình thường với workload cấp phát nhanh nhưng object sống ngắn.

## 7. Thu thập thông tin GC khi ứng dụng đang chạy

Một số công cụ JDK giúp xem trạng thái JVM mà không phải khởi động lại ngay.

Liệt kê tiến trình Java:

~~~bash
jcmd -l
~~~

Xem các cờ JVM đang áp dụng:

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

Xem thông tin heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Theo dõi số liệu GC theo chu kỳ:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh jstat lấy mẫu mỗi giây trong 10 lần. Các cột thường gặp:

- **S0, S1:** tỷ lệ sử dụng Survivor space.
- **E:** tỷ lệ sử dụng Eden.
- **O:** tỷ lệ sử dụng Old Generation.
- **M:** tỷ lệ sử dụng Metaspace.
- **YGC, YGCT:** số lần và tổng thời gian Young GC.
- **FGC, FGCT:** số lần và tổng thời gian Full GC.
- **GCT:** tổng thời gian GC được thống kê.

Tên cột và vùng hiển thị có thể khác theo collector hoặc phiên bản. Hãy đọc header do chính jstat in ra.

JFR có thể ghi các sự kiện GC trong một khoảng thời gian:

~~~bash
jcmd <pid> JFR.start name=gc-investigation settings=profile duration=60s filename=gc-investigation.jfr
jfr summary gc-investigation.jfr
~~~

JFR giúp đối chiếu GC với allocation, hoạt động luồng và các sự kiện runtime khác. Khi sự cố chỉ xuất hiện dưới tải, recording theo khoảng thời gian xảy ra sự cố thường có giá trị hơn một snapshot lúc hệ thống rảnh.

Các thao tác chẩn đoán cần quyền truy cập phù hợp và có thể chịu ảnh hưởng bởi container, Attach mechanism hoặc chính sách bảo mật. Không chạy lệnh nặng liên tục trên tiến trình production mà chưa đánh giá tác động.

## 8. Heap dump khi OutOfMemoryError

Có thể yêu cầu JVM tạo heap dump khi xảy ra OutOfMemoryError:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/app/heap.hprof -jar application.jar
~~~

Heap dump lưu trạng thái object và tham chiếu tại thời điểm dump. Có thể mở bằng công cụ phân tích heap để tìm:

- Lớp nào có số lượng object lớn.
- Object nào chiếm nhiều retained heap.
- Chuỗi tham chiếu nào giữ object sống.
- Collection, cache hoặc listener nào tăng không kiểm soát.

Heap dump có thể rất lớn, tốn dung lượng đĩa và chứa dữ liệu nhạy cảm. Hãy tạo thư mục trước, cấp quyền ghi đúng cho user chạy ứng dụng, dự trù dung lượng và bảo vệ tệp. Nếu JVM bị kill bởi OOM killer của hệ điều hành hoặc container trước khi ném OutOfMemoryError trong Java, tùy chọn này có thể không được kích hoạt.

Heap dump không thay thế GC log. GC log cho biết diễn biến theo thời gian; heap dump cung cấp snapshot để phân tích đồ thị tham chiếu.

## 9. Quy trình chọn và tuning GC

Một quy trình thực tế nên dựa trên mục tiêu vận hành:

1. **Xác định yêu cầu:** throughput, latency trung bình, p95/p99, thời gian pause tối đa, giới hạn bộ nhớ và tải đỉnh.
2. **Ghi nhận baseline:** JDK distribution/version, collector, Xms/Xmx, CPU quota, container memory và GC log hiện tại.
3. **Đo workload đại diện:** dùng dữ liệu, concurrency và thời gian chạy gần production.
4. **Phân tích:** so sánh pause, allocation rate, live set sau GC, CPU, RSS và tail latency.
5. **Đặt giả thuyết:** heap quá nhỏ, object sống lâu, tốc độ cấp phát cao, GC thiếu CPU hoặc collector không phù hợp.
6. **Thay đổi từng yếu tố:** một cờ hoặc một cấu hình mỗi lần để biết nguyên nhân tạo khác biệt.
7. **Chạy lại cùng workload:** so sánh cùng chỉ số, không chỉ nhìn một lần GC.
8. **Triển khai có kiểm soát:** theo dõi sau rollout và giữ khả năng quay lại cấu hình đã biết.

Một số dấu hiệu và hướng điều tra:

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| Young GC diễn ra dày | Allocation rate, object tạm thời, kích thước heap và tốc độ xử lý |
| Old Gen tăng sau mỗi chu kỳ | Object sống lâu, cache, collection giữ tham chiếu, heap dump |
| Pause dài | GC log, lượng object sống, evacuation, CPU quota và collector |
| Full GC lặp lại | Live set, allocation failure, cấu hình heap và log nguyên nhân |
| RSS tăng nhưng heap không tăng | Metaspace, thread stack, direct buffer, native allocation |
| CPU cao khi GC | Tần suất GC, collector, allocation rate, số luồng GC và CPU limit |

Không thể kết luận memory leak chỉ vì heap tăng trong một khoảng thời gian. Ứng dụng có thể đang tải dữ liệu hợp lệ hoặc cache đang warm-up. Hãy quan sát sau nhiều chu kỳ GC và xác định live set có tiếp tục tăng không.

## 10. Ví dụ thực hành với Java 17+

Chương trình dưới đây tạo nhiều mảng byte ngắn hạn để tạo áp lực cấp phát trên heap. Các mảng chỉ được giữ trong một batch hiện tại, vì vậy batch cũ có thể được thu hồi sau khi vòng lặp tiếp tục. Chương trình không gọi System.gc().

Tạo tệp GcOptionsDemo.java:

~~~java
public class GcOptionsDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        long checksum = 0;

        for (int round = 0; round < 256; round++) {
            byte[][] batch = new byte[32][];

            for (int i = 0; i < batch.length; i++) {
                byte[] data = new byte[64 * 1024];
                data[0] = (byte) i;
                data[data.length - 1] = (byte) round;
                batch[i] = data;

                checksum += data[0] + data[data.length - 1];
            }
        }

        sink = checksum;
        System.out.println("Completed allocation workload.");
    }
}
~~~

Biên dịch:

~~~bash
javac GcOptionsDemo.java
~~~

Chạy với G1, heap tối đa 64 MiB và GC log:

~~~bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags GcOptionsDemo
~~~

Dòng output của chương trình:

~~~text
Completed allocation workload.
~~~

Tệp gc.log chứa các sự kiện GC phát sinh; số dòng, thời gian và chi tiết phụ thuộc JDK, máy chạy và trạng thái runtime. Để thử Parallel GC, chạy cùng chương trình với:

~~~bash
java -Xms32m -Xmx64m -XX:+UseParallelGC -Xlog:gc*:file=parallel-gc.log:time,uptime,level,tags GcOptionsDemo
~~~

Có thể so sánh hai log bằng thời gian pause, số lần collection, lượng heap sau GC và thời gian hoàn tất. Một lần chạy không đủ để khẳng định collector nào tốt hơn; cần lặp lại nhiều lần trong điều kiện tải giống nhau.

## 11. Lỗi cấu hình và lưu ý vận hành

**Đặt JVM option sau tên JAR**

~~~bash
java -jar application.jar -XX:+UseG1GC
~~~

Trong lệnh trên, chuỗi -XX:+UseG1GC được truyền cho ứng dụng. Đặt option trước -jar:

~~~bash
java -XX:+UseG1GC -jar application.jar
~~~

**Dùng collector không được JVM hỗ trợ**

Một JDK distribution có thể không chứa Shenandoah hoặc một collector tùy chọn. Hãy thử trên đúng binary sẽ triển khai và kiểm tra thông báo JVM khi khởi chạy.

**Chọn nhiều collector cùng lúc**

Mỗi tiến trình cần một collector phù hợp. Không ghép tùy tiện các cờ chọn Serial, Parallel, G1, ZGC hoặc Shenandoah với nhau. Chọn một collector và xác minh bằng VM.flags.

**Coi MaxGCPauseMillis là giới hạn cứng**

Đây là mục tiêu điều khiển, không bảo đảm pause luôn thấp hơn con số đã đặt. Latency thực tế còn phụ thuộc live set, CPU, allocation rate và workload.

**Tăng Xmx để xử lý memory leak**

Nếu object không còn cần thiết nhưng vẫn bị giữ tham chiếu, tăng heap chỉ trì hoãn thời điểm gặp vấn đề. Hãy dùng GC log, class histogram và heap dump để tìm đường tham chiếu.

**Dùng cờ từ tài liệu JDK khác phiên bản**

Một cờ có thể thay đổi trạng thái, tên hoặc hành vi qua các bản JDK. Đọc tài liệu tương ứng phiên bản và thử nghiệm trên cùng JDK distribution của môi trường triển khai.

**Bật GC log nhưng không quản lý dung lượng**

GC log có thể tăng liên tục. Sử dụng rotation, giới hạn dung lượng, chính sách lưu trữ và quyền truy cập phù hợp.

**Giả định heap là toàn bộ bộ nhớ tiến trình**

JVM còn dùng Metaspace, stack, code cache và native memory. Đặt Xmx gần bằng memory limit có thể khiến container bị kill.

## 12. Nguyên tắc lựa chọn

- Bắt đầu với collector mặc định của JDK đang dùng và đo baseline.
- G1 là lựa chọn tổng quát tốt cho nhiều ứng dụng server.
- Parallel phù hợp khi throughput quan trọng hơn pause ngắn.
- Serial phù hợp với chương trình nhỏ hoặc môi trường ít CPU.
- ZGC hoặc Shenandoah đáng thử khi yêu cầu latency thấp và bản JDK hỗ trợ.
- Epsilon chỉ dành cho tình huống đặc biệt không cần thu hồi bộ nhớ.
- Chỉ thay đổi tuning flag khi có số liệu chứng minh vấn đề.
- Theo dõi heap, native memory, CPU, pause và latency cùng nhau.

GC option quyết định cách JVM thu hồi heap và tiêu thụ tài nguyên để thực hiện công việc đó. Cấu hình tốt là cấu hình đáp ứng SLO trên workload thực tế, có log đủ để điều tra và vẫn nằm trong giới hạn CPU, bộ nhớ của môi trường triển khai.
