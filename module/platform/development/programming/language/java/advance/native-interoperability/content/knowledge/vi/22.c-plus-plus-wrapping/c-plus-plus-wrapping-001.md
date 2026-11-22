# Vì sao lớp, nạp chồng và ABI C++ cần được xem xét trước khi liên kết

## Mục tiêu học tập

Một thư viện C++ không chỉ chứa các hàm có tên. Nó có **class**, **constructor/destructor**, **method overloading**, **virtual dispatch**, **templates**, **STL containers**, **exceptions** và các quy ước ABI do compiler/toolchain quyết định. Khi Java muốn gọi native code thông qua **Foreign Function & Memory API (FFM)** hoặc **JNI**, các chi tiết đó ảnh hưởng trực tiếp đến tên symbol, calling convention, cách truyền dữ liệu, vòng đời object và khả năng tương thích giữa các bản build.

Câu hỏi trung tâm: **Vì sao không thể chỉ nhìn tên phương thức trong C++ rồi dùng Java tìm symbol và gọi nó như hàm C?**

Sau bài này bạn sẽ:

1. Hiểu **name mangling** và lý do C++ overloads cần các symbol phân biệt ở cấp binary.
2. Giải thích rủi ro của **C++ class layout, implicit this, virtual table, multiple inheritance** và RTTI.
3. Phân biệt **C linkage** do **extern "C"** tạo ra với một **C ABI contract thực sự an toàn**.
4. Giải thích vì sao C++ **exceptions, STL, allocator, constructor/destructor** phải được quản lý ở native boundary.
5. Thiết kế một **C-compatible façade**: opaque handles, các tên hàm C riêng, status codes, out parameters và create/destroy cân đối.
6. Tự biên dịch thư viện C++17, tìm exported symbols bằng công cụ native và gọi thư viện qua **Java 22+ FFM**.
7. Biết lúc nào nên chọn **FFM, JNI, jextract**, và cách kiểm tra mismatch giữa Linux/GCC, Windows/MSVC và các ABI khác.

**Môi trường ví dụ:** C++17 trên Linux x64, JDK 22+ (FFM đã trở thành API final từ JDK 22, theo JEP 454). Với JDK 17, vẫn có thể dùng C façade qua JNI, nhưng ví dụ package **java.lang.foreign** không biên dịch nguyên xi trên JDK 17; JDK 21 sử dụng FFM preview khác.

## 1. Ba ranh giới phải hiểu rõ

~~~text
Java code
   |
   | FFM SymbolLookup / Linker / FunctionDescriptor
   | hoặc JNI native method
   v
C-compatible exported functions           ← ABI ổn định theo contract
   |
   | gọi C++ object/method bằng đúng native compiler
   v
C++ implementation (classes, overloads, STL, exceptions)
   |
   v
Native library .so / .dll / .dylib
~~~

Một ứng dụng Java thực tế có thể cần gọi **Counter::add(int)**, nhưng Linker của FFM không tự biết **Counter** là một C++ class, không tự sinh C++ constructor call, không tự tìm overloaded method, và không tự diễn giải vtable. Nó cần một **địa chỉ function** có **chữ ký native tương thích FunctionDescriptor**.

Chia vấn đề thành ba lớp:

| Lớp | Cần xác minh | Nếu sai |
| --- | --- | --- |
| **Tên và export** | Hàm có symbol nào và có nằm trong dynamic export table không? | SymbolLookup không tìm thấy |
| **ABI và kiểu dữ liệu** | Đối số, return, memory layout, calling convention có đúng không? | Lỗi dữ liệu, crash, memory corruption |
| **Ownership và ngữ nghĩa** | Ai tạo/hủy object? Exception, thread, callback và resource được quản lý thế nào? | Leak, use-after-free, double-free, race |

Thành công ở lớp đầu (lookup tìm được địa chỉ) không chứng minh hai lớp sau đúng.

## 2. Name mangling: vì sao một hàm C++ không nhất thiết xuất ra cùng tên

C++ hỗ trợ overloading:

~~~cpp
int transform(int input);
double transform(double input);
~~~

Trong C++ source, compiler phân biệt hai hàm theo type của tham số. Ở cấp linker, nó thường **decorate/mangle** tên để biểu diễn đủ thông tin chọn đúng overload.

Chẳng hạn một toolchain dùng **Itanium C++ ABI** trên Linux có thể tạo các symbol minh họa như:

~~~text
_Z9transformi
_Z9transformd
~~~

Đây là ví dụ về mangled names cho hai kiểu tham số, **không phải hợp đồng chung cho mọi compiler**. Microsoft MSVC sử dụng một hệ **decorated names** khác, thường bắt đầu bằng dấu hỏi trên các hàm C++. Namespace, class, qualifiers, parameter types và calling convention có thể ảnh hưởng tên mã hóa.

Có thể thấy các tên khác nhau khi kiểm tra shared library:

~~~bash
nm -D --defined-only libsample.so
nm -D --defined-only libsample.so | c++filt
~~~

**nm** hiển thị symbols; **c++filt** giúp demangle tên thành mô tả dễ đọc. Nhưng việc demangle chỉ phục vụ chẩn đoán, **không biến ABI C++ thành C**.

### Vì sao không hard-code mangled names ở Java?

Giả sử Java cố tìm **_Z9transformi**. Một phiên bản compiler, namespace hoặc chữ ký khác có thể làm symbol đổi tên. Quan trọng hơn, **member method C++ còn có quy tắc receiver và calling convention**, nên tìm đúng tên không bảo đảm gọi đúng.

Một API public không nên buộc Java phụ thuộc vào implementation-specific mangled names trừ khi dự án cố tình khóa toàn bộ compiler/ABI và đã kiểm thử nghiêm ngặt.

