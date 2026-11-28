# MemoryLayout, ValueLayout và căn chỉnh dữ liệu trong Java 27

Khi ứng dụng Java đọc một tệp nhị phân, trao đổi dữ liệu với thư viện C hoặc lưu cấu trúc trong bộ nhớ **ngoài Java heap** (*off-heap*), chỉ biết “cần 12 byte” chưa đủ. Ta còn phải biết **mỗi trường nằm ở byte nào, rộng bao nhiêu byte, được đọc theo byte order nào và địa chỉ có thỏa điều kiện căn chỉnh hay không**.

API **Foreign Function & Memory (FFM)** ổn định trong Java SE 27 cung cấp hai lớp trừu tượng nền tảng:

- `MemoryLayout`: **bản mô tả cấu trúc** bộ nhớ — kích thước, alignment, tên trường, các phần tử lồng nhau. Nó không tự chứa dữ liệu.
- `ValueLayout`: một loại `MemoryLayout` mô tả cách đọc/ghi **một giá trị cơ bản**, như `int`, `long`, `float`, `double`, `byte` hoặc địa chỉ.
- `MemorySegment`: **vùng bộ nhớ thực tế** được truy cập; có kích thước, ranh giới, vòng đời và chính sách truy cập theo thread.
- `Arena`: cơ chế **cấp phát và quản lý vòng đời** vùng native memory.

Đây là bài thuộc chương **Bộ nhớ ngoài heap và mã native** trong module **Java 27 và các kiến thức liên quan**. Các API `java.lang.foreign` được dùng là tính năng chuẩn hiện hành; những ví dụ truy cập bộ nhớ trong bài **không cần preview** và không yêu cầu gọi hàm native. Khi tích hợp thư viện C thực tế, vẫn phải kiểm tra **ABI** của hệ điều hành, kiến trúc CPU và compiler.

## 1. Phân biệt layout, segment và arena

Hãy hình dung một bản ghi có ba trường:

```text
┌─────────┬───────────────┬───────────┐
│ type    │ value         │ flags     │
│ 1 byte  │ 4 byte        │ 2 byte    │
└─────────┴───────────────┴───────────┘
```

Chỉ cộng 1 + 4 + 2 rồi kết luận bản ghi dài 7 byte có thể **không đúng**. Nếu `value` yêu cầu địa chỉ chia hết cho 4, nó không thể đặt trực tiếp tại offset 1 theo layout được căn chỉnh tự nhiên. Có thể cần **3 byte padding** trước `value` và padding ở cuối cấu trúc khi lưu thành mảng.

Ba vai trò:

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `MemoryLayout` | Byte nào thuộc trường nào, kích thước và alignment là bao nhiêu? | `structLayout(...)` |
| `ValueLayout` | Một giá trị được biểu diễn bằng bao nhiêu byte, kiểu Java nào, thứ tự byte nào? | `JAVA_INT.withOrder(BIG_ENDIAN)` |
| `MemorySegment` | Đọc/ghi trên vùng bộ nhớ thực tế nào và phạm vi hợp lệ là gì? | `segment.get(JAVA_INT, 4)` |
| `Arena` | Ai cấp phát và khi nào vùng native memory được giải phóng? | `try (Arena arena = Arena.ofConfined())` |

Một `MemoryLayout` có thể được **tái sử dụng** để mô tả nhiều segment hoặc nhiều phần tử cùng cấu trúc. Tạo layout không cấp phát bộ nhớ; cấp phát segment không tự xác định ý nghĩa các byte trong đó.

### 1.1. Phạm vi của FFM API

`java.lang.foreign` được chuẩn hóa từ Java 22 và tiếp tục có mặt trong Java 27. API này hướng tới truy cập dữ liệu và hàm bên ngoài Java runtime với các kiểm tra an toàn về **kích thước, vòng đời và ràng buộc thread**.

Không cần sử dụng `sun.misc.Unsafe`, phép cộng địa chỉ thủ công hoặc truy cập vùng nhớ không kiểm soát để học cách mô tả layout. Với giao tiếp native thực sự, phải phân biệt việc **mô tả bộ nhớ** (các ví dụ ở đây) với việc **gọi hàm C qua Linker**, vốn có các điều kiện truy cập native riêng.

## 2. Cấu trúc các loại MemoryLayout

`MemoryLayout` là sealed interface với các loại con chính:

| Loại layout | Dữ liệu được mô tả | Cách tạo |
| --- | --- | --- |
| `ValueLayout` | Một giá trị cơ bản | `ValueLayout.JAVA_INT`, `JAVA_SHORT`... |
| `AddressLayout` | Giá trị địa chỉ/con trỏ | `ValueLayout.ADDRESS` |
| `PaddingLayout` | Các byte không mang giá trị nghiệp vụ | `MemoryLayout.paddingLayout(3)` |
| `SequenceLayout` | N phần tử cùng layout | `MemoryLayout.sequenceLayout(10, element)` |
| `StructLayout` | Các thành viên được đặt **lần lượt** | `MemoryLayout.structLayout(a, b, ...)` |
| `UnionLayout` | Các thành viên dùng chung **offset bắt đầu** | `MemoryLayout.unionLayout(a, b, ...)` |

`StructLayout` và `UnionLayout` đều là các biến thể của `GroupLayout`.

Ví dụ:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;

MemoryLayout pair = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

System.out.println(pair.byteSize());      // 8
System.out.println(pair.byteAlignment()); // 4
```

Hai trường `int` có kích thước 4 byte, bắt đầu tại offset 0 và 4. Cấu trúc có tổng kích thước 8 byte và natural alignment 4 byte.

### 2.1. Layout là giá trị bất biến

Các layout là những đối tượng **immutable, thread-safe, value-based**. Khi viết:

```java
ValueLayout.OfInt bigEndian =
        ValueLayout.JAVA_INT.withOrder(java.nio.ByteOrder.BIG_ENDIAN);
