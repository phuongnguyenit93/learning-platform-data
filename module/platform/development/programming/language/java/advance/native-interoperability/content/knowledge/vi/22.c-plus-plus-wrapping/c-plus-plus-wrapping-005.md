# Chuyển dữ liệu bằng vùng đệm và độ dài thay vì lộ kiểu nội bộ khi bao bọc thư viện C++

Khi Java cần sử dụng một thư viện C++, việc đưa trực tiếp `std::string`, `std::vector`, `std::map` hoặc C++ class object qua ranh giới JNI/FFM là một lựa chọn rủi ro. Các kiểu C++ này có layout, allocator, destructor, quy tắc copy/move và ABI chịu ảnh hưởng compiler, C++ standard library và cách build. Java không biết giải mã một object `std::vector` thành mảng bytes chỉ bằng địa chỉ của object đó.

Cách thiết kế bền vững hơn là **ẩn toàn bộ C++ implementation phía sau một C-compatible façade**, trao đổi dữ liệu thông qua **con trỏ vùng đệm + độ dài**, và với kết quả có thêm **dung lượng buffer + số bytes đã ghi/cần thiết + mã trạng thái**:

```c
int xb_encode(const uint8_t *input, size_t input_length,
              uint8_t *output, size_t output_capacity,
              size_t *output_length);
```

Phía trong `xb_encode` có thể dùng `std::vector<std::uint8_t>`, `std::string` và thuật toán C++ phức tạp. Phía ngoài, C/JNI/FFM chỉ nhìn thấy các C types được mô tả rõ. Cách làm này giúp tách **ABI** khỏi **cấu trúc dữ liệu nội bộ**, minh bạch về lifetime/ownership và tránh trả pointer tới các C++ temporaries đã bị hủy.

**Nguyên tắc:** chỉ có `pointer + length` chưa đủ để an toàn. Contract phải xác định rõ **length theo byte**, **capacity tối đa**, **null/empty**, **ai cấp phát và giải phóng**, **C++ exceptions**, **encoding**, **output khi lỗi** và **có giữ pointer sau return không**.

## 1. Vì sao không xuất các kiểu C++ nội bộ?

Một C++ API tiện lợi nội bộ có thể có dạng:

```cpp
#include <string>
#include <vector>

namespace internal {
    class Codec {
    public:
        std::vector<unsigned char> encode(
                const std::vector<unsigned char>& data) const;
        std::string description() const;
    };
}
```

Đây là **đoạn khai báo minh họa**, không phải class hoàn chỉnh có implementation. Nó hợp lý cho caller C++ được build với ABI phù hợp, nhưng không phải contract để Java suy diễn trực tiếp về binary representation.

Các vấn đề thường gặp:

- `std::vector` không phải mảng bytes được đặt trực tiếp ở địa chỉ object. Object giữ metadata, còn phần tử thường nằm tại allocation riêng. C++ standard không buộc mọi compiler có cùng object layout.
- `std::string` không bảo đảm encoding là UTF-8; có thể chứa binary bytes, embedded NUL và có chính sách Small String Optimization khác nhau.
- C++ symbol names có name mangling; `extern "C"` giúp function name có C linkage nhưng **không** làm `std::vector` trở thành một C ABI type.
- C++ allocators/CRT runtimes có thể khác nhau; `free`, `delete`, `delete[]` và thư viện-specific destroy API không thay thế nhau.
- C++ exception không được để tự động vượt C ABI/JNI/FFM boundary rồi mong Java bắt như Java exception.
- `std::vector::data()` có thể bị invalidated khi vector reallocate; `std::string::c_str()` hết hiệu lực khi owner bị hủy hoặc thao tác làm thay đổi storage.
- Java có GC và JNI references; nó không tự chạy C++ destructor cho một địa chỉ không có owner contract.

Hai chống-mẫu:

```cpp
// Sai: trả địa chỉ bên trong một C++ temporary.
extern "C" const char *bad_result() {
    std::string local = "temporary";
    return local.c_str();  // Dangling ngay khi local bị hủy.
}

// Sai: C linkage không khiến std::vector là C ABI.
extern "C" std::vector<unsigned char> bad_vector_api();
```

**Cách sửa:** giữ `std::string`/`std::vector` bên trong implementation, rồi **copy dữ liệu cần thiết vào một buffer caller sở hữu** trước khi C++ object hết lifetime. Nếu cần giữ state C++ lâu dài, hãy dùng một **opaque C handle** kèm create/destroy; dữ liệu vẫn trao đổi qua buffers.

## 2. Hợp đồng đầy đủ cho buffer + length

| Đối số | Nghĩa chính xác | Điều caller/callee phải bảo đảm |
| --- | --- | --- |
| `input` | Địa chỉ vùng bytes đọc | Nếu `input_length > 0`, trỏ tới ít nhất bấy nhiêu bytes hợp lệ |
| `input_length` | Số bytes hợp lệ của input | Không nhầm với ký tự Java/Unicode hoặc số phần tử của kiểu khác |
| `output` | Địa chỉ vùng có thể ghi | Buffer caller cấp và sở hữu; không phải con trỏ output do callee malloc |
| `output_capacity` | Số bytes tối đa được phép ghi | Có thể lớn hơn output thực tế; không bao giờ ghi vượt capacity |
| `output_length` | Con trỏ tới `size_t` do caller cấp | Callee ghi required size nếu thiếu cap; written size nếu thành công |
| Status `int` | Mã kết quả có contract | Không dùng length=0 làm dấu hiệu lỗi nếu empty output hợp lệ |

**Contract được sử dụng trong bài:**

