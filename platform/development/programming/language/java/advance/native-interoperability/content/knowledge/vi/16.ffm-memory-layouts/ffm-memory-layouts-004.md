# Tính byte đệm tường minh thay vì giả định structLayout tự mô phỏng trình biên dịch C

> **Ngữ cảnh:** Java Advance → Native Interoperability → Bố trí dữ liệu. Bài này hướng dẫn thiết kế `MemoryLayout.structLayout(...)` của Foreign Function & Memory API (FFM) sao cho **vị trí, kích thước, căn chỉnh và byte đệm (padding)** khớp đúng hợp đồng dữ liệu cần dùng. Trọng tâm là hiểu rằng `structLayout` **không tự chèn padding giống trình biên dịch C**, phải tự mô tả byte đệm giữa các trường **và cuối struct** khi cần. Các ví dụ Java dùng **JDK 22+** (FFM API chính thức từ JDK 22).

## 1. Hiểu đúng: `structLayout` nối các layout, không biên dịch một C struct

Trong C, compiler bố trí trường của `struct` theo ABI, kiểu dữ liệu, quy tắc alignment, tùy chọn packing và đôi khi compiler-specific attributes. Đối với một struct như:

```c
#include <stdint.h>

typedef struct {
    uint8_t  tag;      // 1 byte
    uint32_t count;    // 4 byte
    uint16_t flags;    // 2 byte
} Record;
```

Trên **nhiều ABI phổ biến** với `uint32_t` alignment 4 và `uint16_t` alignment 2, compiler thường bố trí:

```text
Byte offset:   0     1  2  3    4  5  6  7    8  9   10 11
             +-----+---------+-------------+-------+-------+
Record       | tag | pad (3) |    count    | flags |pad (2)|
             +-----+---------+-------------+-------+-------+
Field start:    0                 4            8
sizeof(Record) = 12 byte            alignof(Record) = 4 byte
```

Số **12** ở trên là minh họa cho ABI có các điều kiện nêu ra, **không phải kết quả C Standard bắt buộc ở mọi hệ điều hành/compiler**. Muốn xác nhận trên hệ thống đích, phải dùng `sizeof`, `_Alignof`/`alignof` và `offsetof` từ chính toolchain C được dùng để xây thư viện native.

FFM không có thông tin ABI C chỉ từ lời gọi:

```java
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_SHORT.withName("flags")
);
```

Đoạn trên **không hợp lệ** với alignment tự nhiên của các layout này: `tag` dài 1 byte, làm `count` bắt đầu tại byte offset **1**, trong khi `JAVA_INT` thường yêu cầu alignment **4**. Thay vì âm thầm chèn ba byte trống như một số C compiler, `structLayout` kiểm tra và có thể ném `IllegalArgumentException`.

**Quy tắc cốt lõi:**

- `structLayout(M1, M2, ..., Mn)` đặt các member liên tiếp; vị trí member sau bằng tổng `byteSize()` của các member trước đó, kể cả **padding layout do ta chèn**.
- **Không tự chèn padding vào giữa các member**, không tự tính padding cuối để bắt chước `sizeof(C struct)`.
- **Có kiểm tra alignment**: một member ở offset không phù hợp `byteAlignment()` có thể khiến factory ném `IllegalArgumentException` ngay lúc tạo layout.
- `MemoryLayout.paddingLayout(n)` biểu diễn **n byte** bị bỏ qua; trong FFM ổn định n là số **byte**, không phải bit (cần lưu ý khi đọc tài liệu preview/incubator cũ).
- Layout chỉ mô tả bố cục; khi dùng `Arena.allocate(layout)` mới thực sự cấp phát memory và khi dùng `segment.get/set` mới truy cập dữ liệu.

## 2. Phân biệt ba dạng padding

**Padding giữa các trường (inter-field padding)** được chèn trước một field để địa chỉ field đáp ứng alignment. Trong ví dụ `Record`, `tag` kết thúc tại byte 1; `count` cần offset chia hết cho 4 → chèn **3 byte** để bắt đầu tại byte 4.

**Padding cuối (tail padding)** được chèn sau trường cuối để tổng kích thước struct là bội số alignment của struct (khi ABI yêu cầu). `flags` nằm ở byte 8–9; kích thước đang là 10 nhưng struct cần stride 12 để phần tử kế tiếp trong C array căn chỉnh `count` đúng chỗ → chèn **2 byte**.

**Padding trước struct (leading padding)** trong hầu hết ví dụ đơn giản không xuất hiện: base address của struct được cấp phát phù hợp alignment. Nhưng khi struct lồng trong struct khác, **outer struct** có thể cần chèn padding trước nested struct, giống như trước một field lớn.

| Loại | Vị trí | Vì sao cần | Cách mô tả trong FFM |
|---|---|---|---|
| Inter-field | Giữa các trường | Căn chỉnh field kế tiếp | Chèn `MemoryLayout.paddingLayout(gap)` trước field |
| Tail | Cuối một struct | Bảo đảm `sizeof`/stride trong array hoặc nested layout | Chèn `paddingLayout(tail)` sau field cuối |
| Outer/nested | Trước một nested struct trong struct cha | Căn chỉnh địa chỉ bắt đầu của nested struct | Chèn padding trong **outer struct** |
| Packed layout | Có thể không có các khoảng trên | Hợp đồng packed giảm alignment | Cố ý dùng layout field `withByteAlignment(...)` sau khi xác minh compiler |

**Không nên gọi mọi byte trống là padding tự động.** Một định dạng file/network có thể có **reserved field** phải bằng 0 hoặc có ý nghĩa tương lai; đó là yêu cầu của protocol. `paddingLayout` chỉ diễn tả vùng bỏ qua về mặt layout. Nếu reserved field phải được kiểm tra hoặc ghi giá trị có nghĩa, dùng `ValueLayout.JAVA_BYTE`/`sequenceLayout` với tên/contract rõ.

## 3. Cách tính alignment và offset bằng số học byte

Gọi `cursor` là số byte đã bố trí từ đầu struct, `A` là alignment (byte) của field kế tiếp.

