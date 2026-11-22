# Cấu hình đường dẫn header, macro và các khai báo cần xuất khi sinh liên kết jextract

`jextract` là công cụ của dự án OpenJDK Code Tools giúp **phân tích C header (.h)** và sinh Java bindings sử dụng **Foreign Function & Memory API (FFM)**. Khi một dự án Java cần gọi thư viện C, việc cấu hình đúng `jextract` không chỉ là chỉ đường đến một file `.h`: cần cung cấp **đường tìm những header mà file chính include**, **macro tiền xử lý tương thích với binary C thực tế**, và **danh sách khai báo muốn có trong Java API**. Ba nhóm đó quyết định cả những symbol nào được nhìn thấy lẫn những Java classes/methods nào được sinh.

**Cốt lõi:** `-I` giúp Clang tìm được header; `-D` quyết định nhánh `#if`/`#ifdef` và cấu hình types; `--include-function`/`--include-struct`/`--include-constant` và các bộ lọc tương ứng quyết định khai báo nào có binding. **Header mô tả ABI, còn native binary thực sự cung cấp hàm và dữ liệu.** Nếu bộ header và binary được biên dịch với những macro khác nhau, mã sinh có thể thiếu method, có method nhưng không tìm được symbol, hoặc tệ hơn là truyền nhầm layout/calling convention dẫn đến crash.

> **Phiên bản:** FFM `java.lang.foreign` được chuẩn hóa trong **JDK 22 (JEP 454)**. Các ví dụ hoàn chỉnh dưới đây dành cho **Linux x86-64, JDK 22+ và bản `jextract` tương thích với JDK đang dùng**. `jextract` là công cụ được phát hành riêng, không phải lệnh luôn có sẵn trong thư mục `bin` của mọi JDK. API và tùy chọn của các bản `jextract` có thể thay đổi: hãy đối chiếu `jextract --version`/`jextract --help` của binary thực tế và cố định toolchain trong dự án. Java 17 có FFM incubator khác API nên không biên dịch nguyên mẫu Java 22+.

## 1. Sơ đồ từ header đến Java bindings

```text
C library project
  include/
    demo/
      build.h             <- định nghĩa macro mặc định
      api.h               <- public API, #include <demo/build.h>
  src/
    demoapi.c             <- implementation thật
          |
          +-- C compiler -I include -D... --> libdemoapi.so
          |
          +-- jextract   -I include -D... --> generated/*.java
                                        |
                                        +-- package Java
                                        +-- header/symbol class
                                        +-- struct/union/typedef wrappers
                                        +-- static methods xuống native functions
                                        |
                                  javac + FFM runtime
                                        |
                                      Java app
                                           |
                                  native symbol lookup
                                           |
                                      libdemoapi.so
```

Hai đường ở giữa phải **phù hợp nhau**:

- **Compiler C** đọc header và source với các `-I`, `-D` của nó, rồi tạo shared library chứa native symbols.
- **jextract** dùng Clang để parse header (sau C preprocessing) với các `-I`, `-D` của riêng nó, rồi sinh Java bindings theo khai báo nhìn thấy.
- **Java runtime** load/tìm native library theo `--library`/library lookup và gọi functions qua FFM.

`jextract` **không biên dịch implementation C thành shared library**. Nó không thay thế `cc`/`clang`/`gcc` và không bảo đảm tên symbol ở header thực sự có mặt trong `.so`/`.dll`. Một prototype C hiện diện trong header chỉ là lời khai; code Java được sinh vẫn cần binary native phù hợp khi chạy.

## 2. Ba nhóm cấu hình quan trọng

| Nhóm | Tùy chọn `jextract` | Tác động | Không phải là |
| --- | --- | --- | --- |
| Header gốc | Đối số `path/to/api.h` ở cuối lệnh | Translation unit / file bắt đầu parse | Không phải shared library |
| Header search path | `-I dir` hoặc `--include-dir dir` | Cho C preprocessor tìm `#include` | Không phải Java classpath hay runtime library path |
| Preprocessor macro | `-D NAME=VALUE` hoặc `--define-macro NAME=VALUE` | Thay đổi khai báo/thế hệ types do `#if` điều khiển | Không phải Java system property hay tự động sinh hằng |
| Output Java | `--output generated` | Thư mục gốc chứa Java files sinh ra | Không phải classpath của native loader |
| Package | `--target-package demo.binding` hoặc `-t` | Namespace Java classes được sinh | Không đổi C symbol names |
| Header class | `--header-class-name DemoNative` | Tên class Java gốc có functions/constants | Không đổi C header filename hay library ABI |
| Native library | `--library name` hoặc `-l name` | Library mà generated code tìm symbols/loader | Không phải đường tìm `#include` |
| Explicit selection | `--include-function name`, `--include-struct name`, ... | Lọc declarations được sinh thành bindings | Không thay đổi C binary đã compile |
| List symbols | `--dump-includes file` | Tạo danh sách options `--include-*` có thể sửa để lọc | Không phải bản Java API đã biên dịch |
| Comments | `--copy-comments` (nếu tool version hỗ trợ) | Sao chép comments trước khai báo sang generated docs | Không thay đổi ABI |

Ba tầng đường dẫn thường bị nhầm:

```text
Header search time:  -I /opt/lib/include
Generation output:   --output generated
Native runtime:      --library :/opt/lib/libfoo.so
                      hoặc --library foo với OS search path phù hợp
Java compile/runtime: --class-path classes
```

Các paths phục vụ **bốn cơ chế khác nhau**. Sửa `-I` không giúp JVM tìm `libfoo.so` lúc chạy; sửa `java.library.path` không giúp Clang tìm `foo.h` lúc sinh Java bindings.

## 3. Chọn đúng main header, không chỉ chọn header có prototype cần gọi

Thư viện C thường có public umbrella header như:

```c
/* /opt/vendor/include/vendor/vendor.h */
#ifndef VENDOR_H
#define VENDOR_H

#include <vendor/types.h>
#include <vendor/config.h>
#include <vendor/api.h>

#endif
```

Trong mã C thực, compiler thường dùng:

```c
#include <vendor/vendor.h>
```

Vậy `jextract` cũng nên nhận **main public header** được thư viện khuyến nghị, chứ không tự chọn một internal `detail/private_impl.h` chỉ vì nó chứa prototype.

Vì sao?

1. Main header có thể thiết lập macro feature switches và import các types trước khi khai báo functions.
2. C có include guards, conditional compilation, typedef aliases và cấu trúc phụ thuộc thứ tự `#include`.
3. Một internal header có thể không parse độc lập: thiếu một typedef, macro platform hay packing instruction.
4. Public headers là phần thư viện cam kết hỗ trợ; private headers có thể thay đổi giữa patch versions.
5. Chỉ header gốc không đủ nếu các dependencies được tìm qua `#include <vendor/...>`, nên vẫn cần đúng `-I`.

