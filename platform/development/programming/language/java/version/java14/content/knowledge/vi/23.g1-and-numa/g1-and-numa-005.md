# G1 và NUMA: điều kiện hệ điều hành, phần cứng và cấu hình JVM

## 1. Khi nào G1 có thể hưởng lợi từ NUMA?

**NUMA** (*Non-Uniform Memory Access*) là kiến trúc bộ nhớ trong đó thời gian truy cập RAM có thể khác nhau tùy vị trí CPU đang chạy và nơi đặt trang bộ nhớ. Thông thường một CPU truy cập **bộ nhớ cục bộ** (*local memory*) của NUMA node đang dùng nhanh hơn truy cập **bộ nhớ ở node khác** (*remote memory*).

G1 (Garbage-First Garbage Collector) quản lý Java heap theo các **heap region**. Từ JDK 14, JEP 345 bổ sung cơ chế **NUMA-aware memory allocation for G1** nhằm tăng khả năng đặt bộ nhớ cấp phát gần những CPU/thread sẽ dùng nó, đặc biệt cho **Eden và Survivor**. Tính năng này vẫn có ý nghĩa trên các JDK HotSpot hiện đại, nhưng nó **không tự động đem lại lợi ích trên mọi máy**.

Một phép đo G1 + NUMA chỉ đáng xem xét khi đồng thời có những điều kiện:

1. **OS/JVM thực sự hỗ trợ đường triển khai NUMA-aware G1**. Phần triển khai được giới thiệu qua JEP 345 hướng tới **Linux**; không suy luận Windows/macOS cũng kích hoạt chỉ vì flag `-XX:+UseNUMA` được parser chấp nhận.
2. **Máy có nhiều NUMA node khả dụng** và độ trễ truy cập local/remote có chênh lệch. Một máy nhiều core nhưng chỉ có **một node khả dụng** không phải trường hợp thực nghiệm NUMA có ý nghĩa.
3. **Các CPU và memory node phù hợp được phép sử dụng** bởi tiến trình Java. Container, CPU affinity, cgroup/cpuset, VM hoặc lệnh `numactl` có thể làm JVM chỉ nhìn thấy một phần topology.
4. **JVM đang dùng G1** và cơ chế NUMA thực sự được bật, không chỉ có một chuỗi tham số trong script khởi động.
5. **Workload đủ lớn và nhạy cảm với locality của bộ nhớ**. Với heap nhỏ hoặc các thread hầu như không truy cập remote memory, việc bật NUMA có thể không tạo khác biệt đo được.

**Mục tiêu của bài:** xác định đúng **điều kiện hệ điều hành, phần cứng và cấu hình JVM**, biết cách kiểm tra chúng và tránh kết luận “NUMA đã hoạt động” hoặc “NUMA chắc chắn tăng tốc” khi chưa có bằng chứng.

> **Phiên bản:** JEP 345 được đưa vào Java 14 và là thay đổi trong HotSpot/G1, không phải cú pháp Java mới. Các ví dụ ứng dụng bên dưới biên dịch bằng Java 17+, dùng flag và logging đang áp dụng trên các JDK hiện hành. Không dùng flag GC logging legacy hoặc các collector đã bị loại bỏ.

## 2. Hiểu topology: socket, CPU, NUMA node và bộ nhớ

Một sơ đồ đơn giản:

```text
                NUMA node 0                 NUMA node 1
          +----------------------+    +----------------------+
          | CPU / CPU cores      |    | CPU / CPU cores      |
          | RAM cục bộ node 0    |    | RAM cục bộ node 1    |
          +-----------+----------+    +-----------+----------+
                      \                    /
                       \--- interconnect --/

Thread chạy ở node 0:
  đọc RAM node 0  -> local access (thường nhanh hơn)
  đọc RAM node 1  -> remote access (thường tốn độ trễ hơn)
```

Đây là **mô hình** chứ không phải mô tả bắt buộc của mọi server:

