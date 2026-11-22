# Java 10 — Bộ nhớ trong container: `-XX:InitialRAMPercentage` và kích thước heap ban đầu

## 1. Mục tiêu bài học

Khi chạy Java trong Docker, Kubernetes hoặc môi trường bị giới hạn RAM, **Java heap ban đầu** và **Java heap tối đa** cần được hiểu tách biệt. Cờ **`-XX:InitialRAMPercentage`** quy định tỷ lệ RAM **dùng làm đầu vào để tính kích thước heap ban đầu**, **không phải phần trăm RAM JVM sẽ dùng tối đa**, và **không phải toàn bộ bộ nhớ của tiến trình**.

Java 10 là mốc quan trọng vì Oracle/OpenJDK đưa vào hai nhóm cải tiến:

1. **Container awareness** trên Linux, theo thay đổi **JDK-8146115**, giúp JVM tính toán tài nguyên theo các giới hạn CPU/RAM của container thay vì mặc định nhìn toàn bộ máy chủ.
2. Các cờ **`-XX:InitialRAMPercentage`**, **`-XX:MaxRAMPercentage`** và **`-XX:MinRAMPercentage`**, theo **JDK-8186248**, cho phép điều khiển heap sizing dưới dạng phần trăm RAM hiệu dụng.

Những cơ chế này **vẫn có ý nghĩa trên Java hiện đại**. Bài tập và ví dụ sử dụng JDK 17+ và xác minh trên OpenJDK 24.0.2, tránh các cờ chia theo `Fraction` đã bị deprecated/removed ở các JDK mới.

**Sau bài này, bạn có thể:**

- Giải thích mục đích chính xác của `-XX:InitialRAMPercentage`.
- Phân biệt kích thước ban đầu `InitialHeapSize`, kích thước tối thiểu `MinHeapSize`, tối đa `MaxHeapSize` và vùng đang dùng/committed.
- Hiểu sự khác nhau giữa `InitialRAMPercentage`, `MaxRAMPercentage` và `MinRAMPercentage`.
- Biết `-Xms`, `-Xmx` và `-XX:MaxRAM` tương tác với các phần trăm như thế nào.
- Đọc đúng memory limits của container Linux và lý do kết quả có thể khác host RAM.
- Hiểu vì sao heap 60% container **không** bảo đảm container chỉ dùng 60% RAM.
- Kiểm tra giá trị được HotSpot áp dụng qua `-XX:+PrintFlagsFinal`, `MemoryMXBean`, `HotSpotDiagnosticMXBean` và các công cụ Linux/container.
- Chạy hai chương trình Java đầy đủ cùng bốn cấu hình heap đã kiểm chứng.
- Đưa ra lựa chọn khởi tạo heap có cơ sở, tránh cả startup GC quá nhiều và cấp phát quá tay.

**Nguyên tắc ghi nhớ:**

> `InitialRAMPercentage` giúp JVM **chọn quy mô Java heap lúc bắt đầu** dựa trên lượng RAM **mà JVM dùng làm cơ sở sizing**. Nó không tăng RAM vật lý, không đặt hard limit cho tổng RSS, và không tự quyết định mức `-Xmx`.

## 2. Java heap trong container: bốn kích thước khác nhau

Một ứng dụng Java có ít nhất bốn đại lượng cần phân biệt:

| Khái niệm | Định nghĩa | Cách quan sát |
|---|---|---|
| **Initial heap** | Kích thước heap ban đầu do VM khởi tạo và áp dụng các quy tắc ergonomics | `InitialHeapSize`; `MemoryUsage.getInit()` |
| **Minimum heap** | Mức thấp nhất theo chính sách sizing/flags của VM; có thể nhỏ hơn initial | `MinHeapSize` |
| **Maximum heap** | Giới hạn trên của Java heap do JVM chọn/áp dụng | `MaxHeapSize`; `-Xmx`; `MemoryUsage.getMax()` |
| **Current committed/used** | Bộ nhớ heap đang được JVM cam kết và phần đang được dùng để chứa đối tượng | `MemoryUsage.getCommitted()` và `getUsed()` |

### 2.1. “Initial” không phải “maximum”

Giả sử container có RAM limit **1 GiB**. Nếu không có cờ sizing tường minh khác:

- `-XX:InitialRAMPercentage=10`: đề xuất **initial heap khoảng 10%** cơ sở RAM;
- `-XX:MaxRAMPercentage=60`: đề xuất **maximum heap khoảng 60%** cơ sở RAM.

Đó là **hai tham số khác nhau**. Lúc khởi động, heap có thể khoảng 100 MiB nhưng **có quyền tăng trưởng** tới hơn 600 MiB, tùy GC và giới hạn đã chọn.

Khi heap tăng từ initial sang maximum, JVM cần commit thêm bộ nhớ/điều chỉnh các vùng heap, điều có thể ảnh hưởng hiệu năng. Khi initial quá lớn, quá trình khởi động và footprint ban đầu cũng có thể tăng.

### 2.2. “Committed” không phải “used”

**Used** thể hiện bộ nhớ thực tế đang được đánh dấu là sử dụng trong heap. **Committed** phản ánh vùng heap JVM đã được hệ thống bảo đảm backing, nhưng không phải tất cả đều có object sống.

Ví dụ minh họa:

```text
Maximum heap  = 616 MiB
    |
    +-- Reserved address space cho khả năng mở rộng heap
    |
Committed now = 106 MiB
    |
Used now      =   2 MiB
```

Đây là **một trường hợp quan sát** trên OpenJDK 24.0.2 với G1, không phải một kết quả sẽ y hệt trên mọi máy. Đặc biệt, **initial heap size** và **committed heap ngay lúc đọc MXBean** có thể khác nhau vì VM/GC ergonomics.

### 2.3. “Heap maximum” không phải “process memory limit”

Một process Java còn có:
- Metaspace cho metadata lớp;
- Code cache cho JIT-compiled code;
- Thread stacks và một số native thread structures;
- Direct byte buffers/NIO và native allocations;
- JNI/native libraries, GC bookkeeping;
- JVM runtime structures và các vùng mmap;
- Bộ nhớ bị tính trong cgroup theo quy tắc hệ điều hành, có thể bao gồm những trang cache phù hợp.

**Container memory limit bao phủ nhiều nguồn tiêu thụ hơn Java heap.** Do đó, nếu đặt `-Xmx` bằng toàn bộ limit, container có thể bị OOM-kill dù Java heap chưa đạt maximum.

## 3. `-XX:InitialRAMPercentage` hoạt động như thế nào?

Cú pháp:

```bash
java -XX:InitialRAMPercentage=10 -jar app.jar
```

**`10` nghĩa là 10%**, không phải 10 MiB, không phải 0,10%, và không cần ký hiệu `%` trong argument.

