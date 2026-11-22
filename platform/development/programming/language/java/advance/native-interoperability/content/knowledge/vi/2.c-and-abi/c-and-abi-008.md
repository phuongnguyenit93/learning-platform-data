# Biểu diễn mã lỗi, giá trị sentinel và quyền sở hữu bộ nhớ trong hợp đồng C

Khi Java gọi một thư viện native qua JNI hoặc Foreign Function & Memory API (FFM), ranh giới C/ABI phải quy định rõ **thành công hay thất bại được biểu diễn thế nào**, **giá trị nào là dữ liệu hợp lệ**, và **ai phải giải phóng vùng nhớ nào, vào lúc nào**. Một con trỏ khác `NULL` chưa chứng minh thao tác thành công; một mã `-1` có thể là sentinel hoặc dữ liệu bình thường tùy hợp đồng. Nếu Java hiểu sai quy ước này, hậu quả có thể là báo lỗi sai, rò rỉ bộ nhớ, double free, use-after-free hoặc JVM crash.

Bài này tập trung vào việc thiết kế, đọc và ánh xạ **hợp đồng C và ABI**; ví dụ chạy được gồm thư viện C, chương trình C và Java 22+ dùng FFM. JNI tuân theo cùng các nguyên tắc về status và ownership, dù API quản lý tài nguyên riêng.

## 1. Phân biệt kết quả, trạng thái lỗi và nghĩa vụ sở hữu

Mỗi hàm qua ABI nên trả lời được năm câu hỏi:

1. **Điều kiện đầu vào:** tham số nào có thể là `NULL`, con trỏ có cần trỏ đến vùng nhớ hợp lệ, chuỗi dùng UTF-8 hay encoding khác, độ dài có gồm byte NUL không?
2. **Quy tắc thành công:** mã trả về nào là thành công, điều kiện nào khiến các output parameter có giá trị hợp lệ?
3. **Quy tắc thất bại:** mã lỗi biểu diễn bằng `int32_t`, `errno`, giá trị sentinel, hay một tổ hợp? Có thể lấy thông điệp lỗi bằng cách nào?
4. **Vòng đời bộ nhớ:** dữ liệu thuộc caller hay thư viện; ai cấp phát, ai giải phóng, hàm nào giải phóng, có được giữ sau khi lời gọi kết thúc?
5. **Tính ổn định ABI:** kích thước kiểu, calling convention, encoding, giá trị mã lỗi và tên symbol có ổn định giữa phiên bản và nền tảng không?

`ABI` mô tả cách hàm, tham số, kiểu dữ liệu và bố cục bộ nhớ được trao đổi ở mức nhị phân. Chữ ký nhìn giống nhau trong C không bảo đảm có thể ánh xạ tùy ý sang Java: `int32_t` là 32 bit; `size_t` phụ thuộc kiến trúc; con trỏ có độ rộng theo tiến trình; `long` có thể khác giữa Linux x64 (LP64) và Windows x64 (LLP64).

## 2. Các cách biểu diễn lỗi thường gặp

| Quy ước | Minh họa | Ưu điểm | Điều phải ghi rõ |
| --- | --- | --- | --- |
| Mã trạng thái + tham số đầu ra | `int32_t api_read(..., size_t *out_n)` | Dữ liệu và lỗi không va chạm | Giá trị status; trạng thái `out_n` khi lỗi |
| Giá trị sentinel | Hàm trả `NULL` hoặc `-1` | Ít tham số, thường gặp trong API truyền thống | Sentinel có thuộc miền dữ liệu hợp lệ không; tra chi tiết lỗi ở đâu |
| `errno` đi kèm kết quả lỗi | POSIX `read()` trả `-1` | Mô tả lỗi hệ thống phong phú | Chỉ đọc `errno` theo hợp đồng hàm và sau khi xác định lời gọi thất bại |
| Struct kết quả | `{status, value}` | Có thể mang nhiều trường | Bố cục, padding, alignment và quy tắc ABI của struct |
| Status + callback/thông điệp | `api_last_error()` | Giải thích lỗi sâu hơn | Bộ nhớ thông điệp, thread-safety, lúc nào thông điệp bị thay |

