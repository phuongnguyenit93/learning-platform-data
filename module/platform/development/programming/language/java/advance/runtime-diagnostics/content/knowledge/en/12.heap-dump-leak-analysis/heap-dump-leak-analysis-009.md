# 12.9 So sánh bằng chứng qua thời gian thay vì kết luận rò rỉ từ một histogram

## 1. Mục tiêu: biến một ảnh chụp đáng ngờ thành kết luận có chứng cứ

Một **class histogram** của Java heap cho biết mỗi lớp hiện có bao nhiêu instance và tổng dung lượng *shallow* của các instance đó. Nó rất hữu ích để khoanh vùng nghi vấn, nhưng **không trả lời trực tiếp** liệu một tập object có đang rò rỉ, object nào giữ chúng sống, hay số lượng đó có bình thường với tải hiện tại.

Ví dụ, nhìn thấy hàng `byte[]` chiếm nhiều bộ nhớ chỉ cho biết có nhiều mảng byte. Chúng có thể thuộc cache có giới hạn, request đang xử lý, payload tạm, hàng đợi, kết quả batch hoặc những object thực sự bị giữ ngoài ý muốn. Một histogram đơn lẻ không phân biệt được các nguyên nhân ấy.

**Mục tiêu bài học:** xây chuỗi bằng chứng `T0 → T1 → T2` dưới các điều kiện có thể so sánh, kiểm tra xu hướng số lượng object và bộ nhớ sau GC cùng workload, rồi dùng heap dump và đường tham chiếu tới GC roots khi cần tìm nguyên nhân. Kết luận phải phân biệt được:

- **Dữ kiện:** điều đo được tại một thời điểm, ví dụ số instance `[B` và `#bytes`.
- **Xu hướng:** thay đổi qua nhiều mốc sau khi đã chuẩn hóa thời gian, tải, GC và cách đo.
- **Giả thuyết:** cache tăng, backlog tồn đọng, session không hết hạn, listener không hủy, hay retention ngoài ý muốn.
- **Chứng cứ xác nhận:** xác định object sống lâu bất thường, nguồn giữ tham chiếu, vòng đời mong đợi và phép thử giải phóng/ổn định.

Trong Java, “memory leak” thường là **tham chiếu còn giữ object mà nghiệp vụ không cần nữa**, khiến GC không thể thu hồi; object vẫn *reachable* nhưng không còn hữu ích. Đây là khái niệm khác việc **cấp phát nhanh** hoặc **heap.used cao tại một thời điểm**.

## 2. Histogram đo gì, và không đo gì?

Lệnh thường dùng trên HotSpot JDK 17+:

```bash
jcmd 12345 GC.class_histogram
```

`12345` là **PID minh họa**, thay bằng PID thật. Một bảng histogram có thể có cấu trúc sau (số liệu **giả định**, không phải stdout cố định):

```text
 num     #instances         #bytes  class name
--------------------------------------------------
   1:          4000        5242880  [B
   2:          8000         192000  java.lang.String
   3:          1500          48000  java.util.HashMap$Node
Total         13500        5482880
```

Các số giả định chỉ nhằm minh họa hình thức cột; đừng dùng phép cộng những hàng minh họa này để suy ra tổng bộ nhớ thật của JVM. Với output thực tế, hãy đọc đúng header và số ở từng dòng.

| Cột | Ý nghĩa | Không được suy diễn thành |
| --- | --- | --- |
| `num` | Thứ hạng trong bảng được sắp theo dung lượng tại lần đo | ID ổn định của lớp qua các lần lấy mẫu |
| `#instances` | Số object thuộc lớp được liệt kê trong lần đo | Số lần cấp phát từ lúc JVM chạy |
| `#bytes` | Tổng **shallow size** của các instance cùng lớp, đơn vị byte | Retained size, tổng bộ nhớ do lớp đó giữ gián tiếp |
| `class name` | Tên lớp/array type, ví dụ `[B` là `byte[]` và `[Ljava.lang.String;` là `String[]` | Bằng chứng chỉ ra lớp này là nguyên nhân leak |

**Shallow size** là kích thước của bản thân object/array, bao gồm phần dữ liệu nằm trong array; nó **không** cộng mọi object được object đó tham chiếu. **Retained size** của một object, ngược lại, ước lượng lượng bộ nhớ sẽ có thể giải phóng nếu loại bỏ các đường giữ tham chiếu thích hợp và các object do nó chi phối trở thành không thể truy cập. Muốn xét retained size, phải phân tích **đồ thị tham chiếu** (heap dump, dominator tree), điều histogram không chứa.

