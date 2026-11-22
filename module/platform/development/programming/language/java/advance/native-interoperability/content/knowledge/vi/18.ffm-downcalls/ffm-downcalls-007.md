# Truyền struct theo giá trị, nhận struct và tham số SegmentAllocator bổ sung trong FFM

## 1. Mục tiêu: C struct by-value không phải C struct pointer

Trong **Foreign Function & Memory API (FFM)**, Java có thể gọi trực tiếp các hàm native theo C ABI mà không cần viết một JNI wrapper cho từng hàm. Khi hàm C nhận hoặc trả về `struct` **theo giá trị** (*by value*), lập trình viên phải mô tả bố cục struct bằng `StructLayout` và sử dụng `MemorySegment` làm **carrier** bên phía Java.

Điểm đặc biệt của đề bài: nếu hàm C **trả về struct theo giá trị**, downcall `MethodHandle` của FFM **có thêm một đối số `SegmentAllocator`** để linker biết nơi cấp phát bộ nhớ chứa kết quả. Đối số này nằm ở **chữ ký MethodHandle phía Java**, **không phải** tham số mới trong khai báo hàm C. **Không được tự sửa hàm C để thêm `SegmentAllocator` hay một đối số `void* result` chỉ vì thấy Java cần allocator.**

Ví dụ C:

~~~c
typedef struct {
    int x;
    int y;
} Pair;

Pair pair_add(Pair a, Pair b);          /* Nhận 2 struct by-value, trả struct by-value */
int pair_sum(Pair p);                  /* Nhận struct by-value, trả int */
void pair_shift(Pair *p, int dx, int dy); /* Nhận con trỏ tới struct */
~~~

Đây là **các khai báo minh họa**, chưa phải file C hoàn chỉnh. Chúng có **hợp đồng ABI khác nhau**:

- `pair_add(Pair, Pair)`: linker có thể chuyển các trường struct qua thanh ghi, stack hoặc kết hợp, tùy ABI. Hai đối số Java là các `MemorySegment` biểu diễn **giá trị struct**, không phải tham số C `Pair*`.
- `pair_sum(Pair)`: đầu vào là struct by-value nhưng kết quả là số nguyên; **không cần thêm allocator** cho giá trị trả về.
- `pair_shift(Pair*, int, int)`: đối số đầu là **địa chỉ con trỏ**; khai báo FFM phải dùng `ValueLayout.ADDRESS`, và C có thể sửa dữ liệu bên trong vùng nhớ của Java.

**Mục tiêu thực hành:** tạo một thư viện C nhỏ với `Pair`, biên dịch trên Linux/macOS/Windows, rồi dùng Java 22+ gọi hàm **truyền struct theo giá trị**, **nhận struct trả về**, **truyền allocator**, so sánh với truyền con trỏ, đọc/ghi fields bằng `VarHandle` và kiểm tra `sizeof`/`offsetof` trước khi downcall.

Đây là kiến thức **FFM chuẩn từ JDK 22 (JEP 454)**. Trên JDK 21, API vẫn ở trạng thái preview (JEP 442), cần `--enable-preview` và một số tên overload có thể khác. Các ví dụ chính của bài dành cho **JDK 22+**.

## 2. Mô hình dữ liệu của struct theo giá trị

Giả sử trong C:

~~~c
typedef struct {
    int x;
    int y;
} Pair;
~~~

Với ABI thông dụng nơi C `int` có **4 byte** và alignment 4 byte, cấu trúc có:

~~~text
Pair (sizeof = 8 byte, alignof = 4 byte)

byte offset      0 1 2 3   4 5 6 7
                 +-------+-------+
                 |   x   |   y   |
                 +-------+-------+
                   int     int

x ở offset 0, y ở offset 4
~~~

Khi truyền một `Pair` **by-value**, lời gọi C có ngữ nghĩa:

~~~c
Pair change_copy(Pair value) {
    value.x += 100;
    return value;
}
~~~

Đây là **trích đoạn minh họa**. C nhận giá trị của `Pair` theo ABI và sửa `value.x` trong bản sao tham số; dữ liệu của người gọi không tự động bị sửa. Ngược lại:

~~~c
void change_pointer(Pair *value) {
    value->x += 100;
}
~~~

Đây cũng chỉ là **trích đoạn**. Hàm nhận địa chỉ và sửa trực tiếp backing memory được con trỏ trỏ tới. Nếu pointer sai hoặc đã hết hạn, có thể gây crash/memory corruption.

Sơ đồ so sánh:

~~~text
Java MemorySegment input --> FFM linker --> C pair_add(Pair input, ...)
                          [by-value]      C nhận giá trị/ABI aggregate
                                          C không được coi tham số là Pair*

Java MemorySegment input --> FFM linker --> C pair_shift(Pair *input, ...)
                          [ADDRESS]       C nhận địa chỉ
                                          C có thể sửa backing memory

C pair_make(...) returns Pair by-value
           |
           v
FFM linker áp dụng calling convention của ABI
           |
           +-- sử dụng SegmentAllocator do Java cung cấp để có vùng lưu kết quả
           |
           v
Java nhận MemorySegment biểu diễn struct trả về
~~~

Không nên tự suy đoán rằng “by-value” luôn tương ứng với một lần `memcpy` cố định hoặc một con trỏ ẩn. Tùy ABI, C compiler có thể truyền/trả struct nhỏ qua registers và struct lớn qua vùng nhớ/hidden return pointer. **FFM native linker** là thành phần xử lý những quy tắc đó dựa trên `FunctionDescriptor` hợp lệ. Java chỉ thấy các carrier `MemorySegment` và đối số allocator bổ sung khi có group return.

## 3. Khai báo StructLayout khớp C ABI

Trong FFM, một C `struct` được mô hình hóa bằng `MemoryLayout.structLayout(...)`, trả về `StructLayout` (một dạng `GroupLayout`). Các trường kiểu số nguyên thường được mô tả bằng `ValueLayout` phù hợp với ABI.

JDK 22:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout PAIR = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
).withName("Pair");
~~~

Đây là **trích đoạn**, không phải file Java hoàn chỉnh; ví dụ chạy được nằm ở phần 7.

- `JAVA_INT` có carrier `int` và kích thước **4 byte**. Trong bài ta chọn C `int` và kiểm tra bằng `_Static_assert(sizeof(int) == 4)`.
- `withName("x")` và `withName("y")` là **nhãn dùng khi truy cập layout**, không phải tên được chuyển qua C ABI. Bỏ các nhãn này không làm C struct tự đổi layout, nhưng sẽ ảnh hưởng `groupElement("x")`.
- `PAIR.byteSize()` phải khớp `sizeof(Pair)`.
- `PAIR.byteAlignment()` phải khớp alignment cần thiết của C struct.
- `PAIR.byteOffset(groupElement("y"))` phải khớp `offsetof(Pair, y)`.

Không dùng Java POJO/record tự động thay thế `MemorySegment` trong `FunctionDescriptor`. FFM không biết cách marshal một Java object có fields `x`/`y` thành đúng native aggregate ABI nếu không có một binding layer do bạn viết.

### 3.1. Kiểm tra layout bằng native side

Đối chiếu kích thước và offset thật là cách tránh lỗi "chạy được trên laptop nhưng sai trên platform khác":

~~~c
/* Trích đoạn trong C, yêu cầu #include <stddef.h> */
int pair_size(void) {
    return (int) sizeof(Pair);
}

int pair_offset_y(void) {
    return (int) offsetof(Pair, y);
}
~~~

Bài thực hành sẽ **export hai hàm** trên, gọi bằng FFM trước khi thực hiện các downcall có struct by-value. Nếu kích thước/offset sai, chương trình dừng thay vì truyền native data sai.

