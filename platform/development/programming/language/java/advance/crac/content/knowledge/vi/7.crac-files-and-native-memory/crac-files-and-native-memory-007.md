# MappedByteBuffer, bộ nhớ ngoài heap và giới hạn theo bản dựng

Java có nhiều cách lưu dữ liệu ngoài Java heap: direct byte buffer, vùng nhớ native do JNI cấp phát, file được ánh xạ vào bộ nhớ và các vùng nhớ được quản lý bằng Foreign Function & Memory API. Những vùng này không được Garbage Collector quản lý giống object heap thông thường, nhưng chúng vẫn nằm trong không gian địa chỉ của tiến trình hoặc phụ thuộc vào tài nguyên bên ngoài tiến trình.

Điều này quan trọng với CRaC (Coordinated Restore at Checkpoint). Checkpoint lưu trạng thái của một tiến trình đang chạy, bao gồm nhiều vùng nhớ native, nhưng khả năng khôi phục còn phụ thuộc vào cách vùng nhớ được tạo, file backing, checkpoint engine, hệ điều hành và bản dựng JDK. Một vùng nhớ direct được cấp phát ẩn danh có đặc tính khác với một vùng MappedByteBuffer đang ánh xạ file trên filesystem.

Khi thiết kế ứng dụng CRaC, cần phân biệt ba câu hỏi:

1. Dữ liệu nằm ở đâu: Java heap, native memory hay file-backed mapping?
2. Ai sở hữu vòng đời của vùng nhớ: Garbage Collector, Arena, file channel hay thư viện native?
3. Sau restore, vùng nhớ có thể tiếp tục dùng an toàn không, hay phải giải phóng và tạo lại?

## 1. Heap, direct memory và memory mapping

### 1.1 Java heap

Các object Java thông thường được cấp phát trên heap. Garbage Collector theo dõi khả năng truy cập của object và thu hồi vùng nhớ khi object không còn được sử dụng.

Ví dụ:

~~~java
byte[] data = new byte[1024 * 1024];
~~~

Mảng byte trên nằm trong heap. Khi checkpoint, trạng thái heap là một phần của trạng thái tiến trình được lưu. Sau restore, object và dữ liệu của nó tiếp tục tồn tại theo trạng thái đã checkpoint.

Tuy nhiên, nếu object giữ một tham chiếu tới tài nguyên bên ngoài như file, socket hoặc native pointer, việc object còn tồn tại không chứng minh tài nguyên bên ngoài vẫn hợp lệ.

### 1.2 Direct buffer và bộ nhớ ngoài heap

NIO cung cấp ByteBuffer.allocateDirect() để tạo buffer có vùng dữ liệu nằm ngoài Java heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
~~~

Object ByteBuffer vẫn là object Java trên heap, nhưng phần dữ liệu của nó được cấp phát ở vùng nhớ native. JVM có thể sử dụng vùng này để thực hiện I/O hiệu quả hơn, đặc biệt với các thao tác native có thể truy cập trực tiếp vào vùng nhớ đó.

Một direct buffer có hai phần cần phân biệt:

- Object Java quản lý metadata như capacity, position, limit và reference tới vùng dữ liệu.
- Vùng native memory chứa bytes thực tế.

Garbage Collector nhìn thấy object wrapper. Cơ chế cleanup của JDK có thể giải phóng vùng native khi buffer không còn được tham chiếu và cleaner được thực thi. Tuy nhiên, ByteBuffer không cung cấp một phương thức close() công khai để ứng dụng giải phóng direct memory một cách xác định.

Direct memory không phải là một kho dữ liệu độc lập bên ngoài tiến trình. Vùng nhớ này thuộc không gian địa chỉ của tiến trình, nên checkpoint engine có thể phải lưu các trang nhớ đó cùng các vùng nhớ khác. Dù vậy, các native handle hoặc cấu trúc bên ngoài mà thư viện dùng để quản lý vùng nhớ vẫn cần được xem xét riêng.

### 1.3 File-backed memory mapping

MappedByteBuffer là một direct byte buffer đại diện cho một vùng file được ánh xạ vào không gian địa chỉ của tiến trình. Java tạo mapping qua FileChannel.map().

~~~java
try (FileChannel channel = FileChannel.open(
        Path.of("records.dat"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE,
            0,
            1024 * 1024);

    mapped.putInt(0, 42);
    mapped.force();
}
~~~

Dữ liệu trong MappedByteBuffer được truy cập như bộ nhớ, nhưng vùng nhớ có quan hệ với một file trên filesystem. Hệ điều hành chịu trách nhiệm ánh xạ các trang file vào không gian địa chỉ của tiến trình.

Đóng FileChannel không đồng nghĩa mapping đã bị hủy. Theo hợp đồng của MappedByteBuffer, mapping tiếp tục hợp lệ cho tới khi buffer được Garbage Collector thu hồi. Vì vậy, MappedByteBuffer có vòng đời khác với FileChannel dùng để tạo ra nó.

Một mapping file-backed phụ thuộc vào:

- File backing còn tồn tại và có thể truy cập.
- Quyền đọc/ghi phù hợp với chế độ mapping.
- File không bị thay thế hoặc thay đổi theo cách làm sai lệch trạng thái ứng dụng.
- Hệ điều hành và checkpoint engine có thể khôi phục loại mapping đó.
- Các trang dữ liệu đã thay đổi được đồng bộ theo yêu cầu của ứng dụng.

### 1.4 So sánh các loại vùng nhớ

| Loại vùng nhớ | Nơi chứa dữ liệu | Quản lý vòng đời thường gặp | Điểm cần chú ý khi checkpoint |
|---|---|---|---|
| byte[] hoặc object heap | Java heap | Garbage Collector | Trạng thái object được lưu trong ảnh |
| ByteBuffer.allocateDirect() | Native memory ẩn danh | Cleaner/GC | Vùng native có thể được lưu như bộ nhớ tiến trình; wrapper và thư viện native phải còn nhất quán |
| MappedByteBuffer | File-backed mapping | Mapping thường tồn tại tới khi buffer được GC | File backing và mapping phải tương thích khi restore |
| MemorySegment.allocateNative() | Native memory | Arena | Có thể đóng Arena xác định trước checkpoint và cấp phát lại sau restore |
| MemorySegment ánh xạ file | File-backed mapping | Arena | Đóng Arena để giải phóng mapping rồi ánh xạ lại sau restore |
| Native allocation qua JNI | Native memory hoặc tài nguyên OS | Thư viện native | Cần lifecycle hook và chính sách riêng của thư viện |

Không nên gom tất cả các loại này vào một khái niệm chung là off-heap rồi giả định chúng có cùng cách checkpoint. Direct allocation, mapping và native handle có semantics khác nhau.

## 2. MappedByteBuffer hoạt động như thế nào?

### 2.1 FileChannel.map()

FileChannel.map() tạo một vùng nhớ liên kết với một đoạn của file. Tham số gồm:

- MapMode: chế độ READ_ONLY, READ_WRITE hoặc PRIVATE.
- Position: offset bắt đầu trong file.
- Size: số byte cần ánh xạ.

Vùng được trả về có thể được đọc hoặc ghi qua các thao tác ByteBuffer.

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0,
        fileSize);
