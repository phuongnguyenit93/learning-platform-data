# Đọc cấu trúc lồng nhau và mảng cấu trúc bằng đường dẫn layout

## 1. Bài toán: đi từ cấu trúc C đến vùng nhớ Java

Trong lập trình tương tác Java/native, dữ liệu thường không đơn giản là một số `int` hoặc một mảng `byte[]`. Thư viện C có thể trả về **struct chứa struct**, **mảng các struct**, hoặc **struct chứa mảng các struct**. Muốn đọc đúng các trường này ở Java, cần biết **kích thước, thứ tự, alignment và offset** của từng phần tử trong bộ nhớ.

Từ **JDK 22**, Foreign Function & Memory API (FFM, package `java.lang.foreign`) cung cấp một cách mô tả và truy cập dữ liệu như vậy:

- `MemoryLayout`: mô tả hình dạng và kích thước của vùng nhớ.
- `StructLayout`: các trường nằm nối tiếp nhau, theo thứ tự khai báo và padding do bạn mô tả.
- `SequenceLayout`: các phần tử giống nhau lặp lại thành một dãy.
- `ValueLayout`: kiểu dữ liệu lá (ví dụ `JAVA_INT`, `JAVA_LONG`).
- `MemoryLayout.PathElement`: các bước **đi theo đường dẫn layout** tới trường lồng nhau.
- `varHandle(...)`: tạo một `VarHandle` để đọc/ghi một trường nguyên thủy ở vị trí được chọn.
- `byteOffset(...)` và `byteOffsetHandle(...)`: tính vị trí **theo byte** của trường hoặc phần tử.
- `select(...)` và `sliceHandle(...)`: chọn layout con hoặc một view trên vùng nhớ con.

**Mục tiêu của bài:** đọc được `records[1].vertices[2].y` trong bộ nhớ mà **không phải tự cộng các offset “ma thuật”**; đồng thời hiểu khi nào một đường dẫn có chỉ số cố định, khi nào cần truyền chỉ số động, và vì sao padding/ABI quan trọng.

### 1.1. Phạm vi phiên bản và sự khác biệt với JNI

Các API ở đây là **FFM ổn định từ JDK 22** (JEP 454). Vì vậy ví dụ dùng `java.lang.foreign.MemoryLayout`, `MemorySegment`, `Arena`, `ValueLayout` và `java.lang.invoke.VarHandle` sẽ **biên dịch bằng JDK 22+**, không phải mã tương thích thuần Java 17. Trên JDK cũ từng có các phiên bản incubator/preview khác cú pháp; không trộn mã cũ với API ở đây.

Bài minh họa với bộ nhớ native do Java cấp phát và một C `struct` dùng làm mô hình tương đương; **không cần biên dịch C hay gọi JNI** để chạy ví dụ Java. Nếu dùng layout để đọc vùng nhớ trả từ thư viện C thật, phải **kiểm chứng ABI** trên OS, CPU và compiler đích, không suy luận rằng mọi C struct có padding giống nhau.

## 2. Một ví dụ trực quan: struct trong struct, mảng struct trong struct

Xét cấu trúc C dùng kiểu số có kích thước rõ ràng:

```c
#include <stdint.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    int32_t id;
    Point origin;
    Point vertices[3];
} Record;

/* Một vùng bộ nhớ có thể chứa Record records[2]; */
```

Trong C, cú pháp:

```c
records[1].vertices[2].y
```

có nghĩa là:

1. Bắt đầu ở **mảng `records`**.
2. Chọn **`Record` thứ hai** (`[1]`).
3. Chọn trường **`vertices`** của Record.
4. Chọn **`Point` thứ ba** (`[2]`) trong vertices.
5. Chọn trường nguyên thủy **`y`** trong Point ấy.

Ta muốn mô phỏng chính con đường này trong FFM mà không phải đếm offset tay ở mỗi lần đọc.

### 2.1. Sơ đồ layout kỳ vọng

Giả sử ABI đích đặt `int32_t` ở 4 byte, căn chỉnh 4 byte và các trường của ví dụ không phát sinh padding phụ:

```text
Point (8 bytes):
  +0   x: int32 (4)
  +4   y: int32 (4)

Record (36 bytes):
  +0   id: int32 (4)
  +4   origin: Point (8)
       +4  origin.x
       +8  origin.y
  +12  vertices: Point[3] (24)
       +12 vertices[0].x
       +16 vertices[0].y
       +20 vertices[1].x
       +24 vertices[1].y
       +28 vertices[2].x
       +32 vertices[2].y

records = Record[2] (72 bytes):
  record[0]: base +0
  record[1]: base +36

records[1].vertices[2].y:
  36 + 12 + 2 * 8 + 4 = 68 bytes
```

Những con số này **chỉ là kết quả cho layout đã mô tả**; FFM có thể tính chúng để code khỏi phải tự cộng `36 + 12 + 16 + 4`.

### 2.2. Mô hình hóa bằng Java MemoryLayout

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

StructLayout record = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        point.withName("origin"),
        MemoryLayout.sequenceLayout(3, point).withName("vertices")
);