Cũng có thể dùng `_Alignof(Pair)` của C11 để đối chiếu alignment. Bài sẽ đặt `_Static_assert` trong file C nhằm báo lỗi biên dịch nếu đang chạy trên ABI không đáp ứng giả định.

### 3.2. StructLayout KHÔNG tự thêm mọi padding của C

Ví dụ khác:

~~~c
typedef struct {
    char tag;
    double value;
    int count;
} Mixed;
~~~

Với **ABI 64-bit thông dụng** mà C `double` có alignment 8 byte, layout thường là:

~~~text
offset 0: char tag       (1 byte)
offset 1..7: padding    (7 byte)
offset 8: double value  (8 byte)
offset 16: int count    (4 byte)
offset 20..23: tail padding (4 byte)
sizeof(Mixed) = 24, alignof(Mixed) = 8
~~~

Có thể mô tả trên Java **chỉ khi ABI thực tế khớp**:

~~~java
// Trích đoạn JDK22, không tự động portable sang mọi ABI.
StructLayout MIXED = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("tag"),
    MemoryLayout.paddingLayout(7),
    ValueLayout.JAVA_DOUBLE.withName("value"),
    ValueLayout.JAVA_INT.withName("count"),
    MemoryLayout.paddingLayout(4)
);
~~~

Nếu không chèn padding theo C ABI, Java `structLayout` sẽ ghép các member **liên tiếp theo thứ tự khai báo**, và số byte/offset có thể không khớp C. Vì linker cần layout đúng, việc bỏ padding **không chỉ khiến dữ liệu đọc sai**, mà còn có thể khiến cách phân loại aggregate vào thanh ghi/stack và hình thức trả về sai, dẫn đến crash.

**Không lấy ví dụ `Mixed` trên làm chuẩn toàn cầu.** C ABI 32-bit, packed structs, pragmas, compiler flags hoặc các nền tảng khác có thể có kích thước/alignment khác. Hãy dùng `sizeof`, `offsetof`, `_Alignof` (và tài liệu ABI) để xác nhận. `Linker.canonicalLayouts()` cung cấp một số kiểu C scalar canonical của ABI, nhưng **không tự suy ra padding của một struct bất kỳ từ header C**.

## 4. FunctionDescriptor cho by-value và pointer

Trong bài, Java dùng một `StructLayout PAIR` đã định nghĩa. Ba dạng chính:

~~~java
// C: Pair pair_add(Pair a, Pair b);
FunctionDescriptor addDesc =
        FunctionDescriptor.of(PAIR, PAIR, PAIR);

// C: int pair_sum(Pair p);
FunctionDescriptor sumDesc =
        FunctionDescriptor.of(ValueLayout.JAVA_INT, PAIR);

// C: void pair_shift(Pair *p, int dx, int dy);
FunctionDescriptor shiftDesc =
        FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT
        );
~~~

Đây là **trích đoạn**, các import và biến `PAIR` nằm ở ví dụ đầy đủ.

Nhớ ba quy tắc:

1. **`FunctionDescriptor.of(returnLayout, argumentLayouts...)`**: phần tử **đầu tiên là layout kiểu trả về**, không phải tham số đầu tiên của C.
2. **`PAIR` đại diện C `Pair` by-value** trong vị trí argument hoặc return. **`ValueLayout.ADDRESS` đại diện con trỏ** như `Pair*`.
3. **`FunctionDescriptor.ofVoid(...)`** chỉ dành cho C function có kiểu trả về `void`. C `Pair` return là một group layout, tuyệt đối không thay bằng `ADDRESS` cho nhanh.

Bảng ánh xạ:

| C signature | FFM function descriptor | Java MethodHandle carrier type |
|---|---|---|
| `Pair pair_make(int, int)` | `of(PAIR, JAVA_INT, JAVA_INT)` | `(SegmentAllocator, int, int) -> MemorySegment` |
| `Pair pair_add(Pair, Pair)` | `of(PAIR, PAIR, PAIR)` | `(SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment` |
| `Pair pair_tweak_copy(Pair)` | `of(PAIR, PAIR)` | `(SegmentAllocator, MemorySegment) -> MemorySegment` |
| `int pair_sum(Pair)` | `of(JAVA_INT, PAIR)` | `(MemorySegment) -> int` |
| `void pair_shift(Pair*, int, int)` | `ofVoid(ADDRESS, JAVA_INT, JAVA_INT)` | `(MemorySegment, int, int) -> void` |
| `int pair_size(void)` | `of(JAVA_INT)` | `() -> int` |

Bảng dùng **downcall handle đã ràng buộc với địa chỉ hàm** (`linker.downcallHandle(symbol, descriptor)`), không dùng unbound handle có thêm một đối số function address.

Lưu ý: C `struct` trả về by-value có thể là `struct Pair` hoặc typedef `Pair`; cả hai có cùng semantics nếu thực chất cùng loại. Ngược lại, `Pair*` trả về C pointer là trường hợp khác hoàn toàn: Java nhận một segment biểu diễn **địa chỉ**, thường dài 0, và **không có `SegmentAllocator` bổ sung chỉ do return kiểu pointer**.

## 5. Vì sao SegmentAllocator xuất hiện thêm ở Java?

`SegmentAllocator` là giao diện có phương thức trừu tượng `allocate(long byteSize, long byteAlignment)`. Nó diễn tả **cách cung cấp vùng native memory theo kích thước và alignment**. `Arena` cũng là một `SegmentAllocator`, nên `Arena.ofConfined()`, `Arena.ofShared()` đều có thể được truyền tới downcall cần nhận struct result.

Khi return layout là một **group layout**, FFM phải có vùng nhớ phía Java để biểu diễn aggregate trả về. Cụ thể:

~~~text
C declaration: Pair pair_add(Pair a, Pair b);

Java:
    StructLayout PAIR = ...
    FunctionDescriptor.of(PAIR, PAIR, PAIR)
    MethodHandle add = linker.downcallHandle(symbol, descriptor)

add.type():
    (SegmentAllocator, MemorySegment, MemorySegment)MemorySegment
     ^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^  ^^^^^^^^^^^^^
     ALLOCATOR BỔ SUNG  C Pair a       C Pair b

Kết quả:
    MemorySegment đại diện Pair trả về by-value
    Có scope/lifetime của allocation do allocator tạo
~~~

**Allocator không nằm trong prototype C.** Nếu C compiler cần một hidden return buffer pointer theo ABI, đó là chi tiết do **linker/runtime tự xử lý**. Không thêm `SegmentAllocator` vào C header, không tự đổi C `Pair pair_add(Pair, Pair)` thành `void pair_add(void*, Pair*, Pair*)` và không truyền một C pointer result ngẫu nhiên chỉ vì Java handle có một tham số đầu.

Điều kiện phát sinh allocator được quyết định bởi **layout của giá trị trả về (group)**, không bởi việc tham số đầu vào có phải struct hay không. Ví dụ `pair_sum(Pair)` nhận struct by-value nhưng trả `int`, vì thế handle của nó **không có allocator prefix**.

### 5.1. Đúng thứ tự cho bound downcall handle

~~~java
// Giả sử MethodHandle add và Arena arena đã được tạo hợp lệ.
MemorySegment result = (MemorySegment) add.invokeExact(
        (SegmentAllocator) arena, left, right
);
~~~

Đây là **trích đoạn**. Khi dùng `invokeExact`, kiểu Java tại call site phải **khớp chính xác** `MethodHandle.type()`:

- Return cast `(MemorySegment)` là bắt buộc để compiler chọn đúng signature khi sử dụng `invokeExact`.
- Dùng `(SegmentAllocator) arena` (hoặc khai báo `SegmentAllocator allocator = arena`) để call-site type là **`SegmentAllocator`**, không phải `Arena`.
- Hai arguments `left` và `right` phải có type **`MemorySegment`** và đại diện struct hợp lệ.
- Kết quả chỉ được dùng khi arena của allocator còn sống.

**Lỗi thường thấy:**

~~~java
// SAI/được đưa ra để giải thích, không chạy đoạn này:
MemorySegment result = (MemorySegment) add.invokeExact(
        arena, left, right
);
~~~

Nếu biến `arena` có **kiểu tĩnh `Arena`**, compiler sẽ ký hiệu call site `(Arena, MemorySegment, MemorySegment) -> MemorySegment`, không khớp handle đòi `SegmentAllocator`. Kết quả có thể là `WrongMethodTypeException`. `Arena implements SegmentAllocator` **không đủ** cho `invokeExact` nếu không có đúng kiểu tĩnh tại call site. `MethodHandle.invoke` có thể thực hiện một số chuyển đổi thích hợp, nhưng trong bài ta cố ý chọn `invokeExact` để phát hiện lỗi kiểu sớm.

### 5.2. Handle có địa chỉ hàm và handle chưa gắn địa chỉ

Hai cách tạo downcall:

~~~java
// Bound to symbol: không có address prefix lúc invoke.
MethodHandle bound = linker.downcallHandle(symbol, descriptor);

// Unbound: cần address prefix lúc invoke.
MethodHandle unbound = linker.downcallHandle(descriptor);
~~~

Đây là **trích đoạn**. Với return `PAIR` và các parameters `(PAIR, PAIR)`:

- `bound` có dạng **`(SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment`**.
- `unbound` có dạng **`(MemorySegment functionAddress, SegmentAllocator allocator, MemorySegment, MemorySegment) -> MemorySegment`**.

Ở `unbound`, `functionAddress` **không phải một tham số C**; nó cho linker biết sẽ gọi hàm tại địa chỉ nào ở lần gọi đó. `SegmentAllocator` vẫn là virtual parameter để cấp vùng nhớ cho struct return. Các options khác như capture call state có thể thêm các prefix arguments riêng; kiểm tra `handle.type()` là nguồn sự thật khi debug.

## 6. SegmentAllocator nào nên dùng để nhận struct?

### 6.1. Arena.ofConfined — lựa chọn thực hành mặc định

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator allocator = arena;
    MemorySegment result = (MemorySegment) add.invokeExact(
            allocator, left, right
    );
    // Đọc result ngay tại đây; arena còn sống.
}
// Kết thúc try, arena đóng và result không còn hợp lệ.
~~~

Đây là **trích đoạn**: biến `add`, `left`, `right` phải có sẵn. `Arena.ofConfined()` có vòng đời xác định, cho phép thu hồi native memory đúng lúc và hạn chế truy cập ngoài owner thread.

Một số lưu ý:

- Result allocation có thể do linker dùng `allocator.allocate(PAIR.byteSize(), PAIR.byteAlignment())` hoặc cơ chế tương đương. **Không nên dựa vào số lần gọi allocator nội bộ** làm một hợp đồng portable.
- Các segments tạo bởi `arena` thuộc cùng scope; khi close, chúng không được dùng tiếp.
- Không cần tự cấp trước `MemorySegment result = arena.allocate(PAIR)` cho một bound downcall trả group rồi truyền result đó làm tham số C. Tham số `SegmentAllocator` cho phép runtime tự quản lý vùng lưu return.
- Khi có nhiều struct results, một arena có thể sở hữu nhiều allocations và dọn đồng thời.

### 6.2. Arena.ofShared — nhiều thread với vòng đời hữu hạn

`Arena.ofShared()` cũng là `SegmentAllocator`. Nó phù hợp khi những segments được tạo có thể cần được đọc từ nhiều Java threads, **nhưng vẫn có thời điểm đóng rõ ràng**. Không đóng arena khi thread khác đang dùng result hoặc native function vẫn đang giữ pointer tới vùng đó.

**Shared arena không tự đồng bộ mutations** vào fields của struct. Nếu nhiều threads cùng ghi, vẫn cần thiết kế memory ordering/concurrency phù hợp.

### 6.3. Arena.global và Arena.ofAuto — không phải mặc định cho kết quả tạm

- `Arena.global()` có unbounded lifetime: memory mà nó cấp phát **không được arena deallocate**. Dùng nó cho kết quả từng request có thể gây tăng native memory suốt vòng đời JVM.
- `Arena.ofAuto()` có lifetime do JVM/GC quản lý, không thể close xác định thời điểm. Có thể phù hợp một số thiết kế, nhưng không dùng nếu cần chắc chắn giải phóng native memory ngay sau downcall.

Với một lời gọi `Pair pair_add(...)` đơn giản, `ofConfined` thường dễ hiểu, dễ QA và có quy tắc cleanup rõ nhất.

### 6.4. Custom SegmentAllocator: tại sao nên cẩn thận?

`SegmentAllocator` là functional interface, nên có thể tạo allocator riêng hoặc dùng `SegmentAllocator.slicingAllocator(...)`/`prefixAllocator(...)`. Tuy nhiên, những allocators như vậy có thể hoạt động khác `Arena`:

- Một allocator có thể trả **các đoạn bộ nhớ chồng lấn** nếu thiết kế không phù hợp. Nếu linker ghi một struct result lên vùng vẫn đang dùng, kết quả trước có thể bị ghi đè.
- Một allocator có thể **hết dung lượng** hoặc trả memory có sai alignment.
- Một allocator có thể **không thread-safe**.
- Lifetime của segments trả về có thể không phù hợp với thời gian dùng result.

Tài liệu `SegmentAllocator` khuyến cáo khách hàng chỉ tương tác với allocator do mình quản lý và cân nhắc dùng `Arena` nhờ các đảm bảo về thread safety, scope và vùng nhớ không chồng lấn.

## 7. Ví dụ đầy đủ: Java 22 + thư viện C, struct by-value và struct return

Ta viết một thư viện nhỏ gồm các C functions sau:

~~~c
Pair pair_make(int x, int y);
Pair pair_add(Pair a, Pair b);
Pair pair_tweak_copy(Pair value);
int pair_sum(Pair value);
void pair_shift(Pair *value, int dx, int dy);
int pair_size(void);
int pair_offset_y(void);
~~~

Bảng ý nghĩa:

| Native function | Mục đích | Allocator prefix? |
|---|---|---|
| `pair_make` | Tạo một `Pair` và trả by-value | **Có** |
| `pair_add` | Nhận hai `Pair` by-value, trả `Pair` by-value | **Có** |
| `pair_tweak_copy` | Sửa bản sao by-value và trả bản sao | **Có** |
| `pair_sum` | Nhận `Pair` by-value, trả `int` | **Không** |
| `pair_shift` | Nhận `Pair*`, sửa in-place | **Không** |
| `pair_size` / `pair_offset_y` | Kiểm tra ABI của C trước khi truyền aggregate | **Không** |

**Không có JNI wrapper trong mã C của bài.** `System.loadLibrary` và `JNIEnv *` không cần thiết cho downcall qua `SymbolLookup.libraryLookup`.

### 7.1. C — tệp `pairffi.c`

~~~c
#include <stddef.h>

/* Export symbol phù hợp Windows/Linux/macOS. */
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    int x;
    int y;
} Pair;

