# Arena.ofAuto, GC và thời điểm giải phóng không xác định trong Java FFM

`Arena.ofAuto()` là một trong bốn cách tạo `Arena` của Foreign Function & Memory API (FFM). Điểm khác biệt quyết định là vùng nhớ native do arena cấp được **quản lý thu hồi bởi garbage collector (GC)** thay vì được ứng dụng chủ động giải phóng ở một lệnh `close()` xác định.

**Không nhầm GC-managed với free ngay:** tài liệu Java 22 quy định các native regions thuộc automatic arena được giải phóng tại một **thời điểm không xác định**, sau khi **bản thân arena và tất cả memory segments được cấp từ nó không còn reachable**. Việc ra khỏi method, gán một biến bằng `null`, hoặc gọi `System.gc()` không bảo đảm bộ nhớ native đã được giải phóng ngay lúc đó.

`Arena.ofAuto()` thích hợp khi chấp nhận lifetime không xác định và đã kiểm soát chi phí native memory. Nếu cần thu hồi ngay khi request/batch/tác vụ xong, nên dùng `Arena.ofConfined()` hoặc `Arena.ofShared()` với owner và `close()` rõ ràng. Đây là quyết định **quản lý tài nguyên**, không chỉ khác biệt cú pháp.

**Phiên bản:** các đoạn Java runnable trong bài dùng **JDK 22+**, khi FFM finalized theo JEP 454. Java 17 dùng incubator API khác; Java 19–21 dùng preview API có khác biệt. Không chép mã `java.lang.foreign.Arena` trong bài sang Java 17 và kỳ vọng biên dịch không thay đổi.

## 1. Hiểu đúng vòng đời của một automatic arena

Một lần cấp phát thường có dạng:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

Arena arena = Arena.ofAuto();
MemorySegment segment = arena.allocate(
        2L * Integer.BYTES,
        ValueLayout.JAVA_INT.byteAlignment());

segment.setAtIndex(ValueLayout.JAVA_INT, 0, 12);
segment.setAtIndex(ValueLayout.JAVA_INT, 1, 30);
int answer = segment.getAtIndex(ValueLayout.JAVA_INT, 0)
           + segment.getAtIndex(ValueLayout.JAVA_INT, 1);
// answer == 42
```

Đây là đoạn **minh họa trong một Java method**, chưa phải class chạy độc lập. Nó cấp 8 byte native (hai `int`, mỗi giá trị 4 byte), căn lề theo `ValueLayout.JAVA_INT`, rồi ghi/đọc. `MemorySegment` là Java object mô tả địa chỉ, kích thước và scope của vùng native. Bản thân object Java **không phải** vùng native 8 byte đó.

```text
GC roots trong JVM
      |
      +--> Arena auto --------+
      |                       |
      +--> MemorySegment A ---+--> native bytes của A
      |                       |
      +--> MemorySegment B ---+--> native bytes của B
               |
               +--> Slice/View (cùng arena scope)

Còn reference tới arena hoặc một segment liên quan
    -> chưa thể suy ra cả nhóm native memory đã được giải phóng.

Arena và TẤT CẢ segments liên quan đều unreachable
    -> các native regions đủ điều kiện được GC-managed deallocate
       ở MỘT THỜI ĐIỂM KHÔNG XÁC ĐỊNH.
