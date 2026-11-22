# 11.2. Đọc đồ thị heap theo thời gian và lượng dữ liệu còn sống sau chu kỳ thu gom

Trong Java, đồ thị heap theo thời gian giúp phân biệt hai hiện tượng rất khác nhau: **bộ nhớ tạm thời tăng vì ứng dụng liên tục cấp phát đối tượng** và **bộ nhớ vẫn bị giữ lại sau khi bộ thu gom rác (GC) đã có cơ hội thu hồi**. Giá trị có ý nghĩa chẩn đoán không chỉ là đỉnh `heap used`, mà còn là xu hướng của các mức sử dụng **sau những lần GC có thể so sánh được**.

Bài này tập trung vào cách đọc đồ thị, tính toán từ các điểm trước/sau GC, nhận diện tín hiệu bất thường và kiểm chứng bằng quan sát JVM. Các con số và mẫu log bên dưới là ví dụ minh họa, không phải giá trị cố định của mọi JVM.

## 1. Đọc đúng các đường và trục trên đồ thị

Trục ngang thường là thời gian (giây, phút, giờ); trục dọc là dung lượng bộ nhớ (MiB/GiB hoặc byte). Trước khi kết luận, hãy xác định chính xác metric và phạm vi mà công cụ đang vẽ.

| Khái niệm | Ý nghĩa | Cách sử dụng khi đọc đồ thị |
| --- | --- | --- |
| `heap used` | Lượng bộ nhớ heap JVM báo đang được sử dụng tại thời điểm lấy mẫu. | Quan sát đỉnh, đáy và biến động giữa các lần GC. |
| `heap committed` | Lượng bộ nhớ heap JVM đã cam kết/cấp cho heap tại thời điểm đó. | Giải thích vì sao kích thước vùng heap có thể nới rộng hoặc co lại. |
| `heap max` | Mức sử dụng heap tối đa JVM báo cho heap, thường liên quan giới hạn `-Xmx`. | Đánh giá giới hạn lý thuyết; có thể không xác định trong một số API/nhóm bộ nhớ. |
| `used after GC` | Lượng heap được báo còn sử dụng ngay sau một sự kiện GC cụ thể. | Theo dõi đường đáy sau GC, nhưng cần biết loại GC đã chạy. |
| `live set` | Tập đối tượng thực sự còn có thể truy cập từ GC roots tại một thời điểm theo mô hình reachability. | Khái niệm để suy luận lượng dữ liệu còn sống; không đồng nhất máy móc với mọi mẫu `used after GC`. |
| `old generation / tenured used` | Bộ nhớ đang sử dụng ở vùng chứa đối tượng tồn tại lâu, nếu collector chia vùng phù hợp. | Hữu ích khi phân biệt churn ngắn hạn với tích lũy dài hạn. |

`used`, `committed` và `max` là ba đường khác nhau: `used ≤ committed`, và trong cấu hình thông thường `committed ≤ max`. Việc `committed` tăng không tự chứng minh rò rỉ: JVM có thể mở rộng heap để đáp ứng tải. Đồng thời, **RSS/bộ nhớ tiến trình của hệ điều hành không bằng heap used**: metaspace, code cache, stack của thread, direct buffer, thư viện native và các phần ngoài heap cũng tiêu thụ bộ nhớ.

Kiểm tra đơn vị trước khi so sánh: 1 MiB = 1.048.576 byte; 1 GiB = 1.024 MiB. Không đối chiếu phần trăm sử dụng của các pool với số MiB tuyệt đối khi chưa quy đổi. Đồ thị tự động co giãn trục Y có thể khiến một thay đổi nhỏ trông rất lớn.

## 2. Vì sao đồ thị thường có dạng răng cưa?

Trong ứng dụng tạo nhiều đối tượng ngắn hạn, bộ nhớ sử dụng thường tăng trong khoảng giữa hai sự kiện GC rồi giảm khi GC thu hồi được vùng nhớ. Nếu lặp lại, đường `heap used` trông giống răng cưa:

