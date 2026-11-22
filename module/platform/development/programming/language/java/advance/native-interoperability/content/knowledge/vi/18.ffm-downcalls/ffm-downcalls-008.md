# Hàm có số đối số biến đổi, firstVariadicArg và quy tắc nâng kiểu của C trong Java FFM

Một hàm C `variadic` được khai báo có dấu `...`, chẳng hạn `int printf(const char *format, ...);`. Phần `...` cho phép mỗi lần gọi có **số lượng và kiểu đối số khác nhau**, nhưng không phải một mảng chứa metadata kiểu. Khi Java dùng Foreign Function & Memory API (FFM) để gọi hàm này, native linker phải được cung cấp một **chữ ký chuyên biệt hóa**, bao gồm layout của **từng đối số thực tế**, và vị trí bắt đầu của phần variadic bằng `Linker.Option.firstVariadicArg(index)`. Phần variadic còn phải tuân thủ **default argument promotions của C**: `float` thành `double`, các kiểu số nguyên hẹp được nâng thành `int` hoặc `unsigned int` theo quy tắc biểu diễn.

Điểm then chốt: **FFM không tự thực hiện C promotions giúp bạn.** Nếu viết Java `float` rồi khai `ValueLayout.JAVA_FLOAT` ở vị trí `...`, bạn đang mô tả sai lời gọi native; native linker JDK 22 có thể từ chối. Nếu khai sai `firstVariadicArg`, ABI có thể truyền giá trị trong register hoặc vùng stack khác cách C function mong đợi, dẫn đến dữ liệu rác, undefined behavior hoặc JVM crash.

Bài thuộc nhóm **Gọi hàm bằng FFM**, dành cho **Java 22+** dùng API `java.lang.foreign` final (JEP 454). Ta giải thích chính xác vị trí argument và phép nâng kiểu, trường hợp không truyền argument tùy biến, ánh xạ Java carrier/C ABI, `printf`/`va_arg`, rồi tạo ví dụ **C11 + Java 22+ hoàn chỉnh** để thấy hai specialized handles cho cùng symbol, variadic `float`/`short`, và hàm có hai fixed parameters. Có hướng dẫn build trên Linux/macOS/Windows, stdout, bài tập và checklist an toàn.

## 1. C khai báo fixed arguments và variadic arguments thế nào?

Prototype:

~~~c
#include <stdio.h>

/* format là tham số cố định; ... là phần biến đổi. */
int printf(const char *format, ...);
~~~

Một lời gọi C:

~~~c
printf("%d and %.2f", 7, 1.25f);
~~~

Ánh xạ:

~~~text
Actual C source: printf("%d and %.2f", 7, 1.25f);
Argument index:                 0       1      2
Declaration:                const char* ...    ...
ABI type after promotion:       char*   int   double
                                |       \_____/
                                |       variadic
                                fixed

FFM descriptor: result JAVA_INT
                arguments ADDRESS, JAVA_INT, JAVA_DOUBLE
Option:         Linker.Option.firstVariadicArg(1)
~~~

Mặc dù biểu thức cuối là `1.25f` (C `float`), tại nơi C caller truyền qua dấu `...` nó được **nâng thành double**. `printf` khi gặp `%.2f` vì thế đọc `double`, không đọc `float`.

C cũng có function với nhiều hơn một fixed argument:

~~~c
long long add_from(int base, int count, ...);
~~~

Vị trí `base` = 0; `count` = 1; variadic argument đầu tiên = **2**, nên dùng `firstVariadicArg(2)`. `firstVariadicArg` nhận chỉ số **từ 0 của argument layout** trong function descriptor, **không tính return layout**.

**Phân biệt Java varargs:** Java `void log(Object... items)` thực tế nhận `Object[]`. C `void log(const char *fmt, ...)` không có mảng `Object`/`int[]` tự động và không mang runtime type tag. `FunctionDescriptor` trong FFM không thể tự suy ra signature từ chuỗi `fmt`.

## 2. C `va_list` tiêu thụ từng argument theo kiểu đã được nâng

Bên trong hàm C, header `<stdarg.h>` cung cấp `va_list`, `va_start`, `va_arg`, `va_end`. Ví dụ:

~~~c
#include <stdarg.h>

/* Mảnh minh họa: chỉ đúng khi C caller truyền count số int. */
long long sum_variadic(int count, ...) {
    va_list ap;
    va_start(ap, count);
    long long total = 0;
    for (int i = 0; i < count; ++i) {
        total += va_arg(ap, int);
    }
    va_end(ap);
    return total;
}
~~~

`va_start(ap, count)` dựa vào **tên của fixed parameter cuối cùng**. Mỗi `va_arg(ap,int)` lấy một argument ở vị trí variadic tiếp theo mà caller **đã truyền tương thích với `int`**. `va_arg` **không kiểm tra có đủ arguments**, không nhìn vào Java caller và không tự sửa kiểu. Nếu caller truyền hai argument nhưng count=3, C đọc giá trị không tồn tại: undefined behavior.

Với hỗn hợp:

~~~c
/* Mảnh C minh họa: mỗi cặp biến đổi gồm int rồi double. */
double sum_pairs(int pairs, ...) {
    va_list ap;
    va_start(ap, pairs);
    double total = 0.0;
    for (int i = 0; i < pairs; i++) {
        int whole = va_arg(ap, int);
        double fraction = va_arg(ap, double);
        total += whole + fraction;
    }
    va_end(ap);
    return total;
}
~~~

