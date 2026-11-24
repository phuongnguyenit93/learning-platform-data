# Quản lý đường dẫn, cách nạp và phân phối thư viện native

## 1. Vì sao ứng dụng Spring Boot Native Image cần quản lý thư viện native?

Một ứng dụng Java có thể gọi mã C/C++ thông qua **Java Native Interface (JNI)**. Các thư viện native thường được phân phối dưới dạng thư viện chia sẻ của hệ điều hành: `.so` trên Linux, `.dylib` trên macOS hoặc `.dll` trên Windows. Ví dụ, một ứng dụng Spring Boot có thể dùng thư viện mã hóa, xử lý ảnh, nén dữ liệu, driver thiết bị hoặc SDK của nhà cung cấp.

Khi chạy trên JVM, thư viện thường được nạp bằng `System.loadLibrary()` hoặc `System.load()`. Khi biên dịch thành **GraalVM Native Image**, ứng dụng vẫn có thể dùng JNI, nhưng cần quan tâm đồng thời đến ba lớp:

1. **Java/JNI loader:** tìm thư viện mà code Java yêu cầu nạp.
2. **OS dynamic loader:** tìm các thư viện phụ thuộc mà thư viện native vừa nạp cần dùng.
3. **Phân phối sản phẩm:** bảo đảm executable, thư viện JNI và các dependency native có mặt trong môi trường triển khai với đúng hệ điều hành, kiến trúc và ABI.

Một lỗi phổ biến là đã đặt đúng file `libcodec.so` nhưng ứng dụng vẫn báo `UnsatisfiedLinkError`. Nguyên nhân có thể là Java không tìm thấy file, hoặc Java đã tìm thấy file nhưng OS loader không tìm được một thư viện phụ thuộc của nó. Hai lỗi này cần cách kiểm tra khác nhau.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài học này giúp bạn tổ chức thư viện native để bản executable chạy ổn định trên máy phát triển, CI và container. Nội dung tập trung vào **đường dẫn, cách nạp và phân phối thư viện native**; reachability metadata cho JNI được trình bày ở mức cần thiết để phân biệt metadata với file thư viện.

Sau bài học, người học có thể:

- Phân biệt `System.loadLibrary` và `System.load`.
- Xác định cách GraalVM Native Image tìm thư viện JNI.
- Phân biệt Java library path với đường tìm dependency của OS loader.
- Đăng ký JNI metadata cho các Java type/member mà mã C/C++ truy cập.
- Đóng gói thư viện native và dependency cùng native executable.
- Chẩn đoán lỗi thiếu thư viện, sai kiến trúc, sai ABI hoặc thiếu symbol.

## 2. Phân biệt các hướng tích hợp native

Trước khi cấu hình đường dẫn, cần xác định **ai gọi ai**. Có hai hướng thường gặp:

| Hướng tích hợp | Luồng gọi | Cơ chế tiêu biểu |
|---|---|---|
| Java gọi mã native | Java/Spring Boot → hàm C/C++ | Java khai báo method `native`; thư viện JNI triển khai method đó |
| Mã native gọi ngược Java | C/C++ → Java class/method/field | Native code dùng JNI như `FindClass`, `GetMethodID`, `Call<Type>Method` |

Với hướng thứ nhất, Java cần nạp thư viện chứa implementation của các native method. Native Image tạo wrapper cho method được khai báo bằng từ khóa `native`; khi method được gọi, wrapper tìm symbol JNI trong các thư viện đã nạp. Thư viện phải được phân phối và nạp đúng cách.

Với hướng thứ hai, Native Image không thể tự suy ra mọi class, method hoặc field mà mã C/C++ sẽ tìm bằng tên lúc chạy. Những phần tử đó cần được khai báo bằng **JNI reachability metadata** ở thời điểm build. Đây là metadata mô tả khả năng truy cập Java từ JNI; nó không phải file `.so`/`.dll` và cũng không thay thế việc đóng gói thư viện native.

Một khái niệm khác dễ nhầm là **build Native Image thành shared library**. Tùy chọn `native-image --shared` tạo thư viện native từ chương trình Java để một ứng dụng C/C++ gọi vào Java thông qua Native Image C API hoặc JNI Invocation API. Đó là chiều tích hợp ngược với tình huống Spring Boot executable nạp một thư viện JNI bên ngoài. Bài này chủ yếu xử lý tình huống **Spring Boot Native Image gọi thư viện native có sẵn**.

## 3. Chọn đúng API nạp thư viện: loadLibrary hay load?

Java cung cấp hai API chính:

| API | Đối số | Quy tắc |
|---|---|---|
| `System.loadLibrary("codec_jni")` | Tên logic, không có prefix, extension hoặc đường dẫn | Java ánh xạ tên sang quy ước của nền tảng và tìm trong các library paths |
| `System.load("/opt/app/lib/libcodec_jni.so")` | Đường dẫn tuyệt đối tới file thư viện | Yêu cầu đường dẫn tuyệt đối; phù hợp khi ứng dụng quản lý một vị trí cụ thể |

Tên logic `codec_jni` có thể được ánh xạ thành:

| Nền tảng | Tên file thường gặp | Lệnh Java |
|---|---|---|
| Linux | `libcodec_jni.so` | `System.loadLibrary("codec_jni")` |
| macOS | `libcodec_jni.dylib` | `System.loadLibrary("codec_jni")` |
| Windows | `codec_jni.dll` | `System.loadLibrary("codec_jni")` |

Có thể xem tên file mà JDK ánh xạ:

```java
String logicalName = "codec_jni";
String platformName = System.mapLibraryName(logicalName);
System.out.println(platformName);
```