- Một server hai socket **thường** có nhiều node, nhưng socket và node **không phải khái niệm đồng nhất**: firmware, kiến trúc CPU và chế độ phân vùng NUMA có thể làm một socket gồm nhiều node hoặc gộp cách trình bày node.
- Một server 32/64 core **không đồng nghĩa** có 2/4 NUMA node. `Runtime.availableProcessors()` chỉ cho biết số CPU logic mà JVM nhìn thấy theo môi trường runtime; nó không phải API xác định topology NUMA.
- Máy ảo có thể chỉ cung cấp **một node ảo** ngay cả khi máy chủ vật lý có nhiều socket.
- Một container có thể chạy trên host đa NUMA nhưng bị giới hạn `cpuset.mems` hoặc CPU affinity, khiến các node hữu ích không đồng thời khả dụng.
- Hệ điều hành có quyền quản lý trang bộ nhớ; chính sách locality là nỗ lực tối ưu, **không phải bảo đảm mọi trang luôn nằm ở node mong muốn**.

### Lợi ích được kỳ vọng ở đâu?

Khi G1 cấp phát object, giảm truy cập remote memory có thể giúp **memory access latency**, băng thông hữu ích hoặc throughput. Trong quá trình xử lý các region còn sống của young generation, bố trí vùng nhớ phù hợp cũng có thể hỗ trợ locality của GC work.

Nhưng lợi ích phụ thuộc tỉ lệ truy cập local/remote, độ lớn heap, số node, hoạt động thread, lịch chạy CPU, collector/runtime và chính sách OS. Nếu vấn đề chính là truy vấn database chậm, network latency hoặc lock contention, bật NUMA cho G1 có thể **không giải quyết nguyên nhân gốc**.

## 3. Điều kiện hệ điều hành: tập trung vào Linux cho cơ chế JEP 345

### 3.1. Vì sao phải kiểm tra OS và implementation?

NUMA-aware G1 được JEP 345 đưa vào HotSpot với hỗ trợ Linux. Tài liệu triển khai mô tả việc sử dụng khả năng NUMA của Linux để lựa chọn nơi cấp phát theo những node đang hoạt động. Do đó:

- **Linux + HotSpot/JDK tương thích + NUMA topology thật** là môi trường thích hợp để kiểm thử tính năng này.
- **Windows/macOS:** không được mặc định coi cơ chế G1 NUMA-aware từ JEP 345 sẽ hoạt động giống Linux. JVM có thể hiểu `-XX:+UseNUMA` nhưng **tự tắt hiệu lực** theo nền tảng/GC/topology.
- **JVM vendor hoặc bản build khác:** có thể có chi tiết triển khai riêng. Kiểm tra tài liệu đúng **JDK/JVM đang chạy**, log JVM và các flag hiệu lực, không chỉ dựa vào lời mô tả tổng quát của Java.

**Ví dụ đã kiểm chứng trên Windows với OpenJDK 24:** chương trình chạy được khi truyền `-XX:+UseG1GC -XX:+UseNUMA`, nhưng log khởi động báo:

```text
NUMA Support: Disabled
```

Và `-XX:+PrintFlagsFinal` cho thấy `UseG1GC = true` nhưng **`UseNUMA = false`**. Đây là bằng chứng cụ thể rằng **một flag được truyền không đồng nghĩa cơ chế đã kích hoạt**.

**Giới hạn phép kiểm thử:** ví dụ Windows ở bài này xác minh parser, flag hiệu lực và ứng dụng chạy; **không** xác minh G1 NUMA-aware trên một server Linux nhiều node. Đó là bài test cần làm tại môi trường Linux đích.

### 3.2. Các điều kiện hệ điều hành ở Linux

Để thử trên Linux, cần xác nhận:

| Điều kiện | Vì sao quan trọng | Cách kiểm tra |
| --- | --- | --- |
| OS thấy các NUMA node | JVM không thể chọn nhiều node nếu OS chỉ công bố một node | `numactl --hardware`, `lscpu`, `/sys/devices/system/node/online` |
| CPU và RAM thực sự gắn với các node | Phải có locality để khai thác | Danh sách CPU/node, memory size/node và node distances |
| Tiến trình được phép dùng các node | `cpuset`/affinity có thể thu hẹp node hoạt động | `/proc/PID/status`, cgroup, `numactl --show` |
| Hỗ trợ NUMA của hệ thống khả dụng | HotSpot trên Linux sử dụng API NUMA của OS và thư viện liên quan | Kiểm tra runtime/`libnuma` nếu cần, cùng log JVM |
| RAM khả dụng đủ | Khi node thiếu RAM, OS có thể phải dùng node khác hoặc từ chối allocation theo policy | `numactl --hardware`, `numastat`, OS metrics |
| Workload có tính đại diện | Một phép thử nhỏ không chứng minh lợi ích trên server lớn | Benchmark cùng tải/cấu hình và lặp lại |

