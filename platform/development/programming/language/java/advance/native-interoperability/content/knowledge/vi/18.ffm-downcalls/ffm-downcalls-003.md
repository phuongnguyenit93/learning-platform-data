# Chọn Arena cho thời gian sống của thư viện và địa chỉ ký hiệu

## 1. Bài toán: có địa chỉ hàm native rồi, khi nào địa chỉ ấy hết hiệu lực?

Trong **Java Advance – native-interoperability**, chủ đề **Gọi hàm bằng FFM**, Java có thể nạp thư viện native bằng `SymbolLookup.libraryLookup(...)`, tìm một symbol như `abs` hoặc `strlen` và tạo `MethodHandle` qua `Linker.nativeLinker()`. Điều nguy hiểm là **một `MethodHandle` còn tồn tại trong Java không chứng minh function code mà nó trỏ tới vẫn đang được nạp**, và một địa chỉ symbol có kiểu `MemorySegment` không có nghĩa được phép sử dụng ngoài scope của nó.

Bài này trả lời đúng câu hỏi: **chọn loại `Arena` nào để quản lý thời gian sống của thư viện native và những địa chỉ ký hiệu lấy từ thư viện đó?** Cụ thể:

- `Arena` được truyền vào `SymbolLookup.libraryLookup(nameOrPath, arena)` kiểm soát **lifetime của library lookup**, liên quan đến việc **nạp / có thể dỡ thư viện** và tính hợp lệ của symbol addresses.
- Một `MemorySegment` biểu diễn **địa chỉ symbol** thường có `byteSize() == 0`. Nó dùng làm function address cho linker, **không phải bộ đệm dữ liệu 0 byte có thể đọc tùy ý**.
- `Arena.ofConfined()` phù hợp nếu chính **một thread** thực hiện các downcalls và đóng owner; `Arena.ofShared()` phù hợp cho một **library binding được nhiều thread dùng chung** với giao thức shutdown rõ ràng.
- `Arena.ofAuto()` và `Arena.global()` không có **thời điểm đóng tường minh** để phản ánh một session cần unload đúng lúc; dùng chúng chỉ khi thật sự có hợp đồng lifetime thích hợp.
- **Arena của thư viện** và **arena cấp chuỗi/mảng/native buffers cho từng lời gọi** không nhất thiết là một. Buffer input có thể kết thúc sau downcall đồng bộ, trong khi symbol và library phải sống qua nhiều lời gọi.
- Khi Java đóng arena, không gọi lại `MethodHandle`/function pointer gắn với library ấy; **không chạy thử use-after-unload** vì có thể crash JVM thay vì ném exception dễ bắt.

Hai chương trình Java đầy đủ bên dưới đã được biên dịch bằng `javac --release 22` và chạy trên **JDK 24 / Windows x64**. Chúng dùng FFM **chính thức từ JDK 22**, không cần JNI glue code. Ví dụ chính gọi C runtime functions thông qua library lookup; ví dụ thứ hai quản lý thư viện dùng đồng thời bởi hai worker threads và explicit close.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `SymbolLookup.libraryLookup` với `linker.defaultLookup()` và `SymbolLookup.loaderLookup()` về nguồn symbol và lifetime.
2. Giải thích `Arena` nào giữ thư viện tồn tại, `MemorySegment` nào chỉ là địa chỉ symbol, `MethodHandle` nào dùng để gọi.
3. Chọn `ofConfined` hoặc `ofShared` đúng nhu cầu single-thread/multi-thread; tránh dùng `global/auto` để né thiết kế shutdown.
4. Tách lifetime **library / symbol address / downcall handle / call arguments / callback stub**.
5. Thiết kế `OPEN → CLOSING → CLOSED` sao cho không có in-flight foreign call khi unload.
6. Xử lý các lỗi thiếu thư viện, thiếu symbol, permission native access, sai ABI, sai thread, dùng địa chỉ hết hạn và đóng arena hai lần.
7. Viết và chạy một chương trình Java 22+ có kiểm tra chính xác state của scope **trước/sau close** mà **không gọi hàm native sau close**.

## 2. Bức tranh ownership: thư viện khác với bộ nhớ tham số

Hãy xem đường đi từ Java tới C:

~~~text
                 Java application
                         |
                +--------+-----------+
                |                    |
         BINDING / LIBRARY       MỘT LỜI GỌI
                |                    |
       Arena libraryArena      Arena callArena
         (lifetime dài)          (lifetime ngắn)
                |                    |
         SymbolLookup              allocateFrom("...")
         .libraryLookup              |
                |                 MemorySegment (C char*)
         find("strlen")              |
                |                    |
        MemorySegment symbol         |
        (địa chỉ hàm, size 0)         |
                |                    |
      Linker.downcallHandle          |
                |                    |
            MethodHandle ----------> C strlen(char*)
                |                    |
          trả về kết quả <-----------+
                |
         Tiếp tục dùng hàm khác,
         hoặc gọi lại với buffer mới

     STOP new calls -> đợi in-flight -> close libraryArena
     => symbol address thuộc scope đó không còn hợp lệ
~~~

**Điểm khó:** `callArena.close()` có thể diễn ra **giữa hai downcalls** và không có lý do phải đóng thư viện; ngược lại, `libraryArena.close()` có thể khiến những lời gọi tương lai bằng handle đã cache trở nên không hợp lệ, ngay cả khi Java object `MethodHandle` chưa bị GC.

Một hợp đồng ví dụ:
- **Library owner** chịu trách nhiệm nạp thư viện một lần, giữ `Arena libraryArena` còn sống khi bất kỳ caller nào có quyền thực hiện downcall.
- **Call owner** chịu trách nhiệm tạo/giải phóng buffer tạm (`Arena callArena`) sau khi foreign function **thật sự đã ngừng dùng pointer**.
- **Caller của library owner** không được lấy raw function address rồi lưu vượt lifecycle; nếu cần truy cập từ nhiều thread, đi qua owner thực hiện gate/lease.

Trong một thư viện thật, có thể có **native-created worker** và callback C giữ pointer sang Java. Khi đó lifetime phải mở rộng tới khi native code dừng, không chỉ thời gian Java method return.

## 3. `SymbolLookup.libraryLookup` gắn thư viện với arena như thế nào?

FFM JDK 22+ cung cấp hai factory cho native library cụ thể:

~~~java
// Fragment bên trong Java method, cần import java.lang.foreign.*.
SymbolLookup byName =
        SymbolLookup.libraryLookup("libExample.so", libraryArena);

SymbolLookup byPath =
        SymbolLookup.libraryLookup(
                Path.of("/absolute/path/libExample.so"),
                libraryArena);
~~~

Đây là **cú pháp minh họa**, không phải file chạy độc lập và tên/path chỉ là ví dụ Linux. `Path` cần `import java.nio.file.Path;`. Sử dụng **một trong hai**, không phải nạp hai lần mặc định.

Cả hai method là **restricted native access**. Chúng:
1. Tìm thư viện theo **tên** được OS loader hiểu, hoặc theo **path** trong file system.
2. Nạp library nếu chưa có trong tiến trình theo semantics của OS.
3. Trả về lookup chỉ tìm symbols được export trong library ấy.
4. Gắn **scope của lookup và symbol addresses** với `arena` truyền vào.
5. Khi arena đóng, library lookup hết lifetime; thư viện có thể bị dỡ khỏi process, tùy reference counting / loader / việc có thành phần khác cũng đang giữ library.

Cú pháp chạy từ classpath thông thường:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

Không có quyền native access, ứng dụng có thể nhận cảnh báo hoặc `IllegalCallerException` tùy JDK release và chính sách đang dùng. **Không nhầm flag native access với việc cấp thêm bộ nhớ**: đây là cơ chế khai báo module được phép thực hiện những thao tác FFM rủi ro, không làm native function trở nên an toàn nếu ABI sai.

### Arena đóng: đừng đánh đồng scope với tình trạng vật lý của DLL/SO

