# 11.1. Phân biệt heap, non-heap, bộ nhớ tiến trình và giới hạn `-Xmx`

Một ứng dụng Java có thể chạy với `-Xmx512m` nhưng hệ điều hành vẫn ghi nhận tiến trình dùng 800 MiB, 1 GiB hoặc nhiều hơn. Điều đó **không tự động là rò rỉ bộ nhớ**: `-Xmx` chỉ giới hạn một vùng bộ nhớ cụ thể trong JVM, còn tiến trình Java có nhiều vùng khác. Khi điều tra sự cố, trước hết phải xác định **đang đo vùng nào, bằng công cụ nào và theo đại lượng nào**.

Sau bài này, bạn cần phân biệt được Java heap, non-heap theo API quản trị JVM, bộ nhớ native/off-heap, bộ nhớ của toàn tiến trình; hiểu `used`, `committed`, `reserved`, `max`, RSS; và chọn phép đo đúng khi JVM báo `OutOfMemoryError` hoặc tiến trình bị hệ điều hành/container kết thúc.

## 1. Bốn khái niệm thường bị đánh đồng

| Khái niệm | Chứa gì / thể hiện điều gì? | `-Xmx` giới hạn trực tiếp? |
| --- | --- | --- |
| **Java heap** | Vùng cấp phát chủ yếu cho instance và array Java; GC quản lý vòng đời đối tượng | **Có**: đặt mức heap tối đa theo cấu hình JVM |
| **Non-heap theo `MemoryMXBean`** | Các memory pool do JVM báo cáo ngoài heap, chẳng hạn Metaspace và Code Cache trên HotSpot | **Không** |
| **Native/off-heap** | Stack của thread, cấu trúc nội bộ JVM, bộ nhớ cấp phát qua native/JNI, vùng backing của direct buffer, một số vùng mapping… | **Không**; mỗi phần có cơ chế/giới hạn riêng |
| **Bộ nhớ của tiến trình tại OS/container** | Hình ảnh mà hệ điều hành quan sát: các trang resident (RSS), không gian địa chỉ ảo, bộ nhớ tính vào cgroup… | **Không** |

Hai điểm về thuật ngữ:

1. Trong ngôn ngữ thông thường, “non-heap” đôi khi được dùng để chỉ *tất cả bộ nhớ không nằm trên heap*. Nhưng giá trị `MemoryMXBean.getNonHeapMemoryUsage()` **không phải phép cộng của mọi cấp phát native trong tiến trình**. Trong HotSpot, thread stack, direct buffer và nhiều cấu trúc native không nằm trong tổng non-heap của MXBean này.
2. Native/off-heap và “non-heap theo MXBean” có phần giao về ý nghĩa ngoài heap, nhưng **không phải hai nhóm độc lập có thể cộng thẳng**. Hãy luôn ghi rõ metric và nguồn đo.

Sơ đồ khái niệm (không biểu diễn tỷ lệ thật):

```text
Tiến trình java (PID)
├── Java heap                            ← có giới hạn -Xmx
│   └── Đối tượng và mảng do JVM/GC quản lý
├── JVM non-heap memory pools             ← MemoryMXBean / MemoryPoolMXBean
│   ├── Metaspace, Compressed Class Space (tùy JVM)
│   └── Code Cache (mã máy JIT, tùy JVM)
├── Những vùng native khác
│   ├── Thread stacks, cấu trúc GC/JIT/JVM
│   ├── Direct buffers, native libraries, JNI
│   └── Memory mappings và các cấp phát khác
└── Các trang/code/library được OS ánh xạ, chia sẻ hoặc tính vào tiến trình
    ↑ OS báo RSS/VSZ; container còn có cách tính memory riêng
```

## 2. Heap: vùng cấp phát đối tượng, chịu quản lý của GC

Trong mô hình JVM, heap là vùng lưu trữ runtime cho các đối tượng và mảng. Ví dụ, khi chạy `new byte[1024]`, phần dữ liệu mảng thông thường được cấp phát trên heap; một biến tham chiếu cục bộ có thể nằm trong stack frame hoặc được JIT tối ưu, nhưng **không vì thế mà đối tượng được coi là nằm trên stack**. Trình biên dịch JIT có thể loại bỏ một số cấp phát nhờ escape analysis; vì vậy không nên suy luận một-một từ mỗi câu lệnh `new` thành số byte vật lý đã dùng.

