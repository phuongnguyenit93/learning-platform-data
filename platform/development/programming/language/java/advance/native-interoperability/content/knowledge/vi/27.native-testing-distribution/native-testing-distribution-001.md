# Tạo thư viện C nhỏ làm minh chứng cho hợp đồng dữ liệu và quyền sở hữu

Một bài thực hành native interoperability cần bắt đầu từ **hợp đồng dữ liệu (data contract)** và **hợp đồng quyền sở hữu (ownership contract)**. Java và C có mô hình quản lý bộ nhớ khác nhau: Java có GC/Arena, còn C có con trỏ, bộ cấp phát và quy tắc free riêng. Gọi hàm C thành công chưa đủ; ta cần biết chính xác byte nào đi qua ranh giới, ai cấp phát và ai được giải phóng vùng nhớ.

Bài này xây dựng thư viện C thật tên **tinybridge**, có header công khai, mã nguồn, bài test native, cấu hình CMake và chương trình Java dùng **Foreign Function & Memory API (FFM)** từ JDK 22. Ví dụ cố ý nhỏ, chỉ xử lý chữ cái ASCII trong một mảng byte; nhờ vậy có thể kiểm thử rõ hành vi đối với byte NUL và UTF-8 đa byte.

## 1. Hợp đồng sẽ chứng minh

Thư viện xuất ba hàm với ABI C ổn định cho một phiên bản giao diện:

- **tiny_abi_version()** trả phiên bản hợp đồng (bắt đầu từ 1).
- **tiny_ascii_upper_copy(input, input_len, out_data, out_len)** nhận một **vùng byte được mượn**, sao chép nội dung sang **vùng mới do C sở hữu lúc cấp phát**, chuyển chữ ASCII a–z thành A–Z, rồi trao quyền giải phóng vùng kết quả cho caller.
- **tiny_free(data)** giải phóng vùng mà chính thư viện đã cấp phát. Hàm chấp nhận NULL.

Định nghĩa cụ thể:

| Yếu tố | Contract |
| --- | --- |
| Kiểu dữ liệu | Mảng **uint8_t**, độ dài **uint64_t** tính theo byte; không phụ thuộc ký tự kết thúc chuỗi |
| Input | Con trỏ **const uint8_t*** là **borrowed**; hợp lệ trong suốt lời gọi; C không lưu lại và không free |
| Output | **uint8_t*** nằm trong **out_data**; do C cấp bằng malloc, **caller phải gọi tiny_free đúng một lần** nếu nhận pointer khác NULL |
| Output length | Ghi vào **out_len**; khi thành công bằng input_len |
| Thành công, input rỗng | Trả TINY_OK, out_data = NULL và out_len = 0 |
| Lỗi | Trả TINY_EINVAL hoặc TINY_ENOMEM; với hai output slot hợp lệ, out_data = NULL và out_len = 0 |
| Thời gian sống output | Hợp lệ đến khi tiny_free; sau free, mọi pointer/view trỏ đến vùng này đều vô hiệu |
| Đồng thời | Hàm đồng bộ, không giữ pointer hay trạng thái mutable toàn cục; các caller phải tự bảo đảm input/output không bị truy cập sai khi chia sẻ |
| Phiên bản | Caller kiểm tra tiny_abi_version trước khi suy diễn chữ ký hàm |

**Điều kiện tiền đề:** out_data và out_len phải trỏ tới hai ô nhớ **hợp lệ, ghi được, không chồng lấn**; input phải đọc được ít nhất input_len byte nếu input_len lớn hơn 0. C không thể kiểm tra mọi pointer hỏng do caller cung cấp. Với output slots là NULL, hàm trả lỗi mà không thể khởi tạo slot bị thiếu.

Quy ước mã lỗi: **TINY_OK = 0**, **TINY_EINVAL = 1** (tham số, độ dài không hợp lệ) và **TINY_ENOMEM = 2** (không cấp phát được). Không ném exception xuyên ranh giới ABI C.

## 2. Cấu trúc dự án tối thiểu