1. **Đoạn dốc đi lên:** ứng dụng cấp phát thêm đối tượng; một phần sớm trở thành garbage nhưng chưa được thu gom.
2. **Đỉnh trước GC:** mức `used` ngay trước sự kiện thu gom, chịu ảnh hưởng của tốc độ cấp phát, kích thước heap, chính sách collector và tải.
3. **Bước giảm sau GC:** một phần không gian được thu hồi; độ chênh trước/sau là thay đổi của số liệu `used` qua sự kiện đó.
4. **Đáy sau GC:** mức `used` còn được báo sau thu gom. Nối các đáy **cùng loại sự kiện, trong điều kiện tải tương đương** để xem xu hướng giữ bộ nhớ.

Không phải collector nào cũng tạo răng cưa rõ. GC đồng thời như ZGC hoặc Shenandoah thực hiện nhiều pha trong khi ứng dụng chạy; đồ thị được lấy mẫu thưa có thể nhìn mượt hoặc giảm theo nhiều bước. G1 có young GC, mixed GC và các pha concurrent với tác động khác nhau. Vì vậy **vị trí giảm mạnh trên đồ thị chỉ là dấu hiệu gợi ý, còn nhãn sự kiện GC và log mới xác định được chuyện gì xảy ra**.

Khoảng cách giữa hai đỉnh gần nhau có thể phản ánh tốc độ cấp phát, ngưỡng kích hoạt GC hoặc thay đổi kích thước heap. Không diễn giải tần suất GC một cách độc lập với lượng request, batch job, heap committed và thuật toán GC.

## 3. “Còn sống sau GC” phải hiểu trong phạm vi sự kiện thu gom

Một đối tượng *live* là đối tượng còn reachable qua chuỗi tham chiếu bắt đầu từ các GC roots (ví dụ biến cục bộ đang hoạt động, tham chiếu tĩnh hoặc những root do JVM quản lý). Đối tượng không còn reachable là ứng viên có thể thu hồi, nhưng **thời điểm collector thực sự thu hồi** còn phụ thuộc thuật toán và phạm vi của chu kỳ.

- **Sau young GC:** các đối tượng còn tồn tại ở vùng young được giữ/chuyển vùng theo thuật toán, nhưng nhiều đối tượng không còn cần ở old generation có thể chưa được xem xét. `total heap used after young GC` vì vậy **không đo chính xác toàn bộ live set**.
- **Sau mixed/old/full collection:** có thể phản ánh sự giữ lại dài hạn tốt hơn, nhưng phạm vi thu gom khác nhau giữa collector và từng sự kiện. Ngay cả sau full GC, số liệu còn bị ảnh hưởng bởi thời điểm đo, hoạt động ứng dụng và cách JVM ghi nhận vùng nhớ.
- **Trong GC đồng thời:** ứng dụng vẫn có thể cấp phát/đổi tham chiếu trong khi collector làm việc. Một mẫu `used` ngay sau nhãn “cycle complete” không phải ảnh chụp nguyên tử tuyệt đối của toàn bộ object graph.
- **`Retained size` trong heap dump:** dung lượng của các đối tượng sẽ có thể được giải phóng nếu một đối tượng/nhóm root tương ứng không còn giữ chúng (theo dominator analysis). Đây là phép phân tích mối quan hệ tham chiếu, **khác với** tổng `used after GC`.

Khi nói “đáy sau GC tăng”, cách phát biểu chính xác là: *lượng heap được báo còn sử dụng sau các sự kiện GC so sánh được đang tăng*. Chỉ sau khi loại trừ thay đổi workload, cache hợp lệ, chính sách thu gom và sampling mới có cơ sở nghi ngờ dữ liệu bị giữ lại ngoài dự kiến.

## 4. Quy trình đọc một đồ thị heap theo thời gian

### Bước 1 — Xác định đúng chỉ số và cấu hình

