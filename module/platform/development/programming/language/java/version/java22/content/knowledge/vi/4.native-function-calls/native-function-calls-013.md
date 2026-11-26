# Kiểm tra tính di động, đóng gói thư viện và lựa chọn FFM cho từng phần tích hợp JNI

## Gọi hàm native trong Java hiện đại

Module `JAVA_VERSION_JAVA22` học các tính năng được giới thiệu trong Java 22 còn hữu ích ở Java hiện đại. Foreign Function & Memory (FFM) API được hoàn thiện trong JDK 22 và là API chính thức từ đó. FFM cho phép Java gọi trực tiếp hàm theo ABI native và truy cập bộ nhớ ngoài heap thông qua các kiểu như `Linker`, `SymbolLookup`, `FunctionDescriptor`, `MemorySegment` và `Arena`.

FFM là lựa chọn ưu tiên khi cần gọi một hàm native có giao diện C phù hợp. Tuy nhiên, JNI vẫn là giao diện được hỗ trợ và tiếp tục cần thiết trong những phần tích hợp phụ thuộc trực tiếp vào JVM, chẳng hạn native code thao tác sâu với đối tượng Java hoặc một ứng dụng native nhúng JVM. Vì vậy, khi nâng cấp một hệ thống đang dùng JNI, nên đánh giá từng điểm tích hợp để quyết định giữ JNI, chuyển sang FFM hay kết hợp cả hai.

Điều quan trọng là FFM không làm cho thư viện native trở nên độc lập nền tảng. Java bytecode có thể chạy trên nhiều hệ điều hành, nhưng tệp thư viện native vẫn được biên dịch cho hệ điều hành, kiến trúc CPU và ABI cụ thể.

## 1. Hiểu đúng tính di động của thư viện native

Một thư viện native thường được phân phối dưới dạng thư viện chia sẻ:

| Nền tảng | Định dạng thường gặp | Ví dụ kiến trúc |
| --- | --- | --- |
| Linux | `.so` | x86-64, AArch64 |
| Windows | `.dll` | x64, ARM64 |
| macOS | `.dylib` hoặc framework | Intel x86-64, Apple Silicon ARM64 |

Đây là những định dạng phổ biến, không phải quy tắc đủ để xác định mọi trường hợp tương thích. Một tệp `.so` biên dịch cho Linux/AArch64 không thể được nạp trên Windows/x64. Ngay cả hai thư viện cùng là Linux/x86-64 cũng có thể không tương thích nếu chúng phụ thuộc vào ABI hoặc runtime khác nhau.

Khi kiểm tra tính di động, cần xác định ít nhất các yếu tố sau:

- **Hệ điều hành và kiến trúc CPU:** Linux, Windows, macOS; x86-64 hay ARM64.
- **ABI và calling convention:** quy tắc truyền tham số, kiểu trả về, cách căn chỉnh dữ liệu, tên symbol và quy tắc liên kết của nền tảng.
- **Runtime native:** phiên bản glibc hoặc musl trên Linux, runtime C/C++ cần thiết trên Windows, hoặc các thư viện hệ thống mà `.dylib` phụ thuộc trên macOS.
- **Kiểu dữ liệu và cấu trúc:** kích thước `long`, `size_t`, con trỏ, alignment, padding, byte order và cách biểu diễn chuỗi.
- **Symbol được export:** hàm cần gọi phải có tên và quy tắc export mà chương trình Java có thể tra cứu.
- **Phụ thuộc bắc cầu:** thư viện native có thể cần thêm các thư viện chia sẻ khác khi được nạp.

Ví dụ, C `long` có kích thước 8 byte trên nhiều ABI Linux/x64 nhưng 4 byte trên Windows/x64. Do đó, không thể chỉ nhìn tên kiểu rồi ánh xạ C `long` thành Java `long` trên mọi hệ điều hành. Với FFM, hãy lấy layout của kiểu C từ `Linker.nativeLinker().canonicalLayouts()` khi cần mô tả đúng ABI đang chạy.

Một JAR chứa class Java vẫn có thể dùng chung trên nhiều nền tảng, nhưng thư viện native đi kèm cần có biến thể tương ứng cho từng target. Có thể tổ chức artifact theo classifier như `linux-x86_64`, `linux-aarch64`, `windows-x86_64`, `macos-aarch64` và `macos-x86_64`. Ứng dụng chọn đúng biến thể khi chạy hoặc đóng gói mỗi biến thể vào gói cài đặt riêng.

