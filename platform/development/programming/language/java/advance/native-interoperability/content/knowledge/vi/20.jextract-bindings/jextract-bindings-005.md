# Đọc mã jextract sinh ra cho hàm, hằng số, cấu trúc và con trỏ hàm

## Mục tiêu bài học

`jextract` là công cụ trong dự án OpenJDK Code Tools: nó đọc **header C** (`.h`) bằng công cụ phân tích C và **sinh Java bindings** dựa trên Foreign Function & Memory API (FFM). Mục tiêu không chỉ là thay thao tác viết `Linker.downcallHandle` hoặc `Linker.upcallStub` thủ công, mà còn giúp Java code sử dụng các khai báo C với API có cấu trúc: **hàm**, **macro/enum constants**, **struct/union**, **global variables**, **typedefs** và **function pointers/callbacks**.

Khi đọc một tập Java source do jextract sinh, người học cần trả lời:

1. Khai báo nào ở header C sinh ra **file/class Java nào**?
2. Phương thức nào là **wrapper để gọi**, phương thức nào chỉ cho biết **địa chỉ, `FunctionDescriptor` hoặc `MemoryLayout`**?
3. `C int`, `long`, `size_t`, pointer, `struct` và function pointer được thể hiện bằng kiểu nào trong Java?
4. Ai sở hữu native memory, callback stub, native library, và bao giờ được giải phóng?
5. Khi một symbol hoặc method không xuất hiện, đó là lỗi code sinh, preprocessor/filter, unsupported macro, ABI mismatch hay khác phiên bản jextract?

Bài này học cách **đọc và sử dụng source đã sinh**, không coi code được sinh là implementation nghiệp vụ cần viết lại. Một header C và bộ ví dụ xuyên suốt giúp nối các khái niệm với nhau.

**Điều kiện phiên bản:** FFM trong package `java.lang.foreign` trở thành API chuẩn ở **JDK 22** (JEP 454). `jextract` là công cụ **phát hành riêng**, không mặc nhiên nằm trong thư mục `bin` của mọi JDK. Chọn bản jextract tương thích JDK và nền tảng đang chạy; các tên helper ở đây theo **OpenJDK jextract Guide** hiện hành, nhưng **API sinh có thể thay đổi giữa phiên bản, C headers và nền tảng**. Luôn kiểm tra source thật trong thư mục output của chính bạn.

## 1. Từ C header sang cây Java source: bản đồ tổng quan

Giả sử thư viện native có header `demo.h`:

~~~c
#ifndef DEMO_H
#define DEMO_H

#define DEMO_LIMIT 64
#define DEMO_FLAG_A 1
#define DEMO_FLAG_B 2

enum demo_state { DEMO_OFF = 0, DEMO_ON = 1 };

struct Point {
    int x;
    int y;
};

typedef int (*binary_fn)(int a, int b);

int add_values(int a, int b);
int sum_point(const struct Point *p);
int call_callback(binary_fn fn, int a, int b);
binary_fn native_callback(void);

#endif
~~~

Đây là **header minh họa hoàn chỉnh**, không phải một native library đã có sẵn. Nó đưa vào các dạng C khác nhau:

| C declaration | Bản chất | Java bindings thường nằm ở đâu? |
| --- | --- | --- |
| `#define DEMO_LIMIT 64` | Numeric macro constant | Hàm accessor `DEMO_LIMIT()` trong header class |
| `enum demo_state { ... }` | Enum constants C | `DEMO_OFF()`/`DEMO_ON()` trong header class, không nhất thiết là Java `enum` |
| `struct Point { int x; int y; }` | Struct layout và fields | Class `Point` với `layout`, `sizeof`, getter/setter |
| `typedef int (*binary_fn)(int,int)` | Kiểu function pointer C | Class `binary_fn` với `Function`, `allocate`, `invoke` |
| `int add_values(int,int)` | Native function | Static wrapper `add_values(...)` và metadata `$address/$descriptor/$handle` |
| `int sum_point(const struct Point *)` | Function nhận pointer-to-struct | Static wrapper dùng `MemorySegment` cho argument |
| `binary_fn native_callback(void)` | Function trả function pointer | Wrapper trả `MemorySegment`, dùng `binary_fn.invoke` nếu cần gọi |
| `int call_callback(binary_fn,...)` | Function nhận callback | Wrapper nhận `MemorySegment` upcall stub do Java tạo |

Lệnh jextract theo OpenJDK Guide (nội dung mang tính **quy trình có thể thực hiện khi đã cài công cụ**):

~~~bash
jextract \
  --output gensrc \
  --target-package org.example.demo \
  --library demo_native \
  demo.h
~~~

Trên Windows, cách ngắt dòng của PowerShell/CMD khác shell POSIX; có thể dùng một dòng:

~~~text
jextract --output gensrc --target-package org.example.demo --library demo_native demo.h
~~~

Các thành phần:

- `demo.h`: input header C mà clang sẽ parse; bản thân header **không tạo ra file .so/.dll**.
- `--output gensrc`: thư mục gốc lưu Java code được sinh.
- `--target-package org.example.demo`: namespace Java cho các class.
- `--library demo_native`: yêu cầu bindings gắn với native library được tìm theo tên platform; file thực tế như `libdemo_native.so` trên Linux hoặc `demo_native.dll` trên Windows **phải có khi chạy**, trừ khi bạn dùng cách quản lý library khác.
- Với thư viện nhiều header hoặc `#include` phức tạp, thêm `--include-dir` (`-I`) và các macro defines cần thiết để clang hiểu headers giống compiler của native library.
- Có thể dùng `--header-class-name` để chọn tên class tổng hợp; nếu không, thường lấy từ tên header, ví dụ `demo.h` thành `demo_h`.

Ví dụ bố cục **minh họa** của source output (không phải listing đã chạy jextract trên máy này):

~~~text
gensrc/
└── org/
    └── example/
        └── demo/
            ├── demo_h.java
            ├── Point.java
            ├── binary_fn.java
            └── ...  (các helper/internal files tùy phiên bản)
~~~

**Không đoán tên file từ ví dụ rồi giữ cứng trong production:** với typedef, anonymous struct/union, nested struct, cách xử lý tên trùng, generated helper name hoặc phiên bản mới, các tên có thể khác. Hãy đọc file thực sinh, kiểm package/imports/signature rồi mới viết client.

## 2. Cách đọc header class: `demo_h.java`

Theo OpenJDK jextract Guide, phần lớn bindings có các **static methods** trong một *header class* (ví dụ `demo_h`). Đó là chỗ tìm đầu tiên khi cần gọi C function hoặc đọc macro/enum constants.