Kết quả phụ thuộc hệ điều hành và JDK đang chạy. Không tự ghép prefix hoặc extension vào đối số của `System.loadLibrary`.

### Ví dụ khai báo JNI method

Giả sử thư viện C/C++ cung cấp hàm nén dữ liệu:

```java
package com.example.codec;

public final class NativeCodec {

    static {
        System.loadLibrary("codec_jni");
    }

    private NativeCodec() {
    }

    public static native byte[] compress(byte[] input);
}
```

Khối static initializer nạp thư viện trước lần gọi native method đầu tiên. Method `compress` được khai báo `native` nên phần implementation nằm trong thư viện native, không nằm trong bytecode Java.

Với JNI name mangling theo tên class/package/method, một hàm C tương ứng có dạng khái quát:

```c
#include <jni.h>
#include "com_example_codec_NativeCodec.h"

JNIEXPORT jbyteArray JNICALL
Java_com_example_codec_NativeCodec_compress(
    JNIEnv *env,
    jclass type,
    jbyteArray input
) {
    /* Lấy dữ liệu input, gọi thư viện nén và tạo jbyteArray trả về. */
    return input; /* Chỉ là placeholder minh họa chữ ký JNI. */
}
```

Trong dự án thật, nên dùng header do `javac -h` sinh ra để tránh sai tên symbol và chữ ký JNI. Nếu thư viện dùng `RegisterNatives`, việc ánh xạ method với địa chỉ hàm được thực hiện tường minh khi khởi tạo; khi đó không nhất thiết dùng tên symbol JNI mangling.

### Khi nào dùng đường dẫn tuyệt đối?

Nếu vị trí file do môi trường triển khai cung cấp, có thể dùng `System.load`:

```java
String libraryDirectory = System.getenv("APP_NATIVE_LIB_DIR");
if (libraryDirectory == null || libraryDirectory.isBlank()) {
    throw new IllegalStateException("APP_NATIVE_LIB_DIR is not configured");
}

String libraryFile = Path.of(
    libraryDirectory,
    System.mapLibraryName("codec_jni")
).toAbsolutePath().normalize().toString();

System.load(libraryFile);
```

Ví dụ cần import `java.nio.file.Path`. Biến `APP_NATIVE_LIB_DIR` phải trỏ tới thư mục đáng tin cậy, có quyền đọc phù hợp và chứa file thư viện đúng nền tảng. `System.load` yêu cầu một đường dẫn tuyệt đối; đường dẫn tương đối hoặc phụ thuộc thư mục làm việc hiện tại dễ khiến ứng dụng hoạt động khác nhau giữa local và container.

### Lưu ý với JDK mới

Trên các JDK mới, `System.load` và `System.loadLibrary` được xếp vào nhóm restricted methods vì chúng cho phép mã Java nạp và thực thi mã native bên ngoài runtime. Khi kiểm thử bằng JVM, hãy xem cảnh báo native access và cấu hình quyền native access cho module gọi API theo chính sách của JDK đang dùng. Với ứng dụng trên classpath, JDK có thể dùng `--enable-native-access=ALL-UNNAMED`; ứng dụng modular nên chỉ định module cần quyền. Không nên tắt kiểm tra toàn cục như một cách xử lý lâu dài.

## 4. Native Image tìm thư viện ở đâu?

Theo tài liệu JNI của GraalVM, khi ứng dụng Native Image gọi `System.loadLibrary()` hoặc API liên quan, Native Image tìm **thư mục chứa native executable trước**, rồi mới tìm trong Java library path. Vì vậy, nếu thư viện JNI nằm cùng thư mục với executable, thường không cần cấu hình thêm đường dẫn Java.

Ví dụ layout đơn giản:

```text
/opt/service/
├── service
└── libcodec_jni.so
```

Trong ví dụ Linux, `service` là native executable và `libcodec_jni.so` là thư viện JNI. Khi code gọi `System.loadLibrary("codec_jni")`, Native Image có thể tìm thư viện ngay trong thư mục chứa executable.

Nếu tổ chức thư viện ở thư mục riêng:

```text
/opt/service/
├── bin/
│   └── service
└── lib/
    └── libcodec_jni.so
```

cần cấu hình Java library path lúc khởi động hoặc dùng `System.load` với đường dẫn tuyệt đối. Ví dụ với `System.loadLibrary`, có thể truyền thuộc tính khi chạy native executable nếu phiên bản Native Image hỗ trợ:

```bash
./bin/service -Djava.library.path=/opt/service/lib
```

Hãy xác nhận option runtime và giá trị property trong đúng GraalVM release của dự án. Không nên gọi `System.setProperty("java.library.path", ...)` sau khi ứng dụng đã khởi tạo class loading rồi kỳ vọng loader sẽ cập nhật mọi cache tìm thư viện.

**Điểm quan trọng:** Java library path chỉ giúp tìm thư viện JNI mà Java yêu cầu nạp. Nó không tự giải quyết tất cả dependency của thư viện đó. Ví dụ `libcodec_jni.so` có thể phụ thuộc `libvendorcodec.so`; sau khi tìm thấy file đầu tiên, dynamic loader của Linux vẫn phải tìm được file thứ hai theo quy tắc riêng của OS.
## 5. Phân biệt JNI library loading với JNI reachability metadata

Hai cấu hình thường bị nhầm lẫn:

- **Đường dẫn/thư viện native:** cho biết file `.so`, `.dylib` hoặc `.dll` nằm ở đâu và OS loader tìm các dependency của nó thế nào.
- **JNI reachability metadata:** cho biết mã native được phép tra cứu, tạo hoặc gọi những Java type/member nào khi ứng dụng Native Image chạy.

