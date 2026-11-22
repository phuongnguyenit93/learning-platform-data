# Tìm ký hiệu bằng defaultLookup, loaderLookup hoặc libraryLookup trong Java FFM

## 1. Bài toán: muốn gọi hàm C từ Java, phải tìm đúng địa chỉ hàm trước

Giả sử thư viện C xuất ra hàm:

```c
int ffm_demo_answer_2026(int x);
```

Để gọi hàm đó từ Java bằng **Foreign Function & Memory API (FFM)**, cần thực hiện ba việc khác nhau:

1. **Tìm ký hiệu** (symbol lookup): xác định địa chỉ native của tên `ffm_demo_answer_2026`.
2. **Mô tả ABI/chữ ký**: hàm nhận một `int` C và trả một `int` C, tương ứng `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` trên các ABI được hỗ trợ trong ví dụ.
3. **Tạo và gọi downcall**: dùng `Linker.downcallHandle(...)` để tạo `MethodHandle`, sau đó gọi bằng `invokeExact(...)`.

Ở bước đầu tiên có ba nguồn tìm kiếm phổ biến:

- **`Linker.nativeLinker().defaultLookup()`**: tìm trong các thư viện hệ thống thông dụng được linker của JVM cung cấp sẵn.
- **`SymbolLookup.loaderLookup()`**: tìm trong các thư viện native được nạp qua **`System.load`/`System.loadLibrary`** và **gắn với class loader của mã gọi `loaderLookup()`**.
- **`SymbolLookup.libraryLookup(...)`**: mở/tìm trong **một thư viện cụ thể** bằng tên hoặc `Path`, có vòng đời gắn với `Arena` do bạn chỉ định.

Chọn lookup đúng quan trọng không kém tên symbol. Một hàm tồn tại trong file `.so`/`.dylib`/`.dll` **không bảo đảm cả ba lookup đều thấy nó**. Hơn nữa, tìm thấy địa chỉ **không xác nhận** chữ ký C có tương thích với `FunctionDescriptor` bạn khai báo hay không.

### 1.1. Phiên bản Java

Bài sử dụng API ổn định từ **JDK 22** (`java.lang.foreign`, JEP 454). Java 17 chưa có bản FFM API ổn định này; một số bản JDK 19–21 từng có preview API với cú pháp/chính sách khác. Không copy nguyên ví dụ JDK 22 vào project JDK 17 rồi kỳ vọng biên dịch.

Các ví dụ gọi native cần quyền truy cập mã bản địa, vì vậy dùng:

```bash
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
```

`ALL-UNNAMED` cấp quyền cho mã classpath (unnamed module). Với module có tên, thay bằng tên module thích hợp trong cấu hình triển khai. Tùy JDK, việc thiếu native access có thể khiến lệnh restricted thất bại hoặc phát cảnh báo; **đừng coi flag này là tên thư viện hay tùy chọn tìm kiếm symbol**.

## 2. `SymbolLookup` là gì?

Trong JDK 22, `java.lang.foreign.SymbolLookup` là interface có phương thức cốt lõi:

```java
Optional<MemorySegment> find(String symbolName);
```

Nó tra một **tên symbol** và trả:

- `Optional.of(MemorySegment)` nếu tìm thấy. Segment biểu diễn **địa chỉ của symbol**, có `byteSize() == 0` theo đặc tả; đó **không phải** bản sao toàn bộ mã máy của hàm hay Java object chứa dữ liệu.
- `Optional.empty()` nếu không tìm thấy. Không được gọi `get()` khi empty hoặc tự “đoán” một địa chỉ native để thay thế.

Ví dụ trích đoạn (không phải chương trình độc lập):

```java
SymbolLookup lookup = Linker.nativeLinker().defaultLookup();

Optional<MemorySegment> result = lookup.find("strlen");
if (result.isPresent()) {
    MemorySegment functionAddress = result.get();
    // Truyền functionAddress cùng FunctionDescriptor phù hợp
    // cho Linker.downcallHandle(...) nếu thật sự cần gọi.
}
```

`Optional` buộc người dùng quyết định đường đi khi symbol vắng mặt:

- **Bắt buộc phải có**: `lookup.find(name).orElseThrow(...)`, rồi báo lỗi khởi tạo rõ ràng.
- **Tính năng tùy chọn**: `find(name).ifPresent(...)` hoặc kiểm tra `isPresent()` để dùng fallback.
- **Nhiều nguồn tìm kiếm**: dùng `lookupA.or(lookupB)` (mục 8), kiểm soát thứ tự ưu tiên.

### 2.1. Tên ký hiệu không phải tên lớp Java

Trong mã native:

```c
// C symbol (hàm) được export ra shared library:
int ffm_demo_answer_2026(int x);
```

Java tìm đúng chuỗi `"ffm_demo_answer_2026"`. Không có cơ chế biến `"CFunction.add"` thành ký hiệu C, không tự thêm prefix `Java_` như khi giải quyết một số JNI native method, và không tự tìm trong classpath.

Tên thực tế phụ thuộc ABI và cách compiler/linker **export** symbol:

- C thường export tên C như đã khai báo, nếu compiler/linker cho symbol xuất hiện.
- C++ có **name mangling**; khi muốn một symbol C ổn định cho FFM, dùng `extern "C"`.
- Một số platform cần chỉ thị export/visibility; Windows DLL cần lưu ý `__declspec(dllexport)` hoặc export definition file.
- Linux/macOS có thể dùng visibility để ẩn symbol không công khai.
- Không phải mọi symbol trong header đều được export trong shared library đã build.

**Ví dụ C++** (không phải file chạy độc lập):

