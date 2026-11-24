# RSS, heap, bộ nhớ ngoài heap và giới hạn container

## 1. Vì sao không thể chỉ nhìn Java heap?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để đánh giá thời gian khởi động, bộ nhớ, đóng gói container và vận hành. Khi so sánh bộ nhớ giữa ứng dụng JVM và native executable, một sai lầm thường gặp là lấy giá trị heap làm đại diện cho toàn bộ mức tiêu thụ RAM.

Heap chỉ là một phần của bộ nhớ tiến trình. Ứng dụng còn dùng bộ nhớ cho thread stack, runtime/GC, buffer trực tiếp, JNI hoặc native library, vùng code và dữ liệu của image, file được memory-map, socket buffer và các cấu trúc do kernel quản lý. Khi chạy trong container, cgroup còn tính bộ nhớ được charge cho page cache, kernel và các process khác cùng cgroup.

Do đó, cần phân biệt ba góc nhìn:

- **Heap:** bộ nhớ dành cho object Java do garbage collector quản lý.
- **Process memory:** các trang bộ nhớ của tiến trình đang resident trong RAM, thường đo bằng RSS/PSS.
- **Container memory:** lượng bộ nhớ được cgroup tính cho container và các process con, so với giới hạn container.

Ba con số này trả lời ba câu hỏi khác nhau. Native Image có Java heap riêng và không chạy trên HotSpot VM; giới hạn heap tối đa chỉ đặt trần cho Java heap, không đặt trần cho tổng RSS hoặc container memory. [GraalVM mô tả rõ giới hạn này trong tài liệu Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/).

Sau bài học, người học có thể:

1. Phân biệt runtime Java heap, image heap, off-heap/native memory, RSS, PSS và container memory.
2. Giải thích vì sao heap nhỏ không bảo đảm RSS hoặc cgroup usage nhỏ.
3. Đo RSS/PSS của process Linux và memory usage/limit của cgroup.
4. Đọc các metric bộ nhớ Spring Boot Actuator mà không nhầm chúng với RSS.
5. Đặt heap budget phù hợp với container limit và phần dự phòng cho native memory.
6. So sánh JVM và native trong cùng điều kiện workload, CPU, memory limit và thời gian đo.
7. Chẩn đoán OOM do Java heap, native allocation hoặc cgroup limit.
8. Ghi lại peak memory, trạng thái GC, latency và điều kiện benchmark để kết quả có thể tái lập.

> **Nguyên tắc:** đo heap để hiểu object allocation và GC; đo RSS/PSS để hiểu bộ nhớ resident của process; đo cgroup để biết container đang tiến gần giới hạn nào. Không thay thế một chỉ số bằng chỉ số khác.

## 2. Mô hình bộ nhớ của ứng dụng JVM và Native Image

### 2.1. Java heap lúc runtime

Java heap là vùng chứa object được tạo khi ứng dụng chạy. Garbage collector thu hồi object không còn reachable và có thể mở rộng/thu hẹp vùng heap theo chính sách của runtime.

Các chỉ số heap thường gặp:

- **Used:** lượng heap đang được object sử dụng tại thời điểm lấy mẫu.
- **Committed:** lượng heap runtime đã cấp hoặc bảo đảm có thể dùng cho allocation.
- **Max:** giới hạn heap tối đa mà runtime cho phép.
- **Young/old generation:** các vùng heap có vai trò khác nhau trong chính sách GC nếu collector đang dùng có generational layout.

Used thay đổi theo allocation và GC. Committed không nhất thiết bằng used, còn max là trần chứ không phải lượng RAM chắc chắn đã resident.

Ví dụ, một tiến trình có heap max 256 MiB, committed 160 MiB và used 70 MiB không có nghĩa tiến trình chỉ dùng 70 MiB RAM. RSS còn chứa các vùng khác và có thể chứa các trang heap đã commit/resident theo cách runtime quản lý.

### 2.2. Image heap và runtime Java heap trong Native Image

Native Image có hai khái niệm cần phân biệt:

- **Image heap:** object được tạo trong quá trình build, ví dụ static state của class được khởi tạo ở build time. Những object này được đưa vào image và trở thành trạng thái ban đầu của executable.
- **Runtime Java heap:** vùng heap được tạo khi native executable chạy, chứa object được cấp phát trong quá trình xử lý request và các công việc runtime khác.

Image heap không phải heap động được giới hạn bởi Xmx của ứng dụng. Dữ liệu image, code và các vùng được memory-map có thể góp vào RSS khi các trang tương ứng được truy cập. Kích thước file executable cũng không bằng RSS: file có thể chứa các trang chưa được nạp vào RAM, còn RSS chỉ tính các trang hiện đang resident.

