# Giới hạn của JNI hoặc FFM khi thư viện chỉ xuất API C++ phức tạp

## 1. Bài toán: Java không tự hiểu C++ object model

Giả sử một SDK chỉ đưa ra:

~~~cpp
// C++ API minh họa, KHÔNG phải giao diện C.
namespace vision {
    template<class Pixel> class Image;

    class Analyzer {
    public:
        explicit Analyzer(std::string modelPath);
        virtual ~Analyzer();
        std::vector<float> infer(const Image<float>& input);
        std::vector<float> infer(const Image<unsigned char>& input);
        void setOptions(const std::map<std::string, std::string>& options);
    };
}
~~~

Việc có một `.so`/`.dll` và C++ header chưa đủ để Java gọi các methods này. Class layout, constructor, destructor, overloaded function names, template instantiations, virtual dispatch, C++ exceptions và STL containers có các hợp đồng ABI không được Java JNI hoặc FFM tự động tái tạo.

Hai kết luận cần phân biệt:

- **JNI có thể gọi C++**: một JNI native method **được viết bằng C++**, biên dịch với compiler/linker tương thích SDK, có thể gọi class methods, instantiate templates và thao tác `std::string`/`std::vector`. Nhưng cần code native chuyển dữ liệu, quản lý object và exception. JNI không phải trình biên dịch hay bộ phản chiếu C++.
- **FFM gọi native functions theo ABI mà `Linker` hỗ trợ**, điển hình là C ABI trên platform. FFM không tự thực hiện C++ overload resolution, constructor invocation, vtable dispatch hoặc ánh xạ STL object layout. Để kết nối một C++ library phức tạp, cách thông dụng là tạo **C-compatible wrapper** viết bằng C++ rồi để FFM gọi các functions `extern "C"`.

Một **function descriptor** hợp lệ trong Java chưa chứng minh function C++ thực có signature/ABI tương thích. Dùng sai layout, function pointer hoặc object lifetime có thể làm crash JVM chứ không chỉ ném exception.

**Mục tiêu bài:** nhận diện ranh giới của JNI/FFM, biết điều `extern "C"` làm được và không làm được, thiết kế một opaque-handle C wrapper, thực hành C++17 → C ABI → Java 22+ FFM, xem ví dụ JNI Java 17+, và nắm những giới hạn khi chỉ có binary C++ mà không có supported SDK.

## 2. C ABI khác C++ ABI ở những điểm nào?

**ABI (Application Binary Interface)** quy định cách symbol được xuất, đối số đi qua thanh ghi/stack, kích thước và alignment của data, calling convention, exception/unwinding và nhiều chi tiết platform/compiler khác.

| Vấn đề | C-style API | C++ API phức tạp |
| --- | --- | --- |
| Tên hàm | Một export như `engine_add` | Namespace, overload, **name mangling** |
| Gọi hàm | Function pointer theo C ABI | Member receiver `this`, virtual calls, constructors |
| Data types | Fixed-width integers, C pointers, C structs | `std::string`, `std::vector<T>`, inheritance, references |
| Object lifetime | `create/destroy` explicit | RAII, constructors/destructors, copy/move |
| Exceptions | Status/error code | C++ `throw`, exception types, unwinding |
| Template | Không trong C API | Có thể compile-time only/inline, thiếu export symbol |
| Binary portability | Rõ ràng hơn nếu hợp đồng được đo | Cần cùng C++ ABI/stdlib/toolchain và flags |

C++:

~~~cpp
// Minh họa overload, không phải chương trình độc lập.
namespace calc {
    int blend(int a, int b);
    double blend(double a, double b);
}
~~~

Compiler cần phân biệt hai overload ở mức symbol. Trên GCC/Clang Linux, tên export thường bị **mangled**; các compiler/ABI khác có quy tắc khác. `nm -C` hiển thị tên đã **demangle để con người đọc**, không phải raw string chắc chắn có thể đưa vào FFM `SymbolLookup.find`.

**Đừng giải bài toán bằng cách copy raw mangled symbols.** Có thể tra được một symbol của một binary/version cụ thể, nhưng vẫn còn vấn đề member calling convention, type layout, C++ exception ABI và lifetime. Đó không phải một interface được bảo đảm ổn định.

## 3. Ý nghĩa thực sự của `extern "C"`

~~~cpp
extern "C" int32_t engine_add(void *handle, int32_t value);
~~~

`extern "C"` yêu cầu C language linkage cho function được khai báo trong C++: nhờ vậy tên function và kiểu liên kết được mô tả theo C conventions của platform. Nó là công cụ quan trọng để **xuất một giao diện C từ code C++**.

Nhưng nó **không biến** mọi C++ type thành C-compatible type:

~~~cpp
// KHÔNG nên coi đây là giao diện portable cho FFM.
extern "C" std::vector<float> infer(std::string model);
~~~

Một function như vậy vẫn truyền/trả `std::vector` và `std::string` theo C++ object ABI. FFM không có `ValueLayout.STD_VECTOR`. Tương tự, `extern "C"` không tự bắt C++ exception, không gọi destructor giúp Java và không làm class layout trở nên portable.

Giao diện tốt hơn:

~~~c
/* C API minh họa:
   implementation C++ tự giải quyết vector/string. */
typedef struct engine_handle engine_handle;

int engine_create(const char *utf8_name,
                  engine_handle **out_handle);
int engine_add(engine_handle *handle, int32_t value);
int engine_sum(const engine_handle *handle,
               int64_t *out_total);
void engine_destroy(engine_handle *handle);
~~~

Trong C++ implementation, `engine_handle` có thể chứa `std::vector` và `std::string`. Java chỉ nhận một **opaque pointer**: biết cách giữ, truyền và giải phóng qua wrapper, nhưng **không dereference** lớp C++ bên trong.

## 4. Vì sao không mô tả C++ class bằng `MemoryLayout.structLayout`?

