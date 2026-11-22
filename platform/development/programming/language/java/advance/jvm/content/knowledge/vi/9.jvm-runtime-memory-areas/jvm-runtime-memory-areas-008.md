# Bộ nhớ ngoài heap: direct buffer, thư viện native và cấu trúc nội bộ JVM

## 1. Java heap không phải toàn bộ bộ nhớ của tiến trình Java

Trong JVM, **Java heap** là vùng mà garbage collector thường quản lý để chứa những Java object và array thông thường. Nhưng tiến trình Java còn cần nhiều loại memory khác: nội dung **direct buffers**, dữ liệu cấp phát bởi **native libraries**, metadata của class, mã máy do JIT compiler sinh, native thread stacks, các cấu trúc nội bộ GC, những vùng file được map và vùng nhớ do OS/runtime sử dụng.

**Off-heap memory** thường chỉ dung lượng nằm ngoài Java heap do GC quản lý trực tiếp. Trong thực tế, thuật ngữ có hai phạm vi cần tách rõ:

- **Application off-heap:** byte storage cho NIO direct buffers, memory từ JNI/JNA/FFI hoặc thư viện native khác; ứng dụng cần hiểu owner, scope và cleanup của từng nguồn.
- **Native/non-heap process memory:** phạm vi rộng hơn, gồm cả vùng nội bộ JVM như HotSpot Metaspace, code cache, native thread stacks, GC work areas, shared libraries và memory mappings.

Không đồng nhất hai phạm vi trên. **Một direct buffer không phải là toàn bộ native memory** và các native allocation không nhất thiết nằm dưới cùng một quota.

~~~text
Java process (sơ đồ khái niệm, không phải layout địa chỉ thật)

  Java heap (GC quản lý object)
  ├── Business objects, arrays, String...
  ├── HeapByteBuffer wrapper ────> byte[] trong Java heap
  └── DirectByteBuffer wrapper ──┐
                                 │
  Bộ nhớ ngoài Java heap         │
  ├── Nội dung direct buffer <───┘
  ├── Native C/C++ allocations từ JNI/JNA
  ├── Memory-mapped file regions
  ├── Class metadata / Metaspace (HotSpot)
  ├── JIT code cache
  ├── Native thread stacks
  └── GC/runtime/internal structures
~~~

**Thông điệp quan trọng:** `ByteBuffer.allocateDirect(n)` trả về một **Java object `ByteBuffer`** được quản lý như object khác; phần **nội dung byte** mà nó biểu diễn thường được lưu ngoài heap GC thông thường. Không nói “cả DirectByteBuffer object nằm ngoài heap”.

### Ngoài heap không có nghĩa ngoài RAM

Native allocations thường nằm trong **không gian địa chỉ ảo** của process. OS ánh xạ những trang tương ứng tới physical RAM hoặc file backing khi cần. `virtual reserved`, `committed` và `resident (RSS)` là những đại lượng khác nhau. Một JNI pointer thông thường là địa chỉ ảo, **không phải địa chỉ vật lý RAM**, và Java không có API portable để đọc địa chỉ vật lý của một object.

## 2. Tại sao cần off-heap và khi nào không nên dùng?

Các lý do chính:

1. **Native I/O:** direct buffer cho phép JVM cố gắng dùng dữ liệu byte trực tiếp cho một số thao tác I/O hệ điều hành, giảm copy qua buffer trung gian.
2. **Tích hợp native:** thư viện mã hóa, nén, cơ sở dữ liệu, xử lý hình ảnh, networking hoặc thư viện thiết bị có thể cấp phát memory bằng C/C++.
3. **File mapping:** đọc/ghi file lớn theo trang nhờ cơ chế memory-mapped file, đôi khi có lợi với random access.
4. **Nhu cầu của chính VM:** class metadata, compiled code, thread stacks và GC bookkeeping luôn tiêu thụ tài nguyên ngoài Java heap theo implementation tương ứng.
5. **Kiểm soát vòng đời dữ liệu:** một số hệ thống cần buffer pools với giới hạn dung lượng/ownership rõ, giảm churn của heap arrays.

Nhưng **direct không tự đồng nghĩa nhanh hơn**, **off-heap không tự đồng nghĩa zero-copy** và **thay arrays bằng direct buffers không loại bỏ GC**. API Java SE 17 mô tả việc cấp/giải phóng direct buffer thường tốn chi phí hơn heap buffer; chỉ nên dùng khi workload có lợi ích đo được.

