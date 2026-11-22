# Khả năng nhận biết container của HotSpot trên nền tảng được hỗ trợ (Java 10+)

## 1. Bài toán: JVM thấy CPU của container hay toàn bộ máy chủ?

Một máy Linux có thể có hàng chục lõi CPU vật lý hoặc logic, nhưng một container chạy ứng dụng Java chỉ được cấp **một phần tài nguyên** theo chính sách của Docker, containerd hoặc Kubernetes. Nếu JVM dùng số CPU và dung lượng bộ nhớ của **host** thay vì các giới hạn hiệu lực của container, các quyết định tự động về số thread, garbage collection và heap có thể không phù hợp với tài nguyên thật sự được cấp.

Từ **JDK 10**, HotSpot cải thiện khả năng **nhận biết container trên Linux**: JVM có thể dùng thông tin giới hạn CPU/bộ nhớ từ môi trường container để đưa ra các quyết định về tài nguyên thay vì chỉ nhìn tổng tài nguyên host. Tính năng này **vẫn được hỗ trợ và bật mặc định** trên HotSpot ở nền tảng Linux phù hợp của các bản JDK hiện đại.

Ví dụ minh họa về mặt khái niệm:

```text
Host Linux: 32 logical CPUs
        |
        +--- Container A: CPU quota tương đương 2 CPUs
        |          |
        |          +--- HotSpot nhận giới hạn và điều chỉnh CPU ergonomics
        |
        +--- Container B: giới hạn cpuset khác
                   |
                   +--- HotSpot có thể thấy tập CPU hiệu lực khác Container A
```

**Điểm cốt lõi:** con số mà `Runtime.getRuntime().availableProcessors()` trả về trên HotSpot có container support là **số CPU hiệu lực mà JVM sử dụng cho nhiều quyết định nội bộ**, không nhất thiết bằng tổng lõi của host và cũng không phải “số core vật lý được cấp riêng”. Kernel Linux vẫn là thành phần **thực thi giới hạn tài nguyên**; HotSpot chỉ đọc/diễn giải các giới hạn để tự điều chỉnh.

Bài này tập trung vào **khả năng nhận biết container trên nền tảng được hỗ trợ**, chứ không coi mọi JVM hay mọi hệ điều hành đều có cùng cách phát hiện.

## 2. Khả năng này thuộc HotSpot và hệ điều hành, không phải tính năng ngôn ngữ Java

Phải phân biệt ba tầng:

1. **Ngôn ngữ Java:** cú pháp `var`, `record`, `switch`… do compiler quyết định.
2. **Thư viện Java:** API như `Runtime.availableProcessors()` được mã Java gọi để lấy thông tin tài nguyên.
3. **HotSpot VM và Linux kernel:** cách JVM tính CPU/memory từ affinity và cgroup của tiến trình.

**Container awareness là khả năng của VM/runtime**, không phải một cú pháp Java 10. Mã nguồn sau đã hợp lệ từ lâu:

```java
int processors = Runtime.getRuntime().availableProcessors();
System.out.println(processors);
```

Điều thay đổi ở HotSpot là **cách xác định giá trị hiệu lực trong môi trường Linux container**. Khi JVM có hỗ trợ và đọc được giới hạn, số CPU trả về có thể khác số CPU của host.

### Phạm vi lịch sử và hiện hành

- **JDK 10:** Oracle ghi nhận cải thiện HotSpot Docker/container detection cho CPU và memory, cùng tùy chọn `-XX:-UseContainerSupport`.
- **Các JDK hiện hành:** tính năng tiếp tục được hỗ trợ trên **Linux** theo tài liệu launcher HotSpot; có thể nhận biết các dạng cgroup được bản JDK đó hỗ trợ.
- **cgroup v2:** các bản HotSpot/OpenJDK mới đã bổ sung hỗ trợ hierarchy thống nhất, không chỉ kiểu cgroup v1 cũ.
- **Các JDK cập nhật theo nhánh:** tính năng và lỗi sửa lại có thể được backport; không phán đoán chính xác từ số feature mà không biết **update, vendor và build**.

Các thông tin trên giúp hiểu sự phát triển của tính năng, **không khuyến nghị chạy ứng dụng mới trên JDK 10 đã lỗi thời về bảo trì**. Với production, chọn bản JDK còn được nhà cung cấp cập nhật và kiểm thử trên đúng runtime image đang triển khai.

## 3. “Nền tảng được hỗ trợ” cụ thể nghĩa là gì?

Tài liệu launcher Oracle Java SE hiện hành mô tả `UseContainerSupport` là tính năng **Linux only**. Vì vậy cần xét **hệ điều hành nơi tiến trình Java thật sự chạy**, không chỉ hệ điều hành của laptop dùng để chạy công cụ container.

| Môi trường | Có thể dùng container detection theo mô tả HotSpot? | Lưu ý |
| --- | --- | --- |
| HotSpot chạy **bên trong Linux container**, Linux kernel/cgroup được hỗ trợ | **Có** | Trường hợp sử dụng chính; mặc định bật |
| HotSpot chạy trực tiếp trên Linux host | Cùng code HotSpot chạy trên Linux | Có thể thấy tài nguyên host hoặc giới hạn cgroup của process; không được suy luận “đang ở Docker” |
| Linux container chạy qua Docker Desktop trên Windows/macOS | **Có thể**, vì Java process thực sự chạy trong **Linux VM/container** | Phải kiểm tra JDK và cgroup **bên trong container**, không phải JVM trên host |
| HotSpot chạy trực tiếp trên Windows | **Không nên áp dụng cờ Linux-only này** | Một số build không nhận diện `-XX:-UseContainerSupport` |
| HotSpot chạy trực tiếp trên macOS | **Không nên kỳ vọng Linux cgroup awareness** | macOS không cung cấp cùng Linux cgroup API |
| JVM implementation không phải HotSpot | **Tùy implementation** | Không suy ra hỗ trợ/flag HotSpot là chuẩn chung của Java SE |