Có file thư viện đúng chỗ chưa đủ nếu mã C/C++ gọi ngược vào Java nhưng thiếu metadata. Ngược lại, metadata đầy đủ không thể bù cho một file `libcodec_jni.so` không được đóng gói hoặc không thể nạp.

### 5.1. Khi Java gọi native method

Ví dụ `NativeCodec.compress(byte[])` được khai báo bằng từ khóa `native`. Native Image nhận diện khai báo này và tạo wrapper để chuyển từ Java sang native code. Khi method được gọi, wrapper tìm symbol tương ứng trong các thư viện đã nạp. Bạn cần:

- Thư viện JNI được biên dịch cho đúng OS/architecture/ABI.
- Thư viện được nạp trước khi native method được gọi.
- Symbol JNI đúng tên và chữ ký, hoặc code khởi tạo dùng `RegisterNatives`.
- Các thư viện phụ thuộc của thư viện JNI cũng có thể được OS loader tìm thấy.

Nếu C/C++ chỉ thực hiện phép tính trên dữ liệu được truyền vào và trả kết quả về Java, có thể không cần JNI metadata cho callback Java. Nhưng nếu thư viện C/C++ gọi `FindClass`, `GetMethodID`, `GetFieldID` hoặc các hàm `Call<Type>Method` để truy cập Java, hãy tiếp tục bước dưới đây.

### 5.2. Khi native code truy cập Java

Giả sử thư viện C/C++ nhận callback và gọi method `onComplete(String)` trên một đối tượng Java:

```c
jclass callbackType = (*env)->FindClass(
    env,
    "com/example/codec/NativeCallback"
);

jmethodID onComplete = (*env)->GetMethodID(
    env,
    callbackType,
    "onComplete",
    "(Ljava/lang/String;)V"
);

/* Sau khi có callback object hợp lệ: */
(*env)->CallVoidMethod(env, callbackObject, onComplete, message);
```

Native Image không thể dự đoán mọi tên class/member mà native code sẽ tra cứu. Vì vậy, cung cấp JNI metadata cho đúng type và member. Với reachability metadata hiện hành, có thể đặt file `reachability-metadata.json` dưới `META-INF/native-image/<groupId>/<artifactId>/` trong classpath:

```json
{
  "jni": [
    {
      "type": "com.example.codec.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": [
            "java.lang.String"
          ]
        }
      ]
    }
  ]
}
```

Entry trên cho phép JNI truy cập type và method được nêu. Nếu C/C++ còn dùng `GetFieldID` để đọc hoặc ghi field, hãy thêm đúng tên field vào `fields`. Nếu native code tạo object qua `NewObject`, đăng ký constructor tương ứng. Không bật `allDeclaredMethods` hoặc `allDeclaredFields` chỉ để sửa một lời gọi đơn lẻ.

### 5.3. Đóng góp JNI hints bằng Spring RuntimeHints

Spring Framework cung cấp `RuntimeHints.jni()` để đăng ký các Java type/member được truy cập qua JNI. Có thể viết registrar và gắn với bean sử dụng native library:

```java
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

public class NativeCallbackRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
            NativeCallback.class,
            typeHint -> typeHint.withMethod(
                "onComplete",
                List.of(TypeReference.of(String.class)),
                ExecutableMode.INVOKE
            )
        );
    }
}

@Component
@ImportRuntimeHints(NativeCallbackRuntimeHints.class)
class NativeCodecService {
    // Gọi NativeCodec và nhận callback từ thư viện native.
}
```

Class Java được JNI truy cập có thể được khai báo như sau:

```java
package com.example.codec;

public class NativeCallback {
    public void onComplete(String message) {
        // Xử lý kết quả trả về từ thư viện native.
    }
}
```

Ví dụ minh họa một method callback. Nếu native code cần thêm constructor hoặc field, hãy bổ sung đúng thành phần đó bằng API tương ứng của Spring Framework đang dùng. Sau AOT processing, kiểm tra metadata được sinh ra để xác nhận JNI entry đã có trong output.

**Phân biệt với serialization:** nếu ứng dụng dùng `ObjectInputStream`/`ObjectOutputStream` để serialize Java object, hãy dùng serialization metadata tương ứng (ví dụ `RuntimeHints.serialization()` hoặc trường `serializable` trong reachability metadata). Không đăng ký JNI chỉ vì ứng dụng có serialization; đây là hai cơ chế độc lập.

## 6. Đường tìm thư viện phụ thuộc theo hệ điều hành

Sau khi Java loader tìm thấy thư viện JNI chính, hệ điều hành phải nạp được mọi dependency mà thư viện đó tham chiếu. Ví dụ:

```text
Native Image executable
    |
    | System.loadLibrary("codec_jni")
    v
libcodec_jni.so
    |
    | DT_NEEDED: libvendorcodec.so
    v
libvendorcodec.so
    |
    | dependency tiếp theo
    v
các thư viện hệ thống
```

`java.library.path` không thay thế cơ chế tìm dependency của OS loader. Hãy cấu hình cả hai lớp nếu thư viện JNI có dependency riêng.

### 6.1. Linux

Trên Linux, thư viện chia sẻ thường có tên `lib<name>.so`. Dynamic linker (thường là `ld-linux`) tìm các shared objects được khai báo trong ELF. Với dependency không chứa slash trong tên, thứ tự tìm phổ biến gồm:

1. `DT_RPATH` nếu có và không có `DT_RUNPATH`.
2. `LD_LIBRARY_PATH` (trừ một số chế độ thực thi an toàn).
3. `DT_RUNPATH` của đối tượng đang cần dependency trực tiếp.
4. Cache `/etc/ld.so.cache`.
5. Các thư mục mặc định như `/lib` và `/usr/lib` (tùy kiến trúc).