SequenceLayout records = MemoryLayout.sequenceLayout(2, record);
```

Đây là **đoạn minh họa nằm bên trong class hoặc method Java**, chưa phải file có `main`; chương trình chạy đầy đủ ở mục 7.

Hai chi tiết quan trọng:

- `withName("x")`, `withName("vertices")` gán tên để `groupElement("...")` tìm được trường. Tên nằm trong metadata của layout, **không được chép vào bộ nhớ**.
- `sequenceLayout(2, record)` mô tả **2 phần tử Record**. `sequenceLayout(3, point)` mô tả **3 phần tử Point** bên trong từng Record. Hai mức sequence sẽ tạo **hai chỉ số động** khi dùng đường dẫn mở.

## 3. Ba nhóm layout và PathElement hoạt động thế nào?

Một đường dẫn layout là một chuỗi các bước đi từ layout ngoài cùng tới phần tử con. Các bước có thể là:

| PathElement | Dùng trên layout nào? | Ý nghĩa |
| --- | --- | --- |
| `groupElement("name")` | `StructLayout` hoặc `UnionLayout` | Chọn trường trong group có tên `name` |
| `groupElement(index)` | `GroupLayout` | Chọn trường theo chỉ số trong danh sách member layout |
| `sequenceElement(index)` | `SequenceLayout` | Chọn một phần tử có **chỉ số cố định** |
| `sequenceElement()` | `SequenceLayout` | Chọn phần tử với **chỉ số động** — một *open path element* |
| `sequenceElement(start, step)` | `SequenceLayout` | Chọn phần tử qua chỉ số động theo progression `start + i * step` |
| `dereferenceElement()` | `AddressLayout` có target layout | Theo con trỏ tới layout đích (phạm vi nâng cao) |

`groupElement` chọn **member của struct/union**; `sequenceElement` chọn **phần tử trong sequence**. Chúng **không hoán đổi được**. Nếu đang ở `StructLayout` mà gọi `sequenceElement`, đường dẫn không hợp lệ. Nếu đang ở `SequenceLayout` mà gọi `groupElement("x")` trước khi chọn phần tử, cũng không hợp lệ.

### 3.1. Đường dẫn cho một trường lồng nhau

`records[1].vertices[2].y` tương ứng:

```java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long offset = records.byteOffset(
        sequenceElement(1),
        groupElement("vertices"),
        sequenceElement(2),
        groupElement("y")
);
// offset = 68
```

Đây là **trích đoạn**, yêu cầu biến `records` của mục 2 đã tồn tại. Các tham số đúng thứ tự **từ ngoài vào trong**.

- `sequenceElement(1)` chọn Record thứ hai.
- `groupElement("vertices")` chọn dãy Point của Record đó.
- `sequenceElement(2)` chọn Point thứ ba.
- `groupElement("y")` chọn int thứ hai của Point.

Kết quả `byteOffset` là **số byte** tính từ gốc của `records`, không phải chỉ số phần tử, không phải địa chỉ tuyệt đối.

### 3.2. Vì sao đường dẫn phải có tên?

`groupElement("origin")` tìm field có tên `origin`. Nếu layout khai báo:

```java
MemoryLayout.structLayout(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT
);
```

thì không có tên `x` hay `y` để lookup; hoặc cần gán `withName`, hoặc dùng `groupElement(index)`. Cách chọn theo tên dễ bảo trì hơn khi thêm padding hoặc thay đổi thứ tự field, nhưng **không thay thế** việc mô tả ABI chính xác.

### 3.3. Chỉ chọn một layout con, chưa đọc dữ liệu

`select` trả về **định nghĩa layout con**, không truy cập bộ nhớ:

```java
MemoryLayout yLayout = records.select(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);

System.out.println(yLayout.byteSize()); // 4
```

Ở đây dùng hai `sequenceElement()` mở nhưng `select` vẫn chọn được loại layout lá, vì tất cả phần tử tương ứng có cùng cấu trúc `Point`. Kết quả của `select` là layout `int`, chưa phải giá trị `y` của bất kỳ Record nào.

## 4. Đường dẫn cố định và đường dẫn mở

### 4.1. Đường dẫn cố định

Nếu biết sẵn mọi chỉ số sequence:

```java
long fixed = records.byteOffset(
        sequenceElement(1),
        groupElement("vertices"),
        sequenceElement(2),
        groupElement("y")
);
```

FFM có thể tính ngay thành một `long` cụ thể (**68** trong ví dụ). Không phải truyền thêm chỉ số trong lúc đọc.

### 4.2. Đường dẫn mở

Khi xử lý mọi Record và mọi Point, không thể viết một field offset cố định cho tất cả. Dùng hai bước mở:

```java
VarHandle vertexY = records.varHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
```

`vertexY` có các tọa độ truy cập:

```text
(MemorySegment segment, long baseOffset,
 long recordIndex, long vertexIndex) -> int
```

Để đọc `record[1].vertices[2].y`:

```java
int y = (int) vertexY.get(segment, 0L, 1L, 2L);
```

Lưu ý **tọa độ `baseOffset` luôn là `long`**, kể cả bằng 0; hai chỉ số sequence cũng là `long`. Ví dụ dùng `0L, 1L, 2L` chứ không sử dụng bừa các literal `int` trong signature strongly typed của `VarHandle`.

### 4.3. Đếm số tọa độ của VarHandle

| Đường dẫn | Số `sequenceElement()` mở | Tọa độ đọc/ghi (không tính giá trị `set`) |
| --- | ---: | --- |
| `record.varHandle(groupElement("id"))` | 0 | `segment, baseOffset` |
| `records.varHandle(sequenceElement(), groupElement("id"))` | 1 | `segment, baseOffset, recordIndex` |
| `records.varHandle(sequenceElement(), groupElement("origin"), groupElement("x"))` | 1 | `segment, baseOffset, recordIndex` |
| `records.varHandle(sequenceElement(), groupElement("vertices"), sequenceElement(), groupElement("y"))` | 2 | `segment, baseOffset, recordIndex, vertexIndex` |
| `records.varHandle(sequenceElement(1), groupElement("vertices"), sequenceElement(2), groupElement("y"))` | 0 | `segment, baseOffset` |

Đối với `VarHandle.set`, thêm **một đối số cuối cùng** là giá trị theo kiểu của selected `ValueLayout`: ví dụ `int` đối với `JAVA_INT`.

### 4.4. Không gọi `byteOffset` với đường dẫn mở

Ví dụ **sai**:

```java
// Sai: byteOffset yêu cầu offset cố định.
long offset = records.byteOffset(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
```

Vì thiếu chỉ số record và vertex, `byteOffset` không có một hằng offset duy nhất để trả; API sẽ từ chối đường dẫn có open path elements. Nếu cần offset động mà không muốn tự tính, dùng **`byteOffsetHandle`**:

```java
import java.lang.invoke.MethodHandle;

MethodHandle offsetHandle = records.byteOffsetHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);

