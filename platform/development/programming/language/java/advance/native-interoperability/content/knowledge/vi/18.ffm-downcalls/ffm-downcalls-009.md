# Thu trạng thái errno hoặc lỗi nền tảng bằng captureCallState

## Mục tiêu

Khi Java gọi hàm C qua **Foreign Function & Memory API (FFM)**, nhiều native function báo lỗi bằng **giá trị trả về** và đồng thời đặt một trạng thái lỗi của **thread đang chạy**, thay vì tự ném Java exception. Trên hệ C/POSIX, trạng thái điển hình là **errno**. Trên Windows, nhiều Win32 API dùng **GetLastError**, còn Winsock có **WSAGetLastError**. Không thể đọc tất cả các lỗi này bằng cách chỉ xem return value, và cũng không thể giả định Java runtime sẽ giữ nguyên thread-local error state sau khi native function kết thúc.

Từ JDK 22 (FFM API chuẩn hóa, JEP 454), **Linker.Option.captureCallState(...)** cho phép gắn một thao tác **chụp trạng thái lỗi ngay sau downcall** vào chính **MethodHandle** gọi hàm native. Kết quả được ghi vào một **MemorySegment** do ứng dụng cung cấp, có cấu trúc được mô tả bằng **Linker.Option.captureStateLayout()**.

Bài học tập trung vào:

1. Đọc đúng hợp đồng lỗi của native function: return value, errno, Win32 last error và Winsock error.
2. Tạo downcall với **captureCallState("errno")** hoặc tên trạng thái nền tảng hỗ trợ.
3. Cấp phát capture-state segment đúng kích thước/alignment và đọc bằng **VarHandle**.
4. Hiểu vị trí tham số **MemorySegment** bổ sung trong **MethodHandle**, khác với tham số C thực tế.
5. Chạy một ví dụ C + Java có kiểm chứng errno mà không hard-code con số EINVAL cho mọi hệ.
6. Tránh đọc lỗi cũ, đọc sai thread, dùng lại buffer khi nhiều luồng hoặc kết hợp sai **critical** option.

**Phiên bản:** Ví dụ Java đầy đủ dùng **java.lang.foreign** chuẩn ở **JDK 22+**. JDK 21 dùng preview và các API incubator ở JDK 17 khác với ví dụ. Một số JDK sau này có thể bổ sung tính năng, nhưng những mô tả và đoạn code chính bên dưới nhắm vào **hợp đồng JDK 22**, nên chỉ cần lệnh **javac/java** bình thường kèm **--enable-native-access=ALL-UNNAMED** khi thực hiện restricted native operations.

## 1. Vì sao cần bắt lỗi ngay sau foreign call?

Xét một hàm C:

~~~c
#include <errno.h>

int parse_native_input(void) {
    errno = EINVAL;
    return -1;
}
~~~

Nếu Java gọi hàm đó qua FFM downcall, có hai thành phần ý nghĩa:

- **return = -1**: theo hợp đồng riêng của hàm, đây là tín hiệu thất bại.
- **errno = EINVAL**: thêm thông tin loại lỗi tại thread native đã chạy lời gọi.

Đó là **một fragment C**, không phải chương trình độc lập và không khẳng định mọi hàm C đều trả -1 khi lỗi. Có hàm trả **NULL**, **EOF**, giá trị âm khác, mã lỗi trực tiếp, hoặc một cấu trúc. Một số hàm **không dùng errno**, hay chỉ đặt errno trong một số trường hợp cụ thể. **Phải đọc tài liệu native function trước khi chọn cách phân tích lỗi.**

Một lỗi thiết kế thường gặp:

~~~text
Java gọi hàm C -> C đặt errno -> FFM trả về Java
                                  |
                           Java gọi hàm khác
                                  |
                           thử đọc errno muộn
                                  |
                         có thể đã bị thay đổi
~~~

**errno là trạng thái thread-local**, thường được biểu diễn bởi macro trong thư viện C, không phải một số nguyên global bất biến mà Java có thể tùy ý đọc lúc nào cũng được. Java/VM hoặc một native call kế tiếp có thể tác động đến trạng thái đó. Việc tìm địa chỉ **errno** như một symbol biến toàn cục cũng không portable.

**captureCallState** giải quyết vấn đề *thời điểm chụp*: khi downcall kết thúc, linker lấy các giá trị được yêu cầu ngay trong cơ chế gọi native và ghi vào segment snapshot, trước khi những thao tác tiếp theo có thể làm mất giá trị cần đọc.

Lược đồ:

~~~text
          Java application
               |
               | MethodHandle với captureCallState("errno")
               v
       +--------------------+
       | native C function  |
       | return result      |
       | set thread errno   |
       +--------------------+
               |
               v
      Linker tự chụp errno
               |
               +--> capture-state MemorySegment
               |
               v
         Java tiếp tục chạy
               |
               +--> kiểm tra return value
               +--> nếu thất bại, đọc errno từ snapshot
~~~

**Chụp trạng thái không tự biến native failure thành exception.** Java vẫn phải kiểm tra return code hoặc contract của API và quyết định có ném exception, retry, ghi log hay xử lý fallback không.

## 2. captureCallState là Linker.Option, không phải hàm đọc errno

Các API cốt lõi trên JDK 22:

~~~java
Linker.Option option =
        Linker.Option.captureCallState("errno");

StructLayout stateLayout =
        Linker.Option.captureStateLayout();
~~~

**captureCallState(String... capturedState)** tạo một **linker option** định nghĩa tên trạng thái nào cần chụp. Tên hỗ trợ là platform-dependent và phân biệt chữ hoa/thường theo tên chính xác.

**captureStateLayout()** trả một **StructLayout** biểu diễn vùng lưu các trạng thái được platform hỗ trợ. Layout này có thể chứa các **ValueLayout đặt tên** và **padding**. Không được tự giả định errno nằm ở byte offset 0, layout có đúng 4 byte, hay Windows có cùng fields như Linux.

Một số trạng thái thường được tài liệu JDK mô tả:

| Tên capture | Hệ sinh thái | Nguồn ý nghĩa |
| --- | --- | --- |
| **"errno"** | C runtime / POSIX và các môi trường có hỗ trợ | Lỗi kiểu C runtime **errno** của thread hiện tại |
| **"GetLastError"** | Windows Win32, khi nền tảng hỗ trợ | Mã lỗi cuối của Windows API theo contract từng hàm |
| **"WSAGetLastError"** | Windows Winsock, khi nền tảng hỗ trợ | Mã lỗi Winsock cho socket API |

Tên **GetLastError/WSAGetLastError** không được kỳ vọng tồn tại trên Linux hoặc macOS. Không tự chuyển lỗi Winsock sang errno; đây là các error domains khác nhau với ý nghĩa và bảng mã khác nhau.

**Nếu chọn tên không được platform hỗ trợ, captureCallState có thể ném IllegalArgumentException ngay khi tạo option.** Trước khi liên kết, hãy kiểm tra danh sách tên bằng layout thực tế.

### Liệt kê tên trạng thái được hỗ trợ

**File CaptureNames.java:**

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.util.List;
import java.util.Optional;

public class CaptureNames {
    public static void main(String[] args) {
        StructLayout layout = Linker.Option.captureStateLayout();

        List<String> names = layout.memberLayouts().stream()
                .map(MemoryLayout::name)
                .flatMap(Optional::stream)
                .sorted()
                .toList();

        System.out.println("capture layout bytes = "
                + layout.byteSize());
        System.out.println("supported states: " + names);
    }
}
~~~

Chạy JDK 22+:

~~~bash
javac CaptureNames.java
java CaptureNames
~~~

**Output phụ thuộc nền tảng.** Một bản JDK Linux điển hình có thể liệt kê **errno**; bản JDK Windows có thể liệt kê **errno**, **GetLastError**, **WSAGetLastError**. Không đưa một stdout cố định cho chương trình này vì số field và padding phụ thuộc JDK/ABI. Giá trị **layout.byteSize()** cũng không phải một hằng có thể hard-code cho mọi platform.

**Chú ý:** **captureStateLayout()** mô tả các trạng thái *có thể hỗ trợ*, còn **captureCallState(...)** xác định các trạng thái thực sự được yêu cầu lưu. Nếu chỉ capture **errno**, đừng coi các trường khác có trong layout là snapshot hợp lệ của cùng lời gọi.

## 3. Liên kết downcall với captureCallState

Giả sử native C có chữ ký:

~~~c
int fail_with_einval(void);
~~~

Mô tả **chữ ký native**:

~~~java
FunctionDescriptor descriptor =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);
~~~

Native function **không nhận tham số C** và trả về int. Nếu lấy được symbol **target**, liên kết:

~~~java
MethodHandle fail = Linker.nativeLinker().downcallHandle(
        target,
        FunctionDescriptor.of(ValueLayout.JAVA_INT),
        Linker.Option.captureCallState("errno"));
~~~

**Đây là fragment**; **target** phải là symbol MemorySegment hợp lệ. Điểm thường gây nhầm là **MethodHandle** trên Java có thêm một tham số để giao capture-state segment, mặc dù hàm C **không** có tham số ấy:

~~~text
Hàm C:                 int fail_with_einval(void)

MethodHandle Java:     (MemorySegment capturedState) -> int

Gọi từ Java:           int result =
                            (int) fail.invokeExact(capturedState);
~~~

**capture-state segment là tham số được linker sử dụng**, không được truyền thành đối số cho hàm C thật. Nếu thêm nó vào **FunctionDescriptor** như một tham số ADDRESS của C thì đó là **chữ ký native sai**, có thể dẫn đến crash/undefined behavior.

### Bound versus unbound downcall handle

Có hai cách liên kết thường gặp:

- **Bound handle:** **downcallHandle(target, descriptor, option)** đã gắn địa chỉ hàm, nên code Java truyền **capturedState** rồi tới các native arguments bình thường.
- **Unbound handle:** **downcallHandle(descriptor, option)** để địa chỉ hàm được cung cấp khi invoke; code Java truyền **targetAddress** trước, sau đó là **capturedState** và các native arguments.

Với hàm C **int add_and_set_error(int x)** chẳng hạn:

~~~text
C:                      int f(int x)

Bound Java handle:      (MemorySegment capturedState, int x) -> int

Unbound Java handle:    (MemorySegment targetAddress,
                         MemorySegment capturedState, int x) -> int
~~~

Đây là sơ đồ cho một hàm trả scalar. Nếu native function **trả struct by value**, linker có thể cần thêm **SegmentAllocator** và thứ tự tham số đặc biệt; luôn xem **MethodHandle.type()** và JDK javadoc cho đúng descriptor/option thực tế thay vì tự đoán.

Một sai lầm thường gặp là cố gọi bound handle như bình thường mà quên state:

~~~java
// Sai nếu handle được link với captureCallState:
int value = (int) fail.invokeExact();
~~~

Lệnh này sẽ gặp **WrongMethodTypeException** hoặc mismatch khi invoke, vì downcall handle đã có tham số capture state.

## 4. Cấp phát đúng capture-state segment và đọc field

Để đọc errno:

~~~java
StructLayout stateLayout =
        Linker.Option.captureStateLayout();

VarHandle errnoField = stateLayout.varHandle(
        MemoryLayout.PathElement.groupElement("errno"));
~~~

**VarHandle** truy cập field có tên **errno** trong StructLayout. Nó lấy offset và alignment từ layout, không cần hard-code vị trí.

Cấp phát **native MemorySegment** với đúng layout:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment captured = arena.allocate(stateLayout);

    int result = (int) fail.invokeExact(captured);
    int errnoValue = (int) errnoField.get(captured, 0L);

    // Phân tích result và errnoValue theo contract của hàm.
}
~~~

Đây là **fragment** của phương thức khai báo **throws Throwable** và đã có **fail**, **stateLayout**, **errnoField**. **0L** là base offset trong cách dùng VarHandle của **MemoryLayout.varHandle** tại JDK 22; hàm **get** có tọa độ **(MemorySegment, long)**.

