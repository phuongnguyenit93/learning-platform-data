# 18.8 Phạm vi JVM quan sát được và bằng chứng cần lấy thêm từ hệ điều hành hoặc dịch vụ ngoài

## Mục tiêu học tập

Một request Java chậm 800 ms chưa chắc JVM đã thực hiện 800 ms công việc. Một event jdk.SocketRead kéo dài 400 ms chưa chắc mạng truyền dữ liệu mất 400 ms. Một thao tác FileWrite trở về thành công chưa chứng minh dữ liệu đã được ghi bền vững xuống đĩa. Ngược lại, không thấy event I/O trong JFR cũng **không** chứng minh ứng dụng không chờ I/O.

Bài này xác lập **ranh giới quan sát (observability boundary)** giữa JVM, hệ điều hành, mạng/lưu trữ và dịch vụ bên ngoài. Mục tiêu là biết điều gì có thể kết luận trực tiếp từ dữ liệu của JVM, điều gì chỉ là giả thuyết và cần thu thêm bằng chứng ở đâu, đặc biệt trong các ca điều tra **I/O và độ trễ**.

Sau bài này, bạn có thể:

1. Phân biệt Java/JVM I/O events, application spans, OS/kernel counters, network measurements và server-side telemetry.
2. Giải thích vì sao socket read/write duration, file I/O duration, thread states và CPU metrics không tương đương network RTT, disk latency hoặc thời gian xử lý của database.
3. Nhận diện những điểm mù do NIO/asynchronous I/O, connection pool, DNS, TLS, proxy, retry, kernel buffers, storage cache, cgroup và JFR threshold.
4. Thu thập bằng chứng từ Linux/containers và từ dịch vụ phụ thuộc một cách có mục tiêu, an toàn, có timestamp.
5. Ghép timeline theo trace/request ID và kiểm tra giả thuyết cạnh tranh trước khi kết luận nguyên nhân.
6. Viết hồ sơ điều tra có giới hạn quan sát rõ ràng thay vì chỉ nói chung “I/O chậm”.

Phạm vi ví dụ: Java 17+ trên HotSpot/OpenJDK, Java Flight Recorder (JFR) và Java Mission Control (JMC), Linux/cgroup v2 cùng các hệ thống có HTTP/gRPC, database hoặc storage. Khả năng quan sát cụ thể phụ thuộc JVM vendor/version, hệ điều hành, container runtime, network stack, thư viện ứng dụng và event settings. Các lệnh Linux là **công cụ điều tra có điều kiện**, không phải mọi môi trường đều cài sẵn hay cho quyền chạy.

## 1. Một request đi qua nhiều miền trách nhiệm

Giả sử service Java nhận yêu cầu, lấy dữ liệu từ database rồi trả về HTTP response:

~~~text
Client
  |
  | Internet / DNS / TLS
  v
Ingress / Load Balancer / Reverse Proxy
  |
  | Route, queue, retries, connection
  v
Java service
  |-- HTTP server accept / parse / dispatch
  |-- Executor queue / connection pool wait
  |-- Java business code
  |-- JDBC / HTTP client / TLS / socket I/O
  |        |
  |        v
  |    OS kernel / TCP / network / proxy
  |        |
  |        v
  |    Database / remote service / storage
  |        |
  |        v
  |    Remote CPU, locks, disk, cache, queue
  |-- Response encoding / socket write
  v
Proxy / network / end user
~~~

Có ít nhất **bốn góc nhìn**:

- **Application/JVM:** method calls, Java thread stacks, Java-visible I/O operations, GC/JIT, heap, instrumented client/server spans.
- **OS/kernel/container:** CPU scheduling, run queue, TCP state/retransmission/RTT estimates, socket buffers, file descriptors, process I/O counters, block-device queues, cgroup limits và pressure stalls.
- **Hạ tầng trung gian:** DNS resolver, service mesh, load balancer, TLS termination, sidecar proxy, NAT, packet loss, rate limiting và network policy.
- **Remote dependency:** connection queue, server thread pool, query execution/locks, storage IOPS, downstream retries, throttling và ứng dụng khác.

Một hiện tượng thường **được quan sát từ nhiều miền**, nhưng chỉ một số nguồn đủ gần cơ chế để xác định tại sao nó xảy ra. JFR có thể phát hiện thread Java chờ ở socket; muốn biết đó là **đợi database chạy truy vấn**, **packet loss** hay **upstream queue**, cần số liệu của miền bên ngoài.

**Nguyên tắc gốc:** “Nơi tôi quan sát thấy chờ” không tự động là “nơi đã tạo ra sự chậm trễ”.

## 2. Những gì JVM có thể quan sát trực tiếp

### 2.1. JFR events về socket và file I/O

Các tên event JFR thường dùng trên HotSpot:

| Event | Nhìn thấy gì khi được bật/ghi | Không tự chứng minh điều gì |
| --- | --- | --- |
| jdk.SocketRead | Thời lượng thao tác socket read được instrument, endpoint/address/port, bytes và thread/stack khi có | Network RTT, server processing time, mọi packet, mọi async read |
| jdk.SocketWrite | Thời lượng thao tác socket write được instrument và số byte ghi theo semantics của event | Dữ liệu đã đến/được ACK ở phía đích, remote service đã xử lý |
| jdk.FileRead | Thời lượng thao tác file read Java-visible, path/bytes khi có | Mỗi byte đều đọc đĩa vật lý, device service time chính xác |
| jdk.FileWrite | Thời lượng thao tác file write Java-visible | Dữ liệu đã được fsync hoặc lưu bền vững, độ trễ flush thực trên thiết bị |
| jdk.JavaMonitorEnter / jdk.ThreadPark | Một số tình huống monitor contention / park trong JVM nếu recording chứa event | Mọi hình thức queue, mọi thời gian chờ OS/scheduler hoặc network |
| jdk.CPULoad / jdk.ThreadCPULoad | Tín hiệu sử dụng CPU theo JVM/thread trong các khoảng thu | CPU throttling, mọi nguyên nhân chờ I/O, packet loss |
| jdk.GarbageCollection và GC phases | Hoạt động GC trong JVM, giúp đối chiếu pause/pressure với request | Mọi khoảng latency đều do GC hoặc mọi I/O event là lỗi network |

**Các event phải được bật và vượt điều kiện ghi**: threshold, period, stackTrace, duration, recording window và dữ liệu còn giữ. Những event I/O ngắn có thể không xuất hiện nếu threshold khác 0. Mức threshold “mặc định” có thể khác cấu hình .jfc, JDK và view; **đọc cấu hình đang dùng**, đừng hard-code một ngưỡng cho mọi môi trường.

Với SocketRead, một event dài có thể đại diện phần thời gian thread **đang chờ dữ liệu xuất hiện** ở phía nhận. Khoảng đó có thể bao gồm server xử lý truy vấn, thời gian truyền, wait trong kernel và scheduling; không đủ để tách từng thành phần.

