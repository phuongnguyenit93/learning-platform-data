# Mô hình MemorySegment, Arena, MemoryLayout, SymbolLookup và Linker

## 1. Mục tiêu: ghép đúng mô hình Foreign Function & Memory (FFM)

Khi Java cần đọc/ghi native memory hoặc gọi hàm trong thư viện C, **Foreign Function & Memory API (FFM)** cung cấp các thành phần để biểu diễn vùng nhớ, vòng đời, cấu trúc dữ liệu, tên symbol và quy tắc gọi theo native ABI. Bài này dùng **API chính thức từ JDK 22 trở lên** thuộc package `java.lang.foreign`. JDK 17 có FFM *incubator* khác package và API; JDK 19–21 có các phiên bản preview khác nhau. Do đó code mẫu JDK 22+ không phải ví dụ chạy trực tiếp trên Java 17.

Năm thành phần cần phân biệt:

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
|---|---|---|
| **`MemorySegment`** | Vùng byte nào đang được truy cập, dài bao nhiêu, còn hợp lệ không? | `segment.get(JAVA_INT, 0)` |
| **`Arena`** | Ai cấp phát native bytes, lifetime đến khi nào và thread nào được dùng? | `try (Arena a = Arena.ofConfined())` |
| **`MemoryLayout`** | Những bytes ấy có kiểu, field offset, alignment, array stride ra sao? | `MemoryLayout.structLayout(...)` |
| **`SymbolLookup`** | Hàm/biến native mang tên X nằm ở địa chỉ nào? | `lookup.find("strlen")` |
| **`Linker`** | Biến địa chỉ + mô tả signature C thành callable Java theo ABI nào? | `linker.downcallHandle(address, descriptor)` |

Hai khái niệm bổ sung quan trọng: **`FunctionDescriptor`** mô tả signature C cho `Linker`; **`MethodHandle`** là đối tượng Java dùng để thực hiện downcall. Không đưa `MemoryLayout` vào nhầm vị trí của `MemorySegment` và không coi `SymbolLookup` là cơ chế tự suy ra signature.

Sau bài này bạn sẽ có thể: cấp native memory và dùng đúng lifecycle; mô hình hóa C array/struct với padding; tra cứu một native symbol; liên kết hàm C `strlen` thành `MethodHandle`; chạy một Java 22+ program không viết JNI adapter; nhận diện lỗi ABI, use-after-close, sai thread và sự khác biệt version.

### Bức tranh tương tác

~~~text
Java code
  |
  +---- Arena ----------------------> MemorySegment
  |      owner + scope               bytes, address, bounds
  |                                      ^
  +---- MemoryLayout -------------------+|
  |      type/size/alignment/offset      | Java get/set hoặc VarHandle
  |                                      |
  +---- SymbolLookup ----> symbol address (MemorySegment 0 byte)
  |                              |
  +---- FunctionDescriptor ------+----> Linker.nativeLinker()
             signature C                      |
                                              v
                                           MethodHandle
                                              |
                                              v
                                     C function (downcall)
~~~

**Dòng đời của hàm native** và **dòng đời của bộ nhớ native** là hai vấn đề riêng. Một `MethodHandle` đến library đã bị unload có thể nguy hiểm dù Java object đó vẫn còn. Một `MemorySegment` do arena đã đóng cũng không thể dùng chỉ vì biến Java còn giữ reference.

## 2. Hai nửa FFM và ranh giới với JNI

**Foreign memory access**: Java mô tả, cấp phát và truy cập memory theo `MemorySegment`/`Arena`/`MemoryLayout`. Ví dụ mảng ba `int` liên tục trong native memory, được Java ghi/read bằng layout.

**Foreign function access**: `SymbolLookup` tìm địa chỉ một C symbol; `FunctionDescriptor` định nghĩa các tham số và return theo C ABI; `Linker` tạo `MethodHandle` để Java gọi hàm native.

Ví dụ native C:

~~~c
/* Native signature dùng để giải thích FFM, không phải JNI method. */
size_t strlen(const char *text);
~~~

Để gọi đúng, Java phải có C string kết thúc NUL, pointer còn sống trong lúc gọi, symbol `strlen`, return layout phù hợp `size_t` và argument layout phù hợp `const char*`. Linker biết ABI của platform nhưng **không kiểm tra được type của symbol C chỉ từ tên**.

Không nhầm FFM với JNI: JNI native method thường nhận `JNIEnv *` và `jobject/jclass`, có generated C header và phải quản lý JNI local/global references; FFM downcall gọi **C ABI symbol bình thường** không cần tạo JNI glue code. Nhưng FFM không thể thay thế toàn bộ JNI APIs để thao tác lớp, trường và exceptions của JVM.

## 3. MemorySegment: vùng nhớ, bounds và lifetime

Một `MemorySegment` mô tả một dải byte liên tục. View có thể trỏ tới native off-heap memory do `Arena` cấp hoặc một vùng Java heap được phép biểu diễn bằng `MemorySegment.ofArray(...)`. Java view biết kích thước và scope; **không phải một “con trỏ C trần” được dùng tùy ý**.

Ví dụ fragment (cần đặt trong một Java method):

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slot = arena.allocate(ValueLayout.JAVA_INT);
    slot.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = slot.get(ValueLayout.JAVA_INT, 0);
    System.out.println(answer); // 42
}
~~~

Mỗi `get/set` cần đúng type/layout và offset theo **bytes**, không phải index field tùy ý. Ba mức an toàn:

1. **Spatial safety**: Java FFM kiểm tra `offset` và số bytes của type không vượt `segment.byteSize()`. Ví dụ buffer 4 byte mà đọc `JAVA_INT` ở offset 4 là lỗi bounds, không âm thầm đọc sang địa chỉ kế.
2. **Temporal safety**: sau `arena.close()`, segment liên kết với arena mất hiệu lực. Truy cập Java sau đó bị chặn (thông thường `IllegalStateException`).
3. **Thread-confinement safety**: segment của `Arena.ofConfined()` chỉ được dùng bởi owner thread. Truy cập/đóng ở thread khác có thể ném `WrongThreadException`.

Lưu ý: các kiểm tra bảo vệ **truy cập Java FFM**; khi Java đã trao địa chỉ cho native C, C có thể đọc/ghi vượt buffer hoặc use-after-free nếu thư viện vi phạm hợp đồng. Không có `try/catch` Java nào bảo đảm cứu JVM khỏi mọi native memory corruption.

### Slice không copy

`segment.asSlice(offset, size)` tạo một view con, cùng backing memory và cùng lifetime; không cấp phát bản copy. Giữ slice Java sau khi arena đóng **không** giữ vùng nhớ native sống lại. `ValueLayout.ADDRESS` mô tả giá trị pointer, nhưng một giá trị pointer hợp lệ về bit chưa chắc trỏ đến memory đang sống.

### Java heap và native off-heap khác nhau

`MemorySegment.ofArray(byte[])` mô tả một vùng thuộc Java heap; `arena.allocate(...)` thông thường cấp native off-heap memory. Đừng suy rằng mọi Java heap segment đều có thể đưa làm một stable native pointer theo mọi ABI. Chọn đúng cơ chế khi cần native function trực tiếp giữ pointer, đặc biệt với lời gọi bất đồng bộ.

## 4. Arena: sở hữu native memory và thời điểm thu hồi

`Arena` vừa là `SegmentAllocator` vừa mang một **scope** để xác định lifetime. Với arena đóng được, `try-with-resources` là cách đáng tin:

~~~java
MemorySegment data;
try (Arena arena = Arena.ofConfined()) {
    data = arena.allocate(64, 8);
    // Sử dụng data ở owner thread; alignment tối thiểu 8.
}
// Arena đóng; data không được truy cập nữa.
~~~

| Arena | Truy cập từ thread | Đóng tường minh? | Khi nên dùng |
|---|---|---|---|
| `Arena.ofConfined()` | Thread tạo arena | Có, từ owner thread | Buffer ngắn hạn, đồng bộ |
| `Arena.ofShared()` | Nhiều thread | Có, cần phối hợp với những hoạt động đang dùng | Buffer chung có lifetime quản lý rõ |
| `Arena.ofAuto()` | Nhiều thread | Không | Dữ liệu có thể để GC quyết định thời điểm cleanup; không có deadline chính xác |
| `Arena.global()` | Nhiều thread | Không | Dữ liệu sống không giới hạn trong vòng đời liên quan; tránh dùng cho allocation lặp vô hạn |

**Chọn `ofConfined()` làm mặc định khi không cần chia sẻ**. `ofShared()` cho phép truy cập cross-thread **không đồng nghĩa data được tự động khóa**. Hai worker cùng ghi một field vẫn phải có synchronization/atomic protocol. Đóng shared arena khi native code còn giữ pointer cũng là một vấn đề ownership, không thể giải quyết chỉ bằng đổi `ofConfined` thành `ofShared`.

`Arena.ofAuto()` không thích hợp nếu contract yêu cầu hủy buffer **ngay** khi `closeSession()` trả về: thời điểm GC khó dự đoán. `Arena.global()` không tự đóng, nên lặp lại allocation có thể giữ native memory rất lâu. Với một API có trạng thái session, tốt hơn nên có owner tường minh, trạng thái OPEN/CLOSING/CLOSED và đường cleanup.

### Library arena và buffer arena

`SymbolLookup.libraryLookup(library, arena)` dùng một arena cho **lifetime của thư viện đã nạp**. Một buffer tạo trong arena khác chỉ cần sống tới khi native function dùng xong. Do vậy đôi khi có hai arena:

~~~text
libraryArena -> load library -> SymbolLookup -> MethodHandle
     |                       không close trước downcall cuối
     v
native binding lifetime

callArena -> input/output MemorySegments
     |
     +-- close sau khi native code ngừng sử dụng buffer
~~~

Nếu library function lưu input pointer để xử lý sau khi lời gọi return, **không** đóng callArena sớm. Nếu library arena đóng trong khi còn MethodHandle được gọi, function code có thể đã unload; JVM có thể crash dù `MethodHandle` vẫn là Java object hợp lệ.

## 5. MemoryLayout: từ vùng bytes tới dữ liệu có cấu trúc

`MemoryLayout` không cấp phát memory mà mô tả cách hiểu và truy cập bytes.

| Layout | Tương đương khái niệm | Ví dụ |
|---|---|---|
| `ValueLayout.JAVA_INT` | Primitive 32-bit `int` với Java carrier `int` | Field số nguyên |
| `ValueLayout.JAVA_LONG` | Primitive 64-bit `long` với Java carrier `long` | Không tự đồng nhất với C `long` |
| `ValueLayout.ADDRESS` | Native pointer | `char*`, `void*`, function pointer |
| `MemoryLayout.sequenceLayout(n, element)` | Native array có `n` phần tử | `int[3]` |
| `MemoryLayout.structLayout(...)` | C-like struct, fields nối tiếp | `struct Point` |
| `MemoryLayout.unionLayout(...)` | C-like union, fields chồng nhau | Thể hiện nhiều cách xem cùng bytes |
| `MemoryLayout.paddingLayout(n)` | Padding chính xác `n` bytes | Bù khoảng căn lề theo C ABI |

### C struct, alignment và padding

C source:

~~~c
/* Đây là C declaration minh họa, không phải file đầy đủ. */
struct Tagged {
    char kind;
    int value;
};
~~~