Với một API C mới phục vụ Java, cách dễ quản lý là **mã status riêng, cố định + output parameter**. Chẳng hạn: `0` thành công; `1` đối số sai; `2` hết bộ nhớ; `3` vượt giới hạn kích thước. Định nghĩa số tường minh; không đổi số khi thêm trạng thái; caller phải xử lý được mã chưa biết từ phiên bản thư viện mới.

Một hợp đồng tốt có thể quy định: nếu các con trỏ output hợp lệ nhưng thao tác thất bại, `*out_ptr = NULL` và `*out_len = 0`; chỉ khi status là thành công mới được dùng output. Nếu chính con trỏ output là `NULL`, hàm trả lỗi mà không thể ghi vào địa chỉ ấy. Không bao giờ dereference output chưa khởi tạo.

### 2.1. `errno` không phải mã lỗi chung của mọi thư viện

Trong C/POSIX, `errno` là một cơ chế báo lỗi được nhiều API chuẩn sử dụng, thường có trạng thái riêng theo thread. Nhưng không phải mọi hàm C đều thiết lập `errno` khi thất bại, và một giá trị `errno` khác 0 **không tự chứng minh** lời gọi vừa thất bại. Phải kiểm tra sentinel/status được mô tả bởi chính hàm đó trước, rồi đọc/copy `errno` ngay khi còn phù hợp; một lời gọi thư viện khác có thể làm thay đổi nó. Không phụ thuộc vào `errno` nếu hợp đồng của API không hứa sử dụng nó.

Ví dụ POSIX (không phải ISO C thuần): `read(fd, buf, count)` trả số byte đọc được khi thành công, `0` là EOF và `-1` biểu thị lỗi; chỉ khi `-1` mới dùng `errno` để nhận diện nguyên nhân. Số byte có thể nhỏ hơn `count` mà vẫn là thành công.

Hàm `strtol()` minh họa bẫy khác: giá trị `0`, `LONG_MIN` hoặc `LONG_MAX` có thể xuất hiện trong tình huống hợp lệ lẫn lỗi tùy trường hợp. Cần xét `endptr`, `errno == ERANGE` (sau khi đặt `errno = 0` trước lời gọi) và điều kiện đầu vào; không quy mọi kết quả `0` thành lỗi.

## 3. Sentinel: phân biệt “không có giá trị” với “gặp lỗi”

**Sentinel** là một giá trị được dành riêng để truyền tín hiệu đặc biệt. Nó chỉ an toàn khi ý nghĩa không mơ hồ trong ngữ cảnh hợp đồng.

| Sentinel | Bối cảnh | Cách hiểu an toàn |
| --- | --- | --- |
| `NULL` | Hàm trả con trỏ | Có thể có nghĩa lỗi, không tìm thấy, tùy chọn vắng mặt hoặc kết quả rỗng; phải đọc contract |
| `-1` | Hàm trả số nguyên | Chỉ là lỗi nếu `-1` bị loại khỏi miền dữ liệu hợp lệ hoặc có kênh lỗi bổ sung |
| `SIZE_MAX` hay `(size_t)-1` | Kích thước/chỉ số | Đây cũng là giá trị của `size_t`; tránh dùng làm “không tìm thấy” nếu miền dữ liệu bao gồm nó |
| `EOF` | `fgetc()` trong stdio | Giá trị kiểu `int` ngoài miền `unsigned char`; dùng `feof()`/`ferror()` để phân biệt nguyên nhân |
| `MAP_FAILED` | POSIX `mmap()` | Sentinel đặc thù, thường là `(void *)-1`; kiểm tra `MAP_FAILED` chứ không kiểm tra `NULL` |

Đừng trộn hai câu hỏi “tìm thấy không?” và “thao tác lỗi không?” vào cùng một sentinel khi chúng có những hướng xử lý khác nhau. Nếu hàm cần trả một giá trị âm hợp lệ, nên dùng `status + out_value`. Đối với lookup, có thể tách `API_OK` + `out_found` + `out_value`, hoặc định nghĩa mã “not found” riêng; chọn một và mô tả rõ.