**Tại sao dùng arena.allocate(stateLayout)?**

- Segment được allocate theo **byteSize** và **byteAlignment** do JDK trả.
- Capture-state được lưu trong memory native, thuộc phạm vi truy cập của thread.
- Trong **try-with-resources**, segment không bị giải phóng trước khi code đọc.
- Không cần đoán size/align errno riêng hay số lượng field của platform.

Không dùng một **MemorySegment.ofArray(byte[])** nhỏ tùy ý hoặc đặt state vào một object Java rồi kỳ vọng linker nhận nó như một native capture-state buffer. **captureCallState** yêu cầu một native segment có kích thước/alignment tương thích với **captureStateLayout()**.

**Đọc trạng thái sau downcall** là đủ; bạn không cần gọi lại một hàm native để đọc errno. Đọc sau khi đã đóng arena sẽ sai lifetime. Nếu state nằm trong shared arena và được dùng từ nhiều threads, không để các threads ghi cùng vùng capture-state một cách đồng thời.

### Cần đặt errno về 0 trước lời gọi không?

Có những native function được tài liệu yêu cầu caller xóa errno trước khi gọi, vì return value có thể hợp lệ dù bằng giá trị sentinel. Khi đó việc reset phải tuân theo contract native cụ thể, thực hiện ngay trên **thread dùng để downcall**, theo cách portable/đúng ABI (ví dụ thông qua một helper C).

**Đừng nhầm việc ghi 0 vào capture-state segment với việc xóa thread-local errno thực.** Trong **JDK 22**, captureCallState là cơ chế **chụp sau lời gọi**. Nó không phải lời hứa rằng gọi **errnoField.set(captured, 0L, 0)** sẽ thực sự set errno=0 của C runtime. Nếu cần reset errno, hãy thực hiện bằng cơ chế native thích hợp rồi gọi hàm cần kiểm tra; capture-state segment là nơi lưu snapshot mà linker viết sau downcall.

## 5. Demo end-to-end Linux: tạo lỗi errno có kiểm soát

Để không dựa vào việc một file có tồn tại hay mã **EINVAL** bằng bao nhiêu trên máy, ta xây một thư viện C nhỏ gồm hai hàm:

1. **fail_with_einval()** đặt errno=EINVAL rồi trả -1.
2. **native_einval()** trả hằng EINVAL của chính C runtime được dùng để build thư viện.

Chương trình Java chụp errno của lần gọi thứ nhất và so sánh với hằng trả từ lần gọi thứ hai. Kết quả kiểm tra **true** nếu capture hoạt động, bất kể EINVAL có giá trị 22, 22 ở platform phổ biến khác, hoặc một số khác trên một ABI hỗ trợ.

### 5.1. File native: probe_errno.c

~~~c
#include <errno.h>

/*
 * Trên Linux, visibility attribute làm symbol dễ được tìm thấy trong .so.
 * Đây là code C11 cho ví dụ Linux GCC/Clang.
 */
#if defined(__GNUC__)
#define EXPORT __attribute__((visibility("default")))
#else
#define EXPORT
#endif

EXPORT int fail_with_einval(void) {
    errno = EINVAL;
    return -1;
}

EXPORT int native_einval(void) {
    return EINVAL;
}
~~~

**Giải thích:** **errno** là macro truy cập error state của thread C. **EINVAL** là mã lỗi cho invalid argument trong C/POSIX, nhưng giá trị số phụ thuộc platform. Hàm native luôn trả **-1** và luôn set **errno=EINVAL** trước khi trả về. Hàm **native_einval** cung cấp hằng đối chiếu mà không buộc Java code hard-code mã lỗi.

Các hàm không nhận tham số, trả **C int**. Trên Linux/x86-64 hay nhiều ABI phổ biến, C int tương ứng Java **ValueLayout.JAVA_INT** (4 byte). Đây là giả định ABI của ví dụ; với thư viện thật cần kiểm tra canonical C int layout và đúng calling convention.

### 5.2. File Java: CaptureErrnoDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.file.Path;

public class CaptureErrnoDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        StructLayout capturedLayout =
                Linker.Option.captureStateLayout();

        VarHandle errnoField = capturedLayout.varHandle(
                MemoryLayout.PathElement.groupElement("errno"));

        try (Arena arena = Arena.ofConfined()) {
            // File .so được build tại thư mục "build" của dự án.
            Path library = Path.of(
                    "build", "liberrno_probe.so").toAbsolutePath();

            SymbolLookup nativeLib =
                    SymbolLookup.libraryLookup(library, arena);

            MemorySegment failSymbol = nativeLib
                    .find("fail_with_einval").orElseThrow();
            MemorySegment expectedSymbol = nativeLib
                    .find("native_einval").orElseThrow();

            FunctionDescriptor noArgInt =
                    FunctionDescriptor.of(ValueLayout.JAVA_INT);

            // Bound handle: capture segment là tham số đầu.
            MethodHandle fail = linker.downcallHandle(
                    failSymbol,
                    noArgInt,
                    Linker.Option.captureCallState("errno"));

            // Handle thường: native_einval(void) trả một int.
            MethodHandle expectedHandle = linker.downcallHandle(
                    expectedSymbol,
                    noArgInt);

            MemorySegment captured = arena.allocate(capturedLayout);

            // Linker chụp errno vào captured ngay sau native call.
            int result = (int) fail.invokeExact(captured);
            int errnoValue = (int) errnoField.get(captured, 0L);

            // Một downcall khác không thể thay đổi snapshot đã lưu.
            int expected = (int) expectedHandle.invokeExact();

            System.out.println("return = " + result);
            System.out.println("errno matches EINVAL = "
                    + (errnoValue == expected));
            System.out.println("errno is nonzero = "
                    + (errnoValue != 0));

            if (result != -1 || errnoValue != expected) {
                throw new AssertionError(
                        "native error/capture mismatch");
            }
        }
    }
}
~~~

