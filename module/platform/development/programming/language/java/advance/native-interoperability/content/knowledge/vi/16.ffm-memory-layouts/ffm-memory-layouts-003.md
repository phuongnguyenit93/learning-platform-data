# StructLayout, UnionLayout và SequenceLayout biểu diễn cấu trúc C

## Mục tiêu bài học

Khi tương tác Java với C/C++ bằng Foreign Function & Memory API (FFM), dữ liệu thường nằm trong một vùng nhớ native, không phải object Java. **MemorySegment** cung cấp view có giới hạn trên vùng nhớ; **MemoryLayout** mô tả **cách các byte của vùng nhớ được sắp đặt**. Ba layout trung tâm để biểu diễn cấu trúc C là:

- **StructLayout** — các trường nối tiếp nhau, mô phỏng C **struct**.
- **UnionLayout** — các trường bắt đầu ở cùng offset và chia sẻ bytes, mô phỏng C **union**.
- **SequenceLayout** — các phần tử cùng layout nằm liên tiếp, mô phỏng C array **T[N]**.

Sau bài này, bạn có thể xây layout theo header C, tính **byteSize**, **byteAlignment**, **byteOffset**, hiểu padding và stride, truy cập thành viên lồng nhau qua **VarHandle**, đối chiếu bằng **sizeof/offsetof** của C compiler, và nhận ra chỗ cần xử lý ABI, endianness, packed struct, pointer và vòng đời native memory.

**Phiên bản:** Các chương trình Java dùng package **java.lang.foreign** đã được chuẩn hóa trong **JDK 22** (JEP 454). Chạy bằng JDK 22+; API ở JDK 17 là incubator, JDK 21 là preview nên không dùng nguyên xi các câu lệnh dưới đây. Ví dụ mô tả C ABI được nêu với điều kiện cụ thể; không khẳng định một kích thước hoặc alignment áp dụng cho mọi CPU/OS/compiler.

## 1. Layout là mô tả, segment mới là bộ nhớ

~~~text
MemorySegment:
+------+------+------+------+------+------+------+------+
| byte | byte | byte | byte | byte | byte | byte | ...  |
+------+------+------+------+------+------+------+------+
             ^
             |
         MemoryLayout
         /    |     \
       struct union  sequence
       nối tiếp     lặp nhiều
             chồng lấn
~~~

**MemoryLayout** không tự cấp phát dữ liệu và không tự copy bytes. Nó chỉ chứa quy tắc vị trí, kích thước và alignment. **MemorySegment** biểu diễn vùng byte thực, có giới hạn truy cập và thời gian sống. Với native memory, **Arena** thường quản lý cấp phát và giải phóng.

Một tiến trình thao tác:

1. Định nghĩa layout từ kiểu C và ABI.
2. Kiểm tra **layout.byteSize()**, **layout.byteAlignment()** và các field offsets.
3. Cấp phát memory bằng **arena.allocate(layout)** hoặc nhận một segment được tạo nơi khác.
4. Lấy **VarHandle** từ layout path.
5. Đọc/ghi dữ liệu trong khi segment còn sống, đúng alignment, bounds và thread.

Các loại layout:

| Loại | Cách diễn giải | Quy tắc kích thước |
| --- | --- | --- |
| **ValueLayout** | Scalar như int, float, byte, address | Theo carrier/layout |
| **PaddingLayout** | Vùng byte đệm | Số byte chỉ định |
| **StructLayout** | Group các member nối tiếp | Tổng byteSize của những member đã khai báo |
| **UnionLayout** | Group các member chồng lấn | Max byteSize của member |
| **SequenceLayout** | Lặp lại một element layout | Count × element byteSize |

StructLayout và UnionLayout đều là **GroupLayout**; các member có thể là value hoặc layout lồng nhau. SequenceLayout có thể chứa struct; struct có thể chứa sequence/union; union có thể chứa struct.

### Một value layout đơn giản

**File OneInt.java:**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class OneInt {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory =
                    arena.allocate(ValueLayout.JAVA_INT);
            memory.set(ValueLayout.JAVA_INT, 0, 123);
            System.out.println("bytes = " + memory.byteSize());
            System.out.println("value = "
                    + memory.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Chạy:

~~~bash
javac OneInt.java
java OneInt
~~~

Stdout:

~~~text
bytes = 4
value = 123
~~~

**ValueLayout.JAVA_INT** cố định 4 byte theo Java; không tự suy ra C long hoặc size_t cũng là 4 byte.

## 2. StructLayout: các member nối tiếp và padding phải tường minh

C:

~~~c
struct Header {
    unsigned char tag;
    int value;
};
~~~

Nếu ABI của C có char 1 byte, int 4 byte và int cần alignment 4, compiler điển hình bố trí:

~~~text
Byte offset   0   1   2   3   4   5   6   7
             +---+---+---+---+---------------+
             |tag|pad|pad|pad|  int value    |
             +---+---+---+---+---------------+

offsetof(tag) = 0
offsetof(value) = 4
sizeof(Header) = 8
_Alignof(Header) = 4
~~~

**MemoryLayout.structLayout không tự chèn padding.** Mẫu này không đúng:

~~~java
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("value")
);
~~~

Vì int được đặt ngay sau byte tag, tức offset 1, trong khi JAVA_INT cần alignment 4. Việc tạo layout này bị từ chối bằng **IllegalArgumentException** thay vì tự dời int sang offset 4.

Layout phù hợp ABI giả định:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout HEADER = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
).withName("Header");
~~~

