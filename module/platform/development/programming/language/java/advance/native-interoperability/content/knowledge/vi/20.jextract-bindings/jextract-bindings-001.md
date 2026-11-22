# Vai trò jextract trong sinh mã Java từ header thư viện C

## 1. Vấn đề: từ API C sang Java mà không tự viết mọi binding

Giả sử bạn có một thư viện C đã tồn tại:

```c
/* minimath.h */
int add_numbers(int a, int b);
int scale(int value, int factor);
```

Từ Java, bạn muốn gọi hai hàm ấy nhưng không muốn tự tay viết hàng loạt mã tra cứu symbol, `FunctionDescriptor`, `Linker.downcallHandle`, `MethodHandle.invokeExact` và mã xử lý layout khi API trở nên lớn. **jextract** giải quyết bài toán tạo mã liên kết (binding generation) này.

**jextract là công cụ phân tích header C (`.h`) và sinh mã nguồn Java dùng Foreign Function & Memory API (FFM API) để tương tác với native library.** Nó đọc *khai báo* giao diện C, mô hình hóa hàm/kiểu/constant/struct và tạo Java APIs tương ứng. Người dùng Java sau đó có thể gọi wrapper có tên gần với tên hàm C, trong khi mã sinh ra thực hiện việc liên kết FFM ở bên dưới.

Sơ đồ pipeline:

```text
           C HEADER                 C IMPLEMENTATION
         minimath.h                   minimath.c
       Khai báo hàm, struct,         Định nghĩa mã máy
       typedef, macro...             cho các hàm C
             │                            │
             ▼                            ▼
        jextract + clang         C compiler + linker
             │                            │
             ▼                            ▼
    GENERATED JAVA SOURCES          libminimath.so
    demo.bindings.NativeMath             │
    (wrappers, layouts,                  │
     function descriptors,               │
     MethodHandles...)                   │
             │                            │
             ▼                            │
        javac -> .class                  │
             │                            │
             └───────────┬────────────────┘
                         ▼
                  JAVA APPLICATION
              NativeMath.add_numbers(...)
                         │
                         ▼
              FFM downcall -> native C
```

**Điểm cần nhớ:** jextract không chuyển C implementation thành Java, không dịch một file `.c` thành bytecode, không biên dịch `.so`, và không tự cấp phát/giải phóng mọi native pointer. Nó **tạo cầu nối Java từ C declarations**. Native binary thật vẫn cần được biên dịch, phân phối và nạp đúng cách.

### 1.1. FFM API và jextract khác vai trò

| Thành phần | Nó làm gì? | Ai cung cấp? |
| --- | --- | --- |
| `java.lang.foreign` | API Java chuẩn để quản lý foreign memory và gọi native functions | JDK **22+** (final từ JEP 454) |
| `Linker` / `FunctionDescriptor` / `MemoryLayout` | Các khối xây dựng low-level để tạo downcall/upcall, mô tả ABI | FFM trong JDK |
| `jextract` | Phân tích C headers bằng Clang và **sinh Java bindings** dựa trên FFM | Công cụ độc lập thuộc dự án OpenJDK jextract |
| C compiler | Biên dịch implementation C thành native shared library | GCC, Clang, MSVC... |
| Native shared library | Chứa symbol/hàm máy thật để chạy | Sản phẩm của C compiler/linker |
| Generated Java binding | Wrapper Java dùng FFM để tìm/call native symbol và truy cập layouts | Đầu ra của jextract |

**jextract không phải lệnh `javac` của JDK** và không mặc định nằm trong mọi bản cài JDK. Cần tải một bản jextract tương thích với JDK sẽ dùng, hoặc tự build công cụ theo hướng dẫn dự án. Đối với bài tập này, ưu tiên **JDK 22 trở lên** vì `java.lang.foreign` đã hoàn thiện; bản jextract được chọn cũng phải target API của JDK chạy. Nếu dùng bản phát hành mới hơn, kiểm tra version thực tế trước khi copy lệnh hoặc source generated.

## 2. jextract nhận đầu vào gì và tạo ra những gì?

Một lần chạy jextract thường nhận:

- **Header chính:** file `.h` chứa interface công khai của thư viện.
- **Include directories:** đường dẫn để Clang tìm những header được `#include` từ header chính.
- **Macro definitions và compiler flags:** điều kiện tiền xử lý như `-D FEATURE_X=1`, ABI target và các include cần thiết.
- **Đích sinh code:** thư mục đầu ra `--output` và Java package `--target-package`.
- **Tên thư viện:** tham số `--library` (khi muốn generated code tự nạp thư viện).
- **Tùy chọn chọn lọc symbol:** chỉ sinh bindings cho những declarations cần dùng khi thư viện quá lớn.

Một công thức điển hình được công bố trong OpenJDK jextract Guide:

```bash
jextract \
  --include-dir /path/to/native/include \
  --output generated \
  --target-package com.example.nativeapi \
  --library mylib \
  /path/to/native/include/mylib.h
```

Các đường dẫn `/path/to/...` trong đây là **ký hiệu mô tả**, không phải lệnh copy chạy ngay khi không có thư viện. Lệnh tạo Java files theo package, ví dụ `generated/com/example/nativeapi/mylib_h.java` và các classes riêng cho structs/unions/function pointer types nếu header có.

### 2.1. Các tầng của dữ liệu sinh

| Khai báo trong C header | Java binding thường được sinh | Ý nghĩa |
| --- | --- | --- |
| `int add(int,int);` | Một static Java wrapper `add(int,int)`, cùng accessors `add$address()`, `add$descriptor()`, `add$handle()` | Gọi native C và kiểm tra metadata |
| `struct Point { int x; int y; };` | Class `Point`, layout/offset/field getters/setters/allocate helpers | Truy cập và cấp phát C struct |
| `typedef int MyInt;` | Layout/typedef metadata tương ứng | Giữ mapping kiểu C trên ABI |
| `enum Mode { A=1, B=2 };` | Constant accessors; không nhất thiết là Java `enum` | Tương ứng symbolic constants của C |
| `#define MAX_SIZE 256` | Accessor cho macro constant mà công cụ hỗ trợ | Tránh chép tay một số hằng |
| `typedef int (*callback_t)(int,int);` | Lớp hỗ trợ function pointer/upcall stub | Java callback được native gọi |
| `extern int count;` | Global-variable layout/segment/getter/setter | Đọc/ghi C global được export |
| `union Packet { ... };` | Class/layout tương ứng union | Tính offset và quyền diễn giải field |
| `int f(int count,...);` | Variadic invoker API theo kiểu tham số được chuyên biệt hóa | Hỗ trợ một phần variadic C ABI |

**Tùy version jextract và target C header**, kiểu Java cụ thể, tên lớp, overloads và số lượng file sinh có thể thay đổi. Khi viết code production, **đọc files thực tế vừa sinh** và kiểm tra `jextract --version`, không giả định mọi phiên bản tạo source giống hệt ví dụ minh họa.

### 2.2. jextract không cần nội dung body của C function

Ví dụ chỉ với header:

```c
/* math_api.h */
int add(int a, int b);
```

jextract có thể dựng Java wrapper dựa vào declaration. Nhưng nếu không có native library **thật sự export symbol `add`**, đến lúc Java wrapper liên kết/gọi symbol sẽ thất bại. Điều này tương tự việc khai báo `extern` trong C: header mô tả API, không cấp implementation.

Vì vậy kiểm thử binding luôn phải có cả **header, native binary và runtime loading**. Chỉ thấy các file `.java` sinh ra chưa chứng minh ứng dụng gọi native thành công.

