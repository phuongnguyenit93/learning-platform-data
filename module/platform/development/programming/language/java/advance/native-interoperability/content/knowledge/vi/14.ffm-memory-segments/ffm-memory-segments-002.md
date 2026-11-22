# Địa chỉ, kích thước, scope và căn chỉnh của một MemorySegment

## 1. Mục tiêu bài học và phiên bản Java

Khi làm việc với mã native hoặc vùng nhớ ngoài heap, một con trỏ C kiểu `void*` chỉ cho biết địa chỉ. Nó **không tự mô tả** vùng nhớ dài bao nhiêu, còn hợp lệ đến khi nào, hay có đủ căn chỉnh để đọc một `int`/`long` hoặc cấu trúc C hay không. Việc đọc vượt biên, truy cập sau `free` và đọc từ địa chỉ không căn chỉnh là những nguồn lỗi phổ biến của mã native.

Trong Foreign Function & Memory API (FFM), Java biểu diễn một vùng nhớ bằng **`java.lang.foreign.MemorySegment`**. Một segment không chỉ là một con số chứa địa chỉ; nó là một **view có các ràng buộc**. Bốn đặc điểm quan trọng nhất của một segment là:

1. **Địa chỉ (`address`):** vùng nhớ bắt đầu ở đâu trong mô hình địa chỉ của segment?
2. **Kích thước (`byteSize`):** view này cho phép truy cập tối đa bao nhiêu byte?
3. **Scope (`scope`):** vùng nhớ và quyền truy cập còn hiệu lực hay đã kết thúc? Có bị hạn chế theo thread không?
4. **Căn chỉnh (`maxByteAlignment` và `MemoryLayout.byteAlignment`):** địa chỉ truy cập có phù hợp với cách biểu diễn và thao tác đọc/ghi dự kiến không?

Học xong bài này, bạn cần giải thích được sự khác nhau giữa **segment native và heap**, tạo segment với kích thước và alignment yêu cầu, dùng `asSlice` để giới hạn view, đọc/ghi theo `ValueLayout`, xác định khi nào access bị chặn vì vượt biên/scope/thread/alignment, và tránh biến một địa chỉ native thành con trỏ mất an toàn.

**Yêu cầu phiên bản:** các ví dụ dùng API chuẩn `java.lang.foreign`, được hoàn thiện trong **JDK 22** (JEP 454) và chạy với **JDK 22+**. JDK 17 có Foreign Memory API ở trạng thái *incubator* với package/API khác; không thể copy trực tiếp mã dưới đây sang JDK 17 rồi chỉ thêm một import. Các ví dụ thao tác `Arena.allocate` và `MemorySegment.get/set` an toàn không cần `--enable-preview` trên JDK 22+.

## 2. Mô hình trực quan: một view của vùng nhớ có bốn ràng buộc

Giả sử một arena cấp phát 32 byte, với alignment 8 byte:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(32, 8);
    // Sử dụng segment khi arena còn mở.
}
```

Có thể hình dung:

```text
Native address: A (A chia hết cho 8)
                  |
                  v
        +---------+-------------------------------------------+
        | byte 0  | byte 1 ...                ... byte 31    |
        +-----------------------------------------------------+
          <----------------- 32 bytes --------------------->

MemorySegment
  address()            = A             (giá trị địa chỉ phụ thuộc lần chạy)
  byteSize()           = 32            (đơn vị: byte, không phải số phần tử)
  scope()              = scope của arena
  maxByteAlignment()   >= 8            (căn chỉnh tối đa thực tế có thể lớn hơn)
```

Nếu tạo một slice:

```java
MemorySegment slice = segment.asSlice(8, 8);
```

thì slice bắt đầu tại `A + 8`, chỉ dài 8 byte, **dùng chung backing memory và scope** với segment gốc. Slice **không cấp phát vùng nhớ riêng** và **không sở hữu một lần `free` riêng**.

Bốn yếu tố phải được xem đồng thời:

| Yếu tố | API chính | Điều được đảm bảo hoặc giới hạn |
| --- | --- | --- |
| Vị trí bắt đầu | `segment.address()` | Trả một giá trị `long` biểu diễn địa chỉ theo loại segment |
| Kích thước view | `segment.byteSize()` | Các lần truy cập được kiểm tra trong biên `[0, byteSize)` |
| Vòng đời | `segment.scope()`, `scope().isAlive()` | Access bị từ chối khi scope không còn sống; arena quyết định vòng đời native allocation |
| Căn chỉnh khả dụng | `segment.maxByteAlignment()` | Mức alignment tối đa segment hỗ trợ; access còn phải đáp ứng layout và offset cụ thể |
| Quyền luồng | `segment.isAccessibleBy(thread)` | Cho biết thread có phù hợp với confinement của segment hay không |
| Kiểu dữ liệu | `ValueLayout` / `MemoryLayout` | Diễn giải số byte cần đọc, byte order, alignment, field offset |

**Không nhầm:** `MemorySegment` không phải một `byte[]` thông thường và cũng không giống con trỏ C không có biên. Các access methods an toàn của API thực hiện các kiểm tra liên quan trước khi đọc/ghi.

## 3. Địa chỉ: native segment khác heap segment

### 3.1. Native segment

Một native segment được `Arena.allocate` tạo thường tham chiếu tới **off-heap memory**. `segment.address()` là địa chỉ bắt đầu của vùng nhớ native, biểu diễn bằng `long`:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);
    long address = segment.address();

    System.out.println(segment.isNative()); // true
    System.out.println(address % 8 == 0);    // true
}
```

**Đừng ghi cứng địa chỉ cụ thể vào test.** Giá trị địa chỉ thay đổi theo process, lần cấp phát, hệ điều hành, kiến trúc và ASLR. `address()` thường là địa chỉ trong **không gian địa chỉ native của tiến trình**, không phải chứng nhận một địa chỉ RAM vật lý cố định.

