# `-XX:MinRAMPercentage` trong tính heap tối đa cho môi trường ít bộ nhớ (Java/HotSpot hiện hành)

## 1. Bài toán: một JVM trong container nhỏ cần bao nhiêu Java heap?

Giả sử ứng dụng Java được triển khai trong một Linux container có **memory limit nhỏ**, ví dụ vài chục đến vài trăm MiB. Khi không đặt `-Xmx`, HotSpot phải tự quyết định kích thước **Java heap tối đa** từ nguồn bộ nhớ mà JVM nhận biết, các quy tắc ergonomics và các tùy chọn VM.

Một nhầm lẫn rất thường gặp là nhìn thấy tên:

```text
-XX:MinRAMPercentage=50
```

rồi kết luận: “Cờ này bảo đảm Java heap **tối thiểu bằng 50% RAM**”. Kết luận đó **sai**.

Theo tài liệu launcher HotSpot hiện hành, **`-XX:MinRAMPercentage` điều chỉnh tỷ lệ bộ nhớ dùng để tính *heap tối đa* trong chế độ heap nhỏ**, với mức heap nhỏ được mô tả là khoảng **125 MB**. Giá trị mặc định được Oracle công bố là **50%**. Đây **không** phải cờ đặt heap tối thiểu, không phải `-Xms`, và cũng không buộc JVM phải dùng hết một nửa bộ nhớ container.

Trong khi đó, `-XX:MaxRAMPercentage` là cờ thường dùng để tính heap tối đa ở tình huống **không thuộc nhánh heap nhỏ**; giá trị mặc định trong tài liệu launcher là **25%**.

**Ý chính cần nhớ ngay:**

- `MinRAMPercentage`: tỷ lệ dùng cho **tính max heap ở môi trường/heap nhỏ**; chữ “Min” nói về **nhánh ít bộ nhớ**, không nói về mức heap tối thiểu.
- `MaxRAMPercentage`: tỷ lệ thường áp dụng cho **max heap** khi điều kiện heap lớn hơn.
- `InitialRAMPercentage`: ảnh hưởng **initial heap**, không phải max heap.
- `-Xmx`: cách đặt **max heap rõ ràng**, thường được ưu tiên khi cấu hình tường minh.
- **Memory limit của container** khác **max heap**; JVM còn dùng bộ nhớ native, metaspace, stack, code cache, direct buffers…

Đây là kiến thức vẫn còn áp dụng trong HotSpot trên các bản JDK mới. Tài liệu Java SE 25 và source launcher OpenJDK hiện hành vẫn mô tả `MinRAMPercentage` với ý nghĩa trên; không cần sử dụng các tùy chọn ratio đời cũ để làm công việc này.

## 2. Trước hết phải tách bốn đại lượng bộ nhớ

Một container có thể bị giới hạn 128 MiB, nhưng điều đó không đồng nghĩa JVM có Java heap tối đa đúng 128 MiB hoặc heap đã dùng đến 128 MiB.

| Đại lượng | Ý nghĩa | Cách quan sát điển hình |
| --- | --- | --- |
| **Memory limit** của container | Giới hạn bộ nhớ mà Linux cgroup/orchestrator áp đặt | `memory.max` ở cgroup v2, Pod/Docker limit, metrics hệ thống |
| **Available/MaxRAM dành cho JVM ergonomics** | Cơ sở JVM dùng để lựa chọn một số giá trị bộ nhớ, có thể xét host và cgroup | `-XshowSettings:system`, `-XX:MaxRAM`, diagnostic flags |
| **Max Java heap** | Mức tối đa JVM dự định cho vùng Java heap | `-XshowSettings:vm`, `Runtime.maxMemory()`, `-XX:MaxHeapSize` |
| **Java heap đang dùng/committed** | Bộ nhớ heap đã sử dụng hoặc đã commit tại một thời điểm | MemoryMXBean, GC/JFR/metrics |
| **RSS/native memory** | Bộ nhớ thực tiến trình dùng ngoài và trong heap | OS/container RSS, Native Memory Tracking, hệ quan sát |

### Phân biệt `-Xmx` và memory limit

Ví dụ một container có memory limit 128 MiB và JVM có max heap khoảng 64 MiB:

```text
Container memory limit: 128 MiB
  |
  +-- Java heap: có thể mở rộng đến mức max heap đã tính
  +-- Metaspace: class metadata
  +-- Thread stacks
  +-- JIT code cache
  +-- Direct/native buffers
  +-- GC/JVM runtime/native allocations
  +-- Các thành phần khác
```

**Heap tối đa không phải toàn bộ giới hạn bộ nhớ tiến trình.** Ngay cả khi Java heap nằm dưới `-Xmx`, container vẫn có thể bị kernel OOM-kill vì tổng bộ nhớ sử dụng vượt giới hạn. Ngược lại, `Runtime.getRuntime().maxMemory()` là **khả năng heap tối đa được JVM báo**, không phải lượng heap đang dùng tức thời.

Vì thế, tăng `MinRAMPercentage` trong một container rất nhỏ có thể làm **ít chỗ hơn cho bộ nhớ ngoài heap**, khiến tính ổn định kém đi, dù khối lượng dữ liệu Java được phép lớn hơn.

## 3. Hợp đồng chính thức của `-XX:MinRAMPercentage`

Dạng tùy chọn:

```bash
java -XX:MinRAMPercentage=75 -jar app.jar
```

Ở đây `app.jar` là tên JAR minh họa phải thực sự tồn tại mới chạy được. Flag là **tùy chọn VM HotSpot**, không phải một phần cú pháp Java hay một API trong `java.lang`.

Theo tài liệu Java SE 25:

- `MinRAMPercentage` tính **giới hạn bộ nhớ tối đa dành cho heap trước một số bước ergonomics** dựa trên tỷ lệ RAM khi heap nhỏ.
- Một heap nhỏ được mô tả là **khoảng 125 MB**, không nên hiểu như một ngưỡng chính xác do người dùng cấu hình.
- Giá trị mặc định được tài liệu công bố là **50%**.
- `MaxRAMPercentage` có mặc định **25%** cho cách tính heap tối đa ở các trường hợp thông thường.
- `InitialRAMPercentage` có mặc định **1.5625%** cho initial heap theo tài liệu cùng launcher.

