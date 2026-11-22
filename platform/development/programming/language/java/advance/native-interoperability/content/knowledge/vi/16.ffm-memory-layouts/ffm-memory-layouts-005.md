# Đặt tên trường và tìm offset bằng MemoryLayout.PathElement

## 1. Vấn đề thực tế: field trong một cấu trúc native nằm tại byte nào?

Khi trao đổi dữ liệu với thư viện C/C++ thông qua **Foreign Function & Memory API (FFM)**, Java cần biết chính xác **vị trí tính theo byte** của từng trường trong một cấu trúc native. Những vị trí ấy không luôn là tổng số byte nhìn thấy trong khai báo: compiler C có thể chèn **padding** để đáp ứng **alignment**; field còn có thể nằm trong một struct lồng nhau hoặc mảng struct.

Với FFM đã hoàn thiện trong **JDK 22+** (`java.lang.foreign`), `MemoryLayout` là sơ đồ dữ liệu, còn **`MemoryLayout.PathElement`** là thành phần của một *đường dẫn cấu trúc* dùng để:
- chọn một trường theo **tên** hoặc theo **chỉ số thành viên**;
- đi qua struct, union và sequence/mảng lồng nhau;
- tính **byte offset** cố định bằng `byteOffset(...)`;
- tạo **`MethodHandle` tính offset động** bằng `byteOffsetHandle(...)`;
- lấy layout con bằng `select(...)`, hoặc tạo **`VarHandle`** đọc/ghi trường đã chọn.

Bài này tập trung vào **đặt tên trường và tìm offset bằng `MemoryLayout.PathElement`** trong ngữ cảnh **Bố trí dữ liệu**. `Arena` và `MemorySegment` chỉ được dùng để kiểm chứng offset bằng những truy cập Java thật. Không cần viết JNI glue code hay gọi native C function để chạy bài thực hành chính.

**Yêu cầu phiên bản:** Mẫu hoàn chỉnh biên dịch với `javac --release 22` và chạy được trên JDK 22+; đã kiểm thử bằng JDK 24. Không dùng nguyên source này trên JDK 17: FFM ở JDK 17 là API incubator khác package và chữ ký. Các đoạn code ghi rõ *fragment* là ví dụ minh họa trong method/block hợp lệ, không phải file độc lập.

Sau khi hoàn thành, bạn có thể giải thích:
1. `withName("field")` gắn tên cho **layout**, không tạo Java field hay cấp phát memory.
2. `groupElement("name")` chọn field của một group; `sequenceElement(index)` chọn phần tử array.
3. Vì sao offset của field có thể khác kích thước các field đứng trước.
4. Cách tìm offset của một field lồng trong struct và array bằng **một đường dẫn**.
5. Cách phân biệt `byteOffset`, `select`, `byteOffsetHandle` và `varHandle`, đặc biệt **fixed** so với **open sequence path**.
6. Các lỗi điển hình: tên thiếu/sai, số index sai, nhầm byte offset với array index, bỏ base offset khi dùng handles, sai padding/ABI, dùng segment sau khi arena đóng.

## 2. Nền tảng: MemoryLayout mô tả byte, không chứa giá trị

`MemoryLayout` biểu diễn cấu trúc dữ liệu bất biến. Một số factory thường dùng:

~~~java
// Fragments Java JDK 22+, đặt trong method/block hợp lệ.
MemoryLayout oneInt = ValueLayout.JAVA_INT; // 4 byte.
MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
MemoryLayout threePoints = MemoryLayout.sequenceLayout(3, point);
~~~

| Loại layout | Ý nghĩa | Đường dẫn tiếp theo có thể dùng |
|---|---|---|
| `ValueLayout` | Một giá trị kiểu primitive/address: int, byte, long, pointer... | Thường là điểm cuối khi dùng `varHandle` |
| `StructLayout` | Các thành viên nối tiếp nhau với byte offsets | `groupElement("name")` hoặc `groupElement(index)` |
| `UnionLayout` | Các thành viên chồng lên cùng vị trí bắt đầu | `groupElement(...)`; offset thành viên thường bắt đầu ở 0 |
| `SequenceLayout` | N phần tử liên tục, mỗi phần tử có cùng layout | `sequenceElement(index)` hoặc `sequenceElement()` |
| `PaddingLayout` | Những byte bỏ qua để đáp ứng bố trí | Không phải field nghiệp vụ cần đọc/ghi |

Một layout như `point` trên chứa **sơ đồ hai trường** nhưng không có một tọa độ x/y cụ thể. Muốn có bytes, Java phải được cấp một `MemorySegment` có dung lượng và alignment tương thích:

~~~java
// Fragment, cần import java.lang.foreign.*.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment pointBytes = arena.allocate(point);
    // Khi có segment này, Java mới có vùng nhớ thật để ghi x/y.
}
~~~

Hãy giữ ba câu hỏi tách biệt:
- **Layout**: “dữ liệu *phải được hiểu* như thế nào?”
- **PathElement**: “từ root layout, *đi theo nhánh nào* để chọn field?”
- **Segment**: “đọc/ghi dữ liệu *ở vùng nhớ thật nào*, còn sống không?”

`MemoryLayout.byteSize()`, `byteAlignment()` và `byteOffset(...)` giúp suy luận về sơ đồ **không cần cấp phát memory**. Việc tính offset không tự tạo native pointer.

## 3. Đặt tên trường đúng cách: withName và name

Gắn tên ngay khi tạo layout thành viên:

~~~java
MemoryLayout person = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_LONG.withName("score"));
~~~

`withName("id")` tạo ra **một layout mới có name**. Nó **không đổi** biến Java đã giữ layout cũ và cũng **không thêm Java class field**. Kiểu dữ liệu gốc vẫn là `ValueLayout.JAVA_INT`; name là metadata để `PathElement.groupElement("id")` tìm đúng thành viên theo tên.

~~~java
// Fragment độc lập về ý tưởng.
MemoryLayout unnamed = ValueLayout.JAVA_INT;
MemoryLayout named = unnamed.withName("count");

System.out.println(unnamed.name().isPresent()); // false
System.out.println(named.name().orElseThrow());  // count
~~~

`MemoryLayout.name()` trả `Optional<String>`, vì **không phải layout nào cũng có tên**. Những padding layouts và layout gốc không đặt tên có thể không có metadata name.