Trên ABI có `char` 1 byte, `int` 4 byte và yêu cầu căn `int` theo 4-byte boundary, field `value` nằm ở offset **4** và struct có size thường là **8**. `MemoryLayout.structLayout` **không tự thêm ba byte padding**:

~~~java
MemoryLayout tagged = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));
long offset = tagged.byteOffset(
        MemoryLayout.PathElement.groupElement("value")); // 4
~~~

Không mặc định struct layout này tương thích mọi compiler. Thông số thật phải đối chiếu từ C `sizeof(struct Tagged)`, `_Alignof`/`alignof` và `offsetof(struct Tagged, value)`, đặc biệt nếu có packing flags, bitfields hoặc ABI khác.

### VarHandle và layout path

Struct hai trường `int`:

~~~java
MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
VarHandle x = point.varHandle(
        MemoryLayout.PathElement.groupElement("x"));
VarHandle y = point.varHandle(
        MemoryLayout.PathElement.groupElement("y"));
~~~

Nếu `seg` được cấp theo `point`, đọc/ghi:

~~~java
// Fragment: seg là MemorySegment phù hợp và còn sống.
x.set(seg, 0L, 7);
y.set(seg, 0L, 35);
int sum = (int) x.get(seg, 0L) + (int) y.get(seg, 0L);
~~~

`0L` là tọa độ **base offset** của layout-derived VarHandle. Với layout path chứa một `PathElement.sequenceElement()` dạng open path, var handle có **thêm** tọa độ `long` cho index của element; API không tự đoán chỉ số.

### Mảng native

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemoryLayout triple = MemoryLayout.sequenceLayout(
            3, ValueLayout.JAVA_INT);
    MemorySegment numbers = arena.allocate(triple);
    for (int i = 0; i < 3; i++) {
        numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
    }
    int sum = 0;
    for (int i = 0; i < 3; i++) {
        sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
    }
    System.out.println(sum); // 6
}
~~~

`setAtIndex`/`getAtIndex` tính index theo size của ValueLayout và kiểm tra bounds. Không tự xem native array thành Java `int[]` hoặc cho rằng kích thước `JAVA_INT` luôn trùng C `long`.

## 6. SymbolLookup: tìm symbol địa chỉ, không tìm type

`SymbolLookup` tra một tên symbol trong một hoặc nhiều native libraries. `lookup.find("name")` trả `Optional<MemorySegment>`; memory segment của **địa chỉ symbol** thường có kích thước 0 byte. Nó có nghĩa “địa chỉ hàm/biến”, **không** có nghĩa một buffer dữ liệu có thể đọc `get(JAVA_INT,0)`.

Ba lựa chọn cần biết:

- `Linker.nativeLinker().defaultLookup()`: tìm một tập native symbols mà linker nền tảng quyết định expose (ví dụ `strlen` trên nhiều runtime Linux/macOS/Windows). Danh sách symbol **không được cam kết đồng nhất trên mọi OS/JVM**.
- `SymbolLookup.libraryLookup(Path, Arena)` hoặc `libraryLookup(String, Arena)`: nạp/tra library cụ thể do ứng dụng sở hữu. Lookup và khả năng unload gắn với arena; phải giữ arena còn sống trong lúc gọi native.
- `SymbolLookup.loaderLookup()`: tìm symbols từ native libraries nạp bằng `System.load` hoặc `System.loadLibrary` theo class loader phù hợp; **không tự động bao phủ mọi library nạp bằng `libraryLookup`**.

Cách tra symbol:

~~~java
Linker linker = Linker.nativeLinker();
SymbolLookup lookup = linker.defaultLookup();
MemorySegment strlenAddress = lookup.find("strlen")
        .orElseThrow(() -> new IllegalStateException(
                "strlen unavailable in default lookup"));
~~~

`find` không tìm được → báo lỗi hoặc chọn explicit library; không gọi một địa chỉ null. **Tìm thấy symbol cũng chưa xác minh signature C**. Nếu thư viện export `sum` nhận ba tham số, `SymbolLookup` không tự báo cho linker điều đó; bạn phải đọc C header và cung cấp `FunctionDescriptor` chính xác.

### Phạm vi của native library

~~~java
// Fragment minh họa libraryLookup cho Linux.
try (Arena libraryArena = Arena.ofConfined()) {
    SymbolLookup ownLib = SymbolLookup.libraryLookup(
            Path.of("libffm_math.so").toAbsolutePath(), libraryArena);
    MemorySegment address = ownLib.find("ffi_add").orElseThrow();
    // Chỉ gọi native trong lifetime hợp lệ của libraryArena.
}
~~~

Không cache địa chỉ primitive `long` rồi dùng lại sau libraryArena.close: native machine code có thể đã bị unload. `SymbolLookup.loaderLookup` khác `libraryLookup` về class loader và cơ chế nạp; không dùng thay nhau mà không kiểm tra.

## 7. Linker: bridge Java MethodHandle ↔ C ABI

`Linker.nativeLinker()` chọn linker theo ABI của JVM hiện tại: OS, CPU, calling convention và các kiểu native tương ứng. Nó không biên dịch C source; nó chuyển **địa chỉ function + `FunctionDescriptor`** thành callable `MethodHandle`.

Ví dụ C `size_t strlen(const char*)`:

~~~text
Return C size_t  -> canonical layout "size_t"
Argument char*   -> ValueLayout.ADDRESS

SymbolLookup      -> strlenAddress
FunctionDescriptor-> (ADDRESS) -> size_t
Linker             -> MethodHandle
MethodHandle       -> gọi hàm C theo native ABI
~~~

Để không mặc định `size_t` luôn là Java `long`:

~~~java
Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
if (sizeT == null) throw new IllegalStateException("size_t unavailable");

FunctionDescriptor signature = FunctionDescriptor.of(
        sizeT, ValueLayout.ADDRESS);
MethodHandle strlen = linker.downcallHandle(
        strlenAddress, signature);
~~~

`canonicalLayouts()` công bố mapping kiểu native theo ABI; C `long` trên Windows 64-bit thường 32 bit, còn Linux x64 thường 64 bit. `size_t` thường rộng 64 bit trên các platform 64-bit nhưng không được đồng nhất với `JAVA_LONG` bất kể máy nào.

Khi gọi, `MethodHandle.invokeExact` đòi kiểu Java ở call-site khớp **chính xác** carrier/arity của handle. Nếu descriptor có return Java `long` và tham số `MemorySegment`, một cách gọi phù hợp trên nền tảng đó là `long n = (long) strlen.invokeExact(cString)`. Dùng `invokeWithArguments` đơn giản hơn khi minh họa carrier thay đổi theo ABI, nhưng có overhead và **không** thể sửa descriptor C sai.

### Sai signature native có thể làm JVM crash

~~~java
// Fragment SAI, tuyệt đối không chạy:
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
// Sai: strlen(const char*) lại bị mô tả như int strlen(int).
~~~

Symbol name thường không chứa return/argument types. Linker không thể kiểm tra `wrong` với C header thật; nếu Java dùng pointer rác, native code có thể dereference địa chỉ không hợp lệ. Cần đối chiếu **số lượng, thứ tự, độ rộng, alignment, pointer, struct-by-value, varargs** theo đúng ABI.

`Linker.upcallStub(target, descriptor, arena)` là chiều ngược: biến Java method handle thành native function pointer để C gọi lại Java. Stub gắn lifetime với arena, và Java callback cần xử lý exception trong Java trước khi thoát sang C. Bài này tập trung **downcall** để làm rõ năm khối cơ bản.

## 8. Ví dụ Java hoàn chỉnh JDK 22+: struct, array, lookup và strlen

Chương trình sau không cần JNI `.h` header hay C adapter. Nó truy cập native memory, gọi C standard-library `strlen` qua default lookup và chứng minh truy cập Java FFM sau `Arena.close` bị từ chối.

**Giới hạn môi trường:** `strlen` phải được exposed bởi default lookup của linker. Đã chạy thật trên **Windows x64 với JDK 24**, biên dịch `--release 22`. Trên runtime mà default lookup không có symbol đó, chương trình báo lỗi rõ và người học có thể chuyển sang `libraryLookup` chỉ tới một C library cụ thể.