Một địa chỉ có thể vẫn là số khác 0 **sau khi backing memory đã được giải phóng**. Giá trị `long` đó không sở hữu tài nguyên, không giữ scope sống và không tự cho phép truy cập. Dùng lại raw address sau đóng arena có nguy cơ use-after-free.

### 3.2. Heap segment

`MemorySegment.ofArray` tạo segment dựa vào mảng primitive trong Java heap:

```java
byte[] data = new byte[16];
MemorySegment heap = MemorySegment.ofArray(data);

System.out.println(heap.isNative()); // false
System.out.println(heap.address());  // 0
System.out.println(heap.byteSize()); // 16
```

Địa chỉ `0` của heap segment vừa tạo **không** có nghĩa nó là con trỏ C `NULL`. Theo API, địa chỉ heap segment là **offset đã ảo hóa trong backing storage**, chứ không phải địa chỉ máy có thể truyền trực tiếp cho một hàm C. Khi lấy `heap.asSlice(4, 8)`, `address()` của slice thể hiện offset tương ứng trong backing storage.

Garbage collector có thể di chuyển mảng thực tế trong Java heap; FFM che giấu vị trí vật lý đó và cung cấp view theo mô hình heap segment. Không lấy `heap.address()` rồi cast thành con trỏ native.

Các segment tạo từ mảng như `int[]`, `long[]` cũng có `byteSize()` tính bằng **byte**:

```java
MemorySegment ints = MemorySegment.ofArray(new int[5]);
System.out.println(ints.byteSize()); // 20: 5 số int, mỗi số 4 byte
```

Heap segments có scope tự động giữ backing array reachable phù hợp với vòng đời view; chúng không phải native allocations do `Arena.ofConfined` sở hữu và không được “free” bằng cách đóng một arena không liên quan.

### 3.3. Địa chỉ không đồng nghĩa quyền sở hữu hoặc biên

FFM còn có `MemorySegment.ofAddress(long)` để tạo một **native segment dài 0 byte**, gắn với global scope. Khi dài 0, mọi lần đọc có kích thước dương đều bị kiểm tra vượt biên.

`MemorySegment.NULL` tương tự là một biểu diễn null address zero-length, **không phải buffer dùng được**. Các `reinterpret(...)` có thể mở rộng view từ một raw address, nhưng là thao tác **restricted/unsafe** khi gán kích thước hoặc scope; nếu giá trị địa chỉ/kích thước/vòng đời bị khai báo sai, các bảo đảm ban đầu bị phá và có thể làm JVM crash hoặc hỏng bộ nhớ. Bài này không dùng `reinterpret` để “bỏ qua” kiểm tra.

**Kinh nghiệm thực tế:** giữ nguyên `MemorySegment` cùng scope của nó càng lâu càng tốt; chỉ truyền địa chỉ thô cho native code khi thực sự cần, hiểu rõ ABI và bên nào sở hữu việc giải phóng.

## 4. Kích thước: byteSize tạo ranh giới truy cập

### 4.1. byteSize luôn đo theo byte

`segment.byteSize()` trả về `long`, không phải `int` và không phải số phần tử. Ví dụ segment dài 32 byte:

- Đọc `JAVA_BYTE` (1 byte) tại offset 31: có thể hợp lệ.
- Đọc `JAVA_INT` (4 byte) tại offset 28: nằm đúng biên **nếu alignment hợp lệ**.
- Đọc `JAVA_LONG` (8 byte) tại offset 24: nằm đúng biên **nếu alignment hợp lệ**.
- Đọc `JAVA_LONG` tại offset 32: **vượt biên**, vì cần byte 32…39 ngoài view.

Điều kiện biên về mặt logic cho một access có `offset` và `layout.byteSize()` là:

```text
offset >= 0
layout.byteSize() >= 0
layout.byteSize() <= segment.byteSize() - offset
```

API thực hiện kiểm tra tránh vượt biên, kể cả những trường hợp offset/size không thể biểu diễn an toàn. Không tự thay bằng phép `offset + length <= byteSize` trong Java code không kiểm soát overflow.

### 4.2. Offset của get/set là byte offset

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment s = arena.allocate(16, 8);

    s.set(ValueLayout.JAVA_INT, 0, 123);
    s.set(ValueLayout.JAVA_INT, 4, 456);

    System.out.println(s.get(ValueLayout.JAVA_INT, 0)); // 123
    System.out.println(s.get(ValueLayout.JAVA_INT, 4)); // 456
}
```

Ở đây tham số thứ hai của `get/set` là **byte offset**, không phải “phần tử thứ 0/1/2”. Nếu muốn chỉ số phần tử, `getAtIndex(ValueLayout.JAVA_INT, i)` sẽ nhân `i` với kích thước layout, nhưng vẫn chịu kiểm tra biên và alignment.

Byte order cũng thuộc `ValueLayout`; ví dụ `JAVA_INT` dùng native byte order, còn `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` diễn giải 4 byte theo big-endian. Byte order và alignment là **hai ràng buộc khác nhau**.

### 4.3. Slicing: giới hạn quyền nhìn chứ không copy

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment whole = arena.allocate(32, 8);
    MemorySegment part = whole.asSlice(8, 8);

    part.set(ValueLayout.JAVA_INT, 0, 99);

    System.out.println(part.byteSize());                    // 8
    System.out.println(whole.get(ValueLayout.JAVA_INT, 8)); // 99
}
```

`part` và `whole` nhìn **cùng backing storage**. `part` bắt đầu ở offset 8 của `whole`, nhưng access trên `part` lại dùng offset **tương đối với part**: `part.get(..., 0)` chính là `whole.get(..., 8)`.

`asSlice` không tạo arena hay native allocation mới. Slice kế thừa scope, điều kiện sống và hạn chế thread từ nguồn. Khi arena đóng, cả `part` và `whole` không truy cập được nữa.

