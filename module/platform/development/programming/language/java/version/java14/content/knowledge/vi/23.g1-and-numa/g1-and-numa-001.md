# Kiến trúc bộ nhớ truy cập không đồng nhất (NUMA) và ý nghĩa đối với G1 GC

> **Ngữ cảnh:** Java 14 → *G1 và NUMA* → **Kiến trúc bộ nhớ truy cập không đồng nhất**. Hỗ trợ cấp phát bộ nhớ có nhận thức NUMA cho **G1 Garbage Collector** được cải thiện bằng **JEP 345, phát hành cùng JDK 14**. Cơ chế này tiếp tục có ý nghĩa với HotSpot/JDK hiện đại. Mọi ví dụ Java dùng **Java 17+**, không cần preview và không yêu cầu API legacy. Bài phân biệt rõ **kiến trúc phần cứng NUMA**, **chính sách bộ nhớ của hệ điều hành** và **tối ưu hóa trong JVM/G1**.

## 1. NUMA là gì?

**NUMA (Non-Uniform Memory Access)** là kiến trúc trong đó **thời gian truy cập bộ nhớ phụ thuộc vào vị trí của bộ nhớ so với CPU đang truy cập**.

Trên một hệ thống có nhiều CPU socket hoặc nhiều miền phần cứng, mỗi miền có thể có bộ điều khiển bộ nhớ và vùng RAM “gần” riêng. Một CPU thường đọc/ghi bộ nhớ **local** nhanh hơn bộ nhớ **remote** nằm ở miền khác; truy cập remote có thể phải đi qua liên kết giữa các socket hoặc liên kết nội bộ giữa các miền.

**Từ khóa cần hiểu:**

- **NUMA node:** một miền gồm CPU/nhóm CPU và các trang bộ nhớ có đặc tính truy cập tương đối gần nhau. Không phải lúc nào **1 NUMA node = 1 CPU socket**: cấu hình BIOS, NUMA-per-socket, máy ảo và topology phần cứng có thể tạo nhiều node trong một socket hoặc trường hợp đặc biệt khác.
- **Local memory:** trang RAM thuộc node gần CPU đang chạy thread.
- **Remote memory:** trang RAM thuộc một node khác; thường có chi phí độ trễ hoặc băng thông khác so với local.
- **NUMA distance:** chỉ số tương đối mô tả “độ xa” truy cập giữa các node do OS xuất ra; không phải thời gian nanosecond tuyệt đối.
- **CPU affinity:** tập CPU mà một thread/process được phép chạy; khi scheduler di chuyển thread giữa các node, trang bộ nhớ trước đây local có thể thành remote.
- **Memory placement / policy:** quyết định trang vật lý được phân bổ ở node nào, chịu ảnh hưởng OS, lần chạm trang đầu tiên (*first touch*), các giới hạn tài nguyên và nhu cầu bộ nhớ.

### Minh họa trực quan

~~~text
           NUMA NODE 0                     NUMA NODE 1
      +-------------------+            +-------------------+
      | CPU cores 0..N    |            | CPU cores N+1..M  |
      | local RAM bank    |            | local RAM bank    |
      +---------+---------+            +---------+---------+
                |                                |
           local access                     local access
                |                                |
                +---------- interconnect --------+
                        remote access path
~~~

Đây là sơ đồ khái niệm, không đại diện một máy cụ thể. Cả hai node vẫn có thể truy cập dữ liệu của nhau trong cùng không gian địa chỉ của hệ điều hành; **remote không có nghĩa là bị cấm truy cập**. Nó có nghĩa chi phí truy cập có thể khác.

**Khác với UMA:** Trong mô hình **Uniform Memory Access**, chi phí truy cập bộ nhớ được coi tương đối đồng đều giữa CPU và các vùng RAM. Với NUMA, một chính sách cấp phát/scheduling thiếu phù hợp có thể khiến ứng dụng thường xuyên đọc/ghi trang trên node xa dù RAM local còn sẵn.

## 2. Vì sao NUMA ảnh hưởng tới ứng dụng Java?

Một `Thread` Java thực thi trên các CPU core do OS scheduler chọn. Heap Java của HotSpot lại được hỗ trợ bởi các trang bộ nhớ vật lý do OS đặt trên những NUMA node khác nhau.

Hãy tưởng tượng:

1. Thread `A` đang chạy trên CPU thuộc **node 0**.
2. Thread `A` cấp phát nhiều object, các trang chứa chúng được OS đặt tại **node 0**.
3. Một thời gian sau, scheduler chuyển `A` sang CPU **node 1**, hoặc thread khác ở node 1 thường xuyên đọc các object đó.
4. Các lần truy cập bộ nhớ vốn local có thể trở thành **remote**. Nếu việc truy cập lớn và lặp lại, độ trễ và giới hạn băng thông interconnect có thể trở thành chi phí đáng kể.

