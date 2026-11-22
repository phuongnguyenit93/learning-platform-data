# Phân tích phụ thuộc rồi tạo runtime image bằng `jlink` (Java 9+)

`jdeps` và `jlink` là hai công cụ quan trọng của hệ sinh thái **Java Platform Module System (JPMS)**, xuất hiện từ Java 9 và vẫn hữu ích trong các JDK hiện nay. `jdeps` giúp phân tích module/class mà ứng dụng phụ thuộc; `jlink` kết hợp module ứng dụng và phụ thuộc thành **runtime image riêng**, chứa Java runtime đủ để thực thi những module được chọn. Bài này làm trọn một luồng thực hành từ source tới runtime image, với hai module Java, chạy được bằng JDK 17+.

Mục đích không chỉ là chạy lệnh. Bạn sẽ hiểu tại sao `jdeps` là **phân tích tĩnh** và không phát hiện hết reflection/service providers, tại sao `jlink` cần module ứng dụng làm root, cách kiểm tra thành phẩm bằng Java **nằm bên trong image**, và cách đưa image vào quy trình phát hành an toàn.

## 1. Kết quả mong đợi

Sau bài học, bạn có thể:

- Xây dựng hai module `com.example.greeter` và `com.example.app`, khai báo `exports`/`requires` chính xác.
- Biên dịch bằng `javac --module-source-path` và chạy app bằng `java --module-path --module`.
- Sử dụng `jdeps --print-module-deps` để phân tích graph và hiểu những module xuất hiện.
- Tạo runtime image bằng `jlink --module-path --add-modules --launcher --output`.
- Xác nhận runtime image chứa đúng những module cần thiết, chạy được độc lập với Java nằm trên `PATH` của máy phát triển.
- Xác định giới hạn của static analysis, automatic modules, services, reflection và thư viện native.
- Biết lúc nào build lại image, cần kiểm tra điều gì trên CI/OS đích, và phân biệt `jlink` với `jpackage`.

Đầu ra của thực hành là thư mục `build/runtime/`, có `bin/java` và launcher `app` (`app.bat` trên Windows trong ví dụ). Khi chạy launcher, ứng dụng in một câu chào tiếng Việt.

## 2. Tư duy tổng thể: nguồn → phụ thuộc → image

```text
src/ (module-info.java, mã Java)
            │
            ▼
javac --module-source-path
            │
            ▼
build/mods/ (exploded named modules)
            │
     ┌──────┴─────────────┐
     ▼                    ▼
   jdeps                 jlink ◄── JDK/jmods
     │                    │
     ▼                    ▼
Danh sách module      build/runtime/
cần rà soát           bin/java, bin/app, lib, ...
                           │
                           ▼
                    Chạy app từ image
```

| Công cụ | Việc chính | Điều không tự làm |
| --- | --- | --- |
| `javac` | Biên dịch source module thành `.class` và `module-info.class` | Không tạo runtime image |
| `jdeps` | Phân tích class/module dependencies và xuất graph/danh sách module | Không chứng minh mọi dependency động đều được phát hiện |
| `jlink` | Liên kết root modules và phụ thuộc, tạo runtime image | Không sửa source, không tạo installer đa nền tảng |
| `java` bên trong image | Chạy module từ runtime đã liên kết | Không tự cập nhật khi JDK mới được vá |
| `jpackage` | Đóng gói ứng dụng thành các hình thức phù hợp nền tảng | Có mục đích khác `jdeps`, và không thay thế kiểm thử image |

`jlink` nhận **root modules** trong `--add-modules` và tự resolve dependencies. Với ứng dụng có entrypoint trong `com.example.app`, chỉ định module này làm root thường là lựa chọn rõ ràng nhất. Tập module in bởi `jdeps` giúp bạn hiểu và rà soát, nhưng có thể không chứa **chính root module** nếu lệnh phân tích đang in danh sách *phụ thuộc*.

## 3. Chuẩn bị JDK và hiểu version runtime

Cần **JDK đầy đủ**, không chỉ Java runtime tối giản. Dùng JDK 17 hoặc mới hơn:

```bash
java -version
javac -version
jdeps --version
jlink --version
```

Kiểm tra đường dẫn `JAVA_HOME` và thư mục JMOD:

```bash
# Bash / zsh
echo "$JAVA_HOME"
ls "$JAVA_HOME/jmods"
```

```powershell
# PowerShell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\jmods"
```

`jmods` chứa những module chuẩn và module JDK để `jlink` đọc. Nếu `JAVA_HOME` không được thiết lập, cần xác định đúng JDK chứa `jlink` và `jmods`. Tránh phối hợp vô ý các công cụ từ nhiều JDK vendor/version khác nhau.

**Một khác biệt rất quan trọng:** `javac --release 17` tạo bytecode có khả năng chạy trên Java 17, nhưng nếu bạn dùng `jlink` của JDK 24 với `jmods` JDK 24, runtime image chứa **runtime Java 24**. `--release 17` không hạ phiên bản runtime đã link về 17. Khi sản phẩm bắt buộc runtime Java 17, cần build/link bằng **JDK 17** phù hợp.

Runtime image có thành phần native, phụ thuộc **hệ điều hành, kiến trúc CPU và JDK build**. Image tạo trên Windows không thể mặc nhiên chạy trên Linux hoặc macOS; với nhiều target, cần quy trình build/test theo nền tảng.

## 4. Xây dựng dự án hai module

Để thấy module application và library cùng xuất hiện trong image, ta tạo:

| Module | Chức năng | Dependency |
| --- | --- | --- |
| `com.example.greeter` | Xuất API `Greeter.greet` | `java.base` ngầm định |
| `com.example.app` | Chạy entrypoint, dùng `Greeter` và `Logger` | `com.example.greeter`, `java.logging`, `java.base` |

Cấu trúc tệp, bắt đầu từ thư mục `project/`:

```text
project/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/example/greeter/api/
    │       └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/
            └── Main.java
```

### 4.1. Thư viện `com.example.greeter`

Tệp **`src/com.example.greeter/module-info.java`**:

```java
module com.example.greeter {
    exports com.example.greeter.api;
}
```

`exports` làm cho những public type trong package `com.example.greeter.api` có thể được module đọc nó truy cập. `java.base` được đọc ngầm nên không cần khai báo.

Tệp **`src/com.example.greeter/com/example/greeter/api/Greeter.java`**:

```java
package com.example.greeter.api;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

### 4.2. Ứng dụng `com.example.app`

Tệp **`src/com.example.app/module-info.java`**:

```java
module com.example.app {
    requires com.example.greeter;
    requires java.logging;
}
```

Ứng dụng cần đọc module thư viện và module `java.logging` của JDK. Nếu bỏ `requires com.example.greeter`, `javac` sẽ báo app không được phép truy cập package không nằm trong module mà nó đọc.

Tệp **`src/com.example.app/com/example/app/Main.java`**:

```java
package com.example.app;

import com.example.greeter.api.Greeter;
import java.util.logging.Logger;

public final class Main {
    private static final Logger LOGGER = Logger.getLogger(
            Main.class.getName());

    private Main() {
    }

    public static void main(String[] args) {
        if (!Main.class.getName().equals(LOGGER.getName())) {
            throw new AssertionError("Logger was not initialized");
        }

        String name = args.length == 0 ? "Java 9+" : args[0];
        System.out.println(Greeter.greet(name));
    }
}
```

`Logger` giúp chúng ta có phụ thuộc thực vào `java.logging`, nhưng ví dụ không in log, giữ stdout dễ kiểm chứng. `Greeter` là class public được export bởi module thư viện. Tên module khác tên package và phải được viết đúng trong `module-info.java`.

## 5. Biên dịch và chạy trên JDK đầy đủ

Mọi lệnh bên dưới chạy tại thư mục `project/`, nơi có `src/`.

### 5.1. Biên dịch cả hai module

Bash/zsh:

```bash
javac --release 17 -encoding UTF-8 \
  --module-source-path src \
  -d build/mods \
  --module com.example.greeter,com.example.app
```

PowerShell/CMD viết một dòng:

```text
javac --release 17 -encoding UTF-8 --module-source-path src -d build/mods --module com.example.greeter,com.example.app
```

Kết quả chính:

```text
build/mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Đây là **exploded modules**: module đã biên dịch nằm trong thư mục, chưa cần đóng vào JAR. `jlink` nhận cả exploded modules, modular JAR và JMOD nếu có metadata module phù hợp. Khi phát hành thư viện, modular JAR cũng là lựa chọn phổ biến; dạng file không thay đổi bản chất `requires`/`exports`.

