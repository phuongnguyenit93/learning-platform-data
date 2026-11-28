# Phân tích mẫu thực thi cùng sự kiện GC, cấp phát, khóa và I/O

Khi một service Java chậm, nhìn riêng CPU hoặc heap thường chưa đủ để tìm nguyên nhân. Thread có thể đang chạy code tốn CPU, chờ garbage collection, tranh chấp monitor, bị park trong hàng đợi, hoặc đợi database, network hay file. **Java Flight Recorder (JFR)** ghi lại các sự kiện của JVM và ứng dụng theo dòng thời gian. Khi kết hợp **mẫu stack thực thi** với các event về GC, cấp phát, khóa và I/O trong cùng khoảng thời gian, ta có thể hình thành giả thuyết bottleneck và kiểm chứng bằng dữ liệu.

Bài thuộc chương **Lấy mẫu JFR** của module **JAVA_VERSION_JAVA25**. Nội dung sử dụng JDK 25 và các khả năng JFR còn phù hợp hiện nay, đặc biệt **JEP 518 — JFR Cooperative Sampling**, cùng các event tiêu chuẩn như `jdk.ExecutionSample`, `jdk.ObjectAllocationSample`, `jdk.GarbageCollection`, `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead` và `jdk.FileRead`. Bài tập trung vào phân tích mẫu thực thi cùng sự kiện GC, cấp phát, khóa và I/O; không dùng công cụ profiler cũ hoặc event legacy làm quy trình mặc định.

> **Nguyên tắc đọc dữ liệu:** sample là quan sát thống kê tại những thời điểm được chọn, không phải bản ghi mọi lần gọi method hoặc mọi object allocation. Duration event ghi lại khoảng thời gian của một hoạt động được instrument. Hai loại dữ liệu trả lời hai câu hỏi khác nhau; cần đọc chúng cùng timeline và cùng workload.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích JFR recording, event, stack trace và sampling khác nhau như thế nào.
2. Nêu vai trò của JEP 518 trong cơ chế cooperative sampling của HotSpot trên JDK 25.
3. Dùng `jdk.ExecutionSample` để tìm method và call path tiêu tốn CPU.
4. Dùng `jdk.ObjectAllocationSample` để tìm nơi tạo nhiều object và kết hợp với GC events.
5. Đọc `jdk.GarbageCollection`, `jdk.GCPhasePause` và `jdk.GCHeapSummary` để phân tích chu kỳ GC và pause.
6. Phân biệt monitor contention, Object.wait và park/lock contention qua các event phù hợp.
7. Dùng `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead` và `jdk.FileWrite` để tìm thời gian chờ I/O.
8. Bắt đầu, kiểm tra, dump và dừng recording bằng `jcmd`; tóm tắt và lọc recording bằng `jfr`.
9. Ghép các event theo timestamp, duration, thread và stack trace để kiểm tra giả thuyết.
10. Chọn profile, event threshold và thời lượng recording phù hợp với mức overhead và mục tiêu vận hành.
11. Nhận biết giới hạn của sampling, mất event, dữ liệu nhạy cảm và sai lệch do workload.
12. Xây dựng quy trình điều tra hiệu năng có thể lặp lại cho ứng dụng Java/Spring Boot.

## 2. JFR ghi lại điều gì?

JFR là hệ thống ghi nhận sự kiện trong JVM. Mỗi event có thể chứa timestamp, duration, thread, payload và stack trace tùy loại event cũng như cấu hình recording. JFR lưu dữ liệu vào file nhị phân `.jfr`, có thể phân tích bằng Java Mission Control (JMC) hoặc công cụ dòng lệnh `jfr`.

Các event có thể đến từ:

- HotSpot/JVM: GC, class loading, safepoint, thread, compilation và các hoạt động runtime.
- Java runtime/library: socket, file I/O, monitor, exception và các thao tác khác được instrument.
- Ứng dụng: custom JFR events do nhóm phát triển định nghĩa để ghi mốc nghiệp vụ có ích.

JFR không chỉ là CPU profiler. Nó cho phép đặt nhiều loại dữ liệu lên cùng timeline để tìm mối liên hệ giữa một triệu chứng và hoạt động của JVM.

### 2.1. Phân biệt sample với duration event

| Loại dữ liệu | Cách ghi | Câu hỏi trả lời | Ví dụ |
|---|---|---|---|
| Execution sample | Lấy mẫu stack tại các thời điểm | Thread thường đang thực thi method nào? | `jdk.ExecutionSample` |
| Allocation sample | Lấy mẫu các hoạt động cấp phát | Kiểu object và call path nào tạo nhiều allocation? | `jdk.ObjectAllocationSample` |
| Duration event | Ghi thời điểm bắt đầu/kết thúc hoặc thời lượng | Thread đã chờ bao lâu cho một hoạt động? | `jdk.SocketRead`, `jdk.JavaMonitorEnter` |
| GC event | Ghi chu kỳ và các pha GC | GC bắt đầu lúc nào, pause bao lâu, heap thay đổi ra sao? | `jdk.GarbageCollection`, `jdk.GCPhasePause` |
| Periodic event | Ghi giá trị theo chu kỳ | CPU load hoặc thread statistics thay đổi thế nào? | `jdk.CPULoad`, `jdk.ThreadCPULoad` |

**Sample không phải census.** Nếu recording có 1.000 execution samples ở một method, điều đó không có nghĩa method được gọi đúng 1.000 lần. Một method ngắn có thể chạy hàng triệu lần nhưng hiếm khi trùng thời điểm lấy mẫu; một method chạy lâu có thể xuất hiện trong nhiều sample.

**Duration event không phải CPU time.** Một `SocketRead` kéo dài 200 ms thường cho biết thread bị chặn/chờ trong thao tác đọc trong khoảng đó. Nó không có nghĩa CPU đã chạy liên tục 200 ms cho thao tác này.

### 2.2. Vì sao phải xem các event cùng nhau?

Ví dụ một endpoint có latency tăng:

- `jdk.ExecutionSample` cho thấy method xử lý JSON có nhiều sample.
- `jdk.ObjectAllocationSample` cho thấy serializer tạo nhiều object trung gian.
- `jdk.GCPhasePause` cho thấy GC pause tăng sau các đợt allocation.
- `jdk.SocketRead` cho thấy một số request còn đợi database hoặc service bên ngoài.

Chỉ nhìn một event có thể dẫn tới kết luận sai. Đọc timeline sẽ giúp xác định vấn đề chính nằm ở CPU, allocation/GC, lock hay I/O, và chúng có cùng xảy ra trong request chậm hay không.

## 3. JEP 518: JFR Cooperative Sampling trong Java 25

**JEP 518 — JFR Cooperative Sampling** cải thiện cách HotSpot lấy mẫu stack của các thread. Cơ chế sampling truyền thống có những thách thức khi phải đọc stack ở thời điểm thread đang chạy tùy ý: stack có thể chưa ở vị trí an toàn để walk, gây rủi ro và ảnh hưởng độ tin cậy. Nếu chỉ lấy mẫu tại safepoint, profile có thể bị **safepoint bias** vì các điểm dừng không phân bố đồng đều theo thời gian thực thi.

Cooperative sampling cho phép sampler và thread được lấy mẫu phối hợp tạo một sample đại diện cho vị trí thực thi. Thiết kế hướng tới hai mục tiêu:

- Chỉ walk stack tại các vị trí mà JVM có thể mô tả và xử lý an toàn.
- Giảm sai lệch do chỉ lấy mẫu tại safepoint, để dữ liệu phản ánh chương trình tốt hơn.

Đây là thay đổi ở cơ chế nội bộ HotSpot. Khi phân tích ứng dụng, người dùng vẫn đọc các event JFR quen thuộc như `jdk.ExecutionSample`; không cần tự cài một sampler hoặc viết code điều khiển thread để dùng tính năng này.

### 3.1. Cooperative sampling không biến profile thành bản ghi đầy đủ

JEP 518 cải thiện cách lấy mẫu, nhưng sampling vẫn là kỹ thuật thống kê:

- Không ghi lại mọi method invocation.
- Không bảo đảm mọi instruction hoặc mọi thread đều có sample ở từng khoảng thời gian.
- Không thay thế duration events cho I/O, monitor hoặc park.
- Không cho biết chính xác số object được cấp phát chỉ từ số sample.
- Vẫn phụ thuộc sampling period, recording settings, workload và thời lượng thu thập.

Do đó, không kết luận “method không xuất hiện trong profile thì chắc chắn không tốn thời gian”. Có thể method ngắn, ít được gọi, chưa chạy trong cửa sổ recording hoặc stack trace/event không được bật.

### 3.2. JFR và các loại profiler khác

JFR có thể hoạt động trong môi trường production với cấu hình phù hợp và thường được dùng cho recording liên tục hoặc điều tra sự cố. Tuy vậy, mọi recording đều có chi phí CPU, memory và I/O nhất định. Profiler instrumentation, async profiler hoặc tracing agent có thể trả lời câu hỏi khác, nhưng không cần thay JFR làm nguồn dữ liệu đầu tiên nếu JFR đã ghi được event cần thiết.

## 4. Các event cần biết trong bài

