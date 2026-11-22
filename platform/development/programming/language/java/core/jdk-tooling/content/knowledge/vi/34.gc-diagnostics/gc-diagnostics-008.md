# Cấu hình Garbage Collection trong Java

**GC configuration** là việc lựa chọn garbage collector, đặt giới hạn heap và điều chỉnh hành vi thu gom bộ nhớ của JVM. Cấu hình phù hợp giúp cân bằng ba mục tiêu: độ trễ (latency), thông lượng (throughput) và mức tiêu thụ bộ nhớ (footprint).

HotSpot JVM có nhiều collector như Serial, Parallel, G1, ZGC và Shenandoah. Mỗi collector có thiết kế và mục tiêu khác nhau. Cấu hình tốt cho batch job cần throughput cao có thể không phù hợp với API cần response time ổn định. Vì vậy, cấu hình GC phải xuất phát từ yêu cầu ứng dụng và số liệu đo trên workload đại diện.

Bài này hướng dẫn lựa chọn collector, cấu hình heap, hiểu các cờ GC quan trọng, bật GC log, điều chỉnh G1 và ZGC, cấu hình trong container, kiểm tra flag đang có hiệu lực và thực hành bằng Java 17+.

## 1. Mục tiêu của GC configuration

GC configuration thường phải cân bằng ba mục tiêu:

| Mục tiêu | Ý nghĩa | Ví dụ yêu cầu |
|---|---|---|
| Throughput | Tỷ lệ thời gian JVM dành cho công việc ứng dụng thay vì GC | Batch xử lý nhiều bản ghi mỗi giây |
| Latency | Thời gian ứng dụng phải chờ do GC pause | API cần P95/P99 response time ổn định |
| Footprint | Lượng RAM JVM sử dụng | Service chạy trong container có memory limit nhỏ |

Các mục tiêu có thể xung đột:

- Giảm pause thường cần collector làm thêm công việc đồng thời, có thể tăng CPU và giảm throughput.
- Tăng heap có thể giảm tần suất GC nhưng làm footprint lớn hơn.
- Giảm heap có thể giảm RAM nhưng khiến GC chạy thường xuyên.
- Đặt pause target quá thấp có thể làm JVM thu gom thường xuyên hơn và giảm throughput.

Không có một giá trị flag tối ưu cho mọi ứng dụng. Hãy xác định mục tiêu bằng SLO và số liệu như throughput, P95/P99 latency, GC pause, CPU, heap sau GC và memory limit.

## 2. Ergonomics: JVM tự chọn cấu hình như thế nào?

HotSpot có cơ chế **ergonomics** để tự chọn collector, heap size và số GC thread dựa trên môi trường thực thi.

Trong JDK 26, G1 là collector mặc định trên máy server-class; Serial có thể được chọn trên môi trường không thuộc nhóm đó. Máy server-class được JVM xác định dựa trên CPU và bộ nhớ khả dụng. JVM cũng tự điều chỉnh nhiều tham số trong quá trình chạy.

Một số quyết định tự động:

- Collector mặc định theo loại môi trường.
- Heap initial/minimum và maximum theo bộ nhớ khả dụng.
- Số GC thread theo CPU và heap.
- Kích thước young generation theo hành vi allocation.
- Một số ngưỡng bắt đầu concurrent marking của G1.
- Heap có thể tăng hoặc giảm để cân bằng throughput và footprint.

JVM thường tự điều chỉnh tốt hơn một bộ flag được sao chép từ máy khác. Hãy bắt đầu bằng mặc định, đo workload, sau đó chỉ thay đổi tham số liên quan trực tiếp đến vấn đề quan sát được.

### Kiểm tra collector được chọn

Có thể dùng:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

Hoặc xem flag sau khi JVM khởi chạy:

~~~bash
jcmd 2125 VM.flags
~~~

Thay 2125 bằng PID của process. Có thể xem thêm thông tin JVM:

~~~bash
jcmd 2125 VM.info
~~~

