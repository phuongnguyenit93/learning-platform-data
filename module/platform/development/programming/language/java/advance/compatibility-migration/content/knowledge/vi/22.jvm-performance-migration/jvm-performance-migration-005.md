# Nhận diện CPU, bộ nhớ và giới hạn cgroups trong container

## 1. Vì sao container thay đổi cách JVM nhận diện tài nguyên?

Khi ứng dụng Java chạy trực tiếp trên máy vật lý hoặc máy ảo, JVM thường quan sát tài nguyên mà hệ điều hành cung cấp cho tiến trình. Trong container, tiến trình Java vẫn dùng kernel của host nhưng được đặt trong các cơ chế cô lập và quản lý tài nguyên, đặc biệt là **Linux control groups (cgroups)**.

Điều này tạo ra hai lớp thông tin rất khác nhau:

- **Tài nguyên host**: số CPU logic và tổng RAM của node/máy chủ.
- **Tài nguyên hiệu dụng của container**: mức CPU được phép dùng, quota thời gian CPU, tập CPU được phép chạy, giới hạn bộ nhớ và các ràng buộc của cgroup.

Ví dụ một node Kubernetes có 32 CPU logic và 128 GiB RAM nhưng container chạy Java được cấu hình giới hạn 2 CPU và 2 GiB RAM. Nếu JVM quyết định số luồng GC, số luồng biên dịch JIT hoặc dung lượng heap như thể nó có 32 CPU và 128 GiB RAM, ứng dụng có thể bị tăng bộ nhớ, cạnh tranh CPU, throttling hoặc bị hệ thống kết thúc vì vượt giới hạn container.

Khi **Java Advance Compatibility Migration**, điều này đặc biệt quan trọng vì hỗ trợ nhận diện cgroups và các quy tắc JVM ergonomics đã phát triển qua các phiên bản và bản vá JDK. Việc nâng JDK, đổi nhà cung cấp JDK, đổi Linux distribution hoặc chuyển cgroups v1 sang v2 có thể làm những giá trị JVM tự nhận diện thay đổi dù mã nguồn ứng dụng không đổi.

Mục tiêu của bài học:

1. Hiểu các chỉ số CPU và bộ nhớ mà Linux cgroups áp dụng cho container.
2. Phân biệt giới hạn cứng, cơ chế điều phối ưu tiên và thông tin tài nguyên của host.
3. Hiểu JVM container awareness, các chỉ số Runtime.availableProcessors và Runtime.maxMemory.
4. Biết cách quan sát cgroups v1/v2, CPU throttling và container OOM.
5. Cấu hình heap, native memory và thread pools theo workload thực tế thay vì suy luận từ một con số RAM.
6. Kiểm tra hành vi trên Docker/Kubernetes và các phiên bản JDK được hỗ trợ.
7. Lập compatibility baseline để phát hiện regression về hiệu năng và giới hạn tài nguyên sau migration.

## 2. Các khái niệm: CPU, quota, cpuset và memory limit

### 2.1. CPU logic của host

Một máy có thể được hệ điều hành nhận diện là có N logical processors. Các CPU logic này không nhất thiết tương ứng N lõi vật lý và cũng không có nghĩa container được dùng toàn bộ N CPU.

Trong Linux, lệnh như nproc hoặc lscpu có thể hiển thị những góc nhìn khác nhau về CPU; một số công cụ có thể tính đến affinity/cgroup tùy phiên bản. Khi điều tra cần ghi rõ nguồn của số liệu.

### 2.2. CPU quota

**CPU quota** giới hạn tổng thời gian CPU mà nhóm tiến trình có thể tiêu thụ trong một chu kỳ điều phối.

Ví dụ: quota 150.000 microsecond trong period 100.000 microsecond tương ứng ngân sách khoảng **1,5 CPU** ở mức tổng thời gian tính toán. Đây không phải 1,5 lõi vật lý được cấp phát cố định.

Khi workload tiêu thụ hết quota trước khi chu kỳ kết thúc, cgroup có thể bị **CPU throttling** đến kỳ tiếp theo, làm tăng latency dù host vẫn có lõi CPU nhàn rỗi.

### 2.3. Cpuset và CPU affinity

**Cpuset** giới hạn các CPU logic mà tiến trình được phép chạy trên đó. Ví dụ, container có thể chỉ được chạy trên CPU 4 và CPU 5, tương đương một tập hai CPU logic.

Cpuset và quota là hai ràng buộc riêng:

- Cpuset 4 CPU, quota tương đương 1 CPU: tiến trình có thể được scheduler cho chạy trên các CPU trong tập, nhưng tổng thời gian CPU bị giới hạn khoảng 1 CPU.
- Cpuset 2 CPU, quota không giới hạn: tiến trình không thể thực sự chạy trên nhiều hơn 2 CPU logic cùng thời điểm, dù host có nhiều CPU khác.

Ngoài cpuset, process affinity còn có thể bị thay đổi bằng cơ chế khác. Khi kiểm tra CPU hiệu dụng cần xem tổng thể chính sách.

### 2.4. CPU weight hoặc shares

CPU shares (cgroups v1) và CPU weight (cgroups v2) thường phản ánh **mức ưu tiên tương đối khi tài nguyên CPU bị tranh chấp**. Chúng không phải một hard cap tương đương quota.

Ví dụ hai cgroup có weight khác nhau có thể chia thời gian CPU theo tỷ lệ tương đối khi cùng tranh chấp; nếu host đang rảnh, cgroup có weight thấp vẫn có thể dùng nhiều CPU hơn phần chia trong trạng thái tranh chấp, miễn các giới hạn khác cho phép.

Vì vậy, không được đồng nhất Kubernetes CPU request với CPU limit. Request thường liên quan scheduling và quyền được phân bổ tài nguyên; limit có thể được thực thi bằng CPU quota khi cấu hình cơ chế đó.

### 2.5. Memory limit

Memory cgroup có thể đặt giới hạn tối đa cho lượng bộ nhớ được tính vào nhóm. Giới hạn này không chỉ là heap Java: nó liên quan đến các trang bộ nhớ được hệ thống tính vào cgroup, bao gồm nhiều loại bộ nhớ của tiến trình và một số tài nguyên kernel/page cache tùy cơ chế/kernel.

Java heap là một phần quan trọng nhưng **không phải toàn bộ bộ nhớ dùng bởi tiến trình JVM**. Cấu hình Xmx bằng đúng memory limit của container thường không an toàn vì còn phần non-heap/native.

## 3. Cgroups là gì và vì sao có hai phiên bản?

Linux cgroups giúp nhóm các process và quản lý/quan sát tài nguyên như CPU, memory, pids và I/O. Container runtime dùng cgroups cùng với namespaces, filesystem và các cơ chế khác để triển khai cô lập tiến trình và resource controls.

Hai thế hệ thường gặp:

- **cgroups v1**: các controller như cpu, cpuacct, cpuset, memory có thể dùng các hierarchy/mount khác nhau, với các file cấu hình riêng.
- **cgroups v2**: unified hierarchy, API file và cách biểu diễn mới như cpu.max, cpu.weight, memory.max, memory.current.

Một máy có thể dùng cấu hình v1, v2 hoặc hỗn hợp trong những trường hợp hệ thống cụ thể. Trên container hiện đại, thường gặp v2, nhưng không nên giả định mọi môi trường đều giống nhau.

### 3.1. So sánh nhanh các file quan trọng