## 3. extern "C" làm được gì và không làm được gì?

Trong C++:

~~~cpp
extern "C" int c_transform_i32(int input) {
    return input * 2;
}
~~~

**extern "C"** yêu cầu **C language linkage**, giúp public function dùng quy ước tên/liên kết phù hợp C trên toolchain đó. Trên Linux x64 thông thường exported symbol có thể được lookup bằng **c_transform_i32**, không cần biết tên đã được C++ compiler mangle.

### C linkage không hỗ trợ nạp chồng bằng cùng C tên

Hai khai báo sau **cố ý sai** và không phải mã để build:

~~~cpp
extern "C" int c_convert(int value);
extern "C" double c_convert(double value);
~~~

C name không chứa overload signature như C++ decorated name; không thể xuất hai function overload cùng một C linkage identifier rồi kỳ vọng dynamic lookup tự chọn. Phải tách:

~~~cpp
extern "C" int c_convert_i32(int value);
extern "C" double c_convert_f64(double value);
~~~

Tên C mới mô tả kiểu được expose. C++ implementation vẫn có thể dùng overload ở phía sau wrapper.

### extern "C" không tự giải quyết các vấn đề còn lại

- Không biến **std::string/std::vector/std::map** thành C structs có layout portable.
- Không xóa bỏ vptr, C++ object layout, multiple inheritance hoặc RTTI.
- Không khiến constructor/destructor thành ordinary C functions cho Java gọi.
- Không làm C++ exception tự biến thành Java exception.
- Không đảm bảo caller được dùng **free** với C++ object được cấp bằng **new**.
- Không tự làm các type như **long, size_t, pointer, wchar_t** có cùng size trên mọi ABI.
- Không tự export một Windows DLL function nếu thiếu **__declspec(dllexport)** hoặc export configuration.
- Không ngăn một số quy tắc symbol decoration do Windows x86 calling conventions gây ra.

**Kết luận phần này:** extern "C" giúp xây public symbol boundary, nhưng toàn bộ **function signature + layout + lifetime** vẫn phải được thiết kế như một hợp đồng C ABI hoàn chỉnh.

## 4. Class C++ không phải một record có thể gửi nguyên sang Java

Xét:

~~~cpp
class Calculator {
public:
    explicit Calculator(int seed);
    int add(int delta) const;
    double add(double delta) const;
    virtual ~Calculator();
private:
    int seed_;
};
~~~

Có ít nhất năm yếu tố đòi hỏi xem xét riêng.

**Constructor:** Không chỉ là một function C nhận seed và trả Calculator*. C++ compiler chịu trách nhiệm khởi tạo đầy đủ object, có thể gồm base classes và vptr. Một C façade nên cung cấp **calculator_create(int)**, dùng **new Calculator(seed)** bên trong và trả handle.

**Destructor:** Một virtual destructor hay destructor thường phải được gọi đúng native mechanism, có thể kích hoạt cleanup các thành viên. Java không nên tự free địa chỉ object rồi mong destructor chạy. C façade cần **calculator_destroy(handle)**.

**Member function và this:** **Calculator::add(int)** nhận receiver ngầm theo quy tắc C++ ABI. Không thể chỉ tự thêm một **ValueLayout.ADDRESS** vào FFM FunctionDescriptor và khẳng định toàn bộ compiler sẽ gọi giống một C function thường.

**Overloads:** Hai method **add(int)** và **add(double)** có thể có mangled names riêng. Phía C nên expose **calculator_add_i32** và **calculator_add_f64**.

**Virtual dispatch, vtable và inheritance:** Layout vptr/vtable, offset base subobject và pointer adjustment phụ thuộc toolchain. Java không nên đọc một raw vtable pointer để tự gọi hàm virtual nếu không có binding chuyên biệt theo đúng ABI.

Ví dụ C++ multiple inheritance:

~~~cpp
struct BaseA {
    virtual int valueA() const;
};

struct BaseB {
    virtual int valueB() const;
};

struct Derived : BaseA, BaseB {
    int state;
};
~~~

Đoạn này chỉ **minh họa class hierarchy**; virtual methods chưa có implementation. Pointer **Derived*** và **BaseB*** có thể phải điều chỉnh địa chỉ khi cast sang một base subobject. Đây là lý do một opaque handle và các wrapper methods có thể an toàn hơn nhiều so với tự tính class field offsets ở Java.

## 5. ABI C++ rộng hơn tên symbol

**ABI — Application Binary Interface** quy định cả cách máy gọi function và biểu diễn dữ liệu nhị phân: register/stack arguments, return values, alignment, exception unwinding, RTTI và binary object layout.

### GCC/Clang và MSVC

Trên nhiều nền tảng dùng GCC/Clang, C++ mangling/layout theo các quy ước liên quan **Itanium C++ ABI**; tên đó không có nghĩa chỉ sử dụng CPU Itanium. **MSVC** trên Windows có các quy tắc C++ ABI riêng. Một thư viện C++ build bởi compiler A không tự bảo đảm binary compatibility với mọi binary do compiler B build.

Ngay cả trong một compiler family, các yếu tố có thể ảnh hưởng ABI gồm:

- compiler version và target architecture;
- C++ standard library version, libstdc++/libc++/MSVC STL;
- **_GLIBCXX_USE_CXX11_ABI** trên một số GNU libstdc++ builds;
- packing/alignment flags, compiler attributes, exception/RTTI options;
- calling convention và export visibility;
- static vs dynamic C runtime, allocator boundaries;
- build configuration debug/release và cấu hình STL đặc thù.

**Không dùng cùng tên type để chứng minh cùng ABI.** Một function nhận **std::string** từ C++ phía này không nhất thiết hiểu object std::string được tạo bằng compiler/STL khác.

