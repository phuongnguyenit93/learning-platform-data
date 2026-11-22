# 7.3 JConsole để xem biểu đồ, thuộc tính và thao tác quản lý JVM

## Mục tiêu học tập

**JConsole** là công cụ giao diện đồ họa (GUI) đi kèm JDK, sử dụng **Java Management Extensions (JMX)** để quan sát và, khi được cấp quyền, **quản lý** một Java Virtual Machine đang chạy. Không giống một dashboard chỉ hiển thị biểu đồ, JConsole còn truy cập được cây **MBeans**: đọc thuộc tính (attributes), xem notifications và gọi operations. Những khả năng đó rất hữu ích khi chẩn đoán nhưng cũng có rủi ro: một thao tác bấm nút có thể kích hoạt GC, thay đổi thiết lập logging hoặc thực thi chức năng quản trị ngay trong tiến trình JVM đích.

Bài này hướng dẫn thực hành JConsole theo ba trọng tâm của đề bài: **xem biểu đồ**, **đọc thuộc tính**, **thực hiện thao tác quản lý JVM** một cách có kiểm soát.

Sau bài học, bạn có thể:

- Khởi chạy JConsole từ JDK 17+, kết nối đúng **JVM local hoặc remote** qua JMX, kiểm tra PID, thời gian khởi động và quyền truy cập.
- Đọc đúng các tab **Overview, Memory, Threads, Classes, VM Summary và MBeans**; hiểu mỗi biểu đồ/giá trị là snapshot hay một chuỗi thời gian từ lúc theo dõi.
- Điều hướng cây `java.lang` và custom MBeans, phân biệt **read-only attribute**, **writable attribute**, **operation** và **notification**.
- Phân biệt các thao tác quan sát với hành động thay đổi trạng thái như **Perform GC**, **set Verbose**, **invoke operation** hoặc **heap dump**, và biết khi nào phải xin quyền/phê duyệt vận hành.
- Tự xây một chương trình Java 17+ đăng ký MBean có thuộc tính và operation; kết nối JConsole để đọc, ghi, gọi method và quan sát biểu đồ.
- Thu thập dữ liệu có timestamp, đơn vị, context và giới hạn; bảo vệ JMX remote bằng xác thực, mã hóa, quyền tối thiểu và giới hạn mạng.

> Phạm vi chính: Java SE/JDK 21 với hành vi minh họa phù hợp cho JDK 17+. Màn hình cụ thể có thể khác theo JDK, hệ điều hành, look-and-feel, JVM implementation và MBeans mà ứng dụng đăng ký. **Các thao tác nhạy cảm phải làm trên JVM thử nghiệm, không chạy tùy tiện trên production.**

## 1. JConsole, JMX và MBean: hiểu đúng vai trò

Để sử dụng JConsole có hiệu quả, cần tách ba lớp:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **JVM đích** | Tiến trình thật đang chạy code ứng dụng và cung cấp các chỉ số quản trị | PID của service hoặc chương trình demo |
| **JMX agent / MBeanServer** | Công bố các MBean, phục vụ việc đọc thuộc tính, gọi operation, nhận notification | Platform MBean server của JVM |
| **JConsole** | Công cụ GUI **khách** kết nối vào JMX và hiển thị/điều khiển thông tin | Các tab Memory, Threads, MBeans |

Các platform MXBeans như `MemoryMXBean`, `ThreadMXBean`, `ClassLoadingMXBean` và `RuntimeMXBean` cung cấp dữ liệu chuẩn. Ứng dụng hoặc thư viện cũng có thể đăng ký **custom MBeans** cho hàng đợi, cache, trạng thái tính năng, các counters hoặc thao tác quản trị.

Một lược đồ:

```text
+---------------------------+           JMX connector           +---------------------------+
| JConsole (GUI, client)    | <--------------------------------> | JVM đích (process)         |
|  - Overview / Memory      |      local attach hoặc remote      |  Platform MBeanServer      |
|  - Threads / Classes      |        JMX được cấp quyền         |   - java.lang:* MXBeans    |
|  - VM Summary / MBeans    |                                    |   - app custom MBeans      |
+---------------------------+                                    +---------------------------+
              |                                                               |
              +-- Đọc thuộc tính, hiển thị series                              +-- MXBeans phản ánh VM
              +-- Gọi operation, ghi thuộc tính khi có quyền                  +-- Operations chạy ở JVM
              +-- Subscribe notifications khi được hỗ trợ                    +-- Có thể đổi state/chi phí
```

**JConsole không phải profiler toàn năng.** Nó có một số biểu đồ CPU/memory/threads/classes và khả năng nhìn stack thread, nhưng không tự thu đầy đủ flamegraph, allocation stack, distributed traces, query latency hay lịch sử trước khi kết nối. Dùng JFR, GC logs, thread dumps, metrics và tracing khi câu hỏi cần dữ liệu sâu hoặc timeline dài.

### 1.1 Read-only hay quản lý?

Đọc số `HeapMemoryUsage`, `ThreadCount` hoặc `LoadedClassCount` thường là **monitoring**. Ngược lại:

- Ghi một MBean attribute **writable** sẽ gọi setter ở JVM đích.
- Bấm button **operation** có thể gọi method của MBean ở JVM đích.
- `Perform GC` trong tab Memory yêu cầu JVM thực hiện garbage collection.
- Một số operations như `dumpHeap` có thể gây pause, I/O lớn và tạo file chứa dữ liệu nhạy cảm.
- Việc bật verbose class loading/GC hoặc thay cấu hình logging có thể tăng lượng log/overhead.

**Quyền xem JMX không đồng nghĩa quyền thao tác.** Với production, chính sách nên mặc định read-only; phân quyền quản trị riêng cho các thao tác đã được duyệt, và ghi audit khi có thay đổi.

## 2. Chuẩn bị trước khi kết nối

### 2.1 JConsole nằm ở đâu?

Trên bản JDK có chứa công cụ này, executable thường nằm ở:

```text
<JDK_HOME>/bin/jconsole
```

Mở terminal:

```bash
jconsole
```

Đây là lệnh mở **giao diện đồ họa**, không phải lệnh in metrics ra stdout. Cần hệ thống có môi trường hiển thị GUI; container tối giản, server headless và Java runtime tạo bằng `jlink` có thể không đóng gói `jconsole`. Dùng JDK với GUI trên máy quản trị được phép thay vì cài thêm desktop vào production container chỉ để xem biểu đồ.

Theo tài liệu JDK 21, JConsole có thể kết nối local/remote. Với local application và PID đã biết:

```bash
jconsole 12345
```

**12345 là PID giả định.** Thay bằng PID đã xác nhận của process cần xem. Chạy JConsole và target JVM với quyền user phù hợp. Trong môi trường HotSpot có khả năng attach, JConsole có thể bật management agent khi kết nối local nếu trước đó chưa bật; nhưng điều này **không được bảo đảm** nếu JVM tắt attach, policy chặn, namespace/container khác hoặc công cụ/JDK không tương thích.

### 2.2 Chọn đúng Java process

Trước khi chọn một dòng trong Local Process, xác nhận:

1. Tên service/application, host và container/pod hoặc session.
2. PID cùng **process start time**, vì PID có thể tái sử dụng sau restart.
3. JDK/runtime version và instance nhận request lỗi; không gán thông tin replica khác cho replica đang hỏng.
4. JVM hiện hữu và quyền attach/JMX; một máy có thể chạy nhiều `java`/`javaw`.
5. Môi trường GUI và hệ thống đích tương thích, cùng chính sách giám sát được phép.

Trên Linux, có thể dùng OS process metadata đã được cấp quyền:

```bash
ps -p 12345 -o pid,lstart,etime,comm,args
```