Ghi lại collector (G1, Parallel, ZGC, Shenandoah...), phiên bản JDK, `-Xms`, `-Xmx`, đơn vị, thời gian lấy mẫu và liệu đồ thị hiển thị toàn heap hay một memory pool. Kiểm tra xem mỗi điểm là giá trị tức thời, trung bình trong cửa sổ, `max` hay tổng hợp từ nhiều JVM. Chẳng hạn, đường trung bình 1 phút có thể che khuất những đỉnh rất ngắn.

### Bước 2 — Đánh dấu các sự kiện GC thật

Đồng bộ mốc thời gian đồ thị với GC log/JFR: thời điểm bắt đầu, kết thúc, loại sự kiện, giá trị trước/sau (nếu collector báo), thời gian pause và chu kỳ concurrent. Một đồ thị chỉ có `used` mà không có event GC vẫn hữu ích để quan sát xu hướng nhưng **không đủ** để gắn nhãn chính xác mọi đáy.

### Bước 3 — Đọc cả đỉnh và đáy

Với mỗi sự kiện có số liệu trước/sau, ghi:

- `before`: heap used ngay trước GC.
- `after`: heap used ngay sau GC.
- `reclaimed_observed = before - after`: số MiB giảm được quan sát qua sự kiện, không đồng nghĩa tổng lượng garbage được tạo trong khoảng thời gian trước đó.
- `after / committed` và `after / max`: hai tỷ lệ tham khảo khác nhau; cần giữ mẫu số nhất quán khi so sánh.

Ví dụ GC báo `760 MiB → 260 MiB (heap capacity 1.024 MiB)`: mức giảm quan sát là `500 MiB`; phần còn sử dụng sau GC chiếm `260 / 1.024 ≈ 25,4%` của capacity hiển thị. Nếu `-Xmx=1.536 MiB` thì mức sau GC bằng khoảng `16,9%` của giới hạn tối đa. Khoảng `1.536 - 260 = 1.276 MiB` chỉ là **headroom theo số liệu used so với max**, không phải bảo đảm mọi lần cấp phát tương lai đều thành công.

### Bước 4 — Nối các đáy tương đương để nhận diện xu hướng

Chọn các điểm sau **cùng nhóm GC**, cùng phiên bản/cấu hình và cùng pha workload. Với ba young GC, các mức `250 → 265 → 280 MiB` có thể phản ánh cache ấm dần, đối tượng chuyển sang old hoặc tải tăng; chưa thể gọi là leak. Nếu sau khi workload ổn định, một loạt **sự kiện thu gom bao phủ old generation** vẫn có đáy `300 → 450 → 610 MiB`, đây là tín hiệu cần điều tra đối tượng bị giữ lâu.

Không so trực tiếp “đáy sau young GC” với “đáy sau full GC” để suy ra tăng/giảm live set; chúng không đo cùng phạm vi. Với GC concurrent, hãy chọn chỉ số/pha sau chu kỳ thích hợp, hoặc dùng quan sát theo cửa sổ đủ dài thay vì một điểm đơn lẻ.

### Bước 5 — Đọc độ dốc và nhịp GC trong bối cảnh tải

Giữa hai sự kiện GC rõ ràng, `Δused / Δt` là **tốc độ tăng mức heap used quan sát được**, không phải tốc độ cấp phát tổng: trong cùng khoảng thời gian có thể tồn tại garbage chưa thu hồi, object được giữ lại hoặc GC nền đang hoạt động. Để đo allocation rate thực sự, ưu tiên JFR/profiler/metric allocation phù hợp.

Khi đáy ổn định nhưng đỉnh tăng nhanh và GC xảy ra thường xuyên, ứng dụng có thể đang tạo nhiều đối tượng ngắn hạn. Khi cả đáy lẫn old usage tăng nhiều chu kỳ, cần điều tra khả năng giữ tham chiếu lâu hoặc quy mô dữ liệu hợp lệ đang lớn dần. Nhịp GC nhanh hơn thường làm tăng chi phí CPU/pause, nhưng không đủ bằng chứng rằng có leak.