### 8.1. File `FfmModelDemo.java` (source đầy đủ)

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public final class FfmModelDemo {
    public static void main(String[] args) throws Throwable {
        MemoryLayout pointLayout = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("x"),
                ValueLayout.JAVA_INT.withName("y"));

        VarHandle xHandle = pointLayout.varHandle(groupElement("x"));
        VarHandle yHandle = pointLayout.varHandle(groupElement("y"));
        MemorySegment retired;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment point = arena.allocate(pointLayout);
            xHandle.set(point, 0L, 7);
            yHandle.set(point, 0L, 35);

            int x = (int) xHandle.get(point, 0L);
            int y = (int) yHandle.get(point, 0L);
            System.out.println("point=(" + x + "," + y + ")");

            MemoryLayout triple = MemoryLayout.sequenceLayout(
                    3, ValueLayout.JAVA_INT);
            MemorySegment numbers = arena.allocate(triple);
            for (int i = 0; i < 3; ++i) {
                numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
            }

            int sum = 0;
            for (int i = 0; i < 3; ++i) {
                sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
            }
            System.out.println("arraySum=" + sum);

            Linker linker = Linker.nativeLinker();
            MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
            if (sizeT == null) {
                throw new IllegalStateException("size_t unavailable");
            }

            SymbolLookup symbols = linker.defaultLookup();
            MemorySegment strlenAddress = symbols.find("strlen")
                    .orElseThrow(() -> new IllegalStateException(
                            "strlen unavailable in default lookup"));

            FunctionDescriptor signature = FunctionDescriptor.of(
                    sizeT, ValueLayout.ADDRESS);
            MethodHandle strlen = linker.downcallHandle(
                    strlenAddress, signature);

            MemorySegment cString = arena.allocateFrom("hello FFM");
            long length = ((Number) strlen.invokeWithArguments(cString))
                    .longValue();
            System.out.println("strlen=" + length);

            if (x + y != 42 || sum != 6 || length != 9) {
                throw new AssertionError("Unexpected result");
            }

            retired = point;
        }

        try {
            retired.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("Use-after-close accepted");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

File hoàn chỉnh, không package. `VarHandle.set/get(point,0L,...)` dùng tọa độ base offset; `Arena.allocateFrom("hello FFM")` tạo C string UTF-8 có byte NUL kết thúc. `strlen` trả 9 vì chuỗi ASCII có 9 byte trước terminator, không tính byte NUL.

### 8.2. Lệnh build và chạy

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out FfmModelDemo.java
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

**Windows CMD/PowerShell:** tạo thư mục `out` nếu chưa có, rồi:

~~~bat
mkdir out
javac --release 22 -d out FfmModelDemo.java
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

Bỏ qua lỗi “directory already exists” nếu `out` có từ lần chạy trước. **Không cần `javac -h`, `jni.h`, C compiler hoặc `-Djava.library.path`** cho ví dụ mặc định này. `--enable-native-access=ALL-UNNAMED` cấp quyền thực hiện restricted native operations cho code trên classpath; xem mục phiên bản và security phía dưới.

### 8.3. Stdout chính xác khi symbol có mặt

~~~text
point=(7,35)
arraySum=6
strlen=9
afterClose=IllegalStateException
RESULT: PASS
~~~

Đã xác nhận trên JDK 24 Windows x64, biên dịch với `javac --release 22` và chạy với `--enable-native-access=ALL-UNNAMED`. Nếu `strlen` không nằm trong default lookup của platform, bạn sẽ thấy `IllegalStateException("strlen unavailable in default lookup")` thay vì output PASS. Đây là sự khác biệt về **symbol exposure** chứ không phải bằng chứng FFM không hoạt động.

### 8.4. Phân tích đường dữ liệu và ownership

1. `pointLayout` mô tả hai field Java `int`; `xHandle`/`yHandle` cho cách truy cập theo tên. Không có Java class `Point` được cấp phát trong native memory; chỉ có bytes.
2. `Arena.ofConfined` là owner của `point`, `numbers` và `cString`. Tất cả đều được dùng đồng bộ trên thread tạo arena.
3. `numbers.setAtIndex` ghi 1,2,3; `getAtIndex` đọc lại thành 6, có kiểm tra bounds.
4. `Linker.nativeLinker` lấy ABI đang chạy; `size_t` được chọn qua canonical layouts, tránh ép C type thành Java long trên tất cả ABI.
5. `SymbolLookup.defaultLookup` tìm `strlen`, trả segment biểu diễn địa chỉ function. Không đọc field của segment zero-length đó.
6. `FunctionDescriptor.of(sizeT, ADDRESS)` khai báo một tham số pointer và return `size_t`. `downcallHandle` tạo callable method handle.
7. `Arena.allocateFrom` đặt C string ở native memory; `strlen.invokeWithArguments` chạy **trong khi arena còn sống**. C nhận pointer tới dữ liệu UTF-8 có terminator.
8. Sau khi rời `try`, arena close; `retired` là Java object/view còn tồn tại nhưng backing memory đã invalid. `retired.get(...)` bị chặn và được test bắt đúng exception.

PASS xác nhận kịch bản này, **không chứng minh mọi native function an toàn**; C có thể làm điều nguy hiểm ngoài vùng Java checks.

## 9. Một ví dụ độc lập khác: dùng SymbolLookup.libraryLookup với thư viện C riêng

`defaultLookup` là mô hình “nền tảng cung cấp symbol”. Để hiểu mô hình “ứng dụng sở hữu thư viện”, có thể tự viết hàm C xuất symbol thông thường, không dùng JNI glue.

### 9.1. File `native/ffm_math.c`

~~~c
#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

API int ffi_add(int a, int b) {
    return a + b;
}
~~~

Trên nền tảng mục tiêu thông dụng, C `int` là 32 bit. Khi hỗ trợ một compiler/ABI khác, cần xác minh điều này trước khi map sang `ValueLayout.JAVA_INT`.

Build native library:

**Linux:**

~~~sh
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libffm_math.so native/ffm_math.c
~~~

**macOS:**

~~~sh
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libffm_math.dylib native/ffm_math.c
~~~

**Windows MSVC Developer Command Prompt:**

~~~bat
cl /nologo /W4 /LD native\ffm_math.c /Fe:ffm_math.dll
~~~

Dùng compiler target cùng architecture với JVM. Tên symbol có thể bị decorate ở một số ABI, đặc biệt 32-bit Windows; kiểm tra bằng `nm` hoặc `dumpbin /EXPORTS` nếu lookup không tìm thấy.

### 9.2. File `FfmAddDemo.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmAddDemo {
    public static void main(String[] args) throws Throwable {
        String file = System.mapLibraryName("ffm_math");
        Path library = Path.of(file).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                    SymbolLookup.libraryLookup(library, arena);
            MemorySegment address = lookup.find("ffi_add")
                    .orElseThrow(() -> new IllegalStateException(
                            "ffi_add export not found"));

            Linker linker = Linker.nativeLinker();
            FunctionDescriptor signature = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);
            MethodHandle add =
                    linker.downcallHandle(address, signature);

            int result = (int) add.invokeExact(20, 22);
            System.out.println("ffi_add(20,22)=" + result);
            if (result != 42) {
                throw new AssertionError("Bad native result");
            }
        }
        System.out.println("RESULT: PASS");
    }
}
~~~

Chạy trong thư mục chứa native binary đã build:

~~~sh
javac --release 22 FfmAddDemo.java
java --enable-native-access=ALL-UNNAMED FfmAddDemo
~~~

Expected stdout **nếu native library/export/ABI đúng**:

~~~text
ffi_add(20,22)=42
RESULT: PASS
~~~

Đây là bài tập bổ sung có C compiler; **chưa chạy thử C library này trong phiên làm việc hiện tại**, nhưng Java/C signatures được thiết kế nhất quán. `System.mapLibraryName` chọn tên file tương ứng OS; `Path.of(file).toAbsolutePath()` cần thực sự trỏ đúng file. `SymbolLookup.libraryLookup` có thể nạp thư viện theo đường dẫn, không cần `System.loadLibrary` hay `javac -h`.

Khi `try` kết thúc, arena sở hữu library lookup được đóng. Đừng cache `MethodHandle` hoặc địa chỉ `ffi_add` và gọi sau đó: function code có thể đã bị unload. Nếu nhiều Java threads cùng gọi thư viện, dùng một **owner giữ arena sống cho toàn bộ binding**, ngăn calls mới rồi đợi in-flight calls kết thúc trước khi đóng.

## 10. C ABI: sai descriptor nguy hiểm hơn lỗi kiểu Java