## 2. Thiết kế giao diện native ổn định trước khi đóng gói

FFM làm giảm nhu cầu viết lớp trung gian JNI cho các hàm C đơn giản, nhưng nó vẫn cần một giao diện native ổn định. Nếu thư viện được viết bằng C++, nên tạo một lớp giao tiếp C nhỏ thay vì cố gọi trực tiếp các symbol C++ có tên đã bị name-mangling hoặc kiểu dữ liệu phức tạp.

Một giao diện C phù hợp thường có các đặc điểm:

- Export các hàm có tên ổn định, dùng `extern "C"` khi biên dịch bằng C++.
- Dùng kiểu có kích thước xác định như `int32_t`, `uint64_t` khi giao thức cần số bit cố định.
- Truyền chuỗi theo quy ước rõ ràng, ví dụ UTF-8 kết thúc bằng byte NUL hoặc cặp con trỏ và độ dài.
- Quy định rõ bên nào cấp phát và giải phóng bộ nhớ; cung cấp hàm `create`/`destroy` hoặc `allocate`/`free` tương ứng nếu cần.
- Không để exception C++ đi xuyên qua ranh giới ABI C. Chuyển lỗi thành mã trạng thái hoặc cấu trúc kết quả có quy ước rõ ràng.
- Định nghĩa phiên bản ABI và cách kiểm tra tương thích khi thư viện có thể được cập nhật độc lập với ứng dụng Java.

Ví dụ một hàm C có giao diện ổn định:

```c
#include <stdint.h>

#if defined(_WIN32)
    #define API __declspec(dllexport)
#else
    #define API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

API int32_t native_add(int32_t left, int32_t right) {
    return left + right;
}

#ifdef __cplusplus
}
#endif
```

Hàm này không nhận đối tượng Java, không yêu cầu `JNIEnv*` và dùng hai số nguyên 32-bit. Đây là kiểu giao diện thích hợp để FFM liên kết trực tiếp. Với hàm phức tạp hơn, cần mô tả chính xác các con trỏ, layout struct, quy tắc sở hữu bộ nhớ và calling convention trong `FunctionDescriptor` cùng các `MemoryLayout` tương ứng.

## 3. Nạp thư viện và tìm symbol bằng FFM hoặc JNI

Hai API có cách nạp và tra cứu symbol khác nhau.

### Nạp trực tiếp bằng FFM

`SymbolLookup.libraryLookup(Path, Arena)` nạp thư viện từ đường dẫn và tạo bộ tra cứu symbol. Vòng đời của lookup gắn với `Arena` được truyền vào. Khi arena đóng, thư viện gắn với lookup có thể được giải phóng; vì vậy không sử dụng symbol hoặc method handle sau khi arena đã đóng.

Ví dụ Java gọi `native_add`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

static int add(Path libraryPath, int left, int right) throws Throwable {
    Linker linker = Linker.nativeLinker();

    try (Arena arena = Arena.ofConfined()) {
        SymbolLookup library = SymbolLookup.libraryLookup(libraryPath, arena);
        MemorySegment address = library.findOrThrow("native_add");

        MethodHandle add = linker.downcallHandle(
            address,
            FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT
            )
        );

        return (int) add.invokeExact(left, right);
    }
}

// Ví dụ gọi: int result = add(Path.of("duong-dan-thu-vien-native"), 20, 22);
// result = 42
```

Ví dụ giả định hàm C dùng hai tham số và giá trị trả về có biểu diễn ABI tương ứng với số nguyên 32-bit. Khi dùng kiểu C khác hoặc struct, hãy lấy layout đúng từ native linker và mô tả đúng chữ ký hàm. Đường dẫn thư viện trong ví dụ phải được thay bằng đường dẫn của binary phù hợp với nền tảng đang chạy.

### Nạp thư viện bằng JNI

JNI thường nạp thư viện bằng `System.loadLibrary` hoặc `System.load`:

```java
final class NativeBridge {
    static {
        System.loadLibrary("nativecore");
    }