**C++ lưu ý:** `jextract` chủ yếu phân tích **C ABI từ C headers**. C++ overloads, namespaces, templates, classes và name mangling không được xử lý như một C API ổn định bằng cách đơn giản đưa header C++ vào. Muốn gọi một thư viện C++, cung cấp một C-compatible wrapper:

```cpp
/* Wrapper header minh họa cho thư viện C++. */
#ifdef __cplusplus
extern "C" {
#endif

int widget_compute(int value);
void *widget_create(void);
void widget_destroy(void *widget);

#ifdef __cplusplus
}
#endif
```

Sau đó sinh bindings từ **C wrapper header**; phải triển khai đủ các exported C functions trong binary. Không tưởng `jextract` tự dịch C++ templates thành Java generic classes.

## 4. Cấu hình `-I`/`--include-dir` và thứ tự tìm header

Ví dụ file `include/demo/api.h` có:

```c
#include <demo/build.h>
```

Để parse được, lệnh cần một header search root sao cho `include/demo/build.h` tồn tại:

```bash
jextract -I include include/demo/api.h
```

Hoặc dạng dài:

```bash
jextract --include-dir include include/demo/api.h
```

Trong ví dụ, `include` là **root**, không phải `include/demo`, vì include directive chứa prefix `demo/`. Nếu đặt `-I include/demo`, Clang sẽ tìm dạng `include/demo/demo/build.h` và có thể báo file không tìm thấy.

### Nhiều include directories

```bash
jextract \
  -I vendor/sdk/include \
  -I project/include \
  -I generated/config/include \
  project/include/myproject/api.h
```

`-I` được phép xuất hiện nhiều lần; các thư mục được tìm theo thứ tự đã cung cấp, theo quy tắc lookup của compiler/Clang. **Thứ tự là một phần của build configuration**, đặc biệt khi hai SDKs cùng chứa file tên `config.h` hoặc `types.h`.

Phân biệt:

- `#include "local.h"` thường ưu tiên đường dẫn liên quan tới file đang include rồi mới các search directories, tùy compiler/target.
- `#include <library/foo.h>` được tìm theo các include search paths/system paths.
- `-I vendor/sdk/include` không có nghĩa `jextract` tự chọn mọi `.h` trong thư mục ấy để sinh bindings; nó chỉ giúp parse **những headers thực sự được include** qua translation unit.
- Một header được parse như dependency có thể mang theo nhiều declarations không mong muốn; cần dùng bộ lọc `--include-*` nếu chỉ muốn public surface nhỏ.

### Khi path có dấu cách

Dùng dấu nháy shell để tránh tách path:

```bash
jextract \
  --include-dir "/opt/vendor SDK/include" \
  --output "generated bindings" \
  "/opt/vendor SDK/include/vendor/api.h"
```

Dấu nháy ở đây dành cho **shell**, không phải một phần tên thư mục. Trên Windows PowerShell/cmd, escape/quoting khác Unix; dùng lệnh thích hợp cho OS và in `jextract --help` để xác minh.

### Nhiều main headers

`jextract` hỗ trợ nhiều headers làm đầu vào; tài liệu hướng dẫn yêu cầu `--header-class-name` khi có nhiều input headers, vì không thể suy ra một tên duy nhất từ một file. Ví dụ minh họa:

```bash
jextract \
  --include-dir sdk/include \
  --header-class-name VendorApi \
  --target-package example.vendor \
  --output generated \
  sdk/include/vendor/core.h \
  sdk/include/vendor/io.h
```

Đây là lệnh **mẫu**; cần các files thực tế và include graph đúng. Với project lớn, thường dùng **một umbrella header** được SDK khuyến nghị để hạn chế khác biệt preprocessing/ordering.

## 5. `-D`/`--define-macro` là cấu hình C preprocessor

C headers thường dùng macros để quyết định khai báo nào tồn tại:

```c
#ifndef LIB_ENABLE_FAST
#define LIB_ENABLE_FAST 0
#endif

int lib_normal(int value);

#if LIB_ENABLE_FAST
int lib_fast(int value);
#endif
```

Không có `-D LIB_ENABLE_FAST=1`, parser **không thấy** prototype `lib_fast` vì nhánh `#if` đánh giá false. Khi bật:

```bash
jextract -D LIB_ENABLE_FAST=1 path/to/lib.h
```

Hoặc:

```bash
jextract --define-macro LIB_ENABLE_FAST=1 path/to/lib.h
```

Preprocessor nhìn thấy `LIB_ENABLE_FAST=1`, do đó prototype `lib_fast` đi vào tập symbols có thể extract.

### `#if` khác `#ifdef`

```c
#if LIB_ENABLE_FAST
int fast_a(int);
#endif

#ifdef LIB_ENABLE_FAST
int fast_b(int);
#endif
```

- Không định nghĩa macro: `#if LIB_ENABLE_FAST` được coi là false (có thể có warning từ compiler khi bật strict warnings); `#ifdef LIB_ENABLE_FAST` false.
- `-D LIB_ENABLE_FAST=0`: `#if LIB_ENABLE_FAST` **false**, nhưng `#ifdef LIB_ENABLE_FAST` **true**, vì `#ifdef` kiểm tra **sự tồn tại**, không kiểm tra giá trị.
- `-D LIB_ENABLE_FAST` không có `=...`: theo jextract docs nó định nghĩa macro có giá trị `1`.

Chọn `-D` theo chính semantics của thư viện, không chỉ nhìn tên macro. Nếu header dùng `#ifdef FEATURE`, lệnh `-DFEATURE=0` vẫn có thể **bật nhánh khai báo**.

### Macro ảnh hưởng cả ABI, không chỉ số hàm

```c
#ifdef LIB_USE_WIDE_INDEX
typedef long long lib_index_t;
#else
typedef int lib_index_t;
#endif

int lib_read(lib_index_t index);
```

Nếu binary C được build với `LIB_USE_WIDE_INDEX` nhưng jextract parse header không có macro ấy, Java bindings có thể cho rằng đối số là `int` trong khi C implementation mong đợi `long long`. Kết quả có thể sai hoặc crash; đây là **ABI mismatch**, không chỉ lỗi thiếu symbol.

Vì thế, các macro có ảnh hưởng đến **kích thước type, struct packing, alignment, calling convention, exported functions và conditional declarations** phải được đồng bộ giữa:

1. Build/configuration của thư viện C (hoặc ABI mà prebuilt binary công bố).
2. Lời gọi `jextract`.
3. Target OS/architecture của chương trình Java.

Đừng bật macro chỉ để `jextract` thấy nhiều prototypes hơn, nếu thư viện native thực tế không có ABI/function tương ứng.

### Macro trên command line không tự thành Java constant

Đây là điểm ít được chú ý. Tài liệu `jextract` giải thích: **chỉ macro definitions mà parser gặp trong các header files mới được xem xét để sinh constant accessor**. Một macro được cung cấp **chỉ qua `-D`** để điều khiển preprocessing **không tự động có Java getter** như `LIB_ENABLE_FAST()`.

Ví dụ:

```c
/* Header */
#define LIB_API_VERSION 7
```

`LIB_API_VERSION` là **object-like constant macro trong header**, jextract có thể sinh `LIB_API_VERSION()` nếu loại giá trị được hỗ trợ và không bị bộ lọc loại. Ngược lại, `-D LIB_ENABLE_FAST=1` chỉ tạo preprocessing symbol để chọn nhánh; không mặc nhiên sinh `LIB_ENABLE_FAST()` trong Java.

Không phải mọi macro C trở thành Java code. Theo hướng dẫn `jextract`, hỗ trợ trực tiếp chủ yếu các **object-like macros** có giá trị primitive số, string hoặc pointer mà công cụ biểu diễn được; **function-like macros** như `#define MAX(a,b) ...` không được sinh một Java method tương đương tự động. Nếu cần hàm callable, viết **C wrapper function thật** hoặc chuyển logic đơn giản sang Java.

## 6. Bộ lọc khai báo: chọn chính xác API muốn sinh

Các options chính của `jextract` gồm:

| Option | Chọn loại C declaration | Ví dụ |
| --- | --- | --- |
| `--include-function NAME` | C function | `--include-function demo_add` |
| `--include-constant NAME` | Macro constant / enum constant mà tool nhận diện | `--include-constant DEMO_LEVEL` |
| `--include-struct NAME` | `struct` theo tag/name | `--include-struct DemoPair` |
| `--include-union NAME` | `union` | `--include-union DataValue` |
| `--include-typedef NAME` | `typedef` alias | `--include-typedef demo_handle_t` |
| `--include-var NAME` | Global variable | `--include-var demo_counter` |

Khi **không** dùng `--include-*`, công cụ có thể sinh bindings cho nhiều declarations trong input và các headers đã parse. Khi **có bất kỳ** bộ lọc include nào, các symbols không được match bởi các bộ lọc sẽ bị **loại khỏi tập generated bindings**.

Điều này cho phép một module Java chỉ expose phần API cần thiết. Tuy nhiên, bộ lọc phải tính đến **dependencies**: function dùng `struct`/`typedef`/callback type có thể cần binding type đó. Nếu chọn một function nhưng loại struct mà function phụ thuộc, jextract có thể báo lỗi kiểu “depends on ... which has been excluded” và dừng sinh.

**Ví dụ chọn đủ dependency:**

```c
struct DemoPair {
    int left;
    int right;
};

int demo_pair_sum(const struct DemoPair *pair);
```

Nếu cần generated wrapper cho `demo_pair_sum`, nên chọn **cả**:

```bash
--include-function demo_pair_sum \
--include-struct DemoPair
```

Không cần `--include-typedef DemoPair` ở ví dụ này vì khai báo dùng **`struct DemoPair`**, không có một `typedef DemoPair` riêng. Nếu header thực có `typedef struct ... Foo;`, hãy xem symbols thực tế mà jextract liệt kê và chọn đúng loại cũng như tên tương ứng.

### Dùng `--dump-includes` để biết tên symbol thật

Trước khi thiết kế danh sách include thủ công, có thể chạy:

```bash
jextract \
  --include-dir include \
  --define-macro DEMO_ENABLE_EXTRA=1 \
  --define-macro DEMO_SCALE=3 \
  --dump-includes includes.txt \
  include/demo/api.h
```

`includes.txt` có các dòng options dạng:

```text
--include-struct DemoPair
--include-function demo_add
--include-function demo_scaled
--include-function demo_pair_sum
--include-constant DEMO_LEVEL
```

Đây là **minh họa các dòng liên quan**, không phải lời hứa file chỉ chứa đúng năm dòng hoặc sắp xếp đúng thứ tự ấy. Tài liệu `--dump-includes` có thể chứa comments, headers nguồn và những declarations từ header dependencies. Kết quả thực tế tùy version jextract, platform, trạng thái preprocessing và input headers.

Hãy **đọc danh sách thực** trước khi lọc. Sau đó lưu danh sách chọn vào một **argument file**, ví dụ `selected-includes.txt`:

```text
--include-constant DEMO_LEVEL
--include-struct DemoPair
--include-function demo_add
--include-function demo_scaled
--include-function demo_pair_sum
```

Lệnh chạy:

```bash
jextract @selected-includes.txt \
  -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  --target-package demo.binding \
  --header-class-name DemoNative \
  --output generated \
  --library ":$(pwd)/libdemoapi.so" \
  include/demo/api.h
```

`@argfile` là cách tổ chức cấu hình lặp lại, thuận tiện code review/CI. Nếu một symbol biến mất do thay macro/headers, bước generation nên **thất bại rõ ràng**, không âm thầm tiếp tục với Java API thiếu hàm.

### Không nhầm "export" trong jextract với "export" ở linker C

- `--include-function demo_scaled`: cho phép sinh Java binding **nếu Clang thực sự thấy prototype**.
- `cc -shared ...` / native linker exports: quyết định `libdemoapi.so` có symbol `demo_scaled` để FFM tìm được lúc chạy.
- Một Java method được sinh **không chứng minh** dynamic symbol tương ứng được export.
- Ngược lại, C binary có symbol `demo_scaled` nhưng header `#if` không đưa prototype vào translation unit của jextract thì Java binding **không được sinh**.

Vì vậy, cần kiểm tra cả **header preprocessing** lẫn **exported native symbol table**.

## 7. Bài thực hành hoàn chỉnh: header path, macros và chỉ xuất API đã chọn

Đây là một ví dụ **dành cho Linux x86-64 với JDK 22+ và jextract phù hợp**. Bạn sẽ tạo một thư viện C nhỏ gồm ba functions:

- `demo_add(int,int)`: luôn được công bố và export.
- `demo_scaled(int)`: chỉ được công bố/biên dịch khi `DEMO_ENABLE_EXTRA == 1`; kết quả sử dụng `DEMO_SCALE` từ macro.
- `demo_pair_sum(const struct DemoPair*)`: nhận một C struct pointer; jextract phải sinh cả binding cho `struct DemoPair`.

