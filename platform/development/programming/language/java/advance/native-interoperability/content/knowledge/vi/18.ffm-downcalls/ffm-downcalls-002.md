# Phân biệt thư viện nạp qua JNI với thư viện do libraryLookup quản lý

## 1. Cùng là thư viện native, nhưng không cùng cơ chế nạp

Một chương trình Java có thể gọi mã C/C++ theo hai hướng quen thuộc:

- **JNI (Java Native Interface):** khai báo phương thức `native` và nạp thư viện bằng `System.loadLibrary(...)` hoặc `System.load(...)`. JVM quản lý quan hệ giữa **thư viện, class loader và JNI lifecycle hooks**, rồi liên kết các phương thức Java native với hàm C/C++.
- **FFM (Foreign Function & Memory API):** mô tả chữ ký hàm native bằng `FunctionDescriptor`, lấy địa chỉ symbol bằng `SymbolLookup`, sau đó dùng `Linker.downcallHandle(...)`. Đặc biệt, `SymbolLookup.libraryLookup(...)` nạp hoặc truy cập thư viện native thông qua cơ chế thư viện hệ điều hành và liên kết **vòng đời lookup/symbol** với một `Arena`.

Hai cách đều có thể cùng chạy trong một JVM, cùng dùng một file `.so`, `.dylib` hoặc `.dll`. Tuy nhiên **không được coi việc một thư viện đã được `libraryLookup` nạp là tương đương việc JVM đã nạp và đăng ký thư viện đó theo JNI**.

Ví dụ dễ nhớ:

~~~java
// Cơ chế 1: JVM nạp một JNI library và liên kết với class loader.
System.loadLibrary("jniowner");

// Cơ chế 2: FFM tạo library lookup, gắn vòng đời với Arena.
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup symbols = SymbolLookup.libraryLookup(
            Path.of("/absolute/path/to/library.so"), arena);
}
~~~

Đây là **mảnh code minh họa**, không biên dịch riêng lẻ. Cần `java.lang.foreign.Arena`, `SymbolLookup`, `java.nio.file.Path` và đường dẫn thư viện đúng hệ điều hành.

**Khác biệt quan trọng nhất:**

> `System.loadLibrary` làm thư viện trở thành **JNI library gắn với class loader**, có thể gọi `JNI_OnLoad`. `SymbolLookup.libraryLookup` quản lý **OS library lookup theo Arena** và **không tự thực hiện quy trình đăng ký thư viện JNI**.

Bài này dùng API đã chuẩn hóa của **JDK 22+** (JEP 454). Với JDK 17, FFM còn là incubator API khác; các import `java.lang.foreign` và chữ ký ở đây **không tương thích**.

### Bạn sẽ làm được gì?

1. Phân biệt **native library do JVM quản lý qua JNI** và **library lookup do FFM/Arena quản lý**.
2. Hiểu `JNI_OnLoad`, `JNI_OnUnload` và ý nghĩa class loader.
3. Dùng `SymbolLookup.loaderLookup()` để tìm symbol trong những thư viện đã nạp qua JNI.
4. Dùng `SymbolLookup.libraryLookup(String, Arena)` và `libraryLookup(Path, Arena)` đúng vòng đời.
5. Dùng `Linker.nativeLinker()`, `FunctionDescriptor` và `MethodHandle.invokeExact` để gọi hàm C.
6. Chạy ví dụ **hai thư viện C + hai lớp Java** có stdout phân biệt hai con đường nạp.
7. Tránh lỗi dùng symbol sau khi `Arena.close()`, lẫn lộn đường tìm thư viện và nhầm rằng `libraryLookup` tự chạy JNI hooks.

## 2. Bảng đối chiếu nhanh

| Góc nhìn | `System.loadLibrary` / `System.load` (JNI) | `SymbolLookup.libraryLookup` (FFM) |
| --- | --- | --- |
| Ý định chính | Nạp thư viện phục vụ JNI native methods và JNI lifecycle | Nạp/tìm **exported native symbols** để dùng qua FFM |
| API gọi | `System.loadLibrary("name")` hoặc `System.load(absolutePath)` | `SymbolLookup.libraryLookup("native-name", arena)` hoặc `libraryLookup(Path, arena)` |
| Ai quản lý nạp? | **JVM JNI native-library registry** với class loader | **FFM library lookup** dựa vào OS dynamic loader |
| Quan hệ với class loader | Thư viện JNI gắn với loader của lớp gọi load | Lookup không có cùng đăng ký JNI class-loader ownership |
| Quan hệ với Arena | Không được quản lý bằng Arena do caller truyền | Library lookup và symbol addresses gắn scope của **Arena** |
| `JNI_OnLoad` | JVM gọi khi nạp JNI library nếu export hook | **Không tự gọi** chỉ vì `libraryLookup` được tạo |
| `JNI_OnUnload` | Có thể gọi khi class loader sở hữu JNI library được GC | Không tự được gọi như JNI lifecycle hook khi đóng Arena |
| Tìm symbol từ JNI-loaded library | `SymbolLookup.loaderLookup()` từ class loader phù hợp | Có thể tạo `libraryLookup` cho thư viện đó, nhưng đó là lookup riêng |
| Tìm symbol từ FFM-loaded library | `loaderLookup()` **không** tự nhìn thấy | `libraryLookup(...).find(name)` nhìn thấy exported symbol |
| Kết thúc vòng đời | Gắn với class loader và JVM; không có `unloadLibrary()` công khai đối ứng | Dùng `Arena.close()` với confined/shared để kết thúc scope và giải phóng quyền quản lý lookup |
| Native access | JNI invocation theo các quy tắc JNI/JDK tương ứng | JDK 22: `libraryLookup` và tạo downcall là **restricted methods** |
| Lỗi hay gặp | `UnsatisfiedLinkError`, JNI method/linkage/ABI error | `IllegalArgumentException`, `IllegalCallerException`, thiếu symbol, scope/ABI error |

**Chú ý:** `libraryLookup` có thể truy cập thư viện đã được nạp từ trước; OS có thể tái sử dụng handle hoặc duy trì reference count. Đóng Arena **không bảo đảm OS lập tức unmap một file** nếu còn các owner hoặc references khác. Sự khác nhau ở bảng là **cơ chế ownership và quyền truy cập**, không nhất thiết là hai bản sao máy khác nhau của mã native.

## 3. JNI load: JVM ghi nhận thư viện với class loader

Ví dụ Java:

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    public static native int addOne(int number);
}
~~~

Ở lớp `NativeBridge`, `System.loadLibrary("nativebridge")` yêu cầu JVM tìm tên thư viện phù hợp OS: trên Linux thường là `libnativebridge.so`, trên macOS `libnativebridge.dylib`, trên Windows `nativebridge.dll`.

Khi cơ chế JNI nạp thành công, JVM có thể:

1. Yêu cầu OS loader tải shared library và dependencies.
2. Gắn thư viện đã nạp với **class loader của lớp gọi `System.loadLibrary`**.
3. Tìm và chạy `JNI_OnLoad(JavaVM*, void*)` nếu thư viện export symbol đó.
4. Kiểm tra **JNI version** mà hook trả về; hook có thể thực hiện setup như `RegisterNatives`.
5. Khi Java thực sự gọi `native addOne`, JVM liên kết method với hàm C theo tên JNI truyền thống hoặc registration.

