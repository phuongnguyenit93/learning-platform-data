# Đánh giá chi phí CPU, bộ nhớ, dung lượng đĩa và thời gian tạo dump

## 1. Dump là một thao tác chẩn đoán có chi phí

Khi ứng dụng chậm hoặc có dấu hiệu rò rỉ bộ nhớ, dump giúp giữ lại thông tin để phân tích sau. Nhưng để tạo bằng chứng đó, JVM phải thực hiện thêm công việc ngay trên tiến trình đang phục vụ người dùng.

Cần hiểu đúng hai loại thường gặp trong Spring Boot Actuator:

- **Thread dump** ghi lại ngăn xếp lời gọi, trạng thái và thông tin khóa của các luồng được công cụ quan sát.
- **Heap dump** ghi lại các đối tượng và quan hệ tham chiếu trong Java heap để phân tích phần bộ nhớ đang được giữ lại.

Thread dump phù hợp với câu hỏi “luồng đang làm gì, chờ ở đâu?”. Heap dump phù hợp với câu hỏi “đối tượng nào đang giữ bộ nhớ và qua đường tham chiếu nào?”. Heap dump không phải bản sao đầy đủ mọi vùng bộ nhớ của tiến trình; nó không thay thế việc chẩn đoán bộ nhớ native, direct buffer hoặc toàn bộ trạng thái hệ điều hành.

