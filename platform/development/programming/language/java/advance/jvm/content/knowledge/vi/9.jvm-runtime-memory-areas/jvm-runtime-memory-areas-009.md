# Phân biệt bộ nhớ đã dùng, đã cam kết, đã dành trước và bộ nhớ tiến trình trong JVM

Khi theo dõi ứng dụng Java, bạn có thể thấy **heap used = 400 MiB**, **heap committed = 768 MiB**, **heap max = 2 GiB**, trong khi hệ điều hành báo **RSS = 1,1 GiB** và **virtual memory = nhiều GiB**. Những số này **không mâu thuẫn**: chúng đang đo những khía cạnh khác nhau và đôi khi còn thuộc những phạm vi khác nhau.

Muốn phân tích đúng việc dùng bộ nhớ JVM cần phân biệt ít nhất năm câu hỏi:

1. **Used**: phần bộ nhớ JVM **đang được ghi nhận đã dùng** trong một vùng quản lý cụ thể là bao nhiêu?
2. **Committed**: JVM đã **cam kết khả năng sử dụng** bao nhiêu dung lượng cho vùng ấy?
3. **Reserved**: JVM đã **dành trước không gian địa chỉ ảo** bao nhiêu, có thể lớn hơn phần committed?
4. **Process memory**: tiến trình Java thực tế có những vùng bộ nhớ nào bên ngoài Java heap, và hệ điều hành ghi nhận resident/virtual memory ra sao?
5. **Limit/maximum**: giới hạn do Java heap, native allocations, hệ điều hành hoặc container đặt ra là giới hạn của **phần nào**, không phải một con số dùng chung?

Bài lấy **Java SE 17 và HotSpot/OpenJDK phổ biến** làm bối cảnh. Các định nghĩa Java API và JVM memory areas là phần đặc tả; những thuật ngữ của **Native Memory Tracking (NMT)**, RSS/VSZ, tham số `-Xms`/`-Xmx` và hành vi container phụ thuộc implementation/hệ điều hành. Cần đọc đúng nguồn và phiên bản trước khi so sánh.

## 1. Tổng quan: một tiến trình Java không chỉ có Java heap

Trong một JVM đang chạy, có thể tồn tại đồng thời:

- **Java heap**: vùng phục vụ cấp phát objects/arrays theo ngữ nghĩa JVM, được GC quản lý. Đây là phần thường được giới hạn bằng `-Xmx`.
- **Metaspace/class metadata**: dữ liệu lớp và metadata mà HotSpot quản lý bằng bộ nhớ native (từ Java 8 trở đi), không đơn giản nằm trong giới hạn heap `-Xmx`.
- **Thread stacks**: vùng liên quan đến stack của các threads, cùng tài nguyên native dành cho từng thread.
- **Code cache/JIT**: mã máy đã biên dịch và cấu trúc hỗ trợ compiler/runtime.
- **Direct buffers và native allocations**: ví dụ `ByteBuffer.allocateDirect`, JNI, thư viện C/C++, thư viện nén/mã hóa, các native allocators.
- **Memory-mapped files, shared libraries, file-backed mappings**: cách hệ điều hành ánh xạ nội dung file vào không gian địa chỉ của tiến trình.
- **Cấu trúc của JVM và các thành phần khác**: GC, symbol/string structures, class loaders, agents, profiler, allocator fragmentation, runtime libraries.

Một số thành phần trên được JVM quản lý, một số do thư viện native hoặc hệ điều hành quản lý. **Không phải tất cả đều có mặt trong `MemoryMXBean.getHeapMemoryUsage()`**, và không phải mọi byte process RSS đều thuộc heap.

```text
                        Tiến trình Java
+---------------------------------------------------------------+
| Không gian địa chỉ ảo của tiến trình (VSZ / virtual size)      |
|                                                               |
|    Java heap reserved                                         |
|      +--------------------------------------+                 |
|      | Heap committed                       |                 |
|      | +-----------------------+             |                 |
|      | | Heap used              |             |                 |
|      | +-----------------------+             |                 |
|      +--------------------------------------+                 |
|                                                               |
|    Metaspace / class metadata                                  |
|    Thread stacks / code cache / GC native / direct buffers     |
|    Shared libraries / mapped files / JVM runtime / native libs |
+---------------------------------------------------------------+
   ^
   | OS resident pages (RSS) là một phép đo KHÁC:
   | những pages hiện cư trú trong RAM của tiến trình tại thời điểm đo
   | không phải diện tích của hình chữ nhật trên.
```

Sơ đồ này là **mô hình khái niệm**, không phải sơ đồ chính xác các khoảng địa chỉ VM, thứ tự cấp phát hay cam kết trang vật lý của mọi JVM.

## 2. “Used” là gì?

Trong Java Management API, `java.lang.management.MemoryUsage` mô tả tình trạng của **một vùng bộ nhớ** bằng `init`, `used`, `committed`, `max`. Trường **`used`** là lượng bộ nhớ **được ghi nhận đã sử dụng trong vùng ấy** tại thời điểm chụp snapshot.

Ví dụ:

- **Heap used**: dung lượng heap đang có các allocations/objects và cấu trúc được vùng heap quản lý ghi nhận là đã sử dụng theo cách GC/JVM đo.
- **Non-heap used**: dung lượng các vùng non-heap mà API quản lý ghi nhận; **không phải** tổng toàn bộ native allocations của process.
- **Memory pool used**: lượng dùng của một pool cụ thể như một heap generation hoặc metaspace, với ngữ nghĩa và thời điểm cập nhật tùy pool.

### Used không hoàn toàn đồng nghĩa live objects

**Used có thể khác lượng bộ nhớ của các object còn sống sau một full GC.**

- Trước GC, heap có thể chứa các object đã **không còn reachable** nhưng chưa được reclaim. Chúng vẫn có thể ảnh hưởng used cho đến khi GC xử lý.
- Sau GC, mức used có thể giảm; không nên kỳ vọng mức giảm đúng bằng số bytes của các object đã mất reference.
- GC có thể có region, allocation buffer, overhead và các giới hạn hạch toán riêng. Không nên tính chính xác retained heap từ một con số used đơn lẻ.
- Muốn biết object nào giữ memory, dùng **heap histogram, heap dump hoặc profiler phù hợp**; muốn biết heap đang tăng hay giảm, theo dõi used theo **thời gian và qua các lần GC**.