Đồng thời, header chính định nghĩa `DEMO_LEVEL 7` để minh họa việc include một **constant macro trong file header** thay vì mong một giá trị `-D` tự biến thành Java accessor.

### Sơ đồ files

```text
jextract-lab/
  include/
    demo/
      build.h
      api.h
  src/
    demoapi.c
  DemoMain.java
  generated/                 <- jextract tạo
  classes/                   <- javac -d tạo
  libdemoapi.so              <- cc tạo
```

Tất cả các lệnh bên dưới được chạy trong thư mục `jextract-lab`. Thư mục `include/demo` và `src` phải được tạo trước khi lưu files.

### File 1 — `include/demo/build.h`

```c
#ifndef DEMO_BUILD_H
#define DEMO_BUILD_H

/* Cấu hình mặc định nếu compiler/jextract không truyền -D. */
#ifndef DEMO_ENABLE_EXTRA
#define DEMO_ENABLE_EXTRA 0
#endif

#ifndef DEMO_SCALE
#define DEMO_SCALE 2
#endif

#endif
```

File này là header dependency, **không phải main API header**. Hai macros có thể được ghi đè bằng `-D` khi compiler/jextract parse, vì `#ifndef` chỉ gán giá trị mặc định khi macro chưa tồn tại.

### File 2 — `include/demo/api.h`

```c
#ifndef DEMO_API_H
#define DEMO_API_H

/* -I include cho phép tìm <demo/build.h>. */
#include <demo/build.h>

/* Constant nằm trong header, jextract có thể sinh accessor. */
#define DEMO_LEVEL 7

/* Named C struct, được chọn bằng --include-struct DemoPair. */
struct DemoPair {
    int left;
    int right;
};

/* Public API luôn tồn tại. */
int demo_add(int a, int b);

/* Prototype này phụ thuộc preprocessing macro. */
#if DEMO_ENABLE_EXTRA
int demo_scaled(int value);
#endif

/* Function phụ thuộc C struct layout. */
int demo_pair_sum(const struct DemoPair *pair);

#endif
```

Ý nghĩa:

- `#include <demo/build.h>` cần `-I include`, vì root header `build.h` nằm ở `include/demo/build.h`.
- `DEMO_LEVEL` được `#define` trong **file header** và có giá trị object-like numerical `7`.
- `DEMO_ENABLE_EXTRA` dùng `#if`, nên `-D DEMO_ENABLE_EXTRA=1` mới bật prototype `demo_scaled`.
- `struct DemoPair` có hai fields `int` và một pointer parameter ở function `demo_pair_sum`; Java cần generated struct wrapper/layout để tạo đúng memory.
- Không có C++ constructs; toàn bộ API có C ABI rõ ràng.

### File 3 — `src/demoapi.c`

```c
#include <demo/api.h>

int demo_add(int a, int b) {
    return a + b;
}

#if DEMO_ENABLE_EXTRA
int demo_scaled(int value) {
    return value * DEMO_SCALE;
}
#endif

int demo_pair_sum(const struct DemoPair *pair) {
    if (pair == 0) {
        return -1; /* Sentinel minh họa khi pointer null. */
    }
    return pair->left + pair->right;
}
```

Ở demo, phép cộng/nhân dùng các số nhỏ cố ý không tràn C signed `int`. Code C không malloc và không giữ struct pointer sau lời gọi; Java sẽ cấp struct trong arena có lifetime hợp lệ.

### Bước A — biên dịch native shared library

```bash
mkdir -p generated classes

cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  -o libdemoapi.so src/demoapi.c
```

**Cấu hình quan trọng:** Thư viện C được biên dịch với `DEMO_ENABLE_EXTRA=1` nên **có export `demo_scaled`**, và với `DEMO_SCALE=3` nên `demo_scaled(4) == 12`.

Kiểm tra symbol exports (Linux):

```bash
nm -D --defined-only libdemoapi.so
```

Danh sách còn phụ thuộc compiler/linker, nhưng phải tìm được các symbols `demo_add`, `demo_scaled` và `demo_pair_sum`. Không kỳ vọng có dynamic symbol `DEMO_LEVEL`, vì đó là **preprocessor constant**, không phải C function hay biến toàn cục.

### Bước B — tạo Java bindings với đúng macros và filters

```bash
jextract --version

jextract \
  --include-dir include \
  --define-macro DEMO_ENABLE_EXTRA=1 \
  --define-macro DEMO_SCALE=3 \
  --output generated \
  --target-package demo.binding \
  --header-class-name DemoNative \
  --library ":$(pwd)/libdemoapi.so" \
  --include-constant DEMO_LEVEL \
  --include-struct DemoPair \
  --include-function demo_add \
  --include-function demo_scaled \
  --include-function demo_pair_sum \
  include/demo/api.h
```

**Giải thích chính xác từng phần:**

1. `include/demo/api.h` là main public header của example.
2. `--include-dir include` cho phép Clang parse dependency `<demo/build.h>`.
3. `--define-macro DEMO_ENABLE_EXTRA=1` làm `#if DEMO_ENABLE_EXTRA` true, để `demo_scaled` xuất hiện trong **header view** của jextract.
4. `--define-macro DEMO_SCALE=3` đồng bộ macro được dùng khi biên dịch implementation. Macro này chỉ ảnh hưởng preprocessing; không nhất thiết có Java accessor `DEMO_SCALE()` vì nó **không** được `#define` trong header trong trường hợp đã có giá trị `-D`.
5. `--include-constant DEMO_LEVEL` sinh binding cho hằng có definition ở `api.h` (có thể truy cập qua accessor như `DEMO_LEVEL()`).
6. `--include-struct DemoPair` tạo wrapper/layout cho C `struct DemoPair`; nếu bỏ nó trong khi function cần struct, có nguy cơ thiếu dependency.
7. Ba `--include-function` giới hạn Java bindings vào đúng ba C functions cần dùng.
8. `--target-package demo.binding` đặt Java namespace.
9. `--header-class-name DemoNative` đặt tên header/root class Java ổn định thay vì suy ra `api_h` từ filename.
10. `--output generated` chỉ định thư mục gốc chứa các Java files.
11. `--library ":$(pwd)/libdemoapi.so"` dùng `:` mở đầu giá trị library để `jextract` hiểu phần sau là **đường dẫn shared library**, không phải một logical library name. `$(pwd)` được shell Linux thay bằng absolute directory trong lúc chạy lệnh, giúp generated binding load đúng file cụ thể.

