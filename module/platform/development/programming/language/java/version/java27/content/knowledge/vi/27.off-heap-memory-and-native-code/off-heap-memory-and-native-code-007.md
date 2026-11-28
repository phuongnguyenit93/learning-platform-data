# Quyền native access, khả năng di chuyển và đóng gói thư viện native

Java có khả năng gọi mã C/C++ và thao tác với bộ nhớ ngoài Java heap để tích hợp thiết bị, codec, thư viện tính toán, hệ điều hành hoặc SDK của bên thứ ba. Trong Java 27, **Foreign Function and Memory API (FFM)** ở `java.lang.foreign` là API chính thức để làm việc với bộ nhớ và hàm native; **Java Native Interface (JNI)** vẫn là API được hỗ trợ cho các tình huống tương thích và tích hợp sâu với JVM.

Tuy nhiên, native code không được JVM bảo vệ hoàn toàn như Java bytecode. Một sai lệch trong ABI, con trỏ, vòng đời bộ nhớ hoặc thư viện được tải có thể làm tiến trình JVM crash hay gây hỏng dữ liệu. Vì vậy, việc tích hợp native trong Java 27 cần thiết kế đồng thời ba khía cạnh:

1. **Quyền native access:** module nào được phép gọi những thao tác native bị hạn chế (*restricted operations*) và cấu hình launcher ra sao.
2. **Khả năng di chuyển (portability):** phân biệt Java bytecode chạy đa nền tảng với binary native phụ thuộc OS, CPU architecture, ABI, toolchain và các thư viện đi kèm.
3. **Đóng gói/phân phối:** phân phối đúng native artifact, cấu hình đường dẫn tải an toàn, khai báo quyền tối thiểu, tạo launcher/runtime phù hợp và kiểm thử đúng nền tảng đích.

Bài thuộc chương **Bộ nhớ ngoài heap và mã native**, module **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào API và công cụ **đang được Java SE 27 hỗ trợ**, không hướng dẫn dựa trên các phiên bản preview cũ của FFM hay API nội bộ không được bảo đảm tương thích. Các ví dụ C/FFM cần native toolchain và thư viện phù hợp khi chạy thực sự; ví dụ chỉ dùng `Arena` có thể chạy mà không cần thư viện ngoài.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Phân biệt JNI, FFM, bộ nhớ ngoài heap và việc gọi hàm của thư viện hệ điều hành.
- Giải thích vì sao một số phương thức FFM và phương thức tải thư viện native là **restricted**.
- Dùng `--enable-native-access=M1,M2` cho **named modules**, hoặc `--enable-native-access=ALL-UNNAMED` cho mã trên classpath.
- Hiểu `--illegal-native-access=allow|warn|deny` và vì sao nên kiểm thử bằng `deny`.
- Nhận diện **module thực hiện thao tác native**, không nhầm nó với module `java.base` chứa API.
- Phân biệt tải thư viện bằng `System.load`, `System.loadLibrary` và `SymbolLookup.libraryLookup`.
- Quản lý scope của `Arena`, `MemorySegment` và địa chỉ symbol trong lời gọi native.
- Biết những ràng buộc về OS, kiến trúc 32/64 bit, ABI, layout, encoding, ownership và dependency của shared library.
- Lập kế hoạch phân phối artifact native cho Linux, Windows và macOS bằng launcher, `jlink`/`jpackage` khi phù hợp.
- Dùng `jnativescan`, smoke test thực tế và checklist phát hành để giảm lỗi runtime và nguy cơ bảo mật.

## 2. Native code và off-heap khác nhau thế nào?

### 2.1. Off-heap không nhất thiết có lời gọi native

**Off-heap memory** là vùng nhớ nằm ngoài Java heap. Một chương trình có thể cấp phát native memory qua FFM, thao tác số nguyên và đóng vùng nhớ mà **không tải một thư viện C/C++ tùy biến**.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class OffHeapOnlyDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment value = arena.allocate(ValueLayout.JAVA_INT);

            value.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println(value.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Đây là ví dụ FFM sử dụng **allocation và truy cập có kiểm tra bounds/lifetime**. Trong Java SE 27, `Arena.ofConfined()`, `allocate` và `MemorySegment.get/set` theo mẫu trên **không phải** các restricted methods yêu cầu bật native access. Tuy nhiên, việc cấp phát off-heap vẫn tiêu thụ tài nguyên hệ điều hành; không nên hiểu “không cần cấp quyền” là “không có giới hạn tài nguyên”.

### 2.2. Gọi hàm native là ranh giới nguy hiểm hơn

Khi chương trình Java tải một shared library rồi liên kết tới một hàm C, JVM thường **không thể chứng minh** chữ ký hàm thực có khớp với `FunctionDescriptor` Java khai báo hay không. Sai kiểu đối số, calling convention, kích thước struct, con trỏ hoặc vòng đời bộ nhớ có thể dẫn tới hành vi không xác định và crash.

~~~text
Java code
  |
  | FFM (downcall) hoặc JNI (native method)
  v
Thư viện native .so / .dylib / .dll
  |
  | ABI, system libraries, kernel, CPU
  v
Bộ nhớ và tài nguyên ngoài phạm vi kiểm soát đầy đủ của JVM
~~~

Quyền native access là một phần của mục tiêu **integrity by default**: người vận hành nhận biết những module có thể vượt qua ranh giới an toàn của JVM và chủ động cấp quyền cho chúng.

### 2.3. JNI không tự động là “API đã bị loại bỏ”

JNI là giao diện hiện hành dành cho mã native cần tương tác với JVM, đối tượng Java, callbacks, hoặc những binding có sẵn từ lâu. FFM giảm việc phải viết lớp JNI thủ công trong nhiều trường hợp gọi thư viện C và quản lý off-heap.

Không nên kết luận rằng JNI đã bị xóa khỏi Java 27 hoặc mọi ứng dụng JNI buộc phải chuyển sang FFM ngay. Cần đánh giá **chi phí migration, tính tương thích API, mức độ dùng JNI Env, cấu trúc callbacks và ràng buộc library**. Những điểm không còn phù hợp là cách dùng API preview FFM cũ, giả định native load luôn được phép ngầm định, hoặc phụ thuộc vào JDK-internal APIs không có hợp đồng hỗ trợ.

## 3. Native access bị hạn chế vì sao?

### 3.1. Restricted methods là gì?

Một số thao tác của Java platform được phân loại là **restricted** vì nếu sử dụng sai, chúng có thể phá tính toàn vẹn của tiến trình Java. Ví dụ:

| Nhóm | Ví dụ trong Java 27 | Rủi ro chính |
|---|---|---|
| Tải thư viện JNI | `System.load`, `System.loadLibrary`, các phiên bản `Runtime.load*` | Chạy mã native ngay khi loader khởi tạo thư viện |
| Tải thư viện qua FFM | `SymbolLookup.libraryLookup(String, Arena)`, overload nhận `Path` | Tải mã native; symbol/address có lifetime riêng |
| Liên kết downcall | `Linker.downcallHandle(...)` | Java không tự xác minh ABI và chữ ký C thực |
| Tạo upcall stub | `Linker.upcallStub(...)` | C code có thể gọi Java callback thông qua con trỏ |
| Thay đổi phạm vi segment | `MemorySegment.reinterpret(...)` | Có thể gán size/lifetime không tương ứng bộ nhớ thật |
| Layout liên quan dereference pointer | `AddressLayout.withTargetLayout(...)` | Truy cập vùng nhớ qua địa chỉ không thể kiểm chứng |
| Cấp quyền module động | `ModuleLayer.Controller.enableNativeAccess(Module)` | Truyền tiếp quyền thao tác restricted |

Danh sách chi tiết có thể thay đổi giữa các bản JDK; kiểm tra **API documentation của đúng phiên bản runtime** khi viết công cụ hoặc cấu hình phát hành.

### 3.2. Không phải mọi phương thức trong java.lang.foreign đều restricted

`Arena.ofConfined()`, `MemorySegment.get/set` vào vùng nhớ hợp lệ, layout cơ bản và `MemorySegment.ofArray` thuộc các phép thao tác FFM thông thường. Việc gọi **một restricted method cụ thể** mới kích hoạt chính sách native access.

Ví dụ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment memory = arena.allocate(32);
    memory.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
}
~~~