~~~

Với READ_ONLY, ứng dụng chỉ đọc nội dung mapping. Với READ_WRITE, thay đổi trong mapping có thể được ghi trở lại file. Với PRIVATE, thay đổi tạo bản sao riêng theo semantics copy-on-write và không được xem là cập nhật file dùng chung.

Mapping không phải là một bản sao Java array thông thường. Hệ điều hành có thể nạp các trang từ file khi ứng dụng truy cập chúng. Một trang chưa được chạm tới có thể chưa nằm trong RAM vật lý.

### 2.2 Page fault và bộ nhớ vật lý

Khi ứng dụng truy cập một địa chỉ trong vùng mapping mà trang tương ứng chưa được nạp vào RAM, CPU có thể phát sinh page fault. Kernel xử lý fault và nạp trang cần thiết từ file hoặc backing store.

Vì vậy:

- Dung lượng mapping có thể lớn hơn lượng dữ liệu đang resident trong RAM.
- Việc tạo mapping chưa có nghĩa toàn bộ file đã được đọc.
- Truy cập lần đầu có thể phát sinh I/O và làm tăng latency.
- load() có thể yêu cầu hệ điều hành nạp các trang, nhưng đây là best effort.
- isLoaded() chỉ là một gợi ý về khả năng trang đang resident, không phải cam kết.

Có thể dùng load() trong warm-up để giảm page fault sau này, nhưng thao tác này có thể tạo nhiều I/O và áp lực bộ nhớ. Khi checkpoint, việc đã gọi load() không thay thế yêu cầu kiểm tra backing file và tính nhất quán của mapping.

### 2.3 Ghi dữ liệu và force()

Với mapping READ_WRITE, ghi vào buffer làm thay đổi trang nhớ được ánh xạ. Hệ điều hành có thể ghi các trang dirty xuống file theo chính sách của nó. Nếu ứng dụng cần chủ động yêu cầu đồng bộ, hãy gọi force():

~~~java
mapped.putLong(128, 9001L);
mapped.force();
~~~

force() yêu cầu các thay đổi trong vùng mapping được ghi xuống thiết bị lưu trữ. Theo hợp đồng API, với file trên thiết bị lưu trữ cục bộ, khi force() trả về thì các thay đổi kể từ lúc tạo mapping hoặc lần force gần nhất đã được ghi xuống thiết bị.

force() không hủy mapping và không đóng file channel. Nó cũng không biến file thành dữ liệu bất biến. Một tiến trình khác vẫn có thể sửa file, và semantics của thay đổi đồng thời phụ thuộc hệ điều hành.

Nếu checkpoint cần lưu một trạng thái file nhất quán, hãy xác định rõ thứ tự:

1. Ngừng thread đang ghi vào mapping.
2. Hoàn tất các thao tác ghi.
3. Gọi force() khi cần đồng bộ nội dung.
4. Lưu metadata nghiệp vụ như version, offset hoặc checksum.
5. Giải phóng mapping theo cơ chế được hỗ trợ.
6. Tạo checkpoint.

### 2.4 Mapping và FileChannel có vòng đời riêng

Đoạn code sau đóng channel khi ra khỏi try block:

~~~java
MappedByteBuffer mapped;

