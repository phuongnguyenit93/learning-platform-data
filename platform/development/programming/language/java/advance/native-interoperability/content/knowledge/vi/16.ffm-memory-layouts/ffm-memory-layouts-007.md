# Tạo VarHandle cho trường và phần tử cần truy cập lặp lại

## 1. Bài toán: một layout, hàng nghìn lần đọc và ghi

Trong Java Native Interoperability, nhất là **Foreign Function & Memory API (FFM)**, chúng ta thường nhận một vùng bộ nhớ native chứa dữ liệu có cấu trúc: `struct` C, mảng các record, ma trận hoặc buffer nhiều trường. Một thao tác đọc bằng offset thủ công có thể trông đơn giản:

~~~java
// Minh họa: mỗi record gồm hai int (x, y), mỗi int chiếm 4 byte.
int x = segment.get(ValueLayout.JAVA_INT, i * 8L);
int y = segment.get(ValueLayout.JAVA_INT, i * 8L + 4L);
~~~

Nhưng cách này đòi người đọc tự giữ đồng bộ **offset, alignment, stride, kiểu dữ liệu**. Khi thay đổi cấu trúc record, một hằng số `8` hoặc `4` có thể trở thành sai. Nếu nhiều method lặp cùng phép truy cập, logic địa chỉ bị sao chép ở nhiều chỗ.

**`MemoryLayout.varHandle(...)`** giải quyết bài toán: mô tả cấu trúc **một lần** bằng `MemoryLayout`, chỉ ra **đường dẫn tới trường** bằng `PathElement`, rồi tạo **`java.lang.invoke.VarHandle`** để đọc/ghi trường đó nhiều lần trên các `MemorySegment` khác nhau.

Với một mảng record, `PathElement.sequenceElement()` để mở cho **chỉ số tại thời điểm truy cập**. Một VarHandle duy nhất có thể truy cập record thứ 0, thứ 1, thứ 2... mà không cần tạo lại handle trong mỗi vòng lặp.

~~~text
MemoryLayout mô tả cấu trúc
        |
        | varHandle(layout path)
        v
VarHandle (được tạo một lần, có carrier + coordinates rõ ràng)
        |
        +---- get(segment, baseOffset, index)
        +---- set(segment, baseOffset, index, value)
        +---- get(segmentKhac, baseOffset, index)
        |
        v
Mỗi lần sử dụng: JVM tính offset từ layout,
kiểm tra phạm vi/đời sống/alignment và truy cập dữ liệu
~~~

Bài này hướng đến **JDK 22+**, khi FFM API trong `java.lang.foreign` chính thức ổn định (JEP 454). Các ví dụ chỉ thao tác memory trong Java, không cần C compiler hay `--enable-native-access`. Trên JDK 17, FFM còn ở incubator và **không** biên dịch với các import/chữ ký dưới đây.

### Mục tiêu học tập

- Hiểu mối quan hệ giữa `MemoryLayout`, `PathElement`, `MemorySegment` và `VarHandle`.
- Tạo handle cho **field** của `structLayout`, **element** của `sequenceLayout`, và field của mỗi record trong mảng.
- Phân biệt **đường dẫn cố định** và **đường dẫn mở**; truyền đúng các coordinate `long`.
- Viết ví dụ **Java 22+ chạy được**, kèm lệnh `javac`/`java` và stdout xác định.
- Dùng `arrayElementVarHandle` với mảng bản ghi có độ dài runtime, không cần tạo layout theo từng kích thước.
- Biết khi nào nên dùng `byteOffset`, `ValueLayout.varHandle()`, `asSlice` hay `MethodHandles.insertCoordinates`.
- Hiểu kiểm tra boundary, alignment, scope/thread, memory ordering và lý do cache handle để tái sử dụng.

## 2. Những khái niệm phải phân biệt

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `MemoryLayout` | Mô tả **hình dạng và bố trí byte** của dữ liệu | `structLayout(...)`, `sequenceLayout(...)` |
| `ValueLayout` | Một giá trị có carrier type, size, alignment, byte order | `ValueLayout.JAVA_INT` (4 bytes, carrier `int`) |
| `MemoryLayout.PathElement` | Một bước trong đường đi từ layout gốc tới layout con | `groupElement("x")`, `sequenceElement()` |
| `VarHandle` | Handle kiểu mạnh để đọc/ghi **một trường hoặc một họ vị trí** | `X.get(segment, 0L, 2L)` |
| `MemorySegment` | View lên một vùng nhớ có kích thước và scope/lifetime | `arena.allocate(layout)` |
| `Arena` | Cấp phát và quản lý vòng đời của native segments | `Arena.ofConfined()` |

**VarHandle không sở hữu bộ nhớ.** Nó mô tả *cách truy cập* một vị trí tính theo layout. Tham số `MemorySegment` ở mỗi lần `get`/`set` mới chọn **vùng nhớ cụ thể** cần thao tác. Một handle có thể được tái sử dụng cho nhiều segments chứa cùng định dạng.

**Layout cũng không phải bộ nhớ.** Dòng `MemoryLayout.structLayout(...)` chỉ tạo metadata cấu trúc; chỉ khi `arena.allocate(layout)` hay một API khác cấp phát/đem tới `MemorySegment` thì mới có bytes để đọc/ghi.

**Không nhầm với VarHandle cho Java field.** `java.lang.invoke.VarHandle` còn truy cập field của Java object hoặc phần tử Java array. Trong bài này, VarHandle được **suy ra từ FFM memory layout** và coordinate đầu tiên luôn là `MemorySegment`.

### 2.1. Tại sao dùng layout thay cho tự tính offset?

Giả sử record:

~~~c
/* Struct minh họa ở phía native */
struct Point {
    int32_t x;
    int32_t y;
};
~~~

Trong giả định C ABI mà `int32_t` chiếm 4 bytes và struct có hai fields liên tiếp, layout tương ứng:

~~~java
StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
~~~

`POINT.byteSize()` bằng `8`, `POINT.byteOffset(groupElement("x"))` bằng `0`, `POINT.byteOffset(groupElement("y"))` bằng `4`. Nếu sau này có padding hoặc một field mới, hãy sửa **layout một nơi**; các VarHandle được tạo từ layout mới sẽ chọn đúng offset tương ứng.

