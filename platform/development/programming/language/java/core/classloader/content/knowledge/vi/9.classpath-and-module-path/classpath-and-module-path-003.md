# Classpath lúc biên dịch khác classpath lúc chạy

## 1. Vấn đề cốt lõi: biên dịch thành công chưa bảo đảm chạy thành công

Một dự án Java có thể biên dịch hoàn toàn bình thường nhưng khi thực thi lại báo:

```text
java.lang.NoClassDefFoundError: com/acme/lib/Formatter
```

Tình huống này thường xuất hiện khi **dependency có mặt trong classpath lúc biên dịch, nhưng không có mặt (hoặc không đúng phiên bản) trong classpath mà JVM sử dụng lúc chạy**. Trình biên dịch cần tìm kiểu để kiểm tra tên, phương thức, trường và quan hệ kiểu; JVM phải tìm được các định nghĩa thật tại thời điểm cần nạp/liên kết/khởi tạo lớp.

Đây là hai môi trường riêng biệt:

- **Compile-time classpath:** tập thư mục, JAR và các artifact mà công cụ biên dịch (thường là `javac`, thông qua CLI/IDE/build tool) sử dụng để phân giải các loại phụ thuộc bên ngoài source đang biên dịch.
- **Runtime classpath:** tập thư mục, JAR và các artifact mà launcher/JVM cùng các class loader liên quan có thể dùng để nạp các class cần thiết khi chạy ứng dụng trên classpath.
- **Module path:** từ Java 9, ứng dụng có thể dùng JPMS; module path và quy tắc module resolution không đồng nghĩa với classpath truyền thống. Khi dùng module, phải kiểm tra cả quan hệ `requires`, `exports` và cách launcher cấu hình module path.

Hai classpath có thể giống nhau, nhưng **không mặc nhiên giống nhau**. Chúng thường khác khi dùng IDE, dependency scope, ứng dụng đóng gói bằng JAR, chạy Docker, triển khai server, CI/CD, plugin hoặc phiên bản thư viện không thống nhất.

### Ví dụ đời thực

Ứng dụng gọi `Formatter.format()` của thư viện `shared-formatting.jar`. Máy lập trình có JAR trong compile classpath nên `javac` xác nhận phương thức tồn tại và tạo `Main.class`. Khi đưa riêng `Main.class` lên server nhưng quên `shared-formatting.jar`, JVM vẫn có thể tìm được entry point `Main`, song lúc cần `Formatter` thì không tìm ra lớp.

Vì vậy, câu hỏi “Tại sao `javac` không báo lỗi?” được trả lời bằng việc **javac và JVM đang tìm phụ thuộc theo hai cấu hình khác nhau**.

## 2. Classpath biên dịch và classpath runtime trả lời hai câu hỏi khác nhau

Một thư mục `out/app` chứa `com/acme/app/Main.class`, còn `out/lib` chứa `com/acme/lib/Formatter.class`. Nếu biên dịch `Main.java` với `javac -cp out/lib -d out/app ...`, compiler tìm được kiểu `Formatter`; **nó không tự sao chép `Formatter` vào output ứng dụng**.

| Giai đoạn | Lệnh ví dụ trên Linux/macOS | Kết quả cần quan sát |
| --- | --- | --- |
| Compile | `javac -cp out/lib -d out/app src/app/com/acme/app/Main.java` | Compiler tìm được các kiểu bên ngoài |
| Runtime đủ thư viện | `java -cp "out/app:out/lib" com.acme.app.Main` | Class và dependency có thể được nạp |
| Runtime thiếu thư viện | `java -cp out/app com.acme.app.Main` | Main có thể khởi động nhưng liên kết tới Formatter thất bại |

Windows dùng dấu chấm phẩy `;` giữa các classpath entries, còn Linux/macOS dùng dấu hai chấm `:`. `javac -d` chọn **nơi ghi** bytecode, không định nghĩa đường tìm thư viện cho tiến trình `java` sẽ chạy sau.

## 3. Khi nào không chỉ là chuyện thiếu file?

