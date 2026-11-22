# Mục tiêu của cấp phát nhận biết NUMA trong G1 từ Java 14

## 1. Tóm tắt đúng trọng tâm

**JEP 345 — NUMA-Aware Memory Allocation for G1**, được tích hợp từ **JDK 14**, bổ sung khả năng phân bổ bộ nhớ Java heap của **Garbage-First Garbage Collector (G1 GC)** theo cấu trúc phần cứng **NUMA — Non-Uniform Memory Access**. Mục tiêu chính của JEP là **cải thiện hiệu năng G1 trên máy lớn có nhiều NUMA node**, thông qua **ưu tiên cấp phát và giữ đối tượng ở bộ nhớ gần nơi luồng Java hoặc luồng GC đang thực thi**, qua đó giảm truy cập bộ nhớ từ xa với độ trễ cao.

Nói ngắn gọn:

- **Đầu vào:** nhiều CPU hoặc nhóm CPU có mức độ gần bộ nhớ vật lý khác nhau.
- **Vấn đề:** một luồng thực thi trên node A nhưng thường xuyên đọc/ghi trang nhớ ở node B sẽ chịu chi phí kết nối giữa các node.
- **Cải tiến của G1:** tổ chức cấp phát ở vùng **young generation**, đặc biệt **Eden** (đối tượng mới) và **Survivor** (đối tượng sống qua GC), có xét tới NUMA node.
- **Kết quả kỳ vọng:** nhiều truy cập **local memory** hơn, ít truy cập **remote memory** hơn, có khả năng cải thiện throughput và độ trễ thực tế.
- **Giới hạn:** tối ưu này là **best effort**, không bảo đảm mỗi object luôn nằm ở node của thread, không làm toàn bộ G1 tự động trở thành bộ lập lịch NUMA, và **không bảo đảm phần trăm tăng tốc cố định**.

Trong HotSpot hiện đại, cấu hình quan trọng để thử nghiệm G1 NUMA là:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -jar your-app.jar
```

Đây là **lệnh minh họa**, không phải lệnh luôn có hiệu quả trên mọi máy. `-XX:+UseG1GC` chọn G1, còn `-XX:+UseNUMA` **yêu cầu** dùng tối ưu NUMA. JVM/OS vẫn phải có **NUMA topology khả dụng** và hỗ trợ thực tế. Kiểm tra flag đang **có hiệu lực**, topology và log trước khi kết luận.

**Điều vẫn đúng trong Java hiện nay:** G1 NUMA awareness từ Java 14 là một cải tiến runtime/HotSpot có giá trị tiếp tục được dùng trong JDK hiện đại, không phải cú pháp ngôn ngữ Java mới, không phải API lập trình bắt buộc gọi trong mã ứng dụng. Oracle JDK 25/27 vẫn ghi nhận `-XX:+UseNUMA` trong tài liệu lệnh `java`.

Bài học chỉ dùng phương thức Java 17+ và tùy chọn HotSpot còn được tài liệu JDK hiện hành công bố; không đưa các cờ GC lỗi thời hoặc hướng dẫn khởi chạy Java 14 không còn được hỗ trợ làm mặc định sản xuất.

## 2. NUMA là gì và vì sao ảnh hưởng đến G1?

### 2.1. Bộ nhớ không đồng đều

Trên kiến trúc **UMA (Uniform Memory Access)** đơn giản, thời gian truy cập RAM được giả định tương đối đồng đều giữa các CPU. Trên hệ thống **NUMA**, CPU được tổ chức thành các **node**; mỗi node gắn với một phần bộ nhớ hoặc một nhóm bộ điều khiển bộ nhớ.

Ví dụ khái niệm:

```text
NUMA node 0                          NUMA node 1
+-------------------+                +-------------------+
| CPU cores nhóm 0  |                | CPU cores nhóm 1  |
| RAM local node 0  |                | RAM local node 1  |
+---------+---------+                +---------+---------+
          |                                    |
          +----------- interconnect ---------+
                    remote access
