# Hàm có số đối số biến đổi và lựa chọn Linker phù hợp với chữ ký native

Foreign Function & Memory API (FFM) cho phép Java gọi hàm native thông qua `Linker` và downcall `MethodHandle`. Với hàm C có số đối số biến đổi (*variadic function*), chẳng hạn `printf(const char *format, ...)`, Java cần mô tả chính xác từng đối số của một lần gọi cụ thể và đánh dấu vị trí bắt đầu phần variadic bằng `Linker.Option.firstVariadicArg(int)`.

JEP 454 đưa FFM API thành API chính thức từ Java 22. Các API được trình bày trong bài vẫn dùng được ở Java hiện đại. Điểm cần chú ý là `Linker` làm việc theo ABI của nền tảng đang chạy, còn `FunctionDescriptor` phải khớp với chữ ký C thực tế; riêng các variadic arguments phải được mô tả bằng kiểu sau khi C áp dụng default argument promotions.

## 1. Hàm variadic trong C là gì?

Một hàm C variadic có phần khai báo kết thúc bằng dấu ba chấm (`...`). Các tham số đứng trước dấu ba chấm là tham số cố định; phần sau cho phép caller truyền thêm số lượng và kiểu đối số khác nhau.

```c
int printf(const char *format, ...);
```

Trong khai báo này:

- `format` là tham số cố định, luôn nhận con trỏ đến chuỗi định dạng.
- Các đối số sau `format` là variadic arguments.
- Chuỗi định dạng quyết định cách `printf` diễn giải các đối số bổ sung.

Ví dụ:

```c
printf("count=%d, average=%.2f\n", 3, 12.5);
```

Lần gọi trên có ba đối số thực tế: một con trỏ chuỗi, một `int` và một `double`. Mặc dù khai báo C dùng `...`, một lần gọi cụ thể vẫn có một chữ ký hữu hạn và xác định.

## 2. FFM liên kết một lần gọi variadic đã được chuyên biệt hóa

Native linker không tạo một downcall handle có arity tùy ý để Java truyền vào bao nhiêu đối số cũng được. Thay vào đó, ứng dụng phải mô tả một lần gọi cụ thể bằng `FunctionDescriptor`:

1. Ghi layout của kiểu trả về.
2. Ghi layout của tất cả tham số cố định.
3. Ghi thêm một layout cho từng đối số variadic mà lần gọi này sẽ truyền.
4. Cung cấp `Linker.Option.firstVariadicArg(index)` để đánh dấu đối số đầu tiên thuộc phần variadic.

Ví dụ với `printf("count=%d, average=%.2f", 3, 12.5)` có chữ ký đã chuyên biệt hóa như sau:

```text
int printf(const char *format, int count, double average)
```

`FunctionDescriptor` tương ứng gồm layout trả về `int`, layout `ADDRESS` cho `format`, layout `JAVA_INT` cho `count` và layout `JAVA_DOUBLE` cho `average`.

### 2.1. Ý nghĩa của `firstVariadicArg`

`Linker.Option.firstVariadicArg(int index)` nhận chỉ số của layout đối số đầu tiên thuộc phần variadic trong `FunctionDescriptor`. Chỉ số bắt đầu từ `0` và chỉ tính các đối số, không tính layout trả về.

Đây là option dành cho downcall linkage request: Java gọi hàm variadic ở phía native. Nó không biến một upcall stub Java thành hàm variadic có arity tùy ý.

Giả sử descriptor có `N` argument layouts:

| Giá trị `index` | Ý nghĩa |
| --- | --- |
| `0` | Tất cả đối số trong descriptor đều là variadic. |
| `m`, với `0 < m < N` | Các đối số từ vị trí `m` đến `N - 1` là variadic. |
| `N` | Không có đối số variadic trong lần gọi này. |

Với `printf`, `format` ở vị trí `0` là tham số cố định; đối số variadic đầu tiên ở vị trí `1`. Vì vậy phải dùng `firstVariadicArg(1)`.

Luôn cung cấp option này khi liên kết hàm variadic, kể cả khi lần gọi không truyền đối số variadic nào. Ví dụ `printf("ready\n")` có một argument layout là `ADDRESS`, không có variadic argument; vẫn truyền `firstVariadicArg(1)` vì `N = 1`. Một số nền tảng có thể dùng calling convention khác cho hàm variadic ngay cả trong trường hợp không có đối số sau dấu `...`.

## 3. Chọn Linker theo ABI của native platform

ABI (*Application Binary Interface*) quy định cách hàm native nhận đối số, trả kết quả, sử dụng thanh ghi, căn chỉnh dữ liệu và biểu diễn các kiểu C. ABI phụ thuộc vào nền tảng, thường là tổ hợp hệ điều hành, kiến trúc CPU và quy ước của toolchain.

