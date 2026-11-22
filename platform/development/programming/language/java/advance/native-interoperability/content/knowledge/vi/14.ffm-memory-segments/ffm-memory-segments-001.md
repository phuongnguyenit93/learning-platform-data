# MemorySegment: phân biệt vùng nhớ trên heap, ngoài heap và vùng ánh xạ tệp

## Mục tiêu

Trong Foreign Function & Memory API (FFM), `MemorySegment` biểu diễn **một vùng nhớ liên tục, có kích thước, giới hạn truy cập và vòng đời**. Cùng một kiểu `MemorySegment` có thể bao bọc ba tình huống rất khác nhau:

1. **Heap-backed memory**: dữ liệu thực sự nằm trong Java heap, chẳng hạn vùng nhớ của `byte[]` hoặc `int[]`.
2. **Native/off-heap memory được cấp phát**: vùng nhớ nằm ngoài Java heap, thường do một `Arena` cấp phát và quyết định lúc giải phóng.
3. **Memory-mapped file**: vùng địa chỉ ảo của tiến trình được ánh xạ tới nội dung tệp bởi hệ điều hành; trong FFM, đây là **một loại native/off-heap segment**, không phải loại thứ ba tách rời hoàn toàn khỏi native memory.

Bài này giúp bạn trả lời: dữ liệu nằm ở đâu, ai sở hữu bộ nhớ, `Arena` đóng có ảnh hưởng gì, khi nào thay đổi được phản ánh xuống tệp, có phải copy dữ liệu không, giới hạn an toàn là gì và chọn loại nào cho dữ liệu Java, JNI/FFM hoặc xử lý tệp lớn.

> **Phiên bản Java:** Các ví dụ `java.lang.foreign.MemorySegment`, `Arena`, `ValueLayout` và `FileChannel.map(..., Arena)` trong bài sử dụng **API FFM ổn định từ JDK 22** (JEP 454). Không biên dịch trực tiếp các ví dụ này trên JDK 17: thời JDK 17, FFM còn là API incubator khác package và signature. Các ví dụ bên dưới dùng JDK 22+ không cần `--enable-preview`. Nếu vẫn dùng Java 17, `ByteBuffer`/`MappedByteBuffer` là các API liên quan nhưng không hoàn toàn tương đương với `MemorySegment` ổn định.

## 1. Mô hình tư duy: ba cách tạo, hai loại backing memory

~~~text
                  Java code
                      |
                MemorySegment
                      |
        +-------------+----------------------+
        |                                    |
        v                                    v
  HEAP SEGMENT                         NATIVE SEGMENT
  backed by Java array                 nằm ngoài Java heap
        |                                    |
        |                         +----------+--------------+
        |                         |                         |
        v                         v                         v
  MemorySegment.ofArray(...)  Arena.allocate(...)     FileChannel.map(..., Arena)
  [1, 2, 3, 4]               memory native mới         vùng địa chỉ ánh xạ tệp
  GC quản lý Java array      Arena quản lý lifetime    Arena quản lý mapping
~~~

**Điểm phân loại chính xác:** `MemorySegment` có **heap segment** và **native segment**. `Mapped segment` là **native segment đặc biệt** có khả năng đồng bộ nội dung với tệp. Một mapped segment vẫn trả `isNative() == true`, đồng thời `isMapped() == true`.

Nếu gọi mapped file là “loại vùng nhớ thứ ba” để dễ học, hãy hiểu đó là **một phương thức tạo/sử dụng native segment**, chứ không phải một nhánh độc lập với off-heap ở mức API.

### Ma trận so sánh nhanh

| Tiêu chí | Heap-backed segment | Native segment cấp phát | File-mapped segment |
|---|---|---|---|
| Cách tạo điển hình | `MemorySegment.ofArray(array)` | `arena.allocate(bytes, alignment)` | `channel.map(mode, offset, size, arena)` |
| Backing storage | Mảng primitive trên Java heap | Vùng nhớ native ngoài Java heap | Ánh xạ từ vùng tệp vào không gian địa chỉ tiến trình |
| `isNative()` | `false` | `true` | `true` |
| `isMapped()` | `false` | `false` | `true` |
| Ai quản lý vòng đời chính? | JVM/GC quản lý backing array | `Arena` và scope tương ứng | `Arena` quản lý mapping; hệ điều hành quản lý page/file I/O |
| Đóng `Arena` có giải phóng? | `ofArray` không thuộc arena ấy | Confined/shared arena đóng → invalidate và giải phóng | Confined/shared arena đóng → invalidate và tháo mapping |
| Ghi có làm Java array thay đổi? | Có, vì cùng backing array | Không, trừ khi chủ động copy | Không, trừ khi có nguồn chia sẻ khác liên quan |
| Ghi có liên hệ trực tiếp với tệp? | Không | Không | Có, tùy `MapMode`; `force()` cho read-write mapping |
| Truy cập từ thread khác | `ofArray` truy cập từ nhiều thread, nhưng cần đồng bộ dữ liệu | Phụ thuộc loại arena | Phụ thuộc arena và chính sách sửa tệp |
| Rủi ro nổi bật | GC/object retention, alignment của backing array | Leak, use-after-close, dùng sai thread, native memory pressure | Mapping lifetime, I/O, file truncate, concurrent external changes |

Không dùng bảng này để suy ra rằng heap luôn nhanh hơn hoặc mapped luôn nhanh nhất. Hiệu năng phụ thuộc kích thước, quy luật truy cập, page fault, cache, GC, chi phí cấp phát, số lần copy và OS.

## 2. MemorySegment là một *view* có kiểm tra an toàn, không chỉ là địa chỉ

Mỗi `MemorySegment` có những thuộc tính quan trọng:

- **Byte size:** `segment.byteSize()` là số **byte** mà segment biểu diễn, không phải số phần tử Java.
- **Spatial bounds:** truy cập tại offset ngoài vùng được mô tả bị kiểm tra. Ví dụ vùng dài 8 byte không thể đọc `int` 4 byte tại offset 6.
- **Temporal bounds:** segment có một `scope()` kiểm soát lifetime. Nếu native arena đóng, segment và slice của nó không còn được phép truy cập.
- **Thread access:** một số arena, đặc biệt `Arena.ofConfined()`, giới hạn truy cập vào **thread sở hữu**.
- **Read-only flag:** `isReadOnly()`/`asReadOnly()` và chế độ map file có thể khiến thao tác ghi bị từ chối.
- **Backing category:** `isNative()` và `isMapped()` cho phép phân biệt segment trên heap với native, và mapped với native được cấp phát.

