# 11.9 Xác định bằng chứng cần có trước khi thay heap size hoặc tham số GC

## Mục tiêu

Khi ứng dụng Java chậm, tốn bộ nhớ hoặc xuất hiện lỗi hết bộ nhớ, tăng heap hay chỉnh Garbage Collector (GC) là một **giả thuyết can thiệp**, không phải kết luận mặc định. Trước khi thay đổi, người vận hành cần chứng minh vấn đề liên quan tới quản lý bộ nhớ/GC, xác định giới hạn tài nguyên thực tế, và có số liệu nền để đánh giá tác dụng lẫn tác dụng phụ.

Sau bài này, bạn cần trả lời được bốn câu hỏi: **(1)** Triệu chứng nào đang vi phạm mục tiêu? **(2)** Dữ liệu nào nối triệu chứng với heap/GC? **(3)** Điều gì có thể bị ảnh hưởng bởi thay đổi dự kiến? **(4)** Làm sao xác nhận thay đổi tốt hơn và biết khi nào phải rollback?

Phạm vi minh họa: HotSpot/OpenJDK 17+ (đặc biệt JDK 21), với G1 là ví dụ phổ biến. Tên cờ, khả năng của GC và công cụ có thể khác giữa phiên bản JVM/vendor; luôn xác nhận cấu hình thực tế.

## 1. Xác định vấn đề trước khi chọn tham số

Không có một giá trị heap “đúng” cho mọi hệ thống. Heap lớn hơn có thể giảm số lần thu gom nhưng làm tăng áp lực bộ nhớ của container; pause goal nhỏ hơn có thể tăng số lần GC và chi phí CPU. GC chỉ là một trong nhiều nguồn gây độ trễ.

Trước tiên, ghi rõ:

- **Triệu chứng:** p95/p99 latency vượt SLO, throughput giảm, tỉ lệ lỗi tăng, CPU cao, process bị OOMKilled, lỗi OutOfMemoryError, hoặc pause dài.
- **Thời điểm và phạm vi:** bắt đầu khi nào; xảy ra ở pod/instance nào; chỉ lúc tăng tải, sau deploy hay trong steady state; có tái hiện được không?
- **Ngưỡng chấp nhận:** SLO latency, throughput tối thiểu, error budget, giới hạn CPU và memory, yêu cầu an toàn vận hành.
- **Bối cảnh:** JDK/vendor/phiên bản, collector đang bật, cờ heap, CPU quota, cgroup/container memory limit, số replica và đặc trưng tải.

Một biểu đồ heap used hình răng cưa chỉ cho biết JVM đang cấp phát và thu gom; **tự nó không chứng minh heap thiếu**. Tương tự, p99 tăng đồng thời với CPU cao chưa đủ chứng minh GC là tác nhân.

### Phân biệt các khái niệm bộ nhớ

| Khái niệm | Ý nghĩa khi đọc số liệu | Điều dễ nhầm |
| --- | --- | --- |
| Heap used | Bộ nhớ heap đang được sử dụng ở thời điểm lấy mẫu | Không đồng nghĩa với số object còn sống sau GC |
| Heap committed | Phần heap JVM đã cam kết từ hệ điều hành | Không nhất thiết bằng heap used hoặc RSS |
| Heap max / -Xmx | Trần dung lượng heap do JVM cho phép | Không phải trần tổng bộ nhớ của tiến trình |
| Live set (ước lượng) | Các object còn reachable sau một lần GC phù hợp | Occupancy ngay sau young GC không phải phép đo live set tuyệt đối |
| Non-heap/native | Metaspace, code cache, stack, direct buffer, vùng nội bộ JVM và native allocations | Có thể làm RSS tăng dù heap còn trống |
| RSS / working set | Bộ nhớ vật lý/working set được quan sát ở cấp process/container | Khác với reserved/committed được báo bởi JVM; phụ thuộc công cụ |
| GC pause (STW) | Khoảng thời gian ứng dụng phải dừng cho pha GC/safepoint liên quan | Không thể thay thế toàn bộ phép đo latency hay CPU do concurrent GC |

**Điểm mấu chốt:** OutOfMemoryError: Java heap space, OutOfMemoryError: Metaspace, lỗi native thread và container OOMKilled có nguyên nhân cũng như bằng chứng cần kiểm tra khác nhau.

## 2. Hồ sơ bằng chứng tối thiểu

