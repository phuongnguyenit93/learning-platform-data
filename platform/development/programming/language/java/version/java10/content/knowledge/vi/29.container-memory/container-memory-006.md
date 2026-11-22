# Tương tác giữa cấu hình phần trăm với -Xms và -Xmx trong bộ nhớ container Java (Java 10+)

## 1. Mục tiêu và câu trả lời cốt lõi

Trong một container Java, HotSpot có hai nhóm tùy chọn định cỡ **Java heap**:

- **Theo số byte rõ ràng:** `-Xms` đặt initial/minimum heap; `-Xmx` đặt maximum heap.
- **Theo tỷ lệ memory basis của JVM:** `-XX:InitialRAMPercentage` đặt initial heap khi chưa chỉ định kích thước ban đầu; `-XX:MaxRAMPercentage` định cỡ maximum heap khi chưa chỉ định kích thước tối đa; `-XX:MinRAMPercentage` định cỡ **maximum heap với bộ nhớ rất nhỏ**.

**Quy tắc ưu tiên:** nếu đã có `-Xms`, giá trị initial/minimum này **không bị tính lại** theo `InitialRAMPercentage`. Nếu đã có `-Xmx`, maximum heap **không bị tính lại** theo `MaxRAMPercentage`. Hai đầu mút được quyết định **riêng rẽ**, nên có thể dùng `-Xms256m` với `MaxRAMPercentage=70`, hoặc `InitialRAMPercentage=10` với `-Xmx768m`.

Ví dụ, JVM dùng 1 GiB làm cơ sở tính, khi chạy:

~~~bash
java -Xms256m -XX:MaxRAMPercentage=70 -jar app.jar
~~~

thì initial heap là **256 MiB**, còn maximum heap mục tiêu xấp xỉ **716,8 MiB** (có thể bị làm tròn và ảnh hưởng bởi các ergonomic constraints). Nếu thêm `-Xmx640m` thì maximum thành **640 MiB**, không phải 716,8 MiB.

**Cảnh báo quan trọng cho Java hiện hành:** Trong **JDK 26**, Oracle/HotSpot thay đổi **giá trị mặc định của `InitialRAMPercentage` từ 1.5625 sang 0**. Khi không cấu hình initial heap, JVM dùng cách định cỡ dựa trên `MinHeapSize` và ergonomics, thay vì mặc định lấy 1/64 memory basis. Các hướng dẫn Java 17/21/24 cho rằng **mặc định luôn là 1.5625%** không còn đúng cho JDK 26.

Ngoài ra, **heap không bằng tổng bộ nhớ container**. JVM còn tiêu thụ metaspace, thread stacks, JIT code cache, off-heap/direct buffers, JNI và GC/native memory. Không được đặt heap max bằng 100% cgroup limit rồi mặc định ứng dụng không bị OOMKilled.

## 2. Memory basis: phần trăm của bộ nhớ nào?

HotSpot có hỗ trợ nhận biết tài nguyên container từ **Java 10**. Khi chạy trên Linux/cgroups được hỗ trợ và `-XX:+UseContainerSupport` có hiệu lực (thường bật mặc định), JVM có thể dùng **giới hạn bộ nhớ cgroup** làm cơ sở cho các quyết định kích thước heap, thay vì coi toàn bộ RAM node là dành riêng cho container.

Ví dụ:

~~~text
RAM vật lý node:           32 GiB
Container memory limit:     1 GiB
Memory basis JVM phát hiện: 1 GiB
MaxRAMPercentage=70
Target heap max:            ~716.8 MiB
~~~

Đây là **ví dụ minh họa**, không phải số đo của một Pod cụ thể. Memory basis thực tế có thể bị ảnh hưởng bởi RAM vật lý, cgroup limit cha, cgroup version, flags như `-XX:MaxRAM`, và khả năng container detection của bản HotSpot.

### Requests và limits trong Kubernetes

~~~yaml
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "1Gi"
~~~

- **Memory request 512 MiB** tham gia scheduling/QoS; nó **không phải** hard upper limit cho JVM heap.
- **Memory limit 1 GiB** là giới hạn được container runtime/kernel áp dụng qua cgroup trên Linux; nó thường quyết định cơ sở sizing khi HotSpot nhận đúng hạn mức.
- Nếu **không có memory limit**, JVM có thể dựa vào available/physical memory khác, không tự lấy `requests.memory` làm trần.
- Một Pod có thể gồm nhiều containers; các giới hạn của từng container không được nhầm với tổng RAM của node.

**Đừng lấy `MaxRAMPercentage × requests.memory`** để dự đoán heap mà không kiểm tra cgroup và thực tế JVM đang nhìn thấy.

### Cgroups v2

Trong Linux container dùng cgroups v2, có thể đọc:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

`memory.max` là giới hạn hard memory, hoặc `max` khi cgroup đó không đặt giới hạn. `memory.current` là usage tính cho cgroup theo kernel. `memory.events` giúp theo dõi sự kiện memory pressure/OOM theo **độ chênh counter**.

Các đường dẫn chỉ áp dụng trong các container/namespace Linux tương thích. Nếu `memory.max=max`, vẫn có thể có giới hạn khác từ **cgroup cha**, node contention hoặc policy Kubernetes. Không suy ra JVM có thể dùng RAM vô hạn.

## 3. `-Xms` và `-Xmx` thực sự đặt gì?

### `-Xms<size>`

~~~bash
java -Xms256m -jar app.jar
~~~