**Diễn đạt chính xác:** `-XX:MinRAMPercentage=75` là **“cho phép chọn max heap theo tỷ lệ 75% khi logic small-heap được dùng”**, không phải “luôn dành tối thiểu 75% bộ nhớ cho Java heap”. Kết quả cuối còn chịu ảnh hưởng quy tắc sizing, giới hạn heap tối thiểu/tối đa và căn chỉnh bộ nhớ của HotSpot.

**Không khẳng định ranh giới chính xác bằng `memory.limit == 125 MB`.** Tài liệu nói **“small heap approximately 125 MB”**, không đưa một quy tắc đơn giản rằng tất cả container dưới 125 MB dùng MinRAMPercentage và tất cả container trên 125 MB dùng MaxRAMPercentage. Heuristics thực tế còn có các ngưỡng, mức trần và làm tròn.

## 4. Vì sao tên “MinRAMPercentage” dễ gây nhầm?

Đặt hai câu cạnh nhau:

**Sai:**

> `-XX:MinRAMPercentage=50` làm **minimum Java heap** bằng 50% memory limit.

**Đúng:**

> Trong nhánh sizing cho **small heap**, `-XX:MinRAMPercentage=50` ảnh hưởng cách **max Java heap** được chọn từ lượng bộ nhớ JVM dùng làm cơ sở.

Đặc biệt:

- Nó **không đặt `-Xms`**.
- Nó **không bảo đảm** heap luôn chiếm đúng phần trăm ấy.
- Nó **không giữ chỗ** bộ nhớ vật lý cho heap ngay lúc startup.
- Nó **không phải tỷ lệ “bộ nhớ còn trống”** đo theo thời gian thực.
- Nó **không giải quyết** mọi giới hạn native memory hoặc OOMKill.

**Đối chiếu đúng cờ đặt mức heap ban đầu:**

```bash
java -Xms16m -Xmx64m -jar app.jar
```

Cờ `-Xms` đặt initial heap và `-Xmx` đặt maximum heap; đó là kiểu cấu hình cố định rõ ràng, **khác về mục đích** với các phần trăm sizing mặc định.

Khi cần **minimum** theo nghĩa ngữ nghĩa của một giới hạn heap, hãy xem tài liệu về `-Xms` và `-XX:MinHeapSize`. Không dùng `MinRAMPercentage` như một cách viết thay thế cho chúng.

## 5. Mô hình tính heap tối đa ở mức khái niệm

Một mô hình suy nghĩ hữu ích:

```text
Nguồn RAM mà HotSpot dùng để tính ergonomics
  (có thể được xác định theo host/cgroup và -XX:MaxRAM)
                          |
                          v
             Có -Xmx/MaxHeapSize cố định?
                 /                 \
               Có                  Không
               |                     |
               v                     v
        Sử dụng max heap      Heap sizing ergonomics
        cấu hình tường minh     /                 \
                             small-heap       thông thường
                                |                 |
                                v                 v
                       MinRAMPercentage     MaxRAMPercentage
                                \                 /
                                 \               /
                                   v           v
                                 Căn chỉnh/giới hạn
                                       |
                                       v
                                  Max Java heap
```

Đây là **mô hình giải thích**, không phải mã nguồn thực thi hay một thuật toán đủ để tính chính xác mọi kết quả HotSpot. Việc quyết định nhánh small-heap, căn chỉnh và giới hạn khác được kiểm soát bởi implementation.

Ví dụ phép nhân đơn giản **chỉ mang tính dự đoán sơ bộ**:

```text
64 MiB × 50% = 32 MiB
64 MiB × 75% = 48 MiB
1 GiB × 25% = 256 MiB
```

Trong thử nghiệm HotSpot JDK 24 cụ thể ở phần sau, các trường hợp này trùng max heap báo được. Nhưng **không dùng phép nhân đó để cam kết max heap luôn chính xác ở mọi cgroup, kích cỡ, GC và JDK build**; những ràng buộc khác có thể làm kết quả lệch đi.

## 6. Thí nghiệm an toàn trên JDK: giả lập “RAM dùng cho ergonomics” bằng `MaxRAM`

Ta có thể kiểm chứng ảnh hưởng của phần trăm **mà không phải tạo container hạn chế bộ nhớ thật** bằng cách cấu hình `-XX:MaxRAM`.

Ví dụ:

```bash
java -XX:MaxRAM=64m -XshowSettings:vm -version
```

Trong tài liệu launcher, `MaxRAM` quy định **lượng memory tối đa JVM dùng làm cơ sở để tính Java heap trước ergonomics**, không phải số byte heap Java thực sự đã dùng.

Ở đây, `MaxRAM=64m` dùng để **mô phỏng một cơ sở sizing nhỏ**. Cờ này **không sửa cgroup memory.max**, **không giới hạn RSS của tiến trình như Docker `--memory`**, và **không tương đương chạy trong một container 64 MiB thực sự**.

Những câu lệnh thử trên HotSpot JDK 24:

```bash
# Small-memory base, phần trăm mặc định
java -XX:MaxRAM=64m -XshowSettings:vm -version

# Chỉ đổi MinRAMPercentage cho small-heap
java -XX:MaxRAM=64m -XX:MinRAMPercentage=75.0 \
     -XshowSettings:vm -version

# Hạ MinRAMPercentage cho small-heap
java -XX:MaxRAM=64m -XX:MinRAMPercentage=25.0 \
     -XshowSettings:vm -version
```

Các lệnh nhiều dòng dùng dấu `\` để nối dòng theo cú pháp **Bash/sh**. Nếu chạy bằng PowerShell, hãy viết các tùy chọn trên **một dòng** hoặc dùng cách nối dòng của PowerShell.

Trên bản **Azul Zulu OpenJDK 24.0.2/HotSpot** đã kiểm tra, trường `Max. Heap Size (Estimated)` trong `-XshowSettings:vm` lần lượt là:

```text
-XX:MaxRAM=64m                              -> 32.00M
-XX:MaxRAM=64m -XX:MinRAMPercentage=75.0    -> 48.00M
-XX:MaxRAM=64m -XX:MinRAMPercentage=25.0    -> 16.00M
```

**Cách đọc:**

- Khi không ghi đè, JVM dùng giá trị `MinRAMPercentage` mặc định **50%** trong trường hợp này → khoảng 32 MiB.
- Đặt `75.0` → max heap tăng lên **48 MiB**.
- Đặt `25.0` → max heap giảm xuống **16 MiB**.
- Đây là **max heap được tính**, không phải heap đã thực sự dùng 32/48/16 MiB.
- Số liệu minh họa được đo trên JDK cụ thể, không phải chuẩn đo lường cố định cho mọi runtime.

Các số thử không thay đổi cấu hình Docker/Kubernetes của máy. Chúng giúp cô lập tác dụng của **cờ sizing** khỏi các tác động cgroup thực tế.

## 7. Phân biệt với `MaxRAMPercentage` khi cơ sở bộ nhớ không nhỏ

Cùng JDK đã kiểm thử:

```bash
java -XX:MaxRAM=64m \
     -XX:MaxRAMPercentage=70.0 \
     -XshowSettings:vm -version