Trước bất kỳ đề xuất đổi heap/GC nào, thu thập dữ liệu dưới cùng một cửa sổ thời gian và cùng điều kiện tải. Mỗi nguồn có câu hỏi riêng:

| Nhóm | Cần có bằng chứng | Dùng để quyết định |
| --- | --- | --- |
| Mục tiêu ứng dụng | RPS/throughput, p50/p95/p99, errors/timeouts, SLO, thời điểm spike | Có vấn đề thực sự và thay đổi cần cải thiện chỉ số nào? |
| Workload | Request mix, concurrency, batch size, phân bổ payload, cache warm-up, deploy/scaling events | Có đang so sánh cùng tải và cùng giai đoạn vận hành? |
| Cấu hình chạy | Java version/vendor, GC hiện tại, -Xms/-Xmx, MaxRAMPercentage nếu áp dụng, JVM flags, CPU/memory quota | JVM đang hoạt động dưới giới hạn nào, có đúng với suy đoán không? |
| Heap | Used/committed/max theo thời gian, mức sử dụng sau các chu kỳ GC, peak theo tải | Heap thiếu headroom, allocation burst hay live set đang tăng? |
| Hoạt động GC | Timestamp, loại/cause GC, thời lượng pause, tần suất, tổng thời gian GC, Full GC, concurrent cycle, dấu hiệu allocation/evacuation failure nếu collector báo | Có tương quan nhân quả hợp lý giữa GC và triệu chứng không? |
| CPU và OS/container | Process/container CPU, throttling, RSS/working set, memory limit, OOM events, swap/page pressure khi áp dụng | Có vấn đề ngoài heap hoặc giới hạn tài nguyên khiến tuning phản tác dụng không? |
| Phân bổ/giữ object | Allocation hotspots từ JFR/profiler, class histogram/heap dump nếu thật cần, trend object sống | Tăng heap chỉ trì hoãn leak hay workload cấp phát quá nhiều? |
| Những nguồn độ trễ khác | Thread states, lock contention, I/O, database/network latency, safepoint không thuộc GC | Có nguyên nhân khác giải thích p99 tốt hơn không? |

**Tối thiểu để kết luận:** (a) triệu chứng đo được; (b) cấu hình và giới hạn tài nguyên đã xác minh; (c) dữ liệu heap và GC có timestamp; (d) tương quan với tải và latency; (e) kế hoạch đo trước/sau. Thiếu một mục thì ghi “chưa đủ bằng chứng”, thay vì đoán tham số.

### Chuẩn hóa thời gian và độ tin cậy

Sử dụng timestamp có múi giờ/UTC nhất quán, đối chiếu đồng hồ giữa APM, hệ điều hành và GC log. Đo nhiều khoảng tải tương đương, gồm thời điểm bình thường lẫn lúc lỗi; phân biệt warm-up với steady state. Tránh kết luận dựa vào một snapshot heap hoặc một log sự kiện đơn lẻ. Ghi rõ thời gian lấy mẫu, cấu hình, đơn vị (MiB, ms, %, requests/s) và phiên bản bản build.

## 3. Thu thập bằng chứng trên JVM đang chạy

Ví dụ dưới đây dùng JDK 17+ và shell trên Linux/macOS; thay PID/đường dẫn theo môi trường thực tế. Các lệnh attach thường yêu cầu cùng người dùng hệ điều hành với tiến trình Java, quyền container phù hợp và JDK tools có sẵn; trên một số image chỉ có JRE hoặc cơ chế attach bị hạn chế.

### 3.1. Xác nhận JVM, cờ và heap hiện tại

~~~bash
java -version
jcmd -l
PID=12345  # Thay bằng PID thật của tiến trình cần khảo sát
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jstat -gcutil "$PID" 1000 30
~~~

Cách đọc:

- **VM.command_line / VM.flags:** xác nhận cờ thực sự của tiến trình, tránh lấy cấu hình từ tài liệu triển khai đã cũ. Có thể chứa thông tin nhạy cảm trong arguments: chỉ chia sẻ bản đã loại bỏ bí mật.
- **GC.heap_info:** ảnh chụp tình trạng heap hiện tại; cấu trúc báo cáo tùy collector. Muốn hiểu xu hướng phải lấy mẫu liên tục hoặc dùng telemetry.
- **jstat -gcutil:** lấy mẫu mỗi 1 giây, 30 lần. Các cột tỷ lệ lấp đầy và số lần/thời gian GC tùy collector/JDK; tổng thời gian GC cần tính chênh lệch trên cửa sổ đo, không dùng tổng từ lúc process khởi động làm tỷ lệ của cửa sổ ngắn.
- **Cảnh báo:** jcmd và jstat cung cấp phần thông tin khác nhau; không dùng kết quả từ một PID khác hoặc từ thời điểm sau restart để giải thích sự cố trước restart.