| Nhóm | Event tiêu biểu | Dùng để xem |
|---|---|---|
| CPU / execution | `jdk.ExecutionSample` | Stack của thread tại thời điểm sample |
| CPU load | `jdk.CPULoad`, `jdk.ThreadCPULoad` | Mức tải CPU toàn máy/JVM/thread theo chu kỳ |
| Allocation | `jdk.ObjectAllocationSample` | Loại object, stack và trọng số allocation sample |
| GC | `jdk.GarbageCollection` | Chu kỳ GC, collector/cause và thời lượng |
| GC pause | `jdk.GCPhasePause` | Pha dừng ứng dụng và thời gian pause |
| Heap | `jdk.GCHeapSummary` | Heap trước/sau GC theo event |
| Monitor contention | `jdk.JavaMonitorEnter` | Thời gian chờ vào synchronized monitor |
| Monitor wait | `jdk.JavaMonitorWait` | Thời gian thread chờ qua `Object.wait()` |
| Park | `jdk.ThreadPark` | Thread bị park, thường liên quan LockSupport/AQS |
| Socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` | Thời gian và thông tin đọc/ghi socket |
| File I/O | `jdk.FileRead`, `jdk.FileWrite` | Thời gian và thông tin đọc/ghi file |
| Virtual threads | `jdk.VirtualThreadStart`, `jdk.VirtualThreadEnd`, `jdk.VirtualThreadPinned` | Vòng đời và một số tình huống pinning |

Event có sẵn và cấu hình mặc định có thể phụ thuộc JDK distribution, runtime và recording template. Có thể liệt kê event/metadata của runtime bằng `jfr metadata` hoặc dùng JMC để xem event types trong file.

## 5. Bắt đầu recording bằng JFR

Có hai cách thông dụng: bật recording khi khởi chạy JVM hoặc attach vào JVM đang chạy bằng `jcmd`.

### 5.1. Ghi ngay từ lúc khởi động

Ví dụ ghi profile trong hai phút:

~~~bash
java -XX:StartFlightRecording:filename=app-startup.jfr,settings=profile,duration=2m -jar app.jar
~~~

Các tham số quan trọng:

- `filename`: file recording sẽ được ghi ra.
- `settings=profile`: dùng template profile, thường ghi nhiều dữ liệu hơn default.
- `duration=2m`: giới hạn thời lượng recording.

Đối với service chạy lâu, có thể dùng `settings=default` để thu thập nhẹ hơn trong thời gian dài rồi dùng profile recording ngắn khi điều tra sâu. Hãy xác nhận cấu hình template của JDK đang dùng thay vì giả định mọi template giống nhau.

### 5.2. Attach vào JVM đang chạy

Liệt kê Java processes:

~~~bash
jcmd -l
~~~

Bắt đầu recording cho process có PID:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Dump dữ liệu trong khi recording vẫn tiếp tục:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-snapshot.jfr
~~~

Dừng recording theo tên:

~~~bash
jcmd <pid> JFR.stop name=incident
~~~

`JFR.dump` ghi phần dữ liệu đã thu được ra file nhưng không nhất thiết dừng recording. `JFR.stop` kết thúc recording. Nếu `JFR.start` đã có `duration`, JVM có thể tự kết thúc recording sau khoảng thời gian đó.

### 5.3. Điều kiện để jcmd attach thành công

`jcmd` thường cần chạy trên cùng máy với JVM đích và cùng user/effective identity đã khởi chạy process. Trong container, cần thực thi ở đúng namespace/container và bảo đảm công cụ có thể nhìn thấy JVM. Nếu attach thất bại, kiểm PID, quyền, container boundary và JDK tool tương ứng.

## 6. Tóm tắt và lọc file JFR

Sau khi có `incident.jfr`, đừng bắt đầu bằng cách in toàn bộ file ra terminal. Trước tiên xem summary:

~~~bash
jfr summary incident.jfr
~~~

Lệnh này cho biết thời lượng recording, số lượng event theo loại và các thông tin tổng quan. Sau đó lọc nhóm cần phân tích:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample incident.jfr
~~~

Lọc GC:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary incident.jfr
~~~

Lọc monitor, park và I/O:

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite incident.jfr
~~~

Có thể tăng độ sâu stack trace:

~~~bash
jfr print --stack-depth 20 --events jdk.ExecutionSample incident.jfr
~~~

`jfr print` có thể xuất JSON hoặc XML để phân tích tự động:

~~~bash
jfr print --json --events jdk.ExecutionSample incident.jfr
~~~

### 6.1. Dùng Java Mission Control

JMC là công cụ đồ họa để mở file `.jfr`. Các góc nhìn hữu ích gồm:

- **Method Profiling / Hot Methods:** method xuất hiện thường xuyên trong execution samples.
- **Flame Graph:** quan sát call stacks và nơi thời gian thực thi tập trung.
- **Memory / Allocations:** loại object và stack cấp phát.
- **Garbage Collections:** số chu kỳ, pause và thay đổi heap.
- **Threads / Locks:** monitor contention, park và trạng thái thread.
- **I/O:** socket/file operations và duration.
- **Timeline:** đặt các event trên cùng trục thời gian để xem chúng có trùng với đợt latency tăng hay không.

JMC có thể hiển thị tỷ trọng sample; hãy đọc đó là **tỷ trọng trong mẫu thu được**, không phải phần trăm thời gian wall-clock chính xác cho mọi loại hoạt động.

## 7. Phân tích mẫu thực thi: tìm nơi CPU đang làm việc

`jdk.ExecutionSample` là điểm bắt đầu khi nghi ngờ CPU-bound. Event thường có stack trace của thread tại thời điểm được lấy mẫu. Gom các sample theo top frame hoặc call tree để xem method nào xuất hiện nhiều.

### 7.1. Cách đọc một execution profile

Giả sử một profile cho thấy:

~~~text
com.example.order.PriceCalculator.calculate
com.example.order.OrderService.buildSummary
com.example.order.OrderController.getSummary
~~~

Nếu `PriceCalculator.calculate` xuất hiện trong nhiều stack sample, nó là một ứng viên đáng kiểm tra. Tiếp tục xem:

1. Method có thực sự nằm trong đường xử lý request chậm không?
2. Nó dùng CPU để tính toán, parse/serialize hay lặp qua dữ liệu lớn?
3. Các caller có lặp cùng một phép tính không?
4. Có allocation lớn trong cùng call path không?
5. Có event GC hoặc I/O trùng thời gian không?

Không tối ưu method chỉ vì tên nó xuất hiện nhiều. Một method có thể xuất hiện nhiều vì nó là code dùng chung nhưng mỗi lần chạy rất nhanh. Cần đối chiếu với throughput, latency và stack context.

### 7.2. CPU cao và CPU thấp có ý nghĩa khác nhau

| Quan sát | Giả thuyết ban đầu |
|---|---|
| CPU process cao, nhiều execution samples tập trung ở một call tree | CPU-bound hoặc tính toán lặp |
| CPU thấp, request chậm, nhiều `SocketRead` | Chờ remote service/database |
| CPU thấp, nhiều `JavaMonitorEnter`/`ThreadPark` duration dài | Contention hoặc worker queue |
| CPU dao động theo các GC pauses | Allocation pressure/GC có thể góp phần |
| CPU cao nhưng sample phân tán nhiều method | Nhiều luồng tính toán hoặc bottleneck rộng |

`jdk.ExecutionSample` chủ yếu cho biết code được lấy mẫu khi thread đang thực thi. Thread bị block trong I/O không tiếp tục chạy application code trong thời gian chờ, vì vậy cần đọc thêm duration events để hiểu wall-clock latency.

### 7.3. Sampling period và độ ổn định

Tăng tần suất sampling có thể làm profile chi tiết hơn nhưng cũng tăng lượng dữ liệu và overhead. Không chọn period nhỏ nhất chỉ vì muốn “chính xác nhất”. Hãy bắt đầu bằng `settings=profile`, thu một cửa sổ đủ dài, rồi chỉ thay period khi câu hỏi điều tra yêu cầu.

## 8. Kết hợp allocation samples với GC events

Một ứng dụng có thể CPU-bound do tính toán, nhưng cũng có thể tốn thời gian vì tạo quá nhiều object khiến GC làm việc thường xuyên. JFR giúp nối hai phía: **nơi cấp phát** và **hậu quả GC**.

### 8.1. jdk.ObjectAllocationSample

Event này lấy mẫu các allocation để chỉ ra loại object và stack liên quan. Đây là công cụ tốt để tìm:

- Serializer tạo nhiều object trung gian.
- Boxing hoặc chuyển đổi collection lặp lại.
- Tạo chuỗi/byte array quá nhiều.
- Object tạm được tạo trong vòng lặp nóng.
- Một request path có allocation cao bất thường.

Allocation sample không phải một event cho mọi object. Một số trường có thể biểu diễn trọng số allocation ước tính. Đọc weight và semantics của event trong JMC/JFR metadata; **không đếm số sample rồi coi đó là tổng số object đã tạo**.

### 8.2. jdk.GarbageCollection, jdk.GCPhasePause, jdk.GCHeapSummary

Ba event hỗ trợ các câu hỏi khác nhau:

- `jdk.GarbageCollection`: một chu kỳ GC, collector/cause và duration.
- `jdk.GCPhasePause`: thời gian của các pha pause liên quan GC.
- `jdk.GCHeapSummary`: thông tin heap tại các mốc GC được ghi nhận.

Khi phân tích, xem:

1. GC xảy ra bao nhiêu lần trong cửa sổ recording?
2. Tổng thời gian và pause dài nhất là bao nhiêu?
3. Heap sau GC giảm đáng kể hay vẫn giữ mức cao?
4. Allocation samples tập trung vào loại object/call path nào?
5. Request latency có tăng cùng thời điểm GC pause hay không?

### 8.3. Đọc một tình huống allocation pressure

Giả sử cùng một cửa sổ 60 giây có:

| Dấu hiệu | Quan sát minh họa |
|---|---|
| Allocation samples | Nhiều sample ở `JsonMapper.toTree()` |
| GC events | Minor collections xuất hiện dày hơn khi tải tăng |
| GC pauses | Pause tăng trong cùng khoảng thời gian |
| Heap summary | Heap sau GC giảm mạnh nhưng nhanh chóng tăng lại |
| Execution samples | Mapper và object conversion xuất hiện nhiều |

Giả thuyết hợp lý là serializer tạo lượng object tạm lớn. Bước tiếp theo là đo allocation/request, xem cấu trúc dữ liệu, kiểm tra copy/boxing và đánh giá khả năng streaming. Chưa đủ dữ liệu để kết luận chỉ cần tăng heap; heap lớn hơn có thể trì hoãn GC nhưng không loại bỏ allocation churn.

### 8.4. Không nhầm allocation với memory leak

Allocation rate cao có thể là churn: object tạo ra rồi được thu gom nhanh. Memory leak thường liên quan object còn reachable và giữ lại lâu hơn dự kiến.

- Allocation samples giúp tìm **nơi tạo object**.
- Heap dump/old object analysis giúp xem **object còn được giữ bởi ai**.
- GC/heap summary giúp quan sát **heap trước/sau collection**.

Đừng kết luận memory leak chỉ từ việc thấy nhiều allocation. Cần kiểm tra retained objects, dominator tree hoặc old object samples theo tình huống.

## 9. Phân tích GC theo timeline

GC không phải lúc nào cũng là nguyên nhân gốc. Một đợt GC pause có thể chỉ là hệ quả của allocation tăng, heap sizing không phù hợp hoặc workload thay đổi.

### 9.1. Đọc event GC

Lọc:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary incident.jfr
~~~

Các trường cần quan sát tùy event/collector:

- Thời điểm bắt đầu và duration.
- GC ID và loại/cause.
- Pause time.
- Heap used trước/sau GC.
- Các pha GC có thời lượng lớn.
- Khoảng cách giữa các chu kỳ.

### 9.2. Kết hợp GC với request latency

Nếu hệ thống có metrics latency theo giây hoặc trace spans, hãy đối chiếu timestamp với JFR:

- Request chậm đúng lúc stop-the-world pause: GC có thể trực tiếp góp phần vào latency.
- Request chậm nhưng không có GC pause, đồng thời `SocketRead` kéo dài: ưu tiên điều tra remote dependency.
- GC xuất hiện dày nhưng pause ngắn: có thể ảnh hưởng throughput/CPU, nhưng chưa chắc là nguyên nhân P99.
- Heap sau GC liên tục cao: xem retained heap, cache không giới hạn hoặc object graph giữ tham chiếu.

**Không dùng `System.gc()` để tạo một GC event cho dễ quan sát** trong benchmark production. Nó thay đổi hành vi hệ thống và không đại diện cho workload tự nhiên.

## 10. Phân tích khóa và thread waiting

Một service có thể có CPU thấp nhưng latency cao vì nhiều thread chờ cùng một tài nguyên. JFR cung cấp các event giúp phân biệt các loại chờ.

### 10.1. jdk.JavaMonitorEnter

Event này liên quan thread chờ lấy intrinsic monitor, thường do khối `synchronized`. Xem:

- Duration chờ.
- Thread bị chặn.
- Monitor/class liên quan nếu có.
- Stack trace tại vị trí contention.

Nếu nhiều request thread cùng chờ một monitor, một critical section quá dài hoặc lock quá thô có thể giới hạn throughput.

### 10.2. jdk.JavaMonitorWait

Event này phản ánh thread chờ thông qua `Object.wait()`. Đây là cơ chế wait/notify, khác với thời gian chờ lấy monitor ở `JavaMonitorEnter`.

### 10.3. jdk.ThreadPark

Event này thường hữu ích với các cơ chế dựa trên `LockSupport.park`, ví dụ nhiều cấu trúc trong `java.util.concurrent`, lock/condition và executor. Một thread parked có thể đang chờ công việc hoặc chờ đồng bộ hóa; không phải mọi park đều là lỗi.

| Event | Câu hỏi |
|---|---|
| `jdk.JavaMonitorEnter` | Thread chờ vào synchronized monitor bao lâu? |
| `jdk.JavaMonitorWait` | Thread ở trạng thái wait bao lâu? |
| `jdk.ThreadPark` | Thread bị park trong cơ chế đồng bộ/queue nào? |
| `jdk.ThreadSleep` | Thread ngủ chủ động bao lâu? |

### 10.4. Tình huống lock contention

Giả sử `jdk.JavaMonitorEnter` ghi nhiều event duration dài và stack cùng đi qua `CacheRegistry.lookup()`. Điều tra:

1. Monitor có bảo vệ một map toàn cục không?
2. Critical section có gọi database hoặc HTTP bên trong không?
3. Có thể rút ngắn vùng synchronized hoặc chuyển sang concurrent data structure không?
4. Có thể giảm mức chia sẻ hoặc phân vùng lock không?
5. Event có tập trung ở một vài thread hay toàn bộ worker pool?

Không đổi `synchronized` thành `ReentrantLock` chỉ vì muốn dùng API khác. Nếu logic vẫn khóa cùng một vùng tài nguyên trong cùng thời gian, contention có thể không thay đổi.

### 10.5. Virtual threads

Với virtual threads, xem thêm:

- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` để hiểu vòng đời.
- `jdk.VirtualThreadPinned` khi nghi ngờ virtual thread bị pin vào carrier thread.
- `jdk.ThreadPark` và các event monitor để xem chờ/đồng bộ.