Cần tìm **offset nhỏ nhất ≥ cursor** và chia hết cho `A`:

```text
nextOffset = alignUp(cursor, A)
gap        = nextOffset - cursor
newCursor  = nextOffset + field.byteSize()

alignUp(1, 4) = 4   => gap 3
alignUp(8, 2) = 8   => gap 0
alignUp(10,4) = 12  => tail 2
```

Khi `cursor >= 0` và `A > 0`:

```text
gap = (A - (cursor % A)) % A
nextOffset = cursor + gap
```

FFM layout alignments là những giá trị phù hợp quy tắc alignment của API (thường lũy thừa 2). Dù vậy không nên dùng phép cộng không kiểm tra nếu offset/size đến từ input lớn. Trong Java, `Math.addExact` phát hiện tràn số thay vì cho offset âm do overflow.

Áp dụng vào `Record`:

| Bước | Field/layout | Size | Alignment | Cursor trước | Gap trước | Offset field | Cursor sau |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `tag` (`JAVA_BYTE`) | 1 | 1 | 0 | 0 | 0 | 1 |
| 2 | `count` (`JAVA_INT`) | 4 | 4 | 1 | 3 | 4 | 8 |
| 3 | `flags` (`JAVA_SHORT`) | 2 | 2 | 8 | 0 | 8 | 10 |
| 4 | Tail padding | 2 | — | 10 | 2 | 10 | 12 |

Natural alignment của group/struct trong trường hợp này là alignment **lớn nhất** của các member: `max(1,4,2)=4`. Padding layout tự nó có alignment tự nhiên bằng **1**, không tự tăng alignment của group.

**Cần nhớ:** `structLayout` không gọi hàm tính `alignUp` cho bạn. Bạn phải tự chèn những member `paddingLayout` tương ứng (hoặc dùng builder có tính padding tường minh).

## 4. Bốn layout tưởng giống nhau nhưng khác hoàn toàn

Xét Java FFM:

### 4.1. Sai alignment vì không có khoảng đệm

```java
// Minh họa một cấu trúc KHÔNG hợp lệ; code có thể ném exception.
var bad = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_SHORT.withName("flags")
);
```

Đặt `count` tại offset 1, trái với alignment 4 của `JAVA_INT`. `structLayout` không “tự sửa” thành offset 4.

### 4.2. Có padding giữa field nhưng chưa có tail padding

```java
var missingTail = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_SHORT.withName("flags")
);
```

Layout này **có thể được tạo**: `tag=0`, `count=4`, `flags=8`. Tổng kích thước là **10 byte**, alignment group là **4 byte**. Nó **chưa mô tả đúng** `sizeof(Record)=12` trên ABI mẫu. Quan trọng hơn, `MemoryLayout.sequenceLayout(2, missingTail)` sẽ bị từ chối, vì một phần tử dài 10 byte nhưng yêu cầu base alignment 4: phần tử thứ hai bắt đầu byte 10 bị misaligned.

### 4.3. Tường minh cả padding giữa và padding cuối

```java
var record = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_SHORT.withName("flags"),
        MemoryLayout.paddingLayout(2)
);
```

Bây giờ `record.byteSize()==12`, `record.byteAlignment()==4` và các offset là `0,4,8`. `MemoryLayout.sequenceLayout(2, record)` dài 24 byte và mỗi record có stride 12.

### 4.4. Packed layout cố ý bỏ padding (không phải bản sửa chung)

```java
var packed = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withByteAlignment(1).withName("count"),
        ValueLayout.JAVA_SHORT.withByteAlignment(1).withName("flags")
);
```

Dạng này cho `packed.byteSize()==7`, `packed.byteAlignment()==1`, offset các trường `0,1,5`. Nó phù hợp **chỉ khi** C ABI/protocol thật sự dùng packed representation như vậy. Giảm alignment để “né exception” trong một struct C bình thường sẽ khiến Java đọc sai field.

**Cảnh báo:** `record.withByteAlignment(1)` trên **một group đã tạo** không làm các field bên trong tự dời offset; cũng không sửa được lời gọi `structLayout` sai alignment từ đầu. Nếu biểu diễn packed, cần xác định rõ alignment của **member** và layout tổng thể, không chỉ chỉnh alignment của outer group.

## 5. Ví dụ chạy được: inter-field padding, tail padding, packed layout

**Tệp `ExplicitPaddingDemo.java`, JDK 22+:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class ExplicitPaddingDemo {
    public static void main(String[] args) {
        try {
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE,
                    ValueLayout.JAVA_INT);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad-order=IllegalArgumentException");
        }

        var withoutTail = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("tag"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("count"),
                ValueLayout.JAVA_SHORT.withName("flags")
        );

        System.out.println("without-tail=" + withoutTail.byteSize()
                + ",align=" + withoutTail.byteAlignment());

        try {
            MemoryLayout.sequenceLayout(2, withoutTail);
        } catch (IllegalArgumentException ex) {
            System.out.println("array-without-tail=IllegalArgumentException");
        }

        var record = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("tag"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("count"),
                ValueLayout.JAVA_SHORT.withName("flags"),
                MemoryLayout.paddingLayout(2)
        );

        long tagOffset = record.byteOffset(groupElement("tag"));
        long countOffset = record.byteOffset(groupElement("count"));
        long flagsOffset = record.byteOffset(groupElement("flags"));

        System.out.println("record=" + record.byteSize()
                + ",align=" + record.byteAlignment());
        System.out.println("offsets=" + tagOffset + ","
                + countOffset + "," + flagsOffset);
        System.out.println("array-size=" +
                MemoryLayout.sequenceLayout(2, record).byteSize());

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(record);
            segment.set(ValueLayout.JAVA_BYTE, tagOffset, (byte) 9);
            segment.set(ValueLayout.JAVA_INT, countOffset, 1200);
            segment.set(ValueLayout.JAVA_SHORT, flagsOffset, (short) 7);

            System.out.println("values="
                    + segment.get(ValueLayout.JAVA_BYTE, tagOffset) + ","
                    + segment.get(ValueLayout.JAVA_INT, countOffset) + ","
                    + segment.get(ValueLayout.JAVA_SHORT, flagsOffset));
        }

        var packed = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("tag"),
                ValueLayout.JAVA_INT
                        .withByteAlignment(1).withName("count"),
                ValueLayout.JAVA_SHORT
                        .withByteAlignment(1).withName("flags")
        );

        System.out.println("packed=" + packed.byteSize()
                + ",align=" + packed.byteAlignment());
        System.out.println("packed-offsets="
                + packed.byteOffset(groupElement("tag")) + ","
                + packed.byteOffset(groupElement("count")) + ","
                + packed.byteOffset(groupElement("flags")));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExplicitPaddingDemo.java
