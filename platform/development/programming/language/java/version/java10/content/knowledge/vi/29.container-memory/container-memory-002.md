# Nhận diện bộ nhớ khả dụng trong container để chọn cấu hình JVM

## 1. Mục tiêu và phạm vi

Khi chạy Java trực tiếp trên một máy chủ, JVM có thể quan sát RAM vật lý của máy để lựa chọn một số giá trị **ergonomics** như kích thước Java heap mặc định. Trong **Docker hoặc Kubernetes**, ứng dụng lại hoạt động trong một **container** có thể chỉ được cấp một phần tài nguyên của máy chủ.

Ví dụ, node Linux có **64 GiB RAM**, nhưng container Java chỉ có **1 GiB memory limit**. Nếu JVM lấy nhầm 64 GiB làm cơ sở để chọn heap, nó có thể đặt giới hạn Java heap quá lớn so với dung lượng container thực sự được phép dùng. Hệ quả là **OOM kill của hệ điều hành** trước khi JVM kịp báo một ngoại lệ `OutOfMemoryError` bên trong Java.

**Java 10** đánh dấu bước quan trọng khi HotSpot tăng cường nhận diện tài nguyên trong Linux containers, bao gồm memory/CPU constraints và tùy chọn `-XX:+UseContainerSupport`. Khả năng này tiếp tục được phát triển và **vẫn còn hiệu lực trong các JDK hiện hành**. Đặc biệt, khả năng nhận diện **cgroup v2** được bổ sung về sau và cần dùng bản JDK có hỗ trợ phù hợp.

Bài này tập trung vào việc **nhận diện ngân sách bộ nhớ thực tế để chọn cấu hình JVM**, không phải tối ưu GC riêng lẻ. Các ví dụ chính dùng **JDK 17+**, cú pháp HotSpot đang được hỗ trợ, và không đưa các cờ phân số RAM cũ đã deprecated vào khuyến nghị.

Sau bài, bạn có thể:

1. Phân biệt RAM của host, container memory limit, memory request, memory usage và phần memory chưa được sử dụng.
2. Giải thích cách HotSpot nhận giới hạn bộ nhớ qua cgroups và khi nào kết quả có thể sai.
3. Phân biệt `-XX:MaxRAMPercentage`, `-XX:InitialRAMPercentage`, `-XX:MinRAMPercentage`, `-XX:MaxRAM`, `-Xms` và `-Xmx`.
4. Dành ngân sách cho **heap** và các phần **non-heap/native** thay vì đặt heap bằng 100% container limit.
5. Dùng `-XshowSettings:system`, `-Xlog:os+container`, `Runtime.maxMemory()`, `MemoryMXBean`, cgroup files và các chỉ số Kubernetes để kiểm chứng.
6. Phân biệt `java.lang.OutOfMemoryError` với container bị **OOMKilled**, từ đó chẩn đoán đúng.
7. Chạy ví dụ Java 17+ có một chế độ tính ngân sách bộ nhớ cho kết quả xác định và một chế độ quan sát JVM thực tế.

## 2. “Bộ nhớ khả dụng” có nhiều nghĩa

Cùng một chữ “memory available” có thể ám chỉ **nhiều tầng giới hạn và số liệu khác nhau**.

| Khái niệm | Ý nghĩa | Dùng để làm gì? |
| --- | --- | --- |
| **Host physical RAM** | RAM vật lý trên node/máy chủ | Không đủ để quyết định heap của container |
| **Container hard memory limit** | Giới hạn do cgroup/kernel thực thi đối với container | Cơ sở quan trọng để xác định ngân sách toàn tiến trình |
| **Kubernetes memory request** | Lượng bộ nhớ yêu cầu để scheduler bố trí pod | **Không phải** hard memory limit |
| **Container current memory usage** | Bộ nhớ đang được hạch toán cho cgroup | Quan sát áp lực hiện tại; không đồng nhất với Java heap used |
| **Java max heap** | Mức Java heap tối đa JVM cho phép, thường do `-Xmx` hoặc ergonomics xác định | Ngân sách chỉ dành cho Java heap |
| **Committed Java heap** | Dung lượng heap JVM đã commit | Khác max và có thể khác used |
| **Java heap used** | Dung lượng object/heap đang chiếm dụng theo JVM | Không bao gồm toàn bộ native memory |
| **Process RSS / cgroup memory usage** | Resident memory hoặc tổng hạch toán theo hệ điều hành | Cần xem khi điều tra OOM kill |
| **Free/headroom** | Khoảng còn lại sau usage và phần dự phòng | Không phải một giá trị bất biến; chịu ảnh hưởng reclaim/cache |

Ví dụ node có 64 GiB RAM và container limit 1 GiB:

~~~text
Host RAM:                   64 GiB
Container memory limit:      1 GiB
Java heap max (-Xmx):      640 MiB
Non-heap/native allowance: 256 MiB (giả định)
Safety margin:             128 MiB (giả định)
~~~

Hai khoản 256 MiB và 128 MiB chỉ là **ngân sách minh họa**, không phải quy tắc cứng cho mọi ứng dụng. Các con số phải được điều chỉnh theo thread count, metaspace, direct buffers, GC, JNI, JIT, workload, và dữ liệu đo thực tế.

**Điểm quan trọng:** container có memory limit 1 GiB không có nghĩa **Java heap** cũng được phép dùng 1 GiB. JVM còn cần bộ nhớ cho nhiều thành phần khác.

## 3. Linux cgroups thực thi memory limit

Docker và Kubernetes trên Linux sử dụng cơ chế **cgroups** để giới hạn/hạch toán tài nguyên. HotSpot cần biết các giới hạn đó thay vì chỉ nhìn tổng RAM của host.

Ở mức khái niệm:

~~~text
Linux node (64 GiB RAM)
    |
    +-- cgroup / parent hierarchy
             |
             +-- container java-api (limit = 1 GiB)
                     |
                     +-- JVM process
                     |      +-- Java heap
                     |      +-- Metaspace / class metadata
                     |      +-- Direct/native buffers
                     |      +-- Thread stacks
                     |      +-- JIT/code cache/GC data
                     |
                     +-- Khác: nếu có nhiều tiến trình cùng cgroup
~~~

Thông thường, container cgroup limit đặt trần lên **tổng tài nguyên được hạch toán** trong cgroup đó, không chỉ lên Java heap. Nếu có side process cùng cgroup, chúng cũng có thể tiêu thụ ngân sách đó. Hệ thống còn có các giới hạn cấp parent cgroup hoặc node.

Cần phân biệt **hard limit** với **usage**:

- **Hard limit** là mức trần kernel có thể thực thi.
- **Current usage** là mức tiêu thụ được hạch toán tại thời điểm đo.
- **Headroom** phụ thuộc cả memory có thể reclaim, cache và ràng buộc cgroup; không phải phép trừ đơn giản luôn dự báo chính xác có bao nhiêu byte cấp phát mới được.

### 3.1. cgroup v2: `memory.max`, `memory.current` và `memory.events`

