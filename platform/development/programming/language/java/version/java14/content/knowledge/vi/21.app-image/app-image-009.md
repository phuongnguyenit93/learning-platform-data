# Cấu trúc tài nguyên, thư viện native và đường dẫn khi phân phối app image

## 1. Bối cảnh: ứng dụng đã chạy trong IDE nhưng chưa chắc chạy sau khi đóng gói

Khi chạy bằng IDE hoặc `java -jar`, bạn có thể quen với các đường dẫn như `src/main/resources`, `target/classes`, thư mục hiện tại và các DLL/`.so` đã cài trên máy phát triển. Nhưng sau khi tạo **application image** bằng `jpackage`, người dùng có một cây thư mục riêng gồm **launcher**, **mã ứng dụng**, **runtime Java đi kèm**, các tài nguyên và thư viện native mà ứng dụng thực sự cần.

Mục tiêu của bài không chỉ là nhận biết tên các thư mục, mà là **định vị đúng từng loại dữ liệu khi chương trình chạy từ bản phân phối**:

- **Resource trong JAR/module:** ảnh, template, văn bản mặc định, cấu hình read-only được đóng cùng mã.
- **Resource ngoài JAR:** file cấu hình mặc định, mẫu dữ liệu hoặc file cần người vận hành xem, được đưa vào app image như file độc lập.
- **Native library:** `.dll` trên Windows, `.so` trên Linux, `.dylib` trên macOS; phải tương thích OS/CPU và có cách nạp phù hợp.
- **Runtime đi kèm:** các module và thư viện thuộc JVM được `jpackage`/`jlink` tạo ra hoặc sao chép.
- **Dữ liệu ghi lúc chạy:** log, cache, database cục bộ, preference và file người dùng; **không nên ghi vào thư mục cài đặt**.

Một sai lầm điển hình:

~~~java
// Dễ chạy trong IDE nhưng thường sai khi đóng gói:
Path config = Path.of("src/main/resources/config.properties");
~~~

`src/main/resources` là **thư mục trong dự án nguồn**, không phải một đường dẫn bắt buộc có trên máy người dùng. Tương tự, dựa vào `System.getProperty("user.dir")` để tìm file cạnh launcher có thể sai: working directory có thể thay đổi khi mở bằng shortcut, service, terminal hoặc file association.

### Phiên bản Java còn áp dụng

`jpackage` được giới thiệu ở Java 14 dưới dạng incubating và trở thành **công cụ chính thức từ Java 16 (JEP 392)**. Bài sử dụng cách đóng gói **ổn định trên JDK 17+**, không dùng module incubating hay cờ preview lịch sử. Những layout dưới đây dựa trên hướng dẫn Oracle `jpackage` hiện hành; các thư mục nội bộ chi tiết có thể thay đổi theo phiên bản công cụ.

## 2. Cấu trúc app image theo hệ điều hành

Theo hướng dẫn Oracle, app image thường có dạng đại diện như sau.

### 2.1. Windows

~~~text
ResourceLayoutDemo/
├── ResourceLayoutDemo.exe     # Native launcher của ứng dụng
├── app/
│   ├── ResourceLayoutDemo.cfg # Cấu hình launcher do jpackage tạo
│   ├── resource-layout-demo.jar
│   ├── config/
│   │   └── defaults.properties
│   └── native/
│       └── ...                # DLL của app, nếu có
└── runtime/
    ├── bin/
    ├── conf/
    ├── lib/
    │   └── modules
    └── ...
~~~

Đây là **sơ đồ minh họa**, không phải danh sách đầy đủ mọi file. Một ứng dụng bình thường có thể chứa thêm các JAR, resource, file cấu hình, bản quyền và các thành phần khác. Không nên hard-code cấu trúc chi tiết chưa được tài liệu hóa thành hợp đồng API bất biến.

### 2.2. Linux

~~~text
myapp/
├── bin/
│   └── ResourceLayoutDemo   # Launcher
└── lib/
    ├── app/
    │   ├── resource-layout-demo.jar
    │   ├── config/
    │   └── native/
    └── runtime/
        └── ...
~~~

### 2.3. macOS

~~~text
ResourceLayoutDemo.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/
    │   └── ResourceLayoutDemo
    ├── Resources/
    ├── app/
    │   ├── resource-layout-demo.jar
    │   ├── config/
    │   └── native/
    └── runtime/
        └── ...
~~~

Các sơ đồ Linux/macOS trên là **mô hình thư mục tiêu biểu**, không phải một chương trình đã chạy trong bài. Trên macOS, vị trí, nội dung bundle, quyền thực thi và chữ ký mã đặc biệt quan trọng khi phân phối.

### 2.4. Những thư mục cùng tên nhưng vai trò khác nhau

| Thành phần | Mục đích | Nên sửa khi ứng dụng chạy? |
| --- | --- | --- |
| Launcher `.exe` / `bin/name` / `Contents/MacOS/name` | Khởi động JVM và main class/module với cấu hình đã tạo | **Không** |
| `app/` (hoặc `lib/app/`) | JAR/modules ứng dụng, cấu hình mặc định và asset ngoài JAR | Thông thường **không** |
| `runtime/` | Java runtime image gồm modules/native files của JVM | **Không** |
| `*.cfg` của launcher | Các tham số ứng dụng và JVM do `jpackage` tạo | Chỉ thay qua quy trình build/phân phối có quản lý |
| Thư mục dữ liệu người dùng | Log, cache, dữ liệu, file cấu hình có thể sửa | **Có**, theo quyền và chính sách ứng dụng |

**Tự chứa (*self-contained*) không có nghĩa là một file thực thi độc lập duy nhất.** Trên Windows, chỉ chép riêng `ResourceLayoutDemo.exe` ra khỏi image mà không mang `app`/`runtime` có thể làm launcher không hoạt động.

## 3. Phân loại resource trước khi quyết định đường dẫn

Không có một cách đọc file dùng được cho mọi loại resource. Hãy chọn theo **vòng đời của dữ liệu**.