Theo Oracle `java` command documentation, tham số đặt **initial amount of memory used for Java heap before applying ergonomics heuristics**, theo phần trăm của giá trị RAM làm cơ sở sizing như mô tả ở `-XX:MaxRAM`.

Một biểu thức dễ hiểu:

```text
rawInitialHeap ≈ effectiveSizingRAM × InitialRAMPercentage / 100

actualInitialHeap = HotSpot ergonomics + alignment + heap policy
                   áp dụng lên rawInitialHeap
```

Đây là **mô hình giải thích**, không phải thuật toán byte-perfect được cam kết trên mọi JDK/GC.

### 3.1. Mặc định trên các bản JDK được tài liệu hóa

Trong Oracle JDK 17, 21 và 25 docs, **default `InitialRAMPercentage` là 1.5625%**.

Ví dụ không chỉ định:
 
```bash
java -XX:MaxRAM=1g -XX:MaxRAMPercentage=60 -jar app.jar
```

Khi thiếu `-Xms` hoặc `InitialHeapSize` và không có yếu tố tùy biến khác, HotSpot dùng default percentage cùng ergonomics để chọn initial heap.

**Không mặc định giá trị sẽ luôn đúng vĩnh viễn** ở mọi runtime/vendor/JDK mới hơn: kiểm tra `-XX:+PrintFlagsFinal` của chính bản JVM cần triển khai.

### 3.2. Không tự ấn định minimum heap

Một điểm thường bị bỏ qua: `InitialRAMPercentage` chọn **initial heap**, nhưng không nhất thiết nâng **MinHeapSize** lên cùng mức.

Trong phép thử G1 trên OpenJDK 24.0.2 với `MaxRAM=1g` và `InitialRAMPercentage=10`:
- `InitialHeapSize = 104 MiB`;
- `MinHeapSize = 8 MiB`.

Vì vậy đừng viết “`InitialRAMPercentage=10` buộc JVM giữ **tối thiểu** 10% RAM làm heap trong suốt vòng đời”. Điều đó **không phải hợp đồng của flag**.

Khi muốn đặt **mức khởi tạo và mức sàn** rõ ràng, hãy cân nhắc `-Xms` theo tài liệu GC/JDK hiện hành. Nhưng mức sàn lớn có chi phí memory footprint và ảnh hưởng hoạt động co heap.

## 4. RAM nào được dùng làm cơ sở phần trăm?

Một JVM có thể nhìn thấy:
- RAM vật lý của máy chủ;
- RAM bị giới hạn bởi container/cgroups;
- RAM được ghi đè bằng một cờ sizing như `-XX:MaxRAM`.

Trên HotSpot Linux hiện đại có container awareness bật mặc định, giá trị RAM khả dụng cho sizing xét **ràng buộc môi trường**, trong đó có container memory limit khi được hỗ trợ.

Theo Oracle JDK 25 docs, `-XX:MaxRAM` mô tả cơ sở tính toán là giá trị nhỏ hơn giữa **physical memory** và **environment constraints** (ví dụ container), với các giới hạn ergonomics đi kèm. Khi bạn chủ động truyền `-XX:MaxRAM=...`, bạn đang **đặt cơ sở giả định cho tính toán heap**, không tạo ra một hard memory limit mới từ hệ điều hành.

### 4.1. Ví dụ container 1 GiB trên host 64 GiB

```text
Host physical RAM:         64 GiB
Linux container hard limit: 1 GiB
JVM có container support:  effectiveSizingRAM ≈ 1 GiB

InitialRAMPercentage:      10
MaxRAMPercentage:          60

Raw initial sizing:       102.4 MiB
Raw max sizing:           614.4 MiB

Actual heap after ergonomics: phụ thuộc HotSpot, GC, alignment
```

Không lấy 10% của **64 GiB** nếu JVM đang thật sự nhận diện memory limit 1 GiB của container. Ngược lại, nếu bản JDK quá cũ hoặc container/cgroup không được nhận diện, JVM có thể dùng host memory và tính heap quá lớn.

### 4.2. Từ Java 10 đến cgroups v2

Java 10 có các cải tiến container awareness cho Linux, nhưng những bản đời đầu chủ yếu phục vụ môi trường Docker/cgroups của thời điểm đó. **cgroups v2** được hỗ trợ ở dòng OpenJDK hiện đại (trong các JDK mới hơn và một số bản backport).

Bởi vậy không khuyên triển khai Java 10 nguyên bản làm runtime container production năm nay. Với hệ thống dùng cgroups v2, chọn một JDK được bảo trì và **xác minh container limit thật**.

Một cách kiểm tra trên Linux container:

```bash
java -XshowSettings:system -version
```

`-XshowSettings:system` được Oracle dokument hóa cho Linux, giúp xem container/host configuration mà JVM nhận diện.

Muốn xem những chi tiết phát hiện cgroups trên HotSpot:

```bash
java -Xlog:os+container=trace -version
```

Log có thể nhiều; chỉ bật trace khi cần chẩn đoán. Cú pháp này là **HotSpot Unified Logging**, không phải API Java portable cho mọi VM.

### 4.3. Windows và môi trường không phải Linux

`-XX:InitialRAMPercentage` có thể dùng để kiểm tra heap ergonomics trên Windows HotSpot, nhưng cơ chế tự phát hiện Linux cgroups **không áp dụng y nguyên**.

**Các kết quả Java chạy được trong bài này đã được kiểm chứng trên Windows/OpenJDK 24.0.2** bằng `-XX:MaxRAM=1g` để tạo **một cơ sở sizing cố định**. Đó **không** phải bằng chứng rằng một Docker Linux container đã được phát hiện.

## 5. Phân biệt các flags thường đi cùng nhau

| JVM flag | Cơ chế | Khi dùng |
|---|---|---|
| `-XX:InitialRAMPercentage=N` | Tỷ lệ đầu vào để tính **initial heap** | Muốn khởi tạo heap theo RAM hiệu dụng |
| `-XX:MaxRAMPercentage=N` | Tỷ lệ đầu vào để tính **max heap** | Muốn giới hạn heap theo RAM hiệu dụng |
| `-XX:MinRAMPercentage=N` | Tỷ lệ để tính **max heap trong trường hợp RAM nhỏ** | Phân tích small-memory ergonomics |
| `-XX:MaxRAM=SIZE` | Đặt **cơ sở RAM để tính sizing** | Thử nghiệm sizing hoặc cấu hình có chủ đích |
| `-XmsSIZE` | Đặt **initial heap và minimum heap** rõ ràng | Muốn initial/minimum tuyệt đối, không theo % |
| `-XmxSIZE` | Đặt **maximum heap** rõ ràng | Muốn cap heap tuyệt đối |
| `-XX:InitialHeapSize=SIZE` | Đặt initial heap tường minh | Tuning đặc thù; cần hiểu precedence |
| `-XX:MinHeapSize=SIZE` | Đặt minimum heap tường minh | Tuning chuyên biệt |
| `-XX:+UseContainerSupport` | Trên Linux HotSpot hỗ trợ: nhận diện giới hạn container, mặc định bật | Thường giữ default; dùng log để xác minh |
| `-XX:+AlwaysPreTouch` | Yêu cầu JVM touch pages heap ở startup | Có thể đổi footprint/startup latency |

