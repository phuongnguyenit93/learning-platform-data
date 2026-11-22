# Phân biệt API FFM thử nghiệm ở JDK 21 với API chính thức từ JDK 22

## 1. Vì sao cần phân biệt JDK 21 và JDK 22?

**Foreign Function & Memory API (FFM)** cho phép Java gọi hàm native theo C ABI và thao tác với vùng nhớ bên ngoài Java heap. Thay vì phải viết một lớp JNI C cho mọi lời gọi, Java có thể lấy địa chỉ symbol trong native library, tạo `MethodHandle` thông qua `Linker` và dùng `MemorySegment`/`Arena` để quản lý dữ liệu.

**Điểm mấu chốt của đề bài:**

- **JDK 21:** FFM thuộc **JEP 442 — Third Preview**. Đây là API thử nghiệm ở mức *preview*, chưa chính thức ổn định. Việc biên dịch và chạy chương trình sử dụng FFM cần bật `--enable-preview`.
- **JDK 22:** FFM được **hoàn thiện (finalized) theo JEP 454** và trở thành API chính thức trong Java SE 22. Mã sử dụng **FFM final** không cần `--enable-preview` chỉ vì FFM.
- **Không chỉ thay cờ chạy:** một số tên method thay đổi từ 21 sang 22, nổi bật là `allocateUtf8String` → `allocateFrom`, `allocateArray` → `allocateFrom`, `getUtf8String` → `getString`, `setUtf8String` → `setString`.
- **Không nhầm preview với restricted native access:** sau khi FFM được final ở 22, thao tác liên kết/gọi native thuộc nhóm restricted vẫn cần xử lý chính sách quyền `--enable-native-access`.

Mục tiêu của bài: hiểu trạng thái của API theo từng phiên bản, nhận diện thay đổi thật sự trong source, biết chính xác lệnh `javac`/`java`, chạy được ví dụ JDK 21 và JDK 22, đồng thời tránh các lỗi do native ABI, scope và class file preview.

## 2. Dòng thời gian của FFM từ incubator đến final

| JDK | JEP | Trạng thái | Vị trí đáng chú ý |
|---|---|---|---|
| **17** | JEP 412 | First incubator | `jdk.incubator.foreign` |
| **18** | JEP 419 | Second incubator | `jdk.incubator.foreign` |
| **19** | JEP 424 | First preview | `java.lang.foreign` |
| **20** | JEP 434 | Second preview | `java.lang.foreign` |
| **21** | **JEP 442** | **Third preview** | `java.lang.foreign`, cần preview flags |
| **22** | **JEP 454** | **Final / standard** | `java.lang.foreign`, không còn preview cho FFM |

**Incubator** là giai đoạn API được thử nghiệm trong module dành riêng, có thể đổi thiết kế hoặc tên lớn. **Preview** là bước tiến gần hơn tới chuẩn, được tích hợp vào JDK nhưng vẫn **chưa vĩnh viễn**; người dùng phải bật cờ preview tường minh. **Final** là trạng thái API chuẩn của Java SE.

Đừng viết rằng “FFM được ra mắt chính thức trong Java 21”: JDK 21 chỉ có bản third preview. JDK 22 là bản **đầu tiên** chốt FFM thành API chính thức. Một ứng dụng có thể dùng JDK 22 nhưng vẫn bật preview cho **tính năng khác**; điều đó không làm FFM trở lại preview.

Đặc biệt, các hướng dẫn cũ chứa:

~~~java
import jdk.incubator.foreign.*;
~~~

là từ giai đoạn incubator (chẳng hạn 17/18), **không phải** ví dụ đúng cho FFM third preview 21 hoặc final 22. Trong hai bản cần học ở đây, import sẽ là `java.lang.foreign`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

Hai khối trên là **trích đoạn import**, không phải chương trình Java độc lập.

## 3. Các khái niệm nền tảng được giữ lại qua hai phiên bản

| Kiểu API | Vai trò |
|---|---|
| `Arena` | Cấp phát native memory và quản lý thời gian sống; hỗ trợ arena confined, shared, automatic, global |
| `MemorySegment` | Biểu diễn vùng bộ nhớ và địa chỉ native; có kiểm tra kích thước, scope, thread |
| `MemoryLayout` và `ValueLayout` | Mô tả kích thước/căn lề/bố cục dữ liệu native và kiểu carrier Java |
| `FunctionDescriptor` | Diễn tả chữ ký **hàm C** theo native ABI, không phải chữ ký JVM kiểu JNI |
| `Linker` | Chuyển `FunctionDescriptor` và địa chỉ native thành `MethodHandle`; hỗ trợ upcall |
| `SymbolLookup` | Tìm native symbol trong thư viện hoặc tập lookup phù hợp |
| `MethodHandle` | Đối tượng JVM đại diện một lời gọi có chữ ký Java được xác định |