**Một điểm rất đáng học:** Chương trình **đọc errno từ capture segment trước** khi gọi **native_einval()**. Nhưng ngay cả khi gọi helper sau đó, giá trị trong segment vẫn là snapshot đã được ghi từ lần gọi **fail_with_einval()**. Không cần sử dụng cùng biến errno của thread sau khi những native calls khác đã chạy.

**SymbolLookup.libraryLookup(path, arena)** giữ thư viện sống trong lifetime của arena. Không giữ symbol hoặc MethodHandle để gọi sau khi đã đóng arena; downcall target address có thể không còn hợp lệ nếu native library bị unload.

### 5.3. Biên dịch và chạy trên Linux

Cần **JDK 22+** và compiler C tương thích hệ điều hành/kiến trúc JVM:

~~~bash
mkdir -p build

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  probe_errno.c -o build/liberrno_probe.so

javac -d build CaptureErrnoDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build CaptureErrnoDemo
~~~

Lệnh **--enable-native-access=ALL-UNNAMED** cấp quyền sử dụng restricted FFM functions cho code classpath không thuộc named module. Trên JDK22, không cần **--enable-preview** cho các FFM APIs đã được chuẩn hóa. Nếu bạn chuyển class vào named module thì phải cấp native access đúng tên module tương ứng.

### 5.4. Stdout có thể kiểm chứng

Nếu thư viện được nạp và ví dụ chạy đúng:

~~~text
return = -1
errno matches EINVAL = true
errno is nonzero = true
~~~

**Không in một giá trị errno cố định** vì tiêu chuẩn không yêu cầu EINVAL bằng cùng số trên mọi OS. Chính C helper cung cấp giá trị tham chiếu. Mỗi lần downcall là một native operation thật, không phải việc Java tự mô phỏng errno.

Nếu lệnh **java** báo không tìm thấy thư viện, kiểm tra path tuyệt đối từ working directory hiện tại và file **liberrno_probe.so** đã được build. Nếu thiếu tên symbol, kiểm tra file .so thực sự export **fail_with_einval** và **native_einval**, kiến trúc tương thích và ABI. Nếu chạy Windows/macOS, dùng tên shared library và toolchain tương ứng; lệnh GCC và tên .so trên dành riêng cho Linux.

## 6. Minh họa với API C chuẩn như fopen: lỗi chỉ có nghĩa khi kết quả thất bại

Trên Linux/POSIX, **fopen** có chữ ký:

~~~c
FILE *fopen(const char *filename, const char *mode);
~~~

Với chế độ **"r"**, nếu file không tồn tại hoặc không đọc được, **fopen** trả **NULL** và đặt errno để chỉ nguyên nhân. Nhưng nếu **fopen** thành công, **errno** *không có nghĩa là bắt buộc bằng 0*. Nó có thể còn giá trị từ thao tác trước, vì nhiều hàm C không reset errno khi thành công.

Quy trình Java đúng:

~~~text
fopen(path, "r") qua captureCallState("errno")
          |
          v
    Kết quả là NULL?
        /       \
      Có        Không
      |           |
  đọc errno     giữ FILE*
  từ snapshot   gọi fclose sau khi dùng
      |
  xử lý lỗi
~~~

Nếu dùng C library chuẩn thông qua **Linker.nativeLinker().defaultLookup()**, bạn có thể liên kết **fopen** bằng:

~~~java
// Fragment dành cho môi trường có symbol fopen trong defaultLookup.
Linker linker = Linker.nativeLinker();
MemorySegment fopenSymbol =
        linker.defaultLookup().find("fopen").orElseThrow();

MethodHandle fopen = linker.downcallHandle(
        fopenSymbol,
        FunctionDescriptor.of(
                ValueLayout.ADDRESS,
                ValueLayout.ADDRESS,
                ValueLayout.ADDRESS),
        Linker.Option.captureCallState("errno"));
~~~

Native descriptor chứa return **FILE*** (address) và hai tham số C là **char***. MethodHandle **bound** tạo ra có dạng:

~~~text
(MemorySegment capturedState,
 MemorySegment filename,
 MemorySegment mode) -> MemorySegment
~~~

Ví dụ fragment gọi (bên trong một **Arena** còn sống, có **fopen** đã link):

~~~java
MemorySegment captured = arena.allocate(
        Linker.Option.captureStateLayout());
MemorySegment filename = arena.allocateFrom(
        "file-that-should-not-exist.txt");
MemorySegment mode = arena.allocateFrom("r");

MemorySegment file = (MemorySegment) fopen.invokeExact(
        captured, filename, mode);

if (file.equals(MemorySegment.NULL)) {
    int code = (int) errnoField.get(captured, 0L);
    System.out.println("native fopen error code = " + code);
}
~~~

Đây là **fragment**, không phải chương trình độc lập: cần imports, **arena** và **errnoField**, exception declaration, cùng cleanup **fclose** nếu file mở thành công. Tên file chỉ minh họa tình huống; đừng giả định nó không tồn tại trong mọi working directory. Không in stdout cố định cho errno vì lỗi có thể là **ENOENT, EACCES**, hoặc lỗi khác theo OS/filesystem.

**FILE* không phải một Java object và không được free trực tiếp bằng Arena.** Nếu **fopen** trả pointer hợp lệ, phải gọi **fclose** theo C library contract. Chụp errno không thay thế resource cleanup.

### strerrror/strerror và thông điệp lỗi

Một native **strerror(errno)** có thể trả thông điệp của mã C errno, nhưng:

- Tên thông điệp phụ thuộc OS, locale và C library;
- **strerror** có thể dùng buffer tĩnh hoặc có ràng buộc thread safety tùy runtime;
- Nếu gọi C function khác để định dạng thông điệp lỗi, **hãy chụp và đọc errno trước**;
- C pointer trả về có lifetime/bounds cần được hiểu trước khi đọc bằng Java FFM.

Chỉ log message trong môi trường đã xác minh API, không dựa vào string tiếng Anh cố định để kiểm thử.