Ví dụ import:

~~~java
import static org.example.demo.demo_h.*;
import org.example.demo.Point;
import org.example.demo.binary_fn;
~~~

`import static` đưa những accessor/wrapper static của header class vào phạm vi Java; import các generated classes giúp truy cập struct và callback helpers. Không nhất thiết phải dùng wildcard imports; trong sản phẩm lớn, explicit imports dễ kiểm soát xung đột tên.

Cần phân biệt **file Java sinh ra** với **native library implementation**:

~~~text
demo.h                       demo.c / native library
   |                               |
   | jextract parses               | cc builds
   v                               v
demo_h.java, Point.java,     libdemo_native.so / .dll / .dylib
binary_fn.java, ...
   |                               |
   +-------- Java application -----+
              ↓ FFM linker/lookup
           native symbols
~~~

Jextract chỉ parse header và sinh Java bindings; nó **không tự cài đặt native function**, không bảo đảm OS loader tìm được thư viện, không xác nhận C source/library đang dùng thực sự phù hợp header. Để chạy, bạn cần **đúng native binary** với exported symbols và ABI phù hợp.

### Đọc ba lớp của một binding

Khi thấy một tên C như `foo`, tìm theo thứ tự:

1. **Public wrapper** `foo(...)`: điểm vào tiện dụng cho Java caller.
2. **Metadata** `foo$descriptor()`, `foo$address()`, `foo$handle()`: cho biết type ABI, symbol address và method handle.
3. **Implementation/wiring nội bộ**: symbol lookup, `Linker`, library loading, chuyển đổi arguments.

Lớp 2 rất hữu ích cho debug signature; lớp 3 thường là code máy sinh, không nên sửa tay để “fix ABI” khi vấn đề thực chất là header/build configuration.

## 3. Đọc bindings của C function

Với header:

~~~c
void foo(int x);
~~~

OpenJDK Guide trình bày API Java sinh **tương đương**:

~~~java
// Trích hình dạng từ tài liệu, không phải tệp có thân method.
public static void foo(int x) { /* generated downcall */ }

public static MemorySegment foo$address() { /* address */ }
public static FunctionDescriptor foo$descriptor() { /* ABI */ }
public static MethodHandle foo$handle() { /* downcall handle */ }
~~~

Bốn phần phục vụ mục tiêu khác nhau:

| Thành phần | Câu hỏi được trả lời | Cách dùng |
| --- | --- | --- |
| `foo(int)` | “Làm sao gọi trực tiếp hàm C?” | `foo(5)` |
| `foo$address()` | “Địa chỉ symbol native là gì?” | Kiểm symbol lookup/lifetime; không dereference như data |
| `foo$descriptor()` | “Kiểu return/arguments theo FFM là gì?” | Phân tích `FunctionDescriptor` khi debug ABI |
| `foo$handle()` | “MethodHandle FFM thật nằm ở đâu?” | Chỉ dùng nếu cần thao tác MethodHandle nâng cao; wrapper thường đủ |

`$address` không phải địa chỉ object Java; nó là pointer tới native symbol. `$descriptor` được suy từ header C mà tool đã parse, **không** phải một phép kiểm tra độc lập đối với binary đang load. Nếu header và thư viện lệch phiên bản, generated descriptor vẫn có thể “trông đúng” nhưng native call vẫn hỏng.

### C function có pointer argument

Header:

~~~c
int sum_point(const struct Point *p);
~~~

Wrapper thường có dạng:

~~~java
// Hình dạng minh họa; lấy chữ ký chuẩn từ source được sinh.
public static int sum_point(MemorySegment p) {
    /* generated FFM downcall */
}
~~~

`MemorySegment` biểu diễn **pointer của C**, không tự biến thành Java `Point` object ở heap. Khi gọi, bạn phải truyền một segment mà native library được phép đọc; ở ví dụ, dùng `Point.allocate(arena)` và giữ arena sống suốt lời gọi.

**Không** tưởng `const struct Point *` là Java immutable type: `const` là hợp đồng C, còn khả năng sửa từ aliases và cách generated source thể hiện read-only có thể khác. Caller không được mutate dữ liệu khi C contract cấm, dù Java compiler không ngăn.

### Return types và carrier

Layout của C arguments/return được chuyển thành FFM carrier:

| C | Java carrier điển hình | Kiểm tra thêm |
| --- | --- | --- |
| `int` | `int` | `C_INT`/ABI: C int phải phù hợp kích thước Java int ở platform |
| `long` | `int` hoặc `long` tùy ABI | Windows 64-bit có C long thường 32-bit; không đoán |
| `long long` | `long` trên ABI thông dụng | Kiểm layout generated |
| `float` / `double` | `float` / `double` | Phụ thuộc C ABI/calling convention |
| `void *` / `T *` | `MemorySegment` | Địa chỉ, bounds, null, ownership và lifetime |
| `void` | Java `void` | Không có return value |
| `struct` by value | Có thể cần `MemorySegment`/allocator tùy FFM ABI | Đọc chữ ký cụ thể được sinh; không giả định scalar |

Nếu một generated method nhận `MemorySegment` ở đầu vì một **struct return by value**, có thể có **`SegmentAllocator`** làm tham số được FFM chèn theo convention. Điều đó khác với hàm C nhận pointer; phải đọc **generated method signature và descriptor**, không suy từ tên.

### Khi nào dùng `$handle`?

`$handle` hữu ích khi bạn cần áp dụng MethodHandle combinators, caching hoặc call site tối ưu hóa. Tuy nhiên `invokeExact` yêu cầu **kiểu Java chính xác tại call site**, nên một sai biệt `int` vs `long`, `MemorySegment` vs `Object` có thể gây `WrongMethodTypeException`. Với ứng dụng thông thường, ưu tiên **generated wrapper** vì đã thể hiện signature và chuyển đổi kiểu theo đúng logic generator.

## 4. Đọc constants: macros và C enums

Đây là nơi dễ nhầm với Java `static final` hoặc Java `enum`.

Ví dụ header:

~~~c
#define DEMO_LIMIT 64
#define DEMO_FLAG_A 1
#define DEMO_FLAG_B 2

enum demo_state { DEMO_OFF = 0, DEMO_ON = 1 };
~~~

Theo jextract Guide, numeric macro/enum constants thường trở thành **static accessor methods** trong header class:

~~~java
// Phác họa API được sinh, không phải source hoàn chỉnh.
public static int DEMO_LIMIT() { /* returns 64 */ }
public static int DEMO_FLAG_A() { /* returns 1 */ }
public static int DEMO_FLAG_B() { /* returns 2 */ }

public static int DEMO_OFF() { /* returns 0 */ }
public static int DEMO_ON() { /* returns 1 */ }
~~~

Client:

~~~java
int limit = DEMO_LIMIT();
int flags = DEMO_FLAG_A() | DEMO_FLAG_B();
int state = DEMO_ON();
~~~

Đây là snippet, giả sử đã `import static org.example.demo.demo_h.*;` và generator sinh các tên đó. Giá trị tương ứng là `64`, `3`, `1`.

**C enums không nhất thiết trở thành Java `enum`**: các enum constants được đưa vào vùng tên trên cùng của C. Một giá trị enum bit mask có thể cần phép `|`, `&`; Java `enum` tự thân không tương đương số nguyên C.

### Macros nào không sinh được accessor?

Một số macro C không thể chuyển thành Java constant đơn giản:

~~~c
#define DEMO_LIMIT 64                /* constant-like: có thể sinh */
#define DEMO_VERSION "1.0"           /* string literal: có thể sinh */
#define DOUBLE_IT(x) ((x) * 2)       /* function-like: KHÔNG hỗ trợ trực tiếp */
~~~

OpenJDK Guide nêu jextract hỗ trợ macro có giá trị **primitive numeric, string, hoặc pointer**, nhưng **không hỗ trợ function-like macros**. Nếu không tìm thấy `DOUBLE_IT()` trong Java source, đó **không nhất thiết là bug**.

Macro dùng conditional compilation cũng phụ thuộc headers/defines và target platform:

~~~c
#ifdef _WIN32
#define PLATFORM_CODE 1
#else
#define PLATFORM_CODE 2
#endif
~~~

Giá trị được jextract nhìn thấy là kết quả **preprocessing trong môi trường chạy tool**. Không reuse bindings sinh từ headers/platform A trên platform B mà không so ABI và giá trị constants.

**Chú ý `-D`:** macro được định nghĩa chỉ bằng option dòng lệnh `-DNAME=VALUE` có thể dùng để điều khiển preprocessing nhưng theo guide sẽ **không** được tự sinh accessor như một macro có khai báo trong header.

## 5. Struct: cách hiểu `Point.java`, `layout` và các field helpers

Header C:

~~~c
struct Point {
    int x;
    int y;
};
~~~

Jextract thường sinh **một class riêng** cho `Point`. Theo Guide, hình dạng API gần như:

~~~java
// MINH HỌA GENERATED API; bodies phụ thuộc phiên bản.
public class Point {
    public static GroupLayout layout() { /* ... */ }
    public static long sizeof() { /* ... */ }

    public static ValueLayout.OfInt x$layout() { /* ... */ }
    public static long x$offset() { /* ... */ }
    public static int x(MemorySegment struct) { /* ... */ }
    public static void x(MemorySegment struct, int value) { /* ... */ }

    public static ValueLayout.OfInt y$layout() { /* ... */ }
    public static long y$offset() { /* ... */ }
    public static int y(MemorySegment struct) { /* ... */ }
    public static void y(MemorySegment struct, int value) { /* ... */ }

    public static MemorySegment allocate(SegmentAllocator a) { /* ... */ }
    public static MemorySegment allocateArray(long count, SegmentAllocator a)
            { /* ... */ }
    public static MemorySegment asSlice(MemorySegment array, long index)
            { /* ... */ }
}
~~~

**Các chữ ký ở đây chỉ minh họa; không copy nguyên khối này để biên dịch:** đây không phải source được sinh đầy đủ. Hàm thật có thể có overloads/những helper khác. Điều đáng học là **trách nhiệm của từng tên method**:

| Generated method | Ý nghĩa | Điểm review |
| --- | --- | --- |
| `Point.layout()` | `GroupLayout` mô tả tổng thể fields/padding/alignment | So với C header/ABI |
| `Point.sizeof()` | Kích thước `sizeof(struct Point)` theo generator | Không thay bằng tự cộng sizes nếu có padding |
| `Point.x$layout()` | Memory layout của field `x` | C int có layout gì trên platform? |
| `Point.x$offset()` | Byte offset của field trong struct | Offset **byte**, không phải index |
| `Point.x(point)` | Đọc field x từ native segment | Yêu cầu segment hợp lệ và đủ bounds |
| `Point.x(point, 3)` | Ghi field x | Segment writable, còn sống |
| `Point.allocate(arena)` | Cấp một struct | Lifetime gắn `Arena` |
| `Point.allocateArray(n, arena)` | Cấp n structs liên tiếp | Kiểm `n`, size, tránh overflow |
| `Point.asSlice(array,i)` | View của phần tử thứ i | Không cấp phát/copy thêm, vẫn lifetime parent |

Một client đúng thường như sau:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment p = Point.allocate(arena);
    Point.x(p, 3);
    Point.y(p, 4);

    int x = Point.x(p);
    int y = Point.y(p);
    System.out.println(x + y); // 7
}
~~~

Đây là snippet sử dụng **giả định đã chạy jextract và import `Point`**. Nó chỉ thao tác memory do arena cấp; không cần gọi C function để thấy getter/setter sinh hoạt động.

### Padding và alignment không thể bỏ qua

Với:

~~~c
struct Packet {
    char kind;
    int count;
    void *payload;
};
~~~

Giữa fields có thể có **padding** do ABI. Nếu tự ghép Java `MemoryLayout.structLayout(JAVA_BYTE, JAVA_INT, ADDRESS)` mà không thêm padding và xác minh alignment, có thể mô tả sai. Generated `Packet.layout()` có thể chứa padding và ABI-specific member layouts, nên `Packet.count$offset()` là nguồn để kiểm.

Không lấy `sizeof` trên một hệ điều hành rồi hardcode vào JVM trên hệ khác. C `long` đặc biệt khác giữa Windows x64 và nhiều Unix x64 ABIs; trình biên dịch native có thể dùng tùy chọn packing ảnh hưởng offsets.

### Struct arrays và slices

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment points = Point.allocateArray(3, arena);

    for (long i = 0; i < 3; i++) {
        MemorySegment element = Point.asSlice(points, i);
        Point.x(element, (int) (i + 1));
        Point.y(element, 10);
    }

    int secondX = Point.x(Point.asSlice(points, 1)); // 2
}
~~~