Classpath entry phải là **root cây package** hoặc JAR phù hợp. Đặt JAR ở một thư mục không có nghĩa loader của ứng dụng tự tìm nó. Ngoài việc thiếu thư viện, compile-time và runtime còn có thể chọn **hai phiên bản class cùng tên**: JVM tìm ra class nhưng API trong bytecode không khớp, dẫn tới `NoSuchMethodError`, `NoSuchFieldError` hoặc lỗi linkage. Thí nghiệm tiếp theo cô lập một dependency để minh họa đúng nguyên nhân; việc Gradle/Maven chọn và phân phối dependency được trình bày chuyên sâu ở bài cuối chương.

## 4. Thí nghiệm Java 17+: compile có Formatter, runtime lại thiếu Formatter

Ta tạo hai phần độc lập: một lớp thư viện và một class ứng dụng. Ví dụ không phụ thuộc Maven/Gradle; chỉ yêu cầu JDK 17+.

Tạo cây thư mục theo đường dẫn:

```text
src/
├── lib/
│   └── com/acme/lib/Formatter.java
└── app/
    └── com/acme/app/Main.java
```

Nội dung file `src/lib/com/acme/lib/Formatter.java`:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String format(String text) {
        return "Formatted: " + text;
    }
}
```

Nội dung file `src/app/com/acme/app/Main.java`:

```java
package com.acme.app;

import com.acme.lib.Formatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println(Formatter.format("Java"));
    }
}
```

Hai class này có **package** và **đường dẫn** nhất quán. Không có giả định IDE hoặc công cụ build tự thêm thư viện.

### Bước 1 — Biên dịch thư viện

Từ thư mục gốc của ví dụ:

```bash
javac --release 17 -d out/lib src/lib/com/acme/lib/Formatter.java
```

Thư viện được ghi thành:

```text
out/lib/com/acme/lib/Formatter.class
```

### Bước 2 — Biên dịch ứng dụng với compile-time classpath có thư viện

```bash
javac --release 17 -cp out/lib -d out/app src/app/com/acme/app/Main.java
```

Lệnh này thành công vì `javac` tìm thấy `com.acme.lib.Formatter` từ `out/lib`. Kết quả ứng dụng được ghi vào:

```text
out/app/com/acme/app/Main.class
```

**Điểm quan trọng:** `javac -cp out/lib` chỉ cho compiler sử dụng thư viện; nó **không chép `Formatter.class` vào `out/app`**. Các file vẫn ở hai thư mục đầu ra riêng biệt.

### Bước 3 — Chạy với runtime classpath đầy đủ

Linux/macOS:

```bash
java -cp "out/app:out/lib" com.acme.app.Main
```

Windows (PowerShell hoặc Command Prompt):

```powershell
java -cp "out/app;out/lib" com.acme.app.Main
```

Stdout xác định:

```text
Application started
Formatted: Java
```

Có cả root chứa `Main.class` và root chứa `Formatter.class`, nên JVM có thể nạp lớp của chương trình và phụ thuộc.

### Bước 4 — Chạy với runtime classpath thiếu thư viện

```bash
java -cp out/app com.acme.app.Main
```

Ở lần chạy này, `Main.class` vẫn có trong `out/app`. Nhưng `out/lib` bị loại khỏi runtime classpath, nên JVM không có đường tìm lớp `com.acme.lib.Formatter` theo cơ chế thông thường.

Trên JVM thông dụng, stdout thường đã in `Application started` trước khi lệnh gọi `Formatter.format(...)` gây lỗi; phần stderr sẽ chứa thông tin tương tự:

```text
Exception in thread "main" java.lang.NoClassDefFoundError: com/acme/lib/Formatter
    ...
Caused by: java.lang.ClassNotFoundException: com.acme.lib.Formatter
    ...