Đây là fragment khai báo, cần đặt trong field hoặc phương thức Java. **HEADER.byteSize() == 8**, **HEADER.byteAlignment() == 4**. Padding được khai báo bằng **paddingLayout(3)**: đơn vị là byte, không phải bit.

### Tail padding

C:

~~~c
struct Event {
    int code;
    unsigned char type;
};
~~~

Trong ABI căn int 4 byte, code chiếm offsets 0..3, type ở offset 4, nhưng **sizeof(Event)** có thể là 8 chứ không phải 5. Compiler thêm 3 byte **tail padding** để mỗi phần tử **Event** trong một mảng bắt đầu aligned.

Layout Java tương ứng:

~~~java
StructLayout EVENT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("code"),
        ValueLayout.JAVA_BYTE.withName("type"),
        MemoryLayout.paddingLayout(3)
);
~~~

Bỏ tail padding khiến stride của mảng struct sai, hoặc làm SequenceLayout không được chấp nhận vì **element byteSize** không chia hết cho alignment.

**Kết luận:** phải kiểm tra padding **giữa các member** và **ở cuối struct** bằng compiler C; đừng chỉ cộng độ rộng các field.

### Packed struct

Một số compiler hỗ trợ packed struct, đặt int ngay ở offset 1. Có thể mô tả một layout 5 byte với:

~~~java
StructLayout PACKED = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withByteAlignment(1).withName("value")
);
~~~

**PACKED.byteSize()==5**, **PACKED.byteAlignment()==1**. Đây là layout cho ABI packed *nếu compiler C thực sự dùng packing phù hợp*, không phải cách viết mặc định. Chỉ gọi **withByteAlignment(1)** trên group mà vẫn giữ member int cần alignment 4 không làm cho member ấy hợp lệ tại offset 1. Phải xác định đúng alignment của member hoặc giữ padding theo ABI thực.

## 3. UnionLayout: nhiều trường chồng lấn trên cùng vùng bytes

C:

~~~c
union Number {
    int count;
    float ratio;
};
~~~

Nếu int và float cùng 4 byte/alignment 4:

~~~text
Byte offset     0     1     2     3
               +-----+-----+-----+-----+
count          |   32-bit integer     |
               +-----+-----+-----+-----+
ratio          |    32-bit float      |
               +-----+-----+-----+-----+
               Cùng vị trí, không phải hai vùng riêng
~~~

Java:

~~~java
UnionLayout NUMBER = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_FLOAT.withName("ratio")
).withName("Number");
~~~

Kết quả: **NUMBER.byteSize() == 4**, **NUMBER.byteAlignment() == 4**. Không cộng hai member để thành 8 byte. Cả **count** và **ratio** bắt đầu ở offset 0.

Khi ghi vào union bằng view int rồi đọc bằng view float, Java đang diễn giải **cùng bit pattern** dưới hai kiểu khác nhau, không thực hiện chuyển đổi số học. Ví dụ bit pattern **0x3f800000** của IEEE-754 float **1.0f**:

~~~java
// Fragment: countH và ratioH cùng xuất phát từ layout NUMBER.
countH.set(segment, 0L, 0x3f800000);
float ratio = (float) ratioH.get(segment, 0L);
// ratio có giá trị 1.0f.
~~~

Điều quan trọng khi mô hình C là **active member**: mã native thường có một tag/discriminator chỉ ra khi nào count hoặc ratio mang ý nghĩa. Java layout không tự theo dõi active member, và việc đọc một C union member khác member vừa ghi có các quy tắc ngôn ngữ C/ABI riêng. Đừng mặc định đây là numeric conversion portable.

### Union có array

~~~c
union Word {
    int32_t value;
    unsigned char bytes[4];
};
~~~

Java:

~~~java
UnionLayout WORD = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("value"),
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_BYTE)
                .withName("bytes")
).withName("Word");
~~~

Hai member chồng lên cùng bốn byte. Đọc **bytes[0]** là byte cao hay thấp của value phụ thuộc **endianness**, không phụ thuộc tên layout.