Trong HotSpot, `-Xms` đặt **initial và minimum Java heap size**. Nó không có nghĩa tất cả 256 MiB đều chứa Java objects sống ở thời điểm khởi động. Việc reserve, commit, touch physical pages và đo RSS có thể khác tùy collector, platform và flags.

### `-Xmx<size>`

~~~bash
java -Xmx768m -jar app.jar
~~~

`-Xmx` đặt **maximum heap size** (tương đương `-XX:MaxHeapSize` trong HotSpot). Đây **không phải** upper bound cho toàn bộ RSS hay cgroup memory usage.

Hai đầu mút có thể cùng được đặt:

~~~bash
java -Xms256m -Xmx768m -jar app.jar
~~~

Với cấu hình trên, heap có thể mở rộng theo workload và GC giữa minimum/initial và max. Nếu đặt `-Xms768m -Xmx768m`, JVM có initial bằng maximum, có thể giúp tránh mở rộng heap nhưng làm startup/footprint lớn hơn.

**Không có quy tắc “mọi dịch vụ container phải dùng `-Xms=-Xmx`”.** Tùy workload, memory pressure và yêu cầu startup.

### Sai quan hệ min/max

~~~bash
java -Xms768m -Xmx512m -jar app.jar
~~~

Initial lớn hơn maximum nên cấu hình không hợp lệ. Các lựa chọn phần trăm cũng cần được đánh giá để initial hữu hiệu **không lớn hơn** maximum hữu hiệu.

## 4. Hai tỷ lệ chính: InitialRAMPercentage và MaxRAMPercentage

### `-XX:InitialRAMPercentage=P`

Khi chưa đặt initial heap bằng `-Xms` hay `-XX:InitialHeapSize`, cờ này đề xuất initial heap dựa trên **P% memory basis**, trước các điều chỉnh của HotSpot.

~~~bash
java -XX:InitialRAMPercentage=10 -jar app.jar
~~~

Với memory basis 1 GiB, con số tính nháp là **102,4 MiB**. Kết quả hiệu lực có thể khác vì minimum heap, GC region/page alignment và JVM ergonomics.

**Initial không phải maximum**: `InitialRAMPercentage=10` không ngăn heap lớn dần tới `-Xmx` hoặc mức max được chọn bằng `MaxRAMPercentage`.

### `-XX:MaxRAMPercentage=P`

Khi chưa đặt max bằng `-Xmx`/`MaxHeapSize`, cờ này dùng P% memory basis để định cỡ maximum heap.

~~~bash
java -XX:MaxRAMPercentage=70 -jar app.jar
~~~

Với memory basis 1 GiB, maximum mục tiêu xấp xỉ **716,8 MiB** trước những chi tiết sizing của VM. Nó không đảm bảo sẽ dùng hết 716,8 MiB, không cấp phát trước toàn bộ RAM, và không trực tiếp đặt giới hạn memory của cgroup.

### Cấu hình đồng thời

~~~bash
java -XX:InitialRAMPercentage=15 -XX:MaxRAMPercentage=70 -jar app.jar
~~~

Ý nghĩa: initial khoảng 15%, max khoảng 70% của memory basis nếu không có explicit sizing can thiệp. Giá trị thực phải được đọc lại từ JVM. Có thể đặt **một tỷ lệ** mà không đặt tỷ lệ còn lại.

## 5. Bảng ưu tiên và tương tác quan trọng nhất

Giả sử HotSpot xác định memory basis **1024 MiB**, và các kích thước sau là **mục tiêu** trước rounding khi không ghi explicit:

| Cấu hình | Initial heap | Maximum heap |
| --- | --- | --- |
| `InitialRAMPercentage=10 MaxRAMPercentage=70` | ~102,4 MiB | ~716,8 MiB |
| `-Xms256m MaxRAMPercentage=70` | **256 MiB** | ~716,8 MiB |
| `InitialRAMPercentage=10 -Xmx768m` | ~102,4 MiB | **768 MiB** |
| `-Xms256m -Xmx768m` | **256 MiB** | **768 MiB** |
| `InitialRAMPercentage=50 MaxRAMPercentage=90 -Xms256m -Xmx768m` | **256 MiB** | **768 MiB** |
| `-Xms192m MaxRAMPercentage=50 InitialRAMPercentage=50` | **192 MiB** | ~512 MiB |
| `-Xmx384m InitialRAMPercentage=12.5 MaxRAMPercentage=75` | ~128 MiB | **384 MiB** |

**Không có phép tính chung kiểu “lấy số lớn hơn trong hai flags”.** Cờ explicit ở phía initial quyết định initial, cờ explicit ở phía maximum quyết định max. Một percentage flag vẫn có thể xuất hiện trong `PrintFlagsFinal` nhưng **không quyết định effective heap size** ở đầu mút đã có explicit byte size.

Nếu cùng đặt cả `-Xmx` và `-XX:MaxHeapSize` với số khác nhau, hãy coi đó là cấu hình vận hành khó hiểu cần loại bỏ. Hai cách đặt cùng max heap không phải hai nguồn độc lập có thể cộng lại. Tương tự, `-Xms` và `-XX:InitialHeapSize` có liên hệ thứ tự xuất hiện như Java launcher docs mô tả; tốt nhất chỉ định **một nguồn cấu hình rõ ràng** cho mỗi đầu mút.

### Vẫn phải kiểm tra initial ≤ max

~~~bash
java -XX:InitialRAMPercentage=80 -Xmx256m -jar app.jar
~~~

Nếu memory basis 1 GiB, initial tính nháp 819,2 MiB, vượt Xmx 256 MiB. Đừng dựa vào việc VM sẽ tự sửa mọi quan hệ xấu. Hãy kiểm tra flags và kết quả khởi động; cấu hình này **không phải phương án hợp lý**.