Đây là snippet dựa vào generated `Point`. `asSlice(points,i)` là view một struct ở **index i**, không nhầm với byte offset. Slice vẫn phụ thuộc lifetime của arena. Nếu native code giữ pointer tới phần tử, arena phải tiếp tục sống tới khi native code không dùng pointer nữa.

### Union

Một `union` C cho phép nhiều fields **chồng lên cùng vùng nhớ**, khác với `struct` ghép fields nối tiếp. Jextract Guide mô tả helper class cho union **có hình dạng tương tự struct** (`layout`, field accessors, allocation), nhưng semantic aliasing khác nhau. Ghi field union A có thể thay đổi bit của field B; ứng dụng phải biết field nào đang active theo giao thức C.

## 6. Function pointers: vì sao jextract sinh class riêng?

C khai báo:

~~~c
typedef int (*binary_fn)(int a, int b);
~~~

`binary_fn` không phải một int scalar và cũng không phải con trỏ tới một struct; nó là **kiểu con trỏ hàm** có chữ ký `int(int,int)` theo ABI C.

Theo OpenJDK Guide, một class được sinh cho function pointer type, với hình dạng **tương đương**:

~~~java
// MINH HỌA GENERATED SHAPE; không phải tệp chạy độc lập.
public class binary_fn {
    public interface Function {
        int apply(int a, int b);
    }

    public static FunctionDescriptor descriptor() { /* ... */ }

    public static MemorySegment allocate(Function impl, Arena arena)
            { /* ... upcall stub ... */ }

    public static int invoke(MemorySegment functionPointer, int a, int b)
            { /* ... downcall ... */ }
}
~~~

**Hai hướng dễ bị nhầm**:

- `binary_fn.allocate((a,b) -> a + b, arena)`: biến **Java lambda** thành một **native function pointer** mà C có thể gọi — **upcall**.
- `binary_fn.invoke(nativeFunctionPointer, 3, 4)`: Java gọi một **function pointer nhận từ C** — **downcall** tới pointer đó.

| API generated | Input | Ai gọi ai? | Ownership |
| --- | --- | --- | --- |
| `binary_fn.descriptor()` | Không có | Chỉ đọc ABI metadata | Không cấp callback |
| `binary_fn.allocate(impl,arena)` | Functional interface Java + arena | C gọi vào Java callback stub | Stub hợp lệ tới lúc arena đóng |
| `binary_fn.invoke(ptr,a,b)` | Native function pointer + arguments | Java gọi C function pointer | Pointer phải còn hợp lệ theo C library |
| `call_callback(ptr,a,b)` | Callback pointer từ `allocate` | Java gọi C, rồi C gọi Java | Phải giữ stub sống suốt thời gian C gọi |

### Vòng đời callback thật sự quan trọng

Với một C API gọi callback **đồng bộ** rồi trả ngay, bạn có thể tạo stub trong `try (Arena arena = Arena.ofConfined())` và giải phóng khi native call hoàn tất. Nhưng nếu C lưu pointer cho sự kiện **bất đồng bộ**, không được đóng arena sau đăng ký; phải có unregister/acknowledge hoàn thành callbacks in flight rồi mới đóng arena.

Một **upcall Java không được ném Java exception vượt qua native boundary**. Theo FFM Linker contract, ném exception qua upcall có thể khiến JVM kết thúc đột ngột. Bắt lỗi **bên trong callback**, trả mã C phù hợp nếu native protocol cho phép, truyền lỗi tới Java owner qua kênh riêng.

`binary_fn.invoke` cũng không tự validate native pointer là code hợp lệ; truyền địa chỉ NULL/dangling hoặc sai ABI có thể crash. Không gọi function pointer đã bị library unload hoặc callback stub đã bị free.

### Typedef function pointers xuất hiện ở nhiều nơi

Các trường hợp C điển hình:

~~~c
void register_callback(void (*cb)(void)); // parameter
void (*get_callback(void))(void);         // return type
typedef int (*binary_fn)(int, int);      // typedef
struct Holder {
    binary_fn on_event;                 // field trong struct
};
~~~

Jextract có thể sinh type/helper riêng để diễn tả function pointer này. Khi field có kiểu function pointer, getter của struct có thể trả `MemorySegment` (giá trị địa chỉ). Đừng cố đọc field function pointer bằng `JAVA_INT` hoặc xem đó là Java `Runnable`. Để gọi, dùng helper `invoke` đúng signature; để cài Java callback, dùng helper `allocate` với arena hợp lệ.

## 7. Ví dụ xuyên suốt: cùng một header, nhiều kiểu generated bindings

Tạo hai tệp dưới đây trong một **thư mục ví dụ riêng**. Bài trình bày chúng để người học có thể tự thực hành trên máy đã cài native compiler và jextract tương thích. Mã C và Java bên dưới là **một demo đầu-cuối**; phần generated API được dự đoán theo OpenJDK Guide và **phải kiểm lại tên/chữ ký trên output thực** trước khi chạy trên bản tool khác.

### 7.1. Native header: `demo.h`

~~~c
#ifndef DEMO_H
#define DEMO_H

#define DEMO_LIMIT 64
#define DEMO_FLAG_A 1
#define DEMO_FLAG_B 2

enum demo_state {
    DEMO_OFF = 0,
    DEMO_ON = 1
};

struct Point {
    int x;
    int y;
};

typedef int (*binary_fn)(int a, int b);

int add_values(int a, int b);
int sum_point(const struct Point *p);
int call_callback(binary_fn fn, int a, int b);
binary_fn native_callback(void);

#endif
~~~

Các C declarations được giữ đơn giản: không có macro function-like, anonymous struct, varargs hoặc C++ name mangling. `int` được giả định 32-bit theo các ABI phổ biến mà FFM/jextract tương thích; khi port, kiểm ABI thật.

### 7.2. Native implementation: `demo.c`

~~~c
#include "demo.h"

static int multiply(int a, int b) {
    return a * b;
}

int add_values(int a, int b) {
    return a + b;
}

int sum_point(const struct Point *p) {
    if (p == 0) {
        return -1;
    }
    return p->x + p->y;
}

int call_callback(binary_fn fn, int a, int b) {
    if (fn == 0) {
        return -1;
    }
    return fn(a, b);
}

binary_fn native_callback(void) {
    return &multiply;
}
~~~

`multiply` ở đây là `static` C function: nó không cần là exported symbol vì `native_callback` trả **function pointer** tới nó; lifetime của code phụ thuộc native library còn được nạp. `add_values`, `sum_point`, `call_callback`, `native_callback` là các hàm công khai phù hợp header; build shared library phải export symbol theo compiler/linker đang dùng.