1. `input` **borrowed read-only** trong một lời gọi. Callee không giữ pointer, không gọi `free(input)`, không ghi đè dữ liệu input.
2. Caller sở hữu `output` và chỉ cho callee ghi tối đa `output_capacity` bytes. Callee không `free(output)`.
3. `output_length` **bắt buộc non-null**; callee ghi số bytes **cần** khi trả `BUFFER_TOO_SMALL`, hoặc số bytes **đã ghi** khi trả `OK`.
4. Nếu cap thiếu, callee không được ghi một kết quả bị cắt nửa; status `BUFFER_TOO_SMALL` phải kèm required length.
5. Với `input_length == 0`, `input == NULL` hợp lệ. Với `output_capacity == 0`, `output == NULL` hợp lệ để *query* size.
6. Output là **binary data**; không thêm NUL terminator nếu contract không nói vậy.
7. Trong contract công khai, `input` và `output` phải là hai vùng **không chồng lấn**. Dù implementation hiện tại có buffer trung gian, caller không được dựa vào khả năng in-place khi API chưa cam kết.
8. Mọi C++ exceptions phải được bắt trong C façade. Lỗi trả bằng status; JNI shim có thể map status thành Java exception.
9. **Không thể xác minh một pointer có thật sự trỏ tới đủ số bytes chỉ qua con trỏ và length được khai báo.** Caller phải bảo đảm bounds và lifetime chính xác.

Điều kiện số 9 đặc biệt quan trọng: C vẫn có thể crash nếu caller nói `length=1000` nhưng allocation thực chỉ có 8 bytes. API buffer+length giúp hợp đồng rõ ràng và dễ validate logic hơn, không thay thế cơ chế memory safety cho native code.

## 3. Input length khác output capacity và written length

Với một biến đổi trả kết quả dài `M` bytes, caller có buffer output `N` bytes:

- Nếu `N >= M`, callee ghi đúng `M` bytes, trả `OK` và `*output_length=M`.
- Nếu `N < M`, callee trả `BUFFER_TOO_SMALL` và `*output_length=M`, không ghi một phần output.
- Nếu caller chưa biết `M`, có thể gọi `output=NULL` và `capacity=0` để hỏi.

```text
Java/C caller               C façade                  C++ core
     |                          |                         |
     | input,len,NULL,0,&need   |                         |
     |------------------------->| tính số bytes cần        |
     |<-------------------------| TOO_SMALL, need=M        |
     |                          |                         |
     | allocate M bytes         |                         |
     | input,len,out,M,&written |                         |
     |------------------------->| -> xử lý dữ liệu ------->|
     |                          | <- C++ vector result ----|
     |                          | copy ≤ capacity          |
     |<-------------------------| OK, written=M            |
     |                          |                         |
     | Caller dùng đúng M bytes và tự quản lý output buffer  |
```

Cách này gọi là **two-pass output pattern**. Với data có kích thước kết quả xác định trước (ví dụ XOR mỗi byte, output length bằng input length), có thể bỏ query trong bản tối ưu; ví dụ này vẫn dùng hai pass để thể hiện API phổ quát cho các thư viện nén/serialize/convert có output biến thiên.

**Lưu ý:** nếu output size phụ thuộc state thay đổi giữa lần query và fill (ví dụ database, time-based value, stream), `M` có thể thay đổi. Khi đó phải thiết kế snapshot/version token, hoặc retry khi nhận lại `BUFFER_TOO_SMALL` **có giới hạn**. Đừng retry vô hạn, và đừng tin rằng hai-pass tự tạo transaction.

## 4. Độ dài được tính bằng **byte**, không phải độ dài chuỗi

Xét binary input chứa NUL:

```c
#include <stdint.h>
#include <stddef.h>

const uint8_t data[] = {0x41, 0x00, 0xFF};
const size_t size = sizeof(data); /* 3 bytes */
```

Đây là **3 bytes**, dù `strlen((const char*)data)` sẽ dừng ở byte `0x00` đầu tiên. **Không dùng `strlen` cho arbitrary binary data**; luôn dựa vào `input_length` đã được kiểm chứng.

Với text, encoding phải được khai báo riêng:

```java
String text = "Cà phê";
int units = text.length(); // 6 UTF-16 code units.
byte[] utf8 = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
int lengthBytes = utf8.length;  // 8 UTF-8 bytes.
```

- Java `String.length()` đếm UTF-16 code units; số này không luôn bằng Unicode code points hoặc UTF-8 byte count.
- `std::string::size()` đếm bytes của stored string, không nói các bytes ấy đã được encode theo chuẩn nào.
- JNI `GetStringUTFChars` trả **modified UTF-8** chứ không nhất thiết chuẩn UTF-8 (khác ở U+0000 và supplementary code points). Nếu C++ library nhận UTF-8 chuẩn, dùng chuyển đổi được định nghĩa rõ, như `String.getBytes(StandardCharsets.UTF_8)`.
- Nếu C API đòi NUL-terminated string, quy định rõ việc thêm byte 0 và không chấp nhận embedded NUL khi không có cách biểu diễn; một binary buffer+length **không tự có terminator**.
- Với serialized objects, images, compressed payloads hay protobuf, tuyệt đối không chuyển bytes sang `String` chỉ để truyền dễ hơn.

## 5. Kiến trúc thực hành: 4 lớp được tách rõ

```text
NativeBufferDemo.java (Java 17+)
    byte[] input --> xorCopy(input) --> byte[] output
                          |
                          v
jni_bridge.cpp (JNI/C++ shim)
    GetByteArrayRegion (copy, không pin Java array)
    malloc temporary source/output + RAII free
                          |
                          v
bridge.h / bridge.cpp (C-compatible API)
    int xb_encode(uint8_t*,size_t,uint8_t*,size_t,size_t*)
    validation, buffer-too-small, C status, catch C++ exceptions
                          |
                          v
private_core.hpp / private_core.cpp (C++ nội bộ)
    internal::Codec sử dụng std::vector<uint8_t>
```

Để minh họa rõ byte length kể cả NUL, core sẽ **XOR mỗi byte với key `0x5A`**. Đây là phép biến đổi dữ liệu phục vụ học tập, **không phải encryption hay cơ chế bảo mật**.

```text
Input:         41 00 FF
XOR key:       5A 5A 5A
Output:        1B 5A A5
XOR lần hai:   41 00 FF
```

Công thức `x ^ key ^ key == x` giúp ta kiểm chứng dữ liệu không bị truncate, kể cả byte 0 và byte FF.

## 6. File `bridge.h`: C ABI không chứa C++ types