### 5.1. Tên `MinRAMPercentage` rất dễ gây hiểu nhầm

**`-XX:MinRAMPercentage` không đặt “heap tối thiểu bằng N% RAM”.**

Theo Oracle docs, nó ảnh hưởng việc tính **maximum heap trên những máy có RAM nhỏ** (ví dụ dưới khoảng 125 MB theo tài liệu). Nó không phải đồng nghĩa của `-Xms` hay `-XX:MinHeapSize`.

Không viết:

```bash
# SAI nếu ý định là đặt initial/minimum heap 50%:
java -XX:MinRAMPercentage=50 -jar app.jar
```

Nếu mục tiêu là initial heap 10%, phải dùng **`-XX:InitialRAMPercentage=10`**. Nếu mục tiêu là minimum heap cố định, có thể dùng `-Xms` theo yêu cầu thực tế.

### 5.2. `MaxRAMPercentage` không đồng nghĩa `InitialRAMPercentage`

`-XX:MaxRAMPercentage=60` giới hạn **maximum** theo công thức ergonomics. Nó không yêu cầu JVM cấp phát/commit ngay 60% RAM lúc startup.

`-XX:InitialRAMPercentage=10` là **initial**, không giới hạn max. Khi thiếu một trong hai, JVM có thể dùng default còn lại hoặc ràng buộc khác.

### 5.3. `MaxRAM` không phải hạn mức cgroup

`-XX:MaxRAM=1g` không tương đương Docker `--memory=1g`.

- `-XX:MaxRAM` là một **đầu vào heap ergonomics** của HotSpot;
- `docker run --memory=1g` tạo **giới hạn do môi trường/container** thực thi;
- Có thể dùng cả hai nhưng **không** đồng nghĩa;
- Java process vẫn có native memory và có thể vượt budget tổng thể nếu cấu hình không phù hợp.

## 6. Công thức tính minh họa và vấn đề căn chỉnh

Giả sử ta sử dụng `MaxRAM = 1 GiB = 1.073.741.824 bytes`.

**Đặt initial 10%:**

```text
1,073,741,824 bytes × 0.10 = 107,374,182.4 bytes
≈ 102.4 MiB
```

**Đặt maximum 60%:**

```text
1,073,741,824 bytes × 0.60 = 644,245,094.4 bytes
≈ 614.4 MiB
```

Nhưng HotSpot có các bước **ergonomics**, **heap alignment**, **GC region/page sizing**. Vì thế số cuối có thể khác giá trị tính toán thuần túy.

Trên **OpenJDK 24.0.2, G1, Windows x64**, khi chạy:

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 HeapSizingDemo
```

đã quan sát:

```text
InitialHeapSize = 109051904 bytes = 104 MiB
MaxHeapSize     = 645922816 bytes = 616 MiB
```

**Không phải phép tính sai.** JVM đã áp các quy tắc sizing theo collector/runtime. Đừng dùng số `102.4` hoặc `614.4` như golden output của một JVM không được chỉ định.

### 6.1. MiB và MB

Trong tính toán:
- `1 KiB = 1024 bytes`;
- `1 MiB = 1024 KiB = 1.048.576 bytes`;
- `1 GiB = 1024 MiB`.

Flag `-XX:MaxRAM=1g` dùng suffix byte-size của Java launcher; trong kết quả đã đo là **1 GiB**. Các tài liệu container/Kubernetes có thể dùng ký hiệu `Mi`/`Gi` khác với `MB`/`GB`. Khi tính budget cần nhất quán đơn vị.

## 7. `-Xms` ghi đè phần trăm initial trong trường hợp nào?

Khi bạn đặt initial heap tường minh:

```bash
java -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -Xms256m ...
```

HotSpot dùng `-Xms256m` để ấn định **InitialHeapSize=256 MiB** và **MinHeapSize=256 MiB** trong cấu hình đã kiểm chứng, dù giá trị cờ `InitialRAMPercentage` vẫn có thể hiển thị là `10.0` trong diagnostic flags.

**Kết luận:** sự hiện diện của một giá trị flag **không đủ** để kết luận flag ấy thực sự đã quyết định kích thước cuối. Cần kiểm tra **`InitialHeapSize` thực tế**.

### 7.1. Ví dụ giá trị còn hiện nhưng không còn quyết định

```text
InitialRAMPercentage = 10.0
InitialHeapSize      = 268435456 bytes = 256 MiB
MinHeapSize          = 268435456 bytes = 256 MiB
```

Khi có `-Xms`, phần trăm initial không phải là mức phải áp bằng mọi giá. Đây là một lý do không nên vừa đặt `-Xms` vừa đặt `InitialRAMPercentage` nếu không có chủ đích: nó làm cấu hình khó hiểu khi review.

### 7.2. `-XX:InitialHeapSize` và thứ tự flags

Oracle Java launcher docs cũng mô tả một mối quan hệ **thứ tự xuất hiện** giữa `-Xms` và `-XX:InitialHeapSize`: khi cả hai được cung cấp, giá trị được ưu tiên có thể phụ thuộc vị trí trong command line.

Đừng trộn nhiều flag **điều khiển cùng một mục tiêu** trong production. Hãy chọn một nguồn cấu hình rõ ràng, tránh việc `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Docker ENTRYPOINT và startup script cộng dồn nhiều cờ trái ngược nhau.

## 8. `-Xmx` ghi đè phần trăm maximum

Ví dụ:

```bash
java -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -Xmx320m HeapSizingDemo
```

Cấu hình đã thử cho kết quả:

```text
InitialHeapSize      = 104 MiB
MaxHeapSize          = 320 MiB
MaxRAMPercentage     = 60.0
```

`MaxRAMPercentage` vẫn là 60.0 theo diagnostic, nhưng `-Xmx320m` ấn định max heap 320 MiB.

**Không** diễn giải “MaxRAMPercentage 60” thành “JVM không thể có max heap thấp hơn 60% của RAM”. Tương tự `-Xms`, cờ **tường minh** có ý nghĩa quyết định trong trường hợp này.

### 8.1. Tương tác khi initial vượt maximum

Một cấu hình initial quá lớn so với maximum không tạo ra một heap có thể tồn tại hợp lệ. JVM có thể báo lỗi khởi động hoặc điều chỉnh theo quy tắc VM/flags cụ thể.

Ví dụ cần tránh:

```bash
java -Xms800m -Xmx640m -jar app.jar
```

Đây là ví dụ **cấu hình không hợp lệ về kích thước**, không phải lời khuyên chạy. Đảm bảo initial/minimum không cao hơn max sau khi JVM áp các giới hạn khác.