## 5. Scope: ranh giới thời gian và quyền sử dụng theo thread

### 5.1. Scope là gì?

Mỗi `MemorySegment` gắn với một `MemorySegment.Scope`, truy vấn bằng:

```java
MemorySegment.Scope scope = segment.scope();
boolean alive = scope.isAlive();
```

`isAlive()` là **trạng thái hiện tại** của scope. Khi scope của arena đóng tường minh bị invalidated, các segment liên quan không còn được phép access. Quan trọng: một lần kiểm tra `isAlive() == true` **không thể thay thế** các kiểm tra atomic/concurrency của API nếu thread khác có quyền đóng arena ngay sau đó.

**Spatial safety** kiểm tra địa chỉ và `byteSize`; **temporal safety** kiểm tra scope còn hợp lệ tại lúc access. Đây là hai lớp bảo vệ độc lập.

### 5.2. Bốn loại Arena thông dụng

| Arena | Vòng đời bộ nhớ cấp phát | Đóng tường minh bằng `close()`? | Quyền truy cập theo thread |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Kết thúc khi đóng arena | **Có** | Chỉ thread tạo arena được access và close |
| `Arena.ofShared()` | Kết thúc khi đóng arena | **Có** | Các thread có thể access; cần phối hợp lifecycle/đồng bộ dữ liệu |
| `Arena.ofAuto()` | GC quản lý, thời điểm thu hồi không định trước | **Không**; gọi close ném `UnsupportedOperationException` | Không giới hạn owner thread |
| `Arena.global()` | Không có điểm kết thúc do API quản lý; backing allocation sống không giới hạn | **Không**; close không hỗ trợ | Không giới hạn owner thread |

**Đừng nhầm `Arena.ofAuto` với “auto-close khi ra khỏi scope Java”.** Nó chỉ là lifetime **do GC quản lý**, không có thời hạn thu hồi tài nguyên đảm bảo. Đối với native memory lớn hoặc tài nguyên cần giải phóng đúng lúc, nên ưu tiên arena đóng được và `try-with-resources`.

`Arena.global()` dùng khi thật sự cần vùng nhớ sống suốt quá trình; cấp phát tùy tiện bằng global arena có thể giữ native memory đến khi process kết thúc.

### 5.3. Đóng arena invalidates tất cả segment có cùng scope

```java
MemorySegment s;
try (Arena arena = Arena.ofConfined()) {
    s = arena.allocate(8, 8);
    s.set(ValueLayout.JAVA_LONG, 0, 10L);
    System.out.println(s.scope().isAlive()); // true
} // arena.close() tự được gọi ở cuối try-with-resources

System.out.println(s.scope().isAlive()); // false
s.get(ValueLayout.JAVA_LONG, 0);          // IllegalStateException
```

Đoạn trên **minh họa exception**, không phải ví dụ chạy đến cuối bình thường. Trong chương trình chạy đầy đủ ở mục 7, ngoại lệ này được `catch` để chứng minh.

**Một điểm rất dễ nhầm:** việc giữ Java variable `s` không khiến backing native allocation tiếp tục hợp lệ sau `arena.close()`. Java object biểu diễn view có thể còn sống, trong khi vùng native memory đã được giải phóng.

`Arena.close()` **không idempotent**: nếu cố đóng cùng arena lần hai sau khi nó đã đóng, API ném `IllegalStateException`. Đây là chủ ý phát hiện lỗi vòng đời; đừng giả định giống mọi `close()` của wrapper khác.

### 5.4. Thread confinement cũng được kiểm tra khi access

Với `Arena.ofConfined()`, thread không phải owner không thể đọc/ghi segment của arena đó, kể cả khi `scope().isAlive()` đang true. Một access từ thread sai sẽ có thể bị từ chối bằng `WrongThreadException`.

Với `Arena.ofShared()`, các thread có thể access segment, nhưng **không tự đồng bộ hóa dữ liệu**. Ứng dụng vẫn phải giải quyết data races và tránh đóng arena trong khi một thread đang dùng tài nguyên. `Arena.close()` của shared arena có thể thất bại nếu có access đồng thời không thể đóng an toàn.

Có thể kiểm tra khả năng tiếp cận theo thread bằng `segment.isAccessibleBy(Thread.currentThread())`; đây là phép kiểm tra quyền truy cập, **không** chứng nhận bytes đã nằm trong biên hoặc layout đã căn chỉnh.

## 6. Alignment: địa chỉ cần chia hết cho gì?

### 6.1. Alignment biểu diễn theo byte và thường là lũy thừa của hai

Căn chỉnh `N` byte có nghĩa địa chỉ mục tiêu chia hết cho `N`. Chẳng hạn:

| Địa chỉ minh họa | Bội số 2? | Bội số 4? | Bội số 8? |
| --- | --- | --- | --- |
| 1000 | Có | Có | Có |
| 1004 | Có | Có | Không |
| 1006 | Có | Không | Không |
| 1007 | Không | Không | Không |

