# Tạo MemorySegment từ mảng hoặc ByteBuffer và hiểu thời gian sống của vùng nền

Trong Foreign Function & Memory API (FFM), `MemorySegment` mô tả một **vùng nhớ liên tục có kích thước, quyền truy cập và thời gian sống xác định**. Nhiều ví dụ FFM sử dụng `Arena.allocate(...)` để cấp phát bộ nhớ native, nhưng không phải segment nào cũng cần tự cấp phát. Java cho phép tạo **view không sao chép dữ liệu** từ một mảng nguyên thủy bằng `MemorySegment.ofArray(...)` hoặc từ một `java.nio.Buffer` bằng `MemorySegment.ofBuffer(...)`.

Điểm khó không phải chỉ là cú pháp: segment được tạo ra **không tự nhiên sở hữu một bản sao dữ liệu**. Nó tham chiếu đến vùng nhớ nền đã tồn tại. Vùng nền đó có thể ở **Java heap**, trong **direct ByteBuffer** do JVM/cleaner quản lý, hoặc ở **native allocation có scope của Arena**. Mỗi trường hợp có lifecycle riêng; việc biến một đối tượng thành `MemorySegment` **không chuyển quyền sở hữu một cách tùy ý**.

Bài này dùng API ổn định từ **JDK 22 trở lên** (FFM hoàn thiện trong JEP 454), làm rõ ánh xạ byte, aliasing, position/limit, read-only, GC reachability, `Arena`, thread confinement, sai lầm thường gặp và ví dụ Java chạy được.

## 1. Mental model: segment là view, vùng nền mới giữ bytes

Hãy tưởng tượng một đoạn nhớ gồm bốn byte:

```text
Vùng nhớ nền (backing storage)
index:      0       1       2       3
bytes:     [10]    [20]    [30]    [40]
              \       |       /
               \      |      /
              MemorySegment view
              address + bounds + scope
```

Một `MemorySegment` lưu/mô hình hóa:

- **Vùng byte có thể truy cập:** `byteSize()` và offset, có kiểm tra giới hạn (spatial bounds).
- **Nguồn bộ nhớ:** `isNative()` phân biệt segment native/off-heap với heap segment.
- **Khả năng ghi:** `isReadOnly()` và phương thức tạo view read-only.
- **Thời gian sống:** `scope()` mô tả khi nào quyền truy cập còn hiệu lực (temporal bounds).
- **Điều kiện thread:** segment có thể chỉ được truy cập bởi owner thread của `Arena.ofConfined()`.
- **Phép đọc/ghi có kiểu:** `get(ValueLayout.JAVA_BYTE, offset)`, `set(...)`, `getAtIndex(...)`, v.v.

Hai segment có thể khác nhau về **khoảng nhìn thấy** nhưng cùng trỏ tới bytes nền; ghi qua một view sẽ hiện ra ở view kia. Đó là **aliasing**. Mặt khác, một lời gọi `toArray(...)` hoặc `MemorySegment.copy(...)` thực sự **sao chép dữ liệu**, tạo quan hệ ownership khác.

Không nhầm segment với raw C pointer: `address()` của heap segment **không** phải địa chỉ native có thể tự ý đưa sang C. Java GC có thể di chuyển array; FFM che giấu chi tiết này bằng biểu diễn heap segment và cơ chế kiểm soát truy cập. Với native segment, địa chỉ là địa chỉ native nhưng vẫn phải tuân thủ lifetime và bounds.

## 2. `MemorySegment.ofArray(...)`: view trên mảng Java

API hỗ trợ các mảng primitive sau:

```java
MemorySegment.ofArray(byte[]);
MemorySegment.ofArray(char[]);
MemorySegment.ofArray(short[]);
MemorySegment.ofArray(int[]);
MemorySegment.ofArray(long[]);
MemorySegment.ofArray(float[]);
MemorySegment.ofArray(double[]);
```

Đây là **danh sách chữ ký minh họa các overload**, không phải code Java có thể chạy độc lập. Không có overload trực tiếp cho `boolean[]`, `Object[]` hoặc `String[]`; không thể giả định mọi mảng Java có thể dùng làm một khối byte theo FFM.

Một ví dụ nhỏ:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

byte[] bytes = {10, 20, 30, 40};
MemorySegment segment = MemorySegment.ofArray(bytes);

System.out.println(segment.byteSize());                 // 4
System.out.println(segment.isNative());                 // false
System.out.println(segment.get(ValueLayout.JAVA_BYTE, 1)); // 20

segment.set(ValueLayout.JAVA_BYTE, 1, (byte) 21);
System.out.println(bytes[1]);                           // 21
```

Đây là **đoạn trong một Java method**, chưa phải file hoàn chỉnh. Nó chứng minh `ofArray` **không copy**: thay đổi qua segment cập nhật trực tiếp array ban đầu, và thay đổi `bytes[i]` sau đó sẽ đọc thấy qua segment.

Với `int[]`, mỗi phần tử có bốn byte:

```java
int[] numbers = {100, 200};
MemorySegment ints = MemorySegment.ofArray(numbers);