## 6. `MinRAMPercentage`: không phải `-Xms`

Tên `MinRAMPercentage` rất dễ gây nhầm thành “RAM tối thiểu mà heap được cấp”. **Theo Oracle Java launcher, `MinRAMPercentage` điều chỉnh _maximum heap sizing_ trong môi trường có ít bộ nhớ**, thường ở vùng khoảng **125 MB** theo ngưỡng ergonomics của HotSpot.

Ví dụ:

~~~bash
java -XX:MinRAMPercentage=50 -XX:MaxRAMPercentage=25 -jar app.jar
~~~

Nếu memory basis rất nhỏ, maximum heap có thể được định cỡ bằng **50%** thay vì 25%. Vì vậy không phải lúc nào lấy memory limit × MaxRAMPercentage cũng cho max heap trên cấu hình nhỏ.

**So sánh ba tỷ lệ:**

| Cờ | Phần heap mà cờ liên quan | Ghi chú |
| --- | --- | --- |
| `InitialRAMPercentage` | **Initial heap** | Dùng khi initial không explicit |
| `MaxRAMPercentage` | **Maximum heap** | Dùng cho sizing thông thường khi max không explicit |
| `MinRAMPercentage` | **Maximum heap cho small-memory environment** | **Không phải** minimum heap; thường áp dụng vùng RAM thấp |

### Giá trị mặc định và thay đổi JDK 26

| Cờ | JDK 24/25 (HotSpot) | JDK 26 (HotSpot) |
| --- | --- | --- |
| `MaxRAMPercentage` | 25% | 25% |
| `MinRAMPercentage` | 50% cho small heaps | 50% cho small heaps |
| `InitialRAMPercentage` | 1.5625% | **0**, không còn mặc định 1.5625% |

**Oracle JDK 26 release notes, JDK-8371986:** khi người dùng không chỉ định initial heap bằng `-Xms` hoặc `-XX:InitialHeapSize`, HotSpot **không còn lấy giá trị default 1/64 system memory**. Initial mặc định chuyển về `MinHeapSize` do JVM ergonomics xác định, giúp giảm công việc khởi tạo heap và startup time trên những máy có nhiều RAM.

Bạn vẫn **có thể đặt explicit `-XX:InitialRAMPercentage=1.5625`** nếu muốn thử lại hành vi percentage đó; hoặc đặt `-Xms` nếu cần số byte cụ thể. **Không dùng default JDK 24 để giải thích default JDK 26.**

## 7. Kiểm chứng năm kịch bản trên JDK 24

Để chủ động kiểm tra quy tắc trên một máy dev mà không cần container, trong lab ta sử dụng:

~~~text
-XX:MaxRAM=1024m
~~~

Flag này thay đổi **cơ sở memory sizing của JVM**; nó **không tạo cgroup 1 GiB** và không đặt hard RAM limit tại Linux kernel.

**Đã kiểm thử thật trên OpenJDK 24.0.2, HotSpot G1:** các kịch bản dưới đây cho:

| Lab | Flags | Initial quan sát | Maximum quan sát |
| --- | --- | --- | --- |
| A | `MaxRAM=1024m InitialRAMPercentage=12.5 MaxRAMPercentage=50` | 128 MiB | 512 MiB |
| B | `MaxRAM=1024m InitialRAMPercentage=50 MaxRAMPercentage=75 -Xms192m -Xmx384m` | **192 MiB** | **384 MiB** |
| C | `MaxRAM=1024m InitialRAMPercentage=50 MaxRAMPercentage=50 -Xms192m` | **192 MiB** | 512 MiB |
| D | `MaxRAM=1024m InitialRAMPercentage=12.5 MaxRAMPercentage=75 -Xmx384m` | 128 MiB | **384 MiB** |
| E | `MaxRAM=64m MinRAMPercentage=50 MaxRAMPercentage=25` | 8 MiB | **32 MiB** |

Ở **B**, mặc dù tỷ lệ 50/75 có thể ngụ ý 512/768 MiB, cặp explicit `-Xms192m -Xmx384m` vẫn quyết định **192/384 MiB**.

Ở **C**, chỉ initial bị `-Xms` override; max vẫn 50% của 1024 MiB.

Ở **D**, chỉ maximum bị `-Xmx` override; initial vẫn 12,5% của 1024 MiB.

Ở **E**, memory basis nhỏ khiến `MinRAMPercentage` được xét để sizing maximum. **Initial 8 MiB chỉ là kết quả của JDK 24/G1 trong phép thử**, không phải bảo đảm đúng default JDK 26.

**Không dùng các con số lab này như một bảng bắt buộc cho mọi JDK/collector/OS**; có rounding/minimums theo VM.

## 8. Chương trình Java đầy đủ để in kích thước hiệu lực