| Mục đích | cgroups v1 | cgroups v2 |
|---|---|---|
| CPU quota | cpu.cfs_quota_us | cpu.max |
| CPU period | cpu.cfs_period_us | Phần thứ hai của cpu.max |
| CPU priority tương đối | cpu.shares | cpu.weight |
| CPU throttling | cpu.stat | cpu.stat |
| CPU affinity/cpuset | cpuset.cpus và các file hiệu dụng tùy kernel | cpuset.cpus, cpuset.cpus.effective |
| Memory hard limit | memory.limit_in_bytes | memory.max |
| Memory hiện dùng | memory.usage_in_bytes | memory.current |
| Memory soft/high boundary | Có cơ chế v1 riêng, tùy controller/kernel | memory.high |
| Memory events/OOM | memory.failcnt, memory.oom_control và nguồn khác | memory.events |
| Swap-related limits | Các file memsw khi được bật | memory.swap.max, memory.swap.current |
| PIDs limit | pids.max | pids.max |

Tên file v1 phụ thuộc nơi controller được mount. Không phải container nào cũng có các file này dưới đúng một đường dẫn /sys/fs/cgroup/memory hoặc /sys/fs/cgroup/cpu. Cần đọc mount information và cgroup membership thực tế.

### 3.2. Cách phát hiện trong container Linux

Ví dụ lệnh quan sát:

~~~bash
cat /proc/self/cgroup
cat /proc/self/mountinfo
ls /sys/fs/cgroup
~~~

Với unified cgroups v2, /proc/self/cgroup thường có entry dạng:

~~~text
0::/some/container/path
~~~

và cgroup filesystem có thể hiển thị các file như cpu.max, memory.max. Nhưng layout thực tế thay đổi theo runtime, delegation và mount namespace.

Với cgroups v1, /proc/self/cgroup thường có nhiều dòng theo controller. Không nên dùng một regex cứng cho mọi Docker, containerd, Kubernetes hoặc systemd version.

### 3.3. Giới hạn có thể kế thừa từ cgroup cha

Trong hệ thống phân cấp, tiến trình có thể chịu giới hạn từ cgroup của chính nó hoặc từ một ancestor. Ví dụ container nằm trong một pod/slice đã bị giới hạn thấp hơn. Chỉ đọc một file memory.max tại đường dẫn bạn nghĩ là container có thể bỏ sót ràng buộc hiệu dụng.

Nếu cgroup con hiển thị max nhưng cgroup cha bị giới hạn, resource còn thực sự sử dụng vẫn bị ràng buộc bởi ancestor. JVM và công cụ chẩn đoán có thể có logic tìm giới hạn hiệu dụng khác nhau theo phiên bản.

Khi kết quả JVM không khớp với file trực tiếp, hãy xem toàn bộ cgroup path, hierarchy và các giới hạn ở cấp pod/node/systemd.

## 4. CPU quota trên cgroups v1

Ở cgroups v1, scheduler CPU controller thường dùng:

- cpu.cfs_quota_us: số microsecond CPU time tối đa cho phép trong một period.
- cpu.cfs_period_us: độ dài chu kỳ, đơn vị microsecond.

Ví dụ:

~~~text
cpu.cfs_quota_us  = 150000
cpu.cfs_period_us = 100000
~~~

Tỷ lệ quota/period là:

~~~text
150000 / 100000 = 1.5 CPU
~~~

Đây là ước lượng năng lực CPU theo thời gian, không phải thông báo JVM sẽ báo chính xác Runtime.availableProcessors() = 1.5. Phương thức Java trả về số nguyên, và chính sách làm tròn/kết hợp quota với cpuset phụ thuộc JDK và các giới hạn hiện hành.

Khi quota không áp dụng, file quota v1 thường có giá trị đặc biệt như -1; cần kiểm tra theo kernel/controller đang dùng.

### 4.1. CFS throttling

Ví dụ /sys/fs/cgroup/cpu/cpu.stat trong một môi trường v1:

~~~text
nr_periods 10000
nr_throttled 3600
throttled_time 78000000000
~~~

Các giá trị là ví dụ minh họa, không phải kết quả đo từ hệ thống cụ thể.

Trong cgroups v1, throttled_time thường được biểu diễn bằng nanosecond. nr_throttled tăng cho biết đã có những chu kỳ cgroup bị throttling. Không nên suy ra tỷ lệ thất thoát công suất một cách chính xác chỉ từ nr_throttled / nr_periods; cần xem thời gian throttling, workload và lịch phân phối CPU.

Khi ứng dụng Java có độ trễ tăng mạnh ở tải cao nhưng CPU usage dường như “không đầy node”, throttling theo quota có thể là nguyên nhân cần xem xét.

## 5. CPU quota và weight trên cgroups v2

Ở cgroups v2, quota và period được biểu diễn trong cùng file cpu.max:

~~~text
150000 100000
~~~

Nghĩa là quota 150.000 microsecond trên period 100.000 microsecond, tương đương khoảng 1,5 CPU.

Nếu không có quota, giá trị có thể là:

~~~text
max 100000
~~~

Trong trường hợp này cpu.max không áp hard quota ở cgroup đó, nhưng cpuset, ancestor cgroup và các policy khác vẫn có thể giới hạn CPU thực tế.

Ví dụ:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.weight
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
~~~

Các đường dẫn chỉ trực tiếp khả dụng khi layout/mount namespace của container trình bày file tại đó.

### 5.1. CPU weight không phải hard quota

cpu.weight là trọng số điều phối tương đối của cgroup v2. Nếu CPU limit chưa được đặt và weight thấp, workload vẫn có thể sử dụng nhiều CPU khi node nhàn rỗi. Vì vậy:

- Không suy CPU limit bằng cách chia cpu.weight cho một hằng số rồi xem là số core cố định.
- Không tự dùng Kubernetes CPU request như thể đó là quota đã được thực thi.
- Nên test ở môi trường có contention, quota và cpuset đại diện cho production.

Một số JDK cũ từng tính CPU count dựa trên CPU shares/weight theo chính sách riêng. Các release và bản vá mới có thể xử lý khác; khi migration phải đo Runtime.availableProcessors() trên đúng JDK, không dựa vào suy luận chung.

### 5.2. Throttling trên cgroups v2

cpu.stat có thể chứa các field như:

~~~text
usage_usec 12000000
user_usec 9000000
system_usec 3000000
nr_periods 15000
nr_throttled 4300
throttled_usec 2200000
~~~

Giá trị trên chỉ là ví dụ. Các tên field có thể phụ thuộc kernel/controller; khi có CPU bandwidth control, nr_throttled và throttled_usec giúp đánh giá mức throttling.

Nếu quota làm nghẽn request xử lý CPU-heavy, tăng kích thước thread pool không tạo thêm CPU time. Thậm chí nó có thể làm tăng context switching, queueing và memory do stack của nhiều threads.

## 6. CPU hiệu dụng mà JVM nhận diện

Trong Java, một chỉ số nền tảng là:

~~~java
int processors = Runtime.getRuntime().availableProcessors();
~~~

Con số này được JVM xác định từ thông tin CPU và policy khả dụng theo triển khai; trong JVM có container support, nó có thể chịu ảnh hưởng bởi cgroup quota/cpuset và các tùy chọn JVM.

Đây **không nhất thiết là số CPU vật lý của host** và cũng không phải bảo đảm throughput tương ứng với số đó.

### 6.1. CPU fractional quota và số nguyên

Ví dụ container có quota tương đương 0,5 CPU. Runtime.availableProcessors() vẫn trả về một số nguyên dương, không thể trả 0,5. Một số lượng thread pool tự cấu hình theo availableProcessors có thể dùng ít nhất một worker, nhưng scheduler vẫn throttling sau khi hết quota.

Với quota 1,5 CPU, JVM có thể chọn số nguyên theo chính sách và kết hợp các ràng buộc khác. Đừng dựa vào một quy tắc làm tròn cố định khi chưa biết JDK vendor/release.

### 6.2. CPU quota ảnh hưởng JVM ergonomics

Số processor hiệu dụng có thể ảnh hưởng đến:

- Số luồng GC trong một số collectors và pha GC.
- Số compiler threads/JIT hoặc chính sách tối ưu hóa.
- Một số default của ForkJoinPool.commonPool và parallel streams.
- Một số library/framework tính default thread pool bằng Runtime.availableProcessors().
- Quyết định về concurrent phases, workload sizing và parallelism.

Không phải mọi thread pool tự động lấy availableProcessors; nhiều thư viện có cấu hình riêng hoặc sử dụng số luồng cố định. Cần kiểm tra từng component khi regression hiệu năng.

### 6.3. Tùy chọn -XX:ActiveProcessorCount

Khi cần cố định cách JVM nhìn số processor cho các quyết định ergonomics:

~~~bash
java -XX:ActiveProcessorCount=2 -jar application.jar
~~~

Tùy chọn này có thể override số processor mà JVM báo cho nhiều mục đích runtime, tùy HotSpot/JDK sử dụng. Tuy nhiên, **nó không thay CPU quota** của kernel và không cấp thêm CPU resources cho container.

Nếu kernel chỉ cho 0,5 CPU mà đặt ActiveProcessorCount=8, tiến trình không có thêm 7,5 CPU thực; JVM và thư viện có thể tạo nhiều worker hơn rồi chịu throttling nặng hơn.

Chỉ dùng override có chủ đích khi có số liệu benchmark và hiểu tác động lên GC, ForkJoinPool, thread pools. Không dùng flag để che một cấu hình cgroup sai.

## 7. Kubernetes CPU requests và limits

Trong Kubernetes, resource requests và limits có vai trò khác nhau:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-cgroup-demo
spec:
  containers:
    - name: app
      image: example/java-app:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "1500m"
          memory: "1Gi"
~~~

Đây là manifest minh họa; image example/java-app:1.0 là placeholder, không phải image được tạo sẵn.

Diễn giải:

- requests.cpu = 500m tương ứng 0,5 CPU dùng cho quyết định scheduling/đảm bảo tài nguyên theo cơ chế cluster.
- limits.cpu = 1500m tương ứng 1,5 CPU dưới cơ chế giới hạn CPU thông thường; trên Linux nó thường được áp dụng qua quota của CPU controller nếu cấu hình tương ứng được bật.
- requests.memory = 512Mi giúp scheduler tính tài nguyên cần thiết.
- limits.memory = 1Gi thiết lập giới hạn bộ nhớ của container theo runtime/kubelet policy.

**Request không phải hard cap**. Nếu chỉ đặt CPU request mà không có CPU limit, CPU time hiệu dụng có thể phụ thuộc node contention, shares/weight, affinity và policy cluster.

### 7.1. Kubernetes CPU throttling

Với container bị CPU limit, khi sử dụng vượt quota trong period nó có thể bị throttling. Điều này có thể làm:

- P95/P99 request latency tăng.
- GC pauses/concurrent GC tiến triển chậm.
- Event loop, executor và background jobs xử lý queue chậm.
- Health checks timeout hoặc probe fail dưới tải.

Nên theo dõi metric từ cgroup/container monitoring như throttled periods, throttled time và CPU usage, sau đó đối chiếu với request latency và application saturation.

### 7.2. CPU requests và hiệu năng JVM không tương đương

Giả sử:

~~~text
requests.cpu = 250m
limits.cpu   = 2
~~~

JVM có thể nhận diện processor count dựa trên quota, cpuset và chính sách của JDK, chứ không nhất thiết dùng 250m làm số CPU cố định. Khi node có contention, CPU shares/weight vẫn có thể ảnh hưởng mức cạnh tranh.

Do đó, tối ưu concurrency nên dựa trên **thời gian CPU thực tế, throttling, queue depth và latency**, không chỉ một giá trị requests.cpu trong YAML.

## 8. Memory cgroup v1

Ở cgroups v1, hai file thường gặp:

~~~text
memory.limit_in_bytes
memory.usage_in_bytes
~~~

Các file có thể nằm trong một memory controller mount tương ứng, chẳng hạn /sys/fs/cgroup/memory trên một số môi trường.

Ví dụ:

~~~bash
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.failcnt
~~~

Đường dẫn và khả năng truy cập phụ thuộc container runtime/kernel.

### 8.1. Giá trị lớn không đồng nghĩa container có nhiều RAM

Trong cgroups v1, khi memory limit không bị ràng buộc theo cách thông thường, file limit có thể chứa một giá trị số rất lớn dùng làm biểu diễn gần như unlimited. Không nên coi đó là RAM vật lý thật để tính Xmx.

Khi JVM đọc container limits, nó phải phân biệt giới hạn khả dụng với các giá trị biểu thị không bị giới hạn, và có thể đối chiếu physical memory/ancestor limits tùy implementation.

### 8.2. Bộ nhớ cgroup không đồng nhất với Java heap

memory.usage_in_bytes phản ánh mức sử dụng bộ nhớ được memory controller accounting, không bằng Runtime.totalMemory hay Runtime.maxMemory.

Trong container có thể có:

- Java heap committed/resident pages.
- Metaspace, class metadata và code cache.
- Thread stacks và runtime native allocations.
- DirectByteBuffer, memory mapped files và native libraries.
- GC native structures, JIT/compiler memory.
- Page cache và các memory charges khác theo kernel/controller.

Vì vậy, một ứng dụng heap mới dùng 700 MiB vẫn có thể bị OOM kill nếu memory limit là 1 GiB và các phần còn lại chiếm vượt ngân sách.

## 9. Memory cgroup v2

Trong cgroups v2, các file quan trọng gồm:

~~~text
memory.max
memory.current
memory.high
memory.events
memory.stat
memory.swap.max
memory.swap.current
~~~

Một ví dụ:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.events
~~~

### 9.1. memory.max

memory.max là hard limit của cgroup theo controller. Nếu file chứa:

~~~text
1073741824
~~~

thì mức đó tương đương 1 GiB trong ví dụ. Nếu chứa:

~~~text
max
~~~

nghĩa là không đặt hard limit tại cgroup đó; các ancestor và ràng buộc khác vẫn có thể áp dụng.

### 9.2. memory.current

memory.current phản ánh memory usage đang được tính vào cgroup. Đây không phải tổng heap object sống của JVM. Một thay đổi image/kernel/page cache có thể làm số liệu memory.current khác dù Java heap usage tương tự.

### 9.3. memory.high

memory.high là ngưỡng điều tiết: khi cgroup vượt ngưỡng, kernel có thể áp dụng reclaim và throttling để giảm áp lực bộ nhớ. Nó không có cùng ý nghĩa với memory.max.

Vì vậy, memory latency tăng dù chưa OOM kill vẫn có thể liên quan memory.high, reclaim hoặc pressure từ host/ancestor.

### 9.4. memory.events

File này có thể chứa các trường:

~~~text
low 0
high 120
max 24
oom 3
oom_kill 2
oom_group_kill 0
~~~

Các giá trị là ví dụ. high/max/oom/oom_kill là sự kiện controller có ý nghĩa khác nhau; trong điều tra OOM cần kết hợp thời gian, pod status, kernel/container runtime logs và JVM metrics.

Không suy ra rằng mọi lần OutOfMemoryError trong Java đều phải làm bộ đếm oom_kill tăng: Java có thể tự ném OutOfMemoryError do giới hạn heap hoặc một vùng khác trước khi kernel tiêu diệt process.

## 10. JVM nhận diện container resources như thế nào?

Ở những JVM triển khai hỗ trợ container awareness, JVM có thể sử dụng thông tin cgroups thay vì chỉ nhìn toàn bộ RAM/CPU host. Với HotSpot hiện đại, tùy chọn:

~~~text
-XX:+UseContainerSupport
~~~

thường được bật mặc định trên các bản JDK phù hợp. Trên một số JDK cũ và các bản update, lịch sử hỗ trợ container/cgroups khác nhau; các vendor có thể backport fixes.