### 3.2. GC log có timestamp để đối chiếu latency

Bật Unified JVM Logging từ khi khởi động ứng dụng, nếu phương án triển khai cho phép:

~~~bash
java -Xlog:help
java '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
~~~

Đây là ví dụ **thu thập log**, không phải đề xuất heap size. Cần bảo đảm đường dẫn ghi hợp lệ, rotation/dung lượng disk phù hợp, quyền bảo vệ log và kiểm tra chi phí quan sát. Nếu dịch vụ đã chạy, đánh giá khả năng cấu hình logging động bằng lệnh được JVM hỗ trợ và chính sách vận hành; đừng restart production chỉ để thử một cờ mà chưa có phương án an toàn.

Đọc GC log theo các trục:

1. **When:** timestamp của pause/GC cycle có trùng khoảng p99 hoặc timeout tăng không?
2. **What:** young/mixed/full GC, safepoint, concurrent marking, nguyên nhân được collector ghi nhận.
3. **How long/how often:** phân phối pause (p95/p99/max), số lần GC mỗi phút, tỉ lệ thời gian STW trong cửa sổ đo; đừng chỉ nhìn trung bình.
4. **Memory before/after:** heap occupancy thu hồi được bao nhiêu, có tăng theo cùng mức tải hay không; dữ liệu “after” phụ thuộc loại sự kiện.
5. **Pressure:** có Full GC, to-space exhausted/evacuation failure, allocation failure, humongous allocation hoặc bất thường do collector báo? Chỉ diễn giải sau khi biết collector và JDK.

GC có thể chạy concurrent và dùng CPU mà không có pause lớn. Vì vậy chỉ cộng pause time vẫn chưa mô tả hết chi phí GC. Ngược lại, độ trễ dài có thể do safepoint, lock, I/O hoặc scheduler ngay cả khi GC pause ngắn.

### 3.3. JFR và nguồn chứng cứ ứng dụng

Khi cần đối chiếu allocation/GC/CPU/latency, cân nhắc Java Flight Recorder (JFR), nếu môi trường cho phép:

~~~bash
jcmd "$PID" JFR.start name=heap_gc_probe settings=profile duration=5m filename=heap-gc-probe.jfr
jcmd "$PID" JFR.check
jfr summary heap-gc-probe.jfr
~~~

Lệnh summary chạy **sau khi file ghi xong** và tại nơi có file. Năm phút chỉ là ví dụ; chọn cửa sổ đại diện cho vấn đề. Hồ sơ profile có chi phí thu thập, cần đo/giới hạn và bảo vệ dữ liệu nhạy cảm. Dùng JFR để tìm allocation hotspot, GC events, thread/lock/I/O activity mà recording thực sự chứa; không khẳng định mọi event đều bật với mọi cấu hình.

Ghép JFR, metrics APM và log ứng dụng theo timestamp. Ví dụ request p99 tăng 500 ms nhưng không có pause hoặc GC CPU tương ứng thì chưa đủ cơ sở nói GC là nguyên nhân. Nếu phát hiện lock contention hoặc truy vấn database chậm cùng thời điểm, ưu tiên điều tra tác nhân đó.

### 3.4. Native memory và container memory

Với HotSpot, Native Memory Tracking (NMT) giúp xem phần native memory do JVM theo dõi, nhưng thường **phải bật lúc khởi động**; ví dụ cấu hình quan sát:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Khi NMT đã bật:

~~~bash
jcmd "$PID" VM.native_memory summary
~~~

NMT báo reserved/committed theo nhóm, không phải phép đo RSS, cũng không bao trùm mọi cấp phát của thư viện native bên ngoài JVM. Không nên bật/tắt tùy tiện trên production mà không xét overhead và quy trình restart.

Nếu chạy Linux cgroup v2, có thể kiểm tra từ đúng cgroup của tiến trình/container:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
~~~