### Size và tail padding của union

**unionLayout** lấy kích thước lớn nhất của các member. Tuy nhiên, C **sizeof(union)** cũng có thể được làm tròn để phù hợp alignment khi union dùng trong mảng/struct khác. Nếu member lớn nhất không cho size đúng bội số alignment, bạn phải mô hình tail padding rõ ràng, chẳng hạn thêm một member padding có size đủ lớn sau khi xác minh ABI. **withByteAlignment** không tự thêm bytes.

## 4. SequenceLayout: mảng C có stride cố định

C:

~~~c
int32_t samples[5];
~~~

Java:

~~~java
SequenceLayout SAMPLES =
        MemoryLayout.sequenceLayout(5, ValueLayout.JAVA_INT)
                .withName("samples");
~~~

- **elementCount() == 5**.
- **elementLayout().byteSize() == 4**.
- **byteSize() == 20**.
- **byteAlignment() == 4**.
- Element offsets: **0, 4, 8, 12, 16** byte.

~~~text
element index    0        1        2        3        4
byte offset      0        4        8       12       16
              +--------+--------+--------+--------+--------+
              | int[0] | int[1] | int[2] | int[3] | int[4] |
              +--------+--------+--------+--------+--------+
~~~

**Stride = elementLayout.byteSize()**, không phải một giá trị do Java tự tính từ C sizeof. Vì vậy nếu element là struct, phải đưa **tail padding** đúng C ABI vào StructLayout trước khi xây SequenceLayout.

### Array of structs

~~~c
struct Point {
    int32_t x;
    int32_t y;
};
struct Point points[3];
~~~

Java:

~~~java
StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
).withName("Point");

SequenceLayout POINTS = MemoryLayout.sequenceLayout(3, POINT)
        .withName("points");
~~~

Point có 8 byte; POINTS có 24 byte, các Point bắt đầu ở byte 0, 8 và 16. Field **points[1].y** bắt đầu tại offset **8 + 4 = 12**.

Count của SequenceLayout không được âm; phép nhân element count với element byteSize không được overflow. Layout có count **0** hợp lệ cho một số trường hợp mảng động, nhưng bản thân không cấp phát các phần tử runtime.

## 5. Ghép cả ba layout: một Table C có Row và Payload

Xét C11:

~~~c
#include <stdint.h>

typedef union {
    int32_t count;
    float ratio;
} Payload;

typedef struct {
    uint8_t kind;
    Payload payload;
} Row;

typedef struct {
    int32_t length;
    Row rows[3];
} Table;
~~~

Giả định **uint8_t=1 byte**, **int32_t=4 byte**, **float=4 byte**, **Payload size/alignment=4**. Compiler C phổ biến sẽ bố trí:

~~~text
Table, 28 byte:
  0..3     length
  4..11    rows[0]
  12..19   rows[1]
  20..27   rows[2]

Row, 8 byte:
  +0       kind
  +1..3    padding
  +4..7    payload union

Payload, 4 byte:
  +0..3    count hoặc ratio (cùng bytes)
~~~

Java FFM:

~~~java
UnionLayout PAYLOAD = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_FLOAT.withName("ratio")
).withName("payload");

StructLayout ROW = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        PAYLOAD
).withName("Row");

SequenceLayout ROWS = MemoryLayout.sequenceLayout(3, ROW)
        .withName("rows");

StructLayout TABLE = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("length"),
        ROWS
).withName("Table");
~~~

Các fragment khai báo trên sẽ được sử dụng trong ví dụ đầy đủ ở mục 7.

| Field | Offset tính từ đầu Table |
| --- | ---: |
| length | 0 |
| rows[0].kind | 4 |
| rows[0].payload.count | 8 |
| rows[0].payload.ratio | 8 |
| rows[1].kind | 12 |
| rows[1].payload.count | 16 |
| rows[2].payload.ratio | 24 |

Tổng size **4 + 3×8 = 28**, alignment 4. Offset **rows[1].payload.count = 4 + 1×8 + 4 = 16**.

## 6. Tìm member bằng layout paths và VarHandle

Để truy cập field bên trong struct/union/sequence, dùng **MemoryLayout.PathElement**.

- **groupElement("name")**: chọn group member được gắn **withName("name")**.
- **groupElement(index)**: chọn member theo thứ tự, bao gồm cả padding layout.
- **sequenceElement(1)**: chọn phần tử sequence cụ thể (index 1).
- **sequenceElement()**: path mở; khi dùng VarHandle, số index sẽ được truyền ở thời điểm gọi.

### Tính byteOffset

~~~java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long lengthOffset = TABLE.byteOffset(
        groupElement("length"));