```

Java tạo một layout với byte order mong muốn; nó **không thay đổi** hằng `JAVA_INT` dùng ở nơi khác.

Không dùng `==` để kiểm tra nội dung hai layout. Nếu cần so sánh mô tả, dùng `equals` theo hợp đồng API.

## 3. ValueLayout: kiểu Java mang giá trị, kích thước và byte order

Mỗi `ValueLayout` có ít nhất bốn thông tin:

1. `carrier()` — kiểu Java dùng để đọc/ghi, như `int.class` hoặc `long.class`.
2. `byteSize()` — số byte của một giá trị.
3. `byteAlignment()` — ràng buộc địa chỉ tính theo byte.
4. `order()` — thứ tự byte của giá trị đa byte.

Các hằng thường dùng:

| Layout | Carrier | Kích thước (byte) | Alignment chuẩn (byte) |
| --- | --- | ---: | ---: |
| `JAVA_BYTE` | `byte` | 1 | 1 |
| `JAVA_BOOLEAN` | `boolean` | 1 | 1 |
| `JAVA_SHORT` | `short` | 2 | 2 |
| `JAVA_CHAR` | `char` | 2 | 2 |
| `JAVA_INT` | `int` | 4 | 4 |
| `JAVA_FLOAT` | `float` | 4 | 4 |
| `JAVA_LONG` | `long` | 8 | 8 |
| `JAVA_DOUBLE` | `double` | 8 | 8 |
| `ADDRESS` | `MemorySegment` | Phụ thuộc độ rộng địa chỉ của nền tảng | Phụ thuộc nền tảng |

Với các layout Java dựng sẵn, byte order mặc định là `ByteOrder.nativeOrder()`. Đừng suy ra mọi máy đều là little-endian hoặc mọi định dạng tệp đều dùng native order.

```java
import java.lang.foreign.ValueLayout;

System.out.println(ValueLayout.JAVA_INT.carrier());       // int
System.out.println(ValueLayout.JAVA_INT.byteSize());      // 4
System.out.println(ValueLayout.JAVA_INT.byteAlignment()); // 4
```

### 3.1. Hằng _UNALIGNED để đọc dữ liệu packed

Với các kiểu nhiều byte còn có biến thể `JAVA_SHORT_UNALIGNED`, `JAVA_INT_UNALIGNED`, `JAVA_LONG_UNALIGNED`, `JAVA_FLOAT_UNALIGNED`, `JAVA_DOUBLE_UNALIGNED` và các biến thể tương ứng khác.

```java
System.out.println(ValueLayout.JAVA_INT_UNALIGNED.byteSize());      // 4
System.out.println(ValueLayout.JAVA_INT_UNALIGNED.byteAlignment()); // 1
```

Đây vẫn là số `int` **4 byte**, chỉ giảm ràng buộc căn chỉnh của địa chỉ xuống 1 byte. Unaligned **không có nghĩa** bộ dữ liệu tự được chuyển thành một kiểu “nén” khác, và cũng không thay đổi byte order.

## 4. Alignment là gì?

**Alignment** là yêu cầu địa chỉ bắt đầu của giá trị/cấu trúc phải chia hết cho một số byte nhất định. Nếu giá trị cần alignment 4, những địa chỉ 0, 4, 8, 12... (xét theo điểm bắt đầu vùng bộ nhớ được căn chỉnh) là phù hợp; offset 1, 2, 3 không phù hợp.

```text
Offset:     0   1   2   3   4   5   6   7
            ├───┬───┬───┬───┬───┬───┬───┤
int A       [======= 4 byte =======]
int B                       [======= 4 byte =======]
                                ↑
                      offset 4 chia hết cho 4
```

Ví dụ `JAVA_INT`:

```java
long size = ValueLayout.JAVA_INT.byteSize();         // 4
long align = ValueLayout.JAVA_INT.byteAlignment();  // 4
```

### 4.1. byteAlignment phải là lũy thừa của 2

Có thể thay đổi ràng buộc alignment bằng `withByteAlignment(long)`:

```java
ValueLayout.OfInt unaligned = ValueLayout.JAVA_INT.withByteAlignment(1);
ValueLayout.OfInt moreStrict = ValueLayout.JAVA_INT.withByteAlignment(8);
```

Các giá trị 1, 2, 4, 8, 16... là lũy thừa của 2 hợp lệ. Một giá trị như 3 bị từ chối bằng `IllegalArgumentException`.

Tăng alignment không làm `int` từ 4 byte thành 8 byte; đó chỉ là yêu cầu **địa chỉ căn chỉnh nghiêm ngặt hơn**. Nếu một định dạng yêu cầu 4 byte dữ liệu cộng 4 byte padding, phải mô tả 4 byte padding **riêng**, không sửa `byteAlignment` rồi cho rằng kích thước tự tăng.

### 4.2. Kiểm tra địa chỉ thực, không chỉ offset

Với native segment, địa chỉ truy cập hợp lệ phải tuân theo:

```text
(segment.address() + offset) % layout.byteAlignment() == 0
```

Với heap segment, không thể dựa vào địa chỉ vật lý như native memory; API có ràng buộc alignment lớn nhất theo kiểu vùng backing. `segment.maxByteAlignment()` cho biết alignment tối đa được hỗ trợ ở điểm bắt đầu của segment.

```java
if (segment.maxByteAlignment() < layout.byteAlignment()) {
    throw new IllegalArgumentException("Segment chưa được căn chỉnh đủ");
}
```

Đây là fragment trong ngữ cảnh có `segment` và `layout`. Nó kiểm tra alignment của **segment start**; khi truy cập trường ở offset khác, offset đó cũng phải tương thích alignment của value layout.

## 5. Padding là byte có vị trí nhưng không dùng làm giá trị

**Padding** giữ chỗ để trường phía sau nằm đúng vị trí yêu cầu hoặc để một cấu trúc có stride đúng khi lặp trong mảng.

Ví dụ minh họa cho cấu trúc có 1 byte `kind` và 4 byte `value`:

```text
byte offset    0        1   2   3        4   5   6   7
              ┌───────┬────────────┬────────────────────┐
              │ kind  │  padding   │       value        │
              │1 byte │  3 byte    │       4 byte       │
              └───────┴────────────┴────────────────────┘
```

Tạo bằng API:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;

MemoryLayout tagged = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);

System.out.println(tagged.byteSize());      // 8
System.out.println(tagged.byteAlignment()); // 4
```

**Đơn vị của `paddingLayout(3)` trong Java 27 là 3 byte.** Không nhầm với ba bit hoặc ba phần tử `int`.

Padding không phải một trường dữ liệu nghiệp vụ; không nên phụ thuộc vào nội dung bit của những byte padding để so sánh object, mã hóa dữ liệu hay tính checksum nếu protocol không có quy tắc rõ ràng.