Lưu tệp **`HeapPrecedenceDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class HeapPrecedenceDemo {

    private static long mib(long bytes) {
        return bytes / (1024L * 1024L);
    }

    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        Runtime runtime = Runtime.getRuntime();

        System.out.println("heapInitMiB="
                + mib(heap.getInit()));
        System.out.println("heapMaxMiB="
                + mib(heap.getMax()));
        System.out.println("runtimeMaxMiB="
                + mib(runtime.maxMemory()));
        System.out.println("initNotAboveMax="
                + (heap.getInit() <= heap.getMax()));
    }
}
~~~

Đây là **chương trình hoàn chỉnh chạy được trên JDK 17+**, chỉ sử dụng các API Java đã có từ trước Java 10.

Biên dịch:

~~~bash
javac HeapPrecedenceDemo.java
~~~

### Lab A — chỉ percentages

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=1024m -XX:InitialRAMPercentage=12.5 -XX:MaxRAMPercentage=50 HeapPrecedenceDemo
~~~

**`stdout` thực tế JDK 24.0.2:**

~~~text
heapInitMiB=128
heapMaxMiB=512
runtimeMaxMiB=512
initNotAboveMax=true
~~~

### Lab B — cặp `-Xms` và `-Xmx` thắng

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=1024m -XX:InitialRAMPercentage=50 -XX:MaxRAMPercentage=75 -Xms192m -Xmx384m HeapPrecedenceDemo
~~~

**`stdout`:**

~~~text
heapInitMiB=192
heapMaxMiB=384
runtimeMaxMiB=384
initNotAboveMax=true
~~~

### Lab C — initial explicit, maximum percentage

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=1024m -XX:InitialRAMPercentage=50 -XX:MaxRAMPercentage=50 -Xms192m HeapPrecedenceDemo
~~~

**`stdout`:**

~~~text
heapInitMiB=192
heapMaxMiB=512
runtimeMaxMiB=512
initNotAboveMax=true
~~~

### Lab D — initial percentage, maximum explicit

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=1024m -XX:InitialRAMPercentage=12.5 -XX:MaxRAMPercentage=75 -Xmx384m HeapPrecedenceDemo
~~~

**`stdout`:**

~~~text
heapInitMiB=128
heapMaxMiB=384
runtimeMaxMiB=384
initNotAboveMax=true
~~~

### Lab E — bộ nhớ rất nhỏ

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=64m -XX:MinRAMPercentage=50 -XX:MaxRAMPercentage=25 HeapPrecedenceDemo
~~~

**`stdout`:**

~~~text
heapInitMiB=8
heapMaxMiB=32
runtimeMaxMiB=32
initNotAboveMax=true
~~~

**Giải thích output:**

- `heapInitMiB` đọc từ `MemoryMXBean.getHeapMemoryUsage().getInit()`: initial heap do JVM reporting.
- `heapMaxMiB` đọc `getMax()`: maximum heap được quản lý.
- `runtimeMaxMiB` dùng `Runtime.maxMemory()`: giới hạn heap mà ứng dụng có thể quan sát.
- `initNotAboveMax=true`: quan hệ initial ≤ max hợp lệ trong các kịch bản kiểm thử.

**Điểm tránh sai:** các số là kết quả **memory sizing**, không phải mẫu đo Linux cgroup thực. Muốn kiểm tra behavior OOMKilled, phải chạy trong một Linux container có giới hạn bộ nhớ thật và quan sát kernel/cgroup metrics. Các tỷ lệ trong lab là input, **không phải đo trực tiếp %RAM của máy thử**.

## 9. Kiểm tra effective JVM flags thay vì chỉ đọc manifest

### `-XX:+PrintFlagsFinal`

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Để xem các flags liên quan sau khi set:

~~~bash
java -Xms192m -Xmx384m -XX:InitialRAMPercentage=50 -XX:MaxRAMPercentage=75 -XX:+PrintFlagsFinal -version
~~~

Bạn cần tìm:

- `InitialHeapSize`.
- `MinHeapSize`.
- `MaxHeapSize`.
- `InitialRAMPercentage`.
- `MaxRAMPercentage`.
- `MinRAMPercentage`.

Trong lab, với cặp explicit, HotSpot in **`InitialHeapSize=201326592`** và **`MaxHeapSize=402653184`** (byte), tức **192 MiB** và **384 MiB**. Các flag percentage vẫn hiện 50 và 75 nhưng **không quyết định giá trị heap của hai đầu mút đã explicit**.

Trên Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version | grep -E 'InitialHeapSize|MinHeapSize|MaxHeapSize|InitialRAMPercentage|MaxRAMPercentage|MinRAMPercentage'
~~~

Trên Windows PowerShell:

~~~text
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String "InitialHeapSize|MinHeapSize|MaxHeapSize|InitialRAMPercentage|MaxRAMPercentage|MinRAMPercentage"
~~~

**Cẩn thận:** `java -version` thường ghi ra stderr; đó không có nghĩa JVM bị lỗi. Khi dùng PowerShell với chế độ xử lý stderr nghiêm ngặt, hãy kiểm tra exit code của process, không coi mọi dòng stderr của launcher là exception trong Java.

### `-XshowSettings` và container logs

~~~bash
java -XshowSettings:vm -version
~~~

Hiển thị các VM settings hữu ích. Trên Linux container:

~~~bash
java -XshowSettings:system -version
java '-Xlog:os+container=trace' -version
~~~

`-XshowSettings:system` dùng để xem thông tin host/container trên **Linux**, còn tag `os+container` cho phép phân tích quá trình container detection trong HotSpot. Không lấy kết quả của một chương trình chạy trên Windows rồi gọi nó là giới hạn cgroup Linux của Pod.

## 10. Heap init, max, committed, used và RSS là các số khác nhau

Có thể xem qua `MemoryUsage`:

- **init**: kích thước ban đầu được JVM báo.
- **max**: giới hạn heap mà VM báo.
- **committed**: heap memory được JVM committed theo ngữ nghĩa JVM.
- **used**: lượng heap objects đang chiếm theo phép đo JVM.
- **RSS/cgroup memory.current**: hệ điều hành/kernel tính memory cho process/cgroup, bao gồm những vùng **không chỉ là Java heap**.

Ví dụ:

~~~java
MemoryUsage usage =
        ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

System.out.println(usage.getInit());
System.out.println(usage.getUsed());
System.out.println(usage.getCommitted());
System.out.println(usage.getMax());
~~~

Đây là **mảnh mã minh họa bên trong phương thức**. Không có stdout cố định vì heap usage phụ thuộc runtime, allocation và GC.

**Không nhầm:**

- `Runtime.totalMemory()`: memory JVM đang dành cho heap capacity theo runtime; không nhất thiết bằng max.
- `Runtime.freeMemory()`: free bytes trong current heap capacity; **không phải** RAM rảnh của cgroup.
- `Runtime.maxMemory()`: heap max; **không phải** cgroup memory.max.
- NMT `reserved`: virtual address space reserve; **không phải** số trang RAM đã commit hay RSS.

## 11. Vì sao `MaxRAMPercentage=100` có thể gây OOMKilled?

Một Java process sử dụng nhiều loại bộ nhớ:

~~~text
Container memory limit
    |
    +-- Java heap (giới hạn bởi Xmx)
    +-- Metaspace + class metadata
    +-- JIT compiled code cache
    +-- Thread stacks, thread structures
    +-- DirectByteBuffer / mapped buffers
    +-- GC bookkeeping, JNI/native allocations
    +-- Các charges khác theo cơ chế cgroup
~~~

Nếu max heap gần 100% memory limit, phần còn lại **không đủ** cho native overhead khi ứng dụng đạt peak. Vì vậy container có thể bị kernel kill mà không có Java heap `OutOfMemoryError` rõ ràng.

Ví dụ tính nháp:

~~~text
Container limit           : 1,024 MiB
-Xmx                      :   900 MiB
Heap used                 :   740 MiB
Các khoản ngoài heap      :   350 MiB
Tổng minh họa             : 1,090 MiB
~~~

Đây là **mô hình giả định**, không phải phép cộng RSS chính xác; nhưng nó cho thấy lý do **heap còn cách Xmx vẫn có thể OOMKilled**.

### Chọn heap percentage theo budget

Một công thức dự trù:

\[
\text{heap budget} \le \text{container limit} -
\text{nonheap peak} - \text{safety margin}
\]

Ví dụ memory limit **1024 MiB**, nonheap dự kiến **256 MiB**, safety margin **64 MiB**:

~~~text
Heap budget = 1024 - 256 - 64 = 704 MiB
704 / 1024 ≈ 68.75%
~~~

Có thể thử tỷ lệ `MaxRAMPercentage` gần 68% trong tình huống này, sau đó **đo**. Đây **không phải khuyến nghị cố định 68% cho mọi ứng dụng**; mức phù hợp phụ thuộc thread count, direct buffers, metaspace, collector và workload.

Không được xem “75%” là chuẩn không cần kiểm tra. Một số dịch vụ cần 50% hoặc thấp hơn; một số khác có thể phù hợp tỷ lệ cao hơn nếu các nhóm memory ngoài heap đã được kiểm soát và đo đầy đủ.

## 12. `-Xms` lớn, `-Xms=-Xmx` và `AlwaysPreTouch`

**`-Xms` lớn** có thể giúp giảm số lần mở rộng heap khi workload tăng, nhưng có thể khiến JVM chuẩn bị/commit nhiều heap memory từ sớm.

Nếu cấu hình:

~~~bash
java -Xms768m -Xmx768m -XX:+AlwaysPreTouch -jar app.jar
~~~

thì `AlwaysPreTouch` khiến JVM chạm trước các trang heap đã committed theo hành vi HotSpot, có thể làm startup tốn công và bộ nhớ resident xuất hiện sớm hơn. Với Pod có memory limit chật, cách này có thể làm tăng rủi ro memory pressure ngay lúc khởi động.

**Không khẳng định `-Xms768m` tự động đồng nghĩa RSS=768 MiB ở thời điểm đầu**. Virtual reservation, commit, physical page touching và GC có khác biệt.

### Khi nào `-Xms=-Xmx` có ích?

Có thể phù hợp nếu:

- Ứng dụng chạy lâu, working set lớn và ổn định.
- Đã xác định đủ RAM cho cả heap và native memory.
- Muốn hạn chế động tác mở rộng heap và đã đo startup/GC.

Có thể không phù hợp nếu:

- Ứng dụng ngắn hạn/serverless.
- Memory limit nhỏ.
- Tải dao động lớn cần tiết kiệm footprint khi rảnh.
- JDK 26 default initial heap nhỏ hơn đã cho startup tốt và không có lý do ép heap lớn.

**Chỉ quyết định sau khi đo**, không dựa vào quy tắc chung của một bài viết cũ.

## 13. `MaxRAM` không phải cgroup limit

Trong bài lab dùng:

~~~bash
java -XX:MaxRAM=1024m -XX:MaxRAMPercentage=50 HeapPrecedenceDemo
~~~

`MaxRAM` là **cơ sở tối đa được JVM dùng để định cỡ heap**. Nó không phải:

- Một lệnh Docker set memory limit.
- Một file cgroup.
- Cơ chế kernel thực thi hard cap.
- Một mức RSS của Java process.

Để thí nghiệm OOM của container, phải đặt **memory limit thật** qua container runtime/Kubernetes và đọc `memory.max`, `memory.current`, `memory.events`.

Nếu Pod limit 1 GiB mà JVM bị ép `MaxRAM=4g` hoặc được cấp `-Xmx3g`, Java heap có thể được định cỡ quá lớn so với giới hạn kernel. Rủi ro OOMKilled vẫn tồn tại dù phần trăm được tính chính xác trên **memory basis sai**.

## 14. Tránh trùng flags ở Dockerfile, Helm và biến môi trường

Options có thể đến từ nhiều nơi:

- Dockerfile `ENTRYPOINT`/`CMD`.
- Shell script khởi động.
- Helm chart values.
- Kubernetes Deployment YAML.
- Biến môi trường `JAVA_TOOL_OPTIONS`.
- Biến môi trường `JDK_JAVA_OPTIONS`.
- Cấu hình của framework/build tool.

Ví dụ cấu hình khó hiểu:

~~~text
Kubernetes memory limit   : 1Gi
Helm value                : MaxRAMPercentage=70
Dockerfile ENTRYPOINT     : -Xmx2g
~~~

Người đọc Helm chart có thể tưởng maximum heap ~716,8 MiB; nhưng `-Xmx2g` đặt byte size explicit, **không bị giảm bởi tỷ lệ 70%**. Đây là nguyên nhân phổ biến của mismatch giữa manifest và JVM runtime.

**Phương pháp an toàn:** chọn **một nguồn sở hữu mỗi JVM sizing option**, đồng bộ với deployment resources và xác minh `MaxHeapSize`/`InitialHeapSize` trên chính process sau startup. Nếu có explicit `-Xmx`, đừng gửi thêm percentage chỉ để “đề phòng” rồi coi chúng là hai lớp giới hạn.

## 15. Thay memory limit khi JVM đang chạy

Khi một deployment thay memory limit từ 1 GiB lên 2 GiB:

- **JVM khởi động mới** với `MaxRAMPercentage` có thể tính max heap dựa trên limit mới nếu container awareness nhận đúng.
- **JVM khởi động mới** với `-Xmx768m` vẫn dùng max heap 768 MiB, trừ khi flag được đổi.
- **JVM đã chạy** không có cam kết phổ quát rằng mọi live change cgroup sẽ tự làm JVM tính lại `-Xmx` hay `MaxHeapSize`.

Vì vậy sau khi thay memory tier hoặc nâng JDK, nên **rollout/restart theo quy trình** rồi xác minh effective flags. Không suy rằng sửa manifest tự động làm mọi JVM đang chạy thay đổi memory sizing tương ứng.

## 16. Java heap OOM khác OOMKilled của container

### Java heap OOM

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

JVM có thể ném khi không cấp phát được object trong phạm vi heap. Nếu process còn khả năng xử lý, có thể có Java exception/log/heap dump theo cài đặt phù hợp.

### Container OOMKilled

Linux kernel có thể kill process khi cgroup chạm memory limit và không reclaim được. Kubernetes có thể báo `reason: OOMKilled`, thường với exit code `137`.

**Không chỉ dựa vào exit code 137 để kết luận**: SIGKILL trong những hoàn cảnh khác cũng có thể cho mã tương tự. Đọc termination reason, Pod events, cgroup memory.events và timeline.

| Số liệu | Mục đích |
| --- | --- |
| `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Heap objects usage |
| `getMax()` / `Runtime.maxMemory()` | Maximum Java heap |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Một phần nonheap JVM pools, không phải mọi native allocations |
| `memory.current` | Memory charge theo cgroup |
| `memory.max` | Cgroup hard limit |
| `memory.events` | Các sự kiện liên quan pressure/OOM |
| Process RSS | Memory resident theo OS/process |
| `jcmd VM.native_memory` | Một số nhóm HotSpot native memory khi bật NMT |