## 9. Chương trình hoàn chỉnh 1 — xem heap sizes được chọn

Lưu tệp **`HeapSizingDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import com.sun.management.HotSpotDiagnosticMXBean;

public class HeapSizingDemo {
    private static final long MIB = 1024L * 1024L;

    private static long flagMiB(
            HotSpotDiagnosticMXBean bean,
            String name) {
        return Long.parseLong(
                bean.getVMOption(name).getValue()) / MIB;
    }

    public static void main(String[] args) {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                    HotSpotDiagnosticMXBean.class);

        MemoryUsage usage =
                ManagementFactory.getMemoryMXBean()
                    .getHeapMemoryUsage();

        System.out.println("initialPct=" +
                bean.getVMOption(
                    "InitialRAMPercentage").getValue());

        System.out.println("maxPct=" +
                bean.getVMOption(
                    "MaxRAMPercentage").getValue());

        System.out.println("initialHeapMiB=" +
                flagMiB(bean, "InitialHeapSize"));

        System.out.println("minHeapMiB=" +
                flagMiB(bean, "MinHeapSize"));

        System.out.println("maxHeapMiB=" +
                flagMiB(bean, "MaxHeapSize"));

        System.out.println("jmxInitMiB=" +
                usage.getInit() / MIB);

        System.out.println("jmxMaxMiB=" +
                usage.getMax() / MIB);

        System.out.println("committedLeMax=" +
                (usage.getCommitted() <= usage.getMax()));

        System.out.println("usedLeCommitted=" +
                (usage.getUsed() <= usage.getCommitted()));
    }
}
```

Biên dịch trên JDK 17+:

```bash
javac --release 17 -encoding UTF-8 HeapSizingDemo.java
```

Dùng `com.sun.management.HotSpotDiagnosticMXBean` để đọc các flags nội bộ của **HotSpot**. Đây là Java API có tài liệu, nhưng các tên VM flags và việc có chúng là **VM-specific**; chương trình này dùng cho OpenJDK/HotSpot và bản JDK tương thích, không khẳng định mọi JVM vendor phải xuất cùng một tập cờ.

### 9.1. Thí nghiệm A: initial 10%, max 60%

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 HeapSizingDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2, Windows x64:**

```text
initialPct=10.0
maxPct=60.0
initialHeapMiB=104
minHeapMiB=8
maxHeapMiB=616
jmxInitMiB=104
jmxMaxMiB=616
committedLeMax=true
usedLeCommitted=true
```

Điểm cần quan sát:
- `InitialHeapSize` được HotSpot chọn 104 MiB;
- `MinHeapSize` chỉ 8 MiB, **không** bằng initial;
- `MaxHeapSize` được chọn 616 MiB;
- `MemoryMXBean` xác nhận initial và max trong lần thử;
- Các điều kiện `committed ≤ max`, `used ≤ committed` đúng tại thời điểm đọc.

### 9.2. Thí nghiệm B: thêm `-Xms256m`

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -Xms256m HeapSizingDemo
```

**Stdout đã kiểm chứng:**

```text
initialPct=10.0
maxPct=60.0
initialHeapMiB=256
minHeapMiB=256
maxHeapMiB=616
jmxInitMiB=256
jmxMaxMiB=616
committedLeMax=true
usedLeCommitted=true
```

Mặc dù `initialPct=10.0`, **initialHeapMiB=256** bởi `-Xms256m`. Đây là ví dụ trực tiếp cho thấy **flag percentage được khai báo không đồng nghĩa percentage đang điều khiển effective initial heap**.

### 9.3. Thí nghiệm C: thêm `-Xmx320m`

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -Xmx320m HeapSizingDemo
```

**Stdout đã kiểm chứng:**

```text
initialPct=10.0
maxPct=60.0
initialHeapMiB=104
minHeapMiB=8
maxHeapMiB=320
jmxInitMiB=104
jmxMaxMiB=320
committedLeMax=true
usedLeCommitted=true
```

Dù `maxPct=60.0`, **maxHeapMiB=320** do `-Xmx` có hiệu lực. Initial vẫn theo quy tắc của `InitialRAMPercentage`.

### 9.4. Thí nghiệm D: giá trị initial percentage mặc định

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:MaxRAMPercentage=60 HeapSizingDemo
```

**Stdout đã kiểm chứng:**

```text
initialPct=1.5625
maxPct=60.0
initialHeapMiB=16
minHeapMiB=8
maxHeapMiB=616
jmxInitMiB=16
jmxMaxMiB=616
committedLeMax=true
usedLeCommitted=true
```

Điểm quan trọng: **default `InitialRAMPercentage=1.5625`** trên JDK được kiểm chứng cho initial heap **16 MiB** với cơ sở 1 GiB. Không nhầm nó với maximum heap đang bằng 616 MiB.

### 9.5. Vì sao các con số không portable?

Kết quả chính xác phụ thuộc JDK build, garbage collector, heap alignment, platform/architecture, các tùy chọn JVM, và có thể cả điều kiện workload/startup.

Các ví dụ **dùng `-XX:MaxRAM=1g` để cố định sizing input**, không thật sự áp cgroup memory limit. Nếu chạy trong Linux Docker hoặc GC khác, **đừng viết test yêu cầu luôn có đúng 104/616 MiB**; dùng các asserts về quan hệ và kiểm tra effective flags của runtime thật.

## 10. Xem phần trăm, flag origins và hiệu lực thực tế

### 10.1. `-XX:+PrintFlagsFinal`

Không cần viết chương trình Java, HotSpot có thể in final VM options:

```bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -XX:+PrintFlagsFinal -version
```

Output rất dài. Có thể lọc trên Linux/macOS:

```bash
java -XX:MaxRAM=1g -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'InitialRAMPercentage|MaxRAMPercentage|InitialHeapSize|MinHeapSize|MaxHeapSize'
```

Trong Windows PowerShell, có thể dùng `Select-String` thay `grep`.

Cần đọc các dòng **InitialHeapSize** và **MaxHeapSize**, không chỉ dòng có chữ percentage. `PrintFlagsFinal` thường ghi nguồn giá trị như `{default}`, `{ergonomic}`, `{command line}`; tên/cấu trúc thông tin có thể khác theo JDK.

### 10.2. `VMOption.Origin` từ HotSpot MXBean

Với `HotSpotDiagnosticMXBean`:

```java
var mx = ManagementFactory.getPlatformMXBean(
        HotSpotDiagnosticMXBean.class);

