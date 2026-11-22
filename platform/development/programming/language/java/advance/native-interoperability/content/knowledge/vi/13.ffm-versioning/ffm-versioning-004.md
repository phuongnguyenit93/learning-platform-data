# Những tên phương thức cần kiểm tra khi chuyển mã FFM giữa các phiên bản Java

## 1. Vì sao một đoạn Foreign Function & Memory (FFM) chạy ở JDK này lại không biên dịch ở JDK khác?

**Foreign Function & Memory API (FFM)** cung cấp các kiểu Java để làm việc với native memory, thư viện C và native function pointers mà không cần tự viết lớp JNI cho mọi lời gọi. API này trải qua nhiều lần thiết kế lại trước khi trở thành API chính thức:

| JDK | Giai đoạn | Module/package chủ yếu | Ý nghĩa đối với source code |
| --- | --- | --- | --- |
| **17** | JEP 412 — incubator | Module `jdk.incubator.foreign`, package `jdk.incubator.foreign` | Dùng `CLinker`, `ResourceScope`, `MemoryAddress`, nhiều tên cũ; bật incubator module |
| **18** | JEP 419 — incubator lần hai | `jdk.incubator.foreign` | Không giả định mọi chữ ký trong JDK 17 còn giống hệt; tra Javadoc JDK 18 |
| **19** | JEP 424 — preview lần đầu | `java.lang.foreign` trong `java.base` | Xuất hiện `Linker`, `MemorySession`; nhiều tên và carrier type thay đổi |
| **20** | JEP 434 — preview lần hai | `java.lang.foreign` | `Arena`, `SegmentScope`; nhiều `MemoryAddress` được hợp nhất vào `MemorySegment` |
| **21** | JEP 442 — preview lần ba | `java.lang.foreign` | `Arena.ofConfined` và các factory mới; `VaList` đã bị loại bỏ |
| **22** | JEP 454 — **final/permanent** | `java.lang.foreign` | API ổn định về trạng thái preview; đổi một số tên string/allocation, thêm tra cứu C canonical layouts |
| **23+** | Các phiên bản API sau final | `java.lang.foreign` | Tiếp tục có phương thức tiện ích/thay đổi về native-access policy; không suy luận “final” nghĩa là toàn bộ API mãi bất biến |

Đây **không chỉ** là đổi một `import`. Trong một lời gọi FFM có ít nhất bốn phần cần đối chiếu theo phiên bản: **tên lớp/phương thức**, **danh sách tham số**, **kiểu trả về/`MethodHandle` carrier** và **quyền native access khi chạy**.

Ví dụ lỗi thường gặp khi copy một bài hướng dẫn viết cho JDK 21 vào JDK 22:

~~~java
// JDK 21 preview; KHÔNG phải mã JDK 22:
MemorySegment text = arena.allocateUtf8String("Hello");
String value = text.getUtf8String(0);
~~~

Viết cho JDK 22:

~~~java
// JDK 22+: hai tên mới:
MemorySegment text = arena.allocateFrom("Hello");
String value = text.getString(0);
~~~

**Cùng một mục đích** nhưng tên gọi thay đổi. Nếu không khóa JDK mục tiêu, IDE báo `cannot find symbol` dù logic chương trình đúng về mặt ý tưởng.

> **Phạm vi bài:** bản đồ những **tên phương thức cần kiểm tra** khi chuyển mã giữa các JDK 17–23 và những kiểm tra cần tiếp tục thực hiện ở JDK mới hơn. Những ví dụ gắn nhãn lịch sử là *minh họa theo phiên bản*, không phải chương trình chạy độc lập. Hai chương trình ở phần thực hành dùng **JDK 22+** và có lệnh biên dịch/chạy riêng.

## 2. Danh sách tra cứu nhanh: tên cũ, tên mới và dấu mốc

| Chức năng | Tên/cách dùng ở bản cũ | Kiểm tra/cách dùng ở bản mới | Lưu ý |
| --- | --- | --- | --- |
| Gói API | `jdk.incubator.foreign.*` (JDK 17–18) | `java.lang.foreign.*` (JDK 19+) | JDK 19–21 cần preview; JDK 22+ không |
| Lấy linker C | `CLinker.getInstance()` (JDK 17) | `Linker.nativeLinker()` (JDK 19+) | JDK 18 là incubator khác: tra đúng Javadoc 18 |
| Lookup thư viện C mặc định | `CLinker.systemLookup()` (JDK 17) | `Linker.nativeLinker().defaultLookup()` (JDK 19+) | Symbol có sẵn tùy nền tảng; không nhầm với lookup thư viện tự nạp |
| Tìm symbol trong `SymbolLookup` | `lookup("name")` (JDK 17–19) | `find("name")` (JDK 20+) | Đều cần xử lý trường hợp không tìm thấy |
| Tìm symbol hoặc ném exception | `find("name").orElseThrow()` (JDK 20–22) | `findOrThrow("name")` có từ JDK 23 | Không dùng `findOrThrow` khi còn target JDK 22 |
| Quản lý vòng đời native memory | `ResourceScope.newConfinedScope()` (JDK 17) | `MemorySession.openConfined()` (JDK 19), sau đó `Arena` | Không chỉ đổi tên class, cả contract allocation đã đổi |
| Tạo confined arena | `Arena.openConfined()` (JDK 20) | `Arena.ofConfined()` (JDK 21+) | Đổi `open...` → `of...` ở mốc 21 |
| Tạo shared arena | `Arena.openShared()` (JDK 20) | `Arena.ofShared()` (JDK 21+) | Kiểm tra ownership/confinement |
| Cấp phát vùng nhớ | `MemorySegment.allocateNative(..., scope/session)` (JDK 19–20) | `arena.allocate(...)` (JDK 21+) | Mới là instance method của allocator/arena |
| Cấp phát chuỗi C UTF-8 | `arena.allocateUtf8String(s)` (JDK 20–21) | `arena.allocateFrom(s)` (JDK 22+) | `allocateFrom` còn có overload khác, xem kiểu đối số |
| Đọc chuỗi UTF-8 từ segment | `segment.getUtf8String(offset)` (JDK 20–21) | `segment.getString(offset)` (JDK 22+) | JDK 22 có overload `getString(offset, charset)` |
| Ghi chuỗi UTF-8 vào segment | `segment.setUtf8String(offset, s)` (JDK 20–21) | `segment.setString(offset, s)` (JDK 22+) | Không tự suy byte capacity từ `String.length()` |
| Cấp phát mảng primitive | `arena.allocateArray(layout, elements...)` (JDK 20–21) | `arena.allocateFrom(layout, elements...)` (JDK 22+) | Kiểm tra overload `SegmentAllocator` |
| Biểu diễn địa chỉ | `MemoryAddress` riêng (JDK 17–19) | `MemorySegment` mô hình hóa pointer/address (JDK 20+) | Nhiều chữ ký `downcallHandle` và pointer access đổi type |
| Địa chỉ dạng số | `MemoryAddress.toRawLongValue()` ở thiết kế cũ | `MemorySegment.address()` trả `long` ở các bản hiện đại | Không được dùng địa chỉ thô sau khi memory hết vòng đời |
| Lấy kích thước/bounds và scope | `ResourceScope` / `MemorySession` / `SegmentScope` | `Arena.scope()`, `MemorySegment.scope()` (theo JDK) | `MemorySegment.Scope` là tên kiểu ở JDK 22 |
| Tạo upcall stub | `upcallStub(handle, descriptor, session)` (JDK 19) | `upcallStub(handle, descriptor, arena)` (JDK 21–22) | Đối số cuối thay đổi theo cơ chế quản lý lifetime |
| Ký phương thức downcall | `CLinker.downcallHandle(symbol, MethodType, descriptor)` (JDK 17) | `Linker.downcallHandle(symbol, descriptor, options...)` (JDK 20+) | Method type được suy ra; nhiều loại carrier thay đổi |
| Canonical C layouts | Phải tự đối chiếu ABI rõ ràng ở API preview | `linker.canonicalLayouts()` (JDK 22+) | Hữu ích cho `size_t`, `long`, `wchar_t`... |
| C variadic arguments | `VaList` có trong một số bản preview | `Linker.Option.firstVariadicArg(index)` khi dùng downcall variadic theo API mới | JDK 21 đã loại `VaList`; đừng tự map mọi varargs |