Với SocketWrite, việc write trả về thường chỉ nói vùng dữ liệu đã được **chấp nhận ở tầng I/O tương ứng**; kernel có thể buffer, TLS/client library có thể xử lý thêm, network chưa chắc đã giao tới remote application. Một write nhanh không chứng minh response end-to-end nhanh.

### 2.2. Thread dump, stack và JVM runtime metrics

Dữ liệu JVM còn hỗ trợ:
- Java thread state (RUNNABLE/BLOCKED/WAITING/TIMED_WAITING), stack traces và lock ownership theo mức JVM nhận biết.
- GC logs, safepoints, heap/JFR, CPU sampling và classloading/JIT evidence.
- Application-level timers, OpenTelemetry spans, JMX pool metrics, HTTP client metrics, logs với trace/request ID.
- Counts và timing của executor/connection pool nếu thư viện xuất telemetry.

Nhưng Java Thread.State.RUNNABLE **không tương đương** OS thread đang chiếm CPU liên tục: một thread có thể nằm trong lời gọi native hay chờ I/O ở kernel. WAITING không chỉ ra nguyên nhân nguồn lực bên ngoài nếu không biết stack và pool. Thread dump là **ảnh chụp**, còn vấn đề tail latency thường cần chuỗi thời gian.

### 2.3. Phạm vi của JFR không đồng nhất với mọi API I/O

Một event name trong tài liệu không bảo đảm mọi đường đi I/O đều sinh ra event mong muốn. Các framework non-blocking, NIO selectors, native transports, asynchronous file channels, JNI, TLS libraries và RPC stacks có thể dùng kỹ thuật khác nhau. Với event ở tầng dưới, một lần logical HTTP request có thể ứng với nhiều socket reads/writes; ngược lại nhiều requests có thể dùng chung một connection HTTP/2.

Ví dụ một client non-blocking có request span 900 ms nhưng không thấy jdk.SocketRead trên thread request. Điều này **không chứng minh không có network I/O**: request có thể đợi trong connection pool/queue hoặc được xử lý ở event loop khác, và bộ ghi JFR có thể không instrument đúng thao tác đó.

**Khi so JFR và application traces, phải đồng nhất level:** request → logical RPC → connection acquisition → write → server wait → read → deserialize. Không gán một socket event cho cả request khi chưa đối chiếu trace và connection reuse.

## 3. Năm loại thời gian phải phân biệt

### 3.1. End-to-end latency

Từ khi client bắt đầu request đến khi nhận đủ response. Nó có thể gồm DNS, TCP/TLS, proxy queue, Java service, remote dependency, truyền dữ liệu và client rendering. Một JFR file của Java service **không** quan sát trọn hai đầu.

### 3.2. Application server span

Đo ở service Java từ nhận request đến khi ghi/hoàn tất response theo định nghĩa instrumentation. Không nhất thiết bao gồm thời gian request xếp hàng ở load balancer hoặc dữ liệu chờ trong kernel accept queue trước khi handler bắt đầu. Với asynchronous response, cần xác định thời điểm span kết thúc.

### 3.3. Client call span

Đo một thao tác HttpClient/JDBC/gRPC client ở tầng ứng dụng. Nó có thể chứa: connection pool wait, DNS, proxy resolution, TCP connect, TLS handshake, write, server processing, read, retries/backoff và decoding. Nhìn thấy 400 ms trong client span **không đủ** nói 400 ms network transit.

### 3.4. Java I/O event duration

Đo một hoạt động FileRead/SocketRead cụ thể theo semantics của JVM/JFR. Nó không đo mọi giai đoạn của một logical request và có thể bị threshold/filter. Nếu một request có 10 socket read events, cũng không tự cộng durations để ra request latency: các events có thể trên threads khác nhau, overlap, thiếu các giai đoạn trước/sau hoặc chỉ là một phần của protocol.

### 3.5. Kernel/device/remote-service metrics

- **TCP RTT estimate:** kernel ước lượng round-trip của TCP segments; không bằng thời gian DB query hay toàn bộ HTTP call.
- **Block-device await:** latency trung bình của I/O requests ở một device trong khoảng đo; khác thời gian Java FileRead có cache/FS và khác p99 của từng request.
- **Remote service duration:** thời gian được chính service bên kia đo theo ranh giới của nó; thường không bao gồm phần client pool wait hoặc hạ tầng phía trước.
- **Trace spans:** thời gian của công việc có instrumentation, thường lồng nhau; cộng span cha + span con gây **double counting**, còn spans song song có thể chồng lấp.

Không phép trừ một cách cơ học giữa các số khác clock, khác sampling hoặc khác phạm vi để gọi phần dư là “thời gian mạng”. Chỉ phân rã khi đã xác lập các khoảng tương thích, đồng hồ đáng tin và không đếm trùng.

## 4. Câu hỏi “JVM biết được điều gì?” và “điều gì chưa biết?”

| Câu hỏi | JVM/JFR có thể cung cấp | Bằng chứng cần thêm nếu muốn kết luận nguyên nhân |
| --- | --- | --- |
| Java thread đã chờ socket read bao lâu? | SocketRead event duration, thread, stack, endpoint nếu ghi được | Để biết chờ do đâu: tracing, TCP, proxy, remote logs |
| TCP retransmissions tăng không? | Không có toàn bộ TCP stack counters trong JFR | ss/nstat/SNMP counters, network telemetry, packet trace có phép |
| Mạng RTT tới dependency tăng không? | Application call/SocketRead chậm chỉ là tín hiệu | TCP RTT theo socket/path, network device và remote vantage point |
| Database query chạy bao lâu? | JDBC span ở client (nếu instrument), SQL tags có thể có | DB server query duration, execution plan, lock/wait, pool queues |
| Connection pool có nghẽn không? | Chỉ khi thư viện có metrics/spans riêng | Pool active/idle/pending, acquisition wait, connection lifecycle |
| DNS resolution chậm không? | Application timer/JFR stack có thể gợi ý | Resolver metrics/logs, DNS query timing/cache miss, server DNS |
| File read có chạm đĩa vật lý không? | FileRead timing/path và bytes theo API | Page cache, OS per-process I/O, block I/O trace/device counters |
| Storage volume đang bị throttling? | JVM file ops chậm là triệu chứng | iostat, cgroup io.stat/io.pressure, cloud volume limits, storage metrics |
| Container bị CPU throttling trong lúc I/O? | CPU/safepoint/thread metrics có thể gợi ý | cgroup cpu.stat, host scheduler metrics, run queue |
| Remote API bị rate limit/retry? | Client status/retry spans nếu được instrument | API gateway/service response logs, rate-limit headers, retry counters |
| JVM có GC pause trùng latency không? | JFR/GC logs, safepoints | APM request timeline và OS pressure để xác định tác động |
| Người dùng nhận response chậm ở đâu? | Server span chỉ cho một đoạn | Client RUM/tracing, edge/ingress timing, network path |
| TLS handshake/connection establishment tốn thời gian? | Client instrumentation, stack và một số JVM events khi có | Proxy TLS metrics, connect timing, socket state, certificate/DNS logs |
| Remote object store đọc file chậm? | Client span và network I/O ở Java | Object storage server-side latency, status/throttling, retry, network path |

