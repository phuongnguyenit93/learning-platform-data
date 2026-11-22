# Tách mã sinh khỏi lớp bao quản lý tài nguyên và kiểm tra dữ liệu

## 1. Đề bài và nguyên tắc thiết kế

**jextract** là công cụ của OpenJDK đọc C header và sinh Java bindings dựa trên **Foreign Function & Memory API (FFM)**. Generated bindings biết nhiều điều về *chữ ký native*: tên C function, C types, `MemoryLayout`, cách lấy symbol và tạo downcall handles. Nhưng chúng **không thể tự suy ra** quy tắc nghiệp vụ, ranh giới tin cậy và ownership của một con trỏ native.

Vì vậy, có hai lớp Java nên tách biệt:

- **Low-level generated binding:** output cơ học của jextract, gần C ABI, có thể regenerate. Không cấy validation hoặc chính sách tài nguyên vào source tự sinh.
- **Handwritten facade (safe wrapper):** lớp viết tay ổn định cho application. Nó nhận Java objects/primitives, kiểm tra dữ liệu, xác định ai sở hữu native handle, cấp phát buffer theo `Arena`, kiểm tra C status codes, copy output thành Java values, đóng tài nguyên và ngăn gọi sau close.

Không nên để mọi controller/service import generated class rồi tự gọi C functions. Điều đó phân tán ownership và khiến một thay đổi C header gây sửa ở nhiều nơi. Facade gom sự phức tạp FFM về một ranh giới dễ review/test.

~~~text
Application / Controller / Business service
          |
          | public Java API: int[], exceptions, AutoCloseable
          v
demo.api.CheckedCalc                    [VIẾT TAY]
  - validate null / max length / value ranges
  - create/close native session exactly once
  - per-call Arena.ofConfined
  - C status -> Java exception
  - copy result into int[] before Arena closes
          |
          | raw C signatures represented as FFM carriers
          v
demo.generated.RawCalc                 [jextract SINH]
  - symbols, library loading, downcall handles
  - C int -> Java int; C pointer -> MemorySegment
          |
          v
libsecurecalc.so / .dylib / .dll        [NATIVE LIBRARY]
  - sc_open / sc_scale / sc_close
  - malloc/free; C ABI
~~~

**Luận điểm chính:** jextract sinh **liên kết**, không sinh **API ứng dụng an toàn**. Tên “safe wrapper” không có nghĩa native code đã trở nên vô hại: ABI sai, native memory corruption và use-after-free vẫn có thể crash JVM. Mục tiêu là giảm sai sót có thể kiểm soát từ phía Java và làm rõ hợp đồng native.

Các chương trình chính được thiết kế cho **JDK 22+**, phiên bản FFM chính thức theo JEP 454. JDK 21 sử dụng FFM third preview theo JEP 442, cần `--enable-preview` và có những khác biệt API. **jextract không được bảo đảm nằm sẵn trong JDK**; chọn jextract version sinh code phù hợp JDK target.

## 2. Vì sao generated code không thể tự thay wrapper?

| Câu hỏi | Generated jextract binding | Handwritten facade |
|---|---|---|
| C function tên gì? Nhận/Trả C types nào? | Đọc từ header và sinh tương ứng | Sử dụng các phương thức sinh |
| C library được tìm/nạp ra sao? | Theo options của jextract | Cấu hình runtime và xử lý lỗi ở ranh giới |
| `void *` là owned hay borrowed? | Không tự biết | Cần hợp đồng rõ và owner duy nhất |
| `const char*` là UTF-8 hay encoding khác? | Không biết nghiệp vụ | Chọn charset, kiểm tra NUL/byte count |
| `int count` cho phép bao nhiêu phần tử? | Không biết chính sách | Check size, limits, overflow |
| `-3` của native function nghĩa là gì? | Trả `int -3` | Dịch sang Java exception/domain status |
| Native function giữ pointer sau khi return? | Không tự kết luận | Thiết kế Arena lifetime theo C contract |
| Khi nào free native session? | Không biết | `AutoCloseable.close()` + đúng C deallocator |
| C function có thread-safe không? | Không biết | Lock/owner-thread/executor thích hợp |
| C struct layout có đúng ABI thực tế? | Phụ thuộc header/tool/target | Integration tests theo OS/CPU/compiler |
| Cần trả `MemorySegment` ra business layer? | Có thể trả raw carrier | Thường nên copy sang Java array/record |

Ví dụ generated method có thể có carrier `MemorySegment` đối với cả owned C session và borrowed `int*` input, dù **hai con trỏ có owner và lifetime hoàn toàn khác**. Java compiler không phân biệt chúng chỉ nhờ kiểu `MemorySegment`. Facade cung cấp kiểu/khế ước sử dụng phù hợp để người dùng API không phải đoán.

### 2.1. Ba lifetime cần theo dõi độc lập

1. **Generated library/class-loader lifetime:** native binary được nạp theo tùy chọn của binding, phụ thuộc loader/JVM. Nó không phải chính native session.
2. **Native session lifetime:** C `sc_open` cấp phát `sc_session*` qua C allocator; C `sc_close` giải phóng. Wrapper chịu trách nhiệm gọi **một lần**.
3. **Temporary call buffers:** Java cấp native input/output memory bằng `Arena.ofConfined()`; tồn tại trong một lời gọi và được arena thu hồi khi đóng.

`Arena.close()` **không tự giải phóng** một pointer do C `malloc` cấp, chỉ vì Java có một `MemorySegment` chứa địa chỉ ấy. Ngược lại, `sc_close(session)` không giải phóng các buffer do Java Arena cấp. Đó là lý do cần hai loại cleanup trong facade.

## 3. Cấu trúc source và phụ thuộc một chiều