Để cấp phát vùng 32 byte căn chỉnh tối thiểu theo biên 8 byte:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment s = arena.allocate(32, 8);
    System.out.println(s.address() % 8 == 0); // true
}
```

`Arena.allocate(byteSize, byteAlignment)` yêu cầu alignment **dương và là lũy thừa của 2**. Ví dụ `arena.allocate(32, 3)` ném `IllegalArgumentException`; `arena.allocate(32, 8)` hợp lệ. Kích thước `byteSize` và alignment là **hai thông số độc lập**: cấp phát 32 byte căn 8 không có nghĩa mỗi 8 byte là một phần tử.

### 6.2. maxByteAlignment khác yêu cầu allocation alignment

`segment.maxByteAlignment()` trả alignment **tối đa mà segment hỗ trợ**, được suy ra từ địa chỉ segment và loại backing storage; luôn là lũy thừa của hai.

Giả sử arena cấp phát với `byteAlignment = 8`:

- API bảo đảm **ít nhất** alignment 8.
- `maxByteAlignment()` có thể bằng 8 hoặc **lớn hơn** (ví dụ địa chỉ tình cờ chia hết cho 16, 32…), nên không kiểm thử `maxByteAlignment() == 8`.
- Với `s.asSlice(1, 8)`, địa chỉ slice lệch 1 byte so với base đã căn 8. Nếu base chia hết cho 8, slice lệch 1 có `maxByteAlignment() == 1`.
- Một slice ở offset 8 có thể tiếp tục được căn 8.

Điều kiện kiểm tra nhanh một segment có phù hợp **ngay tại base** với layout hay không:

```java
boolean baseAcceptsLayout =
        segment.maxByteAlignment() >= layout.byteAlignment();
```

Tuy nhiên, với access ở `offset` khác 0, cần xét **địa chỉ mục tiêu (`address + offset`)**, không chỉ base. API `segment.get(layout, offset)` kiểm tra cả căn chỉnh của lần access cụ thể.

### 6.3. Layout quy định kích thước, alignment và byte order

`ValueLayout` mô tả cách diễn giải bytes. Một số layout thông dụng:

| Layout | Kích thước | Căn chỉnh mặc định |
| --- | ---: | ---: |
| `ValueLayout.JAVA_BYTE` | 1 byte | 1 byte |
| `ValueLayout.JAVA_SHORT` | 2 byte | 2 byte |
| `ValueLayout.JAVA_INT` | 4 byte | 4 byte |
| `ValueLayout.JAVA_LONG` | 8 byte | 8 byte |
| `ValueLayout.JAVA_FLOAT` | 4 byte | 4 byte |
| `ValueLayout.JAVA_DOUBLE` | 8 byte | 8 byte |

Ví dụ một native segment có base chia hết cho 8:

```java
MemorySegment s = arena.allocate(16, 8); // arena được tạo ở ngoài đoạn mã

s.set(ValueLayout.JAVA_LONG, 0, 11L); // đúng alignment
s.set(ValueLayout.JAVA_INT, 8, 22);   // đúng alignment
s.get(ValueLayout.JAVA_INT, 1);       // IllegalArgumentException (misaligned)
```

Cả offset 0, 8 và 1 đều **nằm trong biên** của segment 16 byte nếu xét riêng chiều dài các phép đọc; nhưng offset 1 không thỏa alignment 4 byte cho `JAVA_INT`. Vì vậy **in-bounds không đồng nghĩa aligned**.

### 6.4. Unaligned layout: có thể được phép, nhưng phải chủ động

JDK 22+ cung cấp `ValueLayout.JAVA_INT_UNALIGNED`, `JAVA_LONG_UNALIGNED` và các layout tương tự có `byteAlignment() == 1`.

```java
byte[] raw = new byte[16];
MemorySegment heap = MemorySegment.ofArray(raw);

// byte[] chỉ hỗ trợ maximum alignment 1.
int safe = heap.get(ValueLayout.JAVA_INT_UNALIGNED, 0);

// Với JAVA_INT mặc định (alignment 4), access trên heap byte[]
// sẽ ném IllegalArgumentException.
```

Khi dữ liệu nằm trong định dạng packed hoặc mạng, unaligned access có thể hữu ích; nhưng phải xét **endianness, ABI, hiệu năng và tính di động**. Unaligned layout không phải cách “chữa” việc khai báo sai cấu trúc native. Một số thao tác atomic/VarHandle còn đòi địa chỉ aligned và không thể tùy tiện dùng trên vùng không căn chỉnh.

**Phân biệt quan trọng:** `ValueLayout.JAVA_INT_UNALIGNED` đổi ràng buộc alignment của **lần đọc/ghi**, không thay đổi vị trí bytes thực tế, không tự sửa C struct packing và không cấp phát lại vùng nhớ.

### 6.5. Heap alignment phụ thuộc loại array

Một heap segment có địa chỉ ảo hóa `0` **không có nghĩa mọi alignment đều hợp lệ**. `maxByteAlignment()` của heap segment còn phụ thuộc kiểu backing primitive array:

- `MemorySegment.ofArray(new byte[16])` có max alignment 1.
- `MemorySegment.ofArray(new int[4])` thường có max alignment phù hợp `ValueLayout.JAVA_INT`, tức 4.
- `MemorySegment.ofArray(new long[2])` có max alignment phù hợp `ValueLayout.JAVA_LONG`, tức 8.

Không dùng phép chia số học `heap.address() % 8 == 0` để kết luận heap `byte[]` hỗ trợ layout 8 byte. Với heap segment, `address()` là offset ảo hóa; phải dựa vào **`maxByteAlignment()` và layout**.

## 7. Ví dụ chạy được Java 22+: kiểm tra đủ 4 thuộc tính

### 7.1. Tạo tệp SegmentFacts.java

Chương trình dưới đây thao tác với native segment 32 byte căn 8, tạo slice, đọc/ghi kiểu primitive, thử lỗi alignment và bounds, đối chiếu với heap segment rồi kiểm tra scope sau đóng arena.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentFacts {
    public static void main(String[] args) {
        MemorySegment segment;
        MemorySegment slice;

        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(32, 8);
            slice = segment.asSlice(8, 8);

            segment.set(ValueLayout.JAVA_LONG, 0, 0x0102030405060708L);
            slice.set(ValueLayout.JAVA_INT, 0, 123456);

            System.out.println("Native: " + segment.isNative());
            System.out.println("Size: " + segment.byteSize());
            System.out.println("Base aligned to 8: "
                    + (segment.address() % 8 == 0));
            System.out.println("Max alignment at least 8: "
                    + (segment.maxByteAlignment() >= 8));
            System.out.println("Scope alive: " + segment.scope().isAlive());
            System.out.println("Slice size: " + slice.byteSize());
            System.out.println("Slice address delta: "
                    + (slice.address() - segment.address()));

            System.out.println("Long at 0: "
                    + Long.toHexString(segment.get(ValueLayout.JAVA_LONG, 0)));
            System.out.println("Int at 8: "
                    + segment.get(ValueLayout.JAVA_INT, 8));

            try {
                segment.get(ValueLayout.JAVA_INT, 1);
            } catch (IllegalArgumentException expected) {
                System.out.println("Misaligned: blocked");
            }

            try {
                segment.get(ValueLayout.JAVA_LONG, 32);
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("Out of bounds: blocked");
            }

            MemorySegment heap = MemorySegment.ofArray(new byte[16]);
            System.out.println("Heap native: " + heap.isNative());
            System.out.println("Heap base address: " + heap.address());
            System.out.println("Heap max alignment: "
                    + heap.maxByteAlignment());

            try {
                heap.get(ValueLayout.JAVA_INT, 0);
            } catch (IllegalArgumentException expected) {
                System.out.println("Heap aligned int: blocked");
            }
            System.out.println("Heap unaligned int: "
                    + heap.get(ValueLayout.JAVA_INT_UNALIGNED, 0));
        }

        System.out.println("Scope alive after close: "
                + segment.scope().isAlive());
        try {
            segment.get(ValueLayout.JAVA_LONG, 0);
        } catch (IllegalStateException expected) {
            System.out.println("After close: blocked");
        }
    }
}
```