```

Kết quả trên JDK 24 trong thí nghiệm:

```text
Max. Heap Size (Estimated): 32.00M
```

Đây là **trường hợp small-heap**, nên việc chỉ đổi `MaxRAMPercentage` lên 70% **không làm max heap tăng** như người học có thể dự đoán từ phép nhân `64 × 70%`.

Thử với cơ sở bộ nhớ lớn hơn:

```bash
java -XX:MaxRAM=1g -XshowSettings:vm -version

java -XX:MaxRAM=1g \
     -XX:MinRAMPercentage=75.0 \
     -XshowSettings:vm -version

java -XX:MaxRAM=1g \
     -XX:MaxRAMPercentage=70.0 \
     -XshowSettings:vm -version
```

Quan sát trên JDK 24:

```text
-XX:MaxRAM=1g                            -> 256.00M
-XX:MaxRAM=1g -XX:MinRAMPercentage=75.0  -> 256.00M
-XX:MaxRAM=1g -XX:MaxRAMPercentage=70.0  -> 718.00M
```

**Giải thích:**

- Cơ sở `1g` không đi theo nhánh small-heap như thí nghiệm `64m`.
- Tăng `MinRAMPercentage` từ 50 lên 75% **không làm max heap 1 GiB tăng** trong trường hợp này.
- Tăng `MaxRAMPercentage` lên 70% **có ảnh hưởng** đến max heap.
- `718.00M` là giá trị thực đã quan sát trên JDK 24; nó không đúng tuyệt đối với phép tính thập phân `1024 × 0.7 = 716.8` vì HotSpot còn có logic căn chỉnh/rounding.

Kết quả này chứng minh một bài học quan trọng: **không được cộng, nhân hoặc áp dụng đồng thời hai tỷ lệ `MinRAMPercentage` và `MaxRAMPercentage` lên cùng một heap**. JVM chọn logic phù hợp điều kiện và áp dụng thêm giới hạn khác; chúng không phải hai mức trần được cộng dồn.

## 8. Mốc “small heap khoảng 125 MB” không phải công tắc Docker 125 MB

Tài liệu chính thức nói **small heap approximately 125 MB**. Đọc sai thường dẫn đến ba kết luận không đúng:

1. “Container dưới 125 MiB dùng `MinRAMPercentage`, còn trên 125 MiB dùng `MaxRAMPercentage`.”
2. “Cứ đạt 126 MiB RAM container là mọi phần trăm đổi ngay.”
3. “Max heap 125 MB là giới hạn cứng do `MinRAMPercentage` tạo ra.”

**Cả ba đều là diễn giải quá mức.**

Trên một HotSpot thực tế, các ngưỡng được thực thi với các quy tắc sizing và căn chỉnh. Khi cơ sở `MaxRAM` nằm ở vùng trung gian, max heap có thể bị giữ ở mức quanh 125 MiB trong một khoảng đầu vào, thay vì bằng tỷ lệ thô ở mọi điểm. Vì vậy, trong vận hành:

- Xem “~125 MB” như **mô tả miền áp dụng**, không phải hằng số kiểm tra theo một dòng YAML.
- Đo **max heap thật sự** tại startup của runtime đang dùng.
- Nếu sản phẩm có SLA bộ nhớ chặt chẽ, định nghĩa `-Xmx` hoặc ngân sách rõ thay vì dựa hoàn toàn vào ngưỡng ước lượng.
- Test các cấu hình sát giới hạn thực tế, nhất là khi ứng dụng chạy ở 128–256 MiB.

Không cần viết code tự mô phỏng thuật toán HotSpot hoặc hardcode ngưỡng 125 MiB vào business logic; đó là một quyết định nội bộ của JVM và có thể thay đổi theo bản JDK.

## 9. `-Xmx` được đặt tường minh: không mong `MinRAMPercentage` tự thắng

Khi đã chỉ định `-Xmx`, mục tiêu là **đặt một maximum heap tường minh**:

```bash
java -XX:MaxRAM=64m \
     -XX:MinRAMPercentage=75.0 \
     -Xmx16m \
     -XshowSettings:vm -version
```

Kết quả đã kiểm tra trên Zulu HotSpot JDK 24:

```text
Max. Heap Size: 16.00M
```

Mặc dù `MaxRAM=64m` và `MinRAMPercentage=75.0` có thể tạo max heap 48 MiB khi không đặt `-Xmx`, cấu hình trên **đặt `-Xmx16m`** nên max heap là **16 MiB**.

**Chú ý:**

- `-Xmx` không phải “lượng heap hiện đang dùng”, mà là **mức tối đa**.
- Đặt `-Xmx` lớn hơn giới hạn container **không cấp thêm RAM**. Container có thể bị OOM-kill trước khi heap chạm mức trần do chi phí native.
- Đặt `-Xmx` quá thấp có thể gây `java.lang.OutOfMemoryError: Java heap space` khi khối lượng dữ liệu lớn.
- Không nên bỏ `-Xmx` chỉ vì nghĩ `MinRAMPercentage` sẽ luôn cấp một lượng heap tối thiểu mong muốn.

Nếu cần bảo đảm mức heap maximum và ngân sách native rõ, hãy dùng thiết kế bộ nhớ tổng thể; một cờ phần trăm chỉ là phần của bài toán.

## 10. `InitialRAMPercentage` và `-Xms` không phải thay thế cho `MinRAMPercentage`

Ba khái niệm quan trọng:

| Cấu hình | Ý nghĩa chính | Mốc mặc định theo launcher khi áp dụng |
| --- | --- | --- |
| `-XX:InitialRAMPercentage` | Tỷ lệ ảnh hưởng **initial heap** trước ergonomics | 1.5625% |
| `-XX:MinRAMPercentage` | Tỷ lệ ảnh hưởng **maximum heap khi nhỏ** | 50% |
| `-XX:MaxRAMPercentage` | Tỷ lệ ảnh hưởng **maximum heap khi thông thường** | 25% |
| `-Xms` | Kích thước heap ban đầu cấu hình tường minh | Theo yêu cầu ứng dụng |
| `-Xmx` | Maximum heap tường minh | Theo yêu cầu ứng dụng |

Ví dụ:

```bash
java -XX:InitialRAMPercentage=5.0 \
     -XX:MinRAMPercentage=75.0 \
     -jar app.jar