Với thư viện native tuân theo ABI C của máy đang chạy JVM, lấy linker bằng:

```java
Linker linker = Linker.nativeLinker();
```

`Linker.nativeLinker()` trả về linker cho ABI gắn với hệ điều hành và bộ xử lý nơi Java runtime đang chạy. Ứng dụng không chọn Linux ABI khi chạy trên Windows, hoặc lấy linker cho một tổ hợp OS/CPU khác để gọi chéo nền tảng. Thư viện native phải được xây dựng cho nền tảng và ABI tương thích với runtime.

Linker này phục vụ ABI native mà Java runtime hỗ trợ trên nền tảng hiện tại. Nếu một thư viện dùng calling convention riêng không tương thích với ABI đó, cần cung cấp một lớp wrapper native có chữ ký theo ABI được hỗ trợ rồi gọi wrapper từ Java.

Không nên tự giả định mọi kiểu C có cùng kích thước trên mọi hệ điều hành. Hãy dùng `canonicalLayouts()` của chính linker để tra layout mà ABI hiện tại dùng cho các kiểu C:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.util.Map;

Linker linker = Linker.nativeLinker();

Map<String, MemoryLayout> cLayouts = linker.canonicalLayouts();
MemoryLayout cInt = cLayouts.get("int");
MemoryLayout cLong = cLayouts.get("long");
MemoryLayout cSizeT = cLayouts.get("size_t");
```

Các native linker cung cấp canonical layout cho những kiểu C cơ bản như `bool`, `char`, `short`, `int`, `long`, `long long`, `float`, `double`, `size_t`, `wchar_t` và `void*`. Layout cụ thể phụ thuộc ABI. Ví dụ:

| Kiểu C | Linux/x64 phổ biến | Windows/x64 phổ biến |
| --- | --- | --- |
| `int` | `JAVA_INT` | `JAVA_INT` |
| `long` | `JAVA_LONG` | `JAVA_INT` |
| `long long` | `JAVA_LONG` | `JAVA_LONG` |
| `size_t` | `JAVA_LONG` | `JAVA_LONG` |
| `void*` | `ADDRESS` | `ADDRESS` |

Bảng chỉ minh họa các data model phổ biến. Khi viết code cần chạy trên nhiều ABI, hãy lấy layout từ `linker.canonicalLayouts()` thay vì sao chép các giả định về kích thước từ một máy phát triển. Ví dụ, C `long` thường có kích thước 64 bit trên Linux/x64 nhưng 32 bit trên Windows/x64. `size_t` thay đổi theo data model 32 bit hoặc 64 bit.

`Linker` còn cung cấp `defaultLookup()` để tìm các symbol trong một số thư viện native thường dùng và được nạp cùng Java runtime. Nếu hàm nằm trong thư viện riêng của ứng dụng, cần tạo `SymbolLookup` phù hợp với thư viện đó; linker vẫn phải tương thích với ABI của thư viện.

## 4. Ví dụ: gọi `printf` với các đối số variadic

Giả sử muốn gọi hàm C sau:

```c
int printf(const char *format, ...);

// Lần gọi cụ thể:
printf("count=%d, average=%.2f\n", 3, 12.5);
```

Java có thể liên kết và gọi hàm bằng FFM như sau:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.invoke.MethodHandle;

import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_DOUBLE;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public class VariadicPrintf {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MemorySegment printfAddress = linker.defaultLookup()
                .find("printf")
                .orElseThrow();

        FunctionDescriptor printfDescriptor = FunctionDescriptor.of(
                JAVA_INT,       // kiểu trả về: int
                ADDRESS,        // tham số cố định: const char *format
                JAVA_INT,       // variadic argument: int count
                JAVA_DOUBLE     // variadic argument: double average
        );

        MethodHandle printf = linker.downcallHandle(
                printfAddress,
                printfDescriptor,
                Linker.Option.firstVariadicArg(1)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment format = arena.allocateFrom(
                    "count=%d, average=%.2f\n"
            );

            int written = (int) printf.invokeExact(format, 3, 12.5d);
            System.out.println("printf wrote " + written + " characters");
        }
    }
}
```

Giải thích các phần quan trọng:

- `Linker.nativeLinker()` lấy linker của ABI native trên máy đang chạy.
- `defaultLookup().find("printf")` tìm địa chỉ symbol `printf` trong nhóm thư viện native mặc định. `orElseThrow()` báo lỗi nếu không tìm thấy symbol.
- `FunctionDescriptor.of(...)` mô tả kiểu trả về và toàn bộ đối số của lần gọi cụ thể. `ADDRESS` đại diện cho `const char*`; `JAVA_INT` và `JAVA_DOUBLE` tương ứng với hai đối số variadic trong ví dụ.
- `firstVariadicArg(1)` chỉ ra đối số ở vị trí `1` là đối số variadic đầu tiên. Vị trí `0` là `format`, một tham số cố định.
- `allocateFrom(...)` tạo chuỗi C có ký tự kết thúc null trong vùng nhớ do `Arena` quản lý. Chuỗi phải còn sống trong suốt thời gian gọi native function.
- `invokeExact` gọi downcall handle với kiểu trả về và kiểu đối số khớp chính xác với method type được tạo từ descriptor.