## 3. Cách jextract giảm lượng mã FFM phải viết tay

Không có jextract, một lời gọi C thường cần logic FFM thủ công như sau:

```java
// Fragment JDK 22+, giả định linker, lookup và arena
// đã được chuẩn bị và giữ sống đúng thời hạn.
MemorySegment fn = lookup.find("add_numbers")
        .orElseThrow();

FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

MethodHandle handle = linker.downcallHandle(fn, descriptor);

int result = (int) handle.invokeExact(20, 22);
```

Đây là **fragment**, chưa phải chương trình Java độc lập. Với hàng trăm native functions, tự duy trì những mô tả này rất dễ sai: thứ tự arguments, `long` của ABI, signature, struct padding hoặc carrier của con trỏ.

jextract tự sinh wrapper có hình thức gần như:

```java
// ĐOẠN MINH HỌA ý tưởng generated binding,
// không phải toàn bộ file jextract xuất ra.
public static int add_numbers(int a, int b) {
    // ... gọi MethodHandle đã tạo từ C symbol và descriptor...
    return /* kết quả native */;
}
```

Bản pseudo-fragment trên cố ý không viết thân MethodHandle cụ thể: generated implementation **phụ thuộc phiên bản tool**. Điều ổn định về mặt khái niệm là Java client gọi `add_numbers(20,22)` trong khi code được sinh lo chuyện `SymbolLookup`/`downcallHandle` và mapping FFM.

Trong một jextract release có hỗ trợ metadata accessors, bạn còn có thể tra cứu:

```java
// Fragment: các hàm tương ứng với symbol add_numbers.
MemorySegment address = NativeMath.add_numbers$address();
FunctionDescriptor fd = NativeMath.add_numbers$descriptor();
MethodHandle mh = NativeMath.add_numbers$handle();

System.out.println(mh.type()); // Trên ABI int32 phù hợp: (int,int)int
```

Các accessors metadata này được mô tả trong OpenJDK jextract Guide. Chúng giúp **kiểm chứng binding đã sinh**, nhưng không thay thế việc đối chiếu C header và binary ABI thật.

## 4. Ví dụ hoàn chỉnh: từ C header tới lệnh gọi Java

Ví dụ này chạy theo pipeline dễ quan sát nhất: tạo thư viện C nhỏ, sinh binding bằng jextract, biên dịch generated Java sources cùng ứng dụng Java và gọi hàm.

**Giả định môi trường:** Linux x86-64, GCC/Clang hỗ trợ C11, một **JDK 22+** và bản **jextract tương thích chính JDK đó** đã tải và thêm vào `PATH`. Mã C dùng `int`; trên Linux x86-64 thông dụng `int` là signed 32-bit nên sinh ra Java carrier `int`. Đối với OS/ABI khác, phải kiểm tra lại.

### 4.1. Cấu trúc thư mục

```text
jextract-minimath/
├── native/
│   ├── minimath.h
│   └── minimath.c
├── src/
│   └── MiniMathDemo.java
├── generated/                  # jextract tạo Java sources ở đây
└── build/
    ├── classes/                # javac tạo .class
    └── libminimath.so          # cc tạo native library
```

Không dùng `javac -h` trong pipeline này. `javac -h` dành cho JNI header generation ở hướng **Java native declaration → C header**; còn jextract đi theo hướng **C header → Java FFM bindings**.

### 4.2. Header C: `native/minimath.h`

```c
#ifndef MINIMATH_H
#define MINIMATH_H

#ifdef __cplusplus
extern "C" {
#endif

int add_numbers(int a, int b);
int scale(int value, int factor);

#ifdef __cplusplus
}
#endif

#endif
```

Hai hàm nằm trong public C API. Include guard tránh khai báo lặp. Phần `extern "C"` chỉ có hiệu lực khi header được dùng bởi C++ compiler, nhằm cung cấp C linkage; bản thân file source ví dụ là C. Dấu ngoặc `extern "C"` không biến jextract thành C++ parser tổng quát.

### 4.3. Implementation C: `native/minimath.c`

```c
#include "minimath.h"

int add_numbers(int a, int b) {
    return a + b;
}

int scale(int value, int factor) {
    return value * factor;
}
```

Không cần JNI-style symbol như `Java_demo_NativeMethod`, cũng không có tham số `JNIEnv *`. Đó là những **C functions bình thường**. Chúng sẽ được gọi trực tiếp bằng FFM downcall thông qua wrapper Java do jextract sinh ra.

Để giữ ví dụ deterministic và tránh undefined behavior của signed integer overflow trong C, Java sẽ chỉ truyền những số nhỏ. Bài này không dùng demo để khẳng định phép nhân C luôn an toàn cho mọi `int`.

### 4.4. Biên dịch shared library C trên Linux

Đứng ở gốc thư mục `jextract-minimath`:

```bash
mkdir -p build/classes generated

cc -std=c11 -Wall -Wextra -O2 -fPIC -shared \
  native/minimath.c -o build/libminimath.so
```

`-fPIC -shared` tạo một shared object Linux. Output `build/libminimath.so` chứa các exported symbols `add_numbers` và `scale`. Nếu compiler gắn visibility ẩn hoặc C++ name mangling vào symbols, jextract vẫn có thể sinh code từ header nhưng Java sẽ không resolve được tên symbol mong đợi.

Có thể kiểm tra symbol trên Linux:

```bash
nm -D --defined-only build/libminimath.so
```

Output thực tế còn chứa địa chỉ/metadata nên không cam kết exact stdout của `nm`. Điều cần xác nhận là **có hai tên `add_numbers` và `scale`** trong exported dynamic symbols.

### 4.5. Kiểm tra công cụ và sinh Java bindings

Chạy:

```bash
java -version
jextract --version
```

Lệnh `jextract --version` cho biết bản công cụ, thông tin target JDK và Clang theo release. Nếu binary jextract được xây cho JDK khác hoặc missing native dependencies, **dừng và chọn toolchain phù hợp** trước khi phát sinh mã.

Sinh binding:

```bash
jextract \
  --output generated \
  --target-package demo.bindings \
  --header-class-name NativeMath \
  --library minimath \
  native/minimath.h
```

Ý nghĩa:

- `native/minimath.h`: header chính jextract cần parse.
- `--output generated`: đặt generated sources dưới thư mục `generated`.
- `--target-package demo.bindings`: package của các lớp được sinh.
- `--header-class-name NativeMath`: đặt tên class gốc là `NativeMath` thay vì để jextract suy tên từ `minimath.h`.
- `--library minimath`: cho generated binding biết cần load native library tên logic `minimath`. Trên Linux, tên đó ánh xạ thành `libminimath.so` qua cơ chế library loader.

Trong thư mục output, ví dụ thường có:

```text
generated/
└── demo/
    └── bindings/
        └── NativeMath.java
        (các helper/generated files khác nếu tool cần)
```

Tên class gốc được chốt bằng `--header-class-name`; **cấu trúc files chi tiết phụ thuộc bản jextract**. Nếu công cụ không nhận tùy chọn, xem `jextract --help` của chính bản cài và điều chỉnh lệnh theo release, không cố dùng output được tạo bởi một release khác.

### 4.6. Java client: `src/MiniMathDemo.java`

```java
import static demo.bindings.NativeMath.add_numbers;
import static demo.bindings.NativeMath.add_numbers$handle;
import static demo.bindings.NativeMath.scale;

public final class MiniMathDemo {
    private MiniMathDemo() {
    }

    public static void main(String[] args) {
        int sum = add_numbers(20, 22);
        int multiplied = scale(7, 6);

        System.out.println("sum: " + sum);
        System.out.println("scaled: " + multiplied);
        System.out.println(
                "add handle type: " + add_numbers$handle().type());
    }
}
```