Tên GC bean có thể được xem qua JMX hoặc chương trình Java dùng GarbageCollectorMXBean. Đừng chỉ dựa vào một flag cấu hình nếu ứng dụng chạy trong môi trường hoặc JDK khác.

## 3. Chọn garbage collector

### Serial GC

Bật bằng:

~~~bash
-XX:+UseSerialGC
~~~

Serial GC dùng một thread để thực hiện công việc GC chính. Nó phù hợp với ứng dụng nhỏ, ít thread, heap nhỏ hoặc môi trường bị giới hạn CPU.

Ưu điểm:

- Cấu hình đơn giản.
- Ít overhead từ nhiều GC worker.
- Có thể phù hợp ứng dụng desktop, công cụ nhỏ hoặc workload nhẹ.

Hạn chế:

- GC pause có thể dài khi heap hoặc live set lớn.
- Không tận dụng nhiều CPU để tăng tốc collection.
- Thường không phù hợp server nhiều thread có yêu cầu latency cao.

### Parallel GC

Bật bằng:

~~~bash
-XX:+UseParallelGC
~~~

Parallel GC còn được gọi là throughput collector. Nó dùng nhiều thread để thực hiện collection, đặc biệt phù hợp workload ưu tiên throughput và có thể chấp nhận pause dài hơn.

Ưu điểm:

- Tối ưu cho throughput.
- Có thể tận dụng nhiều CPU để rút ngắn thời gian collection.
- Phù hợp batch processing và workload tính toán theo lô.

Hạn chế:

- Collection chính vẫn có các khoảng stop-the-world.
- Pause có thể dài hơn collector concurrent.
- Có thể chiếm nhiều CPU trong lúc GC chạy.

### G1 GC

Bật rõ ràng bằng:

~~~bash
-XX:+UseG1GC
~~~

G1 là collector mặc định trên server-class machine trong JDK 26. Nó chia heap thành region, thu gom từng collection set và thực hiện một phần công việc concurrent.

Ưu điểm:

- Cân bằng throughput và latency.
- Điều chỉnh young generation để hướng tới pause-time goal.
- Có thể thu hồi old regions theo từng đợt mixed collection.
- Phù hợp ứng dụng server và heap tương đối lớn.

Hạn chế:

- Có overhead cho remembered set, marking và concurrent work.
- Không bảo đảm mọi pause đều nằm dưới pause target.
- Một số workload allocation hoặc object graph đặc biệt vẫn có thể gây Full GC.

### ZGC

Bật bằng:

~~~bash
-XX:+UseZGC
~~~

ZGC là collector ưu tiên latency thấp và thực hiện phần lớn công việc tốn thời gian đồng thời với application threads. Nó phù hợp ứng dụng có yêu cầu pause rất ngắn hoặc heap lớn.

Từ JDK 24, ZGC chạy ở chế độ generational mặc định và cờ -XX:+ZGenerational đã bị loại bỏ. Không sao chép flag ZGenerational từ tài liệu JDK cũ.

ZGC được thiết kế để tự điều chỉnh. Tham số quan trọng nhất thường là -Xmx, vì collector cần đủ heap để chứa live set và có headroom phục vụ allocation trong lúc GC chạy.

### Shenandoah GC

Bật trên các bản phân phối/platform hỗ trợ:

~~~bash
-XX:+UseShenandoahGC
~~~

Shenandoah là collector concurrent, hướng tới pause thấp và không để thời gian pause tăng tuyến tính theo kích thước heap. Khả năng có mặt và tùy chọn cụ thể phụ thuộc JDK distribution và nền tảng. Kiểm tra tài liệu đúng vendor trước khi sử dụng.

### Bảng chọn nhanh

| Collector | Mục tiêu chính | Khi nên thử |
|---|---|---|
| Serial | Đơn giản, footprint nhỏ | Ứng dụng nhỏ, ít CPU |
| Parallel | Throughput cao | Batch, xử lý theo lô |
| G1 | Cân bằng throughput/latency | Server application, lựa chọn khởi đầu phổ biến |
| ZGC | Latency rất thấp | Dịch vụ nhạy latency, heap lớn |
| Shenandoah | Latency thấp | Workload cần pause thấp trên bản JDK hỗ trợ |