```

Khi luồng trên CPU của node 0 đọc trang nhớ nằm trên node 0, nó thường có **độ trễ truy cập thấp hơn** so với truy cập trang nằm trên node 1. Chi phí thực tế phụ thuộc CPU, interconnect, tải hệ thống, bộ nhớ đệm và việc thread có bị chuyển CPU hay không.

Các con số thường thấy trong sơ đồ minh họa, chẳng hạn “local 80 ns, remote 140 ns”, **không phải bảo đảm phần cứng hay số liệu benchmark của Java**. Đo trên máy thật và xem đặc tả phần cứng nếu cần so sánh định lượng.

**Một socket không nhất thiết bằng một NUMA node**; số node và cấu trúc phụ thuộc thiết kế CPU/BIOS và cấu hình hệ điều hành. Ở máy có một NUMA node hoặc một container chỉ được dùng một node, khái niệm **remote memory giữa nhiều node không còn cơ hội tối ưu theo cách JEP 345 nhắm tới**.

### 2.2. Tác động tới ứng dụng cấp phát nhiều đối tượng

Một ứng dụng Java xử lý request trên nhiều luồng có thể liên tục tạo đối tượng ngắn hạn: request DTO, collections, buffers, đối tượng trung gian của parser, serialization, tính toán, v.v. G1 cấp phát phần lớn đối tượng mới trong **Eden regions**. Nếu vùng RAM đằng sau Eden mà luồng dùng lại nằm xa node CPU thực thi, nhiều lượt cấp phát và truy cập tiếp theo có thể chịu **remote-memory latency**.

Trong GC, object còn sống có thể được **evacuate/copy** sang Survivor hoặc Old regions. Nếu bố trí vùng đích không xét NUMA, vị trí vật lý của object sau GC có thể làm mất locality trước đó.

JEP 345 tập trung giải quyết đúng hai cơ hội quan trọng của **young generation** này: **cấp phát Eden theo node** và **cấp phát Survivor theo node khi GC copy object**.

### 2.3. Phân biệt NUMA locality với cache locality

- **CPU cache locality:** dữ liệu thường dùng được giữ trong L1/L2/L3 cache hoặc truy cập theo pattern tốt.
- **NUMA memory locality:** trang RAM ở node gần CPU hơn, hạn chế đi qua interconnect để tới node xa.
- **G1 object placement:** JVM chọn vùng heap/region thích hợp để cấp phát object; hệ điều hành còn quyết định backing physical pages.
- **CPU affinity/scheduling:** OS quyết định thread chạy trên CPU nào theo thời gian.

Chúng liên quan nhau nhưng **không đồng nhất**. Bật NUMA-aware allocation không tự giải quyết cache misses, CPU migrations, false sharing, contention hoặc thuật toán ứng dụng có locality kém.

## 3. G1 quản lý heap theo region

G1 chia Java heap thành nhiều **regions có kích thước tương đương**. Đây là đơn vị quản lý cấp phát/thu hồi và được gán vai trò theo thời gian:

| Loại region | Chức năng chính | Quan hệ với mục tiêu JEP 345 |
| --- | --- | --- |
| **Eden** | Nhận phần lớn object mới do application threads tạo | Cấp phát ưu tiên NUMA node của mutator đang chạy |
| **Survivor** | Chứa object đã sống sót qua young GC và được copy | Ưu tiên destination region/buffer theo NUMA node của GC worker |
| **Old** | Chứa object có vòng đời dài hoặc được thăng cấp | **Không** có cùng cam kết giữ locality theo per-thread như Eden/Survivor |
| **Humongous** | Object rất lớn, cần nhiều region hoặc được bố trí trong old generation | Phân bố theo chiến lược cân bằng/interleave, không phải per-thread Eden placement |

G1 có thể đổi vai trò của region theo nhu cầu bộ nhớ; không được coi các dải Eden, Survivor và Old là ba khu vực vật lý bất biến trong heap. JDK hiện đại vẫn mô tả G1 theo cơ chế regionalized, generational.

**Quan trọng:** một G1 region là khái niệm của JVM, trong khi **NUMA node được xác định ở mức CPU/RAM vật lý**; mỗi region được backing bởi một hoặc nhiều trang nhớ của OS. JVM có thể đề xuất NUMA policy; OS quyết định liệu các trang có thật sự được cấp ở node mong muốn, tùy quyền hạn và lượng RAM còn trống.

### 3.1. TLAB không phải NUMA node

HotSpot thường cấp phát object nhanh trong **Thread-Local Allocation Buffer (TLAB)**, tức một khối cấp phát cho mỗi thread, giảm tranh chấp khi nhiều luồng tạo object. JEP 345 **không thay TLAB bằng node**; cải tiến là cách G1 tổ chức các **allocation regions phía sau** để TLAB và cấp phát khác có khả năng nhận bộ nhớ phù hợp NUMA locality.

Ví dụ có bốn thread Java cùng chạy trên node 0: mỗi thread có thể dùng TLAB riêng nhưng các region cung cấp bộ nhớ được **ưu tiên** đặt tại node 0. Nếu thread bị OS chuyển sang node 1, placement của object đã tồn tại **không tự dịch chuyển tức khắc** theo thread.

### 3.2. G1 region khác OS page

Hãy phân biệt:

- **Object:** ví dụ `new byte[2048]`.
- **TLAB / PLAB:** vùng cấp phát tối ưu cho thread/GC worker.
- **G1 heap region:** đơn vị quản lý heap thuộc JVM.
- **OS memory page:** đơn vị ánh xạ virtual memory sang physical memory.
- **NUMA node:** nhóm CPU và vùng physical memory.

Một heap region có thể gồm nhiều OS pages; với huge pages thì quan hệ có thể khác. Vì thế, yêu cầu placement theo NUMA node ở mức G1 region **không phải lời hứa mỗi byte/page của region luôn được đặt chuẩn tuyệt đối**. Page size, huge pages, policies của Linux và tình trạng thiếu RAM đều có thể ảnh hưởng placement.

## 4. Những mục tiêu kỹ thuật cốt lõi của JEP 345

### 4.1. Mục tiêu tổng quát: tăng hiệu năng trên máy NUMA lớn

JEP 345 nhắm tới các server nhiều CPU/NUMA nodes, đặc biệt ứng dụng có **độ lớn heap và tốc độ cấp phát đáng kể**. Khi tăng locality, kỳ vọng giảm chi phí truy cập bộ nhớ từ xa, tăng hiệu quả sử dụng CPU và throughput, và trong một số workload có thể cải thiện độ trễ.

**Không có nghĩa:** mọi ứng dụng Java 14+ sẽ chạy nhanh hơn sau khi thêm `-XX:+UseNUMA`. Nếu heap và ứng dụng thực tế chủ yếu chạy/được cấp phát trên một node, hoặc workload bị giới hạn bởi disk, network, khóa, GC pause khác, lợi ích có thể bằng 0 hoặc thay đổi theo cấu hình.

### 4.2. Cấp phát đối tượng mới ưu tiên node của Java thread

Trước cải tiến, G1 không dùng NUMA-local region theo mutator thread với độ chi tiết mới mà JEP 345 bổ sung. Sau cải tiến, G1 có thể duy trì **mutator allocation regions theo NUMA node**. Khi một Java thread yêu cầu bộ nhớ và JVM biết node CPU nơi nó đang chạy, G1 **ưu tiên** lấy một Eden allocation region tương ứng node đó.

Sơ đồ khái niệm:

```text
Java thread T0 chạy CPU node 0
    |
    v
G1 chọn mutator allocation region ưu tiên node 0
    |
    v
TLAB / object mới trong Eden region liên quan node 0
    |
    v
