# Kiểm tra mức dùng native memory, file descriptor và socket

## 1. Vì sao phải theo dõi ngoài Java heap?

Trong production, process Java sử dụng nhiều tài nguyên ngoài heap. Ứng dụng có thể gặp sự cố dù heap vẫn còn nhiều dung lượng: native memory tăng, số file descriptor chạm giới hạn, socket không được đóng, thread không tạo thêm được hoặc container bị OOM kill.

Ba nhóm cần quan sát thường xuyên:

- **Native memory**: bộ nhớ JVM và thư viện native sử dụng ngoài Java heap, gồm thread stack của platform thread, metaspace, code cache, cấu trúc GC, direct buffer, memory mapping và vùng do JNI/JNA hoặc thư viện native cấp phát.
- **File descriptor (FD)**: handle cấp hệ điều hành mà process dùng cho file, socket, pipe, event descriptor và các tài nguyên tương tự trên Unix-like OS.
- **Socket**: kết nối TCP/UDP mà ứng dụng dùng để phục vụ request, gọi database, HTTP service, message broker hoặc hệ thống khác.

Nếu chỉ xem `-Xmx`, heap graph hoặc `MemoryMXBean`, bạn sẽ bỏ sót một phần đáng kể footprint và giới hạn vận hành của process. Cần kết hợp JVM metrics với số liệu process, container và hệ điều hành.

## 2. Phân biệt heap, native memory, RSS và container memory

Các số liệu bộ nhớ thường được gọi chung là “memory usage”, nhưng chúng biểu thị các phạm vi khác nhau.

| Chỉ số | Ý nghĩa | Nguồn quan sát |
|---|---|---|
| Java heap used | Bộ nhớ heap đang được object sử dụng | `MemoryMXBean`, GC log, JFR |
| Java heap committed | Heap JVM đã commit để sử dụng | `MemoryMXBean`, GC log |
| Native memory | Bộ nhớ ngoài heap do JVM hoặc native code sử dụng | NMT, MXBean chuyên biệt, OS |
| Virtual size / VSZ | Không gian địa chỉ ảo process đã map/reserve | OS process metrics |
| RSS | Các trang bộ nhớ hiện đang resident trong RAM của process | `/proc/<pid>/status`, `ps`, container metrics |
| Container memory | Bộ nhớ được cgroup tính cho container | cgroup `memory.current`, `memory.stat` |

`-Xmx` chỉ giới hạn Java heap tối đa. Nó không phải giới hạn tổng bộ nhớ process. Một JVM còn cần metaspace, code cache, thread stack, direct buffer, GC structures, native library, socket buffer và các vùng memory mapping.

RSS cũng không bằng tổng native memory. RSS có thể gồm trang heap, native pages, shared libraries và mapped pages đang resident; trong khi một phần vùng đã reserve/commit có thể chưa resident. Container memory có thể tính thêm page cache và một số bộ nhớ kernel được charge cho cgroup. Vì vậy không cộng hoặc so sánh các số này như thể chúng cùng một đơn vị phạm vi.

Một dấu hiệu cần điều tra là heap sau GC tương đối ổn định nhưng RSS hoặc container memory vẫn tăng liên tục. Khi đó hãy kiểm tra native allocation, direct/mapped buffer, thread, file descriptor, socket và thư viện native.

## 3. Native memory trong một JVM Java 21 gồm những gì?

Native memory có nhiều nguồn:

| Nguồn | Ví dụ | Cách quan sát |
|---|---|---|
| Thread stack | Stack của platform thread và carrier thread | NMT `Thread`, OS thread count, process RSS |
| Metaspace | Class metadata | NMT `Class`, `MemoryPoolMXBean`, class loading metrics |
| Code cache | Native code do JIT compiler tạo | NMT `Code`, code heap metrics |
| GC structures | Metadata và cấu trúc nội bộ của collector | NMT `GC`, GC log/JFR |
| Direct buffer | `ByteBuffer.allocateDirect`, network I/O buffers | `BufferPoolMXBean`, NMT/OS tùy allocation path |
| Memory mapping | File được map vào address space | Buffer pool `mapped`, OS mapping metrics |
| JNI/JNA/native library | Compression, crypto, database driver, native transport | Native library metrics, OS tools, vendor diagnostics |
| Socket/file resources | Socket, file, pipe và handle của process | FD count, `/proc`, `lsof`, `ss` |