try (FileChannel channel = FileChannel.open(
        Path.of("records.dat"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, 4096);
}

// Channel đã đóng, nhưng mapping vẫn còn hiệu lực.
int value = mapped.getInt(0);
~~~

Đây là hành vi có chủ đích của API. Mapping có vòng đời riêng và tiếp tục tồn tại sau khi channel đóng.

Điều này hữu ích trong ứng dụng bình thường, nhưng tạo ra một vấn đề cho checkpoint: chỉ đóng FileChannel trong beforeCheckpoint chưa chắc đã giải phóng mapping. File mapping vẫn có thể còn trong virtual memory area của tiến trình và phụ thuộc vào file backing khi restore.

## 3. Tác động của MappedByteBuffer tới CRaC

CRaC tạo ảnh của trạng thái tiến trình và khôi phục tiến trình từ ảnh đó. Checkpoint engine phải xử lý không chỉ heap mà còn các vùng nhớ trong không gian địa chỉ, descriptor và những tài nguyên liên quan.

### 3.1 Mapping là VMA của tiến trình

Trên Linux, một memory mapping được thể hiện trong vùng địa chỉ ảo của tiến trình. Có thể xem các vùng mapping qua:

~~~bash
cat /proc/<PID>/maps
~~~

Hoặc xem thông tin chi tiết hơn:

~~~bash
cat /proc/<PID>/smaps
~~~

Một mapping file-backed thường hiển thị đường dẫn file backing, offset và quyền truy cập. Mapping anonymous không có file backing theo cách tương tự.

Checkpoint engine có thể cần ghi nhận thông tin VMA và tái tạo mapping tại restore. Với mapping file-backed, engine có thể cần mở lại hoặc xác minh file backing. Ảnh checkpoint không phải là bản sao đầy đủ của filesystem bên ngoài.

### 3.2 File backing có thể thay đổi giữa checkpoint và restore

Giả sử ứng dụng ánh xạ file /data/index.bin. Sau checkpoint, file có thể bị:

- Xóa.
- Đổi tên hoặc thay thế bằng file khác.
- Thay đổi kích thước.
- Thay đổi nội dung.
- Chuyển mount hoặc thay đổi quyền truy cập.
- Không còn được mount tại đường dẫn cũ trong container mới.

Nếu restore yêu cầu file backing nhưng file không thể truy cập hoặc không tương thích, quá trình restore có thể thất bại. Một số checkpoint engine có thể báo lỗi native trong khi Java stack trace chỉ cho biết restore thất bại ở mức tổng quát.

Không nên giả định rằng file-backed mapping sẽ tự động mang theo một bản sao độc lập của file vào checkpoint image. Hãy quản lý file backing như một dependency bên ngoài: đảm bảo nó tồn tại, có quyền phù hợp và giữ đúng version ở môi trường restore.

### 3.3 Mapping còn sống dù channel đã đóng

Một lỗi thường gặp là đóng FileChannel trong callback rồi cho rằng tài nguyên đã được giải phóng. Nếu MappedByteBuffer vẫn còn được tham chiếu, mapping vẫn có thể còn hiệu lực.

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {
    channel.close();
    channel = null;
    // mappedBuffer vẫn được tham chiếu và có thể giữ mapping.
}
~~~

Gán channel về null không ảnh hưởng tới mapping được đại diện bởi MappedByteBuffer. Gán mappedBuffer về null cũng không bảo đảm mapping được unmap ngay, vì việc thu hồi phụ thuộc Garbage Collector.

System.gc() chỉ là yêu cầu GC, không phải API unmap có bảo đảm. Dựa vào GC để giải phóng mapping ngay trước checkpoint có thể khiến hành vi không xác định theo thời điểm.

### 3.4 File descriptor và memory mapping là hai thứ khác nhau

Ở cấp hệ điều hành, một mapping đã được thiết lập có thể tiếp tục tồn tại sau khi descriptor ban đầu dùng cho mmap() được đóng, vì kernel đã tạo VMA tham chiếu tới file. Tuy nhiên, implementation của JDK có thể giữ một descriptor nội bộ hoặc descriptor được duplicate trong mapping/cleaner để quản lý vòng đời. Vì vậy, đóng FileChannel không làm mapping biến mất và cũng không nên suy luận số FD nội bộ chỉ từ descriptor mà ứng dụng đã mở.

Do đó:

- Kiểm tra số FD còn mở chưa chắc phát hiện mọi mapping còn tồn tại.
- Đóng channel chưa chắc giải phóng vùng mapping.
- Một mapping vẫn có thể phụ thuộc file backing trong restore.
- Resource policy dành cho file descriptor không mặc nhiên quản lý mọi VMA.
- Cần xem cả /proc/PID/maps và /proc/PID/smaps khi điều tra.

Điều này giải thích vì sao ứng dụng có thể không còn file descriptor của file nhưng restore vẫn thất bại khi checkpoint engine cần truy cập mapped file.

## 4. Off-heap memory có được lưu trong checkpoint không?

Cần phân biệt native memory thuộc không gian địa chỉ của tiến trình với tài nguyên nằm ngoài tiến trình.

### 4.1 Vùng nhớ native thuộc tiến trình

DirectByteBuffer, vùng nhớ được cấp phát bằng malloc hoặc các vùng anonymous mapping thường nằm trong không gian địa chỉ của tiến trình. Checkpoint engine có thể lưu các trang nhớ thuộc tiến trình, bao gồm cả những vùng không nằm trong Java heap.

Vì vậy, dữ liệu off-heap có thể được giữ trong checkpoint image. Điều này không có nghĩa mọi native resource đều được tự động khôi phục.

Ví dụ:

- Một mảng byte được cấp phát bằng native allocator là vùng nhớ.
- Một con trỏ tới vùng nhớ đó là địa chỉ trong tiến trình.
- Một file descriptor là handle do kernel quản lý.
- Một socket là trạng thái giao tiếp do kernel và peer cùng quản lý.
- Một GPU context hoặc device handle có thể phụ thuộc driver và thiết bị.

Checkpoint engine xử lý memory pages không đồng nghĩa nó có thể tái tạo mọi trạng thái kernel, thiết bị hoặc dịch vụ từ xa.

### 4.2 Native pointer và thư viện JNI

Thư viện JNI có thể giữ pointer tới vùng native, struct, thread-local data hoặc handle do thư viện quản lý. Nếu checkpoint engine khôi phục vùng nhớ tại đúng địa chỉ cần thiết, pointer có thể vẫn trỏ tới vùng đó trong một số môi trường. Tuy nhiên, tính đúng đắn còn phụ thuộc:

- Allocator và metadata quản lý vùng nhớ.
- Native thread và TLS.
- File descriptor hoặc socket mà thư viện đang giữ.
- Callback hoặc signal handler do thư viện đăng ký.
- Driver hoặc thiết bị mà thư viện sử dụng.
- ABI, CPU architecture và phiên bản thư viện ở môi trường restore.

Không nên thiết kế ứng dụng dựa trên giả định rằng mọi pointer native đều có thể dùng lại an toàn. Thư viện native cần có hướng dẫn hoặc hỗ trợ checkpoint/restore rõ ràng.

### 4.3 DirectByteBuffer và giới hạn bộ nhớ

DirectByteBuffer sử dụng native memory. Dung lượng này không được tính như Java heap, nhưng vẫn tiêu thụ RAM và có thể làm tăng kích thước checkpoint image.

Một số tham số và công cụ liên quan:

| Cơ chế | Tác dụng | Giới hạn |
|---|---|---|
| -Xmx | Giới hạn Java heap tối đa | Không phải giới hạn tổng native memory |
| -XX:MaxDirectMemorySize | Giới hạn NIO direct-buffer allocations theo cách JVM hạch toán | Không phải giới hạn tổng native memory của tiến trình, JNI/malloc hoặc mapping do native code tự tạo; cách hạch toán mapped buffer cần đối chiếu implementation JDK |
| BufferPoolMXBean | Quan sát pool direct và mapped buffer | Không thay thế công cụ đo RSS và native memory tổng thể |
| Native Memory Tracking | Theo dõi nhiều nhóm native allocation do HotSpot quản lý | Không bảo đảm ghi nhận mọi allocation của thư viện bên thứ ba |
| /proc/PID/smaps_rollup | Thống kê memory mapping và RSS/PSS của tiến trình trên Linux | Là số liệu hệ điều hành, không phân loại đầy đủ theo object Java |

Đừng đặt MaxDirectMemorySize bằng toàn bộ ngân sách RAM của container. JVM còn cần heap, metaspace, code cache, thread stack, GC structures và các native allocation khác. Checkpoint engine cũng cần tài nguyên để tạo và restore image.

### 4.4 Kích thước ảnh checkpoint

Ảnh checkpoint phản ánh trạng thái bộ nhớ của tiến trình và có thể bao gồm nhiều vùng native. Dung lượng image không nhất thiết bằng Xmx vì heap có thể chưa dùng hết, trang zero có thể được tối ưu, vùng nhớ có thể được nén hoặc ánh xạ trực tiếp tùy engine.

Một ứng dụng sử dụng nhiều direct buffer hoặc native memory có thể tạo image lớn dù heap tương đối nhỏ. Một ứng dụng map file lớn cũng có thể tạo nhiều VMA và ảnh hưởng thời gian restore, tùy cách engine xử lý file-backed pages.

Hãy đo kích thước image, RSS/PSS, thời gian checkpoint và thời gian restore trong workload thực tế. Không dùng Xmx làm đại diện cho tổng bộ nhớ cần checkpoint.

## 5. Vòng đời MappedByteBuffer và vấn đề unmap

### 5.1 Không có close() công khai trên MappedByteBuffer

MappedByteBuffer không triển khai AutoCloseable và không có phương thức close() công khai để unmap mapping một cách xác định.

Mapping được duy trì cho tới khi buffer được Garbage Collector thu hồi. Điều này có nghĩa ứng dụng không thể dựa vào một lệnh close thông thường để bảo đảm file mapping đã biến mất trước checkpoint.

Một số JDK có API nội bộ để ép unmap, nhưng các API này không thuộc hợp đồng Java SE ổn định. Gọi API nội bộ bằng reflection hoặc Unsafe có thể phụ thuộc module access, phiên bản JDK và implementation. Không nên xem đó là giải pháp portable cho CRaC.

### 5.2 Vì sao đặt buffer về null chưa đủ?

~~~java
mappedBuffer = null;
System.gc();
~~~

Đoạn code trên chỉ bỏ reference và yêu cầu Garbage Collector chạy. GC có thể chưa chạy, có thể chọn không thu hồi buffer tại thời điểm đó, hoặc cleaner có thể chưa thực thi ngay.

Nếu checkpoint được gọi ngay sau đó, mapping vẫn có thể còn tồn tại. Đây là lý do cần cơ chế quản lý lifetime xác định khi ứng dụng phải giải phóng mapping trước checkpoint.

### 5.3 Dùng MemorySegment và Arena trên JDK mới

Foreign Function & Memory API cung cấp MemorySegment và Arena để quản lý vùng nhớ native với lifetime rõ ràng. API này được hoàn thiện trong JDK 22. Ở các JDK cũ hơn, các phiên bản preview/incubator có thể có chữ ký hoặc quy tắc khác.

FileChannel có overload map() nhận Arena và trả về MemorySegment. Khi Arena đóng, mapping gắn với Arena được giải phóng.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.channels.FileChannel;

MemorySegment mapped;

try (Arena arena = Arena.ofConfined()) {
    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY,
            0,
            fileSize,
            arena);

    byte first = mapped.get(
            java.lang.foreign.ValueLayout.JAVA_BYTE, 0);
}
~~~