**Ranh giới câu trả lời:** “JFR thấy SocketRead 350 ms” là quan sát. “Database mất 350 ms để thực hiện SQL” là suy luận; phải có DB-side bằng chứng hoặc trace cho cùng request để đủ mạnh.

## 5. Bẫy lớn: không có event không có nghĩa không có I/O

Trước khi kết luận điều gì **không xảy ra**, hãy kiểm tra:

1. Recording có bao phủ đúng instance/PID và timestamp của incident không?
2. jdk.SocketRead/jdk.SocketWrite/jdk.FileRead/jdk.FileWrite có được bật trong .jfc và có stackTrace không?
3. Threshold là bao nhiêu? Các I/O ngắn có thể bị loại, trong khi tổng hàng nghìn thao tác ngắn vẫn lớn.
4. Duration của event có đúng đối tượng cần đo không? Async/NIO/HTTP/2 có thể không khớp từng logical request.
5. Có đủ dữ liệu sau rolling retention/maxsize không? Có restart hoặc JFR chỉ thu sau sự cố không?
6. Event được thực thi trên thread khác? Đã lọc đúng thread/process chưa?
7. Có bước chờ **trước** I/O, như connection pool, executor queue, rate limiter, DNS, token refresh hoặc circuit breaker?
8. Đã kiểm tra library/native transport, kernel bypass, proxy/sidecar và version hỗ trợ event chưa?
9. Event dài có thể bị chọn bởi threshold, gây **selection bias**: median event được ghi không bằng median của mọi I/O thực hiện.
10. Dữ liệu JFR bị thiếu/gián đoạn do crash, disk full, instrumentation overhead hoặc file chỉ chứa một phần khoảng quan sát không?

Không nên đặt threshold cực thấp trên production mặc định để “ghi mọi event”: số lượng event/stack traces có thể tăng mạnh và làm thay đổi hiệu năng. Khi cần, thu profile ngắn có kiểm soát, đo overhead và lưu cấu hình.

## 6. Thu bằng chứng trong JVM: quy trình tối thiểu

Ví dụ lệnh JDK 21; thay PID và path bằng giá trị thật. jcmd cần quyền attach thích hợp; minimal container có thể không đóng gói JDK tools. Dùng đường dẫn có quyền ghi từ góc nhìn process Java.

~~~bash
java -version
jcmd -l
PID=12345                      # Ví dụ; phải xác minh PID thật
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" help JFR.start
jcmd "$PID" JFR.check
~~~

Nếu đã có một recording đang chạy, có thể dump dữ liệu theo chính sách vận hành mà **không dừng** recording. Nếu chưa có, cân nhắc ghi một phiên ngắn quanh workload tái hiện:

~~~bash
jcmd "$PID" JFR.start name=io_probe \
  settings=profile disk=true duration=2m \
  filename=/var/tmp/io-probe.jfr
~~~

Lệnh là minh họa: profile không bảo đảm mọi event đã bật với threshold mong muốn. Khi cần I/O chi tiết hơn, kiểm tra .jfc hoặc dùng API/cấu hình JFR chính xác cho từng event; đừng khẳng định event absent nghĩa I/O absent. Đường dẫn file do JVM đích xử lý; chờ phiên hoàn tất/xác minh file trước khi phân tích. Recording có thể chứa dữ liệu nhạy cảm.

Khi file đã hoàn chỉnh:

~~~bash
jfr summary /var/tmp/io-probe.jfr
jfr metadata /var/tmp/io-probe.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite \
  /var/tmp/io-probe.jfr
jfr print --events jdk.FileRead,jdk.FileWrite \
  /var/tmp/io-probe.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter \
  /var/tmp/io-probe.jfr
~~~

Lưu ý:
- jfr summary cho biết event types và count ghi được, **không phải tổng số thao tác I/O thực tế**.
- metadata mô tả schema/types và không chứng minh có event instance.
- jfr print in events nếu file có chúng. Với file lớn, chỉ in phần được chọn hoặc phân tích bằng JMC; output có thể dài.
- Nếu muốn stack, xem thuộc tính stackTrace của event và giới hạn stack-depth. Tăng độ sâu in không khôi phục các frame không được ghi.
- Đối chiếu event startTime/duration với application trace ID/time. Socket event không mặc định mang trace ID của logical request; cần instrument/ghép bổ sung.

**Cần chứng minh cái gì?** Với mỗi câu hỏi, hãy tạo một bảng gồm sự kiện, thread/stack, remote address hoặc file path, thời điểm, duration/bytes và mức độ coverage. Chỉ sau đó mới quyết định nguồn chứng cứ tiếp theo.

## 7. Dữ liệu OS/network: những thứ JVM không đo thay kernel

### 7.1. Linux socket state và TCP

Trên đúng host **và network namespace** của process/container, các lệnh thường hữu ích:

~~~bash
ss -s
ss -tin
ss -tinp
ip -s link
nstat -az
~~~

Giải thích:
- ss -s: tóm tắt số socket theo trạng thái, phục vụ dấu hiệu tích tụ kết nối.
- ss -tin: TCP sockets với thông tin nội bộ như RTT estimate, retransmission state, cwnd, send/receive queues tùy kernel.
- ss -tinp: thêm process association khi có quyền; trong container có thể hạn chế PID/namespace.
- ip -s link: bytes, packet drops/errors ở interface; số liệu thường **toàn interface**, không phải riêng Java app.
- nstat -az: thống kê protocol/counters kernel, phụ thuộc iproute2/cấu hình. Các counters thường là cộng dồn; lấy chênh lệch theo cửa sổ và đánh giá quy mô, không đọc một con số tích lũy rồi kết luận vừa xảy ra packet loss.

**TCP RTT** trong ss là ước lượng của kernel cho socket TCP, không trực tiếp bằng DNS/TLS/setup, server app time hoặc client HTTP latency. Cwnd/retrans có ích để giả thuyết network congestion/loss, nhưng còn phải tương quan với đường kết nối đúng, cùng thời điểm và metrics ở remote/proxy side.

Không dùng ss -tin từ một namespace khác rồi bảo “không có connection”. Sidecar mesh có thể khiến Java chỉ kết nối localhost, còn upstream TCP connection nằm tại sidecar; phải kiểm tra network path và namespace thực.

### 7.2. Dữ liệu packet-level và eBPF

Khi nghi retransmissions, handshake timeout, reset, abnormal socket queues hoặc packet loss, có thể cần packet capture hay eBPF tracing tại node/sidecar.