System.out.println(ints.byteSize()); // 8
ints.setAtIndex(ValueLayout.JAVA_INT, 1, 250);
System.out.println(numbers[1]);     // 250
```

Ở đây `getAtIndex/setAtIndex` nhận **chỉ số phần tử theo ValueLayout** (chẳng hạn `JAVA_INT` có bề rộng 4 byte), còn `get/set` nhận **byte offset**. Không dùng `segment.get(JAVA_INT, 1)` để đọc phần tử `numbers[1]`: offset 1 byte là sai chỗ và có thể vi phạm alignment.

### 2.1. Scope của mảng Java

`MemorySegment.ofArray(array)` trả **heap segment** với một **automatic scope** giữ array nền reachable. Khi segment hoặc các view liên quan còn reachable, JVM không được thu gom array nền vì nó vẫn cần thiết cho các phép truy cập đã được phép. Segment có thể được truy cập từ nhiều thread theo scope, nhưng **không tự bảo đảm thread-safety của dữ liệu**: nếu hai thread ghi cùng phần tử không đồng bộ, vẫn có data race.

Không tồn tại thao tác `arena.close()` để giải phóng bytes của một array do `ofArray` bọc: array thuộc Java heap và do garbage collector quản lý. Gọi `DeleteLocalRef` trong JNI, `free` trong C hoặc cố thao tác cleaner thủ công không phải cách quản lý heap segment ở đây.

### 2.2. `heapBase()` và `address()`

`heapBase()` cho biết Java object là nền heap khi API cho phép; với writable segment từ `byte[]`, có thể nhận lại đúng mảng gốc. Khi segment read-only, `heapBase()` có thể trả `Optional.empty()` dù segment vẫn là heap. Do đó **không dùng `heapBase().isPresent()` như cách phân biệt heap/native phổ quát**; dùng `isNative()`.

Một heap segment tạo trực tiếp bằng `ofArray` thường có `address() == 0`, nhưng đó **không phải NULL native pointer** và không phải địa chỉ vật lý ổn định. Với slice của heap segment, địa chỉ mang ý nghĩa offset tương đối tới heap base. Không lưu `address()` của heap segment làm C pointer hoặc handle có lifetime độc lập.

## 3. `MemorySegment.ofBuffer(...)`: view trên phần còn lại của Buffer

Chữ ký API:

```java
static MemorySegment ofBuffer(java.nio.Buffer buffer)
```

`Buffer` bao gồm `ByteBuffer` và các typed buffers như `IntBuffer`, `CharBuffer`. `ofBuffer` không chỉ nhận dung lượng toàn bộ buffer. Theo API, segment biểu diễn **khoảng từ `position()` (bao gồm) đến `limit()` (không bao gồm)** tại lúc tạo view.

Đối với `ByteBuffer`, position/limit đếm byte. Với `IntBuffer`, chúng đếm phần tử int và segment có byte length tương ứng số phần tử nhân kích thước mỗi phần tử. Cần luôn biết đang làm việc với kiểu buffer nào.

### 3.1. Ví dụ ByteBuffer heap: không copy, tôn trọng position/limit

```java
byte[] bytes = {10, 20, 30, 40};
ByteBuffer buffer = ByteBuffer.wrap(bytes);
buffer.position(1);
buffer.limit(3);

MemorySegment window = MemorySegment.ofBuffer(buffer);

System.out.println(window.byteSize());                    // 2
System.out.println(window.get(ValueLayout.JAVA_BYTE, 0)); // 20

window.set(ValueLayout.JAVA_BYTE, 1, (byte) 31);
System.out.println(bytes[2]);                             // 31
```

Đoạn nằm trong Java method đã có import `java.nio.ByteBuffer` và FFM imports.

Ánh xạ byte chính xác:

```text
Array gốc:   [10] [20] [30] [40]
Index:        0    1    2    3
ByteBuffer: position=1, limit=3
View segment:      [20] [30]
View offset:         0    1
                       |
segment.set(offset=1, 31) -> array[2] = 31
```

`window.byteSize() == buffer.remaining() == 2` trong trường hợp `ByteBuffer` này. Offset 0 của segment ứng với **vị trí 1 của buffer**, không nhất thiết là index 0 trong array.

Tạo segment không làm buffer tự `flip()`, `clear()` hay tự thay đổi cursor. Thay đổi `buffer.position(...)` **sau khi tạo** cũng không thay đổi khoảng view vốn đã được segment ghi nhận; nếu muốn khoảng khác thì tạo một segment mới từ trạng thái buffer mới.

### 3.2. `ByteBuffer.allocate(...)` và `ByteBuffer.wrap(...)`

Hai phương thức này tạo/wrap **heap buffer**. Khi vùng nền thật sự được hỗ trợ bởi primitive array, `MemorySegment.ofBuffer(buffer)` tạo **heap segment** với cùng backing storage; không chuyển bộ nhớ sang native.

`ByteBuffer.wrap(bytes, start, length)` có position và limit được thiết lập theo yêu cầu; đừng lẫn tham số `start` với offset trực tiếp trong segment. Cách ít nhầm là tạo buffer, kiểm tra `position/limit/remaining`, rồi tạo segment và truy cập offset từ **0**.

Một heap buffer có thể là read-only view; `hasArray()` không phải lúc nào cũng trả true dù nội bộ nó vẫn có backing array. Trái lại, một số heap `Buffer` thực sự **không được backing bởi array** (chẳng hạn `CharBuffer.wrap(CharSequence)`), và `MemorySegment.ofBuffer` có thể ném `IllegalArgumentException` theo Javadoc. Không xem mọi đối tượng `Buffer` là luôn chuyển được sang segment.

### 3.3. Read-only phải được giữ nguyên

```java
ByteBuffer readOnly = ByteBuffer.wrap(new byte[] {1, 2})
                                .asReadOnlyBuffer();
MemorySegment segment = MemorySegment.ofBuffer(readOnly);

System.out.println(segment.isReadOnly()); // true
```

Chuyển qua `ofBuffer` **không bỏ quyền read-only**. Cố `segment.set(...)` vào một read-only segment sẽ lỗi (API FFM dùng `IllegalArgumentException` trong trường hợp ghi vào read-only segment); còn `ByteBuffer.put(...)` của read-only buffer dùng exception riêng của NIO. Không dùng một view để tìm cách vượt quyền truy cập của view khác.

## 4. Direct ByteBuffer: vẫn alias nhưng bộ nhớ nằm ngoài Java heap

`ByteBuffer.allocateDirect(n)` cấp phát một **direct buffer**, thường chứa bytes ở native/off-heap memory. `MemorySegment.ofBuffer(direct)` trả **native segment**:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(4);
direct.put(1, (byte) 7);
direct.position(1);
direct.limit(3);

MemorySegment segment = MemorySegment.ofBuffer(direct);
System.out.println(segment.isNative());                 // true
System.out.println(segment.byteSize());                 // 2
System.out.println(segment.get(ValueLayout.JAVA_BYTE, 0)); // 7

segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
System.out.println(direct.get(1));                      // 9
```

