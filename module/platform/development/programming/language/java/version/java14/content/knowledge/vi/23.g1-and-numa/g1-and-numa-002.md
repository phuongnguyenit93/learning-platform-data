# Nút NUMA và chi phí truy cập bộ nhớ gần hoặc xa trong G1 GC

## 1. Vì sao cùng một lệnh đọc RAM lại có thể tốn thời gian khác nhau?

Trên máy có **Non-Uniform Memory Access (NUMA)**, thời gian CPU truy cập RAM phụ thuộc vào **CPU nào thực hiện truy cập** và **trang bộ nhớ vật lý đang nằm ở NUMA node nào**. Không phải toàn bộ bộ nhớ chính đều cách mọi CPU một khoảng tương đương.

Một **NUMA node** thường là nhóm tài nguyên xử lý và bộ nhớ có quan hệ gần về phần cứng. Máy nhiều socket CPU là ví dụ dễ hiểu, nhưng **không nên đồng nhất tuyệt đối một NUMA node với một CPU socket**: cách firmware, hệ điều hành và phần cứng chia topology có thể tạo nhiều node trong một socket hoặc các node với đặc tính khác nhau.

- **Local memory access (truy cập bộ nhớ gần):** luồng đang chạy trên CPU thuộc một node và đọc/ghi trang RAM nằm tại node gần CPU đó.
- **Remote memory access (truy cập bộ nhớ xa):** CPU của node này đọc/ghi RAM được đặt tại một node khác, phải đi qua đường kết nối/cache-coherency và các tài nguyên hệ thống tương ứng.
- **NUMA locality:** mức độ công việc có thể truy cập dữ liệu trên node gần CPU đang chạy.
- **NUMA distance:** chỉ số thể hiện quan hệ khoảng cách/chi phí tương đối giữa các node, chẳng hạn hệ điều hành Linux công bố qua `/sys/devices/system/node/nodeX/distance`. Đây **không phải số nanosecond tuyệt đối**.

Thông thường, việc truy cập RAM *remote* có độ trễ lớn hơn và có thể bị giới hạn băng thông hơn so với *local*. Tuy nhiên khác biệt thực tế còn phụ thuộc kiến trúc máy, cache hit/miss, bộ điều khiển nhớ, liên kết giữa các node, cạnh tranh tải và chính sách hệ điều hành. Không có một tỷ lệ “remote luôn chậm hơn đúng 2 lần” áp dụng cho mọi máy.

**Liên hệ Java:** G1 Garbage Collector đã có tối ưu cấp phát bộ nhớ nhận biết NUMA từ JDK 14 (JEP 345). Các bản JDK hiện đại vẫn có option HotSpot `-XX:+UseNUMA`, nhưng **có NUMA-aware allocator không đồng nghĩa JVM bảo đảm mọi object luôn nằm gần thread truy cập**.

## 2. Mô hình hai NUMA node: “gần” và “xa” là khái niệm tương đối

Hình dung một hệ thống có hai node:

~~~text
        NUMA NODE 0                      NUMA NODE 1
  +----------------------+        +----------------------+
  | CPUs: 0,1,2,3        |        | CPUs: 4,5,6,7        |
  | Memory: RAM node 0   |        | Memory: RAM node 1   |
  +----------------------+        +----------------------+
        |    local                        |    local
        |                                 |
        +====== interconnect =============+
                 cross-node traffic
~~~

Giả sử thread đang chạy trên **CPU thuộc node 0**:

- Đọc trang bộ nhớ ở **node 0** là truy cập **local**.
- Đọc trang bộ nhớ ở **node 1** là truy cập **remote**.

Nếu hệ điều hành sau đó chuyển thread sang **CPU thuộc node 1**, trong khi dữ liệu vẫn ở node 0, **cùng vùng dữ liệu** trước đó là local giờ có thể trở thành remote. Vậy “gần” không phải nhãn bất biến của một Java object; nó phụ thuộc **cặp CPU thực thi ↔ trang bộ nhớ** tại thời điểm truy cập.

Ví dụ một ma trận khoảng cách **giả định để minh họa**, không phải số đo phần cứng:

| CPU đang ở node | RAM node 0 | RAM node 1 |
| --- | ---: | ---: |
| **Node 0** | 10 (local) | 20 (remote) |
| **Node 1** | 20 (remote) | 10 (local) |

Trong bảng này, `10` và `20` là **đơn vị khoảng cách tương đối**. Không được kết luận 10 ns và 20 ns hoặc kết luận máy thực tế có đúng tỷ lệ độ trễ 1:2. Trên Linux, bảng `distance` có thể giống dạng này, nhưng các giá trị phụ thuộc topology.

### Tại sao remote thường đắt hơn?