```

Các dòng stack trace cụ thể, thứ tự xuất hiện giữa stdout/stderr khi redirect và thời điểm JVM chọn resolution có thể phụ thuộc triển khai; vì vậy đây là **mẫu dạng lỗi**, không phải khẳng định toàn bộ output bất biến trên mọi VM. Không cần đoán số dòng source trong stack trace.

**Tại sao `Main` biên dịch được?** Vì tại compile time có `out/lib`. **Tại sao lại lỗi khi chạy?** Vì tại runtime chỉ có `out/app`, không có nguồn để load `Formatter`. Đây là ví dụ tách bạch nhất về hai classpath.

### Bước 5 — Chạy lại sau khi sửa đường dẫn

Thêm `out/lib` trở lại runtime classpath như bước 3 và chạy lại; output của chương trình sẽ trở về hai dòng thành công. Với một tiến trình đã gặp lỗi khởi tạo hoặc linkage trong class loader đang hoạt động, cách sửa classpath thường cần **khởi chạy tiến trình mới**, không thể chỉ sửa file rồi kỳ vọng loader đang dùng tự đổi cấu hình.

## 5. Lúc compile và lúc runtime có thể cùng tên nhưng khác phiên bản

Một lỗi khó hơn trường hợp hoàn toàn thiếu class: **cả hai môi trường đều có `com.acme.lib.Formatter`, nhưng bytecode thực tế khác nhau**.

Ví dụ compile-time có thư viện v1:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String format(String value) {
        return "v1:" + value;
    }
}
```

Ứng dụng được biên dịch với lời gọi `Formatter.format("Java")`. Sau khi triển khai, runtime lại dùng bản v2:

```java
package com.acme.lib;

public final class Formatter {
    private Formatter() {}

    public static String render(String value) {
        return "v2:" + value;
    }
}
```

Hai đoạn là **hai phiên bản thay thế nhau của cùng binary name**, không phải hai file được biên dịch đồng thời trong cùng output. Nếu khi chạy JVM nạp bản v2 vốn không còn `format(String)`, lời gọi đã biên dịch trong `Main.class` vẫn tham chiếu tới method signature cũ. Khi JVM giải quyết lời gọi đó, có thể ném:

```text
java.lang.NoSuchMethodError: 'java.lang.String com.acme.lib.Formatter.format(java.lang.String)'
```

Tình huống tương tự xảy ra khi xóa/đổi field (`NoSuchFieldError`), đổi loại instance/static method, thay class thành interface, hoặc thay đổi quan hệ kế thừa theo cách không tương thích nhị phân.

Vì thế, không nên chỉ kiểm tra “JAR có tồn tại?”; phải kiểm tra **đúng phiên bản runtime đã nạp** và ABI mà mã đã biên dịch kỳ vọng.

### Bytecode compatibility không phải luôn source compatibility

- **Source compatibility:** mã nguồn có thể biên dịch lại được với API mới không?
- **Binary compatibility:** file `.class` đã biên dịch từ trước còn liên kết/chạy với API mới không?
- **Behavioral compatibility:** chạy được nhưng kết quả có đúng kỳ vọng không?

Một thay đổi dependency có thể làm source không biên dịch được, nhưng binary cũ vẫn chạy; hoặc source cũ biên dịch với bản A trong khi runtime nạp bản B rồi sinh `NoSuchMethodError`. Ba khái niệm này cần được phân biệt khi chẩn đoán.

## 6. ClassLoader quyết định thực tế lớp nào được thấy ở runtime

Một classpath cấu hình đúng còn phải xét **class loader đang xử lý yêu cầu**.

Trong ứng dụng Java chạy trên classpath đơn giản, application/system loader thường tìm lớp từ những đường dẫn mà launcher cung cấp. Nhưng ở container, plugin framework, servlet container hoặc hệ module, nhiều loader có thể có vùng nhìn thấy khác nhau.

```text
Application / Parent Loader
    |- app.Main
    |- lib.Formatter v1
    |
    +-- Plugin Loader
            |- plugin.Entry
            |- lib.Formatter v2
```

Với parent-first delegation, yêu cầu `PluginLoader.loadClass("lib.Formatter")` có thể được parent thỏa mãn bởi v1 **trước khi** loader con tìm tới v2. Dù JAR v2 có mặt trong thư mục của plugin, class được nạp thực tế vẫn là bản v1.