Đường dẫn trên chỉ là trường hợp mount cgroup v2 thông thường; vị trí và giao diện khác trên cgroup v1/Kubernetes/host. Đối chiếu thêm process RSS, container working set, CPU throttling và sự kiện OOMKilled từ hệ điều phối. **Memory limit áp dụng cho nhiều thành phần ngoài heap**: metaspace, code cache, stack threads, direct/native buffers, GC metadata, thư viện native và các chi phí liên quan.

### 3.5. Heap dump, histogram: chỉ khi giả thuyết cần đến

Nếu mức used sau những chu kỳ GC phù hợp liên tục tăng ở tải tương tự, nghi vấn object retention/leak cần dữ liệu về object sống và đường tham chiếu. Có thể cân nhắc histogram, JFR allocation profiling hoặc heap dump với kế hoạch riêng. **GC.class_histogram** có thể gây pause/GC; **GC.heap_dump** có tác động cao và thường yêu cầu Full GC nếu không có tùy chọn đặc biệt. Heap dump có thể chứa token, dữ liệu người dùng và làm đầy disk. Chỉ thực hiện khi có quyền, không gian và thời gian bảo trì phù hợp; không lấy dump thường xuyên như một metric nhẹ. Tăng -Xmx không chữa được leak.

## 4. Từ số liệu đến chẩn đoán

### 4.1. Kiểm tra mối liên hệ với latency

Một quan hệ đồng thời chưa đủ để chứng minh nguyên nhân. Với mỗi sự cố, lập timeline chung:

| Mốc thời gian | Ứng dụng | GC/heap | CPU/OS | Nhận định |
| --- | --- | --- | --- | --- |
| Trước sự cố | RPS, p99 bình thường | Pause, occupancy nền | RSS và CPU nền | Đường cơ sở |
| Lúc sự cố | p99/errors tăng rõ | GC event/cycle nào, thời lượng, used trước–sau | Throttling, OOM, I/O, lock | Có trùng thời gian và cường độ đủ giải thích không? |
| Sau sự cố | p99 hồi phục hay tiếp tục xấu | Heap có được thu hồi, live set còn cao? | Tài nguyên hồi phục? | Nguyên nhân nào còn hợp lý? |

Ví dụ giả định: tại 10:00, p99 tăng từ 90 ms lên 550 ms; GC log chỉ có pause 12–24 ms và không có Full GC gần đó. Không thể quy toàn bộ 460 ms chênh lệch cho các pause ấy; cần điều tra request path, contention, CPU throttling và I/O. Nếu thấy các pause Full GC cỡ 600 ms trùng các lần p99 tăng, GC trở thành giả thuyết mạnh hơn, nhưng vẫn phải xem **vì sao** heap/collector bị dồn vào Full GC.

### 4.2. Đọc “heap after GC” đúng cách

- Theo dõi occupancy sau những lần collection có ý nghĩa tương đương, cùng collector và tải; không so bừa số after-young-GC với after-full-GC.
- Nếu đáy heap dần tăng xuyên nhiều chu kỳ ở cùng tải, nghi retention, cache tăng không giới hạn hoặc live set tăng. Cần allocation/retention evidence; mở rộng heap có thể chỉ trì hoãn lỗi.
- Nếu đáy ổn định nhưng đỉnh chạm giới hạn theo burst và GC phải chạy dồn dập, giả thuyết thiếu heap headroom đáng kiểm tra, sau khi loại trừ allocation burst bất thường.
- Nếu heap còn dư nhiều và thời gian GC nhỏ so với SLO, việc đổi -Xmx hoặc GC không có nền tảng đo lường vững chắc.
- Không dùng một ngưỡng occupancy chung, ví dụ “80% là phải tăng Xmx”: tỷ lệ này phụ thuộc collector, GC phase, phân bố object, tải và khoảng đo.

### 4.3. Phân biệt throughput, latency và footprint

**Latency:** GC pause hoặc CPU contention có thể góp phần tăng tail latency. So timestamp và độ dài pause với p99, đồng thời kiểm tra các nguyên nhân ngoài GC.

**Throughput:** GC ăn nhiều CPU/thời gian trong các khoảng tải ổn định có thể giảm công suất xử lý. Đổi pause goal có thể khiến GC thường xuyên hơn, giảm throughput dù pause đơn lẻ ngắn đi.

