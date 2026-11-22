# Sinh lại jextract khi header thay đổi và kiểm chứng với thư viện nhị phân được phân phối

## 1. Tại sao sinh lại binding chưa đủ?

`jextract` là công cụ OpenJDK đọc **C headers** bằng Clang và sinh **Java bindings** dùng Foreign Function & Memory API (FFM). Nó có thể tạo các lớp chứa `MemoryLayout`, `FunctionDescriptor`, `MethodHandle` và wrapper để Java gọi hàm C. Nhưng jextract **không** đọc ngược machine code để chứng minh binary có cùng ABI với header.

Trong quy trình phát hành có ít nhất ba thực thể độc lập:

- **Public header (.h):** bản mô tả mà C compiler và jextract dựa vào để hiểu tên hàm, tham số, struct, typedef, macro và điều kiện tiền xử lý.
- **Generated Java bindings:** mã Java được jextract sinh từ header **ở một toolchain và target cụ thể**.
- **Native binary được phân phối:** file `.so`, `.dylib` hoặc `.dll` thực tế được đóng gói, tải vào JVM và thực thi.

```text
  [Release header + các header được include]
                  |
                  v
      jextract + JDK + libclang
      -I / -D / target platform
                  |
                  v
        Generated Java sources
                  |
                 javac
                  |
                  v
            Java application
                  |
                  v
     Load actual distributed .so/.dylib/.dll
                  |
                  v
         ABI + semantic smoke tests
```

Nếu header đổi nhưng bindings vẫn cũ, Java có thể tạo descriptor sai. Nếu bindings đã sinh lại từ header mới nhưng ứng dụng vẫn nạp binary cũ, code Java **vẫn có thể compile thành công**, thậm chí resolve được symbol cùng tên, rồi đọc sai field hoặc gọi native function với sai ABI.

**Quy tắc cốt lõi:** **khi hợp đồng header hoặc inputs sinh code thay đổi, tái sinh jextract từ đúng bộ header release; sau đó kiểm chứng trên đúng binary sẽ được phân phối cho khách hàng.** Không coi `jextract` thành công, `javac` thành công hay “symbol có tồn tại” là bằng chứng toàn diện về tính tương thích.

Bài này tập trung vào quy trình **regeneration và binary verification**, không dừng ở câu lệnh chạy jextract. Ta sẽ xây dựng một thư viện C mẫu có ABI-version/size/offset probes, một integration test Java gọi trực tiếp generated bindings và hai gate độc lập cho hash và exported symbols.

**Phiên bản Java:** FFM chuẩn được hoàn thiện trong **JDK 22** (JEP 454). `jextract` là công cụ **riêng**, không mặc định đi kèm mọi JDK; cần chọn bản tương thích với JDK và libclang/OS đích. Ví dụ `jextract`/FFM dùng JDK 22+, hai chương trình kiểm tra file được viết cho JDK 17+ (`BinaryExportGate` dùng FFM nên yêu cầu JDK 22+).

## 2. Ba lớp tương thích khác nhau

| Lớp | Điều cần khớp | Kiểm chứng đặc trưng |
| --- | --- | --- |
| **Source API** | Header, declarations, macros và kiểu Java sinh ra | Chạy jextract, compile toàn bộ generated code và handwritten wrapper |
| **Binary ABI** | Symbol, calling convention, độ rộng C types, layout, alignment, field offsets, pointer width | Kiểm export, đúng architecture, native `sizeof`/`offsetof` probes, ABI major |
| **Behavior/semantic** | Giá trị trả về, error reporting, memory ownership, callback behavior, thread safety | Smoke test với actual binary, negative/integration tests, release notes |

Hai headers có thể dùng tên hàm giống nhau nhưng struct layouts khác nhau. Ví dụ cấu trúc v2 và v3 đều dài 16 byte, nhưng field `total` đổi offset từ 8 sang 0. Kiểm tra symbol `demo_sum_record` hoặc `sizeof == 16` riêng lẻ không phát hiện khác biệt. Đặc biệt đối với C, exported symbol name thường **không encode đầy đủ prototype**.

Ngược lại, binary có thể giữ nguyên ABI nhưng thay đổi semantics: hàm trước đây trả milliseconds nay trả microseconds, hoặc một con trỏ `borrowed` chuyển thành `owned`. jextract không suy ra những quy tắc kinh doanh/vòng đời đó.

**Không trộn kết luận:** source-compatible chưa chắc ABI-compatible; ABI-compatible chưa chắc semantic-compatible; có sha256 khớp với một file nào đó cũng chưa chứng minh đó là artifact đúng release nếu nguồn expected hash chưa đáng tin.

## 3. Khi nào cần sinh lại?

Một thay đổi trực tiếp hoặc gián tiếp có thể làm generated Java sai:

1. Public `.h` đổi hàm, tham số, return type, constant, enum, typedef, struct/union, callback signature.
2. **Transitive header** được `#include` đổi dù header gốc không đổi.
3. `-D` macros hoặc `#ifdef` chọn declaration khác; `-I` include order tìm ra file khác.
4. Compiler flags/ABI đổi như `#pragma pack`, `-fpack-struct`, MSVC `/Zp`, calling convention, visibility.
5. Target OS hoặc CPU đổi: x86/x64/arm64, LP64 so với LLP64, `long`, `size_t`, pointer width.
6. JDK/jextract/libclang thay đổi có thể sinh mã hoặc layout khác.
7. SDK/sysroot/target headers, build compiler và ABI settings đổi.
8. Native binary được nâng cấp: **luôn chạy lại binary verification**; không nhất thiết phải regenerate nếu header/toolchain/ABI thật sự không đổi.
9. Semantic contract đổi dù prototype giữ nguyên: cập nhật handwritten wrappers/tests và xác minh release notes.