~~~text
tinybridge/
├── CMakeLists.txt
├── include/
│   └── tinybridge.h
├── src/
│   └── tinybridge.c
├── tests/
│   └── test_tinybridge.c
└── examples/
    └── TinyBridgeDemo.java
~~~

Cặp **header + thư viện binary** chính là hợp đồng để Java, C hoặc ứng dụng khác gọi vào. Không cần expose struct nội bộ, STL/C++ object hay địa chỉ allocator của bên ngoài.

## 3. Public header: include/tinybridge.h

~~~c
#ifndef TINYBRIDGE_H
#define TINYBRIDGE_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(TINYBRIDGE_BUILD)
#    define TINY_API __declspec(dllexport)
#  else
#    define TINY_API __declspec(dllimport)
#  endif
#else
#  define TINY_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define TINY_ABI_VERSION 1u
#define TINY_OK      0
#define TINY_EINVAL  1
#define TINY_ENOMEM  2

TINY_API uint32_t tiny_abi_version(void);

/*
 * input: borrowed, readable for input_len bytes, not retained.
 * out_data and out_len: two valid, writable, nonoverlapping slots.
 * On success: output is a separately allocated copy; caller owns it.
 * On error: if both output slots are valid, sets *out_data=NULL,
 *           *out_len=0.
 * input_len==0 accepts input==NULL and returns empty output.
 */
TINY_API int tiny_ascii_upper_copy(
        const uint8_t *input,
        uint64_t input_len,
        uint8_t **out_data,
        uint64_t *out_len);

/* Release only output allocated by tinybridge; NULL is allowed. */
TINY_API void tiny_free(void *data);

#ifdef __cplusplus
}
#endif
#endif
~~~

**Vì sao khai báo như vậy?**

1. **uint8_t** nghĩa là byte/octet, **uint64_t** là độ dài 64-bit. Với Java FFM, chúng tương ứng nội dung byte, **JAVA_LONG** cho tham số uint64_t trên ABI 64-bit thông dụng và **ADDRESS** cho con trỏ. Giá trị uint64_t lớn hơn Long.MAX_VALUE cần xử lý riêng; ví dụ Java dưới đây chỉ truyền mảng nhỏ.
2. **const** cho input ghi rõ C không được ghi vào dữ liệu mượn. Nó không tự bảo vệ bộ nhớ khỏi caller free sớm.
3. **uint8_t \*\*out_data** và **uint64_t \*out_len** là địa chỉ của hai output slot; C ghi giá trị con trỏ và độ dài vào đó. Chúng khác với bản thân buffer output.
4. **extern "C"** giữ tên symbol theo C ABI khi header được ứng dụng C++ sử dụng, tránh C++ name mangling.
5. **TINY_API** xuất symbol từ DLL trên Windows và đặt visibility trên Unix-like. Macro **TINYBRIDGE_BUILD** chỉ áp dụng khi biên dịch thư viện; client C/DLL import không đặt macro này.
6. Không dùng Java object, **std::string**, callback hoặc struct ABI phức tạp. Giao diện nhỏ giúp khóa phiên bản và test độc lập.

## 4. Implementation: src/tinybridge.c

~~~c
#include "tinybridge.h"

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

uint32_t tiny_abi_version(void) {
    return TINY_ABI_VERSION;
}

int tiny_ascii_upper_copy(const uint8_t *input, uint64_t input_len,
                          uint8_t **out_data, uint64_t *out_len) {
    if (out_data == NULL || out_len == NULL) {
        return TINY_EINVAL;
    }

    /* Lỗi hay input rỗng đều có output xác định. */
    *out_data = NULL;
    *out_len = 0;

    if (input_len != 0 && input == NULL) {
        return TINY_EINVAL;
    }
    if (input_len > (uint64_t) SIZE_MAX) {
        return TINY_EINVAL; /* Không chuyển tràn sang size_t. */
    }
    if (input_len == 0) {
        return TINY_OK;
    }

    size_t n = (size_t) input_len;
    uint8_t *copy = malloc(n);
    if (copy == NULL) {
        return TINY_ENOMEM;
    }

    for (size_t i = 0; i < n; ++i) {
        uint8_t b = input[i];
        copy[i] = (b >= 'a' && b <= 'z')
                ? (uint8_t) (b - ('a' - 'A'))
                : b;
    }

    *out_data = copy;
    *out_len = input_len;
    return TINY_OK;
}