```

Tùy chọn đầu tiên có thể đổi initial heap; tùy chọn thứ hai liên quan max heap small-memory. Chúng không phải hai cách đặt cùng một giới hạn.

Tương tự:

```bash
java -Xms16m -Xmx48m -jar app.jar
```

Đây là cấu hình heap ban đầu và heap tối đa **tường minh**, không cần suy ra từ phần trăm RAM.

**Một cảnh báo thường gặp:** tăng `-Xms` lên gần `-Xmx` có thể làm JVM commit thêm heap ngay lúc startup. Điều này không chắc phù hợp container rất nhỏ và không nên dùng như một mẹo “luôn nhanh hơn”. Quyết định nên dựa vào đặc trưng cấp phát bộ nhớ và kết quả profiling.

## 11. Container awareness ảnh hưởng cơ sở tính, không thay ngữ nghĩa cờ

Trên HotSpot chạy **Linux** với container support, JVM có thể đọc giới hạn bộ nhớ cgroup để xác định cơ sở lựa chọn heap. Theo tài liệu Java launcher, `UseContainerSupport` **bật mặc định** trên Linux được hỗ trợ và có thể tắt bằng:

```bash
java -XX:-UseContainerSupport -version
```

**Không dùng cờ Linux-only này trên JVM native Windows/macOS** mà không xác nhận runtime hỗ trợ. Khi dùng Docker Desktop trên Windows/macOS, Java tiến trình **bên trong Linux container** chạy trên Linux VM/kernel, khác với JVM native trên máy host.

Ví dụ Docker (yêu cầu Docker và image được kéo về):

```bash
docker run --rm --memory=128m eclipse-temurin:21-jdk \
    java -XshowSettings:vm -version
```

Tài liệu giải thích cách đo:

1. Docker giới hạn bộ nhớ cgroup của tiến trình Java.
2. HotSpot Linux hỗ trợ container có thể dùng giới hạn ấy khi chọn heap.
3. `-XshowSettings:vm` báo **max heap thực sự được JVM chọn**.
4. Số đó có thể **khác** các ví dụ `-XX:MaxRAM=128m` do cgroup hierarchy, JDK build, GC, flag ghi đè và các ràng buộc khác.

**Không đưa một output max heap cụ thể cho Docker command nếu chưa chạy chính image/resource spec đó.** Bài này đã kiểm thử các trường hợp `-XX:MaxRAM` để chứng minh cờ sizing, không giả vờ đã benchmark mọi image container.

Cũng đừng nhầm:

- `requests.memory` của Kubernetes: mức dành cho scheduler, **không phải giới hạn cứng**.
- `limits.memory`: mức giới hạn do container runtime/kernel áp dụng.
- `-XX:MaxRAM`: cơ sở sizing ở tầng HotSpot, **không tự tạo cgroup limit**.
- `-Xmx`: giới hạn **Java heap**, **không phải toàn bộ process RSS**.

Đặc biệt, nếu container **không có memory limit**, HotSpot có thể dựa vào lượng bộ nhớ lớn hơn dự kiến. Trong production cần hiểu resource spec thực và xác minh từ JVM.

## 12. Chương trình Java 17+ kiểm tra heap max thật sự

Tạo tệp `HeapSizingProbe.java` với nội dung:

```java
public final class HeapSizingProbe {

    private static long toMiB(long bytes) {
        return bytes / (1024L * 1024L);
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long maxHeap = runtime.maxMemory();

        System.out.println("maxHeapMiB=" + toMiB(maxHeap));
        System.out.println("maxHeapPositive=" + (maxHeap > 0));
    }
}
```

Biên dịch:

```bash
javac --release 17 HeapSizingProbe.java
```

Chạy trường hợp cơ sở 64 MiB:

```bash
java -XX:MaxRAM=64m HeapSizingProbe
```

Output trên Azul Zulu OpenJDK 24.0.2/HotSpot đã kiểm chứng qua giá trị `Runtime.maxMemory()`:

```text
maxHeapMiB=32
maxHeapPositive=true
```

Thử nâng tỷ lệ small-memory:

```bash
java -XX:MaxRAM=64m \
     -XX:MinRAMPercentage=75.0 \
     HeapSizingProbe