/* Ví dụ này chỉ nhắm ABI có int=4 byte, align=4, Pair=8 byte. */
_Static_assert(sizeof(int) == 4, "C int must be 4 bytes");
_Static_assert(_Alignof(int) == 4, "C int alignment must be 4");
_Static_assert(sizeof(Pair) == 8, "Pair must be 8 bytes");
_Static_assert(_Alignof(Pair) == 4, "Pair alignment must be 4");
_Static_assert(offsetof(Pair, y) == 4, "Pair.y offset must be 4");

/* Return Pair by-value: Java downcall sẽ cần SegmentAllocator. */
FFM_EXPORT Pair pair_make(int x, int y) {
    Pair result = {x, y};
    return result;
}

/* Input và output đều by-value: C KHÔNG nhận Pair*. */
FFM_EXPORT Pair pair_add(Pair a, Pair b) {
    Pair result = {a.x + b.x, a.y + b.y};
    return result;
}

/* Sửa bản sao của tham số, không sửa Pair trong caller. */
FFM_EXPORT Pair pair_tweak_copy(Pair value) {
    value.x += 100;
    return value;
}

/* Input by-value nhưng kết quả scalar => không có allocator prefix. */
FFM_EXPORT int pair_sum(Pair value) {
    return value.x + value.y;
}

/* Khác by-value: nhận pointer và sửa backing memory in-place. */
FFM_EXPORT void pair_shift(Pair *value, int dx, int dy) {
    if (value != NULL) {
        value->x += dx;
        value->y += dy;
    }
}

/* Cấp số liệu thật để Java kiểm tra layout trước các by-value calls. */
FFM_EXPORT int pair_size(void) {
    return (int) sizeof(Pair);
}

FFM_EXPORT int pair_offset_y(void) {
    return (int) offsetof(Pair, y);
}
~~~

Đây là **file C hoàn chỉnh**, dùng các tính năng **C11** (`_Static_assert`, `_Alignof`). Khi build ở OS không thỏa điều kiện `int` 4-byte, alignment 4, `Pair` 8-byte, compiler sẽ dừng bằng lỗi static assert thay vì chạy bindings không tương thích. Đây là biện pháp giới hạn **đáng tin hơn** việc im lặng giả định C ABI luôn như nhau.

Các kết quả trong ví dụ đều nhỏ, tránh tràn signed `int` trong C. Với dữ liệu không tin cậy, cần xác định chính sách kiểm tra overflow để tránh undefined behavior trong native C khi cộng.

**Vì sao không có allocator trong C function?** C `Pair pair_add(Pair, Pair)` trả một struct thật theo C ABI. Native linker của JVM sẽ xử lý quy tắc truyền/trả aggregate, kể cả hidden return pointer nếu ABI yêu cầu. `SegmentAllocator` chỉ là giao diện cho Java chọn scope và vùng nhớ đích của kết quả.

### 7.2. Java — tệp `StructByValueDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.nio.file.Path;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public class StructByValueDemo {
    private static final StructLayout PAIR = MemoryLayout.structLayout(
            JAVA_INT.withName("x"),
            JAVA_INT.withName("y")
    ).withName("Pair");

    private static final VarHandle X = PAIR.varHandle(groupElement("x"));
    private static final VarHandle Y = PAIR.varHandle(groupElement("y"));

    private static MemorySegment newPair(Arena arena, int x, int y) {
        MemorySegment pair = arena.allocate(PAIR);
        X.set(pair, 0L, x);
        Y.set(pair, 0L, y);
        return pair;
    }

    private static int x(MemorySegment pair) {
        return (int) X.get(pair, 0L);
    }

    private static int y(MemorySegment pair) {
        return (int) Y.get(pair, 0L);
    }

    private static String show(MemorySegment pair) {
        return "(" + x(pair) + "," + y(pair) + ")";
    }

    private static MethodHandle bind(
            Linker linker, SymbolLookup lookup,
            String name, FunctionDescriptor descriptor
    ) {
        MemorySegment symbol = lookup.find(name).orElseThrow();
        return linker.downcallHandle(symbol, descriptor);
    }

    private static void requireType(
            MethodHandle handle, MethodType expected
    ) {
        if (!handle.type().equals(expected)) {
            throw new AssertionError(
                    "wrong handle type: " + handle.type()
                    + ", expected: " + expected
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        Path nativeLibrary = Path.of(
                System.mapLibraryName("pairffi")
        ).toAbsolutePath();

        MemorySegment resultOutsideArena;

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    nativeLibrary, arena
            );

            MethodHandle size = bind(
                    linker, lookup, "pair_size",
                    FunctionDescriptor.of(JAVA_INT)
            );
            MethodHandle offsetY = bind(
                    linker, lookup, "pair_offset_y",
                    FunctionDescriptor.of(JAVA_INT)
            );

            int cSize = (int) size.invokeExact();
            int cOffsetY = (int) offsetY.invokeExact();
            long javaOffsetY = PAIR.byteOffset(groupElement("y"));

            // Dừng trước khi truyền/nhận struct nếu layout không khớp.
            if (cSize != PAIR.byteSize()
                    || cOffsetY != javaOffsetY
                    || PAIR.byteAlignment() != 4L) {
                throw new AssertionError("C/Java Pair layout differs");
            }

            MethodHandle make = bind(
                    linker, lookup, "pair_make",
                    FunctionDescriptor.of(PAIR, JAVA_INT, JAVA_INT)
            );
            MethodHandle add = bind(
                    linker, lookup, "pair_add",
                    FunctionDescriptor.of(PAIR, PAIR, PAIR)
            );
            MethodHandle tweak = bind(
                    linker, lookup, "pair_tweak_copy",
                    FunctionDescriptor.of(PAIR, PAIR)
            );
            MethodHandle sum = bind(
                    linker, lookup, "pair_sum",
                    FunctionDescriptor.of(JAVA_INT, PAIR)
            );
            MethodHandle shift = bind(
                    linker, lookup, "pair_shift",
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS, JAVA_INT, JAVA_INT
                    )
            );

            // Bound handle trả Pair: allocator LÀ đối số đầu tiên.
            requireType(add, MethodType.methodType(
                    MemorySegment.class,
                    SegmentAllocator.class,
                    MemorySegment.class,
                    MemorySegment.class
            ));
            requireType(make, MethodType.methodType(
                    MemorySegment.class, SegmentAllocator.class,
                    int.class, int.class
            ));
            requireType(sum, MethodType.methodType(
                    int.class, MemorySegment.class
            ));

            // Java chuẩn bị hai struct đầu vào trong native memory.
            MemorySegment a = newPair(arena, 3, 4);
            MemorySegment b = newPair(arena, 10, 20);

            // SegmentAllocator là tham số của MethodHandle, không của C.
            SegmentAllocator allocator = arena;

            MemorySegment made = (MemorySegment) make.invokeExact(
                    allocator, 7, 8
            );
            MemorySegment added = (MemorySegment) add.invokeExact(
                    allocator, a, b
            );
            MemorySegment tweaked = (MemorySegment) tweak.invokeExact(
                    allocator, a
            );

            int total = (int) sum.invokeExact(added);

            System.out.println("C size = " + cSize);
            System.out.println("Java size = " + PAIR.byteSize());
            System.out.println("offset y = " + javaOffsetY);
            System.out.println("allocator first = "
                    + (add.type().parameterType(0)
                            == SegmentAllocator.class));
            System.out.println("a = " + show(a));
            System.out.println("b = " + show(b));
            System.out.println("made = " + show(made));
            System.out.println("added = " + show(added));
            System.out.println("tweaked copy = " + show(tweaked));
            System.out.println("sum(added) = " + total);

            // C function này nhận Pair* (ADDRESS), sửa in-place.
            shift.invokeExact(added, 1, 2);
            System.out.println("shifted by pointer = " + show(added));
            System.out.println("a unchanged = " + show(a));

            resultOutsideArena = added;
        }

        // Chỉ kiểm tra scope, KHÔNG dereference sau khi arena đóng.
        System.out.println("result alive after close = "
                + resultOutsideArena.scope().isAlive());
    }
}
~~~