```

Một automatic arena có thể cấp nhiều segments. Chúng cùng gắn với **arena scope**. Khi nói về điều kiện GC, phải xét cả nhóm, không chỉ một biến `segment` trong một block code.

## 2. Ba tầng cần phân biệt: Java object, native allocation, scope

| Tầng | Chứa gì? | Ai quản lý? | Điểm dễ nhầm |
| --- | --- | --- | --- |
| Java references | `Arena`, `MemorySegment` và các aliases/views | Java GC/reachability | Reference mất không có nghĩa native bytes free ngay |
| Native backing memory | Bytes nằm ngoài Java heap | Arena/JVM hoặc native allocator phù hợp | Không đo đầy đủ qua Java heap usage |
| Arena scope | Ràng buộc lifetime và quyền truy cập của segments | Arena và FFM runtime | `scope().isAlive()` không phải đồng hồ báo lúc GC free |

`Arena.ofAuto()` tạo một **automatic scope**. Java GC quản lý thời điểm vùng backing memory được thu hồi khi điều kiện reachability được đáp ứng. Automatic scope khác với closeable scope của confined/shared arena: programmer không có phép đóng thủ công để buộc kết thúc vòng đời.

Một Java object `MemorySegment` có thể nhỏ so với allocation của nó. Ví dụ một segment đại diện cho vùng 128 MiB off-heap không nhất thiết khiến Java heap tăng 128 MiB. Ứng dụng chỉ nhìn heap chart có thể bỏ qua áp lực memory ở cấp tiến trình/container.

## 3. `Arena.ofAuto()` bảo đảm điều gì?

Theo Javadoc FFM Java 22:

1. `Arena.ofAuto()` tạo **automatic arena** do GC quản lý.
2. Các vùng native memory được allocate từ arena **zero-initialized**; đọc giá trị nguyên thủy trước khi ghi sẽ thấy toàn byte 0 (nếu layout/offset hợp lệ).
3. Segments của automatic arena **có thể truy cập từ mọi Java thread**, không bị giới hạn một owner thread như confined arena.
4. **`auto.close()` ném `UnsupportedOperationException`**. Automatic arena không hỗ trợ manual close.
5. Native regions chỉ **được giải phóng ở một thời điểm không xác định sau khi automatic arena và mọi segments của nó không còn reachable**.

Cũng có những điều **không được bảo đảm**:

- Không có SLA như 10 ms, 1 giây hoặc một chu kỳ GC cụ thể để free.
- Không có bảo đảm `System.gc()` sẽ cleanup ngay.
- Không phải lời hứa RSS sẽ giảm ngay sau GC.
- Không tự đồng bộ các phép đọc/ghi shared native memory.
- Không tự duy trì lifetime cho một raw pointer C mà Java không còn giữ references tương ứng.
- Không giải phóng các native resources khác (socket, global native state, file descriptor) chỉ vì một Java automatic arena hết reachability.

`Arena.ofAuto()` là một lựa chọn **ownership/lifetime policy**, không phải API hủy toàn bộ tài nguyên native của chương trình.

## 4. Bảng so sánh bốn loại Arena

| Loại | Lifetime | Có `close()` tường minh? | Thread access | Khi nào chọn |
| --- | --- | --- | --- | --- |
| `Arena.ofConfined()` | Hữu hạn, có điểm đóng xác định | **Có**, owner thread đóng | Chỉ owner thread | Xử lý đồng bộ, resource dùng trong một method |
| `Arena.ofShared()` | Hữu hạn, có điểm đóng xác định | **Có**, điều phối close sau khi consumers xong | Mọi threads | Buffer dùng bởi nhiều workers/callbacks có lifecycle riêng |
| **`Arena.ofAuto()`** | Hữu hạn, **thời điểm GC deallocate không xác định** | **Không**; gọi close ném `UnsupportedOperationException` | Mọi threads | Native data ngắn/vừa hạn, chấp nhận cleanup do GC quản lý |
| `Arena.global()` | Không giới hạn trong đời VM | **Không**; gọi close ném `UnsupportedOperationException` | Mọi threads | Dữ liệu chủ đích tồn tại suốt đời JVM |

`ofAuto` và `global` đều không close được nhưng **không đồng nghĩa**. Automatic có điều kiện GC-managed deallocation; global có lifetime không giới hạn và vùng native của nó không được tự giải phóng trong đời VM. Đừng dùng `global()` như bản thay thế "auto nhưng nhanh hơn" cho các allocations lặp lại.

Ngược lại, `ofConfined` và `ofShared` được thiết kế để ứng dụng có thể quyết định chính xác khi nào kết thúc lifetime. Nếu close thành công, backing native regions được deallocate và accesses qua segments liên quan không còn hợp lệ.

## 5. Vì sao unreachable khác already freed?

Xét ví dụ:

```java
// Minh họa khái niệm; không dùng để assert thời điểm GC.
MemorySegment segment = Arena.ofAuto().allocate(1024);
segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);

// ... dùng segment ...