Không cần bật `--enable-native-access` chỉ vì có import `java.lang.foreign`. Ngược lại, tạo downcall handle hay tải một thư viện bằng restricted API cần chính sách cấp quyền phù hợp.

### 3.3. Cấp quyền không làm native code trở nên an toàn

`--enable-native-access` chỉ cho phép module sử dụng những thao tác có thể vượt qua ranh giới an toàn. Nó **không**:

- Kiểm tra thư viện có đáng tin hay không.
- Xác minh chữ ký ABI, struct padding hoặc ownership pointer.
- Bảo đảm native code không thể crash JVM.
- Bỏ qua quyền truy cập tệp của hệ điều hành.
- Cấp quyền `root`/Administrator.
- Giải quyết DLL dependency, linker loader path hoặc sai kiến trúc CPU.

Vì vậy, native access phải được coi là **quyền nhạy cảm của ứng dụng**, dù nó không phải quyền quản trị hệ điều hành.

## 4. Cấp native access bằng java launcher

### 4.1. Named modules: cấp quyền theo tên module

Giả sử có module `com.example.bridge` chứa lớp thực hiện `SymbolLookup.libraryLookup` hoặc `System.loadLibrary`, còn module `com.example.app` sử dụng API của bridge.

~~~text
com.example.app
      |
      | requires
      v
com.example.bridge
      |
      | restricted FFM/JNI operation
      v
Native library
~~~

Lệnh chạy:

~~~bash
java --enable-native-access=com.example.bridge \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Option là một phần của **JVM startup**, không phải câu Java trong mã nguồn. Nếu cả hai module thực sự gọi restricted APIs thì danh sách có thể gồm cả hai tên:

~~~bash
java --enable-native-access=com.example.bridge,com.example.app \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Không nên cấp thêm `com.example.app` nếu chỉ `com.example.bridge` thực hiện native access. Module cần quyền là **module chứa mã gọi restricted operation / native method**, chứ không phải `java.base` chỉ vì các lớp FFM nằm trong đó.

### 4.2. Classpath: ALL-UNNAMED

Ứng dụng classpath truyền thống không có named module của riêng nó. Cấp quyền cho mã trong các unnamed modules bằng:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     -cp app.jar com.example.Main
~~~

`ALL-UNNAMED` bao phủ mọi unnamed module, nên **rộng hơn** cấp cho một named module duy nhất. Nó có thể cần thiết trong ứng dụng cũ hoặc công cụ nhỏ, nhưng với dịch vụ có nhiều thư viện bên thứ ba, nên xem xét module path và cấp quyền hẹp cho module được kiểm soát.

Không cần tự tạo `module-info.java` chỉ để thử mã FFM đọc/ghi bộ nhớ ở mục 2. Cấu hình trên cần khi **thực sự có thao tác restricted/native**.

### 4.3. Không có directive requires native access

Ví dụ descriptor:

~~~java
module com.example.bridge {
    exports com.example.bridge;
}
~~~

Không có cú pháp `requires native` hay `opens native` để tự động xin quyền native. `requires` điều khiển **readability của JPMS**; `exports` và `opens` điều khiển các hình thức truy cập package. Native access là **quyền runtime riêng** được cấp bởi launcher hoặc cơ chế runtime được thiết kế cho mục đích đó.

Sửa `module-info.java` để export package nội bộ không phải cách khắc phục thiếu native access. Ngược lại, cấp native access cũng không làm module đọc được một module khác vốn không có readability.

### 4.4. Kiểm tra quyền tại runtime

~~~java
public class NativeAccessCheck {
    public static void main(String[] args) {
        Module module = NativeAccessCheck.class.getModule();

        System.out.println("Module: " +
                (module.isNamed() ? module.getName() : "ALL-UNNAMED"));
        System.out.println("Native access enabled: " +
                module.isNativeAccessEnabled());
    }
}
~~~

`Module.isNativeAccessEnabled()` cho biết module có quyền gọi restricted methods hay không. Kết quả `false` không đồng nghĩa mọi API FFM đều không dùng được; các phép quản lý segment thông thường vẫn có thể dùng.

Đừng dùng `isNativeAccessEnabled()` như một cơ chế kiểm tra toàn diện cho native binary đã tải. Nó chỉ phản ánh **quyền module**, không kiểm chứng library ABI, checksum hoặc hành vi thực.

## 5. --illegal-native-access và chuyển đổi sang cấu hình chặt

### 5.1. Ba chế độ trong Java SE 27

Java 27 cho phép điều khiển phản ứng với **illegal native access** bằng:

| Option | Khi một module chưa được cấp quyền thực hiện restricted operation |
|---|---|
| `--illegal-native-access=allow` | Cho phép tiếp tục mà không báo warning từ cơ chế này |
| `--illegal-native-access=warn` | Cho phép tiếp tục, cảnh báo lần đầu với từng module vi phạm |
| `--illegal-native-access=deny` | Từ chối, ném `IllegalCallerException` đối với restricted operation |

Trong Java SE 27, **`warn` là chế độ mặc định** theo tài liệu launcher; tương lai có thể chuyển mặc định sang `deny`. `--illegal-native-access` được đánh dấu là tùy chọn chuyển tiếp và **dự kiến bị loại bỏ trong một bản tương lai**, vì vậy không xây dựng chiến lược vận hành dài hạn dựa vào `allow`.

### 5.2. Quy trình kiểm tra tương thích được khuyến nghị

Trong môi trường test/CI, chạy:

~~~bash
java --illegal-native-access=deny \
     --enable-native-access=com.example.bridge \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Mục đích:

1. Tất cả code restricted được dự kiến phải thuộc các module được cấp quyền.
2. Bất kỳ thư viện phụ thuộc nào thực hiện native operation mà chưa khai báo rõ có thể bộc lộ lỗi sớm.
3. Không cần đợi đến lúc JDK đổi mặc định mới phát hiện vấn đề.

Nếu thực tế có module khác hợp lệ cần quyền, bổ sung **chính xác module đó** sau khi xem xét rủi ro. Đừng chuyển sang `allow` để che cảnh báo trong ứng dụng production mà không phân tích nguồn gốc native access.

### 5.3. Cảnh báo không đồng nghĩa mã đang an toàn

Ở chế độ mặc định `warn`, restricted operation không được cấp quyền **vẫn có thể chạy**. Việc chương trình hiện chạy được không chứng minh cấu hình đã sẵn sàng cho một Java runtime tương lai có chính sách chặt hơn.

