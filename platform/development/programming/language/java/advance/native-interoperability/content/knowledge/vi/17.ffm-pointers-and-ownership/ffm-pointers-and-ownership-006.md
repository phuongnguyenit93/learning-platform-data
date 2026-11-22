# Con trỏ và sở hữu — Xử lý tham số đầu ra, con trỏ kép và vùng đệm do thư viện điền

## 1. Vì sao tham số đầu ra không thể xử lý như giá trị Java thông thường?

Trong Java, khi gọi một method trả `int`, kết quả thường nằm ở giá trị `return`. Nhiều thư viện C lại dùng **tham số đầu ra (output parameters)**: hàm trả về mã trạng thái, còn giá trị thực được ghi qua địa chỉ mà caller truyền vào.

Ba mẫu C rất phổ biến:

```c
// [out] Giá trị nguyên: caller truyền địa chỉ một ô int.
int get_answer(int *out);

// [out] Con trỏ: caller truyền địa chỉ của một biến con trỏ.
int create_payload(unsigned char **out_data, size_t *out_count);

// [out] Vùng đệm caller cấp: thư viện ghi vào một dải byte cho sẵn.
int fill_message(char *buffer, size_t capacity, size_t *required);
```

Nếu chỉ đọc **giá trị trả về** của các hàm trên, Java sẽ bỏ sót kết quả. Với Foreign Function & Memory (FFM) API, Java phải cấp phát `MemorySegment` đúng kích thước/alignment, chuyển **địa chỉ native của segment** cho C, gọi `MethodHandle`, rồi đọc những byte được C ghi.

Điểm quan trọng nhất: **biết C đã ghi địa chỉ nào chưa đủ; phải biết ai sở hữu memory mà địa chỉ đó trỏ tới, kích thước hợp lệ là bao nhiêu, và khi nào phải giải phóng.** Nhầm quyền sở hữu (ownership) có thể dẫn tới rò rỉ bộ nhớ, double-free, use-after-free hoặc crash toàn JVM.

Bài dựa trên **FFM chính thức trong JDK 22+** (JEP 454). Ví dụ đã kiểm tra với **OpenJDK 24**. Ở JDK 21, FFM vẫn là preview API (JEP 442), phải dùng `--enable-preview` và một số tên API có thể khác; không áp trực tiếp toàn bộ source JDK 22+ vào JDK 21 mà không đối chiếu.

## 2. Phân biệt `T*`, `T**` và buffer

### 2.1. Tham số dạng `int *out`

```c
int read_value(int *out) {
    if (out == NULL) return -1;
    *out = 42; // Ghi vào ô nhớ mà caller đã cấp phát.
    return 0;
}
```

Lúc gọi, C nhận một **địa chỉ của ô `int`**. Caller vẫn sở hữu ô nhớ. Trong Java FFM:

```java
MemorySegment out = arena.allocate(ValueLayout.JAVA_INT);
int status = (int) readValue.invokeExact(out);
if (status != 0) throw new IllegalStateException("Native call failed");
int value = out.get(ValueLayout.JAVA_INT, 0); // 42
```

Đây là snippet minh họa, giả định đã có `arena` và `MethodHandle readValue` đúng ABI. `int*` **được mô tả bằng `ValueLayout.ADDRESS` ở FunctionDescriptor**, vì tham số nhận là con trỏ; riêng ô nhớ được cấp phát bằng `JAVA_INT`.

### 2.2. Tham số dạng `char **out` hoặc `T **out`

```c
int get_label(const char **out) {
    static const char label[] = "ready";
    if (out == NULL) return -1;
    *out = label; // Ghi một ĐỊA CHỈ vào ô nhớ caller cung cấp.
    return 0;
}
```

Ở đây có **hai tầng**:

```text
Java/C caller
   │
   └──► slot chứa con trỏ (địa chỉ của biến char*)
                    │  thư viện ghi *out = some_address
                    ▼
              địa chỉ một vùng dữ liệu
                    │
                    └──► các byte/ký tự mà thư viện sở hữu hoặc mượn
```

Trong Java FFM, cấp phát **một slot kiểu ADDRESS**, chứ **không** chỉ cấp phát `JAVA_BYTE`:

```java
MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
pointerSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
int rc = (int) getLabel.invokeExact(pointerSlot);
MemorySegment resultAddress = pointerSlot.get(ValueLayout.ADDRESS, 0);
```

Snippet chỉ giải thích cơ chế: `getLabel` phải được liên kết với chữ ký C thích hợp trước khi chạy. `resultAddress` là con trỏ trỏ tới **dữ liệu đích**, không phải bản copy dữ liệu. Dữ liệu đó có thể **borrowed/static**, **caller-owned**, hoặc **newly allocated/native-owned**; cách giải phóng phụ thuộc hợp đồng API, không thể suy từ hai dấu sao `**`.

### 2.3. Tham số dạng `char *buf, size_t cap`

```c
int fill_message(char *buf, size_t cap, size_t *required);
```

Thư viện được phép ghi tối đa `cap` byte vào memory mà caller cấp. `required` có thể là số byte thực sự đã ghi, hoặc kích thước cần có, **tùy đặc tả của thư viện**. Phải đọc đúng hợp đồng: kích thước được tính bằng **byte**, phần tử, UTF-16 code units hay có bao gồm byte NUL kết thúc không?

```text
Java cấp buf 6 byte: [_ _ _ _ _ _]
                   │
           fill_message(buf, 6, &required)
                   │
                   ▼
                   ['h' 'e' 'l' 'l' 'o' '\0']
                                         ↑
                               NUL kết thúc C string
```