Ví dụ sơ đồ downcall:

~~~text
Java program
    |
    | SymbolLookup.libraryLookup(path, arena)
    v
Native library được tải và có symbol "ffm_add"
    |
    | lookup.find("ffm_add")
    v
MemorySegment biểu diễn địa chỉ native function
    |
    | Linker.nativeLinker().downcallHandle(symbol, FunctionDescriptor)
    v
MethodHandle trong Java
    |
    | invokeExact(7, 5)
    v
C function ffm_add(7, 5)
    |
    v
Java nhận 12
~~~

Khi FFM được final, các ý tưởng `Arena`/`MemorySegment`/`Linker` không biến mất. Sự khác biệt chính là **trạng thái API**, một số phương thức đã được **chuẩn hóa tên và khả năng**, và cấu hình build/run. Không nên giả định “cùng tên class” có nghĩa source code của mọi phiên bản hoàn toàn tương thích.

## 4. Bảng khác biệt JDK 21 preview và JDK 22 final

| Nội dung | **JDK 21 (JEP 442)** | **JDK 22 (JEP 454)** |
|---|---|---|
| API status | Third preview | Final |
| Package | `java.lang.foreign` | `java.lang.foreign` |
| Module | `java.base` | `java.base` |
| Compile dùng FFM | `javac --enable-preview --release 21 ...` | `javac --release 22 ...` |
| Run dùng FFM | `java --enable-preview ...` | `java ...` |
| Cấp phát chuỗi C UTF-8 | `arena.allocateUtf8String("Hi")` | `arena.allocateFrom("Hi")` |
| Cấp phát native array có dữ liệu | `arena.allocateArray(JAVA_INT, 1, 2, 3)` | `arena.allocateFrom(JAVA_INT, 1, 2, 3)` |
| Cấp phát và khởi tạo một primitive | `arena.allocate(JAVA_INT, 42)` | `arena.allocateFrom(JAVA_INT, 42)` |
| Đọc C string UTF-8 | `segment.getUtf8String(0)` | `segment.getString(0)` |
| Ghi C string UTF-8 | `segment.setUtf8String(0, "Hi")` | `segment.setString(0, "Hi")` |
| Chỉ định charset cho C string | Các API chuyên UTF-8 | Có `allocateFrom(String, Charset)` và `getString`/`setString` với `Charset` |
| Canonical layout của C ABI | Chưa có `Linker.canonicalLayouts()` | Có `Linker.canonicalLayouts()` |
| Restricted native calls | Chính sách `--enable-native-access` | **Vẫn có**, độc lập với preview |
| `Arena.ofConfined()`, `FunctionDescriptor.of(...)` | Có (preview) | Có (final) |

**Không phải toàn bộ API đã bị viết lại:** code sử dụng `Linker.nativeLinker`, `SymbolLookup.libraryLookup` và `FunctionDescriptor.of` cho các trường hợp cơ bản có thể trông gần như giống hệt giữa hai phiên bản. Nhưng code dùng các overload tạo chuỗi/mảng native kiểu cũ có thể không biên dịch trên 22.

Cần phân biệt ba dạng cấp phát:

~~~text
JDK 22:
arena.allocate(16)                   // Cấp 16 byte, không có dữ liệu nguồn
arena.allocate(ValueLayout.JAVA_INT) // Cấp vùng theo layout
arena.allocateFrom(JAVA_INT, 42)      // Cấp vùng rồi chép một giá trị int
arena.allocateFrom(JAVA_INT, 1,2,3)   // Cấp vùng rồi chép các phần tử int
~~~

Đây là **so sánh cú pháp**, không phải tệp Java độc lập. Không thay tất cả `allocate(...)` thành `allocateFrom(...)` một cách máy móc: chỉ chọn `allocateFrom` khi thực sự **có dữ liệu khởi tạo đầu vào**.

## 5. Ví dụ chạy được trên JDK 21: phần foreign memory preview

Trước tiên thực hành chỉ với bộ nhớ để tránh sự khác nhau của native library và C ABI. Trong thư mục làm việc, tạo tệp đúng tên **`Ffm21Memory.java`**.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class Ffm21Memory {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers =
                    arena.allocateArray(ValueLayout.JAVA_INT, 2, 4, 6);

            int total =
                    numbers.getAtIndex(ValueLayout.JAVA_INT, 0)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 1)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 2);

            MemorySegment text = arena.allocateUtf8String("FFM");
            System.out.println("sum = " + total);
            System.out.println("text = " + text.getUtf8String(0));
        }
    }
}
~~~

Tệp trên là **chương trình Java 21 đầy đủ**. Kiểm tra terminal đang dùng **JDK 21** trước khi biên dịch:

~~~bash
java -version
javac -version
javac --enable-preview --release 21 Ffm21Memory.java
java --enable-preview Ffm21Memory
~~~