**Một file thư viện có thể export nhiều hàm C thông thường**, nhưng việc JVM đã biết thư viện theo JNI **không tự biến mọi hàm C export thành Java native methods**. Với `native addOne`, JVM vẫn cần tên JNI hợp lệ hoặc `RegisterNatives`.

### 3.1. `JNI_OnLoad` và giá trị trả về

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

Đây là **JNI hook C hoàn chỉnh về mặt chữ ký**, nhưng chưa có phương thức nghiệp vụ.

- `JNI_OnLoad` được JVM **gọi khi thư viện được nạp theo JNI**, không phải một Java native method phải tự gọi.
- Giá trị thành công của **`JNI_OnLoad` là `JNI_VERSION_*` được JVM hỗ trợ**, ví dụ `JNI_VERSION_1_6`. Không nhầm `JNI_OK` (mã trạng thái của `GetEnv` và nhiều JNI APIs) với JNI version.
- Thư viện **không có** `JNI_OnLoad` vẫn có thể là JNI library; theo đặc tả JVM giả định nó yêu cầu JNI `JNI_VERSION_1_1`.
- Nếu hook trả một JNI version không hợp lệ, JVM từ chối nạp như thư viện chưa được nạp.
- Hook chạy trong ngữ cảnh class loader nạp thư viện, nên `FindClass` bên trong hook có quy tắc class-loader đặc biệt hữu ích khi đăng ký native methods.

Một thư viện được **chỉ** nạp thông qua cơ chế OS của `libraryLookup` không tự có quá trình JVM gọi hook `JNI_OnLoad`. Ngay cả khi file đó *có export* symbol `JNI_OnLoad`, sự tồn tại của symbol không đủ để tạo JNI registration.

### 3.2. `JNI_OnUnload` và vòng đời class loader

JNI có hook:

~~~c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    /* Dọn tài nguyên được thư viện JNI sở hữu. */
}
~~~

JVM có thể gọi hook khi **class loader chứa JNI library được GC**. Không xem hook là lời hứa “chắc chắn chạy khi Java process thoát” hoặc “mỗi lần người dùng đóng màn hình thì chạy”.

Theo quy tắc JNI truyền thống:

- Một JNI library động **không thể đồng thời được gắn với hai class loaders độc lập**. Việc nạp lại cùng thư viện từ loader khác có thể báo `UnsatisfiedLinkError`.
- JNI library lifetime liên quan đến reachability của class loader và các objects/references khác.
- Không có API Java công khai đơn giản kiểu `System.unloadLibrary("...")` để đóng thư viện theo ý muốn.
- Dùng `SymbolLookup.loaderLookup()` sẽ **giữ class loader liên quan reachable** chừng nào lookup/symbol segments tương ứng còn reachable, do đó có thể kéo dài vòng đời JNI library.

**Không áp dụng máy móc các quy tắc class loader của JNI** cho `SymbolLookup.libraryLookup`. Dù cả hai cùng gọi OS loader ở tầng thấp, FFM có ownership thông qua Arena và không tạo JNI class-loader registration tương đương.

## 4. FFM `libraryLookup`: thư viện được quản lý bằng Arena

Các overload trong JDK 22:

~~~java
SymbolLookup byName =
        SymbolLookup.libraryLookup("some-platform-name", arena);

SymbolLookup byPath =
        SymbolLookup.libraryLookup(
                Path.of("/absolute/path/to/native/library.so"),
                arena);
~~~

Đây là snippets, với `arena` đã được tạo và còn sống.

- `libraryLookup(String, Arena)` cho OS resolver tìm thư viện theo **native name**. Cách dò phụ thuộc OS: POSIX thường dựa vào `dlopen`; Windows dựa vào `LoadLibrary`.
- `libraryLookup(Path, Arena)` chỉ rõ **đường dẫn** đến thư viện, thường dễ kiểm soát hơn trong ví dụ và khi ứng dụng đóng gói file native riêng.
- `arena` quyết định **thời gian sống** của lookup và các address segments lấy qua `find`.
- `lookup.find("function_name")` trả `Optional<MemorySegment>`: có symbol thì trả address view (zero-length memory segment), không có thì `Optional.empty()`.
- `Linker.downcallHandle(address, FunctionDescriptor...)` tạo `MethodHandle` để gọi một **native function** theo ABI của OS/CPU.

Minh họa đủ thứ tự:

~~~java
try (Arena arena = Arena.ofConfined()) {
    Path library = Path.of(
            System.mapLibraryName("mathdemo")).toAbsolutePath();

    SymbolLookup lookup =
            SymbolLookup.libraryLookup(library, arena);

    MemorySegment address =
            lookup.find("native_square").orElseThrow();

    Linker linker = Linker.nativeLinker();

    MethodHandle square = linker.downcallHandle(
            address,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

    int result = (int) square.invokeExact(7);
    System.out.println(result);  // 49, nếu C export native_square.
}
~~~

Đoạn này là **minh họa**, chưa có `mathdemo` source ở đây. Các import cần dùng: `Arena`, `SymbolLookup`, `MemorySegment`, `Linker`, `FunctionDescriptor`, `ValueLayout`, `MethodHandle`, `Path`. `main` hoặc method phải xử lý/khai báo `Throwable` cho `invokeExact`.

**Giới hạn vòng đời:** `arena.close()` làm các symbol address segments từ lookup đó hết hiệu lực. **Không** giữ một downcall handle trỏ vào library của Arena đã đóng rồi gọi lại. Nếu native code còn đang dùng thư viện, phải chờ tất cả callers hoàn thành trước khi close.

### 4.1. Vì sao `libraryLookup` cần Arena?

Nạp thư viện native tạo một **resource cấp hệ điều hành**: handle tới thư viện, các dynamic dependencies và địa chỉ symbol. Người lập trình cần một cách nói rõ “được dùng tới khi nào”. Arena giải quyết:

~~~text
Native file trên disk
       |
       v
SymbolLookup.libraryLookup(path, arena)
       |
       +-- lookup.find("foo") -> symbol address A
       +-- lookup.find("bar") -> symbol address B
       |
       +-- Linker.downcallHandle(A, descriptorA)
       +-- Linker.downcallHandle(B, descriptorB)
       |
       v
Arena còn sống -> các calls có thể được phép khi ABI/lifetime hợp lệ
       |
       v
Arena.close() -> scope không còn sống, lookup/symbols hết hiệu lực
                 FFM giải phóng ownership đối với library
~~~

Lưu ý FFM không đảm bảo một thư viện được **gỡ khỏi bộ nhớ vật lý ngay lập tức** nếu còn được nạp qua JNI, được tham chiếu bởi thư viện khác, hoặc OS giữ handle. Việc close Arena là **kết thúc hợp đồng sử dụng qua lookup này**, không có nghĩa mọi tham chiếu ngoài JVM đã biến mất.

### 4.2. Các loại Arena

| Arena | Quyền truy cập và close | Phù hợp khi |
| --- | --- | --- |
| `Arena.ofConfined()` | Một owner thread; `close()` xác định | Downcalls đồng bộ một thread, scope ngắn |
| `Arena.ofShared()` | Có thể dùng từ nhiều threads; `close()` xác định nhưng phải phối hợp users | Các services chia sẻ functions/library qua threads |
| `Arena.ofAuto()` | Không `close` thủ công; GC quản lý thời điểm kết thúc không xác định | Chỉ khi không cần unload/cleanup có deadline |
| `Arena.global()` | Không hỗ trợ close; lifetime gần như suốt process/VM | Native library được giữ lâu dài có chủ đích |

Không tạo một `ofConfined()` trong helper rồi trả lookup hoặc symbol để caller dùng **sau khi helper đã close Arena**. Cũng không dùng `global()` cho mọi request chỉ để né quản lý lifetime nếu hệ thống cần unload hoặc có áp lực native resources.

## 5. `loaderLookup()` và `libraryLookup()` thấy các symbol khác nhau

### 5.1. Loader lookup không phải library lookup

~~~java
SymbolLookup loaderSymbols = SymbolLookup.loaderLookup();
~~~

`loaderLookup()` tìm symbol trong các native libraries mà **JVM đã nạp qua JNI** và **gắn với class loader của lớp đang gọi `loaderLookup()`**.

Ví dụ:

~~~java
System.loadLibrary("jniowner");

// Trong lớp dùng cùng class loader:
SymbolLookup loader = SymbolLookup.loaderLookup();
boolean found = loader.find("jniowner_hook_count").isPresent();
~~~

Nếu thư viện export `jniowner_hook_count` và load thành công, `found` là `true`. Nhưng `loaderLookup()` **không tự mở một file thư viện mới**, và nó **không** tìm tất cả OS libraries trong process.

Đặc điểm:

- **Dynamic lookup:** Nếu một JNI library mới sau đó được load bằng `System.loadLibrary` từ cùng loader, lookup đã tạo trước đó có thể thấy symbols của library mới.
- **Caller-sensitive:** “Cùng class loader” quan trọng. Plugin loader A và application loader B không nhất thiết nhìn cùng tập JNI library symbols.
- **Lifetime:** Các địa chỉ từ loader lookup được gắn với automatic scope giữ caller class loader reachable. Bạn **không** đóng lookup này như một confined Arena.
- Nếu lời gọi được thực hiện trong ngữ cảnh thiếu caller frame (ví dụ native-attached thread gọi trực tiếp), đặc tả quy định dùng **system class loader**.

### 5.2. `libraryLookup` không làm `loaderLookup` nhìn thấy library

Nếu **chỉ** làm:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup ffmSymbols =
            SymbolLookup.libraryLookup(
                    Path.of("/path/to/ffmside.so"), arena);

    boolean byFfm =
            ffmSymbols.find("ffmside_triple").isPresent();

    boolean byJniLoader =
            SymbolLookup.loaderLookup()
                    .find("ffmside_triple").isPresent();
}
~~~