### Đặt tên cho group và sequence lồng nhau

~~~java
MemoryLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"))
        .withName("header");

MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));

MemoryLayout record = MemoryLayout.structLayout(
        header,
        MemoryLayout.sequenceLayout(3, point).withName("points"),
        ValueLayout.JAVA_INT.withName("checksum"));
~~~

Trong root `record`:
- `header` là group **có tên "header"**, chứa field có tên "kind"/"count".
- `points` là **sequence có tên "points"**, mỗi phần tử là group kiểu `point` có field "x"/"y".
- `checksum` là một field ở root.
- Padding 3 byte ở `header` là một member layout để đẩy field `count` tới offset 4; nó **không** phải data field có tên.

**Thực hành tốt:** chọn tên **duy nhất trong từng group** và bám theo C header/sơ đồ ABI. Hai group khác nhau có thể cùng tên field (ví dụ `header.count` và `footer.count`) vì path phân biệt qua tên group cha. Nếu đặt trùng tên ở **cùng một group**, lookup theo tên khó đọc/khó duy trì; đừng dựa vào một lựa chọn ngầm để phân biệt.

### Tên layout ≠ C symbol ≠ Java reflection

`withName("count")` là tên **thành viên trong bố trí memory**, không phải:
- Java reflection `Class.getDeclaredField("count")`;
- tên exported symbol dùng bởi `SymbolLookup`;
- tên biến C/JNI có thể tự được tra từ header;
- cam kết rằng compiler C thật đặt field tại offset Java mong đợi.

Đặt tên là bước đầu để **tính toán cấu trúc rõ ràng**. Việc khớp native ABI vẫn cần kiểm chứng `sizeof`/`offsetof`, alignment, byte order và compiler packing.

## 4. MemoryLayout.PathElement: các bước đi trong cây layout

`MemoryLayout.PathElement` là interface con của `MemoryLayout`. Một path gồm một hoặc nhiều **path elements**, áp dụng tuần tự từ root đến field đích.

| Factory của `PathElement` | Dùng khi current layout là | Ý nghĩa |
|---|---|---|
| `groupElement("name")` | `StructLayout` hoặc `UnionLayout` | Chọn member trong group theo tên |
| `groupElement(long index)` | `StructLayout` hoặc `UnionLayout` | Chọn member theo vị trí, **zero-based** |
| `sequenceElement(long index)` | `SequenceLayout` | Chọn phần tử mảng tại index **cố định** |
| `sequenceElement()` | `SequenceLayout` | Chọn phần tử chưa xác định: **open path**, index truyền khi dùng handle |
| `sequenceElement(long start, long step)` | `SequenceLayout` | Một dạng **open path** cho dãy chỉ số theo công thức; chỉ dùng khi hiểu bước nhảy |
| `dereferenceElement()` | `AddressLayout` có target layout | Đi theo pointer qua target layout; cần bảo đảm pointer/memory hợp lệ |

Bài này dùng bốn factory đầu; `dereferenceElement()` là chủ đề nâng cao vì đụng tới pointer target và native memory lifetime. **Không** nhầm `groupElement(index)` với `sequenceElement(index)`:
- Group index là **vị trí thành viên trong struct/union**, có tính cả padding layout.
- Sequence index là **vị trí phần tử trong mảng**, mỗi phần tử có stride bằng kích thước element layout.

### Path luôn đi từ ngoài vào trong

Giả sử muốn trường `y` của phần tử `points[2]` trong `record`. Trình tự:

~~~text
record (struct)
  |
  +-- groupElement("points") --> points (sequence of 3 point structs)
                                  |
                                  +-- sequenceElement(2) --> point #2 (struct)
                                                               |
                                                               +-- groupElement("y") --> int32
~~~

Cú pháp Java:

~~~java
// Fragment: record là MemoryLayout ở mục 3.
long offset = record.byteOffset(
        MemoryLayout.PathElement.groupElement("points"),
        MemoryLayout.PathElement.sequenceElement(2),
        MemoryLayout.PathElement.groupElement("y"));
~~~

Đổi chỗ hai bước là sai: sau khi chọn `groupElement("points")`, current layout là **sequence**, nên chưa thể gọi `groupElement("y")` trực tiếp. Cần chọn **một phần tử sequence** rồi mới vào member "y" của struct phần tử.

### Import cú pháp gọn

Nếu có import sau trong đầu file Java:

~~~java
import static java.lang.foreign.MemoryLayout.PathElement.*;
~~~

thì có thể viết `groupElement("points")`, `sequenceElement(2)`, `groupElement("y")` mà không lặp tên class. Đây chỉ là static import các **factory methods**; không thay đổi semantics.

## 5. Đọc byte map trước khi code: ví dụ Record có header và points

Cùng root layout ở mục 3:

~~~text
Record (36 bytes, minh họa int32 align=4)
Offset (byte)       Dữ liệu              Kích thước
0                   header.kind          1
1..3                padding             3
4..7                header.count        4
8..11               points[0].x         4
12..15              points[0].y         4
16..19              points[1].x         4
20..23              points[1].y         4
24..27              points[2].x         4
28..31              points[2].y         4
32..35              checksum            4
~~~ 

Từ đó:

| Path từ root | Offset tính theo byte | Cách hiểu |
|---|---:|---|
| `groupElement("header")` | 0 | Header bắt đầu ngay đầu record |
| `groupElement("header"), groupElement("kind")` | 0 | Byte đầu tiên |
| `groupElement("header"), groupElement("count")` | 4 | Bỏ qua kind (1) + padding (3) |
| `groupElement("points")` | 8 | Mảng bắt đầu sau header 8 byte |
| `groupElement("points"), sequenceElement(0), groupElement("x")` | 8 | Phần tử 0 bắt đầu tại 8 |
| `groupElement("points"), sequenceElement(0), groupElement("y")` | 12 | y của phần tử 0 |
| `groupElement("points"), sequenceElement(1), groupElement("y")` | 20 | 8 + 1×8 + 4 |
| `groupElement("points"), sequenceElement(2), groupElement("y")` | 28 | 8 + 2×8 + 4 |
| `groupElement("checksum")` | 32 | Sau ba Point, mỗi Point 8 byte |

Công thức trong layout có fixed-size array:

\[
\operatorname{offset}(\mathrm{points}[i].y)
  = \operatorname{offset}(\mathrm{points}) + i \cdot \operatorname{sizeof}(\mathrm{Point}) + \operatorname{offset}(\mathrm{Point.y})
  = 8 + 8i + 4.
\]

Với `i=2` kết quả là **28**. Tuy nhiên, **không hardcode 8 và 4** khi có `PathElement`: thiết kế sẽ dễ vỡ nếu bạn thêm field vào header, thay Point layout, cập nhật padding hoặc đổi ABI.

### Vì sao không cộng kích thước các kiểu một cách ngây thơ?

Nếu bỏ `MemoryLayout.paddingLayout(3)` trong header, `count` không nằm ở offset 4. Trên JDK 22+, `structLayout` **không tự chèn padding** cho field căn lề; cấu trúc với field alignment không phù hợp có thể bị từ chối khi tạo layout. Tự mô tả một struct native đòi hỏi hiểu **size, alignment, packing, tail padding** của ABI thực, không chỉ nhìn C declaration rồi nối field.

Một struct C có trường `uint8_t kind` và `int32_t count` thường được compiler C đặt count tại offset 4, nhưng **không được suy rộng sang mọi compiler/flag/platform**. Khi kết nối native thật, kiểm tra bằng C `offsetof`, `sizeof` và `_Alignof` thay vì coi bảng này là chân lý xuyên ABI.

## 6. byteOffset(...): tìm một vị trí cố định, không cấp phát

`record.byteOffset(path...)` trả **`long`**, là byte offset **tương đối từ byte 0 của chính root layout**. Không phải một raw address/pointer và cũng không tự tham chiếu vùng nhớ được cấp ở đâu.

~~~java
// Fragments: record là MemoryLayout đã định nghĩa.
long countOffset = record.byteOffset(
        groupElement("header"), groupElement("count"));  // 4

long firstYOffset = record.byteOffset(
        groupElement("points"), sequenceElement(0),
        groupElement("y"));                              // 12

long thirdYOffset = record.byteOffset(
        groupElement("points"), sequenceElement(2),
        groupElement("y"));                              // 28

long checksumOffset = record.byteOffset(
        groupElement("checksum"));                      // 32
~~~

**Điều kiện quan trọng:** `byteOffset` cần một path xác định **chính xác một vị trí**. Vì thế:
- `sequenceElement(2)` là **fixed/bound path element**, dùng được để hỏi offset của phần tử 2.
- `sequenceElement()` là **open path element**, chưa biết index nào; **không được** truyền trực tiếp vào `byteOffset(...)`. API ném `IllegalArgumentException`.
- `dereferenceElement()` có target ở nơi mà pointer runtime trỏ tới; `byteOffset(...)` không dùng cho path chứa dereference element.

Không nhầm:

~~~java
long bad = record.byteOffset(
        groupElement("points"),
        sequenceElement(),
        groupElement("y")); // Sai: open sequence path, ném IllegalArgumentException.
~~~

Hãy dùng `byteOffsetHandle(...)` nếu muốn tính offset cho **nhiều chỉ số khác nhau lúc chạy**, không gọi `byteOffset` với một index “chưa gắn”.

### Offset của sublayout khác offset của field từ root

~~~java
MemoryLayout header = record.select(groupElement("header"));
long countInsideHeader = header.byteOffset(groupElement("count")); // 4

long countInsideRecord = record.byteOffset(
        groupElement("header"), groupElement("count"));           // 4
~~~

Trong ví dụ header ở byte 0 nên hai số cùng bằng 4. Nếu header bắt đầu ở byte 16 trong một root lớn hơn, offset tính từ **header** vẫn 4 còn offset tính từ **root** sẽ 20. Vì vậy **luôn ghi rõ root layout** và không cộng nhầm offset đã được tính từ root một lần nữa.

## 7. select(...): chọn loại layout của trường, không hỏi vị trí phần tử

`select(PathElement...)` trả **`MemoryLayout` của field được chọn**, có thể xem `name()`, `byteSize()`, `byteAlignment()` hoặc dùng làm type information. Nó **không** trả byte offset.

Ví dụ:

~~~java
MemoryLayout selected = record.select(
        groupElement("points"),
        sequenceElement(),
        groupElement("y"));

System.out.println(selected.name().orElse("<unnamed>")); // y
System.out.println(selected.byteSize());                 // 4
~~~

**Chi tiết ít người để ý nhưng phải nhớ:** trong JDK 22+:
- `select(...)` cho phép một **open sequence element** (`sequenceElement()`) để lấy *element layout* nói chung, không quan tâm index.
- `select(...)` **không cho phép một fixed-index sequence path** như `sequenceElement(1)`. Dùng sẽ ném `IllegalArgumentException`, vì việc *chọn kiểu layout* không cần ràng buộc một element index.
- `select(...)` cũng từ chối dereference path.

Điều này trông ngược với `byteOffset(...)`, nhưng rất hợp lý khi tách nhu cầu:

| Muốn biết | API | Ví dụ chọn sequence |
|---|---|---|
| **Field nằm tại byte nào của phần tử số 2?** | `byteOffset(...)` | `sequenceElement(2)` |
| **Mọi phần tử có field y thuộc layout nào?** | `select(...)` | `sequenceElement()` |
| **Tính offset theo index truyền runtime?** | `byteOffsetHandle(...)` | `sequenceElement()` |
| **Đọc/ghi y của phần tử runtime i?** | `varHandle(...)` | `sequenceElement()` |

**Đừng viết `select(...sequenceElement(2)...)` rồi báo “PathElement bị lỗi”;** hãy chọn `sequenceElement()` khi hỏi layout, hoặc đổi sang `byteOffset` khi hỏi vị trí phần tử cố định.

## 8. byteOffsetHandle(...): offset động có base và index

Khi một loop cần offset của `points[i].y` cho nhiều `i`, `byteOffsetHandle(...)` tạo một `java.lang.invoke.MethodHandle` nhận các tham số `long` tại runtime.

~~~java
import java.lang.invoke.MethodHandle;
// record là root MemoryLayout; có static import PathElement.*.
MethodHandle yOffset = record.byteOffsetHandle(
        groupElement("points"),
        sequenceElement(),
        groupElement("y"));
~~~