long offset = (long) offsetHandle.invokeExact(0L, 1L, 2L);
// 68
```

Đây là trích đoạn đặt trong phương thức **khai báo `throws Throwable`** hoặc xử lý exception phù hợp. `MethodHandle` có signature nhận `baseOffset` và hai chỉ số động, trả `long`; `invokeExact` yêu cầu đúng kiểu tại điểm gọi.

## 5. Đường dẫn tới một field lá khác với đường dẫn tới cả struct

### 5.1. `varHandle` chỉ nhắm tới ValueLayout

Ví dụ hợp lệ:

```java
VarHandle originX = records.varHandle(
        sequenceElement(),
        groupElement("origin"),
        groupElement("x")
);
```

Kết thúc tại trường `x` là `ValueLayout.JAVA_INT`. `VarHandle.get` đọc ra `int`.

Nếu đường dẫn kết thúc ở **cả `origin` là `StructLayout`**, lời gọi `varHandle` không hợp lệ vì selected layout không phải `ValueLayout`. Để lấy layout con, dùng `select`; để lấy **vùng bộ nhớ con** có thể dùng `asSlice` hoặc **`sliceHandle`**.

### 5.2. Chọn một struct con bằng offset và slice

```java
long originOffset = records.byteOffset(
        sequenceElement(1),
        groupElement("origin")
);
MemorySegment originView = segment.asSlice(
        originOffset, point.byteSize()
);
```

`originView` có **8 byte** mô tả Point của Record thứ hai. Đây là **view trên cùng backing memory**, không phải copy. Có thể đọc `originView` bằng một `VarHandle` được tạo từ `point`:

```java
VarHandle pointX = point.varHandle(groupElement("x"));
int x = (int) pointX.get(originView, 0L);
// 30 trong ví dụ chạy đầy đủ ở mục 7
```

Kết quả quan sát sau này phụ thuộc memory còn sống; đừng giữ `originView` để truy cập sau khi `Arena` sở hữu segment gốc đã bị đóng.

### 5.3. `sliceHandle` cho cấu trúc con với chỉ số mở

Nếu cần lấy nhiều `Point` trong mảng:

```java
MethodHandle pointSlice = records.sliceHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement()
);

MemorySegment onePoint = (MemorySegment) pointSlice.invokeExact(
        segment, 0L, 1L, 2L);
```

Đoạn này được gọi trong một phương thức `throws Throwable`, yêu cầu `records`/`segment` đã khai báo. `onePoint` là view dài **`point.byteSize()`**, tương ứng `records[1].vertices[2]`, và dùng chung backing với segment gốc. Phần tử con không tự được sao chép.

## 6. Tại sao phải tính alignment và padding?

Cấu trúc C thường có **padding** để thỏa alignment của trường và của struct. `MemoryLayout.structLayout` **không tự động chèn padding** như compiler C. Layout Java phải mô tả chính các byte có thật trong C ABI.

### 6.1. C struct có khoảng đệm

Một ví dụ C:

```c
#include <stdint.h>

