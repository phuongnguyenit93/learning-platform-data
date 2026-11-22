# Live set, allocation rate và vùng nhớ dự phòng cho GC độ trễ thấp trong Java

> **Ngữ cảnh:** Chủ đề **GC độ trễ thấp**, module Java 15. Bài tập trung vào ba đại lượng phải được xem **cùng lúc** khi thiết kế heap cho các bộ thu gom đồng thời hiện hành: **live set** (dữ liệu còn sống), **allocation rate** (tốc độ cấp phát đối tượng) và **headroom** (vùng nhớ còn dự phòng cho hoạt động của ứng dụng và GC). Các nguyên tắc vẫn áp dụng với JDK 17, 21, 25 và các bản Java mới. Ví dụ thực hành dùng **Java 17+** và API/cờ được hỗ trợ hiện nay. Đặc biệt, **ZGC từ JDK 24 chỉ còn chế độ generational**; không sử dụng hướng dẫn bật/tắt chế độ non-generational đã bị loại bỏ.

## 1. Mục tiêu của GC độ trễ thấp không phải chỉ là “GC ngắn”

Một ứng dụng yêu cầu phản hồi thấp thường quan tâm các chỉ số như độ trễ **p95/p99/p99.9**, thời gian tạm dừng (*stop-the-world pause*), thông lượng, mức sử dụng RAM và mức sử dụng CPU.

Các collector như **ZGC** thực hiện phần lớn công việc thu gom **đồng thời** với luồng ứng dụng. Điều này giúp giảm các khoảng dừng dài, nhưng **không làm bộ nhớ trở thành vô hạn**.

Khi GC chạy, chương trình Java vẫn có thể tạo đối tượng mới:

```text
Thời gian
   |
   +---- Mutator (luồng ứng dụng): allocate, xử lý request, allocate...
   |
   +---- Concurrent GC: truy vết, thu hồi, di chuyển dữ liệu...
   |
   +---- Hạn mức heap (-Xmx): vẫn là một giới hạn hữu hạn
```

Nếu lượng bộ nhớ ứng dụng cần cấp phát **tăng quá nhanh** so với khả năng GC thu hồi và phần heap đang sẵn có, ứng dụng có thể gặp **allocation stall** (chờ có bộ nhớ để cấp phát), tăng tail latency, áp lực CPU, hoặc cuối cùng là lỗi thiếu bộ nhớ.

Vì vậy không thể chỉ hỏi “live set là 3 GiB, vậy `-Xmx3g` được không?”. Câu hỏi đúng hơn là:

> Heap có đủ để giữ **dữ liệu đang sống**, chứa **các cấp phát mới trong thời gian GC cần để bắt kịp**, và có **biên an toàn cho biến động thực tế** không?

## 2. Ba khái niệm cốt lõi

| Đại lượng | Ý nghĩa | Đơn vị phổ biến | Sai lầm dễ gặp |
| --- | --- | --- | --- |
| **Live set** | Tập các đối tượng trên Java heap **vẫn reachable** và cần được giữ lại tại một thời điểm/pha quan sát | MiB, GiB | Nhầm mọi byte `heap used` với đối tượng thật sự còn sống |
| **Allocation rate** | Tốc độ ứng dụng tạo/cấp phát đối tượng trên Java heap theo thời gian | MiB/s, GiB/s | Đo bằng `heap used` tăng/giảm rồi cho rằng đó là lượng đã cấp phát |
| **Headroom** | Phần heap còn có thể sử dụng, bên ngoài mức đang chiếm giữ cần thiết; là bộ đệm cho cấp phát/GC | MiB, GiB hoặc % | Chỉ đặt `-Xmx` bằng live set, bỏ qua cấp phát khi GC đang chạy |

Đây là **các biến liên quan nhưng không đồng nhất**. Live set lớn không nhất thiết có allocation rate lớn; allocation rate cao không tự động gây memory leak; một heap có dung lượng lớn nhưng headroom thực tế nhỏ vẫn có thể gặp allocation stall.

### 2.1. Live set là gì?

Một đối tượng thuộc live set khi nó vẫn **reachable** từ GC roots, ví dụ các tham chiếu trên stack, trường static, object graph đang được giữ bởi ứng dụng, hoặc những root khác mà JVM công nhận.

```text
GC roots
   |
   +--> cache -------------------> Object A ---> Object B
   |
   +--> request đang xử lý -----> Object C
   |
   +--> trạng thái service -----> Object D

Object E (không còn reachable) ---> ứng viên thu hồi
```

Ví dụ:

```java
List<byte[]> cache = new ArrayList<>();
cache.add(new byte[1024 * 1024]);
```

Miễn là `cache` và phần tử của nó còn reachable, mảng byte 1 MiB này đóng góp vào dữ liệu sống (cộng metadata/overhead của object). Ngược lại:

```java
byte[] temp = new byte[1024 * 1024];
use(temp);
temp = null;
```

Đây là các **snippet**, không phải chương trình độc lập; `use` là phương thức do ứng dụng định nghĩa. Gán `temp=null` không buộc GC chạy và cũng không chứng minh toàn bộ object graph đã hết tham chiếu. Điều quan trọng là đối tượng **còn reachable hay không** tại các điểm mà JVM tính liveness.

**Live set không bằng “heap used ngay bây giờ”.** `heap used` có thể bao gồm đối tượng đã không còn reachable nhưng **chưa được thu hồi**, dữ liệu đang trong những pha GC khác nhau, đối tượng thuộc các thế hệ khác nhau, và overhead tùy collector. Với GC chạy đồng thời, không có nghĩa mọi số đo là một ảnh chụp toàn cục chính xác của toàn bộ live set.

### 2.2. Allocation rate là gì?

Allocation rate biểu diễn lượng bộ nhớ **được yêu cầu cấp phát cho object mới trong một khoảng thời gian**, chia cho độ dài khoảng đó:

```text
allocation_rate = allocated_bytes_during_interval / interval_seconds
```

Ví dụ nếu ứng dụng đã cấp phát tổng cộng **1.5 GiB đối tượng heap trong 2 giây**, allocation rate trung bình là **0.75 GiB/s** trong khoảng quan sát đó.

Một ứng dụng có thể có:

- **Live set 3 GiB, allocation rate 0.05 GiB/s:** phần lớn dữ liệu sống lâu, ít đối tượng tạm.
- **Live set 0.5 GiB, allocation rate 2 GiB/s:** nhiều đối tượng được tạo rồi nhanh chóng chết.
- **Live set 3 GiB, allocation rate tăng từ 0.5 lên 2 GiB/s theo burst:** cần dự phòng cho đỉnh tải, không chỉ dựa trên số trung bình cả giờ.

**Phân biệt:** `heapUsed(t2) - heapUsed(t1)` không phải tổng số bytes đã allocate giữa `t1` và `t2`. Trong khoảng đó GC có thể đã thu hồi rất nhiều object. Tốc độ tăng heap used thấp **không chứng minh** allocation rate thấp.

### 2.3. Headroom là gì?

Ở mức ngân sách đơn giản:

```text
maxHeap = -Xmx
occupiedHeap = lượng heap đang chiếm giữ ở thời điểm đo

headroom_now ≈ maxHeap - occupiedHeap
```

Nhưng đối với **concurrent GC**, phần “còn trống” tại một thời điểm chưa hẳn là toàn bộ dự phòng **hữu dụng**. Một số bộ nhớ có thể đang được GC dùng cho di chuyển/relocation, object chưa được thu hồi, metadata theo cấu trúc collector hoặc chịu các ràng buộc khác.