Ví dụ dùng layout để đọc:

~~~java
int value = segment.get(ValueLayout.JAVA_INT, 0L);
~~~

Đây là **mảnh minh họa**, giả định đã có biến `segment` và segment có ít nhất bốn byte, được căn chỉnh phù hợp với `JAVA_INT`, đang sống và được thread hiện hành phép truy cập. Tham số `0L` là **byte offset**. `ValueLayout` cho JVM biết loại dữ liệu, kích thước, thứ tự byte và yêu cầu alignment.

**Không nhầm các khái niệm sau:**

- `MemorySegment` là **đối tượng Java** trên heap mô tả một vùng nhớ.
- `segment.isNative()` nói về **backing storage** của vùng nhớ, không nói segment object nằm ngoài heap.
- `segment.address()` không phải con trỏ C dùng được trong mọi trường hợp. Với heap-backed array, địa chỉ được ảo hóa (ví dụ segment `ofArray` có address 0), không phải địa chỉ cố định của Java object khi GC di chuyển nó.
- `MemorySegment` không có nghĩa mọi C pointer đều tự an toàn. Các vùng native “mượn” qua địa chỉ thô, alias hay bên thứ ba giải phóng ngoài `Arena` có thể vi phạm giả định về lifetime.

## 3. Heap segment: MemorySegment.ofArray

### Cách tạo và quan hệ với Java array

~~~java
byte[] bytes = {1, 2, 3, 4};
MemorySegment heap = MemorySegment.ofArray(bytes);

System.out.println(heap.isNative()); // false
System.out.println(heap.isMapped()); // false

heap.set(ValueLayout.JAVA_BYTE, 1L, (byte) 99);
System.out.println(bytes[1]);        // 99
~~~

Đây là **đoạn Java có thể chèn vào phương thức** trên JDK 22+ với import `java.lang.foreign.MemorySegment` và `java.lang.foreign.ValueLayout`. `heap` và `bytes` tham chiếu **cùng backing region**; `set` qua segment sửa trực tiếp phần tử tương ứng của mảng Java. Không có bản copy mới chỉ vì bạn gọi `ofArray`.

Nếu Java sửa `bytes[0]`, một lượt `heap.get(ValueLayout.JAVA_BYTE, 0L)` tiếp theo thấy giá trị mới (tuân theo quy tắc visibility/happens-before nếu nhiều thread). Nếu heap segment có slice, slice cũng truy cập cùng backing array.

### Heap segment có phải tự close không?

Không. `MemorySegment.ofArray(byte[])` tạo segment với **automatic scope** giữ backing array reachable. Không có `Arena.ofConfined()` riêng để bạn `close()` nhằm giải phóng Java array. GC quyết định thời điểm thu hồi Java heap object khi không còn reachable; việc giữ một `MemorySegment` tham chiếu backing array cũng có thể giữ array sống.

Ngược lại, nếu bạn tạo native segment bằng `arena.allocate`, close arena tường minh làm segment invalid. **Đừng áp dụng quy tắc “try-with-resources arena” của native segment cho `ofArray` như thể nó quản lý Java array.**

### Độ dài theo byte, không phải số phần tử

~~~java
int[] values = {11, 22, 33};
MemorySegment ints = MemorySegment.ofArray(values);
System.out.println(ints.byteSize()); // 12
~~~

Java `int` có 4 byte; ba phần tử tương ứng 12 byte backing memory. Để đọc phần tử thứ hai, dùng:

~~~java
int second = ints.getAtIndex(ValueLayout.JAVA_INT, 1);
~~~

Đây là các mảnh Java JDK 22+; `getAtIndex` nhận **chỉ số phần tử theo layout**, khác `get(layout, byteOffset)`. Với layout `JAVA_INT`, chỉ số 1 tương ứng byte offset 4. Đừng dùng `get(JAVA_INT, 1L)` với ý định đọc `values[1]`; đó là byte offset 1 và còn có thể sai alignment.

### Giới hạn alignment trên heap

Vùng nhớ backed bởi `byte[]` chỉ bảo đảm alignment tương ứng phần tử byte. Vì thế:

~~~java
MemorySegment bytesSegment = MemorySegment.ofArray(new byte[8]);
// bytesSegment.get(ValueLayout.JAVA_INT, 0L); // Có thể bị từ chối vì alignment.
int n = bytesSegment.get(ValueLayout.JAVA_INT_UNALIGNED, 0L);
~~~

Đoạn trên minh họa đọc bốn byte đầu bằng **unaligned layout**. Đây không phải yêu cầu “sửa byte order” bằng unaligned layout; nếu cần định dạng tệp/network cố định, bạn còn phải chọn `withOrder(ByteOrder.BIG_ENDIAN)` hoặc `LITTLE_ENDIAN` phù hợp. Mảng `int[]`, `long[]` có giới hạn alignment khác; không lấy khả năng alignment của một backing type để suy ra cho mọi heap array.

### Khi nào dùng heap segment?

- Dữ liệu gốc đã ở mảng Java và cần truy cập qua API `MemorySegment`.
- Muốn tích hợp thuật toán dùng `get`/`set`/`MemoryLayout` mà không copy dữ liệu khỏi mảng.
- Vùng dữ liệu vừa phải, vòng đời phù hợp GC; JNI/FFM code không đòi native address cho đầu vào đó.
- Muốn tránh quản lý explicit native allocation khi không cần.

**Cảnh báo:** “heap segment” không tự làm địa chỉ mảng Java ổn định để truyền cho mã C tùy ý. JVM có thể di chuyển mảng khi GC; FFM có các quy tắc riêng cho việc truyền heap segment tới downcall, và native linker/ABI không thể luôn xử lý heap segment giống native pointer. Khi C yêu cầu một buffer ổn định trong thời gian gọi, hãy xem xét native segment và copy dữ liệu một cách có kiểm soát.

## 4. Native/off-heap segment: Arena.allocate

### Cấp phát có vòng đời rõ ràng

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeBytes = arena.allocate(16);
    nativeBytes.set(ValueLayout.JAVA_BYTE, 0L, (byte) 7);
    System.out.println(nativeBytes.get(ValueLayout.JAVA_BYTE, 0L)); // 7
} // arena.close(): native region không còn được sử dụng.
~~~

Đây là đoạn Java JDK 22+ có import `java.lang.foreign.Arena`, `MemorySegment` và `ValueLayout`.