### C ABI cũng phụ thuộc nền tảng

C façade không biến ABI thành duy nhất cho mọi hệ. C **long** thường 8 byte trên LP64 Linux x64 và 4 byte trên LLP64 Windows x64. **size_t**, pointer width, alignment, struct packing, boolean/enum conventions cũng cần kiểm tra.

Khi đặt public C function, ưu tiên fixed-width types như **int32_t, uint64_t** cho thông tin số có độ rộng xác định, nhưng vẫn phải kiểm tra **double representation**, calling convention, alignment, pointer ownership và compiler/platform thực tế.

## 6. C++ exception, STL và allocator phải dừng ở biên native

### C++ exception boundary

C++ method có thể throw **std::overflow_error**, **std::bad_alloc** hoặc exception khác. FFM downcall **không cung cấp cơ chế tự động catch một C++ exception xuyên qua Java frame**. Để C++ exception thoát khỏi C-compatible function được FFM/JNI gọi là nguy hiểm: quá trình unwinding có thể không được hỗ trợ, dẫn đến terminate, crash hoặc lỗi không kiểm soát.

Giải pháp:

~~~text
C++ operation
     |
   try/catch (...), ở trong native wrapper
     |
     +-- success -> status = 0, ghi output
     |
     +-- failure -> status != 0, output không được tin
     |
Java kiểm tra status
     |
     +-- tạo Java exception phù hợp nếu cần
~~~

**Chụp exception chỉ là bước đầu**. Nếu một function mutate state rồi throw, wrapper trả status không tự động rollback mọi thay đổi; API cần document exception safety/transaction guarantees.

### STL và chuỗi

Đừng expose trực tiếp **std::string**, **std::vector** hoặc C++ references trong header mà Java FFM coi là C ABI. Cách dễ kiểm soát hơn:

- **const char* + length** cho chuỗi có encoding xác định (thường UTF-8);
- **const uint8_t* + size_t** cho binary data;
- **caller-owned buffer** để nhận data được copy về Java;
- **opaque handle** cho C++ collection/object phức tạp;
- **create/destroy** hoặc **buffer_release** rõ ràng cho allocation do native quản lý.

Một pointer **char*** có thể là NUL-terminated string hoặc raw buffer; phải có contract rõ ràng, đặc biệt khi có byte 0 ở giữa hoặc encoding khác UTF-8.

### new/delete không thay bằng malloc/free tùy tiện

Object được cấp bằng **new** phải được xử lý bằng native **delete** phù hợp để destructor chạy. Dùng C **free** cho địa chỉ object này là sai. Đặc biệt trên Windows, các DLL/CRT heaps khác nhau khiến việc giải phóng tài nguyên bằng một runtime khác càng nguy hiểm.

**Arena** của Java FFM quản lý những native MemorySegment được cấp thông qua Arena, **không tự quản lý lifetime của C++ object được library cấp bằng new**. Bởi vậy C-compatible wrapper phải có destroy function và Java bắt buộc gọi đúng lúc.

## 7. Thiết kế C façade: API chỉ chứa C-compatible types

Mục tiêu là **ẩn implementation C++** và expose một tập nhỏ C functions mà Java có thể liên kết chính xác.

Nguyên tắc:

1. Mỗi C++ overload có **C export name riêng**.
2. Dùng **extern "C"** trong header khi được compile bằng C++.
3. Có export visibility đúng trên Linux/macOS/Windows.
4. Giữ class implementation bên trong .cpp, public C header chỉ dùng **opaque struct pointers**.
5. Dùng **int32_t, double, pointers** với ABI đã xác minh.
6. C wrapper **catch exceptions**, trả status codes; không throw qua boundary.
7. Định nghĩa **output valid only when status==0**.
8. Dùng **create/destroy** đối xứng, nhất quán allocator.
9. Nói rõ caller có được share handle giữa threads hay không.
10. Dùng native compiler kiểm chứng exported symbol names và Java integration test.

API C lõi sẽ có dạng:

~~~c
typedef struct CounterHandle CounterHandle;
CounterHandle* counter_create(int32_t initial);
int counter_add_i32(const CounterHandle *h, int32_t delta, int32_t *out);
int counter_add_f64(const CounterHandle *h, double delta, double *out);
void counter_destroy(CounterHandle *h);
~~~

Đây là **fragment** rút gọn; code đầy đủ bên dưới có guard, macro export và noexcept. Java không cần biết CounterHandle có bao nhiêu field hoặc có vtable không; Java chỉ truyền handle lại cho C functions của cùng library.

## 8. Ví dụ end-to-end: hai C++ overloads, một C façade, Java FFM

**Nền tảng mục tiêu:** Linux x64, GCC/Clang hỗ trợ C++17, JDK22+ có FFM chuẩn. Ví dụ cố ý dùng phép cộng đơn giản để kiểm chứng đúng overloaded method và ABI.

### 8.1. File counter_c.h — giao diện C-compatible

~~~c
#ifndef COUNTER_C_H
#define COUNTER_C_H

#include <stdint.h>

/* Export macro theo nền tảng. */
#if defined(_WIN32)
    #if defined(COUNTER_BUILD)
        #define COUNTER_API __declspec(dllexport)
    #else
        #define COUNTER_API __declspec(dllimport)
    #endif