Không bắt buộc mọi bản Linux phải cài lệnh `numactl` để ứng dụng Java chạy, nhưng đây là công cụ hữu ích để **quan sát topology và memory policy**. Một số hệ thống cần cài package `numactl` riêng cho các lệnh kiểm tra. Thư viện `libnuma` và khả năng JVM thực sự dùng NUMA cũng cần được xác minh theo bản phân phối.

## 4. Kiểm tra phần cứng NUMA trên Linux trước khi bật flag

Các lệnh Linux dưới đây là **các bước thực hiện trên host/VM Linux đích**, không phải kết quả đo từ máy Windows:

```bash
# Thông tin CPU và NUMA nodes:
lscpu
lscpu -e=CPU,NODE

# Danh sách node, CPU và RAM/node, khoảng cách giữa các node:
numactl --hardware

# Những node mà Linux đang công bố:
cat /sys/devices/system/node/online

# Chính sách memory affinity của shell hiện tại:
numactl --show
```

Với `numactl --hardware`, quan sát **node available**, **node size**, **node free** và **node distances**. Nếu chỉ có node 0 thì thử nghiệm lợi ích giữa nhiều node thường không có ý nghĩa. Nếu khoảng cách từ node 0 đến node 1 lớn hơn truy cập nội bộ node 0, đó là tín hiệu có khác biệt locality cần xem xét.

**Không có một bộ số cố định cho mọi máy.** Node IDs có thể không liên tục; số CPU, dung lượng RAM và distances phụ thuộc thiết bị và OS. Không tự suy ra “node 1 luôn nhanh/chậm hơn node 0”: local hay remote còn phụ thuộc CPU/thread đang ở node nào.

### Quyền của tiến trình thực tế

Sau khi Java process đã chạy, kiểm tra affinity theo PID của **chính tiến trình Java**:

```bash
PID=12345    # Thay bằng PID Java thực, không dùng 12345 nguyên xi
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/"$PID"/status
numastat -p "$PID"
```

- `Cpus_allowed_list` cho biết tập CPU mà kernel cho tiến trình dùng.
- `Mems_allowed_list` cho biết tập memory node mà tiến trình được phép sử dụng.
- `numastat -p PID` cho phép quan sát phân bố bộ nhớ theo NUMA node ở mức hệ điều hành; **không** thay được phép đo truy cập local/remote hoặc nguyên nhân throughput tăng/giảm.

Ở container/cgroup v2, có thể cần kiểm tra `cpuset.cpus.effective` và `cpuset.mems.effective` trong cgroup tương ứng. Trên cgroup v1 hoặc hệ thống cấu hình khác, vị trí file và cơ chế thể hiện hạn mức có thể khác. Đừng đọc một file cgroup ngẫu nhiên rồi coi là cấu hình của Java process nếu chưa xác định đúng cgroup.

### Các tình huống không có nhiều node hiệu lực

- BIOS/firmware hoặc hypervisor không công bố topology NUMA.
- VM chỉ được gán một virtual NUMA node.
- Container chỉ được cấp CPU hoặc memory từ một node.
- Tiến trình bị `numactl --membind=0` hoặc cpuset giới hạn chỉ dùng bộ nhớ node 0.
- JVM phát hiện điều kiện không đủ và vô hiệu hóa phần tối ưu NUMA.
- Heap quá nhỏ hoặc workload không trải qua các node còn lại.

**Kết luận kỹ thuật:** có **hai socket vật lý** không đủ để tuyên bố JVM đang dùng **hai node NUMA**. Phải kiểm tra cả OS, process affinity và log JVM.

## 5. Điều kiện JVM: G1 và `UseNUMA` là hai việc khác nhau

### 5.1. Chọn collector đúng

`-XX:+UseG1GC` yêu cầu **Garbage-First GC**. G1 là collector mặc định trong nhiều JDK HotSpot hiện hành, nhưng khi benchmark nên bật tường minh để cả hai lần chạy chắc chắn dùng cùng collector.

```bash
java -XX:+UseG1GC -version
```

