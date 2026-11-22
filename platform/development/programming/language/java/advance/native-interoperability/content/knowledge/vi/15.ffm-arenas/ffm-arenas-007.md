# Phân biệt đối tượng MemorySegment còn được giữ với vùng nhớ đã hết hạn

## 1. Vấn đề cốt lõi: một Java object tồn tại không có nghĩa bộ nhớ native còn hợp lệ

Với Java thuần, lập trình viên thường nghĩ: “Nếu tôi vẫn giữ tham chiếu mạnh đến một đối tượng, đối tượng đó chưa bị garbage collector (GC) thu gom, nên tôi vẫn có thể sử dụng nó.” Quy tắc này **không đủ** khi đối tượng Java chỉ là một *view* tới **tài nguyên native có vòng đời độc lập**, điển hình là `java.lang.foreign.MemorySegment` của Foreign Function & Memory API (FFM).

Ví dụ một phương thức giữ `MemorySegment` trong biến Java:

```java
MemorySegment segment;

try (Arena arena = Arena.ofConfined()) {
    segment = arena.allocate(8);
} // Arena.close() đã chạy.

// segment vẫn là Java reference khác null,
// nhưng backing native memory của segment đã hết hạn!
```

Sau khối `try`, có **hai sự thật đồng thời**:

1. Biến `segment` vẫn đang giữ **đối tượng Java** biểu diễn view; nó không tự biến thành `null` và đối tượng không cần bị GC thu gom.
2. `arena.close()` đã **invalidate scope** và giải phóng vùng nhớ off-heap do arena sở hữu. Vì vậy thao tác `segment.get(...)`/`set(...)` sẽ không được phép dù biến Java còn tồn tại.

Sự phân biệt này là trọng tâm của bài:

> **Java reference tồn tại** là vấn đề *reachability của object trên Java heap*. **Vùng nhớ có thể truy cập** là vấn đề *lifetime/scope và quyền truy cập của native backing memory*.

**Yêu cầu phiên bản:** các ví dụ dùng `java.lang.foreign.Arena`, `MemorySegment`, `ValueLayout` ở API chuẩn hoàn thiện từ **JDK 22** (JEP 454). Hãy dùng **JDK 22+**, không yêu cầu `--enable-preview` cho các thao tác truy cập bộ nhớ thông thường. JDK 17 dùng API incubator khác và không biên dịch trực tiếp các đoạn mã này.

### Mục tiêu sau bài

Bạn cần trả lời được:

- Tại sao `segment != null` hoặc biến `final MemorySegment` **không** chứng minh vùng nhớ còn sống?
- Tại sao `segment.scope().isAlive()` có thể trả `false` dù Java object vẫn reachable?
- Vì sao `byteSize()`, `address()` hoặc slice metadata có thể còn đó nhưng không đồng nghĩa được đọc/ghi?
- Khi tạo slice hoặc `ByteBuffer` view, những object view ấy có kéo dài vòng đời native allocation không?
- `Arena.ofConfined` và `Arena.ofShared` khác gì `Arena.ofAuto`/`Arena.global` về quyền đóng và GC?
- Làm sao thiết kế API sở hữu arena tránh trả về một segment đã hết hạn, và cách **copy dữ liệu** nếu phải giữ dữ liệu sau khi đóng?
- Những trường hợp nào FFM chặn bằng exception, và những trường hợp nào sử dụng raw native pointer có thể gây lỗi nghiêm trọng ngoài phạm vi kiểm tra của FFM?

## 2. Ba thực thể khác nhau: wrapper, scope và backing memory

Một segment nên được hiểu qua **ba lớp**, không phải một con trỏ duy nhất:

```text
Java heap                             Native / off-heap memory
---------------------------------     --------------------------------
MemorySegment object (view)
  ├─ byteSize = 16
  ├─ address = A --------------------> [16 bytes at native address A]
  └─ Scope -----------------+
                           |
Arena.ofConfined() ---------+
  └─ close() -> invalidates Scope
                 và giải phóng backing native memory

Sau khi close:
  segment Java object vẫn có thể còn reachable
  Scope.isAlive() == false
  address metadata vẫn có thể bằng A
  native bytes tại A KHÔNG còn thuộc allocation này
  get()/set() trên segment -> IllegalStateException
```

Phân tích:

**(A) `MemorySegment` Java object** là mô tả một view: vị trí bắt đầu, kích thước, cách chia sẻ backing memory, scope/điều kiện sử dụng. Đối tượng Java vẫn có thể được tham chiếu bởi biến, field, collection hoặc closure. Việc còn tham chiếu mạnh ngăn **object Java** trở thành unreachable, nhưng không “mở lại” arena đã đóng.

**(B) `MemorySegment.Scope`** đặt **ranh giới thời gian** (*temporal bounds*) cho các access được quản lý bởi FFM. Mỗi segment liên kết với một scope, truy vấn qua `segment.scope()`. Với segment do arena cấp phát, scope của segment là arena scope. Khi close thành công, scope không còn alive.

**(C) Backing memory** là bytes thực tế: vùng off-heap, mapped file, hoặc mảng trong Java heap. Khi arena quản lý native allocation được đóng, native backing memory có thể được thu hồi và không được tiếp tục dùng. Java object `MemorySegment` không nhất thiết biến mất khi việc thu hồi xảy ra.

**Từ vựng:** `MemorySegment` không phải bản thân allocation. Nó là *view của allocation*. Một allocation có thể có nhiều views (segment gốc, slice, read-only view, `ByteBuffer` view), cùng chịu ràng buộc vòng đời tương ứng.