Đừng diễn giải một lượng lớn `ThreadPark` là lỗi ngay lập tức. Virtual threads thường park trong lúc chờ I/O hoặc đồng bộ hóa; cần xem duration, stack và ảnh hưởng tới throughput. Khi có pinning, xác định đoạn code/native interaction gây pinning theo JDK version và runtime behavior hiện hành.

## 11. Phân tích I/O: socket và file

Nếu thread dành nhiều thời gian chờ dữ liệu, execution samples có thể không thể hiện phần thời gian wall-clock đó. Dùng duration events:

- `jdk.SocketRead`
- `jdk.SocketWrite`
- `jdk.FileRead`
- `jdk.FileWrite`

Các event này giúp phân tích thời gian chờ, số byte và thông tin liên quan đến thao tác I/O.

### 11.1. Socket read/write

Các câu hỏi cần đặt:

- Thread chờ response từ remote host bao lâu?
- Có host/port nào chiếm phần lớn thời gian?
- Số byte đọc/ghi có bất thường không?
- Một số request có chờ read lâu hơn các request khác?
- Thời gian chờ nằm ở database, service nội bộ hay external API?

Không thể chỉ nhìn `SocketRead` và khẳng định database chậm: cần biết remote endpoint và stack/call path tương ứng. Nếu event không có thông tin đủ chi tiết, đối chiếu application logs, database metrics và distributed tracing.