Chỉ chọn một collector chính cho một JVM. Không truyền đồng thời các flag chọn collector mâu thuẫn với nhau.

## 4. Cấu hình kích thước heap

Hai flag cơ bản nhất:

| Flag | Ý nghĩa |
|---|---|
| -Xms | Initial/minimum heap size |
| -Xmx | Maximum heap size |

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

JVM bắt đầu với heap 512 MB và có thể mở rộng tới 2 GB.

Trong server deployment, đôi khi đặt Xms và Xmx bằng nhau để tránh heap resize trong runtime:

~~~bash
java -Xms2g -Xmx2g -jar app.jar
~~~

Cách này có thể làm memory footprint ban đầu lớn hơn. Chỉ dùng khi đã hiểu memory budget và có lý do về tính ổn định latency.

### Không đặt Xmx bằng toàn bộ RAM máy

Java heap chỉ là một phần của bộ nhớ process. JVM còn cần:

- Metaspace và class metadata.
- Thread stacks.
- Direct buffers và native allocations.
- JIT code cache.
- GC metadata và internal structures.
- Native libraries và memory-mapped regions.

Nếu container có giới hạn 2 GB, không nên mặc định đặt Xmx=2g. Heap cần chừa headroom cho các vùng native và các process phụ trợ trong cùng container.

### Dùng MaxRAMPercentage

HotSpot có thể tính maximum heap dựa trên bộ nhớ khả dụng:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Trong JDK 26, mặc định của -XX:MaxRAMPercentage là 25%. Giá trị 60 ở ví dụ là phần trăm của bộ nhớ tối đa JVM xác định được, không phải phần trăm RAM vật lý luôn luôn.

Có thể đặt initial heap theo phần trăm:

~~~bash
-XX:InitialRAMPercentage=10
~~~

Khi cấu hình container, hãy đo peak RSS, native memory, metaspace và thread count trước khi chọn phần trăm. Đừng cộng Xmx với MaxRAMPercentage như thể chúng cùng lúc có hiệu lực; một cấu hình có thể ghi đè cách sizing của cấu hình khác.

## 5. Cấu hình pause-time và throughput goal

### MaxGCPauseMillis

Flag:

~~~bash
-XX:MaxGCPauseMillis=200
~~~

Đặt mục tiêu pause tối đa mong muốn là 200 ms. Đây là **soft goal**, không phải hard limit hoặc SLA guarantee. JVM điều chỉnh heap và GC policy để cố gắng đạt mục tiêu.

Trong JDK 26, pause-time target này được hỗ trợ bởi G1 và Parallel. Với G1, giá trị mặc định là 200 ms.

Giảm target có thể làm young generation nhỏ hơn, GC xảy ra thường xuyên hơn và throughput giảm. Nếu đặt quá thấp, JVM có thể khó đạt mục tiêu trong workload thực tế.

### GCTimeRatio

Flag:

~~~bash
-XX:GCTimeRatio=19
~~~

Đặt mục tiêu tỷ lệ thời gian GC so với thời gian ứng dụng:

\[
\text{GC fraction} = \frac{1}{1+\text{GCTimeRatio}}
\]

Với giá trị 19:

\[
\frac{1}{1+19}=0.05=5\%
\]

Đây là mục tiêu cho thời gian GC theo chính sách collector, không phải phép đo pause percentile. Giá trị mặc định và cách áp dụng phụ thuộc collector.

### Footprint

Heap maximum được giới hạn bằng Xmx. JVM cố gắng cân bằng throughput và pause goal trước khi giảm footprint. Nếu heap quá nhỏ để chứa live set và allocation headroom, GC sẽ hoạt động thường xuyên và hiệu năng có thể giảm mạnh.

## 6. Cấu hình G1 GC

G1 thường là lựa chọn đầu tiên cho ứng dụng server. Tài liệu Oracle khuyến nghị bắt đầu bằng mặc định, sau đó mới thay đổi pause target hoặc Xmx khi số liệu cho thấy cần thiết.

