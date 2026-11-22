# Cgroups, CPU và bộ nhớ khả dụng trong môi trường đích

CRaC (Coordinated Restore at Checkpoint) cho phép khôi phục một tiến trình Java từ trạng thái đã được chuẩn bị trước. Nhưng khả năng restore thành công không chỉ phụ thuộc vào checkpoint image và JDK. Tiến trình còn phải chạy trong một môi trường có tài nguyên phù hợp: CPU được phép sử dụng, giới hạn CPU time, bộ nhớ, swap, số process/thread và các giới hạn do container hoặc hệ điều phối áp đặt.

Trên Linux, cgroups (control groups) là cơ chế kernel dùng để theo dõi và giới hạn tài nguyên của một nhóm process. Container runtime và Kubernetes thường dùng cgroups để thực thi CPU limit, memory limit và một số giới hạn khác. JVM hiện đại có khả năng nhận biết một số giới hạn container để điều chỉnh heap, số processor mà JVM nhìn thấy và các quyết định runtime. Tuy nhiên, cách nhận biết phụ thuộc JDK, vendor, phiên bản và cấu hình.

Khi tạo checkpoint ở môi trường nguồn rồi restore trong môi trường đích, CPU và memory limit có thể khác nhau. JVM đã khởi động và thực hiện các quyết định ergonomics trước checkpoint; không nên mặc định mọi quyết định đó sẽ được tính lại như một lần khởi động mới. Nếu môi trường đích nhỏ hơn, tiến trình có thể bị throttling, GC không đủ thời gian, cạn native memory hoặc bị cgroup OOM killer kết thúc. Nếu môi trường đích lớn hơn, heap maximum và thread pool đã tạo có thể vẫn giữ kích thước cũ.

Vì vậy, cần kiểm tra giới hạn cgroups thực tế tại nơi restore, đối chiếu với cấu hình JVM và footprint của ứng dụng, rồi thử nghiệm dưới đúng resource limit dự kiến triển khai.

## 1. Cgroups và container resource limits

Cgroups là cơ chế của Linux kernel để tổ chức process thành nhóm và áp dụng accounting hoặc giới hạn tài nguyên. Một container thường được đặt trong một cgroup hoặc một nhánh của cây cgroup. Các controller có thể quản lý:

- CPU: thời gian CPU được cấp, trọng số ưu tiên và tập CPU được phép chạy.
- Memory: lượng bộ nhớ được sử dụng, ngưỡng reclaim và giới hạn tối đa.
- PIDs: số lượng process/thread có thể tồn tại trong nhóm.
- I/O: băng thông hoặc số thao tác I/O tùy controller và kernel.
- Cpuset: các CPU hoặc NUMA node mà process được phép sử dụng.

Cgroup không phải là một máy ảo có CPU và RAM vật lý riêng. Nó là cơ chế kernel kiểm soát và thống kê process trong một hệ thống chia sẻ. Hai container có thể cùng dùng CPU vật lý, nhưng mỗi container có quota, weight hoặc cpuset riêng.

Trong môi trường container, nhìn thấy số CPU của host không có nghĩa process được dùng toàn bộ số CPU đó. Tương tự, tổng RAM của máy không phải là bộ nhớ container được phép sử dụng.

## 2. Cgroups v1 và cgroups v2

Linux có hai thế hệ cgroups:

- **cgroups v1:** Các controller có thể được mount ở những hierarchy riêng. CPU, memory và cpuset có thể nằm ở các mount point khác nhau.
- **cgroups v2:** Dùng một hierarchy thống nhất với các controller được bật theo nhánh. Các file điều khiển có tên và ngữ nghĩa được chuẩn hóa hơn.

Một hệ thống có thể dùng v1, v2 hoặc cấu hình hybrid tùy kernel và runtime. Không nên giả định mọi máy Linux đều có cùng đường dẫn hoặc cùng file.

| Chủ đề | cgroups v1 | cgroups v2 |
|---|---|---|
| CPU quota | cpu.cfs_quota_us, cpu.cfs_period_us | cpu.max |
| CPU weight/share | cpu.shares | cpu.weight |
| CPU set | cpuset.cpus, có thể cần kiểm tra effective set | cpuset.cpus.effective cùng các file cpuset |
| CPU statistics | cpu.stat | cpu.stat |
| Memory current | memory.usage_in_bytes | memory.current |
| Memory limit | memory.limit_in_bytes | memory.max |
| Memory high/reclaim boundary | Tùy controller và kernel, không có giao diện tương đương hoàn toàn | memory.high |
| Memory events | memory.failcnt, một số event file tùy kernel | memory.events, memory.events.local |
| Memory + swap | memory.memsw.* nếu được bật | memory.swap.max, memory.swap.current |

Các file có thể không xuất hiện nếu controller chưa được bật, kernel không hỗ trợ hoặc container namespace chỉ expose một phần hierarchy. Hãy xác định phiên bản cgroup và đường dẫn thực tế trước khi đọc giá trị.

## 3. Xác định cgroup của process đang chạy

Không nên chỉ đọc một file ở /sys/fs/cgroup rồi kết luận đó là giới hạn của process. Trong một hierarchy lồng nhau, giới hạn ở ancestor có thể áp dụng cho container ngay cả khi cgroup con không đặt giới hạn riêng. Container runtime cũng có thể mount cgroup namespace làm đường dẫn nhìn thấy khác với host.

Bắt đầu bằng:

~~~bash
cat /proc/self/cgroup
cat /proc/self/mountinfo
~~~

