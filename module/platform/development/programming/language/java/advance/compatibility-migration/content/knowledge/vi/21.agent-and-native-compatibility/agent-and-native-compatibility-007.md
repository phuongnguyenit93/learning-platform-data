# Foreign Function & Memory API và ràng buộc khi chuyển từ giải pháp cũ

Trong nhiều hệ thống Java lâu năm, phần nghiệp vụ chạy trên JVM nhưng vẫn cần gọi mã C/C++, sử dụng thư viện native của hệ điều hành hoặc truy cập vùng nhớ nằm ngoài Java heap. Các dự án thường giải quyết nhu cầu này bằng **JNI**, thư viện wrapper như **JNA**, `sun.misc.Unsafe`, `ByteBuffer.allocateDirect()`, hoặc một agent/native bridge được đóng gói riêng. Những giải pháp đó có thể đã hoạt động ổn định nhiều năm nhưng bộc lộ ràng buộc khi nâng JDK: phải biên dịch lại native code, gặp lỗi module access, phụ thuộc vào ABI/hệ điều hành, hoặc không còn dùng được API nội bộ mà bản thư viện cũ dựa vào.

**Foreign Function & Memory API (FFM API)** cung cấp cách truy cập bộ nhớ và gọi hàm native thông qua API Java chuẩn. Cách tiếp cận này giúp giảm nhu cầu viết JNI glue code cho nhiều tình huống, đồng thời mô hình hóa rõ hơn kích thước bộ nhớ, phạm vi sống và thread ownership. Nhưng FFM không biến mã native thành mã Java an toàn tuyệt đối, không xóa khác biệt ABI giữa Windows/Linux/macOS, và cũng **không thay thế mọi chức năng của JNI, JVMTI hoặc Java agent**.

Trong Java Advance Compatibility Migration, cần phân biệt hai loại thay đổi:

- **Nâng JDK nhưng giữ JNI/JNA hoặc native bridge hiện tại:** ưu tiên chứng minh compatibility với JDK mới, không nhất thiết phải chuyển sang FFM ngay.
- **Chủ động thay native bridge cũ bằng FFM:** là migration kiến trúc có thay đổi API, ownership, packaging, callback, bảo mật và hiệu năng; cần thiết kế/test riêng.

Bài học này tập trung vào lịch sử FFM qua các JDK, những API và ràng buộc thực tế, ví dụ Java 22+, ma trận so sánh với JNI/JNA/Unsafe và quy trình chuyển đổi có kiểm chứng.

## 1. Foreign Function & Memory API giải quyết vấn đề gì?

### 1.1. Hai nhu cầu thường đi cùng nhau

Một chương trình Java cần tương tác native thường phải làm hai việc:

1. **Foreign function:** tìm và gọi hàm trong thư viện native, ví dụ `sum_ints`, `sqlite3_open` hoặc một hàm có C ABI.
2. **Foreign memory:** cấp phát/đọc/ghi vùng nhớ ngoài heap để trao đổi dữ liệu với hàm native, bao gồm buffer, struct, array và con trỏ.

Nếu chỉ gọi hàm C có hai tham số `int` và kết quả `int`, bài toán tương đối nhỏ. Nhưng khi hàm nhận `struct*`, ghi vào output buffer, trả về pointer cần giải phóng, hoặc giữ callback dùng sau khi Java call kết thúc, migration trở nên phức tạp hơn nhiều.

### 1.2. Mô hình trước đây

JNI dùng native method được khai báo trong Java rồi implement bằng C/C++:

```java
public final class NativeMath {
    static {
        System.loadLibrary("mathbridge");
    }

    public static native int sum(int a, int b);
}
```

Thư viện native cần export entrypoint JNI thích hợp, quản lý `JNIEnv*`, handle, reference và exception bridge. Cách này linh hoạt nhưng tăng mã glue, trách nhiệm quản lý resources và yêu cầu build per-platform.

JNA giảm nhu cầu viết JNI glue thủ công bằng thư viện tự ánh xạ lời gọi native, nhưng dự án cần phụ thuộc vào JNA runtime/version và vẫn phải bảo đảm ánh xạ C ABI.

FFM bổ sung một hướng khác: mô tả function signature và memory layout bằng API Java, rồi tạo `MethodHandle` để gọi native function phù hợp.

### 1.3. FFM không phải giao thức truyền thông

FFM làm việc với memory và các hàm native **trong process hoặc thông qua dynamic library được nạp vào process**. Nó không tự mang lại isolation như RPC/gRPC, không chuyển mã C thành Java bytecode và không bảo vệ JVM khỏi mọi lỗi trong native code.

Nếu native library có thể crash, ghi ngoài buffer hoặc thực thi mã không tin cậy, cân nhắc chạy nó trong **process tách biệt** với protocol IPC rõ ràng. FFM không thay thế security boundary của hệ điều hành.

## 2. Lịch sử API và các mốc JDK

FFM trải qua nhiều vòng incubator/preview trước khi ổn định. Khi migration, **không được xem source code FFM trên JDK 17, 21 và 22 là tương đương**.

| JDK | Mốc phát triển | Trạng thái cần nhớ |
|---|---|---|
| JDK 14 | JEP 370 – Foreign-Memory Access API | Incubator về truy cập foreign memory |
| JDK 16 | JEP 393 – Foreign-Memory Access API | Lần incubator tiếp theo |
| JDK 17 | JEP 412 – Foreign Function & Memory API | Incubator; API/packaging chưa phải API chuẩn cuối cùng |
| JDK 19 | JEP 424 – Foreign Function & Memory API | Preview |
| JDK 20 | JEP 434 – Foreign Function & Memory API | Lần preview tiếp theo |
| JDK 21 | JEP 442 – Foreign Function & Memory API | Preview, vẫn có thể thay đổi |
| JDK 22 | JEP 454 – Foreign Function & Memory API | API được hoàn thiện (final) |

### 2.1. JDK 17 không cung cấp API final của JDK 22

Ở các giai đoạn incubator, API xuất hiện qua module/package riêng, ví dụ `jdk.incubator.foreign`, và yêu cầu cấu hình compiler/runtime tương ứng. Không thể copy nguyên code dùng `java.lang.foreign.Arena` hoặc `Linker` ở phiên bản chuẩn rồi chạy trên Java 17.

Nếu sản phẩm còn hỗ trợ runtime JDK 17, có thể cần:

- Tiếp tục JNI/JNA cho dòng hỗ trợ Java 17.
- Tách native implementation sau một interface dùng chung và có backend riêng theo JDK.
- Đợi đến lúc minimum runtime nâng lên JDK 22+ mới áp dụng FFM final.
- Dùng một phương án build/phân phối khác được kiểm thử, không giả định API preview sẽ tương thích ngược.

Không dùng reflection, hack module hoặc thêm JAR tùy ý để giả lập `java.lang.foreign` final trên JDK cũ.

### 2.2. JDK 21 vẫn là preview

Một chương trình dùng FFM preview trên JDK 21 phải compile/run theo quy tắc preview của JDK 21, ví dụ:

```bash
javac --enable-preview --release 21 ForeignDemo.java
java --enable-preview --enable-native-access=ALL-UNNAMED ForeignDemo
```

Cú pháp cần điều chỉnh theo classpath/module path và nhu cầu native access thực tế. **Không dùng source ví dụ FFM final JDK 22 rồi giả định mọi method/signature đã tồn tại y nguyên ở JDK 21.** Preview được phép thay đổi API và behavior trước khi final.

Preview feature cũng ràng buộc version runtime: bytecode dùng preview của một JDK thường phải chạy trên đúng release hỗ trợ nó với preview enabled. Điều này khác với `--release 21` thông thường dành cho một source không dùng preview.

### 2.3. Từ JDK 22: `java.lang.foreign`

API final gồm các kiểu như:

- `Arena`.
- `MemorySegment`.
- `MemoryLayout` và `ValueLayout`.
- `Linker`.
- `SymbolLookup`.
- `FunctionDescriptor`.

Các kiểu chính nằm trong package `java.lang.foreign` của Java SE. Từ JDK 22, không cần bật preview chỉ để compile source dùng FFM final. Tuy vậy, **các thao tác native bị giới hạn (restricted methods) có thể yêu cầu native-access permission** và chính sách đối với truy cập không được cấp phép phụ thuộc JDK release.

### 2.4. Nên chọn baseline nào?