**Cách đọc bảng:** Các ô là **mốc chuyển tiếp cần kiểm tra**, không khẳng định một tên tồn tại trong mọi phiên bản của cả một khoảng khi chưa xem Javadoc của bản cụ thể. Ví dụ `CLinker.getInstance()` được nêu đúng cho JDK 17; không được copy nguyên sang JDK 18 chỉ vì cả hai đều là incubator.

Bảng dùng các tài liệu chính thức theo **versioned Javadoc** ở cuối bài. Điều tối quan trọng là đừng copy kết quả tìm kiếm Java 25 để sửa source bắt buộc chạy trên Java 21.

## 3. Đổi package và cơ chế bật tính năng: trước cả việc sửa method

### 3.1. JDK 17–18: incubator

Import kiểu cũ:

~~~java
// JDK 17 (incubator), chỉ minh họa:
import jdk.incubator.foreign.CLinker;
import jdk.incubator.foreign.MemorySegment;
import jdk.incubator.foreign.ResourceScope;
~~~

Với JDK 17 incubator, cần thêm module và native access khi chương trình sử dụng restricted operations, ví dụ:

~~~bash
# Ví dụ cú pháp cho JDK 17; không phải lệnh biên dịch file JDK 22.
javac --add-modules jdk.incubator.foreign OldFfm17.java
java --add-modules jdk.incubator.foreign \
  --enable-native-access=ALL-UNNAMED OldFfm17
~~~

Tên tệp `OldFfm17.java` ở đây **là ký hiệu ví dụ lệnh**: phần code trên không cung cấp file độc lập đó. Việc module incubator hiện lên warning không chứng minh rằng code sai.

### 3.2. JDK 19–21: preview

Import chuyển thành:

~~~java
// JDK 19–21 preview; chỉ minh họa import:
import java.lang.foreign.MemorySegment;
import java.lang.foreign.Linker;
~~~

Preview của FFM phải được bật lúc **compile** và **run**. Thay `21` bằng đúng phiên bản JDK preview mục tiêu:

~~~bash
# Ví dụ khung lệnh cho JDK 21; file Example21.java là tên giả định.
javac --enable-preview --release 21 Example21.java
java --enable-preview --enable-native-access=ALL-UNNAMED Example21
~~~

Không dùng `--release 22 --enable-preview` cho chương trình FFM đã final, vì preview của phiên bản khác không có ý nghĩa tương đương. Cũng không coi class file compile bằng JDK 21 preview có thể chạy y hệt trên JDK 22.

### 3.3. JDK 22+: final, nhưng vẫn xét native access

Từ JDK 22, FFM là API chính thức trong `java.lang.foreign`. Với chương trình chỉ cấp phát/đọc native memory theo API không restricted, thường không cần `--enable-preview`. Với chương trình tạo foreign downcall handle hoặc gọi restricted methods, **cấp native access đúng module**:

~~~bash
# Lệnh dành cho chương trình FFM JDK 22+ ở classpath:
javac FfmMigration22.java
java --enable-native-access=ALL-UNNAMED FfmMigration22
~~~

Tên file ở đây tương ứng với chương trình runnable trong phần 10.

**JDK 24+ thay đổi chính sách cảnh báo native access:** restricted operations từ module không được cấp quyền có thể phát cảnh báo theo mặc định; tùy chọn `--illegal-native-access=deny` cho phép kiểm tra chế độ chặn nghiêm ngặt. Không dùng việc “chạy được nhưng có warning” làm bằng chứng tương thích lâu dài. Với named module, bật native access cho **tên module thật** thay vì dùng `ALL-UNNAMED` tùy tiện trong production.

**Kiểm tra trước tiên:** `java -version`, `javac -version`, target JDK của build tool, module/classpath và flags. Nếu JDK thực dùng khác JDK của IDE, những lỗi `cannot find symbol` rất dễ bị chẩn đoán sai.