Ở những hệ thống dùng **cgroup v2**, các interface thường gặp:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
~~~

Ý nghĩa:

| File cgroup v2 | Ý nghĩa chính | Lưu ý |
| --- | --- | --- |
| `memory.max` | Hard memory limit; có thể là số byte hoặc chuỗi `max` | `max` nghĩa là **không giới hạn ở cấp cgroup đó** |
| `memory.current` | Usage hiện tại được hạch toán cho cgroup | Bao gồm nhiều loại memory; **không bằng Java heap used** |
| `memory.events` | Bộ đếm sự kiện áp lực memory, gồm các mục OOM/OOM-kill | Dùng cùng timeline/pod status; không suy diễn từ một giá trị đơn |
| `memory.high` | Ngưỡng bảo vệ/reclaim và throttling trong cgroup v2 | **Không** đồng nghĩa hard limit `memory.max` |
| `memory.swap.max` | Giới hạn liên quan swap | Không thay thế định nghĩa `memory.max` |

Trên cgroup v2, `memory.max` có thể chứa:

~~~text
1073741824
~~~

Tức **1.073.741.824 byte = 1 GiB = 1.024 MiB**.

Nếu file ghi:

~~~text
max
~~~

thì **không có giới hạn tại cấp đó**, nhưng có thể vẫn có parent cgroup hoặc giới hạn host. Đừng coi `max` là số 0 hay là bằng RAM host.

Các file ở `/sys/fs/cgroup` ở trên là **đường dẫn phổ biến trong container có cgroup v2 mount ở root**, không bảo đảm có mặt đúng vị trí trên mọi runtime, phiên bản OS hoặc namespace. Muốn truy vết chính xác phải xét `/proc/self/cgroup`, `/proc/self/mountinfo`, và hierarchy của tiến trình.

### 3.2. cgroup v1: đường dẫn và ý nghĩa khác

Trên hệ thống còn dùng **cgroup v1**, thường có các file như:

~~~bash
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
~~~

Cấu trúc mount có thể khác. Một số môi trường biểu diễn trạng thái **không có hard limit** bằng số sentinel rất lớn, không phải một mức RAM sử dụng được thực sự.

**Không** tự làm logic cấu hình heap theo kiểu: “đọc file đầu tiên thấy tên memory.limit, parse thành long và chia 4”. Nó có thể sai nếu dùng v2, có parent limit, file path khác, không có quyền đọc, hoặc gặp giá trị sentinel.

**Cách an toàn hơn:** để HotSpot bản phù hợp đọc cgroups, rồi dùng công cụ JVM kiểm chứng. Chỉ đọc cgroup files trực tiếp như một công cụ chẩn đoán và khi cần đối chiếu với runtime/container.

## 4. Java 10 tới JDK hiện đại: container awareness hoạt động ra sao?

Từ **JDK 10**, HotSpot nhận diện tốt hơn bộ nhớ và CPU của Linux containers. Tùy chọn chính:

~~~text
-XX:+UseContainerSupport
~~~

Với các bản HotSpot Linux có hỗ trợ, tùy chọn này **được bật mặc định**. Nó cho phép JVM xét container limits trong các quyết định ergonomics như heap sizing và số CPU hữu dụng.

Để **tắt nhận diện container**:

~~~text
-XX:-UseContainerSupport
~~~

**Không khuyến nghị tắt trong production một cách vô thức**. Trên host 64 GiB RAM nhưng container limit 1 GiB, việc bỏ qua container có thể khiến JVM sizing theo host và cấu hình không phù hợp với giới hạn thực.

### 4.1. cgroup v2 phụ thuộc phiên bản JDK

Nhận diện container không có nghĩa **mọi phiên bản HotSpot đều hiểu mọi phiên bản cgroups**.

- Hỗ trợ Linux container/cgroup v1 đã có từ các JDK trước và được cải thiện ở **JDK 10**.
- Hỗ trợ nhận diện **cgroup v2** xuất hiện từ các bản JDK mới hơn (OpenJDK/HotSpot **JDK 15 trở lên**); các bản JDK 8/11 được backport vào những update release được xác định rõ.
- Kubernetes hiện khuyến nghị dùng Java runtime có hỗ trợ cgroup v2 đầy đủ nếu node sử dụng cgroup v2. Không được suy luận rằng một JDK 10 nguyên bản tự động hiểu đầy đủ cgroup v2.
- Phạm vi hỗ trợ cụ thể còn phụ thuộc **vendor, update build và kiến trúc**; hãy kiểm tra runtime hiện được triển khai.

Tài liệu Kubernetes nêu các mốc tham khảo cho OpenJDK/HotSpot như **JDK 15+**, **11.0.16+**, **8u372+** đối với cgroup v2. Điều này là một lý do vận hành để dùng JDK hiện hành, không nên cố dùng bản Java cũ chỉ vì một máy thử nghiệm từng chạy được.

### 4.2. Nhận diện không đồng nghĩa heap tự bằng giới hạn container

Khi container limit là 1 GiB, HotSpot có thể nhận đúng 1 GiB là cơ sở memory sizing, nhưng vẫn dùng quy tắc **ergonomic heap percentage** để tính **max heap**.

Ví dụ JDK 17/25 tài liệu hóa giá trị mặc định `MaxRAMPercentage` là khoảng **25%** cho các trường hợp thông dụng; với 1 GiB limit, max heap mặc định có thể vào khoảng **256 MiB**, không phải 1 GiB.

Tuy nhiên không mặc định rằng mọi bản JVM/small container/option đều cho đúng 256 MiB: các heuristic, alignment, tính năng GC và quy tắc special-case cho small heaps có thể thay đổi kết quả thực tế.

**Luôn kiểm tra max heap được JVM chọn**, không chỉ tính theo một giá trị mặc định trong tài liệu.

## 5. Các cờ HotSpot cần phân biệt

| Cờ | Nó điều khiển gì? | Ghi nhớ |
| --- | --- | --- |
| `-XX:+UseContainerSupport` | Cho phép JVM xét tài nguyên container khi được hỗ trợ | Mặc định bật trên HotSpot Linux hỗ trợ |
| `-XX:-UseContainerSupport` | Tắt container awareness | Dễ gây chọn heap/CPU sai trong container |
| `-XX:MaxRAMPercentage=p` | Tỷ lệ memory sizing base dùng để chọn **max Java heap** | **Không** phải tỷ lệ của toàn process RSS |
| `-XX:InitialRAMPercentage=p` | Tỷ lệ memory base dùng để chọn **initial heap** | Khác max heap |
| `-XX:MinRAMPercentage=p` | Tỷ lệ dùng cho **max heap trong trường hợp small heaps** | Tên “Min” dễ gây hiểu nhầm |
| `-XX:MaxRAM=...` | Thay cơ sở memory mà JVM dùng cho heap ergonomics | **Không** phải toàn bộ bộ nhớ mà process được phép sử dụng |
| `-Xmx...` | Đặt rõ **maximum Java heap size** | Thường ưu tiên so với heap maximum tự tính theo percentage |
| `-Xms...` | Đặt rõ **initial Java heap size** | Có thể làm footprint ban đầu cao |
| `-XX:MaxDirectMemorySize=...` | Giới hạn một số allocation NIO direct buffer | Không phải trần mọi native allocation |
| `-XX:MaxMetaspaceSize=...` | Giới hạn class metadata metaspace | Không phải trần toàn non-heap |
| `-XX:ActiveProcessorCount=n` | Override CPU count JVM dùng cho các quyết định như GC thread pools | Là cờ **CPU**, không trực tiếp đặt memory limit |