void tiny_free(void *data) {
    free(data);
}
~~~

**Bằng chứng ownership nằm ở đâu?**

- Hàm chỉ đọc **input** trong khi lời gọi đang chạy; không lưu con trỏ lại trong global hay request bất đồng bộ. Vì vậy, caller có thể thu hồi input **sau khi hàm trả về** nếu không có consumer khác.
- Khi input_len > 0, **malloc(n)** tạo vùng mới và sao chép từng byte. **copy** không alias vùng input.
- Khi thành công, quyền quản lý output được chuyển qua **\*out_data**. C không tự free trước khi trả kết quả; Java/C caller phải gọi đúng **tiny_free**.
- Khi bất kỳ lỗi hợp lệ nào xảy ra, **\*out_data** và **\*out_len** đã được reset, giúp caller không nhầm dữ liệu lỗi với dữ liệu thật.
- Input rỗng tạo **NULL + 0**, tránh phải phụ thuộc hành vi malloc(0). **free(NULL)** theo C là thao tác hợp lệ.

Hàm chỉ đổi byte ASCII từ 0x61–0x7A thành 0x41–0x5A. UTF-8 không-ASCII (ví dụ ký tự é mã hóa bằng **C3 A9**) giữ nguyên từng byte. Đây **không phải** thuật toán viết hoa Unicode; tên hàm thể hiện giới hạn đó.

**Cảnh báo:** C không có bounds check tự động đối với pointer; cặp pointer/length không khớp vẫn có thể gây đọc sai vùng nhớ. FFM không thể biến địa chỉ native tùy ý thành vùng nhớ an toàn một cách tự động.

## 5. Kiểm thử contract ở C trước khi gọi Java

**File: tests/test_tinybridge.c**

~~~c
#include "tinybridge.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    if (tiny_abi_version() != TINY_ABI_VERSION) {
        return 1;
    }

    /* Có byte NUL ở giữa và hai byte UTF-8 của chữ é. */
    const uint8_t input[] = {'h', 'i', 0, 'a', 0xC3, 0xA9};
    const uint8_t want[]  = {'H', 'I', 0, 'A', 0xC3, 0xA9};

    uint8_t *out = NULL;
    uint64_t len = 99;
    int status = tiny_ascii_upper_copy(
            input, sizeof input, &out, &len);

    if (status != TINY_OK || out == NULL || len != sizeof want) {
        return 2;
    }

    int equal = memcmp(out, want, sizeof want) == 0;
    tiny_free(out); /* Đóng vòng đời vùng do thư viện cấp. */
    if (!equal) {
        return 3;
    }

    /* Lỗi: input NULL mà length > 0; output slots phải reset. */
    uint8_t marker = 42;
    out = &marker;
    len = 99;
    status = tiny_ascii_upper_copy(NULL, 3, &out, &len);
    if (status != TINY_EINVAL || out != NULL || len != 0) {
        return 4;
    }

    /* Input rỗng hợp lệ; trả NULL/0 thay vì vùng giả. */
    out = &marker;
    len = 99;
    status = tiny_ascii_upper_copy(NULL, 0, &out, &len);
    if (status != TINY_OK || out != NULL || len != 0) {
        return 5;
    }

    tiny_free(out); /* free(NULL) hợp lệ. */
    puts("contract tests: OK");
    return 0;
}
~~~

Bài test chủ động kiểm tra **embedded NUL** (không dùng strlen), UTF-8 nhiều byte, input rỗng, tham số lỗi, output initialization và đường giải phóng. Trả về mã khác 0 khi contract bị vi phạm, nên CTest nhận ra test fail. Test này không thay thế fuzzing, leak detection hoặc stress test.