**Không nên viết một quy tắc quá đơn giản** kiểu “tất cả Java 8 đều không biết container” hoặc “mọi Java 11 đều xử lý cgroups v2 đầy đủ”. Khả năng thực tế phụ thuộc:

- JDK major, update level, vendor và backports.
- Linux kernel/container runtime và cgroups v1/v2.
- Các flag đã được bật/tắt.
- Cấu hình mount namespace và cgroup hierarchy.
- Các lỗi đã được sửa trong từng update release.

Khi migration, phải kiểm tra trên binary JDK thực tế được đóng gói trong container hoặc được triển khai.

### 10.1. Container support ảnh hưởng những gì?

Một số giá trị/ergonomics có thể chịu ảnh hưởng:

- Số active processors.
- Cách JVM xác định lượng RAM làm cơ sở tính ergonomic heap size.
- Default số GC threads và một số thread counts.
- Quyết định chọn GC/heap trong các tổ hợp JDK/flags.
- Một số runtime APIs/metrics của JVM.

JVM container awareness không đồng nghĩa mọi thư viện Java đều tự nhận diện memory cgroup giống JVM; một thư viện có thể đọc /proc/meminfo, dùng file riêng hoặc dùng giả định từ host.

### 10.2. Tùy chọn -XX:-UseContainerSupport

Một số HotSpot JDK cho phép tắt container awareness:

~~~bash
java -XX:-UseContainerSupport -jar application.jar
~~~

Khi đó JVM có thể quay về một số cách nhìn tài nguyên kiểu host và các flag cài đặt khác. Đây **không phải giải pháp mặc định** cho lỗi hiệu năng container; tắt awareness có thể khiến heap/parallelism được chọn quá lớn so với limits.

Chỉ dùng trong thí nghiệm chẩn đoán có kiểm soát để phân biệt nguyên nhân, và phải ghi rõ JDK/flags. Không áp dụng vô điều kiện ở production.

## 11. Heap JVM và memory limit: hai con số khác nhau

Java heap được JVM dùng để lưu objects do Java quản lý. Các giá trị thường nhắc đến:

- Xms: initial heap capacity configuration.
- Xmx: maximum heap size.
- MaxRAMPercentage: tỷ lệ RAM nền tảng dùng để tính ergonomic maximum heap khi không có Xmx tường minh.
- InitialRAMPercentage: tỷ lệ để tính initial heap trong các trường hợp phù hợp.
- MinRAMPercentage: một tùy chọn ergonomics liên quan cấu hình cho máy/bộ nhớ nhỏ; tên gọi dễ khiến người đọc hiểu nhầm là minimum heap cứng.

Các phần trăm này áp dụng theo thuật toán, giới hạn và version JVM tương ứng; không nên coi mọi JDK đều sử dụng cùng default percentage.

### 11.1. Ví dụ giới hạn 1 GiB

Giả sử container đặt memory limit 1 GiB. Nếu JVM container-aware sử dụng 1 GiB làm cơ sở tính MaxRAMPercentage và cấu hình:

~~~bash
java -XX:MaxRAMPercentage=65.0 -jar application.jar
~~~

thì phép tính lý thuyết 65% của 1 GiB khoảng 665,6 MiB. Kích thước heap tối đa thực tế có thể được làm tròn/điều chỉnh bởi JVM ergonomics và các flag khác.

Phần bộ nhớ còn lại phải dành cho:

- Metaspace.
- Code cache.
- Thread stacks.
- Direct/native buffers.
- GC runtime structures.
- Native libraries và agent.
- Những thành phần khác được memory cgroup tính vào.

Đừng xem 35% còn lại là “dư đảm bảo”. Mức cần thiết phụ thuộc workload, số threads, I/O buffers, class metadata và phần hệ thống được accounting.

### 11.2. -Xmx có độ ưu tiên và ý nghĩa riêng

Nếu cấu hình:

~~~bash
java -Xms256m -Xmx768m -jar application.jar
~~~

thì explicit Xmx quyết định maximum Java heap trong phạm vi tùy chọn JVM áp dụng. Trong trường hợp đó, MaxRAMPercentage thường không còn là cơ sở chọn maximum heap cho process này.

Điều quan trọng: Xmx 768 MiB trên container 1 GiB **không đảm bảo** an toàn. Native memory cộng các memory charges khác có thể khiến cgroup vượt 1 GiB.

### 11.3. Không tính heap theo số RAM host khi container có limit

Nếu host 64 GiB và container 1 GiB, một JVM không nhận diện limit có thể chọn ergonomic heap dựa trên host. Ứng dụng có thể bị kernel OOM kill trước khi Java heap đạt maximum do JVM tự tính.

Với JDK container-aware, heap sizing dựa trên container limit có thể hợp lý hơn, nhưng vẫn cần xác định mức headroom cho non-heap. Không nên kỳ vọng JVM tự biết mọi native allocator và memory consumption của ứng dụng.

## 12. Tổng bộ nhớ JVM ngoài heap

Một phân tích capacity đơn giản:

~~~text
Container memory limit
       │
       ├── Java heap committed/resident
       ├── Metaspace + class metadata
       ├── Code cache/JIT compiler
       ├── Thread stacks
       ├── Direct/off-heap buffers
       ├── JVM/GC native structures
       ├── JNI/JNA/FFM libraries và allocations
       ├── TLS/native compression/IO allocators
       └── Page cache và kernel charges liên quan
~~~

Đây là sơ đồ các thành phần có thể ảnh hưởng memory accounting, không phải phép cộng hoàn hảo giữa những metric có thể đọc riêng. Một số hạng mục đã nằm trong RSS hoặc được tính theo cách khác tùy kernel; phải tránh cộng trùng số liệu giữa JVM NMT, process RSS và cgroup usage.

### 12.1. Metaspace

Metaspace chủ yếu lưu metadata của classes và có thể tăng theo class loading, dynamic proxies, application reload hoặc classloader leak.

Nếu nâng framework làm tăng số class được load, native memory có thể tăng dù heap sizing không đổi.

### 12.2. Thread stacks

Mỗi thread JVM/OS có stack cùng các cấu trúc liên quan. Ứng dụng tạo hàng nghìn platform threads có thể tiêu thụ memory đáng kể ngoài Java heap.

Flag Xss điều khiển kích thước stack trong phạm vi phù hợp, nhưng giảm Xss tùy tiện có thể gây StackOverflowError; tăng số threads không chỉ làm tăng CPU contention mà còn tăng memory.

Virtual threads có mô hình stack khác platform threads, nhưng vẫn có overhead bộ nhớ, scheduling và carrier threads; không nên suy ra số lượng virtual threads vô hạn là miễn phí.

### 12.3. Direct buffers và native libraries

Các framework network có thể sử dụng direct memory. Native libraries hoặc FFM/JNI có thể cấp phát bộ nhớ mà JVM heap metrics không thể hiện.

Trong một số HotSpot scenarios, -XX:MaxDirectMemorySize có thể giới hạn một loại direct buffer allocation được JVM quản lý, nhưng nó không phải hard cap cho **mọi** native malloc/JNI allocation.

Nếu hệ thống dùng Netty, Arrow, database native drivers hoặc memory-mapped data, cần đọc tài liệu memory management cụ thể của dependency.

### 12.4. Cgroup usage và process RSS

Process RSS là một góc nhìn về các resident pages của tiến trình; cgroup memory.current bao gồm các khoản tính theo memory controller, có thể gồm page cache và kernel memory. Do đó hai con số không nhất thiết bằng nhau.

Khi điều tra OOM, nên xem cả:

- JVM heap used/committed/max.
- Native Memory Tracking nếu có.
- Process RSS và memory maps.
- Cgroup memory.current/events, memory.stat.
- Pod/container memory metrics từ hệ giám sát.

Không nên cộng RSS của nhiều process rồi mặc định đó bằng chính xác memory.current vì shared pages và accounting có quy tắc riêng.