~~~text
checked-jextract/
├── native/
│   ├── securecalc.h
│   └── securecalc.c
├── generated/
│   └── src/demo/generated/...
├── src/main/java/
│   └── demo/
│       ├── api/CheckedCalc.java
│       └── app/Main.java
├── build/classes/
└── libsecurecalc.so      (Linux; Windows/macOS có tên khác)
~~~

**Thư mục có chủ sở hữu rõ ràng:**

- `native/securecalc.h`: C ABI header, **nguồn dữ liệu đầu vào của jextract**.
- `native/securecalc.c`: implementation C và logic quản lý native session.
- `generated/src`: **chỉ jextract ghi**. Có thể commit generated sources hoặc regenerate trong CI, nhưng chọn một chiến lược nhất quán.
- `src/main/java/demo/api`: code viết tay, giữ validation/ownership/error handling.
- `src/main/java/demo/app`: application chỉ phụ thuộc facade `CheckedCalc`.
- `build/classes`: đầu ra javac; không sửa như source.

Sơ đồ import:

~~~text
Allowed:
    demo.app -> demo.api -> demo.generated -> native library

Discouraged:
    demo.app -> demo.generated
    service  -> raw MemorySegment
    generated -> demo.api
    caller khác -> sc_close(session) bằng pointer đã mượn
~~~

Các packages trên là **ranh giới kiến trúc**, không phải cơ chế bảo mật. Khi cần chặn việc dùng raw generated API, có thể cân nhắc Java modules và chỉ export facade package, với module graph/native-access đã cấu hình đúng. Không nhầm “không nên import” với “không thể import”.

## 4. Định nghĩa native contract trước khi sinh code

Ví dụ sử dụng C library `securecalc` có 3 hàm: tạo session với factor limit, nhân từng phần tử mảng với factor, đóng session.

**Hợp đồng C:**

- `sc_open(int max_factor)` nhận `0..10`. Nếu thành công trả `sc_session*`, caller **sở hữu** session và phải gọi `sc_close` đúng **một lần**. Nếu thất bại trả `NULL`.
- `sc_scale(session,input,count,factor,output)` yêu cầu session sống, `count` từ 1 đến 64, input/output đều có ít nhất `count` số `int`, factor từ 0 tới `session->max_factor`, mỗi input từ 0 tới 10000.
- C function không giữ con trỏ input/output sau khi trả về. Vì thế những buffer đó có thể sống trong một **call-scoped arena**.
- `sc_scale` trả `0` khi thành công, mã âm khi thất bại. **Chỉ đọc output khi status bằng 0**.
- `sc_close(session)` gọi đúng deallocator của `sc_open`. Không gọi lại trên cùng pointer; C code trong demo không hỗ trợ double-free.
- ABI mẫu hướng tới nền tảng phổ biến có C `int` 32 bit; với ABI bất thường, phải kiểm tra type width/layout hoặc thay header bằng kiểu có độ rộng xác định.

**Đừng suy ra ownership từ tên method hoặc kiểu C pointer.** Một `char*` có thể trỏ tới bộ nhớ tĩnh, một allocation phải free, một buffer tạm hoặc chuỗi trong nội bộ thư viện. Chỉ C API documentation/contract mới quyết định.

### 4.1. Header đầy đủ — `native/securecalc.h`

~~~c
#ifndef SECURECALC_H
#define SECURECALC_H

#if defined(_WIN32)
#  define SC_EXPORT __declspec(dllexport)
#else
#  define SC_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque native handle: chỉ dùng qua các functions bên dưới. */
typedef struct sc_session sc_session;

/* max_factor 0..10, trả NULL khi không tạo được. */
SC_EXPORT sc_session *sc_open(int max_factor);

/* 0=OK, -1=session NULL, -2=bad pointers/count,
   -3=invalid factor, -4=invalid input value.
   Thất bại: không dùng contents của output. */
SC_EXPORT int sc_scale(
    sc_session *session,
    const int *input,
    int count,
    int factor,
    int *output
);

/* Free một session đang sống đúng một lần; NULL được chấp nhận. */
SC_EXPORT void sc_close(sc_session *session);

#ifdef __cplusplus
}
#endif

#endif
~~~

Đây là **tệp header hoàn chỉnh**. `extern "C"` ngăn C++ name mangling nếu một caller C++ include header; example implementation là C. Các exports cho phép native loader tìm symbols. jextract đọc **declarations trong header**, không cần bạn viết tên `Java_package_Class_method` của JNI.

### 4.2. Implementation đầy đủ — `native/securecalc.c`

~~~c
#include "securecalc.h"
#include <stddef.h>
#include <stdlib.h>

struct sc_session {
    int max_factor;
};

sc_session *sc_open(int max_factor) {
    if (max_factor < 0 || max_factor > 10) {
        return NULL;
    }

    sc_session *session = (sc_session *)malloc(sizeof(*session));
    if (session == NULL) {
        return NULL;
    }

    session->max_factor = max_factor;
    return session;
}

int sc_scale(
        sc_session *session,
        const int *input,
        int count,
        int factor,
        int *output) {
    if (session == NULL) {
        return -1;
    }
    if (count <= 0 || count > 64 || input == NULL || output == NULL) {
        return -2;
    }
    if (factor < 0 || factor > session->max_factor) {
        return -3;
    }

    /* Validate tất cả trước khi ghi output. */
    for (int i = 0; i < count; i++) {
        if (input[i] < 0 || input[i] > 10000) {
            return -4;
        }
    }

    for (int i = 0; i < count; i++) {
        output[i] = input[i] * factor;
    }
    return 0;
}

void sc_close(sc_session *session) {
    free(session);
}
~~~