**Chữ ký quan trọng:** handle trả ra luôn có:
1. **Một tham số `long` đầu tiên là base offset**.
2. **Mỗi open path element thêm một tham số `long`** theo thứ tự xuất hiện trong path.
3. **Return type `long`** là offset tính bằng byte.

Trong ví dụ có đúng **một open sequence element**, method handle có Java method type tương ứng **`(long base, long index)long`**:

~~~java
long a = (long) yOffset.invokeExact(0L, 0L);  // 12
long b = (long) yOffset.invokeExact(0L, 1L);  // 20
long c = (long) yOffset.invokeExact(0L, 2L);  // 28

long shifted = (long) yOffset.invokeExact(100L, 2L); // 128
~~~

Tham số `base` giúp tái sử dụng layout trong một buffer chứa nhiều records, hoặc tính từ một vị trí bắt đầu khác. Nhưng base offset **không tự chứng minh vùng nhớ có đủ dữ liệu** — đây là toán học offset; khi đọc/ghi trên `MemorySegment` phải tuân thủ bounds/lifetime.

### Hai open sequences

Nếu layout có hai sequence lồng nhau, ví dụ matrix 2×3 của `JAVA_INT`:

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT));
MethodHandle cellOffset = matrix.byteOffsetHandle(
        sequenceElement(), sequenceElement());
long addressWithinMatrix =
        (long) cellOffset.invokeExact(0L, 1L, 2L); // (1*3 + 2)*4 = 20
~~~

Handle này có **ba `long` inputs**: base, outer index, inner index. Thứ tự index tương ứng với **thứ tự open elements trong path**, không phải theo tên biến tùy ý. Nếu dùng `invokeExact`, cả số đối số lẫn primitive types phải **khớp chính xác** method type; `int` thay `long` có thể dẫn tới `WrongMethodTypeException`.

### byteOffsetHandle khác byteOffset

Với fixed path, `byteOffset` tính ngay một số `long`; không cần handle. Với open path, `byteOffsetHandle` cho phép trì hoãn chỉ số tới lúc chạy. Tạo handle một lần rồi tái sử dụng trong vòng lặp; tránh dựng lại layout/path mỗi lần chỉ để đọc một field.

## 9. varHandle(...): dùng PathElement để đọc/ghi dữ liệu thật

`MemoryLayout.varHandle(path...)` chỉ tạo VarHandle khi path chọn đến một **ValueLayout** thích hợp. Nếu path kết thúc tại cả một struct hoặc sequence, không thể giả định Java có primitive carrier cho toàn khối ấy.

Để truy cập `count` và `points[i].y`:

~~~java
import java.lang.invoke.VarHandle;

VarHandle count = record.varHandle(
        groupElement("header"), groupElement("count"));

VarHandle y = record.varHandle(
        groupElement("points"), sequenceElement(),
        groupElement("y"));
~~~

- `count` có coordinates **`(MemorySegment, long base)`**, carrier `int`.
- `y` có coordinates **`(MemorySegment, long base, long index)`**, carrier `int`.
- `long base` là tọa độ bắt buộc trong API JDK 22; không tự lược vì bạn luôn dùng offset 0.
- Có thể dùng `VarHandle.toMethodHandle(...)` và các adapters khi cần composition, nhưng ở bài này dùng `get/set` đơn giản.

Ghi/đọc trong một arena:

~~~java
// Fragment: recordLayout là layout, arena còn sống, segment đúng dung lượng.
MemorySegment memory = arena.allocate(record);

count.set(memory, 0L, 3);          // Đặt header.count = 3.
y.set(memory, 0L, 0L, 11);         // points[0].y = 11.
y.set(memory, 0L, 1L, 22);         // points[1].y = 22.
y.set(memory, 0L, 2L, 33);         // points[2].y = 33.

int value = (int) y.get(memory, 0L, 2L); // 33
~~~

Tham số `0L` là base offset, `2L` là index của open sequence path. Nếu viết `y.get(memory, 2L)`, bạn **không** đang chọn phần tử 2: lời gọi thiếu tọa độ và có thể gây `WrongMethodTypeException`. Nếu dùng `byteOffset(...)` lấy cố định `points[2].y` thì có thể đọc bằng `memory.get(ValueLayout.JAVA_INT, offset)`, nhưng khi đã dùng VarHandle đường dẫn rõ ràng hơn cho code lặp.

### Từ layout tới offset rồi mới đọc bằng MemorySegment.get

Hai hướng truy cập tương đương về vị trí:

~~~java
long off = record.byteOffset(
        groupElement("points"), sequenceElement(2), groupElement("y"));
int fromOffset = memory.get(ValueLayout.JAVA_INT, off);

VarHandle pointY = record.varHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
int fromHandle = (int) pointY.get(memory, 0L, 2L);
~~~

Nếu layout/byte order/type giống nhau và memory hợp lệ, hai giá trị đều là `points[2].y`. `byteOffset` cho một số byte offset; `varHandle` kết hợp layout, path, carrier và offset arithmetic vào một view thao tác.

### Truy cập phải hợp lệ về nhiều chiều

VarHandle từ `MemoryLayout` vẫn phải tuân thủ:
- **spatial bounds** của `MemorySegment`;
- **temporal lifetime** của arena;
- **thread confinement** hoặc quy tắc sharing;
- **alignment** của layout/address đang truy cập;
- quyền đọc/ghi của segment.

Một layout path “cú pháp đúng” không khiến memory tự nhiên lớn hơn, và một Java VarHandle không ngăn C code khác dùng pointer sai.

## 10. Chương trình hoàn chỉnh (JDK 22+): offset cố định, offset động, tên và lỗi

Chương trình dưới đây là một file Java **biên dịch/chạy độc lập**, dùng duy nhất FFM memory APIs không restricted native downcall. Không cần C compiler, JNI headers, `System.loadLibrary` hoặc `--enable-native-access` cho các thao tác được dùng.