**Lưu ý:** `--library` không thay đổi nội dung declarations được parse; nó ảnh hưởng cách generated bindings tìm/load native symbols khi chạy. Nếu chỉ sinh code từ header mà không có binary, có thể không cần `--library` tại bước generation, nhưng ứng dụng cuối vẫn phải thiết lập library lookup phù hợp.

### Bước C — xem Java files được sinh

```bash
find generated -type f -name '*.java' -print
```

Với cấu hình trên, cần thấy các generated sources thuộc `package demo.binding`, gồm header class `DemoNative` và struct binding `DemoPair` (tên/kiến trúc các file phụ có thể khác giữa các phiên bản `jextract`). Dự kiến có các entry points kiểu:

```java
// MÔ PHỎNG cấu trúc API, không phải copy exact generated source.
package demo.binding;

public class DemoNative {
    public static int DEMO_LEVEL() { /* ... */ }
    public static int demo_add(int a, int b) { /* ... */ }
    public static int demo_scaled(int value) { /* ... */ }
    public static int demo_pair_sum(
            java.lang.foreign.MemorySegment pair) { /* ... */ }
}

public class DemoPair {
    public static java.lang.foreign.MemorySegment allocate(
            java.lang.foreign.SegmentAllocator allocator) { /* ... */ }
    public static void left(
            java.lang.foreign.MemorySegment segment, int value) { /* ... */ }
    public static void right(
            java.lang.foreign.MemorySegment segment, int value) { /* ... */ }
}
```

**Đây là pseudocode về shapes/tên phương thức**, không phải Java file compile trực tiếp: Java không cho hai public top-level classes trong một source file, và phần bodies còn được jextract tự sinh. **Không chỉnh tay generated code** dựa trên mô phỏng; hãy mở thực tế `generated/.../DemoNative.java` và `DemoPair.java` để xác minh tên/methods do bản tool của bạn tạo ra. Hướng dẫn OpenJDK mô tả cơ chế generated header class và struct wrappers tương tự.

### File 4 — `DemoMain.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

import demo.binding.DemoPair;
import static demo.binding.DemoNative.*;

public final class DemoMain {
    public static void main(String[] args) {
        System.out.println("level=" + DEMO_LEVEL());
        System.out.println("add=" + demo_add(2, 5));
        System.out.println("scaled=" + demo_scaled(4));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment pair = DemoPair.allocate(arena);
            DemoPair.left(pair, 8);
            DemoPair.right(pair, 11);
            System.out.println(
                    "pair=" + demo_pair_sum(pair));
        }
    }
}
```

Java tự cấp struct qua `Arena.ofConfined()`; `DemoPair.allocate(arena)` sử dụng layout đúng của C struct do jextract sinh từ header. `DemoPair.left(pair, 8)` và `right(pair, 11)` là setter. C function mượn pointer **chỉ trong lời gọi đồng bộ**, không giữ lại sau khi return; đóng arena sau đó là hợp lệ.

**Không tự viết `new DemoPair(...)`**: generated struct wrapper thường thao tác trên `MemorySegment` có layout/offset theo ABI chứ không giống một Java POJO có fields độc lập.

### Bước D — compile/run Java

```bash
javac -d classes \
  $(find generated -type f -name '*.java') \
  DemoMain.java

java --enable-native-access=ALL-UNNAMED \
  -cp classes \
  DemoMain
```

`--enable-native-access=ALL-UNNAMED` áp dụng khi app và generated binding ở unnamed module/classpath; khi ứng dụng đặt trong named module, cấp native access cho đúng module. Các nguồn generated jextract dùng FFM restricted calls để thực hiện native downcalls/library lookup.

Trên toolchain jextract/JDK tương thích với guide, **stdout kỳ vọng**:

```text
level=7
add=7
scaled=12
pair=19
```

Đối chiếu số học:

- `DEMO_LEVEL` được định nghĩa bằng `7` trong `api.h`.
- `demo_add(2,5) = 7`.
- Native binary compile với `DEMO_SCALE=3`; `demo_scaled(4) = 4 × 3 = 12`.
- `DemoPair` có `left = 8`, `right = 11`; C `demo_pair_sum` trả `8 + 11 = 19`.

Mọi con số trên phụ thuộc **đúng cùng headers/macros/library binary đã cung cấp**. Nếu jextract version thay đổi hình dạng generated wrappers, hãy dùng `jextract --version`/`--help`, đọc code được sinh và điều chỉnh phần gọi Java theo generated API thực, không ép generated classes trở về giả định cũ.

## 8. Ba thí nghiệm có chủ đích để nhìn rõ ý nghĩa flags

### Thí nghiệm 1 — bỏ `-I include`

```bash
jextract \
  -D DEMO_ENABLE_EXTRA=1 \
  --output generated-no-include \
  include/demo/api.h
```

Vì `api.h` chứa `#include <demo/build.h>`, tool có thể báo kiểu `'demo/build.h' file not found` hoặc lỗi parse dependency. Dùng `-I include`, **không** phải `-I include/demo`, để Clang có đúng header search root.

Nếu một máy tình cờ có header cùng tên trong system include path, build có thể vô tình parse **nhầm version header**. Vì thế test chỉ để minh họa; production nên pin SDK include root và xác minh source header đã parse, không chỉ kiểm tra tool exit code.

### Thí nghiệm 2 — bỏ `-D DEMO_ENABLE_EXTRA=1`

```bash
jextract \
  -I include \
  --dump-includes without-extra.txt \
  include/demo/api.h
```

Ở `build.h`, default `DEMO_ENABLE_EXTRA=0`. Do `#if DEMO_ENABLE_EXTRA` false, prototype `demo_scaled` bị loại trong preprocessing, nên danh sách symbols không có function này. Nếu sau đó cố yêu cầu `--include-function demo_scaled`, tool không thể sinh binding đúng cho một function **không tồn tại trong translation unit**.

Ngược lại, nếu C binary đã compile feature ON nhưng Java code generated từ feature OFF, bạn sẽ có native symbol mà Java binding không expose. Nếu feature OFF trong native binary nhưng ON khi jextract parse, generated Java có method nhưng native lookup lúc gọi có thể báo missing symbol.

### Thí nghiệm 3 — lọc thiếu struct dependency

```bash
jextract \
  -I include \
  --include-function demo_pair_sum \
  --output generated-missing-type \
  include/demo/api.h
```

`demo_pair_sum` nhận `const struct DemoPair *`. Theo cơ chế filtering của jextract, nếu struct bị loại trong khi function phụ thuộc nó, tool có thể dừng với lỗi dependency (tùy bản tool và hình thức type). Không nên cố né bằng cách đưa một địa chỉ `long` tùy ý vào Java. Hãy bổ sung `--include-struct DemoPair` và tái sinh bindings.