segment = null;
// Không có bảo đảm 1024 native bytes đã free ngay tại đây.
```

Có ba trạng thái cần tách rõ:

1. **Still reachable:** một đường tham chiếu từ GC roots vẫn giữ arena/segment/alias sống. Bộ nhớ chưa đạt điều kiện reachability để được dọn theo automatic arena.
2. **Eligible for GC-managed cleanup:** arena **và tất cả segments của nó** đã không còn reachable. JVM có thể xử lý giải phóng native memory về sau.
3. **Actually deallocated:** cleanup thực sự diễn ra. Tài liệu không công bố thời hạn từ trạng thái 2 tới trạng thái 3.

Thêm một điểm: kể cả khi runtime/allocator đã free một khối native memory, **RSS có thể chưa giảm** vì native allocator hoặc OS có thể giữ pages để tái sử dụng. Vì thế một quan sát RSS tĩnh không phân biệt được tất cả các trạng thái trên.

Dòng `segment = null` cũng chỉ bỏ **một** tham chiếu. Nếu một cache giữ slice, một callback giữ segment khác, hoặc biến arena vẫn còn reachable, không được kết luận điều kiện của cả nhóm đã đáp ứng.

### Scope không trùng hoàn toàn với phạm vi cặp ngoặc nhọn

```java
// Đây là ví dụ minh họa, không phải một class độc lập.
MemorySegment outside;
{
    Arena automatic = Arena.ofAuto();
    outside = automatic.allocate(4);
}
// outside vẫn có thể dùng vùng native ở thời điểm này;
// rời block KHÔNG gọi close() và không buộc GC thu hồi.
outside.set(ValueLayout.JAVA_INT, 0, 5);
```

Trong ví dụ này, `outside` tiếp tục giữ segment reachable. Rời scope **từ vựng** của biến `automatic` không giống kết thúc **FFM arena scope**.

## 6. Một segment còn dùng có thể giữ cả nhóm allocations

Một automatic arena có thể cấp nhiều segments có vòng đời sử dụng không giống nhau:

```java
// Minh họa retention, không phải benchmark chạy độc lập.
Arena automatic = Arena.ofAuto();

MemorySegment large = automatic.allocate(64L * 1024 * 1024);
MemorySegment tiny = automatic.allocate(4);

