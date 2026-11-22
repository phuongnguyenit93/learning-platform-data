# Garbage Collector, bộ nhớ đang dùng và kích thước ảnh

Trong Java Advance CRaC, ba đại lượng thường được đặt cạnh nhau là lượng heap đang dùng, lượng bộ nhớ tiến trình đang chiếm dụng và kích thước ảnh checkpoint. Chúng có liên hệ với nhau, nhưng không đo cùng một thứ.

- **Heap đang dùng** cho biết JVM hiện ghi nhận bao nhiêu bộ nhớ dành cho các đối tượng Java.
- **Bộ nhớ tiến trình** phản ánh những trang bộ nhớ mà tiến trình đang giữ hoặc đang cư trú trong RAM, bao gồm cả phần ngoài heap.
- **Kích thước ảnh CRaC** phản ánh dữ liệu cần lưu để khôi phục trạng thái tiến trình tại checkpoint, theo định dạng của runtime và công cụ checkpoint đang dùng.

Garbage Collector (GC) có thể làm thay đổi heap đang dùng và đôi khi làm giảm dữ liệu phải lưu trong ảnh checkpoint. Tuy nhiên, không thể lấy một con số heap sau GC để suy ra trực tiếp kích thước ảnh. Muốn tối ưu CRaC, cần hiểu từng đại lượng và đo chúng trong cùng một kịch bản.

## 1. Phân biệt heap, bộ nhớ tiến trình và ảnh checkpoint

Một ứng dụng Java không chỉ sử dụng heap. Ngoài heap còn có Metaspace, bộ nhớ mã máy đã biên dịch, stack của các thread, direct buffer, thư viện native, vùng ánh xạ tệp và nhiều cấu trúc nội bộ của JVM.

| Đại lượng | Nó mô tả điều gì? | Công cụ hoặc API thường dùng |
|---|---|---|
| Heap used | Dung lượng heap JVM đang ghi nhận là đã dùng | `MemoryMXBean`, `Runtime` |
| Heap committed | Dung lượng heap JVM đã commit và có thể sử dụng | `MemoryMXBean` |
| Heap max | Giới hạn heap tối đa mà JVM có thể dùng | `MemoryMXBean`, `Runtime.maxMemory()` |
| Non-heap | Bộ nhớ JVM quản lý ngoài heap, ví dụ Metaspace và Code Cache | `MemoryMXBean.getNonHeapMemoryUsage()` |
| Native memory | Bộ nhớ ngoài heap do JVM, thư viện native hoặc ứng dụng quản lý | Native Memory Tracking, công cụ hệ điều hành |
| RSS | Các trang bộ nhớ của tiến trình hiện đang cư trú trong RAM | Công cụ hệ điều hành |
| Container memory | Mức sử dụng bộ nhớ được bộ điều khiển tài nguyên của container ghi nhận | Cgroup hoặc công cụ container |
| Checkpoint image size | Dung lượng các tệp ảnh được tạo ra để khôi phục tiến trình | Công cụ hệ điều hành trên thư mục checkpoint |

Các đại lượng này trả lời những câu hỏi khác nhau. Ví dụ, heap used có thể giảm mạnh sau GC trong khi heap committed gần như giữ nguyên. RSS cũng có thể giảm ít hơn heap used vì tiến trình còn giữ stack, Metaspace, direct buffer và các trang native khác. Ảnh checkpoint lại phụ thuộc vào tập dữ liệu trạng thái mà cơ chế checkpoint phải lưu.

### Heap used, committed và max

JVM quản lý heap trong một vùng địa chỉ bộ nhớ. Ba số liệu quan trọng có ý nghĩa như sau:

- **used**: dung lượng heap hiện đang được sử dụng theo góc nhìn của JVM. Số này có thể bao gồm cả đối tượng đã không còn được ứng dụng tham chiếu nhưng GC chưa thu hồi.
- **committed**: dung lượng heap JVM đã commit để có thể cấp phát đối tượng. Phần chênh lệch giữa committed và used là khoảng trống hiện có trong vùng heap đã commit.
- **max**: giới hạn heap tối đa. Giá trị có thể không xác định trên một số môi trường hoặc JVM, khi đó API trả về giá trị âm.