**Footprint:** Một heap tối đa lớn có thể làm JVM giữ thêm bộ nhớ trong quá trình vận hành, khiến container gần memory limit. Xmx đặt giới hạn heap; nó **không** bảo đảm toàn process luôn nằm dưới giới hạn container.

## 5. Ma trận quyết định: cần thấy gì trước khi chỉnh?

| Dấu hiệu quan sát | Bằng chứng phải kiểm tra thêm | Hướng xử lý hợp lý |
| --- | --- | --- |
| p99 tăng, GC pause nhỏ/không tương quan | APM traces, thread/lock, I/O, CPU throttling, safepoint | Ưu tiên nguyên nhân ngoài GC; chưa có cơ sở tuning |
| Young GC rất thường xuyên, allocation rate cao | Allocation profiling, request mix, live set ổn định, CPU/GC time | Giảm churn/object allocation nếu có thể; sau đó mới thử headroom/GC |
| Full GC hoặc evacuation/allocation failure lặp lại | GC log, occupancy trước–sau, peak load, retained objects, container headroom | Xác định thiếu heap tạm thời hay live set/leak; chỉ thử tăng heap khi có dư địa |
| Sau GC, occupancy tăng dài hạn dù tải tương đương | Retention trend, heap histogram/dump khi đủ điều kiện, cache policy | Điều tra leak/object giữ lâu; tăng heap không phải cách sửa gốc |
| Container OOMKilled, heap chưa đầy | RSS/working set, native/direct/metaspace, threads, cgroup events | Điều tra native/limit; tăng Xmx có thể làm tệ hơn |
| GC pause gây tail latency đã được chứng minh | Pause histogram, SLO, GC CPU, throughput, collector/JDK | Thử pause goal/collector trong phép đo đối chứng có guardrail |
| Ứng dụng khỏe, GC ít, có đủ memory headroom | SLO và đường cơ sở ổn định | Giữ nguyên; tránh tuning vì cảm giác “heap chưa tối ưu” |

**Chẩn đoán trước tham số:** cần chứng minh nút thắt đang ở đâu. Không có một tham số nào vừa bảo đảm p99 thấp, throughput cao, footprint nhỏ cho mọi workload.

## 6. Chọn giả thuyết thay đổi và hiểu trade-off

### 6.1. Thử thay -Xmx khi nào?

Cơ sở hợp lý: có GC pressure do thiếu không gian làm việc tạm thời **sau khi đã hiểu live set và allocation rate**, và memory budget thực sự cho phép. Trước khi đề xuất Xmx mới, ghi:

- Heap max/committed/used hiện tại, đỉnh dùng dưới peak load, đáy sau GC, allocation rate, số/độ dài Full GC và các dấu hiệu collector báo thiếu headroom.
- Memory limit/host capacity, peak RSS/native/non-heap, margin cho thread stacks/direct buffers/code cache/metaspace, biến động theo tải và tiến trình khác.
- Dự báo tác động đến tần suất GC, thời lượng pause, container OOM risk và số replica.

Một phép kiểm tra ngân sách sơ bộ là: **Xmx ứng viên + phần non-heap/native có thể tăng đến đỉnh + margin an toàn phải thấp hơn giới hạn RAM khả dụng**. Đây là điều kiện cần để thử nghiệm, không phải công thức chọn heap tự động. Đừng trừ số RSS hiện tại khỏi memory limit rồi gán toàn bộ phần dư cho heap: RSS hiện tại đã bao gồm heap resident, và nhiều phần native có thể tăng theo tải.

### 6.2. Thử thay -Xms khi nào?

-Xms là heap ban đầu; -Xmx là heap tối đa. Chỉ cân nhắc -Xms khi quan sát thấy việc heap mở rộng/co lại hoặc giai đoạn warm-up gây bất ổn đáng kể; đo thời gian khởi động, RSS/committed và khả năng dùng RAM của môi trường. Đặt -Xms bằng -Xmx có thể phù hợp một số service ổn định nhưng cam kết bộ nhớ cao hơn, không phải quy tắc phổ quát.

### 6.3. -XX:MaxRAMPercentage và giới hạn container

Nếu không đặt -Xmx trực tiếp, HotSpot có thể chọn max heap từ RAM được JVM nhận diện và các cờ phần trăm như -XX:MaxRAMPercentage. Cần đối chiếu **giá trị max heap thực tế** trong process với cgroup/container limit. Không đồng thời diễn giải -Xmx và MaxRAMPercentage như hai trần heap độc lập được cộng vào nhau. Tăng tỷ lệ heap mà không dành headroom cho native memory có thể dẫn tới OOMKilled.