**Stdout của chương trình:**

~~~text
sum = 12
text = FFM
~~~

Compiler/JVM có thể in thêm **preview diagnostics** trên stderr; các dòng đó không phải stdout ứng dụng.

Cơ chế:

1. `Arena.ofConfined()` tạo một arena quản lý vùng nhớ native có vòng đời rõ ràng, gắn với thread hiện tại.
2. `allocateArray(JAVA_INT, 2, 4, 6)` cấp phát bộ nhớ cho ba số nguyên và chép chúng vào segment.
3. `getAtIndex(JAVA_INT, i)` đọc phần tử thứ `i` theo đơn vị **phần tử**, không phải byte offset. `2 + 4 + 6 = 12`.
4. `allocateUtf8String("FFM")` mã hóa Java string thành chuỗi C null-terminated UTF-8.
5. `getUtf8String(0)` đọc chuỗi từ offset byte 0 tới dấu NUL đầu tiên.
6. Try-with-resources gọi `arena.close()` khi kết thúc. Dùng segment đã thuộc arena đóng sẽ vi phạm vòng đời.

Vì đây chỉ là **cấp phát và đọc bộ nhớ**, không tạo native downcall handle hay tải library bằng restricted lookup, ví dụ không cần `--enable-native-access`. Nó **vẫn cần `--enable-preview`**, vì API FFM trên JDK 21 chưa finalized.

### 5.1. Những method cũ JDK 21 cần nhận diện

~~~java
// Trích đoạn trong JDK 21 preview, giả sử arena/segment hợp lệ.
arena.allocateUtf8String("Hello");
arena.allocateArray(ValueLayout.JAVA_INT, 10, 20, 30);
arena.allocate(ValueLayout.JAVA_INT, 42);

segment.getUtf8String(0);
segment.setUtf8String(0, "OK"); // Segment phải đủ byte.
~~~

Đây là **trích đoạn minh họa**, không phải chương trình hoàn chỉnh. Ba dòng `allocate...` vừa chỉ ra ba kiểu khởi tạo từ dữ liệu nguồn. Trong 22, những kiểu sử dụng đó được chuẩn hóa bằng tên `allocateFrom`. Không sao chép nguyên các method trên vào dự án 22.

## 6. Ví dụ tương đương chạy được trên JDK 22 final

Tạo tệp **`Ffm22Memory.java`**, không dùng lại tên class `Ffm21Memory` để tránh nhầm artifact.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class Ffm22Memory {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers =
                    arena.allocateFrom(ValueLayout.JAVA_INT, 2, 4, 6);

            int total =
                    numbers.getAtIndex(ValueLayout.JAVA_INT, 0)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 1)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 2);

            MemorySegment text = arena.allocateFrom("FFM");
            System.out.println("sum = " + total);
            System.out.println("text = " + text.getString(0));
        }
    }
}
~~~

Dùng **JDK 22**:

~~~bash
java -version
javac -version
javac --release 22 Ffm22Memory.java
java Ffm22Memory
~~~

**Stdout chính xác:**

~~~text
sum = 12
text = FFM
~~~

Phép tính và vùng nhớ tương đương ví dụ 21; chỉ đổi API liên quan đến **khởi tạo dữ liệu** và **đọc C string**, đồng thời bỏ cờ preview.

So sánh các dòng quan trọng:

~~~diff
- arena.allocateArray(ValueLayout.JAVA_INT, 2, 4, 6)
+ arena.allocateFrom(ValueLayout.JAVA_INT, 2, 4, 6)

- arena.allocateUtf8String("FFM")
+ arena.allocateFrom("FFM")

- text.getUtf8String(0)
+ text.getString(0)
~~~

Diff chỉ minh họa những chỗ cần đổi; tệp chạy được đầy đủ nằm ở trên.

### 6.1. Khác biệt về string charset

JDK 22 cho phép thao tác với **C string** dùng charset được chỉ định, ví dụ:

~~~java
// JDK 22, trích đoạn trong phạm vi Arena arena đang mở.
MemorySegment utf8 = arena.allocateFrom(
        "Java", java.nio.charset.StandardCharsets.UTF_8
);
String text = utf8.getString(
        0, java.nio.charset.StandardCharsets.UTF_8
);
~~~

Đây không phải tệp Java chạy độc lập. Nếu không truyền `Charset`, `allocateFrom(String)` và `getString(long)` dùng UTF-8 theo đặc tả. C string có **byte NUL** kết thúc; nếu nội dung chứa NUL ở giữa, cách đọc chuỗi có thể bị ngắt sớm. Khi dùng `setString`, phải cấp **đủ byte** cho chuỗi được mã hóa và terminator, không chỉ dựa vào `String.length()`.