**Lệnh chạy** (JDK 22+, không cần JNI library hoặc C compiler):

```bash
javac SegmentFacts.java
java SegmentFacts
```

**Stdout đã xác minh trên JDK 24 (không in raw native address):**

```text
Native: true
Size: 32
Base aligned to 8: true
Max alignment at least 8: true
Scope alive: true
Slice size: 8
Slice address delta: 8
Long at 0: 102030405060708
Int at 8: 123456
Misaligned: blocked
Out of bounds: blocked
Heap native: false
Heap base address: 0
Heap max alignment: 1
Heap aligned int: blocked
Heap unaligned int: 0
Scope alive after close: false
After close: blocked
```

Đọc từng điểm:

1. `arena.allocate(32, 8)` tạo off-heap segment 32 byte, base chia hết cho 8; giá trị `maxByteAlignment` có thể >8 nên in điều kiện “at least”.
2. `segment.asSlice(8, 8)` có `byteSize = 8` và address cách base 8 byte.
3. `slice.set(JAVA_INT, 0, ...)` ghi tại offset 8 của parent, nên `segment.get(JAVA_INT, 8)` thấy `123456`.
4. `segment.get(JAVA_INT, 1)` bị chặn bởi alignment 4 byte, dù offset 1 vẫn còn nằm trong 32-byte view.
5. `segment.get(JAVA_LONG, 32)` vượt giới hạn 32 byte và ném `IndexOutOfBoundsException`.
6. Heap `byte[]` có address ảo hóa 0 và max alignment 1; `JAVA_INT` bị từ chối, `JAVA_INT_UNALIGNED` đọc 4 byte zero hợp lệ.
7. Cuối `try`, arena đóng; `scope().isAlive() == false` và lần đọc lại bị `IllegalStateException`.

Không dự đoán hoặc so sánh **địa chỉ native số cụ thể** trong test: đó là dữ liệu phụ thuộc môi trường. Với Java array `new byte[16]` ở ví dụ, heap base address 0 là đặc tả của `ofArray`.

## 8. Ví dụ độc lập: slice mất alignment và quyền truy cập theo thread

Tạo tệp **SegmentThreadFacts.java**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentThreadFacts {
    public static void main(String[] args) throws InterruptedException {
        try (Arena confined = Arena.ofConfined()) {
            MemorySegment seg = confined.allocate(16, 8);
            MemorySegment misaligned = seg.asSlice(1, 8);

            System.out.println("Slice max alignment: "
                    + misaligned.maxByteAlignment());

            try {
                misaligned.get(ValueLayout.JAVA_LONG, 0);
            } catch (IllegalArgumentException expected) {
                System.out.println("Slice aligned long: blocked");
            }

            Thread worker = new Thread(() -> {
                try {
                    seg.get(ValueLayout.JAVA_BYTE, 0);
                    System.out.println("Unexpected confinement success");
                } catch (WrongThreadException expected) {
                    System.out.println("Confined other thread: blocked");
                }
            });
            worker.start();
            worker.join();
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment seg = shared.allocate(8);
            Thread worker = new Thread(() -> {
                seg.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
                System.out.println("Shared other thread: "
                        + seg.get(ValueLayout.JAVA_BYTE, 0));
            });
            worker.start();
            worker.join();
        }
    }
}
```

**Chạy:**

```bash
javac SegmentThreadFacts.java
java SegmentThreadFacts
```

**Stdout đã xác minh trên JDK 24:**

```text
Slice max alignment: 1
Slice aligned long: blocked
Confined other thread: blocked
Shared other thread: 7
```

Giải thích hai khía cạnh khác nhau:

- `misaligned` bắt đầu ở base + 1, vì vậy max alignment là 1. Nó vẫn **nằm trong biên 16 byte của parent**, và scope còn sống, nhưng đọc `JAVA_LONG` ở offset 0 không thỏa alignment 8 byte.
- Với `Arena.ofConfined()`, thread mới không có quyền access segment của thread tạo arena; `WrongThreadException` được bắt. Với `Arena.ofShared()`, worker có thể đọc/ghi segment; ví dụ `join()` giúp luồng main đợi worker hoàn tất **trước khi arena đóng**.

`WrongThreadException` là lỗi confinement, không phải lỗi alignment hay out-of-bounds. Trong thực tế, `Arena.ofShared` không biến mọi thao tác memory thành thread-safe; nhiều worker cùng ghi một vùng cần quy tắc đồng bộ dữ liệu riêng.

## 9. Căn chỉnh struct C: vai trò của MemoryLayout

Khi làm việc với struct C, alignment của từng field và padding giữa fields rất quan trọng. Giả sử layout muốn có:

- Một `int` 4 byte ở offset 0.
- Padding 4 byte.
- Một `long` 8 byte ở offset 8.

Ta có thể mô tả **bố trí bộ nhớ cụ thể này** bằng `MemoryLayout` (đây là bố trí ví dụ có layout cố định; không khẳng định C `long` luôn dài 8 byte trên mọi ABI):

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructFacts {
    public static void main(String[] args) {
        MemoryLayout layout = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("code"),
                MemoryLayout.paddingLayout(4),
                ValueLayout.JAVA_LONG.withName("payload"));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment s = arena.allocate(layout);

            long codeOffset = layout.byteOffset(groupElement("code"));
            long payloadOffset = layout.byteOffset(groupElement("payload"));

            s.set(ValueLayout.JAVA_INT, codeOffset, 7);
            s.set(ValueLayout.JAVA_LONG, payloadOffset, 99L);

            System.out.println("Struct bytes: " + layout.byteSize());
            System.out.println("Struct alignment: " + layout.byteAlignment());
            System.out.println("Payload offset: " + payloadOffset);
            System.out.println("Allocated alignment OK: "
                    + (s.address() % layout.byteAlignment() == 0));
            System.out.println("Payload: "
                    + s.get(ValueLayout.JAVA_LONG, payloadOffset));
        }
    }
}
```