Nếu `try (Arena arena = Arena.ofConfined())` kết thúc bình thường, `arena.scope().isAlive()` chuyển thành `false`. Đó là điều **Java FFM có thể kiểm chứng**. Việc hệ điều hành đã unload file SO/DLL ra khỏi process thật chưa có thể phụ thuộc:
- thư viện đã được load sẵn bởi JVM hoặc module khác;
- bộ đếm tham chiếu của dynamic loader;
- dependency giữa native libraries;
- chính sách giữ system runtime libraries ở OS.

Do đó cách diễn đạt đúng là **library lookup và symbol addresses của owner arena đã hết hạn; không được gọi nữa**. Tránh khẳng định “chắc chắn DLL bị xóa khỏi bộ nhớ ngay lập tức” hoặc dựa vào tên file còn mở để quyết định an toàn.

### Một `SymbolLookup` không tự cho biết ABI signature

~~~java
MemorySegment address = byName.find("ffi_calculate")
        .orElseThrow(() -> new IllegalStateException("symbol missing"));
~~~

`address` chỉ biểu diễn vị trí symbol native. `find` không đọc C header hay biết `int`/`size_t`/pointer arguments. Developer phải có `FunctionDescriptor` phù hợp để `Linker` tạo handle. Sai signature native có thể crash JVM; không có compile-time Java type checker nào đối chiếu symbol với function declaration C thật.

## 4. Địa chỉ ký hiệu là một `MemorySegment` đặc biệt

Javadoc FFM mô tả địa chỉ của symbol như một **zero-length memory segment**:

~~~java
MemorySegment functionAddress =
        lookup.find("abs").orElseThrow();
long bytes = functionAddress.byteSize(); // 0 trong lookup của bài.
~~~

Đây không phải buffer:

~~~java
// SAI – không thể đọc giá trị int từ "function address" zero-length.
int data = functionAddress.get(ValueLayout.JAVA_INT, 0);
~~~

Bạn có thể dùng nó làm function address cho `linker.downcallHandle(address, descriptor)`. Nếu symbol là **native global variable**, muốn thao tác dữ liệu nằm tại địa chỉ ấy phải biết size, alignment và ownership, rồi dùng API thích hợp; việc mở rộng bounds bằng `reinterpret` là **restricted operation** và có thể nguy hiểm nếu đoán kích thước.

### Kiểm tra scope mà không dereference

Từ symbol của `libraryLookup(..., arena)`:

~~~java
MemorySegment address = lookup.find("abs").orElseThrow();
boolean active = address.scope().isAlive();
~~~

Trong demo: khi `libraryArena` đang mở, `active` là `true`; sau `close`, là `false`. **Không in địa chỉ raw** vì địa chỉ phụ thuộc ASLR/OS/phiên chạy và không hữu ích để chứng minh lifetime.

Một `MemorySegment` Java vẫn có thể tồn tại khi scope đã đóng, nhưng đó là **view hết hiệu lực**. Giữ `MemorySegment` trong Java field, chuyển nó qua `long` rồi dựng lại pointer, hay giữ `MethodHandle` là những cách khác nhau để nắm **thông tin địa chỉ**; chúng không thay thế quyền sử dụng hợp lệ theo lifetime.

### Scope của symbol và scope của input buffer khác nhau

`functionAddress.scope()` gắn với **libraryArena** của lookup; `inputCString.scope()` gắn với **callArena** đã allocate nó. Hai objects có thể có cùng Java type `MemorySegment` nhưng có owner khác và phải được đóng ở thời điểm khác.

Đây là lý do cần đặt tên `libraryArena`, `callArena` rõ trong source, thay vì chỉ dùng một biến `arena` kéo dài không biết ai chịu trách nhiệm.

## 5. Chọn loại Arena cho thư viện: confined, shared, auto hay global?

| Loại arena | Dùng `libraryLookup` được không? | Giới hạn chính | Trường hợp phù hợp |
|---|---|---|---|
| `Arena.ofConfined()` | Có | Symbol segments/thread access thuộc **thread tạo arena**; close bởi owner thread | Binding dùng đồng bộ trong một thread; test/demo hoặc luồng chuyên trách |
| `Arena.ofShared()` | Có | Cho nhiều threads dùng symbol; **không tự chặn race giữa close và calls** | Binding dùng chung bởi server/worker pool; cần owner/gate/stop protocol |
| `Arena.ofAuto()` | Có nếu native-access policy cho phép | Không đóng tường minh; cleanup do reachability/GC, **không có deadline** | Chỉ khi lifetime tự động thực sự hợp contract |
| `Arena.global()` | Có nếu policy cho phép | Scope không đóng; native resources có thể sống tới hết process | Library cố ý dùng suốt JVM lifetime, có giới hạn số lượng và không cần unload |

### 5.1. Chọn `ofConfined` khi mọi thao tác thuộc một thread