| Câu hỏi | Resource điển hình | Vị trí khuyến nghị | Cách đọc |
| --- | --- | --- | --- |
| File có đi cùng phiên bản mã và không cần sửa sau cài đặt? | Template HTML, icon, SQL mẫu, messages | **Trong JAR hoặc module** | `Class.getResourceAsStream` |
| Cần nằm ngoài JAR nhưng là cấu hình mặc định của bản phát hành? | `defaults.properties`, file từ khóa, sample data | Dưới **app payload** từ `--input` | `Files.newInputStream` với path từ cấu hình launcher |
| Là thư viện máy dùng JNI/JNA? | DLL/`.so`/`.dylib` | Thư mục native thuộc app payload, đúng OS/CPU | `System.load` với path tuyệt đối hoặc `loadLibrary` theo search path |
| Sẽ thay đổi trong thời gian sử dụng? | Preferences, database, cache, log, file tải về | **Thư mục ghi được của người dùng/ứng dụng** | `Files`/API lưu trữ tùy nền tảng |
| Là module Java của JVM? | `java.base`, `java.desktop`, `java.sql` | **Runtime image** | JVM quản lý, ứng dụng không đọc như resource riêng |
| Là icon/metadata của gói cài đặt? | Icon của launcher, metadata installer, template packaging | Tùy chọn `jpackage`, chẳng hạn `--icon`/`--resource-dir` | Công cụ đóng gói xử lý tại build time |

**Quy tắc chung:** Nếu file phải còn dùng được sau khi ứng dụng nâng cấp và có thể do người dùng chỉnh sửa, **đừng coi nó là resource bất biến bên trong JAR hoặc thư mục runtime**.

## 4. Tài nguyên trong JAR: đọc bằng classpath, không dùng `src/main/resources`

Trong dự án Java thông thường:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/App.java
    └── resources/
        └── assets/
            └── banner.txt
~~~

Build tool như Maven/Gradle sẽ đưa resource thành các entry trong JAR đầu ra theo cấu hình. Khi chạy bằng `jpackage`, JAR được mang vào app image; **resource bên trong JAR vẫn truy cập bằng class loader**, không phải bằng file path của mã nguồn.

Ví dụ class `com.example.App`:

~~~java
try (InputStream in = App.class.getResourceAsStream("/assets/banner.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing assets/banner.txt in JAR");
    }
    String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(content.strip());
}
~~~

Đây là **đoạn code minh họa**, cần import `java.io.InputStream` và `java.nio.charset.StandardCharsets`; lớp `App` phải được đặt trong chương trình thích hợp.

### 4.1. Ý nghĩa dấu `/` ở đầu

- `App.class.getResourceAsStream("/assets/banner.txt")`: đường dẫn resource **từ gốc classpath/module** tương ứng.
- `App.class.getResourceAsStream("banner.txt")`: đường dẫn **tương đối theo package của `App`**.
- `ClassLoader.getResourceAsStream("assets/banner.txt")`: thông thường dùng tên resource **không có dấu `/` đầu**, và chịu quy tắc tìm kiếm của class loader.

Với named modules (JPMS), việc truy cập resource còn chịu quy tắc module/resource encapsulation phù hợp. Đừng mặc định mọi resource từ module khác đều có thể đọc qua class loader mà không có khai báo và mức mở package thích hợp.

### 4.2. Resource URL có thể là `jar:`, không phải file path

~~~java
URL url = App.class.getResource("/assets/banner.txt");
~~~

Khi ứng dụng được đóng JAR, URL có thể có dạng `jar:file:...!/assets/banner.txt`. Vì vậy, phương pháp:

~~~java
// Dễ sai: resource trong JAR không nhất thiết là file hệ thống.
Path path = Path.of(url.toURI());
~~~

có thể gây lỗi nếu resource tồn tại trong một JAR filesystem chưa được mount hoặc một kiểu URL không tương thích. Khi chỉ cần **đọc nội dung**, ưu tiên `getResourceAsStream`; không yêu cầu resource phải có `Path` thật trên ổ đĩa.

Nếu thư viện bên ngoài bắt buộc nhận một file path thực, cần có thiết kế **trích xuất resource** tới một vị trí được phép ghi hoặc **phân phối resource ngoài JAR** ngay từ đầu; bảo toàn quyền, kiểm soát phiên bản và không tự trích xuất file thực thi không đáng tin.

### 4.3. Kiểm tra đúng nội dung JAR trước khi phát hành

~~~bash
jar --list --file input/resource-layout-demo.jar
~~~

Kiểm tra có `assets/banner.txt` cùng các class. Nếu resource bị thiếu, đó thường là vấn đề ở **bước build JAR**, không phải vấn đề `jpackage` không đọc được đường dẫn đến source.

Các tệp trong JAR được triển khai cùng ứng dụng và thường **read-only** theo ý nghĩa phân phối; không mở JAR để ghi log/cập nhật cấu hình tại runtime.

## 5. Resource độc lập ngoài JAR: dùng `--input`

`jpackage --input DIR` lấy thư mục có các file cần đóng gói. Với non-modular app, các file từ `DIR` được đặt trong **app payload** của image. Có thể tổ chức:

~~~text
input/
├── resource-layout-demo.jar
├── config/
│   └── defaults.properties
├── native/
│   └── README.txt
└── data/
    └── sample.csv
~~~

Sau packaging, trên Windows tương ứng thường là:

~~~text
ResourceLayoutDemo/
└── app/
    ├── resource-layout-demo.jar
    ├── config/defaults.properties
    ├── native/README.txt
    └── data/sample.csv
~~~

Các file này **không tự trở thành classpath resources** chỉ vì nằm cùng thư mục `app`. Nếu đọc một file độc lập bằng `Files`, bạn cần một **đường dẫn hệ thống thực** tới file đó.

### 5.1. Đừng nhầm ba tùy chọn

| Tùy chọn | Trách nhiệm |
| --- | --- |
| `--input` | Đưa JAR/modules/resource files của ứng dụng vào app payload |
| `--app-content` | Thêm file/thư mục vào application payload theo quy tắc nền tảng; cần kiểm tra vị trí sinh ra |
| `--resource-dir` | Ghi đè **tài nguyên của chính công cụ đóng gói**, như template/icon installer; **không phải cơ chế chung để đọc tài nguyên runtime của ứng dụng** |

`--app-content` và cách đặt thêm dữ liệu (đặc biệt khi tạo macOS bundle) cần kiểm tra theo hướng dẫn đúng JDK/nền tảng. Đối với resource dưới `app` mà chương trình chủ động đọc, `--input` thường dễ dự đoán và kiểm thử hơn.

`--icon` chọn icon của launcher/bundle ở build time. Nó không đồng nghĩa đường dẫn ảnh mà ứng dụng Java đọc trong khi chạy.

## 6. Làm sao xác định app payload directory khi launcher chạy?

Đây là điểm rất dễ nhầm: Java **không có một biến chuẩn chung tên `APPDIR`** tự động xuất hiện trong `System.getenv`. `jpackage` launcher hỗ trợ **token thay thế đặc biệt `$APPDIR`** trong các tham số launcher, bao gồm `--java-options` và `--arguments` theo tài liệu hiện hành.

Cách rõ ràng là **truyền vị trí app payload vào một Java system property tại build time**:

~~~powershell
jpackage --type app-image --name ResourceLayoutDemo --input input --main-jar resource-layout-demo.jar --main-class ResourceLayoutDemo --java-options '-Ddemo.app.dir=$APPDIR' --win-console --dest release
~~~

**Lệnh trên dùng PowerShell trên Windows.** Dấu nháy đơn quanh `'-Ddemo.app.dir=$APPDIR'` khiến PowerShell không thay `$APPDIR` thành biến PowerShell. Token đó được **launcher `jpackage` thay bằng app directory tại thời điểm chạy**.

Trong Java:

~~~java
String configured = System.getProperty("demo.app.dir");
if (configured == null || configured.isBlank()) {
    throw new IllegalStateException("Missing demo.app.dir");
}
Path appDir = Path.of(configured).toAbsolutePath().normalize();
Path defaultConfig = appDir.resolve("config").resolve("defaults.properties");
~~~

Đây là **đoạn minh họa** với import `java.nio.file.Path`. Tại runtime, chương trình nhận đúng đường dẫn tới **app payload**, không phải đoán theo working directory hoặc ghép `../app` thủ công.

### 6.1. Phân biệt các đường dẫn

| Giá trị | Ý nghĩa | Có nên dùng để tìm `config/defaults.properties` trong app image? |
| --- | --- | --- |
| `System.getProperty("user.dir")` | **Working directory** của tiến trình | **Không nên**: phụ thuộc cách mở app |
| `System.getProperty("user.home")` | Home directory của người dùng | Dành cho dữ liệu người dùng, không phải vị trí JAR đã cài |
| `System.getProperty("java.home")` | Runtime Java đang chạy | **Không**: trỏ vào JVM runtime, không phải app payload |
| `System.getProperty("demo.app.dir")` khi launcher truyền `$APPDIR` | Vị trí app payload theo launcher | **Có**: cho external resources đã đóng qua `--input` |
| `Class.getResourceAsStream` | Nội dung nhúng vào classpath/module | **Có**, nếu resource nằm bên trong JAR/module |
| `System.getenv("PATH")` | OS search path | Không phải cách nhận diện chắc chắn vị trí app |

**Không dùng `System.getenv("APPDIR")` như thể `jpackage` luôn tạo biến môi trường này.** `$APPDIR` là token do launcher thay thế khi truyền tham số; nó không phải một biến môi trường chuẩn Java.

### 6.2. Các token launcher khác

Tài liệu `jpackage` hiện hành còn mô tả `$BINDIR` và `$ROOTDIR` trong các ngữ cảnh launcher tương ứng. Tuy nhiên, không nên tự suy đoán mọi token là environment variable hoặc có cùng layout trên mọi OS. Với dữ liệu bên trong `--input`, **`$APPDIR` là lựa chọn đúng mục đích và đã được kiểm chứng trong ví dụ**.

Đối với người dùng chạy bằng `java -jar` trong giai đoạn phát triển, có thể truyền cùng property tường minh:

~~~powershell
$appInput = (Resolve-Path input).Path
java "-Ddemo.app.dir=$appInput" -jar input/resource-layout-demo.jar
~~~

Nhờ đó, code Java không cần đoán đang chạy từ IDE, JAR hay app image. **Nhiệm vụ xác định vị trí được đặt tại entrypoint/launcher**, giúp kiểm thử và bảo trì rõ ràng hơn.

## 7. Native library: bản chất và vị trí trong bản phân phối

Một Java application có thể gọi mã native qua **JNI** hoặc các thư viện/framework khác. Dù Java bytecode có thể đa nền tảng, native library **không tự đa nền tảng**:

| Hệ điều hành | Tên file ví dụ cho library `samplemath` | Yêu cầu cơ bản |
| --- | --- | --- |
| Windows | `samplemath.dll` | Đúng Windows/architecture và phụ thuộc DLL |
| Linux | `libsamplemath.so` | Đúng ELF architecture, ABI và thư viện `.so` phụ thuộc |
| macOS | `libsamplemath.dylib` | Đúng Mach-O architecture, code signing/loader rules nếu có |

Java hỗ trợ:

~~~java
System.mapLibraryName("samplemath");
~~~

Hàm này trả tên file native theo quy tắc của platform mà **JVM đang chạy**, rất hữu ích khi tạo path. Nó **không biên dịch native library**, **không kiểm tra ABI** và **không xác nhận file đó tồn tại**.

### 7.1. Đặt native libraries của app ở đâu?

Một cấu trúc dễ kiểm soát:

~~~text
input/
├── resource-layout-demo.jar
├── config/defaults.properties
└── native/
    ├── samplemath.dll         # Trong bản phát hành Windows thật
    └── các DLL phụ thuộc nếu hợp đồng loader yêu cầu
~~~

**Không tự ý copy DLL của ứng dụng vào `runtime/lib`** của JDK chỉ để nó được nạp. `runtime` thuộc runtime Java đã link, nên được giữ nguyên như thành phần do JDK/jpackage tạo. Native libraries riêng nên được quản lý trong **app payload**, phân phối cùng đúng OS/architecture và được nạp theo chính sách rõ ràng.

### 7.2. `System.load(String)` và `System.loadLibrary(String)`

**`System.load`** nhận **đường dẫn tuyệt đối** tới thư viện native:

~~~java
Path library = appDir.resolve("native")
        .resolve(System.mapLibraryName("samplemath"))
        .toAbsolutePath().normalize();
System.load(library.toString());
~~~

Đây là **đoạn code minh họa**, chỉ chạy khi bạn đã đưa **native binary thật và tương thích** vào đúng vị trí. Không dùng một file `.txt` hoặc DLL giả để thử `System.load`; như vậy tất nhiên sẽ lỗi. Cách dùng đường dẫn tuyệt đối thích hợp khi bạn biết vị trí thư viện trong app payload.

**`System.loadLibrary`** nhận **tên cơ sở**, không có path, tiền tố `lib` hay extension:

~~~java
System.loadLibrary("samplemath");
~~~

JVM và loader sẽ tìm library theo các quy tắc platform/runtime, chịu ảnh hưởng của `java.library.path` và các cơ chế tìm thư viện của hệ điều hành. Lệnh sau **không hợp lệ theo hợp đồng `loadLibrary`**:

~~~java
// KHÔNG ĐÚNG: loadLibrary không nhận path + extension.
// System.loadLibrary("native/samplemath.dll");
~~~

Nếu muốn dùng `loadLibrary`, có thể truyền JVM option khi đóng gói:

~~~powershell
jpackage --type app-image --name ResourceLayoutDemo --input input --main-jar resource-layout-demo.jar --main-class ResourceLayoutDemo --java-options '-Djava.library.path=$APPDIR/native' --win-console --dest release
~~~