long row1CountOffset = TABLE.byteOffset(
        groupElement("rows"),
        sequenceElement(1),
        groupElement("payload"),
        groupElement("count"));
~~~

**lengthOffset=0**, **row1CountOffset=16**. Lệnh **byteOffset** chỉ tính offset theo layout, không đọc memory.

### Tạo VarHandle

~~~java
VarHandle lengthH = TABLE.varHandle(
        groupElement("length"));

VarHandle countH = TABLE.varHandle(
        groupElement("rows"), sequenceElement(),
        groupElement("payload"), groupElement("count"));
~~~

**lengthH** có tọa độ **(MemorySegment, long baseOffset)**. **countH** có tọa độ **(MemorySegment, long baseOffset, long sequenceIndex)**. Khi gọi set, truyền giá trị ở cuối:

~~~java
lengthH.set(memory, 0L, 3);
countH.set(memory, 0L, 1L, 42);

int length = (int) lengthH.get(memory, 0L);
int secondCount = (int) countH.get(memory, 0L, 1L);
~~~

Đây là fragment cần có **TABLE**, **MemorySegment memory** và import **VarHandle**. Base offset **0L** nghĩa là segment đang bắt đầu ở đầu Table. Với segment chứa nhiều cấu trúc nối tiếp, có thể dùng base offset khác khi đúng bounds/alignment.

VarHandle kết thúc path tại **ValueLayout** mới có scalar carrier. Truyền sai carrier type, số tọa độ hoặc thứ tự tọa độ có thể gây **WrongMethodTypeException**. **JAVA_BYTE** nhận byte, **JAVA_INT** nhận int, **JAVA_FLOAT** nhận float.

## 7. Chương trình runnable: StructLayout + UnionLayout + SequenceLayout

### File LayoutCompositionDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.UnionLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.MemoryLayout.PathElement.sequenceElement;

public class LayoutCompositionDemo {
    static final UnionLayout PAYLOAD = MemoryLayout.unionLayout(
            ValueLayout.JAVA_INT.withName("count"),
            ValueLayout.JAVA_FLOAT.withName("ratio")
    ).withName("payload");

    static final StructLayout ROW = MemoryLayout.structLayout(
            ValueLayout.JAVA_BYTE.withName("kind"),
            MemoryLayout.paddingLayout(3),
            PAYLOAD
    ).withName("Row");

    static final SequenceLayout ROWS =
            MemoryLayout.sequenceLayout(3, ROW).withName("rows");