**Điểm quan trọng:** mã Java client **không tự viết `FunctionDescriptor` hay `Linker.downcallHandle`**. Generated binding xử lý chúng từ C declarations. Chúng ta chỉ import static wrappers và một metadata accessor để chứng minh signature FFM.

Theo OpenJDK jextract Guide, một hàm C `int add_numbers(int,int)` trên ABI 32-bit `int` sẽ có Java wrapper kiểu:

```text
int add_numbers(int,int)
```

và `add_numbers$handle().type()` là:

```text
(int,int)int
```

Nó thể hiện **MethodType của downcall bound handle**, không phải tên C mang theo Java signature bằng cách thần kỳ. Việc mapping C type vẫn được jextract xác định theo compiler/ABI khi parse header.

### 4.7. Biên dịch Java và chạy

Từ thư mục gốc, trên shell Linux có `find`:

```bash
javac -d build/classes \
  $(find generated -type f -name '*.java') \
  src/MiniMathDemo.java
```

Dùng generated Java source files **của cùng lần jextract**, không tự tạo một file stub `NativeMath.java` để giả vờ có binding.

Mặc định `--library minimath` dùng native OS library lookup (không phải mặc nhiên theo `java.library.path`). Cấu hình `LD_LIBRARY_PATH` **trước khi khởi động JVM** để dynamic linker tìm được `build/libminimath.so`:

```bash
LD_LIBRARY_PATH="$PWD/build" \
  java --enable-native-access=ALL-UNNAMED \
       -cp build/classes MiniMathDemo
```

`--enable-native-access=ALL-UNNAMED` cấp quyền dùng restricted FFM operations cho ứng dụng đang ở unnamed module/classpath, phù hợp demo. Trong hệ thống module hóa, chỉ cấp cho named modules cần thiết. Đừng bỏ qua cảnh báo/ngoại lệ native access nếu runtime thực tế yêu cầu thêm cấu hình.

**Stdout dự kiến trên toolchain tương thích đã nêu:**

```text
sum: 42
scaled: 42
add handle type: (int,int)int
```

Nếu dynamic loader không tìm thấy thư viện, JVM sẽ báo lỗi ở bước load/symbol lookup, **không** in ba dòng thành công này. Nếu generated code/FFM API không tương thích với JDK, lỗi có thể xảy ra ngay trong biên dịch Java; cần kiểm tra chính xác version và generated source.

### 4.8. Vì sao ví dụ là một demo C→Java, không phải JNI?

| So sánh | jextract + FFM | JNI truyền thống |
| --- | --- | --- |
| Hướng khai báo | **C header → generated Java binding** | Thường **Java `native` declaration → native C function** |
| Java gọi | Wrapper `add_numbers(20,22)` do tool sinh | Java `native int addNumbers(...)` |
| C implementation | `int add_numbers(int,int)` | Hàm JNI như `Java_demo_X_addNumbers(JNIEnv*,jclass,...)` |
| Công cụ sinh | `jextract` | `javac -h` sinh C header theo Java native method |
| Cơ chế gọi | FFM `Linker`/`MethodHandle` (downcall) | JNI native method entry point |
| Cần native library? | **Có** | **Có** |
| Có tự giải quyết ownership? | **Không** | **Không** |

JNI vẫn hữu ích khi Java phải được tích hợp sâu vào C hoặc các native APIs cũ đã dựa trên JNI. jextract + FFM lại đặc biệt thuận tiện khi **đã có một C API công khai** và muốn sinh wrappers một cách cơ học, giảm mã cầu nối phải bảo trì.

## 5. Chi tiết mã sinh: hàm C và accessors

Với C:

```c
void foo(int x);
```

OpenJDK jextract Guide mô tả một bộ APIs có dạng:

```java
// MINH HỌA dạng chữ ký generated, không phải file Java độc lập.
public static void foo(int x) { /* gọi native */ }

public static MemorySegment foo$address() { /*...*/ }
public static FunctionDescriptor foo$descriptor() { /*...*/ }
public static MethodHandle foo$handle() { /*...*/ }
```

Các phương thức có những vai trò khác nhau:

1. `foo(...)`: API mà ứng dụng Java sử dụng trực tiếp; ngữ nghĩa gần với hàm C.
2. `foo$address()`: địa chỉ của symbol native, biểu diễn thành `MemorySegment`.
3. `foo$descriptor()`: `FunctionDescriptor` mô tả native parameter/return layouts.
4. `foo$handle()`: `MethodHandle` được linker tạo và wrapper sử dụng.

Để kiểm thử một hàm trong dự án, có thể in các đối tượng này hoặc xây assertion cho `MethodHandle.type()`. Tuy nhiên, **descriptor được suy ra từ header**, không phải trình kiểm chứng binary ABI. Nếu bạn dùng sai header version hoặc biên dịch C library với macro/struct packing khác, generated Java có thể sai dù source code trông hợp lệ.

### 5.1. Sinh code không đồng nghĩa cung cấp Java API thiết kế tốt cho domain

Tên `add_numbers`, `struct Some_Type` hoặc `foo$handle` cố ý giữ gần C declarations. Điều đó tiện để ánh xạ 1-1, nhưng chưa chắc là một API Java thân thiện. Thư viện production thường có hai tầng:

```text
Native library C
      ↑
Generated jextract bindings
      ↑
Java façade / domain-level API
      ↑
Java application
```

Tầng façade có thể:

- Đổi tên theo Java conventions (ví dụ `add` thay vì `add_numbers`).
- Kiểm tra dữ liệu đầu vào và chuyển native error codes thành exceptions.
- Tạo/đóng `Arena` đúng scope, che raw pointers khỏi callers.
- Chuyển `MemorySegment` chứa UTF-8 C string thành Java `String` bằng API phù hợp.
- Giấu OS-specific constants/layouts dưới một hợp đồng Java ổn định.
- Đảm bảo tài nguyên native được giải phóng đúng một lần.

**Không nhất thiết chỉnh sửa trực tiếp generated sources**. Tạo wrapper bên ngoài giúp lần regenerate sau không xóa các thay đổi thủ công.

## 6. Mapping kiểu C: jextract tự giúp gì và vẫn phải kiểm tra gì?

Khi phân tích header bằng Clang, jextract nhìn thấy các thông tin kiểu C, aliases và platform-specific declarations, rồi chọn FFM layouts tương ứng. Nó giúp tránh sai sót phổ biến khi tự map kiểu bằng mắt.

Bảng dưới đây là mô hình điển hình; mapping thực tế dựa trên **ABI và version jextract**:

| C declaration | Java carrier / FFM thường dùng | Lưu ý |
| --- | --- | --- |
| `int` trên Linux x86-64 | `int` / `ValueLayout.JAVA_INT` | Kiểm tra ABI, không mặc nhiên áp cho mọi target |
| `short` 16-bit | `short` / `JAVA_SHORT` | Java signed; C có unsigned variants |
| `long long` 64-bit | `long` / `JAVA_LONG` | Phân biệt với C `long` |
| `float` | `float` / `JAVA_FLOAT` | ABI float arguments/return |
| `double` | `double` / `JAVA_DOUBLE` | ABI double arguments/return |
| `char *` hoặc `void *` | `MemorySegment` / `ADDRESS` | Java `String` không được truyền trực tiếp như C pointer |
| `struct Point` by value | `MemorySegment` với `GroupLayout` | C ABI padding/return conventions phải khớp |
| `struct Point *` | `MemorySegment` biểu diễn pointer | Không tự biết lifetime, ownership hoặc số phần tử |
| `size_t` | 32/64-bit carrier tùy ABI | Không khẳng định luôn Java `long` trên mọi platform |
| `enum` / numeric macros | Giá trị/hằng theo kiểu C suy ra | Không tự thành Java domain enum |