~~~java
// Fragment, cần Java 22+ và native access.
try (Arena libraryArena = Arena.ofConfined()) {
    SymbolLookup lookup =
            SymbolLookup.libraryLookup(libraryName, libraryArena);

    MemorySegment address = lookup.find("abs").orElseThrow();
    MethodHandle abs = linker.downcallHandle(
            address,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

    int result = (int) abs.invokeExact(-17);
    // result == 17.
} // Symbol scope và library owner kết thúc ở đây.
~~~

Ưu điểm: lifetime ngắn, đóng đúng chỗ, đơn giản, chi phí scope thấp. Nhược điểm: **không** chuyển symbol/handle gắn với confined arena sang thread pool rồi tự ý gọi ở các thread khác. Đặc biệt, nếu một thread Java khác gọi `close` trên confined arena, thường gặp `WrongThreadException`.

### 5.2. Chọn `ofShared` cho library-wide owner đa thread

~~~java
// Fragment khái niệm: các thao tác phải nằm trong một class owner có gate.
Arena libraryArena = Arena.ofShared();
SymbolLookup lookup = SymbolLookup.libraryLookup(
        libraryName, libraryArena);
MethodHandle mh = linker.downcallHandle(
        lookup.find("abs").orElseThrow(), signature);

// Multiple worker threads may use the shared-scope symbol.
// Owner phải chặn calls mới và đợi mọi calls cũ xong trước khi:
libraryArena.close();
~~~

**Shared không có nghĩa “đóng ở đâu/lúc nào cũng an toàn”**. Arena có thể từ chối close trong khi một segment đang được truy cập đồng thời (ví dụ downcall đang chạy), nhưng exception không thay thế lock/gate/state machine. Muốn deterministic shutdown, **không mở race rồi chỉ catch `IllegalStateException` để thử lại tùy ý**.

### 5.3. Khi nào tránh `ofAuto` hoặc `global`?

Nếu code có explicit `closeSession()`, cần đảm bảo không thể gọi native nữa sau khi hàm trả về, và muốn giải phóng library đúng thời điểm, **`ofAuto` không cho deadline**, còn `global` **không đóng được**. Nếu tạo hàng trăm classloaders/plugins độc lập rồi mỗi plugin dùng `Arena.global()`, có thể khiến native code/resources không được release theo session.

Cả hai vẫn có use case hợp lệ: một dependency hệ thống bắt buộc sống suốt tiến trình có thể gắn global lifetime; một API hoàn toàn dựa vào reachability có thể cân nhắc auto. Hãy ghi rõ lựa chọn này là **quyết định ownership**, không phải lựa chọn “để đỡ phải đóng”.

### 5.4. Bảng quyết định ngắn

| Bài toán | Arena đề xuất cho **library** | Arena đề xuất cho **tham số** |
|---|---|---|
| Một thread gọi một vài functions đồng bộ trong một block | `ofConfined`, dùng `try-with-resources` | `ofConfined` theo từng call hoặc dùng cùng arena nếu lifetime tương đương |
| Một service nhiều request threads dùng cùng library | `ofShared` do service/binding owner giữ | `ofConfined` **từng request/call thread** cho buffers ngắn |
| Native async callback giữ pointer sau return | `ofShared` hoặc owner dài hạn phù hợp | Session arena sống tới sau callback/unregister, không call-local |
| Plugin muốn unload/reload rõ ràng | `ofShared`/`ofConfined` tùy threads, có `close` rõ | Scope của từng operation |
| Thư viện dùng suốt vòng đời process, không cần unload | `global` có thể phù hợp nếu thực sự có contract | Vẫn **không** nên mặc định mọi request buffer cũng là global |

Lựa chọn arena khác nhau là bình thường: **lifetime của code function** và **lifetime của bytes truyền vào function** là hai hợp đồng độc lập.

## 6. `libraryLookup`, `defaultLookup`, `loaderLookup`: đừng lẫn ownership

| API | Các symbols đến từ đâu? | Thời gian sống / owner |
|---|---|---|
| `SymbolLookup.libraryLookup(name/path, arena)` | Một native library cụ thể, được nạp nếu chưa có | **Arena đã truyền vào** điều khiển lookup/library lifetime |
| `Linker.nativeLinker().defaultLookup()` | Các native libraries linker/JVM nền tảng chọn expose | Không truyền arena do caller sở hữu; không tự đóng như library lookup |
| `SymbolLookup.loaderLookup()` | Libraries đã được nạp bằng `System.load`/`System.loadLibrary` trong class loader của caller | Có cơ chế classloader reachability; không phụ thuộc call-local arena tùy ý |

Một nhận định dễ sai: “Tôi đã dùng `SymbolLookup.libraryLookup("foo", arena)` nên `SymbolLookup.loaderLookup().find("foo")` phải tìm thấy các symbols trong foo”. **Không đúng**: JDK 22 quy định loader lookup chỉ bao gồm các libraries nạp theo JNI loader, không tự động gồm thư viện được library lookup nạp. Vì vậy **giữ chính lookup mà bạn đã nhận** từ `libraryLookup` khi muốn truy cập symbol cùng scope.

Một nhận định sai khác: “`defaultLookup` tìm toàn bộ thư viện máy tôi đã cài”. Không có cam kết ấy; tập symbol của default lookup phụ thuộc native linker/JDK/OS. Muốn một plugin cụ thể, dùng `libraryLookup` với tên/path và quản lý arena.

### SymbolLookup.or(...) và lifetime của từng source

`lookupA.or(lookupB)` tạo lookup kết hợp: thử A trước, nếu không thấy mới thử B. Nhưng **không biến hai library arenas thành một owner duy nhất**. Symbol tìm được từ A thuộc lifetime của A; tìm được từ B thuộc lifetime của B. Không được đóng A sớm chỉ vì bạn vẫn giữ lookup composite và B còn sống.

Ví dụ (fragment):

~~~java
SymbolLookup combined = SymbolLookup.libraryLookup("foo", arenaFoo)
        .or(SymbolLookup.libraryLookup("bar", arenaBar));
MemorySegment address = combined.find("some_function").orElseThrow();
// Phải biết symbol đến từ foo hay bar để chọn lifetime đúng.
~~~

Nếu hai thư viện có symbol cùng tên, thứ tự lookup cũng quan trọng: A được ưu tiên. Trong bindings lớn, nên quản lý riêng mỗi thư viện/ABI để tránh gọi nhầm symbol từ library khác.

### Tên so với đường dẫn

`libraryLookup(String, Arena)` giải quyết tên qua **OS native loader** (Windows `LoadLibrary`, Linux `dlopen`...); tên `libc.so.6`, `msvcrt.dll`, `libSystem.B.dylib` là **platform-specific**, không phải tên JVM portable. `libraryLookup(Path, Arena)` cho một file cụ thể, thường phù hợp thư viện do ứng dụng đóng gói. Việc dùng `Path.of(...).toAbsolutePath()` không làm binary tương thích nếu CPU architecture hoặc dependencies sai.

## 7. Linker và MethodHandle không “pin” mọi thời gian sống mã native

Để thực hiện một downcall:

~~~java
Linker linker = Linker.nativeLinker();
MemorySegment symbol = lookup.find("abs").orElseThrow();

FunctionDescriptor signature = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

MethodHandle abs = linker.downcallHandle(symbol, signature);
int result = (int) abs.invokeExact(-42);
~~~

Tương ứng C: `int abs(int);`. Trên các ABI phổ biến `int` là 32-bit; ứng dụng production phải xác minh C header và ABI thay vì giả định mọi `int`/`long` cùng kích thước. `ValueLayout.JAVA_INT` dùng carrier Java `int`.

`MethodHandle` là một Java object callable, nhưng **không có quyền tăng lifetime của thư viện lên vô hạn**. Nó chỉ có thể được gọi trong khi function address/lookup vẫn hợp lệ. Nếu library arena bị đóng, gọi `abs.invokeExact(-42)` bằng handle cũ không được phép — **đừng làm thử**, bởi trong các trường hợp sai lifetime có thể dẫn tới lỗi JVM nghiêm trọng, không chỉ một Java exception.

### Mã Java chạy thành công không có nghĩa ABI đã đúng

`SymbolLookup.find("abs")` chỉ xác nhận symbol theo tên tồn tại. `FunctionDescriptor` phải được tạo dựa trên **chữ ký C thật**. Ví dụ sai:

~~~java
// Sai: abs(int) nhưng mô tả như nhận địa chỉ pointer.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.ADDRESS);
~~~

Nếu cố gọi C `abs` với descriptor này, bạn đã nói với linker một ABI khác thực tế. Một số tình huống có thể cho kết quả rác hoặc crash. Không dùng Java exception handling để thay cho kiểm tra signature.

### Địa chỉ hàm có thể thay đổi khi reload

OS loader có thể gán vị trí khác khi native library được unload/reload (ASLR hoặc trạng thái process). Không lưu raw `long functionAddress` vào database/cache rồi dùng sau restart/reload. Luôn tạo **lookup/handle mới trong owner mới** nếu cần load lại. Các Java references tới old symbol không được đưa sang binding instance mới.

## 8. Chương trình 1: hai arena, một thư viện và hai lời gọi hàm C

Ví dụ này minh họa **`Arena.ofConfined()`** quản lý thư viện dùng trong **cùng thread**, còn `Arena.ofConfined()` thứ hai quản lý C string cho một call. Ta dùng hai functions C phổ biến:

~~~c
/* Hai khai báo C để xác định ABI, không phải JNI glue code. */
int abs(int value);
size_t strlen(const char *text);
~~~

`abs` nhận/trả `int`; `strlen` trả `size_t` (ABI-specific), nhận pointer đến C string kết thúc bằng NUL. Các hệ điều hành có tên C runtime khác nhau; code có lựa chọn điển hình cho Windows, Linux và macOS. Đã kiểm thử thực thi **Windows x64/JDK 24**; không cam kết mọi bản phân phối Linux/macOS expose đầy đủ hai symbols đúng tên trong library đã chọn.

### 8.1. File Java đầy đủ: `LibraryArenaLesson.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.util.Locale;

public final class LibraryArenaLesson {
    private static String nativeLibraryName() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        if (os.contains("win")) return "msvcrt.dll";
        if (os.contains("mac")) return "libSystem.B.dylib";
        if (os.contains("linux")) return "libc.so.6";
        throw new UnsupportedOperationException(
                "No example libc name for " + os);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment escapedAddress;

        try (Arena libraryArena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                    nativeLibraryName(), libraryArena);

            MemorySegment absAddress = library.find("abs")
                    .orElseThrow(() -> new IllegalStateException(
                            "abs not exported"));
            escapedAddress = absAddress;

            System.out.println("symbolBytes=" + absAddress.byteSize());
            System.out.println(
                    "libraryAlive=" + libraryArena.scope().isAlive());

            FunctionDescriptor absSignature = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
            MethodHandle abs = linker.downcallHandle(
                    absAddress, absSignature);

            int first = (int) abs.invokeExact(-7);
            System.out.println("abs(-7)=" + first);

            MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
            if (sizeT == null) {
                throw new AssertionError("missing size_t");
            }
            MemorySegment strlenAddress = library.find("strlen")
                    .orElseThrow(() -> new IllegalStateException(
                            "strlen not exported"));
            MethodHandle strlen = linker.downcallHandle(
                    strlenAddress, FunctionDescriptor.of(
                            sizeT, ValueLayout.ADDRESS));

            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment cstr =
                        callArena.allocateFrom("library");
                long n = ((Number) strlen.invokeWithArguments(cstr))
                        .longValue();

                System.out.println("strlen=" + n);
                if (n != 7) {
                    throw new AssertionError("bad strlen");
                }
            } // Buffer cstr hết lifetime tại đây.

            // C library vẫn còn sống dù callArena đã đóng.
            int second = (int) abs.invokeExact(-42);
            System.out.println("afterCallArenaAbs=" + second);

            if (first != 7 || second != 42) {
                throw new AssertionError("bad abs");
            }
        } // Đóng libraryArena; không còn quyền downcall.

        // Chỉ quan sát trạng thái scope, KHÔNG gọi lại abs/strlen.
        System.out.println("symbolAliveAfterClose="
                + escapedAddress.scope().isAlive());
        if (escapedAddress.scope().isAlive()) {
            throw new AssertionError("library scope alive");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

Không có `package`; tên file phải đúng `LibraryArenaLesson.java`. `import java.lang.foreign.*` hỗ trợ ví dụ gọn trong Java 22+. Tên runtime `msvcrt.dll`/`libc.so.6`/`libSystem.B.dylib` là **minh họa cho platform phổ biến**, không thay thế việc kiểm tra cài đặt thật.

### 8.2. Build/run đúng phiên bản

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED \
  -cp out LibraryArenaLesson
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

**Windows CMD** (nếu `out` chưa tồn tại):

~~~bat
mkdir out
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

Với JDK 22+ FFM đã finalized, **không cần `--enable-preview`**. Cũng không cần `javac -h` hay `jni.h`, vì code dùng **SymbolLookup/Linker** chứ không tạo JNI native method.

### 8.3. Stdout đã được kiểm chứng

~~~text
symbolBytes=0
libraryAlive=true
abs(-7)=7
strlen=7
afterCallArenaAbs=42
symbolAliveAfterClose=false
RESULT: PASS
~~~

Kết quả này đã chạy thực tế trên **JDK 24, Windows x64**, biên dịch với `javac --release 22` và chạy kèm `--enable-native-access=ALL-UNNAMED`.

Các dòng minh họa **từng lifetime khác nhau**:
- `symbolBytes=0`: địa chỉ function là **segment zero-length**; không đọc như buffer.
- `libraryAlive=true`: thư viện còn trong FFM scope do `libraryArena` sở hữu.
- `abs(-7)=7`: linker dùng ABI của C runtime, gọi function khi library alive.
- `strlen=7`: buffer của `callArena` chứa "library" gồm bảy byte ASCII trước NUL và sống qua `strlen` synchronous call.
- `afterCallArenaAbs=42`: đóng input arena không ảnh hưởng đến library scope.
- `symbolAliveAfterClose=false`: scope của function address đã hết hiệu lực sau `libraryArena.close()`. **Không thử gọi abs sau dòng này**.
- `RESULT: PASS`: các assertions và scope checks đã đạt.

Nếu platform không tìm được libc theo tên, sẽ phát sinh `IllegalArgumentException` ở `libraryLookup`; nếu tên library đúng nhưng không export `abs`/`strlen`, `orElseThrow` tạo `IllegalStateException` cụ thể. Đừng sửa bằng cách tạo raw function address tùy ý; hãy chọn đúng native runtime library/path của môi trường hoặc dùng ví dụ thư viện riêng ở phần sau.

## 9. Vì sao chọn riêng callArena? Phân tích theo thời gian

Một lời gọi `strlen` đồng bộ có lifecycle:

~~~text
t0   libraryArena mở, lookup("strlen"), tạo MethodHandle strlen
t1   callArena mở, cấp C string ("library\0")
t2   Java gọi strlen(cstr), C đọc buffer khi callArena còn sống
t3   strlen return long/int theo ABI, Java lấy giá trị 7
t4   callArena.close() -> cstr hết hiệu lực
t5   Java gọi abs(-42) bằng symbol khác trong libraryArena
t6   libraryArena.close() -> symbol scope hết hiệu lực
t7   Không dùng bất kỳ function address/handle thuộc owner đã đóng
~~~

Nếu C API lưu pointer cho **asynchronous use**, bước t4 **không còn hợp lệ** chỉ vì Java method return. Khi đó cần một **session arena** dài hơn call arena, một API callback/unregister hoặc cơ chế xác nhận native code không còn dùng buffer trước khi close.

### Không chỉ một Arena cho “tất cả mọi thứ”

Đôi khi dùng một arena cho cả library lẫn buffers để code ngắn:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lib = SymbolLookup.libraryLookup(name, arena);
    MemorySegment input = arena.allocateFrom("example");
    // Gọi hàm native đồng bộ, rồi đóng tất cả.
}
~~~