**Chỉ thực hiện khi có phê duyệt vận hành và bảo mật**, lọc hẹp theo host/port/duration, tránh ghi payload nhạy cảm và đánh giá overhead. TLS giúp bảo vệ payload trên wire nhưng metadata vẫn nhạy cảm; ở điểm termination có thể lộ nhiều hơn.

Packet trace có thể giúp trả lời: SYN/SYN-ACK mất bao lâu, retransmission xảy ra không, TCP reset do phía nào quan sát, window/ACK patterns bất thường ra sao. Nó **không** tự nói database query chậm hay Java code lỗi nếu không gắn với request/trace.

**Tránh đo chủ động thiếu kiểm soát:** lệnh tạo tải/scan, tracer sâu hoặc capture toàn cluster có thể làm nặng sự cố; nên ưu tiên telemetry đã có và truy vấn nhỏ nhất.

### 7.3. DNS, proxy, TLS và connection pooling

Một lần client.send chậm có thể gồm:
- DNS lookup/cache miss;
- connection pool pending do số connection hạn chế;
- TCP connect hoặc TLS handshake;
- proxy/sidecar queue/routing/retry;
- chờ remote service nhận và xử lý;
- response body transfer;
- deserialization/application callbacks.

JFR SocketRead/Write chỉ nhìn một phần; DNS/resolver, pool lease duration và TLS timing thường cần **client instrumentation** hoặc proxy/client library telemetry. Đo phases tách biệt, ít nhất: acquire → connect/TLS → send → first byte → last byte, nếu SDK hỗ trợ. HTTP/2 multiplexing làm nhiều requests dùng chung socket, nên không gắn một socket read với một HTTP request chỉ bằng địa chỉ IP/port.

## 8. Bằng chứng từ filesystem và block storage

### 8.1. FileRead/FileWrite là Java-visible operations

Một Java FileRead nhanh có thể nhận dữ liệu từ page cache, không cần chạm thiết bị. Một Java FileWrite nhanh có thể ghi vào page cache/kernel buffers; không đồng nghĩa ổ cứng/volume đã commit dữ liệu ổn định. Đặc biệt, fsync/FileChannel.force, journal, filesystem metadata và remote network filesystems có cơ chế riêng.

Nếu request chậm tại FileRead, các nguyên nhân cạnh tranh:
- device queue và IOPS/bandwidth limit;
- storage network congestion đối với NFS/remote volume;
- filesystem locks hoặc metadata contention;
- page-cache misses, memory pressure, direct I/O tùy ứng dụng;
- thread scheduling/CPU throttling;
- ứng dụng đọc quá nhiều file nhỏ, random access, serialization sau read.

Vì thế JFR file path và duration là **điểm bắt đầu**. Nó không tự xác định phần chờ vật lý ở NVMe/volume hay cache.

### 8.2. Linux counters để đối chiếu

Các công cụ dưới đây cần package (sysstat) và quyền phù hợp:

~~~bash
PID=12345
cat "/proc/$PID/io"
pidstat -d -p "$PID" 1 5
iostat -xz 1 5
~~~

Diễn giải:
- /proc/PID/io có các counters như rchar/wchar, read_bytes/write_bytes, syscr/syscw; chúng **khác nghĩa**. rchar/wchar có thể gồm bytes qua syscalls không tương ứng bytes từ đĩa, còn read_bytes/write_bytes liên quan I/O thực ở mức OS theo định nghĩa kernel. Đây là **counter**, không phải latency mỗi thao tác.
- pidstat -d cho per-process I/O throughput/đợi theo phiên bản/tool; cần kiểm tra đơn vị. Không đủ để kết luận p99 I/O.
- iostat -xz cho block-device stats: await, r_await/w_await, queue/throughput, utilization tùy version. Đây là **tổng hợp ở device**, không phải một Java method; filesystem/RAID/cloud volume có thể làm số liệu không trùng logical I/O.
- Lấy đúng device/volume đang phục vụ file path; host có nhiều volumes dễ khiến nhìn nhầm device khỏe khác.
- Đọc theo **cùng khoảng** incident, chú ý lần báo cáo đầu tiên của một số tiện ích có thể là tích lũy từ boot, không đại diện cho cửa sổ vừa phát sinh.

Nếu file nằm trên object store hoặc remote mount, block I/O counters của máy Java có thể không phản ánh latency phía server. Khi đó phải xem mount/client metrics, network và storage-provider metrics.

### 8.3. Cgroup v2 I/O và pressure stall information

Trong cgroup v2 phù hợp, có thể có:

~~~bash
cat /sys/fs/cgroup/io.stat
cat /sys/fs/cgroup/io.pressure
cat /sys/fs/cgroup/io.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.events
~~~

**Không giả định** /sys/fs/cgroup ở mọi host/container là cgroup thật của ứng dụng. Xác định cgroup path của process, mount, version (v1 hay v2) và controller có sẵn trước khi đọc.

- io.stat: read/write bytes và I/O counts theo thiết bị/cgroup, không tự có p95/p99 latency.
- io.pressure: PSI, biểu diễn thời gian các tasks bị stall vì I/O theo cửa sổ/counters được kernel cung cấp. Không tương đương disk response time mỗi request.
- io.max: cấu hình throttle bandwidth/IOPS nếu controller bật; đọc để biết **giới hạn**, không tự suy luận nó đã bị chạm.
- cpu.stat: CPU usage, throttling counters nếu có; hỗ trợ phân biệt ứng dụng bị thiếu CPU với tình trạng “I/O chậm”.
- memory.events: memory pressure/OOM-related events theo cgroup, giúp kiểm tra ảnh hưởng memory tới page cache và tiến trình.

Với cloud volumes hoặc CSI, cần thêm provider-side throttle/IOPS/throughput/latency metrics; kernel view của node chưa phải mọi góc nhìn của storage backend.

## 9. Bằng chứng từ các dịch vụ bên ngoài

### 9.1. HTTP/gRPC dependency và proxy

Lấy từ đúng dịch vụ/route/instance:
- Server-side request duration theo route/method/status, request rate và p95/p99.
- Concurrent requests, in-flight queue, worker threads, saturation và deadline/retry counts.
- Proxy/ingress: upstream connect time, upstream response time, retries, queue/routing time, status, reset/timeout reasons và TLS handshake metrics (nếu sản phẩm hỗ trợ).
- Trace spans dùng trace_id/span_id, parent relationships, request path; cân nhắc clock skew và sampling.
- Network telemetry giữa Java app ↔ proxy ↔ remote service, không chỉ giữa client ↔ Java app.

**Chú ý định nghĩa duration khác nhau:** Nginx/Envoy/ALB hoặc mesh có metrics tên giống nhau nhưng ranh giới bắt đầu/kết thúc không đồng nhất. Đọc tài liệu metric của sản phẩm đang dùng. “upstream_response_time” không nhất thiết bằng total client elapsed hoặc DB execution time.