Nếu C caller truyền `short whole` và `float fraction` trong `...`, compiler dùng **int** và **double** theo promotions; Java FFM cũng phải xây descriptor `JAVA_INT` và `JAVA_DOUBLE` tương ứng. Không được sửa C thành `va_arg(ap, short)` hay `va_arg(ap,float)`: kiểu đó không khớp promoted argument.

**Cảnh báo:** Ở code production, phải kiểm tra count trong miền API cho phép và xử lý lỗi, nhưng guard count không chứng minh thực tế caller đã đưa đủ arguments. Hợp đồng số lượng và thứ tự phải được kiểm tra ở binding.

## 3. Bảng default argument promotions của C

Áp dụng cho **đối số trong `...`**, không tự áp dụng cho fixed prototype parameters.

| Kiểu C ban đầu | Kiểu khi đi qua `...` | FFM layout hay dùng trên ABI desktop | Ghi chú |
| --- | --- | --- | --- |
| `float` | **`double`** | `ValueLayout.JAVA_DOUBLE` | Java phải truyền `double`, không truyền `float` |
| `char`, `signed char` | `int` nếu `int` biểu diễn được giá trị | `JAVA_INT` | Java `byte` phải cast sang `int` |
| `unsigned char` | `int` nếu chứa hết miền, nếu không `unsigned int` | Thường `JAVA_INT` | Xác minh ABI đặc biệt |
| `short` / `unsigned short` | `int` hoặc `unsigned int` theo integer promotions | Thường `JAVA_INT` | `JAVA_SHORT` không phù hợp tại dấu `...` |
| `_Bool` | `int` trong integer promotions | Thường `JAVA_INT` | C chỉ có 0/1 cho `_Bool` |
| C enumeration | integer-promoted type | Thường `JAVA_INT` | Enum có underlying type/range theo implementation |
| `int` / `unsigned int` | Giữ loại tương ứng | `JAVA_INT` | Signedness cần mapping đúng |
| `double` | `double` | `JAVA_DOUBLE` | Không nâng thành `long double` |
| `long` / `long long` | Giữ loại tương ứng | canonical C layout | C `long` 32-bit trên Windows x64, 64-bit thường trên Linux x64 |
| C pointer (`void*`, `char*`) | Pointer | `ADDRESS` | Đúng lifetime và type con trỏ |
| Struct/union | Không tự chuyển thành primitive | ABI group layout nếu được native linker hỗ trợ | Passing aggregates variadic phức tạp; ưu tiên typed wrapper |

**Integer promotions chính xác:** Kiểu số nguyên nhỏ chuyển sang `int` **nếu `int` biểu diễn được mọi giá trị của kiểu gốc**, nếu không sang `unsigned int`. Trên OS/CPU phổ biến (`int` 32 bit), `char` và `short` đa số thành `int`. Không được giả định vậy trên mọi C implementation.

**Điểm dễ nhầm:** Giá trị `float f=0.1f` chuyển thành `double` **không trở thành** giá trị cùng biểu diễn với literal `0.1d`. Nó giữ số đã làm tròn ở độ chính xác float, rồi biểu diễn ở double. Đó cũng là ngữ nghĩa C default promotion. Để stdout chính xác trong ví dụ, ta chọn `1.25f` và `2.5f`, đều biểu diễn được chính xác trong binary floating point.

## 4. `firstVariadicArg` đánh dấu ranh giới ABI chứ không thêm arguments

JDK 22 cung cấp:

~~~java
// Chỉ là mảnh mô tả API; xem ví dụ runnable ở mục 8.
Linker.Option.firstVariadicArg(int index);
~~~

Với một `FunctionDescriptor` có `N` argument layouts, chỉ số nằm trong khoảng **0 ≤ index ≤ N**:

- `index=0`: đánh dấu mọi argument là variadic; chỉ dùng nếu hợp đồng/prototype thực sự có ý nghĩa tương ứng.
- `0 < index < N`: argument layout có chỉ số index và mọi layout sau nó là variadic.
- `index=N`: **không có variadic argument trong lời gọi cụ thể**.
- **Vẫn phải đưa `firstVariadicArg` khi `index=N`** để đánh dấu function gốc có `...`; một vài C ABI vẫn phân biệt cách gọi variadic với non-variadic khi số phần tử biến đổi bằng 0.

Chẳng hạn với `long long sum_ints(int count, ...)`:

| C call | Argument layouts trong descriptor (không tính return) | `firstVariadicArg` |
| --- | --- | ---: |
| `sum_ints(0)` | `(JAVA_INT)` | 1 = N |
| `sum_ints(1,42)` | `(JAVA_INT,JAVA_INT)` | 1 |
| `sum_ints(3,10,20,-5)` | `(JAVA_INT,JAVA_INT,JAVA_INT,JAVA_INT)` | 1 |

Cùng C symbol có ba **dạng chuyên biệt hóa** và cần các `MethodHandle` có arity tương ứng. `firstVariadicArg(1)` không biến Java `invokeExact` thành một phương thức có `Object...`. Java vẫn phải đưa đúng số và đúng carrier types theo `FunctionDescriptor`.

Với `long long add_from(int base,int count,...)`, số fixed arguments là 2; dùng `firstVariadicArg(2)` kể cả khi không thêm argument nào (`N=2`). Nhầm index thành 1 khiến FFM coi `count` là variadic mặc dù khai báo C cho biết đó là fixed.