Đây là **mẫu cấu hình**, chưa tự tạo hay xác minh bất kỳ DLL nào. `java.library.path` là đường tìm kiếm cho native library theo Java; **không đảm bảo tất cả transitive dependencies của library đều được loader OS tìm ra**. Với ví dụ bài học, `System.load` và path tuyệt đối thường dễ kiểm soát hơn.

### 7.3. JNI cần khớp những gì?

Một native DLL/`.so`/`.dylib` hợp lệ phải tương thích với:
- Hệ điều hành/CPU: ví dụ Windows x64 **không thể** dùng trực tiếp `.so` Linux hoặc DLL ARM khác kiến trúc.
- JNI symbol/signature và quy ước gọi của class/method hoặc cơ chế `RegisterNatives`.
- Phụ thuộc dynamic loader: MSVC runtime, C/C++ runtime, thư viện con và các phiên bản ABI phù hợp.
- Chính sách bảo mật: quyền đọc/chạy, code signing/notarization trên các môi trường yêu cầu, provenance của binary.
- Phiên bản Java/JNI/FFM mà ứng dụng chọn sử dụng.

Tệp native có thể tồn tại ở đúng path nhưng **`System.load` vẫn ném `UnsatisfiedLinkError`** nếu architecture sai, thư viện phụ thuộc không tìm thấy hoặc binary không phù hợp.

### 7.4. Đừng coi `java.library.path` là toàn bộ OS loader path

Native library A có thể phụ thuộc library B. Java tìm thấy A nhưng loader của Windows/Linux/macOS không tìm thấy B, khi đó vẫn lỗi.

Các điểm cần xem theo nền tảng:
- **Windows:** DLL dependency resolution, thư mục application/module và chính sách search path của OS.
- **Linux:** ELF shared objects, `RPATH`/`RUNPATH`, `LD_LIBRARY_PATH` trong phạm vi phù hợp và phiên bản libc/ABI.
- **macOS:** `@rpath`/`@loader_path`/`@executable_path`, chữ ký mã/hardened runtime và bundle rules.

Đừng sửa `PATH` hoặc `LD_LIBRARY_PATH` toàn cục một cách tùy tiện như giải pháp đầu tiên. Thay vào đó, xây đúng native artifact, test trên OS đích và cấu hình **search paths có chủ đích, tối thiểu**.

### 7.5. Nếu native library nằm bên trong JAR?

`System.load` yêu cầu một **file native có thể được OS loader mở theo path**, không tự động giải nén một JAR entry. Nếu bạn để `samplemath.dll` dưới `assets/` trong JAR thì việc nhận InputStream của nó **không đồng nghĩa** có path để `System.load`.

Có hai hướng:
1. **Ưu tiên:** phân phối binary native ngoài JAR, ví dụ dưới `app/native`, rồi nạp từ path đã biết.
2. **Khi thật sự cần:** trích xuất native binary từ JAR tới thư mục ghi được, có quản lý phiên bản, kiểm tra integrity và cleanup, rồi nạp. Cách thứ hai cần thiết kế bảo mật/cạnh tranh/permissions cẩn thận; không đơn giản viết file vào thư mục cài đặt.

## 8. Resource read-only và dữ liệu cần ghi lúc chạy

Khi cài một app bằng installer, thư mục cài đặt có thể là nơi người dùng **không có quyền ghi**, ví dụ dưới `Program Files` trên Windows hoặc các vị trí ứng dụng được bảo vệ ở macOS/Linux. Kể cả app image dạng thư mục của bạn có thể ghi được trên máy dev, điều đó **không đảm bảo quyền ghi ở mọi máy đích**.

### 8.1. Những dữ liệu không nên ghi vào app/runtime

- `application.log`, file crash dump tùy ứng dụng.
- Database SQLite hoặc file dữ liệu có thay đổi.
- User preferences, token đăng nhập và các giá trị cấu hình theo người dùng.
- Cache ảnh/HTTP, dữ liệu tải về, tệp tạm.
- File do người dùng tạo/chỉnh sửa.

Nếu ghi trực tiếp vào `app/config/defaults.properties`, installer update có thể ghi đè thay đổi; nhiều người dùng trên cùng máy cũng có thể cùng tranh quyền ghi một file.

### 8.2. Vị trí dữ liệu theo OS

| OS | Vị trí điển hình cho dữ liệu/cấu hình ứng dụng | Lưu ý |
| --- | --- | --- |
| Windows | `%APPDATA%\\Vendor\\App` cho dữ liệu roaming, `%LOCALAPPDATA%\\Vendor\\App` cho dữ liệu chỉ lưu cục bộ | Chọn đúng loại dữ liệu và scope người dùng |
| macOS | `~/Library/Application Support/App` | Theo conventions của macOS; cache/log có vị trí riêng |
| Linux | `$XDG_CONFIG_HOME/app` hoặc `~/.config/app` cho config; `$XDG_DATA_HOME/app` hoặc `~/.local/share/app` cho data | Tôn trọng biến môi trường XDG nếu có và hợp lệ |

Đây là **các quy ước nền tảng**, không phải API path duy nhất mà Java tự trả về. Trong code thực tế, có thể có helper tạo path theo OS và policy sản phẩm. `user.home` là fallback thường dùng cho demo nhỏ, không thay thế tự động mọi quy ước ứng dụng desktop.

### 8.3. Có thể gắn tên đường dẫn ra ngoài bằng config

Thay vì hard-code, ứng dụng có thể nhận:

~~~java
String configRoot = System.getProperty("demo.user.config.dir");
if (configRoot != null) {
    Path userConfig = Path.of(configRoot).resolve("user.properties");
    // Kiểm tra quyền, tồn tại và nội dung trước khi đọc.
}
~~~

Đây là **đoạn minh họa**, cần import `java.nio.file.Path`. Phân phối có thể quyết định một path cụ thể theo người dùng khi chạy. Đừng nhúng private data vào JAR rồi tưởng người dùng không xem được: nội dung package có thể bị trích xuất/đọc.

### 8.4. Resource mặc định và override theo người dùng

Một mẫu thiết kế thường dùng:
1. **Defaults read-only** phân phối dưới `app/config/defaults.properties`.
2. **User override** lấy từ thư mục data/config bên ngoài app image.
3. Khi khởi động, đọc defaults trước, đọc override nếu có sau, rồi kiểm tra schema/giá trị.
4. Chỉ ghi lại vào **user override**, không sửa default trong app image.
5. Khi nâng cấp, nếu cần migration, thực hiện có versioning/backup và báo lỗi rõ.

