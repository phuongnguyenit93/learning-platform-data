# Memory tab trong JConsole

**Memory tab** trong **JConsole** là giao diện giám sát mức sử dụng bộ nhớ của một Java Virtual Machine (JVM) đang chạy. Tab này hiển thị biểu đồ heap, non-heap và từng memory pool theo thời gian; đồng thời cung cấp các chỉ số Used, Committed, Max và thống kê garbage collection (GC).

Memory tab hữu ích khi cần quan sát heap tăng hay giảm, kiểm tra vùng nhớ nào đang chiếm nhiều tài nguyên, theo dõi tác động của GC và phát hiện xu hướng có thể liên quan đến memory leak. Đây là công cụ quan sát runtime dựa trên Java Management Extensions (JMX), không phải công cụ phân tích toàn bộ RAM của hệ điều hành hay tự động tìm nguyên nhân leak.

## 1. JConsole và Memory tab

JConsole là công cụ GUI đi kèm JDK, sử dụng JMX để đọc các thông tin quản lý từ JVM. Sau khi kết nối đến một ứng dụng Java, giao diện thường có các tab:

- **Overview:** tổng quan CPU, memory, thread và class loading.
- **Memory:** biểu đồ heap/non-heap, memory pools và GC.
- **Threads:** số lượng thread, trạng thái và stack trace.
- **Classes:** thống kê class loading.
- **VM:** thông tin runtime và tham số khởi chạy.
- **MBeans:** truy cập các MXBean và MBean đã đăng ký.

Memory tab tập trung vào memory usage. Các biểu đồ được cập nhật theo thời gian để bạn quan sát xu hướng thay đổi khi ứng dụng tạo object, giải phóng object, chạy GC hoặc nạp class.

JConsole đọc dữ liệu từ các platform MXBean, đặc biệt là:

- `MemoryMXBean`: heap/non-heap usage và thao tác yêu cầu GC.
- `MemoryPoolMXBean`: usage của từng pool và thông tin threshold.
- `GarbageCollectorMXBean`: số lần collection và tổng thời gian GC.
- `ClassLoadingMXBean`: số class đã nạp, nếu cần đối chiếu với metaspace.

## 2. Mở JConsole và kết nối JVM cục bộ

`jconsole` nằm trong thư mục `bin` của JDK. Mở terminal:

```bash
jconsole
```

JConsole hiển thị hộp thoại liệt kê các Java process cục bộ mà tài khoản hiện tại có thể quan sát. Chọn ứng dụng cần kiểm tra rồi bấm **Connect**.

Nếu đã biết PID, có thể kết nối trực tiếp:

```bash
jps -l
jconsole 18420
```

Trong ví dụ, `18420` là PID minh họa; hãy thay bằng PID thực tế.

Trên Windows, có thể tìm PID trong Task Manager hoặc dùng `jps -l`. Trên Linux/macOS, có thể dùng `ps` hoặc `jps -l`.

Để local attach hoạt động:

- JConsole và JVM đích thường phải chạy dưới cùng user hệ điều hành.
- JVM phải hỗ trợ Attach API và không bị giới hạn bởi môi trường/security policy.
- Trong container, PID namespace và user có thể khác với host; đôi khi cần chạy JConsole trong cùng container hoặc namespace.
- Một số JVM không attach được nếu Attach Mechanism đã bị vô hiệu hóa khi khởi động.

Khi kết nối local, JConsole có thể bật management agent động cho một JVM attachable chưa bật agent từ đầu. Một số process không hỗ trợ attach sẽ bị làm mờ hoặc không thể chọn.

## 3. Kết nối JConsole tới JVM từ xa

Để giám sát ứng dụng ở máy khác, JConsole kết nối qua JMX agent.

Cú pháp:

```bash
jconsole hostname:port
```

Trong đó:

- `hostname` là máy chạy JVM.
- `port` là cổng JMX agent đã cấu hình trên JVM đích.

Khi mở hộp thoại Remote Process, nhập hostname, port và thông tin xác thực nếu JMX agent yêu cầu.

Remote JMX cần được cấu hình từ phía ứng dụng/JVM. Trong production:

- Bật authentication và TLS theo chính sách của hệ thống.
- Giới hạn nguồn mạng được phép truy cập cổng JMX.
- Không expose JMX unauthenticated ra Internet hoặc mạng không tin cậy.
- Không dùng mật khẩu mặc định hoặc lưu password trong script/repository.
- Ưu tiên VPN, bastion hoặc tunnel bảo mật nếu kiến trúc yêu cầu.

Giám sát local thuận tiện cho development, nhưng JConsole tiêu thụ tài nguyên trên cùng máy đang chạy ứng dụng. Với production, remote monitoring giúp tách tải của giao diện giám sát khỏi máy đang được theo dõi.

## 4. Các thành phần chính của Memory tab

Memory tab thường có những khu vực sau:

1. **Chart:** biểu đồ mức sử dụng bộ nhớ theo thời gian.
2. **Chart selector:** chọn Heap Memory Usage, Non-Heap Memory Usage hoặc memory pool cụ thể.
3. **Time Range:** chọn khoảng thời gian hiển thị trên biểu đồ.
4. **Details:** hiển thị các giá trị Used, Committed, Max và GC time.
5. **Heap/Non-Heap bars:** thanh thể hiện mức sử dụng tương đối của heap và non-heap.
6. **Perform GC:** yêu cầu JVM thực hiện garbage collection.

Tên memory pool và cách hiển thị có thể khác theo JDK vendor, phiên bản JVM, garbage collector và cấu hình runtime. Không giả định mọi máy đều có đúng cùng một danh sách pool.

## 5. Heap Memory Usage

**Heap memory** là vùng runtime nơi JVM cấp phát bộ nhớ cho các object và array. Garbage collector thu hồi vùng nhớ của các object không còn reachable.

Trong Memory tab, chọn biểu đồ **Heap Memory Usage** để quan sát tổng mức sử dụng heap theo thời gian.

Một biểu đồ điển hình có dạng răng cưa:

- Khi ứng dụng tạo object, Used tăng dần.
- Khi GC thu hồi object không còn reachable, Used giảm.
- Committed có thể tăng khi JVM cần thêm vùng nhớ để đáp ứng allocation.
- Committed cũng có thể giảm khi JVM trả một phần vùng nhớ về hệ điều hành.
- Max thể hiện giới hạn heap mà JVM có thể sử dụng, nếu giới hạn được xác định.

Biểu đồ này giúp trả lời:

- Heap có tăng liên tục trong workload ổn định không?
- Sau GC, Used có giảm đáng kể không?
- Heap có thường xuyên tiến sát Max không?
- Committed có tăng theo thời gian không?
- Những đợt tăng bộ nhớ có trùng với thời điểm tải cao hoặc batch job không?

Không kết luận memory leak chỉ từ một đỉnh biểu đồ. Cần quan sát nhiều chu kỳ GC và so sánh mức Used sau GC dưới workload tương đương.

## 6. Non-Heap Memory Usage

**Non-heap memory** chứa dữ liệu phục vụ cấu trúc class và hoạt động nội bộ của JVM. Nó có thể bao gồm:

- Metadata của class và method.
- Runtime constant pool và thông tin class.
- Metaspace và Compressed Class Space trên HotSpot hiện đại.
- Code Cache dùng cho mã máy được JIT compiler tạo ra.
- Các vùng non-heap khác tùy JVM implementation.

Chọn **Non-Heap Memory Usage** để quan sát mức sử dụng vùng nhớ này.

Non-heap tăng có thể liên quan đến:

- Nạp thêm class hoặc proxy động.
- Framework tạo nhiều classloader.
- Classloader cũ không được giải phóng sau redeploy.
- JIT compiler tạo thêm mã máy.
- Ứng dụng hoặc thư viện sử dụng metadata ngày càng nhiều.

Không đồng nhất non-heap với toàn bộ native memory của process. Thread stack, direct buffer, native library và một số allocation ngoài heap có thể làm RSS tăng mà không xuất hiện đầy đủ trong hai biểu đồ heap/non-heap của Memory tab. Nếu process memory tăng nhưng heap ổn định, cần xem thêm Native Memory Tracking (NMT), direct buffer metrics và công cụ hệ điều hành.