**Chú ý ABI:** `MemoryLayout.structLayout` **không tự thêm padding** theo C compiler. Code Java phải mô tả đúng layout thực tế từ C header/ABI, kể cả padding và alignment (xem phần 9). Đừng tin rằng chỉ trùng tên field là chắc chắn tương thích với mọi bản build C.

## 3. Cơ chế `MemoryLayout.varHandle(PathElement...)`

API trọng tâm:

~~~java
VarHandle handle = someLayout.varHandle(pathElements...);
~~~

Đường dẫn phải chọn được một **`ValueLayout`** cuối cùng; nếu chọn cả struct hoặc sequence thay vì một giá trị, `varHandle` không tạo được handle truy cập giá trị như mong muốn.

### 3.1. Trường trong struct

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

MemoryLayout layout = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_INT.withName("score"));

VarHandle idHandle = layout.varHandle(
        PathElement.groupElement("id"));

VarHandle scoreHandle = layout.varHandle(
        PathElement.groupElement("score"));
~~~

Đây là mảnh code **đặt trong một method**, không phải file độc lập. `withName("id")` gắn tên cho **member layout**, nhờ đó `groupElement("id")` tìm đúng field.

VarHandle được tạo có **carrier type** `int` và hai **coordinate types**:

~~~text
(MemorySegment, long) -> int

get(segment, baseOffset)             -> int
set(segment, baseOffset, intValue)    -> void
~~~

`baseOffset` là offset **tính theo bytes** từ đầu segment; nếu dữ liệu bắt đầu ở byte đầu, truyền `0L`. Kể cả khi field có offset tĩnh như `score` ở byte `4`, bạn **vẫn truyền `baseOffset`**; handle sẽ cộng offset field vào base.

### 3.2. Phần tử mảng: open sequence path

~~~java
SequenceLayout values = MemoryLayout.sequenceLayout(
        4, ValueLayout.JAVA_INT);

VarHandle elementHandle = values.varHandle(
        PathElement.sequenceElement());
~~~

Đây là mảnh code cần thêm import `SequenceLayout` và `VarHandle`; không chạy độc lập.

`sequenceElement()` **không chọn một phần tử cụ thể** khi tạo handle. Nó tạo *open path element*, nên mỗi lời gọi `get`/`set` nhận thêm **một coordinate `long`** cho chỉ số:

~~~text
(MemorySegment, long, long) -> int

elementHandle.get(segment, baseOffset, index)
elementHandle.set(segment, baseOffset, index, value)
~~~

Ví dụ `elementHandle.get(segment, 0L, 2L)` truy cập phần tử thứ 2 theo thứ tự 0-based. Chỉ số không phải byte offset. JVM dùng kích thước element layout để tính stride.

### 3.3. Phần tử cố định: closed sequence path

~~~java
VarHandle thirdElement = values.varHandle(
        PathElement.sequenceElement(2));
~~~

Lúc này vị trí phần tử 2 đã được **cố định khi tạo handle**, nên **không** có coordinate `index` tại thời điểm gọi:

~~~text
(MemorySegment, long) -> int

thirdElement.get(segment, 0L)
thirdElement.set(segment, 0L, 99)
~~~

Đừng vô tình gọi `thirdElement.get(segment, 0L, 2L)` như với open path; kiểu tọa độ của handle đã thay đổi.

### 3.4. Hai path elements đi liên tiếp

Để chọn field `y` trong phần tử `i` của `sequenceLayout` gồm nhiều struct `Point`:

~~~java
VarHandle y = pointsLayout.varHandle(
        PathElement.sequenceElement(),
        PathElement.groupElement("y"));
~~~

Đường dẫn được đọc **từ ngoài vào trong**:

1. Bước `sequenceElement()` đi tới **struct Point chưa xác định index**.
2. Bước `groupElement("y")` đi tới **value layout của trường y**.
3. Khi `get`/`set`, truyền `MemorySegment`, **byte base offset**, **long index** rồi (nếu ghi) giá trị `int`.

Một handle có thể dùng qua nhiều vòng lặp và nhiều segments có layout phù hợp.

## 4. Ví dụ chạy được #1: field VarHandle cho một struct