Mã là đoạn nằm trong method. Native segment ở đây vẫn chỉ là **view của backing memory thuộc direct buffer**. Không có allocation native thứ hai của FFM và không có lời gọi `free()` cần thực hiện cho `segment`.

### 4.1. Ai sở hữu lifetime của direct buffer?

Nếu direct buffer được tạo theo cách thông thường như `allocateDirect`, native backing memory của nó được quản lý theo vòng đời do JVM/implementation xác định, thường thông qua reachability/cleaner và không có thời điểm thu hồi deterministic do caller chọn.

**Đặc tả `ofBuffer` nói rõ:** khi buffer không được sinh trực tiếp từ `MemorySegment.asByteBuffer()` của một scope có sẵn, segment nhận một **automatic scope giữ buffer reachable**. Như vậy một segment hoặc slice của nó còn reachable sẽ giữ direct buffer nền reachable và không cho bộ nhớ do buffer quản lý bị deallocate quá sớm chỉ vì biến `ByteBuffer` ban đầu rời scope Java.

Điều đó **không** cho phép tự gọi native `free(address)`, `Unsafe.freeMemory` hoặc tự kích hoạt cleaner trên direct buffer. Những thao tác giải phóng ngoài contract có thể làm pointer bị treo trong khi `MemorySegment` vẫn còn sống. Automatic scope không thể bảo vệ trước thư viện native khác **chủ động** free vùng nhớ từ bên ngoài JVM.

Đừng cố `System.gc()` để “chứng minh” segment giữ memory: GC không có nghĩa vụ thu gom tại thời điểm bạn yêu cầu. Test hành vi bằng cách truy cập hợp lệ khi object còn reachable và bằng các hợp đồng scope rõ ràng, không bằng kỳ vọng về lịch thu hồi bộ nhớ.

### 4.2. Mapped ByteBuffer và tài nguyên ngoài JVM

Nếu `Buffer` là một mapped buffer, `MemorySegment.ofBuffer` có thể cho ra mapped native segment theo thuộc tính vùng nhớ nền. Đừng coi mọi direct buffer là file mapping, và đừng đóng file/mapping hoặc thực hiện unmap thủ công khi code vẫn dùng view.

Với memory-mapped file do `FileChannel.map(..., Arena)` của FFM tạo, arena có thể sở hữu lifetime mapping; với NIO `MappedByteBuffer`, vòng đời thường phụ thuộc reference cleanup/implementation. Phân biệt **ai cấp phát/mapping** và **ai có quyền đóng** là yêu cầu bắt buộc trong contract.

## 5. Trường hợp tinh tế: buffer xuất phát từ `MemorySegment.asByteBuffer()`

Đây là khác biệt quyết định trong bài về lifetime.

Giả sử dùng arena cấp phát native memory rồi chuyển sang NIO buffer:

```java
MemorySegment viewOutside;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment owner = arena.allocate(8);
    owner.set(ValueLayout.JAVA_BYTE, 0, (byte) 55);

    ByteBuffer nioView = owner.asByteBuffer();
    viewOutside = MemorySegment.ofBuffer(nioView);

    System.out.println(
        viewOutside.get(ValueLayout.JAVA_BYTE, 0)); // 55
}

// Arena đã close. Cả owner và viewOutside
// cùng chịu ràng buộc thời gian sống của arena.
try {
    viewOutside.get(ValueLayout.JAVA_BYTE, 0);
} catch (IllegalStateException expected) {
    System.out.println("closed-scope");
}
```

Đoạn nằm trong method có import `Arena`, `MemorySegment`, `ValueLayout`, `ByteBuffer`.

**Quy tắc từ Javadoc:** nếu buffer được tạo từ `asByteBuffer()` của segment có scope `S`, segment tạo lại bằng `ofBuffer(buffer)` **gắn với cùng scope `S`**. Kết thúc `try (Arena ...)` sẽ đóng `Arena.ofConfined()`, khiến backing native allocation bị giải phóng; việc giữ `nioView` hoặc `viewOutside` trong Java **không kéo dài thêm lifetime**.

Vì thế:

- `ByteBuffer.allocateDirect(...) → MemorySegment.ofBuffer(...)`: một buffer được JVM quản lý theo automatic scope giữ buffer reachable.
- `Arena.allocate(...) → asByteBuffer() → MemorySegment.ofBuffer(...)`: buffer/segment views **vay mượn** lifetime của arena; close arena là invalidation point của mọi view.

Cả hai là native segments và thường có `isNative() == true`. **Không thể suy ra lifetime chỉ từ `isNative()`**. Phải truy nguồn gốc vùng nền.

### 5.1. `asByteBuffer()` không chuyển ownership

`MemorySegment.asByteBuffer()` tạo view NIO trên cùng bytes. Nó **không copy**, không tạo một arena mới, không đổi thành lifetime của `ByteBuffer.allocateDirect`.

Một `ByteBuffer` được trả từ `asByteBuffer()` thường có:

- `position = 0`.
- `limit = capacity = segment.byteSize()`.
- Thuộc tính read-only giống segment.
- Direct nếu segment native.
- Byte order ban đầu là `BIG_ENDIAN` (theo Javadoc của `asByteBuffer`), có thể gọi `order(...)` để đổi.

Nếu segment lớn hơn `Integer.MAX_VALUE` hoặc không thể biểu diễn dưới dạng ByteBuffer, `asByteBuffer()` có thể ném `UnsupportedOperationException`. Segment có thể hỗ trợ kích thước lớn hơn giới hạn `int` của NIO buffer; **không ép mọi workload memory-mapped lớn qua ByteBuffer**.

