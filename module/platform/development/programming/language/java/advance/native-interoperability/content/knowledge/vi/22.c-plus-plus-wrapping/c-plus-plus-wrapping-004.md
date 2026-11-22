# Giữ ngoại lệ, std::string và bộ cấp phát C++ bên trong lớp bao

## Mục tiêu bài học

Khi Java tích hợp một thư viện C++ bằng **Foreign Function & Memory API (FFM)** hoặc JNI, rủi ro không chỉ nằm ở việc gọi đúng symbol. Ngoại lệ C++, đối tượng **std::string**, cách bố trí class, vòng đời **new/delete** và allocator nội bộ không phải những thứ nên công khai nguyên dạng qua biên C ABI.

Một thiết kế dễ kiểm thử là tạo **lớp bao C ABI** (C-compatible wrapper) làm ranh giới: phía Java chỉ thấy mã trạng thái, các kiểu dữ liệu có độ rộng đã xác định, con trỏ opaque, buffer byte có capacity/length rõ ràng và một hàm giải phóng tương ứng. Phía C++ giữ exception, STL types, destructor, RAII và allocator trong cùng thư viện.

Bài này giúp bạn:

1. Giải thích tại sao **extern "C" không tự biến std::string hoặc exception thành C ABI ổn định**.
2. Bắt tất cả exception C++ bên trong wrapper **noexcept**, chuyển thành mã lỗi để Java xử lý.
3. Giữ **std::string** bên trong; truyền qua biên bằng **const char* + byte length**, hoặc **char* output + capacity + required length**.
4. Giữ đối tượng C++ qua **opaque handle** và gọi matching **create/release**, không trộn new/delete với malloc/free.
5. Dùng RAII, **std::unique_ptr**, try/finally và Arena để giữ đúng ownership khi có exception.
6. Chạy ví dụ hoàn chỉnh: **C header + C++17 implementation + Java 22+ FFM**, với lệnh build Linux/macOS/Windows, mã lỗi xác định và stdout dự kiến.
7. Phân tích lỗi phổ biến về Unicode, ABI, thread safety, lifetime, output buffer, double-free, library unloading và nâng cấp binary.

**Phiên bản:** API java.lang.foreign được hoàn thiện trong **JDK 22 (JEP 454)**, nên mã Java FFM ở đây yêu cầu JDK 22+. Nếu phải chạy trên Java 17, dùng JNI adapter phù hợp nhưng vẫn áp dụng cùng nguyên tắc C++ wrapper.

## 1. Phân chia trách nhiệm ở ranh giới

~~~text
              Java application
       String / exceptions / Arena
                     |
          FFM downcall hoặc JNI
                     |
       +--------------------------+
       | Public C ABI             |
       | int32_t status           |
       | char* + byte length      |
       | opaque bridge_handle*    |
       | bridge_release(handle)   |
       +--------------------------+
                     |
          C++ wrapper (noexcept)
          catches all exceptions
          converts status/errors
                     |
        Internal C++ implementation
        std::string / std::vector
        std::unique_ptr / new/delete
        custom allocator / RAII
~~~

**Đường ranh này là một hợp đồng, không phải một thủ thuật name mangling.** Java không cần biết std::string có small-string optimization hay không, destructor C++ hoạt động thế nào, vtable/class layout ra sao hoặc compiler dùng exception unwinding runtime nào.

### Vì sao không xuất class C++ trực tiếp?

C++ chuẩn hóa hành vi của class/STL, nhưng không chuẩn hóa binary layout của std::string, kiểu trả về aggregate, vtable và name mangling giữa các compiler/runtime. FFM Linker gọi native function theo **FunctionDescriptor do lập trình viên cung cấp**, không tự khám phá mọi quy tắc C++ template và object model.

Header sau **không phải C ABI thuần** dù có extern "C":

~~~cpp
extern "C" std::string make_label(); // KHÔNG NÊN.
extern "C" const std::exception* last_exception(); // KHÔNG NÊN.
~~~

Java phải đoán layout/lifetime/allocator của những C++ objects để sử dụng kết quả. Một cách tốt hơn là:

~~~c
typedef struct bridge_handle bridge_handle;

int32_t bridge_create(
    const char* bytes,
    int32_t byte_length,
    bridge_handle** out_handle
);
int32_t bridge_render(
    const bridge_handle* handle,
    int32_t repeat,
    char* out_bytes,
    int32_t capacity_bytes,
    int32_t* out_required_bytes
);
void bridge_release(bridge_handle* handle);
~~~

Đây là phần **minh họa cấu trúc API**; header đầy đủ với macros export/noexcept nằm ở mục 6. Tên struct được công bố, còn định nghĩa của nó **không công khai**.

## 2. C++ exceptions phải được bắt trước khi rời wrapper

### extern "C" không tự bắt exception

~~~cpp
extern "C" int32_t bad_function() {
    throw std::runtime_error("failure"); // CỐ Ý SAI.
}
~~~