Chỉ đổi mtime của header mà không đổi tokens/configuration không nhất thiết phải tái sinh. Nên dựa trên **nội dung và dependency closure**, không chỉ timestamp. Tuy nhiên binary mới dù header vẫn giống vẫn phải được smoke test.

Hướng dẫn jextract chính thức lưu ý generated code **có thể phụ thuộc nền tảng**: quá trình preprocessing chọn nhánh khác và một số kiểu built-in như C `long` có kích thước khác nhau trên Windows và Linux. Nếu muốn phát hành một bộ bindings cho nhiều OS, phải kiểm tra generation layout trên từng platform rồi chứng minh portability.

## 4. Khóa toàn bộ đầu vào để regeneration có thể tái tạo

| Đối tượng | Thông tin nên pin |
| --- | --- |
| Public headers | Git tag/commit, SHA-256, toàn bộ transitive header closure |
| Native ABI | OS, architecture, toolchain, C compiler, target triple, packing, calling convention |
| Preprocessor | Chính xác danh sách `-I`, `-D`, sysroot, platform macros và include order |
| jextract | Phiên bản/build của generator, libclang version, cấu hình output/filter |
| Java toolchain | JDK compiler và runtime version tương thích generated FFM API |
| Native binary | File release candidate, version/SONAME, SHA-256, các shared dependencies |
| Kiểm thử | Required symbols, `sizeof`, `offsetof`, ABI major, primitive/struct behavior |
| Distribution | Bản package/container cuối cùng, đúng file được người dùng tải |

Chỉ ghi “chạy jextract demoabi.h” là thiếu. Ví dụ cùng tên `demoabi.h` nhưng một lần tìm `stdint.h` theo SDK khác, hoặc một lần có `-D FEATURE_X`, có thể tạo output khác.

**Expected digest phải đến từ signed hoặc trusted release manifest độc lập.** Tính sha256 trên file đang được kiểm tra rồi so lại với chính nó chỉ xác nhận phép tính hash, không chứng minh artifact là bản phát hành đúng.

## 5. Dự án C mẫu có ABI tự mô tả

Ta tạo thư viện `demoabi` với các exported native functions:

- `demo_abi_major()`: phiên bản ABI mà **binary đang chạy** thực hiện.
- `demo_record_size()`: `sizeof(struct DemoRecord)` do C compiler tính.
- `demo_total_offset()`: `offsetof(struct DemoRecord,total)` thực tế.
- `demo_add(int64_t,int64_t)`: kiểm tra primitive arguments và return.
- `demo_sum_record(const struct DemoRecord*)`: kiểm tra truyền pointer và layout các fields.

Bố trí thư mục:

```text
example/
  include/demoabi.h
  native/demoabi.c
  smoke/AbiSmoke.java
  smoke/BinaryExportGate.java
  smoke/ArtifactShaGate.java
  dist/include/demoabi.h           # header thực sự của release
  dist/native/libdemoabi.so        # Linux; macOS .dylib; Windows demoabi.dll
  build/generated/                # chỉ chứa code jextract sinh ra
  build/classes/
```

### 5.1. File `include/demoabi.h`

```c
#ifndef DEMOABI_H
#define DEMOABI_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(DEMOABI_BUILD)
#    define DEMOABI_API __declspec(dllexport)
#  else
#    define DEMOABI_API __declspec(dllimport)
#  endif
#else
#  define DEMOABI_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define DEMO_ABI_MAJOR 2

struct DemoRecord {
    int32_t id;
    int32_t flags;
    int64_t total;
};

DEMOABI_API int32_t demo_abi_major(void);
DEMOABI_API int32_t demo_record_size(void);
DEMOABI_API int32_t demo_total_offset(void);

DEMOABI_API int64_t demo_add(int64_t a, int64_t b);
DEMOABI_API int64_t demo_sum_record(
        const struct DemoRecord *record);

#ifdef __cplusplus
}
#endif

#endif
```

**Tại sao `int32_t`/`int64_t` thay vì `int`/`long`?** Kiểu cố định độ rộng hạn chế khác biệt giữa LP64 (thường Linux x64) và LLP64 (Windows x64). Tuy nhiên vẫn cần kiểm thử alignment, padding và calling convention. `DEMO_ABI_MAJOR` là constant header để generated Java so với **native runtime function**.

### 5.2. File `native/demoabi.c`

```c
#include "demoabi.h"
#include <stddef.h>
#include <stdint.h>

DEMOABI_API int32_t demo_abi_major(void) {
    return DEMO_ABI_MAJOR;
}

DEMOABI_API int32_t demo_record_size(void) {
    return (int32_t)sizeof(struct DemoRecord);
}

DEMOABI_API int32_t demo_total_offset(void) {
    return (int32_t)offsetof(struct DemoRecord, total);
}

DEMOABI_API int64_t demo_add(int64_t a, int64_t b) {
    return a + b;
}

DEMOABI_API int64_t demo_sum_record(
        const struct DemoRecord *record) {
    if (record == NULL) {
        return INT64_MIN;
    }

    return (int64_t)record->id
            + (int64_t)record->flags
            + record->total;
}
```