## 4. Quyền sở hữu và vòng đời bộ nhớ

Trong native interoperability, **quyền sở hữu (ownership)** là trách nhiệm duy trì và giải phóng tài nguyên, không chỉ là quyền đọc/ghi. `const char *` nói rằng không sửa dữ liệu qua con trỏ đó; nó **không** tự nói ai sở hữu, dữ liệu sống bao lâu hoặc có phải gọi `free()` không.

| Dạng API | Ai sở hữu bộ nhớ | Caller có thể làm gì? | Khi nào hết hiệu lực? |
| --- | --- | --- | --- |
| Borrowed input: `const char *name` | Caller | Thư viện chỉ đọc trong lời gọi, không lưu lại nếu chưa có thỏa thuận | Caller kiểm soát; phải còn sống suốt lời gọi |
| Borrowed output: `const char *api_status_text(code)` | Thư viện/static | Đọc; không free, không ghi; copy nếu cần lưu lâu | Theo contract (ví dụ static tới hết tiến trình) |
| Owned output: `char **out_message` | Thư viện chuyển quyền sở hữu cho caller khi thành công | Đọc rồi gọi chính hàm release được công bố | Từ lúc tạo đến một lần release |
| Caller-provided buffer: `char *buf, size_t cap` | Caller | Thư viện ghi tối đa theo capacity, nêu rõ NUL/độ dài | Theo vòng đời buffer caller |
| Ownership transfer vào thư viện | Thư viện nhận quyền sau lời gọi thành công | Caller không dùng/free nữa sau điểm chuyển giao | Theo quy định riêng |

Các tình huống phải đặc biệt cẩn trọng:

- **Allocator/deallocator phải đi thành cặp.** Bộ nhớ tạo bằng allocator nội bộ của thư viện nên trả về qua `api_free()` của chính thư viện. Không tùy tiện gọi `free()` từ runtime khác trên Windows, `delete` của C++, `Unsafe.freeMemory()` hay đóng Java `Arena` để giải phóng bộ nhớ thư viện đã `malloc()`.
- **Không trả địa chỉ biến local trên stack.** Vùng nhớ mất hiệu lực ngay khi hàm C trả về, dù con trỏ khác `NULL`.
- **Không giữ con trỏ borrowed sau hạn dùng.** Bao gồm buffer của Java truyền vào native, con trỏ tới đối tượng đã release, hoặc pointer tới vùng cache thư viện có thể thay đổi ở lần gọi tiếp theo.
- **Một ownership, một lần release.** Đặt lại con trỏ local thành `NULL` sau khi giải phóng nếu nó còn được dùng; tránh double free. Khi một kết quả gồm nhiều con trỏ, phải quy định destructor cho toàn bộ cấu trúc.
- **Lifetime và thread-safety là hai điều khác nhau.** Con trỏ static có thể sống lâu nhưng dữ liệu vẫn có thể bị thay đổi đồng thời; tài liệu phải nêu rõ liệu có an toàn khi nhiều thread cùng đọc/gọi không.

Với Java FFM, `Arena` tự quản lý **các allocation tạo bởi arena**. Nó không mặc nhiên biết cách thu hồi con trỏ được thư viện C cấp phát và trả về. Với JNI, các cặp như `GetStringUTFChars/ReleaseStringUTFChars` hoặc `GetByteArrayElements/ReleaseByteArrayElements` là hợp đồng quản lý tài nguyên riêng, không thay thế cho hàm release của thư viện C.

## 5. Thiết kế một C ABI có thể gọi từ Java

Ví dụ dưới đây minh họa API tạo chuỗi `"Hello, " + name`. Để tách lỗi khỏi dữ liệu, hàm trả `int32_t` status, xuất `char *` và số **byte** qua hai out parameter. Thành công chuyển ownership của chuỗi sang caller; lỗi không chuyển ownership. `name` là chuỗi UTF-8 kết thúc bằng NUL, còn sống ít nhất trong lời gọi và không chứa NUL nhúng có chủ ý. `out_length` không gồm byte NUL cuối.

### 5.1. Header công khai: `demo_api.h`