**Điều kiện hỗ trợ gồm cả OS + CPU architecture + JDK build/vendor + cấu hình cgroup.** Các mô tả cũ có thể giới hạn ở một kiến trúc cụ thể, trong khi các bản runtime mới hơn hỗ trợ thêm kiến trúc. Không áp dụng một danh sách kiến trúc từ tài liệu JDK cũ để đánh giá một HotSpot mới; xem tài liệu **của bản phân phối và bản build đang chạy**.

Trên Windows native, ví dụ JDK 24 có thể báo `Unrecognized VM option 'UseContainerSupport'` khi truyền cờ tắt Linux-only. Đó là **khác biệt nền tảng**, không phải chứng minh một container Linux cũng sẽ không được nhận biết.

**Không dùng biến môi trường `KUBERNETES_SERVICE_HOST`, sự tồn tại của `/.dockerenv` hay tên hostname như một phép kiểm tra duy nhất** để kết luận CPU quota đã được HotSpot đọc và áp dụng. Chúng không thay thế thông tin cgroup hiệu lực.

## 4. HotSpot đọc gì từ Linux?

Linux dùng **control groups (cgroups)** để phân bổ, giới hạn và ghi nhận tài nguyên cho một nhóm tiến trình. Container runtime và Kubernetes thường biểu đạt chính sách CPU/memory qua các cơ chế kernel này.

Những thông tin liên quan:

| Nguồn thông tin | Điều nó có thể biểu đạt | Liên hệ với HotSpot |
| --- | --- | --- |
| **CPU quota + period** | Lượng thời gian CPU được phép dùng trong một chu kỳ | Giúp HotSpot tính mức CPU hiệu lực cho nhiều thuật toán ergonomics |
| **CPU set / processor affinity** | Những CPU logic mà tiến trình được phép chạy trên đó | Giới hạn tập xử lý thực tế mà tiến trình có thể dùng |
| **CPU weight / shares** | Mức ưu tiên **tương đối** khi tranh chấp CPU | **Không nên coi là số CPU cứng**; HotSpot mới không dùng shares làm CPU count theo mặc định |
| **Memory limit** | Giới hạn bộ nhớ của cgroup | Ảnh hưởng việc JVM tự chọn một số giá trị memory ergonomics |
| **Kernel/cgroup accounting** | Các thông số resource usage và giới hạn hiệu lực | Có thể xem bằng logging/settings hoặc các nguồn theo dõi hệ thống |

Tùy bản Linux, cấu trúc cgroup có thể là:

- **cgroup v1:** các controller CPU/memory/cpuset thường ở các hierarchy riêng.
- **cgroup v2:** hierarchy thống nhất, ví dụ `cpu.max`, `cpuset.cpus.effective` và `memory.max`.

Với cgroup v2, `cpu.max` thường chứa hai giá trị: **quota** và **period** (đơn vị microsecond), hoặc token `max` khi không có quota cứng. Ví dụ:

```text
cpu.max: 200000 100000
```

Về mặt quota, tỷ số này tương đương **2 CPU** trong mỗi chu kỳ 100.000 microsecond. Nhưng giá trị `availableProcessors()` thật sự vẫn có thể chịu ảnh hưởng của cpuset/affinity và thuật toán của bản HotSpot, chứ **không** phải luôn chỉ là phép chia hai số này.

**Không chỉnh tay những file trong `/sys/fs/cgroup` chỉ để “ép JVM thấy số CPU mong muốn”**. Trong Docker/Kubernetes, cấu hình resource qua container runtime/orchestrator và để kernel quản lý; dùng diagnostic để quan sát.

## 5. Tác động trực tiếp đến `Runtime.availableProcessors()`

API Java:

```java
int n = Runtime.getRuntime().availableProcessors();
```

Javadoc mô tả số processor mà Java VM có thể sử dụng. Trên HotSpot hỗ trợ container, giá trị này có thể dựa vào:

- Tập CPU được phép chạy qua affinity/cpuset.
- CPU quota/period nếu có.
- Thông tin về môi trường Linux/cgroup mà HotSpot nhận diện.
- Một override tường minh như `-XX:ActiveProcessorCount`.

**Số này là một số nguyên; không phải số “millicore” hay tỷ lệ sử dụng CPU tại thời điểm đo.** Ví dụ một giới hạn 1500m trong Kubernetes tương đương 1,5 CPU thời gian tính toán, nhưng `availableProcessors()` vẫn là integer và có thể được HotSpot làm tròn/giới hạn tùy cấu hình thực tế.

Không khẳng định:

- `availableProcessors() == số core vật lý`.
- `availableProcessors() == số core của host`.
- `availableProcessors() == requests.cpu`.
- `availableProcessors() == limits.cpu` trong mọi trường hợp, nhất là khi có fractional CPU, cpuset hoặc affinity.

Nên quan sát giá trị thực tế bên trong container chạy cùng image và resource spec của production.

## 6. Cờ điều khiển hiện hành: `UseContainerSupport`

Trên HotSpot **Linux**, tài liệu launcher mô tả:

```bash
java -XX:+UseContainerSupport -version
java -XX:-UseContainerSupport -version
```

- `-XX:+UseContainerSupport`: bật khả năng đọc thông tin container để JVM xác định lượng CPU/memory hiệu lực.
- `-XX:-UseContainerSupport`: tắt cơ chế này, thường khiến JVM tính tài nguyên theo góc nhìn hệ điều hành/host và những giới hạn khác mà OS vẫn báo.
- Trên Linux được hỗ trợ, **mặc định đã bật**; bình thường **không cần** thêm `-XX:+UseContainerSupport`.