## 6. Build, chạy test và tạo gói phân phối bằng CMake

**File: CMakeLists.txt**

~~~cmake
cmake_minimum_required(VERSION 3.16)
project(tinybridge VERSION 1.0.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_library(tinybridge SHARED src/tinybridge.c)
target_compile_definitions(tinybridge PRIVATE TINYBRIDGE_BUILD)
target_include_directories(tinybridge PUBLIC include)

add_executable(test_tinybridge tests/test_tinybridge.c)
target_link_libraries(test_tinybridge PRIVATE tinybridge)

enable_testing()
add_test(NAME tinybridge_contract COMMAND test_tinybridge)

install(TARGETS tinybridge
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib)
install(FILES include/tinybridge.h DESTINATION include)
~~~

Trong thư mục gốc **tinybridge/**, dùng máy có **CMake + C compiler**:

~~~bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
cmake --install build --config Debug --prefix stage
~~~

Với test pass, chương trình C in ra:

~~~text
contract tests: OK
~~~

Tên binary tùy hệ điều hành và generator:

| Hệ thống | Thư viện động điển hình |
| --- | --- |
| Linux | **libtinybridge.so** |
| macOS | **libtinybridge.dylib** |
| Windows | **tinybridge.dll**, thường nằm dưới **build/Debug/** với Visual Studio |

CMake có thể đặt binary vào thư mục cấu hình khác; xác nhận đường dẫn thực tế trước khi Java load. Bước **install** tạo nội dung gói gồm header và shared library (Windows có thể thêm import library **.lib** trong **lib/**). Khi phát hành, đi kèm bản ghi **ABI_VERSION**, hệ điều hành, CPU architecture (x86-64/arm64), compiler/runtime dependency và phiên bản artifact; không coi DLL/SO/DYLIB của nền tảng này có thể dùng trực tiếp trên nền tảng khác.

Kiểm tra symbol khi cần: **nm -D** trên Linux, **nm -g** hoặc **otool** trên macOS, **dumpbin /EXPORTS** trên Windows/MSVC. Ba tên **tiny_abi_version**, **tiny_ascii_upper_copy**, **tiny_free** phải được export rõ ràng.

## 7. Java 22+: gọi thư viện C bằng FFM và giải phóng đúng owner

FFM chuẩn hóa trong **java.lang.foreign** từ Java 22. Chương trình dùng **SymbolLookup** tìm symbol, **Linker** tạo downcall, và **Arena** cấp vùng input + hai output slot. Vùng output thực tế do **C malloc**, **không thuộc Arena của Java**.

**File: examples/TinyBridgeDemo.java**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Arrays;

public class TinyBridgeDemo {
    private static MemorySegment requireSymbol(SymbolLookup lib, String name) {
        return lib.find(name).orElseThrow(
                () -> new IllegalStateException("Symbol missing: " + name));
    }

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass absolute library path");
        }

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib = SymbolLookup.libraryLookup(
                    Path.of(args[0]).toAbsolutePath(), arena);

            MethodHandle version = linker.downcallHandle(
                    requireSymbol(lib, "tiny_abi_version"),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));
            MethodHandle copy = linker.downcallHandle(
                    requireSymbol(lib, "tiny_ascii_upper_copy"),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
                            ValueLayout.ADDRESS, ValueLayout.ADDRESS));
            MethodHandle release = linker.downcallHandle(
                    requireSymbol(lib, "tiny_free"),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            int abi = (int) version.invokeExact();
            if (abi != 1) throw new IllegalStateException("Unsupported ABI: " + abi);

            byte[] src = ("hi" + (char) 0 + "aé")
                    .getBytes(StandardCharsets.UTF_8);
            MemorySegment input = arena.allocate(src.length);
            for (int i = 0; i < src.length; i++) {
                input.set(ValueLayout.JAVA_BYTE, i, src[i]);
            }

            MemorySegment outSlot = arena.allocate(ValueLayout.ADDRESS);
            MemorySegment lenSlot = arena.allocate(ValueLayout.JAVA_LONG);
            outSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            lenSlot.set(ValueLayout.JAVA_LONG, 0, 0L);

            int status = (int) copy.invokeExact(
                    input, (long) src.length, outSlot, lenSlot);
            MemorySegment owned = outSlot.get(ValueLayout.ADDRESS, 0);
            long size = lenSlot.get(ValueLayout.JAVA_LONG, 0);

            try {
                if (status != 0) {
                    throw new IllegalStateException("Native status: " + status);
                }
                if (size < 0 || size > Integer.MAX_VALUE
                        || (size > 0 && owned.address() == 0)) {
                    throw new IllegalStateException("Invalid result pointer/length");
                }

                byte[] result = size == 0 ? new byte[0]
                        : owned.reinterpret(size).toArray(ValueLayout.JAVA_BYTE);
                byte[] expected = ("HI" + (char) 0 + "Aé")
                        .getBytes(StandardCharsets.UTF_8);
                if (!Arrays.equals(result, expected)) {
                    throw new AssertionError("Unexpected native output");
                }

                System.out.println("ABI=" + abi);
                System.out.println("input=" + Arrays.toString(src));
                System.out.println("output=" + Arrays.toString(result));
                System.out.println("text=" + new String(result, StandardCharsets.UTF_8)
                        .replace(String.valueOf((char) 0), "<NUL>"));
            } finally {
                release.invokeExact(owned);
            }
        }
    }
}
~~~

Sau khi tạo thư viện bằng CMake, biên dịch Java từ thư mục gốc dự án:

~~~bash
javac examples/TinyBridgeDemo.java
~~~

Trên Linux, khi thư viện có đường dẫn chuẩn **build/libtinybridge.so**:

~~~bash
java --enable-native-access=ALL-UNNAMED -cp examples TinyBridgeDemo "$PWD/build/libtinybridge.so"
~~~

Trên macOS, thay phần đuôi **.so** bằng **.dylib**. Trên Windows PowerShell với Visual Studio generator:

~~~powershell
$lib = (Resolve-Path .\build\Debug\tinybridge.dll).Path
java --enable-native-access=ALL-UNNAMED -cp examples TinyBridgeDemo $lib
~~~

Dữ liệu đầu vào mang byte NUL ở giữa và ký tự é. Với bản build tương ứng chạy thành công, stdout phải là:

~~~text
ABI=1
input=[104, 105, 0, 97, -61, -87]
output=[72, 73, 0, 65, -61, -87]
text=HI<NUL>Aé
~~~

**Giải thích những dòng quan trọng:**

- **Arena** giữ sống input và các output slot trong phạm vi lời gọi. **Arena.ofConfined()** thích hợp vì chương trình gọi native đồng bộ trên cùng Java thread.
- **ValueLayout.ADDRESS** tương ứng con trỏ. Slot **outSlot** chứa địa chỉ của output do C trả về; slot **lenSlot** chứa số byte. **JAVA_LONG** tương ứng tham số/slot **uint64_t** trên target 64-bit đã chọn.
- Con trỏ output trả từ downcall có segment mang kích thước 0; chỉ **sau khi kiểm tra length/pointer**, Java mới dùng **reinterpret(size)** để tạo view đủ byte. Reinterpret là thao tác nhạy cảm: nếu C trả pointer hoặc length sai, JVM có thể crash.
- **toArray(JAVA_BYTE)** sao chép bytes vào Java heap. Sau thao tác copy, Java array có đời sống độc lập với vùng C. Nếu muốn giữ zero-copy view, phải giữ output native còn sống cho đến lần truy cập cuối.
- **release.invokeExact(owned)** nằm trong **finally**, ghép đúng allocator/free của thư viện, kể cả khi kiểm tra kết quả hay xử lý output ném lỗi. **tiny_free(NULL)** hợp lệ.
- Đóng Java Arena chỉ giải phóng các vùng do Arena cấp; nó **không** thay cho **tiny_free(owned)** đối với C malloc. Đồng thời phải bảo đảm không gọi symbol sau khi Arena dùng cho library lookup đã đóng.

Các downcall FFM là truy cập native có hạn chế; dùng **--enable-native-access=ALL-UNNAMED** cho ứng dụng trên classpath. Java 22+ yêu cầu quy tắc cấp quyền native access phù hợp phiên bản JVM; nếu chuyển sang named module, cấp quyền cho tên module đó.

## 8. Sơ đồ ownership của ví dụ

~~~text
Java tạo input (Arena) ------------- borrowed ----------> C đọc input
       |                                                        |
       |                                                malloc(output)
       |                                                        |
       +-- outSlot / lenSlot <--------- pointer + length -------+
                   |
          Java kiểm tra dữ liệu
                   |
            copy sang byte[]
                   |
      tiny_free(pointer) ----------> C free(output), đúng một lần
                   |
             đóng Arena
~~~

Chú ý có **hai cấp vùng nhớ** khác nhau: **outSlot** (chứa giá trị địa chỉ, do Java Arena cấp) và **output** (vùng byte thực, do C malloc). Không được free địa chỉ của **outSlot** bằng tiny_free; cũng không được close Arena rồi tiếp tục truy cập **outSlot**.

Ownership không tự chuyển theo cú pháp C pointer. Hợp đồng header và tài liệu hàm mới là nơi quy định bên nào được release.

## 9. Những biến thể cần quyết định rõ khi mở rộng thư viện

| Kiểu API | Ai sở hữu bộ nhớ? | Khi nào được release? |
| --- | --- | --- |
| **Borrowed input** | Caller | Sau khi hàm đồng bộ trả về; nếu native giữ pointer để xử lý async, phải đợi completion thực |
| **Owned output** như ví dụ | Caller nhận trách nhiệm cleanup; allocator thuộc C | Khi đọc/copy xong và không còn view/callback sử dụng |
| **Borrowed output** | Thư viện hoặc object owner | Không được tự tiny_free; chỉ dùng đến mốc thư viện quy định |
| **Caller-allocated output** | Caller cấp và quản lý | Sau khi native ghi xong; API phải có capacity, actual length, mã lỗi khi thiếu |
| **Opaque native handle** | Quy định theo create/destroy của thư viện | Gọi destroy chuyên dụng sau khi các operation dùng handle đã kết thúc |
| **Transferred input** | Native nhận ownership theo API | Caller không được tự free sau chuyển giao thành công; cần mô tả xử lý khi chuyển giao thất bại |

Nếu thêm hàm trả **const char*** trỏ đến string tĩnh, hãy ghi rõ đó là **borrowed pointer**, caller chỉ đọc, không free; kèm độ dài hoặc quy tắc NUL termination. Nếu thêm API nhận string, phải ghi rõ **UTF-8/UTF-16/locale**, NUL có được phép không, độ dài tính theo byte hay code point, ai giữ terminator, và có normalize hay không.

Nếu thêm struct C vào ABI, tránh đoán padding/alignment của Java từ thứ tự field. Dùng **sizeof**, **offsetof** và MemoryLayout phù hợp từng nền tảng; kiểm tra trên cả target 64-bit. Không expose nội bộ C++ hay API dựa trên compiler-specific object layout khi muốn ABI rộng rãi.

## 10. Những lỗi điển hình và cách phát hiện

1. **Gọi free() từ Java/JNA trên memory do DLL cấp**: nguy cơ sai runtime allocator, nhất là Windows có nhiều CRT/heap. Dùng hàm release do thư viện export.
2. **Đóng Arena thay cho tiny_free**: vùng malloc của C bị rò rỉ. Hai bộ cấp phát có lifetime độc lập.
3. **tiny_free(input)**: input mượn không phải vùng C cấp, có thể gây heap corruption.
4. **Double-free output**: lần release thứ hai dẫn đến undefined behavior. Chỉ có một owner chịu trách nhiệm dọn dẹp; đặt cleanup vào một đường finally duy nhất.
5. **Giữ MemorySegment view sau tiny_free**: view trỏ địa chỉ thô có thể trở thành dangling pointer; cần sao chép vào Java heap nếu dữ liệu phải sống lâu hơn.
6. **Dùng strlen cho buffer binary**: byte NUL giữa mảng làm mất dữ liệu. Dùng explicit length như demo.
7. **Hiểu nhầm ASCII uppercase thành Unicode uppercase**: chữ é được giữ nguyên; thuật toán Unicode cần thư viện và contract khác.
8. **Đọc output dù status báo lỗi**: output invalid; phải kiểm tra status, pointer, length trước khi đọc.
9. **Không cố định ABI**: cập nhật chữ ký function mà Java vẫn dùng descriptor cũ có thể làm hỏng stack hoặc memory. Kiểm tra version, giữ compatibility hoặc tăng phiên bản.
10. **Sai architecture/library path**: JVM 64-bit không thể load binary native sai CPU/OS; cấu hình distribution phải có variant tương ứng.
11. **Đổi sang async nhưng vẫn free input ngay sau submit**: C tiếp tục giữ pointer dẫn tới use-after-free. Phải có handle/request + completion/quiescence, làm rõ owner và thời điểm release lại từ đầu.

## 11. Checklist kiểm thử và phân phối có thể áp dụng

**Contract tests:** kiểm tra thành công, length rỗng, input NULL trái hợp đồng, output NULL, dữ liệu chứa NUL, bytes ngoài ASCII, dữ liệu lớn, lỗi cấp phát giả lập, free(NULL), nhiều lời gọi liên tục. Test đường lỗi sao cho không còn allocated pointer bị thất lạc.

**Tooling:** bật compiler warnings (**-Wall -Wextra -Wpedantic** với GCC/Clang, **/W4** với MSVC) và cân nhắc AddressSanitizer/UndefinedBehaviorSanitizer trong build hỗ trợ. Chạy memory leak checks và stress test đa thread nếu API cho phép gọi đồng thời. Kiểm tra symbol export và binary dependency.

