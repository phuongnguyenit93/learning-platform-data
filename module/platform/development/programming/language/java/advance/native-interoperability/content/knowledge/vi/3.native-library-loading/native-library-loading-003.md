# Ánh xạ tên bằng `System.mapLibraryName` và vai trò `java.library.path`

## 1. Vấn đề cần giải quyết

Khi một chương trình Java cần gọi hàm trong thư viện native (C/C++), JVM phải tìm được **tệp thư viện được biên dịch cho đúng hệ điều hành và kiến trúc CPU**, nạp nó vào tiến trình, rồi liên kết lời gọi native phù hợp. Tên thư viện mà Java truyền vào API thường **không trùng nguyên văn** với tên tệp trên đĩa:

- Linux: thư viện logic `mathbridge` thường tương ứng `libmathbridge.so`.
- Windows: thư viện logic `mathbridge` thường tương ứng `mathbridge.dll`.
- macOS: thư viện logic `mathbridge` thường tương ứng `libmathbridge.dylib`.

Hai khái niệm quyết định bước tìm nạp:

1. **`System.mapLibraryName(String libname)`**: đổi **tên logic** của thư viện thành **tên tệp native theo quy tắc nền tảng**. Đây là thao tác tạo tên, **không tìm tệp và không nạp thư viện**.
2. **`java.library.path`**: system property chứa những **thư mục tìm kiếm thư viện native** được JVM dùng trong đường tải thư viện bằng tên; đây **không phải** Java classpath và cũng không tự giải quyết mọi thư viện phụ thuộc ở cấp hệ điều hành.

Tên tệp đúng là **điều kiện cần, chưa phải điều kiện đủ**: thư viện phải nằm trong đường tìm kiếm thích hợp (hoặc có đường dẫn tuyệt đối), đúng định dạng, đúng kiến trúc, đủ quyền truy cập và có các thư viện phụ thuộc cần thiết.

## 2. Phân biệt ba API thường bị nhầm

| API / thành phần | Đầu vào | Chức năng | Điểm cần nhớ |
| --- | --- | --- | --- |
| `System.mapLibraryName("mathbridge")` | Tên logic | Trả về tên tệp theo nền tảng | Không kiểm tra tệp có tồn tại, không tải thư viện. |
| `System.loadLibrary("mathbridge")` | **Tên logic**, không có thư mục, tiền tố `lib` hay phần mở rộng | Yêu cầu JVM nạp thư viện native theo tên; JVM áp dụng cơ chế tìm thư viện thích hợp | Thường liên quan đến `java.library.path` và bộ nạp lớp; có thể thất bại với `UnsatisfiedLinkError`. |
| `System.load("/absolute/path/libmathbridge.so")` | **Đường dẫn tuyệt đối**, bao gồm tên tệp thực | Yêu cầu nạp trực tiếp từ đường dẫn đã cung cấp | Không cần tra tên theo `mapLibraryName` hoặc tìm theo `java.library.path`; phụ thuộc native vẫn do bộ nạp của OS xử lý. |
| `ClassLoader.findLibrary("mathbridge")` | Tên logic | Điểm mở rộng để custom class loader trả về đường dẫn tuyệt đối | Nếu cơ chế này trả `null`, JVM có thể tìm theo `java.library.path`. |

Sơ đồ thông thường cho thư viện động (bỏ qua một số trường hợp đặc biệt như thư viện đã liên kết tĩnh với JVM):

~~~text
Java: System.loadLibrary("mathbridge")
          |
          v
JVM dùng cơ chế tìm thư viện gắn với class loader
          |
          +-- ClassLoader.findLibrary("mathbridge") có thể cung cấp
          |   một đường dẫn tuyệt đối
          |
          +-- Hoặc JVM dùng các đường tìm kiếm thích hợp,
          |   trong đó có java.library.path
          |                  |
          |                  v
          |        tên tệp theo nền tảng
          |        (ví dụ libmathbridge.so)
          |
          v
Bộ nạp native của hệ điều hành mở thư viện và phụ thuộc của nó
          |
          v
JNI/foreign function được liên kết/gọi nếu chữ ký, ABI và symbol hợp lệ
~~~