Trong ví dụ trên, mapped chỉ có thể được truy cập trong lifetime của Arena. Sau khi thoát try block, Arena đóng và segment không còn hợp lệ.

Nếu ứng dụng cần giữ mapping trong suốt vòng đời service, hãy giữ Arena ở một resource có thể đóng trong beforeCheckpoint và tạo Arena/mapping mới trong afterRestore.

Arena.ofConfined() phù hợp khi vùng nhớ chỉ được truy cập từ thread sở hữu. Nếu nhiều thread cần truy cập, có thể cần Arena.ofShared(), đồng thời phải đồng bộ việc đóng Arena với các thread đang dùng segment.

### 5.4 MemorySegment cấp phát native memory

Arena cũng có thể cấp phát vùng native memory:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment nativeMemory = arena.allocate(1024 * 1024);

    nativeMemory.set(
            java.lang.foreign.ValueLayout.JAVA_INT,
            0,
            12345);
}
~~~

Khi Arena đóng, vùng native memory được giải phóng theo lifetime của Arena. Đây là cách quản lý có tính xác định hơn so với direct buffer phụ thuộc cleaner.

Nếu dữ liệu cần tồn tại qua checkpoint, có hai lựa chọn:

- Giữ vùng nhớ trong ảnh nếu build và engine hỗ trợ đúng workload đó, đồng thời bảo đảm mọi native dependency vẫn hợp lệ.
- Đóng Arena trước checkpoint, lưu dữ liệu cần thiết vào file hoặc trạng thái nghiệp vụ, rồi cấp phát và nạp lại vùng nhớ sau restore.

Lựa chọn nào phù hợp phụ thuộc kích thước dữ liệu, thời gian restore, khả năng tái tạo và yêu cầu nhất quán.

## 6. Quản lý mapping bằng CRaC Resource

Một Resource có thể sở hữu FileChannel, Arena và MemorySegment. Trước checkpoint, nó ngừng truy cập mapping, đồng bộ dữ liệu cần thiết, đóng Arena và channel. Sau restore, nó mở lại file, tạo Arena mới và tạo mapping mới.

Ví dụ dưới đây minh họa một file mapping chỉ đọc:

~~~java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class MappedFileResource implements Resource, AutoCloseable {

    private final Path path;
    private final long offset;
    private final long size;

    private FileChannel channel;
    private Arena arena;
    private MemorySegment segment;

    public MappedFileResource(Path path, long offset, long size)
            throws IOException {
        this.path = path;
        this.offset = offset;
        this.size = size;
        openMapping();
        Core.getGlobalContext().register(this);
    }

    private synchronized void openMapping() throws IOException {
        FileChannel newChannel = FileChannel.open(
                path, StandardOpenOption.READ);
        Arena newArena = Arena.ofShared();

        try {
            MemorySegment newSegment = newChannel.map(
                    FileChannel.MapMode.READ_ONLY,
                    offset,
                    size,
                    newArena);

            channel = newChannel;
            arena = newArena;
            segment = newSegment;
        } catch (Throwable failure) {
            try {
                newArena.close();
            } catch (Throwable closeFailure) {
                failure.addSuppressed(closeFailure);
            }

            try {
                newChannel.close();
            } catch (Throwable closeFailure) {
                failure.addSuppressed(closeFailure);
            }

            throw failure;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        segment = null;

        if (arena != null) {
            arena.close();
            arena = null;
        }

        if (channel != null) {
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openMapping();
    }

    @Override
    public synchronized void close() throws Exception {
        segment = null;

        if (arena != null) {
            arena.close();
            arena = null;
        }

        if (channel != null) {
            channel.close();
            channel = null;
        }
    }
}
~~~

Ví dụ dùng API FFM ổn định từ JDK 22 trở lên và package org.crac. Nếu dùng jdk.crac thì thay import CRaC tương ứng với bản JDK.

Một số điểm thiết kế:

- Resource là owner duy nhất của mapping và Arena.
- Trước khi đóng Arena, ứng dụng phải bảo đảm không còn thread nào truy cập segment.
- Channel được mở lại từ path sau restore; không lưu số FD.
- Nếu file thay đổi giữa checkpoint và restore, ứng dụng cần xác minh version hoặc checksum trước khi cho phép truy cập.
- Nếu openMapping() thất bại, exception phải được truyền lên CRaC để restore không bị xem là thành công.

Đoạn code minh họa cleanup khi tạo mapping thất bại. Trong production, có thể bổ sung một kiểu exception cụ thể và chính sách xác minh file để phân biệt lỗi I/O, lỗi Arena và lỗi dữ liệu không tương thích.

### 6.1 Mapping có ghi dữ liệu

Nếu mapping được mở ở READ_WRITE, callback trước checkpoint cần dừng writer và đồng bộ dữ liệu trước khi đóng Arena:

~~~java
@Override
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    stopWritersAndWait();

    if (segment != null) {
        // Thực hiện bước đồng bộ dữ liệu theo API và
        // semantics của mapping đang dùng.
    }

    closeMapping();
}
~~~

Với MappedByteBuffer, có thể gọi force() trước khi bỏ reference. Với MemorySegment mapping, hãy dùng cơ chế đồng bộ file phù hợp với JDK API đang sử dụng; không giả định MemorySegment có cùng phương thức force() như MappedByteBuffer.

Nếu dữ liệu là dữ liệu nghiệp vụ quan trọng, cần xác định rõ checkpoint chỉ được phép diễn ra sau một commit point. Việc đóng mapping không thay thế transaction hoặc protocol ghi dữ liệu của ứng dụng.

## 7. Dùng MappedByteBuffer trong ứng dụng CRaC

Nếu ứng dụng đã dùng MappedByteBuffer và chưa thể chuyển sang MemorySegment, cần xác định liệu mapping có thể được giữ qua checkpoint trong đúng build và engine hay không.

### 7.1 Kiểm kê tất cả mapping

Tìm nơi gọi:

- FileChannel.map().
- MappedByteBuffer hoặc các lớp wrapper giữ mapping.
- Thư viện indexing, database embedded, cache hoặc search engine.
- Native library gọi mmap() trực tiếp.
- Các mapping được framework hoặc thư viện tạo ngầm.

Đừng chỉ tìm FileChannel.open(). Mapping có thể được tạo từ một lớp khác hoặc từ native code.

### 7.2 Xác định backing file

Với mỗi mapping, ghi nhận:

- Path hoặc file identity.
- Offset và size.
- READ_ONLY, READ_WRITE hay PRIVATE.
- File nằm trên local filesystem, network filesystem, volume hay tmpfs.
- Ai có quyền thay đổi hoặc thay thế file.
- Mapping có được dùng đồng thời bởi tiến trình khác hay không.
- Ứng dụng có cần ghi force() trước checkpoint hay không.

Nếu restore chạy trên host khác, file backing phải được cung cấp ở đúng vị trí và tương thích với ảnh. Đừng dựa vào đường dẫn tuyệt đối của host nguồn nếu deployment không bảo đảm mount giống nhau.

### 7.3 Xác định cách unmap

Với MappedByteBuffer cổ điển, không có API unmap công khai và xác định. Nếu mapping phải được giải phóng trước checkpoint, cần cân nhắc:

- Chuyển sang MemorySegment + Arena trên JDK hỗ trợ.
- Dùng một thư viện có API quản lý mapping lifetime rõ ràng và đã kiểm chứng với JDK/CRaC build.
- Thay mapping bằng FileChannel hoặc I/O theo khối nếu phù hợp với hiệu năng.
- Chỉ giữ mapping qua checkpoint nếu engine và môi trường triển khai hỗ trợ rõ ràng và đã kiểm thử.

Không dựa vào System.gc() như một bước đảm bảo unmap.

### 7.4 Thử restore thực tế

Checkpoint và restore trên đúng loại filesystem, container, kernel và build mục tiêu. Kiểm tra trường hợp file backing:

- Còn nguyên.
- Thay đổi nội dung.
- Bị thay thế.
- Bị thiếu.
- Không đủ quyền.
- Được mount tại đường dẫn khác.

Một checkpoint chạy thành công trên máy phát triển chưa chứng minh mapping có thể restore trên host production.

## 8. Giới hạn theo JDK, CRaC build và checkpoint engine

CRaC không phải là một tính năng có cùng mức hỗ trợ trên mọi JDK. API, engine, hệ điều hành, kiến trúc CPU và tùy chọn build có thể khác nhau. Khi đánh giá MappedByteBuffer và off-heap, cần kiểm tra ít nhất bốn lớp.

### 8.1 JDK có tích hợp CRaC

CRaC API không thuộc Java SE specification. Một số bản JDK tích hợp package jdk.crac; thư viện tương thích org.crac cho phép biên dịch ứng dụng và chuyển tiếp tới implementation nếu runtime có hỗ trợ.

Ứng dụng chạy được với org.crac trên JDK thông thường không có nghĩa runtime đó có thể tạo checkpoint thực. Dummy implementation có thể cho phép đăng ký Resource nhưng thao tác checkpoint sẽ thất bại vì không có engine.

Vì vậy, phải kiểm tra runtime thực tế, không chỉ kiểm tra compile thành công.

### 8.2 Phiên bản Foreign Function & Memory API

Foreign Function & Memory API có lịch sử incubator/preview ở các JDK trước và được hoàn thiện trong JDK 22.

| Dòng JDK | Cách tiếp cận |
|---|---|
| JDK 17 | MappedByteBuffer và DirectByteBuffer là API NIO phổ biến; FFM chưa phải API ổn định trong Java SE |
| JDK 21 | FFM ở giai đoạn preview; chữ ký và cách sử dụng phụ thuộc phiên bản preview |
| JDK 22 trở lên | FFM là API chuẩn; Arena và MemorySegment cung cấp lifetime rõ ràng cho native memory và mapped file |
| JDK vendor build có CRaC | Cần kiểm tra riêng việc tích hợp CRaC, package API, engine và nền tảng được hỗ trợ |

Không thể chỉ nhìn số phiên bản Java rồi kết luận có thể checkpoint. Cần dùng đúng bản dựng có CRaC và kiểm tra phiên bản FFM của JDK đó.

### 8.3 Khác biệt giữa CRIU và Warp

Checkpoint engine là thành phần ghi và khôi phục trạng thái tiến trình. Các engine có thể khác nhau về cách lưu memory pages, xử lý file mapping, image storage và giới hạn môi trường.

CRIU dựa trên Linux checkpoint/restore. Nó thu thập thông tin VMA, file descriptor và các tài nguyên tiến trình qua giao diện hệ điều hành. Khi restore, nó cần tái tạo mapping và các tài nguyên tương ứng.

Warp là engine khác được cung cấp trong một số Azul Zulu/Zing builds. Cách lưu và nạp memory image có thể khác CRIU. Tài liệu engine mô tả các chế độ direct mapping, memory loading và các tối ưu riêng theo loại build.

Không nên giả định một mapping hoạt động với CRIU sẽ có hành vi giống hệt với Warp, hoặc ngược lại. Hãy thử trên đúng engine sẽ triển khai.

### 8.4 Khác biệt giữa Linux thật và simulation engine

Một số build cung cấp simengine trên Windows, macOS và Linux để kiểm tra callback. Simulation engine gọi beforeCheckpoint và afterRestore trong cùng tiến trình, nhưng không tạo process image thực.

Do đó, simengine hữu ích để kiểm tra logic đóng/mở resource và khả năng lặp callback. Nó không chứng minh rằng:

- Native memory được lưu và nạp đúng.
- File-backed mapping được tái tạo.
- File backing có thể truy cập trên host khác.
- Kernel hỗ trợ các thao tác restore.
- Checkpoint image có thể được mở bởi engine production.

Cần có thử nghiệm checkpoint/restore thực trên Linux và đúng engine mục tiêu.

### 8.5 Bảng quyết định theo build

| Điều kiện | Điều cần xác minh |
|---|---|
| JDK thông thường, không tích hợp CRaC | Không có checkpoint engine thực; chỉ có thể dùng compatibility API cho code hoặc test stub |
| JDK có CRaC API nhưng engine mô phỏng | Callback có thể chạy; không kết luận về VMA, native memory hoặc file mapping |
| CRaC build dùng CRIU | Kiểm tra kernel, quyền, VMA, file backing và khả năng tái tạo mapping |
| CRaC build dùng Warp | Kiểm tra hỗ trợ mapping, quyền truy cập file backing, image mode và tùy chọn engine |
| Linux x86_64 hoặc ARM64 | Kiểm tra đúng kiến trúc và phiên bản vendor build |
| Windows hoặc macOS | Có thể phát triển hoặc mô phỏng tùy build; không mặc định có checkpoint engine thực |
| Native library hoặc driver | Xác nhận thư viện có hỗ trợ checkpoint/restore và đúng ABI/driver trên host restore |

Đây là cách phân loại để lên kế hoạch thử nghiệm, không phải một ma trận cam kết hỗ trợ cho mọi vendor. Danh sách nền tảng và engine thay đổi theo bản phát hành. Luôn đối chiếu tài liệu của đúng vendor, JDK build và engine đang sử dụng.

## 9. Giới hạn hệ điều hành và môi trường

### 9.1 VMA và số lượng memory mapping

Linux quản lý các virtual memory area (VMA) của tiến trình. Một ứng dụng tạo nhiều mapping nhỏ có thể tiêu thụ nhiều VMA, kể cả khi tổng dung lượng dữ liệu không lớn.

Giới hạn vm.max_map_count của host có thể ảnh hưởng tới ứng dụng tạo rất nhiều mapping. Một số runtime và engine cần thêm VMA trong lúc restore. Nếu gặp lỗi không tạo được mapping, hãy kiểm tra:

~~~bash
sysctl vm.max_map_count
cat /proc/<PID>/maps
~~~

Tăng vm.max_map_count là thay đổi ở cấp host và chỉ nên làm theo tài liệu vận hành của build/engine. Ví dụ, tài liệu Azul Zing có khuyến nghị tăng giới hạn VMA trong một số triển khai; giá trị cụ thể không nên áp dụng máy móc cho mọi hệ thống.

### 9.2 Quyền truy cập file backing

Restore có thể cần truy cập file backing của mapping. Nếu quyền của tiến trình mới khác, mount namespace khác hoặc file không còn truy cập được, engine có thể báo lỗi.

Một trường hợp được tài liệu Azul mô tả là Warp không thể mở một file đã được ánh xạ bởi Name Service Cache Daemon do thiếu quyền truy cập. Điều này cho thấy mapping do hệ thống hoặc thư viện tạo ra cũng có thể ảnh hưởng tới restore, dù ứng dụng không trực tiếp gọi FileChannel.map().

### 9.3 Filesystem và container

Cần thử trên loại filesystem thực tế: ext4, XFS, tmpfs, overlay filesystem, NFS hoặc volume của nền tảng cloud. Các loại filesystem có semantics và giới hạn khác nhau đối với mapping, đồng bộ dữ liệu và quyền truy cập.

Trong container, hãy kiểm tra:

- Mount namespace và đường dẫn file.
- UID/GID và permission.
- Volume có tồn tại ở cả nguồn và đích.
- File có được thay thế bởi init container hoặc sidecar hay không.
- VMA limit của host.
- Engine có đủ capability hoặc quyền cần thiết không.

Không nên tạo checkpoint trên container có mapping tới file tạm thời rồi restore trong container khác mà không bảo đảm file đó được cung cấp lại.

### 9.4 CPU, kiến trúc và cấu hình bộ nhớ

Checkpoint image có thể phụ thuộc CPU features, kiến trúc và cấu hình JVM tại thời điểm tạo ảnh. Restore trên máy thiếu CPU feature cần thiết có thể thất bại trước khi ứng dụng chạy tới callback afterRestore.

Cấu hình heap và một số cấu trúc nội bộ của JVM cũng có thể được cố định theo môi trường checkpoint. Restore trên máy có ít CPU hoặc ít memory hơn có thể gây vấn đề hiệu năng hoặc ổn định.

Với off-heap, cần tính cả lượng native memory và số lượng mapping vào ngân sách tài nguyên của host đích. Chỉ kiểm tra -Xmx là chưa đủ.

## 10. Theo dõi direct và mapped memory

Khi ứng dụng gặp lỗi memory hoặc restore chậm, cần thu thập dữ liệu từ cả JVM và hệ điều hành.

### 10.1 BufferPoolMXBean

JVM cung cấp BufferPoolMXBean để quan sát các buffer pool như direct và mapped.

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {

    System.out.printf(
            "%s: count=%d, memoryUsed=%d, totalCapacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity());
}
~~~

Các giá trị hữu ích:

- count: số buffer trong pool.
- memoryUsed: ước lượng bộ nhớ đang được sử dụng.
- totalCapacity: tổng capacity của các buffer.

Đây là số liệu theo buffer pool của JVM, không phải bản đồ đầy đủ mọi native allocation. Một native library tự gọi malloc hoặc mmap có thể không xuất hiện trong các số liệu này.

### 10.2 Native Memory Tracking

Có thể bật Native Memory Tracking khi khởi động JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó truy vấn:

~~~bash
jcmd <PID> VM.native_memory summary
~~~

NMT giúp quan sát nhiều nhóm native memory do HotSpot quản lý. Nó có overhead và không nhất thiết ghi nhận đầy đủ allocation của mọi thư viện native bên thứ ba.

### 10.3 Linux procfs

Các file hữu ích:

~~~bash
cat /proc/<PID>/maps
cat /proc/<PID>/smaps_rollup
cat /proc/<PID>/status
~~~

- maps cho biết các vùng địa chỉ và file backing.
- smaps_rollup cung cấp thống kê tổng hợp như RSS/PSS.
- status cho biết các số liệu bộ nhớ và trạng thái tiến trình.

Có thể kết hợp pmap:

~~~bash
pmap -x <PID>
~~~

Khi so sánh trước và sau restore, cần dùng cùng loại metric và cùng điều kiện tải. RSS tăng không nhất thiết có nghĩa direct buffer bị rò rỉ; các trang file mapping có thể được nạp dần khi ứng dụng truy cập.

## 11. Thiết kế chiến lược checkpoint cho off-heap

Có ba chiến lược chính, tùy loại dữ liệu và yêu cầu hiệu năng.

### 11.1 Giữ vùng nhớ trong ảnh

Phù hợp khi vùng native memory thuộc tiến trình, build và engine hỗ trợ, không phụ thuộc một handle ngoài tiến trình cần tạo lại, và dữ liệu có thể tiếp tục sử dụng an toàn sau restore.

Ví dụ: một bảng tra cứu immutable được cấp phát native memory, không giữ pointer tới file hoặc thiết bị và không phụ thuộc trạng thái native library bên ngoài.

Cần đo kích thước image và restore time. Vùng nhớ lớn có thể làm ảnh lớn, tốn I/O hoặc thời gian nạp.

### 11.2 Đóng và tái tạo mapping

Phù hợp khi mapping phụ thuộc file backing có thể thay đổi hoặc cần được xác minh lại sau restore.

Trước checkpoint:

- Dừng thread sử dụng mapping.
- Đồng bộ dữ liệu nếu cần.
- Lưu metadata và version.
- Đóng Arena nếu dùng MemorySegment mapping.
- Đóng channel và giải phóng các handle khác.

Sau restore:

- Mở file backing.
- Kiểm tra file identity/version.
- Tạo mapping mới.
- Khởi tạo lại cấu trúc phụ thuộc.
- Cho phép thread truy cập sau khi xác minh thành công.

### 11.3 Lưu dữ liệu bền vững, tái tạo cache native

Phù hợp với cache hoặc index có thể xây dựng lại từ dữ liệu gốc. Trước checkpoint, có thể đóng toàn bộ vùng native cache và chỉ giữ metadata cần thiết. Sau restore, nạp lại hoặc tái tạo cache theo chiến lược có giới hạn.

Cách này giảm phụ thuộc vào native allocator và file mapping cũ, nhưng có thể tăng thời gian restore. Hãy đo chi phí tái tạo so với chi phí giữ memory image.

### 11.4 So sánh chiến lược

| Chiến lược | Ưu điểm | Đánh đổi |
|---|---|---|
| Giữ off-heap trong image | Có thể giữ dữ liệu đã warm-up và giảm công việc khởi tạo | Image lớn; phụ thuộc engine và native state |
| Đóng rồi tạo lại | Kiểm soát lifecycle, xác minh file/dependency mới | Cần thời gian tạo lại và đồng bộ thread |
| Lưu dữ liệu gốc rồi rebuild | Giảm phụ thuộc trạng thái native cũ; dễ kiểm soát tính nhất quán | Tốn thời gian nạp hoặc dựng lại cache |

Không có chiến lược đúng cho mọi ứng dụng. Quyết định dựa trên khả năng tái tạo dữ liệu, yêu cầu consistency, dung lượng off-heap và hỗ trợ thực tế của engine.

## 12. Các lỗi thường gặp

### Đóng FileChannel nhưng quên mapping

MappedByteBuffer có lifetime riêng. Đóng channel không unmap buffer. Kiểm tra mapping còn sống và file backing khi restore.

### Dùng System.gc() để ép unmap

GC không bảo đảm chạy ngay. Không dùng nó làm bước đồng bộ trước checkpoint.

### Nhầm off-heap với dữ liệu bên ngoài tiến trình

Native memory vẫn thuộc không gian địa chỉ tiến trình và có thể được checkpoint. File descriptor, socket, device handle và trạng thái dịch vụ từ xa là các tài nguyên khác.

### Nghĩ file mapping đã được đóng cùng file descriptor

Mapping vẫn có thể tồn tại sau khi descriptor tạo mapping đã đóng. Kiểm tra VMA, không chỉ kiểm tra FD.

### Nghĩ checkpoint image mang theo file backing

File-backed mapping phụ thuộc filesystem. Bảo đảm file tồn tại, đúng version và có quyền truy cập khi restore.

### Dùng MappedByteBuffer cho vùng lớn mà không xét giới hạn ByteBuffer

ByteBuffer dùng chỉ số int. Với dữ liệu lớn hơn giới hạn capacity, cần chia mapping thành nhiều đoạn hoặc xem xét MemorySegment API có kích thước long trên JDK phù hợp.

### Dùng MemorySegment sau khi Arena đã đóng

Lifetime của segment gắn với Arena. Truy cập sau close sẽ thất bại. Cần đồng bộ thread trước khi đóng Arena.

### Dùng Arena confined từ nhiều thread

Arena.ofConfined() giới hạn quyền truy cập theo thread sở hữu. Nếu segment được chia sẻ, cần chọn Arena phù hợp và quản lý đồng thời.

### Chỉ quan sát Java heap

Heap có thể ổn định trong khi direct memory, mapped memory hoặc native allocation tăng mạnh. Theo dõi cả BufferPoolMXBean, NMT và số liệu procfs.

### Dùng simulation engine để kết luận mapping được restore

Simulation engine kiểm tra callback nhưng không tạo image thực. Phải thử trên build, engine, kernel và filesystem mục tiêu.

## 13. Quy trình triển khai

Khi chuẩn bị một ứng dụng dùng MappedByteBuffer hoặc off-heap cho CRaC, có thể đi theo các bước sau:

**Bước 1 — Lập danh sách vùng nhớ.** Tìm direct buffer, mapped buffer, MemorySegment, JNI allocation, native library và mọi lời gọi mmap().

**Bước 2 — Phân loại backing.** Xác định vùng nhớ anonymous, file-backed, shared mapping hay tài nguyên do driver quản lý. Ghi lại owner và dependency.

**Bước 3 — Chọn lifetime.** Quyết định vùng nhớ nào giữ qua checkpoint, vùng nào đóng và tạo lại, vùng nào có thể rebuild từ dữ liệu bền vững.

**Bước 4 — Xác định API phù hợp.** Với JDK mới, cân nhắc MemorySegment và Arena để quản lý native memory/mapping có lifetime xác định. Với MappedByteBuffer cũ, không giả định có thể unmap ngay bằng API công khai.

**Bước 5 — Viết Resource callbacks.** Dừng thread sử dụng vùng nhớ, flush dữ liệu cần thiết, đóng Arena hoặc resource native và mở lại sau restore. Truyền lỗi ra ngoài khi cleanup hoặc tái tạo thất bại.

**Bước 6 — Kiểm tra build và engine.** Xác nhận JDK vendor, phiên bản, OS, kiến trúc, CRaC engine, filesystem và các giới hạn VMA.

**Bước 7 — Đo bộ nhớ.** Thu thập direct/mapped buffer pool, NMT, RSS/PSS, số VMA, kích thước image và thời gian restore.

**Bước 8 — Kiểm thử môi trường thay đổi.** Thử file bị thay thế, thiếu quyền, mount khác, native dependency không sẵn sàng và restore trên host khác.

**Bước 9 — Chỉ mở traffic sau xác minh.** Sau restore, kiểm tra mapping, file version và các native dependency trước khi ứng dụng nhận request.

## Tài liệu tham khảo

- [Java API — MappedByteBuffer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/MappedByteBuffer.html): lifetime của mapping, load(), isLoaded() và force().
- [Java API — FileChannel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/channels/FileChannel.html): map file và các overload mapping.
- [Java API — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifetime và cách đóng vùng nhớ native.
- [Java API — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): truy cập vùng nhớ native và file-backed.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và các yêu cầu phối hợp tài nguyên.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): build, nền tảng và cách kiểm thử CRaC thực tế.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): khác biệt giữa CRIU, Warp và simulation engines.
- [CRaC — Debugging CRaC Failures](https://docs.azul.com/crac/usage/debugging): lỗi restore liên quan mapped file và cách điều tra.
- [CRaC — Concurrent Memory Loading](https://docs.azul.com/crac/operational/concurrent-memory-loading): cách engine nạp memory image và các giới hạn khi dùng native code.
- [CRaC — Usage Instructions for Azul Zing](https://docs.azul.com/crac/usage/zing-specific): lưu ý về giới hạn VMA và cấu hình hệ thống.
- [CRaC — CRaC API compatibility](https://github.com/CRaC/docs/blob/master/README.md): khác biệt giữa jdk.crac và org.crac.