Pattern này hợp lệ nếu **mọi resource thật sự cùng lifetime**. Nhưng nếu service load library một lần và xử lý hàng triệu requests, không nên giữ mọi input buffer trong library arena cho đến khi server shutdown: như thế memory của mỗi call bị giữ quá lâu. Hãy phân biệt **binding owner** và **request buffer owner**.

### Không đóng thư viện trong helper trả về handle

~~~java
// SAI về lifetime: không chạy kiểu helper này.
static MethodHandle badHandle() {
    try (Arena arena = Arena.ofConfined()) {
        var lookup = SymbolLookup.libraryLookup("myLibrary", arena);
        var symbol = lookup.find("my_function").orElseThrow();
        return Linker.nativeLinker().downcallHandle(
                symbol, someKnownDescriptor);
    } // Arena đóng TRƯỚC khi caller dùng handle.
}
~~~

`someKnownDescriptor` trong fragment chỉ đại diện một descriptor phải được định nghĩa từ C header. Lỗi không nằm ở cú pháp Java mà ở API design: helper trả **handle vượt lifetime của owner**. Sửa bằng việc trả **binding owner object** có `Arena`, `MethodHandle` và `close()`, rồi chỉ cho phép gọi qua owner khi còn OPEN. Ví dụ đầy đủ phía dưới.

## 10. Chương trình 2: dùng `Arena.ofShared()` với gate đóng thư viện

Một library có thể dùng chung bởi nhiều Java threads. Nếu tạo `libraryArena = Arena.ofConfined()` trong thread main rồi đưa `MethodHandle` có symbol scoped tới workers, việc gọi từ thread khác **không phải lựa chọn đúng**. `Arena.ofShared()` cho phép segment scope được dùng đa thread, nhưng cần **gate** để đảm bảo không đóng arena khi downcall còn đang chạy.

Chương trình dùng `ReentrantReadWriteLock`:
- Mỗi `absolute(int)` giữ **read lock** xuyên suốt native downcall.
- `close()` lấy **write lock**, vì thế đợi tất cả read locks trả về rồi mới close.
- `closed` được kiểm tra **dưới cùng gate**, không chỉ dùng một biến boolean đọc ngoài lock.
- Sau close, gọi tiếp sẽ nhận `IllegalStateException` **từ Java wrapper**, không thử thực thi stale native handle.
- Arena đóng được giữ **trong owner**; caller không nhận raw address/`MethodHandle` ra ngoài.