Không được cho rằng một Java `char` luôn tương ứng một byte UTF-8. Với các ký tự tiếng Việt hoặc emoji, kích thước UTF-8 thường khác số code units UTF-16. Mỗi khi trao đổi với C library, hãy kiểm tra charset và quy tắc độ dài của chính thư viện đó.

## 7. Ví dụ native downcall — cùng một thư viện C, hai bản JDK

Để học **phần foreign function** của FFM, ta dùng một hàm C nhỏ:

~~~c
int ffm_add(int a, int b);
~~~

Nó nhận hai số nguyên C và trả tổng. Trên các nền tảng desktop phổ biến dùng cho ví dụ, C `int` tương ứng kiểu layout `ValueLayout.JAVA_INT`. Với một API native thực tế, **phải xác nhận C ABI**, vì một số kiểu C như `long` hoặc `size_t` có độ rộng thay đổi theo OS/kiến trúc.

### 7.1. Tệp native: `ffm_math.c`

~~~c
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

FFM_EXPORT int ffm_add(int a, int b) {
    return a + b;
}
~~~

Đây là **tệp C hoàn chỉnh**. Khác JNI, nó không cần `jni.h`, `JNIEnv *` hoặc một export tên `Java_...`. Symbol C `ffm_add` được export để FFM lấy địa chỉ bằng `SymbolLookup`.

Biên dịch bằng một trong các lệnh sau, tại thư mục chứa tệp C:

**Linux (GCC hoặc Clang):**

~~~bash
cc -fPIC -shared ffm_math.c -o libffm_math.so
~~~

**macOS (Clang):**

~~~bash
cc -fPIC -dynamiclib ffm_math.c -o libffm_math.dylib
~~~

**Windows (MSVC Developer Command Prompt, `cmd.exe`):**

~~~bat
cl /LD ffm_math.c /Fe:ffm_math.dll
~~~

Chọn compiler và binary cùng kiến trúc với JVM. Không thể load file `.dll` của Windows trong Linux hoặc một thư viện 32-bit vào tiến trình JVM 64-bit. Tên tệp native khác nhau, nhưng tên function C `ffm_add` là như nhau.

### 7.2. JDK 21 preview: `Ffm21Call.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class Ffm21Call {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                System.mapLibraryName("ffm_math")
        ).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    library, arena
            );
            MemorySegment symbol = lookup.find("ffm_add")
                    .orElseThrow();

            MethodHandle add = Linker.nativeLinker()
                    .downcallHandle(
                        symbol,
                        FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT
                        )
                    );

            int value = (int) add.invokeExact(7, 5);
            System.out.println("native = " + value);
        }
    }
}
~~~

Đây là chương trình **đầy đủ cho JDK 21 preview**. `System.mapLibraryName("ffm_math")` sinh tên thư viện theo OS, còn `toAbsolutePath()` trỏ đến binary vừa build trong thư mục hiện hành. Cần chạy terminal tại đúng thư mục có file library.

Biên dịch và chạy với JDK 21:

~~~bash
javac --enable-preview --release 21 Ffm21Call.java
java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call
~~~

**Stdout ứng dụng:**

~~~text
native = 12
~~~

Giải thích từng khâu: `SymbolLookup.libraryLookup(path, arena)` nạp/tham chiếu native library; `find("ffm_add")` tìm địa chỉ function; `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` mô tả **C function trả int, nhận hai int**; `Linker.nativeLinker().downcallHandle` tạo Java method handle; `invokeExact(7, 5)` gọi native code và nhận `12`.

Trong ví dụ này có hai cơ chế khác nhau:

- `--enable-preview`: bắt buộc vì đang dùng FFM preview trong **JDK 21**.
- `--enable-native-access=ALL-UNNAMED`: cấp quyền cho code trong **classpath** dùng restricted FFM operations, chẳng hạn `libraryLookup` và tạo downcall handle.

`ALL-UNNAMED` là tên đặc biệt chỉ code trong unnamed modules, không phải một tên module tự phát minh. Cần cấp quyền theo tên module thật nếu ứng dụng dùng named modules.

### 7.3. JDK 22 final: `Ffm22Call.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class Ffm22Call {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                System.mapLibraryName("ffm_math")
        ).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    library, arena
            );
            MemorySegment symbol = lookup.find("ffm_add")
                    .orElseThrow();

            MethodHandle add = Linker.nativeLinker()
                    .downcallHandle(
                        symbol,
                        FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT
                        )
                    );

            int value = (int) add.invokeExact(7, 5);
            System.out.println("native = " + value);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 22**:

~~~bash
javac --release 22 Ffm22Call.java
java --enable-native-access=ALL-UNNAMED Ffm22Call
~~~

**Stdout:**

~~~text
native = 12
~~~

Cần chú ý:

- Mã downcall **rất giống JDK 21** vì `Linker`, `SymbolLookup` và `FunctionDescriptor` cơ bản vẫn có hình dạng tương tự. Đừng cố tưởng tượng tất cả API FFM đều đổi khi finalized.
- Lệnh chạy **không cần `--enable-preview`**, vì FFM đã chính thức trong JDK 22.
- Lệnh vẫn chỉ định **`--enable-native-access=ALL-UNNAMED`** vì thư viện và downcall là thao tác restricted. Chính sách native access và trạng thái final là **hai khái niệm độc lập**.
- Vòng đời của symbol lookup phụ thuộc arena. Không lưu method handle để dùng sau khi arena đóng và thư viện có thể bị unload.
- `invokeExact` đòi hỏi Java carrier type chính xác. Với descriptor `(int,int) -> int`, lời gọi truyền hai `int` và cast kết quả sang `int`. Nếu dùng sai Java carrier, có thể gặp `WrongMethodTypeException`; còn nếu khai báo sai **native C ABI**, hậu quả có thể nặng hơn.

**So với JNI:** đây là call đến symbol C `ffm_add`, không phải một Java method được khai báo `native` và không có phần triển khai JNI C dạng `Java_package_Class_method`.

### 7.4. FFM FunctionDescriptor không phải JNI method descriptor

FFM khai báo hàm C trả `int` và nhận hai `int`:

~~~java
FunctionDescriptor.of(
    ValueLayout.JAVA_INT, // kiểu trả về
    ValueLayout.JAVA_INT, // tham số a
    ValueLayout.JAVA_INT  // tham số b
);
~~~

Đây là trích đoạn FFM; trong JNI, một Java method nhận hai int trả int có descriptor chuỗi `(II)I`. Hai cơ chế không hoán đổi: FFM `FunctionDescriptor` là **tập MemoryLayout/ValueLayout cho C ABI**, không nhận trực tiếp chuỗi `"(II)I"` của JVM.

## 8. Điểm mới hữu ích của JDK 22: Linker.canonicalLayouts()

Khi viết FFM native functions, xác định **chính xác C type layout** là trách nhiệm của người gọi. Không phải mọi tên kiểu C có cùng độ rộng trên các nền tảng:

- C `int` thông thường tương ứng 32-bit trên các platform mẫu.
- C `long` thường là 64-bit trên Linux x64 nhưng 32-bit trên Windows x64.
- C `size_t` thường theo độ rộng pointer: 32-bit hoặc 64-bit tùy ABI.

Trong JDK 21, thư viện FFM không có method `Linker.canonicalLayouts()`. **JDK 22 bổ sung method này** để tra một bản đồ các canonical C type layouts của ABI native hiện hành.

Ví dụ **trích đoạn chỉ có trên JDK 22**:

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
System.out.println(sizeT);
~~~

Không gán stdout cố định cho đoạn này: giá trị string của layout phụ thuộc native linker/JVM/ABI; map có những key được nền tảng cung cấp. Phải kiểm tra `sizeT` khác `null` và kiểm tra kiểu layout trước khi dùng.

`canonicalLayouts()` giúp giảm việc tự đoán kích thước C type, **nhưng không tự động suy ra prototype của native function**. Với `struct`, `union`, callback hay C pointer trỏ vùng không rõ kích thước, vẫn phải xem header và C ABI thật, quản lý alignment và lifetime.

## 9. Hai loại cờ độc lập: preview và native access

### 9.1. Bật preview ở JDK 21

~~~bash
javac --enable-preview --release 21 Ffm21Memory.java
java --enable-preview Ffm21Memory
~~~

JDK 21 cần preview flags cho FFM. Bỏ cờ compile/run có thể gây lỗi liên quan preview API hoặc class file preview. Để build **FFM JDK 21**, hãy sử dụng **javac của JDK 21**; đừng lấy `javac` của JDK 22 rồi yêu cầu `--enable-preview --release 21` như một cách “biên dịch ngược” preview. Preview features được chọn theo phiên bản compiler thực tế.

### 9.2. Không bật preview chỉ vì FFM ở JDK 22

~~~bash
javac --release 22 Ffm22Memory.java
java Ffm22Memory
~~~

Các lệnh trên chỉ cần JDK 22 và không có native downcall. Nếu ứng dụng **đồng thời dùng tính năng preview khác** của JDK 22, dự án đó vẫn có thể cần preview flags **cho tính năng khác**, không phải FFM.

### 9.3. Native access vẫn phải được xét ở cả hai bản

Những FFM methods như `SymbolLookup.libraryLookup` hoặc `Linker.downcallHandle` liên quan tới mã native không an toàn về mặt ABI và được hạn chế bởi chính sách **restricted methods**. Với chương trình chạy trên classpath:

~~~bash
java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call
java --enable-native-access=ALL-UNNAMED Ffm22Call
~~~

Đây là **hai lệnh cho hai phiên bản khác nhau**, không chạy cùng một binary/class trên một JVM. Cờ `--enable-native-access` cấp quyền để sử dụng restricted methods không bị cảnh báo hoặc chặn theo chính sách tương ứng.