Với virtual thread trong Java 21, không có một native OS thread stack riêng cho từng virtual thread. Virtual thread được mount lên platform thread (carrier) khi chạy; stack state của virtual thread được quản lý theo mô hình runtime của JVM. Do đó, không suy số native thread stack bằng số virtual thread. Vẫn cần theo dõi platform/carrier thread và memory mà ứng dụng cấp phát cho task.

## 4. Bật Native Memory Tracking (NMT)

Native Memory Tracking là công cụ của HotSpot JVM để theo dõi các vùng native memory mà JVM quản lý. NMT không bật mặc định; phải chọn mức theo dõi khi khởi động JVM.

### 4.1. Chế độ summary

Với phần lớn môi trường production cần giám sát tổng quan, có thể bắt đầu bằng:

```bash
java -XX:NativeMemoryTracking=summary -jar application.jar
```

`summary` theo dõi mức sử dụng theo các nhóm lớn như Java Heap, Class, Thread, Code, GC, Compiler, Internal và các nhóm JVM khác. Chế độ này phù hợp để theo dõi xu hướng và xác định category nào tăng.

### 4.2. Chế độ detail

Khi cần điều tra sâu hơn, có thể chạy JVM với:

```bash
java -XX:NativeMemoryTracking=detail -jar application.jar
```

`detail` thu thập thêm thông tin call site cho các allocation mà NMT theo dõi. Nó có overhead lớn hơn summary; hãy đánh giá chi phí trong staging hoặc một canary trước khi bật diện rộng.

NMT phải được bật từ lúc JVM khởi động. Không thể bật nó cho một JVM đang chạy bằng `jcmd` nếu trước đó JVM đã khởi động với NMT tắt. Nếu cần NMT trong production, hãy đưa flag vào startup configuration của release.

NMT có overhead về CPU và bộ nhớ. Mức ảnh hưởng phụ thuộc workload và chế độ tracking; detail thường tốn kém hơn summary. Đừng bật detail vĩnh viễn trên mọi instance mà không đo chi phí.

## 5. Đọc số liệu NMT bằng `jcmd`

Khi JVM đã khởi động với NMT, có thể xem summary:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

Output hiển thị các nhóm memory, trong đó thường có `reserved` và `committed`:

- **Reserved**: vùng địa chỉ ảo JVM đã reserve cho mục đích sử dụng.
- **Committed**: phần vùng đã commit để JVM có thể sử dụng; không đồng nghĩa toàn bộ phần này đang resident trong RAM.

Không coi `reserved` là RAM đang dùng. Cũng không coi `committed` bằng RSS.

### 5.1. Lấy baseline và so sánh mức tăng

Để biết category nào tăng trong một khoảng thời gian, lấy baseline sau khi ứng dụng khởi động và đạt trạng thái ổn định:

```bash
jcmd <pid> VM.native_memory baseline
```

Sau khi chạy workload hoặc đợi một khoảng thời gian, lấy chênh lệch:

```bash
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Nếu JVM được khởi động với `detail`, có thể lấy chi tiết chênh lệch:

```bash
jcmd <pid> VM.native_memory detail.diff scale=MB
```

Lặp lại các snapshot theo cùng chu kỳ tải để xem xu hướng. Một category tăng trong lúc warm-up không nhất thiết là leak; cần kiểm tra xem sau khi workload ổn định, mức sử dụng có tiếp tục tăng không.

### 5.2. NMT có giới hạn

NMT tập trung vào memory allocation nội bộ mà HotSpot theo dõi. Nó không phải công cụ kiểm kê toàn bộ native memory của process; allocation do JNI/JNA hoặc thư viện native bên thứ ba có thể không xuất hiện đầy đủ trong báo cáo. Một số tài nguyên JDK/class library cũng cần được theo dõi bằng MXBean chuyên biệt hoặc công cụ hệ điều hành.

Vì vậy, nếu RSS tăng nhưng NMT summary không giải thích được, đừng kết luận số liệu OS sai. Hãy kiểm tra direct/mapped buffer, native library, memory mapping, allocator riêng và cgroup metrics. NMT là một nguồn bằng chứng, không phải nguồn duy nhất.

## 6. Theo dõi direct buffer và mapped buffer bằng MXBean

NIO cung cấp `BufferPoolMXBean` để quan sát các buffer pool như `direct` và `mapped`. Có thể lấy số lượng buffer, tổng capacity và memory được ước lượng đang sử dụng.

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

static void printBufferPools() {
    for (BufferPoolMXBean pool :
            ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
        System.out.printf(
                "%s: count=%d, used=%d bytes, capacity=%d bytes%n",
                pool.getName(),
                pool.getCount(),
                pool.getMemoryUsed(),
                pool.getTotalCapacity());
    }
}
```

Ý nghĩa:

- `getCount()`: số buffer trong pool.
- `getMemoryUsed()`: lượng memory ước tính pool đang sử dụng.
- `getTotalCapacity()`: tổng capacity của các buffer trong pool.

Các giá trị này hữu ích để nhận ra direct/mapped buffer tăng theo thời gian. Chúng không phải tổng native memory của JVM và không bao gồm mọi allocation của native library.

Nếu `direct` pool tăng liên tục, kiểm tra vòng đời `ByteBuffer.allocateDirect`, network framework, database driver và buffer cache. Nếu `mapped` tăng, kiểm tra số file mapping và vòng đời của các tác vụ xử lý file. Đảm bảo code đóng resource owner tương ứng và không giữ buffer/reference lâu hơn yêu cầu.

## 7. Đo file descriptor trong Java

Trên các hệ điều hành Unix-like, JDK cung cấp `com.sun.management.UnixOperatingSystemMXBean` với số FD đang mở và giới hạn FD tối đa của process.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import com.sun.management.UnixOperatingSystemMXBean;