**Tắt container support không hủy giới hạn do kernel áp dụng.** Một container bị CPU quota vẫn có thể bị throttling bởi kernel, ngay cả khi JVM tính số worker thread theo tài nguyên host. Điều có thể thay đổi là **heuristics của VM**, không phải quyền sử dụng CPU do OS cấp.

Cũng không nên tắt container support chỉ để “tăng throughput”: nếu JVM tạo quá nhiều thread hoặc đặt memory budget sai, chương trình có thể gặp contention, GC behavior kém hoặc bị giới hạn tài nguyên mạnh hơn.

Trên **Windows/macOS host**, không dựa vào tính sẵn có của cờ Linux-only. Chỉ dùng nó khi tài liệu và một lần kiểm tra flag trên runtime mục tiêu xác nhận được hỗ trợ.

## 7. `-XX:ActiveProcessorCount`: override có chủ đích

HotSpot có tùy chọn:

```bash
java -XX:ActiveProcessorCount=2 -jar app.jar
```

Với Java process trên HotSpot được hỗ trợ, tùy chọn này chỉ định số CPU hiệu lực mà VM dùng cho **nhiều phép tính CPU ergonomics**, ví dụ chọn số worker GC hoặc ForkJoinPool.

Javadoc launcher còn ghi rõ: **`ActiveProcessorCount` được tôn trọng ngay cả khi `UseContainerSupport` bị tắt**.

Đối chứng trên Linux:

```bash
java -XX:ActiveProcessorCount=2 -jar app.jar

java -XX:-UseContainerSupport \
     -XX:ActiveProcessorCount=2 \
     -jar app.jar
```

Với ứng dụng Java đơn giản đọc `Runtime.getRuntime().availableProcessors()`, hai lệnh trên có thể cùng báo `2` trên HotSpot hiện hành.

**Điều không thay đổi:**

- `ActiveProcessorCount` **không** đổi `cpu.max` hoặc cpuset của Linux.
- Nó **không cấp thêm CPU** so với quota container.
- Nó không đồng nghĩa một custom thread pool của ứng dụng sẽ tự thay kích thước nếu pool được cấu hình cứng.
- Nó không bảo đảm số thread ở mọi subsystem bằng chính xác giá trị đã chỉ định.

Nên dùng flag này khi **có lý do vận hành xác đáng**, ví dụ heuristic của VM không phù hợp workload hoặc hệ thống có yêu cầu phân vùng rõ ràng. Với phần lớn ứng dụng Linux container hiện đại, hãy **quan sát kết quả mặc định trước**; không thêm flag chỉ vì thấy một mẹo tối ưu cũ.

## 8. CPU requests, limits và cpu shares trong Kubernetes

Trong Kubernetes, các trường resource có ý nghĩa khác nhau:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "2"
    memory: "512Mi"
```

Đây là **đoạn cấu hình container** đặt trong manifest Pod/Deployment hợp lệ, không phải một file YAML hoàn chỉnh.

- `requests.cpu = 500m` là mức yêu cầu **phục vụ scheduling/quản lý chia sẻ tài nguyên**; thông thường liên quan CPU weight/shares, **không phải giới hạn cứng 0,5 CPU**.
- `limits.cpu = 2` có thể được container runtime biểu diễn bằng **CPU quota** của Linux.
- `limits.memory = 512Mi` là giới hạn bộ nhớ; **không phải số `-Xmx` được bảo đảm**.
- Một pod có thể có thêm giới hạn do cpuset, CPU Manager, ancestor cgroups hoặc chính sách node.

**Thay đổi quan trọng vẫn còn áp dụng:** HotSpot/OpenJDK hiện đại **không còn dùng CPU shares làm số CPU hiệu lực theo mặc định**. Oracle JDK 19 release notes và các bản cập nhật JDK 17 nêu thay đổi này, vì shares phản ánh trọng số **tương đối** chứ không phải một CPU count cứng.

Vì vậy, đừng áp dụng một công thức cũ kiểu:

```text
CPU count = requests.cpu / 1000
```

để dự đoán `availableProcessors()`. Nó sai về ý nghĩa của requests và không phản ánh thuật toán HotSpot hiện đại.

Thay vì suy đoán từ YAML, xác nhận **effective CPU count** trong JVM và cgroup đang chạy. Với Kubernetes, nhớ rằng requests và limits còn có thể bị thay đổi bởi defaulting, admission policy, LimitRange hoặc các tầng quản trị khác.

## 9. cgroup v1 và cgroup v2: vì sao phải quan tâm JDK build?

Nếu runtime Linux dùng cgroup v2, một JDK/HotSpot quá cũ chưa hỗ trợ nó có thể **không nhận đúng giới hạn container**. Đây là một khác biệt tương thích thực tế khi di chuyển node hoặc nâng kernel/container runtime.

Kubernetes hiện hành khuyến nghị dùng OpenJDK/HotSpot đã hỗ trợ cgroup v2 đầy đủ; ví dụ nhánh JDK 17, 21 và các bản mới có sự hỗ trợ này. Ngoài feature release, vẫn cần **các bản cập nhật đủ mới** nếu bạn phải duy trì nhánh cũ.

Để hiểu môi trường Linux đang dùng:

```bash
test -e /sys/fs/cgroup/cgroup.controllers \
  && echo cgroup-v2-present \
  || echo cgroup-v2-not-detected
```

Đây là phép kiểm tra **một dấu hiệu filesystem** cho cgroup v2, không phải bản kiểm kê mọi mount/controller hoặc chứng minh HotSpot đã dùng limits thành công.

Trên cgroup v2 có quyền đọc:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
```