java ExplicitPaddingDemo
```

**stdout (đã kiểm tra hành vi tương đương bằng JDK 24):**

```text
bad-order=IllegalArgumentException
without-tail=10,align=4
array-without-tail=IllegalArgumentException
record=12,align=4
offsets=0,4,8
array-size=24
values=9,1200,7
packed=7,align=1
packed-offsets=0,1,5
```

Giải thích từng kết quả:

- `bad-order`: `JAVA_INT` ở offset 1 không đáp ứng alignment4, nên factory **từ chối** chứ không âm thầm chèn 3 byte.
- `without-tail=10,align=4`: có internal padding 3 byte nhưng thiếu 2 byte ở cuối. Một struct có size10 không tự biến thành 12.
- `array-without-tail`: `sequenceLayout` yêu cầu kích thước element phù hợp element alignment; stride10 không đảm bảo phần tử kế tiếp được căn chỉnh 4.
- `record=12,align=4`: hai khoảng đệm **3+2** byte tạo đúng bố cục ABI mẫu.
- `offsets=0,4,8`: được tính bằng **layout path**, không lấy từ hard-code khi truy cập.
- `array-size=24`: hai record có stride12.
- `values`: `Arena.allocate(record)` cấp phát native memory phù hợp size/alignment; `get/set` hoạt động ở đúng byte offset.
- `packed=7,align=1`: layout packed thay đổi contract, không phải chỉ là tối ưu kích thước vô hại.

Trong ví dụ này, ta không in byte hex vì `JAVA_INT`/`JAVA_SHORT` dùng byte order native của máy. Số **giá trị** và **offset** vẫn ổn định; dãy byte cụ thể có thể khác khi đổi endianness.

## 6. `byteOffset`, `byteSize` và `byteAlignment` là nguồn sự thật của Java layout

Sau khi tạo layout, **không suy diễn offset từ thứ tự field**. Truy vấn trực tiếp:

```java
import java.lang.foreign.MemoryLayout;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

// Giả định record được tạo và có các field được đặt tên.
long byteLength = record.byteSize();
long requiredAlignment = record.byteAlignment();
long countOffset = record.byteOffset(groupElement("count"));
long flagsOffset = record.byteOffset(groupElement("flags"));
```

Đoạn này là trích đoạn minh họa, biến `record` chưa được tạo trong snippet. Với layout chuẩn ở mục 5, kết quả tương ứng là `12`, `4`, `4` và `8`.

Các giá trị không thể hoán đổi:

| API | Đơn vị/kết quả | Ví dụ |
|---|---|---|
| `record.byteSize()` | Tổng số **byte** của cả struct, gồm padding | 12 |
| `record.byteAlignment()` | Căn chỉnh yêu cầu cho base address | 4 |
| `record.byteOffset(groupElement("count"))` | Byte offset field tính từ đầu struct | 4 |
| `ValueLayout.JAVA_INT.byteSize()` | Kích thước một giá trị `int` | 4 |
| `record.select(groupElement("count"))` | Layout **field** tại path, không phải byte offset | Named int layout |
| `MemoryLayout.sequenceLayout(2, record).byteSize()` | Size cho **2 record** | 24 |

Tên field được gắn bởi `withName("...")` để layout path có thể chọn đúng phần tử. Tên này **không ghi vào native memory**: byte buffer chỉ chứa dữ liệu và padding. Nếu đổi tên hoặc lồng layout, đường path cũng phải đổi. Khi không thể tìm field, `byteOffset`/`select` có thể báo `IllegalArgumentException`.

Các layout là **mô tả bất biến**; gọi `withName` hoặc `withByteAlignment` trả layout mới, không sửa member cũ tại chỗ. Hãy tránh việc cache offset của layout A rồi dùng với layout B đã đổi packing/alignment.

## 7. Tự động *tính* padding bằng helper nhưng vẫn chèn nó tường minh

Trong codebase có nhiều struct, tự đếm `paddingLayout(3)`/`paddingLayout(2)` cho từng field dễ sai. Ta có thể viết một **helper Java do ứng dụng sở hữu**, tính khoảng đệm trước mỗi member và tail padding, rồi trả về `structLayout` đã chèn các padding member tường minh.

Đây **không phải chức năng tự động của `MemoryLayout.structLayout`**. Helper chỉ mô phỏng một **quy tắc alignment được ta chủ động chọn**: align mỗi field lên bội số `field.byteAlignment()`, và align tổng size lên bội số alignment tối đa. Quy tắc đó thường mô tả nhiều C structs thông thường, nhưng chưa đủ để tự động xác định mọi C ABI (packed structs, bitfields, compiler attributes, vector types và loại C phụ thuộc platform vẫn cần xử lý).

### Hàm dựng layout theo alignment

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.util.ArrayList;

public final class LayoutBuilder {
    private LayoutBuilder() {}

    public static StructLayout alignedStruct(MemoryLayout... fields) {
        if (fields.length == 0) {
            throw new IllegalArgumentException("empty struct");
        }

        var parts = new ArrayList<MemoryLayout>();
        long cursor = 0;
        long maxAlignment = 1;

        for (MemoryLayout field : fields) {
            long alignment = field.byteAlignment();

            // cursor >= 0; alignment > 0.
            long gap = (alignment - (cursor % alignment)) % alignment;

            if (gap > 0) {
                parts.add(MemoryLayout.paddingLayout(gap));
            }

            cursor = Math.addExact(cursor, gap);
            parts.add(field);
            cursor = Math.addExact(cursor, field.byteSize());
            maxAlignment = Math.max(maxAlignment, alignment);
        }

        long tail = (maxAlignment -
                (cursor % maxAlignment)) % maxAlignment;

        if (tail > 0) {
            parts.add(MemoryLayout.paddingLayout(tail));
        }

        return MemoryLayout.structLayout(
                parts.toArray(MemoryLayout[]::new));
    }
}
```