Native Image không chạy trên Java HotSpot VM. Nó sử dụng runtime và memory manager của GraalVM; Serial GC là collector mặc định trong tài liệu hiện hành, còn collector và tùy chọn cụ thể phụ thuộc distribution, release và platform. [GraalVM Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/) và [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/) cho thấy image heap và code area được thống kê riêng trong output build.

### 2.3. Bộ nhớ ngoài heap và native memory

Trong bài này, **off-heap/native memory** là cách gọi chung cho những vùng bộ nhớ không nằm trong Java object heap được GC quản lý. Những nguồn thường gặp:

| Nguồn | Ví dụ | Dấu hiệu cần quan sát |
| --- | --- | --- |
| Thread stacks | Stack của từng platform thread | RSS tăng cùng số thread; thread count cao. |
| Direct buffers | ByteBuffer.allocateDirect, network buffer | Buffer pool tăng dù heap không tăng tương ứng. |
| JNI/native library | Driver, codec, compression, crypto hoặc thư viện C/C++ | RSS tăng trong khi heap tương đối ổn định; lỗi native allocation hoặc load library. |
| Runtime và GC structures | Metadata/runtime structures, GC bookkeeping | Có thể xuất hiện trong RSS nhưng không được tính như object heap. |
| Memory-mapped files | File, shared library, resource mapping | RssFile, Pss_File hoặc file cache thay đổi. |
| Socket/kernel buffers | TCP send/receive buffers và cấu trúc kernel | Cgroup usage có thể tăng mà process heap không đổi. |

Trên HotSpot, người vận hành thường quen với Metaspace, Code Cache và Native Memory Tracking. Không nên bê nguyên cách diễn giải đó sang Native Image: Native Image không có cùng mô hình HotSpot metaspace/JIT code cache. Hãy đo bằng công cụ và runtime thực tế, sau đó phân loại vùng bộ nhớ theo nguồn có thể quan sát được.

### 2.4. Bảng phân biệt nhanh

| Khái niệm | Phạm vi | Có phải tổng RAM container không? |
| --- | --- | --- |
| Heap used | Object đang dùng trong Java heap | Không |
| Heap committed | Heap runtime đã commit/cấp cho allocator | Không |
| Heap max | Trần Java heap | Không |
| Image heap | Object đã được chuẩn bị trong executable lúc build | Không |
| Off-heap/native memory | Buffer, stack, JNI, runtime và native allocations | Không, chỉ là một phần |
| RSS | Trang của process hiện resident trong RAM | Không |
| PSS | RSS có phân bổ tỷ lệ các trang shared | Không |
| Cgroup memory usage | Bộ nhớ được charge cho cgroup và descendants | Gần với góc nhìn giới hạn container nhất |

## 3. RSS, PSS và virtual memory

### 3.1. RSS là gì?

**Resident Set Size (RSS)** là lượng trang của một process hiện đang nằm trong RAM. Trên Linux, RSS thường được chia thành:

- RssAnon: trang anonymous, ví dụ heap, stack và anonymous mappings.
- RssFile: trang file-backed đang resident, ví dụ executable và shared libraries.
- RssShmem: trang shared memory, bao gồm một số mapping từ tmpfs.

Về khái niệm:

~~~text
RSS ≈ RssAnon + RssFile + RssShmem
~~~

RSS phù hợp để quan sát footprint của một process, nhưng có thể tính toàn bộ trang shared vào RSS của từng process. Vì vậy, cộng RSS của nhiều process có thể đếm trùng shared pages.

### 3.2. PSS là gì?

**Proportional Set Size (PSS)** chia chi phí trang shared theo số process cùng chia sẻ trang đó. Nếu hai process cùng map một trang shared, mỗi process được tính một nửa trang vào PSS.

PSS hữu ích khi so sánh footprint của nhiều process hoặc nhiều replica dùng chung library pages. Trên Linux, có thể đọc Pss trong /proc/<PID>/smaps_rollup. Kernel mô tả smaps_rollup là bản tổng hợp các trường từ toàn bộ memory mappings của process. [Linux proc filesystem documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html).

### 3.3. Virtual memory không phải RAM đang dùng

VmSize/virtual size phản ánh không gian địa chỉ được map hoặc reserve. Một process có thể reserve một vùng lớn nhưng chỉ chạm vào một phần nhỏ; khi đó RSS thấp hơn nhiều so với virtual size.