Với ABI 64-bit thông dụng, struct mẫu gồm hai số 32-bit rồi một số 64-bit; dự kiến `sizeof(DemoRecord)=16` và `offsetof(total)=8`. Nhưng **không thay các probe bằng con số dự đoán**: kiểm thử phải hỏi chính compiled native binary để phát hiện compiler flags/packing sai.

`INT64_MIN` cho null chỉ là quy ước hàm mẫu; một thư viện production cần định nghĩa rõ error semantics, ownership và giới hạn giá trị.

## 6. Biên dịch native binary mẫu trên các nền tảng

Đây là lệnh **minh họa** để tự build native artifact nếu có C compiler. Trong quy trình phát hành thật, binary được phân phối có thể đến từ vendor hoặc hệ thống release độc lập; phải test **file đó**, không tự thay bằng một build mới từ local header.

**Linux (GCC):**

```bash
mkdir -p dist/native dist/include build/generated build/classes
cp include/demoabi.h dist/include/demoabi.h

gcc -std=c11 -O2 -fPIC -shared \
  -DDEMOABI_BUILD -Iinclude \
  -o dist/native/libdemoabi.so native/demoabi.c
```

**macOS (Clang):**

```bash
mkdir -p dist/native dist/include build/generated build/classes
cp include/demoabi.h dist/include/demoabi.h

clang -std=c11 -O2 -dynamiclib \
  -DDEMOABI_BUILD -Iinclude \
  -o dist/native/libdemoabi.dylib native/demoabi.c
```

**Windows (Visual Studio Developer Command Prompt):**

```bat
mkdir dist
mkdir dist\native
mkdir dist\include
mkdir build
mkdir build\generated
mkdir build\classes

copy include\demoabi.h dist\include\demoabi.h
cl /nologo /LD /DDEMOABI_BUILD /Iinclude native\demoabi.c /Fe:dist\native\demoabi.dll
```

Cần đảm bảo đúng **C compiler/architecture** của release; ví dụ DLL x64 không chạy trong JVM x86. Nếu thư mục đã tồn tại, `mkdir` có thể cảnh báo; tổ chức pipeline idempotent theo công cụ build thực tế.

## 7. Chạy jextract bằng release header và đầu ra sạch

### 7.1. Kiểm tra toolchain

```bash
java -version
javac -version
jextract --version
```

`jextract` là chương trình ngoài JDK base; lấy bản tương thích tại dự án OpenJDK và kiểm tra yêu cầu libclang. Bản generator có thể thay đổi FFM API và cấu trúc generated classes theo JDK target; đừng trộn tùy tiện JDK hiện hành với bindings sinh từ generator không tương thích.

### 7.2. Command được hướng dẫn chính thức hỗ trợ

```bash
jextract \
  --include-dir dist/include \
  --output build/generated \
  --target-package edu.demoabi \
  --library demoabi \
  --use-system-load-library \
  dist/include/demoabi.h
```

Giải thích:

- `--include-dir`: nơi Clang tìm các headers phụ thuộc.
- `--output`: thư mục sinh các Java source files.
- `--target-package`: package của classes sinh.
- `--library demoabi`: native library tên logic `demoabi`.
- `--use-system-load-library`: generated code tải library chính qua `System.loadLibrary`/`java.library.path`; các phụ thuộc của library vẫn tuân theo OS loader.
- Đối số cuối: **header thực sự của distributed release**.

Các versions hiện hành thường sinh class `edu.demoabi.demoabi_h`, ngoài ra có class `edu.demoabi.DemoRecord` cho tagged struct. Trước khi viết handwritten wrapper, hãy kiểm tra file output vừa sinh để biết accessor names.

**Yêu cầu generation sạch:** tạo `build/generated` mới hoặc xóa đúng **thư mục generated được pipeline sở hữu** trước mỗi lần regenerate. Nếu không, một class sinh từ symbol đã bị xóa có thể tiếp tục tồn tại, làm build pass giả. Không xóa file handwritten hoặc release artifacts.

### 7.3. Nếu phải lọc symbols

Có thể dùng options:

```bash
jextract \
  --include-dir dist/include \
  --output build/generated \
  --target-package edu.demoabi \
  --library demoabi \
  --use-system-load-library \
  --include-function demo_abi_major \
  --include-function demo_record_size \
  --include-function demo_total_offset \
  --include-function demo_add \
  --include-function demo_sum_record \
  --include-struct DemoRecord \
  dist/include/demoabi.h
```

Tùy chọn `--include-*` giới hạn output theo tên symbol/struct. Với dự án phức tạp, nếu lọc mà thiếu declaration phụ thuộc, jextract có thể báo lỗi. Đối với smoke ABI toàn bộ mẫu, lệnh **không lọc** trong mục 7.2 đơn giản và ít nguy cơ bỏ sót hơn.

`jextract --dump-includes` hữu ích nếu muốn xuất danh sách symbols và quản lý filter qua argfile được version control. Tuy nhiên đừng chỉ filter symbols mới rồi bỏ qua một struct phụ thuộc.

### 7.4. Version control và reproducibility

Có hai chiến lược hợp lý:

- **Commit generated Java:** PR đổi header kèm regeneration diff; CI tái sinh cùng toolchain rồi xác nhận output không khác bất ngờ.
- **Không commit generated Java:** CI phải generate từ toolchain/headers đã pin trong mỗi build và lưu/generated sources trong artifact; cache phải invalidated khi bất kỳ generator input nào đổi.