Truy cập object có cơ hội dùng RAM local node 0
```

Đây là **ưu tiên placement**, không pin một Java thread cố định vào node và không yêu cầu lập trình viên gọi một API `allocateOnNode(0)`.

### 4.3. Giữ locality cho object sống qua young GC

Trong một **young GC**, G1 sao chép object còn sống từ Eden/Survivor cũ sang Survivor mới hoặc thăng cấp sang Old.

JEP 345 mở rộng locality vào quá trình **Survivor evacuation**: các GC worker có thể sử dụng vùng cấp phát Survivor theo NUMA node. **Promotion-Local Allocation Buffer (PLAB)** hỗ trợ các worker copy nhiều object mà giảm tranh chấp.

Sơ đồ:

```text
Young GC / parallel GC workers
        |
        +--> worker trên node 0
        |        |
        |        v
        |   PLAB / Survivor region ưu tiên node 0
        |
        +--> worker trên node 1
                 |
                 v
            PLAB / Survivor region ưu tiên node 1
```

Như vậy, G1 cố gắng **không đánh mất hoàn toàn lợi ích NUMA-locality sau mỗi young collection**. Tuy nhiên, nơi object được copy còn phụ thuộc worker thực hiện, region có sẵn và OS; **không có cam kết object luôn ở đúng node nơi thread tạo nó** sau mọi GC.

### 4.4. Phân bố và cân bằng các vùng heap

JDK 14 release notes nêu rõ: với **Old và Humongous regions**, G1 cố gắng **phân bố tương đối đều giữa các NUMA nodes bằng strict interleave**; placement của object copy từ young sang old có tính ngẫu nhiên theo chiến lược thời điểm đó.

Từ đó có hai kết luận:

1. **Young Eden/Survivor** là trọng tâm NUMA-aware placement theo thread/worker của JEP 345.
2. **Old/Humongous** không nên được mô tả là luôn giữ cùng locality theo mutator như young. Cần cân bằng vùng nhớ, tránh dồn toàn bộ heap vào một node.

Một số heuristic chi tiết trong HotSpot đã tiếp tục phát triển qua các bản JDK. Tài liệu JDK 14 là mốc **giải thích thiết kế được giới thiệu**, không phải cam kết mọi cấu trúc nội bộ G1 trong JDK 25+ bất biến. Chỉ xây vận hành production dựa vào **các tùy chọn được hỗ trợ và kết quả đo trên JVM thực tế**.

### 4.5. Những mục tiêu *không* thuộc JEP này

JEP 345 **không hứa hẹn**:

- Thay đổi bytecode, cú pháp Java, `new` hoặc API collection thông thường.
- Làm **mọi garbage collector** hỗ trợ NUMA giống G1; `-XX:+UseNUMA` còn có hành vi tùy collector.
- Tự pin thread vào node hoặc điều chỉnh affinity của toàn bộ ứng dụng.
- Làm old generation luôn giữ object trên node nơi nó ra đời.
- Biến NUMA thành một cơ chế isolation/bảo mật bộ nhớ giữa tenant.
- Bảo đảm throughput tăng một phần trăm cố định hoặc mọi GC pause giảm.
- Thay thế cách thiết kế thuật toán, buffer, phân vùng dữ liệu và kiểm soát tranh chấp trong ứng dụng.

**Câu trả lời ngắn cho đề bài:** cải tiến nhằm tăng **NUMA-local memory allocation cho G1 trên máy nhiều node**, nhất là ở Eden và Survivor, để **giảm remote-memory access và tăng hiệu năng thực tế khi workload phù hợp**.

## 5. Điều kiện để tối ưu G1 NUMA thực sự có hiệu lực

### 5.1. Có topology NUMA nhìn thấy từ JVM

Một máy phải có **nhiều NUMA memory nodes khả dụng** và OS/JVM phải hỗ trợ. Với HotSpot hiện đại, **Linux** là môi trường thực hành phù hợp để kiểm chứng NUMA node, memory policy và placement.

Kiểm tra trên Linux:

```bash
lscpu
numactl --hardware
```

Các lệnh này cần công cụ hệ thống tương ứng (gói `numactl` có thể chưa được cài). `lscpu` cho biết tổng quan CPU/node; `numactl --hardware` liệt kê các node và bộ nhớ nhìn thấy.

Không chạy thử trên laptop một node rồi kết luận JEP 345 không hoạt động, bởi **không có tài nguyên NUMA khác nhau để so sánh**. Ngược lại, server vật lý có nhiều socket **chưa chắc JVM/container được phép dùng tất cả node**.

### 5.2. Bật G1 và yêu cầu tối ưu NUMA

Cú pháp chuẩn HotSpot vẫn được tài liệu JDK 25/27 công bố:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms4g -Xmx4g -jar your-app.jar
```

`-XX:+UseG1GC` chọn G1; `-XX:+UseNUMA` yêu cầu chính sách NUMA; `-Xms4g` và `-Xmx4g` ở đây chỉ là **con số ví dụ cho máy đủ RAM**, không phải một kích cỡ heap bắt buộc. Trong production, ưu tiên chính sách heap phù hợp load và memory limits.

Để đối chứng:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms4g -Xmx4g -jar your-app.jar
```

**Không mặc định rằng NUMA được bật sẵn.** Tài liệu hiện đại nói giá trị mặc định của `UseNUMA` **phụ thuộc garbage collector**. Dù đã truyền `-XX:+UseNUMA`, JVM còn có thể vô hiệu hóa tối ưu nếu OS, topology hoặc bindings không thích hợp.

### 5.3. Kiểm tra giá trị có hiệu lực, không chỉ kiểm tra command line

Trên Linux:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseG1GC|UseNUMA'
```