    static final StructLayout TABLE = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("length"),
            ROWS
    ).withName("Table");

    static final VarHandle LENGTH =
            TABLE.varHandle(groupElement("length"));
    static final VarHandle KIND =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("kind"));
    static final VarHandle COUNT =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("payload"),
                    groupElement("count"));
    static final VarHandle RATIO =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("payload"),
                    groupElement("ratio"));

    public static void main(String[] args) {
        System.out.println("row size = " + ROW.byteSize());
        System.out.println("row alignment = " + ROW.byteAlignment());
        System.out.println("table size = " + TABLE.byteSize());
        System.out.println("table alignment = " + TABLE.byteAlignment());

        long payloadOffset = ROW.byteOffset(
                groupElement("payload"));
        long secondCountOffset = TABLE.byteOffset(
                groupElement("rows"),
                sequenceElement(1),
                groupElement("payload"),
                groupElement("count"));

        System.out.println("row payload offset = " + payloadOffset);
        System.out.println("row[1] count offset = " + secondCountOffset);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment table = arena.allocate(TABLE);

            LENGTH.set(table, 0L, 3);

            KIND.set(table, 0L, 0L, (byte) 1);
            COUNT.set(table, 0L, 0L, 99);

            KIND.set(table, 0L, 1L, (byte) 2);
            RATIO.set(table, 0L, 1L, 1.5f);

            KIND.set(table, 0L, 2L, (byte) 1);
            COUNT.set(table, 0L, 2L, 5);

            System.out.println("length = "
                    + (int) LENGTH.get(table, 0L));
            System.out.println("row 0 count = "
                    + (int) COUNT.get(table, 0L, 0L));
            System.out.println("row 1 ratio = "
                    + (float) RATIO.get(table, 0L, 1L));
            System.out.println("row 2 count = "
                    + (int) COUNT.get(table, 0L, 2L));

            // Bit pattern IEEE-754 của float 1.0f.
            COUNT.set(table, 0L, 2L, 0x3f800000);
            System.out.println("row 2 float view = "
                    + (float) RATIO.get(table, 0L, 2L));
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 22+ (không cần preview flags cho các API này):

~~~bash
javac LayoutCompositionDemo.java
java LayoutCompositionDemo
~~~

Stdout:

~~~text
row size = 8
row alignment = 4
table size = 28
table alignment = 4
row payload offset = 4
row[1] count offset = 16
length = 3
row 0 count = 99
row 1 ratio = 1.5
row 2 count = 5
row 2 float view = 1.0
~~~

**Phân tích kết quả:**

- **ROW** gồm 1 byte kind, 3 byte padding và 4 byte union: size 8, alignment 4.
- **ROWS** chứa 3 ROW: size 24; **TABLE** chứa length 4 + ROWS 24: size 28.
- **row[1].payload.count** có offset 4 + 8 + 4 = 16.
- **COUNT** và **RATIO** đọc cùng bytes. Ghi 0x3f800000 rồi đọc dạng Java float cho giá trị 1.0f.
- **Arena.ofConfined** giữ native allocation sống trong try-with-resources; khi kết thúc khối, memory được giải phóng. Layout không tự thay đổi vòng đời của segment.

Ví dụ chỉ thao tác memory bằng FFM Java; không yêu cầu native library riêng. Muốn dùng layout này để gọi C library thật phải **kiểm tra khớp ABI**, không chỉ tin output của chương trình Java.

## 8. Kiểm chứng kích thước, alignment và offset bằng C compiler

Cùng layout bên C, viết chương trình C11 độc lập:

### File check_layout.c

~~~c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef union {
    int32_t count;
    float ratio;
} Payload;

typedef struct {
    uint8_t kind;
    Payload payload;
} Row;

typedef struct {
    int32_t length;
    Row rows[3];
} Table;

int main(void) {
    printf("Payload: size=%zu align=%zu\n",
           sizeof(Payload), _Alignof(Payload));

    printf("Row: size=%zu align=%zu payload=%zu\n",
           sizeof(Row), _Alignof(Row),
           offsetof(Row, payload));

    printf("Table: size=%zu align=%zu rows=%zu\n",
           sizeof(Table), _Alignof(Table),
           offsetof(Table, rows));

    printf("row[1].payload.count offset=%zu\n",
           offsetof(Table, rows)
             + sizeof(Row)
             + offsetof(Row, payload)
             + offsetof(Payload, count));

    return 0;
}
~~~

Biên dịch/chạy trên Linux với C11 compiler:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic check_layout.c -o check_layout
./check_layout
~~~

Trên ABI x86-64 thông thường, khi Payload/Row/Table đáp ứng giả định:

~~~text
Payload: size=4 align=4
Row: size=8 align=4 payload=4
Table: size=28 align=4 rows=4
row[1].payload.count offset=16
~~~

Đây là **output có điều kiện theo ABI**, không cam kết cho mọi compiler, architecture hoặc cờ packing. Nếu C trả con số khác Java layout thì phải sửa lại layout, điều kiện build hoặc ABI mapping.

Có thể đặt **_Static_assert** trong native library để bắt ABI thay đổi:

~~~c
/* Fragment C11 đặt sau typedef đã khai báo. */
_Static_assert(sizeof(Row) == 8, "Row size changed");
_Static_assert(offsetof(Row, payload) == 4,
               "payload offset changed");
_Static_assert(sizeof(Table) == 28, "Table size changed");
~~~

Kiểm thử bằng C compiler thực tế rất quan trọng vì Java không tự biết compiler C đã sử dụng packing, anonymous members hoặc typedef nào khi xây native library.

## 9. Vì sao padding là điều kiện thiết yếu của mảng struct?

Thử một struct có dữ liệu 5 byte nhưng alignment 4:

~~~c
struct Tail {
    int32_t number;
    unsigned char state;
};
~~~

Một C compiler x86-64 điển hình đặt number tại offsets 0..3, state tại offset 4, rồi thêm tail padding 3 byte, làm **sizeof(Tail)=8**. Một array **Tail[2]** có phần tử thứ hai bắt đầu ở offset 8. Nếu Java mô tả chỉ size 5, nó sẽ tính sai stride.

Chương trình Java chứng minh quy tắc alignment khi tạo StructLayout:

### File PaddingCheck.java

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public class PaddingCheck {
    public static void main(String[] args) {
        try {
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE,
                    ValueLayout.JAVA_INT);
            System.out.println("unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("misaligned struct rejected");
        }

        StructLayout padded = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE,
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT);

        System.out.println("padded size = " + padded.byteSize());
        System.out.println("padded alignment = "
                + padded.byteAlignment());
    }
}
~~~

Lưu **PaddingCheck.java**, chạy:

~~~bash
javac PaddingCheck.java
java PaddingCheck
~~~

Stdout:

~~~text
misaligned struct rejected
padded size = 8
padded alignment = 4
~~~

Không tự hạ alignment để tránh exception nếu native không dùng packed struct: đó chỉ khiến Java chấp nhận một layout có thể sai.

## 10. Ánh xạ kiểu C theo ABI: JAVA_LONG không luôn là C long

