# Layout path và VarHandle để truy cập thành phần trong cấu trúc lồng nhau

Foreign Function & Memory API (FFM API) cho phép Java mô tả vùng nhớ bằng `MemoryLayout`, đại diện vùng nhớ bằng `MemorySegment` và truy cập dữ liệu thông qua các API có kiểm tra giới hạn, căn chỉnh và vòng đời. Khi dữ liệu có cấu trúc nhiều tầng, chẳng hạn một hình chữ nhật chứa hai điểm hoặc một đa giác chứa mảng điểm, ta không cần tự cộng từng offset để tìm một trường nằm sâu bên trong.

**Layout path** mô tả đường đi từ layout gốc tới layout thành phần. Từ đường đi đó, `MemoryLayout` có thể chọn layout con, tính offset hoặc tạo một `VarHandle` để đọc và ghi giá trị. Cách này giúp mã Java thể hiện cấu trúc dữ liệu rõ ràng và giảm lỗi khi layout thay đổi.

Các ví dụ trong bài dùng FFM API chính thức từ JDK 22, được chuẩn hóa qua JEP 454. Đây là API trong `java.lang.foreign`, không phải các API incubator hoặc preview của những JDK cũ. Cách tiếp cận này vẫn áp dụng trên các phiên bản Java hiện đại.

## 1. Mô hình dữ liệu: MemoryLayout và cấu trúc lồng nhau

`MemoryLayout` mô tả hình dạng dữ liệu trong bộ nhớ: kích thước, căn chỉnh, thứ tự byte và cách các thành phần được tổ chức. Các layout thường gặp gồm:

| Loại layout | Vai trò |
| --- | --- |
| `ValueLayout` | Mô tả giá trị nguyên thủy như `int`, `long`, `float`, `double` hoặc địa chỉ. |
| `StructLayout` | Mô tả các thành phần được đặt nối tiếp nhau, tương tự `struct` trong C. |
| `UnionLayout` | Mô tả các thành phần dùng chung vị trí bắt đầu, tương tự `union` trong C. |
| `SequenceLayout` | Mô tả một dãy phần tử có cùng layout, tương tự mảng. |
| `PaddingLayout` | Mô tả vùng đệm được thêm để đạt bố cục hoặc căn chỉnh mong muốn. |

Ví dụ, một điểm hai chiều có hai trường `x` và `y` kiểu `double`:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

static final StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_DOUBLE.withName("x"),
        ValueLayout.JAVA_DOUBLE.withName("y")
);
```

Một hình chữ nhật có thể chứa hai điểm, góc trên trái và góc dưới phải:

```java
static final StructLayout RECTANGLE = MemoryLayout.structLayout(
        POINT.withName("topLeft"),
        POINT.withName("bottomRight")
);
```

`RECTANGLE` là một group layout chứa hai group layout `POINT`. Mỗi `POINT` lại chứa hai value layout có tên. Cấu trúc này có thể hình dung như sau:

```text
RECTANGLE
|-- topLeft: POINT
|   |-- x: double
|   `-- y: double
`-- bottomRight: POINT
    |-- x: double
    `-- y: double
```

Tên được gắn bằng `withName(...)` là cơ sở để chọn thành phần bằng `PathElement.groupElement(String)`. Nên đặt tên rõ ràng cho các trường cần truy cập để layout path dễ đọc và ít phụ thuộc vào thứ tự khai báo.

## 2. Layout path là gì?

Layout path là một chuỗi `MemoryLayout.PathElement` dùng để chọn một layout con bên trong layout gốc. Mỗi phần tử của đường đi chọn một thành phần thuộc layout hiện tại, sau đó việc chọn tiếp tục trên layout con vừa tìm được.

Ba nhóm path element chính:

| Path element | Công dụng |
| --- | --- |
| `groupElement("name")` | Chọn thành phần có tên trong `GroupLayout` (`StructLayout` hoặc `UnionLayout`). |
| `groupElement(index)` | Chọn thành phần theo vị trí trong group layout. |
| `sequenceElement()` | Chọn một phần tử bất kỳ trong `SequenceLayout`; chỉ số được truyền khi gọi handle. |
| `sequenceElement(index)` | Chọn một phần tử cụ thể của sequence ngay khi tạo path. |
| `sequenceElement(start, step)` | Chọn một dãy vị trí theo điểm bắt đầu và bước nhảy. |
| `dereferenceElement()` | Đi theo địa chỉ được mô tả bởi `AddressLayout` có target layout. |