Trong cả hai trường hợp, **không sửa tay generated file rồi coi nó là nguồn sự thật**. Đặt rules nâng cao, validations hoặc abstractions ở handwritten Java wrapper; nếu cần cải thiện cách sinh, thay headers/configuration/tooling tương ứng.

## 8. Kiểm tra ABI từ generated Java trước khi gọi native code có struct

Bốn tầng preflight:

1. Compiled header ABI major == binary runtime ABI major.
2. `DemoRecord.sizeof()` == `demo_record_size()`.
3. `DemoRecord.total$offset()` == `demo_total_offset()`.
4. Export symbol có mặt và primitive/struct smoke test trả kết quả đúng.

### 8.1. File `smoke/AbiSmoke.java`

Jextract guide mô tả generated header class `demoabi_h` với accessor cho functions/macros và generated struct class `DemoRecord` với `sizeof()`, `total$offset()` và field getters/setters. Mã dưới đây nhắm vào API conventions ấy; kiểm chứng tên thực tế trong **generated Java của chính version jextract đang dùng**.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

import edu.demoabi.DemoRecord;
import static edu.demoabi.demoabi_h.*;

public class AbiSmoke {
    public static void main(String[] args) {
        int expectedMajor = DEMO_ABI_MAJOR();
        int actualMajor = demo_abi_major();

        if (actualMajor != expectedMajor) {
            throw new IllegalStateException(
                    "ABI version mismatch: header=" + expectedMajor
                    + ", binary=" + actualMajor);
        }

        long generatedSize = DemoRecord.sizeof();
        int binarySize = demo_record_size();

        if (generatedSize != binarySize) {
            throw new IllegalStateException(
                    "Size mismatch: header=" + generatedSize
                    + ", binary=" + binarySize);
        }

        long generatedOffset = DemoRecord.total$offset();
        int binaryOffset = demo_total_offset();

        if (generatedOffset != binaryOffset) {
            throw new IllegalStateException(
                    "Offset mismatch: header=" + generatedOffset
                    + ", binary=" + binaryOffset);
        }

        long add = demo_add(7L, 9L);
        if (add != 16L) {
            throw new IllegalStateException(
                    "Primitive ABI mismatch: " + add);
        }

        long sum;
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = DemoRecord.allocate(arena);
            DemoRecord.id(record, 5);
            DemoRecord.flags(record, 2);
            DemoRecord.total(record, 11L);

            sum = demo_sum_record(record);
        }

        if (sum != 18L) {
            throw new IllegalStateException(
                    "Struct ABI mismatch: " + sum);
        }

        System.out.println("ABI major: " + actualMajor);
        System.out.println("Record sizeof: " + binarySize);
        System.out.println("Total offset: " + binaryOffset);
        System.out.println("Add: " + add);
        System.out.println("Sum: " + sum);
    }
}
```

**Điểm thiết kế quan trọng:** `AbiSmoke` kiểm tra ABI major/size/offset **trước khi** cấp phát và truyền `DemoRecord` qua native boundary. Nếu đã biết header/binary khác nhau, fail ngay trong Java thay vì mạo hiểm đọc sai bytes.

### 8.2. Biên dịch tất cả generated sources và smoke

Trên Linux/macOS:

```bash
find build/generated -type f -name '*.java' > build/generated-sources.txt
printf '%s\n' smoke/AbiSmoke.java >> build/generated-sources.txt

javac -d build/classes @build/generated-sources.txt

java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path="$(pwd)/dist/native" \
  -cp build/classes AbiSmoke
```

Trên Windows PowerShell:

```powershell
$generated = Get-ChildItem build\generated -Recurse -Filter *.java |
    ForEach-Object { $_.FullName }

javac -d build\classes $generated smoke\AbiSmoke.java