| Sản phẩm | Lựa chọn nền tảng cần cân nhắc |
|---|---|
| Phải chạy trên JDK 17 | Giữ JNI/JNA hoặc adapter tương thích; không mặc định dùng FFM final |
| Chạy JDK 21 LTS và muốn ổn định | Đánh giá rủi ro của preview; có thể tiếp tục bridge hiện tại |
| Minimum runtime đã là JDK 22+ | Có thể dùng FFM final sau khi kiểm chứng OS/ABI/native access |
| Đang có JNI/JVMTI agent phức tạp | Tách phần native calls/memory có thể migrate khỏi phần agent callbacks/instrumentation |
| Hỗ trợ nhiều JDK/OS | Định nghĩa compatibility matrix và backend strategy; test từng tổ hợp |

Chọn FFM là quyết định kiến trúc gắn với **minimum supported JDK**, không chỉ với JDK của máy build.

## 3. Cấu trúc tổng quát của FFM

Một luồng gọi hàm native qua FFM có thể mô tả:

```text
Java application
      |
      v
SymbolLookup ----> tìm symbol trong thư viện native
      |
      v
FunctionDescriptor ----> mô tả tham số/giá trị trả về theo ABI
      |
      v
Linker.downcallHandle(...)
      |
      v
MethodHandle.invokeExact(...)
      |
      v
Native function trong cùng process
      |
      v
MemorySegment <---- đọc/ghi buffers/structs, quản lý bằng Arena
```

Bốn nhóm trách nhiệm:

1. **Library/symbol:** thư viện nào được nạp, symbol nào được tìm, namespace nào và lifetime của lookup.
2. **ABI mapping:** C type, return type, calling convention, alignment, padding và pointer width.
3. **Memory ownership:** ai cấp phát, ai giải phóng, thread nào được truy cập và native code có giữ pointer không.
4. **Operational safety:** native access permission, OS library path, deployment, crash containment, metrics và testing.

Nếu bỏ qua một nhóm, mã có thể compile nhưng vẫn sai khi gọi thật.

## 4. MemorySegment: vùng nhớ có kích thước và vòng đời

### 4.1. Khác gì một địa chỉ `long`?

Trong code cũ, một pointer có thể được biểu diễn bằng `long` hoặc `Pointer` của thư viện wrapper. Với `MemorySegment`, Java có abstraction thể hiện vùng nhớ, kích thước, phạm vi sống và một số giới hạn truy cập.

Ví dụ JDK 22+:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class SegmentExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocate(16);

            numbers.set(ValueLayout.JAVA_INT, 0, 42);
            numbers.set(ValueLayout.JAVA_INT, 4, 84);

            int first = numbers.get(ValueLayout.JAVA_INT, 0);
            int second = numbers.get(ValueLayout.JAVA_INT, 4);

            System.out.println(first + second); // 126
        }
    }
}
```

Điểm cần hiểu:

- `arena.allocate(16)` cấp 16 byte native memory thuộc arena.
- `ValueLayout.JAVA_INT` biểu diễn vùng dữ liệu `int` 32 bit theo layout phù hợp của API.
- Offset tính theo byte; không phải chỉ số phần tử.
- `MemorySegment.get/set` có thể kiểm tra giới hạn, alignment và lifetime theo contract.
- Khi thoát `try-with-resources`, confined arena được đóng và các segment phụ thuộc không còn hợp lệ.

Không dùng `MemorySegment` đã bị đóng; native pointer giữ lại sau khi arena đóng có thể trở thành dangling pointer.

### 4.2. Heap segment và native segment khác nhau

FFM cũng có thể tạo memory view từ Java heap arrays. Nhưng một Java heap segment không đồng nghĩa một pointer native ổn định có thể giữ tùy ý trong C code.

JVM có garbage collector, có thể di chuyển object trong heap; native linker/ABI yêu cầu các ràng buộc riêng. Nếu hàm C cần giữ pointer sau lời gọi, thường phải thiết kế native allocation có lifetime rõ ràng hoặc copy dữ liệu vào vùng nhớ thích hợp.

Đừng tự suy luận rằng mọi `MemorySegment` đều có thể truyền như một native address hợp lệ trong mọi ngữ cảnh. Cần kiểm tra loại segment và yêu cầu của method/hàm native.

### 4.3. Slice và offset

Một segment có thể biểu diễn một phần của vùng nhớ khác qua slice, giúp code làm việc với subrange có bounds. Ví dụ:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    MemorySegment firstEightBytes = block.asSlice(0, 8);

    firstEightBytes.set(ValueLayout.JAVA_INT, 0, 1234);
    // firstEightBytes.get(..., 8) sẽ vượt phạm vi 8 byte
}
```

Khi wrapper cũ xử lý `pointer + offset` bằng số học trực tiếp, chuyển sang slice có thể giúp mô hình hóa bounds rõ ràng hơn. Nhưng native code nhận pointer vẫn có thể đọc/ghi ngoài giới hạn được Java quản lý nếu C function không tuân thủ contract.

## 5. Arena: ai sở hữu bộ nhớ và được dùng trên thread nào?

### 5.1. Vì sao lifetime là vấn đề chính?

Một native function có thể:

- Chỉ đọc buffer trong lúc lời gọi đang thực thi.
- Ghi dữ liệu vào buffer rồi trả về.
- Trả pointer trỏ tới vùng nhớ tĩnh của thư viện.
- Trả pointer cần gọi native free function.
- Giữ pointer/callback để sử dụng sau khi lời gọi kết thúc.

Không thể áp một quy tắc “đóng Arena khi return” cho mọi trường hợp. **Lifetime thực tế phải dựa trên contract của native API.**

### 5.2. Các mô hình Arena

| Arena | Ý nghĩa sử dụng | Rủi ro/điểm kiểm tra |
|---|---|---|
| `Arena.ofConfined()` | Bộ nhớ gắn với một thread owner và có thể đóng chủ động | Truy cập từ thread khác không hợp lệ theo confinement |
| `Arena.ofShared()` | Bộ nhớ có thể truy cập từ nhiều thread, đóng chủ động | Cần đồng bộ riêng, kiểm soát concurrent close |
| `Arena.ofAuto()` | Vòng đời do GC quản lý | Không phù hợp khi cần giải phóng đúng thời điểm |
| `Arena.global()` | Vòng đời gắn với process/runtime | Khó kiểm soát tài nguyên dài hạn; tránh lạm dụng |

Tùy JDK version, chi tiết API và semantics có thể thay đổi; bảng áp dụng cho FFM final trong JDK 22+. Confined arena kiểm soát thread ownership, nhưng nó không biến mọi thao tác với thư viện native thành single-thread-safe tự động.

### 5.3. Sai lầm: trả segment từ Arena đã đóng

```java
static MemorySegment wrong() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(64);
    }
}
```

Method trả một segment có lifetime gắn với arena. Khi method return, `try-with-resources` đóng arena; caller nhận một view không còn hợp lệ.

Một thiết kế khác:

```java
static MemorySegment allocateBuffer(Arena arena) {
    return arena.allocate(64);
}
```

Caller quyết định lifetime và truyền arena với ownership contract rõ. Nếu muốn hàm sở hữu memory và trả dữ liệu, có thể copy sang Java heap hoặc trả một object `AutoCloseable` bao cả arena lẫn segment.

### 5.4. Từ confined sang shared không phải phép sửa mọi lỗi thread

Nếu worker thread đọc segment thuộc confined arena do thread khác tạo, Java có thể ném exception về sai thread. Chuyển sang shared arena cho phép nhiều thread truy cập, nhưng **không tự tạo synchronization**.

Hai thread ghi cùng một struct hoặc một thread đóng arena trong lúc thread kia đang gọi native là vấn đề concurrency khác. Cần:

- Ghi rõ owner, readers, writers.
- Điều phối shutdown/close.
- Chỉ định lock, queue hoặc single-thread executor khi cần.
- Đảm bảo native library thread-safe theo tài liệu của nó.
- Test khi cancellation, timeout và parallel calls diễn ra đồng thời.

## 6. Downcall: gọi hàm C từ Java không cần JNI glue cho trường hợp phù hợp

### 6.1. Hàm native làm ví dụ

Giả sử có thư viện C riêng cung cấp:

```c
#include <stdint.h>

int32_t sum_ints(int32_t a, int32_t b) {
    return a + b;
}
```

Hàm được export theo C ABI và đã được build thành shared library phù hợp với hệ điều hành/kiến trúc. Với C++ cần đảm bảo export C ABI, ví dụ dùng `extern "C"`, để tránh name mangling theo compiler C++ nếu mục tiêu là gọi symbol `sum_ints`.