### 4.1. Vì sao ranh giới ảnh hưởng ABI?

Một số C ABI áp dụng cách passing đối số biến đổi khác so với fixed prototypes, nhất là khi có floating-point/vector registers và metadata liên quan. Bằng chứng một descriptor “tình cờ chạy đúng” trên một máy không đủ chứng minh portable. `firstVariadicArg` giúp linker dùng quy tắc phù hợp cho các arguments từ vị trí chỉ định. Cần biết **đúng số fixed arguments từ C header** thay vì đoán từ test.

Oracle `Linker` JDK 22 còn quy định native linker chỉ hỗ trợ linking **specialized form** của hàm variadic; nó không tự áp dụng default promotions. Native linker có thể từ chối layout đại diện kiểu C chưa được promote ở variadic position; trên Linux/x64, ví dụ gồm C `float`, `char` và `short`. Tuy nhiên không thể trông chờ linker bắt **mọi** descriptor sai: C symbol không chứa đủ metadata kiểu/số đối số để đối chiếu.

## 5. Lập `FunctionDescriptor` đúng return, fixed và variadic arguments

Với C:

~~~c
long long sum_ints(int count, ...);
~~~

FFM Java 22+:

~~~java
// Mảnh minh họa: cần Java imports, linker và symbol trước khi chạy.
FunctionDescriptor callThree = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG, // kết quả C long long
        ValueLayout.JAVA_INT,  // fixed count, index 0
        ValueLayout.JAVA_INT,  // vararg index 1
        ValueLayout.JAVA_INT,  // vararg index 2
        ValueLayout.JAVA_INT); // vararg index 3

MethodHandle sumThree = linker.downcallHandle(
        sumSymbol, callThree,
        Linker.Option.firstVariadicArg(1));

long value = (long) sumThree.invokeExact(3, 10, 20, -5);
~~~

**Lưu ý method-handle typing:** `ValueLayout.JAVA_INT` tạo Java carrier `int`, `JAVA_LONG` là Java `long`; trong `invokeExact`, call site phải sử dụng đúng argument/return Java types. Nếu biến Java gốc là `short` thì cast rõ thành `int`, tương tự `float` cast thành `double` khi tham gia variadic call. Nếu không khớp `MethodHandle.type()`, Java thường ném `WrongMethodTypeException`, nhưng **đây là kiểm tra kiểu Java**, không chứng minh C ABI signature thật đã đúng.

Descriptor cho lời gọi không có extra args:

~~~java
FunctionDescriptor callZero = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,
        ValueLayout.JAVA_INT);

MethodHandle sumZero = linker.downcallHandle(
        sumSymbol, callZero,
        Linker.Option.firstVariadicArg(1));
long zero = (long) sumZero.invokeExact(0);
~~~

**Quan trọng:** return layout **đứng riêng trước danh sách đối số** và **không được tính vào `firstVariadicArg`**. Nếu function trả `void`, dùng `FunctionDescriptor.ofVoid(...)`; danh sách argument layouts vẫn bắt đầu index0.

### 5.1. Khi nào dùng `JAVA_FLOAT`?

Nếu function C không có `...`:

~~~c
double fixed_float(float x);
~~~

thì `x` là fixed prototype parameter có C type `float`. FFM descriptor phù hợp trên ABI thông dụng là:

~~~java
FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE, // C double return
        ValueLayout.JAVA_FLOAT); // C fixed float argument
~~~

**Không** nâng `fixed_float(float)` thành `double`: promotions của ellipsis không áp dụng cho fixed parameter đã có prototype. Ngược lại, một `float` được đưa qua `...` phải thành `double`. Ví dụ hoàn chỉnh chạy cả hai để chứng minh.

## 6. Mismatch trong `printf` và cách giảm rủi ro

Prototype:

~~~c
int printf(const char *format, ...);
~~~

Trong Java FFM, lời gọi tương đương `printf("%d + %.2f",7,1.25)` cần:

~~~java
// Mảnh JDK22+, giả định linker là Linker.nativeLinker()
// và native C library chứa symbol printf trong defaultLookup().
MethodHandle printf = linker.downcallHandle(
        linker.defaultLookup().find("printf").orElseThrow(),
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,    // C int return
                ValueLayout.ADDRESS,     // const char* fixed
                ValueLayout.JAVA_INT,    // %d: promoted int
                ValueLayout.JAVA_DOUBLE),// %f: double
        Linker.Option.firstVariadicArg(1));

try (Arena arena = Arena.ofConfined()) {
    MemorySegment fmt = arena.allocateFrom("%d + %.2f\n");
    int printed = (int) printf.invokeExact(fmt, 7, 1.25d);
}
~~~

Đây là **mảnh minh họa** không phải file runnable độc lập: cần imports, `throws Throwable`, quyền native access và native `printf` có trong lookup tương ứng. Để kiểm thử đồng nhất Linux/macOS/Windows, bài dùng thư viện C riêng ở mục 7 thay vì phụ thuộc libc và locale của `printf`.

Với format-based API, **đúng layout chưa đủ**: mỗi conversion specifier phải khớp kiểu dữ liệu thực tế sau promotions:

- `%d` yêu cầu C `int` (Java layout thường `JAVA_INT`).
- `%f`/`%.2f` của `printf` yêu cầu **double**, không phải float; FFM `JAVA_DOUBLE`.
- `%s` yêu cầu C `char*` trỏ tới chuỗi byte có NUL terminator, lifetime còn hợp lệ; FFM `ADDRESS`/`MemorySegment`.
- `%p` yêu cầu pointer phù hợp; không dùng Java `long` chỉ vì pointer rộng 8 byte.
- `%ld` yêu cầu C `long`, `%lld` yêu cầu C `long long`, `%zu` yêu cầu `size_t`. C `long` thường 32-bit trên Windows x64 nhưng 64-bit trên Linux x64; xem `linker.canonicalLayouts()`.
- `%*.*f` tiêu thụ hai variadic `int` cho width/precision **trước** một `double`.
- `%n` ghi qua pointer; format string do người dùng kiểm soát có thể tạo nguy cơ đọc/ghi tùy ý. Không truyền untrusted string làm format.

**Sai kiểu/sai count là undefined behavior của C**, có thể ném JVM vào crash, không nhất thiết sinh một Java exception. `printf("%d", 1.5)` không tự ép double thành int. Đặc biệt đừng dùng `sprintf` không có capacity; khi cần formatted C output, ưu tiên `snprintf` với buffer cap và kiểm tra kết quả.

Một API C wrapper an toàn hơn thường tách typed functions:

~~~c
/* Chỉ minh họa interface; không phải toàn bộ file chạy độc lập. */
int log_i32(const char *label, int32_t value);
int log_f64(const char *label, double value);
int log_blob(const unsigned char *bytes, size_t count);
~~~

Có thể gọi ba hàm này bằng FFM descriptors cố định, không cần gắn varargs metadata runtime. Với dữ liệu format động từ client Java, wrapper kiểu `pointer+length` thường đáng bảo trì hơn một hệ thống tự tạo mọi variadic signatures.

## 7. C11 hoàn chỉnh: thư viện `varbridge` có ba dạng variadic và một hàm fixed

Để học từ một ví dụ độc lập, ta dùng C ABI thuần, không chứa `JNIEnv` hoặc hàm `Java_package_Class_method`. Thư viện export bốn functions:

- `sum_ints(int count,...)`: đọc `count` số `int` variadic; Java tạo handle cho 3 extras và một handle cho 0 extras.
- `sum_pairs(int pair_count,...)`: đọc tuần tự các cặp `int,double`; Java chuẩn bị `short/byte` thành `int` và `float` thành `double`.
- `add_from(int base,int count,...)`: hai fixed args, kiểm tra `firstVariadicArg(2)`.
- `fixed_float(float value)`: non-variadic control case, input `JAVA_FLOAT`.

Sơ đồ:

~~~text
ffm-varargs/
├── native/
│   └── varbridge.c
├── src/
│   └── VariadicDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

Tạo file đầy đủ `native/varbridge.c`:

~~~c
#include <stdarg.h>

#if defined(_WIN32)
#define API_EXPORT __declspec(dllexport)
#else
#define API_EXPORT __attribute__((visibility("default")))
#endif

/* Demo dành cho target thông dụng: int32, long long64, double64. */
_Static_assert(sizeof(int) == 4, "C int must be 4 bytes");
_Static_assert(sizeof(long long) == 8, "C long long must be 8 bytes");
_Static_assert(sizeof(double) == 8, "C double must be 8 bytes");