Đây là **sơ đồ khái niệm**, không phải lời hứa về thứ tự tìm kiếm giống hệt nhau trên mọi JVM/OS. `System.loadLibrary` tự thực hiện đường nạp thư viện theo đặc tả và triển khai; ứng dụng **không bắt buộc** gọi `System.mapLibraryName` trước `loadLibrary`. Ta chủ động gọi `mapLibraryName` khi cần **hiển thị, kiểm tra tên tệp, đóng gói artifact hoặc tự dựng một đường dẫn tuyệt đối**.

## 3. `System.mapLibraryName` hoạt động như thế nào?

Chữ ký API Java:

~~~java
public static String mapLibraryName(String libname)
~~~

Đầu vào là tên logic như `"mathbridge"`. Kết quả phụ thuộc hệ điều hành và **triển khai JVM**. Ví dụ thông dụng với OpenJDK/HotSpot:

| Nền tảng | `System.mapLibraryName("mathbridge")` |
| --- | --- |
| Linux | `libmathbridge.so` |
| Windows | `mathbridge.dll` |
| macOS hiện đại | `libmathbridge.dylib` |

Bảng này dùng để hiểu quy tắc phổ biến; phần mềm cần tính di động nên **hỏi JVM đang chạy bằng API**, không viết sẵn `"lib" + name + ".so"` rồi mong dùng được trên Windows/macOS. Một số nền tảng, phiên bản và trường hợp đặc biệt có thể có cơ chế khác.

### Ví dụ Java 17+ độc lập: chỉ ánh xạ tên

Tạo tệp `MapLibraryNameDemo.java`:

~~~java
import java.io.File;