Nếu `javac` báo `Module ... not found`, hãy kiểm tra tên thư mục ngay dưới `src`, `module-info.java`, `requires`, đường dẫn source và chính tả tên module. Khi file Java chứa tiếng Việt, `-encoding UTF-8` tránh lỗi phụ thuộc charset của môi trường.

### 5.2. Chạy app trước khi đóng gói

Bash:

```bash
java --module-path build/mods \
  --module com.example.app/com.example.app.Main
```

PowerShell/CMD:

```text
java --module-path build/mods --module com.example.app/com.example.app.Main
```

Stdout:

```text
Xin chào, Java 9+!
```

Thử với đối số:

```bash
java --module-path build/mods --module com.example.app/com.example.app.Main Lan
```

Stdout:

```text
Xin chào, Lan!
```

Chỉ sang bước `jdeps`/`jlink` khi app đã chạy được trên module path. Khi image lỗi, việc đã có một lượt chạy cơ sở thành công giúp tách lỗi code/module descriptor khỏi lỗi đóng gói.

## 6. Phân tích dependency với `jdeps`

### 6.1. Module dependencies

```bash
jdeps --module-path build/mods \
  --module com.example.app \
  --print-module-deps
```

PowerShell/CMD:

```text
jdeps --module-path build/mods --module com.example.app --print-module-deps
```

Với project mẫu, tập module được liệt kê là:

```text
com.example.greeter,java.base,java.logging
```

Thứ tự hiển thị có thể khác, nhưng ý nghĩa không đổi:

- `com.example.greeter`: module riêng của ứng dụng.
- `java.logging`: module chuẩn JDK chứa `Logger`.
- `java.base`: module nền Java.
  
`--print-module-deps` in danh sách cách nhau bằng dấu phẩy, thuận lợi để rà soát hoặc dùng trong build script. Nó không nhất thiết in **module gốc** `com.example.app` vì lệnh đang tập trung vào những **phụ thuộc** của root.

Đừng đọc kết quả theo nghĩa “thấy `java.base` thì chỉ cần include `java.base`”: nếu muốn link ứng dụng có `Main`, root `--add-modules` vẫn phải chứa module ứng dụng.

### 6.2. Các chế độ phân tích khác

```bash
jdeps --module-path build/mods \
  --module com.example.app \
  --list-deps
```

`--list-deps` liệt kê dependencies và có thể cho thêm ngữ cảnh. `--list-reduced-deps` lược bỏ những cạnh đọc đã được hàm ý từ module graph; `--print-module-deps` phù hợp nếu muốn dạng dấu phẩy. Khi dùng script để xây manifest, kiểm tra mã thoát `jdeps`, cảnh báo phụ thuộc không tìm thấy và phạm vi phân tích.

Để rà soát một JAR sử dụng API nội bộ JDK:

```bash
jdeps --jdk-internals path/to/library.jar
```

`path/to/library.jar` là **đường dẫn ví dụ**, phải đổi thành artifact thực. Đừng quyết định dùng API `jdk.internal.*` chỉ vì công cụ có thể nhìn thấy; API nội bộ không có cam kết ổn định như API public.

**Thư viện multi-release JAR:** nếu cùng JAR chứa implementation khác nhau cho nhiều phiên bản Java, dùng `jdeps --multi-release <version>` với version đích để tránh phân tích nhầm variant. Bài học về module phải gắn với bộ Java được hỗ trợ, không chỉ JDK cài trên laptop.

### 6.3. Giới hạn của phân tích tĩnh

`jdeps` dựa trên class files, static references và metadata module. Nó không tự phát hiện trọn vẹn những thứ được nạp động qua:

- `Class.forName("com.vendor.Driver")` hoặc reflection theo tên chuỗi;
- `ServiceLoader` và module **provider** chỉ được phát hiện ở runtime;
- Native libraries/JNI, file resource, provider bảo mật hoặc cấu hình;
- Framework plugin loader, generated class, package được nạp có điều kiện;
- Những nhánh hiếm chỉ chạy trên hệ điều hành hoặc môi trường nhất định.