**Chạy:**

```bash
javac StructFacts.java
java StructFacts
```

**Stdout đã xác minh trên JDK 24:**

```text
Struct bytes: 16
Struct alignment: 8
Payload offset: 8
Allocated alignment OK: true
Payload: 99
```

Hai điểm quan trọng:

- `MemoryLayout.byteAlignment()` là **ràng buộc của layout**, còn `MemorySegment.maxByteAlignment()` là **khả năng alignment của segment**; `arena.allocate(layout)` tạo vùng nhớ đáp ứng layout đã cho.
- `MemoryLayout.structLayout` không tự suy ra mọi padding từ ABI C bất kỳ; trong ví dụ có `MemoryLayout.paddingLayout(4)` **chủ động**. Khi interoperating với C struct thực tế, phải khớp **ABI, field width, packing, endian, padding và alignment** của thư viện và hệ điều hành. Một C `long` không luôn có cùng kích thước với Java `long` trên mọi ABI.

## 10. Phân biệt các điều kiện thất bại khi access

Một lần `segment.get(layout, offset)` có thể thất bại do **nhiều nguyên nhân độc lập**. Hãy phân loại trước khi sửa:

| Điều kiện | Ví dụ | Lỗi thường gặp |
| --- | --- | --- |
| Vượt biên view | Segment 32 byte, đọc `JAVA_LONG` ở offset 32 | `IndexOutOfBoundsException` |
| Sai alignment | Base căn 8, đọc `JAVA_INT` ở offset 1 | `IllegalArgumentException` |
| Scope không còn sống | Đọc segment từ `Arena.ofConfined` sau khi arena đóng | `IllegalStateException` |
| Không đúng owner thread | Luồng khác đọc segment của `Arena.ofConfined` | `WrongThreadException` |
| Ghi vào view read-only | `segment.asReadOnly().set(...)` | `IllegalArgumentException` |
| Yêu cầu cấp phát sai | `arena.allocate(32, 3)` | `IllegalArgumentException` |
| Cố đóng arena đã đóng | `arena.close()` lần hai | `IllegalStateException` |
| Cố đóng arena không cho phép close | `Arena.ofAuto().close()`, `Arena.global().close()` | `UnsupportedOperationException` |

Nếu nhiều điều kiện cùng sai, **không dựa vào giả định thứ tự kiểm tra** để đoán loại exception đầu tiên; mỗi ví dụ kiểm thử nên cố ý tạo đúng một điều kiện lỗi nổi bật.

Một cách nghĩ hữu ích cho access an toàn:

```text
segment.get(layout, offset)
       |
       +-- Scope alive?          --- no --> IllegalStateException
       |
       +-- Thread được access?   --- no --> WrongThreadException
       |
       +-- Offset + size trong biên? -- no --> IndexOutOfBoundsException
       |
       +-- Địa chỉ đúng alignment? --- no --> IllegalArgumentException
       |
       +-- Đọc dữ liệu và diễn giải theo layout
```

Sơ đồ trên là **mô hình tư duy**, không khẳng định thứ tự kiểm tra nội bộ của mọi implementation JVM. Các thao tác `set` còn cần kiểm tra segment có read-only không.

## 11. Những bẫy thường gặp khi sử dụng MemorySegment với native code

### 11.1. Dùng địa chỉ raw thay cho segment

Không viết `long p = s.address()` rồi giả định `p` luôn hợp lệ sau khi arena đóng. FFM chỉ bảo vệ những lần truy cập được thực hiện **qua view còn hợp lệ**. Khi chuyển `p` qua JNI hoặc API C ngoài FFM, phần kiểm tra biên và scope không được tự động áp vào native pointer đó.

Nếu thư viện C cần giữ pointer sau khi hàm Java return, hãy bảo đảm arena và backing memory tiếp tục sống **đủ lâu**, có cơ chế sở hữu/close rõ ràng và không đóng trong khi native worker còn dùng. `Arena.ofConfined()` cũng không phù hợp nếu native worker khác cần tiếp cận segment qua Java API từ thread khác.

### 11.2. Nhầm scope với kích thước