    static native int calculate(int left, int right);
}
```

`System.loadLibrary("nativecore")` nhận tên logic của thư viện, không truyền tiền tố, phần mở rộng hoặc đường dẫn nền tảng. JVM ánh xạ tên đó theo quy tắc của hệ điều hành, chẳng hạn thành `libnativecore.so` trên Linux hoặc `nativecore.dll` trên Windows. `System.load(...)` dùng đường dẫn tuyệt đối đến tệp thư viện.

### Dùng FFM với thư viện đã được JNI nạp

Một thư viện có thể chứa cả hàm JNI và các hàm C được export riêng. Nếu thư viện đã được nạp qua `System.loadLibrary`, `SymbolLookup.loaderLookup()` có thể tìm các symbol trong những thư viện gắn với class loader của mã gọi:

```java
System.loadLibrary("nativecore");

SymbolLookup symbols = SymbolLookup.loaderLookup();
MemorySegment address = symbols.findOrThrow("native_add");
```

Cách này hữu ích khi chuyển từng hàm sang FFM mà vẫn giữ những native method JNI còn cần thiết. Tuy nhiên, symbol JNI như `Java_package_Class_method` là entry point theo quy ước JNI; không thể coi nó như một hàm C thông thường có chữ ký `int(int, int)`. FFM cần một hàm có ABI C phù hợp và `FunctionDescriptor` khớp với chữ ký thực tế.

Nếu thư viện dựa vào `JNI_OnLoad` để đăng ký native method hoặc khởi tạo trạng thái JNI, hãy tiếp tục nạp thư viện bằng `System.loadLibrary` để JVM thực hiện lifecycle hook đó, rồi dùng `loaderLookup()` cho những symbol C được export riêng. Không nên giả định việc nạp thư viện bằng `libraryLookup` sẽ thay thế quy trình khởi tạo JNI.

## 4. Đóng gói thư viện cho nhiều nền tảng

Đóng gói ứng dụng Java không tự biên dịch hoặc chuyển đổi thư viện native sang nền tảng khác. Quy trình phát hành cần tạo và kiểm thử binary native riêng cho mỗi target được hỗ trợ.

Một cấu trúc artifact có thể được tổ chức như sau:

```text
application/
  app.jar
  native/
    linux-x86_64/
      libnativecore.so
    linux-aarch64/
      libnativecore.so
    windows-x86_64/
      nativecore.dll
    macos-aarch64/
      libnativecore.dylib
    macos-x86_64/
      libnativecore.dylib
```

Khi khởi động, ứng dụng xác định target đã được hỗ trợ rồi chọn đúng binary. Nếu native library được nhúng trong JAR dưới dạng resource, ứng dụng phải giải nén nó ra một vị trí trên filesystem trước khi gọi `libraryLookup(Path, arena)` hoặc `System.load`. Thư mục giải nén cần có quyền truy cập phù hợp; không nạp một binary tùy ý từ thư mục mà người dùng khác có thể thay thế.

Khi đóng gói, cần chú ý:

1. **Build theo target:** biên dịch native library cho từng hệ điều hành và kiến trúc, dùng đúng ABI và phiên bản runtime mục tiêu.
2. **Đóng gói phụ thuộc:** kèm hoặc khai báo các thư viện native phụ thuộc theo cách phù hợp với hệ điều hành. Kiểm tra cả thư viện trực tiếp lẫn phụ thuộc bắc cầu.
3. **Định tuyến binary:** xác định rõ quy tắc chọn thư viện từ OS và kiến trúc; xử lý target chưa hỗ trợ bằng thông báo lỗi dễ hiểu.
4. **Giữ tên và symbol nhất quán:** export đúng symbol, giữ tương thích ABI giữa các bản cập nhật và tránh đổi tên thư viện không có kế hoạch.
5. **Bảo vệ artifact:** kiểm tra nguồn phát hành, chữ ký hoặc checksum của binary; không nạp thư viện lấy từ đường dẫn không đáng tin cậy.
6. **Kiểm thử trên môi trường sạch:** chạy trên máy hoặc image gần với môi trường người dùng, không dựa vào thư viện tình cờ có sẵn trên máy build.

`jlink` tạo runtime image tùy chỉnh chứa các module JDK cần thiết. `jpackage` tạo gói cài đặt hoặc application image cho nền tảng đích. Hai công cụ này hỗ trợ đóng gói runtime và ứng dụng Java; native library của ứng dụng vẫn cần được đưa vào artifact và bố trí đúng nơi để trình nạp hệ điều hành tìm thấy. Gói `jpackage` cho nhiều hệ điều hành cần được tạo trên từng nền tảng đích tương ứng.

Ví dụ tạo application image trên từng máy build tương ứng:

```bash
# Chạy trên máy build Windows, macOS hoặc Linux tương ứng
jpackage --type app-image \
  --name NativeDemo \
  --input input \
  --main-jar app.jar