| C concept | FFM layout gợi ý | Lưu ý |
|---|---|---|
| `int` 32-bit | `ValueLayout.JAVA_INT` | Xác minh ABI, không đoán |
| `long long` 64-bit | Thường `ValueLayout.JAVA_LONG` | Kiểm tra độ rộng trong C |
| `long` | Canonical layout theo ABI | Windows 64-bit thường 32-bit; Linux x64 thường 64-bit |
| `size_t` | `linker.canonicalLayouts().get("size_t")` | Không nhất thiết luôn là Java `long` |
| `void*`/`char*` | `ValueLayout.ADDRESS` | Kích thước, lifetime và nullability phải có hợp đồng |
| `struct` | `structLayout` + `paddingLayout` | Xác minh `sizeof`, alignment, `offsetof` |
| `T[n]` | `sequenceLayout(n, typeLayout)` | Stride theo layout element |
| C callback pointer | `Linker.upcallStub` | Lifetime arena và quy tắc exception/thread |

Một `MemorySegment` pointer có thể hợp lệ tại thời điểm tạo nhưng native code vẫn ghi quá bounds, hoặc trả pointer tới `malloc` và kỳ vọng caller gọi `free` đúng API. FFM Java không tự hiểu quyền sở hữu do thư viện C quy định. Nếu C trả raw pointer chưa kèm kích thước, đừng `reinterpret` bừa: operation đó restricted và khai sai size có thể gây crash hoặc silent corruption.

Native C `char*` và Java `String` cũng khác nhau: `Arena.allocateFrom(String)` tạo C string UTF-8 kết thúc NUL; C `strlen` trả **số bytes**, không phải số Java UTF-16 code units hoặc code points. Với Unicode tiếng Việt, kết quả thường khác `String.length()`.

Đối với C variadic functions (ví dụ `printf`), descriptor phải mô tả specialized argument list và có `Linker.Option.firstVariadicArg(...)` khi cần; không copy công thức `FunctionDescriptor.of(return,args...)` từ non-variadic call rồi đoán promotion. Endianness, packed structs, unions và C calling conventions cũng là phần contract ABI.

### Function pointer và data pointer khác nhau về mục đích

`SymbolLookup.find("ffi_add")` trả segment biểu diễn **địa chỉ symbol**. Nó không cấp phát một buffer dữ liệu để ghi `set(JAVA_INT,0,...)`. Với một global native variable, địa chỉ tra được có thể cần mô tả/điều chỉnh size một cách có chứng cứ; với một native function, đưa address cho `Linker.downcallHandle`.

Một `MethodHandle` có `type()` bên Java, nhưng đó là **Java calling signature được tạo từ FunctionDescriptor**; nó không chứng minh native symbol thật sự có cùng C signature. Muốn an toàn phải kiểm tra C header/ABI và test ở nền tảng triển khai.

## 11. Lifetime và đồng thời: Arena.ofShared không tự khóa dữ liệu

Nhiều lỗi production không đến từ cách gọi API mà từ shutdown:

~~~text
Thread A                         Thread B
------------------------------   -----------------------------
Arena.ofShared() cấp buffer
                                 downcall C nhận pointer buffer
close arena
                                 C tiếp tục đọc pointer cũ -> nguy hiểm
~~~

Java scope safety không có khả năng buộc C dừng ngay khi Java gọi `close`. Nếu native call/callback còn dùng buffer, phải có **protocol đợi** hoàn tất trước khi giải phóng. Có thể quản lý state:

~~~text
OPEN
  cho phép downcall mới; in-flight count++
CLOSING
  không cho nhận calls mới; chờ count về 0
CLOSED
  release native callbacks/buffers; close arena và library scope
~~~

Đối với synchronous `strlen` trong bài, C không lưu pointer và hàm return trước `arena.close()` nên an toàn về lifetime. Với asynchronous C API, một arena có lifetime của **session** phù hợp hơn call-local arena. Không truyền pointer của confined arena sang thread khác rồi mong thread đó truy cập hợp lệ chỉ vì địa chỉ là số nguyên.

### Library arena cũng phải sống đủ lâu

Nếu đã dùng `SymbolLookup.libraryLookup(..., arena)`, thư viện có thể unload khi arena đóng. Không chỉ cần buffer sống tới khi native call xong, mà **function code** cũng phải còn load khi `MethodHandle` được gọi. Với upcall stub tương tự: Java stub của `Linker.upcallStub` có lifetime của arena; C phải unregister callback và không gọi function pointer sau khi đóng scope.

### Arena.ofAuto() và global() không phải lối thoát khỏi thiết kế

`ofAuto()` không có thời hạn cleanup cụ thể; `global()` có lifetime không giới hạn. Chúng có những use cases hợp lệ nhưng không thể được dùng như cách lờ đi việc thiết kế owner. Nếu một native library cần explicit `destroy(handle)`, hãy giữ contract đóng rõ ràng thay vì chỉ trông vào GC.

## 12. Native access, restricted methods và flags

FFM là finalized từ JDK 22 nhưng có các **restricted operations** như tạo downcall handle, upcall stub, library lookup, hoặc thay đổi phạm vi của raw pointer bằng `reinterpret`. Các operation này có thể khiến JVM crash nếu developer cung cấp ABI/address sai.

Khi chạy code trong **unnamed module/classpath**:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

Khi triển khai trong named module, cấp native access cho **module thực sự chứa code FFM**, ví dụ `--enable-native-access=com.example.binding`. Một số JDK releases cảnh báo restricted native access khi chưa cấp quyền; chính sách của các JDK mới có thể chặt hơn. Không nên phỏng đoán hành vi khi thiếu flag — xem đúng JDK docs và log runtime.

**Phân biệt các cờ:**

