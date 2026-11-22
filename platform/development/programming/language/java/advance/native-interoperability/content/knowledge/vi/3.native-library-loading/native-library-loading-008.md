# Giới hạn của việc thay đổi đường dẫn tìm thư viện sau khi JVM khởi động

Khi tích hợp Java với thư viện native qua JNI, một tình huống dễ gây nhầm lẫn là: ứng dụng bắt đầu chạy, tải cấu hình mới trỏ tới thư mục chứa `.so`/`.dll`/`.dylib`, gọi `System.setProperty("java.library.path", newPath)`, đọc lại thấy đúng giá trị mới nhưng `System.loadLibrary("foo")` vẫn báo không tìm được thư viện.

**Nguyên nhân:** `java.library.path` là cấu hình đường tìm thư viện native theo tên; thay đổi *chuỗi system property* sau khi JVM khởi động không đồng nghĩa với thay đổi đường tìm đã được JVM/class loader sử dụng. Trên các bản OpenJDK/HotSpot hiện đại, đường tìm này được lưu lại trong quá trình khởi tạo. Java không cung cấp API chuẩn để bắt JVM nạp lại danh sách đó tại runtime.

**Cách chọn đúng:** nếu chủ động điều khiển lệnh khởi động, truyền `-Djava.library.path=...` trước tên class/JAR; nếu phải nạp một file native tại đường dẫn được xác định sau khởi động, dùng `System.load(absolutePath)` và quản lý các thư viện phụ thuộc theo cơ chế của hệ điều hành. Hai cách có những giới hạn khác nhau; cả hai đều cần file native đúng kiến trúc, ABI và quyền truy cập.

## 1. Những đường dẫn dễ bị nhầm với nhau

| Thành phần | Dùng để tìm gì? | Ví dụ | Khi nào được thiết lập? |
| --- | --- | --- | --- |
| Java `-cp` / `--class-path` | Class Java và JAR trên class path | `java -cp app.jar com.example.Main` | Khi khởi động chương trình |
| `java.library.path` | Các thư mục mà cơ chế tải thư viện native của Java dùng cho `loadLibrary` | `-Djava.library.path=/opt/app/native` | Nên cấu hình trước khi JVM khởi động |
| `System.loadLibrary("foo")` | **Tên logic** của thư viện native, không phải tên file/đường dẫn | `"foo"` → thường `libfoo.so` trên Linux, `foo.dll` trên Windows | Lúc gọi, nhưng dùng cấu hình/cơ chế tìm đã có |
| `System.load("/opt/app/native/libfoo.so")` | **File native xác định** bởi đường dẫn tuyệt đối | `/opt/app/native/libfoo.so` | Có thể gọi sau khi JVM chạy, nếu file hợp lệ |
| OS dynamic loader search path | Các thư viện phụ thuộc mà binary native cần, và những tìm kiếm native do OS đảm nhận | Linux `LD_LIBRARY_PATH`, ELF `RPATH/RUNPATH`; Windows DLL search; macOS `@rpath` | Theo quy tắc loader và môi trường tiến trình, không phải một system property Java |

`java.library.path` **khác** `java.class.path`. Đặt file `libfoo.so` cạnh `app.jar` không tự khiến `System.loadLibrary("foo")` tìm được file. Tương tự, gọi `System.load` trỏ tới file chính không tự bảo đảm mọi `.so`/`.dll` mà file đó phụ thuộc đều được tìm thấy.

Tên file native phụ thuộc nền tảng; `System.mapLibraryName("foo")` trả về cách ánh xạ tên theo JVM hiện tại. Không tự ghép `"lib" + name + ".so"` rồi dùng cho mọi hệ điều hành.

## 2. Vì sao `System.setProperty` sau startup không hoạt động như mong đợi?

Giả sử quá trình khởi động Java diễn ra theo thứ tự:

```text
Shell / service / container
    │
    ├── Đặt environment và các -D JVM arguments
    ▼
JVM khởi tạo
    │
    ├── Đọc các system properties ban đầu
    ├── OpenJDK lưu/cố định một số giá trị cấu hình nội bộ
    │   (trong đó có đường tìm native library)
    ▼
main(...) bắt đầu
    │
    ├── System.setProperty("java.library.path", "/new/native")
    │   └── Thay đổi giá trị nhìn thấy bởi System.getProperty(...)
    │
    └── System.loadLibrary("foo")
        └── Không bắt buộc đọc lại property vừa đổi;
            đường tìm đã có từ startup vẫn được dùng
```