Các giá trị có thể là `max`, số quota/period, danh sách CPU hoặc giới hạn memory. **Không hardcode output** của các lệnh này: nó phụ thuộc kernel, cgroup hierarchy và quyền trong container.

Điểm quan trọng hơn việc đọc file là **so sánh những gì kernel thực thi với những gì JVM báo** qua `-XshowSettings:system` và log container của HotSpot. Một con số đúng tình cờ không đủ chứng minh tất cả đường code ergonomics đã được đặt đúng.

## 10. Chẩn đoán bằng `-XshowSettings:system`

Trên HotSpot/Oracle Java hiện hành cho **Linux**, lệnh sau yêu cầu Java launcher in thông tin OS/container rồi tiếp tục:

```bash
java -XshowSettings:system -version
```

Một môi trường **Linux container dùng cgroup v2** có thể báo:

```text
Operating System Metrics:
    Provider: cgroupv2
    Effective CPU Count: 4
    CPU Period: 100000us
    CPU Quota: 400000us
    ...
    Memory Limit: 4.00G
```

Đây là **một output mẫu đã quan sát trên OpenJDK 21 trong Linux container**, **không phải expected output cố định** cho mọi máy. Các trường có thể thay đổi, bị ẩn hoặc báo giá trị không giới hạn khi hệ thống không áp dụng quota.

**Cách đọc đúng:**

- `Provider: cgroupv2` cho biết provider metrics đang dùng trong ví dụ.
- `Effective CPU Count` là số CPU hiệu lực được HotSpot tính.
- `CPU Quota` và `CPU Period` là số liệu kernel; không phải mức sử dụng CPU tức thời.
- `Memory Limit` là giới hạn container được nhìn thấy; **không phải mặc định đúng bằng Java heap max**.

`-XshowSettings:system` được mô tả **Linux only** trong tài liệu launcher. Không ép một JVM native Windows/macOS phải in ra cùng dữ liệu hoặc nhận đúng option như Linux.

## 11. Chẩn đoán sâu bằng unified logging

HotSpot cung cấp unified logging với tag `os+container`:

```bash
java -Xlog:os+container=trace -version
```

Ở mức `trace`, JVM có thể in chi tiết quá trình nhận diện cgroup, giới hạn CPU/memory và những nguyên nhân không đọc được dữ liệu. Để log gọn hơn có thể dùng:

```bash
java -Xlog:os+container=debug -version
```

Ví dụ một dòng mang ý nghĩa:

```text
Detected cgroups v2 unified hierarchy
```

Trên OpenJDK 21, log mức debug trong môi trường thử nghiệm cho thấy cgroup v2 được phát hiện. **Không assert chính xác chuỗi log** trong unit test đa phiên bản; wording, số lượng dòng và tag có thể thay đổi theo build/vendor.

Nếu log không có thông tin container mong đợi:

1. Xác nhận đang chạy **HotSpot trên Linux**, không phải launcher host Windows/macOS.
2. Xác nhận version/vendor/build của `java` được dùng.
3. Xem cgroup v1/v2 và mount permissions trên Linux.
4. Kiểm tra `UseContainerSupport` có bị tắt không.
5. Kiểm tra quota, cpuset và các giới hạn cgroup tổ tiên.
6. Kiểm tra process Java có thực sự chạy **trong container/pod cần đo** hay không.

Không bật trace logging liên tục trong production mà không kiểm soát chi phí I/O và độ chi tiết; dùng ở môi trường kiểm thử, hoặc trong một khoảng chẩn đoán được phép.

## 12. Vì sao số CPU trong JVM có thể khác dự đoán?

Giả sử Kubernetes khai báo `limits.cpu: "2"`, nhưng lệnh diagnostic báo khác `2`. Các khả năng có thể bao gồm:

- CPU quota không thực sự được áp vào cgroup của process như dự đoán.
- CPU set/affinity hoặc giới hạn ancestor cgroup có hiệu lực khác.
- Một flag `-XX:ActiveProcessorCount` override kết quả auto.
- Container support bị tắt hoặc JDK build không hỗ trợ kiểu cgroup đang dùng.
- Metrics được thu thập từ **node/host** thay vì bên trong container.
- Hệ điều hành/container runtime đã thay đổi giới hạn, còn phiên bản HotSpot có cơ chế cache/đọc lại riêng.
- Hành vi rounding của quota fractional và mức CPU tối thiểu khác cách tính tay.

**Không kết luận ngay “HotSpot có bug” chỉ vì hai số khác nhau.** Cần xem **bộ ba**: cấu hình mong muốn, trạng thái cgroup thực tế, trạng thái JVM đã nhận.

Cũng không dùng số CPU của JVM như một phép đo **CPU utilization**. Muốn biết tiến trình đang dùng bao nhiêu CPU hoặc có bị throttling không, dùng metrics OS/container và hệ thống quan sát phù hợp.

## 13. Liên hệ CPU count với thread pool và GC

HotSpot dùng số CPU hiệu lực cho nhiều quyết định tự động:

- Quy mô worker threads của một số garbage collector.
- Một số phép tính về parallel/concurrent hoạt động của VM.
- Mặc định hoặc heuristic của các thư viện/runtime phụ thuộc vào `availableProcessors()`.
- Một số executor hoặc framework có thể dùng CPU count để gợi ý độ song song.

Nhưng **không phải mọi thread pool tự bằng con số `availableProcessors()`**. Ví dụ `ForkJoinPool.commonPool()` có chính sách parallelism riêng; application thread pool có thể được cấu hình cố định bằng property hoặc deployment setting.

```java
int available = Runtime.getRuntime().availableProcessors();
int configuredWorkers = Math.min(available, 8);
```