Ví dụ ứng dụng có heap used tăng từ 350 lên 600 MiB rồi về 380 MiB sau GC không nhất thiết bị memory leak. Cần xem **đường xu hướng sau GC**, allocation rate, GC overhead và retained objects.

## 3. “Committed” là gì?

`MemoryUsage.getCommitted()` mô tả lượng bộ nhớ JVM **đã cam kết sẵn sàng sử dụng** cho vùng được báo cáo. Với Java heap, đây là mức dung lượng heap đang được JVM/GC quản lý và đã đưa vào phạm vi dùng được, thường nằm giữa used và max nếu max được xác định.

Bất biến cơ bản trong `MemoryUsage`:

```text
0 <= used <= committed

Nếu max >= 0:
    committed <= max
```

Đừng áp dụng bất biến ấy một cách mù quáng giữa **hai nguồn số liệu khác nhau**: heap used trong MXBean và NMT reserved của toàn process không phải bốn trường của cùng một `MemoryUsage` object.

### Committed không phải RSS

**Committed không đồng nghĩa mỗi byte đã có page vật lý resident trong RAM ngay lúc đo.**

Lý do:

- Hệ điều hành quản lý virtual memory và cấp phát/touch physical pages theo cơ chế của nó. Một khoảng memory có thể đã committed nhưng chưa được chạm tới hoặc đã bị paging.
- Runtime và OS có thể dùng các kỹ thuật như demand paging, transparent huge pages, swap hay lazy physical backing.
- Ngược lại, RSS có thể bao gồm **mmap file pages, native allocations, code cache, thread stacks** và thành phần khác ngoài Java heap.
- Vì vậy, heap committed = 800 MiB **không suy ra** process RSS phải đúng 800 MiB, lớn hơn 800 MiB hay nhỏ hơn 800 MiB trong mọi môi trường.

**Committed của JVM** cũng không nên đồng nhất máy móc với thuật ngữ **commit charge** trong công cụ Windows: hệ điều hành có một hệ thống hạch toán riêng, không cùng tập vùng và không nhất thiết đo cùng điều kiện.

### Committed trừ used nói điều gì?

Trong cùng một `MemoryUsage` snapshot:

```text
committed - used = phần dung lượng đã cam kết nhưng chưa được ghi nhận là đang dùng
```

Con số đó **không** cho biết:

- Hệ điều hành còn bao nhiêu RAM vật lý.
- JVM chắc chắn cấp phát được thêm đúng từng đó object bytes mà không GC.
- Số byte live objects sẽ còn lại sau GC.
- Bao nhiêu memory phải trả lại hệ điều hành nếu ngừng tạo object.

Đây là một phép chênh lệch hạch toán **bên trong vùng JVM**; việc cấp phát thực còn phụ thuộc layout, GC, contiguous allocation/region constraints và overhead.

## 4. “Reserved” là gì?

Ở mức virtual memory, **reserved** thường là không gian **địa chỉ ảo** mà runtime dành cho một mục đích như Java heap, thread stack hoặc code cache; **committed** là phần bên trong reservation được cam kết sử dụng.

Trên HotSpot, công cụ **Native Memory Tracking (NMT)** có thể hiển thị các categories với:

```text
reserved = ... KB
committed = ... KB
```

Điều quan trọng:

1. **Reserved không phải số RAM đã cấp thật**; dành địa chỉ ảo không có nghĩa đã có physical pages backing cho toàn bộ khoảng.
2. **Reserved có thể lớn hơn committed**; ví dụ heap có thể dành không gian địa chỉ gần heap maximum để có chỗ tăng sau này nhưng chỉ cam kết một phần.
3. **Committed có thể lớn hơn used** nếu vùng có metric used tương ứng; nhưng NMT không phải lúc nào cũng báo một trường used tương ứng với cùng ý nghĩa của heap MXBean.
4. **Reserved không đồng nghĩa mọi virtual address range của process**; NMT chỉ bao phủ bộ nhớ mà cơ chế theo dõi ấy ghi nhận, không phải bất kỳ mapping nào có thể xuất hiện.
5. Reservation lớn có thể khiến **VSZ/VmSize** trông cao, nhưng một giá trị VSZ lớn không tự chứng minh ứng dụng đang tiêu thụ nhiều RAM vật lý.

### Ví dụ số *giả định* để hiểu khái niệm

Giả sử ở một thời điểm, một ứng dụng có các số **minh họa**:

| Số đo | Giá trị giả định | Ý nghĩa |
| --- | ---: | --- |
| Heap max | 2.048 MiB | Giới hạn heap có thể dùng của cấu hình runtime |
| Heap reserved (NMT) | 2.048 MiB | Không gian địa chỉ ảo dành trước cho heap trong ví dụ |
| Heap committed | 768 MiB | Phần heap đã cam kết cho sử dụng |
| Heap used | 400 MiB | Phần heap đang được JVM ghi nhận đã dùng |
| Process RSS | 1.100 MiB | Tổng resident pages được hệ điều hành hạch toán cho tiến trình |
| Process virtual size | 6.000 MiB | Tổng không gian địa chỉ ảo được ánh xạ trong tiến trình |

Đây là **bộ số giả định để giảng giải**, không phải kết quả thực đo trên một JVM. Có thể kiểm tra `400 <= 768 <= 2048` trong heap metric, nhưng **không thể lấy `1100 - 768 = 332` rồi khẳng định chính xác đó là toàn bộ native memory**. RSS và heap committed không đo cùng điều, còn shared/file-backed mappings, unused committed pages và các hiệu ứng OS khiến phép trừ đó không có ý nghĩa kết toán chuẩn.

## 5. “Max” khác reserved và committed như thế nào?

Trong `MemoryUsage`, **`max`** là dung lượng lớn nhất vùng ấy có thể dùng theo contract của metric; **`-1`** nghĩa là giá trị tối đa **không xác định**.

Với Java heap trên HotSpot:

- `-Xmx` thường giới hạn **heap maximum**, chứ không phải toàn bộ resident memory/virtual memory của process.
- `-Xms` thường đặt **initial heap size** hoặc mức heap khởi đầu mà JVM quản lý.
- Runtime có thể **tăng/giảm committed heap** giữa mức đang dùng và cấu hình/giới hạn, tùy collector, flags và điều kiện OS.
- Heap **reserved** có thể liên quan vùng địa chỉ dành cho heap maximum, nhưng **không phải lời bảo đảm số NMT reserved luôn bằng đúng `-Xmx`** trong mọi build/GC.
- `max` của một non-heap memory pool có thể trả `-1`, hoặc có giới hạn riêng không liên quan `-Xmx`.

Vì vậy cách diễn giải:

```text
-Xmx2g
  không có nghĩa:
    process RSS <= 2 GiB
    process VSZ <= 2 GiB
    total native + heap memory <= 2 GiB
```

Nếu ứng dụng dùng heap 1,4 GiB, direct buffers 500 MiB, metaspace, code cache, threads và native libraries, **process memory có thể vượt mức `-Xmx`** dù heap vẫn nằm dưới giới hạn.

### Tránh nhập nhằng giữa `-Xms` và “used lúc khởi động”

`-Xms512m` **không** nói 512 MiB object đã được tạo ngay khi JVM bắt đầu. Heap **committed** khởi đầu có thể gần cỡ cấu hình, nhưng heap **used** phản ánh lượng đã được sử dụng. Có thể JVM còn pre-touch memory nếu bật các flag liên quan (ví dụ `-XX:+AlwaysPreTouch` trong môi trường hỗ trợ), ảnh hưởng resident footprint; đừng suy runtime RSS chỉ từ `-Xms`.

## 6. Bộ nhớ tiến trình: RSS, VSZ/VmSize và PSS

Các công cụ hệ điều hành không dùng cùng tập metrics với JVM.

| Chỉ số OS | Khái niệm | Điều KHÔNG thể kết luận chỉ từ một số |
| --- | --- | --- |
| **RSS** (Resident Set Size) | Số physical resident pages hiện được gán cho process theo phương pháp đếm của OS | Không phải heap used, không phải heap committed, không phải private memory thuần túy |
| **VSZ/VIRT/VmSize** | Tổng kích thước các virtual memory mappings của process | Không phải RAM đã sử dụng thực tế |
| **PSS** (Proportional Set Size; Linux) | Resident memory được quy đổi theo tỷ lệ chia sẻ các pages dùng chung | Không phải heap used; cũng không phải một loại NMT reserved |
| **Private dirty / anonymous RSS** | Các góc nhìn OS vào resident private/anonymous pages | Không thể tự tách chính xác heap khỏi mọi loại native allocation |
| **Peak RSS / VmHWM** | Mức resident high-water mark đã ghi nhận | Không phải giá trị RSS hiện tại |
| **Swap** | Những pages/charges đã nằm ở swap theo công cụ OS | Không tự cho biết kiểu Java object nào bị paging |

### Tại sao RSS có thể cao hơn heap committed?

Vì RSS chứa resident pages của **nhiều vùng ngoài heap**, ví dụ native buffers, mã máy/JIT, metaspace, thread stacks, memory-mapped files và shared libraries. Không có ràng buộc “RSS phải nhỏ hơn `-Xmx`”.

### Tại sao RSS có thể thấp hơn heap committed?

Một vùng heap đã committed có thể chưa được chạm hết hoặc một số pages không đang resident. OS memory policy và collector khiến những vùng committed/virtual và resident không trùng nhau.

### Tại sao VSZ có thể rất lớn?

Mỗi reserved virtual range đóng góp địa chỉ ảo. Heap, thread stacks, code cache, mmap và các reservations khác có thể làm VSZ lớn hơn nhiều RAM vật lý. Chỉ số VSZ cao **tự nó không phải bằng chứng memory leak**. Phải phân tích thêm tốc độ tăng, RSS/PSS, native allocations, container limit và trạng thái ứng dụng.

### Shared memory làm phép cộng RSS nhiều tiến trình dễ sai

Nếu hai processes ánh xạ cùng một shared library page, RSS của mỗi process có thể **đếm toàn bộ page ấy**. Tổng RSS hai processes có thể **đếm trùng shared pages**. PSS là góc nhìn bổ sung trên Linux khi muốn quy phần shared theo tỷ lệ; nó cũng không trở thành metric used của JVM.

## 7. MemoryMXBean và MemoryUsage của Java 17

Java Management API cung cấp metric theo **heap** và **non-heap**:

- `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()`
- `ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()`
- `ManagementFactory.getMemoryPoolMXBeans()`, với `MemoryPoolMXBean.getUsage()` cho từng pool.

Các đối tượng `MemoryUsage` có bốn trường:

| Method | Ý nghĩa |
| --- | --- |
| `getInit()` | Dung lượng khởi tạo JVM yêu cầu, hoặc `-1` nếu không xác định |
| `getUsed()` | Dung lượng được ghi nhận đang dùng |
| `getCommitted()` | Dung lượng JVM đã cam kết sẵn sàng dùng |
| `getMax()` | Giới hạn vùng nếu biết, có thể là `-1` |

**Đây là các metric theo vùng JVM**, không phải mọi native allocations của process; đọc chúng không yêu cầu parsing OS `/proc`.

### Ví dụ Java 17 hoàn toàn xác định: bốn trường của MemoryUsage

Tạo **`MemoryUsageExample.java`**:

```java
import java.lang.management.MemoryUsage;

public class MemoryUsageExample {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        // Số liệu giả định: không đo JVM hiện tại.
        MemoryUsage sample = new MemoryUsage(
                0L, 40L * MIB, 96L * MIB, 512L * MIB);

        System.out.println("used=" + sample.getUsed() / MIB + "MiB");
        System.out.println("committed=" + sample.getCommitted() / MIB + "MiB");
        System.out.println("max=" + sample.getMax() / MIB + "MiB");
        System.out.println("committedMinusUsed="
                + (sample.getCommitted() - sample.getUsed()) / MIB
                + "MiB");
        System.out.println("invariant="
                + (sample.getUsed() <= sample.getCommitted()
                && sample.getCommitted() <= sample.getMax()));
    }
}
```