var option = mx.getVMOption("InitialHeapSize");
System.out.println(option.getValue());
System.out.println(option.getOrigin());
```

**Mảnh code**, cần imports `ManagementFactory` và `HotSpotDiagnosticMXBean` trong chương trình đầy đủ ở trên.

`getValue()` cho giá trị flag thực; `getOrigin()` cho biết nó do default/ergonomics/VM creation... theo HotSpot. Đây là cách hữu ích để xem **mức size đã chọn** và nguồn quyết định.

Không viết code phụ thuộc vào **thứ tự hiển thị** của mọi flag hoặc **chuỗi thông báo lỗi** không được đặc tả.

### 10.3. `-XshowSettings:vm`

```bash
java -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -XshowSettings:vm -version
```

Công cụ này cho một bức tranh chung về thiết lập VM, đặc biệt estimated maximum heap. Tuy nhiên **không phải mọi con số initial/minimum** đều được in theo cùng cấu trúc. Dùng `-XX:+PrintFlagsFinal` hoặc MXBean nếu cần so sánh cụ thể.

### 10.4. Trong container Linux: `-XshowSettings:system`

```bash
java -XshowSettings:system -version
```

Mục tiêu là xác minh JVM **nhìn thấy giới hạn cgroups gì**, thay vì chỉ tin Kubernetes manifest hoặc Docker CLI.

Nếu thấy memory limit không đúng, đừng lập tức đổi `InitialRAMPercentage` để “chữa” việc JVM không nhìn thấy container. Trước tiên kiểm tra JDK container support/cgroups version và cấu hình runtime thật.

## 11. Docker Linux — ví dụ giới hạn RAM có chủ đích

Với Docker đang chạy trên máy Linux và image **Eclipse Temurin JDK 21**, có thể thử:

```bash
docker run --rm --memory=1g eclipse-temurin:21-jdk \
  java -XshowSettings:system -version
```

Quan sát mục liên quan **Provider / Memory Limit / cgroup** tùy Docker và JDK. Sau đó:

```bash
docker run --rm --memory=1g eclipse-temurin:21-jdk \
  java -XX:+UseG1GC \
  -XX:InitialRAMPercentage=10 \
  -XX:MaxRAMPercentage=60 \
  -XX:+PrintFlagsFinal -version
```

Hai lệnh **là mẫu để thực hành trên Docker Linux**, **không phải lệnh đã chạy trong phép thử Windows ở mục 9**. Dung lượng, log và tên fields có thể khác trên runtime của bạn.

### 11.1. Điều gì nên xảy ra?

Khi Linux HotSpot nhận diện hard memory limit 1 GiB và không có cờ size khác ghi đè:
- Effective sizing RAM phải phản ánh limit container theo policy VM;
- Initial và max heap được tính theo 10% và 60% **trước ergonomics**;
- Cần kiểm tra **InitialHeapSize/MaxHeapSize cuối cùng**, không đoán giá trị byte chính xác;
- Process Java vẫn sử dụng native memory ngoài heap.

**Nếu container không bị giới hạn memory**, JVM có thể sizing theo host/limits khác. Docker CPU quota không tự tạo ra RAM limit; `--cpus` và `--memory` là các loại hạn mức khác nhau.

### 11.2. Không dùng `-XX:-UseContainerSupport` như giải pháp mặc định

Cờ tắt container detection có thể giúp chẩn đoán sự khác biệt giữa nhìn host và nhìn container, nhưng trong deployment có memory limit nhỏ nó có thể làm JVM sizing quá lớn so với khả năng thực tế.

Giữ default support trên Linux HotSpot hiện đại trừ khi có lý do có tài liệu và đã đo đạc. Khi nghi ngờ, dùng `-Xlog:os+container=trace` để kiểm tra.

### 11.3. Cgroups v1/v2 và phiên bản JDK

Các môi trường Kubernetes mới thường dùng **cgroups v2**. Không khuyên dùng các bản JDK/container runtime quá cũ không nhận diện đúng memory limit của v2.

Từ **OpenJDK 15** có hỗ trợ cgroups v2 trong mainline, và có backports trong một số nhánh LTS. Chọn JDK 17/21/25+ được cập nhật thường an toàn hơn về mặt container detection. **Không đồng nhất “Java 10 hỗ trợ Docker” với “mọi môi trường cgroups v2 hiện tại đều hoạt động đúng trên Java 10 nguyên bản”.**

## 12. Kubernetes — request và limit không giống nhau

Ví dụ một đoạn cấu hình container:

```yaml
resources:
  requests:
    memory: "384Mi"
  limits:
    memory: "1Gi"
```

Đây chỉ là **mảnh YAML**, không phải Pod manifest đầy đủ.

- `requests.memory` thường dùng cho scheduling/resource accounting theo chính sách Kubernetes;
- `limits.memory` là mức hard limit được hệ điều hành/container runtime thực thi;
- JVM container awareness thường nhìn **memory limit thực tế** cho sizing, không được mặc định coi `requests.memory` là heap limit;
- Những resource controls nâng cao có thể ảnh hưởng hành vi cụ thể; phải xem cgroup thực tế nếu nghi ngờ.

Với ví dụ limit 1 GiB, cờ `InitialRAMPercentage=10` chỉ nói về **Java heap ban đầu gần 10% cơ sở sizing**, **không** nghĩa Pod chỉ tiêu thụ 102.4 MiB khi vừa ready.

### 12.1. Cấu hình mẫu

Một môi trường có thể đặt startup flags:

```bash
java -XX:+UseG1GC \
  -XX:InitialRAMPercentage=10 \
  -XX:MaxRAMPercentage=60 \
  -jar app.jar