Lệnh này có thể hiện **arguments chứa secret**; xem trong terminal đáng tin và chỉ lưu phần đã xử lý. `jps`/`jcmd -l` cũng hữu ích khi được hỗ trợ, nhưng có thể không liệt kê JVM trong container namespace riêng.

Trong JConsole, sau khi kết nối, xem **VM Summary** để đối chiếu runtime version/uptime và JVM arguments; đừng vội giải thích biểu đồ khi chưa chắc chọn đúng target.

### 2.3 Local và remote khác nhau

| Kiểu | Cách kết nối thường dùng | Điều kiện và giới hạn |
| --- | --- | --- |
| **Local** | Chạy `jconsole`, chọn Local Process hoặc `jconsole <PID>` | Cùng máy, quyền user, attach và namespace phù hợp; có thể không hoạt động trên JVM không attachable |
| **Remote host:port** | `jconsole host.example:9010` hoặc nhập host/port trong GUI | Target phải cung cấp JMX remote connector; có vấn đề TLS, authentication, authorization, network/firewall/RMI |
| **JMX Service URL** | Chọn Remote/Advanced connection theo giao diện và nhập URL | Dành cho connector riêng hoặc khi cần URL đầy đủ; syntax phụ thuộc connector |
| **Qua vùng mạng giới hạn** | Kết nối trong mạng quản trị/VPN/tunnel được phê duyệt | Không biến JMX thành public endpoint; remote network topology/RMI ports phải đúng |

Đối với Remote JMX dùng RMI trong HotSpot, cần phân biệt **RMI registry port** với **RMI connector/server port**, và đôi khi cấu hình `java.rmi.server.hostname` để stub trả địa chỉ client truy cập được. Một host:port đúng mà kết nối đứng ở “Connecting...” có thể do cổng thứ hai hoặc địa chỉ trong RMI stub không truy cập được; không tự tắt TLS/authentication để “sửa nhanh”.

JDK 21 mô tả các system properties như `com.sun.management.jmxremote.port`, `com.sun.management.jmxremote.rmi.port` và `java.rmi.server.hostname`. Chúng được cấu hình theo chính sách vận hành/triển khai; **không tự mở JMX remote trên production chỉ vì muốn dùng JConsole**.

### 2.4 Bảo mật kết nối JMX remote

JMX remote là **mặt phẳng quản trị ứng dụng**, không phải một port metrics đơn giản. Khi được phép triển khai:

- Giới hạn truy cập ở network/firewall/VPN/bastion và port RMI cần thiết; không expose trực tiếp ra Internet.
- Dùng TLS/SSL được cấu hình và xác thực server/khách theo chính sách, credentials và authorization rõ ràng.
- Áp dụng quyền tối thiểu: tài khoản `readonly` để quan sát; quyền ghi/invoke operations chỉ cho người hoặc hệ thống được phép.
- Không dùng cấu hình bỏ xác thực và TLS (`authenticate=false`, `ssl=false`) cho môi trường production.
- Không lưu password ở command history, ticket, ảnh chụp màn hình hoặc URL được chia sẻ; khóa/secret cần được quản lý đúng chính sách.
- Kiểm tra bảo vệ RMI registry, file password/access permission và tính tương thích với môi trường container/NAT.
- Không cho rằng vì đang mở được GUI thì mọi thao tác MBean đều an toàn; **giấy phép truy cập và giấy phép thay đổi** là hai quyết định khác nhau.

JConsole/management agent cũng có overhead và có thể ảnh hưởng JVM, nhất là khi polling dữ liệu nặng. Oracle khuyên thận trọng với JConsole local trên production; thường sử dụng một JConsole client riêng qua remote connection được bảo vệ nếu việc chẩn đoán yêu cầu.

## 3. Sáu tab chuẩn: đọc được gì?

Giao diện JConsole JDK 21 thường có **sáu tab**:

| Tab | Dữ liệu chính | Vấn đề thường khoanh vùng |
| --- | --- | --- |
| **Overview** | Đồ thị CPU, memory, thread count, loaded classes | So sánh biến động tài nguyên theo cùng một khoảng thời gian |
| **Memory** | Heap/non-heap, memory pools, used/committed/max, GC count/time | Heap pressure, GC activity, vùng bộ nhớ tăng |
| **Threads** | Live/peak threads, tên/trạng thái/stack của thread, deadlock detection | Request kẹt, block/lock contention, thread tăng |
| **Classes** | Current loaded, total loaded, unloaded classes | Class loading churn, nghi classloader retention |
| **VM Summary** | VM/runtime facts, uptime, CPU time, flags/args, GC và OS tóm tắt | Xác nhận target JVM và ngữ cảnh thực thi |
| **MBeans** | ObjectName, attributes, operations, notifications của platform/custom MBeans | Đọc trường chi tiết, xem domain-specific counters, quản trị có kiểm soát |

Tất cả đều là **cách nhìn vào cùng JVM**, nhưng các getter và biểu đồ có thể lấy dữ liệu tại những thời điểm khác nhau. Không giả định mọi số cùng một hàng là “atomic transaction snapshot”.

## 4. Overview: đọc biểu đồ tổng quan

Tab **Overview** hiển thị các biểu đồ CPU, memory, threads và loaded classes trên một màn hình. Đây là nơi hữu ích để trả lời: “Khoảng thời gian latency tăng có trùng với tăng heap, thread count hoặc class loading không?”.

### 4.1 Các đồ thị trả lời câu hỏi gì?

- **CPU:** đại diện cho CPU consumption theo số liệu OS/MXBean mà JConsole có thể cung cấp; không tự chỉ ra method nào dùng CPU. Với nhiều cores, tỷ lệ hiển thị cần hiểu theo định nghĩa của VM/JMX implementation.
- **Memory:** thể hiện memory usage theo thời gian, thường gắn heap; biểu đồ không đủ chứng minh retained-object leak.
- **Threads:** số platform/live threads quan sát được; tăng lên có thể do pool mở rộng, workload, blocked requests hoặc tạo thread ngoài kiểm soát.
- **Classes:** số class đã load hiện tại; tăng trong warm-up bình thường, tăng liên tục qua redeploy/plugin reload có thể cần kiểm tra classloader lifecycle.

Một **cùng thời điểm spike** trên hai chart là **correlation**, chưa chứng minh causal chain. Ví dụ CPU tăng cùng heap used có thể do request throughput, allocation churn hoặc GC; cần thêm CPU samples/JFR/GC events, request metrics và traces.

### 4.2 Time Range và dữ liệu lịch sử

JConsole hiển thị dữ liệu khi nó giám sát JVM và theo bộ đệm/biểu đồ của phiên GUI; thay đổi menu **Time Range** không làm JConsole tự lấy được lịch sử trước khi kết nối nếu không có hệ thống recording riêng. Nếu bạn vừa mở JConsole sau khi incident đã kết thúc, thấy biểu đồ phẳng **không chứng minh** hệ thống không từng có spike.

Khi chọn time range:

1. Chọn khoảng đủ rộng để thấy baseline, incident và recovery.
2. Kiểm tra độ phân giải/số mẫu. Spike kéo dài 1 giây có thể không nhìn thấy nếu chu kỳ cập nhật lớn.
3. So cùng khoảng thời gian trên Overview và tab chi tiết.
4. Ghi thời điểm UTC và thời gian JVM đã chạy; tránh ghép hai process trước/sau restart như một chuỗi liên tục.

### 4.3 Lưu biểu đồ CSV

Tài liệu JDK 21 mô tả thao tác **right-click chart → Save data as...** để xuất dữ liệu biểu đồ ra **CSV**. File CSV được lưu trên **máy đang chạy JConsole**, không mặc nhiên trên máy chủ JVM remote. Sau khi xuất, cần kiểm tra timestamp/timezone, tên cột, units, khoảng quan sát và số mẫu.

