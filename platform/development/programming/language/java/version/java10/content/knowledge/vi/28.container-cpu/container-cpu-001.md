# Phân biệt CPU máy chủ với tài nguyên cấp cho container trong Java

## 1. Vấn đề: nhìn thấy 32 CPU không có nghĩa được sử dụng 32 CPU

Một máy chủ Linux (hoặc nút Kubernetes) có thể cung cấp **32 logical CPUs**, nhưng container chạy Java chỉ được cấp **CPU quota tương đương 1,5 CPU** hoặc chỉ có thể chạy trên một tập con CPU. Các thông tin quan sát có vẻ mâu thuẫn:

~~~text
Host: 32 logical CPUs
CPU affinity/cpuset trong container: CPUs 0-1 (2 logical CPUs)
Quota / period: 150000 / 100000 microseconds
CPU-equivalent budget: 1.5
Runtime.getRuntime().availableProcessors(): có thể là 2
~~~

Chúng không mâu thuẫn vì đo **những khái niệm khác nhau**:

- **Host CPU count:** số bộ xử lý logic mà hệ điều hành host/VM nhận diện. Không hẳn bằng số core vật lý; hyper-threading có thể tạo nhiều logical CPUs trên một core vật lý.
- **CPU affinity/cpuset:** tập logical CPUs mà thread của tiến trình được phép chạy trên đó. Nó kiểm soát *vị trí có thể được schedule*.
- **CPU quota:** tổng số microsecond CPU time cgroup được tiêu thụ trong một chu kỳ có độ dài nhất định. Nó kiểm soát *ngân sách CPU time* và có thể tương đương **0,5; 1,5; 2,25** CPU.
- **CPU shares/weight:** trọng số chia sẻ CPU **tương đối khi cạnh tranh**; không phải hard quota.
- **JVM active processor count:** số nguyên JVM sử dụng cho các quyết định về mức song song, số worker GC, thread pools và các thành phần liên quan.
- **CPU usage thực:** lượng CPU đã được tiến trình/container sử dụng trong một khoảng đo; có thể nhỏ hơn ngân sách hoặc bị CPU throttling.
- **CPU throttling:** kernel hạn chế chạy tiếp khi cgroup tiêu hết quota trong một chu kỳ.

**Kết luận trước tiên:** số CPU trên host, số CPU mà container được phép chạy, quota tương đương CPU, số active processors của JVM và mức CPU thật sử dụng **không phải năm cách viết khác nhau của cùng một giá trị**.

### Liên hệ với Java 10

**JDK 10** tích hợp cải tiến nhận diện tài nguyên Docker/container vào HotSpot, theo **JDK-8146115** trong Oracle JDK 10 Release Notes. JVM có thể đọc cấu hình CPU và memory từ cgroups thay vì luôn dựa vào phần cứng host. Cờ **`-XX:+UseContainerSupport`** được bật mặc định trên nền tảng hỗ trợ, và **`-XX:ActiveProcessorCount=N`** cho phép ghi đè số processor mà VM sử dụng cho sizing.

Đây là nền tảng quan trọng để Java chạy đúng trong container. Tuy nhiên, cách xử lý **CPU shares** đã được sửa ở những JDK mới hơn; bài trình bày hành vi **còn áp dụng hiện nay**, không hướng dẫn vận hành bằng những mẹo cũ đã lỗi thời.

## 2. CPU vật lý, logical CPU, vCPU và giới hạn container

### 2.1. Host có thể là máy ảo

Một máy vật lý có 16 CPU cores và mỗi core có hai hardware threads có thể hiện ra là **32 logical CPUs**. Một VM cloud có thể trình bày 32 vCPUs với các đặc tính scheduler riêng. Một container Linux chạy trên **cùng kernel** với host, nên thông tin CPU topology đôi khi vẫn đề cập các CPUs host dù container không được sử dụng hết.

**Không suy luận:**

~~~text
lscpu báo 32 CPUs
=> ứng dụng Java có 32 core vật lý chuyên dụng
~~~

Điều đó sai vì `lscpu` có thể phản ánh **topology của host/node** chứ không phản ánh giới hạn cgroup hay thời gian CPU mà ứng dụng được cấp.

### 2.2. Những công cụ quan sát CPU trả lời câu hỏi khác nhau

| Công cụ/thông tin | Thường cho biết | Không tự chứng minh |
| --- | --- | --- |
| `lscpu` | CPU topology/logical CPU của hệ thống nhìn thấy | Container có quota bằng số đó |
| `/proc/cpuinfo` | Thông tin CPU mà kernel trình bày | Process có quyền dùng tất cả |
| `nproc` | Processor count theo môi trường công cụ, thường xét affinity | Hard CPU quota dạng phân số |
| `taskset -pc <pid>` | CPU affinity của process/thread trên Linux | CPU time quota hoặc quyền độc quyền |
| `cpu.max` (cgroup v2) | Quota + period | Số core vật lý chuyên dụng |
| `cpuset.cpus.effective` | Tập CPU được phép trong cgroup | Các CPU ấy luôn rảnh |
| `cpu.weight`/`cpu.shares` | Trọng số khi cạnh tranh | Hard cap |
| `Runtime.availableProcessors()` | Số nguyên processors JVM xem là khả dụng | CPU utilization hoặc quota chính xác |
| `cpu.stat` | Dữ liệu sử dụng và throttling của cgroup | Nguyên nhân duy nhất của request chậm |

Khi một lệnh và JVM hiển thị các con số khác nhau, hãy xác định **ngữ nghĩa của từng nguồn** trước khi gọi đó là lỗi.

## 3. Cpuset/affinity: giới hạn tập CPU được phép chạy

Một cgroup v2 có thể cho thấy:

~~~text
cpuset.cpus.effective = 0-1
~~~

Nghĩa là **hai logical CPUs** có ID 0 và 1 nằm trong tập được phép. Hoặc:

~~~text
cpuset.cpus.effective = 0-3,8
~~~

thì có **năm** CPU được phép: 0, 1, 2, 3, 8.