### 10.1. Tạo file LayoutPathLesson.java

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class LayoutPathLesson {
    private static final MemoryLayout POINT = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("x"),
            ValueLayout.JAVA_INT.withName("y"));

    private static final MemoryLayout HEADER = MemoryLayout.structLayout(
            ValueLayout.JAVA_BYTE.withName("kind"),
            MemoryLayout.paddingLayout(3),
            ValueLayout.JAVA_INT.withName("count")).withName("header");

    private static final MemoryLayout RECORD = MemoryLayout.structLayout(
            HEADER,
            MemoryLayout.sequenceLayout(3, POINT).withName("points"),
            ValueLayout.JAVA_INT.withName("checksum"));

    public static void main(String[] args) throws Throwable {
        long countOffset = RECORD.byteOffset(
                groupElement("header"), groupElement("count"));
        long firstYOffset = RECORD.byteOffset(
                groupElement("points"), sequenceElement(0), groupElement("y"));
        long thirdYOffset = RECORD.byteOffset(
                groupElement("points"), sequenceElement(2), groupElement("y"));
        long checksumOffset = RECORD.byteOffset(groupElement("checksum"));

        MethodHandle offset = RECORD.byteOffsetHandle(
                groupElement("points"), sequenceElement(), groupElement("y"));
        long computedThirdYOffset = (long) offset.invokeExact(0L, 2L);
        if (computedThirdYOffset != thirdYOffset) {
            throw new AssertionError("Offset mismatch");
        }

        VarHandle count = RECORD.varHandle(
                groupElement("header"), groupElement("count"));
        VarHandle y = RECORD.varHandle(
                groupElement("points"), sequenceElement(), groupElement("y"));

        System.out.println("recordBytes=" + RECORD.byteSize());
        System.out.println("countOffset=" + countOffset);
        System.out.println("firstYOffset=" + firstYOffset);
        System.out.println("thirdYOffset=" + thirdYOffset);
        System.out.println("checksumOffset=" + checksumOffset);

        MemorySegment expired;
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(RECORD);
            record.set(ValueLayout.JAVA_BYTE, 0L, (byte) 7);
            count.set(record, 0L, 3);
            y.set(record, 0L, 0L, 11);
            y.set(record, 0L, 1L, 22);
            y.set(record, 0L, 2L, 33);
            record.set(ValueLayout.JAVA_INT, checksumOffset, 66);

            int[] ys = {
                    (int) y.get(record, 0L, 0L),
                    (int) y.get(record, 0L, 1L),
                    (int) y.get(record, 0L, 2L)
            };
            System.out.println("kind=" + record.get(ValueLayout.JAVA_BYTE, 0L));
            System.out.println("count=" + count.get(record, 0L));
            System.out.println("pointsY=" + Arrays.toString(ys));
            System.out.println("checksum=" + record.get(
                    ValueLayout.JAVA_INT, checksumOffset));

            MemoryLayout selected = RECORD.select(
                    groupElement("points"),
                    sequenceElement(),
                    groupElement("y"));
            System.out.println("selected=" + selected.name().orElse("<unnamed>")
                    + ":" + selected.byteSize());

            try {
                RECORD.byteOffset(
                        groupElement("points"),
                        sequenceElement(),
                        groupElement("y"));
                throw new AssertionError("Expected open-path error");
            } catch (IllegalArgumentException expected) {
                System.out.println("openPathOffset=IllegalArgumentException");
            }

            try {
                RECORD.select(
                        groupElement("points"),
                        sequenceElement(1),
                        groupElement("y"));
                throw new AssertionError("Expected fixed-select error");
            } catch (IllegalArgumentException expected) {
                System.out.println("fixedIndexSelect=IllegalArgumentException");
            }

            try {
                RECORD.byteOffset(groupElement("missing"));
                throw new AssertionError("Expected missing-field error");
            } catch (IllegalArgumentException expected) {
                System.out.println("missingName=IllegalArgumentException");
            }

            expired = record;
        }

        try {
            count.get(expired, 0L);
            throw new AssertionError("Expected closed-arena failure");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

**Đây là code hoàn chỉnh**, không có package. Nên giữ nguyên class name `LayoutPathLesson` và file `LayoutPathLesson.java`; `POINT/HEADER/RECORD` là layout descriptions bất biến và có thể tái sử dụng.

### 10.2. Biên dịch và chạy

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

**Windows (PowerShell):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

**Windows CMD** (trong một thư mục chưa có `out`):

~~~bat
mkdir out
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

Nếu `out` đã có, không cần tạo lại. Trong ví dụ chỉ dùng native memory allocation qua `Arena` và layout access bình thường; **không cần** `--enable-preview` cho FFM đã finalized từ JDK 22 và **không cần** `--enable-native-access` vì không có restricted downcall/library loading. Những flags đó có ý nghĩa khác ở bài gọi native function.

### 10.3. Stdout chính xác đã kiểm chứng

~~~text
recordBytes=36
countOffset=4
firstYOffset=12
thirdYOffset=28
checksumOffset=32
kind=7
count=3
pointsY=[11, 22, 33]
checksum=66
selected=y:4
openPathOffset=IllegalArgumentException
fixedIndexSelect=IllegalArgumentException
missingName=IllegalArgumentException
afterClose=IllegalStateException
RESULT: PASS
~~~

Kết quả được kiểm thử bằng **JDK 24 trên Windows x64**, lệnh `javac --release 22` rồi `java -cp out LayoutPathLesson`. Các dòng số chỉ phụ thuộc layout đã chọn; không dựa vào raw native address, hash code hay thời điểm GC.

### 10.4. Đọc kết quả theo từng trách nhiệm

- `recordBytes=36`: một Header 8 byte + ba Point × 8 byte + checksum 4 byte.
- `countOffset=4`: field count đi sau kind 1 byte và padding 3 byte.
- `firstYOffset=12` và `thirdYOffset=28`: `points` bắt đầu ở byte 8, Point có stride 8, field y offset 4 trong Point.
- `computedThirdYOffset` được kiểm tra bằng `byteOffsetHandle`; nếu không bằng offset cố định, code ném AssertionError trước khi in PASS.
- `pointsY=[11, 22, 33]` xác nhận VarHandle open sequence đọc đúng từng phần tử và đúng số tọa độ.
- `selected=y:4` chứng minh `select` chọn **layout của field y** với tên y, size 4.
- Ba dòng `IllegalArgumentException` là các trường hợp lỗi **có chủ ý**, không phải test hỏng: open path không hợp lệ với `byteOffset`; bound index không hợp lệ với `select`; tên field không tồn tại.
- `afterClose=IllegalStateException` là trường hợp cố ý thử truy cập qua VarHandle khi arena đã đóng; chứng minh layout hợp lệ **không** bỏ qua lifetime của memory.

## 11. Map sang C struct thật: PathElement không tự hiểu ABI

Java `structLayout` mô tả **bytes bạn chỉ định**. Nếu một native library có struct C:

~~~c
/* C declaration: kiểm tra ABI trước khi dùng chung memory với Java. */
#include <stdint.h>

struct Header {
    uint8_t kind;
    int32_t count;
};
struct Point {
    int32_t x;
    int32_t y;
};
struct Record {
    struct Header header;
    struct Point points[3];
    int32_t checksum;
};
~~~

Trên **ABI phổ biến** có alignment 4 cho `int32_t`, compiler C thường tạo:

~~~text
sizeof(Header) = 8
offsetof(Header, count) = 4
sizeof(Point) = 8
offsetof(Point, y) = 4
offsetof(Record, points) = 8
offsetof(Record, checksum) = 32
sizeof(Record) = 36
~~~

Đây là **giá trị cần xác nhận trên compiler/architecture thực**, không phải mặc định của mọi C implementation. Có thể thêm các compile-time assertions trong một file C để kiểm chứng:

~~~c
/* Fragment C phải đặt cùng các struct declarations ở trên. */
#include <stddef.h>

_Static_assert(sizeof(struct Header) == 8, "Header ABI mismatch");
_Static_assert(offsetof(struct Header, count) == 4, "count offset");
_Static_assert(sizeof(struct Point) == 8, "Point ABI mismatch");
_Static_assert(offsetof(struct Point, y) == 4, "y offset");
_Static_assert(offsetof(struct Record, points) == 8, "points offset");
_Static_assert(offsetof(struct Record, checksum) == 32, "checksum offset");
_Static_assert(sizeof(struct Record) == 36, "Record ABI mismatch");
~~~

Nếu compiler C từ chối một assertion, Java `MemoryLayout` đang **không khớp** native layout ở môi trường đó. Đừng bỏ assertion để làm build qua; hãy điều tra packing/alignment/compiler options rồi chỉnh layout theo đúng ABI và test lại.

**Một điều dễ quên:** C struct có thể có **tail padding** để kích thước toàn struct là bội của alignment lớn nhất; `MemoryLayout.structLayout` không tự thêm padding cuối như compiler C trong mọi trường hợp. Khi mô tả mảng struct, stride sai vì thiếu tail padding sẽ làm mọi phần tử từ index 1 trở đi lệch, dù field của phần tử 0 trông đúng. Test cả `sizeof(Record)` và offset phần tử thứ hai, không chỉ field đầu tiên.

### Offsets khác nhau giữa StructLayout và UnionLayout

Với struct, các member nằm nối tiếp và padding có thể làm offset tăng. Với union C, nhiều member chia sẻ **cùng vị trí đầu**, nên `MemoryLayout.unionLayout(...)` thường cho member offset bằng **0**. `groupElement("field")` vẫn chọn member theo tên; nhưng byte offset của field không nhất thiết duy nhất cho member identity. Không dùng công thức cộng dồn struct cho union.

## 12. Các dạng path nâng cao: named groups, indexed members, nested arrays, pointer

### 12.1. groupElement(index) đếm **member layouts**, kể cả padding

Với `header`:

~~~java
MemoryLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"));
~~~

Thành viên index 0 là `kind`, index 1 là **padding**, index 2 là `count`. Do đó:

~~~java
long byIndex = header.byteOffset(groupElement(2));       // 4
long byName = header.byteOffset(groupElement("count"));  // 4
~~~

Nếu sau này thêm một member vào trước `count`, chỉ số 2 có thể thay đổi còn path theo tên **ổn định hơn**. Trong code production, nên dùng tên cho semantic fields và dùng index khi layout không đặt tên hoặc khi thực sự cần xử lý group theo vị trí.

### 12.2. Sequence lồng nhau: matrix

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT));