```c
#ifndef BUFFER_BRIDGE_H
#define BUFFER_BRIDGE_H

#include <stddef.h> /* size_t */
#include <stdint.h> /* uint8_t */

enum {
    XB_OK = 0,
    XB_BUFFER_TOO_SMALL = 1,
    XB_INVALID_ARGUMENT = 2,
    XB_NO_MEMORY = 3,
    XB_INTERNAL_ERROR = 4
};

#ifdef __cplusplus
extern "C" {
#endif

/*
 * input/input_length: borrowed, read-only bytes.
 * output/output_capacity: writable buffer do caller cấp.
 * output_length: required length khi TOO_SMALL, actual khi OK.
 * Query: output=NULL, output_capacity=0.
 * Null input được phép nếu input_length=0.
 * Không ghi một phần output khi thiếu capacity.
 * Không retain/free các con trỏ input và output.
 * Hai vùng input/output theo contract không được overlap.
 * Không để C++ exception thoát khỏi function này.
 */
int xb_encode(const uint8_t *input, size_t input_length,
              uint8_t *output, size_t output_capacity,
              size_t *output_length);

#ifdef __cplusplus
}
#endif

#endif
```

**Vì sao các types này phù hợp?** `uint8_t` là byte 8 bit trên Linux x86-64; `size_t` biểu diễn C buffer size theo ABI của tiến trình; `int` biểu diễn status. `enum` khai báo C-compatible integral constants (không phải C++ `enum class`). `extern "C"` được bọc `#ifdef __cplusplus` để C compiler cũng đọc được header.

`size_t` **không được mặc định bằng Java `int`**; trên Linux x64 nó thường rộng 64 bit. Khi JNI chuyển `jsize` sang `size_t` phải kiểm tra giá trị signed và khi chuyển required length về `jsize` phải kiểm tra trước cast.

## 7. Files `private_core.hpp` và `private_core.cpp` — implementation thuần C++

**File `private_core.hpp`:**

```cpp
#ifndef PRIVATE_CORE_HPP
#define PRIVATE_CORE_HPP

#include <cstddef>
#include <cstdint>
#include <vector>

namespace internal {
class Codec final {
public:
    std::vector<std::uint8_t> encode(
            const std::uint8_t *data,
            std::size_t length) const;
};
}

#endif
```

**File `private_core.cpp`:**

```cpp
#include "private_core.hpp"

namespace internal {

std::vector<std::uint8_t> Codec::encode(
        const std::uint8_t *data,
        std::size_t length) const {

    std::vector<std::uint8_t> result(length);
    for (std::size_t i = 0; i < length; ++i) {
        result[i] = static_cast<std::uint8_t>(
                data[i] ^ static_cast<std::uint8_t>(0x5A));
    }
    return result;
}

}
```

C++ core **được phép** dùng vector, constructors/destructors, exceptions và standard library. Nó không export những types ấy ra Java. Trong thư viện thực tế, `Codec::encode` có thể làm serialization, image conversion, compression hoặc tính toán phức tạp; cách trao bytes qua public C header không cần đổi chỉ vì internal container được refactor.

C++ vector có thể ném `std::bad_alloc` nếu hết memory. Bridge phải **catch** và trả status thay vì đưa C++ exception vượt JNI/C ABI.

## 8. File `bridge.cpp` — đo capacity, ghi chính xác, chặn C++ exceptions

```cpp
#include "bridge.h"
#include "private_core.hpp"

#include <cstring>    // std::memcpy
#include <new>        // std::bad_alloc

extern "C" int xb_encode(
        const uint8_t *input,
        size_t input_length,
        uint8_t *output,
        size_t output_capacity,
        size_t *output_length) {

    if (output_length == nullptr) {
        return XB_INVALID_ARGUMENT;
    }
    *output_length = 0;

    if ((input_length > 0 && input == nullptr) ||
        (output_capacity > 0 && output == nullptr)) {
        return XB_INVALID_ARGUMENT;
    }

    // Thuật toán XOR bảo toàn length, required = input_length.
    *output_length = input_length;
    if (output_capacity < input_length) {
        return XB_BUFFER_TOO_SMALL; // Không ghi một phần output.
    }
    if (input_length == 0) {
        return XB_OK; // Không dereference input/output.
    }

    try {
        internal::Codec codec;
        std::vector<std::uint8_t> result =
                codec.encode(input, input_length);

        // Kiểm tra lại nếu core thay đổi length sau này.
        if (result.size() > output_capacity) {
            *output_length = result.size();
            return XB_BUFFER_TOO_SMALL;
        }

        std::memcpy(output, result.data(), result.size());
        *output_length = result.size();
        return XB_OK;
    } catch (const std::bad_alloc &) {
        *output_length = 0;
        return XB_NO_MEMORY;
    } catch (...) {
        *output_length = 0;
        return XB_INTERNAL_ERROR;
    }
}
```

Ở đây **`std::vector` là biến local** và destructor của nó giải phóng storage nội bộ khi function return. C façade copy bytes sang **output do caller sở hữu trước khi local vector hết lifetime**. Nó không trả `result.data()` hoặc memory mang layout của `std::vector`.

**Bốn bất biến cần code review:**

1. Không dereference input khi length=0.
2. Không gọi core/copy nếu capacity thiếu; `*output_length` chứa required bytes để caller cấp lại.
3. Khi thành công, ghi không quá capacity và ghi số bytes thực vào `*output_length`.
4. Không để `std::bad_alloc` hoặc bất kỳ C++ exception nào thoát khỏi exported C function.

Ở ví dụ này query required có thể tính bằng `input_length`, vì XOR là **length preserving**. Nếu thay core bằng nén hoặc serialization, **phải thay thuật toán query** (ví dụ `measure` hoặc encode tạm) để required thực sự đúng; kiểm tra sau encode không thay thế được một query contract chính xác.

**Giới hạn:** nếu pointer input trỏ vào memory không hợp lệ, `catch(...)` không bảo vệ khỏi SIGSEGV/undefined behavior. Caller vẫn phải cung cấp địa chỉ, size và lifetime đúng.

## 9. File `jni_bridge.cpp` — JNI copy, RAII cleanup, Java exception

JNI shim sẽ nhận `byte[]` của Java, copy qua native input buffer, gọi C façade theo hai-pass, rồi copy output vào **một `byte[]` mới**.