**Lưu ý lịch sử:** các tài liệu JDK cũ có thể nhắc đến Permanent Generation (PermGen). HotSpot từ Java 8 đã loại bỏ PermGen và chuyển class metadata sang Metaspace. Khi học hoặc vận hành Java 17+, không dùng PermGen như tên memory pool hiện hành.

## 7. Memory pools và biểu đồ theo từng pool

Một **memory pool** là vùng bộ nhớ mà JVM quản lý. JVM có thể có nhiều pool thuộc heap hoặc non-heap; số lượng và tên pool phụ thuộc garbage collector và implementation.

Với HotSpot dùng G1 trong Java 17+, các pool thường gặp gồm:

| Nhóm | Tên pool ví dụ | Vai trò |
| --- | --- | --- |
| Heap | G1 Eden Space | Vùng cấp phát ban đầu cho phần lớn object mới |
| Heap | G1 Survivor Space | Vùng chứa object sống sót qua các chu kỳ young GC |
| Heap | G1 Old Gen | Vùng chứa object đã được promote hoặc tồn tại lâu |
| Non-heap | Metaspace | Metadata của class |
| Non-heap | Compressed Class Space | Metadata class pointer nén khi JVM sử dụng cơ chế này |
| Non-heap | CodeHeap 'profiled nmethods' | Một phần code cache cho mã được JIT biên dịch |
| Non-heap | CodeHeap 'non-profiled nmethods' | Một phần code cache cho mã JIT không thuộc nhóm profiled |
| Non-heap | CodeHeap 'non-nmethods' | Mã runtime/compiler không thuộc nhóm nmethod thông thường |

Tên và số lượng pool có thể khác nếu dùng Serial GC, Parallel GC, ZGC, Shenandoah hoặc JVM vendor khác.

Trong Chart selector, chọn pool cụ thể để xem đường biểu diễn của pool đó. Việc này giúp xác định phần nào của heap hoặc non-heap đang tăng.

Ví dụ:

- Eden tăng nhanh rồi giảm sau young GC có thể là hoạt động allocation bình thường.
- Old Gen tăng qua nhiều chu kỳ và không giảm đáng kể có thể cần điều tra object retention.
- Metaspace tăng liên tục có thể liên quan đến class loading hoặc classloader lifecycle.
- Code Cache tăng khi ứng dụng warm-up và JIT compile có thể là bình thường.

Không áp dụng tên pool của collector này cho collector khác. Hãy xem danh sách thực tế trong Memory tab hoặc MBeans.

## 8. Đọc Used, Committed và Max

Khu vực Details hiển thị các chỉ số quan trọng.

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Used** | Dung lượng đang được JVM ghi nhận là đã sử dụng tại thời điểm lấy mẫu |
| **Committed** | Dung lượng JVM đã commit và bảo đảm có thể dùng |
| **Max** | Giới hạn tối đa mà memory area có thể sử dụng, nếu được xác định |
| **GC time** | Tổng thời gian và số lần garbage collection theo từng collector |

### Used

Used bao gồm vùng nhớ đang chiếm bởi object còn reachable và object đã unreachable nhưng chưa được GC thu hồi. Vì vậy Used có thể chưa giảm ngay khi ứng dụng bỏ tham chiếu đến object.

### Committed

Committed là dung lượng JVM đã commit để có thể sử dụng. Nó thường lớn hơn hoặc bằng Used. Committed có thể thay đổi theo nhu cầu runtime và chính sách của collector.

### Max

Max là giới hạn trên của vùng nhớ. Giá trị có thể thay đổi hoặc không được xác định; trong API, giá trị không xác định có thể được biểu diễn bằng `-1`.

Ngay cả khi Used chưa đạt Max, allocation vẫn có thể thất bại nếu JVM không thể tăng Committed do thiếu tài nguyên hệ thống hoặc giới hạn container.

### GC time

GC time là thời gian tích lũy đã dùng cho garbage collection và số lần collection. Có thể có nhiều dòng, mỗi dòng tương ứng với một collector/garbage collector bean.

Đây là số liệu tích lũy kể từ khi JVM khởi động hoặc kể từ khi bộ đếm được reset theo implementation; không phải thời gian pause của riêng lần GC gần nhất.