#else
    #define COUNTER_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
    #define COUNTER_NOEXCEPT noexcept
    extern "C" {
#else
    #define COUNTER_NOEXCEPT
#endif

/* Incomplete type: C/Java không được truy cập object internals. */
typedef struct CounterHandle CounterHandle;

enum {
    COUNTER_OK = 0,
    COUNTER_INVALID_ARG = 1,
    COUNTER_ARITHMETIC_ERROR = 2
};

/* Trả NULL khi tạo native object thất bại. */
COUNTER_API CounterHandle *counter_create(
        int32_t initial) COUNTER_NOEXCEPT;

/* Chỉ ghi *out khi return status == COUNTER_OK. */
COUNTER_API int counter_add_i32(
        const CounterHandle *handle,
        int32_t delta,
        int32_t *out) COUNTER_NOEXCEPT;

COUNTER_API int counter_add_f64(
        const CounterHandle *handle,
        double delta,
        double *out) COUNTER_NOEXCEPT;

/* Caller chỉ destroy một lần, sau khi không còn calls dùng handle. */
COUNTER_API void counter_destroy(
        CounterHandle *handle) COUNTER_NOEXCEPT;

#ifdef __cplusplus
}
#endif

#endif
~~~

**Điểm chính:**

- Khi compile dưới C++, **extern "C"** dùng C linkage và **COUNTER_NOEXCEPT** thành **noexcept**; khi compile dưới C, hai yếu tố C++ được loại bỏ.
- Trên Windows, **COUNTER_API** export symbol nếu build DLL với **COUNTER_BUILD**, còn code C import có thể dùng dllimport. Trên Linux/macOS GCC/Clang, default visibility giúp public functions được tìm bởi loader.
- **CounterHandle** là opaque/incomplete struct: người gọi không được cấp phát bằng **sizeof(CounterHandle)**, đọc fields hay tự delete.
- Status **0,1,2** là contract của ví dụ, không phải mã lỗi chuẩn của C++.
- **COUNTER_NOEXCEPT** trên declarations giúp ABI wrapper được thể hiện như một boundary không để exception thoát.

### 8.2. File counter.cpp — C++ class và C wrappers

~~~cpp
#include "counter_c.h"

#include <cstdint>
#include <limits>
#include <stdexcept>

class Counter {
public:
    explicit Counter(std::int32_t initial)
            : base_(initial) {}

    std::int32_t add(std::int32_t delta) const {
        const std::int64_t sum =
                static_cast<std::int64_t>(base_) +
                static_cast<std::int64_t>(delta);

        if (sum < std::numeric_limits<std::int32_t>::min() ||
            sum > std::numeric_limits<std::int32_t>::max()) {
            throw std::overflow_error("int32 overflow");
        }

        return static_cast<std::int32_t>(sum);
    }

    double add(double delta) const {
        return static_cast<double>(base_) + delta;
    }

private:
    std::int32_t base_;
};

struct CounterHandle {
    explicit CounterHandle(std::int32_t initial)
            : object(initial) {}

    Counter object;
};

extern "C" COUNTER_API CounterHandle *counter_create(
        int32_t initial) noexcept {
    try {
        return new CounterHandle(initial);
    } catch (...) {
        return nullptr;
    }
}

extern "C" COUNTER_API int counter_add_i32(
        const CounterHandle *handle,
        int32_t delta,
        int32_t *out) noexcept {
    if (handle == nullptr || out == nullptr) {
        return COUNTER_INVALID_ARG;
    }

    try {
        const std::int32_t answer = handle->object.add(delta);
        *out = answer;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_ARITHMETIC_ERROR;
    }
}

extern "C" COUNTER_API int counter_add_f64(
        const CounterHandle *handle,
        double delta,
        double *out) noexcept {
    if (handle == nullptr || out == nullptr) {
        return COUNTER_INVALID_ARG;
    }

    try {
        const double answer = handle->object.add(delta);
        *out = answer;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_ARITHMETIC_ERROR;
    }
}

extern "C" COUNTER_API void counter_destroy(
        CounterHandle *handle) noexcept {
    delete handle;
}
~~~

**Giải thích:**

- C++ có hai methods cùng tên **add** nhưng nhận **std::int32_t** và **double**; compiler chọn đúng overload trong từng wrapper.
- **counter_add_i32** và **counter_add_f64** là hai exported C names riêng biệt, không cần Java hiểu mangled method names.
- **int64_t** cộng hai int32 không overflow trong bước trung gian, sau đó kiểm tra miền int32. Khi base 10 cộng **Integer.MAX_VALUE**, C++ method throw **std::overflow_error**.
- C wrapper catch exception và trả **COUNTER_ARITHMETIC_ERROR = 2**. **out** chỉ được ghi sau khi tính toán thành công.
- **counter_create** cấp phát bằng **new**, **counter_destroy** giải phóng bằng **delete** cùng library.
- Không có STL type hoặc class definition trong public C header. Đây là một **shared library implementation**, không có main.

**Giới hạn:** catch-all được dùng để demo không cho exception vượt boundary, nhưng production API thường cần phân loại errors rõ hơn và không che giấu mọi nguyên nhân vào một status.

### 8.3. Build trên Linux

Tạo hai file **counter_c.h** và **counter.cpp** trong cùng thư mục, rồi chạy:

~~~bash
mkdir -p build

g++ -std=c++17 -Wall -Wextra -Wpedantic \
    -O2 -fPIC -shared -fvisibility=hidden \
    -DCOUNTER_BUILD counter.cpp \
    -o build/libcounter_c.so
~~~

**g++** (hoặc clang++ có cấu hình phù hợp) biên dịch và liên kết C++ runtime. **-fPIC -shared** tạo ELF shared library trên Linux; **-fvisibility=hidden** giới hạn các symbol không public, còn **COUNTER_API** chủ động export C façade. **-DCOUNTER_BUILD** chỉ tác động macro import/export ở nhánh Windows, không làm sai demo Linux.

Kiểm tra exported C symbols:

~~~bash
nm -D --defined-only build/libcounter_c.so \
  | grep 'counter_'
~~~

Mục tiêu là thấy bốn tên:

~~~text
counter_create
counter_add_i32
counter_add_f64
counter_destroy
~~~

Đây là **danh sách tên symbol cần thấy**, không phải stdout nguyên dạng của **nm**, vì nm còn in địa chỉ và loại symbol. Có thể dùng **nm -D ... | c++filt** để đọc C++ mangled names nhưng không lấy chúng làm public ABI Java.

### 8.4. File CppFacadeDemo.java — Java 22+ dùng FFM downcall

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class CppFacadeDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        Path library = Path.of("build", "libcounter_c.so")
                .toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // CounterHandle* counter_create(int32_t)
            MethodHandle create = linker.downcallHandle(
                    symbols.find("counter_create").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            // int counter_add_i32(CounterHandle*, int32_t, int32_t*)
            MethodHandle addI32 = linker.downcallHandle(
                    symbols.find("counter_add_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            // int counter_add_f64(CounterHandle*, double, double*)
            MethodHandle addF64 = linker.downcallHandle(
                    symbols.find("counter_add_f64").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.ADDRESS));

            // void counter_destroy(CounterHandle*)
            MethodHandle destroy = linker.downcallHandle(
                    symbols.find("counter_destroy").orElseThrow(),
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS));

            MemorySegment handle =
                    (MemorySegment) create.invokeExact(10);

            if (handle.equals(MemorySegment.NULL)) {
                throw new IllegalStateException(
                        "native constructor returned NULL");
            }

            System.out.println("created = true");

            try {
                MemorySegment intOut =
                        arena.allocate(ValueLayout.JAVA_INT);

                int intStatus =
                        (int) addI32.invokeExact(handle, 32, intOut);
                if (intStatus != 0) {
                    throw new IllegalStateException(
                            "int status=" + intStatus);
                }
                System.out.println("int result = " +
                        intOut.get(ValueLayout.JAVA_INT, 0));

                MemorySegment doubleOut =
                        arena.allocate(ValueLayout.JAVA_DOUBLE);

                int doubleStatus =
                        (int) addF64.invokeExact(handle, 2.5, doubleOut);
                if (doubleStatus != 0) {
                    throw new IllegalStateException(
                            "double status=" + doubleStatus);
                }
                System.out.println("double result = " +
                        doubleOut.get(ValueLayout.JAVA_DOUBLE, 0));

                // 10 + Integer.MAX_VALUE không vừa int32.
                int overflowStatus = (int) addI32.invokeExact(
                        handle, Integer.MAX_VALUE, intOut);
                System.out.println("overflow status = " +
                        overflowStatus);

            } finally {
                destroy.invokeExact(handle);
                System.out.println("destroyed = true");
            }
        }
    }
}
~~~

**Quan sát các mapping:**

| C façade signature | Java FFM descriptor |
| --- | --- |
| **CounterHandle* create(int32_t)** | Return **ADDRESS**, argument **JAVA_INT** |
| **int add_i32(CounterHandle*, int32_t, int32_t*)** | Return **JAVA_INT**, args **ADDRESS, JAVA_INT, ADDRESS** |
| **int add_f64(CounterHandle*, double, double*)** | Return **JAVA_INT**, args **ADDRESS, JAVA_DOUBLE, ADDRESS** |
| **void destroy(CounterHandle*)** | **ofVoid(ADDRESS)** |

**MemorySegment handle** từ **ValueLayout.ADDRESS** biểu diễn một pointer token, không có nghĩa Java được đọc các bytes của Counter object. Java chỉ truyền nó vào các function của same library.

**Output buffers:** **intOut** và **doubleOut** được Java Arena cấp trong đúng scope, đưa con trỏ sang native và đọc sau khi status 0. Với overflow, **intOut** không được coi là kết quả mới, bất kể trong nó còn giá trị từ lần gọi trước.

**finally** bảo đảm gọi destroy nếu đã tạo handle thành công, kể cả khi Java code ném exception sau đó. Library lookup và output segments còn sống trong Arena đến hết khối **try-with-resources**. Không gọi destroy hai lần.

### 8.5. Chạy Java

~~~bash
javac CppFacadeDemo.java

java --enable-native-access=ALL-UNNAMED CppFacadeDemo
~~~

Với JDK22+ FFM và Linux native library đã build đúng, stdout:

~~~text
created = true
int result = 42
double result = 12.5
overflow status = 2
destroyed = true
~~~

**Vì sao đúng?** C++ Counter nhận base=10. Overload int tính **10+32=42**. Overload double tính **10.0+2.5=12.5**. Gọi int overload với **Integer.MAX_VALUE** vượt giới hạn int32, C++ throw overflow_error, wrapper catch và trả status 2. Cuối cùng Java gọi **counter_destroy** đúng native lifetime.

**--enable-native-access=ALL-UNNAMED** cấp quyền restricted methods từ code classpath; không cần **--enable-preview** cho FFM đã final ở JDK22. Khi dùng named module phải cấu hình native access cho module thực.

**Không hứa về stderr:** Tùy JVM và cấu hình môi trường, diagnostics có thể có thông báo thêm; năm dòng trên là stdout do chương trình chủ động in.

## 9. Vì sao demo này không liên kết thẳng Counter::add?

Từ Java, có thể nhận ra rõ:

~~~text
Java biết:
  "counter_create"
  "counter_add_i32"
  "counter_add_f64"
  "counter_destroy"

Java không cần biết:
  C++ mangled names
  byte layout của Counter
  vtable / hidden this
  constructor/destructor ABI
  C++ exception implementation
  std::allocator
~~~

Hai C++ methods overload **add** được chọn ngay trong native source code bởi C++ compiler phù hợp. C façade bảo đảm một nhóm symbol và primitive signatures dễ diễn đạt bằng FFM.