Ví dụ đường đi tới trường `y` của điểm `bottomRight` trong hình chữ nhật:

```java
MemoryLayout.PathElement.groupElement("bottomRight"),
MemoryLayout.PathElement.groupElement("y")
```

Đường đi có hai bước:

1. Từ `RECTANGLE`, chọn group có tên `bottomRight`.
2. Từ group `POINT` vừa chọn, chọn value layout có tên `y`.

Đường đi phải phù hợp với cấu trúc layout. Ví dụ, `groupElement(...)` chỉ áp dụng cho group layout; `sequenceElement(...)` chỉ áp dụng cho sequence layout. Nếu một thành phần không tồn tại hoặc path không hợp lệ, API ném `IllegalArgumentException` khi tạo kết quả tương ứng.

## 3. Dùng layout path để chọn layout con và tính offset

Không phải lúc nào cũng cần đọc hoặc ghi giá trị. Có lúc ta chỉ cần biết layout con là kiểu gì hoặc nó bắt đầu ở byte thứ mấy trong layout gốc.

### Chọn layout con với `select(...)`

```java
MemoryLayout bottomRightYLayout = RECTANGLE.select(
        MemoryLayout.PathElement.groupElement("bottomRight"),
        MemoryLayout.PathElement.groupElement("y")
);

System.out.println(bottomRightYLayout);
```

`select(...)` trả về layout tại cuối đường đi. Trong ví dụ này, kết quả là layout mô tả một giá trị `double`.

### Tính vị trí với `byteOffset(...)`

```java
long bottomRightYOffset = RECTANGLE.byteOffset(
        MemoryLayout.PathElement.groupElement("bottomRight"),
        MemoryLayout.PathElement.groupElement("y")
);

System.out.println("Offset: " + bottomRightYOffset);
```

`byteOffset(...)` trả về offset tính bằng byte so với đầu layout gốc. Với hai điểm gồm các trường `double`, mỗi điểm có kích thước 16 byte; `y` của điểm `bottomRight` bắt đầu tại offset 24.

Không nên tự ghi cứng con số offset vào nhiều vị trí trong chương trình. Nếu cấu trúc thay đổi, hãy tính offset từ layout hoặc tạo handle từ layout path để mã tự theo bố cục đã mô tả.

## 4. Tạo VarHandle từ layout path

`VarHandle` là một đối tượng truy cập biến có kiểu được kiểm tra động. Với FFM API, `MemoryLayout.varHandle(...)` tạo một handle để đọc hoặc ghi value layout được chọn bởi đường đi.

Ví dụ tạo handle truy cập trường `y` của điểm `bottomRight`:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.invoke.VarHandle;