Trong mẫu này, bộ nhớ thuộc **Arena của Java**. Native code **chỉ ghi**, không được `free(buf)`, không giữ `buf` sau khi Java đóng arena, trừ khi API công bố một giao thức giữ pointer rõ ràng.

## 3. Bảng ánh xạ C ABI ↔ Java FFM

| C declaration | Ý nghĩa | Layout hoặc bộ nhớ bên Java |
| --- | --- | --- |
| `int` | Số nguyên 32 bit trên ABI ví dụ | `ValueLayout.JAVA_INT` |
| `int *out` | Địa chỉ ô nguyên 32 bit caller cấp | Tham số `ValueLayout.ADDRESS`; cấp slot `arena.allocate(JAVA_INT)` |
| `char *dst` | Địa chỉ dãy byte | Tham số `ADDRESS`; cấp buffer theo **byte capacity** |
| `char **out` | Địa chỉ ô chứa một pointer | Tham số `ADDRESS`; cấp slot `arena.allocate(ADDRESS)` |
| `void **out` | Địa chỉ ô chứa con trỏ không định kiểu | `ADDRESS` + slot `ADDRESS`; cần biết kiểu/kích thước đích trước khi dereference |
| `size_t` | Kích thước không dấu, tùy ABI | **X64 trong bài:** `JAVA_LONG` 64 bit; cần đối chiếu ABI khi port |
| `size_t *len` | Địa chỉ ô độ dài | Tham số `ADDRESS`; cấp slot `JAVA_LONG` trên x64 |
| `const char *input` | Chuỗi/bytes đầu vào thường borrowed | `arena.allocateFrom("text")` tạo UTF-8 C string trên JDK 22+ |
| `wchar_t *output` trên Windows | Buffer ký tự UTF-16 do Windows điền | `JAVA_CHAR` 2 byte × số **UTF-16 code units** |

Hai cột “layout của tham số” và “layout của dữ liệu được trỏ tới” **khác nhau**. Ví dụ `int*` có tham số FFM `ADDRESS`, nhưng segment mà nó trỏ tới phải có ít nhất `JAVA_INT.byteSize()` byte. `T**` là `ADDRESS` trong `FunctionDescriptor`, nhưng **slot** lại cần `ADDRESS.byteSize()` byte và alignment đúng.

**Về platform ABI:** trên **Windows x64 (LLP64)**, C `long` chỉ rộng **32 bit**, dù pointer và `size_t` rộng 64 bit. Trên **Linux x86-64 (LP64)**, `long` và `size_t` thường đều 64 bit. Vì vậy không được map một cách máy móc `C long = Java long` trên mọi OS. Trong ví dụ `strtol` Windows bên dưới, C `long` được map bằng `JAVA_INT`; còn `size_t` trong thư viện C x64 ở mục 8 được map bằng `JAVA_LONG`.

Các con trỏ trong FFM là `MemorySegment` carrier khi gọi downcall. `ValueLayout.ADDRESS.byteSize()` cho biết **độ rộng pointer của môi trường**, không phải kích thước data đích. `MemorySegment.NULL` biểu diễn địa chỉ null. Đừng tự ép một địa chỉ máy tùy ý thành memory hợp lệ.

## 4. Đọc `T**`: slot, pointer trả về và zero-length segment

Điểm dễ nhầm nhất là:

```java
MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

// Native code nhận slot để làm *out = pointer;
MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
```

`pointer` là **giá trị địa chỉ** do native code ghi. Theo hợp đồng FFM, pointer đọc từ một ô `ADDRESS` thông thường được biểu diễn bằng **zero-length memory segment**, tức `pointer.byteSize() == 0`. Nó không mang sẵn thông tin về kích thước hay ownership. Gọi `pointer.get(JAVA_BYTE, 0)` trên zero-length segment sẽ bị chặn vì ngoài phạm vi.

Nếu **thư viện có hợp đồng bảo đảm** pointer trỏ tới một vùng hợp lệ `n` byte, có thể dùng:

```java
// Chỉ an toàn khi đã xác minh NULL, size, lifetime và ABI.
MemorySegment view = pointer.reinterpret(n);
```

**`reinterpret` là restricted API nguy hiểm:** chỉ thay đổi kích thước mà Java cho phép truy cập; nó **không cấp phát lại**, **không kiểm tra được thực tế native đã cấp bao nhiêu byte**, **không kéo dài lifetime** của đối tượng đích và **không tự gọi free**. Nói sai `n` có thể đọc/ghi ngoài vùng, làm hỏng bộ nhớ hoặc crash JVM. Khi dùng API này phải có `--enable-native-access` thích hợp, đúng hợp đồng C, và cơ chế cleanup riêng.

Nếu con trỏ do native trả về chỉ **mượn từ vùng Java-owned** đang sống, cách tốt hơn là không `reinterpret`. Ví dụ `strtol` đặt `endptr` trỏ vào **bên trong chuỗi đầu vào**; hãy tính **byte offset**, kiểm tra offset nằm trong segment đầu vào và đọc từ **segment gốc** còn được Arena kiểm soát. Cách này tận dụng được bound/lifetime đã biết.

## 5. Demo đầy đủ chạy trên Windows x64: out-parameter, `char**` và buffer

Ví dụ này **không cần compiler C**, vì gọi các native functions có sẵn trên Windows:

1. `msvcrt.dll!strtol(const char*, char**, int)`: nhận `char** endptr` và ghi **con trỏ mượn** vào chuỗi input.
2. `kernel32.dll!MultiByteToWideChar(...)`: nhận **caller-owned wide-character output buffer**; có chế độ hỏi trước kích thước.
3. `kernel32.dll!GetComputerNameW(wchar_t*, DWORD*)`: nhận **buffer đầu ra** và **in/out length slot**.

Tất cả sử dụng **FFM Java 22+**, đã biên dịch và chạy trên **OpenJDK 24.0.2 / Windows 64-bit**. Ví dụ đọc địa chỉ và buffer, không phụ thuộc nội dung tên máy trong kết quả in ra.

### 5.1. File `OutPointerWindowsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class OutPointerWindowsDemo {
    private static MethodHandle link(Linker linker, SymbolLookup library,
                                     String symbol, FunctionDescriptor descriptor) {
        return linker.downcallHandle(library.findOrThrow(symbol), descriptor);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup crt = SymbolLookup.libraryLookup("msvcrt.dll", arena);
            SymbolLookup kernel = SymbolLookup.libraryLookup("kernel32.dll", arena);

            // C: long strtol(const char *s, char **endptr, int base);
            // Windows x64: C long = 32 bit.
            MethodHandle strtol = link(linker, crt, "strtol",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

            MemorySegment text = arena.allocateFrom("123tail");
            MemorySegment endSlot = arena.allocate(ValueLayout.ADDRESS);
            endSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

            int number = (int) strtol.invokeExact(text, endSlot, 10);
            MemorySegment end = endSlot.get(ValueLayout.ADDRESS, 0);

            // end là pointer mượn nằm bên trong text, không được free().
            long offset = end.address() - text.address();
            if (offset < 0 || offset >= text.byteSize()) {
                throw new IllegalStateException("Invalid strtol end pointer");
            }
            System.out.println("parsed: " + number);
            System.out.println("suffix: " + text.getString(offset));

            // Windows: int MultiByteToWideChar(
            //   UINT cp, DWORD flags, LPCCH src, int srcLen,
            //   LPWSTR dst, int dstChars);
            MethodHandle toWide = link(linker, kernel, "MultiByteToWideChar",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

            MemorySegment input = arena.allocateFrom("hello");
            // cbMultiByte = 5 => KHÔNG bao gồm byte NUL ở cuối.
            int needed = (int) toWide.invokeExact(
                65001, 0, input, 5, MemorySegment.NULL, 0);
            if (needed <= 0) {
                throw new IllegalStateException("MultiByteToWideChar sizing failed");
            }

            // WCHAR trên Windows = 2 byte UTF-16.
            MemorySegment output = arena.allocate(
                needed * 2L, ValueLayout.JAVA_CHAR.byteAlignment());
            int written = (int) toWide.invokeExact(
                65001, 0, input, 5, output, needed);
            if (written != needed) {
                throw new IllegalStateException("MultiByteToWideChar conversion failed");
            }

            StringBuilder buffer = new StringBuilder();
            for (int i = 0; i < written; i++) {
                buffer.append(output.getAtIndex(ValueLayout.JAVA_CHAR, i));
            }
            System.out.println("buffer: " + buffer);

            // Windows: BOOL GetComputerNameW(LPWSTR buffer, LPDWORD inoutSize);
            MethodHandle getName = link(linker, kernel, "GetComputerNameW",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS));

            MemorySegment name = arena.allocate(
                256L * 2, ValueLayout.JAVA_CHAR.byteAlignment());
            MemorySegment inOutLength = arena.allocate(ValueLayout.JAVA_INT);

            // nSize input là capacity tính theo WCHAR, KHÔNG phải byte.
            inOutLength.set(ValueLayout.JAVA_INT, 0, 256);
            int success = (int) getName.invokeExact(name, inOutLength);
            if (success == 0) {
                throw new IllegalStateException("GetComputerNameW failed");
            }

            // Khi thành công, nSize output không tính NUL kết thúc.
            int chars = inOutLength.get(ValueLayout.JAVA_INT, 0);
            System.out.println("inout length valid: " + (chars > 0 && chars <= 256));
        }
    }
}
```

### 5.2. Compile và chạy

Trên Windows 64-bit với **JDK 22 trở lên** (ví dụ đã thử JDK 24):

```powershell
javac -encoding UTF-8 OutPointerWindowsDemo.java
java --enable-native-access=ALL-UNNAMED OutPointerWindowsDemo
```

**Stdout đã kiểm thử thực tế:**

```text
parsed: 123
suffix: tail
buffer: hello
inout length valid: true
```

Mọi lệnh `linker.downcallHandle`/`SymbolLookup.libraryLookup` gọi restricted FFM operations đều nằm trong chương trình **không có module name** (classpath). `--enable-native-access=ALL-UNNAMED` cho phép các restricted methods đó. JDK 22+ FFM đã final, nên không cần `--enable-preview` **chỉ để dùng FFM**. Nếu dùng named Java module, cấp native-access cho module cụ thể thay vì `ALL-UNNAMED`.

### 5.3. Giải mã từng mẫu ownership trong kết quả

**`strtol` và `endptr`:** `endSlot` là bộ nhớ **Java Arena sở hữu** để chứa một địa chỉ. `strtol` ghi vào slot địa chỉ của ký tự `'t'` đầu tiên trong chuỗi `"123tail"`. `end.address() - text.address() == 3` (đơn vị byte). Vì đã kiểm tra bound trên `text`, Java đọc phần đuôi `text.getString(3)` là `tail`.

Con trỏ `end` là **borrowed pointer** trỏ vào vùng của `text`. **Không gọi `free(end)`**, vì nó không phải block được `malloc` riêng; nó hết hiệu lực khi arena đóng hoặc text không còn hợp lệ. Trong ví dụ, mọi thao tác với `end` đều hoàn tất trước khi ra khỏi `try`.

**`MultiByteToWideChar` và buffer:** Lần gọi với output là `MemorySegment.NULL` và `dstChars=0` hỏi số **UTF-16 code units** cần thiết. Java cấp đúng `needed*2` byte, cho native ghi vào. Khi `cbMultiByte=5`, chuỗi output **không tự có NUL cuối**, vì input length không bao gồm byte NUL. Vì vậy Java đọc **đúng `written` ký tự**, không dùng `getString` hay quét vô hạn để tìm terminator. Với chuỗi `hello`, kết quả là `buffer: hello`.

**`GetComputerNameW` và input/output length:** `inOutLength` là slot `DWORD*` **vừa đầu vào vừa đầu ra**. Trước khi gọi, Java ghi số ô `WCHAR` mà buffer chứa (256), **không phải 512 byte**. Sau khi thành công, native ghi số ký tự thực tế **không tính NUL**. Tên máy thay đổi theo hệ thống nên demo chỉ in điều kiện kích thước hợp lệ, tránh công bố tên máy hoặc phụ thuộc môi trường. Nếu buffer quá nhỏ, API báo lỗi và có quy tắc trả kích thước cần thiết; không đọc buffer như thể nó đã được điền thành công.

### 5.4. Những ràng buộc platform của demo

- `strtol` là hàm của CRT, trên Windows x64 `long` là **32 bit**, nên mapping return `JAVA_INT` đúng. Trên Linux x86-64, C `long` **64 bit**, cần mapping `JAVA_LONG` và tìm hàm từ thư viện C tương ứng.
- `GetComputerNameW` và `MultiByteToWideChar` là **Win32 APIs**, không có trên macOS/Linux. `WCHAR` Windows là UTF-16 2 byte, khác `wchar_t` trên nhiều hệ POSIX.
- `MultiByteToWideChar` đòi `cchWideChar` tính theo **ký tự WCHAR**, không phải byte. `GetComputerNameW` có quy tắc riêng về NUL và kích thước; không lấy hợp đồng của hàm này áp cho mọi hàm khác.
- Trước khi port, kiểm tra **C header**, calling convention, ABI, alignment, C string encoding và return semantics. Sai một descriptor của FFM có thể dẫn tới crash JVM, không chỉ Java exception.

## 6. Trường hợp `T**` trả bộ nhớ cấp phát bởi thư viện

Mẫu `strtol` ở trên có `char**` nhưng chỉ trả **borrowed pointer**. Một API khác có thể cấp phát memory rồi ghi địa chỉ mới vào `T**`:

```c
int create_payload(unsigned char **out_bytes, size_t *out_count);
void release_payload(unsigned char *ptr);
```

Hợp đồng ví dụ:

1. Caller cấp hai slot: một để chứa địa chỉ `unsigned char*`, một để chứa độ dài `size_t`.
2. Native code ghi `*out_bytes = malloc(...)` và `*out_count = n` nếu thành công.
3. Khi thành công, **ownership của block vừa malloc chuyển cho caller**. Java phải gọi đúng `release_payload(ptr)` một lần, dù thao tác xử lý dữ liệu phát exception.
4. Nếu trả lỗi, thư viện đặt `*out_bytes = NULL` và `*out_count = 0`; caller không được dereference pointer.
5. Slot chứa pointer và slot chứa size vẫn là **Java-owned Arena memory**. Chúng khác với **native-owned block** do pointer chỉ đến.

Đây là lý do **hai kiểu cùng là `char**` nhưng cleanup khác hoàn toàn**: `strtol` trả pointer vào chuỗi input (không free); `create_payload` trả block được `malloc` (phải free bằng hàm của thư viện). Quyền sở hữu đến từ **documentation/API contract**, không đến từ kiểu `T**`.

## 7. Thư viện C mẫu độc lập: `int*`, buffer và `unsigned char**`

Dưới đây là một thư viện C nhỏ để thấy rõ bên native thực sự ghi vào các out parameters. Nó không lệ thuộc Win32 APIs; có thể build trên **Linux x86-64, macOS 64-bit hoặc Windows x64** bằng compiler tương ứng.

### 7.1. Source `outdemo.c`

```c
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