```bash
javac --release 17 MemoryUsageExample.java
java MemoryUsageExample
```

**Stdout chính xác:**

```text
used=40MiB
committed=96MiB
max=512MiB
committedMinusUsed=56MiB
invariant=true
```

Lưu ý: constructor `MemoryUsage` trong bài tạo **một snapshot giả định có số cố định**, không cấp phát thật 512 MiB hay thay đổi `-Xmx`. Không lấy các số này để kết luận về máy đang chạy.

### Ví dụ Java 17 lấy số liệu JVM thật

Tạo **`LiveJvmMemory.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public class LiveJvmMemory {
    private static final long MIB = 1024L * 1024L;

    private static String amount(long bytes) {
        return bytes < 0 ? "undefined"
                : String.format("%.1f MiB", bytes / (double) MIB);
    }

    private static void show(String name, MemoryUsage usage) {
        System.out.println(name
                + ": used=" + amount(usage.getUsed())
                + ", committed=" + amount(usage.getCommitted())
                + ", max=" + amount(usage.getMax())
                + ", init=" + amount(usage.getInit()));
    }

    public static void main(String[] args) {
        show("heap", ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage());
        show("non-heap", ManagementFactory.getMemoryMXBean()
                .getNonHeapMemoryUsage());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                show("pool " + pool.getName(), usage);
            }
        }
    }
}
```

```bash
javac --release 17 LiveJvmMemory.java
java -Xms128m -Xmx512m LiveJvmMemory
```

**Stdout phụ thuộc JVM, GC, thời điểm chạy và OS** — không có một bộ số bytes chính xác chung cho mọi máy. Mẫu **chỉ minh họa định dạng**, không phải kết quả đã đo:

```text
heap: used=<số> MiB, committed=<số> MiB, max=<số> MiB, init=<số> MiB
non-heap: used=<số> MiB, committed=<số> MiB, max=undefined, init=<số> MiB
pool <tên pool>: used=<số> MiB, committed=<số> MiB, max=<số hoặc undefined>, init=<số> MiB
```

**Không dùng mẫu trên làm regex yêu cầu output chính xác**: ví dụ dấu `<...>` ở đây là ký hiệu giải thích, giá trị non-heap max không bắt buộc lúc nào cũng `undefined`, danh sách pool phụ thuộc collector.

### Vì sao cộng tất cả memory pools không phải lúc nào khớp một snapshot heap?

- Các giá trị có thể được chụp **không đồng thời**, GC hoặc allocation xảy ra giữa những lần gọi.
- GC chia heap thành các pools/regions theo chính sách của collector; giá trị maximum một pool có thể không xác định hoặc biến động.
- Những metrics được cập nhật ở các thời điểm khác nhau và theo cấu trúc pool; không dùng tổng thủ công làm tiêu chuẩn bắt buộc chính xác từng byte bằng heap aggregate trong mọi release/collector.
- Non-heap MXBean không là phép đo trọn vẹn RSS hoặc mọi native allocation.

## 8. Runtime.totalMemory/freeMemory/maxMemory: cùng hướng, nhưng là snapshot khác

Một API quen thuộc:

```java
Runtime runtime = Runtime.getRuntime();
long total = runtime.totalMemory();
long free = runtime.freeMemory();
long max = runtime.maxMemory();
long approximateUsed = total - free;
```

Đây là **fragment minh họa** đặt trong một method.

- `totalMemory()`: dung lượng heap mà JVM đang có thể sử dụng theo contract của runtime, thường được so sánh với **heap committed**.
- `freeMemory()`: phần dung lượng heap còn trống **trong mức total hiện tại**, không phải RAM vật lý còn rảnh.
- `maxMemory()`: giới hạn tối đa JVM cố gắng sử dụng cho heap, không phải process RSS limit.
- `total - free` là phép ước lượng **heap currently used** tại thời điểm gọi, nhưng mỗi method là một lần quan sát riêng; allocation/GC có thể diễn ra giữa các lần gọi nên không đòi nó trùng tuyệt đối với `MemoryMXBean` đọc sau.

Không dùng `Runtime.freeMemory()` làm “máy còn bao nhiêu GB RAM” và không suy rằng `Runtime.maxMemory()` giới hạn cả direct buffers, metaspace và thread stacks.

## 9. Native Memory Tracking (NMT): nhìn reserved/committed phía HotSpot

**Native Memory Tracking** là một khả năng chẩn đoán của HotSpot/OpenJDK để theo dõi những allocation/mapping thuộc phạm vi JVM hỗ trợ. NMT có thể phân loại theo những categories như **Java Heap**, **Class**, **Thread**, **Code**, **GC**, **Compiler**, **Internal**, v.v., với tổng **reserved** và **committed**.

NMT là công cụ *implementation-specific*, không phải `MemoryMXBean` chuẩn bắt buộc mọi JVM triển khai giống nhau. Các category names và thống kê có thể khác theo JDK build/collector.

### Bật NMT từ lúc khởi chạy

Ví dụ:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m LiveJvmMemory
```

Chương trình `LiveJvmMemory` trong ví dụ trước kết thúc rất nhanh nên có thể không còn process để attach. Trong ứng dụng thật, hãy bật NMT ở **JVM process chạy đủ lâu** (server hoặc chương trình có thời gian chờ hợp lệ) rồi dùng process ID của nó.

Khi process đang chạy:

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

Đây là lệnh **minh họa với placeholder `<PID>`**; thay bằng số PID thật và thực hiện khi VM còn chạy. Nếu NMT chưa bật ở **startup**, không thể mặc định yêu cầu `summary` rồi đợi có dữ liệu; nó phải được cấu hình phù hợp lúc bắt đầu JVM.

### Dạng output NMT minh họa

```text
Native Memory Tracking:
Total: reserved=...MB, committed=...MB