### 6.2. Java FFM final (JDK 22+)

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmMath {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of("/opt/example/libmathops.so");

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                SymbolLookup.libraryLookup(library, arena);

            MemorySegment function = lookup.find("sum_ints")
                .orElseThrow(() ->
                    new IllegalStateException("Missing sum_ints")
                );

            Linker linker = Linker.nativeLinker();

            FunctionDescriptor descriptor = FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // Return: int32_t
                ValueLayout.JAVA_INT, // Param 1
                ValueLayout.JAVA_INT  // Param 2
            );

            MethodHandle handle =
                linker.downcallHandle(function, descriptor);

            int result = (int) handle.invokeExact(7, 5);
            System.out.println(result); // 12
        }
    }
}
```

Đường dẫn `/opt/example/libmathops.so` chỉ là ví dụ Linux; trên Windows/macOS cần shared library filename, symbol export và binary tương ứng. Để chạy lệnh gọi native, phải đáp ứng native-access policy của JDK đang dùng.

Ví dụ dùng kiểu cố định 32 bit; mapping ABI vẫn phải được xác minh theo platform của native library. Hàm C này không giữ pointer sau khi trả kết quả, nên lifecycle tương đối đơn giản.

### 6.3. Vì sao cần FunctionDescriptor?

FFM không đọc C header rồi tự hiểu mọi signature trong shared library. `FunctionDescriptor` mô tả:

- Kiểu trả về.
- Thứ tự và layout tham số.
- Quy tắc ABI cần thiết cho downcall.

Nếu descriptor sai, code có thể compile nhưng native call truyền giá trị không đúng, đọc sai return register/stack hoặc gây crash. Không xem `FunctionDescriptor` chỉ là khai báo kiểu mang tính trang trí.

### 6.4. MethodHandle phải được gọi đúng kiểu

`invokeExact` yêu cầu method type của lời gọi phù hợp chính xác với handle. Một số khác biệt Java primitive hoặc carrier type có thể gây `WrongMethodTypeException` nếu sử dụng sai kiểu.

Cách an toàn là tạo wrapper Java typed method có test riêng, giấu `MethodHandle` khỏi business layer và chuyển đổi kiểu ở một nơi được kiểm soát.

Không nên phân tán `invokeExact` và các layout constant trên hàng chục class nghiệp vụ.

## 7. SymbolLookup và đóng gói native libraries

### 7.1. Tìm symbol đúng thư viện

Một native library có thể được tìm qua:

- Path tới shared library do ứng dụng quản lý.
- Lookup cho library theo tên theo quy tắc OS.
- Default lookup của native linker cho những symbol phù hợp.

Các lựa chọn không giống nhau về nguồn thư viện, khả năng portability và security. Nếu dùng path tương đối, working directory của app/container có thể làm kết quả thay đổi.

Tổ chức production nên có quy tắc:

- Thư viện nằm ở vị trí có thể dự đoán trong image/package.
- Path rõ ràng, không tìm DLL/SO trong thư mục không tin cậy.
- Checksum/version/signature của binary được quản lý.
- Không phụ thuộc vào PATH/LD_LIBRARY_PATH/DYLD_LIBRARY_PATH ngoài kiểm soát.
- Có release manifest gắn bản Java wrapper với native binary.
- Kiểm tra native dependency động như libc, OpenSSL hoặc thư viện vendor.

### 7.2. Symbol name không phải lúc nào giống function name trong source

Trên C++, name mangling có thể đổi exported symbol. Trên Windows, export table và calling convention có thể ảnh hưởng tên; trên một số OS có versioned symbols. Việc cùng một hàm tồn tại trong header không chứng minh symbol có mặt trong shared library.

Khi `lookup.find("sum_ints")` trả về empty, cần kiểm tra:

- File native thực tế được load.
- Exported symbol table.
- Compiler/linker flags.
- Architecture phù hợp JVM.
- Dependencies của shared library.
- C vs C++ symbol mangling.
- Runtime library version.

Công cụ `nm`, `readelf`, `objdump`, `otool` hoặc `dumpbin` có thể hỗ trợ tùy OS/toolchain; chúng không phải Java APIs và output có thể khác theo platform.

### 7.3. Lifetime của symbol lookup và library

Nếu lookup hoặc library được quản lý bởi Arena có thể đóng, cần tránh sử dụng function handle sau khi resource liên quan đã hết lifetime. Một wrapper nên giữ arena/library ownership cùng với các method handles và đóng khi không còn call/callback đang sử dụng.

Không tạo function handle trong một `try (Arena arena = ...)` ngắn rồi lưu nó vào static field để gọi tùy ý về sau mà chưa xác minh lifetime contract.

## 8. C ABI và native data layout: rủi ro lớn nhất khi di chuyển

### 8.1. Java primitive không đồng nghĩa mọi C primitive

Java có kích thước primitive cố định như `int` 32 bit và `long` 64 bit. Trong C, một số type thay đổi theo ABI:

- `long` có thể 32 bit trên Windows 64-bit, nhưng thường 64 bit trên Linux 64-bit.
- `size_t` phụ thuộc pointer width.
- `char` signed/unsigned tùy môi trường.
- `wchar_t` và Unicode representation khác nhau theo OS/compiler.
- `bool`, enum, bitfield và packed struct có quy tắc riêng.

Nếu wrapper JNI cũ đã tự xử lý conversion, chuyển FFM phải chuyển **cả logic conversion**, không chỉ thay native entrypoint.

### 8.2. Kiểu cố định giúp giảm rủi ro

Khi sở hữu C API, ưu tiên các kiểu minh bạch như:

```c
#include <stdint.h>

typedef struct {
    int32_t id;
    int64_t timestamp_ms;
} event_record;
```

Dù kiểu số nguyên đã có width rõ, struct vẫn chịu alignment, padding và byte order theo ABI. Nếu struct layout được truyền qua một thư viện native, phải mô tả đúng offset/size theo platform target.

### 8.3. Padding và alignment của struct

Ví dụ:

```c
typedef struct {
    uint8_t tag;
    int32_t value;
} packet_header;
```

Không nên giả định `value` bắt đầu ở byte offset 1. Compiler C có thể chèn padding để đáp ứng alignment. FFM `MemoryLayout.structLayout(...)` phải biểu diễn layout native thực tế, có padding khi cần.

Các cách kiểm chứng:

1. Trong native test helper, in `sizeof(packet_header)`.
2. In `offsetof(packet_header, tag)` và `offsetof(packet_header, value)`.
3. So sánh với `MemoryLayout.byteSize()` và offsets từ Java.
4. Test trên từng OS, architecture, compiler/ABI cần hỗ trợ.

Đừng copy layout Linux x86-64 sang Windows ARM64 chỉ vì field names giống nhau.

### 8.4. Canonical C layouts

FFM `Linker` cung cấp thông tin về canonical layouts phù hợp ABI cho những C types nhất định; đây là hướng đáng cân nhắc cho `size_t`, `long` và các kiểu native phụ thuộc platform.

Không hardcode mọi C `long` thành `ValueLayout.JAVA_LONG` mà không xem ABI. Với một hàm nhận pointer, `ValueLayout.ADDRESS` mô tả address carrier phù hợp, nhưng cần bảo đảm pointer hợp lệ và lifetime.

### 8.5. Variadic functions và errno

Các hàm C variadic như `printf(const char*, ...)` có quy tắc ABI khác fixed-arity. FFM có cơ chế mô tả variadic arguments theo phiên bản API, nhưng không nên tự tạo descriptor như các hàm thường.

Nếu native API báo lỗi qua `errno` hoặc platform-specific thread-local last-error, chỉ nhìn return value có thể chưa đủ. FFM hỗ trợ những cơ chế capture call state tùy API/JDK; wrapper cần đọc ngay và chuyển thành exception/result có ý nghĩa, tránh làm `errno` bị ghi đè bởi native call khác.

Đối với migration, bắt đầu bằng các hàm C đơn giản, non-variadic và có contract ownership rõ, rồi xử lý các trường hợp ABI nâng cao khi có test riêng.

## 9. Pointer, ownership và bộ nhớ trả về từ C

### 9.1. Không phải pointer nào cũng được free

Các hàm C có thể trả:

- Pointer tới static/global memory: **không tự free**.
- Pointer tới object do caller sở hữu: chỉ còn hợp lệ khi owner sống.
- Pointer tới vùng nhớ cần gọi `free`.
- Pointer tới vùng nhớ cần **custom release API** (không dùng libc `free`).
- Pointer tới buffer tạm chỉ hợp lệ trước lời gọi tiếp theo.

Nếu dùng sai release function, JVM có thể crash hoặc heap của native allocator bị hỏng.

Ví dụ API:

```c
native_result* result_create(void);
void result_destroy(native_result* result);
```

Ở Java, wrapper phải mô hình hóa `result_destroy` như một phần contract. Đừng dùng `Arena.close()` để giải phóng trực tiếp memory do native library cấp phát nếu API không trao ownership đó cho Arena.

### 9.2. Pointer size và bounds

Một pointer nhận từ native có thể chỉ có địa chỉ và **không kèm kích thước vùng dữ liệu**. Truy cập pointer theo một byte-size đoán mò là rủi ro cao.

Wrapper nên có length/element-count từ native API, kiểm tra overflow khi tính `count * elementSize` và chỉ tạo view trong phạm vi được cam kết. Những API native có length parameter thường dễ migrate an toàn hơn API chỉ trả naked pointer.

### 9.3. Null pointer là một trường hợp bình thường cần xử lý

Hàm C có thể trả `NULL` khi lỗi hoặc khi không có kết quả. Java FFM có representation cho null address, nhưng wrapper phải kiểm tra nó trước khi dereference hay reinterpret memory view.

Không biến `NULL` thành Java object hợp lệ tùy ý; thiết kế kết quả như `Optional`, exception hoặc error code theo hợp đồng thực sự.

### 9.4. UTF-8 và chuỗi C

Một C string thông thường là chuỗi byte kết thúc bằng null byte, không phải một Java `String` hay UTF-16 buffer. Khi truyền string cần thống nhất:

- Encoding, thường là UTF-8 nếu native API quy định vậy.
- Null terminator.
- Embedded null bytes có hợp lệ không.
- Native code có sao chép dữ liệu hay giữ pointer?
- Ai chịu trách nhiệm giải phóng pointer?
- Có trường hợp dữ liệu không hợp lệ/malformed encoding không?

Đừng suy từ tên function rằng nó luôn nhận UTF-8. Trên Windows có API bản ANSI và bản wide-char; cần chọn đúng binding theo header/ABI.

## 10. Upcall: native code gọi ngược vào Java

### 10.1. Callback là trường hợp phức tạp hơn downcall

Một native library có thể nhận callback function pointer rồi gọi nó sau này. FFM có cơ chế **upcall stub**, thường được tạo bằng `Linker.upcallStub(...)` từ Java `MethodHandle` và `FunctionDescriptor`.

Mô hình:

```text
Java callback method
       |
       v