```

Đây là **cấu hình minh họa**, không phải “mức chuẩn tốt nhất” cho mọi microservice. Phần 40% chưa dành cho heap cũng **không phải một khoản native memory đã được JVM bảo đảm**; cần đo native allocations, page cache và memory pressure thực tế.

### 12.2. OOMKilled khác `OutOfMemoryError`

**Java `OutOfMemoryError: Java heap space`:**
- Có thể do Java heap không đủ chỗ cho objects;
- JVM thường ghi exception hoặc crash tùy xử lý;
- Có thể xảy ra **trước** khi container chạm memory limit.

**Container OOMKilled:**
- Memory usage theo cgroup/host vượt chính sách kernel;
- Process có thể bị SIGKILL (thường exit status 137, tùy hệ thống);
- Không bảo đảm Java có cơ hội in `OutOfMemoryError` hoặc thread dump;
- Có thể xảy ra dù heap used nhỏ hơn `-Xmx` vì native memory và các nguồn khác.

Đừng giải quyết container OOMKilled bằng cách **tăng `InitialRAMPercentage`**. Việc đó có thể làm footprint lúc startup lớn hơn và **tệ đi**.

## 13. Initial heap và footprint khi khởi động

### 13.1. Initial lớn có lợi khi nào?

Một JVM với heap ban đầu quá nhỏ có thể phải:
- Mở rộng heap nhanh khi ứng dụng khởi động;
- Thu gom GC thường xuyên do allocations của framework;
- Chịu latency khi heap/GC heuristics điều chỉnh không gian.

Tăng `InitialRAMPercentage` có thể giúp **giảm nhu cầu tăng heap/GC ở giai đoạn warm-up**, nhất là khi live set sau startup khá lớn.

Tuy nhiên, **không tự động kết luận startup nhanh hơn**. Cần xem GC logs và thời gian đến ready của ứng dụng.

### 13.2. Initial lớn có tác hại khi nào?

- JVM có thể commit/đụng vào nhiều trang bộ nhớ hơn trong lúc startup;
- Khi dùng `-XX:+AlwaysPreTouch`, startup cost và áp lực resident memory có thể tăng mạnh;
- Một Pod/container nhỏ có thể bị OOM sớm nếu JVM không còn headroom cho native memory;
- Nhiều JVM trên cùng node có thể giữ memory footprint cao hơn;
- Cấu hình không còn phù hợp khi container limit được giảm;
- Bộ nhớ đặt dành cho heap có thể làm ứng dụng thiếu không gian cho JNI/direct buffers.

**Cách làm đúng:** chọn initial heap theo **allocation profile + startup/warmup benchmark**, không chỉ vì “container có 1 GiB nên cứ đặt 50%”.

### 13.3. `-Xms` cố định khác percentage scaling

Khi dùng:
- `-Xms256m`: initial/minimum heap **256 MiB** dù container có 1 GiB hay 2 GiB (trong điều kiện JVM khởi động được);
- `-XX:InitialRAMPercentage=10`: initial sizing **tỷ lệ** theo RAM hiệu dụng mà VM nhận được.

Percentage phù hợp khi cùng application image chạy ở các memory tiers khác nhau. `-Xms` phù hợp khi muốn dự đoán một mức sàn cố định. Không có một lựa chọn đúng cho mọi workload.

## 14. `-XX:+AlwaysPreTouch` có làm thay ý nghĩa cờ initial?

`-XX:+AlwaysPreTouch` yêu cầu JVM **touch** các pages mà heap cam kết ở startup, thay vì đợi ứng dụng chạm dần theo cách hệ điều hành quản lý page faults.

Tác động có thể gồm:
- Tăng thời gian khởi động;
- Làm memory trở thành resident sớm hơn;
- Giảm một số page-fault overhead sau startup;
- Làm áp lực memory rõ hơn tại thời điểm container vừa khởi động.

Nó **không đổi định nghĩa** `InitialRAMPercentage` thành “hard process memory cap”. Đây là flag về **chiến lược sờ/khởi tạo trang**, không phải thay thế `MaxRAMPercentage`.

Nếu đang có memory limit chặt và startup burst:
- Đo cả **startup RSS**, **time-to-ready** và **GC**;
- Xem `AlwaysPreTouch` có thật sự cần không;
- Không bắt chước blindly cấu hình từ server on-prem nhiều RAM.

## 15. Java heap và direct/native memory — chương trình hoàn chỉnh 2

Tạo **`HeapAndDirectDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