Vì vậy cần phân biệt:

- **Dự phòng theo hạn mức:** `-Xmx - heapUsed`, một phép tính thô từ số liệu.
- **Dự phòng cần thiết theo tải:** lượng bộ nhớ mà ứng dụng cần trong lúc GC đang thu hồi và khi tải tăng đột ngột.
- **Bộ nhớ vật lý còn sẵn:** RAM hoặc memory limit của container trừ **tất cả** thành phần bộ nhớ tiến trình/OS; không đồng nghĩa với `-Xmx - heapUsed`.

**Không dùng mọi con số “free memory” làm cùng một đại lượng.** `Runtime.freeMemory()` nói về free space bên trong mức heap **đã được JVM cam kết/committed** theo cách triển khai, không phải chênh lệch đến `-Xmx` hoặc toàn bộ RAM vật lý còn rảnh.

## 3. Vòng đời phân bổ bộ nhớ của ứng dụng và GC

Hình dung một heap tại thời điểm GC bắt đầu:

```text
Hạn mức tối đa (-Xmx)
+------------------------------------------------------------------+
| Live set cần giữ | Đối tượng chết chưa reclaim | Free/headroom  |
+------------------------------------------------------------------+
     ^                          ^                     ^
     |                          |                     |
     | chưa thể thu hồi         | sẽ thu hồi khi GC    | phục vụ allocation
     v                          v                     v

Concurrent GC bắt đầu
       |
       +--> Các luồng Java vẫn allocate object mới
       +--> Một số object cũ vẫn sống; một số object chết
       +--> Collector truy vết/thu hồi/di chuyển tùy thuật toán
       |
       v
Concurrent GC hoàn tất hoặc bắt kịp
```

Điều này tạo ra hai áp lực:

**Áp lực giữ đối tượng sống:** nếu nhiều object trong một cache, queue, session hoặc graph còn reachable, GC **không được phép** thu hồi chúng chỉ vì cần thêm chỗ. Live set lớn làm giảm ngân sách dành cho cấp phát mới.

**Áp lực cấp phát:** khi yêu cầu tạo object mới dồn dập trong thời gian GC chưa trả lại đủ memory, headroom bị tiêu hao. Với collector đồng thời, khả năng giữ latency thấp phụ thuộc vào **đủ thời gian và tài nguyên để GC bắt kịp**.

Các thông số này phải xem **trong cùng cửa sổ tải**: live set ở lúc tải cao, allocation rate ở đỉnh request, và thời gian GC cần trong chính điều kiện CPU/memory đó.

## 4. Mô hình ngân sách heap: live set + cấp phát khi GC chạy + biên an toàn

Một mô hình thô, hữu ích để bắt đầu suy nghĩ:

```text
H_required ≳ L_peak + A_peak × T_concurrent + S

Trong đó:
H_required  = mức heap cần thử nghiệm (GiB)
L_peak      = live set cao nhất có ý nghĩa trong workload (GiB)
A_peak      = allocation rate ở giai đoạn tải cao (GiB/s)
T_concurrent= thời gian GC cần để theo kịp áp lực (s)
S           = safety margin cho burst, fragmentation, relocation,
              đối tượng chưa reclaim, độ bất định đo đạc... (GiB)
```

**Đây là mô hình ước lượng, KHÔNG phải công thức sizing chính xác của JVM.** Trong thực tế GC có thể thu hồi trong khi ứng dụng vẫn allocate, có generational collection khác nhau, và throughput của collector thay đổi theo CPU, loại object, live data, write barriers, heap occupancy và nhiều yếu tố.

Công thức trên giúp **không bỏ sót** ba nguồn áp lực, chứ không đủ để chứng minh một `-Xmx` bất kỳ chắc chắn tránh allocation stall. Không lấy `T_concurrent` bằng thời gian **STW pause**: đây là hai thời lượng hoàn toàn khác.

### Ví dụ số: cùng live set, tải bình thường và tải tăng vọt

Giả sử một service có:

- Live set đỉnh đã ước lượng: **3.00 GiB**.
- Allocation rate bình thường ở giai đoạn quan tâm: **0.75 GiB/s**.
- Allocation rate khi burst: **1.50 GiB/s**.
- Giả định thời gian cửa sổ GC cần theo kịp: **2.00 giây**.
- Biên an toàn tạm chọn để thử nghiệm: **0.75 GiB**.
- Heap đang cân nhắc: **`-Xmx6g`**.

Tính:

```text
Bình thường:
  allocation during 2s ≈ 0.75 × 2 = 1.50 GiB
  rough budget ≈ 3.00 + 1.50 + 0.75 = 5.25 GiB
  -Xmx6g: trong hạn mức mô hình (còn 0.75 GiB so với budget)

Khi burst:
  allocation during 2s ≈ 1.50 × 2 = 3.00 GiB
  rough budget ≈ 3.00 + 3.00 + 0.75 = 6.75 GiB
  -Xmx6g: thiếu 0.75 GiB theo mô hình
```

Ví dụ **không nói** một ứng dụng thật sẽ OOM ở `-Xmx6g`; GC có thể reclaim đồng thời trước khi tiêu hết chỗ. Nó cũng không bảo đảm `-Xmx8g` là đủ. Nó minh họa vì sao chỉ xem **live set 3 GiB** rồi chọn heap 3–4 GiB không phản ánh đầy đủ tác động của burst và tốc độ GC.

### Bài tập mô hình bằng Java, stdout xác định

Tạo tệp **`HeadroomBudgetDemo.java`**:

```java
import java.util.Locale;

public class HeadroomBudgetDemo {
    private static double estimatedBudget(
            double liveGiB, double rateGiBPerSec,
            double gcSeconds, double safetyGiB) {
        return liveGiB + rateGiBPerSec * gcSeconds + safetyGiB;
    }

    private static void report(
            String scenario, double rate,
            double live, double gcSeconds,
            double safety, double heapLimit) {
        double pending = rate * gcSeconds;
        double budget =
                estimatedBudget(live, rate, gcSeconds, safety);

        System.out.printf(Locale.ROOT,
                "%s.allocatedDuringCycle=%.2f GiB%n",
                scenario, pending);
        System.out.printf(Locale.ROOT,
                "%s.estimatedBudget=%.2f GiB%n",
                scenario, budget);
        System.out.println(scenario + ".fits6GiB="
                + (budget <= heapLimit));
    }

    public static void main(String[] args) {
        double liveGiB = 3.0;
        double gcSeconds = 2.0;
        double safetyGiB = 0.75;
        double maxHeapGiB = 6.0;

        System.out.printf(Locale.ROOT,
                "live=%.2f GiB%n", liveGiB);
        System.out.printf(Locale.ROOT,
                "maxHeap=%.2f GiB%n", maxHeapGiB);

        report("steady", 0.75,
                liveGiB, gcSeconds, safetyGiB, maxHeapGiB);
        report("burst", 1.50,
                liveGiB, gcSeconds, safetyGiB, maxHeapGiB);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 HeadroomBudgetDemo.java
java HeadroomBudgetDemo
```

**Stdout chính xác:**

```text
live=3.00 GiB
maxHeap=6.00 GiB
steady.allocatedDuringCycle=1.50 GiB
steady.estimatedBudget=5.25 GiB
steady.fits6GiB=true
burst.allocatedDuringCycle=3.00 GiB
burst.estimatedBudget=6.75 GiB
burst.fits6GiB=false
```