Ví dụ, nếu heap có used = 400 MiB, committed = 768 MiB và max = 2 GiB, điều đó có nghĩa JVM đang ghi nhận 400 MiB heap được sử dụng, có 768 MiB heap đã commit và còn giới hạn tăng trưởng đến 2 GiB. Nó không có nghĩa tiến trình chỉ chiếm 400 MiB RAM.

`Runtime.freeMemory()` cũng không phải lượng RAM trống của máy. Nó biểu thị dung lượng còn trống bên trong heap đã commit tại thời điểm gọi. Để đọc các số liệu heap một cách nhất quán, có thể dùng `MemoryMXBean`.

## 2. Garbage Collector hoạt động như thế nào?

Java cấp phát phần lớn đối tượng thông thường trên heap. Khi ứng dụng tạo đối tượng, JVM dành vùng nhớ cho đối tượng đó. Trong quá trình chạy, một số đối tượng tiếp tục được sử dụng; số khác trở thành rác khi không còn đường tham chiếu hợp lệ từ trạng thái đang sống của chương trình.

GC xác định đối tượng còn có thể truy cập được bằng cách bắt đầu từ các **GC roots**, chẳng hạn:

- Tham chiếu từ stack của các thread đang chạy.
- Tham chiếu trong trường static đang được giữ bởi class loader còn sống.
- Tham chiếu JNI và một số tham chiếu nội bộ do JVM quản lý.

Từ các roots này, JVM lần theo đồ thị tham chiếu. Đối tượng có thể đi tới từ một root được xem là reachable. Đối tượng không thể đi tới từ bất kỳ root nào có thể được thu hồi. Một nhóm đối tượng tham chiếu vòng lẫn nhau vẫn có thể được thu hồi nếu cả nhóm không còn đường đi từ GC roots. Vì vậy, GC không dựa đơn giản vào việc đếm số tham chiếu.

### Các thế hệ và chu kỳ thu gom

Nhiều collector tận dụng quan sát rằng phần lớn đối tượng chỉ tồn tại trong thời gian ngắn. Heap vì thế thường được tổ chức hoặc xử lý theo các vùng có vai trò tương tự:

- **Young generation**: nơi nhiều đối tượng mới được cấp phát. Thu gom vùng này thường diễn ra thường xuyên hơn.
- **Old generation**: nơi các đối tượng sống lâu được giữ lại sau nhiều chu kỳ thu gom hoặc được cấp phát theo chiến lược của collector.

Tên vùng, cách tổ chức và lịch thu gom phụ thuộc vào GC được chọn. G1, Parallel GC, ZGC và các collector khác có chiến lược khác nhau về vùng nhớ, mức độ đồng thời, thời gian dừng và khả năng thu gọn bộ nhớ. Không nên giả định mọi JVM đều vận hành giống nhau.

GC có thể thực hiện một hoặc nhiều công việc:

1. Xác định đối tượng còn sống và đối tượng không còn reachable.
2. Thu hồi vùng nhớ của đối tượng không còn sống.
3. Di chuyển hoặc compact đối tượng để giảm phân mảnh, nếu collector sử dụng cơ chế đó.
4. Điều chỉnh lượng heap đã commit hoặc trả một số vùng nhớ về hệ điều hành khi chiến lược và điều kiện runtime cho phép.

Thu hồi đối tượng không đồng nghĩa JVM phải trả ngay toàn bộ vùng heap tương ứng về hệ điều hành. JVM có thể giữ vùng đã commit để phục vụ các lần cấp phát tiếp theo, tránh phải xin lại bộ nhớ liên tục.

### Đối tượng không còn dùng và đối tượng đã được GC thu hồi

Hai trạng thái này cần được phân biệt:

- Một đối tượng đã không còn cần thiết về mặt nghiệp vụ nhưng vẫn được giữ bởi một tham chiếu còn tồn tại thì vẫn reachable. GC không thể tự suy đoán rằng ứng dụng không cần nó.
- Một đối tượng đã unreachable nhưng chưa đi qua chu kỳ GC thích hợp vẫn có thể chiếm chỗ trong heap used.

Ví dụ, một cache giữ tham chiếu đến hàng triệu bản ghi cũ sẽ khiến các bản ghi đó vẫn reachable. Gọi GC không giải quyết được việc cache giữ dữ liệu quá lâu. Cần đặt giới hạn dung lượng, thời gian sống hoặc loại bỏ các mục không còn cần thiết.

GC cũng không thay thế việc đóng tài nguyên bên ngoài heap. File, socket, kết nối cơ sở dữ liệu và tài nguyên native cần được quản lý bằng cơ chế vòng đời rõ ràng như try-with-resources hoặc callback của CRaC. Không nên chờ GC chạy để đóng các tài nguyên này.

### Vì sao GC ảnh hưởng đến checkpoint?

Checkpoint lưu trạng thái tiến trình tại một thời điểm. Nếu heap vẫn chứa nhiều đối tượng rác chưa được thu gom, các trang bộ nhớ chứa chúng có thể vẫn thuộc trạng thái mà cơ chế checkpoint phải xem xét và lưu. Một chu kỳ GC trước checkpoint có thể:

- Giảm heap used bằng cách thu hồi đối tượng không còn reachable.
- Làm thay đổi nội dung các trang heap.
- Trong một số điều kiện, giúp collector thu gọn heap hoặc trả bớt vùng nhớ đã commit.
- Làm giảm lượng dữ liệu bộ nhớ cần lưu trong ảnh checkpoint.

Hiệu quả phụ thuộc vào collector, cách heap được commit, cách các trang được ghi nhận và cách công cụ checkpoint tạo ảnh. Nếu phần lớn heap chứa đối tượng còn sống, GC không thể thu hồi chúng. Nếu bộ nhớ tăng chủ yếu đến từ native allocation hoặc direct buffer còn đang được giữ, GC trên Java heap cũng không tự giải phóng ngay phần đó.

`System.gc()` chỉ là một yêu cầu để JVM xem xét chạy GC. JVM có thể bỏ qua hoặc xử lý yêu cầu theo cấu hình và chiến lược của nó. Không nên coi lời gọi này là cam kết rằng toàn bộ rác đã được thu hồi hoặc ảnh checkpoint chắc chắn nhỏ hơn.

## 3. Đọc số liệu bộ nhớ trong Java