Cấu hình khởi đầu:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx2g -XX:MaxGCPauseMillis=200 -jar app.jar
~~~

### Adaptive IHOP

G1 dùng Initiating Heap Occupancy Percent (IHOP) để quyết định khi nào bắt đầu concurrent marking.

Flag liên quan:

~~~bash
-XX:InitiatingHeapOccupancyPercent=45
-XX:+G1UseAdaptiveIHOP
~~~

Adaptive IHOP được bật mặc định. G1 quan sát thời gian marking và lượng allocation vào old generation để tự điều chỉnh ngưỡng. Giá trị 45% được dùng trong những chu kỳ đầu khi chưa có đủ dữ liệu.

Chỉ tắt adaptive IHOP khi log cho thấy dự đoán mặc định không phù hợp và bạn có cơ sở chọn ngưỡng thủ công:

~~~bash
-XX:-G1UseAdaptiveIHOP -XX:InitiatingHeapOccupancyPercent=35
~~~

Không nên cố định IHOP chỉ vì thấy heap usage chạm một tỷ lệ trong một lần quan sát.

### G1ReservePercent

Flag:

~~~bash
-XX:G1ReservePercent=10
~~~

G1 dành một phần heap làm reserve để giảm nguy cơ promotion failure khi evacuation. Mặc định là 10%. Tăng reserve sẽ làm giảm phần heap có thể dùng cho application objects, vì vậy phải tính vào heap budget.

### G1HeapRegionSize

Flag:

~~~bash
-XX:G1HeapRegionSize=16m
~~~

G1 tự chọn region size theo heap size, thường hướng tới khoảng 2.048 region. Chỉ đặt thủ công khi GC log cho thấy vấn đề liên quan humongous objects hoặc region sizing. Giá trị phải là lũy thừa của 2 và nằm trong phạm vi JDK hỗ trợ.

### Tránh cố định young generation khi dùng G1

Các flag như -Xmn, -XX:NewSize, -XX:MaxNewSize hoặc cấu hình generation ratio có thể làm mất khả năng tự điều chỉnh young generation của G1. Đây là cơ chế chính để G1 đáp ứng pause goal.

Không đặt cố định young generation nếu mục tiêu là để G1 tự cân bằng pause time và throughput.

### Mixed collection

Sau concurrent marking, G1 có thể thu gom old regions theo nhiều mixed collections. Một số flag ảnh hưởng đến quá trình này:

| Flag | Ý nghĩa |
|---|---|
| -XX:G1MixedGCCountTarget | Mục tiêu số mixed collections trong phase |
| -XX:G1HeapWastePercent | Mức heap waste cho phép trước khi dừng thêm old-region reclamation |
| -XX:G1MixedGCLiveThresholdPercent | Ngưỡng live data để chọn old region |

Chỉ điều chỉnh các flag này khi GC log chỉ ra vấn đề cụ thể trong space-reclamation phase.

## 7. Cấu hình Parallel GC

Parallel GC phù hợp khi throughput quan trọng hơn pause latency.

Ví dụ:

~~~bash
java -XX:+UseParallelGC -Xms2g -Xmx4g -XX:GCTimeRatio=19 -jar batch.jar
~~~

Có thể đặt số worker GC:

~~~bash
-XX:ParallelGCThreads=4
~~~

Nếu đặt quá nhiều thread, GC có thể cạnh tranh CPU với application threads. Nếu đặt quá ít, collection có thể kéo dài. Mặc định JVM chọn số thread theo CPU khả dụng và heap.

Parallel GC hỗ trợ pause-time goal qua:

~~~bash
-XX:MaxGCPauseMillis=500
~~~

Giá trị 500 ms chỉ là gợi ý cho collector. Khi có pause goal, JVM có thể điều chỉnh heap và các tham số khác, nhưng throughput có thể giảm.

### Khi nào nên chọn Parallel?