### Bước 6 — Đối chiếu hiệu năng và sự kiện ứng dụng

Đặt lên cùng trục thời gian: request/s, batch job, số người dùng, hàng đợi, kích thước cache, latency p95/p99, GC pause, CPU và lỗi `OutOfMemoryError` (nếu có). Một spike trùng lúc tải tăng hoặc import hàng triệu bản ghi có ý nghĩa khác với đáy heap tăng suốt nhiều giờ trong điều kiện tải phẳng.

## 5. Bài đọc số liệu mẫu

Giả sử một ứng dụng G1 có `-Xmx1536m`, dung lượng heap committed tại các thời điểm dưới đây khoảng 1.024 MiB. GC log cung cấp các cặp trước/sau; bảng được đơn giản hóa để học cách suy luận:

| Thời điểm | Sự kiện | Heap trước GC | Heap sau GC | Mức giảm quan sát | Nhận xét |
| --- | --- | ---: | ---: | ---: | --- |
| 09:00 | Young GC #41 | 710 MiB | 250 MiB | 460 MiB | Nhiều dữ liệu ngắn hạn được dọn. |
| 09:05 | Young GC #42 | 760 MiB | 265 MiB | 495 MiB | Đáy tăng 15 MiB, chưa đủ kết luận. |
| 09:10 | Young GC #43 | 790 MiB | 280 MiB | 510 MiB | Cần đối chiếu old usage và tải. |
| 09:20 | Mixed GC #55 | 820 MiB | 230 MiB | 590 MiB | Phạm vi GC đã khác; không ghép vào chuỗi young GC như cùng một loại mẫu. |

Ở 09:05, phép trừ `760 - 265 = 495 MiB` cho thấy bao nhiêu heap used đã giảm trong sự kiện, **không** cho biết có chính xác 495 MiB đối tượng chết trong 5 phút trước đó. Ba đáy young GC `250, 265, 280 MiB` tăng 30 MiB trong 10 phút; chuỗi quá ngắn và chưa có kiểm soát workload để kết luận. Sau mixed GC, `230 MiB` thấp hơn mọi đáy young GC trước đó: điều này gợi ý đã thu hồi thêm vùng nhớ khác, nhưng cũng không có nghĩa rằng trước đó đã xảy ra leak.

So sánh hai tình huống giả định trong một giai đoạn dài hơn với tải và cấu hình ổn định:

| Dữ liệu sau những sự kiện GC tương đương | Diễn giải hợp lý | Việc kiểm chứng |
| --- | --- | --- |
| `280, 286, 279, 283 MiB` | Đáy dao động quanh một nền tương đối ổn định. | Kiểm tra GC pause, throughput; có thể là trạng thái bình thường. |
| `280, 360, 440, 530 MiB` | Nền còn sử dụng đang tăng liên tục. | So khớp workload/cache/old usage, rồi kiểm tra class và đường giữ tham chiếu nếu xu hướng kéo dài. |
| `280, 360, 440, 300 MiB` | Tăng rồi giảm; có thể là cache được dọn, workload kết thúc hoặc một chu kỳ GC khác đã thu hồi thêm. | Tìm đúng sự kiện/tác vụ tại điểm đảo chiều; tránh kết luận từ một đoạn. |

## 6. Các hình dạng điển hình và cách đặt giả thuyết