- `--enable-native-access`: cho phép code trong một module thực hiện restricted native operations.
- `--enable-preview`: dùng cho bản Java có preview features; **không cần để chạy FFM finalized trên JDK 22+**.
- `--add-modules jdk.incubator.foreign`: thuộc API incubator lịch sử ở JDK 17, không áp dụng cho `java.lang.foreign` finalized.
- `-cp`/`--class-path`: tìm Java classes, không phải thư viện native.
- `-Djava.library.path`: liên quan cơ chế tìm native libraries nhất định, không tự động làm `Linker.defaultLookup` tìm mọi file tùy ý trên disk.

Quyền native access **không biến code C không an toàn thành code an toàn**. Production vẫn cần kiểm soát nguồn binary, signatures, error handling và lifecycle.

## 13. Các thế hệ FFM Java: tránh trộn ví dụ khác version

| JDK | Trạng thái | Cách đọc tài liệu |
|---|---|---|
| 17–18 | FFM API incubator, package lịch sử `jdk.incubator.foreign` | Không lấy nguyên source của bài này chạy trên 17; API và flags khác |
| 19–21 | FFM trải qua các bản preview và có điều chỉnh API | Cần API/Javadoc đúng từng release và preview flags khi áp dụng |
| **22** | **Finalized**, JEP 454, `java.lang.foreign` | Source bài này chọn JDK 22 là baseline |
| 23+ | API stable được duy trì, có thể thay đổi chi tiết và native-access policy theo release | Đối chiếu Javadoc/notes bản đang deploy |

Chương trình `FfmModelDemo` được **biên dịch `--release 22` và chạy trên JDK 24**, không cần preview. Không nên chỉ đổi tên package trong một tutorial FFM JDK 17 rồi mong tương thích: design surface của `MemorySession`/`ResourceScope` trong bản cũ khác `Arena` finalized.

Với dự án hỗ trợ nhiều JDK, có thể cần source sets riêng hoặc đặt baseline JDK 22+. Nếu buộc hỗ trợ Java 17, một số integrations sẽ hợp lý hơn khi dùng JNI ổn định hoặc bindings riêng thích hợp thay vì API FFM incubator chưa nhất quán.

## 14. FFM và JNI: mỗi cơ chế có điểm mạnh riêng

| Mục tiêu | FFM JDK 22+ | JNI |
|---|---|---|
| Gọi C function ABI rõ | `SymbolLookup` + `Linker` + `MethodHandle`, không cần JNI adapter | `native` method + C/JNI bridge |
| Đọc/ghi buffer native | `MemorySegment`, `Arena`, `MemoryLayout` | JNI arrays, direct buffers, hoặc C malloc |
| Gọi Java từ native | FFM `upcallStub` với function pointer contract | `JNIEnv *`, `Call*Method` |
| Quản lý Java references/classes | Không phải mục tiêu trung tâm của FFM | JNI có API riêng cho local/global refs và Java object operations |
| Chạy nguyên source mẫu trên Java 17 | Không | JNI có hỗ trợ lâu đời |
| Rủi ro | ABI descriptor, native pointers, arena/library lifetime | JNI refs, thread attach, C memory misuse |

FFM phù hợp khi cần binding C ABI cụ thể, native memory với lifetime rõ và baseline JDK 22+. JNI hợp lý khi cần tương tác sâu với JVM object model hoặc phải hỗ trợ JDK cũ. **Cả hai không thay thế yêu cầu kiểm thử native code**. Công cụ `jextract` có thể hỗ trợ tạo bindings từ C headers, nhưng không thay developer kiểm tra ownership/ABI.

## 15. Troubleshooting theo tầng

| Lỗi quan sát | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
|---|---|---|
| `package java.lang.foreign does not exist` | JDK build/target trước 22 | Dùng JDK 22+, đặt `--release 22` |
| `cannot find symbol allocateFrom` | API theo JDK cũ/preview | Đọc Javadoc đúng release, tránh trộn bản |
| Cảnh báo restricted native API | Chưa cấp quyền native access theo chính sách JDK | `--enable-native-access=ALL-UNNAMED` hoặc tên module |
| `IllegalCallerException` | Module caller không được phép gọi restricted API | Sửa launcher/module configuration |
| `strlen unavailable in default lookup` | Runtime không expose symbol | `find` kiểm tra, chọn custom libraryLookup |
| `ffi_add export not found` | Native symbol name/visibility/ABI decoration | `nm`/`dumpbin` và xác nhận đúng file library |
| Library load failure | Sai path, kiến trúc, thư viện phụ thuộc | Kiểm tra absolute `Path`, binary format, dependencies |
| `WrongMethodTypeException` | Java `invokeExact` không khớp carrier | Xem `MethodHandle.type()`, sửa call-site signature |
| JVM crash trong downcall | C ABI signature sai, C ghi ra ngoài memory | Đọc C header, kiểm tra descriptor, dùng ASan/native debugger |
| `IndexOutOfBoundsException` | Offset hoặc layout vượt segment | `byteSize()` và index/field offsets |
| `IllegalStateException` sau close | Segment không còn scope hợp lệ | Dời use trước `arena.close` hoặc kéo lifetime phù hợp |
| `WrongThreadException` | Confined segment từ thread khác | Giữ một owner thread hoặc dùng shared + synchronization |
| C struct trả giá trị sai | Sai padding/alignment/endianness | `sizeof`/`offsetof` và layout tests |
| C `strlen` đếm khác Java length | C đếm UTF-8 bytes đến NUL | Xác nhận encoding và terminator |
| Native memory tăng mãi | Arena global/auto không hợp contract, native malloc không free | Theo dõi allocation/close; profile native heap |
| MethodHandle đã cache gây crash sau shutdown | Library đã unload | Chặn downcall mới, đợi in-flight rồi close library arena |