extern "C" chủ yếu điều khiển language linkage/tên symbol; nó **không** chuyển exception C++ thành Java Throwable, và không bảo đảm một Java FFM downcall có thể catch exception C++ như RuntimeException. Để exception thoát xuyên foreign boundary có thể dẫn tới terminate, crash hoặc hành vi không xác định.

### Mẫu noexcept và status code

~~~cpp
extern "C" int32_t safe_function(int32_t value) noexcept {
    try {
        if (value < 0) {
            throw std::invalid_argument("negative input");
        }
        return 0;   // OK
    } catch (const std::invalid_argument&) {
        return 1;   // INVALID_ARGUMENT
    } catch (const std::out_of_range&) {
        return 2;   // OUT_OF_RANGE
    } catch (const std::bad_alloc&) {
        return 3;   // NO_MEMORY
    } catch (...) {
        return 5;   // INTERNAL_ERROR
    }
}
~~~

Đây là snippet cần các header C++ tương ứng; không phải source đầy đủ. **noexcept** là cam kết hàm không ném ra caller; nếu exception thoát khỏi một noexcept function, C++ sẽ gọi **std::terminate**. Vì vậy catch toàn bộ exception ở wrapper là một phần correctness.

### Mã lỗi phải có ý nghĩa rõ ràng

| Status | Nghĩa trong API ví dụ | Hành động Java |
| ---: | --- | --- |
| **0** | OK | Chỉ khi đó dùng outputs bình thường |
| **1** | INVALID_ARGUMENT | Kiểm tra NULL, length âm, repeat âm |
| **2** | OUT_OF_RANGE | Vượt limit hoặc kích thước quá lớn |
| **3** | NO_MEMORY | Lỗi allocator/không đủ tài nguyên |
| **4** | BUFFER_TOO_SMALL | Đọc required byte length rồi cấp đủ |
| **5** | INTERNAL_ERROR | Lỗi bất ngờ trong thư viện; ghi nhận để điều tra |

**Các số trên do ví dụ tự định nghĩa**, không phải lỗi mặc định của Java FFM. Không catch(...) rồi trả OK, không xem mọi lỗi là “chuỗi rỗng”, và không tạo thêm std::string phức tạp trong catch khi bộ nhớ đang cạn.

### Ngoại lệ từ destructor

Các destructors của C++ resource đi qua public release function phải không ném. Nếu destructor ném trong một noexcept release, chương trình có thể terminate. Với đóng resource có thể thất bại, nên xem xét một **close** trả status trước, rồi **release** không throw để giải phóng allocation; phải quy định rõ trạng thái sau lỗi, không retry một cách mù quáng.

## 3. std::string phải được giữ ở phía C++

**std::string** quản bytes, capacity và allocator ở C++ side. Nó không phải một C struct với layout chuẩn. Không trả std::string by value hoặc pointer tới std::string cho Java đọc bằng MemoryLayout.

### Đầu vào: byte pointer + explicit length

~~~c
int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
);
~~~

C++ có thể dựng std::string từ **input_bytes** với **input_size_bytes**. Không dùng strlen hoặc constructor std::string(const char*) nếu bytes có thể chứa NUL ở giữa.

Đối với Java:

- **String.length()** đếm UTF-16 code units, không phải byte count UTF-8.
- Dùng **string.getBytes(StandardCharsets.UTF_8)**, sau đó truyền **byte[].length**.
- Ví dụ **é** có một UTF-16 code unit nhưng hai UTF-8 bytes; emoji bổ sung có hai UTF-16 code units nhưng bốn UTF-8 bytes.
- std::string lưu bytes; không tự kiểm chứng chuỗi là UTF-8 hợp lệ. Nếu library yêu cầu UTF-8, wrapper hoặc caller phải validate theo contract.
- Dữ liệu binary không nhất thiết là C string, và không bắt buộc có byte 0 kết thúc.

### Đầu ra: caller-provided byte buffer

Không trả pointer tới local.c_str():

~~~cpp
extern "C" const char* unsafe_name() {
    std::string local = "temporary";
    return local.c_str(); // Dangling sau khi return.
}
~~~

Một pointer c_str/data còn có thể bị vô hiệu hóa khi std::string bị mutate/reallocate hoặc object bị hủy. Phương án dễ kiểm soát là **copy bytes vào buffer mà Java cấp**:

~~~c
int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t capacity_bytes,
    int32_t *out_required_bytes
);
~~~

Quy tắc:

1. Khi gọi với **out_bytes=NULL, capacity=0**, C trả số **bytes cần thiết** qua out_required_bytes.
2. Nếu output không rỗng và không đủ capacity, C trả **BUFFER_TOO_SMALL** và **không ghi vượt bộ nhớ**.
3. Java cấp buffer đúng required bytes, gọi lại.
4. C++ sao chép **chính xác** số bytes; Java decode theo số byte thực, không dùng strlen.
5. **Required không tính NUL terminator** trong hợp đồng ví dụ. Nếu API khác xuất C string, phải định nghĩa rõ **có cộng một byte NUL** hay không.