## 13. Phân biệt Java OutOfMemoryError và container OOM kill

Hai sự kiện này có hậu quả và bằng chứng khác nhau.

### 13.1. OutOfMemoryError trong JVM

Ví dụ:

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Đây là exception JVM phát hiện khi không thể cấp phát trong Java heap theo giới hạn/tình trạng GC. Tùy process và cấu hình, log/heap dump có thể được sinh ra. Một số loại OutOfMemoryError khác liên quan native threads, metaspace hoặc direct buffers.

Không thể kết luận tất cả OutOfMemoryError đều do memory cgroup hard limit.

### 13.2. Container bị OOM kill

Nếu cgroup memory limit bị vượt và kernel xử lý bằng OOM killer, Java process có thể bị kết thúc bởi signal mà không có Java exception hoặc heap dump hoàn chỉnh.

Trên Kubernetes, status của container có thể ghi:

~~~text
Reason: OOMKilled
Exit code: 137
~~~

Exit code 137 thường gắn với tiến trình bị SIGKILL trong cơ chế báo exit code, nhưng **không phải mọi exit 137 đều chứng minh OOM**. Cần đối chiếu reason của container, kernel events/logs, memory.events và timeline để xác định.

### 13.3. Điều tra theo nhánh

~~~text
Application dừng / restart
             │
             ▼
    Có Java OutOfMemoryError?
        │             │
       Có            Không
        │             │
        ▼             ▼
Kiểm tra heap/     Kiểm tra container status,
metaspace/native   OOMKilled, signal, cgroup events
        │             │
        └──────┬──────┘
               ▼
       Đối chiếu memory metrics
       trước sự cố và giới hạn
               │
               ▼
       Chọn cách sửa đúng nguyên nhân
~~~

Nếu native memory gây cgroup OOM, giảm heap có thể tạo thêm headroom nhưng không giải quyết native leak. Nếu heap quá nhỏ khiến GC thrash/OOME, tăng Xmx có thể cần thiết nhưng chỉ an toàn khi container memory budget còn đủ.

## 14. Các công cụ quan sát JVM

### 14.1. Từ Java API

Một ví dụ tự chứa:

~~~java
public final class ResourceSnapshot {
    private static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("availableProcessors=" +
                runtime.availableProcessors());
        System.out.printf("heap.max.MiB=%.1f%n",
                mib(runtime.maxMemory()));
        System.out.printf("heap.committed.MiB=%.1f%n",
                mib(runtime.totalMemory()));
        System.out.printf("heap.freeWithinCommitted.MiB=%.1f%n",
                mib(runtime.freeMemory()));
    }
}
~~~

Kết quả có ý nghĩa:

- availableProcessors: số processor hiệu dụng theo cách JVM quyết định.
- maxMemory: giới hạn heap tối đa mà Runtime báo, không phải container memory limit.
- totalMemory: lượng heap đã được JVM cấp phát/committed theo semantics của Runtime.
- freeMemory: phần free bên trong heap hiện đã cấp phát, không phải RAM trống của container.

Để lấy heap used/committed/max theo management APIs, có thể dùng java.lang.management.MemoryMXBean; các metric đó vẫn không biểu diễn đầy đủ native memory hay cgroup limit.

### 14.2. -XshowSettings:system

Trên những JDK hỗ trợ tùy chọn này, có thể chạy:

~~~bash
java -XshowSettings:system -version
~~~

Output có thể chứa thông tin container metrics/cgroup như provider, memory limit, effective CPU count. Cú pháp, trường output và mức hỗ trợ thay đổi theo JDK/vendor, vì vậy cần xác nhận trên JDK đang triển khai.

Nếu JVM không hiểu option, không nên kết luận kernel không có cgroups; có thể bản JDK không cung cấp cách hiển thị đó.

### 14.3. JVM unified logging

Trên HotSpot JDK phù hợp:

~~~bash
java -Xlog:os+container=trace -version
~~~

Nội dung log có thể giúp quan sát cách JVM phát hiện cgroups, quota, cpuset và memory limit. Tag/level hỗ trợ khác nhau theo JDK update; dùng java -Xlog:help hoặc tài liệu của runtime đã chọn để xác nhận.

Khi bật trace trong production cần kiểm soát log volume và tránh phát tán metadata hệ thống không cần thiết.

### 14.4. jcmd

Với JDK có công cụ jcmd và quyền attach phù hợp:

~~~bash
jcmd
jcmd <pid> VM.flags
jcmd <pid> VM.info
~~~

Lệnh giúp xem một phần JVM flags, thông tin JVM và những chi tiết implementation tương ứng. Không phải mọi lệnh đều hoạt động trong container tối giản hoặc môi trường hạn chế attach; một số image runtime chỉ gồm JRE/minimal runtime không có jcmd.

### 14.5. Native Memory Tracking

Nếu HotSpot JDK hỗ trợ Native Memory Tracking (NMT), có thể khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Sau đó:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT giúp phân loại các loại native memory được HotSpot theo dõi, nhưng có overhead và **không bao phủ mọi memory allocation của thư viện native bên ngoài**. Không dùng NMT total như một phép đo thay thế duy nhất cho cgroup memory.current hay process RSS.

Một số runtime flags/NMT settings phải được bật từ lúc khởi động; không nên giả định mọi chế độ có thể bật động về sau.

## 15. Docker: thí nghiệm tối thiểu

Có thể so sánh JVM trong một image JDK Linux được tổ chức cho phép, ví dụ image minh họa:

~~~bash
docker run --rm --cpus=1.5 --memory=1g eclipse-temurin:21-jdk \
    java -XshowSettings:system -version
~~~

Mục đích là quan sát JDK trong container với CPU quota và memory limit rõ ràng. Lệnh giả định Docker host/runtime hỗ trợ các flags và image có phiên bản phù hợp; đây không phải kết quả đã được chạy.

### 15.1. So sánh không giới hạn và có giới hạn

Ví dụ:

~~~bash
docker run --rm eclipse-temurin:21-jdk java -version

docker run --rm --cpus=1 --memory=512m \
    eclipse-temurin:21-jdk \
    java -XshowSettings:system -version
~~~

Không đặt giới hạn tường minh trong docker run đầu không có nghĩa container được đảm bảo toàn bộ tài nguyên host: còn chính sách parent cgroup, Docker Desktop VM, runtime và tài nguyên platform.

### 15.2. Kiểm tra cgroup bên trong container

~~~bash
docker run --rm --cpus=1.5 --memory=1g \
    --entrypoint sh eclipse-temurin:21-jdk \
    -c 'cat /proc/self/cgroup; ls /sys/fs/cgroup'
~~~

Nếu image có shell/các tiện ích cơ bản, lệnh này giúp xem loại cgroup được mount. Với image tối giản hoặc distroless, có thể không có sh/cat/ls; cần dùng một debug image phù hợp hoặc đọc metrics bằng ứng dụng.

### 15.3. Đặt Xmx trong container

Ví dụ:

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk \
    java -XX:MaxRAMPercentage=60.0 -XshowSettings:vm -version
~~~

Mục tiêu là nhìn JVM ergonomic heap size trong điều kiện giả định 1 GiB limit. Không xem 60% là tỷ lệ tối ưu cho mọi workload; cần có benchmark, memory headroom và quy trình capacity planning riêng.

### 15.4. Docker Desktop, VM và host OS

Trên Windows/macOS, Docker Desktop thường chạy Linux containers trong một môi trường VM hoặc lớp ảo hóa. Linux kernel/cgroups của container nằm trong môi trường Linux đó, không đồng nhất với tổng RAM/CPU của host desktop.

Khi so sánh kết quả:

- Xem giới hạn cấp Docker Desktop VM.
- Xem --cpus/--memory của container.
- Xem JDK bên trong image Linux, không phải JDK Windows/macOS bên ngoài.
- Không đối chiếu lệnh lscpu trên host với Runtime.availableProcessors trong container mà bỏ qua VM/cgroup layers.