Trong môi trường demo **không JNI-load ffmside** và không có library khác trong cùng class loader export cùng tên symbol: `byFfm` là `true`, `byJniLoader` là `false`.

**Không cố biến `loaderLookup` thành nơi tìm mọi shared library**. Nó chỉ phơi bày các symbols trong libraries mà **JNI loader registry** liên kết với caller class loader.

### 5.3. Vậy library đã nạp qua JNI có thể tra lại bằng FFM `libraryLookup` không?

**Có.** `SymbolLookup.libraryLookup(...)` có thể tạo lookup cho một thư viện L đã tồn tại trên OS, **kể cả L từng được nạp qua JNI**. Điều đó **không chuyển ownership JNI của class loader sang Arena**. OS dynamic-loader implementations có thể giữ cùng loaded image hoặc tăng reference count khi tạo lookup.

Nên phân biệt:

~~~text
JNI loader registry:         System.loadLibrary("L")
         |                                |
         v                                v
L gắn với ClassLoader CL           JNI_OnLoad (nếu có)
         |
         +--> loaderLookup() tìm symbols của L
         |
         +--> libraryLookup("L", arena) cũng có thể
              lấy symbols của L qua một handle FFM
              NHƯNG không chuyển L khỏi CL
~~~

Không rút kết luận rằng `arena.close()` sẽ xóa class-loader registration của JNI hoặc gọi `JNI_OnUnload`. Nếu muốn quản lý riêng theo Arena, dùng một thư viện chỉ FFM-load trong vòng đời xác định.

## 6. `Linker.defaultLookup()` là đường thứ ba

FFM còn có:

~~~java
Linker linker = Linker.nativeLinker();
SymbolLookup defaults = linker.defaultLookup();
~~~

`defaultLookup()` cung cấp symbols của những native libraries thông dụng theo **ABI/OS** mà linker hỗ trợ, ví dụ một số hàm libc. Nó không đồng nghĩa:

- `loaderLookup()` — các libraries gắn với caller class loader qua JNI.
- `libraryLookup(...)` — tập symbol của library cụ thể do caller yêu cầu.

Một số symbol có thể tình cờ xuất hiện ở nhiều lookup do chính sách OS/linker, nhưng **không nên phụ thuộc** vào việc `defaultLookup` nhìn thấy mọi thư viện bạn vừa `System.loadLibrary` hoặc `libraryLookup`. Muốn biết rõ symbol thuộc đâu, hãy chọn đúng lookup.

Có thể kết hợp với `SymbolLookup.or(...)` khi muốn fallback:

~~~java
SymbolLookup preferred = SymbolLookup.libraryLookup(
        somePath, arena);
SymbolLookup combined = preferred.or(
        SymbolLookup.loaderLookup());
~~~

Đây là **snippet minh họa**, `somePath`/`arena` do caller cung cấp. `or` thử `preferred` trước, khi không có symbol thì mới tra `loaderLookup`. Cách này hữu ích khi có nhiều nguồn symbol nhưng cần tránh **đụng tên**: hai thư viện khác nhau có cùng tên export sẽ được phân giải theo thứ tự lookup, không dựa vào “hàm nào đúng hơn”.

## 7. Hai hệ lifecycle: JNI hooks khác OS loader hooks

| Sự kiện | `System.loadLibrary("jniowner")` | `SymbolLookup.libraryLookup(ffmPath, arena)` |
| --- | --- | --- |
| OS thực hiện dynamic loading nếu cần | Có | Có |
| OS constructors / dynamic-loader initialization có thể chạy | Có | Có |
| JVM ghi nhận JNI library với class loader | Có | **Không tự làm** |
| JVM gọi `JNI_OnLoad` export từ JNI library | Có, khi JNI load phù hợp | **Không tự gọi** |
| JVM có thể gọi `JNI_OnUnload` theo class-loader GC | Có | Không theo Arena close |
| FFM `SymbolLookup.find` tìm export | Qua `loaderLookup` hoặc library lookup riêng | Qua chính library lookup đã tạo |
| Kết thúc ownership ở API | Class loader reachability / VM lifecycle | `Arena.close()` đối với arena explicit |

**Hàm `JNI_OnLoad` khác với static constructor của C/C++ library.**

Trong C/C++, có thể có static initialization, ELF constructors, Windows `DllMain` hoặc OS-level loader callbacks. Các phần đó có thể chạy chỉ vì OS loader mở library, **kể cả khi không có JNI registration**. `JNI_OnLoad` là **cơ chế do JVM chủ động tìm và gọi**, không phải callback tiêu chuẩn của `dlopen`/`LoadLibrary`.

Vì vậy nói “FFM `libraryLookup` không gọi `JNI_OnLoad`” **không có nghĩa** “FFM nạp thư viện mà không thực thi bất kỳ native code nào”. Chính vì dynamic load có thể chạy native constructors nên `SymbolLookup.libraryLookup` được phân loại là **restricted method**.

## 8. Ví dụ hoàn chỉnh: hai thư viện C và hai lớp Java

Mục tiêu là **chứng minh bằng stdout**:

1. `System.loadLibrary("jniowner")` chạy `JNI_OnLoad` của JNI library; native method hoạt động.
2. `SymbolLookup.loaderLookup()` từ cùng application class loader tìm được function export của JNI library.
3. `SymbolLookup.libraryLookup(Path, arena)` mở library `ffmside`.
4. Hàm C thuần trong `ffmside` được gọi qua `Linker.downcallHandle`.
5. `ffmside` *cũng có* symbol `JNI_OnLoad`, nhưng vì thư viện này chỉ được nạp bằng FFM, hook đó **không tự được JVM gọi**.
6. `loaderLookup()` không thấy `ffmside` vì nó không thuộc danh sách JNI-loaded libraries của class loader.

Ta dùng **hai thư viện riêng** để không bị hiệu ứng OS đã nạp cùng file từ trước gây khó diễn giải.

### 8.1. Cấu trúc thư mục

~~~text
jni-ffm-lookup-demo/
├── JniOwner.java
├── NativeLibraryComparison.java
├── jniowner.c
└── ffmside.c
~~~

Kết quả build sẽ bổ sung `.class` và các shared libraries đúng hệ điều hành.

### 8.2. Java: `JniOwner.java`

~~~java
public final class JniOwner {
    static {
        System.loadLibrary("jniowner");
    }

    private JniOwner() {
    }

    public static native int plusOne(int x);
}
~~~

Đây là lớp Java chứa native method được JVM liên kết bằng cơ chế JNI. Static initializer chỉ nạp `jniowner` **khi lớp được khởi tạo**, không phải “mỗi lần gọi `plusOne` lại chạy `JNI_OnLoad`”.

### 8.3. C: `jniowner.c`

~~~c
#include <jni.h>

static jint hook_count = 0;

/* Chỉ JVM JNI library loader chủ động gọi hook này. */
JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    ++hook_count;
    return JNI_VERSION_1_6;
}

/* Hàm triển khai Java static native int plusOne(int). */
JNIEXPORT jint JNICALL Java_JniOwner_plusOne(
        JNIEnv *env, jclass declaringClass, jint x) {
    (void) env;
    (void) declaringClass;
    return x + 1;
}

/* Symbol C thuần được export để FFM tìm qua loaderLookup. */
JNIEXPORT jint jniowner_hook_count(void) {
    return hook_count;
}
~~~

**Vì sao có cả ba function?**

- `JNI_OnLoad` là hook lifecycle JNI, tăng `hook_count` đúng khi JVM nạp thư viện.
- `Java_JniOwner_plusOne` liên kết với tên/signature `JniOwner.plusOne(int)` theo JNI name-based resolution.
- `jniowner_hook_count` là **hàm C không phải Java native method**, chỉ trả giá trị global C. Ta gọi nó qua FFM để quan sát hook thực sự đã chạy.

`JNIEXPORT` đảm bảo export symbol trên toolchain JNI được hỗ trợ. Với kiến trúc **x64/ARM64 tương ứng**, `jint` có kích thước 32-bit phù hợp `ValueLayout.JAVA_INT`; trên Windows **32-bit** cần xem thêm calling convention và decorated symbols, nên bài demo yêu cầu **64-bit JDK + compiler cùng kiến trúc**.

### 8.4. C: `ffmside.c`

~~~c
#include <jni.h>

static jint hook_count = 0;

/*
 * File này CŨNG export JNI_OnLoad để so sánh.
 * Nhưng ví dụ chỉ nạp ffmside bằng SymbolLookup.libraryLookup.
 * Vì không có JNI library load, hook này không tự chạy.
 */
JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    ++hook_count;
    return JNI_VERSION_1_6;
}

/* Hàm thuần C: Java sẽ gọi qua FFM downcall. */
JNIEXPORT jint ffmside_triple(jint value) {
    return value * 3;
}

/* Trả số lần JNI_OnLoad của ffmside được JVM gọi. */
JNIEXPORT jint ffmside_hook_count(void) {
    return hook_count;
}
~~~

**Quan trọng:** `ffmside_triple` không khai báo `JNIEnv *`, `jobject` hoặc `jclass` vì đây là **hàm C thông thường**, không phải JNI native method. `FunctionDescriptor` bên Java phải khớp `int32 -> int32`.

Một file nạp bằng FFM vẫn có thể chứa những export tên `JNI_OnLoad`, nhưng bản thân `libraryLookup` không thực hiện bước “JVM gọi hook”. Counter vẫn ở `0` cho tới khi có một **JNI load thực sự** theo điều kiện khác.

### 8.5. Java: `NativeLibraryComparison.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class NativeLibraryComparison {
    private NativeLibraryComparison() {
    }

    private static int callNoArg(
            Linker linker, SymbolLookup lookup, String name)
            throws Throwable {
        MethodHandle handle = linker.downcallHandle(
                lookup.find(name).orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT));
        return (int) handle.invokeExact();
    }

    private static int callIntArg(
            Linker linker, SymbolLookup lookup, String name,
            int value) throws Throwable {
        MethodHandle handle = linker.downcallHandle(
                lookup.find(name).orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));
        return (int) handle.invokeExact(value);
    }

    public static void main(String[] args) throws Throwable {
        // 1. Kích hoạt JNI library load của JniOwner.
        System.out.println("JNI result=" + JniOwner.plusOne(41));

        // 2. JNI loader lookup của cùng application class loader.
        SymbolLookup loader = SymbolLookup.loaderLookup();
        Linker linker = Linker.nativeLinker();

        int jniHookCount = callNoArg(
                linker, loader, "jniowner_hook_count");

        System.out.println("JNI_OnLoad count=" + jniHookCount);
        System.out.println(
                "loader sees JNI symbol="
                        + loader.find("jniowner_hook_count").isPresent());

        // 3. Mở riêng ffmside bằng FFM, không thông qua JNI loader.
        Path ffmPath = Path.of(
                System.mapLibraryName("ffmside")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup ffm =
                    SymbolLookup.libraryLookup(ffmPath, arena);

            int result = callIntArg(
                    linker, ffm, "ffmside_triple", 14);
            int ffmHookCount = callNoArg(
                    linker, ffm, "ffmside_hook_count");

            System.out.println("FFM result=" + result);
            System.out.println(
                    "FFM JNI_OnLoad count=" + ffmHookCount);
            System.out.println(
                    "loader sees FFM symbol="
                            + loader.find("ffmside_triple").isPresent());
        }
        // close arena ở đây: không gọi downcall từ ffm sau đó.
    }
}
~~~

**Chú thích các API:**

- `System.mapLibraryName("ffmside")` tạo tên file kiểu `libffmside.so` / `libffmside.dylib` / `ffmside.dll` theo OS. `toAbsolutePath()` làm rõ file trong thư mục chạy hiện tại.
- `SymbolLookup.loaderLookup()` được gọi từ `NativeLibraryComparison`; lớp này và `JniOwner` được nạp bởi **cùng application class loader** trong demo.
- `SymbolLookup.libraryLookup(ffmPath, arena)` dùng **đường dẫn absolute** thay vì phụ thuộc đường tìm OS.
- `FunctionDescriptor.of(ValueLayout.JAVA_INT)` mô tả hàm C trả `int32` và **không có tham số**.
- `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)` mô tả hàm C nhận **một `int32` và trả `int32`**.
- `MethodHandle.invokeExact` đòi kiểu chính xác, ở đây `(int) handle.invokeExact(value)` với `value` là `int`. Vì vậy helper khai báo `throws Throwable`.
- `try (Arena arena = Arena.ofConfined())` giữ thư viện `ffmside` và symbol segments hợp lệ trong các downcalls; nó close sau khi tất cả lời gọi hoàn thành.

