# Sinh liên kết bằng jextract rồi thêm lớp bao kiểm tra hợp đồng

## Mục tiêu và sản phẩm thực hành

Bài thực hành này xây dựng một thư viện C rất nhỏ, dùng **jextract** sinh Java binding từ file header `.h`, sau đó viết một **lớp bao Java do mình quản lý** để kiểm tra hợp đồng (*contract*) trước và sau khi gọi native. Cách làm áp dụng khi tích hợp thư viện C hoặc C ABI của C++ qua Foreign Function & Memory API (FFM).

Sau khi thực hiện, bạn cần có:

1. Thư viện native `labmath` với một hàm tính tổng mảng số nguyên và hợp đồng lỗi tường minh.
2. Các binding được **jextract sinh tự động** từ `labmath.h`, có thể gọi hàm C bằng `MemorySegment`.
3. Lớp `LabMath` nhận `int[]` thông thường, kiểm tra đầu vào/ABI, cấp phát và đóng bộ nhớ native, xử lý mã lỗi, trả về `long`.
4. Chương trình `Main` chứng minh kết quả và kiểm tra biên lỗi, cộng với một lời gọi raw để xác nhận hợp đồng C.
5. Checklist để phân biệt lỗi của header/binary, lỗi loader, lỗi dữ liệu, lỗi về ownership và sai khác giữa binding thô với public API Java.

**Tại sao phải có lớp bao?** jextract giải quyết phần cơ học của ABI: nhận diện function, type, layout, symbol và xây dựng downcall. Nó **không biết** chính sách nghiệp vụ: mảng tối đa bao nhiêu phần tử, `NULL` có được phép không, buffer do ai sở hữu, có thể gọi sau `close` không, mã trả về nào là lỗi, và Java API nên ném exception hay trả result. Hợp đồng đó thuộc **lớp bao**, dựa trên tài liệu C của thư viện.

> **Yêu cầu phiên bản:** dùng **JDK 22+** vì FFM trở thành API chính thức từ JDK 22. Chọn bản jextract tương thích với JDK đang dùng và xác minh bằng `jextract --version`. jextract là công cụ riêng của dự án OpenJDK, không mặc nhiên nằm trong mọi bản JDK. Ví dụ minh họa cho Linux dùng compiler C (`cc`) và shell POSIX; có hướng dẫn điều chỉnh Windows/macOS phía sau.

## 1. Hợp đồng đầu tiên: bắt đầu từ C ABI rõ ràng

Chúng ta chọn API cực nhỏ để dễ quan sát:

```c
int32_t labmath_abi_version(void);
int32_t labmath_sum(const int32_t *values,
                    int32_t count,
                    int64_t *out_sum);
```

Hợp đồng `labmath_sum`:

- `count` nằm trong khoảng **0..4096**, tính cả hai đầu.
- Nếu `count > 0`, `values` phải trỏ tới ít nhất `count` phần tử `int32_t` có thể đọc trong suốt lời gọi.
- Khi `count == 0`, `values == NULL` hợp lệ và tổng bằng 0.
- `out_sum` bắt buộc không `NULL` và trỏ tới ít nhất một `int64_t` có thể ghi.
- Khi thành công, hàm trả `LABMATH_OK == 0` và ghi `*out_sum`. Khi lỗi, trả mã khác 0 và **giữ nguyên `*out_sum`**.
- C **không giữ** các pointer sau khi hàm trả về; cũng không tự cấp phát/giải phóng dữ liệu đầu vào hoặc buffer đầu ra.
- C không tạo worker thread hoặc callback; toàn bộ native access hoàn thành đồng bộ trước khi Java đóng `Arena`.
- `labmath_abi_version()` trả phiên bản ABI mà binary thực sự cung cấp; giá trị này được so với hằng trong header dùng để sinh binding.

Với tối đa 4096 số nguyên có dấu 32-bit, tổng nằm an toàn trong `int64_t`. Ta cố ý trả kiểu 64-bit để tránh overflow của tổng `int32_t`. Đây là quyết định hợp đồng, không phải một tính năng jextract tự suy luận.