**Lưu ý hai lượt query/copy:** Cần snapshot/immutable source hoặc versioning/bounded retry nếu chuỗi có thể thay đổi giữa hai lần gọi. Trong ví dụ, text của một handle không bị sửa sau khi tạo, nên required size ổn định.

## 4. C++ allocator và ownership phải nằm trong lớp bao

### Matching allocation/deallocation

| Ai cấp phát? | Ai giải phóng đúng cách? |
| --- | --- |
| C++ **new T** | C++ **delete p** qua owner tương ứng |
| C++ **new T[n]** | **delete[] p** |
| **malloc** | Matching **free** |
| Custom C++ allocator/pool | Chính API release của allocator/pool |
| **std::unique_ptr** | Deleter do C++ type nắm giữ |
| **Arena.allocate** từ Java FFM | Arena.close() của owner Arena |
| Object opaque được bridge_create chuyển quyền cho Java | **bridge_release** trong cùng thư viện C++ |

Không gọi libc free vào object được tạo bởi C++ new: destructor có thể không chạy, allocator có thể khác và native heap có thể bị hỏng. Trên Windows, việc trộn các C runtime heaps/toolchains khác nhau càng cần tránh.

### Opaque handle

Public C header chỉ khai báo:

~~~c
typedef struct bridge_handle bridge_handle;
~~~

Phía C++ định nghĩa nội dung thật:

~~~cpp
struct bridge_handle {
    std::string text;

    explicit bridge_handle(std::string value)
        : text(std::move(value)) {}
};
~~~

Java chỉ nhận **bridge_handle \*** như một ADDRESS; **không được reinterpret thành structLayout để đọc trực tiếp C++ class**.

### RAII đến đúng điểm chuyển quyền sở hữu

~~~cpp
std::unique_ptr<bridge_handle> pending(
    new bridge_handle(std::move(text))
);
// Nếu một bước còn có thể throw, pending sẽ tự cleanup.
// Khi mọi bước thành công:
*out_handle = pending.release();
~~~

Đây là snippet; biến text/out_handle phải tồn tại trong hàm đầy đủ. Nếu constructor hoặc xử lý ném trước release(), unique_ptr tự dọn object. Khi release() thành công, ownership được chuyển sang caller: Java phải gọi **bridge_release** đúng một lần.

**Một MemorySegment alias không tự tạo thêm quyền sở hữu.** Nhiều Java modules có thể giữ cùng địa chỉ nhưng chỉ một owner được release. Với Java AutoCloseable wrapper, dùng state/lock thích hợp nếu cần close idempotent; đừng vừa gắn Arena cleanup vừa manual free cho cùng handle.

## 5. Thiết kế public C ABI có thể include bằng C compiler

Các quyết định quan trọng:

- Dùng **extern "C"** dưới **#ifdef __cplusplus**, để C compiler vẫn đọc được header.
- Dùng export macro theo OS; trên Windows build DLL phải dùng **__declspec(dllexport)**.
- Dùng **noexcept** phía C++ trong prototype và definition, nhưng C compiler không có từ khóa đó.
- Cô lập class/stdlib type bằng **opaque pointer**.
- Ưu tiên **int32_t** cho status/length ở ví dụ để dễ ánh xạ **ValueLayout.JAVA_INT**.
- Ghi comments về **bytes**, **NULL**, **ownership**, error outputs và range.
- Giữ một **bridge_release** tương ứng với mỗi create thành công.

Không dùng C++ std::string, std::vector, std::exception, std::unique_ptr, C++ references hay templates trong public C ABI.

## 6. Ví dụ runnable — File cpp_bridge.h

Tạo file **cpp_bridge.h**:

~~~c
#ifndef CPP_BRIDGE_H
#define CPP_BRIDGE_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(BRIDGE_BUILD)
#    define BRIDGE_API __declspec(dllexport)
#  else
#    define BRIDGE_API __declspec(dllimport)
#  endif
#else
#  define BRIDGE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
#  define BRIDGE_NOEXCEPT noexcept
extern "C" {
#else
#  define BRIDGE_NOEXCEPT
#endif

/* Incomplete type, không xuất C++ class layout. */
typedef struct bridge_handle bridge_handle;

enum {
    BR_OK = 0,
    BR_INVALID_ARGUMENT = 1,
    BR_OUT_OF_RANGE = 2,
    BR_NO_MEMORY = 3,
    BR_BUFFER_TOO_SMALL = 4,
    BR_INTERNAL_ERROR = 5
};

/*
 * input_size_bytes: byte count, không phải C string length.
 * input_bytes có thể NULL khi input_size_bytes == 0.
 * out_handle != NULL; thành công chuyển ownership cho caller.
 * Thất bại: *out_handle == NULL, caller không được release.
 */
BRIDGE_API int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
) BRIDGE_NOEXCEPT;

