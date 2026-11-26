# MemoryLayout, StructLayout và SequenceLayout để mô tả cấu trúc dữ liệu native

## Mục tiêu

Khi làm việc với Foreign Function & Memory API (FFM), Java có thể đọc và ghi dữ liệu nằm ngoài Java heap thông qua `MemorySegment`. Với một vùng nhớ đơn giản, ta có thể truy cập từng giá trị bằng `ValueLayout`. Nhưng khi vùng nhớ chứa cấu trúc phức tạp như một `struct` trong C hoặc một mảng các cấu trúc, việc tự tính từng offset rất dễ sai và khó bảo trì.

`MemoryLayout` mô tả hình dạng của dữ liệu trong vùng nhớ. Ba khái niệm trọng tâm của bài học là:

- `MemoryLayout`: kiểu nền tảng để mô tả kích thước, căn chỉnh và cấu trúc dữ liệu.
- `StructLayout`: mô tả các thành viên khác kiểu được đặt nối tiếp nhau, tương tự `struct` trong C.
- `SequenceLayout`: mô tả một phần tử được lặp lại nhiều lần, tương tự mảng native.

FFM API đã là API chính thức từ JDK 22 theo JEP 454 và tiếp tục là API hiện hành trong Java SE 27. Các ví dụ trong bài sử dụng API ổn định, không cần bật preview.

## MemoryLayout mô tả điều gì?

Một memory layout mô tả cách diễn giải các byte trong một `MemorySegment`. Layout cung cấp thông tin để chương trình biết:

- Giá trị có kích thước bao nhiêu byte.
- Vùng nhớ yêu cầu căn chỉnh ở mức nào.
- Các trường nằm ở offset nào.
- Một cấu trúc gồm những thành viên nào.
- Một phần tử được lặp lại bao nhiêu lần.

Các layout là đối tượng bất biến và có thể tái sử dụng. Thông thường, nên khai báo layout dùng chung thành hằng `static final`.

### Các loại layout thường gặp

| Loại | Mục đích | Ví dụ |
|---|---|---|
| `ValueLayout` | Mô tả một giá trị đơn như số nguyên, số thực hoặc địa chỉ | `ValueLayout.JAVA_INT` |
| `PaddingLayout` | Mô tả các byte đệm không mang dữ liệu ứng dụng | `MemoryLayout.paddingLayout(3)` |
| `StructLayout` | Mô tả các thành viên khác kiểu được đặt nối tiếp | `MemoryLayout.structLayout(...)` |
| `SequenceLayout` | Mô tả một layout phần tử lặp lại theo số lượng xác định | `MemoryLayout.sequenceLayout(10, elementLayout)` |
| `UnionLayout` | Mô tả các thành viên dùng chung offset bắt đầu, tương tự `union` trong C | `MemoryLayout.unionLayout(...)` |

`StructLayout` và `SequenceLayout` đều là các dạng `MemoryLayout` phức hợp. Bài này tập trung vào cấu trúc và mảng, nên không đi sâu vào `UnionLayout`.

## Kích thước và căn chỉnh

Hai thuộc tính cần kiểm tra khi mô tả dữ liệu native là:

- `byteSize()`: tổng kích thước layout, tính bằng byte.
- `byteAlignment()`: yêu cầu căn chỉnh của layout, tính bằng byte.

Ví dụ:

~~~java
long intSize = ValueLayout.JAVA_INT.byteSize();       // 4
long intAlignment = ValueLayout.JAVA_INT.byteAlignment(); // 4
~~~

Với các value layout tiêu chuẩn, kích thước và căn chỉnh tự nhiên thường tương ứng với kiểu Java. Chẳng hạn `JAVA_INT` có kích thước 4 byte và căn chỉnh 4 byte. Kích thước của `ValueLayout.ADDRESS` phụ thuộc nền tảng vì con trỏ có thể có kích thước khác nhau trên các kiến trúc khác nhau.

Căn chỉnh là yêu cầu về địa chỉ bắt đầu của dữ liệu. Ví dụ, layout có căn chỉnh 4 byte yêu cầu địa chỉ truy cập là bội số của 4. Căn chỉnh phù hợp có thể ảnh hưởng đến hiệu năng và những kiểu truy cập mà `VarHandle` hỗ trợ.

## StructLayout: mô tả một cấu trúc gồm nhiều trường

`StructLayout` biểu diễn một nhóm thành viên được đặt nối tiếp nhau. Mỗi thành viên có thể là một `ValueLayout`, một `SequenceLayout`, một `StructLayout` khác hoặc một layout phức hợp khác.

Ví dụ, cấu trúc C sau có hai trường số nguyên:

~~~c
struct Point {
    int x;
    int y;
};
~~~