```

Lệnh trên minh họa cách tạo application image. Nó không tạo ra các biến thể `.dll`, `.so` hay `.dylib`; pipeline phát hành phải cung cấp binary native phù hợp và kiểm tra vị trí nạp của nó trong image kết quả.

### Kiểm tra phụ thuộc và kiến trúc

Ngoài việc kiểm tra tên tệp, cần xác minh binary thực sự có đúng kiến trúc và dependency. Tùy hệ điều hành, có thể dùng `file` và `readelf` trên Linux, `otool -L` trên macOS, hoặc `dumpbin /DEPENDENTS` trên Windows. Những công cụ này giúp phát hiện binary sai kiến trúc, thiếu runtime hoặc thiếu thư viện chia sẻ trước khi đóng gói.

Một ma trận kiểm thử phát hành nên có ít nhất một dòng cho mỗi tổ hợp OS/CPU/ABI được hỗ trợ:

| Target | Binary native | Kiểm tra cần thực hiện |
| --- | --- | --- |
| Linux x86-64 | `.so` x86-64 | ABI libc, dependency, symbol và quyền nạp. |
| Linux AArch64 | `.so` AArch64 | Binary ARM64, ABI libc và dependency. |
| Windows x64 | `.dll` x64 | Export symbol, runtime C/C++ và DLL phụ thuộc. |
| macOS Apple Silicon | `.dylib` ARM64 | Kiến trúc ARM64, dependency và chữ ký khi phân phối. |
| macOS Intel | `.dylib` x86-64 | Kiến trúc x86-64, dependency và chữ ký khi phân phối. |

Chỉ liệt kê những target thực sự được dự án hỗ trợ. Không nên suy ra một binary chạy được trên mọi bản phân phối Linux chỉ vì nó có kiến trúc x86-64; mức glibc hoặc các dependency hệ thống vẫn có thể khác nhau.

## 5. Chọn FFM hay JNI cho từng phần tích hợp

FFM và JNI giải quyết cùng bài toán liên kết Java với mã native nhưng có mô hình lập trình khác nhau. Không cần chuyển toàn bộ thư viện chỉ vì một hàm đã có thể dùng FFM.

| Nhu cầu tích hợp | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Gọi hàm C có chữ ký đơn giản, rõ ràng | FFM | Có thể tạo `MethodHandle` trực tiếp từ symbol và `FunctionDescriptor`, không cần viết native method và lớp JNI trung gian. |
| Truy cập buffer, struct hoặc vùng nhớ native | FFM | `MemorySegment`, `Arena`, `MemoryLayout` và `VarHandle` cung cấp mô hình bộ nhớ có kiểm tra phạm vi và vòng đời. |
| Gọi API C của thư viện hiện có | FFM | Có thể liên kết trực tiếp nếu symbol được export và ABI được mô tả chính xác. |
| Thư viện chỉ cung cấp entry point theo quy ước JNI | Giữ JNI hoặc bổ sung lớp C ABI | Entry point JNI cần `JNIEnv*` và chữ ký JNI; không phải hàm C độc lập để gọi bằng FFM. |
| Native code thao tác sâu với object, field, method hoặc exception Java | JNI thường phù hợp hơn | JNI cung cấp `JNIEnv` và các hàm truy cập trực tiếp mô hình đối tượng của JVM. |
| Native application tạo và nhúng JVM | JNI Invocation API | Đây là giao diện dành cho chương trình native khởi tạo hoặc quản lý JVM. |
| Cần gọi ngược từ native vào Java | FFM upcall hoặc JNI | FFM có upcall stub cho callback theo chữ ký hỗ trợ; JNI phù hợp khi callback cần tương tác với JVM qua `JNIEnv`. |
| Hệ sinh thái hoặc nền tảng chỉ hỗ trợ tích hợp JNI | Giữ JNI | Khả năng hỗ trợ FFM phải được xác nhận trên runtime mục tiêu; không giả định mọi nền tảng Java đều có cùng mức hỗ trợ. |

FFM không tự động thay thế mọi tính năng của JNI. Ngược lại, JNI cũng không cần bị loại bỏ khỏi những phần đang hoạt động ổn định và cần khả năng truy cập JVM trực tiếp. Đánh giá theo từng hàm hoặc nhóm hàm giúp giới hạn phạm vi thay đổi và dễ kiểm chứng hơn.

### Những điều FFM cải thiện

- Không cần khai báo `native` method và tạo lớp C/C++ trung gian chỉ để chuyển lời gọi đến một hàm C đơn giản.
- Có thể mô tả chữ ký native bằng `FunctionDescriptor` và gọi qua `MethodHandle`.
- Có thể mô tả bố cục dữ liệu bằng `MemoryLayout`, quản lý vùng nhớ qua `Arena` và `MemorySegment`.
- Có thể dùng `SymbolLookup` để tìm symbol từ thư viện native hoặc thư viện đã được nạp qua JNI.
- Có thể tạo upcall stub để mã native gọi một hàm Java có chữ ký phù hợp.

Các kiểm tra phạm vi và vòng đời của `MemorySegment` làm giảm một số lỗi truy cập bộ nhớ thường gặp. Tuy nhiên, FFM không biến mã native thành mã an toàn tuyệt đối: hàm C vẫn có thể truy cập con trỏ sai, ghi vượt vùng nhớ hoặc làm JVM sập. Chữ ký, ABI, quyền sở hữu bộ nhớ và vòng đời callback vẫn phải được thiết kế chính xác.

### Khi nào nên giữ JNI

Giữ JNI khi native code cần dùng trực tiếp `JNIEnv` để tạo hoặc kiểm tra đối tượng Java, gọi method, truy cập field, tạo global/local reference, quản lý exception Java hoặc gắn thread native vào JVM. JNI Invocation API cũng cần thiết khi một chương trình native phải khởi tạo JVM.

Nếu thư viện hiện tại chỉ cung cấp các hàm JNI, có thể tiếp tục dùng chúng trong khi bổ sung một lớp C ABI mỏng cho các thao tác mới. Không nên gọi trực tiếp entry point JNI từ FFM bằng cách tự đoán chữ ký: các hàm đó được thiết kế để JVM gọi với tham số theo quy ước JNI.

## 6. Di chuyển từng phần từ JNI sang FFM

Một lộ trình thực tế có thể triển khai theo các bước sau:

1. **Kiểm kê điểm gọi native:** tìm các khai báo `native`, `System.loadLibrary`, `System.load`, lớp wrapper, thư viện và dependency native. Trên JDK hiện hành, công cụ `jnativescan` có thể quét class path hoặc module path để phát hiện một số điểm dùng JNI và restricted methods.
2. **Phân loại từng hàm:** xác định hàm chỉ dùng C ABI hay cần `JNIEnv`, thao tác object Java, quản lý thread hoặc JVM. Nhóm thứ nhất là ứng viên chuyển sang FFM.
3. **Ổn định giao diện C:** nếu thư viện chỉ có API C++, JNI entry point hoặc kiểu dữ liệu khó ánh xạ, tạo wrapper C nhỏ với symbol export và quy tắc bộ nhớ rõ ràng.
4. **Viết binding FFM:** mô tả chữ ký bằng `FunctionDescriptor`, tìm symbol bằng `SymbolLookup`, tạo downcall handle và quản lý vùng nhớ bằng `Arena`.
5. **Cho hai đường tích hợp cùng tồn tại:** giữ JNI cho hàm còn phụ thuộc JVM, chuyển những hàm phù hợp sang FFM. Nếu cần dùng chung thư viện đã nạp qua JNI, cân nhắc `SymbolLookup.loaderLookup()`.
6. **Kiểm tra theo từng target:** chạy test với đúng binary, runtime native và kiến trúc đích; kiểm tra cả trường hợp thiếu thư viện hoặc thiếu symbol.
7. **Theo dõi và loại bỏ wrapper thừa:** chỉ xóa JNI wrapper sau khi mọi caller đã chuyển, kiểm thử đạt và không còn consumer phụ thuộc.

Một thay đổi nhỏ có thể bắt đầu bằng một hàm tính toán không trạng thái. Sau đó mới chuyển các API nhận struct, chuỗi, buffer hoặc callback. Với API phức tạp, hãy tách thành các bước nhỏ để dễ kiểm tra layout và quyền sở hữu bộ nhớ.

## 7. Native access trong các JDK hiện hành

FFM có các restricted methods vì thao tác nạp thư viện, tạo liên kết hàm và làm việc với con trỏ native có thể ảnh hưởng đến tính toàn vẹn của JVM. Trên JDK 22, runtime cảnh báo khi mã gọi restricted methods mà chưa bật native access; cấu hình `--enable-native-access` cho module cần dùng các phương thức này để chạy mà không có cảnh báo.

Từ JDK 24, các thao tác JNI như khai báo `native` method hoặc gọi `System.loadLibrary`, `System.load`, `Runtime.loadLibrary` và `Runtime.load` cũng chịu native access restrictions. Do đó, khi ứng dụng nâng cấp JDK, hãy kiểm tra cả JNI hiện có lẫn phần FFM mới.

Với ứng dụng dùng named module, có thể bật native access có chọn lọc:

```bash
java --enable-native-access=com.example.nativebridge \
     --illegal-native-access=deny \
     -m com.example.app/com.example.app.Main
