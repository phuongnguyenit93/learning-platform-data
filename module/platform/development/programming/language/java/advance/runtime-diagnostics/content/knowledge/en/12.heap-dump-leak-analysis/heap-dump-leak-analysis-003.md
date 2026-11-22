# 12.3. Thu HPROF bằng `GC.heap_dump` hoặc `HotSpotDiagnosticMXBean`

Khi một ứng dụng Java có dấu hiệu tăng heap bất thường, liên tục `OutOfMemoryError: Java heap space`, hoặc giữ nhiều đối tượng sau GC, **heap dump** là ảnh chụp các đối tượng trong Java heap tại một thời điểm. Trên HotSpot, hai con đường chủ động lấy ảnh chụp HPROF phổ biến là **gửi lệnh `GC.heap_dump` bằng `jcmd` từ bên ngoài tiến trình** và **gọi `HotSpotDiagnosticMXBean.dumpHeap(...)` từ mã Java hoặc JMX**. Hai cách phục vụ các tình huống vận hành khác nhau nhưng đều tạo dữ liệu để phân tích tham chiếu và phân bổ đối tượng.

Sau bài này, bạn cần tự xác định đúng PID, chọn cách thu HPROF, hiểu tác động của GC và cờ `-all`/`live`, tạo một tệp dump hợp lệ trên máy chạy JVM, kiểm tra đầu ra và tránh những sai lầm thường gây mất bằng chứng hoặc ảnh hưởng dịch vụ.

## 1. HPROF lưu những gì và không lưu những gì?

**HPROF heap dump** là tệp nhị phân chứa thông tin về đồ thị đối tượng Java mà JVM ghi nhận: class, instance, array, quan hệ tham chiếu và các GC roots liên quan theo cách bộ tạo dump hỗ trợ. Công cụ như Eclipse Memory Analyzer (MAT) có thể đọc HPROF để xem histogram, dominator tree, retained size và đường tham chiếu tới GC roots.

- **Shallow size**: bộ nhớ của chính đối tượng/array, chưa tính các đối tượng mà nó tham chiếu.
- **Retained size**: phần dung lượng heap có thể được giải phóng nếu đối tượng đó và các đối tượng phụ thuộc không còn được giữ từ GC roots, theo mô hình phân tích của công cụ.
- **GC root**: điểm gốc để JVM truy vết tính reachable, chẳng hạn tham chiếu từ stack/thread, class/static field hoặc cơ chế JVM khác.

HPROF **không phải** ảnh chụp toàn bộ RAM của tiến trình. Nó không thay thế phép đo thread stacks, Metaspace, code cache, JNI/native allocations, direct buffer backing memory, RSS hoặc memory của container. Một object `DirectByteBuffer` có thể xuất hiện trong HPROF nhưng backing memory native của nó không vì thế được ghi nguyên vẹn như một Java array.

Một heap dump cũng **không tự chứng minh memory leak**. Cache đang nóng, batch lớn hoặc tải cao có thể tạo nhiều đối tượng hợp lệ. Để kết luận, cần xem chủ sở hữu tham chiếu và diễn biến qua thời gian ở điều kiện tải tương đương.

## 2. Chọn đúng cách thu dump

| Tiêu chí | `jcmd <PID> GC.heap_dump` | `HotSpotDiagnosticMXBean.dumpHeap(...)` |
| --- | --- | --- |
| Người kích hoạt | Người vận hành hoặc công cụ bên ngoài ứng dụng | Chính ứng dụng, tác vụ nội bộ, hoặc client JMX được cấp quyền |
| Có cần sửa code ứng dụng? | Không | Có nếu muốn tự gọi trong mã; có thể gọi MXBean sẵn có qua JMX |
| Yêu cầu thường gặp | JDK có `jcmd`, biết đúng PID, attach được tới JVM HotSpot | JVM có `jdk.management`/HotSpot MXBean và quyền thao tác |
| Chọn phạm vi đối tượng | Mặc định; hoặc `-all` để gồm đối tượng chưa thu gom | Tham số `live=true` hoặc `live=false` |
| Điều khiển đầu ra | Tên tệp và một số tùy chọn phụ thuộc phiên bản JDK (JDK 21 có `-gz`, `-overwrite`) | Đường dẫn tệp kết thúc bằng `.hprof`; API này không cung cấp tham số nén |
| Phù hợp | Sự cố phát sinh đột xuất trên tiến trình đang chạy | Luồng chẩn đoán tích hợp, trigger có kiểm soát, JMX |