- Java Heap (reserved=...MB, committed=...MB)
- Class     (reserved=...MB, committed=...MB)
- Thread    (reserved=...MB, committed=...MB)
- Code      (reserved=...MB, committed=...MB)
- GC        (reserved=...MB, committed=...MB)
```

Các dòng này **chỉ mô tả cách đọc**, không đại diện cho một kết quả NMT thực tế, và không cố gắng liệt kê mọi category. Với một số vùng được JVM theo dõi bằng `malloc`, NMT có thể tính phần allocated như reserved và committed tương ứng; các memory maps có thể có reserved lớn hơn committed. Đừng áp đặt cùng một mô hình reservation đơn giản lên tất cả dòng.

### Theo dõi *delta* thay vì chỉ một ảnh chụp

Một cách dùng phổ biến:

```bash
jcmd <PID> VM.native_memory baseline
# Cho workload đi qua giai đoạn cần quan sát.
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Nếu NMT khởi động ở chế độ detail, có thể dùng thêm các báo cáo chi tiết phù hợp như `detail`/`detail.diff` khi công cụ hỗ trợ. Vì `summary` ít overhead hơn `detail`, cần cân đối chi phí theo môi trường vận hành.

**Đọc delta đúng cách:** NMT native committed tăng đáng kể ở mục Thread có thể gợi ý nhiều threads hơn; mục Class tăng có thể gợi ý class metadata/classloaders; mục Code có thể tăng theo JIT. Đây là **dấu hiệu điều tra**, không tự chứng minh nguồn leak hay chỉ ra Java object nào giữ memory.

### NMT không đo toàn bộ native memory của mọi thư viện

Phạm vi NMT không bao trùm một cách đầy đủ những native allocations do các thư viện bên thứ ba tự thực hiện ngoài cơ chế JVM được theo dõi. Nó cũng không phải RSS trực tiếp. Vì vậy:

- **NMT committed != process RSS** là điều bình thường.
- **NMT reserved != process VSZ** là điều bình thường.
- Process RSS tăng mà NMT committed ít thay đổi có thể xuất phát từ mmap/file-backed pages, thư viện native/JNI, allocator behavior hoặc phần không được NMT ghi nhận.
- Cần dùng công cụ OS/native profiler tương ứng để điều tra tiếp, không suy “RSS - NMT committed = memory leak bytes” như công thức chính xác.

## 10. Direct buffers, metaspace và thread stacks nằm ngoài câu chuyện heap used

### Direct ByteBuffer

`ByteBuffer.allocateDirect(size)` cấp phát buffer với backing memory ngoài Java heap theo cơ chế JVM/runtime. **Object `ByteBuffer` wrapper/reference vẫn có thể tồn tại trên heap**, còn backing memory có thể được quản lý native; do đó:

- Java heap used tăng ít **không** chứng minh direct memory không tăng.
- `-Xmx` không phải giới hạn duy nhất cho việc cấp phát direct buffers.
- HotSpot có tùy chọn liên quan như `-XX:MaxDirectMemorySize`; mặc định và cách enforcement cần đối chiếu JDK/build.
- Thời điểm giải phóng backing memory có thể liên quan reference reachability, cleaners và GC, không nhất thiết lập tức ngay lúc biến local ra khỏi scope.

### Chương trình Java 17 minh họa: direct allocation và heap wrapper

Tạo **`DirectMemoryDemo.java`**:

```java
import java.nio.ByteBuffer;

public class DirectMemoryDemo {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(1024);
        ByteBuffer direct = ByteBuffer.allocateDirect(1024);

        System.out.println("heapDirect=" + heap.isDirect());
        System.out.println("nativeDirect=" + direct.isDirect());
        System.out.println("heapCapacity=" + heap.capacity());
        System.out.println("nativeCapacity=" + direct.capacity());
    }
}
```

```bash
javac --release 17 DirectMemoryDemo.java
java DirectMemoryDemo
```

**Stdout chính xác:**

```text
heapDirect=false
nativeDirect=true
heapCapacity=1024
nativeCapacity=1024
```

`isDirect()` cho biết buffer thuộc kiểu direct theo API, **không** đo RSS chính xác. Demo này không chứng minh sẽ tăng đúng 1024 bytes resident vì wrapper, alignment, native allocator và policies của OS còn tham gia.

### Metaspace

HotSpot từ Java 8 dùng **native memory cho class metadata** trong metaspace. Khi load nhiều class hoặc giữ nhiều class loaders sống, native committed cho class metadata có thể tăng trong khi **heap used không tăng tương ứng**. Vẫn có các objects trên heap liên quan tới Class/class loaders; nói “mọi thứ về class đều không ở heap” cũng sai.

- `-XX:MaxMetaspaceSize` là một ví dụ cấu hình giới hạn metaspace trên HotSpot; không phải tổng native memory limit.
- `OutOfMemoryError: Metaspace` gợi ý vấn đề class metadata và giới hạn/tài nguyên, không kết luận ngay “phải tăng `-Xmx`”.
- Nếu nghi class loader leak, xem số lượng classes/loaders, unloading behavior, references giữ class loader và NMT/ClassLoader-related diagnostics.

### Thread stacks

Nhiều threads có thể tăng nhu cầu stack/native memory ngay cả khi heap used không đổi nhiều:

- Tham số như `-Xss` ảnh hưởng tài nguyên stack của threads (mức độ áp dụng tùy JVM/loại thread và OS).
- NMT có thể hiển thị **Thread reserved lớn hơn committed** vì reserved stack space không nhất thiết toàn bộ được cam kết/touch.
- Việc tạo thread còn tốn tài nguyên OS khác, và container có thể có giới hạn PID/thread count.
- `java.lang.OutOfMemoryError: unable to create native thread` không nhất thiết do heap đầy; có thể liên quan memory native, OS process/thread limits hoặc resource controls.

Không lấy `Threads × -Xss` làm phép đo RSS chính xác. Đó có thể là ước lượng không gian stack virtual đã reserved, không phải resident pages thật.

## 11. Đọc số liệu hệ điều hành trên Linux

Nếu Java chạy trên Linux, có thể kiểm tra thông tin tiến trình với PID hợp lệ:

```bash
ps -o pid,rss,vsz,comm -p <PID>
grep -E 'VmSize|VmRSS|VmHWM|RssAnon|RssFile|VmSwap|Threads' /proc/<PID>/status
cat /proc/<PID>/smaps_rollup
```

Đây là **các lệnh minh họa**; thay `<PID>` bằng PID thật, và `smaps_rollup` có thể bị hạn chế bởi quyền truy cập hoặc không khả dụng trên kernel cũ. `ps` thường hiển thị RSS/VSZ theo KiB trên Linux; đọc manual của môi trường thay vì giả định đơn vị trên mọi OS.

Ý nghĩa thực hành:

- `VmSize` liên quan **virtual address space**, không phải RAM đã tiêu thụ.
- `VmRSS` gần góc nhìn RSS của process, gồm nhiều loại resident pages, có thể chia sẻ.
- `RssAnon` và `RssFile` giúp phân biệt anonymous/file-backed pages theo OS bookkeeping, **không trực tiếp chỉ ra Java heap vs non-heap**.
- `smaps_rollup` có thể cho RSS/PSS và private/shared metrics tổng hợp; hữu ích nếu RSS có nhiều file-backed/shared mappings.
- Số liệu ở những nguồn khác nhau chụp vào **những thời điểm khác nhau**; CPU/GC/allocator có thể thay đổi memory giữa các lần đo.

### OS memory và JVM metrics cần ghép theo cùng PID, cùng thời điểm

Nếu chạy nhiều JVM trên máy, hãy xác định PID của **đúng ứng dụng**. `jcmd -l` có thể liệt kê một số Java processes khả dụng; `ps` giúp xem process; container PID namespace có thể khiến PID quan sát bên trong và ngoài container **khác nhau**.

Đừng so heap used của JVM A với RSS của JVM B hoặc tổng RSS của cgroup/container rồi kết luận có leak trong JVM A.

## 12. Container memory: không phải Java heap maximum

Trong container hoặc Kubernetes, cgroup giới hạn **tài nguyên toàn cgroup/container**, không chỉ Java heap. Với Linux cgroup v2, các tệp hay gặp:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
```

**Đường dẫn chỉ là ví dụ cho môi trường cgroup v2 phổ biến**; hệ thống có thể mount ở nơi khác, dùng cgroup v1 hoặc giới hạn quyền truy cập.

- `memory.current`: bộ nhớ đang được cgroup hạch toán, có thể gồm **anonymous memory, page cache, kernel memory** và các thành phần tùy cơ chế kernel.
- `memory.max`: hard limit của cgroup, hoặc chuỗi `max` nếu không có giới hạn hữu hạn tại tệp ấy.
- `memory.stat`: phân rã các nguồn sử dụng cgroup theo kernel.
- `memory.events`: các sự kiện như chạm giới hạn, OOM/OOM-kill trong scope phù hợp.

**Container memory usage không bằng process RSS** nếu cgroup có nhiều processes, cache và các vùng kernel được hạch toán. Một container còn có thể bị **OOM killed** bởi kernel dù JVM chưa từng ném `OutOfMemoryError: Java heap space`, vì tổng tiêu thụ cgroup vượt limit.

### Ví dụ bài toán sizing

Giả sử limit container là **2 GiB** và đặt `-Xmx2g`. Cấu hình này **không chừa ngân sách** cho metaspace, stacks, code cache, GC native allocations, direct buffers, agents, mapped memory, OS/page-cache accounting. Do đó nguy cơ container memory pressure rất cao, kể cả khi Java heap used chưa chạm 2 GiB.

Cách tính budget cần bao gồm:

```text
Container / process budget (ước lượng, không phải đẳng thức RSS)
    = heap target
    + direct/native buffers
    + metaspace/classes
    + thread stacks
    + code cache + GC/JVM internals
    + native libraries, agents
    + headroom cho runtime và kernel accounting
```

**Không** cộng số heap used, NMT reserved và RSS lại với nhau: chúng là những góc nhìn chồng lấn. Ưu tiên đo số liệu thật theo peak workload và có headroom, thay vì ghép các metric không cùng đơn vị/ngữ nghĩa.

### Đừng đoán nguyên nhân exit code đơn độc

Exit status như `137` trong một số môi trường thường liên quan signal `SIGKILL`, có thể do container OOM killer hoặc bị kill bên ngoài. **Một exit code riêng lẻ không chứng minh kernel OOM**; kiểm tra Kubernetes events, cgroup `memory.events`, logs và thông tin orchestrator.

## 13. Bảng đối chiếu các công cụ quan sát

| Công cụ/API | Có thể thấy | Không cung cấp trực tiếp |
| --- | --- | --- |
| `MemoryMXBean.getHeapMemoryUsage()` | Heap used/committed/max/init | Process RSS/VSZ và tất cả native allocations |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Non-heap managed usage | Toàn bộ native memory của thư viện bên thứ ba |
| `MemoryPoolMXBean` | Usage của pool theo collector/manager | Một snapshot OS resident không sai lệch |
| `Runtime.totalMemory/freeMemory/maxMemory` | Các thông tin heap ở mức API | RAM còn trống của máy |
| `jcmd <PID> GC.heap_info` | Thông tin heap/GC tùy JVM | Toàn bộ process memory mapping |
| `jstat -gc <PID>` | GC/heap pool counters tùy collector | Tổng RSS chính xác |
| `jcmd <PID> VM.native_memory summary` | NMT reserved/committed thuộc phần JVM theo dõi | Mọi native allocation và RSS vật lý |
| `ps`, `/proc/<PID>/status` | Process VSZ/RSS/thread counters theo Linux | Heap objects reachable hoặc ownership Java |
| `/proc/<PID>/smaps_rollup` | PSS/RSS, private/shared memory rollup | Object histogram hoặc GC reachability |
| cgroup `memory.current`/`memory.max` | Usage/limit của cgroup | Mỗi method/object Java đã dùng bao nhiêu |
| Heap dump/profiler | Objects/retained heap/allocations tùy chế độ | Mặc định không cho full native RSS breakdown |

**Tránh “một metric làm nguồn sự thật duy nhất”**. Hãy bắt đầu từ câu hỏi chẩn đoán cụ thể: heap leak, direct/native leak, nhiều threads, metaspace growth hay OS/container pressure.

## 14. Một quy trình đo có thể lặp lại trên Java 17

### Bước 1: chốt môi trường và giới hạn

Ghi ít nhất: JVM vendor/build, Java version, GC, `-Xms`/`-Xmx`, `-Xss`, NMT flag, container memory limit và PID. Nếu có thể, bật GC logging/NMT ngay từ startup cho lần quan sát có kế hoạch.

Ví dụ chạy một **server thật** (không phải chương trình thoát ngay):

```bash
java -Xms256m -Xmx1024m -XX:NativeMemoryTracking=summary -jar app.jar
```

`app.jar` chỉ là tên minh họa của ứng dụng đã build phù hợp. Đừng thêm `-jar` vào lệnh của những ví dụ Java file `.class` nếu bạn không có JAR.

### Bước 2: quan sát cùng lúc theo cùng PID

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> VM.native_memory summary scale=MB
ps -o pid,rss,vsz,comm -p <PID>
```