Đây là **một ví dụ chính sách ứng dụng**, không phải thuật toán mặc định của HotSpot hay câu trả lời tối ưu cho mọi workload. Việc chọn worker count phải xét CPU-bound/I/O-bound, blocking, virtual threads và latency requirements.

**Nếu quota là 2 CPU nhưng một ứng dụng tạo 100 CPU-bound worker**, kernel không tự cấp thêm CPU. Công việc có thể bị tranh chấp/throttling; thông tin container giúp đưa ra mặc định hợp lý hơn, nhưng không thay profiling/load testing.

## 14. CPU count khác hoàn toàn giới hạn heap và memory

Bài thuộc chủ đề CPU, nhưng **container awareness** cũng liên quan tới memory. Đừng gộp hai đại lượng:

```java
int cpuCount = Runtime.getRuntime().availableProcessors();

long heapMax = Runtime.getRuntime().maxMemory();
```

- `cpuCount`: số CPU hiệu lực theo VM.
- `heapMax`: giới hạn heap tối đa mà JVM có thể cấp phát trong cấu hình hiện tại.
- `heapMax` **không phải** dung lượng RAM của container, và cũng không phải toàn bộ mức RSS tiến trình.
- Bộ nhớ JVM còn dùng cho metaspace, thread stacks, direct buffers, code cache, native/JNI và nhiều phần khác.

Trên Linux container, memory limit có thể tham gia **cơ chế chọn default heap size**, nếu không có giá trị `-Xmx`/flags khác ghi đè. Nhưng không nên suy từ `Memory Limit: 512Mi` rằng `Runtime.maxMemory() == 512MiB`.

Để quản lý memory production, hãy kết hợp memory limit của container với heap sizing và ngân sách native memory; đừng cho rằng chỉ bật `UseContainerSupport` là loại bỏ mọi nguy cơ OOMKill.

## 15. Chương trình Java 17+ hoàn chỉnh: kiểm chứng CPU ergonomics trên Linux HotSpot

Chương trình sau được thiết kế để **không hardcode số CPU của host/container**, nhưng xác minh một hợp đồng có thể tái lập: `-XX:ActiveProcessorCount=2` làm JVM con báo `availableProcessors() == 2`; trên Linux HotSpot, tùy chọn này vẫn hiệu lực nếu `-XX:-UseContainerSupport` được bật.

Để chương trình chạy độc lập, nó dùng `ProcessBuilder` tạo ba JVM con bằng **chính bản Java đang chạy chương trình cha**, tránh vô tình chọn JDK khác từ `PATH`.

Tạo tệp `ContainerCpuProbe.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ContainerCpuProbe {

    record Result(int exitCode, int processors, boolean heapPositive) { }

    static Result child(String... vmOptions) throws Exception {
        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";

        String javaPath = Path.of(
                System.getProperty("java.home"), "bin", executable)
                .toString();

        List<String> command = new ArrayList<>();
        command.add(javaPath);
        command.addAll(Arrays.asList(vmOptions));
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add(ContainerCpuProbe.class.getName());
        command.add("--child");

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8);

        int exit = process.waitFor();
        int cpus = -1;
        boolean heapPositive = false;

        for (String line : output.split("\\R")) {
            if (line.startsWith("processors=")) {
                cpus = Integer.parseInt(
                        line.substring("processors=".length()));
            } else if (line.startsWith("heapPositive=")) {
                heapPositive = Boolean.parseBoolean(
                        line.substring("heapPositive=".length()));
            }
        }

        return new Result(exit, cpus, heapPositive);
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            System.out.println("processors="
                    + Runtime.getRuntime().availableProcessors());
            System.out.println("heapPositive="
                    + (Runtime.getRuntime().maxMemory() > 0));
            return;
        }

        if (!System.getProperty("os.name")
                .equalsIgnoreCase("Linux")) {
            System.out.println(
                    "platform=non-Linux; use Linux HotSpot to test cgroups");
            return;
        }

        Result automatic = child();
        Result forced = child("-XX:ActiveProcessorCount=2");
        Result disabled = child(
                "-XX:-UseContainerSupport",
                "-XX:ActiveProcessorCount=2");

        boolean automaticOkay = automatic.exitCode() == 0
                && automatic.processors() > 0
                && automatic.heapPositive();

        boolean forcedOkay = forced.exitCode() == 0
                && forced.processors() == 2
                && forced.heapPositive();

        boolean disabledOkay = disabled.exitCode() == 0
                && disabled.processors() == 2
                && disabled.heapPositive();

        System.out.println("auto.cpuAndHeapValid=" + automaticOkay);
        System.out.println("forced.cpuTwo=" + forcedOkay);
        System.out.println(
                "forced.withContainerDisabled=" + disabledOkay);

        if (!automaticOkay || !forcedOkay || !disabledOkay) {
            throw new AssertionError(
                    "HotSpot option verification failed");
        }

        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy trên **Linux với HotSpot JDK 17+** có quyền khởi động JVM con:

```bash
javac --release 17 ContainerCpuProbe.java
java ContainerCpuProbe
```

Output đã kiểm chứng trên **OpenJDK 21 Linux container**:

```text
auto.cpuAndHeapValid=true
forced.cpuTwo=true
forced.withContainerDisabled=true
tests=PASS
```

**Kết quả chứng minh những gì?**

1. `auto.cpuAndHeapValid=true`: JVM mặc định khởi động được, báo CPU count và heap limit dương.
2. `forced.cpuTwo=true`: đặt `ActiveProcessorCount=2` khiến JVM con báo `2`.
3. `forced.withContainerDisabled=true`: trên Linux HotSpot, flag CPU override **vẫn có hiệu lực** khi tắt container awareness.
4. `tests=PASS` chỉ xuất hiện nếu cả ba điều kiện kiểm chứng đúng.

**Giới hạn của bài test:** nó **không khẳng định JVM đang chạy trong container**, **không đo CPU quota/cpuset** và **không chứng minh** memory limit hay CPU quota cụ thể đã được nhận chính xác. Để làm việc đó, dùng môi trường Linux container có resource limits được xác định và đối chiếu `-XshowSettings:system`, `-Xlog:os+container` và cgroup thực tế.

Nếu chạy trên Windows/macOS host, chương trình **không áp dụng phép thử cờ Linux-only** và in thông báo nền tảng; không nhận đó là test fail. Nếu dùng JVM khác HotSpot, cần kiểm tra hỗ trợ các tùy chọn `-XX` trước.

## 16. Kiểm tra trực tiếp với Docker: giới hạn CPU trên Linux

Để kiểm chứng khả năng nhận biết thực sự, nên chạy Java **trong một container Linux có giới hạn rõ ràng**.

Ví dụ trên hệ thống có Docker Engine hoặc Docker Desktop sử dụng Linux containers:

```bash
docker run --rm --cpus=2 --memory=512m \
    eclipse-temurin:21-jdk \
    java -XshowSettings:system -version