### 5.1. structLayout không tự chèn padding

Lệnh sau **không hợp lệ**:

```java
// IllegalArgumentException: JAVA_INT bắt đầu ở offset 1.
// MemoryLayout bad = MemoryLayout.structLayout(
//         ValueLayout.JAVA_BYTE,
//         ValueLayout.JAVA_INT
// );
```

Vì `JAVA_INT` có alignment 4 nhưng theo phép ghép tuần tự nó bắt đầu ở offset 1, factory từ chối cấu trúc.

Cách đúng khi cần layout căn chỉnh:

```java
MemoryLayout aligned = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);
```

Cách đúng khác, **nếu định dạng thực sự packed**, là sử dụng layout unaligned:

```java
MemoryLayout packed = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        ValueLayout.JAVA_INT_UNALIGNED.withName("value")
);

System.out.println(packed.byteSize());      // 5
System.out.println(packed.byteAlignment()); // 1
```

Đừng chọn bản packed chỉ để né ngoại lệ nếu đang mô tả một C struct căn chỉnh theo ABI. Layout phải **khớp dữ liệu thật**, không phải chỉ “chạy được”.

## 6. StructLayout: các field có offset cộng dồn

`MemoryLayout.structLayout(...)` đặt các member **liền nhau theo đúng thứ tự** đã khai báo; tổng kích thước bằng tổng `byteSize()` của các member.

Một layout bản ghi 12 byte:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("type"), // offset 0
        MemoryLayout.paddingLayout(3),          // offsets 1..3
        ValueLayout.JAVA_INT.withName("length"),// offsets 4..7
        ValueLayout.JAVA_SHORT.withName("flags"), // offsets 8..9
        MemoryLayout.paddingLayout(2)           // offsets 10..11
);

System.out.println(header.byteSize());      // 12
System.out.println(header.byteAlignment()); // 4
```

Biểu diễn:

```text
Offset:   0     1 2 3      4 5 6 7         8 9       10 11
        ┌──────┬─────────┬───────────────┬─────────┬─────────┐
        │ type │ padding │ length: int   │ flags   │ padding │
        │ 1B   │ 3B      │ 4B            │ short 2B│ 2B      │
        └──────┴─────────┴───────────────┴─────────┴─────────┘
                           size = 12B; alignment = 4B
```

**Tail padding** ở cuối giúp kích thước 12 chia hết cho alignment 4, để các phần tử liên tiếp trong mảng có cùng căn chỉnh. Với một kiểu khác, hãy tính padding từ dữ liệu/ABI thật, không mặc định “mọi struct đều bội số 8”.

### 6.1. Offset từng trường được tính từ layout

Không nên rải các con số 4, 8 trong mã nếu đã có layout:

```java
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

long typeOffset = header.byteOffset(groupElement("type"));
long lengthOffset = header.byteOffset(groupElement("length"));
long flagsOffset = header.byteOffset(groupElement("flags"));

System.out.println(typeOffset);   // 0
System.out.println(lengthOffset); // 4
System.out.println(flagsOffset);  // 8
```

Khi sửa mô tả layout, cách tra offset từ `groupElement(...)` giúp giảm nguy cơ dùng hằng số cũ.

`groupElement("length")` chọn member theo **tên layout**, không phải tên biến Java. Nếu chưa gọi `withName("length")` cho field, không có tên này để tra.

### 6.2. Tạo dữ liệu bằng Arena.allocate(layout)

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment memory = arena.allocate(header);
    System.out.println(memory.byteSize()); // 12
}
```

`arena.allocate(header)` dùng thông tin kích thước và alignment của layout để yêu cầu một vùng native memory phù hợp. **Layout vẫn chỉ là bản mô tả**, còn `memory` là vùng ghi/đọc thực tế. `Arena.ofConfined()` cung cấp vòng đời đóng rõ ràng cho segment.

## 7. ValueLayout.withOrder: byte order độc lập với alignment

Với giá trị gồm nhiều byte, có hai byte order thường gặp:

- `ByteOrder.BIG_ENDIAN`: byte có trọng số cao ở trước.
- `ByteOrder.LITTLE_ENDIAN`: byte có trọng số thấp ở trước.

Ví dụ số hex `0x01020304` chiếm 4 byte:

```text
BIG_ENDIAN:       01 02 03 04
LITTLE_ENDIAN:    04 03 02 01
```

Tạo layout cụ thể:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt networkInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

ValueLayout.OfInt littleInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
```

`withOrder(...)` không thay kích thước 4 byte hay alignment 4 byte. Nó thay cách giải thích thứ tự byte khi đọc/ghi.

### 7.1. Không dựa vào nativeOrder cho định dạng wire

Nếu một tệp hoặc protocol quy định big-endian, hãy viết tường minh:

```java
ValueLayout.OfInt lengthField =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
```

Dùng `JAVA_INT` mặc định có thể tạo dữ liệu khác nhau khi chạy trên máy có native byte order khác. Ngược lại, khi mô tả vùng nhớ do một ABI native xác định, `ByteOrder.nativeOrder()` thường có ý nghĩa, nhưng vẫn phải xác minh layout của kiểu C và padding.

### 7.2. Signed và unsigned

`JAVA_INT` dùng carrier `int` của Java, nên giá trị nhận về là **signed 32-bit**. Một trường C `uint32_t` cũng có 32 bit nhưng được hiểu như unsigned.

```java
int raw = 0xFFFFFFFF;
long unsigned = Integer.toUnsignedLong(raw);

System.out.println(unsigned); // 4294967295
```

Không thay đổi `byteSize()` hoặc `byteOrder()` chỉ vì muốn đọc unsigned; hãy diễn giải **bit pattern** theo đúng miền giá trị. Với `uint16_t`, có thể dùng `Short.toUnsignedInt(shortValue)`.

## 8. Truy cập trực tiếp qua MemorySegment.get/set

Đối với giá trị đơn, không nhất thiết phải tạo `VarHandle`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt bigEndian =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8, 4);

    segment.set(bigEndian, 0L, 0x01020304);
    segment.set(ValueLayout.JAVA_INT, 4L, 27);

    System.out.println(segment.get(bigEndian, 0L)); // 16909060
    System.out.println(segment.get(ValueLayout.JAVA_INT, 4L)); // 27

    System.out.printf("%02X %02X%n",
            Byte.toUnsignedInt(segment.get(ValueLayout.JAVA_BYTE, 0)),
            Byte.toUnsignedInt(segment.get(ValueLayout.JAVA_BYTE, 1)));
    // 01 02
}
```

