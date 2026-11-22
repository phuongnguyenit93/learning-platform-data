# Java Networking: đối chiếu metric ứng dụng, trạng thái socket và giới hạn hệ điều hành

## 1. Bài toán: server “còn sống” nhưng người dùng không kết nối được

Một Java server có thể báo **CPU 30%**, **heap chỉ dùng 40%** và dashboard hiển thị **200 active requests**, nhưng client vẫn liên tục gặp `ConnectException`, kết nối chậm, `Too many open files` hoặc timeout. Vấn đề nằm ở đâu?

Muốn trả lời, không chỉ xem metric Java. Một request đi qua nhiều lớp:

~~~text
                    Java application metrics
   requests, accepted sessions, active handlers, queue,
   connection pool, response latency, connect errors
                              |
                              v
                    JVM / process resources
     Java threads, heap, direct buffers, process open FDs
                              |
                              v
                     Operating system
       TCP LISTEN / ESTABLISHED / CLOSE_WAIT / TIME_WAIT
     accept queue, SYN queue, ports, socket buffers,
        per-process and system-wide resource limits
                              |
                              v
                  Network / proxy / client
       NAT, firewalls, LB, retries, timeouts, DNS,
        retransmissions and upstream availability
~~~

**Mấu chốt:** ba nhóm số liệu **không có cùng đơn vị, phạm vi hay thời điểm đo**:

- Một `activeRequest` thường là **đơn vị xử lý ứng dụng**, không phải một TCP socket.
- Một kết nối HTTP keep-alive có thể rảnh nhưng vẫn ở **TCP ESTABLISHED**.
- Một WebSocket được giữ lâu có thể **không có request handler đang chạy**.
- Một `TIME_WAIT` entry có thể tồn tại trong kernel **sau khi ứng dụng đã đóng socket**, không tương đương một Java `Socket` đang mở.
- Chỉ số `openFileDescriptorCount` của **process** chứa nhiều loại file descriptors ngoài network sockets (file, pipe, epoll, logging...), không phải “số connections”.
- `ss -s` hoặc kernel TCP statistics thường đo **network namespace/host**, không phải một Java process duy nhất.
- Nếu Java service nằm trong container, metric host có thể bao gồm cả nhiều tiến trình/namespaces khác hoặc không phản ánh cùng giới hạn mà container chịu.

Mục tiêu: biết **đếm đúng thứ cần đếm**, ghép metric ứng dụng với TCP socket states và OS limits, phân tích sự chênh lệch, xây biểu đồ/alert có ý nghĩa và chạy một demo **Java 17+** minh họa cách một JVM có thể có cả socket phía client, phía server và listening socket nhưng **chỉ có hai server sessions đang xử lý**.

## 2. Bắt đầu từ câu hỏi và phạm vi, đừng bắt đầu từ một con số

Đặt năm câu hỏi trước khi mở terminal:

1. **Đang đo đối tượng nào?** Process PID nào, container/pod nào, IP/port nào, IPv4 hay IPv6, inbound hay outbound?
2. **Đếm gì?** Request đang chạy, established sockets, file descriptors, TCP state entries, hàng đợi accept, hay connection pool entries?
3. **Ở thời điểm nào?** Snapshot instant hay rate trong một phút? Metrics export mỗi 15 giây nhưng `ss` lấy tại thời điểm khác có thể lệch vì burst ngắn.
4. **Cấp nào?** Process, network namespace, toàn host, cluster, proxy hay cả backend pool?
5. **Mục đích điều tra?** Connection leak, server overload, client reconnect storm, lỗi bind, ephemeral port exhaustion, file descriptor exhaustion hay OS backlog?

Một số tình huống:

| Hiện tượng | Số liệu cần đối chiếu đầu tiên |
| --- | --- |
| `Too many open files` | Process open FDs, per-process soft limit, socket/file type |
| HTTP 200 chậm dù CPU thấp | Request/queue latency, active handlers, socket send/receive queue, downstream I/O |
| Kết nối mới thất bại nhưng connections cũ hoạt động | `LISTEN`, accept queue, errors, backlog, FD limits, firewall/proxy |
| Outbound `Cannot assign requested address` | Ephemeral port use, outbound connection churn, destination, NAT, TIME_WAIT |
| `CLOSE_WAIT` tăng dài hạn | Socket close ownership trong process, leaked streams/sessions |
| `TIME_WAIT` tăng đột biến | Tốc độ đóng kết nối, active closer, connection reuse, client retry |
| App báo 100 active nhưng OS thấy 20.000 established | Keep-alive/idle pools, WebSockets, proxy fan-out, scope mismatch |
| Heap bình thường nhưng RSS tăng | Direct buffers, native memory, kernel socket memory, threads, file descriptors |

**Không vội chỉnh `sysctl` hoặc tăng `ulimit`** khi chưa biết có leak hay chỉ là lưu lượng bình thường. Tăng limit có thể tạm che đi một rò rỉ tài nguyên và làm sự cố lan rộng hơn.

## 3. Định nghĩa metric ứng dụng thật chính xác

Một hệ thống đáng quan sát nên có những nhóm metric:

| Metric minh họa | Loại | Khi nào tăng/giảm | Ý nghĩa |
| --- | --- | --- | --- |
| `net_accept_total` | Counter | Tăng sau mỗi socket inbound được accept | Tổng lượt accept kể từ khi process khởi động |
| `net_connection_closed_total` | Counter | Tăng khi socket đã thực sự close | Tổng lượt đóng do ứng dụng ghi nhận |
| `net_active_server_connections` | Gauge | Tăng sau accept, giảm trong `finally` sau close | Số accepted server sockets ứng dụng đang sở hữu |
| `net_outbound_active_connections` | Gauge | Theo open/close hoặc pool connection state | Outbound connections do ứng dụng quản lý |
| `http_requests_in_flight` | Gauge | Tăng khi request handler bắt đầu, giảm khi kết thúc | Công việc HTTP đang xử lý, **không phải socket** |
| `http_request_duration_seconds` | Histogram | Observe khi request hoàn tất | Latency phân phối p50/p95/p99 theo method/route |
| `http_request_errors_total` | Counter | Theo status/loại lỗi | HTTP 4xx/5xx và lỗi transport theo contract |
| `net_connect_failures_total` | Counter | Tăng khi connect thất bại | Lỗi mở kết nối mới từ app |
| `net_read_timeouts_total` | Counter | Khi đọc quá hạn | Client/server read stall |
| `net_bytes_received_total` / `sent_total` | Counter | Byte thực sự nhận/gửi | Traffic app level; không luôn bằng wire bytes |
| `executor_active_tasks` | Gauge | Số worker đang chạy | Saturation của thread pool |
| `executor_queued_tasks` | Gauge | Task chờ trong executor queue | Dấu hiệu backlog trong ứng dụng |
| `pool_idle_connections` | Gauge | Kết nối rảnh trong HTTP/DB pool | Có thể vẫn TCP ESTABLISHED |
| `socket_send_queue_bytes` | OS/diagnostic | Kernel outbound data đang chờ | Client đọc chậm, nghẽn network hoặc scheduling |

Tên ở bảng là **gợi ý thiết kế**, không phải một bộ metric tự động có sẵn trong mọi JDK library. JDK `HttpClient`, Netty, Spring Boot, Micrometer hay Prometheus exporters có các metric cụ thể khác nhau; phải đọc documentation đúng phiên bản và thực tế instrument.

### 3.1. Counter, gauge và histogram không thể dùng thay nhau

- **Counter** như `accepted_total` tăng theo thời gian sống của process. Để biết **tốc độ**, tính rate/delta; reset khi process restart không có nghĩa “connections bị trả về 0 ở kernel”.
- **Gauge** như `active_connections` mô tả thời điểm gần nhất được collect. Một giá trị 200 hôm nay và 200 ngày mai chưa chắc là **cùng 200 sessions**.
- **Histogram** về request duration cho phép phân tích phân phối latency, không thể suy ra p99 từ mỗi số trung bình cộng.
- **Error rate** phải có mẫu số phù hợp: `connect_failures / connect_attempts` khác `http_5xx / all_requests` và khác timeout rate.

**Đừng gắn `remoteIp`, `userId`, `socketId`, request ID lên mọi time series label**: cardinality có thể nổ khi client nhiều hoặc thay đổi liên tục. Dùng route template, role, protocol, status class và instance ID hữu hạn; giá trị chi tiết thuộc logs/traces có sampling và kiểm soát dữ liệu riêng tư.