Tạo file **`EmployeeLayoutDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class EmployeeLayoutDemo {
    private static final StructLayout EMPLOYEE =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    ValueLayout.JAVA_INT.withName("score"));

    // Khai báo và dùng lại; không tạo handle trong mỗi lần truy cập.
    private static final VarHandle ID = EMPLOYEE.varHandle(
            PathElement.groupElement("id"));
    private static final VarHandle SCORE = EMPLOYEE.varHandle(
            PathElement.groupElement("score"));

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(EMPLOYEE);

            ID.set(record, 0L, 7);
            SCORE.set(record, 0L, 90);

            int oldScore = (int) SCORE.get(record, 0L);
            SCORE.set(record, 0L, oldScore + 5);

            int id = (int) ID.get(record, 0L);
            int score = (int) SCORE.get(record, 0L);

            System.out.println("id=" + id);
            System.out.println("score=" + score);
            System.out.println("bytes=" + EMPLOYEE.byteSize());
            System.out.println("score offset=" + EMPLOYEE.byteOffset(
                    PathElement.groupElement("score")));
        }
    }
}
~~~

Biên dịch/chạy với **JDK 22 trở lên**:

~~~bash
javac EmployeeLayoutDemo.java
java EmployeeLayoutDemo
~~~

Stdout:

~~~text
id=7
score=95
bytes=8
score offset=4
~~~

**Lý do output đúng:**

- Hai `JAVA_INT` liên tiếp, mỗi trường 4 bytes, layout 8 bytes.
- `ID` chọn field ở offset 0; `SCORE` chọn offset 4.
- `SCORE` được đọc, cộng thêm 5 và ghi lại, kết quả 95.
- `arena.allocate(EMPLOYEE)` cấp đúng kích thước/alignment; khi khối `try` kết thúc, native segment mất hiệu lực.

Ở đây `get` luôn cần **cast `(int)`** vì `VarHandle.get` là API signature-polymorphic. `set` nhận `int` và offset `long`. Nếu bỏ cast, truyền index kiểu `int` khi handle yêu cầu `long`, hoặc chọn một carrier không khớp, có thể gặp `WrongMethodTypeException`. Hãy kiểm tra `VarHandle.varType()` và `coordinateTypes()` khi debug.

## 5. Ví dụ chạy được #2: nhiều record, một cặp VarHandle

Một lần tạo **sequence layout gồm ba Point**, mỗi Point có hai trường nguyên `x` và `y`. Ta tạo `X` và `Y` **một lần**; mỗi lần lặp chỉ đổi coordinate `index`.

### 5.1. File `PointsVarHandleDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class PointsVarHandleDemo {
    private static final StructLayout POINT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final SequenceLayout POINTS =
            MemoryLayout.sequenceLayout(3, POINT);

    private static final VarHandle X = POINTS.varHandle(
            PathElement.sequenceElement(),
            PathElement.groupElement("x"));

    private static final VarHandle Y = POINTS.varHandle(
            PathElement.sequenceElement(),
            PathElement.groupElement("y"));

    private static final VarHandle SECOND_Y = POINTS.varHandle(
            PathElement.sequenceElement(1),
            PathElement.groupElement("y"));

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(POINTS);

            for (long i = 0; i < POINTS.elementCount(); i++) {
                int x = (int) (i + 1);
                int y = x * 10;
                X.set(memory, 0L, i, x);
                Y.set(memory, 0L, i, y);
            }

            for (long i = 0; i < POINTS.elementCount(); i++) {
                int x = (int) X.get(memory, 0L, i);
                int y = (int) Y.get(memory, 0L, i);
                System.out.println(
                        "point[" + i + "]=(" + x + "," + y + ")");
            }

            System.out.println("bytes=" + POINTS.byteSize());
            System.out.println(
                    "second y=" + (int) SECOND_Y.get(memory, 0L));
            System.out.println(
                    "second y offset=" + POINTS.byteOffset(
                            PathElement.sequenceElement(1),
                            PathElement.groupElement("y")));
        }
    }
}
~~~

### 5.2. Biên dịch, chạy

~~~bash
javac PointsVarHandleDemo.java
java PointsVarHandleDemo
~~~

Stdout:

~~~text
point[0]=(1,10)
point[1]=(2,20)
point[2]=(3,30)
bytes=24
second y=20
second y offset=12
~~~

**Giải thích bố trí bytes:**

~~~text
POINT struct: 8 bytes
  x: offset 0, int = 4 bytes
  y: offset 4, int = 4 bytes

POINTS sequence: 3 * 8 = 24 bytes

Index | x offset | y offset
  0   |     0    |     4
  1   |     8    |    12
  2   |    16    |    20
~~~

`X.set(memory, 0L, i, x)` chọn `0 + i*8 + 0`. `Y.set(memory, 0L, i, y)` chọn `0 + i*8 + 4`. Bạn **không** cần nhân `i * 8` trong Java code dùng handle.

**Hai cách chọn trường `y` của record 1:**

- `Y.get(memory, 0L, 1L)`: **open path**, index được truyền lúc truy cập.
- `SECOND_Y.get(memory, 0L)`: **closed path**, index đã cố định khi tạo handle.

`POINTS.byteOffset(sequenceElement(1), groupElement("y"))` trả **12** vì đây là đường dẫn chỉ chứa indices tĩnh. Khi cần offset động cho nhiều indices, dùng `byteOffsetHandle(...)` hoặc VarHandle có open path; đừng gọi `byteOffset` với một đường dẫn mở rồi kỳ vọng nó tự nhận chỉ số vòng lặp.

### 5.3. Lợi ích khi xử lý hàng nghìn phần tử

Trong một vòng lặp lớn, các hằng số `POINTS`, `X`, `Y` nên là `static final` (hoặc tối thiểu được tạo **ngoài vòng lặp**). Mỗi lần lặp chỉ:

1. Tính giá trị `i` từ thuật toán.
2. Gọi `get`/`set` với cùng handle.
3. Để JVM áp dụng stride và offset đúng từ layout, đồng thời kiểm tra phạm vi/lifetime.

VarHandle **có thể được JIT tối ưu tốt** trong nhiều tình huống, nhưng không có cam kết tốc độ luôn cao hơn truy cập `MemorySegment.get`/`set`. Cần benchmark với JMH và workload thật; lợi ích quan trọng trước tiên là **đúng kiểu, đúng layout, dễ bảo trì**.

## 6. Khi số phần tử chỉ biết lúc chạy: `arrayElementVarHandle`

`MemoryLayout.sequenceLayout(count, POINT)` phù hợp khi **count có sẵn lúc tạo layout**. Nhưng nếu bạn nhận một mảng records từ native code có số lượng thay đổi liên tục, không cần tạo sequence layout mới cho mỗi count.

API:

~~~java
VarHandle x = POINT.arrayElementVarHandle(
        PathElement.groupElement("x"));
~~~

Nó tạo VarHandle truy cập **mảng các phần tử nằm cạnh nhau**, mỗi phần tử có layout `POINT`. Handle có các coordinates:

~~~text
(MemorySegment, long baseOffset, long elementIndex) -> int
~~~

Điểm khác biệt: `arrayElementVarHandle` thêm một **index coordinate** của chính các records, ngay cả khi layout gốc chỉ là **một struct POINT**. Đường dẫn `groupElement("x")` chọn field **bên trong một Point**.