### 5.2. Đóng arena khiến cả buffer NIO cũng mất hiệu lực

Khi `ByteBuffer` đến từ arena segment, việc dùng nó sau khi arena đóng có thể ném `IllegalStateException`. Nếu arena confined, truy cập từ thread khác có thể ném `WrongThreadException`.

Đừng cố lấy một view từ segment rồi xuất nó ra như API trả `ByteBuffer` “sống mãi” nếu arena sắp đóng:

```java
// Anti-pattern: trả view trên vùng sẽ bị đóng trước khi caller dùng.
static ByteBuffer invalidView() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(16).asByteBuffer();
    }
}
```

Đây là **anti-pattern biên dịch được** nhưng trả về một view không sử dụng an toàn sau khi phương thức thoát. Cách đúng là đưa ownership của arena lên caller, hoặc copy bytes trước khi đóng.

## 6. Bảng lifetime: gốc tạo view quyết định ownership

| Cách tạo segment | Loại memory | Scope/lifetime chính | Ai giải phóng vùng nền? |
| --- | --- | --- | --- |
| `MemorySegment.ofArray(byte[])` | Heap | Automatic scope giữ array reachable, truy cập nhiều thread | Java GC, không close thủ công |
| `MemorySegment.ofBuffer(ByteBuffer.allocate(n))` | Heap | Automatic scope giữ buffer/array nền | Java GC |
| `MemorySegment.ofBuffer(ByteBuffer.wrap(array))` | Heap | Automatic scope giữ buffer/array nền | Java GC |
| `MemorySegment.ofBuffer(ByteBuffer.allocateDirect(n))` | Native | Automatic scope giữ direct buffer reachable | JVM/allocator của direct buffer theo contract |
| `MemorySegment.ofBuffer(arenaSegment.asByteBuffer())` | Native (nếu arena native) | **Chính scope của `arenaSegment`** | Arena owner đóng đúng lúc |
| `arena.allocate(bytes)` | Native | Scope của `Arena.ofConfined/ofShared/ofAuto/...` | Arena/cleaner theo arena kind |
| `segment.asSlice(offset, length)` | Như segment gốc | Scope/lifetime kế thừa | Owner của vùng nền gốc |
| `segment.asReadOnly()` | Như segment gốc | Scope/lifetime kế thừa, chỉ bỏ quyền ghi | Owner của vùng nền gốc |
| `segment.toArray(ValueLayout.JAVA_BYTE)` | Mảng Java **mới** | Array mới không còn alias với segment gốc | Java GC cho array mới |

Lưu ý: `Arena.ofAuto()` là scope tự động được quản lý theo reachability, không close tường minh; `Arena.global()` không có điểm close chủ động; `Arena.ofConfined()` và `Arena.ofShared()` là các arena closeable. Phần này chỉ dùng những arena loại phổ biến; API caller phải tham khảo Javadoc phiên bản JDK đang chạy.

Đừng “double close” native allocation khi nhiều view cùng tham chiếu nó. Một segment slice không phải owner riêng của một allocation. Nếu một thư viện cần nắm ownership độc lập, hãy định nghĩa rõ chuyển giao hoặc cấp phát/copy dữ liệu mới.

## 7. Phân biệt *alias/view* với *copy/snapshot*

Một thao tác giữ nguyên vùng nền:

```java
byte[] original = {1, 2, 3, 4};
MemorySegment all = MemorySegment.ofArray(original);
MemorySegment slice = all.asSlice(1, 2);

slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
System.out.println(original[1]); // 9
```

`asSlice(1, 2)` không tạo allocation: slice có `byteSize() == 2`, offset 0 của slice tương ứng index 1 của array. Thay đổi qua slice được quan sát qua `all`, `original` và mọi view khác của vùng đó.

Ngược lại, tạo snapshot:

```java
byte[] snapshot = slice.toArray(ValueLayout.JAVA_BYTE);
slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);

System.out.println(snapshot[0]); // 9 (bản copy độc lập)
System.out.println(original[1]); // 7 (vùng gốc)
```

Đây là hai đoạn **trong method**; đoạn sau giả định `slice` và `original` đã có từ đoạn trước.

Một cách khác để copy sang vùng native riêng:

```java
try (Arena destinationArena = Arena.ofConfined()) {
    MemorySegment destination = destinationArena.allocate(
        slice.byteSize());
    MemorySegment.copy(slice, 0, destination, 0, slice.byteSize());

    // destination có backing allocation riêng:
    // thay đổi slice không tự làm thay đổi destination.
}
```

Đoạn cuối minh họa code khi `slice` hợp lệ và không bị read-only; vùng copy có lifetime của `destinationArena`. Nếu cần để kết quả sống ngoài block, không được trả `destination` mà vẫn đóng arena; có thể trả bản copy `byte[]` hoặc chuyển ownership arena cho caller.

### 7.1. Khi nào nên copy thay vì view?

Copy có chi phí cấp phát và băng thông bộ nhớ, nhưng hữu ích khi:

1. Dữ liệu phải sống **lâu hơn arena gốc**, ví dụ kết quả trả về từ API nằm ngoài `try-with-resources`.
2. Caller/callee cần **ownership độc lập**, không muốn thay đổi bên này hiện ngay bên kia.
3. Buffer được tái sử dụng cho lần nhận gói tin tiếp theo, trong khi task async vẫn cần snapshot cũ.
4. Dữ liệu chạy giữa các thread không có cơ chế đồng bộ hoặc không muốn giữ backing direct buffer lâu.
5. Dữ liệu native không an toàn để tham chiếu sau một callback, hoặc một thư viện C chỉ bảo đảm pointer trong thời gian ngắn.

Không dùng copy chỉ vì muốn đổi kiểu Java cho tiện khi zero-copy sharing được hợp đồng lifetime cho phép; nhưng đừng tối ưu bằng zero-copy nếu nó buộc phải giữ allocation rất lớn lâu hơn cần thiết.