long off = matrix.byteOffset(
        sequenceElement(1),
        sequenceElement(2)); // 20
~~~

Ở đây outer index 1 chọn hàng thứ 2, inner index 2 chọn cột thứ 3, mỗi `JAVA_INT` là 4 byte. Công thức offset: `(1 * 3 + 2) * 4 = 20`. Với indices chưa biết trước, dùng **hai** `sequenceElement()` trong `byteOffsetHandle` hoặc `varHandle`, rồi truyền hai `long` indices theo thứ tự.

### 12.3. arrayElementVarHandle cho mảng kích thước runtime

Đôi khi C declaration chứa `Point points[]` (flexible array member), số phần tử chỉ có lúc chạy. Trong trường hợp đó, có thể lấy `VarHandle` cho **một Point layout** rồi yêu cầu bước nhảy theo kích thước Point bằng `arrayElementVarHandle`:

~~~java
// Fragment, point là MemoryLayout struct {int x; int y}.
VarHandle xs = point.arrayElementVarHandle(groupElement("x"));
// Coordinates: MemorySegment, long base, long elementIndex.
// Buffer thật phải đủ chứa các Point liên tục.
int x2 = (int) xs.get(pointsMemory, 0L, 2L);
~~~

Đây **không phải** ví dụ tự cấp phát số phần tử runtime; `pointsMemory` phải là một `MemorySegment` hợp lệ có bounds và alignment phù hợp, do caller/native API cấp đúng size. Với variable-length C array, bạn phải lấy số phần tử/buffer length từ contract C, không dereference tùy ý chỉ vì handle chấp nhận index.

### 12.4. dereferenceElement dùng cho C pointer field

Nếu một struct có field kiểu pointer (`ValueLayout.ADDRESS.withTargetLayout(...)`), `PathElement.dereferenceElement()` có thể tạo đường dẫn đi **qua địa chỉ được chứa trong field đó** đến target layout để tạo VarHandle. Đây là khác biệt căn bản với nested struct được **nhúng trực tiếp**:
- Nhúng struct: byte offset tính được bằng cộng các offsets tại layout.
- Pointer tới struct: địa chỉ target chỉ biết từ **giá trị pointer trong memory khi chạy**, không thể coi target nằm ngay sau field pointer của root.

`byteOffset(...)` và `select(...)` không nhận đường dẫn có dereference path trong JDK 22 API. Khi làm pointer dereference qua VarHandle, native target memory phải còn sống và có target layout hợp lệ; sai pointer/size có thể gây JVM crash. Với bài tính offset cho struct nhúng và array, **không cần `dereferenceElement()`**.