Đây là **mô hình toán học độc lập**, không điều khiển JVM thật và không đo GC. Đọc `fits6GiB` như **kết quả so sánh trong mô hình**, không phải bằng chứng rằng ứng dụng thực chắc chắn đạt SLO hay chắc chắn thất bại.

## 5. Live set khác heap used, committed, reserved và RSS

Những chỉ số cùng mang đơn vị byte nhưng nói về **những lớp khác nhau**:

| Tên | Bản chất | Cách hiểu |
| --- | --- | --- |
| **Live set** | Đối tượng mà GC phải giữ vì vẫn reachable | Không có một thuộc tính chuẩn đơn giản luôn đo chính xác mọi thời điểm |
| **Heap used** | Phần heap JVM báo đang sử dụng ở thời điểm chụp | Gồm dữ liệu còn sống và có thể có dữ liệu chưa reclaim/overhead |
| **Heap committed/capacity** | Bộ nhớ heap JVM đang có để sử dụng theo cơ chế quản lý | Có thể thay đổi động, không nhất thiết bằng max heap |
| **Heap max (`-Xmx`)** | Hạn mức tối đa cho Java heap | Không phải số RAM đã được cấp phát vật lý ở thời điểm đó |
| **Reserved virtual address space** | Dải địa chỉ ảo JVM dành cho heap/cơ chế collector | Không đồng nhất với RAM thực đã sử dụng |
| **RSS/process memory** | Bộ nhớ resident của **toàn tiến trình** theo OS | Gồm heap và nhiều thành phần không nằm trong heap |
| **Container memory usage** | Tổng mức sử dụng theo cgroup/container | Có thêm các khoản mà cách kế toán của OS/container quy định |

Một service Java có thể có `-Xmx8g` nhưng `RSS` khác 8 GiB, do heap chưa fully committed hoặc do direct buffers, metaspace, stacks, JIT/code cache, native libraries và những thành phần khác.

### Vì sao `-Xmx` không thể bằng giới hạn RAM container?

Ví dụ container có memory limit **8 GiB** mà đặt `-Xmx8g` không chừa không gian cho:

- Metaspace và compressed class space.
- Thread stacks.
- Direct/native buffers, JNI, NIO và bộ nhớ của thư viện native.
- Code cache/JIT, GC metadata, JVM runtime.
- Memory-mapped files, page cache và các khoản khác tính theo môi trường OS/cgroup.

Kết quả có thể là **OOM kill của container/OS**, dù Java heap chưa chạm `-Xmx`. Cần một **ngân sách bộ nhớ cấp tiến trình** riêng với **headroom bên trong Java heap**.

### Quy tắc đo live set thực tế

Trong hệ thống production, có thể **ước lượng** live set qua:

- Đường cong **heap occupancy sau các chu kỳ collection thích hợp**, sau khi ứng dụng ổn định (*steady state*), không chỉ một snapshot.
- JFR/GC logs cho biết kích thước heap, collection cycle, heap used before/after và các dữ liệu collector phát ra.
- Phân tích object retention/cache/heap dump khi có nghi vấn memory leak và đã cân nhắc chi phí vận hành.

**Thận trọng với generational GC:** chỉ nhìn occupancy **sau young collection** không nhất thiết là live set toàn bộ heap. Young collection có thể chưa thu hồi các đối tượng chết ở old generation. Với ZGC generational và các collector đồng thời, dùng xu thế qua **nhiều chu kỳ phù hợp** thay vì khẳng định một lần quan sát sau GC là con số liveness tuyệt đối.

## 6. Allocation rate: tải trung bình không đủ, cần phân vị và burst

Giả sử hệ thống đo 60 giây:

```text
Giây 0-50:   150 MiB/s
Giây 50-55:  900 MiB/s
Giây 55-60:  150 MiB/s
```

Allocation trung bình toàn khoảng:

```text
(50 × 150 + 5 × 900 + 5 × 150) / 60
= (7500 + 4500 + 750) / 60
= 212.5 MiB/s
```

Nếu sizing chỉ dựa trên **212.5 MiB/s**, bạn có thể bỏ lỡ burst **900 MiB/s** kéo dài 5 giây — chính là loại burst làm headroom bị tiêu hao nhanh khi GC chưa theo kịp.

Cần xem:

1. **Allocation rate theo cửa sổ ngắn phù hợp** (ví dụ 1s, 5s, 30s), không chỉ average dài hạn.
2. **Đỉnh sustained rate** và tần suất burst.
3. **Concurrency**: thêm request đồng thời có làm object allocation per second tăng tuyến tính không?
4. **Đường cong live set** cùng thời điểm, vì cache/queue cũng có thể mở rộng khi burst.
5. **Tốc độ reclaim/GC cycle duration** và tài nguyên CPU collector đang có.
6. **Tail latency thực đo**: p99/p99.9 phản ánh ảnh hưởng của allocation stall hoặc cạnh tranh CPU.

### Allocation rate cao có đồng nghĩa leak?

**Không.** Một chương trình có thể cấp phát hàng GiB object mỗi giây, nhưng phần lớn object chết rất nhanh; live set vẫn ổn định. Điều này tạo áp lực GC chứ không tự chứng minh memory leak.

Ngược lại, một ứng dụng cấp phát vừa phải nhưng cache/queue **không giải phóng tham chiếu** có thể khiến live set tăng liên tục, dù allocation rate không cao.

Phân biệt bằng số liệu:

| Hiện tượng | Allocation rate | Live set qua thời gian | Khả năng thường xét |
| --- | --- | --- | --- |
| Nhiều object tạm thời | Cao | Gần ổn định | Áp lực cấp phát/GC throughput |
| Cache lớn có giới hạn | Vừa/cao | Ổn định ở mức cao | Heap cần chứa retained data |
| Queue bị tắc | Có thể cao | Tăng theo backlog | Backpressure, giới hạn queue, consumer chậm |
| Memory leak/retention ngoài ý muốn | Bất kỳ | Tăng bền vững sau collection | Đường giữ tham chiếu, cache không eviction |
| Burst ngắn | Tăng mạnh tạm thời | Có thể tăng rồi giảm | Dự phòng headroom, burst protection |

Đừng “sửa” memory leak bằng cách chỉ tăng heap mà không xử lý retained objects. Heap lớn hơn có thể chỉ trì hoãn lúc hết bộ nhớ.

## 7. ZGC hiện hành: tính toán headroom dựa trên live set và allocation rate

ZGC là bộ thu gom đồng thời, độ trễ thấp của HotSpot. Hướng dẫn Oracle về ZGC hiện hành khuyến nghị **tuning từ `-Xmx`**, vì heap cần đủ chứa **live set** và **dự phòng cấp phát khi collector còn đang làm việc**.

Với các bản Java hiện đại:

```bash
java -XX:+UseZGC -Xms1g -Xmx8g MyApp
```

Đây là **mẫu lệnh**: `MyApp` là tên class chính do ứng dụng cung cấp, không phải class có sẵn. Chỉ dùng khi máy/container có đủ memory budget và workload thật sự phù hợp.

### Cập nhật quan trọng của JDK mới