large = null;
// tiny vẫn được dùng; automatic cũng còn referenced ở đây.
tiny.set(ValueLayout.JAVA_INT, 0, 1);
```

Không được khẳng định buffer 64 MiB đã được giải phóng riêng vì biến `large` trở thành null. Điều kiện từ Javadoc áp dụng ở cấp automatic arena **và tất cả memory segments do nó cấp**. Nếu một segment hoặc một reference tới arena tồn tại lâu, native memory của cả nhóm có thể bị giữ lâu hơn mong đợi.

Trường hợp nguy hiểm là dùng **một automatic arena duy nhất** để cấp nhiều buffer lớn cho các requests khác nhau, rồi lưu một số segments nhỏ của arena ấy vào cache dài hạn. Lifetime của cache nhỏ có thể không tương thích với đời của các buffers lớn.

**Cách thiết kế tốt hơn:** tách arenas theo lifetime, hoặc chỉ giữ **Java primitive/value object** nếu cần 4 byte trạng thái. Với buffer lớn có thời điểm xử lý kết thúc rõ, dùng closeable arena và giải phóng ở đó thay vì để GC suy đoán.

### Aliases và views cũng quan trọng

`segment.asSlice(...)` tạo một segment mới có view/bounds riêng nhưng cùng arena scope; `segment.asReadOnly()` cũng không cấp một arena lifetime độc lập. Nếu một Java object, collection, lambda hoặc task vẫn giữ những views này, việc chỉ gán reference gốc thành null không nhất thiết làm backing memory đủ điều kiện thu hồi.

`segment.asByteBuffer()` tạo một Java `ByteBuffer` view vào segment. Khi chia sẻ buffer/view qua các tầng, phải coi chúng là **các aliases có thể kéo dài reachability** và tuân thủ cùng lifetime contract, không chỉ nhìn field lưu original `MemorySegment`.

## 7. Ví dụ Java 22+ chạy được, không phụ thuộc thời điểm GC

Chương trình sau minh họa **các hành vi xác định** theo FFM API. Nó cố ý **không** gọi `System.gc()` và **không** in thông báo "memory freed", vì thời điểm cleanup của automatic arena không thể được bảo đảm bằng một bài thử ngắn.

Chương trình cho thấy:

- Vùng native của auto arena ban đầu bằng 0.
- `byteSize`, `get`, `set` và `asSlice` cho kết quả đúng.
- Segment của auto arena truy cập được từ worker thread.
- `auto.close()` gây `UnsupportedOperationException`, và lần close thất bại không làm invalidated segment.
- Confined arena đóng được, sau close mọi segment của nó không còn truy cập được.

### File `AutoArenaGcDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class AutoArenaGcDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Arena auto = Arena.ofAuto();
        MemorySegment values = auto.allocate(
                2L * Integer.BYTES,
                ValueLayout.JAVA_INT.byteAlignment());

        System.out.println("bytes=" + values.byteSize());
        System.out.println("initial=" +
                values.getAtIndex(ValueLayout.JAVA_INT, 0));

        values.setAtIndex(ValueLayout.JAVA_INT, 0, 12);
        values.setAtIndex(ValueLayout.JAVA_INT, 1, 30);

        MemorySegment second = values.asSlice(
                Integer.BYTES, Integer.BYTES);
        int sum = values.getAtIndex(ValueLayout.JAVA_INT, 0)
                + second.get(ValueLayout.JAVA_INT, 0);

        System.out.println("sum=" + sum);
        System.out.println("autoAlive=" +
                auto.scope().isAlive());

        Thread worker = new Thread(() -> {
            int value = second.get(ValueLayout.JAVA_INT, 0);
            System.out.println("workerRead=" + value);
        });
        worker.start();
        worker.join();

        try {
            auto.close();
            System.out.println("unexpectedCloseSuccess");
        } catch (UnsupportedOperationException expected) {
            System.out.println(
                    "autoClose=UnsupportedOperationException");
        }

        System.out.println("afterCloseAttempt=" +
                values.getAtIndex(ValueLayout.JAVA_INT, 0));

        MemorySegment escaped;
        try (Arena confined = Arena.ofConfined()) {
            escaped = confined.allocate(ValueLayout.JAVA_INT);
            escaped.set(ValueLayout.JAVA_INT, 0, 7);
            System.out.println("confinedInside=" +
                    escaped.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpectedAccessAfterClose");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "confinedAfterClose=IllegalStateException");
        }

        System.out.println("end");
    }
}
```

### Biên dịch và chạy

Dùng **JDK 22+**, `javac` và `java` thuộc cùng JDK. FFM đã finalize ở JDK 22, nên mã này không cần `--enable-preview`. Mã chỉ cấp/đọc/ghi memory, không gọi restricted foreign function, do đó cũng không cần `--enable-native-access` cho ví dụ.

```bash
java -version
javac AutoArenaGcDemo.java
java AutoArenaGcDemo
```

`java -version` in version tùy môi trường; phần stdout xác định của lệnh `java AutoArenaGcDemo` là:

```text
bytes=8
initial=0
sum=42
autoAlive=true
workerRead=30
autoClose=UnsupportedOperationException
afterCloseAttempt=12
confinedInside=7
confinedAfterClose=IllegalStateException
end
```

### Vì sao ra các kết quả đó?

1. `bytes=8` vì hai `int`, mỗi phần tử 4 byte.
2. `initial=0` do native region mới cấp bằng auto arena được zero-initialized.
3. `sum=42` vì phần tử 0 = 12 và slice ở offset 4 chứa phần tử 1 = 30.
4. `autoAlive=true` vì auto arena/segment đang được dùng trong method. Đây không phải lời hứa về thời điểm future GC.
5. `workerRead=30` vì automatic arena cho phép truy cập từ thread khác; `join()` ổn định thứ tự output.
6. `autoClose=UnsupportedOperationException` vì automatic arena không cho explicit close.
7. `afterCloseAttempt=12` minh họa close thất bại không giải phóng memory.
8. `confinedInside=7` trong `try-with-resources`; sau khi confined arena đóng, thao tác `get` gây `IllegalStateException`.
9. Không in thời gian native free; tài liệu FFM **không quy định** một thời gian có thể assert như vậy cho `ofAuto()`.

Điểm đáng học là phân biệt **hành vi xác định** của API với **lịch trình GC bất định**.

## 8. Vì sao không dùng try-with-resources với `ofAuto()`?

Mọi `Arena` implements `AutoCloseable`, nên đoạn sau có thể **biên dịch**, nhưng sai về lựa chọn lifetime:

```java
// Minh họa lỗi; đặt trong method của class Java 22+.
try (Arena arena = Arena.ofAuto()) {
    MemorySegment segment = arena.allocate(16);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
}
// Khi rời block, try-with-resources gọi arena.close():
// UnsupportedOperationException.
```

`AutoCloseable` không có nghĩa mọi loại arena đều hỗ trợ close theo contract. `Arena.ofAuto()` và `Arena.global()` **không cho đóng thủ công**. Nếu kỳ vọng exit block giải phóng native memory ngay, hãy thay bằng:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
} // close() thành công: các native regions được deallocate.
```

Nếu buffer phải được worker thread khác truy cập, thay `ofConfined()` bằng `ofShared()` **và chờ mọi worker/callback hoàn tất trước khi close**. Không coi `ofShared` là giải pháp thay thế hoàn toàn cho concurrency coordination.

## 9. GC không có deadline; System.gc không phải free

`System.gc()` gửi một yêu cầu JVM cân nhắc GC. Nó không cung cấp một hợp đồng để ứng dụng nói:

- GC chắc chắn đã chạy toàn bộ trước khi lời gọi trả về.
- Automatic arena không còn referenced sẽ được cleanup ngay lập tức.
- Native pages được trả về OS ngay sau cleanup.
- RSS bắt buộc giảm một lượng nhất định sau một lần GC.
- Chương trình có thể dựa vào 100 ms hoặc 5 giây để giải phóng bộ nhớ auto.

Ví dụ sau **không phải kiểm thử đúng**:

```java
// Mã minh họa chống-mẫu; không phải benchmark hợp lệ.
MemorySegment block = Arena.ofAuto().allocate(1024 * 1024);
block = null;
System.gc();
// SAI nếu khẳng định ở đây 1 MiB native đã được free.
```

Một JVM có thể trì hoãn hoặc không thực hiện explicit GC theo cấu hình; ngay cả khi cleanup xảy ra, native allocator/OS không nhất thiết giảm chỉ số RSS ngay. Kiểm thử dựa trên `Thread.sleep(...)` sau `System.gc()` cũng flake và không thành một bảo đảm portable.

### WeakReference có chứng minh native free không?

Không. Một `WeakReference<MemorySegment>` chỉ cung cấp quan sát về **Java referent được weakly referenced**, không chứng minh mọi segment của arena đã không còn reachable, cleanup native đã chạy, hay OS đã thu hồi pages. Dùng weak references để chẩn đoán reachability có thể hữu ích, nhưng **không** dùng kết quả một weak reference như đồng hồ free memory.

### Cleaner có biến auto thành deterministic không?

Không. `Cleaner` cũng gắn với reachability/GC và không có deadline giống `finally` hay `try-with-resources`. Đừng đăng ký một cleaner khác để tự `free` buffer của `Arena.ofAuto()`; JVM/arena đã sở hữu allocation đó. Tự áp một allocator/free sai lên vùng này có thể gây double-free/corruption. Với resource native bên ngoài, cần rõ ownership và cleanup callback phù hợp, không thêm cleaner theo cảm tính.

## 10. `ofAuto()` cho mọi thread truy cập, nhưng không tự đồng bộ dữ liệu

FFM phân biệt **thread accessibility** với **data-race freedom**. Automatic arena không bị owner-thread restriction của confined arena, nên một worker có thể gọi `segment.get(...)` khi segment còn hợp lệ. Tuy nhiên, hai threads cùng sửa một giá trị bằng read-modify-write có thể mất cập nhật:

```java
// Đoạn minh họa trong method; 'counter' là MemorySegment
// từ automatic/shared arena.
int oldValue = counter.get(ValueLayout.JAVA_INT, 0);
counter.set(ValueLayout.JAVA_INT, 0, oldValue + 1);
```

Nếu hai threads chạy đồng thời, kết quả không được bảo đảm chính xác chỉ vì arena là `ofAuto()`. Cần synchronization, memory ordering hoặc `VarHandle` với atomic operations thích hợp cho layout, địa chỉ và ABI. Thread-safe access vào segment không làm một tổ hợp `get` + `set` thành atomic transaction.

Dùng `Arena.ofShared()` cũng không tự giải quyết race; nó chỉ cho phép multi-thread access và **có thêm explicit close** theo hợp đồng. Vì vậy quyết định auto/shared dựa trên **lifetime**, còn quyết định lock/atomic dựa trên **concurrency**.

## 11. Đặc biệt nguy hiểm: native C giữ pointer sau khi Java bỏ reference

Một chương trình FFM có thể truyền địa chỉ native sang C. Giả sử C lưu một `void*` vào global variable để callback sử dụng về sau:

```c
/* C declarations minh họa, không phải chương trình độc lập. */
void native_store_pointer(void *buffer);
void native_use_later(void);
```

Nếu Java **không giữ** một strong reference đến arena hoặc segment trong suốt thời gian native cần pointer, JVM GC không đương nhiên biết C global variable đang chứa raw pointer đó. Khi automatic arena đủ điều kiện cleanup và backing memory bị giải phóng, C đọc pointer cũ có thể gây **use-after-free**.

```text
Java MemorySegment ----> native allocation
      |
      +-- C nhận raw address và lưu để dùng sau
      |
Java bỏ hết owner references
      |
automatic arena có thể GC-managed deallocate
      |
C vẫn đọc raw pointer cũ ----> memory corruption / crash
```

FFM kiểm tra temporal/spatial safety khi code truy cập qua `MemorySegment` với metadata hợp lệ. Nhưng **C dereference raw pointer nằm ngoài những kiểm tra Java này**. Automatic arena không biến mọi pointer C thành một Java GC root.

### Hướng xử lý