### 11.2. File read/write

Các event file I/O giúp tìm:

- Đọc/ghi file cấu hình hoặc template trong request path.
- Ghi log hoặc export file đồng bộ.
- Truy cập storage chậm.
- Đọc file lớn hoặc lặp lại cùng file.
- Thread chờ filesystem trong khi xử lý request.

### 11.3. Threshold mặc định và việc thu nhiều event hơn

Oracle JDK 25 troubleshooting guide lưu ý các event file/socket I/O thường chỉ ghi những thao tác vượt ngưỡng duration mặc định (20 ms trong cấu hình được mô tả). Hạ threshold có thể giúp thấy các thao tác ngắn hơn nhưng làm tăng số event, dung lượng recording và overhead.

Có thể cấu hình threshold riêng khi bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=io-investigation settings=profile duration=2m filename=io.jfr jdk.SocketRead#threshold=10ms jdk.SocketWrite#threshold=10ms jdk.FileRead#threshold=10ms jdk.FileWrite#threshold=10ms
~~~

Đây là cấu hình điều tra có mục tiêu. Không hạ threshold cho tất cả event trong mọi production recording. Bắt đầu với profile mặc định, xem event có bị thiếu do threshold hay không, rồi chỉ điều chỉnh nhóm liên quan.

## 12. Ghép execution samples với GC, allocation, lock và I/O

Đây là kỹ năng trọng tâm: **đừng phân tích từng tab JFR như những báo cáo tách biệt**. Chọn cùng một cửa sổ thời gian và ghép các event theo timestamp, duration, thread và stack trace.

~~~mermaid
flowchart TD
    A["Triệu chứng: latency / throughput / CPU"] --> B["Chọn recording window"]
    B --> C["ExecutionSample<br/>Thread đang chạy code nào?"]
    B --> D["Allocation + GC<br/>Tạo object gì? GC pause lúc nào?"]
    B --> E["Monitor + Park<br/>Thread chờ lock/queue nào?"]
    B --> F["Socket + File I/O<br/>Thread chờ tài nguyên nào?"]
    C --> G["Đặt các event lên cùng timeline"]
    D --> G
    E --> G
    F --> G
    G --> H["Đối chiếu metrics/traces và hình thành giả thuyết"]
    H --> I["Thử thay đổi có kiểm soát"]
    I --> J["Record lại và so sánh"]
~~~

### 12.1. Ma trận chẩn đoán

| Dấu hiệu kết hợp | Giả thuyết | Kiểm tra tiếp theo |
|---|---|---|
| CPU load cao + ExecutionSample tập trung một call tree | CPU-bound | Xem thuật toán, vòng lặp, parse/serialize |
| Allocation samples tập trung + GC dày + pause tăng | Allocation pressure | Tìm object churn, copy, boxing, collection |
| JavaMonitorEnter duration dài + CPU thấp | Monitor contention | Xem critical section và lock scope |
| ThreadPark duration dài + worker queue backlog | Thread chờ queue/lock | Xem executor, pool size, downstream saturation |
| SocketRead kéo dài + CPU thấp | Remote dependency chậm | Đối chiếu DB/API metrics và timeout |
| SocketWrite kéo dài | Remote peer/network backpressure | Xem network, client buffer, server receive rate |
| FileRead/FileWrite kéo dài | Filesystem/storage bottleneck | Xem đường dẫn, kích thước, storage latency |
| GC pause trùng P99 spikes | GC góp phần vào tail latency | Xem pause, allocation, heap before/after |
| CPU cao và SocketRead dài ở các khoảng khác nhau | Nhiều bottleneck theo thời điểm | Chia timeline, không gộp thành một nguyên nhân |

### 12.2. Ví dụ điều tra endpoint chậm

Một endpoint `GET /orders/summary` tăng P99 từ 150 ms lên 900 ms. Trong cùng một recording window:

- CPU load không cao.
- `jdk.ExecutionSample` không cho thấy một method CPU-bound nổi bật.
- `jdk.SocketRead` từ database kéo dài 500–700 ms trên các thread xử lý request.
- `jdk.JavaMonitorEnter` ngắn, không có contention lớn.
- GC pauses nhỏ và không trùng với các request chậm.

Giả thuyết ưu tiên là thời gian chờ database/network, không phải JVM CPU hoặc GC. Bước tiếp theo là kiểm tra query plan, pool saturation, network latency, DB wait events và timeout. Tăng heap hoặc tối ưu loop Java chưa chắc giải quyết được nguyên nhân.