```cpp
extern "C" int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

Nếu thiếu `extern "C"`, native symbol có thể mang tên đã mã hóa theo compiler; `find("ffm_demo_answer_2026")` không tìm được dù code C++ tồn tại.

## 3. So sánh nhanh ba nguồn tra cứu

| Tiêu chí | `defaultLookup()` | `loaderLookup()` | `libraryLookup(...)` |
| --- | --- | --- | --- |
| Lấy từ đâu? | `Linker.nativeLinker()` | `SymbolLookup` static factory | `SymbolLookup` static factory |
| Phạm vi | Các thư viện **thông dụng do linker chọn** | Các thư viện nạp qua JNI và gắn với **class loader của caller** | **Thư viện cụ thể** do tên/path xác định |
| Có nạp thư viện mới không? | Không phải mục tiêu API này | **Không**; tìm trong tập đã nạp bằng `System.load*` | **Có thể có**; nếu chưa nạp sẽ tải thư viện |
| Cần `Arena` khi tạo? | Không | Không | **Có** |
| Quản lý lifetime | Theo linker/runtime | Liên quan lifecycle class loader, tự giữ loader còn reachable khi lookup/symbol còn reachable | **Theo Arena**; phải giữ sống tới khi dùng xong |
| Trường hợp hợp lý | `strlen`, `malloc`, hàm thư viện OS/C phổ biến **nếu được linker expose** | Đã có plugin/JNI library nạp bằng `System.load` | Muốn dùng hàm ở `.so`/`.dll` tùy chọn theo path |
| Điểm dễ nhầm | Không phải tra **mọi** symbol của process | Không thấy thư viện chỉ được mở bằng `libraryLookup` | Không tự biến thư viện thành JNI class-loader library |

**Không thể dựa vào `defaultLookup` như một bảng toàn cục liệt kê mọi thư viện trong tiến trình.** Tập thư viện nó expose là quyết định theo **OS, kiến trúc và linker implementation**, không phải một danh sách thống nhất trên Windows/Linux/macOS.

## 4. `Linker.nativeLinker().defaultLookup()`

### 4.1. Cách lấy và tra cứu

```java
Linker linker = Linker.nativeLinker();
SymbolLookup systemSymbols = linker.defaultLookup();

Optional<MemorySegment> strlenAddress = systemSymbols.find("strlen");
```

`defaultLookup()` là **instance method** của `Linker`. Nó không phải `SymbolLookup.defaultLookup()` và cũng không phải `Linker.defaultLookup()` static. Trước tiên chọn linker cho **native ABI của platform đang chạy**.

Một linker có thể expose thư viện C chuẩn hay thư viện toán học; ví dụ trên **Linux/x64**, symbol `strlen` thường được tra qua default lookup. Nhưng đặc tả không quy định mọi platform đều phải expose cùng symbol hoặc cùng ABI.

### 4.2. Ví dụ Linux/x64: tìm và gọi `strlen`

C khai báo:

```c
#include <string.h>
size_t strlen(const char* text);
```

Trên **Linux/x64 điển hình**, `size_t` là 64-bit nên descriptor thường là:

```java
FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)
```

Cách này **không phổ quát** cho hệ 32-bit: `size_t` có thể mang carrier `int`. Nếu cần code đa platform, nên tra canonical layout cho `"size_t"` bằng `linker.canonicalLayouts()` và xử lý kiểu Java tương ứng.

Tệp **`LinuxStrlenDemo.java`** — chương trình độc lập, chủ đích cho Linux/x64 với JVM/JDK 22+:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.util.Optional;

public final class LinuxStrlenDemo {
    private LinuxStrlenDemo() {}

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = linker.defaultLookup();

        Optional<MemorySegment> address = symbols.find("strlen");

        if (address.isEmpty()) {
            System.out.println("strlen unavailable in default lookup");
            return;
        }

        MethodHandle strlen = linker.downcallHandle(
                address.orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom("Hello FFM");
            long size = (long) strlen.invokeExact(cString);
            System.out.println("strlen=" + size);
        }
    }
}
```

Lệnh chạy (Linux/x64, JDK 22+):

```bash
javac LinuxStrlenDemo.java
java --enable-native-access=ALL-UNNAMED LinuxStrlenDemo
```

**Stdout khi `strlen` được default lookup expose:**

```text
strlen=9
```

Nếu linker không expose symbol này, chương trình **không crash do `Optional.get()`**, mà in:

```text
strlen unavailable in default lookup
```

`"Hello FFM"` chứa 9 ký tự ASCII; `Arena.allocateFrom(String)` tạo C string null-terminated UTF-8, còn `strlen` đếm số byte trước byte kết thúc. Với chuỗi Unicode nhiều byte, số byte và số Java `char` có thể khác.

**Đừng áp dụng descriptor `JAVA_LONG` cho `size_t` trên Windows/CPU khác một cách máy móc.** Cần chọn ABI đúng, có thể kiểm tra `linker.canonicalLayouts().get("size_t")` theo tài liệu nền tảng.

## 5. `SymbolLookup.loaderLookup()`: nạp qua JNI rồi tìm bằng class loader

### 5.1. Hợp đồng quan trọng

`SymbolLookup.loaderLookup()` tra các native libraries được tải bằng:

- `System.load("/duong/dan/tuyet/doi/libdemo.so")`; hoặc
- `System.loadLibrary("demo")`.

Điểm quyết định: thư viện được **liên kết với class loader của class gọi `System.load*`**. `loaderLookup()` sau đó tra thư viện liên kết với **class loader của class gọi chính `loaderLookup()`**. Hai bên cần cùng class loader phù hợp; nếu plugin A và plugin B có class loader khác nhau, `loaderLookup` tại B **không** phải “danh mục native libraries của A”.

### 5.2. Lookup động theo quá trình nạp

Điểm hay của `loaderLookup` là nó **dynamic**: giữ một lookup trước, sau đó nạp thêm JNI library ở đúng loader, rồi dùng **chính lookup đã tạo** để thấy symbol mới.

```java
SymbolLookup lookup = SymbolLookup.loaderLookup();

boolean before = lookup.find("ffm_demo_answer_2026").isPresent();

System.load(absoluteLibraryPath.toString());

boolean after = lookup.find("ffm_demo_answer_2026").isPresent();
```

Đoạn này là **minh họa**, giả định `absoluteLibraryPath` đã chỉ đúng thư viện chứa symbol được export. Trên tiến trình thử nghiệm sạch ở mục 10, `before=false`, `after=true`. Nếu thư viện đã được một lệnh `System.load*` khác nạp trước đó cùng loader, không nên khẳng định `before` luôn false.

**Quan trọng:** `loaderLookup` **không phải** hàm nạp thư viện. Nếu chỉ gọi `loaderLookup().find("...")` mà chưa `System.load*` thư viện tương ứng, thì lookup không được yêu cầu tự tìm file trên đĩa.

### 5.3. Vòng đời theo class loader

Javadoc nêu rằng loader lookup có scope tự động giúp **giữ class loader của caller còn reachable** khi lookup hoặc symbol segments do nó trả về còn reachable. Điều đó cũng làm các JNI libraries gắn với class loader được giữ nạp trong thời gian đó.