## 13. Các loại lỗi và đúng cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách giải quyết |
|---|---|---|
| `IllegalArgumentException` khi `groupElement("foo")` | Root/current group không có member tên foo | Xem tên `withName` và thứ tự path; field có thể ở group con |
| `IllegalArgumentException` khi đi `groupElement` sau sequence | Chưa chọn phần tử sequence | Chèn `sequenceElement(...)` trước `groupElement` |
| `IllegalArgumentException` từ `byteOffset` với `sequenceElement()` | Chọn **open path** cho API cần fixed offset | Dùng `sequenceElement(index)` hoặc `byteOffsetHandle` |
| `IllegalArgumentException` từ `select` với `sequenceElement(2)` | `select` không nhận **bound sequence index** | Dùng `sequenceElement()` để chọn loại layout |
| `IllegalArgumentException` khi `varHandle` chọn cả group | Kết quả path không phải `ValueLayout` | Chọn sâu tới primitive field hoặc dùng slice/layout APIs |
| `WrongMethodTypeException` khi `invokeExact` | Sai số lượng/loại tham số method handle | Kiểm tra `handle.type()`: base `long` + một `long` cho mỗi open path |
| `WrongMethodTypeException` khi `VarHandle.get/set` | Quên base offset hoặc dynamic sequence index | Với mở một index dùng `get(seg, 0L, i)` |
| Kết quả offset sai | Bỏ qua C padding/tail padding, nhầm bytes và elements | Đối chiếu `sizeof`, `offsetof`, `byteSize` và byte map |
| `IndexOutOfBoundsException` | Offset/index dẫn đến truy cập ngoài segment | Kiểm tra segment size, value layout size, offset và capacity |
| `IllegalArgumentException` do alignment | Memory address/offset không đáp ứng layout alignment | Cấp phát phù hợp hoặc mô tả packed layout đúng ABI |
| `WrongThreadException` | Dùng confined arena segment từ thread khác | Giữ đúng owner thread; nếu cần sharing, dùng shared arena + đồng bộ |
| `IllegalStateException` sau `Arena.close()` | Segment không còn sống | Không dùng view/VarHandle sau close; điều chỉnh ownership |
| Java C struct đọc sai nhưng không ném exception | Native layout, endian hoặc value type sai | So C ABI/byte order và test thực với C fixture |
| `package java.lang.foreign does not exist` | Dùng JDK trước 22 hoặc compile target không tương thích | Chọn JDK 22+; bản 17/21 có API/flags khác |

**Lỗi về path và lỗi về memory là hai tầng khác nhau.** Một path có thể hợp lệ nhưng segment đã đóng, hoặc path có offset hợp lệ trên layout nhưng ABI của thư viện C lại khác. Test cả hai tầng, không kết luận “offset đúng” chỉ vì không có Java exception.

## 14. Thiết kế API thực tế: constants cho layout, paths ổn định cho field

Một binding lớn thường đặt layout trong một class duy nhất, tính offsets/handles một lần:

~~~java
// Fragment thiết kế, không phải class độc lập.
static final MemoryLayout RECORD_LAYOUT = ...;  // Đã khai báo đầy đủ.
static final long COUNT_OFFSET = RECORD_LAYOUT.byteOffset(
        groupElement("header"), groupElement("count"));
static final VarHandle POINT_Y = RECORD_LAYOUT.varHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
~~~

Lợi ích:
- Không lặp phép tính offset thủ công ở nhiều file.
- Path theo tên giúp refactor bố trí field có kiểm soát.
- Nhìn vào code đã biết một giá trị là **offset bytes** hay **index của sequence**.
- Offset constants và varhandles được kiểm thử cùng một layout nguồn.
- Tránh tạo lại handles trong hot loop, giảm chi phí setup không cần thiết.

Nếu có nhiều phiên bản C ABI, không giả định một `RECORD_LAYOUT` dùng được mọi platform. Có thể thiết kế factory nhận **ABI contract** (header version, struct size/alignment, feature flags), xác thực `sizeof/offsetof` khi tích hợp và chỉ phát hành handles khi layout đã hợp lệ.

### Kiểm tra layout ngay tại startup

Thay vì đợi đến lúc xử lý record thứ triệu, kiểm tra:

~~~java
// Fragment dùng trong initialization/validation.
if (RECORD_LAYOUT.byteSize() != 36) {
    throw new IllegalStateException("Unexpected Record layout size");
}
long y2 = RECORD_LAYOUT.byteOffset(
        groupElement("points"), sequenceElement(2), groupElement("y"));
if (y2 != 28) {
    throw new IllegalStateException("Unexpected points[2].y offset");
}
~~~

Hai assertions trên **chỉ có ý nghĩa cho layout mẫu và ABI giả định của bài**. Trong production, giá trị expected phải đến từ C ABI/header đang hỗ trợ, không hardcode “36 và 28” nếu library có nhiều biến thể.

### Thread-safe layout không có nghĩa thread-safe segment

`MemoryLayout` được thiết kế immutable, có thể dùng chung như constants. Nhưng nếu hai Java threads cùng đọc/ghi **cùng native memory** qua cùng VarHandle, vẫn cần memory model/synchronization thích hợp. `Arena.ofShared()` không tự đặt mutex. Không đồng nhất **reusable layout definition** với **mutable memory content**.

## 15. Bài tập tự luyện (có lời giải)

### Bài 1. Chọn path đúng

Cho Record trong bài, muốn offset field `header.count` từ root.

A. `groupElement("count")`  
B. `groupElement("header"), groupElement("count")`  
C. `sequenceElement(0), groupElement("count")`

**Đáp án B.** `count` không phải member trực tiếp của `record`; phải đi qua group `header`. Offset từ root là 4 byte.

### Bài 2. Tính tay offset của points[1].x

`points` bắt đầu ở byte 8; mỗi Point 8 bytes, x ở offset 0 trong Point. Vậy `points[1].x` = `8 + 1 * 8 + 0 = 16`.

Code:

~~~java
long x1 = record.byteOffset(
        groupElement("points"), sequenceElement(1), groupElement("x"));
System.out.println(x1); // 16
~~~

### Bài 3. Vì sao hai path sau xử lý khác nhau?

~~~java
record.byteOffset(
    groupElement("points"), sequenceElement(1), groupElement("y"));