```c
#ifndef DEMO_API_H
#define DEMO_API_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  if defined(DEMO_BUILD)
#    define DEMO_API __declspec(dllexport)
#  else
#    define DEMO_API __declspec(dllimport)
#  endif
#else
#  define DEMO_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum {
    API_OK = 0,
    API_EINVAL = 1,
    API_ENOMEM = 2,
    API_EOVERFLOW = 3
};

/*
 * Returns API_OK on success.
 * name: borrowed, valid NUL-terminated UTF-8 for this call.
 * out_message/out_length: required non-NULL pointers.
 * On success: *out_message is owned by caller and must be
 *              released once with api_free(); length excludes NUL.
 * On failure with valid out pointers: *out_message = NULL,
 *              *out_length = 0; nothing to free.
 * Thread-safe; no shared mutable state in this implementation.
 */
DEMO_API int32_t api_make_message(
    const char *name, char **out_message, size_t *out_length);

/* Accepts NULL; valid only for pointers returned as owned by this API. */
DEMO_API void api_free(void *p);

/* Returns borrowed, immutable, static-lifetime text; never free. */
DEMO_API const char *api_status_text(int32_t status);

#ifdef __cplusplus
}
#endif
#endif
```

Chú ý: status có số cố định, `extern "C"` giữ tên symbol theo C khi header được include từ C++, và macro export xử lý symbol trong shared library. Header là **hợp đồng công khai**; thay đổi cách cấp phát hoặc ý nghĩa status mà không cập nhật người gọi là lỗi tương thích.

### 5.2. Implementation: `demo_api.c`

```c
#include "demo_api.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

int32_t api_make_message(
    const char *name, char **out_message, size_t *out_length) {

    if (out_message == NULL || out_length == NULL) {
        return API_EINVAL;
    }

    *out_message = NULL;
    *out_length = 0;

    if (name == NULL) {
        return API_EINVAL;
    }

    static const char prefix[] = "Hello, ";
    const size_t prefix_len = sizeof(prefix) - 1;
    const size_t name_len = strlen(name);

    if (name_len > SIZE_MAX - prefix_len - 1) {
        return API_EOVERFLOW;
    }

    const size_t total_len = prefix_len + name_len;
    char *result = malloc(total_len + 1);
    if (result == NULL) {
        return API_ENOMEM;
    }

    memcpy(result, prefix, prefix_len);
    memcpy(result + prefix_len, name, name_len);
    result[total_len] = '\0';

    *out_message = result;
    *out_length = total_len;
    return API_OK;
}

void api_free(void *p) {
    free(p);
}

const char *api_status_text(int32_t status) {
    switch (status) {
        case API_OK:        return "ok";
        case API_EINVAL:    return "invalid argument";
        case API_ENOMEM:    return "out of memory";
        case API_EOVERFLOW: return "size overflow";
        default:           return "unknown status";
    }
}
```

Ở đây, `strlen()` chỉ an toàn vì precondition yêu cầu `name` trỏ tới chuỗi C hợp lệ có NUL kết thúc. Kiểm tra `name != NULL` không thể chứng minh một con trỏ bất kỳ là hợp lệ. Phép kiểm tra `SIZE_MAX - prefix_len - 1` ngăn cộng độ dài vượt `size_t` trước khi cấp phát. Việc set output rỗng trước các nhánh lỗi giúp caller không đọc nhầm pointer rác; hai output pointer bắt buộc phải hợp lệ.

Không đổi `malloc()` sang một allocator khác rồi để caller tự gọi `free()` trong tài liệu: caller chỉ biết quy tắc ổn định là `api_free()`. `api_status_text()` trả chuỗi literal tĩnh: **không** thuộc quyền sở hữu caller.

### 5.3. Caller C: `demo_client.c`

```c
#include "demo_api.h"

#include <inttypes.h>
#include <stdio.h>

int main(void) {
    char *message = NULL;
    size_t byte_count = 0;

    int32_t status =
        api_make_message("Java", &message, &byte_count);

    if (status != API_OK) {
        fprintf(stderr, "error=%s\n", api_status_text(status));
        return 1;
    }

    printf("status=%" PRId32 "\n", status);
    printf("bytes=%zu\n", byte_count);
    printf("text=%s\n", message);

    api_free(message);
    message = NULL;
    return 0;
}
```