Histogram nhóm theo class nên cũng không cho biết:

- Object nào được tạo trong request nào, ai sở hữu, tuổi thọ và deadline giải phóng của nó.
- Những object đang tạm thời được tham chiếu bởi thread stack, cache, static field hay class loader nào.
- Mức sử dụng đó có phù hợp với số user/session/message đang hoạt động không.
- Có object không còn reachable nhưng chưa được GC dọn trước khi đo không (tùy chế độ của công cụ).
- Một class có nhiều instance do hàng nghìn phần tử hợp lệ hay vì một bộ sưu tập phát triển không giới hạn.

### Reachability và `-all` làm thay đổi ý nghĩa phép đo

Với `jcmd GC.class_histogram`, tùy chọn `-all` cho phép **kiểm tra cả object không còn reachable**; giá trị mặc định là `false` theo tài liệu JDK 21. Vì vậy:

```bash
jcmd 12345 GC.class_histogram
jcmd 12345 GC.class_histogram -all=true
```

**Không so chéo** hai chế độ trên như thể chúng cùng phản ánh “live objects”. Chế độ mặc định hướng tới các object còn được giữ sau hoạt động thu gom thích hợp của VM; chế độ `-all=true` có thể bao gồm object đã chết về mặt reachability nhưng chưa được thu hồi. Trong điều tra leak, hãy ghi lại chính xác chế độ đã dùng, collector/JDK, thời điểm và hoạt động GC lân cận.

Lệnh histogram được JDK xếp **Impact: High**, phụ thuộc kích thước heap và nội dung; có thể gây pause/hoạt động GC và tác động quan sát. Chỉ lấy mẫu với tần suất hợp lý, đặc biệt trên production. Không dùng vòng lặp chụp histogram liên tục như một hệ thống metrics.

## 3. Vì sao một histogram “to” thường tạo kết luận sai?

| Hiện tượng ở một snapshot | Giả thuyết còn mở | Điều cần đo tiếp |
| --- | --- | --- |
| `byte[]` đứng đầu bảng | Buffer của I/O, nội dung cache, payload, object còn chờ GC hoặc retention bất thường | Count/bytes ở T0–T2, loại truy cập, owner trong heap dump |
| Rất nhiều `String` | Data set hợp lệ, parser đang chạy, key cache, log/trace payload | Count trên mỗi request/record; key/value và đối tượng giữ |
| Nhiều `HashMap$Node` | Cache/map lớn; có thể là registry hợp lệ hoặc map không được dọn | Số key, chính sách giới hạn/TTL, owner của map và retained graph |
| `Class`/class loader tăng | Khởi tạo thư viện, tạo dynamic class hợp lệ hoặc class-loader retention | Số class loader qua các chu kỳ deploy, class-unloading/Metaspace |
| Heap cao nhưng histogram không có “thủ phạm” rõ | Nhiều object nhỏ, dữ liệu phân tán, cấu trúc giữ phức tạp | Sau-GC used, dominator tree, nhóm theo class loader/package |

Một mốc cao ở cuối batch có thể rất khác với cùng con số sau khi batch hoàn thành và hàng đợi đã rỗng. **Không thể đánh giá tính bất thường của kích thước nếu chưa biết vòng đời mong đợi của dữ liệu.**

Ngoài ra, bảng là **xếp hạng theo `#bytes`**; dòng số 1 của T0 và dòng số 1 của T1 có thể là hai lớp khác nhau. Muốn diff đúng, ghép bằng **danh tính class (và khi cần class loader)**, không trừ theo cùng số dòng `num`.

## 4. Thiết kế phép đo theo thời gian có thể so sánh

Nên coi mỗi lần thu thập là một bản ghi gồm **histogram + ngữ cảnh vận hành**, không phải chỉ là tệp text. Bộ metadata tối thiểu:

| Trường | Cách thu thập hoặc ghi chú | Vì sao cần |
| --- | --- | --- |
| PID, JVM start time/uptime, version | `jcmd -l`, `VM.version`, `VM.uptime` | Tránh trộn hai JVM khi PID bị tái sử dụng |
| GC, `-Xms`, `-Xmx`, cấu hình runtime | `VM.flags`, cấu hình khởi động | Collector và giới hạn heap ảnh hưởng hình dạng số đo |
| Timestamp của từng snapshot | Đặt tên mốc T0, T1, T2 và ghi giờ bắt đầu/kết thúc | Đối chiếu với GC, log nghiệp vụ và latency |
| Chế độ histogram | Mặc định hay `-all=true`, cùng công cụ/JDK | Bảo đảm cùng tiêu chí reachability |
| Tải | RPS, số request hoàn tất, active users, batch size, queue length | Phân biệt dữ liệu hữu ích tăng với retention bất thường |
| Chu kỳ nghiệp vụ | Sau warm-up? sau batch? sau TTL? sau logout? | Nền sau chu kỳ ổn định mới so được |
| GC và heap | GC count/time, used sau GC hoặc log GC | Không nhầm allocation tạm thời với nền object còn sống |
| Đặc điểm snapshot | Pause, lỗi attach, thời gian chụp, snapshot thiếu | Không kết luận từ mẫu méo/thiếu |

**Một chuỗi thực hành tốt**:

1. **Khởi động/warm-up:** đợi JIT, cache khởi tạo, class loading ban đầu và các tác vụ startup tương đối ổn định. Đặt mốc **T0** khi biết rõ trạng thái nghiệp vụ.
2. **Vận hành ở mức tải A:** giữ tương đối đồng nhất các yếu tố ảnh hưởng; nếu tải thay đổi phải **ghi lại rõ ràng**. Chụp **T1** sau khoảng đủ để có nhiều đợt GC hoặc qua một chu kỳ nghiệp vụ.
3. **Duy trì hoặc dừng tải:** đợi request, batch, session, queue hoặc TTL có cơ hội hoàn thành/hết hạn; chụp **T2**. Nếu nghi retention chậm, thu thập thêm T3, T4 thay vì cố giải thích hai điểm.
4. **Đọc mẫu sau-GC và metrics:** quan sát nền bộ nhớ thấp nhất sau những lần GC **tự nhiên tương đương** trong cùng điều kiện. Nếu chủ động kích hoạt Full GC để chuẩn hóa trong môi trường thử nghiệm, phải gắn nhãn rõ vì bản thân phép đo đã làm thay đổi trạng thái.
5. **Đối chiếu với nghiệp vụ:** khi throughput/active objects ổn định, object còn sống có giữ trần hay tiếp tục tích lũy? Nếu số request tăng gấp đôi, một số class tăng gấp đôi chưa đủ để nghi leak.

Không có “chu kỳ 5 phút” đúng cho mọi ứng dụng. Chọn khoảng cách theo **lifetime dự kiến**: buffer theo request có thể đo vài phút; session TTL một giờ cần theo dõi qua hơn một giờ; cache có warm-up dài cần baseline sau warm-up.

### “Sau GC” nên hiểu thế nào?

`heap.used` lúc T0 khác với live set sau collection: ngay trước GC có thể tồn tại object đã không còn reachable nhưng chưa bị thu hồi. Với concurrent collectors, “sau một lần young GC” không có nghĩa toàn bộ old generation đã được quét và reclaim. Hãy dùng GC log/GC counters để biết **đã xảy ra collection loại nào**, tránh khẳng định một số đo là “sau Full GC” nếu không có bằng chứng.

Oracle khuyên theo dõi **live set trong trạng thái ổn định, dưới tải ổn định, theo thời gian** để nhận biết leak. Dấu hiệu sau-GC used tăng kéo dài tạo **nghi vấn có cơ sở**, chưa thay thế bằng chứng giữ tham chiếu.

## 5. Lấy histogram và GC evidence trên cùng PID

Tại terminal chứa JDK 17+:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 VM.uptime
jcmd 12345 help GC.class_histogram
```

Thay `12345` bằng PID của JVM đang cần khảo sát. Chụp cách nhau theo kế hoạch và đặt tên tệp khác nhau. Ví dụ chạy trong terminal hỗ trợ chuyển hướng stdout:

```bash
jcmd 12345 GC.class_histogram > hist_T0.txt
jstat -gcutil 12345 1000 5 > gc_T0.txt

# Thực hiện hoặc quan sát cùng mức tải, ghi mốc thời gian.
jcmd 12345 GC.class_histogram > hist_T1.txt
jstat -gcutil 12345 1000 5 > gc_T1.txt