## 7. Windows: GetLastError và WSAGetLastError khác errno

Trong Windows có nhiều error namespaces. **captureCallState** cho phép chọn đúng trạng thái nền tảng nếu JDK platform hỗ trợ.

| API native | Tín hiệu thất bại điển hình | Trạng thái thích hợp |
| --- | --- | --- |
| Hàm C runtime (ví dụ một số file/string API) | Tùy contract C runtime | **errno** |
| Win32 API như **CreateFileW** | **INVALID_HANDLE_VALUE** | **GetLastError** |
| Win32 BOOL-returning API | **FALSE** | **GetLastError** theo contract hàm |
| Winsock **socket/recv/send** | **INVALID_SOCKET / SOCKET_ERROR** tùy hàm | **WSAGetLastError** |
| API tự trả lỗi trong return value | Mã trả về có thể đã là lỗi | Có thể **không cần** captureCallState |

Không dùng **GetLastError** để diễn giải một C runtime function chỉ quy định errno. Không dùng **WSAGetLastError** cho Win32 file API. Đừng cho rằng một mã số trùng nhau trong các hệ error domain cũng có cùng ý nghĩa.

### Kiểm tra hỗ trợ trước khi chọn option

~~~java
StructLayout stateLayout =
        Linker.Option.captureStateLayout();

boolean win32Supported = stateLayout.memberLayouts().stream()
        .flatMap(member -> member.name().stream())
        .anyMatch("GetLastError"::equals);

if (win32Supported) {
    Linker.Option win32Option =
            Linker.Option.captureCallState("GetLastError");
    VarHandle win32Field = stateLayout.varHandle(
            MemoryLayout.PathElement.groupElement("GetLastError"));
    // Liên kết downcall Win32 phù hợp với win32Option.
}
~~~

Đây là **fragment**, không tự gọi Windows function. Nó kiểm tra chính xác **GetLastError** có trong capture-state layout hiện tại. **WSAGetLastError** kiểm tra tương tự với tên riêng, không suy ra hỗ trợ khi chỉ thấy GetLastError.

### Trình tự gọi một Win32 function

~~~text
1. Link native Win32 function với FunctionDescriptor đúng Win32 ABI.
2. Gắn captureCallState("GetLastError") khi nền tảng hỗ trợ.
3. Cấp capture segment bằng captureStateLayout().
4. Invoke downcall, truyền capture segment ở vị trí đúng.
5. Kiểm tra return sentinel của chính Win32 function.
6. Chỉ khi contract xác nhận thất bại thì đọc GetLastError
   từ capture-state segment.
7. Dịch mã lỗi/ghi log bằng phương tiện phù hợp, ví dụ FormatMessageW.
~~~

Một số Windows API cho phép **GetLastError** chứa thông tin ngay cả khi thành công hoặc yêu cầu logic kiểm tra đặc biệt; phải đọc tài liệu từng hàm. **Không đọc GetLastError của một native call trước** sau khi đã chạy nhiều Win32 calls khác rồi kỳ vọng trạng thái vẫn đúng.

**Mã Windows error là giá trị hệ thống, có thể dùng cách diễn giải unsigned** khi cần hiển thị DWORD. Nếu carrier là Java int, **Integer.toUnsignedLong(code)** giúp in miền unsigned 32-bit; việc này không thay đổi lỗi gốc. Với Winsock, chọn tên **WSAGetLastError** thay vì tên Win32, rồi tra bảng mã **WSA...** tương ứng.

### Ví dụ ý tưởng native Windows (không phải chương trình Java hoàn chỉnh)

~~~c
/* Fragment Windows C minh họa trạng thái Win32. */
#include <windows.h>

int fail_win32_demo(void) {
    SetLastError(ERROR_INVALID_PARAMETER);
    return 0;
}
~~~

Nếu dùng linker option **captureCallState("GetLastError")** với hàm đó, snapshot tương ứng được dự kiến chứa mã **ERROR_INVALID_PARAMETER** của Win32. Tuy nhiên, việc export hàm từ DLL, compile, link, ABI và dùng Windows-specific tooling cần thực hiện riêng; không coi fragment này là đoạn code chạy trên Linux.

**Không tự ánh xạ ERROR_INVALID_PARAMETER thành EINVAL**. Đó là hai domain có thể có ý nghĩa gần nhau nhưng cơ chế/cách mã hóa khác nhau.

## 8. Vì sao không thể chỉ gọi errno() từ Java sau đó?

**errno** trong C thường là một macro mở rộng thành truy cập thread-local state qua function/variable đặc thù C runtime. Tên implementation cụ thể thay đổi theo platform, ví dụ cơ chế thread-local storage; không nên hard-code địa chỉ hoặc tự đoán symbol.

Nếu Java gọi native function A, rồi link một hàm B để hỏi errno:

~~~text
Java
  |
  +-- downcall A (sets errno)
  |
  +-- Java/JVM làm công việc khác
  |
  +-- downcall B ("get errno")
~~~

B có thể đọc **một trạng thái đã thay đổi**, hoặc một C runtime/thread-local variable khác nếu bạn link qua runtime khác. Bản chất vấn đề là **thời điểm** và **runtime/thread context**, không phải chỉ là lookup đúng symbol. **captureCallState** đưa việc đọc trạng thái vào quy trình A được linker điều phối, tránh một lần downcall B chỉ để chụp lỗi.

**Giới hạn:** captureCallState chụp những trạng thái mà linker hỗ trợ. Nó không tự biết error structure do thư viện C tự định nghĩa, không capture mọi TLS variable bất kỳ, không đọc errno của một thread OS khác và không giữ lịch sử lỗi của nhiều lời gọi. Với error protocol riêng, phải định nghĩa FunctionDescriptor/return struct hoặc helper tương ứng.

## 9. Không đọc errno khi thành công nếu API không cam kết reset

Một quy tắc C quan trọng: **không phải mọi native success đều đặt errno về 0**.

Ví dụ logic lỗi:

~~~c
int operation(void) {
    if (/* thành công */ 1) {
        return 42;
    }
    errno = EIO;
    return -1;
}
~~~