Ngược lại, child-first được cấu hình có chủ đích có thể chọn bản v2 ở plugin trước; lúc đó hai loader có thể định nghĩa hai bản cùng tên. Nhưng nếu kiểu thư viện riêng của plugin bị truyền qua API host dùng bản v1, sẽ có nguy cơ `ClassCastException` hoặc `LinkageError` liên quan type identity.

### Danh tính kiểu còn phụ thuộc defining loader

Một kiểu runtime được nhận diện bởi cặp **(binary name, defining loader)**. Hai loader độc lập định nghĩa `lib.Formatter` tạo ra hai kiểu riêng, kể cả khi bytecode giống nhau.

Vì vậy, muốn chẩn đoán lớp thực sự nào đang được dùng, có thể in:

```java
static void describe(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
    System.out.println("source="
            + (cs == null ? "<unknown>" : cs.getLocation()));
}
```

Đây là **phương thức hỗ trợ**, cần đặt trong class ứng dụng và gọi với đối tượng `Class<?>` đã được tải; nó không phải chương trình `main` riêng. `getClassLoader()` trả `null` khi class do bootstrap loader định nghĩa. `CodeSource` có thể `null`, đặc biệt với các lớp nền tảng, module hoặc class được định nghĩa tùy biến. Không kết luận classpath sai chỉ vì `source=<unknown>`.

**TCCL không đồng nghĩa defining loader:** `Thread.currentThread().getContextClassLoader()` chỉ là context loader mà một số API, như service discovery, lựa chọn để tìm dependency; nó không tự thay đổi loader đã định nghĩa một lớp cụ thể.

## 7. Thời điểm lỗi xuất hiện phụ thuộc loading và linking

Có lúc ứng dụng chạy được vài giây rồi mới báo thiếu class, dù thư viện không được đưa vào runtime từ đầu. Điều đó liên quan đến vòng đời lớp:

1. **Loading:** JVM tìm định nghĩa lớp khi cần; superclass và superinterface là phụ thuộc cấu trúc cần thiết khi định nghĩa.
2. **Linking:** verifier, preparation, resolution của constant pool. Resolution có thể diễn ra sớm hoặc khi tham chiếu được dùng, trong giới hạn đặc tả.
3. **Initialization:** khi active use yêu cầu, JVM khởi tạo lớp và những phụ thuộc cần khởi tạo theo quy tắc JLS/JVMS.

Ví dụ:

```java
class OptionalFeature {
    static void run() {
        LibraryOnlyAtRuntime.execute();
    }
}
```

Đây là **mã minh họa, không phải chương trình chạy độc lập**; giả định `LibraryOnlyAtRuntime` có mặt lúc biên dịch. Việc một code path chưa chạy không chứng minh tất cả phụ thuộc đều hiện diện; JVM có thể phân giải tham chiếu ở thời điểm khác và fail khi chức năng được sử dụng.

Trái lại, thiếu superclass hoặc superinterface trực tiếp/gián tiếp của class đang được định nghĩa có thể khiến quá trình nạp lớp thất bại **trước cả khi gọi phương thức**.

Vì vậy, không nên dùng riêng thời điểm stack trace xuất hiện để kết luận lỗi chỉ nằm ở câu lệnh Java đang hiển thị. Phải xem **lớp phụ thuộc nào được JVM tìm ở thời điểm đó**, loader nào, và quá trình linking/initialization có liên quan hay không.

## 8. Những loại lỗi điển hình khi classpath compile và runtime khác nhau