**Đặc biệt với `long`:** C `long` trên Linux x64 thường 64-bit nhưng Windows x64 thường 32-bit; Java `long` luôn 64-bit. Đây là nguyên nhân một binding tạo trên OS này không thể tùy tiện xem là ABI-correct trên OS khác.

### 6.1. Unsignedness vẫn là trách nhiệm của Java API

Nếu C trả `uint32_t` bằng carrier Java `int`, giá trị có bit cao bằng 1 có thể hiện thành số âm theo signed Java `int`. jextract không tự biến mọi unsigned type thành một arbitrary-precision Java number.

Java façade có thể:

```java
// Fragment: rawUint32 là int mang đúng 32 bit dữ liệu.
long unsignedValue = Integer.toUnsignedLong(rawUint32);
```

Ở chiều ngược lại, phải validate range trước khi ép từ Java `long` xuống unsigned C 32-bit. Jextract giúp dựng binding *bit width/type*, nhưng không thiết kế cho bạn mọi ràng buộc nghiệp vụ.

### 6.2. Pointer và String không cùng kiểu

C declaration:

```c
int consume_text(const char *utf8);
```

Có tham số C pointer, nên generated Java wrapper thường yêu cầu `MemorySegment`. Java client phải chuẩn bị native NUL-terminated string trong arena:

```java
// Fragment giả định đã có generated function consume_text().
try (Arena arena = Arena.ofConfined()) {
    MemorySegment text = arena.allocateFrom("hello");
    int rc = consume_text(text);
    // Xử lý rc trước khi arena đóng.
}
```

Đây là **fragment**; `Arena`/`MemorySegment` cần import và `consume_text` là wrapper giả định trong binding được sinh từ header có hàm đó. `Arena.allocateFrom(String)` mã hóa UTF-8/NUL-termination theo FFM API và giữ buffer sống trong block. **Nếu native API lưu pointer sau khi return**, không được đóng arena ngay; phải thiết kế ownership/lifetime khác.

### 6.3. ABI của struct phức tạp hơn kích thước từng field

Trong C:

```c
struct Mixed {
    char tag;
    int value;
    double weight;
};
```

Một layout ABI thường có padding giữa `tag` và `value`, và yêu cầu alignment cho `double`. Nếu Java tự cộng `1 + 4 + 8` rồi ép struct dài 13 byte, khả năng cao sai ABI. jextract có ích vì Clang đã phân tích offset/alignment theo compiler target, và sinh `MemoryLayout` cùng field accessors cho khai báo đó.

**Dù vậy**, nếu native binary được build với tùy chọn `#pragma pack`, target khác, macro khác hoặc compiler ABI không khớp lúc chạy jextract, layout đã sinh vẫn có thể sai. Header/toolchain chính xác là một phần của giao diện.

## 7. Sinh bindings cho struct/union: không chỉ là wrapper function

Giả sử C header khai báo:

```c
struct Point {
    int x;
    int y;
};
```

OpenJDK jextract Guide mô tả generated class `Point` có thể chứa:

```java
// LƯỢC ĐỒ generated API — minh họa, không compile độc lập.
public static GroupLayout layout();
public static long sizeof();

public static long x$offset();
public static ValueLayout.OfInt x$layout();
public static int x(MemorySegment point);
public static void x(MemorySegment point, int value);

public static MemorySegment allocate(SegmentAllocator allocator);
public static MemorySegment allocateArray(
        long count, SegmentAllocator allocator);
public static MemorySegment asSlice(
        MemorySegment array, long index);
```

Ở đây chỉ là **bản kê chữ ký**, không phải các khai báo Java có body. Các generated structs/unions có thể nằm trong file riêng thay vì class header gốc.

Để sử dụng:

```java
// Fragment: Point là class đã được jextract sinh từ struct Point.
// Đây là mô hình giống ví dụ trong OpenJDK jextract Guide.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment point = Point.allocate(arena);
    Point.x(point, 10);
    Point.y(point, 5);

    System.out.println(Point.x(point)); // 10
    System.out.println(Point.y(point)); // 5
}
```

**Lợi ích của jextract:** bạn không cần tự viết `MemoryLayout.structLayout`, tính `byteOffset` của `x`/`y` hay mọi accessor. Nhưng **đóng arena là trách nhiệm của người gọi**, và không được dùng `point` khi backing memory đã hết lifetime.

### 7.1. Struct pointer khác struct value

Nếu C function trả `struct Point *`, generated Java có thể nhận được một `MemorySegment` mang pointer. Điều này **không tự động cấp quyền free** hay biết có một hay nhiều `Point`. Một số generated helpers có `reinterpret` để tạo view kích thước struct và gắn lifetime vào `Arena`.

Ví dụ ý tưởng theo jextract Guide:

```java
// Fragment minh họa khi C library định nghĩa:
// struct Point *create_point(void);
// void delete_point(struct Point *);
//
// Cần có generated wrappers và owner contract tương ứng.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment raw = create_point();
    MemorySegment point = Point.reinterpret(
            raw, arena, NativeLib::delete_point);

    System.out.println(Point.x(point));
}
// delete_point được đăng ký làm cleanup nếu generated API/version
// và native ownership contract thật sự hỗ trợ mẫu này.
```

Đoạn trên **không phải mẫu runnable độc lập**: `NativeLib` là ký hiệu đại diện cho generated header class thật trong dự án, và phải thay bằng tên đã sinh. Chỉ dùng cleanup nếu native contract quy định **caller owns** pointer và phải gọi đúng `delete_point` đúng một lần. **Không dùng với borrowed pointer, static memory hoặc opaque handles**.

### 7.2. Array-of-structs

Đối với mảng record C, helpers như `Point.allocateArray(n, arena)` và `Point.asSlice(array, i)` giúp xác định **stride theo layout struct** thay vì chỉ nhân theo kích thước `int`. Điều này đặc biệt quan trọng khi struct có padding.

Tuy nhiên, số phần tử **n** vẫn phải đến từ C contract hoặc dữ liệu được kiểm tra; không suy n từ một raw pointer. Chỉ thấy pointer không đủ biết vùng đích dài bao nhiêu.

## 8. Hàm callback: jextract có thể sinh lớp cho function pointer typedef

C interface có thể định nghĩa:

```c
typedef int (*callback_t)(int a, int b);
int run_callback(callback_t cb);
```

jextract thường sinh một lớp `callback_t` (tên cụ thể tùy declaration/tool version) hỗ trợ:

- `descriptor()`: mô tả chữ ký callback.
- `allocate(Function implementation, Arena arena)`: tạo native-callable upcall stub cho Java callback.
- `invoke(MemorySegment functionPointer, ...)`: gọi một function pointer nhận được từ native.

Một fragment theo hướng dẫn chính thức:

```java
// Fragment: run_callback() là generated wrapper đã tồn tại;
// callback_t là class jextract sinh từ typedef.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment callback =
            callback_t.allocate((a, b) -> a + b, arena);

    int result = run_callback(callback);
    System.out.println(result);
}
```

Ở đây `run_callback` trong C phải thực sự gọi callback đúng signature và **không lưu callback sau khi arena đã đóng**. Generated upcall stub chỉ có lifetime tương ứng arena; callback Java có thể bị gọi trên thread native, vì vậy cần cân nhắc exception, synchronization, thread confinement và các hạn chế của FFM upcalls.