Vì vậy:

- Không dùng một reference tới lookup/symbol như thể không ảnh hưởng class unloading.
- Trong hệ thống plugin/reloadable class loader, tránh cache lookup/symbol toàn tiến trình nếu muốn unload plugin.
- Không tự gọi `Arena.close` cho `loaderLookup`: API không nhận Arena từ caller, khác `libraryLookup`.

### 5.4. `System.loadLibrary` khác `System.load`

`System.loadLibrary("ffmlookupdemo")` nhận **tên logic** để JVM tra đường dẫn native library của nó. `System.load(absolutePath)` nhận **đường dẫn tuyệt đối** tới đúng file. Khi viết ví dụ thực hành đa OS và để file ngay thư mục hiện tại, cách ổn định là:

```java
String fileName = System.mapLibraryName("ffmlookupdemo");
Path absolutePath = Path.of(fileName).toAbsolutePath().normalize();
System.load(absolutePath.toString());
```

Đây là **trích đoạn**, cần import `java.nio.file.Path` và file đã được build cùng thư mục chạy. `System.mapLibraryName` thường ánh xạ:

- Linux: `libffmlookupdemo.so`.
- macOS: `libffmlookupdemo.dylib`.
- Windows: `ffmlookupdemo.dll`.

Nếu build theo toolchain đặc thù hoặc target loader khác, có thể cần tùy chỉnh đường dẫn. Đừng hard-code `.dll` trên Linux.

## 6. `SymbolLookup.libraryLookup(String, Arena)`: thư viện theo tên

### 6.1. Dùng tên được native OS loader hiểu

Ví dụ Linux:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup libc =
            SymbolLookup.libraryLookup("libc.so.6", arena);

    Optional<MemorySegment> strlen = libc.find("strlen");
    System.out.println(strlen.isPresent());
}
```

Đoạn này là **trích đoạn dành cho hệ Linux/glibc thông dụng**, không phải lựa chọn chạy được trên mọi Linux distribution (ví dụ hệ musl có tên thư viện khác). `libc.so.6` là tên do **native dynamic loader** xử lý, không phải Java classpath hay Maven artifact.

Một số tên thường gặp nhưng **không bảo đảm có sẵn trên mọi máy**:

| Hệ | Tên thư viện native có thể gặp | Lưu ý |
| --- | --- | --- |
| Linux glibc | `libc.so.6`, `libm.so.6` | Distro, linker search path và ABI |
| macOS | `/usr/lib/libSystem.B.dylib` | System libraries, framework và chính sách SIP |
| Windows | `ucrtbase.dll`, `kernel32.dll` | Windows DLL search semantics, architecture |

Nếu target thư viện cụ thể trong ứng dụng, ưu tiên `Path` tới file đã đóng gói thay vì chỉ tin tên OS cố định.

### 6.2. Arena kiểm soát lifetime của lookup

`libraryLookup` nhận `Arena` bắt buộc:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lib = SymbolLookup.libraryLookup(
            "libc.so.6", arena
    );

    MemorySegment function = lib.find("strlen").orElseThrow();

    // Tạo downcall/call function khi arena vẫn còn sống.
}
// Sau close, không dùng function address/handle từ lookup
// như thể thư viện vẫn được bảo đảm còn nạp.
```

Cú pháp trên là **đoạn trích**, không phải chương trình Java độc lập. Thư viện được mở nếu chưa nạp; phạm vi của lookup gắn với arena. Khi một confined arena đóng, phần native library do arena đó sở hữu có thể bị unload theo contract (trừ khi còn được giữ nạp độc lập qua cơ chế khác).

**Không nhất thiết đóng arena sẽ khiến mọi bản sao của cùng library biến mất ngay khỏi tiến trình.** Hệ điều hành/JVM có thể còn reference khác (ví dụ thư viện đã `System.load` trước đó). Nhưng code vẫn phải tuân theo lifetime của lookup và các địa chỉ lấy từ nó, không dùng hàm native sau khi scope bị đóng.

### 6.3. Giữ arena đủ lâu

Anti-pattern:

```java
// SAI: trả về symbol từ một arena sẽ đóng ngay.
static MemorySegment getSymbol() {
    try (Arena arena = Arena.ofConfined()) {
        return SymbolLookup.libraryLookup(
                "libc.so.6", arena
        ).find("strlen").orElseThrow();
    }
}
```

Hàm chỉ là minh họa lỗi; địa chỉ trả về không nên dùng sau khi arena đóng.

Cách đúng là **sở hữu đồng thời arena, lookup và downcall trong một service object**, có phương thức `close` sau khi tất cả callers đã kết thúc. Nếu cần gọi từ nhiều Java threads, cân nhắc `Arena.ofShared()`, nhưng vẫn đồng bộ đóng và không cho in-flight call dùng library sau close.

## 7. `SymbolLookup.libraryLookup(Path, Arena)`: thư viện bằng đường dẫn

API còn overload:

```java
SymbolLookup.libraryLookup(path, arena)
```

Trong đó `path` là `java.nio.file.Path` trên **default file system**, thường dùng khi ứng dụng tự build/cấp phát native library cạnh executable. Nó giúp giảm phụ thuộc vào search path hệ điều hành:

```java
Path path = Path.of(
        System.mapLibraryName("ffmlookupdemo")
).toAbsolutePath();

try (Arena arena = Arena.ofConfined()) {
    SymbolLookup library = SymbolLookup.libraryLookup(path, arena);
    MemorySegment address = library
            .find("ffm_demo_answer_2026")
            .orElseThrow();
    // Tạo downcall và sử dụng trước khi đóng arena.
}
```

Đoạn này cần file native đã build đúng tại `path`. `libraryLookup(Path, Arena)` **không** tự thêm prefix `lib`, **không** tự lấy từ Maven/JAR, cũng không tự tìm các `.class`. Nó làm việc với native library thực tế.

### 7.1. Vì sao có thể phải dùng tên thay cho Path?

- Với thư viện hệ thống như `libc`, tên/soname thường được OS dynamic loader tìm theo cấu hình chuẩn.
- Trong một số môi trường Linux/macOS/Windows, path cố định tới system library không ổn định khi nâng cấp OS.
- Với thư viện **do ứng dụng quản lý**, dùng path tuyệt đối giúp kiểm soát version và kiến trúc của binary.
- Có thể kết hợp fallback: cố dùng thư viện ứng dụng bằng Path; nếu không có, tìm một thư viện hệ thống bằng String, nhưng cần có hợp đồng ABI tương thích, không chọn đại chỉ vì trùng tên symbol.