Với Actuator, `threaddump` có thể trả JSON hoặc văn bản; `heapdump` trả dữ liệu nhị phân, thường cần lưu thành tệp để phân tích. Định dạng heap dump phụ thuộc JVM: HotSpot dùng HPROF, OpenJ9 dùng PHD. Bài tập chạy mã bên dưới dành cho **HotSpot, Java 17 trở lên**, với JDK 21 để đối chiếu số đo. [Spring Boot 3.3: Thread Dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html), [Heap Dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

Trong bài, **thu gom rác (garbage collection, GC)** là công việc JVM thu hồi bộ nhớ của đối tượng không còn cần giữ. **Safepoint** là điểm phối hợp để JVM có thể thực hiện một số công việc với trạng thái các luồng phù hợp; tùy thao tác, các luồng ứng dụng có thể bị dừng để hoàn tất công việc đó. Không đồng nhất mọi safepoint với một lần GC.

Mục tiêu không phải tìm một con số chung như “dump luôn mất 2 giây”. Mục tiêu là biết **đo gì, dự trù tài nguyên nào và khi nào chi phí vượt khả năng chịu đựng của ứng dụng**.

## 2. Tách bốn loại chi phí và ba khoảng thời gian

### 2.1. CPU, RAM, đĩa và thời gian không thay thế cho nhau

| Đại lượng | Câu hỏi cần trả lời |
| --- | --- |
| CPU | JVM dùng thêm bao nhiêu thời gian xử lý để duyệt đối tượng, thu thập stack, GC, định dạng hoặc nén dữ liệu? |
| Bộ nhớ | Trong lúc tạo và truyền dump, tiến trình/container cần thêm bộ nhớ nào ngoài phần đang phục vụ nghiệp vụ? |
| Đĩa | Tệp được tạo ở đâu, chiếm bao nhiêu byte, có bao nhiêu bản đồng thời và còn đủ chỗ cho hoạt động khác không? |
| Thời gian | Công việc chẩn đoán kéo dài bao lâu và trong khoảng nào các yêu cầu nghiệp vụ bị ảnh hưởng? |

Một lần dump có thể không làm CPU trung bình tăng nhiều nhưng vẫn gây chậm nghiêm trọng vì ứng dụng bị dừng trong một khoảng hoặc vì I/O bị nghẽn. Ngược lại, CPU của nhiều luồng JVM có thể tăng mạnh trong một khoảng thời gian thực khá ngắn.

### 2.2. Phân biệt thời gian tạo, thời gian tải và thời gian gián đoạn

Với luồng tạo heap dump ra tệp rồi tải qua HTTP, có thể hình dung:

```text
Nhận yêu cầu
    -> xác thực / chờ phối hợp
    -> JVM tạo tệp dump
    -> ứng dụng đọc tệp và truyền phản hồi
    -> máy khách lưu tệp
```

Có ba số đo khác nhau:

1. **Thời gian tạo dump**: từ lúc bắt đầu thao tác trong JVM đến khi tệp được tạo xong theo cơ chế đang dùng.
2. **Thời gian hoàn tất yêu cầu**: gồm cả tạo dump, truyền mạng và ghi phía máy khách.
3. **Thời gian ảnh hưởng nghiệp vụ**: khoảng dừng JVM, độ trễ tăng, yêu cầu hết thời gian chờ, hàng đợi dồn lại và thời gian phục hồi sau đó.

Không lấy thời gian curl chạy làm thời gian JVM bị dừng. Không lấy riêng thời gian GC làm toàn bộ thời gian tạo dump.

Nếu client timeout sau 30 giây, điều đó chỉ chứng minh client đã ngừng chờ. Nó không chứng minh công việc bên JVM đã bị hủy; cần kiểm tra trạng thái máy chủ trước khi nghĩ đến lần tạo tiếp theo.

## 3. Chi phí CPU: phải hiểu JVM đang làm việc gì

### 3.1. Heap dump

Để ghi một heap dump, JVM cần duyệt cấu trúc đối tượng, thu thập metadata liên quan và ghi biểu diễn của chúng. Nếu yêu cầu chỉ ghi các đối tượng còn có thể truy cập, công việc có thể bao gồm một lần thu gom rác lớn trước khi ghi.

Trong HotSpot, tham số `live=true` của `HotSpotDiagnosticMXBean.dumpHeap` có nghĩa là chỉ ghi đối tượng còn có thể truy cập từ các đối tượng khác. Không hiểu `live` là “dump trực tiếp nhưng không gây gián đoạn”. [JDK 21: HotSpotDiagnosticMXBean.dumpHeap](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html#dumpHeap(java.lang.String,boolean)).

Tài liệu `jcmd` JDK 21 xếp `GC.heap_dump` vào nhóm ảnh hưởng cao, phụ thuộc kích thước và nội dung heap; lệnh yêu cầu Full GC trừ khi dùng tùy chọn `-all`. Đây là thông tin của công cụ đó, không phải lời hứa về một thời gian dừng cố định cho mọi JVM. [JDK 21: jcmd GC.heap_dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Các yếu tố cần ghi trong kết quả thử nghiệm gồm:

- Phiên bản, nhà cung cấp JVM và bộ thu gom rác.
- Heap đang dùng, số lượng và cấu trúc đối tượng.
- Chế độ ghi đối tượng còn truy cập được hay cả đối tượng chưa được thu gom.
- CPU thực tế được cấp, giới hạn CPU của container và mức tải nền.
- Tốc độ ghi tệp, áp lực bộ nhớ và việc nén nếu cơ chế đang dùng có hỗ trợ.

Đổi sang ghi cả đối tượng chưa được thu gom có thể giảm một phần công việc thu gom trước đó nhưng làm dữ liệu lớn hơn và vẫn phải duyệt/ghi heap. Không kết luận `live=false` là “không dừng JVM” hoặc luôn rẻ hơn về tổng chi phí. Không áp dụng tham số HotSpot cho OpenJ9 khi chưa kiểm tra hỗ trợ.

### 3.2. Thread dump

Thread dump không cần chụp toàn bộ các đối tượng trong heap, nên thường có chi phí nhỏ hơn heap dump ở cùng ứng dụng. Tuy nhiên, việc thu thập nhiều stack trace và thông tin khóa, tạo kết quả rồi chuyển sang JSON/văn bản vẫn tiêu tốn CPU và bộ nhớ.

Chi phí tăng theo số luồng được thu thập, độ sâu stack và thông tin đồng bộ hóa cần ghi. Lấy thread dump liên tục trên ứng dụng có rất nhiều luồng có thể tự trở thành nguồn tải.

Trong Spring Boot 3.3.0, `ThreadDumpEndpoint` dùng `ThreadMXBean.dumpAllThreads(true, true)`. Trên JDK 21, `ThreadMXBean` quan sát **platform thread**, không quản lý virtual thread. Vì vậy, ứng dụng dùng virtual thread cần kiểm tra công cụ thu thập phù hợp; một kết quả ít luồng không chứng minh toàn hệ thống có ít tác vụ. [Mã nguồn ThreadDumpEndpoint 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/management/ThreadDumpEndpoint.java), [JDK 21: ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

### 3.3. CPU time khác thời gian thực

Giả sử thao tác kéo dài 4 giây theo đồng hồ nhưng các luồng trong tiến trình dùng tổng cộng 9 giây CPU. Hai số không mâu thuẫn: nhiều luồng có thể chạy song song trên nhiều lõi.

Ngược lại, thao tác kéo dài 20 giây nhưng CPU time chỉ tăng ít có thể đang chờ I/O, bị giới hạn CPU hoặc chờ được phối hợp với các luồng khác.

Để đọc số đo đúng, cần biết công cụ báo CPU theo một lõi, theo toàn máy hay theo quota container. Một mẫu CPU thưa có thể bỏ qua đỉnh ngắn; thời gian CPU của tiến trình cũng bao gồm công việc nền và nghiệp vụ diễn ra cùng lúc, không riêng thao tác dump.

## 4. Chi phí bộ nhớ: heap còn trống chưa đủ để kết luận an toàn

### 4.1. Kích thước tệp không bằng lượng RAM cần thêm

Các đại lượng sau khác nhau:

- `-Xmx`: giới hạn Java heap.
- Heap đã sử dụng: số đo của vùng heap tại thời điểm quan sát.
- Bộ nhớ cư trú của tiến trình hoặc bộ nhớ tính vào container.
- Kích thước heap dump trên đĩa.
- Bộ nhớ cần cho công cụ phân tích dump sau này.

Tệp HPROF không phải bản sao byte theo byte của toàn bộ vùng `-Xmx`. Đối tượng được chọn, định dạng bản ghi và metadata làm kích thước tệp khác các số đo heap. Không đặt quy tắc “dump luôn bằng heap used” hoặc “dump chắc chắn không vượt Xmx” để quyết định dung lượng.

Một cơ chế ghi ra tệp rồi truyền bằng luồng cũng không có nghĩa phải cấp thêm một Java heap lớn bằng toàn bộ tệp. Nhưng điều đó không làm chi phí RAM bằng 0: JVM, lớp I/O, kết quả thread dump, bộ đệm mạng và các thành phần trung gian vẫn sử dụng tài nguyên.

### 4.2. Nhìn ở mức tiến trình và container

Ngoài Java heap còn có metaspace, code cache, ngăn xếp luồng, direct buffer và các vùng native khác. Trên hệ thống có giới hạn bộ nhớ, cần quan sát số đo bộ nhớ được hệ điều hành/container tính thực tế, cùng phần dự phòng cho tải đang tăng.

Tệp đặt trên `tmpfs` tiêu thụ bộ nhớ, dù đường dẫn trông như một thư mục đĩa thông thường. Với Kubernetes, dữ liệu trong `emptyDir` có `medium: Memory` được tính như sử dụng bộ nhớ, không như lưu trữ cục bộ thông thường. Một heap dump lớn ghi vào đó có thể đẩy container tới giới hạn bộ nhớ. [Kubernetes: quản lý tài nguyên và emptyDir trong bộ nhớ](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Với hệ thống tệp trên đĩa, bộ nhớ đệm của hệ điều hành và cách hạch toán cgroup cũng cần được xét. Không cộng RSS và bộ nhớ đệm một cách tùy ý rồi coi đó là số liệu container chính xác; chọn một hệ đo nhất quán cho môi trường đang vận hành.

### 4.3. Không dùng hai điểm đo để khẳng định đỉnh RAM

Heap trước và sau dump có thể giảm vì GC. Điều đó không chứng minh rằng trong lúc dump không có đỉnh bộ nhớ hoặc ứng dụng không bị ảnh hưởng.

Để đánh giá phần dự phòng, cần chuỗi số liệu đủ dày trong toàn khoảng thử nghiệm: heap, bộ nhớ tiến trình/container, GC và hoạt động I/O. Nếu chỉ có số đo trước/sau, phải ghi rõ giới hạn đó.

Máy phân tích dump là một ngân sách riêng: công cụ có thể tạo chỉ mục và dùng thêm RAM/đĩa đáng kể. Không mở dump lớn ngay trong chính container đang gặp áp lực bộ nhớ.

## 5. Chi phí đĩa: tính đúng nơi ghi và số bản cùng tồn tại

### 5.1. Có thể có cả tệp phía máy chủ và phía máy khách

Ở nhánh HotSpot của Spring Boot 3.3.0, endpoint tạo tệp tạm rồi trả về tài nguyên để truyền đi; tệp được xóa khi luồng đọc được đóng theo cơ chế của tài nguyên. Nó cũng có khóa quanh giai đoạn tạo dump. [Mã nguồn HeapDumpWebEndpoint 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/management/HeapDumpWebEndpoint.java).

Các hệ quả cần kiểm tra trên phiên bản triển khai thực tế:

- Có một tệp trên máy chủ trước khi tải về máy khách.
- Client chậm có thể kéo dài thời gian tệp máy chủ còn tồn tại.
- Khóa tạo dump không đồng nghĩa với giới hạn tổng số tệp của mọi lần tải đang diễn ra.
- Lỗi truyền, lỗi xóa tệp hoặc tiến trình kết thúc bất thường cần được xử lý theo quy trình dọn tệp; không dựa vào giả định luôn dọn xong.

Với nhánh HotSpot này, tệp tạm được tạo qua cơ chế thư mục tạm của Java, thường liên quan `java.io.tmpdir`. Không cho rằng đặt `-XX:HeapDumpPath` cho dump khi OutOfMemoryError cũng tự đổi nơi lưu tệp của endpoint Actuator. Đó là hai đường tạo dump khác nhau.

Nếu muốn chỉ định thư mục tạm khi khởi động ứng dụng, cần kiểm tra mount, quyền ghi, quota và ảnh hưởng tới các thành phần khác cũng dùng thư mục đó. Với OpenJ9, kiểm tra riêng cơ chế và vị trí tạo PHD; không suy từ nhánh HotSpot.

### 5.2. Một phép dự trù dung lượng

Dùng các biến cho cùng một hệ thống tệp:

```text
D_plan  = kích thước dump dự trù dựa trên thử nghiệm tương đương
N       = số tệp dump tối đa cùng tồn tại trên hệ thống tệp đó
G       = dung lượng dự phòng cho log và dữ liệu khác tăng trong khoảng thao tác
R       = mức trống tối thiểu cần giữ cho vận hành

Free_needed = N * D_plan + G + R
```

Đây là phép lập kế hoạch, không phải công thức dự đoán chính xác HPROF.

Ví dụ giả định:

| Thành phần | Giá trị |
| --- | --- |
| Một dump dự trù | 3 GiB |
| Log/dữ liệu khác có thể tăng | 1 GiB |
| Mức trống cần giữ | 2 GiB |
| Dung lượng đang trống | 8 GiB |

Nếu chỉ có một tệp cùng tồn tại, cần `3 + 1 + 2 = 6 GiB`: qua điều kiện dung lượng đã đặt. Nếu có hai tệp, cần `2 * 3 + 1 + 2 = 9 GiB`: không đạt.

Qua điều kiện đĩa **không có nghĩa toàn bộ thao tác đã an toàn**: CPU, RAM và độ trễ vẫn phải được đánh giá riêng.

Dùng đúng đơn vị: `1 GiB = 1024 MiB`; không trộn GB thập phân với GiB rồi xem các phép chia là chính xác. Kiểm tra dung lượng khả dụng cho đúng tài khoản tiến trình, quota, giới hạn tệp, inode nếu có và không gian tạm của proxy/công cụ trung gian.

### 5.3. Nén và lưu nhiều bản có thêm chi phí

Nén sau khi tạo có thể giảm số byte cần truyền nhưng tiêu tốn CPU, thời gian và có thể cần thêm dung lượng khi tệp gốc và tệp nén cùng tồn tại. Nó không làm biến mất chi phí tạo bản dump chưa nén trước đó.

Nếu công cụ có chế độ ghi nén trực tiếp, phải đánh giá riêng tốc độ và CPU của chế độ đó. Không mặc định endpoint Actuator 3.3 hỗ trợ mọi tùy chọn nén của `jcmd`.

## 6. Ước lượng thời gian bằng mô hình có giới hạn

Giả sử dự trù một tệp **3 GiB = 3.072 MiB**, tốc độ ghi hữu hiệu đo được là **150 MiB/s**, còn đường truyền tải về hữu hiệu là **40 MiB/s**:

```text
Phần ghi:    3072 / 150 = 20,48 giây
Phần truyền: 3072 / 40  = 76,8 giây
```

Hai con số chỉ giúp thấy ngân sách I/O. Chúng chưa gồm chi phí duyệt heap, GC, chờ được phối hợp với JVM, xác thực, proxy hoặc biến động tải.

Trong giai đoạn truyền, đọc phía máy chủ, mạng và ghi phía máy khách có thể chạy theo một luồng liên tục. Tốc độ bị giới hạn bởi khâu chậm nhất; không mặc định cộng ba lần thời gian cho cùng một luồng byte.

Trong cơ chế tạo xong tệp rồi mới truyền, giai đoạn tạo và giai đoạn tải xảy ra nối tiếp. Tuy vậy, không cộng phần ghi tệp một lần nữa nếu thời gian tạo đã được đo bao gồm nó.

Tốc độ ghi khi bộ nhớ đệm còn trống có thể cao hơn tốc độ duy trì lâu dài của thiết bị. Một kết quả ghi xong ở tầng phần mềm cũng không mặc nhiên là cam kết dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ.

Để chọn cửa sổ vận hành, cần thử với heap, kiểu đối tượng, tải, giới hạn tài nguyên và thiết bị gần thực tế; ghi cả khoảng biến động thay vì chỉ lấy lần chạy nhanh nhất.

## 7. Thí nghiệm Java nhỏ: đo tạo dump ngay trong JVM

Chương trình sau tạo một heap dump của **chính JVM thử nghiệm**. Nó giữ tám mảng, mỗi mảng 1 MiB; heap tối đa được giới hạn ở 64 MiB bằng lệnh chạy.

Thực hiện trong thư mục thử riêng, không có dữ liệu thật. Tệp dump có thể chứa dữ liệu tồn tại trong JVM, nên giữ quyền truy cập phù hợp cả trong thí nghiệm. Chương trình từ chối ghi nếu tệp đích đã tồn tại; dùng một thư mục mới cho mỗi lần đo.

Lưu mã thành `DumpCostProbe.java`:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class DumpCostProbe {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        Path output = Path.of("dump-cost-lab.hprof").toAbsolutePath();
        if (Files.exists(output)) {
            throw new IllegalStateException("Output already exists; use a fresh lab directory");
        }

        for (int i = 0; i < 8; i++) {
            byte[] block = new byte[1024 * 1024];
            Arrays.fill(block, (byte) i);
            RETAINED.add(block);
        }

        var memory = ManagementFactory.getMemoryMXBean();
        var os = (OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
        var diagnostic = ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
        long heapBefore = memory.getHeapMemoryUsage().getUsed();
        long cpuBefore = os.getProcessCpuTime();
        long started = System.nanoTime();

        diagnostic.dumpHeap(output.toString(), true);

        long elapsed = System.nanoTime() - started;
        long cpuAfter = os.getProcessCpuTime();
        long heapAfter = memory.getHeapMemoryUsage().getUsed();

        System.out.printf(Locale.ROOT, "wall.ms=%.3f%n", elapsed / 1_000_000.0);
        if (cpuBefore >= 0 && cpuAfter >= cpuBefore) {
            System.out.printf(Locale.ROOT, "process.cpu.ms=%.3f%n",
                    (cpuAfter - cpuBefore) / 1_000_000.0);
        } else {
            System.out.println("process.cpu.ms=unavailable");
        }
        System.out.println("heap.before.bytes=" + heapBefore);
        System.out.println("heap.after.bytes=" + heapAfter);
        System.out.println("dump.bytes=" + Files.size(output));
        System.out.println("retained.blocks=" + RETAINED.size());
    }
}
```

Biên dịch và chạy bằng HotSpot JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 DumpCostProbe.java
java -Xms32m -Xmx64m "-Xlog:gc*,safepoint:file=dump-cost-gc.log:time,uptime,level,tags" DumpCostProbe
```

Một lần chạy kiểm chứng bằng HotSpot JDK 21 trên Windows, dùng G1 và giới hạn heap như lệnh trên, cho stdout sau:

```text
wall.ms=7.565
process.cpu.ms=15.625
heap.before.bytes=17432576
heap.after.bytes=17419544
dump.bytes=11400364
retained.blocks=8
```

**Đây là số đo của một lần chạy, không phải kết quả số học cố định.** Thời gian, mức dùng heap và kích thước tệp thay đổi theo JVM, GC, máy và lần chạy. `retained.blocks=8` phản ánh số mảng mà chương trình chủ động giữ.

Cách đọc kết quả:

- `wall.ms` đo lời gọi `dumpHeap`, chưa gồm truyền HTTP hay phân tích tệp.
- `process.cpu.ms` là mức tăng CPU time của toàn tiến trình trong cửa sổ đo; độ phân giải của công cụ có thể thô so với một thử nghiệm chỉ vài ms.
- `heap.before.bytes` và `heap.after.bytes` là hai điểm đo, không phải đỉnh RAM trong thao tác.
- `dump.bytes` là kích thước tệp tạo được, không phải RAM được cấp thêm.
- Tám mảng 1 MiB không đồng nghĩa tệp chỉ có 8 MiB: JVM còn các đối tượng khác và định dạng ghi có cấu trúc riêng.

Trong lần chạy này, GC log ghi nhận một `Pause Full (Heap Dump Initiated GC)` dài khoảng **1,445 ms** và safepoint `HeapDumper` có tổng thời gian khoảng **6,763 ms**. Điều đó minh họa vì sao chỉ nhìn thời gian GC sẽ bỏ qua phần thời gian khác của thao tác. Không suy rộng các số này sang heap nhiều GiB.

Chương trình không đo đỉnh RSS, không tạo tải HTTP và không mô phỏng quota container. Muốn đánh giá production, dùng phép đo ngoài tiến trình và tải đại diện; không tăng kích thước mảng tới sát giới hạn chỉ để ép ra một con số lớn hơn.

## 8. Đo cả đường Actuator mà không nhầm thời gian mạng

Mẫu dưới đây dành cho **một endpoint đã được bật, expose và bảo vệ quyền truy cập**, có HTTPS hợp lệ. Thay địa chỉ ví dụ bằng hệ thống thử đã xác định và dùng danh tính có quyền. Đây là thao tác tạo dump mới, không phải đọc một tệp tĩnh có sẵn.

```bash
curl --user dump-operator --fail \
  --connect-timeout 5 --max-time 180 \
  --dump-header heap-case-001.headers \
  --output heap-case-001.hprof \
  --write-out 'http=%{http_code} start=%{time_starttransfer}s total=%{time_total}s bytes=%{size_download} speed=%{speed_download}B/s\n' \
  https://ops.example.test/actuator/heapdump
```

Trong Windows PowerShell, dùng `curl.exe` và viết trên một dòng nếu không dùng shell hỗ trợ dấu xuống dòng Bash. Tài khoản chỉ có tên khiến curl hỏi mật khẩu thay vì đặt mật khẩu trực tiếp trong lệnh.

Các số curl cần đối chiếu với số liệu máy chủ:

| Số đo | Cách hiểu |
| --- | --- |
| `http_code` | Kết quả HTTP; phải xác minh thành công trước khi xem tệp là heap dump đầy đủ |
| `time_starttransfer` | Thời gian tới byte phản hồi đầu tiên, gồm nhiều khâu trước đó; không riêng thời gian tạo dump |
| `time_total` | Thời gian tổng phía client, gồm cả tạo và tải trong đường đi này |
| `size_download` | Số byte tải về; không chứng minh định dạng hoặc tính đầy đủ nếu chỉ nhìn một mình |
| `speed_download` | Tốc độ trung bình phía curl; không phải benchmark riêng của đường mạng khi còn thời gian tạo/chờ |

Mốc 180 giây là giới hạn chờ minh họa cho client, không phải một thời hạn hủy công việc JVM. Không bật cơ chế tự retry để tạo dump lặp lại khi timeout hoặc lỗi kết nối.

Trong lúc đo, đối chiếu trên **đúng instance**:

- CPU time/mức sử dụng CPU và hiện tượng bị giới hạn CPU.
- Heap, bộ nhớ tiến trình/container và số liệu GC/safepoint.
- Dung lượng trống ở nơi tạo tệp, tốc độ I/O và hàng đợi thiết bị.
- Độ trễ p95/p99 (phân vị 95/99), tỷ lệ lỗi, throughput và độ dài hàng đợi nghiệp vụ.
- Dấu hiệu tiến trình bị khởi động lại, OOM hoặc kiểm tra sức khỏe thất bại.

Nếu tệp tải chưa hoàn chỉnh hoặc công cụ không mở được, kiểm tra trạng thái thao tác và tệp phía máy chủ trước; không lập tức tạo thêm một dump mới.

Với thread dump, dùng một yêu cầu có `Accept: text/plain` hoặc JSON theo nhu cầu, lưu kết quả và đo tương tự. Không mặc định tạo một tệp tạm lớn phía máy chủ giống heap dump; nhưng việc thu thập, tạo kết quả, truyền và lưu vẫn có chi phí.

## 9. Ra quyết định trước, trong và sau thao tác

### Trước khi tạo

Xác định câu hỏi chẩn đoán trước khi chọn công cụ. Nếu nghi luồng chờ khóa, một heap dump lớn chưa chắc trả lời được câu hỏi; nếu cần tìm chuỗi tham chiếu giữ một tập đối tượng, thread dump lại thiếu bằng chứng.

Chọn một instance cụ thể, ghi lại phiên bản và cấu hình liên quan, kiểm tra ngân sách CPU/RAM/đĩa và xác định cách quan sát ảnh hưởng. Với dịch vụ có nhiều instance, cân nhắc giảm tải hoặc đưa riêng instance ra khỏi luồng phục vụ nếu quy trình vận hành cho phép.

Đặt điều kiện thành công và điều kiện dừng phát sinh thao tác mới: mức dự phòng đĩa, khả năng chịu độ trễ, số dump được giữ, người chịu trách nhiệm và thời gian lưu. Các ngưỡng phải đến từ yêu cầu dịch vụ và thử nghiệm, không từ một tỷ lệ “an toàn” chung.

### Trong khi tạo

Chỉ thực hiện số lần đã lập kế hoạch. Đừng dùng dump như một phép kiểm tra sức khỏe định kỳ; một HTTP GET vẫn có thể kích hoạt công việc rất nặng.

Nếu các chỉ số xấu đi, ngừng tạo thêm dump và áp dụng phương án giảm tải/ứng phó đã chuẩn bị. Không khẳng định đóng curl có thể ngắt an toàn một lần heap dump đang chạy. Việc chấm dứt cả JVM có hệ quả riêng và không phải nút hủy mặc định của thao tác chẩn đoán.

Theo dõi cả tài nguyên dùng chung: ghi dump trên cùng thiết bị với cơ sở dữ liệu hoặc log quan trọng có thể ảnh hưởng các tiến trình khác, dù CPU của ứng dụng chưa tăng rõ.

### Sau khi tạo

Xác minh mã HTTP hoặc kết quả lời gọi, kích thước, khả năng mở bằng công cụ đúng định dạng và nguồn instance/thời điểm. Lưu kèm số liệu quan sát để người phân tích biết dump được tạo trong điều kiện nào.

Chuyển tệp sang nơi phân tích được kiểm soát, kiểm tra việc dọn tệp tạm và dung lượng đã thu hồi. Một lần tải thành công không làm chi phí lưu trữ hoặc rủi ro lộ dữ liệu kết thúc: bản tải, bản nén và chỉ mục phân tích đều cần vòng đời rõ ràng.

## 10. Các kết luận dễ sai

| Nhận định | Cách đánh giá đúng hơn |
| --- | --- |
| “Heap còn trống nên dump không ảnh hưởng” | Xét cả pause, CPU, native memory, container và I/O |
| “Tệp 2 GiB nghĩa là cần thêm đúng 2 GiB RAM” | Phân biệt định dạng tệp, cơ chế truyền và bộ nhớ thực tế |
| “Xmx là dung lượng đĩa tối đa chắc chắn cần” | Dự trù bằng thử nghiệm và có dự phòng; không dùng Xmx làm cam kết định dạng |
| “Thread dump luôn miễn phí” | Đo theo số luồng, độ sâu stack, thông tin khóa và tần suất |
| “GC chỉ 100 ms nên người dùng chỉ bị ảnh hưởng 100 ms” | Đối chiếu toàn bộ safepoint, I/O và thời gian hồi phục nghiệp vụ |
| “Client timeout nghĩa là dump đã dừng” | Kiểm tra máy chủ; không tự tạo thêm yêu cầu |
| “Chỉ một dump được tạo một lúc nên chỉ có một tệp” | Xét cả các lần tải còn giữ tệp và các bản sao khác |
| “Đổi sang live=false là hết pause” | Chế độ chọn đối tượng không phải bảo đảm không gián đoạn |
| “Một lần thử trên laptop đủ để dự đoán production” | Cần workload, JVM, quota và lưu trữ đại diện |

## 11. Bài thực hành tự kiểm tra

1. Với dump dự trù 3 GiB, dự phòng tăng dữ liệu 1 GiB, mức trống cần giữ 2 GiB và 8 GiB đang trống, vì sao giữ hai dump đồng thời không đạt ngân sách?
2. Nếu tệp 3 GiB tải qua tốc độ hữu hiệu 40 MiB/s, phần truyền mất xấp xỉ bao lâu? Những chi phí nào chưa có trong số đó?
3. Vì sao `heap.after.bytes` nhỏ hơn `heap.before.bytes` không đủ để kết luận thao tác không gây áp lực bộ nhớ?
4. Chạy chương trình ở một thư mục mới, giữ lại stdout và GC log. Tách thời gian GC, safepoint và thời gian lời gọi; ghi rõ các số chưa đo được.
5. Khi một yêu cầu heap dump timeout, cần xác minh những gì trước khi thực hiện lần tiếp theo?

Đối chiếu: câu 1 cần `9 GiB`, lớn hơn `8 GiB`; câu 2 khoảng `76,8 giây` chỉ cho phần truyền theo giả định. Một đánh giá đầy đủ phải kết nối được tài nguyên tiêu thụ, nơi lưu tệp và ảnh hưởng lên công việc nghiệp vụ, thay vì chỉ ghi lại thời gian tải xong.