`Arena.ofConfined()` tạo arena chỉ cho phép **owner thread** truy cập. `arena.allocate(16)` xin một vùng native 16 byte được mô tả bằng `MemorySegment`. Khi `try-with-resources` kết thúc bình thường hoặc do exception, `Arena.close()` được gọi; các vùng được arena quản lý hết hiệu lực. Nếu bạn giữ lại `nativeBytes` hoặc một slice rồi truy cập sau close, API sẽ báo lỗi thay vì âm thầm dùng vùng đã giải phóng.

**Đừng hiểu nhầm:** `Arena` là nơi quản lý lifetime của những vùng native nó đã cấp/mapping vào scope; nó không có trách nhiệm giải phóng mọi pointer tùy ý từ `malloc` ở thư viện C khác. Việc đóng arena không thay thế `free`/destructor của native SDK nếu bạn tự quản lý pointer ngoài arena.

### Arena nào phù hợp?

| Arena | Vòng đời và quyền truy cập | Gợi ý |
|---|---|---|
| `Arena.ofConfined()` | Chủ sở hữu một thread; close tường minh | Thích hợp cho lời gọi/thuật toán đơn luồng có phạm vi `try` rõ |
| `Arena.ofShared()` | Có thể truy cập từ nhiều thread; close tường minh | Khi cần chia sẻ dữ liệu, vẫn phải đồng bộ access và phối hợp close |
| `Arena.ofAuto()` | Lifetime do GC quản lý tự động, không có thời điểm cleanup xác định | Khi chấp nhận cleanup không tất định và khó dự đoán memory pressure |
| `Arena.global()` | Lifetime không giới hạn; các vùng cấp từ đây không được tự deallocate | Chỉ dùng với kiến trúc cần sống suốt tiến trình, cẩn thận leak |

Với `ofShared`, việc nhiều thread **được phép truy cập** không tự làm các phép đọc/ghi **đồng bộ**. Ứng dụng vẫn phải tổ chức data race, memory ordering, ownership và cách ngăn close khi còn thread đang sử dụng vùng nhớ.

Với `ofConfined`, truy cập từ thread khác có thể ném `WrongThreadException`. Không truyền segment sang thread executor rồi nghĩ rằng nó chỉ là một byte array an toàn dùng đa thread.

### Alignment và native data layout

Native code thường yêu cầu alignment của C struct hoặc primitive type. Hãy chỉ định rõ khi cấp phát:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment oneLong = arena.allocate(
            ValueLayout.JAVA_LONG.byteSize(),
            ValueLayout.JAVA_LONG.byteAlignment());

    oneLong.set(ValueLayout.JAVA_LONG, 0L, 123456789L);
}
~~~

`ValueLayout.JAVA_LONG` mô tả primitive Java `long` 8 byte; khi tương tác với C `long`, **không mặc định coi chúng cùng độ rộng trên mọi ABI** (C `long` có thể 32 bit trên Windows x64). Khi giao tiếp với native struct, nên xây `MemoryLayout` khớp ABI thực tế và dùng các layout C phù hợp nếu API/linker cung cấp.

### Off-heap không có nghĩa “miễn phí với GC”

Dữ liệu backing nằm ngoài Java heap nhưng segment object, các metadata và wrapper vẫn nằm trên heap. Bộ nhớ native vẫn chiếm tài nguyên process/OS và có thể góp phần vào giới hạn container. Không được cấp phát một arena lớn rồi quên close vì “JVM không nhìn thấy”. Một chương trình vẫn có thể gặp native memory exhaustion ngay cả khi Java heap còn nhiều dung lượng.

Một native segment không tự gắn với tệp; sau khi ghi `nativeBytes.set(...)`, việc close arena **giải phóng backing memory** chứ không lưu giá trị vào nơi lưu trữ lâu dài.

## 5. Memory-mapped file: native segment có backing từ tệp

### Tạo mapping bằng FileChannel.map(..., Arena)

JDK 22 cung cấp overload:

~~~java
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,     // file offset, tính bằng byte
        size,   // số byte muốn ánh xạ
        arena); // scope/lifetime của mapping
~~~

Đây là **mảnh code** trong phương thức Java đã mở `FileChannel channel`, có `long size` hợp lệ và `Arena arena` còn sống. API map một vùng của tệp vào vùng địa chỉ ảo của tiến trình và trả một `MemorySegment`. Giá trị của `mapped.isNative()` là `true`, `mapped.isMapped()` cũng là `true`.

**Không đồng nhất file-mapped với “đã đọc toàn bộ tệp vào RAM”.** Hệ điều hành quản lý virtual memory mapping, fault/load trang khi cần; dữ liệu có thể nằm trong page cache hoặc thiết bị lưu trữ. `mapped.byteSize()` mô tả kích thước vùng mapped trong **không gian địa chỉ**, không chứng minh các byte đó đang resident trong RAM.

### Các chế độ MapMode

| MapMode | Đọc | Ghi qua segment | Quan hệ với tệp gốc |
|---|---|---|---|
| `READ_ONLY` | Có | Không: segment chỉ đọc | Không dùng để cập nhật nội dung file |
| `READ_WRITE` | Có | Có | Thay đổi có thể được hệ điều hành đồng bộ với backing file; `force()` yêu cầu ghi xuống storage theo đặc tả |
| `PRIVATE` | Có | Có | Copy-on-write, thay đổi riêng không được truyền ngược vào file gốc theo hợp đồng |

Các chế độ trên không phải isolation level cho giao dịch database. `READ_WRITE` không khóa file khỏi chương trình khác, không tạo atomic transaction và không loại trừ external writers.

### `force()`, `load()`, `unload()` và `isLoaded()`

Những API này áp dụng cho **mapped segment**:

- `mapped.force()` yêu cầu ghi các thay đổi thuộc read-write mapping vào storage. Với local storage, đặc tả đưa ra bảo đảm mạnh hơn; với thiết bị từ xa, bảo đảm có thể khác. `force()` có thể ném `UncheckedIOException` khi flush lỗi.
- `mapped.load()` cố gắng đưa trang vào memory. Đây là **best effort**, không phải cam kết khóa dữ liệu trong RAM.
- `mapped.isLoaded()` cho gợi ý về residency, không phải bằng chứng bền vững hoặc snapshot.
- `mapped.unload()` cố gắng gỡ trang khỏi resident memory; không hủy mapping và không thay cho `Arena.close()`.
- Với segment không mapped, các phương thức chuyên dụng cho mapped segment có thể ném `UnsupportedOperationException`; hãy kiểm tra `isMapped()` trước khi sử dụng.