| Thứ cần bảo vệ | Binding thô nhìn thấy | Lớp bao phải làm |
| --- | --- | --- |
| `values` | `MemorySegment`, có thể là NULL hoặc segment sai kích thước | Nhận `int[]`, kiểm tra null/độ dài, tạo segment đủ byte |
| `count` | `int` truyền nguyên xi tới C | Không để vượt 4096 hoặc không khớp số phần tử |
| `out_sum` | `MemorySegment` trỏ vào nơi ghi | Tự cấp phát 8 byte đúng alignment, chỉ đọc sau success |
| Return code | `int` do C trả về | Chuyển lỗi thành exception giữ nguyên mã |
| Version | Function và macro sinh từ header | So bản header với binary trước khi dùng |
| Lifetime | Pointer chỉ là một địa chỉ | Dùng `try (Arena ...)` và bảo đảm C không giữ pointer |
| Library | Symbol được jextract liên kết từ binary | Đóng gói đúng OS/arch/ABI và kiểm tra loader |

## 2. Tạo thư mục ví dụ

Cấu trúc sau là **một project thực hành độc lập**. Bạn có thể tạo ở bất kỳ thư mục làm việc phù hợp nào; các lệnh sau được chạy từ root của thư mục này.

```text
labmath-lab/
├── native/
│   ├── labmath.h
│   └── labmath.c
├── src/
│   └── demo/
│       ├── LabMath.java          # viết tay, thuộc public API
│       └── Main.java             # chương trình kiểm thử
└── build/
    ├── native/                   # liblabmath.so, do C compiler tạo
    ├── generated/                # demo/raw/*.java, do jextract tạo
    └── classes/                  # Java class, do javac tạo
```

Không sửa mã trong `build/generated` bằng tay. Khi header thay đổi, chạy lại jextract. Để bảo đảm khả năng tái tạo, lưu lại phiên bản jextract/JDK, compiler target, cờ sinh binding và checksum hoặc phiên bản header/native binary trong quy trình build.

## 3. Viết header C chứa hợp đồng

Tạo `native/labmath.h`:

```c
#ifndef LABMATH_H
#define LABMATH_H

#include <stdint.h>

/* Windows: export khi build DLL, import khi ứng dụng sử dụng. */
#if defined(_WIN32)
  #if defined(LABMATH_BUILD)
    #define LABMATH_API __declspec(dllexport)
  #else
    #define LABMATH_API __declspec(dllimport)
  #endif
#else
  #define LABMATH_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define LABMATH_ABI_VERSION 1
#define LABMATH_MAX_COUNT   4096

#define LABMATH_OK          0
#define LABMATH_ERR_NULL    1
#define LABMATH_ERR_RANGE   2

/*
 * Trả phiên bản C ABI của binary đã được nạp.
 */
LABMATH_API int32_t labmath_abi_version(void);

/*
 * values: borrowed, tối thiểu count int32_t nếu count > 0.
 * count: 0..4096; values có thể NULL khi count == 0.
 * out_sum: borrowed, writable int64_t, không được NULL.
 *
 * Thành công: trả 0, ghi out_sum.
 * Thất bại: trả LABMATH_ERR_*, KHÔNG thay đổi out_sum.
 * Hàm đồng bộ; không giữ pointer sau khi trả về.
 */
LABMATH_API int32_t labmath_sum(
    const int32_t *values,
    int32_t count,
    int64_t *out_sum);

#ifdef __cplusplus
}
#endif

#endif
```

Các loại `int32_t`/`int64_t` tránh phụ thuộc kích thước `long` trong C (thay đổi theo nền tảng). Khi dùng jextract với một header thực tế, kiểm tra thêm struct packing, alignment, calling convention, typedef, pointer ownership và compile flags. Các hàm C++ có name mangling cần một lớp `extern "C"` hoặc C ABI thật; jextract không tự diễn giải toàn bộ mô hình object/method của C++.

Hằng `LABMATH_ABI_VERSION` là hợp đồng do chúng ta thiết kế. jextract không thể tự xác thực ABI của một binary khác phiên bản header. Bởi vậy cần một function runtime `labmath_abi_version`.

## 4. Viết thư viện C triển khai đúng hợp đồng

Tạo `native/labmath.c`:

```c
#include "labmath.h"
#include <stddef.h>

int32_t labmath_abi_version(void) {
    return LABMATH_ABI_VERSION;
}

int32_t labmath_sum(
        const int32_t *values,
        int32_t count,
        int64_t *out_sum) {

    if (out_sum == NULL) {
        return LABMATH_ERR_NULL;
    }
    if (count < 0 || count > LABMATH_MAX_COUNT) {
        return LABMATH_ERR_RANGE;
    }
    if (count > 0 && values == NULL) {
        return LABMATH_ERR_NULL;
    }

    int64_t total = 0;
    for (int32_t i = 0; i < count; ++i) {
        total += (int64_t) values[i];
    }

    *out_sum = total;     /* chỉ ghi sau khi qua toàn bộ validation */
    return LABMATH_OK;
}
```

Giải thích các chi tiết có chủ ý:

1. Kiểm tra `out_sum` trước khi dereference.
2. Kiểm tra count âm/quá lớn **trước khi** truy cập phần tử.
3. `values == NULL` chỉ hợp lệ nếu count bằng 0.
4. Tính vào `int64_t` và chỉ cập nhật `out_sum` khi không còn lý do để thất bại.
5. C không giữ pointer sau lời gọi nên arena cục bộ của Java đủ điều kiện đóng ngay sau downcall.

Mã C **không thể tự chứng minh** con trỏ khác NULL thực sự trỏ tới ít nhất `count` phần tử. Trách nhiệm bảo đảm bounds của pointer thuộc caller. Nếu chuyển raw pointer trực tiếp từ Java mà không có wrapper, C có thể đọc ngoài vùng nhớ hợp lệ.

**Phản ví dụ hợp đồng:** nếu sau này C sửa thành lưu `values` vào một queue xử lý bất đồng bộ, lời gọi Java ở phần sau sẽ trở nên nguy hiểm vì `Arena` có thể đóng trước khi queue đọc xong. Phải thay giao thức thành copy vào vùng native sở hữu lâu dài hoặc có hàm release/stop/drain rõ ràng. Không được giữ nguyên wrapper chỉ vì chữ ký C chưa đổi.

## 5. Build thư viện native

Ví dụ **Linux x86-64 hoặc aarch64** với compiler C11 hỗ trợ shared library:

```bash
mkdir -p build/native build/generated build/classes
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
   -o build/native/liblabmath.so native/labmath.c
```

Sau build phải có `build/native/liblabmath.so`. Kiểm tra function export bằng công cụ phù hợp, ví dụ `nm -D build/native/liblabmath.so` hoặc `readelf -Ws build/native/liblabmath.so`. Tên symbol kỳ vọng là `labmath_sum` và `labmath_abi_version`.

Đối với macOS, sử dụng chế độ tạo dynamic library:

```bash
mkdir -p build/native
cc -std=c11 -O2 -Wall -Wextra -dynamiclib \
   -o build/native/liblabmath.dylib native/labmath.c
```

Đối với Windows, build DLL bằng MSVC/clang hoặc toolchain tương thích, định nghĩa `LABMATH_BUILD` khi biên dịch C để xuất hàm. File kỳ vọng là `labmath.dll`. Lệnh và linker flags cụ thể khác nhau theo toolchain; bảo đảm cùng kiến trúc với JVM và symbol thực sự export. Không dùng file `.so` trên Windows hay nhầm thư viện 32-bit với JVM 64-bit.

## 6. Dùng jextract sinh binding từ header

Kiểm tra công cụ và JDK:

```bash
java -version
jextract --version
```