Với JNI, các thao tác tải thư viện và native method binding có thể tạo warning/exception tương ứng; với FFM, các restricted methods như `libraryLookup` và `downcallHandle` nằm trong phạm vi chính sách.

### 5.4. Khởi động bằng manifest, options file hoặc môi trường

Ngoài command line, Java launcher hỗ trợ:

- `JDK_JAVA_OPTIONS`: cung cấp launcher options qua environment; cần quản lý minh bạch vì ảnh hưởng mọi lệnh `java` trong môi trường đó.
- Argument file như `@runtime-options.txt`: gom cấu hình launcher dưới quản lý triển khai.
- Executable JAR manifest với thuộc tính `Enable-Native-Access: ALL-UNNAMED` cho trường hợp được tài liệu hỗ trợ.
- Runtime image/launcher tùy biến phù hợp, với các option được nhúng khi tạo/đóng gói.

Ví dụ nội dung argument file:

~~~text
--enable-native-access=ALL-UNNAMED
--illegal-native-access=deny
~~~

Chạy:

~~~bash
java @runtime-options.txt -jar app.jar
~~~

Nếu dùng named module, ưu tiên option đích danh trên launcher thay vì thuộc tính manifest áp dụng rộng cho unnamed modules.

## 6. Phân biệt JNI, FFM và cơ chế tải thư viện

### 6.1. FFM: tải, tìm symbol, tạo downcall

Các thành phần hiện hành:

- `SymbolLookup.libraryLookup(...)`: nạp thư viện và tìm symbol, có overload theo tên hoặc `Path`.
- `Linker.nativeLinker()`: đại diện cho linker với ABI native của hệ thống.
- `FunctionDescriptor`: mô tả signature của hàm native tại biên FFM.
- `Linker.downcallHandle(...)`: tạo `MethodHandle` gọi hàm C qua địa chỉ symbol.
- `Arena` và `MemorySegment`: quản lý dữ liệu native và vòng đời của vùng nhớ.

Để dùng downcall **đúng**, phải khớp kiểu dữ liệu, calling convention, số lượng tham số, cách trả struct, pointer lifetime và ABI của binary thực. Không được lấy một descriptor “có vẻ hợp lý” rồi gọi hàm tùy ý: nhiều sai lệch không trở thành Java exception mà có thể gây lỗi bộ nhớ.

### 6.2. JNI: khai báo native method và tải thư viện

Ví dụ cấu trúc Java:

~~~java
package com.example.bridge;

public final class NativeMath {
    static {
        System.loadLibrary("mathbridge");
    }

    public static native int add(int left, int right);
}
~~~

`System.loadLibrary("mathbridge")` nhận **tên thư viện logic** không chứa prefix `lib`, extension hay path. Runtime/OS thực hiện việc tìm và nạp thư viện theo cơ chế tương ứng; native binary phải cung cấp implementation JNI cho phương thức Java.

Một phiên bản triển khai JNI ở C thường có signature phụ thuộc class/package đã khai báo và dùng JNI header sinh bằng công cụ như `javac -h`. Đừng giả định một hàm C thông thường `int add(int, int)` sẽ tự thỏa mãn convention của JNI; đó là lý do FFM và JNI có **hai cách binding khác nhau**.

### 6.3. System.load, loadLibrary và FFM libraryLookup

| API | Đầu vào | Cơ chế chính |
|---|---|---|
| `System.load(String absoluteFilename)` | Đường dẫn tuyệt đối tới thư viện | Nạp thư viện qua cơ chế JNI/class loader |
| `System.loadLibrary(String libname)` | Tên logic, không đường dẫn/prefix/đuôi | Tìm theo cơ chế native library lookup của JVM/OS |
| `SymbolLookup.libraryLookup(String name, Arena)` | Tên thư viện theo quy tắc OS/provider | Nạp thư viện và tạo lookup theo lifetime arena |
| `SymbolLookup.libraryLookup(Path path, Arena)` | Đường dẫn `Path` tới binary | Tìm và nạp thư viện theo path, tạo lookup |
| `SymbolLookup.loaderLookup()` | Không có tham số library | Tìm symbols ở những thư viện đã tải theo JNI liên quan class loader |
| `Linker.defaultLookup()` | Không chỉ định thư viện riêng | Tìm những symbol phổ biến mà native linker cung cấp theo nền tảng |

`System.loadLibrary` và `SymbolLookup.libraryLookup` **không đồng nghĩa**; lifecycle, lookup visibility và class-loader association khác nhau. `loaderLookup()` hướng tới những thư viện được nạp qua JNI; theo API, nó không tự động thấy tất cả các thư viện chỉ được tải bằng `libraryLookup(...)`.

### 6.4. Lỗi thư viện thiếu và lỗi thiếu quyền khác nhau

Một số tình huống:

- **`IllegalCallerException`**: module không được cấp native access trong chế độ từ chối.
- **`UnsatisfiedLinkError`**: thư viện không tìm thấy/không thể load, thiếu dependency, sai kiến trúc hoặc symbol JNI cần thiết chưa có.
- **Lỗi tương thích ABI**: có thể dẫn tới crash hoặc corrupted memory thay vì exception Java rõ ràng.
- **`IllegalStateException`/`WrongThreadException`** trong FFM: thao tác với segment/arena đã đóng hoặc sai thread khi có phạm vi confined.
- **OS permission errors**: file tồn tại nhưng không có quyền đọc/execute/map, hoặc hệ thống chặn bởi policy/signing/quarantine.

Khi debug, phải phân biệt “chưa cấp quyền native cho module” với “đã cấp quyền nhưng không tìm được binary phù hợp”.

## 7. Ví dụ runnable: kiểm tra quyền và vòng đời bộ nhớ

Ví dụ dưới đây **không** tải thư viện native của bên thứ ba, giúp tách biệt hai khái niệm: quyền restricted operation và cấp phát native memory thông thường.