Vì vậy **phải kiểm tra image bằng integration tests**. Kết quả jdeps là cơ sở tốt để hiểu graph, nhưng không được coi là chứng chỉ mọi đường đi runtime đều hoạt động.

## 7. Dùng `jlink` tạo runtime image

Với hai module đã nằm trong `build/mods`, gọi `jlink` với **root module là `com.example.app`**. Công cụ sẽ tự lấy cả dependency tĩnh của nó.

Bash/zsh:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/mods" \
  --add-modules com.example.app \
  --launcher app=com.example.app/com.example.app.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

PowerShell:

```powershell
$mp = "$env:JAVA_HOME\jmods;build\mods"
jlink --module-path $mp `
  --add-modules com.example.app `
  --launcher app=com.example.app/com.example.app.Main `
  --strip-debug --no-header-files --no-man-pages `
  --output build/runtime
```

PowerShell dùng dấu `;` giữa các thư mục module path, còn Bash trên Unix dùng `:`. Dấu backtick ở cuối dòng là ký hiệu nối dòng PowerShell; có thể viết lệnh thành một dòng.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--module-path` | Nơi tìm JDK modules và modules của dự án |
| `--add-modules com.example.app` | Chọn module ứng dụng làm root; `jlink` giải thêm dependencies |
| `--launcher app=com.example.app/com.example.app.Main` | Tạo launcher `app` chạy đúng entrypoint |
| `--strip-debug` | Bỏ debug information khỏi image khi phù hợp |
| `--no-header-files` | Không kèm header files dùng trong development |
| `--no-man-pages` | Không kèm manpages |
| `--output build/runtime` | Thư mục output mới chứa Java runtime riêng |

**Tại sao `--module-path` có hai phần?** `build/mods` chứa hai module của dự án, còn `$JAVA_HOME/jmods` chứa `java.base`, `java.logging` và các module nền tảng. Nếu thiếu một bên, jlink không thể resolve đủ module graph.

**Tại sao chỉ `--add-modules com.example.app`?** App đã khai báo `requires com.example.greeter; requires java.logging;` nên linker tự lấy module phụ thuộc và transitively resolved dependencies. Bạn vẫn có thể thêm root khác khi có nhu cầu độc lập, nhưng không cần liệt kê lại toàn bộ graph chỉ để làm ví dụ tối thiểu.

`jlink` không ghi đè image ở `--output` nếu thư mục đó đã tồn tại. Trong CI nên build vào một thư mục artifact mới hoặc dọn đúng output **do job sở hữu** trước lần build; không xóa tùy tiện thư mục runtime khác của người dùng.

## 8. Kiểm tra thành phẩm bằng chính runtime trong image

Image chứa một thư mục runtime, không phải một file executable đơn:

```text
build/runtime/
├── bin/
│   ├── java        (java.exe trên Windows)
│   └── app         (app.bat trên Windows)
├── conf/
├── legal/
├── lib/
└── release
```

Các file cụ thể có thể khác theo JDK và OS. Không được chỉ sao chép `bin/java` hoặc `bin/app` rồi bỏ `lib` và kết luận ứng dụng đã tự chạy được.

### 8.1. Kiểm tra module bên trong image

Unix:

```bash
./build/runtime/bin/java --list-modules
```

PowerShell:

```powershell
& .\build\runtime\bin\java.exe --list-modules
```

Với ví dụ hai module và không thêm service binding, bạn sẽ thấy các module:

```text
com.example.app
com.example.greeter
java.base@<JDK-version>
java.logging@<JDK-version>
```

`<JDK-version>` là placeholder cho version thực tế của JDK dùng **để link**. Đừng hard-code `17` nếu image được link bằng JDK 24. Danh sách có thể tăng khi bạn bổ sung module, plugin hoặc cấu hình service binding.

### 8.2. Chạy launcher từ image

Bash/zsh:

```bash
./build/runtime/bin/app
```

PowerShell:

```powershell
& .\build\runtime\bin\app.bat
```

Stdout:

```text
Xin chào, Java 9+!
```

Bạn cũng có thể chạy bằng Java trong image:

```bash
./build/runtime/bin/java --module com.example.app/com.example.app.Main
```

PowerShell:

```powershell
& .\build\runtime\bin\java.exe --module com.example.app/com.example.app.Main
```

Stdout giống như trên. Hai cách này xác nhận runtime có module ứng dụng và giải được module graph mà không dùng Java trên `PATH`. Nếu chỉ chạy `java` trong terminal, bạn có thể vô tình chạy JDK hệ thống, khiến phép smoke test mất ý nghĩa.

### 8.3. Thử thay đổi dependency

Thêm sử dụng API thuộc `java.net.http` vào app (ví dụ `HttpClient.newBuilder()`) và khai báo `requires java.net.http;`. Sau đó:

1. Chạy lại `javac` trên source đã sửa;
2. Chạy `jdeps --print-module-deps` trên bytecode mới;
3. Tạo **image mới** bằng `jlink`, không dùng lại directory output đã có;
4. Liệt kê module trong image và chạy lại entrypoint/tính năng liên quan.

Lúc này bạn sẽ thấy `java.net.http` trong graph/image nếu API được sử dụng và khai báo đúng. Bài tập chứng minh jdeps đọc artifact đã biên dịch, không tự phân tích những thay đổi source mà bạn chưa compile.

## 9. ServiceLoader, reflection và module động

Một ứng dụng có thể có code như sau:

```java
// Trích đoạn minh họa, MyService là interface do ứng dụng tự định nghĩa.
for (MyService service : java.util.ServiceLoader.load(MyService.class)) {
    service.perform();
}
```

Đây **không phải** chương trình chạy độc lập vì thiếu định nghĩa `MyService`. Trong JPMS, consumer thường khai báo `uses com.example.spi.MyService`, provider khai báo `provides ... with ...`. Hai module có thể không được liên kết bằng `requires` tĩnh theo cách mà `jdeps` cho thấy.

Nếu image không có provider cần thiết, application vẫn có thể khởi động nhưng một tính năng lại báo thiếu driver, provider hoặc plugin lúc thực thi. Khi đó:

- Xác định provider thật từ API/framework và module descriptor;
- Thêm provider module cần thiết vào `--add-modules`; hoặc
- Dùng `jlink --bind-services` để linker giải service providers và dependencies liên quan, **sau đó kiểm tra kích thước và danh sách module**.

Ví dụ thử trên image riêng:

```bash
jlink --module-path "$JAVA_HOME/jmods:build/mods" \
  --add-modules com.example.app \
  --bind-services \
  --output build/runtime-with-services