Đây là **pseudocode C** để giải thích contract; không dùng trực tiếp như hàm sản phẩm. Nếu lần trước native code đặt errno=EINVAL và lần sau operation trả 42 nhưng không đụng errno, capture của lần sau vẫn có thể chứa một mã errno khác 0. Điều này **không biến return 42 thành lỗi**.

Khi Java xử lý:

~~~java
int result = (int) call.invokeExact(captured);

if (result == -1) {
    int errno = (int) errnoHandle.get(captured, 0L);
    throw new IllegalStateException(
            "native function failed, errno=" + errno);
}

System.out.println("success = " + result);
~~~

Đây là **fragment** giả định native function có sentinel **-1**, **call** đã link với captureCallState, **captured** và **errnoHandle** hợp lệ, code cho phép throws Throwable. Không áp dụng **result == -1** cho mọi C/Windows API. **Return code quyết định khi nào errno có ý nghĩa**, trừ khi tài liệu hàm chỉ định một quy tắc khác.

Với các hàm như **strtol**, có trường hợp return **LONG_MAX/LONG_MIN/0** cần phân biệt giá trị hợp lệ và overflow; tài liệu C quy định cách reset errno trước gọi và kiểm tra sau gọi. Chỉ capture sau lời gọi là chưa đủ nếu bỏ mất bước reset theo contract.

## 10. Một lần gọi — một capture snapshot: không dùng chung bừa bãi

Đối với nhiều lời gọi nối tiếp, bạn có thể dùng một capture-state segment **nếu đọc/copy dữ liệu cần thiết trước lần invoke tiếp theo**. Nhưng mỗi downcall với captureCallState có thể ghi đè field trong segment đó.

~~~text
call A -> captured errno A
             |
             +-- Java đọc / lưu errno A vào int local
             |
call B -> captured errno B (ghi đè cùng vùng)
             |
             +-- Java đọc errno B
~~~

Đoạn Java minh họa:

~~~java
int resultA = (int) first.invokeExact(state);
int errorA = (int) errnoHandle.get(state, 0L);

int resultB = (int) second.invokeExact(state);
int errorB = (int) errnoHandle.get(state, 0L);

// errorA đã lưu riêng, không thay đổi khi state bị ghi đè.
~~~

Đây là **fragment**; cả hai handle được gắn captureCallState và có FunctionDescriptor trả int, không nhận native parameters. Nếu muốn lưu lâu một snapshot hoặc đối chiếu nhiều lỗi, allocate **hai state segments**, hoặc copy các field cần thiết sang Java value/record.

### Đa luồng

- **MethodHandle** được link một lần có thể được dùng từ nhiều Java threads nếu các tham số native/đối tượng sử dụng đều đáp ứng contract.
- **errno** là thread-local: kết quả capture gắn với **thread thực thi native downcall**, không phải một errno global của process.
- Mỗi thread/lần invoke nên dùng **capture-state segment riêng**, hoặc thiết kế synchronization nếu cần tái sử dụng.
- Với **Arena.ofConfined()**, segment chỉ có thể được thread sở hữu arena truy cập; dùng ở thread khác có thể gây **WrongThreadException**.
- Dùng **Arena.ofShared()** không tự làm việc nhiều threads ghi cùng segment thành an toàn. Không để hai calls cùng write vào một capture segment mà không đồng bộ.

Capture state segment còn sống bao lâu tùy arena; nếu close rồi đọc, bạn vi phạm lifetime của MemorySegment. Đặc biệt **không giữ reference đến segment của arena đã close** rồi đưa cho logging thread để đọc sau.

## 11. Liên quan đến Linker.Option.critical(boolean)

FFM có linker option **critical(boolean allowHeapAccess)** dành cho native function cực ngắn và đáp ứng các hạn chế nghiêm ngặt về tương tác với JVM. Nó cho phép một số tối ưu hóa cho critical downcall.

**Trong JDK 22, captureCallState không được kết hợp với critical(boolean).** Nếu một native call cần bắt errno/GetLastError, hãy dùng downcall thông thường cùng capture option, không ép critical chỉ để tối ưu tốc độ. Đây là quy tắc rõ ràng trong JDK 22 API.

Sai:

~~~java
// Fragment cố ý sai: tổ hợp option không hợp lệ trên JDK 22.
linker.downcallHandle(
        symbol,
        FunctionDescriptor.of(ValueLayout.JAVA_INT),
        Linker.Option.captureCallState("errno"),
        Linker.Option.critical(false));
~~~

**Không dùng critical để gọi một hàm có thể blocking, gọi lại Java, hoặc có hành vi không đáp ứng critical contract**. Việc kết hợp option sai có thể bị từ chối ngay khi linker tạo MethodHandle. Tách phần chẩn đoán lỗi ra khỏi khái niệm critical performance.

## 12. Chữ ký native và ABI luôn quan trọng hơn code Java trông hợp lý

**captureCallState chỉ chụp trạng thái, không kiểm tra FunctionDescriptor có khớp hàm C thật hay không.** Nếu liên kết:

~~~c
int foo(const char *name, size_t length);
~~~

bằng descriptor chỉ có một int parameter, bạn đang gọi sai ABI. Ở mức native, mismatch có thể làm crash JVM hoặc memory corruption, không chỉ ném Java exception.

Với FFM:

- **int** C thường ánh xạ Java **ValueLayout.JAVA_INT** trên ABI phổ biến.
- **char*** thường là **ValueLayout.ADDRESS** và truyền MemorySegment chứa C string đúng encoding/NUL.
- **size_t** có kích thước theo ABI; dùng **Linker.nativeLinker().canonicalLayouts().get("size_t")** để xác nhận mapping thay vì mặc định long.
- **C long** 8 byte trên Linux/x64 LP64 nhưng có thể 4 byte trên Windows/x64 LLP64.
- Pointer trả về có thể là segment kích thước 0; không tự dereference vượt bounds hoặc sau lifetime của native object.