Kiểm tra các dòng flag được JVM in ra, nhưng đừng xem riêng việc command line có `+UseNUMA` là bằng chứng đã đặt physical pages đúng node. Kiểm tra thêm **OS/JVM logging**, CPU/memory node bindings và NUMA page placement.

Để xem log liên quan NUMA trong một phiên bản HotSpot hỗ trợ tag này:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:numa*=debug \
  -jar your-app.jar
```

Có thể bổ sung `-Xlog:gc*=info` để thấy hoạt động GC. Tag `numa` được xác nhận có mặt trong các HotSpot hiện đại đã thử; nội dung log cụ thể phụ thuộc JDK, mức log và topology. **Không có dòng NUMA đặc biệt trong log không tự chứng minh heap đã tối ưu hoặc chưa tối ưu**: xem flag, log hệ điều hành và phân bố thực.

### 5.4. Linux / container constraints có thể vô hiệu hóa lợi ích

- **cpuset CPU / mems:** process hoặc container chỉ được dùng các CPU/memory nodes đã cấp. Nếu chỉ có một memory node khả dụng, JVM không thể khai thác hai node.
- **CPU/memory node mismatch:** CPU bị giới hạn một node nhưng memory được cấp trên node khác có thể khiến chính sách local allocation không phù hợp hoặc bị JVM tắt.
- **OS scheduling:** Java threads có thể bị dời CPU/node khi tải đổi; object đã cấp phát không tự dịch chuyển cùng thread.
- **Linux memory policy:** `numactl --membind`, `--interleave`, `--cpunodebind` có thể thay đổi chính sách trang nhớ nhìn từ JVM. Không thử kết hợp ngẫu nhiên nhiều policy trên production mà chưa có A/B.
- **RAM pressure:** node local thiếu bộ nhớ có thể khiến OS dùng node khác, hoặc phát sinh chi phí giữ trang/GC khác.
- **Virtualization:** guest NUMA topology phụ thuộc hypervisor và cấu hình virtual CPUs, không nhất thiết giống host vật lý.
- **Huge pages:** thay đổi độ lớn trang vật lý và cách OS bố trí, có thể ảnh hưởng mức độ chính xác của region affinity.

**Kết luận:** NUMA awareness là phối hợp giữa **hardware → Linux scheduler/memory policy → HotSpot GC**, không phải một boolean độc lập với môi trường.

## 6. Java 17+ runnable: kiểm tra chương trình cấp phát và chọn G1

Không có Java SE API chuẩn nào trong `new` để bảo đảm một object cụ thể được đặt trên NUMA node nào. Ta có thể viết **workload tạo đối tượng** và xác minh G1 đang dùng; để đo **locality thật**, phải chạy trên Linux multi-NUMA-node với công cụ OS, chứ không dựa vào stdout Java.

**Tệp `G1NumaAllocationDemo.java`:**

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class G1NumaAllocationDemo {
    static long produce() {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 3_000; i++) {
            byte[] block = new byte[2_048];
            block[0] = (byte) (i % 128);
            checksum += Byte.toUnsignedInt(block[0]);

            if (i % 200 == 0) {
                survivors.add(block);
            }
        }
        return checksum + survivors.size();
    }

    public static void main(String[] args) throws Exception {
        boolean g1 = ManagementFactory.getGarbageCollectorMXBeans()
                .stream()
                .map(GarbageCollectorMXBean::getName)
                .anyMatch(name -> name.startsWith("G1 "));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Long> work = G1NumaAllocationDemo::produce;
            Future<Long> first = pool.submit(work);
            Future<Long> second = pool.submit(work);

            long total = first.get() + second.get();
            System.out.println("g1CollectorPresent=" + g1);
            System.out.println("workers=2");
            System.out.println("checksum=" + total);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch bằng JDK hiện đại nhưng nhắm API/bytecode Java 17:

```bash
javac --release 17 -encoding UTF-8 G1NumaAllocationDemo.java
```

Chạy baseline với G1:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC G1NumaAllocationDemo
```

Chạy yêu cầu NUMA:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:numa*=debug G1NumaAllocationDemo
```

Chạy tắt NUMA tường minh:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -XX:-UseNUMA G1NumaAllocationDemo
```

**Stdout chính xác được xác minh trên Windows, HotSpot/OpenJDK 24.0.2:**

```text
g1CollectorPresent=true
workers=2
checksum=376998
```

Trong lần thử đó, **cả ba chế độ đều in ba dòng trên**, bên cạnh log nếu có. Đây **không phải** số liệu tốc độ, NUMA hit rate hoặc bằng chứng local allocation. Chương trình chỉ xác nhận G1 được chọn, hai tác vụ cấp phát hoàn thành và checksum đúng.

### 6.1. Giải thích các phần mã

- `GarbageCollectorMXBean` là API chuẩn Java quản lý GC; trong HotSpot với G1, tên collector thường bắt đầu bằng `"G1 "`. Đây là cách kiểm tra loại GC trên môi trường thử, **không phải API xác nhận NUMA locality**.
- `ExecutorService` tạo hai worker Java threads để minh họa ứng dụng đa luồng. **Không** có câu lệnh pin hai threads vào các NUMA nodes cố định.
- Mỗi worker tạo 3.000 mảng byte 2 KiB, có chạm dữ liệu trong `block[0]`; một phần nhỏ được giữ tạm trong `survivors`. Tổng checksum là giá trị **toán học tất định**.
- `Byte.toUnsignedInt` chuyển byte sang số 0–255; nhờ đó checksum không phụ thuộc dấu của byte.
- `Future.get()` chờ hai worker hoàn tất; `shutdown()` giải phóng executor. Không có race trên `checksum` vì mỗi task có biến local riêng.
- Ví dụ có **heap 128 MiB** và chạy rất ngắn, nên **không phù hợp làm benchmark JEP 345**. Để đánh giá locality, cần workload lớn và dài hơn, theo dõi GC, CPU scheduling, memory pages và kết quả nhiều lần.