### 5.1. `MaxRAMPercentage`: tỉ lệ của memory sizing base

Ví dụ:

~~~bash
java -XX:MaxRAMPercentage=62.5 -jar app.jar
~~~

Với container memory limit **1.024 MiB** và HotSpot nhận diện đúng giới hạn đó, giá trị `62.5` gợi ý một max heap khoảng:

~~~text
1024 MiB × 62.5% = 640 MiB
~~~

Đó là **kết quả dự kiến trước các chi tiết ergonomics/alignment**, không phải cam kết số byte chính xác hoặc một mức tổng RAM tiêu thụ tối đa. Nên dùng `-XshowSettings:vm` hoặc `Runtime.maxMemory()` để kiểm chứng max heap thật.

**Không** dùng `-XX:MaxRAMPercentage=100` chỉ vì container có 1 GiB rồi cho rằng process sẽ an toàn: **100% memory budget dành cho heap** có thể để quá ít chỗ cho thread stacks, metaspace, code cache, native memory và phần overhead khác.

### 5.2. `MinRAMPercentage` không đặt “heap tối thiểu”

Dù tên bắt đầu bằng **Min**, cờ `-XX:MinRAMPercentage` **không phải** min heap size. Nó giúp JVM tính **maximum heap** cho trường hợp rất ít RAM (theo tài liệu Oracle, heap nhỏ cỡ 125 MB).

Nếu cần kiểm soát initial heap, dùng `-Xms` hoặc `InitialRAMPercentage`, không suy luận từ `MinRAMPercentage`.

Trong container rất nhỏ, nên xác minh kết quả thay vì áp tỷ lệ 25% thông thường một cách máy móc.

### 5.3. `-Xmx` và `MaxRAMPercentage` không nên dùng như hai giới hạn cộng dồn

~~~bash
java -Xmx640m -XX:MaxRAMPercentage=50 -jar app.jar
~~~

Cách cấu hình trên **không có nghĩa** Java heap bị giới hạn bởi cả hai con số hay có một “trần dự phòng” tự động. Khi `-Xmx` được chỉ định tường minh, nó điều khiển max heap, thay vì phải tính max tự động từ `MaxRAMPercentage`.

**Chọn một chính sách rõ ràng:**

- **Fixed heap:** `-Xmx640m`, phù hợp deployment có memory limit cố định.
- **Proportional heap:** `-XX:MaxRAMPercentage=62.5`, phù hợp image dùng nhiều memory limits nhưng cần điều chỉnh theo tỷ lệ.
- Nếu cần cả initial và maximum, thiết kế `-Xms`/`-Xmx` hoặc các cờ tương ứng rõ ràng, sau đó kiểm chứng bằng JVM thực.

### 5.4. `-XX:MaxRAM` không phải giới hạn toàn tiến trình

Ví dụ:

~~~bash
java -XX:MaxRAM=1g -XX:MaxRAMPercentage=50 -jar app.jar
~~~

Nó điều chỉnh **cơ sở RAM cho heap sizing** trong HotSpot. Nó không thay đổi cgroup hard limit do kernel áp dụng. Đồng thời, nó không thể thay Docker `--memory` hay Kubernetes `resources.limits.memory`.

Đừng dùng `MaxRAM` để “lách” memory limit của container; JVM vẫn chịu ràng buộc của OS.

## 6. Tính ngân sách heap: còn phải dành chỗ cho gì?

Một JVM process không chỉ có heap. Các thành phần ngoài heap đáng kể:

| Nhóm | Nguồn tiêu thụ | Dấu hiệu/quan sát |
| --- | --- | --- |
| **Metaspace** | Class metadata, framework, class loaders | `MemoryMXBean` non-heap, `jcmd VM.metaspace` nếu hỗ trợ |
| **Code cache/JIT** | Mã máy JIT compile và compiler state | JVM code cache metrics/JFR/NMT |
| **Thread stacks** | Java/native thread stacks | Số thread và stack size; `-Xss` là một yếu tố |
| **Direct buffers** | `ByteBuffer.allocateDirect`, network/NIO | BufferPoolMXBeans, direct memory monitoring |
| **GC bookkeeping** | Data structures của collector, remembered sets, bitmap | NMT/GC diagnostics |
| **JNI/native libraries** | malloc, native allocators, compression, crypto, database drivers | NMT, OS metrics và công cụ native |
| **Mapped memory/file cache** | File mappings, shared libraries, page cache | RSS/cgroup memory usage tùy cách hạch toán |
| **Cùng cgroup có tiến trình khác** | Agent, helper process nếu chạy chung cgroup | Theo dõi cgroup-level usage |

Lượng non-heap không cố định: hàng nghìn thread và direct buffers lớn có thể cần ngân sách rất khác một dịch vụ ít thread/ít I/O.

### 6.1. Mô hình ngân sách sơ bộ

~~~text
containerLimit
    >= peakJavaHeapCommitted
     + peakJVMNativeAndNonHeap
     + otherCgroupUsage
     + safetyMargin
~~~

Công thức này là **mô hình lập ngân sách**, không phải một định luật đẳng thức byte: container hạch toán một số loại page cache/kernel, các trang memory mapping có chia sẻ, committed heap khác RSS, và thành phần có thể thay đổi theo tải.

Ví dụ limit **1 GiB**:

~~~text
Container memory limit:  1024 MiB
Non-heap/native budget:   256 MiB  (giả định sau đo đạc)
Safety margin:            128 MiB  (giả định)
-----------------------------------------------
Heap budget:              640 MiB
Heap budget percent:      62.5%
~~~

Những mức **256/128 MiB** chỉ là minh họa cách nghĩ. Không áp dụng nguyên cho mọi dịch vụ. Nếu service dùng Netty direct buffers lớn, hàng trăm thread hoặc nhiều native libraries, ngân sách non-heap có thể phải lớn hơn rất nhiều.

### 6.2. Vì sao không set `-Xms = -Xmx` theo thói quen?

~~~bash
java -Xms640m -Xmx640m -jar app.jar
~~~

Chính sách này phù hợp với **một số workload** cần heap đã sẵn sàng và có thể chấp nhận footprint ban đầu. Nhưng đặt initial heap quá cao có thể làm tăng committed/physical memory pressure ngay từ lúc khởi động và hạn chế sự linh hoạt của ứng dụng khi chạy trong container nhỏ.

Nếu workload không cần heap luôn ở maximum, hãy đo GC và process RSS trước khi quyết định bằng nhau. **Không coi initial heap bằng max heap là yêu cầu bắt buộc của Docker/Kubernetes.**