// int*: caller owns one int slot.
EXPORT int get_answer(int *out_value) {
    if (out_value == NULL) return -1;
    *out_value = 42;
    return 0;
}

// char* buffer + size_t* required: caller owns the buffer.
// required counts ALL bytes including trailing NUL.
EXPORT int fill_message(char *buffer, size_t capacity, size_t *required) {
    static const char message[] = "hello"; // sizeof == 6
    if (required == NULL) return -1;

    *required = sizeof(message);
    if (buffer == NULL || capacity < sizeof(message)) {
        return 1; // Need more space; no buffer write.
    }

    memcpy(buffer, message, sizeof(message));
    return 0;
}

// unsigned char**: native allocates, then TRANSFERS block ownership.
EXPORT int create_payload(unsigned char **out_bytes, size_t *out_count) {
    if (out_bytes == NULL || out_count == NULL) return -1;
    *out_bytes = NULL;
    *out_count = 0;

    unsigned char *p = (unsigned char *) malloc(4);
    if (p == NULL) return -2;

    p[0] = 10;
    p[1] = 20;
    p[2] = 30;
    p[3] = 40;
    *out_bytes = p;
    *out_count = 4;
    return 0;
}

// Must be called exactly once for each successful create_payload().
EXPORT void release_payload(unsigned char *p) {
    free(p);
}
```

Các hàm dùng **C ABI**, tránh name mangling của C++; `EXPORT` giúp xuất symbol khi build DLL bằng MSVC. Nếu mã nguồn được biên dịch dưới dạng C++ thay vì C, phải điều chỉnh khai báo `extern "C"` để tên symbol tương thích với `SymbolLookup.find`.

**Trạng thái lỗi:** `0` thành công; `1` của `fill_message` có nghĩa **buffer không đủ** và `*required` chứa capacity cần thiết; giá trị âm nghĩa là input không hợp lệ hoặc cấp phát lỗi. Đó là hợp đồng **của ví dụ này**, không phải quy tắc chung cho thư viện C.

**Về chuỗi:** `sizeof(message)` gồm byte `'\0'` cuối, nên `required=6`; C chỉ ghi khi buffer đủ `6` byte. Không được gọi `strcpy` vào buffer chưa biết kích thước hay quên chỗ cho terminator.

### 7.2. Build native library

Linux x86-64 với GCC (lệnh từ thư mục chứa `outdemo.c`):

```bash
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -o liboutdemo.so outdemo.c
```

macOS 64-bit với Clang:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -o liboutdemo.dylib outdemo.c
```