Tương tự, nếu thread chạy trên node 0 nhưng các trang heap liên quan bị phân bổ nhiều trên node 1 ngay từ đầu, ứng dụng có thể trả giá cho remote accesses.

| Tình huống | Điều xảy ra | Tác động có thể quan sát |
| --- | --- | --- |
| CPU đọc dữ liệu trên node gần | Local memory access | Thường ít tốn chi phí liên kết hơn |
| CPU đọc dữ liệu trên node khác | Remote memory access | Có thể tăng latency, giảm băng thông hiệu dụng |
| Thread chuyển node sau khi cấp phát | Vị trí CPU thay đổi, trang RAM chưa chắc di chuyển | Dữ liệu vốn local có thể thành remote |
| Node local thiếu RAM | OS có thể cấp phát ở node khác hoặc dùng chính sách khác | Tối ưu local có thể không thực hiện được |
| Nhiều thread chia sẻ dữ liệu ở hai node | Tính local của dữ liệu khác nhau theo thread | Không có vị trí tốt nhất cho **mọi thread** |
| JVM/OS cân bằng locality tốt | Một phần working set gần thread truy cập | Có thể tăng throughput hoặc giảm tail latency |

**Không được suy luận:** mọi thao tác Java đều cần truy cập DRAM vật lý. Dữ liệu có thể được phục vụ từ CPU caches; JVM/JIT có thể tối ưu code; cache coherence cũng có chi phí riêng. NUMA là **một trong các tầng của hệ thống bộ nhớ**, không phải lời giải thích duy nhất cho độ trễ ứng dụng.

### NUMA khác với garbage collection

NUMA đề cập **chi phí truy cập bộ nhớ vật lý theo topology**. GC đề cập **quản lý vòng đời/cấp phát/thu hồi object**. G1 có thể dùng thông tin NUMA để **ưu tiên nơi cấp phát vùng heap**, nhưng NUMA **không làm thay đổi** điều kiện object sống/chết, bảo đảm thread-safety hoặc Java Memory Model.

Không có cú pháp Java thông thường như `new Object()` để chỉ định “object này chắc chắn nằm trên NUMA node 0” theo API chuẩn. Việc object nằm ở đâu là quyết định kết hợp giữa JVM, OS, topology và quá trình GC; vị trí có thể thay đổi sau một lần GC.

## 3. Page placement, first touch và CPU scheduling

### 3.1. Reserved memory không đồng nghĩa physical memory đã nằm ở một node

Khi JVM dành một dải **virtual address** cho heap, không nhất thiết mọi trang vật lý đã được cấp phát ngay lúc đó. OS thường gắn trang vật lý khi memory được commit/touch theo chính sách đang hoạt động. Tùy OS, `first touch` hoặc memory policy của process ảnh hưởng node cấp phát trang.

Vì vậy, `-Xmx16g` chỉ đặt **giới hạn heap tối đa**, không chứng minh đã có 16 GiB physical RAM tại một node cụ thể. Tương tự, báo heap “committed” không đủ để suy ra bố cục vật lý NUMA.

### 3.2. Đừng xem “trên cùng một máy” là “trên cùng một node”

Một process có thể được phép chạy trên nhiều node. Scheduler có thể chuyển thread; các thread trong cùng process cũng chạy trên những CPU khác nhau. Một object hoặc page có thể được nhiều thread truy cập, nhưng không thể local đồng thời cho mọi thread trên nhiều node.

**Hệ quả khi tối ưu:**

- Kiểm tra **CPU affinity và memory-node allowance** của process, nhất là container.
- Đo truy cập bộ nhớ thực, không chỉ xem thread names.
- Đừng ép tất cả thread vào một node nếu workload cần tổng CPU/RAM của nhiều node.
- Đừng tự bật memory interleaving hoặc binding cứng mà chưa kiểm tra tương tác với chính sách của JVM và GC.

### 3.3. NUMA distance do hệ điều hành công bố

Trên Linux có NUMA support, `numactl --hardware` hiển thị các node và ma trận distance. Một dạng kết quả **minh họa** có thể là:

~~~text
available: 2 nodes (0-1)
node 0 cpus: ...
node 1 cpus: ...
node distances:
node   0   1
  0:  10  21
  1:  21  10
~~~

Các con số trong ví dụ **không phải phép đo trên máy đang chạy bài này**; output thật khác theo hardware và firmware. Trong dạng biểu diễn này, 10/21 là **thước đo tương đối**. Không kết luận “remote mất đúng 21 ns” hoặc “chậm chính xác 2,1 lần” từ distance matrix.