**Không có “`JNIEnv *` tham số ẩn” ở FFM downcall** tới `ffmside_triple`. Còn JNI method `Java_JniOwner_plusOne` được JVM gọi với `JNIEnv *` và `jclass` trước tham số `jint x`.

### 8.6. Biên dịch Java

Dùng **JDK 22+**:

~~~bash
javac JniOwner.java NativeLibraryComparison.java
~~~

Không cần `--enable-preview` ở JDK 22 cho các API đã chuẩn hóa. Cần đảm bảo **JDK 22+ thực sự được chọn cho cả `javac` và `java`**.

### 8.7. Build trên Linux x64 hoặc ARM64

Đặt `JAVA_HOME` đến thư mục gốc JDK đang chạy; compile C bằng GCC hoặc Clang cùng kiến trúc JVM:

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jniowner.c -o libjniowner.so

cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  ffmside.c -o libffmside.so
~~~

Không cần liên kết trực tiếp `libjvm.so` khi shared JNI library chỉ nhận `JavaVM *` và `JNIEnv *` thông qua hook/native entry points. OS loader và JVM sẽ cung cấp giao diện JNI theo runtime tương ứng.

### 8.8. Build trên macOS x64 hoặc ARM64

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jniowner.c -o libjniowner.dylib

cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  ffmside.c -o libffmside.dylib
~~~

### 8.9. Build trên Windows x64

Mở **x64 Native Tools Command Prompt for Visual Studio** với JDK x64:

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniowner.c /link /OUT:jniowner.dll

cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" ffmside.c /link /OUT:ffmside.dll
~~~

Không chạy cả ba nhóm lệnh; dùng một nhóm phù hợp OS. Trong mọi trường hợp, đặt cả hai shared libraries **cùng thư mục làm việc** với hai file `.class`, vì demo lấy đường dẫn FFM tương ứng với thư mục hiện tại.

### 8.10. Chạy Java, bật native access

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  NativeLibraryComparison
~~~

Trên Windows Command Prompt, chạy một dòng:

~~~bat
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. NativeLibraryComparison
~~~

- `--enable-native-access=ALL-UNNAMED` cấp quyền dùng restricted FFM methods cho lớp trên classpath. Trong JDK 22, không bật có thể phát cảnh báo restricted native access; bật quyền rõ ràng giúp chương trình chạy không cảnh báo và không phụ thuộc các chính sách sẽ thay đổi ở các JDK sau.
- `-Djava.library.path=.` giúp `System.loadLibrary("jniowner")` tìm JNI library trong thư mục hiện tại.
- Phía FFM sử dụng `Path.toAbsolutePath()`, **không dựa vào `java.library.path`** để định vị `ffmside`.
- `--enable-native-access` không tự load thư viện, không tạo JNI registration và không thay việc kiểm tra ABI.

### 8.11. Stdout mong đợi

~~~text
JNI result=42
JNI_OnLoad count=1
loader sees JNI symbol=true
FFM result=42
FFM JNI_OnLoad count=0
loader sees FFM symbol=false
~~~

**Phân tích từng dòng:**

1. `JNI result=42`: JNI native method `plusOne(41)` của `JniOwner` trả `42`.
2. `JNI_OnLoad count=1`: JVM JNI loader gọi `JNI_OnLoad` của `jniowner` một lần trong lần nạp của demo.
3. `loader sees JNI symbol=true`: `loaderLookup` của application class loader thấy `jniowner_hook_count` được export từ JNI-loaded library.
4. `FFM result=42`: FFM downcall tới `ffmside_triple(14)` trả `42`.
5. `FFM JNI_OnLoad count=0`: mặc dù `ffmside` export `JNI_OnLoad`, cách `libraryLookup` **không tự gọi** hook JNI.
6. `loader sees FFM symbol=false`: `ffmside` chưa được nạp qua `System.loadLibrary` trong cùng class loader; loader lookup không chứa nó.

**Điều kiện để stdout có nghĩa:** chạy trong **JVM process mới**, nạp đúng hai thư viện vừa biên dịch, không có code khác gọi `System.loadLibrary("ffmside")` hoặc export trùng các symbol demo. Nếu ứng dụng thực đã nạp hoặc tái sử dụng thư viện theo đường JNI khác, giá trị counter và tập symbols có thể khác; ví dụ được thiết kế để cô lập hai trường hợp.

## 9. Sơ đồ nhìn từ góc JVM và OS loader

~~~text
                  JAVA APPLICATION (cùng ClassLoader CL)
                                   |
               +-------------------+-------------------+
               |                                       |
               v                                       v
    JniOwner.plusOne(41)                    NativeLibraryComparison
               |                                       |
               v                                       |
    System.loadLibrary("jniowner")                     |
               |                                       |
               v                                       v
      JVM JNI library registry                  Arena.ofConfined()
      quản lý (CL, jniowner)                           |
               |                                       v
               |                            SymbolLookup.libraryLookup(
               |                                  ffmsidePath, arena)
               v                                       |
          OS load JNI lib                              v
               |                                  OS load FFM lib
               v                                       |
         JVM gọi JNI_OnLoad                             |
               |                                       |
               v                                       v
     Java_JniOwner_plusOne                   ffmside_triple(14)
               |                                       |
               +---------------+-----------------------+
                               |
                  SymbolLookup.loaderLookup()
                    tìm JNI-loaded symbols,
                    KHÔNG tự nhìn thấy ffmside
                               |
                     arena.close() chỉ
                     kết thúc FFM lookup
                     không xóa JNI registry
~~~

Cả hai nhánh có thể đi qua **cùng OS dynamic loader** và có khả năng tham chiếu cùng native image nếu là cùng file. Vì vậy phải phân biệt:

- **OS load state**: thư viện nào đang được process map, số native references, dependencies.
- **JNI registration state**: class loader nào sở hữu một JNI library và JNI hooks nào đã chạy.
- **FFM lookup lifetime**: arena nào giữ quyền dùng một tập symbol addresses.

Ba lớp trạng thái **có liên quan**, nhưng **không thay thế lẫn nhau**.

## 10. Scope của symbol address, MethodHandle và quyền gọi lại

Một symbol lookup trả `MemorySegment` kích thước `0` chứa **địa chỉ hàm**. Đây không phải buffer dữ liệu kiểu `arena.allocate(1024)`. Không được dùng `get(ValueLayout.JAVA_INT, 0L)` để “đọc một int” từ symbol hàm; phải truyền địa chỉ vào linker với đúng `FunctionDescriptor`.

### 10.1. Không gọi hàm sau khi arena đóng

Anti-pattern:

~~~java
// SAI: giữ downcall handle trỏ tới thư viện của arena đã đóng.
MethodHandle saved;

try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup =
            SymbolLookup.libraryLookup(libraryPath, arena);

    saved = Linker.nativeLinker().downcallHandle(
            lookup.find("ffmside_triple").orElseThrow(),
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));
}

// Không gọi saved.invokeExact(5) ở đây.
// Library lookup đã hết scope: pointer không còn hợp lệ.
~~~

Đoạn này là **pseudocode Java**, biến `libraryPath` đến từ caller. Không cố dự đoán rằng mọi nền tảng sẽ ném cùng một exception an toàn khi gọi stale native function pointer; gọi một địa chỉ native đã bị unload có thể gây **JVM crash hoặc memory corruption**.