### 6.2. Kết quả thực tế của cờ NUMA trên máy kiểm chứng

Trên máy Windows JDK 24.0.2 đã thử, lệnh yêu cầu `-XX:+UseNUMA` **được JVM chấp nhận**, nhưng truy vấn flags cuối cùng cho thấy **`UseNUMA = false`** trong khi **`UseG1GC = true`**. Vì vậy không được kết luận tính năng NUMA của G1 đã hoạt động chỉ từ việc chương trình vẫn chạy.

Đây là trường hợp dạy rất tốt về sự khác biệt giữa:

1. **Requested option** — tham số người vận hành đưa vào command line.
2. **Effective VM state** — JVM có thực sự bật cơ chế đó sau kiểm tra OS/topology.
3. **Observed memory locality** — OS thực sự đặt trang nhớ ở node nào và workload có nhận lợi ích không.

**Không bịa stdout về NUMA placement** từ chương trình Java trên máy không có topology Linux thích hợp. Những phần sau trình bày cách đo thực tế.

## 7. Quy trình thử nghiệm đúng trên Linux nhiều NUMA nodes

### Bước 1 — Xác nhận topology và quyền sử dụng

```bash
lscpu
numactl --hardware
```

Đọc số NUMA nodes, CPU thuộc từng node, dung lượng RAM node và khoảng cách truy cập nếu công cụ có hiển thị. Nếu trong container, kiểm tra các ràng buộc CPU/memory được cấp cho process. Đừng thử trên máy chỉ được sử dụng một node rồi coi kết quả là benchmark cho G1 NUMA.

### Bước 2 — Đối chứng hai cấu hình chỉ khác một cờ

Dùng **cùng JDK vendor/build, cùng app, cùng input/tải, cùng heap và cùng giới hạn CPU/RAM**. Ví dụ giả định service cần 4 GiB heap và máy có đủ RAM:

```bash
# Baseline: G1, tắt NUMA optimization
java -Xms4g -Xmx4g -XX:+UseG1GC -XX:-UseNUMA \
  -Xlog:gc*=info -jar your-service.jar

# Experiment: G1, yêu cầu NUMA optimization
java -Xms4g -Xmx4g -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:gc*=info -Xlog:numa*=debug -jar your-service.jar
```

`your-service.jar` là **artifact của ứng dụng thật**, không phải file được tạo ở chương trình demo ở trên. Nếu không có service test, dùng workload/benchmark định lượng được lặp lại nhiều lần. Không dùng `-Xms4g` trên máy thiếu tài nguyên hoặc vượt memory limit của container.

Quan trọng hơn việc “bật một cờ”, hãy xác nhận JVM chạy được **với cờ đó thực sự có hiệu lực** và workload đủ lớn để dùng nhiều node. Nếu GC/OS quyết định bỏ qua NUMA do ràng buộc phần cứng, so sánh hai cấu hình sẽ không đo được cải tiến.

### Bước 3 — Thu thập mức độ locality thật

Trên Linux, khi process vẫn đang chạy, dùng công cụ của OS:

```bash
# PID là process ID thật của ứng dụng đang thử.
numastat -p PID

# Cần quyền phù hợp; xem các virtual memory mappings và NUMA pages:
cat /proc/PID/numa_maps
```

`numastat -p` và `/proc/PID/numa_maps` giúp quan sát **phân bố trang nhớ ở các node**. Chúng không tự tách hết “heap của G1” khỏi code cache, metaspace, thư viện native, stack và phần ánh xạ khác; cần kết hợp thông tin memory mapping/JVM khi phân tích.

Kiểm tra thêm:

- **GC logs** từ `-Xlog:gc*=info` hoặc mức debug có chủ đích: các loại pause, thời gian dừng, memory occupancy, allocation pressure.
- **Linux NUMA metrics:** tỷ lệ truy cập local/remote hoặc memory placement/counters mà hệ điều hành/phần cứng cung cấp; tên counter tùy CPU.
- **CPU usage và thread migrations:** vị trí chạy của các Java/GC threads có ổn định không.
- **Throughput:** request/s hoặc transaction/s ở **cùng tải**.
- **Latency:** p50, p95, p99 end-to-end và GC pause distribution.
- **Disk/network/lock contention:** bảo đảm yếu tố khác không trở thành nút thắt che lợi ích NUMA.

Đừng chỉ đọc một dòng `UseNUMA=true` rồi kết luận “đã tối ưu thành công”. Cũng đừng chỉ nhìn `numastat` tổng của cả process rồi tuyên bố mọi object Java đều local.

### Bước 4 — Tổ chức A/B benchmark có kiểm soát

- Làm **warmup** để JIT, class loading và GC đạt trạng thái đại diện.
- Chạy nhiều lần, cân bằng thứ tự cấu hình để giảm hiệu ứng nhiệt độ/cache/tải nền.
- Giữ cùng số cores được cấp, heap size, GC options, input, process affinity/cpuset.
- Theo dõi số node, node capacity, kernel/BIOS và lịch sử nền tảng.
- Dùng dữ liệu đủ lớn để trải qua nhiều chu kỳ GC; test vài nghìn mảng trong vài mili giây không đại diện.
- Lưu log, commit, build JDK, VM flags, loại workload và kết quả median/percentile.
- Đánh giá **chi phí** CPU/memory/GC cùng với hiệu quả; không đánh đổi tính ổn định hệ thống chỉ để lấy một benchmark đẹp.

**Tiêu chí kết luận:** một cải thiện đáng tin phải thể hiện ở **metrics mục tiêu của ứng dụng**, gắn với sự thay đổi locality có bằng chứng, và lặp lại được. Nếu không có lợi ích hoặc gây hồi quy, có thể giữ cấu hình G1 mặc định/NUMA off và tập trung tối ưu bottleneck khác.

