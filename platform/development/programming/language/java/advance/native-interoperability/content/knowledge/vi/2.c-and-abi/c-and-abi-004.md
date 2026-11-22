# Quy ước gọi hàm, truyền tham số và giá trị trả về trong C ABI

## 1. ABI quyết định điều gì khi gọi một hàm native?

Trong C, khai báo `int add(int a, int b);` cho biết **giao diện ở mức mã nguồn**: tên hàm, số lượng/thứ tự tham số và kiểu trả về. Khi chương trình đã được biên dịch, bên gọi (caller) và hàm được gọi (callee) còn phải tuân thủ một **Application Binary Interface (ABI)** để hiểu chính xác cùng một lời gọi.

ABI thường quy định:

- Tham số kiểu nguyên, dấu phẩy động, con trỏ và cấu trúc được đặt vào **thanh ghi nào** hoặc **vị trí nào trên stack**.
- Cách căn chỉnh stack, vùng nhớ dành sẵn cho callee, thanh ghi nào caller/callee phải bảo toàn.
- Vị trí nhận **giá trị trả về**; khi nào một `struct` được trả qua thanh ghi hoặc một con trỏ kết quả ngầm.
- Kích thước/căn chỉnh của kiểu C, bố cục `struct`, tên symbol và quy tắc liên kết với thư viện.

**Calling convention** là phần ABI nói riêng về trình tự gọi hàm, truyền đối số, dùng stack/thanh ghi và trả kết quả. ABI rộng hơn calling convention vì còn bao gồm biểu diễn dữ liệu, symbol, object file và các quy tắc liên kết.

Hai chương trình dùng cùng cú pháp C vẫn có thể **không tương thích ở mức nhị phân** nếu biên dịch cho ABI khác nhau. Phải xét cụ thể bộ ba **kiến trúc CPU + hệ điều hành + ABI/toolchain**; không có một quy tắc gọi hàm áp dụng cho mọi máy.

### 1.1. Các bước khái niệm của một lời gọi

1. **Caller** tính đối số, thực hiện chuyển đổi kiểu theo prototype, chuẩn bị thanh ghi/stack theo ABI và phát lệnh gọi.
2. **Callee** nhận tham số theo đúng quy tắc đó, lưu/phục hồi những thanh ghi bắt buộc phải bảo toàn và thực thi thân hàm.
3. **Callee** đặt kết quả vào vị trí ABI quy định (hoặc ghi vào vùng kết quả được caller cấp), rồi trở về.
4. **Caller** đọc kết quả, tiếp tục sử dụng các thanh ghi còn hợp lệ và giải phóng vùng stack do mình phụ trách.

Đây là mô hình khái niệm: trình biên dịch có thể tối ưu, inline, tail-call hoặc không tạo stack frame như sơ đồ thông thường. Các tối ưu đó không làm thay đổi **hợp đồng ABI** tại một biên gọi thực sự.

**Chú ý:** *thứ tự đánh giá các biểu thức đối số* trong C không được quy định chung là từ trái sang phải. Đừng nhầm vị trí truyền đối số của ABI với thứ tự tính các biểu thức ở mã C.

## 2. So sánh các quy ước phổ biến

Các quy tắc dưới đây là **khái quát cho tham số scalar thông thường**; `struct`, vector, biến thể ABI, hàm variadic và kiểu đặc biệt cần quy tắc phân loại riêng.

| Đích biên dịch | Tham số nguyên/con trỏ | Tham số `float`/`double` | Đặc điểm stack | Kết quả scalar thường gặp |
| --- | --- | --- | --- | --- |
| **x86-64 System V** (đa số Linux x86-64, macOS Intel) | Tối đa 6 thanh ghi: `RDI, RSI, RDX, RCX, R8, R9` | Tối đa 8 thanh ghi `XMM0–XMM7`, được phân bổ riêng với nhóm nguyên | Căn chỉnh theo ABI; có *red zone* 128 byte với điều kiện sử dụng cụ thể | Số nguyên/con trỏ thường ở `RAX`; dấu phẩy động ở `XMM0` |
| **Windows x64** (ABI mặc định của MSVC x64) | 4 vị trí đầu: `RCX, RDX, R8, R9` | `XMM0–XMM3` ứng với **vị trí đối số** 1–4 | Caller cấp ít nhất 32 byte *shadow space*; không dùng red zone như System V | Số nguyên/con trỏ thường ở `RAX`; dấu phẩy động ở `XMM0` |
| **AArch64 AAPCS64 cơ sở** (ARM 64-bit) | `x0–x7` | `v0–v7` | Stack 16-byte aligned tại các biên yêu cầu | Số nguyên thường ở `x0`/`x1`; dấu phẩy động thường ở `v0` |