Cấp phát 8 byte với alignment 4 đáp ứng hai thao tác `int` tại offset 0 và 4.

**Đừng đọc padding chưa khởi tạo rồi cho rằng nội dung là zero.** Hãy khởi tạo vùng dữ liệu hoặc các trường cần thiết theo contract, nhất là khi xuất bytes ra ngoài hệ thống.

### 8.1. Đọc packed int tại offset lẻ

```java
import java.lang.foreign.Arena;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

var packedInt = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);

try (Arena arena = Arena.ofConfined()) {
    var segment = arena.allocate(5, 1);

    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
    segment.set(packedInt, 1, 0x11223344);

    System.out.println(segment.get(packedInt, 1)); // 287454020
}
```

Ở offset 1, `JAVA_INT` alignment 4 không phù hợp, nhưng `JAVA_INT_UNALIGNED` alignment 1 được phép đọc/ghi thông thường.

**Không suy luận** mọi thao tác atomic hoặc volatile đều hoạt động trên layout unaligned; khả năng hỗ trợ các access mode của `VarHandle` còn phụ thuộc alignment.

## 9. VarHandle: truy cập trường theo một layout path

Khi có nhiều trường trong một struct, có thể tạo `VarHandle` từ layout path thay vì tính offset bằng tay:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

MemoryLayout record = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_LONG.withName("timestamp")
);
```

**Đoạn trên chưa đúng nếu tạo trực tiếp:** `JAVA_LONG` có alignment 8, nhưng nằm ở offset 4. Cần sửa bằng padding:

```java
MemoryLayout record = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        MemoryLayout.paddingLayout(4),
        ValueLayout.JAVA_LONG.withName("timestamp")
);

VarHandle idHandle = record.varHandle(groupElement("id"));
VarHandle tsHandle = record.varHandle(groupElement("timestamp"));
```

Hai handle dùng loại tọa độ cơ bản:

```text
VarHandle.get(MemorySegment segment, long baseOffset)
VarHandle.set(MemorySegment segment, long baseOffset, <giá trị đúng carrier>)
```

Ví dụ truy cập:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(record);

    idHandle.set(data, 0L, 42);
    tsHandle.set(data, 0L, 123456789L);

    int id = (int) idHandle.get(data, 0L);
    long timestamp = (long) tsHandle.get(data, 0L);

    System.out.println(id + ", " + timestamp); // 42, 123456789
}
```

`baseOffset` là vị trí bắt đầu của một instance layout trong segment. Handle tự cộng offset của trường `id` hoặc `timestamp`.

### 9.1. Vì sao dùng VarHandle thay vì chỉ get/set?

- Mô tả cấu trúc dữ liệu **ở một chỗ**.
- Dùng tên trường thay vì số offset lặp lại.
- Có thể dùng các **layout paths** đi qua struct, union, sequence.
- Có thể dùng một handle với nhiều bản ghi tương tự trong cùng segment.
- Với layout căn chỉnh đủ, một số VarHandle access modes mạnh hơn `get/set` có thể khả dụng, tùy ràng buộc API và nền tảng.

Không nên tự động dùng `compareAndSet` trên mọi layout; **unaligned VarHandle** chỉ hỗ trợ các access modes phù hợp và có thể không hỗ trợ thao tác atomic.

## 10. SequenceLayout: mảng các phần tử cùng layout

Khi có N phần tử giống nhau, dùng `MemoryLayout.sequenceLayout(N, elementLayout)`.

Ví dụ mảng ba điểm 2D:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

SequenceLayout points = MemoryLayout.sequenceLayout(3, point);

System.out.println(point.byteSize());     // 8
System.out.println(points.elementCount()); // 3
System.out.println(points.byteSize());   // 24
System.out.println(points.byteAlignment()); // 4
```

Mỗi điểm chiếm 8 byte, nên các điểm bắt đầu ở offset 0, 8, 16.

### 10.1. Layout paths với sequenceElement cố định

`PathElement.sequenceElement(i)` chọn phần tử cụ thể trong mảng:

```java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long secondY = points.byteOffset(
        sequenceElement(1),
        groupElement("y")
);

System.out.println(secondY); // 12
```

Vì phần tử thứ hai (index 1) bắt đầu tại offset 8, còn trường `y` ở offset 4 trong một `point`, tổng offset là 12.

### 10.2. Open sequenceElement và tọa độ động của VarHandle

Có thể tạo một handle dùng chung cho mọi điểm:

```java
VarHandle xHandle = points.varHandle(
        sequenceElement(),
        groupElement("x")
);

VarHandle yHandle = points.varHandle(
        sequenceElement(),
        groupElement("y")
);
```

Một **open path element** thêm một tọa độ `long` động cho chỉ số phần tử. Vì vậy:

```text
xHandle.get(segment, baseOffset, elementIndex)
xHandle.set(segment, baseOffset, elementIndex, intValue)
```

Ví dụ thực hiện đầy đủ:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(points);

    xHandle.set(data, 0L, 0L, 10);
    yHandle.set(data, 0L, 0L, 20);

    xHandle.set(data, 0L, 1L, 30);
    yHandle.set(data, 0L, 1L, 40);

    System.out.println((int) yHandle.get(data, 0L, 1L)); // 40
}
```

Chỉ số `1L` ở đây chọn **điểm thứ hai**, không phải byte offset 1. Layout đã biết stride 8 byte nên handle tính đúng địa chỉ.

`byteOffset(...)` chỉ có thể trả một offset cố định khi path **không chứa open path element**. Nếu cần địa chỉ phụ thuộc index, dùng `VarHandle` hoặc `byteOffsetHandle(...)` phù hợp.

### 10.3. Stride phải tương thích alignment

Với `sequenceLayout(N, elementLayout)`, kích thước một phần tử (stride) phải chia hết cho alignment của chính element layout. Nếu không, các phần tử kế tiếp có thể không được căn chỉnh.