Cả hai phương pháp có thể gây **dừng ứng dụng đáng kể** do thao tác toàn heap, đặc biệt với heap lớn. Chọn thời điểm và instance phù hợp trước khi chạy trên production. Không xem heap dump như một phép đọc metric nhẹ.

## 3. Chuẩn bị trước khi thu HPROF

1. **Xác nhận JVM/PID** của đúng service và đúng môi trường. Trong container hoặc Kubernetes, PID phía host có thể khác PID nhìn từ namespace của container. `jcmd -l` có thể không liệt kê JVM nằm trong một Docker process namespace khác.
2. **Chọn đường dẫn tuyệt đối trên máy hoặc filesystem nơi JVM đích chạy**, ví dụ `/var/tmp/diagnostics/service-12345.hprof`. Tên nên gồm service/PID/thời điểm để tránh đụng tệp cũ. Nếu gọi từ client JMX ở máy khác, file vẫn được ghi **tại máy của JVM đích**.
3. **Bảo đảm thư mục tồn tại và user chạy JVM có quyền ghi**, filesystem còn dung lượng trống đủ lớn. Dung lượng HPROF phụ thuộc số lượng đối tượng, không thể suy ra chính xác từ `-Xmx`; heap nhiều GiB có thể tạo file rất lớn. Với container, kiểm tra thêm dung lượng volume/ephemeral storage.
4. **Chấp nhận tác động vận hành**: dump có thể tạo safepoint/pause dài; cách mặc định của `jcmd GC.heap_dump` còn yêu cầu Full GC. Ghi lại thời điểm, PID, phiên bản Java, heap limit và bối cảnh tải để có thể giải thích snapshot.
5. **Bảo vệ dữ liệu**: HPROF có thể chứa string, token, dữ liệu phiên, thông tin cá nhân và payload ứng dụng. Hạn chế quyền đọc file, lưu ở kho được kiểm soát, chuyển an toàn và xóa theo chính sách sau khi phân tích.

Một lệnh dump chỉ thành công khi **JVM vẫn hoạt động và có thể thực hiện lệnh**. Nếu JVM đã bị hệ điều hành giết vì OOM, không thể quay lại lấy dump bằng cách attach vào PID đã mất.

## 4. Cách A — `jcmd GC.heap_dump` trên JVM đang chạy

### Bước 1: Tìm và xác nhận PID

Trên máy có JDK và quyền truy cập thích hợp:

~~~bash
jcmd -l
~~~

Từ kết quả, xác định PID của **đúng tiến trình Java**. Đối chiếu thêm process command line, tên service và môi trường, vì nhiều JVM có thể chạy cùng một main class. Trong container, thực hiện công cụ trong môi trường có thể nhìn thấy PID và attach đúng JVM.

Giả sử PID cần kiểm tra là **12345** (chỉ là ví dụ; phải thay bằng PID thực tế):

~~~bash
jcmd 12345 help GC.heap_dump
jcmd 12345 VM.command_line
jcmd 12345 GC.heap_info
~~~

Lệnh `help GC.heap_dump` cho biết cú pháp/tùy chọn mà **JVM đích** hỗ trợ; `VM.command_line` và `GC.heap_info` giúp nhận diện phiên chạy và heap hiện tại. `jcmd` cần chạy trên cùng máy, với effective user/group phù hợp và cơ chế attach hoạt động. Tên lệnh/tùy chọn có thể thay đổi theo JDK/JVM.

### Bước 2: Lấy dump mặc định

Ví dụ trên Linux với đường dẫn tuyệt đối đã có thư mục chứa:

~~~bash
jcmd 12345 GC.heap_dump filename=/var/tmp/diagnostics/service-12345.hprof
~~~