typedef struct {
    uint8_t  kind;
    int32_t  value;
} Entry;
```

Trên một ABI phổ biến mà `int32_t` căn chỉnh 4 byte:

```text
offset 0: kind       (1 byte)
offset 1..3: padding (3 bytes)
offset 4..7: value   (4 bytes)
sizeof(Entry) = 8 bytes
```

Muốn khớp trên hệ đó, mô tả rõ phần đệm:

```java
StructLayout entry = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);
```

Chọn `groupElement("value")` sẽ cho offset **4**, còn các `Entry` trong mảng có stride **8**.

**Cảnh báo tương thích:** `uint8_t`/`int32_t` có kích thước byte rõ nhưng **alignment và padding do C ABI/compiler quy định**. Trước khi truy cập dữ liệu C thật, kiểm tra bằng `sizeof`, `alignof`, `offsetof` hoặc header/layout sinh bằng công cụ đáng tin (ví dụ `jextract` nếu phù hợp). Không tuyên bố mọi ABI đều có kích thước Entry = 8.

### 6.2. Trường hợp thứ tự không hợp lệ

Ví dụ:

```java
// Không tự động được thêm padding.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("count")
);
```

Vì `count` bị đặt tại byte offset 1 nhưng `JAVA_INT` đòi alignment 4, việc dựng layout có thể bị từ chối. Khắc phục bằng `paddingLayout(3)` **nếu đó là layout thực**, hoặc dùng một `ValueLayout` với alignment nới lỏng **nếu ABI thực sự packed**. Không tự làm packed layout chỉ để tránh exception nếu C side vẫn dùng alignment tự nhiên.

### 6.3. Padding của struct ảnh hưởng stride

`MemoryLayout.sequenceLayout(n, structLayout)` dùng `structLayout.byteSize()` làm **stride** của các phần tử. Nếu bạn quên padding cuối struct, phần tử thứ hai bắt đầu sai và mọi trường của `array[1]` trở đi có thể được đọc nhầm. Cần đối chiếu **cả sizeof(struct)**, không chỉ offsetof vài trường đầu.

Với ví dụ `Record` chỉ chứa `int32_t`/`Point` nên trên ABI giả định sizeof(Point)=8, sizeof(Record)=36, các bước stride phù hợp. Với `char`, `double`, bit field, packed struct hay union, cần phân tích ABI kỹ hơn.

## 7. Chương trình Java 22+ chạy được: đọc cả nested struct và array of structs

Đây là ví dụ độc lập, sử dụng đúng cấu trúc `Point` và `Record` ở mục 2, và **không dùng JNI**. Dữ liệu được cấp phát off-heap bằng `Arena.ofConfined()`, ghi rồi đọc bằng các var handles có **đường dẫn layout**.

### 7.1. Tệp `NestedLayoutDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class NestedLayoutDemo {
    private static final StructLayout POINT = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("x"),
            ValueLayout.JAVA_INT.withName("y")
    );

    private static final StructLayout RECORD = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("id"),
            POINT.withName("origin"),
            MemoryLayout.sequenceLayout(3, POINT).withName("vertices")
    );

    private static final SequenceLayout RECORDS =
            MemoryLayout.sequenceLayout(2, RECORD);

    // Một chỉ số sequence mở: Record số mấy?
    private static final VarHandle ID = RECORDS.varHandle(
            sequenceElement(), groupElement("id")
    );
    private static final VarHandle ORIGIN_X = RECORDS.varHandle(
            sequenceElement(),
            groupElement("origin"),
            groupElement("x")
    );
    private static final VarHandle ORIGIN_Y = RECORDS.varHandle(
            sequenceElement(),
            groupElement("origin"),
            groupElement("y")
    );

    // Hai chỉ số mở: Record nào? Vertex nào?
    private static final VarHandle VERTEX_X = RECORDS.varHandle(
            sequenceElement(),
            groupElement("vertices"),
            sequenceElement(),
            groupElement("x")
    );
    private static final VarHandle VERTEX_Y = RECORDS.varHandle(
            sequenceElement(),
            groupElement("vertices"),
            sequenceElement(),
            groupElement("y")
    );

    private NestedLayoutDemo() {}

    public static void main(String[] args) throws Throwable {
        System.out.println("pointBytes=" + POINT.byteSize());
        System.out.println("recordBytes=" + RECORD.byteSize());
        System.out.println("arrayBytes=" + RECORDS.byteSize());

        // Offset cố định, tính từ layout gốc.
        long originY = RECORD.byteOffset(
                groupElement("origin"), groupElement("y")
        );
        long lastY = RECORDS.byteOffset(
                sequenceElement(1),
                groupElement("vertices"),
                sequenceElement(2),
                groupElement("y")
        );
        System.out.println("offset origin.y=" + originY);
        System.out.println("offset records[1].vertices[2].y=" + lastY);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(RECORDS);

            for (long i = 0; i < 2; i++) {
                int id = (i == 0) ? 101 : 202;
                int baseX = (i == 0) ? 10 : 30;
                int baseY = (i == 0) ? 20 : 40;

                ID.set(data, 0L, i, id);
                ORIGIN_X.set(data, 0L, i, baseX);
                ORIGIN_Y.set(data, 0L, i, baseY);

                for (long j = 0; j < 3; j++) {
                    VERTEX_X.set(data, 0L, i, j, baseX + (int) j + 1);
                    VERTEX_Y.set(data, 0L, i, j, baseY + (int) j + 1);
                }
            }

            for (long i = 0; i < 2; i++) {
                int id = (int) ID.get(data, 0L, i);
                int ox = (int) ORIGIN_X.get(data, 0L, i);
                int oy = (int) ORIGIN_Y.get(data, 0L, i);
                int vx = (int) VERTEX_X.get(data, 0L, i, 2L);
                int vy = (int) VERTEX_Y.get(data, 0L, i, 2L);
                System.out.println("row[" + i + "] id=" + id
                        + " origin=(" + ox + "," + oy + ")"
                        + " last=(" + vx + "," + vy + ")");
            }

            int openValue = (int) VERTEX_Y.get(data, 0L, 1L, 2L);

            // Cùng trường, nhưng chỉ số Record/Vertex là cố định.
            VarHandle fixedY = RECORDS.varHandle(
                    sequenceElement(1),
                    groupElement("vertices"),
                    sequenceElement(2),
                    groupElement("y")
            );
            int fixedValue = (int) fixedY.get(data, 0L);

            MethodHandle dynamicOffset = RECORDS.byteOffsetHandle(
                    sequenceElement(),
                    groupElement("vertices"),
                    sequenceElement(),
                    groupElement("y")
            );
            long computed = (long) dynamicOffset.invokeExact(
                    0L, 1L, 2L);

            System.out.println("openY=" + openValue);
            System.out.println("fixedY=" + fixedValue);
            System.out.println("dynamicOffset=" + computed);

            MemoryLayout selected = RECORDS.select(
                    sequenceElement(),
                    groupElement("vertices"),
                    sequenceElement(),
                    groupElement("y")
            );
            System.out.println("selectedBytes=" + selected.byteSize());

            // Lấy view của Record thứ hai, rồi dùng path cục bộ.
            long record1Offset = RECORDS.byteOffset(
                    sequenceElement(1));
            MemorySegment record1 = data.asSlice(
                    record1Offset, RECORD.byteSize());
            VarHandle localOriginX = RECORD.varHandle(
                    groupElement("origin"),
                    groupElement("x")
            );
            System.out.println("sliceOriginX="
                    + (int) localOriginX.get(record1, 0L));
        }
    }
}
```

Các `VarHandle` dùng làm hằng `static final` để không phải dựng lại path cho từng vòng lặp. `RECORDS.varHandle(...)` trả một “công thức truy cập” chứ không tự lưu một con trỏ tới `data`. Khi gọi `get`/`set` bạn truyền **segment sống**, **base offset** và các **chỉ số mở** tương ứng.

### 7.2. Biên dịch/chạy trên JDK 22+

Đặt file trong thư mục làm việc:

```bash
javac NestedLayoutDemo.java
java NestedLayoutDemo
```

Không cần `--enable-preview`, `--enable-native-access` hay native compiler cho phần code này. `MemoryLayout`, `Arena` và `MemorySegment` ổn định từ JDK 22; nếu compiler báo `package java.lang.foreign does not exist`, kiểm tra đúng `javac -version` và `java -version` đều đang dùng JDK hỗ trợ.

### 7.3. Kết quả stdout chính xác

```text
pointBytes=8
recordBytes=36
arrayBytes=72
offset origin.y=8
offset records[1].vertices[2].y=68
row[0] id=101 origin=(10,20) last=(13,23)
row[1] id=202 origin=(30,40) last=(33,43)
openY=43
fixedY=43
dynamicOffset=68
selectedBytes=4
sliceOriginX=30
```

### 7.4. Vì sao kết quả như vậy?

- `Point` có hai `JAVA_INT`, mỗi trường 4 byte → **8 byte**.
- `Record` chứa `id` 4 + `origin` 8 + `vertices` (3 × 8) 24 → **36 byte**.
- `RECORDS` có hai Record → **72 byte**.
- `origin.y` trong một Record nằm sau `id` 4 byte và `origin.x` 4 byte → **offset 8**.
- `records[1]` bắt đầu ở byte 36. `vertices` ở offset 12 trong Record; Point thứ ba có offset 2×8; `y` có offset 4 → **68**.
- Với Record thứ hai, `baseX=30`, `baseY=40`; vertex thứ ba chứa `x=33`, `y=43`.
- `VERTEX_Y` (path mở) và `fixedY` (path cố định) chọn cùng vị trí nên đều trả `43`.
- `byteOffsetHandle` nhận các chỉ số động và cho kết quả offset `68`.
- `select` tìm `ValueLayout.JAVA_INT` có `byteSize=4`, không truy cập dữ liệu.
- `asSlice` từ offset Record thứ hai tạo view 36 byte. Đọc `origin.x` bằng path bắt đầu từ `RECORD` trả `30`.

**Phân biệt:** `records[1]` là **chỉ số phần tử**, còn `68` là **byte offset**. Bạn không cần tính byte 68 thủ công trong code ứng dụng nếu luôn dùng path/VarHandle.

## 8. Chương trình thứ hai: struct có padding và mảng struct

Đoạn này là một ví dụ **độc lập khác** để làm rõ tại sao `groupElement("value")` phải tính cả padding và tại sao mảng struct có stride bằng `sizeof(struct)`.

### 8.1. Tệp `PaddedStructArrayDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class PaddedStructArrayDemo {
    private PaddedStructArrayDemo() {}

    public static void main(String[] args) {
        StructLayout entry = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("kind"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("value")
        );
        SequenceLayout entries = MemoryLayout.sequenceLayout(2, entry);

        VarHandle kind = entries.varHandle(
                sequenceElement(), groupElement("kind")
        );
        VarHandle value = entries.varHandle(
                sequenceElement(), groupElement("value")
        );

        System.out.println("entryBytes=" + entry.byteSize());
        System.out.println("valueOffset="
                + entry.byteOffset(groupElement("value")));
        System.out.println("entries[1].valueOffset="
                + entries.byteOffset(
                        sequenceElement(1), groupElement("value")));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(entries);

            kind.set(memory, 0L, 0L, (byte) 7);
            value.set(memory, 0L, 0L, 1234);
            kind.set(memory, 0L, 1L, (byte) 8);
            value.set(memory, 0L, 1L, 5678);

            for (long i = 0; i < 2; i++) {
                byte k = (byte) kind.get(memory, 0L, i);
                int v = (int) value.get(memory, 0L, i);
                System.out.println("entry[" + i + "]=(" + k + "," + v + ")");
            }
        }
    }
}
```

Chạy:

```bash
javac PaddedStructArrayDemo.java
java PaddedStructArrayDemo
```

Stdout:

```text
entryBytes=8
valueOffset=4
entries[1].valueOffset=12
entry[0]=(7,1234)
entry[1]=(8,5678)
```

Vì `paddingLayout(3)` đệm ba byte sau `kind`, `value` nằm ở offset 4. Mỗi Entry dài 8 byte, nên `entries[1].value` nằm ở byte **8 + 4 = 12**. Nếu bỏ padding và chọn offset 1 trong layout thì sẽ không phản ánh ABI mẫu; thậm chí layout có thể bị từ chối do alignment không tương thích.

## 9. Khai báo và đọc mảng nhiều tầng lồng nhau

Hai tầng sequence **không nhất thiết** phải xen giữa bởi struct. Ví dụ bảng gồm 2 hàng, mỗi hàng chứa 3 Point:

```java
SequenceLayout grid = MemoryLayout.sequenceLayout(
        2,
        MemoryLayout.sequenceLayout(3, point)
);