Lưu vào `NativeMemoryRightsDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class NativeMemoryRightsDemo {

    public static void main(String[] args) {
        Module self = NativeMemoryRightsDemo.class.getModule();

        System.out.println("Module = " +
                (self.isNamed() ? self.getName() : "ALL-UNNAMED"));
        System.out.println("Native access = " +
                self.isNativeAccessEnabled());

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);

            data.set(ValueLayout.JAVA_INT, 0, 2027);
            System.out.println("Off-heap value = " +
                    data.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 27:

~~~bash
javac NativeMemoryRightsDemo.java
java NativeMemoryRightsDemo
~~~

Không cần `--enable-native-access` để chạy phép `Arena.allocate` và `MemorySegment.get/set` minh họa. Chạy thêm:

~~~bash
java --illegal-native-access=deny NativeMemoryRightsDemo
~~~

Ví dụ vẫn có thể làm việc với vùng nhớ được cấp phát và quản lý an toàn, vì nó **không gọi restricted operation**.

Điều này không phủ nhận những nguy cơ off-heap: cấp phát quá lớn có thể hết native memory, và việc giữ arena sống quá lâu có thể giữ tài nguyên không cần thiết.

## 8. Ví dụ FFM với thư viện native thật

Ví dụ sau minh họa cách một binary C đơn giản trở thành thư viện callable từ Java bằng FFM. Nó **có phần phụ thuộc nền tảng**, vì vậy không mặc định chạy trên mọi máy chỉ với `javac`.

### 8.1. Native C library: định nghĩa một ABI nhỏ

Giả sử file C chứa:

~~~c
// mathbridge.c
#if defined(_WIN32)
#define BRIDGE_API __declspec(dllexport)
#else
#define BRIDGE_API __attribute__((visibility("default")))
#endif

BRIDGE_API int bridge_add(int a, int b) {
    return a + b;
}
~~~

Biên dịch thành shared library bằng toolchain **phù hợp OS/architecture**. Ví dụ minh họa:

~~~bash
# Linux, với toolchain C hỗ trợ shared library:
cc -shared -fPIC -o libmathbridge.so mathbridge.c

# macOS, với toolchain C thích hợp:
cc -dynamiclib -o libmathbridge.dylib mathbridge.c
~~~

Trên Windows, cần trình biên dịch và cờ xuất DLL phù hợp với toolchain, tạo `mathbridge.dll`. Không thể dùng một command C compiler duy nhất cho mọi nền tảng. Nếu build bằng C++, cần công bố symbol C ABI qua `extern "C"` và kiểm soát name mangling.

### 8.2. Java FFM: tải library, tìm symbol và downcall

Lưu vào `FfmNativeBridgeDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FfmNativeBridgeDemo {

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java FfmNativeBridgeDemo <absolute-library-path>");
            return;
        }

        Path library = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(library)) {
            throw new IllegalArgumentException(
                    "Native library is missing: " + library);
        }

        // Chỉ tải binary từ đường dẫn triển khai đáng tin cậy.
        try (Arena libraryArena = Arena.ofConfined()) {
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, libraryArena);

            Linker linker = Linker.nativeLinker();

            MethodHandle add = linker.downcallHandle(
                    symbols.findOrThrow("bridge_add"),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            int result = (int) add.invokeExact(20, 22);
            System.out.println("20 + 22 = " + result);
        }
    }
}
~~~

Hai điểm quan trọng:

- `SymbolLookup.libraryLookup` và `Linker.downcallHandle` là **restricted methods** nên module gọi chúng cần được cấp native access.
- `libraryArena` xác định lifetime của library lookup/symbol liên quan. Không nên giữ `MethodHandle` hoặc địa chỉ native đã lấy từ lookup rồi sử dụng sau khi arena đóng nếu việc đó làm symbol/library không còn hợp lệ.

Với native bridge minh họa, `int` trong C được giả định tương ứng đúng layout được cấu hình và calling convention của platform đích; khi tích hợp thư viện thực, phải kiểm chứng ABI trước, không suy ra từ tên C type.

### 8.3. Chạy trên classpath

Sau khi biên dịch `FfmNativeBridgeDemo.java` và có thư viện được build đúng nền tảng:

~~~bash
javac FfmNativeBridgeDemo.java

java --illegal-native-access=deny \
     --enable-native-access=ALL-UNNAMED \
     FfmNativeBridgeDemo /absolute/path/to/libmathbridge.so
~~~

Đường dẫn ở ví dụ là **placeholder cho Linux**. Trên Windows/macOS phải thay đúng tên file và đường dẫn của thư viện. Không chạy path placeholder rồi kết luận FFM không hỗ trợ nền tảng đó.

Thử bỏ `--enable-native-access=ALL-UNNAMED` trong chế độ `deny` sẽ giúp phát hiện việc gọi restricted method từ unnamed module chưa được cấp quyền. Không cần sửa mã Java chỉ để đổi quyền này.

### 8.4. Chọn named module cho native bridge

Nếu chuyển lớp gọi FFM sang named module `com.example.bridge`, command sẽ có dạng:

~~~bash
java --illegal-native-access=deny \
     --enable-native-access=com.example.bridge \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Đây là **mẫu cấu trúc** cho ứng dụng modular có `module-info.java` và module path được build đúng; nó không phải lệnh có thể chạy trực tiếp nếu chưa tạo các module đó.

Quan trọng: quyền cấp cho module chứa `libraryLookup`/`downcallHandle`. Nếu dependency bên ngoài cũng gọi restricted methods từ một module khác, cần đánh giá và cấp quyền riêng cho module đó.

## 9. Portability: Java bytecode và native binary có ranh giới khác nhau

### 9.1. Ba lớp tương thích

| Lớp | Điều kiện tương thích |
|---|---|
| **Java API/bytecode** | Phiên bản Java, class file version, module graph, JDK vendor/behavior được hỗ trợ |
| **Native binary** | OS, CPU architecture, ABI, bitness, calling convention, loader, dependency native |
| **Giao diện Java ↔ native** | Chữ ký C, layouts, alignment, pointer lifetime, encoding, thread ownership, error mapping |

Một JAR Java có thể chuyển từ Linux sang Windows nếu chỉ dùng API đa nền tảng. Nhưng một file `libmathbridge.so` **không tự trở thành DLL** khi copy JAR sang Windows. Cần build bản DLL và bảo đảm dependency hệ điều hành tương ứng.

### 9.2. Tên thư viện theo nền tảng

Ví dụ thông dụng:

| Nền tảng | Kiểu shared library | Ví dụ logic mathbridge |
|---|---|---|
| Linux | ELF shared object, thường `.so` | `libmathbridge.so` |
| macOS | Mach-O dynamic library, thường `.dylib` | `libmathbridge.dylib` |
| Windows | PE dynamic-link library, `.dll` | `mathbridge.dll` |

Đây là quy ước phổ biến, **không phải hợp đồng rằng mọi thư viện sẽ có chính xác cách đặt tên đó**. Versioned sonames, symlinks, static linking và cách linker diễn giải tên có thể khác.

Nếu dùng `System.loadLibrary("mathbridge")`, hãy để JVM/OS áp dụng quy tắc tìm tên thư viện của nền tảng. Nếu cần hiển thị tên mapped theo implementation hiện tại, `System.mapLibraryName("mathbridge")` là API tiện dụng, nhưng kết quả vẫn cần kiểm tra trên nền tảng và provider đang chạy.

### 9.3. Architecture và bitness

Các bản build thường được phân phối riêng:

~~~text
linux-x86_64/
linux-aarch64/
windows-x86_64/
windows-aarch64/
macos-x86_64/
macos-aarch64/
~~~

Đây là **mẫu phân loại release artifact**, không phải danh sách mọi CPU mà Java/driver nhất định hỗ trợ. Cần kiểm tra hệ điều hành và toolchain mục tiêu thật.

Một JVM 64-bit không thể nạp tùy ý thư viện chỉ build cho 32-bit. Ngay cả khi OS và kiến trúc giống nhau, native binary có thể yêu cầu libc, C++ runtime hoặc thư viện hệ thống phiên bản khác.

`System.getProperty("os.arch")` và `System.getProperty("os.name")` có thể giúp ghi log hoặc chọn artifact trong một ma trận **đã biết và kiểm thử**, nhưng không đủ để xác định toàn bộ ABI/c-runtime. Đừng tự suy đoán đầy đủ tên artifact từ hai property mà không thử tải thực tế.

### 9.4. ABI và sự khác biệt giữa C và Java

Những giả định nguy hiểm khi viết `FunctionDescriptor`:

- `long` trong Java là số nguyên 64-bit, nhưng `long` trong C không luôn có kích thước như thế trên mọi ABI.
- `size_t`, `wchar_t` và `bool` có thể có representation khác theo nền tảng.
- Struct có **padding, alignment** và quy tắc truyền by-value/by-reference.
- Calling convention và quy tắc trả struct có thể khác OS/architecture.
- `char *` có thể chứa UTF-8, ANSI code page hoặc dữ liệu nhị phân; không tự bảo đảm UTF-8.
- Endianness cần được thống nhất khi làm việc với binary protocol hoặc dữ liệu được serialize.
- Con trỏ có thể là borrowed pointer, owned pointer hoặc buffer do library quản lý.

`Linker.canonicalLayouts()` cung cấp những layout tương ứng các C types được native linker biết theo ABI đang chạy. Trong thư viện phức tạp, công cụ tạo binding như `jextract` hoặc code generator tương ứng có thể giảm lỗi thủ công; vẫn phải xác minh với header và phiên bản binary thực tế.

### 9.5. ABI ổn định tốt hơn phụ thuộc layout C++ trực tiếp

Khi có quyền thiết kế native library, nên xuất một **C ABI nhỏ, có version** làm boundary:

~~~c
// api.h - minh họa concept
#ifndef MATH_BRIDGE_API_H
#define MATH_BRIDGE_API_H

#ifdef __cplusplus
extern "C" {
#endif

int bridge_api_version(void);
int bridge_add(int a, int b);

#ifdef __cplusplus
}
#endif

#endif
~~~

Không nên expose trực tiếp class C++ STL, exception types hoặc allocator nội bộ qua binary boundary nếu mục tiêu là portability lâu dài. C++ ABI/name mangling có thể khác compiler, standard library và version.

Trong sản phẩm, tách header công khai, implementation, symbol visibility và semantic versioning phù hợp. Một API trả buffer phải chỉ rõ **bên nào cấp phát và bên nào giải phóng**; không dùng một allocator để free memory cấp bởi allocator khác nếu hợp đồng không cho phép.

## 10. Native memory lifetime, thread ownership và an toàn API

### 10.1. Arena quyết định vòng đời của segment

Các loại arena phổ biến:

| Arena | Cách quản lý lifetime | Thread access |
|---|---|---|
| `Arena.ofConfined()` | Có thể đóng chủ động | Chỉ owner thread |
| `Arena.ofShared()` | Có thể đóng chủ động | Có thể truy cập từ nhiều thread, cần đồng bộ phù hợp |
| `Arena.ofAuto()` | Bộ nhớ giải phóng tự động khi không còn reachable theo GC | Có thể dùng nhiều thread |
| `Arena.global()` | Lifetime không giới hạn thực tế cho tới hết tiến trình | Có thể dùng nhiều thread |

`Arena.ofConfined()` thường thích hợp với phép tính native ngắn chạy trong một thread và có `try`-with-resources. `Arena.ofShared()` cần khi nhiều thread cùng dùng segment nhưng không tự đồng bộ dữ liệu. `Arena.global()` không hợp lý cho một luồng yêu cầu tạo nhiều bộ đệm lớn có lifetime ngắn vì giữ memory lâu.

### 10.2. Hai loại ràng buộc được kiểm tra

FFM hỗ trợ:

- **Spatial bounds:** truy cập không được vượt phạm vi `MemorySegment` hợp lệ.
- **Temporal bounds:** truy cập không được dùng segment sau khi scope đóng.

~~~java
MemorySegment saved;

try (Arena arena = Arena.ofConfined()) {
    saved = arena.allocate(ValueLayout.JAVA_INT);
    saved.set(ValueLayout.JAVA_INT, 0, 10);
}

// Sau scope.close(): thao tác sau không còn hợp lệ.
// int x = saved.get(ValueLayout.JAVA_INT, 0);
~~~

Khi truy cập segment thuộc arena confined từ thread khác, `WrongThreadException` có thể được ném. Với memory do native code trả về theo địa chỉ thô, việc tự khai lại size/lifetime bằng restricted APIs như `reinterpret` có thể phá các bảo đảm nếu thông tin được khai sai.

### 10.3. Native function có thể giữ pointer sau khi Java trả về

Nếu API native được phép giữ pointer để sử dụng sau lời gọi, không thể luôn tạo buffer trong `Arena.ofConfined()` rồi đóng ngay khi hàm trả về. Phải có hợp đồng lifecycle:

- Hàm có sao chép dữ liệu ngay hay giữ pointer?
- Native code giữ pointer bao lâu?
- Ai gọi hàm giải phóng tài nguyên?
- Có callback từ native thread sau khi arena/Java object đã đóng không?
- Native library có yêu cầu mọi lời gọi cùng một OS thread không?

Nếu đóng `Arena` trước khi library kết thúc sử dụng pointer, native code có thể gặp use-after-free và gây crash dù Java đã dùng `try`-with-resources đúng cú pháp.

### 10.4. Đừng dùng native access thay thế giới hạn tài nguyên

Off-heap allocation có thể vượt ngưỡng Java heap mà không phản ánh trực tiếp ở các chỉ số heap thông thường. Cần:

- Giới hạn kích thước mỗi allocation và tổng native memory theo request/service.
- Đóng arena rõ ràng và tránh giữ nhiều arena sống quá lâu.
- Đo resident set size (RSS), native memory và hiệu ứng container limits.
- Không đưa dữ liệu không tin cậy trực tiếp thành length/pointer tùy ý.
- Giới hạn số lời gọi native đồng thời nếu library không thread-safe.

Native memory vẫn là tài nguyên thật của tiến trình, có thể làm OS kill process khi vượt giới hạn.

## 11. Đóng gói thư viện native cùng ứng dụng Java

### 11.1. Một JAR không biến shared library thành binary đa nền tảng

Một file Java JAR là gói ZIP chứa class/resources và metadata. Native library vẫn phải có **binary đúng OS/architecture** và được native loader truy cập.

Ví dụ cấu trúc release đa nền tảng:

~~~text
release/
├── app.jar
├── native/
│   ├── linux-x86_64/
│   │   └── libmathbridge.so
│   ├── linux-aarch64/
│   │   └── libmathbridge.so
│   ├── macos-aarch64/
│   │   └── libmathbridge.dylib
│   └── windows-x86_64/
│       └── mathbridge.dll
└── LICENSES/
~~~

Release cho **một target cụ thể** có thể chỉ chứa đúng native binary của target đó để giảm kích thước và sự nhầm lẫn. Việc đặt các file dưới cùng thư mục phân phối **chưa đủ** để `System.loadLibrary` chắc chắn nhìn thấy chúng; ứng dụng vẫn cần chiến lược lookup hoặc đường dẫn rõ ràng.

### 11.2. Tải bằng đường dẫn tuyệt đối có kiểm soát

Với thư viện do ứng dụng phân phối, có thể cấu hình path tuyệt đối và gọi:

~~~java
import java.nio.file.Path;

public final class NativeLoader {
    private NativeLoader() {}

    public static void loadTrustedLibrary(Path nativeFile) {
        Path absolute = nativeFile.toAbsolutePath().normalize();
        System.load(absolute.toString());
    }
}
~~~

Ví dụ này **chỉ nên nhận đường dẫn được deploy và kiểm soát**, không phải giá trị tùy ý từ HTTP request. Nó minh họa cách gọi `System.load`, chưa thực hiện kiểm tra nguồn binary, chữ ký, quyền tệp hoặc symlink. Với FFM, có thể dùng `SymbolLookup.libraryLookup(absolute, arena)` theo hợp đồng library và lifetime.