Đối với **HotSpot JDK 21**, đây là lệnh tạo HPROF; **nếu không chọn `-all`, JVM yêu cầu một Full GC trước khi ghi**. Các đối tượng không còn reachable có thể bị thu gom trước snapshot. Điều này hữu ích nếu muốn quan sát những đối tượng còn bị giữ sau GC nhưng cũng thay đổi trạng thái heap tại thời điểm đo.

Đường dẫn trên là đường dẫn của tiến trình **đích**, không phải vị trí mà người vận hành đang đứng khi gọi `jcmd`. Khi chạy từ máy host/container khác, hãy xác định rõ mount và namespace; file có thể nằm trong filesystem của container.

### Bước 3: Khi nào dùng `-all`?

~~~bash
jcmd 12345 GC.heap_dump -all filename=/var/tmp/diagnostics/service-12345-all.hprof
~~~

Theo `jcmd` JDK 21, `-all` gồm cả các đối tượng **chưa được thu gom dù đã unreachable**, và công cụ **không yêu cầu Full GC** trước khi dump. Đây là chế độ hữu ích nếu cần giữ thêm bằng chứng về garbage tồn tại trong heap tại thời điểm đó; đổi lại dữ liệu có thể nhiều và nhiễu hơn khi phân tích leak. `-all` **không có nghĩa** là không có pause hoặc không có bất kỳ hoạt động GC nào vì lý do khác.

Không so sánh số lượng đối tượng giữa snapshot mặc định và snapshot `-all` như thể cả hai dùng cùng một định nghĩa “live set”.

### Bước 4: Nén HPROF ngay khi ghi (tùy chọn JDK hỗ trợ)

HotSpot JDK 21 có tham số `-gz`. Ví dụ:

~~~bash
jcmd 12345 GC.heap_dump -gz=1 filename=/var/tmp/diagnostics/service-12345.hprof.gz
~~~

Mức `1` ưu tiên tốc độ nén; mức `9` nén mạnh hơn nhưng thường tốn thêm CPU/thời gian. Kiểm tra trình phân tích của bạn có mở trực tiếp `.hprof.gz` hay phải giải nén trước. Không mặc định mọi JDK/VM hỗ trợ cùng tùy chọn; luôn kiểm tra `help GC.heap_dump` của PID đích.

JDK 21 còn có `-overwrite` nhưng mặc định không ghi đè tệp đã có. Trong thao tác điều tra, **ưu tiên tên tệp mới** để không phá hủy một snapshot cũ.

### Bước 5: Xác minh artifact

Trên máy hoặc volume nơi JVM đã ghi tệp:

~~~bash
ls -lh /var/tmp/diagnostics/service-12345.hprof
~~~

Đảm bảo file tồn tại, có kích thước khác 0, thời điểm cập nhật phù hợp và công cụ phân tích HPROF mở được. Thông báo `Heap dump file created` của `jcmd` là tín hiệu thành công ban đầu; việc mở được bằng MAT hoặc công cụ tương đương là bước xác nhận hữu ích hơn. Nếu đã dùng `-gz`, đối chiếu tên tệp nén tương ứng.

## 5. Cách B — gọi `HotSpotDiagnosticMXBean.dumpHeap`

`com.sun.management.HotSpotDiagnosticMXBean` nằm trong module `jdk.management` trên HotSpot JDK hiện đại. Phương thức:

~~~java
void dumpHeap(String outputFile, boolean live) throws IOException;
~~~

Ý nghĩa:

- `outputFile`: đường dẫn tệp trên **máy chạy JVM đích**; nếu là đường dẫn tương đối, nó được tính theo working directory mà JVM đích khởi chạy. Dùng đường dẫn tuyệt đối để tránh nhầm.
- `live=true`: chỉ đưa vào các đối tượng reachable (“live”) theo định nghĩa API; có thể kích hoạt công việc GC để xác định tập đối tượng này.
- `live=false`: không giới hạn dump chỉ ở đối tượng còn reachable, nên có thể gồm đối tượng chưa được thu gom.
- Đường dẫn phải có hậu tố **`.hprof`**; tệp đã tồn tại, không tạo/ghi được hoặc hết dung lượng sẽ gây `IOException`. Không có tham số nén hay tùy chọn `-overwrite` trong phương thức này.
- Interface này **đặc thù HotSpot**, không phải một hợp đồng bắt buộc được mọi JVM triển khai. Khi không khả dụng, không cố giả định có thể gọi nó trên runtime khác.