`force()` cũng **không thay thế** việc đóng mapping/arena. Một mapped region có thể đang hoạt động sau khi force; khi chương trình không dùng nữa, đóng arena đã tạo mapping để chấm dứt lifetime.

### FileChannel.close() khác Arena.close()

Trong ví dụ, `FileChannel` quản lý channel descriptor, còn `Arena` quản lý lifetime của segment/mapping. Đóng file channel **không được dùng thay cho việc close arena** để tuyên bố mapped segment đã invalid. Việc đóng arena mới là thao tác chủ động kết thúc scope của mapped segment do arena ấy quản lý.

Quan trọng hơn, nếu **tệp bị truncate hoặc sửa** bởi thread/process khác trong khi còn mapped, vùng mapped có thể thay đổi hoặc trở nên không truy cập được. Đặc tả lưu ý lỗi truy cập có thể không giống kiểm tra bounds Java thông thường. Không coi `MemorySegment` là lớp bảo vệ tuyệt đối chống các thay đổi ngoài JVM với backing file.

### Khi nào dùng mapped segment?

- Đọc/ghi tệp lớn với truy cập ngẫu nhiên và muốn tránh một số bản sao trung gian thông qua I/O thường.
- Cần chia sẻ nội dung qua cơ chế memory-mapping của OS giữa process theo cách được kiểm soát.
- Xử lý dữ liệu có cấu trúc từ file và có thể mô tả layout/byte order chính xác.
- Chấp nhận quản lý mapping lifetime, I/O errors, page faults và đồng bộ hóa theo file/OS.

Không dùng mmap chỉ vì file “to”: với stream tuần tự, `FileChannel.read`, `BufferedInputStream` hoặc bulk I/O có thể đơn giản và hiệu quả hơn; luôn benchmark workload thật.

## 6. Ví dụ đầy đủ JDK 22+: nhìn cùng lúc cả ba trường hợp

Chương trình Java dưới đây **không cần thư viện native C**: dùng FFM để thao tác heap, allocated native memory và mapped file. Nó tạo một tệp tạm, ghi giá trị vào mapping, `force()` rồi đọc lại nội dung tệp sau khi đóng arena. Đồng thời thử truy cập allocated native segment đã hết lifetime.

### 6.1. File: `MemoryKindsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

import static java.nio.file.StandardOpenOption.READ;
import static java.nio.file.StandardOpenOption.WRITE;

public final class MemoryKindsDemo {