## 7. Ví dụ Java 17+ hoàn chỉnh: tính ngân sách và xem cấu hình thật

Chương trình gồm hai chế độ:

- **`demo`**: tính một ngân sách giả định 1 GiB, đầu ra **cố định**.
- **`inspect`**: đọc thông tin JVM đang chạy, đầu ra **phụ thuộc máy/container/JDK**.

Lưu tên file **ContainerMemoryProbe.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.Locale;

public class ContainerMemoryProbe {
    private static final long MIB = 1024L * 1024;

    private static long mib(long bytes) {
        return bytes < 0 ? -1 : bytes / MIB;
    }

    private static void demo() {
        long containerLimitMiB = 1024;
        long estimatedNonHeapMiB = 256;
        long safetyMarginMiB = 128;

        long heapBudgetMiB =
                containerLimitMiB
                - estimatedNonHeapMiB
                - safetyMarginMiB;

        System.out.println("container limit: "
                + containerLimitMiB + " MiB");
        System.out.println("non-heap budget: "
                + estimatedNonHeapMiB + " MiB");
        System.out.println("safety margin: "
                + safetyMarginMiB + " MiB");
        System.out.println("heap budget: "
                + heapBudgetMiB + " MiB");

        System.out.printf(
                Locale.ROOT,
                "heap budget percent: %.1f%%%n",
                100.0 * heapBudgetMiB / containerLimitMiB
        );
    }

    private static void inspect() {
        Runtime runtime = Runtime.getRuntime();
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        System.out.println("runtime.maxMemory: "
                + mib(runtime.maxMemory()) + " MiB");
        System.out.println("runtime.totalMemory: "
                + mib(runtime.totalMemory()) + " MiB");
        System.out.println("runtime.freeMemory: "
                + mib(runtime.freeMemory()) + " MiB");
        System.out.println("mxbean.heap.max: "
                + mib(memory.getHeapMemoryUsage().getMax())
                + " MiB");
        System.out.println("mxbean.nonHeap.used: "
                + mib(memory.getNonHeapMemoryUsage().getUsed())
                + " MiB");
        System.out.println("availableProcessors: "
                + runtime.availableProcessors());
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "demo" : args[0];

        if ("demo".equals(mode)) {
            demo();
        } else if ("inspect".equals(mode)) {
            inspect();
        } else {
            throw new IllegalArgumentException(
                    "Use demo or inspect"
            );
        }
    }
}
~~~

Biên dịch:

~~~bash
javac ContainerMemoryProbe.java
~~~

Chạy phép tính minh họa:

~~~bash
java ContainerMemoryProbe demo
~~~

**Stdout chính xác của chế độ `demo`, đã kiểm chứng trên JDK:**

~~~text
container limit: 1024 MiB
non-heap budget: 256 MiB
safety margin: 128 MiB
heap budget: 640 MiB
heap budget percent: 62.5%
~~~

Đây là **mô hình budget được hard-code để học**, không có khả năng tự đọc giới hạn Docker/Kubernetes. Nó giúp hiểu logic chọn heap **sau khi** bạn đã xác minh memory limit và non-heap consumption thực tế.

Chạy chế độ quan sát JVM:

~~~bash
java ContainerMemoryProbe inspect
~~~

Bạn sẽ nhận các nhãn `runtime.maxMemory`, `runtime.totalMemory`, `runtime.freeMemory`, `mxbean.heap.max`, `mxbean.nonHeap.used`, `availableProcessors`. Giá trị **thay đổi giữa runtime**, vì vậy bài này **không bịa một stdout cố định** cho chế độ `inspect`.

### Đọc đúng thông tin từ Java

| API | Dùng để đọc | Không được hiểu thành |
| --- | --- | --- |
| `Runtime.maxMemory()` | Max Java heap theo JVM hiện tại | Container memory limit |
| `Runtime.totalMemory()` | Heap hiện đã được JVM cấp phát/committed theo Runtime API | Tổng RAM host/container |
| `Runtime.freeMemory()` | Phần heap trống **bên trong heap đã cấp phát** | RAM còn trống trong container |
| `MemoryMXBean.getHeapMemoryUsage().getMax()` | Giới hạn heap được báo qua MXBean | Max RSS của tiến trình |
| `getNonHeapMemoryUsage().getUsed()` | Bộ nhớ non-heap **JVM quản lý và được MXBean báo cáo** | Tổng mọi native malloc/JNI/cgroup usage |
| `Runtime.availableProcessors()` | Số CPU JVM quan sát | Dung lượng RAM hoặc container memory limit |

Một số pool có `MemoryUsage.getMax() == -1` khi không xác định trần. Đó không phải `-1 MiB` thực; chương trình dùng phép `mib` trả -1 như sentinel và không coi đó là giới hạn tài nguyên.

Chỉ dùng một `MemoryMXBean` để suy ra **non-heap budget toàn bộ JVM** là không đủ. Muốn có bức tranh memory đầy đủ, kết hợp OS/cgroup, NMT, direct buffers, thread stacks và dữ liệu thực nghiệm.

## 8. Xem HotSpot phát hiện container thế nào

### 8.1. Kiểm tra launcher settings

Trong Linux container dùng JDK hỗ trợ:

~~~bash
java -XshowSettings:system -version
java -XshowSettings:vm -version
~~~

- `-XshowSettings:system` giúp hiển thị thông tin hệ thống/container trên các runtime hỗ trợ.
- `-XshowSettings:vm` giúp xem VM settings, đặc biệt **Max. Heap Size** mà JVM chọn.

Trong từng bản JDK, cách trình bày có thể khác. Nếu runtime không nhận container, thông tin system có thể thiếu hoặc không đúng cgroup limit; cần kết hợp log và kiểm tra cgroup từ Linux.

### 8.2. Log container detection

~~~bash
java -Xlog:os+container=debug -version
~~~

Nếu cần chi tiết hơn để chẩn đoán:

~~~bash
java -Xlog:os+container=trace -version
~~~

Thông tin có thể đề cập cgroup version, memory limit, CPU quota và các bước detection. **Không dùng một chuỗi log duy nhất làm điều kiện chung cho mọi JDK** vì cấu trúc thông báo thay đổi theo implementation/version.

Logging ở mức trace nên dùng **tạm thời khi điều tra**, không phải cấu hình production mặc định.

### 8.3. Xem các JVM flags được chọn

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Trong danh sách có thể tìm:

~~~text
UseContainerSupport
MaxRAMPercentage
InitialRAMPercentage
MinRAMPercentage
MaxRAM
InitialHeapSize
MaxHeapSize
ActiveProcessorCount
~~~

Các flags được hiển thị với giá trị hiện tại và nguồn thiết lập tùy JDK. Đừng nhầm **giá trị cờ mặc định `MaxRAMPercentage`** với **max heap thực tế** khi `-Xmx` đã được thiết lập.

Trên hệ thống có `jcmd`, có thể xem một JVM đang chạy:

~~~bash
jcmd 1 VM.flags
jcmd 1 GC.heap_info
~~~

Ở đây `1` chỉ là ví dụ về PID **nếu JVM thực sự có PID 1 trong container**; không giả định PID đó luôn đúng. JVM chạy trong Docker thường là PID 1 khi không có init wrapper, nhưng với Kubernetes hoặc launcher/script thì PID có thể khác.

## 9. Thử trong Docker với memory limit cụ thể

Ví dụ trên máy có Docker và một image **Eclipse Temurin JDK 21**:

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk java -XshowSettings:system -XshowSettings:vm -version
~~~

**Kỳ vọng định tính** trên Linux host + container runtime được hỗ trợ:

- JVM có cơ hội quan sát memory hard limit khoảng **1 GiB** thay vì toàn bộ RAM host.
- VM settings in ra **max heap được chọn**, thường nhỏ hơn 1 GiB do JVM phải có ngân sách non-heap.
- Không nên sao chép một giá trị max heap cụ thể từ máy này sang mọi máy khác mà không kiểm tra.

Thử chọn max heap theo tỷ lệ:

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk java -XX:MaxRAMPercentage=62.5 -XshowSettings:vm -version
~~~

Nếu memory sizing base được xác định là 1 GiB, max heap kỳ vọng ở **quanh 640 MiB**, có thể có khác biệt nhỏ do heap alignment/ergonomics.

So với `-Xmx` cố định:

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk java -Xmx640m -XshowSettings:vm -version
~~~

Hai lệnh có thể cho **mức heap gần tương đương** với memory limit 1 GiB. Nhưng nếu deployment tăng limit container lên 2 GiB, chính sách **percentage** có thể tăng max heap theo limit, còn chính sách **fixed -Xmx640m** vẫn giữ 640 MiB.

### Không dùng disable container awareness làm ví dụ production

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk java -XX:-UseContainerSupport -XshowSettings:vm -version
~~~

Lệnh trên chỉ **phù hợp để điều tra sự khác biệt** giữa host-based và container-based sizing. Trên host nhiều RAM, JVM có thể chọn default heap vượt quá ngân sách container nếu bỏ qua cgroup. **Không lấy nó làm startup flag cho ứng dụng thật**.

### Hạn chế của thí nghiệm

Các lệnh `java -version` không tạo workload memory thực. Chúng chỉ chứng minh **những settings JVM đã tính tại khởi động**, không chứng minh container chịu tải lớn vẫn tránh được OOM kill. Một phép kiểm thử sản xuất cần có workload, bộ nhớ native, thread count, GC và metrics tương đương ứng dụng thực tế.

## 10. Kubernetes: request không bằng limit

Một manifest minh họa:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: container-memory-probe
spec:
  restartPolicy: Never
  containers:
    - name: java
      image: eclipse-temurin:21-jdk
      command:
        - java
        - -XshowSettings:system
        - -XshowSettings:vm
        - -version
      resources:
        requests:
          memory: "512Mi"
        limits:
          memory: "1Gi"
~~~

**Giải thích:**

- `requests.memory: "512Mi"` là lượng tài nguyên dùng cho **scheduler** và quản lý scheduling/QoS.
- `limits.memory: "1Gi"` là **hard memory limit** do cgroup/kernel thực thi (theo chính sách runtime).
- JVM nên nhìn giới hạn container phù hợp với **1 GiB** nếu được container runtime/JDK hỗ trợ, **không lấy 512Mi làm hard limit** chỉ vì đó là request.
- Manifest chỉ chạy lệnh in settings rồi thoát, không phải deployment phục vụ HTTP. Để đo Java service thật, dùng image/JAR và khối resources tương ứng.
- Nếu không khai báo `limits.memory`, có thể container không có hard limit riêng hoặc bị áp default qua `LimitRange`/admission policies. Không tự suy ra limit bằng request.

Kubernetes thực thi memory limit theo dạng **reactive OOM killing**: kernel có thể kết thúc container khi bộ nhớ chịu áp lực; không phải một bộ kiểm tra luôn ngăn ngay từng lệnh cấp phát vượt một ngưỡng byte.

### MiB và MB dễ bị nhầm

- **1 GiB** = 1024 MiB = 1.073.741.824 byte.
- **1 GB** = 1000 MB = 1.000.000.000 byte.
- Trong Kubernetes, `Mi` và `Gi` là đơn vị nhị phân; `M`, `G` là đơn vị thập phân.
- Trong các phép tính Java dùng `1024 * 1024` nên ghi **MiB**, không gắn nhãn MB chung chung.

Việc lẫn 1G/1Gi có thể làm tính nhầm ngân sách dự phòng. Với giới hạn chặt, hãy đọc **byte value thực tế** từ cgroups hoặc Kubernetes API thay vì diễn giải nhãn theo cảm tính.

## 11. Xử lý cgroup không giới hạn hoặc gặp giới hạn cấp trên

Không phải mọi container đều có `memory.max` bằng một số nhỏ.

Các tình huống:

1. Container không có hard limit → `memory.max` ở cgroup tương ứng có thể là `max`.
2. Container chạy trong parent cgroup có giới hạn thấp hơn → effective budget có thể chịu **ràng buộc từ parent**.
3. Cgroup bị hạch toán memory cao do page cache/file-backed pages → `memory.current` lớn không nhất thiết tương ứng toàn bộ với private RSS của JVM.
4. Node có memory pressure hoặc swap policy riêng → ứng dụng có thể bị áp lực dù heap chưa đầy.
5. Container sử dụng nhiều process trong cùng cgroup → tổng hạch toán bao gồm nhiều thành phần, không chỉ một `java`.

**Kết luận:** không có một cách đọc “`memory.max` trừ `memory.current` = RAM chắc chắn còn cấp phát được cho JVM” trong mọi trường hợp. Reclaimable cache, parent limits, chính sách swap, file-backed mapping, overcommit và trạng thái hệ thống đều làm bài toán phức tạp hơn.

Dùng cgroup files để hiểu **đường đi của giới hạn**, JVM settings để hiểu **heap đã chọn**, OS metrics để hiểu **usage**, và test thực tế để đánh giá **headroom**.

## 12. OOMKilled khác `OutOfMemoryError` của Java

Hai tình huống thường bị nhập nhằng:

| Tình huống | Ai phát hiện/ra quyết định? | Dấu hiệu thường gặp |
| --- | --- | --- |
| **Java heap OOME** | JVM không cấp phát được object trong heap | `java.lang.OutOfMemoryError: Java heap space` |
| **Metaspace OOME** | JVM không đáp ứng allocation class metadata | `java.lang.OutOfMemoryError: Metaspace` |
| **Direct buffer OOME** | Runtime/library không thể cấp phát NIO direct buffer theo giới hạn/quy tắc | `OutOfMemoryError: Cannot reserve ... direct buffer memory` (text tùy JDK) |
| **Native allocation OOME** | JVM/native allocator không lấy được bộ nhớ | Có thể xuất hiện native OOME hoặc JVM fatal error |
| **Container OOM kill** | Linux kernel/cgroup OOM machinery | Kubernetes `reason: OOMKilled`, exit 137 thường gặp |