| Hình dạng quan sát | Giả thuyết cần xem xét | Dấu hiệu để phân biệt |
| --- | --- | --- |
| Răng cưa lặp, đáy quanh một mức | Cấp phát thường xuyên, GC thu hồi đều. | Đáy ổn định trên nhiều chu kỳ; latency/CPU chấp nhận được. |
| Đỉnh cao hơn nhưng đáy không tăng tương ứng | Tải hoặc tốc độ tạo đối tượng ngắn hạn tăng; heap committed có thể mở rộng. | So request/s, allocation rate, `committed` và GC pause. |
| Đáy sau những lần GC tương đương tăng dần | Dữ liệu sống lớn dần: cache, queue, session, batch chưa xong hoặc giữ tham chiếu ngoài ý muốn. | Theo dõi old usage và tập đối tượng retained trong heap dump/JFR. |
| Mật độ GC dày, heap gần giới hạn, sau GC vẫn cao | Áp lực bộ nhớ; nguy cơ GC overhead cao, pause tăng hoặc OOM nếu không còn chỗ cấp phát. | Xem `-Xmx`, GC cause, allocation pressure, pause và các lỗi cấp phát. |
| Heap used gần như đi ngang nhưng RSS tăng | Bộ nhớ ngoài heap hoặc native; cũng có thể là heap committed cao nhưng used thấp. | So RSS với direct buffer, thread stack, metaspace, code cache, native memory tracking khi được bật. |
| Đường giảm mạnh sau khi batch/traffic kết thúc | Đối tượng tạm thời đã được thu gom hoặc cache được giải phóng. | Đối chiếu thời điểm giảm với GC log, batch completion và chỉ số old usage. |
| Không thấy bước giảm trong khoảng quan sát ngắn | Có thể chưa xảy ra GC, collector chạy đồng thời hoặc sampling bỏ lỡ sự kiện. | Kiểm tra event log và kéo dài cửa sổ/giảm interval lấy mẫu. |

Một cache có giới hạn dung lượng thường tăng trong giai đoạn warm-up rồi ổn định; một cache không giới hạn có thể giữ dữ liệu mãi. Cả hai có thể tạo đường đáy tăng ban đầu. **Đồ thị là bằng chứng về triệu chứng bộ nhớ, không phải phép chứng minh nguồn gốc tham chiếu.**

## 7. Thu thập dữ liệu từ JVM để xác nhận cách đọc

### 7.1. Unified GC logging (Java 17+)

Khi khởi chạy ứng dụng, bật GC logging ở mức phù hợp với môi trường:

```bash
java -Xms256m -Xmx1536m \
  -Xlog:gc*,gc+heap=debug:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

Ví dụ một dòng GC log minh họa (cách diễn đạt thay đổi theo JDK/collector/cấu hình tag):

```text
[12.345s][info][gc] GC(41) Pause Young (Normal) (G1 Evacuation Pause) 760M->260M(1024M) 12.3ms
```

Ở ví dụ này: `760M` là heap trước sự kiện; `260M` là heap sau sự kiện; `1024M` là heap capacity được báo trong dòng log; `12.3ms` là thời lượng pause được báo. **Đừng đọc `1024M` trong ngoặc là giá trị `-Xmx`**; chúng có thể khác nhau. Khi phân tích một collector khác, hãy dựa trên cấu trúc log thực tế thay vì giả định mọi dòng đều có mẫu tương tự.

Không tăng mức log quá rộng và quá lâu trên production nếu chưa đánh giá chi phí lưu trữ/I/O; đảm bảo log được xoay vòng và đồng bộ múi giờ/timestamp với monitoring.

### 7.2. Lệnh quan sát không cần sửa mã

```bash
# Thông tin heap theo collector hiện tại, tại một thời điểm
jcmd <pid> GC.heap_info

# Mẫu mức sử dụng các pool và bộ đếm GC mỗi 1.000 ms, 10 mẫu
jstat -gcutil <pid> 1000 10