/proc/self/cgroup cho biết process hiện tại thuộc cgroup path nào. /proc/self/mountinfo cho biết cgroup filesystem được mount ở đâu và mount root nào được nhìn thấy. Từ hai thông tin này, xác định đúng directory chứa các file controller.

Có thể kiểm tra thêm:

~~~bash
mount | grep cgroup
findmnt -t cgroup,cgroup2
~~~

Trong cgroups v2, dòng trong /proc/self/cgroup thường có dạng 0::/some/path. Nếu cgroup2 được mount tại /sys/fs/cgroup, đường dẫn process có thể nằm dưới mount point đó. Nhưng trong cgroup namespace, process có thể thấy chính cgroup của mình như root /; do đó hãy đối chiếu mount root trong mountinfo.

Trong cgroups v1, mỗi controller có thể có path và mount point khác nhau. Ví dụ, CPU controller và memory controller có thể không nằm cùng một thư mục.

## 4. CPU quota, period và CPU capacity

CPU quota giới hạn tổng thời gian CPU mà một cgroup được phép sử dụng trong một chu kỳ. Với cgroups v1, quota và period thường nằm trong:

- cpu.cfs_quota_us
- cpu.cfs_period_us

Với cgroups v2, cả hai giá trị thường nằm trong cpu.max theo định dạng:

~~~text
<quota> <period>
~~~

Ví dụ:

~~~text
50000 100000
~~~

Có nghĩa cgroup được dùng tối đa 50.000 microsecond CPU trong mỗi chu kỳ 100.000 microsecond. Tỷ lệ tương đương là 0,5 CPU time trung bình theo quota đó. Giá trị max 100000 có nghĩa không đặt quota CPU ở cgroup hiện tại; vẫn có thể bị giới hạn bởi ancestor hoặc cpuset.

Một ví dụ khác:

~~~text
200000 100000
~~~

Tương đương tối đa khoảng hai CPU time trong mỗi chu kỳ, nếu cgroup có đủ CPU được phép và không bị giới hạn ở ancestor.

Tỷ lệ quota/period không phải là số core vật lý riêng dành cho container. Nó là giới hạn thời gian CPU tổng hợp. Một container có quota tương đương 1,5 CPU có thể chạy đồng thời trên nhiều core trong một phần chu kỳ rồi bị throttle khi dùng hết quota.

## 5. Cpuset và CPU được phép chạy

Quota không phải yếu tố duy nhất quyết định CPU capacity. Cpuset giới hạn tập CPU mà process có thể chạy trên đó.

Trong cgroups v2, kiểm tra các file cpuset.cpus và cpuset.cpus.effective. Tên đường dẫn thực tế phụ thuộc cgroup directory. cpuset.cpus.effective phản ánh tập CPU hiệu lực mà cgroup có thể sử dụng sau khi xét các ràng buộc ở hierarchy. Trong cgroups v1, có thể gặp cpuset.cpus và các file liên quan.

Ví dụ giá trị:

~~~text
2-5
~~~

Cho biết các CPU logic có ID 2, 3, 4 và 5 nằm trong cpuset. Nếu quota chỉ tương đương một CPU, việc được phép chạy trên bốn CPU không đồng nghĩa được sử dụng cả bốn CPU liên tục.

CPU capacity của process cần xét đồng thời:

- CPU quota ở cgroup hiện tại.
- Quota ở các ancestor cgroup.
- Cpuset hiệu lực.
- CPU thực tế đang có trên host.
- Cạnh tranh với workload khác.
- CPU weight/share khi có contention.

Không thể lấy riêng nproc hoặc số CPU host rồi dùng làm giới hạn worker tối ưu.

## 6. CPU weight và shares không phải hard limit

cpu.weight trong cgroups v2 và cpu.shares trong cgroups v1 biểu diễn trọng số tương đối khi nhiều cgroup cạnh tranh CPU. Chúng không giống CPU quota.

Ví dụ, hai container cùng không có quota nhưng có weight khác nhau. Khi CPU rảnh, cả hai có thể sử dụng nhiều CPU. Khi host quá tải, cgroup có weight cao hơn có thể nhận tỷ lệ CPU lớn hơn theo cơ chế phân phối của kernel.

| Cơ chế | Tác dụng | Có đặt trần CPU cứng không? |
|---|---|---|
| CPU quota | Giới hạn CPU time trong mỗi period | Có |
| Cpuset | Giới hạn CPU logic được phép chạy | Giới hạn tập CPU, không phải quota thời gian |
| CPU weight/share | Trọng số tương đối khi cạnh tranh | Không |
| Kubernetes CPU request | Thông tin phục vụ scheduling và cấu hình phân bổ tương ứng | Không phải CPU limit |
| Kubernetes CPU limit | Thường được runtime thực thi bằng quota | Có, theo cấu hình runtime/kernel |

CPU request và CPU limit trong Kubernetes có vai trò khác nhau. Request ảnh hưởng đến scheduling và một số quyết định phân bổ tài nguyên; nó không có nghĩa container luôn được độc quyền số CPU đó. Limit thường được thực thi bằng CPU quota. Cần kiểm tra cgroup thực tế thay vì chỉ đọc YAML.

## 7. CPU throttling và ảnh hưởng đến Java

Khi cgroup dùng hết quota trong period, kernel có thể throttle các task cho đến chu kỳ tiếp theo. Process vẫn sống nhưng không được chạy CPU trong một phần thời gian.

Trong cgroups v2, cpu.stat thường cung cấp các chỉ số như:

- usage_usec: CPU time đã sử dụng.
- user_usec: CPU time ở user mode.
- system_usec: CPU time ở kernel mode.
- nr_periods: số chu kỳ quota.
- nr_throttled: số chu kỳ bị throttle.
- throttled_usec: tổng thời gian bị throttle.

Tên và tập trường có thể thay đổi theo kernel. Dùng chúng để quan sát xu hướng throttling thay vì suy ra chính xác mọi latency từ một lần đọc.

CPU throttling ảnh hưởng đến ứng dụng Java theo nhiều cách:

- Request thread xử lý chậm hơn và p95/p99 latency tăng.
- Garbage Collector có ít CPU time hơn để hoàn tất công việc.
- JIT compiler và class loading có thể mất nhiều thời gian hơn.
- Executor queue tăng vì worker xử lý không kịp.
- Scheduler và heartbeat có thể trễ.
- Thread renew lease, health check hoặc service discovery có thể không chạy đúng thời điểm dự kiến.
- Một tác vụ có timeout ngắn có thể thất bại dù dependency bên ngoài vẫn khỏe.

Sau restore, nếu CPU quota thấp hơn môi trường tạo checkpoint, ứng dụng có thể mất nhiều thời gian hơn để đạt readiness. Một pool thread được tạo với kích thước lớn dựa trên số CPU ở nguồn có thể tạo quá nhiều runnable thread so với CPU time thực tế ở đích.

## 8. JVM nhận biết CPU container như thế nào?

HotSpot trên các phiên bản hiện đại có cơ chế container awareness trên Linux. Tùy phiên bản, JVM có thể xem xét cgroup CPU quota, cpuset và các thông tin container để quyết định số processor khả dụng cho một số phép tính ergonomics.

Một số điểm cần phân biệt:

- Runtime.getRuntime().availableProcessors() trả về số processor mà JVM báo là có sẵn cho ứng dụng.
- Số CPU host từ nproc, lscpu hoặc /proc/cpuinfo có thể lớn hơn số processor JVM nhận biết.
- Quota phân số như 0,5 CPU không nhất thiết được biểu diễn trực tiếp thành một nửa processor trong API trả về số nguyên.
- Cách làm tròn và cách xét quota/cpuset phụ thuộc JDK version và implementation.
- CPU weight/share không nhất thiết được xem như số processor.
- Cờ -XX:ActiveProcessorCount=N có thể ghi đè số processor mà JVM dùng cho ergonomics trên các JDK hỗ trợ cờ này.

Trên HotSpot hiện đại, container support thường được bật mặc định trên Linux, nhưng cần xác minh với đúng JDK. Các bản Java cũ hoặc bản phân phối khác có thể có hành vi khác.

Có thể kiểm tra:

~~~bash
java -XshowSettings:system -version
~~~

Tùy JDK, lệnh này hiển thị thông tin hệ thống/container mà JVM nhận biết. Có thể bật log container khi khởi động nếu bản JVM hỗ trợ tag tương ứng:

~~~bash
java -Xlog:os+container=trace -version
~~~

Kiểm tra tài liệu của JDK nếu unified logging tag hoặc tùy chọn này không được hỗ trợ. Trong ứng dụng, có thể ghi nhận:

~~~java
public final class RuntimeCapacity {
    public static void logCapacity() {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("maxHeapBytes="
                + runtime.maxMemory());
        System.out.println("totalHeapBytes="
                + runtime.totalMemory());
        System.out.println("freeHeapBytes="
                + runtime.freeMemory());
    }
}
~~~

Đây là thông tin JVM nhìn thấy, không thay thế việc đọc cgroup. maxMemory() phản ánh heap maximum của JVM, không phải tổng memory limit của container.

## 9. ActiveProcessorCount và các quyết định phụ thuộc CPU

Nhiều thành phần JVM sử dụng số processor để chọn mức song song:

- Garbage Collector chọn số GC worker.
- ForkJoinPool có thể dùng số processor để tính parallelism mặc định.
- Một số framework hoặc thư viện tự chọn kích thước thread pool.
- JIT và các tác vụ runtime điều chỉnh mức concurrency.
- Ứng dụng có thể tự tính số worker dựa trên availableProcessors().

Nếu JVM nhìn thấy quá nhiều CPU so với quota thực tế, ứng dụng có thể tạo nhiều thread hơn mức CPU time cho phép. Điều này làm tăng context switching, cạnh tranh lock, stack memory và queueing. Nếu JVM nhìn thấy quá ít CPU, throughput có thể thấp dù môi trường đích có nhiều CPU hơn.

Cờ -XX:ActiveProcessorCount=N có thể giúp đặt số processor mà JVM sử dụng cho các quyết định ergonomics, nhưng nó không thay đổi CPU quota của cgroup. Đặt giá trị cao hơn giới hạn thực tế không tạo thêm CPU time; đặt quá thấp có thể giảm mức song song không cần thiết.

Ví dụ:

~~~bash
java -XX:ActiveProcessorCount=2 -jar app.jar
~~~

Chỉ dùng cờ này sau khi đo và xác minh. Nếu CPU quota thay đổi theo workload hoặc môi trường, nên cân nhắc cấu hình riêng theo deployment thay vì cố định một giá trị chung.

## 10. Memory cgroup: current, high và max

Cgroups v2 cung cấp các file memory thường dùng:

- memory.current: lượng bộ nhớ hiện tại được tính cho cgroup.
- memory.max: hard limit; max nghĩa không đặt giới hạn tại cấp này.
- memory.high: ngưỡng áp lực/reclaim; khi vượt ngưỡng, kernel có thể gây reclaim/throttling để giảm sử dụng.
- memory.events: bộ đếm sự kiện như high, max, oom và oom_kill tùy kernel.
- memory.stat: phân rã các loại memory usage.
- memory.swap.current và memory.swap.max: trạng thái và giới hạn swap nếu controller được bật.