### 6.4. Pause goal và lựa chọn GC

Với G1, -XX:MaxGCPauseMillis là **mục tiêu mềm**, không phải bảo đảm pause luôn thấp hơn giá trị đã đặt. Siết mục tiêu có thể dẫn tới GC thường xuyên hơn, tăng CPU hoặc giảm throughput. Khi đánh giá, so **p99 ứng dụng + GC pause histogram + GC CPU + throughput + RSS**, không chỉ một biểu đồ pause.

Đổi collector (ví dụ các collector tối ưu latency nếu JDK/vendor hỗ trợ) là thay đổi lớn: cần xác nhận khả năng tương thích, CPU/memory cost, hành vi theo workload và cấu hình vận hành. Với G1, tránh khóa young generation bằng -Xmn hay NewRatio chỉ để “ít GC hơn” khi chưa có bằng chứng; G1 dùng kích thước young generation để điều chỉnh pause goal. Các cờ chuyên sâu như IHOP, region size, thread counts chỉ nên xét khi dữ liệu GC cụ thể chỉ ra nút thắt liên quan và thử nghiệm chứng minh cải thiện.

## 7. Thiết kế phép thử đối chứng trước khi áp dụng

Mỗi phép thử là một giả thuyết đo được, ví dụ: “Với cùng request mix ở 800 RPS, tăng max heap từ 2 GiB lên 2,5 GiB sẽ giảm Full GC gây p99 spike, trong khi peak RSS vẫn nằm dưới budget.” Các số ở đây **chỉ minh họa**, không phải khuyến nghị cấu hình.

1. **Lưu baseline:** revision/build, Java version, GC, toàn bộ JVM flags liên quan, CPU/memory limit, số replica, tải, thời gian warm-up và khoảng steady state; lưu GC logs/JFR/metrics cùng mốc thời gian.
2. **Đổi một biến chính:** ví dụ chỉ -Xmx; tránh đồng thời đổi GC, replica, CPU limit, cache policy hoặc request mix khiến kết quả không quy được nguyên nhân.
3. **Tạo tải so sánh hợp lệ:** cùng concurrency, request mix, payload, peak/burst và warm-up; lặp lại đủ số lần để tránh nhiễu. Nếu A/B production, kiểm soát traffic split và khác biệt instance.
4. **Đo cùng cửa sổ và đơn vị:** p50/p95/p99, throughput, errors, GC count/pause p95/p99/max, tổng thời gian pause, GC/total CPU, allocation rate, heap peak/after-GC, process/container RSS, throttling và OOM events.
5. **Xác định guardrail trước:** không đánh đổi SLO hoặc tăng OOM risk quá mức; chuẩn bị rollback nhanh về cấu hình baseline nếu p99, error rate, CPU/RSS hay stability xấu đi.
6. **Kết luận dựa vào phân phối và lặp lại:** khác biệt cần đủ lớn, ổn định, có ý nghĩa với mục tiêu ứng dụng. Chỉ báo GC tốt hơn nhưng p99/throughput không cải thiện có thể không đáng thay đổi.

Mẫu bảng ghi quyết định:

| Trường | Baseline | Ứng viên | Điều kiện chấp nhận |
| --- | --- | --- | --- |
| JDK / collector / cờ | Ghi giá trị thực | Ghi đúng một thay đổi chính | Môi trường tương đương |
| Tải và cửa sổ | RPS, request mix, thời gian | Cùng workload | Chênh lệch tải trong ngưỡng đã chọn |
| p99 / errors | Số đo nền | Số đo mới | Đạt SLO, không phát sinh regression |
| GC pause và CPU | Histogram, tổng pause, GC CPU | Cùng cách tính | Có cải thiện liên quan tới giả thuyết |
| Heap after-GC và RSS | Trend/peak | Trend/peak | Không đẩy process/container tới OOM |
| Quyết định | Giữ lại dữ liệu | Keep / rollback | Có bằng chứng, chủ sở hữu và ngày review |

## 8. Ví dụ phân tích có đủ/thiếu bằng chứng

### Tình huống A — chưa được phép kết luận “phải tăng heap”