Nếu trực tiếp tìm mangled name của **Counter::add(double)**, Java còn phải biết receiver pointer, cách compiler truyền member args, const/cv qualification, actual ABI và pointer adjustment khi có inheritance. Việc dùng một C façade giảm số giả định nguy hiểm về native toolchain.

## 10. Tương tác với JNI và jextract

### FFM (Java 22+)

**SymbolLookup.libraryLookup**, **Linker.downcallHandle**, **FunctionDescriptor** và **MemorySegment** cho phép gọi một C-compatible native function. Ưu điểm là không cần khai báo các Java native methods và viết JNI stubs nếu public interface đã là C ABI.

~~~text
Java FFM -> native C ABI façade -> C++ methods
~~~

FFM restricted native calls đòi native access đúng module/runtime policy. FFM không có cơ chế tự động hiểu C++ class object.

### JNI (khi cần JVM-specific integration hoặc JDK cũ)

JNI đi qua một Java native method và một function export đúng JNI naming/ABI:

~~~cpp
// Fragment C++: cần jni.h và Java class demo.Bridge tương ứng.
extern "C" JNIEXPORT jint JNICALL
Java_demo_Bridge_add(JNIEnv *env,
                     jclass cls,
                     jint left,
                     jint right) {
    (void)env;
    (void)cls;
    return left + right;
}
~~~

JNIEXPORT/JNICALL mô tả export/calling convention theo JNI, còn **extern "C"** tránh C++ mangling ngoài quy tắc tên JNI. Fragment không độc lập: cần Java native declaration, build thư viện và System.loadLibrary. Khi bridge thực sự gọi C++ object, vẫn cần giải quyết constructor, exception, ownership và ABI như với FFM.

### jextract (sinh bindings cho C header)

jextract có thể sinh Java bindings từ **counter_c.h** vì đây là C-compatible header, không expose C++ templates hoặc classes. Cần chọn jextract version phù hợp FFM API và JDK target, kiểm tra generated methods, compile/run trên native ABI đích. Không cho jextract một C++ STL-heavy header rồi mặc định mọi overload/vtable đều được sinh thành Java methods.

**Có thể kết hợp:** C++ implementation + C façade + jextract-generated Java FFM bindings. Sự kết hợp này thuận tiện nếu interface có nhiều functions/structs nhưng vẫn muốn tránh viết tay nhiều FunctionDescriptor.

## 11. Đường nạp thư viện và symbol checks

### Linux

~~~bash
nm -D --defined-only build/libcounter_c.so
nm -D --defined-only build/libcounter_c.so | c++filt
readelf -d build/libcounter_c.so
ldd build/libcounter_c.so
~~~

- **nm -D** xem dynamic exported symbols.
- **c++filt** giúp đọc mangled C++ names khi chẩn đoán.
- **readelf -d** cho thấy dynamic dependencies và loader metadata.
- **ldd** giúp kiểm tra shared library dependencies trên binary tin cậy.

**Symbol lookup thành công ≠ ABI đúng.** Nếu gọi sai FunctionDescriptor, pointer lifetime hoặc calling convention, app vẫn có thể crash sau lookup.

### Windows

Có thể dùng MSVC Developer Command Prompt (minh họa, không phải lệnh demo Linux):

~~~bat
cl /nologo /std:c++17 /EHsc /LD /DCOUNTER_BUILD ^
  counter.cpp /Fe:counter_c.dll

dumpbin /exports counter_c.dll
~~~

Windows cần macro **__declspec(dllexport)** hoặc export declaration phù hợp, đúng MSVC toolset và CRT setup. Trên một số Windows x86 calling conventions, symbol C vẫn có name decoration, nên cần kiểm tra tên thực trong DLL export table. Trên Windows x64 common C-style exports thường ít bị decorate hơn, nhưng không được suy luận chỉ từ tên file.

### macOS

Thông thường dùng **.dylib** và dyld library loading. Công cụ nm có thể biểu diễn C symbols với leading underscore, không có nghĩa Java luôn phải tìm với underscore: hãy xác minh symbol lookup trên runtime thật. Không chuyển nguyên .so Linux hoặc C++ ABI assumptions sang macOS một cách tự động.

## 12. Thread safety, callback và ownership

C façade không làm class C++ thread-safe. Khi Java giữ một **CounterHandle***, cần quy định:

- Một handle có cho phép nhiều Java threads gọi methods đồng thời?
- C++ methods có mutate fields hay gọi code bên ngoài?
- Có internal locks và reentrancy policy không?
- Có được destroy trong lúc một thread khác còn downcall sử dụng handle không?
- Một callback native→Java được đăng ký bao lâu, thread nào gọi và khi nào unregister?
- Có native thread-affinity như COM/GUI/event loop không?

Demo Counter chỉ đọc base_ sau construction và không sửa nội trạng trong add. Nhưng **destroy vẫn phải chờ mọi in-flight operations kết thúc**. Java **finally** chỉ quản lý phạm vi của thread gọi, không tự đồng bộ toàn bộ hệ thống.

**Lưu ý về memory:** Một returned pointer có thể được biểu diễn bằng Java **MemorySegment** mà Java không tự biết object đã bị delete. Không dereference hoặc truyền handle sau destroy. Với Java wrapper production, có thể đóng gói handle trong một **AutoCloseable** quản lý trạng thái closed, nhưng phải tránh double close và concurrent use-after-close.

**Callback/upcall:** Nếu C++ lưu function pointer được tạo qua Java FFM **Linker.upcallStub**, arena chứa stub phải còn sống đến khi native code unregister. Java exception/callback policy cũng phải có ranh giới tương thích; không cho ngoại lệ xuyên native frames tùy tiện.