### 9.2. Database

Một JDBC call chậm có thể vì:
- Đợi connection pool trước khi bắt đầu query;
- TCP connect/TLS/network;
- Server queue, CPU, lock, deadlock/serialization conflict;
- Query plan/index không phù hợp, scan nhiều rows, disk/cache misses;
- Transaction giữ lock lâu;
- Driver fetch/decoding hoặc đọc result set lớn;
- Retries/timeouts do ứng dụng hoặc proxy.

Nên thu:
- Pool acquisition time, active/idle/pending connections, timeout/eviction.
- Query fingerprint/ID và execution time **trên DB server**, không chỉ JDBC elapsed phía client.
- Locks/waits, active sessions, CPU, buffer cache, IOPS và slow query logs; execution plan khi có quyền và an toàn.
- Rows returned/bytes, transaction boundaries, query count per request, statement timeout.
- DB connection errors, failover/restart, replication lag hoặc quota/throttling nếu liên quan.

Ví dụ PostgreSQL có thể dùng pg_stat_activity, pg_stat_statements và EXPLAIN theo chính sách quyền và chi phí; chúng không tự gắn một câu SQL với JFR event nếu thiếu query ID/trace mapping. **Không chạy EXPLAIN ANALYZE trên truy vấn tốn kém trong production** khi chưa đánh giá tác động.

### 9.3. Redis/cache, message broker, object store

- Cache/Redis: server latency, command duration, CPU/evictions, connection/queue, retry, cache hit/miss.
- Kafka/RabbitMQ: broker request latency, producer batching, consumer lag, partition queue, replication/acks, throttling.
- Object storage: request IDs, server-side latency/TTFB nếu có, retry/throttle/status codes, bandwidth, multipart/size.
- DNS: resolver latency, lookup fail/timeout, cache hit/miss và authoritative/upstream issues.
- Service mesh: xDS/routing, outlier ejection, circuit breaking, pending requests, connect failures, sidecar CPU/throttling.

Tùy loại incident chỉ thu những nhóm **có liên quan đến lời gọi chậm thực tế**. Không yêu cầu “bật mọi debug log ở mọi service”; chi phí, rủi ro dữ liệu nhạy cảm và tính quá tải có thể làm suy giảm hệ thống.

## 10. Cách ghép evidence đúng một request

Một “bộ bằng chứng” mạnh có các lớp sau:

| Lớp | ID gắn kết | Mốc thời gian cần |
| --- | --- | --- |
| Edge/ingress | request ID / trace ID | Receive, queue, upstream connect, first/last response |
| Java service | trace ID / span ID, pod/PID | Handler start/end, route/status, application phases |
| Client library | parent span, connection/request metadata | Acquire, connect/TLS, send, response headers/body, retries |
| JFR | PID, thread ID/name, event/stack, endpoint | startTime/duration của SocketRead/FileRead, GC, ThreadPark |
| OS/kernel | PID/TID, socket tuple, netns/cgroup/device | Time-series RTT/retrans/queue, I/O, CPU/PSI, limits |
| Remote service | trace ID/request ID, server instance, query ID | Receive/queue/process/response; lock/CPU/storage |
| User-facing metric | route/customer cohort, request ID khi có | End-to-end latency/p99/error/timeout SLO |

**Đồng hồ và scope:** Timezone phải rõ (nên UTC), theo dõi clock synchronization/skew giữa hosts. Monotonic clock dùng đo duration trong một process; wall-clock timestamp dùng tương quan cross-host và có thể bị điều chỉnh. Một event trên socket cần ghép cẩn thận với logical request, đặc biệt với keepalive, HTTP/2 multiplexing, TLS termination và connection reuse.

### 10.1. Nested spans không được cộng tùy tiện

Ví dụ:
- Server span tổng 550 ms;
- HTTP client span 430 ms nằm **bên trong** server span;
- Database server span 370 ms nằm **bên trong** client/server chain tương ứng.

Không được cộng 550 + 430 + 370 = 1.350 ms rồi gọi đó là request latency. Các khoảng **lồng nhau**. Cũng không được khẳng định 430 - 370 = 60 ms “là thời gian network” nếu client span có pool wait, retries, proxy, serialization và clocks thiếu đồng bộ.

Muốn định lượng network/wait đúng, cần spans tách phases và measurement ở hai đầu, hoặc packet/kernel evidence. Thời gian “chưa giải thích” nên được ghi như **unattributed time** cho tới khi có nguồn đủ tốt.

### 10.2. Sampling và dữ liệu không trùng request

JFR record tập sự kiện theo cấu hình, distributed trace thường được sample một phần, access logs có thể được sampling/lược bỏ. Không nên gán ngẫu nhiên SocketRead 400 ms cho một request có trace cùng phút nếu không có mapping connection/thread đủ rõ. Với latency ở mức p99, phải ưu tiên mẫu **đúng tail cohort**, không chỉ traffic trung bình.

## 11. Runbook điều tra chậm I/O, từ rẻ tới sâu

### Bước 1 — Xác nhận triệu chứng và phạm vi

Ghi: thời điểm UTC, route/operation, p95/p99, errors/timeouts, throughput, bytes per request, instance/pod/PID, JDK/GC, deploy/change log, tỷ lệ bị ảnh hưởng. Sự cố toàn bộ service hay chỉ một dependency? Có trùng spike traffic không?

### Bước 2 — Xác nhận phần JVM nhìn thấy

Mở JFR đúng process và incident window. Xem SocketRead/Write, FileRead/Write, ThreadPark/monitor, CPU, GC. Kiểm tra event settings/thresholds, stacks và timestamps. Nếu không có dữ liệu, **ghi rõ coverage gap**, không vội kết luận không có I/O.

### Bước 3 — Xem application-level spans và client pools

Đặt các spans request handler, client call, connection acquisition, retry, timeout cạnh nhau. Một HTTP call chậm vì pool pending khác hoàn toàn một socket chậm do packet loss. Đừng đọc mọi thời gian chờ là time spent in network.

### Bước 4 — Kiểm tra host/container cùng thời điểm

Nếu nghi network: socket RTT/retrans/queues, interface drops, node/sidecar CPU, netns.
Nếu nghi disk: block-device await/queue, per-process I/O, io.pressure/io.stat, volume limits.
Nếu nghi CPU/scheduler: cpu.stat throttling, CPU load, runnable queue, host saturation.
Nếu nghi memory: page-cache pressure, swap/stall counters khi áp dụng; tránh nhầm heap used với toàn bộ memory của process.

### Bước 5 — Kiểm tra proxy và remote service

Thu server response time, queue/lock/CPU/storage, status/retry, query ID, trace ID; so khớp yêu cầu cụ thể với Java client span. Có remote service chứng minh chậm không? Nếu remote xử lý nhanh, phần nào xảy ra trước/sau remote span?