## 4. G1 GC liên quan gì đến NUMA?

**G1 (Garbage-First)** là bộ thu gom rác vùng (*region-based collector*) của HotSpot. G1 chia Java heap thành nhiều **regions** (các vùng bộ nhớ), được sử dụng luân phiên cho:

- **Eden regions:** nơi phần lớn object bình thường được cấp phát ban đầu.
- **Survivor regions:** chứa object còn sống sau các lần young GC.
- **Old regions:** chứa object sống lâu hơn; có cả cơ chế xử lý riêng cho object rất lớn (*humongous*).

G1 thu gom các vùng khác nhau theo chu kỳ và có thể **di chuyển/copy** object sang vùng mới. Vì vậy, locality NUMA không chỉ phụ thuộc chỗ object được cấp phát lần đầu mà còn có thể bị ảnh hưởng bởi các lần GC.

### 4.1. JEP 345 đã bổ sung điều gì?

**JEP 345 — NUMA-Aware Memory Allocation for G1** được tích hợp trong **JDK 14**. Mục tiêu của cải tiến là giúp G1 cấp phát bộ nhớ hiệu quả hơn trên các máy **NUMA nhiều node**, đặc biệt là **phân bổ các Eden regions gần node của thread đang cấp phát** khi có thể.

Ở mức khái niệm:

1. JVM/OS xác định những NUMA nodes có thể sử dụng.
2. G1 theo dõi region tương ứng các nodes, và khi cần một Eden region cho thread, ưu tiên region có vị trí NUMA phù hợp.
3. Nếu không còn region thích hợp hoặc chính sách OS không cho phép, hệ thống **có thể fallback** sang vùng khác.
4. Khi object được copy/promote bởi GC, quan hệ local/remote có thể thay đổi.

Đây là mô tả **hành vi ưu tiên locality**, không phải cam kết mọi object đều mãi nằm trên node gần thread.

**Giới hạn cần nhớ:** cải tiến JEP 345 tập trung vào **young-generation/Eden allocation**, không biến toàn bộ G1 heap thành cơ chế cưỡng bức phân bổ object cho từng node. Old/survivor regions, dữ liệu chia sẻ, scheduler, page migration và chính sách OS vẫn ảnh hưởng locality. Trên một số cấu hình, chi phí bookkeeping/chiến lược cân bằng có thể khiến lợi ích thực tế nhỏ hoặc không có.

### 4.2. Mô hình cấp phát trước và sau khi ưu tiên locality

~~~text
Không xét locality rõ ràng:
  Thread trên node 0
       |
       +-- lấy một Eden region bất kỳ
                  |
                  +-- có thể ở node 0 hoặc node 1

Khi G1 NUMA-aware đang hoạt động:
  Thread trên node 0
       |
       +-- ưu tiên Eden region gắn node 0
                  |
                  +-- không có vùng phù hợp? fallback hợp lệ

G1 GC có thể copy object sang vùng survivor/old.
NUMA placement vì thế là tối ưu best-effort, không phải invariant.
~~~

Nếu heap nhỏ hơn RAM local, workload ít động tới RAM hoặc threads không được phân bổ trên nhiều node, lợi ích NUMA-aware có thể khó thấy. Ngược lại, ứng dụng server nhiều CPU socket, heap và allocation rate lớn có thể có lý do để kiểm nghiệm.

### 4.3. NUMA không thay thế tuning G1

Các mục tiêu tuning độc lập:

| Mục tiêu | Công cụ/cấu hình chính | Lưu ý |
| --- | --- | --- |
| Chọn collector | `-XX:+UseG1GC` | G1 là mặc định phổ biến trên HotSpot server hiện đại, nhưng nên xác nhận collector thực |
| Giới hạn heap | `-Xms`, `-Xmx` | Liên quan memory pressure và kích thước working set |
| Mục tiêu pause | `-XX:MaxGCPauseMillis=...` | Mục tiêu mềm, không cam kết mọi pause đều dưới mức này |
| Hướng cấp phát NUMA | `-XX:+UseNUMA` khi được collector/OS hỗ trợ | Đánh giá trên phần cứng NUMA nhiều node, không mặc định tăng hiệu năng |
| Đánh giá GC | `-Xlog:gc*` và thông số ứng dụng | GC logs không tự chứng minh local DRAM access |
| Đánh giá NUMA | OS topology, `numastat`, page placement và counters | Cần xét cả affinity, pressure và remote access |

Không nên đồng thời thay heap size, GC algorithm, thread count, OS memory policy và `UseNUMA` rồi gán mọi khác biệt benchmark cho một tùy chọn.