record.select(
    groupElement("points"), sequenceElement(1), groupElement("y"));
~~~

**Đáp án:** `byteOffset` hợp lệ và trả 20; `select` từ chối fixed-index sequence path trong JDK 22+ và ném `IllegalArgumentException`. Để chọn loại layout y, thay `sequenceElement(1)` bằng `sequenceElement()` trong lời gọi `select`.

### Bài 4. Hàm tính offset động nhận bao nhiêu arguments?

~~~java
MethodHandle off = record.byteOffsetHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
~~~

**Đáp án:** hai `long`: một base offset, một sequence index; return là `long`. Với base 0, index 2, kết quả 28. Gọi `off.invokeExact(2L)` sẽ không khớp method type.

### Bài 5. Tại sao dùng groupElement(2) có thể nguy hiểm khi sửa struct?

Vì nó chỉ “member thứ ba trong group”; nếu thêm/xóa/move padding hoặc member ở trước thì index thay đổi. `groupElement("count")` mô tả đúng ý định hơn và không phụ thuộc vị trí thành viên, dù bạn vẫn phải kiểm tra ABI khi thay layout.

### Bài 6. Sửa lỗi thiếu tọa độ

~~~java
// Sai: y là VarHandle có open sequence path.
int v = (int) y.get(segment, 2L);
~~~

**Đáp án:** cần truyền base offset **và** index: `int v = (int) y.get(segment, 0L, 2L);`. Nếu không, đó là lỗi method type của VarHandle, không phải “index 2 quá lớn”.

### Bài 7. Phân biệt tên trường và tên symbol

`ValueLayout.JAVA_INT.withName("checksum")` có khiến `SymbolLookup.find("checksum")` tự tìm được biến C cùng tên không?

**Đáp án:** Không. `withName` là metadata của MemoryLayout, còn SymbolLookup tra native exported symbols trong library/loader. Chúng thuộc hai không gian tên/khả năng khác nhau.

### Bài 8. Khi nào dùng arrayElementVarHandle thay cho sequenceElement()?

Khi dữ liệu native là mảng elements có số phần tử quyết định ở runtime và bạn đã có buffer size hợp lệ, `point.arrayElementVarHandle(groupElement("x"))` có thể stride theo size của Point mà không cần tạo trước một `sequenceLayout(N, point)` với N cố định. Vẫn cần bounds check, ownership và ABI hợp lệ.

## 16. Checklist nghiệm thu cho mô hình đặt tên và offset

- [ ] Dùng **JDK 22+** cho API `java.lang.foreign` finalized của ví dụ; compile bằng `--release 22` nếu muốn baseline 22.
- [ ] Mỗi field nghiệp vụ của `StructLayout/UnionLayout` được đặt tên rõ ràng bằng `withName`; không phụ thuộc tên lặp mơ hồ.
- [ ] Nắm root layout khi tính offsets; không cộng offsets tính từ các roots khác nhau hai lần.
- [ ] Dùng `groupElement("name")` với group và `sequenceElement(index)` với mảng, đúng thứ tự cây.
- [ ] Có padding đúng theo C ABI: size, alignment, offsets, tail padding và element stride.
- [ ] `byteOffset` dùng path cố định; không truyền open path.
- [ ] `select` dùng open sequence path khi chọn layout phần tử; không truyền fixed index.
- [ ] `byteOffsetHandle` nhận base offset `long` và một `long` cho mỗi open sequence element.
- [ ] `varHandle` chọn tới value layout, truyền `MemorySegment`, base offset, các chỉ số runtime đúng số lượng.
- [ ] `MemorySegment` đủ bytes, alignment, scope còn sống và thread được phép dùng; không coi layout path là cơ chế nới bounds.
- [ ] Thử các lỗi có chủ ý: missing field, nhầm fixed/open path, sai VarHandle arguments, arena closed.
- [ ] Nếu mapping sang C thật: dùng `sizeof/offsetof`/compiler ABI checks, không dựa vào layout tự suy diễn.
- [ ] Chỉ chia sẻ immutable layouts/handles khi thích hợp; synchronization của memory mutable vẫn phải thiết kế riêng.
- [ ] Offset constants và handles có test được kiểm chứng trên các OS/architectures sẽ triển khai.

## 17. Tổng kết và nguồn tham khảo

**Tên trường** do `withName("field")` gắn trên member layout; **đường dẫn** do `MemoryLayout.PathElement` xây từ `groupElement` và `sequenceElement`; **offset** do `byteOffset` hoặc `byteOffsetHandle` tính; **truy cập dữ liệu** do `varHandle` và `MemorySegment` thực hiện trong lifetime của `Arena`. Đặt tên giúp code ổn định, nhưng **không tự đảm bảo đúng ABI**: padding, alignment, byte order, bounds và native ownership vẫn cần xác nhận.

Ghi nhớ bảng phân biệt:

| Nhu cầu | API nên chọn |
|---|---|
| Đặt tên field | `ValueLayout.withName("field")` hoặc `MemoryLayout.withName(...)` |
| Lấy offset của field cố định | `root.byteOffset(groupElement(...), ...)` |
| Lấy offset của array field tại index cụ thể | `sequenceElement(index)` trong `byteOffset(...)` |
| Chọn layout loại field trong array | `root.select(..., sequenceElement(), ...)` |
| Tính offset tại runtime với index | `root.byteOffsetHandle(..., sequenceElement(), ...)` |
| Đọc/ghi field trong segment theo index | `root.varHandle(..., sequenceElement(), ...)` |
| Truy cập mảng length động không biết khi tạo layout | `elementLayout.arrayElementVarHandle(...)`, kèm kiểm tra native buffer |

Tài liệu chính thức dành cho API ở JDK 22+:
- [JEP 454: Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)
- [Oracle JDK 22 — MemoryLayout, layout paths, open path elements và methods](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle JDK 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html)
- [Oracle JDK 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle JDK 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle JDK 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)

Khi chuyển code sang JDK mới hơn, đối chiếu Javadoc của **đúng runtime đang dùng**; khi trao đổi dữ liệu với C, đối chiếu **C ABI thật của compiler**. Một offset “có vẻ hợp lý” nhưng sai 1–4 byte có thể làm lỗi dữ liệu khó phát hiện hơn cả một Java exception rõ ràng.