**Heap used thấp không đồng nghĩa process không thể OOMKilled.**

## 17. Native Memory Tracking để tìm overhead ngoài heap

Trong HotSpot, bật **Native Memory Tracking (NMT)** từ lúc khởi động nếu cần điều tra:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Rồi chạy công cụ `jcmd` đối với JVM được phép truy cập:

~~~bash
jcmd PID VM.native_memory summary
jcmd PID VM.native_memory baseline
jcmd PID VM.native_memory summary.diff
~~~

Thay `PID` bằng process ID thực tế. NMT có thể thống kê các vùng HotSpot VM internal memory như Class, Thread, Code, GC và Java Heap virtual/committed reservations.

**Giới hạn:** NMT không đo mọi allocations của thư viện native bên thứ ba, JNI hoặc phần bộ nhớ mà kernel tính cho cgroup. Nó có overhead và phải được bật khi JVM khởi động; không thể mặc định `jcmd` truy vấn ra đầy đủ dữ liệu ở một process không bật NMT.

**Không cộng NMT reserved rồi gọi đó là RSS.** `reserved` là address-space reservation; `committed` và physical resident pages có những định nghĩa khác.

## 18. Kịch bản vận hành

### A. Một ứng dụng ở Pod 512 MiB và 2 GiB

Nếu dùng `-Xmx512m` ở mọi Pod, container 512 MiB gần như không còn chỗ cho native memory, trong khi container 2 GiB lại có thể chưa tận dụng được heap cần thiết.