public class HeapAndDirectDemo {
    public static void main(String[] args) {
        long maxBefore =
                ManagementFactory.getMemoryMXBean()
                    .getHeapMemoryUsage().getMax();

        byte[][] arrays = new byte[4][];
        for (int i = 0; i < arrays.length; i++) {
            arrays[i] = new byte[1024 * 1024];
            arrays[i][0] = (byte) i;
        }

        ByteBuffer direct =
                ByteBuffer.allocateDirect(4 * 1024 * 1024);
        direct.put(0, (byte) 77);

        System.out.println(
                "heapArraysMiB=" + arrays.length);
        System.out.println(
                "directBufferMiB=" +
                    direct.capacity() / (1024 * 1024));
        System.out.println(
                "isDirect=" + direct.isDirect());
        System.out.println(
                "firstHeapByte=" + arrays[0][0]);
        System.out.println(
                "firstDirectByte=" + direct.get(0));

        System.out.println(
                "heapMaximumSame=" +
                    (maxBefore ==
                     ManagementFactory.getMemoryMXBean()
                         .getHeapMemoryUsage().getMax()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 HeapAndDirectDemo.java
java -Xms64m -Xmx128m HeapAndDirectDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

```text
heapArraysMiB=4
directBufferMiB=4
isDirect=true
firstHeapByte=0
firstDirectByte=77
heapMaximumSame=true
```

### 15.1. Đọc kết quả

- `byte[][] arrays` và bốn `byte[]` là **Java heap objects**;
- `ByteBuffer.allocateDirect(...)` cấp phát vùng lưu dữ liệu direct buffer **ngoài Java heap** (đối tượng wrapper/metadata Java vẫn là Java object);
- Cả hai cùng tiêu tốn tài nguyên của một tiến trình;
- Max heap `-Xmx128m` không bị thay đổi vì chỉ có một direct buffer;
- Kết quả không nói tổng RSS chỉ là 8 MiB: JVM còn nhiều thành phần memory khác.

### 15.2. Vì sao không thể lấy `MaxRAMPercentage=100` cho container?

Nếu max heap được phép gần bằng toàn bộ container limit, các vùng ngoài heap có thể khiến process vượt limit. Tình trạng có thể xấu đi ở ứng dụng:
- Nhiều threads và thread stacks;
- Nhiều class/metaspace;
- NIO/direct buffers;
- Native libraries/JNI;
- JIT code cache;
- Mmap/cache/network frameworks.

Do đó phải để **headroom** hợp lý, dựa vào đo đạc chứ không chỉ toán học heap.

## 16. Quan sát tổng memory với NMT và công cụ container

### 16.1. Native Memory Tracking

HotSpot có **Native Memory Tracking (NMT)** cho nhiều hạng mục native memory. Có thể bật ở startup:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Trong một process JVM khác hoặc shell chẩn đoán tương ứng, dùng:

```bash
jcmd PID VM.native_memory summary
```

Ở đây `PID` là **mã tiến trình JVM cần kiểm tra**, không phải literal command sẽ chạy thành công nếu chưa thay số PID.

NMT cho biết các category như Java Heap, Class/Metaspace, Thread, Code, GC và Internal theo HotSpot. Nó **không phải trình đo toàn bộ mọi malloc của mọi native library một cách hoàn hảo**; kết hợp với OS/cgroup metrics để đánh giá RSS/memory pressure.

### 16.2. Container metrics

Trong Linux container/Kubernetes, xem:
- Memory current/usage theo cgroup;
- Container working set/RSS theo runtime và monitoring stack;
- Memory limit;
- OOM events;
- Java heap used/committed/max;
- NMT nếu cần;
- Thread count và direct-buffer usage khi phù hợp.

**Không so sánh đơn giản “JVM heap used < container limit” rồi kết luận đủ RAM**. Hãy tính cả committed/native/page-cache accounting phù hợp và peak memory.

### 16.3. Heap có thể co sau GC

Với những GC/runtime cho phép heap shrinkage, initial không có nghĩa “bộ nhớ này luôn bị giữ suốt đời process”. Ngược lại, có những flags/minimum constraints có thể làm heap khó co xuống.

Khi dùng `-Xms`, HotSpot thường đặt minimum heap tương ứng, khiến vùng heap không co thấp hơn mức đó theo chính sách. Khi chỉ dùng `InitialRAMPercentage`, minimum có thể thấp hơn nhiều như đã thấy trong thí nghiệm.

## 17. Tối ưu startup đúng cách: thay đổi từng biến

Một quy trình an toàn:

1. Giữ nguyên image ứng dụng, image JDK và resource limits;
2. Đo thời gian **process start → readiness** và số GC trong startup;
3. Ghi giá trị `InitialHeapSize`, `MinHeapSize`, `MaxHeapSize` thực tế;
4. Kiểm tra container memory current/peak và CPU quota;
5. Chọn một vài mức initial percentage để thử (ví dụ **5%**, **10%**, **20%** trong môi trường thử nghiệm);
6. Giữ `MaxRAMPercentage` cố định khi cần cô lập tác động của initial heap;
7. Đo trên nhiều lần và xem p50/p95 startup, GC counts, RSS và OOM;
8. Chỉ đưa cấu hình vào production nếu có lợi ích ổn định, còn đủ native-memory headroom.

**Không khuyến nghị cụ thể 5/10/20% cho tất cả sản phẩm.** Chúng chỉ là **mức thí nghiệm**, kết quả cuối phải theo profiling của ứng dụng.

### 17.1. Tại sao không đặt cùng lúc quá nhiều flags?

Nếu vừa đổi `InitialRAMPercentage`, `MaxRAMPercentage`, `MaxGCPauseMillis`, GC, CPU quota, thread count và container memory limit, rất khó biết thay đổi nào tác động đến startup.

Hãy cô lập biến và log chính xác cấu hình của từng run.

### 17.2. Mục tiêu là production behavior, không phải chỉ heap number

Một initial heap lớn hơn không có giá trị nếu:
- Time-to-ready không cải thiện;
- OOMKilled tăng;
- RSS peak vượt budget;
- GC trong giai đoạn bình thường xấu đi;
- Nhiều bản sao Pod trên một node làm tổng memory overhead tăng.

Một initial nhỏ cũng không tốt nếu startup chịu rất nhiều GCs và heap expansion, làm rollout chậm. Cần cân bằng theo workload.

## 18. Những lỗi cấu hình phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`InitialRAMPercentage=10` đặt max heap 10% RAM.” | **Không**. Nó đặt tỷ lệ tính **initial heap**. |
| “`MaxRAMPercentage=60` có nghĩa JVM dùng 60% RAM ngay khi start.” | **Không**. Nó liên quan **maximum heap**. |
| “`MinRAMPercentage=50` đặt minimum heap 50% RAM.” | **Không**. Nó liên quan **maximum heap với RAM nhỏ**. |
| “10% của container 1 GiB là chắc chắn đúng 102.4 MiB initial.” | Chưa chắc. HotSpot ergonomics/alignment có thể cho 104 MiB. |
| “Chỉ cần thấy flag `InitialRAMPercentage=10` là initial heap phải bằng 10%.” | `-Xms` có thể ghi đè initial size; xem `InitialHeapSize`. |
| “`-XX:MaxRAM=1g` tạo ra container limit 1 GiB.” | Không. Nó là **input sizing** cho JVM. |
| “`-Xmx` là tổng bộ nhớ process.” | Không. Nó là cap của Java heap. |
| “Heap used thấp nghĩa container không thể OOM.” | Sai. Native/direct/metaspace/stacks cũng tiêu tốn RAM. |
| “`-Xms` chỉ đặt initial, không liên quan minimum.” | Trên HotSpot, nó đặt cả initial và minimum theo tài liệu. |
| “Initial heap phải bằng committed heap ở mọi mili giây.” | Không. GC ergonomics và thời điểm đo có thể làm committed khác. |
| “Docker host có 64 GiB thì container 1 GiB cũng sizing theo 64 GiB.” | JDK hiện đại có container support sẽ xét giới hạn container. |
| “Java 10 container support bảo đảm mọi cgroups v2 hiện tại.” | Không. Cần JDK cập nhật hỗ trợ cgroups v2. |
| “`-XshowSettings:vm` luôn cho tất cả initial/min/max flags.” | Không. Dùng `PrintFlagsFinal` hoặc MXBean. |
| “Đặt initial lớn sẽ bảo đảm startup nhanh hơn.” | Không. Cần benchmark; có thể tốn RSS/pre-touch. |
| “`AlwaysPreTouch` làm heap maximum tăng.” | Không. Nó đổi cách touch memory pages. |
| “OOMKilled giống Java OutOfMemoryError.” | Khác cơ chế; cgroup SIGKILL có thể xảy ra không có Java stack trace. |
| “Tăng initial heap sẽ sửa OOMKilled.” | Không có cơ sở; có thể làm tình hình tệ hơn. |
| “Container request memory là JVM memory limit.” | Thường JVM sizing theo **limit** được cgroup enforce, không phải scheduling request. |
| “Dùng flags `InitialRAMFraction` trên JDK mới tốt hơn.” | Không. Những dạng Fraction cũ đã deprecated/removed; dùng Percentage. |

## 19. Checklist code review và deployment

- [ ] Đã xác định mục tiêu là **initial heap**, không phải maximum?
- [ ] `InitialRAMPercentage` có được ghi đúng dạng số phần trăm, không có ký hiệu `%`?
- [ ] Có hiểu default 1.5625% là default của JDK được tài liệu hóa, không phải giá trị cố định mọi VM?
- [ ] Có đọc đúng giá trị `InitialHeapSize` sau ergonomics/alignment?
- [ ] Có xem `MinHeapSize` để tránh nhầm initial với minimum?
- [ ] `-Xms` hoặc `InitialHeapSize` có vô tình ghi đè percentage không?
- [ ] `-Xmx` có ghi đè chính sách max percentage không?
- [ ] Có phân biệt `MinRAMPercentage` với minimum heap không?
- [ ] Nếu test dùng `MaxRAM=1g`, có ghi rõ đó **không phải Docker limit** không?
- [ ] JDK trên Linux có nhận đúng cgroup memory limit không?
- [ ] Có kiểm tra cgroups v1/v2 tương thích với JDK version không?
- [ ] Có dùng container memory **limit** thay vì mặc định suy theo **request** không?
- [ ] Có để headroom cho metaspace/direct buffers/thread stacks/JIT/GC/native?
- [ ] Có phân biệt `OutOfMemoryError` với cgroup OOMKilled?
- [ ] Có log startup GC, heap committed, heap max và RSS peak?
- [ ] Nếu dùng `AlwaysPreTouch`, có đo time-to-ready và memory peak không?
- [ ] Có tránh ép một giá trị `InitialRAMPercentage` duy nhất cho mọi workloads?
- [ ] Có đo benchmark nhiều lần và so cùng JDK/CPU/memory limit không?
- [ ] Có xác nhận production không bị ảnh hưởng vì nhiều flags khác nguồn cùng được inject?
- [ ] Có cập nhật JDK thay vì giữ runtime cũ chỉ vì các flag Fraction legacy?

### 19.1. Ví dụ nhận xét review

> “Cấu hình này đặt `InitialRAMPercentage=50` vì muốn dùng 50% RAM làm giới hạn heap. Đây là nhầm lẫn: nó chỉ tác động đến **heap ban đầu**. Nếu muốn cap max heap theo limit container, hãy xem `MaxRAMPercentage` hoặc `-Xmx`, và vẫn cần chừa native-memory headroom.”

Một nhận xét khác:

> “Pod đã có `-Xms256m`, nên `InitialRAMPercentage=10` không quyết định actual initial heap. Hãy chọn một cơ chế rõ ràng và kiểm chứng `InitialHeapSize` qua HotSpot flags.”

## 20. Tự kiểm tra kiến thức

**1.** `-XX:InitialRAMPercentage=10` có nghĩa gì?

**Đáp án:** Initial Java heap được chọn từ **10% của effective sizing RAM trước ergonomics**, không phải hard limit của tổng process memory.

**2.** Container có limit 1 GiB, raw initial 10% là bao nhiêu?

**Đáp án:** **102.4 MiB** trước alignment/ergonomics.

**3.** Vì sao trong OpenJDK 24.0.2 demo lại được 104 MiB?

**Đáp án:** Vì HotSpot/G1 áp dụng heap alignment và ergonomics; raw calculation không phải final bytes.

**4.** `InitialRAMPercentage` đặt minimum heap không?

**Đáp án:** Không nhất thiết. Trong demo, `InitialHeapSize=104MiB` nhưng `MinHeapSize=8MiB`.

**5.** `MaxRAMPercentage` điều khiển gì?

**Đáp án:** Maximum heap sizing trước ergonomics, không phải initial heap.

**6.** `MinRAMPercentage` đặt minimum heap?

**Đáp án:** Không. Nó liên quan maximum heap sizing ở môi trường RAM nhỏ.

**7.** Có `-Xms256m` và `InitialRAMPercentage=10`, initial heap thực tế là gì trong demo?

**Đáp án:** **256 MiB**, do `-Xms`.

**8.** Có `-Xmx320m` và `MaxRAMPercentage=60`, max heap là gì trong demo?

**Đáp án:** **320 MiB**, do `-Xmx`.

**9.** `MaxRAM=1g` có giới hạn RAM container không?

**Đáp án:** Không. Nó chỉ đặt RAM basis dùng trong JVM ergonomics.

**10.** Vì sao không đặt max heap bằng đúng hard memory limit của container?

**Đáp án:** Vì tiến trình Java cần memory ngoài heap (direct buffers, metaspace, thread stacks, code cache...), có thể bị OOMKilled.

**11.** `-XshowSettings:system` phù hợp trên nền nào?

**Đáp án:** **Linux**, để xem host/container configuration theo Java launcher docs.

**12.** Vì sao Java 10 container support không bảo đảm nhận diện tốt cgroups v2 hiện đại?

**Đáp án:** Cgroups v2 được hỗ trợ trong các phiên bản JDK về sau và các bản backport; cần dùng runtime đã cập nhật.

**13.** Tại sao `HeapSizingDemo` dùng `HotSpotDiagnosticMXBean`?

**Đáp án:** Để đọc **effective VM flags** như `InitialHeapSize` và `MaxHeapSize` thay vì chỉ suy đoán theo phần trăm.

**14.** Một `DirectByteBuffer` lớn tiêu tốn memory ở đâu?

**Đáp án:** Dữ liệu của direct buffer được cấp ngoài Java heap, vẫn tính vào memory của tiến trình/container theo OS accounting.

**15.** `-XX:+AlwaysPreTouch` có thể tác động đến startup ra sao?

**Đáp án:** Touch các trang heap sớm có thể tăng startup time và memory residency; cần benchmark.

**16.** `initial heap 10%` có nghĩa ứng dụng không thể dùng quá 10% heap trong runtime?

**Đáp án:** Không. JVM có thể mở rộng heap tới maximum đã đặt.

**17.** Khi Pod bị OOMKilled, tăng initial percentage có chắc giúp không?

**Đáp án:** Không. Có thể làm peak memory tệ hơn. Cần kiểm tra cgroup memory usage, native memory, heap, allocation và giới hạn.

**18.** Điều gì nên đo trước/sau khi tăng initial percentage?

**Đáp án:** Actual InitialHeapSize, time-to-ready, GC trong startup, memory peak, RSS/working set và tần suất lỗi OOM.

## 21. Nguồn tham khảo chính thức

- [Oracle JDK 10 Release Notes — Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): thay đổi **JDK-8146115**, **JDK-8186248** và ba flags Percentage xuất hiện ở Java 10.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `InitialRAMPercentage` default 1.5625, `MaxRAMPercentage` default 25, `MinRAMPercentage` default 50 cho small heaps; quan hệ với `-Xms`, `-Xmx`, `MaxRAM`; `UseContainerSupport`, `-XshowSettings:system` và logging.
- [Oracle Java SE 25 — Factors Affecting Garbage Collection Performance](https://docs.oracle.com/en/java/javase/25/gctuning/factors-affecting-garbage-collection-performance.html): reserved/committed heap, cách heap có thể tăng/giảm và tương tác initial/max.
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): xác nhận flags Percentage được hỗ trợ trên một JDK LTS hiện đại.
- [Oracle Java SE 25 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): ý nghĩa `init`, `used`, `committed`, `max`.
- [Oracle Java SE 25 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): API theo dõi Java heap và non-heap memory.
- [Oracle Java SE 25 — `HotSpotDiagnosticMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): đọc HotSpot VM flags bằng `getVMOption`.
- [Oracle JDK 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): theo dõi các hạng mục native memory và `jcmd VM.native_memory`.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): phân biệt `requests.memory` và `limits.memory`, cơ chế memory limits.
- [Kubernetes — About cgroup v2](https://kubernetes.io/docs/concepts/architecture/cgroups/): cgroups v1/v2 và yêu cầu JDK hỗ trợ container.
- [Red Hat Developers — Java 17 Container Awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): bối cảnh hỗ trợ cgroups v2 từ OpenJDK 15 và các nhánh LTS backport.

**Kết luận:** **`-XX:InitialRAMPercentage` quyết định cơ sở tính kích thước Java heap ban đầu, không phải giới hạn heap tối đa hay toàn bộ RSS của container.** Trên Linux có container awareness, RAM basis thường phản ánh giới hạn memory của container; HotSpot vẫn áp dụng ergonomics/alignment, và `-Xms` có thể thay thế quyết định theo phần trăm. Khi vận hành, luôn đọc **effective `InitialHeapSize`/`MaxHeapSize`**, chừa budget cho native memory và đo startup/GC/RSS thực tế.