API_EXPORT long long sum_ints(int count, ...) {
    if (count < 0 || count > 16) {
        return -1;
    }

    va_list ap;
    va_start(ap, count);
    long long total = 0;
    for (int i = 0; i < count; ++i) {
        total += (long long) va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

API_EXPORT double sum_pairs(int pair_count, ...) {
    if (pair_count < 0 || pair_count > 8) {
        return -1.0;
    }

    va_list ap;
    va_start(ap, pair_count);
    double total = 0.0;
    for (int i = 0; i < pair_count; ++i) {
        int whole = va_arg(ap, int);
        double fraction = va_arg(ap, double);
        total += (double)whole + fraction;
    }
    va_end(ap);
    return total;
}

API_EXPORT long long add_from(int base, int count, ...) {
    if (count < 0 || count > 16) {
        return -1;
    }

    va_list ap;
    va_start(ap, count);
    long long total = (long long)base;
    for (int i = 0; i < count; ++i) {
        total += (long long) va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

API_EXPORT double fixed_float(float value) {
    return (double)value;
}
~~~

**Đây là nguyên tệp C11**, biên dịch thành shared library, không có `main`. `API_EXPORT` đảm bảo C symbols xuất hiện trong binary trên GCC/Clang/MSVC. `_Static_assert` ngăn dùng ví dụ trên target khác các width assumptions đã nêu; vẫn cần kiểm tra kiến trúc/toolchain ABI khi triển khai.

Vì `va_arg(ap, int)` chỉ dùng sau khi Java đã gửi `int`, và `va_arg(ap, double)` chỉ dùng sau Java `double`, C đọc đúng các giá trị. Hàm `sum_ints` giới hạn count≤16 nên cộng tối đa 16 `int` có thể đại diện bằng `long long` mà không overflow. Với `sum_pairs`, count≤8; cả Java lẫn C phải đồng ý rằng **mỗi cặp tiêu thụ hai arguments**. Những guards này không chữa mismatch khi caller nói 3 nhưng chỉ cấp hai variadic arguments.

**Chú ý `va_start`:** trong `add_from(int base,int count,...)` phải gọi `va_start(ap,count)` vì `count` mới là **last named parameter**. Gọi `va_start(ap,base)` không mô tả đúng vị trí bắt đầu variadic parameters theo C và có thể gây undefined behavior.

## 8. Java 22+ hoàn chỉnh: chuyên biệt hóa bốn kiểu gọi

Tạo nguyên file `src/VariadicDemo.java`, không khai báo package:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class VariadicDemo {
    private VariadicDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of("build", "lib",
                System.mapLibraryName("varbridge")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            MemorySegment sumAddress =
                    symbols.find("sum_ints").orElseThrow();

            // sum_ints(3, 10, 20, -5): 1 fixed + 3 variadic ints.
            MethodHandle sumThree = linker.downcallHandle(
                    sumAddress,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    Linker.Option.firstVariadicArg(1));

            long sum3 = (long) sumThree.invokeExact(3, 10, 20, -5);

            // Cùng C function, nhưng lần này KHÔNG có extra args.
            // Vẫn dùng firstVariadicArg(1), bằng N=1.
            MethodHandle sumZero = linker.downcallHandle(
                    sumAddress,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT),
                    Linker.Option.firstVariadicArg(1));

            long sum0 = (long) sumZero.invokeExact(0);

            // Mỗi pair tiêu thụ int + double sau promotion.
            MethodHandle pairs = linker.downcallHandle(
                    symbols.find("sum_pairs").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.JAVA_INT,    // fixed pair_count
                            ValueLayout.JAVA_INT,    // promoted short
                            ValueLayout.JAVA_DOUBLE, // promoted float
                            ValueLayout.JAVA_INT,    // promoted byte
                            ValueLayout.JAVA_DOUBLE),// promoted float
                    Linker.Option.firstVariadicArg(1));

            short firstWhole = 7;
            float firstFraction = 1.25f;
            byte secondWhole = -2;
            float secondFraction = 2.5f;

            double pairSum = (double) pairs.invokeExact(
                    2,
                    (int) firstWhole, (double) firstFraction,
                    (int) secondWhole, (double) secondFraction);

            // Hai đối số cố định: base index 0, count index 1.
            MethodHandle addFrom = linker.downcallHandle(
                    symbols.find("add_from").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT,  // fixed base
                            ValueLayout.JAVA_INT,  // fixed count
                            ValueLayout.JAVA_INT,  // variadic
                            ValueLayout.JAVA_INT), // variadic
                    Linker.Option.firstVariadicArg(2));

            long twoFixed = (long) addFrom.invokeExact(100, 2, 20, -3);

            // Non-variadic: C float cố định -> JAVA_FLOAT.
            MethodHandle fixedFloat = linker.downcallHandle(
                    symbols.find("fixed_float").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.JAVA_FLOAT));

            double fixed = (double) fixedFloat.invokeExact(1.25f);

            System.out.println("sum3=" + sum3);
            System.out.println("sum0=" + sum0);
            System.out.println("pairSum=" + pairSum);
            System.out.println("twoFixed=" + twoFixed);
            System.out.println("fixedFloat=" + fixed);
        }
    }
}
~~~

**Vì sao những lời gọi này khớp C?**

1. `sumThree` nhận Java arguments `(int,int,int,int)`, trả `long`, fixed count có index0; linker biết phần index1..3 là variadic.
2. `sumZero` nhận `(int)`, trả `long`, `index=N=1`, vẫn gắn firstVariadicArg vì prototype C có dấu `...`.
3. `pairs` nhận `(int,int,double,int,double)`; `short`/`byte` được Java cast tường minh thành int, `float` thành double trước `invokeExact`. C `va_arg(ap,int)` và `va_arg(ap,double)` đọc đúng thứ tự.
4. `addFrom` có `firstVariadicArg(2)`, tránh đánh dấu nhầm fixed `count` làm variadic.
5. `fixedFloat` nhận `float`, trả `double` và không cần option, giúp phân biệt fixed-parameter ABI với ellipsis.
6. `SymbolLookup.libraryLookup(path,arena)` dùng đường dẫn đến thư viện được build, và `Arena` còn mở trong suốt downcalls. Sau close, không tiếp tục gọi những MethodHandle gắn với library symbol nữa.
7. `MethodHandle.invokeExact` yêu cầu Java carrier types chính xác; `throws Throwable` là cách viết gọn cho ví dụ giáo dục.

**Không dùng `javac -h`:** đây là C ABI được FFM gọi trực tiếp, không phải native methods kiểu JNI. Không có tham số `JNIEnv*` hay `jobject`.

## 9. Build trên Linux, macOS và Windows

Chạy từ thư mục gốc `ffm-varargs`. Cần **JDK 22+** với FFM final, C compiler hỗ trợ C11 và shared library cùng kiến trúc CPU với JVM.

### 9.1. Linux (GCC/Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/varbridge.c -o build/lib/libvarbridge.so

javac -d build/classes src/VariadicDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes VariadicDemo
~~~

### 9.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/varbridge.c -o build/lib/libvarbridge.dylib

javac -d build/classes src/VariadicDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes VariadicDemo
~~~

### 9.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /std:c11 /LD native\varbridge.c ^
  /link /OUT:build\lib\varbridge.dll

javac -d build\classes src\VariadicDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes VariadicDemo
~~~

Lệnh Windows dùng **Command Prompt**, ký tự `^` nối dòng. MSVC cần hỗ trợ `/std:c11`; chạy từ Developer Command Prompt có cấu hình x64. JDK và shared library phải có cùng architecture. `System.mapLibraryName("varbridge")` tạo tên OS tương ứng.