Nếu chạy trong cgroup v2, ghi thêm `memory.current` và `memory.max` ở **cgroup thực chứa process**. Đọc kỹ units: bytes, KiB, MiB và số được làm tròn dễ tạo các chênh lệch tưởng là lỗi.

### Bước 3: đặt baseline để xem delta

```bash
jcmd <PID> VM.native_memory baseline
# Chạy một workload đủ đại diện, có tải ổn định và peak.
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Đồng thời ghi **heap used sau GC** hoặc xu hướng heap pools, RSS/PSS, số threads và cgroup memory. NMT delta cho biết category nào tăng từ baseline; nó không tự cho biết object nào còn reachable.

### Bước 4: phân loại biểu hiện

| Biểu hiện | Giả thuyết ưu tiên kiểm tra |
| --- | --- |
| Heap used sau GC tăng đều, gần heap max | Java heap retention, cache không giới hạn, object leak |
| Heap committed lớn, heap used thấp | Heap chưa shrink hoặc JVM giữ committed headroom; không tự chứng minh leak |
| NMT Thread reserved/committed tăng và thread count tăng | Nhiều threads, stacks/native thread resources |
| NMT Class/Metaspace tăng kèm số class loaders tăng | Dynamic class loading, class loader retention |
| NMT Code tăng rồi ổn định | JIT code cache warming; tăng không đồng nghĩa leak |
| RSS tăng, heap used ổn định, NMT native tăng | Điều tra native categories, direct buffers, agents |
| RSS tăng nhưng NMT ít thay đổi | Đối chiếu mmap, third-party native, allocator fragmentation, OS pages |
| Container memory.current tăng nhanh nhưng process RSS không tương ứng | Cgroup có processes/cache/kernel accounting khác; kiểm tra memory.stat |
| OOMKilled mà heap dùng chưa cao | Container/native budget pressure, không chỉ Java heap |

### Bước 5: xác nhận bằng đúng công cụ

- Nghi **Java objects leak**: allocation profiler, heap dump, dominator/retained-size analysis và GC logs.
- Nghi **native memory leak**: NMT trend kết hợp native profiler/OS mappings, đặc biệt thư viện C/JNI không được NMT bao phủ.
- Nghi **nhiều threads**: thread dump, thread count theo thời gian, stack reservation, thread pool configuration.
- Nghi **container limit**: cgroup events, kubelet/orchestrator events, memory pressure và total budget.
- Nghi **GC/commit hành vi**: GC logs, heap occupancy trước/sau collection, shrink/uncommit behavior của GC thực tế.

Không chủ động gọi `System.gc()` trong production chỉ để “làm đẹp metric”. Kết quả GC không bảo đảm hoàn tất hoặc làm giảm footprint ngay; việc ép GC có thể ảnh hưởng latency.

## 15. Dùng số đo để tránh suy luận sai

### Tình huống A: heap committed cao nhưng used thấp

Ví dụ (giả định) heap used 250 MiB, committed 1.000 MiB, max 2.000 MiB. Có thể JVM giữ heap đã committed để tránh mở rộng lại, hoặc collector chưa/không thu nhỏ sau GC. **Không đủ dữ liệu để kết luận leak**. Hãy xem heap occupancy qua GC, memory pressure và collector flags.

### Tình huống B: NMT reserved cao nhưng RSS thấp

Ví dụ NMT heap reserved 4 GiB, heap committed 512 MiB, RSS 900 MiB. Không có gì mâu thuẫn: phần reserved là **address space**, không phải 4 GiB physical RAM. Kiểm tra giới hạn virtual address space (nhất là môi trường 32-bit cũ) chỉ khi phù hợp, không nâng RAM dựa duy nhất vào reserved.

### Tình huống C: RSS tăng trong khi heap dùng gần như không đổi

Các thủ phạm khả dĩ: direct buffers, JNI/native library allocations, thêm threads, JIT code cache, metaspace, file-backed memory touched hoặc native allocator fragmentation. Dùng NMT + OS + profiler; **không tự kết luận “memory leak ở Java heap”**.

### Tình huống D: process RSS lớn hơn `-Xmx`

Hoàn toàn có thể: `-Xmx` chỉ giới hạn heap. Process có memory khác và RSS là resident metric của tổng process. Sửa bằng việc hiểu native budget; tăng `-Xmx` mù quáng có thể làm container OOM **dễ hơn**.

### Tình huống E: một container có memory.current cao hơn Java process RSS

Cgroup có thể tính thêm page cache, kernel memory hoặc processes khác. Xem `memory.stat` và process list; đừng ép hai chỉ số phải bằng nhau từng byte.

### Tình huống F: VSZ cao bất thường nhưng RSS/PSS ổn định

Có thể có nhiều reserved address ranges, thread stacks, mmap. Theo dõi xu hướng và failures thực tế. Trên nền tảng 64-bit, không gian địa chỉ ảo rất lớn; một con số VSZ cao không tự nói memory physical sắp hết.

## 16. Sai lầm phổ biến và cách sửa tư duy

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Heap used = RSS của Java process” | Heap used chỉ là một vùng; RSS gồm nhiều mapped/resident pages |
| “Heap committed = RAM đã chiếm” | Committed là số liệu vùng JVM; physical residency đo bằng RSS/PSS theo OS |
| “Heap reserved = RAM đã tiêu thụ” | Reserved thường là địa chỉ ảo; chưa chắc backed bằng physical pages |
| “`-Xmx` = giới hạn mọi memory của process” | `-Xmx` giới hạn heap, không phải native/direct/stacks/metaspace |
| “`-Xms` = heap objects đang dùng ban đầu” | `-Xms` liên quan initial heap, không tạo từng ấy objects |
| “`Runtime.freeMemory()` là RAM trống của máy” | Là vùng heap free trong mức total hiện tại |
| “NMT committed bằng RSS” | NMT tracking và OS residency khác phạm vi/ngữ nghĩa |
| “NMT thấy hết memory của JNI/C libraries” | NMT không bảo đảm theo dõi toàn bộ allocations bên ngoài cơ chế của JVM |
| “RSS của nhiều processes cộng lại bằng RAM physical đã dùng” | Shared pages có thể bị đếm trùng; PSS cung cấp một góc nhìn khác |
| “VSZ cao chứng minh leak” | Có thể chỉ là virtual address reservation |
| “Heap used thấp nên chắc chắn không thể OOM” | Native/container/thread/metaspace allocations vẫn có thể OOM |
| “Heap used đang tăng là chắc chắn leak” | Cần so sau GC và đối chiếu objects/retention |
| “Mọi `MemoryPoolMXBean.getMax()` đều là số dương hữu hạn” | Max có thể là `-1` (undefined) |
| “Các công cụ đo khác nhau phải khớp từng byte” | Scope, thời điểm snapshot và đơn vị khác nhau |
| “Nâng `-Xmx` sửa được container OOM” | Có thể làm native budget thiếu hơn; phải phân tích tổng footprint |
| “Một mẫu số đo chứng minh nguyên nhân root cause” | Cần trend, GC/allocation/OS evidence và tái hiện workload |

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Heap used = 300 MiB, committed = 600 MiB, max = 2 GiB. Có nghĩa process đang dùng đúng 300 MiB RAM?

**Không.** 300 MiB là heap used theo metric, không tính mọi resident native/file-backed pages.

**Câu 2:** Heap reserved = 8 GiB nhưng máy chỉ có 4 GiB RAM vật lý; dữ liệu này chắc chắn sai?

**Không.** Reserved có thể là khoảng địa chỉ ảo, không đòi 8 GiB physical RAM ngay.

**Câu 3:** Java process RSS = 1,5 GiB, `-Xmx1g`. Có nhất thiết JVM vi phạm giới hạn?

**Không.** `-Xmx` chỉ đặt giới hạn Java heap; non-heap/native vẫn tiêu thụ process memory.

**Câu 4:** `getCommitted() - getUsed()` trong cùng một `MemoryUsage` nói gì?

**Phần dung lượng đã committed nhưng chưa được metric ghi nhận used**. Nó không phải RAM OS còn trống.

**Câu 5:** Một memory pool có `getMax() == -1`. Có phải vùng ấy đã dùng hết memory?

**Không.** `-1` biểu thị maximum **không xác định** theo API.

**Câu 6:** NMT summary không tăng, nhưng RSS tăng. Có thể khẳng định không có native leak?

**Không.** NMT không bao phủ mọi thư viện/mapping; còn cần native profiler/OS evidence.

**Câu 7:** Trong container, heap used chưa cao nhưng kernel OOM kill process. Nguyên nhân có thể là gì?

**Tổng cgroup memory** gồm heap, native memory, stacks, file cache/kernel allocations và những processes khác vượt limit. Phải kiểm tra cgroup events/metrics.

**Câu 8:** Nên lấy một thời điểm đo heap used trước GC để kết luận object leak?

**Không.** Ưu tiên xu hướng occupancy sau GC và retained object analysis, cùng workload tương ứng.

**Câu 9:** RSS của hai processes cùng dùng một shared library page có thể tính trùng không?

**Có.** RSS tính resident pages theo process; PSS là một cách phân bổ shared pages theo tỷ lệ trên Linux.

**Câu 10:** Dùng lệnh `jcmd <PID> VM.native_memory` mà công cụ báo NMT disabled. Có sửa bằng cách thêm `summary` vào lệnh không?

**Không.** NMT phải được cấu hình từ JVM startup phù hợp; chạy `jcmd` không tự bật theo dõi retroactively.

## Tài liệu đối chiếu và hướng tìm hiểu thêm

- [Java SE 17 `MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): định nghĩa `init`, `used`, `committed`, `max` và tính hợp lệ của snapshot.
- [Java SE 17 `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap vs non-heap memory usage.
- [Java SE 17 `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): per-pool usage và thresholds.
- [Java SE 17 `Runtime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `totalMemory`, `freeMemory`, `maxMemory`.
- [JVMS Java SE 17, Chương 2 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): heap, method area, JVM stack, native stacks.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct và heap buffers.
- [Java SE 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info` và `VM.native_memory`.
- [Java SE 17 `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory utilization statistics.
- [Oracle Java Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): cơ chế theo dõi và các giới hạn của NMT.
- [Linux proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): `VmSize`, `VmRSS`, `RssAnon`, `RssFile`, `VmHWM`.
- [Linux proc_pid_smaps(5)](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): RSS/PSS và private/shared mappings.
- [Linux cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory): `memory.current`, `memory.max`, `memory.stat`, `memory.events`.

**Ghi nhớ:** **Used** là lượng JVM ghi nhận đã dùng trong **một vùng**; **committed** là lượng vùng ấy đã cam kết có thể sử dụng; **reserved** thường nói về **địa chỉ ảo dành trước**, không phải RAM resident. **RSS/VSZ/PSS** là góc nhìn **tiến trình/hệ điều hành**, còn **cgroup memory** là góc nhìn **nhóm tài nguyên**. Chỉ so sánh chúng khi đã thống nhất **scope, đơn vị, thời điểm, JVM/OS implementation**; không dùng `-Xmx` hay một số đo heap làm đại diện cho toàn bộ process memory.