public class MapLibraryNameDemo {
    public static void main(String[] args) {
        String logicalName = "mathbridge";

        System.out.println("logical=" + logicalName);
        System.out.println("native=" + System.mapLibraryName(logicalName));
        System.out.println("pathSeparator=" + File.pathSeparator);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapLibraryNameDemo.java
java MapLibraryNameDemo
~~~

Stdout trên **Linux/OpenJDK 17**:

~~~text
logical=mathbridge
native=libmathbridge.so
pathSeparator=:
~~~

Trên Windows, hai dòng sau lần lượt có tên tệp `mathbridge.dll` và dấu phân cách đường dẫn `;`; trên macOS thông dụng, chúng là `libmathbridge.dylib` và `:`.

Bài chạy thành công **ngay cả khi trên máy không có thư viện mathbridge**: `mapLibraryName` chỉ trả chuỗi. Nó không dò đĩa, không kiểm tra ABI, không xác nhận symbol JNI và không thêm thư mục vào `java.library.path`. `File.pathSeparator` cũng không liên quan tới thao tác ánh xạ tên; chương trình in nó để giúp hiểu cách cấu hình **danh sách đường dẫn** ở phần tiếp theo.

## 4. `java.library.path` là gì và được dùng khi nào?

`java.library.path` là **system property của JVM** mô tả danh sách thư mục để tìm các native library có thể nạp theo tên. Giá trị có thể đọc bằng:

~~~java
String path = System.getProperty("java.library.path");
~~~

Để chủ động cấu hình, đặt bằng tùy chọn `-D` **lúc khởi động Java**:

~~~bash
java -Djava.library.path=./native MyMain
~~~

Nếu chạy tệp JAR:

~~~bash
java -Djava.library.path=./native -jar app.jar
~~~

`-D...` là tham số dành cho **JVM**, vì vậy phải ở trước tên class hoặc `-jar`. Câu lệnh `java MyMain -Djava.library.path=./native` truyền chuỗi đó vào `args` của ứng dụng, không cấu hình đường tìm thư viện.

Giá trị gồm **các thư mục**, không phải danh sách tên file thư viện. Khi có nhiều đường dẫn, phân cách bằng **`File.pathSeparator`** (khác `File.separator` dùng giữa các thành phần của *một* đường dẫn):

| Nền tảng | Phân cách danh sách | Ví dụ hai thư mục |
| --- | --- | --- |
| Linux/macOS | `:` | `/srv/app/native:/opt/vendor/lib` |
| Windows | `;` | `C:\app\native;D:\vendor\bin` |

Lệnh Linux/macOS:

~~~bash
java -Djava.library.path="/srv/app/native:/opt/vendor/lib" -jar app.jar
~~~

Ví dụ Windows **PowerShell** (nháy đơn giữ nguyên dấu `;` và dấu gạch chéo ngược):

~~~powershell
java '-Djava.library.path=C:\app\native;D:\vendor\bin' -jar app.jar
~~~

Đường dẫn tương đối như `./native` được hiểu dựa trên **working directory của tiến trình Java** khi chạy, không tự động dựa trên vị trí tệp `.jar` hay package của class. Ví dụ chạy ứng dụng bằng terminal từ một thư mục khác, IDE, Docker hoặc system service có thể làm đường dẫn tương đối trỏ sang nơi khác. Khi triển khai thực tế, cân nhắc dùng đường dẫn tuyệt đối được cấu hình rõ.

**Không nên sửa `java.library.path` động trong chương trình rồi kỳ vọng có hiệu lực cho `System.loadLibrary`.** JVM có thể khởi tạo/cache cơ chế tìm native library từ sớm; `System.setProperty("java.library.path", "...")` chỉ thay đổi giá trị property đọc được, **không bảo đảm** làm mới bộ nạp native. Cách ổn định là cấu hình khi khởi động JVM; nếu đã có đường dẫn file tuyệt đối, cân nhắc `System.load`.

## 5. Bài thực hành hoàn chỉnh Java 17 + JNI: quan sát ánh xạ và tìm thư viện

Bài thực hành tạo thư viện C `mathbridge` chỉ có phép cộng, sau đó gọi nó từ Java theo hai cách: `System.loadLibrary` (theo tên) và `System.load` (đường dẫn tuyệt đối). Phần build minh họa trên **Linux x86-64/ARM64 có JDK 17+ và GCC tương ứng với JVM**, biến môi trường `JAVA_HOME` trỏ đến thư mục JDK.

Cấu trúc dự kiến sau khi build:

~~~text
demo/
  LibraryPathDemo.java
  LibraryPathDemo.class
  LibraryPathDemo.h
  mathbridge.c
  native/
    libmathbridge.so
~~~

### Bước 1: mã Java

Tạo `LibraryPathDemo.java`:

~~~java
import java.nio.file.Path;

public final class LibraryPathDemo {
    private static final String LIBRARY = "mathbridge";

    private static native int add(int left, int right);

    public static void main(String[] args) {
        String fileName = System.mapLibraryName(LIBRARY);
        System.out.println("mapped=" + fileName);
        System.out.println("java.library.path=" +
                System.getProperty("java.library.path"));

        if (args.length == 1 && "absolute".equals(args[0])) {
            Path file = Path.of("native", fileName)
                    .toAbsolutePath()
                    .normalize();
            System.load(file.toString());
        } else {
            System.loadLibrary(LIBRARY);
        }

        System.out.println("sum=" + add(20, 22));
    }
}
~~~

- `System.mapLibraryName` chỉ hiển thị **tên tệp được JVM ánh xạ**.
- Nhánh mặc định gọi `System.loadLibrary("mathbridge")`: truyền **tên logic** và để JVM tìm thư viện.
- Khi truyền đối số `absolute`, chương trình dựng đường dẫn tuyệt đối đến tệp `native/<tên-đã-ánh-xạ>` rồi gọi `System.load(...)`. Phần tìm theo `java.library.path` **không được dùng để quyết định file chính** trong nhánh này.
- Mã cố ý chỉ thực hiện một phương thức tải mỗi lần chạy và gọi JNI `add` sau khi tải xong.

### Bước 2: mã C

Tạo `mathbridge.c`:

~~~c
#include <jni.h>
#include "LibraryPathDemo.h"

JNIEXPORT jint JNICALL Java_LibraryPathDemo_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
~~~

Ở đây `Java_LibraryPathDemo_add` khớp tên entry point JNI tương ứng với method `static native add` của class không có package. Tham số `jint` phù hợp Java `int`. Hai tham số `JNIEnv*` và `jclass` được API JNI truyền vào dù ví dụ chưa cần sử dụng.

### Bước 3: biên dịch Java, sinh header và tạo thư viện động Linux

Chạy các lệnh dưới đây từ thư mục `demo`:

~~~bash
javac -h . LibraryPathDemo.java
mkdir -p native
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o native/libmathbridge.so mathbridge.c
~~~

- `javac -h .` tạo `LibraryPathDemo.class` và header `LibraryPathDemo.h`, tránh tự đoán quy tắc tên symbol JNI.
- `-fPIC -shared` tạo shared library dùng được trên Linux; hai thư mục include cung cấp `jni.h` và header JNI theo Linux.
- `-o native/libmathbridge.so` tạo đúng tệp mà `mapLibraryName("mathbridge")` trả về trên Linux thông dụng.

### Bước 4: thử `System.loadLibrary` với `java.library.path`

~~~bash
java -Djava.library.path=./native LibraryPathDemo
~~~

Stdout trên Linux/OpenJDK 17 trong điều kiện trên:

~~~text
mapped=libmathbridge.so
java.library.path=./native
sum=42
~~~

Trình tự:

1. Java báo tên tệp native theo nền tảng.
2. `System.loadLibrary("mathbridge")` yêu cầu JVM nạp thư viện có tên logic `mathbridge`.
3. Với cấu hình `java.library.path=./native`, JVM tìm thư viện trong `./native`; hệ điều hành nạp file hợp lệ và các phụ thuộc cần thiết.
4. JVM liên kết và gọi `Java_LibraryPathDemo_add` khi Java gọi `add(20, 22)`.

### Bước 5: thử `System.load` bằng đường dẫn tuyệt đối

~~~bash
java LibraryPathDemo absolute
~~~

Lần này chương trình chủ động tạo absolute path đến `native/libmathbridge.so` rồi gọi `System.load`. Nếu file và các phụ thuộc hợp lệ, kết quả cuối vẫn là:

~~~text
sum=42
~~~

Hai dòng đầu vẫn xuất hiện, nhưng `java.library.path` sẽ in giá trị **mặc định của JVM trên máy đang chạy** (có thể khác nhau); không nên gán một stdout đầy đủ cố định cho nhánh này. Nhánh `absolute` được thiết kế để **không cần thêm thư mục `native` vào `java.library.path`**; nó vẫn đòi hỏi chương trình chạy từ đúng working directory vì ví dụ dùng `Path.of("native", ...)` trước khi đổi sang absolute path.

### Các nền tảng khác

Trên **macOS**: thay cách biên dịch C để tạo `native/libmathbridge.dylib` và dùng include path JNI `"$JAVA_HOME/include/darwin"`; ví dụ với Clang thường là:

~~~bash
javac -h . LibraryPathDemo.java
mkdir -p native
clang -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o native/libmathbridge.dylib mathbridge.c
java -Djava.library.path=./native LibraryPathDemo
~~~

Trên **Windows**: file ánh xạ thông thường là `mathbridge.dll`, cần trình biên dịch/SDK phù hợp với JVM đang sử dụng và thư mục JNI header `%JAVA_HOME%\include\win32`. Chú ý tên thư viện không có tiền tố `lib`; đường dẫn, tùy chọn liên kết và biểu diễn chuỗi phụ thuộc công cụ build (MSVC/MinGW). Trên cả ba hệ điều hành, **bitness và kiến trúc** của JVM và native binary phải tương thích.

## 6. Vì sao `System.mapLibraryName` không thể thay thế `java.library.path`?

Giả sử chương trình chạy trên Linux và `System.mapLibraryName("mathbridge")` trả `libmathbridge.so`:

~~~text
/srv/app/
  app.jar
  native/libmathbridge.so

Java biết tên file:        libmathbridge.so
Java cần biết nơi tìm:     /srv/app/native
Java còn cần kiểm tra:    đúng ELF, đúng CPU/ABI, đủ phụ thuộc,
                          có thể nạp, có symbol JNI phù hợp
~~~

Nếu chỉ gọi `mapLibraryName`, không hành động tìm hay nạp nào xảy ra. Nếu gọi `System.loadLibrary("mathbridge")` mà file nằm ngoài những nơi bộ nạp thực sự tìm, chương trình vẫn thất bại. Nếu biết chính xác vị trí file, `System.load("/srv/app/native/libmathbridge.so")` giúp chỉ định file chính trực tiếp.

Câu hỏi quan trọng: **“Tên tệp nào?”** là việc của `mapLibraryName`; **“Tìm ở thư mục nào?”** là việc của cơ chế tìm thư viện (trong đường nạp theo tên, `java.library.path` là một cấu phần quan trọng); **“File có tải và liên kết được không?”** phụ thuộc thêm vào loader của OS, ABI và các thư viện liên quan.

## 7. Phân biệt `java.library.path`, Java classpath và đường tìm phụ thuộc của OS

| Thành phần | Nó tìm cái gì? | Ví dụ |
| --- | --- | --- |
| `java.class.path` / `-cp` | Class và JAR của Java (trên classpath) | `java -cp "app.jar:lib/*" Main` trên Linux/macOS |
| `java.library.path` | Những thư mục JVM dùng khi tìm native library theo tên | `-Djava.library.path=/srv/app/native` |
| `PATH` (Windows), `LD_LIBRARY_PATH` (Linux), cơ chế `dyld`/`DYLD_*` (macOS) | Tùy OS, ảnh hưởng đến việc tìm binary hoặc thư viện động/phụ thuộc | Đường tìm DLL/`.so`/`.dylib` của bộ nạp hệ điều hành |
| `System.load(absolutePath)` | Tệp native được chỉ định cụ thể | `/srv/app/native/libmathbridge.so` |

**Thư viện chính và thư viện phụ thuộc là hai bài toán khác nhau.**

Ví dụ `libmathbridge.so` được JVM tìm thấy trong `/srv/app/native` nhưng nó còn phụ thuộc `libvendor.so`. Việc chỉ đặt `java.library.path=/srv/app/native` **không đảm bảo** Linux dynamic loader cũng tìm được `libvendor.so`. Bộ nạp OS xét cấu hình và metadata của binary, chẳng hạn `RPATH`/`RUNPATH` trên ELF, vị trí phụ thuộc, các thư mục chuẩn và biến môi trường thích hợp. Ở macOS có thể có `@loader_path` và `@rpath`; trên Windows có quy tắc tìm DLL khác.

Do đó, khi thông báo lỗi **“missing dependent library”** xuất hiện, không nên chỉ liên tục thêm đường dẫn vào `java.library.path`. Hãy kiểm tra dependency của native binary và cấu hình tìm phụ thuộc ở cấp OS. Việc đặt `java.library.path` đúng giải quyết phần **JVM tìm file chính**; bước tải tiếp theo vẫn có thể thất bại.

### Tệp thư viện được đặt bên trong JAR thì sao?

Việc đặt `libmathbridge.so` vào một resource trong JAR **không tự khiến** `System.loadLibrary("mathbridge")` nhìn thấy tệp đó: loader native của OS thường cần một tệp thực có thể nạp trên filesystem hoặc một cơ chế tích hợp riêng. Một giải pháp triển khai là đóng gói các binary theo OS/CPU rồi giải nén chúng vào vị trí được tin cậy, kiểm tra tính toàn vẹn và dùng `System.load` với đường dẫn tuyệt đối. Phải xác định rõ vòng đời/tên file và cách tránh tranh chấp khi nhiều tiến trình chạy đồng thời.

## 8. `ClassLoader.findLibrary` và ngữ cảnh nạp thư viện

Ở mức nâng cao, việc tìm native library có liên quan **class loader của class yêu cầu nạp**. Một custom `ClassLoader` có thể override `findLibrary(String libname)` để trả về **đường dẫn tuyệt đối** của thư viện do nó quản lý. API chuẩn mô tả: khi `findLibrary` trả `null`, JVM có thể tiếp tục tìm theo `java.library.path`. Vì vậy, **không phải mọi lần `loadLibrary` đều chỉ đơn giản quét mỗi thư mục trong property này**.

Các hệ thống có plugin, application server hoặc class loader riêng cần lưu ý:

- Native library gắn với ngữ cảnh tải; trên nhiều JVM, cố nạp cùng native library vào các class loader khác nhau có thể tạo lỗi `UnsatisfiedLinkError` liên quan đến thư viện đã nạp.
- Không nên dùng thủ thuật sửa private field/cache JVM để “refresh” `java.library.path` hay ép nạp lại. Cấu hình đường dẫn từ lúc khởi động hoặc thiết kế rõ ownership/cách tải binary.
- Nếu tổ chức quản lý bộ cài native theo module, nên gom một điểm nạp có xử lý lỗi và logging rõ ràng thay vì gọi `loadLibrary` rải rác ở nhiều class.

Lưu ý: `ClassLoader.findLibrary` là **API mở rộng cho người viết class loader**; chương trình Java thông thường không cần tự gọi nó. Ví dụ ở phần 5 dùng class loader mặc định.

## 9. Chẩn đoán `UnsatisfiedLinkError` theo từng tầng

`UnsatisfiedLinkError` có thể xuất hiện ở bước tìm thư viện, nạp native file hoặc giải quyết native symbol. Những triệu chứng và nguyên nhân mẫu:

| Tình huống | Điều cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Thông báo dạng `no mathbridge in java.library.path` | File có thực ở thư mục được JVM tìm? Có truyền tên logic `mathbridge` và đặt `-D` trước class không? | Kiểm tra path, tên file qua `mapLibraryName`, working directory và tham số JVM. |
| File chính có thật nhưng không mở được | Đúng OS/CPU/ABI? Quyền đọc/tải hợp lệ? Phụ thuộc native nào còn thiếu? | Dùng công cụ kiểm tra binary và dependency của OS; build lại đúng kiến trúc. |
| Nạp xong nhưng gọi `native add` báo thiếu triển khai | Tên symbol JNI, khai báo `native`, package/class, `static`/instance, chữ ký có khớp không? | Dùng `javac -h` để sinh header, xuất đúng JNI symbol hoặc `RegisterNatives` theo thiết kế. |
| Code dùng `System.loadLibrary("libmathbridge.so")` | API nhận tên logic; chuỗi chứa tiền tố/hậu tố platform, có thể gây tên sai | Dùng `System.loadLibrary("mathbridge")`. |
| Chạy được trong IDE nhưng thất bại khi chạy JAR/service | Working directory hoặc cấu hình JVM của IDE khác production | In `user.dir`/`java.library.path`, cấu hình đường dẫn tuyệt đối có chủ đích. |
| Nạp thư viện chính được nhưng báo thiếu `libvendor.so` / DLL khác | OS loader không giải quyết được phụ thuộc | Kiểm tra `RPATH`/`RUNPATH`, bộ cài và đường tìm phụ thuộc của OS. |
| Tải lại trong môi trường nhiều class loader gặp lỗi | Ownership theo class loader và thư viện đã nạp | Thống nhất điểm tải thư viện, kiểm tra class loader thực tế. |

Một quy trình điều tra có thể thực hiện trước khi thay đổi cấu hình:

1. In tên logic và `System.mapLibraryName(name)` để chắc rằng JVM chọn đúng **tên tệp dự kiến**.
2. In `System.getProperty("java.library.path")` và `System.getProperty("user.dir")` ngay lúc chạy ứng dụng; đối chiếu đường dẫn thực tế.
3. Kiểm tra file, kích thước, quyền, loại binary và kiến trúc CPU/JVM; **file tồn tại không có nghĩa có thể nạp**.
4. Nếu native binary có phụ thuộc, kiểm tra dependency bằng công cụ phù hợp (Linux: `readelf -d`, `ldd` cho binary tin cậy; macOS: `otool -L`; Windows: `dumpbin /DEPENDENTS` hoặc công cụ tương đương).
5. Nếu file đã nạp mà native method vẫn lỗi, kiểm tra header `javac -h`, symbol export, khai báo JNI và thông báo lỗi đầy đủ.
6. Thử `System.load` với **absolute path được tin cậy** để tách câu hỏi “đường tìm thư viện chính” khỏi các lỗi binary/ABI/dependency khác.

Các ví dụ lỗi trong bảng là **mẫu tình huống**, không cam kết chính xác từng dòng thông báo trên mọi OS/JDK.

## 10. Những lỗi thiết kế và lưu ý vận hành

### Không ghép tên tệp theo thói quen của một hệ điều hành

Không viết:

~~~java
String fileName = "lib" + name + ".so";
~~~

nếu chương trình phải chạy đa nền tảng. Hãy dùng:

~~~java
String fileName = System.mapLibraryName(name);
~~~

Cả hai đoạn là **mã minh họa một dòng, không phải chương trình độc lập**. Nếu code đã nhận đường dẫn tuyệt đối đến native binary từ cấu hình triển khai, có thể không cần dùng `mapLibraryName`.

### Không đưa đường dẫn tệp vào `loadLibrary`

Sai mục đích:

~~~java
System.loadLibrary("/opt/app/native/libmathbridge.so");
~~~

Đúng cách sử dụng:

~~~java
System.loadLibrary("mathbridge");
System.load("/opt/app/native/libmathbridge.so");
~~~

Hai dòng “đúng cách” là **hai cách thay thế**, không có ý định cùng gọi liên tiếp trong một chương trình. Dòng thứ nhất dùng tên logic; dòng thứ hai dùng absolute path trên Linux. `System.load` cũng không tự chuyển tên logic sang tên tệp.

### Không dựa vào `System.setProperty` để đổi search path sau khi JVM đã chạy

~~~java
System.setProperty("java.library.path", "/opt/app/native");
System.loadLibrary("mathbridge");
~~~

Đây là **mẫu cấu hình không đáng tin cậy**: property có thể thay đổi nhưng bộ nạp thư viện có thể đã lưu đường tìm ở giai đoạn khởi tạo. Hãy truyền `-Djava.library.path=...` lúc khởi động hoặc dùng `System.load` với đường dẫn tuyệt đối phù hợp.

### Không coi nạp thành công đồng nghĩa với an toàn

Thư viện native chạy với quyền của tiến trình Java; lỗi con trỏ, tràn bộ nhớ hoặc ABI không tương thích có thể làm sập JVM. Khi tải file từ thư mục có thể bị ghi bởi người dùng không tin cậy, có nguy cơ **library path hijacking**. Trong production, nên dùng đường dẫn đóng gói/được quản lý, quyền ghi phù hợp, kiểm tra nguồn gốc binary và tránh xây đường dẫn bằng input không tin cậy.

### Không đồng nhất Java classpath với native path

`-cp` hoặc khai báo dependency Maven/Gradle giúp Java tìm class/JAR; nó **không tự bảo đảm** JVM/OS có thể tìm và nạp `.so`/`.dll`/`.dylib`. Thư viện Java có tích hợp native cần quy trình đóng gói đúng OS/architecture và đường tải native rõ ràng.

### Kiểm tra phiên bản JDK khi triển khai

Các ví dụ chạy nhằm vào **JDK 17 trở lên**, với lệnh thực hành chuẩn trên JDK 17. Ở những phiên bản JDK mới hơn, chính sách cảnh báo hoặc yêu cầu **native access** đối với JNI/native library loading có thể thay đổi; hãy đọc hướng dẫn tương ứng với runtime thực tế. Quy tắc đặt tên logic và khác biệt giữa `mapLibraryName`, `loadLibrary`, `load` vẫn là nền tảng để phân tích.

## 11. Câu hỏi tự kiểm tra

1. Gọi `System.mapLibraryName("codec")` trên Linux trả `libcodec.so`. Thư viện `libcodec.so` chưa tồn tại trên máy: phương thức này có ném `UnsatisfiedLinkError` vì thiếu file không?
2. Với tệp `/srv/app/native/libcodec.so`, muốn nạp qua `System.loadLibrary("codec")` trong ứng dụng thông thường, có thể cấu hình JVM thế nào?
3. Vì sao `System.loadLibrary("/srv/app/native/libcodec.so")` không phải cú pháp phù hợp?
4. Chạy `java -Djava.library.path=./native App` từ hai working directory khác nhau có thể cho kết quả khác nhau không?
5. Vì sao `java.library.path` đúng vẫn có thể lỗi thiếu `libvendor.so` mà `libcodec.so` phụ thuộc?
6. Thêm thư viện native vào `app.jar` đã đủ để `System.loadLibrary("codec")` mở trực tiếp nó chưa?
7. Trong code cần hỗ trợ Windows, Linux và macOS, nên gọi API nào để dựng tên tệp từ tên logic?
8. `System.setProperty("java.library.path", "...")` ngay trước `System.loadLibrary` có phải biện pháp chuẩn để thay đổi đường tìm native không?

**Gợi ý đáp án:** (1) không, phương thức chỉ tạo chuỗi; (2) cấu hình `-Djava.library.path=/srv/app/native` trước class/JAR, hoặc cơ chế class loader tương đương; (3) `loadLibrary` nhận tên logic, muốn nạp absolute path dùng `load`; (4) có, do `./native` phụ thuộc working directory; (5) phụ thuộc do OS loader giải quyết; (6) chưa, thường cần giải nén/tích hợp bộ nạp phù hợp; (7) `System.mapLibraryName`; (8) không được bảo đảm, hãy cấu hình từ lúc JVM khởi động.

## 12. Tài liệu API chuẩn

- [Java SE 17 — `System.mapLibraryName`, `System.load` và `System.loadLibrary`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Java SE 17 — `ClassLoader.findLibrary`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String))
- [Java SE 17 — `File.pathSeparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html)
- [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html)

**Cốt lõi:** `System.mapLibraryName` giải thích **tên tệp**; `java.library.path` góp phần xác định **nơi JVM tìm thư viện theo tên**; `System.loadLibrary` yêu cầu nạp bằng **tên logic**, còn `System.load` nhận **đường dẫn tuyệt đối tới tệp**. Nạp thành công cuối cùng còn phụ thuộc hệ điều hành, kiến trúc, binary dependencies và native symbol.