**Đặc điểm quan trọng:**

1. Cpuset quy định thread **có thể chạy ở đâu**, không quy định tổng CPU time mỗi chu kỳ.
2. Linux CPU affinity ở cấp tiến trình/thread cũng có thể thu hẹp tập CPUs.
3. Một tập CPU được phép **không đồng nghĩa** tập CPU được cấp độc quyền; process khác có thể tranh cùng những CPUs.
4. Container có cpuset=2 CPU vẫn có thể mang quota chỉ **1,5 CPU**.
5. Khi có nested cgroups hoặc chính sách CPU Manager, tập CPU *effective* có thể khác tập được khai báo ban đầu.

**Phân biệt chiều không gian và ngân sách:** cpuset giống danh sách vị trí có thể chạy; quota giống số CPU-time được dùng trong một kỳ.

## 4. CPU quota/period: giới hạn ngân sách CPU time

### 4.1. Công thức

Trong Linux cgroup v2, file `cpu.max` thường có hai trường:

~~~text
150000 100000
~~~

Ý nghĩa:

- `150000`: số microsecond CPU time được cấp trong một kỳ.
- `100000`: độ dài kỳ tính theo microsecond wall time.
- Tỷ lệ `150000 / 100000 = 1,5` CPU-equivalent.

Công thức:

~~~text
CPU quota equivalent = quota_us / period_us

150000/100000 = 1.5
 50000/100000 = 0.5
300000/100000 = 3.0
~~~

Đây là tỷ lệ **CPU time**, không phải số logical CPU trong cpuset. Quota 1,5 không tạo một “nửa core” vật lý và không xác định chính xác thread sẽ chạy trên core nào.

### 4.2. Vì sao quota có thể gây throttling?

Giả sử cpuset cho phép hai logical CPUs và container luôn có hai threads đang runnable:

~~~text
CPU A chạy thread 1: 75 ms
CPU B chạy thread 2: 75 ms
Tổng CPU time:       150 ms
Quota của chu kỳ:    150 ms / 100 ms wall time
~~~

Nếu hai threads chạy liên tục và scheduler có thể thực hiện như ví dụ, cgroup đã tiêu hết quota sau khoảng 75 ms wall time. Nó có thể bị **throttled** trong phần thời gian còn lại của kỳ, dù host vẫn còn CPU rảnh ở nơi khác.

Đây là **mô hình đơn giản**. Thời điểm throttling thực phụ thuộc scheduler, runnable threads, burst configuration, CPU quota của cgroup cha và nhiều điều kiện kernel.

### 4.3. “Không có quota” chưa đồng nghĩa unlimited CPU trên host

Nếu:

~~~text
cpu.max = max 100000
~~~

thì không có hard quota áp từ giá trị đó **ở cgroup đang đọc**. Nhưng process vẫn có thể bị ràng buộc bởi:

- Cpuset và affinity.
- Quota ở **cgroup cha**.
- Policy của container runtime/Kubernetes.
- CPU contention với container khác.
- Quota ở cấp VM/hypervisor.
- Thiếu CPU do host overload hoặc cgroup weight thấp.

Do đó “max” chỉ có nghĩa *không có quota ở trường này*, không phải một bảo đảm 32 CPUs host luôn dành riêng cho ứng dụng.

### 4.4. Quota chỉ 0,5 CPU

~~~text
cpu.max = 50000 100000
~~~

Một cgroup được dùng tổng 50 ms CPU time mỗi 100 ms wall time ở mức khai báo. Java có thể vẫn báo `availableProcessors()` là số nguyên **1** hoặc bị ảnh hưởng bởi cờ override; điều đó **không** nâng quota lên 1,0 CPU.

Nếu một tác vụ liên tục cần 100 ms CPU time thì, ngay cả trước khi xét các overhead khác, nó sẽ bị giới hạn bởi ngân sách CPU time và khó hoàn tất trong 100 ms wall time. Đây là một hiện tượng **CPU throttling/scheduling**, không phải bằng chứng bản thân Java code có lock.

## 5. CPU shares/weight: không tương đương quota

### 5.1. Shares là trọng số tương đối

Cgroup v1 có `cpu.shares`; cgroup v2 có `cpu.weight`. Docker dùng `--cpu-shares` để gán mức ưu tiên trong cơ chế chia sẻ.

Nếu hai cgroup cần CPU cùng lúc, trọng số ảnh hưởng cách kernel phân chia CPU time giữa chúng. Nếu một cgroup không bị tranh chấp và không có quota khác, nó **có thể sử dụng thêm CPU khi có tài nguyên rảnh**.

Đừng đổi `cpu.shares=256` thành “container có chính xác 0,25 CPU”. Giá trị shares không có đơn vị “CPU-equivalent hard limit”.

### 5.2. Điều chỉnh quan trọng kể từ các JDK mới

**JDK 10 ban đầu** đã đọc cpusets, CPU shares và CPU quota để suy ra số active CPUs. Nhưng việc xem CPU shares như một giới hạn processor có thể khiến JVM **underutilize** khả năng thực tế.

Oracle **JDK 19 Release Notes** và **JDK 17.0.4 Release Notes** nêu rõ thay đổi **JDK-8281181: CPU Shares Ignored When Computing Active Processor Count**. Trong những JDK đã nhận thay đổi này, CPU shares **không còn được xét mặc định** khi suy ra active processor count.

**Hướng dẫn hiện nay:**

- Giữ đúng ngữ nghĩa shares/weight là **ưu tiên khi tranh chấp**.
- Không coi shares là hard CPU limit trong code hoặc quy trình tuning.
- Không khuyên bật lại cách suy CPU count từ shares bằng các cờ tương thích cũ đã deprecated/không còn phù hợp.
- Nếu nền tảng chỉ cấp shares mà không cấp quota, **JVM có thể nhìn nhiều CPUs của host**. Khi điều đó gây vấn đề sizing, cân nhắc `-XX:ActiveProcessorCount` hoặc cấu hình thread pools theo chính sách có đo đạc.