**Đây là file Java 22 hoàn chỉnh**, không phải pseudocode. Nó dùng `SymbolLookup.libraryLookup` và `Linker.downcallHandle` để liên kết các symbols C, không dùng native declarations trong Java.

Một số điểm được cố ý làm rõ:

1. `PAIR` là `StructLayout` có **hai `int` 4-byte**, tên members x/y khớp C.
2. `X` và `Y` là `VarHandle` truy cập fields theo đường dẫn `groupElement`. `X.set(pair, 0L, x)` dùng offset gốc `0L` đúng method type của VarHandle.
3. `newPair` tạo native segment với `arena.allocate(PAIR)`, đảm bảo kích thước/alignment theo layout; không dựa vào memory unaligned bất kỳ.
4. `pair_size`/`pair_offset_y` được gọi trước khi tạo hoặc dùng downcall xử lý struct, kiểm tra runtime consistency.
5. `requireType` kiểm tra **MethodType thật** mà FFM tạo ra: `add` và `make` cần `SegmentAllocator` ở vị trí đầu; `sum` chỉ có `MemorySegment` input và scalar result.
6. Biến `allocator` được khai báo **kiểu tĩnh `SegmentAllocator`**, cho `invokeExact` đúng signature; bản thân object vẫn là `Arena.ofConfined()`.
7. `made`, `added`, `tweaked` là **những result segments** có scope do allocator cung cấp. Chúng chỉ được dereference khi arena còn mở.
8. `pair_tweak_copy(Pair)` thay đổi bản sao C, trả struct mới; `a` không đổi.
9. `pair_shift(Pair*)` nhận địa chỉ và sửa trực tiếp `added`, giúp phân biệt pointer semantics với by-value.
10. `resultOutsideArena.scope().isAlive()` được đọc sau try để chứng minh result theo scope allocator. Mã không cố truy cập field sau khi `arena.close()`.

**Kỹ thuật đọc `MethodHandle.type()`** rất hữu ích khi debug `WrongMethodTypeException`: đừng dựa vào số lượng tham số C để phỏng đoán chữ ký Java của downcall. Struct return có allocator prefix, unbound handle còn có address prefix; một số linker options cũng thêm tham số.

### 7.3. Build thư viện C

Chọn một compiler hỗ trợ C11, tạo thư viện cho **đúng OS và kiến trúc** của JVM. Không cần `jni.h`.

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -fPIC -shared pairffi.c -o libpairffi.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -fPIC -dynamiclib pairffi.c -o libpairffi.dylib
~~~

**Windows (Visual Studio 2022 Developer Command Prompt, cmd.exe):**

~~~bat
cl /std:c11 /LD pairffi.c /Fe:pairffi.dll
~~~

Lệnh Windows giả định MSVC có hỗ trợ C11 (`/std:c11`). `_Static_assert` và `_Alignof` có thể không khả dụng nếu dùng compiler C cũ; hãy nâng toolchain, không bỏ các điều kiện xác minh ABI chỉ để build chạy.

Binary cần được đặt **trong thư mục hiện hành** khi chạy Java, hoặc thay cách xây `Path nativeLibrary` để trỏ tới một đường dẫn tuyệt đối thực tế. `System.mapLibraryName("pairffi")` sinh ra `libpairffi.so` (Linux), `libpairffi.dylib` (macOS) hoặc `pairffi.dll` (Windows).

**Kiểm tra export** (tùy platform):

~~~text
Linux:   nm -D libpairffi.so
macOS:   nm -g libpairffi.dylib
Windows: dumpbin /EXPORTS pairffi.dll
~~~

Đây là **lệnh kiểm tra gợi ý**, không phải script portable chạy nguyên văn trên mọi OS. Xác nhận các tên symbol C như `pair_make`, `pair_add` và `pair_shift` xuất hiện đúng. Trên macOS, `nm` có thể hiển thị ký tự `_` tiền tố theo Mach-O symbol convention.

### 7.4. Biên dịch và chạy Java

Chạy trong thư mục chứa `StructByValueDemo.java` và thư viện đã build:

~~~bash
java -version
javac -version
javac --release 22 StructByValueDemo.java
java --enable-native-access=ALL-UNNAMED StructByValueDemo
~~~

Yêu cầu **JDK 22** khi dùng `--release 22`, và FFM đã finalized nên **không cần `--enable-preview`**. Cờ `--enable-native-access=ALL-UNNAMED` cấp quyền cho code Java trong classpath thực hiện các restricted native operations, trong đó có `SymbolLookup.libraryLookup` và `Linker.downcallHandle`.

**Stdout kỳ vọng trên ABI thỏa các static asserts:**

~~~text
C size = 8
Java size = 8
offset y = 4
allocator first = true
a = (3,4)
b = (10,20)
made = (7,8)
added = (13,24)
tweaked copy = (103,4)
sum(added) = 37
shifted by pointer = (14,26)
a unchanged = (3,4)
result alive after close = false
~~~

Giải thích:

- `pair_make(7, 8)` trả một struct từ C và Java nhận segment với fields `(7,8)`.
- `pair_add(Pair(3,4), Pair(10,20))` trả `(13,24)`; Java dùng **SegmentAllocator** để có native storage cho kết quả.
- `pair_tweak_copy(Pair(3,4))` tăng trường `x` của **tham số by-value** rồi trả `(103,4)`; `a` vẫn `(3,4)`.
- `pair_sum(Pair(13,24))` trả **scalar** 37; không truyền allocator cho handle này.
- `pair_shift(&added, 1,2)` sửa struct đang nằm trong segment `added` qua **pointer**, ra `(14,26)`.
- `arena.close()` ở cuối try làm result segments không còn hợp lệ; `scope().isAlive()` sau đó trả `false`.

**Trạng thái kiểm chứng:** chương trình được thiết kế bám API Java SE 22 và có stdout xác định cho C ABI đã khai báo, nhưng đoạn này không thay thế việc chạy test trên chính máy/ABI mục tiêu. Nếu linker từ chối group layout hoặc C compiler dừng `_Static_assert`, **không được sửa descriptor tùy tiện** để ép chạy; phải kiểm tra ABI, nền tảng được FFM hỗ trợ và compiler flags.

## 8. Ba luồng gọi có chữ ký khác nhau

### 8.1. Nhận struct by-value, trả struct by-value

~~~text
C:
    Pair pair_add(Pair a, Pair b)

Java FunctionDescriptor:
    of(PAIR, PAIR, PAIR)