Có thể lấy MXBean trong cùng tiến trình:

~~~java
HotSpotDiagnosticMXBean diagnostic =
        ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
diagnostic.dumpHeap("/var/tmp/diagnostics/app-live.hprof", true);
~~~

Đây là **đoạn trích minh họa**; ví dụ chương trình hoàn chỉnh ngay bên dưới bao gồm imports, kiểm tra MXBean và xử lý đường dẫn. Không nên gắn việc tạo heap dump vào request HTTP thông thường: một request có thể kích hoạt pause dài, chiếm disk hoặc tạo nhiều snapshot nếu lặp ngoài ý muốn. Nếu tích hợp vào ứng dụng, hãy dùng trigger chẩn đoán có xác thực, giới hạn tần suất và vị trí ghi rõ ràng.

Ngoài gọi trực tiếp trong code, MXBean thường được đăng ký dưới ObjectName `com.sun.management:type=HotSpotDiagnostic` và có thể được công cụ JMX như JConsole kích hoạt nếu đã thiết lập truy cập quản trị an toàn. **Đường dẫn được nhập qua JMX remote vẫn nằm trên máy ứng dụng, không nằm trên máy chạy JConsole.**

## 6. Ví dụ Java 17+ tự chạy để thử cả hai cách

Tạo file **`HprofDemo.java`**. Chương trình giữ tham chiếu tới tám mảng, có chế độ `mxbean` để tự ghi HPROF và chế độ `wait` để người học attach `jcmd` từ terminal khác.

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class HprofDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        if (args.length == 2 && "mxbean".equals(args[0])) {
            HotSpotDiagnosticMXBean diagnostic =
                    ManagementFactory.getPlatformMXBean(
                            HotSpotDiagnosticMXBean.class);
            if (diagnostic == null) {
                throw new IllegalStateException("HotSpot MXBean unavailable");
            }

            Path destination = Path.of(args[1]).toAbsolutePath();
            diagnostic.dumpHeap(destination.toString(), true);
            System.out.println("Created: " + destination.getFileName());
            return;
        }

        if (args.length == 1 && "wait".equals(args[0])) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            Thread.sleep(180_000L);
            System.out.println("Wait finished");
            return;
        }

        System.out.println("Usage: mxbean <new-file.hprof> | wait");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên (HotSpot):

~~~bash
javac HprofDemo.java
~~~

**Thử MXBean** trong thư mục có quyền ghi, bảo đảm tên file chưa tồn tại:

~~~bash
java -Xms32m -Xmx128m HprofDemo mxbean demo-live-001.hprof
~~~

Khi thành công, stdout phần chương trình in là:

~~~text
Created: demo-live-001.hprof
~~~

Sau đó kiểm tra file `demo-live-001.hprof` ở thư mục chạy chương trình. Nếu chạy lại với cùng tên, API có thể ném `IOException` vì file đã tồn tại; đổi tên mới thay vì ghi đè snapshot.

**Thử `jcmd`** bằng hai terminal:

Terminal A:

~~~bash
java -Xms32m -Xmx128m HprofDemo wait
~~~

Chương trình in `PID: <số PID thực tế>`, rồi tồn tại khoảng ba phút. Ở terminal B, thay **12345** bằng PID vừa thấy và chọn một đường dẫn mới có quyền ghi:

~~~bash
jcmd 12345 GC.heap_dump filename=/var/tmp/diagnostics/hprof-demo-12345.hprof
~~~