Có thể mô tả cấu trúc này bằng Java:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

static final StructLayout POINT = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("x"),
    ValueLayout.JAVA_INT.withName("y")
).withName("Point");
~~~

Hai thành viên được đặt theo thứ tự khai báo:

| Thành viên | Offset | Kích thước |
|---|---:|---:|
| `x` | 0 | 4 byte |
| `y` | 4 | 4 byte |

Vì vậy, `POINT.byteSize()` bằng 8 byte và `POINT.byteAlignment()` bằng 4 byte.

### Đặt tên cho thành viên

`withName("x")` gắn tên cho layout của một trường. Tên này có thể được dùng trong layout path để chọn trường cần truy cập:

~~~java
long yOffset = POINT.byteOffset(
    MemoryLayout.PathElement.groupElement("y")
); // 4
~~~

Tên trường giúp code diễn đạt theo cấu trúc dữ liệu thay vì phải nhớ các offset số học. Nếu không cần truy cập theo tên, có thể chọn thành viên bằng chỉ số thông qua `groupElement(long)`.

### StructLayout không tự chèn padding theo ABI

Đây là điểm rất quan trọng khi mô tả cấu trúc C. `structLayout(...)` đặt các thành viên nối tiếp và kích thước của struct bằng tổng kích thước các thành viên. API không tự suy luận rồi chèn các khoảng đệm giống quy tắc của một compiler C cụ thể.

Ví dụ, xét cấu trúc C:

~~~c
#include <stdint.h>

struct TaggedValue {
    int8_t kind;
    int32_t value;
};
~~~

Trên ABI phổ biến có căn chỉnh `int8_t` là 1 byte và `int32_t` là 4 byte, compiler thường đặt `value` tại offset 4. Ba byte đệm xuất hiện giữa hai trường. Có thể mô tả khoảng đệm đó tường minh:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

static final StructLayout TAGGED_VALUE = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("value")
).withName("TaggedValue");
~~~

Layout có các vị trí sau:

| Thành phần | Offset bắt đầu | Kích thước |
|---|---:|---:|
| `kind` | 0 | 1 byte |
| padding | 1 | 3 byte |
| `value` | 4 | 4 byte |

Tổng kích thước là 8 byte. Căn chỉnh tự nhiên của struct là 4 byte vì thành viên có yêu cầu căn chỉnh lớn nhất là `JAVA_INT`.

Padding ở cuối struct cũng có thể cần thiết để kích thước mỗi phần tử trong mảng thỏa mãn căn chỉnh của struct. Ví dụ minh họa sau mô tả một cấu trúc có `int8_t tag`, `int32_t count`, `int16_t flags`, theo ABI phổ biến có căn chỉnh tương ứng 1, 4 và 2 byte:

~~~java
static final StructLayout RECORD = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("tag"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("count"),
    ValueLayout.JAVA_SHORT.withName("flags"),
    MemoryLayout.paddingLayout(2)
).withName("Record");
~~~

Các offset lần lượt là 0, 4 và 8; tổng kích thước là 12 byte. Padding cuối giữ cho kích thước phần tử là bội số của căn chỉnh 4 byte. Đây là ví dụ theo một ABI cụ thể, không phải quy tắc kích thước struct áp dụng cho mọi nền tảng.

Khi tích hợp với thư viện native, hãy xác định đúng ABI, compiler, kiến trúc và khai báo C thực tế. Quy tắc padding và căn chỉnh có thể khác giữa các nền tảng hoặc cấu hình compiler. Không nên suy luận layout native chỉ từ tên kiểu Java.

Nếu trường C dùng kiểu unsigned như `uint8_t` hoặc `uint16_t`, layout vẫn mô tả đúng số byte bằng `JAVA_BYTE` hoặc `JAVA_SHORT`, nhưng carrier Java tương ứng là kiểu có dấu. Khi cần giá trị số không dấu, hãy chuyển đổi bằng `Byte.toUnsignedInt(...)` hoặc `Short.toUnsignedInt(...)` sau khi đọc.

## SequenceLayout: mô tả mảng các phần tử cùng kiểu

`SequenceLayout` mô tả một layout phần tử được lặp lại theo một số lượng xác định. Cách tạo cơ bản:

~~~java
SequenceLayout integers =
    MemoryLayout.sequenceLayout(10, ValueLayout.JAVA_INT);
~~~

Layout trên mô tả 10 số nguyên liên tiếp. Mỗi phần tử có kích thước 4 byte, nên toàn bộ sequence có kích thước 40 byte.

Các phương thức hữu ích:

- `elementLayout()`: lấy layout của một phần tử.
- `elementCount()`: lấy số lượng phần tử.
- `withElementCount(n)`: tạo layout mới với số lượng phần tử khác.
- `byteSize()`: lấy tổng kích thước của sequence.