Có thể dùng Java Management API để đọc heap và thống kê tích lũy của các GC. Đoạn mã sau không yêu cầu một collector cụ thể:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class MemoryReport {

    private static final long MIB = 1024L * 1024L;

    private MemoryReport() {
    }

    public static void print(String phase) {
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memoryBean.getHeapMemoryUsage();
        MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

        System.out.printf(
                Locale.ROOT,
                "[%s] heap: used=%s, committed=%s, max=%s%n",
                phase,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(heap.getMax())
        );

        System.out.printf(
                Locale.ROOT,
                "[%s] non-heap: used=%s, committed=%s, max=%s%n",
                phase,
                mib(nonHeap.getUsed()),
                mib(nonHeap.getCommitted()),
                mib(nonHeap.getMax())
        );

        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(
                    Locale.ROOT,
                    "[%s] GC %s: collections=%d, time=%s%n",
                    phase,
                    gc.getName(),
                    gc.getCollectionCount(),
                    millis(gc.getCollectionTime())
            );
        }
    }

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.1f MiB", bytes / (double) MIB);
    }

    private static String millis(long value) {
        return value < 0 ? "unknown" : value + " ms";
    }
}
```

Các bộ đếm GC là số tích lũy kể từ khi JVM khởi động. `getCollectionCount()` cho biết số lần thu gom mà MXBean ghi nhận; `getCollectionTime()` là thời gian tích lũy theo millisecond. Một số collector hoặc JVM có thể không cung cấp đủ số liệu, khi đó API trả về giá trị âm. Không nên so sánh hai lần đo nếu thời gian chạy, tải hoặc cấu hình GC khác nhau mà không tính đến các khác biệt đó.

Có thể gọi `MemoryReport.print("warm")` sau khi ứng dụng đã khởi động và tải dữ liệu cần thiết, rồi gọi lại trước checkpoint. Kết quả giúp thấy heap và bộ đếm GC thay đổi ra sao. Nó chưa cho biết RSS hoặc kích thước ảnh checkpoint.

### Đọc kết quả minh họa

Giả sử một lần đo ghi nhận:

```text
[before-gc] heap: used=920.0 MiB, committed=1024.0 MiB, max=2048.0 MiB
[after-gc]  heap: used=310.0 MiB, committed=1024.0 MiB, max=2048.0 MiB
```

Có thể kết luận heap used đã giảm khoảng 610 MiB sau chu kỳ GC được quan sát. Tuy nhiên, committed vẫn là 1024 MiB. JVM vẫn giữ vùng heap đã commit ở mức đó, nên không thể kết luận tiến trình đã trả lại 610 MiB RAM cho hệ điều hành. Cũng chưa thể kết luận ảnh checkpoint giảm đúng 610 MiB.

Nếu heap used không giảm sau GC, hãy kiểm tra xem dữ liệu có còn được giữ bởi cache, static field, thread local, queue hoặc các tham chiếu đang sống hay không. Nếu heap used nhỏ nhưng RSS vẫn cao, hãy kiểm tra native memory, thread stack, direct buffer, Metaspace, Code Cache và các vùng ánh xạ.

## 4. Ảnh checkpoint CRaC chứa những gì?

CRaC cho phép checkpoint trạng thái của một tiến trình JVM để có thể khôi phục tiến trình đó sau này. Ảnh checkpoint là dữ liệu do runtime và cơ chế checkpoint tạo ra để tái lập trạng thái tiến trình. Với môi trường Linux thường dùng CRaC, quá trình này dựa vào khả năng checkpoint/restore của hệ điều hành và công cụ tương ứng.

Về mặt khái niệm, trạng thái cần khôi phục có thể bao gồm:

- Các trang bộ nhớ của tiến trình, trong đó có các trang chứa heap Java.
- Trạng thái thread và thông tin thực thi cần thiết để tiếp tục tiến trình.
- Các ánh xạ bộ nhớ và trạng thái tài nguyên mà công cụ checkpoint hỗ trợ lưu.
- Những dữ liệu phụ trợ và metadata theo định dạng của công cụ checkpoint.

Chi tiết chính xác phụ thuộc JDK CRaC, phiên bản runtime, hệ điều hành, công cụ checkpoint, cấu hình và cách lưu ảnh. Không nên giả định ảnh luôn là một tệp duy nhất hoặc mọi vùng nhớ đều được lưu theo cùng một cách.

### Kích thước ảnh không bằng heap used

Kích thước ảnh có thể chịu ảnh hưởng bởi nhiều yếu tố:

1. **Các trang heap có dữ liệu cần khôi phục**: số lượng và nội dung trang bộ nhớ được checkpoint ghi nhận.
2. **Heap committed và cách JVM quản lý trang**: heap đã commit có thể giữ những trang mà ứng dụng không còn sử dụng trực tiếp.
3. **Bộ nhớ ngoài heap**: thread stack, Metaspace, Code Cache, direct buffer, JNI và thư viện native.
4. **Số lượng thread và cấu trúc runtime**: mỗi thread có trạng thái và vùng stack riêng.
5. **Tài nguyên và memory mapping**: tệp được ánh xạ, thư viện, socket và các tài nguyên khác theo khả năng hỗ trợ của môi trường.
6. **Định dạng lưu trữ**: ảnh có thể gồm nhiều tệp; cách ghi trang, nén, sparse file hoặc chia sẻ trang ảnh hưởng đến số byte hiển thị trên đĩa.

Vì vậy, ba tình huống sau có thể xảy ra:

- Heap used giảm mạnh nhưng ảnh giảm ít, vì committed heap hoặc các vùng native vẫn cần được lưu.
- Heap used gần như không đổi nhưng ảnh thay đổi do thread, native allocation hoặc các vùng nhớ khác thay đổi.
- Kích thước ảnh trên đĩa khác đáng kể với lượng bộ nhớ tiến trình đang cư trú trong RAM, do định dạng lưu trữ, nén hoặc sparse file.

Khi đo thư mục ảnh trên Linux, `du -sh` thường phản ánh dung lượng block được cấp phát trên đĩa; `ls -lh` phản ánh kích thước logic của tệp. Hai số có thể khác nhau nếu có sparse file. Hãy ghi rõ bạn đang so sánh kích thước logic hay dung lượng đĩa thực tế.

### Phân biệt CRaC checkpoint image và Docker image

Trong môi trường container, từ “image” còn có nghĩa là **OCI/Docker image**. Hai loại ảnh này khác nhau:

| Loại ảnh | Nội dung chính | Yếu tố thường ảnh hưởng |
|---|---|---|
| OCI/Docker image | Các layer hệ thống tệp dùng để tạo container | JRE/JDK, thư viện, ứng dụng, tài nguyên và layer build |
| CRaC checkpoint image | Trạng thái tiến trình đang chạy để khôi phục | Heap và native memory, thread, mapping, trạng thái tiến trình và định dạng checkpoint |

Giảm dung lượng JAR hoặc Docker layer có thể giảm kích thước OCI image, nhưng không tự động làm ảnh checkpoint nhỏ tương ứng. Ngược lại, giảm dữ liệu sống trong tiến trình có thể tác động đến ảnh checkpoint mà không thay đổi các layer của Docker image.

## 5. GC có thể giảm kích thước ảnh CRaC đến đâu?

GC có thể giúp giảm kích thước ảnh khi heap chứa nhiều đối tượng rác và những trang chứa chúng không còn cần được giữ nguyên trong ảnh. Nhưng mức giảm không có tỷ lệ cố định với số byte được thu hồi.

Hãy xét ba trường hợp:

**Trường hợp A — nhiều đối tượng tạm đã hết vòng đời.** Ứng dụng vừa tải và xử lý một lượng lớn dữ liệu tạm. Sau khi xử lý, các tham chiếu đã được loại bỏ. Nếu GC thu hồi được phần lớn dữ liệu đó trước checkpoint, heap used có thể giảm đáng kể. Những trang bộ nhớ không còn cần thiết có thể làm ảnh nhỏ hơn, tùy cách JVM và công cụ checkpoint quản lý trang.

**Trường hợp B — cache lớn vẫn đang được sử dụng.** Cache giữ tham chiếu đến dữ liệu để phục vụ các request sau restore. Những đối tượng đó vẫn reachable, vì vậy GC phải giữ chúng. Nếu muốn giảm ảnh, cần xem xét chính sách cache: giới hạn dung lượng, thời gian sống, dữ liệu có thể tải lại và chi phí làm nóng cache sau restore.

**Trường hợp C — bộ nhớ tăng ngoài heap.** Ứng dụng giữ nhiều direct buffer hoặc cấp phát native memory qua JNI. GC trên heap Java không đồng nghĩa phần bộ nhớ này được giải phóng ngay. Cần quản lý vòng đời buffer và tài nguyên native theo API tương ứng, sau đó đo lại RSS và ảnh checkpoint.

Một full GC trước checkpoint đôi khi hữu ích trong một thử nghiệm có kiểm soát, nhưng không nên mặc định chạy nó trong mọi lần checkpoint. Full GC có thể gây pause dài, tăng độ trễ, làm giảm lợi ích khởi động nhanh và vẫn không bảo đảm ảnh nhỏ đi. Chỉ giữ bước này nếu số liệu trên môi trường mục tiêu chứng minh lợi ích tổng thể.

### Có nên gọi System.gc() trong beforeCheckpoint?

Không có câu trả lời đúng cho mọi ứng dụng. `beforeCheckpoint` là thời điểm thích hợp để chuẩn bị trạng thái ứng dụng và tài nguyên theo hợp đồng CRaC. Có thể thử nghiệm yêu cầu GC ở giai đoạn này, nhưng cần đánh giá ít nhất:

- GC có thực sự chạy hay không, thể hiện qua bộ đếm GC và heap used.
- Thời gian dừng thêm trước checkpoint.
- Kích thước ảnh trước và sau thay đổi.
- Thời gian restore và bộ nhớ sau restore.
- Ảnh hưởng đến latency và thông lượng khi ứng dụng tiếp tục chạy.

Nếu `System.gc()` bị tắt bằng cấu hình JVM hoặc JVM bỏ qua yêu cầu, lời gọi không tạo ra hiệu quả như mong đợi. Không dùng một lời gọi `System.gc()` như bằng chứng rằng heap đã được làm sạch.

## 6. Đo bộ nhớ tại vòng đời CRaC

Một cách đo có ích là ghi số liệu ở các mốc có ý nghĩa:

1. Sau khi JVM khởi động và hoàn tất phần warm-up cần thiết.
2. Sau khi tải dữ liệu hoặc cache mà ứng dụng dự kiến giữ lại trong ảnh.
3. Ngay trước checkpoint.
4. Sau khi restore và hoàn tất callback phục hồi tài nguyên.

CRaC cung cấp `Resource` để ứng dụng chuẩn bị trước checkpoint và phục hồi sau restore. Ví dụ sau đăng ký một resource để in số liệu heap ở hai callback. Nó chỉ quan sát số liệu; không tự gọi GC và không thay đổi chính sách cache.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointMemoryMetrics implements Resource {

    public CheckpointMemoryMetrics() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        MemoryReport.print("beforeCheckpoint");
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        MemoryReport.print("afterRestore");
    }
}
```