**Nguyên tắc:** method handle **không phải công cụ kéo dài lifetime của Arena**. Owner phải giữ arena còn sống cho tới khi tất cả foreign calls, callbacks và background jobs sử dụng thư viện đã hoàn thành.

### 10.2. Chia sẻ function symbols giữa nhiều threads

Với một service nhiều threads, `Arena.ofConfined()` có thể không phù hợp vì symbols từ lookup gắn với confined scope. Cân nhắc `Arena.ofShared()` rồi:

- Tạo lookup/MethodHandle khi khởi động service.
- Cho nhiều workers truy cập theo hợp đồng ABI và thread-safety của thư viện C.
- Dừng nhận task mới trước shutdown.
- Đợi **mọi downcalls** hoàn tất.
- Đóng shared arena **một lần** sau khi không ai còn dùng function pointers.

`Arena.ofShared()` **không bảo đảm hàm C là thread-safe**. Nếu native library dùng global state hoặc yêu cầu init/teardown riêng, phải tuân theo tài liệu thư viện và synchronization thích hợp.

### 10.3. Nếu native library được nạp ở nhiều nơi

Một file `libX.so` có thể đồng thời được tham chiếu bởi JNI load, FFM lookups và native dependencies. Khi một FFM arena đóng, OS thường giảm quyền sở hữu/reference liên quan lookup; file có thể **vẫn được giữ loaded** vì những người dùng khác.

Tránh ba giả định:

1. “`libraryLookup` luôn tạo bản sao lib mới trong RAM” — OS có thể dùng lại loaded image.
2. “`arena.close()` chắc chắn làm DLL/dylib biến mất ngay” — có thể còn references.
3. “`arena.close()` tương đương `JNI_OnUnload`” — **không đúng**. JNI class-loader lifecycle là chuyện khác.

## 11. Lỗi phổ biến khi trộn JNI và FFM

| Triệu chứng | Nguyên nhân gốc khả dĩ | Cách xử lý |
| --- | --- | --- |
| `System.loadLibrary` ném `UnsatisfiedLinkError` | Tên JNI library sai, `java.library.path` thiếu, sai ABI/dependency | Kiểm tra `System.mapLibraryName`, đường dẫn, CPU architecture và native deps |
| JNI method ném `UnsatisfiedLinkError` khi được gọi | Thư viện đã load nhưng tên `Java_*` hoặc `RegisterNatives` sai | So JNI header (`javac -h`), method descriptor và exports |
| `JNI_OnLoad` không chạy khi dùng `libraryLookup` | Không có JNI library load | **Đúng thiết kế**; nếu cần JNI setup hãy dùng cơ chế JNI |
| `loaderLookup().find("ffmSymbol")` rỗng | Thư viện chỉ nạp qua `libraryLookup` | Dùng **chính FFM lookup** trả về từ `libraryLookup` |
| `libraryLookup` không thấy symbol | Symbol không export, C++ name mangling, sai path, dependency, typo | Kiểm tra exports và dùng `extern "C"` với C++ |
| `libraryLookup` ném `IllegalArgumentException` | Tên/path không xác định thư viện hợp lệ | Dùng absolute path đến đúng `.so/.dll/.dylib` |
| `libraryLookup` ném `IllegalCallerException` | Module caller chưa được cấp native access | Dùng `--enable-native-access=ALL-UNNAMED` trên classpath hoặc đúng module name |
| `lookup.find("foo").orElseThrow()` ném `NoSuchElementException` | `find` trả `Optional.empty()` | Kiểm tra tên symbol, export visibility và library |
| `MethodHandle.invokeExact` ném `WrongMethodTypeException` | Java argument/return types không trùng descriptor | Kiểm tra `FunctionDescriptor` và `MethodHandle.type()` |
| JVM crash dù MethodHandle types có vẻ đúng | ABI C thực khác descriptor: struct/varargs/pointer/calling convention | Kiểm tra C signature, linker canonical layouts, native ABI; lỗi có thể không được Java phát hiện |
| `WrongThreadException` khi dùng lookup/symbol | Confined arena được dùng từ thread khác | Chọn đúng owner thread hoặc dùng shared arena |
| Lỗi sau `Arena.close()` | Gọi stale symbol/MethodHandle | Đảm bảo arena còn sống trong mọi downcall; không gọi sau close |
| Class loader plugin không unload được | `loaderLookup`/symbol hoặc static references còn reachable | Kiểm tra reachability và chủ sở hữu; không giữ lâu ngoài ý muốn |
| Close Arena nhưng `JNI_OnUnload` chưa chạy | Arena close không xóa JNI registration | Quản lý JNI class loader riêng; không đồng nhất lifecycle |
| Cùng JNI library nạp từ loader khác bị từ chối | JNI có chính sách một library không gắn với hai loaders độc lập | Thiết kế native bridge loader ổn định hoặc phân tách deployment |

### 11.1. Các công cụ chẩn đoán native symbols

Linux:

~~~bash
nm -D libjniowner.so
nm -D libffmside.so
~~~

macOS:

~~~bash
nm -gU libjniowner.dylib
nm -gU libffmside.dylib
~~~

Windows Developer Command Prompt:

~~~bat
dumpbin /exports jniowner.dll
dumpbin /exports ffmside.dll
~~~

Phải nhìn thấy các exported symbols tương ứng (trên một số nền tảng `nm` hiển thị dấu gạch dưới prefix theo binary format). Với code C++ phải export bằng `extern "C"` để tránh C++ name mangling của các functions dùng cho FFM (và export `JNI_OnLoad` theo đúng JNI C linkage).

Không tự suy rằng `System.loadLibrary("jniowner")` thành công thì mọi symbol C có thể tra bằng loader lookup: symbol phải thực sự được export/visible. Native internal `static` function trong C không được export chỉ vì thư viện đã được JNI nạp.

## 12. Cẩn thận với `FunctionDescriptor` và JNI signature

Hai hàm sau đều nhận một số nguyên và trả một số nguyên, nhưng **giao diện gọi khác nhau**:

~~~c
/* Native implementation của Java JNI method. */
JNIEXPORT jint JNICALL Java_JniOwner_plusOne(
        JNIEnv *env, jclass clazz, jint x);

/* Hàm C thuần dùng cho FFM direct downcall. */
JNIEXPORT jint ffmside_triple(jint x);
~~~

Với JNI method, JVM tự truyền `JNIEnv *` và `jclass`; application Java **không** tự dựng `FunctionDescriptor` cho native method đó. Với `ffmside_triple`, FFM `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` mô tả đúng **một đối số int** và **giá trị trả về int**.

**Không lấy địa chỉ `Java_JniOwner_plusOne` rồi gọi bằng descriptor một đối số int**. Hàm đó cần thêm hai tham số ABI. Sai descriptor có thể gây crash hoặc đọc dữ liệu rác chứ không chỉ là `WrongMethodTypeException`.

Một foreign function còn có thể:

- Trả `void`: `FunctionDescriptor.ofVoid(...)`.
- Nhận pointer: dùng `ValueLayout.ADDRESS` và `MemorySegment` carrier.
- Nhận/ trả `long` của C: cần kiểm tra ABI; trên Windows x64 kiểu C `long` thường 32-bit, còn Linux/x64 thường 64-bit.
- Nhận `struct`: phải mô tả `MemoryLayout` và padding/alignment đúng ABI.
- Là hàm variadic: cần dùng FFM linker option thích hợp cho variadic arguments, không gán nhầm một descriptor cố định.