### 3.2. Đếm tại đúng thời điểm và đảm bảo giảm trong finally

Với inbound TCP, tăng gauge sau khi ứng dụng nhận ownership của accepted socket, giảm khi socket không còn được sở hữu:

~~~java
AtomicInteger active = new AtomicInteger();
LongAdder acceptedTotal = new LongAdder();

void onAccepted(Socket socket) {
    active.incrementAndGet();
    acceptedTotal.increment();
    try (socket) {
        handleRequest(socket);
    } catch (IOException error) {
        recordSocketError(error);
    } finally {
        active.decrementAndGet();
    }
}
~~~

Đây là **fragment minh họa**, cần các hàm ứng dụng `handleRequest`/`recordSocketError` và imports Java thích hợp. Nếu có transfer ownership sang worker khác, gauge nên đo **socket lifecycle**, không chỉ thời gian method accept trả về.

**Trường hợp submit thất bại:** nếu `ExecutorService.execute(...)` ném `RejectedExecutionException` trước khi handler chạy, ứng dụng phải **đóng socket** và **giảm gauge nếu đã tăng**, nếu không số liệu có thể báo leak ảo. Nếu instrumentation đếm accept total trước reject, rõ ràng rejected vẫn được tính vào accept total, nhưng active gauge phải về 0 sau close.

### 3.3. HTTP multiplexing làm quan hệ 1 request = 1 connection sai

- HTTP/1.1 keep-alive tái sử dụng một socket cho nhiều request **nối tiếp**.
- HTTP/2 có thể multiplex nhiều streams/requests trên **một TCP connection** nếu cả client/server hỗ trợ.
- Client HTTP pool có thể giữ socket idle dù không có request in-flight.
- Reverse proxy có thể gom nhiều client connections vào ít backend connections hoặc mở outbound connections riêng; mỗi tầng có số liệu độc lập.
- WebSocket giữ một session có thể tồn tại lâu dù không có message; message callbacks thường ngắn hơn socket lifetime.

Vì vậy **đừng so số active HTTP requests bằng số dòng ESTABLISHED** rồi coi khác nhau là lỗi. Phải phân loại protocol, direction và connection pooling.

## 4. TCP states là trạng thái của kernel, không phải Java thread state

Trên Linux/macOS/Windows, TCP stack có các trạng thái; công cụ hiển thị tên và chi tiết tùy OS:

| TCP state | Mô tả trực giác | Khi nào nên điều tra |
| --- | --- | --- |
| `LISTEN` | Đang chờ nhận kết nối tại local endpoint | Server không listen đúng IP/port, backlog đầy |
| `SYN-SENT` / `SYN_SENT` | Đang cố mở outbound connection | Connect timeout, routing/firewall, server unreachable |
| `SYN-RECV` / `SYN_RECEIVED` | Đã nhận SYN, handshake chưa hoàn tất | SYN flood, backlog, network path, asymmetric routing |
| `ESTABLISHED` | TCP connection đã thiết lập | Idle pool, active sessions, WebSocket, cả hai đầu của loopback |
| `FIN-WAIT-1` / `FIN_WAIT1` | Phía này đã gửi FIN và đang chờ xác nhận | Close in progress, peer/network chậm |
| `FIN-WAIT-2` / `FIN_WAIT2` | Đã nhận ACK cho FIN, chờ peer đóng | Peer giữ half-close quá lâu, timeout policy |
| `CLOSE-WAIT` / `CLOSE_WAIT` | **Peer đã gửi FIN**, local application chưa đóng phần socket tương ứng | Nếu tăng dai dẳng: kiểm tra leak/close ownership |
| `LAST-ACK` / `LAST_ACK` | Đang chờ ACK cho FIN cuối | Cần xem tốc độ đóng và connection loss |
| `TIME-WAIT` / `TIME_WAIT` | Tạm giữ trạng thái sau kết thúc để xử lý packet cũ/delayed | Churn/reconnect, active closer; **không tự là leak** |
| `CLOSING` | Hai phía cùng khởi xướng đóng | Có thể bình thường khi close đồng thời |
| `CLOSED` | Không còn kết nối active trong TCP control block | Thường không có socket entry thường trực để đếm |

**Phân biệt đóng phía ứng dụng với TCP state:** `Socket.close()` trả về không có nghĩa kernel phải xóa ngay mọi dấu vết của connection. `TIME_WAIT` có thể tồn tại sau khi socket descriptor được đóng. Ngược lại, `CLOSE_WAIT` cho thấy **local side chưa hoàn tất close** sau khi peer đóng hướng gửi; nếu số lượng tăng mãi, nghi ngờ ứng dụng quên `close` nhưng vẫn phải điều tra bằng PID, stack và lịch sử.

### 4.1. Phân tích `ESTABLISHED` trước khi coi là “active users”

Ví dụ cùng một JVM chạy loopback TCP server và kết nối tới chính server đó:

~~~text
Java process
   listener on 127.0.0.1:randomPort   -> 1 listening socket
   outbound client Socket A           -> 1 endpoint TCP
   outbound client Socket B           -> 1 endpoint TCP
   accepted server Socket A           -> 1 endpoint TCP
   accepted server Socket B           -> 1 endpoint TCP

Metric ứng dụng server: 2 accepted active connections.
OS có thể liệt kê: 4 TCP ESTABLISHED endpoints trong cùng process
                  + 1 LISTEN endpoint.
Process FD: còn có file/pipe/epoll/console và descriptor khác.
~~~

Đây là trường hợp **không thể mong các bộ đếm bằng nhau**. Số dòng kernel còn phụ thuộc hệ điều hành, IPv4/IPv6, quyền xem socket và thời điểm snapshot. Khi cùng process sở hữu cả đầu client lẫn server, không được cộng hai đầu loopback rồi gọi đó là “4 người dùng”.

### 4.2. `CLOSE_WAIT` khác `TIME_WAIT`

**CLOSE_WAIT:** remote đã gửi FIN, local application vẫn có trách nhiệm đóng socket sau khi xử lý phần dữ liệu cần thiết. Nếu `CLOSE_WAIT` của một PID tăng dai dẳng cùng `open_fd`, kiểm tra code dùng `Socket`, `InputStream`, `OutputStream`, `try-with-resources`, handling cancellation và connection pool release.

**TIME_WAIT:** thường gắn với bên chủ động kết thúc TCP close; kernel duy trì state để xử lý các segment bị trễ. Nhiều TIME_WAIT có thể phản ánh **lượng kết nối ngắn đóng liên tục**, không phải Java stream chưa close. Tìm nguyên nhân client liên tục mở/đóng (không reuse pool), proxy lifecycle, request retries hoặc deployment churn; không vội bật kernel tunables rủi ro.

### 4.3. `LISTEN` chưa có nghĩa nhận được mọi connection

Một listening socket không tự bảo đảm acceptor/worker đủ năng lực. Có thể `LISTEN` vẫn hiển thị, nhưng accept queue đầy, JVM đã chạm FD limit, CPU scheduling không đủ, rate limiter từ chối hoặc proxy route không đúng. Cần ghép **accept rate + accepts/errors + queue length + socket backlog** và latency ở hai đầu.

## 5. File descriptor (FD) là tài nguyên hữu hạn nhưng không phải mọi FD đều là socket

Trên Unix-like systems, TCP sockets thường dùng **file descriptors**. Mỗi process có giới hạn open FDs, nhưng danh sách FD còn chứa:

- TCP và UDP sockets, Unix-domain sockets.
- File log/config/data, pipes, eventfd, epoll/kqueue-related handles.
- Temporary files, mmap-related resources và runtime internals.
- Các descriptors phục vụ Java application và thư viện native.

Do đó:

~~~text
process_open_fd != number_of_ESTABLISHED_sockets
process_open_fd != app_active_connections
process_open_fd != total_OS_TCP_states
~~~

### 5.1. Hai số cần đọc cùng nhau: open và limit

Trên Unix-like JVM có MXBean phù hợp:

~~~java
var bean = ManagementFactory.getOperatingSystemMXBean();
if (bean instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    long open = unix.getOpenFileDescriptorCount();
    long max  = unix.getMaxFileDescriptorCount();
    System.out.println("Open FDs: " + open + ", max FDs: " + max);
} else {
    System.out.println("Unix FD metrics not available on this platform");
}
~~~