Dùng bản jextract phát hành cho JDK bạn chọn (từ [trang jextract](https://jdk.java.net/jextract/) hoặc [mã nguồn OpenJDK jextract](https://github.com/openjdk/jextract)). Các bản jextract mới nhắm tới JDK hiện hành, nên compiler của binding có thể đòi JDK mới hơn 22.

Ví dụ trên Linux, từ root của project:

```bash
jextract \
  --output build/generated \
  --target-package demo.raw \
  --header-class-name labmath_h \
  --library ":$(pwd)/build/native/liblabmath.so" \
  native/labmath.h
```

Ý nghĩa cờ:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--output build/generated` | Đặt Java source được sinh ở thư mục build tách khỏi mã viết tay |
| `--target-package demo.raw` | Package của binding mức thấp |
| `--header-class-name labmath_h` | Khóa tên class chính để code Java import ổn định |
| `--library ":.../liblabmath.so"` | Nạp đúng binary theo đường dẫn; dấu `:` báo jextract đây là *path* |
| `native/labmath.h` | Header C cung cấp chữ ký, hằng và layout |

Ở ví dụ dùng đường dẫn tuyệt đối được tạo bởi `$(pwd)`; nếu thư mục project di chuyển thì **phải sinh lại** binding hoặc chuyển sang chiến lược nạp theo tên. Để chạy ứng dụng phân phối, có thể dùng `--library labmath` cùng cơ chế tìm thư viện của OS, hoặc `--use-system-load-library` và `java.library.path` theo tài liệu jextract. Không hardcode đường dẫn build của developer vào artifact production.

Sau khi chạy, kiểm tra thư mục `build/generated/demo/raw`. Một bản jextract tương thích sẽ tạo class header `labmath_h` với các accessor tương ứng. Trong thực hành này, ta sử dụng chữ ký thông thường từ các khai báo trên:

```java
// API kỳ vọng ở lớp được jextract sinh, không phải mã tự viết.
int labmath_abi_version();
int labmath_sum(MemorySegment values, int count, MemorySegment outSum);
int LABMATH_ABI_VERSION();
```

Đây là **minh họa chữ ký cần kiểm tra ở output**, không phải một lớp Java đầy đủ. Với các function đơn giản, jextract còn sinh `labmath_sum$address()`, `labmath_sum$descriptor()` và `labmath_sum$handle()`. Chúng giúp chẩn đoán và thao tác FFM mức thấp; public API ở phần sau chỉ nên gọi wrapper function đã sinh.

**Đừng nhầm:** jextract sinh `MemorySegment` theo type pointer ở C; nó không suy luận rằng `count` là số phần tử của `values`, cũng không tự thêm `Objects.requireNonNull`, giới hạn 4096 hoặc kiểm tra return code. Vì vậy code Java gọi thẳng `labmath_h.labmath_sum(...)` vẫn có thể phá hợp đồng C.

## 7. Viết lớp bao Java kiểm tra hợp đồng

Tạo `src/demo/LabMath.java`:

```java
package demo;

import demo.raw.labmath_h;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Objects;

public final class LabMath {
    public static final int MAX_ELEMENTS = 4096;

    private LabMath() {}

    public static long sum(int[] values) {
        Objects.requireNonNull(values, "values");
        if (values.length > MAX_ELEMENTS) {
            throw new IllegalArgumentException("Maximum length is 4096");
        }
        int abiVersion = labmath_h.labmath_abi_version();
        if (abiVersion != labmath_h.LABMATH_ABI_VERSION()) {
            throw new LinkageError("Header/native ABI mismatch: " + abiVersion);
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeValues = values.length == 0
                ? MemorySegment.NULL
                : arena.allocate(
                    (long) values.length * ValueLayout.JAVA_INT.byteSize(),
                    ValueLayout.JAVA_INT.byteAlignment());

            for (int i = 0; i < values.length; i++) {
                nativeValues.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
            }

            MemorySegment out = arena.allocate(ValueLayout.JAVA_LONG);
            int status = labmath_h.labmath_sum(nativeValues, values.length, out);
            if (status != 0) {
                throw new NativeCallException("labmath_sum", status);
            }
            return out.get(ValueLayout.JAVA_LONG, 0);
        }
    }

    public static final class NativeCallException extends RuntimeException {
        private final int status;
        public NativeCallException(String operation, int status) {
            super(operation + " failed with native status " + status);
            this.status = status;
        }
        public int status() { return status; }
    }
}
```

### Đi qua từng hàng rào kiểm tra

**Hàng rào 1: Java inputs.** `Objects.requireNonNull` loại `null` từ đầu; kiểm tra `MAX_ELEMENTS` ngay trước cấp phát. Độ dài mảng Java vốn không âm. Quy tắc 4096 được đặt rõ ràng trong lớp bao để không vô tình gọi C với count quá lớn. Trong production, đồng bộ giới hạn này với header bằng cấu hình/kiểm tra generated constant, và test sai khác giữa các phiên bản.

**Hàng rào 2: header so với binary.** `LABMATH_ABI_VERSION()` đến từ header; `labmath_abi_version()` đến từ native binary. Giá trị khác nhau làm ném `LinkageError` trước khi thao tác pointer. Version check giúp phát hiện lệch phiên bản có quy ước, nhưng **không thay thế** kiểm tra ABI thực tế: nhà cung cấp phải tăng version khi thay đổi ABI, test symbol/struct layout và đóng gói đúng binary.

**Hàng rào 3: kích thước/alignment.** Mỗi `int` Java được chép vào segment có `count * 4` byte và alignment phù hợp `ValueLayout.JAVA_INT`. Việc ép `(long) values.length` làm phép nhân sử dụng 64-bit; với giới hạn 4096 nên không thể tràn. Output được cấp phát bằng `ValueLayout.JAVA_LONG` tương ứng kích thước 64-bit trong ví dụ. `setAtIndex`/`get` có kiểm tra bounds trên phía Java, còn C vẫn đòi pointer và count phải khớp.

**Hàng rào 4: trường hợp mảng rỗng.** Với mảng 0 phần tử, wrapper truyền `MemorySegment.NULL` cùng `count=0`; đó là đúng **vì header đã cho phép**. Nếu API C khác bắt buộc pointer non-null ngay cả khi length=0, lớp bao phải dùng cách khác. Không suy diễn mọi API đều cho phép null/empty.

**Hàng rào 5: return code.** Không đọc `out` trước khi `status == 0`. Khi C báo lỗi, `NativeCallException` chứa operation và số nguyên gốc, tránh đánh mất thông tin do tự đoán exception không phù hợp. Với một thư viện thật, có thể ánh xạ *mã lỗi đã biết* thành các exception cụ thể, nhưng mã chưa biết vẫn phải được giữ lại.

**Hàng rào 6: lifetime.** `Arena.ofConfined()` thuộc thread gọi `sum`; `try-with-resources` đóng cả `nativeValues` và `out` khi thành công hoặc khi có exception. C chỉ mượn pointer trong **thời gian downcall đồng bộ**, không lưu con trỏ nên không có use-after-free. Nếu C giữ pointer cho callback/worker, phải thiết kế lifecycle khác và không đóng arena ngay.

**Hàng rào 7: API surface.** Callers thấy `long sum(int[])`, không thấy `MemorySegment`, `Arena` hoặc mã lỗi thô. Đặt code sinh ở `demo.raw` và public wrapper ở `demo` giúp tránh rải thao tác unsafe khắp ứng dụng. Có thể chặn quyền import package raw bằng module/package conventions và code review.

## 8. Viết chương trình kiểm tra cả hành vi Java và hợp đồng raw

Tạo `src/demo/Main.java`:

```java
package demo;

import demo.raw.labmath_h;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class Main {
    public static void main(String[] args) {
        System.out.println("sum=" + LabMath.sum(new int[] {1, 2, 3}));
        System.out.println("empty=" + LabMath.sum(new int[] {}));
        System.out.println("wide=" + LabMath.sum(
            new int[] {Integer.MAX_VALUE, Integer.MAX_VALUE}));

        try {
            LabMath.sum(null);
            throw new AssertionError("null was accepted");
        } catch (NullPointerException expected) {
            System.out.println("null rejected");
        }

        try {
            LabMath.sum(new int[4097]);
            throw new AssertionError("too many elements were accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("too many rejected");
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment out = arena.allocate(ValueLayout.JAVA_LONG);
            out.set(ValueLayout.JAVA_LONG, 0, 123L);
            int code = labmath_h.labmath_sum(MemorySegment.NULL, -1, out);
            System.out.println("raw status=" + code
                + " out=" + out.get(ValueLayout.JAVA_LONG, 0));
        }
    }
}
```

**Vì sao có một lời gọi raw trong `Main`?** Đây là phép thử **chính hợp đồng của C**, không phải cách ứng dụng thông thường gọi thư viện. Ta cấp phát output hợp lệ, truyền `count=-1` và pointer input NULL; C phải phát hiện range sai, trả `LABMATH_ERR_RANGE == 2`, không ghi đè output sentinel `123`. Điều đó kiểm tra sự khác biệt giữa binding thô (cho phép truyền giá trị tùy ý) và lớp bao (loại dữ liệu sai trước khi gọi C). Phép thử chỉ an toàn vì API C **đã** kiểm tra count trước khi truy cập `values`.

`wide` cũng kiểm tra rằng hai giá trị `Integer.MAX_VALUE` cộng lại thành `4294967294L`, vượt giới hạn `int` nhưng nằm trong `long`. Nếu native hoặc generated binding vô tình sử dụng type 32-bit cho output, phép thử sẽ bộc lộ sai khác.

## 9. Biên dịch và chạy

Khi `build/generated` đã được jextract tạo, trên Linux:

```bash
mkdir -p build/classes
javac -d build/classes $(find build/generated src -name '*.java')
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.Main
```

Dùng JDK tương thích với output của jextract. Tham số `--enable-native-access=ALL-UNNAMED` cấp quyền gọi native cho code chạy trên classpath trong trường hợp này. Khi dùng named module, cấu hình native-access cho module cụ thể và quy tắc đóng gói của ứng dụng. Đừng bật native access cho code không tin cậy.

**Stdout kỳ vọng từ chương trình mẫu** (không tính log loader hoặc cảnh báo cấu hình JVM nếu có):

```text
sum=6
empty=0
wide=4294967294
null rejected
too many rejected
raw status=2 out=123
```

Ý nghĩa:

- `sum=6` chứng minh đường đi Java `int[]` → native pointer → mã thành công → Java `long`.
- `empty=0` xác nhận sự phối hợp `count=0` và pointer NULL hợp lệ.
- `wide=4294967294` xác nhận output 64-bit.
- `null rejected` và `too many rejected` xác nhận kiểm tra Java trước khi cấp phát/gọi C.
- `raw status=2 out=123` xác nhận điều kiện lỗi của C và tính chất không ghi output khi thất bại.

Nếu thiếu jextract/clang/toolchain ở máy đang học, có thể **kiểm tra riêng cú pháp và logic wrapper bằng một test stand-in có cùng chữ ký `labmath_h`**, nhưng điều đó chỉ là unit test phía Java. Muốn công nhận hoàn thành bài thực hành kết nối native, phải sinh binding và chạy chính `liblabmath` bằng jextract trên máy phù hợp.

## 10. Test matrix mở rộng để phát hiện lỗi hợp đồng

| Test | Dữ liệu / thiết lập | Kỳ vọng | Lớp bắt lỗi |
| --- | --- | --- | --- |
| Tổng bình thường | `[1,2,3]` | `6` | End-to-end |
| Mảng rỗng | `[]` | `0` | Wrapper + C |
| Tổng vượt int32 | `[MAX_INT,MAX_INT]` | `4294967294L` | ABI/output layout |
| Null từ Java | `null` | `NullPointerException` trước downcall | Wrapper |
| Vượt giới hạn | `new int[4097]` | `IllegalArgumentException` trước downcall | Wrapper |
| Biên tối đa | 4096 phần tử hợp lệ | Tổng 64-bit đúng | Wrapper + native |
| Negative length raw | `values=NULL,count=-1,out=valid` | `ERR_RANGE`, output giữ nguyên | C |
| Output pointer NULL raw | `out=NULL` | `ERR_NULL`, không dereference | C |
| Positive count + input NULL raw | `count=1,values=NULL,out=valid` | `ERR_NULL` | C |
| Header/binary lệch version | Header 1, binary trả 2 | `LinkageError` trước gọi sum | Wrapper |
| Native trả error chưa biết | Test shim trả mã giả lập | Exception giữ đúng mã và tên function | Wrapper |
| Library không tìm thấy | Đổi đường dẫn/xóa file trong test env | Lỗi linkage/loading có nguyên nhân rõ | Loader |
| Không có symbol `labmath_sum` | Đổi tên export trong binary test | Load/link phải thất bại có kiểm soát | Binding + loader |
| Wrong pointer extent | Raw pointer ngắn hơn count | Không đưa vào JVM chính; test riêng/sanitizer | Native ABI safety |
| Multi-thread | Nhiều thread gọi `LabMath.sum` | Mỗi call có arena riêng, output độc lập | Wrapper/thread safety |
| Regenerate header | Đổi C signature và chạy lại jextract | Diff signature được review; update tests | Build/contract drift |

Đối với một thư viện bên thứ ba không có API version, wrapper có thể kiểm tra khả năng lookup symbol, chạy smoke test bằng input nhỏ đã biết, xác minh layout trước khi mở session, hoặc tự có cơ chế version pin. **Không** tự giả định version check đơn lẻ xác thực mọi layout C.

Với trường hợp memory-safety không xác định, tránh cố ý truyền pointer đã free trong main JVM. C/C++ có thể gây `SIGSEGV` hoặc access violation, không phải Java exception; chạy test trong process riêng với AddressSanitizer/UndefinedBehaviorSanitizer khi có thể, giới hạn thời gian và thu thập crash dump.

## 11. Jextract đã làm gì và chưa làm gì?

Từ khai báo C:

```c
int32_t labmath_sum(const int32_t *, int32_t, int64_t *);
```

jextract làm phần **phù hợp với ABI**: giải quyết tên symbol, descriptor kiểu C, downcall handle và method Java nhận các tham số tương ứng. Thông thường class header sinh ra có các phương thức để lấy `$address`, `$descriptor`, `$handle` của hàm.

Những thứ jextract không thể suy ra chỉ từ prototype:

- Một pointer là *borrowed* hay phải `free` bằng hàm nào.
- Length tương ứng với bao nhiêu byte/phần tử; pointer có thể NULL lúc nào.
- Truyền memory segment có hợp lệ trên thread này hoặc sau close không.
- Hai biểu tượng C có phải cùng ABI/runtime version với header lúc generation không.
- Mã `0` có phải success, mã khác có thể retry không.
- Thư viện có giữ callback hoặc con trỏ sau khi downcall trả về không.
- Lời gọi có thể block, tạo worker, hoặc yêu cầu synchronization không.
- Giá trị nào phải cấm vì nghiệp vụ (ví dụ count tối đa, input constraints).

Lớp bao là nơi thể hiện và test các quy tắc này. Với thư viện thật, **đừng chỉnh Java code jextract sinh** để vá trực tiếp null check và error handling: lần regenerate sẽ xóa sửa đổi. Giữ generated code như artifact build, đặt validation, error mapping và ownership trong các class riêng.

Nếu C API dùng struct hay opaque handle, wrapper thường cần thêm `AutoCloseable` và state rõ ràng. Ví dụ `create_native_handle` trả pointer owned thì `close` phải gọi đúng destructor **một lần**, sau khi không còn downcall/callback sử dụng handle; không chỉ đóng arena lưu pointer. Nếu native giữ callback, lifetime của upcall stub phải kéo dài đến sau unregister + drain theo hợp đồng. Những quyết định đó không nằm trong phạm vi hàm `labmath_sum` đồng bộ của lab này, nhưng là điều kiện bắt buộc khi mở rộng bài.

## 12. Lỗi thường gặp và cách chẩn đoán

### 12.1. Không chạy được jextract

- `jextract: command not found`: cài công cụ phù hợp và đưa executable vào PATH; JDK không luôn bao gồm jextract.
- `UnsupportedClassVersionError` khi chạy jextract/code sinh: JDK chạy quá cũ so với bản công cụ hoặc bytecode; kiểm tra `java -version`, `javac -version`, `jextract --version`.
- Clang không parse được header: kiểm tra include path `-I`, macro `-D`, compiler flags, các typedef/attribute và SDK thực tế.
- Header chứa C++ class/template: tạo C ABI bridge có `extern "C"` trước; jextract chủ yếu xử lý C header.
- Đặt quá nhiều lọc `--include-function` nhưng thiếu typedef/struct phụ thuộc: dùng output đầy đủ trước, rồi chỉ lọc khi đã biết các dependency.

### 12.2. Không link hoặc load được binary

- `UnsatisfiedLinkError`/linkage failure: kiểm tra path ở `--library`, file tồn tại, dependency thư viện, kiến trúc, OS và tên symbol export.
- Linux nếu dùng `--library labmath` thì loader tìm `liblabmath.so` qua cơ chế OS (có thể dùng `LD_LIBRARY_PATH`). macOS dùng `liblabmath.dylib`, Windows dùng `labmath.dll`.
- Nếu chọn `--use-system-load-library`, cơ chế nạp dựa vào `System.loadLibrary` và `java.library.path`; các native dependencies vẫn dựa vào loader OS.
- Lỗi “symbol not found” thường do sai tên export, C++ name mangling, sai library version hoặc function không được export. Đừng sửa binding bằng cách đoán địa chỉ.
- Lỗi native-access flag: đặt `--enable-native-access=ALL-UNNAMED` cho classpath; với named module thì sử dụng danh sách module theo cấu hình JDK.

**Thứ tự debug:** kiểm tra phiên bản công cụ → binary có đúng OS/arch → symbol export → generated header class và chữ ký → chế độ library lookup → native access → hợp đồng runtime.

### 12.3. Kết quả sai dù build thành công

- Java nhận `long` nhưng C trả `int`: header/binary không cùng signature; không ép cast để “sửa nhanh”.
- Kiểu C `long` khác trên Windows 64-bit và Linux 64-bit: chọn `int32_t/int64_t` hoặc sinh riêng theo nền tảng, kiểm tra layout.
- Đọc `out_sum` khi `status != 0`: đang đọc dữ liệu không có bảo đảm; chỉ đọc sau success.
- Truyền pointer tới buffer quá ngắn: crash hoặc dữ liệu sai; wrapper tạo segment đúng bounds và count.
- Đóng arena trước khi native hoàn tất: use-after-free; với API async cần stop/drain/ownership khác.
- Sử dụng một `MemorySegment` từ confined arena trên thread khác: có thể gặp `WrongThreadException`.
- So version macro với chính macro của code sinh nhưng **không gọi native version function**: chỉ biết header, chưa xác nhận binary.
- Chỉnh trực tiếp file trong `build/generated`: lần sinh kế tiếp mất sửa đổi; đưa policy vào wrapper.

## 13. Cách đưa cấu trúc này vào module thật

Một codebase Java có thể chia thành ba lớp:

```text
native C library / third-party C ABI
              ↓  jextract
demo.raw.labmath_h  (generated; ABI only)
              ↓  contract checks + ownership
demo.LabMath         (authored; public Java API)
              ↓
application/service/tests
```

Đối với dự án Gradle hoặc Maven, thêm bước generation/build thích hợp **chỉ khi thực sự cần**, giữ output generated ngoài source do con người chỉnh sửa. Khóa phiên bản jextract tương thích JDK; tách build native theo target platform và kiểm tra thay đổi header/binary trên CI. Không yêu cầu một repository Java học tập phải dùng cùng một layout package như ví dụ: `demo.raw` và `demo` chỉ là tên của lab độc lập.

Bộ acceptance checks khi tích hợp:

1. `labmath.h` có contract rõ cho mỗi pointer, count, return code, ABI version và ownership.
2. Native library biên dịch cho đúng platform; symbol export khớp tên header.
3. jextract sinh binding với package/tên class ổn định; mọi thay đổi output được review sau regenerate.
4. Java wrapper chặn input sai, tạo bounds/alignment đúng và chỉ đọc output khi native báo thành công.
5. Wrapper không tiết lộ raw pointer ngoài public API; arena sống đúng khoảng thời gian C mượn pointer.
6. Chạy thực tế `Main` cho đúng sáu dòng stdout; test negative count xác nhận output không đổi.
7. Test riêng version mismatch, missing symbol và native return code khác 0; giữ error code gốc trong exception.
8. Test trên từng OS/arch được hỗ trợ và với đúng JDK/jextract release; không giả định binary Linux chạy trên Windows.

**Kết luận:** jextract giảm đáng kể công việc tạo FFM binding từ C header nhưng chỉ cung cấp *cửa gọi native*. Lớp bao kiểm tra hợp đồng mới biến cửa gọi đó thành API Java có đầu vào hợp lệ, ownership rõ, lỗi có ý nghĩa và khả năng kiểm thử. Chất lượng tích hợp phụ thuộc vào **hợp đồng C được viết rõ → generated binding trung thực với ABI → wrapper bảo vệ các điều kiện mà header không tự biểu đạt → test end-to-end với binary thật**.

## Tài liệu tham khảo

- [Dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/).
- [OpenJDK jextract — Guide, CLI, generated methods, library loading](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- [Oracle Java 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).
- [JDK 22 API — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [JDK 22 API — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