    public static void main(String[] args) throws Exception {
        // 1. Heap: segment và byte[] chia sẻ cùng backing array.
        byte[] array = {1, 2, 3, 4};
        MemorySegment heap = MemorySegment.ofArray(array);
        heap.set(ValueLayout.JAVA_BYTE, 1L, (byte) 9);

        System.out.println("heap: native=" + heap.isNative()
                + ", mapped=" + heap.isMapped()
                + ", array[1]=" + array[1]);

        // 2. File tạm có nội dung xác định, không dựa vào file có sẵn.
        Path file = Files.createTempFile("ffm-memory-kinds-", ".bin");
        try {
            Files.write(file, new byte[] {10, 20, 30, 40});
            MemorySegment oldNative;

            try (Arena arena = Arena.ofConfined()) {

                // 3. Off-heap allocation, không có file backing.
                MemorySegment nativeBytes = arena.allocate(4);
                oldNative = nativeBytes;
                nativeBytes.set(ValueLayout.JAVA_BYTE, 0L, (byte) 77);

                System.out.println("native: native=" + nativeBytes.isNative()
                        + ", mapped=" + nativeBytes.isMapped()
                        + ", byte[0]="
                        + nativeBytes.get(ValueLayout.JAVA_BYTE, 0L));

                // 4. File-backed mapping với cùng arena.
                try (FileChannel channel = FileChannel.open(file, READ, WRITE)) {
                    MemorySegment mapped = channel.map(
                            FileChannel.MapMode.READ_WRITE,
                            0L,
                            4L,
                            arena);

                    mapped.set(ValueLayout.JAVA_BYTE, 1L, (byte) 99);
                    mapped.force();

                    System.out.println("mapped: native=" + mapped.isNative()
                            + ", mapped=" + mapped.isMapped()
                            + ", byte[1]="
                            + mapped.get(ValueLayout.JAVA_BYTE, 1L));
                }

            } // Đóng arena: native allocation và mapping hết hiệu lực.

            System.out.println(
                    "file=" + Arrays.toString(Files.readAllBytes(file)));

            try {
                oldNative.get(ValueLayout.JAVA_BYTE, 0L);
                System.out.println("unexpected access");
            } catch (IllegalStateException expected) {
                System.out.println("afterClose=IllegalStateException");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Tất cả byte trong ví dụ nằm trong khoảng 0–127 để `Arrays.toString(byte[])` có giá trị dương, dễ đối chiếu; với byte trên 127, Java `byte` là signed và thường được in thành số âm.

### 6.2. Lệnh biên dịch/chạy

Kiểm tra đang dùng JDK 22 hoặc mới hơn:

~~~bash
java -version
javac -version
javac MemoryKindsDemo.java
java MemoryKindsDemo
~~~

Không cần `--enable-preview` cho FFM ổn định trên JDK 22. Nếu `javac` báo không tồn tại package `java.lang.foreign`, khả năng cao bạn đang dùng JDK cũ hoặc toolchain không khớp; hãy xác minh `java` và `javac` thực sự trỏ đến đúng JDK.

### 6.3. Stdout mong đợi

Trên một JDK 22+ có hỗ trợ `FileChannel.map(..., Arena)` và tệp tạm hoạt động bình thường:

~~~text
heap: native=false, mapped=false, array[1]=9
native: native=true, mapped=false, byte[0]=77
mapped: native=true, mapped=true, byte[1]=99
file=[10, 99, 30, 40]
afterClose=IllegalStateException
~~~

**Vì sao kết quả có dạng trên?**

1. `MemorySegment.ofArray(array)` không tạo copy; ghi tại offset 1 của heap segment sửa `array[1]` từ 2 thành 9.
2. `arena.allocate(4)` trả native segment. `nativeBytes.set` ghi vào off-heap allocation, không ảnh hưởng mảng Java hay tệp.
3. `FileChannel.map` tạo mapped segment có `isNative()==true` **và** `isMapped()==true`. Lệnh ghi byte 99 ở offset 1 sau đó `force()`.
4. Đọc lại file cho `[10, 99, 30, 40]`: file còn nguyên ở vị trí 0, 2 và 3; chỉ vị trí 1 bị thay. Tên file tạm được sinh ngẫu nhiên **không xuất hiện** trong stdout, nên output còn xác định.
5. Sau khi thoát `try (Arena ...)`, `oldNative` vẫn là reference Java tới **segment object**, nhưng scope đã bị đóng; lệnh `get` ném `IllegalStateException`. Việc giữ Java reference **không giữ native backing memory sống** sau một lần close tường minh.

Nếu hệ thống không hỗ trợ mapping của overload này, hoặc không thể tạo/ghi tệp tạm, ví dụ có thể ném `IOException`/`UnsupportedOperationException`. Khi đó không nên giả định output trên xảy ra trên mọi filesystem hoặc provider; các dòng trên là kết quả trong môi trường hỗ trợ theo hợp đồng JDK.

### 6.4. Một chi tiết quan trọng: đóng channel trước arena

Ở mã mẫu, thứ tự đóng là:

~~~text
Tạo file
  |
  +-- Arena.ofConfined()
        |
        +-- allocate native
        |
        +-- FileChannel.open(...)
              |
              +-- map(..., arena)
              +-- mapped.set(...), mapped.force()
              |
              +-- channel.close()
        |
        +-- arena.close() -> invalidates native và mapped
  |
  +-- Files.readAllBytes(file)
  +-- Files.deleteIfExists(file)
~~~

Đóng `FileChannel` kết thúc channel I/O, còn `Arena` mới kiểm soát lifetime của mapped memory segment. `force` được gọi trước khi cả hai đóng để thể hiện rõ yêu cầu persist. Đối với tệp tạm trên Windows, đảm bảo mapping đã được giải phóng trước khi xóa file để tránh lỗi file-in-use.

## 7. Lát cắt, sao chép và aliasing

Một `MemorySegment` có thể có slice:

~~~java
MemorySegment whole = MemorySegment.ofArray(new byte[] {1, 2, 3, 4});
MemorySegment middle = whole.asSlice(1L, 2L);

middle.set(ValueLayout.JAVA_BYTE, 0L, (byte) 88);

System.out.println(whole.get(ValueLayout.JAVA_BYTE, 1L)); // 88
~~~

Đoạn Java trên có thể chạy trong method JDK 22+. `asSlice` tạo **view**, không copy; `middle[0]` là cùng byte với `whole[1]`. Slice có bounds nhỏ hơn nhưng vẫn dùng cùng scope/lifetime của backing memory. Điều này đúng với heap, native allocation và mapped segment.

Ngược lại, `MemorySegment.copy(src, srcOffset, dst, dstOffset, byteCount)` **sao chép dữ liệu** giữa hai segments, với số byte chỉ định. Đừng giả định copy là zero-copy hay alias; hai vùng nhận dữ liệu có thể tách biệt.

| Thao tác | Tạo copy dữ liệu? | Quan hệ lifetime |
|---|---|---|
| `MemorySegment.ofArray(existingArray)` | Không copy backing array | Scope giữ backing array reachable |
| `segment.asSlice(offset, size)` | Không copy | Chia sẻ scope và backing storage |
| `MemorySegment.copy(...)` | Có, copy byte theo vùng | Mỗi source/destination giữ scope riêng |
| `Arena.allocate(bytes)` | Tạo allocation native mới | Do arena quản lý |
| `FileChannel.map(...)` | Tạo mapping, không buộc đọc hết file vào heap | Mapping do arena quản lý |
| `Files.readAllBytes(path)` | Tạo một Java `byte[]` chứa dữ liệu file | Java heap/GC quản lý array |

Một file-mapped segment là vùng nhớ chia sẻ với file backing (theo MapMode), nhưng không nhất thiết là vùng vật lý chứa nguyên toàn bộ file ở RAM. Kỹ thuật mapping thường giúp **tránh bản sao dữ liệu lên một Java byte[]** cho một số workload; nó không có nghĩa mọi dữ liệu hay page fault đều “zero cost”.

## 8. Bounds, alignment, byte order và read-only

### 8.1. Byte offset phải nằm trong bounds

Với segment tám byte:

~~~java
MemorySegment eight = MemorySegment.ofArray(new byte[8]);

// Đọc bốn byte ở offset 0: dùng unaligned layout phù hợp byte[].
int first = eight.get(ValueLayout.JAVA_INT_UNALIGNED, 0L);

// eight.get(ValueLayout.JAVA_INT_UNALIGNED, 6L);
// Sẽ bị từ chối: cần bốn byte, nhưng chỉ còn hai byte.
~~~

Tại offset 6, truy cập bốn byte vượt `byteSize()=8`; `MemorySegment` kiểm tra phạm vi theo size của layout. Bounds của slice có thể nhỏ hơn segment gốc, nên một offset hợp lệ trên `whole` vẫn có thể không hợp lệ trên `slice`.

### 8.2. Byte order không giống endian của file

`ValueLayout` mang byte order. Khi xử lý một file/wire format có quy định **big-endian**, khai báo tường minh:

~~~java
import java.nio.ByteOrder;

// Đặt bên trong method đã có biến segment phù hợp và đủ byte.
var beInt = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);
int n = segment.get(beInt, 0L);
~~~

Đây là **mảnh code**, không phải chương trình độc lập. Sử dụng `JAVA_INT_UNALIGNED` khi region có yêu cầu alignment 1; `withOrder` điều chỉnh thứ tự byte, không thay đổi số byte của `int`. Đừng chỉ dựa vào endian của CPU khi định dạng file đã quy định cụ thể.

### 8.3. Read-only thực sự chặn ghi

~~~java
MemorySegment readonly = MemorySegment.ofArray(new byte[4])
        .asReadOnly();

// readonly.set(ValueLayout.JAVA_BYTE, 0L, (byte) 1);
// Không hợp lệ: readonly segment từ chối ghi.
~~~

Đoạn này minh họa. Việc `asReadOnly` tạo **view chỉ đọc** không có nghĩa backing array bị đóng băng: nếu caller vẫn giữ `byte[]` gốc hoặc một mutable segment khác, caller đó vẫn có thể ghi dữ liệu. Muốn dữ liệu immutable ở tầng ứng dụng, cần kiểm soát những alias và writer khác.

Mapped `READ_ONLY` cũng không được ghi. Mapped `PRIVATE` có thể ghi vào view copy-on-write nhưng **không được kỳ vọng persist** vào backing file bằng `force()`.

## 9. Lifetime, thread confinement và lỗi sau khi đóng

### 9.1. Lifetime của slice kế thừa arena

~~~java
MemorySegment alias;
try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(8);
    alias = root.asSlice(2, 4);
} // Scope của root và alias đều hết hiệu lực.

// alias.get(ValueLayout.JAVA_BYTE, 0);
// Ném IllegalStateException vì arena đã đóng.
~~~

Đây là mảnh code trong một method. `MemorySegment` kiểm tra *temporal bounds* trên mỗi access. Slice không kéo dài lifetime của native allocation. Phải giữ arena sống trong toàn bộ thời gian segment/slice cần dùng.

### 9.2. Arena shared không tự xử lý race

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment shared = arena.allocate(1024);
    // Có thể cho nhiều thread truy cập shared, nhưng ứng dụng
    // phải kiểm soát đồng bộ dữ liệu và close so với in-flight access.
}
~~~

`ofShared` giải quyết quyền truy cập cross-thread ở mức scope; nó **không** làm mọi `get`/`set` trên cùng byte trở thành transaction hoặc tự bảo đảm memory ordering. Nếu nhiều thread thay đổi cùng state, dùng giao thức đồng bộ hoặc atomic access qua VarHandle layout phù hợp.

Ngay cả khi API ngăn một số close race, bạn vẫn phải xác định thread nào sở hữu arena và thời điểm chấm dứt công việc. Đừng truyền segment cho task bất đồng bộ rồi đóng arena ngay ở thread gọi trước khi task xong.

### 9.3. Sai thread và sai lifetime là hai lỗi khác nhau

- `WrongThreadException`: truy cập segment từ thread không được scope/arena cho phép, ví dụ segment của `ofConfined` ở thread khác.
- `IllegalStateException`: truy cập vùng có scope đã đóng, bất kể Java object vẫn tồn tại.
- `IndexOutOfBoundsException`: offset/size không nằm trong giới hạn.
- `IllegalArgumentException`: có thể phát sinh khi vi phạm alignment hoặc cố ghi vào read-only segment, tùy API access.
- Với mapped file, lỗi I/O ngoài heap còn có thể xuất hiện qua `UncheckedIOException` hoặc khi backing file bị thay đổi/truncate.

Java exceptions ở đây là cách FFM kiểm tra truy cập trong phạm vi mà **JVM kiểm soát được**. Không nên kết luận rằng mọi external C pointer hoặc file map đều miễn nhiễm với memory corruption nếu native code khác tự giải phóng backing storage.

## 10. Quan hệ với JNI, native libraries và ByteBuffer

### 10.1. JNI không tự hiểu Java heap segment như một C pointer tùy ý

Một hàm C nhận `void*` cần một địa chỉ native hợp lệ và lifetime rõ ràng. `MemorySegment.ofArray` không tự đảm bảo địa chỉ Java array ổn định để ghi lại trong thư viện native. Khi cần truyền dữ liệu qua FFM downcall/JNI tới hàm có hợp đồng native pointer, hãy chọn đúng loại segment, layout và lifetime; thường là **native segment** cho buffer cần địa chỉ off-heap.

Ví dụ quy trình ý tưởng:

~~~text
Java byte[] dữ liệu nguồn
      |
      +-- MemorySegment.ofArray(array) (không copy)
      |
      +-- MemorySegment.copy(...) hoặc set(...) có kiểm soát
                  |
                  v
            Native MemorySegment (arena)
                  |
                  v
         Foreign downcall / JNI bridge
                  |
                  v
         native code dùng buffer khi arena còn sống
~~~

Đây là mô hình **minh họa**, không phải một tuyên bố mọi native function đều cần copy. Cách truyền dữ liệu tối ưu phụ thuộc ABI, API FFM, loại dữ liệu, restrictions và cách native code sử dụng buffer.

Đặc biệt: không gọi `segment.address()` trên heap rồi ép nó thành địa chỉ của array trong C. Với `ofArray`, địa chỉ ảo hóa trong `MemorySegment` không phải physical pointer để native code lưu lại.

### 10.2. ByteBuffer.heap, direct và mapped

Các khái niệm đã có từ trước FFM:

- `ByteBuffer.allocate(n)`: buffer có backing storage trên Java heap.
- `ByteBuffer.allocateDirect(n)`: direct buffer, thông thường dùng native/off-heap storage.
- `FileChannel.map(mode, pos, len)`: trả `MappedByteBuffer`, thường là mapping native do OS quản lý.

FFM có thể kết nối với buffer bằng `MemorySegment.ofBuffer(buffer)` hoặc lấy `ByteBuffer` view qua `segment.asByteBuffer()` trong điều kiện API cho phép. **Không** suy ra mọi ByteBuffer wrapper có cùng lifetime với Arena: một direct buffer tự cấp, một mapped ByteBuffer legacy và một MemorySegment do Arena quản lý có các hợp đồng cleanup khác nhau.

Một giới hạn hữu ích: `MemorySegment.asByteBuffer()` cần segment có size không lớn hơn `Integer.MAX_VALUE` và backing tương thích; một `MemorySegment` có thể mô tả vùng lớn hơn khả năng biểu diễn bởi một ByteBuffer. Với heap segment backed bởi mảng không phải `byte[]`, `asByteBuffer` có thể không hỗ trợ.

### 10.3. Java 17 thì làm gì?

Java 17 **không có** API `java.lang.foreign.MemorySegment` ổn định. Có thể học khái niệm bằng `ByteBuffer` và `MappedByteBuffer`, hoặc sử dụng API incubator theo đúng tài liệu phiên bản đó, nhưng không copy nguyên ví dụ JDK 22 rồi chạy với `javac 17`.

Một ví dụ Java 17 độc lập về **heap buffer vs direct buffer**:

~~~java
import java.nio.ByteBuffer;

public class BufferKinds17 {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(4);
        ByteBuffer direct = ByteBuffer.allocateDirect(4);