Mẫu này giúp installer có thể thay bản mặc định mà vẫn giữ dữ liệu cá nhân hợp lệ.

## 9. Ví dụ đầy đủ đã kiểm chứng: resource trong JAR + config ngoài + thư mục native

Ví dụ này **không cần DLL thực** để chạy: nó kiểm tra đường dẫn và cách ánh xạ tên thư viện trên Windows. Mục tiêu là chứng minh **hai loại resource** được tìm đúng sau `jpackage`, bất kể working directory.

### 9.1. Chuẩn bị cấu trúc source và input

Tạo bố cục:

~~~text
project/
├── ResourceLayoutDemo.java
├── classes/
│   └── assets/
│       └── banner.txt
├── input/
│   ├── config/
│   │   └── defaults.properties
│   └── native/
│       └── README.txt
└── release/
~~~

`classes/assets/banner.txt` sẽ được đóng **bên trong JAR**. `input/config/defaults.properties` và `input/native/README.txt` là **file ngoài JAR**. `README.txt` chỉ đánh dấu vị trí dành cho binary native **trong bản phân phối thật** — **không phải DLL**, và chương trình này **không gọi `System.load`**.

### 9.2. Mã Java — `ResourceLayoutDemo.java`

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class ResourceLayoutDemo {
    private static String readClasspathResource() throws Exception {
        try (InputStream in = ResourceLayoutDemo.class
                .getResourceAsStream("/assets/banner.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing JAR resource");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        String configured = System.getProperty("demo.app.dir");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException("Missing demo.app.dir");
        }
        Path appDir = Path.of(configured).toAbsolutePath().normalize();

        Properties props = new Properties();
        try (InputStream in = Files.newInputStream(
                appDir.resolve("config").resolve("defaults.properties"))) {
            props.load(in);
        }

        String base = System.getenv("APPDATA");
        Path userData = (base != null && !base.isBlank())
                ? Path.of(base).resolve("ResourceLayoutDemo")
                : Path.of(System.getProperty("user.home"))
                      .resolve(".resource-layout-demo");

        System.out.println("JAR resource: " + readClasspathResource());
        System.out.println("External config: " + props.getProperty("mode"));
        System.out.println("APPDIR exists: " + Files.isDirectory(appDir));
        System.out.println("Native folder exists: "
                + Files.isDirectory(appDir.resolve("native")));
        System.out.println("Native filename: "
                + System.mapLibraryName("samplemath"));
        System.out.println("CWD differs from APPDIR: "
                + !Path.of("").toAbsolutePath().normalize().equals(appDir));
        System.out.println("User data outside APPDIR: "
                + !userData.toAbsolutePath().normalize().startsWith(appDir));
    }
}
~~~

**Giải thích:**
- `getResourceAsStream` tìm `assets/banner.txt` trong JAR mà không cần file path của JAR.
- `System.getProperty("demo.app.dir")` đến từ **launcher `jpackage`**, không phụ thuộc current directory.
- `defaults.properties` được mở như **file ngoài JAR** từ app payload.
- `System.mapLibraryName` trả tên file theo hệ điều hành; **chưa nạp native binary**.
- `APPDATA` hoặc `user.home` trong demo chỉ dùng tính **vị trí dữ liệu người dùng**, không ghi file.
- Chương trình cố tình ném lỗi nếu không có `demo.app.dir`; điều này tốt hơn im lặng đọc sai `.`.

### 9.3. Tạo các file demo trên Windows PowerShell

Từ thư mục chứa `ResourceLayoutDemo.java`, chạy:

~~~powershell
New-Item -ItemType Directory -Force -Path classes/assets,input/config,input/native,release | Out-Null

$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'classes/assets/banner.txt'),
    'Hello from JAR',
    $utf8
)
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'input/config/defaults.properties'),
    'mode=packaged',
    $utf8
)
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'input/native/README.txt'),
    'Place matching native libraries here.',
    $utf8
)
~~~

Dùng UTF-8 không BOM cho dữ liệu demo giúp kết quả không lẫn ký tự BOM ở đầu file. Ví dụ `Properties.load(InputStream)` đọc một file cấu hình ASCII đơn giản; nếu cần Unicode tiếng Việt với file `.properties`, hãy chọn encoding/`Reader` phù hợp thay vì đoán cách giải mã.

### 9.4. Biên dịch và tạo JAR chứa resource

~~~powershell
javac -encoding UTF-8 --release 17 -d classes ResourceLayoutDemo.java

jar --create --file input/resource-layout-demo.jar --main-class ResourceLayoutDemo -C classes .

jar --list --file input/resource-layout-demo.jar
~~~

Hãy xác nhận output `jar --list` có `ResourceLayoutDemo.class` và `assets/banner.txt`. `-C classes .` đưa toàn bộ nội dung đã biên dịch và resource trong `classes` vào JAR.

Để kiểm thử trực tiếp từ JAR **trước khi đóng gói**, truyền property tường minh:

~~~powershell
$appInput = (Resolve-Path input).Path
java "-Ddemo.app.dir=$appInput" -jar input/resource-layout-demo.jar
~~~

### 9.5. Tạo runtime và app image

`jdeps` cho ví dụ đơn giản này trả `java.base`, vì nó chỉ dùng core APIs từ `java.base`:

~~~powershell
jdeps --print-module-deps input/resource-layout-demo.jar
~~~

Kết quả đã kiểm chứng:

~~~text
java.base
~~~

Tạo runtime tối giản:

~~~powershell
jlink --add-modules java.base --strip-debug --no-man-pages --no-header-files --output runtime
~~~

Đây là lựa chọn **đủ cho ví dụ này**, không phải gợi ý dùng `java.base` đơn lẻ cho mọi app. Với GUI, JDBC, logging, ServiceLoader/providers hoặc các module khác, cần dùng tập module phù hợp, kiểm thử và có thể thêm `--bind-services`.

Tạo app image Windows và truyền `$APPDIR` cho Java:

~~~powershell
jpackage --type app-image --name ResourceLayoutDemo --input input --main-jar resource-layout-demo.jar --main-class ResourceLayoutDemo --runtime-image runtime --java-options '-Ddemo.app.dir=$APPDIR' --win-console --dest release
~~~

**Điểm dễ sai nhất trong PowerShell:** Dùng **single quotes** quanh `'-Ddemo.app.dir=$APPDIR'`. Nếu để PowerShell thay `$APPDIR` thành biến của shell quá sớm, launcher sẽ không còn token cần mở rộng vào thời điểm chạy.

### 9.6. Chạy bản đã đóng gói

Từ thư mục project — **khác thư mục app payload** — chạy:

~~~powershell
.\release\ResourceLayoutDemo\ResourceLayoutDemo.exe