`printf` trả về số ký tự đã ghi (không tính ký tự null kết thúc chuỗi). Giá trị trả về được lưu trong `written` để minh họa việc ánh xạ kiểu trả về.

> Trong C, chuỗi định dạng và các đối số phải khớp nhau. Ví dụ `%d` yêu cầu một `int`, còn `%f` trong `printf` yêu cầu `double`. Sai kiểu hoặc sai số lượng đối số có thể dẫn đến hành vi không xác định ở phía C; linker không thể suy ra hay kiểm tra nội dung format string.

## 5. Default argument promotions trong C

Đối số truyền qua dấu `...` chịu quy tắc *default argument promotions* của C. Đây là một điểm quan trọng khi tạo `FunctionDescriptor`: native linker không tự chuyển kiểu Java hoặc layout sang kiểu đã được C promote.

Các chuyển đổi phổ biến gồm:

| Kiểu trước promotion | Kiểu sau promotion thường gặp |
| --- | --- |
| `float` | `double` |
| `_Bool` | `int` theo quy tắc integer promotion của C |
| `char` | `int` hoặc `unsigned int` theo khả năng biểu diễn của `int` |
| `short` | `int` hoặc `unsigned int` theo khả năng biểu diễn của `int` |

Với `char` và `short`, kiểu sau integer promotion phụ thuộc miền giá trị và cách biểu diễn của kiểu đích. Cần xác định kiểu C thực tế mà hàm nhận, không suy ra chỉ từ kiểu Java dùng để tạo dữ liệu ban đầu.

Ví dụ, nếu muốn truyền một giá trị Java `float` vào đối số variadic mà hàm C sẽ đọc bằng `va_arg(args, double)`, descriptor phải dùng `JAVA_DOUBLE` và Java phải truyền một giá trị `double`:

```java
double promoted = (double) 1.25f;
// Layout của đối số variadic phải là JAVA_DOUBLE.
```

Native linker từ chối các descriptor có layout variadic tương ứng với kiểu C chưa được promote. Tập layout bị từ chối có thể phụ thuộc nền tảng vì kích thước và miền giá trị của kiểu C là platform-dependent. Ví dụ, trên Linux/x64, các layout tương ứng với `_Bool`, `unsigned char`, `unsigned short` và `float` bị từ chối khi dùng làm variadic argument. Hãy dùng `canonicalLayouts()` để xác định layout C trên nền tảng đích và tự thực hiện promotion trước khi liên kết.

## 6. Mỗi MethodHandle có arity và kiểu đối số cố định

Hàm C có thể nhận nhiều dạng đối số, nhưng downcall `MethodHandle` được tạo từ một `FunctionDescriptor` có số lượng và kiểu đối số xác định. Ví dụ:

| Lần gọi C | Chữ ký chuyên biệt | Chỉ số đầu tiên variadic |
| --- | --- | --- |
| `printf("ready\n")` | `(char*) -> int` | `1` (descriptor có 1 đối số, không có varargs) |
| `printf("%d", 7)` | `(char*, int) -> int` | `1` |
| `printf("%d %.1f", 7, 2.5)` | `(char*, int, double) -> int` | `1` |

Nếu ứng dụng cần gọi cùng một hàm variadic với nhiều tổ hợp số lượng hoặc kiểu đối số, hãy tạo một downcall handle cho từng chữ ký chuyên biệt cần dùng. Không thể tạo một descriptor có dấu `...` rồi mong `invokeExact` tự nhận số lượng đối số bất kỳ.

Khi không có đối số variadic, option vẫn cần thiết. Trong ví dụ `printf("ready\n")`, descriptor chỉ có `ADDRESS`, do đó `N = 1` và chỉ số đầu tiên variadic là `1`.