        heap.put(0, (byte) 11);
        direct.put(0, (byte) 22);

        System.out.println("heapDirect=" + heap.isDirect());
        System.out.println("nativeDirect=" + direct.isDirect());
        System.out.println("heap0=" + heap.get(0));
        System.out.println("native0=" + direct.get(0));
    }
}
~~~

Chạy trên JDK 17:

~~~bash
javac BufferKinds17.java
java BufferKinds17
~~~

Stdout:

~~~text
heapDirect=false
nativeDirect=true
heap0=11
native0=22
~~~

Đoạn này cho thấy khác biệt API ByteBuffer cũ, **không** chứng minh rằng direct buffer giống hệt `Arena.allocate`. Tài nguyên direct/mapped buffer legacy có lifetime gắn với cơ chế quản lý riêng; vì vậy bài chính vẫn dùng FFM ổn định JDK 22 để giải thích `MemorySegment` và `Arena`.

## 11. Chi phí, giới hạn và lựa chọn thực tế

### 11.1. Khi nào chọn heap?

Chọn `MemorySegment.ofArray` khi dữ liệu tự nhiên đã nằm ở Java array hoặc Java heap có thể quản lý tốt kích thước đó. Tránh cấp phát off-heap rồi copy chỉ vì “native luôn nhanh hơn”: việc copy bổ sung, arena bookkeeping và native memory pressure có thể làm giải pháp phức tạp hơn mà không cải thiện hiệu năng.