static void printFileDescriptorUsage() {
    OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();
    if (os instanceof UnixOperatingSystemMXBean unix) {
        long open = unix.getOpenFileDescriptorCount();
        long max = unix.getMaxFileDescriptorCount();
        double ratio = max > 0 ? (double) open / max : Double.NaN;

        System.out.printf(
                "openFD=%d, maxFD=%d, usage=%.1f%%%n",
                open, max, ratio * 100.0);
    }
}
```

Interface này dành cho nền tảng Unix-like; không giả định nó có trên Windows. Nếu ứng dụng được đóng gói bằng custom runtime image (`jlink`), cần bảo đảm module `jdk.management` có mặt nếu code sử dụng MXBean này.

Đưa open FD count và tỷ lệ so với max vào metrics. Cảnh báo khi mức dùng tăng bất thường hoặc tiến gần giới hạn, nhưng chọn threshold theo workload và burst behavior của service. Không đợi tới 100% mới cảnh báo.

## 8. Kiểm tra FD của process trên Linux

Trên Linux, mỗi FD của process xuất hiện như một symbolic link trong `/proc/<pid>/fd`.

Đếm FD đang mở:

```bash
find /proc/<pid>/fd -maxdepth 1 -type l | wc -l
```

Liệt kê đích của từng FD:

```bash
ls -l /proc/<pid>/fd
```

Xem giới hạn FD mà process thực sự nhận:

```bash
grep -i "Max open files" /proc/<pid>/limits
```

Đây là nguồn đáng tin cậy hơn việc chỉ chạy `ulimit -n` trong terminal hiện tại, vì shell của operator có thể có limit khác process service. Nếu service chạy qua systemd, container runtime hoặc Kubernetes, kiểm tra cả cấu hình giới hạn ở tầng khởi chạy.

Có thể dùng `lsof` để phân loại FD:

```bash
lsof -nP -p <pid>
lsof -nP -a -p <pid> -i
```

Lệnh thứ hai tập trung vào network sockets. Cần quyền phù hợp để thấy đầy đủ thông tin process. Không chạy `lsof` liên tục ở tần suất cao trên process rất lớn; đây là công cụ điều tra, còn metrics nhẹ nên dùng cho giám sát thường xuyên.

### 8.1. Giới hạn FD ở các tầng khác nhau

Trên Linux, cần phân biệt:

- **Per-process soft/hard limit**: giới hạn `RLIMIT_NOFILE` mà process được cấp.
- **System-wide file table**: giới hạn tổng thể ở kernel, có thể xem qua `/proc/sys/fs/file-max` và `/proc/sys/fs/file-nr`.
- **Container/service configuration**: limit được truyền vào process khi container hoặc service khởi chạy.

Ví dụ kiểm tra systemd service:

```bash
systemctl show my-java-service -p LimitNOFILE
```

Thay `my-java-service` bằng unit thực tế. Thay đổi limit ở shell sau khi process đã chạy không tự động thay đổi limit của process đó; cần cập nhật cấu hình service/container và restart theo quy trình vận hành.

Tăng `nofile` chỉ giải quyết giới hạn nếu ứng dụng cần hợp lệ nhiều FD hơn và kernel/system capacity cho phép. Nó không sửa được leak do stream, socket hoặc file không được đóng.

## 9. Kiểm tra socket và trạng thái TCP

Socket là một loại FD trên Unix-like OS. Theo dõi socket giúp phân biệt connection pool bình thường với connection leak hoặc vấn đề mạng.

Trên Linux, xem TCP socket của process:

```bash
ss -tanp
```

Có thể lọc theo PID trong output hoặc dùng `lsof`:

```bash
lsof -nP -a -p <pid> -iTCP
```

Xem thống kê tổng quan TCP:

```bash
ss -s
```

Các trạng thái thường gặp:

| TCP state | Ý nghĩa khái quát | Điều cần xem |
|---|---|---|
| `LISTEN` | Socket đang chờ kết nối đến | Số listener có đúng cấu hình server không |
| `ESTAB` | Kết nối đã thiết lập | Có tương ứng với connection pool và traffic dự kiến không |
| `SYN-SENT` | Client đang chờ SYN-ACK | Remote endpoint, routing, firewall hoặc connect backlog |
| `CLOSE-WAIT` | Remote đã đóng phía gửi; local endpoint chưa đóng socket | Code có đọc/đóng response body và socket đúng cách không |
| `TIME-WAIT` | TCP giữ trạng thái sau khi một phía chủ động đóng | Connection churn, tốc độ tạo kết nối và ephemeral port |
| `FIN-WAIT-1/2` | Local đang trong quá trình đóng kết nối | Peer có hoàn tất đóng kết nối không |

Không phải trạng thái nào xuất hiện nhiều cũng là leak. Nhiều `ESTAB` có thể là HTTP keep-alive hoặc connection pool hoạt động đúng. `TIME-WAIT` thường là trạng thái TCP bình thường sau khi đóng kết nối; số lượng cao có thể phản ánh connection churn nhưng không đồng nghĩa process vẫn giữ FD cho từng socket đó.

`CLOSE-WAIT` tăng liên tục thường là dấu hiệu đáng chú ý: peer đã gửi FIN nhưng ứng dụng local chưa đóng socket. Kiểm tra stream, response body, connection pool, callback và đường exception/cancellation có bỏ qua cleanup không.

## 10. Kiểm tra ephemeral port và connection churn

Client tạo quá nhiều outbound connection ngắn hạn có thể làm tăng `TIME-WAIT`, gây áp lực lên ephemeral port và NAT/conntrack. Hãy kiểm tra số kết nối theo destination, tốc độ tạo/đóng connection và chính sách reuse của HTTP/database client.

Trên Linux, xem dải ephemeral port:

```bash
cat /proc/sys/net/ipv4/ip_local_port_range
```

Khi nghi ngờ, đối chiếu:

- Số socket theo trạng thái và remote destination bằng `ss`.
- Số FD mở của process.
- Connection pool metrics của HTTP client, JDBC pool và message client.
- Connect timeout, retry rate và lỗi `BindException`/`ConnectException`.
- NAT gateway hoặc conntrack metrics nếu hệ thống đi qua NAT.

Một lượng lớn `TIME-WAIT` thường phản ánh nhiều connection được đóng gần đây. Tránh áp dụng kernel TCP tuning tùy tiện để che triệu chứng; trước tiên hãy tái sử dụng client/connection pool hợp lý, giới hạn concurrency và xác định lý do connection bị tạo mới liên tục.

## 11. Quan sát memory và FD ở cấp container

Trong container Linux sử dụng cgroup v2, có thể đọc một số file dưới cgroup filesystem:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
```