Có thể xác nhận thêm bằng log:

```bash
java -XX:+UseG1GC -Xlog:gc+init=info -version
```

Khi chạy một ứng dụng lâu dài, dùng JFR/GC logs hoặc `jcmd` để kiểm tra collector và heap thực tế. **Không nhầm** G1 với các collector khác: `UseNUMA` có chính sách/khả năng hỗ trợ tùy GC và JVM; chỉ riêng việc đặt `UseNUMA` không tự đổi collector thành G1.

### 5.2. Yêu cầu tối ưu NUMA

```bash
java -XX:+UseG1GC -XX:+UseNUMA -jar app.jar
```

Đây là **mẫu lệnh**, `app.jar` phải là JAR thực sự tồn tại. Khi truyền `-XX:+UseNUMA`, JVM được yêu cầu sử dụng tối ưu NUMA nếu nền tảng và GC hỗ trợ. Nó **không buộc** Linux đặt mọi Java object vào local memory, **không override** cgroup/OS policy và **không đảm bảo throughput tăng**.

Tài liệu option `UseNUMA` hiện hành nêu giá trị mặc định **phụ thuộc collector**. Vì vậy trong một phép so sánh nghiêm túc, nên đặt **tường minh** `-XX:-UseNUMA` ở baseline và `-XX:+UseNUMA` ở biến thể, rồi kiểm tra **giá trị hiệu lực** và log tại cả hai lần chạy.

### 5.3. Xem flag hiệu lực, không chỉ xem dòng startup command

```bash
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseG1GC|UseNUMA'
```

Phần `{command line}` hoặc tên flag chỉ cho biết nguồn cấu hình; **giá trị Boolean cuối cùng mới quan trọng**. Trên môi trường không hỗ trợ, có trường hợp `UseNUMA` bị đặt lại thành `false`, dù lệnh chứa `+UseNUMA`.

Trong một số bản JVM, hỗ trợ NUMA còn có các điều kiện runtime không phản ánh đầy đủ chỉ bằng một flag. Do đó cần **cả log khởi tạo G1/NUMA**, topology Linux và bằng chứng benchmark.

## 6. Bật logging để chẩn đoán G1/NUMA

HotSpot hiện đại dùng **Unified JVM Logging** với `-Xlog`. Đối với NUMA, `numa` là một tag hữu ích; đối với GC initialization, sử dụng `gc+init`.

Ví dụ:

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
  -Xms4g -Xmx4g \
  -Xlog:gc+init=info,numa*=debug \
  -jar app.jar
```

**Đây là mẫu dành cho một host Linux đủ RAM**, không phải cấu hình nên chép nguyên lên laptop. Các giá trị `-Xms4g` và `-Xmx4g` chỉ minh họa heap cố định 4 GiB; chọn theo yêu cầu ứng dụng và tài nguyên môi trường thật.

Các điểm cần tìm trong log:

- Collector thực tế là **G1**.
- Thông tin **NUMA Support: Enabled/Disabled** hoặc thông báo NUMA tương ứng của JDK đó.
- Số node NUMA JVM thực sự xem là **active** và chính sách phân bổ nếu runtime có ghi.
- Thông tin kích thước G1 region/heap và điều kiện bộ nhớ.
- Các cảnh báo về policy/topology, nếu có.

**Không có một dòng log duy nhất bảo đảm xuất hiện nguyên văn trên mọi JDK.** Trên một JVM không hỗ trợ, log NUMA có thể không xuất hiện; có thông báo bị tắt bởi log level. Kiểm tra cú pháp tag khả dụng bằng:

```bash
java -Xlog:help
```

Trên Linux production có thể ghi log có rotation để không tràn stdout/disk:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms4g -Xmx4g \
  -Xlog:gc*=info,numa*=debug:file=gc-numa.log:uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

Nếu cú pháp option hoặc logging tag khác ở một bản JDK/vendor, xác nhận bằng `java -Xlog:help` và tài liệu của runtime ấy. Không quay lại dùng cách log GC legacy đã được thay bằng Unified Logging trên Java hiện hành.

### `AlwaysPreTouch` và heap cố định

Một số hệ thống chủ động đặt `-Xms` bằng `-Xmx` và dùng `-XX:+AlwaysPreTouch` để chạm các trang heap trong lúc khởi động. Điều này có thể tác động đáng kể tới **thời gian startup, commit memory và chính sách placement của OS**, đặc biệt trên NUMA.

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
  -Xms4g -Xmx4g -XX:+AlwaysPreTouch \
  -jar app.jar
```