## 16. Kubernetes: quan sát từ Pod đến node

### 16.1. Xem cấu hình requests và limits

~~~bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -o yaml
~~~

Các placeholder cần được thay bằng thông tin môi trường thực. Chỉ nên dùng cluster/test namespace được cho phép.

Đối chiếu:

- Requests và limits trong Pod spec.
- LimitRange/ResourceQuota nếu cluster áp dụng.
- RuntimeClass, CPU manager policy hoặc cpuset liên quan.
- Pod QoS class và trạng thái container.
- Container image tag/digest và JDK vendor/version.

### 16.2. Xem usage thực tế

~~~bash
kubectl top pod <pod-name> -n <namespace> --containers
~~~

Lệnh yêu cầu metrics infrastructure thích hợp. Metrics hiển thị CPU/memory usage ở một thời điểm/cửa sổ đo; không phải phép thay thế cho cgroup quota, JVM heap metrics hoặc nguyên nhân OOM.

### 16.3. Kiểm tra OOM/restarts

~~~bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
~~~

--previous chỉ có dữ liệu khi runtime giữ log của container trước đó. Nếu process bị kernel kill, log Java có thể kết thúc đột ngột mà không có OutOfMemoryError.

Nên xem:

- Last State / Reason / Exit Code.
- Events trong namespace/pod.
- Cgroup memory.events hoặc container runtime metrics.
- Node pressure, eviction và deployment rollout events.

Kubernetes eviction do node memory pressure là một tình huống khác với container chạm hard memory cgroup limit; không gộp mọi pod restart vào một loại “Java OOM”.

## 17. CPU throttling và GC latency

CPU quota không chỉ làm giảm throughput của application threads. GC, compiler/JIT và runtime background tasks cũng cần CPU.

Ví dụ:

~~~text
Container có CPU limit thấp
        │
        ▼
Application + GC + JIT cùng tranh quota
        │
        ▼
Quota hết trong period
        │
        ▼
CPU throttling
        │
        ▼
Response latency tăng, queues đầy
        │
        ▼
Timeout/retry làm tải tăng thêm
~~~

Hệ quả có thể là một vòng lặp xấu: throttling kéo dài xử lý request, retry tăng traffic, thread pools tăng backlog và memory tăng.

### 17.1. Metric cần kết hợp

- Container CPU usage và limit/quota.
- Cgroup nr_throttled và throttled time.
- JVM GC pause time và throughput.
- JVM compiler activity nếu liên quan.
- Application request rate, latency p95/p99, error rate.
- Executor queue length, active threads và saturation.
- Memory.current và Java heap usage.

Không kết luận “GC kém” chỉ vì pause/latency tăng trên JDK mới; cùng lúc CPU quota hoặc availableProcessors có thể đã thay đổi.

### 17.2. Cách đánh giá

1. Xác định quota/cpuset thực tế và effective processor count.
2. Tải cùng workload và cùng dữ liệu đại diện trên JDK baseline/mục tiêu.
3. Ghi throttling và GC metrics theo cùng khoảng thời gian.
4. Thử thay một biến có kiểm soát: CPU limit, pool size, GC settings hoặc JDK.
5. Kiểm tra throughput, latency, error rate và memory headroom.

Việc tăng CPU limit có thể làm giảm throttling nếu bottleneck thực sự do quota, nhưng phải đánh giá cluster capacity và chi phí. Đổi ActiveProcessorCount chỉ điều chỉnh JVM ergonomics, không tạo thêm CPU entitlement.

## 18. Các cấu hình JVM thường liên quan

| JVM option | Ý nghĩa thường dùng | Rủi ro nếu dùng sai |
|---|---|---|
| -XX:+UseContainerSupport | JVM xem xét thông tin container/cgroups khi được implementation hỗ trợ. | Không chắc có trên mọi JDK cũ; semantics thay đổi theo version. |
| -XX:-UseContainerSupport | Tắt container awareness trong JDK hỗ trợ flag. | JVM có thể tính theo host và vượt limits. |
| -XX:ActiveProcessorCount=N | Override số processor JVM sử dụng cho một số quyết định. | Đặt quá cao làm tăng parallelism/throttling; không cấp CPU thực. |
| -XX:MaxRAMPercentage=P | Điều khiển ergonomic maximum heap theo tỷ lệ RAM nền tảng. | P quá cao làm thiếu native headroom. |
| -XX:InitialRAMPercentage=P | Điều khiển ergonomic initial heap theo tỷ lệ trong cấu hình tương ứng. | Initial heap quá lớn không phù hợp startup/capacity. |
| -XmxSIZE | Giới hạn heap tối đa tường minh. | Bằng memory limit có thể dẫn đến container OOM. |
| -XmsSIZE | Thiết lập initial heap size. | Xms quá lớn tăng footprint ban đầu. |
| -XssSIZE | Stack size cho platform threads trong phạm vi áp dụng. | Quá thấp gây stack overflow; quá lớn làm tăng memory. |
| -XX:MaxDirectMemorySize=SIZE | Giới hạn một phạm vi direct buffer allocations theo implementation. | Không chặn mọi native allocations. |
| -XX:NativeMemoryTracking=summary | Bật thống kê native memory HotSpot ở mức summary. | Có overhead; không bao phủ mọi thư viện native. |

Không phải mọi HotSpot flag tồn tại hoặc có cùng ngữ nghĩa trên mọi JDK/vendor. Khi dùng OpenJ9 hoặc JVM khác, hãy tra cứu tài liệu tương ứng, không tự giả định các flag -XX: của HotSpot được hỗ trợ.

### 18.1. Một cấu hình gợi ý để thí nghiệm, không phải mặc định production

~~~bash
java \
    -XX:MaxRAMPercentage=60.0 \
    -XX:ActiveProcessorCount=2 \
    -jar application.jar
~~~

Ví dụ đặt heap ergonomic percentage và số processor cho benchmark có kiểm soát. Nó không nên được áp dụng nguyên xi cho container 512 MiB, 1 GiB hoặc 16 GiB mà không đo native memory và CPU quota.

### 18.2. Không cộng các giới hạn một cách ngây thơ

Giả sử:

~~~text
memory limit   = 1024 MiB
Xmx            = 700 MiB
MaxDirectMemory= 256 MiB
~~~

Không thể suy rằng phần còn lại 68 MiB luôn đủ cho toàn bộ JVM. Ngoài heap và direct buffer còn Metaspace, stacks, code cache, native libraries, GC overhead, page cache và các khoản khác. Ngược lại, một vùng maximum reserve chưa chắc đã resident đầy đủ ở mọi thời điểm.

Cần dựa trên **peak resident/cgroup usage** và workload thực tế, có headroom cho biến động tải.

## 19. Nhận diện thay đổi khi nâng JDK

Một đợt Java migration có thể đổi cùng lúc:

~~~text
JDK baseline / cgroups v1 / image cũ
             │
             ▼
JDK mục tiêu / cgroups v2 / image mới
             │
             ▼
JVM ergonomics và runtime observations khác
~~~

Nếu nâng JDK và chuyển node OS/cgroup hierarchy đồng thời, khó quy khác biệt cho riêng JDK.

### 19.1. Những câu hỏi nên trả lời trước migration

1. Runtime JDK trước/sau là phiên bản, update và vendor nào?
2. Container Linux đang dùng cgroups v1 hay v2?
3. JDK target có hỗ trợ loại cgroups đó theo implementation đang dùng?
4. Limits thực tế ở cgroup nào, có ancestor giới hạn không?
5. Runtime.availableProcessors() trước/sau là bao nhiêu?
6. Runtime.maxMemory() và Xmx effective trước/sau thế nào?
7. Có thay JVM flags/GC/thread pools không?
8. CPU throttling và memory events trước/sau ra sao?
9. App có off-heap/native/agent tăng lên khi nâng framework không?
10. Container image, OS kernel và libc có đổi không?