Đừng suy luận rằng Windows on ARM64, Apple arm64 hoặc các nền tảng đặc thù có mọi chi tiết giống hệt AAPCS64 cơ sở. Quy tắc phân loại aggregate, variadic và ngoại lệ nền tảng phải xem tài liệu ABI của đúng target.

### 2.1. Ví dụ: cùng một prototype, hai cách truyền khác nhau

~~~c
int score(int count, double ratio, int bonus);
~~~

Giả sử lời gọi được biên dịch theo ABI mặc định và các đối số đều là scalar:

- **System V AMD64:** `count → EDI`, `ratio → XMM0`, `bonus → ESI`. Hai nhóm thanh ghi nguyên và dấu phẩy động được phân bổ tương đối độc lập.
- **Windows x64:** `count → ECX`, `ratio → XMM1`, `bonus → R8D`. `ratio` chiếm **vị trí đối số thứ hai**, nên dùng `XMM1` thay vì `XMM0`.
- **AAPCS64 cơ sở:** `count → w0`, `ratio → d0`, `bonus → w1`.

Giá trị trả về kiểu `int` thường ở `EAX` (x86-64) hoặc `w0` (AArch64). Đây là ví dụ minh họa vị trí thanh ghi, không phải mã assembly phải viết thủ công.

### 2.2. Caller-saved, callee-saved và stack

- **Caller-saved/volatile:** caller không được giả định giá trị còn nguyên sau lời gọi; nếu cần thì tự lưu.
- **Callee-saved/nonvolatile:** nếu callee sử dụng/thay đổi thanh ghi thuộc nhóm này, nó phải phục hồi giá trị trước khi trả về.
- **Stack alignment:** ABI có ràng buộc căn chỉnh stack tại điểm gọi/nhập hàm; mã assembly tự viết sai alignment có thể gây lỗi với lệnh SIMD hoặc mã compiler tạo ra.
- **Stack arguments:** khi không đủ thanh ghi, tham số có thể được truyền qua stack. Vị trí cụ thể còn phụ thuộc phân loại kiểu và ABI, không chỉ phụ thuộc số lượng đối số.
- **Windows x64 shadow space:** 32 byte được caller chuẩn bị ngay cả khi hàm không dùng hết bốn tham số đăng ký; callee có thể dùng để lưu chúng.
- **System V red zone:** vùng 128 byte dưới `RSP` có thể được một số mã userspace tận dụng theo quy tắc ABI; không được mang giả định này sang Windows hoặc code chạy trong kernel.

Trên **x86 32-bit**, các quy ước lịch sử như `__cdecl` (thường caller dọn tham số trên stack) và `__stdcall` (thường callee dọn) có thể khác nhau; sai quy ước có thể làm lệch stack. Trên Windows x64, quy ước gọi mặc định đã được chuẩn hóa hơn, nên không thể áp cách lý giải `__stdcall` 32-bit một cách máy móc.

## 3. Truyền tham số trong C: giá trị, con trỏ và mảng

**C luôn truyền tham số theo giá trị.** Một tham số `int` nhận bản sao của số nguyên; một tham số `Point` nhận giá trị cấu trúc (về mặt ngữ nghĩa); một tham số `Point *` nhận **bản sao của địa chỉ**. “Truyền con trỏ” cho phép sửa dữ liệu mà nó trỏ tới, nhưng không biến bản thân biến con trỏ của caller thành tham số truyền tham chiếu.

~~~c
void update(int x, int *p) {
    x = 100;       // Chỉ thay đổi bản sao x
    if (p != NULL) {
        *p = 200;  // Thay đổi đối tượng mà caller đã truyền địa chỉ
    }
}
~~~