### 7.2. Những lỗi khi `libraryLookup` mở thư viện

Javadoc JDK 22 nêu các lỗi đáng chú ý:

| Điều kiện | Lỗi/triệu chứng |
| --- | --- |
| Tên không nhận diện một thư viện native hợp lệ | `IllegalArgumentException` |
| `Path` không trỏ tới library hợp lệ trên default filesystem | `IllegalArgumentException` |
| Arena đã đóng | `IllegalStateException` |
| Thread gọi không phải owner của confined arena | `WrongThreadException` |
| Caller chưa có native access | `IllegalCallerException` |
| Thư viện không có symbol cần tìm | `find` trả `Optional.empty()` |
| Library đúng nhưng sai CPU/ABI/dependency | Native loader thất bại, đôi khi hiện qua exception liên quan load |

**Lưu ý:** lỗi **nạp thư viện** và lỗi **không tìm thấy symbol** là hai giai đoạn khác nhau. `libraryLookup` có thể tải thư viện thành công nhưng `find("wrong_name")` vẫn rỗng.

## 8. `SymbolLookup.or` để tìm nhiều nơi theo thứ tự

FFM hỗ trợ kết hợp các lookup bằng `or`:

```java
SymbolLookup combined = appLibrary
        .or(SymbolLookup.loaderLookup())
        .or(Linker.nativeLinker().defaultLookup());

Optional<MemorySegment> symbol = combined.find("some_function");
```

Đây là **trích đoạn**, giả định `appLibrary` là lookup đã được tạo và arena liên quan còn sống.

Cơ chế `or`:

1. Tìm ở **lookup bên trái** trước.
2. Nếu không thấy, chuyển sang lookup bên phải.
3. Nếu cả hai không có, trả `Optional.empty()`.

Thứ tự **là một phần hợp đồng ứng dụng**. Nếu nhiều thư viện cùng export tên `init` hoặc `version`, gọi hàm từ nhầm ABI có thể gây crash. Vì vậy nên:

- Ưu tiên lookup của **thư viện đã xác định rõ**.
- Chỉ fallback khi hai implementation thực sự có **cùng hợp đồng C ABI**, phiên bản và ownership.
- Dùng tên symbol có namespace/prefix riêng, tránh các tên `init`/`open` quá chung.
- Quản lý arena của từng `libraryLookup` trong chain; `or` không làm lookup bất tử sau khi arena đóng.

### 8.1. Không ghép lookup để “vét mọi thư viện” tùy tiện

Việc ghép nhiều nguồn có ích với plugin fallback, nhưng không thay bước kiểm tra **thư viện và phiên bản ABI**. Một tên symbol giống nhau ở hai thư viện không chứng minh nó nhận cùng kiểu tham số. Cần biết rõ `FunctionDescriptor` phù hợp với symbol **được chọn thực tế**.

## 9. Từ symbol đến hàm có thể gọi: `Linker.downcallHandle`

`SymbolLookup.find` chỉ lấy **địa chỉ**. Nó không tự tạo Java method, không kiểm tra C signature, và không biết thư viện định trả `int` hay `double`.

Ví dụ từ một symbol C:

```c
int ffm_demo_answer_2026(int x);
```

FFM:

```java
MemorySegment address = lookup.find(
        "ffm_demo_answer_2026"
).orElseThrow();

MethodHandle fn = Linker.nativeLinker().downcallHandle(
        address,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT
        )
);

int answer = (int) fn.invokeExact(21);
```

Đây là **trích đoạn** có `lookup` hợp lệ và phương thức chứa code khai báo `throws Throwable`. `FunctionDescriptor.of(returnLayout, parameterLayouts...)` ở đây mô tả đúng C `int → int`. Lưu ý **tham số đầu tiên** của `of` là layout **giá trị trả về**. Với native C `void` dùng `FunctionDescriptor.ofVoid(...)`.

`invokeExact` kiểm tra kiểu Java **chính xác**; cần `(int)` cho kiểu trả về, và tham số truyền đúng Java `int`. Trong trường hợp này:

```java
int value = (int) fn.invokeExact(21);
```

là đúng. Nếu vô tình viết:

```java
// Sai về loại dữ liệu nếu MethodHandle mong đợi (int)int.
long value = (long) fn.invokeExact(21L);
```

thì signature `long → long` không trùng `int → int` và sẽ phát sinh `WrongMethodTypeException`; không phải lỗi tìm kiếm symbol.

### 9.1. FFM không kiểm tra chữ ký C từ binary

Native symbol address không mang metadata Java mô tả đủ ABI. Một `FunctionDescriptor` sai có thể gây **corruption, crash** hoặc kết quả ngẫu nhiên, dù `find` trả present và compiler Java không báo lỗi. Luôn lấy chữ ký từ **header C của đúng thư viện/version**, và kiểm tra ABI cho kiểu như `long`/`size_t`/struct/varargs/pointer.

Ví dụ `size_t` của Linux/x64 thường 64-bit, nhưng Windows x86 hoặc CPU 32-bit có thể khác. Không chọn `JAVA_LONG` chỉ theo thói quen khi chưa biết platform và mapping.

### 9.2. Địa chỉ hàm không phải bộ nhớ dữ liệu thông thường

MemorySegment trả từ `find` có **zero length**. Không nên gọi `symbol.get(JAVA_INT,0)` để “đọc mã lệnh” hoặc coi nó là buffer dữ liệu. Với **global variable symbol**, có trường hợp cần `reinterpret` với kích thước phù hợp để truy cập, nhưng đó là API restricted nguy hiểm, yêu cầu hiểu quyền sở hữu bộ nhớ/địa chỉ; bài này tập trung vào **tra ký hiệu hàm** và downcall.

## 10. Thực hành đầy đủ: C library + Java, so sánh cả ba lookup

Chúng ta tạo một shared library C **của riêng mình**, có tên symbol ít khả năng trùng với thư viện hệ thống:

```c
int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

Sau đó chạy Java thành **ba tiến trình khác nhau**:

- `library`: dùng `libraryLookup(Path, Arena)` mở thư viện riêng và chứng minh `loaderLookup` **không** tự nhận thư viện chỉ được mở qua library lookup.
- `loader`: tạo `loaderLookup` trước rồi gọi `System.load` và dùng lookup **cũ** để tìm symbol vừa được nạp.
- `default`: kiểm tra `strlen` ở `defaultLookup`; kết quả **phụ thuộc OS/linker**, không giả định nó luôn có.

**Tại sao chạy tách tiến trình?** Một native library đã nạp ở tiến trình này có thể làm thay đổi tập library gắn với class loader. Để chứng minh khác nhau giữa `libraryLookup` và `loaderLookup`, phải chạy hai mode trong **hai lần khởi động JVM riêng**, tránh lẫn trạng thái nạp từ mode trước.

### 10.1. File C: `FfmLookupDemo.c`

```c
#if defined(_WIN32)
#  define EXPORT __declspec(dllexport)
#else
#  define EXPORT __attribute__((visibility("default")))
#endif

/* C ABI ổn định, không cần JNI_OnLoad hay native Java methods. */
EXPORT int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

Đây là **file C độc lập để biên dịch thành shared library**. Không cần `#include <jni.h>` hoặc header JNI vì Java gọi qua **FFM downcall**, không khai báo Java `native`.

Trên Windows, hướng dẫn dùng **x64 MSVC**, nhằm có tên symbol C đơn giản không bị biến thể convention như một số target x86/32-bit. Với C++ thì bổ sung `extern "C"` như mục 2.

### 10.2. Java: `FfmSymbolLookupDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmSymbolLookupDemo {
    private static final String LIB = "ffmlookupdemo";
    private static final String SYMBOL = "ffm_demo_answer_2026";

    private FfmSymbolLookupDemo() {}

    private static MethodHandle bind(
            Linker linker, MemorySegment symbol) {

        // C: int ffm_demo_answer_2026(int)
        return linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)
        );
    }

    private static void libraryMode(
            Linker linker, Path path) throws Throwable {

        // Lookup được tạo trước khi libraryLookup tải thư viện.
        SymbolLookup callerLibraries = SymbolLookup.loaderLookup();
        System.out.println("loader before="
                + callerLibraries.find(SYMBOL).isPresent());

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup direct =
                    SymbolLookup.libraryLookup(path, arena);

            MemorySegment symbol =
                    direct.find(SYMBOL).orElseThrow();

            MethodHandle function = bind(linker, symbol);
            int result = (int) function.invokeExact(21);

            System.out.println("library=" + result);
            System.out.println("loader after libraryLookup="
                    + callerLibraries.find(SYMBOL).isPresent());
        }
    }

    private static void loaderMode(
            Linker linker, Path path) throws Throwable {

        // Loader lookup là dynamic: cùng object lookup vẫn
        // nhìn thấy JNI library mới được nạp bởi class loader này.
        SymbolLookup callerLibraries = SymbolLookup.loaderLookup();
        System.out.println("loader before="
                + callerLibraries.find(SYMBOL).isPresent());

        System.load(path.toString());

        MemorySegment symbol =
                callerLibraries.find(SYMBOL).orElseThrow();
        int result = (int) bind(linker, symbol).invokeExact(21);

        System.out.println("loader after System.load="
                + callerLibraries.find(SYMBOL).isPresent());
        System.out.println("loader=" + result);

        // libraryLookup vẫn có thể tra library đã được System.load.
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup direct =
                    SymbolLookup.libraryLookup(path, arena);

            int viaLibrary = (int) bind(
                    linker,
                    direct.find(SYMBOL).orElseThrow()
            ).invokeExact(21);

            System.out.println("library after System.load="
                    + viaLibrary);
        }
    }

    private static void defaultMode(Linker linker) {
        SymbolLookup standard = linker.defaultLookup();

        // Không assume thư viện custom có trong default lookup.
        // Tập symbol do linker/OS quyết định.
        System.out.println("default strlen present="
                + standard.find("strlen").isPresent());
    }

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use: library, loader, or default"
            );
        }

        Linker linker = Linker.nativeLinker();

        Path path = Path.of(
                System.mapLibraryName(LIB)
        ).toAbsolutePath().normalize();

        switch (args[0]) {
            case "library" -> libraryMode(linker, path);
            case "loader"  -> loaderMode(linker, path);
            case "default" -> defaultMode(linker);
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }
}
```

**Điểm đáng học từ code:**

1. `Linker.nativeLinker()` là nguồn tạo linker cho native ABI; không tự quyết định thư viện cần tìm.
2. `System.mapLibraryName("ffmlookupdemo")` đổi tên logic thành tên file native thích hợp theo OS.
3. `libraryMode` chỉ gọi `SymbolLookup.libraryLookup(path, arena)`, **không** gọi `System.load`. `loaderLookup` đã tạo trước sẽ tiếp tục không thấy symbol của thư viện chỉ được mở bằng library lookup.
4. `loaderMode` gọi `System.load` từ cùng class loader, nên `callerLibraries` — dù tạo **trước khi nạp** — có thể tra symbol sau khi nạp.
5. `libraryLookup` vẫn tra được thư viện ngay cả khi thư viện đã được nạp từ `System.load`; việc gắn với class loader không hạn chế lookup theo thư viện cụ thể.
6. Mọi lời gọi `MethodHandle` lấy từ library lookup diễn ra **bên trong try-with-resources**, khi arena còn sống.
7. `defaultMode` kiểm tra một symbol hệ thống và **không** gán cho nó stdout cứng, vì tập default symbols thay đổi theo platform.
8. `Optional.orElseThrow` được dùng cho symbol **bắt buộc** của thư viện custom; nếu không export được, chương trình thất bại rõ thay vì gọi địa chỉ không hợp lệ.
9. Tham số `21` và hàm C cộng `21` khiến kết quả thành `42`; đây là kết quả độc lập với OS miễn thư viện tương thích ABI được nạp thành công.

### 10.3. Linux — GCC/Clang

Dùng JDK **22+** và compiler C tương ứng kiến trúc JVM, đứng trong thư mục chứa cả hai file. Ví dụ GCC trên Linux x64:

```bash
gcc -std=c11 -O2 -shared -fPIC \
    FfmLookupDemo.c -o libffmlookupdemo.so

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

Nếu hệ điều hành không tìm được dependency của thư viện hoặc JNI loader áp dụng hạn chế, cần kiểm tra thông báo native loader, đường dẫn đầy đủ và `ldd`/`readelf`. Vì ví dụ dùng `Path` tuyệt đối trỏ tới file hiện tại, không cần đặt tên thư viện vào `java.library.path` để gọi `System.load(path)`.