Chụp error state không làm FunctionDescriptor, Arena và SymbolLookup thành tự động an toàn. Native library còn phải sống, memory arguments còn hợp lệ, thread có quyền truy cập và native code phải tuân thủ API contract.

## 13. Vận hành thực tế: chuyển native error thành Java exception

Một ứng dụng Java nên chuẩn hóa thông tin lỗi thành object có ít nhất ba thành phần:

1. **Operation**: hàm hoặc thao tác native vừa thất bại.
2. **Error domain**: **errno**, **GetLastError**, **WSAGetLastError**, hoặc mã riêng của thư viện.
3. **Error code + optional text**: giá trị nguyên gốc và diễn giải dựa trên OS/runtime tương ứng.

Ví dụ mã Java không phụ thuộc FFM để định hình một kết quả:

~~~java
record NativeFailure(String operation, String domain, int code) {
    String summary() {
        return operation + " failed: "
                + domain + "=" + Integer.toUnsignedString(code);
    }
}
~~~

**Fragment này không phải chương trình chạy độc lập**. Với POSIX errno thường là int không âm nên có thể in bằng **Integer.toString(code)**; **Integer.toUnsignedString** minh họa việc cần cân nhắc Win32 DWORD khi diễn giải unsigned. Muốn hiển thị thông điệp, hãy dùng cơ chế dịch phù hợp hệ điều hành; đừng hard-code English messages vào business logic.

Một wrapper JDK22 nên trông như:

~~~text
request
   |
   v
allocate per-call capturedState
   |
   v
invoke bound MethodHandle
   |
   v
check return according to native API
   |
   +-- success -> use native result, release resources
   |
   +-- failure -> read named field from capturedState
                    |
                    v
              NativeFailure(domain, code)
                    |
                    v
              map to Java exception / retry / status
~~~

**Đừng tự động retry mọi errno**. Ví dụ **EINTR**, **EAGAIN**, **EACCES**, **EINVAL**, **ENOMEM** có ý nghĩa, khả năng retry và side effects khác nhau theo API. Một lời gọi có thể đã làm thay đổi một phần state trước khi trả lỗi; quyết định retry cần tôn trọng idempotency và contract.

### Ghi log an toàn

Hạn chế ghi raw path, credential, pointer address hay user-provided native strings vào log. Luôn ghi **error domain** cùng code số vì cùng mã có thể có tên khác nhau giữa POSIX và Windows. Trong chẩn đoán cần thiết có thể log phiên bản JDK, OS/architecture, native library version và tên native function.

## 14. Bảng lỗi phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Trả native error code mà tưởng JVM sẽ tự throw | Java chạy tiếp với kết quả sai | Kiểm tra return sentinel, rồi đọc capture |
| Đọc errno sau các native calls khác | Mất/tráo state của lời gọi cần kiểm tra | Gắn captureCallState vào downcall cần theo dõi |
| Coi errno là biến global process | Nhầm mã giữa threads | Nhớ errno là thread-local |
| Coi errno khác 0 luôn là failure | Phân loại sai một native success | Kiểm tra return contract trước |
| Dùng "GetLastError" trên Linux | IllegalArgumentException hoặc unsupported option | Liệt kê tên từ captureStateLayout() |
| Dùng errno cho Winsock failure | Sai error domain | Dùng WSAGetLastError nếu được hỗ trợ |
| Tự hard-code offset 0 cho errno | Đọc nhầm field trên layout khác | VarHandle groupElement("errno") |
| Tự allocate 4 byte cho snapshot | Không đáp ứng full layout size/alignment | arena.allocate(captureStateLayout()) |
| Quên truyền capture segment khi invoke | WrongMethodTypeException | Theo MethodHandle.type() |
| Đưa capturedState vào FunctionDescriptor như tham số C | Sai ABI, có thể crash | Capture là tham số do linker thêm |
| Chỉ đọc capture sau khi arena đã đóng | Sai lifetime | Đọc trước khi close |
| Dùng cùng segment cho concurrent calls | Race và snapshot bị ghi đè | State riêng cho mỗi call/thread |
| Kết hợp captureCallState với critical trên JDK22 | Linker option combination không hợp lệ | Dùng downcall thường |
| Hard-code EINVAL=22 làm test portable | Test sai trên ABI khác | So với mã native trả từ chính toolchain |
| Đọc các field chưa chọn capture | Nhầm bytes là giá trị được chụp | Chỉ tin fields nêu trong option |
| Cho rằng capture thay thế fclose/free/CloseHandle | Rò native resource | Quản lý cleanup theo hợp đồng native |
| Ném Java exception khi C trả success nhưng errno cũ | False positive | Dựa vào return sentinel và API contract |
| Gọi sai FunctionDescriptor | Lỗi ABI/memory safety | Đối chiếu đúng chữ ký C và calling convention |

## 15. Checklist triển khai cho mỗi native downcall

Trước khi giao một helper FFM captureCallState vào production, hãy kiểm tra:

1. **Native function** thuộc API nào? Nó báo thất bại qua NULL, -1, FALSE, INVALID_HANDLE_VALUE hay return error code trực tiếp?
2. **State thích hợp** là errno, GetLastError, WSAGetLastError hay error object riêng? Một số APIs không cần capture.
3. **Tên field** có tồn tại trong **captureStateLayout()** trên JDK/runtime đang chạy không?
4. **FunctionDescriptor** khớp C signature, scalar widths, calling convention và pointers chưa?
5. **MethodHandle** có đúng tham số capture-state bổ sung không? Bound/unbound có khác nhau?
6. **Capture-state segment** được cấp với **arena.allocate(captureStateLayout())** và còn sống khi đọc?
7. **Exception handling** có kiểm tra return sentinel trước khi diễn giải errno không?
8. **Native API có yêu cầu xóa errno trước** hoặc một bước thiết lập khác không? Nếu có, thực hiện tại native thread đúng cách.
9. **Concurrency** có state segment riêng cho mỗi call không? Có tránh dùng confined segment sai thread không?
10. **Cleanup** có đóng FILE*, socket, HANDLE, Arena hoặc native resource khi mọi nhánh success/failure không?
11. **Testing** có kiểm tra lỗi thực tế, cả trường hợp success với errno cũ, và ít nhất hai nền tảng nếu ứng dụng portable không?
12. **Logging** có ghi error domain và numerical code, không giả định message cố định không?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một C function trả -1 và đặt errno, nhưng Java gọi một hàm native khác trước khi đọc errno. Lỗi tiềm ẩn là gì?