/*
 * render text lặp repeat lần, giữa các lần là '|'.
 * repeat: 0..16. out_required_bytes != NULL.
 * output: bytes chính xác, KHÔNG NUL terminator.
 * Query size: out_bytes=NULL, capacity=0.
 */
BRIDGE_API int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t out_capacity_bytes,
    int32_t *out_required_bytes
) BRIDGE_NOEXCEPT;

/* Đúng một release trên mỗi handle còn sống. */
BRIDGE_API void bridge_release(
    bridge_handle *handle
) BRIDGE_NOEXCEPT;

/* Chỉ để kiểm tra ví dụ, không thay synchronization. */
BRIDGE_API int32_t bridge_active_handles(void) BRIDGE_NOEXCEPT;

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CPP_BRIDGE_H */
~~~

**Phân tích header:** BRIDGE_BUILD chọn export trên Windows; file implementation sẽ định nghĩa macro này trước khi include header. BRIDGE_NOEXCEPT giữ khai báo và định nghĩa cùng exception specification trong C++; khi biên dịch file C, macro rỗng. bridge_handle là incomplete type; nó không bị cấp phát bằng malloc từ phía C caller/Java.

### C ABI không đồng nghĩa binary chạy trên mọi hệ điều hành

Shared library phải build theo OS/CPU/ABI của JVM. Wrapper vẫn phải link những dependency C++ có runtime/compiler tương thích, dù public header tránh lộ C++ STL ABI. Khi thay C++ implementation, kiểm thử cùng bộ C signatures, mã status và semantics.

## 7. Ví dụ runnable — File cpp_bridge.cpp

Tạo file **cpp_bridge.cpp**:

~~~cpp
#define BRIDGE_BUILD
#include "cpp_bridge.h"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>

struct bridge_handle {
    std::string text;

    explicit bridge_handle(std::string input)
        : text(std::move(input)) {}
};

namespace {
    std::atomic<int32_t> live_handles{0};
    constexpr int32_t MAX_REPEAT = 16;
}

extern "C" BRIDGE_API int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
) noexcept {
    if (out_handle == nullptr) {
        return BR_INVALID_ARGUMENT;
    }
    *out_handle = nullptr;

    try {
        if (input_size_bytes < 0 ||
            (input_size_bytes > 0 && input_bytes == nullptr)) {
            throw std::invalid_argument("invalid input");
        }

        // Giữ nguyên byte sequence, kể cả embedded NUL.
        std::string text;
        if (input_size_bytes > 0) {
            text.assign(
                input_bytes,
                static_cast<std::size_t>(input_size_bytes)
            );
        }

        std::unique_ptr<bridge_handle> pending(
            new bridge_handle(std::move(text))
        );
        *out_handle = pending.release();
        live_handles.fetch_add(1, std::memory_order_relaxed);
        return BR_OK;
    } catch (const std::invalid_argument&) {
        return BR_INVALID_ARGUMENT;
    } catch (const std::bad_alloc&) {
        return BR_NO_MEMORY;
    } catch (...) {
        return BR_INTERNAL_ERROR;
    }
}

extern "C" BRIDGE_API int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t out_capacity_bytes,
    int32_t *out_required_bytes
) noexcept {
    if (out_required_bytes == nullptr) {
        return BR_INVALID_ARGUMENT;
    }
    *out_required_bytes = 0;

    try {
        if (handle == nullptr ||
            repeat < 0 ||
            out_capacity_bytes < 0 ||
            (out_capacity_bytes > 0 && out_bytes == nullptr)) {
            throw std::invalid_argument("invalid arguments");
        }
        if (repeat > MAX_REPEAT) {
            throw std::out_of_range("too many repeats");
        }

        const uint64_t n =
            static_cast<uint64_t>(handle->text.size());
        const uint64_t r = static_cast<uint64_t>(repeat);
        const uint64_t separatorBytes = r > 0 ? r - 1 : 0;
        const uint64_t required64 = n * r + separatorBytes;

        if (required64 >
            static_cast<uint64_t>(
                std::numeric_limits<int32_t>::max()
            )) {
            throw std::out_of_range("too many output bytes");
        }

        const int32_t required =
            static_cast<int32_t>(required64);
        *out_required_bytes = required;

        // Query size: không ghi nếu buffer không đủ.
        if (out_capacity_bytes < required) {
            return BR_BUFFER_TOO_SMALL;
        }

        std::string output;
        output.reserve(static_cast<std::size_t>(required));
        for (int32_t i = 0; i < repeat; ++i) {
            if (i > 0) {
                output.push_back('|');
            }
            output.append(handle->text);
        }

        if (required > 0) {
            std::memcpy(
                out_bytes, output.data(),
                static_cast<std::size_t>(required)
            );
        }
        return BR_OK;
    } catch (const std::invalid_argument&) {
        return BR_INVALID_ARGUMENT;
    } catch (const std::out_of_range&) {
        return BR_OUT_OF_RANGE;
    } catch (const std::length_error&) {
        return BR_OUT_OF_RANGE;
    } catch (const std::bad_alloc&) {
        return BR_NO_MEMORY;
    } catch (...) {
        return BR_INTERNAL_ERROR;
    }
}