### 11.2. Khi nào chọn native allocation?

Chọn `Arena.allocate` khi:

- Cần buffer native để trao đổi dữ liệu với thư viện C/ABI phù hợp.
- Cần kiểm soát alignment và lifetime bằng `Arena`.
- Muốn quản lý memory pressure ngoài Java heap và chấp nhận đóng tường minh.
- Có nhiều vùng cùng lifetime, có thể gom vào một arena.

Không cấp phát từ `Arena.global()` cho mọi request ngắn hạn; vùng từ global arena không được deallocate trong vòng đời process và có thể rò rỉ. Với request có boundary rõ, `Arena.ofConfined()` + `try-with-resources` thường dễ kiểm soát nhất.

### 11.3. Khi nào chọn mapped file?

Chọn mapping khi dữ liệu là tệp, workload phù hợp truy cập ngẫu nhiên hoặc chia sẻ qua OS, và bạn có thể quản lý external file updates, kích thước, I/O failures và flush. Đừng dựa vào mapping để bảo đảm durable transaction như database; `force()` không giải quyết đồng bộ nghiệp vụ giữa nhiều writers.

### 11.4. Những thứ benchmark phải đo

Nếu so hiệu năng, đo riêng:

- Thời gian **create/allocate/map** và **close/unmap**.
- Chi phí truy cập lần đầu (page faults) và truy cập lặp lại (cache warm).
- Thông lượng cho đọc tuần tự, đọc ngẫu nhiên, ghi nhỏ và ghi khối lớn.
- Số bản sao dữ liệu giữa Java array/native buffers/file.
- Memory footprint: Java heap, native allocations, mapped virtual size, resident pages và page cache.
- Tác động `force()` lên latency và thực tế storage (local/remote).
- Tốc độ GC và tổng thời gian xử lý end-to-end, không chỉ microbenchmark của một lệnh `get`.

Một mapped segment có `byteSize()` rất lớn không nhất thiết tương đương dùng cùng số byte resident RAM. Ngược lại, off-heap memory tiêu thụ tài nguyên hệ thống dù không được tính như Java heap objects.

## 12. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Xem mapped file là loại “không phải off-heap” | `isNative()==true` với mapped segment | Hiểu mapped là một phân loại con của native segment |
| `MemorySegment.ofArray` làm copy Java array | Nó bao bọc backing array hiện có | Nhận diện aliasing; dùng `MemorySegment.copy` nếu cần bản sao |
| Tính offset theo phần tử khi dùng `get(layout, offset)` | Offset của `get/set` là **byte** | Dùng `getAtIndex` hoặc nhân đúng kích thước layout |
| Dùng `JAVA_INT` trên segment từ `byte[]` mà không xét alignment | Heap segment có giới hạn alignment theo backing array | Dùng layout unaligned hoặc backing type phù hợp |
| Đóng arena rồi tiếp tục dùng segment/slice | Scope hết hiệu lực | Giữ arena sống suốt thao tác; không giữ raw pointer sau close |
| Cho rằng mapped data luôn đã ở RAM | OS quản lý page residency lazy | Đo page faults, `isLoaded` chỉ là hint |
| Mong `arena.close()` ghi dữ liệu allocated native vào file | Allocation native không có file backing | Chủ động file I/O hoặc mapped `READ_WRITE` + `force()` |
| Mong `mapped.force()` là database transaction | Flush không tự kiểm soát concurrency/atomicity | Dùng transaction/locking protocol cấp ứng dụng |
| Cho rằng mapped `PRIVATE` ghi ngược xuống file | Private mapping có copy-on-write | Dùng `READ_WRITE` và policy flush khi cần persist |
| Đóng channel và tưởng đã invalid mapped segment | Segment lifetime gắn arena | Đóng arena tương ứng |
| Sửa/truncate tệp khi vẫn mapped | OS có thể làm mapping mất hiệu lực hoặc thay đổi bất ngờ | Điều phối file lifecycle và external writers |
| Dùng `Arena.ofConfined` rồi chuyển segment sang worker thread | Vi phạm thread confinement | Dùng arena phù hợp và giao thức đồng bộ |
| Dùng `Arena.ofAuto` cho resource cần giải phóng ngay | GC timing không xác định | Dùng confined/shared + close tường minh |
| Cho rằng `MemorySegment.address()` trên heap là C pointer | Heap backing có địa chỉ ảo hóa và có thể GC move | Không tự ép địa chỉ heap; tuân theo FFM ABI |
| Cho rằng `byteSize()` mapped là lượng RAM resident | Mapped size mô tả vùng địa chỉ | Phân biệt virtual mapping, resident pages và file size |
| Kỳ vọng `java.lang.foreign` chạy thẳng trên Java 17 | API ổn định từ 22 | Dùng JDK 22+ hoặc code tương ứng riêng cho JDK 17 |

## 13. Tình huống và bài tập

### Tình huống A — đọc tệp rất lớn

Ứng dụng phân tích file hàng chục GB theo offset. Nếu dùng `Files.readAllBytes`, bạn cần một Java array lớn (thậm chí vượt giới hạn array trên nhiều JVM). Một mapped `MemorySegment` cho phép ánh xạ vùng tệp và truy cập theo offset `long`, nhưng phải kiểm tra memory address space, file size, lifetime và hành vi page faults. Không phải file nào cũng thích hợp mmap: với stream tuyến tính, `FileChannel`/buffered I/O có thể là lựa chọn tốt.