$nativeDir = (Resolve-Path dist\native).Path
java --enable-native-access=ALL-UNNAMED "-Djava.library.path=$nativeDir" -cp build\classes AbiSmoke
```

**Stdout dự kiến** khi binary mẫu được build đúng như C source, có ABI major 2 và fields khớp:

```text
ABI major: 2
Record sizeof: 16
Total offset: 8
Add: 16
Sum: 18
```

**Phân biệt kiểm chứng và kỳ vọng:** test integration `AbiSmoke` yêu cầu cả `jextract` **và native binary demoabi**. Nếu máy chỉ có JDK mà không có jextract/C compiler, không thể chạy trọn demo. Output trên là kết quả **dự kiến theo C implementation**, phải được xác nhận trong CI của từng release/platform, không được mô tả như một execution đã diễn ra nếu chưa chạy.

### 8.3. Ba probe không chứng minh mọi ABI contract

ABI probes cũng phải có prototype/ABI ổn định, và chỉ so những điều được đo:

- Chúng không tự phát hiện mọi enum width, bitfield packing, nested structure, callback calling convention hoặc error semantics.
- Native binary có thể export đúng probe names nhưng chính prototype của probes đã thay đổi; do đó phải dùng manifest version và kiểm tra baseline trước.
- Một library khác version có thể có cùng `sizeof` và `offsetof` nhưng logic business đã đổi.
- ABI mismatch có thể gây crash trước khi probe chạy nếu import prototype sai nghiêm trọng.
- Với API có con trỏ và ownership, cần smoke test release handles và error paths ngoài kiểm tra layout.

Kiểm tra ABI giúp fail-fast và giảm nguy cơ, **không biến mọi FFM downcall thành memory-safe nếu C contract sai**.

## 9. Đảm bảo đúng file binary đang được nạp

### 9.1. Lỗi nạp nhầm phiên bản

Thử nghiệm trên `dist/native/libdemoabi.so` không có giá trị nếu production lại nạp `/usr/local/lib/libdemoabi.so` cũ. Ngược lại, nếu generated code dùng `--library demoabi` mà không `--use-system-load-library`, native OS lookup có thể không tuân theo `java.library.path`.

Cần biết chính xác cơ chế load:

- Theo OpenJDK jextract guide, `--library name` thông thường dùng cơ chế native loader/`SymbolLookup.libraryLookup`; dependency lookup phụ thuộc OS.
- `--use-system-load-library` chuyển library chính sang `System.loadLibrary` và tìm qua `java.library.path`. **Thư viện phụ thuộc** vẫn có thể phải tìm theo OS PATH/RPATH/LD_LIBRARY_PATH.
- `--library :/absolute/path/libdemoabi.so` có thể yêu cầu một path cụ thể, phù hợp môi trường test nhưng không portable nếu hardcode path dev.
- Dùng `-Xlog:library` trên HotSpot khi cần điều tra actual load. Log chỉ là bằng chứng hỗ trợ; nên kết hợp SHA-256/hash manifest.
- Khi đóng gói, hãy kiểm tra lại hash **sau** copy/compression/extraction hoặc trước publish và trong môi trường installation test.

### 9.2. Xem export và dependencies bằng công cụ OS

**Linux/ELF:**

```bash
nm -D --defined-only dist/native/libdemoabi.so
readelf -h dist/native/libdemoabi.so
readelf -d dist/native/libdemoabi.so
```

**macOS/Mach-O:**

```bash
nm -gU dist/native/libdemoabi.dylib
otool -L dist/native/libdemoabi.dylib
file dist/native/libdemoabi.dylib
```

**Windows/PE (MSVC Developer Command Prompt):**

```bat
dumpbin /exports dist\native\demoabi.dll
dumpbin /headers dist\native\demoabi.dll
dumpbin /dependents dist\native\demoabi.dll
```

Các exports của library mẫu:

```text
demo_abi_major
demo_record_size
demo_total_offset
demo_add
demo_sum_record
```

Trên macOS, `nm` có thể hiển thị dấu gạch dưới dẫn đầu theo conventions của Mach-O. Ngoài tên symbol, kiểm tra architecture, linking dependencies, soname/install name và version.

**Giới hạn:** có symbol không bảo đảm prototype đúng. Với một số C ABI, tên symbol không encode kiểu tham số, nên thay `int32_t` thành `int64_t` vẫn có thể giữ export cũ và gây lỗi khi gọi.

## 10. Java độc lập: BinaryExportGate kiểm tra exports của đúng file

Đây là chương trình **JDK 22+** kiểm tra library tại **đường dẫn chỉ định**, không cần jextract-generated code. Nó chỉ kiểm tra export availability, không gọi các hàm đó.

### 10.1. File `smoke/BinaryExportGate.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.SymbolLookup;
import java.nio.file.Path;

public final class BinaryExportGate {
    public static void main(String[] args) {
        if (args.length < 2) {
            throw new IllegalArgumentException(
                    "Usage: BinaryExportGate absoluteLibraryPath "
                    + "export1 [export2 ...]");
        }

        Path library = Path.of(args[0]).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    library, arena);

            for (int i = 1; i < args.length; i++) {
                String symbol = args[i];

                if (lookup.find(symbol).isEmpty()) {
                    throw new IllegalStateException(
                            "Missing export: " + symbol);
                }

                System.out.println("Export present: " + symbol);
            }
        }
    }
}
```

**Build/run Linux với đúng library phân phối:**

```bash
javac -d build/classes smoke/BinaryExportGate.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes \
  BinaryExportGate "$(pwd)/dist/native/libdemoabi.so" \
  demo_abi_major demo_record_size demo_total_offset demo_add demo_sum_record
```

Trên macOS/Windows dùng path `.dylib`/`.dll` tương ứng. Nếu missing export, gate throw `IllegalStateException` và CI exit code khác 0. Nếu library không load được vì sai architecture/dependency, lookup thất bại sớm.

**Thử nghiệm đã thực hiện trên JDK 24 Windows:** chương trình biên dịch/chạy với `kernel32.dll`, xác nhận các exports thật `GetCurrentProcessId`, `GetFileAttributesW`; cố ý tìm một symbol không có đã tạo failure mong đợi. Vì máy thử không có C compiler, **chưa chạy BinaryExportGate trên chính demoabi.dll mẫu**. Gate này là một lớp bảo vệ bổ sung; `AbiSmoke` vẫn bắt buộc.

## 11. Java độc lập: kiểm tra SHA-256 của header và binary

`ArtifactShaGate` chạy bằng **JDK 17+**, không phụ thuộc jextract hay FFM. Nó chỉ xác nhận bytes của hai files khớp SHA-256 từ **manifest đáng tin**.

### 11.1. File `smoke/ArtifactShaGate.java`

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class ArtifactShaGate {
    private static String sha256(Path path) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");

        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int n;

            while ((n = in.read(buffer)) != -1) {
                hash.update(buffer, 0, n);
            }
        }

        return HexFormat.of().formatHex(hash.digest());
    }

    private static void check(
            String label, String file, String expected) throws Exception {
        String actual = sha256(Path.of(file));

        if (!actual.equalsIgnoreCase(expected)) {
            throw new IllegalStateException(
                    label + " SHA-256 mismatch");
        }

        System.out.println(label + " hash: OK");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactShaGate header expectedHeaderSha256 "
                    + "library expectedLibrarySha256");
        }

        check("Header", args[0], args[1]);
        check("Binary", args[2], args[3]);
    }
}
```