### Bước 6 — Đánh giá giả thuyết cạnh tranh

Ví dụ Java SocketRead dài:
- A: DB query/lock lâu;
- B: packet loss/retransmission;
- C: proxy queue/retries;
- D: Java thread bị deschedule/CPU throttled;
- E: event không liên quan đúng request hoặc recording thiếu ngữ cảnh.

Với mỗi giả thuyết, viết **dữ liệu nào sẽ xác nhận hoặc bác bỏ**. Ưu tiên evidence từ miền chịu trách nhiệm trực tiếp; không chỉ tìm một chart ủng hộ giả thuyết ban đầu.

### Bước 7 — Thử nghiệm nhỏ và xác minh

Thay một biến có cơ sở (pool limit, query plan/index, batch size, retry policy, concurrency, storage capacity hoặc network path). Chạy cùng workload, so SLO, errors, throughput, resource usage và metrics của cả dependency. Có rollback. Không vội tăng timeout: có thể chỉ biến lỗi nhanh thành hàng đợi tồn đọng.

## 12. Tình huống A — SocketRead lâu, nguyên nhân ở DB server

Dữ liệu giả định:
- Java/JFR: 60 SocketRead events kéo dài 300–600 ms trên connection hướng tới database, cùng đoạn checkout p99 tăng.
- JDBC span: 500 ms; connection acquisition dưới 5 ms.
- TCP ss: RTT estimate thấp và retrans không tăng rõ ở cùng socket/window.
- DB tracing/query log: statement execution khoảng 440–480 ms với lock wait tăng; query ID trùng request.

**Kết luận có cơ sở hơn:** ứng dụng đã chờ response trong khi DB thực hiện query/chờ lock; cần xử lý cạnh tranh/SQL/transaction, không tối ưu socket read method.

**Giới hạn:** RTT thấp và không thấy retrans không phủ định mọi lỗi mạng; nhưng kết hợp DB-side timing cho cùng query làm giả thuyết server wait mạnh hơn. Các con số là ví dụ, không phải một phép suy từ Java SocketRead ra DB execution.

Hành động: kiểm tra lock holders, transaction duration, index/query plan, connection behavior; xác nhận cải thiện cả DB execution time và checkout p99.

## 13. Tình huống B — Request chậm nhưng không có SocketRead event đáng kể

Dữ liệu giả định:
- HTTP client span 1.100 ms; JFR chỉ ghi ít SocketRead event.
- Connection pool: pending acquisition 900 ms và pending queue tăng.
- Remote service: xử lý trung vị 40 ms; network RTT/packet drops ổn định.
- App concurrency tăng từ 100 lên 1.000, pool chỉ cho 30 connections.

**Diễn giải:** bottleneck chính có thể ở **pool acquisition/queue trước khi socket read**. Không có SocketRead event dài không phủ định RPC chậm. Việc tăng connect timeout, đổi GC hoặc truy tìm packet loss không phải bước đầu phù hợp.

Hành động: đo peak inflight, pool checkout, connection reuse, retry storms, bounded concurrency và service capacity; cân nhắc pool size sau khi kiểm tra sức chịu tải phía remote. Tăng pool mù quáng có thể chỉ chuyển hàng đợi sang database.

## 14. Tình huống C — FileWrite nhanh, nhưng dữ liệu không bền vững và volume bị nghẽn

Dữ liệu giả định:
- Java FileWrite events phần lớn dưới vài ms.
- Một số giao dịch có bước flush/force lâu; latency end-to-end tăng theo batch.
- OS/cloud volume metrics: write queue, await, throttling/IOPS gần giới hạn.
- cgroup io.pressure và device stats tăng trong khoảng incident.

**Diễn giải:** write API nhanh có thể nhờ kernel buffering, còn bước yêu cầu durability hoặc thiết bị lưu trữ phía sau chậm. Nếu chỉ xem FileWrite histogram, có thể bỏ qua flush hoặc filesystem pressure. Chưa chắc toàn bộ latency do device nếu không ghép trace và host counters chính xác.

Hành động: kiểm tra transaction/flush frequency, write batch policy, cloud volume limit, filesystem và durability requirements. Không được giảm fsync hay bỏ durability để “tăng hiệu suất” khi chưa xác nhận yêu cầu an toàn dữ liệu.

## 15. Tình huống D — Network bị nghi oan vì CPU throttling

Dữ liệu giả định:
- Java client span tăng từ 120 ms lên 500 ms trong giờ peak.
- OS TCP RTT/retrans ít thay đổi.
- cgroup cpu.stat cho thấy throttling counter/time tăng mạnh.
- Request worker, event-loop threads hoặc sidecar CPU tiến gần quota; số queue pending tăng.
- Remote API server-side processing ổn định.

**Diễn giải:** thiếu CPU/scheduling/queue trong container có thể làm thao tác I/O **được cảm nhận là chậm** dù network path và remote handler không phải cơ chế chính. JVM CPU load và thread states riêng lẻ có thể chưa mô tả đủ cgroup throttling.

Hành động: xem CPU requests/limits, node contention, CPU-heavy serialization/TLS, traffic shaping và queue; thử workload/CPU quota có kiểm soát rồi đối chiếu p99.

## 16. Tình huống E — SocketWrite không chậm nhưng client timeout

Dữ liệu giả định:
- Java server SocketWrite nhanh, handler duration nhỏ.
- Ingress/proxy logs cho thấy downstream send/reset và queue/delivery khác thường.
- Network/edge telemetry cho thấy retransmission hoặc một nhóm client connections có RTT cao.
- Client end-to-end latency/timeout chỉ tăng ở một vùng mạng.

**Diễn giải:** Java write kết thúc nhanh có thể nghĩa bytes đã tới buffer hoặc một tầng transport, không có nghĩa client cuối cùng đã nhận đủ HTTP body. Cần evidence từ proxy/edge và phía client, phân biệt server completion, network delivery, client read timeout.

Hành động: kiểm tra load balancer response-body timing, size, client locations, TCP path và retry/cancellation. Không khẳng định server hoàn toàn vô can chỉ vì method write nhanh, nhưng không nên quy mọi timeout cho code server.

## 17. Ví dụ Java 17+ — đọc giới hạn của một số đo

Ví dụ sau là chương trình **độc lập và chạy được trên Java 17+**, dùng số liệu **giả định đã thu thập**. Nó minh họa lý do không được quy toàn bộ duration của một HTTP client span cho network, ngay cả khi chỉ số CPU của thread trong đoạn nhỏ.

Đặt tên file **LatencyBoundaryDemo.java**:

~~~java
import java.util.Locale;

public class LatencyBoundaryDemo {
    record Sample(
            String operation,
            long requestWallMs,
            long clientSpanWallMs,
            long clientThreadCpuMs) {

        Sample {
            if (requestWallMs <= 0
                    || clientSpanWallMs < 0
                    || clientSpanWallMs > requestWallMs
                    || clientThreadCpuMs < 0
                    || clientThreadCpuMs > clientSpanWallMs) {
                throw new IllegalArgumentException("Invalid sample");
            }
        }
    }