Đây là **tệp C đầy đủ**. Native C vẫn tự kiểm tra count, pointer và value ranges, bởi caller ngoài wrapper có thể gọi trực tiếp. Tuy nhiên, C function chỉ nhận một `int*`, **không có metadata byte length** của bộ nhớ mà con trỏ thực sự trỏ tới: nếu caller nói `count=64` nhưng chỉ cấp 2 phần tử, C không thể tự xác minh dung lượng. Wrapper phải giữ `count` nhất quán với buffer đã cấp.

Hai vòng validation có lý do riêng:

- **Java wrapper:** fail sớm bằng exception phù hợp với Java API, tránh cấp phát/FFM call không cần thiết.
- **C native:** phòng thủ với những caller khác và kiểm tra lại ranh giới C.

Trong C demo, maximum `10000 * 10 = 100000`, tránh signed overflow trên `int` 32-bit. Với input tùy ý, phải thiết kế arithmetic bounds/saturation/error policy rõ ràng, không để C signed overflow thành undefined behavior.

## 5. Sinh code đúng toolchain và không can thiệp generated source

`jextract` là công cụ riêng của dự án OpenJDK, không mặc nhiên cài cùng mọi JDK. Generated code dùng FFM APIs nên **jextract version phải khớp JDK target**. Hướng dẫn này chọn **JDK 22+**, ưu tiên một jextract release/branch được xây cho FFM final JDK22. Jextract phiên bản mới có thể yêu cầu JDK mới hơn, không thể giả định bản mới nhất tạo code dùng được với JDK22.

Trước tiên kiểm tra:

~~~bash
java -version
javac -version
jextract --version
jextract --help
~~~

Khi đã chọn cặp công cụ tương thích, từ project root chạy:

~~~bash
jextract \
  --output generated/src \
  --target-package demo.generated \
  --header-class-name RawCalc \
  --library securecalc \
  --use-system-load-library \
  native/securecalc.h
~~~

**Ý nghĩa options:**

| Tùy chọn | Ý nghĩa |
|---|---|
| `--output generated/src` | Đưa mọi generated Java sources vào một root riêng |
| `--target-package demo.generated` | Package của bindings |
| `--header-class-name RawCalc` | Tên class chính giữ ổn định khi code phù hợp |
| `--library securecalc` | Tên logic của native binary cần load |
| `--use-system-load-library` | Dùng cơ chế `System.loadLibrary` để có thể cấu hình `java.library.path` |
| `native/securecalc.h` | Chính xác header C được parse |

Trên Windows cmd.exe, dùng **một dòng** để tránh khác cú pháp nối dòng:

~~~bat
jextract --output generated/src --target-package demo.generated --header-class-name RawCalc --library securecalc --use-system-load-library native\securecalc.h
~~~

Generated source **thật** (không tự tạo class này thủ công) dự kiến có các static wrapper methods với carrier:

~~~text
demo.generated.RawCalc

sc_open(int)                       -> MemorySegment
sc_scale(MemorySegment session,
         MemorySegment input,
         int count,
         int factor,
         MemorySegment output)     -> int
sc_close(MemorySegment session)    -> void
~~~

Đây là **bảng chữ ký mô tả**, không phải Java source. Method names/carriers phải được đối chiếu trên **files thực sự do jextract tạo**, bởi generator version, typedefs và target ABI có thể làm output khác. Nếu chúng khác, kiểm tra jextract version/header trước; sửa **adapter viết tay** nếu cần, không sửa mã sinh.

Bản generated có thể còn cung cấp `sc_scale$address()`, `sc_scale$descriptor()`, `sc_scale$handle()` hoặc helper classes. App không cần biết các chi tiết này. Các raw C pointer, kể cả opaque `sc_session*`, thường được biểu diễn bằng `MemorySegment` nhưng **không mang ownership** hay byte size đáng tin chỉ từ carrier.

### 5.1. Vì sao --use-system-load-library được chọn?

Theo tài liệu jextract, nếu dùng `--library securecalc` mặc định, bindings có thể dùng `SymbolLookup.libraryLookup` và loader search path của OS. Với `--use-system-load-library`, jextract tạo logic load theo `System.loadLibrary`; khi đó Java có thể chỉ định `-Djava.library.path=.` để tìm `libsecurecalc.so`, `libsecurecalc.dylib` hay `securecalc.dll` trong thư mục đang chạy.

**Không nhầm** `java.library.path` với search path của native *dependencies* mà hệ điều hành tải theo. Nếu library còn phụ thuộc file khác, có thể vẫn cần cấu hình OS loader. Nếu bản jextract của bạn không có `--use-system-load-library`, đọc `jextract --help` và chọn một chiến lược load nhất quán thay vì copy flag từ tool khác.

### 5.2. Không sửa generated Java sau khi sinh

Nếu muốn thêm `if (len > 64) throw ...`, hãy viết nó trong `CheckedCalc`. Nếu muốn sửa package name, hãy thay `--target-package` và regenerate. Nếu muốn giới hạn declarations, dùng jextract include filters, không xóa thủ công methods trong generated files mỗi lần build.

Khi C header hoặc jextract thay đổi:

~~~text
C header / toolchain update
       |
       v
Regenerate ONLY generated/src
       |
       v
Compile generated + handwritten Java
       |
       v
Run unit tests and native integration tests
       |
       v
Review generated diff + wrapper contract
~~~

Tách thư mục giúp dễ review thay đổi máy sinh mà không lẫn với sửa logic nghiệp vụ.

## 6. Lớp Java facade: sở hữu session, kiểm tra dữ liệu và cleanup

Public API của example:

~~~text
new CheckedCalc(4)         -> tạo native session, kiểm tra max factor
calc.scale(int[], factor)   -> validate, allocate, call C, copy result
calc.close()                -> sc_close đúng một lần, đánh dấu closed
calc.scale(...) sau close  -> Java IllegalStateException, KHÔNG gọi C
~~~

