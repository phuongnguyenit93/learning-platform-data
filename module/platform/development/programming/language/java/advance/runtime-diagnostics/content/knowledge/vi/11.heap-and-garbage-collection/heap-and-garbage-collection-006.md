# 11.6 Dùng GC.heap_info, MXBeans và jstat để đối chiếu tình trạng heap

## 1. Mục tiêu và cách tiếp cận

Khi một tiến trình Java dùng nhiều bộ nhớ, một con số “heap đang dùng” riêng lẻ không trả lời được các câu hỏi: heap đã cấp phát đến đâu, có đang tăng liên tục không, GC có thu hồi được bộ nhớ không, hay chúng ta đang nhầm heap với metaspace/bộ nhớ native? Bài này hướng dẫn **đối chiếu ba góc nhìn của cùng một JVM**:

1. `jcmd <PID> GC.heap_info`: ảnh chụp tức thời về heap theo cách trình bày của HotSpot/collector đang chạy.
2. `MemoryMXBean` và `MemoryPoolMXBean`: các số đo bộ nhớ lấy ngay từ bên trong JVM hoặc qua JMX; thuận tiện để gắn mốc thời gian và theo dõi trong ứng dụng.
3. `jstat`: các mẫu thống kê liên tiếp về vùng nhớ và số lần/thời gian GC; hữu ích để giải thích biến động giữa hai ảnh chụp.

Phạm vi ví dụ là **HotSpot JDK 17 trở lên**, minh họa với G1 GC. Tên vùng nhớ, cấu trúc output và một số bộ đếm có thể khác ở collector, phiên bản JDK hoặc JVM khác. Không yêu cầu cả ba công cụ phải báo **cùng một số byte** tại các thời điểm khác nhau; mục tiêu là kiểm tra sự nhất quán về *ý nghĩa và xu hướng*.

## 2. Hiểu đúng các đại lượng trước khi so sánh

`MemoryUsage` trả về bốn giá trị tính bằng **byte**:

| Thuộc tính | Ý nghĩa | Cách đọc đúng |
| --- | --- | --- |
| `init` | Kích thước khởi tạo JVM yêu cầu, nếu xác định được | Liên hệ `-Xms`, nhưng đừng dùng làm “bộ nhớ đang chiếm”. |
| `used` | Số byte hiện chứa đối tượng/dữ liệu được tính vào vùng nhớ | Với heap, gồm cả đối tượng chưa được GC thu hồi; **không đồng nghĩa dung lượng đối tượng còn sống**. |
| `committed` | Số byte JVM đã cam kết sẵn sàng sử dụng cho vùng đó | Thường lớn hơn hoặc bằng `used`; có thể vẫn cao sau khi GC. |
| `max` | Giới hạn tối đa mà vùng nhớ có thể dùng nếu được xác định | Có thể bằng `-1` khi không xác định; không phải RSS của tiến trình. |

Đổi đơn vị: `1 KiB = 1.024 byte`, `1 MiB = 1.048.576 byte`. `jstat -gc` báo dung lượng các space theo **KB (thực tế quy đổi theo 1.024 byte)**, trong khi MXBeans báo byte; `jstat -gcutil` báo **phần trăm dung lượng của từng space**. Thời gian `YGCT`, `FGCT`, `GCT` tính theo **giây**, còn `GarbageCollectorMXBean.getCollectionTime()` tính theo **mili giây**, nếu JVM hỗ trợ.

Phân biệt ba tỷ lệ thường bị trộn lẫn:

- **Mức dùng heap đã commit**: `heap.used / heap.committed`.
- **Mức dùng trên giới hạn cấu hình**: `heap.used / heap.max`, chỉ tính khi `max > 0`.
- **Mức dùng một space** (chẳng hạn cột `O` của `jstat -gcutil`): `old.used / old.capacity`. Cột `O` **không phải phần trăm sử dụng toàn heap**.

Heap là nơi cấp phát các object/array Java thông thường. Metaspace, compressed class space, code cache và nhiều vùng khác thuộc **non-heap/native**. RAM thực tế của tiến trình (RSS/working set) còn có thread stacks, direct buffers, native allocations, mapped files... nên **không** được suy ra bằng cách lấy `heap.used` cộng `metaspace.used`.

## 3. Mỗi công cụ trả lời câu hỏi gì?