**File `jni_bridge.cpp`:**

```cpp
#include "NativeBufferDemo.h" // javac -h tạo JNI prototype.
#include "bridge.h"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <memory>

static constexpr jsize MAX_INPUT = 1024 * 1024;

static void throw_if_no_pending(
        JNIEnv *env, const char *class_name,
        const char *message) {
    if (env->ExceptionCheck()) {
        return;
    }

    jclass type = env->FindClass(class_name);
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

static void throw_status(JNIEnv *env, int status) {
    if (status == XB_NO_MEMORY) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "native allocation failed");
    } else if (status == XB_INVALID_ARGUMENT) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "invalid native buffer argument");
    } else {
        throw_if_no_pending(
                env, "java/lang/IllegalStateException",
                "native buffer conversion failed");
    }
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_NativeBufferDemo_xorCopy(
        JNIEnv *env, jclass owner, jbyteArray input) {

    (void)owner;

    if (input == nullptr) {
        throw_if_no_pending(
                env, "java/lang/NullPointerException", "input");
        return nullptr;
    }

    const jsize java_length = env->GetArrayLength(input);
    if (env->ExceptionCheck()) {
        return nullptr;
    }
    if (java_length > MAX_INPUT) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "demo input exceeds 1 MiB");
        return nullptr;
    }

    const std::size_t n =
            static_cast<std::size_t>(java_length);

    using Buffer = std::unique_ptr<
            std::uint8_t, decltype(&std::free)>;

    Buffer source(static_cast<std::uint8_t *>(
            std::malloc(n == 0 ? 1 : n)), &std::free);

    if (!source) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "malloc input failed");
        return nullptr;
    }

    if (java_length > 0) {
        env->GetByteArrayRegion(
                input, 0, java_length,
                reinterpret_cast<jbyte *>(source.get()));
        if (env->ExceptionCheck()) {
            return nullptr; // unique_ptr free source.
        }
    }

    std::size_t required = 0;
    const int query = xb_encode(
            source.get(), n, nullptr, 0, &required);

    if ((query != XB_OK && query != XB_BUFFER_TOO_SMALL) ||
        required != n) {
        throw_status(env, query);
        return nullptr;
    }

    if (required > static_cast<std::size_t>(
            std::numeric_limits<jsize>::max())) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "native output exceeds Java array size");
        return nullptr;
    }

    Buffer output(static_cast<std::uint8_t *>(
            std::malloc(required == 0 ? 1 : required)),
            &std::free);

    if (!output) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "malloc output failed");
        return nullptr;
    }

    std::size_t written = 0;
    const int status = xb_encode(
            source.get(), n,
            output.get(), required, &written);

    if (status != XB_OK || written != required) {
        throw_status(env, status);
        return nullptr;
    }

    jbyteArray result = env->NewByteArray(
            static_cast<jsize>(written));
    if (result == nullptr) {
        return nullptr; // OutOfMemoryError có thể pending.
    }

    if (written > 0) {
        env->SetByteArrayRegion(
                result, 0, static_cast<jsize>(written),
                reinterpret_cast<const jbyte *>(output.get()));
        if (env->ExceptionCheck()) {
            return nullptr;
        }
    }

    return result; // source/output được free qua RAII.
}
```

**Vì sao code dọn tài nguyên đúng?**

- `GetByteArrayRegion` **copy** từ Java array vào buffer caller đã cấp; nó không phải JNI lease như `GetByteArrayElements`, nên **không có `ReleaseByteArrayRegion`**.
- `std::unique_ptr` với deleter `std::free` quản lý chính xác các allocations do `std::malloc` tạo. Khi return sớm hoặc Java exception pending, destructor vẫn thực hiện cleanup.
- `NewByteArray` tạo Java-owned output; JVM quản lý đối tượng ấy. JNI không gọi `free` trên Java array.
- JNI shim không bao giờ truy cập `std::vector` trực tiếp; nó gọi C ABI `xb_encode` và chỉ biết buffer/length/status.
- Nếu một JNI call đặt pending exception, `throw_if_no_pending` không che lỗi gốc bằng exception mới. `DeleteLocalRef` được phép gọi trong đường cleanup khi exception pending.
- `required == n` là bất biến riêng của **XOR**; nếu core đổi thành thuật toán có output length khác, cần cập nhật JNI client để dùng đúng required byte count (và chính sách retry).

Ví dụ đặt giới hạn input 1 MiB để tránh cấp phát khổng lồ trong bài học. Production nên có giới hạn memory, số calls đồng thời, error policy và cancellation phù hợp với workload.

## 10. File `NativeBufferDemo.java` — caller chỉ thấy `byte[]`

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public final class NativeBufferDemo {
    static {
        System.loadLibrary("bufferbridge");
    }

    private static native byte[] xorCopy(byte[] input);

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ")
                .withUpperCase()
                .formatHex(bytes);
    }

    public static void main(String[] args) {
        byte[] input = {
                (byte) 0x41,
                (byte) 0x00,
                (byte) 0xFF
        };
        byte[] original = input.clone();

        byte[] encoded = xorCopy(input);
        byte[] decoded = xorCopy(encoded);

        System.out.println("input=" + hex(input));
        System.out.println("encoded=" + hex(encoded));
        System.out.println("decoded=" + hex(decoded));
        System.out.println("unchanged=" +
                Arrays.equals(input, original));
        System.out.println("emptyLength=" +
                xorCopy(new byte[0]).length);

        String text = "Cà phê";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf16Units=" + text.length());
        System.out.println("utf8Bytes=" + utf8.length);
    }
}
```

`HexFormat` có từ Java 17, do đó code này không cần thư viện bổ sung. Java chỉ biết **Java arrays**, không biết C++ types, pointers hay allocator. Demo XOR là một thao tác binary, không phải cryptography.

## 11. Build và chạy trên Linux với JDK 17+ và C++17

Tạo sáu files đã liệt kê trong **cùng thư mục**:

```text
native-buffer-lab/
  NativeBufferDemo.java
  bridge.h
  bridge.cpp
  private_core.hpp
  private_core.cpp
  jni_bridge.cpp
  NativeBufferDemo.h   <-- sinh bằng javac -h
  libbufferbridge.so   <-- sinh bằng c++