## 8. Tình huống mang lại lợi ích và tình huống không đáng bật

| Điều kiện | Kỳ vọng thực tế | Cách xử lý |
| --- | --- | --- |
| Máy nhiều NUMA nodes, heap lớn, allocation-heavy | Có cơ hội tăng local-memory access | Benchmark `-XX:+UseNUMA` cùng cấu hình đối chứng |
| GC nhiều young evacuations, object có vòng đời ngắn/vừa | Eden/Survivor locality có thể quan trọng | Xem GC phases, throughput, page placement |
| Heap vừa trong một node, thread ít di chuyển | Lợi ích có thể rất nhỏ | Đo trước, tránh bật theo thói quen |
| Một NUMA node khả dụng | Không có tối ưu cross-node đáng kể | Không khẳng định cờ sẽ tăng tốc |
| Container giới hạn mems/cpus vào một node | JVM có thể vô hiệu hóa tính năng | Kiểm tra cpuset, JVM flag/log |
| Old generation chiếm phần lớn hiệu năng | JEP 345 không bảo đảm local placement cho old | Phân tích layout, dữ liệu lâu sống, GC, application access |
| Network/DB là bottleneck | Tối ưu RAM locality khó cải thiện throughput tổng | Đo end-to-end, xử lý nút thắt chính |
| Thread liên tục chuyển node | Lợi ích locality có thể bị giảm | Kiểm tra scheduling/affinity trước khi kết luận |
| Node local thiếu RAM | OS fallback/remote allocations có thể tăng | Giám sát capacity và NUMA counters |
| Máy phát triển Windows không có topology phù hợp | Flag có thể bị vô hiệu hóa | Chỉ dùng để kiểm tra cú pháp/GC, benchmark trên Linux multi-node |

**Không có cấu hình “luôn bật NUMA cho mọi JVM”.** G1 đã được thiết kế cân bằng giữa throughput, pause time và mức sử dụng bộ nhớ. Oracle G1 tuning guide còn khuyên **bắt đầu bằng mặc định hợp lý** (có thể đặt `-Xmx`, pause goal nếu cần) và chỉ tuning khi có số liệu.

## 9. Phân biệt đúng các tối ưu JVM khác

| Tùy chọn/khái niệm | Vai trò | Không nên hiểu sai thành |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn G1 GC | Tự bật NUMA ở mọi hệ thống |
| `-XX:+UseNUMA` | Yêu cầu GC/VM tối ưu theo NUMA nếu hỗ trợ | Pin mọi thread và object |
| `-XX:-UseNUMA` | Tắt NUMA optimization cụ thể của VM | Tắt G1 hoặc tắt GC |
| `-Xms` / `-Xmx` | Heap ban đầu/tối đa | Quy định object được cấp ở node nào |
| `-XX:G1HeapRegionSize` | Điều chỉnh cỡ G1 region (khi thật sự cần) | NUMA node size hoặc OS page size |
| `-XX:+AlwaysPreTouch` | Pre-touch các trang heap lúc khởi động, tăng chi phí startup nhưng có thể ổn định runtime | Tự đảm bảo memory placement đúng node |
| `numactl --cpunodebind` | Hạn chế CPU nodes cho process Linux | Hoàn toàn tương đương `UseNUMA` |
| `numactl --membind` | Chính sách memory nodes của Linux | Bảo đảm mọi object Java ở thread-local node |
| TLAB | Khối cấp phát nhanh cho mỗi Java thread | Một NUMA node hay G1 region |
| PLAB | Khối cấp phát để GC worker copy object | Bảo đảm promotion sang Old vẫn local |
| `-Xlog:gc*=info` | Ghi thông tin GC hiện đại | Đo trực tiếp tỉ lệ remote RAM accesses |
| `-Xlog:numa*=debug` | Log về xử lý NUMA khi JVM hỗ trợ | Thay được đo page placement/latency thật |

**Đừng dùng cờ log GC cũ từ các bài viết trước unified logging.** Với Java 17+, `-Xlog` là cách ghi log được hỗ trợ để quan sát GC/NUMA. Không tự đặt `-Xmn` hoặc cố định kích thước young generation tùy tiện vì có thể phá khả năng G1 điều chỉnh pause-time mục tiêu.

### 9.1. Cân nhắc `AlwaysPreTouch` và kích thước heap

`-XX:+AlwaysPreTouch` khiến JVM chạm các trang heap khi khởi động, có thể chuyển chi phí page fault từ runtime sang startup. Trong hệ thống NUMA, thời điểm và chính sách cấp trang có thể ảnh hưởng nơi backing pages xuất hiện.

Nhưng **pre-touch không phải bảo đảmNUMA-locality**. Khi đánh giá, so sánh A/B trong cùng điều kiện `AlwaysPreTouch`, `Xms/Xmx`, transparent huge pages, scheduler và OS policy. Tương tự, `-Xms = -Xmx` có thể làm heap resize ổn định hơn trong một số workload, nhưng đổi hai cờ đó đồng thời với `UseNUMA` sẽ làm khó xác định nguyên nhân chênh lệch.

### 9.2. JFR/JMX giúp gì?

**JMX GarbageCollectorMXBean** giúp đọc tên collector và số lần/thời gian GC, **không trả node vật lý của từng Java object**. **JFR** hữu ích để theo dõi allocations, GC events, thread behavior và tải ứng dụng, nhưng **không phải API tra cứu vị trí NUMA chính xác của mọi object**. Dùng chúng cùng công cụ OS/hardware thay vì gán trách nhiệm không có trong Java SE.

## 10. Những ngộ nhận phổ biến về JEP 345

### Lỗi 1 — “Java 14 tạo API để chỉ định node khi new object”

Sai. JEP 345 cải tiến **HotSpot G1 runtime allocation**, không thêm câu lệnh Java nào tương tự `newOnNode(0)`. Ứng dụng vẫn dùng `new`, GC/OS đưa ra quyết định placement.