- Batch job cần hoàn thành nhiều công việc mỗi giây.
- Pause dài hơn có thể chấp nhận.
- Có đủ CPU để chạy nhiều GC worker.
- Throughput là chỉ số quan trọng hơn tail latency.

Không chọn Parallel chỉ vì số lượng GC thread lớn hơn. Hãy benchmark end-to-end với cùng workload.

## 8. Cấu hình ZGC

ZGC hướng tới pause thấp và tự điều chỉnh nhiều tham số. Cấu hình khởi đầu thường đơn giản:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx8g -jar latency-service.jar
~~~

### Xmx và allocation headroom

Vì ZGC làm nhiều công việc concurrent, heap phải đủ chỗ cho:

- Live set của ứng dụng.
- Allocation phát sinh trong lúc GC đang chạy.
- Allocation spikes.
- Một khoảng dự phòng cho thay đổi workload.

Nếu heap gần cạn trong lúc concurrent cycle chưa thu hồi đủ bộ nhớ, application threads có thể phải chờ allocation stall. Tăng Xmx có thể giải quyết headroom, nhưng phải nằm trong memory budget của process/container.

### SoftMaxHeapSize

Flag:

~~~bash
-XX:+UseZGC -Xmx8g -XX:SoftMaxHeapSize=6g
~~~

SoftMaxHeapSize là giới hạn mềm cho heuristic sizing. ZGC cố gắng giữ heap dưới 6 GB, nhưng vẫn có thể vượt lên đến Xmx=8 GB nếu cần để tránh ứng dụng bị stall.

SoftMaxHeapSize không thay thế Xmx. Xmx vẫn là giới hạn cứng.

### Không bật lại ZGenerational

Từ JDK 24, ZGC đã generational mặc định. Flag -XX:+ZGenerational đã bị loại bỏ. Cấu hình JDK hiện đại chỉ cần:

~~~bash
-XX:+UseZGC
~~~

### Khi nào nên thử ZGC?

- API hoặc interactive service có latency SLO rất chặt.
- Heap lớn và pause là bottleneck.
- CPU có đủ headroom cho concurrent GC.
- Đã đo được GC pause là nguyên nhân của latency spike.

ZGC có thể tiêu thụ CPU nhiều hơn collector throughput-oriented. So sánh cả CPU, throughput và memory headroom, không chỉ pause.

## 9. Cấu hình Shenandoah

Trên JDK distribution có hỗ trợ Shenandoah:

~~~bash
java -XX:+UseShenandoahGC -Xms2g -Xmx8g -jar app.jar
~~~

Shenandoah là concurrent low-pause collector. Một số bản JDK cho phép chọn mode hoặc heuristic cụ thể. Các flag và trạng thái hỗ trợ phụ thuộc vendor, platform và release.

Kiểm tra option trên đúng runtime:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Không sao chép flag Shenandoah từ một bản OpenJDK sang Oracle JDK hoặc vendor khác nếu chưa xác nhận hỗ trợ.

## 10. GC logging là phần bắt buộc của tuning

Trước khi chỉnh flag, cần biết GC đang làm gì. Dùng unified logging:

~~~bash
java -Xlog:gc*:file=logs/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Cấu hình này:

- Ghi nhóm log GC.
- Thêm timestamp và uptime.
- Ghi level và tag.
- Xoay vòng tối đa 5 file.
- Mỗi file có dung lượng mục tiêu 20 MB.

Để chẩn đoán G1 chi tiết hơn:

~~~bash
-Xlog:gc*=debug
~~~

Để xem thông tin heap region:

~~~bash
-Xlog:gc+heap=info
~~~

Để xem các GC phase:

~~~bash
-Xlog:gc+phases=debug
~~~

Xem cú pháp tag và level khả dụng:

~~~bash
java -Xlog:help
~~~

Không bật debug logging quá chi tiết trong thời gian dài nếu chưa đánh giá dung lượng và overhead.

## 11. Kiểm tra flag GC đang có hiệu lực

Flag truyền trên command line không phải lúc nào cũng phản ánh toàn bộ trạng thái runtime. JVM có ergonomic defaults và một số flag có thể được thay đổi bởi launcher, environment hoặc container.