Đoạn trên minh họa ngữ nghĩa, chưa phải chương trình độc lập. Nếu caller có `int a = 1, b = 2;` và gọi `update(a, &b);`, sau lời gọi `a` vẫn là `1`, `b` thành `200`.

Các điểm dễ nhầm:

- `T *` là một **đối số con trỏ truyền theo giá trị**; `T **` cho phép hàm nhận địa chỉ biến con trỏ của caller và thay đổi con trỏ đó.
- Tham số khai báo `int items[]` trong prototype hàm được điều chỉnh thành `int *items`; kích thước mảng không tự đi theo. Giao diện thực tế nên có thêm `size_t count` hoặc `size_t capacity`.
- `const T *` giới hạn thao tác qua con trỏ đó trong mã C, **không tự bảo đảm** vùng nhớ có lifetime đủ dài hoặc thread-safe.
- `NULL`/con trỏ null chỉ hợp lệ nếu hợp đồng hàm cho phép. Native code dereference null thường gây lỗi ở mức tiến trình.
- C không quy định một quy tắc sở hữu bộ nhớ chung: phải tự thỏa thuận bên nào cấp phát, được sửa, giữ con trỏ bao lâu và giải phóng bằng API nào.

### 3.1. Truyền và trả `struct` theo giá trị: ví dụ C11 chạy được

Lưu thành **`point.c`**:

~~~c
#include <stdio.h>

typedef struct {
    int x;
    int y;
} Point;

static Point moved(Point p, int dx, int dy) {
    p.x += dx;
    p.y += dy;
    return p;
}

static void move_in_place(Point *p, int dx, int dy) {
    if (p != NULL) {
        p->x += dx;
        p->y += dy;
    }
}

int main(void) {
    Point p = {1, 2};
    Point q = moved(p, 3, 4);
    move_in_place(&p, -1, 2);

    printf("p=(%d,%d), q=(%d,%d)\n", p.x, p.y, q.x, q.y);
    return 0;
}
~~~

Biên dịch/chạy với GCC hoặc Clang (Linux/macOS):

~~~bash
cc -std=c11 -Wall -Wextra -pedantic point.c -o point
./point
~~~

Windows với **Developer Command Prompt** có MSVC:

~~~powershell
cl /W4 point.c
.\point.exe
~~~

Kết quả stdout trên cả hai trường hợp:

~~~text
p=(0,4), q=(4,6)
~~~

Giải thích: `moved` nhận bản sao của `p`, thay đổi bản sao rồi **trả một `Point` theo giá trị** để khởi tạo `q`. Hàm `move_in_place` nhận địa chỉ của `p` và sửa trực tiếp đối tượng gốc. Việc compiler truyền hoặc nhận `Point` qua thanh ghi hay bộ nhớ là chi tiết ABI; tính đúng đắn ở mức C của ví dụ không phụ thuộc vào lựa chọn đó.

## 4. Cách ABI truyền `struct`, union và kiểu phức hợp

Không thể suy từ câu “`struct` lớn thì luôn truyền qua stack” thành một quy luật chung.

- Ở **System V AMD64**, các nhóm 8-byte của aggregate được phân loại (`INTEGER`, `SSE`, `MEMORY`, …); cấu trúc nhỏ có thể đi qua nhiều thanh ghi, còn trường hợp khác phải đi qua bộ nhớ.
- Ở **Windows x64**, nhiều aggregate nhỏ phù hợp điều kiện được truyền như số nguyên cùng cỡ; các aggregate không đạt điều kiện được truyền gián tiếp bằng con trỏ đến vùng tạm do caller cấp. Một đối số không được chia qua nhiều thanh ghi như quy tắc SysV.
- Ở **AArch64**, cách truyền phụ thuộc kích thước, bố cục và phân loại aggregate, kể cả quy tắc riêng cho *homogeneous floating-point aggregates* ở những ABI áp dụng.

### 4.1. Bố cục bộ nhớ là một phần của hợp đồng

~~~c
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t kind;
    uint32_t value;
} Packet;