### 19.2. Cấu hình giống nhau vẫn có thể cho kết quả khác

Ví dụ cả hai image đều đặt:

~~~text
CPU limit    : 1500m
Memory limit : 1Gi
~~~

nhưng một JVM cũ không nhận diện cgroups v2 chính xác, còn JVM mục tiêu nhận diện được. Số active processors hoặc ergonomic heap có thể đổi dù YAML không đổi.

Đây không nhất thiết là regression của JDK mới; có thể JDK mới phản ánh limit chính xác hơn. Việc cần làm là đánh giá lại GC, thread pools và memory budgeting dựa trên tài nguyên thực tế.

## 20. Ma trận kiểm thử tài nguyên trong CI

Một bảng thử nghiệm nên gồm:

| Kịch bản | CPU limit/cpuset | Memory limit | Điều cần quan sát |
|---|---|---|---|
| Container không có hard limit tường minh | Không giới hạn tường minh | Không giới hạn tường minh | JVM nhận diện host/ancestor constraints ra sao? |
| CPU fractional | 500m | 1Gi | availableProcessors, throttling, latency. |
| CPU 1.5 | 1500m | 1Gi | CPU quota, GC threads, request throughput. |
| Cpuset hẹp | 2 logical CPUs | 1Gi | JVM có nhận diện affinity/cpuset đúng? |
| Memory nhỏ | 1 CPU | 512Mi | Heap size, native memory, startup và OOM risk. |
| Memory rộng | 2 CPU | 4Gi | Heap ergonomics, GC và memory headroom. |
| Cgroups v1 | Theo môi trường | Theo môi trường | File controller và JVM detection. |
| Cgroups v2 | Theo môi trường | Theo môi trường | cpu.max/memory.max và JVM detection. |

Các ô là ví dụ thiết kế test; không phải mọi runner CI đều hỗ trợ tự đổi cgroup version. Có thể cần những nodes/VM/containers riêng được provision trước.

### 20.1. Bằng chứng mỗi lượt test

Lưu tối thiểu:

- JDK vendor/version/update và JVM flags.
- Kernel, container runtime, cgroups version.
- Container image digest, node architecture.
- CPU request/limit, cpuset, cpu.max hoặc cfs quota/period.
- memory.max hoặc memory.limit_in_bytes và giới hạn ancestor liên quan.
- JVM availableProcessors, heap max, committed và GC configuration.
- Throughput, latency, CPU throttling, memory.current/events.
- Test dataset, concurrency, duration và kết quả.

Không cần lưu secrets hoặc toàn bộ environment variables. Chỉ ghi metadata cần thiết và loại bỏ các giá trị nhạy cảm.

### 20.2. Trường hợp thử có tải

Chỉ khởi động JVM và in Runtime.maxMemory là chưa đủ để xác nhận capacity:

1. Chạy workload nhẹ để xác nhận startup.
2. Chạy tải đại diện cho production.
3. Chạy peak/soak test nếu mục tiêu cần.
4. Đo GC, off-heap, RSS, throttling và OOM events.
5. Thử các failure paths như retry storm hoặc batch lớn.

Memory leak hoặc CPU throttling có thể chỉ xuất hiện sau một khoảng tải kéo dài. Cần lưu sự khác nhau giữa test startup, stress test và production observations.

## 21. Rủi ro của autoscaling và resource policy

Kubernetes Horizontal Pod Autoscaler hoặc các cơ chế autoscaling có thể dựa trên CPU utilization, custom metrics và target settings. Khi sửa CPU requests, cách tính CPU utilization theo request có thể đổi, ngay cả khi CPU usage tuyệt đối không đổi.

Ví dụ:

~~~text
CPU usage observed = 400m
CPU request old    = 400m → 100% theo request
CPU request new    = 800m → 50% theo request
~~~

Đây là phép minh họa cách tỷ lệ thay đổi nếu HPA dùng utilization tương đối so với request; autoscaling thực tế còn phụ thuộc metric availability, tolerance, windows và cấu hình policy.

Do đó, thay requests.cpu để “sửa JVM availableProcessors” có thể ảnh hưởng scheduling và autoscaling, chứ không chỉ thread pool. Cần phối hợp với platform team khi điều chỉnh resource policy.

### 21.1. Memory limits, OOM và autoscaling

Thêm replica không tự giải quyết memory leak trong từng JVM. Nếu mỗi container có workload/heap peak vượt hard limit, từng replica vẫn có thể bị OOM kill.

Ngược lại, tăng memory limit có thể cho JVM chọn heap lớn hơn theo MaxRAMPercentage, làm thay đổi GC footprint và scheduling. Khi đổi Kubernetes resources, nên quan sát lại ergonomic heap size chứ không mặc định Xmx giữ nguyên.

## 22. Các tình huống điều tra mẫu

### 22.1. Java mới tăng CPU utilization và giảm throughput

Triệu chứng:

~~~text
Host: 32 CPUs
Container CPU limit: 1 CPU
JDK mới: Runtime.availableProcessors=1
Application: p99 latency tăng ở tải cao
~~~

Các bước:

1. Kiểm tra cpu.max hoặc quota/period thực tế.
2. Đọc cpu.stat để biết có throttling.
3. So sánh JDK baseline/mục tiêu, GC logs và thread pool settings.
4. Kiểm tra request rate, retry behavior và saturation.
5. Nếu bottleneck do quota, đánh giá CPU limit hoặc tối ưu workload/concurrency.

Không nên mặc định đặt ActiveProcessorCount=32 chỉ để JDK nhìn giống host; quota vẫn chỉ cho khoảng 1 CPU tổng thời gian.

### 22.2. JVM heap chưa đầy nhưng container OOMKilled

Giả sử:

~~~text
Container memory limit: 1024 MiB
Java heap used peak:     550 MiB
Container memory peak:  1024+ MiB
Outcome:                OOMKilled
~~~

Những giá trị này chỉ minh họa một nguyên nhân có thể.

Điều tra:

- Heap committed và maximum, không chỉ heap used.
- Native Memory Tracking nếu hỗ trợ.
- Thread counts/stacks.
- Direct/off-heap buffers, JNI/native libraries.
- cgroup memory.stat và container memory metrics.
- Page cache hoặc file mappings.

Nếu off-heap/natively allocated memory là nguồn lớn, điều chỉnh Java heap riêng lẻ có thể không giải quyết nguyên nhân gốc.

### 22.3. Nâng JDK trên node cgroups v2 làm heap đổi

Ứng dụng trước đó chạy trên runtime cũ với container limit 2 GiB, nhưng JVM nhìn host có 64 GiB. Sau nâng JDK, JVM nhận 2 GiB đúng hơn và Xmx ergonomic giảm đáng kể.

Điều này có thể:

- Giảm rủi ro container OOM kill.
- Tăng GC frequency nếu workload trước đó sử dụng heap lớn hơn limit thực tế.
- Khiến ứng dụng cần chọn một Xmx phù hợp với native memory headroom.

Cần xem thông số JDK/container thực tế và kiểm thử tải, thay vì vội tắt UseContainerSupport để quay về hành vi cũ.

### 22.4. CPU request tăng nhưng CPU quota không đổi

Container:

~~~text
requests.cpu: 250m → 500m
limits.cpu  : 1000m (không đổi)
~~~

CPU hard quota có thể vẫn tương đương 1 CPU. Nhưng relative scheduling weight, Kubernetes scheduling hoặc HPA behavior có thể thay đổi. JVM availableProcessors cũng có thể phụ thuộc JDK's container accounting implementation.

Muốn kết luận tác động, cần đo cả quota, shares/weight, active processors, throttling và scaling behavior.