Các caller không thấy `MemorySegment`, `Arena`, raw C status codes hoặc con trỏ `sc_session*`.

### 6.1. Tệp hoàn chỉnh — `src/main/java/demo/api/CheckedCalc.java`

~~~java
package demo.api;

import demo.generated.RawCalc;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Objects;

public final class CheckedCalc implements AutoCloseable {
    private static final int MAX_ITEMS = 64;
    private static final int MAX_VALUE = 10000;
    private static final int MAX_FACTOR = 10;

    private final MemorySegment session;
    private final int maxFactor;
    private boolean closed;

    public CheckedCalc(int maxFactor) {
        if (maxFactor < 0 || maxFactor > MAX_FACTOR) {
            throw new IllegalArgumentException("maxFactor must be 0..10");
        }

        MemorySegment ptr = RawCalc.sc_open(maxFactor);
        if (ptr.address() == 0L) {
            throw new IllegalStateException("native sc_open returned NULL");
        }

        session = ptr;
        this.maxFactor = maxFactor;
    }

    public synchronized int[] scale(int[] values, int factor) {
        ensureOpen();
        Objects.requireNonNull(values, "values");

        if (values.length > MAX_ITEMS) {
            throw new IllegalArgumentException("too many items");
        }
        if (factor < 0 || factor > maxFactor) {
            throw new IllegalArgumentException("factor out of range");
        }
        for (int value : values) {
            if (value < 0 || value > MAX_VALUE) {
                throw new IllegalArgumentException("value out of range");
            }
        }

        // API Java cho phép mảng trống; C contract yêu cầu count >= 1.
        if (values.length == 0) {
            return new int[0];
        }

        try (Arena callArena = Arena.ofConfined()) {
            MemorySegment input =
                    callArena.allocateFrom(ValueLayout.JAVA_INT, values);
            MemorySegment output =
                    callArena.allocate(ValueLayout.JAVA_INT, values.length);

            int status = RawCalc.sc_scale(
                    session, input, values.length, factor, output
            );
            if (status != 0) {
                // Không đọc output khi C báo lỗi.
                throw new IllegalStateException(
                        "native sc_scale failed: " + status
                );
            }

            int[] result = new int[values.length];
            for (int i = 0; i < result.length; i++) {
                result[i] = output.getAtIndex(
                        ValueLayout.JAVA_INT, i
                );
            }
            return result;
        }
    }

    private void ensureOpen() {
        if (closed) {
            throw new IllegalStateException("CheckedCalc is closed");
        }
    }

    @Override
    public synchronized void close() {
        if (!closed) {
            closed = true;
            RawCalc.sc_close(session);
        }
    }
}
~~~

Đây là **tệp Java hoàn chỉnh** do người phát triển sở hữu. Nó dựa vào các method carrier đã sinh từ đúng `native/securecalc.h`. Nếu generated signature khác, hãy kiểm tra tool/header, không đổi C ABI theo phỏng đoán.

### 6.2. Vì sao từng bước quan trọng?

1. **Constructor kiểm tra factor trước native allocate**, nên đầu vào không hợp lệ không tạo session.
2. `RawCalc.sc_open` trả một `MemorySegment` bọc opaque pointer. `ptr.address() == 0L` biểu thị C NULL, wrapper từ chối tạo object không có resource.
3. Session là `private final`, **không có public getter raw pointer**, tránh caller tự `sc_close` và tạo double-free.
4. `scale` kiểm tra state trước mọi native call. Sau `close`, không được dùng con trỏ đã bị giải phóng.
5. `Objects.requireNonNull` giúp lỗi Java rõ ràng; không đưa null hoặc count sai xuống C.
6. Kiểm tra maximum 64 và values 0..10000 trước khi cấp phát. Trường hợp `values.length == 0` được wrapper xử lý bằng `[]`, không gọi C với count=0.
7. `callArena.allocateFrom(JAVA_INT, values)` sao chép dữ liệu Java vào native memory, còn `callArena.allocate(JAVA_INT, count)` cấp output buffer phù hợp.
8. C nhận hai `int*`, count đúng bằng số phần tử. **C không biết `MemorySegment.byteSize()`; Java chịu trách nhiệm nhất quán count/byte size.**
9. `status != 0` trở thành exception. Không copy output từ một lời gọi native thất bại.
10. Copy result thành `int[]` **trước** khi arena đóng. Output vẫn hợp lệ sau khi method trả về dù native buffer đã được thu hồi.
11. `try (Arena ...)` bảo đảm buffers được giải phóng khi happy path, C status error hoặc Java exception.
12. `close` idempotent ở facade: lệnh C deallocator được gọi một lần. **Không** suy ra C `free(session)` tự idempotent nếu gọi hai lần.

Lớp có thể được thay đổi để ánh xạ native status sang domain-specific exception types nếu C API thật có nhiều loại lỗi. Với demo, `IllegalStateException("native sc_scale failed: ...")` báo một vi phạm hợp đồng không được kỳ vọng vì Java đã validate trước.

### 6.3. Concurrency: close và lời gọi cùng instance

Cả `scale` và `close` đều `synchronized` trên `this`. Điều này có ý nghĩa:

~~~text
Thread A vào synchronized scale:
    dùng session để gọi sc_scale
    copy output; đóng call Arena
    rời monitor

Thread B muốn synchronized close:
    chờ Thread A rời monitor
    đóng native session bằng sc_close
    đánh dấu closed

Lời gọi scale tiếp theo:
    thấy closed -> IllegalStateException
    không gọi C trên pointer đã free
~~~