`memory.current` cho biết memory đang được charge cho cgroup; `memory.max` là giới hạn nếu được cấu hình; `memory.stat` cung cấp phân rã theo loại memory; `memory.events` ghi nhận các sự kiện như vượt ngưỡng hoặc OOM. Đường dẫn và quyền đọc phụ thuộc container runtime, cgroup namespace và cấu hình host.

Container memory không đồng nhất với Java heap hoặc RSS của một process duy nhất. Nếu container chứa sidecar hoặc nhiều process, số liệu cgroup là tổng của các thành phần được charge vào cgroup đó. Hãy kết hợp process metrics với cgroup metrics để xác định đúng process gây tăng.

Với Docker, `docker stats` hữu ích để quan sát nhanh mức sử dụng container. Trong Kubernetes, xem container memory usage, limit, restart/OOMKilled và node pressure qua metrics của cluster. Không dùng một snapshot duy nhất để kết luận leak; hãy xem xu hướng và sự kiện OOM theo thời gian.

## 12. Dấu hiệu và cách phân loại sự cố

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Heap sau GC ổn định nhưng RSS tăng | Native allocation, direct/mapped buffer, thread stack, JNI/JNA hoặc mapping |
| NMT `Thread` tăng cùng platform thread count | Thread tạo không giới hạn, executor không được đóng hoặc thread pool cấu hình sai |
| NMT `Class`/metaspace tăng liên tục | Classloader leak, dynamic class generation hoặc class không được unload |
| Direct buffer pool tăng | Buffer được giữ lâu, network client hoặc direct buffer lifecycle |
| FD count tăng liên tục | File/socket/pipe/stream không đóng hoặc tạo resource không giới hạn |
| Nhiều `CLOSE-WAIT` | Local socket chưa đóng sau khi peer đóng |
| Nhiều `TIME-WAIT` | Connection churn; kiểm tra connection reuse và ephemeral port |
| `Too many open files` | Process FD limit hoặc system file table đã chạm ngưỡng |
| `unable to create native thread` | Native memory, OS thread limit, PID/cgroup limit hoặc process limit |
| `OutOfMemoryError: Direct buffer memory` | Direct buffer memory pressure hoặc giới hạn direct memory |
| Container OOMKilled dù heap chưa đầy | Native/RSS/page cache/kernel charge hoặc tổng memory của nhiều process vượt cgroup limit |

Không gán nguyên nhân chỉ từ một exception. Ví dụ `unable to create native thread` có thể do thiếu native memory hoặc giới hạn số process/thread của container; phải kiểm tra `pids.max`, process limits, thread count và RSS.

## 13. Những nguồn leak phổ biến trong ứng dụng Java

### 13.1. File và stream không được đóng

Luôn đóng `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel` và resource tương ứng bằng try-with-resources:

```java
try (InputStream input = Files.newInputStream(path);
     OutputStream output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
```

Nếu code return sớm hoặc ném exception, try-with-resources vẫn gọi `close()`. Với stream được thư viện trả về, đọc API contract để biết ai sở hữu và ai phải đóng.

### 13.2. HTTP response body và client