Ví dụ:

~~~text
memory.current = 805306368
memory.high    = 1073741824
memory.max     = 1610612736
~~~

Có thể diễn giải là cgroup hiện dùng khoảng 768 MiB, có ngưỡng high 1 GiB và hard max 1,5 GiB. Giá trị thực tế phải được chuyển đổi đúng đơn vị; các file thường biểu diễn byte.

memory.high không giống hard limit. Khi vượt high, kernel có thể reclaim memory và làm process chậm. memory.max là giới hạn cứng của cgroup; nếu không thể reclaim đủ, kernel có thể kích hoạt OOM handling.

Trong cgroups v1, các file phổ biến là memory.usage_in_bytes, memory.limit_in_bytes, memory.failcnt và một số file memory.stat. Tên và hành vi chi tiết phụ thuộc kernel.

## 11. Memory limit có thể nằm ở ancestor cgroup

Container có thể không đặt memory.max ở cgroup con nhưng vẫn chịu giới hạn từ parent. Ví dụ, một Pod cgroup hoặc systemd slice có thể giới hạn tổng memory của nhiều container hoặc process.

Vì vậy, cần kiểm tra giới hạn trên toàn đường ancestor. Giới hạn hiệu lực thực tế là giới hạn chặt nhất áp dụng từ các cấp hierarchy, cùng với các giới hạn khác của runtime/host. Không nên kết luận max ở một file tại cgroup con nghĩa là process không có memory limit.

Trong Kubernetes, cần hiểu giới hạn ở cấp container và pod tùy phiên bản/runtime/configuration. Một sidecar có thể dùng chung giới hạn ở cấp cao hơn hoặc có giới hạn riêng. Hãy xem cả cấu hình orchestrator lẫn cgroup mà process thực sự thuộc về.

## 12. Những loại bộ nhớ JVM cần tính vào container limit

Memory limit của cgroup không chỉ dành cho Java heap. Process Java có thể sử dụng:

- **Java heap:** Đối tượng Java và dữ liệu ứng dụng.
- **Metaspace:** Metadata của class.
- **Code cache:** Mã máy được JIT biên dịch.
- **Thread stacks:** Stack của platform thread và các vùng native liên quan.
- **Direct buffers:** Buffer ngoài heap, thường dùng cho I/O.
- **JNI/native libraries:** Bộ nhớ do thư viện native cấp phát.
- **GC structures:** Region metadata, remembered sets, mark bitmaps và cấu trúc collector.
- **JVM internal memory:** Compiler, symbol table, class metadata và cấu trúc runtime khác.
- **Native allocator và libc:** Bộ nhớ cấp phát bởi malloc hoặc allocator của thư viện.
- **Memory mapping:** File mapping và các vùng mmap.
- **Page cache và kernel-accounted memory:** Một số loại file cache, socket buffer và kernel memory có thể được tính vào cgroup tùy controller/kernel.

Do đó, -Xmx không nên bằng toàn bộ memory.max. Nếu heap chiếm hết cgroup limit, process vẫn cần memory cho native runtime, thread, direct buffer, GC và các thành phần khác. Cgroup OOM killer có thể kết thúc process trước khi JVM ném OutOfMemoryError: Java heap space.

Một mô hình ngân sách khái quát:

~~~text
Cgroup memory limit
  |
  +-- Java heap
  +-- Metaspace và class metadata
  +-- JIT code cache
  +-- Thread stacks
  +-- Direct buffers
  +-- GC/JVM native structures
  +-- JNI / native libraries
  +-- Memory mapping / file cache / kernel accounting
  +-- Phần dự phòng cho biến động tải
~~~

Các thành phần không nhất thiết cộng tuyến tính hoặc được đo giống nhau trên mọi kernel. Hãy dùng cgroup memory metrics và công cụ JVM để đo trong workload thực tế.

## 13. JVM chọn heap maximum từ container memory

HotSpot có thể dùng container memory để tính heap ergonomics khi khởi động. Các cờ thường gặp:

- -Xms: heap initial/minimum theo cấu hình JVM.
- -Xmx: heap maximum.
- -XX:InitialRAMPercentage: tỷ lệ bộ nhớ được JVM nhận biết dùng để tính initial heap trong các trường hợp áp dụng.
- -XX:MaxRAMPercentage: tỷ lệ bộ nhớ tối đa được JVM dùng để tính heap maximum.
- -XX:MaxRAM: giá trị RAM tối đa mà JVM dùng làm cơ sở ergonomics trong các trường hợp hỗ trợ.

Ví dụ cấu hình:

~~~bash
java -XX:MaxRAMPercentage=60 -XX:InitialRAMPercentage=25 -jar app.jar
~~~

Các tỷ lệ chỉ là ví dụ. Không có một tỷ lệ đúng cho mọi ứng dụng. Cần để lại headroom cho native memory, thread stacks, direct buffers, metaspace, GC và phần memory khác của cgroup.

Nếu dùng -Xmx cố định, giá trị này có thể vượt memory limit của môi trường đích. Nếu dùng MaxRAMPercentage, JVM tính dựa trên memory mà nó nhận biết tại thời điểm áp dụng ergonomics. Hành vi cụ thể phụ thuộc JDK và flags khác.