### In command line flags

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

### In tất cả flag và giá trị cuối

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Có thể lọc trên Linux:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E "UseG1GC|UseParallelGC|UseZGC|MaxHeapSize|InitialHeapSize|MaxGCPauseMillis"
~~~

Trên PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String "UseG1GC|UseParallelGC|UseZGC|MaxHeapSize|InitialHeapSize|MaxGCPauseMillis"
~~~

### Kiểm tra process đang chạy

~~~bash
jcmd 2125 VM.flags
jcmd 2125 VM.info
jcmd 2125 GC.heap_info
~~~

Dùng PID của JVM thực tế. VM.flags cho biết flag runtime; VM.info cung cấp thông tin tổng quan; GC.heap_info hiển thị thông tin heap.

### Kiểm tra option cụ thể

Có thể dùng:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Tìm flag cần quan tâm và xem giá trị cuối cùng. Một số option diagnostic hoặc experimental cần mở khóa và không được khuyến nghị dùng trong cấu hình production thông thường.

## 12. Cấu hình GC trong Docker và Kubernetes

Trên Linux, HotSpot có container support bật mặc định trong JDK 26. JVM có thể đọc giới hạn memory và CPU của container để chọn heap và số thread. Flag -XX:+UseContainerSupport bật chức năng này; đây là mặc định trên Linux. Có thể tắt bằng -XX:-UseContainerSupport, nhưng thường không nên tắt nếu ứng dụng phụ thuộc vào container resource limits.

Ví dụ container có memory limit 2 GiB:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Với MaxRAMPercentage 60, maximum heap ergonomics được tính dựa trên memory khả dụng mà JVM nhận diện. Đây chỉ là ví dụ; phần còn lại cần đủ cho metaspace, native memory, thread stacks, direct buffers và các thành phần khác.

### Container CPU limit

JVM dùng số CPU khả dụng để tính GC thread và thread pool. Nếu cần ghi đè số CPU mà JVM nhìn thấy:

~~~bash
-XX:ActiveProcessorCount=4
~~~

Flag này ảnh hưởng đến số CPU JVM dùng cho các heuristic, kể cả khi container support bị tắt.

### Xác minh container awareness

Có thể bật log chẩn đoán:

~~~bash
-Xlog:os+container=trace
~~~

Dùng log này để xem JVM nhận diện memory/CPU limit như thế nào. Đừng giả định JVM luôn nhìn thấy toàn bộ tài nguyên của host.

### Lập memory budget

Ví dụ container có 2 GiB memory limit:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Java heap maximum | 1.2 GiB |
| Metaspace | 160 MiB |
| Direct/native buffers | 200 MiB |
| Thread stacks | 160 MiB |
| Code cache và JVM internals | 100 MiB |
| Dự phòng | Phần còn lại |

Các con số chỉ minh họa cách lập ngân sách, không phải default. Đo RSS và native memory thực tế trước khi chốt Xmx.

## 13. Những flag GC thường gặp

| Flag | Mục đích | Lưu ý |
|---|---|---|
| -Xms | Heap initial/minimum | Có thể tăng footprint ban đầu |
| -Xmx | Heap maximum | Cần chừa native memory |
| -XX:MaxRAMPercentage | Tính heap max theo memory khả dụng | Mặc định JDK 26 là 25% |
| -XX:MaxGCPauseMillis | Pause target | Soft goal, không phải guarantee |
| -XX:GCTimeRatio | Throughput goal | Giá trị càng lớn thì phần thời gian GC mục tiêu càng nhỏ |
| -XX:ParallelGCThreads | Số GC worker stop-the-world | Tăng quá mức có thể cạnh tranh CPU |
| -XX:ConcGCThreads | Số concurrent GC worker | Ảnh hưởng CPU ứng dụng |
| -XX:+DisableExplicitGC | Bỏ qua System.gc() request | Chỉ dùng khi đã xác minh tác động |
| -XX:+UseStringDeduplication | Deduplicate String backing data với G1 | Có chi phí xử lý bổ sung |
| -XX:MaxMetaspaceSize | Giới hạn native memory cho class metadata | Không phải heap limit |
| -XX:ActiveProcessorCount | Override CPU count JVM sử dụng | Hữu ích khi partition CPU |