Scope còn sống **không** cho phép truy cập vượt `byteSize`. Ngược lại, segment đủ dài **không** cho phép truy cập sau close. Hai thuộc tính này tách biệt. Slice thường có size nhỏ hơn parent nhưng **chung lifetime**.

### 11.3. Nhầm address alignment với mọi offset alignment

Ngay cả khi `segment.maxByteAlignment() >= 8`, access ở offset 1 với `JAVA_LONG` vẫn sai. Công thức địa chỉ mục tiêu của native segment là **base + offset**, và chính địa chỉ mục tiêu phải đáp ứng alignment layout. `maxByteAlignment` của segment tại base là thông tin cần nhưng chưa đủ cho mọi access offset.

### 11.4. Nhầm heap address bằng 0 với pointer null

`MemorySegment.ofArray(new byte[16]).address() == 0` là định nghĩa **offset ảo hóa**, không phải dấu hiệu mảng rỗng hay vùng nhớ đã free. Kiểm tra `isNative()` để biết kiểu backing segment; muốn tương tác C pointer không thể lấy `address()` của heap segment và coi đó là malloc address.

### 11.5. Dùng unaligned layout như phương pháp sửa ABI

`ValueLayout.JAVA_INT_UNALIGNED` cho phép đọc không căn chỉnh, nhưng nếu bố trí C struct thật có padding khác hoặc field width khác, nó không thể “sửa” cấu trúc dữ liệu. Hãy định nghĩa MemoryLayout đúng ABI trước khi lập trình offset; dùng unaligned layout khi dữ liệu thực sự là packed representation và bạn hiểu rủi ro portability.

### 11.6. Chọn Arena.global cho mọi allocation

Global arena có lifetime không giới hạn theo API, dễ khiến native memory không được giải phóng trong quá trình ứng dụng chạy. Dùng `Arena.ofConfined()` hoặc `Arena.ofShared()` cùng `try-with-resources` khi tài nguyên có điểm kết thúc; `Arena.ofAuto()` chỉ phù hợp khi chấp nhận GC quyết định thời điểm thu hồi.

### 11.7. Dùng ofAddress + reinterpret để bỏ qua an toàn

`MemorySegment.ofAddress(address)` tạo segment zero-length, giúp **không có quyền đọc** nếu không tăng biên bằng restricted API. `reinterpret` là thao tác mạnh nhưng unsafe; nếu nhận address không thuộc vùng hợp lệ hoặc khai báo size/scope sai, có thể đọc/ghi ngoài bộ nhớ của tiến trình, gây hỏng dữ liệu hoặc JVM crash. Không mở rộng biên chỉ vì gặp `IndexOutOfBoundsException`.

### 11.8. Đóng Arena trong lúc native callback còn dùng dữ liệu

Một downcall/native function có thể giữ pointer trong khi Java code cố close arena. Dù FFM cung cấp kiểm tra temporal safety cho các access được quản lý, code C bên ngoài hệ thống bảo vệ không tự có bounds/lifetime checks. **Không chuyển ownership chưa rõ ràng** sang C rồi đóng arena sớm. Đồng bộ các nhiệm vụ và xác nhận native call đã hoàn tất trước khi close.

## 12. Quy trình thiết kế và review một API dùng segment

Một API public hoặc wrapper JNI/FFM đáng tin cậy nên trả lời các câu hỏi:

1. **Bộ nhớ nằm ở đâu?** Native hay Java heap? Có thực sự cần off-heap? Có file mapping không?
2. **Ai cấp phát?** `Arena.allocate`, mảng Java, `MemorySegment.ofBuffer`, mapped file hay thư viện C khác?
3. **Địa chỉ có nghĩa gì?** Native address thật trong process hay offset heap? Có được phép đưa cho native function không?
4. **View dài bao nhiêu byte?** Có phải một slice không? Đọc/ghi theo offset byte hay logical index?
5. **Layout nào áp dụng?** Mỗi value rộng bao nhiêu, endian gì, alignment mấy byte, có padding không?
6. **Arena nào quản lý lifetime?** Confined, shared, auto hay global? Ai đóng và vào lúc nào?
7. **Thread nào truy cập?** Có đúng owner không? Nếu shared, dữ liệu có được đồng bộ giữa readers/writers không?
8. **Có giữ raw address ở nơi khác không?** Nếu có, cách ngăn sử dụng sau khi arena đóng là gì?
9. **Có test cả đường lỗi?** Bounds, misalignment, wrong thread, after close, read-only, constructor/allocator failures?
10. **Có đo native memory không?** Heap metrics không nhất thiết phản ánh tất cả pressure ngoài heap; dùng công cụ profiling/quan sát thích hợp.

### Bảng lựa chọn nhanh

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Đọc/ghi native buffer ngắn hạn trong một thread | `Arena.ofConfined()` + `try-with-resources` |
| Nhiều Java threads cần truy cập một vùng native | `Arena.ofShared()` + đồng bộ dữ liệu và lifecycle |
| Có thể chấp nhận GC quản lý thời gian thu hồi | `Arena.ofAuto()` (không có deadline) |
| Cần vùng sống không giới hạn một cách có chủ đích | `Arena.global()`, có cảnh báo resource lifetime |
| Chỉ cần view mảng Java primitive | `MemorySegment.ofArray(...)` |
| Cần layout cho một value primitive | `ValueLayout.JAVA_*` và các thao tác `get/set` |
| Cần biểu diễn struct và offset fields | `MemoryLayout.structLayout(...)`, tính offset bằng layout paths |
| Cần subrange giới hạn khả năng access | `segment.asSlice(offset, size)` |
| Dữ liệu đóng gói không căn chỉnh | Layout `*_UNALIGNED` có chủ ý, chú ý ABI và hiệu năng |

## 13. Bài tập tự kiểm tra