**Không phải mọi exit code 137 đều chứng minh OOMKilled**, vì 137 cũng tương ứng việc bị SIGKILL do nguyên nhân khác. Cần kiểm tra pod termination reason, container events/cgroup counters và node conditions.

### Case A — `-Xmx` thấp, container còn headroom

Nếu `-Xmx=256m` và ứng dụng cần giữ 400 MiB object Java, JVM có thể ném **Java heap space** dù cgroup limit là 1 GiB và native memory vẫn còn. Tăng heap có thể giúp, nhưng phải xác định đối tượng sống có hợp lệ hay là leak.

### Case B — heap phù hợp nhưng native tăng mạnh

Nếu `-Xmx=640m`, một thư viện tạo direct buffers lớn và nhiều thread, tổng cgroup usage có thể vượt 1 GiB. Container bị **OOMKilled** mà không có Java heap OOME. Giảm `-Xmx` hoặc kiểm soát native/direct/thread footprint có thể hiệu quả hơn tăng heap.

### Case C — JVM không nhận đúng cgroup v2

Trên một JDK không hỗ trợ đầy đủ cgroup v2, JVM có thể nhìn bộ nhớ host thay vì container limit, dẫn tới tính heap ergonomics quá lớn. Giải pháp nên ưu tiên **nâng runtime lên bản hỗ trợ**, hoặc cấu hình heap rõ ràng `-Xmx` như biện pháp quản trị cần thiết, chứ không dựa vào cờ container awareness của một bản JDK quá cũ.

## 13. Công cụ quan sát memory ngoài heap

### 13.1. Native Memory Tracking (NMT)

Nếu cần điều tra memory do JVM quản lý ở mức native, khởi động với:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx640m -jar app.jar
~~~

Khi process chạy:

~~~bash
jcmd 1 VM.native_memory summary
~~~

Dùng PID thực thay vì 1 nếu JVM không chạy ở PID 1. NMT có overhead và **không bao phủ mọi allocation của thư viện native bên thứ ba**. Nó giúp phân loại những phần memory do HotSpot quản lý như heap, class, thread, code, GC, compiler, internal, v.v.

### 13.2. Direct buffer pools

Trong code hoặc JMX, `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` có thể cung cấp thông tin của các buffer pools như `direct` hoặc `mapped` khi runtime hỗ trợ. Nhưng số liệu này không nhất thiết bao quát mọi loại native allocation hoặc các thư viện phân bổ ngoài đường NIO thông thường.

Giới hạn `-XX:MaxDirectMemorySize` có thể hữu ích với NIO direct buffers, **không phải** một `-Xmx` thứ hai cho mọi native memory.

### 13.3. Metrics của OS/Kubernetes

Dùng các công cụ phù hợp:

~~~bash
kubectl describe pod container-memory-probe
kubectl top pod container-memory-probe
~~~

Manifest ở phần 10 là pod ngắn hạn: lệnh `kubectl top` có thể **không có dữ liệu** sau khi pod kết thúc. Đối với ứng dụng thật, dùng pod/service còn chạy để thu các mẫu liên tiếp.

Đồng thời đối chiếu:

- Cgroup `memory.current`, `memory.events`.
- Process RSS/PSS khi cần phân tích resident memory.
- Bộ nhớ cache/reclaimable và node memory pressure.
- Container restart count/OOMKilled reason.
- Heap used/committed/max từ JVM.
- Native memory breakdown và số thread/direct buffers.

**Không trộn metrics** như `container_memory_working_set_bytes`, RSS và `Runtime.totalMemory()` thành một đại lượng nếu không hiểu cách chúng được tính. Mỗi nguồn bao phủ một tập memory khác nhau.

## 14. Quy tắc lựa chọn `-Xmx`/percentage theo workload

Chọn một ngân sách **trước khi** quyết định cờ.

### Bước 1 — xác nhận hard limit

- Trong Docker: xem `--memory`/container inspect và cgroup.
- Trong Kubernetes: xem `resources.limits.memory` **sau khi** mọi admission/default policies áp dụng.
- Xác nhận cgroup v1/v2 và JDK có nhận ra không.
- Nếu không có giới hạn rõ ràng, không tự coi memory request là limit.

### Bước 2 — đo non-heap/native khi tải đại diện

Đo ít nhất:

- Thread count/stack footprint.
- Metaspace/class loading.
- Direct buffers, Netty/IO/native allocations.
- Code cache, GC, compiler.
- NMT breakdown và process/container usage.
- Peak usage ở startup, warm-up, traffic spike và shutdown.

Không chỉ đo tại thời điểm idle.

### Bước 3 — chọn margin và heap budget

Công thức minh họa:

~~~text
heapBudget = memoryLimit - measuredNonHeapPeak - otherUsage - safetyMargin
~~~

Nếu kết quả không dương, **deployment không đủ ngân sách** cho cấu hình này; cần giảm tải/footprint, hạn chế thread/direct/cache hoặc tăng memory limit thay vì cố đặt heap.

Margin không có tỷ lệ duy nhất đúng cho mọi service. Một ứng dụng cực ít native memory có thể dùng tỷ lệ heap cao hơn; một ứng dụng dùng nhiều direct buffers có thể phải dùng tỷ lệ thấp hơn đáng kể.

### Bước 4 — chọn phương án vận hành

**Fixed heap:**

~~~bash
java -Xmx640m -jar app.jar
~~~

**Proportional heap:**

~~~bash
java -XX:MaxRAMPercentage=62.5 -jar app.jar
~~~

**Kiểm chứng:**

~~~bash
java -XshowSettings:vm -XX:MaxRAMPercentage=62.5 -version
~~~

Cả hai cách đều cần kiểm tra **RSS/GC/latency/OOM** sau khi chạy đúng workload. Đừng ép JVM dùng đúng 640 MiB nếu bản thân service cần 700 MiB live objects; trước tiên phải sửa yêu cầu memory hoặc ứng dụng.

## 15. Lưu ý khi thay đổi memory limit của container

Cgroup limit có thể được cấu hình lại bởi orchestrator/kernel, nhưng **max heap đã được JVM tính tại lúc khởi động** thường không tự co giãn theo từng lần thay đổi limit runtime.

Vì vậy:

- Tăng limit container từ 1 GiB lên 2 GiB **không bảo đảm** `Runtime.maxMemory()` tự tăng tương ứng trong JVM đang chạy.
- Giảm limit xuống dưới tổng memory process đang sử dụng có thể dẫn tới áp lực/OOM kill ngay cả khi JVM chưa kịp điều chỉnh.
- Khi thay đổi memory limit đáng kể, thường nên **khởi động lại/deploy lại JVM** và xác nhận heap sizing/cgroup detection từ đầu.
- Tương tự, một deployment dùng cờ `-Xmx640m` tường minh **sẽ không tự tăng heap** chỉ vì node có thêm RAM.