Biên dịch và chạy trên Linux/macOS có compiler C11 (chương trình executable dùng trực tiếp hai source file):

```bash
cc -std=c11 -Wall -Wextra -Wpedantic demo_api.c demo_client.c -o demo_client
./demo_client
```

Output chính xác với input `"Java"` (7 byte `"Hello, "` + 4 byte `"Java"`):

```text
status=0
bytes=11
text=Hello, Java
```

Dù caller gặp ngoại lệ hoặc phải thoát sớm ở một nhánh khác, nó vẫn phải đưa mọi pointer đã nhận quyền sở hữu đến `api_free()` đúng một lần. Trong C, dùng cấu trúc cleanup thống nhất (ví dụ nhãn `cleanup:`) khi nhiều đường thoát cần giải phóng tài nguyên.

## 6. Gọi ABI trên từ Java bằng FFM (JDK 22+, Linux x64)

Java FFM cung cấp `Linker`, `SymbolLookup`, `FunctionDescriptor` và `MemorySegment` để gọi C function trực tiếp. Ví dụ này cố ý chốt **Linux 64-bit**, nơi `int32_t` khớp `JAVA_INT`, `size_t` và con trỏ là 8 byte; `size_t *` được đọc bằng `JAVA_LONG`. Nếu chạy trên ABI khác, kiểm tra lại mọi layout và đường dẫn shared library trước khi dùng.

Trước hết tạo thư viện chia sẻ từ cùng source C:

```bash
cc -std=c11 -fPIC -shared -DDEMO_BUILD demo_api.c -o libdemo_api.so
```

File `DemoFFM.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;

public class DemoFFM {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib = SymbolLookup.libraryLookup(
                Path.of("libdemo_api.so").toAbsolutePath(), arena);

            MethodHandle make = linker.downcallHandle(
                lib.find("api_make_message").orElseThrow(),
                FunctionDescriptor.of(
                    JAVA_INT, ADDRESS, ADDRESS, ADDRESS));
            MethodHandle release = linker.downcallHandle(
                lib.find("api_free").orElseThrow(),
                FunctionDescriptor.ofVoid(ADDRESS));

            MemorySegment input = arena.allocateFrom("Java");
            MemorySegment ptrSlot = arena.allocate(ADDRESS);
            MemorySegment lenSlot = arena.allocate(JAVA_LONG);
            ptrSlot.set(ADDRESS, 0, MemorySegment.NULL);
            lenSlot.set(JAVA_LONG, 0, 0L);

            int status = (int) make.invokeExact(
                input, ptrSlot, lenSlot);
            if (status != 0) {
                throw new IllegalStateException(
                    "Native status=" + status);
            }

            MemorySegment nativePtr = ptrSlot.get(ADDRESS, 0);
            long byteCount = lenSlot.get(JAVA_LONG, 0);

            try {
                if (nativePtr.equals(MemorySegment.NULL)
                        || byteCount < 0
                        || byteCount > Integer.MAX_VALUE) {
                    throw new IllegalStateException(
                        "Native result violates the ABI contract");
                }

                // The returned ADDRESS has unknown bounds.
                // Trust the documented length only while the allocation lives.
                byte[] bytes = nativePtr.reinterpret(byteCount)
                    .toArray(JAVA_BYTE);

                System.out.println("status=" + status);
                System.out.println("bytes=" + byteCount);
                System.out.println("text=" +
                    new String(bytes, StandardCharsets.UTF_8));
            } finally {
                // The C library owns the allocator and exports the release.
                release.invokeExact(nativePtr);
            }
        }
    }
}
```

Chạy với JDK 22+ tại thư mục chứa `libdemo_api.so`:

```bash
javac DemoFFM.java
java --enable-native-access=ALL-UNNAMED DemoFFM
```