Lớp `LayoutBuilder.java` biên dịch bằng `javac LayoutBuilder.java` trên JDK 22+, nhưng không có `main` nên không chạy trực tiếp bằng `java LayoutBuilder`. Các ví dụ runnable khác phía dưới sử dụng ý tưởng tương tự trong một file.

Vì sao helper này có các chi tiết trên?

- `parts` là **danh sách các field và padding layouts** theo thứ tự thật; `structLayout` chỉ nhận danh sách đã được sắp xếp đúng.
- Chỉ gọi `paddingLayout(gap)` khi `gap>0`: `paddingLayout(0)` không hợp lệ trong FFM API.
- Dùng `Math.addExact` tránh overflow âm thầm khi tính offset lớn.
- `maxAlignment` là alignment lớn nhất; padding cuối khiến `struct.byteSize()` tương thích với stride khi dùng trong sequence.
- Helper **không biết** compiler C có căn chỉnh riêng cho `long double`, `_Bool`, pointer, `#pragma pack` hay bitfield hay không. Phải cung cấp các member layouts đã phản ánh đúng ABI và xác minh với chương trình C.
- Một nested struct phải được bố trí hợp lệ từ **bên trong** trước khi đưa vào helper; helper không thể tự suy ra padding nội bộ của một layout sai.

**Giới hạn quan trọng:** Một số ABI dùng quy tắc padding cuối, alignment và padding attribute khác quy tắc này. Vì vậy **helper là công cụ tính**, không phải "C ABI auto detector". Kết quả cuối phải so sánh `sizeof/alignof/offsetof` native.

## 8. Chương trình hoàn chỉnh: helper alignment, bytes và nested struct

Ví dụ tiếp theo có hàm `alignedStruct` tự tính số pad và tạo layout; ghi record bằng **little-endian tường minh** để byte dump giống nhau bất kể endianness của máy.

**Tệp `AutoPaddingDemo.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.StringJoiner;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class AutoPaddingDemo {
    static StructLayout alignedStruct(MemoryLayout... fields) {
        if (fields.length == 0) {
            throw new IllegalArgumentException("empty struct");
        }

        var parts = new ArrayList<MemoryLayout>();
        long cursor = 0;
        long maxAlignment = 1;

        for (MemoryLayout field : fields) {
            long a = field.byteAlignment();
            long pad = (a - (cursor % a)) % a;
            if (pad > 0) {
                parts.add(MemoryLayout.paddingLayout(pad));
            }
            cursor = Math.addExact(cursor, pad);
            parts.add(field);
            cursor = Math.addExact(cursor, field.byteSize());
            maxAlignment = Math.max(maxAlignment, a);
        }

        long tail = (maxAlignment -
                (cursor % maxAlignment)) % maxAlignment;
        if (tail > 0) {
            parts.add(MemoryLayout.paddingLayout(tail));
        }
        return MemoryLayout.structLayout(
                parts.toArray(MemoryLayout[]::new));
    }

    public static void main(String[] args) {
        var intLE =
                ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
        var shortLE =
                ValueLayout.JAVA_SHORT.withOrder(ByteOrder.LITTLE_ENDIAN);

        var record = alignedStruct(
                ValueLayout.JAVA_BYTE.withName("tag"),
                intLE.withName("count"),
                shortLE.withName("flags")
        );

        long tag = record.byteOffset(groupElement("tag"));
        long count = record.byteOffset(groupElement("count"));
        long flags = record.byteOffset(groupElement("flags"));

        System.out.println("autoSize=" + record.byteSize()
                + " autoAlign=" + record.byteAlignment());
        System.out.println("autoOffsets="
                + tag + "," + count + "," + flags);

        try (Arena arena = Arena.ofConfined()) {
            var segment = arena.allocate(record);
            segment.set(ValueLayout.JAVA_BYTE, tag, (byte) 0x5A);
            segment.set(intLE, count, 0x01020304);
            segment.set(shortLE, flags, (short) 0x0506);

            var hex = new StringJoiner(" ");
            for (long offset = 0;
                    offset < segment.byteSize(); offset++) {
                int octet = Byte.toUnsignedInt(
                        segment.get(ValueLayout.JAVA_BYTE, offset));
                hex.add("%02X".formatted(octet));
            }
            System.out.println("bytes=" + hex);
        }

        var records = MemoryLayout.sequenceLayout(2, record);
        System.out.println("arraySize=" + records.byteSize()
                + " stride=" + record.byteSize());

        var outer = alignedStruct(
                ValueLayout.JAVA_BYTE.withName("kind"),
                record.withName("record")
        );
        long nestedCount = outer.byteOffset(
                groupElement("record"), groupElement("count"));
        System.out.println("outerSize=" + outer.byteSize()
                + " nestedCountOffset=" + nestedCount);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AutoPaddingDemo.java
java AutoPaddingDemo
```

**stdout (đối chiếu bằng JDK 24 cho logic tương đương):**

```text
autoSize=12 autoAlign=4
autoOffsets=0,4,8
bytes=5A 00 00 00 04 03 02 01 06 05 00 00
arraySize=24 stride=12
outerSize=16 nestedCountOffset=8
```

Diễn giải byte dump:

```text
Offset   00 01 02 03 | 04 05 06 07 | 08 09 | 10 11
Value    5A 00 00 00 | 04 03 02 01 | 06 05 | 00 00
Meaning  tag + pad3   count (LE)     flags    tail2
```