Khởi tạo resource một lần trong giai đoạn ứng dụng khởi động để nó được đăng ký với global context. Đảm bảo lớp này được biên dịch bằng CRaC JDK/API phù hợp với runtime đang chạy. Ứng dụng thực tế thường có nhiều resource khác để đóng hoặc chuẩn bị kết nối, thread và tài nguyên bên ngoài trước checkpoint, rồi mở lại hoặc kiểm tra chúng sau restore.

Số liệu in từ callback giúp quan sát heap tại hai mốc. Để đánh giá kích thước ảnh, cần đo riêng thư mục checkpoint sau khi thao tác checkpoint hoàn tất. Để đánh giá bộ nhớ tiến trình, cần lấy RSS hoặc số liệu container từ hệ điều hành. Không thay thế các phép đo này bằng `MemoryMXBean`.

### Các công cụ đo bổ sung

Tùy môi trường chạy, có thể kết hợp:

- **JMX / `MemoryMXBean`**: heap used, committed, max và non-heap.
- **`GarbageCollectorMXBean`**: số lần và thời gian GC tích lũy.
- **`jcmd <pid> GC.heap_info`**: thông tin heap của JVM đang chạy, nếu lệnh và JVM hỗ trợ.
- **`jcmd <pid> VM.native_memory summary`**: phân tích native memory khi JVM được khởi động với Native Memory Tracking phù hợp, ví dụ `-XX:NativeMemoryTracking=summary`.
- **Công cụ hệ điều hành**: RSS, số thread, memory mapping và bộ nhớ container.
- **`du` / `ls` trên thư mục checkpoint**: kích thước ảnh lưu trên đĩa.