- Nếu C chỉ sử dụng buffer trong **một downcall đồng bộ**, giữ segment sống xuyên suốt thao tác. Khi phải thao tác với địa chỉ thô và cần ngăn JVM/JIT rút ngắn liveness, xem `java.lang.ref.Reference.reachabilityFence(segment)` ở điểm sau lần dùng cuối; lệnh này **không giải phóng** native memory và không làm hợp lệ những con trỏ đã hỏng.
- Nếu C **giữ pointer để xử lý bất đồng bộ**, thiết kế một owner có lifetime tường minh (thường confined/shared tùy threads), đợi mọi native work/callback hoàn tất rồi mới close.
- Nếu native subsystem cần **sở hữu riêng vùng nhớ**, dùng API cấp phát/giải phóng phù hợp với native library và hợp đồng copy/ownership rõ, không tùy tiện `free` vùng mà arena cấp.
- Với các phương thức restricted như `MemorySegment.reinterpret(...)`, không khai báo tùy ý kích thước hoặc scope cho một pointer C chưa xác minh. Bounds/scope do Java biết không thể chứng minh native allocation bên ngoài còn sống nếu C đã tự `free` nó.

**Tóm lại:** muốn chia sẻ memory an toàn với C lâu dài, phải quản lý **native ownership**. Không dựa vào auto GC để bảo vệ callback/pointer mà JVM không nhìn thấy.

## 12. Native memory pressure: vì sao heap còn trống vẫn có thể hết RAM?

Java GC theo dõi Java objects và có thể tham gia thu hồi native allocations của automatic arena, nhưng một vùng native lớn không đồng nghĩa heap chứa cùng số byte. Ví dụ một Java `MemorySegment` object nhỏ có thể mô tả nhiều MiB off-heap; việc tăng nhiều native buffers không nhất thiết làm heap usage tăng tương ứng.

Các tình huống dễ gặp:

- Server cấp một automatic arena với buffer lớn cho mỗi request rồi trông chờ GC dọn kịp request rate.
- Image/video/ML jobs cấp native buffers hàng trăm MiB nhưng chỉ nhìn heap chart.
- Một cache giữ segment nhỏ từ arena đã cấp nhiều buffers lớn.
- Async tasks giữ segment references lâu hơn dự kiến.
- C native library giữ pointer nhưng Java đã bỏ references, tạo nguy cơ use-after-free.

**Không có bảo đảm JVM sẽ chạy GC đúng lúc để tránh mọi kiểu native memory exhaustion.** Ứng dụng có thể gặp lỗi cấp phát hoặc bị giới hạn container/OS ngay cả khi Java heap chưa chạm ngưỡng giới hạn.

### Quan sát vận hành

- Đo **process RSS/container memory** cùng với Java heap, không dùng chỉ mỗi heap.
- Ghi metric số bytes native **yêu cầu cấp phát** và số tasks đang hoạt động; tránh gọi một tổng tự tính là "bytes hiện chưa free" nếu không có tín hiệu free chính xác.
- Theo dõi số segments được cache và các owner Java còn giữ references.
- Trên HotSpot, Native Memory Tracking có thể hữu ích nếu được bật phù hợp; nó không bảo đảm bao phủ mọi thư viện/allocator bên ngoài.
- Chạy stress tests ở memory limit sát production; đo peak/steady-state và phân biệt **retention do references** với **cleanup chậm**.
- Không viết unit test assert RSS giảm ngay sau `System.gc()`.

Nếu cần thời gian release có thể dự đoán, **đổi arena type** là giải pháp thiết kế, không phải tăng số lần gọi `System.gc()`.

## 13. Ba mẫu lựa chọn thiết kế

### Mẫu A: buffer tạm đồng bộ, cần giải phóng khi return

```java
// Minh họa trong method trên JDK 22+.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment work = arena.allocate(4096);
    work.set(ValueLayout.JAVA_INT, 0, 123);
    // Xử lý hoàn toàn trên owner thread.
} // Native memory được dọn khi close thành công.
```

Lý do chọn: lifetime của data gắn với một đoạn xử lý xác định. GC không quyết định thời điểm free.

### Mẫu B: buffer dùng bởi nhiều workers, có điểm hoàn thành

```java
// Minh họa cấu trúc; ứng dụng phải định nghĩa workers cụ thể.
try (Arena arena = Arena.ofShared()) {
    MemorySegment work = arena.allocate(4096);
    // Phát work cho workers, đồng bộ dữ liệu nếu cần.
    // Đợi toàn bộ outstanding tasks/callbacks hoàn tất.
} // Close shared arena sau khi hoàn thành mọi consumers.
```