**Quy tắc lọc:** chọn API theo **dependency closure** (các types/constants/layouts cần thiết), không chỉ theo tên những functions Java sẽ gọi.

## 9. `--dump-includes`, `@argfile` và cấu hình có thể lặp lại

Với SDK lớn, chạy `jextract` không filter có thể sinh hàng nghìn Java classes/methods. Tập API quá lớn:

- Làm generated code khó review.
- Tăng chi phí compile, thay đổi dependency graph.
- Vô tình đưa internals vào Java module.
- Tăng rủi ro code thay đổi khi SDK update.
- Khi header chứa platform-specific types, có thể phát sinh phần API Java không dùng đến nhưng vẫn cần giải quyết.

Một quy trình nhất quán:

```text
1. Chọn đúng SDK version và umbrella header
2. Khóa compiler target, -I roots, -D switches
3. jextract --dump-includes symbols.txt ...
4. Chọn functions / constants / structs / typedefs cần dùng
5. Lưu selected includes trong @argfile (được code review)
6. jextract @argfile với cùng -I/-D/package/library
7. Compile generated Java
8. Test native call + binary ABI
9. Commit generated sources và cấu hình toolchain theo chính sách dự án
```

Dùng `@argfile` tách danh sách symbols ra khỏi build script giúp review thay đổi API khi thư viện nâng version: một function biến mất hoặc một typedef đổi có thể được phát hiện sớm.

Một điểm tinh tế: **macro trên command line không tự trở thành accessor**, nhưng macro trong header có thể sinh Java constant nếu jextract hỗ trợ loại giá trị. Nếu muốn Java code có một constant API ổn định, ưu tiên **named enum/object-like constant definition trong public header**, hoặc C function như `int lib_api_version(void)` nếu giá trị phải được xác định ở runtime. Không dùng `-D` như một "Java constant generator".

## 10. Debug theo tầng: lỗi header, preprocess, bindings, runtime

Khi `jextract` hoặc Java app thất bại, chẩn đoán **đúng tầng**:

| Triệu chứng | Tầng | Nguyên nhân có khả năng | Kiểm tra/sửa |
| --- | --- | --- | --- |
| `fatal error: demo/build.h: No such file or directory` | Parse/header | Sai `-I` root, header path/SDK | Xác minh `include/demo/build.h` tồn tại, thêm `-I include` |
| `unknown type name` | Preprocess/dependency | Thiếu header, macro loại typedef, sai include order | Dùng main header, đồng bộ `-D`, check preprocessed text |
| Không thấy `demo_scaled` trong generated Java | Preprocess/filter | `DEMO_ENABLE_EXTRA` false, hoặc thiếu `--include-function` | `--dump-includes` với đúng `-D` rồi thêm filter |
| `DemoPair` không được sinh | Filter/dependency | Thiếu `--include-struct DemoPair` | Chọn type closure, không chỉ function |
| Thấy `DEMO_SCALE=3` khi compile C nhưng không có `DEMO_SCALE()` Java | Constant generation | Macro chỉ đặt qua `-D`; không phải definition header | Muốn constant thì khai báo tương thích trong public header |
| Generated Java thiếu `DEMO_LEVEL()` | Filter/macro | Không hỗ trợ macro type, macro không được thấy hoặc thiếu include-constant | Kiểm tra `--dump-includes`, header và jextract version |
| `UnsatisfiedLinkError`/symbol not found | Runtime lookup | Sai `--library`, binary không export symbol, feature macro C OFF | `nm -D`, kiểm tra `LD_LIBRARY_PATH`/absolute library |
| Java compile báo package/class không tồn tại | Java compile | Sai `--output`/`-t`, quên compile generated files | `find generated`, `javac -d classes ...`, classpath |
| JDK báo lỗi native access | FFM restricted access | Thiếu `--enable-native-access` đúng module | Thêm flag theo JDK/unnamed/named module |
| JVM crash hoặc trả số vô lý | ABI | Header khác binary, struct packing, C `long` width, calling convention | Đối chiếu SDK+target macros+layouts, dùng sanitizers |
| Java chạy được trên Linux nhưng lỗi Windows | Platform | OS search/ABI/packing/`long` khác | Sinh/test bindings theo OS/arch đích |
| C library được compile nhưng jextract không chạy | Toolchain | Chưa cài jextract, thiếu native libclang, mismatch JDK/tool version | `jextract --version`/`--help`, cài đúng release |
| Macro function-like không thành Java method | Generator support | Không được jextract hỗ trợ trực tiếp | Viết exported wrapper C function hoặc Java helper |
| Truy cập memory sau `Arena.close` | Lifetime | Buffer/native pointer bị giữ quá hạn | Owner/lifetime đúng, không giữ pointer khi arena đóng |

**Lưu ý:** Một `UnsatisfiedLinkError` có thể phát sinh do bản thân shared library không load được hoặc vì native function symbol không thấy. Cần đọc thông điệp và native loader diagnostics, không quy ngay cho `-I`.

### Dùng C compiler để xem preprocessing

Để kiểm tra nhánh C nào thực sự active:

```bash
cc -E -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  src/demoapi.c > preprocessed.c

grep -n 'demo_scaled' preprocessed.c
```

Đây là kỹ thuật hỗ trợ đối chiếu **cùng macro/header config**, không thay thế output thực từ Clang/jextract nếu compiler/target khác. Không commit `preprocessed.c` vào source tree trừ khi có lý do đặc biệt, vì file này rất lớn và phụ thuộc môi trường.

Để xem macro definitions đang active (compiler GCC/Clang hỗ trợ):

```bash
cc -dM -E -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  include/demo/api.h | grep 'DEMO_'
```

Kỳ vọng có những macro như `DEMO_ENABLE_EXTRA 1`, `DEMO_SCALE 3` và `DEMO_LEVEL 7`. Việc một macro tồn tại trong kết quả preprocessing **không có nghĩa** jextract bắt buộc sinh Java accessor cho nó.

### Kiểm tra native symbol export thực

```bash
nm -D --defined-only libdemoapi.so |
  grep -E 'demo_add|demo_scaled|demo_pair_sum'
```

Nếu thiếu `demo_scaled`, xem lệnh `cc` có `-D DEMO_ENABLE_EXTRA=1` không. Nếu một function được khai báo `static` trong C source, nó có **internal linkage** và thường không thể được tìm qua dynamic symbol lookup; cần exported C API thật. Nếu dự án build với `-fvisibility=hidden`, phải thêm export attribute đúng platform để public functions visible.