### 10.4. macOS — Clang

Trên macOS với Command Line Tools và JDK 22+:

```bash
clang -std=c11 -O2 -dynamiclib \
    FfmLookupDemo.c -o libffmlookupdemo.dylib

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

Với macOS Apple Silicon hoặc Intel, phải dùng JDK cùng kiến trúc với shared library. Nếu library được ký/có policy đặc biệt, native loader còn có quy tắc hệ thống khác; đó là vấn đề **loading**, không phải khác biệt `find`.

### 10.5. Windows — MSVC x64

Mở **x64 Native Tools Command Prompt** của Visual Studio, bảo đảm JDK 22+ x64 có trong `PATH`:

```bat
cl /nologo /O2 /LD FfmLookupDemo.c /link /OUT:ffmlookupdemo.dll

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

Thư viện `ffmlookupdemo.dll` nằm trong thư mục đang chạy; Java tạo `Path` tuyệt đối tới đó. Windows DLL loader cũng phải tìm được các dependency tương ứng, nếu có.

### 10.6. Stdout chính xác cho `library`

Ở **tiến trình sạch**, chỉ có custom library ở đường dẫn hiện tại, không có library đã nạp trước đó export cùng tên độc nhất:

```text
loader before=false
library=42
loader after libraryLookup=false
```

Đây là chứng minh: mở một thư viện bằng `libraryLookup` **không gắn nó vào caller class loader như `System.load`**. Việc symbol có thể nằm trong process không làm `loaderLookup` trở thành lookup “toàn tiến trình”.

### 10.7. Stdout chính xác cho `loader`

Chạy một **tiến trình Java mới** (lệnh `java` riêng):

```text
loader before=false
loader after System.load=true
loader=42
library after System.load=42
```

Đây là chứng minh: `loaderLookup` được tạo trước vẫn cập nhật theo native libraries mới của class loader. Sau khi `System.load`, cả loader lookup và library lookup vào đúng thư viện đều tìm được symbol. Cần giữ tên thư viện và đường dẫn chính xác theo OS.

### 10.8. Stdout của `default` phụ thuộc OS/linker

Ví dụ nếu `strlen` thuộc tập system symbols do linker expose:

```text
default strlen present=true
```

Nếu không expose:

```text
default strlen present=false
```

**Cả hai đều là output hợp lệ** của nhánh `default`: đây là phép hỏi `find("strlen").isPresent()`, không phải phép kiểm thử cứng rằng platform phải export `strlen`. `defaultLookup` không yêu cầu custom C library vừa build phải xuất hiện.

## 11. Những chi tiết dễ sai về vòng đời Arena

### 11.1. Confined và shared arena

`Arena.ofConfined()` phù hợp một luồng tạo lookup và gọi symbol trong phạm vi đó. Gọi restricted `libraryLookup` từ thread khác với owner có thể gặp `WrongThreadException`. Với thư viện được dùng trong nhiều Java threads, có thể cân nhắc:

```java
Arena arena = Arena.ofShared();
SymbolLookup lib = SymbolLookup.libraryLookup(path, arena);

// Các worker có thể truy cập những symbol segments
// theo scope shared, nhưng phải phối hợp ngừng hoạt động
// trước khi đóng arena.
```

Đây là **mẫu minh họa**, giả định `path` đã có và caller có quyền native access. `Arena.ofShared()` không khiến native library tự thread-safe: C function có thể dùng global state và không reentrant. Owner phải quản lý **in-flight calls** và `arena.close()` chỉ sau khi mọi lời gọi đã hoàn tất.

### 11.2. Không cache MethodHandle lâu hơn arena

`downcallHandle` có thể đóng địa chỉ symbol từ `libraryLookup`. Nếu bạn cache `MethodHandle` vào singleton rồi đóng arena, việc gọi lại handle là sai hợp đồng vòng đời. Không dựa vào `MethodHandle` để “giữ file thư viện mãi tồn tại” khi arena đã đóng.

Một service hợp lý có vòng đời:

```text
open()
  -> Arena.ofShared()/Arena.ofConfined()
  -> SymbolLookup.libraryLookup(...)
  -> find required symbols
  -> build MethodHandles
RUNNING
  -> invoke handles only while library scope alive
close()
  -> reject new calls
  -> wait for in-flight calls to complete
  -> close arena
CLOSED
  -> never invoke old handles/addresses
```

Các trạng thái `RUNNING/CLOSED` do **ứng dụng thiết kế**, không phải các enum sẵn của FFM.

### 11.3. `loaderLookup` có thể kéo dài class loader lifetime

Khác với `libraryLookup`, loader lookup không có Arena do caller tạo. Lookup/symbol segments có scope tự động liên hệ tới class loader; cache toàn cục một symbol trong plugin có thể khiến plugin không thể unload. Khi thiết kế plugin hot reload, cần kiểm soát các reference Java và class-loader graph.

### 11.4. `defaultLookup` cũng không là lời hứa API ổn định của mọi hệ

Một phiên bản JDK mới hoặc OS ABI khác có thể expose tập symbol khác. Dùng `defaultLookup` cho thư viện hệ thống **thực sự là một phần của hợp đồng platform** của bạn; đối với native plugin do sản phẩm đóng gói, `libraryLookup(Path, Arena)` thường rõ ràng hơn.

## 12. Đối tượng trả từ `find`: hàm và global variable

`find` trả **địa chỉ symbol**, không có bước tự nhận ra đó là hàm hay biến. Nếu C library export:

```c
int global_counter = 100;
int ffm_demo_answer_2026(int x) { return x + 21; }
```

thì `find("global_counter")` và `find("ffm_demo_answer_2026")` đều trả địa chỉ native, nhưng cách sử dụng rất khác:

- **Hàm**: dùng `Linker.downcallHandle` với `FunctionDescriptor` chính xác.
- **Biến toàn cục**: phải biết layout/kích thước, trạng thái write và lifetime; symbol segment từ lookup là **zero length**. Việc `reinterpret` để đọc/ghi variable là restricted và có thể mất an toàn.

Không được gọi `downcallHandle` lên địa chỉ một biến rồi kỳ vọng JVM tự phát hiện sai. Tương tự, không đọc dữ liệu int trực tiếp từ function address. Bài này chủ ý chỉ minh họa **function symbol** để tránh nhập nhằng.

## 13. Tra cứu tên nào trên hệ điều hành nào?