## 9. Heap và Non-Heap bars

Ở góc dưới bên phải, Memory tab hiển thị thanh Heap và Non-Heap để biểu diễn mức sử dụng tương đối so với giới hạn/khả năng quản lý của từng vùng.

Thanh có thể chuyển màu đỏ khi memory usage vượt usage threshold đã cấu hình. Threshold chỉ được hỗ trợ ở một số memory pool; hãy kiểm tra khả năng hỗ trợ trước khi đặt.

Với JMX, thông tin threshold nằm ở `MemoryPoolMXBean`:

- `isUsageThresholdSupported()` cho biết pool có hỗ trợ usage threshold hay không.
- `getUsageThreshold()` đọc ngưỡng hiện tại.
- `setUsageThreshold(long)` đặt ngưỡng nếu được hỗ trợ và caller có quyền phù hợp.
- `isUsageThresholdExceeded()` cho biết ngưỡng có bị vượt tại thời điểm kiểm tra không.

Không coi màu đỏ là bằng chứng chắc chắn có memory leak. Đây là tín hiệu vượt ngưỡng để người vận hành kiểm tra thêm.

## 10. Chart selector và Time Range

**Chart selector** cho phép chọn loại dữ liệu muốn theo dõi:

- Heap Memory Usage.
- Non-Heap Memory Usage.
- Một memory pool cụ thể mà JVM cung cấp.

**Time Range** cho phép chọn khoảng thời gian biểu đồ giữ lại. Chọn khoảng ngắn để xem chi tiết một sự kiện allocation/GC; chọn khoảng dài để quan sát xu hướng qua nhiều phút hoặc lâu hơn.

Cách sử dụng:

1. Chọn Heap Memory Usage để quan sát tổng heap.
2. Chọn Non-Heap Memory Usage để theo dõi metadata và code cache.
3. Chọn từng pool để khoanh vùng khu vực tăng.
4. Đổi Time Range để so sánh biến động ngắn hạn và dài hạn.
5. Đối chiếu thời điểm tăng/giảm với log, metrics, request rate và GC activity.

Không chỉ nhìn một đường tổng. Nếu heap tăng, chọn Old Gen hoặc Eden để tìm pool đóng góp nhiều hơn. Nếu non-heap tăng, kiểm tra Metaspace và Code Cache.

## 11. Perform GC: khi nào nên dùng?

Nút **Perform GC** yêu cầu JVM thực hiện garbage collection. Nó tương đương một yêu cầu GC thông qua management interface; hành vi thực tế phụ thuộc collector và cấu hình JVM.

Có thể dùng trong một phiên điều tra có kiểm soát để quan sát Used trước và sau GC:

1. Ghi nhận Used và Committed hiện tại.
2. Bấm Perform GC một lần.
3. Quan sát Used sau khi GC hoàn tất.
4. So sánh với các chu kỳ GC tự nhiên trước đó.
5. Ghi lại thời điểm thao tác để đối chiếu log và metrics.

Nếu Used giảm mạnh, nhiều object đã unreachable và được thu hồi. Nếu Used vẫn cao, có thể còn nhiều object reachable hoặc collector chưa thu hồi theo kỳ vọng.

**Không bấm Perform GC liên tục.** Yêu cầu explicit GC có thể gây pause và làm thay đổi hành vi runtime. Một số cấu hình có thể bỏ qua explicit GC. Việc Used giảm sau GC không chứng minh ứng dụng không có leak; việc Used không giảm cũng không tự chứng minh leak.

Trong production, ưu tiên quan sát các chu kỳ GC tự nhiên trước. Chỉ dùng Perform GC khi có câu hỏi chẩn đoán cụ thể và đã cân nhắc tác động.

## 12. Nhận diện xu hướng có thể là memory leak

Memory leak trong Java thường xảy ra khi object không còn cần thiết nhưng vẫn reachable qua một reference, ví dụ static collection, cache không giới hạn, listener không được gỡ hoặc ThreadLocal giữ dữ liệu lâu hơn dự kiến.

Dấu hiệu cần điều tra:

- Used sau các chu kỳ GC có xu hướng tăng dần dưới workload tương đương.
- Old Gen tăng qua nhiều chu kỳ và không trở về baseline trước đó.
- Committed liên tục tăng để đáp ứng allocation.
- Tần suất hoặc tổng thời gian GC tăng.
- Ứng dụng tiến gần Max hoặc gặp OutOfMemoryError.
- Số object retained trong một số class tăng theo thời gian.

Quy trình quan sát:

1. Chọn một khoảng thời gian có workload tương đối ổn định.
2. Theo dõi Heap Memory Usage qua nhiều chu kỳ GC.
3. Chuyển sang Old Gen và xem mức Used sau collection.
4. Ghi lại GC time/count.
5. Lặp lại sau một khoảng thời gian và so sánh baseline.
6. Nếu xu hướng đáng ngờ, lấy class histogram hoặc heap dump để phân tích sâu.

Biểu đồ JConsole chỉ giúp phát hiện dấu hiệu. Để tìm nguyên nhân, dùng heap dump với Eclipse Memory Analyzer (MAT), xem dominator tree, retained size và path to GC roots. JFR cũng hữu ích khi cần xem allocation và GC theo thời gian.

## 13. Lưu dữ liệu biểu đồ ra CSV

JConsole cho phép xuất dữ liệu của các chart:

1. Nhấp chuột phải vào biểu đồ cần lưu.
2. Chọn **Save data as...**.
3. Chọn đường dẫn và tên file CSV.
4. Mở CSV bằng spreadsheet hoặc công cụ phân tích dữ liệu.

CSV thường có cột timestamp và một hoặc nhiều cột giá trị. Có thể dùng dữ liệu này để:

- Vẽ biểu đồ riêng.
- So sánh heap giữa các lần chạy.
- Tính baseline và mức tăng theo thời gian.
- Ghép với thời điểm deploy, batch job hoặc sự cố.
- Chia sẻ số liệu đã lọc thay vì gửi toàn bộ màn hình.

Khi nhập CSV vào spreadsheet, kiểm tra định dạng cột timestamp để dữ liệu thời gian được nhận diện chính xác.

## 14. Xem memory metrics qua MBeans

Memory tab dùng các platform MXBean. Nếu cần thông tin chi tiết hơn, mở tab **MBeans**.

Các node thường gặp:

- `java.lang / Memory`: HeapMemoryUsage, NonHeapMemoryUsage, ObjectPendingFinalizationCount và thao tác GC.
- `java.lang / MemoryPool`: Usage, PeakUsage, CollectionUsage và threshold của từng pool.
- `java.lang / GarbageCollector`: CollectionCount và CollectionTime.
- `java.lang / OperatingSystem`: thông tin hệ điều hành và process tùy JDK/vendor.

Có thể double-click một giá trị số được hỗ trợ để xem biểu đồ của attribute đó. Các attribute writable có thể được chỉnh từ MBeans tab nếu MBean cho phép; chỉ thay đổi khi hiểu rõ tác động.