**Native-access flag:** `--enable-native-access=ALL-UNNAMED` dành cho classpath/unnamed module; với module có tên thì cấp quyền theo tên module thay vì mở rộng cho tất cả. `SymbolLookup.libraryLookup` và `Linker.downcallHandle` là những restricted operations. JDK22+ **không yêu cầu `--enable-preview`**.

### 9.4. Stdout kỳ vọng từ source

~~~text
sum3=25
sum0=0
pairSum=8.75
twoFixed=117
fixedFloat=1.25
~~~

Phép tính được xác định:

- `sum3` = 10 + 20 - 5 = **25**.
- `sum0` = 0 vì C count0 nên không đọc bất kỳ `va_arg` nào.
- `pairSum` = (7 + 1.25) + (-2 + 2.5) = **8.75**.
- `twoFixed` = base100 + 20 - 3 = **117**.
- `fixedFloat` = float 1.25f được C đổi sang double 1.25 để trả; fixed input vẫn truyền theo C `float`.

Đây là stdout **suy ra từ source logic** với ABI đúng và build thành công, không phải khẳng định đã chạy compiler trên máy bạn. Chạy integration test thật trên OS/architecture triển khai để xác nhận.

### 9.5. Kiểm tra exported C symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libvarbridge.so
~~~

Các tên mong đợi:

~~~text
sum_ints
sum_pairs
add_from
fixed_float
~~~

macOS: `nm -gU build/lib/libvarbridge.dylib` (Mach-O tool thường thêm dấu `_` vào tên symbol); Windows: `dumpbin /exports build\lib\varbridge.dll`. `symbols.find(...).orElseThrow()` không tìm thấy tên có thể ném `NoSuchElementException`. Đừng nhầm lỗi lookup/export với lỗi promotions hoặc `firstVariadicArg`.

## 10. Khi ánh xạ ABI của C, tên kiểu là chưa đủ

FFM `ValueLayout` có carrier Java và kích thước/alignment cụ thể. **C ABI** còn phụ thuộc OS/CPU/compiler. Đặc biệt:

- C `int` thường rộng 32 bit trên các nền tảng desktop; `ValueLayout.JAVA_INT` phù hợp trong ví dụ có `_Static_assert(sizeof(int)==4)`.
- C `double` thường rộng 64 bit; ví dụ kiểm tra `sizeof(double)==8` và dùng `JAVA_DOUBLE`.
- C `long long` trong ví dụ có 8 byte; return layout dùng `JAVA_LONG` trên các target thường gặp, và có static assert bảo vệ width.
- C `long` thường 64-bit Linux x64 nhưng 32-bit Windows x64. `JAVA_LONG` là Java long 64-bit, không được mặc định ánh xạ cho mọi C long.
- C `size_t` thường 64-bit trên 64-bit và 32-bit trên 32-bit. Không dùng Java `int` hoặc `long` dựa trên tên.
- Pointer dùng `ValueLayout.ADDRESS` với Java carrier `MemorySegment`, **không phải** `JAVA_LONG` chỉ vì pointer 8 byte.
- C `long double` không đồng nghĩa `double`; linker có thể không hỗ trợ layout tương ứng trên ABI mục tiêu.

Để xem các ánh xạ canonical:

~~~java
// Mảnh minh họa Java 22+, không phải chương trình độc lập.
Linker linker = Linker.nativeLinker();
var cInt = linker.canonicalLayouts().get("int");
var cLong = linker.canonicalLayouts().get("long");
var cLongLong = linker.canonicalLayouts().get("long long");
var cSizeT = linker.canonicalLayouts().get("size_t");
var cDouble = linker.canonicalLayouts().get("double");
~~~

**Trình tự đúng:** (1) xác định kiểu C *sau default promotion* ở từng variadic position; (2) lấy layout ABI cho kiểu đó; (3) đối chiếu Java carrier khi `invokeExact`. Lấy canonical `"float"` rồi đặt thẳng vào variadic position vẫn sai: C caller đã chuyển float thành double.

Với C++ API có `...`, đừng coi vtable/name mangling và C++ exception semantics tự được FFM xử lý. Nếu có thể, viết một C ABI wrapper có `extern "C"` và typed parameters để binding ổn định.

## 11. Vì sao một sai khác nhỏ có thể gây lỗi lớn?

Một native function không chứa đủ metadata để FFM xác định bạn đã khai đúng descriptor. Sai lệch có thể xảy ra tại ba tầng:

| Tầng | Điều phải đúng | Sai thường thấy |
| --- | --- | --- |
| **Java MethodHandle** | Java carrier và arity khớp descriptor | `WrongMethodTypeException` do truyền float/short khi handle cần double/int |
| **FFM → C ABI** | `firstVariadicArg`, type layouts, return layout, register classes đúng | Linker từ chối unsupported layout hoặc tạo call không portable |
| **C callee** | `va_arg(ap,T)`, count/format/types đúng theo caller | Undefined behavior, sai số, memory corruption hoặc JVM crash |

Một số sai ABI không có exception đáng tin để bắt. Đặc biệt, việc đổi một `JAVA_INT` thành `JAVA_DOUBLE` ở descriptor hoặc đặt sai index có thể khiến C đọc sai floating-point/integer register. `-Xcheck:jni` cũng không phải giải pháp đầy đủ cho lỗi **FFM downcall**; JNI checker và FFM API là hai ranh giới khác nhau.