Ở **JDK 21/22**, nếu không chỉ định cờ native access, một số restricted methods có thể vẫn chạy nhưng phát warning. Ngược lại, nếu đã cấp quyền **chỉ cho một số modules** mà module gọi API không thuộc danh sách, có thể gặp `IllegalCallerException`. Để triển khai có trách nhiệm, hãy cấp quyền rõ cho đúng module; không dựa vào cấu hình mặc định cảnh báo để làm chính sách production.

Các bản JDK mới hơn có thể thay đổi chế độ cảnh báo/chặn native access. **Không áp quy tắc của bản mới hơn về ngược JDK 21/22**; luôn đọc JDK documentation theo phiên bản thực thi.

### 9.4. Ma trận lệnh chạy nhanh

| Nhiệm vụ | JDK 21 preview | JDK 22 final |
|---|---|---|
| Compile memory sample | `javac --enable-preview --release 21 Ffm21Memory.java` | `javac --release 22 Ffm22Memory.java` |
| Run memory sample | `java --enable-preview Ffm21Memory` | `java Ffm22Memory` |
| Compile native-call sample | `javac --enable-preview --release 21 Ffm21Call.java` | `javac --release 22 Ffm22Call.java` |
| Run native-call sample | `java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call` | `java --enable-native-access=ALL-UNNAMED Ffm22Call` |

**Nhớ:** mọi lệnh ở cột 21 phải dùng JDK 21, mọi lệnh ở cột 22 phải dùng JDK 22. Các lệnh dành cho native-call sample cũng đòi hỏi tệp thư viện C đã được build cho OS/CPU phù hợp.

## 10. Vòng đời Arena: final API không xóa các quy tắc an toàn

Cả JDK 21 và 22 đều có những loại arena chính:

| Arena | Vòng đời | Quyền truy cập theo thread | Có thể close chủ động? |
|---|---|---|---|
| `Arena.ofConfined()` | Hữu hạn, do lập trình viên đóng | Thread tạo arena | Có |
| `Arena.ofShared()` | Hữu hạn, do lập trình viên đóng | Có thể nhiều thread | Có |
| `Arena.ofAuto()` | Do JVM/GC quản lý | Có thể nhiều thread | Không |
| `Arena.global()` | Vòng đời không giới hạn | Có thể nhiều thread | Không |

Ví dụ với `ofConfined`:

~~~text
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);
    ... truy cập hợp lệ khi arena còn sống ...
}
   |
   v
arena.close() làm scope không còn alive
   |
   v
Truy cập lại segment -> lỗi vòng đời, không được dùng
~~~

Đoạn trên là **sơ đồ**, không phải chương trình Java hợp lệ để copy nguyên văn.

FFM có kiểm tra ranh giới spatial/temporal/thread ở cấp `MemorySegment`, nhưng **không biến mọi địa chỉ native thành an toàn**. Khi native function trả con trỏ với kích thước không được biết, việc tự mở rộng phạm vi bằng API restricted (ví dụ `reinterpret`) có thể dẫn đến đọc/ghi sai bộ nhớ hoặc JVM crash. Nếu callback bất đồng bộ giữ một địa chỉ nằm trong arena đã đóng, đó cũng là lỗi lifetime.

Đặc biệt không đồng nhất **GC của Java** với giải phóng native memory: `Arena.ofConfined()` đóng tường minh đúng thời điểm; `Arena.ofAuto()` để JVM quyết định thời điểm dọn. Một C library tự cấp phát bằng `malloc` có thể yêu cầu gọi `free` hoặc hàm giải phóng riêng; đóng một arena không có nghĩa toàn bộ tài nguyên ngoại lai mà library từng tạo đều được thu hồi.

## 11. Checklist di trú source FFM 21 → 22

Khi nâng một codebase dùng FFM preview, thực hiện theo thứ tự:

1. **Xác định toolchain**: chọn JDK 22 và xác minh `java -version`/`javac -version` trong local, IDE, CI. Không dựa vào `JAVA_HOME` nếu `PATH` lại trỏ JDK khác.
2. **Tìm các API preview**: tìm `allocateUtf8String`, `allocateArray`, `getUtf8String`, `setUtf8String`, overload `allocate(layout, value)`.
3. **Đổi theo ngữ nghĩa**: cấp phát khởi tạo dữ liệu → `allocateFrom`; đọc/ghi C string → `getString`/`setString`. Không thay nhầm `allocate(byteSize)` hoặc `allocate(layout)`.
4. **Kiểm tra charset**: C strings là bytes với terminator, không phải Java UTF-16 String; dùng `Charset` rõ ràng nếu C API không chấp nhận UTF-8.
5. **Kiểm tra C ABI**: `FunctionDescriptor`, kiểu trả về, tham số, pointer/struct, alignment, `size_t`, signedness và kiến trúc.
6. **Sửa compile/run flags**: bỏ `--enable-preview` **nếu chỉ cần FFM final**; dùng `javac --release 22` với compiler 22.
7. **Giữ native access đúng nơi**: các restricted calls vẫn cần grant thích hợp, đặc biệt `libraryLookup`, linking và một số thao tác unsafe.
8. **Kiểm tra native library**: build đúng OS, bitness và export symbol; không giả định library được nạp qua `System.loadLibrary` nếu mã sử dụng `SymbolLookup.libraryLookup`.
9. **Kiểm tra resource lifecycle**: Arena close, segment lifetime, callbacks, threading, native library unloading, native memory do C tự cấp phát.
10. **Chạy test thực tế trên JDK 22**: test happy path, input bất thường, null pointer, boundary, encoding, errors, callback, concurrent access; không chỉ dựa vào việc javac thành công.
11. **Quy hoạch binary compatibility**: class file preview JDK 21 không phải artifact nên đem chạy tùy ý trên JDK 22. Biên dịch lại và test bằng runtime đích; một module cần hỗ trợ cả 21 và 22 có thể phải dùng source sets/toolchains tách biệt.
12. **Ghi rõ minimum supported Java version** trong tài liệu, build system và artifact metadata. Code `java.lang.foreign` final yêu cầu JDK 22 trở lên, không thể triển khai trực tiếp vào Java 17 chỉ vì package có tên `java.lang`.

Một dự án chỉ đọc/ghi native segment đơn giản có thể đổi ít dòng. Nhưng dự án dùng ABI cụ thể, struct phức tạp, C++ interop hay callback phải test sâu hơn. **Finalized là ổn định API**, không phải đảm bảo hành vi mọi thư viện native đều portable.

## 12. Lỗi phổ biến, nguyên nhân và cách khắc phục

| Lỗi hoặc hiểu lầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `jdk.incubator.foreign` trên JDK 21 | Đọc nhầm tutorial JDK 17/18 | Dùng `java.lang.foreign` và docs bản 21 |
| `javac` báo FFM là preview | Quên `--enable-preview` với JDK 21 | Bật preview trong lệnh compile |
| Runtime từ chối class preview | Quên cờ runtime hoặc dùng JVM không đúng version | Chạy bằng JDK 21 và `--enable-preview` |
| `allocateUtf8String` không tìm thấy ở JDK 22 | API đã đổi tên | `arena.allocateFrom(String)` |
| `allocateArray` không tìm thấy ở JDK 22 | API cấp phát từ các phần tử đã đổi | `arena.allocateFrom(layout, values...)` |
| `getUtf8String` không tìm thấy ở JDK 22 | Method đọc string đã đổi | `segment.getString(offset)` |
| `allocateFrom` không có ở JDK 21 | Copy code JDK 22 về 21 | Dùng API preview JDK 21 tương đương |
| Lỗi preview khi `--release 21` với compiler 22 | Compiler không biên dịch preview của bản cũ theo cách đó | Dùng đúng `javac` JDK 21 |
| Warning restricted native method | `--enable-preview` không cấp native access | Cấp `--enable-native-access=...` |
| `IllegalCallerException` | Module caller chưa được cấp native access | Chỉ định đúng module hoặc `ALL-UNNAMED` |
| Không tìm thấy native library | File DLL/.so/.dylib sai path/OS/bitness | Build đúng thư viện, chạy đúng thư mục |
| `NoSuchElementException` từ `find(...).orElseThrow()` | Không export đúng tên symbol | Kiểm tra `ffm_add` trong bảng export |
| `WrongMethodTypeException` | `invokeExact` không khớp Java carrier | So sánh `FunctionDescriptor`/kiểu đối số |
| JVM crash sau downcall | Signature C ABI sai hoặc pointer hết hạn | So C header thật, kiểm tra lifetime và architecture |
| `WrongThreadException` | Segment confined truy cập từ thread khác | Dùng đúng owner thread hoặc thiết kế shared arena |
| `IllegalStateException` khi truy cập segment | Arena đã bị đóng | Không dùng segment sau close |
| `size_t`/`long` sai trên Windows | Giả định C type rộng như trên Linux | Dùng ABI thực tế, xem `canonicalLayouts()` của 22 |

### 12.1. Công cụ kiểm tra

~~~bash
java -version
javac -version
~~~

Bước này xác minh compiler/runtime thực tế, nhất là khi máy cài nhiều JDK. Trên Linux/macOS/Windows, việc kiểm tra exported native symbols có thể dùng:

~~~text
Linux:   nm -D libffm_math.so
macOS:   nm -g libffm_math.dylib
Windows: dumpbin /EXPORTS ffm_math.dll
~~~