**Cross-language tests:** Java thử ABI version mismatch, function lookup fail, input Unicode UTF-8, embedded NUL, output length, đặc biệt dọn dẹp trong finally. Chạy trên từng OS/CPU mà gói tuyên bố hỗ trợ. Một bản Java compile thành công **không chứng minh** thư viện C đã build, load hoặc chạy đúng trên máy khác.

**Phân phối:** gói **tinybridge.h**, đúng native binary theo platform, ghi ABI/architecture/dependencies, giấy phép, cách load, và bảng ownership ở phần 1. Chạy CTest và Java integration test trên artifact thực trước khi phát hành; tránh chỉ test một bản C source khác với binary đã đóng gói.

**Bài tập mở rộng:** thêm **tiny_copy_to_buffer(input, len, output, capacity, written)** để caller sở hữu output. Định nghĩa khi capacity không đủ: trả mã lỗi, ghi **written** theo quy ước nhất quán và tuyệt đối không ghi vượt capacity. So sánh việc phân phối API này với owned output **tiny_ascii_upper_copy**.

## 12. Điều cần nhớ

Thư viện native nhỏ vẫn phải trả lời đủ bốn câu hỏi: **byte nào đi qua**, **ai cấp phát**, **ai được phép giải phóng**, và **tài nguyên sống đến lúc nào**. Trong ví dụ, Java cho C mượn input trong một downcall đồng bộ; C tạo output riêng và chuyển trách nhiệm dọn dẹp cho Java; Java sao chép kết quả rồi yêu cầu chính C giải phóng output qua tiny_free. Unit test, FFM integration test và ABI version giúp contract đó kiểm chứng được khi build và phân phối.

### Tham khảo

- Oracle Java SE 22, FFM API: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html
- Dev.java, native memory với Arena/MemorySegment: https://dev.java/learn/api/io/ffm/access-memory/
- CMake, add_library / install / enable_testing: https://cmake.org/cmake/help/latest/
- ISO C, malloc/free và hợp đồng pointer/size: tham khảo phần stdlib.h trong tài liệu C11 của compiler và platform SDK đang dùng.