Một cách đóng gói có thể di chuyển giữa các thư mục là dùng `$ORIGIN` trong `RUNPATH`. Token này được dynamic linker thay bằng thư mục chứa executable hoặc shared object tương ứng. Ví dụ khi liên kết `libcodec_jni.so` và các dependency cùng nằm trong thư mục `lib`:

```bash
gcc -shared -fPIC \
  -Wl,-rpath,'$ORIGIN' \
  -o libcodec_jni.so codec_jni.c
```

`$ORIGIN` được cố ý đặt trong dấu nháy đơn để shell không mở rộng nó trước linker. Nếu `libcodec_jni.so` phụ thuộc thư viện ở thư mục anh em, chẳng hạn `../vendor`, có thể cấu hình `$ORIGIN/../vendor` theo layout đã chọn.

Có thể dùng `LD_LIBRARY_PATH` cho thử nghiệm hoặc một môi trường được kiểm soát:

```bash
LD_LIBRARY_PATH=/opt/service/lib:/opt/service/vendor \
  ./service -Djava.library.path=/opt/service/lib
```

Không nên dựa vào việc người vận hành phải tự thiết lập biến này bằng tay trong mọi môi trường. Với sản phẩm phân phối, ưu tiên RPATH/RUNPATH phù hợp hoặc cấu hình hệ thống có quản lý.

Lệnh chẩn đoán:

```bash
# Xem các dependency và RPATH/RUNPATH được ghi trong ELF.
readelf -d /opt/service/lib/libcodec_jni.so

# Xem dependency mà loader có thể phân giải trên máy hiện tại.
ldd /opt/service/lib/libcodec_jni.so

# Theo dõi quá trình tìm thư viện khi chạy.
LD_DEBUG=libs ./service
```

Chỉ chạy `ldd` trên binary đáng tin cậy; khi cần kiểm tra file không đáng tin, ưu tiên công cụ đọc ELF tĩnh như `readelf`.

### 6.2. macOS

Trên macOS, thư viện động thường có đuôi `.dylib`. Dynamic loader là `dyld`. Các install name có thể dùng token:

- `@executable_path`: thư mục chứa executable chính.
- `@loader_path`: thư mục chứa image (executable hoặc dylib) đang tham chiếu dependency.
- `@rpath`: một đường dẫn được phân giải thông qua các run-path search paths đã khai báo.

Khi đóng gói ứng dụng có cấu trúc bundle, nên cấu hình install name và runpath tương đối, ví dụ `@rpath/libcodec_jni.dylib` cùng một `LC_RPATH` phù hợp. Tránh hardcode đường dẫn tuyệt đối tới thư mục build trên máy phát triển.

Kiểm tra dependency và runpath:

```bash
file ./service
otool -L ./libcodec_jni.dylib
otool -l ./libcodec_jni.dylib
```

`otool -L` liệt kê các install name mà thư viện tham chiếu; `otool -l` cho phép xem các load commands, bao gồm thông tin runpath. Nếu cần sửa install name của binary hiện có, công cụ `install_name_tool` có thể hỗ trợ, nhưng nên sửa cấu hình linker ở build pipeline để lần build sau tái tạo đúng kết quả.

### 6.3. Windows

Trên Windows, thư viện động thường có đuôi `.dll`. Cần phân biệt:

- Java loader phải tìm được DLL mà `System.loadLibrary` yêu cầu.
- Windows loader phải tìm được các DLL phụ thuộc của DLL đó.

Windows có quy tắc DLL search order riêng, chịu ảnh hưởng của application directory, system directories, các thư mục được thêm rõ ràng và `PATH` theo kiểu nạp/flags đang dùng. Cách phân phối dễ kiểm soát là đặt DLL JNI và các dependency riêng của nó trong thư mục ứng dụng được bảo vệ quyền ghi.

Ví dụ layout:

```text
C:\apps\service\
├── service.exe
├── codec_jni.dll
└── vendorcodec.dll
```

Có thể kiểm tra dependency bằng công cụ Visual Studio:

```powershell
dumpbin /DEPENDENTS C:\apps\service\codec_jni.dll
```

Hoặc dùng công cụ phân tích PE/DLL phù hợp trong môi trường build. Tránh đặt thư viện cùng tên vào thư mục làm việc hiện tại có thể bị người dùng khác ghi vào, vì việc nạp nhầm DLL có thể dẫn đến thực thi mã ngoài ý muốn. Khi cần nạp từ thư mục tùy chỉnh, ưu tiên API Windows thiết lập search directories an toàn trong phần native loader, hoặc đặt thư viện tại application directory theo chính sách triển khai.
## 7. Đóng gói thư viện cùng native executable

Native Image không tự động biến mọi file thư viện native bên ngoài thành một phần của executable. Nếu ứng dụng gọi `System.loadLibrary("codec_jni")`, hãy bảo đảm thư viện JNI và dependency của nó được phân phối trong gói cài đặt hoặc container runtime.

### 7.1. Layout đơn giản: đặt JNI library cạnh executable

Đây là cách ít cấu hình nhất với GraalVM Native Image:

```text
/opt/service/
├── service
├── libcodec_jni.so
└── libvendorcodec.so
```

`service` là native executable; `libcodec_jni.so` là thư viện mà Java nạp; `libvendorcodec.so` là dependency của thư viện JNI. Native Image tìm thư viện JNI trong thư mục chứa executable trước Java library path. Để OS loader tìm được `libvendorcodec.so`, hãy cấu hình RUNPATH phù hợp cho `libcodec_jni.so` (ví dụ `$ORIGIN` nếu dependency nằm cùng thư mục).

Layout trên có thể thay đổi theo nền tảng:

- Linux: `service`, `libcodec_jni.so` và dependency `.so`.
- macOS: `service`, `libcodec_jni.dylib` và dependency `.dylib`.
- Windows: `service.exe`, `codec_jni.dll` và dependency `.dll`.

Không dùng chung một binary native cho tất cả nền tảng. Mỗi OS/architecture cần artifact phù hợp.

### 7.2. Layout tách bin và lib

Nếu muốn tách executable khỏi thư viện:

```text
/opt/service/
├── bin/
│   └── service
└── lib/
    ├── libcodec_jni.so
    └── libvendorcodec.so
```

Có thể chạy với Java library path và OS loader path riêng:

```bash
LD_LIBRARY_PATH=/opt/service/lib \
  /opt/service/bin/service \
  -Djava.library.path=/opt/service/lib
```

Trong ví dụ này:

- `-Djava.library.path` giúp Native Image tìm thư viện JNI mà code Java yêu cầu nạp bằng `System.loadLibrary`.
- `LD_LIBRARY_PATH` giúp Linux dynamic linker tìm dependency của thư viện JNI.
- Hai biến có vai trò khác nhau; đặt một biến không thay thế biến còn lại.

Đối với môi trường production, ưu tiên cấu hình RUNPATH tương đối và đường dẫn do ứng dụng quản lý. `LD_LIBRARY_PATH` hữu ích để thử nghiệm hoặc trong môi trường triển khai được kiểm soát, nhưng việc phụ thuộc vào biến này cần được ghi rõ trong manifest/run script.

### 7.3. Nếu thư viện native được đóng gói bên trong JAR

Một số thư viện Java đóng gói binary theo classifier hoặc resource, ví dụ:

```text
META-INF/native/linux-x86_64/libcodec_jni.so
META-INF/native/linux-aarch64/libcodec_jni.so
META-INF/native/windows-x86_64/codec_jni.dll
```

OS loader không thể nạp trực tiếp một resource nằm bên trong JAR hoặc resource đã được nhúng vào Native Image. Nếu thư viện được phân phối theo cách này, ứng dụng cần:

1. Chọn đúng resource theo OS/architecture.
2. Đọc resource bằng `getResourceAsStream`.
3. Ghi nội dung ra một file tạm hoặc thư mục ứng dụng có quyền ghi an toàn.
4. Gọi `System.load` với đường dẫn tuyệt đối của file đã giải nén.
5. Bảo đảm dependency bậc hai của thư viện cũng được tìm thấy.

Ví dụ rút gọn:

```java
Path extractedLibrary = Files.createTempFile(
    "codec-jni-",
    System.mapLibraryName("codec_jni")
);

try (InputStream input = NativeCodec.class.getResourceAsStream(
        "/META-INF/native/linux-x86_64/libcodec_jni.so")) {
    if (input == null) {
        throw new IllegalStateException("Native library resource is missing");
    }
    Files.copy(input, extractedLibrary, StandardCopyOption.REPLACE_EXISTING);
}

extractedLibrary.toFile().deleteOnExit();
System.load(extractedLibrary.toAbsolutePath().toString());
```

Đây chỉ là minh họa cho một nền tảng Linux x86_64. Ứng dụng thật phải chọn resource theo platform đã kiểm tra, xử lý quyền file và vòng đời file tạm, đồng thời giải nén dependency cần thiết. Với native executable chạy trong container, **đặt thư viện cạnh executable hoặc ở một thư mục runtime đã cấu hình** thường dễ vận hành và chẩn đoán hơn việc giải nén động.

Không dùng `URL.getFile()` để lấy đường dẫn file từ resource nhúng trong Native Image. Resource embedded có thể dùng URL scheme `resource:` thay vì `file:`; hãy đọc qua stream.

## 8. Đóng gói trong Docker/container

Container runtime phải chứa native executable, JNI library và tất cả dependency native cần thiết. Một Dockerfile tối giản trên Linux có thể như sau, giả sử tất cả file được đặt cạnh nhau và RUNPATH của thư viện JNI đã được cấu hình:

```dockerfile
FROM debian:bookworm-slim

WORKDIR /opt/service

COPY service ./service
COPY libcodec_jni.so ./libcodec_jni.so
COPY libvendorcodec.so ./libvendorcodec.so

RUN chmod 0555 ./service \
    && chmod 0444 ./*.so

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["./service"]
```

Dockerfile trên chỉ minh họa layout. Hãy chọn base image tương thích với binary đã build:

- Native executable và thư viện JNI phải khớp Linux architecture, ví dụ `amd64` hoặc `arm64`.
- Nếu binary phụ thuộc glibc, run image phải có glibc tương thích; image dựa trên musl không thể thay thế tùy ý.
- Nếu thư viện JNI dùng C++ runtime hoặc thư viện hệ thống khác, run image phải cung cấp đúng runtime dependencies.
- Chỉ copy các thư viện runtime cần thiết vào final image; không đưa compiler, header hoặc build tools vào production nếu không cần.
- Chạy bằng user không có quyền ghi vào thư mục chứa thư viện đã cài, tránh bị thay thế thư viện lúc runtime.

### Với Cloud Native Buildpacks

Spring Boot có thể tạo container image qua Maven `spring-boot:build-image` hoặc Gradle `bootBuildImage`. Tuy nhiên, việc có native executable trong image **không tự bảo đảm** các file `.so` bên ngoài cũng được đưa vào run image.

Nếu ứng dụng phụ thuộc thư viện native riêng, hãy xác định rõ cơ chế đưa chúng vào final image:

- Dùng buildpack bổ sung hoặc custom buildpack để copy thư viện vào layer runtime.
- Dùng builder/run image đã được tổ chức cung cấp thư viện cần thiết, nếu chính sách phân phối cho phép.
- Hoặc dùng Dockerfile/multi-stage build để kiểm soát chính xác các file được copy.

Sau khi build image, phải kiểm tra filesystem của final image và chạy smoke test trong chính container đó. Không chỉ kiểm tra file trong builder container vì builder có thể chứa thư viện mà run image không có.

### Phân biệt artifact build và runtime package

| Thành phần | Có trong gói runtime? | Mục đích |
|---|---|---|
| Native executable | Có | Khởi chạy ứng dụng |
| JNI library (`.so`, `.dylib`, `.dll`) | Có nếu ứng dụng gọi nó | Triển khai các native method |
| Dependency native bậc hai | Có nếu loader cần | Cung cấp symbol mà JNI library tham chiếu |
| `reachability-metadata.json` | Thường chỉ là đầu vào build, không phải thư viện runtime | Đăng ký truy cập động khi tạo Native Image |
| GraalVM compiler, C compiler, linker | Không cần trong runtime thông thường | Dùng trong giai đoạn build |
| JDK/JRE đầy đủ | Native executable thông thường không cần JVM riêng | Chỉ cần cho quy trình JVM hoặc công cụ khác |

## 9. Biên dịch và kiểm tra một JNI library trên Linux

Giả sử mã Java khai báo `NativeCodec.compress(byte[])` và mã C triển khai method đó. Một quy trình phát triển rút gọn:

```bash
mkdir -p build/classes build/include build/native

# Biên dịch Java và sinh JNI header.
javac -h build/include \
  -d build/classes \
  src/main/java/com/example/codec/NativeCodec.java

# Biên dịch JNI implementation thành shared library.
cc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -Wl,-rpath,'$ORIGIN' \
  -o build/native/libcodec_jni.so \
  src/main/c/codec_jni.c
```

Các điểm cần chú ý:

- `javac -h` sinh header có khai báo JNI phù hợp với method signature.
- `-fPIC -shared` tạo thư viện chia sẻ trên Linux.
- `JAVA_HOME/include` và thư mục platform-specific chứa `jni.h`, `jni_md.h`.
- `-Wl,-rpath,'$ORIGIN'` đặt RUNPATH tương đối để thư viện có thể tìm dependency nằm cạnh chính nó; chỉ dùng nếu phù hợp với dependency layout.
- Compiler, headers và ABI phải phù hợp với target OS/architecture.

Kiểm tra file vừa tạo:

```bash
file build/native/libcodec_jni.so
readelf -h build/native/libcodec_jni.so
readelf -d build/native/libcodec_jni.so
nm -D build/native/libcodec_jni.so
```

`file` và `readelf -h` giúp kiểm tra định dạng ELF/architecture; `readelf -d` xem dependency, RPATH/RUNPATH; `nm -D` xem các symbol được export. Hãy kiểm tra symbol JNI có tên đúng theo header sinh từ `javac -h` hoặc thư viện đã đăng ký method bằng `RegisterNatives`.

Sau đó đặt `libcodec_jni.so` vào thư mục runtime được chọn, build Spring Boot Native Image và chạy test trên executable. Lệnh build cụ thể phụ thuộc Maven/Gradle plugin; điều cần xác nhận là native executable được tạo với cùng classpath/AOT metadata và file JNI được cung cấp ở runtime.

## 10. Kiểm thử và chẩn đoán theo từng lớp

Đừng bắt đầu bằng cách thêm hàng loạt thư mục vào PATH hoặc đổi base image. Hãy xác định loader nào đang báo lỗi.

| Triệu chứng | Lớp có khả năng lỗi | Hướng kiểm tra |
|---|---|---|
| `no codec_jni in java.library.path` hoặc không tìm được library name | Java/JNI loader | Kiểm tra tên logic, `java.library.path` và thư mục chứa executable |
| `cannot open shared object file: libvendorcodec.so` | Linux dynamic loader | Kiểm tra `DT_NEEDED`, RUNPATH, `LD_LIBRARY_PATH` và thư viện đã có trong image chưa |
| `UnsatisfiedLinkError: no ... in java.library.path` | Java không tìm được thư viện hoặc không thể nạp nó | Kiểm tra cả đường dẫn file và lỗi loader lồng bên trong |
| `undefined symbol` | Linker/symbol resolution | Kiểm tra ABI, phiên bản thư viện, symbol export và dependency |
| `wrong ELF class` hoặc sai architecture | File native không khớp target | Kiểm tra `file`, `readelf -h`, kiến trúc máy và container |
| `GLIBC_x.y not found` | ABI/runtime libc không tương thích | Build với target phù hợp hoặc dùng run image có glibc tương thích |
| `The specified module could not be found` trên Windows | Có thể thiếu DLL chính hoặc một dependency DLL | Kiểm tra toàn bộ DLL dependency, không chỉ file JNI chính |
| `MissingJNIRegistrationError` | Native code truy cập Java member thiếu JNI metadata | Kiểm tra `FindClass`, `GetMethodID`, `GetFieldID` và reachability metadata |
| `UnsatisfiedLinkError: '...native method...'` | Symbol native method không được tìm thấy | Kiểm tra JNI name mangling, chữ ký, `RegisterNatives` và thư viện đã load |
| Chạy local được nhưng container lỗi | Runtime image thiếu file hoặc khác ABI/architecture | Kiểm tra final image, không chỉ builder image |

### Bộ lệnh kiểm tra nhanh

Trên Linux:

```bash
# Kiểm tra architecture và dynamic dependencies.
file ./service ./libcodec_jni.so
readelf -d ./libcodec_jni.so
ldd ./libcodec_jni.so

# Xem loader tìm thư viện như thế nào.
LD_DEBUG=libs ./service
```