- Java 15 là mốc lịch sử liên quan đến ZGC chính thức; nhưng không nên dùng nguyên các tuning guide cho các đời JDK cũ.
- **Từ JDK 24, ZGC chỉ còn chạy chế độ generational**; tùy chọn chọn non-generational hoặc `ZGenerational` cũ đã bị loại bỏ. **Không đưa `-XX:+ZGenerational` hoặc `-XX:-ZGenerational` vào cấu hình cho JDK 24/25+**.
- ZGC điều chỉnh một số quyết định nội bộ theo workload. Không nên bắt đầu bằng danh sách dài các cờ GC phức tạp chưa có dữ liệu hỗ trợ.
- Cờ `-XX:+UseZGC` vẫn được hỗ trợ để chọn ZGC. `-Xmx` là biến sizing cần kiểm tra đầu tiên.

### `-XX:SoftMaxHeapSize` là gì?

ZGC có tùy chọn:

```bash
java -XX:+UseZGC -Xmx8g -XX:SoftMaxHeapSize=6g MyApp
```

Ý nghĩa:

- `-Xmx8g` là **giới hạn cứng** của heap.
- `SoftMaxHeapSize=6g` là **mục tiêu mềm** mà heuristics ZGC cố giữ khi điều kiện cho phép.
- ZGC **có quyền vượt mức mềm lên tới `-Xmx`** khi cần để tránh stall do thiếu memory.
- Phần chênh **2 GiB** không nhất thiết đã là bộ nhớ vật lý **committed** hoặc chắc chắn cấp phát tức thì; đây là **khả năng tăng theo giới hạn**, không phải một vùng RAM được khóa riêng và đảm bảo luôn sẵn.
- Khi đã vượt ngưỡng mềm, ZGC vẫn phải dựa vào khả năng allocate, committed memory, CPU/GC activity và memory limit của tiến trình.

**Không dùng `SoftMaxHeapSize` như một cách “bảo đảm tối thiểu 2 GiB trống”.** Mọi giới hạn thực tế vẫn được đánh giá bằng dữ liệu live-set, allocation rate, GC stalls, RSS và tình trạng container.

### Khi nào cân nhắc tăng `-Xmx`?

Khi có bằng chứng:

- Live set/retention đã ổn định nhưng gần sát hạn mức.
- Allocation rate burst làm GC không bắt kịp và xuất hiện allocation stalls.
- CPU/collector đủ năng lực xử lý nếu được thêm chỗ/chu kỳ để thu hồi.
- Process/container còn đủ RAM cho **heap + non-heap**, không dẫn đến swapping hoặc OOM kill.

Tăng `-Xmx` thường giúp thêm headroom nhưng **không tự khắc phục** memory leak, CPU contention nghiêm trọng, latency từ I/O hoặc sự cố mạng.

### `-XX:ConcGCThreads` có nên chỉnh ngay?

ZGC có heuristic chọn số GC threads đồng thời. Tăng GC threads có thể giúp collector hoàn thành nhanh hơn nhưng **lấy CPU khỏi ứng dụng**; giảm quá mức có thể khiến GC không theo kịp allocation rate.

Quy trình tốt: để mặc định trước, đo **GC throughput, CPU saturation, latency và allocation stalls**, rồi mới thử chỉnh theo từng bước với workload đại diện. Không mặc định giá trị thích hợp cho mọi máy và không tối ưu chỉ một metric GC mà bỏ qua tail latency của request.

## 8. Shenandoah và các collector khác: nguyên tắc chung, chi tiết phụ thuộc runtime

**Shenandoah** cũng là một bộ thu gom concurrent low-pause trên các bản OpenJDK/JDK có tích hợp và bật hỗ trợ. Nó có chính sách dự trữ free heap và phản ứng trước allocation pressure; nhưng tên cờ, chế độ và sự hiện diện của Shenandoah **phụ thuộc bản build/JDK**.

Các nguyên tắc còn đúng:

- Heap phải chứa **dữ liệu sống**, có chỗ cho **cấp phát trong lúc GC hoạt động** và overhead liên quan.
- Allocation rate tăng nhanh có thể làm collector không theo kịp.
- CPU là tài nguyên chia sẻ giữa mutator và concurrent GC.
- Không thể đưa một tỷ lệ headroom cố định áp dụng an toàn cho mọi workload.
- Chính sách memory limit, container và native memory phải được xem xét riêng.

Với **G1** (một collector hiện hành khác), cơ chế và mục tiêu latency khác ZGC nhưng việc xem **live set, allocation rate, heap occupancy và pause** cũng quan trọng. Không tự coi thuật ngữ “low latency GC” là một loại collector duy nhất với cùng cờ tuning.

**Không sao chép cờ tuning của collector A sang collector B** rồi mong hành vi giống nhau. Luôn ghi rõ phiên bản JDK, collector được chọn, số CPU, cấu hình RAM/cgroup và khối lượng công việc dùng để đo.

## 9. Đo heap và allocation pressure bằng JFR, GC log, JMX

Kỹ thuật đo nên kết hợp **nhiều nguồn**, vì không chỉ một chỉ số đủ diễn giải ba khái niệm chính.

### 9.1. GC logs

Unified logging vẫn là cơ chế được hỗ trợ trên JDK hiện hành. Với một chương trình có tên class chính `MyApp`:

```bash
java -XX:+UseZGC -Xms512m -Xmx4g \
  -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
  MyApp
```

Đây là **lệnh minh họa shell kiểu Bash**; `MyApp` là ứng dụng phải tự cung cấp. Nếu dùng PowerShell/CMD, viết toàn bộ thành một dòng thay cho ký hiệu nối dòng `\`.

Log có thể cho thấy:

- Thời điểm bắt đầu/kết thúc GC cycle.
- Heap capacity/occupancy trước, trong hoặc sau các pha GC (tùy collector/tag/level).
- GC pauses và các phase được báo.
- Những dấu hiệu GC chạy quá thường xuyên hoặc gặp **allocation stall** khi thiếu headroom.
- Thời điểm vấn đề xảy ra, để đối chiếu với request load và allocation rate.

**Không giả định format log cố định giữa các phiên bản/collector.** Hãy đọc sự kiện và các tag thực tế của JVM, không viết parser chỉ dựa vào một câu tiếng Anh trong log.

### 9.2. Java Flight Recorder (JFR)

JFR là công cụ profiling hiện hành của JDK. Một ví dụ bật recording khi khởi động:

```bash
java -XX:+UseZGC -Xms512m -Xmx4g \
  -XX:StartFlightRecording=filename=run.jfr,settings=profile,dumponexit=true \
  MyApp
```

Hoặc với JVM đang chạy:

```bash
jcmd <PID> JFR.start name=gc-study settings=profile duration=60s filename=gc-study.jfr
```

Trong hai snippet này, thay `MyApp` bằng class ứng dụng và `<PID>` bằng process ID thật. **Không thực thi literal `<PID>`** trên shell; đó là placeholder lệnh chẩn đoán, không phải code trong chương trình Java. Khi JFR dump ra file, có thể xem:

```bash
jfr summary run.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.ObjectAllocationSample run.jfr
```

Các event và tần suất phụ thuộc JDK, collector và recording settings. `jdk.ObjectAllocationSample` là **sự kiện lấy mẫu**; **không** được lấy tổng kích thước của vài mẫu rồi xem đó là số bytes ứng dụng đã cấp phát chính xác. Dùng phân tích có trọng số/methodology hoặc công cụ chuyên dụng nếu cần allocation rate toàn JVM.

Với một workload ngắn, event có thể ít hoặc không đủ mẫu; **không** kết luận allocation rate bằng 0 chỉ vì JFR file không chứa sự kiện sampling mong muốn.

**Gợi ý:** dùng `settings=default` khi cần ghi liên tục với chi phí thấp, `settings=profile` cho giai đoạn phân tích ngắn theo khả năng runtime. Recording và log có thể chứa stack trace/class/method name hoặc metadata nhạy cảm, cần lưu trữ phù hợp.

### 9.3. JMX/MemoryMXBean: đo snapshot, không gọi là live set

Snippet trong một Java class:

```java
java.lang.management.MemoryUsage usage =
        java.lang.management.ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