Việc `Path.normalize` thành công không chứng minh file an toàn trước symlink manipulation; nếu có attacker có thể thay đổi đường dẫn khi tải, phải thiết kế vùng lưu trữ và phân quyền chặt để tránh **TOCTOU**.

### 11.3. Library trong JAR resource có thể cần giải nén

Native loader của OS thường yêu cầu một thư viện thực ở nơi có thể map/load. Chỉ đặt `libmathbridge.so` trong JAR như resource **không bảo đảm** `System.loadLibrary("mathbridge")` tự nạp từ bên trong JAR.

Nếu chọn chiến lược extract resource ra file trước khi tải, cần:

- Tạo vị trí extraction do ứng dụng sở hữu, có quyền truy cập phù hợp.
- Chọn đúng binary theo OS/architecture/ABI.
- Kiểm tra checksum/chữ ký từ nguồn phát hành đáng tin.
- Chống archive path traversal, symlink attack và việc thay thế file trong lúc tải.
- Đặt tên/version đủ rõ để tránh trùng thư viện giữa các tiến trình hoặc phiên bản.
- Lưu ý hệ thống có thể từ chối execute/map library trong một số vị trí (ví dụ policy `noexec`, quarantine hoặc code signing).
- Dọn tài nguyên theo lifecycle; không xóa file đang được loader sử dụng với giả định mọi OS xử lý giống nhau.

Đối với ứng dụng desktop/server thông thường, phân phối native binary như **file bên ngoài JAR trong installation/app image** thường dễ quan sát và kiểm soát hơn việc tự triển khai extractor phức tạp.

### 11.4. java.library.path không phải câu trả lời cho mọi loader

`-Djava.library.path=...` có thể ảnh hưởng cách JVM tìm thư viện của `System.loadLibrary`, tùy implementation và môi trường. Nhưng nó không tự giải quyết phụ thuộc native **bên trong** shared library; OS loader có thể tìm dependency bằng các quy tắc khác như Windows DLL search, ELF RPATH/RUNPATH hoặc macOS install name.

Không dựa vào việc sửa `System.setProperty("java.library.path", ...)` **sau khi ứng dụng đã khởi động** rồi mặc định JVM sẽ tìm lại như mong đợi. Chọn cấu hình launcher và packaging được kiểm thử trên từng target.

## 12. jpackage, jlink và launcher có quyền native access

### 12.1. jpackage tạo ứng dụng phân phối theo nền tảng

`jpackage` trong JDK 27 có thể tạo app image hoặc native installer cho nền tảng host:

- Windows: các định dạng như `exe`, `msi`.
- macOS: `pkg`, `dmg`.
- Linux: `deb`, `rpm`.
- `app-image`: layout ứng dụng có launcher và runtime/dependencies theo cấu hình.

**jpackage không hỗ trợ cross-platform packaging theo một lần build duy nhất:** cần thực hiện trên nền tảng tương ứng. Native libraries càng làm yêu cầu CI theo OS/architecture trở nên quan trọng.

### 12.2. Ví dụ app image cho ứng dụng classpath

Giả sử thư mục `dist` có `app.jar` và các artifact native dành cho nền tảng đang build. Lệnh khung:

~~~bash
jpackage \
    --type app-image \
    --name NativeBridgeApp \
    --input dist \
    --main-jar app.jar \
    --main-class com.example.Main \
    --java-options "--enable-native-access=ALL-UNNAMED"
~~~

`--input` đóng gói các file đầu vào vào application image; `--java-options` cấu hình VM khi launcher chạy. **Lệnh này chưa giải quyết đường dẫn tải native library**, chưa cung cấp một `app.jar` thực hay C binary trong ngữ cảnh bài học. Ứng dụng phải tự biết vị trí native artifact trong layout được tạo hoặc nhận absolute path qua cấu hình đáng tin cậy.

Với ứng dụng modular, có thể dùng `--module-path` và `--module module/name.Main`, rồi chuyển JVM option thành:

~~~text
--enable-native-access=com.example.bridge
~~~

Phần này chỉ đúng nếu module `com.example.bridge` có mặt và là module thực hiện restricted operations.

### 12.3. Dùng jlink tạo custom runtime

`jlink` tạo runtime image từ named modules và dependency của chúng. Một custom runtime giúp gói đúng JDK modules, giảm phụ thuộc vào JRE cài trên máy đích, nhưng **không tự xây dựng native library của bên thứ ba cho mọi nền tảng**.

Ví dụ khung:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.app \
    --launcher native-app=com.example.app/com.example.app.Main \
    --output runtime-image
~~~

Trong trường hợp này, `mods` cần chứa module ứng dụng và các dependency phù hợp, runtime image được tạo cho platform đang chạy. Các flag native access vẫn phải được áp dụng qua launcher/VM configuration được hỗ trợ khi chạy, hoặc thông qua cơ chế đóng gói option trong runtime image nếu thích hợp.

**Không trộn** `--enable-native-access` với `requires`: một cái là quyền truy cập native runtime, một cái là dependency module.

### 12.4. Cấp quyền chính xác hơn khi đóng gói

Một release kiểm soát tốt nên chứa:

~~~text
Application launcher:
  --enable-native-access=com.example.bridge

Module graph:
  com.example.app -> com.example.bridge

Native artifact:
  native/<target-os>-<target-arch>/libmathbridge...

Policy:
  --illegal-native-access=deny   (dùng trong test tương thích)
~~~

Đối với launcher đóng gói thành binary app, người dùng cuối thường không chạy lệnh `java` thủ công. Vì thế đội phát triển phải **tài liệu hóa option trong packaging configuration** và kiểm thử trên sản phẩm đã đóng gói, không chỉ trên IDE.

## 13. Dò tìm native access khi nâng cấp thư viện

### 13.1. jnativescan là công cụ hiện hành của JDK

`jnativescan` là công cụ phân tích tĩnh hỗ trợ tìm nơi sử dụng restricted methods và khai báo `native` trong JAR. Ví dụ:

~~~bash
jnativescan --class-path app.jar
~~~

Để nhận danh sách module cần native access khi quét module path:

~~~bash
jnativescan \
    --module-path mods \
    --add-modules com.example.app \
    --print-native-access
~~~

Kết quả giúp lên danh sách module được dự kiến cho `--enable-native-access=...`. Khi quét classpath, mã thuộc unnamed module nên có thể được báo là `ALL-UNNAMED`.

### 13.2. Phân tích tĩnh có giới hạn

Không được hiểu rằng `jnativescan` đảm bảo phát hiện mọi hành vi native có thể xảy ra trong runtime. Code sinh động, reflection, dependency được nạp thêm, native code tự gọi native khác, lời gọi gián tiếp hoặc biến thể classpath có thể làm kết quả thực tế khác những gì tool phân tích.

Quy trình nên kết hợp:

1. `jnativescan` với đúng module/classpath và target release.
2. Chạy integration/smoke tests bằng `--illegal-native-access=deny`.
3. Theo dõi warning trong môi trường kiểm thử cho các đường code hiếm khi chạy.
4. Kiểm tra dependency tree và cập nhật native binaries của vendor.
5. Sử dụng JFR events như `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload` khi cần quan sát native library lifecycle.

### 13.3. Không cấp ALL-UNNAMED theo phản xạ