VarHandle yHandle = grid.varHandle(
        sequenceElement(), // row
        sequenceElement(), // column
        groupElement("y")
);

int y = (int) yHandle.get(segment, 0L, 1L, 2L);
```

Đây là **mã minh họa**, với `point` là layout từ mục 2 và `segment` đã được cấp phát ít nhất `grid.byteSize()` byte, sống/đúng alignment. Đường dẫn là:

```text
grid[row=1][column=2].y
       |        |     |
  sequence   sequence  group
```

Hai bước `sequenceElement()` mở tương ứng **hai tọa độ `long`** theo đúng thứ tự xuất hiện. Nếu hoán đổi `rowIndex` và `columnIndex`, code có thể đọc sai vị trí hoặc rơi ngoài phạm vi.

Với **struct chứa mảng các struct**:

```java
VarHandle vertexY = record.varHandle(
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
int y = (int) vertexY.get(recordSegment, 0L, 2L);
```

Vì gốc là **một Record** (không phải cả `records`), chỉ có **một** sequence index mở. Nếu thay gốc bằng `RECORDS`, phải thêm `sequenceElement()` ở đầu và truyền thêm chỉ số Record.

## 10. Root layout, base offset và cách tái sử dụng handle

Một `VarHandle` tạo từ layout chứa đủ thông tin để **tính offset tương đối** của selected field. Tuy nhiên nó không biết bạn đang thao tác trên vùng nhớ nào cho đến khi truyền `MemorySegment` vào.

### 10.1. Tại sao luôn có `baseOffset`?

Theo đặc tả JDK 22, `varHandle(PathElement...)` nhận:

```text
MemorySegment, long baseOffset, [long dynamicSequenceIndices...]
```

Ví dụ dùng root là `RECORD`, nhưng đang đọc Record thứ hai nằm trong một buffer bao gồm hai Record:

```java
VarHandle id = record.varHandle(groupElement("id"));

long record1Offset = record.byteSize();  // 36
int record1Id = (int) id.get(fullSegment, record1Offset);
```

Đây là **trích đoạn** với `record`/`fullSegment` đã khai báo. Vì `id` chỉ là field trong một Record, bạn truyền base offset 36 để đọc Record thứ hai. Một cách khác là lấy `fullSegment.asSlice(36,36)` rồi gọi `id.get(slice, 0L)`.

### 10.2. Có nên cache VarHandle không?

Có. Nếu layout không thay đổi, định nghĩa:

```java
static final VarHandle FIELD = LAYOUT.varHandle(
        sequenceElement(), groupElement("field")
);
```

trong một class có `LAYOUT` tương ứng thường dễ bảo trì hơn dựng lại layout path trong mỗi phần tử của vòng lặp. Thay đổi layout schema thì cần tạo lại handle cùng schema; không thể giữ handle cũ rồi tự giả định offset không đổi.

### 10.3. `byteOffsetHandle` không dereference pointer

`byteOffsetHandle` tính offset từ **gốc layout trong cùng vùng bộ nhớ liên tiếp**, không phải một phép dereference để theo con trỏ C. Nếu cấu trúc chứa `T* ptr`, bước `groupElement("ptr")` chọn một **địa chỉ** (AddressLayout), không phải struct `T` nằm inline ở offset đó. Muốn đi sâu vào vùng được trỏ, cần mô tả target layout và dùng `dereferenceElement()` trong những API hỗ trợ; đó là hoạt động **đọc địa chỉ và vùng nhớ khác**, với thêm ràng buộc lifetime và an toàn. Đừng cộng offset của struct inline rồi mặc nhiên cho rằng tương đương pointer dereference.

## 11. Biến số lượng phần tử: khi `sequenceLayout(n,...)` không đủ

`sequenceLayout(n, element)` phù hợp khi số lượng phần tử **được biết trước**. Nhưng dữ liệu native thực tế đôi khi là:

```c
typedef struct {
    int32_t count;
    Point points[];
} Packet;
```

`points[]` ở đây là **flexible array member** theo C99; độ dài không cố định ở thời điểm tạo schema. Không thể giả định `sequenceLayout(100, point)` nếu `count` có thể khác 100.

JDK 22 cung cấp `MemoryLayout.arrayElementVarHandle(...)` để truy cập **mảng liền kề của một layout phần tử**, với một chỉ số lặp không bị cố định bởi `SequenceLayout` bên ngoài.

Ví dụ nguyên tắc (giả định đã có `StructLayout point` đúng ABI):

```java
VarHandle xOfPoint = point.arrayElementVarHandle(
        groupElement("x")
);

long pointsOffset = packetLayout.byteOffset(
        groupElement("points")
);

// Trong vùng packet có đủ bộ nhớ backing cho n Point.
for (long i = 0; i < n; i++) {
    int x = (int) xOfPoint.get(packetSegment, pointsOffset, i);
}
```

Đây **không phải chương trình độc lập**: `packetLayout`, `packetSegment` và `n` phải được chuẩn bị đúng như một struct header cộng vùng dữ liệu; `pointsOffset` phải được kiểm tra theo ABI và có backing đủ dài.

VarHandle trên `point` có signature:

```text
(MemorySegment segment, long baseOffset, long arrayIndex) -> int
```

Khác với `sequenceElement()` trên `sequenceLayout(3, point)`, chỉ số trong `arrayElementVarHandle` dùng để stride theo **kích thước của toàn `point` layout**, không bị ràng buộc bằng một số lượng cố định ngay trong `SequenceLayout`.

**Cảnh báo an toàn:** nếu `count` đến từ native input/file/network, xác thực `count >= 0` và `pointsOffset + count * point.byteSize()` không tràn và không vượt `packetSegment.byteSize()`. Nếu chưa xác định backing memory đủ lớn hoặc vùng pointer không hợp lệ, không dereference. Đừng bỏ qua thread ownership/scope chỉ vì handle cho phép tính index.

### 11.1. Khi nào dùng PathElement và khi nào dùng arrayElementVarHandle?

| Trường hợp | API hợp lý | Ghi chú |
| --- | --- | --- |
| `Record[2]` cố định | `sequenceLayout(2, Record)` + `sequenceElement()` | Layout mô tả trọn mảng |
| `Record.vertices[3]` cố định | `groupElement("vertices"), sequenceElement()` | Đi vào field rồi chọn phần tử |
| Mảng Point với số lượng xác định tại runtime | `point.arrayElementVarHandle(...)` | Dùng index stride theo `point.byteSize()` |
| Header có C flexible array member | Layout header + offset + `arrayElementVarHandle` | Tính buffer size từ count được xác thực |
| Field C kiểu con trỏ `Point*` | `AddressLayout`/target + dereference có kiểm soát | Khác với inline array |

## 12. Đọc dữ liệu từ native library thật: kiểm chứng schema và lifetime

Bài tập Java tạo bộ nhớ do Java sở hữu; khi đọc `struct` native do C/C++ cung cấp, bạn phải xem thêm:

### 12.1. Kích thước và offset từ ABI thật

Không chỉ biết typedef C là đủ. Các nhân tố ảnh hưởng:

- Compiler/ABI và kiến trúc (x86_64, AArch64, Windows ABI...).
- `sizeof` và `alignof` của từng type, quy tắc padding.
- `#pragma pack`, packed attribute và yêu cầu alignment khác.
- Byte order (`endianness`) và quy tắc biểu diễn số.
- `union`: nhiều member **trùng offset**, khác với `struct` nối tiếp.
- Con trỏ, bit fields và flexible array members cần cách xử lý riêng.

Nếu layout Java mô tả sai stride của Record, `records[0]` có thể còn đọc được nhưng `records[1]` bắt đầu sai — loại lỗi đặc biệt khó phát hiện.

Trong triển khai liên thông thật, đối chiếu `sizeof(Record)` và `offsetof(Record, vertices)`, `offsetof(Point, y)`; có thể dùng công cụ như `jextract` trên header phù hợp target. Với ví dụ ở mục 7, toàn bộ thông số do **chính layout Java** quyết định nên output có thể dự đoán chính xác.

### 12.2. Segment phải trỏ tới vùng nhớ hợp lệ

`MemorySegment` chỉ cho phép truy cập trong **giới hạn không gian**, **scope còn sống** và **quyền truy cập của thread**. Một offset đúng theo layout không làm một địa chỉ native tùy ý thành bộ nhớ an toàn. Không dùng `MemorySegment.ofAddress` với địa chỉ không đáng tin, không tự mở rộng segment vô hạn và không đọc sau khi thư viện C giải phóng bộ nhớ.

Ví dụ `Arena.ofConfined()`:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(recordsLayout);
    // Truy cập có cấu trúc trong scope này.
}
// Sau close, không được sử dụng lại segment native.
```

Đây là **trích đoạn minh họa**, với `recordsLayout` là một layout hợp lệ. Nếu muốn đa thread, có thể dùng `Arena.ofShared()` nhưng phải thiết kế đồng bộ; shared scope không tự bảo đảm tránh data races.

### 12.3. Đọc dữ liệu có layout nhưng không có metadata tên trong bộ nhớ

Tên field `x`, `y`, `origin` là metadata Java cho layout path. Bộ nhớ C không chứa các chuỗi tên này. Do đó `groupElement("y")` **không tìm chữ "y" trong bytes**; nó đọc offset đã được định nghĩa ở layout. Nếu schema C thay đổi, code Java cần layout mới đúng kích thước/thứ tự.

## 13. Những lỗi phổ biến

| Sai lầm | Điều gì xảy ra? | Cách sửa |
| --- | --- | --- |
| Dùng `groupElement("y")` trực tiếp trên `SequenceLayout` | Path không đúng loại layout | Chọn phần tử bằng `sequenceElement(...)` trước |
| Dùng `sequenceElement(...)` trên `StructLayout` | Path không hợp lệ | Chọn field sequence bằng `groupElement("vertices")` |
| Thiếu `withName("origin")` | Lookup theo tên không tìm được field | Đặt tên cho member hoặc dùng chỉ số |
| Gọi `varHandle` tới cả `StructLayout` | Selected layout không phải `ValueLayout` | Dùng `select`, `asSlice` hoặc `sliceHandle` |
| Gọi `byteOffset` có `sequenceElement()` mở | Không có offset cố định | Dùng `sequenceElement(index)` hoặc `byteOffsetHandle` |
| Nhầm `0L` base offset với index record | Đọc sai phần tử/`WrongMethodTypeException` | Đọc đúng tọa độ theo thứ tự `segment, base, indices` |
| Dùng `1` (int) nơi VarHandle yêu cầu `long` | Signature không khớp tại điểm gọi | Dùng `1L` hoặc cast `(long)i` |
| Hoán đổi hai chỉ số sequence | Lấy sai vertex/record | Theo thứ tự PathElement từ ngoài vào trong |
| Tự nhân index bằng 4 khi handle đã biết stride | Offset bị tính hai lần | Truyền **index**, để handle tính offset |
| Bỏ padding của struct C | Offset/stride sai, đặc biệt phần tử mảng thứ hai | So sánh `sizeof/offsetof` theo ABI |
| Chọn `JAVA_INT` cho field C có kích thước khác 4 byte | Đọc sai carrier/bytes | Chọn `ValueLayout` đúng với C type |
| Dùng layout phù hợp field nhưng segment bị đóng arena | `IllegalStateException` | Giữ arena sống qua toàn bộ access |
| Truy cập confined segment từ thread khác | `WrongThreadException` | Đúng owner hoặc dùng shared arena phù hợp |
| Index vượt vùng segment | `IndexOutOfBoundsException` hoặc truy cập logic sai | Kiểm tra cả count và byteSize |
| Dùng `get` trên handle nhưng cast sai kiểu | `ClassCastException`/`WrongMethodTypeException` | Xem carrier của selected `ValueLayout` |
| Chọn field C là pointer nhưng xử lý như nested inline struct | Dữ liệu không cùng vị trí | Dùng address target/dereference đúng |
| Coi `sliceHandle` là sao chép dữ liệu | Alias vẫn còn; thay đổi vùng gốc tác động slice | Nếu cần snapshot, copy sang vùng khác |

### 13.1. Path không hợp lệ tại thời điểm tạo handle

Ví dụ sai:

```java
// records là SequenceLayout, chưa vào Record/Point.
VarHandle bad = records.varHandle(groupElement("y"));
```

Cách sửa là bắt đầu bằng `sequenceElement()`, rồi chọn các `groupElement` tương ứng cho từng struct con. Phần lớn lỗi sai **hình dạng path** xảy ra ngay lúc tạo layout/handle, còn lỗi về index, scope, read-only hoặc alignment xảy ra lúc truy cập.

### 13.2. Open path không phải giấy phép index tùy ý

Đối với dãy có số phần tử hữu hạn, vòng lặp vẫn phải giữ chỉ số trong phạm vi logic. Ngoài việc API kiểm tra giới hạn byte của segment, bạn nên kiểm tra **sequence element count** để tránh phép tính offset lạc sang vùng khác mà vẫn nằm trong một segment lớn hơn, nhất là khi có nhiều layout lồng nhau và sử dụng base offset. Đừng trông chờ mọi phép `VarHandle.get` đều hiểu semantic “vertexIndex phải nhỏ hơn 3” nếu bộ nhớ thực còn chứa những byte khác.

### 13.3. Bỏ qua byte order

`ValueLayout.JAVA_INT` mô tả một `int` 4 byte với byte order theo layout. Khi đọc dữ liệu từ file/network, hãy chọn `withOrder(ByteOrder.BIG_ENDIAN)` hoặc `LITTLE_ENDIAN` phù hợp nếu protocol yêu cầu. Đường dẫn layout chỉ tính **vị trí**, không tự sửa sai **cách diễn giải byte**.

## 14. Hiệu năng và tính dễ bảo trì

**Ưu tiên tạo layout và handle một lần.** Với một schema ổn định, cache `StructLayout`, `SequenceLayout` và `VarHandle` dưới dạng `static final`. Các đối tượng layout là immutable và dùng được ở nhiều chỗ; còn `MemorySegment` vẫn chịu giới hạn sống, ownership, và thread access của vùng nhớ tương ứng.

**Dùng đường dẫn thay vì offset tay** khi schema có nhiều tầng. Một thay đổi cấu trúc có thể làm offset của nhiều field thay đổi; nếu tiếp tục giữ các số hard-code như 12, 36, 68 trong mã ứng dụng, sai lệch dễ lọt qua review. Khi truy cập bằng path, thay đổi layout sẽ cập nhật phép tính offset dựa vào schema.

**Vẫn cần kiểm chứng ABI.** Path giúp tránh sai cộng trừ sau khi layout đã đúng; nó **không tự phát hiện** header C thật có khác schema Java.

**Không làm phép copy ngoài ý muốn.** `asSlice`/`sliceHandle` tạo view lên cùng vùng nhớ; đọc bằng `VarHandle` không phải tự động sao chép struct sang Java object. Nếu cần chuyển dữ liệu sang class Java độc lập, tự đọc các trường theo path rồi tạo record/POJO hoặc copy sang mảng Java theo quy tắc ứng dụng.

## 15. Tình huống áp dụng

### A. Mảng vị trí của các cảm biến

C thư viện trả `Point readings[100]`. Tạo `sequenceLayout(100, POINT)` rồi `varHandle(sequenceElement(), groupElement("x"))`, đọc với `handle.get(memory, 0L, (long)i)`. Không cần dựng 100 handle khác nhau.

### B. Một struct chứa metadata và chuỗi điểm

Thư viện trả `Record` với `id`, `origin` và `vertices`. Tạo `StructLayout` lồng `Point` và `SequenceLayout`, sau đó dùng `groupElement("vertices"), sequenceElement(), groupElement("y")`. Bổ sung `sequenceElement()` ở đầu nếu có **mảng `Record[]`** bên ngoài.

### C. Nhiều bản ghi từ network/binary file

Nếu data format **cố định** và không có native pointer, có thể xây `MemoryLayout` khớp endian/schema của file, rồi dùng `MemorySegment.ofArray(byte[])` hoặc native segment có đủ scope để đọc. Kiểm tra checksum/bounds trước, tránh đọc array count chưa kiểm chứng.

### D. Header C thay đổi giữa phiên bản SDK

Không giữ các offset hard-coded; quản lý schema theo phiên bản thư viện. Xác minh `sizeof/offsetof` đúng phiên bản. Nếu compiler thêm padding hoặc đổi packing, cập nhật layout, không chỉ thay index trong Java.

### E. Kết quả cần trả về Java object

FFM layout path đọc nguyên thủy hiệu quả; nhưng một DTO Java như `record Point(int x,int y)` vẫn có vòng đời, garbage collection và bất biến riêng. Đọc bằng `VarHandle` rồi **xây Java record** nếu bên gọi muốn ownership độc lập, thay vì lưu `MemorySegment` có thể hết hạn theo arena.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao `records[1].vertices[2].y` cần hai bước `sequenceElement`?** Vì có hai tầng mảng: `Record[]` bên ngoài và `Point[]` bên trong một Record. Mỗi bước mở tạo một tọa độ chỉ số `long`.

**2. Khác nhau giữa `sequenceElement(2)` và `sequenceElement()`?** Một cái chọn phần tử thứ ba cố định khi tạo path; cái còn lại để caller truyền index tại lúc `get/set`.

**3. Dùng `byteOffset` được với open path không?** Không. Dùng fixed index hoặc `byteOffsetHandle` để truyền index động.

**4. Có thể gọi `records.varHandle(sequenceElement(), groupElement("origin"))` để nhận cả struct Point không?** Không. `origin` là StructLayout, không phải ValueLayout; dùng `select`/`sliceHandle`/`asSlice`.

**5. Trong ví dụ `Record`, `records[1].vertices[2].y` nằm ở byte offset nào?** **68** từ đầu `Record[2]`, theo `36 + 12 + 2×8 + 4`.

**6. Nếu `groupElement("x")` không tìm thấy field thì sao?** Đường dẫn không hợp lệ, API báo lỗi lúc tạo path/handle; phải gán tên layout bằng `withName` hoặc chọn đúng member.

**7. Vì sao JDK 22 cần `paddingLayout` khi mô tả C struct?** `structLayout` không tự chèn padding. Muốn offset/stride trùng với C ABI phải mô tả đúng các byte đệm.

**8. `sliceHandle` có tạo một bản sao Point không?** Không. Nó cho view trên vùng con của segment gốc, nên tuân theo scope và backing tương ứng.

**9. Khi nào cân nhắc `arrayElementVarHandle`?** Khi số phần tử của mảng native chỉ xác định lúc runtime, không được mã hóa thành một `SequenceLayout` có length cố định.

**10. `VarHandle.get(segment,0L,1L,2L)` có nghĩa gì trong ví dụ?** `segment` là vùng nhớ, `0L` là base offset, `1L` chọn Record thứ hai, `2L` chọn vertex thứ ba; kết quả là giá trị trường đã chọn, `43` trong dữ liệu mẫu.

## 17. Checklist trước khi đọc dữ liệu struct lồng nhau

1. Xác định đang dùng **JDK 22+ FFM API**; không lẫn code preview/incubator trước đó.
2. Mô tả đúng `ValueLayout`, `StructLayout`, `SequenceLayout`, tên `withName` và padding.
3. Kiểm chứng `sizeof`, `alignof`, `offsetof` trên C ABI đích nếu dữ liệu là native thực.
4. Sắp xếp `groupElement`/`sequenceElement` theo đường đi **ngoài → trong**; chọn đúng loại bước cho loại layout.
5. Nếu cần **offset cố định**, dùng `byteOffset` với các sequence index cố định.
6. Nếu cần **đọc/ghi field lá**, dùng `varHandle`; nhớ đúng số tọa độ `long` và Java carrier.
7. Nếu cần **offset động**, dùng `byteOffsetHandle`; nếu cần **vùng struct con**, dùng `sliceHandle` hoặc `asSlice`.
8. Nếu có **mảng không biết trước số lượng**, dùng `arrayElementVarHandle` và xác minh kích thước vùng dữ liệu.
9. Kiểm tra chỉ số logic, `byteSize`, alignment, endianness, scope còn sống và thread ownership.
10. Không nhầm view với copy; không dùng segment sau khi arena đóng hoặc pointer sau khi native owner giải phóng.
11. Cache layout/handles khi schema ổn định; viết integration tests kiểm tra offset và giá trị mẫu.
12. Khi dữ liệu cần tồn tại lâu dưới dạng object Java, tự chuyển đổi sang cấu trúc Java có ownership độc lập.

## Tài liệu tham khảo chính thức

- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): layout paths, `select`, `byteOffset`, `byteOffsetHandle`, `varHandle`, `arrayElementVarHandle` và `sliceHandle`.
- [Java SE 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html): `groupElement`, `sequenceElement` và `dereferenceElement`.
- [Oracle Java SE 22 — Memory Layouts and Structured Access](https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html): hướng dẫn chính thức về struct, sequence và VarHandle tọa độ động.
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): phạm vi truy cập và quy tắc kiểm tra bộ nhớ.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native và vòng đời scope.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM trở thành API ổn định trong JDK 22.