Nếu dùng body handler streaming như `BodyHandlers.ofInputStream()` hoặc `ofLines()`, caller phải đóng stream sau khi đọc xong hoặc dừng sớm. Client dùng chung nên được quản lý theo lifecycle service; không tạo/đóng client sau mỗi request. Với executor do ứng dụng truyền vào `HttpClient`, chủ sở hữu executor cần đóng nó đúng lifecycle.

### 13.3. JDBC và connection pool

Đóng `Connection`, `Statement` và `ResultSet` đúng cách. Connection pool có thể giữ một số socket mở để tái sử dụng; đó là hành vi bình thường. Cần theo dõi active/idle/pending connection, acquisition latency và leak detection của pool thay vì đóng socket thủ công.

### 13.4. Thread và executor

Tránh tạo thread/executor mới cho từng request mà không có giới hạn và lifecycle. Dùng executor có chủ sở hữu rõ ràng, shutdown khi thành phần dừng và có chính sách chờ/cancel. Virtual thread giúp tạo nhiều task blocking I/O, nhưng không loại bỏ giới hạn FD, socket, direct memory hoặc connection downstream.

### 13.5. Native resource

Thư viện JNI/JNA hoặc native transport có thể cấp phát memory và resource ngoài phạm vi NMT. Dùng API close/dispose do thư viện cung cấp, kiểm tra release note và metrics riêng của thư viện. Không gọi `System.gc()` như một cách giải phóng native resource có tính xác định; GC không thay thế ownership và cleanup rõ ràng.

## 14. Quy trình điều tra production

Khi RSS, FD hoặc socket tăng bất thường, có thể theo trình tự:

1. **Xác định process/container**: PID, image digest, JDK build, thời điểm khởi động và node đang chạy.
2. **Ghi baseline**: heap used/committed, RSS, cgroup memory, NMT summary nếu bật, FD count, socket state và thread count.
3. **Đo xu hướng**: lấy snapshot cách nhau một khoảng thời gian trong cùng loại workload; phân biệt warm-up/burst với tăng liên tục.
4. **Phân loại memory**: heap, NMT category, direct/mapped buffer, RSS và cgroup usage.
5. **Phân loại FD**: file, pipe, socket, event descriptor; kiểm tra process limit và system limit.
6. **Phân loại socket**: local/remote address, port, TCP state, connection age và owner/pool.
7. **Đối chiếu application metrics**: HTTP/JDBC pool, pending request, stream lifecycle, executor, retry và timeout.
8. **Thu thập thêm bằng chứng**: `jcmd VM.native_memory`, `lsof`, `ss`, JFR, log và tracing theo đúng mức cần thiết.
9. **Xác định ownership**: resource được tạo ở đâu, ai chịu trách nhiệm đóng, nhánh exception/cancel có cleanup không.
10. **Sửa và soak test**: xác minh số liệu trở về mức ổn định sau khi workload kết thúc và sau nhiều chu kỳ xử lý.

Khi có nguy cơ process chạm FD hoặc memory limit, ưu tiên giảm tải/giới hạn admission theo runbook và bảo vệ service. Đừng chạy nhiều lệnh scan nặng trên production đang quá tải; thu thập số liệu nhẹ trước, sau đó chọn công cụ điều tra phù hợp.

## 15. Thiết lập monitoring và alert

Nên có metric theo process/container và theo nhóm tài nguyên:

| Metric | Gợi ý cảnh báo |
|---|---|
| Process RSS và cgroup memory usage/limit | Tăng liên tục hoặc tiến gần memory limit |
| Heap after GC | Xu hướng tăng qua nhiều chu kỳ GC |
| NMT category diff | Category native tăng nhanh bất thường so với baseline |
| Direct/mapped buffer memory | Tăng không trở về mức ổn định sau workload |
| Open FD count / max FD | Tỷ lệ cao, tăng dốc hoặc gần process limit |
| Socket count theo state | `CLOSE-WAIT` tăng liên tục; connection churn bất thường |
| Platform thread count | Tăng vượt baseline hoặc gần PID/thread limit |
| Connection pool active/pending | Pool bão hòa kéo dài hoặc acquisition timeout |
| OOM/restart/FD exception | Có event `OOMKilled`, `Too many open files` hoặc native allocation failure |