Trong OpenJDK, lớp nội bộ `jdk.internal.util.StaticProperty` ghi rõ các giá trị đã được lưu từ lúc khởi tạo sẽ không thay đổi theo `System.setProperty`; mã nguồn hiện hành có trường `JAVA_LIBRARY_PATH` và phương thức `javaLibraryPath()`. Đây là **chi tiết triển khai OpenJDK**, không phải một giao diện ứng dụng được phép gọi trực tiếp. Bản thân tài liệu API `java.lang.System` cũng cảnh báo rằng thay đổi standard system properties sau khởi tạo có thể không tạo tác dụng mong muốn vì các giá trị có thể được cache.

Ví dụ sai thường gặp:

```java
String newDirectory = "/opt/new-native";
System.setProperty("java.library.path", newDirectory);

System.out.println(System.getProperty("java.library.path"));
// In ra /opt/new-native, nhưng không chứng minh loader đã đổi nơi tìm.

System.loadLibrary("foo");
// Trên OpenJDK/HotSpot thông dụng, KHÔNG thể trông cậy lệnh này
// sẽ bắt đầu tìm trong /opt/new-native.
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Cần phân biệt hai trạng thái:

1. **Giá trị property đọc qua API Java:** có thể đã đổi; `getProperty` phản ánh giá trị vừa gán.
2. **Trạng thái thực tế của bộ nạp native:** có thể đã được xác lập trước đó và không đổi theo chuỗi property.

Không có lời hứa trong Java SE rằng “gán lại `java.library.path` rồi lần `loadLibrary` kế tiếp sẽ dùng thư mục mới”. Do đó, không dùng cách này cho logic hot reload, cho plugin native cài thêm sau startup hoặc làm cơ chế chuyển phiên bản thư viện đang chạy.

### Cả khi chưa từng gọi `loadLibrary` trước đó thì sao?

Đừng dựa vào giả thuyết “lần đầu gọi `loadLibrary` mới đọc property nên có thể gán ngay trước lần gọi đầu tiên”. JDK đã có thể khởi tạo và giữ đường tìm trong giai đoạn bootstrap. Thời điểm chính xác là chi tiết của bản triển khai; cơ chế thư viện không có hợp đồng chuẩn cho việc cập nhật `java.library.path` giữa chừng.

Tương tự, việc `System.setProperties(...)`, `System.clearProperty("java.library.path")` hoặc thay nội dung `System.getProperties()` không phải API refresh native loader.

## 3. Chọn `loadLibrary` hay `load`?

### `System.loadLibrary(String libname)`

- Đối số là **tên logic**, ví dụ `System.loadLibrary("pathlesson")`.
- Không truyền `libpathlesson.so`, `pathlesson.dll`, thư mục hoặc đường dẫn; API không nhận phần tiền tố/hậu tố phụ thuộc OS.
- Cơ chế của JVM áp dụng ánh xạ tên và tìm thư viện theo class loader/cấu hình nền tảng. Một `ClassLoader` tùy biến có thể override `findLibrary(String)` để trả về **đường dẫn tuyệt đối**; nếu không, Java sử dụng đường tìm native theo `java.library.path`.
- Hợp với ứng dụng có vị trí thư viện cố định và đã cấu hình đúng **trước lúc JVM chạy**.

Ví dụ cấu hình từ command line:

```bash
java -Djava.library.path=/opt/myapp/native -cp app.jar com.example.Main
```

Lệnh trên hợp lệ trên hệ Unix khi thư mục tồn tại. JVM argument `-D...` phải nằm **trước** tên main class hoặc `-jar`; nếu đặt sau tên class, nó thường trở thành đối số của `main`. Với nhiều đường dẫn, dùng `File.pathSeparator` tương ứng hệ điều hành (`:` ở Unix thông dụng, `;` ở Windows). Tránh ép một đường dẫn Unix sang Windows hoặc ngược lại.

### `System.load(String filename)`

- Đối số là **đường dẫn tuyệt đối đến file native**, gồm tên file và extension phù hợp nền tảng; `System.load` không nhận mỗi tên logic.
- Có thể quyết định file ở runtime, ví dụ sau khi đọc thư mục cấu hình hoặc giải nén một native artifact đáng tin cậy ra đĩa.
- Việc nạp vẫn phải vượt qua kiểm tra kiến trúc, quyền truy cập, các thư viện phụ thuộc, native symbols và quy tắc class loader. Đường dẫn tuyệt đối chỉ giải quyết **việc xác định file chính**.
- Việc đổi `java.library.path` không cần thiết cho `System.load`.

Ví dụ:

```java
import java.nio.file.Path;