# Ghi một JFR ngắn để phân tích sự kiện GC, pause và workload
jcmd <pid> JFR.start name=heaptrend settings=profile duration=120s filename=heaptrend.jfr
```

`jstat -gcutil` chủ yếu hiển thị **phần trăm sử dụng của các pool** và các bộ đếm/thời gian GC; không thể coi cột `O` là số MiB live set của toàn heap. `jcmd GC.heap_info` là snapshot chứ không cung cấp một đường thời gian đầy đủ. Với JFR, mở file bằng Java Mission Control (JMC), xem timeline GC, allocation, pause và số liệu được JDK/collector thực sự ghi; các loại event sẵn có không giống nhau ở mọi cấu hình.

Có thể dùng VisualVM, JConsole hoặc dashboard Micrometer/Prometheus để xem chuỗi thời gian `heap used`/`committed`/`max`. Với metric ứng dụng, kiểm tra nhãn `area=heap`, pool, instance, đơn vị và cách công cụ gộp series. Một “live data size” metric phụ thuộc collector và thời điểm cập nhật; không suy đoán nó được làm mới sau mọi young GC.

### 7.3. Tự lấy mẫu heap bằng Java 17+

Ví dụ độc lập sau in trạng thái heap và tổng bộ đếm collection mỗi giây. Nó hữu ích để hiểu **giá trị được lấy mẫu**, nhưng bản thân nó không nhận diện chính xác mọi điểm “ngay sau GC”.

Tạo tệp `HeapTrend.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.time.Instant;

public class HeapTrend {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 10; i++) {
            MemoryUsage heap =
                    ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
            long collections = 0L;

            for (GarbageCollectorMXBean gc :
                    ManagementFactory.getGarbageCollectorMXBeans()) {
                long count = gc.getCollectionCount();
                if (count >= 0) {
                    collections += count;
                }
            }

            String max = heap.getMax() >= 0
                    ? (heap.getMax() / MIB) + "MiB"
                    : "unknown";

            System.out.printf(
                    "%s used=%dMiB committed=%dMiB max=%s gcCount=%d%n",
                    Instant.now(), heap.getUsed() / MIB,
                    heap.getCommitted() / MIB, max, collections);