## 5. Xác định môi trường có NUMA hay không

### 5.1. Linux: kiểm tra topology

Trên một server Linux:

~~~bash
uname -s
uname -m
lscpu

# CPU nào thuộc NUMA node nào:
lscpu -e=CPU,NODE,SOCKET,CORE

# Khi numactl được cài và khả dụng:
numactl --hardware

# Thông tin node được kernel xuất qua sysfs:
cat /sys/devices/system/node/online
~~~

**Cách đọc:**

- Nếu chỉ có **một node có thể sử dụng**, không thể kỳ vọng tối ưu local-vs-remote giữa nhiều node sẽ có tác dụng đáng kể.
- Nếu máy vật lý có nhiều sockets, vẫn cần **xem topology mà OS/container/JVM thực sự thấy**, không suy diễn từ nhãn model CPU.
- Nếu `numactl` không tồn tại, đó là vấn đề thiếu **tiện ích OS**, không có nghĩa kernel chắc chắn không hỗ trợ NUMA. Có thể xem `lscpu`/sysfs hoặc cài công cụ theo chính sách quản trị máy.
- `uname -m` cho biết CPU architecture, **không** cho biết số NUMA nodes.
- Các lệnh trên **không thay đổi** chính sách cấp phát hay quyền trên máy.

### 5.2. Kiểm tra ràng buộc của chính process/container

~~~bash
# Cho biết CPU và các memory nodes mà process hiện tại được cho phép:
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/self/status

# Với cgroup v2, nếu các file này hiện diện:
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpuset.mems.effective
~~~

Container/Kubernetes có thể nhìn thấy topology host nhưng **được giới hạn CPU và memory nodes** bởi cpuset/cgroup. Do đó, số node toàn host không đồng nghĩa số node mà JVM được cấp phép thực sự sử dụng. Nếu file cpuset không tồn tại, hãy kiểm tra phiên bản cgroup và cấu trúc mount của môi trường, **không mặc định lỗi JVM**.

### 5.3. Không dùng Java API đơn giản để “đếm node”

~~~java
int processors = Runtime.getRuntime().availableProcessors();
System.out.println(processors);
~~~

Đoạn code đặt trong phương thức. `availableProcessors()` cho biết số processor mà JVM thấy có thể sử dụng theo môi trường, **không phải số NUMA nodes**. `Runtime.maxMemory()` cho biết giới hạn heap Java, **không cho biết mỗi NUMA node có bao nhiêu RAM**.

Trong Java SE thông thường không có lời gọi `new Object()` hay `Thread.currentThread()` chuẩn nào tự trả “NUMA node chứa object hoặc thread” để dùng thay công cụ OS/JVM. Muốn đo page placement, dùng công cụ hệ điều hành/JFR/performance tool phù hợp.

## 6. Kiểm tra hỗ trợ G1 NUMA của JVM hiện hành

### 6.1. Xác minh phiên bản, collector và flag thực

~~~bash
java --version

# Xem flag đang được JVM chọn ở lần chạy này:
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version 2>&1 |
  grep -E 'UseG1GC|UseNUMA|UseNUMAInterleaving'

# Thử yêu cầu NUMA awareness và xem giá trị cuối:
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 |
  grep -E 'UseG1GC|UseNUMA|UseNUMAInterleaving'
~~~

Các câu lệnh trên là **Bash/Linux**; trên Windows PowerShell có thể lọc bằng `Select-String` thay `grep`.

**Đọc kết quả thật cẩn thận:**

- `UseG1GC = true` xác nhận collector đã chọn ở lần thử.
- `UseNUMA = true` cho biết JVM thực sự bật flag ở môi trường đó, nhưng muốn đánh giá locality vẫn cần hardware/OS và workload.
- `UseNUMA = false` dù bạn đưa `-XX:+UseNUMA` có thể xảy ra khi JVM xác định nền tảng/topology không đáp ứng. Không có tối ưu NUMA thực thì không có cơ sở tuyên bố benchmark hiệu quả nhờ cờ.
- `UseNUMAInterleaving` là **cờ khác**, liên quan chính sách interleaving, không phải bằng chứng G1 đã đạt local allocation.
- Mặc định của `UseNUMA` **phụ thuộc JDK/collector/platform**; Oracle JDK 25 mô tả rõ “default value depends on the garbage collector”. Không nên dạy một giá trị default cứng cho tất cả các JDK.