## 4. Tên liên quan Linker: `CLinker`, `Linker`, `downcallHandle`

### 4.1. JDK 17: `CLinker.getInstance()` và method type viết thủ công

Ví dụ **chỉ minh họa đặc trưng API JDK 17**, không phải chương trình độc lập:

~~~java
import jdk.incubator.foreign.*;
import java.lang.invoke.*;

MethodHandle strlen = CLinker.getInstance().downcallHandle(
        CLinker.systemLookup().lookup("strlen").orElseThrow(),
        MethodType.methodType(long.class, MemoryAddress.class),
        FunctionDescriptor.of(CLinker.C_LONG, CLinker.C_POINTER)
);
~~~

Ở JDK 17, người viết cung cấp `MethodType` riêng. Chữ ký `CLinker.C_LONG`, `CLinker.C_POINTER` phụ thuộc **ABI**; ví dụ `strlen` trên Linux/x64 có return `size_t` tương ứng một giá trị 64-bit. Đừng suy luận rằng Windows/x64 luôn dùng cùng layout cho `long`.

### 4.2. JDK 19: `Linker.nativeLinker()`, `SymbolLookup.lookup()`

Trong JDK 19 preview, đường gọi đã chuyển sang `Linker`:

~~~java
// JDK 19 preview, chỉ minh họa APIs theo version:
Linker linker = Linker.nativeLinker();
SymbolLookup lookup = linker.defaultLookup();
var symbol = lookup.lookup("strlen").orElseThrow();
var descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);
var handle = linker.downcallHandle(symbol, descriptor);
~~~

**Điểm không thể thay bằng search-and-replace đơn giản:** JDK 19 vẫn có các abstraction địa chỉ `MemoryAddress` và `Addressable`, trong khi JDK 20 hợp nhất vai trò đó vào `MemorySegment`. Khi gặp lỗi type ở method handle, tra kỹ carrier types theo JDK, không chỉ đổi tên phương thức `downcallHandle`.

### 4.3. JDK 20–22: `SymbolLookup.find()`

Đổi tên rõ ràng:

~~~java
// JDK 17–19:
lookup.lookup("strlen").orElseThrow();

// JDK 20–22:
lookup.find("strlen").orElseThrow();
~~~

Đến JDK 23, `SymbolLookup` cung cấp thêm phương thức tiện ích:

~~~java
// JDK 23+:
MemorySegment symbol = lookup.findOrThrow("strlen");
~~~

`findOrThrow` **không phải alias để dùng cho JDK 22**. Nếu thư viện còn hỗ trợ JDK 22, giữ `find("name").orElseThrow()`. Cũng không đảo chiều `find` → `lookup` khi đi từ 21 sang 22: `find` đã dùng từ 20.

### 4.4. Bound và unbound downcall method handles

Với API JDK 22, linker có hai dạng liên kết:

~~~java
// Minh họa APIs JDK 22+; linker, symbol, descriptor đã có.
MethodHandle bound = linker.downcallHandle(symbol, descriptor);
MethodHandle unbound = linker.downcallHandle(descriptor);
~~~

- `bound` có **địa chỉ hàm cố định** trong handle, tham số lúc invoke chỉ là tham số C của function (và có thể thêm allocator cho struct-return theo ABI).
- `unbound` yêu cầu thêm đối số **`MemorySegment` địa chỉ symbol** lúc invoke. Đừng gọi một handle unbound với danh sách đối số dành cho bound handle.
- `MethodHandle.invokeExact` kiểm tra chữ ký method handle rất chặt; chuyển type từ `MemoryAddress` sang `MemorySegment`, từ `int` sang `long` hoặc đổi return carrier sẽ gây `WrongMethodTypeException` nếu invoke không khớp.
- `FunctionDescriptor.ofVoid(...)` dùng khi native function trả `void`; `FunctionDescriptor.of(returnLayout, argLayouts...)` cho function có return value.
- Đối với callback/upcall, `Linker.upcallStub` cũng có signature và quy tắc lifetime phụ thuộc JDK, xem phần 9.

## 5. Tên liên quan SymbolLookup và nạp thư viện

Cần phân biệt hai việc:

1. **Tìm symbol ở các thư viện mặc định** do ABI/linker cung cấp (ví dụ các hàm libc sẵn có): `linker.defaultLookup()`.
2. **Mở một thư viện riêng** rồi tìm symbol ở đó: `SymbolLookup.libraryLookup(..., arena)` trong API hiện đại.

Ví dụ JDK 22:

~~~java
// Minh họa, không phải runnable độc lập:
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup custom = SymbolLookup.libraryLookup(
            "mynative", arena);
    MemorySegment symbol = custom.find("my_function").orElseThrow();
}
~~~

Tên `"mynative"` trong ví dụ chỉ là minh họa; thư viện thật có thể cần full path hoặc tên native OS (`.so`/`.dll`/`.dylib`), tùy cách `libraryLookup` yêu cầu. **Không giả định** tên cho `System.loadLibrary` và tên cho `libraryLookup` có cùng quy tắc tìm kiếm. Tham số `Arena` xác định lifetime của lookup/thư viện được nạp qua API, nên **không được giữ pointer symbol rồi dùng sau khi arena bị close**.

Các phương thức cần kiểm:

| API | Tên cần kiểm | Tại sao |
| --- | --- | --- |
| System/default symbols | `CLinker.systemLookup` (17) → `Linker.defaultLookup` (19+) | Chuyển trách nhiệm từ `CLinker` sang native linker |
| Loader lookup | `SymbolLookup.loaderLookup()` | Tìm symbol trong thư viện liên quan class loader, không phải mọi library |
| Tìm symbol | `lookup(name)` → `find(name)` | Dấu mốc JDK 20 |
| Not-found shortcut | `findOrThrow(name)` | Chỉ có từ JDK 23; JDK 22 phải dùng `find(...).orElseThrow()` |
| Explicit library | `libraryLookup(name/path, session/scope/arena)` | Kiểu đối số quản lý lifetime thay đổi theo các đời FFM |
| Nạp classpath JNI library | `System.loadLibrary(logicalName)` | Là API Java/JNI cũ, **không** đổi thành `libraryLookup` một cách máy móc |