FFM hỗ trợ `MemoryLayout.structLayout` cho C-compatible struct và `unionLayout` cho union, nhưng việc mô tả đúng đòi biết `sizeof`, `alignof`, `offsetof`, padding và ABI thực.

C++ class với virtual methods/inheritance/STL có thể có:

- Vtable/vptr và dynamic dispatch theo compiler ABI.
- Multiple/virtual inheritance, base-class subobject offsets, thunks.
- `std::string` chứa internal buffer, capacity hoặc small-string optimization.
- `std::vector` có allocator-dependent representation và capacity/size metadata.
- Non-trivial constructors, destructors, copy/move semantics.

~~~cpp
class Base {
public:
    virtual int kind() const = 0;
    virtual ~Base() = default;
};

class Derived : public Base {
public:
    explicit Derived(std::string name);
    int kind() const override;
private:
    std::string name_;
    std::vector<int> values_;
};
~~~

Ngay cả nếu C++ compiler báo `sizeof(Derived)=N`, việc Java gọi `arena.allocate(N)` **không tạo một đối tượng Derived**: constructor C++ chưa chạy, vtable/STL internals chưa được xây, destructor cũng chưa có ai gọi.

FFM `MemorySegment.ofAddress(addr)` đại diện một native address; nó **không** tự tạo C++ dynamic type hay thực hiện `dynamic_cast`/RTTI/virtual dispatch. Cố đọc vtable từ offsets phỏng đoán là cách làm phụ thuộc compiler và có nguy cơ memory corruption.

**Thay thế:** chỉ cho C++ adapter tạo object bằng constructor/new, hủy bằng delete/destructor, gọi member functions và trả kết quả qua kiểu C kiểm chứng được.

## 5. JNI: có thể dùng C++ ở phía native, nhưng cần glue

JNI entrypoint có chữ ký do JVM/JNI quy định, nhưng phần thân có thể viết bằng C++ và link tới vendor C++ SDK:

~~~cpp
// Pseudocode: chưa phải chương trình độc lập.
JNIEXPORT jint JNICALL
Java_App_doWork(JNIEnv *env, jobject self, jlong nativeHandle) {
    // Xác minh handle và gọi C++ SDK bằng C++ compiler.
    // Chuyển đổi Java arrays -> std::vector<T> khi cần.
    // Catch C++ exception trước khi return về JVM.
}
~~~

Các việc JNI **không tự động** làm cho bạn:

1. Phân tích và chọn overloaded C++ methods từ Java reflection.
2. Chuyển Java `String`/`List`/`Map` thành `std::string`/`vector`/`map`.
3. Tạo C++ object hợp lệ từ Java `new` hoặc thu hồi bằng Java GC.
4. Bảo đảm `jlong` chứa native pointer còn sống/đúng type.
5. Bảo đảm C++ compiler/plugin ABI khớp vendor library.
6. Tự ánh xạ C++ exception sang Java exception.
7. Quản lý JNI local/global references, worker thread attachment và pending exceptions.

JNI có ích khi cần thao tác nhiều Java objects và muốn C++ native translation unit gọi class methods trực tiếp. Nhưng **JNI không phải bộ chuyển ABI C++ tổng quát**. Một JNI plugin vẫn phải được build, phát hành và test theo từng OS/CPU/toolchain mục tiêu.

### 5.1. JNI reference và thread ownership

Nếu một native C++ SDK gọi Java callback từ thread tạo bởi C++, cần dùng JVM attach/detach APIs theo JNI specification trước khi gọi JNI qua `JNIEnv*`. `JNIEnv*` không phải pointer dùng tự do trên mọi threads. Java objects được giữ qua lần gọi cần JNI `GlobalRef`, và phải `DeleteGlobalRef` khi đăng ký kết thúc; local references không được dùng như long-lived global handles.

Khi JNI gọi Java methods, cần kiểm tra `ExceptionCheck` hoặc các cách xử lý pending Java exception. Ngược lại, khi code C++ ném exception, JNI method phải **catch phía C++**, rồi chuyển sang status hoặc gọi `ThrowNew` theo JNI contract.

## 6. FFM: C header là biên giới có thể mô tả

FFM final từ **JDK 22** (JEP 454) cung cấp:

- `Linker.nativeLinker()`: native calling conventions hỗ trợ.
- `SymbolLookup.libraryLookup(...)` và `find("engine_add")`: tra symbol theo **tên export thực**.
- `FunctionDescriptor.of(...)` / `ofVoid(...)`: mô tả return type và C parameters bằng `MemoryLayout`.
- `MemorySegment` và `Arena`: buffer/pointer/lifetime trong Java.
- `MethodHandle.invokeExact`: gọi native function có carrier types phù hợp.
- `Linker.upcallStub`: tạo function pointer callback khi C API nhận callback.

Với C signature:

~~~c
int engine_add(engine_handle *handle, int32_t value);
~~~

descriptor trên Linux/x64 là:

~~~java
// Java 22+, trích đoạn, không độc lập.
FunctionDescriptor addSignature = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,   // C return int status
        ValueLayout.ADDRESS,    // engine_handle*
        ValueLayout.JAVA_INT);  // int32_t value
~~~

FFM có thể thực hiện lời gọi đó qua đúng ABI **mà không cần biết C++ class** phía sau `engine_handle`. `MemorySegment` nhận từ pointer là giá trị địa chỉ; nó không biến thành đối tượng Java chứa các member methods của class.

### 6.1. `jextract` hỗ trợ tới đâu?

Theo hướng dẫn OpenJDK, `jextract` phân tích **C headers** và tạo Java FFM bindings. Nó **không phải công cụ dịch mọi C++ templates/classes/overloads** thành Java classes. Với C++ library có C wrapper, `jextract` có thể đọc **wrapper header** rồi sinh bindings; vẫn cần tự thiết kế ownership và exception protocol.

Sơ đồ:

~~~text
C++ SDK (classes, templates, stdlib)
          |
       .cpp adapter -- compiler C++ tương thích SDK
          |
       C header + C exports
          |
      +---+------------------------+
      |                            |