Đặc biệt với CRaC, tiến trình đã khởi động trước checkpoint. Không nên giả định JVM sẽ tính lại toàn bộ heap ergonomics như lần khởi động mới khi restore vào cgroup có memory limit khác. Heap maximum và nhiều cấu hình runtime đã được thiết lập khi JVM khởi động. Cần xác minh hành vi của JDK CRaC cụ thể và thiết kế checkpoint trong một resource envelope tương thích với môi trường restore.

## 14. Vì sao restore vào memory limit nhỏ hơn có thể thất bại?

Giả sử ứng dụng được warm-up trong container có memory limit 4 GiB và heap maximum 2,5 GiB. Checkpoint image có thể phản ánh một heap đã sử dụng 1,8 GiB, cùng native memory, thread stacks và page cache.

Nếu restore vào container chỉ có 2 GiB:

- Heap hiện tại cộng native memory có thể vượt giới hạn ngay khi process tiếp tục.
- JVM có thể cần cấp thêm memory cho GC, JIT hoặc thread.
- Kernel có thể reclaim mạnh khi vượt memory.high.
- Nếu không thể reclaim đủ, cgroup OOM killer có thể kết thúc process.
- Ứng dụng có thể bị kill mà không có Java heap OutOfMemoryError.
- Readiness có thể không hoàn tất do CPU/memory pressure.

Ngay cả khi heap đang dùng thấp hơn -Xmx, tổng process memory vẫn có thể vượt cgroup limit. -Xmx là giới hạn heap, không phải cam kết tổng RSS tối đa.

Restore vào memory limit lớn hơn thường ít rủi ro hơn về OOM, nhưng không tự động tăng heap maximum của JVM đã khởi động. Nếu muốn tận dụng giới hạn lớn hơn, cần tạo checkpoint từ JVM được khởi động với ergonomics phù hợp hoặc thiết kế runtime có khả năng điều chỉnh được hỗ trợ.

## 15. Memory pressure, reclaim và OOM events

Với cgroups v2, memory.events có thể cung cấp số lần xảy ra một số sự kiện. Ví dụ các trường có thể gồm:

~~~text
low 0
high 12
max 3
oom 1
oom_kill 1
~~~

Ý nghĩa tổng quát:

- low: sự kiện liên quan ngưỡng low protection.
- high: số lần vượt ngưỡng high và bị xử lý theo cơ chế memory pressure.
- max: số lần usage tiến gần/vượt hard max.
- oom: số lần cgroup đi vào OOM handling.
- oom_kill: số process bị OOM killer kết thúc.

Tập trường và chi tiết phụ thuộc kernel. memory.events.local nếu có chỉ phản ánh event tại cgroup hiện tại; memory.events có thể tổng hợp từ descendant theo ngữ nghĩa v2.

Khi điều tra restore chậm hoặc bị kill, cần đọc các event counter trước và sau thử nghiệm. Chỉ nhìn free -m trong container có thể không phản ánh đầy đủ cgroup limit hoặc memory pressure.

## 16. Direct memory và MaxDirectMemorySize

Nhiều thư viện networking và I/O dùng direct ByteBuffer để giảm copy giữa heap và native I/O. Direct memory không nằm trong Java heap theo cách thông thường nhưng vẫn tiêu thụ memory của process và cgroup.

Cờ:

~~~bash
-XX:MaxDirectMemorySize=512m
~~~

có thể giới hạn tổng direct buffer memory mà JVM quản lý theo cơ chế tương ứng. Nếu không đặt rõ, giá trị mặc định phụ thuộc JVM implementation và ergonomics. Một số native allocation không đi qua direct buffer pool và không bị giới hạn bởi cờ này.

Khi restore, buffer direct và native allocation đã tồn tại cần được tính vào footprint. Nếu ứng dụng tạo thêm nhiều direct buffer ngay sau restore, memory usage có thể tăng nhanh. Theo dõi direct buffer pool qua MXBeans hoặc JMX, đồng thời so sánh với memory.current.

Ví dụ đọc direct buffer pool:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

public final class BufferMetrics {
    public static void logDirectBuffers() {
        for (BufferPoolMXBean pool
                : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                System.out.println("directBufferCount=" + pool.getCount());
                System.out.println("directBufferUsedBytes=" + pool.getMemoryUsed());
                System.out.println("directBufferCapacityBytes=" + pool.getTotalCapacity());
            }
        }
    }
}
~~~

MXBean cung cấp góc nhìn về buffer pool do JVM quản lý; nó không đo toàn bộ native memory. Hãy kết hợp với Native Memory Tracking và cgroup metrics.

## 17. Thread count, stack memory và pids limit

Mỗi platform thread thường cần native stack memory. Giá trị stack phụ thuộc JVM, OS, kiến trúc và -Xss. Tạo quá nhiều thread làm tăng memory usage và có thể chạm giới hạn số process/thread.

Cgroups có thể áp dụng PIDs controller:

- cgroups v2: pids.current, pids.max, pids.events.
- cgroups v1: thường có pids.current, pids.max, pids.events nếu controller được bật.

Một Java process tạo thread mới cũng tiêu thụ PID slot theo cách kernel accounting áp dụng. Nếu pids.max quá thấp, tạo thread có thể thất bại dù heap còn trống.

Với CRaC, thread pool có thể đã được tạo ở môi trường nguồn. Nếu ứng dụng khởi động với nhiều processor và tạo nhiều worker, restore vào môi trường có giới hạn PIDs hoặc memory thấp hơn có thể gây áp lực. Các thread mới cần tạo sau restore có thể thất bại.

Cần theo dõi:

- Số platform thread đang sống.
- Số thread trong executor và queue.
- Thread stack size.
- pids.current và pids.max.
- Lỗi unable to create native thread.
- Native memory và cgroup memory current.