Một lần truy cập DRAM có thể đi qua bộ nhớ đệm CPU, bộ điều khiển bộ nhớ và mạng kết nối giữa các node. Nếu dữ liệu ở node khác, đường đi có thể dài hơn, tạo thêm chi phí truyền và đồng bộ cache. Trong trường hợp nhiều thread đồng thời dùng remote memory, **băng thông liên kết** còn có thể trở thành nút thắt, kể cả khi độ trễ một lần đọc không đổi nhiều.

Phải phân biệt:

1. **Cache hit:** đọc dữ liệu đã có trong cache gần CPU; phép đọc có thể chưa cần tới RAM nên rất khó dùng nó để ước lượng NUMA DRAM latency.
2. **DRAM local:** không tìm thấy dữ liệu trong cache và phải tới RAM gần CPU.
3. **DRAM remote:** cần truy cập RAM nằm ở node khác; liên kết liên node có thể tăng độ trễ và giảm throughput.
4. **Tác động của tải:** cùng một topology nhưng số thread chạy, hoạt động memory controller, cấu hình bộ nhớ và áp lực hệ thống khác sẽ cho số liệu khác.

Vì vậy một benchmark Java đọc mảng vài KB có thể chỉ phản ánh **CPU cache**, không phải chi phí local/remote DRAM.

## 3. Cơ chế NUMA ảnh hưởng đến ứng dụng Java thế nào?

Một ứng dụng có thể tạo object trên một thread nhưng object đó lại được nhiều thread khác đọc. Đường đi thường gồm:

~~~text
Java thread chạy trên CPU node A
        |
        v
Yêu cầu JVM cấp phát object
        |
        v
JVM / collector quyết định vùng heap phù hợp
        |
        v
Hệ điều hành ánh xạ các trang bộ nhớ vật lý
        |
        v
Thread truy cập object (có thể đang ở node A hoặc B)
        |
        v
Local hoặc remote theo CPU node và RAM node thực tế
~~~

Có ít nhất **ba quyết định độc lập**:

- **Đặt thread chạy ở CPU nào:** Linux scheduler, CPU affinity, cpuset/cgroup hoặc cấu hình container có thể làm thread thay đổi vị trí.
- **Đặt trang bộ nhớ vào NUMA node nào:** chính sách memory allocation, lần first-touch, OS page placement/migration và các yêu cầu phân bố bộ nhớ của JVM.
- **Object tồn tại ở đâu trong Java heap:** collector quản lý heap regions, có thể cấp phát và sao chép object qua các đợt garbage collection.

Lưu ý **Java object không trực tiếp tự chứa một “NUMA node ID” trong API Java SE**. Dữ liệu vật lý nằm theo **memory pages** của hệ điều hành, trong khi G1 quản lý **heap regions** ở mức JVM. Một region có thể gồm nhiều trang OS; số lượng và kích thước từng lớp không nhất thiết trùng nhau.

Hệ quả: một thread từng cấp phát object ở node gần **không bảo đảm** object luôn gần thread đó. Thread có thể di chuyển, object có thể được GC di chuyển, một vùng có thể được nhiều thread khác nhau truy cập, hoặc OS không thực hiện chính xác mọi yêu cầu ưu tiên placement.

## 4. G1 GC và NUMA: JEP 345 giải quyết việc gì?

**Garbage-First (G1)** là một collector được thiết kế cho môi trường nhiều CPU, heap lớn và mục tiêu cân bằng throughput với GC pause time. G1 chia heap thành nhiều **regions** có kích thước tương đương, chứa các vùng eden, survivor, old và những vùng dành cho humongous objects.

Trong bối cảnh NUMA, vấn đề là:

- Một thread ở node A có thể thường xuyên cấp phát object mới.
- Nếu bộ nhớ của object được cấp phát chủ yếu trên RAM node B, luồng làm việc sẽ phải đọc/ghi **remote memory** khi heap data không còn nằm trong cache.
- Khi young GC sao chép các object sống sót, nếu bản copy bị đặt sang node khác, locality vốn có thể lại giảm.
- Tăng remote traffic có thể ảnh hưởng throughput và độ trễ, đặc biệt ở máy nhiều node và workload cần nhiều RAM.

**JEP 345: NUMA-Aware Memory Allocation for G1** (được đưa vào **JDK 14**) cải thiện việc cấp phát nhận biết NUMA của G1. Oracle JDK 14 Release Notes mô tả G1 cố **cấp phát và giữ các object ở cùng NUMA node trong young generation qua các lần GC** khi tính năng phù hợp được bật.

Một cách hiểu mức cao của chiến lược này:

1. JVM/collector nhận biết những NUMA nodes sẵn có với tiến trình.
2. G1 cố ưu tiên sử dụng heap regions thuộc node gần thread cấp phát.
3. Khi sao chép object còn sống trong **young collection**, GC cố giữ locality hữu ích thay vì phân phối hoàn toàn mù với node.
4. Hệ thống vẫn cần chia bộ nhớ và đáp ứng nhu cầu của các object có tuổi thọ dài, humongous objects, các thread khác nhau và áp lực heap.

**Phân biệt kiến thức khái niệm hiện hành với chi tiết lịch sử:** tài liệu JDK 14 mô tả bản đầu của JEP 345 cố phân bố **Old/Humongous regions** giữa các node bằng interleaving, còn placement từ young sang old chưa bảo đảm locality tương đương. Đây là **phạm vi của cơ chế khi JEP ra đời**, không phải một cam kết bất biến rằng mọi bản G1 mới về sau chỉ có chính xác các heuristic đó. Với bản JDK đang vận hành, hãy dựa vào release notes và logging của chính bản đó.

Tối ưu của G1 mang tính **best effort**. Nó không phải một hệ thống cam kết “100% object đọc trên local RAM”, và không loại bỏ nhu cầu xem xét thread scheduling, container placement, OS memory policy hoặc hành vi ứng dụng.

## 5. Chi phí NUMA được biểu diễn và hiểu như thế nào?

Có hai cách mô tả **khác nhau**:

### 5.1. Khoảng cách NUMA tương đối

Linux có thể cung cấp `/sys/devices/system/node/node0/distance` và dữ liệu topology qua `numactl --hardware`. Các số như `10 20` thường là **distance/relative cost**.

Chúng cho biết điều gì đó về mối quan hệ gần/xa trong topology **theo cách OS công bố**, nhưng **không phải** thời gian đọc DRAM bằng nanosecond. Đọc distance không tự đo bandwidth, cache misses, mức tải hoặc throughput của Java.

### 5.2. Độ trễ và băng thông thực sự

Nếu muốn biết truy cập remote tốn bao nhiêu thời gian, cần **benchmark trên phần cứng mục tiêu** với workload được thiết kế để truy cập DRAM, kiểm soát CPU affinity, memory placement và giảm nhiễu từ cache hoặc cạnh tranh tải.

Ví dụ mô hình lý thuyết:

~~~text
T_trung_bình ≈ p_local * T_local + (1 - p_local) * T_remote
~~~

Trong đó:

- `p_local`: tỷ lệ truy cập DRAM thực sự tới node gần.
- `T_local`: độ trễ trung bình của truy cập local.
- `T_remote`: độ trễ trung bình của truy cập remote.

Đây chỉ là **mô hình tuyến tính đơn giản để giải thích trực giác**. Chương trình thật có prefetch, cache/coherence, nhiều yêu cầu nhớ song song, queueing và bandwidth bottleneck nên tổng latency/throughput không nhất thiết tuân theo công thức một cách trực tiếp.

Nếu `T_remote > T_local`, giảm tỷ lệ remote access **có thể** giúp cải thiện độ trễ trung bình. Nhưng phải đo trong điều kiện thật để biết **bao nhiêu** và liệu lợi ích có bù chi phí scheduler/pinning/migration hay không.

## 6. Chương trình Java 17+ số 1: minh họa local/remote bằng ma trận tương đối

Mục đích chương trình này là **chứng minh logic quan hệ CPU node ↔ memory node**, không phải đo tốc độ RAM của máy đang chạy.

Tạo file **`NumaLocalityModelDemo.java`**:

~~~java
public class NumaLocalityModelDemo {
    private static final int[][] DISTANCE = {
            {10, 20},
            {20, 10}
    };

    static String access(int cpuNode, int memoryNode) {
        boolean local = cpuNode == memoryNode;
        return (local ? "local" : "remote")
                + "(distance=" + DISTANCE[cpuNode][memoryNode] + ")";
    }