```

Đây là lệnh **minh họa cần Docker và quyền kéo image**; số liệu phụ thuộc host, Docker backend, cgroup và build runtime. Không coi output mẫu dưới đây là kết quả đã xác thực của một Docker image bất kỳ:

```text
Operating System Metrics:
    Provider: cgroupv2
    Effective CPU Count: 2
    ...
    Memory Limit: 512.00M
```

**Đọc đúng ý nghĩa:**

- `--cpus=2` biểu diễn giới hạn CPU thời gian xử lý theo quota Docker.
- `--memory=512m` đặt giới hạn memory cgroup.
- `-XshowSettings:system` yêu cầu JVM in metrics hệ thống/container **đang thấy từ trong container**.
- Output thực tế có thể là `cgroupv1`, `cgroupv2` hoặc định dạng khác; khi số CPU bất ngờ, hãy kiểm tra quota/cpuset/flags và log HotSpot.
- Nếu kernel hoặc runtime không áp dụng giới hạn như mong đợi, chỉ nhìn vào câu lệnh Docker ở bên ngoài là chưa đủ.

Có thể dùng đối chứng trên cùng image/host:

```bash
docker run --rm --cpus=2 --memory=512m \
    eclipse-temurin:21-jdk \
    java -Xlog:os+container=debug -XshowSettings:system -version
```

Không cần thêm `-XX:+UseContainerSupport` trên Linux HotSpot hiện đại nếu flag đang dùng mặc định.

## 17. Test trong Kubernetes: tránh nhầm request, limit và môi trường thực tế

Trong một Pod Java, quy trình xác minh đúng là:

1. Xem resource `requests` và `limits` của container ứng dụng, kể cả các giá trị sau admission/defaulting.
2. Xem JDK build/vendor, nền tảng Linux và cấu hình VM đang chạy **bên trong chính Pod**.
3. Dùng `Runtime.getRuntime().availableProcessors()` để xem CPU VM hiệu lực.
4. Dùng `java -XshowSettings:system -version` hoặc log `os+container` trên cùng image nếu điều kiện cho phép.
5. Đối chiếu với cgroup `cpu.max`/cpuset trên node/container; xử lý quyền đọc và namespace.
6. Theo dõi CPU throttling, latency, GC threads và hiệu năng, không chỉ snapshot số core.

Ví dụ `kubectl exec` để chạy một lệnh chẩn đoán giả sử container có `java` và chính sách cluster cho phép:

```bash
kubectl exec deploy/java-service -- \
    java -XshowSettings:system -version