### Lỗi 2 — “Bật `UseNUMA` nghĩa là chắc chắn hoạt động”

Sai. Runtime có thể từ chối hoặc vô hiệu hóa dựa trên OS/topology/cpuset. **Sửa:** kiểm tra effective flags, log và page-placement metrics trên Linux.

### Lỗi 3 — “G1 đặt tất cả objects lên node của thread đầu tiên tạo nó”

Sai. Cơ chế ưu tiên local regions là best effort, thread có thể di chuyển, GC worker có thể copy object và old/humongous regions dùng chính sách khác. **Sửa:** phân biệt Eden/Survivor với Old/Humongous.

### Lỗi 4 — “NUMA chỉ là tên mới của TLAB”

Sai. TLAB giảm contention cấp phát theo thread; NUMA locality liên quan vị trí memory pages so với CPU. Hai kỹ thuật bổ sung nhau.

### Lỗi 5 — “Nếu các CPUs có nhiều cores thì chắc chắn là nhiều NUMA node”

Sai. NUMA topology không được suy ra chỉ từ số core/socket. **Sửa:** xem `lscpu` và `numactl --hardware`.

### Lỗi 6 — “NUMA always boosts throughput by 20%”

Sai. Số liệu benchmark từng được báo cáo cho một hệ thống workload cụ thể, không phải cam kết. **Sửa:** dùng A/B với workload, OS, JDK và dung lượng heap thật.

### Lỗi 7 — “Kích thước heap nhỏ vẫn được lợi như heap lớn”

Không nhất thiết. Nếu mọi dữ liệu quan trọng nằm trong một node, remote access vốn đã ít. **Sửa:** xem locality và hot set trước khi tuning.

### Lỗi 8 — “Một lần xem `java -XX:+PrintFlagsFinal` đủ chứng minh locality”

Không đủ. Flag cho biết cấu hình JVM, không đo latency và không biết page placement thật. **Sửa:** OS NUMA statistics + GC/performance metrics.

### Lỗi 9 — “Có thể dùng Windows local để xác nhận NUMA của Linux”

Không hợp lệ. G1/UseNUMA có điều kiện hỗ trợ platform và topology; ví dụ chạy trên Windows JDK24 đã kiểm chứng cho thấy `UseNUMA=false` dù yêu cầu bật. **Sửa:** chạy kiểm thử locality trên Linux multi-node có quyền truy cập các node.

### Lỗi 10 — “Bật cờ thì Old generation cũng luôn local”

Sai. Cải tiến JEP 345 tập trung young generation; Old/Humongous bố trí có mục tiêu cân bằng, không local-by-thread như Eden. **Sửa:** đọc đúng phạm vi JEP và kiểm tra dữ liệu dài sống thực.

### Lỗi 11 — “CPU/node binding lúc nào cũng cải thiện NUMA”

Không hẳn. Gắn process vào một node có thể giảm remote access nhưng làm mất cores/RAM và tăng contention hoặc khiến JVM tắt NUMA heuristics. **Sửa:** so sánh chính sách OS và JVM có kiểm soát.

### Lỗi 12 — “Có NUMA-aware GC thì không cần tối ưu code”

Sai. Lock contention, allocation pressure, cache misses, cấu trúc dữ liệu và thuật toán có thể chi phối hiệu năng. **Sửa:** profile bottleneck ứng dụng trước.

### Lỗi 13 — “Chỉ cần chạy thử vài nghìn allocations để đo sự cải thiện”

Sai. Ví dụ `G1NumaAllocationDemo` là smoke test, không đủ bộ nhớ/thời gian để đánh giá locality. **Sửa:** benchmark đủ tải và thời gian, lặp lại đo lường.

### Lỗi 14 — “Tắt `UseNUMA` đồng nghĩa tắt G1”

Sai. `-XX:-UseNUMA` chỉ tắt tối ưu NUMA; `-XX:+UseG1GC` vẫn chọn G1. Hai cờ phục vụ hai trách nhiệm riêng.

### Lỗi 15 — “G1 NUMA chỉ có trong Java 14 và không dùng được nữa”

Sai. JEP 345 là mốc **cải tiến được đưa vào từ Java 14**, không phải một tính năng preview phải gỡ bỏ. Các cờ liên quan vẫn được tài liệu lệnh `java` trong JDK hiện đại công bố; khi triển khai vẫn phải kiểm tra implementation/platform.

## 11. Checklist triển khai trên hệ thống thật

- [ ] Chỉ kích hoạt có chủ đích khi hardware/VM có nhiều NUMA nodes khả dụng.
- [ ] Đã xác minh JVM dùng **G1** và biết `UseNUMA` effective state.
- [ ] Kiểm tra CPU/node topology, cpuset và memory node policy của process/container.
- [ ] Dùng JDK vendor/build đang được hỗ trợ, không cố giữ runtime Java 14 lỗi thời.
- [ ] Thử baseline `-XX:-UseNUMA` và experiment `-XX:+UseNUMA` với cùng workload.
- [ ] Cấu hình `-Xms`/`-Xmx` hợp lý, không làm A/B bị nhiễu do heap khác.
- [ ] Có đủ RAM tại các nodes, đã đánh giá memory pressure và fallback.
- [ ] Theo dõi allocations/GC pauses/throughput/p95/p99 theo workload thật.
- [ ] Đo NUMA memory page placement/local-vs-remote bằng công cụ Linux/OS.
- [ ] Nếu dùng `AlwaysPreTouch` hoặc huge pages, giữ cùng policy giữa hai lần thử.
- [ ] Không đọc log rồi suy ra mọi object đều local; quan sát toàn bộ dữ liệu.
- [ ] Không nhầm Eden/Survivor awareness với guarantee cho Old/Humongous.
- [ ] Cân nhắc ảnh hưởng của CPU migrations, locks, I/O và các bottlenecks khác.
- [ ] Với production, rollout theo nhóm máy phù hợp và có phương án vô hiệu hóa nếu hồi quy.
- [ ] Ghi JDK build, GC flags, NUMA topology, dataset, metric và kết luận benchmark.
- [ ] Không copy số phần trăm tăng tốc của một benchmark lịch sử thành cam kết ứng dụng.