C có data model khác nhau theo hệ điều hành:

| C scalar | Ghi chú |
| --- | --- |
| **char** | Một C byte, signedness của plain char phụ thuộc implementation |
| **short** | Thường 2 byte |
| **int** | Thường 4 byte, Java int cố định 4 byte |
| **long** | Linux x64 LP64 thường 8 byte; Windows x64 LLP64 thường 4 byte |
| **long long** | Thường 8 byte |
| **size_t** | Phụ thuộc độ rộng địa chỉ/data model |
| **void*** | Địa chỉ, không phải dữ liệu được trỏ đến |
| **float/double** | Cần kiểm tra size, alignment, representation |

Ví dụ:

~~~c
struct NativeCounter {
    long count;
    void *data;
};
~~~

Không nên mặc định **JAVA_LONG** tương đương C long trên Windows x64. FFM **Linker.nativeLinker().canonicalLayouts()** cung cấp mapping scalar type theo native ABI.

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.util.Map;

Map<String, MemoryLayout> canonical =
        Linker.nativeLinker().canonicalLayouts();

MemoryLayout cInt = canonical.get("int");
MemoryLayout cLong = canonical.get("long");
MemoryLayout cSizeT = canonical.get("size_t");
MemoryLayout cPointer = canonical.get("void*");
~~~

Đây là fragment, không phải chương trình độc lập; một số thao tác linker có thể yêu cầu native-access configuration tùy JDK. Không ép một canonical layout về kiểu carrier Java cố định khi chưa xác minh. Native linker thường bảo đảm các canonical types **bool, char, short, int, long, long long, float, double, size_t, wchar_t, void***.

**Canonical layouts không tự tạo padding cho struct và union.** Bạn phải xem compiler/ABI và tổng hợp layout đúng. Với C aggregate truyền **by value** qua downcall, FunctionDescriptor còn phải hợp lệ với calling convention và quy tắc ABI; một layout đọc bytes đúng chưa đủ để khẳng định truyền struct by value là portable.

## 11. Pointer member khác array inline

C:

~~~c
struct BufferPointer {
    int32_t length;
    unsigned char *data;
};

struct BufferInline {
    int32_t length;
    unsigned char data[16];
};
~~~

**BufferPointer.data** là một giá trị địa chỉ, cần **AddressLayout** theo native pointer ABI. Nó không chứa các bytes của vùng dữ liệu đích trong chính struct. **BufferInline.data** là 16 byte nằm ngay trong struct, cần **SequenceLayout**.

| Member C | Cách mô hình hóa | Nội dung thực |
| --- | --- | --- |
| **char *p** | AddressLayout | Một địa chỉ tới vùng khác |
| **char p[16]** | sequenceLayout(16, JAVA_BYTE) | 16 byte inline |
| **struct Row *rows** | AddressLayout, có thể có target layout | Con trỏ tới Row |
| **struct Row rows[3]** | sequenceLayout(3, ROW) | Ba Row inline |

Con trỏ đọc từ native có thể null, dangling hoặc có bounds chưa được biết; không dereference địa chỉ không tin cậy. Có target layout không tự bảo đảm memory đích còn sống hoặc đủ bytes.

## 12. Flexible array member với số phần tử runtime

C99 cho phép:

~~~c
struct Packet {
    int32_t length;
    uint8_t payload[];
};
~~~

Độ dài payload phụ thuộc instance được cấp phát. Có thể mô tả phần cố định và member sequence rỗng:

~~~java
StructLayout PACKET = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("length"),
        MemoryLayout.sequenceLayout(0, ValueLayout.JAVA_BYTE)
                .withName("payload")
);
~~~

**sequenceLayout(0, ...)** có size 0; nó không chứa dữ liệu runtime. Khi nhận segment thực, phải đọc length, kiểm tra dữ liệu, rồi tạo view hợp lệ:

~~~java
long start = PACKET.byteOffset(
        MemoryLayout.PathElement.groupElement("payload"));
long length = Integer.toUnsignedLong(rawLength);

if (start > segment.byteSize()
        || length > segment.byteSize() - start) {
    throw new IllegalArgumentException("invalid payload length");
}

MemorySegment data = segment.asSlice(start, length);
~~~

Đoạn trên là fragment, giả định **rawLength** đã được đọc từ header và **segment** chứa vùng memory được cấp phát. Kiểm tra bằng phép trừ giúp tránh overflow của cộng offset + length. C standard cũng có quy tắc padding đặc biệt quanh flexible array member; nếu cần ánh xạ bằng header C thật, hãy xác minh **offsetof(payload)** thay vì chỉ đoán.

Với mảng struct dài theo runtime, **MemoryLayout.arrayElementVarHandle(...)** có thể truy cập các element dựa trên stride của element layout mà không cần khai báo SequenceLayout count cố định. Nó vẫn chịu bounds của MemorySegment.