// Khi debug, kiểm tra trên đúng target:
// sizeof(Packet), _Alignof(Packet), offsetof(Packet, value)
~~~

Trên nhiều ABI phổ biến, `value` nằm sau phần **padding** để căn chỉnh, do đó không thể suy rằng `sizeof(Packet) == 5`. Các kích thước và offset phải được đo/khẳng định theo target thực tế, không dựa vào số byte cộng tay.

Khi trao đổi cấu trúc qua FFI:

1. Đồng bộ **khai báo header C**, kích thước từng field, thứ tự, alignment, padding và luật truyền/return aggregate.
2. Dùng `sizeof`, `_Alignof`, `offsetof` hoặc static assertion phù hợp để kiểm chứng; kiểm tra cả biến thể 32/64-bit.
3. Hạn chế mang trực tiếp **bit-field, union phức tạp, flexible array member, C++ class, `long double`, vector** qua biên FFI nếu không mô hình hóa đúng ABI.
4. Không tùy tiện thêm `#pragma pack` hoặc thuộc tính `packed`: packing thay đổi alignment/layout và có thể gây truy cập không căn chỉnh.
5. Cùng một `struct` *by value* có thể được truyền bằng phương thức khác một con trỏ tới `struct`. Đổi `Point` thành `Point *` làm **thay đổi signature/ABI**, không phải tối ưu nội bộ.

## 5. Giá trị trả về và tham số kết quả ẩn

| Khai báo C | Ý nghĩa ở mức C | Cách ABI thường hiện thực |
| --- | --- | --- |
| `int f(void)` | Trả scalar nguyên | Thanh ghi kết quả nguyên (ví dụ `EAX` trên x86-64) |
| `double f(void)` | Trả scalar dấu phẩy động | Thanh ghi dấu phẩy động (ví dụ `XMM0` hoặc `v0`) |
| `void *f(void)` | Trả bản sao giá trị con trỏ | Thanh ghi kết quả con trỏ; lifetime và ownership do API quy định |
| `void f(int *out)` | Không trả giá trị C; ghi qua con trỏ được truyền vào | `out` là tham số thông thường; caller cấp vùng nhớ |
| `Big f(void)` | Trả `struct Big` **theo giá trị** | Có thể qua thanh ghi, hoặc vùng kết quả caller cấp và một tham số địa chỉ *ngầm* (*sret*) |

**Hidden sret pointer:** Với một số kiểu trả về aggregate, caller chuẩn bị bộ nhớ kết quả và ABI sắp xếp truyền địa chỉ của vùng đó theo một quy tắc đặc biệt. Địa chỉ ngầm có thể làm dịch chuyển vị trí các tham số hiển thị. Tuy nhiên, đây là **cách compiler hạ thấp lời gọi**, không đồng nghĩa việc bạn được tự đổi prototype C thành `void f(Big *out)` rồi cho rằng tương thích nhị phân. Muốn bảo đảm ABI ổn định, hãy công khai thiết kế out-parameter ngay trong API C.

### 5.1. Phân biệt con trỏ kết quả và dữ liệu được trỏ

~~~c
// Ví dụ hợp đồng C minh họa:
int read_value(int32_t *out_value);  // 0: thành công; mã khác 0: lỗi
char *make_text(void);               // Cần quy định ai free và dùng hàm nào
const char *current_text(void);      // Cần quy định pointer còn hiệu lực đến lúc nào
~~~

- Không trả địa chỉ biến local tự động: `return &local;` tạo con trỏ vô hiệu khi hàm kết thúc.
- Trả con trỏ đến bộ nhớ cấp phát động chỉ an toàn nếu caller có API giải phóng phù hợp, tốt nhất qua chính thư viện đã cấp phát.
- Con trỏ trả về có thể chỉ hợp lệ đến **lần gọi tiếp theo**, đến khi **arena** đóng, hoặc cho đến khi object native bị giải phóng; phải ghi rõ hợp đồng.
- Khi cần báo lỗi và trả dữ liệu, **status code + out-parameter** thường rõ nghĩa hơn một sentinel dễ nhầm, ví dụ con trỏ null hoặc `-1` vốn có thể là kết quả hợp lệ.