Java bound MethodHandle:
    (SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment

Java invoke:
    add.invokeExact(allocator, a, b)

Kết quả:
    Segment chứa struct do allocator tạo
~~~

Hai `MemorySegment` truyền vào là nguồn dữ liệu mà linker dùng để tạo các **giá trị struct** theo quy tắc ABI. Không dùng `ValueLayout.ADDRESS` cho chúng: điều đó sẽ biến kiểu native được mô tả thành `Pair*`, khác prototype thật.

### 8.2. Nhận struct by-value, trả số nguyên

~~~text
C:
    int pair_sum(Pair value)

Java FunctionDescriptor:
    of(JAVA_INT, PAIR)

Java bound MethodHandle:
    (MemorySegment) -> int

Java invoke:
    int answer = (int) sum.invokeExact(pair)

Không có SegmentAllocator prefix!
~~~

Bản thân **việc truyền struct by-value** không làm phát sinh allocator extra. Nó chỉ xuất hiện vì **giá trị trả về** là group layout.

### 8.3. Nhận con trỏ, sửa struct tại chỗ

~~~text
C:
    void pair_shift(Pair *value, int dx, int dy)

Java FunctionDescriptor:
    ofVoid(ADDRESS, JAVA_INT, JAVA_INT)

Java bound MethodHandle:
    (MemorySegment, int, int) -> void

Java invoke:
    shift.invokeExact(pair, 1, 2)

Java thấy fields của segment thay đổi.
~~~

Ở đây `MemorySegment` biểu diễn **địa chỉ native** cho tham số C `Pair*`. FFM kiểm tra các điều kiện sống/thread của segment theo khả năng của API, nhưng **không tự xác minh native function tuân thủ đúng byteSize hoặc không giữ pointer sau lời gọi**. Đảm bảo pointer hợp lệ tới hết C invocation và mọi native consumer còn lại là trách nhiệm của binding.

## 9. Vì sao không thể thay struct by-value bằng ADDRESS?

Có hai chữ ký C rất khác:

~~~c
Pair make_pair(int x, int y);
Pair *allocate_pair(int x, int y);
~~~

Đây là **trích đoạn khai báo**, không phải chương trình cung cấp sẵn cả hai hàm.

- Với `make_pair`, C trả **giá trị aggregate**. Java descriptor phải có **return layout là `StructLayout`**, handle có `SegmentAllocator` extra và trả `MemorySegment` đại diện **kết quả theo giá trị**.
- Với `allocate_pair`, C trả **một con trỏ**. Java descriptor dùng **`ValueLayout.ADDRESS`**, handle **không có allocator prefix do return group**. Java nhận segment biểu diễn địa chỉ; nếu library cấp phát dynamic memory, cần contract riêng để biết size và hàm release.

Nếu mô tả `Pair make_pair(...)` bằng `FunctionDescriptor.of(ADDRESS, JAVA_INT, JAVA_INT)`, caller và callee **không thống nhất ABI**. Tùy OS/CPU, một struct có thể được trả qua registers/stack/hidden pointer theo cách không giống pointer return. Lỗi có thể là giá trị rác, silent corruption hoặc JVM crash.

**Không có cơ chế reflection tổng quát để JVM tra cứu “kiểu trả về C thật” từ địa chỉ symbol.** `FunctionDescriptor` là lời mô tả do bạn cung cấp; linker tin vào nó. Sai chữ ký là sai hợp đồng native.

### 9.1. SegmentAllocator không phải hàm malloc() của C

Một số người nhầm `SegmentAllocator` với `malloc` vì nó tạo memory. Nhưng:

- `SegmentAllocator` là **giao diện Java**, cho linker chọn nơi đặt aggregate result.
- C compiler xử lý ABI, có thể dùng thanh ghi hoặc hidden result pointer nội bộ; Java không cần tự đoán.
- `Arena` sở hữu storage cho result do nó allocate; khi đóng, result hết hiệu lực.
- Với C function `Pair* allocate_pair(...)`, memory allocation xảy ra ở **C library** và có thể đòi `free_pair(...)`. Truyền một Java `SegmentAllocator` không tự giải phóng con trỏ do C tạo ra.

Dùng đúng loại return layout để phân biệt **value** với **address**.

## 10. Vòng đời của struct result và các vấn đề sở hữu

Một result `MemorySegment` từ downcall có group return được gắn với **storage mà `SegmentAllocator` đã cấp**. Đừng nhầm:

~~~java
// Trích đoạn giả sử handle add đã được bind hợp lệ.
MemorySegment result;

try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator allocator = arena;
    MemorySegment a = arena.allocate(PAIR);
    MemorySegment b = arena.allocate(PAIR);
    result = (MemorySegment) add.invokeExact(allocator, a, b);
}

// SAI: result đã hết scope; đọc fields sau đây không hợp lệ.
// int x = (int) X.get(result, 0L);
~~~

Đây là **trích đoạn minh họa vòng đời**, không phải mã hoàn chỉnh vì `PAIR`, `add` và `X` chưa được khai báo trong đoạn. Khi ra khỏi try, arena bị đóng; Java FFM có thể ném `IllegalStateException` nếu truy cập result.

### 10.1. Đưa kết quả ra khỏi scope như thế nào?

Các cách hợp lý:

1. **Đọc fields thành Java primitives/record** khi arena còn sống; trả Java object chứa dữ liệu đã được copy, không trả segment sống ngắn.
2. **Copy sang một arena khác** có vòng đời được quản lý phù hợp nếu cần giữ native representation lâu hơn. Cần bảo đảm owner mới còn sống và data copy đúng layout.
3. **Dùng shared arena** nếu result phải tồn tại qua nhiều threads và có điểm cleanup xác định.
4. **Đừng mặc định dùng global arena** để tránh lỗi “segment closed”: làm vậy có thể chuyển bug lifetime thành **native memory leak process-lifetime**.

Nếu C library giữ địa chỉ của một struct input/result sau khi downcall kết thúc, việc Java close arena sớm sẽ gây dangling pointer. C signature by-value bình thường truyền **giá trị**, nhưng native function có thể cố giữ địa chỉ của một bản sao nội bộ; đó là một hợp đồng C khác cần xem xét và thường không hợp lệ khi stack/local copy hết đời.

### 10.2. Return allocator có thể là arena riêng với input arena

Về nguyên tắc, các input `MemorySegment` và result allocator **không bắt buộc cùng arena**, miễn chúng đều hợp lệ trong suốt downcall và có lifetime thích hợp. Ví dụ input tồn tại trong một shared arena, còn output được allocate trong request-scoped confined arena. Điều quan trọng là **return value thuộc lifetime của allocator đã cung cấp**, không tự động thuộc scope của từng input.

Đừng đóng input scope khi native call còn chạy; cũng không được đóng result allocator trước khi đã đọc hoặc chuyển dữ liệu.

### 10.3. Kết quả by-value khác view trỏ vào memory bên C

Một C `Pair` returned by value là **giá trị aggregate**. Java nhận một `MemorySegment` chứa dữ liệu kết quả do allocator cung cấp. Không suy ra result segment đang trỏ trực tiếp tới biến local của C callee.

Nếu hàm C trả `Pair*`, segment Java có thể chỉ là wrapper của địa chỉ đến C memory; cần biết **ai free**, **khi nào free** và **length**. Đừng gọi `reinterpret(sizeof(Pair))` lên pointer không rõ nguồn rồi giả định dữ liệu an toàn. `reinterpret` thay metadata nhưng **không xác minh backing allocation**.

## 11. Padding, alignment và khả năng portable của struct ABI

### 11.1. Vì sao chỉ sizeof bằng nhau có thể vẫn sai?

Hai struct có thể cùng `sizeof` nhưng offset fields khác nhau. Ví dụ packed struct, compiler pragmas, bit fields hoặc C unions có thể làm cách diễn giải khác dù tổng số byte trùng khớp.

Vì thế, với `Pair` ta kiểm tra:

~~~text
C sizeof(Pair)                  == Java PAIR.byteSize()
C offsetof(Pair, y)             == Java PAIR.byteOffset(groupElement("y"))
C _Alignof(Pair)                == Java PAIR.byteAlignment()
C type int width/alignment      == Java JAVA_INT width/alignment theo ABI
~~~

File C của ví dụ áp dụng `_Static_assert` cho cả width, alignment, size và offset. Java kiểm tra size/offset trước khi sử dụng `Pair` by-value. Với struct phức tạp hơn, cần kiểm tra **tất cả các offsets** cần thiết và alignment, không chỉ trường cuối.

### 11.2. Vì sao GroupLayout ảnh hưởng đến calling convention?