## 8. Byte offsets, alignment và byte order

FFM đọc/ghi qua một `ValueLayout` cụ thể:

```java
segment.get(ValueLayout.JAVA_BYTE, 0);
segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

segment.get(ValueLayout.JAVA_INT, 0);
segment.setAtIndex(ValueLayout.JAVA_INT, 1, 42);
```

Các dòng minh họa cần một `segment` đủ lớn và đúng alignment. Quy tắc:

- `get/set(layout, offset)` dùng **byte offset**.
- `getAtIndex/setAtIndex(layout, index)` dùng **logical index**, offset thực tế được nhân với `layout.byteSize()`.
- `ValueLayout.JAVA_INT` yêu cầu bốn byte cho một giá trị `int`, với alignment tương ứng. Nếu buffer window bắt đầu ở offset byte lẻ, thao tác int ở đầu view có thể **không thỏa alignment**; nên dùng byte layout hoặc một layout unaligned thích hợp khi dữ liệu packed theo contract.
- `ValueLayout.JAVA_INT` dùng **native byte order**. `ByteBuffer.order()` có thể đang là big-endian hoặc little-endian; việc đổi byte order của ByteBuffer **không làm ValueLayout tự đổi**. Muốn cùng cách giải mã binary, chỉ định `ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN)` hoặc thứ tự theo giao thức.
- Heap array `int[]` không phải là một `byte[]` tự do định dạng bất kỳ: khi tạo segment từ `int[]`, phải dùng layout/bounds/alignment tương thích.

Ví dụ đọc dữ liệu little-endian từ một buffer window (mã đặt trong method):

```java
ByteBuffer b = ByteBuffer.allocate(4);
b.put(0, (byte) 0x04);
b.put(1, (byte) 0x03);
b.put(2, (byte) 0x02);
b.put(3, (byte) 0x01);

MemorySegment s = MemorySegment.ofBuffer(b);
int n = s.get(
    ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.LITTLE_ENDIAN),
    0);
System.out.println(n); // 16909060 (0x01020304)
```

Ở đây `JAVA_INT_UNALIGNED` cho phép vùng packed không phải lúc nào cũng aligned theo int (dù buffer ví dụ có offset 0), và `withOrder` làm kết quả độc lập endianness của CPU. Import thêm `java.nio.ByteOrder`. Với protocol binary thực tế, cũng cần định nghĩa signedness, magic/version, chiều dài, checksum và kiểm tra bounds.

## 9. Chương trình Java 22+ đầy đủ: kiểm tra alias, phạm vi, lifetime

Ví dụ sau **không cần JNI hay thư viện C**; nó chỉ dùng API ổn định `java.lang.foreign`. Các giá trị in ra là xác định, không dựa vào địa chỉ native hoặc thời gian GC.

### 9.1. File `SegmentBackingDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

public final class SegmentBackingDemo {
    public static void main(String[] args) {
        // 1. ofArray: heap memory, zero-copy alias.
        byte[] bytes = {10, 20, 30, 40};
        MemorySegment fromArray = MemorySegment.ofArray(bytes);

        System.out.println("array-native=" + fromArray.isNative());

        fromArray.set(ValueLayout.JAVA_BYTE, 1, (byte) 21);
        System.out.println("array-second=" + bytes[1]);

        // 2. ofBuffer trên heap ByteBuffer chỉ nhìn position..limit.
        ByteBuffer heapBuffer = ByteBuffer.wrap(bytes);
        heapBuffer.position(1);
        heapBuffer.limit(3);

        MemorySegment window = MemorySegment.ofBuffer(heapBuffer);
        System.out.println("window-size=" + window.byteSize());
        System.out.println(
            "window-first=" + window.get(ValueLayout.JAVA_BYTE, 0));

        window.set(ValueLayout.JAVA_BYTE, 1, (byte) 31);
        System.out.println("array-third=" + bytes[2]);
        System.out.println(
            "buffer-cursor=" + heapBuffer.position()
                + "/" + heapBuffer.limit());

        // 3. Typed primitive array; index của int nhân 4 byte.
        int[] numbers = {100, 200};
        MemorySegment intSegment = MemorySegment.ofArray(numbers);
        intSegment.setAtIndex(ValueLayout.JAVA_INT, 1, 250);
        System.out.println("ints-bytes=" + intSegment.byteSize());
        System.out.println("ints-second=" + numbers[1]);

        // 4. Direct ByteBuffer: native memory, vẫn zero-copy.
        ByteBuffer direct = ByteBuffer.allocateDirect(4);
        direct.put(1, (byte) 7);
        direct.position(1);
        direct.limit(3);

        MemorySegment directWindow = MemorySegment.ofBuffer(direct);
        System.out.println("direct-native=" + directWindow.isNative());
        System.out.println("direct-size=" + directWindow.byteSize());

        directWindow.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
        System.out.println("direct-at-one=" + direct.get(1));

        // 5. Quyền read-only được kế thừa.
        ByteBuffer readOnly =
            ByteBuffer.wrap(new byte[] {1, 2}).asReadOnlyBuffer();
        MemorySegment readOnlySegment = MemorySegment.ofBuffer(readOnly);
        System.out.println("read-only=" + readOnlySegment.isReadOnly());

        // 6. Một ByteBuffer từ Arena không sống lâu hơn Arena.
        MemorySegment viewFromArenaBuffer;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment allocated = arena.allocate(2);
            allocated.set(ValueLayout.JAVA_BYTE, 0, (byte) 55);

            ByteBuffer nioView = allocated.asByteBuffer();
            viewFromArenaBuffer = MemorySegment.ofBuffer(nioView);

            System.out.println(
                "arena-value="
                    + viewFromArenaBuffer.get(ValueLayout.JAVA_BYTE, 0));
        }