```

Output cùng môi trường:

```text
maxHeapMiB=48
maxHeapPositive=true
```

Các trường hợp khác đã đối chiếu bằng `Runtime.getRuntime().maxMemory()` và `-XshowSettings:vm` trên JDK 24:

| Lệnh JVM trước tên class | `maxHeapMiB` đã quan sát | Điều cần học |
| --- | ---: | --- |
| `-XX:MaxRAM=64m` | 32 | 50% mặc định trong small-memory case |
| `-XX:MaxRAM=64m -XX:MinRAMPercentage=75.0` | 48 | Tỷ lệ small-memory thay max heap |
| `-XX:MaxRAM=64m -XX:MinRAMPercentage=25.0` | 16 | Tỷ lệ thấp hơn thay max heap |
| `-XX:MaxRAM=64m -XX:MaxRAMPercentage=70.0` | 32 | Chỉ đổi tỷ lệ large-memory không ảnh hưởng ca nhỏ này |
| `-XX:MaxRAM=1g` | 256 | Mốc thường theo MaxRAMPercentage mặc định |
| `-XX:MaxRAM=1g -XX:MinRAMPercentage=75.0` | 256 | MinRAMPercentage không tác động ở ca lớn này |
| `-XX:MaxRAM=1g -XX:MaxRAMPercentage=70.0` | 718 | MaxRAMPercentage mới tác động trong ca lớn |
| `-XX:MaxRAM=64m -XX:MinRAMPercentage=75.0 -Xmx16m` | 16 | `-Xmx` tường minh thắng kết quả auto |

**Tại sao dùng MiB thay vì MB?** Các cờ `64m` và phép chia `1024×1024` phù hợp cách JVM diễn đạt đơn vị nhị phân. Viết rõ đơn vị để không nhầm “64 MB thập phân” với “64 MiB”. Output `-XshowSettings:vm` có thể dùng ký hiệu `M`; bảng trên báo theo MiB của chương trình.

**Ý nghĩa của `Runtime.maxMemory()`:** đây là mức bộ nhớ **tối đa JVM sẽ cố dùng cho heap**, khác với `Runtime.totalMemory()` (mức heap hiện được cấp/committed) và `Runtime.freeMemory()` (phần free trong heap hiện được cấp). Không suy rằng mọi container đang sử dụng toàn bộ con số đó.

## 13. Một cách QA tự động hóa kịch bản trên máy phát triển

Nếu không muốn copy kết quả số cố định vào script kiểm thử, có thể so sánh các ca **theo quan hệ**.

Giả sử sau khi biên dịch `HeapSizingProbe.java`, bạn có thể chạy:

```bash
java -XX:MaxRAM=64m HeapSizingProbe
java -XX:MaxRAM=64m -XX:MinRAMPercentage=75.0 HeapSizingProbe
java -XX:MaxRAM=1g HeapSizingProbe
java -XX:MaxRAM=1g -XX:MinRAMPercentage=75.0 HeapSizingProbe
```

**Các quan hệ muốn kiểm chứng trên bản HotSpot đang dùng:**

- Ở cơ sở 64 MiB, thay `MinRAMPercentage=50` thành `75` có thể **tăng** max heap; đây là branch small-memory.
- Ở cơ sở 1 GiB, đổi `MinRAMPercentage` có thể **không thay** max heap.
- Nếu `-Xmx` đã đặt, kết quả max heap phản ánh chính `-Xmx` tường minh.
- Các con số **không nhất thiết có cùng rounding** trên mọi GC/JDK.

Nếu muốn chạy trên Windows/PowerShell, các dòng ở trên đều là **một lệnh** và chạy bình thường. Các ví dụ nối nhiều dòng bằng dấu `\` ở những mục trước là cú pháp Bash, không phải PowerShell.

Với CI, không nên viết test “tất cả JVM đời sau đều phải trả chính xác 48 MiB” nếu sản phẩm không cố định bản HotSpot, GC và configuration. Test nên kết hợp **điều kiện có ý nghĩa của ứng dụng** (startup thành công, budget phù hợp, latency và không vượt memory limit) với một vài assertion về cấu hình flag đã được hỗ trợ.

## 14. Chẩn đoán qua `-XshowSettings:vm` và `PrintFlagsFinal`

Trước khi thay production flags, đo cấu hình thực tế:

```bash
java -XshowSettings:vm -version
```

Mục `VM settings` có thể báo:

```text
Max. Heap Size (Estimated): ...
```

Nếu có `-Xmx`, output có thể ghi `Max. Heap Size` không kèm `Estimated`. Việc xuất hiện hay không xuất hiện chữ `Estimated` không phải một API ổn định để phần mềm production tự parse; đây là **diagnostic dành cho con người**.

Có thể xem các cờ HotSpot:

```bash
java -XX:+PrintFlagsFinal -version
```

Ở output thường có những tên cần tìm:

```text
MinRAMPercentage
MaxRAMPercentage
InitialRAMPercentage
MaxRAM
MaxHeapSize
InitialHeapSize
UseContainerSupport
```

**Lưu ý:** `UseContainerSupport` có thể không xuất hiện/không được hỗ trợ ở JVM ngoài Linux hoặc implementation không tương thích. `-XX:+PrintFlagsFinal` hiển thị **giá trị và nguồn gốc flag** (default, command line, ergonomic…), không thay thế việc kiểm tra mức sử dụng bộ nhớ trong quá trình chạy.

Trên Linux container với HotSpot có hỗ trợ:

```bash
java -XshowSettings:system -version
java -Xlog:os+container=debug -version
```

Các lệnh này giúp xem container memory limit, provider cgroup và lý do JVM nhận hoặc không nhận các giới hạn. Đối chiếu chúng với các flag `MaxRAM`, `-Xmx` và output `HeapSizingProbe`.

**Không chỉ dựa vào `docker stats` một lần**: đó là số liệu hiện thời, không thể thay thế max heap cấu hình. Cũng không chỉ dựa vào `Runtime.maxMemory()` để biết cgroup limit.

## 15. Quan hệ với Kubernetes memory request/limit

Ví dụ cấu hình một container Java:

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "250m"
  limits:
    memory: "256Mi"
    cpu: "1"
```

Đây là **đoạn manifest** cần đặt trong cấu trúc Pod/Deployment thích hợp.

- `requests.memory = 128Mi`: scheduler dùng để xét khả năng đặt Pod, **không tự trở thành memory cap 128 MiB**.
- `limits.memory = 256Mi`: container runtime/kernel có thể áp cgroup memory limit theo giá trị đó.
- HotSpot Linux hỗ trợ container có thể nhận memory limit hiệu lực khi tự chọn heap.
- `MinRAMPercentage` chỉ tác động khi logic **small-heap** được chọn; không có nghĩa cứ một Pod khai báo request nhỏ thì JVM sẽ đi vào nhánh đó.
- `MaxRAMPercentage` có thể tác động khi cơ sở memory/heap lớn hơn, nhưng không nên gắn một tỷ lệ cao tùy tiện cho toàn bộ bộ nhớ container.

**Bẫy rất phổ biến:** ứng dụng Java đặt `-XX:MaxRAMPercentage=80` với container limit 256 MiB và nghĩ rằng “còn 20% là luôn đủ cho native memory”. Không có bảo đảm như vậy; số lượng thread, direct buffers, metaspace, logging/JIT và native/JNI khác nhau giữa workloads.

Trong môi trường rất nhỏ, phần native overhead có thể chiếm một tỷ lệ cao. Do đó chọn `MinRAMPercentage=75` có thể *hữu ích* nếu ứng dụng cần nhiều Java object và native ít, nhưng cũng có thể *gây hại* nếu native overhead lớn. Quyết định phải dựa trên đo thực tế.

## 16. Java heap OOME khác cgroup OOMKill

Hai nhóm lỗi cần nhận diện:

### A. `java.lang.OutOfMemoryError: Java heap space`

Điều này thường có nghĩa JVM không thể thỏa mãn allocation trong Java heap, do max heap/GC/workload, dù có thể container còn bộ nhớ ngoài heap.

Tín hiệu điều tra:

- `Runtime.maxMemory()`, heap usage và GC pressure.
- Heap dump nếu phù hợp và có quyền/dung lượng.
- Allocation profile, retained objects và tăng trưởng dữ liệu.
- Kiểm tra cấu hình `-Xmx` hoặc `MinRAMPercentage` ảnh hưởng đến cap.