Đừng mặc định bật `AlwaysPreTouch` chỉ vì muốn thử NUMA; nó thay đổi thêm một yếu tố của phép đo. Nếu muốn so sánh `UseNUMA` bật/tắt, hãy giữ **giống nhau** mọi tùy chọn khác, kể cả `AlwaysPreTouch`, kích thước heap, large pages và CPU affinity.

## 7. Ví dụ Java 17+ chạy được: xác nhận G1 và thực thi workload nhỏ

Đoạn chương trình sau dùng Java SE để kiểm tra **collector G1 có đang hoạt động không**, số CPU JVM nhìn thấy có hợp lệ không và thử cấp phát vài MiB bộ nhớ. Đây là **smoke test runtime**, không phải một benchmark NUMA.

**Tệp `Main.java`:**

```java
import java.lang.management.ManagementFactory;

public class Main {
    public static void main(String[] args) {
        boolean g1 = ManagementFactory.getGarbageCollectorMXBeans()
                .stream().anyMatch(gc -> gc.getName().startsWith("G1 "));

        byte[][] blocks = new byte[64][];
        long checksum = 0;
        for (int i = 0; i < blocks.length; i++) {
            blocks[i] = new byte[128 * 1024];
            blocks[i][0] = (byte) (i + 1);
            blocks[i][blocks[i].length - 1] = 1;
            checksum += (blocks[i][0] & 0xff)
                    + (blocks[i][blocks[i].length - 1] & 0xff);
        }

        System.out.println("G1_ACTIVE=" + g1);
        System.out.println("CPU_COUNT_POSITIVE="
                + (Runtime.getRuntime().availableProcessors() > 0));
        System.out.println("BLOCKS=" + blocks.length);
        System.out.println("CHECKSUM=" + checksum);
        System.out.println("JAVA_17_PLUS=" +
                (Runtime.version().feature() >= 17));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 Main.java
```

Chạy baseline trên HotSpot:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms128m -Xmx128m Main
```

**Stdout chính xác đã kiểm chứng:**

```text
G1_ACTIVE=true
CPU_COUNT_POSITIVE=true
BLOCKS=64
CHECKSUM=2144
JAVA_17_PLUS=true
```

Kết quả này có ý nghĩa:

- `G1_ACTIVE=true` được suy ra từ tên các GC MXBean bắt đầu bằng `"G1 "`; phù hợp với HotSpot G1 trong lần thử.
- `CPU_COUNT_POSITIVE=true` chỉ nói `availableProcessors() > 0`, **không nói có bao nhiêu NUMA node**.
- `BLOCKS=64` và `CHECKSUM=2144` xác nhận dữ liệu đã được cấp phát và truy cập đúng trong chương trình.
- `JAVA_17_PLUS=true` xác nhận runtime có feature version tối thiểu 17.

**Không có dòng nào chứng minh NUMA-aware placement đang hoạt động.** API `ManagementFactory` chỉ dùng trong ví dụ để xác minh collector và thông tin runtime, không thay cho `numactl`, NUMA telemetry hoặc log JVM.

### Chạy cùng mã với cấu hình `+UseNUMA`

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms128m -Xmx128m \
  -Xlog:gc+init=info,numa*=debug Main
```

Với **OpenJDK 24 trên Windows** của phép kiểm thử, chương trình vẫn in đúng năm dòng ở trên; **log bổ sung** có:

```text
NUMA Support: Disabled
```

Và kiểm tra flag cuối cho thấy `UseNUMA=false`. Như vậy chỉ chứng minh **Windows JVM trong phép thử không kích hoạt hỗ trợ NUMA**, không phải rằng NUMA hoạt động và không phải rằng NUMA luôn chậm/nhanh.

Trên **Linux nhiều node**, cần chạy lệnh và phân tích **log thực tế trên máy đó** để biết `UseNUMA` được dùng hay bị tắt. Không tự sao chép dòng log Windows thành kết quả dự kiến của Linux.

## 8. G1 NUMA-aware xử lý phần nào của heap?