CSV là ảnh dữ liệu mà JConsole thực sự có trong bộ đệm cho chart đó, không phải sự thật toàn bộ vòng đời JVM. Nếu muốn giám sát nhiều ngày, hệ thống metrics có retention/chính sách alert là nguồn thích hợp hơn; JConsole phù hợp điều tra tương tác và kiểm tra trực tiếp.

## 5. Memory: biểu đồ heap, non-heap và memory pools

Tab **Memory** cho phép chọn scope trong danh sách chart: total heap, non-heap và các **memory pools** mà JVM đó công bố. Số lượng/tên pools phụ thuộc implementation và GC. Trên một HotSpot JDK 21, có thể gặp Metaspace, Code Cache và các G1/ZGC pools; không lấy tài liệu hình ảnh JDK đời cũ có “Permanent Generation” làm bằng chứng rằng PermGen tồn tại trên JDK 21.

### 5.1 Ba giá trị quan trọng

| Giá trị | Nghĩa | Không được hiểu là |
| --- | --- | --- |
| **Used** | Số byte bộ nhớ hiện được vùng Java quản lý sử dụng; có thể gồm object chưa GC dù đã unreachable | “Retained/live objects chắc chắn”, “RSS của tiến trình” |
| **Committed** | Memory JVM đã đảm bảo sẵn cho vùng được đo | RAM vật lý resident hoặc current used |
| **Max** | Giới hạn tối đa nếu JVM có thể công bố; có thể undefined | Memory đã cấp hoặc giới hạn duy nhất của toàn container |

Nếu đi vào MBeans và đọc `java.lang:type=Memory`, attribute `HeapMemoryUsage` trả một composite gồm `init`, `used`, `committed`, `max` theo Java Management API. `-1` của `max` là “không xác định”, **không phải 0 hoặc không giới hạn**.

**Ví dụ số học minh họa** (không phải output từ một JVM):

```text
heap.used      = 300 MiB
heap.committed = 600 MiB
heap.max       = 1.200 MiB

used / committed = 50%
used / max       = 25%
```

Dashboard ghi “heap sử dụng 50%” mà không nói mẫu số là committed hay max có thể gây hiểu nhầm. Cùng một snapshot nhưng câu hỏi khác nhau.

### 5.2 Cách đọc đường heap used

Thông thường heap used tăng khi cấp phát object và giảm sau một số GC event; biểu đồ hình răng cưa có thể là bình thường. Đừng kết luận leak khi chưa có chuỗi **sau GC** dưới workload tương đương, allocation/retention evidence hoặc heap analysis phù hợp. Heap used không thể quy đổi trực tiếp thành RSS: native memory, thread stacks, direct buffers, mappings, code cache và nhiều vùng khác còn ảnh hưởng footprint.

Để so GC với latency:

1. Xác định incident time window.
2. Ghi heap used/committed/max ở thời điểm có liên quan.
3. Xem GC count/time trong Memory cùng GC logs/JFR để biết tần suất và pause.
4. Đối chiếu throughput, allocation rate, request latency, container memory.
5. Khi cần retained objects, chỉ dùng heap dump/histogram sau khi cân nhắc overhead, dung lượng và bí mật.

GC time từ Management API thường là **số tích lũy** theo collector từ lúc JVM khởi động, không phải duration của đúng request đang xem; muốn tính rate/delta cần có hai snapshot và khoảng thời gian phù hợp.

### 5.3 Nút Perform GC là thao tác, không phải “xem thêm”

JConsole có nút **Perform GC** trong Memory tab. Bấm nút này yêu cầu JVM thực hiện garbage collection; nó **có thể ảnh hưởng latency/throughput** và làm thay đổi chính tình trạng đang điều tra. Tùy GC/VM flags, JVM có thể xử lý yêu cầu theo chính sách riêng; không nên dùng GC thủ công như phương pháp lấy baseline chuẩn.

Vì vậy:

- Trong production incident, **không bấm Perform GC** chỉ vì muốn xem đồ thị “sau khi sạch”.
- Không dùng giảm used sau forced GC để khẳng định không có leak.
- Nếu thực sự cần thử trên môi trường lab, ghi thời điểm bấm và đánh dấu đây là can thiệp, không còn chỉ là quan sát.
- Đừng giả định JConsole sẽ hỏi xác nhận với tất cả operations; một số thao tác có thể được thực thi ngay.

## 6. Threads: số luồng, stack và Detect Deadlock

Tab **Threads** hiển thị số lượng thread live/peak theo thời gian và danh sách thread mà VM hỗ trợ quản lý. Khi chọn một thread, giao diện có thể hiện **tên, trạng thái và stack trace**.

### 6.1 Diễn giải thread state

| Trạng thái | Ý nghĩa khái quát | Điều cần kiểm tra thêm |
| --- | --- | --- |
| `RUNNABLE` | Thread đang hoặc sẵn sàng thực thi theo mô hình JVM | Không tự chứng minh CPU cao; cần CPU samples/OS counters |
| `BLOCKED` | Đang chờ monitor lock | Lock owner, các frame liên quan, thời lượng kẹt |
| `WAITING` | Chờ không đặt timeout, có thể vì queue, condition hoặc join | Có thể là trạng thái bình thường của worker |
| `TIMED_WAITING` | Chờ có timeout (sleep, wait, park...) | Kiểm tra nhiệm vụ và timeout |
| `NEW` / `TERMINATED` | Chưa start / đã kết thúc trong mô hình thread | Một snapshot danh sách active có thể không chứa các trạng thái này |

Một thread `WAITING` có thể đang khỏe mạnh và chờ công việc. Một thread `RUNNABLE` không mặc nhiên là CPU hotspot. Để chẩn đoán request treo, nên lấy **nhiều snapshot cách nhau hợp lý** và liên hệ với thread pool queue, lock metrics, request trace và JFR.

### 6.2 Detect Deadlock

Trong tab Threads, **Detect Deadlock** gửi yêu cầu phát hiện deadlock mà JVM hỗ trợ, rồi hiển thị các chu trình tìm thấy (nếu có). Theo JDK 21, công cụ có thể tìm deadlock trên **object monitors** và các ownable synchronizers thuộc `java.util.concurrent` do JVM hỗ trợ.

Giới hạn:

- Không phải mọi sự cố chờ đều là deadlock theo mô hình công cụ. Thread có thể bị kẹt do network I/O, database lock ở hệ thống ngoài, queue starvation hoặc chờ tín hiệu không tạo chu trình lock rõ.
- “No deadlock detected” chỉ nghĩa là **không phát hiện loại deadlock được hỗ trợ tại thời điểm đo**, không chứng minh ứng dụng không thể deadlock hoặc không đang treo.
- Nếu hỗ trợ và có quyền, `java.lang:type=Threading` trong MBeans còn cho biết các operations/attributes của `ThreadMXBean`. Một operation tra cứu lock/stack có thể tốn chi phí theo số lượng thread.

### 6.3 Java 21 virtual threads: giới hạn cực kỳ quan trọng

`ThreadMXBean` trong Java SE 21 **hỗ trợ platform threads, không quản lý/giám sát virtual threads theo cùng cách**. Vì JConsole tab Threads chủ yếu dựa vào nền tảng ThreadMXBean, không được dùng số thread trong tab đó để kết luận “ứng dụng có chính xác n virtual threads” hoặc “không có virtual thread nào bị block”.

Nếu dịch vụ sử dụng virtual threads, cần công cụ/recording phù hợp phiên bản JDK như JFR events, đặc biệt khi nghi pinning, blocking hay có nhiều virtual threads đang chờ. Đọc dữ liệu **theo phạm vi mà nguồn thực sự hỗ trợ**, không mở rộng kết luận.

### 6.4 Khi nào tab Threads hữu ích?