    static void report(Sample s) {
        double share = 100.0 * s.clientSpanWallMs() / s.requestWallMs();
        long wallMinusCpu = s.clientSpanWallMs() - s.clientThreadCpuMs();

        System.out.printf(
                Locale.ROOT,
                "%s: request=%dms, client-span=%dms (%.1f%%), "
                        + "client-thread-cpu=%dms, wall-minus-cpu=%dms%n",
                s.operation(),
                s.requestWallMs(),
                s.clientSpanWallMs(),
                share,
                s.clientThreadCpuMs(),
                wallMinusCpu);
    }

    public static void main(String[] args) {
        report(new Sample("checkout", 500, 420, 12));
        report(new Sample("report", 500, 50, 10));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LatencyBoundaryDemo.java
java LatencyBoundaryDemo
~~~

Stdout **chính xác** với dữ liệu cố định:

~~~text
checkout: request=500ms, client-span=420ms (84.0%), client-thread-cpu=12ms, wall-minus-cpu=408ms
report: request=500ms, client-span=50ms (10.0%), client-thread-cpu=10ms, wall-minus-cpu=40ms
~~~

Cách hiểu **đúng**:
- Trong mẫu checkout, client span chiếm 84% request wall time. Đây là vị trí cần điều tra trước.
- wall-minus-cpu = 408 ms là **chênh lệch giữa wall time của span và CPU time của một thread theo dữ liệu giả định**; nó có thể gồm waiting, scheduling, pool wait, DNS, network, server execution hoặc công việc chạy ở thread khác. **Không được gọi 408 ms là network latency.**
- Nếu client span có async tasks, CPU của nhiều threads không được cộng vào một chỉ số client-thread-cpu đơn giản; diễn giải càng hạn chế.
- Các durations trong ví dụ đã giả định cùng request, cùng scope, không âm; code không kiểm tra sampling errors, clock skew hay coverage. Nó minh họa phép tính, **không đo I/O thật** và không suy luận nguyên nhân gốc.

### 17.1. Đo thật ở cấp ứng dụng cần gì?

Với instrumentation production, dùng **System.nanoTime()** cho duration trong cùng process, không dùng System.currentTimeMillis() làm stopwatch. Nếu cần current thread CPU time, ThreadMXBean có thể cung cấp khi JVM/OS hỗ trợ và tính năng được bật; nó không đếm CPU trên mọi thread async trong một span.

Một span tốt nên có:
- service, route, request/trace ID, remote logical dependency;
- operation start/end, success/error, timeout type, status;
- request/response bytes, attempts/retries;
- pool acquisition, connect/TLS, first byte, body read và decode nếu SDK hỗ trợ;
- connection reuse và timeouts/deadlines;
- event-level link tới JFR nếu có cách ghép đáng tin.

Không log secret, token, mật khẩu, đầy đủ SQL parameters hay toàn bộ request/response payload chỉ để điều tra latency. Nếu gắn query/URL attributes, áp dụng chính sách redact/sampling.

## 18. Bảng chọn nguồn bằng chứng theo triệu chứng

| Triệu chứng chính | Kiểm tra trong JVM trước | Nguồn bổ sung ưu tiên | Điều chưa được phép kết luận |
| --- | --- | --- | --- |
| SocketRead chậm | Event/stack/endpoint, JDBC/HTTP span, GC/CPU | Remote processing logs, TCP RTT/retrans, proxy tracing | “Mạng chậm” chỉ từ read duration |
| Client RPC chậm, ít socket events | Pool metrics, ThreadPark, client span phases | Proxy/mesh queues, remote status, async transport | “Không phải I/O” vì thiếu event |
| SocketWrite chậm | Event size/duration, thread, backpressure | Socket send queue, network drops, downstream read speed | “Server code ghi chậm” không cần nhìn kernel |
| Client timeout nhưng server span nhanh | Handler/write span, cancellation/error logs | Edge/proxy/client RUM, transport errors | “Đã giao thành công tới client” |
| JDBC call chậm | Connection acquisition, driver spans, stack | DB waits/locks/query ID, execution plan | “SQL execution chậm” nếu chỉ có JDBC time |
| FileRead/FileWrite chậm | Path, duration, bytes, GC/CPU | iostat, process I/O, fs/cache, cloud volume | “Đĩa vật lý chậm” từ một FileRead |
| JFR file I/O ít nhưng p99 cao | Threshold, recording coverage, async model | Traces, queue/pool, dependency metrics | “Không có bottleneck” |
| p99 tăng dưới tải peak | RPS/route mix, GC, CPU, thread queues | cgroup throttle/PSI, proxy/server load | “JVM bug” trước khi xét capacity |
| DNS/TLS/connect spike | Client phase timers, logs, errors | Resolver, TLS/sidecar/ingress metrics, socket connect | “SocketRead đã đo cả DNS” |
| Chỉ một vùng địa lý bị lỗi | Server/trace by region/tenant | Edge/client/network path/CDN metrics | “Toàn JVM chậm” |

## 19. Chất lượng dữ liệu, an toàn và những sai lầm thường gặp

### 19.1. Tương quan không đồng nghĩa nhân quả

Nếu JVM SocketRead duration tăng cùng lúc với TCP retransmissions, đây là bằng chứng ủng hộ khả năng network path có vấn đề, **nhưng vẫn cần** kiểm tra đúng socket/remote IP/namespace/route. Retrans toàn node có thể thuộc workload khác. Nếu DB query p99 cũng tăng, cả hai có thể cùng chịu load hoặc là hai vấn đề độc lập.

Kết luận nên nêu:
1. **Quan sát trực tiếp:** nguồn nào, metric nào, timestamp nào;
2. **Giả thuyết:** cơ chế khiến latency tăng;
3. **Bằng chứng phân xử:** từ OS, proxy hoặc remote service;
4. **Hạn chế:** missing telemetry, sampling/clock skew;
5. **Thử nghiệm/khắc phục:** thay đổi nào và đo lại bằng gì.

### 19.2. Sai lầm phải tránh

- **Đọc SocketRead duration là network RTT.** Nó có thể bao server think time, waiting và scheduling.
- **Đọc SocketWrite success là client đã nhận dữ liệu.** Kernel buffering/ACK/application consumption là các tầng khác nhau.
- **Đọc FileWrite duration là disk durable write time.** Có page cache, flush và filesystem semantics.
- **Không thấy JFR event = không có I/O.** Event settings/threshold, async/native path và recording window có thể làm thiếu dữ liệu.
- **Chỉ nhìn JVM CPU/heap để kết luận I/O.** Thiếu cgroup throttling, kernel/block-device và remote logs.
- **Chỉ dùng số liệu host aggregate để kết luận một pod.** Phải biết netns/cgroup/device/socket/process mapping.
- **Cộng các spans lồng nhau thành thời gian request.** Parent/child thường chồng lấp; async work càng dễ làm sai.
- **So dữ liệu khác thời điểm/process.** PID mới sau restart hoặc snapshot sau spike không thay được lịch sử trước lỗi.
- **Tăng timeout/pool/retry ngay.** Có thể phóng đại queue, connection load, retry storms và làm dependency sập.
- **Bật debug trace/capture toàn hệ thống.** Có thể tạo overhead, rò dữ liệu nhạy cảm, làm méo phép đo.
- **Tin threshold mặc định không đổi.** Kiểm tra .jfc/event settings và version chính xác.
- **Sử dụng traceroute/ping bất kỳ để phủ định network issue.** Probe có thể đi path/protocol/priority khác traffic ứng dụng.
- **Coi TCP RTT thấp là remote response nhanh.** DB có thể đang lock/query lâu.
- **Coi high iostat await là nguyên nhân duy nhất.** Device aggregate có thể phản ánh job khác; cần liên hệ đúng volume và service.
- **Tin log timestamp tuyệt đối của nhiều hosts luôn đồng bộ.** Cần clock skew/UTC và trace span boundaries.
- **So count của các event threshold khác nhau.** Không cùng mẫu quan sát.

### 19.3. Bảo vệ dữ liệu và độ an toàn vận hành

JFR, logs, traces, packet captures và database query samples có thể chứa path, class names, endpoints, IP, request IDs, SQL, file names, stack traces hoặc thông tin nhạy cảm. Chỉ thu phạm vi cần thiết, hạn chế quyền, redaction trước khi chia sẻ, retention rõ ràng và tránh công cụ làm tăng tải/treo production.

Nếu không có quyền truy cập OS/remote service, ghi rõ **blocker về evidence** và yêu cầu đúng nhóm phụ trách: SRE/network/storage/DB/platform. Không tự diễn giải “không thấy evidence” thành “không xảy ra”.

## 20. Mẫu báo cáo sự cố I/O theo ranh giới bằng chứng

~~~text
# I/O latency investigation

Sự cố / mục tiêu SLO:
Service / build / JDK / PID / pod / namespace:
Incident UTC start/end:
RPS / request mix / payload / concurrency:
p95/p99 / error rate / timeout type:
Java application spans / trace IDs:
JFR file / configuration / event thresholds:
Relevant JFR I/O events (type, time, duration, stack, endpoint/path):
Thread/GC/CPU context:
Coverage gaps and sampling limits:

OS evidence:
- Host/netns/cgroup/device identifiers:
- Socket RTT/retrans/queues, interface drops, time window:
- Process/block I/O and io.pressure/limits:
- CPU throttling / memory pressure:
- Missing permissions or unavailable commands:

External evidence:
- Proxy/ingress/mesh timings, retries, status:
- Remote service / DB query ID and server duration:
- Locks, pool queue, CPU/storage, throttling:
- Client experience and end-to-end trace:

Hypothesis A / supporting evidence / falsifier:
Hypothesis B / supporting evidence / falsifier:
What is directly observed vs inferred:
Confidence and remaining gaps:
Smallest proposed experiment:
Validation metrics and rollback:
~~~

Mẫu này là **khung incident**, không phải file output của JFR. Một báo cáo tốt không cần mọi ô đều có số; nó cần nêu rõ chỗ nào **đã đo**, chỗ nào **chưa thể quan sát** và cách lấy evidence phù hợp.

## 21. Checklist cuối cùng

- [ ] Tôi xác nhận đúng service, instance/PID, JVM version, recording và khoảng UTC của incident.
- [ ] Tôi phân biệt end-to-end latency, server span, client call span, JFR I/O duration, kernel RTT và remote processing time.
- [ ] Tôi không gán SocketRead cho toàn bộ network/server phase hoặc SocketWrite cho delivery thành công tới client.
- [ ] Tôi kiểm tra JFR event settings, thresholds, stack coverage, recording retention và async/native transport.
- [ ] Tôi có application-level metrics cho connection pool, executor queue, retries, deadline và error codes.
- [ ] Tôi biết logical request nào tương ứng với service/connection/trace và hiểu HTTP/2 multiplexing.
- [ ] Tôi lấy OS/network telemetry từ **đúng host, network namespace và khoảng thời gian**.
- [ ] Nếu nghi disk, tôi có process/cgroup/device metrics và hiểu page cache/fsync/remote-volume khác Java FileWrite.
- [ ] Nếu nghi CPU scheduling, tôi kiểm tra cgroup CPU throttling, host pressure và sidecar.
- [ ] Tôi kiểm tra remote service/DB/proxy metrics và đối chiếu cùng query/request ID khi có thể.
- [ ] Tôi không cộng spans nested hoặc aggregate từ nhiều threads thành request latency một cách mù quáng.
- [ ] Tôi xem giả thuyết cạnh tranh và viết ra điều kiện bác bỏ từng giả thuyết.
- [ ] Tôi không thay pool/timeout/heap/GC/storage/network mà chưa xác định bottleneck và guardrails.
- [ ] Tôi đảm bảo telemetry/capture an toàn, có redaction, quyền truy cập và thời gian thu hợp lý.
- [ ] Kết luận tách **quan sát trực tiếp**, **suy luận có điều kiện**, **chưa đủ dữ liệu** và **việc phải đo tiếp**.

## 22. Kết luận

**JVM rất tốt trong việc cho biết ứng dụng Java đã làm gì và bị chặn ở đâu theo góc nhìn runtime; JVM không phải hệ thống đo đầy đủ network, kernel, disk hoặc dịch vụ bên ngoài.**

Với I/O latency, trình tự đúng là:

**Triệu chứng & SLO → xác minh JFR/trace coverage → xem Java I/O và thread evidence → kiểm tra OS/kernel/container đúng namespace → kiểm tra proxy/remote service đúng request → ghép timeline, loại trừ giả thuyết cạnh tranh → thử nghiệm và đo lại.**

Một kết luận hữu ích phải trả lời đồng thời: **“Tôi quan sát được gì từ JVM?”, “đó là phần nào trong end-to-end path?”, “phần còn lại cần nguồn nào chứng minh?”, “nếu giả thuyết đúng thì số liệu nào sẽ đổi?”**

### Tài liệu tham khảo chính thức

- Oracle JDK 21 — jfr command (summary, metadata, print): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 17 — Troubleshoot Performance Issues Using Flight Recorder, mục I/O Performance: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — JFR API event settings và threshold: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — jcmd/JFR.start/JFR.check: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Linux ss(8) manual: https://man7.org/linux/man-pages/man8/ss.8.html
- Linux Kernel cgroup v2 (io.stat, io.max, io.pressure, cpu.stat): https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