Đây là điểm dễ gây hiểu nhầm: “G1 hỗ trợ NUMA” không có nghĩa **mọi object trong toàn bộ heap đều được ghim vĩnh viễn vào node của thread tạo ra chúng**.

Theo thiết kế ban đầu của JEP 345:

1. G1 chia heap thành nhiều **region**, được cấu hình để có quan hệ với các NUMA node hoạt động.
2. Khi cần cấp phát ở **Eden**, G1 có thể chọn vùng cấp phát phù hợp với NUMA node của thread đang thực thi.
3. Trong quá trình **young GC**, survivor allocations cũng có cơ chế xét tới node phù hợp.
4. **Old generation** trong thiết kế ban đầu không được xử lý theo cùng một chính sách gắn mỗi object với node. Không nên suy ra mọi vùng Old luôn có locality tối ưu.
5. Thực tế trang nhớ do **OS** cấp phát và đặt; khi node thiếu RAM hoặc thread chuyển node, vẫn có thể có truy cập remote hoặc placement khác mong đợi.

G1 có thể di chuyển object khi GC, thread có thể được scheduler chuyển CPU, và dữ liệu có thể được nhiều thread ở các node khác nhau sử dụng. Vì vậy tối ưu NUMA là **cải thiện xác suất locality**, không phải đảm bảo tuyệt đối.

Một máy có **một node**, một heap nhỏ hoặc workload chủ yếu làm việc với dữ liệu nằm ở một node có thể không thấy lợi ích rõ ràng.

## 9. Container, cgroup, CPU affinity và `numactl`

Trên server đa NUMA, cấu hình OS có thể làm hai tiến trình cùng chạy JVM/GC nhưng thấy topology khác nhau.

Ví dụ các cơ chế ảnh hưởng:

- **`taskset` / CPU affinity:** giới hạn tập CPU, làm thread khó phân bố giữa nhiều node.
- **`numactl --cpunodebind`:** chỉ định node CPU cho process.
- **`numactl --membind`:** giới hạn node dùng để cấp phát memory.
- **Cgroup/cpuset trong container:** giới hạn cả CPU lẫn memory node mà process được phép sử dụng.
- **VM vNUMA:** hypervisor quyết định topology được cung cấp cho guest.

Ví dụ lệnh minh họa **chỉ để quan sát**, không tự ý áp dụng trên production:

```bash
numactl --show
numactl --hardware

PID=12345
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/"$PID"/status
numastat -p "$PID"
```

**Không đặt bừa `numactl --membind=0`** rồi kỳ vọng G1 tận dụng hai node: khi bộ nhớ bị giới hạn ở một node, cơ hội tối ưu đa node gần như không còn, và JVM có thể tắt NUMA-aware mode. Tương tự, tự thay đổi `taskset`/cpuset giữa lần baseline và lần thử NUMA làm phép so sánh thiếu công bằng.

**Trong Kubernetes:** hãy xem xét CPU Manager, NUMA-aware/topology-aware placement của container, memory limits/cpuset và chính sách node thực tế. Không coi một pod có “nhiều CPU” là bằng chứng được quyền dùng nhiều NUMA memory nodes. Cần kiểm tra topology bên trong môi trường chứa JVM và đối chiếu với OS host.

## 10. Kiểm thử hiệu năng có đối chứng

Bật `UseNUMA` là **giả thuyết tối ưu**; phải chứng minh bằng phép đo trên workload thật.

### Hai cấu hình chỉ khác nhau ở NUMA

Trên một **host Linux nhiều node** đủ bộ nhớ, có thể thử với cùng heap và cùng ứng dụng:

**A — baseline tắt NUMA:**

```bash
java -XX:+UseG1GC -XX:-UseNUMA \
  -Xms4g -Xmx4g \
  -Xlog:gc*:file=baseline-gc.log:uptime,level,tags \
  -jar app.jar
```

**B — yêu cầu G1 NUMA-aware:**

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
  -Xms4g -Xmx4g \
  -Xlog:gc*=info,numa*=debug:file=numa-gc.log:uptime,level,tags \
  -jar app.jar