| Nguồn | Nên quan sát | Câu hỏi nó giúp trả lời | Hạn chế |
| --- | --- | --- | --- |
| `GC.heap_info` | Heap total/used, region hoặc generation layout, và một số thông tin metaspace tùy GC | “Tại thời điểm này heap được tổ chức và dùng ra sao?” | Output phụ thuộc collector/JDK; một ảnh chụp không cho biết xu hướng; thao tác chẩn đoán có chi phí. |
| `MemoryMXBean.getHeapMemoryUsage()` | `used`, `committed`, `max` của heap | “Ứng dụng thấy bao nhiêu byte heap đang dùng/cam kết/được phép tối đa?” | Số đo tức thời và có thể thay đổi khi ứng dụng chạy; `used` không đồng nghĩa live set sau GC. |
| `MemoryPoolMXBean.getUsage()` | Usage của từng pool kiểu `HEAP` hoặc `NON_HEAP` | “Vùng nào đóng góp vào mức sử dụng?” | Danh sách pool phụ thuộc collector; `getUsage()` có thể trả `null` với pool không còn hợp lệ. |
| `jstat -gc` | `EU`, `OU`, survivor usage/capacity, `YGC`, `FGC`, thời gian GC | “Các space và bộ đếm GC đang thay đổi thế nào?” | Cột/diễn giải phụ thuộc HotSpot và phiên bản; số liệu lấy mẫu, không đồng thời với MXBeans. |
| `jstat -gcutil` | `E`, `O`, `S0`, `S1` theo %, cùng bộ đếm GC | “Công suất từng vùng tăng/giảm và có GC giữa các mẫu không?” | % riêng của từng vùng, không phải % heap; không nên parse output làm giao thức lâu dài. |

**Quy tắc đối chiếu:** xác định **cùng PID, cùng JVM, cùng loại vùng nhớ, cùng đơn vị, cùng mốc thời gian** trước khi kết luận hai con số chênh lệch.

## 4. Tạo JVM để thực hành trên JDK 17+

Lưu mã sau thành đúng file `HeapDiagnosticsDemo.java`. Chương trình in PID, tạo nhiều object ngắn hạn và giữ một tập object nhỏ trong `RETAINED` để có thay đổi heap/GC đủ dễ quan sát. Các giá trị đo phụ thuộc máy và thời điểm chạy, nên không có stdout số học cố định.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

public final class HeapDiagnosticsDemo {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();

    private static String size(long bytes) {
        return bytes < 0
                ? "undefined"
                : String.format(Locale.ROOT, "%.1f MiB", bytes / 1_048_576.0);
    }

    private static void printUsage(String label, MemoryUsage usage) {
        if (usage == null) {
            System.out.println(label + ": unavailable");
            return;
        }
        System.out.printf(Locale.ROOT,
                "%s: used=%s, committed=%s, max=%s%n",
                label, size(usage.getUsed()),
                size(usage.getCommitted()), size(usage.getMax()));
    }