static final VarHandle BOTTOM_RIGHT_Y = RECTANGLE.varHandle(
        MemoryLayout.PathElement.groupElement("bottomRight"),
        MemoryLayout.PathElement.groupElement("y")
);
```

Đường đi kết thúc tại `ValueLayout`, nên có thể tạo `VarHandle`. Nếu đường đi kết thúc tại một group hoặc sequence layout thay vì một value layout, `varHandle(...)` không thể tạo handle đọc/ghi giá trị và sẽ ném `IllegalArgumentException`.

### Các coordinate của VarHandle

Một điểm quan trọng là handle được tạo từ `MemoryLayout.varHandle(...)` có các coordinate sau:

- `MemorySegment`: vùng nhớ sẽ được truy cập.
- `long`: offset gốc bên trong segment.
- Một `long` bổ sung cho mỗi open path element, ví dụ mỗi `sequenceElement()` không cố định chỉ số.

Với path chỉ gồm hai `groupElement(...)` như `BOTTOM_RIGHT_Y`, handle có dạng khái niệm `(MemorySegment, long) -> double`. Vì vậy, lời gọi `get` hoặc `set` cần cả segment và offset gốc:

```java
double y = (double) BOTTOM_RIGHT_Y.get(segment, 0L);
BOTTOM_RIGHT_Y.set(segment, 0L, 42.5d);
```

Coordinate `0L` có nghĩa là bắt đầu tính đường đi từ byte đầu tiên của segment. Có thể truyền offset khác nếu dữ liệu cần truy cập nằm trong một vùng con của segment lớn hơn.

## 5. Ví dụ đầy đủ: đọc và ghi trường trong struct lồng nhau

Ví dụ sau cấp phát bộ nhớ cho hình chữ nhật, ghi tọa độ qua `VarHandle`, rồi đọc lại giá trị:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

public class NestedStructAccess {
    static final StructLayout POINT = MemoryLayout.structLayout(
            ValueLayout.JAVA_DOUBLE.withName("x"),
            ValueLayout.JAVA_DOUBLE.withName("y")
    );

    static final StructLayout RECTANGLE = MemoryLayout.structLayout(
            POINT.withName("topLeft"),
            POINT.withName("bottomRight")
    );

    static final VarHandle BOTTOM_RIGHT_Y = RECTANGLE.varHandle(
            MemoryLayout.PathElement.groupElement("bottomRight"),
            MemoryLayout.PathElement.groupElement("y")
    );

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment rectangle = arena.allocate(RECTANGLE);

            BOTTOM_RIGHT_Y.set(rectangle, 0L, 42.5d);

            double y = (double) BOTTOM_RIGHT_Y.get(rectangle, 0L);
            System.out.println("bottomRight.y = " + y);
        }
    }
}
```

Kết quả:

```text
bottomRight.y = 42.5
```

`Arena.ofConfined()` tạo một arena có vòng đời được giới hạn trong thread tạo ra nó. `arena.allocate(RECTANGLE)` cấp phát vùng nhớ đủ kích thước và căn chỉnh theo layout. Khi thoát khỏi khối `try`, arena được đóng và segment gắn với arena không còn được truy cập.

Việc khai báo layout và `VarHandle` ở dạng `static final` giúp tái sử dụng cấu trúc và tránh tạo lại handle trong mỗi lần đọc/ghi. Segment vẫn cần được truyền vào từng lần truy cập.

## 6. Truy cập phần tử trong sequence lồng trong struct

Một cấu trúc phổ biến khác là một đối tượng chứa mảng các phần tử. Ví dụ, đa giác có trường `count` và một dãy điểm `points`, mỗi điểm có `x` và `y`.

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

static final StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_DOUBLE.withName("x"),
        ValueLayout.JAVA_DOUBLE.withName("y")
);

static final SequenceLayout POINTS = MemoryLayout.sequenceLayout(3, POINT);

static final StructLayout POLYGON = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("count"),
        MemoryLayout.paddingLayout(4),
        POINTS.withName("points")
);
```

`POLYGON` có một số nguyên 4 byte, tiếp theo là 4 byte padding, rồi đến ba điểm. Padding được khai báo tường minh để trường `points` bắt đầu tại offset 8, phù hợp với căn chỉnh 8 byte của `POINT`. `structLayout(...)` bố trí các member theo thứ tự được cung cấp; khi cần mô tả ABI của cấu trúc native, phải khai báo padding và alignment phù hợp với ABI đó.

Tạo handle truy cập `y` của một phần tử bất kỳ trong mảng:

```java
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

static final VarHandle POINT_Y = POLYGON.varHandle(
        PathElement.groupElement("points"),
        PathElement.sequenceElement(),
        PathElement.groupElement("y")
);
```

`sequenceElement()` là một **open path element**: nó chọn phần tử theo chỉ số được cung cấp lúc gọi `VarHandle`. Do path có một open element, handle có coordinate `(MemorySegment, long, long)`, lần lượt là segment, offset gốc và chỉ số phần tử.

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment polygon = arena.allocate(POLYGON);

    for (int i = 0; i < 3; i++) {
        double y = i * 10.0;
        POINT_Y.set(polygon, 0L, (long) i, y);
    }

    for (int i = 0; i < 3; i++) {
        double y = (double) POINT_Y.get(polygon, 0L, (long) i);
        System.out.println("points[" + i + "].y = " + y);
    }
}
```

Kết quả:

```text
points[0].y = 0.0
points[1].y = 10.0
points[2].y = 20.0
```

Chỉ số `i` được truyền dưới dạng `long`, đúng với coordinate mà open path element yêu cầu. Chỉ số nằm ngoài số phần tử của sequence hoặc offset vượt giới hạn segment sẽ dẫn tới lỗi truy cập thay vì âm thầm đọc vùng nhớ ngoài phạm vi.

## 7. Open path và fixed path

`sequenceElement()` và `sequenceElement(index)` có ý nghĩa khác nhau:

| Cách khai báo | Ý nghĩa | Coordinate chỉ số lúc gọi handle |
| --- | --- | --- |
| `sequenceElement()` | Chọn phần tử tùy theo lần truy cập. | Có thêm một `long`. |
| `sequenceElement(2)` | Chọn cố định phần tử thứ ba ngay trong layout path. | Không có coordinate cho chỉ số này. |
| `sequenceElement(1, 2)` | Chọn dãy phần tử bắt đầu ở chỉ số 1, bước 2. | Có thêm một `long` để chọn vị trí trong dãy đã chọn. |

Ví dụ, nếu chỉ muốn truy cập trường `y` của điểm thứ ba:

```java
VarHandle THIRD_POINT_Y = POLYGON.varHandle(
        PathElement.groupElement("points"),
        PathElement.sequenceElement(2),
        PathElement.groupElement("y")
);

// Path đã cố định phần tử thứ ba nên chỉ còn segment và base offset.
double y = (double) THIRD_POINT_Y.get(polygon, 0L);
```

Open path phù hợp khi chỉ số thay đổi trong vòng lặp hoặc được xác định khi chạy. Fixed path hữu ích khi một vị trí cụ thể có ý nghĩa cố định trong cấu trúc.

Nếu một layout path chứa nhiều open path element, mỗi phần tử mở tạo thêm một coordinate `long`. Thứ tự coordinate tương ứng với thứ tự các open element xuất hiện trong path. Cần ghi nhớ điều này khi xây dựng handle cho cấu trúc nhiều chiều hoặc lồng nhiều sequence.

## 8. Mảng có độ dài thay đổi và `arrayElementVarHandle(...)`

Một mảng có kích thước cố định có thể được mô tả bằng `sequenceLayout(count, elementLayout)`. Nhưng trong một số cấu trúc native, số phần tử chỉ được biết khi chạy. Ví dụ, một polygon có trường `count` và flexible array member `points[]` trong C.

Trong trường hợp đó, có thể mô tả phần đuôi bằng sequence có số lượng phần tử bằng 0, tính offset bắt đầu của mảng, rồi dùng `arrayElementVarHandle(...)` trên layout của phần tử:

```java
static final StructLayout POLYGON_HEADER = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("count"),
        MemoryLayout.paddingLayout(4),
        MemoryLayout.sequenceLayout(0, POINT).withName("points")
);

static final long POINTS_OFFSET = POLYGON_HEADER.byteOffset(
        PathElement.groupElement("points")
);

static final VarHandle POINT_ARRAY_Y = POINT.arrayElementVarHandle(
        PathElement.groupElement("y")
);
```

`arrayElementVarHandle(...)` tạo handle truy cập các phần tử liên tiếp có layout gốc là `POINT`. Handle này có coordinate `MemorySegment`, `long` offset cơ sở, `long` chỉ số mảng, sau đó là các coordinate của open path element bên trong layout phần tử (nếu có). Ở ví dụ trên, path bên trong `POINT` chỉ chọn member `y`, nên lời gọi có dạng:

```java
double y = (double) POINT_ARRAY_Y.get(polygon, POINTS_OFFSET, (long) i);
```

Offset cơ sở là `POINTS_OFFSET`, chỉ tới đầu mảng flexible. Chỉ số `i` xác định phần tử nào trong mảng cần truy cập. Segment phải đủ lớn để chứa toàn bộ phần header và số phần tử thực tế; `arrayElementVarHandle` không tự cấp phát hoặc tự mở rộng vùng nhớ.

Với dữ liệu native thực tế, cần biết số phần tử, kích thước vùng nhớ và quy tắc căn chỉnh từ hợp đồng của thư viện native. Không được suy ra rằng một flexible array có thể truy cập an toàn chỉ vì layout header mô tả được offset của nó.