Không chỉ tăng heap để che memory leak.

### B. Container bị OOMKill

Kernel/cgroup có thể kết thúc process vì **tổng bộ nhớ tính vào cgroup** vượt limit. Trong Kubernetes, container có thể nhận trạng thái `OOMKilled`, exit code thường thấy `137` do SIGKILL.

Điều tra:

- Memory limit, RSS/cgroup working set và event của kernel.
- Heap max và committed/used.
- Native memory, thread stacks, metaspace, code cache, direct memory.
- Sự tồn tại của tiến trình khác trong cùng cgroup và thay đổi limit.

**Tăng `MinRAMPercentage` có thể làm OOMKill dễ xảy ra hơn** trong container nhỏ vì heap được phép tăng mà native memory budget không tăng theo. Và giảm `MinRAMPercentage` có thể giảm rủi ro OOMKill nhưng làm tăng GC pressure hoặc Java heap OOME. Vì vậy cần một **cân bằng workload**, không có một giá trị phần trăm tối ưu chung cho mọi microservice.

## 17. Native Memory Tracking, metrics và khoảng trống ngoài heap

Với JDK có hỗ trợ, có thể bật **Native Memory Tracking** khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau đó có thể dùng `jcmd` đối với PID thích hợp:

```bash
jcmd <PID> VM.native_memory summary
```

Ở đây `<PID>` là placeholder thay bằng PID thực tế, không phải cú pháp Java nguyên văn. Chức năng này cần quyền truy cập phù hợp và có chi phí quan sát; dùng theo chính sách vận hành.

**Đừng chỉ nhìn mỗi Java heap trong dashboard.** NMT phân loại nhiều vùng native/VM allocation, nhưng cũng không phải một phép đo thay thế hoàn toàn cho RSS/cgroup memory accounting của hệ điều hành. Nên kết hợp:

- Java heap used/committed/max.
- GC throughput/pauses và allocation rate.
- Metaspace và code cache.
- Direct memory và thread count/stacks.
- Process/container RSS và memory.events.
- Cgroup limit, OOMKill/throttling/event.
- JDK build và garbage collector được dùng.

Nếu không muốn dùng NMT, vẫn có thể lấy Java heap metrics qua JMX/MemoryMXBean/JFR; nhưng cần hiểu chúng **không phản ánh toàn bộ memory của process**.

## 18. Khi nào nên chỉnh `MinRAMPercentage`?

Những tình huống **có thể cân nhắc** chỉnh:

- Container rất nhỏ và default max heap quá thấp so với lượng Java object cần giữ.
- Đã xác minh app bị `Java heap space` do heap cap nhỏ, không phải memory leak.
- Có **ngân sách native memory** đã đo và còn đủ sau khi tăng max heap.
- Có biểu đồ GC/latency cho thấy tăng heap nhỏ vừa phải giúp giảm chi phí GC.
- Đã kiểm thử trên **đúng JDK/vendor, GC và cgroup** dùng trong production.
- Có cơ chế giám sát OOMKill, restart count, startup latency và footprint.

Những tình huống **không nên chỉnh** chỉ vì thói quen:

- Tài liệu/cấu hình đã dùng `-Xmx` phù hợp.
- Container có memory limit lớn, nên `MinRAMPercentage` không phải nhánh quyết định max heap.
- Ứng dụng không gặp vấn đề heap size hay GC.
- Không biết memory limit thực tế đang là bao nhiêu.
- Chỉ dựa trên công thức “heap = 75% memory limit” mà chưa dành ngân sách cho native.
- Đang chạy JVM không phải HotSpot hoặc JDK không bảo đảm cùng flags.
- Mục tiêu là khống chế *minimum heap* hoặc *initial heap* — đây không phải flag đúng.

**Một phương án thay thế:** nếu yêu cầu production cần một max heap rõ và ít biến động, có thể đặt `-Xmx` dựa trên capacity planning thay vì dựa hoàn toàn vào heuristics phần trăm. Nhưng `-Xmx` cũng không tự bảo vệ process khỏi tất cả native-memory OOM.

## 19. Tình huống thực tế: service 64 MiB và service 1 GiB

### Tình huống A: footprint rất nhỏ

Một ứng dụng tối giản chạy trong container hiệu lực khoảng 64 MiB, không đặt `-Xmx`.

Theo thí nghiệm **sizing giả lập** `-XX:MaxRAM=64m` trên JDK 24:

```text
MinRAMPercentage=50 -> max heap 32 MiB
MinRAMPercentage=75 -> max heap 48 MiB
```

Nếu tăng phần trăm lên 75, app có thể giữ nhiều Java object hơn trước khi đụng heap cap, nhưng phần memory còn lại chỉ khoảng 16 MiB theo phép trừ **trên giấy**, chưa trừ các thành phần native vốn không nhỏ. Đây có thể là cấu hình **không phù hợp** cho một ứng dụng Java thực tế.

**Không kết luận** rằng `75%` là đề xuất mặc định cho 64 MiB container; bài thử chỉ giúp minh họa **hành vi flag**. Một số chương trình JVM còn có thể không khởi động ổn định trong ngân sách memory hạn hẹp.

### Tình huống B: service 1 GiB

Một service có cơ sở memory để tính heap khoảng 1 GiB.

Theo thí nghiệm `-XX:MaxRAM=1g`:

```text
Mặc định                  -> max heap 256 MiB
MinRAMPercentage=75.0     -> max heap 256 MiB
MaxRAMPercentage=70.0     -> max heap 718 MiB (đã căn chỉnh)
```

Ở đây tăng `MinRAMPercentage` không có tác dụng lên max heap. Nếu muốn điều chỉnh tỷ lệ cho trường hợp này, cờ `MaxRAMPercentage` mới là thứ cần xem xét. Dù vậy, không nên chọn 70% chỉ vì muốn heap lớn; phải tính native memory và tải ứng dụng.

### Tình huống C: đã đặt `-Xmx`

```text
MaxRAM=64m, MinRAMPercentage=75, -Xmx16m
  -> max heap đã quan sát: 16 MiB
```

Thứ cần chỉnh nếu thật sự muốn thay max heap là **`-Xmx`**. Không tăng `MinRAMPercentage` rồi kỳ vọng vượt qua một giới hạn max heap đã được cấu hình tường minh.

## 20. Cảnh báo về khả năng lặp lại kết quả giữa các JVM