### 12.3. Ví dụ allocation/GC làm tăng latency

Một endpoint khác có CPU load cao, `ObjectAllocationSample` tập trung vào `OrderMapper.toDto()`, GC events xuất hiện dày và P99 spikes trùng với `GCPhasePause`. Lúc này giả thuyết allocation churn có cơ sở hơn.

Kiểm tra mapper có tạo nhiều bản sao list/string, có chuyển đổi qua nhiều DTO trung gian hoặc serialize lại cùng dữ liệu hay không. Thay đổi từng yếu tố, rồi record lại cùng workload để xác nhận allocation rate và GC pause giảm.

## 13. Cấu hình recording theo mục tiêu

Không phải lúc nào cũng nên bật mọi event với threshold bằng zero. Chọn template và event settings theo câu hỏi.

| Mục tiêu | Recording gợi ý | Event trọng tâm |
|---|---|---|
| Theo dõi nền lâu dài | `default` | JVM health và các event mặc định ít overhead |
| Điều tra CPU ngắn hạn | `profile` | `jdk.ExecutionSample`, CPU load |
| Allocation/GC | `profile` + kiểm event allocation/GC | `jdk.ObjectAllocationSample`, `jdk.GarbageCollection`, `jdk.GCPhasePause` |
| Lock contention | `profile` + monitor/park settings | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` |
| I/O chậm | `profile` + threshold có mục tiêu | `jdk.SocketRead/Write`, `jdk.FileRead/Write` |
| Điều tra nhiều nhóm cùng lúc | Recording ngắn, có kế hoạch | Execution, allocation, GC, lock, I/O |

### 13.1. Event settings

JFR cho phép bật/tắt event và cấu hình `period`, `threshold`, stack trace. Có thể dùng `jfr configure` để tạo custom `.jfc`, hoặc cấu hình trực tiếp bằng `jcmd JFR.start`.

Ví dụ trong Java JFR API, setting map có thể chứa:

~~~java
Map<String, String> settings = new HashMap<>();
settings.put("jdk.ExecutionSample#period", "10 ms");
settings.put("jdk.SocketRead#threshold", "10 ms");
recording.setSettings(settings);
~~~

Các event/setting phải được runtime hỗ trợ. Có thể xem setting descriptors bằng JFR API hoặc `jfr metadata`; không hard-code tên event mà chưa kiểm tra JDK đích.

### 13.2. Sampling period ngắn hơn không phải lúc nào cũng tốt hơn

Tần suất cao hơn có thể thu được nhiều sample hơn nhưng đồng thời:

- Tăng overhead của sampler và ghi event.
- Tăng kích thước file.
- Làm khó phân tích do nhiều dữ liệu hơn.
- Tăng ảnh hưởng đến workload cần đo.

Chọn period dựa trên thời gian của method và độ dài recording. Nếu method thực thi trong vài microsecond, tăng sampling frequency không bảo đảm bạn sẽ thấy từng lần gọi.

## 14. JFR trong ứng dụng production: overhead, dữ liệu và quyền truy cập

JFR được thiết kế cho quan sát JVM với overhead thấp khi dùng cấu hình phù hợp, nhưng **không có recording nào miễn phí**. Chi phí phụ thuộc số event, stack traces, threshold, period, thời lượng và workload.

### 14.1. Giảm overhead

- Bắt đầu với template `default` cho recording dài hạn.
- Dùng `profile` trong cửa sổ điều tra ngắn.
- Chỉ bật thêm event khi có câu hỏi cụ thể.
- Không hạ mọi threshold xuống mức thấp nhất.
- Giới hạn duration, file size và nơi lưu recording.
- Đo overhead trên staging/canary trước khi áp dụng cấu hình nặng trong production.

### 14.2. Bảo vệ file recording

JFR có thể chứa thông tin nhạy cảm hoặc giúp suy ra cấu trúc hệ thống, ví dụ:

- Class/method/package names và stack traces.
- Hostname, địa chỉ remote, đường dẫn file.
- System properties, environment details hoặc command-line arguments tùy event/settings.
- Custom event fields do ứng dụng tự ghi.
- Thông tin vận hành về thời gian và tần suất truy cập.

Không ghi password, token, session cookie, raw request body hoặc secret vào custom JFR events. Bảo vệ file `.jfr` như dữ liệu vận hành nội bộ: giới hạn quyền đọc, thời hạn lưu, kênh chuyển giao và scrub trước khi chia sẻ ra ngoài.

### 14.3. Tránh custom event có cardinality cao

Nếu thêm custom event để gắn business operation với JFR, dùng các trường có giá trị chẩn đoán như operation type, outcome hoặc bounded category. Tránh ghi mọi user ID, email, token hoặc request payload; dữ liệu có cardinality rất cao vừa khó phân tích vừa có rủi ro riêng tư.

## 15. Phân tích bằng JFR API khi cần tự động hóa

Ngoài JMC và CLI, Java SE có package `jdk.jfr.consumer` để đọc recording. Ví dụ sau đếm các top-frame method xuất hiện trong `jdk.ExecutionSample`.

~~~java
// File: ExecutionSampleSummary.java
import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class ExecutionSampleSummary {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: ExecutionSampleSummary file.jfr");
            return;
        }

        Map<String, Long> counts;

        try (RecordingFile file =
                     new RecordingFile(Path.of(args[0]))) {

            counts = file.readAllEvents().stream()
                    .filter(event -> event.getEventType()
                            .getName().equals("jdk.ExecutionSample"))
                    .map(RecordedEvent::getStackTrace)
                    .filter(stack -> stack != null
                            && !stack.getFrames().isEmpty())
                    .map(stack -> stack.getFrames().getFirst())
                    .filter(frame -> frame.isJavaFrame())
                    .map(frame -> frame.getMethod())
                    .collect(Collectors.groupingBy(
                            method -> method.getType().getName()
                                    + "." + method.getName(),
                            Collectors.counting()));
        }

        counts.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue()
                        .reversed())
                .limit(20)
                .forEach(entry -> System.out.println(
                        entry.getValue() + " " + entry.getKey()));
    }
}
~~~

**Lưu ý về ví dụ:** đây là bộ đếm số sample theo top frame, không phải bộ đếm invocation hay CPU time tuyệt đối. Nó dùng `readAllEvents()` nên phù hợp recording nhỏ/vừa; với file lớn, cân nhắc đọc tuần tự bằng `RecordingFile.readEvent()` và xử lý từng event để giảm bộ nhớ. Trong JDK 25, `List.getFirst()` có sẵn; nếu muốn hỗ trợ source release cũ hơn, dùng `get(0)` và kiểm tra danh sách rỗng.

Biên dịch với module JFR:

~~~bash
javac --release 25 --add-modules jdk.jfr ExecutionSampleSummary.java
java --add-modules jdk.jfr ExecutionSampleSummary incident.jfr
~~~

### 15.1. Không cộng mọi sample thành một con số thời gian

Một histogram sample có thể hữu ích để xếp hạng method trong cùng recording. Nhưng nếu muốn ước tính CPU time, cần hiểu sampling period, thread states, event semantics và cách tool xây flame graph. Không cộng duration event, allocation weights và execution sample counts vào cùng một chỉ số.

## 16. Troubleshooting khi dữ liệu không như mong đợi

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy `jdk.ExecutionSample` | Recording template không bật event hoặc workload không có thread chạy Java code | Kiểm settings và thời gian recording |
| Sample tập trung ở một method nhưng CPU thấp | Method được gọi nhiều nhưng không nhất thiết là bottleneck CPU toàn process | Đối chiếu CPU load, sample weight/period và latency |
| Không thấy allocation events | Event chưa enabled hoặc template/provider khác | Kiểm `jfr metadata`, JMC event settings |
| Allocation sample ít nhưng heap tăng | Sample không phải census; object giữ lâu có thể quan trọng hơn | Kiểm GC/heap và dùng heap analysis khi cần |
| GC pause không trùng latency | GC có thể không phải nguyên nhân P99 | Đối chiếu socket/lock và request traces |
| Không thấy monitor contention | Lock dùng AQS/park thay vì intrinsic monitor, hoặc threshold chưa phù hợp | Xem `jdk.ThreadPark` và settings |
| Nhiều `ThreadPark` | Thread chờ queue/condition có thể là bình thường | Đọc duration, stack và queue backlog |
| Không thấy socket/file events ngắn | Duration dưới threshold | Hạ threshold riêng cho event liên quan |
| File JFR quá lớn | Recording dài, nhiều event/stack traces hoặc threshold thấp | Dùng template phù hợp, giới hạn duration/size |
| `jcmd` không attach được | Sai PID, user, container boundary hoặc JVM khác | Chạy đúng host/container và identity |
| JFR mất event | Buffer overflow hoặc recorder bị quá tải | Kiểm `jdk.DataLoss`, giảm event volume/stack depth |
| Flame graph thiếu method | Method quá ngắn, ít sample hoặc stack trace không có | Tăng thời lượng recording và kiểm workload |
| Event thread không khớp log thread name | Thread pool reuse, virtual threads hoặc mapping khác | Đối chiếu timestamp, thread ID/name và request trace |
| Recording chứa dữ liệu nhạy cảm | Event/custom payload ghi quá nhiều thông tin | Scrub, hạn chế quyền và giảm field |

### 16.1. Kiểm tra data loss

Nếu recording có event `jdk.DataLoss`, cần xem lượng dữ liệu bị mất và khoảng thời gian liên quan. Recording có data loss có thể làm kết luận sampling/event count thiếu tin cậy. Không bỏ qua cảnh báo này khi so sánh hai file.

### 16.2. Đọc event metadata trước khi tự động hóa

Danh sách event và field có thể thay đổi theo JDK release. Dùng:

~~~bash
jfr metadata incident.jfr
jfr summary incident.jfr
~~~

để kiểm tra recording thực tế. Script phân tích nên chịu được event/field không tồn tại thay vì giả định mọi JVM có cấu hình giống nhau.

## 17. Quy trình điều tra hiệu năng có thể lặp lại

Một quy trình thực tế:

1. **Ghi triệu chứng:** endpoint nào chậm, thời điểm nào, latency percentile nào, CPU/GC/DB metrics ra sao.
2. **Chọn cửa sổ recording:** bắt đầu trước hoặc trong lúc triệu chứng xảy ra và dừng sau khi đã quan sát đủ.
3. **Dùng profile phù hợp:** `default` cho nền dài hạn; `profile` cho điều tra ngắn; thêm event/threshold theo câu hỏi.
4. **Xem summary và data loss:** xác nhận file có thời lượng, event types và chất lượng dữ liệu mong muốn.
5. **Đọc execution samples:** tìm call tree CPU đáng chú ý.
6. **Đọc allocation/GC:** xác định object churn và pause có trùng với latency hay không.
7. **Đọc lock/park:** xác định thread chờ monitor, condition hoặc queue.
8. **Đọc socket/file I/O:** xác định thời gian chờ remote hoặc filesystem.
9. **Đối chiếu metrics/traces/logs:** ghép theo timestamp và request/operation context.
10. **Đưa ra một giả thuyết cụ thể:** nêu bằng chứng, giới hạn và cách kiểm chứng.
11. **Thay đổi một yếu tố:** tránh sửa đồng thời nhiều cấu hình.
12. **Record lại cùng workload:** so sánh latency, throughput, CPU, allocation, GC và waiting time.

~~~mermaid
flowchart TD
    A["Triệu chứng đã xác định"] --> B["Thu JFR có kiểm soát"]
    B --> C["Kiểm recording + data loss"]
    C --> D["CPU samples"]
    C --> E["Allocation + GC"]
    C --> F["Locks + parks"]
    C --> G["Socket + file I/O"]
    D --> H["Ghép timeline với metrics/traces"]
    E --> H
    F --> H
    G --> H
    H --> I["Giả thuyết có bằng chứng"]
    I --> J["Thay đổi một yếu tố"]
    J --> K["Record và benchmark lại"]
~~~

## 18. Bài thực hành

**Bài 1 — Tạo recording:** chạy một ứng dụng Java hoặc Spring Boot trong vài phút với `settings=profile`. Dùng `jfr summary` để liệt kê event types và thời lượng.

**Bài 2 — Execution samples:** tạo một workload tính toán CPU-bound. Dùng JMC hoặc `jfr print --events jdk.ExecutionSample` để tìm method có nhiều sample. Giải thích vì sao số sample không phải số lần gọi.

**Bài 3 — Allocation pressure:** tạo workload tạo nhiều object tạm trong vòng lặp. Xem `jdk.ObjectAllocationSample`, GC events và heap summary. Đề xuất một thay đổi giảm allocation churn.

**Bài 4 — GC correlation:** ghi recording trong lúc tăng tải. Đối chiếu `jdk.GCPhasePause` với latency metrics. Xác định pause nào trùng với request chậm và pause nào không có ảnh hưởng rõ.

**Bài 5 — Monitor contention:** tạo một critical section được nhiều threads truy cập. Dùng `jdk.JavaMonitorEnter` để tìm stack và duration chờ. Rút ngắn critical section rồi record lại.

**Bài 6 — Park/queue:** tạo worker pool có queue hoặc lock. Dùng `jdk.ThreadPark` để phân biệt thread chờ công việc với thread đang chạy CPU.

**Bài 7 — Socket I/O:** gọi một test server có độ trễ có kiểm soát. Ghi `jdk.SocketRead`/`jdk.SocketWrite`, sau đó điều chỉnh threshold và so sánh số event/dung lượng file.

**Bài 8 — File I/O:** đọc một file lớn hoặc ghi file đồng bộ trong request path. Tìm `jdk.FileRead`/`jdk.FileWrite` và đề xuất cách giảm thời gian chờ.

**Bài 9 — Ghép nhiều nhóm:** tạo một workload có allocation, lock contention và socket delay ở các khoảng thời gian riêng. Xác định nhóm event nào chỉ ra bottleneck của từng giai đoạn.

**Bài 10 — JFR API:** viết chương trình đọc `jdk.ExecutionSample` bằng `jdk.jfr.consumer`, in top 10 top-frame methods và ghi rõ đó là sample counts.

**Bài 11 — Recording production:** thiết kế cấu hình JFR nền và một profile recording ngắn cho incident. Nêu cách giới hạn duration, file size, quyền truy cập và scrub dữ liệu.

**Bài 12 — Đánh giá JEP 518:** giải thích cooperative sampling giải quyết vấn đề an toàn stack walking và safepoint bias như thế nào, đồng thời nêu giới hạn vẫn còn của kỹ thuật sampling.

## 19. Checklist hoàn thành

- [ ] Hiểu JFR ghi event theo timeline và có thể chứa timestamp, duration, payload, thread, stack trace.
- [ ] Phân biệt execution sample, allocation sample, duration event và periodic event.
- [ ] Nêu vai trò JEP 518 Cooperative Sampling trong JDK 25.
- [ ] Không coi số `jdk.ExecutionSample` là số lần gọi method hoặc CPU time chính xác.
- [ ] Dùng `jdk.ExecutionSample` để tìm call tree cần kiểm tra.
- [ ] Dùng `jdk.ObjectAllocationSample` để tìm allocation hot paths.
- [ ] Đọc `jdk.GarbageCollection`, `jdk.GCPhasePause` và `jdk.GCHeapSummary`.
- [ ] Phân biệt `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait` và `jdk.ThreadPark`.
- [ ] Dùng `jdk.SocketRead/Write` và `jdk.FileRead/Write` để phân tích I/O duration.
- [ ] Ghép event theo timestamp, duration, thread và stack trace.
- [ ] Biết bắt đầu/kiểm tra/dump/dừng recording bằng `jcmd`.
- [ ] Biết dùng `jfr summary`, `jfr print`, `jfr metadata` và JMC.
- [ ] Hiểu event threshold và sampling period ảnh hưởng lượng dữ liệu/overhead.
- [ ] Kiểm tra `jdk.DataLoss` trước khi đưa ra kết luận.
- [ ] Bảo vệ file `.jfr` và không ghi secret vào custom event.
- [ ] Đo lại sau thay đổi với cùng workload và điều kiện.
- [ ] Không coi JFR là hệ thống distributed tracing hoặc profiler census.

## Tài liệu tham khảo chính thức

- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): thiết kế cooperative sampling, stack walking an toàn và giảm safepoint bias.
- [Java SE 25 — JFR package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event, settings, period, threshold và cách cấu hình Flight Recorder.
- [Java SE 25 — JFR consumer package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): đọc event từ recording bằng Java API.
- [Oracle JDK 25 — jcmd command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` và event settings.
- [Oracle JDK 25 — jfr command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `print`, `metadata`, filter và định dạng output.
- [Oracle JDK 25 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): ghép execution, GC, lock và I/O events để tìm bottleneck.
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): phân tích recording, timeline và flame graphs.
- [JEP 509 — JFR CPU-Time Profiling](https://openjdk.org/jeps/509): bối cảnh bổ sung về profiling CPU time trong JDK 25.

## Kết luận

**JFR hiệu quả nhất khi mẫu thực thi được đọc cùng các event mô tả thời gian chờ và hoạt động của JVM.** `jdk.ExecutionSample` giúp tìm code đang chạy; `jdk.ObjectAllocationSample` chỉ ra allocation hot paths; GC events cho biết pause và heap behavior; monitor/park events cho biết thread đang chờ đồng bộ; socket/file events cho biết thời gian chờ I/O.

Trong Java 25, JEP 518 cải thiện nền tảng lấy mẫu bằng cooperative sampling, nhưng sample vẫn là dữ liệu thống kê. Hãy thu recording có mục tiêu, kiểm tra data loss, ghép các event trong cùng timeline, đối chiếu với metrics/traces và benchmark lại sau thay đổi. Khi phân biệt rõ **CPU execution, allocation/GC, lock waiting và I/O waiting**, bạn có thể tìm bottleneck bằng bằng chứng thay vì suy đoán từ một chỉ số đơn lẻ.