```

Đây là **mẫu lệnh để thiết kế phép đo**, chưa phải kết quả thực thi trên Linux. Không dùng kích thước 4 GiB nếu host/cluster không có đủ RAM, và phải kiểm tra `+UseNUMA` thực sự **có hiệu lực** trước khi so sánh.

Giữ nguyên các yếu tố:

- Cùng JDK vendor/version, OS, CPU/NUMA topology và heap parameters.
- Cùng mức tải, request mix, số thread, bộ dữ liệu, cache/warm-up và thời lượng đo.
- Cùng giới hạn container/cgroup, CPU/memory affinity, page size và background load.
- Cùng cài đặt logging/profiling phù hợp; logging chi tiết thêm có thể tạo overhead nên nên tách bước **chẩn đoán kích hoạt** khỏi bước **benchmark hiệu năng**.
- Lặp lại nhiều lượt, kiểm tra biến thiên tự nhiên và tránh quyết định từ một mẫu ngắn.

### Nên đo gì?

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput (requests/s, jobs/s) | Có xử lý được nhiều công việc hơn dưới cùng tải không? |
| Latency p50/p95/p99 | Có cải thiện/tệ đi về thời gian phản hồi, đặc biệt tail latency không? |
| CPU utilization theo node/thread | Có thay đổi cách dùng CPU giữa các node không? |
| GC pause, GC frequency, allocation rate | Có tác động phụ lên collector không? |
| Node-local / remote access nếu có counter | Có thật sự giảm truy cập bộ nhớ ngoài node không? |
| `numastat -p PID`, page faults, memory placement | OS đặt memory trên các node như thế nào? |
| Memory pressure và node free memory | Có mất cân bằng khiến node thiếu RAM không? |

Không biến `numastat` thành thước đo **độ trễ** duy nhất: nó phản ánh phân bố memory/page theo node nhưng không đo trực tiếp request p99. Cũng không coi ít GC hơn tự động là performance tốt hơn nếu throughput hoặc latency ứng dụng xấu đi.

### Khi nào kết quả có thể không cải thiện?

- JVM nhận diện chỉ **một NUMA node**.
- Heap và dữ liệu quá nhỏ so với RAM ở một node.
- Workload CPU-bound, network-bound hoặc lock-bound hơn là memory-bandwidth/latency-bound.
- Thread liên tục di chuyển giữa node, làm giảm locality mong đợi.
- Cgroup/numactl/cpuset vô tình chỉ cho phép dùng một node.
- Cấu hình kích hoạt bị JVM vô hiệu hóa, dù lệnh startup có `-XX:+UseNUMA`.
- Chính sách pre-touch, huge pages, page placement hoặc cache làm kết quả khác dự đoán.

Mục tiêu không phải chứng minh JEP 345 luôn tốt hơn, mà xác định **trên hệ thống cụ thể đang điều tra, trong những điều kiện cụ thể, nó có cải thiện đại lượng mục tiêu hay không**.

## 11. Bảng quyết định: môi trường nào nên thử?

| Môi trường | Hướng xử lý |
| --- | --- |
| Linux, HotSpot tương thích, 2+ node đang hoạt động, heap và tải lớn | Có cơ sở thử G1 `+UseNUMA`, kiểm tra flag/log rồi benchmark A/B |
| Linux nhưng chỉ có 1 active node | Không kỳ vọng lợi ích locality giữa nhiều node; ưu tiên tối ưu khác |
| Linux host 2+ node, container chỉ có 1 memory node | Kiểm tra cgroup/affinity; đừng suy ra từ topology host |
| Windows với JVM trả `NUMA Support: Disabled` | Coi tính năng không hoạt động trong phép thử đó; không kết luận “đã bật” |
| macOS, laptop phổ thông hoặc máy không có topology phù hợp | Kiểm tra hỗ trợ thực tế; đừng mặc định NUMA-aware G1 sẽ có hiệu lực |
| Linux đa node nhưng heap rất nhỏ, tải nhẹ | Có thể thử nếu cần, nhưng chi phí đo có thể lớn hơn lợi ích dự kiến |
| JVM dùng collector khác G1 | Đọc chính sách NUMA của collector đó; không áp dụng trực tiếp hướng dẫn JEP 345 |
| Docker/Kubernetes với CPU/memory placement phức tạp | Xác minh topology **bên trong process** và chính sách node/container trước |

## 12. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Thấy `-XX:+UseNUMA` trong command line rồi kết luận đã bật | JVM có thể tự tắt theo nền tảng/GC/node | Xem `PrintFlagsFinal` và log `gc+init`/`numa` |
| Lấy số core suy ra số NUMA nodes | Core và node không đồng nghĩa | `numactl --hardware`, `lscpu -e` |
| Dùng kết quả Windows để chứng minh G1 NUMA ở Linux | Đường triển khai/platform support khác | Kiểm thử trên Linux đích |
| Chỉ xem topology vật lý, bỏ qua container | Cgroup có thể giới hạn node | Xem memory/CPU affinity của Java process |
| Cố ép memory vào node 0 rồi bật `UseNUMA` | Mất cơ hội cấp phát đa node | Kiểm tra `numactl`/cpuset policy |
| Dùng heap toy 128 MiB làm performance benchmark | Workload quá nhỏ để quan sát NUMA | Dùng workload/heap đại diện, có tải thực |
| So sánh hai lần chạy khác `Xmx` hoặc CPU affinity | Nhiều biến thay đổi cùng lúc | A/B giữ nguyên các yếu tố khác |
| Bật `AlwaysPreTouch` chỉ trong lần NUMA | Thay đổi startup/placement và overhead | Giữ cấu hình giống nhau hoặc tách phép đo |
| Nghĩ G1 NUMA ghim mọi object vào node | G1/OS/thread scheduling không đảm bảo tuyệt đối | Đo locality thực tế, hiểu phạm vi Eden/Survivor |
| Kết luận nhanh từ một benchmark | Nhiễu, warm-up, OS pressure | Lặp lại, xem phân bố latency/throughput |
| Dùng flag GC logging cũ không phù hợp | Thiếu log hiện đại hoặc bị bỏ/obsolete | Dùng `-Xlog` và `java -Xlog:help` |
| Chỉ tối ưu JVM dù vấn đề do I/O hoặc lock | Chọn sai nguyên nhân | Xác định bottleneck bằng GC log/JFR/OS metrics |

## 13. Checklist trước khi triển khai

1. **OS:** bản JVM thực tế có hỗ trợ NUMA-aware G1 trên OS này không?
2. **JDK:** đang chạy JDK/vendor/version nào? G1 có thật sự được chọn?
3. **Phần cứng:** có **nhiều active NUMA nodes** với RAM và CPU phù hợp không?
4. **Quyền truy cập:** tiến trình có được dùng các CPU và memory nodes đó không?
5. **Cấu hình:** `-XX:+UseNUMA` được yêu cầu và **có hiệu lực** hay JVM đã tắt?
6. **Logging:** đã quan sát GC/NUMA initialization và node policy bằng `-Xlog` chưa?
7. **Workload:** heap/tải/latency mục tiêu có đủ đại diện để quan sát locality?
8. **Đối chứng:** đã chạy `-XX:-UseNUMA` với cùng điều kiện làm baseline chưa?
9. **Kết quả:** throughput, p95/p99, GC pause, memory locality có cải thiện rõ, lặp lại được không?
10. **Vận hành:** container placement, affinity, memory limits và startup policy có giữ nguyên khi deploy không?

**Ghi nhớ:** G1 NUMA-aware **không phải chỉ là một flag**. Kết quả thực tế cần **OS/JVM hỗ trợ + nhiều NUMA node hữu ích + tiến trình được phép dùng chúng + G1 + `UseNUMA` có hiệu lực + workload đủ phù hợp**. Tính năng từ Java 14 vẫn liên quan tới hệ thống hiện đại, nhưng chỉ nên giữ trong cấu hình khi phép đo trên **máy và tải thật** chứng minh nó mang lại lợi ích.

### Tài liệu tham khảo

- [JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345) — mục tiêu và phạm vi thay đổi từ Java 14.
- [Oracle JDK 25 — Java Command / `-XX:+UseNUMA` và `-Xlog`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — các tùy chọn hiện hành và logging.
- [Oracle JDK 25 — Garbage-First GC Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html) — phương pháp tuning G1 và lưu ý heap.
- [OpenJDK G1 NUMA implementation notes — Sangheon Kim](https://sangheon.github.io/2020/11/03/g1-numa.html) — NUMA node, young regions và logging trong thiết kế JEP 345.
- [Linux numactl project](https://github.com/numactl/numactl) — công cụ kiểm tra topology và policy của Linux.