MethodHandle + FunctionDescriptor
       |
       v
Linker.upcallStub(..., Arena)
       |
       v
Native function pointer
       |
       v
C library gọi callback trong hoặc sau native operation
```

Khi làm migration JNI/JNA callback sang FFM, cần kiểm tra:

- Native library gọi callback đồng bộ hay bất đồng bộ.
- Callback có thể đến từ native thread không được app tạo trực tiếp.
- Callback có thể bị gọi sau khi Java method đăng ký đã return không.
- Lifetime của upcall stub/Arena dài đủ không.
- Native code có giữ function pointer ở global state không.
- Callback Java ném exception thì xử lý theo contract nào.
- Có race giữa native unregister và Arena close không.

### 10.2. Lifetime của callback là hợp đồng bắt buộc

Một sai lầm là tạo callback stub trong confined Arena của một method đăng ký rồi đóng Arena ngay sau khi method return, trong khi C library lưu callback pointer để sử dụng sau.

Phải giữ arena còn sống cho đến khi native library xác nhận không gọi callback nữa. Một mô hình an toàn:

1. Tạo callback handle và stub.
2. Đăng ký với native library.
3. Giữ strong references/ownership cần thiết ở wrapper.
4. Trong shutdown, ngừng nhận task mới.
5. Unregister callback qua API native nếu có.
6. Chờ in-flight callback kết thúc.
7. Chỉ sau đó đóng arena và unload resources theo contract.

Không tự suy luận rằng garbage collector giữ callback hoặc thư viện native sẽ tự hủy mọi function pointer.

### 10.3. Callback và Java agent khác nhau

FFM upcall hỗ trợ native code gọi một Java method theo C ABI. Nó **không đồng nghĩa** JVMTI callbacks (như ClassFileLoadHook), Java Instrumentation API hay Attach API. Một native JVMTI agent vẫn cần tuân thủ JVMTI/JNI lifecycle, agent entrypoints và quyền attach/load tương ứng.

Có thể chuyển một phần data conversion/native library call sang FFM, trong khi phần agent/instrumentation vẫn giữ JNI/JVMTI. Đây thường là thiết kế hợp lý hơn việc ép FFM thay toàn bộ agent framework.

## 11. So sánh FFM với JNI, JNA, Unsafe và DirectByteBuffer

| Tiêu chí | JNI | JNA | FFM final | `sun.misc.Unsafe` / direct buffers |
|---|---|---|---|---|
| Cần native glue do dự án viết? | Thường có | Thường không cho lời gọi C chuẩn | Thường không cho downcall tương thích | Tùy trường hợp |
| Gọi symbol C trực tiếp | Có qua JNI bridge | Có qua mapping | Có qua linker/symbol lookup | Không phải mục tiêu chính |
| Mô tả C struct/layout | Trong C/JNI wrapper | Mapping của JNA | MemoryLayout/ValueLayout | Thường thủ công |
| Quản lý lifetime ngoài heap | C/JNI và Java cùng chịu trách nhiệm | Pointer/Memory API của JNA | Arena/MemorySegment | Dễ phụ thuộc manual cleanup |
| Yêu cầu native binary | Có nếu dùng C bridge | Thư viện đích + JNA runtime | Thư viện đích | Tùy cách dùng |
| Phụ thuộc phiên bản JDK | JNI có compatibility contract riêng | JNA version phải hỗ trợ JDK | Final API từ JDK 22 | Internal API có rủi ro cao |
| JVMTI/agent instrumentation | Phù hợp với native agents | Không thay thế JVMTI | Không thay thế JVMTI | Không thay thế |
| Giới hạn an toàn Java-side | Phụ thuộc wrapper | Phụ thuộc JNA API | Bounds/lifetime/thread checks rõ hơn | Có thể dùng vùng nhớ không an toàn |

Không có giải pháp duy nhất tốt nhất. Quyết định dựa trên native API complexity, minimum JDK, performance, security, legacy ABI, deployment và năng lực bảo trì.

### 11.1. Khi nên giữ JNI

Có thể giữ JNI nếu:

- Bridge hiện tại ổn định, có test và không gây vấn đề compatibility.
- App phải hỗ trợ JDK trước 22.
- Native code cần tương tác sâu với JVM objects, JNI references hoặc JVMTI.
- C/C++ layer thực hiện logic native phức tạp mà FFM không làm giảm đáng kể chi phí.
- Library vendor chỉ cung cấp một JNI binding chính thức.
- Chuyển bridge có rủi ro cao hơn lợi ích dự kiến.

Nâng JDK không bắt buộc phải xóa JNI. Nhưng cần đảm bảo thư viện native và wrapper tương thích JDK/OS mới, loại bỏ API nội bộ không được hỗ trợ, test thread/GC/pinning và deployment.

### 11.2. Khi cân nhắc FFM

FFM phù hợp khi:

- Native API có C ABI được định nghĩa rõ.
- Có nhiều hàm C đơn giản và JNI glue code đang tốn bảo trì.
- Cần memory access có bounds/lifetime rõ ràng.
- Ứng dụng đã chọn minimum JDK hỗ trợ FFM final.
- Có thể pin platform-specific binaries và tạo integration tests.
- Đội ngũ chấp nhận quản lý ABI descriptors và native-access policy.

### 11.3. Khi không nên dùng FFM để “sửa” Unsafe tùy tiện

`sun.misc.Unsafe` có các chức năng rộng ngoài direct memory access: field offsets, atomics, fence, object manipulation và một số internal operations. Không phải mọi cách dùng đều ánh xạ một-một sang `MemorySegment`.

Các thao tác memory access có thể chuyển sang FFM; nhưng concurrency/atomics trên Java heap có thể nên dùng `VarHandle` hoặc API chuẩn phù hợp. Với phần phụ thuộc object layout nội bộ của JVM, cần thiết kế lại thay vì tìm một API tương đương không được hỗ trợ.

FFM không cho phép tự do đọc/ghi mọi object address trong Java heap theo cách một codebase `Unsafe` từng làm.

### 11.4. DirectByteBuffer vẫn có vai trò

`ByteBuffer.allocateDirect()` vẫn hữu ích cho NIO, channel và native-oriented buffer APIs. Migrate sang FFM không phải yêu cầu bắt buộc.

Khi chuyển, đánh giá:

- API downstream có nhận `MemorySegment` hay chỉ nhận `ByteBuffer`?
- Có cần view adapter không?
- Memory ownership/cleanup có thay đổi không?
- Byte order, alignment và bounds có giữ đúng không?
- Có copy dữ liệu không mong muốn không?
- Có nguy cơ double-free hay use-after-close không?

Không ép mọi direct buffer thành segment khi thư viện NIO hiện tại hoạt động ổn định và không có yêu cầu rõ.

## 12. JNI/JNA to FFM migration: không thể thay import đơn giản

### 12.1. JNI đã che nhiều quy tắc ABI

Một JNI wrapper cũ có thể:

- Chuyển Java `String` sang encoding mà C API cần.
- Tạo native struct, padding và alignment.
- Copy Java array sang native buffer.
- Chuyển error code/errno thành exception.
- Quản lý reference của Java objects.
- Bắt callback qua JNI global reference.
- Lock thread hoặc serialise calls do native library không thread-safe.
- Free native buffers trong `finally`.

Nếu thay `native int call(...)` bằng `MethodHandle.invokeExact(...)` mà bỏ những chức năng này, code mới có thể sai dù native function trả giá trị đúng trong một test đơn giản.

### 12.2. Lập bản đồ wrapper contract

Với mỗi JNI/JNA method, cần ghi:

| Thuộc tính | Cần xác định |
|---|---|
| Symbol/C signature | Tên export, argument/return ABI |
| Java-facing contract | Nullability, exception, timeout, thread safety |
| Encoding | UTF-8, UTF-16, ASCII, OS-specific |
| Memory ownership | Caller, callee, shared hoặc global |
| Buffer size | Cấp bởi ai; size/count semantics |
| Struct layout | Size/offset/alignment/endianness |
| Callback | Đồng bộ/bất đồng bộ; unregister và lifetime |
| Error reporting | Return code, `errno`, last-error, error string |
| Library loading | Path, native dependencies, classloader |
| Platform variants | Linux/Windows/macOS, x86-64/ARM64 |
| Security | Input validation, unsafe pointer, native-access permission |

Không chỉ kiểm kê hàm được gọi; cần kiểm kê **ngầm định đã được wrapper cũ thực thi**.

### 12.3. Di chuyển theo adapter, không thay đồng loạt

Một interface Java chung giúp chuyển từng phần:

```java
public interface NativeChecksum {
    int checksum(byte[] payload);
}
```

Hai implementation có thể tồn tại trong giai đoạn migration:

```text
NativeChecksum
  ├── JniChecksumAdapter
  └── FfmChecksumAdapter