Một lựa chọn khi đã có số đo:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

JVM khởi động lại với limit khác có thể định cỡ heap theo tier mới, nhưng **60% cũng không đảm bảo mọi workload vừa native headroom**. Đo cả trường hợp Pod nhỏ nhất.

### B. Workload ổn định, muốn explicit memory budget

~~~bash
java -Xms256m -Xmx768m -jar app.jar
~~~

Nếu Pod 1 GiB, vẫn cần chứng minh nonheap peak và safety margin nằm trong khoảng còn lại. Không chỉ xem hiệu năng GC.

### C. Khởi động nhanh trên JDK 26

Trên JDK 26, initial heap mặc định đã giảm về `MinHeapSize` theo JVM ergonomics khi không có initial sizing. Đừng tự đặt `-Xms768m` chỉ vì bài hướng dẫn từ JDK trước nói heap ban đầu phải lớn. Hãy đo startup, RSS và GC để quyết định.

### D. Ứng dụng nhiều platform threads hoặc direct buffers

Thread stacks, code cache, Metaspace, direct/off-heap buffers có thể chiếm lượng lớn. Ứng dụng loại này cần **MaxRAMPercentage thấp hơn hoặc memory limit cao hơn** so với ứng dụng chỉ có heap objects và ít threads.

Virtual threads (Java 21+) hữu ích cho một số công việc đợi I/O nhưng không xóa mọi native/off-heap memory và không tạo thêm RAM budget.