Các quan sát 32/48/16/256/718 MiB thuộc một cấu hình kiểm thử cụ thể trên **HotSpot JDK 24.0.2**. Không phải mọi Java VM implementation đều dùng HotSpot hay hỗ trợ bộ flag `-XX` giống nhau.

Kết quả có thể chịu ảnh hưởng bởi:

1. Phiên bản và bản build JDK, kể cả backport về container awareness.
2. Garbage collector và các giới hạn heap tối thiểu/căn chỉnh.
3. Hệ điều hành, CPU architecture và page size.
4. Cgroup memory limit, ancestor cgroup và thông tin host được VM nhìn thấy.
5. Cờ `-Xms`, `-Xmx`, `MaxRAM`, `MaxHeapSize` cùng các tùy chọn GC khác.
6. Mức memory RAM dùng làm cơ sở khác với kết quả `docker stats`.
7. Build vendor hoặc runtime image triển khai có thể được tùy biến.

**Cách lập test đúng:** cố định JDK/GC/flags khi cần một expected number chính xác; đồng thời có integration test chạy trong container với resource limit thật. Nếu chỉ học cơ chế, nên kiểm tra **quan hệ** giữa các kịch bản để tránh biến một số rounding đặc thù thành “hợp đồng Java SE”.

## 21. Những hiểu nhầm phổ biến

| Hiểu nhầm | Thực tế | Hướng xử lý |
| --- | --- | --- |
| “`MinRAMPercentage` đặt minimum heap.” | Nó ảnh hưởng **maximum heap cho small heaps** | Với initial heap, xem `-Xms`/`InitialRAMPercentage` |
| “Đặt MinRAMPercentage=75 nghĩa heap luôn chiếm 75% RAM.” | Giá trị dùng trong sizing; không phải usage hoặc reservation | Kiểm tra `Runtime.maxMemory` và committed/used riêng |
| “Trong container 1 GiB, MinRAMPercentage=75 sẽ cho max heap 768 MiB.” | Nhánh small-heap thường không áp dụng | Xem `MaxRAMPercentage` hoặc `-Xmx` |
| “Cứ container dưới đúng 125 MB thì dùng MinRAMPercentage.” | “~125 MB” là mô tả small heap, không phải công tắc cgroup chính xác | Đo max heap thật trên JDK hiện dùng |
| “`MaxRAMPercentage=70` luôn cho 70% kể cả môi trường 64 MiB.” | Small-heap branch có thể chọn MinRAMPercentage | Thử cả hai flag trong ca ít RAM |
| “`MinRAMPercentage` cộng với `MaxRAMPercentage`.” | Hai nhánh ergonomics, không cộng phần trăm | Xác nhận flag và kích thước heap đã chọn |
| “`-Xmx` nhỏ nhưng tăng MinRAMPercentage sẽ ghi đè `-Xmx`.” | Cấu hình `-Xmx` tường minh quyết định max heap | Thay `-Xmx` nếu policy cho phép |
| “`-XX:MaxRAM=64m` chính là Docker memory=64m.” | MaxRAM là cơ sở sizing của VM, không áp cgroup limit | Muốn test container thật, chạy Docker `--memory` |
| “`Runtime.maxMemory` là RAM hiện đã dùng.” | Nó báo max Java heap | Dùng heap used/committed và RSS metrics |
| “Container có limit 128Mi, -Xmx128m chắc chắn an toàn.” | Native/stack/metaspace còn tốn RAM | Dành native overhead và test OOMKill |
| “`-Xms` bằng `MinRAMPercentage`.” | `-Xms` là initial heap, MinRAMPercentage liên quan max heap small | Phân biệt initial/max/used |
| “Nên tăng MinRAMPercentage lên 90% cho mọi microservice.” | Dễ thiếu native memory, có thể OOMKill | Capacity planning, đo GC/latency/RSS |
| “Memory request của Kubernetes là hard memory limit.” | Request giúp scheduling; limit mới ràng buộc kernel | Đọc resource spec/cgroup thực |
| “Java 10 flag đã lỗi thời, phải dùng ratio fraction cũ.” | Các cờ Percentage vẫn được tài liệu HotSpot hiện hành sử dụng | Dùng API/flag còn được hỗ trợ |
| “Thấy `Java heap space` là chắc chắn bị kernel OOMKill.” | Đây là hai cơ chế lỗi khác nhau | Chẩn đoán heap OOME vs cgroup kill |
| “Đổi một flag sẽ bảo đảm JVM có hiệu năng tốt.” | Hiệu năng phụ thuộc workload, GC, native memory | Đo benchmark và production metrics |
| “`PrintFlagsFinal` cho biết tổng RSS process.” | Nó cho biết cờ/config, không phải bộ đếm RSS | Dùng OS/cgroup metrics/NMT |

## 22. Bài tập tự kiểm tra

### Bài 1: giải nghĩa một flag

```bash
java -XX:MinRAMPercentage=75 -jar app.jar
```

**Hỏi:** Flag trên có bảo đảm JVM đặt `-Xms` bằng 75% RAM không?

**Đáp án:** **Không**. Nó tham gia lựa chọn **maximum heap cho tình huống small heap**, không đặt initial heap hay minimum heap. Nếu muốn đặt initial heap tường minh, dùng `-Xms`.

### Bài 2: mô hình ít bộ nhớ

Trên một HotSpot cụ thể, `-XX:MaxRAM=64m` với `MinRAMPercentage` mặc định cho max heap khoảng 32 MiB. Khi dùng `-XX:MinRAMPercentage=75`, dự kiến gì?

**Đáp án:** Max heap có thể tăng lên khoảng **48 MiB** trong kịch bản đã kiểm thử trên JDK 24. Nhưng **không** được suy rộng là mọi JVM và container 64 MiB đều an toàn với cấu hình đó.

### Bài 3: mô hình bộ nhớ lớn hơn

Với `-XX:MaxRAM=1g`, việc tăng `MinRAMPercentage` từ 50 lên 75 trên JDK 24 có làm max heap tăng từ 256 lên 768 MiB không?

**Đáp án:** **Không**. Kết quả đã đo là **256 MiB** ở cả hai trường hợp. Trong nhánh thường, `MaxRAMPercentage` có vai trò chính.

### Bài 4: tình huống đã đặt `-Xmx`

```bash
java -XX:MaxRAM=64m \
     -XX:MinRAMPercentage=75 \
     -Xmx16m HeapSizingProbe
```