```

Bằng cách này, domain code không biết backend; integration test có thể chạy cùng bộ fixtures với hai implementation và so sánh output, exception mapping và tài nguyên.

Chọn backend theo artifact/JDK/platform được hỗ trợ, tránh tự động thử tải native libraries không rõ nguồn hoặc fallback âm thầm khi lỗi ABI.

## 13. jextract: sinh binding từ C header

### 13.1. Vì sao cần generator?

Tự viết hàng trăm `FunctionDescriptor` và `MemoryLayout` dễ lỗi. **jextract** là một công cụ độc lập thuộc hệ sinh thái OpenJDK Project Panama, có thể tạo Java bindings từ C headers trong phạm vi tính năng của tool/version.

Điểm cần nhớ:

- jextract **không phải công cụ chuẩn luôn nằm trong mọi JDK distribution**.
- Version jextract có thể gắn với một generation/version của FFM.
- C header parsing phụ thuộc toolchain phù hợp, thường liên quan Clang/libclang.
- Các macro phức tạp, C++ constructs, conditional compilation và platform headers có thể cần xử lý riêng.
- Code được sinh là một phần API/runtime compatibility của ứng dụng.

### 13.2. Pipeline được khuyến nghị

```text
Pinned C header + platform defines + toolchain
                  |
                  v
         Pinned jextract version
                  |
                  v
     Generated Java bindings (FFM API target)
                  |
                  v
       Build application/library on JDK target
                  |
                  v
      Integration tests with real native binary
```

Các input quan trọng:

- Header version và checksum.
- `-I` include paths, defines, target platform/ABI.
- jextract version, Java runtime yêu cầu để chạy.
- Generated package/class names.
- Output directory/source set.
- Runtime lookup/loading behavior.
- CI environment và compiler/Clang version.

Nếu generator lấy headers từ một SDK mới nhưng runtime native binary là SDK cũ, generated bindings có thể tham chiếu symbol/struct layout chưa có trên production.

### 13.3. Generated source không phải hợp đồng vĩnh viễn

Nâng jextract hoặc thay target JDK có thể tạo code khác cấu trúc và tên method. Tránh để business code phụ thuộc trực tiếp vào hàng trăm generated classes; tạo một facade/adaptor ổn định.

Khi cần nâng tool:

1. Pin input headers.
2. Generate ở môi trường sạch.
3. Xem diff generated sources.
4. Compile trên JDK target.
5. Chạy ABI/layout tests với native binary.
6. Chạy contract tests của adapter.
7. Ghi version tool và generated output trong release artifacts.

Không sửa generated code bằng tay để che vấn đề: thay đổi sẽ mất khi regenerate hoặc gây khác biệt khó tái lập.

## 14. Native-access policy và các tùy chọn JVM

### 14.1. Tại sao có restricted methods?

Một số thao tác FFM, đặc biệt việc tạo native linker/downcall/upcall hoặc các operation liên quan mã native, có thể vượt hàng rào an toàn của Java và gây crash nếu dùng sai. JDK kiểm soát quyền truy cập này qua cơ chế **native access**.

Với ứng dụng classpath/unnamed module, một tùy chọn thường gặp:

```bash
java --enable-native-access=ALL-UNNAMED \
     -cp app.jar com.example.Main
```

Với named module, thay bằng module thực sự được cấp quyền:

```bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

Các tên module chỉ minh họa. Tùy JDK release, việc gọi restricted method mà không có native access có thể phát cảnh báo hoặc bị từ chối; các release tiếp theo có thể thắt chặt chính sách. Phải đọc hành vi của JDK mục tiêu và xử lý warnings như tín hiệu compatibility, không coi mọi version có cùng mức thực thi.

### 14.2. Native access không phải phép cấp an toàn chung

Cấp `ALL-UNNAMED` nghĩa là phạm vi native access rộng cho các unnamed modules trong classpath. Với ứng dụng module hóa, ưu tiên chỉ cấp cho module thực sự cần.

Dù đã cấp quyền, ứng dụng vẫn chịu trách nhiệm:

- Tải đúng native library.
- Không gọi sai ABI.
- Không giữ dangling pointer.
- Không vượt lifetime của Arena.
- Không truyền dữ liệu không tin cậy vào native code không được thiết kế an toàn.
- Không làm rò rỉ file descriptor, handle hoặc memory.

Native-access flag không kiểm tra logic trong C library và không biến một shared library không đáng tin cậy thành thành phần an toàn.

### 14.3. Module path, reflection và native libraries là ba cơ chế khác nhau

Đừng nhầm:

- `--enable-native-access`: kiểm soát native access theo policy của FFM/JNI trong JDK liên quan.
- `--add-opens`: mở package cho deep reflection khi có cơ sở.
- `--add-exports`: mở quyền truy cập một package module ở mức compile/runtime theo trường hợp.
- `java.library.path` hoặc library lookup: liên quan vị trí native library.
- `--enable-preview`: cần cho API preview ở JDK hỗ trợ tương ứng.

Không có một flag duy nhất có thể sửa mọi lỗi FFM/JNI/JPMS.

## 15. Agent và native instrumentation: phân biệt đúng phạm vi

### 15.1. Java agent sử dụng Instrumentation API

Một Java agent thường có `premain` hoặc `agentmain` và dùng `java.lang.instrument.Instrumentation` để transform class. Agent có thể dựa vào bytecode libraries như ASM/Byte Buddy và có ràng buộc theo class-file version, module access và attach policy.

FFM không tự thay cách Java agent được nạp, không thay `ClassFileTransformer` và không giải quyết lỗi transformer chưa hỗ trợ bytecode của JDK mới.

### 15.2. JVMTI native agent sử dụng interface riêng

Native agent JVMTI dùng entrypoint như `Agent_OnLoad` và JVMTI callbacks để theo dõi event JVM. Nó thường tương tác với JNI/JVMTI data structures, pointer và memory management theo đặc tả agent.

Có thể dùng FFM trong một Java-facing helper để gọi C library, nhưng không thể giả định FFM thay thế toàn bộ khả năng attach, instrumentation, JVMTI events hoặc JNI object handles.

### 15.3. Khi nâng JDK, cần phân loại vấn đề