**Không coi một `MemorySegment` chứa function address là vùng nhớ dữ liệu có thể đọc trực tiếp.** Native symbol lookup trả segment biểu diễn địa chỉ; ở thiết kế hiện đại nó thường có kích thước 0. Dùng với `downcallHandle` thay vì đọc byte từ đó; nếu cần dereference memory ngoài, phải biết bounds/lifetime thực và sử dụng API restricted đúng quy định.

## 6. Tên về lifetime: `ResourceScope` → `MemorySession` → `Arena`

### 6.1. JDK 17

~~~java
// JDK 17 incubator, minh họa: chỉ một cấu trúc vòng đời.
try (ResourceScope scope = ResourceScope.newConfinedScope()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, scope);
    // dùng nativeMemory trong phạm vi scope hợp lệ
}
~~~

`ResourceScope` quản lý lúc memory segment trở nên không hợp lệ. Việc copy `ResourceScope.newConfinedScope()` vào JDK 22 sẽ thất bại vì class này đã không còn thuộc API hiện đại.

### 6.2. JDK 19

~~~java
// JDK 19 preview, minh họa:
try (MemorySession session = MemorySession.openConfined()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, session);
}
~~~

`MemorySession` thay thế mô hình scope cũ ở JDK 19. Không thể giả định `session` có mọi method trùng với `ResourceScope`.

### 6.3. JDK 20

~~~java
// JDK 20 preview, minh họa:
try (Arena arena = Arena.openConfined()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, arena.scope());
}
~~~

Đây là giai đoạn `Arena` và `SegmentScope` tách biệt trong API, và `Arena.openConfined()` là tên factory. **Nó không phải `Arena.ofConfined()` của JDK 21.**

### 6.4. JDK 21–22+

~~~java
// JDK 21 preview hoặc JDK 22+ final:
try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeMemory = arena.allocate(16);
    nativeMemory.set(ValueLayout.JAVA_INT, 0, 7);
}
~~~

Kiểu API này ngắn gọn hơn: `Arena` vừa là nơi cấp phát vừa kiểm soát lifetime. Ở JDK 22, `arena.allocate(ValueLayout.JAVA_INT)` cũng dùng được khi muốn cấp phát đúng một primitive layout.

Các factory cần phân biệt:

| Factory JDK 21+ | Lifetime/đặc điểm | Khi nên cân nhắc |
| --- | --- | --- |
| `Arena.ofConfined()` | Close tường minh; truy cập trong owner thread | Tác vụ ngắn trên một thread, dùng try-with-resources |
| `Arena.ofShared()` | Close tường minh; có thể truy cập từ nhiều thread | Chia sẻ segment có hợp đồng đồng bộ |
| `Arena.ofAuto()` | Lifetime tự động do GC quản lý | Không cần giải phóng theo thời điểm tuyệt đối; chấp nhận tính bất định |
| `Arena.global()` | Lifetime không giới hạn, không close | Chỉ khi chủ ý giữ memory tồn tại tới cuối process |

**Không chỉ đổi tên factory rồi bỏ qua thread ownership.** `Arena.ofConfined()` không cho thread khác tùy ý đọc segment; `Arena.ofShared()` cho phép truy cập nhưng không tự khiến dữ liệu mutable trở thành thread-safe. Khi segment đã bị close, đọc/ghi có thể ném `IllegalStateException`.

## 7. Tên API về chuỗi và mảng native — điểm đổi nổi bật ở JDK 22

### 7.1. C-string: allocation và đọc/ghi

Bản JDK 20–21:

~~~java
// JDK 20–21 preview; không biên dịch y hệt trên 22:
MemorySegment cString = arena.allocateUtf8String("hello");
String value = cString.getUtf8String(0);
cString.setUtf8String(0, "hi");
~~~

Bản JDK 22+:

~~~java
// JDK 22+:
MemorySegment cString = arena.allocateFrom("hello");
String value = cString.getString(0);
cString.setString(0, "hi");
~~~

**Lưu ý về kích thước:** Sau `allocateFrom("hello")`, buffer chỉ được cấp phát theo kích thước cần cho `"hello"` cộng terminator. `setString(0, ...)` với chuỗi dài hơn kích thước buffer có thể lỗi bounds. Không có chuyện một String Java 10 UTF-16 units luôn tốn đúng 11 byte C-string UTF-8: số byte phụ thuộc mã hóa, đặc biệt với dấu tiếng Việt và emoji.

JDK 22 cung cấp overload nhận `Charset` như `arena.allocateFrom(text, charset)`, `segment.getString(offset, charset)` và `segment.setString(offset, text, charset)`. Vì vậy thay tên không đồng nghĩa bỏ qua quy định encoding, byte order hoặc null terminator.

### 7.2. Native arrays

JDK 21:

~~~java
// JDK 21 preview, minh họa method naming:
MemorySegment values = arena.allocateArray(
        ValueLayout.JAVA_INT, 2, 3, 5);
~~~

JDK 22+:

~~~java
// JDK 22+:
MemorySegment values = arena.allocateFrom(
        ValueLayout.JAVA_INT, 2, 3, 5);
~~~

Đọc bằng API giữ ổn định về ý tưởng:

~~~java
// Minh họa kiểu API JDK 22+:
int first = values.getAtIndex(ValueLayout.JAVA_INT, 0);
int third = values.getAtIndex(ValueLayout.JAVA_INT, 2);
~~~

Kiểm tra overload `allocateFrom` với mảng `int[]`, varargs `int...` và loại layout cụ thể. Một lần đổi signature có thể khiến lời gọi bị chọn nhầm overload hoặc không match generics/carrier, kể cả khi code vẫn “trông giống”.

### 7.3. Dữ liệu native và Java heap không giống nhau

`arena.allocateFrom` tạo **native memory copy** của dữ liệu theo hợp đồng allocator; nó không biến Java array thành native array zero-copy. `MemorySegment.ofArray(int[])` tạo **heap segment** khác về native status và mức alignment; không được truyền bất kỳ heap segment nào tới C function đòi pointer native mà không kiểm tra hợp đồng `Linker`.