- Thread count tăng đều qua thời gian, nghi tạo threads không được giải phóng.
- Nhiều request kẹt ở cùng monitor/lock và có stack tương đồng.
- Thread pool starvation: nhiều worker đang block trên downstream, queue tăng.
- Cần kiểm tra deadlock theo Java monitor/ownable synchronizer.
- Muốn xem cấu trúc stack của một thread trước khi quyết định có cần thread dump/JFR sâu hơn.

JConsole không tự cung cấp một **CPU profile thống kê đầy đủ** của mọi method; khi cần hotspot, chọn profiler/JFR CPU sampling.

## 7. Classes: class loading và khả năng classloader leak

Tab **Classes** cho biết:

- **Current loaded:** số class hiện được JVM giữ đã load.
- **Total loaded:** số class đã từng load kể từ lúc VM bắt đầu, bao gồm class sau này unload.
- **Total unloaded:** số class đã unload kể từ lúc VM bắt đầu.

Biểu đồ thường phân biệt **total loaded** và **current loaded** theo thời gian. Tổng loaded là counter tích lũy nên hiếm khi giảm, ngay cả khi nhiều class được unload; current có thể lên xuống. Đừng nhầm total loaded tăng với “classloader leak”.

Trong môi trường plugin hot-reload, reflection/proxy, bytecode generation hoặc application server redeploy:

1. Quan sát current class count qua các chu kỳ có cùng workload.
2. Đối chiếu Metaspace pool, GC/class unloading events và lifecycle classloader.
3. Xem hoạt động redeploy/module/plugin mới diễn ra lúc nào.
4. Nếu current và Metaspace sau nhiều vòng vẫn tăng, đó mới là tín hiệu cần điều tra sâu, **chưa đủ để kết luận leak**.

JConsole có điều khiển **Verbose** để bật/tắt thông tin class loading trên một số VM. Đây là **hành động thay đổi trạng thái logging** của JVM, có thể tăng output và overhead; không bật chỉ vì đang quan sát. Việc số classes tăng trong warm-up có thể hoàn toàn bình thường.

## 8. VM Summary: biết mình đang xem JVM nào

Tab **VM Summary** cho biết ngữ cảnh mà các biểu đồ khác thiếu: runtime/VM version, uptime, process CPU time, classpath, library path, JVM input arguments, threads/classes/GC/OS summary (mức độ hiển thị phụ thuộc JVM).

Các mục hữu ích:

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| JVM/version/uptime | Xác nhận JVM đúng instance và đúng vòng đời process | Sau restart uptime reset; PID có thể đổi/tái sử dụng |
| VM arguments | Xem input arguments được VM báo cáo | Có thể chứa `-Dpassword`/token; không tương đương mọi app arguments |
| Heap/GC information | Đối chiếu với Memory tab | Số snapshot có thể khác vì lấy khác thời điểm |
| Threads/classes | Tóm tắt trạng thái | Không thay thế tab chi tiết |
| Process CPU time | Tổng CPU time đã tiêu thụ từ khi JVM khởi động | **Không phải** “mức dùng CPU hiện tại” nếu không tính delta/interval |
| Classpath/library path | Tìm đường dẫn artifact/dependencies | Có thể lộ cấu trúc filesystem, không mặc nhiên là đúng version code từ repo |
| OS information | Kiểm tra context CPU/RAM/OS | Không tự thay thế container limits/native process metrics |

JConsole có thể cho thấy các input arguments nhưng không tự đưa ra toàn bộ **effective VM flags** do ergonomics, container constraints hoặc runtime changes. Nếu cần phân biệt `-Xmx` explicit và `MaxHeapSize` hiện hành, đối chiếu `jcmd <PID> VM.command_line` và `VM.flags` khi được phép.

Những thông tin có thể nhạy cảm: command line, JVM properties, file paths, classpath. Trước khi chụp màn hình hoặc xuất CSV, xem lại dữ liệu; không công bố raw arguments chứa secrets.

## 9. MBeans: nơi xem thuộc tính, gọi thao tác và nhận thông báo

Đây là trọng tâm của khả năng **quản lý JVM**. Tab **MBeans** truy cập các MBean được đăng ký trong platform MBean server. Mỗi MBean thường có:

- **ObjectName:** tên định danh JMX gồm domain và key properties, ví dụ `java.lang:type=Memory` hoặc `demo.jmx:type=LabControl`.
- **Attributes:** các giá trị hoặc cấu hình; có thể **read-only**, **write-only**, hoặc **read-write**, phụ thuộc MBean.
- **Operations:** methods có thể gọi qua JMX; có thể chỉ tra cứu hoặc thay đổi trạng thái/thực hiện I/O.
- **Notifications:** events từ một số MBeans, có thể subscribe để nhận.
- **MBeanInfo/Descriptor:** metadata về tên, kiểu dữ liệu, parameter, mô tả và capabilities.

Tab này không chỉ chứa platform MXBeans; custom MBeans do ứng dụng/libraries đăng ký cũng có thể xuất hiện. MBean có thể biến mất hoặc xuất hiện mới khi ứng dụng thay đổi lifecycle.

### 9.1 Đọc ObjectName và cây MBeans

Một số ví dụ phổ biến trên Java 17+/21:

| ObjectName / mẫu | Vai trò |
| --- | --- |
| `java.lang:type=Memory` | Heap/non-heap usage, GC verbosity, memory notifications và liên quan |
| `java.lang:type=Threading` | Platform thread counts, CPU time/stack/lock operations theo hỗ trợ |
| `java.lang:type=ClassLoading` | Loaded/unloaded classes và verbose class loading |
| `java.lang:type=Runtime` | VM name/vendor/version, uptime, input arguments |
| `java.lang:type=OperatingSystem` | OS/process counters theo Java Management API |
| `java.lang:type=MemoryPool,name=...` | Current/peak/collection usage và thresholds theo pool |
| `java.lang:type=GarbageCollector,name=...` | Collection count/time và GC pools |
| `com.sun.management:type=HotSpotDiagnostic` | Diagnostics phụ thuộc HotSpot, gồm heap dump/VM options |
| `demo.jmx:type=LabControl` | Custom MBean của ví dụ thực hành bên dưới |

Các pattern có dấu `...` là **minh họa**: tên thực tế thuộc VM, collector và library của ứng dụng. Không giả định mọi MBean hoặc mọi operation đều tồn tại trên OpenJ9, HotSpot version khác, runtime image rút gọn hay custom MBean server.

JConsole nhóm cây theo ObjectName; key properties có thể ảnh hưởng cấu trúc cây, nên hãy dùng tên đầy đủ cùng domain để nhận diện, không chỉ vị trí hiển thị.

### 9.2 Attributes: đọc và ghi khác nhau như thế nào?

Chọn **MBeans → java.lang → type=Memory → Attributes → HeapMemoryUsage** (tên đường dẫn trực quan có thể khác chút theo GUI). Thuộc tính này là một composite có `init, used, committed, max`; mở chi tiết sẽ thấy dữ liệu JVM hiện tại. Với numeric attribute, JConsole có thể cho phép mở **chart** bằng thao tác nhấp đúp; dữ liệu được cập nhật khi công cụ polling.

Theo tài liệu JDK 21, **writable attributes** có thể hiển thị giá trị bằng màu xanh trong JConsole. Ví dụ thuộc tính `Verbose` của Memory/ClassLoading có thể được sửa từ GUI — nhưng điều đó **gọi setter trên MBean** và thay đổi JVM logging. Đừng coi “chỉ sửa một ô trong GUI” là thao tác vô hại.

Một attribute có các tính chất:

| Thuộc tính | Kiểu | Hành động |
| --- | --- | --- |
| `HeapMemoryUsage` | Dữ liệu tổng hợp read-only | Đọc và quan sát; không sửa |
| `ThreadCount` | Numeric read-only | Đọc/quan sát |
| `Verbose` | Boolean writable trên MBean hỗ trợ | Set giá trị và gây thay đổi tracing/logging |
| Custom `Counter` | Numeric getter trong demo | Đọc, có thể vẽ chart |
| Custom `Ready` | Boolean getter + setter trong demo | Đọc và thay đổi trạng thái demo |

**Không tự suy từ tên attribute “có vẻ vô hại” mà gọi setter trên production.** Chỉ khi MBean metadata cho biết writable và có quyền điều khiển, phải hiểu side effect từ contract của chính MBean.

### 9.3 Operations: button có thể gọi code thật

Trong cây MBean, chọn **Operations** để thấy methods được đăng ký. JConsole có thể hiển thị nút cho từng operation và các tham số; khi bấm, JMX **invoke method trong JVM đích**.

Phân biệt:

- Getter-like operation: có thể trả thông tin hiện tại nhưng vẫn có overhead.
- Mutation/maintenance: ví dụ `resetCounter`, `setVMOption`, bật tracing, clear cache; có thể ảnh hưởng business behavior.
- Heap dump: `com.sun.management:type=HotSpotDiagnostic` có `dumpHeap` trên HotSpot; gọi nó có thể tạo file lớn, pause và làm lộ dữ liệu trong heap.
- GC operation: tương đương yêu cầu JVM làm GC, không phải một thao tác đọc.
- Operation của custom MBean: **hợp đồng do ứng dụng tự định nghĩa**; JConsole không tự bảo đảm nó idempotent, nhanh, thread-safe hoặc an toàn.

MBean metadata có thể hiển thị operation “impact” như INFO/ACTION/ACTION_INFO/UNKNOWN, nhưng **không thay thế phân tích tác động thực tế** và policy. Một MBean có thể được viết sai metadata hoặc method bên trong có I/O/blocking; đừng bấm thử để “xem nó làm gì”.

### 9.4 Notifications: một kênh sự kiện từ MBeans

MBeans có thể phát JMX notifications. Trong tab MBeans, chọn nhánh **Notifications**, nhấn **Subscribe** nếu MBean hỗ trợ và bạn được phép. Đây là cơ chế nhận sự kiện trong phiên JConsole, không thay thế toàn bộ lịch sử alert hoặc message queue.

Ví dụ `MemoryMXBean` có thể phát notification khi JVM phát hiện **memory usage threshold** hoặc **collection usage threshold** bị vượt theo các pool hỗ trợ. Nếu threshold chưa được cấu hình, không có notification **không chứng minh** memory không từng tăng cao.

Lưu ý:

- Subscribe có thể giữ listener trong JMX session; kiểm tra lifecycle/unsubscribe khi cần.
- Notification count không phải số request lỗi hay số bytes đã cấp phát.
- Một callback/notification của MBean có thể đến theo thời điểm JVM phát hiện sự kiện, không phải timestamp chính xác của mọi allocation.
- Trong production, một hệ thống alert chuyên dụng có retention và policy phù hợp thường đáng tin hơn việc để cửa sổ JConsole mở liên tục.

## 10. Bảng phân loại thao tác: quan sát, quản lý nhẹ và thao tác rủi ro

| Hành động JConsole | Tính chất | Hướng xử lý |
| --- | --- | --- |
| Xem Overview, Memory, Threads, Classes | Chủ yếu đọc | Được phép khi có quyền monitoring; đánh giá polling overhead |
| Xem VM Summary | Đọc, có thể lộ args/paths | Chỉ chụp/chia sẻ bản đã redact |
| Xem attributes read-only | Đọc | Xác nhận scope/unit/timestamp và quyền |
| Vẽ chart của numeric attribute | Polling/đọc liên tục | Giới hạn tần suất và số đối tượng được đọc |
| Detect Deadlock | Gọi diagnostic để kiểm tra lock cycles | Chỉ dùng khi cần, tránh lặp quá dày |
| Subscribe notifications | Đăng ký listener | Hiểu lifecycle và ngữ nghĩa event |
| Ghi attribute `Verbose` | **Thay đổi cấu hình tracing** | Cần phê duyệt/rollback và kiểm tra chi phí log |
| Gọi custom operation `incrementCounter` của demo | Thay đổi state của **JVM lab** | Được dùng trong lab; không áp dụng lên production MBean không rõ contract |
| Perform GC | **Yêu cầu GC** | Không dùng tùy tiện trên production |
| `dumpHeap` hoặc operation phân tích nặng | **I/O/disk/memory lớn**, có thể pause | Cần kế hoạch tác động, dung lượng, quyền và bảo mật artifact |
| `setVMOption` hay operations điều khiển khác | **Đổi VM/app state** | Chỉ thực hiện theo quy trình change/incident được phê duyệt |

Một nguyên tắc vận hành có giá trị lâu dài: **mở tab để nhìn không đồng nghĩa đã được phép nhấn mọi button**. Thao tác JMX đi qua mạng nhưng chạy trong JVM đích; hậu quả có thể trực tiếp đến latency, throughput, logging, memory hoặc tính nhất quán ứng dụng.

## 11. Thực hành Java 17+: tạo MBean để đọc, ghi và gọi operation

Bài thực hành này dùng **một JVM lab riêng**, không yêu cầu remote JMX và không thực hiện thao tác vào ứng dụng thật. Ta tạo một **Standard MBean** tên `demo.jmx:type=LabControl` với:

- Attribute `Counter` (**read-only**): bắt đầu từ 0.
- Attribute `Ready` (**read-write**): bắt đầu là `true`, thay đổi chỉ ảnh hưởng biến demo.
- Operation `ping()` (**không thay đổi state**): trả `"pong"`.
- Operation `incrementCounter()` (**thay đổi state**): tăng bộ đếm và trả kết quả.
- Operation `resetCounter()` (**thay đổi state**): đưa bộ đếm về 0.

### 11.1 Code đầy đủ, biên dịch được

Tạo tệp **`JConsoleLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class JConsoleLab {

    // Nested public interface là giao diện quản lý chuẩn của MBean.
    public interface LabControlMBean {
        long getCounter();
        boolean isReady();
        void setReady(boolean ready);
        String ping();
        long incrementCounter();
        void resetCounter();
    }

    public static final class LabControl implements LabControlMBean {
        private final AtomicLong counter = new AtomicLong();
        private volatile boolean ready = true;

        @Override
        public long getCounter() {
            return counter.get();
        }

        @Override
        public boolean isReady() {
            return ready;
        }

        @Override
        public void setReady(boolean ready) {
            this.ready = ready;
        }

        @Override
        public String ping() {
            return "pong";
        }

        @Override
        public long incrementCounter() {
            return counter.incrementAndGet();
        }

        @Override
        public void resetCounter() {
            counter.set(0L);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("demo.jmx:type=LabControl");

        LabControl lab = new LabControl();
        server.registerMBean(
                new StandardMBean(lab, LabControlMBean.class), name);

        System.out.println("JConsoleLab READY");
        System.out.println("MBean=demo.jmx:type=LabControl");
        System.out.println("PID=" + ProcessHandle.current().pid());

        // Giữ process tồn tại để mở GUI JConsole ở terminal khác.
        Thread.sleep(120_000L);
        System.out.println("JConsoleLab DONE");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac JConsoleLab.java
java JConsoleLab
```

**Hai dòng stdout đầu tiên chính xác, bất kể hệ điều hành/JVM:**

```text
JConsoleLab READY
MBean=demo.jmx:type=LabControl
```

Dòng tiếp theo là `PID=<giá-trị-thực>`, phụ thuộc máy. Sau khoảng 120 giây chương trình in `JConsoleLab DONE` và thoát. Nếu chạy JConsole quá chậm, hãy khởi động lại **JVM lab**; không mặc định một PID đã kết thúc còn hợp lệ. Trên JDK 17+/21, `javac` thành công thường không in gì; đó không phải lỗi.