- `0x5A` là byte tag (ký tự ASCII Z).
- `00 00 00` sau tag là **3 byte đệm**.
- `04 03 02 01` là giá trị count `0x01020304` little-endian.
- `06 05` là flags `0x0506` little-endian.
- `00 00` cuối là **2 byte tail padding**.
- Trong một allocation mới từ `Arena`, memory được zero-initialized; **đừng suy rộng** điều đó thành quy định của C rằng padding bytes trong mọi C struct đều bằng 0. C code có thể để lại giá trị padding không xác định; khi trao đổi dữ liệu, đọc/ghi trường theo offset và protocol thay vì coi padding là dữ liệu nghiệp vụ.

**Nested struct:** field `kind` của `outer` dài 1 byte; field `record` có alignment 4 nên outer phải chèn 3 byte. `record.count` ở offset4 bên trong record, tức ở offset **4 + 4 = 8** tính từ đầu outer. `byteOffset(groupElement("record"), groupElement("count"))` trả chính xác 8. Nếu `record` thiếu tail padding thì việc dùng nó trong array/nested struct dễ tạo mismatch với C `sizeof(Record)` và sai stride.

## 9. Tail padding và mảng struct: lỗi chỉ lộ ra ở phần tử thứ hai

Có hai khái niệm rất dễ nhầm:

- `sizeof(Record)` bên C: kích thước **một phần tử** dùng khi pointer arithmetic `records + 1`, gồm cả tail padding nếu ABI đặt nó.
- `recordLayout.byteSize()` bên Java: tổng đúng bằng các member layouts đã đưa vào `structLayout`. Nếu thiếu tail padding, Java báo 10 chứ không tự tăng lên 12.

Trên ABI mẫu:

```text
C Record[2] với sizeof=12:

record[0] ở byte  0; count@4,  flags@8
record[1] ở byte 12; count@16, flags@20
total bytes=24
```

Nếu Java tự tính `offsetRecord2 = 10` vì thiếu tail padding:

- `record[1].tag` bị đọc từ byte 10, thực tế là padding cuối record[0].
- `record[1].count` bị đọc lệch 2 byte, dữ liệu sai và có thể vi phạm alignment.
- Những lỗi có thể “vô tình chạy được” trên một máy dùng access unaligned, nhưng không làm layout đúng.

Cách chính xác: dùng `record.byteSize()` làm stride **sau khi đã xác minh nó khớp C `sizeof(Record)`**:

```java
// Trích đoạn minh họa, giả định record và arena hợp lệ.
MemoryLayout recordsLayout =
        MemoryLayout.sequenceLayout(2, record);
MemorySegment records = arena.allocate(recordsLayout);

long secondBase = record.byteSize(); // 12, không phải 10
long countWithinRecord =
        record.byteOffset(groupElement("count")); // 4
long secondCountOffset =
        Math.addExact(secondBase, countWithinRecord); // 16

records.set(ValueLayout.JAVA_INT, secondCountOffset, 77);
```

Nếu layout sequence có alignment mismatch, `MemoryLayout.sequenceLayout(...)` có thể từ chối tạo; **đừng hạ `withByteAlignment(1)` để né exception nếu dữ liệu vẫn là C struct thường**. Giải pháp đúng là tính lại layout/padding theo ABI.

Lưu ý: `MemoryLayout.sequenceLayout(2, record)` không cấp phát memory; `arena.allocate(recordsLayout)` mới tạo segment. Một `MemorySegment` có thể chứa nhiều records, song byte offset vẫn tính từ đầu **toàn segment**.

## 10. Packed structs: giảm alignment là thay đổi hợp đồng ABI

Trong các tình huống C dùng `#pragma pack(1)` hoặc attribute packing không chuẩn C, các field có thể được đặt sát nhau. Ví dụ record packed với 1+4+2 byte sẽ có offset `0,1,5`, kích thước `7` và alignment `1` trên toolchain có packing tương ứng.

FFM có thể mô tả **định dạng packed đã được xác minh**:

```java
var packedRecord = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT
                .withByteAlignment(1).withName("count"),
        ValueLayout.JAVA_SHORT
                .withByteAlignment(1).withName("flags")
);

// packedRecord.byteSize() = 7
// packedRecord.byteAlignment() = 1
// byte offsets: tag=0, count=1, flags=5
```

Đây là trích đoạn minh họa, cần `import java.lang.foreign.*;`. Nó không phải "cách tối ưu" thay mọi layout C bình thường. Nó chỉ hợp lệ nếu **source of truth** của native ABI/wire format nói rằng field tại offset 1/5 và cho phép access unaligned.

Phân biệt rõ:

| Tình huống | Java layout nên làm gì? |
|---|---|
| C struct thường: compiler thêm inter-field/tail padding | Chèn `paddingLayout` đúng số byte, giữ alignment member |
| C struct packed với offset và alignment xác định | Hạ `withByteAlignment` của member theo contract; thường không cần padding |
| Protocol binary quy định field không căn chỉnh | Dùng packed/unaligned layout phù hợp protocol, byte order xác định |
| Chỉ muốn tránh exception từ `structLayout` | **Không** tự động chọn packed; phải đối chiếu ABI thật |
| C compiler đổi `#pragma pack` hoặc struct attribute | Cập nhật layout Java và thêm test ABI; không hy vọng JVM tự phát hiện |

**Bẫy platform:** `#pragma pack` là cơ chế compiler-specific. Trên GCC/Clang/MSVC có biến thể/giới hạn khác nhau; kể cả khi cùng `pack(1)` cũng cần kiểm tra `sizeof` và `offsetof`. Khi triển khai đa kiến trúc, tốt nhất có bộ test ABI chạy bằng toolchain thật cho từng target.

## 11. Xác minh C thật bằng `sizeof`, `_Alignof` và `offsetof`

Đừng dùng lời kể hoặc dự đoán “compiler sẽ chèn 3 byte rồi 2 byte” làm bằng chứng duy nhất. C cung cấp phép đo trực tiếp cho chính struct được biên dịch.