Native Memory Tracking có overhead và không bao quát mọi allocation từ thư viện native bên ngoài JVM. RSS cũng không cho biết chính xác phần nào là heap. Hãy dùng nhiều góc đo để giải thích nguyên nhân thay đổi thay vì cố tìm một chỉ số duy nhất.

## 7. Quy trình thử nghiệm để đánh giá ảnh hưởng của GC

Muốn biết GC có giúp ảnh CRaC nhỏ hơn trong ứng dụng cụ thể hay không, hãy thiết kế một phép so sánh có thể lặp lại.

### Chuẩn bị hai lượt chạy

- **Lượt 1 — baseline**: chạy ứng dụng với cùng cấu hình và dữ liệu, đưa ứng dụng đến trạng thái sẵn sàng checkpoint, rồi tạo ảnh.
- **Lượt 2 — có GC được yêu cầu**: lặp lại cùng quy trình, nhưng yêu cầu GC ở một thời điểm xác định trước checkpoint. Ghi lại việc GC có thực sự diễn ra hay không.

Giữ giống nhau các yếu tố có thể ảnh hưởng kết quả: phiên bản JDK CRaC, collector, `-Xms`, `-Xmx`, dữ liệu đầu vào, cache, số thread, tải, thời gian warm-up và cách tạo ảnh. Dùng một tiến trình mới cho mỗi lượt để tránh trạng thái còn sót lại từ lần chạy trước.