Đây là **Java 17 fragment** yêu cầu import `java.lang.management.ManagementFactory`. `com.sun.management.UnixOperatingSystemMXBean` là **API mở rộng dành cho nền tảng Unix-like**, không phải một API có sẵn để trả số FD trên mọi Windows JVM. Nếu đo được số `max` dương, tỉ lệ `open/max` giúp cảnh báo gần giới hạn; nhưng một số hệ thống có thể trả sentinel khi không biết, nên phải kiểm tra giá trị trước khi chia.

**Không suy diễn từ open=300, max=1024 rằng có 300 TCP connections.** Hãy dùng công cụ OS để phân loại FD và TCP states trước khi kết luận.

### 5.2. Soft limit, hard limit và system limit

Trên Linux, `RLIMIT_NOFILE` có **soft** và **hard** limit của **process**. Soft limit quyết định điều kiện mở thêm descriptors trong thực tế; hard limit là trần quản trị để nâng soft theo quyền. Còn có system-wide limits và systemd/container runtime settings.

| Cấp | Ví dụ | Cần nhớ |
| --- | --- | --- |
| Shell hiện tại | `ulimit -n` | Chỉ nói shell đang chạy command, không chắc là limit JVM service |
| Process Java cụ thể | `/proc/<PID>/limits`, `prlimit` | Đúng PID của instance cần điều tra |
| Service manager | systemd `LimitNOFILE` | Có thể khác interactive shell |
| OS toàn cục | `fs.file-max` và related kernel resource limits | Không phải per-JVM FD limit |
| Container/process sandbox | ulimits/cgroups/runtime | Không luôn trùng host shell |
| Ứng dụng | max clients, pool cap, worker count | Giới hạn logic nằm **ngoài** file descriptor limit |

Một app có nhiều log files, pipes hoặc outbound sockets có thể chạm FD limit **trước khi** đạt target “10.000 inbound clients”. Ngược lại, nếu tăng NOFILE nhưng executor/heap/network không chịu nổi, nâng limit không giải quyết năng lực phục vụ thực.

### 5.3. `EMFILE` / `ENFILE` và lỗi trong Java

Thông báo `Too many open files` thường liên quan process chạm giới hạn open file descriptors (POSIX `EMFILE`), hoặc hệ thống cạn bảng file entries (POSIX `ENFILE`) theo OS/context. Trong Java, accept/open socket/file operations có thể ném `IOException`, `SocketException` hoặc thông báo native tương ứng.

Đừng catch `IOException` rồi map mọi lỗi thành “FD exhaustion”; xem message/native errno/log cùng metric `open_fd`, process limit và loại tài nguyên đang tăng. Nếu system-wide limit cạn, nhiều processes cũng có thể bị ảnh hưởng.

## 6. Công cụ Linux: quan sát đúng PID, cổng và TCP state

> Các lệnh trong mục này là **diagnostics trên Linux**, không phải Java code. Dùng PID/port của một dịch vụ mà bạn có quyền quan sát. Với container, hãy chạy trong **network namespace phù hợp** hoặc hiểu rõ khác biệt giữa namespace host/pod. Đừng quét toàn host khi chỉ cần một service.

Ví dụ biến shell:

~~~bash
PID=12345
PORT=8080
~~~

Thay `12345` bằng **PID thật của Java process**, `8080` bằng **cổng app lắng nghe**. Đọc trong cùng môi trường/namespace thực tế.

### 6.1. Đang LISTEN ở đâu?

~~~bash
ss -ltnp "sport = :$PORT"
~~~

- `-l`: listening sockets.
- `-t`: TCP; `-n`: numeric addresses/ports; `-p`: process info nếu có quyền.
- Kiểm tra `Local Address:Port`. Nếu chỉ bind `127.0.0.1` thì remote host không thể trực tiếp kết nối tới interface khác chỉ vì port đang LISTEN.
- Một cổng có thể có IPv4/IPv6 khác nhau; `[::]:8080` và `0.0.0.0:8080` không nên coi luôn tương đương trong mọi cấu hình.

Trên Linux `ss -ltn`, các cột `Recv-Q`/`Send-Q` của listening sockets thường biểu thị **số kết nối đã qua handshake chờ accept** và giới hạn hàng đợi tương ứng theo kernel/stack. Đừng lấy chúng làm tổng số active TCP sessions. Kernel release và cơ chế TCP SYN backlog có thể khiến các counters khác nhau.

### 6.2. Đếm các kết nối liên quan port ứng dụng

~~~bash
ss -tanp "( sport = :$PORT or dport = :$PORT )"
ss -tan state established "( sport = :$PORT or dport = :$PORT )"
ss -tan state close-wait "( sport = :$PORT or dport = :$PORT )"
ss -tan state time-wait "( sport = :$PORT or dport = :$PORT )"
~~~

Đây là những snapshot gần thời điểm đo; `ss -p` có thể cần quyền tương ứng để in PID/process. Bộ lọc `sport/dport` chọn **endpoint có port đó**, không chứng minh mọi dòng thuộc **PID của ứng dụng**: nhiều process, proxy hoặc connections TIME_WAIT không còn owner rõ trong userspace cũng có thể xuất hiện.

**Phân biệt direction:** nếu `PORT` là listener inbound, accepted sockets thường có **source/local port** bằng PORT. Còn những kết nối outbound từ ứng dụng tới một database ở port 5432 có **destination/peer port** 5432; bạn cần lọc theo peer/local IP, PID và role, không coi tất cả port 5432 là traffic của JVM đó.

### 6.3. Ghép socket với process qua lsof

~~~bash
lsof -nP -a -p "$PID" -iTCP
~~~

`-a` áp dụng giao các điều kiện; `-p` giới hạn process, `-iTCP` chọn TCP FDs, `-nP` tắt DNS/service name lookup để không làm điều tra chậm. Với quyền không đủ, kết quả có thể thiếu. `lsof` liệt kê **FD còn mở**, trong khi `ss` có thể hiển thị `TIME_WAIT` state không còn là một FD mở ở process; hai danh sách không được kỳ vọng trùng 100%.

### 6.4. Đọc giới hạn của đúng process

~~~bash
grep -E "Max open files" "/proc/$PID/limits"
ls -1 "/proc/$PID/fd" | wc -l
prlimit --pid "$PID" --nofile
~~~

- `/proc/<PID>/limits` cho soft/hard limits của **process**.
- `/proc/<PID>/fd` chứa symbolic links đại diện descriptors; số dòng thay đổi trong lúc liệt kê và có thể bị hạn chế quyền. Một số lệnh đọc/quan sát cũng có thể ảnh hưởng rất nhỏ hoặc race với việc FD đóng/mở.
- `prlimit` có thể dùng để xem/điều chỉnh resource limits với quyền phù hợp. **Ở đây chỉ dùng để xem**, không nâng limit khi chưa có kế hoạch.
- `ulimit -n` trong một terminal mới **không phải** bằng chứng Java service do systemd/container khởi động có cùng NOFILE.

Cần kết hợp `lsof` và `ss` để xác định open FDs là **socket hay file**, không suy luận từ tổng số FDs.

### 6.5. Xem snapshot kernel nhưng giữ đúng phạm vi

~~~bash
ss -s
ss -tin state established
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
sysctl net.ipv4.ip_local_port_range
~~~

- `ss -s` là thống kê **trong network namespace hiện tại**, không phải process-specific.
- `ss -ti` có thể cho các TCP chi tiết như RTT, retransmission/congestion state tùy kernel, nhưng sample có thể thay đổi nhanh; tránh log mọi socket ở tải cao.
- `somaxconn` liên quan giới hạn **accept backlog**; `tcp_max_syn_backlog` liên quan pending SYN handling theo Linux TCP. Cả hai **không phải** tham số “tối đa số connections ESTABLISHED mà Java được phép dùng”.
- `ip_local_port_range` liên quan **ephemeral local ports cho outbound connections** trong network namespace theo các điều kiện thực tế; không coi nó là “số clients tối đa” của server inbound.

Không tự động áp dụng một giá trị `sysctl -w` từ tutorial. Phải xác định root cause, kernel version, tải thực, môi trường container, rollback plan và ảnh hưởng bảo mật/tài nguyên.

### 6.6. Khi nghi backlog đầy

Nếu inbound connect latency cao, service vẫn `LISTEN` nhưng accept rate giảm:

1. So sánh **inbound connect rate** ở proxy/client với `accept_total` của Java.
2. Xem `ss -ltn` để biết listening queue và backlog theo thời điểm.
3. Đọc các Linux TCP extended counters liên quan listen drops/overflows qua `nstat`/`netstat -s`, đo **delta theo thời gian**.
4. Xem worker saturation, GC pauses, CPU quotas, scheduler delays và lỗi accept do FD exhaustion.
5. Phân biệt SYN stage và fully-established accept queue; chúng là các điểm nghẽn khác nhau.
6. Nếu chạy sau load balancer, có thể hàng đợi ở proxy trước khi tới kernel socket của Java; điều tra cả tầng proxy.

Các bộ đếm kernel thường **aggregate**, có thể gồm nhiều services. Không kết luận “Java port 8080 gây toàn bộ TcpExtListenOverflows” chỉ từ một tổng namespace-wide.

## 7. Windows và macOS: cùng câu hỏi, khác công cụ

### 7.1. Windows PowerShell

Windows không có `/proc/<PID>/fd` và `RLIMIT_NOFILE` theo nghĩa Linux. Bạn có thể xem TCP endpoints bằng PowerShell:

~~~powershell
$targetPid = 12345
Get-NetTCPConnection -OwningProcess $targetPid |
    Group-Object State |
    Select-Object Name, Count

Get-NetTCPConnection -OwningProcess $targetPid |
    Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess

Get-Process -Id $targetPid |
    Select-Object Id, ProcessName, HandleCount

netstat -ano
netsh int ipv4 show dynamicport tcp
~~~

**Không dùng biến PowerShell `$PID` để chỉ Java process một cách mù quáng**: `$PID` là PID của **PowerShell hiện tại**. Dùng `$targetPid` lấy từ công cụ quản lý process, JMX/JFR hoặc task manager.

`HandleCount` của Windows process **không phải TCP socket count**. Handles bao gồm nhiều loại kernel objects; quyền và việc API đếm endpoints cũng khác Unix FD model. Không so trực tiếp metric `getOpenFileDescriptorCount` của Unix MXBean với `HandleCount` Windows rồi gắn cùng ngưỡng.

`Get-NetTCPConnection` có thể cần quyền phù hợp và phản ánh trạng thái TCP ở thời điểm quan sát. `netstat -ano` là lệnh chung khi module NetTCPIP không có; `netsh int ipv4 show dynamicport tcp` xem dải dynamic ports của Windows, **không nói hiện tại còn bao nhiêu port tự do cho từng destination**.

### 7.2. macOS

Các công cụ phổ biến:

~~~bash
PID=12345
lsof -nP -a -p "$PID" -iTCP
netstat -anv -p tcp
sysctl kern.maxfiles
sysctl kern.maxfilesperproc
ulimit -n
~~~

`lsof` giới hạn theo process và TCP; `netstat` có thể hiện cả nhiều ứng dụng; `sysctl` hiển thị các giới hạn kernel macOS. Shell `ulimit` vẫn không chứng minh limit của service daemon đã khởi động với launchd. Cần đối chiếu process thực tế, quyền và cấu hình runtime.

### 7.3. So sánh công cụ không đồng nghĩa so sánh định nghĩa

| Câu hỏi | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Socket TCP của một process | `lsof -p PID -iTCP` / `ss -p` | `Get-NetTCPConnection -OwningProcess` | `lsof -p PID -iTCP` |
| TCP states | `ss -tan` | `Get-NetTCPConnection`, `netstat -ano` | `netstat -anv -p tcp` |
| Process resources | `/proc/PID/limits`, `/proc/PID/fd` | Process handles và Windows resource counters | `lsof`, process limits và `sysctl` |
| Dynamic local port range | `ip_local_port_range` | `netsh int ipv4/ipv6 show dynamicport tcp` | OS network sysctls theo phiên bản |
| Java PID metrics | JMX/`UnixOperatingSystemMXBean` khi hỗ trợ | JMX và Windows-specific tools | JMX/`UnixOperatingSystemMXBean` khi hỗ trợ |

Đừng chuẩn hóa dashboard thành “fd_open” bằng cách gán Windows `HandleCount` vào cùng định nghĩa mà không ghi rõ nguồn, platform và semantics.

## 8. JVM metrics để bổ sung bức tranh

### 8.1. `ManagementFactory` và MXBeans

Java 17 cung cấp nhiều Management Beans để quan sát **JVM/process**:

~~~java
int liveThreads = ManagementFactory.getThreadMXBean().getThreadCount();
long heapUsed = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage().getUsed();

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println(pool.getName()
            + ": count=" + pool.getCount()
            + ", used=" + pool.getMemoryUsed());
}
~~~

Đây là **Java fragment** cần imports `java.lang.management.ManagementFactory` và `BufferPoolMXBean`, không phải standalone. Nơi đây có thể hiển thị buffer pools như `direct` và `mapped` tùy runtime. Đừng coi `direct_buffer_used` là toàn bộ **native memory** hoặc kernel socket buffers; các vùng nhớ native, thread stacks, TLS, JIT, mapped files và memory của OS có cách hạch toán khác.

### 8.2. Open FD metric từ Unix MXBean

Đo đúng **process JVM** trên nền tảng hỗ trợ:

~~~java
var os = ManagementFactory.getOperatingSystemMXBean();

if (os instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    long open = unix.getOpenFileDescriptorCount();
    long max = unix.getMaxFileDescriptorCount();
    if (max > 0 && open >= 0) {
        double utilization = 100.0 * open / max;
        System.out.printf("FD use: %.1f%%%n", utilization);
    }
}
~~~

`open/max` giúp phát hiện tiến sát giới hạn, nhưng không cho biết trong đó bao nhiêu TCP sockets hoặc file descriptors. Cần ghép với `lsof`/OS tooling và xem **trend sau khi traffic giảm**. Nếu số open FD liên tục tăng khi application active connections giảm về baseline, nghi có file/socket/resource leak.

### 8.3. JVM threads và scheduler

Một TCP server dùng kiểu **mỗi connection một blocking worker thread** có thể hết threads/stack memory/CPU scheduling **trước khi** hết file descriptors. Ngược lại, NIO/Netty dùng ít selector threads nhưng rất nhiều connections; số JVM threads nhỏ không tự nghĩa service xử lý tốt. Quan sát thread count, executor queue, active handlers, runnables blocked, GC pause và socket buffer pressure.

Dùng `jcmd <pid> Thread.print` để quan sát thread dump khi được phép. `jcmd` thuộc công cụ chẩn đoán của JDK, cần đúng phiên bản/quyền, có chi phí và có thể tác động tải; không chạy liên tục mỗi giây trong production.

### 8.4. GC và native memory

Nếu ứng dụng có 5.000 connections và heap dùng ít nhưng RSS/process memory tăng:

- Kiểm tra **direct/mapped buffers** qua `BufferPoolMXBean`; nhớ rằng metric chỉ phản ánh pool tương ứng.
- Kiểm tra thread stacks, JIT/code cache, native libraries và TLS/native allocations.
- Với Linux, xem OS socket memory/`ss -m` theo bối cảnh và container accounting; kernel socket buffers không thể đo bằng mỗi heap usage.
- JDK `jcmd <pid> VM.native_memory summary` đòi JVM khởi động với **Native Memory Tracking (NMT)** được bật phù hợp; không giả định lệnh luôn có dữ liệu khi NMT chưa bật.
- Tìm leak bằng nhiều tín hiệu, không đổ lỗi cho “socket buffer” chỉ vì RSS tăng.

## 9. Ví dụ Java 17+ hoàn chỉnh: hai kết nối inbound, bốn endpoint TCP cùng JVM

Mục tiêu demo: chứng minh bằng quan sát **một process có thể sở hữu nhiều FD/socket hơn metric server-side active connections**. Chương trình tạo một `ServerSocket` loopback tại cổng ngẫu nhiên, mở **hai client Socket trong chính JVM**, chấp nhận chúng thành **hai accepted server Sockets** và giữ worker bằng `CountDownLatch` để snapshot có thể tái lập.

- `LongAdder acceptedTotal` đếm tổng **lượt accept** trong demo.
- `AtomicInteger active` đếm **accepted sockets phía server** chưa đóng.
- Hai client sockets cùng process là **outbound endpoints** riêng; chúng **không làm `active` tăng**.
- `ServerSocket` đang LISTEN cũng là một tài nguyên riêng.
- `osFdSnapshot(...)` in **số FDs thực tế vào stderr** trên JVM Unix-like hỗ trợ `UnixOperatingSystemMXBean`; trên Windows in thông báo không hỗ trợ.
- Chương trình in ra **stdout có kết quả cố định**, còn FD counts thay đổi theo JDK/OS/libraries và chạy vào stderr để không mạo nhận một giá trị tuyệt đối.
- Chỉ khi main cho phép worker hoàn tất, các accepted sockets mới close và gauge trở về 0; các client sockets được đóng ở `try-with-resources`.