# Sau khi tải/công việc có cơ hội hoàn tất.
jcmd 12345 GC.class_histogram > hist_T2.txt
jstat -gcutil 12345 1000 5 > gc_T2.txt
```

Đây là **trình tự thao tác**, không phải một script tự đợi đúng khoảng thời gian: người thực hành phải chụp T0/T1/T2 vào các mốc đã chọn. Trên Windows PowerShell, chuyển hướng output sẽ theo cơ chế encoding của shell; kiểm tra encoding khi xử lý tự động. Nếu công cụ attach thất bại trong container, phải xác minh user/permission, cùng namespace và cơ chế attach, thay vì âm thầm đổi PID.

Các số `YGC`, `FGC`, `YGCT`, `FGCT`, `GCT` của `jstat` cho biết số lần/thời gian GC tích lũy theo bộ đếm công cụ (thời gian thường bằng giây). `-gcutil` hiển thị `E`, `O` theo **phần trăm riêng từng space**; **không đồng nhất `O=80%` với “heap 80%”**. Collector/JDK khác nhau có thể hiển thị cột khác; đọc header thay vì giả định thứ tự cứng.

Nên lưu riêng `heap.used/committed/max` từ `MemoryMXBean`, ứng dụng metrics hoặc GC log. Histogram chỉ là lớp bổ sung để nhìn **phân bố object theo class**, không thay thế toàn cảnh heap.

**Tác động sản xuất:** `GC.class_histogram` có mức tác động cao, nên lên lịch ở cửa sổ chẩn đoán phù hợp, đo thời gian chạy và kiểm tra latency. Không cần gọi `System.gc()` hay `jcmd ... GC.run` sau mỗi mẫu; cách này làm thay đổi hệ thống đang điều tra. Nếu đã chủ động Full GC vì một thí nghiệm được kiểm soát, phải ghi thành một biến của thí nghiệm và không so trực tiếp với mẫu bình thường.

## 6. Cách tính delta đúng khi so T0, T1, T2

Giả sử với **cùng class** `com.acme.OrderContext`:

```text
deltaInstances(T0,T1) = instances(T1) - instances(T0)
deltaShallowBytes     = shallowBytes(T1) - shallowBytes(T0)
growthRate           = deltaShallowBytes / elapsedMinutes
bytesPerInstance     = shallowBytes / instances  (khi instances > 0)
```

Chúng là số đo **net change** giữa các snapshot; không phản ánh tất cả allocation trong khoảng đó vì hàng triệu object có thể vừa được cấp phát vừa được thu hồi.

Ví dụ **giả định** với tải ổn định và cùng chế độ đo:

| Mốc | Thời gian từ T0 | `OrderContext` instances | Shallow bytes | Sau-GC heap used |
| --- | ---: | ---: | ---: | ---: |
| T0 | 0 phút | 2.000 | 160.000 B | 120 MiB |
| T1 | 10 phút | 3.200 | 256.000 B | 150 MiB |
| T2 | 20 phút | 4.400 | 352.000 B | 180 MiB |

Tính được:

- T0 → T1: `+1.200` instances, `+96.000 B` shallow, tốc độ trung bình `9.600 B/phút`.
- T1 → T2: `+1.200` instances, `+96.000 B` shallow, tiếp tục tăng trong cửa sổ thứ hai.
- Nền sau-GC heap used tăng `+30 MiB` mỗi khoảng 10 phút.

Đây là **bằng chứng xu hướng đáng điều tra** khi RPS, số request đồng thời, cache warm-up, batch queue và các chu kỳ nghiệp vụ đã ổn định. **Không được** gán toàn bộ mức tăng `30 MiB` cho `OrderContext`: shallow bytes của chính lớp đó chỉ tăng `96.000 B`, còn các object nó tham chiếu hoặc các cấu trúc khác có thể chiếm phần lớn. Histogram không chứng minh mối liên hệ giữ tham chiếu.

Ngược lại, giả sử cache hợp lệ có số instance `2.000 → 3.200 → 3.200` sau giai đoạn warm-up rồi ổn định nhiều chu kỳ tải; đây có thể là hành vi cache có giới hạn. Nếu workload ở T2 gấp đôi T0, cần chuẩn hóa số liệu theo request/session/queue size trước khi gọi tăng trưởng là bất thường.

**Đừng chỉ lấy tỉ lệ phần trăm tăng**: tăng từ 1 lên 10 object là `+900%` nhưng có thể vô nghĩa; tăng từ 5 GiB lên 6 GiB chỉ `+20%` nhưng có thể nghiêm trọng. Luôn báo cả **delta tuyệt đối, thời gian và bối cảnh tải**.

## 7. Phân biệt bốn kiểu đồ thị qua thời gian

### 7.1. Allocation tạm thời: đỉnh cao nhưng nền trở về

Sau mỗi đợt request, heap used tăng rồi giảm khi GC thu hồi object ngắn hạn. Histogram ở đỉnh tải có thể cho nhiều `byte[]` hoặc `String`, nhưng số lượng sau xử lý và sau GC không tăng bền vững. Hướng xử lý thường là kiểm tra **allocation rate/GC pressure/latency**, chưa phải xác định “leak”.

### 7.2. Warm-up hoặc cache hữu hạn: tăng rồi đạt trần

Cache dần lấp đầy từ 0 tới giới hạn 10.000 entry rồi đi ngang. Histogram lấy sớm sẽ luôn cho delta dương; phải đo qua mốc đạt trần, TTL/eviction hoặc sau khi dừng workload. Kiểm tra cả giới hạn theo **số lượng, dung lượng byte, cardinality khóa** và chính sách eviction thực tế.

### 7.3. Backlog: tích lũy có thể đảo ngược

Queue tăng vì tốc độ sản xuất lớn hơn tiêu thụ, trong khi xử lý chậm. Nhiều message/context cùng tồn tại, sau đó giảm khi consumer bắt kịp. Nếu T0–T2 nằm trong giờ cao điểm, histogram tăng đều có thể là **hệ quả của backlog**. Cần đối chiếu queue depth, throughput, retries và thời gian xả backlog.

### 7.4. Retention bất thường: nền tăng dù đầu vào đã ổn định/kết thúc

Sau mỗi chu kỳ hoàn tất, một bộ sưu tập, listener registry, thread-local, cache không có giới hạn hoặc static field vẫn giữ object không còn cần nữa. T2 sau khi workload/TTL kết thúc vẫn cao và tăng theo số chu kỳ. Đây là **nghi vấn leak mạnh hơn**, nhưng phải mở heap dump để tìm **GC root → chuỗi tham chiếu → object** và so với vòng đời mong đợi.

## 8. Ví dụ Java 17+ có thể chạy: bounded và growing retention

Thí nghiệm tạo hai kiểu retention cùng dạng `byte[]`; ý nghĩa là so **xu hướng trong mỗi tiến trình**. Chế độ `bounded` là cache giới hạn; `growing` cố ý giữ các mảng ngày càng nhiều để mô phỏng **triệu chứng** mà một leak có thể gây ra. Đây là mô phỏng có chủ đích, không phải một lỗi bí mật trong code.

Lưu toàn bộ mã thành **`HistogramTrendDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