**FFM không biết tên hàm C mang kiểu gì.** `lookup.find(...)` chỉ cung cấp địa chỉ; `FunctionDescriptor` là cam kết của lập trình viên rằng signature ABI đã được xác minh.

### 12.1. Native access là kiểm soát khả năng, không phải sandbox

Trong JDK 22, `SymbolLookup.libraryLookup(...)` và `Linker.downcallHandle(...)` là **restricted methods**. Dùng:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeLibraryComparison
~~~

Trong dự án dùng Java modules, nên cấp native access **chỉ cho module cần dùng FFM** thay vì `ALL-UNNAMED` cho mọi classpath. Cờ này **không kiểm tra chất lượng hoặc độ tin cậy của DLL**; một thư viện độc hại hoặc có lỗi ABI vẫn có thể làm hỏng tiến trình. Chỉ nạp libraries từ đường dẫn đáng tin và kiểm soát deployment.

**Khác nhau theo phiên bản:** kể từ các JDK sau 22, chính sách cảnh báo/từ chối restricted native access tiếp tục phát triển. Chạy command có quyền native access rõ ràng giúp ví dụ không phụ thuộc chính sách mặc định theo từng phiên bản.

## 13. Cùng một thư viện được gọi qua cả JNI và FFM: khi nào hợp lý?

Có những ứng dụng chuyển đổi dần từ JNI sang FFM hoặc có library export **cả JNI bridge lẫn C ABI functions**. Khi đó:

- Thư viện có thể tiếp tục nạp qua `System.loadLibrary` để thực hiện JNI registration và dùng `JNI_OnLoad`.
- FFM có thể tra symbol C thuần từ chính JNI-loaded library qua **`SymbolLookup.loaderLookup()`**, miễn caller class loader phù hợp.
- Không cần mở thêm `libraryLookup` chỉ để tra một symbol đã có trong loader lookup, nếu JNI ownership đã đáp ứng yêu cầu và export visible.
- Nếu phải dùng `libraryLookup` riêng với cùng file, hãy xem đó là **một OS-level reference/lookup với Arena lifetime riêng**, không phải yêu cầu JVM nạp JNI lần thứ hai.
- Không gọi JNI functions với FFM descriptor thiếu `JNIEnv *`/`jclass`; nên export một **C ABI wrapper thuần** riêng cho FFM.

### 13.1. Mẫu kiến trúc khi di chuyển dần

~~~text
Java app / service
      |
      +-- JNI bridge (legacy)
      |     System.loadLibrary("legacy")
      |     native methods -> Java_... / RegisterNatives
      |     JNI_OnLoad for JNI setup
      |
      +-- FFM bridge (new)
            SymbolLookup.loaderLookup() nếu dùng C symbols
            trong thư viện JNI đang được nạp
            hoặc
            SymbolLookup.libraryLookup(newLibPath, arena)
            nếu thư viện được quản lý riêng bằng FFM
            |
            FunctionDescriptor + Linker
            |
            MethodHandle.invokeExact(...)
~~~

Các yếu tố cần quyết định **trước** khi viết code:

1. Native library có **C ABI public/stable** hay chỉ là các JNI entrypoints?
2. Ai sở hữu init/teardown? JNI hooks, native API tường minh hay RAII của library?
3. Class loader nào sở hữu JNI library? Có plugin/reload không?
4. Dữ liệu và function pointers cần tồn tại bao lâu; Arena nào quản lý?
5. Có native background threads giữ pointers? Khi nào được close/unload?
6. Có tình trạng `libraryLookup` và JNI cùng nạp cùng file khiến ABI/static global state bị chia sẻ ngoài ý muốn?

Hợp đồng init/teardown tốt thường có hàm C tường minh như `library_init()`/`library_shutdown()` nếu thư viện cần dùng từ nhiều runtime. **Không giả định JNI_OnLoad là API init phổ quát cho mọi consumer**, vì OS loader/FFM không tự thực hiện JNI hook.

## 14. Vì sao không nên tự gọi `JNI_OnLoad` qua FFM?

Giả sử `libraryLookup` tìm thấy exported symbol `JNI_OnLoad`. Có thể ai đó nghĩ: “Mình sẽ downcall trực tiếp hook đó để khởi tạo FFM library”. Đây **không phải cách thay thế** JNI library loading vì:

- `JNI_OnLoad` nhận `JavaVM *` và một pointer reserved theo JNI contract; Java FFM app không có lý do chính đáng để giả lập JVM loader handshake.
- JNI OnLoad có thể gọi `FindClass` và `RegisterNatives` dựa vào **ngữ cảnh class loader** mà JNI loader tạo. Gọi trực tiếp từ FFM không tái tạo đầy đủ ngữ cảnh đó.
- JVM không ghi nhận thư viện trong JNI registry chỉ vì một native function có tên `JNI_OnLoad` được gọi bằng downcall.
- Có thể khởi tạo state nhiều lần, thứ tự sai hoặc gây lỗi nếu sau đó JNI loader thực sự chạy hook.
- Khi arena đóng, `JNI_OnUnload` sẽ không tự đối ứng với lời gọi giả mạo.

**Đúng cách:** dùng `System.loadLibrary` nếu cần JNI library/lifecycle; dùng `libraryLookup` nếu cần C symbols qua FFM và native library có cơ chế init/cleanup thích hợp cho FFM.

## 15. Tình huống lifetime thực tế

### 15.1. Confined library lookup cho một thao tác đồng bộ

~~~java
void runOnce() throws Throwable {
    try (Arena arena = Arena.ofConfined()) {
        SymbolLookup lookup = SymbolLookup.libraryLookup(
                Path.of("/trusted/lib/tool.so"), arena);

        var fn = Linker.nativeLinker().downcallHandle(
                lookup.find("run_tool").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT));

        int rc = (int) fn.invokeExact();
        // Đọc kết quả, kiểm tra rc trước khi close.
    }
}
~~~

Snippet trên là **minh họa không độc lập**: đường dẫn C và tên symbol chỉ là ví dụ; khai báo imports/ABI theo dự án. Với library nạp/tắt lặp lại rất nhiều lần, overhead `dlopen/dlclose` có thể đáng kể; cân nhắc giữ một lookup lâu hơn phù hợp với service lifetime nếu điều này đúng với yêu cầu.

### 15.2. Library shared theo service lifecycle

~~~java
// Pseudocode Java mô tả kiến trúc, không chạy độc lập.
final class NativeService implements AutoCloseable {
    private final Arena arena = Arena.ofShared();
    private final SymbolLookup symbols =
            SymbolLookup.libraryLookup(verifiedPath, arena);

    void runTask() {
        // Sử dụng symbol + linker handle từ library khi arena còn sống.
        // Đồng bộ native global state nếu thư viện không thread-safe.
    }

    @Override
    public void close() {
        // Ngừng nhận công việc mới.
        // Đợi toàn bộ worker/downcall đang chạy hoàn thành.
        arena.close();
    }
}
~~~

Đây là **pseudocode**, `verifiedPath` và code worker coordination chưa được định nghĩa. Cố tình không trình bày thành source runnable vì việc đóng shared library đúng cách đòi lifecycle, task tracking và error handling riêng của dự án.

### 15.3. JNI-loaded library trong plugin class loader

Nếu plugin nạp JNI library bằng `System.loadLibrary`, đừng để một singleton global vô tình giữ mãi `SymbolLookup.loaderLookup()` hoặc symbol segment của plugin. Theo javadoc, loader lookup có scope giúp giữ caller class loader reachable; vì vậy việc cache ở một class loader lâu sống có thể **ngăn JNI library unload** dù plugin logic đã bị loại bỏ.