**jextract sinh được adapter cơ bản, không tự quyết định callback được phép chạy bao lâu.** Nếu C SDK giữ callback để gọi bất đồng bộ, Java phải giữ stub và arena sống đến khi đăng ký được hủy an toàn.

## 9. Constants, enums, typedefs và global variables

### 9.1. Numeric macros và enum constants

C header:

```c
#define MY_LIMIT 256
enum Mode { MODE_OFF = 0, MODE_ON = 1 };
```

jextract có thể tạo accessors cho các numeric constants, chẳng hạn `MY_LIMIT()`, `MODE_OFF()` và `MODE_ON()`. Chúng không nhất thiết là Java `enum Mode`; đây là lựa chọn cố ý để phản ánh cách C cho phép dùng enum values như các số nguyên và bitmasks.

**Không áp dụng cho mọi macro:** function-like macros như `#define SQUARE(x) ((x)*(x))` không được jextract hỗ trợ như một native function có sẵn. Chúng là logic tiền xử lý C, không phải symbol có địa chỉ để downcall.

Nếu cần một macro dạng hàm trong Java, có thể:

- Viết lại phép toán trong Java nếu ngữ nghĩa đơn giản và không phụ thuộc compiler/platform.
- Tạo một **C shim exported function** bao quanh macro, rồi cho jextract đọc header của shim.
- Với macro phức tạp, thiết kế binding thủ công có kiểm chứng.

### 9.2. Typedefs

`typedef int MyInt;` có thể được sinh thành layout alias; `typedef struct Point MyPoint;` có thể dẫn tới class struct-related riêng hoặc aliases tùy version tool. Việc dùng typedef còn phản ánh **ABI type**, không nhất thiết xây nên domain Java class giàu logic.

### 9.3. Global variables

C:

```c
extern int global_count;
```

jextract có thể cung cấp helpers cho layout, địa chỉ segment của global và getter/setter tương ứng. Nhưng đọc/ghi global C có thể cần synchronization khi nhiều native threads cùng truy cập. Generated wrapper **không tự cung cấp Java memory-model guarantees cho mọi native shared state**.

Không xem bất kỳ C global nào là thread-safe chỉ vì Java accessor là static method.

## 10. Các tùy chọn lệnh jextract cần biết

Bảng tóm tắt những options thường có trong các bản jextract theo OpenJDK Guide; **kiểm tra `jextract --help` và `jextract --version` của bản cài**:

| Tùy chọn | Vai trò |
| --- | --- |
| `--output <dir>` | Thư mục root chứa generated Java sources |
| `--target-package <package>` hoặc `-t` | Package Java được tạo |
| `--header-class-name <name>` | Tên generated root/header class |
| `--library <name-or-path>` hoặc `-l` | Native shared library generated binding sẽ tìm |
| `--include-dir <dir>` hoặc `-I` | Thêm include search path cho Clang |
| `--define-macro NAME=value` hoặc `-D` | Đặt macro cho C preprocessor |
| `--include-function <symbol>` | Chỉ sinh binding cho hàm chỉ định khi dùng lọc |
| `--include-struct <symbol>` | Chọn struct cần sinh trong phạm vi được lọc |
| `--include-typedef <symbol>` | Chọn typedef |
| `--include-var <symbol>` | Chọn global variable |
| `--dump-includes <file>` | Liệt kê declarations/tool filters từ input headers |
| `--use-system-load-library` | Dùng `System.loadLibrary`/`System.load` cho `--library`, chuyển logic tìm thư viện sang `java.library.path` |
| `--copy-comments` | Đưa một số comment header gần declarations vào generated bindings |
| `--version` | Hiện tool/version/JDK/Clang info |

Khi header include nhiều phụ thuộc:

```c
#include "api_types.h"
#include <stdint.h>

int api_process(struct ApiConfig *config);
```

có thể cần:

```bash
jextract \
  --include-dir /path/to/sdk/include \
  --target-package com.example.sdk \
  --output generated \
  --library sdk \
  /path/to/sdk/include/api.h
```

**Các đường dẫn trong đoạn trên là placeholders của hướng dẫn sử dụng, không phải file đã có**. Nếu header bị parse lỗi, xem Clang diagnostics và kiểm tra include path, platform macros, compiler defines, target ABI, packing; đừng vội sửa generated Java bằng tay.

### 10.1. Filter đúng khi header quá rộng

Ví dụ thư viện C có 5.000 declarations nhưng app chỉ cần một hàm:

```bash
jextract \
  --include-function api_version \
  --target-package demo.api \
  --output generated \
  --library api \
  /path/to/sdk/include/api.h
```

Nếu `api_version` phụ thuộc một struct/typedef mà filter đã loại, jextract có thể báo lỗi phụ thuộc và không tạo binding. Vì vậy, một workflow tốt là:

1. Chạy `--dump-includes includes.txt` để biết tên symbols đã parse.
2. Chọn các hàm/struct/typedef liên quan.
3. Giữ dependencies đủ cho từng declaration.
4. Sinh bindings tối thiểu và compile ngay để phát hiện thiếu loại.
5. Thêm regression test đối với generated API.

Không đổi tên macro/function tùy tiện nếu C header đã public; hãy dùng façade Java nếu cần API đẹp hơn.

### 10.2. Macro và các điều kiện compile phải trùng native library

Header:

```c
#ifdef USE_WIDE_VALUES
long long get_value(void);
#else
int get_value(void);
#endif
```

Nếu native library build với `USE_WIDE_VALUES` nhưng jextract parse header **không** có macro ấy, Java sẽ sinh descriptor trả `int` thay vì `long` 64-bit. Compile Java vẫn có thể thành công, nhưng gọi C có thể sai ABI nghiêm trọng.

Khi phải dùng:

```bash
jextract \
  -D USE_WIDE_VALUES=1 \
  --output generated \
  --target-package demo.api \
  --library api \
  /path/to/sdk/include/api.h
```

hãy đảm bảo cả **C compiler và jextract** dùng cùng bộ defines. Một toolchain/CI tốt lưu cấu hình build thành artifact có thể kiểm chứng, không tách macro flags ở hai nơi dễ lệch.

## 11. Nạp thư viện C: `--library` không thay thế native binary

Khi dùng:

```bash
jextract --library minimath --output generated \
  --target-package demo.bindings \
  native/minimath.h
```

generated code thường dùng native library lookup để load tên logic `minimath`. Trên Linux là `libminimath.so`, Windows thường là `minimath.dll`, macOS là `libminimath.dylib`. Cơ chế OS dynamic loader còn phải giải quyết **dependencies** của chính shared library.

Đối với mặc định dùng OS lookup trên Linux, có thể chạy bằng:

```bash
LD_LIBRARY_PATH="$PWD/build" \
  java --enable-native-access=ALL-UNNAMED \
  -cp build/classes MiniMathDemo
```

Nếu generated code được cấu hình `--use-system-load-library`, đường `System.loadLibrary` sẽ tìm qua `java.library.path` thay vì mặc định OS path cho thư viện top-level. Khi thay đổi strategy này, **tái sinh bindings** và cấu hình Java launcher phù hợp.

**Không trộn lẫn một cách máy móc `LD_LIBRARY_PATH` với `-Djava.library.path`** — chúng phục vụ các loader paths khác nhau. Một binary có thể tự load được nhưng không load được dependency; phải kiểm tra cơ chế dynamic linker và packaging cụ thể.

### 11.1. Header version và library version phải tương thích