### 7.3. Build shared library và chạy jextract (Linux/POSIX)

Ví dụ cho Linux với compiler C hỗ trợ C11:

~~~bash
cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
   demo.c -o libdemo_native.so

jextract \
  --output gensrc \
  --target-package org.example.demo \
  --library demo_native \
  demo.h
~~~

`jextract` chạy lúc build để sinh **Java source**; `cc` biên dịch C để tạo **native executable code**. Hai thao tác độc lập. Trên macOS/Windows thay compiler flags, library extension và search path; không dùng chính xác lệnh Linux trên hệ khác.

### 7.4. Java client: `DemoMain.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

import static org.example.demo.demo_h.*;
import org.example.demo.Point;
import org.example.demo.binary_fn;

public final class DemoMain {
    public static void main(String[] args) {
        System.out.println("limit=" + DEMO_LIMIT());
        System.out.println("flags=" + (DEMO_FLAG_A() | DEMO_FLAG_B()));
        System.out.println("state=" + DEMO_ON());

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment point = Point.allocate(arena);
            Point.x(point, 3);
            Point.y(point, 4);

            System.out.println("add=" + add_values(2, 5));
            System.out.println("point-sum=" + sum_point(point));

            MemorySegment javaCallback = binary_fn.allocate(
                    (a, b) -> a + b,
                    arena);

            System.out.println("c-to-java="
                    + call_callback(javaCallback, 6, 7));

            MemorySegment cCallback = native_callback();
            System.out.println("java-to-c="
                    + binary_fn.invoke(cCallback, 3, 4));
        }
    }
}
~~~

Bốn nhóm binding đều được dùng rõ:

1. `DEMO_LIMIT()`, `DEMO_FLAG_A()`, `DEMO_FLAG_B()`, `DEMO_ON()`: macro và C enum constants.
2. `Point.allocate`, `Point.x`, `Point.y`: generated struct layout/field helpers.
3. `add_values`, `sum_point`, `call_callback`, `native_callback`: C function wrappers trong header class.
4. `binary_fn.allocate` và `binary_fn.invoke`: chiều Java → C callback pointer (upcall) và Java gọi con trỏ hàm C (downcall).

### 7.5. Compile/run client

Trên Linux/POSIX, nếu đang ở thư mục chứa `DemoMain.java`, `gensrc` và `libdemo_native.so`:

~~~bash
javac -encoding UTF-8 -d classes \
  $(find gensrc -name '*.java') \
  DemoMain.java

LD_LIBRARY_PATH=. java -cp classes \
  --enable-native-access=ALL-UNNAMED DemoMain
~~~

Trên Windows, thay cách compile/find và dynamic library search path. `--enable-native-access` cần thiết vì generated FFM bindings thường dùng restricted native operations (downcall/upcall/library loading). Nếu phần generated code thuộc named module, cấp native access cho module tương ứng chứ không chỉ unnamed module.

**Stdout dự kiến** trên một môi trường Linux phù hợp (header, C library, jextract và JDK đều cùng ABI và generated names khớp guide):

~~~text
limit=64
flags=3
state=1
add=7
point-sum=7
c-to-java=13
java-to-c=12
~~~

Đây là **kết quả được suy từ implementation C/Java đã cung cấp**, không phải một phát biểu rằng mọi phiên bản jextract đã được chạy trong mọi OS. Nếu tool sinh method names khác, dựa vào source thực để điều chỉnh import/call; nếu thư viện không load được, sửa native library path trước khi phân tích tính đúng của logic.

### Tại sao không in `Point.sizeof()` trong stdout này?

Kích thước của C struct do **ABI** quyết định. Với hai `int` 4 byte liền nhau, nhiều ABI cho size 8, nhưng bài học không dùng một size cố định làm yêu cầu cross-platform. Bạn có thể thêm một dòng:

~~~java
System.out.println(Point.sizeof());
System.out.println(Point.x$offset());
System.out.println(Point.y$offset());
~~~

Những giá trị này phải được so với `sizeof(struct Point)` và `offsetof` của **native compiler thật**, đặc biệt khi thư viện có packing flags hoặc struct chứa pointers/`long`/bit-fields.

## 8. Standalone Java lab: kiểm ý nghĩa layout và descriptor (không cần jextract)

Để phân biệt **quy tắc FFM thật** và **hình dạng API jextract sinh**, đây là một bài thực hành **Java 22+ độc lập**, không cần C compiler, shared library hay jextract. Nó tự mô phỏng hai thứ mà generated code thường đưa ra: `FunctionDescriptor` của một function nhận hai C ints và `GroupLayout` của struct có hai fields.