Service trên JDK 21/G1, memory limit 4 GiB, Xmx 2 GiB. Giờ cao điểm, p99 từ 90 ms lên 550 ms; GC pauses tối đa 24 ms gần các spike, không thấy Full GC; container working set đã gần giới hạn và CPU throttling tăng. Từ dữ liệu này **chưa đủ bằng chứng** cho tăng Xmx hoặc đổi GC. Tăng Xmx có thể làm rủi ro OOMKilled lớn hơn. Cần xem traces, CPU quota/throttling, lock và I/O, đồng thời xác nhận memory breakdown và tương quan theo timestamp.

### Tình huống B — có lý do để thử nghiệm, chưa đủ để triển khai thẳng

Một service khác có Full GC dài trùng với p99 spike, GC log báo thiếu headroom trong peak burst; sau các collection tương đương, occupancy nhìn chung ổn định, không có dấu hiệu retention tăng lâu dài. Metrics cho thấy memory limit vẫn có margin cho native/GC overhead nếu thử Xmx lớn hơn. Có thể đặt giả thuyết “thiếu heap headroom tại peak” và thử **một thay đổi Xmx** dưới tải kiểm soát. Nếu chỉ pause giảm nhưng RSS sát memory limit hoặc throughput xấu, phải loại ứng viên; nếu Full GC biến mất, p99 đạt SLO và CPU/RSS an toàn qua nhiều lần thử tương đương, mới có cơ sở triển khai.

### Tình huống C — dấu hiệu leak, tăng heap chỉ trì hoãn

Sau mỗi đợt tải tương tự, mức heap occupancy sau collection tiếp tục cao hơn qua hàng giờ, số object retained tăng và cuối cùng phát sinh Full GC/OOME. Cần xem allocation/retention, cache size, collection giữ reference, thread-local, listener hoặc classloader theo triệu chứng cụ thể. Heap tăng có thể kéo dài thời gian tới sự cố nhưng không giải quyết nguyên nhân giữ object.

## 9. Checklist trước khi thay một tham số

- [ ] Triệu chứng, SLO và thời điểm vi phạm đã đo được; có baseline đủ đại diện.
- [ ] Đã xác minh JDK/vendor, collector, các cờ JVM **đang có hiệu lực**, CPU/memory limit, build và workload.
- [ ] GC log/metrics có timestamp trùng với latency/errors, cùng timezone và đủ giai đoạn trước–trong–sau.
- [ ] Có trend heap used/committed/max, post-GC occupancy, allocation rate hoặc phương án đo bổ sung khi thiếu.
- [ ] Đã đối chiếu pause/GC CPU/throughput với vấn đề; kiểm tra lock, I/O, CPU throttling và safepoint ngoài GC.
- [ ] Đã phân biệt Java heap OOME, native/metaspace issue và container OOMKilled; xác minh RSS/memory headroom.
- [ ] Đã điều tra retention/leak nếu đáy heap tăng theo thời gian ở cùng tải.
- [ ] Viết giả thuyết: thay **tham số nào**, vì quan sát gì, kỳ vọng chỉ số nào cải thiện, tác dụng phụ nào cần theo dõi.
- [ ] Có phép so sánh hợp lệ, guardrail, rollback và người chịu trách nhiệm đánh giá.
- [ ] Nếu thiếu bằng chứng, ghi rõ phần thiếu và **chưa thay** heap/GC chỉ vì cảm giác hệ thống “thiếu RAM”.

## 10. Kết luận thực hành

Hãy coi heap size và GC flags là **biến cần kiểm chứng** trong một hệ thống nhiều nguồn gây chậm/hết bộ nhớ. Chuỗi ra quyết định đúng là:

**Triệu chứng/SLO → cấu hình và giới hạn thực tế → timeline workload + heap + GC + OS → loại trừ nguyên nhân khác → giả thuyết có thể bác bỏ → A/B với guardrail → quyết định giữ hoặc rollback.**

Chứng cứ mạnh nhất không phải “GC chạy nhiều” hay “heap đầy 80%”, mà là: **dữ liệu đúng lúc, đúng tiến trình, đúng collector; diễn giải được cơ chế; và thay đổi được xác nhận cải thiện mục tiêu ứng dụng mà không đẩy rủi ro sang CPU, native memory hoặc độ ổn định**.

### Tài liệu tham khảo chính thức

- Oracle JDK 21 — jcmd: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Java launcher, JVM options và Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — Garbage-First GC Tuning: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html