Một C SDK có thể thay:

- Tên hoặc tham số hàm.
- Kích thước enum/typedef.
- Offsets trong `struct`.
- Calling convention hoặc symbol visibility.
- Semantic ownership của pointer.

Cùng tên `libfoo.so` không bảo đảm ABI giữ nguyên. Quy trình release nên gắn **header version + native binary version + jextract version + target JDK/OS/arch**. Nếu thư viện nâng major version, kiểm thử lại bindings và regenerate khi cần.

### 11.2. Lỗi tên symbol

Nếu header khai báo `extern "C" int add(int,int);` nhưng binary được build từ C++ không có C linkage, symbol có thể bị mangled thành tên khác. Generated jextract sẽ lookup `add` và không tìm thấy. Cách sửa nằm ở **C ABI/exported name**, không phải dùng một Java cast hoặc ép `MethodHandle.type()`.

Tương tự, một native function `static` trong file `.c` không phải exported public symbol cho dynamic linker, nên không thể chỉ khai báo trong header rồi hy vọng jextract gọi được.

## 12. jextract hỗ trợ C, không phải C++ header tổng quát

Một header C++ có template, overloads, classes, exceptions và name mangling không phải input mà jextract có thể chuyển thành Java API đầy đủ như Java code. Theo OpenJDK jextract Guide, phạm vi chính là **C headers**.

Muốn dùng thư viện C++:

1. Tạo một **C-compatible ABI layer**:
   - Các hàm `extern "C"` export tên C.
   - `void *`/opaque handles để biểu diễn đối tượng C++.
   - Các hàm `create/destroy` rõ ownership.
   - API trả error codes thay vì để C++ exception vượt qua boundary.
2. Viết C header công khai cho ABI layer đó.
3. Chạy jextract trên header C.
4. Gọi qua generated Java bindings và quản lý lifecycle.

Ví dụ C wrapper của một C++ engine:

```c
/* engine_c.h: chỉ là API minh họa. */
#ifdef __cplusplus
extern "C" {
#endif

typedef struct EngineHandle EngineHandle;
EngineHandle *engine_create(void);
int engine_step(EngineHandle *handle);
void engine_destroy(EngineHandle *handle);

#ifdef __cplusplus
}
#endif
```

Vì `EngineHandle` opaque, jextract không thể suy ra layout private. Điều đó là **đúng thiết kế**: Java dùng `MemorySegment` handle và wrapper C, không đọc field nội bộ của object C++.

**Không ép jextract parse C++ template class rồi cho rằng sinh được một Java subclass tương đương.** Cầu nối cần hợp đồng C ABI riêng.

## 13. Những giới hạn quan trọng của jextract

OpenJDK Guide nêu nhiều điểm mà jextract **không hỗ trợ hoặc cần xử lý thủ công**, tùy phiên bản:

### 13.1. Function-like macros

`#define SQUARE(x) ((x)*(x))` không có exported function address. Không có `downcallHandle` cho một macro như vậy. Viết Java helper hoặc C shim.

### 13.2. Bitfields của struct

```c
struct Flags {
    unsigned int ready : 1;
    unsigned int mode : 3;
};
```

Bitfield allocation/order phụ thuộc compiler ABI; jextract có thể cảnh báo và **bỏ qua bitfield fields**. Không được tự đọc bytes bên cạnh như thể field đã có generated accessor. Nếu ABI cần bitfields, expose một C helper:

```c
/* Fragment minh họa chữ ký C helper. */
unsigned int flags_get_mode(const struct Flags *flags);
```

để Java gọi qua binding của helper đã được export.

### 13.3. Opaque structs

`struct Handle;` chỉ khai báo type không đầy đủ, không mô tả fields. jextract không thể sinh một class chứa field accessors chính xác cho một struct không có definition. Việc dùng opaque handle qua C functions vẫn khả thi, nhưng Java không được dereference private fields.

### 13.4. Các C types không được FFM hỗ trợ trực tiếp

Một số `long double` rộng hơn 64 bit trên Linux, types phụ thuộc compiler extensions hay vector ABI có thể không map được sang carrier/layout của FFM. Nếu jextract cảnh báo type unsupported, lựa chọn thường là:
- Dùng C shim đổi return/argument sang `double`/integer hoặc buffer layout rõ ràng.
- Thiết kế API trả dữ liệu qua `void *` + length.
- Giới hạn platform support và kiểm thử ABI.

**Không âm thầm đổi `long double` 80/128-bit thành Java `double`** nếu cần giữ toàn bộ precision.

### 13.5. Linker options và call-state capture

Không phải mọi `Linker.Option` đều được diễn đạt bằng option jextract. Chẳng hạn một C function báo lỗi qua `errno` có thể cần `Linker.Option.captureCallState("errno")` khi tự tạo downcall. Nếu generated binding không cấu hình capture, API Java phải có chiến lược khác (ví dụ C shim trả error code/last error trong cùng call).

**Không mặc định jextract sẽ tự biến `errno` thành Java exception**.

### 13.6. Non-native scalar byte order

Các compiler attributes ảnh hưởng byte order của field, chẳng hạn định dạng packed big-endian của một struct đặc biệt, có thể không được generator tự chuyển thành correct FFM layout. Với file formats, byte order phải theo specification; một generated native struct layout không tự bảo đảm on-disk encoding.

### 13.7. Variadic functions

`printf(const char *, ...)` là một native variadic function. jextract có thể tạo invoker-specialization cho các đối số cụ thể, thay vì một static wrapper Java `printf(Object...)` tự xử lý mọi format và C ABI.

Dùng variadics phải xác định chính xác **số và kiểu C arguments** theo calling convention; sai descriptor có thể nguy hiểm. Khi muốn API ổn định hơn, thêm C shim với signature không variadic.

## 14. Quy tắc ownership và memory safety không biến mất khi sinh code

jextract chỉ dựng **lớp gọi native**. C pointer vẫn có thể gây:

- Use-after-free nếu backing memory đã bị giải phóng.
- Double-free nếu caller và callee cùng nhận là owner.
- Memory leak nếu quên gọi đúng destructor/release function.
- Truy cập quá bounds nếu pointer không mang độ dài thật.
- Data race khi C và Java/native thread cùng sửa dữ liệu.
- Invalid pointer khi truyền heap segment như raw C memory hoặc sử dụng scope sai.
- Sai string encoding/NUL termination.

### 14.1. Trường hợp Java sở hữu native buffer

Java có thể:

```java
// Fragment: consume_bytes là generated wrapper của:
// int consume_bytes(const void *bytes, size_t len);
try (Arena arena = Arena.ofConfined()) {
    MemorySegment input = arena.allocate(8);
    input.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

    // Kiểu carrier của len (size_t) phụ thuộc target ABI.
    // Trên Linux x64 thông dụng có thể là long.
    int status = consume_bytes(input, 8L);
    // Kiểm tra status, bảo đảm C không giữ input sau return.
}
```

Không coi đây là file Java độc lập vì `consume_bytes` chưa có implementation/header trong demo chính. Nó minh họa caller ownership: arena phải sống trong suốt lời gọi, sau đó được đóng đúng lúc.

### 14.2. Trường hợp C sở hữu pointer trả về

C API:

```c
/* Fragment khai báo theo hợp đồng thư viện giả định. */
void *buffer_create(size_t bytes);
void buffer_destroy(void *memory);
```

Java wrapper nhận một `MemorySegment` có thể chỉ biểu diễn **giá trị địa chỉ**. Nếu muốn dereference, cần biết kích thước, alignment và lifetime. Việc tự `reinterpret` địa chỉ sai kích thước có thể dẫn tới JVM crash, dù FFM API có kiểm tra bounds theo view.