Tệp `BindingReadingLab.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.GroupLayout;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class BindingReadingLab {
    public static void main(String[] args) {
        FunctionDescriptor fn = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT);

        GroupLayout point = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("x"),
                ValueLayout.JAVA_INT.withName("y"));

        long x = point.byteOffset(
                MemoryLayout.PathElement.groupElement("x"));
        long y = point.byteOffset(
                MemoryLayout.PathElement.groupElement("y"));

        System.out.println("method-type=" + fn.toMethodType());
        System.out.println("point-size=" + point.byteSize());
        System.out.println("x-offset=" + x);
        System.out.println("y-offset=" + y);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment p = arena.allocate(point);
            p.set(ValueLayout.JAVA_INT, x, 3);
            p.set(ValueLayout.JAVA_INT, y, 4);

            int sum = p.get(ValueLayout.JAVA_INT, x)
                    + p.get(ValueLayout.JAVA_INT, y);
            System.out.println("point-sum=" + sum);
        }
    }
}
~~~

Chạy bằng JDK 22+ (FFM chuẩn, **không cần native access** cho đoạn này):

~~~bash
javac -encoding UTF-8 BindingReadingLab.java
java BindingReadingLab
~~~

**Stdout đã kiểm tra bằng JDK 24**, với `JAVA_INT` 4 byte:

~~~text
method-type=(int,int)int
point-size=8
x-offset=0
y-offset=4
point-sum=7
~~~

Đây **không phải** Java code do jextract sinh. Nó minh họa ý nghĩa thực tế của những metadata mà ta đọc trong `foo$descriptor()` và `Point.layout()/x$offset()/y$offset()`. Nếu native compiler dùng layout khác, generated source phù hợp ABI mới là chỗ cần review trước khi gọi C.

## 9. Global variables: phân biệt `bar()` với `bar$segment()`

Dù đề bài tập trung vào hàm/hằng số/struct/function pointers, cần nhận diện **global C variable** vì code sinh có naming tương tự hàm:

~~~c
int bar;
~~~

Theo Guide, header class thường có:

~~~java
// Hình dạng minh họa.
public static ValueLayout.OfInt bar$layout() { /* ... */ }
public static MemorySegment bar$segment() { /* ... */ }
public static int bar() { /* getter */ }
public static void bar(int value) { /* setter */ }
~~~

- `bar$layout()`: layout của biến global.
- `bar$segment()`: địa chỉ/vùng biểu diễn biến global.
- `bar()`: đọc nội dung hiện tại của C global.
- `bar(int)`: ghi nội dung global nếu native library cho phép.

**Khác với macro:** `bar()` không phải constant accessor; giá trị có thể thay đổi. C global có lifetime của native library/process và có thể cần synchronization khi nhiều threads truy cập. Đừng cache output getter rồi xem như một immutable macro constant.

Với C `extern const int` hoặc library chỉ cung cấp getter, không tự cho rằng mọi generated setter đều an toàn. Phải tôn trọng native declaration và library contract. Nếu global symbol không được export, binding có thể không tìm được khi runtime load/call; header khai báo không đồng nghĩa symbol được linker export.

## 10. Typedefs và những tên trông giống Java class

C:

~~~c
typedef int MyInt;

struct Point {
    int x;
    int y;
};
typedef struct Point MyPoint;
~~~

Theo Guide:

- **Primitive typedef** như `MyInt` thường thành một **layout constant** trong main header class.
- **Struct/union typedef** như `MyPoint` thường thành **separate Java class** liên quan tới struct class gốc.

Không đoán rằng `typedef int MyInt` tạo một Java primitive type hoặc class mới dùng ở method signature. Nó vẫn là C alias, và generated method có thể dùng Java `int` carrier với layout metadata tương ứng.

**Tự tra:** nếu `MyInt.java` không tồn tại, đừng vội coi binding thiếu; tìm `MyInt` trong main header class và xem declaration thực. Với `Point`/`MyPoint`, kiểm generated classes và static methods được kế thừa/forward để hiểu alias.

## 11. Đọc `MemorySegment` trong generated code không đồng nghĩa “con trỏ an toàn”

Mã sinh thường làm thao tác FFM đúng API, nhưng không thể tự suy mọi hợp đồng native library:

| Giá trị mang kiểu `MemorySegment` | Rủi ro | Bạn cần tự xác minh |
| --- | --- | --- |
| Pointer trả từ C function | Có thể `NULL`, size 0, dangling | Kiểm `address()==0L`, length, owner/free |
| Pointer-to-struct | Có thể không đủ bounds để đọc field | Dùng generated `reinterpret` khi có đúng lifetime/size contract |
| Pointer do `Point.allocate(arena)` trả | Hết hiệu lực khi arena đóng | Native code không giữ sau close |
| Function pointer trả từ native library | Code pointer có thể hết hiệu lực sau unload | Chỉ invoke khi library tồn tại và signature đúng |
| Callback pointer từ `binary_fn.allocate` | Stub có lifetime của arena | C không gọi sau close |
| C string pointer | Encoding/NUL terminator/length không rõ | Không tự đọc vượt buffer; hợp đồng API quyết định |
| C array pointer | Không có count tự động | Dùng explicit length, tránh index overflow |
| Global variable address | Dữ liệu mutable hoặc library bị unload | Đúng synchronization và lifetime |

### Generated `reinterpret`: công cụ mạnh, không phải validation

Ví dụ theo cấu trúc OpenJDK Guide:

~~~java
// Snippet minh họa với native API caller-owned:
// struct Point *new_point(void);
// void delete_point(struct Point *);
try (Arena arena = Arena.ofConfined()) {
    MemorySegment p = new_point();
    if (p.address() == 0L) {
        throw new IllegalStateException("native allocation failed");
    }

    MemorySegment sized =
            Point.reinterpret(p, arena, demo_h::delete_point);

    // Chỉ dùng sized trong lifetime của arena.
}
~~~

Ở đây `Point.reinterpret` là **generated helper** có thể gán `sizeof(Point)` bounds và cleanup function khi arena đóng. **Chỉ dùng nếu C API thực sự trả một caller-owned Point từ allocator mà `delete_point` được phép giải phóng.** Nếu C library sở hữu pointer, cleanup này sẽ gây double-free/invalid free. Nếu C trả array có nhiều phần tử, dùng overload element count và kiểm số lượng.

Nếu header không khai báo `new_point` hay `delete_point`, **snippet trên không chạy với header demo ở mục 7**: nó mô tả một *API khác* để giải thích helper được sinh. Không để người học nhầm đoạn này là lệnh chạy nguyên văn của DemoMain.

## 12. Tại sao có những chỗ không sinh ra Java method?

Không phải mọi cú pháp C đều được jextract biểu diễn trực tiếp. Một số nhóm thường gặp:

### Function-like macros

~~~c
#define DOUBLE_IT(x) ((x) * 2)
~~~

Không có method `DOUBLE_IT(...)` generated theo cơ chế constant-macro của jextract Guide. Nếu cần, viết wrapper C thật với exported function hoặc tự hiện thực logic Java sau khi đã hiểu macro side effects và types.

### C++ API

FFM/jextract hiện tập trung vào **C header ABI**. C++ classes, templates, overloads, exceptions, name mangling và ABI giữa compilers làm việc liên kết trực tiếp phức tạp. Thiết kế **`extern "C"` C-compatible wrapper** cho library C++ rồi jextract header wrapper; không tự cho rằng đọc `.hpp` là sẽ có generated Java API đầy đủ và portable.

### Static inline / không có exported symbol

~~~c
static inline int triple(int x) { return x * 3; }
~~~

Hàm này có thể được compiler inline và không có external symbol trong shared library. Đừng giả định jextract có thể gọi nó như exported function. Nếu cần callable ABI ổn định, viết một C wrapper exported. Để debug, kiểm output source và symbol table của native library.

### Header được preprocessing khác

`#ifdef`, `#define`, `-I` include paths, ABI, compiler target và feature macros ảnh hưởng declarations jextract nhìn thấy. Nếu Linux source chứa method mà Windows bindings không có, trước hết so generated preprocess configuration và native headers.

### Filtering

Để giảm output của thư viện lớn, jextract có `--include-function`, `--include-constant`, `--include-struct`, `--include-union`, `--include-typedef` và `--include-var`. Một lần chạy với filters sẽ **không sinh toàn bộ symbols**. Nếu một helper cần dependency đã bị lọc, tool có thể báo thiếu và dừng.