Nếu dùng Windows, có thể chỉ định đường dẫn như `C:/dumps/hprof-demo-12345.hprof` sau khi tạo thư mục và cấp quyền ghi. Đầu ra thực tế của `jcmd` gồm thông tin PID và thông báo từ JVM, không có chuỗi stdout cố định giống nhau trên mọi JDK.

Vì `RETAINED` là static field giữ các mảng, chúng có thể xuất hiện trong object graph và được truy từ đường đi GC roots phù hợp; cách bộ phân tích thể hiện shallow/retained size còn tùy phiên bản JVM và dữ liệu dump. Kết thúc chế độ `wait` sau ba phút là kết thúc chương trình demo, không phải bằng chứng của OOM.

## 7. Hiểu rõ `-all` và `live`: thời điểm thu ảnh cũng thay đổi kết quả

| Cách gọi | Đối tượng được nhắm tới | Liên quan GC |
| --- | --- | --- |
| `jcmd ... GC.heap_dump filename=...` | Các đối tượng còn lại trong snapshot sau bước GC được yêu cầu | JDK 21 yêu cầu Full GC nếu không có `-all` |
| `jcmd ... GC.heap_dump -all filename=...` | Gồm cả đối tượng unreachable chưa được reclaim | Không yêu cầu Full GC cho mục đích dump |
| `dumpHeap(path, true)` | Chỉ đối tượng live/reachable | Có thể yêu cầu thu gom để xác định live set |
| `dumpHeap(path, false)` | Không lọc chỉ live objects | Không thể dùng như bảo đảm không có safepoint |

**Ví dụ:** ứng dụng vừa ngừng giữ tham chiếu tới một mảng 100 MiB, nhưng GC chưa chạy. Snapshot `-all` có thể ghi nhận mảng đó, trong khi ảnh live-only thu sau Full GC có thể không còn mảng. Nếu chỉ nhìn histogram rồi kết luận “leak 100 MiB” từ ảnh `-all` sẽ sai. Ngược lại, khi điều tra chi phí cấp phát hoặc nhiều đối tượng tạm, nhìn thấy unreachable objects có thể mang ý nghĩa riêng.

Chế độ live-only thường phù hợp hơn khi tìm **đối tượng đang bị giữ**; dùng chế độ all khi có câu hỏi chẩn đoán cụ thể và hiểu tác động. Một snapshot sau Full GC có thể không phản ánh chính xác đỉnh heap ngay trước sự kiện.

## 8. Mở HPROF và trả lời đúng câu hỏi về leak

Trình tự gợi ý với Eclipse MAT hoặc công cụ đọc HPROF tương đương:

1. Mở đúng file HPROF, ghi lại thời điểm, JVM version, PID, cờ dump (live hay all) và tải khi chụp.
2. Xem **Histogram** để biết loại đối tượng và tổng shallow size. Đếm nhiều `byte[]` hay `String` chỉ là tín hiệu, chưa chỉ ra ai giữ.
3. Xem **Dominator Tree** và **Retained Heap** để tìm đối tượng hoặc cấu trúc giữ nhiều dung lượng.
4. Tìm **Path to GC Roots** cho nghi phạm, đặc biệt các static fields, collection/cache, listener, thread-local, class loader hoặc hàng đợi.
5. Đối chiếu với ý định thiết kế: cache có giới hạn không, dữ liệu có vòng đời rõ không, thread/request đã kết thúc chưa, class loader cũ còn được giữ không?
6. Nếu có thể, so **nhiều snapshot sau GC ở tải tương đương** và GC metrics theo thời gian. “Một object còn reachable” chưa đủ chứng minh không bao giờ được giải phóng.