Thường nên có một Java domain wrapper quản lý:
- Pair `pointer + length`.
- Check NULL.
- Đúng deallocator `buffer_destroy` và exactly-once release.
- Không dùng pointer sau khi release.
- Không để callback dùng pointer đã free.

**jextract không đoán được ai sở hữu vùng nhớ chỉ từ C type `void *`**.

### 14.3. Callback lifetime

jextract-generated callback helper có thể dùng `Arena` để cấp phát upcall stub. Nếu C lưu function pointer để gọi sau, callback scope phải **kéo dài đủ lâu**; không để C gọi stub sau khi arena đóng. Nếu C callback trên native thread, Java callback cần tránh assumptions về thread-local context, locks và exceptions đi qua boundary.

### 14.4. Quyền native access

Generated binding sử dụng restricted FFM APIs khi load library hoặc tạo linker/upcall stub. Trên JDK 22+ ứng dụng thường chạy với:

```bash
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes MiniMathDemo
```

đối với classpath demo; với named modules, cấu hình tên module. Native access là một **quyền nhạy cảm** vì descriptor/ownership sai có thể gây memory corruption hoặc crash. Không bật rộng rãi cho code không đáng tin trong ứng dụng production.

## 15. jextract và kiểm soát sự thay đổi của C SDK

### 15.1. Generated code nên được tạo khi nào?

Theo OpenJDK Guide, jextract thường được chạy **khi tích hợp thư viện native**, rồi generated sources được thêm vào project hoặc build output. Chỉ cần regenerate khi header/library hoặc chính jextract thay đổi, thay vì bắt buộc chạy ở mọi application startup.

Một workflow có thể chọn:
- **Commit generated sources** vào version control để build application không phụ thuộc jextract có sẵn ở mọi máy.
- **Generate trong build pipeline** để đảm bảo tái lập khi toolchain được pin.
- **Phân phối một binding JAR** đi cùng native binaries cho từng nền tảng.

Mỗi cách đều được, miễn kiểm soát version và binary ABI. Không đưa jextract tool vào runtime classpath chỉ vì code được sinh từ nó; người dùng ứng dụng cần generated **classes**, JDK FFM runtime và native library đúng phiên bản.

### 15.2. Tái tạo output cần các input cố định

Danh sách nên pin trong CI:

- Phiên bản **C header** từ SDK.
- Phiên bản **native binary** (`libfoo.so`/DLL/dylib).
- Phiên bản **jextract** (và target JDK/API).
- JDK dùng biên dịch generated Java.
- OS/arch/ABI hoặc target compiler flags.
- Include directories và macro definitions.
- Output package, filtering flags và library-loading strategy.

Vì Clang tiền xử lý `#if` và macros, cùng một header có thể sinh **API khác nhau giữa Linux và Windows**. Không nên generate trên Linux rồi copy JAR sang Windows nếu không chứng minh ABI-compatibility bằng kiểm tra types/layouts.

### 15.3. Generated files và code thủ công nên tách thư mục

Một cấu trúc gợi ý:

```text
project/
├── native/
│   ├── include/
│   └── src/
├── generated-sources/
│   └── demo/bindings/
├── src/main/java/
│   └── demo/api/
│       └── SafeNativeApi.java
└── build/
```

`generated-sources` chỉ chứa đầu ra do jextract quản lý. `SafeNativeApi` là Java façade do developer viết, giữ logic validation/error handling/lifetime. Khi regenerate, không ghi đè façade hoặc chỉnh source generated theo cách sẽ mất khi tool chạy lại.

### 15.4. Kiểm thử sau mỗi lần regenerate

Một bộ test hữu ích:

1. **Build:** generated Java sources compile được với target JDK.
2. **Load:** native library được tìm đúng path và resolve symbols.
3. **ABI scalar:** hàm `int`/`double` trả đúng test vectors.
4. **Struct layout:** đối chiếu `sizeof`/field offsets với C `sizeof`/`offsetof`.
5. **Pointer:** kiểm tra NULL, length, ownership, deallocator.
6. **Callback:** test Java upcall đúng thread và lifetime.
7. **Error codes:** C errors được chuyển thành Java exceptions/status có ý nghĩa.
8. **Portability:** CI với các OS/architectures mà ứng dụng hỗ trợ.
9. **Unload/reload:** không còn worker/callback hoặc raw pointer sau khi thư viện bị unload.
10. **Regression:** generated public API không mất constants/functions bất ngờ do filter/macros.

## 16. Chẩn đoán lỗi khi jextract hoặc generated binding không chạy

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `jextract: command not found` | Chưa tải/không đặt binary vào PATH | Cài jextract riêng, kiểm tra `jextract --version` |
| JDK và generated source không khớp | Binary jextract target FFM API của JDK khác | Dùng jextract compatible release, regenerate |
| Clang báo `file not found` ở header | Thiếu `-I` include dir/SDK headers | Dùng đúng main header và include paths |
| Parser gặp symbols sai | Thiếu/mâu thuẫn `-D`, C macro condition | Dùng compiler defines trùng native build |
| Generated class không có hàm muốn gọi | Chọn sai header, filter bỏ symbol, macro không supported | `--dump-includes` và kiểm tra generated API |
| `cannot find symbol` / `UnsatisfiedLinkError` | Binary thiếu export, sai tên, wrong library version | `nm -D`/`objdump`/platform symbol inspection |
| `libminimath.so` không được load | OS library search path chưa đúng | Kiểm tra `LD_LIBRARY_PATH` hoặc `--use-system-load-library` |
| Native access warning/error | Module chưa có quyền restricted FFM | `--enable-native-access` cho module phù hợp |
| Compile lỗi generated code | Version/tool mismatch, source incomplete, missing generated helper | Pin jextract/JDK và compile tất cả generated Java |
| `WrongMethodTypeException` | Java call site không khớp `MethodHandle.type()` | Kiểm tra accessor `foo$handle().type()` |
| Giá trị scalar C sai trên một OS | Mapping C `long`/`size_t` khác ABI | Generate/test cho OS, kiểm tra canonical layouts |
| Struct fields đọc sai | Padding/packing/ABI mismatch | Kiểm tra C `sizeof`/`offsetof` và Java `layout()` |
| Callback crashes sau khi return | Upcall stub arena đã close hoặc C giữ callback | Thiết kế register/unregister lifecycle |
| JVM crash khi native function chạy | Descriptor/symbol ABI sai, con trỏ không hợp lệ | Kiểm tra header/binary/allocator trước, không chỉ Java stack trace |
| Memory leak | C pointer do caller phải free nhưng wrapper không làm | Dùng deallocator đúng C API, owner wrapper |
| C++ library không tìm đúng symbol | Name mangling hoặc không có C ABI | Tạo `extern "C"` exported shim |

### 16.1. Phân biệt lỗi sinh code và lỗi native runtime

**Lỗi sinh code:** jextract không parse được header, không tạo Java source, hoặc generated Java không compile. Chúng thường có diagnostics rõ ở toolchain.

**Lỗi runtime linking:** Java classes compile nhưng native binary không nằm trên library lookup path, thiếu symbol, hoặc signature ABI không khớp. Chúng chỉ lộ khi load/call native.

**Lỗi memory safety:** call đã chạy nhưng C/Java dùng pointer quá lifetime, sai bounds hoặc concurrent access. Đây là nhóm có thể phá hỏng tiến trình, không nên chờ JVM ném Java exception để phát hiện.

Chia lỗi theo ba giai đoạn giúp debug nhanh hơn:

```text
Header parsing  →  Java compilation  →  Native load/downcall
     │                    │                     │
  Clang/macros          JDK/API          symbols, ABI, lifetime
```

## 17. Cách kiểm tra chất lượng generated bindings

Sau khi sinh code, thay vì chỉ xem số file, hãy kiểm tra:

- **Root class:** package và header class name đúng như options.
- **Native functions:** tên và Java carrier arguments/return phù hợp C ABI.
- **Metadata accessors:** `foo$descriptor()`, `foo$handle().type()` phản ánh đúng intended signature.
- **Structs:** field offsets, `sizeof()`, alignment và array stride.
- **Enums/macros:** values đúng sau preprocessing, không thiếu macro quan trọng.
- **Library load:** đúng `-l`/path, tìm được shared object và dependencies.
- **Error policy:** return codes/`errno` được hiểu đúng và có Java façade khi cần.
- **Ownership:** C allocators/deallocators được ghép cặp, không dùng borrowed pointer như owned pointer.
- **Toolchain match:** jextract/JDK/native headers/binaries nhất quán.

Không nên sửa generated classes để “cho hết lỗi” mà không truy tìm nguyên nhân. Nếu generator parse đúng một header **sai phiên bản**, sửa header/toolchain mới là giải pháp bền vững.

## 18. Câu hỏi tự kiểm tra (kèm đáp án)

**Câu 1.** jextract nhận đầu vào gì và tạo đầu ra gì?  
**Đáp án:** Nhận C header(s) cùng include/macros/options, dùng Clang phân tích và sinh **Java source bindings** dựa trên FFM; không sinh implementation C từ Java và không tự compile native binary.

**Câu 2.** Vì sao jextract không thay thế C compiler?  
**Đáp án:** Header chỉ mô tả declarations. C implementation vẫn phải biên dịch thành binary có exported symbols phù hợp; generated Java wrapper cần binary ấy để chạy.

**Câu 3.** Khi jextract sinh `add_numbers(int,int)`, Java developer còn phải tự viết `Linker.downcallHandle` không?  
**Đáp án:** Thường không. Generated wrapper đã dùng FFM linker bên dưới và có metadata accessors nếu cần kiểm chứng.

**Câu 4.** jextract có phải một phần mặc định của mọi JDK 17/22/25 không?  
**Đáp án:** Không. jextract là công cụ riêng của dự án OpenJDK; phải cài compatible release hoặc build từ source. FFM final từ JDK 22.

**Câu 5.** Vì sao cùng C header có thể sinh Java bindings khác trên Linux và Windows?  
**Đáp án:** C preprocessor, target macros, `long`/`size_t`, struct packing, calling conventions và ABI có thể khác. Phải kiểm chứng platform target.

**Câu 6.** `#define SQUARE(x) ((x)*(x))` có tự sinh thành Java downcall `SQUARE(x)` không?  
**Đáp án:** Không. Function-like macro không có symbol native, cần Java helper hoặc C shim.

**Câu 7.** Khi C header khai báo `struct Point` có x/y, jextract giúp gì?  
**Đáp án:** Sinh layout, field accessors, offsets và allocation helpers theo ABI đã parse, giảm việc tự viết `MemoryLayout`/`VarHandle` cho từng field.

**Câu 8.** Một C function trả `char*`, Java có thể nhận ngay `String` tự động không?  
**Đáp án:** Không nên mặc định. Pointer được thể hiện bằng `MemorySegment`; cần biết encoding, NUL/length, lifetime và giải phóng khi phù hợp.

**Câu 9.** C SDK cấp phát `malloc` và yêu cầu caller free. jextract có tự gọi `free` sau mỗi wrapper call không?  
**Đáp án:** Không. Caller hoặc Java façade phải thực hiện deallocator đúng contract, không free quá sớm hoặc double-free.

**Câu 10.** Vì sao cần `--include-dir` khi header đã có `#include "types.h"`?  
**Đáp án:** Clang preprocessor cần tìm header phụ thuộc để phân tích các kiểu và declarations đúng.

**Câu 11.** `--library foo` có khiến jextract build ra `libfoo.so` không?  
**Đáp án:** Không. Nó nói generated binding sẽ tìm thư viện tên logic `foo`. `libfoo.so` phải có sẵn từ C compiler hoặc SDK.

**Câu 12.** Native binary còn sống nhưng generated binding có thể sai sau nâng SDK vì sao?  
**Đáp án:** Header, macros, ABIs, structs hoặc symbols có thể thay đổi. Cần regenerate và chạy regression tests với đúng version.

**Câu 13.** jextract trực tiếp parse C++ classes/templates được không?  
**Đáp án:** Không theo phạm vi C header của công cụ. Dùng một lớp C ABI wrapper/`extern "C"` phù hợp để liên kết thư viện C++.

**Câu 14.** Tool output cho thấy struct field có type đúng. Có cần kiểm tra ownership nữa không?  
**Đáp án:** Có. Field/accessor chỉ mô tả layout, không khẳng định target memory còn sống hoặc ai phải free nó.

**Câu 15.** Làm sao chứng minh `MethodHandle` sinh cho hàm C `int add(int,int)` là đúng?  
**Đáp án:** In `add$handle().type()` để kiểm tra Java signature, đồng thời đối chiếu **header + ABI + binary thực** và chạy golden native test. Chỉ xem `MethodType` chưa đủ chứng minh toàn bộ ABI.

## 19. Ghi nhớ

- **jextract = C header → Java FFM bindings**. Mục đích là cơ học hóa việc viết wrappers, `FunctionDescriptor`, `MethodHandle` và layouts cho API C.
- **FFM API là nền tảng runtime**, jextract là **tool sinh source độc lập**; từ JDK 22 FFM trở thành API chính thức. Chọn jextract release tương thích JDK.
- **C implementation và native library vẫn cần tồn tại**, với symbols và ABI đúng. `--library` không tự compile binary.
- Generated class thường cung cấp wrapper functions và accessors cho `$address`, `$descriptor`, `$handle`; structs, globals, constants và function pointers được tạo thêm helpers.
- **Clang preprocessor, include paths, macros, compiler target và ABI** ảnh hưởng trực tiếp generated output. Regenerate đúng môi trường, pin versions và kiểm thử đa nền tảng nếu cần.
- **jextract không giải quyết toàn bộ ownership, error handling, encoding, thread-safety hay native safety**. Tạo Java façade kiểm soát lifecycle và domain semantics là thực hành tốt.
- **Đối với JNI**, `javac -h` đi từ Java native declaration sang C headers; còn **jextract đi chiều ngược**, từ C headers sang Java FFM bindings.
- **Kiểm thử cả ba giai đoạn:** parse header thành công, generated Java compile được và actual C binary load/call đúng.

### Tài liệu chính thức

- [OpenJDK jextract — Jextract Guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md): CLI, generated wrappers, structs, callbacks, macros, loader strategy và unsupported features.
- [OpenJDK jextract source repository](https://github.com/openjdk/jextract): source, build instructions, samples và các thay đổi của công cụ.
- [JDK jextract download page](https://jdk.java.net/jextract/): các binary jextract có sẵn; chọn bản tương thích JDK.
- [Dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/): bài hướng dẫn thực hành chính thức với ví dụ sinh bindings.
- [Oracle Java SE 25 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/25/core/call-native-functions-jextract.html): ví dụ triển khai từ C header sang Java FFM.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API hoàn thiện trong JDK 22.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): cơ chế downcall/upcall mà generated bindings dựa vào.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): ánh xạ native function layouts sang Java carriers.