    public static void main(String[] args) {
        System.out.println("cpu0-memory0=" + access(0, 0));
        System.out.println("cpu0-memory1=" + access(0, 1));
        System.out.println("cpu1-memory1=" + access(1, 1));
        System.out.println("cpu1-memory0=" + access(1, 0));
        System.out.println("localPlusRemote="
                + (DISTANCE[0][0] + DISTANCE[0][1]));
        System.out.println("twoLocal="
                + (DISTANCE[0][0] + DISTANCE[1][1]));
        System.out.println("illustrationOnly=true");
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac --release 17 -encoding UTF-8 NumaLocalityModelDemo.java
java NumaLocalityModelDemo
~~~

**Stdout đã được kiểm thử:**

~~~text
cpu0-memory0=local(distance=10)
cpu0-memory1=remote(distance=20)
cpu1-memory1=local(distance=10)
cpu1-memory0=remote(distance=20)
localPlusRemote=30
twoLocal=20
illustrationOnly=true
~~~

Đọc kết quả:

- `cpu0-memory0` và `cpu1-memory1` là **local** vì CPU và RAM có cùng node trong mô hình.
- `cpu0-memory1` và `cpu1-memory0` là **remote** vì truy cập đi qua node khác.
- Hai giá trị `localPlusRemote=30` và `twoLocal=20` chỉ là phép cộng **score giả định** để thấy truy cập remote có thể làm tổng chi phí lớn hơn.
- Dòng `illustrationOnly=true` nhắc rằng chương trình **không dùng Linux NUMA API**, không đọc physical page location, không đo latency, không chứng minh `20/10` là tỷ lệ thời gian thực.

Để đo máy thật, phải lấy topology của OS và thiết kế benchmark kiểm soát vị trí thread và trang nhớ; phần 8 và 9 hướng dẫn cách tiếp cận đó.

## 7. Khởi động G1 và tìm hiểu option `UseNUMA` hiện hành

Các cờ HotSpot liên quan:

| Option | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn G1 collector | G1 thường là collector mặc định trên HotSpot server hiện đại |
| `-XX:+UseNUMA` | Yêu cầu các tối ưu cho kiến trúc NUMA | Hiệu lực thực sự phụ thuộc JVM, GC, OS và topology |
| `-XX:-UseNUMA` | Tắt các tối ưu NUMA tương ứng khi được hỗ trợ | Có thể dùng làm cấu hình đối chứng có kiểm soát |
| `-XX:+PrintFlagsFinal` | In giá trị cờ JVM cuối cùng | Có thể xem `UseG1GC`, `UseNUMA` là true hay false |
| `-Xlog:numa*=debug` | Đăng ký unified logging cho tag liên quan NUMA của HotSpot | Mức log và thông tin thực tế phụ thuộc JDK/hardware; không hứa luôn có dòng NUMA |
| `-Xlog:gc*=info` | Log các hoạt động GC bằng unified logging | Bổ trợ quan sát G1, **không** tự biến thành phép đo độ trễ NUMA |

Oracle JDK 25/27 vẫn tài liệu hóa `-XX:+UseNUMA`, đồng thời nêu **giá trị mặc định phụ thuộc garbage collector**. Vì thế không được tuyên bố cờ luôn mặc định bật hoặc mặc định tắt trên mọi Java/GC.

Lệnh gợi ý trên máy **Linux đa NUMA node** có JVM hỗ trợ:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:numa*=debug -Xms2g -Xmx2g -jar app.jar
~~~

Đây là **ví dụ thao tác vận hành**, không phải một phép benchmark đã chạy trong bài và không phải cấu hình tối ưu cho mọi ứng dụng. Cần thay `app.jar` bằng chương trình của bạn, chọn kích thước heap phù hợp, xác nhận chính cờ/log tag đã được JVM hỗ trợ và đọc kết quả thật.

Kiểm tra cờ thực tế:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseG1GC|UseNUMA'
~~~

Nếu JVM in `UseNUMA = false` dù bạn đã truyền `-XX:+UseNUMA`, hệ thống có thể không hỗ trợ chế độ NUMA đó trong điều kiện hiện tại. Đừng dựa vào việc câu lệnh được parse thành công để khẳng định allocator đang phân bổ page theo NUMA.

**Kết quả kiểm tra có giới hạn trên Windows JDK 24.0.2:** khi chạy với `-XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal`, máy thử trả `UseG1GC=true` nhưng `UseNUMA=false`. Đây là minh họa rằng **cờ được yêu cầu chưa chắc có hiệu lực** trên mọi OS/JVM, không phải kết luận mọi bản JDK trên Windows đều có hành vi giống nhau.

**Đừng áp dụng cứng cho production:** chỉ cân nhắc bật/tắt NUMA trên host thật có nhiều node và có bằng chứng performance. Nhiều JVM nhỏ trên máy đơn node hoặc container bị giới hạn CPU/memory có thể không hưởng lợi đáng kể.

## 8. Kiểm tra topology NUMA thực tế trên Linux

Các lệnh sau dành cho **Linux**, cần có quyền truy cập sysfs và tiện ích `numactl`/`numastat`. Chúng **chưa được chạy trên máy Linux đa NUMA node trong bài**, vì môi trường kiểm thử hiện tại là Windows. Đây là các lệnh đọc thông tin hệ thống được tài liệu Linux hỗ trợ.

~~~bash
# Kiểm tra node, CPU lists, RAM và khoảng cách tương đối.
numactl --hardware

# Chỉ số node đang online.
cat /sys/devices/system/node/online

# Khoảng cách từ node0 tới các node khác (nếu node0 tồn tại).
cat /sys/devices/system/node/node0/distance

# CPU thuộc node0.
cat /sys/devices/system/node/node0/cpulist

# Xem chính sách NUMA của tiến trình hiện tại.
numactl --show
~~~

Mẫu minh họa **giả định**, không phải output đã đo:

~~~text
node 0 cpus: 0 1 2 3
node 1 cpus: 4 5 6 7
node distances:
node   0   1
  0:  10  20
  1:  20  10
~~~

Khi đọc:

- `node 0 cpus` là các CPU logic gắn với node0 ở mức hệ điều hành; nó **không phải toàn bộ số Java threads**.
- `node distances` là ma trận **chi phí tương đối do OS công bố**; không thể biến `20` thành “20 ns latency” chỉ bằng cách đọc file này.
- Một host báo **một NUMA node** không có kiểu truy cập “remote node khác” trong topology nhìn thấy của tiến trình; chạy G1 với NUMA flag không tự tạo node thứ hai.
- Container/cpuset có thể làm **vùng CPU và memory nodes được phép** của tiến trình hẹp hơn topology toàn host; cần kiểm tra tài nguyên thực sự có thể dùng.
- Node topology và memory placement là dữ liệu của OS/hardware, không phải property có sẵn qua `System.getProperty("numa.node")` trong Java SE.

### Quan sát bộ nhớ của một tiến trình

Trên Linux có `numastat`:

~~~bash
numastat -p <PID>
~~~

Ký hiệu `<PID>` là chỗ thay bằng ID tiến trình Java thật. Tùy version `numastat`, kết quả thống kê cách memory được phân bố theo node. Cần phân biệt **số trang đang nằm ở node nào** với **latency của từng lần truy cập**: lượng memory tại node A chưa chứng minh mọi CPU đọc nó đều ở node A.

Có thể phối hợp thông tin này với GC logs và số đo ứng dụng, nhưng đừng xem một dòng log `numa` là phép đo throughput độc lập.

## 9. Cách làm thí nghiệm local và remote đúng mục tiêu

Khi có máy **Linux thật sự nhiều NUMA node**, có thể dùng `numactl` để kiểm soát điều kiện thử nghiệm. Một phương pháp đơn giản là giữ CPU affinity của process ở node0, rồi thay chính sách memory node cho hai lần chạy.

Ví dụ minh họa, **chỉ dùng trên máy đã xác minh node0 và node1 hợp lệ**, có đủ RAM, quyền cài đặt và hiệu ứng policy được chấp nhận:

~~~bash
# Ưu tiên CPU node0 và cấp bộ nhớ node0: điều kiện local giả định.
numactl --cpunodebind=0 --membind=0 \
  java -XX:+UseG1GC -Xms2g -Xmx2g -jar workload.jar

# Vẫn CPU node0 nhưng buộc memory node1: điều kiện remote giả định.
numactl --cpunodebind=0 --membind=1 \
  java -XX:+UseG1GC -Xms2g -Xmx2g -jar workload.jar
~~~

**Không dùng hai lệnh này như cấu hình production chung.** `--membind` là một chính sách ràng buộc chặt; nếu node bị ràng buộc không đủ memory hoặc nằm ngoài cpuset được phép, việc cấp phát có thể thất bại. Với workload thực tế, process còn có JVM/GC threads, native memory, I/O và hoạt động OS; gọi một lần chạy là “local 100%” chỉ vì flag là **quá đơn giản hóa**.

Muốn kết luận đáng tin cần:

1. Xác nhận topology, RAM mỗi node, CPU affinity và vùng node process được phép dùng trước khi chạy.
2. Giữ **cùng JDK/collector, heap, input, số worker threads, warmup và điều kiện tải** giữa các lần.
3. Chạy đủ lâu để hết giai đoạn JVM warmup/JIT, đo nhiều lần, xem median, percentiles, biến thiên và tài nguyên.
4. Đo **chỉ số quan trọng với ứng dụng**: throughput, p95/p99 latency, GC pause time, CPU utilization, page faults và memory bandwidth nếu công cụ cho phép.
5. Quan sát `numastat -p PID` hoặc hệ thống giám sát tương đương, để kiểm tra thực sự có khác biệt memory placement.
6. Tránh cache benchmark quá nhỏ; dữ liệu phải có mô hình truy cập phù hợp với DRAM hoặc ứng dụng thật.
7. Sau khi xác định khác biệt local/remote phần cứng, mới so sánh thêm **G1 với `UseNUMA` bật/tắt** trong điều kiện được kiểm soát.
8. Ghi nhận các yếu tố ngoài JVM: Linux NUMA balancing, process migration, cgroup/cpuset, shared host contention, huge pages và kernel version.

**Quan trọng:** so sánh local/remote bằng `numactl` là một loại thí nghiệm; so sánh `-XX:+UseNUMA` với `-XX:-UseNUMA` là một loại khác. Không trộn hai kết quả để tuyên bố G1 “giảm X% remote latency” nếu chưa phân biệt chi phí phần cứng và tác dụng của collector.

## 10. Chương trình Java 17+ số 2: xác nhận đang chạy G1, không tự nhận mình đo NUMA

Java SE có API chuẩn để quan sát **GC beans, heap và CPU count**, nhưng không có API portable được bảo đảm có thể trả **NUMA node của mọi Java object**. Chương trình sau chỉ xác nhận môi trường G1 và nói rõ giới hạn đó.

Tạo file **`G1EnvironmentDemo.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

public class G1EnvironmentDemo {
    public static void main(String[] args) {
        boolean g1Selected = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getName().startsWith("G1 ")) {
                g1Selected = true;
            }
        }
        if (!g1Selected) {
            throw new AssertionError("Run this demonstration with -XX:+UseG1GC");
        }

        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        System.out.println("g1Selected=" + g1Selected);
        System.out.println("heapMaxPositive="
                + (memory.getHeapMemoryUsage().getMax() > 0));
        System.out.println("processorsPositive="
                + (Runtime.getRuntime().availableProcessors() > 0));
        System.out.println("numaNodeFromStandardJavaAPI=not-exposed");
    }
}
~~~

Biên dịch và chạy trên HotSpot/OpenJDK JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 G1EnvironmentDemo.java
java -XX:+UseG1GC -Xmx256m G1EnvironmentDemo
~~~

**Stdout đã kiểm tra trên HotSpot/OpenJDK:**

~~~text
g1Selected=true
heapMaxPositive=true
processorsPositive=true
numaNodeFromStandardJavaAPI=not-exposed
~~~

Giải thích:

- `ManagementFactory.getGarbageCollectorMXBeans()` cho metadata GC của JVM; trong HotSpot với G1, GC beans có tên bắt đầu `"G1 "`.
- `heapMaxPositive=true` xác nhận `-Xmx256m` cho giới hạn heap dương; nó **không** xác định page memory thuộc node nào.
- `processorsPositive=true` chỉ xác nhận JVM thấy số processors lớn hơn 0; nó **không** nói có bao nhiêu NUMA nodes, vì CPU count không đồng nghĩa node count.
- Dòng `numaNodeFromStandardJavaAPI=not-exposed` là thông báo có chủ đích để phân biệt thông tin quản lý JVM với topology/physical placement. Nó không phải kết quả của một truy vấn API nào tự tìm node của object.
- Tên GC beans là thông tin triển khai có thể khác với JVM khác. Ví dụ này nhắm HotSpot/OpenJDK; điều kiện `startsWith("G1 ")` **không phải chuẩn nhận dạng mọi GC trên mọi máy ảo Java**.

Nói cách khác: chương trình có thể xác nhận **G1 được chọn**, nhưng không thể dùng `ManagementFactory` đơn độc để tuyên bố các object đang nằm ở node0 hoặc tỷ lệ local/remote access.

## 11. Khi nào NUMA locality giúp và khi nào không rõ lợi ích?

NUMA locality có khả năng đáng quan tâm khi:

- Máy có nhiều NUMA nodes vật lý/logic **thực sự được process sử dụng**, chứ không chỉ nhiều core trong cùng node.
- Heap/object working set lớn và có nhiều truy cập DRAM, khiến cost của remote memory dễ thể hiện.
- Nhiều thread phân bổ và tiêu thụ phần lớn dữ liệu gần nơi chúng chạy; locality có thể tối ưu theo những nhóm đó.
- Remote link hoặc bandwidth đang bị tải, và profiler/OS counters cho thấy remote accesses đáng kể.
- Có thể kiểm soát placement hoặc ít nhất đo xác thực ảnh hưởng của điều chỉnh NUMA.

Có thể **ít cải thiện hoặc khó chứng minh** khi:

- Chỉ có một node khả dụng, hoặc container/cpuset giới hạn chỉ một node.
- Working set chủ yếu nằm trong CPU caches, ít truy cập RAM.
- Object được chia sẻ rộng khắp giữa threads của nhiều node; không có một vị trí “local cho tất cả”.
- Scheduler thường chuyển thread, OS tự cân bằng memory pages hoặc GC di chuyển object.
- Tắc nghẽn thật nằm ở lock contention, IO, database, network hoặc algorithm, không phải NUMA.
- Chi phí ép affinity, migration và mất khả năng cân bằng tải lớn hơn lợi ích local memory.
- Tải/hệ điều hành không hỗ trợ hoặc bỏ qua `UseNUMA`, dù option được truyền.

Không nên đưa ra một số phần trăm cải thiện cố định cho mọi ứng dụng. JEP 345 và các benchmark lịch sử giúp giải thích **tiềm năng** của NUMA-aware allocation, nhưng **không thay thế phép đo riêng cho ứng dụng đang vận hành trên JDK/OS/hardware hiện tại**.

## 12. Các lỗi hiểu nhầm thường gặp

**Lỗi 1 — “NUMA node là một core.”**  
Sai. Node thường bao gồm nhiều CPUs/cpu threads và một vùng bộ nhớ; không thể đếm core rồi suy ra số NUMA nodes.

**Lỗi 2 — “NUMA node luôn bằng một CPU socket.”**  
Không nhất thiết. Cấu hình phần cứng, BIOS/firmware và OS có thể chia node khác ranh giới socket.

**Lỗi 3 — “Node0 luôn có RAM gần mọi CPU.”**  
Sai. Local/remote là quan hệ theo CPU đang thực thi. Node0 local với CPU của node0, nhưng remote với CPU ở node khác.

**Lỗi 4 — “NUMA distance=20 nghĩa là 20 ns.”**  
Sai. Dữ liệu `distance` của Linux là **chỉ số khoảng cách tương đối**, không trực tiếp là phép đo latency.

**Lỗi 5 — “Thread tạo object rồi thì object luôn gần thread.”**  
Sai. Thread có thể chuyển node, GC có thể di chuyển object, OS có thể đặt/migrate pages và data có thể chia sẻ giữa nhiều nodes.

**Lỗi 6 — “JEP 345 làm mọi old object trong G1 luôn local.”**  
Sai. Cải tiến ban đầu tập trung vào locality của young generation; không có bảo đảm tổng quát như vậy. Các heuristic cụ thể có thể thay đổi theo JDK.

**Lỗi 7 — “Bật `UseNUMA` tức chắc chắn đang có NUMA optimization.”**  
Sai. Cần xác nhận cờ hiệu lực và topology hỗ trợ. Một JVM có thể báo `UseNUMA=false` trong thực tế mặc dù dòng lệnh có yêu cầu bật.

**Lỗi 8 — “Nếu heap có nhiều regions thì chắc chắn mỗi region là một NUMA node.”**  
Sai. Heap regions là đơn vị quản lý của G1; NUMA nodes là topology của OS/hardware. Một node chứa nhiều regions và mỗi region có nhiều OS pages.

**Lỗi 9 — “Càng ép mọi thread về một node càng tốt.”**  
Không hẳn. Nếu node quá tải hoặc thiếu RAM, ép affinity/membind có thể làm giảm throughput hoặc lỗi allocation.

**Lỗi 10 — “Chạy microbenchmark mảng nhỏ là đo được NUMA DRAM.”**  
Không đáng tin. Mảng có thể chủ yếu nằm trong CPU cache; JVM JIT, warmup, prefetch và concurrent load dễ chi phối số đo.

**Lỗi 11 — “`-XX:+UseG1GC` tự bật mọi tối ưu NUMA.”**  
Không được suy ra vậy. Giá trị và hiệu lực của `UseNUMA` phụ thuộc GC/JVM/OS, cần kiểm tra riêng.

**Lỗi 12 — “`numastat -p` cho ta latency của từng Java object.”**  
Không. Nó cho thống kê phân bố bộ nhớ của process, không trả độ trễ của từng phép truy cập hoặc nút của một object Java tùy ý.

**Lỗi 13 — “Remote RAM lúc nào cũng chậm đúng một hệ số.”**  
Sai. CPU caches, interconnect, memory bandwidth, topology và tải quyết định hiệu năng thực tế.

**Lỗi 14 — “Thấy benchmark cải thiện là do G1 NUMA.”**  
Chưa chắc. Phải so sánh cùng JDK/heap/workload và phân biệt thay đổi NUMA policy, GC, topology/CPU affinity và nguồn nhiễu.

## 13. Checklist thực tế khi xử lý hiệu năng G1 + NUMA

1. **Xác định topology**: ít nhất bao nhiêu NUMA nodes, CPUs thuộc node nào, RAM khả dụng của từng node?
2. **Xác định workload**: heap lớn hay nhỏ, object locality theo thread có rõ không, hay data chia sẻ rộng?
3. **Kiểm tra G1**: xác minh `UseG1GC` và phiên bản JVM thay vì giả định chỉ từ lệnh `java`.
4. **Kiểm tra `UseNUMA` thực tế**: xem `PrintFlagsFinal` và log, không dựa riêng vào option đầu vào.
5. **Xem OS policy**: affinity, cpuset/container, NUMA balancing, page placement và quyền tài nguyên.
6. **Đo trước khi thay**: throughput, tail latency, GC pauses, CPU utilization, memory bandwidth và phân bố memory per node.
7. **Đặt giả thuyết có thể kiểm chứng**: ví dụ “remote traffic cao khi các worker của node1 liên tục đọc data ở node0”.
8. **Thay một yếu tố mỗi lần**: mặc định, `UseNUMA` bật, `UseNUMA` tắt hoặc policy node trong những đợt riêng; không trộn thay đổi heap và số threads tùy tiện.
9. **Lặp lại phép thử**: warmup đủ, lấy nhiều samples, đo độ biến thiên và loại các lần có nhiễu tải.
10. **Xem trade-off**: locality có thể tốt hơn nhưng fairness, throughput, GC pause hoặc resource utilization có thể xấu đi.
11. **Tránh tối ưu máy đơn node**: nếu không có remote node hữu dụng, việc ép NUMA không có mục đích rõ.
12. **Ghi nhận JDK/OS/hardware**: các con số benchmark phải kèm môi trường; không hứa kết quả giống trên máy khác.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** CPU thuộc node0 đọc RAM node1 là local hay remote?  
**Đáp án:** **Remote**, vì CPU và bộ nhớ thuộc hai node khác nhau.

**Câu 2.** Nếu thread chuyển từ CPU node0 sang CPU node1 nhưng dữ liệu vẫn nằm ở RAM node0, locality có thể đổi không?  
**Đáp án:** **Có**. Dữ liệu vốn local với CPU node0 có thể trở thành remote với CPU node1.

**Câu 3.** `numactl --hardware` cho hai node với distances 10 và 20 có nghĩa remote latency là 20 ns không?  
**Đáp án:** **Không**. Đây là giá trị khoảng cách tương đối do hệ điều hành cung cấp, không phải nanosecond.

**Câu 4.** JEP 345 được đưa vào JDK nào và nhằm cải thiện gì?  
**Đáp án:** JDK 14. Nó làm G1 hiểu NUMA tốt hơn khi cấp phát/giữ object trẻ để tăng khả năng local memory access.

**Câu 5.** Chạy `-XX:+UseNUMA` đã chứng minh mọi object local chưa?  
**Đáp án:** **Chưa**. Cần kiểm tra cờ có hiệu lực, topology, OS placement và workload; cơ chế chỉ cố tối ưu.

**Câu 6.** Java `GarbageCollectorMXBean` có trả NUMA node của một object bất kỳ không?  
**Đáp án:** **Không**. Nó dùng để quan sát thông tin GC, không phải API portable để truy vấn physical page mapping.

**Câu 7.** Nhiều core trên một NUMA node có nghĩa là nhiều NUMA nodes không?  
**Đáp án:** **Không**. Số core và số NUMA nodes là hai thông số khác nhau.

**Câu 8.** Vì sao benchmark object array nhỏ không đủ kết luận remote DRAM chậm bao nhiêu?  
**Đáp án:** Dữ liệu có thể nằm trong CPU cache; cần phương pháp đo phù hợp và kiểm soát CPU/memory placement.

**Câu 9.** `numastat -p PID` báo pages ở node0. Có chắc mọi truy cập đều local không?  
**Đáp án:** **Không**. Thread có thể chạy ở các node khác nhau; thống kê placement không đo riêng từng access.

**Câu 10.** Khi nào không nên chủ động ép `numactl --membind`?  
**Đáp án:** Khi chưa xác minh nodes/đủ RAM/quyền, khi workload chưa được đo, hoặc trong production nơi ràng buộc có thể gây thiếu RAM và giảm khả năng cân bằng tải.

## Tài liệu chính thức và đọc thêm

- **OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1** (bổ sung trong JDK 14): https://openjdk.org/jeps/345
- **Oracle JDK 14 Release Notes — JEP 345**: mô tả mục tiêu G1 young NUMA locality, sự khác biệt Old/Humongous và cờ `-XX:+UseNUMA`: https://www.oracle.com/java/technologies/javase/14-relnote-issues.html
- **Oracle JDK 25 — Java Command**: `-XX:+UseNUMA` còn được hỗ trợ, default phụ thuộc collector; `-XX:+UseG1GC` và unified logging: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle JDK 25 — Garbage-First (G1) Garbage Collector**: heap regions, young/old, evacuation và pause/throughput trade-off: https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html
- **Oracle Java SE 17 — G1 GC Tuning**: khuyến nghị bắt đầu từ mặc định, đo workload thật trước khi tuning: https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html
- **Linux manual — numactl(8)**: `--hardware`, `--cpunodebind`, `--membind`, `--localalloc` và `--show`: https://man7.org/linux/man-pages/man8/numactl.8.html
- **Linux kernel sysfs ABI — node distance/cpulist/meminfo**: https://www.kernel.org/doc/html/latest/admin-guide/abi-stable-files.html
- **Linux manual — numa(3)**: NUMA node, memory policies và first-touch/page fault: https://man7.org/linux/man-pages/man3/numa.3.html