**Trong Linux CI**, hai biến môi trường lấy từ trusted release manifest, không lấy từ việc vừa tính hash cùng files:

```bash
javac -d build/classes smoke/ArtifactShaGate.java

java -cp build/classes ArtifactShaGate \
  dist/include/demoabi.h "$EXPECTED_HEADER_SHA256" \
  dist/native/libdemoabi.so "$EXPECTED_LIBRARY_SHA256"
```

**Stdout khi cả hai checksum khớp:**

```text
Header hash: OK
Binary hash: OK
```

Nếu một digest sai, gate ném `IllegalStateException` và trả exit code khác 0. **Test thực tế đã chạy trên JDK 24:** cả positive (hai hashes đúng) và negative (hash header bị thay sai) được xác nhận bằng những fixture files độc lập. Không diễn giải phép thử fixture thành đã xác thực bộ demoabi của vendor.

### 11.2. SHA-256 không có nghĩa là ABI tương thích

Hai file có hashes khớp manifest có thể vẫn là một **cặp phát hành sai** nếu manifest sai hoặc không được xác thực. Hash kiểm **đúng bytes**, không kiểm function signature, compiler ABI, export semantics hay khả năng chạy. Kết hợp với signature/provenance, đúng native binary loading, export inspection, ABI probes và behavior tests.

## 12. Ví dụ breaking change: header v3 với binary v2

Bản v2 có:

```c
#define DEMO_ABI_MAJOR 2
struct DemoRecord {
    int32_t id;
    int32_t flags;
    int64_t total;   /* offset 8 */
};
```

Bản v3 (khác ABI) có thể đổi thành:

```c
#define DEMO_ABI_MAJOR 3
struct DemoRecord {
    int64_t total;  /* offset 0 */
    int32_t id;
    int32_t flags;
};
```

Trên ABI 64-bit thông dụng, cả hai struct vẫn có thể dài **16 byte**, và binary v2 vẫn có thể export đầy đủ các tên functions. Kết quả có thể là:

- `jextract` sinh `DemoRecord.total$offset() == 0` từ header v3.
- `javac` biên dịch Java dùng generated class v3 thành công.
- Binary v2 thực thi `demo_abi_major() == 2` và `demo_total_offset() == 8`.
- `AbiSmoke` gặp **ABI major mismatch** trước khi dereference struct.
- Nếu vendor quên tăng version macro, phép so **offset** vẫn phát hiện mismatch dù `sizeof` giống nhau.

Đây là lý do **export-only** và **size-only** tests không đủ. Nếu Java cố gọi `demo_sum_record` bằng layout mới trên binary cũ, native code có thể đọc field sai, trả kết quả sai và trong trường hợp nghiêm trọng gây memory corruption.

**Header không đổi, binary đổi** thì sao? Không nhất thiết regenerate bindings khi inputs thật sự không đổi, nhưng phải run lại export check, digest check và native behavior smoke trên binary mới. Những lỗi thay đổi semantics không tự biểu hiện qua header diff.

## 13. Các ABI hazards cần rà soát khi review regeneration

### 13.1. Struct packing và alignment

`#pragma pack`, GCC/Clang attributes và MSVC `/Zp` có thể đổi offset hoặc alignment dù field names không đổi. Với structs có nested fields, unions hoặc pointers, chỉ kiểm `sizeof` của struct ngoài cũng có thể thiếu. Dùng probes `sizeof`/`_Alignof`/`offsetof` ở những type fields quan trọng và so với jextract-generated layouts.

### 13.2. Native type widths theo OS/architecture

Trên x64 Windows, C `long` thường 32-bit (LLP64), trong khi trên x64 Linux nó thường 64-bit (LP64). `size_t`, `wchar_t` và pointer width cũng khác theo platform. Dùng `int32_t`/`int64_t` có thể tăng portability nhưng **không thay thế** kiểm thử ABI.

### 13.3. C++ mangled symbols và calling convention

Nếu thư viện viết C++, nên cung cấp lớp C-compatible exported wrapper `extern "C"` khi jextract cần xử lý C headers. Trên một số ABI như Windows x86, `__stdcall`/`__cdecl` và symbol decoration khác nhau. Không mặc định `demo_add` cùng tên là có cùng calling convention và parameter passing.

### 13.4. Opaque pointers và ownership

Một hàm C giữ prototype `void* get_resource()` nhưng đổi contract từ “borrowed pointer” sang “caller phải free” sẽ không tự khiến jextract báo sai. Wrapper Java cần được cập nhật để gọi **đúng destructor**, tránh double-free và use-after-free. Bài test chỉ kiểm return number không phát hiện lỗi vòng đời.

### 13.5. Callbacks và function pointers

Một callback đổi signature hoặc thread rules có thể gây JVM crash dù native function symbol chính vẫn tồn tại. CI cần kiểm callback upcall/downcall và lifetime của `Arena` chứa stub, cũng như error policy.

### 13.6. Unsupported C constructs