## 23. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao không đúng | Cách xử lý |
|---|---|---|
| Container thấy host 64 CPU nên JVM chắc có 64 CPU. | Cgroup quota/cpuset có thể giới hạn. | Đọc cgroup và availableProcessors trên JVM thật. |
| CPU requests bằng CPU limits. | Requests không phải hard quota; limits có thể dùng quota. | Phân biệt scheduling/weight và quota. |
| CPU weight 100 tương đương 1 core. | Weight là ưu tiên tương đối, không quy đổi thành core cố định. | Đánh giá quota/cpuset và contention. |
| availableProcessors=2 nghĩa là có 2 CPU độc quyền. | Đây là con số JVM dùng cho ergonomics, không phải CPU reservation. | Đo usage/throttling và host scheduling. |
| ActiveProcessorCount=8 tạo thêm CPU cho container 1 CPU. | Flag không thay kernel quota. | Chọn concurrency theo năng lực thực. |
| Xmx bằng 1 GiB là an toàn trong container 1 GiB. | JVM còn native/non-heap và memory accounting khác. | Dành headroom, đo peak usage. |
| Runtime.freeMemory là RAM container còn trống. | Nó biểu diễn phần free trong heap đã cấp phát. | Xem cgroup memory.current và OS metrics. |
| Java OutOfMemoryError và OOMKilled là một. | JVM exception khác kernel/container kill. | Phân loại bằng log, status và cgroup events. |
| memory.max=max nghĩa là không có giới hạn ở đâu. | Ancestor cgroup hoặc node có thể giới hạn. | Xem hierarchy và effective constraints. |
| Có cgroups v2 thì mọi JDK đều hỗ trợ như nhau. | JDK update/vendor/backports khác nhau. | Xác nhận với binary JDK thực tế. |
| Mọi Linux container có file ở cùng đường dẫn. | Mount namespaces và cgroup layout khác nhau. | Đọc /proc/self/cgroup và mountinfo. |
| Heap max đại diện tổng RSS. | Native memory, direct buffers, page cache chưa được phản ánh. | Kết hợp heap, NMT, RSS và cgroup metrics. |
| CPU throttling chỉ ảnh hưởng business threads. | GC, JIT và runtime threads cũng cần CPU. | Đối chiếu GC/latency và cgroup cpu.stat. |
| HPA tự xử lý memory leak per-container. | Scale out không loại bỏ leak trong từng replica. | Điều tra memory profile và sửa leak. |
| Chạy ổn ở local Docker nghĩa là production Kubernetes giống vậy. | Kernel/cgroups/VM/limits khác nhau. | Test với topology/resource policy đích. |

## 24. Quy trình migration JVM trên container

### Bước 1 — Thu thập baseline

Ghi JDK vendor/version/update, JVM flags, Gradle/runtime artifact, image digest, host/kernel, cgroups version và resource requests/limits. Chụp availableProcessors, Xmx, CPU quota/cpuset và memory limits.

### Bước 2 — Xác minh cgroups hiệu dụng

Đọc /proc/self/cgroup và mountinfo. Với v1 kiểm tra quota/period và memory.limit_in_bytes; với v2 kiểm tra cpu.max, cpuset.cpus.effective, memory.max và memory.events. Xem ancestor limits nếu cần.

### Bước 3 — Xác nhận JVM container awareness

Quan sát java -XshowSettings:system, -Xlog:os+container=trace hoặc cách khác mà JDK hỗ trợ. Không mặc định mọi JDK vendor/update có cùng behavior.

### Bước 4 — Xác định heap/native budget

Chọn Xmx/MaxRAMPercentage phù hợp memory limit và peak native footprint. Đo GC, thread stacks, direct buffers, Metaspace và cgroup memory usage.

### Bước 5 — Đánh giá CPU ergonomics

Xem availableProcessors, GC thread counts, ForkJoinPool, executor pools và CPU throttling. Không chỉnh ActiveProcessorCount chỉ dựa vào CPU host.

### Bước 6 — Chạy baseline và target với cùng workload

Giữ dataset, concurrency, requests/limits, image topology và resource metrics nhất quán nhất có thể. Nếu đồng thời đổi cgroups v1 sang v2, ghi rõ đây là biến độc lập.

### Bước 7 — Điều chỉnh từng biến

Nếu có regression, chỉ thay một nhóm thông số mỗi lượt: JDK, heap percentage/Xmx, CPU limit, thread pool hoặc GC. Lưu kết quả trước/sau để tránh nhầm tương quan với nguyên nhân.

### Bước 8 — Kiểm tra lỗi và giới hạn

Thử workload gây peak, xác minh không OOMKilled ngoài kịch bản dự kiến; kiểm tra throttling, timeouts, queue backlog, GC pauses và memory.events.

### Bước 9 — Triển khai có giám sát

Canary hoặc staging gần production, theo dõi latency, GC, heap/native, cgroup memory, CPU throttle, pod restarts, OOMKilled và HPA behavior.

### Bước 10 — Công bố operational baseline

Ghi JVM flags, JDK runtime được hỗ trợ, resource requests/limits, native headroom, metrics và điều kiện rollback cho mỗi loại workload.

## 25. Mẫu báo cáo tài nguyên sau migration

Một báo cáo có thể ghi:

~~~text
Service:
Artifact / image digest:
JDK vendor + version + update:
OS/kernel/container runtime:
cgroups mode: v1 / v2 / mixed

Kubernetes/Docker configuration:
  CPU request:
  CPU limit:
  Cpuset / affinity:
  Memory request:
  Memory limit:
  Swap configuration:

Effective controller observations:
  cpu quota / period:
  cpu weight/shares:
  cpuset effective:
  memory hard limit:
  memory current/peak:
  throttling counters:
  OOM/memory.events:

JVM observations:
  availableProcessors:
  UseContainerSupport:
  ActiveProcessorCount override:
  Xms:
  Xmx / Runtime.maxMemory:
  MaxRAMPercentage:
  GC and thread configuration:
  Heap used/committed:
  Native memory estimate:

Load-test evidence:
  workload / concurrency / duration:
  throughput:
  p95/p99 latency:
  GC metrics:
  CPU throttling:
  OOM / restarts:
  pass/fail and open risks:
~~~

Đây là mẫu cấu trúc để ghi dữ liệu thật trong dự án. Không điền các kết quả giả định như thể CI/production đã được kiểm thử. Bảo vệ các thông tin cấu hình nhạy cảm theo chính sách tổ chức.

## 26. Kết luận

Trong container, **CPU và bộ nhớ hiệu dụng của JVM không đơn giản là CPU và RAM của host**. Cgroups v1/v2 có các cơ chế CPU quota, cpuset, shares/weight, memory hard/high limits và accounting riêng. JVM container awareness giúp HotSpot ở những release phù hợp nhận diện thông tin này cho processor count và các quyết định ergonomic heap/GC, nhưng mức hỗ trợ còn phụ thuộc JDK vendor, update, kernel và runtime.

Để nâng Java an toàn, cần phân biệt CPU request với hard limit, xem throttling thay vì chỉ xem CPU usage; phân biệt Java heap với tổng container memory; nhận biết OutOfMemoryError khác OOMKilled; và đo JVM flags, Runtime.availableProcessors, Runtime.maxMemory cùng cgroup files ngay trong môi trường triển khai.

**Không lấy một con số processor hoặc một tỷ lệ MaxRAMPercentage làm công thức cố định cho mọi container.** Một migration có kiểm soát cần ma trận JDK–cgroups–CPU–memory, benchmark và integration tests với tải đại diện, đo peak native memory, GC và latency, rồi ghi lại cấu hình runtime thực sự được hỗ trợ. Khi các bằng chứng này được lưu cùng artifact và deployment policy, nhóm có thể chuyển JDK/container mà không vô tình làm thay đổi throughput, OOM behavior hoặc chất lượng dịch vụ.