### Kiểm tra generated Java chứ không đoán

```bash
grep -R 'demo_scaled' generated
grep -R 'class DemoPair' generated
grep -R 'DEMO_LEVEL' generated
```

Những lệnh tìm kiếm này chỉ để debug **generated Java của bài thực hành**, không thay cho việc mở mã nguồn để review ABI. Generated files có thể có nhiều helper classes và metadata tùy version; tên package hoặc signatures thay đổi cần đối chiếu guide/release thực tế.

## 11. Lọc declaration theo dạng type thực tế

### Functions

`--include-function NAME` yêu cầu C function đã có **declaration được parser nhìn thấy**. Nếu header chỉ có một macro `#define CALL(x) do_work(x)` nhưng không có prototype `CALL`, không thể dùng `--include-function CALL` rồi mong sinh downcall C function tương ứng. Java downcall cần **native symbol callable**, không phải macro đã được C preprocessor xóa/expand.

### Structs/Unions

`--include-struct NAME` / `--include-union NAME` chọn C aggregate types. C layout phụ thuộc alignment, packing, compiler ABI và conditional fields; trong production nên kiểm tra `sizeof`, offsets và binary version. Một field bị thay từ `int` sang `long` qua macro có thể làm layout Java generated sai nếu build C/jextract không đồng bộ.

### Typedefs

`--include-typedef NAME` chọn aliases, đặc biệt quan trọng khi C API dùng opaque handle hoặc function-pointer typedef. Một typedef như `typedef struct Opaque Opaque;` có thể biểu thị incomplete type chỉ được truyền qua pointer; không nên dùng Java segment như một struct value có layout chưa biết. Cần nắm rõ ownership API `create/destroy` thay vì cố dereference opaque memory.

### Constants

`--include-constant NAME` chọn những object-like macros/enum constants mà parser nhận diện. C enum values có thể được sinh dưới dạng Java accessor; C function-like macros không tự trở thành callable functions. Một số floating, string, pointer constants có representation khác primitive integers; mở generated source thay vì luôn giả định `int`.

### Global variables

`--include-var NAME` cho exported global variables được public header công bố, nhưng C `static`/thread-local globals hoặc symbols bị hidden visibility có thể không resolve ở runtime. Truy cập C global native memory cần thread safety và đúng lifetime. Không nhầm global variable declaration với một `#define` macro constant.

### Callback typedef và nested dependencies

Nếu một function nhận C function pointer typedef, generator có thể cần generated functional interface/helper cho callback ABI. Lọc function mà quên typedef có thể gây thiếu dependency. Callback Java được FFM chuyển thành upcall stub trong arena có lifetime rõ; không chỉ cần tên function trong `--include-function`.

## 12. Chọn `--library` và cách tải thư viện khi chạy

### Tên logic

```bash
jextract --library demoapi \
  --output generated \
  --target-package demo.binding \
  -I include \
  include/demo/api.h
```

Tên `demoapi` được ánh xạ bởi platform, thường là `libdemoapi.so` trên Linux. Generated code dùng library lookup theo công cụ và OS search mechanism. Khi chạy có thể cần thư viện nằm trên các paths mà OS dynamic loader tìm được.

### Đường dẫn cụ thể

```bash
jextract --library ":/absolute/path/libdemoapi.so" \
  --output generated \
  -I include \
  include/demo/api.h
```

Dấu `:` làm library specifier được hiểu là **path** thay vì logical library name. Đây là cách dễ tái lập trong lab, nhưng việc hard-code absolute path trong **generated bindings** không phù hợp cho ứng dụng phân phối sang máy khác. Trên CI/production, cân nhắc logical library name, loader configuration hoặc cơ chế copy/package native libs có version rõ.

### `--use-system-load-library` là một lựa chọn khác

Theo OpenJDK jextract guide, option `--use-system-load-library` làm generated code load các libraries trong `-l` qua `System.loadLibrary`/`System.load` theo JNI library loading mechanism. Khi đó `java.library.path` có ý nghĩa, nhưng phụ thuộc native của thư viện vẫn có thể được OS loader xử lý bằng search paths riêng.

**Không trộn các hướng dẫn đường dẫn:** `-I` dành cho C headers, `--library` cho native binary và `-cp`/`--class-path` cho Java classes. Chúng giải quyết ba nhu cầu khác nhau.

## 13. Khi nâng cấp SDK hoặc đổi nền tảng

`jextract` sinh code phụ thuộc **cách C headers được parse tại thời điểm generation**. Việc upgrade SDK không chỉ là copy file `.so` mới nếu ABI thay đổi.

Một quy trình cập nhật đáng tin:

1. Pin **version header**, **version native binary**, **compiler target**, **jextract release** và **JDK version**.
2. Lưu/kiểm tra danh sách `-I` search roots, `-D` feature switches và các `--include-*` filters.
3. Regenerate bindings trong môi trường tương thích với OS/architecture đích.
4. So sánh generated sources với bản đã review: functions, constants, structs, field offsets, type carriers.
5. Build C binary với cùng feature macros/ABI.
6. Compile Java, chạy smoke tests với native symbols thật.
7. Chạy tests về negative paths (missing feature, missing library, null pointers, lifetime/arena).
8. Với structs/pointers/ownership, kiểm tra thêm type sizes, alignment, target ABI và concurrency.
9. Chỉ deploy khi header/binary/generated Java là một **bộ tương thích**.

Đặc biệt với C `long`: trên Linux 64-bit thông dụng `long` 64 bit; trên Windows 64-bit phổ biến `long` 32 bit. Struct layout có thể khác, dù Java code cùng tên methods. Không phát hành một bản binding platform-specific cho mọi OS mà không kiểm chứng.

Một dòng Java `import static demo.binding.DemoNative.*;` trông thuần Java nhưng **một phần contract bên dưới là native ABI**; cần coi generated bindings là code boundary có rủi ro cao hơn Java thông thường.

## 14. Checklist review trước khi sinh code và release