| Đặc tính | Heap ByteBuffer | Direct ByteBuffer |
| --- | --- | --- |
| Tạo bằng | `ByteBuffer.allocate(n)`, `wrap(byte[])` | `ByteBuffer.allocateDirect(n)` |
| `isDirect()` | `false` | `true` |
| Java wrapper | Có | Có |
| Nơi nội dung byte nằm | Thường trong Java `byte[]` | Có thể nằm ngoài heap GC thông thường |
| Dùng backing array qua `array()` | Có backing array với `allocate` | Không mặc định được hỗ trợ; kiểm tra `hasArray()` |
| Native I/O | Có thể cần intermediate copy | JVM best effort để giảm intermediate copy |
| Thời điểm memory được thu hồi | GC của heap backing array khi unreachable | GC/reference processing/native cleanup tùy implementation |
| Chỉ định ownership | Thông thường theo Java object reachability | Cần quan tâm thêm pool/view/native user lifetime |

## 3. Cách sử dụng `ByteBuffer` và ý nghĩa của các view

Các thao tác quan trọng trong Java NIO:

- `capacity()`: tổng sức chứa **byte** của buffer.
- `position()`: vị trí đọc/ghi tương đối tiếp theo.
- `limit()`: ranh giới hợp lệ của các thao tác tương đối.
- `remaining()`: số phần tử từ position tới limit.
- `put`, `get`, `putInt`, `getInt`: đọc/ghi nội dung theo offset logic.
- `order(ByteOrder.BIG_ENDIAN)` và `LITTLE_ENDIAN`: chọn thứ tự byte khi đọc/ghi primitive nhiều byte.
- `duplicate()`: tạo wrapper mới với trạng thái position/limit/mark riêng nhưng **chia sẻ nội dung**.
- `slice()` hoặc `slice(int, int)`: tạo view một vùng con mà **không copy** nội dung.
- `asReadOnlyBuffer()`: tạo read-only view; không làm storage vật lý trở nên immutable với những view khác có quyền ghi.

### Buffer state không phải lifetime của allocation

~~~text
0 ----- position ----- limit ----- capacity

clear():  position=0, limit=capacity
flip():   limit=position, position=0
rewind(): position=0
~~~

`clear()` **không zero-fill**, **không free native allocation**, **không xóa dữ liệu nhạy cảm**. `flip()` chủ yếu thay đổi con trỏ logic để có thể đọc dữ liệu đã ghi; nó không flush file và không gọi `free`. Khi pool tái sử dụng buffer, phải xử lý dữ liệu nhạy cảm và ownership riêng.

### `duplicate()`/`slice()` có thể làm memory sống lâu

Một view 100 byte từ direct allocation 64 MiB có thể tiếp tục giữ backing region lớn **reachable**. Điều này có thể làm direct-memory usage cao dù ứng dụng “chỉ giữ một slice nhỏ”. Khi cần giữ vài byte lâu, một bản copy độc lập đôi khi dễ quản lý hơn alias vào buffer lớn.

## 4. Ví dụ Java 17 hoàn chỉnh: direct, heap và aliasing