### 11.2 Tại sao dùng StandardMBean?

`LabControlMBean` là interface **public** khai báo contract JMX. Class `LabControl` implement contract đó. `StandardMBean` giúp đăng ký implementation theo interface xác định, tránh phải tự tạo metadata MBean phức tạp. Bean được đăng ký qua **platform MBeanServer** nên local JConsole có thể tìm thấy trong tab MBeans khi kết nối đúng process.

Chương trình dùng:

- `AtomicLong` để tăng/reset counter an toàn khi JMX client gọi đồng thời.
- `volatile boolean` để getter/setter của `Ready` thấy state mới giữa các threads; trong demo, đổi `Ready` **không tắt service, không pause worker và không điều khiển JVM runtime**.
- `Thread.sleep` chỉ để giữ JVM sống đủ lâu cho lab, không chứng minh rằng JMX sẽ block ứng dụng trong 120 giây.
- `ProcessHandle.current().pid()` để in PID của **chính JVM demo**, không lấy PID từ máy khác.

JConsole hoặc JMX có thể gọi getter thường xuyên để vẽ đồ thị; getter của custom MBean nên **nhanh, an toàn và không có side effects đáng kể**. Không nên đưa DB query đắt hoặc thao tác network blocking vào mỗi lần `getCounter()`.

### 11.3 Kết nối đúng JVM demo

Mở JConsole trong một terminal khác trên cùng máy, cùng user:

```bash
jconsole
```

Trong cửa sổ Local Process, chọn process `JConsoleLab` có PID trùng dòng in từ demo; hoặc:

```bash
# Thay 12345 bằng PID thật in trên terminal của JConsoleLab.
jconsole 12345
```

Trình tự thao tác trên GUI:

1. Kết nối JVM demo và mở **VM Summary**; xác minh uptime/process context.
2. Mở **Overview** để xem các biểu đồ; vì demo gần như idle, không kỳ vọng CPU cao hay memory tăng liên tục.
3. Mở **MBeans**, tìm domain `demo.jmx` và ObjectName `type=LabControl`.
4. Chọn **Attributes**: đọc `Counter = 0` và `Ready = true` trước khi dùng operations.
5. Thử nhấp đúp giá trị numeric `Counter` để xem chart (nếu GUI hỗ trợ kiểu/hiển thị đó).
6. Chọn **Operations → ping** và gọi; kết quả kỳ vọng là chuỗi `pong`.
7. Chọn **Operations → incrementCounter** và gọi một lần; giá trị trả về dự kiến **1**, attribute `Counter` sau refresh là **1**.
8. Gọi `incrementCounter` thêm lần nữa; giá trị trả về dự kiến **2**, attribute `Counter` sau refresh là **2**.
9. Thay `Ready` thành `false` ở **writable attribute** nếu GUI và quyền cho phép; đọc lại để xác minh state. Đây chỉ là flag của lab.
10. Gọi `resetCounter`; sau khi refresh, `Counter` trở lại **0**.
11. Không cần thử `Perform GC` hoặc `HotSpotDiagnostic.dumpHeap` để chứng minh custom MBean hoạt động.

Thứ tự hiển thị attributes/operations trên GUI có thể khác, và giá trị chart chỉ được cập nhật khi JConsole polling. Các kỳ vọng 0→1→2→0 chính xác **nếu chỉ một người đang thao tác vào JVM demo này** và không có client khác gọi operations xen vào.

### 11.4 Sự khác nhau giữa read-only, writable và operation

| Thành phần demo | Cơ chế | Tác động |
| --- | --- | --- |
| `getCounter()` | Getter → attribute `Counter` | Chỉ đọc atomic counter |
| `isReady()` | Boolean getter → attribute `Ready` | Chỉ đọc state |
| `setReady(boolean)` | Setter → ghi attribute `Ready` | Đổi state trong JVM demo |
| `ping()` | MBean operation | Trả `pong`; không đổi counter/state |
| `incrementCounter()` | MBean operation | **Tăng Counter** |
| `resetCounter()` | MBean operation | **Reset Counter** |

Việc gọi setter/operation qua JMX là **hành động thực**, không phải tương tác giả lập của JConsole. Trong hệ thống thật, custom MBean có thể cung cấp drain queue, rotate secret, clear cache, reload config hoặc shutdown service; không gọi khi chưa hiểu contract/ủy quyền.

### 11.5 Cách dừng lab an toàn

Nếu chưa đủ 120 giây, quay lại terminal chạy JVM lab và bấm Ctrl+C để dừng. JConsole có thể báo mất kết nối, đó là hành vi bình thường khi target process thoát. Nếu khởi động lại, JVM nhận **PID mới hoặc cùng PID đã được tái sử dụng**, và custom MBean/Counter quay lại trạng thái ban đầu.

Không kết luận JConsole “tự sửa counter” khi thấy từ 2 trở về 0 nếu thực tế bạn vừa kết nối vào **phiên JVM mới**.

## 12. Diễn giải ba tình huống thực tế

### 12.1 Memory chart tăng liên tục: leak hay workload?

Giả sử trong Overview/Memory bạn thấy heap used tăng 200→700 MiB trong 20 phút, max là 1 GiB. Đây là **dữ liệu minh họa**, chưa phải bằng chứng leak.

Các bước:

1. Kiểm tra cùng PID/uptime, time range và GC collector.
2. Nhìn chu kỳ GC: used có giảm sau GC không, đáy sau GC có tăng liên tục không?
3. Kiểm tra heap committed/max và container memory limits; đừng nhầm committed với used hoặc RSS.
4. Đối chiếu request mix, throughput, caches, batch jobs, JFR allocation/GC events.
5. Nếu nghi retained references, lên kế hoạch heap analysis/dump có ngân sách overhead và bảo vệ dữ liệu.
6. Không dùng **Perform GC** để chỉnh kết quả đo khi đang cố quan sát trạng thái tự nhiên.

Kết luận có thể là allocation churn bình thường, cache warm-up, giữ object lâu, classloader issue hoặc leak; JConsole **gợi hướng** chứ không tự chứng minh nguyên nhân.

### 12.2 Threads tăng và latency p99 cao

Khi Threads chart tăng, mở danh sách thread/stacks; tìm những worker đang chờ lock, downstream hoặc queue; dùng Detect Deadlock nếu có bằng chứng Java lock cycle.

Không kết luận ngay có deadlock vì thread count tăng. Có thể thread pool scale theo workload; các thread `WAITING` đang nhàn; p99 cao do DB/network timeout mà Java Deadlock Detection không thể biết. Thu một vài snapshot qua thời gian và nối với service metrics, thread pool queue, distributed traces.

Nếu JVM dùng **virtual threads**, nhớ ThreadMXBean của Java 21 không phản ánh đầy đủ chúng: JConsole Threads chart chỉ là một phần góc nhìn, không phải tổng mọi logical tasks.

### 12.3 Current classes và Metaspace tăng qua redeploy

Chọn Classes tab và Memory pool liên quan đến Metaspace:

1. Ghi current loaded, total loaded, total unloaded và Metaspace usage.
2. Đối chiếu thời điểm reload/deploy, plugin generation, GC/class unloading.
3. Khi total loaded tăng nhưng current ổn định, có thể do nhiều class đã unload.
4. Nếu current và Metaspace tiếp tục tăng qua nhiều chu kỳ tương tự, cần điều tra classloader retention hoặc dynamic code generation.
5. Không bật class loading verbose từ JConsole chỉ để “thử” trên production, vì nó có thể tăng logging và làm thay đổi overhead.

## 13. Sự cố kết nối JConsole: giải quyết theo nguyên nhân