**Hỏi:** Mức heap tối đa đã đo là bao nhiêu?

**Đáp án:** **16 MiB** trong bản HotSpot đã kiểm tra, vì `-Xmx16m` đặt max heap rõ ràng. `MinRAMPercentage` không được hiểu như mức sàn bắt buộc vượt qua `-Xmx`.

### Bài 5: lỗi memory trong container

Một pod có limit 128 MiB. Ứng dụng tăng `MinRAMPercentage` làm heap tối đa lớn hơn rồi bị `OOMKilled`. Có thể giải thích thế nào?

**Đáp án:** Heap được phép mở rộng chiếm thêm ngân sách trong khi native memory, stack, metaspace và buffer vẫn cần RAM. Khi tổng memory vượt cgroup limit, kernel có thể kill process. Kiểm tra heap used, native/RSS, memory events và limit; không chỉ nhìn `-Xmx`.

### Bài 6: hiểu `MaxRAM`

```bash
java -XX:MaxRAM=64m -XshowSettings:vm -version
```

**Hỏi:** Lệnh này có đặt memory limit 64 MiB cho toàn process giống Docker `--memory=64m` không?

**Đáp án:** **Không**. Nó thay cơ sở tính heap ergonomics của HotSpot. Docker memory limit là giới hạn do kernel/cgroup áp lên process/container.

### Bài 7: so hai con số khác nhau

Một application báo `Runtime.maxMemory() = 48 MiB`, dashboard container báo sử dụng RSS 70 MiB. Đây có nhất thiết là bug?

**Đáp án:** **Không**. Java heap max khác tổng native+heap memory/RSS. RSS có thể cao hơn Java heap max vì metaspace, code, stacks, native buffers và các vùng khác.

## 23. Checklist vận hành khi cấu hình heap cho container nhỏ

1. Xác nhận **runtime thật sự là HotSpot** và bản JDK còn được cập nhật, không dựa trên hướng dẫn cho các flag cũ.
2. Ghi version/vendor/build, GC và các cờ `-Xms`, `-Xmx`, `MaxRAM`, `MinRAMPercentage`, `MaxRAMPercentage`.
3. Xác nhận **memory limit thực** của container/cgroup, không suy từ Kubernetes request.
4. Nếu không có `-Xmx`, quan sát max heap JVM chọn bằng `-XshowSettings:vm` và `Runtime.maxMemory()`.
5. Nếu cơ sở memory nhỏ, hiểu rằng `MinRAMPercentage` **ảnh hưởng max heap** chứ không phải minimum heap.
6. Không coi “small heap ~125 MB” là công tắc **exactly 125 MB container RAM**.
7. Kiểm tra xem thay `MaxRAMPercentage` có thực sự tác động đến ca đang xét không.
8. Khi `-Xmx` được đặt, đừng kỳ vọng tăng phần trăm sẽ tự vượt cap đó.
9. Ước lượng native overhead: metaspace, code cache, threads, direct buffers, GC và các thành phần khác.
10. Phân biệt `java.lang.OutOfMemoryError` với kernel/container `OOMKilled`.
11. Đo heap used/committed/max cùng RSS/cgroup usage, GC pressure, startup latency và restarts.
12. Thử một vài giá trị trên **đúng image JDK** và runtime cgroup thực, không chỉ trên laptop.
13. Nếu đổi Java version hoặc collector, đo lại vì sizing/rounding/provider có thể khác.
14. Đừng chọn một tỷ lệ lớn chỉ vì nhìn tỷ lệ từ phép nhân: bảo đảm memory budget cho native.
15. Xác định rõ mục tiêu: **giảm Java heap OOME**, **giảm GC pressure**, **giảm RSS/OOMKill** hay **giữ latency**, vì chúng có thể cần giải pháp khác nhau.
16. Ưu tiên cấu hình giải thích được và được kiểm thử thay vì các mẹo tối ưu từ JDK cũ.

## Kết luận

`-XX:MinRAMPercentage` là **tùy chọn HotSpot vẫn còn hiện hành** dùng trong **tính *maximum Java heap* cho điều kiện bộ nhớ/heap nhỏ**, không phải tỷ lệ bảo đảm **minimum heap**. Tài liệu Java launcher mô tả small heap khoảng **125 MB** và mặc định `MinRAMPercentage=50%`. Ở các môi trường lớn hơn, `MaxRAMPercentage` (mặc định 25%) thường có vai trò quyết định max heap.

Thử nghiệm thực tế với `-XX:MaxRAM=64m` trên JDK 24 cho thấy thay `MinRAMPercentage` từ 50 lên 75 có thể đưa max heap từ **32 MiB lên 48 MiB**, trong khi thay cờ đó với `MaxRAM=1g` không làm kết quả **256 MiB** thay đổi. Khi đã đặt `-Xmx`, giới hạn tường minh ấy vẫn quyết định mức heap tối đa.

Trong container nhỏ, **lựa chọn heap phải tính cả memory ngoài heap và cgroup limit**. Cách làm đúng là kiểm tra JVM đang nhận RAM nào, đo max heap thực tế, theo dõi RSS/GC/OOMKill và kiểm thử trên đúng môi trường triển khai, thay vì đoán từ tên `MinRAMPercentage` hoặc một phép nhân phần trăm duy nhất.

## Tài liệu tham khảo chính thức và hiện hành

- [Oracle Java SE 25 — `java` launcher, `-XX:MinRAMPercentage`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): hợp đồng small heap khoảng 125 MB, mặc định 50%, ảnh hưởng **maximum heap** chứ không phải minimum heap.
- [Oracle Java SE 25 — `MaxRAMPercentage`, `InitialRAMPercentage`, `-XX:MaxRAM`, `-Xmx`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): phạm vi sizing, tỷ lệ mặc định và cấu hình heap tường minh.
- [OpenJDK — `java` launcher manual (source hiện hành)](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): mô tả các tùy chọn HotSpot/launcher được duy trì.
- [Oracle Java SE 25 — `-XX:-UseContainerSupport` và `-Xlog:os+container`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): nhận biết memory/CPU giới hạn trong Linux container.
- [Java SE 25 API — `Runtime.maxMemory()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#maxMemory()): phân biệt memory tối đa của heap với thông tin committed/free.
- [Java SE 25 API — `MemoryUsage`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): các giá trị init, used, committed và max.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): phân biệt memory request, limit và quy tắc áp giới hạn container.
- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): quan sát native memory bên ngoài Java heap.