Test-Path .\release\ResourceLayoutDemo\app\config\defaults.properties
Test-Path .\release\ResourceLayoutDemo\app\native\README.txt
Test-Path .\release\ResourceLayoutDemo\runtime\lib\modules
~~~

**Stdout chính xác đã kiểm chứng trên Windows với JDK hỗ trợ `jpackage`:**

~~~text
JAR resource: Hello from JAR
External config: packaged
APPDIR exists: true
Native folder exists: true
Native filename: samplemath.dll
CWD differs from APPDIR: true
User data outside APPDIR: true
~~~

Ba lệnh `Test-Path` đều trả `True` trên môi trường kiểm chứng. App image còn có `ResourceLayoutDemo.exe` và `app/resource-layout-demo.jar`.

**Giới hạn kết luận của ví dụ:** Ta đã chứng minh `jpackage` đặt resource ngoài JAR vào `app`, launcher truyền đúng app directory, resource nhúng được đọc và runtime đi kèm tồn tại. Ta **chưa** biên dịch hay nạp một DLL `samplemath.dll` thật; `Native filename: samplemath.dll` chỉ là kết quả của `System.mapLibraryName`.

### 9.7. Vì sao ví dụ không dùng `user.dir` để mở config?

Ở lần kiểm chứng, working directory vẫn là project folder trong khi `appDir` trỏ tới image `release/ResourceLayoutDemo/app`. Do đó:

~~~java
Path wrong = Path.of("config/defaults.properties");
~~~

sẽ dựa vào `user.dir`, **không chắc** đọc được file thuộc app image. Cách đúng ở đây là:

~~~java
Path correct = appDir.resolve("config/defaults.properties");
~~~

Trong ứng dụng thực, người dùng có thể mở từ Start Menu, desktop shortcut hoặc thư mục bất kỳ. Thiết kế không phụ thuộc working directory giúp tránh lỗi “chạy bằng terminal được, double-click không chạy”.

### 9.8. Tại sao cần kiểm thử cả source JAR và packaged launcher?

- Chạy `java -jar` cho biết **JAR có resource nhúng** và logic Java đúng.
- Chạy launcher từ app image kiểm tra **path substitution**, cấu trúc `app`, JVM options và bundled runtime.
- Kiểm tra trên một máy **không cài Java hệ thống** mới xác nhận phân phối thật sự không vô tình dựa vào JDK của developer.
- Với native library thật, cần kiểm tra **kiến trúc, các library phụ thuộc và chính sách ký mã** trên OS đích.

Một bài smoke test kiểm tra mỗi dòng `App started` thường **không đủ** để phát hiện lỗi thiếu icon, cấu hình, file mẫu hoặc native library chỉ dùng ở chức năng ít gặp.

## 10. Khi app có DLL/`.so` thật: quy trình thêm vào package

Giả sử ứng dụng có thư viện native `samplemath` đã được build riêng cho **Windows x64**:

~~~text
input/
├── resource-layout-demo.jar
├── config/defaults.properties
└── native/
    ├── samplemath.dll
    └── các binary phụ thuộc nếu cần
~~~

Quy trình:

1. Xây dựng thư viện native bằng **toolchain phù hợp OS/CPU**; kiểm tra tên exports/JNI signatures hoặc API FFI được sử dụng.
2. Đặt file trong `input/native` và bảo toàn cấu trúc cần thiết cho native loader.
3. Tạo `jpackage --type app-image ...` như phần 9.
4. Kiểm tra `app/native/samplemath.dll` **thật sự là native binary hợp lệ**, không phải placeholder.
5. Trong Java, xây path tuyệt đối từ `demo.app.dir` và gọi `System.load(...)`.
6. Chạy một **native operation thật** trong test, không chỉ `Files.exists`.
7. Kiểm thử trên OS/architecture đích không phụ thuộc các native DLL tình cờ có trên máy developer.

Ví dụ **phần nạp library** (chưa thể chạy nếu chưa có DLL/`.so` thật):

~~~java
static void loadNativeMath(Path appDir) {
    Path library = appDir.resolve("native")
            .resolve(System.mapLibraryName("samplemath"))
            .toAbsolutePath().normalize();

    if (!Files.isRegularFile(library)) {
        throw new IllegalStateException(
                "Missing native library: " + library);
    }

    System.load(library.toString());
}
~~~

Đoạn method này cần import `java.nio.file.Path` và `java.nio.file.Files`, đặt trong một class. Nó chỉ kiểm tra file hiện diện trước khi thử load; **`System.load` vẫn có thể thất bại** vì ABI hay phụ thuộc hệ thống.

### 10.1. Cách kiểm tra lỗi native theo thông báo

| Lỗi | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `UnsatisfiedLinkError: no samplemath in java.library.path` | `loadLibrary` không tìm được tên thư viện | Kiểm tra tên library và search path |
| `UnsatisfiedLinkError` dù file tồn tại | OS/CPU sai, binary thiếu phụ thuộc hoặc JNI không khớp | Kiểm tra architecture, dependency scanner, logs |
| Windows báo thiếu dependent DLL | Library A có nhưng B phụ thuộc bị thiếu | Dùng công cụ kiểm tra DLL dependencies, xem cơ chế search path của OS |
| Linux báo `wrong ELF class` hoặc lỗi loader | ELF architecture/ABI không tương thích | Kiểm tra `file`, `ldd` và môi trường phát hành tin cậy |
| macOS từ chối nạp library | Signing/hardened runtime, library location, ABI | Xem log hệ thống, `codesign`, `otool`/`@rpath` |
| `NoSuchMethodError`/`ClassNotFoundException` khi mở tính năng dùng JNI wrapper | Java dependency thiếu hoặc phiên bản không đúng | Kiểm tra classpath/module path và JAR được đóng |
| Load thành công nhưng native call lỗi | Signature, ABI, memory safety hoặc code native | Thử nghiệm integration theo nền tảng, debug native |

**Cẩn trọng bảo mật:** Native library là **mã máy có quyền trong tiến trình**, không phải file dữ liệu vô hại. Chỉ phân phối binary đáng tin cậy, có kiểm tra nguồn gốc/chữ ký và cơ chế cập nhật; không tải DLL ngẫu nhiên theo input của người dùng.

## 11. Mọi thứ vẫn phải đúng trên các nền tảng khác nhau

### 11.1. Không tái sử dụng app image giữa OS

`jpackage` tạo launcher/runtime **phụ thuộc hệ điều hành**. Windows image không chạy trực tiếp trên Linux/macOS; phải tạo artifact thích hợp **trên nền tảng đích**, đúng architecture.

Việc tên file và vị trí launcher khác nhau cũng khiến một đường dẫn hard-code kiểu:

~~~java
Path library = Path.of("C:\\Program Files\\MyApp\\app\\native\\samplemath.dll");
~~~

không phù hợp như một quy tắc chung: khác OS, khác vị trí cài đặt, và người dùng có thể lựa chọn install path khác.

**Sửa:** xác định app directory từ launcher hoặc một cấu hình ổn định, dùng `Path.resolve` và `System.mapLibraryName`. Phần quản lý installation paths và OS loader phải được test theo từng platform.

### 11.2. Linux/macOS còn có quyền và chính sách binary

- Linux: file launcher phải có quyền execute, native `.so` phải hợp ABI của distro, kiểm tra thư viện phụ thuộc.
- macOS: bundle contents, library signing/notarization/hardened runtime phải hợp chính sách phát hành. Không thêm tùy ý file vào bundle đã ký mà không kiểm tra lại chữ ký.
- Windows: DLL architecture, dependency resolution và phân phối runtime phụ thuộc VC++ nếu native build có nhu cầu.

**Không tự đổi đuôi `.dll` thành `.so`** rồi mong library chạy: binary phải được build cho đúng nền tảng.

### 11.3. Các app resources nên được kiểm thử sau cài đặt

Ngay cả khi kiểm tra app image thành công, installer có thể thay đổi install root, file permissions hoặc cách đăng ký shortcut. Vì vậy kiểm thử các bước:
1. Tạo app image.
2. Chạy launcher từ image.
3. Tạo installer theo OS.
4. Cài vào vị trí tiêu chuẩn và, nếu hỗ trợ, vị trí có dấu cách/Unicode.
5. Khởi động bằng shortcut hoặc menu.
6. Đọc classpath resource và external config.
7. Thử native functionality thật khi có.
8. Tạo log/cache trong **user data dir**.
9. Nâng cấp bản mới và xác nhận dữ liệu người dùng không bị ghi đè.
10. Gỡ ứng dụng theo chính sách, không vô tình xóa dữ liệu người dùng nếu không được yêu cầu.

## 12. Những lỗi phổ biến

### Lỗi A — Dùng `src/main/resources` ở runtime

~~~java
// Dễ sai trong app image:
Path path = Path.of("src/main/resources/assets/banner.txt");
~~~

**Sửa:** nhúng resource vào JAR rồi dùng `getResourceAsStream("/assets/banner.txt")`, hoặc đưa resource ra `--input` và đọc qua `$APPDIR`.

### Lỗi B — `Path.of("config/defaults.properties")` dựa vào working directory

Khi người dùng mở bằng shortcut, `user.dir` không bảo đảm là thư mục chứa app. **Sửa:** nhận đường dẫn app payload từ launcher và `resolve("config/defaults.properties")`.

### Lỗi C — Gọi `getResourceAsStream` với file chỉ đặt cạnh JAR

Resource ngoài JAR **không tự nằm trong classpath**. **Sửa:** dùng `Files` với path của file ngoài JAR; hoặc cấu hình build đưa resource vào JAR nếu muốn classpath resource.

### Lỗi D — Coi URL `jar:` như file hệ thống

`getResource` trả URL, không bảo đảm chuyển trực tiếp thành `Path` bình thường. **Sửa:** đọc stream hoặc phân phối/extract file khi API đích bắt buộc cần path.

### Lỗi E — Ghi log/database vào `app` hoặc `runtime`

Có thể lỗi permission, bị ghi đè khi update và làm package khó tái lập. **Sửa:** dùng user data/config directory phù hợp OS.

### Lỗi F — Đặt DLL trong JAR rồi gọi `System.load` bằng tên resource

`System.load` cần path tuyệt đối tới native library; JAR entry không phải file native sẵn cho OS loader. **Sửa:** đóng library như file dưới `app/native` hoặc extract có kiểm soát.

### Lỗi G — Dùng `System.loadLibrary("native/samplemath.dll")`

`loadLibrary` nhận **tên cơ sở**, không nhận path/extension. **Sửa:** `loadLibrary("samplemath")` với search path phù hợp hoặc `System.load(absolutePath)`.

### Lỗi H — Tưởng `java.library.path` đủ cho DLL phụ thuộc

Thư viện A có thể nạp phụ thuộc B qua OS loader, với quy tắc tìm riêng. **Sửa:** kiểm tra toàn bộ dependency chain và loader rules trên OS đích.

### Lỗi I — Ghép tay path bằng `"\\\\"` hoặc `"/"` tùy tiện

Đường dẫn và normalization khác nhau giữa OS. **Sửa:** dùng `Path`/`resolve`; chỉ dùng format path có phân tách khi đúng với một ngữ cảnh cụ thể.

### Lỗi J — Lẫn `--resource-dir` với `--input`

`--resource-dir` là input để **tùy biến tài nguyên của công cụ đóng gói**, không phải thư mục resource ứng dụng được đọc tự động sau cài. **Sửa:** dùng `--input` cho app payload, `--icon` và `--resource-dir` đúng mục đích packaging.

### Lỗi K — Gửi riêng launcher, bỏ JAR/runtime

App image thường là **một cây thư mục**, không phải một file độc lập. **Sửa:** giữ toàn bộ thư mục hoặc tạo native installer đúng cấu trúc.

### Lỗi L — Kết luận native hoạt động vì `Files.exists` trả true

Một file mang đuôi `.dll` có thể không phải DLL hợp lệ hoặc sai architecture. **Sửa:** thực hiện `System.load` và test một native call thật trên máy đích.

### Lỗi M — Không kiểm tra tài nguyên khi tạo installer/update

Bản app image chạy được nhưng installer không chép đủ data, hoặc update xóa file cấu hình người dùng. **Sửa:** có integration tests sau cài và chính sách phân tách immutable defaults/user overrides.

## 13. Bài tập thực hành

### Bài 1 — Đọc icon trong JAR

Một ứng dụng đóng `assets/icon.png` vào JAR. Chương trình cần lấy bytes để hiển thị icon. Nên dùng `Path.of("src/main/resources/assets/icon.png")` hay `getResourceAsStream`?

**Đáp án:** Dùng resource stream của class/class loader, ví dụ `App.class.getResourceAsStream("/assets/icon.png")`. Nó hoạt động khi resource là entry trong JAR và không dựa vào dự án nguồn.

### Bài 2 — Tìm file config ngoài JAR

Bản Windows có:

~~~text
C:\\Apps\\Tool\\app\\config\\defaults.properties
~~~

Launcher truyền `-Dtool.app.dir=$APPDIR`. Viết code tìm config mà không hard-code install root.

**Đáp án:**