## 13. String, buffer và opaque data design

Một header C-facing cho native library có thể trông như:

~~~c
/* Fragment: các tên dùng minh họa, chưa có implementation. */
typedef struct QueryHandle QueryHandle;

int query_create(QueryHandle **out);
int query_add_filter(QueryHandle *handle,
                     const char *key,
                     const char *value);
int query_copy_result(QueryHandle *handle,
                      char *buffer,
                      size_t capacity,
                      size_t *written);
void query_destroy(QueryHandle *handle);
~~~

Cần xác định:

1. **Encoding**: key/value là UTF-8 hay encoding khác?
2. **Termination**: NUL-terminated hay pointer+length? Dữ liệu binary có thể có NUL.
3. **Ownership**: query_add_filter copy strings hay giữ pointers sau khi return?
4. **Buffer capacity**: nếu quá nhỏ, trả mã gì và written là bytes đã ghi hay bytes cần?
5. **Threading**: shared handle có được dùng đồng thời không?
6. **Allocator**: nếu library cấp buffer, ai gọi release và trong runtime nào?
7. **size_t**: Java mapping phải đúng native ABI (x86 vs x64/Windows vs Linux).
8. **Versioning**: thay signature phải nâng API version, không âm thầm giữ tên cũ.

**Đừng để Java nhận std::string by value qua FFM** chỉ vì object đó có dữ liệu UTF-8 bên trong. Layout/allocator của STL không là một giao thức C ABI lâu dài.

## 14. C API versioning và tương thích binary

Một C façade ổn định dễ quản lý phiên bản hơn direct C++ class ABI, nhưng vẫn phải tránh thay đổi chữ ký âm thầm.

Ví dụ:

~~~c
/* Fragment, chưa có implementations. */
int counter_v1_get(const CounterHandle *h, int32_t *result);
int counter_v2_get(const CounterHandle *h,
                   int32_t *result,
                   uint32_t flags);
~~~

Nếu chương trình Java cũ đã liên kết **counter_v1_get** với hai arguments, nhưng native thư viện mới đổi signature thực dưới cùng tên thành ba arguments, FunctionDescriptor cũ có thể gây undefined native behavior. Nên giữ symbol cũ với contract cũ hoặc thay bằng tên versioned và migration rõ ràng.

**C ABI vẫn phụ thuộc platform**: C int/long sizes, pointer width, calling convention, struct packing, endian và library dependencies cần kiểm tra trong mỗi native build. Façade không phải lời hứa một DLL của Windows có thể nạp vào JVM Linux.

## 15. Bảng chẩn đoán lỗi

| Triệu chứng | Khả năng chính | Hướng xác minh |
| --- | --- | --- |
| **SymbolLookup.find** không thấy hàm | C++ mangled name, visibility hidden, chưa export | nm/dumpbin, extern "C", export macros |
| **libcounter_c.so** không load được | Sai path/architecture/dependency | Path tuyệt đối, ldd, target OS/CPU |
| **WrongMethodTypeException** | invokeExact carrier/argument count sai | Đối chiếu FunctionDescriptor và MethodHandle.type |
| **IllegalCallerException** khi downcall | Restricted FFM native access chưa cấp | --enable-native-access đúng module/classpath |
| Crash ngay ở invoke | C ABI/FunctionDescriptor/calling convention sai | Kiểm tra native signature, ABI, pointer |
| Result sai dù gọi không crash | C type sizes, alignment, endian hoặc prototype mismatch | C header/sizeof/offsetof/toolchain |
| Double-free/use-after-free | Ownership và destroy contract không đúng | Java state management, native resource tests |
| C++ exception làm terminate | Wrapper không catch exception trước FFM | Catch trong native, trả status |
| Linux chạy nhưng Windows lỗi | MSVC ABI, DLL export, LLP64, CRT | Build/test theo platform, dumpbin |
| Link C++ object files không tìm STL runtime | Dùng C linker thay C++ linker | g++/clang++, native runtime dependencies |
| JNIEXPORT function không được Java tìm | JNI name/signature/extern C sai | javap, nm, header generated, JNICALL |
| Java memory Arena đóng trước native dùng pointer xong | Lifetime chưa đúng | Giữ Arena sống, xác nhận callback/store semantics |

**Quan trọng:** đừng xử lý lỗi bằng cách đoán mangled symbol mới rồi bỏ qua chữ ký native, runtime và ownership. Nếu cần thử, tạo một C façade tối thiểu rồi chứng minh end-to-end trước.

## 16. Checklist trước khi liên kết thư viện C++

**Thiết kế native boundary**

- [ ] Public symbols là C-compatible functions, không dựa vào mangled C++ method names.
- [ ] Mỗi overload có C export name riêng.
- [ ] Header dùng **extern "C"** cho C++ compilation và export visibility thích hợp.
- [ ] Opaque handles thay cho C++ class layout public.
- [ ] Có **create/destroy**, caller biết sở hữu resource và có one-destroy policy.
- [ ] C++ exceptions được catch và chuyển thành status/error protocol.
- [ ] Dữ liệu scalar, pointer, buffer, encoding và byte lengths có contract rõ ràng.
- [ ] Không expose STL types, templates hoặc C++ references vào C ABI.
- [ ] Threading/reentrancy/async callbacks/lifetime có tài liệu.
- [ ] Compiler/OS/CPU/C++ runtime tương thích với native binary cần wrap.

**Liên kết Java**