Windows x64 trong **Visual Studio Developer PowerShell / Developer Command Prompt** có MSVC:

```powershell
cl /LD /W4 outdemo.c /link /OUT:outdemo.dll
```

Ba lệnh này là lựa chọn **theo toolchain**, không chạy tất cả trên cùng máy. Ứng dụng Java phía dưới dùng `System.mapLibraryName("outdemo")` để chọn tên thư viện cho hệ điều hành. **Source C và Java FFM của thư viện mẫu đã được rà soát; mã C chưa được build/run trong môi trường kiểm thử Windows này vì không có C compiler trong PATH.** Mục 5 là ví dụ FFM đã chạy thực tế mà không cần C compiler.

## 8. Java FFM gọi thư viện C mẫu và dọn native-owned pointer

Chương trình sau độc lập, dùng **JDK 22+**, và giả định đã build `liboutdemo.so`, `liboutdemo.dylib` hoặc `outdemo.dll` theo hệ điều hành rồi đặt vào **thư mục hiện hành**. Để đơn giản, minh họa chỉ nhắm **64-bit ABI**, nơi `size_t` rộng 8 byte. Chạy `java` với native-access flag vì sử dụng các restricted FFM methods.

### 8.1. Source `OutParamsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class OutParamsDemo {
    private static MethodHandle bind(Linker linker, SymbolLookup library,
                                     String symbol, FunctionDescriptor desc) {
        return linker.downcallHandle(library.findOrThrow(symbol), desc);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        try (Arena arena = Arena.ofConfined()) {
            Path path = Path.of(System.mapLibraryName("outdemo"))
                            .toAbsolutePath();
            SymbolLookup library = SymbolLookup.libraryLookup(path, arena);

            MethodHandle answer = bind(linker, library, "get_answer",
                FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS));
            MethodHandle fill = bind(linker, library, "fill_message",
                FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS,
                    ValueLayout.JAVA_LONG, ValueLayout.ADDRESS));
            MethodHandle make = bind(linker, library, "create_payload",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS));
            MethodHandle release = bind(linker, library, "release_payload",
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            // A) int *out: cấp phát slot rồi đọc giá trị native đã ghi.
            MemorySegment outInt = arena.allocate(ValueLayout.JAVA_INT);
            int rc = (int) answer.invokeExact(outInt);
            if (rc != 0) {
                throw new IllegalStateException("get_answer status=" + rc);
            }
            System.out.println("answer: "
                + outInt.get(ValueLayout.JAVA_INT, 0));

            // B) char *buffer, size_t capacity, size_t *required:
            //    lần đầu hỏi size; lần hai cấp buffer đúng số byte.
            MemorySegment requiredSlot = arena.allocate(ValueLayout.JAVA_LONG);
            requiredSlot.set(ValueLayout.JAVA_LONG, 0, 0L);
            rc = (int) fill.invokeExact(
                MemorySegment.NULL, 0L, requiredSlot);
            if (rc != 1) {
                throw new IllegalStateException("size query status=" + rc);
            }
            long capacity = requiredSlot.get(ValueLayout.JAVA_LONG, 0);
            if (capacity < 1 || capacity > 1024) {
                throw new IllegalStateException("Invalid native buffer size");
            }

            MemorySegment buffer = arena.allocate(capacity);
            rc = (int) fill.invokeExact(buffer, capacity, requiredSlot);
            if (rc != 0) {
                throw new IllegalStateException("fill_message status=" + rc);
            }
            System.out.println("buffer: " + buffer.getString(0));

            // C) T**: slot chứa pointer + slot chứa độ dài.
            MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
            MemorySegment lengthSlot = arena.allocate(ValueLayout.JAVA_LONG);
            pointerSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            lengthSlot.set(ValueLayout.JAVA_LONG, 0, 0L);
            rc = (int) make.invokeExact(pointerSlot, lengthSlot);
            if (rc != 0) {
                throw new IllegalStateException("create_payload status=" + rc);
            }

            MemorySegment nativePointer =
                pointerSlot.get(ValueLayout.ADDRESS, 0);
            long length = lengthSlot.get(ValueLayout.JAVA_LONG, 0);

            // Pointer target is malloc-owned; cleanup is not automatic.
            try {
                if (nativePointer.address() == 0 || length != 4) {
                    throw new IllegalStateException("Invalid native result");
                }

                // Restricted: requires TRUSTED length and native-access.
                MemorySegment view = nativePointer.reinterpret(length);
                System.out.print("payload: ");
                for (long i = 0; i < length; i++) {
                    if (i > 0) System.out.print(",");
                    System.out.print(view.get(ValueLayout.JAVA_BYTE, i) & 0xFF);
                }
                System.out.println();
            } finally {
                // Same library/allocator that created the payload.
                release.invokeExact(nativePointer);
            }
        }
    }
}
```

### 8.2. Biên dịch và chạy

Tại thư mục chứa `OutParamsDemo.java` **và shared library đã build**:

```bash
javac -encoding UTF-8 OutParamsDemo.java
java --enable-native-access=ALL-UNNAMED OutParamsDemo
```

**Stdout dự kiến theo đúng source C mẫu:**

```text
answer: 42
buffer: hello
payload: 10,20,30,40
```

**Phân biệt mức kiểm chứng:** mã Java phía trên đã được **javac 24 biên dịch thành công**. Môi trường Windows hiện tại không có C compiler trong PATH nên **chưa chạy cặp Java/C mẫu cùng nhau**. Stdout là **kết quả suy ra từ hợp đồng code C đã trình bày**, không phải log chạy thực tế của cặp này. Ví dụ Windows ở mục 5 đã chạy thực tế trên OpenJDK 24.

### 8.3. Phân tích quyền sở hữu từng đối tượng

| Biến/segment | Ai cấp phát? | Ai sở hữu? | Giải phóng thế nào? |
| --- | --- | --- | --- |
| `outInt` | `arena.allocate(JAVA_INT)` | Java Arena | Tự dọn khi arena đóng |
| `requiredSlot` / `lengthSlot` | `arena.allocate(JAVA_LONG)` | Java Arena | Tự dọn khi arena đóng |
| `buffer` | `arena.allocate(capacity)` | Java Arena | Tự dọn khi arena đóng; C không `free` |
| `pointerSlot` | `arena.allocate(ADDRESS)` | Java Arena | Tự dọn khi arena đóng |
| `nativePointer` (giá trị pointer nhận từ slot) | C ghi địa chỉ vào slot | Không sở hữu địa chỉ chỉ vì có Java handle | Không `free` bản thân “Java handle”; phải xét **block đích** |
| Block mà `nativePointer` trỏ tới | C `malloc(4)` | **Được chuyển cho caller sau khi tạo thành công** | `release_payload(nativePointer)` đúng **một lần** |
| `view` từ `reinterpret(length)` | FFM tạo alias trỏ tới block C | Chỉ là **view**, không phải một allocation riêng | Không free view; block được release bằng API C |

Khi `create_payload` đã thành công, `finally` bảo đảm gọi `release_payload` dù phép đọc/format dữ liệu ném exception. Ngược lại, khi `create_payload` trả lỗi, C mẫu bảo đảm pointer còn `NULL` và không chuyển ownership; Java ném lỗi **không được free một con trỏ rác**.

Không đưa `nativePointer`/`view` ra khỏi phạm vi xử lý sau khi gọi `release_payload`. Java không thể phát hiện mọi use-after-free đối với segment được `reinterpret` theo kích thước thủ công. Không giả định `Arena.close()` tự gọi `free` cho một block được malloc riêng: muốn gắn native allocation với Arena, cần explicit cleanup mechanism như `reinterpret(size, arena, cleanup)` được thiết kế đúng. **Không đồng thời đăng ký cleanup khi đóng arena và gọi free trong `finally`**, vì sẽ gây double-free.

## 9. Hai phương pháp xử lý native buffer: cấp trước và hỏi kích thước trước

Các thư viện dùng buffer có hai giao thức phổ biến.

### 9.1. Caller biết capacity trước

```c
int read_data(char *buf, size_t capacity, size_t *bytes_written);
```

Java cấp đúng capacity; native không ghi vượt quá; khi thành công, `bytes_written` phải nằm trong khoảng `0..capacity`. Java đọc **đúng `bytes_written` byte**, không giả định NUL hoặc UTF-8 nếu API không nói như vậy. Nếu API báo overflow/truncation, phải xử lý thay vì đọc phần bộ nhớ chưa được điền.

**Tình huống dễ sai:** capacity được tính bằng **số phần tử** nhưng Java cấp phát theo byte; với `wchar_t[]` hoặc một C struct có padding, hai con số không giống nhau. Kiểm tra tài liệu C header và biểu diễn dữ liệu.

### 9.2. Two-pass / probe-then-fill

Nhiều API cho phép gọi lần đầu với output `NULL` và capacity `0` để lấy kích thước cần thiết. Ví dụ `fill_message` ở mục 7 dùng `return 1` và `*required=6` rồi Java cấp 6 byte. Tương tự, `MultiByteToWideChar` cho phép hỏi số UTF-16 code units trước.

Mẫu chung:

```text
call(NULL, 0, &required)
        │
        ▼
  validate required (>= 0, within max, no overflow)
        │
        ▼
 allocate exactly required units
        │
        ▼
 call(buffer, capacity, &written)
        │
        ▼
 check status and written <= capacity
        │
        ▼
 decode/copy exact initialized region