### 13.1. Linux

Dùng `nm -D` hoặc `readelf -Ws` để xem dynamic symbol table:

```bash
nm -D libffmlookupdemo.so | grep ffm_demo_answer_2026
readelf -Ws libffmlookupdemo.so | grep ffm_demo_answer_2026
```

Mã C có `__attribute__((visibility("default")))` làm symbol được export trong cấu hình GCC/Clang thông thường. Nếu symbol bị ẩn bởi flags, `find` không trả giá trị dù hàm tồn tại trong object code.

### 13.2. macOS

Dùng `nm` (macOS có thể hiển thị prefix `_` ở cấp symbol table), ví dụ:

```bash
nm -gU libffmlookupdemo.dylib | grep ffm_demo_answer_2026
```

Tại FFM/JNI symbol resolution, tên C được tra bằng API thích hợp của loader, thường dùng tên C theo source `ffm_demo_answer_2026`; không tự thêm underscore tùy tiện nếu chỉ dựa vào cách `nm` hiển thị.

### 13.3. Windows

Dùng `dumpbin /EXPORTS`:

```bat
dumpbin /EXPORTS ffmlookupdemo.dll
```

Xác nhận export name cần tìm. Ví dụ dùng x64 nên tên function C đơn giản hơn các kiểu decoration trên x86. Trên C++, export với `extern "C"` và ABI phù hợp, tránh name mangling.

**Nguyên tắc:** kiểm tra **binary thực tế**, không chỉ header có hàm. Không nên tự thêm hoặc xóa các ký tự của symbol name theo suy đoán, nhất là khi thư viện dùng versioned symbols hoặc compiler đặc biệt.

## 14. Các lỗi điển hình và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Khắc phục |
| --- | --- | --- |
| `find("foo")` trả empty | Không export symbol, sai tên/đúng thư viện nhưng khác version | Kiểm tra `nm`/`dumpbin` và header/library đúng version |
| `loaderLookup` không thấy thư viện đã mở bằng `libraryLookup` | Chỉ `System.load*` nạp và gắn với class loader | Dùng lookup của chính `libraryLookup`, hoặc `System.load*` nếu phù hợp |
| `loaderLookup` tại plugin B không thấy JNI lib plugin A | Hai caller class loaders khác nhau | Định nghĩa ranh giới plugin/loading rõ ràng |
| `loaderLookup` tạo trước `System.load` nhưng lập trình viên nghĩ nó giữ snapshot | Loader lookup **dynamic** | Dùng lại lookup; nó sẽ thấy thư viện mới của cùng loader |
| `defaultLookup` không thấy symbol trong file custom | Tập default libs do linker chọn | Dùng `libraryLookup(Path, Arena)` hoặc đúng `loaderLookup` |
| `libraryLookup("my.so", arena)` không mở được trên OS khác | Tên/soname/loader search path khác nhau | Dùng `Path` có kiểm soát và packaging đúng |
| `System.loadLibrary("libdemo.so")` sai | Nhầm logical name với file name | Dùng `"demo"` hoặc `System.load(absolutePath)` |
| `libraryLookup` trả `IllegalCallerException` | Thiếu native access | Cấp `--enable-native-access` cho module gọi |
| Arena đóng nhưng vẫn gọi downcall handle cũ | Symbol lifetime không còn hợp lệ | Không dùng handle sau khi đóng; owner quản lý in-flight calls |
| Tìm thấy symbol nhưng gọi crash | `FunctionDescriptor` sai, ABI/số tham số không đúng | Đối chiếu C header, calling convention, size_t/long/struct |
| `WrongMethodTypeException` khi `invokeExact` | Java carrier/type không khớp handle | Truyền `int`/`long` đúng và cast return đúng |
| DLL/so không mở được dù file có mặt | Thiếu phụ thuộc, sai arch/ABI, lỗi loader | Kiểm tra dependency chain và native loader diagnostics |
| Code C++ export symbol mangled | Thiếu `extern "C"` | Export tên C ổn định |
| Lookup trong class loader bị giữ mãi | Cache loader lookup ở singleton ngoài plugin | Quản lý reference và plugin unload lifecycle |
| Symbol có tên giống một hàm OS khác | Lookup chain ưu tiên nhầm nơi | Đổi tên namespace rõ ràng hoặc tránh fallback thiếu kiểm chứng |

### 14.1. Phân biệt ba tầng lỗi

Một sự cố FFM thường nằm ở một trong ba tầng:

1. **Load** — không mở được thư viện đúng format/architecture/dependency, `libraryLookup` hoặc `System.load` thất bại.
2. **Lookup** — đã mở được thư viện nhưng `find` không thấy tên export.
3. **Link/invoke** — `find` thành công nhưng `FunctionDescriptor`/carrier/lifetime/native code sai.

Nếu debug bằng cách thay `FunctionDescriptor` khi thực tế file chưa load được, sẽ không giải quyết đúng nguyên nhân. Ghi lại chính xác library path, symbol name, native ABI, Arena state và lớp caller.

## 15. Cấu hình production và bảo mật

### 15.1. Không nạp file native theo input tùy ý

`libraryLookup` có thể nạp thư viện native vào tiến trình JVM. Native binary có toàn quyền thao tác bộ nhớ tiến trình; nó **không** bị Java type safety giới hạn như bytecode bình thường. Không xây đường dẫn tới `.dll`/`.so` trực tiếp từ dữ liệu không đáng tin (HTTP parameter, user-provided file name). Nên:

- Chỉ cho phép các thư viện đã ký hoặc thuộc package đáng tin, có allowlist.
- Kiểm tra canonical path, version, checksum/signature và đúng arch.
- Tránh hijacking đường tìm DLL/thư viện bằng việc tin thứ tự search path không kiểm soát.
- Đối chiếu version/ABI contract với symbol sẽ gọi.

### 15.2. Native access là một ranh giới quyền, không phải cách chọn symbol

`--enable-native-access` cấp quyền cho caller module dùng restricted FFM methods; nó **không** làm `defaultLookup` chứa thêm thư viện, **không** ép `loaderLookup` thấy file mở bằng `libraryLookup`, và **không** chữa lỗi ABI.

Với mã classpath, ví dụ dùng `ALL-UNNAMED`. Với ứng dụng module thật, có thể cấu hình native access theo module và rà soát các quy tắc JDK chạy đích.

### 15.3. Chia sẻ lookup giữa nhiều luồng