Trên ABI 64-bit, một struct nhỏ có thể được phân loại thành các nhóm truyền qua general-purpose registers, floating-point/SIMD registers hoặc stack. Một struct chứa hai `int` thường có cách truyền khác một struct chứa hai `double`. Một struct lớn còn có thể dùng hidden return buffer.

C linker không dựa vào tên Java `"Pair"`; nó dựa trên **kích thước, alignment và thành phần layout**. Nếu bạn mô tả struct có padding sai hoặc thay `double` thành `long`, native ABI classification có thể khác và lời gọi trở nên không an toàn dù `byteSize()` bằng nhau.

### 11.3. C bitfields, packed structs và unions

C bitfields có layout compiler/ABI-dependent; Java `MemoryLayout` không tự hiểu mọi quy ước bitfield trong C source. Một số packed structs có alignment nhỏ hơn natural alignment và **không phải native linker nào cũng hỗ trợ** cách truyền/trả by-value của chúng. Linker có thể ném `IllegalArgumentException` khi descriptor có group layout không được hỗ trợ, nhưng không phải mọi lỗi ABI đều bị phát hiện.

Khi gặp kiểu phức tạp, cân nhắc một C wrapper do bạn kiểm soát chuyển nó sang giao diện đơn giản hơn như các scalar parameters hoặc một pointer tới struct được khai báo rõ, kèm API cấp phát/giải phóng tường minh.

**Không thay by-value bằng pointer ở Java mà giữ nguyên C prototype**; nếu cần đơn giản hóa ABI, phải viết C wrapper **thực sự có prototype mới** và liên kết Java với wrapper đó.

## 12. Bẫy invokeExact và cách debug MethodType

`MethodHandle.invokeExact` là polymorphic signature: call site bị ràng buộc bởi **kiểu tĩnh của biểu thức arguments/return**. Các lỗi phổ biến:

| Cách gọi sai | Vì sao sai | Sửa |
|---|---|---|
| `add.invokeExact(a,b)` | Thiếu `SegmentAllocator` prefix cho group return | `add.invokeExact(allocator,a,b)` |
| `add.invokeExact(arena,a,b)` khi `arena` có static type `Arena` | Handle đòi `SegmentAllocator`, `invokeExact` không tự upcast | Khai báo `SegmentAllocator allocator = arena` hoặc cast |
| `int x = (int) add.invokeExact(...)` | Return handle là `MemorySegment`, không phải `int` | Cast `(MemorySegment)` rồi đọc field |
| `sum.invokeExact(allocator,pair)` | Hàm trả scalar, không có allocator prefix | `int n = (int) sum.invokeExact(pair)` |
| `shift.invokeExact(allocator,pair,1,2)` | Hàm trả void nhận pointer, không group return | `shift.invokeExact(pair,1,2)` |
| `make.invokeExact(allocator,7L,8L)` | C `int` mapped to Java `int`, không phải `long` | Truyền `7,8` kiểu `int` |
| Dùng `FunctionDescriptor.of(ADDRESS, PAIR, PAIR)` cho C `Pair` return | Trộn return pointer và by-value | Dùng `FunctionDescriptor.of(PAIR, PAIR, PAIR)` |
| Dùng `FunctionDescriptor.ofVoid(PAIR, PAIR)` khi C return `Pair` | Sai return ABI | Dùng `of(PAIR, PAIR, PAIR)` hoặc signature thật |

Gợi ý debug an toàn, trong chương trình thật:

~~~java
System.out.println(add.type());
System.out.println(sum.type());
System.out.println(shift.type());
~~~

Đây là **trích đoạn**, cần có ba handles đã liên kết hợp lệ. So sánh `handle.type()` với `MethodType.methodType(...)` trước khi gọi, như cách code đầy đủ đã thực hiện.

Nếu không chắc C signature, hãy đối chiếu **C header thật**, không đoán theo số tham số Java hiện ra. Tham số `SegmentAllocator` và địa chỉ hàm cho unbound handle là *virtual parameters* của FFM chứ không phải danh sách C parameters.

## 13. Các lỗi thường gặp ở runtime

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `WrongMethodTypeException` | Thiếu allocator; cast `Arena` không đúng; return carrier sai; nhầm bound/unbound | In `handle.type()`, đối chiếu từng kiểu và thứ tự |
| `IllegalArgumentException` khi tạo downcall | Struct layout/ABI không được linker hỗ trợ, descriptor sai hoặc symbol không phải native address | Kiểm tra `Linker`, layout, native symbol và ABI |
| `NoSuchElementException` từ `find(...).orElseThrow()` | Tên C symbol không export hoặc thư viện khác phiên bản | Kiểm tra `nm`/`dumpbin` và file library đã load |
| Lỗi load library | Sai path, OS/architecture, dependency native | Build đúng nền tảng và dùng absolute path |
| `IllegalCallerException` / warning restricted native access | Module chưa có quyền native | Dùng `--enable-native-access=ALL-UNNAMED` cho classpath hoặc module phù hợp |
| `IllegalStateException` khi đọc result | Arena allocator đã đóng | Đọc/copy result khi arena còn sống |
| `WrongThreadException` | Segment confined được dùng từ thread không sở hữu | Dùng owner thread hoặc shared arena với quản lý đồng bộ |
| Kết quả fields lộn xộn | StructLayout sai padding, offset, type hoặc alignment | Đối chiếu `sizeof`/`offsetof`/`_Alignof` |
| JVM crash hoặc memory corruption | Sai C ABI signature, truyền ADDRESS thay group hoặc con trỏ invalid | So sánh native header và descriptor; không tiếp tục thử bằng dữ liệu thật |
| Result trước bị ghi đè bởi result sau | Custom allocator trả overlapping memory | Dùng Arena riêng hoặc allocator có đảm bảo non-overlap |
| Native memory tăng dần | Dùng global allocator cho mọi call, quên đóng bounded arenas | Áp dụng try-with-resources và ngân sách bộ nhớ |
| Sai cách cast return | Nhầm `MemorySegment` với `int`/Java POJO | Nhận `MemorySegment`, đọc qua layout/VarHandle |
| C compiler báo `_Static_assert` failure | Nền tảng không thỏa assumption của ví dụ | Điều chỉnh layout và ABI sau khi hiểu compiler target, không xóa assertion |

**Một native call sai ABI không có nghĩa sẽ ném Java exception dễ hiểu.** Nó có thể làm JVM crash trước khi Java có cơ hội xử lý. Dùng kiểm tra layout/handle types và chạy integration tests trên đúng OS/CPU/compiler của deployment.

### 13.1. Kiểm thử tự động nên gồm gì?

Ít nhất kiểm thử:

1. `pair_size`, `pair_offset_y` và `_Alignof` từ native side khớp Java layout.
2. `add.type()` có đúng một `SegmentAllocator` prefix khi result là `StructLayout`.
3. `sum.type()` **không** có allocator prefix dù nhận struct.
4. Dữ liệu đầu vào và kết quả đúng trên cả trường hợp số dương, âm và 0 trong phạm vi không tràn C int.
5. `pair_tweak_copy` không làm thay đổi struct ở caller; `pair_shift` có thay đổi khi truyền `Pair*`.
6. Results không bị dùng sau khi arena đóng; nếu cần trả kết quả lên tầng Java, copy fields thành Java record/primitives trước khi close.
7. Chạy trên nền tảng mục tiêu, gồm CI Linux/macOS/Windows nếu sản phẩm hỗ trợ, không chỉ một compiler.
8. Khi hỗ trợ packed/union/complex structs, test offsets, sizes, alignment và ABI classification của chính các kiểu đó.

## 14. Thiết kế API thực tế: khi nào nên trả struct by-value?