jextract hiện không hỗ trợ đầy đủ tất cả C constructs; guide mô tả các trường hợp như function-like macros, bitfields, opaque declarations và một số kiểu không phổ biến. Phải review warnings và generated API coverage. Nếu cần, tạo exported C wrapper functions hoặc handwritten Java/FFM glue thay vì im lặng bỏ declarations.

## 14. Quy trình CI/CD đề xuất

Một pipeline cho **từng OS/architecture được hỗ trợ**:

```text
1. Fetch headers + binaries + dependencies from a trusted release.
2. Verify signed manifest / checksums of exact staged artifacts.
3. Record JDK, jextract, Clang, compiler flags, OS and CPU ABI.
4. Regenerate bindings from the release header set in a CLEAN dir.
5. Compare generated output against expected API/layout baseline.
6. Compile all generated Java and handwritten wrappers.
7. Inspect native binary format, arch, deps and required symbols.
8. Run ABI major/sizeof/offsetof checks on staged binary.
9. Run primitive and struct smoke calls, then ownership/error tests.
10. Package the same tested binary + bindings/dependencies.
11. Recheck hashes of packaged artifact before release.
12. Publish only if all gates pass.
```

**Tại sao thứ tự này?** Nếu ABI sai, không nên gọi hàm native phức tạp trước khi có probe; nếu binary hash sai, không nên coi smoke test với nó là evidence về release chính thức; nếu package lại copy nhầm DLL/so, test trước package chưa chứng minh end-user sẽ nhận đúng binary.

Với CI matrix có thể tách:

| Nền tảng | Library | Công cụ xuất symbols / deps | Nguy cơ |
| --- | --- | --- | --- |
| Linux x86_64 / arm64 | `libdemoabi.so` | `nm -D`, `readelf` | ELF architecture, glibc/deps, LP64 |
| macOS x86_64 / arm64 | `libdemoabi.dylib` | `nm -gU`, `otool -L` | Mach-O slices/install name |
| Windows x64 | `demoabi.dll` | `dumpbin /exports`, `/dependents` | PE architecture, CRT, LLP64 |

Nếu dự án chỉ hỗ trợ một platform, test đúng platform ấy và nêu support matrix trung thực; không tuyên bố portable nếu chưa kiểm chứng.

### Bảo vệ khỏi generated files cũ

Nếu commit generated Java, CI có thể chạy regeneration cùng toolchain rồi so diff với bản đã commit. Nếu không commit, build phải invalidated cache theo header closure/generator flags/JDK. Tránh trộn class cũ và class mới trong một output directory.

Một warning từ jextract do thiếu typedef hoặc unsupported declaration không được bỏ qua chỉ vì compilation vẫn chạy. So danh sách exported functions dự định dùng với danh sách methods generated và baseline tests.

### Kiểm thử âm tính có giá trị

- Cố tình ghép header v3 với binary v2: ABI major hoặc offset test **phải fail**.
- Bỏ một required symbol khỏi binary test fixture: `BinaryExportGate` **phải fail**.
- Thay một byte trong header fixture hoặc binary fixture: `ArtifactShaGate` **phải fail**.
- Kiểm thử loader trên môi trường có **hai versions cùng tên** và bảo đảm chỉ exact packaged binary được nạp.
- Đổi một `-D` macro ảnh hưởng struct để chắc build nhận ra generated output/layout changed.
- Đổi arch/ABI không tương thích và bảo đảm release pipeline từ chối.

Không tạo test thực thi pointer sai layout **sau khi đã biết ABI mismatch** chỉ để xem JVM có crash không; fail-fast là cách kiểm thử an toàn hơn.

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy lệnh `jextract` | Chưa cài tool ngoài JDK/PATH sai | Cài đúng build và kiểm `jextract --version` |
| Generated code không compile trên JDK hiện tại | jextract targets API FFM khác/JDK không khớp | Pin generator + JDK tương thích |
| Header gốc không đổi nhưng code gen đổi | Transitive header, macros, Clang/SDK/target khác | So preprocessor inputs và toolchain |
| Biểu tượng Java cũ vẫn compile dù C header xóa function | Thư mục generated không được clean | Sinh vào output mới, clean compile |
| `NoSuchElementException` lúc resolve function | Missing symbol hoặc load nhầm version | Inspect exports và exact loaded library |
| `UnsatisfiedLinkError`/load failure | Sai OS/architecture/dependency/path | Kiểm ELF/PE/Mach-O và OS search paths |
| `ABI major mismatch` | Header/binary release pair không tương ứng | Chặn launch, lấy đúng artifact version |
| Struct size đúng nhưng offset sai | Reordered fields, packing hoặc compiler flags | So offset probes và generated layout |
| Exports đủ nhưng call trả sai | ABI types, calling convention hoặc semantic regression | Kiểm descriptor, native function behavior |
| JVM crash | Sai native pointer/layout/prototype/lifetime | Dừng, phân tích crash log + native sanitizer |
| Local smoke pass nhưng package fail | Copy nhầm binary/dependency hoặc dynamic lookup path | Verify packaged hashes và thực tế loader |
| CI Windows pass, Linux fail | LLP64/LP64, preprocessing, version lib khác | Chạy jextract + smoke theo từng platform |

**Ghi nhớ:** tải được thư viện không có nghĩa ABI đúng. OS loader không xác nhận struct field offsets, function return conventions hoặc memory ownership. Không sửa một mismatch bằng cách tắt bounds checks hay cast pointer bừa.

## 16. Bài tập tự kiểm tra