Java FFM + jextract             JNI glue (nếu chọn JNI)
      |                            |
      +---------- Java ------------+
~~~

`jextract` không tự viết `engine_destroy`, không đảm bảo C++ object còn sống, không tự biết có callback đang chạy và không sửa C++ ABI incompatibility trong binary.

## 7. Thiết kế C adapter: một hợp đồng phải rõ từ đầu

Bài thực hành dùng class C++ chứa:

- `std::string name_` để minh họa kiểu có allocator/lifetime phức tạp.
- `std::vector<int32_t> values_` để minh họa dynamic container.
- C++ constructor/destructor và method `add`.
- Method `sum` trả kết quả 64-bit, có kiểm tra tràn số.
- Wrapper C trả status và ghi output qua out parameter.

Thiết kế API:

| C function | Đầu vào | C return | Kết quả |
| --- | --- | --- | --- |
| `engine_create` | UTF-8 C string, `engine_handle**` | Status | Opaque handle |
| `engine_add` | Handle, `int32_t` | Status | Push into C++ vector |
| `engine_sum` | Handle, `int64_t*` | Status | Tổng |
| `engine_count` | Handle, `int64_t*` | Status | Số phần tử |
| `engine_label_bytes` | Handle, `int64_t*` | Status | Bytes của label |
| `engine_destroy` | Handle | `void` | Hủy C++ object |

**Lifetime contract:**

- `create` cấp phát object bằng C++ `new`; `destroy` dùng đúng C++ `delete`.
- Handle thành công phải được destroy **chính xác một lần**; không dùng tiếp sau destroy.
- Wrapper ở demo **không thread-safe cho concurrent add/destroy**; ứng dụng Java dùng một thread.
- C++ exceptions được catch trong adapter, không thoát qua C function boundary.
- Input label là NUL-terminated UTF-8 và được copy trong create; output slots do Java cấp phát.
- Mọi status phải được kiểm tra **trước khi Java đọc out parameters**.
- C++ destructor được gọi trước khi FFM unload thư viện/close Arena liên quan.

## 8. File C-compatible header hoàn chỉnh: `engine_bridge.h`

~~~c
#ifndef ENGINE_BRIDGE_H
#define ENGINE_BRIDGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Không lộ các member của struct này cho C/Java. */
typedef struct engine_handle engine_handle;

enum {
    ENGINE_OK       = 0,
    ENGINE_EINVAL   = 1,
    ENGINE_ENOMEM   = 2,
    ENGINE_ERANGE   = 3,
    ENGINE_EUNKNOWN = 4
};

int engine_create(const char *label_utf8,
                  engine_handle **out_handle);
int engine_add(engine_handle *handle, int32_t value);
int engine_sum(const engine_handle *handle, int64_t *out_sum);
int engine_count(const engine_handle *handle, int64_t *out_count);
int engine_label_bytes(const engine_handle *handle,
                       int64_t *out_bytes);
void engine_destroy(engine_handle *handle);

#ifdef __cplusplus
}
#endif
#endif
~~~

**Vì sao header này được C compiler chấp nhận?** `extern "C"` được bọc bằng `#ifdef __cplusplus`; các kiểu khai báo thuộc chuẩn C; `engine_handle` chỉ được forward-declare và mọi chức năng xuất qua C function names riêng.

Không expose `class Engine`, `std::vector` hoặc `std::string` trong header. Bản C++ implementation sẽ định nghĩa `struct engine_handle` đầy đủ.

## 9. File C++17 implementation: `engine_bridge.cpp`

~~~cpp
#include "engine_bridge.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

class Engine {
public:
    explicit Engine(std::string label)
        : label_(std::move(label)) {}

    void add(std::int32_t value) {
        values_.push_back(value);
    }

    bool trySum(std::int64_t &out) const noexcept {
        std::int64_t total = 0;
        const std::int64_t maximum =
                std::numeric_limits<std::int64_t>::max();
        const std::int64_t minimum =
                std::numeric_limits<std::int64_t>::min();

        for (std::int32_t v : values_) {
            const std::int64_t x = v;
            if ((x > 0 && total > maximum - x) ||
                (x < 0 && total < minimum - x)) {
                return false;
            }
            total += x;
        }

        out = total;
        return true;
    }

    std::size_t count() const noexcept {
        return values_.size();
    }

    std::size_t labelBytes() const noexcept {
        return label_.size();
    }

private:
    std::string label_;
    std::vector<std::int32_t> values_;
};

struct engine_handle {
    explicit engine_handle(std::string label)
        : engine(std::move(label)) {}
    Engine engine;
};

static int writeCount(
        std::size_t n, std::int64_t *out) noexcept {
    if (out == nullptr) {
        return ENGINE_EINVAL;
    }
    const auto limit = static_cast<std::uintmax_t>(
            std::numeric_limits<std::int64_t>::max());
    if (static_cast<std::uintmax_t>(n) > limit) {
        return ENGINE_ERANGE;
    }
    *out = static_cast<std::int64_t>(n);
    return ENGINE_OK;
}

extern "C" int engine_create(
        const char *label_utf8,
        engine_handle **out_handle) {
    if (out_handle == nullptr) {
        return ENGINE_EINVAL;
    }
    *out_handle = nullptr;
    if (label_utf8 == nullptr) {
        return ENGINE_EINVAL;
    }

    try {
        auto owned = std::make_unique<engine_handle>(
                std::string(label_utf8));
        *out_handle = owned.release();
        return ENGINE_OK;
    } catch (const std::bad_alloc &) {
        return ENGINE_ENOMEM;
    } catch (...) {
        return ENGINE_EUNKNOWN;
    }
}

extern "C" int engine_add(
        engine_handle *handle, std::int32_t value) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }

    try {
        handle->engine.add(value);
        return ENGINE_OK;
    } catch (const std::bad_alloc &) {
        return ENGINE_ENOMEM;
    } catch (...) {
        return ENGINE_EUNKNOWN;
    }
}

