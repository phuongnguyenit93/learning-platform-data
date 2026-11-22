# Chuyển giữa ByteBuffer và MemorySegment mà không giả định có bản sao

> **Ngữ cảnh:** Java Advance → Native Interoperability → Bộ đệm và tệp. Bài này giải thích hai chiều chuyển đổi `ByteBuffer ↔ MemorySegment` trong Foreign Function & Memory API (FFM) bằng `MemorySegment.ofBuffer(...)` và `segment.asByteBuffer()`. Trọng tâm: **đó là các *view* cùng sử dụng backing memory, không phải thao tác copy dữ liệu**; phải quản lý phạm vi byte, byte order, quyền ghi, backing heap/direct, vòng đời và thread. Ví dụ dùng **JDK 22+**, phiên bản FFM chính thức theo JEP 454.

## 1. Một vùng nhớ, nhiều cách nhìn: conversion không đồng nghĩa copy

`ByteBuffer` của Java NIO cung cấp thao tác đọc/ghi bytes với các thuộc tính `position`, `limit`, `capacity` và `ByteOrder`. `MemorySegment` của FFM cung cấp view với `long byteSize()`, các truy cập dựa trên `ValueLayout`, scope/lifetime và ràng buộc thread.

Có thể có **hai object Java khác nhau** cùng nhìn **một vùng bytes**:

```text
                     backing memory
             byte 0   byte 1   byte 2   byte 3 ...
                |        |        |        |
                +--------+--------+--------+-----
                      ^         ^
                      |         |
   ByteBuffer ------------------------> put/get(relative/absolute)
                      |
   MemorySegment ---------------------> get/set(ValueLayout,byteOffset)

   Cả hai view cùng tham chiếu dữ liệu, KHÔNG tự sinh bản sao.
```

Nếu ghi thông qua view A rồi đọc thông qua view B **trên cùng bytes, trong lifetime hợp lệ và với đồng bộ đúng**, B sẽ thấy nội dung vừa ghi. Không phải đợi một thao tác `flush` hay `sync` mới “đẩy dữ liệu từ buffer sang segment” trong trường hợp heap/direct bình thường.

Nhưng có ba loại hành động **khác nhau** cần tách bạch:

1. **Tạo view:** `MemorySegment.ofBuffer(buffer)`, `segment.asByteBuffer()`, `buffer.duplicate()`, `buffer.slice()` và `segment.asSlice(...)` nhìn chung **không copy payload bytes**; chúng tạo metadata/view mới trên backing storage.
2. **Tạo allocation mới:** `ByteBuffer.allocate(1024)`, `ByteBuffer.allocateDirect(1024)`, `arena.allocate(1024)` tạo vùng lưu trữ. Tạo memory mới **không đồng nghĩa** đã copy dữ liệu từ vùng cũ.
3. **Copy tường minh:** `destinationSegment.copyFrom(sourceSegment)`, `MemorySegment.copy(...)`, `ByteBuffer.put(otherBuffer)` hoặc `System.arraycopy(...)` chuyển **nội dung bytes** sang destination khác. Đó mới là snapshot độc lập nếu destination không alias với nguồn.

**Đừng đoán bằng tên lớp** rằng `ByteBuffer` luôn dùng heap hoặc `MemorySegment` luôn dùng native memory. Cả hai có thể là heap-backed hoặc native/direct-backed tùy cách tạo.

## 2. Hai API chuyển đổi chính và hợp đồng của chúng

| Chiều | API | Có copy dữ liệu? | Vùng nhìn thấy | Ai quản lý backing memory? |
|---|---|---|---|---|
| `ByteBuffer/Buffer → MemorySegment` | `MemorySegment.ofBuffer(buffer)` | **Không** | Từ `buffer.position()` (bao gồm) tới `buffer.limit()` (không bao gồm) tại thời điểm gọi | Owner gốc của buffer; scope phù hợp theo nguồn |
| `MemorySegment → ByteBuffer` | `segment.asByteBuffer()` | **Không** | Đúng `segment.byteSize()`, nếu biểu diễn được bằng ByteBuffer | Owner gốc của segment/Arena |
| `MemorySegment → MemorySegment` | `segment.asSlice(offset,size)` | **Không** | Một cửa sổ byte con | Cùng scope/owner của segment |
| `ByteBuffer → ByteBuffer` | `buffer.slice()` / `duplicate()` | **Không** | Slice: remaining; duplicate: toàn view với state độc lập | Cùng backing storage |
| `MemorySegment → buffer độc lập` | Allocation mới + `copyFrom` | **Có, khi gọi copy** | Theo size bạn chọn | Owner của allocation mới |

Không phải mọi kết hợp đều chuyển được theo cả hai hướng. Đặc biệt, `asByteBuffer()` không thể trả về ByteBuffer nếu segment lớn hơn `Integer.MAX_VALUE` byte hoặc nếu heap segment không có kiểu backing thích hợp (ví dụ một `int[]`). Đó là giới hạn biểu diễn/loại backing, không phải bằng chứng rằng runtime sẽ tự copy để “cố chuyển”.

### Tên hàm quan trọng

```java
import java.lang.foreign.MemorySegment;
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(16);

MemorySegment segment = MemorySegment.ofBuffer(buffer);
ByteBuffer view = segment.asByteBuffer();
```

Đây là đoạn code có thể dùng bên trong `main`, không tự có `main`. Hai chuyển đổi không tạo bản sao 16 bytes; `buffer`, `segment` và `view` cùng chạm vùng lưu trữ gốc.

## 3. `MemorySegment.ofBuffer` lấy đúng vùng `[position, limit)`

`ByteBuffer` có ba chỉ số (tính bằng bytes):

- `capacity`: tổng dung lượng backing region mà buffer mô tả.
- `limit`: vị trí cuối **không bao gồm** của vùng hợp lệ hiện tại.
- `position`: vị trí tương đối dùng cho các `get/put` **không truyền index**.

Khi gọi `MemorySegment.ofBuffer(buffer)`, segment mới:

- Bắt đầu tại **byte tương ứng `position`** của buffer lúc chuyển đổi.
- Kết thúc ở **byte ngay trước `limit`**; `segment.byteSize() == buffer.remaining()` tại thời điểm tạo.
- Coi **offset 0 của segment** là byte ở **index `position` cũ** của buffer.
- Không tự tăng/giảm `buffer.position()`, `buffer.limit()` hoặc copy nội dung.
- Giữ cửa sổ byte đã chọn; việc chỉnh `position/limit` của buffer **sau đó** không dịch chuyển segment đã được tạo.

Minh họa:

```text
ByteBuffer capacity=8, position=2, limit=6
index:         0     1  |  2     3     4     5  |  6     7
bytes:       [  ]  [  ] | [A]   [B]   [C]   [D] | [  ]   [  ]
                         ^                    ^
                  segment offset 0      segment offset 3

MemorySegment.ofBuffer(buffer) --> byteSize()=6-2=4

segment.get(JAVA_BYTE, 0) <=> buffer.get(2)
segment.get(JAVA_BYTE, 1) <=> buffer.get(3)
segment.get(JAVA_BYTE, 3) <=> buffer.get(5)
segment.get(JAVA_BYTE, 4) --> ngoài segment
```