## 7. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Không truyền `firstVariadicArg` | Native linker không biết ranh giới giữa tham số cố định và variadic. | Luôn truyền option này cho hàm variadic, kể cả khi không có varargs. |
| Dùng sai chỉ số | Index không trỏ đến layout của variadic argument đầu tiên. | Đếm argument layouts từ `0`; không tính return layout. |
| Bỏ layout của đối số variadic | Descriptor không mô tả đủ chữ ký của lần gọi cụ thể. | Thêm một layout cho mỗi đối số sẽ truyền. |
| Dùng layout của kiểu trước promotion | C áp dụng default argument promotions cho variadic arguments. | Chuyển giá trị sang kiểu promoted và mô tả bằng layout tương ứng. |
| Giả định C `long` luôn là Java `long` | Kích thước C `long` phụ thuộc ABI/data model. | Tra `linker.canonicalLayouts().get("long")`. |
| Dùng linker trên nền tảng không tương thích | Calling convention và layout có thể khác. | Dùng `Linker.nativeLinker()` và thư viện native được build cho cùng nền tảng/ABI. |
| Không khớp format string của `printf` | C diễn giải đối số sai kiểu hoặc sai số lượng. | Đảm bảo format specifier và promoted argument types khớp nhau. |
| Dùng sai địa chỉ hoặc chữ ký hàm | Native linker không thể tự kiểm tra chữ ký thực của symbol. | Đối chiếu header C, ABI và symbol; descriptor sai có thể làm JVM crash hoặc gây hỏng bộ nhớ. |

## 8. Quyền truy cập native và giới hạn an toàn

Các thao tác như `Linker.downcallHandle(...)` là restricted methods. Chúng cho phép Java gọi mã native, nhưng descriptor không thể được đối chiếu hoàn toàn với chữ ký thật của symbol. Nếu mô tả sai kiểu trả về, thứ tự đối số, số lượng đối số hoặc ABI, kết quả có thể không xác định, bao gồm crash JVM hoặc memory corruption.

Khi chạy ứng dụng trên classpath, bật quyền native access cho unnamed module:

```bash
java --enable-native-access=ALL-UNNAMED VariadicPrintf
```

Với ứng dụng dùng named module, cấp quyền native access cho module tương ứng theo cấu hình runtime. Chỉ cấp quyền cho module thật sự cần gọi native code.

Ngoài ra, hãy giữ các nguyên tắc sau:

- Chỉ gọi symbol có chữ ký đã được xác minh từ header hoặc tài liệu chính thức của thư viện.
- Dùng đúng ABI và canonical layouts của nền tảng đang chạy.
- Bảo đảm các `MemorySegment` chứa chuỗi, buffer hoặc pointer còn sống trong toàn bộ downcall.
- Không giả định native linker kiểm tra được format string hoặc số đối số mà hàm C đọc qua `va_arg`.
- Không dùng `Linker.Option.critical(...)` cho hàm variadic chỉ để tăng tốc; tùy chọn critical có hợp đồng thực thi riêng và không thay thế `firstVariadicArg(...)`.

## 9. Quy trình thực hiện

Khi cần gọi một hàm native variadic từ Java, có thể đi theo trình tự sau:

1. Đọc khai báo C và xác định ABI mà thư viện sử dụng.
2. Lấy `Linker` bằng `Linker.nativeLinker()` cho nền tảng hiện tại.
3. Tra các kiểu C cần thiết bằng `canonicalLayouts()`; dùng `ADDRESS` cho pointer.
4. Chuyên biệt hóa lần gọi: xác định tất cả tham số cố định và từng variadic argument sau default argument promotions.
5. Tạo `FunctionDescriptor` chứa return layout và toàn bộ argument layouts.
6. Đếm chỉ số từ `0` để truyền `Linker.Option.firstVariadicArg(index)`.
7. Tìm symbol, tạo downcall handle và gọi với method type khớp descriptor.
8. Quản lý vòng đời các segment và cấp quyền native access cho module cần thiết.

## Ghi nhớ

- `Linker.nativeLinker()` cung cấp linker cho ABI của OS và CPU nơi JVM đang chạy. Không thể dùng nó để chọn ABI của một nền tảng khác.
- `canonicalLayouts()` giúp ánh xạ các kiểu C theo ABI, tránh giả định `long` hoặc `size_t` có cùng kích thước trên mọi nền tảng.
- FFM liên kết một lần gọi variadic đã được chuyên biệt hóa bằng `FunctionDescriptor` có số lượng và kiểu đối số cố định.
- `Linker.Option.firstVariadicArg(index)` đánh dấu vị trí đầu tiên của variadic argument, tính từ `0` và không tính return layout. Phải truyền option này kể cả khi lần gọi không có variadic argument.
- Native linker không tự thực hiện C default argument promotions. Đối số variadic phải dùng kiểu và layout sau promotion, chẳng hạn `float` thành `double`.
- `downcallHandle` là restricted method; chữ ký hoặc ABI sai có thể gây lỗi nghiêm trọng ở JVM hoặc bộ nhớ native.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Java SE 22 API — `Linker`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 22 API — `Linker.Option`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Java SE 27 API — `Linker`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 27 API — `Linker.Option`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Java SE 27 API — `FunctionDescriptor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