```

Với ứng dụng chạy trên class path:

```bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp app.jar com.example.Main
```

`--enable-native-access` cấp quyền cho module được chỉ định thực hiện native access. `ALL-UNNAMED` áp dụng cho mã trên class path; nếu có thể, nên chuyển phần native bridge sang named module để giới hạn quyền hẹp hơn. `--illegal-native-access=deny` trên các JDK hỗ trợ tùy chọn này giúp phát hiện thao tác native access chưa được bật quyền trong quá trình kiểm thử. Không nên xem chế độ `warn` là xác nhận rằng cấu hình đã sẵn sàng cho các JDK tương lai.

Khi đóng gói, bảo đảm tùy chọn bật native access được truyền đến tiến trình Java thực tế, ví dụ qua cấu hình launcher, manifest executable JAR hoặc tùy chọn của runtime image. Đừng chỉ thêm tùy chọn vào lệnh chạy trong môi trường phát triển rồi quên cấu hình bản cài đặt.

## 8. Checklist trước khi phát hành

- [ ] Mỗi native library có binary đúng OS, CPU architecture và ABI được hỗ trợ.
- [ ] Symbol được export và chữ ký C khớp với `FunctionDescriptor` hoặc khai báo JNI.
- [ ] Kích thước, alignment, struct layout, byte order và quy tắc chuỗi đã được xác minh.
- [ ] Các dependency native và runtime C/C++ cần thiết đã có trong gói hoặc được khai báo rõ.
- [ ] Vị trí nạp thư viện là xác định, có quyền truy cập phù hợp và không cho phép thay thế binary trái phép.
- [ ] Vòng đời của `Arena`, `MemorySegment`, symbol và callback không bị vượt quá phạm vi hợp lệ.
- [ ] Các module cần native access đã được bật quyền; đã thử chế độ `--illegal-native-access=deny` trên JDK hỗ trợ.
- [ ] Đã chạy test trên máy hoặc image sạch cho từng target phát hành.
- [ ] Các đường JNI còn lại đã được ghi nhận lý do tiếp tục sử dụng và kế hoạch bảo trì.

## Kết luận

Tính di động của tích hợp native phụ thuộc vào ABI và binary được phân phối, không chỉ phụ thuộc vào Java bytecode. Hãy thiết kế giao diện C ổn định, build và đóng gói thư viện theo từng target, xác minh dependency cùng symbol, rồi lựa chọn FFM cho những hàm có ABI phù hợp. Giữ JNI ở các phần cần truy cập trực tiếp vào JVM hoặc đang phụ thuộc vào quy ước JNI. Việc chuyển đổi theo từng điểm tích hợp giúp tận dụng FFM mà vẫn kiểm soát được tương thích và rủi ro khi phát hành.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
- [Java SE 27 — java.lang.foreign](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java SE 27 — SymbolLookup](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 27 — JNI Introduction](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/intro.html)
- [Java SE 27 — JNI Design Overview](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/design.html)
- [Java SE 27 — JNI Invocation API](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/invocation.html)
- [Java SE 27 — Restricted Methods](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)
- [Java SE 26 — jpackage Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