Nếu scan tìm thấy một thư viện đơn lẻ đang gọi native code mà nó nằm trên classpath, có thể cần cấp `ALL-UNNAMED` theo deployment hiện tại. Nhưng đó là **cấp cho toàn bộ mã trên classpath**, không chỉ cho một JAR.

Nếu threat model nhạy cảm và stack hỗ trợ module path, nên cân nhắc đưa thư viện đó lên module path (module rõ ràng hoặc automatic module khi phù hợp), rồi cấp quyền theo module name. Với automatic module, tên có thể phụ thuộc tên JAR hoặc metadata; cần bảo đảm ổn định trước khi đưa vào startup config.

## 14. An toàn chuỗi cung ứng native binary

### 14.1. Tải thư viện là thực thi mã

Không nên coi shared library như file dữ liệu vô hại. Việc OS loader nạp một binary có thể kích hoạt initialization hooks và mã native trước khi Java gọi một hàm nghiệp vụ nào đó.

Do vậy:

- Chỉ tải thư viện từ nguồn release tin cậy, có quản lý version và provenance.
- Kiểm tra checksum/chữ ký của artifact theo quy trình phát hành.
- Dùng quyền file system hạn chế đối với thư mục chứa binary.
- Tránh search path do người dùng không tin cậy kiểm soát.
- Đánh giá license, SBOM, CVE và việc cập nhật dependency native bên trong thư viện.
- Phân phối bản build riêng cho từng OS/architecture và ghi nhận thông tin build.
- Hạn chế nạp thư viện trực tiếp từ thư mục tải xuống, cache không bảo vệ hoặc path từ request.

### 14.2. Tại sao System.load(path) chưa đủ là an toàn?

~~~java
// Không bao giờ lấy trực tiếp từ input HTTP không tin cậy:
System.load(userSuppliedAbsolutePath);
~~~

Dù `System.load` yêu cầu đường dẫn tuyệt đối, một path hợp lệ vẫn có thể trỏ tới binary độc hại. Nếu tiến trình có quyền load DLL/SO đó, mã native có thể được thực thi với quyền của tiến trình.

Cần kiểm soát **nguồn dữ liệu**, quyền của thư mục, tính bất biến của binary sau verify và lifecycle deployment. Không xem `normalize()` hay `Files.exists()` là sandbox ngăn attacker sửa symlink giữa bước kiểm tra và bước tải.

### 14.3. Bảo mật không dừng ở Java module

Native module có thể truy cập các hệ thống mà cơ chế module Java không sandbox được. Chính sách giảm rủi ro cần bao gồm:

- OS process isolation/container boundaries.
- Chạy dưới tài khoản ít quyền.
- Filesystem permissions và hạn chế network capability.
- Giới hạn CPU/RSS/memory và số descriptor nếu có thể.
- Tách native component ra process khác qua IPC nếu code không đủ tin cậy hoặc có yêu cầu fault isolation.
- Audit logging và crash reporting, tránh leak dữ liệu nhạy cảm qua dumps/log.

Nếu thư viện có nguy cơ crash cao nhưng nghiệp vụ yêu cầu availability, tách process có thể có giá trị hơn chỉ thêm exception handling: Java exception không bắt được mọi segmentation fault của native code.

## 15. Tình huống thực tế và cách ra quyết định

### 15.1. SDK thiết bị chỉ cung cấp DLL Windows

Thiết kế có thể là:

- Java public API định nghĩa interface `DeviceClient`.
- Native adapter dùng JNI hoặc FFM để gọi SDK.
- Adapter chỉ được đóng gói cho Windows/architecture mà vendor hỗ trợ.
- Linux/macOS không cố tải DLL; chức năng báo không được hỗ trợ hoặc có implementation khác.
- Launcher cấp native access đúng module của adapter.
- CI chạy smoke test trên Windows phù hợp, không chỉ compile Java trên Linux.

Kết luận: Java API có thể chung, còn **khả năng chạy** phụ thuộc SDK native.

### 15.2. Thư viện xử lý ảnh có bản Linux và macOS

Có thể chọn FFM nếu thư viện cung cấp C ABI rõ, phiên bản header/API được quản lý tốt. Phát hành từng gói native artifact, kiểm tra kích thước struct/ABI và các dependencies như libc/framework của host.

Không nên lấy `os.name` làm lý do tự nạp bất kỳ file có cùng tên: vẫn phải xác minh architecture và artifact provenance.

### 15.3. Chỉ cần vùng nhớ off-heap lớn

Nếu không thực sự gọi thư viện native, sử dụng `Arena`/`MemorySegment` để cấp phát, truy cập và đóng vùng nhớ đúng lifetime. Không cần gói DLL/SO không tồn tại, cũng không cấp `ALL-UNNAMED` chỉ vì thấy từ khóa “off-heap”.

Cần đánh giá liệu `ByteBuffer.allocateDirect` hoặc API Java collection/IO khác có đơn giản hơn; lựa chọn theo bài toán thực, không vì FFM “mới hơn” mà mặc định thay toàn bộ storage abstractions.

### 15.4. Tích hợp JNI lâu năm đang có warning khi nâng JDK

Không nhất thiết phải viết lại bằng FFM ngay. Hãy:

1. Chạy `jnativescan` để xác định JAR/module liên quan.
2. Xem các warning cụ thể khi load JNI và bind native methods.
3. Cấp `--enable-native-access` đúng module/`ALL-UNNAMED` tùy deployment.
4. Chạy test với `--illegal-native-access=deny`.
5. Kiểm tra lại native library dependencies và ABI theo OS/JDK runtime hiện tại.
6. Lập kế hoạch chuyển sang FFM chỉ nếu lợi ích và tính khả thi vượt chi phí/risks.

JNI vẫn là một lựa chọn được tài liệu hóa; vấn đề cần sửa là **cấu hình quyền, dependency và ABI không rõ ràng**.

## 16. Các lỗi thường gặp

| Lỗi hoặc hiểu lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `Arena.allocate` rồi cho rằng luôn cần native access | Cấp quyền rộng không cần thiết | Phân biệt API FFM thông thường và restricted |
| Chỉ dùng `--enable-native-access=java.base` | Cấp sai module | Cấp cho module **gọi** restricted operation |
| Tưởng `requires` trong `module-info.java` là quyền native | Vẫn warning/exception | Dùng launcher option cấp native access |
| Thấy app chạy ở chế độ `warn` rồi kết luận cấu hình đúng | Có thể hỏng khi chuyển sang `deny` | Smoke test `--illegal-native-access=deny` |
| Phụ thuộc dài hạn vào `--illegal-native-access=allow` | Che cảnh báo và nợ migration | Cấp quyền hẹp, xử lý nguyên nhân |
| Gọi `System.loadLibrary` bằng `libfoo.so` | Tên không đúng contract | Dùng tên logic `foo` hoặc `System.load` với path |
| Tưởng library có trong JAR sẽ tự load | Loader không tìm thấy file | Đóng gói hoặc extract có kiểm soát |
| Giả định chỉ cần `java.library.path` cho mọi dependency | OS loader vẫn thiếu thư viện phụ | Kiểm tra RPATH/install name/DLL dependencies |
| Copy `.so` sang Windows | Không tương thích format | Build/publish đúng `.dll` |
| Dùng Linux x86_64 binary trên ARM64 | Không tương thích architecture | Release per-target, smoke test |
| Khai C `long` là Java `long` trên mọi OS | Sai ABI, sai dữ liệu hoặc crash | Dùng canonical layouts và kiểm tra ABI |
| Giữ pointer sau khi `Arena` đóng | Use-after-free | Thiết kế ownership/lifetime |
| Dùng `MemorySegment.reinterpret` tùy tiện | Truy cập ngoài bounds thật | Chỉ dùng khi có metadata đáng tin, hiểu restricted API |
| Đóng arena khi native callback vẫn dùng bộ nhớ | Crash hoặc data corruption | Chờ native hoàn tất trước khi đóng |
| Mở binary từ path do người dùng cung cấp | Có thể thực thi mã độc | Chỉ load artifact tin cậy, kiểm soát thư mục |
| Cho rằng `jpackage` build một lần cho mọi OS | Gói không chạy ở target khác | CI build trên từng nền tảng |
| Chỉ test Java compile, không test binary load | Runtime crash/UnsatisfiedLinkError | Smoke/integration test theo OS/arch |
| Tưởng cấp native access là bảo đảm memory safety | Sai chữ ký ABI vẫn crash | Kiểm chứng layout/contract, hạn chế quyền OS |
| Cho rằng `jnativescan` phát hiện được mọi đường native động | Bỏ sót ở runtime | Kết hợp static scan và runtime tests |
| Dùng API preview FFM cũ trong Java 27 | Sai signature/không compile | Dùng `java.lang.foreign` chính thức của JDK 27 |