## 9. Layout path có con trỏ và `dereferenceElement()`

Một cấu trúc native có thể chứa trường địa chỉ trỏ tới một cấu trúc khác. Nếu `AddressLayout` có target layout, path element `dereferenceElement()` có thể đi theo địa chỉ đó để chọn trường bên trong đối tượng được trỏ tới.

Ví dụ sau khai báo một trường địa chỉ trỏ tới `POINT`, rồi tạo handle để đọc trường `y` của điểm được trỏ tới:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

static final StructLayout RECTANGLE_WITH_POINTER = MemoryLayout.structLayout(
        ValueLayout.ADDRESS.withTargetLayout(POINT).withName("pointAddress")
);

static final VarHandle POINTED_Y = RECTANGLE_WITH_POINTER.varHandle(
        PathElement.groupElement("pointAddress"),
        PathElement.dereferenceElement(),
        PathElement.groupElement("y")
);
```

Ở đây, `pointAddress` là một `AddressLayout` có target layout `POINT`. `withTargetLayout(...)` là restricted method vì việc diễn giải một địa chỉ thô thành segment có thể gây mất an toàn bộ nhớ. Khi chạy mã dùng phương thức này, cần cấp quyền native access, ví dụ `--enable-native-access=ALL-UNNAMED` cho mã trong unnamed module. Khi truy cập, FFM API đọc địa chỉ, tạo segment tương ứng với target layout rồi tiếp tục chọn member `y`.

Việc dereference không xác minh rằng con trỏ native đang trỏ tới vùng nhớ hợp lệ theo hợp đồng nghiệp vụ. Chương trình vẫn phải bảo đảm địa chỉ có thể truy cập, vùng đích còn tồn tại và kích thước target layout mô tả đúng dữ liệu. Khi làm việc với con trỏ không đáng tin cậy hoặc thư viện native có vòng đời riêng, cần kiểm tra quyền sở hữu và thời gian tồn tại của vùng nhớ.

## 10. Căn chỉnh, giới hạn và vòng đời bộ nhớ

Layout path giúp tính vị trí, nhưng một `VarHandle` truy cập thành công chỉ khi các điều kiện bộ nhớ được thỏa mãn:

- Segment phải có đủ kích thước cho vùng giá trị tại offset đã tính.
- Địa chỉ truy cập phải thỏa căn chỉnh mà layout gốc yêu cầu.
- Thread hiện tại phải được phép truy cập segment theo scope của nó.
- Scope của segment phải còn sống; segment gắn với arena đã đóng không còn dùng được.
- Khi ghi, segment không được ở chế độ chỉ đọc.
- Các coordinate chỉ số phải chọn đúng phần tử và không làm phép tính offset bị tràn.

Những lỗi thường gặp:

| Lỗi | Nguyên nhân thường gặp |
| --- | --- |
| `IllegalArgumentException` khi tạo handle | Path không hợp lệ hoặc path không kết thúc ở `ValueLayout`. |
| `IndexOutOfBoundsException` | Offset hoặc chỉ số dẫn tới vùng ngoài giới hạn segment. |
| `IllegalStateException` | Arena hoặc scope đã đóng. |
| `WrongThreadException` | Truy cập segment confined từ thread không sở hữu nó. |
| `IllegalArgumentException` khi ghi | Segment chỉ đọc hoặc địa chỉ truy cập không thỏa alignment. |

Không nên dùng `VarHandle` như cách thay thế cho việc xác định ABI. `MemoryLayout` cần mô tả đúng thứ tự trường, kích thước, byte order và alignment của cấu trúc mà dữ liệu thực tế tuân theo. Với struct C, có thể phải thêm `paddingLayout(...)`, đặt `withByteAlignment(...)` hoặc chọn `ValueLayout` có byte order thích hợp. Đối chiếu với header và quy tắc ABI của nền tảng trước khi truy cập dữ liệu native.

## 11. Khi nào dùng `byteOffset`, `select`, `varHandle` hay `sliceHandle`?

Các phương thức trên giải quyết những nhu cầu khác nhau:

| Phương thức | Khi nên dùng |
| --- | --- |
| `select(path...)` | Cần lấy layout con để kiểm tra kích thước, alignment, tên hoặc kiểu. |
| `byteOffset(path...)` | Cần tính offset cố định của một thành phần. |
| `byteOffsetHandle(path...)` | Cần tính offset với chỉ số sequence được truyền động khi chạy. |
| `varHandle(path...)` | Cần đọc/ghi một giá trị tại vị trí được chọn trong layout. |
| `sliceHandle(path...)` | Cần lấy một `MemorySegment` con tương ứng với layout được chọn. |
| `arrayElementVarHandle(path...)` | Cần truy cập các phần tử liên tiếp có cùng layout, đặc biệt hữu ích với mảng độ dài thay đổi. |

Nếu mục tiêu là đọc một trường nguyên thủy trong cấu trúc lồng nhau, `varHandle(...)` thường là lựa chọn trực tiếp. Nếu cần truyền cả một cấu trúc con cho hàm khác, `sliceHandle(...)` có thể phù hợp hơn vì nó tạo segment con thay vì đọc một giá trị đơn.

## 12. Quy trình áp dụng trong dự án

Khi tích hợp dữ liệu native hoặc định dạng nhị phân vào Java, có thể thực hiện theo các bước:

1. **Xác định cấu trúc nguồn**: đọc header C, đặc tả file hoặc hợp đồng dữ liệu để biết thứ tự trường, kiểu, kích thước và alignment.
2. **Mô tả layout từ trong ra ngoài**: tạo `ValueLayout`, ghép thành `StructLayout`/`UnionLayout`, rồi tạo `SequenceLayout` cho các dãy.
3. **Đặt tên member cần truy cập**: dùng `withName(...)` để layout path có thể chọn bằng tên.
4. **Xây dựng path**: kết hợp `groupElement(...)`, `sequenceElement(...)` và `dereferenceElement()` khi cấu trúc yêu cầu.
5. **Tạo handle dùng lại**: khai báo `VarHandle` ở nơi phù hợp, thường là `static final`.
6. **Truyền đúng coordinate**: segment, base offset và chỉ số cho từng open path element.
7. **Quản lý vòng đời**: chỉ truy cập segment khi arena/scope còn sống và thread được phép truy cập.
8. **Kiểm thử với dữ liệu thật**: đối chiếu offset, giá trị đọc/ghi với cấu trúc native hoặc byte sequence đã biết.

## 13. Kiến thức cần nhớ

- `MemoryLayout` mô tả cấu trúc bộ nhớ; layout path chọn một layout con bên trong cấu trúc đó.
- `groupElement(...)` đi qua member của struct/union; `sequenceElement(...)` đi qua phần tử của sequence.
- `sequenceElement()` là open path element và tạo thêm coordinate chỉ số kiểu `long` cho `VarHandle`.
- `MemoryLayout.varHandle(...)` tạo handle đọc/ghi value layout được chọn; coordinate cơ bản gồm segment và base offset.
- `byteOffset(...)`, `select(...)` và `sliceHandle(...)` giải quyết nhu cầu tính offset, chọn layout và lấy segment con.
- `arrayElementVarHandle(...)` hữu ích khi truy cập các phần tử liên tiếp, nhất là flexible array member.
- Cần mô tả đúng alignment, padding, byte order và kích thước; đồng thời quản lý giới hạn và vòng đời của `MemorySegment`.
- FFM API là API chính thức từ JDK 22 qua JEP 454 và vẫn là nền tảng hiện hành để làm việc với foreign memory trong Java.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — chuẩn hóa FFM API trong JDK 22.
- [MemoryLayout — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html) — layout path, `select`, `byteOffset`, `varHandle`, `sliceHandle` và `arrayElementVarHandle`.
- [MemoryLayout.PathElement — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html) — các path element cho group, sequence và dereference.
- [Package `java.lang.foreign` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html) — API FFM hiện hành.
- [Core Libraries Developer Guide, Chapter 12: Memory Layouts and Structured Access](https://docs.oracle.com/en/java/javase/26/core/java-core-libraries-developer-guide.pdf) — ví dụ thực tế dùng layout path và VarHandle.