| Lỗi / Triệu chứng | Diễn giải có khả năng | Cần kiểm tra |
| --- | --- | --- |
| Compile: `package com.acme.lib does not exist` | Compile classpath thiếu thư viện | `javac -cp`, dependency scope, đường dẫn JAR/classes |
| Compile: `cannot find symbol` | Trình biên dịch không phân giải được tên kiểu, method hoặc field | Import, tên package, phiên bản API, source path |
| Runtime: `Could not find or load main class` | Launcher không tìm hoặc không nạp được entry class | Runtime `-cp`, root package, tên main, JAR manifest |
| Runtime: `ClassNotFoundException` | API như `Class.forName` / `loadClass` tìm theo tên không thấy lớp | Tên nhị phân, loader được yêu cầu, file/JAR nằm ở đâu |
| Runtime: `NoClassDefFoundError` | JVM không thể dùng lớp được kỳ vọng; thường thiếu phụ thuộc hoặc lớp từng khởi tạo lỗi | Chuỗi `Caused by`, lỗi đầu tiên, dependency đã đóng gói |
| Runtime: `NoSuchMethodError` / `NoSuchFieldError` | Binary chạy với API khác phiên bản compile | Vị trí class runtime, ABI method/field, dependency conflicts |
| Runtime: `IncompatibleClassChangeError` | Thay đổi không tương thích về class/interface, static/instance hoặc quan hệ kiểu | Các JAR compile/runtime và method descriptor |
| Runtime: `UnsupportedClassVersionError` | Class được biên dịch cho JVM mới hơn JVM đang chạy | `java -version`, target/release, pipeline JDK |
| Runtime: `ClassCastException` giữa các lớp cùng tên | Có thể do hai defining loader độc lập | `clazz.getClassLoader()` ở cả hai phía |
| Runtime: `ServiceConfigurationError` | Service provider thiếu hoặc không thể nạp/khởi tạo/thực thi SPI | Provider JAR, `META-INF/services`, loader, module config |

**Đọc nguyên nhân, không chỉ loại lỗi.** `NoClassDefFoundError` không đồng nghĩa “classpath chắc chắn thiếu”: initializer từng thất bại có thể khiến lớp ở trạng thái erroneous và các lần gọi sau sinh lỗi cùng loại. `ClassNotFoundException` thường có thể nằm trong `Caused by` của `NoClassDefFoundError` khi loader không tìm ra phụ thuộc.

**Có mặt trên classpath chưa chắc sử dụng được.** Thư viện có thể chứa class đúng tên nhưng được compile cho Java phiên bản cao hơn, phụ thuộc transitive thiếu, classloader không thấy nó, hoặc JPMS không cho phép truy cập package.

## 9. Dependency trực tiếp, bắc cầu và runtime

Ứng dụng có thể compile với `A.jar` trong khi A còn dùng `B.jar`. Nếu runtime thiếu B, code chỉ lỗi khi đường thực thi cần B. Với Gradle, `compileOnly` có trong compile classpath nhưng không tự vào runtime classpath; `runtimeOnly` có chiều ngược lại. Maven `provided` có nghĩa môi trường triển khai được kỳ vọng cung cấp dependency phù hợp.

| Hiện tượng | Cần đối chiếu |
| --- | --- |
| Compile thành công, runtime thiếu class | `compileClasspath` và `runtimeClasspath`, các JAR hiện diện ở runtime |
| Tìm được class, thiếu method | Phiên bản class runtime so với signature compile |
| Có dependency trong build nhưng triển khai thiếu | Artifact cuối cùng, launcher và distribution, không chỉ file khai báo |

Bài **Khác biệt giữa dependency của công cụ build và đường dẫn thực tế của JVM** tập trung vào configuration/scope, resolution và việc một plain JAR khác task `run`. Trong bài hiện tại, hãy theo dõi *thời điểm JVM cần nạp/liên kết class* và phân tích lỗi đầu tiên.

## 10. Chạy JAR: khác biệt giữa -jar và -cp

Ví dụ đóng gói entry class vào `app.jar`:

```bash
jar --create --file app.jar --main-class com.acme.app.Main -C out/app .
```

Lệnh này chỉ đưa class trong `out/app` vào `app.jar` theo cấu trúc đã tạo; nó **không tự bao gồm** `Formatter.class` đang ở `out/lib`.

Nếu sử dụng:

```bash
java -jar app.jar
```

Runtime sẽ thiếu dependency nếu nó không xuất hiện qua các cơ chế mà Java launcher/JAR manifest hỗ trợ. Một executable JAR thông thường có thể dùng **manifest `Class-Path`** chỉ đến các JAR phụ thuộc bên ngoài (đường dẫn tương đối theo quy tắc manifest), hoặc có thể được build thành uber/fat JAR theo công cụ đóng gói phù hợp.

Đừng kỳ vọng:

```bash
java -cp out/lib -jar app.jar
```

sẽ tự thêm `out/lib` vào user classpath cho mode `-jar` như khi gọi main class bằng `-cp`. Theo hợp đồng launcher, khi dùng `-jar`, classpath do `-cp` chỉ định bị bỏ qua cho việc chọn user classes; manifest và cách đóng gói JAR là thành phần phải kiểm tra.

Đối với **plain JAR**, có thể chạy theo tên main class và classpath chứa cả JAR + dependency:

Linux/macOS:

```bash
java -cp "app.jar:out/lib" com.acme.app.Main
```

Windows:

```powershell
java -cp "app.jar;out/lib" com.acme.app.Main
```

Lựa chọn giữa `java -jar` và `java -cp` phải tương thích với loại artifact. Ví dụ, executable JAR do framework đóng gói với nested JAR có launcher riêng; lệnh Java classpath thuần có thể không nhìn thấy thư viện nested theo cách người dùng mong đợi.

## 11. Classpath, module path và môi trường từ Java 9 trở đi

Từ Java 9, JPMS bổ sung **module path**. Khi sử dụng named modules, các tùy chọn quan trọng gồm:

- `--module-path` / `-p`: đường tìm các module (JAR modular hoặc exploded module).
- `--module` / `-m`: yêu cầu launcher chạy main class của named module.
- `requires`: quan hệ đọc module được khai báo trong `module-info.java`.
- `exports`: package mà module cho phép truy cập ở mức module.
- `opens`: package mở cho reflective access theo quy tắc JPMS.

**Module path không phải “classpath mới” có semantics y hệt.** Trên classpath truyền thống, code thường nằm trong unnamed module; trên module path, việc phân giải module và visibility/encapsulation bổ sung ràng buộc.

Nếu ứng dụng compile thành công nhờ module có mặt trên compile module path nhưng runtime module graph thiếu nó, lỗi có thể xuất hiện ngay khi Java launcher resolve graph, chẳng hạn thông báo kiểu:

```text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module ... not found, required by ...
```

Các dấu `...` ở đây **minh họa vị trí tên module**, không phải stdout cố định. Biện pháp là kiểm tra runtime module path, tên module và graph resolved, không chỉ thêm ngẫu nhiên một JAR vào classpath rồi kỳ vọng named module đọc được.

Không nên chữa lỗi module encapsulation bằng cách đổi classpath bừa bãi: nếu thiếu `exports`/`opens` hoặc module readability, loại lỗi và giải pháp khác với việc hoàn toàn thiếu file `.class`.

## 12. Thực hành xác minh compile và runtime classpath

Có thể thực hiện theo quy trình, đặc biệt khi “works in IDE, fails in production”:

1. **Ghi lệnh biên dịch thực tế.** Không chỉ ghi “mình dùng javac”: lấy compile classpath hoặc classpath do IDE/Gradle/Maven cung cấp; lưu bản phân giải dependency và phiên bản.
2. **Ghi lệnh khởi động thực tế.** Nhìn đúng `java` command line, `-cp`, `-jar`, `--module-path`, working directory, environment và các JVM launch options.
3. **Kiểm tra file được đóng gói.** Với JAR thuần có thể dùng `jar --list --file app.jar` hoặc `jar tf app.jar`; lưu ý nested JAR/framework launcher có quy tắc riêng.
4. **Kiểm tra binary name và root path.** Class `com.acme.app.Main` phải được tìm qua gốc chứa `com/acme/app/Main.class`, không phải gốc nằm sâu ở package directory.
5. **Nếu có lỗi liên kết, xác định lớp thực sự được nạp.** Xem defining loader và code source khi class có thể load.
6. **Dò JAR trùng class và xung đột phiên bản.** Hai JAR cùng chứa binary name không có nghĩa JVM tự chọn bản mới nhất; thứ tự và loader selection ảnh hưởng.
7. **So sánh JDK compile với JDK runtime.** Một class file target cao hơn có thể gây `UnsupportedClassVersionError`.
8. **Xem chuỗi `Caused by` và lỗi đầu tiên trong log.** Triệu chứng thứ hai sau initialization failure có thể che mất nguyên nhân gốc.