Với program production, nên **giới hạn tập chữ ký được hỗ trợ**, cho chúng qua tests trên mỗi OS/architecture, và tách contract dạng typed C wrapper khi cấu trúc `...` quá động. Không cho người dùng tự cung cấp cả format string và danh sách/native type unchecked rồi truyền trực tiếp qua FFM.

### 11.1. Cache specialized handles thế nào?

Nếu chỉ có các dạng như `sum_ints(count=0)`, `sum_ints(count=1)` và `sum_ints(count=3)`, tạo ba handles có descriptor riêng và cache theo **(symbol, return ABI, ordered argument layouts, firstVariadicArg)**. Không cache một handle kiểu `(int,int,int,int)→long` rồi dùng để gọi một argument. Các handles và symbol addresses phải còn hợp lệ suốt lifetime native library/`Arena` giữ `libraryLookup`.

Với printf-style API, có thể cung cấp các wrapper Java typed:

~~~java
// Mảnh interface Java minh họa, không có implementation ở đây.
int printInt(MemorySegment format, int value);
int printDouble(MemorySegment format, double value);
int printIntDouble(MemorySegment format, int value, double value);
~~~

Mỗi wrapper sử dụng một specialized FFM handle đã kiểm thử. Nếu format động không tương thích với wrapper, phải từ chối hoặc dùng cơ chế format phía Java, không cast dữ liệu tùy ý cho vừa ABI.

## 12. Lỗi phổ biến và hướng xử lý

| Triệu chứng/anti-pattern | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| `JAVA_FLOAT` ở vùng ellipsis | C `float` bị promote thành `double` | Dùng `JAVA_DOUBLE` và Java `double` |
| `JAVA_SHORT/JAVA_BYTE` ở vùng ellipsis | C integer promotions | Dùng C promoted type/layout, thường `JAVA_INT` |
| Gọi variadic function mà không có `firstVariadicArg` | ABI không được mô tả là variadic | Luôn thêm option, kể cả không có extras |
| `firstVariadicArg(1)` cho C có hai fixed params | Sai ranh giới fixed/variadic | Đếm parameter list và dùng index2 |
| `firstVariadicArg(N+1)` | Chỉ số ngoài [0,N] | Đặt index trong bounds theo `argumentLayouts` |
| Dùng cùng handle cho số extras khác | `MethodHandle` có arity cố định | Tạo specialized handle khác |
| `invokeExact` với Java `short` khi layout `JAVA_INT` | Carrier mismatch | Cast rõ `(int) value` |
| `invokeExact` với Java `float` khi layout `JAVA_DOUBLE` | Carrier mismatch | Cast rõ `(double) value` |
| `va_arg(ap,float)` cho C ellipsis float | C đã nâng float thành double | Dùng `va_arg(ap,double)` |
| `va_start(ap,base)` khi last fixed là `count` | Sai last named parameter | `va_start(ap,count)` |
| C count sai số arguments đã truyền | Không có runtime arity check trong C `...` | Ràng buộc count và descriptor, thử positive cases |
| `printf` format `%s` với Java `String` | String Java không phải C pointer | Cấp C string buffer với NUL/encoding/lifetime |
| `printf` format bị kiểm soát bởi input | Có thể gây format-string vulnerability | Fixed format, escape data, typed wrappers |
| C `long` bị xem là 64-bit trên Windows x64 | LLP64 vs LP64 | Dùng `canonicalLayouts()` |
| `long double` được mô tả bằng `JAVA_DOUBLE` | ABI khác và không chắc được hỗ trợ | Dùng C wrapper cố định |
| Code chạy trên Linux nhưng sai trên Windows | Variadic ABI khác hoặc native export | Kiểm tra index, layouts, build arch, ABI |
| Thiếu native-access flag | Restricted operations bị giới hạn | Cấp quyền cho đúng module |
| Library lookup có nhưng symbol thiếu | C export/name path sai | Kiểm tra `nm`/`dumpbin` |
| Java đóng arena quá sớm | Symbol/lookup lifetime hết | Giữ scope đến khi mọi downcalls xong |

### 12.1. Tại sao `printf("%f", 1.25f)` khác `fixed_float(1.25f)`?

Ở C, literal `1.25f` mang kiểu `float`. Nhưng `printf` có dấu `...`, nên C tự nâng float thành double và `printf` đọc double. `fixed_float(float)` có prototype khai rõ float, nên nhận float. Điều này phản ánh **hợp đồng C** chứ không phải mức độ an toàn tuyệt đối của một Java conversion. FFM Java caller phải mô tả đúng hai ABI types khác nhau.

## 13. Bài tập theo mức độ