Vì vậy, phải xem **JDK update/build cụ thể** chứ không chỉ nhãn Java 17 hoặc Java 19.

## 6. Container awareness trong HotSpot từ Java 10

### 6.1. UseContainerSupport được bật mặc định trên Linux hỗ trợ

Oracle Java 17/25 Java launcher vẫn mô tả:

~~~text
-XX:+UseContainerSupport
-XX:-UseContainerSupport
~~~

`UseContainerSupport` mặc định bật trên môi trường Linux HotSpot được hỗ trợ. JVM đọc thông tin cgroup khi chọn các giá trị phụ thuộc số CPU/memory khả dụng.

Không tắt bằng `-XX:-UseContainerSupport` như mẹo tối ưu mặc định. Khi tắt, JVM có thể dựa vào host/OS view và bỏ qua các giới hạn container, tạo quá nhiều GC threads, compiler threads hoặc chọn heap không phù hợp. Linux kernel **vẫn** thi hành quota; tắt detection không mở rộng tài nguyên được cấp.

### 6.2. ActiveProcessorCount là override của VM, không phải quota

~~~bash
java -XX:ActiveProcessorCount=2 -version
~~~

Cờ này chỉ định **số CPUs mà HotSpot dùng để tính kích thước một số thread pools**, ví dụ GC và `ForkJoinPool`. Theo Oracle Java launcher, cờ vẫn có hiệu lực ngay cả khi container support bị tắt.

Nhưng nó **không**:

- Thêm hai CPU vật lý cho container.
- Pin thread vào hai logical CPUs cụ thể.
- Ghi đè `cpu.max` hoặc CPU throttling của kernel.
- Cấm mọi thư viện tạo hơn hai threads.
- Bảo đảm latency hoặc throughput.
- Chỉnh CPU request/limit ở Kubernetes.

Muốn thay hard quota/cpuset cần dùng container runtime/orchestrator. Muốn điều chỉnh số threads của một library cụ thể thì phải xem cấu hình riêng của library đó.

### 6.3. Cgroups v1 và v2 vẫn cần phân biệt

| Khái niệm | Cgroup v1 | Cgroup v2 |
| --- | --- | --- |
| Quota | `cpu.cfs_quota_us` | Giá trị đầu của `cpu.max` |
| Period | `cpu.cfs_period_us` | Giá trị thứ hai của `cpu.max` |
| CPU relative weight | `cpu.shares` | `cpu.weight` |
| Cpuset | `cpuset.cpus` / effective mask | `cpuset.cpus.effective` |
| Throttling statistics | `cpu.stat` dưới controller | `cpu.stat` |

OpenJDK đã bổ sung nhận diện cgroup v2 từ JDK 15; các dòng JDK LTS hiện đại như Java 17/21/25 đã có hỗ trợ phù hợp. Các bản patch rất cũ có thể đọc cgroup v2 kém và fallback về host CPU/memory. Khi nâng runtime, nên kiểm việc nhận diện cgroup thật.

**Không cố định đường dẫn** `/sys/fs/cgroup/cpu.max` cho mọi container. Mount, cgroup namespace, v1/v2, hierarchy và cấu hình orchestrator có thể khác nhau.

## 7. Runtime.availableProcessors(): JVM nhìn thấy gì?

### 7.1. API vẫn được hỗ trợ

~~~java
int count = Runtime.getRuntime().availableProcessors();
System.out.println(count);
~~~

Theo Oracle Java SE 17 Javadoc, phương thức trả **số processor có thể dùng bởi JVM**, tối thiểu là 1, và **có thể thay đổi trong một lần chạy JVM**. Đây không phải một phép đo CPU usage hay một quota floating-point.

Ví dụ một quota 1,5 CPU có thể khiến JVM hiện đại chọn một **integer hint** như 2. Nhưng **không được khẳng định** mọi phiên bản sẽ trả đúng 2 trong mọi môi trường: affinity, cpuset, JDK build, cgroup hierarchy và override có thể thay đổi kết quả.

### 7.2. Vì sao JVM dùng số nguyên?

Nhiều thành phần cần một số thread count nguyên:

- Song song hóa garbage collection.
- Một số thread compile/JIT.
- `ForkJoinPool.commonPool()` và một số tác vụ parallel.
- Thread pools trong framework và các thành phần khởi tạo dựa trên số CPUs.
- Số công việc đồng thời do heuristic quyết định.

Một CPU có thể time-slice rất nhiều Java threads. Không có quy tắc “2 available processors thì JVM không thể tạo hơn hai thread”.

### 7.3. Dùng OperatingSystemMXBean có phải số core host không?

~~~java
var bean = java.lang.management.ManagementFactory
        .getOperatingSystemMXBean();

System.out.println(bean.getAvailableProcessors());
~~~

Đây vẫn là một **góc nhìn từ JVM/management API**; không tự trở thành một cách tra số core vật lý host độc lập với container.

Không dùng `Thread.activeCount()` để đo CPU quota hoặc CPU usage. Nó nói về số thread active trong thread group liên quan, không phải số processor có thể tiêu thụ CPU time.

### 7.4. Giá trị có thể đổi nhưng pool chưa chắc đổi

`availableProcessors()` có thể thay đổi trong một invocation, nhưng một số framework hoặc thread pools tính concurrency **một lần lúc startup**. Thay CPU limit/cpuset khi container đang chạy không bảo đảm mọi pool được thay kích thước ngay lập tức.

Cần kiểm JDK thực tế và chính sách của từng pool; khi thay nhiều resource limits, redeploy/restart có thể là một phần của quy trình vận hành phù hợp.

## 8. Cách đọc các số CPU trên Linux container

### 8.1. Xác định JDK thật

~~~bash
java --version
~~~

Ghi rõ nhà cung cấp, feature/update/build, nền tảng. Chỉ biết “JDK 17” là chưa đủ vì một số thay đổi container awareness được backport qua những update releases.

### 8.2. Xem thông tin mà HotSpot đã nhận diện

Trên Linux HotSpot với JDK 17+:

~~~bash
java -XshowSettings:system -version
~~~

Có thể thấy những dòng kiểu:

~~~text
Operating System Metrics:
    Provider: cgroupv2
    Effective CPU Count: 2
    CPU Period: 100000us
    CPU Quota: 150000us
~~~

Đây là **ví dụ minh họa**, không phải output cố định. JVM không chạy trong cgroup phù hợp hoặc JDK khác có thể hiện thông tin khác.

Để chẩn đoán container detection kỹ hơn:

~~~bash
java -Xlog:os+container=trace -version
~~~

`-Xlog:os+container=trace` được Oracle Java launcher hiện đại tài liệu hóa. Các dòng trace phụ thuộc JDK build và môi trường; đừng viết test yêu cầu log đúng số ký tự minh họa.

### 8.3. Xem cgroup v2 nếu đúng mount tồn tại

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.weight
cat /sys/fs/cgroup/cpu.stat
~~~

Ví dụ dữ liệu **giả định**:

~~~text
cpu.max               => 150000 100000
cpuset.cpus.effective => 0-1
cpu.weight            => 100
cpu.stat              => nr_periods 1000
                         nr_throttled 200
                         throttled_usec 1234567
~~~

Nếu các file không có, hãy xác định provider v1/v2 và path thực qua `/proc/self/cgroup`, `/proc/self/mountinfo`, hoặc thông tin hệ quản lý container. Không kết luận thiếu file có nghĩa không có giới hạn CPU.

### 8.4. Đọc thống kê throttling theo *delta*

`cpu.stat` cgroup v2 thường có:

- `nr_periods`: số kỳ quota.
- `nr_throttled`: số kỳ có sự kiện throttling.
- `throttled_usec`: thời lượng throttling tích lũy theo bộ đếm kernel.

Giả sử:

~~~text
t1: nr_periods=1000, nr_throttled=200
t2: nr_periods=1100, nr_throttled=260

Delta periods = 100
Delta throttled = 60
60/100 = 60% chu kỳ có throttling trong cửa sổ đó.
~~~

60% **không có nghĩa** ứng dụng đã mất chính xác 60% throughput hay 60% request time. Cần xem thêm CPU usage, thời gian bị throttle, tải thực và latency cùng thời điểm.

### 8.5. Vì sao host metrics cũng cần xem?

Container CPU quota có thể được cấu hình đúng nhưng host đang có *noisy neighbors*, VM bị cạnh tranh CPU hoặc process bị affinity quá chặt. Điều tra chậm cần cả container metrics và host scheduling/CPU saturation nếu có quyền xem.

Một log ứng dụng báo elapsed time cao không tự chứng minh JVM đã dùng hết quota; cần phân biệt CPU-bound work, throttling, I/O và lock contention.

## 9. Chương trình Java 17+ chạy được, kết quả xác định

Mục đích ví dụ là làm rõ **host logical CPUs**, **CPU affinity**, **cpuset** và **CPU time quota**, không mô phỏng đầy đủ HotSpot internals. Chương trình dùng các tình huống số **cố định**, tính:

- CPU-equivalent `quotaUs / periodUs`.
- Một **illustrative hint** = min giữa affinity count, cpuset count và quota đã **làm tròn lên**.
- Với quota không giới hạn, chỉ xét các giới hạn vị trí trong mô hình.
- In giá trị `Runtime.availableProcessors()` thật **chỉ khi chạy với `--live`**, để stdout mặc định không phụ thuộc môi trường.

**Lưu ý:** công thức hint chỉ để học, **không phải đặc tả thuật toán HotSpot**. JDK version, cgroup hierarchy, affinity, override và scheduler policy có thể làm giá trị thực khác dự đoán.