extern "C" BRIDGE_API void bridge_release(
    bridge_handle *handle
) noexcept {
    if (handle == nullptr) {
        return;
    }

    // delete gọi đúng C++ destructor và matching allocator.
    // Handle PHẢI còn sống; double-delete là undefined behavior.
    delete handle;
    live_handles.fetch_sub(1, std::memory_order_relaxed);
}

extern "C" BRIDGE_API int32_t bridge_active_handles(
    void
) noexcept {
    return live_handles.load(std::memory_order_relaxed);
}
~~~

### Điểm quan trọng trong C++ code

**bridge_create:** Tham số out_handle hợp lệ được đặt NULL trước khi tạo object. std::unique_ptr sở hữu object trong giai đoạn còn có thể throw. Khi release() xảy ra, Java caller được chuyển ownership đúng một lần. Nếu lỗi trước đó, destructor/RAII tự cleanup.

**bridge_render:** Dùng std::string nội bộ nhưng chỉ copy **bytes** ra caller buffer. Tính size trong **uint64_t**, từ chối vượt INT32_MAX, sau đó kiểm tra capacity. Khi capacity=0 và output có dữ liệu, trả **BR_BUFFER_TOO_SMALL** cùng required. Dữ liệu đầu ra **không có NUL terminator**.

**bridge_release:** delete opaque handle tại đúng C++ module, nên destructor std::string được chạy. API không tự an toàn với handle đã free; Java phải đảm bảo release đúng một lần.

**bridge_active_handles:** std::atomic chỉ hỗ trợ diagnostic; nó không bảo vệ thao tác render và release trên **cùng một handle** nếu bị gọi đồng thời.

### Exceptions được chuyển thành status ở đâu?

| Lỗi/exception trong C++ | Status C |
| --- | --- |
| Input null/negative: std::invalid_argument | **1** |
| repeat > 16 hoặc output quá lớn: std::out_of_range | **2** |
| std::length_error | **2** |
| std::bad_alloc | **3** |
| Capacity thiếu | **4** |
| Exception không dự kiến | **5** |
| Thành công | **0** |

Không exception C++ nào được phép thoát qua exported C functions. Với một C++ library bên thứ ba không kiểm soát được destructor hoặc custom allocator, cần review lại contract trước khi công bố noexcept; không được suy luận code native luôn an toàn chỉ vì có catch(...).

## 8. Ví dụ runnable — File CppBridgeDemo.java (JDK 22+)

Tạo file **CppBridgeDemo.java**:

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

public final class CppBridgeDemo {
    private static final int OK = 0;
    private static final int OUT_OF_RANGE = 2;
    private static final int BUFFER_TOO_SMALL = 4;

    private CppBridgeDemo() {
    }