        System.out.println(
            "arena-scope-alive="
                + viewFromArenaBuffer.scope().isAlive());

        try {
            viewFromArenaBuffer.get(ValueLayout.JAVA_BYTE, 0);
            System.out.println("unexpected-access");
        } catch (IllegalStateException expected) {
            System.out.println("after-close=IllegalStateException");
        }
    }
}
```

**Giải thích theo thứ tự in ra:**

1. `array-native=false`: `ofArray(byte[])` là heap segment.
2. `array-second=21`: segment thay đổi chính mảng nguồn.
3. `window-size=2` và `window-first=21`: `position=1, limit=3` tạo view đúng hai byte, offset 0 của view trỏ tới phần tử array[1].
4. `array-third=31`: ghi offset 1 của view tác động tới array[2].
5. `buffer-cursor=1/3`: tạo/sử dụng segment không làm position và limit của buffer gốc tự thay đổi.
6. `ints-bytes=8`, `ints-second=250`: mảng hai `int` có tám byte; `setAtIndex` cập nhật phần tử thứ hai.
7. `direct-native=true` và `direct-size=2`: direct buffer cho native segment nhưng chỉ có view hai byte trong khoảng position..limit.
8. `direct-at-one=9`: segment và direct buffer cùng backing allocation.
9. `read-only=true`: read-only được bảo tồn.
10. `arena-value=55`: view NIO từ arena vẫn đọc được trước khi đóng.
11. `arena-scope-alive=false` và `after-close=IllegalStateException`: view segment tạo ngược từ buffer có cùng lifetime của arena gốc.

### 9.2. Biên dịch và chạy

Dùng **JDK 22 trở lên**. FFM API trong JDK 21 còn ở dạng preview và có quy tắc sử dụng khác; bài này không target JDK 17 hay Java 21 preview.

```bash
javac SegmentBackingDemo.java
java SegmentBackingDemo
```

**Stdout chính xác của chương trình:**

```text
array-native=false
array-second=21
window-size=2
window-first=21
array-third=31
buffer-cursor=1/3
ints-bytes=8
ints-second=250
direct-native=true
direct-size=2
direct-at-one=9
read-only=true
arena-value=55
arena-scope-alive=false
after-close=IllegalStateException
```

Bài mẫu **không gọi foreign function**, không `reinterpret` address và không dùng các restricted linker APIs; vì vậy với JDK 22 thông thường, **không cần `--enable-preview`** để biên dịch hoặc chạy. Nếu triển khai chương trình FFM có gọi các API hạn chế về native access, phải cấu hình quyền native access theo JDK/module thực tế.

### 9.3. Vì sao không in địa chỉ hoặc cưỡng bức GC?

Chúng ta không in `segment.address()` hay `ByteBuffer` raw pointer vì chúng phụ thuộc JVM, ASLR, OS và từng lần chạy. Cũng không ép `System.gc()` để kiểm tra lifetime direct buffer: việc GC có hoặc không chạy vào thời điểm đó không phải hợp đồng Java.

Ngược lại, `Arena.ofConfined()` có một điểm close xác định. Điều này cho phép kiểm thử **thời gian sống được ràng buộc bởi scope** một cách ổn định, không phải phỏng đoán khi nào cleaner sẽ thu hồi memory.

## 10. Thời gian sống: automatic scope khác explicit close thế nào?

FFM cung cấp các scope để gắn *temporal bounds* với quyền truy cập. Nhưng **không phải lúc nào scope cũng cho phép caller đóng**.

### 10.1. Automatic scope của array/direct buffer

Khi tạo segment từ mảng hay direct buffer NIO thông thường, FFM dùng automatic scope để giữ backing object reachable. Nó không có phương thức close để bạn tự “giải phóng sớm” vùng nhớ của buffer.

Đây là quản lý dựa trên **reachability**, không phải “TTL 10 giây”. Bộ nhớ chỉ đủ điều kiện được thu hồi khi không còn references liên quan và runtime quyết định thực hiện cleanup. Một `MemorySegment`, `asSlice` hoặc view còn reachable có thể kéo dài thời gian giữ backing direct buffer. Trong các hệ thống đọc file/socket lớn, giữ những segment view trong cache lâu có thể kéo dài **native memory footprint**.

### 10.2. Confined/shared arena: caller sở hữu điểm close

`Arena.ofConfined()` và `Arena.ofShared()` tạo arena có thể close. Native memory cấp phát trong arena đó bị invalidated sau khi đóng. Scope của segment vẫn được dùng để kiểm tra liveness và thread accessibility.

- `Arena.ofConfined()`: chỉ owner thread được truy cập/đóng; thread khác có thể nhận `WrongThreadException` khi truy cập.
- `Arena.ofShared()`: nhiều thread có thể truy cập, có thể close theo quy định của arena; nhưng vẫn phải đồng bộ khi có mutable data sharing.
- `Arena.ofAuto()`: automatic memory management, không close chủ động; thời điểm cleanup phụ thuộc reachability.
- `Arena.global()`: global lifetime, không close thủ công; cần tránh cấp phát không kiểm soát nếu muốn có resource limit.

Không được gửi segment từ confined arena sang worker thread khác rồi kỳ vọng nó có thể sử dụng chỉ vì Java object còn reachable. Reachability và thread confinement là **hai kiểm tra độc lập**.

### 10.3. Kiểm tra `scope().isAlive()` không làm access vĩnh viễn an toàn

Có thể quan sát:

```java
boolean alive = segment.scope().isAlive();
boolean allowed = segment.isAccessibleBy(Thread.currentThread());
```

Đây là code trong method đã có `segment` hợp lệ.

Tuy nhiên, hai phép kiểm tra là quan sát **tại một thời điểm**. Với shared arena, thread khác có thể bắt đầu đóng arena sau khi bạn kiểm tra. FFM tự thực hiện kiểm tra temporal/spatial bounds cho mỗi operation; không sử dụng `isAlive()` như một chứng chỉ lifetime dài hạn. Trong API concurrent, cần protocol ownership và shutdown rõ ràng.

## 11. Giao tiếp native: heap view không tự trở thành pointer C

Tên `MemorySegment` xuất hiện trong FFM không có nghĩa mọi backing storage đều có địa chỉ native hợp lệ.

### 11.1. Heap array

`MemorySegment.ofArray(byte[])` là Java heap. GC có thể di chuyển object và segment không biến array thành một vùng malloc ổn định. Bạn **không** được lấy `heap.address()` rồi dùng như địa chỉ C của `byte[0]`. Khi một API C yêu cầu pointer native tới buffer ổn định, lựa chọn an toàn phổ biến là:

1. Cấp phát off-heap qua `Arena.allocate(n)` phù hợp lifecycle.
2. Copy bytes từ heap segment sang native segment với `MemorySegment.copy(...)`.
3. Gọi native function trong khi arena còn sống và đồng bộ quyền truy cập.
4. Copy kết quả về khi contract yêu cầu.
5. Close arena sau khi không còn native code giữ pointer.

Một số FFM linker options có hỗ trợ đặc biệt cho heap segments trong những điều kiện riêng; đừng tự suy diễn các ngoại lệ này thành quyền truyền mọi heap address cho native library.

### 11.2. Direct buffer

Direct buffer gắn với native memory, nhưng native library cần contract về **byte count, alignment, read-only, ownership và thời gian lưu pointer**. Khi native code chỉ đọc/ghi **đồng bộ trong lời gọi**, một view còn sống có thể phù hợp. Nếu native code **lưu pointer để dùng sau khi hàm trả về**, việc giữ Java object tạm trong stack hiện tại chưa đủ: phải có owner đảm bảo backing memory vẫn sống cho tới khi native async operation kết thúc.

Không tự do `free()` một địa chỉ nhận từ direct buffer trừ khi API sở hữu allocation yêu cầu chính điều đó. Direct buffer thông thường không đồng nghĩa với C `malloc` mà caller tự sở hữu.

### 11.3. Arena-backed ByteBuffer

Nếu native callback nhận một `ByteBuffer` từ segment đã được arena cấp phát, vùng đó mất hiệu lực khi arena đóng, **dù buffer hoặc segment mới tạo từ nó vẫn còn trong một field Java**. Khi chuyển API qua nhiều tầng, hãy truyền thêm **ownership/lifetime contract**, không chỉ trả `ByteBuffer` hay `MemorySegment`.

Cách thiết kế thường dùng là một object chủ sở hữu `AutoCloseable` chứa cả `Arena` và `MemorySegment`, hoặc thực hiện copy ở ranh giới nếu caller không thể giữ arena.

## 12. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `ofArray` copy dữ liệu | Nó tạo view trên array gốc | Nếu cần snapshot, dùng `toArray` hoặc `copy` |
| Nghĩ `ofBuffer` luôn nhìn toàn capacity | API lấy `position..limit` | Kiểm tra `remaining()`; đặt cursor trước khi wrap |
| Nghĩ `segment offset=0` luôn là `array[0]` | Buffer có thể có position/array offset | Map view offset theo buffer window |
| Thay đổi buffer position rồi kỳ vọng segment đã tạo đổi phạm vi | Segment giữ view xác định lúc tạo | Tạo segment mới khi muốn window khác |
| Nghĩ `isNative() == true` nghĩa là memory do arena sở hữu | Direct ByteBuffer thường cũng native | Theo dõi nguồn tạo backing storage |
| Đóng arena rồi giữ `asByteBuffer()` | View không kéo dài arena lifetime | Giữ arena còn sống hoặc copy trước khi close |
| Dùng `System.gc()` để chủ động release direct memory | GC không có deadline do caller kiểm soát | Quản lý resource/lifetime rõ, giảm reference retention |
| Coi `heapBase().isEmpty()` nghĩa là native | Read-only heap segment có thể giấu heapBase | Sử dụng `isNative()` |
| Dùng `address()` của heap segment như C pointer | Heap address không phải native address | Copy/thiết kế FFM call phù hợp |
| Gọi `set(JAVA_INT, 1, x)` để ghi int thứ hai | Offset là **byte**, không phải index | `setAtIndex(JAVA_INT, 1, x)` hoặc offset=4 |
| Trộn `ByteBuffer.order()` với `ValueLayout.JAVA_INT` tùy tiện | Hai API có byte-order riêng | Cấu hình `ValueLayout.withOrder(...)` |
| Truy cập int ở view bắt đầu byte lẻ | Có thể vi phạm alignment | Chọn layout unaligned phù hợp hoặc copy/align |
| Coi read-only buffer thành writable segment | Read-only được kế thừa | Ghi vào bản copy writable nếu cần |
| Truy cập `Arena.ofConfined` từ thread khác | Thread confinement | Dùng owner thread hoặc shared arena đúng contract |
| Tin `isAlive()` đảm bảo cho toàn future | Scope có thể bị đóng sau check | Synchronization và ownership protocol |
| Tự free memory của `ByteBuffer.allocateDirect` | Double-free/dangling view | Để owner JVM quản lý đúng contract |
| Tự map/unmap bên ngoài trong khi có FFM view | Lifetime không còn do segment kiểm soát | Tập trung owner và release theo contract |
| Truyền raw pointer từ heap array sang C | GC có thể di chuyển heap object | Dùng FFM/native allocation đúng cách |
| Dùng `ByteBuffer` cho segment lớn hơn 2 GiB | NIO buffer index/capacity giới hạn int | Truy cập segment trực tiếp bằng long offsets |

## 13. Test cases và cách quan sát

Để kiểm chứng đoạn code tự viết, nên có các test sau:

1. **Heap alias:** tạo `byte[]`, wrap bằng `ofArray`, ghi qua segment, so sánh byte trong array. Đổi chiều cập nhật array rồi đọc lại qua segment.
2. **Buffer window:** đặt `position=2`, `limit=5` trên buffer sáu byte; segment phải có `byteSize=3`. Offset 0 của segment phải là byte gốc tại position 2.
3. **Cursor snapshot:** sau khi tạo segment, thay đổi position/limit của buffer gốc; segment không tự đổi view đã có.
4. **Direct alias:** `allocateDirect` → `ofBuffer` → ghi từ segment → đọc lại bằng `ByteBuffer.get(index)`.
5. **Read-only:** tạo `asReadOnlyBuffer`; `ofBuffer` phải duy trì read-only và chặn ghi.
6. **Unbacked heap Buffer:** với `CharBuffer.wrap("abc")`, xác minh `ofBuffer` có thể ném `IllegalArgumentException` do không có array backing theo Javadoc; đừng giả định thành công với mọi Buffer.
7. **Arena lifetime:** `arena.allocate → asByteBuffer → ofBuffer`; truy cập trước close thành công, sau close ném `IllegalStateException`.
8. **Thread confinement:** segment từ `Arena.ofConfined` truy cập sai thread phải có lỗi phù hợp; tạo test deterministic với thread join và exception capture. Không thay thế bằng race-prone `Thread.sleep`.
9. **Snapshot:** `toArray(JAVA_BYTE)` trước khi sửa view; snapshot phải giữ giá trị cũ.
10. **Bounds:** đọc ở offset vượt `byteSize()` phải ném `IndexOutOfBoundsException`, kể cả khi backing array gốc còn bytes ngoài window.
11. **Alignment:** thử một packed byte protocol đọc int bằng layout aligned rồi kiểm tra `IllegalArgumentException` ở offset không aligned; dùng layout unaligned nếu contract cho phép.
12. **Endian:** dùng mẫu bytes cố định, kiểm tra `withOrder(LITTLE_ENDIAN)` trên JVM big- hoặc little-endian theo kết quả mong đợi.
13. **Liveness and reachability:** dùng lifetime được đảm bảo bởi Arena/scope cho test chắc chắn; không viết test phụ thuộc việc `System.gc()` thu hồi direct buffer ngay.
14. **Native async:** nếu foreign call lưu pointer, kiểm tra quyền sở hữu dữ liệu và việc cleanup chỉ xảy ra sau callback/completion, kể cả timeout.
15. **Performance:** đo throughput và native memory footprint của zero-copy views vs snapshots theo kích thước thực, thay vì giả định zero-copy luôn tốt hơn.

Một test assertion nhỏ không cần JUnit (đặt trong method với `byte[] bytes`):

```java
MemorySegment s = MemorySegment.ofArray(bytes);
int previous = Byte.toUnsignedInt(s.get(ValueLayout.JAVA_BYTE, 0));
byte[] clone = s.toArray(ValueLayout.JAVA_BYTE);
s.set(ValueLayout.JAVA_BYTE, 0, (byte) (previous + 1));
if (clone[0] == bytes[0]) {
    throw new AssertionError("Expected independent snapshot");
}
```

Đây là **đoạn kiểm thử minh họa**; với giá trị byte có thể wrap khi tăng, nên kết luận ở đây chỉ dựa vào việc snapshot giữ giá trị cũ, không giả định trị số sau khi tăng nằm trong miền signed byte. Trong production, dùng JUnit và có test fixtures rõ ràng.

## 14. Checklist thiết kế và ghi nhớ

Trước khi trả một `MemorySegment` từ API hoặc chuyển nó sang một tầng khác:

- Segment được tạo bằng `ofArray`, `ofBuffer`, `Arena.allocate` hay `asSlice`?
- Vùng nền là Java heap, direct ByteBuffer do JVM quản lý, file mapping, hay allocation của arena/native library?
- Có **copy** hay chỉ tạo **view alias**? Nếu alias, bên nào có thể sửa bytes?
- `ofBuffer` lấy đúng khoảng `position..limit` chưa? Offset 0 ứng với byte nào trong backing storage?
- Segment có read-only không? Layout dùng đúng byte alignment và byte order của protocol chưa?
- `scope()` là automatic hay arena-bound? Ai giữ backing object reachable hoặc ai giữ arena alive?
- Nếu close arena, các ByteBuffer views hoặc segment được tạo ngược từ chúng có thể thoát ra ngoài không?
- Đang dùng shared hay confined arena? Có truy cập từ thread khác hoặc race với close không?
- Có native code giữ pointer qua lời gọi không? Nếu có, owner nào đảm bảo memory còn sống?
- Có dựa vào address() của heap segment hoặc GC timing như bảo đảm native lifetime không?
- Nếu data cần sống độc lập, đã tạo snapshot/copy và có contract close của allocation mới chưa?
- Test đã chứng minh alias, copy, read-only, bounds, liveness và thread confinement đúng mong đợi chưa?

**Kết luận:** `MemorySegment.ofArray(array)` và `MemorySegment.ofBuffer(buffer)` chủ yếu tạo **cửa sổ truy cập an toàn vào bộ nhớ đã tồn tại**. `ofArray` giữ Java array reachable. `ofBuffer` trên buffer thông thường dùng automatic scope giữ buffer reachable, nhưng nếu buffer bắt nguồn từ `segment.asByteBuffer()` thì segment mới **kế thừa scope của segment gốc**. Hãy theo dấu **nguồn allocation, scope và điểm close thực sự**, thay vì suy đoán lifetime từ kiểu Java hay từ `isNative()`.

### Tài liệu tham khảo chính thức

- [Java SE 22 — MemorySegment API: ofArray, ofBuffer, scope, asByteBuffer, toArray](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — Arena: confined/shared/automatic và temporal safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — ValueLayout, alignment và byte order](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 22 — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (final)](https://openjdk.org/jeps/454)
- [Java SE 22 — ByteBuffer API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html)