## 6. Variadic và chuyển đổi tham số mặc định

Với hàm khai báo `...` như `printf`, các đối số thuộc phần variadic chịu **default argument promotions**:

- `float` được nâng thành `double`.
- `char`, `short` và một số kiểu nguyên hẹp được *integer promotion* thành `int` hoặc `unsigned int` theo quy tắc C.
- Callee phải đọc các kiểu đã promotion. Chọn sai format trong `printf` hoặc đọc sai kiểu với `va_arg` là **undefined behavior**.

~~~c
#include <stdio.h>

int main(void) {
    float rate = 1.25f;
    printf("%.2f\n", rate);  // printf nhận double sau default promotion
    return 0;
}
~~~

Stdout:

~~~text
1.25
~~~

ABI cho lời gọi variadic còn có chi tiết riêng: ví dụ **Windows x64** nhân đôi giá trị floating-point vào thanh ghi nguyên tương ứng ở vị trí variadic; **System V AMD64** dùng thông tin số thanh ghi vector đã dùng theo quy ước của ABI. Một binding FFM gọi hàm variadic cần khai báo lựa chọn/ranh giới variadic phù hợp; **đừng** chỉ sao chép descriptor của hàm có các tham số cố định.

Ưu tiên wrapper C có **signature cố định, không variadic** khi thiết kế API cho Java hoặc ngôn ngữ khác.

## 7. Kiểu dữ liệu và cách biểu diễn tại ranh giới ABI

Không được suy rằng kiểu Java trùng với tên kiểu C:

| Kiểu/hợp đồng C | Điều cần kiểm tra khi binding |
| --- | --- |
| `int` | Thường 32 bit trên các nền tảng x86-64/AArch64 hiện đại; C chuẩn không bảo đảm mọi target là 32 bit |
| `long` | **LP64** (Linux/macOS 64-bit phổ biến): thường 64 bit; **LLP64** (Windows x64): 32 bit |
| `long long` | Ít nhất 64 bit, thường 64 bit; xác nhận theo ABI khi cần |
| `int32_t`, `uint64_t` | Có độ rộng xác định khi kiểu này tồn tại; chú ý signed/unsigned và miền giá trị ở phía Java |
| `size_t`, `ptrdiff_t` | Phụ thuộc data model/độ rộng địa chỉ; không mặc định tương đương Java `int` |
| `float`, `double` | Cần đúng kích thước, phân loại ABI và kiểu kết quả; không được hoán đổi chỉ vì đều là số thực |
| `void *`, `T *` | Địa chỉ native; **không** phải Java reference; cần kiểm tra null, alignment, lifetime và phạm vi bộ nhớ |
| `char *` | Trỏ tới byte; phải quy định encoding, độ dài và có/không có byte NUL kết thúc |
| `_Bool`, `enum`, bit-field | Phải xét kích thước/định dạng do ABI, compiler và kiểu enum cụ thể quyết định |

Đặc biệt, **Java `char` là đơn vị UTF-16 16 bit**, còn C `char` là một đơn vị byte địa chỉ hóa (thông thường 8 bit trên các target đang xét). Đừng map chuỗi Java trực tiếp sang `char *`; cần vùng nhớ native chứa mã hóa đã chọn, thường UTF-8 với byte NUL kết thúc nếu API C yêu cầu C string.

Khi serialize dữ liệu vào buffer byte để chia sẻ, còn phải xác định **endianness** và biểu diễn nhị phân. Truyền một `int` đúng qua ABI không tương đương việc tự chép byte theo thứ tự bất kỳ.

## 8. Ví dụ end-to-end: Java gọi hàm C bằng FFM (JDK 22+)

Foreign Function & Memory API (FFM) là API chính thức từ **JDK 22**. `Linker.nativeLinker()` nắm quy tắc gọi hàm native theo ABI của nền tảng; `FunctionDescriptor` mô tả kiểu tham số/giá trị trả về. Ví dụ sau dùng signature **cố định** chỉ có hai số nguyên 32-bit để tập trung vào calling convention.

### 8.1. Viết thư viện C

Lưu thành **`abidemo.c`**:

~~~c
#include <stdint.h>

#if defined(_WIN32)
#  define API_EXPORT __declspec(dllexport)
#else
#  define API_EXPORT __attribute__((visibility("default")))
#endif

API_EXPORT int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}
~~~

Hàm export có tên C là `add_i32`, nhận hai giá trị `int32_t` và trả `int32_t`. Ví dụ chỉ sử dụng giá trị nhỏ để tránh tràn số nguyên có dấu. Macro `API_EXPORT` xử lý xuất symbol trên các toolchain minh họa.

Biên dịch thư viện cho **đúng hệ điều hành/kiến trúc đang chạy JVM**:

~~~bash
# Linux: cần GCC/Clang
cc -std=c11 -O2 -fPIC -shared abidemo.c -o libabidemo.so

# macOS: dùng lệnh tương ứng thay cho lệnh Linux
cc -std=c11 -O2 -dynamiclib abidemo.c -o libabidemo.dylib
~~~

Trên Windows, chạy trong **x64 Native Tools Command Prompt for VS**:

~~~powershell
cl /LD /W4 abidemo.c /Fe:abidemo.dll
~~~

Chỉ chạy **một** lệnh phù hợp với nền tảng. Đặt thư viện tạo ra trong thư mục chạy Java ở bước tiếp theo.

### 8.2. Viết Java 22+

Lưu thành **`FfmDemo.java`**:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class FfmDemo {
    public static void main(String[] args) throws Throwable {
        System.loadLibrary("abidemo");

        MemorySegment symbol = SymbolLookup.loaderLookup()
                .find("add_i32")
                .orElseThrow();

        MethodHandle add = Linker.nativeLinker().downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,  // int32_t return (target ở ví dụ)
                        ValueLayout.JAVA_INT,  // int32_t a
                        ValueLayout.JAVA_INT   // int32_t b
                )
        );

        int answer = (int) add.invokeExact(20, 22);
        System.out.println(answer);
    }
}
~~~

Biên dịch và chạy với **JDK 22+**, từ thư mục chứa `FfmDemo.java` và thư viện native:

~~~bash
javac FfmDemo.java
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. FfmDemo
~~~

Stdout mong đợi:

~~~text
42
~~~

Giải thích từng bước:

1. `System.loadLibrary("abidemo")` nạp file có tên thích hợp theo OS (`libabidemo.so`, `libabidemo.dylib` hoặc `abidemo.dll`).
2. `SymbolLookup.loaderLookup()` tìm địa chỉ symbol `add_i32` từ thư viện đã nạp bằng cơ chế gắn với class loader.
3. `FunctionDescriptor.of(returnLayout, arg1Layout, arg2Layout)` cung cấp **đúng số lượng, thứ tự và kiểu ABI**; `ValueLayout.JAVA_INT` có độ rộng 32 bit tương ứng với `int32_t` trong target minh họa.
4. `Linker.nativeLinker().downcallHandle(...)` tạo `MethodHandle` thực hiện chuyển tiếp Java → C theo calling convention của hệ thống.
5. `invokeExact(20, 22)` yêu cầu method type chính xác `(int, int) -> int`; phép cộng native trả `42`.

**Giới hạn môi trường:** JDK 17 không có phiên bản FFM chính thức như ví dụ JDK 22. Lệnh `--enable-native-access=ALL-UNNAMED` cho phép các thao tác native bị hạn chế từ unnamed module. Nếu không tìm thấy thư viện hoặc symbol, JVM sẽ báo lỗi nạp/tìm symbol; nếu descriptor sai nhưng vẫn được liên kết, hậu quả có thể là dữ liệu sai hoặc crash JVM.

### 8.3. Nếu tham số là con trỏ/`struct`

Ví dụ này cố ý chỉ dùng scalar. Với `const uint8_t *data, size_t length`, binding còn phải:

- Truyền địa chỉ native đúng qua `ValueLayout.ADDRESS` và bảo đảm vùng dữ liệu sống trong suốt lời gọi.
- Chọn layout cho `size_t` **theo ABI** (FFM cung cấp `Linker.nativeLinker().canonicalLayouts()` để tra các kiểu C); không hard-code `JAVA_LONG` trên mọi target.
- Nếu có `struct` by value hoặc được return by value, khai báo `MemoryLayout` đúng field/padding và để native linker áp quy tắc aggregate, kể cả vùng return ngầm nếu cần.
- Không giải phóng `Arena` đang chứa buffer hoặc upcall stub khi native code vẫn giữ và có thể truy cập địa chỉ đó.

## 9. JNI và FFM không có cùng signature tại ranh giới C

Đối với Java 17 hoặc dự án dùng JNI, một phương thức như:

~~~java
public final class NativeCalc {
    public static native int add(int a, int b);
}
~~~

có entry point JNI theo **header do `javac -h` sinh**, về mặt khái niệm có dạng:

~~~c
JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *env, jclass clazz, jint a, jint b);
~~~

Đây là **mẫu chữ ký minh họa**, chưa phải file JNI đầy đủ có thể link độc lập. Phương thức `static native` nhận tham số ngầm `JNIEnv *` và `jclass`; phương thức instance dùng `jobject` thay `jclass`. `JNIEXPORT` và `JNICALL` là macro của JNI, phụ thuộc nền tảng/toolchain. Tên symbol có quy tắc mã hóa riêng và có thể khác ví dụ khi dùng package, overload hoặc phiên bản cơ chế liên kết khác; dùng **header được sinh thực tế**.

Không lấy prototype JNI này gán trực tiếp cho descriptor FFM của hàm C thuần `int32_t add_i32(int32_t, int32_t)`. Cả **số tham số ngầm** lẫn **hợp đồng runtime/ownership** đều khác.

## 10. Thiết kế giao diện native ổn định và dễ kiểm thử

Một API C rõ ràng cho ranh giới Java ↔ native có thể được thiết kế như sau (**khai báo giao diện, không phải chương trình hoàn chỉnh**):

~~~c
#include <stddef.h>
#include <stdint.h>

// 0: thành công; khác 0: lỗi.
// data trỏ tới n phần tử int32_t có thể đọc được.
// out_sum trỏ tới vùng int64_t có thể ghi được; không được NULL.
int32_t sum_i32(const int32_t *data, size_t n, int64_t *out_sum);
~~~

Lựa chọn thiết kế này giúp kiểm soát:

- **Độ rộng và thứ tự:** `int32_t`/`int64_t` rõ hơn `long`; `size_t` vẫn phải map theo data model thực tế.
- **Dữ liệu trả về:** status được trả bằng scalar, kết quả lớn/khác kiểu được ghi vào vùng `out_sum` do caller cung cấp.
- **Lifetime:** caller cấp `data` và `out_sum`; callee không giữ địa chỉ sau khi trả về nếu hợp đồng không cho phép.
- **Lỗi:** tài liệu hóa mã lỗi và tránh ném C++ exception xuyên qua biên C/FFI.
- **Độ ổn định:** thay đổi kiểu, thứ tự, số tham số hoặc kiểu return của symbol đã public có thể phá ABI dù vẫn giữ nguyên tên hàm.

Với C++ implementation, cung cấp lớp export `extern "C"` cho API C để tránh name mangling C++ (điều này **không** tự biến bố cục C++ class thành layout C ổn định). Khi cần callback từ native vào Java, phải tạo upcall/JNI bridge có signature phù hợp và bảo đảm thread, lifetime, cách báo lỗi đúng với cơ chế callback.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tham số nhận giá trị lạ, đặc biệt khi trộn `int` và `double` | Dùng nhầm ABI hoặc vị trí register; descriptor FFM sai thứ tự/kiểu | So lại prototype C thực tế, target ABI, `FunctionDescriptor` và ví dụ register tương ứng |
| Trả về `struct` hỏng hoặc crash | Mô tả aggregate sai; bỏ qua hidden result/packing/alignment | Xác nhận `sizeof`, `offsetof`, return classification; cân nhắc wrapper C dùng out-parameter |
| Chạy Linux đúng, Windows x64 sai | Giả định C `long` luôn 64 bit hoặc dùng convention SysV trên Windows | Đối chiếu LP64/LLP64 và dùng canonical layouts của linker |
| Crash sau khi hàm trả về | Native giữ con trỏ vào buffer/arena đã hết lifetime hoặc trả địa chỉ biến local | Công khai lifetime/ownership; kéo dài scope hay copy dữ liệu theo đúng hợp đồng |
| Trả text lỗi dấu hoặc bị cắt | Nhầm Java UTF-16 với `char *`, thiếu encoding/length/NUL | Chọn UTF-8, định rõ độ dài và ai giải phóng vùng chuỗi |
| Lỗi chỉ xuất hiện ở variadic | Sai default promotions/`va_arg`/quy tắc variadic của ABI | Dùng wrapper signature cố định và kiểm chứng từng kiểu |
| `UnsatisfiedLinkError`, không tìm thấy symbol | Sai tên thư viện, đường dẫn, architecture, export hoặc name mangling | Kiểm tra file thực tế, symbol export và target architecture; với JNI dùng header do `javac -h` sinh |