## 3. Bốn phép kiểm tra khác nhau, đừng đánh đồng

| Câu hỏi | Cách kiểm tra/khái niệm | Diễn giải đúng |
| --- | --- | --- |
| Có Java reference? | `segment != null` | Biến đang trỏ tới một Java object, **không nói gì về lifetime của backing allocation** |
| Native backing được gắn scope còn sống? | `segment.scope().isAlive()` | Cho biết trạng thái **hiện tại** của scope; không thay thế access-time checks |
| Có đủ bytes để đọc? | `segment.byteSize()`, offset, `ValueLayout.byteSize()` | Kiểm tra **spatial bounds**; đủ kích thước cũng không chứng minh scope còn sống |
| Thread có quyền truy cập? | `segment.isAccessibleBy(Thread.currentThread())` | Kiểm tra giới hạn **thread confinement**; không bảo đảm scope/offset hợp lệ |
| Địa chỉ có căn chỉnh đúng? | `segment.maxByteAlignment()` và `ValueLayout.byteAlignment()` | Điều kiện alignment; không chứng minh lifetime |
| Backing còn đọc được qua FFM? | `segment.get(layout, offset)` | Truy cập được thực hiện với các kiểm tra liên quan: scope, thread, bounds, alignment… |

Đừng dùng suy luận kiểu:

```java
if (segment != null && segment.byteSize() >= 8) {
    // SAI nếu arena đã đóng.
    long value = segment.get(ValueLayout.JAVA_LONG, 0);
}
```

Cũng không được coi:

```java
if (segment.scope().isAlive()) {
    // Không phải một "giấy phép" dùng raw native pointer vô thời hạn.
    nativeOperation(segment.address());
}
```

là một giao thức vòng đời đầy đủ nếu thread khác có thể đóng arena **giữa lúc kiểm tra và lúc native operation dùng pointer**.

**Mấu chốt:** `isAlive()` là quan sát một thời điểm, không phải “khóa” arena. Với những FFM access được quản lý, API kiểm tra tính hợp lệ tại lúc access và bảo vệ theo hợp đồng. Khi chuyển sang **raw pointer ngoài FFM**, bạn phải xây dựng riêng quy tắc ownership, lifetime và đồng bộ.

## 4. Đóng arena: object có thể còn, bytes đã hết hạn

### 4.1. Arena chịu trách nhiệm lifetime

Một arena điều phối việc cấp phát và giải phóng native memory:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);
    segment.set(ValueLayout.JAVA_LONG, 0, 100L);
    System.out.println(segment.get(ValueLayout.JAVA_LONG, 0)); // 100
} // close() được gọi ở cuối try-with-resources.
```

Khi `Arena.close()` **hoàn tất thành công**:

1. Arena scope chuyển sang trạng thái **không alive**.
2. Những memory segments gắn scope đó không còn được dùng để access.
3. Vùng off-heap do arena cấp phát được deallocate theo cơ chế arena.
4. Các object Java `MemorySegment` có thể **vẫn tồn tại**, nhưng giờ biểu diễn view **đã bị invalidate**.

Vì vậy `MemorySegment` không có một nút `close()` riêng làm vùng của nó sống lâu hơn arena. **Arena mới là owner về mặt giải phóng** đối với những native allocations do nó cấp phát.

### 4.2. Trạng thái sau close không làm object biến thành null

Ví dụ hợp lệ:

```java
MemorySegment remembered;
try (Arena arena = Arena.ofConfined()) {
    remembered = arena.allocate(8);
}
System.out.println(remembered != null);           // true
System.out.println(remembered.scope().isAlive()); // false
```

Truy cập vùng nhớ:

```java
try {
    remembered.get(ValueLayout.JAVA_BYTE, 0);
} catch (IllegalStateException expected) {
    System.out.println("Already closed");
}
```

Trên API FFM chuẩn, đây là **lỗi quản lý vòng đời bị chặn** thay vì đọc bytes đã free. Kiểu `IllegalStateException` ở đây có ý nghĩa khác `NullPointerException`: object còn, **scope đã đóng**.

### 4.3. Metadata không phải “quyền sử dụng”

Sau close, những đặc điểm mô tả view như `byteSize()` hoặc giá trị `address()` có thể vẫn đọc được theo API. **Sự tồn tại của metadata chỉ là dữ liệu về view**, không phải phép thử xem pointer C vẫn còn hiệu lực.

Ví dụ sau khi arena đóng có thể vẫn in:

```text
Segment retained: true
Scope alive: false
Size metadata: 16
Address metadata unchanged: true
```

Điều này **không** hàm ý 16 bytes ở địa chỉ cũ còn thuộc allocation của bạn. Trình cấp phát có thể tái sử dụng địa chỉ ấy cho mục đích khác; dereference raw pointer ở địa chỉ cũ có thể gây use-after-free, ghi đè dữ liệu hoặc crash.

Không nên lấy `address() != 0`, `byteSize() > 0` hay `maxByteAlignment() >= 8` làm điều kiện quyết định vùng native đã được cấp phát hay chưa được free.

## 5. Chương trình chạy được: giữ cả segment, slice, ByteBuffer sau close

Ví dụ này chứng minh **độc lập giữa Java reachability và native lifetime** bằng ba view của **cùng một native allocation**.

### 5.1. Tệp SegmentLifetimeDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class SegmentLifetimeDemo {
    public static void main(String[] args) {
        MemorySegment retained;
        MemorySegment slice;
        ByteBuffer view;
        long oldAddress;

        try (Arena arena = Arena.ofConfined()) {
            retained = arena.allocate(16, 8);
            retained.set(ValueLayout.JAVA_INT, 0, 2026);

            slice = retained.asSlice(0, 4);
            view = retained.asByteBuffer().order(ByteOrder.nativeOrder());
            oldAddress = retained.address();

            System.out.println("In scope: "
                    + retained.scope().isAlive());
            System.out.println("Read in scope: "
                    + slice.get(ValueLayout.JAVA_INT, 0));
            System.out.println("Buffer in scope: "
                    + view.getInt(0));
        } // Đóng arena; cả ba view không giữ allocation tiếp tục mở.

        System.out.println("Segment retained: " + (retained != null));
        System.out.println("Scope alive: "
                + retained.scope().isAlive());
        System.out.println("Slice scope alive: "
                + slice.scope().isAlive());
        System.out.println("Size metadata: " + retained.byteSize());
        System.out.println("Address metadata unchanged: "
                + (retained.address() == oldAddress));

        try {
            retained.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Segment read after close: blocked");
        }

        try {
            slice.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Slice read after close: blocked");
        }

        try {
            view.getInt(0);
        } catch (IllegalStateException expected) {
            System.out.println("Buffer read after close: blocked");
        }
    }
}
```