**Tệp `layout_probe.c` (C11, GCC/Clang):**

```c
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

typedef struct {
    uint8_t tag;
    uint32_t count;
    uint16_t flags;
} Record;

int main(void) {
    printf("size=%zu align=%zu\n",
           sizeof(Record), _Alignof(Record));

    printf("offsets=%zu,%zu,%zu\n",
           offsetof(Record, tag),
           offsetof(Record, count),
           offsetof(Record, flags));

    printf("fieldSizes=%zu,%zu,%zu\n",
           sizeof(((Record *)0)->tag),
           sizeof(((Record *)0)->count),
           sizeof(((Record *)0)->flags));

    return 0;
}
```

Biên dịch/chạy trên Linux/macOS có GCC:

```bash
gcc -std=c11 -Wall -Wextra -pedantic \
    layout_probe.c -o layout_probe
./layout_probe
```

**Ví dụ stdout thường gặp khi ABI căn chỉnh `uint32_t` theo 4 và `uint16_t` theo 2:**

```text
size=12 align=4
offsets=0,4,8
fieldSizes=1,4,2
```

Không cam kết output trên mọi target. Nếu actual `size`, `align` hoặc `offsets` khác, **ưu tiên kết quả từ compiler native đang dùng** và xây layout Java mới cho phù hợp. Việc ghép field bằng `ValueLayout.JAVA_*` chỉ có ý nghĩa khi kiểu Java đó thực sự khớp kích thước/cách biểu diễn trường C.

Cần so sánh **đầy đủ**:

| C measurement | FFM measurement |
|---|---|
| `sizeof(Record)` | `recordLayout.byteSize()` |
| `_Alignof(Record)` | `recordLayout.byteAlignment()` |
| `offsetof(Record, count)` | `recordLayout.byteOffset(groupElement("count"))` |
| `offsetof(Record, flags)` | `recordLayout.byteOffset(groupElement("flags"))` |
| `sizeof(record.count)` | `recordLayout.select(...).byteSize()` |
| Kiểu C và byte order thực tế | `ValueLayout` tương ứng và `withOrder(...)` đúng |

Tốt hơn nữa, native code có thể export một hàm ABI test trả về struct size/offsets, còn Java kiểm tra khi khởi tạo thư viện để **fail fast** nếu binary/linker version thay đổi. Không chọn offset khác chỉ bằng điều kiện “Windows hay Linux”; cùng OS có thể có nhiều ABI theo CPU, compiler option, bitness và packing.

### Không đọc padding bytes như dữ liệu nghiệp vụ

Trong C, padding bytes nói chung **không thuộc dữ liệu có nghĩa của field**; chúng có thể mang byte không xác định tùy quá trình ghi/khởi tạo. Việc serialize thẳng `sizeof(Record)` byte (bao gồm padding) sang file/network không có tính portable, cũng có nguy cơ lộ dữ liệu bộ nhớ ngoài ý muốn khi padding không được làm sạch.

Nếu cần wire format, định nghĩa **field theo byte offset, width và endianness** bằng một schema riêng. Không coi layout C native là format on-disk ổn định trừ khi đó là yêu cầu được chuẩn hóa và thử nghiệm xuyên compiler.

## 12. Java primitive layout chưa chắc khớp C primitive/ABI

Trong JDK22+:

| Java `ValueLayout` | Size thường dùng | Điều cần xác minh ở C |
|---|---:|---|
| `JAVA_BYTE` | 1 byte | Có đúng loại `uint8_t` / `int8_t` / byte buffer, và C `CHAR_BIT==8` không |
| `JAVA_SHORT` | 2 byte | Có tương ứng `int16_t` / `uint16_t`, signedness và alignment phù hợp không |
| `JAVA_INT` | 4 byte | Có tương ứng `int32_t` / `uint32_t`? C `int` trên ABI đó thật sự 4 byte? |
| `JAVA_LONG` | 8 byte | Java `long` 64-bit, nhưng **C `long` có thể 4 hoặc 8 byte** tùy ABI |
| `JAVA_FLOAT` / `JAVA_DOUBLE` | 4 / 8 byte | Native float representation, alignment và ABI constraints |
| `JAVA_CHAR` | 2 byte | Java `char` là UTF-16 code unit, **khác C `char`** |
| `ADDRESS` | Phụ thuộc kiến trúc | C pointer size/alignment, target layout, ownership và lifetime |

**Ví dụ:** Trên nhiều ABI 64-bit LP64 (Linux/macOS), `sizeof(long)` thường 8; trên Windows 64-bit LLP64, C `long` thường 4. Java `long` luôn 8. Nếu struct C khai báo `long`, không tự thay bằng `JAVA_LONG` nếu chưa đo ABI.

Khi tương tác FFM downcall với C ABI, có thể tham khảo các **canonical layouts** do `Linker.nativeLinker()` cung cấp cho các loại C chuẩn trên nền tảng đó. Tuy nhiên canonical layout cũng **không tự điền các khoảng padding giữa các field cho `structLayout`**, và không thay thế đối chiếu `sizeof/offsetof`. Đối với kiểu `uint8_t/uint32_t/uint16_t` như bài này, ta chủ động cố định width và kiểm tra alignment mục tiêu.

**Endianness là vấn đề khác padding:** `MemoryLayout.structLayout` không tự chuyển byte order cho field. Với native C struct, `ValueLayout.JAVA_INT` thường theo native order; với file/wire layout, hãy dùng `withOrder(ByteOrder.LITTLE_ENDIAN/BIG_ENDIAN)` đúng đặc tả. Hai struct có cùng padding/offset nhưng khác byte order vẫn có thể đọc ra dữ liệu sai.

## 13. MemorySegment truy cập đúng offset nhưng vẫn phải quản lý lifetime

Khi layout đã đúng, dùng `Arena.allocate(layout)` để có segment với kích thước và alignment của layout:

```java
// Đoạn minh họa, recordLayout đã được tạo đúng.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(recordLayout);

    long countOffset =
            recordLayout.byteOffset(groupElement("count"));

    segment.set(ValueLayout.JAVA_INT, countOffset, 42);
    int count = segment.get(ValueLayout.JAVA_INT, countOffset);

    System.out.println(count); // 42
}
```

Đây là **trích đoạn** giả định có imports FFM và `groupElement`; không phải file chạy độc lập.

Bốn lớp kiểm tra cần thiết:

1. **Bounds:** offset + width phải nằm trong `[0, segment.byteSize())`. Padding không làm phần field rộng hơn; offset 4 của `JAVA_INT` cần đủ 4 byte tại 4–7.
2. **Alignment:** địa chỉ thực của field phải thỏa alignment của `ValueLayout`. Chèn padding đúng trước field mới giúp address đạt yêu cầu.
3. **Lifetime:** sau `arena.close()`, Java access tới segment không còn hợp lệ. Không trả segment ra ngoài `try` rồi dùng tiếp.
4. **Thread ownership:** `Arena.ofConfined()` chỉ cho thread tạo Arena truy cập. Nếu thực sự chia sẻ sang native worker/Java thread, dùng arena phù hợp và chờ mọi consumer kết thúc trước close.

**Không sửa lỗi layout bằng cách tắt kiểm tra:** `withByteAlignment(1)` là thay đổi mô hình memory, có thể vô tình cho phép đọc một field tại offset sai; kết quả đọc được không chứng minh dữ liệu đúng. Tương tự, `asSlice`/`reinterpret` không tự chèn padding hay biến memory thành một C struct đúng ABI.

Đối với buffer do native C cấp phát, nên rõ ai sở hữu `free` và tới khi nào dữ liệu còn sống; mô tả được layout chính xác không tự quản lý pointer lifetime của C. Không để C giữ address sau khi Arena giải phóng allocation Java-owned.

## 14. Những bẫy thường gặp và cách gỡ

| Sai lầm/triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `structLayout(JAVA_BYTE, JAVA_INT)` ném `IllegalArgumentException` | `JAVA_INT` bắt đầu ở offset 1 nhưng alignment4 | Chèn `paddingLayout(3)` hoặc dùng field unaligned chỉ khi format packed |
| Layout hợp lệ nhưng `byteSize()==10`, còn C `sizeof==12` | Thiếu tail padding | Tính alignment tối đa và chèn `paddingLayout(2)` sau field cuối |
| `sequenceLayout(2, record)` báo lỗi | Element size không chia hết element alignment | Sửa stride/tail padding; không hạ alignment để né |
| Field đầu đúng, record thứ hai đọc sai | Dùng stride10 thay vì C `sizeof==12` | Dùng layout đã verify và `record.byteSize()` |
| Thay C `long` bằng `JAVA_LONG` trên Windows | C `long` không luôn 8 byte | Dùng canonical C layout/ABI probe |
| Sửa field thành `withByteAlignment(1)` rồi đọc ra số nhưng giá trị không khớp C | Mô tả packed trong khi C struct bình thường | Xác minh `offsetof` trước; dùng natural member alignment + padding |
| Có `paddingLayout(0)` gây exception | API đòi padding size dương | Chỉ thêm padding khi `gap>0` |
| Byte offset C và Java khớp nhưng giá trị bytes khác | Native vs chosen byte order; signedness/type width | Chọn `withOrder`/type mapping phù hợp |
| C compiler bật `#pragma pack`, Java vẫn dùng padding chuẩn | ABI packing thay đổi | Cập nhật layout theo phép đo trên compiler đó |
| Dùng `structLayout` như binary file serializer chung | C padding/tail/platform ABI không portable | Định nghĩa wire protocol tách biệt |
| Nhầm `byteOffset` với field index | `byteOffset` luôn tính **byte** | Gọi `byteOffset(path)` và test từng field |
| Ghi nhầm vào padding bytes rồi trông chờ compiler giữ giá trị | Padding không phải field nghiệp vụ | Ghi/đọc theo named field, không dùng padding làm dữ liệu |
| Nested struct offset sai | Thiếu outer padding hoặc inner tail padding | Verify riêng inner và outer; nested `byteOffset(groupElement(...), ...)` |
| Mảng chứa pointer/native address không đúng width | ABI pointer size khác dự đoán | Dùng `ValueLayout.ADDRESS` / native ABI mapping và xác minh pointer layout |
| Chạy Java code trên JDK17 báo không có `java.lang.foreign` | API ổn định từ JDK22 | Chạy trên JDK22+ hoặc theo API incubator/preview tương ứng, không trộn |

### Kiểm tra theo từng lớp trước khi debug crash native

1. **Đọc `Bản C`**: đúng header/version, `#pragma pack`/attribute, compiler flags?
2. **Đo `ABI C`**: `sizeof`, `_Alignof`, `offsetof`, `sizeof(field)`; xác minh kiến trúc/ABI.
3. **Đọc `Layout Java`**: `byteSize`, `byteAlignment`, `byteOffset` từng field và nested field.
4. **So sánh từng số**: nếu mismatch ở C và Java, sửa layout chứ không thử đoán offset trong `get`/`set`.
5. **Đọc byte hex**: xác minh endian/field encoding, **không** suy diễn từ raw struct memory chứa padding chưa khởi tạo.
6. **Kiểm tra lifetime**: Arena còn sống trong suốt native call/callback? Shared buffer có bị sửa đồng thời không?
7. **Thêm ABI regression test**: build/run probe cho mỗi platform/toolchain và đối chiếu trong CI.

## 15. Bài tập có đáp án

**Bài 1 — tính khoảng đệm trước field.** Một layout có `byteOffset=1` sau field `JAVA_BYTE`, field tiếp theo `JAVA_INT` cần alignment4. Cần bao nhiêu byte padding và field int bắt đầu ở đâu?

**Đáp án:** Cần `(4-(1%4))%4 = 3` byte. `JAVA_INT` bắt đầu ở offset **4**.

**Bài 2 — không quên padding cuối.** Record gồm tag1, padding3, int4, short2. Natural struct alignment4. Kích thước nếu thiếu tail, tail cần thêm và stride đúng?