**Ví dụ kiểm chứng giới hạn:** trong môi trường Windows/JDK 24 dùng để chạy ví dụ của bài này, JVM **chấp nhận** `-XX:+UseG1GC -XX:+UseNUMA` nhưng `PrintFlagsFinal` vẫn cho `UseNUMA = false`. Điều đó không chứng minh JEP 345 đã vô hiệu ở tất cả JVM hoặc Linux; nó chỉ nhấn mạnh rằng **flag xuất hiện trên command line không đồng nghĩa NUMA thật sự kích hoạt**.

### 6.2. Quan sát log G1/NUMA khi có phần cứng phù hợp

~~~bash
java -Xms128m -Xmx128m -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:gc=info,gc+heap+numa=debug \
  NumaAllocationDemo
~~~

`-Xlog:gc=info,gc+heap+numa=debug` là cấu hình **Unified JVM Logging** được JVM có log tag tương ứng hiểu; `gc+heap+numa` giúp quan sát thống kê G1 theo NUMA khi tính năng đang hoạt động và có dữ liệu cần in.

**Lưu ý:** Không phải JVM sẽ in log NUMA trong mọi lần chạy. Một máy chỉ có một node, platform thiếu hỗ trợ, quá ít GC hoặc đường đi thực thi không có thống kê có thể cho log ngắn hoặc không có dòng NUMA. Không suy ra hiệu năng bằng cách đếm số dòng `numa`. Xem lại version thực bằng `java -Xlog:help` để biết logging tags/levels mà JDK đang hỗ trợ.

Khi đánh giá sản phẩm, nên lưu log riêng từng cấu hình và ghi rõ: JDK distribution/version, host OS, NUMA nodes được phép, CPU affinity, `-Xms/-Xmx`, collector, `UseNUMA` cuối cùng và workload.

## 7. Chương trình Java 17+ minh họa cấp phát bộ nhớ nhiều luồng

Ví dụ dưới đây tạo các worker threads và nhiều mảng byte để thấy cách code Java **tạo workload memory allocation**. Nó không cố thao tác trực tiếp NUMA placement và **không phải benchmark NUMA**. Giá trị lớn nhất của ví dụ là giúp bạn chạy **cùng một chương trình** dưới các cấu hình JVM khác nhau và quan sát flag/GC logs.

**File: `NumaAllocationDemo.java`**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

public class NumaAllocationDemo {
    public static void main(String[] args)
            throws InterruptedException {

        int workers = Math.min(
                4, Runtime.getRuntime().availableProcessors());

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);
        AtomicLong checksum = new AtomicLong();