Trên macOS:

```bash
file ./service ./libcodec_jni.dylib
otool -L ./libcodec_jni.dylib
otool -l ./libcodec_jni.dylib
```

Trên Windows PowerShell:

```powershell
Get-Item .\service.exe, .\codec_jni.dll
dumpbin /DEPENDENTS .\codec_jni.dll
where.exe codec_jni.dll
```

Lệnh `where.exe` tìm file theo thư mục hiện có trong PATH; nó không thay thế kiểm tra DLL dependency theo Windows loader search order. Khi có thể, dùng công cụ phân tích dependency PE để tìm DLL bậc hai bị thiếu.

## 11. Kiểm thử JNI và metadata trước khi phát hành

Một quy trình kiểm chứng tốt cần đi từ JVM tới Native Image, rồi tới đúng môi trường phân phối.

### Bước 1: kiểm tra JNI trên JVM

Chạy ứng dụng trên JVM cùng OS/architecture với thư viện native. Xác nhận:

- `System.loadLibrary` hoặc `System.load` nạp đúng file.
- Native method được gọi và trả kết quả hợp lệ.
- Các callback từ native code sang Java hoạt động.
- Không có lỗi thiếu dependency hoặc symbol.

JVM test chỉ chứng minh thư viện hoạt động trong môi trường JVM đó. Nó chưa chứng minh native executable có đủ JNI metadata.

### Bước 2: kiểm tra metadata JNI

Nếu thư viện gọi ngược vào Java, kiểm tra `reachability-metadata.json` hoặc hints do Spring AOT sinh ra. Native Image hỗ trợ chế độ exact reachability metadata ở các phiên bản tương ứng:

```text
--exact-reachability-metadata
```

Khi chạy native executable hoặc test, có thể bật chế độ báo thiếu registration:

```text
-XX:MissingRegistrationReportingMode=Warn
```

Chạy tất cả nhánh có JNI callback: success, error, callback bất đồng bộ, đọc/ghi field và tạo object nếu thư viện dùng các thao tác đó. Một test chỉ gọi native method nhưng không kích hoạt callback không chứng minh các Java member callback đã được đăng ký.

### Bước 3: build và chạy native executable

Sau khi metadata đã được xác minh:

1. Chạy Maven/Gradle AOT và native build theo cấu hình dự án.
2. Kiểm tra log build và metadata đầu ra.
3. Đặt JNI library vào đúng vị trí runtime hoặc cấu hình library path.
4. Chạy executable trực tiếp trên OS/architecture đích.
5. Kích hoạt các nhánh JNI và xác nhận kết quả.

Nếu thiếu metadata cho Java member được gọi từ native code, GraalVM có thể báo `MissingJNIRegistrationError`. Nếu không tìm thấy thư viện hoặc symbol, lỗi thường xuất hiện dưới dạng `UnsatisfiedLinkError` hoặc lỗi loader của OS. Hãy đọc thông điệp và stack trace để xác định đúng lớp lỗi.

### Bước 4: kiểm tra trong container cuối

Build image, sau đó chạy chính image đã tạo. Không chỉ kiểm tra native executable trên host. Trong container, kiểm tra:

- File JNI có thực sự tồn tại trong final image không?
- User chạy container có quyền đọc và nạp thư viện không?
- Dependency native bậc hai có mặt không?
- OS, CPU architecture, libc và C/C++ runtime có tương thích không?
- Container có chạy đúng endpoint/tác vụ cần JNI không?

Một thư viện có thể tồn tại trong builder stage nhưng không được copy sang final stage. Chỉ test container cuối mới phát hiện chắc chắn trường hợp này.

## 12. Phân biệt lỗi đường dẫn, metadata và ABI

Khi native app báo lỗi, hãy phân loại trước khi sửa:

| Câu hỏi | Nếu câu trả lời là “không” | Hướng xử lý |
|---|---|---|
| Java loader có tìm thấy file JNI chính? | Không tìm thấy tên hoặc đường dẫn | Kiểm tra `System.loadLibrary`, `System.load` và `java.library.path` |
| OS loader có tìm được dependency của JNI library? | Thiếu `.so`/DLL phụ thuộc | Kiểm tra RUNPATH, `LD_LIBRARY_PATH`, app directory hoặc dependency package |
| Symbol native method có tồn tại? | Không tìm thấy symbol JNI | Kiểm tra JNI header, tên package/class/method, chữ ký hoặc `RegisterNatives` |
| Native code có thể truy cập Java type/member? | Thiếu JNI registration | Bổ sung đúng JNI metadata/hints |
| Binary có đúng nền tảng? | Sai ELF/PE/Mach-O, CPU hoặc ABI | Build lại cho target đúng và chọn run image tương thích |
| File có thể được đọc/nạp? | Permission hoặc policy không phù hợp | Kiểm tra owner, mode, mount flags và quyền của user chạy |

Không dùng `LD_LIBRARY_PATH` để sửa `MissingJNIRegistrationError`. Cũng không thêm JNI metadata để xử lý lỗi `cannot open shared object file`. Mỗi lớp cần đúng loại cấu hình.

## 13. Bảo mật và vận hành thư viện native

Thư viện native chạy với quyền của tiến trình ứng dụng và có thể truy cập bộ nhớ, file, network hoặc thiết bị như mã native thông thường. Quản lý đường dẫn vì vậy cũng là một phần của bảo mật:

- Chỉ nạp thư viện từ thư mục do tổ chức kiểm soát; tránh thư mục tạm hoặc working directory mà người dùng khác có thể ghi.
- Không lấy tên file hoặc đường dẫn native library trực tiếp từ request bên ngoài.
- Pin version và checksum của thư viện trong build pipeline; kiểm tra nguồn cung cấp và license.
- Phân phối cùng các dependency native đã được kiểm kê; tránh phụ thuộc vào một file tình cờ có sẵn trên máy developer.
- Giữ quyền ghi của thư mục thư viện ở mức tối thiểu. Process runtime thường chỉ cần đọc/nạp file.
- Cập nhật thư viện native cùng quy trình vá lỗ hổng của dependency Java.
- Không để nhiều phiên bản cùng tên trong các search paths khó dự đoán; loader có thể nạp nhầm bản.

Nếu ứng dụng cần hỗ trợ nhiều kiến trúc, tạo artifact riêng cho từng target, ví dụ `linux-amd64-glibc` và `linux-arm64-glibc`. Ghi rõ ABI và phiên bản C/C++ runtime mà thư viện yêu cầu. Một file có cùng tên `libcodec_jni.so` nhưng build cho ARM64 không thể thay cho bản x86_64.

## 14. Bài tập thực hành

### Bài tập A — Nạp một JNI library cạnh executable

Tạo class `NativeCodec` có một native method đơn giản. Biên dịch thư viện JNI cho Linux, đặt file `libcodec_jni.so` cạnh native executable và dùng `System.loadLibrary("codec_jni")`.

**Tiêu chí hoàn thành:** JVM và Native Image đều gọi được method, trả kết quả đúng; log và thông tin kiến trúc của thư viện được lưu lại.

### Bài tập B — Tách thư viện sang thư mục lib

Chuyển JNI library sang `/opt/service/lib`. Cấu hình `java.library.path` cho Java loader và RUNPATH/`LD_LIBRARY_PATH` cho dependency loader. Cố ý bỏ một dependency để quan sát lỗi, sau đó khôi phục và ghi rõ thông điệp của từng lớp loader.

**Câu hỏi:** vì sao đặt `LD_LIBRARY_PATH` không nhất thiết làm `System.loadLibrary` tìm được thư viện JNI chính trong Native Image?

### Bài tập C — Callback từ native code vào Java

Viết một callback Java `NativeCallback.onComplete(String)` được gọi bằng JNI. Đăng ký đúng type và method trong `reachability-metadata.json` hoặc Spring `RuntimeHints.jni()`. Build native, kích hoạt callback và kiểm tra kết quả.

**Tiêu chí hoàn thành:** callback hoạt động trên native executable và metadata không bật toàn bộ member của package.

### Bài tập D — Đóng gói container

Tạo final image gồm native executable, JNI library và dependency bậc hai. Kiểm tra architecture, libc, quyền file và đường dẫn nạp. Chạy container trong môi trường tương tự production và gọi endpoint thực hiện tác vụ JNI.

**Tiêu chí hoàn thành:** image chạy được mà không dựa vào file thư viện chỉ có trên host hoặc builder stage.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định hướng gọi: Java gọi native method hay native code gọi ngược Java.
- [ ] Đã chọn `System.loadLibrary` hoặc `System.load` đúng trường hợp.
- [ ] Đã xác minh quy tắc tên file theo OS.
- [ ] JNI library nằm trong thư mục tìm được hoặc đường dẫn tuyệt đối hợp lệ.
- [ ] Java library path và OS dynamic-loader path đã được cấu hình riêng.
- [ ] Các dependency bậc hai đã được phân phối cùng sản phẩm hoặc có trong run image.
- [ ] JNI metadata bao phủ đúng Java type/member được native code truy cập.
- [ ] Đã phân biệt JNI metadata với Java serialization metadata.
- [ ] Native executable, JNI library và container có cùng OS/architecture/ABI.
- [ ] Đã chạy test trên native executable và final container image.
- [ ] Đã kiểm tra symbol, dependency, permission và checksum của thư viện.
- [ ] Đường dẫn thư viện không cho phép người dùng không tin cậy thay thế file được nạp.

## Tài liệu tham khảo

- [GraalVM Native Image — Java Native Interface (JNI)](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): cách nạp shared library, tìm thư viện cạnh executable, JNI wrappers và metadata cho native-to-Java access.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): cấu trúc `reachability-metadata.json`, JNI metadata, tracing agent và missing-registration diagnostics.
- [Oracle Java SE — System](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html): hợp đồng của `System.load`, `System.loadLibrary` và `System.mapLibraryName`.
- [Linux man-pages — ld.so(8)](https://www.man7.org/linux/man-pages/man8/ld.so.8.html): thứ tự tìm shared object, `LD_LIBRARY_PATH`, `RPATH`, `RUNPATH` và `$ORIGIN`.
- [Apple Developer — Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html): install name và runpath của dynamic library trên macOS.
- [Microsoft Learn — Dynamic-link library search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order): cách Windows loader tìm DLL và dependency.

## Kết luận

Quản lý thư viện native trong Spring Boot Native Image cần giải quyết đồng thời **Java library loading**, **OS dynamic linking** và **đóng gói runtime**. `System.loadLibrary` nhận tên logic, `System.load` nhận đường dẫn tuyệt đối; Native Image ưu tiên thư mục chứa executable rồi mới tới Java library path. Sau khi thư viện JNI chính được tìm thấy, OS loader vẫn phải phân giải mọi dependency bậc hai theo quy tắc của Linux, macOS hoặc Windows. Nếu native code gọi ngược vào Java, cần khai báo JNI metadata cho đúng type/member; metadata này không thay thế file thư viện. Khi executable, JNI library, dependency và container được build cho cùng OS/architecture/ABI và đã được kiểm thử trong final image, ứng dụng mới có thể được phân phối và vận hành ổn định.