**Chạy với JDK 22+:**

```bash
javac SegmentLifetimeDemo.java
java SegmentLifetimeDemo
```

**Stdout đã kiểm tra trên JDK 24:**

```text
In scope: true
Read in scope: 2026
Buffer in scope: 2026
Segment retained: true
Scope alive: false
Slice scope alive: false
Size metadata: 16
Address metadata unchanged: true
Segment read after close: blocked
Slice read after close: blocked
Buffer read after close: blocked
```

### 5.2. Phân tích kết quả

- `retained != null` là `true`; điều đó chứng minh Java object vẫn được giữ bởi biến sau khi arena đóng.
- `retained.scope().isAlive()` là `false` vì `Arena.close()` đã invalidate scope.
- `slice` được tạo trước close bằng `asSlice(0, 4)`; nó có view riêng nhưng **dùng cùng backing region và scope**. Vì vậy slice cũng bị invalidate.
- `ByteBuffer view` được tạo bằng `asByteBuffer()` và còn một Java reference. Nó **không biến thành bản copy độc lập**: khi arena đóng, byte buffer view liên kết với segment này cũng không được truy cập bình thường.
- `byteSize()` vẫn là 16; metadata tồn tại sau close không cấp phép access.
- So sánh `retained.address() == oldAddress` vẫn đúng trong ví dụ, nhưng giá trị địa chỉ cũ không còn là pointer dùng được.
- Ba lần truy cập `get`/`getInt` cuối đều gặp `IllegalStateException`; **đây không phải GC xóa object Java**.

**Vì sao dùng `ByteOrder.nativeOrder()`?** `ValueLayout.JAVA_INT` diễn giải bytes theo native byte order; `ByteBuffer` mặc định dùng **big-endian**. Đặt byte order cho view giúp đọc `2026` nhất quán trên các CPU phổ biến, tránh sự lệch endian làm kết quả khó hiểu. Việc đặt byte order **không** thay đổi lifetime.

## 6. Slice, view và collection không kéo dài thời gian sống của arena đóng tường minh

### 6.1. Lưu nhiều Java references có giúp không?

Giả sử:

```java
List<MemorySegment> list = new ArrayList<>();
MemorySegment[] array = new MemorySegment[2];

try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(32, 8);
    list.add(root);
    list.add(root.asSlice(8, 8));
    array[0] = root;
    array[1] = root.asReadOnly();
}

// list và array vẫn giữ Java objects,
// nhưng không làm arena đã đóng quay lại trạng thái alive.
```

Đây là **đoạn mã minh họa**: cần `import java.lang.foreign.*; import java.util.*;`. Không có quy tắc nào nói “cứ còn strong reference tới segment thì arena không được close”. `Arena.ofConfined`/`ofShared` là cơ chế **đóng tường minh**, không chờ GC mất references.

### 6.2. Những thao tác tạo view dùng cùng backing memory

| Thao tác | Tạo bản copy bytes? | Khi arena gốc đóng |
| --- | --- | --- |
| `segment.asSlice(offset, length)` | Không, chỉ tạo sub-view | Slice bị invalidate theo scope |
| `segment.asReadOnly()` | Không; view đọc-only | Vẫn bị invalidate |
| `segment.asByteBuffer()` | Không; view chia sẻ memory | Buffer view không được truy cập sau khi scope đóng |
| `segment.asSlice(...).asByteBuffer()` | Không | Các view lồng nhau vẫn cùng lifetime |
| Lưu `segment` trong field/static/list | Không | Java references có thể tồn tại; native allocation vẫn đóng |
| `segment.toArray(ValueLayout.JAVA_BYTE)` | **Có, sao chép dữ liệu** | Mảng Java copy riêng còn dùng được sau close |
| `MemorySegment.copy(src, ..., dst, ...)` | **Có, sao chép bytes vào backing của dst** | Dữ liệu đích sống theo **scope của dst**, không tự phụ thuộc src |

**Cảnh báo:** với `MemorySegment.copy`, nếu `dst` được cấp phát trong **cùng arena** với `src` thì đóng arena vẫn invalidate cả hai. “Copy” chỉ giải quyết lifetime khi **đích thuộc bộ nhớ/scope còn hợp lệ lâu hơn**, ví dụ một Java byte array hoặc một arena được caller quản lý.

### 6.3. Kéo dài view không đồng nghĩa kéo dài backing allocation

Phương pháp như `asSlice` chỉ thay đổi giới hạn không gian (offset/size), không kéo dài giới hạn thời gian. Mô hình đúng:

```text
Arena A: OPEN ------------------------ CLOSE -----------> CLOSED
             |                           |
root segment |===========================X
slice 1          |=======================X
slice 2                  |===============X
ByteBuffer view              |===========X

Ký hiệu X: mọi access sử dụng chung backing đã kết thúc.
Java objects của các view vẫn có thể tồn tại sau X.
```

## 7. Lỗi trả về một segment từ arena đã bị đóng

### 7.1. Anti-pattern: tạo arena trong helper và return segment ra ngoài

```java
static MemorySegment brokenFactory() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment result = arena.allocate(8, 8);
        result.set(ValueLayout.JAVA_LONG, 0, 77);
        return result; // Java trả object; finally của try đóng arena.
    }
}
```

Khi caller nhận `result`, native allocation **đã bị giải phóng**. Việc Java truyền một object return value qua stack **không giữ arena mở** khi `try-with-resources` đã gọi `close()`.

Điều tương tự xảy ra nếu service lấy segment từ một method rồi đóng arena trong `finally` trước khi hoàn thành callback:

```java
static MemorySegment broken() {
    Arena arena = Arena.ofConfined();
    try {
        return arena.allocate(64);
    } finally {
        arena.close(); // Return xong nhưng segment đã hết hạn.
    }
}
```

Đây không phải leak; nó là **dangling view**. API đúng phải chuyển rõ trách nhiệm về **lifetime owner**, hoặc **copy dữ liệu** trước khi owner đóng.

### 7.2. Cách đúng 1: caller cấp Arena và kiểm soát vòng đời

```java
static MemorySegment createIn(Arena owner) {
    MemorySegment segment = owner.allocate(8, 8);
    segment.set(ValueLayout.JAVA_LONG, 0, 77);
    return segment;
}

static void useResource() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = createIn(arena);
        System.out.println(s.get(ValueLayout.JAVA_LONG, 0));
    } // Caller quyết định đóng tại đây.
}
```

Đây là mẫu **borrowed arena / caller-owned lifetime**: helper chỉ cấp phát vào arena đã nhận, không tự đóng arena của caller. Caller bảo đảm mọi operation, callback hoặc native downcall cần backing memory đều kết thúc trước khi close.

Nếu trả segment cho một object có vòng đời dài hơn phương thức, object đó nên giữ **arena/owner** và có hợp đồng `close()`; không đóng bên trong factory ngay sau khi trả segment.

### 7.3. Cách đúng 2: trả một bản copy sống độc lập

Nếu caller chỉ cần **nội dung**, không cần chung off-heap allocation, hãy copy ra Java heap trước khi đóng:

```java
static byte[] safeCopy() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(8, 8);
        s.set(ValueLayout.JAVA_BYTE, 0, (byte) 17);
        return s.toArray(ValueLayout.JAVA_BYTE);
    }
}
```

Mảng `byte[]` nhận được là storage của Java, không phải view đến native allocation đã đóng. Dĩ nhiên, mảng có nội dung sao chép tại thời điểm gọi `toArray`; nó **không tự cập nhật** khi vùng native gốc thay đổi về sau.

### 7.4. Cách đúng 3: đối tượng sở hữu cả Arena lẫn segment

Thiết kế wrapper:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

final class NativeBlock implements AutoCloseable {
    private final Arena arena = Arena.ofConfined();
    private final MemorySegment block = arena.allocate(32);