Khi muốn unload plugin đúng cách:

- Ngừng native calls/callbacks và native threads liên quan.
- Xóa references tới plugin classes, class loaders, JNI global references khi phù hợp.
- Không giữ loader lookup/symbols trong cache vĩnh viễn ngoài plugin owner.
- Không trông đợi `JNI_OnUnload` chạy tức thì chỉ vì bạn bỏ một Java reference.
- Cân nhắc tách native bridge sang loader ổn định nếu thư viện không hỗ trợ reload.

## 16. Câu hỏi và đáp án tự kiểm tra

**1.** Sau khi dùng `SymbolLookup.libraryLookup(path, arena)`, `SymbolLookup.loaderLookup()` cùng app class loader có tự nhìn thấy symbol của library đó không?

**Đáp án:** Không. `loaderLookup` chỉ cho các libraries nạp qua JNI và gắn với caller class loader; FFM lookup không tự đăng ký JNI library.

**2.** Thư viện `ffmside` export `JNI_OnLoad`. Vì sao ví dụ trả hook count 0?

**Đáp án:** Vì thư viện được nạp **chỉ** qua `libraryLookup`. OS dynamic loading không đồng nghĩa JVM gọi JNI lifecycle hook. Không có JNI load nào trong demo dành cho `ffmside`.

**3.** Một library đã `System.loadLibrary` có thể dùng FFM tìm C symbol của chính nó không?

**Đáp án:** Có. `SymbolLookup.loaderLookup()` tìm symbols của JNI-loaded libraries gắn với caller loader. `libraryLookup` cũng có thể tìm từ thư viện đó qua một lookup riêng, nhưng không chuyển class-loader ownership.

**4.** Có thể gọi method handle trỏ tới symbol của `libraryLookup` sau khi arena đã close không?

**Đáp án:** Không. Symbol address gắn với scope của arena. Gọi pointer đã hết hiệu lực có thể lỗi nghiêm trọng, kể cả crash. Chỉ close sau khi mọi foreign calls hoàn tất.

**5.** `JNI_OnUnload` có tự được gọi khi `Arena.close()` không?

**Đáp án:** Không. Đó là **JNI class-loader lifecycle hook**, không phải callback của việc đóng FFM library lookup.

**6.** Tại sao cả `JNI_OnLoad` và một C++ constructor có thể được gọi vào những thời điểm khác nhau?

**Đáp án:** C++/OS constructors thuộc **OS dynamic loader initialization**. `JNI_OnLoad` do **JVM JNI loader** chủ động gọi sau khi load theo cơ chế JNI. FFM có thể kích hoạt OS constructor mà không gọi JNI_OnLoad.

**7.** Không tìm được `ffi_process` bằng `loaderLookup`. Có phải file native chắc chắn chưa có trong RAM?

**Đáp án:** Không. Nó có thể đã được nạp qua FFM, OS dependency hoặc loader khác. `loaderLookup` chỉ xét JNI libraries gắn với caller class loader, không phải toàn process.

**8.** Trong FFM, nếu C khai báo `int triple(int)`, nên chọn `FunctionDescriptor` gì?

**Đáp án:** Trên ABI demo x64, `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)`: trả `int` và nhận một `int`. Java invocation dùng `(int) methodHandle.invokeExact(intValue)`.

**9.** Tại sao cần `--enable-native-access=ALL-UNNAMED` khi chạy ví dụ JDK 22?

**Đáp án:** `libraryLookup` và `downcallHandle` thuộc restricted FFM APIs. Cấp native access rõ ràng cho classpath code giúp tránh cảnh báo và các hạn chế theo chính sách JVM; không biến native library thành sandbox an toàn.

**10.** Vì sao không nên gọi trực tiếp export `JNI_OnLoad` qua FFM?

**Đáp án:** Nó không thực hiện JNI library registration, không tạo class-loader loading context đúng và có thể làm JNI setup chạy sai thứ tự hoặc lặp lại. Muốn dùng JNI cần `System.loadLibrary`.

**11.** Nếu hai FFM lookups hoặc một JNI load và một FFM lookup cùng trỏ tới một file, đóng một Arena có bảo đảm unload file ngay không?

**Đáp án:** Không. OS có thể giữ thư viện loaded do references khác. Arena close kết thúc **lookup ownership** của Arena đó, không xóa mọi OS/JNI references.

**12.** Khi nào nên dùng `Linker.defaultLookup()` thay vì `libraryLookup`?

**Đáp án:** Khi cần symbols trong các native libraries mặc định do linker/OS hỗ trợ (ví dụ libc). Muốn một custom library cụ thể, dùng `libraryLookup`; muốn library JNI thuộc class loader, dùng `loaderLookup`.

## 17. Checklist khi chọn cơ chế nạp

- Thư viện có cần **JNI native methods**, `JNI_OnLoad` hoặc `RegisterNatives` không? → Chọn cơ chế JNI.
- Thư viện chủ yếu có **C ABI functions** và cần gọi bằng `FunctionDescriptor`? → Chọn FFM library lookup.
- Thư viện đã được nạp qua JNI bởi **cùng class loader**? → Thử `loaderLookup` trước khi mở lookup FFM riêng.
- Cần tự kiểm soát thời điểm giải phóng FFM library? → Chọn confined/shared Arena và tổ chức ownership rõ.
- Có chạy nhiều threads/downcalls song song? → Dùng shared arena khi phù hợp, phối hợp stop/join/close và bảo đảm C thread-safety.
- Library có JNI hook nhưng được nạp qua FFM? → **Không** kỳ vọng hook được gọi.
- Đã kiểm tra exported symbols bằng `nm`/`dumpbin`, native dependencies và đúng CPU architecture?
- `FunctionDescriptor` có đúng **C ABI signature**, không lẫn hai tham số ngầm của JNI?
- Native access đã được cấp cho module/classpath sử dụng restricted FFM APIs?
- Có một đường shutdown rõ ràng, không còn downcalls/native callbacks khi close?
- Có plugin class loaders? → Cẩn thận `loaderLookup` giữ class loader reachable và JNI library có thể không unload.
- Có vô tình phụ thuộc hành vi refcount/dlopen của một OS để suy ra behavior Java trên OS khác?

## 18. Nguồn đọc chính thức

- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup`, `loaderLookup`, `defaultLookup`, dynamic visibility và quy tắc scope.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `downcallHandle`, mapping C ABI và restricted access.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): xác định kiểu tham số/trả về native.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): lifetime, confined/shared/automatic/global scopes.
- [Oracle Java SE 22 — Restricted Methods](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html): `--enable-native-access` và các API restricted.
- [Oracle Java SE 22 — JNI Invocation API](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/invocation.html): cơ chế quản lý JNI libraries và lifecycle `JNI_OnLoad`/`JNI_OnUnload`.
- [Oracle Java SE 22 — System.loadLibrary](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): quy tắc tên library và JNI load.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chính thức từ JDK 22.

**Ghi nhớ:** `System.loadLibrary` → **JVM JNI registry + class loader + JNI lifecycle**. `SymbolLookup.libraryLookup` → **OS library lookup + Arena lifetime + FFM symbols**. `SymbolLookup.loaderLookup` là chiếc cầu tra symbol từ **những thư viện JNI đã nạp**, không phải một lệnh tải thư viện mới hay một danh sách mọi native code trong process.