Lý do chọn: nhiều threads cần truy cập, nhưng owner vẫn phải kiểm soát ngày/giờ deallocate. Không đóng arena khi callbacks vẫn còn dùng memory.

### Mẫu C: buffer có lifetime phụ thuộc reference và không cần close đúng lúc

```java
// Minh họa trong method JDK 22+.
MemorySegment data = Arena.ofAuto().allocate(4096);
data.set(ValueLayout.JAVA_INT, 0, 88);
// Dùng data khi còn reachable.
// Không gọi data.scope().close(): automatic scope không closeable.
// Vùng native đủ điều kiện cleanup sau khi arena và mọi
// segments liên quan đều unreachable; thời điểm GC không xác định.
```

Lý do chọn: ứng dụng chấp nhận nondeterministic deallocation, kích thước và tốc độ cấp phát nằm trong memory budget. Nếu data trở thành một cache dài hạn hoặc native C giữ pointer, phải xét lại ownership.

### Trả kết quả ra Java heap để tránh kéo dài lifetime

```java
// Method minh họa, đặt trong class có imports FFM thích hợp.
static long result() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment data = arena.allocate(ValueLayout.JAVA_LONG);
        data.set(ValueLayout.JAVA_LONG, 0, 900L);
        return data.get(ValueLayout.JAVA_LONG, 0);
    }
}
```

Method trả `long` Java, không trả một `MemorySegment` có scope sắp đóng. Đây là giải pháp tốt khi caller chỉ cần giá trị nhỏ chứ không cần zero-copy native buffer.

## 14. Cạm bẫy thường gặp

| Sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `try (Arena a = Arena.ofAuto())` ném lỗi khi rời block | Auto không hỗ trợ explicit close | Dùng confined/shared nếu muốn `try-with-resources` |
| `System.gc()` xong mà RSS không giảm | GC/allocator/OS không có nghĩa vụ giảm RSS ngay | Không suy cleanup từ một phép đo tức thời |
| Đặt `segment = null` rồi cho rằng native free ngay | Có thể còn arena, aliases, segments khác hoặc GC chưa cleanup | Kiểm tra reachability của cả nhóm và chấp nhận độ trễ |
| Cache một segment 4 byte vô tình giữ memory lớn | Các allocations của một auto arena chia sẻ lifetime | Chia arena theo nhiệm vụ/lifetime hoặc copy giá trị nhỏ ra Java |
| Chỉ quan sát heap memory | Auto arena cấp vùng off-heap | Theo dõi RSS/native memory và workload |
| Chuyển sang `Arena.global()` để không lỗi close | Global không giải phóng vùng cấp trong đời JVM | Dùng global chỉ với state cố ý lifetime toàn tiến trình |
| Xem auto arena là single-thread-only | Confined mới giới hạn owner thread | Auto cho đa thread, nhưng cần synchronization khi shared mutable |
| Xem `get` + `set` tự atomic trên auto arena | Thread accessibility khác tính atomic | Dùng lock/VarHandle atomic đúng |
| C giữ pointer native lâu hơn Java giữ segment | GC không thấy C pointer như Java root | Explicit ownership/lifetime contract |
| Dùng `free()` cho memory do arena cấp | Sai allocator owner | Để arena/JVM xử lý vùng đó |
| Test dựa vào `Thread.sleep()` hoặc `WeakReference` để chờ free | Không có deadline native cleanup | Test API behaviors và memory trend, không assert thời điểm |
| Thay đổi `MemorySegment.reinterpret` để né lỗi bounds | Metadata mới có thể không phản ánh allocation thật | Xác minh C pointer size/ownership trước |

## 15. Câu hỏi tự kiểm tra

**1. Một method tạo `MemorySegment s = Arena.ofAuto().allocate(1024)` và return. Có chắc 1024 byte được free ngay không?**

**Không.** Lifetime do GC quản lý; chỉ sau khi arena và tất cả segments liên quan trở nên unreachable thì vùng nhớ mới đủ điều kiện cleanup, tại thời điểm không xác định.

**2. Tại sao `ofAuto` và `global` đều không gọi close nhưng không giống nhau?**

Auto có lifetime hữu hạn do GC quản lý, global có lifetime không giới hạn trong đời JVM. Global regions không được tự dọn theo reachability của một vài Java segment.

**3. Giữ một slice nhỏ từ cùng automatic arena có thể ảnh hưởng vùng nhớ lớn khác không?**