~~~java
Path appDir = Path.of(System.getProperty("tool.app.dir"));
Path config = appDir.resolve("config").resolve("defaults.properties");
~~~

Cần kiểm tra property khác null và file hợp lệ trước khi đọc; nếu dùng chung code giữa IDE và app image, truyền property tường minh ở môi trường phát triển.

### Bài 3 — Sai kiểu nạp DLL

~~~java
System.loadLibrary("native/samplemath.dll");
~~~

**Hỏi:** Vì sao sai và nên sửa thế nào?

**Đáp án:** `loadLibrary` nhận **base name** như `"samplemath"`, không chứa path/đuôi. Nếu biết thư viện nằm dưới `app/native`, dùng `System.load(appDir.resolve("native").resolve(System.mapLibraryName("samplemath")).toAbsolutePath().toString())`.

### Bài 4 — Phân loại file để lưu đúng chỗ

Sắp xếp: `app.jar`, `template.html` không sửa, `samplemath.dll`, `user.db`, `app.log`, các Java modules.

**Đáp án:**
- `app.jar` và template có thể đi trong **app payload**; template thường có thể nhúng vào JAR.
- `samplemath.dll` ở thư mục **app/native**, đúng OS/CPU.
- `user.db` và `app.log` ở **thư mục user/application data có quyền ghi**.
- Java modules ở **runtime image**, do JDK/linker quản lý.

### Bài 5 — Tại sao launcher chỉ chạy từ terminal?

Một app chạy khi developer đứng trong thư mục build, nhưng mở shortcut thì báo không thấy `config/defaults.properties`. Code đang dùng `Path.of("config/defaults.properties")`.

**Đáp án:** Code dùng **working directory**, trong khi shortcut có thể chọn working directory khác. Dùng `$APPDIR`/launcher property để lấy root của app payload hoặc nhúng resource vào JAR và đọc theo classpath.

### Bài 6 — Native library có file nhưng vẫn lỗi

`app/native/samplemath.dll` tồn tại, nhưng `System.load` ném `UnsatisfiedLinkError`. Nêu ít nhất bốn khả năng.

**Đáp án gợi ý:**
1. Binary sai CPU architecture.
2. Không phải DLL hợp lệ hoặc thiếu exports/JNI symbols tương ứng.
3. Thiếu DLL phụ thuộc hoặc C/C++ runtime.
4. Chính sách code signing/permissions từ chối.
5. App đang chạy bằng một runtime/OS không tương thích hoặc phụ thuộc JNI version khác.

Kiểm tra **file thật và dependency chain**, không chỉ file name và folder.

### Bài 7 — Cách đóng gói resource ngoài

Bạn có tệp `input/config/defaults.properties` và dùng `jpackage --input input` trên Windows. Sau packaging, nên dự kiến tìm file ở đâu?

**Đáp án:** Dưới **app payload directory** của image, thường là `<app-image>/app/config/defaults.properties` trên Windows. Dùng `$APPDIR` để xác định root đó ở runtime thay vì hard-code vị trí cài.

### Bài 8 — Build trên Windows để chạy Linux?

**Đáp án:** Không thể dùng nguyên Windows app image cho Linux. Cần build bằng `jpackage` trên nền tảng đích, dùng Linux runtime/native libraries phù hợp và kiểm thử quyền/ABI.

## 14. Checklist QA cho app image trước phát hành

- [ ] Phân biệt rõ **resource trong JAR/module**, **resource ngoài JAR**, **native binaries** và **dữ liệu người dùng**.
- [ ] Các file trong `--input` xuất hiện đúng trong **app payload**.
- [ ] Resource nhúng vào JAR có thể đọc bằng `getResourceAsStream`.
- [ ] Đường dẫn ngoài JAR được xác định từ **launcher property/`$APPDIR`**, không dựa vào `user.dir`.
- [ ] Không lẫn `--input`, `--app-content`, `--resource-dir` và `--icon`.
- [ ] Runtime image có các module cần thiết; không sửa tùy tiện `runtime`.
- [ ] Native binary có **đúng OS/architecture/ABI** và các thư viện phụ thuộc.
- [ ] Có integration test **nạp và gọi JNI/native thật** nếu sản phẩm cần.
- [ ] Không ghi log, cache, DB và user config vào thư mục cài đặt.
- [ ] App image được kiểm thử khi **working directory khác app directory**.
- [ ] Có smoke test trên máy đích **không cài JDK/JRE hệ thống**.
- [ ] Đã thử installer, shortcut, đường dẫn có dấu cách, cập nhật và gỡ cài đặt.
- [ ] Không đóng secrets trong JAR, config mẫu hoặc native binary phân phối.
- [ ] Có version, kiểm tra integrity và chính sách cập nhật thư viện native/JVM khi có bản vá.

## 15. Ghi nhớ trọng tâm

1. **App image là cả một cấu trúc thư mục** gồm launcher, app payload và bundled runtime; layout khác Windows/Linux/macOS.
2. Resource **trong JAR** phải đọc như classpath/module resource, **không** dựa vào `src/main/resources` hoặc path filesystem của dự án.
3. Resource **ngoài JAR** được đưa vào `--input` và đọc bằng `Path/Files` từ vị trí app payload do launcher cung cấp.
4. **`$APPDIR`** là token được launcher `jpackage` thay trong tham số/JVM options, **không phải biến môi trường Java có sẵn**. Truyền nó thành system property là một cách rõ ràng.
5. Native library cần **file thật, đúng OS/CPU, ABI, quyền và dependencies**. `System.load` nhận absolute path; `System.loadLibrary` nhận base name.
6. **Dữ liệu có thể sửa** như log, database, cache và preferences nên nằm trong **user/application data directory**, không nằm trong app hoặc runtime image.
7. Đóng gói thành công **chưa** chứng minh ứng dụng chạy đúng; cần kiểm thử packaged launcher, resource, native calls, quyền và môi trường sạch.

**Nguồn chính thức đang còn áp dụng:**
- [Oracle JDK 21 — Packaging Overview](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html): layout app image Windows/Linux/macOS và vai trò runtime.
- [Oracle JDK 21 — jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html): `--input`, `--app-content`, `--runtime-image`, `--resource-dir` và launcher options.
- [Oracle JDK 21 — Support Application Requirements](https://docs.oracle.com/en/java/javase/21/jpackage/support-application-features.html): `$APPDIR` trong `--java-options` và cách tìm resource.
- [Oracle JDK 21 — `java.lang.System`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): `load`, `loadLibrary` và `mapLibraryName`.
- [Oracle JDK 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getResource` và `getResourceAsStream`.
- [Oracle JDK 21 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `resolve`, `toAbsolutePath`, `normalize`.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức từ Java 16.