Ví dụ Java đọc heap và từng memory pool:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public class MemoryMetrics {
    public static void main(String[] args) {
        MemoryUsage heap =
            ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.printf(
            "Heap used=%d committed=%d max=%d%n",
            heap.getUsed(),
            heap.getCommitted(),
            heap.getMax()
        );

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();

            if (usage != null) {
                System.out.printf(
                    "%s: used=%d committed=%d max=%d%n",
                    pool.getName(),
                    usage.getUsed(),
                    usage.getCommitted(),
                    usage.getMax()
                );
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MemoryMetrics.java
java MemoryMetrics
```

Số liệu thay đổi theo thời điểm chạy và JVM. Ví dụ này đọc cùng nhóm MXBean mà JConsole sử dụng để trình bày thông tin memory.

## 15. Ví dụ thực hành Java 17: tạo memory activity để quan sát

Ví dụ này tạo allocation ngắn hạn và giữ một số byte array trong danh sách có giới hạn. Mục tiêu là tạo biến động heap đủ để quan sát trên Memory tab.

Tệp **`MemoryTabTarget.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;

public final class MemoryTabTarget {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[] lastTransientAllocation;

    private MemoryTabTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());

        ManagementFactory.getMemoryPoolMXBeans().forEach(pool ->
            System.out.println(
                "pool=" + pool.getName() + " type=" + pool.getType()
            )
        );

        int round = 0;

        while (!Thread.currentThread().isInterrupted()) {
            for (int i = 0; i < 12; i++) {
                lastTransientAllocation = new byte[256 * 1024];
                lastTransientAllocation[0] = (byte) i;
            }

            RETAINED.addLast(new byte[1024 * 1024]);

            if (RETAINED.size() > 16) {
                RETAINED.removeFirst();
            }

            if (round++ % 5 == 0) {
                MemoryUsage heap =
                    ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

                System.out.printf(
                    "heap used=%d committed=%d max=%d retainedChunks=%d%n",
                    heap.getUsed(),
                    heap.getCommitted(),
                    heap.getMax(),
                    RETAINED.size()
                );
            }

            Thread.sleep(500);
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 MemoryTabTarget.java
```

Chạy với heap giới hạn để dễ quan sát:

```bash
java -Xms32m -Xmx128m -XX:+UseG1GC MemoryTabTarget
```

Output minh họa từ một lần chạy:

```text
PID=78016
pool=CodeHeap 'non-nmethods' type=Non-heap memory
pool=Metaspace type=Non-heap memory
pool=CodeHeap 'profiled nmethods' type=Non-heap memory
pool=Compressed Class Space type=Non-heap memory
pool=G1 Eden Space type=Heap memory
pool=G1 Old Gen type=Heap memory
pool=G1 Survivor Space type=Heap memory
pool=CodeHeap 'non-profiled nmethods' type=Non-heap memory
heap used=7455512 committed=35651584 max=134217728 retainedChunks=1
```

PID và số liệu là kết quả của một lần chạy kiểm thử; khi chạy lại, chúng sẽ thay đổi. Tên memory pool cũng phụ thuộc JDK và collector.

Mở terminal thứ hai và kết nối JConsole:

```bash
jconsole 78016
```

Thay `78016` bằng PID được chương trình in ra. Trong JConsole:

1. Chọn tab Memory.
2. Chọn Heap Memory Usage.
3. Chuyển Time Range để quan sát allocation và GC.
4. Chọn G1 Eden Space và G1 Old Gen nếu các pool này xuất hiện.
5. Chuyển sang Non-Heap Memory Usage để xem Metaspace và Code Cache.
6. So sánh Used, Committed, Max và GC time.
7. Có thể xuất chart ra CSV bằng menu chuột phải.

Chương trình giữ tối đa 16 mảng 1 MiB trong danh sách; mỗi vòng thay một mảng cũ bằng mảng mới. Các allocation ngắn hạn tạo thêm hoạt động GC. Đây là ví dụ thực hành, không phải benchmark và không mô phỏng đầy đủ workload production.

Dừng chương trình bằng Ctrl+C ở terminal chạy `MemoryTabTarget`.

## 16. Lỗi thường gặp khi dùng Memory tab

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy JVM trong danh sách Local Process | Khác user, process không attachable hoặc Attach Mechanism bị giới hạn | Kiểm tra user, PID namespace và JVM options |
| Kết nối remote thất bại | JMX agent chưa bật, sai host/port hoặc firewall chặn | Kiểm tra cấu hình JMX và network policy |
| Không thấy pool mong muốn | Pool phụ thuộc collector/JDK/vendor | Xem danh sách thực tế trong Memory tab hoặc MemoryPoolMXBean |
| Heap Used tăng nhưng chưa giảm | Chưa có GC, object còn reachable hoặc workload đang giữ dữ liệu | Quan sát qua nhiều chu kỳ GC và kiểm tra Old Gen |
| Heap Used giảm sau Perform GC | GC đã thu hồi object unreachable | Tiếp tục quan sát baseline; không coi một lần GC là kết luận leak-free |
| Non-Heap tăng liên tục | Class loading, Metaspace hoặc Code Cache tăng | Theo dõi pool cụ thể và classloader statistics |
| Process RAM cao nhưng Heap bình thường | Native memory, thread stacks, direct buffers hoặc native library | Kiểm tra NMT, OS metrics và direct buffer usage |
| Thanh pool chuyển đỏ | Usage threshold bị vượt | Kiểm tra threshold và xu hướng pool; đánh giá khả năng hỗ trợ threshold |
| GC time tăng nhanh | GC xảy ra thường xuyên hoặc tốn thời gian hơn | Đối chiếu allocation, heap occupancy, collector logs và JFR |
| Không lưu được chart CSV | Đường dẫn hoặc quyền ghi không phù hợp | Chọn thư mục có quyền ghi và kiểm tra dung lượng |

## 17. Lưu ý khi giám sát production

- JConsole là công cụ giám sát, không thay thế metrics/alerting liên tục.
- Local JConsole có thể tiêu thụ đáng kể CPU và memory; cân nhắc remote monitoring để giảm tải trên máy đích.
- Không bấm Perform GC lặp lại để ép biểu đồ giảm.
- Không kết luận memory leak từ một snapshot hoặc một lần GC.
- Dùng workload tương đương khi so sánh baseline.
- Bảo vệ thông tin kết nối JMX và credential.
- Không mở cổng JMX không xác thực ra mạng công cộng.
- Lưu CSV, heap dump và JFR theo chính sách bảo mật/retention.
- Khi cần phân tích sâu, kết hợp JConsole với JFR, heap dump, MAT, GC logs và OS-level memory metrics.

Memory tab giúp phát hiện xu hướng và khoanh vùng pool. Muốn xác định nguyên nhân gốc của memory leak, cần theo dõi object retention, GC roots, allocation và lifecycle của ứng dụng.

## 18. Quy trình đọc Memory tab

Khi điều tra memory pressure:

1. Kết nối đúng JVM và ghi lại PID/JDK version.
2. Chọn Heap Memory Usage và quan sát Used/Committed/Max.
3. Chọn Non-Heap Memory Usage để kiểm tra metadata và code cache.
4. Chọn pool cụ thể đang tăng.
5. Theo dõi nhiều chu kỳ GC và so sánh Used sau GC.
6. Đọc GC time/count để đánh giá hoạt động collector.
7. Dùng Perform GC chỉ khi có mục tiêu kiểm tra rõ ràng.
8. Xuất chart CSV nếu cần so sánh hoặc báo cáo.
9. Nếu nghi ngờ leak, lấy histogram/heap dump hoặc JFR để phân tích sâu.
10. Đối chiếu heap/non-heap với process memory và giới hạn container.
11. Bảo vệ file diagnostic và credential JMX.
12. Ghi lại kết luận dựa trên xu hướng, không chỉ một thời điểm.

## 19. Ghi nhớ

- Memory tab trong JConsole giám sát heap, non-heap, memory pools và GC theo thời gian.
- Heap chứa object/array; non-heap chứa class metadata, method data và JIT code.
- Memory pool phụ thuộc JDK, JVM vendor và garbage collector.
- Used có thể gồm cả object unreachable chưa được GC thu hồi.
- Committed là bộ nhớ đã commit; Max là giới hạn tối đa nếu được xác định.
- GC time/count là số liệu tích lũy theo collector.
- Chart selector và Time Range giúp khoanh vùng memory pool và thời gian.
- Perform GC chỉ gửi yêu cầu GC; có thể gây pause và không thay thế phân tích leak.
- Thanh pool có thể chuyển đỏ khi usage threshold được vượt.
- Nhấp chuột phải biểu đồ và chọn Save data as... để xuất CSV.
- Java 17 HotSpot dùng Metaspace thay cho PermGen.
- Heap ổn định không có nghĩa toàn bộ process memory ổn định; cần theo dõi native memory và direct buffers khi cần.

Nắm được cách đọc biểu đồ, memory pools, Used/Committed/Max và GC time giúp bạn sử dụng Memory tab để giám sát JVM có căn cứ, nhận diện memory pressure sớm và quyết định khi nào cần chuyển sang heap dump, JFR hoặc công cụ phân tích sâu hơn.

## Tài liệu tham khảo

- [Using JConsole — Java SE 24 Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [MemoryMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [MemoryPoolMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [GarbageCollectorMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