Ví dụ `structLayout(JAVA_INT, JAVA_BYTE)` có size 5 và alignment 4: có thể mô tả một struct duy nhất, nhưng không thể dùng trực tiếp làm một sequence của nhiều struct có stride 5 và yêu cầu căn chỉnh 4. Cần **tail padding** để size thành bội số 4:

```java
StructLayout element = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3)
);

SequenceLayout many = MemoryLayout.sequenceLayout(10, element);

System.out.println(element.byteSize()); // 8
System.out.println(many.byteSize());    // 80
```

Nếu định dạng **packed** thật sự quy định stride 5, cần giảm alignment của các member và/hoặc layout một cách có chủ đích, đồng thời xác minh khả năng đọc/ghi hợp lệ và tính tương thích với nguồn dữ liệu.

## 11. UnionLayout: nhiều cách hiểu trên cùng một vùng byte

`MemoryLayout.unionLayout(...)` đặt mọi member tại **offset 0** của group. Kích thước union là kích thước **lớn nhất** trong các member.

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.UnionLayout;
import java.lang.foreign.ValueLayout;

UnionLayout raw32 = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("integerValue"),
        ValueLayout.JAVA_FLOAT.withName("floatValue")
);

System.out.println(raw32.byteSize());      // 4
System.out.println(raw32.byteAlignment()); // 4
```

Hai field có cùng offset:

```java
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

System.out.println(raw32.byteOffset(groupElement("integerValue"))); // 0
System.out.println(raw32.byteOffset(groupElement("floatValue")));   // 0
```

Điều này không có nghĩa có hai giá trị độc lập nằm ở hai địa chỉ khác nhau. Viết vào member này sẽ thay **cùng các byte** mà member kia đọc.

### 11.1. Union trong dữ liệu native có thể cần tag

Nếu C API dùng union gồm nhiều biến thể, thông thường sẽ có một trường `tag` cho biết biến thể hiện tại. Hãy kiểm tra tag trước khi đọc các byte union bằng layout của biến thể tương ứng.

Cẩn thận với alignment, kích thước, padding của union; cách biểu diễn cụ thể phụ thuộc ABI và kiểu C thực tế. Không suy ra một C union tùy ý chỉ từ tên `UnionLayout` mà không xác minh header/ABI.

## 12. Padding giữa trường và padding cuối struct là hai mục đích khác nhau

Xét một C struct phổ biến:

```c
struct Message {
    unsigned char type;
    unsigned int length;
    unsigned short flags;
};
```

Trên **một ABI cụ thể** nơi `unsigned int` là 4 byte/alignment 4 và `unsigned short` là 2 byte/alignment 2, bố cục thường là:

```text
type   : offset 0, size 1
padding: offset 1, size 3
length : offset 4, size 4
flags  : offset 8, size 2
padding: offset 10, size 2  ← tail padding
total  : size 12, alignment 4
```

Phân biệt:

- **Internal padding:** đảm bảo member kế tiếp đặt đúng địa chỉ (ba byte trước `length`).
- **Tail padding:** đảm bảo khi mảng chứa nhiều `Message`, phần tử thứ hai bắt đầu tại offset phù hợp (hai byte sau `flags`).

Trong Java:

```java
StructLayout message = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("type"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("length"),
        ValueLayout.JAVA_SHORT.withName("flags"),
        MemoryLayout.paddingLayout(2)
);
```

Đây là bố cục **minh họa đã xác định rõ giả thiết**, không phải cam kết mọi compiler C, ABI hoặc tùy chọn `#pragma pack` đều tạo cùng layout.

Không tự động thêm tail padding vào mọi struct khi không cần. Khi truyền data qua FFM cho hàm C, mô tả phải **khớp tuyệt đối** với layout mà thư viện native thực sự mong đợi.

## 13. Heap segment và native segment: khác nhau về alignment

`MemorySegment` có thể được hỗ trợ bởi **Java heap** hoặc bộ nhớ **native**.

Tạo heap segment:

```java
import java.lang.foreign.MemorySegment;

MemorySegment heapBytes = MemorySegment.ofArray(new byte[16]);
```

Một vùng backing `byte[]` có giới hạn alignment tối đa tương ứng 1 byte theo quy tắc FFM. Vì vậy, với mặc định `JAVA_INT` alignment 4, lời gọi sau **không hợp lệ** ngay cả ở offset 0:

```java
// Có thể gây IllegalArgumentException về alignment.
// int value = heapBytes.get(ValueLayout.JAVA_INT, 0);
```

Dùng bản unaligned:

```java
heapBytes.set(ValueLayout.JAVA_INT_UNALIGNED, 0, 27);
System.out.println(heapBytes.get(ValueLayout.JAVA_INT_UNALIGNED, 0)); // 27
```

Hoặc dùng một heap segment từ backing array có alignment tối đa lớn hơn:

```java
MemorySegment heapLongs = MemorySegment.ofArray(new long[2]);
heapLongs.set(ValueLayout.JAVA_INT, 0, 27);
```

**Lưu ý:** `maxByteAlignment()` cho biết ràng buộc lớn nhất của segment; nó không đảm bảo một layout có kích thước phù hợp nếu segment quá nhỏ. Luôn kiểm tra cả size và alignment.

### 13.1. Native segment cần cấp phát có alignment

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeMemory = arena.allocate(16, 8);

    System.out.println(nativeMemory.byteSize()); // 16
    System.out.println(nativeMemory.maxByteAlignment() >= 8); // true

    nativeMemory.set(ValueLayout.JAVA_LONG, 0, 100L);
}
```

`arena.allocate(16, 8)` yêu cầu một vùng native memory dài 16 byte, bắt đầu tại địa chỉ phù hợp alignment 8. Với `arena.allocate(layout)`, allocator có thể lấy alignment trực tiếp từ layout.

## 14. Vòng đời Arena: tránh truy cập sau khi giải phóng

Có bốn loại arena thường gặp:

| Arena | Thời gian sống | Đóng tường minh? | Truy cập đa thread? |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Bounded | Có | Chỉ thread sở hữu |
| `Arena.ofShared()` | Bounded | Có | Các thread phù hợp |
| `Arena.ofAuto()` | Do GC quản lý | Không | Có |
| `Arena.global()` | Không có điểm đóng thông thường | Không | Có |

Ví dụ đúng:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 27);

    System.out.println(segment.get(ValueLayout.JAVA_INT, 0)); // 27
} // Đóng arena, invalidates những native segments thuộc scope này.
```