| Triệu chứng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy JVM trong Local Process | Khác user, namespace/container, JVM không attachable, process đã thoát | Xác nhận PID/start time, quyền OS, JDK/attach policy |
| “Connection failed” khi dùng PID | Sai PID, JVM restart, permission hoặc attach disabled | Đối chiếu target, user và logs; không tự dùng quyền admin để vượt policy |
| Remote host:port mở được nhưng JConsole vẫn treo | RMI stub trả host/port khác, firewall/NAT, TLS/certificate | Kiểm tra connector/server port và hostname công bố, mạng quản trị |
| Bị từ chối xác thực | Wrong credentials/role, access file, TLS settings | Dùng cơ chế cấp quyền chính thức, không tắt auth/SSL |
| Tab MBeans không có custom MBean | Kết nối nhầm JVM, bean chưa register, khác MBeanServer, lỗi lifecycle | Xác nhận ObjectName và platform registration trong app |
| Attribute/operation báo permission denied | Vai trò read-only, access control hoặc MBean policy | Chỉ dùng quyền được phép; không tìm cách bypass |
| Chart không thay đổi | JVM idle, dữ liệu chưa refresh, series không supported, sai scope | Kiểm tra timestamps, thuộc tính raw và workload |
| Biểu đồ mất sau reconnect | JConsole session mới chỉ có samples từ phiên/đệm hiện có | Dùng metrics/recording được thiết kế có retention |
| GUI không mở | JDK không có `jconsole` hoặc không có display server | Dùng GUI client trên máy phù hợp, kết nối theo chính sách |

Một sự cố JMX remote **không nên được khắc phục bằng cách thêm `authenticate=false`/`ssl=false`** trên production. Hãy ưu tiên cấu hình chính xác TLS, phân quyền, RMI ports, hostname và mạng quản trị.

## 14. Overhead và giới hạn khi dùng JConsole

### 14.1 Polling có chi phí

JConsole lấy các getter định kỳ và vẽ biểu đồ; tùy số lượng attributes, độ phức tạp custom MBeans và đường mạng, nó có thể tăng CPU, heap allocations, safepoint/management activity hoặc network traffic. Một custom getter duyệt toàn bộ cache hàng triệu phần tử có thể đắt gấp nhiều lần platform getter đơn giản.

Khi thấy CPU tăng sau khi mở JConsole, không tự gán tăng này cho application workload. So baseline, xem operations đã gọi và thuộc tính nào đang được chart polling.

### 14.2 Không thay telemetry dài hạn

- Chỉ số Overview theo cửa sổ GUI không phải monitoring retention nhiều ngày.
- JConsole không tự cung cấp traces tương quan nhiều services.
- Chart CPU/Memory không thay thế CPU flamegraph, allocation profiler hoặc heap object graph.
- JVM memory không bao gồm toàn bộ native/process RSS.
- CSV từ một chart không phải snapshot nhất quán nguyên tử của mọi MBean.
- JMX read-only role không phải “không có overhead”; getter cũng có thể tính toán.
- JConsole version GUI và VM version có thể lệch; khi gặp thiếu operation, kiểm tra contract trên target VM.

### 14.3 Cân bằng giữa thao tác bằng GUI và automation

JConsole hữu ích trong **khám phá tương tác, thực hành và điều tra một process**. Để có monitoring liên tục/alert, thường dùng metrics/exporter hoặc hệ thống quan sát có retention. Khi cần chẩn đoán thời điểm sự cố trong production, JFR/thread dump/GC logs có thể phù hợp hơn tùy câu hỏi.

Không ghi giá trị “Observed at 10:00” từ JConsole rồi suy ra “đã như vậy trong 24 giờ trước”. Chỉ trình bày khoảng thực sự có dữ liệu.

## 15. Quy trình vận hành JConsole có kiểm soát

### Bước 1: Xác minh quyền và target

Ghi:

- Service và environment, host/node/container/pod.
- PID và process start time, Java version/vendor, ứng dụng/build.
- Người thực hiện, mục đích, incident/ticket, quyền role JMX.
- Có cho phép operations/attribute writes hay chỉ monitoring?

Nếu dùng remote connection, xác nhận secure network/TLS, RMI hostname/ports và authorization. Không publish credential trong ghi chú.

### Bước 2: Lấy bối cảnh từ VM Summary

Đọc uptime/version/arguments theo đúng PID và ghi timestamp UTC. Redact paths/tokens trước khi chia sẻ. Nếu nhận ra nhầm JVM, ngừng ngay; không tiếp tục đọc/ghi MBean của process khác.

### Bước 3: Quan sát Overview rồi vào tab theo triệu chứng

- Memory pressure → Memory; phân biệt heap/non-heap và pool, GC times, used/committed/max.
- Thread stall → Threads, nhiều snapshots và deadlock detection khi phù hợp.
- Classloader/metaspace → Classes + Memory pool.
- Application custom state → MBeans → ObjectName/Attributes, chỉ đọc trước.
- Cần liên hệ nhiều nhóm → Chọn cùng khoảng thời gian và lấy CSV/metrics khi được phép.

### Bước 4: Trước khi gọi setter/operation

Tự trả lời đủ:

1. Attribute/operation này **thay đổi điều gì trong JVM/app**?
2. Tài liệu/owner của MBean xác nhận side effects, concurrency và quyền nào?
3. Có thể gây pause, chạy GC, dump file lớn, clear cache, mất dữ liệu hoặc tăng log không?
4. Có điều kiện dừng, rollback và cách đo tác động sau thay đổi không?
5. Có phải production, nhiều replica, hay dữ liệu nhạy cảm không?
6. Có phê duyệt vận hành tương ứng không?

Nếu không trả lời được, **không gọi**. Xem MBean metadata và liên hệ owner thay vì bấm thử.

### Bước 5: Thu bằng chứng và thoát phiên

Lưu chart CSV/screenshot nếu chính sách cho phép, gắn timestamp, units, time range, PID/start time và mục tiêu. Không để GUI/remote JMX mở không kiểm soát; disconnect và quản lý phiên/credentials theo policy. Với recording/heap artifacts tạo từ operations, lưu/xóa theo retention và kiểm soát quyền.

### Bước 6: Kết luận có giới hạn

Ví dụ ghi nhận **minh họa**:

```yaml
captureTimeUtc: "2026-10-29T08:30:00Z"
service: "inventory-api"
instance: "inventory-2"
processId: 12345
jvmUptimeSeconds: 3600
connection: "secured remote JMX"
observations:
  heapUsedMiB: 300
  heapCommittedMiB: 600
  heapMaxMiB: 1200
  livePlatformThreads: 64
  loadedClasses: 8600
  deadlockDetection: "no supported deadlock detected at capture"
actions:
  - "read Overview/Memory/Threads/VM Summary"
  - "read MBean attributes"
mutationsPerformed: false
limitations:
  - "No JFR CPU profile"
  - "Data available only during observed time window"
```

Các số và tên trong mẫu là **giả định**. Chỉ điền values đã quan sát thật và không tự chèn thông tin nhạy cảm. `deadlockDetection` ghi cụ thể phạm vi “theo hỗ trợ và tại thời điểm đo”, không ghi khẳng định toàn bộ chương trình không bao giờ deadlock.