Một `SymbolLookup` có thể được truy cập theo hợp đồng liên quan lifetime, nhưng thư viện do `Arena.ofConfined()` quản lý bị ràng buộc bởi thread ownership. Không vượt qua ranh giới thread tùy tiện. Nếu cần shared native access, dùng `Arena.ofShared()` với quy trình đóng đợi hoàn tất, đồng thời bảo đảm **hàm C có tính thread-safe** nếu bị gọi đồng thời.

### 15.4. Test matrix cần kiểm tra thực tế

| Kiểm thử | Điều xác minh |
| --- | --- |
| Mỗi OS/architecture | Binary format, tên file, linker ABI |
| Symbol tồn tại | `find` có giá trị, đúng export |
| Symbol không tồn tại | Fallback hoặc lỗi dễ hiểu, không crash |
| Class loader khác | `loaderLookup` không rò phạm vi giữa plugins |
| `libraryLookup` với Arena đóng | Không dùng symbol/handle sau close |
| `libraryLookup` kết hợp `System.load` | Quy tắc liên kết với loader và reference count |
| `FunctionDescriptor` đúng | Return/parameter types, ptr, struct, size_t |
| Thiếu native access | Lỗi quyền rõ ràng và cấu hình chạy đúng |
| Load từ đường dẫn không tin cậy | Từ chối nguồn không hợp lệ |
| Nhiều phiên bản thư viện | Tránh trùng tên symbol với ABI khác |

## 16. Hỏi đáp để tự kiểm tra

**1. `defaultLookup` có tìm tất cả native libraries đang trong tiến trình không?** Không. Nó expose **tập thư viện được linker chọn** theo OS/processor. Không thay thế library-specific lookup.

**2. `loaderLookup` tự gọi `dlopen` hoặc `LoadLibrary` không?** Không. Nó tra thư viện đã `System.load`/`System.loadLibrary` và gắn với caller class loader.

**3. `libraryLookup(Path, Arena)` có tạo liên kết JNI với class loader không?** Không. Thư viện chỉ được mở bằng library lookup **không** vì thế xuất hiện trong loader lookup của class loader.

**4. `loaderLookup` tạo trước `System.load` có thấy library nạp sau không?** Có, nó dynamic theo tập JNI libraries được gắn với loader tương ứng.

**5. `libraryLookup` có thể tra thư viện đã được `System.load` trước đó không?** Có, vì library lookup tập trung vào chính thư viện, bất kể liên kết class loader của việc nạp JNI.

**6. Vì sao `find` trả `MemorySegment` dài 0?** Vì nó biểu diễn **một địa chỉ symbol**, không phải vùng byte tự động biết kích thước. Khi gọi hàm, truyền segment đó vào `Linker.downcallHandle`.

**7. Hai thư viện cùng export `calculate`, lookup nào được chọn trong `a.or(b)`?** `a` được ưu tiên; chỉ nếu `a.find` empty mới tra `b`. Cần đảm bảo ABI của implementation được chọn.

**8. Tại sao truyền `ValueLayout.JAVA_LONG` cho C `size_t` là nguy hiểm khi port?** Vì C `size_t` phụ thuộc ABI; trên 32-bit thường là 32 bit. Hãy dùng mapping từ linker và kiểm thử target.

**9. Dùng xong `libraryLookup` có thể đóng Arena và vẫn gọi MethodHandle đã cache không?** Không. Phải bảo đảm thư viện và symbol còn sống suốt lời gọi. Đóng arena sau khi mọi in-flight call kết thúc.

**10. Nếu file `.dll` có hàm C nhưng `find` empty, nên kiểm tra điều gì đầu tiên?** Đúng file/architecture, export table (ví dụ `dumpbin /EXPORTS`), đúng spelling/calling convention và visibility.

**11. Có cần `System.loadLibrary` trước `libraryLookup(path, arena)` không?** Không. `libraryLookup` có khả năng **tải thư viện nếu chưa nạp**. Gọi cả hai chỉ khi mô hình của ứng dụng thật sự cần.

**12. Chỉ tra symbol `strlen` thì có cần `FunctionDescriptor` không?** `find("strlen")` thì **không**; nếu muốn **gọi** `strlen` qua downcall thì cần descriptor đúng ABI.

## 17. Checklist áp dụng

1. Chạy JDK 22+ với FFM API ổn định, cấp native access cho module phù hợp khi dùng restricted calls.
2. Phân biệt **tìm symbol** (`SymbolLookup.find`), **mô tả ABI** (`FunctionDescriptor`) và **gọi hàm** (`Linker.downcallHandle`).
3. Muốn symbol OS thông dụng: thử `linker.defaultLookup()`, nhưng luôn xử lý trường hợp không có.
4. Thư viện đã nạp bằng JNI từ cùng class loader: dùng `SymbolLookup.loaderLookup()`.
5. Muốn nhắm một file native cụ thể: dùng `SymbolLookup.libraryLookup(Path, Arena)` hoặc overload tên khi có chủ đích.
6. Không giả định `libraryLookup` làm thư viện xuất hiện trong `loaderLookup`.
7. Với loader lookup, hiểu phạm vi **caller class loader** và tính **dynamic** sau `System.load*`.
8. Với library lookup, giữ Arena mở khi dùng symbol/downcall; đóng khi không còn lời gọi nào đang thực hiện.
9. Với fallback `or`, giữ thứ tự lookup và ABI contract tường minh.
10. Trước khi invoke, kiểm tra symbol export, native architecture, kiểu C carrier và `FunctionDescriptor` đúng.
11. Với `Optional.empty()`, báo lỗi có ngữ cảnh hoặc chọn fallback an toàn; không gọi native qua địa chỉ giả.
12. Trong sản phẩm thật, quản lý version, dependency, path allowlist và lifecycle plugin/class loader.

## Tài liệu tham khảo chính thức

- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `find`, `or`, `loaderLookup`, `libraryLookup(String/Path, Arena)` và quy tắc class loader, Arena.
- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `defaultLookup`, `downcallHandle` và canonical layouts.
- [Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): khai báo chữ ký native function.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): lifetime, confinement và shared arena.
- [Java SE 22 — System.load](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#load(java.lang.String)): nạp thư viện native theo đường dẫn tuyệt đối.
- [Java SE 22 — System.loadLibrary](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): nạp thư viện native theo tên logic.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): lý do API FFM ổn định từ JDK 22, khái niệm linker, lookup và quyền native access.