    MemorySegment view() {
        if (!block.scope().isAlive()) {
            throw new IllegalStateException("NativeBlock already closed");
        }
        return block;
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

**Đoạn này minh họa kiến trúc**, không phải giao thức đa luồng hoàn chỉnh: với `Arena.ofConfined`, phải gọi từ thread owner; `close` lần hai ném exception theo contract Arena; `view()` trả segment borrowed không thể dùng an toàn ngoài lifetime của `NativeBlock`. Bản thân việc caller giữ `MemorySegment` sau `NativeBlock.close()` **không** ngăn block bị invalidate.

Nếu muốn hỗ trợ nhiều threads, cần `Arena.ofShared()` và hợp đồng đồng bộ access/close. Nếu muốn close idempotent, cần state riêng nhưng **không** được lờ đi concurrent users.

## 8. Chương trình độc lập: kết quả của factory sai, owner đúng và copy đúng

### 8.1. Tệp ArenaOwnershipDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaOwnershipDemo {
    private static MemorySegment unsafeEscape() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment s = arena.allocate(8, 8);
            s.set(ValueLayout.JAVA_LONG, 0, 77);
            return s;
        }
    }

    private static MemorySegment createIn(Arena owner) {
        MemorySegment s = owner.allocate(8, 8);
        s.set(ValueLayout.JAVA_BYTE, 0, (byte) 17);
        return s;
    }

    public static void main(String[] args) {
        MemorySegment stale = unsafeEscape();
        System.out.println("Escaped scope alive: "
                + stale.scope().isAlive());

        try {
            stale.get(ValueLayout.JAVA_LONG, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Escaped access: blocked");
        }

        byte[] copy;
        MemorySegment kept;

        try (Arena owner = Arena.ofConfined()) {
            kept = createIn(owner);
            copy = kept.toArray(ValueLayout.JAVA_BYTE);
            System.out.println("Inside owner: "
                    + kept.get(ValueLayout.JAVA_BYTE, 0));
        }

        System.out.println("Kept object: " + (kept != null));
        System.out.println("Kept scope alive: "
                + kept.scope().isAlive());
        System.out.println("Copied byte after close: " + copy[0]);
    }
}
```

**Biên dịch và chạy:**

```bash
javac ArenaOwnershipDemo.java
java ArenaOwnershipDemo
```

**Stdout đã kiểm tra trên JDK 24:**

```text
Escaped scope alive: false
Escaped access: blocked
Inside owner: 17
Kept object: true
Kept scope alive: false
Copied byte after close: 17
```

Giải thích:

- `unsafeEscape` tạo native memory trong một arena được đóng **trước khi caller dùng** segment, vì vậy caller nhận view expired.
- `createIn(Arena owner)` không đóng arena; caller quyết định boundary.
- Trong `try`, `kept` dùng được. Sau `try`, Java object `kept` vẫn non-null nhưng backing memory hết hạn.
- `copy` là mảng Java riêng được tạo trước close, nên đọc `copy[0]` sau khi arena đóng vẫn bình thường.

Bài học từ ví dụ: **để dữ liệu sống lâu, bạn cần một owner có lifetime đủ dài hoặc một storage copy độc lập; giữ lại Java reference đến view là không đủ**.

## 9. So sánh các Arena: khi nào Java reference thực sự ảnh hưởng GC lifetime?

Một hiểu nhầm khác là chuyển quy tắc của **automatic arena** sang **closeable arena**. Chúng có hợp đồng khác nhau.

| Loại arena | Vùng off-heap sống đến khi nào? | Có `close()` tường minh? | Nếu Java code còn giữ segment |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Khi arena được đóng thành công | Có; thread tạo arena đóng | **Vẫn có thể bị invalidate** nếu owner close |
| `Arena.ofShared()` | Khi arena được đóng thành công | Có; các thread có thể close, chịu quy tắc concurrent access | **Vẫn có thể bị invalidate** nếu owner close |
| `Arena.ofAuto()` | Khi GC quyết định thu hồi, sau khi auto arena và mọi segments liên quan không còn reachable | Không; gọi `close` không được hỗ trợ | Strong references giúp giữ auto-backed resource reachable; **không đảm bảo hạn chót release** |
| `Arena.global()` | Lifetime không giới hạn theo API; backing allocation không được deallocate trong vòng đời arena | Không | Segment còn hay mất reference **không tạo điểm giải phóng** |
| Heap segment từ `MemorySegment.ofArray(...)` | Backing Java array được GC quản lý, không phải `Arena.allocate` native allocation | Không liên quan closeable native arena | Segment references giúp array reachable qua backing; không đồng nghĩa native arena |

**Rất quan trọng:** hai phát biểu tưởng mâu thuẫn nhưng đều đúng:

- Với `Arena.ofConfined()/ofShared()`, **segment Java vẫn được giữ** không ngăn arena **đóng chủ động**.
- Với `Arena.ofAuto()`, **segment Java còn reachable** là một trong các điều kiện khiến GC **chưa** thể thu hồi backing allocation của auto arena.

Đừng áp dụng “cứ còn segment là native memory còn sống” cho closeable arena; cũng đừng nói “GC có thể thu gom backing của auto arena trong khi segment vẫn được dùng hợp lệ”, vì đó là sai về hợp đồng reachability.

### 9.1. Tại sao `Arena.ofAuto` không phù hợp cho deadline giải phóng?

`Arena.ofAuto()` hữu ích khi chấp nhận GC quản lý vòng đời một cách tự động. Nhưng số lượng native bytes có thể lớn trong khi Java wrapper nhỏ; GC không có nghĩa vụ chạy ngay sau khi bạn gán `segment = null` hoặc `System.gc()`.

Không kiểm thử kiểu:

```java
MemorySegment s = Arena.ofAuto().allocate(1024 * 1024);
s = null;
System.gc();

// SAI: assert native memory đã được giải phóng ngay tại đây.
```

Không có cam kết thời điểm GC hoặc native free xảy ra sau `System.gc()`.

### 9.2. Global arena không có điểm close

`Arena.global()` thích hợp cho vùng nhớ thực sự cần lifetime không giới hạn theo API. Nếu cấp phát quá nhiều vào global arena, ứng dụng có thể giữ native memory đến khi process kết thúc dù Java references tới các segment đã mất.

Vì vậy mặc định khi tài nguyên có điểm kết thúc nên dùng `Arena.ofConfined()` hoặc `ofShared()` với `try-with-resources`, thay vì dựa vào GC hoặc cấp phát vào global arena.

## 10. Chương trình độc lập: Auto, heap và confined arena

### 10.1. Tệp ArenaModesDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaModesDemo {
    public static void main(String[] args) throws InterruptedException {
        Arena automaticArena = Arena.ofAuto();
        MemorySegment auto = automaticArena.allocate(8);

        System.out.println("Auto alive while retained: "
                + auto.scope().isAlive());

        try {
            automaticArena.close();
        } catch (UnsupportedOperationException expected) {
            System.out.println("Auto close: unsupported");
        }

        System.out.println("Auto alive after attempted close: "
                + auto.scope().isAlive());

        MemorySegment heap = MemorySegment.ofArray(new byte[4]);
        System.out.println("Heap native: " + heap.isNative());
        System.out.println("Heap alive: " + heap.scope().isAlive());

        try (Arena confined = Arena.ofConfined()) {
            MemorySegment s = confined.allocate(4);

            Thread other = new Thread(() -> {
                try {
                    s.get(ValueLayout.JAVA_BYTE, 0);
                } catch (WrongThreadException expected) {
                    System.out.println("Other thread access: blocked");
                }
            });

            other.start();
            other.join();

            System.out.println("Owner thread access: "
                    + s.get(ValueLayout.JAVA_BYTE, 0));
        }
    }
}
```