extern "C" int engine_sum(
        const engine_handle *handle,
        std::int64_t *out_sum) {
    if (handle == nullptr || out_sum == nullptr) {
        return ENGINE_EINVAL;
    }
    std::int64_t sum = 0;
    if (!handle->engine.trySum(sum)) {
        return ENGINE_ERANGE;
    }
    *out_sum = sum;
    return ENGINE_OK;
}

extern "C" int engine_count(
        const engine_handle *handle,
        std::int64_t *out_count) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }
    return writeCount(handle->engine.count(), out_count);
}

extern "C" int engine_label_bytes(
        const engine_handle *handle,
        std::int64_t *out_bytes) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }
    return writeCount(handle->engine.labelBytes(), out_bytes);
}

extern "C" void engine_destroy(engine_handle *handle) {
    delete handle;
}
~~~

### 9.1. Điều mà code C++ làm thay Java

- `std::make_unique<engine_handle>` gọi constructor, tạo `Engine` và `std::string` hợp lệ.
- `engine_add` gọi `std::vector::push_back`, C++ runtime quản lý allocation và reallocation.
- `engine_sum` đọc vector, kiểm tra signed overflow trước khi cộng.
- `engine_label_bytes` tính số **byte** trong C++ string, không phải Java UTF-16 length.
- `engine_destroy` gọi destructor (trực tiếp hoặc gián tiếp) của `Engine` và members; không dùng `free`/Java Arena để hủy chúng.
- `catch(std::bad_alloc)` và `catch(...)` ở những functions có allocation ngăn C++ exceptions đi qua C ABI.
- Wrapper trả status, do đó bên Java có thể biến status thành Java exception **trong Java**, sau khi native call đã return.

`std::size_t` được chuyển sang `int64_t` với kiểm tra range. C wrapper tránh expose C++ `std::size_t` hoặc `std::string` ở biên. Với ứng dụng production có thể dùng `size_t` trong C API nếu binding theo đúng ABI, nhưng cần mô tả kích thước tương thích bằng canonical layouts của FFM.

### 9.2. Giới hạn của validation trong ví dụ

Wrapper có thể phát hiện null handle, nhưng **không thể xác minh tùy tiện một non-null pointer do caller cung cấp thực sự trỏ đến một object còn sống**. Nếu Java gọi `engine_add` sau khi `engine_destroy`, pointer đó dangling và C++ dereference gây undefined behavior. Phải thiết kế owner, state và concurrency protocol phía ứng dụng.

Với nhiều Java threads, `std::vector` trong demo không được truy cập mutable cùng lúc. Để hỗ trợ concurrency, thêm lock trong adapter hoặc giới hạn mọi call vào một owner executor; `Arena.ofShared()` **không tự biến C++ vector thành thread-safe**.

## 10. Java 22+ FFM chương trình hoàn chỉnh: `CppBridgeFfmDemo.java`