    private static void snapshot() {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        printUsage("Heap", memory.getHeapMemoryUsage());
        printUsage("Non-heap", memory.getNonHeapMemoryUsage());

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() == MemoryType.HEAP) {
                printUsage("  " + pool.getName(), pool.getUsage());
            }
        }
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(Locale.ROOT,
                    "GC %s: collections=%d, timeMs=%d%n",
                    gc.getName(), gc.getCollectionCount(), gc.getCollectionTime());
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID: " + ProcessHandle.current().pid());
        for (int second = 1; second <= 120; second++) {
            for (int i = 0; i < 16; i++) {
                byte[] block = new byte[128 * 1024];
                block[0] = (byte) second;
                if (i % 4 == 0) {
                    RETAINED.addLast(block);
                    if (RETAINED.size() > 32) {
                        RETAINED.removeFirst();
                    }
                }
            }
            if (second % 10 == 0) {
                System.out.println("--- t=" + second + "s ---");
                snapshot();
            }
            Thread.sleep(1_000);
        }
    }
}
```

Biên dịch và chạy trong **terminal thứ nhất** (có JDK, không chỉ JRE):

```bash
javac HeapDiagnosticsDemo.java
java -Xms64m -Xmx128m -XX:+UseG1GC HeapDiagnosticsDemo
```

Dòng đầu tiên có dạng `PID: 12345` (con số thực tế khác). Mỗi 10 giây, chương trình in dòng `--- t=10s ---`, `--- t=20s ---`, ... rồi các giá trị `Heap`, `Non-heap`, các heap pool và GC counters. `-Xms64m` đặt kích thước heap khởi tạo theo cấu hình, `-Xmx128m` đặt giới hạn heap trong thí nghiệm; chúng không cố định `used`. Vòng lặp chạy khoảng hai phút; việc tạo object có thể làm `YGC` tăng nhưng **số lần GC không được đảm bảo**.

Trong **terminal thứ hai**, tìm tiến trình:

```bash
jcmd -l
```

Dùng PID mà ứng dụng in ra; các lệnh dưới đây dùng **12345 làm PID minh họa**, phải thay bằng PID thật. Chạy cùng máy/namespace chứa JVM và bằng tài khoản được phép truy cập tiến trình. Trong container, PID nhìn từ host và bên trong container có thể khác; `jps`/`jcmd -l` không phải lúc nào cũng thấy tiến trình ở namespace khác.

## 5. Góc nhìn 1 — ảnh chụp `GC.heap_info`

```bash
jcmd 12345 GC.heap_info
```

Trong HotSpot với G1, output thường có phần heap kiểu `garbage-first heap`, các giá trị `total`, `used`, region size và có thể có phần `Metaspace`. **Đọc nhãn thực sự của phiên bản đang chạy**; đừng gán cứng các dòng/đơn vị output vào parser. Với collector khác, tên/kết cấu dòng có thể khác.

Cách đọc:

1. `total` thường giúp hình dung dung lượng heap đang được cấp cho JVM ở thời điểm chụp (liên hệ với `committed`, nhưng không mặc định byte-for-byte).
2. `used` cho biết mức sử dụng tại ảnh chụp; heap có thể thay đổi ngay sau khi lệnh chạy.
3. Nếu xuất hiện `Metaspace`, đây là thông tin **ngoài heap**; không cộng vào `heap.used`.
4. Không có cơ sở kết luận leak chỉ vì `total` gần `-Xmx` hoặc một ảnh chụp `used` cao: cần xét tải và mức sử dụng **sau các kỳ GC**.

`GC.heap_info` là lệnh chẩn đoán, tài liệu HotSpot xếp mức tác động **Medium**. Nó không phải lệnh yêu cầu Full GC. Không thay thế bằng `GC.run` để “làm số đo đẹp hơn”, vì ép GC sẽ làm thay đổi hiện tượng đang điều tra.

Nếu cần biết JVM đã nhận flag nào, có thể xem thêm `jcmd 12345 VM.command_line`; flag và lựa chọn collector giúp giải thích sự khác biệt của pool/output.

## 6. Góc nhìn 2 — `MemoryMXBean` và `MemoryPoolMXBean`

Trong ví dụ, đoạn `snapshot()` lấy hai mức:

- **Toàn heap:** `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()`. Đây là thước đo ưu tiên khi muốn so sánh tổng `used/committed/max` bằng byte.
- **Từng pool thuộc heap:** lọc `pool.getType() == MemoryType.HEAP`, sau đó `pool.getUsage()`. Tên như `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen` là ví dụ của G1; không viết mã phụ thuộc vào việc luôn tồn tại các tên này.

Theo đặc tả `MemoryMXBean`, `used` và `committed` toàn heap là tổng các giá trị của các **heap pools**, còn `init` và `max` là cấu hình/giới hạn của toàn heap và **không nhất thiết bằng tổng init/max của pool**. Đừng cộng `Non-heap` vào tổng này. Một số pool có thể trả `null`; ví dụ đã kiểm tra trường hợp đó.

Nếu cần tham khảo mức sau kỳ thu gom gần nhất, `MemoryPoolMXBean.getCollectionUsage()` (khi khác `null`) cung cấp số đo *sau lần thu gom có liên quan đến pool đó*; nó **không kích hoạt GC** và **không nhất thiết là ảnh chụp đồng thời** với `getUsage()`. Không coi nó là “live set chính xác” hay dùng khi JVM không hỗ trợ.

Danh sách `GarbageCollectorMXBean` trong ví dụ báo tổng số lần thu gom và thời gian tích lũy do collector đó cung cấp. `-1` có nghĩa bộ đếm không xác định. Tên collector và cách gom sự kiện có thể khác `YGC/FGC` trong `jstat`; dùng các bộ đếm này để hỗ trợ xu hướng, không ghép số một cách máy móc.

Vì lời gọi MXBeans diễn ra tuần tự, ngay cả các dòng `Heap` và pool cùng lần in cũng có thể lệch nhẹ do allocation/GC ở giữa. Có thể lấy mẫu qua JMX từ bên ngoài JVM, nhưng nên giữ cùng chu kỳ mẫu và xác định rõ chi phí, bảo mật của kết nối JMX.

## 7. Góc nhìn 3 — lấy mẫu bằng `jstat`

Trong lúc chương trình còn chạy, thực hiện:

```bash
jstat -gc 12345 1000 5
jstat -gcutil -t 12345 1000 5
```

`1000` là khoảng cách **1.000 ms**; `5` là số lần lấy mẫu. `-t` thêm cột `Timestamp` (số giây từ khi JVM khởi động, **không phải đồng hồ giờ-phút-giây**). Có thể dùng `jstat -gccapacity 12345 1000 5` để xem dung lượng generations/spaces, nếu collector hiển thị các đại lượng đó.

Các cột cần biết trong `-gc` trên HotSpot:

| Cột | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| `S0C`, `S1C`; `S0U`, `S1U` | Capacity và used của hai survivor spaces | KB |
| `EC`, `EU` | Eden capacity và used | KB |
| `OC`, `OU` | Old capacity và used | KB |
| `MC`, `MU` | Metaspace committed và used | KB; **ngoài heap** |
| `CCSC`, `CCSU` | Compressed class space committed và used | KB; **ngoài heap** |
| `YGC`, `YGCT` | Số lần và tổng thời gian young GC | Lần; giây |
| `FGC`, `FGCT` | Số lần và tổng thời gian full GC theo bộ đếm công cụ | Lần; giây |
| `GCT` | Tổng thời gian GC được công cụ báo | Giây |

Trong `-gcutil`, các cột `S0`, `S1`, `E`, `O`, `M`, `CCS` là **% sử dụng của từng vùng riêng**; các cột GC counters giữ ý nghĩa tích lũy. Một số phiên bản/collector có thêm hoặc không có cột; **ưu tiên header mà lệnh thực tế in ra**. `jstat` được tài liệu JDK ghi là công cụ experimental/unsupported và định dạng có thể đổi, vì vậy **không xây pipeline giám sát lâu dài phụ thuộc vào việc parse bảng text cố định**.

### Đọc sự thay đổi, không chỉ một dòng

Ví dụ minh họa về **hai mẫu giả định** (các số dưới đây không phải stdout cam kết của chương trình):

| Mốc | `E` | `O` | `YGC` | `YGCT` | `FGC` |
| --- | ---: | ---: | ---: | ---: | ---: |
| t0 | 92% | 38% | 7 | 0,120 s | 0 |
| t0 + 5 s | 14% | 41% | 9 | 0,145 s | 0 |

Trong 5 giây có `ΔYGC = 2` và `ΔYGCT = 0,025 s`; Eden giảm mạnh, Old tăng nhẹ. Đây là dấu hiệu phù hợp với allocation + young GC + một phần object được giữ/chuyển vùng. **Không** thể chỉ từ hai dòng chứng minh tất cả phần tăng ở Old đều do promotion, cũng không chứng minh có leak. `FGC = 0` không đồng nghĩa “chẳng có hoạt động GC nào”: các đợt GC khác và concurrent work có thể diễn ra tùy collector.

## 8. Quy trình đối chiếu ba nguồn theo cùng một vòng đo

### Bước 1 — chốt danh tính và cấu hình

Ghi PID, Java version, GC đang dùng, `-Xms/-Xmx` và thời điểm bắt đầu lấy mẫu. Không so output của một PID đã kết thúc với tiến trình mới tái sử dụng PID đó.

### Bước 2 — thiết lập đường cơ sở

Ghi `Heap used/committed/max` từ MXBean; chụp một `GC.heap_info`; bắt đầu `jstat -gc` và `-gcutil` trong cùng một cửa sổ thời gian, ví dụ 5–30 giây. Lưu timestamp ứng dụng cùng số liệu; nếu lệch nhiều, chụp lại gần nhau hơn.

### Bước 3 — chuẩn hóa đơn vị và ý nghĩa

Với output `jstat -gc` có đủ các cột thế hệ truyền thống, có thể tính **ước lượng**:

```text
heap_used_KiB      ≈ S0U + S1U + EU + OU
heap_capacity_KiB  ≈ S0C + S1C + EC + OC
heap_used_MiB      ≈ heap_used_KiB / 1024
heap_capacity_MiB  ≈ heap_capacity_KiB / 1024
heap_used_percent  = 100 × MXBean.heap.used / MXBean.heap.committed
```

Đây là phép đối chiếu cho layout phù hợp, **không phải định luật áp dụng cho mọi collector**: G1 có vùng linh hoạt; collector không chia Eden/Survivor/Old theo cách truyền thống; một số số đo/capacity khác cách tính. Không đưa `MC/MU/CCSC/CCSU` vào `heap_used_KiB` vì đó là non-heap.

Ví dụ **giả định để kiểm tra số học**: `EU=14336 KB`, `S0U=0 KB`, `S1U=2048 KB`, `OU=32768 KB` ⇒ tổng `49152 KB = 48 MiB`. Nếu tổng capacity tương ứng là `98304 KB = 96 MiB`, mức dùng trên committed khoảng `50%`. Một MXBean trả `heap.used≈48 MiB` và `committed≈96 MiB`, cùng `GC.heap_info` ở gần thời điểm đó, là các quan sát *phù hợp*; không đòi bằng đúng byte.

### Bước 4 — đo lại sau một hoặc nhiều chu kỳ GC tự nhiên

Xem sự thay đổi `EU`, `OU`, `YGC`, `FGC`, `YGCT`, `GCT`; đồng thời so **mức nền sau GC** và lưu lượng request/khối lượng công việc. Ví dụ, `used` tăng khi load tăng rồi giảm sau collection là khác đáng kể với `used`/Old cứ tăng qua nhiều chu kỳ dù workload ổn định.

### Bước 5 — ghi kết luận có điều kiện

Mẫu kết luận tốt: “Trên HotSpot 21/G1, PID này có heap committed xấp xỉ 96 MiB, used khoảng 48–51 MiB ở ba phép đo gần nhau; trong 10 giây YGC tăng 3, Eden giảm sau các đợt young GC, Old giữ quanh 35–38 MiB; chưa thấy bằng chứng heap leak từ cửa sổ ngắn này.” Nhớ nêu collector, khoảng lấy mẫu, tải và bất định.

## 9. Diễn giải các tình huống thường gặp

| Quan sát kết hợp | Diễn giải hợp lý | Kiểm tra tiếp |
| --- | --- | --- |
| `EU` tăng nhanh rồi giảm, `YGC` tăng, `heap.used` dao động | Allocation ngắn hạn được GC thu hồi; có thể là bình thường | Xem thời gian GC, throughput, pause/latency; không vội tăng heap. |
| `OU` và mức `used` sau GC tăng qua nhiều chu kỳ cùng tải | Có thể có object retention, cache tăng, hoặc leak | So thời gian dài hơn, tải thực tế và live-set; nếu cần dùng GC logs/heap dump với quy trình riêng. |
| `heap.used` thấp nhưng `committed` vẫn cao | JVM vẫn giữ heap đã commit hoặc chịu ảnh hưởng `-Xms`/chính sách GC | Kiểm tra `max`, `committed` và cấu hình GC; không đồng nhất committed với leak. |
| `jstat` cho `M`/`CCS` cao, heap ổn định | Áp lực class metadata/non-heap, không phải trực tiếp Java heap object | Xem non-heap MXBeans và class-loading; không cộng metaspace vào heap. |
| RSS hệ điều hành cao, heap và metaspace thấp | Có thể tốn native memory, direct buffers, stacks, mapped pages hoặc thư viện native | Dùng công cụ OS và native diagnostics phù hợp; ba nguồn trong bài không đủ xác định thủ phạm. |
| `FGC` tăng và `FGCT` tăng nhanh, cùng latency xấu | Full GC có thể gây áp lực hoặc pause đáng kể | Đối chiếu GC logs, allocation rate, old occupancy và mục tiêu latency. |
| `GC.heap_info` khác MXBean vài MiB, `jstat` biến động mạnh | Các phép đo không đồng thời; các pool/đơn vị có cách biểu diễn riêng | Chụp mẫu sát nhau hơn, đổi về MiB, xác minh đúng PID/GC, không “sửa” số để ép khớp. |

**Lưu ý về leak:** một lần `used` tăng hoặc một lần Full GC không chứng minh leak. Dấu hiệu đáng quan tâm là nền sử dụng sau nhiều chu kỳ thu gom tăng bền vững khi workload/caches đã ổn định. Muốn khẳng định object nào được giữ, cần bằng chứng từ heap dump, dominator/retained-size analysis hoặc công cụ chuyên sâu.

## 10. Những sai lầm cần tránh

1. **So `max` với `total` như cùng đại lượng:** `max` là giới hạn; `total/committed` là dung lượng đang được cam kết tại thời điểm đo.
2. **Lấy `O = 80%` thành “heap 80%”:** `O` chỉ là % old space; heap còn các vùng khác.
3. **Cộng metaspace vào heap:** `MC/MU` và `CCS` không phải số byte object trên Java heap.
4. **Quên đổi đơn vị:** `jstat -gc` theo KB, MXBeans theo byte, GC time có giây/mili giây khác nhau.
5. **So ba số đo như một snapshot nguyên tử:** tiến trình vẫn cấp phát và chạy GC giữa các lệnh.
6. **Coi `used` là live set:** trước GC, `used` có thể chứa cả object đã không còn reachable nhưng chưa được thu hồi.
7. **Mặc định mọi JVM đều có Eden/Old/G1 pool giống nhau:** pool names và output phụ thuộc collector/JVM; các phép cộng theo space chỉ là ước lượng có điều kiện.
8. **Suy luận “FGC không tăng nên GC không chạy”:** phải xem `YGC` và các chỉ báo phù hợp collector.
9. **Ép `System.gc()` hoặc `jcmd ... GC.run` trước khi đo:** làm biến dạng trạng thái tự nhiên, có thể tạo pause.
10. **Bỏ qua quyền truy cập:** `jcmd` cần cơ chế attach hoạt động và quyền phù hợp; một số JVM tắt attach. `jstat` cần performance instrumentation sẵn có; khác user/container/namespace có thể không đọc được. Môi trường runtime tối giản có thể không đóng gói `jcmd`/`jstat`.
11. **Chỉ lấy một dòng `jstat`:** không thấy được ΔGC và xu hướng.
12. **Viết parser phụ thuộc vị trí cột `jstat`:** tài liệu công cụ cảnh báo định dạng có thể thay đổi giữa các phiên bản.

## 11. Bài thực hành tự kiểm chứng

Với chương trình ở mục 4, quan sát trong ít nhất 30–60 giây ở hai terminal:

1. Ghi `PID`, Java version, `-Xms`/`-Xmx`, collector đang dùng.
2. Ghi hai lần `GC.heap_info` cách nhau khoảng 15 giây; lấy các giá trị tổng heap và phân biệt metaspace.
3. Ghi 5–10 mẫu `jstat -gc` và `jstat -gcutil`; tính `ΔYGC`, `ΔYGCT`, `ΔFGC`. Quan sát `EU`/`OU` thay đổi thế nào.
4. Chép hai mốc `Heap used/committed/max` và tên/usage các heap pools từ stdout MXBean; đổi `used` ra MiB.
5. So các mốc gần nhau; lý giải khác biệt theo thời gian, đơn vị, collector và đối tượng đang bị giữ bởi `RETAINED`.
6. Viết 3–5 câu kết luận có điều kiện: các con số **nào** đồng thuận, phần nào chênh lệch, `YGC/FGC` thay đổi ra sao, còn thiếu bằng chứng nào trước khi nói “leak”.

**Tiêu chí đạt:** xác định đúng heap và non-heap; phân biệt `used/committed/max`; tính và giải thích được ΔGC; hiểu vì sao ba nguồn gần nhau nhưng không trùng tuyệt đối; không kết luận leak từ một snapshot.

## 12. Tài liệu tra cứu chính thức

- [JDK 21 — `jcmd`, lệnh `GC.heap_info`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [JDK 21 — `jstat`, cú pháp, các cột và giới hạn công cụ](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html).
- [Java 21 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).
- [Java 21 — `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).
- [Java 21 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).