### 6.1. File runnable `VariablePointsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class VariablePointsDemo {
    private static final StructLayout POINT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final VarHandle X =
            POINT.arrayElementVarHandle(
                    PathElement.groupElement("x"));

    private static final VarHandle Y =
            POINT.arrayElementVarHandle(
                    PathElement.groupElement("y"));

    public static void main(String[] args) {
        final int count = 4;  // Có thể đến từ input/metadata runtime.

        try (Arena arena = Arena.ofConfined()) {
            long bytes = Math.multiplyExact(
                    POINT.byteSize(), (long) count);

            MemorySegment records = arena.allocate(
                    bytes, POINT.byteAlignment());

            for (long i = 0; i < count; i++) {
                X.set(records, 0L, i, (int) (10 * i));
                Y.set(records, 0L, i, (int) (100 * i));
            }

            long sumX = 0;
            for (long i = 0; i < count; i++) {
                int x = (int) X.get(records, 0L, i);
                int y = (int) Y.get(records, 0L, i);
                sumX += x;
                System.out.println(
                        "item[" + i + "]=" + x + "," + y);
            }
            System.out.println("sumX=" + sumX);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac VariablePointsDemo.java
java VariablePointsDemo
~~~

Stdout:

~~~text
item[0]=0,0
item[1]=10,100
item[2]=20,200
item[3]=30,300
sumX=60
~~~

**Vì sao `arrayElementVarHandle` hợp cho vòng lặp dài?**

- Không cần tạo `sequenceLayout(4, POINT)` nếu số records chỉ biết tại runtime.
- Một cặp handle `X` và `Y` dùng được cho **nhiều buffers khác nhau**, miễn bộ nhớ thực tế có bố trí đúng như `POINT`.
- JVM tính byte offset theo `POINT.byteSize()` (ở đây 8), không cần viết phép nhân trong từng lệnh read/write.
- `records.byteSize()` giới hạn bytes thực tế: nếu truyền index khiến phép tính truy cập vượt segment, sẽ có **`IndexOutOfBoundsException`**. Mã ứng dụng vẫn phải kiểm tra count, kích thước allocation, input và integer overflow trước khi gọi native.
- `Math.multiplyExact` giúp từ chối overflow khi tính tổng bytes, thay vì âm thầm tạo vùng nhớ có kích thước sai.

**Phân biệt hai nhóm API:**

| API | Layout gốc | Tọa độ động |
| --- | --- | --- |
| `POINTS.varHandle(sequenceElement(), groupElement("x"))` | **SequenceLayout** mô tả N records | Một `long` cho sequence index |
| `POINT.arrayElementVarHandle(groupElement("x"))` | **StructLayout** mô tả một record | Một `long` cho index các records liên tiếp |
| `POINT.varHandle(groupElement("x"))` | **StructLayout** mô tả một record | Không có index; chỉ base offset |

Với `arrayElementVarHandle`, index được chấp nhận theo **physical bounds** của segment chứ không tự có số phần tử cố định từ một `SequenceLayout`. Một segment lớn hơn có thể chứa nhiều records; gọi index sai về **logic** nhưng vẫn nằm trong buffer vẫn là lỗi ứng dụng, nên giữ metadata `count` và tự kiểm tra.

## 7. Nhiều mức lồng nhau: struct chứa sequence và sequence 2D

Đường dẫn layout có thể đi qua nhiều mức. Đó là điểm VarHandle tiết kiệm nhiều phép cộng offset nhất.

### 7.1. Field nằm trong struct chứa một sequence

Ví dụ record gồm `header` và `measurements[3]`:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

MemoryLayout packet = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("type"),
        MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT)
                .withName("measurements"));

VarHandle type = packet.varHandle(
        PathElement.groupElement("type"));

VarHandle measure = packet.varHandle(
        PathElement.groupElement("measurements"),
        PathElement.sequenceElement());
~~~

Đây là **snippet đặt trong method**, không phải source độc lập. `type` có coordinates `(MemorySegment, long)`; `measure` có `(MemorySegment, long, long)`. Khi gọi `measure.get(segment, 0L, 2L)`, handle tự cộng offset field `measurements` trong packet với stride của phần tử thứ 2.

Với `type` ở offset 0, `measurements` ở offset 4, mỗi int 4 bytes; offset của `measurements[2]` là `4 + 2*4 = 12`. Không cần tự cộng các hằng số này khi dùng `measure`.

### 7.2. Ma trận hai chiều

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(
                3, ValueLayout.JAVA_INT));

VarHandle cell = matrix.varHandle(
        PathElement.sequenceElement(),
        PathElement.sequenceElement());
~~~

Đoạn này cũng là snippet, cần import `MemoryLayout`, `ValueLayout`, `VarHandle` và `PathElement`.

Dạng coordinate:

~~~text
(MemorySegment segment, long baseOffset, long row, long col)
    -> int

cell.set(segment, 0L, 1L, 2L, 99)
cell.get(segment, 0L, 1L, 2L)  -> 99
~~~

Lưu ý `row` và `col` đều là **`long`** ở lời gọi VarHandle. Với 2 hàng × 3 cột, mỗi int 4 bytes, offset `[1][2]` là `(1*3 + 2)*4 = 20`. Layout giúp tránh công thức thủ công ở các điểm sử dụng.

### 7.3. Tên field và chỉ số member

`PathElement.groupElement("name")` dựa vào `withName("name")` của member layout. Nếu group member không có tên, có thể dùng `groupElement(long index)` để chọn theo thứ tự, nhưng nó dễ trở nên khó bảo trì nếu struct thay đổi.

`PathElement.sequenceElement(long index)` cố định index khi tạo handle. `PathElement.sequenceElement()` để index động. `PathElement.sequenceElement(start, step)` biểu diễn một đường dẫn mở có biến đổi vị trí theo stride; trường hợp thường gặp chỉ cần dạng không tham số.

Nếu path không tìm thấy name, vượt phạm vi fixed sequence, hoặc cuối path không phải value layout, **`varHandle(...)` có thể ném `IllegalArgumentException` ngay khi tạo handle**. Đây khác với lỗi đọc/ghi tại runtime.

## 8. `ValueLayout.varHandle()`: truy cập primitive theo byte offset

Không phải lúc nào cũng cần nested layout. Khi buffer chỉ là một mảng số nguyên liên tục, có thể tạo handle trực tiếp từ value layout:

~~~java
VarHandle intAtOffset = ValueLayout.JAVA_INT.varHandle();

// Một int tại byte offset 8:
int x = (int) intAtOffset.get(segment, 8L);

// Ghi int tại byte offset 12:
intAtOffset.set(segment, 12L, 123);
~~~

Đây là snippet, không chạy độc lập; import `ValueLayout`/`VarHandle`, và `segment` cần hợp lệ, đủ lớn và aligned.

`ValueLayout.JAVA_INT.varHandle()` trả handle có coordinates **`(MemorySegment, long)`**, nghĩa là **byte offset**, không phải chỉ số phần tử. Nếu cần index element:

- Tính `byteOffset = i * Integer.BYTES` có kiểm tra overflow.
- Hoặc dùng `ValueLayout.JAVA_INT.arrayElementVarHandle()` để nhận thêm index và tự tính stride từ layout.
- Hoặc dùng `MemorySegment.getAtIndex(ValueLayout.JAVA_INT, i)` nếu không cần cache handle riêng.

**Quy tắc đơn giản:** `ValueLayout.varHandle()` cho dữ liệu phẳng theo byte offset; `MemoryLayout.varHandle(path...)` cho trường/element có đường dẫn cấu trúc; `arrayElementVarHandle` cho nhiều bản ghi liên tiếp theo một record layout.

## 9. Alignment, padding và C ABI

Để đọc đúng dữ liệu native, layout Java cần khớp **kích thước, offset, alignment, endianness** phía C. VarHandle lấy metadata từ layout, chứ không có khả năng tự phát hiện struct C thật sự có bao nhiêu byte padding.

Ví dụ C:

~~~c
#include <stdint.h>

struct Tagged {
    uint8_t kind;
    int32_t value;
};
~~~

Với ABI phổ biến căn `int32_t` theo biên 4 bytes, compiler C đặt:

~~~text
byte 0: kind (1 byte)
byte 1..3: padding
byte 4..7: value (4 bytes)
sizeof(struct Tagged) = 8
~~~

Mô tả Java:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

StructLayout TAGGED = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));

VarHandle VALUE = TAGGED.varHandle(
        PathElement.groupElement("value"));
~~~

**`paddingLayout(3)` được tính bằng BYTES trên JDK 22.** Trong `structLayout` của JDK 22, JVM **không tự thêm padding**. Nếu bỏ padding, offset 1 không thỏa alignment 4 của `JAVA_INT` và việc tạo struct layout có thể bị từ chối bởi `IllegalArgumentException`.

Khi mapping từ thư viện C có ABI khác, hãy kiểm tra `sizeof`, `offsetof`, compiler flags và packing thực tế. Ví dụ `#pragma pack` hoặc giao thức network packed có thể cần một `ValueLayout` alignment yếu hơn, chẳng hạn `JAVA_INT_UNALIGNED` hay `withByteAlignment(1)`, đồng thời dùng byte order phù hợp qua `withOrder(ByteOrder.LITTLE_ENDIAN/BIG_ENDIAN)`. **Không tự đổi alignment để “né exception”** nếu bản native không có bố trí tương ứng.

Mảng struct C cũng có thể có **tail padding** theo ABI. Khi dùng `arrayElementVarHandle`, stride là **`POINT.byteSize()`**, nên mọi padding cuối record phải được mô tả đúng. Không đoán stride bằng tổng kích thước payload fields nếu ABI có thể thêm padding.

## 10. `byteOffset`, `byteOffsetHandle`, `asSlice` và VarHandle

Cùng một layout path có thể được dùng để tạo nhiều loại thao tác:

| API | Trả về | Dùng khi |
| --- | --- | --- |
| `layout.byteOffset(fixedPath...)` | Một `long` offset tính theo bytes | Cần **offset tĩnh**, ví dụ field `y` trong record thứ 1 |
| `layout.byteOffsetHandle(openPath...)` | `MethodHandle` tính offset từ coordinate động | Cần **tính byte offset** của phần tử thay vì đọc/ghi nó |
| `layout.varHandle(path...)` | `VarHandle` đọc/ghi value được chọn | Truy cập lặp lại một field/element |
| `layout.sliceHandle(path...)` | `MethodHandle` tạo view/slice tại path | Cần một `MemorySegment` con để xử lý tiếp |
| `segment.asSlice(offset, size)` | `MemorySegment` view cùng backing memory | Đã có offset/size cụ thể và muốn thao tác trên vùng con |

Ví dụ một path tĩnh:

~~~java
long yOffset = POINTS.byteOffset(
        PathElement.sequenceElement(1),
        PathElement.groupElement("y"));
~~~

Kết quả `12` với Point 8 bytes. Nếu cần offset của record `i`, có thể dùng một `byteOffsetHandle` tạo sẵn; khi truy cập giá trị thông thường thì **VarHandle có open sequence path** tiện hơn vì không cần tính offset ra biến rồi lại gọi `segment.get`.

### 10.1. Gắn cố định base offset với `MethodHandles.insertCoordinates`

Một VarHandle từ layout luôn có coordinate `baseOffset`, mặc dù nhiều ứng dụng chỉ dùng `0L`. Có thể tạo adapter để rút ngắn lời gọi.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

// Giả định X là VarHandle có coordinates:
// (MemorySegment segment, long baseOffset, long index).
VarHandle xAtBaseZero =
        MethodHandles.insertCoordinates(X, 1, 0L);

// Adapter còn hai coordinates: (MemorySegment, long index).
xAtBaseZero.set(memory, 2L, 123);
int x = (int) xAtBaseZero.get(memory, 2L);
~~~

Đây là **snippet minh họa**, cần biến `X` và `memory` được tạo như phần 5. Vị trí `1` trong `insertCoordinates` chỉ coordinate **baseOffset**; `0L` là giá trị muốn gắn sẵn. Sau khi adapt, không truyền base offset nữa.

Adapter phù hợp khi:

- Mọi lần truy cập có cùng base offset.
- Bạn muốn API ngắn hơn và giảm nguy cơ truyền nhầm `0L`.
- Handle và adapter được cache để tái sử dụng, không tạo mỗi vòng lặp.

Không nhầm `MethodHandle` (một thao tác được biểu diễn bởi callable signature) với `VarHandle` (đọc/ghi một biến có nhiều access modes). `MethodHandles` là nơi cung cấp các adapter cho VarHandle.

## 11. VarHandle và truy cập đồng thời: không đồng nghĩa mọi thao tác đều atomic

VarHandle hỗ trợ nhiều **access modes**:

- `get` / `set`: đọc/ghi thông thường (*plain*), có ràng buộc memory ordering thấp.
- `getOpaque` / `setOpaque`: opaque access.
- `getAcquire` / `setRelease`: acquire/release ordering.
- `getVolatile` / `setVolatile`: volatile ordering.
- `compareAndSet`, `getAndAdd`, `getAndSet`...: các phép atomic update khi loại dữ liệu, alignment và implementation hỗ trợ.