Tạo file **`DirectMemoryDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class DirectMemoryDemo {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(8);
        ByteBuffer direct = ByteBuffer.allocateDirect(8);

        heap.order(ByteOrder.BIG_ENDIAN);
        direct.order(ByteOrder.BIG_ENDIAN);
        heap.putInt(0, 0x01020304);
        direct.putInt(0, 0x01020304);

        System.out.println("heap.isDirect=" + heap.isDirect());
        System.out.println("direct.isDirect=" + direct.isDirect());
        System.out.println("sameInt=" +
                (heap.getInt(0) == direct.getInt(0)));

        ByteBuffer alias = direct.duplicate();
        alias.putInt(0, 0x0A0B0C0D);
        System.out.println("duplicateSharesBytes=" +
                (direct.getInt(0) == 0x0A0B0C0D));
        System.out.println("heapUnaffected=" +
                (heap.getInt(0) == 0x01020304));

        ByteBuffer firstFour = direct.slice(0, 4);
        System.out.println("slice.isDirect=" + firstFour.isDirect());
        System.out.println("slice.capacity=" + firstFour.capacity());
        System.out.println("sliceSharesBytes=" +
                (firstFour.getInt(0) == direct.getInt(0)));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 DirectMemoryDemo.java
java DirectMemoryDemo
~~~

**Stdout chính xác đã được biên dịch/chạy kiểm chứng bằng JDK 21 với target Java 17:**

~~~text
heap.isDirect=false
direct.isDirect=true
sameInt=true
duplicateSharesBytes=true
heapUnaffected=true
slice.isDirect=true
slice.capacity=4
sliceSharesBytes=true
~~~

Phân tích:

1. Heap buffer và direct buffer đều được cấp 8 byte, nhưng `isDirect()` khác nhau.
2. Lệnh `putInt(0, ...)` ghi bốn byte ở byte index 0; `sameInt=true` chỉ chứng minh **giá trị** đang bằng nhau, không phải hai buffers trỏ cùng địa chỉ.
3. `duplicate()` tạo view wrapper khác nhưng chia sẻ vùng byte. Ghi qua `alias` khiến `direct` thấy `0x0A0B0C0D`.
4. Buffer `heap` độc lập, không thay đổi.
5. `slice(0, 4)` giữ một view 4 byte và vẫn là direct, chứa bốn byte đang chia sẻ với `direct`.

Không được suy ra buffer trực tiếp có API chính thức trả **physical address**. Với `hasArray() == false`, gọi `array()` không được phép. Không dùng reflection/Unsafe đọc field private để suy đoán layout hay địa chỉ native ổn định.

## 5. Direct memory được thu hồi lúc nào?

Đối với `ByteBuffer.allocateDirect`, **Java 17 không cung cấp public `ByteBuffer.close()` hoặc `ByteBuffer.free()`**. Trong HotSpot và các JVM phổ biến, có những cơ chế cleaner/reference processing để quản lý native storage tương ứng khi Java wrapper và những liên kết giữ storage không còn cần thiết. Nhưng **thời điểm GC thực hiện cleanup không được bảo đảm**.

Những khẳng định cần tránh:

- **`direct = null`** không đồng nghĩa memory đã free; có thể còn view khác, queued I/O operation hoặc reference từ object khác.
- **`System.gc()`** chỉ là yêu cầu GC; JVM không bắt buộc reclaim đúng direct allocation ở một thời điểm xác định.
- **`clear()`** chỉ reset position/limit, không deallocate memory.
- **Tự gọi internal cleaner** bằng reflection/`sun.misc.Unsafe` không phải API portable; có nguy cơ use-after-free khi buffer/view/native code còn truy cập memory.
- **Direct memory do JNI cung cấp** không tự chứng minh JVM có trách nhiệm gọi native `free`.

Hãy phân biệt **managed direct allocation** do runtime Java kiểm soát với **native allocation ứng dụng sở hữu**. Nếu native code tự cấp memory và đưa pointer cho Java, ownership/lifetime phải được định nghĩa rõ. Memory phải còn hợp lệ đến khi mọi user đã hoàn tất; sau đó đúng chủ sở hữu mới free.

### Khi cần lifetime xác định

Một API/library có `AutoCloseable` hoặc lifetime scope phù hợp có thể giúp thu hồi tài nguyên chủ động. Java 17 có các foreign-memory API từng ở trạng thái incubating, trong khi cú pháp/contract của FFM ở những JDK mới hơn thay đổi nhiều. **Không chép ví dụ FFM của bản JDK mới vào dự án Java 17 và mặc định nó compile.**

Nếu triển khai wrapper native handle `AutoCloseable`, phải bảo đảm:

1. `close()` không double-free.
2. Không có async operation đang giữ pointer khi close.
3. Native callback/worker được dừng trước deallocation.
4. Không gửi pointer đã free cho Java wrapper hoặc thread khác.
5. Exception trong code Java vẫn đi qua cleanup `try-with-resources`/`finally`.
6. Thư viện có quy tắc đồng bộ khi hai thread cùng truy cập vùng bytes.

## 6. `-Xmx` và `-XX:MaxDirectMemorySize` là hai giới hạn khác nhau

Các tùy chọn HotSpot/JDK 17 thường gặp:

~~~bash
java -Xmx512m -XX:MaxDirectMemorySize=256m DirectMemoryDemo
~~~

- `-Xmx` là giới hạn max **Java heap** theo cơ chế JVM/HotSpot.
- `-XX:MaxDirectMemorySize` đặt giới hạn tổng cho các **NIO direct-buffer allocations** được tính theo cơ chế HotSpot.
- Không được cộng hai flag rồi gọi tổng đó là **mọi memory của process**.
- JNI/JNA native `malloc`, thread stacks, Metaspace, JIT code cache, GC structures và memory mappings có những cơ chế cấp phát/quota khác.
- Native allocator overhead và alignment khiến logical buffer capacity không nhất thiết đúng bằng native bytes đã reserve/commit.
- Flag `-XX:` thuộc VM implementation, **không bảo đảm mọi Java runtime đều hỗ trợ/diễn giải giống nhau**.

### OOME vì direct memory không giống OOME vì Java heap

Một HotSpot có thể ném `OutOfMemoryError` với thông báo dạng `Cannot reserve ... bytes of direct buffer memory` khi không thể reserve theo giới hạn/quỹ native buffer. Thông báo cụ thể phụ thuộc version/implementation, **không phải API contract để parse**.

`OutOfMemoryError: Java heap space` lại là tình huống khác. Nếu heap còn dư nhưng native memory cạn hoặc container vượt limit, tăng `-Xmx` thậm chí có thể khiến tổng memory pressure tệ hơn.

### Container memory limit

Nếu container giới hạn 1 GiB, không nên đặt `-Xmx` sát 1 GiB rồi quên direct buffers, thread stacks, class metadata, code cache và native libraries. OS/cgroup OOM killer có thể dừng process **không có Java stack trace**, khác với exception `OutOfMemoryError` do JVM ném.

Không có tỷ lệ heap/native universal áp dụng cho mọi service. Memory budget phải dựa vào workload: concurrent requests, payload sizes, connection buffers, số threads, số class loaders, library allocations và GC/JIT runtime footprint.

## 7. Memory-mapped files: `MappedByteBuffer`

`FileChannel.map(...)` tạo `MappedByteBuffer`, một loại direct buffer dùng memory mapping của file. OS quản lý các trang ánh xạ; **không phải file 10 GiB chắc chắn resident 10 GiB RAM ngay sau map**.

Một đoạn **minh họa, không phải file Java hoàn chỉnh**:

~~~java
try (FileChannel channel = FileChannel.open(
        Path.of("data.bin"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, 4096L);
    mapped.putInt(0, 123);
    mapped.force();
}
~~~

Muốn chạy đoạn này cần imports `java.nio.*`, `java.nio.channels.*`, `java.nio.file.*`, file hợp lệ và quyền truy cập phù hợp. Việc map vùng file vượt kích thước file/các giới hạn tương ứng phải tuân theo contract `FileChannel.map` và OS.

Những phân biệt bắt buộc:

- `mapped.isDirect()` là `true`, nhưng mapping khác với direct buffer cấp bytes bằng `allocateDirect`.
- `mapped.force()` có ý nghĩa **yêu cầu đẩy thay đổi tới file/storage** theo API; không có nghĩa free hoặc unmap.
- `FileChannel.close()` đóng channel **không đồng nghĩa mapping biến mất tức thời** nếu mapped buffer vẫn sống.
- OS có thể page-fault khi truy cập; file mapping memory accounting khác native heap allocations.
- Thay đổi/truncate file từ nơi khác khi mapping đang sử dụng có thể khiến một số vùng không còn truy cập hợp lệ; cần quản lý file ownership.
- Việc delete/rename file khi còn mapped region có thể khác giữa các hệ điều hành, đáng chú ý ở Windows.
- Buffer pools thường phân biệt `direct` và `mapped`; đừng trộn chúng khi đo đạc.

Map file hữu ích cho một số workload ngẫu nhiên/lớn; không chắc nhanh hơn `FileChannel.read()` cho mọi file, mức cache hay pattern I/O.

## 8. Native libraries: JNI/JNA, native allocators và pointers

Mã Java có thể làm việc với C/C++ hoặc hệ thống bên ngoài bằng JNI, JNA hay cơ chế foreign-function phù hợp phiên bản JDK. Những thư viện này có thể tự sử dụng:

- `malloc`, `calloc`, `realloc`, `free` trong C runtime.
- `mmap`/OS virtual memory allocations.
- Native sockets, file descriptors, GPU/device buffers, crypto/compression contexts.
- Native-created threads, native stacks.
- JNI global references giữ Java object/class.
- Direct buffers biểu diễn vùng native memory.

Vì vậy Java heap dump có thể trông bình thường trong khi C/C++ heap leak khiến process RSS tăng mạnh.

### 8.1. JNI method không tự tạo memory ownership

~~~java
public final class NativeCodec {
    static {
        System.loadLibrary("codec");
    }

    public static native int compress(
            byte[] input, int inputLength);
}
~~~

Đây là **đoạn minh họa không chạy độc lập**: cần thư viện native thật, JNI implementation đúng signature, build ABI tương thích và cấu hình library path. Nó không đủ để tạo stdout.

Nếu implementation cấp phát temporary output buffer trong native memory, phải có nơi free đúng. JNI global reference cần được delete theo API khi hết dùng. Một global ref quên dọn có thể giữ Java object hoặc class loader sống ngoài dự kiến.

### 8.2. Native direct buffers không mặc định được JVM sở hữu

JNI có các API như `NewDirectByteBuffer` để Java xem một vùng native memory. **Không suy ra** JVM sẽ tự `free` vùng do thư viện ứng dụng cấp phát chỉ vì một `ByteBuffer` wrapper đã được tạo.

Hai lỗi nghiêm trọng:

1. **Use-after-free:** native code free vùng bytes khi Java buffer vẫn còn dùng.
2. **Double-free:** hai chủ sở hữu cùng free một vùng allocation.

Kết quả có thể là crash, dữ liệu sai, corrupt memory hoặc vulnerability, không nhất thiết Java exception đẹp. Trong đa luồng, phải có quy tắc memory visibility/atomicity bên cạnh lifetime.

### 8.3. Direct buffer không chứng minh zero-copy

JVM có thể tránh **một số** intermediate copies khi đưa direct buffer vào native I/O. Nhưng giữa application, TLS, compression, network kernel, device drivers và file systems vẫn có thể có copies. **Zero-copy là tính chất của toàn bộ data path**, không phải bảo đảm chỉ dựa vào `isDirect()`. Hãy đo syscall, throughput và CPU trước/sau.

## 9. Cấu trúc native/non-heap nội bộ JVM

Ở góc nhìn HotSpot, nhiều vùng memory khác ngoài Java heap:

| Vùng hoặc cơ chế | Vai trò | Dấu hiệu/điểm cần đo |
| --- | --- | --- |
| **Metaspace / class metadata** | Class/interface/loader-related VM structures | Class loading count, unloading, metaspace stats, NMT |
| **JIT code cache** | Native code được compiler tạo ra | Code cache usage, compiler/code metrics, NMT |
| **Native thread stacks** | Stack/resource của platform threads | Thread count, `-Xss`, OS/native tracking |
| **GC internal structures** | Card tables, remembered sets, bitmap, runtime bookkeeping | GC logs, NMT categories |
| **JNI/JVMTI/native code** | Native library allocations, global refs, C/C++ data | Native profilers, heap retaining paths, OS metrics |
| **Direct NIO buffers** | Off-heap byte content, I/O | `BufferPoolMXBean`, direct memory quota |
| **Memory-mapped files** | OS mappings của file | Mapped pool, page-fault, process mappings |
| **Shared libraries/mappings** | Native executable/library code/data | OS mapping tools, process metrics |

**Metaspace là cơ chế của HotSpot**, không phải tên bắt buộc trong JVM Specification. Đặc tả JVM định nghĩa vùng abstract **method area**, thread stacks và heap; một JVM implementation khác có thể tổ chức cấu trúc thực tế khác.

### Metaspace và class loader leak

Nếu mỗi lần hot-reload tạo loader mới nhưng host giữ plugin object, thread context class loader, listener hoặc reflection cache, loader cũ có thể không đủ điều kiện GC/class unloading. Class metadata theo phiên tích lũy và có thể gây Metaspace OOME. Đây là một **vấn đề lifecycle của loaders/classes**, không phải vấn đề `ByteBuffer.allocateDirect`.

### Code cache

JIT compiler cần vùng native memory để lưu machine code của những method đã compile và cấu trúc liên quan. Kích thước/cache policy phụ thuộc VM flags và workload. JIT có thể deoptimize hoặc thu hồi/reuse code. Đừng gộp code cache vào Java heap used khi lập ngân sách.

### Thread stacks

Một process với hàng nghìn platform threads có thể reserve/commit native stack memory đáng kể. `-Xss` liên quan stack size trên HotSpot nhưng giảm quá thấp có thể làm `StackOverflowError` nhiều hơn; không thay thế việc sửa thread leak và bounded concurrency. Lỗi như `unable to create native thread` có thể do native memory, giới hạn số threads/processes hoặc OS resources, không nhất thiết vì Java heap đầy.

## 10. Theo dõi direct/mapped buffers bằng BufferPoolMXBean

Java SE 17 có interface `java.lang.management.BufferPoolMXBean`, thường cho các pool tên `direct`, `mapped`, và những pool khác tùy runtime.

Tạo file **`BufferStatsDemo.java`**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

public final class BufferStatsDemo {
    public static void main(String[] args) {
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            System.out.printf(
                    "pool=%s count=%d capacity=%d used=%d%n",
                    pool.getName(),
                    pool.getCount(),
                    pool.getTotalCapacity(),
                    pool.getMemoryUsed());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BufferStatsDemo.java
java BufferStatsDemo
~~~

**Không có stdout dạng số cố định** cho chương trình này: số pool, buffer count và bytes thay đổi theo JVM/workload/timing. Ví dụ trên đã được biên dịch với `javac --release 17` và chạy bằng JDK 21; một lần chạy có pool `direct`, `mapped`, nhưng **không biến quan sát của lần chạy đó thành hợp đồng chung**.

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên pool |
| `getCount()` | **Ước lượng** số buffers trong pool |
| `getTotalCapacity()` | **Ước lượng** logical capacity cộng dồn, theo byte |
| `getMemoryUsed()` | **Ước lượng** memory VM dùng cho pool; có thể khác capacity vì alignment/allocator |
| `getMemoryUsed() == -1` | JVM không có số ước lượng khả dụng |

Buffer pool stats **không phải thống kê tất cả JNI native malloc**, Metaspace, code cache hoặc thread stacks. Một số view như `slice()`/`duplicate()` có chung backing bytes; đừng suy luận số bytes resident bằng `count * size` nếu không biết phương thức accounting của implementation.

## 11. Native Memory Tracking (NMT) của HotSpot

NMT là công cụ quan sát nhiều **allocation nội bộ HotSpot VM** theo category như Thread, Class, Code, GC, Compiler và Internal. Nó có các chế độ `summary` và `detail` cùng overhead đáng cân nhắc.

Ví dụ bật NMT **ngay khi khởi động** ứng dụng thật:

~~~bash
java -XX:NativeMemoryTracking=summary -cp app.jar com.example.Main
~~~

Ở đây `app.jar` và `com.example.Main` **chỉ là tên minh họa**, cần thay bằng artifact và main class của ứng dụng.

Khi process có PID thực:

~~~text
jcmd PID VM.native_memory summary
jcmd PID VM.native_memory baseline
jcmd PID VM.native_memory summary.diff
~~~

`PID` ở đây chỉ chỗ thay bằng **số PID**, không gõ nguyên chữ `PID` nếu shell/application không có biến cùng tên.

Quy trình:

1. Khởi động JVM với `-XX:NativeMemoryTracking=summary` hoặc `detail`.
2. Ghi baseline lúc app ổn định.
3. Chạy workload có direct buffers/native code/class loading/threads.
4. Dùng `summary.diff` để xem category nào tăng.
5. Đối chiếu thêm `BufferPoolMXBean`, heap/GC logs, thread count và OS/process metrics.
6. Khi nghi third-party native leak, dùng **native allocator profiler** hoặc công cụ của thư viện tương ứng.

**Giới hạn quyết định:** Theo tài liệu Oracle JDK 17, NMT quan sát **JVM/HotSpot internal native memory**, nhưng **không bao quát toàn bộ memory do third-party native code và nhiều class-library allocations**. Vì vậy NMT không tăng **không đủ** để khẳng định C++ thư viện không leak.

Không mặc định NMT có thể bật bất cứ lúc nào trên một process đã chạy. Muốn NMT thu thập số liệu có ý nghĩa, cần bật khi JVM khởi động; có các lệnh `jcmd` để xem/baseline và một số thao tác quản lý NMT, nhưng không nên hứa bật lại một NMT chưa được cấu hình lúc startup.

## 12. Vì sao process RSS có thể lớn hơn heap used rất nhiều?

Một cách lập **memory budget** tương đối:

~~~text
Process memory footprint (mô hình gần đúng)
  Java heap resident pages
+ direct/native application buffers
+ Metaspace / class metadata
+ JIT compiled code / code cache
+ thread stacks
+ GC runtime structures
+ native libraries / device allocations
+ file mappings và OS-related pages
~~~

Đây **không phải** phép cộng tuyệt đối của các báo cáo memory khác nhau: các số liệu có thể double-count shared mappings hoặc đo reservation/commit/residency bằng đơn vị khác.

Phân biệt:

- **Heap used:** dung lượng GC nhìn thấy trong Java heap.
- **Heap committed:** dung lượng VM đã commit để phục vụ heap, không nhất thiết mọi trang đều resident vật lý.
- **Virtual reserved:** dải địa chỉ ảo đã đặt; không tương đương physical memory.
- **Process RSS:** các trang resident theo hệ thống đo đạc OS, có thể bao gồm shared pages.
- **Cgroup/container usage:** memory tính theo container accounting, có thể gồm những khoản khác process RSS.
- **NMT reserved/committed:** thông tin VM allocations theo categories, không bao gồm mọi native code bên ngoài.

Chỉ số nào phù hợp phụ thuộc câu hỏi bạn đang hỏi: Java object leak, direct buffer quota, native malloc leak, cgroup OOM, Metaspace tăng, hay thread stack pressure.

## 13. Chẩn đoán theo triệu chứng

### A. `OutOfMemoryError: Java heap space`

Kiểm tra Java heap allocations, live objects và GC. Đừng mặc định tăng `MaxDirectMemorySize` để sửa một heap OOME. Tuy nhiên cũng cần xem memory budget tổng khi điều chỉnh `-Xmx`.

### B. Direct buffer memory OOME

Có thể do:

- Pool không giới hạn; quá nhiều buffers đang sống.
- View (`slice`, `duplicate`) hoặc async request giữ backing allocations.
- Allocate quá thường xuyên làm reference cleanup chưa theo kịp.
- Direct-buffer quota quá nhỏ so workload thật.
- Native/OS memory pressure ngăn allocation.

Hướng xử lý: đo BufferPoolMXBean, total capacity, active requests, lifecycle buffer, quota và memory limit. **Không chỉ tăng limit rồi bỏ qua nguồn giữ references**.

### C. RSS tăng nhưng Java heap used ổn định

Nghi native allocations, mapped pages, direct buffers, Metaspace, JIT code hoặc nhiều native thread stacks. Bật NMT có kiểm soát, so BufferPoolMXBean và OS metrics; nếu NMT không bao phủ C/C++ memory, dùng native tools.

### D. Container OOMKilled, JVM không ném `OutOfMemoryError`

OS/cgroup có thể kill process trước khi JVM kịp log OOME/shutdown hooks. Kiểm tra container events, exit code và total resident/working set, thay vì chỉ xem heap GC.

### E. `unable to create native thread`

Kiểm tra thread count, executor leaks, OS process/thread limits, `-Xss` và native memory. Đừng vội tăng `-Xmx` khi Java heap chưa phải nguyên nhân.

### F. Metaspace OOME sau nhiều lần hot reload

Kiểm tra class-loader retention, ThreadLocal/TCCL, static caches, reflection metadata và class unloading. Direct buffer tuning không tự xử lý leak metadata của loaders.

### G. Native library crash

Khi có use-after-free, double-free, out-of-bounds hoặc ABI mismatch, JVM có thể crash cả process. Java heap dump không nhất thiết chỉ ra native allocation. Cần crash log, native debug/sanitizers trong môi trường an toàn, và kiểm tra ownership contract.

## 14. Thiết kế ứng dụng dùng off-heap an toàn

### 14.1. Bounded capacity và backpressure

Ví dụ mỗi request dùng một direct buffer 1 MiB và có 500 concurrent requests, riêng nội dung buffers có thể lên tới **khoảng 500 MiB**, trước allocator overhead, async retention và các vùng khác.

Nên giới hạn:

- Tổng số buffers.
- Tổng bytes direct capacity.
- Số requests/operations giữ buffers cùng lúc.
- Kích thước tối đa cho một buffer.
- Thời gian một buffer được giữ trong pool và timeout cho operations chưa trả buffer.
- Hành vi khi pool cạn: backpressure, queue bounded hoặc trả lỗi phù hợp thay vì cấp phát vô hạn.

### 14.2. Ownership và cleanup

~~~text
acquire / allocate
       |
       v
write bytes, pass to I/O/native operation
       |
       v
wait until operation REALLY completes
       |
       v
release back to bounded pool / close native owner
~~~

Đừng return buffer vào pool trong khi TLS/socket/async channel còn tham chiếu nó. Đừng giữ `slice` nhỏ làm toàn bộ region lớn sống lâu khi không cần. Đừng dùng `clear()` để xóa dữ liệu bí mật đã xử lý. Nếu dùng vùng native do thư viện sở hữu, chỉ close/free khi **mọi phía** đã kết thúc sử dụng.

### 14.3. Benchmark thay vì dựa vào tên API

So sánh heap/direct/mapped theo throughput, tail latency, CPU, GC pause, page fault và total process memory ở workload thực. Một `ByteBuffer.allocateDirect` lớn có thể phù hợp cho long-lived native I/O, nhưng hàng triệu direct allocations nhỏ sống ngắn có thể làm allocator overhead, cleanup cost và memory pressure tăng.

### 14.4. Giới hạn các quyền truy cập native

Native pointers hoặc foreign memory APIs có sức mạnh khác với Java memory-safe object access. Kiểm tra bounds, alignment, thread-safety, ownership và đặc quyền/module access. Tránh gọi internal APIs không được hỗ trợ để lấy địa chỉ memory hoặc ép cleanup của một direct buffer chưa chắc đã không còn user.

## 15. Sai lầm thường gặp

1. **“Off-heap nghĩa là không dùng RAM.”** Sai: đó là phạm vi memory ngoài Java heap, không nói trang có resident hay không.
2. **“DirectByteBuffer object ở ngoài Java heap.”** Sai: wrapper là Java object, byte storage mới thường off-heap.
3. **“Direct buffer luôn zero-copy.”** Sai: JVM cam kết best effort cho native I/O thích hợp.
4. **“`clear()` free native memory hoặc xóa dữ liệu.”** Sai.
5. **“`slice()` và `duplicate()` copy nguyên byte content.”** Sai: chia sẻ content.
6. **“Không còn reference gốc là buffer đã được free.”** Sai: có thể còn view hoặc I/O user.
7. **“`System.gc()` đảm bảo native cleanup ngay.”** Sai.
8. **“Mọi direct buffer Java 17 có `close()`.”** Sai: API ByteBuffer cơ bản không có.
9. **“`-Xmx` giới hạn tổng memory process.”** Sai.
10. **“`MaxDirectMemorySize` giới hạn mọi JNI `malloc`.”** Sai.
11. **“Mapped file chắc chắn vào RAM toàn bộ khi map.”** Sai.
12. **“`MappedByteBuffer.force()` là unmap.”** Sai.
13. **“Đóng FileChannel là mapped buffer đã unmap.”** Sai.
14. **“Metaspace là tên vùng bắt buộc trong mọi JVM.”** Sai: là implementation detail của HotSpot.
15. **“BufferPoolMXBean thống kê mọi native allocation.”** Sai.
16. **“NMT thống kê toàn bộ third-party native code.”** Sai.
17. **“RSS không giảm tức là chắc chắn leak.”** Sai: allocator/OS có thể giữ resident/committed capacity.
18. **“Native pointer là physical RAM address.”** Sai: thông thường là virtual address.
19. **“GC tự sửa mọi native lifetime lỗi.”** Sai: use-after-free có thể crash process.
20. **“Direct buffer nhanh hơn heap ở mọi workload.”** Sai: đo thực tế mới quyết định.

## 16. Câu hỏi tự kiểm tra

1. `ByteBuffer.allocate(16).isDirect()` là gì? **`false`**.
2. `ByteBuffer.allocateDirect(16).isDirect()` là gì? **`true`**.
3. `duplicate()` ghi byte, buffer gốc có thể thấy không? **Có** vì cùng content.
4. `clear()` zero-fill hay free memory không? **Không**.
5. Heap GC vẫn dùng khi có direct buffers không? **Có**, vì Java wrappers vẫn là objects.
6. `-Xmx1g` có ngăn process RSS vượt 1 GiB không? **Không**.
7. `-XX:MaxDirectMemorySize` có quota mọi JNI malloc không? **Không**.
8. Vì sao `getMemoryUsed()` khác `getTotalCapacity()`? **Overhead/alignment/cách đo**, cả hai là estimate.
9. `getMemoryUsed()` có thể bằng `-1` không? **Có**, khi không có estimate.
10. NMT có chứng minh không có C++ memory leak không? **Không**.
11. `MappedByteBuffer.force()` có thu hồi mapping không? **Không**.
12. Vì sao giữ slice 100 byte có thể giữ vùng 64 MiB? **Slice chia sẻ backing region**.
13. Thread count tăng mạnh làm native memory tăng do đâu? **Thread stacks** và runtime/thread resources.
14. Class-loader leak thường tác động vùng nào? **Class metadata/Metaspace**.
15. Vì sao `System.gc()` không là deadline cleanup? **Collector không bị buộc thực hiện đúng tại đó**.
16. Khi OOMKilled bởi container nhưng không có Java OOME, kiểm tra gì? **OS/cgroup memory limit và process footprint**.
17. Nếu native free vùng direct memory trong khi Java còn buffer wrapper, chuyện gì xảy ra? **Use-after-free có thể crash/corrupt data**.
18. Một giải pháp off-heap an toàn cần gì? **Bounded allocations, ownership, cleanup, backpressure và monitoring đa tầng**.

## 17. Tài liệu chuẩn

- Java SE 17 `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `MappedByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html
- Java SE 17 `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `BufferPoolMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- JDK 17 `java` launcher flags, gồm `MaxDirectMemorySize` và `NativeMemoryTracking`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17 Native Memory Tracking: https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- Java SE 17 `System.gc`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()
- Java SE 17 `Cleaner`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html
- JVMS 17 Run-Time Data Areas: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5

**Kết luận kỹ thuật:** **Java heap không phải toàn bộ JVM memory footprint.** `ByteBuffer.allocateDirect` tạo Java wrapper với byte storage có thể ngoài heap, native libraries có thể sở hữu allocations riêng, và bản thân JVM phải quản lý class metadata, compiled-code cache, stacks, GC structures. Đừng xem `-Xmx`, `MaxDirectMemorySize`, BufferPoolMXBean hay NMT là bức tranh đầy đủ một mình. Hãy thiết kế bounded buffers và lifetime rõ, theo dõi đồng thời heap/native/thread/class loading/OS metrics, và phân biệt GC của Java objects với việc thu hồi native resources.