```

Không tự suy “trả `0` luôn là thành công” hoặc “`required` luôn bao gồm NUL”: mỗi native API có return contract khác nhau.

**Race cần lưu ý:** nếu dữ liệu nguồn thay đổi giữa lần probe và lần fill, required size có thể thay đổi. API thực tế có thể yêu cầu vòng lặp cấp phát lại, retry giới hạn, hoặc caller-specified capacity. Không retry vô hạn và không allocate theo kích thước native không được kiểm soát. Với ví dụ C cố định `"hello"`, size không đổi giữa hai lượt.

## 10. Mượn pointer, chuyển ownership, và bảo vệ lifetime

### 10.1. Bảng quyết định free/close

| Native function trả gì? | Ownership kết quả | Có tự free không? |
| --- | --- | --- |
| Pointer đến `static const char[]` | Library-owned/static | **Không**; có thể mất hiệu lực nếu library bị unload |
| Pointer vào một input buffer Java truyền vào (như `strtol endptr`) | Borrowed view | **Không**; chỉ dùng khi input còn sống |
| Pointer mới tạo bằng `malloc`, contract chuyển ownership | Caller-owned/native allocation | **Có**, bằng đúng `free`/release API phù hợp |
| Pointer tới bộ nhớ thư viện giữ trong object/session | Library-owned, có thời hạn | **Không**, gọi close/release của owner theo contract |
| Caller-allocated output buffer | Java-owned Arena memory | **Không `free` bên C**; đóng Arena bên Java |
| OS/API cấp handle opaque, không phải memory pointer | Phụ thuộc loại handle | Dùng `CloseHandle`/`Release...` tương ứng, **không** dùng `free` nếu API không yêu cầu |

Không nên nhầm pointer-to-pointer `T**` với “cấp phát luôn do thư viện thực hiện”. Đôi khi nó chỉ là pointer-to-pointer mượn hoặc output pointer trỏ vào input. Ngược lại, hàm có thể trả **pointer trực tiếp trong giá trị return** mà vẫn chuyển quyền sở hữu. Chỉ **contract/documentation** xác định ai giải phóng.

### 10.2. Không giữ pointer lâu hơn nguồn

- Một `char*` mà C trả ra trỏ tới buffer do `Arena.ofConfined()` cấp phát chỉ an toàn trước khi arena đóng, trên owner thread tương ứng.
- Pointer đến memory tĩnh của thư viện có thể còn hợp lệ lâu nhưng **không nên dùng sau khi thư viện bị unload**.
- Pointer tới block do C malloc vẫn có thể còn về mặt địa chỉ sau `free` nhưng **giá trị đó trở nên vô hiệu để dereference**. Đặt registry/native state thành “đã giải phóng” và không dùng lại.
- Con trỏ trả về chưa biết size không được `reinterpret(1000000)` chỉ để “xem thử dữ liệu”; phải có size authoritative và kiểm tra ngưỡng.

### 10.3. Nếu muốn mang dữ liệu ra khỏi lifetime native

An toàn nhất là **copy kết quả ra Java values** trước khi đóng arena hoặc giải phóng block C:

```java
// Ví dụ cục bộ: view là MemorySegment 4 byte còn hợp lệ.
byte[] copy = view.toArray(ValueLayout.JAVA_BYTE);
// Sau khi copy xong, release native block;
// byte[] là bộ nhớ Java độc lập, không còn phụ thuộc native pointer.
```

Nếu cần trả về chuỗi, decode chính xác các byte đã được ghi, bao gồm quy tắc terminator/encoding. Không trả alias native `MemorySegment` cho code Java có lifetime dài nếu chưa có owner rõ ràng và cleanup chắc chắn.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Java FFM nhận `int*` nhưng descriptor dùng `JAVA_INT` | Lẫn giá trị `int` với địa chỉ `int*` | Descriptor tham số phải là `ADDRESS`; cấp slot `JAVA_INT` |
| Dùng `arena.allocate(JAVA_BYTE)` cho `char**` | Slot không đủ chỗ chứa pointer 64-bit | Cấp bằng `arena.allocate(ADDRESS)` đúng alignment |
| Đọc `pointer.get(JAVA_BYTE,0)` ngay sau `get(ADDRESS,0)` | Pointer-return segment mặc định có kích thước **0** | Dùng segment gốc với offset, hoặc `reinterpret` với size/lifetime chắc chắn |
| Gọi `free` với pointer từ `strtol endptr` | Pointer borrowed, trỏ vào input | Không free; dùng khi input còn sống |
| Không free pointer từ `create_payload` | Native block được malloc và chuyển quyền sở hữu | Gọi đúng `release_payload` trong `finally` |
| Free hai lần | Java và Arena cleanup đều giải phóng cùng block | Chọn **một** cleanup owner; không kết hợp double-free |
| Đọc buffer khi native call báo lỗi | C có thể chưa khởi tạo nội dung | Kiểm tra return status và `written` trước khi đọc |
| Quên NUL hoặc tính sai độ dài | `size_t` có thể là byte count; WinAPI dùng WCHAR count | Cấp đúng đơn vị, có chỗ cho terminator nếu API cần |
| Dùng `JAVA_LONG` cho Windows `strtol` | Windows x64 C `long` chỉ 32 bit | Map return `JAVA_INT` trên Windows LLP64; Linux x64 khác |
| Dùng `JAVA_INT` cho x64 `size_t` | `size_t` x64 64 bit | `JAVA_LONG` trên 64-bit ABI; kiểm tra platform |
| Dùng memory sau khi đóng Arena/free native | Temporal lifetime bị vi phạm | Copy trước, đóng/free đúng owner, không giữ dangling alias |
| Java code không tìm thấy symbol | Sai DLL/.so path hoặc tên C++ bị mangle | Chọn đúng `System.mapLibraryName`, path, exported C symbols |
| Restricted-method warning/`IllegalCallerException` | Thiếu native access permission | `--enable-native-access=ALL-UNNAMED` cho classpath hoặc tên module |
| Crash JVM khi gọi downcall | ABI, pointer size, calling convention hoặc lifetime sai | Đối chiếu C header, từng `FunctionDescriptor`, kiểm tra size và threading |

Nếu C API có `errno`/`GetLastError`, không suy diễn mã lỗi chỉ từ giá trị return hoặc độ dài đầu ra. Ví dụ `strtol` có thể trả 0 khi parse đúng `"0"` **hoặc** khi không có chữ số; phân biệt bằng `endptr`, và dùng cơ chế đọc `errno` phù hợp để xử lý overflow/underflow. Với WinAPI, có thể cần cơ chế lấy **last-error** trên đúng thread/call boundary. Bài này chỉ dùng dữ liệu đầu vào xác định để tập trung vào out-parameters.

## 12. Checklist khi tích hợp một API out-parameter thật

1. Đọc **chữ ký C**: return type, `const`, pointer depth, C ABI, alignment, argument order.
2. Tạo bảng cho từng pointer: **[in], [out], [in,out]**, số byte/element được phép truy cập.
3. Xác định **ai cấp phát**, **ai sở hữu**, **ai giải phóng**, bằng đúng allocator/handle-release API nào.
4. Với `T*`, cấp đúng kiểu slot (`JAVA_INT`, `JAVA_LONG`...). Với `T**`, cấp **slot `ADDRESS`** và đọc pointer sau call.
5. Khởi tạo output slots theo contract, thường null/0, trước khi đưa native code dùng.
6. Kiểm tra **status trước khi dereference**; đừng coi các output là hợp lệ nếu API báo thất bại.
7. Với buffer, kiểm tra size theo đơn vị (byte, UTF-16 code unit, C element), quy tắc NUL, overflow, max capacity.
8. Với native pointer, kiểm tra null, kích thước authoritative và lifetime trước khi `reinterpret`; hiểu restricted API không tự làm memory an toàn.
9. Dọn memory theo đúng owner trong `finally`/`try-with-resources`, không free borrowed pointer, không double-free.
10. Copy sang Java `byte[]`/`String` nếu dữ liệu cần tồn tại sau khi arena hoặc native block được giải phóng.
11. Test nhánh buffer quá nhỏ, native allocation failure, null pointer, length 0, length sai, native error code và multithreading.
12. Thử trên **từng ABI mục tiêu**; đặc biệt kiểm tra `long`, `size_t`, `wchar_t` và struct layout trước khi phát hành.

## 13. Bài tập tự luyện

1. Trong `int get_answer(int *out)`, vì sao tham số FFM là `ADDRESS` nhưng slot Java được cấp bằng `JAVA_INT`?
2. Với `char **out`, Java cần cấp bao nhiêu byte cho slot trên Windows x64? Vì sao không dùng `JAVA_BYTE`?
3. Sau `endSlot.get(ValueLayout.ADDRESS,0)`, vì sao không nên đọc trực tiếp byte từ segment pointer vừa trả về?
4. Vì sao pointer `endptr` của `strtol` **không** được free, dù nó nhận thông qua `char**`?
5. Khi `create_payload` thành công, hai vùng nhớ `pointerSlot` và block do `malloc` có cùng owner không? Ai giải phóng từng vùng?
6. Giả sử thư viện trả size là số phần tử `wchar_t`, tại sao Java không thể mặc định đó là byte count?
7. Nếu lần probe đầu nói cần 64 byte nhưng dữ liệu đổi và lần fill yêu cầu 128, ứng dụng nên xử lý thế nào?
8. Nếu dùng `reinterpret(n)` với `n` lớn hơn block native thật, Java có bảo đảm bounds check ngăn crash không?
9. Vì sao `try-with-resources` trên Arena **không tự free** một pointer mà C cấp bằng `malloc`?
10. Khác nhau giữa `char*` trả về trực tiếp, `char**` output và `char*` caller-supplied buffer là gì về ownership?

**Ghi nhớ:** **`T*`** thường giúp C ghi một giá trị vào slot, **`T**` giúp C ghi **một con trỏ** vào slot, còn **caller-provided buffer** là vùng nhớ Java đã cấp để native điền. FFM chỉ cho bạn handle và memory view; **ownership, size, lifetime, allocator và protocol xử lý lỗi phải đến từ hợp đồng của thư viện**. Không free pointer mượn; phải free pointer được chuyển quyền sở hữu đúng một lần; không đọc dữ liệu ngoài capacity hoặc sau khi Arena/free.

### Tài liệu chính thức

- [Oracle JDK 24 — FFM package overview: MemorySegment, Arena, Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle JDK 22 — MemorySegment API: pointer returns, getString và reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle JDK 22 — SymbolLookup.libraryLookup và lifetime của native library](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java Core Libraries — Foreign Functions That Return Pointers](https://docs.oracle.com/en/java/javase/23/core/foreign-functions-that-return-pointers.html).
- [Microsoft Learn — GetComputerNameW: out buffer, in/out size](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getcomputernamew).
- [Microsoft Learn — MultiByteToWideChar: sizing and output buffer](https://learn.microsoft.com/en-us/windows/win32/api/stringapiset/nf-stringapiset-multibytetowidechar).
- [Microsoft Learn — Windows x64 LLP64 data model](https://learn.microsoft.com/en-us/windows/win32/winprog64/abstract-data-models).
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — Foreign Function & Memory API (Third Preview)](https://openjdk.org/jeps/442).