Truy cập một segment đã bị invalidated do đóng arena sẽ bị từ chối (thường `IllegalStateException`), thay vì cho phép đọc vùng nhớ đã giải phóng.

### 14.1. Không đưa confined segment sang thread khác

Một segment cấp phát từ `Arena.ofConfined()` chỉ được phép truy cập bởi thread tạo arena. Dùng segment đó từ một virtual thread khác hoặc platform thread khác **không tự hợp lệ**:

```java
// Pseudocode: segment tạo từ Arena.ofConfined() ở thread A.
// Thread.ofVirtual().start(() -> segment.get(JAVA_INT, 0));
// Có thể ném WrongThreadException.
```

Nếu cần chia sẻ, cân nhắc `Arena.ofShared()` và thiết kế **đồng bộ hóa các thao tác ghi/đọc**. Shared arena cho phép nhiều thread truy cập hợp lệ, nhưng **không tự biến mọi cập nhật thành atomic** và không ngăn data race.

### 14.2. Không dùng Arena.global cho bộ nhớ cần giải phóng sớm

`Arena.global()` cho native memory có vòng đời không được thu hồi bởi một lời gọi `close()` bình thường. Dùng nó một cách không kiểm soát có thể khiến dữ liệu tồn tại tới cuối tiến trình.

Đối với công việc có phạm vi xác định, ưu tiên `try-with-resources` với confined/shared arena, và đảm bảo native library **không giữ con trỏ** vượt quá lifetime của segment được cấp phát.

## 15. Các kiểm tra an toàn khi truy cập MemorySegment

FFM thực hiện kiểm tra về:

1. **Spatial bounds:** offset và kích thước truy cập phải nằm trong segment.
2. **Temporal bounds:** scope của segment còn sống.
3. **Thread confinement:** thread truy cập được phép theo arena/scope.
4. **Read-only state:** không ghi qua segment chỉ đọc.
5. **Alignment:** địa chỉ truy cập đáp ứng layout.

Các lỗi điển hình:

| Vấn đề | Kết quả thường gặp |
| --- | --- |
| Đọc ở ngoài giới hạn segment | `IndexOutOfBoundsException` |
| Đọc sau khi arena đã đóng | `IllegalStateException` |
| Dùng confined segment từ thread khác | `WrongThreadException` |
| Ghi qua read-only segment | `IllegalArgumentException` theo contract của access operation |
| Không đáp ứng byteAlignment | `IllegalArgumentException` |
| Tạo struct có member nằm ở offset không căn chỉnh | `IllegalArgumentException` ngay khi tạo layout |
| Truy cập `VarHandle` bằng sai loại/số tọa độ | `WrongMethodTypeException` hoặc lỗi kiểu tương ứng |
| Dùng atomic access mode trên unaligned var handle | `UnsupportedOperationException` nếu mode không được hỗ trợ |

Kiểm tra của Java bảo vệ phạm vi **segment mà runtime biết**. Nó không xác minh rằng mọi pointer do mã native đưa vào thực sự trỏ tới dữ liệu còn sống hoặc có kích thước như ứng dụng tuyên bố. Khi liên kết với C, phải đặc biệt nghiêm ngặt với **quyền sở hữu native memory** và độ dài vùng được truyền.

## 16. Căn chỉnh và khả năng truy cập nguyên tử bằng VarHandle

`VarHandle` hỗ trợ các access mode với mức bảo đảm bộ nhớ khác nhau, nhưng không phải **mọi var handle từ layout** đều hỗ trợ tất cả access mode.

Ví dụ:

```java
import java.lang.invoke.VarHandle;

VarHandle alignedInt = ValueLayout.JAVA_INT.varHandle();
VarHandle unalignedInt = ValueLayout.JAVA_INT_UNALIGNED.varHandle();
```

Các access mode thông thường `get` và `set` có thể dùng với cả hai theo các điều kiện về phạm vi, alignment, read-only và lifetime của segment. Tuy nhiên:

- Với layout unaligned, `VarHandle` chỉ bảo đảm các access mode thông thường `get`/`set`; các mode khác như CAS/volatile có thể không được hỗ trợ.
- Với layout được căn chỉnh đầy đủ, các mode mạnh hơn có thể được hỗ trợ theo contract.
- Chỉ chọn memory ordering và atomic semantics khi mô hình đồng thời thật sự cần; không dùng `getVolatile`, `compareAndSet` chỉ vì chúng “mạnh hơn”.

**Rủi ro word tearing:** truy cập nhiều byte không được căn chỉnh có thể không atomic; một thread khác có thể nhìn thấy phần dữ liệu cập nhật không đồng nhất nếu bạn cho phép truy cập đồng thời thiếu đồng bộ.

Thực tế tốt: xem xét kích thước/alignment từ ABI, chọn layout phù hợp, và xác định quyền truy cập giữa các thread trước khi gọi access mode nâng cao.

## 17. Tính offset cho cấu trúc lồng nhau

Giả sử một bản ghi gồm `header` và một mảng điểm:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.ValueLayout;

StructLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_INT.withName("version")
).withName("header");

StructLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
).withName("point");

SequenceLayout points = MemoryLayout.sequenceLayout(3, point)
        .withName("points");

StructLayout packet = MemoryLayout.structLayout(
        header,
        points
);

System.out.println(packet.byteSize()); // 8 + 3 * 8 = 32
```

Muốn lấy offset `y` của điểm thứ ba (index 2):

```java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long offset = packet.byteOffset(
        groupElement("points"),
        sequenceElement(2),
        groupElement("y")
);

System.out.println(offset); // 8 + 16 + 4 = 28
```

Đây là cách để **layout tính offset thay bạn**; không phải dùng `sizeof` tự viết rồi cộng tay trong mọi nơi của dự án.

### 17.1. Truy cập mảng lồng nhau bằng VarHandle

```java
VarHandle y = packet.varHandle(
        groupElement("points"),
        sequenceElement(),
        groupElement("y")
);
```

Handle có tọa độ:

```text
(MemorySegment segment, long baseOffset, long pointIndex)
```

Trong một đoạn mã có Arena phù hợp:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(packet);
    y.set(data, 0L, 2L, 99);
    System.out.println((int) y.get(data, 0L, 2L)); // 99
}
```