Đừng dựa vào hot-resize cgroups như một giải pháp thay cho kế hoạch resource requests/limits và capacity planning có kiểm soát.

## 16. CPU limit có liên quan gián tiếp đến memory

Dù bài học tập trung vào memory, container CPU limits cũng ảnh hưởng JVM ergonomics và vận hành GC:

- `Runtime.availableProcessors()` có thể phản ánh số CPU/quota mà JVM nhận.
- Số GC workers, JIT/compiler threads và các thread pools chịu ảnh hưởng trực tiếp/gián tiếp từ số CPU.
- CPU throttling có thể khiến GC hoặc application xử lý chậm, tăng hàng đợi/retention và tạo áp lực memory.
- `-XX:ActiveProcessorCount=n` thay số CPU JVM dùng cho những quyết định đó, **không thay memory hard limit**.

Không đọc `availableProcessors()` rồi suy ra được RAM; **CPU quota và memory limit là hai nguồn cgroup khác nhau**. Khi tăng heap để giảm GC mà quên CPU quota rất chặt, GC không nhất thiết kịp đáp ứng workload.

## 17. Ma trận kiểm tra ở CI/staging

| Tình huống | Cấu hình | Điều cần xác minh |
| --- | --- | --- |
| Container limit 1 GiB | Không đặt `-Xmx` | JVM nhận container limit, max heap được tính hợp lý |
| Container limit 1 GiB | `MaxRAMPercentage=62.5` | Max heap quanh 640 MiB, vẫn đủ non-heap headroom |
| Container limit 1 GiB | `-Xmx640m` | Max heap cố định dù tỷ lệ khác |
| Container limit 2 GiB | `MaxRAMPercentage=62.5` | Max heap có thể tăng theo memory base mới |
| Container limit 2 GiB | `-Xmx640m` | Max heap vẫn 640 MiB |
| Kubernetes request 512Mi / limit 1Gi | Có container awareness | Không hiểu request 512Mi là hard limit |
| cgroup v2 | JDK 17/21+ | `memory.max` được JVM nhận diện đúng |
| Không đặt hard limit | cgroup `max` hoặc giới hạn từ parent | Không tự chọn một “limit” tưởng tượng |
| Native buffer/threads tăng | Heap used không quá cao | Theo dõi RSS/cgroup và OOMKilled |
| Node CPU throttling | Memory limit không đổi | Tách nguyên nhân GC chậm và backlog |
| Giảm container limit khi JVM còn chạy | Cấu hình động | Không giả định heap tự co ngay |
| Startup với `-XX:-UseContainerSupport` | **Chỉ dành cho QA** | Nhìn thấy khác biệt nhưng không chọn làm cấu hình production |

Nên ghi thêm **JDK vendor, update build, kernel/cgroup version, container runtime, image digest, launch flags** vào báo cáo kiểm thử. Khác biệt giữa JDK 17 và 25 không nên được giải thích chỉ bằng một giá trị heap mặc định.

## 18. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Host có 64 GiB, container Java được dùng 64 GiB.” | Hard limit container có thể chỉ 1 GiB. | Xác minh cgroup/manifest. |
| “Memory request trong Kubernetes là giới hạn cứng.” | Request chủ yếu phục vụ scheduling. | Đọc `limits.memory` và policy thực. |
| “Container limit 1 GiB thì đặt `-Xmx1g` là tối ưu.” | Không còn ngân sách non-heap/native. | Chừa headroom theo số đo. |
| “`Runtime.maxMemory()` là tổng RAM container.” | Nó là **max Java heap**. | Đọc cgroup/system settings cho limit. |
| “`Runtime.freeMemory()` là RAM free của OS.” | Nó là free **bên trong heap đã cấp phát**. | Dùng cgroup/OS metrics cho memory usage. |
| “`MaxRAMPercentage=75` cho JVM tối đa 75% RAM tổng.” | Nó điều khiển sizing **Java heap**, process còn native memory. | Theo dõi RSS và cgroup. |
| “`MinRAMPercentage` quy định heap tối thiểu.” | Nó dùng cho **max heap khi RAM nhỏ**. | Dùng `-Xms` khi cần initial heap. |
| “Đặt cả `-Xmx` và MaxRAMPercentage sẽ tạo hai trần.” | `-Xmx` đặt max heap tường minh. | Chọn một policy. |
| “`MaxRAM=...` thay được Docker memory limit.” | Cờ chỉ ảnh hưởng sizing base JVM. | Dùng hard limit từ container runtime. |
| “Mọi JDK từ 10 hiểu cgroup v2.” | Hỗ trợ v2 được thêm sau và backport theo update. | Dùng JDK có hỗ trợ. |
| “`memory.current` bằng Java heap used.” | Hạch toán thêm native, cache, kernel pages. | So nhiều metrics và semantics. |
| “`memory.max=max` nghĩa container có 0 byte.” | `max` biểu thị không có hard limit tại cgroup đó. | Kiểm tra parent/host. |
| “`-XX:-UseContainerSupport` giúp container nhanh hơn.” | Có thể làm JVM sizing theo host và OOM kill. | Giữ container detection khi hỗ trợ. |
| “Có exit 137 thì chắc chắn Java heap OOME.” | Có thể do SIGKILL/OOMKilled từ OS. | Kiểm tra termination reason/events. |
| “Không có Java stack trace OOME thì không thể thiếu memory.” | Kernel có thể kill trước khi JVM ném lỗi. | Kiểm tra cgroup memory events. |
| “Dùng NMT là đo được mọi native malloc.” | NMT không bao phủ toàn bộ third-party native. | Bổ sung OS/native profiler. |
| “Tăng limit trong pod đang chạy thì max heap tự tăng.” | JVM max heap được sizing lúc start. | Redeploy/restart để kiểm chứng. |
| “Memory.percent áp dụng như nhau cho mọi GC/JDK.” | Ergonomics, small-heap rules, native/GC overhead khác nhau. | Đo trên đúng runtime và workload. |
| “CPU limit không liên quan memory.” | CPU throttle có thể làm queue dài và GC chậm. | Theo dõi CPU quota và backlog. |

## 19. Bài tập tự đánh giá

### Câu 1 — host hay container?

**Đề:** Node có 64 GiB, pod đặt `limits.memory: 1Gi`. JVM nên dùng dung lượng nào làm cơ sở cho sizing theo container nếu được nhận diện đúng?

**Đáp án:** **1 GiB memory hard limit**, không lấy toàn bộ 64 GiB host RAM.

### Câu 2 — ngân sách heap

**Đề:** Limit 1024 MiB, ước lượng native/non-heap 256 MiB, margin 128 MiB. Heap budget theo mô hình minh họa bằng bao nhiêu?

**Đáp án:** **640 MiB**, tức **62,5%**. Đó là ngân sách thiết kế, không phải giá trị bắt buộc của mọi JVM.

### Câu 3 — request và limit

**Đề:** Kubernetes request 512Mi, limit 1Gi. Request có phải hard memory limit hay không?