### Ghi lại các số liệu

| Thời điểm | Heap used | Heap committed | GC count/time | RSS | Kích thước ảnh |
|---|---:|---:|---:|---:|---:|
| Sau warm-up | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Chưa có |
| Trước checkpoint | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Chưa có |
| Sau khi tạo ảnh | Không áp dụng nếu tiến trình đã checkpoint | Không áp dụng | Lưu log trước checkpoint | Ghi theo cách đo phù hợp | Ghi dung lượng ảnh |
| Sau restore | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Dùng ảnh đã tạo |

Đừng chỉ ghi số cuối cùng. Nếu heap used giảm nhưng RSS không giảm, điều đó cho thấy phần bộ nhớ đã thu hồi chưa làm giảm tương ứng trang RAM của tiến trình. Nếu RSS giảm nhưng kích thước ảnh không đổi, có thể các trang hoặc metadata khác chi phối kích thước ảnh. Cần kiểm tra thêm cấu trúc ảnh và đặc điểm lưu trữ.

### Đánh giá kết quả

Một thay đổi chỉ có ích khi cải thiện mục tiêu thực tế mà không tạo ra chi phí lớn hơn ở nơi khác. Hãy xem đồng thời:

- Ảnh checkpoint giảm bao nhiêu byte và tỷ lệ phần trăm.
- Thời gian chuẩn bị checkpoint tăng bao nhiêu.
- Thời gian restore có thay đổi không.
- RSS và container memory sau restore có phù hợp giới hạn triển khai không.
- Ứng dụng có còn dữ liệu cần thiết, kết nối và hành vi đúng sau restore không.
- Độ trễ request đầu tiên và thời gian làm nóng cache sau restore có tăng không.

Lặp lại phép đo nhiều lần và so sánh trong cùng điều kiện. GC và hệ điều hành có thể tạo biến thiên giữa các lần chạy. Một lần đo duy nhất không đủ để kết luận một tùy chọn GC làm ảnh nhỏ hơn.

## 8. Những cách giảm bộ nhớ và ảnh checkpoint

Các biện pháp nên bắt đầu từ dữ liệu và vòng đời ứng dụng:

1. **Giới hạn cache**: đặt maximum size, TTL hoặc chính sách loại bỏ. Chỉ giữ dữ liệu có giá trị sau restore.
2. **Loại bỏ tham chiếu không cần thiết**: xóa mục khỏi collection, queue, listener hoặc ThreadLocal khi công việc kết thúc.
3. **Tránh giữ dữ liệu tạm quá lâu**: xử lý theo batch vừa phải, giải phóng tham chiếu sau khi hoàn tất và tránh lưu toàn bộ kết quả trung gian nếu không cần.
4. **Quản lý direct buffer và native resource**: sử dụng API có vòng đời rõ ràng; đóng tài nguyên đúng lúc thay vì chờ GC.
5. **Quản lý thread**: tránh tạo thread không cần thiết và cấu hình pool hợp lý. Nhiều thread có thể làm tăng stack memory và trạng thái phải checkpoint.
6. **Chuẩn bị resource theo CRaC**: đóng hoặc tạm dừng tài nguyên không thể giữ qua checkpoint; mở lại hoặc xác minh chúng trong `afterRestore`.
7. **Chọn cấu hình heap bằng số liệu**: điều chỉnh `-Xms`, `-Xmx` và collector theo tải thực tế. Heap quá lớn có thể làm tăng áp lực bộ nhớ; heap quá nhỏ có thể tăng tần suất GC và giảm thông lượng.