Nếu chỉ có `volatile boolean closed` mà không đồng bộ đoạn native call với close, có thể xảy ra:

~~~text
A: check closed == false
B: close() -> free(session)
A: sc_scale(session, ...) -> use-after-free
~~~

**`synchronized` chỉ bảo vệ các đường gọi đi qua cùng facade instance.** Nó không thể ngăn native library có thread nội bộ giữ pointer, hoặc code khác cố tình gọi raw binding bên ngoài facade. Nếu C yêu cầu mọi lời gọi trên **một OS thread nhất định**, serialize bằng synchronized **vẫn chưa đủ**: phải dùng owner-thread executor hoặc thiết kế theo thread confinement.

## 7. Application dùng Java API, không biết binding C

Tệp hoàn chỉnh — `src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.CheckedCalc;
import java.util.Arrays;

public final class Main {
    public static void main(String[] args) {
        CheckedCalc calc = new CheckedCalc(4);

        try (calc) {
            System.out.println("scaled = "
                    + Arrays.toString(
                            calc.scale(new int[] {2, 4, 6}, 3)
                    ));

            System.out.println("empty = "
                    + Arrays.toString(
                            calc.scale(new int[0], 2)
                    ));

            try {
                calc.scale(new int[] {2, -1}, 2);
                throw new AssertionError("invalid input was accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid value = rejected");
            }

            try {
                calc.scale(new int[] {2}, 7);
                throw new AssertionError("invalid factor was accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid factor = rejected");
            }
        }

        calc.close(); // Idempotent tại facade, không free lần nữa.

        try {
            calc.scale(new int[] {1}, 2);
            throw new AssertionError("closed session was reused");
        } catch (IllegalStateException expected) {
            System.out.println("after close = rejected");
        }
    }
}
~~~

Đây là **tệp Java đầy đủ**. Vì `calc` được gán đúng một lần, nó là effectively final và có thể dùng trong `try (calc)`. App chỉ import `demo.api.CheckedCalc`; không import `RawCalc`, `Arena`, `MemorySegment`.

**Stdout của ứng dụng, trên native ABI và toolchain đúng:**

~~~text
scaled = [6, 12, 18]
empty = []
invalid value = rejected
invalid factor = rejected
after close = rejected
~~~

Các giá trị:

- `[2,4,6] × 3` ⇒ `[6,12,18]`.
- Empty input ⇒ wrapper trả empty output mà không gọi C.
- Giá trị `-1` bị Java validation từ chối.
- Factor `7` vượt `maxFactor=4` bị từ chối.
- Sau `try`, native session đã đóng; lần gọi `scale` tiếp theo bị Java từ chối, không dereference pointer C cũ.

Output chuẩn trên không bao gồm các dòng debug do bạn bật tracing/downcall logging. Mã C demo được thiết kế không in ra stdout.

## 8. Build C, generate bindings, compile Java, chạy ứng dụng

Các lệnh chạy tại thư mục gốc `checked-jextract`. Dùng compiler native cùng OS/CPU/bitness với JVM; code không cần `jni.h`.

### 8.1. Build native library

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -fPIC -shared \
  -I native native/securecalc.c -o libsecurecalc.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -fPIC -dynamiclib \
  -I native native/securecalc.c -o libsecurecalc.dylib
~~~

**Windows (Visual Studio Developer Command Prompt, cmd.exe):**

~~~bat
cl /LD /I native native\securecalc.c /Fe:securecalc.dll
~~~

Nếu dùng Windows MSVC, hãy chạy Developer Command Prompt để `cl` và linker được cấu hình. Output cần có native symbols `sc_open`, `sc_scale`, `sc_close`. Lệnh kiểm tra tùy nền tảng:

~~~text
Linux:   nm -D libsecurecalc.so
macOS:   nm -g libsecurecalc.dylib
Windows: dumpbin /EXPORTS securecalc.dll
~~~

Nếu không nhìn thấy symbols hoặc native DLL/.so không khớp phiên bản C header, dừng để sửa build; không thay descriptor Java một cách đoán mò.

### 8.2. Generate

**Linux/macOS:**

~~~bash
jextract \
  --output generated/src \
  --target-package demo.generated \
  --header-class-name RawCalc \
  --library securecalc \
  --use-system-load-library \
  native/securecalc.h
~~~

**Windows Command Prompt:**

~~~bat
jextract --output generated/src --target-package demo.generated --header-class-name RawCalc --library securecalc --use-system-load-library native\securecalc.h
~~~

Các lệnh này chỉ đúng khi bản jextract tương thích JDK target và có options như `--use-system-load-library`. Hãy kiểm tra `jextract --help`/`--version`. Không lấy bản jextract mới nhất mà không xem nó sinh code cho JDK bao nhiêu.

### 8.3. Compile generated và code viết tay

**Linux/macOS:**

~~~bash
mkdir -p build/classes
find generated/src src/main/java -name '*.java' > build/java-sources.txt
javac --release 22 -d build/classes @build/java-sources.txt
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes | Out-Null
$files = @(Get-ChildItem generated/src, src/main/java -Recurse -Filter *.java |
    ForEach-Object { $_.FullName })
javac --release 22 -d build/classes $files
~~~

Compile **toàn bộ generated sources**, không chỉ riêng `RawCalc.java` vì generator có thể sinh helpers/struct types dùng nội bộ. Nếu javac 22 báo thiếu method/API trong code sinh, kiểm tra jextract version/target FFM trước khi chỉnh wrapper.

### 8.4. Run

**Linux/macOS:**

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  -cp build/classes demo.app.Main
~~~

**Windows Command Prompt:**

~~~bat
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. -cp build\classes demo.app.Main
~~~

Vì generated binding được tạo với `--use-system-load-library`, `-Djava.library.path=.` cho phép `System.loadLibrary("securecalc")` tìm native binary trong thư mục đang đứng. Nếu thư viện có dependencies khác, OS loader search path vẫn có thể cần cấu hình riêng.

`--enable-native-access=ALL-UNNAMED` áp dụng cho code chạy trên classpath sử dụng restricted FFM methods. Named modules nên được cấp theo tên module thay vì cấp toàn bộ unnamed modules. JDK22 FFM đã final nên **không cần `--enable-preview` cho riêng FFM**.

## 9. Vòng đời resource và exception safety

### 9.1. Native session

~~~text
CheckedCalc(maxFactor)  -- validate --> sc_open
                                         |
                               non-NULL native pointer
                                         |
                                         v
                                       OPEN
                                         |
                              scale() 0..N lần
                                         |
                              close() (once)
                                         |
                              sc_close -> free
                                         |
                                         v
                                       CLOSED
                                         |
                         scale() -> IllegalStateException
                         close() -> no-op
~~~

C deallocator `sc_close` **không tự biết** Java đã từng gọi nó hay chưa. Wrapper giữ state `closed`, tuần tự hóa close/scale và không expose session pointer; đây là ba biện pháp kết hợp để giảm double-free/use-after-free.

### 9.2. Temporary native buffer

~~~text
scale(values, factor)
   |
   +-- Java validation
   |
   +-- try (Arena callArena = Arena.ofConfined())
         |
         +-- allocateFrom(JAVA_INT, values) -> native input
         +-- allocate(JAVA_INT, count)     -> native output
         +-- RawCalc.sc_scale(...)         -> C uses pointers only in call
         +-- if success: copy native output -> Java int[]
         |
         +-- callArena.close() at block exit
   |
   +-- return Java int[]
~~~

Nếu C báo lỗi hoặc Java ném exception trong try, **try-with-resources vẫn đóng Arena**. Với contract demo, C không giữ pointers sau return nên việc close lúc đó đúng.

**Phải thay thiết kế nếu native call bất đồng bộ** (callback hoặc native worker thread còn dùng input/output sau return). Khi ấy không thể đóng call-scoped arena ngay; cần ownership cho async task và chờ hoàn tất. Không chuyển mặc định mọi buffer sang `Arena.global()`, vì global allocations không được arena thu hồi trong vòng đời JVM.

### 9.3. Exceptions và partial failure

- Constructor validate fail: không gọi C, không có native session cần close.
- `sc_open` trả `NULL`: object chưa được tạo; ứng dụng nhận exception.
- `sc_scale` trả status != 0: **không copy output**; temporary Arena tự close.
- Java result-copy fail: temporary Arena cũng close.
- `close` idempotent phía facade: C `sc_close` được gọi tối đa một lần.
- Một native crash/ABI corruption **không được JVM biến chắc chắn thành Java exception**. Đây là lý do cần test native/library, không chỉ policy.

### 9.4. Tại sao không trông chờ vào GC?

Java `finalize()` không phải cơ chế dọn native handle đúng thời điểm. `Cleaner` có thể được xem là safety net cho resource bị quên, nhưng timing GC không xác định và một cleaner state giữ reference sai có thể khiến resource không bao giờ được thu hồi. **`AutoCloseable` + try-with-resources** là contract chính; nếu dùng Cleaner, phải thiết kế riêng và test ownership/double-free.

## 10. Kiểm tra dữ liệu ở đúng tầng, đúng đơn vị

### 10.1. Null, count, range

Trong facade:

~~~java
Objects.requireNonNull(values, "values");
if (values.length > MAX_ITEMS) {
    throw new IllegalArgumentException("too many items");
}
if (factor < 0 || factor > maxFactor) {
    throw new IllegalArgumentException("factor out of range");
}
~~~

Đây là **trích đoạn** của wrapper; constants và biến được định nghĩa trong lớp đầy đủ. C vẫn validate count/pointers/range vì raw bindings hoặc các caller native khác có thể đi vòng qua wrapper.

Một C `int*` chỉ mang địa chỉ, **không mang array length**. Java wrapper phải cấp số byte khớp với `count`. Với mảng lớn hoặc `long count` từ native API, dùng `Math.multiplyExact(count, elementBytes)` và quota, tránh arithmetic overflow trước khi cấp phát hoặc reinterpret pointers.

### 10.2. C string vs Java String

Nếu C function nhận `const char *utf8`, jextract có thể sinh carrier `MemorySegment`; wrapper phải chọn charset đúng, kiểm tra embedded NUL khi C API không cho phép, cấp NUL terminator và giữ buffer alive khi native còn dùng. JDK22 `arena.allocateFrom(String)` sinh UTF-8 null-terminated C string; không lấy `Java String.length()` làm số bytes UTF-8.

Nếu C API thao tác binary buffer, dùng pointer + byte length, không tự giả định có terminator hay encoding.

### 10.3. C struct và pointer ownership

Với một C struct pointer, jextract có thể sinh helper accessor/layout. Nhưng:

- `MemorySegment` có thể chỉ là zero-length pointer, không chứng minh backing allocation có đủ bytes.
- `reinterpret` chỉ thay spatial/temporal metadata, **không xác minh vùng nhớ thật**.
- A native struct returned *by-value* có hợp đồng khác một `struct*` returned pointer.
- Struct chứa pointer fields không được **deep-copy** chỉ vì wrapper copy struct bytes.
- Native deallocator của một pointer field không do `Arena.close()` của struct result tự gọi.

Chỉ expose Java values khi có thể, hoặc resource wrapper/borrowed handle với quyền sở hữu được ghi rõ.

## 11. Chính sách lỗi Java và native status codes

Trường hợp demo:

| C status | C ý nghĩa | Java wrapper xử lý |
|---|---|---|
| `0` | Thành công | Copy output và return `int[]` |
| `-1` | Session null | Invariant/lifetime failure |
| `-2` | Pointers/count sai | ABI/contract mismatch |
| `-3` | Factor sai | Contract/input failure |
| `-4` | Input value sai | Contract/input failure |

Trong code hoàn chỉnh, wrapper validate nên các status âm là dấu hiệu bất thường; nó ném `IllegalStateException` với code. Ứng dụng thật có thể ánh xạ theo domain:

- Invalid user input → `IllegalArgumentException`.
- Native I/O failure → exception mang C error details phù hợp.
- Native protocol failure → một exception custom chứa error code nhưng không leak pointer/address.
- Có thể retry nếu C API docs nói lỗi đó retryable và tài nguyên còn hợp lệ; **không** retry mù trên một session/pointer đã có trạng thái không xác định.

Mã sinh không thể tự quyết định error policy này, vì ý nghĩa status codes đến từ **business/native API contract** chứ không từ chữ ký `int`.

## 12. Test chiến lược hai tầng

### 12.1. Unit tests cho wrapper policy

Không phải mọi unit test đều cần load native library. Có thể tách một adapter interface viết tay để fake:

~~~java
// Trích đoạn thiết kế, không phải thành phần của chương trình chạy demo.
interface RawOperations {
    MemorySegment open(int maxFactor);
    int scale(
        MemorySegment session,
        MemorySegment input,
        int count,
        int factor,
        MemorySegment output
    );
    void close(MemorySegment session);
}
~~~

Adapter thật ủy quyền `RawCalc`; fake test kiểm tra số lần gọi, status codes và close semantics. Interface này thuộc **handwritten code**, không thuộc `generated/src`. Một project đơn giản có thể chưa cần abstraction, nhưng unit test policy và integration test ABI vẫn là hai mối quan tâm khác nhau.

Unit cases:

1. Constructor từ chối maxFactor ngoài `0..10` **trước** khi open native.
2. `scale(null,...)` báo lỗi rõ, không gọi C.
3. Array >64 phần tử bị từ chối trước allocate.
4. Values ngoài `0..10000` bị từ chối.
5. Factor âm hoặc vượt max bị từ chối.
6. Empty array trả `[]` và không gọi C.
7. Native status âm không khiến wrapper copy output.
8. `close()` gọi nhiều lần chỉ release session một lần.
9. `scale` sau close ném `IllegalStateException`.
10. Concurrent `scale`/`close` qua cùng facade không dùng session sau free.

### 12.2. Integration tests bắt buộc với C thật

Generated code compile thành công **không chứng minh runtime C ABI đúng**. Cần test:

- jextract target JDK/FFM tương thích.
- C header và native binary cùng phiên bản.
- Symbols được export và library/dependencies được load trên từng OS.
- Integer type widths, pointer size/ABI, alignment/struct packing khi API có structs.
- `sc_open`/`sc_scale`/`sc_close` chạy thực sự với dữ liệu hợp lệ và invalid.
- Native memory leak/double-free khi nhiều session được tạo và đóng.
- Call/close race trong các tình huống concurrency mục tiêu.
- Callback/async code không dùng buffer sau khi arena đóng (nếu API có).
- Output Java độc lập native Arena sau return.

Đối với bài này, **sanity test** chạy `demo.app.Main` và đối chiếu năm dòng stdout ở phần 7; các lỗi có thể nằm ngoài Java heap và cần native diagnostics phù hợp.

### 12.3. Gỡ lỗi với generated tracing

Một số bản jextract hỗ trợ:

~~~bash
java -Djextract.trace.downcalls=true \
  --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  -cp build/classes demo.app.Main
~~~

**Chỉ bật khi chẩn đoán**: tool có thể in native parameters, pointers và thông tin nhạy cảm. Khi so khớp stdout tự động, không bật tracing để tránh thêm dòng log. Các flags chẩn đoán phụ thuộc phiên bản jextract/JVM; kiểm tra tài liệu tương ứng.

## 13. Regenerate code có kiểm soát khi native header thay đổi

Nếu thêm field vào C struct, đổi tên function hoặc thay `int` bằng `size_t`, hãy xử lý theo thứ tự:

~~~text
C header/native API thay đổi
       |
       +--> Xác nhận C ABI, ownership và semantic compatibility
       |
       +--> Pin jextract + JDK + compiler/target OS
       |
       +--> Regenerate chỉ vào generated/src
       |
       +--> Review generated diff và compile
       |
       +--> Chỉnh facade adapter (nếu signature thay đổi)
       |
       +--> Chạy unit test policy + native integration test
       |
       +--> Publish versioned artifacts và tài liệu contract
~~~

**Đừng đưa generated API thành public contract của business layer.** Một thay đổi `sc_scale` từ `int count` sang `size_t count` có thể yêu cầu sửa facade và native tests, nhưng `CheckedCalc.scale(int[], int)` vẫn có thể giữ API cho callers nếu wrapper thực hiện validation/casting đúng.

### 13.1. Commit generated code hay sinh trong CI?

| Phương án | Thuận lợi | Trách nhiệm |
|---|---|---|
| Commit generated source và regenerate có kiểm soát | Build dễ tái lập, review diff rõ | Ngăn generated output stale so với header/tool |
| Generate trong CI từ version pinned | Source of truth là header/toolchain | CI cần jextract/clang/JDK tương thích, có kiểm tra diff |

Cả hai hợp lệ. Không để developer sửa tay một file generated rồi CI regenerate ghi mất nó. Với multi-platform C ABI, có thể cần generate/kiểm tra theo từng target vì C `long`, `size_t`, struct padding và macros khác nhau.

### 13.2. Version compatibility

- `jextract --version` xác định tool và JDK target.
- `java -version`, `javac -version` xác định runtime/compiler.
- C header cần khớp binary library.
- `--library` và cách load phải nhất quán giữa generate/run.
- JDK 22 FFM final không cần preview flags; JDK 21 preview không thể được xử lý bằng cách chỉ hạ `--release` của JDK22.

Không giả định **jextract latest** tương thích JDK22. Nếu jextract đang nhắm JDK mới hơn, chọn bản phù hợp với JDK deployment hoặc nâng cả toolchain có kiểm thử.

## 14. Anti-pattern và cách khắc phục

| Anti-pattern | Nguy cơ | Cách tốt hơn |
|---|---|---|
| Thêm validation bằng sửa trực tiếp generated Java | Regenerate ghi đè | Đặt validation trong facade |
| Business code gọi `RawCalc.sc_close` | Ownership bị phân tán | Một AutoCloseable quản lý handle |
| Trả native `MemorySegment` của confined arena | Dùng sau close | Copy sang Java value |
| Dùng `Arena.global` cho mọi request | Native memory không được thu hồi bởi arena | Bounded Arena và close đúng scope |
| Không check native status code | Dùng output chưa xác định | Fail-fast và error mapping |
| Cố gọi C với empty input khi C đòi count>0 | Native failure | Facade định nghĩa empty semantics rõ |
| Chỉ kiểm tra Boolean closed không lock với native call | Use-after-free race | Lock/owner-thread/refcount với close |
| Ngầm dùng Java String.length làm UTF-8 bytes | C đọc thiếu hoặc vượt | Xác nhận charset/byte length |
| Retain callback stub pointer sau arena close | Native callback tới vùng hết hạn | Quản lý callback lifetime theo C contract |
| Dùng `MemorySegment.ofAddress` rồi reinterpret số đoán | Không xác minh backing memory | Pointer+size contract hoặc copy |
| Gán mọi lỗi C thành `-1` không thông tin | Khó debug | Typed Java exception + status tracking |
| Chỉ test trên Linux rồi ship Windows | ABI/loader mismatch | CI native integration per target |
| Sinh bằng jextract khác JDK deployment | API/version mismatch | Pin cặp versions |

## 15. Câu hỏi và bài tập

1. Vì sao jextract có thể sinh phương thức nhận `MemorySegment` nhưng không biết con trỏ đó thuộc owned hay borrowed contract?
2. Ba tầng trong sơ đồ kiến trúc là gì? Tầng nào có quyền sửa validation?
3. Vì sao `src/main/java` không nên nằm bên trong `generated/src`?
4. Một native handle do `malloc` cấp được giải phóng bằng `Arena.close()` hay `sc_close`?
5. Nếu C function giữ pointer sau return, `Arena.ofConfined()` theo từng call còn phù hợp không?
6. Vì sao facade copy output thành Java `int[]` trước khi đóng call arena?
7. Khi nào sử dụng `synchronized` là đủ để tránh scale/close race, và khi nào nó không giải quyết yêu cầu native thread affinity?
8. Nếu `RawCalc.sc_open` trả `NULL`, wrapper xử lý thế nào?
9. Nếu native `sc_scale` trả status âm, vì sao không đọc output?
10. Cơ chế `--use-system-load-library` khác gì với `SymbolLookup.libraryLookup` mặc định?
11. Những phiên bản jextract và JDK cần tương thích ở bước nào?
12. Khi native API chuyển from `int count` sang `size_t count`, bạn phải xác nhận gì về ABI/overflow?
13. Vì sao cần test native binary thật dù Java unit tests đã PASS?
14. Một lớp viết tay có thể che generated classes khỏi business layer theo cách nào, và giới hạn của package/module boundaries là gì?
15. Làm sao test close idempotency mà không tạo double-free thực tế?
16. Vì sao một C string có NUL nội bộ làm việc đọc theo `strlen` khác với Java `String`?
17. Nếu native code trả borrowed pointer tới vùng static, nên có `close/free` ở Java không?
18. Điều gì xảy ra nếu CI regenerate Java code bằng jextract target JDK mới hơn nhưng ứng dụng deploy JDK22?
19. Nếu requirement thay đổi từ factor 0..10 sang 0..20, phải kiểm tra/chỉnh ở những lớp nào?
20. Tại sao kết quả `scale([]) = []` là quyết định của wrapper, chứ không phải từ jextract?

**Kết luận:** **Mã sinh bởi jextract là một ranh giới ABI thấp**, giúp Java gọi đúng native symbols, nhưng không phải API ứng dụng an toàn. Hãy tách generated sources khỏi handwritten facade, giữ Java API có validation và trạng thái sở hữu rõ ràng, dùng `AutoCloseable` cho owned native handles, `Arena.ofConfined()` cho buffers tạm, chuyển C status thành Java errors và trả Java values độc lập native memory. Duy trì tính đúng đắn bằng quy trình **pin header/binary/jextract/JDK, regenerate có kiểm soát, unit tests và native integration tests**.

### Tài liệu tham khảo chính thức

- [OpenJDK jextract — Guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md): command-line options, generated function wrappers, code organization và library loading.
- [Dev.java — Generate Java Bindings with jextract](https://dev.java/learn/ffm/jextract/): workflow sinh bindings và tích hợp C header.
- [Oracle Java SE 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html): ví dụ native binding/tool.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native memory lifetime, confined/shared/global scopes.
- [Oracle Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): `allocate` và `allocateFrom`.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): spatial/temporal bounds, carrier và native pointers.
- [JEP 454 — FFM Final (JDK22)](https://openjdk.org/jeps/454) và [JEP 442 — FFM Third Preview (JDK21)](https://openjdk.org/jeps/442): version alignment.