Có thể mô tả mảng hai chiều bằng sequence lồng nhau:

~~~java
SequenceLayout matrix = MemoryLayout.sequenceLayout(
    3,
    MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_DOUBLE)
);
~~~

Đây là mảng gồm 3 hàng, mỗi hàng có 4 giá trị `double`. Tổng kích thước là 3 × 4 × 8 = 96 byte.

### Mảng các struct

Khi kết hợp `SequenceLayout` với `StructLayout`, ta có thể mô tả một mảng các cấu trúc native:

~~~java
static final SequenceLayout POINTS =
    MemoryLayout.sequenceLayout(10, POINT).withName("points");
~~~

Nếu `POINT` có kích thước 8 byte, `POINTS` có kích thước 80 byte. Mỗi phần tử của sequence là một struct Point gồm hai trường `x` và `y`.

Có thể kiểm tra offset của trường `y` trong phần tử thứ ba (chỉ số 2):

~~~java
long offset = POINTS.byteOffset(
    MemoryLayout.PathElement.sequenceElement(2),
    MemoryLayout.PathElement.groupElement("y")
); // 2 * 8 + 4 = 20
~~~

Layout path bắt đầu từ sequence, chọn phần tử thứ ba, rồi chọn thành viên có tên `y`. Nhờ đó, code không phải tự tính offset bằng các phép nhân và cộng rải rác.

## Truy cập trường bằng VarHandle và layout path

`MemoryLayout.varHandle(...)` tạo một `VarHandle` để đọc hoặc ghi trường được chọn trong layout. Layout path mô tả đường đi qua cấu trúc:

- `PathElement.sequenceElement()`: chọn một phần tử bất kỳ trong sequence; chỉ số sẽ được truyền khi gọi VarHandle.
- `PathElement.sequenceElement(index)`: chọn phần tử tại chỉ số cố định.
- `PathElement.groupElement("field")`: chọn thành viên trong struct hoặc group theo tên.

Ví dụ dưới đây tạo các VarHandle để truy cập `x` và `y` của từng phần tử trong mảng Point:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.MemoryLayout.PathElement.sequenceElement;

static final VarHandle X_HANDLE = POINTS.varHandle(
    sequenceElement(),
    groupElement("x")
);

static final VarHandle Y_HANDLE = POINTS.varHandle(
    sequenceElement(),
    groupElement("y")
);
~~~

Do `sequenceElement()` là path element mở, VarHandle có các tọa độ `MemorySegment`, offset cơ sở và chỉ số phần tử. Có thể dùng nó như sau:

~~~java
X_HANDLE.set(segment, 0L, 2L, 100);
int x = (int) X_HANDLE.get(segment, 0L, 2L);
~~~

Trong đó:

- `segment` là vùng nhớ chứa mảng Point.
- `0L` là offset cơ sở trong segment.
- `2L` là chỉ số phần tử trong sequence.
- `100` là giá trị cần ghi vào trường `x`.

Có thể khai báo VarHandle thành `static final` để tái sử dụng, thay vì tạo lại handle trong mỗi lần đọc hoặc ghi.

## Ví dụ hoàn chỉnh: cấp phát và truy cập mảng Point native

Ví dụ sau tạo một vùng nhớ ngoài heap cho 10 struct Point, ghi hai tọa độ và đọc chúng lại. Layout được khai báo một lần, còn vòng đời bộ nhớ do `Arena` quản lý.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.MemoryLayout.PathElement.sequenceElement;

public class PointArrayExample {

    private static final StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
    ).withName("Point");

    private static final SequenceLayout POINTS =
        MemoryLayout.sequenceLayout(10, POINT).withName("points");

    private static final VarHandle X_HANDLE =
        POINTS.varHandle(sequenceElement(), groupElement("x"));

    private static final VarHandle Y_HANDLE =
        POINTS.varHandle(sequenceElement(), groupElement("y"));

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(POINTS);

            for (long i = 0; i < POINTS.elementCount(); i++) {
                X_HANDLE.set(segment, 0L, i, (int) i);
                Y_HANDLE.set(segment, 0L, i, (int) (i * 10));
            }

            for (long i = 0; i < POINTS.elementCount(); i++) {
                int x = (int) X_HANDLE.get(segment, 0L, i);
                int y = (int) Y_HANDLE.get(segment, 0L, i);
                System.out.printf("Point(%d): x=%d, y=%d%n", i, x, y);
            }
        }
    }
}
~~~

Kết quả:

~~~text
Point(0): x=0, y=0
Point(1): x=1, y=10
Point(2): x=2, y=20
Point(3): x=3, y=30
Point(4): x=4, y=40
Point(5): x=5, y=50
Point(6): x=6, y=60
Point(7): x=7, y=70
Point(8): x=8, y=80
Point(9): x=9, y=90
~~~

Trong ví dụ:

1. `POINT` mô tả một struct gồm hai số nguyên.
2. `POINTS` mô tả 10 struct liên tiếp.
3. Hai VarHandle chọn trường theo layout path, không cần tự tính offset.
4. `arena.allocate(POINTS)` cấp phát đủ số byte và căn chỉnh theo layout.
5. Khi thoát khỏi khối `try`, arena đóng và vùng nhớ được giải phóng; không tiếp tục sử dụng segment sau thời điểm đó.

Ví dụ dùng `Arena.ofConfined()` vì toàn bộ thao tác đọc/ghi diễn ra trên cùng luồng. Nếu cần chia sẻ segment cho nhiều luồng, hãy chọn arena có phạm vi chia sẻ phù hợp và tuân thủ các quy tắc đồng bộ dữ liệu.

## Phân biệt StructLayout và SequenceLayout

| Tiêu chí | StructLayout | SequenceLayout |
|---|---|---|
| Hình dạng | Nhóm các thành viên có thể khác kiểu | Lặp lại một layout phần tử |
| Thứ tự | Thành viên nằm nối tiếp nhau | Phần tử nằm liên tiếp theo chỉ số |
| Kích thước | Tổng kích thước các thành viên, bao gồm padding được khai báo | Kích thước phần tử nhân số lượng |
| Tương đương thường gặp trong C | `struct` | Mảng |
| Truy cập theo tên | Có thể dùng `groupElement("field")` | Không có tên trường riêng; chọn phần tử bằng `sequenceElement` |
| Kết hợp | Có thể chứa sequence hoặc struct khác | Có thể lặp lại struct hoặc sequence khác |

Trong thực tế, hai loại layout thường được kết hợp: `StructLayout` mô tả một bản ghi, còn `SequenceLayout` mô tả một mảng các bản ghi đó.

## Những lưu ý khi mô tả dữ liệu native

- **Khớp ABI:** Kích thước kiểu C, căn chỉnh và padding phụ thuộc nền tảng, compiler và ABI. Kiểm tra header, tài liệu thư viện hoặc mã binding được sinh từ header.
- **Padding tường minh:** Thêm `MemoryLayout.paddingLayout(n)` tại đúng vị trí khi cấu trúc native có khoảng đệm. Đừng giả định `structLayout` tự chèn padding.
- **Căn chỉnh:** Kiểm tra `byteAlignment()` và offset của các trường. Có thể dùng `withByteAlignment(n)` để mô tả ràng buộc căn chỉnh cần thiết; phương thức này không tự chèn byte đệm.
- **Kiểu địa chỉ:** `ValueLayout.ADDRESS` có kích thước phụ thuộc nền tảng. Không mặc định mọi con trỏ đều có kích thước cố định trên mọi kiến trúc.
- **Byte order:** Với dữ liệu native, dùng đúng byte order của ABI. Khi đọc định dạng nhị phân có quy định byte order riêng, có thể tạo value layout bằng `withOrder(ByteOrder.BIG_ENDIAN)` hoặc `withOrder(ByteOrder.LITTLE_ENDIAN)`.
- **Bounds và lifetime:** Layout mô tả cấu trúc, nhưng không thay thế các kiểm tra phạm vi và vòng đời của `MemorySegment`. Segment vẫn chịu giới hạn kích thước và thời gian sống của arena.
- **Không nhầm layout với đối tượng Java:** `StructLayout` không tạo ra một object Java hay tự chuyển đổi dữ liệu thành record/class. Nó chỉ mô tả cách diễn giải byte trong segment.

## Chọn layout theo cấu trúc dữ liệu

| Dữ liệu cần mô tả | Cách xây dựng |
|---|---|
| Một số nguyên native | `ValueLayout.JAVA_INT` |
| Một struct có trường `x`, `y` | `MemoryLayout.structLayout(...)` |
| Một mảng 100 số nguyên | `MemoryLayout.sequenceLayout(100, ValueLayout.JAVA_INT)` |
| Một mảng 10 struct Point | `MemoryLayout.sequenceLayout(10, POINT)` |
| Ma trận 3 × 4 số thực double | Sequence lồng nhau |
| Struct có khoảng đệm giữa các trường | `structLayout` kết hợp `paddingLayout` |

## Tài liệu tham khảo

- [JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [MemoryLayout – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [StructLayout – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [SequenceLayout – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SequenceLayout.html)
- [ValueLayout – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [MemorySegment – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle Core Libraries Guide, Java SE 27 – Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/27/core/foreign-function-and-memory-api.html)

