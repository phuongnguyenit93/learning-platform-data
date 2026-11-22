# Nhận vùng nhớ do C cấp phát và bọc nó bằng tài nguyên có thể đóng

## Bài thực hành: quản lý ownership của bộ nhớ native bằng AutoCloseable

Khi một hàm C trả về con trỏ đến bộ nhớ do `malloc` hoặc một allocator riêng tạo ra, Java có thể đọc nội dung qua Foreign Function & Memory API (FFM). Nhưng **nhận được địa chỉ chưa đồng nghĩa Java biết vùng đó lớn bao nhiêu, tồn tại đến khi nào hoặc ai có trách nhiệm giải phóng**. Nếu dùng nhầm hàm free, đọc sau khi giải phóng hoặc quên trả tài nguyên, chương trình có thể rò rỉ bộ nhớ, crash JVM hoặc hỏng dữ liệu.

Bài này tạo một thư viện C cấp phát mảng số nguyên và một lớp Java triển khai `AutoCloseable`. Khi đối tượng Java được đóng, một cleanup action được đăng ký với `Arena` sẽ gọi đúng hàm C để trả lại vùng nhớ. Ví dụ dùng **Java 22+**, phiên bản FFM API đã chính thức (JEP 454); không dùng API incubator của các JDK cũ.

Sau khi thực hành, bạn cần giải thích được:

- Sự khác nhau giữa **vùng nhớ C sở hữu**, **vùng nhớ Java/FFM arena cấp phát** và **con trỏ C mượn tạm (borrowed pointer)**.
- Vì sao con trỏ C trả về qua FFM thường có `MemorySegment.byteSize() == 0`, và điều kiện nào cho phép `reinterpret` thành một view có kích thước.
- Cách gắn một **native cleanup callback** vào `Arena`, để `try-with-resources` đóng tài nguyên và gọi C release đúng một lần.
- Cách ngăn truy cập sau close, xử lý null pointer, lỗi khi chuyển ownership và tránh double free.
- Giới hạn của `Arena.ofConfined()`, các trường hợp đa luồng và cách kiểm tra native memory leak.

## 1. Thiết kế hợp đồng cấp phát trước khi viết Java

Thư viện C trong bài đưa ra hai hàm:

~~~c
int32_t *allocate_numbers(int32_t count);
void release_numbers(int32_t *pointer);
~~~

Hợp đồng của cặp hàm này:

| Điều cần biết | Quy định |
| --- | --- |
| Ai tạo bộ nhớ? | `allocate_numbers` dùng `malloc` bên C |
| Khi nào thành công? | `count > 0`, cấp đủ `count * sizeof(int32_t)` byte và trả pointer khác `NULL` |
| Khi thất bại? | Trả `NULL`; Java **không được dereference** |
| Ai sở hữu pointer sau khi C trả? | Java caller, cụ thể là wrapper `OwnedNumbers` |
| Giá trị phần tử thứ `i`? | `i + 1`, với `0 <= i < count` |
| Ai giải phóng? | Chính `release_numbers(pointer)`, đúng một lần |
| Khi nào hết hạn? | Sau khi wrapper đóng và native cleanup đã chạy |
| Luồng nào được đọc? | Một luồng sở hữu theo `Arena.ofConfined()` trong ví dụ |

**Không tự gọi `free` từ một thư viện C khác** khi allocator của thư viện trả pointer không công bố quyền đó. Trên Windows, sự khác biệt giữa các CRT hoặc allocator có thể làm việc giải phóng chéo không hợp lệ. Cách an toàn về thiết kế là C export cặp `create/destroy`, `allocate/release` hoặc `open/close`, rồi Java giữ đúng hợp đồng.

`MemorySegment.reinterpret` tạo alias/view, **không cấp phát hay sao chép**. Nó cũng không xác minh được C thực sự đã malloc bao nhiêu byte. Java chỉ được khai báo kích thước từ dữ liệu hợp đồng native đáng tin cậy.

## 2. Viết thư viện C cấp phát và trả bộ nhớ

Tạo file **`native/owned_numbers.c`**:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