Kết quả giống chương trình C: status bằng `0`, độ dài `11` byte và chuỗi `Hello, Java`. `Arena` giải phóng `input`, `ptrSlot` và `lenSlot` do Java cấp phát; `api_free(nativePtr)` giải phóng **riêng** chuỗi do thư viện C cấp phát. Pointer lấy từ vùng nhớ native thường được biểu diễn thành `MemorySegment` có độ dài 0 vì Java không tự biết kích thước của nó; chỉ `reinterpret(byteCount)` trong thời gian allocation còn sống mới cho phép copy đúng số byte. Một `reinterpret` với kích thước sai có thể gây lỗi truy cập bộ nhớ, nên chiều dài phải là một phần đáng tin cậy của hợp đồng.

Dùng `try/finally` để release kể cả khi giải mã chuỗi hoặc xử lý Java ném exception. Kiểm tra status **trước** khi dùng output. Ví dụ dùng `size_t` native 64 bit; không sao chép descriptor `JAVA_LONG` này sang tiến trình 32 bit. Trên Windows cần DLL tương ứng và ABI phù hợp; trên macOS cần thư viện có đuôi `.dylib`.

### 6.1. Nếu dùng JNI thay vì FFM

Cùng API C vẫn cần status và ownership như trên. JNI thường có một lớp `native` chuyển status thành exception Java, rồi trả dữ liệu managed. Khi JNI lấy một bản sao hoặc pin chuỗi/mảng Java bằng các hàm JNI, phải gọi đúng hàm `Release...` tương ứng. Đặc biệt, `GetStringUTFChars()` / `NewStringUTF()` dùng **Modified UTF-8** của JNI; nó không đồng nhất hoàn toàn với UTF-8 chuẩn của C ABI, nhất là ở NUL và ký tự bổ sung Unicode. Hãy quy định cách chuyển encoding, không ngầm coi hai định dạng là như nhau.

Nếu JNI gọi `api_make_message()`, lớp cầu nối nên: chuẩn bị input đúng encoding → gọi C → kiểm tra status → chuyển/copy nội dung thành đối tượng Java → giải phóng pointer C qua `api_free()` trong mọi nhánh hợp lệ. Không lưu pointer C thô trong một `long` phía Java nếu chưa thiết kế rõ handle, đồng bộ hóa và thời điểm đóng.

## 7. Các lỗi thiết kế dễ dẫn đến sự cố

| Mùi lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Trả `-1` nhưng `-1` cũng là dữ liệu hợp lệ | Không phân biệt kết quả và lỗi | Tách status và out parameter |
| Chỉ nhìn `errno != 0` | `errno` có thể là giá trị còn lại từ lời gọi trước | Dò kết quả thất bại theo contract, rồi mới đọc `errno` |
| Dereference output khi status lỗi | Out parameter có thể chưa hợp lệ | Khởi tạo output nhất quán; chỉ đọc khi thành công |
| `malloc(0) == NULL` được coi là chắc chắn hết bộ nhớ | C cho phép nhiều hành vi với cấp phát kích thước 0 | Định nghĩa riêng trường hợp kết quả rỗng/kích thước 0 |
| C trả con trỏ stack hoặc vùng đã free | Dangling pointer, có thể crash JVM | Trả owned heap, static borrowed hoặc buffer do caller cấp |
| Java đóng `Arena` rồi dùng input native | Con trỏ hết lifetime | Giữ arena sống trong suốt lời gọi và nhu cầu truy cập |
| Java chỉ đóng `Arena` cho output từ `malloc` C | Rò rỉ vì arena không sở hữu allocation đó | Gọi `api_free()` rõ ràng |
| Java gọi `free` sai allocator/runtime | Mất an toàn heap, nhất là biên DLL/CRT | Dùng cặp `api_alloc/api_free` của cùng thư viện |
| Ánh xạ `size_t` thành `int` cố định | Tràn/cắt độ dài, nhất là 64-bit | Chọn layout theo ABI và kiểm tra kích thước |
| `const char *` bị hiểu là “không cần free” | `const` chỉ ràng buộc quyền ghi qua pointer | Ghi rõ borrowed/owned và hàm release |
| Giữ pointer qua callback/thread mà không quy định | Có thể use-after-free hoặc data race | Định nghĩa lifetime, đồng bộ và ownership transfer |
| Tự ép `struct` C vào layout Java không đối chiếu | Padding/alignment và calling convention có thể khác | Dùng scalar + pointer đơn giản hoặc kiểm chứng layout ABI |