Lưu thành **SocketMetricCorrelationDemo.java**:

~~~java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public class SocketMetricCorrelationDemo {
    static void osFdSnapshot(String point) {
        OperatingSystemMXBean bean =
                ManagementFactory.getOperatingSystemMXBean();

        if (bean instanceof
                com.sun.management.UnixOperatingSystemMXBean unix) {
            System.err.println("OS [" + point + "]: open_fd="
                    + unix.getOpenFileDescriptorCount()
                    + ", max_fd=" + unix.getMaxFileDescriptorCount());
        } else {
            System.err.println("OS [" + point
                    + "]: Unix FD MXBean unavailable");
        }
    }

    static void process(
            Socket peer, CountDownLatch finishWork,
            AtomicInteger active, CountDownLatch finished,
            AtomicReference<Throwable> failure) {

        try (peer) {
            if (!finishWork.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker wait expired");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            failure.compareAndSet(null, e);
        } catch (IOException | RuntimeException e) {
            failure.compareAndSet(null, e);
        } finally {
            active.decrementAndGet();
            finished.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host =
                InetAddress.getByName("127.0.0.1");
        ExecutorService workers =
                Executors.newFixedThreadPool(2);

        AtomicInteger active = new AtomicInteger();
        LongAdder acceptedTotal = new LongAdder();
        CountDownLatch acceptedReady = new CountDownLatch(2);
        CountDownLatch finishWork = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try (ServerSocket listener =
                     new ServerSocket(0, 8, host)) {

            Thread acceptor = new Thread(() -> {
                try {
                    for (int i = 0; i < 2; i++) {
                        Socket peer = listener.accept();
                        try {
                            workers.execute(() -> process(
                                    peer, finishWork,
                                    active, finished, failure));
                            acceptedTotal.increment();
                            active.incrementAndGet();
                            acceptedReady.countDown();
                        } catch (RejectedExecutionException rejected) {
                            peer.close();
                            throw rejected;
                        }
                    }
                } catch (Exception error) {
                    failure.compareAndSet(null, error);
                }
            }, "tcp-acceptor");
            acceptor.start();

            try (Socket clientA =
                         new Socket(host, listener.getLocalPort());
                 Socket clientB =
                         new Socket(host, listener.getLocalPort())) {

                if (!acceptedReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Accept timeout");
                }

                System.out.println("app.accepted_total="
                        + acceptedTotal.sum());
                System.out.println("app.active_server_connections="
                        + active.get());
                System.out.println("app.local_client_sockets=2");

                // Giá trị FD thay đổi theo OS/JVM; in ra stderr.
                osFdSnapshot("connections-open");

                // Cho handlers đóng accepted sockets.
                finishWork.countDown();
                if (!finished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Worker finish timeout");
                }

                System.out.println(
                        "app.active_server_connections_after_close="
                        + active.get());
                osFdSnapshot("accepted-closed");
            }

            acceptor.join(5000);
            if (acceptor.isAlive()) {
                throw new IllegalStateException(
                        "Acceptor did not exit");
            }
            if (failure.get() != null) {
                throw new IllegalStateException(
                        "Server task failed", failure.get());
            }
        } finally {
            finishWork.countDown();
            workers.shutdown();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                throw new IllegalStateException(
                        "Worker pool did not stop");
            }
        }

        System.out.println("workers.terminated="
                + workers.isTerminated());
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 SocketMetricCorrelationDemo.java
java SocketMetricCorrelationDemo
~~~

**Stdout đã được kiểm tra bằng Java 17 JShell:**

~~~text
app.accepted_total=2
app.active_server_connections=2
app.local_client_sockets=2
app.active_server_connections_after_close=0
workers.terminated=true
~~~

**Stderr phụ thuộc OS, không có số cố định.** Trên Unix-like JVM hỗ trợ extension có dạng:

~~~text
OS [connections-open]: open_fd=<giá trị thực tế>, max_fd=<giới hạn>
OS [accepted-closed]: open_fd=<giá trị thực tế>, max_fd=<giới hạn>
~~~

Trên JVM/OS không hỗ trợ extension (ví dụ có thể trên Windows), stderr sẽ ghi:

~~~text
OS [connections-open]: Unix FD MXBean unavailable
OS [accepted-closed]: Unix FD MXBean unavailable
~~~

### 9.1. Diễn giải đúng thay vì tìm một con số “khớp”

- `accepted_total=2`: app đã chấp nhận **hai** TCP connections server-side.
- `active_server_connections=2`: hai accepted sockets còn nằm trong vòng đời handlers.
- `local_client_sockets=2`: JVM này còn sở hữu **hai client sockets** — không cộng vào gauge phía server.
- Listening `ServerSocket` cũng đang mở. Nếu dùng công cụ OS đúng thời điểm trong demo, có thể thấy cả listener và các endpoints ở hai phía của loopback.
- `active_server_connections_after_close=0`: handlers đã đóng accepted sockets, gauge về 0, nhưng **hai client sockets và listener còn mở** tại thời điểm `osFdSnapshot("accepted-closed")`. Vì vậy process FD tổng **không bắt buộc bằng 0** hoặc giảm đúng 2 vì runtime có thể đang quản lý tài nguyên khác.
- `workers.terminated=true`: executor dừng sau các handlers. Không có nghĩa kernel TIME_WAIT entries lập tức biến mất.

**Quan trọng:** lệnh `ss` trên Linux hay `Get-NetTCPConnection` trên Windows phải được chạy **trong lúc server đang giữ socket mở** nếu muốn bắt snapshot ESTABLISHED. Demo dùng latches nhưng khoảng chụp có thể khá ngắn; để quan sát trực tiếp bằng terminal, bạn có thể thêm một lệnh chờ thủ công **chỉ trong lab**. Không thêm sleep vô hạn vào production server.

### 9.2. Vì sao demo dùng Java app metric + OS FD metric?

Ứng dụng có thể biết rõ **nghiệp vụ sở hữu bao nhiêu inbound accepted sockets**, nhưng nó không biết mọi internal FD được tạo bởi JDK, TLS provider, file logger, selector hoặc native library. OS/JMX process counters nhìn lớp thấp hơn. **Kết hợp hai góc nhìn** mới có thể phát hiện app gauge sai, socket leak hoặc giới hạn quá thấp.

Chỉ quan sát một metric `active` mà không nhìn `close`/FD/TCP states dễ bỏ sót rò rỉ. Nhưng chỉ quan sát FD cũng khó biết đâu là DB connections hay WebSockets của ứng dụng.

## 10. Backlog, listen queue và SYN queue: đừng nhầm với active connections

### 10.1. `ServerSocket(backlog)` chỉ là một hint

~~~java
ServerSocket server = new ServerSocket(
        8080, 128, InetAddress.getByName("0.0.0.0"));
~~~

Đây là **Java fragment**; cổng có thể đã bị chiếm, cần close/trust controls. Tham số `backlog=128` gợi ý độ dài hàng chờ incoming connections, nhưng giá trị thực có thể chịu điều chỉnh/capping của OS và implementation. Nó **không** có nghĩa “Java cho phép tối đa 128 ESTABLISHED connections”.

Trong Linux hiện đại, accept queue cho connections đã hoàn tất handshake và SYN queue cho half-open connections là hai khái niệm khác nhau; tuning có thể phụ thuộc `somaxconn`, `tcp_max_syn_backlog` và cấu hình SYN cookies. Không suy ra mọi hệ điều hành/Linux kernel version triển khai giống hệt.

### 10.2. Chẩn đoán accept queue saturation

Nếu app `active_connections` thấp nhưng connect latency tăng:

- Đọc `ss -ltn` Recv-Q/Send-Q và listener port.
- Kiểm tra acceptor có bị block vì xử lý business logic ngay trong accept thread không.
- Kiểm tra số threads chạy, executor queue, GC pauses và CPU throttling.
- Xem resource exhaustion như `EMFILE` làm `accept()` lỗi.
- So sánh TCP listen overflow/drop **delta** cùng tần suất connection attempts.
- Xem proxy/ingress queue, không chỉ kernel listener.
- Đừng chỉ tăng backlog mà bỏ qua nguyên nhân accept loop chậm.

### 10.3. Client không vào được có thể hoàn toàn do mạng

Một `SYN_SENT` tăng ở client nhưng server không có SYN tương ứng có thể gợi ý firewall/routing/NAT; một server `LISTEN` và backlog rỗng không bảo đảm DNS, security group, LB health hoặc TLS handshake đều đúng. Không có metric Java đơn lẻ nào chứng minh packet thực sự đi tới đúng node.

## 11. Ephemeral ports và TIME_WAIT: bẫy khi client outbound tạo kết nối quá nhanh

### 11.1. Local ephemeral port là gì?

Khi Java client gọi:

~~~java
Socket socket = new Socket("example.test", 443);
~~~

mà không chọn local port cụ thể, OS thường chọn một **ephemeral local port** trong dải cấu hình. Mỗi TCP connection được xác định bằng tuple (protocol, local IP, local port, remote IP, remote port). Giới hạn hiệu dụng về outbound connections phụ thuộc **tuple, local addresses, destination distribution, NAT, kernel reuse rules và các tài nguyên khác**, không chỉ lấy kích thước port range làm “tổng connections tối đa”.

### 11.2. Triệu chứng và chẩn đoán

Nếu JVM mở/đóng hàng nghìn outbound TCP connections/giây tới **một destination**:

- Tỉ lệ `connect_failures` và latency tăng.
- TCP `TIME_WAIT` có thể tăng trên phía chủ động close.
- Khi không có local port/tuple khả dụng, application có thể nhận `BindException`/`ConnectException` với thông báo kiểu `Cannot assign requested address` tùy OS/JDK.
- FD usage có thể **không cao** khi các sockets đã đóng nhưng kernel giữ TIME_WAIT, do đó không kết luận “FD thấp => không liên quan socket churn”.
- NAT gateway hoặc proxy có thể có giới hạn ports riêng và gây lỗi dù local JVM còn nhiều tài nguyên.

**Giải pháp ưu tiên:** tái sử dụng HTTP connections bằng client pool/keep-alive, điều phối request concurrency, giảm retry storm, dùng backoff+jitter và cân nhắc nhiều endpoints theo thiết kế. Đừng vội chỉnh `tcp_tw_reuse` hoặc disable TIME_WAIT mà không hiểu bảo đảm TCP và rủi ro của kernel/version.

### 11.3. Câu chuyện phía server inbound

Một server lắng nghe `0.0.0.0:8080` có thể phục vụ rất nhiều clients cùng lúc vì TCP connections khác nhau ở remote tuple; ephemeral local port range **không trực tiếp là trần số inbound connections trên port 8080**. Giới hạn thực còn nằm ở FDs, memory, CPU, threads, protocol, accept/backlog và infrastructure.

## 12. Buffer và memory: heap thấp không chứng minh socket khỏe

### 12.1. Kernel send/receive queues

Khi Java gọi `OutputStream.write`/`SocketChannel.write`, dữ liệu có thể vào buffer của kernel; kết quả syscall hay CompletionStage không tự chứng minh peer đã xử lý business message. Nếu peer đọc chậm, send queue và memory có thể tăng. `ss -tin`/`ss -m` trên Linux có thể cung cấp thông tin per-socket (tùy quyền/kernel).

Khi client gửi nhanh hơn server đọc, receive queue có thể tăng; nếu ứng dụng không consume kịp, kernel window/backpressure có thể tác động throughput. Nếu ứng dụng còn buffer cả payload trong heap hoặc direct buffers, **áp lực có thể nằm ở nhiều lớp cùng lúc**.

### 12.2. Java direct buffers khác TCP buffer

`ByteBuffer.allocateDirect(...)` tạo direct buffer bên ngoài Java heap thông thường. `BufferPoolMXBean` có thể thống kê một số pools của JVM; trong khi kernel TCP socket buffers không nhất thiết được tính vào cùng counter. Không cộng `direct_buffer_used + socket_rcvbuf_size` rồi gọi đó là RSS chính xác: con số cấu hình buffer không phải byte thực đang dùng, và memory accounting phụ thuộc OS/runtime.

### 12.3. So sánh memory/container

Nếu service chạy trong container, xem container memory limit/working set/oom events (cgroup hoặc platform metrics), JVM heap usage, native buffers và kernel socket memory theo công cụ phù hợp. Một process có thể bị OOM-killed dù `-Xmx` còn dư vì tổng RSS/native/mapped/threads và container policy.

## 13. Dữ liệu phải cùng thời điểm và cùng tập đối tượng

Giả sử dashboard mỗi 60 giây scrape `net_active_server_connections`, còn kỹ sư chạy `ss` đúng lúc peak 10 giây. Kết quả lệch có thể do **sampling**, không phải bug.

Quy trình đối chiếu:

1. Xác định **PID/JVM process start time** để tránh nhầm process mới sau restart; PID có thể được tái sử dụng.
2. Ghi **UTC timestamp** và timezone tại mỗi snapshot.
3. Xác nhận **network namespace, container/pod/node, IP, port và protocol**.
4. Lấy **app metric gauge/counter + process FD + TCP states** trong cùng vài giây nếu có thể.
5. Nhóm theo **role**: listening, inbound accepted, outbound client, proxy-to-backend, Unix-domain sockets.
6. Với counters, đo **delta/rate** trên một khoảng ổn định; không so một cumulative counter với một current gauge.
7. Chia theo phiên bản deploy, workload, request arrival rate, keep-alive/connection pooling và proxy routing.
8. Chỉ kết luận leak nếu thấy **tăng tích lũy có hệ thống**, không trở về baseline sau khi workload ngừng, và xác định tài nguyên nào chưa được close.

### 13.1. Không có phép trừ đơn giản luôn đúng

Một công thức dễ khiến nhầm:

~~~text
OS ESTABLISHED - app active requests = leaked connections  (SAI)
~~~

Lý do: idle keep-alive, HTTP/2 multiplexing, WebSocket, inbound/outbound cùng process, proxy connections và scope khác nhau đều làm vế trái lớn mà không có leak. Thay vì thế:

~~~text
App active sockets (định nghĩa cụ thể)
  -> compare with OS open TCP FDs for SAME PID + role
  -> compare with FD total and limit
  -> cross-check TCP states and historical trends
  -> inspect ownership and close paths when anomalies persist
~~~

Có thể dùng check invariant nội bộ như `accepted_total - closed_total ≈ active_connections` **chỉ nếu** accepted/closed counters cùng định nghĩa, mọi đường accept/reject/close đều instrument đầy đủ và đang xét cùng process uptime. Khi app restart, counters reset; khi event được đo không đồng bộ, sai số có thể xuất hiện. Một gauge trực tiếp đo active sockets có thể đáng tin hơn phép trừ counters thiếu events.

## 14. Bảng chẩn đoán từ metric tới nguyên nhân có thể

| Quan sát đồng thời | Giả thuyết ưu tiên | Thao tác xác minh |
| --- | --- | --- |
| `open_fd` tăng sát process NOFILE; `lsof` cho nhiều TCP sockets | Pool/socket leak hoặc tải vượt thiết kế | Xác định loại sockets, owners, close paths, conn pool |
| `open_fd` tăng nhưng TCP sockets ổn định | File/pipe/resource leak không phải TCP | Xem `lsof -p` toàn bộ FD categories |
| `CLOSE_WAIT` của PID tăng, close counter thấp | Local app không close sau peer FIN | Thread dump, try-with-resources, cancellation cleanup |
| `TIME_WAIT` nhiều, FD process thấp | Connection churn, active close, retry storm | Rate outbound connects, pooling, destinations |
| `SYN_SENT` nhiều ở client | Connect path/timeout/firewall/destination slow | DNS, route, peer listener, LB/proxy, timeout |
| `LISTEN` vẫn có nhưng accept queue đầy | Acceptor chậm, FD errors, burst | `ss -ltn`, accept rate, listen drops, executor |
| Request queue cao nhưng TCP count ổn định | Application handler/DB bottleneck | Worker saturation, lock/DB latencies |
| `ESTABLISHED` cao, active requests thấp | Idle keep-alive/WebSocket/pooling | Phân loại sockets theo protocol/role, idle timeout |
| Connect failures cao, ephemeral ports/single destination stressed | Outbound tuple/port exhaustion hoặc NAT limit | Port ranges, TIME_WAIT, NAT/proxy metrics |
| Heap thấp, process RSS cao | Direct buffers/native/thread/kernel accounting | BufferPoolMXBean, NMT, OS memory and queues |
| Socket send queues tăng, CPU thấp | Slow consumers/network bottleneck | `ss -ti/-m`, client read rates, backpressure |
| TCP retransmissions tăng trên host | Network loss/congestion hoặc remote slow | Per-socket detail, NIC, routes; không quy lỗi một PID vội |

Bảng trên đưa ra **giả thuyết**, không phải chẩn đoán chắc chắn. Phải xác minh bằng dữ liệu cùng scope và thử nghiệm có kiểm soát.

## 15. Thiết kế dashboard/alert có ý nghĩa

Một dashboard phù hợp cho Java network service nên đặt **các lớp cạnh nhau**, không gộp thành một “healthy score” bí ẩn:

- **Application:** connections active/accepted/closed/rejected, request arrival rate, concurrent requests, latency p95/p99, error rates, request/worker queues, connection-pool active/idle/pending, network bytes.
- **JVM process:** process open FD/max (khi hỗ trợ), JVM thread count, heap/direct buffer usage, GC pause, CPU, process RSS nếu đo được.
- **OS/network:** TCP states theo port/namespace, `LISTEN` accept queue, retransmissions, TCP resets, ephemeral port distribution, soft/hard resource limits, socket buffer pressure.
- **Infrastructure:** pod readiness/restarts/OOM, ingress/LB connection failures, connection draining, NAT/egress limits, upstream health.

### 15.1. Alert theo xu hướng và tỉ lệ, không theo một số cố định

Ví dụ một cảnh báo “FD utilization cao” có thể xét `open_fd / max_fd` tăng sát trần **cùng connect/accept errors**; ngưỡng thực tế cần baseline, thời gian duy trì, tăng trưởng và môi trường. Không có ngưỡng 80% áp dụng tối ưu cho mọi Java process.

`CLOSE_WAIT` tăng liên tục sau khi lưu lượng giảm là tín hiệu điều tra mạnh hơn một snapshot đơn lẻ. `TIME_WAIT` cao nhưng ngắn hạn sau burst có thể là bình thường. Một `SYN_RECV` spike khi có tải đột ngột cần đánh giá cùng listen drops, rate limits và mạng.

### 15.2. Metric labels tránh bùng nổ cardinality

Nên dùng `direction=inbound/outbound`, `protocol=tcp/http/websocket`, `route=/users/{id}`, `status_class=2xx/5xx`, `instance_id`. Không thêm IP khách hàng, socket 4-tuple, token hoặc request ID làm Prometheus labels cho mọi connection; thông tin chi tiết thuộc logs/traces được redact.

### 15.3. Rate sampling và tương quan

Nếu hệ thống có 500 connects/s, một snapshot TCP mỗi phút có thể bỏ lỡ `SYN_SENT` ngắn. Dùng counters/rates cho connects/errors và sampling OS với chu kỳ phù hợp tải. Với sự cố ngắn, JFR, trace, packet capture theo chính sách bảo mật hoặc network observability có thể hữu ích; **packet capture có thể chứa dữ liệu nhạy cảm**, phải giới hạn và kiểm soát truy cập.

## 16. Quy trình điều tra từ triệu chứng đến kết luận

### Tình huống A — `Too many open files` lúc mở kết nối mới

1. Lấy PID đúng và soft/hard NOFILE của process.
2. Đo `open_fd` của JVM, trend, loại FD qua `lsof` hoặc `/proc/PID/fd`.
3. Đếm TCP sockets theo state và role; không chỉ nhìn ESTABLISHED.
4. So app active/accepted/closed; tìm sockets quên đóng, file log, selector/pipe hoặc pool không release.
5. Xử lý nguồn rò rỉ/giới hạn concurrency; chỉ nâng NOFILE khi capacity planning xác nhận có dư memory/CPU.
6. Kiểm thử lại sau steady load, đảm bảo FD trở về baseline sau khi kết nối đóng.

### Tình huống B — `CLOSE_WAIT` tăng sau khi mobile users mất mạng

Peer chủ động FIN, ứng dụng chưa hoàn tất đóng. Nghi handlers giữ `InputStream`, connection pool không release response hoặc callback bỏ qua close. Kiểm tra process PID của sockets, lifecycle code và metrics `closed_total`. Dùng `try-with-resources`, close trong `finally` và đảm bảo cancellation/timeout cũng cleanup. Không xóa CLOSE_WAIT bằng cách tăng `somaxconn`.

### Tình huống C — `TIME_WAIT` nhiều sau mỗi lần scale deployment

Các clients liên tục tạo TCP connections mới tới cùng upstream. So connect attempts/s, retries, pool reuse, DNS/proxy routing, TIME_WAIT distribution. Nếu `open_fd` không cao nhưng outbound connect fails, nghi ephemeral port/NAT constraints hoặc retry storms. Sửa pooling/backoff và session reuse trước khi chỉnh kernel tuning.

### Tình huống D — Chỉ một HTTP route timeout, TCP ESTABLISHED bình thường

Requests đến được server, socket đủ, nhưng route bị kẹt ở DB/lock/upstream service. TCP states ít giúp tìm nguyên nhân; tập trung `request_duration`, `executor_queued_tasks`, active workers, thread dumps và dependency latency. Không thêm FDs hay đổi port range khi nút cổ chai nằm trong business logic.

### Tình huống E — Proxy báo 502/504, Java active=0

Đừng vội kết luận app không nhận request. Có thể proxy timeout/connect failure xảy ra **trước** khi request tới handler, hoặc metric được lấy ở instance/PID khác. So proxy access/upstream metrics, target endpoints, readiness, `LISTEN`, accept errors, network namespace và timestamps. Nếu app được restart giữa hai lần đo, cumulative counters đã reset.

### Tình huống F — Server thấy 1.000 ESTABLISHED nhưng 20 active HTTP requests

Có thể 980 idle keep-alive connections, các WebSocket sessions, hoặc HTTP/2 multiplex. Hãy đo pool idle/active, thời gian giữ kết nối, OS owner socket và protocol. Không gọi 980 kết nối còn lại là leak cho tới khi xác nhận chúng đáng lẽ đã close.

### Tình huống G — Nâng `ulimit -n` trong terminal nhưng service vẫn lỗi

Nếu service do systemd hoặc container chạy, shell interactive `ulimit` không thay đổi limit của process đã chạy. Kiểm tra `/proc/<JVM_PID>/limits`/service manager/runtime; thay cấu hình launch đúng chỗ, restart một cách kiểm soát và đo lại. Không làm chuyện đổi limit trong production mà không có rollback/capacity check.

### Tình huống H — Windows app có 12.000 handles nhưng chỉ 800 TCP connections

`HandleCount` gồm nhiều object types; nó không phải số TCP endpoints. Dùng `Get-NetTCPConnection -OwningProcess` để lọc TCP state và owner, kết hợp Windows performance/debugging tools phù hợp. Không áp một Unix `RLIMIT_NOFILE` giả định lên Windows.

### Tình huống I — JVM heap ổn, host bị memory pressure

Kiểm tra direct/mapped buffers, thread stacks, JVM native memory, page cache, kernel socket memory, cgroup accounting và lượng buffers/queues. `BufferPoolMXBean` không bao trùm toàn bộ native/kernel memory; phải đối chiếu process RSS/container working set và OS counters.

### Tình huống J — Server `LISTEN` nhưng không nhận connection burst

Kiểm tra acceptor scheduling, FD limit, executor saturation, listen queue, SYN backlog, proxy/NAT và listen drops. `backlog=128` là hint/sự giới hạn chờ connect, không phải max active sessions; tăng backlog có thể hữu ích sau khi chứng minh burst thực tế, nhưng không sửa một accept loop đang deadlock.

## 17. Bài tập kiến thức và lời giải

### Bài 1 — App active bằng 50, OS thấy 100 ESTABLISHED

Cùng một JVM vừa mở 50 outbound loopback client sockets vừa accept 50 inbound sockets. `active_server_connections=50` có sai không?

**Đáp án:** không nhất thiết. Mỗi TCP connection có **hai endpoints**, và cùng JVM sở hữu cả hai phía nên OS có thể liệt kê khoảng 100 established endpoints; server-side gauge chỉ đếm accepted side. Còn listener và FDs không phải TCP có thể làm process open FD lớn hơn nữa.

### Bài 2 — Counter accept tăng mãi, active không tăng

`net_accept_total` từ 1 triệu lên 2 triệu trong một ngày, nhưng `net_active_server_connections` luôn khoảng 200.

**Đáp án:** đây có thể hoàn toàn bình thường. Counter là **tổng số lượt accept qua thời gian**, gauge là **số connections đang mở** tại một thời điểm. Đo rate và close counts, không so hai số tuyệt đối.

### Bài 3 — `CLOSE_WAIT` tăng, TIME_WAIT thấp

Tại cùng một JVM, CLOSE_WAIT tăng từ 10 lên 1.000 sau khi clients disconnect, app active gauge không giảm.

**Đáp án:** nghi đường close/cleanup chưa chạy hoặc gauge sai; xác minh process owner, stack traces và resource lifecycle. Không kết luận chắc chắn chỉ từ hai số, nhưng đây là tín hiệu mạnh phải kiểm tra `Socket.close()`/`try-with-resources`.

### Bài 4 — `TIME_WAIT` 20.000, open_fd chỉ 300

Có thể các con số này cùng đúng không?

**Đáp án:** có. Nhiều TIME_WAIT entries có thể tồn tại trong kernel sau khi process đã đóng FDs; hoặc thuộc processes khác trong namespace. `ss -s` aggregate không phải per-PID FD count. Tìm churn/active close và scope mismatch.

### Bài 5 — `ulimit -n` = 65535, Java PID có soft 1024

Tại sao ứng dụng vẫn nhận “Too many open files”?

**Đáp án:** shell bạn kiểm tra và process Java có launch context khác nhau. Giới hạn thực là của PID; kiểm tra `/proc/PID/limits` và systemd/container runtime. Đừng tin shell `ulimit` như metric JVM.

### Bài 6 — `somaxconn` tăng, nhưng DB queue vẫn cao

Tại sao tăng accept backlog không làm request nhanh hơn?

**Đáp án:** backlog chỉ tác động hàng chờ kết nối, trong khi bottleneck ở business logic/DB/executor. Phải đo request/queue duration, dependency latency và concurrency trước khi thay kernel tuning.

### Bài 7 — Outbound port range 30.000 ports

Điều đó có nghĩa server có tối đa 30.000 inbound clients?

**Đáp án:** không. Ephemeral local port range ảnh hưởng chọn local port cho outbound connections và tuple reuse; inbound server trên một listener port vẫn phục vụ nhiều remote tuples. Giới hạn thực tế còn có FDs, CPU, RAM, broker, queues và network.

### Bài 8 — Windows `HandleCount` và Unix FD

Có thể chuẩn hóa HandleCount trên Windows thành cùng metric `jvm_fd_open` của Linux và đặt alert 90% NOFILE không?

**Đáp án:** không nếu không định nghĩa đúng. Windows handles và Unix FDs khác loại/limits; phân biệt metric source/platform và dùng OS-specific capacity/diagnostics.

### Bài 9 — Cùng server có WebSocket và REST

Metric `http_requests_in_flight=0` trong khi `ss` cho 5.000 ESTABLISHED. Có lỗi không?

**Đáp án:** không nhất thiết. WebSocket có thể giữ kết nối lâu dù không có request HTTP nào đang xử lý, và keep-alive sockets cũng có thể rảnh. Cần metric active WebSocket sessions/idle pools riêng.

### Bài 10 — FD usage không tăng nhưng connect timeout tăng

Những lớp nào cần kiểm tra tiếp?

**Đáp án:** DNS, routing/firewall, peer SYN backlog/accept queue, outbound ephemeral ports/NAT, TLS handshake, proxy, upstream service và rate limiter. Process FD thấp không loại trừ network path errors hoặc TIME_WAIT churn.

### Bài 11 — Thấy hai giá trị khác nhau cách nhau 20 giây

App gauge 100 lúc 10:00:00; `ss` báo 400 lúc 10:00:20, server vừa nhận burst 2.000 connections.

**Đáp án:** có thể là lệch sampling hoặc scopes. Chụp lại cùng thời điểm với PID/ports/role, ghi cả rate và workload burst; không khẳng định gauge instrument sai chỉ từ hai snapshots khác thời gian.

### Bài 12 — JVM RSS tăng nhưng direct buffer MXBean ổn

Có thể vẫn là native/kernel memory vấn đề?

**Đáp án:** có. Thread stacks, native libraries, memory mapping, allocator overhead và kernel socket buffers không nhất thiết đi vào cùng BufferPoolMXBean. Xem OS/cgroup memory, NMT nếu bật và socket memory metrics.

## 18. Checklist điều tra và chuẩn hóa quan sát

- [ ] Tôi đã xác định **đúng PID/instance/container**, thời điểm, IP/port, IPv4/IPv6 và hướng inbound/outbound?
- [ ] Tôi phân biệt counter, gauge và histogram; không so total với instantaneous?
- [ ] Metric active server connections được tăng/giảm theo **socket lifecycle**, không nhầm với active HTTP requests?
- [ ] Tôi hiểu HTTP keep-alive/HTTP2/WebSocket khiến số requests không bằng số sockets?
- [ ] Tôi đã kiểm tra `LISTEN`, `ESTABLISHED`, `CLOSE_WAIT`, `TIME_WAIT` và phạm vi đếm?
- [ ] Tôi biết `CLOSE_WAIT` có thể gợi ý leak khi tăng kéo dài, còn `TIME_WAIT` thường phản ánh churn?
- [ ] Tôi đã xem process open FDs và **process soft/hard limits**, không chỉ shell `ulimit`?
- [ ] Nếu đang trên Windows, tôi dùng Windows handle/TCP tooling thay vì giả định Unix FDs?
- [ ] Tôi đã phân loại FDs là TCP sockets, logs, pipes, files hoặc loại khác?
- [ ] Tôi không coi `ss -s`/kernel counters namespace-wide là metric riêng cho PID?
- [ ] Tôi đã xem accept queue, SYN backlog, connect/accept errors và thread scheduling khi connect chậm?
- [ ] Tôi phân biệt ephemeral port range (outbound) và inbound connection capacity?
- [ ] Tôi đã xem retries, connection pooling, TIME_WAIT và NAT/proxy limits khi outbound connect fail?
- [ ] Tôi đã xem direct buffers, JVM threads, GC và OS socket memory khi heap không giải thích RSS?
- [ ] Tôi lấy snapshots trong cùng thời gian và biết instance có restart/counters reset?
- [ ] Tôi tránh metric labels cardinality cao như user ID, IP và socket four-tuple?
- [ ] Tôi có error rate, queue depth, latency p95/p99 và active gauges cùng OS resource metrics?
- [ ] Tôi chỉ tăng kernel/process limits sau khi xác định root cause và capacity planning?
- [ ] Tôi biết cách tái hiện bằng load test, đánh giá baseline sau khi ngừng traffic và kiểm tra leak?
- [ ] Tôi biết phân biệt proxy/LB/host/container/process và không đổ lỗi sai tầng?

**Kết luận:** Để quan sát Java networking đáng tin cậy, hãy đọc **ba lớp cùng lúc**: (1) **ứng dụng** với accept/close/active requests, pools, queues, errors và latency; (2) **JVM process** với thread/heap/direct buffers/open file descriptors; (3) **hệ điều hành** với TCP states, backlog, ephemeral ports, socket buffers và resource limits. Không có đẳng thức đơn giản “active requests = ESTABLISHED = FDs”. Một chênh lệch chỉ có ý nghĩa khi xác định đúng **PID, hướng kết nối, socket ownership, protocol, container namespace và thời điểm**. Kết luận sau khi ghép **trend + scope + trạng thái + lỗi** sẽ tránh tăng limits sai chỗ và giúp tìm socket leak, client churn hoặc backlog bottleneck chính xác hơn.

## 19. Tài liệu tham khảo

- **Oracle Java 17 — ManagementFactory:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- **Oracle Java 17 — UnixOperatingSystemMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html
- **Oracle Java 17 — BufferPoolMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- **Oracle Java 17 — ServerSocket:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Oracle Java 17 — Socket:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- **Linux manual — ss(8):** https://man7.org/linux/man-pages/man8/ss.8.html
- **Linux manual — proc_pid_limits(5):** https://man7.org/linux/man-pages/man5/proc_pid_limits.5.html
- **Microsoft Learn — Get-NetTCPConnection:** https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection
- **Prometheus — Metric and label naming:** https://prometheus.io/docs/practices/naming/

Những giá trị OS limit/counter phụ thuộc bản phân phối/kernel, JVM và cách deploy (VM, container, systemd, Windows service). Khi áp dụng, hãy kiểm tra documentation phiên bản thực tế và đừng lấy số từ một máy lab làm ngưỡng chung cho production.