```

Đây là cú pháp minh họa cho một Deployment tên `java-service` trong namespace hiện tại; nếu tên, namespace hoặc tập container khác, phải dùng đúng tài nguyên thực tế. Trong production có thể chọn debug pod/công cụ quan sát phù hợp hơn việc chạy thêm JVM bên trong container giới hạn tài nguyên.

**Không suy luận số CPU hiệu lực bằng tổng CPU limits của Pod nhiều container**: giới hạn có thể áp dụng cho từng cgroup/container, còn JVM đọc những ràng buộc hiệu lực trên **cgroup chứa chính tiến trình Java**.

Nếu ứng dụng phải chạy trên cgroup v2, Kubernetes khuyến nghị chọn JDK/HotSpot hỗ trợ cgroup v2 đầy đủ. Với các bản LTS hiện hành được cập nhật, đây là một kiểm tra bắt buộc trong quy trình lựa chọn runtime image.

## 18. Fallback và lỗi nhận diện: phải tách lỗi môi trường khỏi lỗi JVM

Một JVM có thể:

- Không phát hiện có container dù thực tế chạy trong cgroup.
- Phát hiện cgroup nhưng không đọc được một controller hoặc giới hạn cụ thể.
- Đọc đúng quota nhưng có một cờ explicit CPU count ghi đè.
- Đọc đúng CPU nhưng ứng dụng vẫn cấu hình worker pool theo một số cố định.
- Chạy được nhưng hiệu năng khác trước do nâng JDK hoặc thay cgroup driver/runtime.

**Không có một lời gọi Java SE duy nhất trả về “container=true” với hợp đồng xuyên mọi JVM/platform.** `availableProcessors()` trả số CPU, không phải boolean xác nhận Docker/Kubernetes.

Khi số CPU bị đọc quá cao so với quota, có thể dẫn tới:

- Số GC worker/parallel worker được chọn không phù hợp.
- Thread contention và CPU throttling.
- Startup hoặc latency khó dự đoán theo workload.

Khi số CPU bị đọc quá thấp, có thể dẫn tới:

- JVM chọn ít worker hơn mức có thể tận dụng.
- Ứng dụng bị underutilization.
- Các thread pool suy luận từ availableProcessors có khả năng thiếu song song.

Nhưng **đừng áp đặt một hướng sửa chung**. Đầu tiên xác nhận kernel metrics, JDK version, cách hệ thống lựa chọn CPU và workload. `-XX:ActiveProcessorCount` là **override vận hành có chủ đích**, không phải cách thay thế mọi phép đo hiệu năng.

## 19. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| “Java 10 tự hiểu mọi container trên mọi OS.” | Khái quát vượt nền tảng | HotSpot container support là **Linux-only** theo launcher; kiểm tra vendor/build |
| “Chạy Docker Desktop trên Windows nghĩa Windows HotSpot dùng Linux cgroups.” | Lẫn host và guest | Xem JVM **bên trong Linux container/VM** |
| “`UseContainerSupport` là tính năng ngôn ngữ Java.” | Chọn sai công cụ kiểm thử | Đây là JVM/runtime ergonomics |
| “`Runtime.availableProcessors()` luôn bằng host core count.” | Dễ over-allocate threads | Quan sát CPU hiệu lực của JVM |
| “Kubernetes `requests.cpu=500m` chắc chắn JVM có 0,5 CPU.” | Request không phải hard quota; CPU count là số nguyên | Phân biệt requests với limits và quota |
| “CPU shares phải chuyển trực tiếp thành số core.” | Không phù hợp HotSpot mới; underutilization | Xem quota/cpuset và hành vi JDK hiện hành |
| “`-XX:ActiveProcessorCount=2` cấp 2 CPU thật.” | Nhầm override và quota của kernel | Nó chỉ ảnh hưởng heuristic CPU của JVM |
| “Tắt `UseContainerSupport` là hết bị CPU throttling.” | Kernel vẫn thực thi cgroup quota | Quản lý giới hạn tại orchestrator |
| “Mọi JVM đều chấp nhận cờ `-XX:-UseContainerSupport`.” | Lỗi unrecognized VM option ngoài Linux/bản khác | Gắn cờ theo nền tảng được hỗ trợ |
| “Chỉ cần `Provider: cgroupv2` là mọi limit đều chuẩn.” | Một số controller/metrics có thể chưa khớp | Đối chiếu quota, cpuset, memory và log |
| “Cùng YAML thì số CPU sẽ giống hệt trên mọi build JDK.” | Khác cgroup/JDK/affinity/rounding | Test trên runtime image thực |
| “`heapMax` chính là memory limit của container.” | Nhầm heap với toàn bộ RAM/RSS | Xem cả JVM heap và cgroup memory |
| “Một CPU count thấp chứng minh container bị CPU-starved.” | CPU count là capacity hint, không phải utilization | Đo quota/throttling/CPU usage |
| “Thấy Docker env var là đủ chứng minh HotSpot container-aware.” | Env var không chứng minh metrics VM | Dùng launcher settings và container log |
| “Nên gắn `ActiveProcessorCount` vào mọi container.” | Over-tuning, dễ stale khi resource spec đổi | Quan sát mặc định rồi điều chỉnh nếu cần |
| “Nếu JDK feature >= 17 thì mọi bản update/vendor chắc chắn giống nhau.” | Backport và implementation khác nhau | Ghi nhận vendor, build, update và test |
| “Nên dùng CPU shares fallback flag deprecated để sửa.” | Quay lại hành vi cũ không còn được khuyến nghị | Dùng policy tài nguyên rõ ràng và flag hiện hành |

## 20. Bài tập tự kiểm tra

### Bài 1: Linux container 2 CPU, host 32 CPU

Một tiến trình Java trong Linux container có quota tương đương 2 CPU; host có 32 CPU logic. Có thể mặc định `availableProcessors() == 32` không?

**Đáp án:** Không. HotSpot có container awareness có thể dùng quota/cpuset để tính CPU hiệu lực. Kết quả còn tùy cấu hình affinity, flag override, JDK implementation và giới hạn khác; đo trong container.

### Bài 2: hai cờ có tác dụng khác nhau

```bash
java -XX:-UseContainerSupport \
     -XX:ActiveProcessorCount=2 \
     -jar app.jar