**Lưu ý:** Java-side access exceptions là failures có thể chẩn đoán, nhưng khi C ABI/implementation ghi bậy vào vùng native, JVM có thể chết trước khi Java kịp ném exception. Không thay kiểm thử C bằng một `try/catch(Throwable)` bao trọn downcall.

## 16. Câu hỏi tự kiểm tra và đáp án

**1. Arena và MemorySegment có giống nhau không?**  
Không. Arena cấp/giữ scope để quản lý lifetime; MemorySegment là view một vùng byte trong scope đó. Một arena có thể cấp nhiều segments.

**2. Có MemoryLayout rồi có cần allocate không?**  
Có. MemoryLayout chỉ mô tả kích thước/kiểu/offset. `arena.allocate(layout)` mới cấp native memory. VarHandle trên layout dùng với segment đã cấp đúng phạm vi.

**3. Vì sao field `value` trong C struct `{ char kind; int value; }` không luôn ở offset 1?**  
Do alignment/padding ABI. Nếu C đặt value ở offset 4 thì Java structLayout cần ba byte padding. Phải xác minh C `offsetof` thay vì đoán.

**4. SymbolLookup trả về đầy đủ chữ ký native function chưa?**  
Chưa. Nó chủ yếu cho địa chỉ symbol. `FunctionDescriptor` và C header/ABI mới xác định return/parameter layout. Descriptor sai có thể crash JVM.

**5. Vì sao không dùng Java `long` cứng cho C `size_t`?**  
Vì C `size_t` là platform-dependent type; lấy canonical layout từ linker cho ABI đang chạy. `invokeExact` cũng cần Java carrier đúng theo layout ấy.

**6. Arena.ofShared làm thao tác ghi segment thread-safe tự động?**  
Không. Shared arena cho phép nhiều threads truy cập, nhưng không tự đặt lock trên fields. Cần protocol đồng bộ và ngăn close khi worker/native function còn dùng pointer.

**7. Sau khi đóng arena của libraryLookup, Java MethodHandle còn là Java object. Có gọi lại được không?**  
Không được giả định. Library có thể bị unload; call qua stale function pointer nguy hiểm. Owner binding phải giữ library arena sống đến sau downcall cuối.

**8. Mã `FfmModelDemo` có cần `--enable-preview` không?**  
Không. Nó dùng FFM finalized JDK 22+. Dùng `--enable-native-access=ALL-UNNAMED` để cấp quyền restricted native operations cho classpath.

**9. C `strlen("á")` trả bằng Java `"á".length()` không?**  
Không nhất thiết. C đếm bytes UTF-8 đến NUL, còn Java `String.length()` đếm UTF-16 code units. Hai số có thể khác.

**10. FFM có thể hoàn toàn bảo vệ JVM trước C code sai không?**  
Không. Java FFM bounds/scope/thread checks bảo vệ truy cập từ Java, nhưng native C được cấp pointer có thể vi phạm bounds/lifetime/ABI và làm hỏng bộ nhớ.

## 17. Checklist khi đưa FFM binding vào dự án

- [ ] Chọn rõ baseline JDK 22+ và native-access flags; không trộn incubator/preview sources.
- [ ] Mỗi native buffer có owner arena, thời điểm close và đối tượng mượn rõ ràng; không dùng sau close.
- [ ] Thread access của confined/shared arena được hiểu đúng; có synchronization nếu nhiều thread ghi/đọc mutable state.
- [ ] Mọi `MemoryLayout` khớp C ABI thật: size, alignment, padding, field offsets, arrays, pointer width, endianness.
- [ ] `SymbolLookup` chọn đúng source: default, library, loader; tên symbol đã được xác nhận trên native binary.
- [ ] `FunctionDescriptor` đối chiếu chữ ký thật trong C header: return, order, carrier, varargs, structs, calling convention.
- [ ] `MethodHandle` Java type và cách invoke được test; không nhầm `WrongMethodTypeException` với ABI mismatch.
- [ ] Input C strings có terminator/encoding; output buffers đủ kích thước, C không ghi tràn.
- [ ] Upcall stubs, library arenas và buffers sống cho tới khi mọi native users đã dừng.
- [ ] Shutdown ngăn callers mới, đợi in-flight work, unregister callbacks rồi mới close arenas.
- [ ] Native library/version/architecture được quản lý như dependency, không tra địa chỉ raw rồi cache vô thời hạn.
- [ ] Unit tests kiểm tra struct/array/downcall/after-close; CI thử trên OS/ABI thực tế và dùng native tools khi có lỗi.
- [ ] Không coi một lần chạy PASS là bằng chứng mọi native function đều an toàn.

## 18. Tổng kết và tài liệu chính thức

Nhớ mô hình ngắn:

~~~text
Arena         = owner và lifetime
MemorySegment = vùng nhớ và bounds/scope
MemoryLayout  = kiểu dữ liệu trong bytes, alignment/offset
SymbolLookup  = địa chỉ native symbol
FunctionDescriptor = chữ ký C ABI
Linker        = cầu nối ABI
MethodHandle  = lời gọi native từ Java
~~~

Chương trình FFM đúng phải trả lời đồng thời: **vùng nhớ còn sống không, ai được truy cập, layout có đúng C không, symbol có đúng thư viện không, function descriptor có khớp C ABI không, và library code còn load khi gọi không?** Năm thành phần bổ sung nhau, không có thành phần nào tự sửa những điều kiện sai ở phần khác.

Tài liệu chính thức để kiểm tra phiên bản và semantics:

- [JEP 454 – Foreign Function & Memory API, finalized JDK 22](https://openjdk.org/jeps/454)
- [Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)

Với JDK mới hơn, tra đúng Javadoc/release notes của runtime đang dùng, đặc biệt đối với restricted native access và những thay đổi chính sách; đừng suy từ một tutorial bản preview cũ sang bản finalized.