Không nên giải quyết lỗi thread bằng cách chỉ tăng heap. Lỗi tạo thread thường liên quan native memory, PIDs limit, OS limit hoặc stack allocation.

## 18. Kubernetes requests, limits và QoS

Trong Kubernetes, container resources thường được khai báo trong resources.requests và resources.limits.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "1"
    memory: "2Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
~~~

Trong ví dụ:

- CPU request là 1 core-equivalent, dùng trong scheduling và phân bổ tương ứng.
- CPU limit là 2 core-equivalent, thường được thực thi bằng quota.
- Memory request là 2 GiB, dùng cho scheduling.
- Memory limit là 3 GiB, thường được áp dụng như giới hạn memory cgroup.

Request không phải hard guarantee rằng container sẽ luôn nhận đúng lượng CPU time đó khi node quá tải. Memory request cũng không phải hard ceiling. Memory limit mới là giới hạn thường dẫn đến OOM enforcement.

QoS class của Pod được xác định từ requests/limits theo quy tắc Kubernetes. QoS ảnh hưởng đến thứ tự eviction trong một số tình huống node pressure, nhưng không thay thế việc đọc cgroup limit của container.

Khi restore checkpoint, cần xác định checkpoint được tạo với resource requests/limits nào và restore vào Pod/container có cấu hình nào. Một manifest có cùng image nhưng resources khác có thể tạo ra runtime behavior khác đáng kể.

## 19. CPU và memory khác nhau giữa môi trường nguồn và đích

Một ứng dụng có thể được warm-up trên máy build hoặc staging với CPU và memory rộng rãi, sau đó restore vào container production có quota thấp hơn. Các khác biệt thường gặp:

| Thuộc tính | Môi trường nguồn | Môi trường đích | Rủi ro |
|---|---|---|---|
| CPU quota | 4 CPU | 1 CPU | Throttling, readiness chậm |
| Cpuset | 0-7 | 2-3 | Tập CPU hẹp hơn |
| JVM availableProcessors | 4 | JVM đã khởi động với 4 | Thread pool/GC concurrency có thể quá cao |
| Memory max | 8 GiB | 2 GiB | OOM hoặc memory reclaim |
| Heap max | 5 GiB | JVM đã cấu hình 5 GiB | Heap ceiling vượt giới hạn cgroup |
| PIDs max | 4096 | 512 | Tạo thread mới thất bại |
| Direct memory | 1 GiB sử dụng | Headroom nhỏ | Native memory pressure |
| CPU weight | Cao | Thấp | Chậm khi node contention |

Không nên giả định restore sẽ tự điều chỉnh toàn bộ các giá trị theo cgroup đích. Một số tài nguyên có thể được cập nhật hoặc kiểm tra lại bởi runtime/integration; các quyết định ergonomics đã thực hiện khi khởi động có thể vẫn còn. Phải kiểm tra hành vi thực tế của JDK CRaC và thư viện.

## 20. Thiết kế resource envelope cho checkpoint image

Một checkpoint image nên được tạo trong một môi trường có resource envelope tương thích với nơi restore. Resource envelope là tập giới hạn và điều kiện tài nguyên mà ứng dụng cần để hoạt động đúng, ví dụ:

- CPU quota tối thiểu và cpuset phù hợp.
- Memory limit đủ cho heap và native memory.
- PIDs limit đủ cho thread pool và runtime.
- Quyền truy cập cgroup và các kernel interface cần thiết.
- Các dependency ngoài có thể truy cập sau restore.
- Giới hạn I/O và network phù hợp với workload.

Một chiến lược là tạo checkpoint ở cùng loại container resource profile với môi trường đích. Nếu cần dùng một checkpoint cho nhiều loại instance, hãy thiết kế theo profile nhỏ nhất được hỗ trợ và kiểm thử các profile lớn hơn/nhỏ hơn.

Không nên tạo image với heap đã warm-up rất lớn rồi restore vào container nhỏ chỉ vì heap occupancy tại thời điểm checkpoint đang thấp. JVM vẫn có thể cần native memory, GC metadata và headroom khi tiếp tục chạy.

## 21. Chọn heap và native memory budget

Một cách lập ngân sách ban đầu:

~~~text
Container memory limit
  = heap budget
  + metaspace/code cache
  + thread stacks
  + direct buffers
  + GC/JVM native memory
  + JNI/native libraries
  + kernel/file cache accounting
  + safety headroom
~~~

Không có tỷ lệ cố định cho mọi ứng dụng. Hãy đo:

- Heap committed và used sau warm-up.
- Peak heap trong tải đại diện.
- Metaspace và code cache.
- Direct buffer usage.
- Thread count và stack footprint.
- Native memory tracking categories.
- Cgroup memory.current và memory.stat.
- Memory events trong thời gian tải và restore.

Native Memory Tracking (NMT) có thể bật khi khởi chạy JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó dùng jcmd để xem summary nếu công cụ và quyền runtime cho phép:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT có overhead và chỉ theo dõi các allocation thuộc phạm vi JVM mà NMT hỗ trợ; nó không phải phép đo toàn bộ cgroup memory. Dùng cùng cgroup metrics để hiểu phần memory ngoài heap/native mà JVM không thống kê.

## 22. Cấu hình JVM cho container

Ví dụ một lệnh chạy có cấu hình rõ ràng:

~~~bash
java \
  -XX:MaxRAMPercentage=55 \
  -XX:InitialRAMPercentage=20 \
  -XX:MaxDirectMemorySize=384m \
  -XX:ActiveProcessorCount=2 \
  -jar app.jar