- [ ] Java JDK/FFM hoặc JNI version đúng.
- [ ] Native library thực được load và symbols đã kiểm tra.
- [ ] FunctionDescriptor đúng toàn bộ input/output C types.
- [ ] Java không dereference opaque pointer trực tiếp.
- [ ] Kiểm tra native status trước khi đọc out parameters.
- [ ] finally/AutoCloseable và library-specific destroy được gọi phù hợp.
- [ ] Không dùng handle sau destroy hoặc sau library unload.
- [ ] Có native integration test cho success, invalid arguments, exceptions và concurrency.
- [ ] Với jextract, input là C-compatible header, source được sinh tương thích JDK mục tiêu.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao Java không nên dùng **SymbolLookup.find("add")** để gọi trực tiếp Counter::add(int)?

**Đáp án:** C++ member function có mangled name và implicit receiver **this** với calling convention của toolchain. Symbol "add" không mô tả đầy đủ các yếu tố đó; nên dùng public C façade.

**Câu 2.** Dùng **extern "C"** có thể export cùng tên **convert** cho cả overload int và double không?

**Đáp án:** Không. C linkage không cung cấp overload symbol names. Dùng **convert_i32** và **convert_f64** hoặc tên C độc lập khác.

**Câu 3.** Vì sao **std::string** không phải kiểu truyền trực tiếp portable cho Java FFM?

**Đáp án:** C++ object layout, allocator, ABI và lifetime phụ thuộc runtime/compiler. Chuyển thành C-compatible encoding + buffer/length hoặc opaque handle.

**Câu 4.** Khi native Counter được tạo bằng new, Java có thể gọi free(handle) không?

**Đáp án:** Không. Java cần gọi **counter_destroy(handle)** do cùng native library cung cấp, để delete và destructor đúng cách.

**Câu 5.** C++ throw exception trong add, Java FFM có tự biến nó thành Java exception không?

**Đáp án:** Không. Native wrapper catch exceptions bên trong C++ và trả status; Java dựa trên status xử lý lỗi.

**Câu 6.** Nếu exported symbol có tên đúng, đã chắc chắn Java downcall an toàn chưa?

**Đáp án:** Chưa. FunctionDescriptor, ABI, calling convention, pointer lifetime và ownership vẫn cần kiểm tra.

**Câu 7.** Cùng JDK22+, thư viện C++ do MSVC build có tự tương thích object layout với một thư viện GCC build không?

**Đáp án:** Không. JDK không quyết định C++ ABI của các native toolchains.

**Câu 8.** Vì sao Façade vẫn cần thread contract, dù tất cả functions được extern "C"?

**Đáp án:** C linkage chỉ liên quan tên và calling convention, không tự làm C++ object thread-safe; destroy trong lúc downcall khác dùng handle vẫn nguy hiểm.

**Câu 9.** Điều gì xảy ra nếu function C trả status 2 và Java vẫn đọc intOut?

**Đáp án:** intOut không phải kết quả mới hợp lệ; nó có thể giữ value cũ. Chỉ đọc dữ liệu khi contract báo success.

**Câu 10.** jextract có trực tiếp phân tích C++ class và virtual methods thành Java API chuẩn cho mọi compiler không?

**Đáp án:** Không. jextract chủ yếu sinh FFM bindings từ C headers; cần C-compatible façade hoặc công cụ chuyên biệt được xác minh ABI.

### Bài tập thực hành

**A.** Bổ sung overload C++ **add(int64_t)** và C façade **counter_add_i64**, dùng ValueLayout phù hợp int64_t; giải thích tránh overflow trong phép cộng.

**B.** Bỏ extern "C" ở một export trong bản sandbox, build lại library rồi dùng nm so sánh symbol. Ghi lại vì sao FFM lookup theo tên C bị thất bại.

**C.** Thử truyền **MemorySegment.NULL** làm out parameter của **counter_add_i32** và kiểm tra status 1, không được dereference pointer null. Không làm trên thư viện thiếu validation.

**D.** Viết Java wrapper **AutoCloseable** quanh CounterHandle; chống double close, cấm dùng handle sau close và quản lý synchronization nếu nhiều threads có thể gọi đồng thời.

**E.** Thiết kế API nhận UTF-8 string: cho Java cấp buffer pointer+length; đảm bảo native không giữ pointer sau khi Java Arena đóng.

## Tài liệu tham khảo chính thức

- Microsoft Learn — **Name Decoration**: https://learn.microsoft.com/en-us/cpp/error-messages/tool-errors/name-decoration
- Microsoft Learn — **Decorated names**: https://learn.microsoft.com/en-us/cpp/build/reference/decorated-names
- Microsoft Learn — **Exporting C++ Functions for C-Language Executables**: https://learn.microsoft.com/en-us/cpp/build/exporting-cpp-functions-for-use-in-c-language-executables
- GCC libstdc++ — **ABI and binary compatibility**: https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html
- Itanium C++ ABI Specification: https://itanium-cxx-abi.github.io/cxx-abi/abi.html
- Java SE 22 — **Foreign Function & Memory API**: https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html
- Java SE 22 — **Call a C Library Function via FFM**: https://docs.oracle.com/en/java/javase/22/core/calling-c-library-function-foreign-function-and-memory-api.html
- Java SE 22 — **Linker**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Java SE 22 — **SymbolLookup**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- OpenJDK — **JEP 454: FFM API final**: https://openjdk.org/jeps/454
- OpenJDK — **jextract repository**: https://github.com/openjdk/jextract

**Tổng kết:** Khi Java muốn dùng C++, **lớp, nạp chồng và ABI C++ phải được xem xét trước khi liên kết**, bởi symbol name chỉ là phần nổi của hợp đồng nhị phân. Một **C façade có extern "C"**, explicit C names cho overloads, **opaque handles**, **status/out parameters**, exception boundary và **create/destroy** cho phép Java FFM/JNI gọi C++ theo interface đơn giản hơn, nhưng vẫn phải kiểm chứng native ABI, calling convention, loader, lifetime và thread safety.