    private static void expect(int actual, int expected) {
        if (actual != expected) {
            throw new IllegalStateException(
                "Native status " + actual +
                ", expected " + expected
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Library phải sống dài hơn mọi C++ handle.
        try (Arena libraryArena = Arena.ofConfined()) {
            Path lib = Path.of(
                System.mapLibraryName("cppbridge")
            ).toAbsolutePath();

            SymbolLookup symbols =
                SymbolLookup.libraryLookup(lib, libraryArena);

            // int32_t bridge_create(const char*, int32_t, handle**)
            MethodHandle create = linker.downcallHandle(
                symbols.find("bridge_create").orElseThrow(),
                FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
                )
            );

            // int32_t bridge_render(handle*, int32_t,
            //                       char*, int32_t, int32_t*)
            MethodHandle render = linker.downcallHandle(
                symbols.find("bridge_render").orElseThrow(),
                FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
                )
            );

            MethodHandle release = linker.downcallHandle(
                symbols.find("bridge_release").orElseThrow(),
                FunctionDescriptor.ofVoid(
                    ValueLayout.ADDRESS
                )
            );

            MethodHandle active = linker.downcallHandle(
                symbols.find("bridge_active_handles").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            try (Arena arena = Arena.ofConfined()) {
                byte[] bytes = "Native++".getBytes(
                    StandardCharsets.UTF_8
                );

                // C cần native pointer, không đọc trực tiếp heap array.
                MemorySegment input = arena.allocate(bytes.length);
                input.copyFrom(MemorySegment.ofArray(bytes));

                // C++ ghi bridge_handle* vào vùng chứa một ADDRESS.
                MemorySegment handleSlot =
                    arena.allocate(ValueLayout.ADDRESS);
                handleSlot.set(
                    ValueLayout.ADDRESS, 0, MemorySegment.NULL
                );

                int created = (int) create.invokeExact(
                    input, bytes.length, handleSlot
                );
                expect(created, OK);

                MemorySegment handle = handleSlot.get(
                    ValueLayout.ADDRESS, 0
                );
                if (handle.address() == 0L) {
                    throw new IllegalStateException("NULL handle");
                }

                // Java chỉ dùng ADDRESS opaque: không reinterpret class.
                try {
                    int live = (int) active.invokeExact();

                    MemorySegment requiredSlot =
                        arena.allocate(ValueLayout.JAVA_INT);
                    requiredSlot.set(ValueLayout.JAVA_INT, 0, 0);

                    // Query số bytes thực.
                    int query = (int) render.invokeExact(
                        handle, 2, MemorySegment.NULL,
                        0, requiredSlot
                    );
                    expect(query, BUFFER_TOO_SMALL);

                    int required = requiredSlot.get(
                        ValueLayout.JAVA_INT, 0
                    );
                    if (required <= 0 || required > 1024) {
                        throw new IllegalStateException(
                            "Output size unsupported: " + required
                        );
                    }

                    // Cấp buffer Java-owned; C chỉ mượn trong call.
                    MemorySegment output = arena.allocate(required);
                    int copied = (int) render.invokeExact(
                        handle, 2, output, required, requiredSlot
                    );
                    expect(copied, OK);

                    int written = requiredSlot.get(
                        ValueLayout.JAVA_INT, 0
                    );
                    if (written != required) {
                        throw new IllegalStateException(
                            "Output length changed"
                        );
                    }

                    String result = new String(
                        output.toArray(ValueLayout.JAVA_BYTE),
                        StandardCharsets.UTF_8
                    );

                    // std::out_of_range trong C++ -> status 2 ở Java.
                    int bad = (int) render.invokeExact(
                        handle, 17, MemorySegment.NULL,
                        0, requiredSlot
                    );
                    expect(bad, OUT_OF_RANGE);

                    System.out.println("activeWhileOpen=" + live);
                    System.out.println("requiredBytes=" + required);
                    System.out.println("output=" + result);
                    System.out.println("outOfRangeStatus=" + bad);
                } finally {
                    // MỘT Java owner thực hiện MỘT release.
                    release.invokeExact(handle);
                }

                int after = (int) active.invokeExact();
                System.out.println("activeAfterClose=" + after);
            }
        }
    }
}
~~~

**Đọc FunctionDescriptor:** Create nhận ADDRESS (input), JAVA_INT (byte length), ADDRESS (pointer-to-pointer); render nhận ADDRESS, JAVA_INT, ADDRESS, JAVA_INT, ADDRESS và trả JAVA_INT; release nhận ADDRESS và trả void. Không có descriptor nào cố mô hình hóa std::string.

**MemorySegment handle** chỉ là native pointer opaque; không dereference. **handleSlot** và **output/input** do Java Arena cấp nhưng **bridge_handle** do C++ new cấp, nên cần bridge_release trong finally. Library arena phải còn sống khi release chạy.

### Một chi tiết về JNI

Nếu cùng wrapper được gọi từ JNI thay vì FFM, JNI native method nhận JNIEnv đúng thread và có thể chuyển mã lỗi sang Java exception bằng JNI **ThrowNew** sau khi C++ wrapper trả. Nhưng JNI adapter cũng không được để C++ exception thoát vào JVM. Hợp đồng bytes/length, opaque handle và matching destructor vẫn giữ nguyên.

## 9. Biên dịch và chạy

Chuẩn bị ba file trong cùng thư mục: **cpp_bridge.h**, **cpp_bridge.cpp**, **CppBridgeDemo.java**. Cần JDK 22+ và toolchain C++17 tương thích OS/CPU/JVM.

**Linux:**

~~~bash
g++ -std=c++17 -O2 -fPIC -shared \
  cpp_bridge.cpp -o libcppbridge.so
~~~

**macOS:**

~~~bash
clang++ -std=c++17 -O2 -fPIC -dynamiclib \
  cpp_bridge.cpp -o libcppbridge.dylib
~~~

**Windows, Developer Command Prompt của MSVC:**

~~~bat
cl /nologo /EHsc /std:c++17 /LD cpp_bridge.cpp /link /OUT:cppbridge.dll
~~~

Chọn **một phương án** theo OS. Thư viện phải build cùng kiến trúc với JDK đang chạy. System.mapLibraryName("cppbridge") tạo đúng tên file theo OS tương ứng.

Sau khi build:

~~~bash
javac CppBridgeDemo.java
java --enable-native-access=ALL-UNNAMED CppBridgeDemo
~~~

Vì FFM dùng restricted native calls/library lookup, classpath demo bật **ALL-UNNAMED**. Trong ứng dụng modularized, cấp native access cho đúng module khi có thể.

**Stdout dự kiến chính xác khi build/load và native calls thành công:**

~~~text
activeWhileOpen=1
requiredBytes=17
output=Native++|Native++
outOfRangeStatus=2
activeAfterClose=0
~~~

Giải thích: **Native++** dài tám ASCII bytes; hai bản cùng dấu **|** ngăn cách có 8+1+8=17 bytes. C++ tạo một handle (counter=1), Java query/copy đúng 17 bytes rồi decode. Khi repeat=17, wrapper bắt std::out_of_range và trả status 2. Finally gọi bridge_release đúng một lần (counter về 0).

**Phạm vi kiểm chứng:** Source mẫu và output đã được rà soát theo contract, nhưng vẫn cần build/test trên JDK/toolchain mục tiêu; không nên hiểu stdout minh họa là kết quả đã chạy trên mọi nền tảng.

## 10. Lỗi về lifetime và allocator cần đặc biệt chú ý

### Đừng free bằng Java Arena một C++ object

Đóng Arena giải phóng **input/output/handleSlot** do Arena cấp; nó **không tự delete BridgeHandle** do C++ tạo. Handle cần matching bridge_release, dù Java chỉ nhìn thấy MemorySegment ADDRESS.

### Đừng gọi release hai lần

Nếu hai Java wrappers cùng giữ một handle, việc mỗi wrapper gọi release có thể **double-delete**. Một owner phải chịu trách nhiệm duy nhất. Java có thể dùng AutoCloseable với state/lock nếu muốn bảo vệ close, nhưng **đừng đồng thời** đăng ký một cleanup action thứ hai cho cùng handle.

### Đừng unload thư viện trước release

MethodHandle native trỏ vào code của thư viện. Khi SymbolLookup.libraryLookup liên kết library lifetime với Arena, thư viện có thể được unload khi arena đóng. Vì vậy **libraryArena** cần sống lâu hơn **C++ handle** và mọi lần bridge_release.

### Đừng dùng handle sau close

Một opaque address trả từ C có thể vẫn là cùng giá trị long sau khi release, nhưng vùng nhớ đã được delete. **MemorySegment ADDRESS không tự biết object C++ đã free**; FFM không thể tự chặn mọi use-after-free ở native code.

### Đừng release đồng thời với render

Atomic counter trong demo không làm BridgeHandle thread-safe. Nếu worker đang dùng handle và một luồng khác gọi release, có thể crash. Dùng owner lifecycle: ngừng nhận call, đợi in-flight calls hoàn tất, rồi release. Nếu C++ implementation mutable, cần thêm mutex/synchronization theo contract.

## 11. Unicode, error messages và ABI production

**Encoding:** std::string lưu bytes, không tự validate UTF-8. Java nên dùng explicit UTF-8; nếu C API yêu cầu UTF-16 hoặc locale-dependent encoding, phải tạo adapter riêng và ghi contract. Embedded NUL nên được test vì strlen làm mất dữ liệu phía sau NUL.

**Error messages:** Không trả pointer đến std::exception::what() sau khi exception object hết scope. Nếu cần nội dung lỗi, hãy copy bytes vào caller-owned buffer hoặc trả opaque error handle có hàm destroy. Thread-local last-error message có thể bị ghi đè bởi lời gọi kế tiếp, nên đọc ngay và ghi rõ thread/overwrite contract.

**C ABI versioning:** Khi nâng cấp thư viện, không âm thầm đổi số/kiểu tham số của một exported symbol. Có thể thêm hàm **bridge_api_version()** hoặc API mới cho kích thước 64 bit. Với output lớn hơn 2 GiB, int32_t capacity không đủ: thiết kế giao thức 64-bit riêng, kiểm tra unsigned/range.

**Compiler và runtime:** Public C ABI giảm phụ thuộc vào C++ object layout ở phía Java, nhưng bản thân thư viện và C++ dependencies vẫn cần compiler, standard library và runtime tương thích. Phải build/test mỗi platform.

**Errors:** C++ exception chuyển thành status không có nghĩa nguyên nhân đã được khắc phục. Java cần ánh xạ mã lỗi thành exception/Result có ngữ cảnh và có quy trình giám sát. Nếu custom allocator/driver cần thread-affine destruction, bridge_release cũng phải được gọi trên thread phù hợp.

**C++ callbacks:** Nếu thư viện C++ gọi callback Java từ native threads, phải quản lifetime của upcall stub/Arena, unregister/drain trước khi đóng. Java upcall callback không được để Java exception thoát qua C ABI; catch và báo lỗi theo hợp đồng callback.

## 12. Bảng lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xuất std::string by value trong extern "C" | Lộ C++ ABI/allocator | Bytes + length hoặc opaque handle |
| C++ exception vượt FFM/JNI | Crash/terminate/undefined behavior | noexcept + catch/status |
| Catch(...) trả OK | Che lỗi | INTERNAL status/diagnostics |
| Tạo error message bằng allocation trong bad_alloc handler | Có thể throw lại | Status constant hoặc buffer đã có |
| Trả local.c_str() | Dangling pointer | Copy sang buffer caller |
| Giữ pointer text.data() rồi mutate text | Invalidation | Borrowed contract ngắn hoặc copy |
| Dùng String.length làm UTF-8 byte length | Sai capacity/overflow | Encode rồi lấy byte[].length |
| Dùng strlen với dữ liệu chứa NUL | Truncated data | Explicit length |
| C memcpy không kiểm tra capacity | Buffer overflow | Query size + bounded copy |
| Java free C++ new object bằng libc free | Wrong allocator, không chạy destructor | Matching bridge_release |
| Gắn hai cleanup paths cho một handle | Double-free | Một owner |
| Java đọc C++ object qua structLayout | Layout không public/stable | Handle opaque |
| Close library trước handle | Function pointer đã unload | Release trước library close |
| Release đồng thời với render | Native use-after-free | Stop/drain/lock |
| Query/copy khi source thay đổi | Mismatch length | Snapshot/version/retry có giới hạn |
| Bỏ qua build matrix OS/ABI | Load/symbol errors | Compile/test per target |

## 13. Checklist trước khi dùng trong production

- [ ] Public header được C compiler đọc được; không lộ STL/C++ class.
- [ ] extern "C", export symbol và ABI được kiểm tra trên binary thực.
- [ ] FunctionDescriptor khớp đúng C signature/return types.
- [ ] Mọi C ABI entry point bắt exception C++ và không ném qua biên.
- [ ] Status/error semantics và outputs khi lỗi được mô tả tường minh.
- [ ] String qua biên có encoding, byte length, NULL và terminator policy.
- [ ] Không trả pointer đến buffer của std::string đã hủy hoặc có thể mutate.
- [ ] C++ giữ ownership nội bộ bằng RAII, transfer chỉ khi thành công.
- [ ] Có matching release function; Java không trộn allocator và không double-release.
- [ ] Library sống lâu hơn mọi handle/callback và thao tác cleanup.
- [ ] Hai lượt query/copy có kiểm tra capacity, integer overflow và dữ liệu mutable.
- [ ] Thread-safety, close race và affinity được xác định theo C++ contract.
- [ ] Test input rỗng, embedded NUL, UTF-8, repeat âm/quá giới hạn, buffer thiếu và allocation failure.
- [ ] Test startup/shutdown, version compatibility, sanitizer/native heap diagnostics trên OS/CPU/JDK mục tiêu.
- [ ] Không dùng Java exception như cơ chế bắt lỗi native heap corruption.

## 14. Câu hỏi tự kiểm tra

**1. extern "C" có làm std::string trở thành struct C chuẩn không?**

Không. Nó điều khiển linkage, không chuẩn hóa binary layout của STL type.

**2. Vì sao phải catch ngoại lệ C++ trong wrapper?**

Vì C ABI/FFM không có hợp đồng truyền exception C++ thành Java Throwable; để thoát có thể terminate/crash.

**3. Hàm C++ tạo object bằng new thì Java gọi hàm nào để dọn?**

Hàm **bridge_release** do cùng thư viện công bố, không gọi libc free trực tiếp.

**4. Vì sao cần byte count khi truyền UTF-8?**

Java String.length đếm UTF-16 code units, không phải UTF-8 bytes; byte count còn bảo toàn embedded NUL.

**5. Tại sao không trả pointer từ một std::string local?**

Nó bị hủy sau khi hàm return nên pointer trở thành dangling.

**6. Hai lượt query/copy có yêu cầu gì?**

Required length phải được đo theo byte; buffer đủ capacity; dữ liệu nguồn phải ổn định hoặc có cơ chế retry/snapshot phù hợp.

**7. std::bad_alloc trong C++ được Java nhìn thấy thế nào ở ví dụ?**

Wrapper bắt nó và trả mã số **3 (BR_NO_MEMORY)**, không đưa C++ exception object qua FFM.

**8. Vì sao finally cần release dù Java render ném exception?**

Vì ownership của handle đã được chuyển khi create thành công; lỗi sau đó không làm C++ tự delete allocation.

**9. Arena.close có tự hủy BridgeHandle tạo bằng new không?**

Không. Arena chỉ sở hữu allocations do Arena cấp; BridgeHandle cần matching C++ release.

**10. Khi nào được release một handle dùng ở nhiều worker?**

Khi đã ngừng nhận call mới và chắc chắn mọi native consumer/in-flight call hoàn tất theo thread-safety contract.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- [Oracle Java 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle Java 22 — Linker / FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle Java 22 — SymbolLookup và lifetime của shared library](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java 22 — MemorySegment (copy, scope, access)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [C++ language — Exceptions](https://en.cppreference.com/w/cpp/language/exceptions).
- [C++ basic_string reference](https://en.cppreference.com/w/cpp/string/basic_string).

**Kết luận:** **C++ wrapper nên giữ exception, std::string, RAII và allocator bên trong**, chỉ công khai một C ABI với kiểu dữ liệu rõ, status code, byte buffers và matching release. Thiết kế này giúp Java FFM/JNI tránh phụ thuộc STL ABI, ngăn C++ exception thoát qua boundary, kiểm soát quyền sở hữu và giảm nguy cơ tràn buffer, double-free, leak hoặc use-after-free.