### 10.1. File hoàn chỉnh `SharedLibraryLesson.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.util.Locale;
import java.util.concurrent.*;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class SharedLibraryLesson {
    private static String nativeLibraryName() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        if (os.contains("win")) return "msvcrt.dll";
        if (os.contains("mac")) return "libSystem.B.dylib";
        if (os.contains("linux")) return "libc.so.6";
        throw new UnsupportedOperationException(os);
    }

    static final class LibrarySession implements AutoCloseable {
        private final Arena libraryArena;
        private final MethodHandle absolute;
        private final ReentrantReadWriteLock lifecycle =
                new ReentrantReadWriteLock();
        private boolean closed;

        LibrarySession(String name) {
            Arena fresh = Arena.ofShared();
            try {
                SymbolLookup library =
                        SymbolLookup.libraryLookup(name, fresh);
                MemorySegment symbol =
                        library.find("abs").orElseThrow();

                this.absolute =
                        Linker.nativeLinker().downcallHandle(
                                symbol,
                                FunctionDescriptor.of(
                                        ValueLayout.JAVA_INT,
                                        ValueLayout.JAVA_INT));
                this.libraryArena = fresh;
            } catch (RuntimeException | Error ex) {
                fresh.close(); // Cleanup khi init thất bại.
                throw ex;
            }
        }

        int absolute(int value) {
            lifecycle.readLock().lock();
            try {
                if (closed) {
                    throw new IllegalStateException("library closed");
                }
                try {
                    return (int) absolute.invokeExact(value);
                } catch (Throwable failure) {
                    throw new IllegalStateException(
                            "foreign call failed", failure);
                }
            } finally {
                lifecycle.readLock().unlock();
            }
        }

        boolean scopeAlive() {
            lifecycle.readLock().lock();
            try {
                return libraryArena.scope().isAlive();
            } finally {
                lifecycle.readLock().unlock();
            }
        }

        @Override
        public void close() {
            lifecycle.writeLock().lock();
            try {
                if (!closed) {
                    libraryArena.close();
                    closed = true;
                }
            } finally {
                lifecycle.writeLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        LibrarySession owner =
                new LibrarySession(nativeLibraryName());
        try {
            ExecutorService workers = Executors.newFixedThreadPool(2);
            try {
                Future<Integer> first =
                        workers.submit(() -> owner.absolute(-7));
                Future<Integer> second =
                        workers.submit(() -> owner.absolute(-42));

                int a = first.get();
                int b = second.get();
                if (a != 7 || b != 42) {
                    throw new AssertionError();
                }
                System.out.println("parallelAbs=" + a + "," + b);
            } finally {
                workers.shutdown();
                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "workers not finished");
                }
            }
            System.out.println("libraryAliveBeforeClose="
                    + owner.scopeAlive());
        } finally {
            owner.close();
        }

        System.out.println("libraryAliveAfterClose="
                + owner.scopeAlive());
        try {
            owner.absolute(-9);
            throw new AssertionError(
                    "closed owner accepted a call");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "callAfterClose=IllegalStateException");
        }
        System.out.println("RESULT: PASS");
    }
}
~~~

Đây là **file độc lập** với chương trình trước, không copy hai `public class` vào cùng file. `LibrarySession` là owner của library và handle; caller chỉ dùng `absolute(...)` và `close()`. Hàm `nativeLibraryName()` dùng tên runtime OS để demo, cần thay khi triển khai với custom library khác.

### 10.2. Lệnh build và stdout

~~~sh
mkdir -p out
javac --release 22 -d out SharedLibraryLesson.java
java --enable-native-access=ALL-UNNAMED \
  -cp out SharedLibraryLesson
~~~

Trên Windows PowerShell, thay `mkdir` bằng `New-Item -ItemType Directory -Force out | Out-Null` nếu muốn script không báo khi thư mục đã có; câu lệnh `javac/java` giữ nguyên.

Output được kiểm thử:

~~~text
parallelAbs=7,42
libraryAliveBeforeClose=true
libraryAliveAfterClose=false
callAfterClose=IllegalStateException
RESULT: PASS
~~~

**Vì sao output deterministic?** Hai workers có thể chạy theo thứ tự khác nhau, nhưng Java thu kết quả bằng `Future.get()` của `first` và `second`, rồi in theo thứ tự xác định. Native function `abs` là hàm không phụ thuộc mutable session state, và cả hai downcalls được phép chạy trên shared-scope symbol.

### 10.3. Phân tích gate trong code

~~~text
Thread worker A                       Thread worker B
   readLock                                readLock
   check closed=false                     check closed=false
   native abs(-7)                         native abs(-42)
   readUnlock                              readUnlock
        \                                   /
         \                                 /
          Owner close: writeLock đợi tới khi
          KHÔNG còn readLock giữ
              |
              v
         libraryArena.close()
         closed=true
              |
         unlock writeLock
              |
         absolute(...) mới:
         readLock, thấy closed=true -> Java IllegalStateException
         KHÔNG có downcall tới stale function address
~~~

Đây là nguyên tắc **ngăn close so với in-flight calls**. Nếu chỉ có `volatile boolean closed` mà không có gate, một thread có thể kiểm tra `closed == false` rồi bị preempt, thread khác đóng arena, sau đó thread đầu gọi native bằng handle hết hạn. Kiểm tra flag trước call **không đủ** nếu không ngăn shutdown xen vào.

### Giới hạn của ví dụ nhiều thread

- `ReentrantReadWriteLock` chỉ bảo vệ lifecycle của owner và **không làm một native C library vốn không thread-safe trở thành thread-safe**. Nếu C API có global mutable state, cần thêm synchronization theo C API contract.
- Không gọi `owner.close()` **từ chính callback/đường gọi vẫn đang giữ read lock** theo kiểu cố nâng read → write lock: `ReentrantReadWriteLock` không hỗ trợ upgrade an toàn và có thể self-deadlock. Yêu cầu close từ thread điều phối sau khi callbacks kết thúc.
- Code mô phỏng hai future ngắn hạn đã hoàn tất trước close. Với một server thực, quản lý **shutdown / request admission / timeout / interrupt / executor drain**; không close nếu một foreign call vẫn có thể đang chạy trên native side.
- `close()` được thiết kế **idempotent tại wrapper** qua `closed` check, vì **`Arena.close()` bản thân không idempotent**: gọi lại trên arena đã đóng gây exception.
- Nếu `Arena.close()` ném exception do resource đang được truy cập/cleanup lỗi, wrapper không được tuyên bố đã đóng thành công. Bản production cần error policy và trạng thái thất bại riêng để tránh owner rơi vào trạng thái không rõ; demo chỉ minh họa đường chạy bình thường.

## 11. `Arena.close()` và rủi ro race: đừng chỉ catch exception để “retry”

Javadoc của `Arena.close()` cho biết có thể:
- ném `WrongThreadException` nếu confined arena bị thread không phải owner đóng;
- ném `IllegalStateException` nếu arena đã đóng;
- ném `IllegalStateException` trong một số trường hợp có segment được truy cập đồng thời, như một downcall;
- ném `UnsupportedOperationException` nếu arena không hỗ trợ explicit close (auto/global);
- ném lỗi từ cleanup action do custom/native resource gắn với arena.

Có người thiết kế:

~~~java
// SAI về giao thức shutdown.
try {
    libraryArena.close();
} catch (IllegalStateException ignored) {
    // "có call đang chạy, thử lại sau" nhưng không chặn call mới!
}
~~~

Đoạn này không tạo **hàng rào** ngăn downcalls mới. Dù retry sau một chút, thread khác vẫn có thể mở call mới, tạo starvation hoặc unload race. Hãy thiết kế admission gate trước:
1. Đánh dấu `CLOSING` và từ chối yêu cầu mới.
2. Đợi mọi in-flight Java/native calls và callbacks đạt điểm an toàn.
3. Chỉ khi không còn ai dùng symbols, đóng library arena.
4. Đánh dấu `CLOSED` sau khi cleanup thành công.

Không đặt `close()` ở destructor/GC callback như một cách duy nhất để đáp ứng yêu cầu “unload ngay khi phiên làm việc kết thúc”. Với `Arena.ofAuto()`, việc GC chạy vào lúc nào không có deadline; với `Arena.global()`, scope không tự đóng.

### Ví dụ state machine

~~~text
           construct + load + lookup success
                         |
                         v
                       OPEN
                   /           \
         begin call             request close
             |                      |
        inFlight++              CLOSING
             |                reject new calls
        execute native               |
             |                  inFlight > 0?
        inFlight--                 /     \
                                yes      no
                                |         |
                              wait   arena.close()
                                            |
                                            v
                                          CLOSED
~~~