long used = usage.getUsed();
long committed = usage.getCommitted();
long max = usage.getMax();
```

Đoạn này **không phải chương trình độc lập**; nó chỉ minh họa API hiện hành.

- `used`: JVM-reported used heap ở thời điểm lấy mẫu.
- `committed`: heap memory JVM đã committed theo mô hình quản lý.
- `max`: giới hạn tối đa nếu được định nghĩa; có thể trả `-1` trong trường hợp không được xác định.
- Không có phép gọi `getExactLiveSetBytes()` trong `MemoryMXBean`.

Nếu cần theo dõi time series, lấy mẫu có nhịp hợp lý và đặt cạnh GC logs/JFR. Đừng chia mọi `delta(used)` cho thời gian để khẳng định đó là allocation rate: GC có thể làm `used` giảm giữa hai mẫu.

### 9.4. Đo allocation rate đáng tin

Có thể ước lượng bằng một hoặc nhiều cách:

- Công cụ profiler/JFR cho **allocation sampling**, phân tích theo phương pháp được công cụ hỗ trợ.
- Các counter/metric allocated bytes theo thread/JVM do JDK hoặc công cụ giám sát cung cấp, khi được hỗ trợ, cộng và quy đổi qua khoảng thời gian.
- Benchmark có instrument để đếm **object allocations thực tế** theo vùng mã quan tâm, kết hợp với chỉ số JVM/OS.
- So sánh nhiều cửa sổ tải (steady và burst), không chỉ một snapshot.

Cần phân biệt **Java heap object allocation rate** và việc cấp phát bộ nhớ native/off-heap. `ByteBuffer.allocateDirect(...)` và một số thư viện native có thể tiêu thụ RAM ngoài Java heap nhưng không nhất thiết được phản ánh trong chỉ số object allocation theo cách bạn kỳ vọng.

## 10. Ví dụ tải cấp phát Java 17+: nhiều object tạm và một live set giữ lại

Ví dụ sau tạo một nhóm mảng **giữ tham chiếu** (gần với live payload), sau đó yêu cầu cấp phát nhiều mảng **tạm thời**. Mục đích là quan sát một workload có hai thành phần: retained data và allocation churn.

### 10.1. Tệp `AllocationPressureDemo.java`

```java
import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;

public class AllocationPressureDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        final int mib = 1024 * 1024;
        List<byte[]> retained = new ArrayList<>();

        // 32 mảng, mỗi mảng 1 MiB payload, vẫn được giữ tham chiếu.
        for (int i = 0; i < 32; i++) {
            byte[] keep = new byte[mib];
            keep[0] = 1;
            retained.add(keep);
        }

        // 16 × 128 × 256 KiB = 512 MiB payload được yêu cầu cấp phát.
        int rounds = 16;
        int arraysPerRound = 128;
        int bytesPerArray = 256 * 1024;

        for (int round = 0; round < rounds; round++) {
            for (int i = 0; i < arraysPerRound; i++) {
                byte[] temporary = new byte[bytesPerArray];
                temporary[0] = (byte) round;
                temporary[temporary.length - 1] = (byte) i;

                // Observable use giúp phép thử không chỉ tạo đối tượng
                // rồi ngay lập tức bỏ qua mọi kết quả.
                sink += temporary[0]
                        + temporary[temporary.length - 1];
            }
        }

        int transientMiB =
                rounds * arraysPerRound * bytesPerArray / mib;

        System.out.println("retained.arrays=" + retained.size());
        System.out.println("retained.payloadMiB=32");
        System.out.println("transient.requestedMiB=" + transientMiB);
        System.out.println("sink.positive=" + (sink > 0));

        // Bảo toàn reachability của danh sách retained đến điểm này.
        Reference.reachabilityFence(retained);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 AllocationPressureDemo.java
java -Xms128m -Xmx512m AllocationPressureDemo
```

**Stdout khi chương trình hoàn thành bình thường:**

```text
retained.arrays=32
retained.payloadMiB=32
transient.requestedMiB=512
sink.positive=true
```

**Cách hiểu đúng:**

- `retained.payloadMiB=32` là **dung lượng payload logic** của 32 mảng đang được giữ, **không phải live set được JVM đo chính xác**; còn object headers, list và nhiều object khác.
- `transient.requestedMiB=512` là tổng **payload bytes được các lệnh cấp phát yêu cầu** trong vòng lặp, **không phải allocation rate (MiB/s)**. Muốn có rate phải đo thời gian và allocations thực tế trong một cửa sổ.
- `sink.positive=true` cho biết phép tính sử dụng dữ liệu tạo ra; nhưng compiler/JIT có quyền tối ưu trong phạm vi giữ nguyên ngữ nghĩa. **Không dùng con số tự đếm thay cho profiler allocations**.
- Độ trễ, số chu kỳ GC và mức heap used sau khi chương trình chạy **không có một stdout cố định**. Đó là lý do chương trình chỉ in các số logic ổn định.
- Nếu muốn xem dữ liệu GC thực tế, chạy kèm `-XX:+UseZGC`, JFR và `-Xlog:gc*` trong môi trường được phép. Với workload ngắn hoặc heap còn nhiều chỗ, có thể có **rất ít sự kiện GC**; tăng thời gian/độ dài workload thí nghiệm thay vì kết luận GC không hoạt động.

### 10.2. Chạy chương trình dưới ZGC và log ra tệp

Ví dụ trong một terminal, sau khi đã biên dịch:

```bash
java -XX:+UseZGC -Xms128m -Xmx512m \
  -Xlog:gc*:file=gc-demo.log:time,uptime,level,tags \
  -XX:StartFlightRecording=filename=gc-demo.jfr,settings=profile,dumponexit=true \
  AllocationPressureDemo