**Câu hỏi:** ánh xạ file 10 GB có nghĩa cấp phát ngay 10 GB Java heap không? **Không.** Mapped segment mô tả vùng file trong virtual address space và không tạo Java `byte[10GB]`.

### Tình huống B — truyền C struct

Một native C library nhận pointer tới struct có field alignment xác định. `MemorySegment.ofArray(byte[])` có thể không thỏa yêu cầu native address, alignment, hoặc ABI mong muốn. Dùng `Arena.allocate(layout)` với `MemoryLayout` đúng ABI và quản lý lifetime cho tới khi C function hoàn tất. Không giả định C `long` bằng Java `long` trên mọi nền tảng.

**Câu hỏi:** JVM GC có tự deallocate một `Arena.ofConfined` đã close chưa? **Không cần.** Close arena là hành động xác định kết thúc lifetime và giải phóng backing region do arena quản lý.

### Tình huống C — cập nhật mapped file

Một process ánh xạ tệp `READ_WRITE`, thay byte và gọi `mapped.force()`. Sau đó process khác vẫn có thể sửa cùng file; `force()` không cấm điều đó. Cần file locking hoặc giao thức ứng dụng nếu yêu cầu tuần tự hóa writes.

**Câu hỏi:** dùng `MapMode.PRIVATE` có ghi file gốc không? **Không theo hợp đồng copy-on-write.** Những thay đổi ở private mapping không dùng như một cách persist file gốc.

### Bài tập 1 — dự đoán alias

~~~java
byte[] a = {4, 5, 6};
MemorySegment s = MemorySegment.ofArray(a);
s.set(ValueLayout.JAVA_BYTE, 0L, (byte) 11);
System.out.println(a[0]);
~~~

**Đáp án:** `11`, vì `s` truy cập trực tiếp backing array `a`.

### Bài tập 2 — nhận diện mapped

Với `FileChannel.map(READ_WRITE, 0, 100, arena)`, `isNative()` và `isMapped()` trả gì? **Đều `true`.** Với `arena.allocate(100)`, `isNative()==true` và `isMapped()==false`.

### Bài tập 3 — phạm vi của arena

Một `MemorySegment` lấy từ `Arena.ofConfined` được giữ trong field sau khi `arena.close()`. Lệnh `get` sau đó có hợp lệ không? **Không**, sẽ bị kiểm tra temporal bounds và ném `IllegalStateException`, dù Java object của segment còn referenced.

### Bài tập 4 — thread

Một thread T1 tạo confined arena và allocate segment. T2 gọi `segment.get(...)` khi arena còn alive. Có được không? **Không** vì thread confinement; kỳ vọng `WrongThreadException`. Nếu muốn chia sẻ, cần lựa chọn arena, synchronization và lifecycle phối hợp.

### Bài tập 5 — force

Một read-only mapping được gọi `force()`. Có phải thao tác ghi dữ liệu mới xuống tệp không? **Không.** Với read-only/private mapping, `force` có thể không có tác dụng ghi file. Với `READ_WRITE` trên local storage, `force()` là cơ chế yêu cầu flush changes theo hợp đồng API.

### Bài tập 6 — chọn giải pháp

Bạn cần API trao đổi một buffer 4 KiB với hàm native C, xử lý xong rồi trả resource ngay. **Gợi ý:** `try (Arena arena = Arena.ofConfined())` và allocate đúng layout/alignment; không dùng global arena. Nếu dữ liệu gốc ở Java heap, copy/transfer theo yêu cầu API để lifetime native buffer được kiểm soát.

## 14. Checklist review trước khi sử dụng MemorySegment

1. **JDK:** đã dùng `java.lang.foreign` ổn định của JDK 22+ hay đang nhầm với API incubator của JDK cũ?
2. **Nguồn backing:** từ Java array, native allocation hay file mapping?
3. **Loại:** đã hiểu `isNative` và `isMapped` (mapped ⇒ native) chưa?
4. **Byte size và offset:** mọi `get`/`set` có nằm trong `byteSize()` và layout alignment đúng không?
5. **Endian và layout:** đã khớp định dạng file/native ABI, không phụ thuộc tình cờ vào CPU?
6. **Aliasing:** `ofArray`/`asSlice` là view cùng backing; nếu cần copy riêng đã thực hiện đúng chưa?
7. **Ownership:** ai giữ arena, ai close và khi nào? Có access sau scope đã đóng không?
8. **Thread:** confined/shared/auto/global có phù hợp với cách sử dụng? Có concurrent read/write/close race không?
9. **Native calls:** nếu truyền cho C, pointer có đúng ABI và còn sống hết thời gian dùng không?
10. **Mapped file:** file mapping mode, file size, external truncation/writers, flush, exceptions và close được quản lý thế nào?
11. **Performance:** số lần copy, page faults, RSS/native pressure và kích thước file đã được đo trên workload thật chưa?
12. **Cleanup:** `try-with-resources` có đóng channel/arena đúng thứ tự? File tạm chỉ xóa sau khi mapping kết thúc?

## Tài liệu chuẩn

- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): heap/native, `isNative`/`isMapped`, `get`/`set`, alignment, slicing, mapped `force`.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): `ofConfined`, `ofShared`, `ofAuto`, `global`, scope và lifetime.
- [Java SE 22 — FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): `map(MapMode, long, long, Arena)` và các lưu ý file/mapping.
- [Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): kích thước, byte order và alignment.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM trở thành API chuẩn trong JDK 22.

## Ghi nhớ

**Phân biệt backing storage trước khi chọn API:**

- **Heap segment:** `MemorySegment.ofArray(...)` bao bọc mảng Java, chia sẻ dữ liệu với mảng và để GC quản lý backing array.
- **Allocated native segment:** `Arena.allocate(...)` xin vùng nhớ off-heap mới, không tự liên kết với file; lifetime phụ thuộc arena.
- **Mapped file segment:** `FileChannel.map(..., arena)` tạo **native segment đặc biệt** gắn với file, có `isMapped()==true`; `MapMode` và `force()` điều khiển cách cập nhật file, còn arena kiểm soát vòng đời mapping.

`MemorySegment` mang kiểm tra **bounds**, **scope lifetime** và **thread access**, nhưng không thay thế thiết kế ownership, synchronization hoặc cơ chế bảo vệ trước việc file hay mã native khác thay đổi backing storage. Chọn đúng nguồn backing, giữ arena sống đủ lâu, kiểm tra layout và đóng tài nguyên rõ ràng.