### Công cụ dòng lệnh hữu ích

```bash
java -version
javac -version
jar tf app.jar
javap -classpath out/app -public com.acme.app.Main
```

- `java -version` và `javac -version` giúp phát hiện hai JDK/JRE được chọn khác nhau.
- `jar tf` cho biết thành phần bên trong artifact (không cho biết tất cả dependency bên ngoài).
- `javap -classpath ...` cho phép xem cấu trúc class/bytecode đã compile trong root/JAR chỉ định, hữu ích khi nghi ngờ mã chạy không cùng bản với source.

Để quan sát class loading trên JVM hỗ trợ unified logging (JDK 17+):

```bash
java -Xlog:class+load=info -cp "out/app:out/lib" com.acme.app.Main
```

Lệnh ví dụ dùng separator Linux/macOS; trên Windows đổi dấu `:` trong `-cp` thành `;`. Log class-load giúp nhận biết nhiều class được nạp từ nguồn nào, nhưng có thể rất dài; phân biệt nguồn bytecode với **defining loader** và đọc đúng class đang gặp lỗi.

### Classpath ngay trong JVM

Đối với một ứng dụng chạy bằng classpath thuần, có thể in:

```java
System.out.println(System.getProperty("java.class.path"));
```

Đây là **snippet minh họa**, không phải chương trình độc lập. Giá trị này hữu ích để xem Java launcher cấu hình user classpath, nhưng **không biểu diễn mọi URL của mọi custom class loader**, module path hoặc các nguồn bytecode động. Vì vậy, không thấy plugin JAR trong chuỗi property chưa đủ kết luận plugin loader không thể nạp nó.

## 13. Những ngộ nhận thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “`javac` compile được thì JVM luôn thấy các class ấy.” | Compile classpath và runtime classpath độc lập; build không tự đóng gói mọi JAR đã dùng để compile. |
| “Đã `-d out/app` thì `java` tự biết tìm ở out/app.” | Phải dùng đường chạy thích hợp như `java -cp out/app ...`. |
| “Classpath có JAR là chắc chắn JVM dùng đúng bản thư viện.” | Có thể tồn tại JAR/class trùng tên, loader cha ưu tiên bản khác, hoặc module graph không dùng JAR ấy. |
| “`-cp` luôn được áp dụng khi kèm `-jar`.” | Mode `-jar` dùng quy tắc classpath từ JAR/manifest và không dùng `-cp` để tìm user classes theo cách thông thường. |
| “`lib/*` tự quét mọi JAR trong mọi thư mục con.” | Wildcard launcher không phải recursive file discovery; cần đóng gói và bố trí thư mục đúng. |
| “Cứ thấy `NoClassDefFoundError` là bị thiếu JAR.” | Có thể thiếu dependency, hoặc lớp từng khởi tạo lỗi; phải xem cause và bối cảnh. |
| “Trường hợp `NoSuchMethodError` không liên quan classpath.” | Rất thường do runtime nạp phiên bản library khác compile-time ABI. |
| “Chỉ cần `CLASSPATH` môi trường thì khỏi cần biết câu lệnh.” | `-cp`/`--class-path` trực tiếp có thể thay đổi/ghi đè classpath mặc định; launch tool/framework có thể tự thiết lập. |
| “`--release 17` đóng gói dependency Java 17.” | `--release` kiểm soát mục tiêu biên dịch, không gom thư viện bên thứ ba vào artifact. |
| “Tất cả class đều dùng system classpath.” | Class loader tùy biến, parent delegation và JPMS có thể tạo nhiều phạm vi tìm kiếm. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `javac -cp lib/api.jar -d classes Main.java` chạy thành công. Nếu `Main` dùng class trong `api.jar`, lệnh `java -cp classes Main` có chắc chạy được không?

**Trả lời:** Không. Runtime cần có dependency khi lớp được dùng; nếu JVM không tìm được class API, có thể xảy ra lỗi nạp/liên kết. Phải đưa dependency vào runtime classpath hoặc cơ chế launcher tương ứng.