Không có lý do để đặt tất cả các flag trên vào một lệnh khởi chạy. Chọn các option cần thiết cho collector và mục tiêu cụ thể.

## 14. Những cấu hình nên tránh

### Cố định quá nhiều thông số của G1

Nếu đặt Xmn, SurvivorRatio và các generation size cứng, G1 mất một phần khả năng tự điều chỉnh young generation để đáp ứng pause target.

### Hạ pause target quá thấp

Pause target thấp có thể làm GC chạy thường xuyên hơn và giảm throughput. Nếu mục tiêu không thể đạt được với workload thực tế, thay đổi target không giải quyết được nguyên nhân.

### Đặt Xmx bằng memory limit của container

Heap không phải toàn bộ process memory. JVM có thể bị container OOM kill trước khi Java heap chạm Xmx nếu native memory và các vùng khác chiếm phần còn lại.

### Tắt explicit GC mà chưa tìm nguyên nhân

-XX:+DisableExplicitGC bỏ qua yêu cầu System.gc() từ ứng dụng hoặc thư viện. Nếu hệ thống dựa vào explicit GC cho một tác vụ nào đó, hành vi có thể thay đổi. Kiểm tra GC cause và code trước khi bật.

### Sao chép flag từ JDK cũ

Một số option thay đổi, bị deprecated, obsolete hoặc removed. Ví dụ -XX:+ZGenerational không còn hợp lệ từ JDK 24 vì Generational ZGC đã trở thành chế độ mặc định. Luôn kiểm tra tài liệu của đúng JDK.

## 15. Thực hành Java 17+: kiểm tra GC configuration qua MXBean

Ví dụ sau kiểm tra JVM có GarbageCollectorMXBean, heap maximum có giá trị hợp lệ và flag G1 đã được truyền vào command line hay không.

Tệp GcConfigCheck.java:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.RuntimeMXBean;
import java.util.List;

public final class GcConfigCheck {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        boolean gcBeansPresent = !collectors.isEmpty();
        boolean maxHeapPositive =
                memory.getHeapMemoryUsage().getMax() > 0;
        boolean g1FlagPresent =
                runtime.getInputArguments().contains("-XX:+UseG1GC");