### E. Incident sau rollout

Nếu sau thay JDK/manifest bị OOMKilled, thu thập lần lượt:

1. JVM version/build.
2. Memory limits và file cgroup.
3. JVM effective InitialHeapSize/MaxHeapSize.
4. Heap used/committed/max.
5. Process RSS/cgroup memory.current.
6. Thread count, metaspace, direct buffers, NMT nếu có.
7. GC/OOM events và thời điểm khởi động/tăng tải.

Từ dữ liệu đó mới quyết định giảm Xmx, thay percentage, giảm native memory, tăng container limit hay sửa memory leak.

## 19. Các lỗi hiểu nhầm phổ biến

| Hiểu sai | Sửa lại |
| --- | --- |
| “`MaxRAMPercentage` là giới hạn tổng RAM của Pod.” | Nó định cỡ **Java heap max**, không phải kernel hard memory cap. |
| “`-Xmx` và MaxRAMPercentage cộng lại.” | Max heap chỉ có một giá trị hiệu lực; explicit Xmx thắng sizing percentage tương ứng. |
| “`InitialRAMPercentage` ghi đè mọi `-Xms`.” | Explicit `-Xms` đặt initial/minimum. |
| “Chỉ có `-Xms` thì tự đặt lại `-Xmx`.” | Hai đầu mút độc lập; max còn theo các lựa chọn khác. |
| “`MinRAMPercentage` là `-Xms` theo phần trăm.” | Nó áp vào **maximum heap sizing khi bộ nhớ nhỏ**. |
| “Initial mặc định luôn 1.5625%.” | Không còn đúng ở **JDK 26**. |
| “MaxRAMPercentage=100 không thể OOM.” | Native/off-heap memory có thể làm container OOMKilled. |
| “Xmx=768m nghĩa RSS≤768MiB.” | Heap max không giới hạn process RSS. |
| “`Runtime.freeMemory` cho RAM còn lại của Pod.” | Nó cho free space trong Java heap hiện tại. |
| “`MaxRAM` tạo quota OS.” | Nó đặt memory sizing basis của JVM. |
| “Memory request là giới hạn dùng để tính heap.” | Request không phải hard memory limit. |
| “Nếu heap used chưa chạm Xmx, không thể OOMKilled.” | Native memory vẫn được cgroup tính. |
| “Đổi Pod limit thì JVM đang chạy tự tăng Xmx.” | Không có bảo đảm chung; verify sau rollout. |
| “Thấy InitialRAMPercentage=50 trong flags thì initial chắc chắn là 50%.” | Có thể đã bị explicit `-Xms` override. |
| “NMT cho thấy toàn bộ native allocations của mọi thư viện.” | NMT chủ yếu theo dõi HotSpot VM internal allocations, có giới hạn. |
| “`-Xms=-Xmx` luôn cải thiện startup.” | Có thể tăng startup/footprint; phải đo. |

## 20. Bài tập tự kiểm tra

### Câu 1 — cơ sở tính heap

Node có 32 GiB RAM, Pod limit 1 GiB, JVM nhận đúng limit. `MaxRAMPercentage=70` cho max heap mục tiêu bao nhiêu?

**Đáp án:** Khoảng 716,8 MiB trước JVM rounding/ergonomics, **không** phải 70% của 32 GiB.

### Câu 2 — explicit initial

`-Xms256m -XX:MaxRAMPercentage=70` với memory basis 1 GiB. Initial và maximum?

**Đáp án:** Initial 256 MiB, maximum mục tiêu ~716,8 MiB.

### Câu 3 — explicit max

`InitialRAMPercentage=10 -Xmx768m` với basis 1 GiB. Initial/max?

**Đáp án:** Initial mục tiêu 102,4 MiB, max 768 MiB.

### Câu 4 — cờ cùng xuất hiện

`-Xms192m -Xmx384m -XX:InitialRAMPercentage=50 -XX:MaxRAMPercentage=75`. Giá trị hiệu lực theo JDK 24 lab?

**Đáp án:** Initial 192 MiB, maximum 384 MiB. Explicit sizes được dùng dù flags phần trăm vẫn có giá trị.

### Câu 5 — small-memory

`MinRAMPercentage=50` có bắt buộc initial heap bằng 50% RAM không?

**Đáp án:** Không. Đây là cờ maximum heap sizing cho môi trường RAM nhỏ.

### Câu 6 — JDK 26 default

Vì sao không được khẳng định initial mặc định 1.5625% trên Java 26?

**Đáp án:** JDK-8371986 đã bỏ giá trị default này; initial theo MinHeapSize/JVM ergonomics nếu không explicit.

### Câu 7 — `MaxRAM`

Dùng `-XX:MaxRAM=1024m` có tạo Linux memory limit 1GiB không?

**Đáp án:** Không. Nó thay cơ sở tính của JVM, không cấu hình cgroup.