**Câu 2.** Trên Windows, hai root classpath `out/app` và `out/lib` được ngăn bằng ký tự nào?

**Trả lời:** Dấu `;`. Trong PowerShell, sử dụng `java -cp "out/app;out/lib" ...` để giữ argument classpath là một chuỗi.

**Câu 3.** Trên Linux, lệnh `java -cp out/app com.acme.app.Main` báo `NoClassDefFoundError: com/acme/lib/Formatter`, trong khi compile đã dùng `-cp out/lib`. Nguyên nhân trực tiếp đáng kiểm tra nhất?

**Trả lời:** Runtime đã bỏ `out/lib`. Dùng `java -cp "out/app:out/lib" com.acme.app.Main`.

**Câu 4.** Runtime có `Formatter.class`, nhưng báo `NoSuchMethodError` khi gọi `Formatter.format(String)`. Vì sao?

**Trả lời:** Runtime có thể nạp phiên bản `Formatter` khác ABI mà `Main.class` được biên dịch với; phải so sánh class thực tế, chữ ký phương thức và phiên bản JAR.

**Câu 5.** Plugin có JAR v2 nhưng parent loader đã nạp class cùng tên từ JAR v1. Thêm JAR v2 vào plugin classpath có chắc sửa được không?

**Trả lời:** Không. Parent-first có thể tiếp tục trả bản v1. Cần kiểm tra defining loader và thiết kế delegation/ranh giới API thích hợp.

**Câu 6.** `java -jar app.jar` không tìm được dependency, nhưng thêm `-cp lib/*` cùng lệnh `-jar` vẫn thất bại. Hướng xử lý?

**Trả lời:** Kiểm tra loại executable JAR, manifest `Class-Path`, cơ chế framework launcher hoặc chạy main class bằng `-cp` chứa cả app.jar và dependency nếu là plain JAR phù hợp.

**Câu 7.** Vì sao `Class.forName("com.acme.lib.Formatter")` có thể ném `ClassNotFoundException` trong khi một lần invoke code đã compile lại ném `NoClassDefFoundError`?

**Trả lời:** `Class.forName` biểu lộ ngoại lệ tìm lớp qua API; khi JVM đang giải quyết phụ thuộc bytecode đã được biên dịch, lỗi liên kết do class không khả dụng có thể là `NoClassDefFoundError`. Phải đọc chuỗi cause để biết cơ chế gây lỗi.

## 15. Checklist triển khai đáng tin cậy

Trước khi coi bản build là có thể chạy được trên môi trường khác:

- [ ] Artifact triển khai gồm **đúng** main class, các class của ứng dụng và mọi dependency runtime cần thiết, hoặc có hợp đồng rõ về dependency do môi trường cung cấp.
- [ ] Runtime JDK tương thích với target class file và các thư viện.
- [ ] Lệnh chạy sử dụng đúng `-cp` / `-jar` / `--module-path` theo kiểu đóng gói đã chọn.
- [ ] Không vô tình sử dụng bản dependency khác do JAR trùng binary name hoặc class loader parent-first.
- [ ] Đã chạy smoke test bằng **artifact và lệnh khởi động thực tế** trên môi trường càng gần production càng tốt.
- [ ] Khi có lỗi, thu thập stack trace đầy đủ, class loader, nguồn bytecode và dependency graph đã phân giải.

## 16. Kết luận và nguồn tham khảo

Classpath lúc biên dịch trả lời câu hỏi **“compiler phải tìm được những kiểu nào để tạo bytecode hợp lệ?”**; classpath lúc chạy trả lời **“JVM và các class loader thật sự có thể tìm, nạp và liên kết những kiểu nào khi chương trình thực thi?”**. Hai tập phụ thuộc có thể khác nhau về **thư mục, JAR, phiên bản và cách delegation**. Để tránh lỗi, hãy kiểm tra cả compile configuration, runtime launch configuration và artifact được triển khai, thay vì suy luận từ thông báo “BUILD SUCCESSFUL”.

Tài liệu chính thức:

- Java SE 17 `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 `java` launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification 17 §5, Loading, Linking, and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