```

Câu lệnh nhiều dòng dùng cú pháp Bash. Với Windows PowerShell hoặc CMD, đặt toàn bộ tùy chọn trên **một dòng**.

**Quan trọng:** Đây là ví dụ thực hành, không phải cấu hình production. Đừng chọn heap quá nhỏ chỉ để ép GC phát sinh stall trên ứng dụng sản xuất. Mục tiêu là hiểu mối liên hệ giữa số lượng objects retained, allocation churn và headroom qua số liệu JFR/log.

## 11. GC pause, allocation stall, throughput và tail latency: phải đọc cùng nhau

### GC pause ngắn không chứng minh hệ thống có latency thấp

Giả sử collector có các STW pauses rất ngắn nhưng ứng dụng thường xuyên **chờ cấp phát** do headroom cạn. Độ trễ request vẫn có thể tăng dù biểu đồ pause trông tốt.

Ngược lại, một hệ thống có heap lớn và GC chạy ít có thể vẫn gặp p99 cao do I/O, database, lock contention hoặc scheduler. Không đổ mọi tail latency lên GC nếu chưa có dấu vết tương ứng.

Những phép đối chiếu cần làm:

| Dữ kiện | Diễn giải sơ bộ | Hành động tiếp |
| --- | --- | --- |
| `heap used` cao, còn tăng sau các đợt GC thích hợp | Có thể live set tăng hoặc reclamation chưa theo kịp | Xem retention/caches/queues, phân tích nhiều cycle |
| Allocation rate burst cao đúng lúc p99 tăng | Có thể heap headroom đang bị ăn nhanh | Xem allocation stalls và GC progress/CPU |
| GC pause thấp nhưng allocation stall có mặt | Collector đồng thời không theo kịp tại thời điểm đó | Xem `-Xmx`, CPU, churn, headroom |
| CPU GC cao, CPU ứng dụng thiếu | Concurrent collection cạnh tranh CPU | Xem collector config, workload allocation, CPU sizing |
| RSS/container sát limit nhưng heap chưa đầy | Áp lực ngoài heap hoặc tổng memory budget | Xem direct/native/stacks/metaspace, cgroup |
| Live set ổn định nhưng object churn rất cao | Không nhất thiết có leak; có thể quá nhiều allocations ngắn hạn | Tối ưu object creation, batching, data structures |

### “Allocation stall” khác gì “stop-the-world pause”?

- **STW pause:** JVM tạm dừng các luồng Java trong pha cụ thể của GC/safepoint.
- **Allocation stall:** luồng ứng dụng phải **chờ GC giải phóng bộ nhớ** để tiếp tục cấp phát.
- **GC concurrent CPU overhead:** GC chạy song song, sử dụng CPU và có thể làm throughput/tail latency đổi dù không có STW dài.

Cả ba có thể ảnh hưởng đến p99, nhưng **khác nhau về cơ chế và giải pháp**. Khi phân tích, hãy xem GC logs/JFR theo timestamp và kết hợp với tracing hoặc request latency của service.

## 12. Headroom cần biến động theo workload, không đặt một phần trăm bất biến

Không có quy tắc chung “mọi ZGC đều cần đúng 20% heap trống” hoặc “heap phải gấp đôi live set”. Các tỷ lệ cố định có thể hữu ích làm **giả thuyết ban đầu**, nhưng không được xem là bảo đảm của JVM.

Những biến số có thể thay đổi nhu cầu dự phòng:

1. **Live set peak** vào các giờ cao điểm, cache warmup, long-lived sessions.
2. **Allocation spikes** do request fan-out, parsing, serialization, batch jobs.
3. **Số luồng và concurrency**: nhiều luồng cấp phát cùng lúc, cùng tiêu thụ headroom.
4. **GC progress/CPU**: collector cần thời gian thực và tài nguyên để hoàn thành.
5. **Generation mix**: đối tượng ngắn hạn so với dữ liệu giữ lâu trong generational collector.
6. **Fragmentation/relocation/metadata** mà collector quản lý.
7. **Bộ nhớ native/process** và cgroup limit, nhất là khi JVM chạy trong container.
8. **Startup/warmup, traffic bursts và nền tải theo ngày**.
9. **Hiệu quả backpressure** khi upstream gửi nhiều request hơn khả năng xử lý.
10. **Mục tiêu SLO**: đòi p99.9 thấp khác với chỉ cần throughput trung bình cao.

### Ước lượng phần headroom còn lại

Khi có measurements:

```text
observed_headroom ≈ Xmx - observed_heap_occupancy