**Quy trình debug thực dụng:**

1. Ghi rõ OS, CPU architecture, compiler/toolchain, JDK, đường dẫn thư viện và target ABI.
2. Lấy **header C thực sự được biên dịch** và bản khai báo FFM/JNI; so signature theo thứ tự, kiểu trả về, signedness và số lượng tham số.
3. Kiểm tra kích thước/layout bằng `sizeof`, `_Alignof`, `offsetof` và một test native nhỏ trên từng target.
4. Dùng công cụ symbol phù hợp (`nm -D`/`readelf` trên ELF, `nm` trên Mach-O, `dumpbin /exports` trên PE) để kiểm tra export; không suy tên C++ symbol.
5. Tách vấn đề ABI khỏi vấn đề ownership: test trước với hai scalar như `add_i32`, sau đó mới thêm pointer, buffer, struct hoặc callback.
6. Có thể xem assembly/disassembly khi cần, nhưng dựa trên **đặc tả ABI**, không suy quy tắc tổng quát từ một phiên bản compiler hoặc mức tối ưu duy nhất.

## 12. Tự kiểm tra hiểu bài

1. Vì sao cùng một `score(int, double, int)` dùng `XMM0` cho `double` trên SysV AMD64 nhưng dùng `XMM1` trên Windows x64?
2. Khi `void set(int *p)` sửa `*p`, C đang truyền tham chiếu hay truyền bản sao của con trỏ?
3. Vì sao đổi kiểu tham số từ `int32_t` sang `long` có thể làm hỏng binding trên Windows x64?
4. Vì sao một `struct` trả về theo giá trị **không** thể tự ý map thành con trỏ trả về ở lớp binding?
5. Java FFM phải biết những gì ngoài địa chỉ của symbol để gọi đúng hàm C? Buffer/con trỏ cần hợp đồng lifetime nào?
6. Vì sao `printf("%f", 1.25f)` hợp lệ về kiểu variadic nhưng descriptor tương tự cho một hàm nhận `float` cố định lại sai?

**Đáp án ngắn:** (1) SysV phân bổ nhóm nguyên và FP riêng, còn Windows x64 gắn XMM với vị trí đối số; (2) bản sao giá trị địa chỉ; (3) `long` 32 bit trong LLP64 nhưng thường 64 bit ở LP64; (4) aggregate return chịu phân loại ABI và có thể dùng sret ngầm; (5) descriptor đúng kiểu/thứ tự/return và vùng nhớ còn sống; (6) varargs nâng `float` thành `double`, tham số cố định kiểu `float` thì không.

## Tài liệu đối chiếu

- [Microsoft: x64 calling convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170) — tham số, shadow space, kết quả và register preservation trên Windows x64.
- [Arm: Procedure Call Standard for AArch64 (AAPCS64)](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst) — quy ước cho AArch64 và các nhóm aggregate.
- [Oracle JDK 22: Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html) — `Linker`, `FunctionDescriptor`, `SymbolLookup`, `Arena`.
- [Oracle JDK 22: Calling a C Library Function with FFM](https://docs.oracle.com/en/java/javase/22/core/calling-c-library-function-foreign-function-and-memory-api.html) — quy trình Java → native và mô tả signature.