**Câu 1.** `jextract` chạy thành công và `javac` không báo lỗi. Tại sao vẫn cần smoke với binary?

**Đáp án:** jextract sinh bindings từ header, javac kiểm Java source; không bên nào bảo đảm binary thực tế có cùng symbols, ABI/layout hoặc semantics. Cần chạy với exact distributed binary.

**Câu 2.** Một header thêm field vào struct nhưng không đổi exported function name. Có cần regenerate không?

**Đáp án:** Có nếu thay public ABI; phải sinh lại, kiểm tra layout offsets và phát hành binary phù hợp. Tên function không đủ.

**Câu 3.** Vì sao cần `demo_total_offset` bên cạnh `demo_record_size`?

**Đáp án:** Struct v2/v3 có thể cùng `sizeof == 16` nhưng field `total` chuyển từ offset 8 sang 0. Chỉ test size không phát hiện được.

**Câu 4.** Binary mới và header không đổi, có cần luôn regenerate bindings không?

**Đáp án:** Không nhất thiết khi toàn bộ generator inputs/ABI không đổi, nhưng bắt buộc test binary mới, exported symbols, dependencies và semantics.

**Câu 5.** `--library demoabi` có bảo đảm nạp binary trong `dist/native` không?

**Đáp án:** Không. Loader phụ thuộc OS và cấu hình jextract; với `--use-system-load-library` có thể chỉ định `java.library.path` cho main library, nhưng dependencies vẫn có luật OS riêng.

**Câu 6.** Hash của header/binary khớp một manifest do chính máy vừa tạo từ những file đang kiểm tra. Đã chứng minh release đúng chưa?

**Đáp án:** Chưa. Expected hashes phải đến từ trusted manifest/signature độc lập; tự so một file với hash vừa tính không xác nhận provenance.

**Câu 7.** `DemoRecord.sizeof() == demo_record_size()`. Có thể bỏ các test khác?

**Đáp án:** Không. Cần version, offset, symbol, signature, semantics, ownership; size khớp không chắc offsets khớp.

**Câu 8.** Windows x64 và Linux x64 đều 64-bit. Có thể luôn dùng chung C `long` layout không?

**Đáp án:** Không. Windows x64 thường LLP64, Linux x64 LP64. C `long` và `size_t` cần được xác minh theo target ABI; dùng fixed-width types khi thích hợp.

**Câu 9.** Lưu generated sources trong repo có nghĩa không cần jextract trên CI nữa?

**Đáp án:** Để kiểm tra source regeneration có đúng, CI vẫn nên chạy generator đã pin và đối chiếu diff. Nếu muốn không regenerate trên mọi build, ít nhất cần một gate tái sinh khi inputs có thay đổi.

**Câu 10.** Vì sao `BinaryExportGate` không đủ chứng minh ABI?

**Đáp án:** Nó chỉ xác nhận file tải được và có tên symbol. C function prototypes/layout có thể sai dù cùng tên.

**Câu 11.** Khi gặp `NoSuchElementException` ở generated binding, nên bắt exception rồi tiếp tục gọi native bằng pointer khác không?

**Đáp án:** Không. Kiểm tra binary version, exported symbols và load path. Đó có thể là mismatch phát hành, nên fail-fast thay vì đoán tên/địa chỉ hàm.

**Câu 12.** Test về ownership có cần thiết nếu ABI major/offset/size đều khớp?

**Đáp án:** Có. `void*`/callback có thể giữ nguyên signature nhưng đổi borrowed/owned semantics, yêu cầu thread hoặc thời gian sống; jextract không xác minh được.

## 17. Tóm tắt

- **Tái sinh jextract** khi public header, transitive includes, macros, compiler ABI, target platform hoặc generator inputs đổi.
- **Kiểm chứng native binary** với mỗi artifact phát hành, dù header không đổi.
- **Kiểm chứng đúng file:** trusted SHA-256, đúng OS/arch/loader/dependencies, không nạp nhầm thư viện cùng tên.
- **Đừng chỉ kiểm compilation hoặc exports:** so header vs runtime ABI major, `sizeof`, `offsetof`, calling convention và kết quả hàm.
- **Sinh code vào thư mục sạch**, pin jextract/JDK/libclang, review diff/generated warnings.
- **Bắt lỗi trước khi dereference** struct hoặc dùng pointer có ABI chưa được xác nhận.
- **Smoke trên chính binary được ship**, rồi verify lại package. Điều này nối public header, Java binding và binary thành một bộ release có thể kiểm chứng.

## Tài liệu tham khảo chính thức

- [OpenJDK jextract — hướng dẫn chi tiết và command-line options](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md)
- [OpenJDK jextract — source, release và hướng dẫn build](https://github.com/openjdk/jextract)
- [dev.java — Generate Java Bindings with jextract](https://dev.java/learn/ffm/jextract/)
- [Oracle Java SE 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html)
- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 24 — MemoryLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 24 — SymbolLookup](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Microsoft Learn — Inspecting DLL exports](https://learn.microsoft.com/en-us/cpp/build/reference/exports?view=msvc-170)

**Kết luận:** jextract chỉ đồng bộ Java với **khai báo trong header**. Bước còn lại là chứng minh chính **binary phân phối** thực hiện hợp đồng đó: ABI version, offsets, exports, dependencies, owner/lifetime và semantic tests. Chỉ khi cả hai chiều được kiểm chứng, bindings mới đáng tin cậy cho production.