1. `int printf(const char *fmt,...)` có bao nhiêu fixed arguments, index variadic đầu tiên là gì? **Một, index 1.**
2. `void log(int severity,const char *fmt,...)` có index nào? **2.**
3. Hàm `sum_ints(0)` cần bao nhiêu argument layouts? Có cần option không? **Một fixed `JAVA_INT`; cần `firstVariadicArg(1)`.**
4. `sum_ints(1,42)` cần descriptor mấy argument layouts? **Hai `JAVA_INT`, index1.**
5. `sum_ints(3,10,20,-5)` có thể dùng handle của `sum_ints(0)` không? **Không: arity khác.**
6. C `float f=1.25f; log(1,f)`, argument của `f` tại C ABI là gì? **double; FFM `JAVA_DOUBLE`.**
7. Java `byte b=-2` cần Java carrier nào khi đi vào C ellipsis expected `int`? **Java int, cast `(int)b`.**
8. Tại sao `_Bool` tại C ellipsis không dùng thẳng `JAVA_BOOLEAN`? **Integer promotion, thường `int`.**
9. C `double fixed_float(float)` cần input layout gì? **`JAVA_FLOAT`, vì input fixed chứ không phải variadic.**
10. C `void output(int count,...)` đọc `va_arg(ap,double)` khi Java đưa `JAVA_INT`: có gì sai? **Promoted types không khớp; undefined behavior.**
11. C `printf("%*.*f",width,precision,value)` cần bao nhiêu variadic arguments và types? **Ba: int, int, double.**
12. C `long` trên Windows x64 nên tự động ánh xạ `JAVA_LONG`? **Không; C long thường 32-bit.**
13. Tại sao không bỏ `firstVariadicArg` nếu toàn bộ arguments đều là int? **Variadic ABI có thể khác và spec yêu cầu option.**
14. Khi API C nhận C++ object hay `long double` qua ellipsis và linker không hỗ trợ, nên làm gì? **Typed C ABI wrapper.**
15. Làm sao xử lý printf format không tin cậy? **Không dùng input làm format, tạo format cố định hoặc format Java trước.**
16. Tại sao test trên một OS chưa chứng minh đúng? **C ABI và register calling convention khác theo target.**

Các bài tập cố ý hỏi về contract/types hơn là yêu cầu chạy **đoạn FFM sai ABI**. Đừng chủ động gọi native với descriptor mismatch chỉ để xem JVM có exception nào; sai ABI có thể làm crash cả process.

## 14. Checklist trước khi đưa C variadic downcall vào production

- [ ] C header có `...`? Đã đếm **fixed parameters** để chọn đúng `firstVariadicArg(index)` 0-based chưa?
- [ ] Đã lập `FunctionDescriptor` chứa từng actual argument layout theo đúng thứ tự của **một specialized call**?
- [ ] Có gắn option `firstVariadicArg` **kể cả khi không truyền thêm argument** (`index=N`)?
- [ ] Đã áp dụng **default argument promotions** cho mọi `...`: `float→double`, narrow integers→`int/unsigned int` theo C?
- [ ] Java carriers tại `invokeExact` là `int`/`double`/`MemorySegment` tương thích layouts, không dùng nhầm `short/float`?
- [ ] C `va_arg(ap,T)` tiêu thụ đúng type/số arguments, `va_start` dựa trên last fixed parameter, `va_end` được gọi?
- [ ] Return type, C `long`/`long long`/`size_t`, pointer, signedness và ABI canonical layouts đã được xác minh trên target?
- [ ] Có test descriptor/`firstVariadicArg` trên từng OS/CPU/ABI triển khai, không suy từ một lần chạy may mắn?
- [ ] Với format-based APIs, format specifiers, width/precision `*`, encoding, NUL terminator, buffer capacity và số args khớp?
- [ ] Format string không do untrusted input điều khiển; đã tránh `sprintf` không có capacity và `%n` không mong muốn?
- [ ] Native library được export đúng tên, kiến trúc JVM/compiler khớp, arena giữ symbol còn sống suốt downcalls?
- [ ] Đã cấp quyền native access phù hợp trên JDK 22+; không nhầm code final API với Java 17 incubator/Java 21 preview?
- [ ] Khi số lượng/loại arguments thay đổi tự do ở runtime, đã cân nhắc **typed C wrapper + array/count** để giảm nguy cơ varargs mismatch?
- [ ] Không dựa vào `IllegalArgumentException`/`WrongMethodTypeException` của Java như bằng chứng C ABI/format đúng hoàn toàn?

**Kết luận:** Gọi một hàm C `...` qua FFM không có nghĩa Java tự có “C varargs”. Mỗi lời gọi phải được **chuyên biệt hóa thành descriptor cố định**, đánh dấu ranh giới đúng bằng `Linker.Option.firstVariadicArg` và dùng **các kiểu đã được C default-promote** cho phần biến đổi. Khi không thể chứng minh chắc số và kiểu đối số phát sinh động, một **C wrapper có typed signature** là lựa chọn an toàn, rõ ràng và dễ kiểm thử hơn.

### Tài liệu chuẩn để kiểm tra

- Oracle, [JDK 22 Linker — Variadic functions](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): specialized forms, ví dụ `printf`, promotion và giới hạn native linker.
- Oracle, [JDK 22 Linker.Option — firstVariadicArg](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html#firstVariadicArg(int)): index [0,N], trường hợp không có extra argument, quy tắc calling convention.
- Oracle, [JDK 22 FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): return/argument layouts, MethodHandle Java carrier.
- Oracle, [JDK 22 SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): tìm C symbols và lifetime của thư viện.
- cppreference, [C default argument promotions](https://en.cppreference.com/w/c/language/conversion): integer promotions và float-to-double.
- cppreference, [C `va_arg`](https://en.cppreference.com/w/c/variadic/va_arg): cách đọc C variadic arguments đúng promoted type.
- cppreference, [C printf](https://en.cppreference.com/w/c/io/fprintf): format strings, đối số sau promotions và undefined behavior.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): FFM thành API chuẩn từ JDK 22.