By-value thường phù hợp với struct nhỏ, ổn định và có ABI rõ ràng, ví dụ tọa độ, vector 2D, màu, timestamp C hoặc các record nhỏ. Ưu điểm: semantics của C rõ ràng, không bắt caller quản lý pointer tới memory do callee tự cấp phát, và Java có thể nhận giá trị bằng `SegmentAllocator`.

Tuy nhiên:

- Struct lớn có thể tốn chi phí copy hoặc bị ABI đưa vào hidden result buffer.
- Một số ABI phức tạp không được mọi FFM linker hỗ trợ.
- Struct có con trỏ bên trong vẫn mang **vấn đề ownership riêng**. Bản thân struct by-value có thể được copy, nhưng các con trỏ fields bên trong **không được deep-copy**; không suy ra toàn bộ object graph an toàn.
- Struct chứa union/bitfields/packing đặc biệt có thể khó mô tả portable.
- Nếu cần thay đổi trực tiếp một struct lớn tại nơi caller đã allocate, đôi khi một C API nhận `Pair*`/`void*` rõ ràng sẽ thích hợp hơn — **miễn C prototype được thiết kế như vậy từ đầu**.

Sự lựa chọn by-value hay by-pointer nên dựa trên **contract của native library**. FFM không cho phép tự hoán đổi chỉ vì trên Java cả hai trường hợp đều sử dụng carrier `MemorySegment`.

### 14.1. Struct return chứa pointer: trả by-value vẫn không giải quyết ownership

Ví dụ C:

~~~c
typedef struct {
    const char *data;
    size_t length;
} BufferView;
~~~

Đây là **trích đoạn**, không phải thư viện runnable. Ngay cả khi `BufferView` được C trả theo giá trị và Java nhận segment bằng `SegmentAllocator`, thành phần `data` bên trong vẫn là **native pointer**.

- Java phải biết `data` có thật sự trỏ tới `length` byte hợp lệ hay không.
- Owner có thể là C library, caller, một file mapping hoặc một handle.
- `SegmentAllocator` chỉ cấp storage cho **bản sao struct metadata** (pointer + length), không tự sao chép toàn bộ các byte được `data` trỏ tới.
- Close allocator giải phóng storage của **struct result**, không tự gọi deallocator cho pointer fields của C.

Đây là lỗi kiến trúc thường gặp khi nâng một API có pointer ownership phức tạp lên FFM. Nếu cần chuỗi/array độc lập, copy dữ liệu vào vùng do Java sở hữu hoặc tạo contract rõ cho native lifetime.

## 15. SegmentAllocator, Arena, JNI và các phiên bản JDK

FFM final được phát hành trong **JDK 22** theo **JEP 454**. JDK 21 có **FFM third preview (JEP 442)**; nếu cần chạy source preview của JDK 21, phải có cờ preview và kiểm tra chữ ký API theo JDK21. Đừng dùng một source FFM final 22 rồi chỉ thay `--release 21` và mong biên dịch được.

Với các file trong bài, chạy JDK22:

~~~bash
javac --release 22 StructByValueDemo.java
java --enable-native-access=ALL-UNNAMED StructByValueDemo
~~~

**`--enable-native-access` không phải `--enable-preview`.** FFM ở 22 không cần preview, nhưng tạo downcall handle và library lookup là restricted operations. Chính sách warning/deny có thể thay đổi ở các JDK mới hơn; thực thi production nên cấp quyền theo module và tài liệu chính thức của runtime.

Trong **JNI**, người viết có thể truyền `jobject` hoặc thao tác fields qua `JNIEnv`, nhưng khi trao đổi trực tiếp với C struct by-value cần viết wrapper C phù hợp. FFM tạo downcall handles từ C signatures và `MemoryLayout`, nên giảm JNI glue cho nhiều thao tác C ABI. Nó **không biến C ABI thành self-describing**: bạn vẫn phải kiểm chứng chính xác bố cục struct, ownership và calling convention.

## 16. Tự luyện tập

1. Với `Pair pair_add(Pair, Pair)`, `FunctionDescriptor` phù hợp là gì? Vì sao không dùng `ADDRESS` cho hai arguments?
2. Với `int pair_sum(Pair)`, vì sao bound `MethodHandle` **không có `SegmentAllocator`**?
3. `SegmentAllocator` xuất hiện ở vị trí nào trong bound handle trả về `Pair`? Nó có nằm trong C prototype không?
4. Khi dùng `invokeExact`, vì sao truyền biến có static type `Arena` có thể gây `WrongMethodTypeException` dù `Arena implements SegmentAllocator`?
5. Nếu thay `Pair pair_make(int,int)` thành `Pair* pair_make(int,int)` ở C, descriptor và Java ownership phải thay đổi thế nào?
6. `MemoryLayout.structLayout(...)` có tự chèn 7 byte padding sau `char` trước `double` trên mọi ABI không?
7. Vì sao `sizeof(struct)` bằng nhau chưa đủ để khẳng định bố cục các fields đúng?
8. Một struct trả by-value chứa `char* data`: close `Arena` dùng cho return có tự `free(data)` không?
9. Có nên truyền `Arena.global()` làm return allocator cho một API gọi hàng nghìn lần mỗi giây không? Vì sao?
10. Sự khác nhau giữa `Pair change_copy(Pair)` và `void change_pointer(Pair*)` là gì?
11. Nếu handle tạo bằng `linker.downcallHandle(descriptor)` thay vì `linker.downcallHandle(symbol, descriptor)`, có thêm tham số nào lúc invoke?
12. Khi C compiler đặt struct return vào registers hay hidden pointer, ai chịu trách nhiệm thực hiện chuyển đổi ABI?
13. Tại sao không được giữ `MemorySegment result` từ confined arena rồi đọc sau khi arena đóng?
14. Nếu native linker từ chối một packed struct, cách xử lý đúng hơn “đổi mọi group layout thành ADDRESS” là gì?
15. Vì sao kiểm tra `MethodHandle.type()` và các hàm native `sizeof`/`offsetof` là hai lớp kiểm tra khác nhau và đều cần thiết?
16. Hãy mở rộng ví dụ `Pair` với hàm `Pair pair_sub(Pair,Pair)`: cần thay đổi C file, `FunctionDescriptor`, `MethodHandle` và lệnh `invokeExact` như thế nào?

**Kết luận:** Khi C function **nhận struct theo giá trị**, dùng một **`StructLayout` hợp ABI** ở vị trí argument của `FunctionDescriptor` và truyền `MemorySegment` trong Java. Khi C function **trả struct theo giá trị**, downcall handle có thêm **`SegmentAllocator`** ở phía Java để cấp vùng lưu kết quả; C prototype **không** có đối số này. Trái lại, C `Pair*` dùng **`ValueLayout.ADDRESS`** và có pointer/ownership semantics riêng. Luôn kiểm tra `sizeof`, offset, alignment, `MethodHandle.type()` và vòng đời arena trước khi tin rằng chương trình interop đúng.

### Tài liệu chính thức

- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): C ABI, group/struct layout support, downcall handle type và tham số `SegmentAllocator` bổ sung cho group return.
- [Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): contract cấp phát và vai trò làm return allocator.
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `structLayout`, padding, alignment, `byteSize`, `byteOffset` và VarHandle access.
- [Java SE 22 — StructLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html): group layouts xếp member theo thứ tự.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): bounded scope, lifetime và cleanup cho FFM allocations.
- [Java SE 22 — Foreign Function & Memory API Developer Guide](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): memory layout và native downcalls.
- [JEP 454 — FFM Final](https://openjdk.org/jeps/454): bản finalized ở JDK22.
- [JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442): tình trạng preview trong JDK21.