public final class HistogramTrendDemo {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[][] lastBurst;

    public static void main(String[] args) throws InterruptedException {
        if (args.length != 1 ||
                (!"bounded".equals(args[0]) && !"growing".equals(args[0]))) {
            System.err.println("Usage: java HistogramTrendDemo bounded|growing");
            return;
        }

        String mode = args[0];
        System.out.println("PID=" + ProcessHandle.current().pid()
                + " mode=" + mode);

        for (int step = 1; step <= 240; step++) {
            // Allocation tam thoi: co the duoc GC thu hoi ve sau.
            byte[][] burst = new byte[8][];
            for (int i = 0; i < burst.length; i++) {
                burst[i] = new byte[128 * 1024];
                burst[i][0] = (byte) step;
            }
            lastBurst = burst;

            // Mang co tham chieu manh tu static Deque.
            byte[] kept = new byte[128 * 1024];
            kept[0] = (byte) step;
            RETAINED.addLast(kept);

            if ("bounded".equals(mode) && RETAINED.size() > 32) {
                RETAINED.removeFirst();
            }
            lastBurst = null;

            if (step % 20 == 0) {
                MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();
                System.out.printf(Locale.ROOT,
                        "step=%d retained=%d used=%.1f MiB committed=%.1f MiB%n",
                        step, RETAINED.size(),
                        heap.getUsed() / 1_048_576.0,
                        heap.getCommitted() / 1_048_576.0);
            }
            Thread.sleep(500);
        }
    }
}
```

Biên dịch:

```bash
javac HistogramTrendDemo.java
```

Chạy **lần lượt từng chế độ** để tránh nhầm PID và cạnh tranh tài nguyên. Trong terminal A:

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC HistogramTrendDemo bounded
```