**Không phải mọi access mode đều có sẵn cho mọi layout/type.** Đặc tả có giới hạn đối với unaligned layouts, primitive carrier và kích thước truy cập. Ví dụ atomic update trên `int` được căn đúng có thể được hỗ trợ, trong khi một layout unaligned có thể không cho phép một số atomic modes. Dùng `handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` để kiểm tra capability khi phải hỗ trợ nhiều môi trường.

### 11.1. Ví dụ runnable: đếm đa luồng bằng aligned VarHandle

File **`AtomicSegmentCounter.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

public final class AtomicSegmentCounter {
    private static final VarHandle COUNTER =
            ValueLayout.JAVA_INT.varHandle();

    public static void main(String[] args)
            throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment memory = arena.allocate(
                    ValueLayout.JAVA_INT);

            COUNTER.setVolatile(memory, 0L, 0);

            Runnable increment = () -> {
                for (int i = 0; i < 1_000; i++) {
                    // Nhận giá trị cũ; phép tăng là atomic.
                    int old = (int) COUNTER.getAndAdd(
                            memory, 0L, 1);
                }
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);

            first.start();
            second.start();

            first.join();
            second.join();

            int result = (int) COUNTER.getVolatile(memory, 0L);
            System.out.println("count=" + result);
        }
    }
}
~~~

Biên dịch/chạy trên **JDK 22+**:

~~~bash
javac AtomicSegmentCounter.java
java AtomicSegmentCounter
~~~

Stdout:

~~~text
count=2000
~~~

Vì `ValueLayout.JAVA_INT` có alignment phù hợp cho truy cập `int`, `getAndAdd` thực hiện cập nhật nguyên tử; hai threads cùng tăng 1.000 lần nên kết quả xác định là 2.000. `Arena.ofShared()` cho phép các threads truy cập cùng segment; `join` đảm bảo cả hai đã xong **trước khi** arena đóng và trước khi main đọc kết quả.

**Phân biệt hai loại an toàn:**

- `Arena.ofShared()`: segment **có thể được truy cập từ nhiều thread**, không tự làm `x = x + 1` thành atomic.
- `VarHandle.getAndAdd`: bản thân thao tác cập nhật giá trị là atomic với access mode phù hợp, nhưng không quản lý **vòng đời** của memory.

Một phép `get` + `set` riêng lẻ không tương đương `getAndAdd` trong môi trường đa luồng. Với layout cần packed/unaligned, hãy kiểm tra access mode và chọn đồng bộ/biểu diễn dữ liệu đúng, không ép dùng atomic mode không hỗ trợ.

## 12. Memory safety khi tái sử dụng handle

Cùng VarHandle có thể sống lâu hơn nhiều arenas và segments vì nó **chỉ chứa thông tin truy cập**. Điều đó không làm segment cũ còn hiệu lực:

~~~java
// Ý tưởng bên trong method: HANDLE được tạo sẵn từ layout.
MemorySegment expired;

try (Arena arena = Arena.ofConfined()) {
    expired = arena.allocate(ValueLayout.JAVA_INT);
    // HANDLE.set(expired, 0L, 42);
}

// Arena đóng. Dùng HANDLE trên expired vẫn không hợp lệ.
// HANDLE.get(expired, 0L) -> IllegalStateException.
~~~

Đây là minh họa về lifetime, không phải source độc lập. VarHandle tiếp tục tái sử dụng được với **segment mới còn sống**, có layout/size phù hợp.

Các lớp lỗi cần phân biệt:

| Vấn đề | Biểu hiện thông dụng | Nguyên tắc xử lý |
| --- | --- | --- |
| Truy cập quá `segment.byteSize()` | `IndexOutOfBoundsException` | Kiểm tra count, stride, base offset, kích thước segment |
| Dùng segment sau `Arena.close()` | `IllegalStateException` | Không để segment vượt scope; dùng try-with-resources |
| Dùng confined segment từ thread khác | `WrongThreadException` | Chỉ owner thread truy cập hoặc dùng shared arena |
| Offset/address không đáp ứng alignment | `IllegalArgumentException` | Sửa layout/alignment, padding, offset thực tế |
| Ghi vào read-only segment | `IllegalArgumentException` | Chỉ ghi vào segment writable |
| Truyền sai carrier/coordinate types ở `get`/`set` | `WrongMethodTypeException` | Xem `varType()`/`coordinateTypes()`; dùng `long` cho index/offset |
| Access mode không được hỗ trợ | `UnsupportedOperationException` | Kiểm tra `isAccessModeSupported` và alignment/carrier |
| Layout path sai ngay khi tạo handle | `IllegalArgumentException` | Chọn đúng group/sequence path tới value layout |
| Segment có bytes nhưng khác cấu trúc mong đợi | **Có thể đọc ra giá trị sai mà không ném exception** | Xác nhận ABI, byte order, stride, padding và schema |

**Quan trọng:** VarHandle **không tự phát hiện** “đây là buffer record loại A hay loại B”. Nếu cả hai có đủ bytes và alignment, nó vẫn đọc theo layout A bạn đã khai báo. **Type safety của carrier và boundary safety không thay thế layout/ABI correctness**.

### 12.1. Raw native pointers vẫn cần ownership riêng

FFM `MemorySegment` có temporal safety ở Java. Nhưng nếu chương trình C giữ raw address của segment trong một global variable và truy cập sau khi arena đóng, JVM không thể tự bảo vệ C khỏi dangling pointer. Thiết kế native call phải bảo đảm:

1. Segment đủ sống trong suốt lời gọi/công việc native.
2. Nếu C giữ pointer để dùng async, owner phải duy trì arena cho tới khi C xác nhận không còn dùng.
3. Không close shared arena khi thread/native call vẫn đang xử lý memory.
4. Khi muốn copy kết quả sang arena khác, thực hiện copy **khi cả hai scopes còn sống**; không chỉ gán lại reference Java.

## 13. Thiết kế API để dùng VarHandle lặp lại mà không rối

Một pattern tốt là lưu **layout và các handles cùng một nơi**, ví dụ một class codec.

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class PointCodec {
    private static final StructLayout LAYOUT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final VarHandle X =
            LAYOUT.varHandle(PathElement.groupElement("x"));

    private static final VarHandle Y =
            LAYOUT.varHandle(PathElement.groupElement("y"));

    private PointCodec() {
    }

    public static long byteSize() {
        return LAYOUT.byteSize();
    }

    public static int x(MemorySegment segment) {
        return (int) X.get(segment, 0L);
    }

    public static int y(MemorySegment segment) {
        return (int) Y.get(segment, 0L);
    }

    public static void set(MemorySegment segment, int x, int y) {
        X.set(segment, 0L, x);
        Y.set(segment, 0L, y);
    }

    public static MemoryLayout layout() {
        return LAYOUT;
    }
}
~~~

Đây là **file Java hợp lệ** nhưng không có `main`; có thể biên dịch bằng `javac PointCodec.java` rồi sử dụng như thư viện trong code ứng dụng. Một caller có thể làm:

~~~java
// Minh họa trong một method; import Arena, MemorySegment.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment p = arena.allocate(PointCodec.layout());
    PointCodec.set(p, 3, 4);
    System.out.println(PointCodec.x(p) + PointCodec.y(p)); // 7
}
~~~

**Vì sao thiết kế này dễ bảo trì?** Tất cả path, offsets và carrier types nằm cùng `LAYOUT`. Caller không cần biết field `y` ở byte 4. Khi schema thay đổi, kiểm tra và sửa codec thay vì tìm các phép cộng byte offset khắp ứng dụng.

Nên giữ `MemoryLayout` và `VarHandle` là **`static final`** khi layout cố định. Với layout do runtime negotiation quyết định, tạo handles **một lần cho mỗi phiên bản schema**, cache theo metadata thích hợp; không tái sử dụng handle schema cũ lên buffer schema mới.

### 13.1. Có nên gắn luôn `Arena` vào codec?

Không mặc định. Codec chỉ định **cách truy cập dữ liệu**, còn arena chỉ định **ai sở hữu và khi nào giải phóng**. Tách chúng giúp một codec được dùng cho:

- Native memory ở confined arena per-request.
- Shared arena cho dữ liệu qua nhiều threads.
- Heap segment backed by Java array (nếu phù hợp).
- Buffer được truyền từ foreign function, với lifetime đúng.

Đừng đóng arena trong codec nếu caller còn dùng segment. Cũng đừng giữ một global arena chỉ để “giữ sống VarHandle”; VarHandle không cần arena sống để tồn tại.

## 14. Debug: kiểm tra type và coordinates trước khi sửa offset

Khi lời gọi `get`/`set` ném `WrongMethodTypeException`, hãy in signature của handle **ngoài hot loop**:

~~~java
System.out.println(X.varType());
System.out.println(X.coordinateTypes());
~~~

Đối với handle `X` trong `PointsVarHandleDemo`:

~~~text
int
[interface java.lang.foreign.MemorySegment, long, long]
~~~

Đây là mô tả **dạng nội dung in của Java Reflection Class/List trong JDK 22**, dùng để chẩn đoán; không phải stdout của bài chạy chính.

Các lỗi điển hình:

- Gọi `X.get(segment, 0, 2)` với literals `int`, trong khi handle yêu cầu `long`. Dùng `0L` và `2L` hoặc ép `(long)i`.
- Dùng `(long) X.get(...)` cho handle có carrier `int`; kiểu return mong muốn không khớp carrier. Lấy `(int) X.get(...)` rồi mở rộng sang long trong Java nếu cần.
- Cố gọi `X.get(segment, 2L)` khi X còn cả base offset và index.
- Dùng index `i` mà record layout có padding khác C ABI, nên giá trị bị “nhảy nhầm stride” dù không có exception.
- Gọi `varHandle(groupElement("name"))` với field chưa `withName`.
- Tạo path chỉ tới một `StructLayout` hay `SequenceLayout` rồi mong nó đọc được scalar; cần chọn tiếp value field.
- Truy cập Java `int[]` bằng FFM VarHandle đã tạo từ một memory layout của native struct mà không kiểm tra assumptions về backing memory/byte order.

Một check nhanh:

~~~text
1) handle.varType()       -> dữ liệu là int/long/float/...?
2) handle.coordinateTypes() -> cần mấy tham số, theo thứ tự nào?
3) layout.byteSize()      -> buffer có đủ bytes?
4) layout.byteAlignment() -> buffer/offset có đúng alignment?
5) segment.scope().isAlive() -> scope còn sống?
6) segment.isReadOnly()   -> có được ghi?
7) tên field / index / byte order / padding có khớp native ABI?
~~~

Đây là **checklist**, không phải API call gộp thành một method. Với shared arena, kết quả `isAlive()` là ảnh chụp tại thời điểm kiểm tra, không thay thế đồng bộ với thread có thể đóng arena.

## 15. Sai và đúng khi truy cập lặp lại

### Cách dễ lỗi: tính offset thủ công trong mọi vòng lặp

~~~java
// Minh họa: Point 8 bytes, field y tại offset 4.
for (long i = 0; i < count; i++) {
    long offset = i * 8 + 4;
    int y = segment.get(ValueLayout.JAVA_INT, offset);
    consume(y);
}
~~~

Đây là snippet minh họa, `consume` là hàm trong ứng dụng, không phải source độc lập. Vấn đề là các hằng số `8`/`4` được lặp khắp code và dễ sai khi layout thay đổi.

### Cách tốt hơn: tạo handle một lần rồi dùng index

~~~java
VarHandle Y = POINT.arrayElementVarHandle(
        PathElement.groupElement("y"));

// Tạo ngoài vòng lặp.
for (long i = 0; i < count; i++) {
    int y = (int) Y.get(segment, 0L, i);
    consume(y);
}
~~~

Đây cũng là snippet minh họa, giả định `POINT`, `segment` và `consume` đã được định nghĩa. Ưu điểm: **schema quyết định stride và offset**. Nếu layout thay đổi, sửa layout một lần.

### Khi chỉ đọc một giá trị, có nhất thiết dùng VarHandle?

Không. `segment.get(ValueLayout.JAVA_INT, knownOffset)` là API ngắn, rõ ràng nếu offset/kiểu đã được xác nhận và code không cần xử lý nhiều record/field. Dùng VarHandle khi:

- Phải truy cập cùng field hoặc element **nhiều lần**.
- Dữ liệu nested và tính offset thủ công dễ sai.
- Muốn đóng gói layout thành một codec.
- Cần một access mode như `getVolatile`, `compareAndSet` hay `getAndAdd` với ràng buộc alignment/carrier thích hợp.

VarHandle là công cụ **mô tả cách truy cập**, không phải quy tắc bắt buộc cho mọi byte.

## 16. Câu hỏi thực hành và đáp án

**Câu 1.** `POINTS` là `sequenceLayout(3, POINT)`, `POINT` gồm `int x` và `int y`. Vì sao `POINTS.varHandle(sequenceElement(), groupElement("y"))` cần truyền cả `0L` và `index`?  
**Đáp án:** Handle nhận `baseOffset` để xác định vị trí vùng dữ liệu trong segment, và `index` do `sequenceElement()` là một open path. Trường y có offset 4 trong mỗi Point.

**Câu 2.** Chọn `sequenceElement(1)` thay vì `sequenceElement()` có khác gì?  
**Đáp án:** Fixed index 1 được mã hóa lúc tạo handle; không truyền index nữa. Open path cần một `long index` khi `get`/`set`.

**Câu 3.** Tại sao `POINTS.byteOffset(sequenceElement(1), groupElement("y"))` bằng `12`?  
**Đáp án:** Record thứ 1 bắt đầu ở `1*8 = 8`, field y ở `+4`, tổng 12 bytes.

**Câu 4.** Mảng records có số lượng chỉ biết khi gọi native. Chọn API nào?  
**Đáp án:** Cân nhắc `POINT.arrayElementVarHandle(groupElement("x"))`. Handle tự dùng stride của một record `POINT`, index động và physical bounds của segment.

**Câu 5.** `POINT.arrayElementVarHandle(groupElement("x"))` có tự biết count logic của dữ liệu C không?  
**Đáp án:** Không. Nó biết stride từ layout, còn count do metadata của ứng dụng cung cấp. Đảm bảo count và kích thước segment khớp; không giả định buffer có bao nhiêu phần tử chỉ từ handle.

**Câu 6.** VarHandle tạo cho `JAVA_INT` có `varType()` là gì?  
**Đáp án:** `int.class`. `get` thường được cast thành `int` tại call site; offset/index coordinates cần `long` theo handle type.

**Câu 7.** Vì sao dùng `StructLayout` không có padding cho `char kind; int value;` có thể lỗi?  
**Đáp án:** `structLayout` không tự căn chỉnh fields. Nếu `value` phải align 4 nhưng ở offset 1, layout không hợp lệ; hãy mô tả padding đúng theo C ABI.

**Câu 8.** Dùng `Arena.ofConfined()` cho segment, sau đó dùng static VarHandle để đọc từ thread khác có an toàn không?  
**Đáp án:** Không. Handle có thể chia sẻ, nhưng **segment/scope bị thread-confined**; truy cập từ thread không phải owner có thể ném `WrongThreadException`.

**Câu 9.** Có thể dùng lại cùng VarHandle trên segment mới sau khi arena cũ đã close không?  
**Đáp án:** Có, nếu segment mới còn sống và có bố trí, alignment, size phù hợp. Handle không sở hữu/giữ sống backing memory của segment cũ.

**Câu 10.** Hai threads cùng viết `counter = counter + 1` qua `get`/`set` trên shared arena. Kết quả có luôn bằng tổng lượt tăng không?  
**Đáp án:** Không. Hai thao tác riêng không phải cập nhật nguyên tử. Với aligned int và mode hỗ trợ, `getAndAdd` là lựa chọn atomic, kết hợp ownership/close đúng cách.

**Câu 11.** Nếu một `MemorySegment` chứa đủ bytes nhưng dùng handle cho struct sai ABI, JVM có luôn báo lỗi không?  
**Đáp án:** Không. Nếu offsets vẫn nằm trong bounds và thỏa alignment, Java có thể đọc một giá trị sai mà không ném exception. Xác minh `sizeof`, `offsetof`, field types và byte order.

**Câu 12.** Dùng `MethodHandles.insertCoordinates(X, 1, 0L)` với handle `X` có các coords `(MemorySegment, long, long)` tạo ra khác biệt gì?  
**Đáp án:** Cố định `baseOffset` bằng `0L`, nên adapter chỉ còn `(MemorySegment, long index)`; thích hợp khi mọi truy cập đều bắt đầu từ đầu segment.

## 17. Tài liệu tham khảo chính thức

- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `varHandle`, `arrayElementVarHandle`, layout paths, `byteOffset`, kiểm tra bound/alignment.
- [Oracle Java SE 22 — Memory Layouts and Structured Access](https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html): ví dụ chính thức tạo VarHandle cho `sequenceLayout` các điểm `x/y`.
- [Oracle Java SE 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html): group/sequence selectors, open và fixed paths.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): carrier, byte alignment/order và `ValueLayout.varHandle()`.
- [Oracle Java SE 22 — VarHandle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/VarHandle.html): coordinate types, signature-polymorphic calls, access modes và atomicity.
- [Oracle Java SE 22 — MethodHandles](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandles.html): `insertCoordinates` và các VarHandle adapters.
- [Oracle Java SE 22 — Arena và MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native allocations, scope, confinement và lifetime.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): sự chuẩn hóa FFM trong JDK 22 và động cơ native interoperability.

**Tổng kết:** Tạo **layout đúng ABI** trước; từ layout chọn **field hoặc element bằng path**, tạo **VarHandle một lần**, rồi truyền `MemorySegment`, `baseOffset` và các **`long index`** tương ứng khi truy cập lặp lại. Với mảng bản ghi độ dài runtime, dùng `arrayElementVarHandle`. Handle giúp tránh tính lại offsets và tập trung schema, nhưng **không thay thế** kiểm tra ownership, scope, threads, bounds, memory ordering và hợp đồng với native code.