Path library = Path.of("/opt/myapp/native/libfoo.so")
        .toAbsolutePath()
        .normalize();

System.load(library.toString());
```

Đây là đoạn minh họa **chỉ dành cho Linux** với file thực tế tồn tại; không tự động áp dụng phần mở rộng `.so` trên Windows/macOS. `Path.toAbsolutePath()` hữu ích để bảo đảm hợp đồng absolute path nhưng **không** xác minh rằng file đáng tin, đúng ABI hay không chứa symlink ngoài thư mục dự kiến.

## 4. Thực hành JNI hoàn chỉnh trên Linux + JDK 17+

Bài thực hành dùng một thư viện native rất nhỏ tên logic `pathlesson`. Ta giữ nguyên file native và chạy **ba JVM mới**, so sánh khi thay property trong `main`, khi chỉ định file tuyệt đối, và khi đặt đường tìm lúc startup. Ví dụ được thiết kế cho **Linux x64 hoặc Linux cùng kiến trúc với JDK đang dùng, GCC/Clang, JDK 17+**; các hệ khác cần cách biên dịch/link theo nền tảng riêng.

### Bước A — File Java `NativeLoadDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class NativeLoadDemo {
    private static native int answer();

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java NativeLoadDemo name|file <library-file>");
        }

        String mode = args[0];
        Path library = Path.of(args[1])
                .toAbsolutePath()
                .normalize();

        if (!Files.isRegularFile(library)) {
            throw new IllegalArgumentException(
                    "Native library file does not exist: " + library);
        }

        String directory = library.getParent().toString();

        // Gán sau khi JVM đã vào main: chỉ chứng minh property đổi.
        System.setProperty("java.library.path", directory);
        System.out.println("property updated="
                + directory.equals(System.getProperty("java.library.path")));

        try {
            switch (mode) {
                case "name" -> System.loadLibrary("pathlesson");
                case "file" -> System.load(library.toString());
                default -> throw new IllegalArgumentException(
                        "Mode must be name or file");
            }

            System.out.println("result=" + answer());
        } catch (UnsatisfiedLinkError e) {
            // Chỉ để quan sát trong bài học; ứng dụng thực phải log nguyên nhân.
            System.out.println("load failed: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chương trình không đặt `System.loadLibrary` vào `static { ... }` để có thể chủ động chọn từng chế độ chạy trong `main`. Phương thức `answer()` được định nghĩa tại native library ở bước tiếp theo.

### Bước B — File C `native_path.c`

```c
#include "NativeLoadDemo.h"

JNIEXPORT jint JNICALL Java_NativeLoadDemo_answer(
        JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return 42;
}
```

Tên hàm và chữ ký do JNI quy ước cho `static native int answer()` thuộc class không khai báo package có tên `NativeLoadDemo`. Header `NativeLoadDemo.h` được **javac tạo tự động**; không cần tự viết prototype JNI.

### Bước C — Biên dịch

Thực hiện trong cùng một thư mục chứa hai file trên:

```bash
# JAVA_HOME trỏ tới JDK đang biên dịch, ví dụ /usr/lib/jvm/... .
javac -h . NativeLoadDemo.java

mkdir -p native-out

cc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o native-out/libpathlesson.so \
  native_path.c
```

`javac -h .` vừa biên dịch `NativeLoadDemo.class` vừa tạo `NativeLoadDemo.h`. `cc -shared -fPIC` tạo shared library trên Linux; hai đường `include` cung cấp khai báo JNI. Trước bước này cần có compiler native và biến `JAVA_HOME` trỏ đến đúng JDK. Khi nạp trên một môi trường khác, thư viện phải được biên dịch đúng kiến trúc/ABI của tiến trình Java đích.

### Bước D — Ba lần chạy độc lập

**Lần 1 — đổi property bên trong `main` rồi gọi theo tên:**

```bash
java NativeLoadDemo name native-out/libpathlesson.so
```

Khi thư mục `native-out` **không nằm trong đường tìm native ban đầu** và không có thư viện trùng tên ở vị trí khác, đầu ra chuẩn là:

```text
property updated=true
load failed: UnsatisfiedLinkError
```

Đây là **kết quả có điều kiện**, vì đường tìm mặc định có thể khác theo hệ/JVM. File `libpathlesson.so` vẫn tồn tại và property đọc được vẫn đã đổi. Lỗi đến từ việc `loadLibrary` dùng cơ chế tìm theo tên đã được cấu hình trước, không lấy thư mục mới từ `System.setProperty`.

**Lần 2 — nạp file bằng đường dẫn tuyệt đối do Java tạo:**

```bash
java NativeLoadDemo file native-out/libpathlesson.so
```

Đầu ra mong đợi:

```text
property updated=true
result=42
```

`Path.toAbsolutePath()` chuyển tên file tương đối của tham số thành đường dẫn tuyệt đối; `System.load(...)` dùng chính file đó. Không cần thay đường tìm trong JVM để xác định file chính.

**Lần 3 — cấu hình `java.library.path` ngay khi khởi động:**

```bash
java -Djava.library.path=native-out \
  NativeLoadDemo name native-out/libpathlesson.so
```

Đầu ra mong đợi:

```text
property updated=true
result=42
```

Dù `main` lại gán property sang một giá trị đường dẫn tuyệt đối, `loadLibrary` thành công vì bản khởi động JVM **đã có** thư mục `native-out` để tìm file. So sánh ba lần cho thấy sự khác biệt giữa **giá trị hiển thị của system property**, **đường tìm được JVM sử dụng** và **đường dẫn tuyệt đối tới file**.

Nếu thư viện không load được ở lần 2 hoặc 3, đừng kết luận ngay là do `java.library.path`: kiểm tra compiler/JDK arch, file output, quyền truy cập, các thư viện phụ thuộc và thông điệp `UnsatisfiedLinkError`. Đoạn `catch` ở ví dụ chỉ in loại ngoại lệ để giữ stdout ngắn; trong hệ thống thật phải giữ message/stack trace để chẩn đoán.

## 5. Hai tầng tìm thư viện: JVM tìm file chính, OS tìm dependency

Giả sử `libengine.so` được build để cần `libcodec.so`:

```text
Java
  └─ System.load("/opt/product/native/libengine.so")
       │
       ├─ Java đã biết chính xác file libengine.so
       ▼
     OS dynamic loader (Linux)
       └─ Cần tìm tiếp libcodec.so
            ├─ ELF RPATH/RUNPATH (tùy binary)
            ├─ LD_LIBRARY_PATH được loader sử dụng theo quy tắc OS
            ├─ cache/system locations...
            └─ Không mặc nhiên dùng java.library.path
```

Nếu `libengine.so` đã được tìm thấy mà `libcodec.so` không tìm được, `System.load` vẫn có thể ném `UnsatisfiedLinkError`. Đặt `java.library.path` đúng cho file chính không tự giải quyết dependency. Chiến lược tìm thư viện của OS cũng không giống nhau trên mọi hệ:

- **Linux/ELF:** xem `DT_NEEDED`, `RPATH`/`RUNPATH`, `$ORIGIN` và đường tìm do dynamic linker áp dụng. `LD_LIBRARY_PATH` thường là cấu hình môi trường của tiến trình khi khởi động. `readelf -d libengine.so` giúp xem dependencies và embedded paths; `ldd` hữu ích với **binary tin cậy**.
- **Windows:** Windows loader áp dụng thứ tự tìm DLL riêng (có ảnh hưởng từ thư mục ứng dụng, chính sách loader, cấu hình hệ thống). `PATH` là một yếu tố trong một số trường hợp, nhưng **không phải** bản sao của `java.library.path`. Có thể dùng công cụ `dumpbin /DEPENDENTS` hoặc công cụ dependency inspection phù hợp.
- **macOS:** `@rpath`, `@loader_path`, `@executable_path`, các load commands trong Mach-O quyết định đường liên kết; một số environment variables chịu ảnh hưởng bởi cơ chế bảo vệ OS. `otool -L libengine.dylib` cho biết thư viện phụ thuộc.

**Quy tắc chung:** cập nhật `System.setProperty("java.library.path", ...)` không điều khiển dynamic loader của OS. Java `System.getenv()` cũng không cung cấp API chuẩn để ghi lại environment của tiến trình hiện tại. Hãy cấu hình môi trường trước khi chạy Java hoặc đóng gói dependency bằng các cơ chế native loader được hỗ trợ.

Đối với Linux, `$ORIGIN` trong RUNPATH/RPATH (theo linker và chính sách đóng gói) có thể giúp `libengine.so` tìm `libcodec.so` nằm cạnh nó. Điều này thường bền vững hơn việc thay đổi môi trường tùy ý giữa lúc ứng dụng hoạt động. Cần kiểm tra security và quy tắc ưu tiên cụ thể của OS/toolchain.

## 6. Những cách hợp lệ khi thư mục thư viện chỉ được biết ở runtime

### Cách A — Biết vị trí từ trước: đặt JVM argument trước startup

Ví dụ trong script khởi động, service manager, container entrypoint hoặc Gradle/Maven launch config:

```bash
java -Djava.library.path=/opt/product/native -jar product.jar
```

Nếu cần thay đổi đường tìm cho cả ứng dụng, cập nhật cấu hình khởi động rồi chạy **JVM mới**. Trong container, nên cấu hình image/mount/command và native dependencies sao cho có sẵn khi khởi động; đổi environment của container sau khi Java đã chạy không tự cập nhật JVM cũ.

### Cách B — Chỉ biết tên file sau startup: dùng `System.load`

Đọc cấu hình, xác định đúng file bản build native phù hợp OS/CPU, kiểm tra đó là file trong vùng cho phép rồi gọi một đường dẫn tuyệt đối:

```java
// Đoạn minh họa, chạy trong code quản lý thư viện tin cậy.
Path nativeFile = Path.of(configuredDirectory, "libengine.so")
        .toAbsolutePath()
        .normalize();

if (!Files.isRegularFile(nativeFile)) {
    throw new IllegalArgumentException("Missing native file: " + nativeFile);
}

System.load(nativeFile.toString());
```

Code trên dành cho Linux và cần các `import` tương ứng. Không ghép file name từ đầu vào không đáng tin một cách tùy tiện. Nên kiểm tra thư mục đáng tin cậy, quyền truy cập, provenance và tương thích kiến trúc trước khi load. Việc `normalize()` không đủ để chống symlink trỏ sang nơi khác; môi trường có yêu cầu bảo mật cần xác minh bằng chính sách đường dẫn và filesystem thực.

**Giới hạn:** `System.load` không tương đương với “unload/reload” bản thư viện đang dùng, và không giải quyết tự động transitive dependencies.

### Cách C — Đóng gói thư viện native trong JAR

`System.load` không nạp trực tiếp một entry nằm trong JAR bằng đường dẫn `jar:file:...!/...` như một file native thông thường. Một cơ chế triển khai là:

1. Chọn tài nguyên native tương ứng OS/architecture.
2. Giải nén từ JAR vào thư mục native riêng, đáng tin cậy, với file name/path cụ thể; chú ý permissions, cạnh tranh giữa tiến trình và cleanup.
3. `System.load(absoluteExtractedFilePath)` khi file đã hoàn chỉnh.
4. Cung cấp đúng cách các native dependencies theo quy tắc OS.

Không tạo thư viện trong thư mục dùng chung mà người khác có thể thay thế file lúc chương trình load. Nếu bản ứng dụng có nhiều phiên bản native, cần chiến lược tên file/phân vùng version và tránh nạp một binary không tương thích với code Java.

### Cách D — Class loader tùy biến (trường hợp framework)

`ClassLoader.findLibrary(String libname)` có thể được override để JVM nhận **đường dẫn tuyệt đối** cho thư viện thuộc các class được load bằng class loader đó. Cơ chế này hữu ích khi bạn **sở hữu framework/class loader**, nhưng không phải cách để thay đổi toàn cục `java.library.path` của mọi class loader. Nó cũng không vượt qua quy tắc mỗi JNI native library gắn với một class loader, hay việc không thể tự do unload/hot swap binary đang được dùng.

Không tạo class loader mới chỉ để né `java.library.path` nếu không thực sự cần quản lý class/native isolation và lifecycle phức tạp của plugin.

### Cách E — FFM API khi ứng dụng dùng Foreign Function & Memory API

Ở Java 22+, một ứng dụng dùng FFM có thể chọn library bằng `SymbolLookup.libraryLookup(Path, Arena)` và lấy địa chỉ symbol theo API FFM. Đây là **cơ chế khác** với `System.loadLibrary` dành cho JNI; nó không tự làm cho các `native` method JNI được liên kết. Một đoạn minh họa Java 22+:

```java
// Minh họa, chưa tạo downcall; cần import java.lang.foreign.*.
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup = SymbolLookup.libraryLookup(
            Path.of("/opt/product/native/libengine.so"), arena);
    // lookup.find("exported_function").orElseThrow()
    // cần chữ ký C và FunctionDescriptor đúng trước khi gọi.
}
```

`libraryLookup` là phương thức restricted và có thể cần cấu hình `--enable-native-access` phù hợp module/JDK (ví dụ ứng dụng classpath dùng `--enable-native-access=ALL-UNNAMED`). Vòng đời symbol/library lookup gắn với `Arena`; không giữ địa chỉ native rồi gọi sau khi arena không còn hợp lệ. Cơ chế này cũng không bỏ qua việc OS phải resolve dependencies.

## 7. Vì sao nạp lại sau khi sửa file không phải “hot reload” native?

Native library không giống class Java có thể đổi version thông qua một class loader mới. Các nguyên tắc thực tế:

- Khi cùng class loader đã nạp một JNI library, nạp lại cùng binary không bắt buộc đọc lại file hoặc chạy lại mã khởi tạo. JVM và OS có thể giữ thư viện đang nạp.
- Đặc tả JNI quy định một JNI native library không được nạp đồng thời vào **hai class loader khác nhau**; sẽ có trường hợp nhận `UnsatisfiedLinkError: ... already loaded in another classloader`. Điều này thường gặp khi redeploy web app/plugin mà class loader cũ còn sống.
- Đổi bản `.so`/`.dll` trên đĩa trong khi nó đang được sử dụng không đảm bảo thay code native đang thực thi, và có thể vi phạm cơ chế quản lý file của OS.
- Thư viện chỉ có thể được giải phóng trong các điều kiện lifecycle phù hợp; không có API Java chuẩn `System.unloadLibrary(...)` đối xứng để ứng dụng tùy ý unload bản JNI đang dùng.

Với thay đổi **đường tìm native toàn cục**, cập nhật **phiên bản binary**, hoặc sửa **native ABI**, cách quản trị dễ kiểm chứng nhất thường là dừng tiến trình và khởi động JVM mới với thư viện/cấu hình chính xác. Với plugin framework cần chạy liên tục, phải thiết kế versioning, class loader/native isolation và giới hạn unload cụ thể ngay từ đầu; không lấy `System.setProperty` làm phương án hot swap.

## 8. Chẩn đoán `UnsatisfiedLinkError` theo nguyên nhân

`UnsatisfiedLinkError` có thể phát sinh ở những bước khác nhau. Đọc **toàn bộ message/cause/stack trace**, không kết luận mọi lỗi đều là “sai `java.library.path`”.

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `no foo in java.library.path: ...` | Tên logic không resolve được theo đường tìm JVM đang dùng | Cấu hình `-Djava.library.path` trước startup hoặc dùng `System.load` absolute |
| `Expecting an absolute path of the library` | Truyền đường tương đối cho `System.load` | Dùng `Path.toAbsolutePath()`/đường tuyệt đối |
| Thông báo thiếu `libbar.so` hoặc `bar.dll` | File chính tìm được, nhưng thiếu dependency native | Điều chỉnh cơ chế tìm dependency của OS, build RUNPATH/rpath/package |
| `wrong ELF class`, `not a valid Win32 application`, thông báo architecture | JVM/native binary khác 32/64-bit hoặc CPU/ABI | Dùng native artifact đúng target và Java process |
| `already loaded in another classloader` | JNI library bị nạp từ class loader khác còn sống | Thiết kế loader ownership/lifecycle, tránh load trùng, cân nhắc restart |
| `... symbol not found`, `undefined symbol` hoặc `'...NativeMethod...'` | Thiếu symbol, sai export/signature, phiên bản binary hoặc dependency không khớp | Kiểm tra JNI header, function name, ABI, exported symbols và dependency versions |
| Load được nhưng gọi native crash | Sai chữ ký, lỗi native memory, lỗi ABI hoặc lifecycle | Dùng debug native, crash log/hs_err, kiểm tra JNI/FFM signature, không chỉ sửa path |

Một quy trình kiểm tra ngắn:

1. **Xác nhận API:** hiện tại đang gọi `System.loadLibrary`, `System.load`, hay FFM lookup?
2. **Xác nhận thời điểm:** đường dẫn được đặt trong lệnh `java -D...` hay gán trong `main` khi JVM đã khởi động?
3. **Xác nhận file:** tên logic `foo` tương ứng file nào trên OS, file có tồn tại, và đường dẫn có đúng với class loader đang gọi?
4. **Xác nhận binary:** kiến trúc/OS/ABI của thư viện có tương thích JVM? Dùng `file libfoo.so` trên Linux; với dependency xem `readelf -d`, `ldd` (binary tin cậy).
5. **Xác nhận dependency:** loader của OS có tìm được thư viện phụ thuộc không?
6. **Xác nhận lifecycle:** library đã nạp bởi class loader khác, hay ứng dụng đang cố thay binary đang được sử dụng?

Đặc biệt, `System.out.println(System.getProperty("java.library.path"))` là thông tin cấu hình nhìn qua Java API, **không phải bằng chứng cuối cùng** cho đường tìm đã được JVM dùng tại thời điểm lỗi. Kết hợp command line thực tế, build/version JDK, full stack trace và bằng chứng native loader.

## 9. Các mẹo “refresh path” trên mạng: vì sao nên tránh?

Một số hướng dẫn cũ gợi ý phản chiếu (reflection) vào các trường nội bộ như `ClassLoader.sys_paths` hoặc `usr_paths`, gán `null`, rồi gọi lại `System.loadLibrary`. Những trường đó **không phải public API**; có thể khác hoặc không tồn tại trên JDK mới. Module encapsulation từ Java 9+, thay đổi triển khai, quyền truy cập và vấn đề thread safety khiến thủ thuật này không portable và không được đảm bảo hỗ trợ.

Tương tự:

- Đặt `System.setProperty("java.class.path", ...)` không sửa đường tìm native.
- Đặt `-Djava.library.path=...` thành **đối số `main`** sau khi JVM đã khởi chạy là sai thời điểm.
- Đổi `user.dir` không phải cách hỗ trợ chính thức để thay thư mục hiện hành của OS loader.
- Đổi `LD_LIBRARY_PATH`/`PATH` “bên trong Java” bằng thủ thuật không chuẩn không khiến các subsystem đã khởi tạo cập nhật đồng bộ, và không xử lý được mọi phiên bản OS/JVM.
- Dùng `System.load` cho một `.so` cụ thể không làm JVM quên thư viện JNI trước đó cùng tên.

Khi cần tính portable, dùng cơ chế công khai: **startup options**, **đường dẫn file tuyệt đối**, **loader/framework có hợp đồng rõ**, hoặc **khởi động tiến trình mới**.

## 10. Áp dụng vào thiết kế ứng dụng thực tế

| Nhu cầu | Lựa chọn gợi ý | Giới hạn phải nhớ |
| --- | --- | --- |
| Native lib cố định theo bản release | `-Djava.library.path=...` khi start, rồi `loadLibrary` | Cần JVM mới để đổi cấu hình đã cache |
| Người dùng chọn file native lúc đang chạy | Xác minh đường dẫn, `System.load(absolutePath)` | Dependency/lifecycle vẫn theo OS và class loader |
| Cài thư viện như resource của JAR | Giải nén ra đường dẫn file tin cậy, `System.load` | Không nạp trực tiếp entry trong JAR; xử lý đa kiến trúc và cleanup |
| Native lib có nhiều thư viện phụ thuộc | Đóng gói chung đúng ABI; cấu hình OS loader / `RUNPATH` hợp lý | `java.library.path` không phải dependency resolver phổ quát |
| Plugin cần lớp và JNI riêng | Thiết kế class loader và native ownership từ đầu | Cùng một JNI binary không tùy ý gắn vào nhiều loaders |
| Phát hành native version mới lên server | Triển khai artifact rồi restart/roll JVM | Thay file đang được load không bảo đảm thay code |
| Ứng dụng dùng FFM Java 22+ | `SymbolLookup.libraryLookup(Path, Arena)` với native access phù hợp | Khác JNI linking, có arena lifecycle và vẫn phụ thuộc OS loader |

Khi nhận yêu cầu “đổi thư mục tìm thư viện ngay bây giờ, không restart”, câu hỏi quyết định là **cần nạp một file native mới chưa từng sử dụng hay cần đổi bản native đã liên kết trong JVM?** Trường hợp đầu có thể xử lý bằng `System.load` tuyệt đối nếu điều kiện native cho phép. Trường hợp sau có những ràng buộc nặng hơn về JNI/class loader, OS mapped library, symbol resolution và ABI; thường cần quy trình restart/rolling deployment.

## 11. Tự kiểm tra

**Câu 1.** `System.setProperty("java.library.path", "/tmp/libs")` trả về bình thường. Có chắc `loadLibrary("foo")` sau đó sẽ tìm `/tmp/libs/libfoo.so` không?

**Không.** Đã đổi property ở tầng Java, còn đường tìm của OpenJDK có thể đã được cache từ startup. Truyền `-Djava.library.path=/tmp/libs` ngay khi start hoặc dùng `System.load("/tmp/libs/libfoo.so")` nếu chủ động xác định đúng file.

**Câu 2.** Đã gọi `System.load("/opt/native/libfoo.so")` nhưng vẫn nhận `UnsatisfiedLinkError` báo thiếu `libbar.so`. Cần đổi `java.library.path` không?

**Không phải giải pháp trực tiếp.** Lỗi nằm ở thư viện phụ thuộc của file chính. Phải kiểm tra cơ chế tìm của OS loader, build flags/RUNPATH/RPATH, môi trường và cách đóng gói `libbar.so`.

**Câu 3.** Đã dùng `-Djava.library.path=./native` nhưng `System.loadLibrary("foo")` vẫn không tìm được. Ba điều cần xác minh?

Thư mục `./native` được hiểu tương đối với working directory **ở môi trường thực tế lúc khởi động**; file có tên native tương ứng (ví dụ `libfoo.so` trên Linux) và architecture đúng; các dependencies và class loader ownership không gây lỗi. Sau đó kiểm tra full error text.

**Câu 4.** Đổi file `libfoo.so` trên ổ đĩa bằng build mới trong lúc JVM đang dùng thư viện cũ có thay ngay implementation cho mọi lời gọi JNI sau đó không?

**Không được bảo đảm.** JNI library đã được load/linked và có vòng đời riêng. Cần quy trình triển khai/restart hoặc thiết kế plugin native lifecycle chuyên biệt.

**Câu 5.** Vì sao `loadLibrary("foo")` và `load("/absolute/path/libfoo.so")` có thể cho kết quả khác nhau trong cùng một JVM?

Cách đầu bắt đầu bằng **tên logic** và đường tìm của JVM/class loader; cách sau đã xác định **file chính bằng đường dẫn tuyệt đối**. Cả hai vẫn cùng chịu giới hạn OS loader, ABI và JNI lifecycle.

## Tài liệu chính thức để đối chiếu

- Java SE 17 — `ClassLoader.findLibrary(String)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String)
- Java SE 21 — `System`, standard properties và lưu ý về cache: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
- Java SE 21 — `Runtime.load` và `Runtime.loadLibrary`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html
- OpenJDK — `StaticProperty.javaLibraryPath()` (đặc điểm triển khai): https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/jdk/internal/util/StaticProperty.java
- JNI Specification — Library and Version Management: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html#library-and-version-management
- Java 22+ — `SymbolLookup.libraryLookup(Path, Arena)`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html

**Ghi nhớ:** muốn thay đổi đường tìm `loadLibrary` cho lần chạy tiếp theo, chỉnh **cấu hình khởi động JVM**. Muốn nạp một **file native cụ thể** sau khi JVM đã chạy, dùng **đường dẫn tuyệt đối** với cơ chế phù hợp. Đừng nhầm việc đổi một system property với việc cấu hình lại native loader, cũng đừng quên thư viện phụ thuộc và vòng đời JNI.