## 13. Byte order, unsigned values và C bitfield

### Endianness

Java **ValueLayout.JAVA_INT** dùng native byte order. Nếu bytes là một protocol big-endian cố định, cần layout có byte order rõ ràng:

~~~java
import java.nio.ByteOrder;
import java.lang.foreign.ValueLayout;

ValueLayout.OfInt NETWORK_INT =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
~~~

Đây là fragment. Với C struct nội bộ của native library trong cùng tiến trình, thường dùng native order theo ABI; đừng đổi thành big-endian trừ khi định nghĩa dữ liệu yêu cầu.

### Unsigned C

Java byte/short/int/long là signed; C còn có unsigned. Khi C lưu **uint32_t**, layout 4 byte của Java int vẫn biểu diễn được các bits, nhưng chuyển sang **long** để xử lý giá trị unsigned:

~~~java
int raw = -1;  // bit pattern 0xFFFFFFFF
long value = Integer.toUnsignedLong(raw);
System.out.println(value); // 4294967295
~~~

Đây là fragment. Đừng chọn layout 8 byte chỉ vì muốn biểu diễn uint32_t dương: bên C thực tế chỉ lưu 4 byte.

### Bitfield/enum

C bitfields có quy tắc cấp phát/bit order phụ thuộc compiler và ABI, không tự được mô tả chính xác như các field thông thường trong MemoryLayout. C enum cũng có underlying type có thể phụ thuộc compiler flags. Hãy dùng generated bindings hoặc lưu underlying storage units đã xác minh rồi xử lý bằng masks/shifts; không tự mặc định mỗi bitfield là JAVA_INT độc lập.

### Union và reinterpretation

Một C union có tag cho biết member active. Java **VarHandle** có thể nhìn bytes theo nhiều value layout, nhưng điều đó **không tự thực hiện numeric conversion** và không xác nhận mọi C union type-punning portable.

## 14. Quyền truy cập và lifetime không nằm trong StructLayout

Layout mô tả byte arrangement, nhưng **MemorySegment** mới áp dụng:

- **Bounds:** segment có đủ bytes cho field không? Sai thì **IndexOutOfBoundsException**.
- **Alignment:** địa chỉ root/member phù hợp byteAlignment chưa? Sai có thể **IllegalArgumentException**.
- **Read-only:** không thể set qua read-only segment.
- **Liveness:** arena đã đóng thì native segment không còn hợp lệ, thường **IllegalStateException**.
- **Thread confinement:** segment từ **Arena.ofConfined()** chỉ dành cho owner thread, sai thread có thể **WrongThreadException**.

**Arena.ofShared()** cho phép truy cập từ nhiều thread nhưng không tự bảo đảm dữ liệu không có race. Cần synchronization/happens-before cho trường hợp nhiều thread cùng đọc/ghi backing memory.

Có thể lấy offset của nested layout rồi gọi **MemorySegment.asSlice** để trao đúng vùng con cho component khác. Slice chia sẻ bytes với segment gốc, không có allocation và lifetime độc lập; không được dùng slice sau khi arena sở hữu đã đóng.

## 15. Khi nào phải dùng jextract hoặc kiểm thử ABI tự động?

Với một C header thật có nhiều typedef, struct lồng, pointer, union, anonymous member, alignment đặc biệt hoặc function signature by-value, việc viết tay tất cả các offset có thể gây lỗi khó phát hiện. Quy trình khuyến nghị:

1. Xác định đúng C header và compiler flags mà native library dùng.
2. Đo **sizeof**, **_Alignof**, **offsetof** bằng C compiler cùng ABI.
3. Truy vấn canonical scalar layouts thay vì hard-code kiểu dễ biến đổi.
4. Chèn padding rõ ràng, gồm tail padding.
5. Kiểm tra byteSize, byteAlignment, byteOffset bên Java.
6. Test VarHandle và segment trên cùng bộ dữ liệu có giá trị mong đợi.
7. Thực hiện native integration test ở từng platform hỗ trợ.
8. Với header phức tạp, ưu tiên **jextract** sinh FFM binding và so sánh output với phép đo C.

Không có việc Java layout tự động biết C compiler đã bật packed mode hay đổi underlying enum size.