## 8. `MemoryAddress` và `MemorySegment`: không phải chỉ thay tên type

Ở các API cũ, `MemoryAddress` là abstraction riêng. Từ JDK 20 preview, pointer/address được mô hình hóa bằng `MemorySegment`. Điều này ảnh hưởng:

- Giá trị trả về của `SymbolLookup.find`: với API hiện đại là `Optional<MemorySegment>`.
- Carrier type của downcall handle đối với con trỏ C: `MemorySegment` chứ không phải `MemoryAddress`.
- Đọc/ghi pointer từ memory: dùng `ValueLayout.ADDRESS` và `MemorySegment.get/set`.
- Tạo address từ `long` trong JDK 22: `MemorySegment.ofAddress(address)` tạo zero-length segment.
- Thao tác `segment.address()` ở JDK 22 trả một `long`; đây là **địa chỉ thô**, không có nghĩa sở hữu vùng nhớ.
- `MemorySegment.NULL` là constant để biểu diễn địa chỉ null ở API hiện đại.

Ví dụ JDK 22:

~~~java
// Minh họa; chưa đầy đủ khai báo symbol và phạm vi.
MemorySegment pointer = MemorySegment.ofAddress(0x1000L);
long raw = pointer.address();       // 4096
long size = pointer.byteSize();     // 0
~~~

**Không dereference** ví dụ này: `0x1000L` được chọn chỉ để minh họa biểu diễn số, **không** khẳng định địa chỉ này có vùng nhớ hợp lệ. Đọc `pointer.get(ValueLayout.JAVA_BYTE, 0)` sẽ vướng bounds của zero-length segment; tự gọi `reinterpret` với độ dài bịa đặt có thể tạo memory access không an toàn và crash JVM.

### `reinterpret` và target layout là restricted operations

JDK 22 có `segment.reinterpret(newSize)`, các overload gắn lifetime với `Arena` và `AddressLayout.withTargetLayout(...)`. Đây là các API **restricted** bởi việc tự gán bounds/lifetime cho pointer vốn không được JVM kiểm chứng. Chỉ dùng khi biết chắc memory được cấp phát ở đâu, kích thước thật bao nhiêu, ai giải phóng và lúc nào.

Đổi code `MemoryAddress.asSegment(...)` ở thiết kế cũ thành `MemorySegment.ofAddress(...).reinterpret(...)` **không** phải phép đổi tên “an toàn tự động”; phải kiểm tra lại native ownership, offset, bounds, scope và native access policy.

## 9. `upcallStub`, variadic functions và `FunctionDescriptor`

### 9.1. `upcallStub`: kiểm tra kiểu đối số cuối

Một callback Java được native code gọi qua function pointer (upcall) cần một `MethodHandle` phù hợp với `FunctionDescriptor` và một cách giữ stub sống đủ lâu.

Ví dụ API hiện đại:

~~~java
// JDK 22+; minh họa, handle/descriptor/linker đã có:
try (Arena arena = Arena.ofConfined()) {
    MemorySegment stub = linker.upcallStub(
            handle, descriptor, arena);
    // Chỉ đưa stub cho native code còn dùng trong lifetime của arena.
}
~~~

Trong JDK 19, đối số cuối của `upcallStub` có thể là `MemorySession`; trong JDK 20 là `SegmentScope` (thường `arena.scope()`); JDK 21–22 gắn với `Arena`. Nếu chỉ search-and-replace `MemorySession` → `Arena` mà giữ `session`/`scope` như cũ, code có thể sai signature hoặc sai lifetime.

**Cảnh báo:** Native function pointer tới stub không được giữ và gọi sau khi arena giải phóng stub. Callback target method handle phải có carrier types và behavior đúng ABI; exception Java vượt ra khỏi upcall không có cách xử lý tùy ý như Java-to-Java call.

### 9.2. Variadic arguments: `VaList` không phải phương án mặc định cho JDK 21+

Các code mẫu preview cũ có thể nhắc `VaList`. JDK 21 đã loại `VaList` khỏi API. Với C variadic function như `printf(const char*, ...)`, API hiện đại dùng **chữ ký callsite cụ thể** và đánh dấu vị trí argument biến đổi:

~~~java
// JDK 22+; snippet minh họa, không tự gọi printf:
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

var option = Linker.Option.firstVariadicArg(1);
~~~

Đánh dấu index **theo số thứ tự argument của descriptor bắt đầu từ 0**. Với `printf`, argument đầu tiên là format pointer (index 0), số nguyên đầu tiên ở index 1 là variadic. Các quy tắc default argument promotion của C phải được xem xét; FFM linker không tự có quyền đoán mọi ABI signature. Đổi tên API không bảo đảm gọi variadic function an toàn.

### 9.3. `FunctionDescriptor` và canonical C types

`FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)` là ví dụ mô tả `size_t strlen(const char*)` trên **Linux/x64**: `size_t` là 64-bit. Trên hệ 32-bit, return layout có thể khác. Với C `long`, Linux/x64 thường 64-bit nhưng Windows/x64 thường 32-bit.

Từ JDK 22, `linker.canonicalLayouts()` trả ánh xạ canonical C ABI type names sang `MemoryLayout`:

~~~java
// JDK 22+, ví dụ kiểm tra thay vì tự suy size_t:
MemoryLayout sizeT = Linker.nativeLinker()
        .canonicalLayouts()
        .get("size_t");
~~~

Một thư viện đa nền tảng cần xây dựng descriptor dựa trên C header thực tế và ABI tương ứng. Đừng dùng `ValueLayout.JAVA_LONG` để thay thế máy móc cho mọi `long`/`size_t` chỉ vì ví dụ chạy đúng trên máy phát triển.

## 10. Ví dụ chạy hoàn chỉnh, JDK 22+: cấp phát và đọc/ghi native memory