```

Cần `JAVA_HOME` trỏ đến JDK có `include/jni.h` và `include/linux/jni_md.h`, compiler C++ tương thích với JVM.

### Sinh JNI header

```bash
javac -encoding UTF-8 -h . NativeBufferDemo.java
```

Vì Java class `NativeBufferDemo` không đặt trong package và method là `static native byte[] xorCopy(byte[])`, generated header khai báo JNI entry tên `Java_NativeBufferDemo_xorCopy`. Nếu chuyển class vào package, phải sinh lại header và sửa implementation theo symbol name mới, không đoán.

### Compile shared library

```bash
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
  -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libbufferbridge.so \
  private_core.cpp bridge.cpp jni_bridge.cpp
```

Dù exported façade dùng **C ABI**, implementation có `std::vector` và C++ RAII, nên dùng **C++ compiler/linker**. `extern "C"` trên `xb_encode` bảo đảm tên và language linkage ở phía C, có thể dùng lại từ C callers/FFM. File `jni_bridge.cpp` export thêm JNI method `Java_NativeBufferDemo_xorCopy`.

### Chạy ứng dụng

```bash
java -Djava.library.path=. NativeBufferDemo
```

`-Djava.library.path=.` là JVM option phải đặt **trước** tên main class. `System.loadLibrary("bufferbridge")` tìm `libbufferbridge.so` trên Linux. Nếu shared library phụ thuộc các native libraries khác, OS loader còn phải tìm các dependencies tương ứng; Java classpath không làm thay việc đó.

### Stdout kỳ vọng

```text
input=41 00 FF
encoded=1B 5A A5
decoded=41 00 FF
unchanged=true
emptyLength=0
utf16Units=6
utf8Bytes=8
```

Kiểm tra:
- `0x41 ^ 0x5A = 0x1B`, `0x00 ^ 0x5A = 0x5A`, `0xFF ^ 0x5A = 0xA5`.
- XOR cùng key hai lần trả bytes gốc.
- `unchanged=true` vì input Java được copy, không ghi đè.
- `emptyLength=0` kiểm tra input rỗng và không dereference pointer khi length 0.
- `"Cà phê"` có 6 UTF-16 code units và 8 UTF-8 bytes.

Đây là **ví dụ đầy đủ được thiết kế để biên dịch trên Linux/JDK17+/C++17**, chưa phải kết quả của một lượt build thực tế trong mọi môi trường. Trên macOS/Windows phải đổi shared-library filename, compiler flags và JNI platform include path.

## 12. Ownership: ai cấp phát, ai giải phóng?

| Vùng | Owner | Khi nào giải phóng? | Không được làm |
| --- | --- | --- | --- |
| `byte[] input` | JVM/Java | Theo Java lifecycle | C `free` Java array |
| `source` cấp bằng `malloc` tại JNI shim | C++ `unique_ptr` trong JNI call | Destructor gọi `free` khi return | Giữ pointer sau JNI call |
| `std::vector` nội bộ của `Codec` | C++ local object | Destructor C++ khi hết scope | Trả `result.data()` ra Java |
| `output` cấp bằng `malloc` tại JNI shim | C++ `unique_ptr` | Destructor gọi `free` | C façade tự free buffer caller |
| `byte[] result` tạo bằng JNI `NewByteArray` | Java/JVM | Theo Java lifecycle | C `free` result |
| `input`/`output` của `xb_encode` | Caller của C façade | Theo owner caller | Callee retain/free sau return |
| `output_length` | Caller cấp địa chỉ của `size_t` | Theo lifetime caller | Giữ lại pointer sau return |

JNI `GetByteArrayRegion` và `SetByteArrayRegion` là **copy operations**, không tạo JNI pinned array lease cần `ReleaseByteArrayElements`. Ngược lại, nếu chọn `GetByteArrayElements` để có pointer truy cập mảng, **phải** `ReleaseByteArrayElements` dù `isCopy` báo true hay false. Không dùng `free` cho pointer JVM cấp.

Khi C façade cần tự cấp output rồi trả ownership sang Java, phải có matching `xb_free` / `destroy` API do cùng thư viện công bố, Java wrapper `AutoCloseable` hoặc owner protocol phù hợp. Đừng để Java gọi `free` tùy tiện trên memory từ C++ `new[]` hoặc custom allocator.

## 13. Những thiết kế thay thế khi output phức tạp

### A. Caller buffer + length (đang dùng)

```c
int transform(const uint8_t *in, size_t in_len,
              uint8_t *out, size_t cap, size_t *written);
```

**Ưu:** không export C++ types, caller quyết định buffer allocation/pool/reuse. **Nhược:** có thể cần query hai pass, caller phải xử lý cap không đủ.

### B. Callee allocation + explicit free

```c
/* Minh họa API khác; chưa có implementation ở bài này. */
int transform_alloc(const uint8_t *in, size_t len,
                    uint8_t **out, size_t *out_len);
void transform_free(uint8_t *out);
```

**Ưu:** callee có thể cấp đúng size một lần. **Nhược:** caller phải giữ owner và gọi `transform_free` đúng một lần; nếu thiếu sẽ leak, nếu gọi sớm/double sẽ UAF/double-free. API phải công bố error cases (trên lỗi `*out==NULL` hay ownership đã transfer?).

### C. Streaming/chunk callback

```c
typedef int (*on_chunk_fn)(
        void *context, const uint8_t *bytes, size_t length);

int transform_stream(const uint8_t *in, size_t len,
                     on_chunk_fn on_chunk, void *context);
```

**Ưu:** không phải giữ output khổng lồ trong RAM; có thể phát từng chunk. **Nhược:** callback ABI, error propagation, concurrency, reentrancy và lifetime phức tạp. Pointer chunk thường **borrowed chỉ trong callback**, nên nếu cần dùng sau phải copy.

### D. Opaque handle cho C++ object có state

```c
typedef struct xb_session xb_session;

int xb_session_create(xb_session **out);
int xb_session_process(xb_session *session,
                       const uint8_t *input, size_t length,
                       uint8_t *output, size_t capacity,
                       size_t *written);