- [ ] Đã chọn đúng **main public C header** của SDK, không trỏ nhầm internal header.
- [ ] Đã xác nhận `-I` root cho mọi `#include` transitive, có tính thứ tự và path có khoảng trắng.
- [ ] `-D` trên jextract khớp build/native binary, nhất là các macro ảnh hưởng **ABI**, packing và conditional declarations.
- [ ] Đã phân biệt `#if FEATURE` và `#ifdef FEATURE`; không dùng `-DFEATURE=0` nếu mục tiêu là làm `#ifdef FEATURE` false.
- [ ] Hiểu macro `-D` chỉ preprocessing; object-like macro trong header có thể thành Java constant khi được support; function-like macro không được sinh như function.
- [ ] Đã chạy `--dump-includes` để biết đúng names/kinds của symbols.
- [ ] Filters chọn đủ functions, constants, struct/union/typedef dependencies và global variables thực sự cần.
- [ ] Không giả định một function được chọn là symbol C đã export; đã kiểm tra `nm`/linker map trên binary thật.
- [ ] Đã cố định `--target-package`, `--header-class-name` và `--output` để generated Java ổn định.
- [ ] `--library`/OS loader paths và Java classpath được cấu hình độc lập với header search paths.
- [ ] Đã chọn jextract release **tương thích JDK** (FFM final JDK 22+); xác minh `jextract --version`/`--help`.
- [ ] Khi dùng restricted FFM, đã cấu hình `--enable-native-access` cho đúng named/unnamed module.
- [ ] Đã compile generated Java sources và gọi thật vào C library với ít nhất một struct/pointer API.
- [ ] Đã kiểm tra ownership, lifetime Arena, native pointers và deallocator (jextract không giải quyết chúng tự động).
- [ ] CI phát hiện drift khi SDK/headers/macros thay đổi; không hand-edit generated files rồi bỏ bước regenerate.
- [ ] Với nhiều OS/arch, sinh và kiểm thử bindings cho từng target cần hỗ trợ.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `-I include/demo` có phù hợp khi `api.h` viết `#include <demo/build.h>` và file nằm tại `include/demo/build.h` không?

**Không.** Root phù hợp là `-I include`. Với `-I include/demo`, Clang có thể tìm sai đường kiểu `include/demo/demo/build.h`.

**Câu 2.** Nếu C binary compile `DEMO_ENABLE_EXTRA=0` nhưng jextract dùng `-D DEMO_ENABLE_EXTRA=1` thì có vấn đề gì?

Có. jextract sẽ thấy prototype `demo_scaled` và sinh Java binding; binary có thể **không export symbol** này. Java gọi generated method có thể lỗi khi symbol lookup (hoặc khi class/helper khởi tạo). Đây là mismatch giữa header view và actual binary.

**Câu 3.** `-D DEMO_SCALE=3` có bảo đảm generated Java có method `DEMO_SCALE()` không?

**Không.** `-D` định nghĩa macro trong quá trình preprocessing; theo jextract guide, command-line-only macro không tự sinh Java accessor. Một object-like macro `#define` trong header và nằm trong loại được hỗ trợ mới là ứng viên constant accessor.

**Câu 4.** Tại sao phải chọn `--include-struct DemoPair` cùng `--include-function demo_pair_sum`?

Vì function phụ thuộc layout của `struct DemoPair`. Khi bật filters, loại type cần thiết có thể khiến generated binding thiếu dependency; jextract có thể báo lỗi và ngừng. Chọn API theo **dependency closure**.

**Câu 5.** `--include-function demo_add` có làm `demo_add` được export trong `libdemoapi.so` không?

**Không.** Nó chỉ chọn một C declaration để sinh Java binding. Exports do C compiler/linker và visibility quyết định.

**Câu 6.** Một header có `#define MULTIPLY(x,y) ((x)*(y))`, có thể dùng `--include-function MULTIPLY` để sinh JNI/FFM downcall không?

**Không.** Đây là **function-like preprocessor macro**, không phải callable native function symbol; jextract không tự sinh Java function tương đương. Hãy tạo exported C wrapper function hoặc Java helper.

**Câu 7.** Có thể dùng `-D FEATURE=0` để tắt mọi nhánh có macro FEATURE không?

Không. `#if FEATURE` false nhưng `#ifdef FEATURE` true. Phải đọc implementation conditional của header trước khi chọn cách bật/tắt.

**Câu 8.** Tại sao cần `--header-class-name` khi nhiều input headers?

Theo jextract guide, khi có nhiều main headers, tool yêu cầu tên header/root class Java cụ thể. Với một header, có thể dùng option này để ổn định API thay vì để tool suy ra từ tên file.

**Câu 9.** Native library nằm ở `/opt/lib/libdemoapi.so`, Java không load được. Thêm `-I /opt/lib` giúp gì?

Không. `-I` chỉ giải quyết include header tại generation. Runtime cần đúng `--library`/dynamic loader paths (hoặc `--use-system-load-library` cùng `java.library.path`), không phải C header path.

**Câu 10.** Java binding đã compile thành công có nghĩa C ABI chắc chắn đúng không?

Không. Java compiler không xác minh actual C struct layouts, native symbols, macro build flags và calling conventions trong binary. Chỉ running native integration tests trên OS/architecture đích và kiểm tra ABI mới giúp xác nhận.

**Câu 11.** Khi nào nên dùng `--dump-includes` + `@argfile` thay vì gõ thủ công 60 flags?

Khi SDK lớn, nhiều declarations và cần một allowlist được review, tái lập giữa các machines. `--dump-includes` cung cấp tên/kind thật sau preprocessing; `@argfile` giúp lưu danh sách filters, nhưng vẫn cần cùng `-I`/`-D`/tool versions.

**Câu 12.** Có thể đưa trực tiếp C++ template header vào jextract để sinh Java binding cho mọi C++ overloads không?

Không nên. Công cụ làm việc với C headers/C ABI; hãy tạo một C wrapper API có `extern "C"`, functions/types rõ ràng rồi sinh Java bindings từ wrapper.

## 16. Tài liệu chính thức

- OpenJDK Code Tools — [jextract Guide: Running jextract, macros, filtering, command-line reference, library loading](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- Dev.java — [Generate Java Bindings with Jextract: -I/-D, -l, -t, --dump-includes và --include-*](https://dev.java/learn/ffm/jextract/).
- OpenJDK — [jextract repository và hướng dẫn download/build](https://github.com/openjdk/jextract).
- Oracle Java 22 — [Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).
- OpenJDK — [JEP 454: Foreign Function & Memory API, finalized trong JDK 22](https://openjdk.org/jeps/454).
- GCC — [Preprocessor Options -D, -I và conditional compilation](https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html).

**Ghi nhớ:** `jextract` không tự chọn thay bạn đường header, macro ABI hoặc phần C API cần sinh. Hãy **chọn đúng main header**, cấu hình `-I` để Clang tìm đầy đủ dependencies, dùng `-D` khớp library build, xem symbols bằng `--dump-includes` rồi lọc bằng `--include-*` kèm types phụ thuộc. Cuối cùng đối chiếu generated Java với **native binary thật** và chạy FFM integration tests trên đúng nền tảng.