**Đơn vị byte offset chỉ đúng trực tiếp cho ByteBuffer.** `MemorySegment.ofBuffer(Buffer)` còn có thể nhận `IntBuffer`/`ShortBuffer` v.v.; khi đó `position/limit` của buffer có đơn vị **phần tử typed buffer**, còn `segment.byteSize()` vẫn tính **byte**. Chi tiết ở mục 11.

### `Buffer.clear()` không xóa bytes và không đổi view cũ

`buffer.clear()` đặt lại position/limit/mark của buffer, **không zero hóa nội dung**. Segment đã được tạo từ `[2,6)` vẫn nhìn vùng tương ứng với byte 2–5; nó **không** mở rộng theo limit mới. Muốn một cửa sổ khác, gọi lại `ofBuffer` sau khi đã cấu hình buffer, hoặc tạo `asSlice` thích hợp.

## 4. Chương trình đầy đủ 1 — heap ByteBuffer và aliasing hai chiều

**File `SharedHeapViewsDemo.java`, JDK 22+:**

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

public final class SharedHeapViewsDemo {
    public static void main(String[] args) {
        ByteBuffer source = ByteBuffer.allocate(8);
        source.position(2);
        source.limit(6);

        MemorySegment segment = MemorySegment.ofBuffer(source);
        // Segment dài 4 byte, segment[0] trùng source[2].

        segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 77);
        source.put(3, (byte) 41); // Absolute put, không đổi position.

        ByteBuffer newView = segment.asByteBuffer();
        newView.put(2, (byte) 9); // source[4] cũng thay đổi.

        System.out.println("segmentBytes=" + segment.byteSize());
        System.out.println("segmentNative=" + segment.isNative());
        System.out.println("source[2]=" + source.get(2));
        System.out.println("segment[1]=" +
                segment.get(ValueLayout.JAVA_BYTE, 1));
        System.out.println("source[4]=" + source.get(4));
        System.out.println("sourcePosition=" + source.position()
                + " limit=" + source.limit());
        System.out.println("viewPosition=" + newView.position()
                + " limit=" + newView.limit()
                + " capacity=" + newView.capacity()
                + " direct=" + newView.isDirect());