Cũng cần phân biệt **lỗi nghiệp vụ** (ví dụ không tìm thấy khóa, dữ liệu không hợp lệ) với **lỗi hệ thống** (hết bộ nhớ, lỗi I/O) và **vi phạm contract** (pointer đầu vào không hợp lệ, caller double free). Không nên cố “bắt” một use-after-free bằng việc kiểm tra status: undefined behavior có thể xảy ra trước khi status được trả về.

## 8. Kiểm thử hợp đồng và khả năng tương thích

Khi kiểm tra lớp C/Java, ưu tiên những trường hợp phản ánh chính xác boundary:

1. **Đường thành công:** `api_make_message("Java",...)` trả `API_OK`, pointer khác `NULL`, length bằng `11`, byte NUL ở vị trí `11`; `api_free()` đúng một lần.
2. **Đối số sai:** `name == NULL` với hai output pointer hợp lệ trả `API_EINVAL`, output pointer bằng `NULL`, length bằng `0`. Truyền output pointer `NULL` cũng trả `API_EINVAL` mà không dereference.
3. **Chuỗi rỗng:** input `""` là dữ liệu hợp lệ; trả chuỗi `"Hello, "` có length `7`, không nhầm thành lỗi.
4. **Cạnh kích thước:** phải kiểm tra phép cộng chống overflow; kiểm tra simulated allocation failure qua allocator giả/mocking hoặc fault injection, không thử cấp phát bừa một vùng khổng lồ.
5. **Vòng đời:** kiểm tra release trên mọi nhánh exception Java; công cụ như AddressSanitizer/LeakSanitizer/UBSan (khi toolchain hỗ trợ) giúp phát hiện leak, invalid free và undefined behavior của C.
6. **ABI:** build/test ít nhất từng kiến trúc và OS thực sự hỗ trợ; xác nhận độ rộng `size_t`/pointer, tên symbol, calling convention, UTF-8 và cách gọi hàm export.
7. **Thread:** chạy đồng thời chỉ khi contract cam kết thread-safe; thử đường lỗi từ nhiều thread, tránh chia sẻ `Arena.ofConfined()` qua thread khác.
8. **Phiên bản:** giữ nguyên mã status và hành vi release cũ; với status chưa biết, Java có thể báo lỗi tổng quát thay vì giả định success.

Một bảng contract tối thiểu nên được duy trì ngay bên cạnh header:

| Thuộc tính | Cam kết của `api_make_message` |
| --- | --- |
| Input | `name` borrowed, chuỗi C UTF-8 có NUL; hai output pointer bắt buộc hợp lệ |
| Thành công | Trả `API_OK (0)`; `*out_message` sở hữu bởi caller; `*out_length` là byte count không gồm NUL |
| Thất bại | Trả status khác 0; với output pointer hợp lệ, chúng được đặt về `NULL` và `0` |
| Cấp phát | Thư viện cấp phát bằng allocator của chính mình |
| Giải phóng | Caller gọi `api_free(*out_message)` đúng một lần |
| Chuỗi status | `api_status_text()` borrowed static, read-only, không cần free |
| Thread | Triển khai minh họa không dùng trạng thái mutable dùng chung |
| ABI | `int32_t` status, `char*`, `size_t*`; binding phải phù hợp ABI hiện hành |

## 9. Nguyên tắc áp dụng trong dự án thực tế

Khi chuẩn hóa một thư viện C cho Java, hãy mô tả bằng văn bản cùng header: **status và số enum cố định**, **dữ liệu output có hợp lệ khi nào**, **ý nghĩa từng sentinel**, **encoding và kích thước**, **owner/lifetime của từng pointer**, **hàm giải phóng đúng**, **thread-safety** và **ABI/phiên bản được hỗ trợ**. Chỉ ánh xạ sang Java exception hoặc đối tượng kết quả sau khi đọc đủ hợp đồng đó.

Tham khảo API chính thức cho FFM: [Java SE 22 – `java.lang.foreign`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html), [`SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html), [`MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).