**Đáp án:** **Không.** Limit 1Gi mới là mức hard cap do kernel/cgroup thực thi theo chính sách.

### Câu 4 — `MinRAMPercentage`

**Đề:** `-XX:MinRAMPercentage=50` có phải đặt initial heap ít nhất 50% RAM không?

**Đáp án:** Không. Cờ này điều khiển tính **max heap cho small heaps**, không phải initial minimum heap.

### Câu 5 — `Runtime.maxMemory`

**Đề:** `Runtime.maxMemory()` in khoảng 640 MiB. Có thể kết luận container chỉ có 640 MiB hard limit không?

**Đáp án:** **Không.** Đây là max **Java heap**. Container hard limit có thể là 1 GiB hoặc một giá trị khác.

### Câu 6 — OOMKilled

**Đề:** Heap used khoảng 400 MiB, `-Xmx=640m`, container limit 1Gi và pod bị `OOMKilled`. Nên kiểm tra gì?

**Đáp án:** Cgroup memory usage/events, RSS, direct buffers, thread stacks, metaspace, native libraries, page cache và các tiến trình khác trong cgroup. **Không** mặc định tăng `-Xmx`.

### Câu 7 — cgroup v2

**Đề:** `memory.max` ghi `max`. Nó có nghĩa 0 byte hay vô hạn không điều kiện?

**Đáp án:** Không phải 0 byte. Nó biểu thị **không đặt hard limit tại cấp cgroup đó**; vẫn có thể chịu giới hạn từ parent, host hoặc các yếu tố khác.

### Câu 8 — đổi limit khi JVM đang chạy

**Đề:** Pod/container được nâng limit từ 1Gi lên 2Gi. `Runtime.maxMemory()` có chắc tự tăng gấp đôi không?

**Đáp án:** **Không.** Heap max đã sizing lúc JVM khởi động thông thường không tự thay theo limit động; cần thiết kế lại/restart và đo lại.

### Câu 9 — kiểm thử JVM detection

**Đề:** Dùng lệnh nào để kiểm tra container detection và max heap mà không cần viết ứng dụng?

**Đáp án:** Dùng `java -XshowSettings:system -XshowSettings:vm -version`, hoặc `java -Xlog:os+container=debug -version` trên JDK/Linux hỗ trợ.

### Câu 10 — tỉ lệ heap

**Đề:** `MaxRAMPercentage=90` có nghĩa container sẽ không thể dùng hơn 90% memory limit?

**Đáp án:** Không. Nó chỉ ảnh hưởng kích thước tối đa **Java heap**; toàn process còn nhiều phần non-heap/native và cgroup hạch toán cả memory liên quan khác.

## 20. Checklist quyết định cấu hình trước khi triển khai

- [ ] Đã xác nhận **cgroup v1/v2**, OS/kernel, JDK vendor/update và khả năng container support.
- [ ] Đã đọc **memory hard limit** thực, không nhầm với host RAM/request.
- [ ] Đã kiểm tra kết quả `-XshowSettings:system` và `-XshowSettings:vm` hoặc log tương ứng.
- [ ] Đã chọn rõ chính sách **fixed `-Xmx`** hoặc **proportional MaxRAMPercentage**.
- [ ] Đã dành ngân sách cho **native/non-heap, thread stacks, direct buffers, GC, page cache và margin**.
- [ ] Đã kiểm tra initial heap và nhu cầu `-Xms`, không ép initial=max khi chưa đo.
- [ ] Đã theo dõi `Runtime.maxMemory` và actual heap usage trên môi trường thật.
- [ ] Đã so **RSS, cgroup memory.current/events, Kubernetes OOMKilled**, không chỉ Java heap.
- [ ] Đã thử với peak load, nhiều thread, traffic spike và GC pressure.
- [ ] Đã xem xét CPU quota/throttling ảnh hưởng GC và các thread pools.
- [ ] Đã xác định chính sách nâng memory limit và **restart/redeploy JVM**.
- [ ] Đã lưu JDK flags, memory limit và baseline metrics cùng cấu hình release.

## 21. Ghi nhớ nhanh và tài liệu tham khảo chính thức

- Từ **Java 10**, HotSpot nhận diện container memory/CPU tốt hơn; `UseContainerSupport` vẫn là khả năng quan trọng trên JDK hiện đại.
- **Container memory limit ≠ Java max heap.** JVM cần bộ nhớ cho metaspace, thread stacks, direct buffers, JIT/code cache, GC và native libraries.
- **`MaxRAMPercentage`** tính max heap theo memory sizing base. **`MinRAMPercentage`** dành cho small-heap maximum, không phải minimum heap.
- **`-Xmx`** đặt max heap tường minh; **`MaxRAM`** chỉ đặt memory sizing base, không thay hard limit OS.
- **Kubernetes requests.memory** phục vụ scheduling; **limits.memory** mới ràng buộc hard memory.
- **cgroup v2 `memory.max`** là hard limit hoặc `max`; **`memory.current`** không đồng nghĩa Java heap used.
- JVM và cgroups phải tương thích; JDK 10 nguyên bản không nên được coi là có đầy đủ nhận diện **cgroup v2**.
- Dùng **`-Xlog:os+container`**, **`-XshowSettings:system`**, **`-XshowSettings:vm`**, `Runtime.maxMemory` và OS/cgroup metrics để xác minh.
- **OOMKilled** không đồng nghĩa `java.lang.OutOfMemoryError`. Tìm nguyên nhân ở **tổng memory process/cgroup**, không chỉ heap.
- Tỷ lệ heap hợp lý phải đến từ **workload đo thật** và một phần **headroom**, không có một con số phần trăm chính xác cho mọi ứng dụng.

Nguồn chính thức vẫn áp dụng:

1. [Oracle Java SE 17 — java launcher: UseContainerSupport và RAM percentage flags](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
2. [Oracle Java SE 25 — java launcher: Linux container detection, MaxRAMPercentage, MaxRAM](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
3. [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).
4. [Kubernetes — About cgroup v2, yêu cầu Java runtime hỗ trợ](https://kubernetes.io/docs/concepts/architecture/cgroups/).
5. [Kubernetes — Assign Memory Resources to Containers and Pods](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/).
6. [Linux kernel — cgroup v2: memory controller](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html).
7. [OpenJDK — JDK-8230305: Cgroups v2 container awareness](https://bugs.openjdk.org/browse/JDK-8230305).
8. [Oracle JDK 25 — Diagnostic Tools and Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html).

**Kết luận:** Để chọn cấu hình JVM đúng trong container, trước tiên hãy xác minh **hard memory limit thực tế và JVM có nhận diện đúng hay không**. Tiếp đó lập ngân sách **Java heap + native/non-heap + dự phòng**, chọn `-Xmx` hoặc `MaxRAMPercentage` nhất quán, rồi đo cgroup usage/RSS và GC dưới tải thực. Đây là cách tránh cả việc chọn heap quá lớn dẫn tới **OOMKilled** lẫn chọn heap quá nhỏ gây **Java heap OutOfMemoryError** và GC overhead.