Tham số `2L` chọn phần tử thứ ba; byte offset thật được tính từ layout path.

## 18. Tương thích C ABI: không đồng nhất JAVA_LONG với C long

Các hằng `ValueLayout.JAVA_INT` và `ValueLayout.JAVA_LONG` mô tả **kích thước kiểu Java**. Chúng không tự xác nhận rằng `C int`/`C long` có cùng kích thước và alignment trên mọi hệ điều hành.

Ví dụ **C long**:

- Trên một số ABI 64-bit dạng LP64, `long` thường là 8 byte.
- Trên ABI Windows/x64 dạng LLP64, `long` thường là 4 byte dù con trỏ là 8 byte.

Khi tích hợp với hàm native, Java FFM cung cấp:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

MemoryLayout cLong =
        Linker.nativeLinker().canonicalLayouts().get("long");
```

`Linker.canonicalLayouts()` là bảng mapping theo **ABI của native linker hiện hành**. Nó hữu ích để chọn đúng layout cho các kiểu scalar C, đặc biệt `long`, `size_t`, `wchar_t` và pointer.

**Lưu ý:** Mô tả struct/union còn phụ thuộc lựa chọn packing, bit-field rules, alignment override, compiler ABI và cách định nghĩa trong native header. Không suy đoán chúng chỉ từ một bản Java record. Với struct phức tạp, xác minh `sizeof` và `offsetof` ở phía C hoặc dùng công cụ sinh binding/layout thích hợp đã được kiểm chứng.

### 18.1. Địa chỉ và AddressLayout

`ValueLayout.ADDRESS` mô tả một giá trị địa chỉ/con trỏ, có kích thước phụ thuộc nền tảng. Carrier khi đọc bằng layout này là `MemorySegment`, không phải `int` hoặc `long` thuần.

Không biến số nguyên bất kỳ thành con trỏ rồi đọc dữ liệu với kích thước tự đoán. Những con trỏ do mã native trả về có thể gắn với vòng đời riêng của thư viện, và FFM không thể tự xác minh toàn bộ vùng dữ liệu phía native.

## 19. Ví dụ Java 27 hoàn chỉnh: layout bản ghi 12 byte

Ví dụ sau có thể biên dịch bằng JDK 27, dùng API chuẩn và không gọi C. Ta thiết kế một header gồm ba trường:

- `type` — 1 byte.
- `value` — 4 byte, **big-endian**.
- `flags` — 2 byte, **big-endian**.
- Padding bảo đảm offset và stride phù hợp layout có alignment 4.

Tạo file `MemoryLayoutDemo.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class MemoryLayoutDemo {

    private static final StructLayout HEADER = MemoryLayout.structLayout(
            ValueLayout.JAVA_BYTE.withName("type"),
            MemoryLayout.paddingLayout(3),
            ValueLayout.JAVA_INT
                    .withOrder(ByteOrder.BIG_ENDIAN)
                    .withName("value"),
            ValueLayout.JAVA_SHORT
                    .withOrder(ByteOrder.BIG_ENDIAN)
                    .withName("flags"),
            MemoryLayout.paddingLayout(2)
    );

    private static final VarHandle TYPE =
            HEADER.varHandle(groupElement("type"));

    private static final VarHandle VALUE =
            HEADER.varHandle(groupElement("value"));

    private static final VarHandle FLAGS =
            HEADER.varHandle(groupElement("flags"));

    public static void main(String[] args) {
        System.out.println("Size: " + HEADER.byteSize());
        System.out.println("Alignment: " + HEADER.byteAlignment());

        System.out.println("Offsets: "
                + HEADER.byteOffset(groupElement("type")) + ", "
                + HEADER.byteOffset(groupElement("value")) + ", "
                + HEADER.byteOffset(groupElement("flags")));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(HEADER);

            // Tọa độ 0L là base offset của toàn bộ struct.
            TYPE.set(data, 0L, (byte) 7);
            VALUE.set(data, 0L, 0x01020304);
            FLAGS.set(data, 0L, (short) 42);

            byte type = (byte) TYPE.get(data, 0L);
            int value = (int) VALUE.get(data, 0L);
            short flags = (short) FLAGS.get(data, 0L);

            System.out.println("type: " + type);
            System.out.println("value: " + value);
            System.out.println("flags: " + flags);

            System.out.printf("value bytes: %02X %02X %02X %02X%n",
                    Byte.toUnsignedInt(data.get(ValueLayout.JAVA_BYTE, 4)),
                    Byte.toUnsignedInt(data.get(ValueLayout.JAVA_BYTE, 5)),
                    Byte.toUnsignedInt(data.get(ValueLayout.JAVA_BYTE, 6)),
                    Byte.toUnsignedInt(data.get(ValueLayout.JAVA_BYTE, 7)));
        }
    }
}
```

Chạy với JDK 27:

```bash
javac -encoding UTF-8 MemoryLayoutDemo.java
java MemoryLayoutDemo
```

Kết quả xác định:

```text
Size: 12
Alignment: 4
Offsets: 0, 4, 8
type: 7
value: 16909060
flags: 42
value bytes: 01 02 03 04
```

Giải thích:

1. `structLayout` ghép các member theo thứ tự; padding được khai báo **tường minh**, không tự sinh.
2. Alignment của toàn struct là 4 vì thành viên có yêu cầu lớn nhất là `JAVA_INT` alignment 4.
3. Offset của `type`, `value`, `flags` lần lượt là 0, 4, 8.
4. `arena.allocate(HEADER)` cấp phát segment native có size/alignment theo layout.
5. Các `VarHandle` truy cập trường qua `groupElement("...")` và base offset 0.
6. `withOrder(BIG_ENDIAN)` bảo đảm bytes của `0x01020304` tại các offset 4..7 là `01 02 03 04` dù native byte order của máy chủ khác.
7. Khi ra khỏi `try-with-resources`, Arena đóng và vùng native memory không còn được truy cập hợp lệ.
8. Padding không được đọc, không được so sánh hay đưa vào checksum; chỉ các field đã định nghĩa được sử dụng.

## 20. Lỗi thường gặp với layout và alignment

| Sai lầm | Hệ quả | Cách phù hợp |
| --- | --- | --- |
| Nghĩ `MemoryLayout` chứa dữ liệu | Không có vùng nhớ để đọc/ghi | Cấp phát/lấy `MemorySegment` riêng |
| Gọi `structLayout(JAVA_BYTE, JAVA_INT)` | Field `int` bắt đầu ở offset 1 không align 4 | Thêm `paddingLayout(3)` hoặc dùng layout unaligned nếu định dạng packed |
| Nghĩ `structLayout` tự thêm padding | Size/offset sai hoặc factory ném exception | Mô tả padding tường minh theo ABI |
| Cho rằng `byteAlignment(8)` đồng nghĩa 8 byte dữ liệu | Nhầm size với alignment | Kiểm tra cả `byteSize()` và `byteAlignment()` |
| Dùng `paddingLayout(24)` để chèn 3 byte | Thực tế chèn 24 **byte** | Dùng `paddingLayout(3)` |
| Dùng `JAVA_INT` đọc `byte[]` heap segment | Alignment của heap backing không đủ | Dùng `JAVA_INT_UNALIGNED` hoặc backing segment khác phù hợp |
| Dùng `JAVA_INT` tại offset 1 của native segment | Truy cập không căn chỉnh | Căn lại offset hoặc dùng unaligned layout đúng định dạng |
| Dùng `nativeOrder()` cho dữ liệu network big-endian | Wire bytes khác khi đổi nền tảng | Dùng `withOrder(BIG_ENDIAN)` |
| Tự tính mọi offset bằng hằng số | Dễ sai khi layout đổi | Dùng `byteOffset`/layout paths |
| Dùng `byteOffset` với open `sequenceElement()` | Offset chưa có index cụ thể | Dùng `VarHandle`/`byteOffsetHandle` |
| Quên tail padding rồi tạo sequence của struct size 5/alignment 4 | Stride không căn chỉnh | Bổ sung tail padding hoặc mô tả packed đúng |
| Ghi/đọc segment sau khi arena đóng | Không còn lifetime hợp lệ | Giữ dữ liệu trong scope của Arena |
| Đưa confined segment sang thread khác | Vi phạm thread-confinement | Dùng shared arena hoặc chuyển dữ liệu qua API phù hợp |
| Cho rằng shared arena làm data race biến mất | Vẫn có cạnh tranh ghi/đọc | Đồng bộ hóa hoặc dùng access mode đúng |
| Dùng atomic access mode cho unaligned VarHandle | Mode không hỗ trợ | Dùng căn chỉnh thích hợp và đọc contract |
| Coi `JAVA_LONG` luôn tương đương `C long` | Sai trên một số ABI | Dùng canonical layouts/ABI metadata |
| Truy cập memory theo pointer do native cung cấp mà không kiểm tra | Có thể mất an toàn native memory | Xác minh kích thước, ownership và lifetime |
| Nhầm `JAVA_CHAR` với C `char` | Java char 2 byte, C char thường 1 byte | Chọn layout theo C ABI và mã hóa ký tự |
| Dùng `==` để so layout | So sánh identity thay vì đặc điểm layout | Dùng `equals` |

## 21. Checklist trước khi dùng FFM MemoryLayout trong dự án

1. **Vùng dữ liệu đến từ đâu?** Java heap, native arena, memory-mapped file hay con trỏ từ thư viện C?
2. **Có layout chính thức của dữ liệu không?** Lấy từ protocol specification, native header hoặc schema đã kiểm chứng.
3. **Kiểu mỗi trường và số byte?** Phân biệt Java primitive và C scalar type theo ABI.
4. **Byte order có được quy định không?** Chọn `withOrder(...)` cho dữ liệu trao đổi nếu cần.
5. **Alignment của từng trường?** Tính theo byte và lũy thừa của 2; không tự giả định mọi trường packed.
6. **Struct cần internal/tail padding không?** Khai báo `paddingLayout(n)` đúng số byte.
7. **Có mảng nhiều struct không?** Đảm bảo stride chia hết cho alignment của element layout.
8. **Có thể dùng `byteOffset(...)` không?** Với index động, dùng layout path open và `VarHandle`.
9. **Tài nguyên được cấp phát và giải phóng bởi ai?** Định nghĩa owner/lifetime bằng Arena hoặc contract của native library.
10. **Có dùng qua nhiều thread không?** Confined hay shared arena; cần synchronization không?
11. **Truy cập có nằm trong bounds không?** Kiểm tra kích thước segment và chỉ số mảng.
12. **Có yêu cầu atomic không?** Xem alignment và access mode được hỗ trợ, không mặc định unaligned atomic.
13. **Có dữ liệu unsigned không?** Diễn giải giá trị đúng, ví dụ `Integer.toUnsignedLong`.
14. **Có đang dùng native pointer không?** Xác minh ownership, ABI và độ dài thật của vùng nhớ.
15. **Đã thử trên nền tảng mục tiêu chưa?** Kiểm tra size/offset/alignment với nguồn C hoặc protocol và chạy integration test.

**Ghi nhớ:** `MemoryLayout` mô tả **hình dạng các byte**; `ValueLayout` mô tả **một giá trị và cách giải mã byte**; `byteAlignment` ràng buộc **vị trí địa chỉ**; `paddingLayout` đưa vào **các byte trống cần thiết**; `MemorySegment` mới là **vùng dữ liệu thật**. Trong Java 27, sử dụng các thành phần này cùng `Arena` giúp diễn đạt bố cục off-heap rõ ràng mà vẫn có kiểm tra bounds và lifetime.

## 22. Tài liệu chính thức Java SE 27

- [`MemoryLayout` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemoryLayout.html): cấu trúc layout, size, alignment, path, struct/union/sequence/padding và VarHandle.
- [`ValueLayout` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html): carrier, byte order, built-in aligned/unaligned layouts.
- [`StructLayout` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/StructLayout.html): nhóm trường tuần tự, names và byte alignment.
- [`SequenceLayout` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SequenceLayout.html): element count/stride và truy cập theo sequence.
- [`UnionLayout` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/UnionLayout.html): các member dùng chung offset bắt đầu.
- [`MemorySegment` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): get/set, alignment, maxByteAlignment, bounds và scope.
- [`Arena` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native memory và quản lý lifetime/confinement.
- [`Linker` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html): ABI, canonical layouts, C scalar types và native linking.
- [`VarHandle` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): cách truy cập dữ liệu và các access mode.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): mục tiêu và tính năng FFM đã chính thức hóa.