Trong Java, tất cả native method calls đều dùng C ABI của wrapper. Một `engine_handle*` đọc ra từ out parameter là **opaque pointer**: Java chỉ truyền lại cho wrapper, không đọc member offsets.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CppBridgeFfmDemo {
    private static void check(String operation, int status) {
        if (status != 0) {
            throw new IllegalStateException(
                    operation + ": native status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            Path path = Path.of("libenginebridge.so")
                    .toAbsolutePath();

            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle create = linker.downcallHandle(
                    library.find("engine_create").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle add = linker.downcallHandle(
                    library.find("engine_add").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            MethodHandle sum = linker.downcallHandle(
                    library.find("engine_sum").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle count = linker.downcallHandle(
                    library.find("engine_count").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle labelBytes = linker.downcallHandle(
                    library.find("engine_label_bytes").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle destroy = linker.downcallHandle(
                    library.find("engine_destroy").orElseThrow(),
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS));

            MemorySegment label = arena.allocateFrom("demo");
            MemorySegment slot = arena.allocate(
                    ValueLayout.ADDRESS);

            int status = (int) create.invokeExact(label, slot);
            check("engine_create", status);

            MemorySegment handle = slot.get(
                    ValueLayout.ADDRESS, 0);
            if (handle.address() == 0L) {
                throw new IllegalStateException(
                        "engine_create returned NULL");
            }

            try {
                check("add 3",
                        (int) add.invokeExact(handle, 3));
                check("add 5",
                        (int) add.invokeExact(handle, 5));
                check("add 9",
                        (int) add.invokeExact(handle, 9));

                MemorySegment countOut = arena.allocate(
                        ValueLayout.JAVA_LONG);
                MemorySegment sumOut = arena.allocate(
                        ValueLayout.JAVA_LONG);
                MemorySegment nameOut = arena.allocate(
                        ValueLayout.JAVA_LONG);

                check("engine_count",
                        (int) count.invokeExact(handle, countOut));
                check("engine_sum",
                        (int) sum.invokeExact(handle, sumOut));
                check("engine_label_bytes",
                        (int) labelBytes.invokeExact(handle, nameOut));

                System.out.println("count="
                        + countOut.get(ValueLayout.JAVA_LONG, 0));
                System.out.println("sum="
                        + sumOut.get(ValueLayout.JAVA_LONG, 0));
                System.out.println("labelBytes="
                        + nameOut.get(ValueLayout.JAVA_LONG, 0));
            } finally {
                /*
                 * C++ delete CHẠY TRƯỚC Arena.close.
                 * Tuyệt đối không dùng handle sau đây.
                 */
                destroy.invokeExact(handle);
                System.out.println("destroyed=true");
            }
        }
    }
}
~~~

### 10.1. Build và chạy trên Linux x86-64

Dùng **C++17 compiler** (GCC/Clang) và **JDK 22+**. Tạo ba files `engine_bridge.h`, `engine_bridge.cpp`, `CppBridgeFfmDemo.java` trong cùng một thư mục, sau đó:

~~~bash
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -o libenginebridge.so engine_bridge.cpp

javac CppBridgeFfmDemo.java

java --enable-native-access=ALL-UNNAMED CppBridgeFfmDemo
~~~

**Stdout kỳ vọng:**

~~~text
count=3
sum=17
labelBytes=4
destroyed=true
~~~

Giải thích:

- C++ `std::vector` nhận ba values 3, 5, 9 → count 3 và sum 17.
- `std::string("demo")` có 4 bytes UTF-8 → labelBytes 4.
- `engine_destroy` được gọi đúng một lần ở `finally`, trước khi đóng Arena.
- `--enable-native-access=ALL-UNNAMED` bật restricted FFM operations cho class chạy ở classpath. JDK 22 FFM đã final, không dùng `--enable-preview`.
- Thư viện được build bằng `c++` driver vì cần link C++ runtime/stdlib; dùng `cc` mà không link stdlib có thể tạo unresolved symbols.

Để xem các exported C symbols (khi có `nm`):

~~~bash
nm -D --defined-only libenginebridge.so | grep engine_
~~~

Kỳ vọng có `engine_create`, `engine_add`, `engine_sum`, `engine_count`, `engine_label_bytes` và `engine_destroy`. Có thể còn C++ symbols phụ do compiler sinh; Java không gọi chúng trực tiếp.

### 10.2. ABI mapping trong Java

| C wrapper parameter | FFM layout | Java carrier |
| --- | --- | --- |
| Return `int` status | `ValueLayout.JAVA_INT` | `int` |
| `engine_handle*` | `ValueLayout.ADDRESS` | `MemorySegment` |
| `engine_handle** out` | `ValueLayout.ADDRESS` | `MemorySegment` của một pointer slot |
| `const char*` | `ValueLayout.ADDRESS` | `MemorySegment` UTF-8 buffer |
| `int32_t` | `ValueLayout.JAVA_INT` | `int` |
| `int64_t*` | `ValueLayout.ADDRESS` | `MemorySegment` của 8-byte output |
| Return `void` | `FunctionDescriptor.ofVoid(...)` | Java `void` callsite |

Trên Linux x86-64, `int` C là 32 bit và `int64_t` là 64 bit. Một C pointer được mô tả bằng `ADDRESS` chứ không phải layout của object nó trỏ tới.

`slot` được cấp phát bằng `arena.allocate(ValueLayout.ADDRESS)`; C ghi handle pointer vào đó. Java `slot.get(ValueLayout.ADDRESS,0)` trả một pointer-value segment. **Không dùng `handle.get(...)` để đoán C++ fields**: `engine_handle` opaque, pointer segment có thể zero-length và object do C++ sở hữu.

### 10.3. Hai miền sở hữu khác nhau

~~~text
Java arena open
   |
   +-- label/slot/out buffers     [Arena-owned]
   +-- C library lookup          [Arena-related lifetime]
   |
   +-- engine_create
   |      +-- new engine_handle  [C++-owned]
   |      +-- std::string/vector [C++ internals]
   |
   +-- engine_add, count, sum
   |
   +-- finally: engine_destroy   [C++ delete]
   |
   +-- Arena.close              [FFM buffer/library lifetime]
~~~

**Không thể thay `engine_destroy` bằng `arena.close()`.** Arena không sở hữu C++ allocation tạo bằng `new`. Ngược lại, `engine_destroy` không tự giải phóng các FFM output buffers do arena cấp.

Nếu việc `engine_create` thất bại, code C đặt `*out_handle=nullptr` và Java không vào nhánh destroy. Nếu create thành công, `finally` luôn thực thi destroy khi Java code sau đó ném exception.

## 11. Ví dụ JNI chạy độc lập, Java 17+: C++ nằm bên trong JNI method

Ví dụ thứ hai chứng minh JNI **không bị cấm** gọi code C++. Nó không cần C wrapper riêng vì JNI function đã là một native entrypoint do JVM hiểu.

### 11.1. Tệp `JniCppDemo.java`

~~~java
public final class JniCppDemo {
    static {
        System.loadLibrary("jnicppdemo");
    }

    private static native int calculate();

    public static void main(String[] args) {
        System.out.println("jniResult=" + calculate());
    }
}
~~~

### 11.2. Tệp `jni_cpp_demo.cpp`

~~~cpp
#include "JniCppDemo.h"

#include <exception>
#include <numeric>
#include <vector>

static void throwRuntime(JNIEnv *env, const char *message) {
    jclass klass = env->FindClass(
            "java/lang/RuntimeException");
    if (klass != nullptr) {
        env->ThrowNew(klass, message);
        env->DeleteLocalRef(klass);
    }
}

extern "C" JNIEXPORT jint JNICALL
Java_JniCppDemo_calculate(JNIEnv *env, jclass clazz) {
    (void)clazz;

    try {
        std::vector<int> values{10, 20, 12};
        int result = std::accumulate(
                values.begin(), values.end(), 0);
        return static_cast<jint>(result);
    } catch (const std::exception &error) {
        throwRuntime(env, error.what());
        return 0;
    } catch (...) {
        throwRuntime(env, "Unknown C++ error");
        return 0;
    }
}
~~~

Mã native được biên dịch bằng C++ compiler, vì thế nó tạo `std::vector` và dùng STL trực tiếp. Nó **bắt C++ exception** trước khi return về JVM. `ThrowNew` đưa Java exception vào pending state của JNI; native code trả một `jint` vì chữ ký yêu cầu, nhưng Java sẽ quan sát exception nếu nó đã được thiết lập thành công.

### 11.3. Lệnh build/run JNI

Đặt `JAVA_HOME` trỏ đến JDK dùng để compile/running (JDK 17+ trên Linux), rồi chạy:

~~~bash
javac -h . JniCppDemo.java

c++ -std=c++17 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicppdemo.so jni_cpp_demo.cpp

java -Djava.library.path=. JniCppDemo
~~~

**Stdout:**

~~~text
jniResult=42
~~~

Đây không phải ví dụ “JNI tự hiểu `std::vector`”: **C++ compiler** làm việc đó; JNI chỉ là biên Java → native. Với vendor library thật, C++ JNI translation unit phải include đúng SDK header và link đúng vendor binaries/ABI.

## 12. Một số cạm bẫy khi truyền dữ liệu

### 12.1. Java `String` khác `std::string`

FFM ví dụ dùng `arena.allocateFrom("demo")` tạo **NUL-terminated UTF-8 buffer**, rồi C++ copy vào `std::string`. Java String có UTF-16 code units, còn `std::string::size()` đếm bytes; hai độ dài có thể khác, nhất là tiếng Việt và emoji.

Nếu dữ liệu có NUL bên trong, C-string `const char*` sẽ bị cắt ở byte NUL đầu tiên. Với dữ liệu tùy ý nên dùng `const uint8_t* data, size_t length` và quy định encoding, bounds và lifetime rõ ràng.

Không return pointer tới `std::string::c_str()` của một temporary C++ string đã bị destruct. Nếu trả borrowed pointer, tài liệu hóa object nào giữ vùng nhớ sống và thao tác nào có thể invalidate nó.

### 12.2. Java array khác `std::vector<T>`

FFM không cho truyền Java `List<Float>` như `std::vector<float>` by value. C wrapper thường dùng `float* values, size_t count`, sau đó adapter C++ copy/tạo vector. Nếu muốn tránh copy, cần bảo đảm buffer không bị thay đổi/giải phóng khi native code sử dụng.

`std::vector::data()` có thể thay đổi khi vector reallocate do `push_back`, `reserve` hoặc destructor; không lưu pointer rồi trả cho Java dùng vô hạn. Một API two-pass (hỏi size rồi caller cấp buffer để copy) có thể hợp lý, nhưng concurrency khiến size thay đổi giữa hai calls; phải có snapshot/version/retry contract.

### 12.3. C pointer không tự mang bounds

`engine_handle*` là pointer opaque. Không thể gọi `MemorySegment.ofAddress(raw).reinterpret(largeSize)` chỉ để “thử đọc” cấu trúc C++. Tự gán bounds sai là thao tác restricted và có nguy cơ crash. Chỉ truyền pointer cho C wrapper hiểu đúng object type/lifetime.

### 12.4. ABI pointer/number widths và endianness

Trong C API, dùng `int32_t`/`int64_t` giảm một số khác biệt width. Nhưng pointer size, alignment, char encoding, calling convention, layout của C struct và ABI của vendor library vẫn phải được kiểm tra theo OS/architecture. C `long` trên Linux x64 thường 64 bit, còn Windows x64 thường 32 bit; không luôn map C `long` thành Java `JAVA_LONG`.

Khi C interface xuất `size_t`, xem `Linker.nativeLinker().canonicalLayouts()` thay vì đoán width. C ABI wrapper không làm Java binary Linux chạy được với Windows DLL.

## 13. C++ exceptions và error handling ở biên native

C++ native implementation có thể `throw std::bad_alloc` hoặc `std::runtime_error`. FFM không tự chuyển chúng thành Java exceptions; JNI cũng không tự làm điều đó một cách an toàn.

Cách C wrapper mẫu sử dụng:

~~~c
/* Giao thức C công khai. */
enum {
    ENGINE_OK       = 0,
    ENGINE_EINVAL   = 1,
    ENGINE_ENOMEM   = 2,
    ENGINE_ERANGE   = 3,
    ENGINE_EUNKNOWN = 4
};
~~~

Bên C++:

~~~cpp
// Trích đoạn logic, không độc lập.
try {
    // Gọi C++ method; có thể throw.
    return ENGINE_OK;
} catch (const std::bad_alloc &) {
    return ENGINE_ENOMEM;
} catch (...) {
    return ENGINE_EUNKNOWN;
}
~~~

Bên Java đọc **status** trước khi đọc `out_sum`. Mã lỗi phải có hợp đồng: output có bị thay đổi khi failure không, lỗi có thể retry không, native state còn usable không.

Nếu cần error message, dùng một API C `get_error(buffer,capacity,written)` hoặc per-call error buffer có encoding cụ thể. Một global `last_error` có thể bị threads khác ghi đè; `thread_local` cũng đòi xem thread nào thực hiện từng downcall và native async work.

Trong JNI, sau `env->ThrowNew(...)` cần tuân theo quy tắc pending Java exception; đa số JNI functions không được gọi tùy tiện khi pending exception, và một số API có thể trả NULL do OOME. C++ exception phải được bắt **trước** JNI native method return.

## 14. Native ownership, use-after-free và concurrency

Có ít nhất ba dạng lifetime khác nhau:

| Tài nguyên | Ai cấp phát | Ai giải phóng đúng |
| --- | --- | --- |
| C++ object bằng `new` | C++ library/adapter | C++ `delete` qua `engine_destroy` |
| FFM buffer trong `Arena.ofConfined` | Java FFM Arena | Java `arena.close()` trên owner |
| JNI global reference | JNI `NewGlobalRef` | JNI `DeleteGlobalRef` |
| Native vendor allocation | Vendor API | Vendor-specific disposer |
| FFM upcall stub | `Linker.upcallStub`/Arena | Unregister/drain callbacks trước close |
| Java object/array | JVM | Java GC, native chỉ giữ references hợp lệ |

**Không trộn allocators**: `malloc/free`, C++ `new/delete`, FFM Arena và vendor memory pool không tương đương.

### 14.1. Một pointer non-NULL vẫn có thể dangling

~~~text
Java thread A                 Java thread B
--------------------          -------------------------
engine_add(handle, 7)
                              engine_destroy(handle)
C++ vector đang thay đổi      delete object
=> use-after-free / crash
~~~

Wrapper C++ ở ví dụ không triển khai lock cho concurrent operations. Trong ứng dụng Java thật, quản lý một owner thread/executor, hoặc class `AutoCloseable` giữ state OPEN/CLOSING/CLOSED và đợi in-flight calls trước khi destroy.

Kiểm tra `handle.address() != 0` không ngăn use-after-free. Một pointer có thể vẫn khác 0 sau khi object đã bị delete.

### 14.2. Async callbacks làm bài toán khó hơn

Một C++ SDK có thể nhận `std::function<void(Event)>`, giữ lại và gọi ở native worker thread. Java FFM chỉ có thể trao đổi qua một C callback pointer/user-data protocol đã được adapter định nghĩa. Java phải giữ `upcallStub`/Arena còn sống tới khi native **unregister và drain** mọi callback đã bắt đầu hoặc đã reserve quyền gọi.

Trong JNI, worker tạo bởi C++ cần attach/detach với JVM để dùng JNI, không được dùng chung `JNIEnv*` giữa threads. Global Java references cũng phải được thu hồi sau khi không còn callbacks.

Timeout hay Java `Future.cancel(true)` không tự chứng minh native code đã ngừng giữ pointer. Không đóng Arena hoặc destroy native context khi chưa có acknowledgement an toàn.

## 15. Khi không được sửa C++ library

Bốn tình huống:

| Bạn có gì? | Phương án khả thi |
| --- | --- |
| Vendor C++ header + linkable SDK/toolchain | Viết JNI bridge C++ hoặc C API adapter |
| Có sẵn C wrapper chính thức | FFM/JNI gọi C API, cân nhắc `jextract` |
| Chỉ có CLI/service API | Dùng subprocess/IPC/RPC, schema/version/deadline rõ |
| Chỉ có opaque binary và không có supported interface | Yêu cầu vendor API/SDK; không tự đoán vtable/mangled symbols cho production |

**Một C adapter vẫn phụ thuộc vendor C++ ABI ở phía bên trong.** Nếu SDK được build bằng incompatible compiler/stdlib hoặc các cờ như `_GLIBCXX_USE_CXX11_ABI` khác nhau, adapter có thể không link/chạy đúng. `extern "C"` chỉ làm **biên công khai** dễ kiểm soát hơn, không chữa bất đồng ABI giữa các thư viện C++.

Nếu cần tránh một native library không ổn định làm chết JVM, process isolation có lợi: chạy native component trong process riêng, giao tiếp qua RPC/IPC với data schema, timeout và restart policy. Đổi lại có chi phí serialization/IPC và phải không truyền raw memory pointers xuyên qua process.

### 15.1. Vì sao không dùng JNI/FFM để “đoán vtable”?

Vtable layout, virtual base offsets, destructors/thunks có thể thay đổi theo compiler và version. Một ứng dụng production tự đọc một địa chỉ vtable theo số slot phỏng đoán không có hợp đồng ABI tin cậy. Ngay cả khi “chạy trên máy tôi”, chuyển một compiler flag có thể khiến method được gọi sai.

Điều này khác với một C function pointer đã được API vendor công bố có prototype rõ: trường hợp đó FFM có thể mô tả `FunctionDescriptor` chính xác.

## 16. Kiểm thử binding C++ ↔ Java

Những test tối thiểu:

1. **Build ABI**: build adapter bằng đúng compiler/runtime vendor; load đúng architecture, stdlib dependencies.
2. **Symbol exports**: `nm -D` hoặc tool tương ứng xác minh C exports thật, không dùng demangled names.
3. **Positive path**: create → add → sum/count → destroy, đối chiếu C++ expected values.
4. **Error path**: null input/out pointer, invalid status, allocation failure simulation, overflow.
5. **Resource ownership**: no leaks/double-free, close đúng một lần, Java use-after-close bị chặn ở wrapper.
6. **Concurrent access**: nếu cho phép nhiều threads, stress add/read/destroy và kiểm tra synchronization.
7. **Strings**: ASCII, Unicode, embedded NUL contract, long strings, invalid UTF-8.
8. **Arrays**: zero-length, huge length, capacity mismatch, signed vs unsigned, overlap và alignment.
9. **Vendor updates**: C++ class implementation thay đổi mà C ABI vẫn ổn định theo contract; test regeneration khi header C đổi.
10. **Callbacks**: async event, unregister/drain, Arena lifetime, pending exceptions.
11. **Platform matrix**: Linux/Windows/macOS và x86-64/ARM64 chỉ khi thực sự hỗ trợ; không copy file `.so` sang Windows.
12. **Failure containment**: native crash, compiler sanitizer reports, process restart/IPC nếu cần.

Một binding tốt phải kiểm **hai chiều**: Java tạo input mà C++ tính đúng; C++ tạo output mà Java đọc đúng. Java tự ghi rồi đọc cùng một sai layout vẫn có thể trông hợp lệ, nên cần native-side assertions và test trên ABI thật.

## 17. Các anti-pattern dễ nhầm

| Anti-pattern | Vấn đề | Thay thế |
| --- | --- | --- |
| `SymbolLookup.find("Class::method")` | Không giải overload/mangled symbol/receiver | C wrapper function |
| Copy symbol từ `nm -C` | Tên đã demangle, không phải ABI contract | C exports có tên rõ |
| `extern "C" std::vector<T> f(...)` | C++ container ABI vẫn lộ | Buffer + length/status/opaque handle |
| Java tự `arena.allocate(sizeofClass)` | Chưa chạy constructor C++ | C++ create wrapper |
| Java `free` object tạo bằng C++ `new` | Destructor/allocator sai | `engine_destroy` |
| Java giữ `std::vector::data()` sau `push_back` | Reallocation có thể invalidate pointer | Snapshot/copy/lease |
| C++ exception thoát qua FFM/JNI | Không có Java exception mapping tự động | Catch và chuyển status/ThrowNew |
| JNI share `JNIEnv*` giữa native threads | Không tuân JNI thread association | AttachCurrentThread, local JNIEnv |
| Java `jlong` handle dùng sau destroy | Dangling pointer | Owner lifecycle/state guard |
| C++ ABI adapter khác vendor | Link/runtime mismatch | Toolchain/stdlib/flags tương thích |
| FFM `FunctionDescriptor` đoán C++ struct by value | Class ABI không được mô tả đầy đủ | C opaque pointer adapter |
| `--enable-native-access` để sửa symbol ABI | Flag cấp quyền không thay ABI | C interface và đúng toolchain |
| Callbacks chưa drain mà close Arena | Native gọi upcall stub đã invalid | Unregister, drain, join, close |
| Bỏ native cleanup vì có GC | Leak/timing không xác định | AutoCloseable/native destroy rõ |
| Đo hiệu năng bằng vài call nhỏ rồi kết luận JNI/FFM “luôn nhanh hơn” | Overhead theo workload | Benchmark end-to-end thực |

## 18. Checklist trước khi merge

- [ ] Đã xác định C++ SDK, C++ standard library, toolchain và ABI đích?
- [ ] Có header C-compatible hoặc JNI C++ glue, không dựa vào mangled class symbols?
- [ ] C API không lộ `std::string`/`vector`/templates/virtual classes by value?
- [ ] C++ constructors/destructors chạy đúng phía native?
- [ ] Java chỉ giữ opaque handles với lifetime được kiểm soát?
- [ ] Mọi C++ exceptions bị catch trước native/Java boundary?
- [ ] Error/status code và output validity được mô tả rõ?
- [ ] Có một API `destroy` và một Java owner gọi đúng một lần?
- [ ] Không có concurrent use/destroy chưa được đồng bộ?
- [ ] C `long`, `size_t`, fixed-width ints, pointer layouts theo ABI đúng?
- [ ] Java String/arrays được chuyển đổi đúng encoding, length, ownership?
- [ ] Native borrowed buffers không hết lifetime giữa lúc Java dùng?
- [ ] JNI local/global refs, pending exceptions và thread attach đúng?
- [ ] FFM `Linker`/`SymbolLookup`/`FunctionDescriptor` khớp C signatures?
- [ ] FFM native access flags đúng JDK/module?
- [ ] Có unregister/drain trước close upcall Arena/library nếu có async?
- [ ] Có native-side tests, sanitizers hoặc CI cho platforms thực hỗ trợ?
- [ ] Nếu không có SDK hợp lệ, đã cân nhắc vendor C API hoặc IPC thay vì reverse-engineer ABI?

## 19. Câu hỏi tự kiểm tra

1. Vì sao một C++ method `Analyzer::infer(std::vector<float>)` không được mô tả trực tiếp như một C function thông thường?
2. `extern "C"` có biến `std::vector` thành một C struct portable không?
3. JNI có thể viết bằng C++ và gọi STL không? Tại sao vẫn phải tạo glue?
4. Nếu `SymbolLookup.find("name")` tìm ra raw C++ symbol, có nghĩa ABI descriptor đúng chưa?
5. Vì sao chỉ biết `sizeof(CppClass)` không đủ để Java tạo instance bằng Arena?
6. Tại sao `engine_handle*` nên opaque đối với Java?
7. Object cấp bằng `new` nên được giải phóng bằng gì?
8. Nếu Java đổi `std::string` thành buffer UTF-8, cần quy định những yếu tố nào?
9. `std::vector::data()` có thể invalid trong tình huống nào?
10. C++ exceptions phải xử lý ra sao trong C wrapper? Trong JNI?
11. `jextract` có phải công cụ dịch C++ templates/classes tổng quát không?
12. Nếu vendor toolchain C++ khác adapter, `extern "C"` có khắc phục mọi mismatch không?
13. Khi hai Java threads dùng và destroy cùng handle, nguy cơ gì?
14. FFM Arena có sở hữu một object C++ được `new` trong wrapper không?
15. Vì sao FFM `--enable-native-access` không giải quyết ABI của vtable?
16. Nếu vendor không cấp header/API nhưng có CLI, giải pháp khác native loading là gì?
17. Khi callback chạy bất đồng bộ, phải làm gì trước khi close Arena?
18. Vì sao C API fixed-width + opaque handles thường dễ duy trì hơn expose C++ class layout?

**Đáp án gợi ý:** (1) member/overload/template/STL ABI; (2) không, chỉ language linkage; (3) có, nhưng C++ compiler/Java conversions/lifetime phải được viết; (4) chưa, symbol không chứa đủ signature/ownership; (5) constructor/object model chưa chạy; (6) không phụ thuộc class layout/vtable; (7) C++ destroy/delete đúng type; (8) UTF-8, NUL, length, ownership, lifetime; (9) reallocation/destructor; (10) catch thành status hoặc JNI ThrowNew; (11) không, chỉ C headers; (12) không; (13) use-after-free/race; (14) không; (15) permission flag không định nghĩa C++ ABI; (16) IPC/subprocess; (17) unregister và drain callbacks; (18) giảm ABI surface và dễ kiểm chứng/version.

## 20. Tài liệu tham khảo chính thức

- [Oracle JDK 22 — `Linker`, C ABI, downcall/upcall và canonical layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `FunctionDescriptor`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle JDK 22 — `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `Arena` và `MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [OpenJDK jextract Guide — giới hạn C headers và C layer cho C++](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md)
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle JNI Specification — Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [cppreference — C++ language linkage, `extern "C"`](https://en.cppreference.com/w/cpp/language/language_linkage)
- [GCC libstdc++ ABI](https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html)

**Kết luận:** JNI **có thể chạy C++ code** trong native methods, nhưng người phát triển vẫn phải viết glue chuyển Java objects ↔ C++ objects, quản lý lifetime, C++ exceptions và compiler ABI. FFM **không tự hiểu API C++ phức tạp**; nó phù hợp khi có C ABI ổn định. Một C++ adapter xuất **`extern "C"` functions, opaque handles, status/out parameters và explicit create/destroy** thường là lựa chọn rõ ràng nhất để làm Java binding có thể kiểm thử. Khi không có C header/SDK tương thích, không đoán mangled symbols/vtable rồi gọi trực tiếp trong production; hãy yêu cầu vendor interface hoặc dùng process/IPC boundary phù hợp.