Không dùng VmSize để báo cáo memory footprint. Khi so sánh native/JVM, ghi RSS/PSS và container memory; chỉ dùng virtual size khi điều tra mapping hoặc address-space behavior.

### 3.4. Đọc thông tin process trên Linux

Tìm PID của ứng dụng, sau đó đọc:

~~~bash
cat /proc/<PID>/status
~~~

Các dòng thường cần xem:

~~~text
VmSize:      ...
VmRSS:       ...
VmHWM:       ...
RssAnon:     ...
RssFile:     ...
RssShmem:    ...
Threads:     ...
~~~

VmHWM là peak RSS high-water mark do kernel báo cáo. Các trường RSS trong status là số liệu xấp xỉ; khi cần phân tích chi tiết hơn, đọc:

~~~bash
cat /proc/<PID>/smaps_rollup
~~~

Các trường hữu ích gồm Rss, Pss, Private_Clean, Private_Dirty, Shared_Clean, Shared_Dirty, Anonymous và Swap. smaps_rollup tốn chi phí đọc hơn các counter đơn giản, nên không cần poll quá dày trong benchmark tải cao.

Có thể dùng ps hoặc pmap để quan sát nhanh:

~~~bash
ps -o pid,rss,vsz,comm -p <PID>
pmap -x <PID>
~~~

Đơn vị RSS của ps thường là KiB trên Linux. Ghi rõ đơn vị khi lưu kết quả.

## 4. Container memory và cgroup limits

### 4.1. Vì sao RSS không bằng container memory?

Container chạy trên Linux được giới hạn tài nguyên thông qua cgroups. Cgroup memory accounting có thể tính nhiều loại sử dụng:

- Anonymous memory và page cache.
- Kernel data structures như dentries, inodes và page tables.
- TCP socket buffers.
- Bộ nhớ của các process khác nằm trong cùng cgroup hoặc descendants.

Vì vậy, memory.current của cgroup không phải phép đo RSS của riêng Java/native process. Nếu container có sidecar/process phụ hoặc ghi nhiều dữ liệu vào filesystem cache, cgroup usage có thể tăng dù RSS của ứng dụng không tăng tương ứng. [Linux cgroup v2 documentation](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst).

### 4.2. Các counter quan trọng trong cgroup v2

Khi hệ thống dùng cgroup v2, các file thường gặp là:

| File | Ý nghĩa |
| --- | --- |
| memory.current | Tổng bộ nhớ hiện đang được cgroup và descendants sử dụng. |
| memory.max | Hard memory limit; max nghĩa là không đặt hard limit tại cgroup đó. |
| memory.high | Ngưỡng gây reclaim/throttling khi vượt; không trực tiếp kích hoạt OOM killer. |
| memory.peak | Peak memory usage được ghi nhận của cgroup. |
| memory.stat | Phân rã usage theo anon, file, kernel, sock, shmem và các loại khác. |
| memory.events | Bộ đếm sự kiện high, max, oom, oom_kill và các sự kiện liên quan. |
| memory.swap.current | Swap đang được cgroup sử dụng. |
| memory.swap.max | Giới hạn swap của cgroup. |

memory.max là hard limit chính. Khi usage chạm giới hạn và kernel không reclaim đủ, OOM killer có thể được gọi trong cgroup. memory.high thường gây reclaim/throttling và suy giảm hiệu năng trước khi có OOM. Đọc memory.events để biết counter oom hoặc oom_kill có tăng trong lần test hay không. [Linux cgroup v2 memory controller](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst).

Kiểm tra các file trong container Linux:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

Đường dẫn trên là ví dụ phổ biến khi container nhìn thấy cgroup v2 mount ở /sys/fs/cgroup. Cgroup có thể được mount ở vị trí khác hoặc process nằm trong sub-cgroup. Hãy xem /proc/self/cgroup và mount information để tìm đúng directory.

~~~bash
cat /proc/self/cgroup
mount | grep cgroup
~~~

### 4.3. Cgroup v1

Một số hệ thống cũ dùng cgroup v1. Tên file thường gặp:

| File | Ý nghĩa |
| --- | --- |
| memory.usage_in_bytes | Usage hiện tại. |
| memory.limit_in_bytes | Giới hạn memory. |
| memory.max_usage_in_bytes | Peak usage. |
| memory.stat | Phân rã usage. |
| memory.failcnt | Số lần usage chạm giới hạn theo accounting của controller. |

Không giả định container luôn dùng cgroup v2. Xác định version và mount thực tế trước khi viết script thu thập số liệu.

### 4.4. Docker và Kubernetes

Docker cho phép đặt hard limit bằng --memory và soft reservation bằng --memory-reservation. Ví dụ:

~~~bash
docker run --rm \
  --memory=512m \
  --cpus=1.0 \
  -p 8080:8080 \
  orders-service:native
~~~

--memory=512m là giới hạn của container; không có nghĩa Java heap được phép dùng 512 MiB. Docker cũng mô tả tùy chọn swap riêng và các hệ quả hiệu năng khi container phải swap. [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).

Trong Kubernetes:

- **Memory request** ảnh hưởng quyết định scheduling và mức tài nguyên được đảm bảo theo cơ chế của cluster.
- **Memory limit** được thực thi qua cgroup; vượt giới hạn có thể dẫn đến OOM kill.
- kubectl top pod và dashboard thường hiển thị working set hoặc số liệu do metrics pipeline cung cấp; không giả định chúng giống hệt RSS hay memory.current.
- Khi pod bị OOM, kiểm tra container state/reason, restart count, event và metrics cgroup nếu có quyền truy cập.

## 5. Heap, off-heap và giới hạn heap của Native Image

### 5.1. Xmx chỉ giới hạn Java heap

Có thể chạy native executable với heap tối đa:

~~~bash
./orders-service -Xmx256m
~~~

Có thể đặt cả heap ban đầu:

~~~bash
./orders-service -Xms64m -Xmx256m
~~~

Giới hạn này không bao gồm toàn bộ thread stacks, direct buffers, native library allocations, runtime/GC structures, file mappings và kernel-accounted memory. Do đó, không đặt Xmx bằng toàn bộ container limit.

Ví dụ minh họa: với container limit 512 MiB, nếu đặt Xmx512m, process vẫn cần thêm memory ngoài heap và có thể bị cgroup OOM kill trước khi Java heap đạt max. Heap budget phải để chỗ cho phần còn lại và safety margin.

### 5.2. Cấu hình heap mặc định phụ thuộc GC và GraalVM release

Không nên chép một tỷ lệ mặc định vào mọi project. Tài liệu GraalVM hiện hành mô tả Serial GC và G1 có cách xác định heap max khác nhau; ví dụ Serial GC có mặc định dựa trên tỷ lệ RAM vật lý, còn G1 dùng MaxRAMPercentage. Khả năng dùng G1 còn phụ thuộc GraalVM distribution, edition và platform.

Các tùy chọn thường gặp trong tài liệu hiện hành:

- Xmx: giới hạn heap ở runtime.
- Xms: heap tối thiểu ở runtime.
- R:MaxHeapSize: cấu hình heap max mặc định khi build image.
- MaximumHeapSizePercent: tỷ lệ heap max cho các cấu hình GC hỗ trợ option này.
- MaxRAMPercentage: tỷ lệ RAM dùng làm heap max trong các cấu hình hỗ trợ option này.

Ví dụ cấu hình heap max khi build:

~~~bash
native-image -R:MaxHeapSize=256m ...
~~~

Ví dụ override khi chạy:

~~~bash
./orders-service -Xmx256m
~~~

Tên option và GC compatibility cần đối chiếu tài liệu đúng GraalVM release. Đọc phần Image configuration trong native build output để biết collector và max heap thực tế được chọn. [GraalVM Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/).

### 5.3. GC có thể làm RSS tăng tạm thời

Trong quá trình collection, GC có thể cần thêm memory cho việc di chuyển, đánh dấu hoặc xử lý object. GraalVM lưu ý RSS có thể tăng tạm thời khi GC, đặc biệt đáng quan tâm trong container có giới hạn chặt.

Vì vậy, chỉ lấy một snapshot sau startup có thể bỏ lỡ peak memory. Phải lấy mẫu trong lúc warm-up, tải cao, GC và soak test. Không suy ra rằng RSS sau GC luôn lập tức giảm về giá trị trước collection.

### 5.4. Đừng nhầm memory của native-image builder với memory của ứng dụng

native-image builder tự chạy trên JVM và có thể dùng nhiều heap/RSS trong lúc phân tích, tối ưu và tạo executable. Build output có thống kê build resources, memory theo stage, image heap và code area. Đây là **build-time memory**, không phải runtime memory của service sau deploy.

Nếu CI bị OOM trong lúc nativeCompile/native:compile, điều tra builder memory, số thread và giới hạn CI. Nếu container production bị OOM, điều tra native executable runtime và cgroup của container. [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/).

## 6. Thu thập memory metrics trong Spring Boot

### 6.1. Spring Boot Actuator và Micrometer

Spring Boot Actuator có thể xuất các meter JVM qua Micrometer, gồm thông tin memory/buffer pool, GC và thread utilization. Các meter thường có prefix jvm. Spring Boot cũng cung cấp application startup metrics:

- application.started.time: thời gian khởi động application.
- application.ready.time: thời gian từ lúc bắt đầu đến khi ứng dụng sẵn sàng nhận request.

Xem [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và kiểm tra meter thực tế của đúng Spring Boot/GraalVM version.

Ví dụ expose metrics endpoint cho môi trường benchmark:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Truy vấn các meter có sẵn:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
~~~

Tên meter và tag có thể khác theo version/runtime. Hãy gọi endpoint liệt kê trước rồi chọn đúng meter có trong ứng dụng.

### 6.2. Actuator không thay thế RSS/cgroup measurement

jvm.memory.used mô tả vùng memory mà JVM/Micrometer expose qua memory management API. Nó không phải RSS, PSS hay memory.current. Đặc biệt với Native Image, không giả định toàn bộ HotSpot memory pools hoặc các chỉ số JMX có cùng ý nghĩa/độ sẵn có như trên JVM.

Cần đo riêng:

- Actuator/Micrometer: heap, buffer pool, GC, thread và startup metrics nếu runtime expose.
- Process: RSS/PSS/peak RSS từ OS.
- Container: cgroup current/peak/limit/events.
- Workload: request rate, latency, error rate và số kết nối.

Không thêm endpoint Actuator public chỉ để benchmark. Bảo vệ endpoint metrics theo chính sách vận hành và tắt/expose phù hợp sau khi thử nghiệm.

## 7. Quy trình benchmark memory JVM và native

Một phép so sánh chỉ có ý nghĩa khi điều kiện chạy được kiểm soát.

### 7.1. Cố định điều kiện thử nghiệm

Ghi lại:

- Cùng commit và chức năng ứng dụng.
- Cùng Spring Boot/Spring Framework và dependency versions.
- JDK/GraalVM distribution và version.
- Cùng OS, architecture, libc và container base image khi có thể.
- Cùng memory limit, CPU quota và swap policy.
- Cùng environment variables, profile, datasource và external services.
- Cùng dataset, request mix, concurrency và thời gian chạy.
- Cùng logging level, metrics exporters và tracing configuration.

Không so sánh một JVM process chạy trên host không giới hạn với native executable trong container 512 MiB rồi kết luận native tiết kiệm bộ nhớ hơn. Điều kiện giới hạn và workload phải tương đương.

### 7.2. Chia các giai đoạn lấy mẫu

Đo ít nhất các giai đoạn sau:

1. **Cold start:** bắt đầu process/container mới; đo RSS và cgroup usage trong lúc startup.
2. **Ready/idle:** đợi readiness endpoint thành công, không gửi traffic; ghi heap, RSS, cgroup.
3. **Warm-up:** gửi workload ổn định để khởi tạo connection pool, cache, serializer và code paths.
4. **Steady load:** chạy tải mục tiêu đủ lâu; ghi time series và percentile.
5. **Peak load:** tăng concurrency/RPS đến tải thiết kế; ghi peak RSS/cgroup và GC.
6. **Soak:** giữ tải trong thời gian dài để tìm xu hướng tăng dần.
7. **Shutdown:** dừng process/container; ghi thời gian và kiểm tra tài nguyên được giải phóng.

Native Image không có HotSpot JIT warm-up giống JVM thông thường, nhưng application vẫn có warm-up do connection pool, cache, lazy initialization, DNS/TLS session và dữ liệu được nạp lần đầu. Vì vậy vẫn cần tách cold start khỏi steady state.

### 7.3. Chọn các chỉ số cần lưu

| Chỉ số | Cold/idle | Warm/steady | Peak/soak |
| --- | --- | --- | --- |
| Startup-to-ready | Có | Không | Không |
| Heap used/committed/max | Có | Có | Có |
| Buffer/off-heap metrics | Có nếu runtime expose | Có | Có |
| RSS và PSS | Có | Có | Có, lưu peak |
| Cgroup memory.current | Có | Có | Có, lưu memory.peak |
| memory.events | Baseline | Theo dõi | Kiểm tra high, max, oom, oom_kill |
| GC count/time/pause | Baseline | Có | Có |
| Thread count | Có | Có | Có |
| RPS, p95/p99 latency, errors | Smoke | Có | Có |
| CPU usage/throttling | Có | Có | Có |

Lấy mẫu theo chu kỳ cố định, ví dụ 1–5 giây tùy tải và chi phí đo. Giữ cùng chu kỳ cho JVM và native. Khi benchmark ngắn, lấy mẫu quá thưa có thể bỏ lỡ peak; khi benchmark tải rất cao, lấy mẫu quá dày có thể tự tạo overhead.

### 7.4. Chạy Docker với cùng resource limits

Ví dụ chạy một image có hard memory limit và CPU quota:

~~~bash
docker run --rm \
  --name orders-native \
  --memory=512m \
  --cpus=1.0 \
  -p 8080:8080 \
  orders-service:native
~~~

Chạy JVM image với cùng --memory và --cpus, cùng profile/workload. Đo docker stats để quan sát tổng quan; nếu cần số liệu chuẩn để đối chiếu cgroup, đọc memory.current, memory.peak, memory.stat và memory.events trong cgroup của container.

### 7.5. Lặp lại nhiều lần

Chạy mỗi biến thể nhiều lần trong điều kiện sạch, xen kẽ thứ tự JVM/native nếu môi trường có tải nền thay đổi. Báo cáo median và khoảng dao động, không chỉ chọn lần chạy tốt nhất. Với peak memory, lưu maximum từng run và phân phối peak giữa các run.

## 8. Tính heap budget cho container

### 8.1. Dùng mô hình ngân sách

Có thể lập ngân sách khái niệm:

~~~text
Container limit = runtime heap + native/off-heap + image/code resident + stacks + cache/kernel + other processes + safety margin
~~~

Đây không phải công thức cộng chính xác từ các metric, vì RSS/cgroup accounting có thể overlap hoặc charge shared pages khác nhau. Mô hình này nhắc nhóm rằng heap chỉ là một thành phần.

### 8.2. Ví dụ minh họa

Giả sử container có hard limit 512 MiB. Nhóm đo được dưới workload đại diện:

| Thành phần quan sát | Giá trị minh họa |
| --- | ---: |
| Runtime Java heap resident/used | 150 MiB |
| Native/direct buffers và runtime allocations | 65 MiB |
| Thread stacks và code/image pages resident | 80 MiB |
| Page cache, kernel và socket accounting | 35 MiB |
| Process/helper khác trong cùng cgroup | 20 MiB |
| Phần còn lại đến limit | 162 MiB |

Các con số trên chỉ là ví dụ để minh họa cách lập budget, không phải định mức cho Spring Boot Native Image. Trong thực tế, một số vùng có thể được tính ở nhiều góc đo khác nhau; hãy dùng cgroup counter làm nguồn đối chiếu với hard limit và process metrics để giải thích thành phần.

Nếu đo được cgroup peak 490 MiB trên limit 512 MiB, ứng dụng gần như không có khoảng dự phòng cho burst, GC peak, traffic tăng hoặc thay đổi dependency. Cần tối ưu hoặc tăng limit trước khi phát hành.

### 8.3. Đừng đặt heap max bằng container limit

Nếu container limit là 512 MiB, một Xmx512m có thể khiến phần native/off-heap đẩy tổng usage vượt cgroup limit. Hãy đo workload và chọn heap max có dự phòng. Sau đó chạy stress/soak test để xác nhận cgroup peak vẫn nằm dưới hard limit với margin đã thống nhất.

## 9. Chẩn đoán các kiểu tăng bộ nhớ

### 9.1. Heap tăng cùng RSS

Có thể do object allocation lớn, cache giữ object, request backlog hoặc memory leak trong object graph. Kiểm tra:

- Heap used trước/sau GC.
- Object retention và cache size.
- Request concurrency và queue length.
- Số lượng session/connection hoặc object theo tenant.
- Tỷ lệ allocation và GC frequency.

Nếu heap used sau các chu kỳ GC liên tục tăng theo thời gian dưới workload ổn định, điều tra object retention.

### 9.2. Heap ổn định nhưng RSS tăng

Đây là dấu hiệu cần kiểm tra ngoài heap:

- Direct buffers hoặc native allocations tăng.
- Thread count tăng làm tăng stack memory.
- JNI/native library giữ memory.
- Memory-mapped files hoặc file-backed pages tăng.
- Allocator giữ vùng đã cấp phát dù object đã được giải phóng.
- GC/runtime cần thêm vùng memory tạm thời.

Đối chiếu RssAnon, RssFile, Pss, memory.stat và metrics của library liên quan. Không kết luận memory leak chỉ từ một snapshot RSS.

### 9.3. RSS ổn định nhưng cgroup usage tăng

Kiểm tra:

- Page cache hoặc tmpfs.
- Kernel memory, socket buffers và page tables.
- Process phụ hoặc sidecar cùng cgroup.
- File write/read pattern và logging.
- memory.stat để biết anon, file, kernel, sock thay đổi.

Nếu memory.current tăng chủ yếu ở file, xem cache/tmpfs; nếu kernel hoặc sock tăng, xem số connection, network buffer và process activity.

### 9.4. OOM dù heap chưa chạm Xmx

Có thể cgroup hard limit bị chạm trước khi Java heap đạt max. Kiểm tra:

- memory.current và memory.peak.
- memory.max.
- memory.events với oom, oom_kill, max.
- Kubernetes lastState.terminated.reason và pod events.
- Process RSS/PSS và các process khác trong cgroup.

Một process bị SIGKILL hoặc exit code 137 có thể liên quan OOM, nhưng không tự nó chứng minh OOM. Đối chiếu kernel/cgroup/Kubernetes events để xác nhận.

### 9.5. Heap OOM và cgroup OOM khác nhau

| Loại lỗi | Dấu hiệu thường gặp | Nơi kiểm tra |
| --- | --- | --- |
| Java heap OOM | OutOfMemoryError: Java heap space hoặc lỗi allocation từ runtime | Heap metrics, GC log, Xmx, object retention |
| Native allocation failure | Allocation từ JNI/native library thất bại, process có thể crash hoặc trả lỗi | Native library logs, RSS/PSS, memory.stat, system logs |
| Cgroup OOM kill | Process bị kernel kill khi cgroup không thể reclaim dưới hard limit | memory.events, Docker/Kubernetes state, kernel logs |
| Build-time OOM | native-image builder chết hoặc báo heap/RSS cao khi compile | Build log, peak RSS của builder, -J-Xmx, parallelism và CI limit |

## 10. Các lỗi đo lường thường gặp

| Sai lầm | Vì sao gây hiểu nhầm | Cách làm đúng |
| --- | --- | --- |
| Chỉ báo cáo Xmx | Đây là heap cap, không phải total memory. | Báo heap, RSS/PSS và cgroup usage. |
| Dùng executable file size làm RAM usage | File size không cho biết trang nào đã resident. | Đo RSS/PSS sau khi process chạy. |
| So sánh JVM heap với native RSS | Hai số đo khác phạm vi. | So sánh cùng loại metric giữa hai runtime. |
| Lấy RSS của một thời điểm | Có thể bỏ lỡ peak lúc GC hoặc peak traffic. | Thu time series và peak. |
| Chạy JVM không giới hạn, native có cgroup cap | Điều kiện benchmark không tương đương. | Dùng cùng CPU/memory/swap limits. |
| Chỉ nhìn docker stats | Không cho biết rõ heap/off-heap và có khác biệt accounting theo nền tảng. | Kết hợp process metrics với cgroup files. |
| Coi Actuator jvm.memory.used là RSS | Meter mô tả memory pool/heap API, không phải process resident set. | Đo RSS/PSS từ OS. |
| Không chạy soak test | Memory leak hoặc cache tăng dần có thể chưa xuất hiện. | Chạy đủ lâu với workload ổn định. |
| Không ghi version GC/runtime | Defaults và khả năng GC có thể thay đổi theo GraalVM release/distribution. | Ghi GraalVM, GC, options và platform trong report. |
| Trộn build RSS và runtime RSS | native-image builder là process khác với service executable. | Báo cáo build memory và runtime memory riêng. |

## 11. Bài thực hành: đo heap, RSS và cgroup cho cùng một service

**Bối cảnh:** nhóm phát triển có một Spring Boot service chạy trên JVM và một native executable. Cả hai được deploy trong container limit 512 MiB. Nhóm muốn xác định native có giảm memory footprint trong idle và steady load hay không, đồng thời bảo đảm không OOM khi peak traffic.

### Nhiệm vụ

1. Ghi lại commit, Spring Boot, JDK/GraalVM, GC, Native Build Tools, OS/architecture và container base image.
2. Build JVM artifact và native executable từ cùng source/configuration.
3. Chạy hai biến thể trong container có cùng --memory, CPU quota và swap policy.
4. Expose Actuator metrics ở môi trường benchmark; xác nhận meter heap/buffer/GC thực tế có sẵn.
5. Đo application.started.time/application.ready.time nếu được expose.
6. Thu RSS/PSS/peak RSS từ process Linux.
7. Thu cgroup memory.current, memory.peak, memory.max, memory.stat và memory.events.
8. Chạy cùng workload ở cold start, idle, warm-up, steady load, peak load và soak.
9. Ghi RPS, p95/p99 latency, errors, GC count/time và thread count.
10. Tính peak memory và safety margin so với container limit.
11. Phân tích trường hợp heap ổn định nhưng RSS/cgroup tăng.
12. Chạy lại sau khi thay heap max hoặc cấu hình GC; chỉ giữ thay đổi nếu số đo và latency đáp ứng mục tiêu.

### Biên bản kết quả

| Bằng chứng | JVM | Native |
| --- | --- | --- |
| GraalVM/JDK/GC version | Ghi phiên bản | Ghi phiên bản |
| Container memory limit | Ghi giá trị | Ghi giá trị |
| Startup-to-ready | Ghi median và spread | Ghi median và spread |
| Heap used/committed/max | Ghi theo giai đoạn | Ghi theo giai đoạn nếu runtime expose |
| RSS/PSS/peak RSS | Ghi theo giai đoạn | Ghi theo giai đoạn |
| Cgroup current/peak | Ghi theo giai đoạn | Ghi theo giai đoạn |
| Cgroup memory.events | Ghi delta | Ghi delta |
| RPS và p95/p99 | Ghi theo workload | Ghi theo workload |
| GC count/time | Ghi theo workload | Ghi theo workload |
| OOM/restart | Ghi event | Ghi event |
| Safety margin | So với limit | So với limit |

### Tiêu chí hoàn thành

- [ ] Phân biệt được heap, image heap, off-heap, RSS, PSS và cgroup usage.
- [ ] Đo được RSS/PSS của process trên Linux.
- [ ] Đọc được cgroup memory current/peak/limit/events.
- [ ] Có cùng workload và resource limits cho JVM/native.
- [ ] Có số đo ở idle, steady, peak và soak.
- [ ] Phân biệt được heap OOM với cgroup OOM kill.
- [ ] Giải thích được trường hợp heap ổn định nhưng RSS/cgroup tăng.
- [ ] Chọn được heap max có dự phòng cho native/off-heap memory.
- [ ] Báo cáo peak memory và safety margin, không chỉ heap used.
- [ ] Lưu được toolchain/version và điều kiện benchmark để tái lập.

## 12. Câu hỏi tự đánh giá

1. Vì sao Xmx256m không có nghĩa process chỉ dùng tối đa 256 MiB RAM?
2. Image heap khác runtime Java heap như thế nào?
3. RSS khác PSS ở cách tính shared pages ra sao?
4. Vì sao virtual memory size không phải chỉ số phù hợp để báo cáo RAM resident?
5. memory.current, memory.max, memory.peak và memory.events trong cgroup v2 trả lời những câu hỏi nào?
6. Vì sao container memory có thể tăng trong khi RSS của Java process ổn định?
7. Khi heap used thấp nhưng cgroup OOM xảy ra, cần kiểm tra những vùng nào?
8. Vì sao GC có thể làm RSS tăng tạm thời?
9. Spring Boot Actuator jvm.memory.used khác RSS ở điểm nào?
10. Vì sao cần tách peak RSS của native-image builder khỏi peak RSS của service runtime?
11. Những điều kiện nào phải giống nhau khi benchmark JVM và native?
12. Làm thế nào xác định heap budget có đủ safety margin dưới container limit?

## 13. Tài liệu chính thức

Các tùy chọn GC/heap và số liệu memory phụ thuộc GraalVM distribution/release, OS và container runtime. Hãy đối chiếu đúng version của dự án:

- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): Java heap, GC, RSS peak và heap options.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): build resources, peak RSS, image heap và code area.
- [GraalVM Native Image — Optimize Memory Footprint](https://www.graalvm.org/latest/reference-manual/native-image/guides/optimize-memory-footprint/): đo và giới hạn heap của native executable.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM memory/buffer/GC/thread metrics và application startup metrics.
- [Docker Engine — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): hard/soft memory limits, swap và CPU quota.
- [Linux Kernel — Control Group v2](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst): memory.current, memory.max, memory.stat, memory.events và memory controller.
- [Linux Kernel — The /proc Filesystem](https://www.kernel.org/doc/html/latest/filesystems/proc.html): process mappings, RSS, PSS và smaps_rollup.
- [Linux man-pages — proc_pid_status(5)](https://www.man7.org/linux/man-pages/man5/proc_pid_status.5.html): VmRSS, VmHWM, RssAnon, RssFile và RssShmem.

**Điểm cần nhớ:** heap mô tả object memory do runtime quản lý; RSS/PSS mô tả các trang process đang resident; cgroup mô tả memory được tính vào giới hạn container. Chỉ khi đo cả ba cùng workload và cùng resource limits, nhóm mới có thể đánh giá chính xác footprint và nguy cơ OOM của Spring Boot Native Image.