**Biên dịch và chạy:**

```bash
javac ArenaModesDemo.java
java ArenaModesDemo
```

**Stdout đã kiểm tra trên JDK 24:**

```text
Auto alive while retained: true
Auto close: unsupported
Auto alive after attempted close: true
Heap native: false
Heap alive: true
Other thread access: blocked
Owner thread access: 0
```

Đoạn trên **không** cố bắt GC để chứng minh auto-backed memory bị free; nó chỉ kiểm tra những hợp đồng xác định được: auto arena không cho close tường minh khi còn object, heap segment không phải native, confined arena không cho thread khác access.

**Một nuance:** `scope.isAlive()` trên `Arena.ofAuto` trả true khi segment đang được giữ trong ví dụ; nó không cung cấp API “đóng bằng GC ngay bây giờ”. Khi segment và auto arena cùng không còn reachable, runtime mới có cơ hội thu hồi vào thời điểm không xác định.

## 11. Đóng arena và các cuộc đua với luồng khác

Giữ Java reference và giữ arena mở là hai điều khác; **đồng bộ truy cập** lại là khía cạnh thứ ba.

### 11.1. Confined arena

`Arena.ofConfined()` được gán cho thread tạo. Thread khác cố truy cập segment có thể gặp `WrongThreadException` ngay cả khi scope còn alive.

```text
Thread A (owner)
   Arena.ofConfined()
       |
       +-- segment native còn sống
       |
Thread B gọi segment.get(...)
       |
       +-- WrongThreadException (sai owner)
```

Nếu pass segment cho thread B, Java reference vẫn tồn tại nhưng **không được cấp phép access**. Đó không phải lifetime hết hạn, mà là **sai quyền thread**.

### 11.2. Shared arena

`Arena.ofShared()` cho phép access từ nhiều threads. Nhưng đó **không** có nghĩa các accesses hoặc đóng arena được tự động đồng bộ theo logic ứng dụng.

Giả sử thread A đang dùng segment, thread B cố close shared arena:

- FFM thực hiện temporal-safety checks; `Arena.close()` có thể ném `IllegalStateException` khi một FFM operation đang sử dụng một segment trong arena đồng thời.
- Caller cần chính sách quản lý lifecycle rõ ràng: đợi in-flight operations hoàn tất, không cho bắt đầu operation mới sau trạng thái “closing”, rồi close.
- Nếu native code bên ngoài FFM giữ một raw pointer lâu hơn lần gọi FFM, cơ chế runtime **không nhất thiết biết** việc raw pointer đó vẫn đang được dùng. Bắt buộc phối hợp với bên native trước khi giải phóng allocation.

### 11.3. Vì sao check-then-use có race?

```java
if (segment.scope().isAlive()) {
    // Thread khác có thể close shared arena sau phép kiểm tra.
    int value = segment.get(ValueLayout.JAVA_INT, 0);
}
```

Đây không phải phép “reserve” memory. `isAlive()` có thể true tại lúc check, nhưng thay đổi trước `get`. Với FFM, kết quả có thể là exception thay vì access thành công. Trong API của bạn, không nên biến một lần `isAlive()` thành lời hứa vô điều kiện về lifetime cho công việc tiếp theo.

Giải pháp ở mức kiến trúc: dùng ownership rõ ràng, state machine (OPEN → CLOSING → CLOSED), lock/lease/borrow để chặn concurrent close khi có operations đang chạy, hoặc một luồng owner tập trung điều phối close.

## 12. Vẫn giữ raw native address: vùng nguy hiểm FFM không tự bảo vệ

FFM chỉ có thể kiểm soát những access **được thực hiện qua các API có bound/lifetime checks**. Nếu bạn lấy địa chỉ và đưa ra ngoài:

```java
long rawAddress = segment.address();
```

`rawAddress` chỉ là **số nguyên**. Nó không giữ segment alive, không giữ arena mở, không mang theo `byteSize` hoặc thông tin scope. Sau `arena.close()`, số đó có thể vẫn bằng địa chỉ cũ, nhưng native memory đã được deallocate.

Truyền `rawAddress` sang C/C++ rồi dereference sau khi arena đóng có thể gây use-after-free, crash, đọc sai dữ liệu hoặc làm hỏng bộ nhớ. Java exception về closed scope **không tự xuất hiện** trong một hàm C nhận raw address.

### 12.1. Restricted reinterpret không hồi sinh memory

JDK 22+ có `MemorySegment.ofAddress(long)` tạo zero-length view gắn địa chỉ (không cấp phát memory) và những API `reinterpret(...)` để khai báo lại size/scope trong những trường hợp cần tương tác native.

**Không dùng `reinterpret` để “mở lại” một segment đã hết hạn** hoặc làm scope giả tưởng còn sống. Restricted methods có thể vi phạm memory safety khi dùng sai: ví dụ khai báo một view với scope khác sống lâu hơn backing allocation rồi dereference sau khi owner thực sự free. Javadoc cảnh báo có thể dẫn đến JVM crash hoặc memory corruption.

Thực hành an toàn:

1. Bảo toàn owner của native allocation và điểm đóng/`free` thực tế.
2. Chỉ tạo view có kích thước, scope phù hợp với backing memory thực tế.
3. Không tạo “global view” đến pointer được cấp phát trong arena sắp close.
4. Với API bên thứ ba cấp pointer, tìm hiểu hợp đồng ai sở hữu pointer và ai được free, không tự đưa vào arena sai để tự động giải phóng.
5. Sau close, không cố chữa lỗi bằng cách đọc raw address hoặc cast sang `Unsafe`/JNI.