void xb_session_destroy(xb_session *session);
```

**Ưu:** có thể giữ C++ class state private sau một C handle; vẫn truyền dữ liệu qua buffer+length. **Nhược:** phải có create/destroy, ownership, thread-safety, synchronization và lifecycle protocol. Không dereference incomplete C type từ Java.

## 14. Dùng FFM Java 22+ với cùng C ABI

FFM `java.lang.foreign` được finalize từ **JDK 22** (JEP 454). Khi có `bridge.h`, Java 22+ có thể gọi `xb_encode` trực tiếp bằng `Linker.downcallHandle` mà không cần JNI shim. Nhưng **mô hình API công khai không đổi**: Java vẫn thấy các con trỏ, size và status C; không hề thấy `std::vector`.

Trên Linux x86-64 (C `size_t` 64 bit), một descriptor minh họa:

```java
// Đoạn minh họa trong Java 22+, không phải class đầy đủ.
import java.lang.foreign.FunctionDescriptor;
import static java.lang.foreign.ValueLayout.*;

FunctionDescriptor xbDesc = FunctionDescriptor.of(
        JAVA_INT,   // C int return status
        ADDRESS,    // const uint8_t* input
        JAVA_LONG,  // size_t input_length (Linux x86-64)
        ADDRESS,    // uint8_t* output
        JAVA_LONG,  // size_t output_capacity
        ADDRESS     // size_t* output_length
);
```

Java carrier type tương ứng thường là `(MemorySegment,long,MemorySegment,long,MemorySegment)int`. Để chạy thật, cần `SymbolLookup` lấy symbol `xb_encode`, `Linker.downcallHandle`, arena cấp native buffers (kể cả vùng chứa `size_t output_length`), copy input, `invokeExact`, đọc status/required/written, rồi copy output hợp lệ về Java. Native access restricted operations cần flag như `--enable-native-access=ALL-UNNAMED` trên classpath khi phù hợp.

**Không mặc định `size_t == Java long` trên mọi kiến trúc.** Với ABI 32 bit, `size_t` có thể là 32 bit; tra linker canonical layouts và target ABI. `MemorySegment` có scope/bounds, nhưng nếu C giữ raw pointer sau khi arena đóng thì vẫn có thể gây crash. Nếu chỉ gọi C đồng bộ và không retain pointers, `Arena.ofConfined()` có thể quản lý native input/output buffers và đóng sau downcall.

Java 17 không biên dịch đoạn FFM finalized trên: bài thực hành **runnable Java17+** ở trên dùng JNI thay thế.

## 15. Text, binary và serialization: có length chưa đủ nếu thiếu format contract

Một vùng bytes có thể chứa text UTF-8, compressed data, C struct serialized hoặc arbitrary binary. Contract cần mô tả **format**, không chỉ kích thước:

- **Text:** encoding (UTF-8, UTF-16LE, Latin-1...), invalid sequence policy, embedded NUL, có/không trailing terminator.
- **Integer data:** byte order little/big-endian, signedness, width; không giả định C `long` giống nhau trên Windows/Linux.
- **Records/structs:** field order, type, alignment, packing, version, length của variable-sized fields.
- **Binary protocol:** magic/version header, payload length, checksum nếu cần, max size.
- **Strings from C++:** `std::string` chỉ là một container bytes; không ngầm hứa UTF-8 hợp lệ.

Đừng copy raw bytes của `std::string` object (metadata của object) thành wire format; hãy copy **`s.data()` với `s.size()` bytes khi object còn sống**. Cũng đừng copy `std::vector` object; chỉ copy `v.data()` với `v.size() * sizeof(element)` khi phần tử có định dạng binary được định nghĩa, cân nhắc padding/endian nếu không phải byte.

Nếu một C++ API xử lý protobuf/JSON hoặc cấu trúc versioned, nên expose **serialized bytes + length**, để Java dùng parser/codec thích hợp. Đây là cách tránh phụ thuộc lâu dài vào C++ class layout.

## 16. Bảo vệ trước size overflow và dữ liệu không tin cậy

Các lỗi ở native side nghiêm trọng hơn một Java exception thường: vượt vùng C memory có thể corrupt heap hoặc khiến JVM crash.

**Kiểm tra trước khi cast Java length:**

```cpp
// Minh họa trong JNI với required kiểu size_t.
if (required > static_cast<std::size_t>(
        std::numeric_limits<jsize>::max())) {
    // Java array không thể mang length này.
    return nullptr; // Phải báo Java error phù hợp.
}
```

Với tính toán kích thước:

```c
/* Minh họa: header + payload, dùng size_t. */
if (payload_bytes > SIZE_MAX - header_bytes) {
    return XB_INVALID_ARGUMENT;
}
size_t required = header_bytes + payload_bytes;
```

Với số phần tử: kiểm tra `count <= SIZE_MAX / element_size` trước `count * element_size`. `size_t` sang `jsize`/Java `int` nên validate trước cast để tránh truncation. Đừng tin một untrusted input claim rằng output nén/giải nén cần vài GiB mà cấp ngay không giới hạn; đặt **memory budget** và kiểm tra kích thước tối đa. Với signed/unsigned mixing, tránh so sánh số âm bị cast thành số dương khổng lồ.

**Exceptions:** `catch(...)` xử lý C++ exceptions, không biến SIGSEGV/undefined behavior do invalid pointer thành Java exception an toàn. Lỗi gốc vẫn phải được chặn bằng pointer bounds/lifetime, format validation và native memory sanitizer trong test.

## 17. Ghi lỗi vào status thay vì ném C++ exception qua boundary

Một exported C API nên có error policy ổn định:

| Status | Khi nào | `output_length` theo contract demo |
| --- | --- | --- |
| `XB_OK` | Ghi thành công / output rỗng hợp lệ | Số bytes đã ghi |
| `XB_BUFFER_TOO_SMALL` | Caller buffer thiếu capacity | Số bytes cần để thử lại |
| `XB_INVALID_ARGUMENT` | Pointer/length/null combination không hợp lệ | 0 nếu `output_length` non-null |
| `XB_NO_MEMORY` | C++ `std::bad_alloc` | 0 |
| `XB_INTERNAL_ERROR` | C++ exception khác | 0 |

Lợi ích: Java client có thể map status thành Java `IllegalArgumentException`, `OutOfMemoryError` hoặc `IllegalStateException` theo policy. Một empty result hợp lệ không bị nhầm với failure chỉ vì length=0.

**Không bao giờ** trả pointer `std::exception::what()` của temporary exception ra Java rồi dùng sau khi catch kết thúc. Nếu cần diagnostic text, cung cấp một **buffer+length error-message API** khác, hoặc log/đưa mã lỗi có table giải thích. Tách error channel khỏi data channel giúp test chính xác hơn.

## 18. Concurrent calls và async ownership

Nếu C++ core có shared mutable state, phải đồng bộ; việc API chỉ có buffer+length **không biến thư viện thành thread-safe**. Nếu caller đồng thời ghi vào input khi callee đang đọc, đó là data race ở native side hoặc data consistency bug. Contract input read-only chỉ giới hạn hành vi **callee**, không bảo vệ khỏi caller sửa buffer giữa chừng.

Với lời gọi **đồng bộ**, đơn giản nhất:

```text
Caller sở hữu input/output
    |
    +-- gọi C API
           |
           +-- callee mượn pointers
           +-- xử lý/copy kết quả
           +-- trả status
    |