## 13. Dùng generated metadata để debug ABI

Đọc các accessor này trước khi quyết định cast hoặc sửa generator:

~~~java
// Ví dụ kiểm metadata trong một project đã generate:
FunctionDescriptor d = foo$descriptor();
MemorySegment addr = foo$address();
MethodHandle h = foo$handle();
~~~

Đây là **snippet** dùng trên binding thật khi có `foo`; header demo mục 7 không có tên `foo`, nên không copy snippet này vào `DemoMain`.

Một quy trình debug tốt:

1. Mở C header declaration gốc và chắc library build từ **đúng header version**.
2. Xác định generated header class (thường `demo_h`) và method wrapper.
3. Kiểm `$descriptor()`: có đúng số argument và return layout? Pointer có là `ADDRESS`? `long`, `size_t` có width thực tế nào?
4. Kiểm `$address()`: symbol có được tìm thấy đúng native shared library không? Đừng dereference function pointer như data.
5. Kiểm `$handle()` và wrapper: generated carrier Java có phù hợp `toMethodType()` không?
6. Với `struct`, xem `layout/sizeof/field$offset/field$layout`; đối chiếu `sizeof`/`offsetof` của C compiler dùng tạo binary.
7. Với callback, kiểm typedef C và helper `descriptor/allocate/invoke`, ABI, arena lifetime.
8. Chạy trên JDK/native compiler/OS/CPU mục tiêu, không dùng kết quả sinh ở platform khác làm chứng cứ đủ.

### `C_LONG` và bẫy platform

OpenJDK Guide có ví dụ generated `C_LONG` tương ứng `JAVA_INT` trên Windows 64-bit, vì C `long` là 32-bit ở ABI đó. Trên nhiều Unix x64, C `long` lại là 64-bit. Do đó:

- Không mặc định `long` của C bằng `long` của Java.
- Không copy Java source sinh ở Windows rồi mặc định chạy Linux mà không so header/ABI.
- Không thay generated constants `C_INT`, `C_LONG`, `C_POINTER` bằng `JAVA_INT`/`JAVA_LONG` tùy hứng.
- Khi cần portable ABI, cân nhắc các kiểu C có kích thước cố định (như `int32_t`/`int64_t`) và một C API đã xác định ABI rõ.

### So sánh struct offsets thực tế

Nếu struct thêm một pointer:

~~~c
struct WithPointer {
    char flag;
    void *data;
};
~~~

Thường có padding giữa `flag` và `data`. `sizeof(struct WithPointer)` có thể khác phép cộng 1 + sizeof(void*). Đối chiếu generated layout với native compiler bằng `offsetof(struct WithPointer, data)`; không ghi cứng offset từ máy khác.

## 14. Build, runtime loading và native access

Sửa source Java sinh thường **không** giải quyết được những vấn đề cơ bản sau:

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `jextract: command not found` | Công cụ không cài hoặc không có trong PATH | Cài jextract build tương thích JDK/OS; kiểm `jextract --version` |
| Không parse được `#include` | Thiếu include directories/defines | Cấu hình `-I` và `-D` đúng bộ C headers |
| Không có `foo(...)` | C header/filter/macro không đủ hoặc unsupported construct | Đối chiếu declaration và output `--include-*` |
| `ClassNotFoundException` với generated class | Build không compile/include Java source đúng | Kiểm generated package, `javac -d` và classpath/modulepath |
| `UnsatisfiedLinkError`/không tìm thư viện | Native binary chưa ở loader path/sai tên | Kiểm `--library`, file `.so/.dll/.dylib`, OS loader paths |
| Symbol missing khi gọi wrapper | Header khai báo nhưng shared library không export symbol | Kiểm version/symbol table/linking |
| Native access warning/error | Chưa cấp permission cho restricted FFM operation | `--enable-native-access=ALL-UNNAMED` hoặc named module tương ứng |
| `WrongMethodTypeException` | MethodHandle invoked với carrier type sai | Dùng generated wrapper hoặc đúng `MethodType` |
| Crash JVM khi gọi C | Sai ABI/layout/lifetime/null/function pointer | Đối chiếu native header, generated descriptors và ownership |
| Field getter bị out-of-bounds | Pointer segment size 0 hoặc slice thiếu byte | Chỉ reinterpret khi size/lifetime đã được native contract xác minh |
| Java callback không được gọi/đã free | Stub arena đóng sớm hoặc chưa register đúng | Giữ Arena sống, unregister/drain đúng lifecycle |

**Mục tiêu tối thiểu khi deploy:** ghim bộ phiên bản **C headers + native library binary + jextract + JDK/FFM ABI + target platform** và tái tạo generated source cùng cấu hình. Khi thay một thành phần có thể ảnh hưởng layout/signature, regenerate bindings và kiểm lại thay vì sửa generated Java thủ công.

## 15. Học cách đọc source có tên nội bộ thay đổi

Đôi khi generated source có class/helper tên lạ, methods nội bộ hoặc phần lớn logic nằm trong các method static. Thay vì học thuộc toàn bộ tên Java generator version cụ thể:

- Tìm **C symbol name** trong header class.
- Tìm **`$descriptor()`** để hiểu signature của C function.
- Tìm **`$layout()`** và **`$offset()`** để hiểu field data.
- Tìm **`sizeof()`** và **`layout()`** để biết struct aggregate.
- Tìm **`allocate(Arena/SegmentAllocator)`** cho struct hoặc callback; đọc return type để phân biệt allocation dữ liệu vs upcall stub.
- Tìm **`invoke(MemorySegment, ...)`** trong function pointer helper.
- Tìm **`$segment()`** cho C global variable.
- Tìm constant getters `NAME()`, nhớ enum không phải Java `enum`.
- Xem **generated comments** nếu có, nhưng hợp đồng cuối cùng vẫn nằm trong header/native docs và ABI.

Tên `$address()`, `$descriptor()`, `$handle()` không phải “nội dung thật” của C hàm; chúng phục vụ introspection/FFM linking. Java client có thể gọi generated `add_values(2,5)` mà không cần viết lại downcall handle. Đây là phần lợi ích chủ yếu của jextract.

## 16. Bài tự kiểm tra

**Câu 1.** `int add_values(int,int)` trong C trở thành Java `class AddValues` riêng hay wrapper trong header class?

Theo OpenJDK Guide, **function thông thường** được sinh thành **static wrapper method** trong header class, cùng các metadata accessors `$address/$descriptor/$handle`. Không cần class riêng cho mỗi non-variadic C function.