ratio_headroom ≈ observed_headroom / Xmx
```

Đây là **chỉ số theo dõi**, không phải bằng chứng workload an toàn. Cần so sánh nó với **số bytes có thể được allocate trong một cửa sổ GC**, mức tăng live set và overhead.

Đặc biệt, ở collector concurrent, `observed_heap_occupancy` có thể giảm hoặc tăng khi GC làm việc; một lần chụp riêng lẻ dễ gây kết luận sai.

### Khi headroom thấp: thứ tự quyết định hợp lý

1. **Xác định hiện tượng:** allocation stall, OOME, p99, RSS/cgroup, GC cycle đang kéo dài?
2. **Kiểm tra live set:** có object giữ quá lâu, queue/caches không giới hạn?
3. **Kiểm tra allocation rate:** burst do traffic hay do code cấp phát quá nhiều?
4. **Kiểm tra CPU cho GC:** collector có đủ thời gian/CPU để thu hồi không?
5. **Kiểm tra memory budget cấp host/container:** có thực sự thể tăng `-Xmx`?
6. **Thử tăng heap có kiểm soát** hoặc giảm churn/burst, đo lại dưới tải tương đương.
7. **Đánh giá p99/p99.9 và throughput** chứ không chỉ một con số `GC.pause`.

Không đồng thời đổi `-Xmx`, concurrency, code serialization và nhiều flag GC rồi kết luận chắc chắn tác nhân nào cải thiện kết quả.

## 13. Hai trường hợp thực tế: chọn hướng sửa phù hợp

### Trường hợp A — Live set quá lớn vì cache/queue giữ data

Một service có cache không giới hạn. Trong vài giờ:

```text
Live set:       1.0 -> 1.8 -> 2.7 -> 3.8 GiB
Allocation:     xấp xỉ ổn định theo traffic
GC after-cycle: xu hướng heap used tăng lên
```

Nếu object vẫn reachable từ cache, GC không thể thu hồi chúng. Tăng `-Xmx` chỉ tạo thêm thời gian trước khi chạm hạn mức nếu không có eviction hoặc bound.

**Hướng xử lý:** đặt giới hạn size/TTL cho cache, kiểm tra vòng đời key/value, bounded queue/backpressure, phân tích retained paths và cân nhắc cấu trúc dữ liệu ít overhead hơn. Sau khi live set ổn định, mới sizing headroom phù hợp với allocation rate.

### Trường hợp B — Live set ổn định nhưng allocation rate đột biến

Một API service có live set quanh 2 GiB nhưng trong đợt khuyến mại, mỗi giây tạo nhiều đối tượng tạm do JSON parsing và request fan-out:

```text
Live set:       khoảng 2 GiB
Steady alloc:   0.3 GiB/s
Burst alloc:    1.8 GiB/s
GC progress:    tăng theo tải nhưng đôi lúc không bắt kịp
Observed:       allocation stalls + p99 tăng
```

Đây không nhất thiết là leak. Hướng xử lý có thể là:

- Cấp thêm **headroom** nếu memory budget cho phép.
- Giảm allocation per request bằng cách tránh tạo dữ liệu trung gian không cần thiết, tối ưu parsing/serialization, batching.
- Giới hạn concurrency/fan-out và dùng backpressure.
- Bảo đảm concurrent GC có đủ CPU/điều kiện để hoàn thành chu kỳ.
- Kiểm tra lại trên cùng tải burst và request latency thực tế.

### Trường hợp C — Heap còn chỗ nhưng container bị OOMKilled

Một container đặt `-Xmx` quá gần memory limit. Direct buffers, thread stacks, metaspace và JIT code cache tiếp tục tăng, dẫn đến áp lực RAM ngay cả khi Java heap used chưa sát max.

**Hướng xử lý:** đo RSS/cgroup, native memory, thread counts, direct buffer usage, cân đối `-Xmx` với memory limit, giảm native pressure hoặc tăng container limit theo chính sách. Không cố giải bằng cách tăng `-Xmx` thêm nữa.

## 14. Runbook phân tích live set, allocation rate và headroom trong production

Đề xuất chuỗi làm việc theo thứ tự:

### Bước 1: chốt bối cảnh

Ghi nhận:

- JDK vendor/version và collector đang dùng.
- `-Xms`, `-Xmx`, `SoftMaxHeapSize` nếu có.
- CPU limit/cores, container memory limit, mức RSS.
- Loại workload, request mix, concurrency, thời gian warmup.
- SLO độ trễ p95/p99/p99.9 và throughput.

### Bước 2: bật quan sát đủ để diễn giải

Dùng GC logs theo cấu hình vận hành phù hợp và JFR trong khoảng thời gian có tải đại diện. Với ứng dụng thật, ưu tiên các công cụ có thể vận hành an toàn và giữ metadata trong phạm vi cho phép.

### Bước 3: ước lượng live set qua thời gian

Xem occupancy sau những cycle phù hợp và đường xu thế retained data. Tránh gọi một `getHeapMemoryUsage().getUsed()` duy nhất là “live set chuẩn xác”. Xem cache, queue, session và những object graph giữ lâu.

### Bước 4: đo allocation rate theo các cửa sổ thời gian

Thu số liệu allocations từ profiler/metrics có khả năng phù hợp; vẽ theo thời gian và đối chiếu burst với traffic. Ghi **đơn vị** (MiB/s hay MB/s) và đừng nhầm MiB (2^20) với MB (10^6).

### Bước 5: đặt cạnh thời lượng GC và dấu hiệu stall

Quan sát cycle duration, số GC threads/CPU, stall, heap capacity và request tail latency. Khi cần, phân tích JFR stack traces của nơi tạo allocation áp lực cao.

### Bước 6: tạo giả thuyết sizing ban đầu

Dùng mô hình `L_peak + A_peak × T_concurrent + S` để suy nghĩ, **không coi là dự báo chắc chắn**. Xác minh memory budget **cấp tiến trình** trước khi tăng `-Xmx`.

### Bước 7: thay đổi từng biến và chạy thử lại

Ví dụ tăng `-Xmx` từ 4 GiB lên 6 GiB (nếu đủ RAM), giữ nguyên traffic và các tham số khác trong thí nghiệm. So p99, allocation stalls, RSS, GC CPU và throughput. Nếu cải thiện không ổn định, tiếp tục điều tra allocation churn hoặc retention.

### Bước 8: xác nhận ở cả steady và burst

Kiểm thử tải ổn định, warmup, burst, cooldown, deploy/rollout và giai đoạn cache refresh. Mức headroom phù hợp ở steady state chưa chắc chịu được burst.

### Bước 9: theo dõi sau triển khai

Thiết lập dashboard/alert theo tình huống: allocation stalls, heap occupancy cao kéo dài, live set tăng dần, process RSS sát limit, GC throughput không theo kịp, và SLO latency. Không chỉ cảnh báo theo một tỷ lệ heap used cố định.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| Chọn `-Xmx` đúng bằng live set | Không chừa chỗ cho allocate khi GC chạy và overhead | Bổ sung headroom dựa trên allocation rate, cycle duration, safety |
| Coi `heap used` là live set chính xác | Có object chết chưa được reclaim, các thế hệ và phase khác nhau | Ước lượng qua nhiều GC cycles và retention analysis |
| Lấy `ΔheapUsed/Δt` làm allocation rate | GC có thể thu hồi bytes trong khoảng đo | Dùng allocation metrics/profiling và định nghĩa interval |
| Sizing theo allocation rate trung bình cả giờ | Bỏ lỡ burst ngắn có thể gây stall | Theo dõi cửa sổ ngắn, peak sustained rate |
| Lấy thời gian STW pause làm `T_concurrent` | GC pause và concurrent collection khác nhau | Dùng cycle/progress phù hợp hoặc đo time-to-reclaim |
| Coi headroom bằng RAM free của OS | Java heap, RSS, direct memory và cgroup là các lớp khác nhau | Theo dõi heap và memory budget cấp process riêng |
| Cho rằng `-Xmx8g` dùng ngay 8 GiB RAM | Max không đồng nghĩa committed/RSS tức thì | Kiểm tra capacity/committed và giới hạn OS |
| Đặt `-Xmx` sát memory limit container | Không chừa metaspace, stacks, direct/native | Thiết kế cả heap + non-heap |
| Coi `SoftMaxHeapSize` là giới hạn cứng | ZGC có thể vượt soft limit tới `-Xmx` | Dùng làm mục tiêu mềm và kiểm tra hard max |
| Dùng flag `ZGenerational` trên JDK 24+ | Chế độ ZGC non-generational đã bị loại bỏ | Dùng ZGC generational hiện hành; không thêm flag cũ |
| ZGC có pause ngắn nên không thể gây latency | Allocation stall/CPU contention vẫn có thể xảy ra | Kiểm tra stalls + p99 + CPU |
| Có allocation rate cao nên kết luận leak | Nhiều objects có thể chết ngay | Xem live set qua các GC cycles |
| Tăng heap mãi khi live set tăng không giới hạn | GC không thể thu hồi object vẫn reachable | Sửa retention, cache/queue bounds |
| Tăng GC threads vô tội vạ | GC lấy CPU của mutator, có thể làm p99 tệ hơn | Đo/so sánh cân bằng collector throughput và CPU |
| Tin mọi JDK có Shenandoah cùng mode/flags | Build/version khác nhau | Kiểm tra collector và option của runtime thật |
| Tổng hợp JFR allocation samples thành bytes chính xác | Sampling không phải counter toàn bộ allocations | Dùng công cụ/weighting thích hợp |
| Bật `System.gc()` lặp lại để “đo live set” | Ép GC có thể méo workload và latency | Dùng profiling/quan sát thích hợp, cân nhắc tác động |
| Chỉ đo ở idle, không đo burst | Không phản ánh allocation pressure cao nhất | Chạy workload đại diện và lấy peak |
| Một flag chỉnh xong thì tuyên bố đã đạt SLO | Latency còn bị I/O, lock, CPU, network ảnh hưởng | Đo request latency thực tế end-to-end |

## 16. Bài tập tự kiểm tra có đáp án

**Bài 1.** Live set 2 GiB, allocation rate 0.5 GiB/s trong 3 giây, biên an toàn 1 GiB. Mô hình `L + A×T + S` cho ngân sách bao nhiêu?

**Đáp án:** `2 + 0.5×3 + 1 = 4.5 GiB`. Đây chỉ là giá trị **ước lượng ban đầu**, không phải cam kết JVM sẽ chạy ổn với đúng `-Xmx4.5g`.

**Bài 2.** Java heap used giảm từ 4 GiB xuống 2 GiB giữa hai lần đo. Allocation rate trong khoảng đó có nhất thiết âm không?

**Đáp án:** Không. GC có thể đã thu hồi nhiều bytes hơn số bytes ứng dụng mới allocate; allocation rate bản chất là tốc độ **cấp phát mới**, không âm trong định nghĩa thông thường.

**Bài 3.** Ở JDK 25, có nên thêm `-XX:-ZGenerational` để ZGC chạy mode cũ không?

**Đáp án:** Không. Mode non-generational đã bị loại bỏ từ JDK 24. Dùng ZGC hiện hành với `-XX:+UseZGC`; điều chỉnh heap dựa trên workload.

**Bài 4.** `-Xmx8g -XX:SoftMaxHeapSize=6g` nghĩa là JVM chắc chắn sẽ luôn giữ 2 GiB RAM trống không?

**Đáp án:** Không. Soft max là **mục tiêu mềm**; ZGC có thể vượt 6 GiB lên tới 8 GiB, và chênh lệch không phải lời bảo đảm bộ nhớ vật lý luôn sẵn.

**Bài 5.** Một service có live set gần như ổn định nhưng cấp phát tăng 10 lần theo burst. Đây có nhất thiết là memory leak không?

**Đáp án:** Không. Có thể là lượng object tạm thời tăng. Kiểm tra allocation stalls, GC capacity và traffic/concurrency.

**Bài 6.** GC pause chỉ 1 ms nhưng p99 request lên 200 ms. Có thể loại bỏ GC khỏi danh sách nghi vấn ngay không?

**Đáp án:** Không. Concurrent GC có thể tạo allocation stalls hoặc cạnh tranh CPU; đồng thời p99 cao có thể do I/O/lock/network. Cần đối chiếu timeline và dấu vết thực.

**Bài 7.** Một container giới hạn 4 GiB, ứng dụng đặt `-Xmx4g` và bị OOMKilled dù heap used chưa 4 GiB. Nguyên nhân có thể là gì?

**Đáp án:** JVM còn dùng non-heap/native memory; tiến trình/container không chỉ có Java heap. Phải tính RSS/cgroup và các khoản ngoài heap.

**Bài 8.** Vì sao không lấy thời gian dừng `STW` 0.5 ms nhân với allocation rate để xác định toàn bộ headroom của ZGC?

**Đáp án:** ZGC làm nhiều công việc **concurrently** trong một cycle dài hơn pause. Headroom còn phải đủ phục vụ allocation trong lúc collector chưa thu hồi đủ chỗ và có overhead liên quan.

**Bài 9.** Nếu `MemoryMXBean.getHeapMemoryUsage().getUsed()` là 2 GiB, có chắc live set là 2 GiB không?

**Đáp án:** Không. Đây là snapshot heap used, không phải hàm đo liveness chính xác của mọi object.

**Bài 10.** Một bản JFR có nhiều `ObjectAllocationSample`; tổng bytes của các sample có phải tổng cấp phát của JVM?

**Đáp án:** Không. Đó là dữ liệu sampled. Cần dùng phương pháp profiler/weighting đúng hoặc metrics có định nghĩa tổng allocated bytes rõ ràng.

**Bài 11.** Tại sao tăng `-XX:ConcGCThreads` có thể vừa tốt vừa xấu?

**Đáp án:** GC có thể theo kịp allocation nhanh hơn, nhưng cạnh tranh CPU với application threads mạnh hơn. Đo latency/throughput và CPU mới quyết định.

**Bài 12.** Live set tăng liên tục vì queue không giới hạn. Tăng `-Xmx` có giải quyết triệt để không?

**Đáp án:** Không. Cần kiểm soát retention và backpressure; tăng heap chỉ có thể trì hoãn giới hạn.

**Bài 13.** Dùng `-Xmx6g`, live set 3 GiB. Có thể nói headroom chính xác luôn là 3 GiB không?

**Đáp án:** Không. Tại một thời điểm, heap còn chứa object chưa reclaim, allocations mới, GC overhead... `-Xmx - live set` không phải lượng free usable thực tế.

**Bài 14.** Allocation rate trung bình cả phút 200 MiB/s nhưng 5 giây có đỉnh 900 MiB/s. Nên sizing dựa vào 200 hay 900?

**Đáp án:** Phải đánh giá **đỉnh sustained rate** trong cửa sổ GC relevant cùng live set/CPU; không lấy trung bình 200 để bỏ qua 900. Có thể cần headroom, giảm burst hoặc backpressure.

**Bài 15.** `AllocationPressureDemo` in `transient.requestedMiB=512`. Có thể kết luận allocation rate là 512 MiB/s không?

**Đáp án:** Không. Chương trình chỉ in tổng payload cấp phát theo logic vòng lặp. Muốn có MiB/s cần đo **thời gian** và allocations thực tế.

**Bài 16.** Tại sao cần thử nghiệm cả steady và burst sau khi chỉnh heap?

**Đáp án:** Steady state có thể có nhiều free space và GC dễ theo kịp, trong khi burst tiêu thụ headroom nhanh và gây stall/p99 cao. Cần chứng minh trên workload đại diện.

### Checklist tự đánh giá

- [ ] Tôi phân biệt live set, heap used, allocation rate, heap committed/max và RSS.
- [ ] Tôi hiểu **headroom cho concurrent GC** không chỉ là chênh lệch max–live set.
- [ ] Tôi biết mô hình `L + A×T + S` là **heuristic**, không phải công thức đảm bảo.
- [ ] Tôi không nhầm GC pause time với concurrent GC cycle duration.
- [ ] Tôi theo dõi allocation rate ở steady và burst, không chỉ trung bình dài hạn.
- [ ] Tôi phân biệt áp lực object tạm với memory leak/retention.
- [ ] Tôi biết ZGC hiện hành từ JDK 24 chỉ còn **generational mode**.
- [ ] Tôi hiểu `-Xmx` là hard heap limit, `SoftMaxHeapSize` là mục tiêu mềm.
- [ ] Tôi đo GC logs/JFR và đọc snapshot JMX với giới hạn ý nghĩa rõ ràng.
- [ ] Tôi không dùng số JFR samples làm tổng allocation bytes chính xác.
- [ ] Tôi tính riêng RAM cho direct/native memory, stacks, metaspace và container.
- [ ] Tôi đánh giá stall, p99, CPU, RSS, throughput và GC progress sau thay đổi.
- [ ] Tôi chạy được `HeadroomBudgetDemo.java` và hiểu `AllocationPressureDemo.java` không phải profiler.

## 17. Tài liệu hiện hành, chính thức

1. [Oracle Java SE 25 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): lựa chọn và tuning các collector của HotSpot hiện hành.
2. [Oracle Java SE 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): nhu cầu heap chứa live set + headroom, `-Xmx`, `SoftMaxHeapSize`, và chú thích ZGC chỉ còn generational.
3. [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseZGC`, `-Xms`, `-Xmx`, `-XX:ConcGCThreads`, unified logging `-Xlog` và JFR startup.
4. [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.dump`, `JFR.stop` và chẩn đoán tiến trình.
5. [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, các sự kiện hiệu năng/GC và phân tích latency.
6. [Oracle Java SE 25 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): đọc heap usage qua JMX.
7. [Oracle Java SE 25 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): `used`, `committed`, `max` và ý nghĩa các số đo.
8. [OpenJDK JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490): thay đổi được triển khai từ JDK 24, tránh các tùy chọn lỗi thời.
9. [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): cơ sở thiết kế generational ZGC.
10. [dev.java — ZGC Overview](https://dev.java/learn/jvm/tool/garbage-collection/zgc-overview/): giải thích trực quan vì sao cần headroom ngoài live set và nên bắt đầu tuning từ `-Xmx`.

**Tổng kết:** Với GC độ trễ thấp, **live set** quyết định dữ liệu không thể thu hồi, **allocation rate** quyết định tốc độ tiêu thụ không gian cấp phát, còn **headroom** giúp ứng dụng tiếp tục chạy khi GC đồng thời chưa lấy lại đủ chỗ. Một mô hình ban đầu là `heap ≳ live set peak + allocation rate peak × thời gian GC theo kịp + safety`, nhưng phải kiểm chứng bằng JFR, GC log, CPU, RSS và độ trễ ứng dụng dưới tải thực. Với ZGC generational hiện hành, ưu tiên kiểm tra `-Xmx` và workload trước khi chỉnh nhiều cờ.