### Câu 8 — Xms lớn hơn Xmx

`-Xms768m -Xmx512m` có phải cấu hình hợp lý không?

**Đáp án:** Không, vì initial/minimum > maximum.

### Câu 9 — OOMKilled

Heap used chỉ 540 MiB, Xmx=768 MiB, container limit=1GiB vẫn bị OOMKilled. Vì sao?

**Đáp án:** Native/off-heap allocations, thread stacks, metaspace, direct buffers, GC memory và các memory charges khác có thể vượt giới hạn container.

### Câu 10 — kiểm tra thực tế

API nào nên đọc để biết initial và max heap JVM báo?

**Đáp án:** `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()` rồi `getInit()` và `getMax()`; có thể dùng `Runtime.maxMemory()` cho max.

### Câu 11 — memory requests

Kubernetes memory request 512 MiB, limit 1 GiB. Request có phải hard max mà JVM bắt buộc dùng không?

**Đáp án:** Không. Limit/cgroup effective memory mới là thông tin giới hạn quan trọng khi JVM hỗ trợ nhận biết.

### Câu 12 — InitialRAMPercentage và Xms

JVM flags in `InitialRAMPercentage=50` nhưng `InitialHeapSize=201326592`, và command line có `-Xms192m`. Có mâu thuẫn không?

**Đáp án:** Không. Giá trị percentage không quyết định effective initial vì đã có Xms explicit.

### Câu 13 — memory limit thay đổi

Pod đổi từ 1 GiB sang 2 GiB, JVM cũ chạy `-Xmx768m`. Có tự tăng heap max lên 1.5 GiB không?

**Đáp án:** Không. Explicit Xmx không tự đổi. JVM mới chỉ thay khi flags được cập nhật.

### Câu 14 — vì sao cần headroom?

Có nên mặc định đặt `MaxRAMPercentage=100` để tận dụng tối đa Pod memory?

**Đáp án:** Không. Phải dành nonheap/native memory và safety margin, sau đó load test.

### Câu 15 — quy trình xác minh

Nếu max heap khác con số tính từ phần trăm, nên kiểm tra gì?

**Đáp án:** Có `-Xmx`/MaxHeapSize explicit không, `MinRAMPercentage` và small-memory heuristics, container limit có được JVM nhận đúng không, các flags trùng/override, JDK/GC alignment, cuối cùng đọc `MaxHeapSize` hiệu lực.

## 21. Checklist triển khai

- [ ] Xác định JVM vendor/build/version, đặc biệt thay đổi default JDK 26.
- [ ] Xác định memory limit thật và memory request của Pod.
- [ ] Kiểm tra memory cgroup/parent constraints.
- [ ] Quyết định một nguồn sizing cho initial heap, một cho max heap.
- [ ] Tránh trùng `-Xms` với các flags initial không cần thiết và `-Xmx` với max percentage không cần thiết.
- [ ] Đảm bảo initial không lớn hơn maximum.
- [ ] Dành headroom cho metaspace, threads, JIT, direct/native allocations.
- [ ] Chạy kiểm tra JVM `-XX:+PrintFlagsFinal` và `-XshowSettings`.
- [ ] Dùng `MemoryMXBean` đo init/max/committed/used thực tế.
- [ ] Đo container memory.current, memory.max, memory.events trên Linux.
- [ ] Thử nghiệm startup, steady-state và peak load.
- [ ] Phân biệt Java heap OOM và container OOMKilled.
- [ ] Dùng NMT có kiểm soát khi cần điều tra native memory.
- [ ] Sau khi thay container limit hoặc nâng JDK, rollout và verify effective values.
- [ ] Không lấy output của một lab dùng `-XX:MaxRAM` làm bằng chứng container hard limit.

## 22. Tổng kết và nguồn tham khảo chính thức

**Kết luận:** `-Xms` và `-Xmx` là **định cỡ heap theo byte**, ưu tiên ở đầu mút tương ứng. `InitialRAMPercentage` và `MaxRAMPercentage` giúp **định cỡ theo memory basis**, phù hợp khi deploy cùng một ứng dụng ở nhiều container memory tiers. `MinRAMPercentage` dành cho **max heap trong môi trường RAM nhỏ**, không thay thế `-Xms`.

JDK 26 đã **đổi mặc định initial heap**; mọi phép tính và lời khuyên phải ghi rõ release. Dù dùng cách sizing nào, **Java heap max không đại diện toàn bộ RAM container**; cần theo dõi nonheap/native và cgroup để tránh OOMKilled.

### Nguồn còn hiệu lực

1. [Oracle Java SE 26 — `java` launcher](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-Xms`, `-Xmx`, `MaxRAM`, `InitialRAMPercentage`, `MaxRAMPercentage`, `MinRAMPercentage`, `-XshowSettings`.
2. [Oracle — JDK 26 Release Notes, JDK-8371986](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): thay đổi default InitialRAMPercentage/MinHeapSize.
3. [Inside Java — Java 26 for DevOps](https://inside.java/2026/03/02/jdk-26-rn-ops/): diễn giải của nhóm Java về thay đổi initial heap.
4. [Oracle Java SE 25 — java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): đối chiếu mặc định 1.5625% trước JDK 26.
5. [Linux Kernel — cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): memory.max/current/events, giới hạn bộ nhớ.
6. [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): memory requests, limits, OOM kill enforcement.
7. [Oracle Java SE 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/java-virtual-machine-guide.pdf): NMT và giới hạn của nó.
8. [Oracle Java SE 26 — MemoryMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap init, max, committed, used.