Lưu file **`ContainerCpuBudgetDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

public final class ContainerCpuBudgetDemo {

    private ContainerCpuBudgetDemo() {
    }

    record Scenario(
            String name,
            int hostLogical,
            int affinity,
            int cpuset,
            long quotaUs,
            long periodUs) {

        Scenario {
            if (name == null
                    || hostLogical <= 0
                    || affinity <= 0
                    || cpuset <= 0
                    || periodUs <= 0
                    || (quotaUs != -1 && quotaUs <= 0)) {
                throw new IllegalArgumentException(
                        "invalid CPU scenario");
            }
        }
    }

    static int ceilingQuotaCpus(Scenario s) {
        if (s.quotaUs() == -1) {
            return Integer.MAX_VALUE;
        }

        // ceil(quota/period), không cộng trước để tránh overflow.
        long ceiling = 1L + (s.quotaUs() - 1L) / s.periodUs();

        return ceiling > Integer.MAX_VALUE
                ? Integer.MAX_VALUE
                : (int) ceiling;
    }

    static int illustrativeHint(Scenario s) {
        int allowed = Math.min(s.affinity(), s.cpuset());

        return Math.max(1, Math.min(
                allowed,
                ceilingQuotaCpus(s)));
    }

    static String quotaDescription(Scenario s) {
        if (s.quotaUs() == -1) {
            return "unlimited";
        }

        return String.format(
                Locale.ROOT,
                "%.2f",
                (double) s.quotaUs() / s.periodUs());
    }

    static void show(Scenario s) {
        System.out.printf(
                Locale.ROOT,
                "%s: host=%d affinity=%d cpuset=%d"
                        + " quotaCores=%s hint=%d%n",
                s.name(),
                s.hostLogical(),
                s.affinity(),
                s.cpuset(),
                quotaDescription(s),
                illustrativeHint(s));
    }

    public static void main(String[] args) {
        var fraction = new Scenario(
                "fraction", 32, 8, 2, 150_000, 100_000);

        var half = new Scenario(
                "half", 32, 8, 8, 50_000, 100_000);

        var cpusetOnly = new Scenario(
                "cpusetOnly", 32, 32, 4, -1, 100_000);

        var quotaThree = new Scenario(
                "quotaThree", 32, 16, 16, 300_000, 100_000);

        var unconstrained = new Scenario(
                "unconstrained", 32, 32, 32, -1, 100_000);

        for (Scenario s : List.of(
                fraction,
                half,
                cpusetOnly,
                quotaThree,
                unconstrained)) {
            show(s);
        }

        System.out.println("fractionalQuota="
                + (fraction.quotaUs() % fraction.periodUs() != 0));
        System.out.println("halfQuotaHintAtLeastOne="
                + (illustrativeHint(half) >= 1));
        System.out.println("sharesAreNotHardCap=true");
        System.out.println("modelIsNotHotSpotSpecification=true");

        if (args.length == 1 && "--live".equals(args[0])) {
            System.out.println(
                    "liveJvmAvailableProcessors="
                    + Runtime.getRuntime().availableProcessors());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 ContainerCpuBudgetDemo.java
java ContainerCpuBudgetDemo
~~~

**Stdout chính xác khi không có tham số:**

~~~text
fraction: host=32 affinity=8 cpuset=2 quotaCores=1.50 hint=2
half: host=32 affinity=8 cpuset=8 quotaCores=0.50 hint=1
cpusetOnly: host=32 affinity=32 cpuset=4 quotaCores=unlimited hint=4
quotaThree: host=32 affinity=16 cpuset=16 quotaCores=3.00 hint=3
unconstrained: host=32 affinity=32 cpuset=32 quotaCores=unlimited hint=32
fractionalQuota=true
halfQuotaHintAtLeastOne=true
sharesAreNotHardCap=true
modelIsNotHotSpotSpecification=true
~~~

Để xem **thêm một dòng** processor count thực của môi trường JVM:

~~~bash
java ContainerCpuBudgetDemo --live
~~~

Lúc đó JVM sẽ in dòng bắt đầu bằng `liveJvmAvailableProcessors=` và **số nguyên cụ thể tùy máy/container**. Không nên đặt một stdout giả định cố định cho dòng này.

### Giải thích chương trình

**fraction:** host có 32 logical CPUs; affinity cho phép 8, cpuset cho phép 2, quota tương đương 1,5. Mô hình in hint=2 nhưng chỉ có 1,5 CPU-equivalent quota, không phải hai core độc quyền.

**half:** affinity/cpuset cho phép 8 nhưng quota 0,5; processor hint làm tròn thành 1, trong khi CPU bandwidth vẫn thấp hơn một CPU đầy đủ.

**cpusetOnly:** không có hard quota ở tình huống mẫu; cpuset chỉ cho phép bốn logical CPUs. Không được suy bốn CPUs luôn rảnh.

**quotaThree:** cpuset cho 16 logical CPUs, quota cho 3,0 CPU-equivalent. Quota có thể bị dùng hết bởi nhiều runnable threads.

**unconstrained:** tình huống giả định không có hạn chế trong mô hình. Nó không chứng minh host thật có CPU rảnh hoặc được hệ điều phối bảo đảm tài nguyên độc quyền.

Với đầu vào không hợp lệ như `periodUs <= 0`, record constructor ném `IllegalArgumentException`. Ví dụ không đọc file cgroup của máy nên vẫn có thể chạy trên Windows/macOS để **học mô hình**, dù cờ/đường dẫn cgroup ngoài ví dụ chỉ áp dụng trên Linux.

## 10. Thực hành với Docker: quota, cpuset, shares

Các lệnh dưới đây dành cho **host có Docker Engine và quyền chạy container**. Image minh họa là JDK 17 thông thường; output phụ thuộc image version, host và cgroup thực. Không có số `Effective CPU Count` được hứa sẽ giống nhau trên mọi host.

### 10.1. Quota 1,5 CPU

~~~bash
docker run --rm --cpus=1.5 eclipse-temurin:17-jdk java -XshowSettings:system -version
~~~

`--cpus=1.5` cấu hình quota tương đương 1,5 CPU trong container runtime hỗ trợ. JVM có thể hiển thị quota/period/processor count tương ứng. Không hiểu “1,5 CPU” là một core vật lý cộng nửa một core.

### 10.2. Quota kèm cpuset

~~~bash
docker run --rm --cpus=1.5 --cpuset-cpus=0-1 eclipse-temurin:17-jdk java -XshowSettings:system -version
~~~

Lệnh yêu cầu IDs CPU 0 và 1; nó chỉ chạy được khi các logical CPUs đó được host cho phép gán. Nếu môi trường có IDs khác, chọn tập CPU hợp lệ.

- Cpuset giới hạn **vị trí** chạy ở 2 logical CPUs.
- Quota 1,5 giới hạn **thời gian CPU**.
- JVM active count có thể là số nguyên, thường 2 khi không có ràng buộc khác, nhưng **phải quan sát output thực**.

### 10.3. Shares chỉ là trọng số

~~~bash
docker run --rm --cpu-shares=256 eclipse-temurin:17-jdk java -XshowSettings:system -version
~~~

`256` là trọng số chia sẻ tương đối. Nó **không** tương đương `--cpus=0.25` và cũng không tự tạo cgroup quota 0,25 CPU. Với JDK đã áp dụng JDK-8281181, không nên dự đoán `availableProcessors()` chỉ còn 1 dựa vào shares.

### 10.4. Override JVM processor count

~~~bash
docker run --rm --cpus=1.5 eclipse-temurin:17-jdk java -XX:ActiveProcessorCount=1 -XshowSettings:system -version
~~~

Cờ override có thể làm JVM dùng **1** cho ergonomic sizing. Nhưng **kernel quota vẫn 1,5 CPU**, và application threads không tự bị pin vào một CPU cụ thể. Nó là một lựa chọn tuning, không sửa cấu hình tài nguyên container.

### 10.5. Tại sao cần đo với chính image phát hành?

Một image tag có thể nhận security updates/HotSpot fixes theo thời gian; các JDK vendors cũng có backports khác nhau. Kết quả trên laptop, CI, cloud container và Kubernetes production có thể khác. Ghi rõ **image digest/JDK build, cgroup version, Docker flags** trước khi so số liệu.

## 11. Kubernetes: CPU request không phải CPU limit

Một cấu hình Kubernetes điển hình:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "512Mi"
~~~

Ý nghĩa:

- `requests.cpu=500m`: yêu cầu **0,5 CPU** cho scheduling và trọng số phân bổ tài nguyên theo nền tảng.
- `limits.cpu=1500m`: giới hạn CPU **1,5 CPU-equivalent**, thường được triển khai bằng CFS quota.
- `memory limit=512Mi`: giới hạn memory container, **không đồng nghĩa** JVM heap `-Xmx` luôn bằng 512MiB.
- Khi không có CPU limit, request CPU **không tự trở thành** hard CPU quota. Container có thể burst nếu CPU rảnh, chịu trọng số/tranh chấp.

Với JVM hiện đại, chỉ đặt CPU request **không bảo đảm** `Runtime.availableProcessors()` tự giảm xuống tương ứng request. Nếu nền tảng không có hard quota, JVM có thể thấy nhiều CPUs host/affinity. Khi cần quyết định thread pool size, phải xem **effective resources** và yêu cầu throughput, không chỉ đọc YAML.

### 11.1. Điều gì xảy ra với 500m request và 1500m limit?

Host có thể là 32 logical CPUs, cpuset container có thể không hẹp và quota bằng 1,5. JVM có thể báo **2 active processors** nếu heuristic làm tròn quota lên. Như vậy:

~~~text
Host:             32 logical CPUs
CPU request:      0,5 CPU (scheduling)
CPU limit:        1,5 CPU (hard quota, nếu áp dụng)
JVM active:       một số nguyên phù hợp detection/override
Actual CPU usage: biến động tùy workload và throttling
~~~

Không được gọi `requests.cpu=500m` là “container chỉ có thể dùng 0,5 CPU”.

### 11.2. CPU Manager và pinned CPUs

Một số Kubernetes clusters có CPU Manager policy cho phép gán tập CPUs cụ thể cho một số workloads đủ điều kiện. Nhưng **không phải** cứ có CPU request/limit là được pin vào core độc quyền. Điều kiện có thể gồm QoS class, số CPU nguyên, chính sách CPU Manager, phiên bản kubelet và tài nguyên của node.

Nếu một Pod được pin CPUs, vẫn nên kiểm cpuset effective, quota và host contention theo đúng môi trường.

### 11.3. Quan sát cùng JVM và Kubernetes

Khi có quyền quản trị phù hợp, cần xem:

- Manifest request/limit thực của container.
- Pod/container metrics (CPU usage theo thời gian).
- Cgroup quota, period, cpuset và throttling.
- JVM `Runtime.availableProcessors()` và `-XshowSettings:system`.
- GC/JIT/thread pools nếu ứng dụng chậm.

Một số liệu `kubectl top` tại một thời điểm không cho biết hết các spikes throttling trong quá khứ và không thay phần cấu hình limit.

## 12. CPU throttling và ảnh hưởng tới Java latency

### 12.1. JVM thấy hai CPUs nhưng vẫn bị throttling

Giả sử Java có nhiều CPU-bound threads, quota là 1,5 CPU và cpuset cho phép hai CPUs:

1. Threads chạy và tiêu thụ CPU time trên các CPUs được phép.
2. Cgroup dùng hết 150 ms CPU time trước khi kết thúc kỳ 100 ms.
3. Scheduler throttles cgroup đến kỳ mới (theo chính sách kernel).
4. Request đang cần CPU có thể tiếp tục bị kéo dài **wall-clock latency**.
5. Trong thời điểm load cao, p95/p99 latency có thể xấu hơn dù Java không có lock contention hoặc gọi database chậm.

Điều này giải thích vì sao một JVM có `availableProcessors()==2` không hề có bảo đảm cung cấp 2,0 CPU-equivalent liên tục.

### 12.2. Garbage collector và JIT cũng dùng CPU quota

Application threads không phải người tiêu thụ CPU time duy nhất. HotSpot có thể chạy GC/JIT threads; khi CPU quota quá chặt:

- GC phases song song có thể khó được lên lịch đủ CPU.
- Một GC pause đo bằng **wall time** có thể kéo dài vì workers tranh CPU hoặc bị throttling.
- JIT compilation và các tác vụ runtime khác cũng cạnh tranh ngân sách.
- Nhiều runnable threads có thể làm tăng scheduler overhead và context switching.

Không coi mọi GC pause dài là do quota; cần kiểm GC log, heap pressure, CPU throttling, CPU usage và host contention.

### 12.3. Cách xác định có throttling

Đọc hai lần `cpu.stat` trong cùng cửa sổ latency cao:

~~~text
t1: nr_periods=1000, nr_throttled=200
t2: nr_periods=1100, nr_throttled=260

Delta nr_periods    = 100
Delta nr_throttled  = 60
Tỷ lệ chu kỳ có throttling = 60%
~~~

Đây chỉ là **tỷ lệ số chu kỳ**. Nó không tự chứng minh 60% wall time bị throttled hay 60% request latency bị mất. Cần so thêm delta `throttled_usec`, CPU usage và timeline của requests.

### 12.4. Phân biệt nguyên nhân cùng triệu chứng

| Quan sát | Có thể là gì? | Nên đối chiếu |
| --- | --- | --- |
| Latency cao và `nr_throttled` tăng | Quota bị chạm | CPU usage, period/quota, runnable threads |
| Latency cao nhưng CPU thấp | I/O, lock, downstream | JFR, distributed tracing |
| CPU usage gần quota nhưng không throttling | Workload CPU-bound và hoàn tất trong quota | Throughput, scheduler, saturation |
| JVM thấy CPU host quá lớn | Missing/không nhận quota, cờ override, shares-only | `-XshowSettings:system`, JDK build, cgroup |
| JVM thấy rất ít processors | Cpuset quá nhỏ, quota thấp hoặc config | Cgroup effective, overrides |
| GC pause tăng đúng lúc throttling | Có thể GC workers thiếu CPU | GC logs + cpu.stat + container metrics |
| Container không có quota nhưng chậm | Host contention hoặc I/O/lock | CPU queue, affinity, weight, JFR |

Suy luận nhân quả cần nhiều tín hiệu và phép đo lặp lại; một con số ở thời điểm riêng lẻ không đủ.

## 13. Cách chọn cấu hình phù hợp

### 13.1. Không tuning bằng cảm giác

Một quy trình an toàn:

1. Ghi số host logical CPUs, nhưng đừng coi đó là entitlement.
2. Xác định quota/period, cpuset/affinity và relative weight thực.
3. Xem `Runtime.availableProcessors()` của JVM đang chạy.
4. Xem số threads thật mà ứng dụng, GC và thread pools tạo ra.
5. Kiểm throttling, CPU utilization, latency/throughput cùng timeline.
6. Nếu thấy concurrency quá mức, điều chỉnh application thread pools hoặc `ActiveProcessorCount` trong **môi trường thử nghiệm**.
7. Nếu CPU demand vượt ngân sách, cân nhắc điều chỉnh CPU limit/request, workload hoặc kiến trúc phân tải.
8. So sánh trước/sau với cùng JDK, image, CPU quota, traffic và host conditions.

### 13.2. Khi nào ActiveProcessorCount hữu ích?

Nếu môi trường chỉ dùng CPU shares/weight và không có hard CPU quota, một JDK hiện đại có thể nhìn một số lượng CPUs lớn từ host/affinity. Nếu JVM và framework tạo nhiều thread pools hơn mức tài nguyên dự kiến cho dịch vụ, `-XX:ActiveProcessorCount=N` có thể dùng để kiểm soát sizing.

Tuy nhiên, quyết định `N` phải dựa trên **kết quả benchmark/điều kiện vận hành**, không đơn giản lấy `requests.cpu` rồi làm tròn mà không xem đặc tính tải.

### 13.3. Có nên tắt UseContainerSupport?

Thông thường **không**. Tắt container support có thể khiến JVM dựa vào host/OS view và bỏ qua những giới hạn Docker cgroup. Nếu muốn kiểm hành vi JVM, có thể so có/không cờ ở môi trường chẩn đoán, nhưng không đưa `-XX:-UseContainerSupport` làm cấu hình vận hành mặc định.

### 13.4. Tăng số Java threads có tạo thêm CPU không?

Không. Nhiều platform threads hoặc virtual threads có thể giúp ứng dụng xử lý đồng thời các tác vụ chờ I/O, nhưng không tăng tổng CPU bandwidth được cấp. Nếu workload **CPU-bound**, tăng runnable threads quá mức có thể tăng contention và throttling.

Với virtual threads từ JDK 21, số lượng virtual threads là một khái niệm concurrency, không phải processor count hoặc quota. Đừng dùng số virtual threads làm căn cứ nói một container được nhiều CPU hơn.

## 14. Những hiểu nhầm phổ biến

| Nhận định sai | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Host có 32 CPU nên Java trong container có 32 CPU | Container có thể có quota/cpuset | Xem cgroup và JVM |
| `lscpu` là số CPU cgroup được phép dùng | Nó thường hiển thị host topology | Dùng cpuset/affinity + quota |
| 2 JVM active CPUs là 2 core vật lý độc quyền | Active count là số JVM dùng sizing | Kiểm hiệu lực quota/affinity |
| Quota 1,5 nghĩa có 1,5 CPUs trong cpuset | Cpuset liệt kê CPU IDs nguyên | Tách vị trí chạy và CPU time |
| Shares 256 nghĩa quota 0,25 CPU | Shares là trọng số tương đối | Dùng quota cho hard cap |
| Cgroup v2 `cpu.max=max` nghĩa không giới hạn nào | Có thể còn cpuset/cgroup cha | Kiểm effective hierarchy |
| Kubernetes CPU request bằng CPU limit | Request ưu tiên scheduling, limit áp quota | Đọc cả hai |
| Java 10 và JDK hiện đại tính shares giống nhau | JDK-8281181 đã thay đổi mặc định | Dựa vào JDK update/build |
| ActiveProcessorCount cấp thêm CPU | Cờ không thay kernel cgroups | Đổi quota ở orchestrator |
| Tắt UseContainerSupport giúp được nhiều CPU | Kernel vẫn áp limit; JVM có thể sizing sai | Giữ detection mặc định |
| availableProcessors luôn cố định | Javadoc cho phép thay đổi | Kiểm pools và runtime behavior |
| CPU usage 100% luôn nghĩa một core vật lý | Công cụ có mẫu số khác nhau | Đọc metric semantics |
| Tăng số threads là tăng tốc | Có thể gây CPU contention | Benchmark đúng tải |
| Throttling 60% là mất 60% throughput | Tỷ lệ chu kỳ khác mức ảnh hưởng | Đo cùng request latency |
| Quota unlimited đồng nghĩa host không tranh CPU | Scheduler vẫn quản lý tài nguyên chung | Xem host contention |
| Nhiều virtual threads đồng nghĩa nhiều CPU | Virtual thread không tạo CPU capacity | Tách concurrency với CPU bandwidth |

## 15. Checklist triển khai và câu hỏi tự kiểm tra

### Checklist dành cho người viết ứng dụng

- [ ] Đã phân biệt host logical CPUs, core vật lý và vCPU?
- [ ] Đã phân biệt CPU request, limit, cpuset/affinity và shares/weight?
- [ ] Đã hiểu quota/period có thể tạo CPU-equivalent **phân số**?
- [ ] Đã biết `Runtime.availableProcessors()` trả một **số nguyên**?
- [ ] Không dùng processor count để suy CPU usage hoặc reserved cores?
- [ ] Không hard-code số threads dựa trên host CPU count khi có quota?
- [ ] Đã biết thread pools có thể không resize khi resource thay đổi?
- [ ] Đã kiểm JVM vendor/build và hỗ trợ cgroup v1/v2?
- [ ] Có dùng `ActiveProcessorCount` chỉ khi có mục tiêu sizing rõ?
- [ ] Đã đánh giá overhead của GC/JIT/application workers trong quota?

### Checklist dành cho vận hành

- [ ] Đã ghi lại CPU quota/period và cpuset effective trong container?
- [ ] Đã kiểm shares/weight là relative priority, không phải hard quota?
- [ ] Đã dùng `java -XshowSettings:system -version` trên đúng image?
- [ ] Đã dùng `-Xlog:os+container=trace` khi cần chẩn đoán?
- [ ] Đã đo delta `cpu.stat` cùng cửa sổ latency?
- [ ] Đã so CPU usage, runnable threads, p95/p99 và GC pause?
- [ ] Đã biết phiên bản JDK có thay đổi JDK-8281181?
- [ ] Đã giữ container support mặc định thay vì tắt tùy tiện?
- [ ] Đã benchmark trước/sau khi đổi JVM active processor count?
- [ ] Đã kiểm thay CPU resources không tự chỉnh mọi thread pool?

### Câu hỏi

**1. Host có 32 logical CPUs, cpuset có 2 CPUs và quota bằng 1,5. Container có được bảo đảm hai core vật lý không?**

Không. Có thể chạy trên hai logical CPUs thuộc tập cho phép, nhưng CPU time bị quota giới hạn; chuyện được độc quyền CPU phụ thuộc scheduler/orchestrator.

**2. Vì sao Java có thể trả `availableProcessors()==2` dù quota chỉ là 1,5?**

Do API trả số nguyên dùng cho JVM ergonomics; quota CPU-equivalent là giá trị phân số. Không được coi giá trị số nguyên là CPU bandwidth được bảo đảm.

**3. CPU shares/weight có phải hard limit không?**

Không. Đây là trọng số tương đối khi CPU cạnh tranh; hard CPU bandwidth limit sử dụng quota/period.

**4. `cpu.max=150000 100000` có nghĩa gì?**

Được phép tiêu thụ tổng CPU time 150000 microsecond mỗi kỳ 100000 microsecond wall time, tương đương 1,5 CPU.

**5. `cpu.max=max 100000` chứng minh container được dùng toàn bộ CPU host không?**

Không. Nó chỉ cho biết không có quota cứng ở trường hiện tại; vẫn có affinity, cgroup cha và contention.

**6. Kubernetes request 500m có luôn là quota 0,5 CPU không?**

Không. Request chủ yếu dùng để scheduling và ưu tiên; CPU limit mới thường được áp bằng quota.

**7. JDK 10 và các JDK mới có suy processor count từ CPU shares giống nhau không?**

Không. Thay đổi JDK-8281181 bỏ CPU shares khỏi tính active processor count mặc định trên các JDK đã cập nhật.

**8. `-XX:ActiveProcessorCount=4` có cấp 4 CPU thật không?**

Không. Nó override số CPUs JVM dùng cho một số quyết định sizing, không thay cgroup limit.

**9. Có nên thay `-XX:-UseContainerSupport` để “mở khóa” CPU không?**

Không. Kernel vẫn giới hạn CPU; cờ chỉ ảnh hưởng cách JVM nhận diện tài nguyên, và tắt dễ gây sizing sai.

**10. `nr_throttled` tăng từ 200 lên 260 trên 100 chu kỳ nói lên điều gì?**

Có 60 chu kỳ có throttling trong 100 chu kỳ quan sát; không suy thẳng thành mất 60% throughput.

**11. Làm sao quan sát active CPUs và quota thật?**

Đọc `Runtime.availableProcessors()`, `java -XshowSettings:system -version` và các file cgroup phù hợp ngay trong môi trường mục tiêu.

**12. Tăng số thread hay virtual threads có thay CPU quota không?**

Không. Threads là cơ chế concurrency; CPU quota/bandwidth do kernel/container runtime quản lý.

## 16. Nguồn chính thức vẫn được áp dụng

- [Oracle JDK 10 Release Notes — Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): JDK-8146115, nhận diện CPU/memory Docker từ Java 10 và `UseContainerSupport`/`ActiveProcessorCount`.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:ActiveProcessorCount`, `-XX:-UseContainerSupport` và `-Xlog:os+container=trace`.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): xác nhận container support và các JVM options hiện đại.
- [Oracle Java SE 17 — Runtime.availableProcessors()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): giá trị processor count JVM, có thể thay đổi trong đời JVM.
- [Oracle JDK 19 Release Notes](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): JDK-8281181 về CPU shares bị bỏ qua khi tính active processor count.
- [Oracle JDK 17.0.4 Release Notes](https://www.oracle.com/java/technologies/javase/17-0-4-relnotes.html): thay đổi cùng JDK-8281181 đã được cập nhật trong dòng 17.
- [Docker Docs — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): ý nghĩa `--cpus`, `--cpu-quota`, `--cpu-period`, `--cpuset-cpus` và `--cpu-shares`.
- [Linux Kernel Docs — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.weight`, `cpu.stat` và cpuset.
- [Kubernetes Docs — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests và limits.
- [Red Hat Developer — Java 17 Container Awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): hỗ trợ cgroup v2 và `-XshowSettings:system`.
- [AWS Containers — JVM memory, CPU, and classpath best practices for Java containers](https://aws.amazon.com/blogs/containers/jvm-memory-cpu-and-classpath-best-practices-for-java-containers-on-aws/): thông tin hiện hành về CPU shares-only, CFS quotas và hoạt động JVM trong container.

**Tóm tắt:** **Host CPU count không phải CPU entitlement của container**. Cpuset/affinity giới hạn vị trí chạy; CPU quota giới hạn CPU time; shares/weight chỉ là ưu tiên tương đối; `Runtime.availableProcessors()` là số nguyên mà JVM dùng cho ergonomics. Java 10 cải thiện nhận diện tài nguyên container, nhưng JDK hiện đại đã thay cách xử lý CPU shares mặc định. Muốn lý giải hiệu năng, phải kiểm đồng thời **JDK build, cgroup quota/period, cpuset/affinity, active processor count, CPU usage và throttling thực tế**.