**Có thể.** Slice gắn với arena scope; khi còn references tới arena/segments của cùng nhóm, không thể khẳng định native regions đã đủ điều kiện deallocate. Hãy thiết kế allocations có lifetime khác nhau trong các arenas khác nhau.

**4. Vì sao `System.gc()` không phải cách hoàn trả native buffer của `ofAuto()`?**

`System.gc()` là một yêu cầu GC, không có hợp đồng bảo đảm hoàn thành deallocation cho automatic arena tại thời điểm gọi. Để release xác định, chọn arena closeable từ đầu.

**5. `Arena.ofAuto()` có thể được truy cập bởi hai threads. Có thể bỏ mọi synchronization không?**

Không. Quyền truy cập khác với bảo đảm dữ liệu không có race. Hai threads ghi vào cùng vùng cần synchronization/atomic semantics thích hợp.

**6. Java giữ Java heap chỉ 100 MiB nhưng auto allocations tạo native memory lớn. Điều đó có thể xảy ra không?**

Có. Off-heap native memory không phải Java heap; phải theo dõi cả process/native memory và giới hạn lượng allocation đồng thời.

**7. Nếu C lưu raw address mà Java không giữ segment/arena nữa, auto GC có biết pointer đó phải sống lâu không?**

Không tự động. C pointer không phải Java strong reference tới segment. Khi backing memory được cleanup, native code có thể dùng địa chỉ đã giải phóng. Cần hợp đồng owner/callback.

**8. Chương trình muốn trả memory native ngay khi batch xong, loại arena nào hợp lý?**

Confined nếu một owner thread xử lý; shared nếu nhiều workers và có coordinator đợi hoàn thành. Hai loại này hỗ trợ explicit close, khác auto.

**9. Có thể thử `WeakReference<MemorySegment>` rồi assert native memory freed khi `get()==null` không?**

Không. Một weak reference chỉ theo dõi Java referent; không chứng minh tất cả segments/arena unreachable, cleanup hoàn tất hoặc OS đã giảm RSS.

**10. Khi nào `ofAuto()` là lựa chọn hợp lý?**

Khi dữ liệu không cần release vào một deadline, ứng dụng chấp nhận cleanup bất định, không giữ raw pointers C sau lifetime Java và đã đặt memory budget/monitoring phù hợp.

## 16. Checklist production

Trước khi quyết định dùng `Arena.ofAuto()`:

1. **Version:** JDK 22+ cho FFM finalized; kiểm tra đúng JDK runtime/build.
2. **Bytes:** tính đúng byte count/alignment, tránh allocations lớn vô hạn.
3. **Ownership:** tài liệu hóa ai còn giữ arena/segments, views, callback và caches.
4. **Grouping:** chỉ gom các allocations có lifetime gần nhau vào cùng auto arena.
5. **Close policy:** không dùng `try-with-resources` kỳ vọng close; hiểu `UnsupportedOperationException`.
6. **GC assumption:** không có deadline free; test không assert `System.gc()` đã dọn.
7. **Thread safety:** phân biệt multi-thread accessible với thread-safe data access.
8. **C pointers:** không để native C giữ raw pointer ngoài Java lifetime contract.
9. **Monitoring:** theo dõi process/native memory, không chỉ heap.
10. **Fallback:** nếu cần deterministic deallocation, chuyển sang confined/shared và close đúng lúc.
11. **Memory tests:** kiểm tra peak/steady-state dưới tải, OS/container limit và retained references.
12. **Documentation:** ghi rõ tại sao ứng dụng chấp nhận GC-managed native cleanup thay vì explicit lifetime.

## 17. Tài liệu chính thức

- Oracle Java SE 22 — [`Arena`, automatic arena, GC reachability và thời điểm giải phóng không xác định](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- Oracle Java SE 22 — [`MemorySegment`, spatial/temporal bounds và scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- Oracle Java SE 22 — [`java.lang.foreign` package overview](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- OpenJDK — [JEP 454: Foreign Function & Memory API, finalized trong JDK 22](https://openjdk.org/jeps/454)
- Dev.java — [Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)
- Oracle Java SE 22 — [`System.gc()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html)

**Kết luận:** `Arena.ofAuto()` cấp native memory với **GC-managed lifetime nhưng không xác định lúc thu hồi**. Cần phân biệt **đủ điều kiện được thu hồi** với **đã free**, quản lý reachability của toàn arena/segments và hiểu rằng `close()` không được hỗ trợ. Với tài nguyên lớn hoặc yêu cầu release tại thời điểm rõ ràng, hãy dùng **`Arena.ofConfined()` hoặc `Arena.ofShared()`** và quản lý hoàn tất công việc trước khi close.