Caller có thể tái sử dụng hoặc giải phóng buffers sau return
```

Nếu API **bất đồng bộ** giữ pointer sau return, toàn bộ contract phải đổi:

- Ai giữ allocation sống đến khi callback cuối hoàn tất?
- Có `retain/release`, opaque handle, task completion hoặc cancel/await API không?
- C có cần copy input trước khi return?
- Khi nào caller được free/reuse output?
- Con trỏ có thể được dùng từ thread khác không?
- C++ library/unload/native callback pointer còn sống đến lúc kết thúc không?

Không được truyền một pointer JNI `GetByteArrayElements` rồi trả về mà không Release, hoặc giữ pointer vào FFM arena đã đóng cho native worker. Với async thường phải **copy sang native-owned buffer có explicit owner** hoặc dùng shared arena và coordinator chờ in-flight work kết thúc.

## 19. Hiệu năng: có nên tránh mọi phép copy?

Ví dụ demo thực hiện nhiều lần copy:

```text
Java byte[] 
   -> GetByteArrayRegion -> native input
   -> std::vector (XOR)
   -> memcpy -> native output
   -> SetByteArrayRegion -> Java byte[]
```

Đây không phải zero-copy. Nhưng lifetime, ownership và error handling đơn giản, có thể rất tốt với payload nhỏ/trung bình.

Các hướng tối ưu **không cần lộ kiểu nội bộ**:

1. Reuse các native output buffers với owner/pool rõ ràng để giảm malloc/free.
2. Khi output size biết trước (như XOR), bỏ query hai-pass và cấp một lần theo input length.
3. Cho C++ core ghi trực tiếp vào caller-owned output buffer; public C ABI vẫn như cũ.
4. Với C++20, dùng `std::span<std::byte>` **nội bộ**, không xuất `span` qua C ABI.
5. Dùng FFM native memory segments/DirectByteBuffer với explicit lifetime nếu throughput thực sự cần zero-copy.
6. Dùng streaming/chunks khi payload quá lớn.
7. Batch nhiều calls nhỏ để giảm overhead JNI/FFM crossing.

Không tối ưu theo trực giác. Đo throughput, P95/P99 latency, allocation rate, RSS và tổng thời gian C++/Java conversion trước khi trả giá bằng phức tạp ownership. Một lỗi UAF/double-free thường đắt hơn vài lượt copy.

## 20. Ma trận kiểm thử âm tính

### C façade

| Input | Trạng thái mong đợi |
| --- | --- |
| `input=NULL`, `input_length=0`, query output | `XB_OK`, required=0 |
| `input=NULL`, `input_length>0` | `XB_INVALID_ARGUMENT` |
| `output_length=NULL` | `XB_INVALID_ARGUMENT` |
| `output=NULL`, cap=0, length=3 | `XB_BUFFER_TOO_SMALL`, required=3 |
| Output cap=2, required=3 | `XB_BUFFER_TOO_SMALL`, không partial-write |
| Output cap=3, required=3 | `XB_OK`, written=3, bytes đúng |
| Bytes chứa `00`, `FF` | Không truncate, output length đúng |
| C++ core ném `std::bad_alloc` | `XB_NO_MEMORY`, không exception vượt C ABI |
| Core ném exception khác | `XB_INTERNAL_ERROR` |
| Pointer invalid hoặc size nói dối | **Caller contract violation**; không thử trong JVM production |

### Java/JNI

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| `xorCopy(new byte[0])` | Java output length 0 |
| `xorCopy(new byte[]{0, -1})` | Hai bytes được xử lý, không NUL truncation |
| `xorCopy(null)` | `NullPointerException` |
| Input dài quá 1 MiB | `IllegalArgumentException` |
| JNI tạo array thất bại do thiếu memory | Giữ pending Java exception, RAII dọn buffers |
| Chạy nhiều lần | Không giữ native input/output pointers sau return |
| Nhiều Java threads gọi đồng thời | Core demo không giữ shared mutable state |
| Test text tiếng Việt | Byte length UTF-8 lấy từ `getBytes(UTF_8)`, không `String.length()` |

Khi có điều kiện, chạy JVM với `-Xcheck:jni` và kiểm thử native bằng AddressSanitizer/UndefinedBehaviorSanitizer. Một lần stdout đúng không chứng minh mọi lỗi cấp phát, race hay overflow đã được kiểm thử; cần thêm fault injection và load testing phù hợp.

## 21. Checklist thiết kế wrapper C++ cho Java

- [ ] Public C header không chứa `std::string`, `std::vector`, template, C++ reference hoặc C++ exception.
- [ ] `extern "C"` được khai báo đúng cho function symbols, header C/C++ cùng đọc được.
- [ ] Input có pointer + length **theo byte**; output có pointer + capacity + required/written count.
- [ ] Không dùng NUL terminator cho binary data; text API công bố encoding/NUL policy riêng.
- [ ] Caller/callee ownership rõ; callee không retain/free borrowed buffers.
- [ ] Query size có semantics chính xác; cap thiếu không ghi partial output.
- [ ] Nếu kết quả thay đổi giữa query và fill, có retry/snapshot/version protocol.
- [ ] Kiểm tra null/zero-length và size/offset overflow trước khi dereference/cast.
- [ ] C++ exceptions được catch và chuyển thành C status, không vượt qua JNI/FFM.
- [ ] Native temporary buffers có RAII/cleanup trên mọi nhánh lỗi.
- [ ] Nếu callee tự cấp output, có matching destroy API và đúng allocator/module.
- [ ] Không trả pointer đến C++ local vector/string đã hết lifetime.
- [ ] Dữ liệu struct/object được serialize/version hóa hoặc dùng C-compatible layout có ABI review.
- [ ] FFM/JNI conversion thống nhất C types, byte width, alignment, target OS/ABI.
- [ ] Có memory/CPU budgets cho untrusted lengths và payloads lớn.
- [ ] Async/native callback không giữ pointer quá lifetime và có cơ chế chờ hoàn tất.
- [ ] Đã benchmark trước khi tối ưu zero-copy.
- [ ] Có unit/native tests cho empty, NUL, FF, short capacity, null, OOM, unicode và concurrency.
- [ ] Generated JNI headers và native library binary được build đúng OS/architecture.
- [ ] C header là **contract được version hóa**; implementation C++ có thể thay đổi mà không lộ internals.

## 22. Câu hỏi tự kiểm tra

**1. Vì sao `extern "C" std::vector<uint8_t> encode(...)` không tạo API Java an toàn?**

Vì `extern "C"` chỉ điều khiển language linkage, không tạo layout/allocator/destructor contract tương thích C cho `std::vector`. Java không thể giải mã object vector và không biết hủy nó. Dùng C façade với buffer+length.

**2. Có `output_length` rồi, tại sao vẫn cần `output_capacity`?**

`output_capacity` là giới hạn ghi **caller đã cấp**; `output_length` là số bytes callee **cần hoặc đã ghi**. Không so sánh chúng trước copy sẽ có nguy cơ buffer overflow.

**3. Vì sao cần hai lượt với output chưa biết kích thước?**

Lượt query trả required size để caller cấp đủ, lượt fill ghi bytes vào buffer caller. Nhưng nếu input/state thay đổi giữa hai lượt, phải snapshot/retry có giới hạn hoặc thiết kế streaming.

**4. `input={0x41,0x00,0xFF}` có dài 1 byte vì NUL xuất hiện ở vị trí 2 không?**

Không. Binary input dài **3 bytes**. Chỉ C string operations như `strlen` dừng ở NUL; API binary dùng explicit length.

**5. JNI `GetByteArrayRegion` có cần `ReleaseByteArrayRegion` không?**

Không. Nó **copy** vào buffer do caller cấp, không tạo JNI lease. `GetByteArrayElements` thì cần `ReleaseByteArrayElements` đúng cặp.

**6. Nếu C++ core trả `result.data()` của `std::vector` local thì có dùng sau C function return được không?**

Không. Khi vector bị hủy, pointer invalid. Hãy copy vào caller-owned buffer trước khi local vector hết scope hoặc tạo explicit callee-allocated output + matching free API.

**7. Vì sao `String.length()` không phải độ dài buffer UTF-8?**

Java đếm UTF-16 code units, còn UTF-8 có số bytes khác. `"Cà phê"` có 6 UTF-16 units nhưng 8 UTF-8 bytes.

**8. C++ `std::bad_alloc` có tự trở thành Java `OutOfMemoryError` không?**

Không được dựa vào điều đó. Bắt nó tại C façade, trả status `XB_NO_MEMORY`, JNI shim chủ động báo Java error nếu chưa có pending exception.

**9. Nếu `size_t` 64 bit nhưng `jsize` 32 bit, nên làm gì?**

Kiểm tra required/output size không vượt `jsize::max` **trước** khi cast; overflow và signed/unsigned conversion phải được validate. FFM mapping cũng phải theo target ABI.

**10. Dùng C façade buffer+length có chắc không còn crash do pointer sai không?**

Không. Nó giúp diễn đạt contract rõ hơn, nhưng C không xác minh được pointer thật có đủ byte và còn sống. Caller phải bảo đảm allocation, bounds, lifetime và thread-safety.

**11. Nếu C++ class có state sống lâu, có phải expose class layout không?**

Không. Dùng **opaque C handle** kèm create/process/destroy, và giữ bytes vào/ra qua buffer+length. Cần owner/thread lifecycle rõ.

**12. Java 17 có thể dùng phần FFM `java.lang.foreign` finalized trực tiếp không?**

Không; mã runnable Java17+ ở bài là JNI. FFM finalized từ JDK 22; Java 17 có incubator khác API.

## 23. Nguồn đối chiếu

- Oracle JNI Specification — [Get/Set Primitive Array Region và quản lý byte buffers](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines).
- Oracle JNI Specification — [Array operations, Get/Release array elements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#array-operations).
- Oracle Java 17 — [`HexFormat`, `ofDelimiter` và `withUpperCase`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).
- cppreference — [C++ language linkage và `extern "C"`](https://en.cppreference.com/w/cpp/language/language_linkage).
- cppreference — [`std::vector` và quản lý contiguous storage](https://en.cppreference.com/w/cpp/container/vector).
- Oracle Java 22 — [FFM Linker và C ABI downcalls](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- Oracle Java 22 — [FFM Arena và memory lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- OpenJDK — [JEP 454: FFM API finalized ở JDK 22](https://openjdk.org/jeps/454).

**Kết luận:** khi bọc thư viện C++ cho Java, giữ các `std::vector`/`std::string`/C++ classes **hoàn toàn nội bộ**. Công bố một **C ABI đơn giản với input pointer+byte length, output pointer+capacity, actual/required length và status**; kiểm tra null/size/overflow, bắt C++ exceptions trong bridge, và bảo đảm ownership/lifetime của mọi buffer. Cách này dùng được qua JNI lẫn FFM và tránh gắn Java API vào layout biến động của C++ implementation.