        source.clear();
        System.out.println("afterClearBytes=" + segment.byteSize());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SharedHeapViewsDemo.java
java SharedHeapViewsDemo
```

**Kết quả mong đợi (các thao tác chính đã được kiểm tra trên JDK 24):**

```text
segmentBytes=4
segmentNative=false
source[2]=77
segment[1]=41
source[4]=9
sourcePosition=2 limit=6
viewPosition=0 limit=4 capacity=4 direct=false
afterClearBytes=4
```

Giải thích:

- `source` được tạo bằng `ByteBuffer.allocate` nên backing là Java heap `byte[]`.
- `MemorySegment.ofBuffer(source)` tạo heap segment `isNative()==false`, chứa **bốn byte** từ `source[2]` tới `source[5]`.
- `segment.set(JAVA_BYTE,0,77)` lập tức được nhìn thấy qua `source.get(2)`.
- `source.put(3,41)` lập tức được nhìn thấy qua `segment.get(JAVA_BYTE,1)`.
- `newView.put(2,9)` ghi vào byte offset2 của cửa sổ, tương đương source index4.
- Position/limit của `source` vẫn là 2/6, còn `newView` có position0, limit/capacity4.
- `source.clear()` thay đổi **metadata buffer**, không khiến `segment.byteSize()` đổi từ4 thành8.

Ví dụ này chứng minh hai điều đồng thời: **không copy payload** và **trạng thái position/limit không phải trạng thái chung**. Hai view cùng backing memory vẫn có các vị trí con trỏ đọc/ghi riêng.

## 5. `asByteBuffer()`: view mới, position 0, order mặc định BIG_ENDIAN

Theo `MemorySegment.asByteBuffer()`, nếu chuyển đổi được thì ByteBuffer kết quả:

- `position() == 0`.
- `limit() == capacity() == (int)segment.byteSize()`.
- `isReadOnly()` bằng trạng thái read-only của segment.
- `isDirect() == true` nếu segment là native segment; heap segment thích hợp cho view heap.
- **`order() == ByteOrder.BIG_ENDIAN`** ban đầu, dù layout hay ByteBuffer gốc đã dùng order khác.
- Vòng đời và quyền truy cập thread của ByteBuffer view bị ràng buộc bởi **scope của segment gốc**.

`asByteBuffer` không làm segment tự “chuyển thành heap” hay tự “tạo direct copy”. Khi parent là native memory, view ByteBuffer là direct; khi parent heap byte array, view là heap. Không có ngầm định dữ liệu được sao chép giữa chúng.

**Quan trọng về byte order:** `MemorySegment` không chứa một trường “default order” được chuyển sang ByteBuffer. Khi truy cập nhiều byte bằng `ValueLayout.JAVA_INT`, layout sẽ quyết định byte order. `ByteBuffer.getInt/putInt` phụ thuộc `buffer.order()`. Phải đặt hai bên theo cùng wire format:

```java
// Snippet minh họa, giả định segment chứa ít nhất 4 byte.
ByteBuffer view = segment.asByteBuffer();
view.order(java.nio.ByteOrder.LITTLE_ENDIAN);

var intLE = java.lang.foreign.ValueLayout.JAVA_INT
        .withOrder(java.nio.ByteOrder.LITTLE_ENDIAN);

// Dùng thêm withByteAlignment(1) khi backing heap byte[]
// và data layout cho phép unaligned access.
```

Không gọi `view.getInt(0)` với mặc định BIG_ENDIAN rồi so sánh với `segment.get(JAVA_INT.withOrder(LITTLE_ENDIAN),0)` và kết luận “copy sai”. Họ có thể diễn giải **cùng bốn byte theo hai thứ tự khác nhau**.

## 6. Chương trình đầy đủ 2 — native Arena → ByteBuffer → MemorySegment

Ở chiều ngược, Arena cấp phát off-heap memory, `asByteBuffer()` cho Java NIO view và `ofBuffer(...)` tạo lại một segment trên **cùng allocation**.

**File `NativeRoundTripDemo.java`, JDK 22+:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class NativeRoundTripDemo {
    public static void main(String[] args) {
        ByteBuffer escapedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeMemory = arena.allocate(8, 8);
            ByteBuffer view = nativeMemory.asByteBuffer();
            escapedView = view;

            // ByteBuffer view ban đầu dùng BIG_ENDIAN.
            view.putInt(0, 0x01020304);

            // ofBuffer(view) không allocate/copy dữ liệu mới.
            MemorySegment roundTrip = MemorySegment.ofBuffer(view);

            System.out.println("direct=" + view.isDirect());
            System.out.println("native=" + roundTrip.isNative());
            System.out.println("sameScope=" +
                    (roundTrip.scope() == nativeMemory.scope()));

            System.out.printf("intBE=0x%08X%n",
                    nativeMemory.get(
                            ValueLayout.JAVA_INT.withOrder(
                                    ByteOrder.BIG_ENDIAN), 0));

            roundTrip.set(ValueLayout.JAVA_BYTE, 4, (byte) 88);
            System.out.println("view[4]=" + view.get(4));
        }

        // Không được dùng ByteBuffer trỏ đến Arena đã đóng.
        try {
            escapedView.get(0);
        } catch (IllegalStateException expected) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NativeRoundTripDemo.java
java NativeRoundTripDemo
```

**stdout:**

```text
direct=true
native=true
sameScope=true
intBE=0x01020304
view[4]=88
afterClose=IllegalStateException
```

Điểm cần chú ý:

1. `Arena.ofConfined()` tạo memory ngoài heap; `nativeMemory.asByteBuffer()` trả **direct ByteBuffer**, không copy lên Java heap.
2. `MemorySegment.ofBuffer(view)` trên ByteBuffer đã được tạo từ một segment có scope `S` **kế thừa cùng scope `S`**, thay vì tự tạo lifetime mới độc lập.
3. `roundTrip.set(JAVA_BYTE,4,88)` hiện ra ngay ở `view.get(4)`. Đây là bằng chứng shared backing.
4. Khi `arena.close()` chạy, allocation không còn hợp lệ; ByteBuffer có thể còn Java reference nhưng Java byte-access qua nó ném `IllegalStateException`. **Giữ object ByteBuffer không giữ allocation Arena được quyền sống sau khi close**.
5. Nếu truy cập từ thread khác khi Arena confined, view ByteBuffer cũng chịu thread confinement (thường `WrongThreadException`); `isDirect()==true` không có nghĩa “ai cũng truy cập được”.

**Không được gọi cleaner/direct-buffer free thủ công** lên `view`. Arena là owner của allocation; free ngoài Arena rồi để Arena close có thể gây double-free/use-after-free. Nếu cần native memory sống qua nhiều thread, hãy thiết kế `Arena.ofShared()` cùng shutdown barrier thích hợp.

## 7. ByteOrder và alignment: cùng bytes vẫn có thể đọc thành số khác

Một lỗi ít hiển nhiên: hai view có thể trỏ cùng bytes nhưng **khác cách diễn giải** giá trị `int`/`short`. Ngoài endianness còn có alignment: heap buffer backed by `byte[]` không đảm bảo alignment tự nhiên4 của `ValueLayout.JAVA_INT`.

### 7.1. Mặc định order của ByteBuffer mới

Giả sử bốn bytes là:

```text
byte[0..3] = 44 33 22 11

LITTLE_ENDIAN  int = 0x11223344
BIG_ENDIAN     int = 0x44332211
```

`ByteBuffer.allocate(8).order(LITTLE_ENDIAN)` có thể ghi `0x11223344` thành `44 33 22 11`. Nhưng `MemorySegment.ofBuffer(...).asByteBuffer()` cho một ByteBuffer mới mặc định **BIG_ENDIAN**. `newView.getInt(0)` sẽ đọc `0x44332211` cho đến khi gọi `newView.order(LITTLE_ENDIAN)`.

### 7.2. Vấn đề maxByteAlignment của heap `byte[]`

`MemorySegment.ofBuffer(ByteBuffer.allocate(...))` trả một **heap segment** backed by `byte[]`. Do độ căn chỉnh được bảo đảm cho phần tử `byte` chỉ 1 byte, `segment.maxByteAlignment()` có thể là **1**. Trên JDK24 đã kiểm tra, gọi:

```java
// Snippet minh họa từ một heap ByteBuffer.
segment.get(ValueLayout.JAVA_INT, 0);
```

có thể ném `IllegalArgumentException` **ngay tại offset 0**, dù còn ≥4 bytes. Đây là vấn đề alignment của **backing heap type**, không phải bounds và không liên quan đến copy.

Nếu format thực sự lưu các int không đòi native alignment, dùng layout **unaligned**:

```java
var intLE = ValueLayout.JAVA_INT
        .withOrder(ByteOrder.LITTLE_ENDIAN)
        .withByteAlignment(1);
int value = segment.get(intLE, 0);
```

Trích đoạn giả định có imports và biến `segment`. `withByteAlignment(1)` biểu diễn access unaligned theo contract, **không thay đổi bytes**, không copy và không làm vùng nhớ lớn hơn. Với native struct thực sự yêu cầu alignment4, phải cấp phát/bố trí đúng ABI; **không** hạ alignment chỉ để né exception.

## 8. Chương trình đầy đủ 3 — phân biệt shared view và snapshot copy

Chương trình này minh họa cả **copy tường minh** (`copyFrom`) lẫn **byte order tường minh**, cùng cảnh báo heap-byte alignment.

**File `CopyAndOrderDemo.java`, JDK 22+:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class CopyAndOrderDemo {
    public static void main(String[] args) {
        ByteBuffer source =
                ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
        source.position(1);
        source.limit(4);

        // View 3 byte: 20,30,40. Không copy.
        MemorySegment live = MemorySegment.ofBuffer(source);

        try (Arena arena = Arena.ofConfined()) {
            // MỚI cấp vùng lưu trữ và copy bytes rõ ràng.
            MemorySegment snapshot = arena.allocate(live.byteSize());
            snapshot.copyFrom(live);

            live.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
            System.out.println("source=" + source.get(1)
                    + " copied=" +
                    snapshot.get(ValueLayout.JAVA_BYTE, 0)
                    + " length=" + snapshot.byteSize());
        }

        ByteBuffer little = ByteBuffer.allocate(8)
                .order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(0, 0x11223344);
        little.position(0);
        little.limit(4);

        MemorySegment asSegment = MemorySegment.ofBuffer(little);

        var intLE = ValueLayout.JAVA_INT
                .withOrder(ByteOrder.LITTLE_ENDIAN)
                .withByteAlignment(1);

        System.out.println("heapMaxAlignment=" +
                asSegment.maxByteAlignment());
        System.out.printf("segmentLE=0x%08X%n",
                asSegment.get(intLE, 0));

        ByteBuffer anotherView = asSegment.asByteBuffer();
        System.out.printf("viewDefault=0x%08X%n",
                anotherView.getInt(0));

        anotherView.order(ByteOrder.LITTLE_ENDIAN);
        System.out.printf("viewLE=0x%08X%n",
                anotherView.getInt(0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CopyAndOrderDemo.java
java CopyAndOrderDemo
```

**stdout (đã kiểm tra hành vi tương đương trên JDK 24):**

```text
source=99 copied=20 length=3
heapMaxAlignment=1
segmentLE=0x11223344
viewDefault=0x44332211
viewLE=0x11223344
```

Vì sao `snapshot` giữ giá trị20 trong khi `source` thành99? `copyFrom` đã **chép nội dung** vào một native allocation mới. `source` và `live` chia sẻ byte từ heap array; `snapshot` là bản sao độc lập. Đó là điểm khác nhau giữa `copyFrom` và các API view-conversion.

Vì sao `segmentLE` và `viewDefault` khác nhau? Chúng đọc **cùng 4 bytes** nhưng layout `intLE` yêu cầu LITTLE_ENDIAN, còn ByteBuffer mới mặc định BIG_ENDIAN. Sau `anotherView.order(LITTLE_ENDIAN)`, chúng khớp.

**Bảo đảm và giới hạn:** `heapMaxAlignment=1` là kết quả phù hợp heap `byte[]` theo alignment guarantee, không được suy rộng thành “mọi MemorySegment đều alignment1”. Với native allocation `arena.allocate(8,8)`, layout `JAVA_INT` alignment4 thường hợp lệ ở offset0. Đọc/ghi đa byte cần xét **cả type và alignment của backing region**.

## 9. Heap, direct, mapped và typed buffers không giống nhau

| Nguồn tạo | Backing storage | `MemorySegment.ofBuffer` | `segment.asByteBuffer` |
|---|---|---|---|
| `ByteBuffer.allocate(n)` | Heap `byte[]` | Heap segment, **không copy** | ByteBuffer view heap nếu size hợp lệ |
| `ByteBuffer.wrap(byte[])` | Heap `byte[]` được cung cấp | Heap segment, **không copy** | ByteBuffer view heap nếu size hợp lệ |
| `ByteBuffer.allocateDirect(n)` | Native/direct memory | Native segment, **không copy** | Direct ByteBuffer view |
| `arena.allocate(n)` | Native memory thuộc Arena | Có thể gọi `segment.asByteBuffer()` trước | Direct ByteBuffer share scope Arena |
| `MappedByteBuffer` từ `FileChannel.map` | File-mapped native memory | Native segment với shared backing | Có thể tạo ByteBuffer view nếu size phù hợp; không copy mapping |
| `MemorySegment.ofArray(byte[])` | Heap `byte[]` | Không cần `ofBuffer` để có segment | ByteBuffer view có thể được tạo |
| `MemorySegment.ofArray(int[])` | Heap `int[]` | Segment tồn tại | **`asByteBuffer` không được hỗ trợ** cho heap backing không phải `byte[]` |
| `IntBuffer.wrap(int[])` | Heap `int[]` | `ofBuffer` có thể tạo segment tính size theo byte | Không được mặc định cho rằng có thể `asByteBuffer` |
| `CharBuffer.wrap(CharSequence)` không backed by array | Một dạng CharSequence view | `ofBuffer` có thể ném `IllegalArgumentException` | Không có bảo đảm chuyển được |

**Quan trọng:** `Buffer.hasArray()==false` không chứng minh “không chia sẻ memory”. Direct ByteBuffer thường không lộ Java array nhưng vẫn chia sẻ native backing với MemorySegment. Read-only heap buffer cũng có thể không cho truy cập array công khai, nhưng vẫn có backing bytes.

Đừng tự suy ra native pointer từ heap segment. `segment.isNative()==false` nghĩa là backing ở Java heap; Java GC có thể di chuyển nó và không được xử lý như một `void*` ổn định tùy ý. Trong native interoperability, hãy dùng API yêu cầu đúng kind/pointer contract; khi cần native memory thực, tạo direct buffer hoặc Arena segment, và **copy dữ liệu có chủ đích** nếu nguồn ban đầu ở heap.

## 10. Typed Buffer và giới hạn `asByteBuffer`: phản ví dụ đáng nhớ

`MemorySegment.ofBuffer` chấp nhận một `java.nio.Buffer`, không chỉ `ByteBuffer`. Ví dụ `IntBuffer` có `position`/`limit` **tính theo số int**, không phải byte.

**File `TypedBufferEdgeDemo.java`, JDK 22+:**

```java
import java.lang.foreign.MemorySegment;
import java.nio.IntBuffer;

public final class TypedBufferEdgeDemo {
    public static void main(String[] args) {
        IntBuffer ints = IntBuffer.wrap(new int[]{10, 20, 30});
        ints.position(1);
        ints.limit(3);

        MemorySegment segment = MemorySegment.ofBuffer(ints);
        System.out.println("segmentBytes=" + segment.byteSize());
        System.out.println("native=" + segment.isNative());

        try {
            segment.asByteBuffer();
        } catch (UnsupportedOperationException expected) {
            System.out.println(
                    "asByteBuffer=UnsupportedOperationException");
        }
    }
}
```

Chạy:

```bash
javac TypedBufferEdgeDemo.java
java TypedBufferEdgeDemo
```

**stdout:**

```text
segmentBytes=8
native=false
asByteBuffer=UnsupportedOperationException
```

Hai `int` còn lại (`20,30`) chiếm `2 × 4 = 8` byte. FFM có thể tạo heap segment trên vùng lưu trữ của `int[]`, nhưng `asByteBuffer` không hỗ trợ chuyển heap segment backed by non-byte array thành `ByteBuffer`. Nó **không tự copy hoặc reinterpret theo cách khác** để né giới hạn đó.

Nếu thật sự cần bytes độc lập, hãy **chọn encoding/endianness**, cấp `byte[]` hoặc Arena segment rồi ghi từng `int`/copy dữ liệu theo contract. Không ép `int[]` thành `byte[]` bằng cast hoặc giả định endianness/representation.

### Typed buffer từ direct memory

Một `IntBuffer` có thể là **view của direct ByteBuffer**, không nhất thiết backed by `int[]`. Khi `ofBuffer` trả native segment, `asByteBuffer` có thể biểu diễn nó trong giới hạn size. Hãy kiểm tra `segment.isNative()` và hợp đồng API thay vì đưa ra quy tắc tuyệt đối rằng “IntBuffer nào cũng thất bại”.

## 11. Vị trí và offset: hai hệ tọa độ dễ nhầm

`ByteBuffer` có **relative operations** và **absolute operations**:

```java
// Snippet minh họa: buffer dài đủ byte.
byte a = buffer.get();      // Đọc tại position rồi tăng position.
byte b = buffer.get(3);     // Đọc tại absolute index3; position giữ nguyên.
buffer.put((byte) 7);       // Ghi tại position rồi tăng position.
buffer.put(3, (byte) 7);    // Ghi absolute index3; position giữ nguyên.
```

`MemorySegment` truy cập bằng **byte offset** tính từ đầu view:

```java
// Snippet minh họa: segment >= 4 byte.
byte x = segment.get(ValueLayout.JAVA_BYTE, 0);
segment.set(ValueLayout.JAVA_BYTE, 3, (byte) 7);
```

Không có `position` mutable trong MemorySegment. Nếu cần “cursor”, caller tự giữ một biến offset hoặc dùng ByteBuffer view với relative `get/put`. Khi tạo segment từ ByteBuffer, byte offset0 của segment là **position của buffer tại thời điểm chuyển đổi**; khi tạo ByteBuffer từ segment, position của ByteBuffer mới luôn0.

**Sơ đồ ví dụ theo index:**

```text
ByteBuffer       capacity=10, position=4, limit=9
index buffer     0 1 2 3 | 4 5 6 7 8 | 9
segment offset           | 0 1 2 3 4 |
segment.byteSize=5

ByteBuffer original.get(4)  = segment.get(JAVA_BYTE,0)
ByteBuffer original.get(8)  = segment.get(JAVA_BYTE,4)
ByteBuffer original.get(9)  không nằm trong segment.
```

Nếu buffer gốc là một `slice` hoặc một `duplicate` có `arrayOffset` riêng, không tự lấy index từ array gốc mà bỏ qua slice offset. Dùng view APIs vì chúng đã lưu mapping đúng sang backing region.

### Slice của buffer khác slice của segment nhưng đều không copy

`ByteBuffer.slice()` trả buffer mới có position0, limit/capacity bằng remaining của buffer gốc và cùng backing storage. `MemorySegment.asSlice(start,length)` trả segment mới có byteSize=length, scope của parent và cùng backing storage. Cả hai là view, không phải snapshot.

Cẩn thận với `ByteBuffer.duplicate()`: nó giữ cùng content backing nhưng position/limit/mark **độc lập**; việc thay đổi byte sẽ hiện qua cả hai, việc di chuyển position của một buffer thì không tự di chuyển buffer còn lại.

## 12. Read-only: giới hạn ghi trên view, không phải snapshot bất biến

Đọc cùng backing memory nhưng có quyền ghi khác nhau là chuyện bình thường:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnlyBuffer = writable.asReadOnlyBuffer();

MemorySegment readOnlySegment =
        MemorySegment.ofBuffer(readOnlyBuffer);

System.out.println(readOnlySegment.isReadOnly()); // true

ByteBuffer anotherView = readOnlySegment.asByteBuffer();
System.out.println(anotherView.isReadOnly());      // true

// readOnlySegment.set(JAVA_BYTE, 0, (byte)9):
// IllegalArgumentException do segment là read-only.
// anotherView.put(0, (byte)9):
// java.nio.ReadOnlyBufferException.
```

Đoạn này là snippet học tập; thêm `main` nếu muốn chạy. Có hai điểm thường bị bỏ qua:

- `ofBuffer` giữ thuộc tính **read-only** từ buffer gốc. `asByteBuffer` giữ thuộc tính read-only của segment.
- **Read-only view không phải immutable snapshot.** Nếu còn một writable alias khác tới cùng backing memory (như `writable` trong snippet), alias đó vẫn có thể thay đổi bytes và read-only view sẽ quan sát sự thay đổi.

Nếu cần một bản ghi cố định cho cache, ký số, hoặc kiểm tra CRC giữa nhiều luồng không đồng bộ, một read-only view đơn thuần **không đủ**: phải copy sang vùng lưu trữ riêng và ngăn các owner khác sửa nó, hoặc áp dụng synchronization phù hợp.

## 13. Scope và ownership: vòng đời đi theo nguồn gốc memory

Có hai đường phổ biến cần phân biệt.

### 13.1. `ByteBuffer` gốc không xuất phát từ `MemorySegment.asByteBuffer()`

Ví dụ:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
MemorySegment segment = MemorySegment.ofBuffer(direct);
```

`ofBuffer` tạo **native segment view** với một **automatic scope** giữ `direct` reachable. Điều này giúp backing memory của ByteBuffer gốc không bị reclaim bởi GC **chừng nào segment hoặc các slices còn reachable**. Nhưng điều đó **không** trao quyền manual `arena.close()`, bởi đây không phải allocation do Arena của bạn tạo.

Không gọi `free`, `Unsafe.invokeCleaner` hoặc một deallocator SDK tùy ý lên địa chỉ của direct buffer. Vùng nhớ vẫn thuộc owner gốc (thường JVM/direct-buffer mechanism); tự giải phóng rồi tiếp tục dùng segment hoặc buffer có thể tạo dangling view.

### 13.2. `ByteBuffer` được tạo từ Arena segment

`arena.allocate(...).asByteBuffer()` tạo view trong scope của Arena; gọi `MemorySegment.ofBuffer(view)` lại **kế thừa cùng scope**, không tạo một owner độc lập để “kéo dài” lifetime.

```text
Arena.ofConfined() -> allocate() -> MemorySegment M
                       |
                       +-- M.asByteBuffer() -> ByteBuffer B
                                                |
                                                +-- ofBuffer(B) -> MemorySegment N
Arena.close() -> M, B và N đều không thể truy cập allocation nữa.
```

Giữ reference B/N **không ngăn owner gọi `arena.close()`**. Đây là lý do test trong `NativeRoundTripDemo` ném `IllegalStateException` sau khi Arena đóng.

### 13.3. Thread confinement cũng lan tới buffer view

`Arena.ofConfined()` chỉ cho owner thread truy cập vùng nhớ. Nếu tạo `ByteBuffer view = segment.asByteBuffer()` rồi gửi view tới thread khác, Java NIO access cũng chịu ràng buộc tương ứng và có thể ném `WrongThreadException`. Với shared arena, nhiều thread có thể truy cập nhưng **data race vẫn do ứng dụng chịu trách nhiệm**.

Một số asynchronous I/O APIs có thể chạy read/write trên thread không phù hợp với confined scope. Theo JDK docs, với ByteBuffer được tạo từ **thread-confined segment**, hành vi exception của một số kênh I/O bất đồng bộ có thể không cố định. Khi truyền view sang executor/I/O subsystem, cân nhắc `Arena.ofShared()` với owner lifecycle rõ ràng.

## 14. File mapping: chuyển view không đồng nghĩa copy toàn bộ tệp

Đối với file lớn, Java NIO hỗ trợ `MappedByteBuffer` và FFM hỗ trợ `MemorySegment` trực tiếp trên mapped file. Mapping cho phép truy cập dữ liệu file qua virtual memory; hệ điều hành vẫn có page faults/caching và quản lý dirty pages, nên từ “zero-copy view” **không** có nghĩa “mọi I/O đều không có copy/kernel work/page faults”.

Hai cách:

### 14.1. NIO map trước rồi tạo MemorySegment view

```java
// Snippet minh họa, channel đã mở READ/WRITE; size > 0
// và <= Integer.MAX_VALUE cho MappedByteBuffer.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, size);

MemorySegment mappedView = MemorySegment.ofBuffer(mapped);
mappedView.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

// mapped và mappedView chia sẻ cùng mapped region.
// Gọi mapped.force() khi cần yêu cầu ghi dữ liệu về storage.
mapped.force();
```

Đây là trích đoạn; cần imports `java.nio.MappedByteBuffer`, `java.nio.channels.FileChannel`, `java.lang.foreign.*`. **Không có copy toàn bộ file** ở `ofBuffer`. Vòng đời mapping ở nhánh NIO gắn với nguồn `MappedByteBuffer`/GC, không được hiểu như có thể đóng mapping bằng một Arena tự tạo sau đó.

### 14.2. FFM map trước rồi tạo ByteBuffer view

Từ JDK22, `FileChannel.map(mode, offset, size, arena)` có thể trả `MemorySegment` của vùng file-mapped:

```java
// Snippet minh họa trong một hàm throws IOException;
// file tồn tại, opened READ/WRITE và size phù hợp.
try (FileChannel channel = FileChannel.open(
            path, StandardOpenOption.READ,
            StandardOpenOption.WRITE);
     Arena arena = Arena.ofConfined()) {

    MemorySegment mapped = channel.map(
            FileChannel.MapMode.READ_WRITE,
            0L, channel.size(), arena);

    // Chỉ dùng asByteBuffer nếu mapped.byteSize() <= Integer.MAX_VALUE.
    ByteBuffer view = mapped.asByteBuffer();
    view.put(0, (byte) 42);

    // Chủ động yêu cầu persist dirty mapped bytes khi thích hợp.
    mapped.force();
} // Đóng arena -> unmap vùng mapped theo contract FFM.
```

Đây là snippet, giả định đã import `FileChannel`, `Path`/`StandardOpenOption`, `Arena`, `MemorySegment`, `ByteBuffer`. `MappedSegment.force()` không phải bước bắt buộc để Java nhìn thấy thay đổi thông qua hai views trên cùng map; nó phục vụ **persistence** của mapped file theo contract OS/file system.

**Thận trọng:** file có thể bị truncate từ process khác, hoặc map mode/permissions không phù hợp; một mapped region có thể mất tính truy cập. Mapping không tự tạo snapshot nhất quán của file. Khi nội dung có thể thay đổi đồng thời, cần file locks/protocol/checksum tùy thiết kế.

### 14.3. Vùng file lớn hơn 2 GiB

`FileChannel.map(MapMode,long,long,Arena)` có thể trả segment kích thước biểu diễn bằng `long`, hỗ trợ mục tiêu lớn hơn giới hạn ByteBuffer trong môi trường cho phép. Nhưng `mapped.asByteBuffer()` **không** biểu diễn được > `Integer.MAX_VALUE` bytes. Hãy làm việc với `mapped.asSlice(offset, length)` cho từng cửa sổ nhỏ, hoặc dùng FFM access trực tiếp. Cần bảo đảm mọi cửa sổ không vượt bounds và còn trong lifetime Arena.

## 15. Giới hạn 2 GiB và những lỗi chuyển đổi cụ thể

`ByteBuffer` dùng `int` cho `capacity()`, `limit()` và `position()`; `MemorySegment` dùng `long` cho `byteSize()`. Vì vậy:

```java
// Không chạy với segment khổng lồ chỉ để thử.
// Một segment giả định có byteSize() > Integer.MAX_VALUE:
segment.asByteBuffer(); // UnsupportedOperationException
```

Không phải runtime sẽ ngầm copy 2+ GiB thành nhiều buffers hay “truncate còn 2 GiB” giúp bạn. Muốn dùng NIO, chia ra các slice có size nằm trong giới hạn, rồi xử lý từng window với offset tính bằng `long`.

Bảng lỗi/điều kiện thường gặp:

| Tình huống | Kết quả/rủi ro | Cách xử lý |
|---|---|---|
| `segment.byteSize() > Integer.MAX_VALUE` | `asByteBuffer` ném `UnsupportedOperationException` | Dùng FFM trực tiếp hoặc slice thành từng window hợp lệ |
| Heap segment backed by `int[]` | `asByteBuffer` không được hỗ trợ | Chuyển đổi dữ liệu tường minh sang `byte[]`/native allocation |
| `CharBuffer.wrap(CharSequence)` không backed by array | `ofBuffer` có thể ném `IllegalArgumentException` | Materialize sang array/ByteBuffer một cách tường minh |
| Confined segment được dùng từ thread khác | `WrongThreadException` | Cùng thread hoặc dùng shared arena đúng lifetime |
| Arena đã đóng | `IllegalStateException` khi truy cập view | Không để view thoát owner lifetime |
| `segment.asReadOnly()` rồi gọi `set` | `IllegalArgumentException` | Cần writable view/owner theo contract |
| Read-only ByteBuffer rồi gọi `put` | `ReadOnlyBufferException` | Không tự gỡ read-only; tạo owned mutable copy nếu cần |
| Buffer view đọc `int` khác Segment view | Khác byte order/alignment | Chọn `order` và `ValueLayout` đúng schema |
| Buffer được `clear/flip` sau `ofBuffer` | Segment cũ vẫn nhìn cửa sổ byte cũ | Tạo segment view mới nếu muốn vùng mới |
| Dùng `ByteBuffer.get()` tương đương `segment.get(JAVA_BYTE,0)` | Relative get đổi position, còn segment offset0 cố định | Dùng absolute index hoặc quản lý cursor tường minh |
| Tạo snapshot bằng `duplicate()/slice()/asByteBuffer` | Vẫn alias backing, không có bản sao | Cấp destination mới và `copyFrom` |
| Đưa heap view trực tiếp làm native pointer | Không có stable address như native memory | Theo Linker contract; dùng direct/Arena và copy khi cần |
| Java GC quản lý direct buffer nhưng app gọi manual free | Có thể dangling view/double-free | Để đúng owner quản lý; không clean/free chéo |

## 16. Đồng thời và memory visibility: zero-copy không tự làm thread-safe

Hai views trên cùng backing memory tạo ra **aliasing**. Với một thread, write rồi read qua view khác sẽ thấy bytes mới. Nhưng nếu thread A và B truy cập cùng bytes đồng thời mà **không có synchronization**, chương trình có thể có data race hoặc không có visibility guarantees như người viết mong muốn.

Ví dụ sai về giả định:

```java
// PSEUDOCODE: Không phải chương trình chạy độc lập.
// producer:
while (...) {
    segment.set(ValueLayout.JAVA_INT_UNALIGNED, 0, nextValue++);
}

// consumer trên thread khác:
while (...) {
    int n = buffer.getInt(0); // Không có happens-before.
}
```

Không thể dựa vào `segment` và `buffer` là cùng backing rồi coi thao tác read/write là atomic, ordered hoặc visible đúng thứ tự. Ngoài ra ví dụ có thể cần byte-order phù hợp, alignment, và scope có thể được truy cập từ cả hai threads.

Giải pháp tùy bài toán:

- Dùng **lock** chung và lifecycle owner cho cả các đường ByteBuffer/MemorySegment.
- Sử dụng `VarHandle` cho field với access modes/ordering rõ ràng, đồng thời thỏa alignment cần thiết.
- Dùng producer-consumer queue, `CompletableFuture` hoặc đồng bộ trước/sau buffer handoff.
- Với native code hoặc memory mapped file chia sẻ giữa processes, phải hiểu memory ordering và protocol ở cả native/OS boundary; Java monitor chỉ đồng bộ hóa các Java threads theo contract tương ứng, không tự áp dụng cho thiết bị ngoài.
- Với `Arena.ofShared()`, các thread được phép truy cập cùng region nhưng close phải diễn ra sau khi worker/callback đã dừng; shared arena **không** là locks hoặc atomic memory model.

**Một biến position không nên được dùng làm bộ đồng bộ.** ByteBuffer position/limit là state mutable thuộc mỗi buffer và không tự bảo vệ đồng thời. Hai ByteBuffer views có thể có position khác nhau nhưng cùng dữ liệu; vấn đề ownership/lifetime và visibility vẫn tồn tại.

## 17. Kết nối với JNI/FFM native interoperability

Chuyển được ByteBuffer ↔ MemorySegment **không** có nghĩa đã có một native allocation an toàn để C giữ pointer. Phân biệt nguồn:

### Heap buffer

`ByteBuffer.allocate(n)` thường backed by Java `byte[]`. `MemorySegment.ofBuffer(buffer)` trả heap segment, `isNative()==false`. Garbage collector có thể di chuyển underlying heap storage. Không lấy `segment.address()` rồi đưa vào native C như một pointer địa chỉ vật lý ổn định; trong heap segment, address mang ý nghĩa offset/trừu tượng, không phải pointer raw C có thể dereference tùy ý.

Nếu native API cần pointer tới một buffer theo contract, cân nhắc:

- `ByteBuffer.allocateDirect(n)` để tạo direct/native backing mà JNI `GetDirectBufferAddress` có thể truy cập khi buffer thích hợp.
- `Arena.allocate(n)` để cấp memory có lifetime explicit; truyền `MemorySegment` theo FFM downcall descriptor `ADDRESS` và chỉ khi API/Linker cho phép, còn sống và đúng bounds.
- Copy tường minh từ heap sang native allocation, và từ native sang heap khi cần. Đây là **đường có copy theo chủ đích**, có thể đúng và an toàn hơn zero-copy khi native giữ buffer lâu hoặc xử lý bất đồng bộ.

### Direct buffer hoặc Arena-owned native segment

Khi `MemorySegment.ofBuffer(ByteBuffer.allocateDirect(n))` trả native segment, conversion không tạo mới vùng dữ liệu; nhưng **JVM/direct buffer** vẫn là owner backing memory. Không gọi C `free` vào địa chỉ đó, cũng không tự gán arena owner mới để giải phóng.

Khi `Arena.allocate(n).asByteBuffer()` tạo direct view, **Arena** sở hữu backing. Không dùng view sau `arena.close()`; nếu native callback/worker giữ địa chỉ, phải stop/drain/join trước khi close Arena.

### JNI `NewDirectByteBuffer`

JNI có thể tạo ByteBuffer view trên một vùng memory `void*` do SDK cấp (`NewDirectByteBuffer`). `MemorySegment.ofBuffer(...)` tiếp tục tạo view, **không chuyển quyền sở hữu**. SDK vẫn phải giải phóng đúng deallocator của mình **sau khi** mọi Java view và native consumer ngừng dùng vùng đó. Chỉ giữ Java ByteBuffer object không tự gia hạn lifetime của SDK allocation nếu SDK đã free pointer ở ngoài.

**Quy tắc nhận diện:** conversion giữ **same backing bytes**, nhưng không tự hứa thêm ownership, copying, pinning, retaining, native-pointer validity hoặc thread safety. Mọi thứ này đến từ **API tạo backing memory ban đầu**.

## 18. Kiểm thử để chứng minh có/không có copy

Thay vì đoán qua `==`/`equals`, có thể kiểm tra aliasing có kiểm soát:

1. Tạo buffer với dữ liệu dễ quan sát, đặt position/limit tạo một cửa sổ không bắt đầu ở 0.
2. Chuyển thành segment bằng `ofBuffer`; kiểm tra `byteSize==remaining` tại thời điểm tạo.
3. Ghi qua segment offset0, đọc qua original buffer index position cũ. Giá trị đổi chứng minh shared backing.
4. Ghi qua original buffer absolute index, đọc qua segment offset tương ứng.
5. Tạo `segment.asByteBuffer`, xác nhận view position0, limit/capacity bằng segment size.
6. Thay source `position/limit/clear`; xác nhận segment window không tự thay kích thước.
7. Cấp một destination memory khác, gọi `copyFrom`, sau đó mutate source; xác nhận destination không đổi.
8. Kiểm tra native vs heap qua `segment.isNative()` và `buffer.isDirect()`.
9. Kiểm tra byte order ở hai bên với một số hex không đối xứng (`0x11223344`).
10. Kiểm tra bounds, read-only và lifetime sau arena close.
11. Với typed buffer, xác nhận `IntBuffer.wrap(int[])` cho segment tính byte size đúng nhưng `asByteBuffer` có thể không hỗ trợ.
12. Với mapping file, kiểm tra flush/persistence bằng API mapping chính thức, không đánh đồng file persistence với shared in-memory view.

**Không nên dùng địa chỉ native in ra logs làm bằng chứng duy nhất.** Cùng địa chỉ có thể là vùng đã free và được cấp lại, hoặc heap address mang ý nghĩa khác. Mutate/read đối xứng trong một scope an toàn là test trực tiếp nhất cho shared backing, nhưng không phải phép chứng minh hệ thống không có data race hoặc lifetime bug.

### Đo hiệu năng có trách nhiệm

View conversion thường tránh copy payload lớn, nhưng không vì thế mà **luôn nhanh hơn** trong mọi workload. Access patterns, endian transforms, heap/direct cost, page faults, alignment, bounds checks, CPU cache, GC pressure và việc native I/O cần copy riêng đều ảnh hưởng hiệu năng. Nếu chọn zero-copy cho performance, dùng JMH/microbenchmarks có warmup và kiểm tra end-to-end throughput; không dùng `System.nanoTime` một lần cho kết luận chung.

## 19. Bài tập kèm đáp án

**Bài 1 — remaining.** Một ByteBuffer có capacity12, position3, limit9. `MemorySegment.ofBuffer(buffer).byteSize()` bằng bao nhiêu và segment offset0 trùng buffer index nào?

**Đáp án:** `9 - 3 = 6` byte; segment offset0 trùng buffer **index3**. Các index9–11 không nằm trong segment view dù thuộc capacity của buffer.

**Bài 2 — independent cursor.** Tạo `MemorySegment segment = ofBuffer(buffer)`; sau đó gọi `buffer.clear()`. Segment có tự mở rộng sang toàn capacity không?

**Đáp án:** Không. `clear()` chỉ đổi position/limit/mark của buffer; region segment được xác định ở thời điểm `ofBuffer`, backing bytes vẫn shared.

**Bài 3 — alias vs copy.** `MemorySegment s = ofBuffer(b); ByteBuffer c = s.asByteBuffer();`. Ghi `c.put(0,(byte)9)` có tạo một phiên bản độc lập của dữ liệu không?

**Đáp án:** Không. `s` và `c` đều là view, cùng backing. Nếu writable và đang sống, byte tương ứng trong `b` đổi. Muốn snapshot cần allocation riêng và `copyFrom`/put.

**Bài 4 — byte order.** ByteBuffer gốc order LITTLE_ENDIAN, chứa bytes `44 33 22 11`. Gọi `ofBuffer` rồi `asByteBuffer` và `getInt(0)` ngay. Giá trị nào?

**Đáp án:** View mới có order **BIG_ENDIAN** mặc định nên trả `0x44332211`. Sau `order(LITTLE_ENDIAN)` thì trả `0x11223344`. Không có copy dữ liệu; chỉ cách diễn giải thay đổi.

**Bài 5 — alignment.** Heap ByteBuffer backed by byte[] chứa 4 bytes của int. `segment.get(ValueLayout.JAVA_INT,0)` ném `IllegalArgumentException` dù byteSize≥4. Tại sao và sửa thế nào?

**Đáp án:** Heap segment từ byte[] có guaranteed alignment tối đa1; layout int tự nhiên thường yêu cầu4. Dùng `JAVA_INT.withByteAlignment(1)` với byte order thích hợp **nếu schema cho phép unaligned int**, hoặc dùng một native allocation phù hợp alignment.

**Bài 6 — Arena lifetime.** Tạo `ByteBuffer view = arena.allocate(16).asByteBuffer()`, trả view khỏi method rồi close Arena. Caller vẫn giữ view, có tiếp tục đọc được không?

**Đáp án:** Không. ByteBuffer kế thừa scope Arena; truy cập sau close ném `IllegalStateException`. Giữ ByteBuffer reference không kéo dài một scoped allocation đã đóng.

**Bài 7 — direct buffer.** `ByteBuffer b = ByteBuffer.allocateDirect(100)`; `MemorySegment s = ofBuffer(b)`. Có cần `arena.allocate(100)` và `copyFrom` chỉ để có native segment không?

**Đáp án:** Không, conversion từ direct buffer đã tạo native segment view trên cùng backing memory. **Nhưng** muốn ownership/lifetime khác thì phải thiết kế và cấp phát/copy một cách tường minh; đừng gọi `free` trên direct buffer.

**Bài 8 — typed buffer.** `IntBuffer.wrap(new int[]{10,20,30})` có position1/limit3. `MemorySegment.ofBuffer(ints)` có bao nhiêu byte và `asByteBuffer()` có chắc thành công không?

**Đáp án:** 2 int ×4 = **8 byte**; không chắc. Nếu heap backed by `int[]`, `asByteBuffer()` ném `UnsupportedOperationException`. Nó không tự chuyển mảng int thành mảng byte.

**Bài 9 — file 3 GiB.** Một FFM mapped segment có byteSize > Integer.MAX_VALUE. Có thể gọi `asByteBuffer()` để lấy một ByteBuffer bao trùm toàn file không?

**Đáp án:** Không. `ByteBuffer` có giới hạn size từ `int`. Dùng FFM direct access hoặc các `asSlice` nhỏ vừa giới hạn ByteBuffer, với bounds và scope đúng.

**Bài 10 — hai threads.** Producer ghi vào MemorySegment, consumer đọc qua ByteBuffer cùng backing trong shared arena. Có thể bỏ mọi đồng bộ vì không copy không?

**Đáp án:** Không. Hai view alias dữ liệu nhưng không tự thiết lập happens-before, atomicity hoặc bảo vệ race. Phải có synchronization/VarHandle/queue phù hợp và bảo đảm Arena còn sống.

**Bài 11 — read-only.** `MemorySegment.ofBuffer(readOnlyByteBuffer)` rồi `asByteBuffer()`. View sau có writable không? Dữ liệu có bất biến vĩnh viễn không?

**Đáp án:** View sau cũng **read-only**, nhưng backing memory có thể thay đổi nếu tồn tại writable alias hợp lệ. Read-only view không tương đương snapshot immutable.

**Bài 12 — ownership.** SDK native tạo `void*` rồi JNI tạo DirectByteBuffer view; Java chuyển tiếp sang MemorySegment. Ai gọi free?

**Đáp án:** Theo **hợp đồng allocator của SDK**. JNI/NewDirectByteBuffer và `ofBuffer` chỉ tạo views, không tự chuyển quyền free. Cần đợi tất cả Java/native users kết thúc trước khi SDK owner release.

## 20. Checklist và tài liệu chính thức

Trước khi dùng `ByteBuffer ↔ MemorySegment` trong một hệ thống native/file I/O:

- [ ] Đã xác định **nguồn backing memory**: Java heap byte[], direct/native, Arena, SDK hay file mapping.
- [ ] Đã hiểu `ofBuffer` lấy **position/limit lúc chuyển đổi**, không phải capacity toàn bộ.
- [ ] Đã hiểu `asByteBuffer` trả position0, limit/capacity bằng segment size.
- [ ] Đã ghi rõ **không có payload copy** ở conversion; nếu cần snapshot thì cấp vùng mới và `copyFrom`.
- [ ] Đã đối chiếu **byte order** của ByteBuffer mới (BIG_ENDIAN) với ValueLayout/format.
- [ ] Đã kiểm tra **byte alignment**; với byte[] heap phải cân nhắc layout unaligned khi hợp đồng cho phép.
- [ ] Đã xác minh segment size **≤ Integer.MAX_VALUE** và backing phù hợp trước `asByteBuffer`.
- [ ] Đã kiểm tra read-only/write-permissions và tình trạng có writable alias.
- [ ] Đã kiểm tra **scope/lifetime**: direct buffer automatic scope hay Arena closeable?
- [ ] Nếu từ Arena, Java ByteBuffer view không được sống sau `arena.close()`.
- [ ] Nếu xử lý nhiều threads, đã chọn scope phù hợp và có synchronization.
- [ ] Nếu native C giữ pointer, đã xác định **owner, release API, stop/join barrier**.
- [ ] Nếu file mapping, đã phân biệt **shared memory visibility** với **persistence/force**.
- [ ] Các tests chứng minh aliasing, independent snapshot, bounds, endian và lifetime đều chạy.

**Kết luận:** `MemorySegment.ofBuffer` và `MemorySegment.asByteBuffer` là **chuyển đổi view**. Chúng cho phép cùng truy cập một vùng bytes, không tạo bản sao ẩn. Chính vì vậy, code phải quản lý **offset, endianness, alignment, quyền ghi, scope và ownership** một cách tường minh. **Zero-copy view là cơ chế chia sẻ dữ liệu, không phải sự bảo đảm an toàn hay một chiến lược sao chép.**

### Tài liệu chính thức

- [JEP 454 — Foreign Function & Memory API chính thức từ Java 22](https://openjdk.org/jeps/454)
- [Java SE 25 — MemorySegment: `ofBuffer`, `asByteBuffer`, scope, alignment, slices, copy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 25 — ByteBuffer: position/limit, direct, slice/duplicate, byte order](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 25 — Buffer: position, limit, capacity](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/Buffer.html)
- [Java SE 25 — Arena: confined/shared/auto và close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 25 — ValueLayout và alignment](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 25 — FileChannel.map: MappedByteBuffer và MemorySegment với Arena](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java SE 25 — MappedByteBuffer.force](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html)