        for (int i = 0; i < workers; i++) {
            final int workerId = i;

            Thread worker = new Thread(() -> {
                long local = 0;
                try {
                    start.await();

                    for (int round = 0; round < 160; round++) {
                        byte[] bytes = new byte[256 * 1024];

                        // Chạm một byte ở mỗi đoạn 4096 byte,
                        // nhưng không giả định OS page size luôn 4096.
                        for (int pos = 0; pos < bytes.length; pos += 4096) {
                            bytes[pos] = (byte) (workerId + round + 1);
                            local += bytes[pos] & 0xff;
                        }
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    checksum.addAndGet(local);
                    done.countDown();
                }
            }, "allocator-" + i);

            worker.start();
        }

        start.countDown();
        done.await();

        System.out.println("workers=" + workers);
        System.out.println(
                "checksumPositive=" + (checksum.get() > 0));
        System.out.println("finished=true");
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 NumaAllocationDemo.java

java -Xms128m -Xmx128m -XX:+UseG1GC NumaAllocationDemo
~~~

**Ví dụ stdout đã kiểm tra trên Windows/JDK 24:**

~~~text
workers=4
checksumPositive=true
finished=true
~~~

`workers` phụ thuộc số CPU mà JVM nhìn thấy; trên môi trường khác có thể là 1, 2 hoặc 3. Hai dòng boolean còn lại đúng trong lần kiểm thử của ví dụ. **Không in thời gian và không cố định số lần GC**, vì những số ấy phụ thuộc JVM/JIT/OS và scheduling.

### Vì sao ví dụ không chứng minh NUMA?

- Chạy được trên máy **không có nhiều NUMA nodes**, nên chỉ xác nhận Java code và G1 runtime.
- `new byte[...]` không yêu cầu một node cụ thể; OS và G1 quyết định physical placement.
- Dùng 4096 byte làm bước ghi để tạo workload, **không có nghĩa page size của mọi hệ thống bằng 4096**.
- Chương trình sống ngắn, không có workload nghiệp vụ thật; các thread có thể đổi core giữa các vòng.
- Tổng lượng cấp phát tạo GC pressure nhưng chưa đủ để đo remote/local latency hoặc lợi ích của một thay đổi hệ thống.

Vì vậy, nếu mục tiêu là tìm hiểu `-XX:+UseNUMA`, hãy chạy ví dụ trên **Linux NUMA nhiều node có thực** để xem flag/log. Nếu mục tiêu là đánh giá hiệu năng ứng dụng, cần benchmark dài hơn và giữ các yếu tố khác cố định.

## 8. So sánh hai lần chạy trên Linux NUMA nhiều node

Sau khi xác minh phần cứng và biên dịch chương trình ở mục 7, có thể chạy hai cấu hình **chỉ khác `UseNUMA`**:

~~~bash
# Baseline: cùng G1 và heap, tắt nhận thức NUMA.
java -Xms128m -Xmx128m -XX:+UseG1GC -XX:-UseNUMA \
  NumaAllocationDemo

# Thử nghiệm: cùng G1/heap, yêu cầu NUMA awareness.
java -Xms128m -Xmx128m -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:gc=info,gc+heap+numa=debug \
  NumaAllocationDemo
~~~

Đây là ví dụ **kiểm tra khả năng chạy và logs**, không phải phép đo hiệu suất đáng tin. Mục đích:

1. Kiểm tra JVM có chấp nhận flags không.
2. Kiểm tra `UseNUMA` hiệu lực bằng `-XX:+PrintFlagsFinal` hoặc log.
3. Quan sát kết quả ứng dụng có thay đổi đúng hay không.
4. Tách vấn đề API/lifecycle khỏi vấn đề hiệu năng NUMA.

**Không khẳng định:** chạy với `-XX:+UseNUMA` chắc chắn nhanh hơn. Cũng không lấy thời gian một lần chạy làm kết quả benchmark, vì GC warm-up, JIT compilation, OS page placement và CPU frequency có thể khiến nhiễu lớn hơn chênh lệch.

### Thiết kế benchmark có ý nghĩa

Khi triển khai một thử nghiệm NUMA thật sự trên hệ thống nhiều socket:

- Chọn **cùng bản JDK/GC và cùng heap size** cho A/B.
- Chạy đủ lâu để JIT ổn định, thực hiện warm-up và đo nhiều lần; randomize thứ tự A/B nếu phù hợp.
- Giữ hoặc ghi lại CPU affinity, mức tải ngoài, container cpuset, memory policy và lượng RAM rảnh từng node.
- Giữ workload thật: allocation rate, số threads, object lifetime, shared working set, request mix.
- Đo **throughput, p50/p95/p99 latency, GC pauses, CPU utilization, page faults và NUMA placement**.
- Phân tích bằng thống kê nhiều lần chạy thay vì chọn một số tốt nhất.
- Nếu flag được yêu cầu nhưng cuối cùng `UseNUMA = false`, không tính lần ấy là thử nghiệm NUMA-aware.
- Báo rõ điều kiện phần cứng; kết quả từ máy một node không suy rộng cho nhiều socket.

### Một phép tối ưu có thể làm hại cấu hình khác

Thay đổi CPU pinning, interleave policy hoặc placement có thể làm giảm remote access ở một phía nhưng tăng pressure, imbalance hoặc memory contention ở phía khác. G1 ưu tiên local khi khả thi, nhưng còn phải giữ heap health và tiến hành GC. Vì thế tối ưu có thể không cải thiện tail latency của một dịch vụ có dữ liệu chia sẻ rất lớn.

## 9. Đọc thống kê NUMA của hệ điều hành

Trên Linux, các công cụ thông dụng:

~~~bash
# Tổng quan các node và khoảng cách:
numactl --hardware

# Thống kê NUMA tổng thể:
numastat

# Với PID Java đang chạy:
numastat -p PID

# Bản đồ phân bố trang bộ nhớ theo node (khi có quyền đọc):
cat /proc/PID/numa_maps
~~~

`PID` là ký hiệu cần **thay bằng process ID thật**; đây là các lệnh minh họa, không sao chép nguyên “PID” rồi đòi kết quả. `numactl`/`numastat` có thể không được cài sẵn; `/proc/PID/numa_maps` phụ thuộc Linux, kernel và quyền. Các counters của `numastat` thể hiện bố trí trang, hits/misses và những thống kê kernel hỗ trợ, **không tự là thời gian latency của từng Java object**.

Nếu theo dõi process sau khi chạy ví dụ ngắn, process có thể đã kết thúc trước khi gọi `numastat -p`. Với ứng dụng thật, dùng một process chạy đủ lâu và dùng đúng PID.

### CPU binding và memory binding có liên quan, nhưng cần thận trọng

`numactl` hỗ trợ các chính sách như:

- `--cpunodebind=<nodes>`: giới hạn CPU node mà process chạy.
- `--membind=<nodes>`: giới hạn nơi OS cấp phát bộ nhớ.
- `--interleave=<nodes>`: yêu cầu xen kẽ trang trên các node theo chính sách OS.

**Không khuyến nghị bật đồng thời tất cả**. Khi bị bind về một node duy nhất, việc đo lợi ích tối ưu qua nhiều node trở nên không còn tương đương baseline; một số đường đi G1 NUMA có thể được JVM vô hiệu vì không có nhiều node được phép. Interleaving cố ý làm việc khác chiến lược ưu tiên local, nên có thể **triệt tiêu hoặc che khuất** lợi ích cần kiểm thử. Sử dụng chỉ khi bạn hiểu rõ mục tiêu thí nghiệm và ảnh hưởng đến memory pressure.

Trong môi trường Kubernetes, các CPU Manager/Topology Manager/cpuset có thể ảnh hưởng khả năng sắp đặt. Hãy xác minh cấu hình node affinity/memory restrictions thay vì chỉ nhìn số node của host.

## 10. Những điều G1 NUMA-aware không bảo đảm

| Hiểu lầm | Thực tế |
| --- | --- |
| “Bật `-XX:+UseNUMA` là mọi object được đưa lên RAM local.” | Chính sách ưu tiên, có fallback, GC relocation, OS page placement và data sharing. |
| “NUMA node chính là CPU core.” | Một node có thể chứa nhiều cores, đôi khi không trùng ranh giới socket. |
| “Remote memory không thể truy cập.” | Truy cập được, nhưng có thể đắt hơn local. |
| “`availableProcessors()` cho biết số NUMA nodes.” | Nó báo số processor JVM nhìn thấy, không phải topology NUMA. |
| “G1 chỉ dùng một vùng heap liên tục.” | Heap là vùng địa chỉ ảo chia thành **G1 regions**; physical pages có thể phân bố nhiều node. |
| “JEP 345 bảo đảm toàn bộ heap được NUMA optimized.” | Mục tiêu cải tiến ban đầu là **Eden/young allocation**; không đảm bảo mọi thế hệ/đối tượng. |
| “Nếu `java -version` chạy được thì G1 NUMA đang bật.” | Phải xác minh collector, `UseNUMA` hiệu lực và topology. |
| “Java 17 bắt buộc `-XX:+UseNUMA` ở mọi server.” | Tùy hardware/OS/collector/workload; có thể vô hiệu hoặc không có lợi. |
| “Một node hay container chỉ thấy một node vẫn tăng tốc nhờ NUMA.” | Không có nhiều miền local/remote để cải thiện tương quan; cần đo thực. |
| “Dùng `numactl --interleave=all` chắc chắn giúp G1.” | Interleave là chính sách OS khác, có thể xung đột mục tiêu locality. |
| “NUMA giải quyết pause do GC.” | NUMA chỉ là một lớp chi phí; pause còn phụ thuộc live set, allocation, GC algorithm, CPU, pressure. |
| “Thời gian chạy một vòng lặp nhỏ đủ đánh giá lợi ích.” | Microbenchmark ngắn đầy nhiễu; cần workload và đo lường có kiểm soát. |
| “NUMA thay đổi thứ tự Java memory operations.” | Không thay thế hoặc thay đổi quy tắc đồng bộ của Java Memory Model. |
| “Log `numa` hiện một dòng là chứng minh cải thiện latency.” | Log chỉ cho thấy quan sát/trạng thái; kết quả phải dựa trên hiệu năng và workload. |

## 11. Checklist vận hành trước khi bật NUMA cho G1

- [ ] Server có nhiều NUMA nodes mà JVM thực sự **được phép** sử dụng.
- [ ] Biết OS, CPU sockets, architecture và topology từ `lscpu`/`numactl`.
- [ ] Xác nhận `java --version` và collector thật, không giả định G1 nếu đã cấu hình collector khác.
- [ ] Kiểm tra `-XX:+UseNUMA` có được JVM hỗ trợ, flag thực hiệu lực qua `PrintFlagsFinal`.
- [ ] Không xem Windows, máy một node hoặc container giới hạn một node là môi trường chứng minh lợi ích G1 NUMA.
- [ ] Đã xác định CPU affinity, memory policy, cgroups/cpuset, page placement và RAM pressure.
- [ ] Dùng workload đại diện, giữ heap, GC, JDK, threads và điều kiện tải tương đương.
- [ ] Thu thập GC logs và OS-level NUMA statistics khi cần; không chỉ đo wall-clock một lần.
- [ ] Đo throughput, p95/p99 latency, GC pause và resource usage qua nhiều lượt.
- [ ] Cân nhắc tác động của GC relocation, shared objects và thread migration.
- [ ] Không tự ràng buộc mọi process về một node rồi kỳ vọng tận dụng toàn bộ hệ thống nhiều node.
- [ ] Có kế hoạch rollback cấu hình khi kết quả thực tế không cải thiện hoặc tăng tail latency.
- [ ] Ghi lại JDK, OS, topology, JVM flags, container limits và kết quả thử nghiệm.

## 12. Bài tập tự luyện

1. Vẽ sơ đồ hai NUMA nodes, mỗi node có 4 CPU cores và RAM local. Cho một thread chạy trên node 0 truy cập trang ở node 1: đây là local hay remote? Nếu thread chuyển sang node 1, phân loại truy cập thay đổi thế nào?
2. Trình bày vì sao **“2 sockets” không nhất thiết đồng nghĩa “2 NUMA nodes”**. Lệnh Linux nào cho biết node và CPU?
3. Giải thích sự khác biệt giữa `-Xmx` và vị trí trang vật lý thực tế. Khi nào `first touch` có thể ảnh hưởng placement?
4. Nêu lý do JVM không thể cam kết mọi object G1 luôn nằm gần thread cấp phát: GC copying, sharing, thread migration và fallback.
5. Chạy `NumaAllocationDemo.java` với `javac --release 17`, ghi stdout và các thông tin JVM. Vì sao giá trị `workers` thay đổi theo môi trường?
6. Trên Linux NUMA thực, so sánh `java -XX:+UseG1GC -XX:-UseNUMA ...` với `-XX:+UseNUMA`. Xác nhận **giá trị flag cuối cùng** trước khi diễn giải phép đo.
7. Dùng `numactl --hardware` để đọc distance matrix; giải thích vì sao con số 21 không có nghĩa 21 ns.
8. Với JVM nằm trong container, kiểm tra `/proc/self/status` và cpuset restrictions. Tại sao topology của host không đủ?
9. Một ứng dụng có p99 latency cao khi remote memory traffic tăng. Hãy thiết kế A/B test giữ JDK/heap/workload/CPU restrictions ổn định và theo dõi những metrics cần thiết.
10. Giả sử bật `-XX:+UseNUMA` nhưng `PrintFlagsFinal` báo `UseNUMA=false`. Nêu ít nhất ba điều cần kiểm tra trước khi nói JVM “đã tối ưu NUMA”: OS support, số allowed nodes, GC/JDK version.
11. Phân biệt lý do dùng G1 GC với lý do tối ưu NUMA: mục tiêu pause-time và reclaim khác với locality của memory pages.
12. Một nhóm muốn ép toàn bộ memory về node 0 bằng `--membind=0` rồi so sánh G1 NUMA nhiều node. Hãy phân tích vì sao thay đổi này khiến kết quả khó quy về riêng G1.

## 13. Tài liệu chuẩn, còn áp dụng

- [OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): cải tiến NUMA-aware của G1 được đưa vào JDK 14, cơ chế ưu tiên các vùng cấp phát trên node phù hợp.
- [Oracle Java SE 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): region-based heap layout, Eden/Survivor/Old, collection và copy objects.
- [Oracle Java SE 25 — Garbage-First GC Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): cân bằng latency/throughput, tuning G1 và GC logging.
- [Oracle Java SE 25 — java launcher và `-XX:+UseNUMA`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): định nghĩa flag NUMA và default phụ thuộc collector.
- [OpenJDK HotSpot engineer — NUMA-Aware Memory Allocation for G1 GC](https://sangheon.github.io/2020/11/03/g1-numa.html): giải thích kiến trúc, phạm vi young generation, log tags và điều kiện hiệu năng; đọc như tài liệu giải thích triển khai, không thay thế phiên bản JDK đang chạy.
- [Linux manual — numactl(8)](https://man7.org/linux/man-pages/man8/numactl.8.html): topology, `--hardware` và các chính sách CPU/memory binding/interleaving.
- [Linux manual — numastat(8)](https://man7.org/linux/man-pages/man8/numastat.8.html): thống kê cấp phát bộ nhớ NUMA ở cấp hệ thống và process.

**Ghi nhớ:** NUMA có nghĩa **chi phí truy cập RAM không đồng đều giữa các CPU nodes**. G1 có thể tận dụng topology để **ưu tiên vùng Eden gần thread cấp phát** khi JVM và hệ điều hành hỗ trợ. Tối ưu này **best-effort**, không bảo đảm mọi object local hay mọi ứng dụng nhanh hơn. Muốn áp dụng thực tế, phải **xác minh nhiều NUMA nodes, flag `UseNUMA` hiệu lực, CPU/memory policy và workload**, rồi **đo A/B trên đúng máy đích**.