Đầu ra luôn bắt đầu bằng dòng có dạng `PID=12345 mode=bounded`. Các số `used` và `committed` **không cố định**; khi in ở các bước 20, 40, 60, bộ đếm `retained` lần lượt là `20`, `32`, `32` vì mã giới hạn 32 phần tử. Chương trình lặp 240 bước cách nhau ít nhất 500 ms (khoảng hai phút, có thể lâu hơn do GC hoặc lệnh chẩn đoán).

Trong terminal B khi tiến trình vẫn chạy, thay PID thực tế rồi chụp các mốc ở khoảng sau bước 40/80/160:

```bash
jcmd 12345 GC.class_histogram > bounded_T0.txt
jcmd 12345 GC.class_histogram > bounded_T1.txt
jcmd 12345 GC.class_histogram > bounded_T2.txt
```

**Các lệnh là ba hành động thủ công tại ba thời điểm**, đừng chạy nối nhau tức thì; giữa mỗi lần cần chờ đủ khoảng lấy mẫu và ghi lại step thực tế của ứng dụng. Có thể lấy mẫu GC qua `jstat -gcutil 12345 1000 5` ở giữa.

Sau khi tiến trình `bounded` kết thúc, mở terminal A chạy lại:

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC HistogramTrendDemo growing
```

Chụp cùng một giao thức cho **PID mới**, lưu thành `growing_T0.txt`, `growing_T1.txt`, `growing_T2.txt`. Khi in ở bước 20/40/60, `retained` lần lượt là `20`, `40`, `60`, vì không loại phần tử.

### Dự kiến quan sát và cách viết kết luận

- **`bounded`:** sau warm-up, số mảng `byte[]` được giữ cố ý sẽ ổn định quanh giới hạn; các buffer Java/JVM khác có thể làm tổng `[B` dao động, nên histogram không nhất thiết cho một con số phẳng tuyệt đối.
- **`growing`:** `RETAINED` tăng thêm một mảng `128 KiB` mỗi bước, nên phần dữ liệu cố ý giữ tăng khoảng `128 KiB/bước` (240 bước ≈ 30 MiB dữ liệu mảng, chưa kể overhead). Histogram `[B` và nền sau-GC có xu hướng tăng, nhưng số đo thực tế vẫn chịu ảnh hưởng hoạt động JVM/GC.
- **Điểm mấu chốt:** chỉ từ histogram tăng không thể biết vì sao; khi xem source trong bài mới xác định được tham chiếu `static RETAINED` và vòng đời hai chế độ. Ở dự án thật phải tìm quan hệ này bằng heap dump, thông tin nghiệp vụ và phân tích GC roots.

Không lấy kết quả hai JVM khác nhau làm cặp T0/T1 để tính delta. **Mỗi chế độ phải có chuỗi T0–T2 bên trong chính JVM của nó** rồi mới so đặc điểm hình dạng xu hướng giữa hai chế độ.

## 9. Khi nào cần heap dump thay vì histogram tiếp theo?

Histogram qua nhiều mốc có thể chỉ ra **class đáng nghi và xu hướng**. Để hỏi “object nào đang giữ dữ liệu này?” phải chuyển sang đồ thị object, ví dụ heap dump HPROF:

```bash
jcmd 12345 GC.heap_dump heap_T2.hprof
```

Chỉ chạy khi đã cân nhắc pause, dung lượng ổ đĩa, quyền truy cập và thông tin nhạy cảm có thể tồn tại trong heap. Trên HotSpot JDK 21, `GC.heap_dump` được tài liệu xếp **Impact: High** và **yêu cầu Full GC trừ khi dùng `-all`**. Vì vậy dump mặc định và dump `-all=true` không phải hai snapshot có ý nghĩa reachability giống nhau. Thu thập T1/T2 bằng cùng chế độ và ghi lại mọi thay đổi do dump/GC tạo ra.

Trong **Eclipse Memory Analyzer (MAT)** hoặc công cụ tương đương, thực hiện:

1. **Histogram/Top Consumers:** xác nhận loại object và lượng shallow heap tương ứng; tìm những class tăng đáng kể khi so hai dump có điều kiện tương đương.
2. **Dominator Tree:** xem object/cấu trúc nào đang chi phối một tập object lớn; **retained size** giúp đo mức bộ nhớ có thể giải phóng nếu bỏ được điểm giữ đó.
3. **Path to GC Roots:** lần ngược từ object nghi vấn đến static field, thread, thread-local, JNI root, class loader... để biết **vì sao object còn reachable**.
4. **Kiểm tra vòng đời nghiệp vụ:** tham chiếu đó có được phép tồn tại tới thời điểm T2 không? Nếu dữ liệu chỉ cần trong một request đã hoàn tất, lý do gì object vẫn nằm trong registry/cache/queue?
5. **Xác nhận bằng phép thử:** giới hạn cache, hủy registration, xóa key đã hết hạn, đóng resource... trong môi trường phù hợp; lặp lại cùng tải và xem nền sau-GC/retained path có còn tích lũy không.

**Một root giữ hàng triệu object không tự động là lỗi.** Cấu trúc đó có thể là cache chủ đích. Câu hỏi cuối cùng là “đang giữ **đúng những object còn cần** trong **đúng khoảng thời gian** hay không?”.

Phân biệt:

| Công cụ | Khẳng định có thể đưa ra | Điều còn thiếu |
| --- | --- | --- |
| Một histogram | Lớp X có N instance, B shallow bytes tại mốc T | Xu hướng, root, vòng đời, tính bất thường |
| Nhiều histogram cùng điều kiện | Lớp X có delta/tốc độ tăng qua các mốc | Object cụ thể nào tồn tại, đường tham chiếu |
| Heap/GC metrics theo thời gian | Nền sau GC tăng/ổn định, GC pressure thay đổi | Object và chủ sở hữu dẫn đến tăng |
| Heap dump + dominator + GC roots | Đường giữ object và retained graph tại mốc đo | Dữ liệu nghiệp vụ để kết luận giữ tham chiếu sai |
| Phép thử trước/sau thay đổi | Kiểm tra giả thuyết nguyên nhân dưới tải tương đương | Độ tin cậy qua nhiều chu kỳ, edge cases, regression |

## 10. Mẫu biên bản điều tra và cách trình bày có trách nhiệm

Dùng một bảng thống nhất để tránh lời kết luận vượt quá dữ liệu:

| Mốc | Giờ/PID | Workload | GC context | N của lớp nghi vấn | Shallow bytes | Sau-GC heap used | Ghi chú |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| T0 | ... | warm-up xong, load A | ... | ... | ... | ... | Baseline |
| T1 | ... | load A, sau 1 chu kỳ | ... | ... | ... | ... | Delta so T0 |
| T2 | ... | load A hoặc đã xả queue | ... | ... | ... | ... | Kiểm tra plateau |
| T3 (nếu cần) | ... | sau TTL/GC phù hợp | ... | ... | ... | ... | Phản chứng |

**Mẫu nhận định tốt (số giả định):**

> Trong cùng JVM HotSpot/G1, với các histogram mặc định và tải khoảng 100 requests/s ổn định, count của `OrderContext` tăng 2.000 → 3.200 → 4.400 trong 20 phút; mức used sau các chu kỳ GC tương đương tăng từ 120 lên 180 MiB. Các request quan sát đã hoàn tất và queue không tăng. Đây là dấu hiệu retention cần điều tra. Chưa đủ bằng chứng xác định leak hay đối tượng giữ; bước tiếp theo là tìm dominator/GC roots trong heap dump và đối chiếu TTL/vòng đời `OrderContext`.

**Mẫu nhận định yếu:** “Histogram có rất nhiều `byte[]`, chắc chắn ứng dụng leak.” Câu này không nói tải, thời gian, cách đo, kiểu GC hay chủ sở hữu object.

Đừng dùng “đã chứng minh leak” chỉ vì thấy hai histogram tăng. Dùng ngôn ngữ thích hợp với mức bằng chứng: **quan sát → nghi vấn → nguyên nhân có đường tham chiếu → được xác nhận bằng phép thử**.

## 11. Các sai lầm thường gặp

1. **Kết luận từ một histogram:** không biết tăng hay giảm, trước/sau chu kỳ nghiệp vụ, cũng không biết baseline.
2. **Trừ theo số thứ tự `num`:** thứ hạng thay đổi; cần ghép đúng class, cân nhắc class loader cùng tên.
3. **Đọc `#bytes` như retained size:** đó là shallow tổng theo class; không chứng minh những object này đang giữ cả cây tham chiếu.
4. **So histogram mặc định với `-all=true`:** một bên có thể đếm object đã không còn reachable; ý nghĩa phép đo khác.
5. **Không đồng bộ thời gian/tải:** một ảnh chụp giữa batch và một ảnh chụp lúc idle không tạo được delta đại diện.
6. **Không biết collector và GC vừa chạy gì:** so `used` trước GC với sau GC rồi kết luận “đã hết leak” hoặc “leak tăng”.
7. **Nhầm `heap.committed` hoặc RSS với live set:** committed là bộ nhớ JVM đã cam kết; RSS còn chứa native/stack/direct memory; histogram không giải thích hết RSS.
8. **Bỏ qua cache warm-up và TTL:** object tăng đúng thời gian xây dựng cache hoặc trong thời gian session tồn tại có thể hợp lệ.
9. **Nhìn class phổ biến mà bỏ qua owner:** `String`/`byte[]` xuất hiện ở rất nhiều thư viện; cần path đến root và ngữ cảnh nghiệp vụ.
10. **Dùng tỷ lệ % mà không ghi chênh lệch byte/count:** tỷ lệ cao có thể là thay đổi rất nhỏ về tuyệt đối.
11. **Lấy histogram quá thường xuyên trên production:** lệnh có Impact High, bản thân phép đo có thể ảnh hưởng latency/GC.
12. **Chủ động Full GC không ghi nhận:** làm thay đổi live set/latency và biến thí nghiệm thành điều kiện khác.
13. **So class count giữa hai phiên bản/deployment khác nhau:** schema, traffic, code path, GC, cache và class loader có thể khác.
14. **Cho rằng tăng trưởng tuyến tính đủ chứng minh không có giới hạn:** nhiều cache tăng tuyến tính trong giai đoạn đầu, sau đó đạt trần.
15. **Không xác minh bằng phép thử:** có đường tham chiếu tới một static cache vẫn chưa đủ nếu dữ liệu đó đúng là phải tồn tại.

## 12. Bài tập tự đánh giá

**Tình huống A:** T0 có 10 MiB shallow `byte[]`, T1 là 18 MiB trong lúc queue tăng từ 200 lên 2.000, T2 còn 11 MiB sau khi queue xả hết và qua GC. Kết luận nào phù hợp?

Gợi ý: số liệu phù hợp với **backlog/retention tạm thời**; chưa có bằng chứng leak. Cần chứng minh queue xử lý xong và mảng có vòng đời tương ứng.

**Tình huống B:** cùng workload và cấu hình, T0/T1/T2 cách nhau mỗi 30 phút; sau-GC used tăng 300 → 390 → 480 MiB, `SessionRecord` và `HashMap$Node` tăng đều; session cũ đã hết hạn. Làm gì?

Gợi ý: báo **nghi vấn retention bền vững**, thu heap dump tại mốc phù hợp, tìm map/registry giữ `SessionRecord` và path tới GC roots, đối chiếu TTL. Chỉ sau khi chứng minh object không cần nữa vẫn được tham chiếu và thay đổi eviction làm xu hướng ổn định mới đủ mạnh để quy kết cơ chế leak.

**Tình huống C:** hai histogram báo `byte[]` tăng gấp đôi nhưng T0 dùng mặc định còn T1 dùng `-all=true`. Có tính `Δ` để kết luận không?

Gợi ý: **không**; điều kiện reachability khác nhau, phải lấy lại mẫu cùng chế độ.

**Thực hành:** chạy hai chế độ `bounded` và `growing` ở mục 8, lấy ba histogram theo thời gian, trích count/bytes của `[B`, ghi cả `retained` từ stdout và `heap.used`. Viết báo cáo 5 câu lần lượt gồm: điều kiện, số đo T0–T2, delta, cách giải thích bằng vòng đời, bước xác minh tiếp theo. Chỉ được kết luận mức mà dữ kiện hỗ trợ.

## 13. Tài liệu chuẩn để đối chiếu

- [Oracle JDK 21 — `jcmd`, `GC.class_histogram` / `GC.heap_dump` và mức impact](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — Troubleshoot Memory Leaks: live set, histogram theo chuỗi và giả thuyết leak](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).
- [Oracle JDK 21 — Diagnostic Tools: JFR, JMX và GC evidence](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Eclipse MAT — Dominator Tree: retained graph](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html).
- [Eclipse MAT — Finding Memory Leak: Top Consumers và Paths to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html).

**Nguyên tắc thực hành:** histogram cho biết *cái gì đang có*; nhiều mốc cùng điều kiện cho biết *cái gì đang thay đổi*; heap dump/GC roots và vòng đời nghiệp vụ mới giúp giải thích *vì sao object còn được giữ*, còn phép thử có kiểm soát giúp xác nhận giả thuyết.