## 16. Bảng các lỗi hay gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| StructLayout tự thêm padding | Offset sai hoặc tạo layout thất bại | Thêm paddingLayout theo ABI |
| Quên tail padding | Sai stride của struct array | So sizeof và byteSize |
| Union có hai vùng riêng | Ghi member này làm đổi bytes của member kia | Dùng tag, hiểu overlapping storage |
| Cộng size các union member | Size sai | Dùng max member size, xét ABI rounding |
| Sequence như Java object array | Sai storage model | Sequence biểu diễn contiguous bytes |
| Dùng số thứ tự element làm byte offset | Đọc sai vị trí | Tính stride hoặc dùng VarHandle path |
| groupElement(index) bỏ qua padding | Chọn sai member | Dùng groupElement(name) khi có thể |
| Map C long thành JAVA_LONG luôn | Sai LLP64 Windows | canonical layouts + C kiểm chứng |
| Bỏ qua pack và ABI | Offset C khác Java | Kiểm tra compiler flags |
| Đọc pointer như bytes inline | Sai vùng nhớ/bounds | Dùng AddressLayout |
| Chọn group thay ValueLayout trong varHandle | Không có scalar carrier | Path tới value hoặc dùng slice |
| Dùng after Arena.close() | Truy cập vùng nhớ đã hết hạn | Quản lý arena lifecycle |
| Dùng confined segment ở thread khác | WrongThreadException | Đúng owner thread hoặc shared arena |
| Không kiểm thử offsetof | Java tự chạy được nhưng C không khớp | Kiểm chứng native compiler |
| Dùng FunctionDescriptor pointer cho C by-value struct | Sai calling convention | ABI-compatible group layout |

## 17. Câu hỏi và bài tập

**Câu 1.** C struct có một char rồi một int; vì sao java **structLayout(JAVA_BYTE, JAVA_INT)** không hợp lệ khi int alignment 4?

**Đáp án:** Int ở offset 1. StructLayout không tự thêm padding; cần chèn 3 byte hoặc mô tả packed ABI đúng thực tế.

**Câu 2.** Union gồm JAVA_INT và JAVA_FLOAT có kích thước bao nhiêu?

**Đáp án:** 4 byte và cả hai member có offset 0; không cộng thành 8.

**Câu 3.** Sequence gồm 3 Point size 8. Element offsets và tổng byteSize?

**Đáp án:** 0, 8, 16; tổng 24 byte.

**Câu 4.** Trong Table mẫu, **rows[2].payload.ratio** tại offset nào?

**Đáp án:** **4 + 2×8 + 4 = 24** byte từ đầu Table.

**Câu 5.** C struct int + char thường có size 8 dù tổng data chỉ 5 byte vì sao?

**Đáp án:** Tail padding để sizeof là bội số alignment của struct, đảm bảo stride array.

**Câu 6.** C long trên Windows x64 có thể dùng JAVA_LONG không cần kiểm tra?

**Đáp án:** Không. LLP64 thường có C long 4 byte, Java long 8 byte; dùng mapping ABI đúng.

**Câu 7.** Nếu Java đọc union ratio sau khi C vừa ghi count, có nhận số count được chuyển đổi thành float không?

**Đáp án:** Không. Java đọc cùng bit pattern dưới float layout; không phải numeric conversion.

**Câu 8.** **AddressLayout** cho pointer có tự đại diện các bytes của object được trỏ tới không?

**Đáp án:** Không. Nó chỉ mô tả địa chỉ; bounds/lifetime và dữ liệu đích cần contract riêng.

**Bài tập A:** Đổi ROW từ **kind, padding(3), PAYLOAD** sang **PAYLOAD, kind, padding(3)**. Tính offset kind (4), payload (0), size (8), alignment (4).

**Bài tập B:** Dùng **MemoryLayout.sequenceLayout(10, ROW)**; tính offset payload của Row index 7: **7×8+4=60**.

**Bài tập C:** Trong C, thêm **_Static_assert(offsetof(Row,payload)==4)** và thử một compiler mode packed. Giải thích khi assert thất bại.

**Bài tập D:** Tạo union gồm int32 và 4 bytes; ghi số 0x01020304, quan sát thứ tự bytes và giải thích byte order của máy.

## Tài liệu tham khảo

- Java SE 22 — **MemoryLayout**, structLayout, unionLayout, sequenceLayout, paddingLayout và layout paths: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html
- Java SE 22 — **StructLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html
- Java SE 22 — **UnionLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/UnionLayout.html
- Java SE 22 — **SequenceLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SequenceLayout.html
- Java SE 22 — **Linker** và canonical layouts của C ABI: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle Java 22 — **Memory Layouts and Structured Access**: https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html
- OpenJDK **JEP 454: Foreign Function & Memory API**: https://openjdk.org/jeps/454

**Kết luận:** **StructLayout nối tiếp member và đòi hỏi padding tường minh; UnionLayout chồng lấn member; SequenceLayout lặp element theo stride = element byteSize**. Khi ánh xạ sang C thực tế, phải khớp ABI, sizeof, offsetof, alignment, scalar type, byte order và lifetime; chỉ tên layout đúng chưa đủ để bảo đảm interoperability.