**Đáp án:** Thread-local errno có thể đã bị thay đổi. Gắn **captureCallState("errno")** vào chính downcall của function cần kiểm tra để lưu snapshot ngay khi lời gọi kết thúc.

**Câu 2.** Đã dùng **captureCallState("errno")**, vậy FunctionDescriptor của **int fail(void)** có thêm tham số C kiểu ADDRESS không?

**Đáp án:** Không. FunctionDescriptor vẫn là **FunctionDescriptor.of(ValueLayout.JAVA_INT)**. Linker thêm một tham số **MemorySegment** vào **MethodHandle Java**, nhưng native C signature không đổi.

**Câu 3.** Dùng bound handle cho **int fail(void)** có capture option, lời gọi **invokeExact** cần truyền gì?

**Đáp án:** Một **capture-state MemorySegment**, sau đó không có native argument nào. Ví dụ **(int) handle.invokeExact(captured)**.

**Câu 4.** Có nên allocate capture buffer 4 byte chỉ vì errno thường là C int 4 byte?

**Đáp án:** Không. Capture-state layout là platform-dependent struct, có thể chứa thêm các fields/padding và alignment. Dùng **arena.allocate(Linker.Option.captureStateLayout())**.

**Câu 5.** Tại sao một function trả thành công nhưng errno captured khác 0 vẫn có thể hợp lệ?

**Đáp án:** Nhiều C functions không reset errno khi thành công; nó có thể còn lỗi từ thao tác trước. Phải đọc tài liệu và kiểm tra return sentinel trước.

**Câu 6.** Có thể dùng **captureCallState("GetLastError")** nguyên xi trên Linux không?

**Đáp án:** Không. Trạng thái này là Windows-specific và có thể không được hỗ trợ. Liệt kê names trong captureStateLayout() trước.

**Câu 7.** Win32 function lỗi do file system, nên dùng **WSAGetLastError** hay **GetLastError**?

**Đáp án:** Nếu native function là Win32 file API và tài liệu dùng GetLastError, chọn **GetLastError**. **WSAGetLastError** dành cho Winsock.

**Câu 8.** Gọi xong downcall A chụp errno vào segment S, sau đó downcall B cũng chụp vào S. Đọc S lúc cuối sẽ có errno của A hay B?

**Đáp án:** Thông thường là trạng thái từ lời gọi B ghi sau cùng vào cùng field. Phải lưu errno A sang Java local trước khi B chạy, hoặc allocate snapshot khác.

**Câu 9.** Có thể kết hợp **captureCallState** với **Linker.Option.critical(false)** trên JDK22 không?

**Đáp án:** Không. JDK22 document ghi rõ option này không được kết hợp với critical(boolean).

**Câu 10.** Vì sao chương trình mẫu gọi **native_einval()** thay vì so captured errno với số 22?

**Đáp án:** EINVAL là macro C có giá trị do C runtime/ABI định nghĩa. Lấy mã tham chiếu từ cùng toolchain làm test portable hơn so với hard-code một giá trị số.

### Bài tập nâng cao

**Bài tập A:** Trong demo, thay **errno=EINVAL** thành **errno=EACCES**, đồng thời đổi hàm trả mã tham chiếu. Dự đoán stdout vẫn có hai kiểm tra **true**, vì mã so sánh lấy từ C runtime.

**Bài tập B:** Liên kết thêm một hàm C **int succeed_without_clearing(void) { return 42; }**, gắn captureCallState, gọi sau fail. Giải thích vì sao **không được ném exception chỉ dựa trên errno khác 0** nếu success contract là return 42.

**Bài tập C:** Tạo **hai capture-state segments** để lưu riêng lỗi hai calls. Đọc cả hai sau khi gọi; so sánh với dùng chung một segment bị overwrite.

**Bài tập D:** Viết chương trình **CaptureNames** cho hai máy Windows/Linux. In và đối chiếu các names, size/alignment của captureStateLayout; giải thích lý do code không nên hard-code layout offset.

**Bài tập E:** Với một Win32 API có documented GetLastError, thiết kế wrapper lưu đồng thời operation name, return sentinel và error code. Mô tả vị trí xử lý resource cleanup và việc chuyển DWORD thành unsigned long khi ghi log.

## Tài liệu tham khảo chính thức

- Java SE 22 API — **Linker.Option.captureCallState / captureStateLayout**, thứ tự tham số capture và hạn chế critical: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html
- Java SE 22 API — **Linker.downcallHandle**, FunctionDescriptor và native ABI: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Java SE 22 API — **MemoryLayout.varHandle** và groupElement path: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html
- Java SE 22 API — **SymbolLookup.libraryLookup** và lifetime: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- Oracle Java 22 Core Libraries — **Checking for Native Errors Using errno**: https://docs.oracle.com/en/java/javase/22/core/checking-native-errors-using-errno.html
- OpenJDK — **JEP 454: Foreign Function & Memory API**: https://openjdk.org/jeps/454
- Microsoft Win32 — **GetLastError**: https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror
- Microsoft Winsock — **WSAGetLastError**: https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-wsagetlasterror

**Ghi nhớ:** **captureCallState** là một **Linker.Option gắn vào downcall** để lưu các trạng thái lỗi nền tảng **ngay sau lời gọi native** vào một MemorySegment có layout do JDK cung cấp. Nó **không thay thế kiểm tra return value**, không biến errno thành lỗi Java tự động, không thêm tham số vào chữ ký C, không xóa errno bằng cách sửa capture buffer, và không bảo đảm các error domains của POSIX/Win32/Winsock tương đương nhau.