Heap có thể gồm nhiều thế hệ/vùng tùy bộ thu gom rác. GC thu hồi các đối tượng không còn cần thiết theo quy tắc reachability. Con số **heap used** có thể bao gồm cả đối tượng đã trở thành garbage nhưng chưa được GC thu gom. Vì vậy một snapshot `used` cao không đủ để kết luận memory leak: cần xem biến động qua thời gian, sau các đợt GC và mối liên hệ với tải.

Các tham số thường gặp:

- `-Xms256m`: cấu hình kích thước heap ban đầu (trên HotSpot cũng là mức heap tối thiểu được cấu hình).
- `-Xmx1g`: cấu hình kích thước heap tối đa khoảng 1 GiB. Đây **không phải** trần bộ nhớ của tiến trình.
- `-XX:MaxRAMPercentage=...`: trên các phiên bản HotSpot hỗ trợ, cho JVM tính kích thước heap tối đa theo phần trăm bộ nhớ mà nó nhận diện; `-Xmx` chỉ định tường minh sẽ quyết định mức heap tối đa thay cho cách tính mặc định này.

Ví dụ cấu hình `-Xms256m -Xmx1g`: JVM có thể dự trữ không gian địa chỉ cho heap gần 1 GiB, chỉ cam kết một phần lúc đầu và dùng ít hơn phần đã cam kết. Hành vi cụ thể tùy GC, phiên bản JDK và nền tảng. **Heap max ≠ heap committed ≠ heap used ≠ RSS.**

Một số lỗi thường liên quan heap là `java.lang.OutOfMemoryError: Java heap space` hoặc GC phải làm việc quá mức vì live set sát cận trên. Tăng `-Xmx` có thể giảm áp lực dung lượng nếu máy còn đủ bộ nhớ, nhưng không sửa được việc ứng dụng giữ tham chiếu ngoài ý muốn.