Trong multithreading, cần giữ consistency giữa `OPEN/CLOSING` và counter/inFlight. Một **read-write lifecycle lock** như demo đơn giản hóa chuyện đó, nhưng nếu foreign call làm callback reentrant hoặc yêu cầu close trong chính callback, phải đánh giá deadlock/lock-order hoặc thiết kế queue shutdown riêng.

## 12. Giao thức production cho session: ai tạo, ai mượn, ai hủy?

Để tránh *use-after-unload*, mỗi object trong binding phải có vai trò:

| Resource | Owner | Người “mượn” | Điểm cuối quyền sử dụng |
|---|---|---|---|
| `Arena libraryArena` | `LibrarySession/Binding` | Các methods gọi native, qua gate | Sau khi in-flight calls/callbacks dừng |
| `SymbolLookup library` | Binding | Code resolve symbol | Không dùng ngoài scope libraryArena |
| `MemorySegment symbol` | Lookup/arena | `Linker` hoặc downcall handle | Hết khi scope libraryArena đóng |
| `MethodHandle` bound to symbol | Binding | Callers qua API của binding | Không invoke sau owner close |
| `Arena callArena` | Mỗi call/request | Native function đồng bộ | Sau khi C không còn dùng buffer |
| `MemorySegment input/output` | Call/session arena | Native function có pointer | Không sau close/async use |
| `upcallStub` pointer (nếu có) | Callback/session arena | Native library đăng ký callback | Unregister + đợi callback cuối trước arena close |

Một pattern tốt: **không expose raw addresses/handles** từ public API. Dùng methods mức nghiệp vụ như `binding.calculate(a,b)`, nơi owner có thể:
- kiểm tra còn OPEN;
- giữ lease/read lock xuyên suốt call;
- cấp input buffers trong call arena;
- gọi method handle;
- kiểm tra kết quả/lỗi native;
- release buffer và lease;
- chỉ cho close khi không còn lease.

### Failure-atomic constructor

Nạp thư viện có thể thành công rồi `find("symbol")` thất bại, hoặc `downcallHandle` báo descriptor không hỗ trợ. Nếu constructor không dọn arena vừa tạo, bạn có thể giữ một library load không chủ đích. Vì vậy trong constructor ví dụ đa thread:

~~~java
Arena fresh = Arena.ofShared();
try {
    SymbolLookup library = SymbolLookup.libraryLookup(name, fresh);
    // Find symbol, create descriptor, linker/downcall handle.
    // Khi thành công, chuyển ownership vào field libraryArena.
} catch (RuntimeException | Error ex) {
    fresh.close(); // Cleanup nếu init chưa hoàn tất.
    throw ex;
}
~~~

Đây là fragment trình bày ý tưởng; chương trình đầy đủ ở mục 10 đã triển khai chính xác. Nếu cần xử lý phức tạp hơn, guard cả exception phát sinh khi cleanup và giữ exception gốc qua `addSuppressed`. Không để lại resource mới chỉ vì một phần initialization thất bại.

### Không tái sử dụng owner đã đóng

Nếu muốn reload plugin:

~~~text
Owner #1 OPEN -> CLOSING -> CLOSED
        |
        +-- symbol/handle thuộc Owner #1: không còn hợp lệ
Owner #2 NEW -> OPEN
        |
        +-- lookup/symbol/handle MỚI thuộc Owner #2
~~~

Không “hồi sinh” Java `MethodHandle` cũ bằng cách tạo một arena mới, kể cả thư viện cùng tên. Địa chỉ code có thể đổi qua unload/reload. Mọi callers của owner cũ phải được ngăn gọi tiếp, và API reload nên phát hành **một binding instance mới**.

## 13. Custom library của ứng dụng: dùng `libraryLookup(Path, Arena)`

Bài thực hành chính sử dụng C runtime OS để không cần C compiler. Khi cần đóng gói thư viện riêng, hãy biết phiên bản **Path overload**. Ví dụ dưới đây cung cấp một symbol C `ffi_square` và các lệnh build theo nền tảng. Đây là **bài thực hành bổ sung**; phần Java/C này chưa được chạy trên mọi toolchain trong phiên kiểm tra chính, nên hãy tự build/check exported symbol.

### 13.1. File native `native/ffm_arena.c`

~~~c
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

/* Ví dụ đơn giản, chỉ gọi với giá trị nhỏ tránh overflow int. */
FFM_EXPORT int ffi_square(int x) {
    return x * x;
}
~~~

Đây là một **C ABI symbol bình thường**: không có `JNIEnv *` hay JNI method name. Compiler cần export symbol có tên đúng `ffi_square`.

**Linux**:

~~~sh
mkdir -p native
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libffm_arena.so native/ffm_arena.c
~~~

**macOS**:

~~~sh
mkdir -p native
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libffm_arena.dylib native/ffm_arena.c
~~~

**Windows MSVC Developer Command Prompt**:

~~~bat
mkdir native
cl /nologo /W4 /LD native\ffm_arena.c /Fe:ffm_arena.dll
~~~

Tạo source `native/ffm_arena.c` trước khi build; `mkdir native` chỉ cần nếu thư mục chưa có. Native binary và JVM phải cùng CPU architecture. Kiểm tra exports bằng `nm -D --defined-only` (Linux), `nm -gU` (macOS) hoặc `dumpbin /EXPORTS` (Windows). Trên một số 32-bit Windows ABI, tên symbol có thể bị decorate và cần điều chỉnh export convention/lookup.

### 13.2. Java gọi đúng symbol và giữ library arena sống

Tạo `CustomLibraryArenaDemo.java`:

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CustomLibraryArenaDemo {
    public static void main(String[] args) throws Throwable {
        // JVM ánh xạ tên logic sang .so/.dylib/.dll theo OS.
        String filename = System.mapLibraryName("ffm_arena");
        Path libraryPath = Path.of(filename).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    libraryPath, libraryArena);
            MemorySegment function = lookup.find("ffi_square")
                    .orElseThrow(() -> new IllegalStateException(
                            "ffi_square not found"));

            Linker linker = Linker.nativeLinker();
            FunctionDescriptor desc = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

            MethodHandle square =
                    linker.downcallHandle(function, desc);

            int answer = (int) square.invokeExact(6);
            System.out.println("square(6)=" + answer);
            if (answer != 36) {
                throw new AssertionError("wrong C result");
            }
        } // Đóng owner library ở đây, sau downcall cuối.

        System.out.println("RESULT: PASS");
    }
}
~~~

Chạy **trong thư mục có native binary** (và source Java):

~~~sh
javac --release 22 CustomLibraryArenaDemo.java
java --enable-native-access=ALL-UNNAMED CustomLibraryArenaDemo
~~~

Dự kiến khi C binary đúng:

~~~text
square(6)=36
RESULT: PASS
~~~

`libraryLookup(Path, Arena)` nạp library theo file `Path` của JVM hiện tại; khác với `System.loadLibrary` qua JNI loader. Java source này không cần `javac -h` hoặc JNI C headers. Để dùng từ nhiều request threads, thay `Arena.ofConfined` bằng owner `Arena.ofShared` kèm gate tương đương ví dụ 2, **không chỉ sửa một từ khóa arena rồi coi lifecycle đã xong**.

## 14. Thư viện, symbol và callback: các phụ thuộc lifetime có thể tạo deadlock

Một native library có thể lưu function pointer để gọi ngược Java bằng `Linker.upcallStub`. Khi đó:

~~~text
Library owner arena ----- function code của C library
        |
        +-- C callback registry giữ function pointer upcall
                      |
                      v
Callback arena ------ upcallStub -> Java MethodHandle target
        |
        +-- phải còn sống trong khi callback đang được native gọi
~~~

Khi shutdown:
1. **Chặn callback registrations mới** và những downcalls mới.
2. **Unregister callback** từ native library, trong khi library vẫn còn live để gọi hàm unregister.
3. **Đợi callbacks/in-flight native work hoàn tất**.
4. Đóng callback/session arenas và các call buffers không còn được sử dụng.
5. Chỉ khi không còn function call vào library, **đóng library owner arena**.