```

**Hỏi:** trên Linux HotSpot, điều gì xảy ra với tính toán số CPU?

**Đáp án:** Cơ chế nhận container qua `UseContainerSupport` bị tắt, nhưng `ActiveProcessorCount=2` **vẫn được tôn trọng**. Điều này không thay đổi quota kernel của container.

### Bài 3: Pod có request nhưng không có CPU limit

Một container khai báo `requests.cpu: "500m"`, không đặt CPU limit, và không bị giới hạn cpuset nào đặc biệt. Có được kết luận `Runtime.availableProcessors() == 1` không?

**Đáp án:** Không. Request liên quan scheduling/CPU weight, không phải hard CPU quota. HotSpot mới không lấy CPU shares làm CPU count mặc định. Cần kiểm tra CPU affinity/cgroup quota và runtime thực tế.

### Bài 4: JVM trên Windows host

Ứng dụng Java chạy trực tiếp trên Windows máy phát triển; container Linux khác đang chạy qua Docker Desktop. Có nên mặc định chạy `java -XX:-UseContainerSupport` ở JVM Windows để thử Linux cgroups không?

**Đáp án:** Không. Cờ này thuộc cơ chế container support Linux của HotSpot, có thể không được JVM Windows nhận. Hãy chạy diagnostic **trong container Linux** với JDK phù hợp.

### Bài 5: hai nguồn metrics khác nhau

`java -XshowSettings:system -version` cho `Effective CPU Count: 4`, còn `cpu.max` cho quota 4 CPU và cpuset liệt kê 5 processor. Có nhất thiết là lỗi?

**Đáp án:** Không. CPU quota có thể giới hạn CPU count xuống mức 4 dù cpuset cho phép chạy trên 5 CPU logic. Cần hiểu quota, affinity và cách HotSpot tính số CPU hiệu lực.

### Bài 6: dấu hiệu cgroup v2

Máy có tệp `/sys/fs/cgroup/cgroup.controllers`. Điều đó có chứng minh mọi limit đều được HotSpot đọc chính xác không?

**Đáp án:** Không. Đây chỉ là một dấu hiệu cgroup v2. Cần xác nhận JDK build hỗ trợ, file/controller được mount/đọc đúng, và đối chiếu log cùng `-XshowSettings:system`.

### Bài 7: có nên tắt detection để tối ưu?

Một người đề xuất tắt `UseContainerSupport` vì ứng dụng chậm khi có 2 CPU. Điều này có cấp thêm CPU vượt quota được không?

**Đáp án:** Không. Kernel vẫn áp đặt quota. Cần profile GC/thread pools và đo CPU throttling, sau đó mới cân nhắc điều chỉnh resource limits hoặc một override hợp lý.

## 21. Checklist xác minh container awareness trên HotSpot

1. Xác nhận **Java process thực sự chạy trên Linux** và JVM là HotSpot/implementation hỗ trợ.
2. Ghi `java -version` cùng vendor, update và build của runtime thực tế.
3. Xác định Linux cgroup v1/v2 đang áp dụng cho process, bao gồm quota và cpuset.
4. Kiểm tra `UseContainerSupport` có được bật (mặc định trên Linux được hỗ trợ).
5. Dùng `java -XshowSettings:system -version` để xem effective CPU count và container metrics.
6. Khi cần phân tích sâu, dùng `-Xlog:os+container=debug` hoặc `trace` trong môi trường chẩn đoán.
7. Không coi `requests.cpu` hay CPU weight/shares là hard CPU count.
8. Xem có `-XX:ActiveProcessorCount` nào đang override không.
9. Nếu cấu hình CPU fractional, không đòi output integer bằng raw millicores.
10. Đo CPU utilization và throttling bằng metrics kernel/container riêng, không dựa vào `availableProcessors()`.
11. Kiểm tra ứng dụng/GC/executor có thực sự sử dụng CPU count làm heuristic hay có thiết lập cố định.
12. So sánh cùng image và resource spec giữa staging/production; tránh so host Mac/Windows JVM với Linux Pod JVM.
13. Nếu chuyển node từ cgroup v1 sang v2, xác nhận JDK build hỗ trợ và test lại.
14. Đối với memory, không đồng nhất `Runtime.maxMemory()` với container memory limit.
15. Tránh gắn cờ tắt container support hay deprecated flags theo mẹo cũ; dùng quan sát và policy rõ.
16. Kiểm tra readiness/latency và GC/throttling thực tế khi thay JDK hoặc resource requests/limits.

## Kết luận

**Khả năng nhận biết container của HotSpot** giúp JVM trên **nền tảng Linux được hỗ trợ** sử dụng thông tin cgroup (CPU quota, cpuset/affinity, memory limit…) để tự chọn một số giá trị tài nguyên phù hợp hơn với container. Đây là cải tiến được giới thiệu ở **JDK 10** và **vẫn hoạt động trong các JDK hiện hành**, với hỗ trợ cgroup v2 trên các runtime đủ mới.

Ba điều cần nhớ:

- `-XX:+UseContainerSupport` thường đã **bật mặc định trên Linux HotSpot**; `-XX:-UseContainerSupport` tắt cơ chế đọc giới hạn container chứ **không hủy quota kernel**.
- `-XX:ActiveProcessorCount` là **override CPU ergonomics**, được tôn trọng ngay cả khi container support bị tắt; nó không cấp thêm core vật lý.
- **Chỉ kết luận trên nền tảng đang chạy thật**: dùng `Runtime.availableProcessors()`, `-XshowSettings:system` và `-Xlog:os+container`, đối chiếu với cgroup CPU quota/cpuset và các cấu hình resource của Pod.

Đặc biệt, **không diễn giải CPU shares/request thành số CPU cứng** trên HotSpot mới và không suy rằng Windows/macOS host HotSpot có cùng cơ chế Linux cgroups. Đó là cách hiểu hiện hành, phù hợp với yêu cầu vận hành Java hiện đại.

## Tài liệu tham khảo chính thức và hiện hành

- [Oracle Java SE 27 — `java` launcher: `UseContainerSupport`, `ActiveProcessorCount`, `-XshowSettings:system` và `-Xlog:os+container`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): cờ hỗ trợ container chỉ áp dụng trên Linux, bật mặc định và công cụ chẩn đoán.
- [Oracle JDK 10 Release Notes — Java Improvements for Docker Containers (JDK-8146115)](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): mốc phát triển khả năng nhận biết container CPU/memory từ Java 10.
- [Oracle JDK 19 Release Notes — CPU Shares Ignored When Computing Active Processor Count (JDK-8281181)](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): nguyên tắc hiện hành không coi CPU shares là số CPU theo mặc định.
- [Oracle JDK 17.0.4 Release Notes — CPU Shares Ignored](https://www.oracle.com/java/technologies/javase/17-0-4-relnotes.html): minh họa hành vi được cập nhật/backport trong nhánh JDK 17.
- [Kubernetes — About cgroup v2](https://kubernetes.io/docs/concepts/architecture/cgroups/): cgroup v2 và các phiên bản runtime Java hỗ trợ.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): sự khác nhau giữa CPU requests và limits.
- [Java SE 27 API — `Runtime.availableProcessors()`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): số processor có sẵn cho JVM; không phải CPU utilization.