Threshold cần dựa trên baseline, giới hạn process/container và tốc độ tăng. Dùng alert theo cả ngưỡng tuyệt đối lẫn rate of change để phát hiện sớm leak. Tránh alert chỉ dựa vào số socket `TIME-WAIT` mà không có bối cảnh connection churn.

## 16. Windows và hệ điều hành không có `/proc`

Các lệnh `/proc`, `lsof` và `ss` trong bài chủ yếu dành cho Linux. Trên Windows, có thể kiểm tra process handle và TCP connection bằng PowerShell:

```powershell
Get-Process -Id 12345 | Select-Object Id, HandleCount, WorkingSet64
Get-NetTCPConnection -OwningProcess 12345 | Group-Object State
```

`HandleCount` là tổng số handle của process, không phải số file descriptor Unix và cũng không chỉ đếm socket. `Get-NetTCPConnection` cung cấp connection TCP theo owning process. Với macOS/BSD, dùng công cụ hệ điều hành tương ứng như `lsof`, `netstat`/`sockstat` và process limits; cú pháp có thể khác Linux.

Trong Java, `UnixOperatingSystemMXBean` không phải API portable cho Windows. Nếu cần dashboard đa nền tảng, hãy dùng metrics abstraction có kiểm tra capability và bổ sung exporter/agent theo OS.

## 17. Checklist vận hành

Trước khi đưa service Java 21 vào production, xác nhận:

1. Heap limit được đặt dựa trên tổng memory budget, có headroom cho native memory và OS.
2. Đã quyết định có bật NMT summary/detail từ startup hay không và đã đánh giá overhead.
3. Có metrics direct/mapped buffer nếu ứng dụng sử dụng NIO hoặc network framework.
4. Có open FD count và max FD trên Unix-like OS.
5. Đã kiểm tra `RLIMIT_NOFILE` của process thực tế và system/container limits.
6. Có số socket theo state và connection pool metrics.
7. Có alert cho RSS/cgroup memory, FD saturation, `CLOSE-WAIT` growth và native allocation failures.
8. Các stream, file, socket, JDBC resource và native handle có owner/cleanup rõ ràng.
9. Đã soak test dưới workload đại diện và xác minh resource usage trở về vùng ổn định.
10. Runbook có cách lấy NMT, FD, socket và container snapshot mà không gây tải điều tra quá mức.

## 18. Tài liệu tham khảo chính thức

- [Java SE 21 Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html): sử dụng NMT để phân tích native memory của JVM.
- [Java SE 21 `jcmd` documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.native_memory` và các diagnostic command.
- [Java SE 21 API — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): quan sát direct/mapped buffer pool.
- [Java SE 21 API — `UnixOperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html): số FD đang mở và giới hạn FD trên Unix-like systems.
- [Java SE 21 API — `ManagementFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): truy cập platform MXBean.
- [Linux `proc_pid_fd(5)`](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html): danh sách FD của process trong `/proc`.
- [Linux `ss(8)`](https://man7.org/linux/man-pages/man8/ss.8.html): xem socket và TCP state.
- [Linux cgroup v2 documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html): memory controller và resource accounting.

Để kiểm tra mức dùng native memory, file descriptor và socket trong production, cần kết hợp NMT/MXBean của JVM với process, cgroup và OS metrics. NMT giúp tìm category native do HotSpot theo dõi; `BufferPoolMXBean` quan sát direct/mapped buffer; `UnixOperatingSystemMXBean`, `/proc`, `lsof` và `ss` giúp tìm FD cùng socket state. Hãy theo dõi xu hướng theo thời gian, xác định owner của resource và kiểm chứng cleanup dưới soak test; một snapshot hoặc một con số heap đơn lẻ không đủ để kết luận process đang an toàn.