```

Không cần `--bind-services` cho bài chào hỏi đơn giản. Bật tùy chọn có thể kéo thêm modules/provider không trực tiếp nằm trong `requires` và làm image lớn hơn. Chọn theo nhu cầu thực tế của ứng dụng, không bật/cắt theo cảm tính.

**Reflection theo tên class** (`Class.forName`), native libraries, JDBC driver, TLS/crypto providers, locale data, font/charset mở rộng và framework plugin loading cần có smoke/integration test phù hợp. `jdeps` giúp rà soát nhưng không thể đảm bảo những đường đi này chỉ bằng static inspection.

## 10. Trường hợp JAR chưa được modular hóa

Không phải JAR bên thứ ba nào cũng có `module-info.class`. Trên module path, một JAR không có descriptor có thể trở thành **automatic module** để giúp tương thích, nhưng **không được coi mọi automatic module là đầu vào có thể link thành image** bằng `jlink`.

Hướng xử lý phù hợp:

1. Ưu tiên phiên bản thư viện có explicit module descriptor và artifact được nhà phát hành hỗ trợ.
2. Nếu đội phát triển sở hữu source, thêm `module-info.java` đúng `exports`, `requires`, `uses` và `provides`, rồi kiểm thử trước khi phát hành.
3. Với thành phần bắt buộc nằm trên classpath hoặc tải động, giữ một cơ chế packaging đúng đặc tính thư viện và kiểm tra trên runtime image; có thể phải đóng gói application bên cạnh runtime image tùy kiến trúc.

`jdeps` có thể hỗ trợ gợi ý descriptor cho JAR, nhưng output sinh tự động cần được **review**. Reflection, service providers, JNI, runtime plugins và dependencies theo cấu hình có thể không được diễn tả đầy đủ.

Không dùng cờ bỏ qua missing dependencies để “qua build” rồi coi image là hợp lệ. Nếu thiếu module, phải xác định lý do và loại bỏ/đóng gói/khai báo dependency theo hành vi sản phẩm.

## 11. Kích thước runtime và các quyết định tối ưu

Image thường nhỏ hơn JDK đầy đủ vì nó chỉ chứa module graph được chọn, nhưng **không có số MB cố định**. Kích thước phụ thuộc vendor/build JDK, OS, số module, provider binding, locale data và plugins.

Các cờ `--strip-debug`, `--no-header-files`, `--no-man-pages` có thể giúp giảm size. Đừng cắt bỏ module chỉ vì nó ít xuất hiện trong unit test: một driver hoặc provider có thể cần thiết trong luồng lỗi hiếm gặp hoặc ở môi trường production.

Các JDK mới có cú pháp nén `--compress=zip-N` (chẳng hạn `zip-6`) tùy plugin/version. Kiểm tra `jlink --help` của JDK đang dùng; tránh dùng tùy chọn nén dạng số cũ chỉ vì thấy trong bài hướng dẫn lâu năm. Bài thực hành không bắt buộc nén, nhằm hoạt động được trên nhiều JDK 17+.

Nếu cần installer, shortcuts, icon và tích hợp cụ thể với OS, hãy tìm hiểu **`jpackage`**. `jlink` tạo runtime image; `jpackage` giải quyết bài toán đóng gói ứng dụng cho người dùng cuối. Chúng bổ sung nhau, không có quan hệ một công cụ “thay thế hoàn toàn” công cụ kia.

## 12. Kiểm thử và phát hành trên CI

Quy trình gợi ý:

```text
1. Chọn JDK cho target OS/CPU, ghi vendor và version.
2. Build modular code bằng javac/build tool.
3. Chạy unit tests và integration tests trên JDK đầy đủ.
4. Chạy jdeps, review graph và các dependency bất ngờ.
5. Chạy jlink với root application module và module path rõ ràng.
6. Chạy `build/runtime/bin/java --list-modules`.
7. Chạy launcher thực từ image, kiểm tra output/chức năng.
8. Test các nhánh sử dụng reflection, service providers, native code, TLS, JDBC.
9. Đóng gói cả thư mục image, lưu checksum và phát hành theo platform.
10. Khi có bản vá JDK, build/test và phát hành lại image.
```

| Thông tin cần lưu | Giá trị thực tế |
| --- | --- |
| JDK version/vendor | Biết runtime code nào đã nằm trong image |
| Target OS/CPU | Runtime native gắn với nền tảng |
| Root module và module path | Tái tạo kết quả jlink |
| Danh sách module trong image | Quan sát dependency tăng/giảm |
| Kết quả chạy **bằng runtime trong image** | Chứng minh artifact thực thi được ở luồng đã test |
| Version artifact và checksum | Phát hiện gói sai hoặc thiếu file |
| Lịch cập nhật JDK và rebuild | Image **không tự nhận** bản vá từ JDK hệ thống |

Nếu bạn nâng JDK để xử lý CVE, bản image được tạo trước đó **không tự được vá**. Hãy tái tạo và phân phối image mới. Nếu target nhiều OS, chạy build và smoke test trên từng môi trường mục tiêu hoặc pipeline được thiết kế tương ứng; không gửi image Windows sang Linux rồi mong nó hoạt động.

## 13. Lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| `Module ... not found` ở compile | Sai `module-info.java` hoặc module-source-path | Sửa tên/path, `requires`, `exports` |
| App chạy classpath nhưng không chạy module path | Module graph chưa đúng, package không export | Làm rõ descriptor/module path |
| `jdeps` không thấy thư viện được tải bằng chuỗi | Reflection/dynamic loading | Kiểm tra cấu hình/runtime |
| `jlink` không tìm ra `java.base` | Thiếu module JDK hoặc dùng sai JAVA_HOME | Kiểm tra `JAVA_HOME/jmods` |
| `jlink` không tìm thấy app module | Chỉ đưa JDK JMODs, quên `build/mods` | Thêm module ứng dụng vào module path |
| Automatic module không link được | JAR không có explicit descriptor phù hợp | Sử dụng bản modularized hoặc packaging khác |
| `--output` đã tồn tại | Jlink yêu cầu output mới | Build vào thư mục mới do job quản lý |
| Launcher không chạy | Sai `module/mainClass`, thiếu module/provider | Kiểm tra `--launcher` và module list |
| Chạy JDK đầy đủ được, image thất bại | Dependency/provider/resource không được đóng gói | Test từ bin/java của image, sửa graph |
| Dùng `--bind-services` tăng image bất ngờ | Kéo thêm provider modules | Đối chiếu module list và nhu cầu thực |
| Chỉ có image Windows nhưng muốn chạy Linux | Runtime native khác platform | Build theo OS/architecture |
| `--release 17` nhưng image là Java 24 | Linker lấy JMODs JDK 24 | Build/link bằng JDK đúng mục tiêu |
| Image vẫn chứa lỗi JDK đã vá | Image cũ chưa được build lại | Rebuild, test, redistribute |

## 14. Bài tập tự kiểm tra

**Bài tập A — thay đổi graph:** thêm `java.net.http` vào app (kèm code gọi một API của module). Hãy ghi lại `jdeps --print-module-deps` trước/sau, tạo image mới và đối chiếu module list. Cần biên dịch lại; jdeps không đọc thay đổi source chưa được compile.

**Bài tập B — thiếu requires:** xóa tạm `requires com.example.greeter;` rồi biên dịch. Quan sát lỗi module không được đọc; thêm lại `requires`, build lại, chạy thành công. Mục đích là hiểu tính tường minh của JPMS thay vì chỉ học lệnh jlink.

**Bài tập C — kiểm tra image:** so `java --list-modules` của JDK đầy đủ và `build/runtime/bin/java --list-modules` của image. Đừng chỉ đếm số module: đánh giá module có cần thiết cho chức năng và provider hay không.

**Bài tập D — kiểm thử deployment:** chuyển **toàn bộ thư mục image** sang máy cùng OS/architecture, chạy launcher mà không phụ thuộc Java trên `PATH`. Nếu dự án có plugin, TLS, native libs hoặc JDBC thì phải test chúng trong môi trường phân phối.

## 15. Checklist trước khi hoàn thành

- [ ] Dùng JDK có `javac`, `jdeps`, `jlink`, `jmods`; ghi vendor/version.
- [ ] `module-info.java` phản ánh đúng API public và dependencies.
- [ ] Module compile với `--release` đúng version hỗ trợ.
- [ ] Chạy app thành công trên module path trước khi link.
- [ ] Đã phân tích dependency bằng `jdeps` và nhận biết giới hạn phân tích tĩnh.
- [ ] `--module-path` của jlink trỏ tới JDK JMODs và modular application/library.
- [ ] `--add-modules` chứa module **ứng dụng làm root**.
- [ ] Link thành công vào output mới, có launcher đúng entrypoint.
- [ ] Đã kiểm tra `--list-modules` và chạy app từ runtime bên trong image.
- [ ] Có test đối với reflection/service/native/driver/charset/TLS nếu ứng dụng dùng chúng.
- [ ] Đã kiểm tra target OS/architecture và cách đóng gói đầy đủ thư mục image.
- [ ] Có quy trình rebuild image khi nâng JDK hoặc vá CVE.

## Tài liệu chính thức

- [The jdeps Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html) — phân tích dependencies, `--print-module-deps`.
- [The jlink Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html) — tạo runtime image, module path, launcher.
- [The javac Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — biên dịch modular source.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — cơ chế module từ Java 9.
- [Dev.java — Jlink](https://dev.java/learn/jvm/core-tools/jlink/) — công cụ tạo runtime tùy chỉnh.
- [Dev.java — Creating Runtime and Application Images](https://dev.java/learn/jlink/) — ví dụ nâng cao, service binding.

**Ghi nhớ:** `jdeps` trả lời “ứng dụng phụ thuộc những module nào có thể nhìn thấy bằng phân tích tĩnh?”, `jlink` trả lời “với root module và graph đã resolve, tạo runtime image như thế nào?”. Bước cuối luôn là **chạy và kiểm thử bằng chính image phát hành**, đồng thời tái tạo image khi JDK được cập nhật.