**Bài 1.** Một segment native có `address() = 1000` (giả định), `byteSize() = 16`, scope alive. Có thể đọc `JAVA_LONG` ở offset 8 và offset 12 không?

**Đáp án:** Offset 8 có địa chỉ 1008 chia hết cho 8, dữ liệu chiếm bytes 8…15 nên hợp lệ. Offset 12 chỉ còn bytes 12…15 (4 byte), không đủ 8 byte; còn địa chỉ 1012 cũng không căn 8. Ít nhất có lỗi biên và alignment; đừng giả định thứ tự exception nếu cả hai điều kiện cùng vi phạm.

**Bài 2.** `arena.allocate(32, 8)` bảo đảm `maxByteAlignment() == 8` chứ?

**Đáp án:** Không. Nó bảo đảm base **ít nhất căn 8**; actual address có thể phù hợp alignment lớn hơn, khiến `maxByteAlignment` >8. Kiểm tra `>= 8`.

**Bài 3.** Vì sao `MemorySegment.ofArray(new byte[16]).address() == 0` nhưng không phải native null pointer?

**Đáp án:** Đây là heap segment, `address()` biểu diễn **offset ảo hóa** trong array backing, không phải địa chỉ RAM có thể dereference bằng C. `isNative()` là false.

**Bài 4.** `MemorySegment part = s.asSlice(1, 8)` có tự mua thêm 8 byte và tồn tại độc lập sau `arena.close()` không?

**Đáp án:** Không. Nó cùng backing storage và scope với `s`, chỉ đổi base và view size. Offset 1 còn có thể làm giảm alignment tối đa xuống 1.

**Bài 5.** Sau `arena.close()`, `segment.byteSize()` vẫn có thể phản ánh độ dài ban đầu. Có nghĩa vùng nhớ native còn sống không?

**Đáp án:** Không. `byteSize` là metadata của view; khả năng access phụ thuộc `scope().isAlive()` và các kiểm tra khác. Đọc/ghi sau close bị từ chối.

**Bài 6.** Arena confined được tạo ở main thread và segment được truyền cho worker thread. Scope vẫn alive, vậy worker đọc `JAVA_BYTE` được không?

**Đáp án:** Không. Confinement yêu cầu thread owner. API có thể ném `WrongThreadException`. Đổi sang `Arena.ofShared()` nếu thực sự cần cross-thread, rồi bảo vệ dữ liệu/lifecycle cho đúng.

**Bài 7.** Vì sao có thể đọc `JAVA_INT_UNALIGNED` trên segment backed bởi `byte[]` mà `JAVA_INT` mặc định bị chặn?

**Đáp án:** `byte[]` hỗ trợ maximum alignment 1, `JAVA_INT` mặc định yêu cầu 4, còn `JAVA_INT_UNALIGNED` yêu cầu 1. Cả hai đều chiếm 4 byte, nhưng có ràng buộc alignment khác nhau.

**Bài 8.** `MemoryLayout.structLayout` có tự chèn mọi padding giống compiler C của OS không?

**Đáp án:** Không thể giả định. Phải mô tả padding/width/alignment theo ABI C thực tế. Ví dụ `paddingLayout(4)` được viết rõ để tạo offset 8 cho `payload`.

**Bài 9.** Segment có scope alive, offset hợp lệ và aligned; liệu một native function giữ raw pointer lại sau khi Java đóng arena có an toàn không?

**Đáp án:** Không. Các ràng buộc bảo vệ access qua segment không tự truyền sang raw pointer C. Cần quy tắc ownership và đảm bảo native consumer kết thúc trước khi backing memory được giải phóng.

**Bài 10.** Dùng `Arena.ofAuto()` có đảm bảo tài nguyên native được giải phóng khi Java method kết thúc không?

**Đáp án:** Không. Arena auto do GC quản lý, không có thời hạn; cần confined/shared arena và `try-with-resources` nếu muốn đóng theo scope cụ thể.

## 14. Tổng kết

- **`address()`** là địa chỉ/offset của segment, không tự biểu thị quyền sở hữu hoặc tính hợp lệ; native address khác heap virtualized address.
- **`byteSize()`** giới hạn số byte được phép đọc/ghi; slice thu hẹp view và không tạo backing memory mới.
- **`scope()`** đặt ranh giới thời gian; đóng arena làm segment cùng scope không truy cập được, kể cả khi object Java còn tồn tại.
- **`Arena.ofConfined`, `ofShared`, `ofAuto`, `global`** khác nhau ở quyền close và quyền sử dụng theo thread.
- **`maxByteAlignment()`** mô tả căn chỉnh segment hỗ trợ; **`MemoryLayout.byteAlignment()`** mô tả căn chỉnh một access cần. Offset cũng phải phù hợp.
- **`ValueLayout.JAVA_INT_UNALIGNED`** cho phép đọc packed bytes ở căn chỉnh 1 nhưng không thay thế thiết kế ABI đúng.
- Access an toàn cần đồng thời **đúng biên + scope còn sống + đúng thread + đúng alignment + quyền ghi thích hợp**.
- **Không cố vượt qua giới hạn** bằng raw pointer, `ofAddress` hoặc restricted `reinterpret` khi chưa xác minh kích thước và vòng đời native memory.

## Tài liệu tham khảo chính thức

- [Java SE 22 API — java.lang.foreign.MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 API — MemorySegment (address, byteSize, maxByteAlignment, scope, slicing)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 API — Arena (confined/shared/auto/global)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 24 API — ValueLayout và unaligned value layouts](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 24 API — MemoryLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [JEP 454 — Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)

**Ghi nhớ cốt lõi:** một `MemorySegment` là **view có biên không gian, biên thời gian và yêu cầu căn chỉnh**. Hãy bảo toàn cả bốn đặc điểm khi cắt slice, chuyển dữ liệu sang native code và quản lý vòng đời tài nguyên.