Nếu đóng library arena trước khi gọi native unregister API, bạn đã làm mất code cần cho quá trình shutdown. Nếu đóng callback arena trong khi C vẫn giữ upcall pointer, C có thể gọi pointer hết hạn, gây crash.

**Deadlock cũng có thể xuất hiện:** một thread giữ write lock yêu cầu đóng binding rồi chờ callback, trong khi callback cố lấy read lock của chính binding để hoàn tất. Phải thiết kế *quiescing* và lock order. Không giữ write lock qua một blocking native unregister function nếu chính callback cần read lock ấy; có thể cần chuyển sang trạng thái `CLOSING`, thả lock, chờ hoạt động kết thúc, sau đó đóng khi quiescent. Ví dụ `ReentrantReadWriteLock` trong bài chỉ áp dụng cho các downcalls ngắn **không callback reentrant**.

## 15. Những sai lầm dễ gây lỗi khó tìm

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tạo `libraryLookup` bằng try-with-resources trong helper, return `MethodHandle` | MethodHandle vượt scope owner, nguy cơ use-after-unload | Return owner `AutoCloseable` giữ arena/handle và kiểm soát calls |
| Dùng `Arena.ofConfined` rồi gọi handle từ worker pool | Sai thread access, có thể `WrongThreadException` | Dùng `ofShared` và gate nếu cần cross-thread |
| Dùng `Arena.ofShared` rồi đóng khi request khác đang gọi native | Race close/in-flight, lỗi hoặc crash | Chặn calls mới, đợi tất cả calls/callbacks kết thúc rồi close |
| Giữ input buffers trong cùng library arena suốt service lifetime | Native memory tăng không cần thiết | Tách `callArena` cho synchronous buffers |
| Dùng `Arena.ofAuto` khi cần unload ngay tại `closeSession` | Không có deadline cho GC cleanup | Chọn explicit arena + close protocol |
| Dùng `Arena.global` cho mọi plugin reload | Không có explicit unload; tài nguyên có thể tích tụ | Chỉ dùng cho library cố ý process-lifetime |
| Gọi lại handle sau close để “xem có lỗi không” | Use-after-unload có thể crash JVM | Chỉ kiểm tra `scope().isAlive()` hoặc owner state, **không gọi native** |
| Ép symbol address size=0 thành readable data segment tùy ý | Truy cập sai bounds/ABI/lifetime | Symbol function dùng cho linker, global data cần size contract |
| Tìm symbol ở `loaderLookup` dù nạp qua `libraryLookup` | Không tìm thấy, loader semantics khác | Giữ lookup đúng nguồn và arena của nó |
| Giả định `defaultLookup` có mọi symbol được cài trên máy | `Optional.empty` | Dùng explicit native library lookup/path |
| Bỏ `--enable-native-access` | Cảnh báo hoặc IllegalCallerException theo bản JDK | Cấp quyền cho đúng module |
| Đoán Java `long` cho C `long`/`size_t` | ABI mismatch trên OS khác | Dùng `linker.canonicalLayouts()` và C headers |
| Catch mọi Throwable từ native call rồi tiếp tục gọi | Che giấu corruption/native error | Áp dụng error policy; C crash không phải Java exception bình thường |
| Đóng arena hai lần mà không có owner state | `Arena.close()` không idempotent | Wrapper có flag/state, idempotent public close khi hợp đồng yêu cầu |

### Đừng cất `MemorySegment.address()` vào cache dài hạn

Một function address có thể in ra dạng `long`, nhưng raw number ấy **không mang scope** khi chuyển thành số. Chuyển handle/address sang số nguyên không gia hạn DLL/SO lifetime. Sau unload/reload, symbol mới có thể ở vị trí khác, và việc dùng raw address cũ vượt qua các safeguards của FFM.

### Đừng gọi `close` trong pending downcall/callback

Một vài tài nguyên Java có cleanup tường minh, nhưng native function có thể vẫn đang dùng pointer tới buffer hoặc callback pointer. Việc `Arena.close()` báo lỗi concurrent access **không có nghĩa native code đã dừng**, và việc không thấy lỗi cũng **không phải** bằng chứng toàn bộ C threads đã dừng. Phải có native-level acknowledgements/joins khi cần.

## 16. Chẩn đoán theo thứ tự

### A. Không biên dịch Java

- `package java.lang.foreign does not exist`: đang dùng JDK dưới 22 hoặc compile target khác; dùng JDK 22+ cho source finalized.
- `cannot find symbol libraryLookup`: trộn FFM incubator/preview API, hoặc source/Javadoc của release khác. Kiểm tra `java -version` và `javac -version`.
- `WrongMethodTypeException` khi `invokeExact`: method handle carrier/argument types không khớp Java call site, cần xem `handle.type()`; riêng `strlen` dùng `invokeWithArguments` và `Number.longValue()` để tránh khóa cứng `size_t` Java carrier trên mọi pointer width.

### B. Nạp thư viện thất bại

- `IllegalArgumentException` ở `SymbolLookup.libraryLookup(name, arena)`: tên library không hợp lệ/OS loader không tìm thấy file hoặc dependencies không được load. Sử dụng tên chính xác trên OS, hoặc `libraryLookup(Path, Arena)` với file rõ.
- Load được nhưng `find("foo")` là empty: symbol không được export/tên khác, name mangling C++/calling convention hoặc sai version binary. Kiểm tra `nm`/`dumpbin`, C headers và linker export tables.
- `UnsatisfiedLinkError` ở JNI `System.loadLibrary` là một đường nạp **khác**, không đồng nghĩa FFM library lookup đang dùng Java library path theo cách giống JNI.

### C. Lỗi native access và ABI

- `IllegalCallerException`: caller/module không được phép gọi restricted `libraryLookup`/`downcallHandle`; cấp `--enable-native-access=ALL-UNNAMED` với classpath hoặc tên module thực.
- Native code crash hoặc dữ liệu rác: `FunctionDescriptor` sai C header (carrier, pointer, return, packing, varargs); luôn kiểm tra OS/arch/ABI trước.
- `WrongThreadException`: library lookup address gắn với confined arena bị truy cập từ thread khác hoặc confined arena bị close sai thread.
- `IllegalStateException` khi close: arena đã đóng, hoặc có truy cập concurrent. Dừng/admit gate, đợi in-flight work, ghi nhận lỗi; không thử lại vô hạn.

### D. Quan sát lifetime an toàn

Các phép kiểm tra hợp lý:

~~~java
boolean scopeAlive = libraryArena.scope().isAlive();
boolean symbolAlive = functionAddress.scope().isAlive();
int symbolBytes = (int) functionAddress.byteSize(); // thường là 0.
~~~

Khi scope hết hạn, chỉ quan sát status/owner state; **không gọi downcall** như một "test". Không suy ra actual OS unload từ việc PID vẫn có một DLL/SO mapped do loader có thể còn references khác.

### E. Lỗi chỉ xuất hiện dưới tải đa thread

Nếu single-threaded demo PASS nhưng production crash lúc shutdown:
- Ai đóng arena? Đóng trước khi worker pool drain chưa?
- Có native threads giữ C pointers vượt Java method return không?
- Có callbacks đang chạy hoặc sắp được native trigger?
- Owner có trả `MethodHandle`/`MemorySegment` ra ngoài gate, cho code không kiểm soát gọi khi CLOSED không?
- Có deadlock do close chờ callback, callback chờ lock của owner không?
- Library có global state không thread-safe dù Java gate cho phép nhiều read locks không?
- Phân biệt scope/lifetime errors với lỗi ABI hoặc C allocator.

## 17. Chiến lược test cho thư viện có unload/reload