### 12.2. Heap segment không thể hiểu như native pointer

`MemorySegment.ofArray(new byte[16])` có Java heap backing, địa chỉ được ảo hóa, không phải địa chỉ native thực tế cần truyền tới C. Với heap-backed segment, `address()` của segment gốc có thể bằng 0, nhưng điều đó **không** nghĩa mảng Java đã bị giải phóng hay pointer C là `NULL`.

Nếu native function cần truy cập các bytes ấy, hãy dùng con đường API hỗ trợ và bảo đảm backing storage được xử lý hợp lệ; không cast `heap.address()` thành pointer C. Đây là vấn đề độc lập với việc arena native đã close hay chưa.

## 13. Một số lỗi dễ mắc và cách sửa

| Mẫu lỗi | Sai ở đâu? | Cách đúng |
| --- | --- | --- |
| `segment != null` nên `get` chắc chắn hợp lệ | Java reference không bảo đảm native backing còn sống | Kiểm tra hợp đồng owner/scope; thực hiện access hợp lệ trong lifetime |
| Lưu `MemorySegment` vào field static để “không bao giờ bị free” | Không thể ngăn owner đóng `Arena.ofConfined`/`ofShared` | Lưu cả owner nếu cần, quản lý thời điểm close |
| Return segment từ `try (Arena arena = ...)` | Scope đã đóng trước khi caller dùng | Caller sở hữu arena hoặc copy dữ liệu |
| Trả `asSlice` rồi đóng parent arena | Slice dùng cùng backing/scope | Giữ parent arena mở đến khi mọi view xong |
| `asByteBuffer` sẽ tách khỏi arena | Buffer view chia sẻ native backing memory | Copy sang `byte[]` hoặc buffer lưu trữ độc lập |
| `byteSize() > 0` nghĩa memory còn | Metadata không liên quan runtime lifetime | `scope().isAlive()` và access-time checks |
| `address()` sau close vẫn khác 0 nên C pointer hợp lệ | Số địa chỉ không mang quyền sở hữu | Không dereference raw pointer sau khi free |
| `isAlive()` được kiểm tra một lần rồi dùng vô hạn | Thread khác có thể close sau check | Đồng bộ lifecycle và access; xử lý exception |
| Tưởng `Arena.ofAuto()` đóng khi method kết thúc | Do GC quản lý, không có deadline | Closeable arena + `try-with-resources` khi cần đúng hạn |
| Tưởng mọi arena chịu GC như nhau | Confined/shared đóng chủ động, auto do GC quản lý | Phân biệt ownership của arena |
| Đóng `Arena.ofConfined` từ thread khác | Vi phạm confinement | Close trên owner thread hoặc thiết kế shared arena |
| Dùng `reinterpret` để né invalidation | Scope view mới có thể dài hơn thực tế backing | Chỉ reinterpret khi biết chắc lifetime/size của memory |
| Copy sang segment khác nhưng cùng arena | Cả hai chết cùng scope | Copy sang heap hoặc sang arena đích sống đủ lâu |
| Dựa vào `System.gc()` để xác nhận free | GC không đảm bảo thời điểm thu hồi | Kiểm thử deterministic bằng close |
| Bỏ qua in-flight native uses khi close | Raw C pointer không có temporal checks FFM | Chờ callbacks/native tasks kết thúc trước close |

## 14. Kiểm thử đúng: tách reachability, lifetime và access permission

Một bộ test nên đo **những điều chắc chắn theo contract** thay vì phụ thuộc vào điều kiện GC không ổn định.

### Kiểm thử với arena đóng được

- Tạo arena confined, cấp phát, đọc/ghi khi scope alive.
- Lưu `MemorySegment` vào một biến còn sống ngoài `try`.
- Đóng arena bằng `try-with-resources`.
- Xác minh `segment != null` vẫn true.
- Xác minh `segment.scope().isAlive() == false`.
- Xác minh `get` hoặc `set` trên segment ném `IllegalStateException`.
- Tạo `asSlice` và `asByteBuffer` **trước** khi close; xác minh view không thể đọc sau close.
- Không assert một raw native address hoặc giá trị `address()` cụ thể vì phụ thuộc môi trường.

### Kiểm thử ownership/copy

- Test factory đóng arena trước khi return: caller nhận stale view, access bị chặn.
- Test factory nhận arena từ caller: access thành công **trong** scope của caller.
- Test snapshot bằng `toArray`: Java array copy vẫn còn dữ liệu sau close.
- Test không đóng arena trong một helper mà chính caller còn đang sở hữu, tránh double close.

### Kiểm thử multi-thread

- `Arena.ofConfined`: một worker thread khác thử access sẽ gặp `WrongThreadException`.
- `Arena.ofShared`: các threads có thể access, nhưng test cần phối hợp với close và dữ liệu dùng chung. Không trông chờ test race ngẫu nhiên để chứng minh không có use-after-free trong C.
- Mô phỏng close đúng khi tất cả in-flight tasks đã hoàn thành và xử lý case access từ thread đến sau close.

### Không viết test đòi GC phải giải phóng lập tức

```java
MemorySegment s = Arena.ofAuto().allocate(1024);
s = null;
System.gc();

// Không có bảo đảm phạm vi native allocation
// đã được thu hồi ngay sau lời gọi System.gc().
```

Một bài kiểm thử ép GC là thử nghiệm **không xác định** về thời gian thu hồi, không phải phép xác minh hợp đồng lifetime tuyệt đối.

## 15. Bài tập tự kiểm tra