Giới hạn quan trọng: retained size là thuộc tính của **đồ thị tham chiếu tại thời điểm dump**. Nó không cộng trực tiếp với native memory để ra RSS; cũng không phải dự đoán chắc chắn rằng GC sẽ thu hồi từng ấy byte ngay lập tức.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `Could not attach`, `AttachNotSupportedException`, permission denied | Sai PID, user/group khác, JVM không cho attach, process đã thoát, container namespace khác | Xác nhận PID của JVM, quyền user, trạng thái process, cơ chế attach và namespace |
| `Unknown diagnostic command` hoặc không có tùy chọn muốn dùng | JDK/JVM đích khác phiên bản hoặc không hỗ trợ | Chạy `jcmd 12345 help GC.heap_dump` trên chính JVM đích |
| File không xuất hiện trên máy người gọi | Dump được ghi trong filesystem của JVM đích/container | Kiểm tra working directory, đường dẫn tuyệt đối, mount/volume bên trong tiến trình |
| `IOException`: file exists/cannot write | MXBean không ghi đè, file name không mới, thiếu quyền, thư mục chưa có hoặc hết disk | Chọn đường dẫn `.hprof` mới, tạo thư mục hợp lệ, kiểm tra quota/dung lượng/quyền |
| `IllegalArgumentException` từ MXBean | Thường do đường dẫn không có đuôi `.hprof` | Đổi tên đầu ra thành tệp `.hprof` (không dùng `.hprof.gz` trực tiếp với phương thức này) |
| Service bị chậm hoặc timeout khi dump | Heap lớn, Full GC/heap walk kéo dài, CPU/I/O bận | Ưu tiên instance phụ hoặc thời điểm phù hợp; đo thời gian thao tác; không kích hoạt nhiều dump đồng thời |
| HPROF mở được nhưng không thấy nghi phạm | Đã Full GC nên object unreachable biến mất; snapshot không đúng thời điểm; nghi vấn nằm ở native/off-heap | Xem cờ live/all, chụp đúng tải, kết hợp heap/GC trend và NMT/OS nếu nghi native |
| `jcmd` không thu được sau khi JVM chết | PID không còn tồn tại, hoặc process bị OOMKilled trước khi attach | Chuẩn bị phương án chụp trước khi crash; nếu phù hợp có thể dùng `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath=...` từ lúc khởi động |

**Lưu ý về tự động dump khi OOME:** cờ `-XX:+HeapDumpOnOutOfMemoryError` là một phương án dự phòng khác, không thay thế hai kỹ thuật chủ động trong bài. Nó chỉ có thể hoạt động khi JVM còn đủ khả năng tạo dump trong tình huống lỗi; container bị OS giết đột ngột có thể không tạo file.

## 10. Checklist ngắn trước khi áp dụng trên môi trường thực

- Tôi đã xác nhận **đúng JVM/PID** và quyền truy cập.
- Tôi biết dump cần **live objects** hay **all objects**, hiểu thao tác có thể gây Full GC/pause.
- Đường dẫn **trên máy/container chạy JVM** là tuyệt đối, thư mục tồn tại, file chưa có và còn đủ dung lượng.
- Tôi đã chọn phương thức phù hợp: `jcmd` cho thao tác ngoài tiến trình; `HotSpotDiagnosticMXBean` cho điều khiển qua mã/JMX.
- Tôi có cách kiểm tra HPROF đã ghi và mở được, đồng thời bảo vệ dữ liệu nhạy cảm trong file.
- Khi phân tích, tôi tìm **ai đang giữ object** và đối chiếu lịch sử/tải, không kết luận leak chỉ từ kích thước file hoặc một histogram.

**Điểm cốt lõi:** `GC.heap_dump` và `HotSpotDiagnosticMXBean.dumpHeap` đều tạo snapshot **Java heap** ở định dạng HPROF, nhưng chúng khác nhau ở cách kích hoạt và cách chọn đối tượng cần đưa vào ảnh. Hãy ghi rõ **PID + thời điểm + đường dẫn + chế độ live/all**, vì bốn thông tin đó quyết định giá trị của bằng chứng khi điều tra rò rỉ.

## Tài liệu tham khảo chính thức

- Oracle JDK 21, *The jcmd Command* — cú pháp `GC.heap_dump`, `-all`, `-gz`, `-overwrite` và tác động Full GC: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API, *HotSpotDiagnosticMXBean* — `dumpHeap(outputFile, live)`, đường dẫn, hậu tố file, ngoại lệ: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html
- Oracle JDK 21, *Troubleshoot Memory Leaks* — thu dump bằng `jcmd`, JMX và phương án OOME: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