Giảm `-Xmx` chỉ thay đổi giới hạn heap, không bảo đảm ảnh checkpoint nhỏ hơn. Giảm `-Xms` có thể thay đổi heap commit ban đầu nhưng tác động thực tế phụ thuộc cách JVM mở rộng heap và tải ứng dụng. Hãy đo thay đổi trên runtime CRaC mục tiêu.

Một số ứng dụng cần giữ cache để đạt latency thấp ngay sau restore. Xóa toàn bộ cache có thể làm ảnh nhỏ hơn nhưng khiến request đầu tiên phải tải hoặc tính toán lại dữ liệu. Hãy cân bằng kích thước ảnh, thời gian restore, thời gian warm-up và trải nghiệm sau restore.

## 9. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Heap used giảm 500 MiB thì ảnh chắc chắn giảm 500 MiB. | Heap used và ảnh đo các phạm vi khác nhau; mức giảm phụ thuộc trang bộ nhớ và định dạng checkpoint. |
| Heap committed bằng RSS. | Committed là số liệu heap JVM; RSS là trang bộ nhớ tiến trình đang cư trú trong RAM. |
| Gọi `System.gc()` bảo đảm thu gom hết rác. | Đây là yêu cầu GC; JVM có thể bỏ qua hoặc xử lý theo cấu hình. |
| GC giải phóng socket, file và mọi native memory. | GC quản lý đối tượng Java; tài nguyên ngoài heap cần vòng đời riêng. |
| Heap used thấp nghĩa là tiến trình nhẹ. | Native memory, thread stack, Metaspace, direct buffer và mapping vẫn có thể lớn. |
| Docker image nhỏ thì CRaC checkpoint image cũng nhỏ. | OCI image và checkpoint image chứa những loại dữ liệu khác nhau. |
| Xóa cache luôn là tối ưu. | Cache có thể làm ảnh lớn hơn nhưng giảm độ trễ sau restore; cần đo cả hai mục tiêu. |

## 10. Checklist trước khi kết luận

- [ ] Đã xác định “image” đang nói đến OCI/Docker image hay CRaC checkpoint image.
- [ ] Đã ghi heap used, committed, max và non-heap tại cùng các mốc đo.
- [ ] Đã ghi GC count/time và xác nhận GC thực sự xảy ra khi thử nghiệm.
- [ ] Đã đo RSS hoặc container memory bằng công cụ hệ điều hành.
- [ ] Đã đo kích thước thư mục checkpoint và ghi rõ đang dùng kích thước logic hay dung lượng đĩa.
- [ ] Đã giữ nguyên JDK, GC, heap flags, dữ liệu và quy trình warm-up giữa các lượt so sánh.
- [ ] Đã kiểm tra thời gian checkpoint, restore và hành vi ứng dụng sau restore.
- [ ] Chỉ giữ bước GC chủ động nếu số liệu cho thấy lợi ích phù hợp với chi phí pause.

Điểm cốt lõi khi vận hành CRaC là GC quản lý khả năng thu hồi đối tượng trên Java heap, còn checkpoint phải lưu trạng thái rộng hơn heap. GC có thể giảm dữ liệu sống và góp phần làm ảnh nhỏ hơn, nhưng kết quả chỉ có thể xác nhận bằng cách đo riêng heap, bộ nhớ tiến trình và ảnh checkpoint trong cùng một kịch bản.