## 17. Checklist phát hành ứng dụng có native library

Trước khi release:

1. **Xác định ranh giới native**: phương thức FFM/JNI nào gọi restricted operations, module nào chứa chúng?
2. **Chọn quyền tối thiểu**: `--enable-native-access=<module>` hay `ALL-UNNAMED` là cần thiết thật?
3. **Kiểm thử `deny`**: toàn bộ đường tích hợp native có chạy khi `--illegal-native-access=deny` không?
4. **Scan dependency**: chạy `jnativescan` trên đúng classpath/module path và target Java release.
5. **Chọn ABI rõ ràng**: C header, calling convention, data layouts, alignment, encoding và error convention đã cố định chưa?
6. **Quản lý ownership**: ai cấp phát/free bộ nhớ, native giữ pointer bao lâu, khi nào arena/library có thể đóng?
7. **Tạo ma trận build**: OS/architecture/libc/C runtime/version của native artifacts được liệt kê chưa?
8. **Đóng gói đầy đủ**: các shared-library dependencies, runtime/JDK modules và license files đã có chưa?
9. **Cấu hình loader**: đường dẫn tải native được kiểm soát, không phụ thuộc working directory ngẫu nhiên?
10. **Đảm bảo integrity**: binary có provenance/checksum/signature và thư mục không ghi được bởi attacker?
11. **Launcher options**: executable JAR, `jlink`/`jpackage` hoặc service/container đã truyền native access flags chưa?
12. **Smoke test sau đóng gói**: chạy bản phân phối thực trên máy/VM/container đích, không chỉ chạy trong IDE?
13. **Resource limits**: native memory, file descriptors, concurrency và memory leaks được giám sát chưa?
14. **Crash recovery**: có logging, dump policy và fault isolation nếu native code có thể crash JVM?
15. **Update strategy**: có thể cập nhật thư viện native bị CVE mà không phá ABI hoặc làm mất chữ ký không?

## 18. Câu hỏi tự kiểm tra

1. Off-heap memory có bắt buộc đồng nghĩa với việc gọi hàm C/JNI không?
2. Vì sao `Arena.ofConfined().allocate(...)` không nhất thiết cần `--enable-native-access`?
3. Kể tên ít nhất ba restricted operations hiện hành liên quan FFM/JNI.
4. Nếu `com.example.bridge` gọi `SymbolLookup.libraryLookup`, vì sao không đơn giản cấp quyền cho `java.base`?
5. Khác nhau giữa `--enable-native-access=ALL-UNNAMED` và cấp cho named module là gì?
6. `--illegal-native-access=warn` có từ chối thao tác ngay không? Còn `deny` thì sao?
7. Vì sao chạy thành công dưới mặc định `warn` chưa chứng minh ứng dụng đã sẵn sàng cho chính sách tương lai?
8. `Module.isNativeAccessEnabled()` phản ánh điều gì và không phản ánh điều gì?
9. Khác nhau giữa `System.load` và `System.loadLibrary` là gì?
10. Vì sao `SymbolLookup.loaderLookup()` không nhất thiết thấy thư viện chỉ được tải qua `libraryLookup`?
11. Khi tạo downcall FFM, vì sao Java không tự chứng minh function descriptor tương ứng ABI C thực?
12. Tại sao `libmathbridge.so` không thể dùng nguyên xi trên Windows dù JAR Java giống nhau?
13. Vì sao kích thước C `long` và Java `long` có thể làm binding bị lỗi?
14. `Arena.ofConfined` và `Arena.ofShared` khác nhau thế nào về thread ownership?
15. Vì sao native code giữ pointer khiến `try`-with-resources chưa đủ nếu đóng arena quá sớm?
16. Đặt `.dll` trong JAR có bảo đảm `System.loadLibrary` tìm ra không?
17. `jpackage` có tự tạo native binary đa nền tảng từ một build không?
18. `jnativescan` hỗ trợ xác định điều gì và giới hạn nào cần test runtime bù đắp?
19. Vì sao không được nạp thư viện từ đường dẫn tùy ý do HTTP request cung cấp?
20. Nếu một thư viện JNI cũ có warning, có nhất thiết phải thay bằng FFM ngay không?
21. Ngoài `--enable-native-access`, ba điều kiện deployment nào còn cần để ứng dụng FFM chạy được trên host mới?

## 19. Tài liệu tham khảo chính thức cho Java SE 27

- [Oracle Java SE 27 — Restricted Methods](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html): restricted FFM methods, cách cấp quyền module và chính sách illegal native access.
- [Oracle Java SE 27 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/27/core/foreign-function-and-memory-api.html): hướng dẫn FFM hiện hành, native linker, segments và arenas.
- [Java SE 27 API — Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/auto/global, lifetime và thread ownership.
- [Java SE 27 API — MemorySegment](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): truy cập vùng nhớ, bounds và scope.
- [Java SE 27 API — SymbolLookup](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SymbolLookup.html): libraryLookup và loaderLookup, symbols và quản lý lifetime.
- [Java SE 27 API — Linker](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html): downcall, ABI, function descriptor, canonical layouts và upcall.
- [Java SE 27 API — Module](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Module.html): `isNativeAccessEnabled()` và module identity.
- [Java SE 27 API — System](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html): `load`, `loadLibrary` và `mapLibraryName`.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--enable-native-access`, `--illegal-native-access` và launcher options.
- [Java SE 27 — jnativescan Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jnativescan.html): scan native usage trong JAR/module graph.
- [Java SE 27 — jpackage Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html): app-image, runtime/launcher và packaging theo nền tảng.
- [Java SE 27 — jlink Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): xây dựng runtime image cho named modules.
- [Oracle Java SE 27 Migration Guide — Restrictions on Accessing Native Code](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): thay đổi hạn chế JNI/FFM và các bước migration.
- [Java SE 27 — JNI Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/intro.html): JNI vẫn được hỗ trợ, quy ước và các rủi ro integrity.