Tạo file **`FfmMigration22.java`** với nội dung sau. Đây là chương trình **độc lập**, chỉ cần **JDK 22 trở lên**, không cần thư viện C riêng, không dùng API preview và không yêu cầu phương thức restricted.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class FfmMigration22 {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {

            MemorySegment number =
                    arena.allocate(ValueLayout.JAVA_INT);
            number.set(ValueLayout.JAVA_INT, 0, 42);

            MemorySegment word =
                    arena.allocateFrom("Java FFM");

            MemorySegment values =
                    arena.allocateFrom(
                            ValueLayout.JAVA_INT, 2, 3, 5);

            System.out.println(
                    "number=" + number.get(
                            ValueLayout.JAVA_INT, 0));
            System.out.println(
                    "word=" + word.getString(0));
            System.out.println(
                    "sum=" + (
                            values.getAtIndex(
                                    ValueLayout.JAVA_INT, 0)
                            + values.getAtIndex(
                                    ValueLayout.JAVA_INT, 1)
                            + values.getAtIndex(
                                    ValueLayout.JAVA_INT, 2)));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FfmMigration22.java
java FfmMigration22
~~~

**Stdout chính xác**:

~~~text
number=42
word=Java FFM
sum=10
~~~

Tại sao dùng các tên này:

- `Arena.ofConfined()`: factory của JDK 21+, vẫn hợp lệ ở 22.
- `arena.allocate(ValueLayout.JAVA_INT)`: cấp phát một vùng theo layout `int`.
- `arena.allocateFrom("Java FFM")`: API tạo C string kiểu mới từ JDK 22.
- `arena.allocateFrom(ValueLayout.JAVA_INT, 2, 3, 5)`: API cấp phát native int array từ JDK 22.
- `word.getString(0)`: API đọc chuỗi mới từ JDK 22; không dùng `getUtf8String` kiểu preview.
- `number.get(...)`, `number.set(...)`, `values.getAtIndex(...)`: truy cập segment theo layout, offset/index hợp lệ.
- `try (Arena arena = ...)`: hết block thì memory backing các segment được cấp phát qua arena bị giải phóng.

Chương trình không gọi native linker, nên không nhất thiết cần `--enable-native-access` trong những JDK nơi các phương thức dùng ở đây không bị restricted. Nếu trộn thêm `Linker.downcallHandle` hoặc `reinterpret`, hãy kiểm tra quyền native access của module.

## 11. Ví dụ chạy hoàn chỉnh: gọi `strlen` bằng FFM trên Linux/x64, JDK 22+

Ví dụ này dành cho nền tảng **Linux/x64 với libc cung cấp `strlen` qua default lookup**. Trên ABI đó, `size_t` dài 64 bit, vì vậy có thể mô tả return type bằng `ValueLayout.JAVA_LONG`. Đây là ví dụ đối chiếu tên method khi chuyển từ JDK 21 sang 22.

Tạo file **`FfmStrlen22.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class FfmStrlen22 {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MemorySegment symbol = linker.defaultLookup()
                .find("strlen")
                .orElseThrow();

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cText = arena.allocateFrom("FFM 22");

            long bytes = (long) strlen.invokeExact(cText);

            System.out.println("bytes=" + bytes);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FfmStrlen22.java
java --enable-native-access=ALL-UNNAMED FfmStrlen22
~~~

**Stdout trên Linux/x64 khi `strlen` được tìm thấy và native access đã bật:**

~~~text
bytes=6
~~~

Đường đi của dữ liệu:

1. `Linker.nativeLinker()` chọn linker theo ABI của JVM hiện tại.
2. `linker.defaultLookup().find("strlen").orElseThrow()` lấy địa chỉ hàm C. Tên `find` đúng cho JDK 22; `lookup` sẽ không compile.
3. `FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)` mô tả return `size_t` và tham số `const char*` theo ABI Linux/x64.
4. `downcallHandle(symbol, descriptor)` trả MethodHandle đã bind địa chỉ function, do đó `invokeExact(cText)` có **một** argument kiểu `MemorySegment`.
5. `arena.allocateFrom("FFM 22")` tạo buffer UTF-8 kết thúc NUL. `strlen` đếm byte trước NUL, trả `6`.
6. Hết `try-with-resources`, arena close và buffer không còn được phép dùng. Không giữ segment cho native code sau thời điểm này.

Nếu triển khai trên Windows/x64 hoặc ABI khác, **đừng** giữ `ValueLayout.JAVA_LONG` cho return của C function mà không kiểm tra C ABI; cũng đừng giả định default lookup luôn expose `strlen` trên mọi hệ điều hành. Chương trình này là runnable **theo môi trường đã nêu**, không phải lời hứa đa nền tảng vô điều kiện.

### 11.1. Nếu nâng target tối thiểu lên JDK 23

Có thể thay:

~~~java
// JDK 22:
MemorySegment symbol = linker.defaultLookup()
        .find("strlen").orElseThrow();

// JDK 23+:
MemorySegment symbol = linker.defaultLookup()
        .findOrThrow("strlen");
~~~

Nếu dự án là thư viện còn phải chạy ở JDK 22, giữ biến thể đầu. `findOrThrow` là ví dụ điển hình của **method mới được bổ sung**, không phải breaking rename của `find`.

## 12. Cách xác minh tên phương thức bằng đúng Javadoc

Khi dự án chuyển từ **version A → version B**, áp dụng quy trình sau thay vì thay tên theo trực giác.

### Bước 1: khóa version và cách chạy

~~~bash
java -version
javac -version
~~~

Đối chiếu thêm `maven.compiler.release` / `--release` / Gradle Java toolchain / IDE Project SDK và module-path. Không đủ nếu chỉ biết JDK cài trên máy: CI có thể dùng JDK khác.

### Bước 2: tra **từng lớp trong đúng Javadoc của bản đích**

Các URL có cấu trúc cố định:

~~~text
https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/jdk/incubator/foreign/CLinker.html
https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/MemorySession.html
https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/Arena.html
https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html
https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html
https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/lang/foreign/SymbolLookup.html
~~~

Trong Javadoc đích, nhìn **Method Summary** rồi **Method Details**, đặc biệt phần `Since`, `Preview`, `Restricted`, `Parameters`, `Returns`, `Throws`. Nếu một tên chỉ có từ bản sau, không dùng cho binary/source target bản trước.

### Bước 3: so sánh **full signature**, không chỉ identifier

Ví dụ danh sách cần ghi vào review:

~~~text
Class/interface:
  SymbolLookup            java.lang.foreign.SymbolLookup
Name:
  find                    (JDK 20+)
Parameters:
  String
Return type:
  Optional<MemorySegment>
Error behavior:
  optional empty nếu không thấy symbol
Replacement/API convenience:
  findOrThrow             (JDK 23+)
~~~

Ví dụ khác: `Linker.downcallHandle` có overload bound và unbound; đổi từ `Addressable` sang `MemorySegment` làm thay đổi kiểu parameter của `MethodHandle`. Chỉ thấy method tên giống nhau **không đủ** để kết luận code portable.

### Bước 4: kiểm tra các yếu tố **ngoài Java method names**

- ABI: `sizeof(long)`, `sizeof(size_t)`, alignment và calling convention.
- Native library: tên file, platform loading/lookup, symbol visibility.
- Lifetime: arena/session/scope có còn sống khi native dùng pointer không?
- Thread confinement: segment của confined arena được dùng đúng thread không?
- Restricted API: flags/native access/preview và module có đúng không?
- Encoding: UTF-8 bytes, NUL terminator, buffer size.
- Pointer bounds: zero-length segment, `reinterpret`, return pointer được ai cấp phát/`free`?

### Bước 5: compile và test trên **từng JDK được cam kết hỗ trợ**

Thư viện muốn hỗ trợ JDK 21 và 22 cần ít nhất hai build/test profiles hoặc hai source-set/adapters với đúng API. Do JDK 21 dùng preview, không phải “compile once” đảm bảo nhảy sang final API 22; những lỗi không compile là tín hiệu phải cập nhật contract, không phải chỉnh flags lung tung.

## 13. Lỗi thường gặp khi chuyển FFM và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Cần kiểm tra/sửa |
| --- | --- | --- |
| `package jdk.incubator.foreign does not exist` | Dùng import incubator với JDK đã bỏ module, hoặc chưa add module cũ | Đối chiếu target JDK và package; 19+ dùng `java.lang.foreign` |
| `package java.lang.foreign does not exist` | Compile với JDK 17/18 hoặc JDK thực không đúng | Kiểm tra `javac -version`; không thể chỉ thêm import để có API |
| `cannot find symbol: method lookup(String)` | Đem `SymbolLookup.lookup` của 17–19 sang 20+ | Dùng `find` (hoặc `findOrThrow` ở 23+) |
| `cannot find symbol: method findOrThrow` | Dùng method tiện ích JDK 23 trong target JDK 22 | Thay bằng `find(...).orElseThrow()` |
| `cannot find symbol: method openConfined` | Dùng `Arena.openConfined` JDK 20 trên JDK 21/22 | Thay bằng `Arena.ofConfined` |
| `cannot find symbol: method allocateUtf8String` | Dùng tên allocation cũ của JDK 20/21 trên JDK 22 | `arena.allocateFrom(text)` |
| `cannot find symbol: method getUtf8String` | Dùng tên đọc chuỗi JDK 20/21 trên JDK 22 | `segment.getString(offset)` |
| `cannot find symbol: method allocateArray` | Dùng `SegmentAllocator.allocateArray` preview trên JDK 22 | `arena.allocateFrom(layout, values...)` |
| `cannot find symbol: method allocateNative` | Dùng static `MemorySegment.allocateNative` cũ với API mới | Chuyển sang `arena.allocate(...)` |
| `cannot find symbol: class VaList` | JDK 21 đã loại bỏ abstraction `VaList` preview | Thiết kế descriptor và `Linker.Option.firstVariadicArg` theo target ABI |
| `method downcallHandle cannot be applied` | Kiểu symbol/descriptor/options hoặc overload khác phiên bản | Đối chiếu bound/unbound, `MemorySegment` carrier và signature thật |
| `WrongMethodTypeException` | `invokeExact` không đúng carrier/arity/return Java method handle | Kiểm tra descriptor, argument list, cast return và `MethodHandle.type()` |
| `IllegalCallerException` | Restricted native-access operation không được cấp quyền | Bật native access đúng module/flag theo JDK |
| Runtime warning về restricted/native access | JDK mới báo module đang dùng native APIs | Bật `--enable-native-access`; thử `--illegal-native-access=deny` trên JDK hỗ trợ |
| `NoSuchElementException` ở symbol lookup | Thư viện/symbol không được expose trên OS/ABI | Phân biệt `defaultLookup` với `libraryLookup`; kiểm tra symbol thật |
| `IllegalStateException` khi access segment | Arena/scope đã đóng | Không giữ segment/pointer ngoài lifetime |
| `WrongThreadException` | Confined arena dùng sai owner thread | Thiết kế shared arena hoặc di chuyển công việc về owner thread |
| Native crash dù Java biên dịch | Descriptor sai C ABI, lifetime/pointer/bounds sai | Kiểm tra C header, canonical layouts, ownership; không chỉ sửa method name |

**Không sửa một native crash bằng cách đổi `invokeExact` sang `invoke` mà không hiểu signature.** `invoke` có thể thực hiện một số phép chuyển đổi theo MethodHandle rules, nhưng không chứng minh ABI của C đúng. FFM vẫn cho phép unsafe native calls và có thể làm JVM crash nếu descriptor sai.

## 14. Checklist đối chiếu mã nguồn FFM trước khi merge

Có thể dùng checklist này cho mỗi PR nâng Java:

- [ ] Đã ghi **source JDK**, **target JDK**, OS/ABI và API stage (incubator/preview/final)?
- [ ] Đã thay `jdk.incubator.foreign` bằng `java.lang.foreign` nếu qua mốc 19?
- [ ] `CLinker`/`Linker.nativeLinker` được dùng đúng version?
- [ ] `CLinker.systemLookup`/`Linker.defaultLookup` và `SymbolLookup.loaderLookup/libraryLookup` có đúng phạm vi?
- [ ] `SymbolLookup.lookup`, `find` và `findOrThrow` có đúng mốc phiên bản?
- [ ] `ResourceScope`/`MemorySession`/`Arena` cùng `scope()` đã được kiểm tra lại?
- [ ] `Arena.openConfined` ↔ `Arena.ofConfined` không bị trộn?
- [ ] `MemorySegment.allocateNative`/`arena.allocate` đã đổi đúng chữ ký?
- [ ] `allocateUtf8String` ↔ `allocateFrom(String)` và `getUtf8String` ↔ `getString` đã được sửa đúng?
- [ ] `allocateArray` ↔ `allocateFrom(layout, values...)` đúng overload?
- [ ] `MemoryAddress`/`Addressable` → `MemorySegment` và carrier types của method handles đã được đối chiếu?
- [ ] `upcallStub` có đúng đối số lifetime `session/scope/arena` của target?
- [ ] Nếu dùng `VaList` hoặc variadic C call, đã kiểm tra `Linker.Option.firstVariadicArg` và promotions?
- [ ] `FunctionDescriptor`, C ABI, `canonicalLayouts` và return/argument widths đã khớp platform?
- [ ] Không gọi `reinterpret` hay giữ pointer ngoài lifetime mà thiếu quyền/ownership?
- [ ] Compiler flags preview/incubator/native access và Maven/Gradle toolchain đúng phiên bản?
- [ ] Đã chạy **compile + test** bằng chính JDK thấp nhất được hỗ trợ, không chỉ bản mới nhất?

## 15. Câu hỏi ôn tập

1. Vì sao một dự án dùng `CLinker.getInstance()` từ JDK 17 không thể chỉ đổi Java compiler flag để chạy FFM API final JDK 22?
2. Trong các JDK 19, 20 và 22, phương thức nào dùng để tra một symbol từ `SymbolLookup`?
3. Khi target tối thiểu là JDK 22, có thể dùng `findOrThrow("strlen")` không? Tại sao?
4. Factory tạo confined arena đổi tên giữa JDK 20 và 21 như thế nào?
5. Khi nâng từ JDK 21 preview sang 22 final, cần đổi `allocateUtf8String`, `getUtf8String` và `allocateArray` thành gì?
6. Tại sao `MemorySegment.allocateNative` của JDK 19/20 không thể được thay bằng một `new MemorySegment(...)` tùy ý ở JDK 22?
7. Vì sao `MemoryAddress` và `MemorySegment` không thể được thay thế trong `MethodHandle.invokeExact` mà không xem carrier type?
8. `Linker.downcallHandle(symbol, descriptor)` khác `Linker.downcallHandle(descriptor)` về tham số lúc invoke như thế nào?
9. Nếu mã JDK 22 gọi `strlen` trên Linux/x64 thì return C `size_t` thường ánh xạ sang layout nào? Có được áp dụng máy móc sang Windows/x64 hoặc 32-bit không?
10. Khi nâng từ JDK 21 lên 22, còn cần `--enable-preview` không? Thế còn `--enable-native-access` cho restricted downcall?
11. Tại sao địa chỉ tạo bởi `MemorySegment.ofAddress(0x1000L)` không tự động an toàn để dereference?
12. Khi thấy `IllegalCallerException` hoặc native-access warning, cần phân biệt điều gì với lỗi `cannot find symbol`?

**Đáp án gợi ý:** (1) package/classes và signatures đã đổi qua nhiều lần thiết kế; (2) 19 `lookup`, 20 và 22 `find`; (3) không, API tiện ích có từ 23, 22 dùng `find(...).orElseThrow()`; (4) `openConfined` → `ofConfined`; (5) `allocateFrom`, `getString` và `allocateFrom(layout, values...)`; (6) allocation đi qua `Arena/SegmentAllocator` và quản lý lifetime; (7) địa chỉ/handle Java method type thay đổi, `invokeExact` cần signature chính xác; (8) unbound có thêm argument địa chỉ hàm; (9) `JAVA_LONG` ở Linux/x64, phải xem ABI máy khác; (10) không cần preview cho API final, nhưng restricted FFM vẫn cần native access đúng module; (11) chưa biết bounds, lifetime và ownership; (12) lỗi quyền native khác lỗi thiếu tên method/lookup symbol.

## 16. Tài liệu tham khảo theo đúng phiên bản

**JEPs chính thức:**

- [JEP 412 — Foreign Function & Memory API (Incubator), JDK 17](https://openjdk.org/jeps/412)
- [JEP 419 — Foreign Function & Memory API (Second Incubator), JDK 18](https://openjdk.org/jeps/419)
- [JEP 424 — Foreign Function & Memory API (Preview), JDK 19](https://openjdk.org/jeps/424)
- [JEP 434 — Foreign Function & Memory API (Second Preview), JDK 20](https://openjdk.org/jeps/434)
- [JEP 442 — Foreign Function & Memory API (Third Preview), JDK 21](https://openjdk.org/jeps/442)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)

**Versioned API/Javadoc:**

- [JDK 17 `CLinker` và `SymbolLookup`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/jdk/incubator/foreign/CLinker.html)
- [JDK 19 `MemorySession`](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/MemorySession.html)
- [JDK 19 `SymbolLookup`](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 20 `Arena`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 20 `SymbolLookup`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 21 `Arena` và các factory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 22 `SegmentAllocator`: `allocateFrom`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
- [JDK 22 `MemorySegment`: `getString`/`setString`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [JDK 22 `Linker`: `canonicalLayouts` và downcalls](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [JDK 23 `SymbolLookup`: `findOrThrow`](https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 25 — Restricted Methods và Native Access](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)

**Kết luận:** Khi chuyển mã FFM, không có một phép “đổi tên hàng loạt” an toàn. Hãy **khóa JDK target**, đối chiếu từng symbol theo **versioned Javadoc**, kiểm tra **đầy đủ signature + carrier + lifetime + ABI + flags**, sau đó biên dịch/chạy bằng chính JDK đó. Những tên đặc biệt dễ nhầm là `SymbolLookup.lookup/find/findOrThrow`, `Arena.openConfined/ofConfined`, `MemorySegment.allocateNative/Arena.allocate`, `allocateUtf8String/allocateFrom`, `getUtf8String/getString` và `CLinker/Linker`.