**Câu 2.** `#define DEMO_LIMIT 64` có dùng `DEMO_LIMIT` như Java constant field hay `DEMO_LIMIT()`?

Theo pattern được tài liệu hóa, jextract dùng **accessor method `DEMO_LIMIT()`** cho numeric macro. Tuy nhiên, kiểm output cụ thể; đừng giả định một macro phức tạp cũng được sinh.

**Câu 3.** `enum demo_state { DEMO_OFF, DEMO_ON }` có tạo một Java `enum DemoState` không?

Thường **không**. Các enum constants C được thể hiện như top-level accessor methods trong header class (`DEMO_OFF()`, `DEMO_ON()`). Cần làm bitwise operations bằng số khi ABI/API yêu cầu.

**Câu 4.** `Point.x$offset()` là chỉ số field thứ 0 hay byte offset?

Là **byte offset** của field `x` theo generated C struct layout. Nó giúp tránh giả định memory packed không có padding.

**Câu 5.** Vì sao `Point.sizeof()` đáng tin hơn tự cộng kích thước fields?

Nó phản ánh struct size từ layout generator theo ABI, bao gồm padding/alignment; tự cộng fields có thể sai.

**Câu 6.** `binary_fn.allocate((a,b)->a*b,arena)` và `binary_fn.invoke(ptr,a,b)` khác nhau ra sao?

`allocate` tạo **function pointer C gọi ngược Java** (upcall stub) có lifetime của arena; `invoke` giúp Java gọi một **native function pointer** (downcall). Hai hàm cùng liên quan pointer type nhưng chiều gọi khác nhau.

**Câu 7.** Một C function trả `struct Point *` có tự mang đủ byte bounds khi vào Java không?

Không nhất thiết. Native pointer trả về thường thiếu bounds/lifetime. Generated helper `Point.reinterpret` có thể cung cấp bounds nếu **caller xác minh** allocation, count, owner và cleanup. Không reinterpret bừa pointer không rõ nguồn gốc.

**Câu 8.** Không tìm thấy `DOUBLE_IT(x)` từ `#define DOUBLE_IT(x) ...` trong generated source: có chắc tool lỗi không?

Không. **Function-like macros không được jextract Guide hỗ trợ** như ordinary constants; cần wrapper C hoặc Java implementation có semantics tương ứng.

**Câu 9.** Build generated source từ Windows x64 rồi chạy Linux x64 có chắc C `long` giữ nguyên layout không?

Không. C `long` khác nhau giữa nhiều Windows và Unix x64 ABIs. Phải xem generated `C_LONG` và native library ABI theo nền tảng.

**Câu 10.** C callback được lưu bất đồng bộ, Java được đóng arena ngay sau `register` không?

Không. **Upcall stub chỉ hợp lệ khi arena còn sống**. C phải unregister và hoàn tất in-flight callbacks trước khi đóng arena.

**Câu 11.** `foo$descriptor()` đúng nhưng native call vẫn crash: vì sao?

Generated descriptor có thể đúng theo **header mà jextract đã parse** nhưng header/library binary không khớp, pointer invalid, sai thread/lifetime, sai allocator hoặc C ABI khác. Metadata không phải phép chứng minh tất cả memory accesses đều an toàn.

**Câu 12.** Những chỗ nào nên mở đầu khi review generated source?

Header class `demo_h` (function wrappers, constants và layouts C), struct class `Point` (layout/fields/allocate), function pointer class `binary_fn` (descriptor/allocate/invoke). Sau đó kiểm lại C header và library ABI.

## 17. Checklist để đọc và sử dụng bindings an toàn

- [ ] Đã xác minh đúng version JDK 22+/jextract, target OS/CPU, C compiler và native library?
- [ ] Biết tên generated header class (mặc định theo header, hoặc do `--header-class-name` đặt)?
- [ ] Tìm được wrapper của mỗi C function và `$descriptor/$address/$handle` metadata?
- [ ] Hiểu return/argument carrier types, đặc biệt C `long`/`size_t`/pointer/struct?
- [ ] Đọc constant accessors cho numeric/string macros và C enums; không giả định function-like macros được sinh?
- [ ] Biết class nào đại diện struct/union, `layout/sizeof` và `field$offset/$layout`?
- [ ] Với struct arrays, phân biệt element index của `asSlice` và byte offset của fields?
- [ ] Với function pointer, phân biệt `allocate` (Java callback upcall stub) và `invoke` (native function pointer downcall)?
- [ ] Callback stub và native data có arena/lifetime phù hợp tới hết C work, kể cả async?
- [ ] Đã xác minh null, buffer size, owner và đúng deallocator trước `reinterpret`/dereference?
- [ ] Đã kiểm generated code phù hợp native headers đã dùng để build binary và exported symbols?
- [ ] Đã hiểu vì sao C macro, static inline, typedef và platform conditional có thể không sinh theo kỳ vọng?
- [ ] Khi có lỗi, kiểm exact generated source và C ABI trước khi sửa tay file sinh?
- [ ] Đã có test chạy trên target platform, không phụ thuộc stdout địa chỉ thực tế hoặc layout ngẫu nhiên?
- [ ] Generated source chỉ regenerate khi header/tool thay đổi có chủ đích; không trộn các phiên bản ABI?

## Tài liệu tham khảo chính thức

1. [OpenJDK jextract — Guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md): mô tả cách dùng output của jextract cho functions, macros/enums, structs/unions, function pointers, typedefs, globals và variadic functions.
2. [Dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/): tải/cài tool, options, build và import bindings.
3. [Oracle Java SE 25 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/25/core/call-native-functions-jextract.html): ví dụ generated bindings và `qsort` callback.
4. [OpenJDK jextract repository](https://github.com/openjdk/jextract): source, releases/build instructions và samples.
5. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): nền tảng FFM chuẩn của Java 22+.
6. [Oracle Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall và ABI.
7. [Oracle Java SE 24 — MemoryLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemoryLayout.html): struct layouts, padding, byte offsets và alignment.

**Kết luận:** Khi đọc Java source do jextract sinh, hãy nối **C declaration → generated header/class → FFM layout/descriptor → Java wrapper/helper → native binary/ownership**. Functions sinh **wrappers và `$descriptor/$address/$handle`**, constants sinh **accessors**, structs sinh **layout/fields/allocate**, và function pointer types sinh **`descriptor/allocate/invoke`**. Hiểu những nhóm này giúp bạn đọc bindings nhanh, không nhầm hàm với hằng số, data pointer với function pointer, hoặc Java wrapper với quyền sở hữu native memory.