**Đáp án:** Size ban đầu **10**, tail padding **2**, size/stride đúng **12**. Record thứ hai bắt đầu byte12.

**Bài 3 — vì sao factory từ chối?** `structLayout(JAVA_SHORT, JAVA_INT)` có size dự kiến 6. Vì sao không tạo thành công, và sửa thế nào nếu muốn layout aligned?

**Đáp án:** `JAVA_INT` bắt đầu offset2 nhưng alignment4; chèn `paddingLayout(2)` trước int, thành offset4 và size8. Nếu thật sự packed, có thể giảm alignment của int theo ABI đã kiểm tra, nhưng đó là contract khác.

**Bài 4 — size và alignment khác nhau.** Layout `structLayout(JAVA_BYTE, paddingLayout(3), JAVA_INT, JAVA_SHORT)` báo byteSize10 và byteAlignment4. Có thể dùng làm element của `sequenceLayout(3, layout)` không?

**Đáp án:** Không; 10 không chia hết4 và vị trí phần tử sau không được căn chỉnh đúng. Chèn thêm tail padding2, size12, sau đó `sequenceLayout(3, ...)` có size36.

**Bài 5 — packed vs normal.** Một C struct có trường `uint32_t count` ở offset1 do compiler bật packing. Java nên thêm padding3 vào trước int hay giảm alignment của member?

**Đáp án:** Với hợp đồng **packed đã được chứng minh** (offsetof count =1), dùng `JAVA_INT.withByteAlignment(1)`; không chèn padding3 vì điều đó biến layout thành **normal aligned**, khác ABI.

**Bài 6 — nested.** Outer struct có `byte kind` ở offset0 và `Record` có alignment4, size12. `Record.count` trong record nằm offset4. Tính offset count tính từ đầu outer, size outer nếu có tail thích hợp?

**Đáp án:** Trước Record chèn padding3 → nested Record ở offset4. `count` tuyệt đối ở offset **8**. Outer có size **16**, alignment4.

**Bài 7 — thiết kế test liên nền tảng.** Bạn chỉ biết C struct có `unsigned long size` và `void *data`. Có thể luôn dùng `JAVA_LONG` và `ADDRESS` theo thứ tự rồi tự căn 8 byte?

**Đáp án:** Không. C `unsigned long` và pointer có kích thước/alignment phụ thuộc ABI; thứ tự/packing cũng quan trọng. Đo bằng `sizeof`/`_Alignof`/`offsetof` trên target, cân nhắc canonical layouts của native linker rồi tính padding tường minh.

**Bài 8 — sửa code tính padding.** Helper luôn gọi `paddingLayout(gap)` ngay cả khi `gap==0`. Điều gì xảy ra?

**Đáp án:** `MemoryLayout.paddingLayout(0)` không hợp lệ, gây `IllegalArgumentException`. Chỉ thêm layout đệm khi `gap>0`.

**Bài 9 — đọc giá trị đúng nhưng byte dump khác.** C struct và FFM layout có cùng size/alignment/offset; khi đọc từ file big-endian, Java `get(JAVA_INT,...)` ra giá trị sai trên máy little-endian. Padding có phải nguyên nhân?

**Đáp án:** Không nhất thiết. Đó là lỗi **byte order**. Dùng `JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` nếu file protocol quy định big-endian, không sửa padding để khắc phục.

## 16. Checklist trước khi gọi native và tài liệu chuẩn

Để bảo đảm layout không dựa vào giả định mơ hồ:

- [ ] Đã chọn đúng **JDK 22+**, không lẫn incubator/preview APIs.
- [ ] Đã xác định source of truth: **C ABI trong binary hiện tại** hay **wire/file specification**?
- [ ] Đã đối chiếu từng field: C type, width, alignment, signedness và byte order.
- [ ] Đã tính và **chèn inter-field padding** theo offsets thực.
- [ ] Đã tính **tail padding** để `byteSize()` khớp stride/`sizeof` khi dùng mảng/nested struct.
- [ ] Đã thử `MemoryLayout.structLayout` mà không nén alignment sai chỉ để né exception.
- [ ] Đã kiểm tra `byteSize`, `byteAlignment` và `byteOffset(groupElement(...))`.
- [ ] Đã đo `sizeof`, `_Alignof`, `offsetof` với **đúng** compiler, flags, OS, CPU ABI.
- [ ] Nếu packed, đã xác minh rules và dùng `withByteAlignment` trên field phù hợp.
- [ ] Nếu nested/sequence, đã kiểm tra offset trong/ngoài và stride của **phần tử tiếp theo**.
- [ ] Nếu truyền segment xuống C, đã xác định lifetime Arena, ownership và thread-safety.
- [ ] Đã thử cả record đơn lẻ lẫn mảng ít nhất 2 phần tử và có test regression theo target ABI.

**Kết luận:** `MemoryLayout.structLayout(...)` là một công cụ **lắp ghép layout có kiểm tra alignment**, **không phải trình biên dịch C mini**. Đúng ABI nghĩa là tự tính/chèn padding theo dữ liệu đo được; nhớ cả **byte đệm giữa field lẫn byte đệm cuối struct**. Để dùng bền vững, so sánh `sizeof`/`offsetof` native với `byteSize`/`byteOffset` Java, thay vì dựa vào kết quả “có vẻ đúng” trên một nền tảng.

### Tài liệu chính thức

- [Java SE 22 — MemoryLayout API; `structLayout`, `paddingLayout`, `sequenceLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java SE 22 — StructLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [Java SE 22 — ValueLayout, `withByteAlignment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 22 — MemorySegment `get/set` và Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [JEP 454 — Foreign Function & Memory API chính thức từ JDK 22](https://openjdk.org/jeps/454)
- [Java SE 22 — Linker và canonical layouts theo ABI](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [C language — `offsetof` trong `stddef.h`, `_Alignof`/`sizeof` (tham khảo đặc tả compiler đích)](https://en.cppreference.com/w/c/types/offsetof)