**Câu 1.** Biến `final MemorySegment s` vẫn reachable. Nếu `Arena.ofConfined()` chứa nó đã đóng, `s.get(ValueLayout.JAVA_BYTE, 0)` hợp lệ không?

**Đáp án:** Không. `final` chỉ giới hạn việc gán lại biến Java, không thay đổi scope hoặc quyền đóng arena. Sau close, access không hợp lệ và bị từ chối.

**Câu 2.** Một segment có `byteSize() = 1024` và `address() = A`. Hai giá trị ấy có thể còn quan sát sau close không? Có nghĩa 1024 bytes tại A còn thuộc bạn không?

**Đáp án:** Metadata vẫn có thể quan sát, nhưng backing memory đã bị deallocate khi close thành công. Địa chỉ cũ không phải quyền sở hữu; không truy cập bytes bằng raw pointer.

**Câu 3.** `slice = root.asSlice(8, 8)` được giữ trong `List`. Đóng arena của `root` làm `slice` mất hiệu lực không?

**Đáp án:** Có. Slice chia sẻ backing memory và scope với root. Collection chỉ giữ Java view object, không làm scope còn alive.

**Câu 4.** Gọi `toArray(ValueLayout.JAVA_BYTE)` trước close thì sao?

**Đáp án:** Trả một mảng Java sao chép bytes; dữ liệu trong mảng đó còn dùng được sau khi arena native đóng, vì backing storage độc lập.

**Câu 5.** Hai lời gọi `segment.scope().isAlive()` và `segment.get(...)` có thành một thao tác “giữ sống” atomic không?

**Đáp án:** Không. `isAlive()` là snapshot; một thread khác có thể đóng shared arena giữa hai calls. Access FFM kiểm tra hợp lệ, nhưng API caller cần đồng bộ lifetime nếu cần guarantee cho cả workflow.

**Câu 6.** Khi nào strong reference đến một segment có vai trò bảo vệ vòng đời backing native memory khỏi GC?

**Đáp án:** Với auto arena, GC chỉ thu hồi backing sau khi auto arena và tất cả segments liên quan không còn reachable; giữ segment giúp không đáp ứng điều kiện thu hồi. Điều này **khác** closeable arenas, vốn có thể được đóng tường minh khi segment vẫn còn reachable.

**Câu 7.** Một `MemorySegment.ofArray(new byte[8])` có `address() == 0`. Có phải backing memory đã hết hạn?

**Đáp án:** Không. Đây là heap segment với địa chỉ ảo hóa, không phải raw native pointer; không suy luận lifetime từ giá trị địa chỉ.

**Câu 8.** Java caller nhận `MemorySegment` từ helper, nhưng helper đã `close()` arena trong `finally`. Hướng sửa hợp lý nhất?

**Đáp án:** Để caller quản lý arena cho tới khi sử dụng xong hoặc trả bản copy dữ liệu độc lập. Không trả borrowed view ra ngoài một owner đã bị đóng.

**Câu 9.** Nếu FFM chặn `get` sau close, có an toàn dùng `long oldAddress = segment.address()` với JNI/C?

**Đáp án:** Không. Raw pointer không mang scope/bounds và có thể trỏ tới memory đã free; FFM không tự kiểm tra dereference trong C.

**Câu 10.** Một `Arena.ofShared` vẫn alive tại thời điểm bạn kiểm tra. Có thể close nó ngay khi một native worker đang dùng raw pointer không?

**Đáp án:** Không. Cần phối hợp để native worker kết thúc và trả quyền sở hữu trước khi close; kiểm tra `isAlive()` riêng lẻ không ngăn race hoặc use-after-free bên ngoài FFM.

## 16. Tóm tắt áp dụng

- **Java object còn reachable** ≠ **native backing memory còn sống**.
- `Arena.close()` thành công làm scope không alive và invalidate các segment có scope đó, kể cả Java vẫn giữ mọi view.
- `segment != null`, `byteSize()` và `address()` chỉ là những dấu hiệu **về view**, không thay thế kiểm soát lifetime.
- Slice, read-only view, `ByteBuffer` view **chia sẻ backing/scope**, không kéo dài vòng đời do arena đóng chủ động.
- `toArray` hoặc copy sang storage có lifetime độc lập giúp giữ **dữ liệu**, không phải giữ nguyên native allocation.
- `Arena.ofConfined/ofShared` có **explicit close**; `Arena.ofAuto` do GC quản lý, và `Arena.global` không có deadline giải phóng.
- `scope().isAlive()` là trạng thái tức thời; muốn một workflow dùng memory an toàn qua nhiều bước phải có **owner/borrow/lifecycle synchronization**, đặc biệt khi nhiều threads hoặc native code có thể giữ pointer.
- Khi cần chia sẻ segment giữa các lớp hoặc trả từ helper, hãy truyền arena từ caller hoặc trả wrapper giữ arena, không đóng owner trước khi consumer dùng xong.

## Tài liệu tham khảo chính thức

- [JDK 24 API — MemorySegment: access, scope, lifetime, views](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [JDK 24 API — Arena: thời gian sống, close, automatic và confined/shared](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 24 API — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [JDK 24 API — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Dev.java — Access On/Off-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)

**Kết luận:** giữ một tham chiếu Java đến `MemorySegment` **không thể hồi sinh vùng nhớ native đã được arena đóng**. Đừng hỏi chỉ “còn object không?” mà phải hỏi “**arena/scope còn hợp lệ, đúng thread, đúng kích thước và backing memory còn thuộc owner không?**”. Đó là ranh giới giữa một Java view tồn tại và vùng nhớ thực sự còn sử dụng được.