            if (i < 9) {
                Thread.sleep(1000);
            }
        }
    }
}
```

Biên dịch và chạy (cần JDK 17 trở lên):

```bash
javac HeapTrend.java
java -Xms128m -Xmx512m HeapTrend
```

Chương trình in **10 dòng**, mỗi dòng theo định dạng `<timestamp> used=<n>MiB committed=<n>MiB max=512MiB gcCount=<n>` trong cấu hình ví dụ (giá trị `used`, `committed`, thời gian và số lần GC tùy máy/lần chạy). Không đưa ra stdout số học cố định vì việc cấp phát, khởi tạo JVM và lịch GC không xác định. `gcCount` là tổng số collection mà các MXBean hỗ trợ báo cáo, không phải ID của sự kiện GC và cũng không đảm bảo tăng đúng một lần cho mỗi thay đổi heap. Muốn ghép chính xác before/after với sự kiện, dùng GC log/JFR thay cho suy luận từ hai mẫu cách nhau 1 giây.

## 8. Khi nào nghi ngờ giữ bộ nhớ ngoài dự kiến?

Một quy trình điều tra có cơ sở là:

1. **Dựng đường nền đủ dài:** lấy chuỗi sau những GC so sánh được trên nhiều chu kỳ, không chỉ 2–3 điểm; ghi lại tải và thay đổi cấu hình.
2. **Tách growth hợp lệ:** loại trừ cache warm-up, session tăng, hàng đợi chưa xử lý, bulk import, lưu dữ liệu trong phạm vi batch và các thay đổi nghiệp vụ có chủ đích.
3. **Kiểm tra vùng sống lâu:** so old usage, tỷ lệ promotion, GC old/mixed/full, `committed` và pause trong đúng giai đoạn. Với collector không chia vùng theo kiểu này, dùng metric phù hợp của nó.
4. **Tìm ai đang giữ đối tượng:** nếu nền tiếp tục tăng ở tải ổn định, dùng JFR, class histogram hoặc heap dump và phân tích bằng Eclipse Memory Analyzer/VisualVM. Xem đối tượng chiếm nhiều bộ nhớ, dominator tree, retained size, GC roots và đường tham chiếu giữ đối tượng.
5. **Kiểm chứng giả thuyết:** một `Map` tĩnh không dọn, listener không unregister, queue không tiêu thụ, ThreadLocal tồn tại quá lâu hoặc cache không giới hạn là *nghi phạm thường gặp*; chỉ kết luận khi tìm được đường giữ tham chiếu hoặc so sánh mẫu trước/sau sửa.

Heap dump có thể lớn, tạo tải CPU/I/O và khiến ứng dụng bị pause tùy công cụ/JVM; dump còn có thể chứa dữ liệu nhạy cảm. Chỉ thu thập trong điều kiện vận hành cho phép. Tránh gọi `System.gc()` để “ép chứng minh” leak: lời gọi là đề nghị GC, có thể bị vô hiệu hóa, gây pause và làm méo điều kiện đo. Không tăng `-Xmx` như phương pháp duy nhất xử lý retention growth; nó chỉ có thể trì hoãn thời điểm đầy heap.

## 9. Những nhầm lẫn cần tránh

- **“Heap used tăng nghĩa là memory leak.”** Sai: cấp phát và đợi GC là hành vi bình thường. Quan sát đáy sau GC tương đương và sự tiến triển của workload.
- **“Đáy sau young GC chính là toàn bộ live set.”** Sai: các vùng chưa được thu gom có thể vẫn chứa garbage.
- **“Sau GC vẫn còn 300 MiB tức 300 MiB bị leak.”** Sai: object còn sống có thể là trạng thái hợp lệ của ứng dụng và JVM; chỉ phần không còn cần nhưng vẫn bị giữ mới đáng điều tra.
- **“Mức giảm `before-after` bằng toàn bộ object bị chết từ GC trước.”** Sai: hai điểm đo không đếm tổng allocation/garbage trong khoảng; các lần GC/ghi nhận khác và concurrent work có thể xen vào.
- **“Đỉnh chạm `committed` là lập tức OOM.”** Sai: JVM có thể mở rộng heap khi còn headroom; OOM phụ thuộc giới hạn, phân mảnh, loại allocation và khả năng thu gom.
- **“Full GC càng thường xuyên càng tốt vì đáy rõ.”** Sai: full GC thường có chi phí lớn; không chủ động gây ra chỉ để đồ thị dễ đọc.
- **“RSS cao mà heap used thấp chứng minh GC lỗi.”** Sai: cần xem memory ngoài heap, native allocations và heap committed.
- **“Đồ thị ít răng cưa nghĩa là không GC.”** Sai: collector concurrent và aggregation có thể làm mờ các bước giảm.

## 10. Checklist thực hành khi xem dashboard

Trả lời đủ các câu hỏi sau trước khi đề xuất tuning hoặc sửa mã:

1. Tôi đang xem `heap used` của **JVM nào**, đơn vị nào, sample interval/aggregation gì?
2. Các đường `committed` và `max` nằm ở đâu? Heap có tự mở rộng không?
3. Các điểm giảm trùng **GC event nào**: young, mixed/old, full hay concurrent cycle?
4. Sau những sự kiện **cùng loại, tải tương đương**, đáy ổn định, tăng, hay trở về mức cũ?
5. Nếu đáy tăng, đó là sau warm-up/batch/cache hợp lệ hay tiếp tục tăng khi workload đã ổn định?
6. Đỉnh, tần suất GC, CPU, pause, latency và lỗi cấp phát thay đổi cùng nhau thế nào?
7. Nếu cần xác minh leak, đã tìm **loại đối tượng và đường tham chiếu giữ chúng** bằng bằng chứng phù hợp chưa?

**Điểm cần nhớ:** đường răng cưa mô tả nhịp cấp phát và thu gom; **đáy sau các chu kỳ GC có thể so sánh** giúp ước lượng xu hướng bộ nhớ được giữ; còn kết luận có rò rỉ hay không phải dựa vào phạm vi GC, tải thực tế và bằng chứng về đối tượng được giữ lại.