## 16. Những lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “JConsole chỉ để xem, bấm mọi nút đều vô hại.” | Writable attributes/operations thực thi ngay trong target JVM. |
| “Có thể luôn attach local JVM mà không cần cấu hình.” | Còn phụ thuộc user/permissions, namespace, attach policy, runtime và platform. |
| “Bật JMX remote chỉ cần mở một cổng.” | RMI có registry, connector port, stub hostname, firewall và TLS/auth concerns. |
| “Bỏ xác thực JMX để dễ chẩn đoán production.” | Rủi ro truy cập trái phép/mutation; phải giữ security và phân quyền. |
| “CPU chart đã cho thấy class/method gây chậm.” | Cần profiler/JFR CPU samples và workload context. |
| “Memory used tăng là leak.” | Có thể do allocation churn, cache/warm-up, GC policy; cần chuỗi sau-GC và retained references. |
| “Committed heap bằng RSS.” | Heap committed khác physical resident/process memory. |
| “Perform GC chỉ cập nhật biểu đồ.” | Gửi yêu cầu garbage collection và có thể làm thay đổi trạng thái/latency. |
| “ThreadCount của Java 21 bao gồm mọi virtual thread.” | `ThreadMXBean` chỉ giám sát platform threads theo contract JDK 21. |
| “Detect Deadlock không tìm thấy nghĩa là không có chờ/kẹt.” | Chỉ kiểm tra những loại deadlock hỗ trợ tại thời điểm đó. |
| “Total loaded classes tăng luôn là classloader leak.” | Total loaded là số tích lũy; cần current, unloaded, Metaspace và bối cảnh. |
| “MBean attribute writable chỉ là một ô trên GUI.” | Ghi value gọi setter trong process. |
| “MBean operation có tên `ping` nên chắc chắn không tác động.” | Với custom MBeans, phải đọc contract/code của owner; tên không bảo đảm side effect. |
| “Chart xuất CSV bao gồm dữ liệu từ trước khi JConsole mở.” | CSV chỉ xuất dữ liệu chart có trong phiên/bộ đệm. |
| “Có thể dùng một JVM demo để suy ra JVM production.” | Luôn lấy dữ liệu từ đúng PID/instance/runtime đang cần chẩn đoán. |
| “JConsole luôn hiển thị các memory pool theo hình cũ có Permanent Generation.” | Tên pools thay đổi theo GC/JDK; Java 17/21 không dùng PermGen theo cách Java 7 trước đây. |
| “Một role đọc JMX hoàn toàn miễn chi phí.” | Getter/polling có thể tốn tài nguyên, đặc biệt custom MBean không tối ưu. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Mở JConsole kết nối JVM và thấy CPU cùng heap used tăng. Có đủ kết luận memory leak gây CPU cao?

**Đáp án:** chưa. Đó là tương quan theo thời gian, cần GC/CPU sampling, allocation, workload và retained-object evidence. Hai chart không cho thấy causal chain.

**Câu 2.** Trong MBeans thấy `HeapMemoryUsage` gồm `used=300`, `committed=600`, `max=1200` MiB. Used/max và used/committed là bao nhiêu?

**Đáp án:** **25%** và **50%**. Hai tỷ lệ nói đến hai loại capacity khác nhau; không đổi tên mà không đổi mẫu số.

**Câu 3.** Người quan sát muốn “làm sạch heap trước khi nhìn chart” bằng `Perform GC`. Có coi là read-only được không?

**Đáp án:** không. Nó yêu cầu GC, có thể ảnh hưởng dịch vụ và thay đổi trạng thái đang đo. Trong môi trường thật cần quy trình phê duyệt can thiệp.

**Câu 4.** Trong demo `Counter` đọc bằng attribute, `incrementCounter()` gọi bằng operation, `Ready` được sửa bằng setter. Ba việc khác nhau thế nào?

**Đáp án:** đọc `Counter` không đổi state; `incrementCounter` tăng state; ghi `Ready` gọi setter và đổi flag trong process demo. Hai thao tác sau là mutation.

**Câu 5.** `Detect Deadlock` không phát hiện gì nhưng request vẫn bị treo. Có mâu thuẫn không?

**Đáp án:** không. Có thể do I/O, starvation, database lock bên ngoài hoặc loại chờ không tạo deadlock cycle mà JConsole kiểm tra được.

**Câu 6.** Một ứng dụng Java 21 tạo 100.000 virtual threads, nhưng Threads tab không báo con số đó. Vì sao?

**Đáp án:** JDK 21 `ThreadMXBean` không giám sát virtual threads theo cách tương tự platform threads. Cần JFR/công cụ phù hợp virtual threads để đánh giá.

**Câu 7.** Một JMX remote connection cần login, nhưng người vận hành muốn bật `authenticate=false` và `ssl=false` để truy cập từ laptop. Có nên không?

**Đáp án:** không trên production. JMX có operations và writable state, cần authentication, TLS, role/network restrictions. Sửa credential/RMI/SSL đúng cách.

**Câu 8.** JConsole đang vẽ `Counter` của demo, gọi `incrementCounter` hai lần. Chart không đổi ngay lập tức. Có chứng minh operation thất bại?

**Đáp án:** chưa. Polling interval, refresh và selected attribute có thể khiến chart chậm cập nhật. Xác minh kết quả operation và đọc lại raw `Counter`.

**Câu 9.** Tại sao VM Summary không được xem là bằng chứng chắc chắn về toàn bộ effective flags và parameters của app?

**Đáp án:** VM input args khác với application args và những VM flags mà JVM tự chọn/điều chỉnh; có thể cần `jcmd`/JVM APIs, deployment config và runtime state.

**Câu 10.** Một custom MBean có operation `clearCache`. Khi nào được gọi?

**Đáp án:** chỉ khi hiểu contract/side effect, phạm vi ảnh hưởng, concurrency/rollback và có quyền vận hành phù hợp. Không bấm thử chỉ để xem GUI có hoạt động không.

## 18. Checklist thực hành cuối bài

- Xác định đúng **JVM/PID/start time**, Java version và quyền kết nối.
- Local attach đúng user/namespace; remote JMX có TLS, authentication, authorization và mạng giới hạn.
- Biết sáu tab: **Overview, Memory, Threads, Classes, VM Summary, MBeans**.
- Phân biệt **used/committed/max**, current/peak threads, loaded/current classes và cumulative metrics.
- Không nhầm JConsole charts với profiler hoặc hệ thống lưu lịch sử dài hạn.
- Trong MBeans, nhận diện **ObjectName**, **attribute read-only/writable**, **operation**, **notification** và metadata.
- Mọi writable attribute, GC action, heap dump hay custom operation được xem là **change** cho đến khi biết chắc side effects.
- Chạy được ví dụ `JConsoleLab.java`, tìm `demo.jmx:type=LabControl`, đọc `Counter`/`Ready`, gọi `ping`/`incrementCounter`/`resetCounter`.
- Ghi timestamp, scope, units, source, window và giới hạn phép đo; bảo vệ dữ liệu trước khi xuất screenshot/CSV.
- Dùng JFR, GC logs, thread dumps, metrics/tracing khi cần độ sâu hoặc timeline mà JConsole không cung cấp.

**Kết luận:** JConsole giúp “nhìn JVM bằng mắt” thông qua đồ thị và MBeans, nhưng nó đồng thời là một **công cụ điều khiển** có thể ảnh hưởng trực tiếp đến ứng dụng. Quy trình an toàn là **xác nhận đúng process → quan sát trước → hiểu hợp đồng MBean → chỉ thực hiện thao tác được phép → kiểm tra tác động và lưu bằng chứng có ngữ cảnh**.

### Tài liệu tham khảo chính thức

- [Oracle JDK 21 — Using JConsole](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html): cách mở JConsole, local/remote, sáu tab, chart CSV, attributes, operations và notifications.
- [Oracle JDK 21 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html): management agent, remote RMI ports/hostname, authentication, TLS và role access.
- [Oracle JDK 21 — The jconsole Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html): launcher command, `-J` options và cách khởi chạy.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): quản lý platform threads và giới hạn virtual threads.
- [Java SE 21 — MBeanServer](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html): register/query/read/set/invoke MBeans trong server.
- [Java SE 21 — StandardMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html): đăng ký Standard MBean thông qua management interface.
- [Java SE 21 — MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): semantics của init/used/committed/max.