~~~

Đây là cấu hình minh họa, không phải khuyến nghị mặc định. Trước khi dùng:

- Xác nhận JDK hỗ trợ các cờ.
- Đo memory footprint thực tế.
- Đảm bảo heap không chiếm hết memory limit.
- Xác định số processor hợp lý so với quota và cpuset.
- Đo số thread, direct buffer và native allocation.
- Kiểm tra cgroup ancestor limits.
- Thử tải cực đại và restore.

Nếu -Xmx được đặt trực tiếp, giá trị này thường có ưu tiên so với việc tính heap maximum theo percentage. Cần xem toàn bộ flags để hiểu JVM thực sự dùng giá trị nào. Không nên đồng thời đặt nhiều cờ mâu thuẫn rồi chỉ suy luận từ một property.

## 23. Chẩn đoán cgroup từ trong container

Với cgroups v2, nếu mount root và path tương ứng đã được xác định, các lệnh ví dụ có thể là:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

Đường dẫn ở trên chỉ là ví dụ phổ biến khi container thấy cgroup của mình ở mount root. Trong hierarchy lồng nhau, hãy ghép cgroup path từ /proc/self/cgroup với mount root phù hợp; kiểm tra ancestor để tìm limit có hiệu lực.

Với cgroups v1, các file có thể nằm ở mount riêng, ví dụ:

~~~bash
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us
cat /sys/fs/cgroup/cpu/cpu.cfs_period_us
cat /sys/fs/cgroup/cpu/cpu.shares
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.failcnt
~~~

Đừng chạy nguyên các đường dẫn mẫu nếu hệ thống mount khác. Trước tiên xác định controller mount point từ mountinfo.

## 24. Đo CPU và memory của JVM cùng cgroup

Cần ghép số liệu JVM với số liệu kernel:

| Nguồn | Dữ liệu | Câu hỏi trả lời |
|---|---|---|
| Runtime.availableProcessors() | Processor count JVM nhìn thấy | JVM đang dùng bao nhiêu processor cho ergonomics? |
| JVM flags | Heap, GC, processor override, direct memory | JVM được cấu hình thế nào? |
| jcmd VM.native_memory | Native allocation thuộc phạm vi NMT | Native memory tăng ở nhóm nào? |
| Heap MXBeans / GC logs | Heap used/committed, pause, allocation | Heap có gần giới hạn không? |
| BufferPoolMXBean | Direct/mapped buffer | I/O buffer tiêu thụ bao nhiêu? |
| ThreadMXBean / thread dump | Số thread và stack traces | Thread có tăng hoặc bị kẹt không? |
| cpu.stat | Usage và throttling | Cgroup có bị throttle không? |
| memory.current, memory.stat | Memory usage và phân loại | Cgroup memory tăng ở đâu? |
| memory.events | High/max/OOM counters | Có memory pressure hoặc OOM event không? |
| pids.current | Process/thread count theo cgroup | Có gần PIDs limit không? |

Chụp số liệu tại ít nhất bốn thời điểm: sau startup, sau warm-up, ngay trước checkpoint và sau restore khi đã có tải. Nếu có thể, ghi thêm peak trong tải đại diện.

## 25. Quy trình chuẩn bị checkpoint và restore với resource limits

Một quy trình triển khai nên gồm:

1. Xác định resource profile của môi trường đích: CPU quota, cpuset, memory max/high, swap, PIDs và giới hạn ancestor.
2. Chọn JDK CRaC và flags JVM phù hợp với profile đó.
3. Khởi chạy ứng dụng trong môi trường có giới hạn tương đương hoặc được chứng minh tương thích.
4. Để Spring/framework và các dependency hoàn tất warm-up.
5. Đo heap, native memory, direct buffers, thread count và cgroup usage.
6. Ngừng ingress và background work trước checkpoint theo lifecycle của ứng dụng.
7. Tạo checkpoint và lưu kèm metadata về JDK build, flags, cgroup profile và image version.
8. Restore trong môi trường đích với limits dự kiến.
9. Đo lại cgroup và JVM metrics, kiểm tra throttling, memory pressure và PIDs.
10. Chạy health check có đại diện cho workload thực tế.
11. Chỉ mở readiness khi dependency và resource budget đủ đáp ứng.
12. Chạy tải kiểm chứng để xác nhận không có OOM, throttle kéo dài hoặc queue tăng không kiểm soát.

Nếu restore target có resource nhỏ hơn profile đã kiểm chứng, coi đó là một thay đổi cấu hình cần thử nghiệm riêng. Không nên dùng một checkpoint image cho mọi resource tier mà không đo.

## 26. Ví dụ Kubernetes deployment

Ví dụ sau minh họa một container có request/limit tách biệt:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crac-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: crac-service
  template:
    metadata:
      labels:
        app: crac-service
    spec:
      containers:
        - name: app
          image: example/crac-service:latest
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "3Gi"
~~~

Đây chỉ là ví dụ cấu trúc. Cấu hình thực tế còn phụ thuộc checkpoint/restore integration, runtime class, volume lưu checkpoint, security context và yêu cầu của JDK. Requests/limits cần được chọn theo phép đo của ứng dụng.

Khi so sánh môi trường tạo checkpoint và môi trường restore, hãy kiểm tra Pod spec, container spec, cgroup của process và các giới hạn ở node/parent. Không suy ra resource thực tế chỉ từ file YAML vì admission policy, LimitRange, runtime và ancestor cgroup có thể ảnh hưởng cấu hình cuối cùng.

## 27. Readiness khi CPU hoặc memory không đủ