#if defined(_WIN32)
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int32_t *allocate_numbers(int32_t count) {
    if (count <= 0) {
        return NULL;
    }

    size_t length = (size_t) count;
    if (length > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    int32_t *data = malloc(length * sizeof(int32_t));
    if (data == NULL) {
        return NULL;
    }

    for (int32_t i = 0; i < count; i++) {
        data[i] = i + 1;
    }

    return data;  // Ownership chuyển từ C sang caller.
}

EXPORT void release_numbers(int32_t *data) {
    free(data);
}
~~~

Điểm cần hiểu:

- `count <= 0` được coi là đầu vào không hợp lệ trong hợp đồng bài này; không nhầm `malloc(0)` có thể trả pointer đặc biệt với buffer hữu ích.
- Phép kiểm tra `SIZE_MAX / sizeof(int32_t)` giúp ngăn tràn trong phép nhân số byte. Cần include header thích hợp cho kiểu/constant (ở đây `<stdint.h>`, `<stddef.h>`, `<stdlib.h>`).
- `malloc` cấp memory phù hợp căn chỉnh thông thường của `int32_t`; C ghi đầy đủ `count` giá trị trước khi trả.
- `release_numbers` nhận **địa chỉ gốc** do `allocate_numbers` cấp; không truyền pointer đã tăng offset, không gọi hai lần cho cùng allocation.
- Nếu thư viện thật cấp phát nhiều cấu trúc bên trong, hàm `destroy` của nó cần tự cleanup các cấu trúc đó; Java không nên đoán sơ đồ cấp phát bên C.

Thư mục làm việc:

~~~text
native-ownership/
├── native/
│   └── owned_numbers.c
└── NativeOwnershipDemo.java
~~~

### Build shared library

Chạy **một** lệnh tương ứng hệ điều hành, từ thư mục `native-ownership`:

~~~bash
# Linux:
cc -std=c11 -O2 -fPIC -shared -o native/libowned_numbers.so native/owned_numbers.c

# macOS:
cc -std=c11 -O2 -fPIC -dynamiclib -o native/libowned_numbers.dylib native/owned_numbers.c

# Windows với MinGW-w64:
gcc -std=c11 -O2 -shared -o native/owned_numbers.dll native/owned_numbers.c
~~~

Phải cài compiler C phù hợp và tạo thư viện cùng kiến trúc/ABI với JVM. Tên thư viện dùng đúng quy tắc `System.mapLibraryName("owned_numbers")`. Không dùng compiler 32-bit để tạo DLL rồi nạp vào JVM 64-bit.

## 3. Lớp Java bọc con trỏ C bằng AutoCloseable

Tạo **`NativeOwnershipDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Objects;

public class NativeOwnershipDemo {

    static final class OwnedNumbers implements AutoCloseable {
        private static final MethodHandle ALLOCATE;
        private static final MethodHandle RELEASE;

        static {
            try {
                Path library = Path.of(
                        "native", System.mapLibraryName("owned_numbers"))
                        .toAbsolutePath();

                // Library còn sống đến hết process; cleanup vẫn gọi được.
                SymbolLookup symbols =
                        SymbolLookup.libraryLookup(library, Arena.global());
                Linker linker = Linker.nativeLinker();

                ALLOCATE = linker.downcallHandle(
                        symbols.find("allocate_numbers").orElseThrow(),
                        FunctionDescriptor.of(
                                ValueLayout.ADDRESS,
                                ValueLayout.JAVA_INT));

                RELEASE = linker.downcallHandle(
                        symbols.find("release_numbers").orElseThrow(),
                        FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));
            } catch (Throwable error) {
                throw new ExceptionInInitializerError(error);
            }
        }

        private final Arena arena;
        private final MemorySegment elements;
        private final int length;
        private boolean closed;

        private OwnedNumbers(
                Arena arena, MemorySegment elements, int length) {
            this.arena = arena;
            this.elements = elements;
            this.length = length;
        }

        static OwnedNumbers allocate(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException("count must be > 0");
            }

            // Tính trên long, rồi dùng đúng count đã yêu cầu từ C.
            long bytes = Math.multiplyExact(
                    (long) count, ValueLayout.JAVA_INT.byteSize());
            Arena arena = Arena.ofConfined();

            MemorySegment raw;
            try {
                raw = (MemorySegment) ALLOCATE.invokeExact(count);
            } catch (Throwable failure) {
                arena.close();
                throw new IllegalStateException(
                        "C allocation call failed", failure);
            }

            if (raw.address() == 0L) {
                arena.close();
                throw new OutOfMemoryError("C allocator returned NULL");
            }

            MemorySegment view;
            try {
                // Pointer từ C chưa mang chiều dài mảng.
                // reinterpret tạo view có kích thước, scope và cleanup.
                view = raw.reinterpret(bytes, arena, pointer -> {
                    try {
                        RELEASE.invokeExact(pointer);
                    } catch (Throwable failure) {
                        throw new IllegalStateException(
                                "C release call failed", failure);
                    }
                });
            } catch (RuntimeException | Error failure) {
                // Đã nhận pointer nhưng chưa chuyển được ownership
                // cho cleanup: giải phóng ngay theo nhánh lỗi.
                try {
                    RELEASE.invokeExact(raw);
                } catch (Throwable cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
                try {
                    arena.close();
                } catch (RuntimeException closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
                throw failure;
            }

            return new OwnedNumbers(arena, view, count);
        }

        int length() {
            return length;
        }

        int get(int index) {
            if (closed) {
                throw new IllegalStateException("Resource already closed");
            }
            Objects.checkIndex(index, length);
            return elements.getAtIndex(ValueLayout.JAVA_INT, index);
        }

        @Override
        public void close() {
            if (closed) {
                return;  // Lớp wrapper có close idempotent.
            }

            // Đóng scope Java và chạy C release qua cleanup action.
            arena.close();
            closed = true;
        }
    }

    public static void main(String[] args) {
        OwnedNumbers retained;

        try (OwnedNumbers numbers = OwnedNumbers.allocate(4)) {
            retained = numbers;
            int sum = 0;

            for (int i = 0; i < numbers.length(); i++) {
                sum += numbers.get(i);
            }

            System.out.println("first=" + numbers.get(0));
            System.out.println("last=" + numbers.get(3));
            System.out.println("sum=" + sum);
        }

        // Không dereference pointer sau free: chỉ kiểm tra guard Java.
        try {
            retained.get(0);
        } catch (IllegalStateException expected) {
            System.out.println("closed=true");
        }

        retained.close();
        System.out.println("second close=ok");
    }
}
~~~

### Biên dịch và chạy

Từ `native-ownership` sau khi đã tạo shared library:

~~~bash
javac NativeOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED NativeOwnershipDemo
~~~

Kết quả **dự kiến** khi build và chạy đúng:

~~~text
first=1
last=4
sum=10
closed=true
second close=ok
~~~

Bài không đưa số liệu benchmark; stdout trên là kết quả logic của C khởi tạo `[1, 2, 3, 4]` và Java cộng các phần tử. Đường dẫn thư viện được tính từ **current working directory** lúc chạy Java; nếu chạy từ nơi khác phải sửa path hoặc đặt lại working directory. Một số thao tác FFM gồm native library lookup, linker và reinterpret là restricted; cờ `--enable-native-access=ALL-UNNAMED` bật quyền cho lớp trong unnamed module. Với named module, cấp quyền cho đúng tên module.

## 4. Giải thích các bước chuyển ownership

### 4.1. Downcall trả pointer, không trả array Java

`FunctionDescriptor.of(ValueLayout.ADDRESS, ValueLayout.JAVA_INT)` mô tả C function nhận `int32_t` và trả pointer. `ALLOCATE.invokeExact(count)` trả `MemorySegment` đại diện địa chỉ native. Java không biết kích thước bộ nhớ chỉ từ địa chỉ nên segment trả về từ pointer thường có **size 0**. Không đọc `raw.getAtIndex(...)` trực tiếp.

Java biết số phần tử hợp lệ nhờ hợp đồng C: `count * sizeof(int32_t)`. Sau khi kiểm tra pointer khác null, `raw.reinterpret(bytes, arena, cleanup)` tạo view trên **cùng vùng nhớ** có size và scope tương ứng. Khai báo `bytes` lớn hơn allocation thực là nguy hiểm: FFM không thể tự kiểm chứng kích thước malloc nằm bên ngoài Java.

### 4.2. Arena chỉ định lifetime và giới hạn thread

`Arena.ofConfined()` tạo scope chỉ được truy cập từ thread sở hữu. Segment `view` gắn scope này; sau `arena.close()`, truy cập view không còn hợp lệ. Confined arena phù hợp với bài thực hành một thread, giúp tránh vô tình đọc từ worker khác. Trong ứng dụng đa luồng, `Arena.ofShared()` cho phép truy cập từ nhiều thread nhưng **không tự đồng bộ dữ liệu**; mọi reader/writer/native callback phải được điều phối trước khi close.

### 4.3. Cleanup action gọi native free

Ở ví dụ, đối số cuối của `reinterpret(bytes, arena, pointer -> ...)` đăng ký hành động chạy khi scope arena đóng. Callback nhận một segment đại diện cho địa chỉ native được chuẩn bị cho cleanup, rồi gọi đúng `release_numbers` bằng `RELEASE.invokeExact(pointer)`.

**Không được kết hợp** cleanup action này với một lời gọi `release_numbers` thứ hai trong `close()`. Điều đó tạo double free. Ở đây wrapper `close()` chỉ gọi `arena.close()`; chính việc đóng arena kích hoạt cleanup C. Bộ nhớ C không phải do arena cấp phát nên nếu bỏ callback, việc đóng arena đơn thuần **không giải phóng malloc buffer**.

### 4.4. try-with-resources ngăn quên đóng

Đối tượng `OwnedNumbers` triển khai `AutoCloseable`, cho phép:

~~~java
try (OwnedNumbers numbers = OwnedNumbers.allocate(4)) {
    System.out.println(numbers.get(0));
} // numbers.close() tự chạy, kể cả khi khối try ném lỗi.
~~~

Đây là **đoạn minh họa** đặt trong cùng class `NativeOwnershipDemo` hoặc nơi truy cập được `OwnedNumbers`. Không phụ thuộc vào garbage collector, finalizer hay việc JVM kết thúc để release native memory. Tính chất idempotent của wrapper `close()` được thực hiện bằng biến `closed`; bản thân `Arena.close()` không idempotent và gọi đóng arena hai lần có thể ném `IllegalStateException`.

### 4.5. Giữ thư viện C sống đủ lâu

`SymbolLookup.libraryLookup(path, Arena.global())` gắn lifetime của thư viện C với global arena: native function `release_numbers` vẫn sẵn khi cleanup action chạy. Nếu dùng arena riêng để load/unload thư viện, phải đóng hết resources còn sống **trước khi unload** thư viện chứa native release function. Không giữ MethodHandle trỏ đến code native đã unload.

## 5. Dòng thời gian resource

| Trạng thái | Vùng nhớ C | Java wrapper | Được phép đọc? |
| --- | --- | --- | --- |
| Chưa cấp phát | Chưa tồn tại | Chưa có | Không |
| `allocate_numbers` thành công | Tồn tại, ownership được chuyển | Kiểm tra null/size | Chưa đọc qua raw pointer |
| `reinterpret` hoàn tất | Tồn tại, cleanup gắn arena | `OwnedNumbers` mở | Có, đúng thread và index |
| Trong khối `try-with-resources` | Tồn tại | Dùng `get` | Có |
| Kết thúc khối `try` | `release_numbers` đã gọi | `closed=true` sau close bình thường | Không |
| Gọi `close()` lần hai | Đã release | Wrapper bỏ qua | Không |
| Gọi `get()` sau close | Đã release | Ném `IllegalStateException` | Không |

Một nguồn leak phổ biến là cấp phát C rồi ném exception trước khi tạo wrapper. Ví dụ xử lý nhánh đó bằng cách release `raw` nếu không gắn được cleanup, và đóng arena tạm. Khi thiết kế sản phẩm thật, cần kiểm soát mọi đường lỗi giữa bước “C đã cấp phát” và bước “ownership đã được chuyển an toàn”. Một callback cleanup ném exception trong lúc `Arena.close()` cũng cần được giám sát: không nên giả định việc release native có thể retry tùy ý.

## 6. Sở hữu, mượn và chuyển giao: ba trường hợp không được lẫn

| Nguồn pointer | Owner thật | Quy tắc release |
| --- | --- | --- |
| `arena.allocate(...)` của Java FFM | Arena tạo ra segment | Đóng arena; không gọi C free |
| `malloc`/allocator của C, trả quyền sở hữu | Wrapper Java sau khi nhận | Dùng đúng C release một lần khi close |
| C trả borrowed/static pointer | Thư viện/đối tượng C | Java **không free**; bảo đảm native owner còn sống |
| C giữ pointer do Java cấp để xử lý bất đồng bộ | Tùy giao thức API đã thỏa thuận | Giữ Java arena sống tới khi C thực sự dùng xong; chỉ đóng sau khi hoàn tất |

Một native API kiểu `get_internal_buffer` có thể trả pointer không thuộc quyền sở hữu Java. Gắn callback `free` lên pointer đó là lỗi nghiêm trọng. Nếu API trả pointer cùng length bằng struct hoặc out-parameter, Java phải đọc length đáng tin cậy và xác nhận bounds trước khi reinterpret. Nếu dữ liệu có thể bị realloc hoặc invalidated bởi C, không được giữ view cũ rồi tiếp tục đọc.

## 7. Những rủi ro và cách kiểm tra

**Null pointer:** C có thể trả null do allocation failure. Wrapper kiểm tra `raw.address() == 0L` và không dereference. Nếu API dùng `NULL` làm kết quả hợp lệ cho mảng rỗng, cần thay hợp đồng và representation của Java cho phù hợp; bài này từ chối `count <= 0`.

**Size mismatch:** `reinterpret(4096, ...)` không khiến C thật sự malloc 4096 byte. Khai báo vượt kích thước, dùng sai layout hoặc offset có thể gây corruption/crash dù `MemorySegment` có kiểm tra bounds theo size Java khai báo.

**Sai allocator:** C cấp bằng custom allocator thì phải trả bằng đúng native destroy/release. Trên một số môi trường, dùng `free` từ CRT khác hoặc `delete` cho vùng nhớ từ `malloc` là undefined behavior.

**Use-after-free:** API Java trong bài không expose raw pointer và kiểm tra `closed` trước `get`. Nhưng nếu đã chuyển con trỏ thô cho native C code khác, scope của Java không bảo vệ được mã native khỏi dereference sau khi free. Phải chờ mọi native use hoàn tất trước close.

**Double free:** Cleanup của `reinterpret` và code `close` không được cùng gọi C release. Mỗi tài nguyên phải có **một owner chịu trách nhiệm duy nhất**. Nếu dùng multiple views cùng một allocation, chúng không được đăng ký các cleanup độc lập cùng giải phóng một địa chỉ.

**Truy cập từ thread khác:** Ví dụ là confined/single-thread. Nếu thread khác gọi `get`, FFM có thể ném `WrongThreadException`. Tránh biến boolean `closed` không đồng bộ thành một lifecycle manager đa luồng. Nếu cần shared, cần protocol ownership/concurrency và bảo đảm không close khi native downcall, reader hoặc writer còn dùng pointer.

**Native cleanup có thực sự chạy?** Việc `closed=true` và đọc sau close bị từ chối không chứng minh riêng rằng C không leak. Hãy dùng AddressSanitizer, Valgrind (nền tảng phù hợp), native memory profiler, hoặc bộ đếm allocate/release ở thư viện C. Đo nhiều vòng cấp phát/đóng và theo dõi memory ổn định sau warmup.

## 8. Bài tập tự kiểm tra

1. **Bounds:** Đổi `allocate(4)` thành `allocate(8)`; tổng đúng là `36`. Thử `get(8)` trước close: phải ném `IndexOutOfBoundsException`.
2. **Invalid input:** Gọi `allocate(0)`: phải ném `IllegalArgumentException` mà không cấp phát C.
3. **Exception safety:** Trong khối try-with-resources, cố ý ném một Java exception sau lần đọc đầu tiên; xác nhận cleanup vẫn được gọi.
4. **Idempotent close:** Giữ biến tham chiếu wrapper, gọi `close()` thêm lần nữa; kiểm tra C không release cùng pointer hai lần.
5. **Borrowed pointer:** Thử phác thảo API C trả vùng nhớ static; giải thích vì sao không được dùng `release_numbers` cho pointer này.
6. **Struct phức tạp:** Nếu C trả opaque handle chứa nhiều allocation, hãy tạo một hàm `destroy_handle` giải phóng nội bộ đúng thứ tự; Java chỉ gắn callback destroy một lần.
7. **Đa luồng:** Nếu phải chuyển wrapper sang thread khác, xác định cách chọn scope và điều phối close; đừng đổi `ofConfined()` thành `ofShared()` rồi giả định mọi truy cập an toàn.

## 9. Checklist trước khi dùng với native library thật

- [ ] Đã xác định rõ pointer là owned hay borrowed và ai phải release?
- [ ] Dùng đúng hàm release từ chính thư viện/allocator đã tạo ra pointer?
- [ ] Đã kiểm tra null, số phần tử, overflow, layout, byte order và alignment?
- [ ] Chỉ reinterpret theo kích thước C thực sự bảo đảm?
- [ ] Đã đăng ký **một** cleanup action hoặc dùng một close path chính xác?
- [ ] Wrapper hạn chế việc rò rỉ alias/raw pointer cho code ngoài?
- [ ] Mọi lỗi giữa alloc và attach ownership đều có đường cleanup?
- [ ] try-with-resources được dùng ở caller và tránh double close native?
- [ ] Có chính sách thread confinement, callback và bất đồng bộ rõ ràng?
- [ ] Đã dùng công cụ native để kiểm tra leak, double free và use-after-free?

## Tài liệu đọc thêm

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API chính thức từ Java 22.
- [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): `reinterpret`, segment scope, spatial và temporal safety.
- [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): vòng đời, confined/shared và `close()`.
- [Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): native downcall handle và function descriptor.
- [dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): C pointers, segment size 0 và cleanup action.

**Nguyên tắc chính:** Một wrapper native-memory tốt là một **resource owner có hợp đồng rõ ràng**: biết địa chỉ, kích thước, phạm vi truy cập và đúng một hành động release. `AutoCloseable` cùng `try-with-resources` đưa trách nhiệm giải phóng đó vào vòng đời có thể kiểm chứng của mã Java.