Đây là **các lệnh gợi ý theo hệ điều hành**, không phải script dùng chung. Công cụ `nm` trên macOS có thể hiển thị dấu underscore ở tên symbol dạng Mach-O; `SymbolLookup` xử lý tên theo quy tắc của hệ điều hành và loader.

## 13. Chọn phiên bản nào trong dự án thực tế?

Nếu phải hỗ trợ **JDK 21 LTS**, cần biết FFM trên đó **vẫn là preview**, nên phải chấp nhận preview flags, khóa version/toolchain và kiểm tra cả các lần cập nhật compiler/runtime.

Nếu dự án có thể yêu cầu **JDK 22+**, hãy ưu tiên viết mới theo **FFM final (JEP 454)**: API `allocateFrom`/`getString` chính thức, không cần preview cho riêng FFM và phù hợp làm baseline rõ ràng. Nhưng việc này **không bỏ trách nhiệm** cấp native access, thiết kế ABI, đóng Arena và bảo mật thư viện native.

Nếu ứng dụng phải chạy trên nhiều major JDK, đừng chỉ copy một tệp `.class` compile preview JDK 21 rồi xem nó là binary portable cho JDK 22. Nên tách build/test phù hợp với từng release, hoặc cân nhắc JNI cho runtime cũ nếu yêu cầu sản phẩm khiến FFM final chưa có sẵn.

FFM là công cụ mạnh để liên kết C ABI mà không viết JNI glue cho từng hàm, nhưng **không là giải pháp thay thế hoàn toàn JNI**. JNI vẫn quan trọng khi C/C++ code cần thao tác trực tiếp với Java objects, callbacks ở mức JNI hoặc hệ thống đã có native bindings lâu năm.

## 14. Câu hỏi ôn tập

1. JDK 21 thuộc JEP nào và là preview thứ mấy? JDK 22 thuộc JEP nào?
2. FFM JDK 21 nằm trong `jdk.incubator.foreign` hay `java.lang.foreign`? Vì sao nhầm điều này thường gây lỗi import?
3. Vì sao từ JDK 22 không cần `--enable-preview` cho riêng FFM, nhưng vẫn có thể cần `--enable-native-access`?
4. Hãy chuyển ba lời gọi `allocateUtf8String`, `allocateArray`, `getUtf8String` sang JDK 22.
5. Khi nào nên giữ `arena.allocate(layout)` mà không đổi thành `allocateFrom`?
6. Tại sao hai ví dụ memory dùng JDK 21 và 22 có cùng stdout `sum = 12` và `text = FFM`?
7. Hãy viết lệnh `javac` và `java` đúng cho `Ffm21Call.java` và `Ffm22Call.java`.
8. Cờ `ALL-UNNAMED` áp dụng cho code nào? Nếu dùng named module phải làm gì?
9. `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` mô tả điều gì? Có tương đương truyền chuỗi JNI `(II)I` vào API không?
10. Tại sao việc khai báo `size_t` bằng `JAVA_LONG` cho mọi OS không an toàn?
11. `Linker.canonicalLayouts()` bắt đầu có ở JDK nào, giải quyết loại vấn đề gì?
12. Điều gì xảy ra khi code cố truy cập `MemorySegment` từ confined Arena đã đóng?
13. Vì sao không nên giữ native function pointer hoặc method handle lâu hơn thời gian thư viện được load?
14. Nếu toàn bộ mã FFM 21 build thành công nhưng fail khi chạy trên JDK 22, bạn sẽ kiểm tra **API đổi tên, preview class file, toolchain, native access, ABI** theo thứ tự nào?

**Kết luận:** **JDK 21 = FFM third preview (JEP 442)**, cần preview flags; **JDK 22 = FFM final (JEP 454)**, không cần preview cho FFM. Nâng cấp không chỉ bỏ cờ: phải chuyển API tạo dữ liệu native từ `allocateUtf8String`/`allocateArray`/`allocate(layout,value)` sang `allocateFrom` và từ `getUtf8String`/`setUtf8String` sang `getString`/`setString`. Mặt khác, `Arena`, `Linker`, `SymbolLookup` và `FunctionDescriptor` vẫn giữ mô hình lõi; **native access, C ABI, memory lifetime và thread safety** vẫn cần được quản lý tường minh.

### Tài liệu chuẩn theo phiên bản

- [JEP 442 — Foreign Function & Memory API (Third Preview), JDK 21](https://openjdk.org/jeps/442)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [Java 21 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 21 — SegmentAllocator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) và [MemorySegment](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/MemorySegment.html): `allocateUtf8String`, `allocateArray`, `getUtf8String`.
- [Java 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) và [MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `allocateFrom`, `getString`/`setString`.
- [Java 22 — Linker API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): canonical C layouts, downcall và restricted methods.
- [Oracle JDK 21 — FFM overview](https://docs.oracle.com/en/java/javase/21/core/foreign-function-and-memory-api.html) và [Oracle Java 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html).