| Tình huống | Khả năng liên quan |
|---|---|
| Agent không nạp được sau nâng JDK | Manifest/attach policy, agent runtime, class-file target |
| Agent transform lỗi `Unsupported class file major version` | Bytecode library/ASM/Byte Buddy |
| JNI library báo `UnsatisfiedLinkError` | Library path, architecture, exported symbol, native dependencies |
| FFM downcall không được phép | Native-access policy/flags |
| Native call crash JVM | ABI/layout/lifetime hoặc bug native |
| Callback không còn hợp lệ | Arena/upcall stub lifetime, native unregister |
| Framework dùng reflection bị chặn | JPMS opens, framework compatibility |
| Native profiling khác kết quả | JVMTI version, OS tooling, agent implementation |

Lỗi native và lỗi agent có thể xuất hiện cùng lúc, nhưng phải tách loại để tránh chuyển sang FFM khi vấn đề thực sự là bytecode instrumentation.

## 16. JDK version, ABI và hệ điều hành: ba chiều tương thích

Một binding native không chỉ có “Java version”.

### 16.1. Minimum JDK

- JDK 17: không có FFM final.
- JDK 21: preview FFM với source/runtime flags phù hợp.
- JDK 22+: final FFM API của JEP 454, song vẫn phải theo dõi native-access policy/release changes.

Nếu phát hành thư viện hỗ trợ Java 17, không thể công bố một method public dùng `java.lang.foreign.MemorySegment` final JDK22 rồi tuyên bố consumer Java17 có thể compile/chạy bình thường.

### 16.2. OS và kiến trúc

Cần có thư viện native tương ứng với:

- Linux x86-64 / ARM64.
- Windows x86-64 / ARM64 nếu sản phẩm hỗ trợ.
- macOS x86-64 / Apple Silicon.
- libc/toolchain khác nhau trên Linux khi liên quan.
- CPU ABI, calling convention và endianness nếu có platform đặc biệt.

Một ứng dụng Java “write once, run anywhere” không làm native shared library trở nên đa nền tảng. Mỗi OS/architecture cần đúng binary artifact và test.

### 16.3. 32-bit, 64-bit và host endianness

Pointer width, `size_t` và alignment có thể khác. Java memory layout phải khớp host ABI, không khớp một giả định từ môi trường development.

Byte order cũng quan trọng: dữ liệu trong native struct có thể dùng host-endian, còn file/network protocol thường dùng byte order được đặc tả riêng. Không dùng layout native làm format persistent xuyên nền tảng nếu không có chuẩn hóa.

### 16.4. Native library ABI version

Một tên symbol giống nhau không bảo đảm struct/function contract còn tương thích. Vendor có thể thay layout, thêm field, đổi enum values hoặc ownership semantics giữa release. Tổ chức cần quản lý version của C headers và binary library cùng nhau, giống như quản lý Java API và implementation.

## 17. Test vòng đời và concurrency ở boundary FFM

### 17.1. Những tình huống cần test riêng

- Đọc/ghi đúng ranh giới 0 byte, 1 byte và kích thước tối đa.
- Truy cập segment sau khi Arena đã đóng.
- Truy cập confined segment từ thread khác.
- Gọi native function khi library handle/lifetime không còn hợp lệ.
- Native function trả null pointer hoặc error code.
- C cấp phát buffer nhưng Java quên gọi custom release API.
- Java cấp phát buffer rồi native giữ pointer quá lâu.
- Upcall đến sau khi Java unregister hoặc đóng arena.
- Concurrent close trong lúc downcall đang chạy.
- Native library không thread-safe nhưng nhiều virtual/platform threads gọi cùng lúc.
- Cancellation/timeout của Java task trong khi native call vẫn đang chạy.

### 17.2. Timeout Java không nhất thiết hủy native call

Một Java task bị timeout hoặc interrupt không có nghĩa một hàm C blocking đang chạy sẽ tự được hủy. Nếu thư viện native cung cấp API cancellation, wrapper phải tích hợp nó và bảo đảm thread/resource cleanup.

Nếu không có cancellation contract, có thể cần execution isolation, giới hạn concurrency, watchdog hoặc chạy native operation trong process riêng. Không hứa hẹn rằng virtual threads biến native calls blocking thành operations an toàn có thể hủy.

### 17.3. Exception của Java không thể tùy tiện xuyên C ABI

C function không có khái niệm Java checked exception. Wrapper phải chuyển:

- Return/error code.
- `errno` hoặc native last-error.
- Native-owned error string.
- Null result.
- Callback failure.
- Fatal signal hoặc process crash.

Một native crash không trở thành `IOException` có thể catch bình thường. Nếu C library có nguy cơ crash, tách process là một lựa chọn kiến trúc quan trọng.

## 18. Hiệu năng: đừng thay JNI bằng FFM chỉ dựa trên microbenchmark

### 18.1. Chi phí native boundary chỉ là một phần

Hiệu năng end-to-end phụ thuộc:

- Số lượng và kích thước native calls.
- Chi phí chuyển đổi String/array/struct.
- Buffer allocation/copying.
- Synchronization, lock contention.
- Thread confinement/shared arena.
- Callback frequency.
- Native library performance.
- GC/off-heap memory và resource cleanup.
- JIT warmup, CPU/OS/toolchain, virtualization.

Một phép gọi C cộng hai số có thể đo chi phí boundary, nhưng không đại diện cho một pipeline image processing hay database native engine.

### 18.2. Benchmark cần đúng workload

Các trường hợp benchmark có ích:

1. Function call đơn giản với primitive arguments.
2. Call nhận pointer + array/buffer nhỏ.
3. Call với buffer lớn.
4. Batch nhiều native operations trong một call.
5. Callback native → Java.
6. Multi-thread throughput và latency.
7. Allocation/cleanup theo từng request.
8. Performance trên platform/architecture được hỗ trợ.

Có thể dùng JMH để kiểm soát warmup/fork/measurement và so sánh hai backend. Không chạy benchmark với debug flags, profile hoặc khác JVM options giữa hai phương án rồi coi kết quả là bằng chứng trực tiếp.

### 18.3. Safety và maintainability cũng là tiêu chí

Ngay cả khi FFM không nhanh hơn một JNI wrapper rất tối ưu, FFM có thể cải thiện tính rõ ràng của memory lifecycle và giảm lượng C glue code. Ngược lại, nếu FFM binding quá phức tạp hoặc native API không phù hợp, JNI hiện tại có thể dễ bảo trì hơn.

Quyết định migration nên cân bằng **tính đúng, an toàn, portability, vận hành và hiệu năng**, không chỉ throughput.

## 19. Build và packaging cho native integration

### 19.1. Java module và native artifact phải được version hóa cùng nhau

Một hệ thống có thể có:

```text
native-bridge/
  ├── Java API module
  ├── FFM implementation module
  ├── generated bindings
  ├── C headers
  ├── native libraries per platform
  ├── integration tests
  └── release manifest
```

Native libraries có thể được build bởi CMake/Meson/Make hoặc vendor cung cấp. Java build dùng Maven/Gradle nhưng không tự đảm bảo C toolchain/ABI đúng.

### 19.2. Maven/Gradle phải pin cả tool và runtime

Nếu dùng jextract hoặc native toolchain:

- Pin version generator và JDK chạy generator.
- Pin C compiler/toolchain và native SDK version.
- Khai báo input headers, defines và output source.
- Tránh tải native binaries không kiểm soát trong task build.
- Ghi metadata OS/architecture.
- Nối generated sources vào đúng source set.
- Tạo package/launcher chọn native binary tương ứng.
- Test trong clean checkout và container/VM đích.

Không đưa native SDK của build workstation vào production image nếu chỉ cần shared runtime library. Ngược lại, không tạo artifact chỉ chứa Java bindings mà quên native binary phải được load khi chạy.

### 19.3. Cơ chế load library an toàn

Hạn chế search path không rõ ràng; một DLL/SO giả có thể bị load nếu path ưu tiên sai. Sử dụng artifact integrity checks và repository/packaging policy của tổ chức.

Với Java classpath/module path, cần xác định native library được copy ở đâu trong JAR/distribution. Một số framework extract native library vào thư mục tạm; cần kiểm tra quyền, cleanup, concurrent startup và khả năng chạy trên container read-only file system.

### 19.4. GraalVM Native Image

Nếu ứng dụng còn xây native image bằng GraalVM, phải xem compatibility của FFM API, dynamic library lookup, reflection/native access và platform-specific support theo đúng phiên bản GraalVM. Không giả định một binding chạy trên HotSpot JDK 22 sẽ chạy y nguyên trong native image.

FFM không giải quyết tự động mọi vấn đề ahead-of-time compilation, linker, runtime symbol availability và static/shared linking.

## 20. Migration từ Unsafe hoặc JNI khi có nhiều JDK được hỗ trợ

### 20.1. API Java-facing trung lập với FFM

Một thư viện cần hỗ trợ Java 17 và Java 22+ có thể công bố interface không chứa kiểu FFM:

```java
public interface NativeDigest {
    byte[] digest(byte[] bytes);

    void close();
}
```

Trong implementation:

```text
app-api
  |
  +-- legacy-jni-backend  (Java 17-compatible)
  |
  +-- ffm-backend         (Java 22+)
```

Cách đóng gói có thể dùng module/artifact riêng theo target runtime. Với multi-release JAR, cần hiểu các quy tắc runtime và class loading thật; không nên dùng chỉ vì muốn tránh thêm artifact, nhất là khi public API type khác nhau.

### 20.2. Không compile source FFM final với --release 17

Một source có:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
```

không thể được coi là Java 17-compatible bằng cách đặt `--release 17`. API này không thuộc Java 17 platform API; compiler đúng phải từ chối.

Nếu muốn một release hỗ trợ cả Java 17 và 22+, giữ FFM implementation ở source set/module được compile cho Java 22+ và bảo đảm Java 17 không phải nạp class đó khi khởi động hoặc chạy.

### 20.3. Rolling deployment cần ổn định contract trên biên

Khi thay JNI bằng FFM, output của hàm native không được tùy tiện đổi format:

- Bytes/endianness.
- Struct fields và padding.
- Error code translation.
- String encoding.
- Resource ownership.
- Ordering/concurrency.
- Callback/lifecycle semantics.

Nếu hệ thống có lưu file hoặc gửi dữ liệu qua network, cần test compatibility với sản phẩm khác hoặc bản cũ trước khi canary. Native bridge migration có thể làm output thay đổi dù Java business code không đổi.

## 21. Những lỗi thường gặp và cách điều tra

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Kiểm tra trước |
|---|---|---|
| `package java.lang.foreign does not exist` | Compiler/target JDK quá cũ | JDK version, toolchain và `--release` |
| Preview FFM source không compile | Source dùng API của preview release khác | Xác minh JDK 21 vs 22+ APIs và flags |
| Restricted native access warning/error | Thiếu quyền native access | Named/unnamed module và chính sách JDK |
| `UnsatisfiedLinkError` | Thiếu native binary/dependency hoặc sai architecture | Library path, OS/CPU ABI, exported symbols |
| Lookup không tìm thấy symbol | Library/version khác, name mangling, export hidden | Export table và binary checksum |
| `WrongMethodTypeException` | `MethodHandle` call-site type không khớp | Carrier types và descriptor |
| Crash JVM khi downcall | ABI descriptor, pointer/lifetime hoặc bug native | Core dump/hs_err, C signature, layout |
| Truy cập segment thất bại sau close | Arena đã đóng | Ownership/lifetime và cleanup |
| Truy cập confined segment từ thread khác | Sai confinement | Thiết kế thread ownership/shared Arena |
| Dữ liệu struct sai trên Windows | C `long`/alignment/packing khác Linux | `sizeof`, `offsetof` và ABI |
| Buffer trả về chứa dữ liệu lỗi | Pointer invalid hoặc đã bị native free | Ownership contract và callback timing |
| Native memory tăng mãi | Không gọi release/native destroy | Resource lifecycle và leak metrics |
| Callback crash sau shutdown | Native code giữ upcall stub đã đóng | Unregister, in-flight callbacks, Arena |
| JNI hoạt động nhưng FFM khác kết quả | Wrapper cũ có conversion/validation | So sánh semantics và fixtures |
| Java agent lỗi sau nâng JDK | Instrumentation/bytecode API, không phải FFM | ASM/Byte Buddy/JVMTI version |
| Native image không load library | AOT/runtime support/packaging | GraalVM matrix và linker config |

Không suy ra “FFM có bug” chỉ vì một lỗi mới xuất hiện trong quá trình chuyển. Ghi lại OS, architecture, JDK vendor/build, native library checksum, C header version và minimal reproducer.

## 22. Quy trình điều tra native crash

Một native crash có thể làm toàn JVM thoát, nên phải điều tra khác với Java exception.

### Bước 1: Tái hiện trong môi trường cách ly

Dùng fixture nhỏ, không chạy trên production, đầu vào đáng tin cậy và thư viện native xác minh được nguồn gốc.

### Bước 2: Ghi thông tin đầy đủ

- JVM vendor/version/build.
- OS/kernel/architecture.
- Native library path, checksum, version.
- C compiler, flags và linked dependencies.
- Function symbol, descriptor và layouts.
- Thread/concurrency scenario.
- Native-access flags và module configuration.
- Crash log như `hs_err_pid*.log` khi JVM tạo.

### Bước 3: Kiểm tra ABI trước khi tối ưu

So sánh C header với FunctionDescriptor; kiểm tra argument width, alignment, struct offsets và calling convention. Nếu C++ API, xác minh extern C/export contract hoặc dùng wrapper C ABI có kiểm soát.

### Bước 4: Kiểm tra pointer và lifetime

Xác định buffer owner, size, thread access, arena close và native free. Một lỗi trỏ sai có thể chỉ crash khi chạy dưới tải hoặc trên kiến trúc khác.

### Bước 5: Dùng native debugging khi cần

Công cụ như gdb/lldb/WinDbg hoặc sanitizers trong build native có thể hỗ trợ chẩn đoán. Kiểm tra native address sanitizer/undefined behavior sanitizer tùy toolchain, lưu ý overhead và khả năng tương tác JVM.

### Bước 6: Viết regression test

Không chỉ sửa để hết crash một lần; tạo test boundary với input/offset/lifetime có thể tái hiện, chạy ở các platform hỗ trợ.

## 23. Kịch bản migration thực tế: từ JNI bridge sang FFM

Giả sử ứng dụng quản lý hồ sơ ảnh có:

- Java 17 production runtime.
- JNI bridge gọi thư viện C thực hiện resize/compression.
- C method nhận pointer + length và trả output pointer.
- Thư viện dùng custom `image_result_free`.
- Một callback thông báo tiến độ.
- Native binaries cho Linux x86-64 và Windows x86-64.
- Mục tiêu dài hạn là JDK 22+ và giảm JNI glue.

### Giai đoạn 1: Kiểm kê và baseline

Tạo matrix tất cả function signatures, struct layouts, ownership, callback lifecycle và error handling. Lưu native SDK/library version, headers và những fixture ảnh đại diện.

### Giai đoạn 2: Giữ public Java API

Tạo interface `ImageNativeEngine` với method nhận/trả `byte[]` hoặc DTO ổn định; giữ JNI implementation làm baseline. Không phơi `MemorySegment` vào public contract nếu còn consumer Java17.

### Giai đoạn 3: Viết FFM backend cho downcalls

Bắt đầu với hàm stateless, fixed-arity: lấy native version, đọc config hoặc thao tác resize đơn giản. Mô tả descriptor bằng C ABI, quản lý input/output buffer với arena/native release function.

### Giai đoạn 4: Chuyển ownership cẩn thận

Hàm native trả pointer cần `image_result_free`. Adapter FFM phải copy output khi cần, rồi gọi đúng release function trong `finally`. Không dùng Arena close thay custom free.

### Giai đoạn 5: Chuyển callback

Thiết kế upcall stub còn sống đến sau native unregister, có cơ chế chờ callbacks đang thực thi. Test shutdown, timeout, cancellation và nhiều job song song.

### Giai đoạn 6: So sánh behavior

Chạy cùng fixture ảnh qua JNI và FFM, so sánh output bytes/chất lượng theo tolerance đã định, error codes, exception mapping, memory usage, latency và throughput.

### Giai đoạn 7: Đóng gói và test platform

Tạo JAR/native package riêng per platform, chạy trên JDK mục tiêu, test cả container image/OS/CPU mà tổ chức hỗ trợ. Kiểm tra native-access permission và startup library resolution.

### Giai đoạn 8: Canary và rollback

Chọn một phần workload sử dụng FFM backend, theo dõi crash, heap/off-heap memory, native handle counts, processing errors và latency. Giữ JNI backend làm rollback trong thời gian chuyển tiếp nếu deployment cho phép.

Chỉ loại bỏ JNI khi toàn bộ các contract đã được kiểm chứng và minimum supported JDK không còn yêu cầu Java 17 backend.

## 24. Một ví dụ native memory wrapper có ownership rõ

Một wrapper Java cho native resource nên biểu diễn cả lifetime, thay vì chỉ trả naked segment:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

public final class NativeBuffer implements AutoCloseable {
    private final Arena arena;
    private final MemorySegment segment;

    public NativeBuffer(long bytes) {
        this.arena = Arena.ofConfined();
        try {
            this.segment = arena.allocate(bytes);
        } catch (RuntimeException | Error failure) {
            arena.close();
            throw failure;
        }
    }

    public MemorySegment segment() {
        return segment;
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

Sử dụng:

```java
try (NativeBuffer buffer = new NativeBuffer(256)) {
    MemorySegment segment = buffer.segment();
    // Gọi native API đồng bộ, không giữ pointer sau scope.
}
```

Ví dụ này minh họa ownership của bộ nhớ **do Arena cấp phát**. Nó không phù hợp để trực tiếp quản lý pointer native do library khác cấp phát, không xử lý callback bất đồng bộ và không tự thread-safe. Wrapper production có thể cần state kiểm soát close idempotency, ownership transfer và xử lý concurrent calls.

Điểm chính là thiết kế API làm rõ ai đóng tài nguyên, thay vì để business code gọi `Arena.close()` hoặc custom free một cách rải rác.

## 25. Chuẩn hóa chiến lược native backend trong tổ chức

Nếu nhiều service cùng dùng thư viện native, tổ chức nên tránh mỗi nhóm tự tạo FFM/JNI wrappers không nhất quán. Có thể công bố một SDK nội bộ với:

1. Java-facing facade không chứa ABI details khi cần hỗ trợ nhiều JDK.
2. Backend JNI/JNA/FFM được chọn theo minimum runtime và ma trận hỗ trợ.
3. Metadata native binaries theo OS/CPU và checksum.
4. Thư viện generated bindings được pin version.
5. Một nơi quản lý native-access flags và module descriptors.
6. Typed error mapping, lifetime và thread-safety contract.
7. Cross-platform integration tests.
8. Resource leak/crash metrics và runbook.
9. Release notes của ABI/binary compatibility.
10. Rollback/fallback strategy rõ ràng, không âm thầm che lỗi.

Không nhất thiết phải dùng FFM cho tất cả native integrations; SDK có thể quy định tiêu chí chọn lựa và cách đánh giá migration. Một API ổn định với backend thay đổi có kiểm soát thường có giá trị hơn việc đưa mọi `MemorySegment` và `MethodHandle` vào domain layer.

## 26. Hồ sơ kiểm chứng trước khi phát hành

Một lần thay JNI/JNA/Unsafe bằng FFM cần bàn giao những bằng chứng sau:

| Bằng chứng | Nội dung |
|---|---|
| Version matrix | JDK build/runtime, FFM generation, native library version |
| C ABI inventory | Function signatures, calling conventions, struct sizes/offsets |
| Memory ownership matrix | Caller/callee allocation, release function, lifetime, threads |
| Callback contract | Registration, unregister, in-flight calls, shutdown |
| Native binary manifest | OS/arch, checksum, compiler, linked dependencies |
| Generated binding record | jextract/tool version, headers, flags, output |
| Permissions | Native-access policy theo named/unnamed module |
| Integration report | Contract fixtures, correct outputs, errors, null pointers |
| Performance report | CPU, latency, throughput, off-heap memory và resource leak |
| Security review | Input trust, library provenance, native code audit/boundary |
| Deployment report | Library loading trong artifact/container, startup smoke |
| Rollback plan | Backend/binary/JDK compatibility và rollback trigger |

Nếu ứng dụng hỗ trợ nhiều JDK, thêm một cột cho mỗi runtime: JDK 17/JNI, JDK 21/preview (nếu cố ý), JDK 22+/FFM final. Không gom mọi môi trường thành một ô “Java compatible”.

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| “FFM đã final trong JDK 21” | JDK 21 là preview; final từ JDK 22 theo JEP 454 |
| “FFM final dùng được trên Java 17 chỉ bằng thêm dependency” | Không phải API chuẩn của Java 17; cần backend khác hoặc nâng minimum JDK |
| “FFM thay thế toàn bộ JNI/JVMTI agents” | Không thay thế JVM instrumentation, JVMTI callbacks và mọi JNI operations |
| “MemorySegment làm native code tuyệt đối an toàn” | Java-side bounds/lifetime checks không bảo vệ mọi thao tác C |
| “Arena đóng là đã free mọi pointer C” | Pointer native-owned có thể yêu cầu custom release API |
| “Shared Arena tự đồng bộ multi-thread” | Shared access không đồng nghĩa data-race free |
| “Java long luôn tương đương C long” | C long thay đổi theo ABI/OS |
| “C struct size bằng tổng field sizes” | Có padding/alignment |
| “jextract luôn có trong JDK” | Là tool riêng; phải pin version và tương thích API/headers |
| “Cứ tăng --enable-native-access là sửa mọi crash” | Flag không sửa sai ABI/pointer/library |
| “JNI bridge cũ phải bị xóa khi nâng JDK” | Giữ JNI có thể là lựa chọn ít rủi ro và được hỗ trợ |
| “Native callback còn hợp lệ sau khi method return” | Phụ thuộc stub/Arena và native unregister/lifetime |
| “Thư viện native Linux chạy trên Windows cùng bytecode Java” | Native binary phụ thuộc OS/architecture |
| “Timeout Future đồng nghĩa hủy native function” | Blocking native call có cancellation contract riêng |
| “FFM chạy trên HotSpot nghĩa là Native Image cũng hỗ trợ y nguyên” | Phải kiểm tra GraalVM AOT/runtime/toolchain cụ thể |

## 28. Checklist migration FFM

### Nền tảng và phiên bản

- [ ] Đã xác định minimum supported JDK và phân biệt FFM preview với final.
- [ ] Đã chốt JDK build, JDK runtime và class-file target.
- [ ] Đã xác minh `java.lang.foreign` chỉ xuất hiện ở module/artifact có runtime hỗ trợ.
- [ ] Đã ghi native-access flags và policy theo đúng JDK release.
- [ ] Đã xác định vai trò của JNI/JVMTI agent còn cần giữ.

### ABI và dữ liệu

- [ ] Đã đối chiếu C headers với FunctionDescriptors.
- [ ] Đã kiểm tra size/alignment/padding và pointer width theo từng OS.
- [ ] Đã phân biệt C `long`, `size_t`, `wchar_t`, signed/unsigned types.
- [ ] Đã xác minh string encoding, null termination và conversion.
- [ ] Đã kiểm tra pointer null, buffer lengths và lỗi overflow.
- [ ] Đã chuẩn hóa error mapping/errno hoặc native last-error khi cần.
- [ ] Đã ghi binary/library ABI version và exported symbols.

### Vòng đời và concurrency

- [ ] Mỗi native allocation có owner và release function rõ ràng.
- [ ] Không dùng segment sau khi Arena đóng.
- [ ] Không giữ pointer native sau lifetime hợp lệ.
- [ ] Đã chọn confined/shared/automatic arena dựa trên contract.
- [ ] Đã xác minh thread safety, concurrent close và cancellation.
- [ ] Đã kiểm tra upcall stub lifetime và unregister callbacks.
- [ ] Đã xác định native calls nào có thể block không hủy được.

### Build và deployment

- [ ] jextract/tool version, headers và generated bindings được pin.
- [ ] Native binaries được build/đóng gói theo OS/architecture được hỗ trợ.
- [ ] Shared library path và integrity được kiểm soát.
- [ ] CI clean build có thể regenerate bindings khi cần.
- [ ] Đã kiểm tra library lookup và loaded symbol trên artifact cuối.
- [ ] Đã kiểm tra container permissions, native dependencies và startup.
- [ ] Nếu dùng Native Image, đã test đúng GraalVM version/runtime.

### Kiểm chứng và phát hành

- [ ] Đã so sánh output/error semantics của backend cũ và mới.
- [ ] Đã chạy tests cho null, bounds, lifetime, alignment và callback races.
- [ ] Đã test trên mọi JDK/OS/architecture cam kết hỗ trợ.
- [ ] Đã quan sát off-heap memory, native handles và crash logs.
- [ ] Đã benchmark workload đại diện, không chỉ microbenchmark.
- [ ] Đã chuẩn bị rollout, rollback và owner khi xảy ra native failure.
- [ ] Đã lưu ABI inventory, ownership matrix và release manifest.

**Kết luận:** FFM API mở ra một con đường chuẩn hóa việc gọi hàm C và quản lý vùng nhớ ngoài heap từ Java, đặc biệt từ JDK 22 khi API được hoàn thiện. Nhưng chuyển từ JNI, JNA, Unsafe hoặc custom native bridge sang FFM không phải một cuộc thay tên import; đó là migration của **ABI, memory ownership, callback lifecycle, quyền native access, cách đóng gói và ma trận JDK/OS**. Cần giữ một facade Java ổn định, chuyển từng nhóm hàm có contract rõ ràng, kiểm chứng trên native binary thật và chỉ loại bỏ backend cũ khi đã chứng minh được tính tương thích cùng khả năng rollback.