## 12. Bài tập có hướng dẫn

1. **Định nghĩa:** giải thích “local memory” và “remote memory” trong máy NUMA, tại sao độ trễ khác nhau.
2. **Mục tiêu:** nêu mục tiêu chính của JEP 345 và lý do các ứng dụng allocation-heavy trên server NUMA lớn có thể được lợi.
3. **Phạm vi:** phân biệt Eden/Survivor placement với Old/Humongous và vì sao không được khẳng định mọi object local.
4. **Mechanism:** vẽ đường đi khi Java thread trên node 0 yêu cầu bộ nhớ: CPU → region/TLAB → pages/OS.
5. **Young GC:** giải thích tại sao GC worker và PLAB/Survivor regions có liên quan tới giữ NUMA locality sau GC.
6. **Flags:** viết lệnh bật G1 và yêu cầu NUMA, rồi viết lệnh đối chứng tắt NUMA nhưng vẫn dùng G1.
7. **Effective state:** nếu command line chứa `+UseNUMA` mà JVM report `UseNUMA=false`, có thể kết luận NUMA đang bật không?
8. **Hardware:** trong container có `cpuset.mems` chỉ cho một node, tại sao thêm `UseNUMA` chưa chắc thay đổi gì?
9. **Code:** biên dịch `G1NumaAllocationDemo` bằng `--release 17`, chạy ba chế độ và kiểm tra checksum; tại sao ba stdout có thể giống nhau?
10. **Monitoring:** thiết kế A/B đo throughput, p95/p99, GC pauses, NUMA locality và CPU migrations.
11. **Performance:** nếu database/network mới là nút thắt, việc bật NUMA-aware allocation có chắc giải quyết latency không?
12. **Affinity:** nêu một trường hợp pin CPU một node giúp locality và một trường hợp nó gây thiếu tài nguyên.
13. **Heap sizing:** tại sao thay cả `Xmx` lẫn `UseNUMA` trong cùng benchmark khiến khó tìm nguyên nhân?
14. **Runtime:** G1 được chọn bằng `UseG1GC` có đồng nghĩa đã có nhiều NUMA nodes không?
15. **Production:** đề xuất một quy trình bật dần tùy chọn NUMA trên các máy Linux đủ node, với ngưỡng rollback.

**Gợi ý trả lời:** (1) memory node gần CPU thường nhanh hơn; (2) tăng cơ hội local access/giảm remote access để cải thiện hiệu năng G1; (3) young locality là trọng tâm, old không có per-thread guarantee; (4) HotSpot và OS cùng quyết định placement; (5) evacuation/copy sang Survivor cũng cần affinity; (6) `-XX:+UseG1GC -XX:+UseNUMA` và `-XX:+UseG1GC -XX:-UseNUMA`; (7) không; (8) chỉ một node khả dụng; (9) đây là tối ưu cấp phát, không đổi kết quả tính toán; (10) có workload, warmup, metric, lặp lại; (11) không; (12) đo cẩn thận giới hạn tài nguyên; (13) cần chỉ thay một biến khi A/B; (14) không; (15) canary, theo dõi, tắt nếu hồi quy.

## 13. Nguồn tài liệu đáng tin và còn liên quan

- **OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1:** mục tiêu tối ưu hiệu năng trên máy NUMA lớn: https://openjdk.org/jeps/345
- **Oracle JDK 14 Release Notes, JEP 345:** Eden/young allocations, Old/Humongous interleave và cờ `UseNUMA`: https://www.oracle.com/java/technologies/javase/14-relnote-issues.html
- **Oracle Java SE 25 `java` command reference:** `-XX:+UseG1GC`, `-XX:+UseNUMA` và cách đọc các JVM options hiện hành: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle Java SE 27 `java` command reference:** xác nhận `UseNUMA` tiếp tục được công bố trong tài liệu JDK mới: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Oracle Java SE 25 G1 GC overview:** mô hình regions, young/old, evacuation và hiện trạng G1 hiện đại: https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html
- **Oracle Java SE 25 G1 GC tuning:** bắt đầu với defaults, chọn heap/pause goal và thu thập unified GC logs: https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html
- **Sangheon Kim (OpenJDK engineer) — NUMA-Aware Memory Allocation for G1 GC:** giải thích kỹ thuật mutator allocation regions, Survivor PLAB và benchmark có bối cảnh: https://sangheon.github.io/2020/11/03/g1-numa.html
- **Linux kernel NUMA Memory Policy documentation:** tác động của policies tới việc OS chọn node đặt trang nhớ: https://www.kernel.org/doc/html/latest/admin-guide/mm/numa_memory_policy.html
- **Oracle Java SE 17 API — `GarbageCollectorMXBean`:** nhận biết collector/metrics chứ không phải physical memory page location: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

**Ghi nhớ:** NUMA-aware allocation của G1 được bổ sung từ **Java 14** nhằm cải thiện **local memory access cho Young Generation**, đặc biệt lúc cấp phát ở Eden và copy object sống sang Survivor. Tác dụng trên máy NUMA nhiều node có thể đáng kể, nhưng **chỉ là tối ưu runtime best effort**, không thay đổi semantics Java, không bảo đảm tất cả object local và không tự động tăng tốc mọi workload. Bật `UseNUMA` là bước cấu hình; **kiểm chứng effective flags, topology và performance mới là cơ sở ra quyết định triển khai**.