## 3. Non-heap theo API quản trị JVM là gì?

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` báo cáo tổng hợp những non-heap memory pool mà JVM phơi bày qua API management. Trên HotSpot, bạn thường gặp:

| Vùng | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **Metaspace** | Metadata của class, method và cấu trúc liên quan được nạp | Sử dụng native memory; `-XX:MaxMetaspaceSize` có thể giới hạn một phần này |
| **Compressed Class Space** | Vùng phục vụ class pointer nén khi tính năng tương ứng bật | Dung lượng **reserved** có thể lớn hơn rất nhiều dung lượng **committed** |
| **Code Cache** | Mã máy được JIT biên dịch và một số đoạn mã JVM tạo | Có cấu hình riêng như `-XX:ReservedCodeCacheSize` |

Tên pool, số pool và cách chia pool là chi tiết của JVM/GC/JDK đang chạy; không nên hard-code một danh sách rồi coi là chuẩn cho mọi runtime.

Phân biệt thêm các thành phần **không được bao quát đầy đủ bởi tổng non-heap của MXBean**:

- **Thread stack**: mỗi thread nền tảng cần vùng stack riêng; `-Xss` liên quan đến kích thước stack từng thread, **không** giới hạn tổng bộ nhớ mọi thread. Virtual thread có mô hình stack khác; đừng lấy số lượng virtual thread nhân thẳng với `-Xss`.
- **Direct `ByteBuffer`**: dữ liệu backing thường được cấp phát ngoài heap, dù bản thân object `ByteBuffer` là object Java. HotSpot có tùy chọn `-XX:MaxDirectMemorySize`; chi phí native khác vẫn có thể phát sinh.
- **Cấu trúc GC/JIT/JVM và thư viện native/JNI**: có các vùng riêng, một số được Native Memory Tracking nhận diện, một số không.

Do đó, **heap used + non-heap used từ MXBean không phải total process memory**, và cũng không suy ra chính xác native memory chỉ bằng phép trừ `RSS - heap used`.

## 4. Những con số đo bộ nhớ có nghĩa khác nhau

| Metric | Ý nghĩa | Dễ hiểu sai ở đâu? |
| --- | --- | --- |
| `used` | Phần JVM báo đang sử dụng trong vùng/pool được đo | Không đồng nghĩa lượng đối tượng còn sống sau GC; không là RSS |
| `committed` | Dung lượng đã cam kết cho vùng bộ nhớ; với `MemoryUsage`, JVM bảo đảm có thể sử dụng phần này | Không đồng nghĩa từng byte đều đang nằm trong RAM vật lý |
| `max` | Mức tối đa theo pool/heap khi có thể xác định; `-1` nghĩa là không xác định | Không phải mọi pool có max; max của non-heap không bằng `-Xmx` |
| `reserved` | Không gian địa chỉ ảo được dành sẵn, thường thấy trong Native Memory Tracking (NMT) | Reserved lớn không có nghĩa đã chiếm từng ấy RAM |
| **RSS** (Resident Set Size) | Các trang của tiến trình đang resident trong RAM theo phép đo của OS | Có thể bao gồm trang được chia sẻ và khác số `committed` của JVM |
| **VSZ/VIRT** | Không gian địa chỉ ảo của tiến trình | Lớn không tự chứng minh thiếu RAM |
| **Container/cgroup memory** | Bộ nhớ được kernel hạch toán cho nhóm tiến trình/container | Có thể bao gồm file cache và nhiều tiến trình; không phải RSS của riêng JVM |

Trong `java.lang.management.MemoryUsage`, khi các số được xác định, ta thường có `used <= committed <= max`. Trường `init` biểu diễn dung lượng khởi tạo được yêu cầu. Với NMT, cặp `reserved/committed` ở từng category là **các đại lượng về quản lý bộ nhớ JVM**, không phải ảnh chụp RSS của OS. Cũng không nên cộng tùy tiện các category lồng nhau hoặc các metric đến từ nguồn khác nhau.

Ví dụ minh họa **giả định**, không phải số đo từ một chương trình thực tế:

| Vùng | Giá trị minh họa |
| --- | ---: |
| Heap max theo `-Xmx` | 1.024 MiB |
| Heap committed | 512 MiB |
| Heap used | 350 MiB |
| Non-heap MXBean used | 90 MiB |
| RSS do OS báo | 760 MiB |

Những giá trị này không mâu thuẫn nhau. Không thể lấy `760 - 350 - 90 = 320 MiB` rồi khẳng định đúng 320 MiB là “direct buffer” hay “leak”: còn committed nhưng chưa used, stack, GC, native, mapping, trang chia sẻ và khác biệt giữa các công cụ đo.

## 5. Chương trình Java 17+ tự đo heap và non-heap

Lưu đoạn mã sau vào tệp **`MemoryLayersDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public class MemoryLayersDemo {
    public static void main(String[] args) {
        MemoryMXBean bean = ManagementFactory.getMemoryMXBean();

        printUsage("Heap", bean.getHeapMemoryUsage());
        printUsage("Non-heap (MXBean)", bean.getNonHeapMemoryUsage());

        System.out.println("Runtime max heap: "
                + asMiB(Runtime.getRuntime().maxMemory()));

        System.out.println("Các non-heap memory pool:");
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                System.out.printf(Locale.ROOT, "  %s: used=%s%n",
                        pool.getName(), asMiB(usage.getUsed()));
            }
        }
    }

    private static void printUsage(String label, MemoryUsage usage) {
        System.out.printf(Locale.ROOT,
                "%s: used=%s, committed=%s, max=%s%n",
                label,
                asMiB(usage.getUsed()),
                asMiB(usage.getCommitted()),
                asMiB(usage.getMax()));
    }

    private static String asMiB(long bytes) {
        if (bytes < 0) {
            return "không xác định";
        }
        return String.format(Locale.ROOT, "%.1f MiB",
                bytes / 1048576.0);
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac MemoryLayersDemo.java
java -Xms128m -Xmx256m MemoryLayersDemo
```

Chương trình in các dòng `Heap: used=..., committed=..., max=...`, `Non-heap (MXBean): ...`, `Runtime max heap: ...` và danh sách pool không thuộc heap. **Các số MiB và tên pool phụ thuộc JDK, GC, hệ điều hành và thời điểm đo**, nên không có stdout số cố định đáng tin để chép cho mọi máy. Với cấu hình minh họa, `Runtime.maxMemory()` thể hiện giới hạn heap hữu hiệu gần mức `-Xmx256m` (có thể lệch do cách JVM bố trí và làm tròn heap).

Điểm quan trọng của ví dụ: `Runtime.getRuntime().maxMemory()` và `MemoryMXBean.getHeapMemoryUsage()` nói về **heap**; `getNonHeapMemoryUsage()` chỉ nói về các pool non-heap được JVM công bố. Không dòng nào trực tiếp là RSS hoặc tổng memory của container.

## 6. Quan sát JVM đang chạy và đối chiếu với OS

Khi chương trình/service Java vẫn đang chạy, có thể dùng các lệnh JDK sau (thay `<PID>` bằng mã tiến trình thực tế):

```bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

- `jcmd -l`: liệt kê tiến trình Java mà công cụ có thể nhìn thấy (không bảo đảm thấy mọi tiến trình trong mọi container/namespace).
- `VM.flags`: xem cờ JVM đang có hiệu lực; kết hợp tham số khởi động để kiểm tra `-Xmx`, `-Xms`, tùy chọn GC và giá trị suy diễn. Đừng đoán cấu hình chỉ từ manifest triển khai.
- `GC.heap_info`: ảnh chụp thông tin heap, hình thức kết quả phụ thuộc collector và JDK. Kết hợp với JMX/metrics/GC logs để xem xu hướng.

Với **HotSpot Native Memory Tracking (NMT)**, cần bật ngay khi khởi động JVM, chẳng hạn:

```bash
java -Xms256m -Xmx512m -XX:NativeMemoryTracking=summary -jar my-service.jar
```

Khi service đã chạy, lấy bản tóm tắt hoặc theo dõi thay đổi:

```bash
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Thực hiện lệnh `summary.diff` sau một khoảng thời gian/tải cần quan sát. NMT hiển thị các category như `Java Heap`, `Class`, `Thread`, `Code`, `GC` cùng tổng `reserved` và `committed` do HotSpot theo dõi. Nó **không bao phủ toàn bộ** cấp phát của thư viện bên ngoài/JNI và không thay thế công cụ OS; NMT cũng có overhead nên cân nhắc khi bật trên production. Không thể khởi động lại NMT từ trạng thái off bằng `jcmd` trong một JVM đã chạy.

Trên Linux, tham khảo bộ nhớ resident và virtual của **đúng PID**:

```bash
ps -o pid,rss,vsz,comm -p <PID>
cat /proc/<PID>/status
```

`rss` và `vsz` trong `ps` thường tính theo KiB; kiểm tra tài liệu công cụ của môi trường cụ thể. Với container, đối chiếu thêm số liệu memory ở cgroup/orchestrator, `memory.current` và `memory.max` trên hệ thống cgroup v2 khi áp dụng. Trên Windows có thể xem Working Set/Commit trong công cụ giám sát tiến trình; đừng so sánh trực tiếp các số khác định nghĩa mà không thống nhất cách đo.

Khi nghi ngờ heap, GC log có thể cung cấp chuỗi thời gian về occupancy trước/sau GC, pause và nhịp thu gom (ví dụ trên HotSpot: `-Xlog:gc*`). Một số công cụ attach yêu cầu quyền cùng user, namespace và hỗ trợ từ runtime; nếu không attach được, dùng metrics/logging có sẵn.

## 7. `-Xmx` và giới hạn bộ nhớ container: hai tầng giới hạn khác nhau

Giả sử container có memory limit **1 GiB**, còn JVM cấu hình `-Xmx900m`. Dù heap chỉ đạt 850 MiB, tiến trình vẫn có thể cần thêm Metaspace, code cache, stack, direct buffers, cấu trúc GC và native libraries. Khi tổng bộ nhớ bị hạch toán vượt giới hạn container, kernel có thể giết tiến trình vì OOM. Khi đó đôi khi chỉ thấy exit code **137** hoặc sự kiện `OOMKilled`, **không nhất thiết có Java `OutOfMemoryError` hay heap dump**.

Vì vậy khi lập memory budget:

1. Lấy **giới hạn thực tế** của host/cgroup và kiểm tra JVM đang nhận diện giới hạn nào.
2. Ước lượng live heap và đặt `-Xmx` dựa trên tải thực tế, không lấy toàn bộ limit dành cho heap.
3. Dành dung lượng cho Metaspace, Code Cache, GC, số thread nền tảng/`-Xss`, direct buffers, JNI và thư viện native.
4. Chừa khoảng dự phòng cho đỉnh tải và sai số quan sát; kiểm tra lại bằng RSS/cgroup và NMT khi có thể.
5. Trong HotSpot hiện đại, các cơ chế container awareness và heap sizing theo tỷ lệ có thể ảnh hưởng default; nếu đặt `-Xmx` tường minh, hãy kiểm tra giá trị cuối cùng bằng cờ/metrics thay vì suy đoán.

Không có công thức “RSS = `-Xmx` + non-heap” áp dụng cho mọi ứng dụng. Kích thước stack, số thread, GC, mmap, page cache, direct allocation và môi trường vận hành làm mức chênh thay đổi đáng kể.

## 8. Chẩn đoán theo triệu chứng

| Triệu chứng | Giả thuyết nên kiểm tra trước | Bằng chứng cần lấy |
| --- | --- | --- |
| Heap used tăng qua nhiều chu kỳ tải, đáy sau GC ngày càng cao | Đối tượng bị giữ tham chiếu / cache tăng không giới hạn; cũng có thể do tải hoặc warmed-up state | Heap trend, GC logs, heap dump/retained references |
| `OutOfMemoryError: Java heap space` | Heap không đủ cho lượng object còn giữ hoặc có leak | `-Xmx` hữu hiệu, heap occupancy, heap dump đúng thời điểm |
| Heap used thấp nhưng RSS/cgroup memory cao | Thread stacks, direct memory, Metaspace, GC/native/JNI, mapping hoặc cách OS hạch toán | RSS/cgroup trend, NMT, thread count, direct-buffer metrics |
| `OutOfMemoryError: Metaspace` | Áp lực metadata hoặc class loader không được giải phóng | Metaspace pool/NMT `Class`, số class/class loader, cấu hình Metaspace |
| Lỗi cấp phát direct buffer | Direct memory đạt giới hạn hoặc native memory căng | BufferPoolMXBean `direct`, direct allocations, cấu hình/direct limit và OS |
| `unable to create native thread` | Thiếu tài nguyên cho thread, stack hoặc chạm giới hạn OS/cgroup | Thread count, `-Xss`, ulimit/PID limits, memory OS |
| Container `OOMKilled` nhưng JVM không báo Java OOME | Cgroup chạm memory limit trước khi JVM tự ném lỗi | Event orchestrator, cgroup memory, RSS và cấu hình heap/native |

**Quy trình thực hành:** xác minh PID/runtime/flags → ghi nhận heap used/committed/max theo thời gian → đối chiếu non-heap pool và thread/direct-buffer metrics → đọc NMT (nếu đã bật) → đối chiếu RSS/cgroup cùng timestamp → mới kết luận nguyên nhân. Snapshot đơn lẻ thường không đủ để phân biệt tăng trưởng bình thường với leak.

### Ba tình huống để tự kiểm tra hiểu biết

**Tình huống A.** `-Xmx512m`, heap used 220 MiB, RSS 700 MiB. Có vi phạm `-Xmx` không? **Không.** RSS đo cả những vùng ngoài heap. Việc cần làm là tìm thành phần chiếm bộ nhớ; không suy ra leak từ chênh lệch này.

**Tình huống B.** `-Xmx1g`, NMT `Java Heap reserved` gần 1 GiB nhưng `committed` mới 300 MiB. Đã tiêu thụ 1 GiB RAM vật lý chưa? **Chưa thể kết luận như vậy.** Reserved là vùng địa chỉ dành trước; cần so committed và bộ nhớ resident thực tế.

**Tình huống C.** Service trong container 1 GiB, `-Xmx900m`, log GC không báo `Java heap space` nhưng Pod bị `OOMKilled`. Có nên tăng `-Xmx`? **Không theo phản xạ.** Phải xem cgroup usage và tổng chi phí ngoài heap; tăng heap tối đa có thể làm rủi ro OOM của container nặng hơn.

## 9. Những nhầm lẫn cần tránh

- “`-Xmx` là tổng RAM tối đa Java được dùng” → sai; chỉ giới hạn **heap**.
- “Heap used bằng heap committed” → sai; JVM có thể cam kết dung lượng chưa dùng cho object.
- “Heap used giảm ngay khi object không còn tham chiếu” → sai; thu gom do GC quyết định.
- “Non-heap của MXBean gồm mọi native memory” → sai; còn stack, direct buffers, JNI và nhiều vùng khác.
- “NMT committed phải bằng RSS” → sai; cách theo dõi và tập hợp trang khác nhau, NMT còn có vùng không theo dõi được.
- “VSZ lớn = memory leak” → sai; địa chỉ ảo reserved/mapped có thể lớn hơn resident.
- “`OutOfMemoryError` và `OOMKilled` là một sự kiện” → sai; một lỗi do JVM báo, một sự kiện do OS/cgroup quản lý bộ nhớ.

**Ghi nhớ:** `-Xmx` là *trần Java heap*; `MemoryMXBean` đo *heap và một tập non-heap pool*; NMT quan sát *một phần quản lý native memory của HotSpot*; RSS/cgroup cho *góc nhìn hệ điều hành*. Luôn đặt số liệu cạnh **tên metric, phạm vi, thời điểm và nguồn đo**.

## Tài liệu tham khảo

- Java SE 21 API — `MemoryMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Java SE 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Java SE 21 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