        System.out.println("GC_BEANS_PRESENT=" + gcBeansPresent);
        System.out.println("MAX_HEAP_POSITIVE=" + maxHeapPositive);
        System.out.println("G1_FLAG_PRESENT=" + g1FlagPresent);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 GcConfigCheck.java
~~~

Chạy với G1 và heap tối đa 256 MB:

~~~bash
java -XX:+UseG1GC -Xmx256m GcConfigCheck
~~~

Stdout chính xác trên HotSpot:

~~~text
GC_BEANS_PRESENT=true
MAX_HEAP_POSITIVE=true
G1_FLAG_PRESENT=true
~~~

Chương trình kiểm tra flag được truyền vào, không tự suy ra collector đang thực thi chỉ từ tên flag. Để xác minh runtime đầy đủ, hãy kết hợp jcmd PID VM.flags, jcmd PID VM.info và thông tin GC bean.

## 16. Quy trình tuning GC an toàn

1. Xác định mục tiêu chính: throughput, latency hay footprint.
2. Ghi lại JDK vendor/version, collector, heap size, CPU và container limit.
3. Chạy với collector mặc định và cấu hình gần mặc định.
4. Bật GC logging có rotation.
5. Thu thập JFR nếu cần phân tích GC phase, allocation hoặc thread.
6. Đo baseline bằng workload đại diện và thời gian đủ dài.
7. Tính pause sum, max/P95/P99 pause, GC time, throughput và RSS.
8. Xem heap trước/sau GC và live set.
9. Nếu heap quá nhỏ, đánh giá Xmx và memory headroom.
10. Nếu pause dài, xác định collector phase trước khi đổi flag.
11. Nếu throughput thấp, xem CPU GC, allocation rate và collector overhead.
12. Chỉ thay đổi một nhóm flag mỗi lần.
13. Chạy lại cùng workload, warmup và thời gian đo.
14. So sánh với baseline và kiểm tra memory limit.
15. Ghi lại lý do, flag, kết quả và điều kiện thử nghiệm.

Không tối ưu dựa trên một lần Full GC hoặc một dòng log. Tìm xu hướng qua nhiều lần chạy và đảm bảo workload tương đương.

## 17. Troubleshooting GC configuration

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Flag không được nhận diện | Flag bị removed hoặc không có trên vendor/JDK | Kiểm tra PrintFlagsFinal và release docs |
| JVM báo conflicting collector options | Nhiều flag chọn collector cùng được truyền | Chỉ giữ một collector |
| Heap lớn hơn container limit | Xmx/MaxRAMPercentage không chừa native headroom | Tính lại memory budget và kiểm tra RSS |
| JVM không nhận container CPU | Container support hoặc cgroup detection không như dự kiến | Dùng os+container logging |
| G1 pause dài | Phase cụ thể chậm, heap pressure hoặc live set lớn | Đọc gc*=debug, JFR và GC phases |
| G1 GC quá thường xuyên | Young generation bị giới hạn hoặc allocation cao | Kiểm tra Xmn/MaxNewSize và allocation profile |
| G1 Full GC | Evacuation failure, humongous allocation hoặc old-gen pressure | Kiểm tra GC log, heap headroom và object retention |
| ZGC allocation stall | Không đủ headroom khi concurrent GC chạy | Đánh giá Xmx, allocation rate và live set |
| Parallel throughput thấp | GC chiếm CPU hoặc pause target quá chặt | Xem GCTimeRatio, GC threads và workload |
| RSS vượt Xmx | Native memory, metaspace, stacks hoặc direct buffers | Dùng NMT và OS metrics |
| GC log tăng quá nhanh | Logging quá chi tiết hoặc không có rotation | Giới hạn level, filecount và filesize |
| Kết quả thay đổi sau nâng JDK | Ergonomics, defaults hoặc option đã đổi | So sánh PrintFlagsFinal và release notes |

## 18. Ghi nhớ

- GC configuration cân bằng throughput, latency và memory footprint.
- Bắt đầu bằng collector mặc định và đo trước khi tuning.
- G1 là default collector trên server-class machine trong JDK 26.
- Serial phù hợp môi trường nhỏ; Parallel ưu tiên throughput; G1 cân bằng; ZGC và Shenandoah hướng tới pause thấp.
- Xms đặt initial/minimum heap; Xmx đặt maximum heap.
- Java heap không phải toàn bộ process memory; phải chừa chỗ cho native memory, metaspace, stacks và direct buffers.
- MaxGCPauseMillis là soft goal, không phải hard guarantee.
- GCTimeRatio đặt mục tiêu tỷ lệ thời gian GC so với thời gian ứng dụng.
- G1 adaptive IHOP được bật mặc định; tránh cố định young generation nếu muốn G1 tự điều chỉnh pause.
- ZGC từ JDK 24 là generational mặc định; không dùng flag ZGenerational đã bị loại bỏ.
- MaxRAMPercentage mặc định JDK 26 là 25%; trong container cần xác minh memory limit JVM nhận diện.
- ActiveProcessorCount có thể override số CPU JVM dùng để sizing GC và thread pools.
- GC logs và JFR là cơ sở để xác định phase hoặc hành vi cần tuning.
- Thay đổi từng nhóm flag, chạy cùng workload và so sánh với baseline.

## Tài liệu tham khảo chính thức

- [HotSpot VM Garbage Collection Tuning Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/)
- [Ergonomics — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/ergonomics.html)
- [Available Collectors — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html)
- [G1 Garbage Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html)
- [G1 Tuning — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Parallel Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/parallel-collector1.html)
- [The Z Garbage Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)