Sau restore, process có thể vẫn sống nhưng chưa đủ khả năng phục vụ. Ví dụ:

- Memory pressure làm mọi request chậm.
- CPU throttling khiến health check timeout.
- Thread pool đã có nhiều worker nhưng PIDs limit không cho tạo thêm thread.
- GC liên tục chạy vì heap gần cạn.
- Direct buffer allocation thất bại.
- Executor queue tăng nhanh hơn tốc độ xử lý.
- Background refresh hoặc lease renewal trễ do thiếu CPU.

Readiness không nên chỉ kiểm tra process còn tồn tại. Cần xác minh các thành phần thiết yếu và khả năng xử lý tối thiểu. Tuy nhiên, health check cũng không nên tạo tải lớn hoặc tạo side effect nghiệp vụ.

Có thể dùng một ngưỡng vận hành cho CPU throttling, memory headroom, GC pause, executor queue và PIDs usage. Ngưỡng cần dựa trên baseline đo được. Nếu resource budget không đủ, instance nên ở trạng thái chưa ready hoặc bị thay thế bằng profile phù hợp thay vì nhận traffic rồi thất bại hàng loạt.

## 28. Những lỗi thường gặp

**Dùng CPU host làm CPU capacity của container.** JVM có thể bị quota hoặc cpuset giới hạn. Kiểm tra cgroup và availableProcessors().

**Nhầm CPU request với CPU limit.** Request phục vụ scheduling; limit mới là hard quota thường được thực thi. Đọc cgroup thực tế.

**Chỉ đọc cpu.max ở cgroup con.** Ancestor có thể áp dụng quota chặt hơn. Kiểm tra toàn bộ hierarchy.

**Cho rằng cpu.weight là số core.** Weight là trọng số tương đối khi cạnh tranh, không phải CPU quota.

**Đặt ActiveProcessorCount cao hơn CPU quota.** Cờ này không tạo thêm CPU time. Có thể gây concurrency và thread count quá cao.

**Đặt Xmx bằng memory.max.** Heap không phải toàn bộ process memory. Chừa ngân sách cho native memory, thread, direct buffers, GC và kernel accounting.

**Cho rằng MaxRAMPercentage sẽ tự tính lại sau restore.** JVM đã khởi động và có thể giữ quyết định ergonomics từ nguồn. Xác minh JDK CRaC cụ thể.

**Chỉ kiểm tra heap usage.** Cgroup có thể OOM do native memory hoặc page cache dù heap còn chỗ. Theo dõi memory.current và memory.events.

**Bỏ qua pids.max.** Thread creation có thể thất bại dù memory còn đủ. Theo dõi PIDs và số thread.

**Checkpoint trên máy lớn rồi restore vào container nhỏ mà không thử.** Heap maximum, thread pool và native footprint có thể vượt khả năng đích. Tạo resource profile tương thích và kiểm thử.

**Chỉ kiểm tra ngay sau restore.** Tải tăng có thể làm memory và CPU vượt ngưỡng sau warm-up. Chạy workload đại diện và theo dõi peak.

## 29. Checklist tương thích cgroups, CPU và memory

- [ ] Đã xác định process thuộc cgroups v1 hay v2 chưa?
- [ ] Đã xác định đúng cgroup path và mount root từ /proc/self/cgroup và mountinfo chưa?
- [ ] Đã kiểm tra quota CPU ở cgroup hiện tại và ancestor chưa?
- [ ] Đã kiểm tra cpuset hiệu lực chưa?
- [ ] Đã phân biệt quota, weight/share và Kubernetes request/limit chưa?
- [ ] Đã đọc CPU throttling statistics chưa?
- [ ] Đã xác minh Runtime.availableProcessors() và JVM container awareness chưa?
- [ ] ActiveProcessorCount có phù hợp với quota và workload không?
- [ ] Đã kiểm tra memory.current, memory.high, memory.max và ancestor limits chưa?
- [ ] Đã xem memory.events để phát hiện pressure/OOM chưa?
- [ ] Heap budget có chừa đủ native memory, direct buffer, metaspace, code cache và thread stack không?
- [ ] Đã kiểm tra direct memory và Native Memory Tracking chưa?
- [ ] Đã kiểm tra pids.current và pids.max chưa?
- [ ] Resource profile tạo checkpoint có tương thích với môi trường đích không?
- [ ] Đã đo CPU, memory, GC, thread và readiness trước/sau restore chưa?
- [ ] Đã chạy tải đại diện trong đúng cgroup limits của môi trường đích chưa?

## Kết luận

Cgroups quyết định giới hạn tài nguyên mà process thực sự có thể sử dụng trong container. CPU quota, cpuset và CPU weight có ý nghĩa khác nhau; memory high và memory max cũng là hai ngưỡng khác nhau. JVM có thể nhận biết một số giới hạn container khi khởi động, nhưng hành vi phụ thuộc JDK và không nên giả định mọi quyết định ergonomics sẽ được tính lại khi restore.

Để checkpoint image hoạt động ổn định trong môi trường đích, hãy đo resource envelope thực tế, chọn heap và native memory budget có headroom, đặt mức concurrency phù hợp với CPU quota, kiểm tra PIDs limit và theo dõi throttling/OOM events. Tạo checkpoint trong profile tương thích với nơi restore, sau đó thử restore và chạy tải đại diện dưới đúng cgroups limits. Chỉ khi JVM, ứng dụng và toàn bộ container có đủ CPU, memory và thread capacity thì restore mới có thể chuyển thành một instance sẵn sàng phục vụ ổn định.