Một bộ kiểm thử thực dụng gồm:
1. **Load đúng library**: `libraryLookup` theo name/path đã xác nhận; `find` symbol cần thiết.
2. **Downcall trong scope**: descriptor đúng ABI; hàm đơn giản `abs(-7)=7` hoặc custom `ffi_square(6)=36`.
3. **Input arena ngắn hơn library arena**: đóng call arena, tiếp tục downcall khác với library vẫn sống.
4. **Scope sau close**: `symbol.scope().isAlive()==false`; **không invoke stale handle**.
5. **Multi-threaded calls**: owner `ofShared`, run futures và đảm bảo tất cả hoàn thành trước close.
6. **Post-close rejection**: gọi wrapper API sẽ ném `IllegalStateException` **trước native call**, do owner state/gate.
7. **Initialization failures**: thiếu library/symbol; arena được đóng khi constructor thất bại.
8. **Shutdown contention**: stress tests thử thread A đang gọi, thread B yêu cầu close, thread C bắt đầu call mới; không có đường nào gọi sau CLOSED.
9. **Callback contracts**: nếu C có callback, unregister và in-flight callbacks quiescent trước close.
10. **Cross-OS builds**: kiểm tra Windows/Linux/macOS tên file, exports, dependencies, ABI và native loader behavior.

Một bài test khẳng định **native library đã bị unload thật** bằng việc gọi stale function pointer là **không an toàn**. Nếu cần điều tra physical unload ở OS, dùng profiler/native loader events trong môi trường cách ly; đừng biến nó thành unit test dựa trên crash.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `MemorySegment symbol` từ `lookup.find("abs")` có `byteSize()==0` mà vẫn gọi được hàm?  
**Đáp án:** Nó biểu diễn **địa chỉ function**, không phải data buffer. Linker dùng địa chỉ ấy cùng `FunctionDescriptor` để tạo downcall handle. Không `get(JAVA_INT,0)` để đọc “nội dung hàm”.

**Câu 2.** `MethodHandle abs` được cache trong singleton; library arena bị đóng. Vẫn gọi được vì singleton còn sống?  
**Đáp án:** Không. Java reachability của handle không gia hạn hợp đồng library scope. Phải chặn gọi và tạo binding mới nếu reload.

**Câu 3.** `Arena.ofConfined()` có phù hợp cho binding 8 threads gọi đồng thời không?  
**Đáp án:** Không phải lựa chọn phù hợp. Confined scope gắn owner thread. Dùng `ofShared()` và giao thức admission/close; kiểm tra native function bản thân có thread-safe.

**Câu 4.** Sao không dùng `Arena.global()` để tránh mọi lỗi use-after-close?  
**Đáp án:** Nó tránh explicit close nhưng tạo lifetime gần như vô hạn, không phù hợp plugin/session cần giải phóng native resources đúng lúc và có thể gây resource retention.

**Câu 5.** Đóng `callArena` sau `strlen` rồi gọi `abs` tiếp có hợp lý không?  
**Đáp án:** Có, vì `strlen` đồng bộ đã ngừng dùng C string, và `abs` chỉ dùng library symbol còn sống trong `libraryArena` riêng.

**Câu 6.** `SymbolLookup.loaderLookup()` có nhìn thấy mọi symbol từ `libraryLookup(path,arena)` không?  
**Đáp án:** Không. Loader lookup tập trung các native libraries đã nạp qua JNI loading APIs của caller class loader. Giữ đúng library lookup cho binding này.

**Câu 7.** Close một shared arena có thể ném IllegalStateException khi đang có downcall, vậy catch rồi retry có đủ không?  
**Đáp án:** Không. Phải **chặn downcalls mới**, đợi các calls/callbacks hiện hành xong rồi mới đóng. Bắt exception không thay thế giao thức ownership.

**Câu 8.** `SymbolLookup.libraryLookup("mylib", Arena.ofAuto())` có đảm bảo unload tại `closeSession` không?  
**Đáp án:** Không. Auto arena dựa vào GC/reachability; không có deadline cleanup xác định hay explicit close. Cần owner `ofConfined`/`ofShared` khi có close contract.

**Câu 9.** Nếu thư viện đã được JVM hoặc OS giữ ở nơi khác, `libraryArena.close()` có luôn xóa file khỏi process không?  
**Đáp án:** Không thể khẳng định. Scope của lookup đã hết hiệu lực; actual unload phụ thuộc loader/reference counting và các owners khác. Không được tiếp tục dùng function address cũ.

**Câu 10.** Khi native API đăng ký upcall stub và gọi callback sau này, arena nào được close đầu tiên?  
**Đáp án:** Sau khi đã **unregister** và đợi callbacks in-flight kết thúc, có thể đóng callback/session arena; library arena phải còn sống trong quá trình dùng native unregister API và mọi calls cuối, rồi mới đóng.

## 19. Checklist trước khi merge FFM binding có thư viện riêng

- [ ] Dùng FFM **JDK 22+ finalized** đúng version; native access enabled cho module/classpath nếu cần.
- [ ] Xác nhận chính xác library file/name, platform, CPU arch và C ABI.
- [ ] `SymbolLookup.libraryLookup(name/path, arena)` có owner rõ ràng; arena không đóng sớm.
- [ ] `MemorySegment` biểu diễn symbol address được dùng như function pointer, không nhầm với readable buffer.
- [ ] `FunctionDescriptor` khớp native C function signature; `MethodHandle` đúng Java method type.
- [ ] Chọn `ofConfined` nếu tất cả calls/close từ một thread, `ofShared` nếu nhiều threads; không xem shared như synchronization.
- [ ] `Arena.ofAuto/global` chỉ dùng khi lifetime không cần explicit close hoặc process-long theo contract.
- [ ] Có **binding owner** giữ arena, symbols/handles và `close`; không expose raw handles để gọi ngoài gate.
- [ ] Tách `callArena`/session buffer arenas nếu thời gian sống khác library; quản lý pointer mà C giữ bất đồng bộ.
- [ ] Shutdown chặn calls mới, đợi in-flight downcalls/upcalls/unregister rồi mới đóng library arena.
- [ ] Nếu có callback, tránh deadlock giữa write lock shutdown và callback cần read lock.
- [ ] Không gọi stale method handle hay dereference stale symbol sau close, kể cả trong test.
- [ ] Xác minh `scope().isAlive()` và owner state; public API reject calls sau close **trước native call**.
- [ ] Dọn arena khi khởi tạo thất bại một phần, không giữ library vô thời hạn.
- [ ] Đảm bảo wrapper close idempotent nếu API contract yêu cầu; nhớ `Arena.close()` tự nó không idempotent.
- [ ] Test trên OS/ABI thật; không suy từ một lần Windows PASS là mọi Linux/macOS symbols đều đồng nhất.

## 20. Tổng kết và nguồn tài liệu chuẩn

Một công thức dễ nhớ:

~~~text
libraryArena     -> giữ quyền dùng thư viện
libraryLookup    -> tìm địa chỉ symbol thuộc libraryArena
symbol address   -> MemorySegment zero-length, có scope
FunctionDescriptor + Linker -> MethodHandle downcall
callArena        -> cấp native bytes cho mỗi lời gọi
close libraryArena -> không gọi lại symbol/handle của owner ấy
~~~

**Quyết định Arena đúng không chỉ là chọn `ofConfined` hay `ofShared`: đó là thiết kế ai mở thư viện, ai được phép gọi, ai chờ các calls hoàn tất và ai đóng sau cùng.** Khi tách library lifetime khỏi input-buffer lifetime, quản lý symbol như resource có scope thay vì raw pointer vĩnh viễn, và có gate shutdown rõ, ứng dụng FFM sẽ dễ suy luận hơn nhiều.

Tài liệu chính thức:

- [OpenJDK JEP 454 – Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)
- [Java SE 22 – SymbolLookup: libraryLookup, loaderLookup, default lookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 – Arena: các loại arena, scope, close và thread confinement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 – Linker: downcall method handle và native ABI](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 22 – MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [Java SE 22 – FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)

Với phiên bản JDK mới hơn, xem Javadoc của **JDK đang triển khai** để kiểm tra native-access restrictions, vì chính sách có thể phát triển dù mô hình ownership giữ nguyên. Không thử nghiệm use-after-unload bằng cách chủ động crash JVM: thiết kế API owner nên **ngăn** hành động nguy hiểm đó ngay từ trước native call.