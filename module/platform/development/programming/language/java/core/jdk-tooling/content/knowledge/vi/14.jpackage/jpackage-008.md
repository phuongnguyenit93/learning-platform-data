# Runtime image trong jpackage

`jpackage` là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc installer theo hệ điều hành. Ứng dụng thường cần một Java runtime phù hợp để chạy. Runtime image là bộ runtime đã được chuẩn bị với các module cần thiết; `jpackage` có thể tự tạo runtime image bằng `jlink` hoặc sử dụng runtime image đã được tạo trước qua tùy chọn `--runtime-image`.

Cần phân biệt ba sản phẩm:

- **Runtime image:** bộ Java runtime được liên kết từ các module, thường tạo bằng `jlink`. Nó chứa Java launcher và các thành phần runtime cần thiết.
- **Application image:** thư mục ứng dụng do `jpackage --type app-image` tạo. Nó chứa launcher ứng dụng, các tệp ứng dụng và runtime đi kèm.
- **Installer:** gói cài đặt theo hệ điều hành, chẳng hạn MSI/EXE, DMG/PKG, DEB hoặc RPM. Installer thường được tạo từ cùng cấu hình ứng dụng và runtime.

Bài này sử dụng JDK 17 trở lên, hướng dẫn cách để `jpackage` tự tạo runtime, cách cung cấp runtime tùy chỉnh, cách đóng gói ứng dụng modular và classpath, cũng như cách kiểm tra sản phẩm trước khi phát hành.

## 1. Runtime image là gì?

Runtime image là một thư mục chứa Java runtime đã được liên kết cho một tập module cụ thể. Nó thường có:

- Java launcher trong thư mục `bin`.
- Các module đã được liên kết trong runtime.
- Thư viện native và các tệp hỗ trợ theo nền tảng.
- Cấu hình và dữ liệu runtime cần thiết.

Runtime image có thể được tạo trực tiếp bằng `jlink`. Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --output runtime
~~~

Lệnh này tạo thư mục `runtime` với các module được chọn và dependency cần thiết. Có thể kiểm tra các module có trong image bằng:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

Trên Linux/macOS:

~~~bash
./runtime/bin/java --list-modules
~~~

Runtime image không nhất thiết chứa ứng dụng của bạn. Nó cung cấp môi trường Java để ứng dụng chạy. `jpackage` đưa ứng dụng và runtime vào application image hoặc installer.

## 2. Phân biệt runtime image và application image

Hai khái niệm này thường bị nhầm lẫn:

| Sản phẩm | Được tạo bởi | Nội dung chính | Mục đích |
|---|---|---|---|
| Runtime image | `jlink` hoặc được `jpackage` tạo nội bộ | Java runtime và các module cần thiết | Cung cấp môi trường chạy Java |
| Application image | `jpackage --type app-image` | Launcher ứng dụng, ứng dụng, resource và runtime | Chạy ứng dụng mà không cần cài Java riêng |
| Installer | `jpackage` với loại gói hệ điều hành | Application image cùng metadata cài đặt | Cài đặt, tạo shortcut và tích hợp hệ điều hành |

Ví dụ cấu trúc application image có thể tương tự:

~~~text
ExampleApp/
├── app/
│   ├── ExampleApp.cfg
│   └── app.jar hoặc các module ứng dụng
├── runtime/
│   ├── bin/
│   └── lib/
└── bin/
    └── launcher của ứng dụng
~~~

Cấu trúc chính xác thay đổi theo hệ điều hành và kiểu ứng dụng. Trên macOS, application image thường là bundle `.app`; trên Windows và Linux, thư mục image có launcher riêng trong cấu trúc tương ứng.

Application image là sản phẩm có thể kiểm thử và phân phối như một thư mục. Installer là lớp đóng gói bổ sung để cài application image vào máy người dùng.

## 3. jpackage tạo runtime image như thế nào?

Khi tạo application image hoặc installer mà không chỉ định `--runtime-image`, `jpackage` có thể gọi `jlink` để tạo runtime phù hợp với ứng dụng.

Với ứng dụng modular, `jpackage` có thể xác định dependency từ module descriptor và tạo runtime dựa trên module graph.

Với ứng dụng classpath, công cụ có thể phân tích dependency của ứng dụng để xác định các module nền tảng cần thiết. Khi phân tích tự động chưa đủ, có thể chỉ định thêm module bằng các tùy chọn runtime tương ứng.

Một số tùy chọn liên quan:

| Tùy chọn | Vai trò |
|---|---|
| `--add-modules` | Chỉ định module cần đưa vào runtime image khi `jpackage` tạo runtime |
| `--bind-services` | Liên kết service provider cần thiết |
| `--jlink-options` | Truyền các tùy chọn bổ sung cho `jlink` |
| `--runtime-image` | Dùng runtime image đã được tạo sẵn |
| `--module-path` | Chỉ định nơi tìm module ứng dụng hoặc dependency |
| `--module` | Chỉ định module chính và main class |

`--jlink-options` dùng để tinh chỉnh runtime image được tạo tự động, ví dụ loại bỏ debug information hoặc man pages. Kiểm tra `jpackage --help` của JDK đang sử dụng để xem danh sách tùy chọn và mặc định chính xác của phiên bản đó.

Nếu cần kiểm soát tập module, service binding hoặc cách runtime được tạo, hãy tạo runtime riêng bằng `jlink` rồi truyền cho `jpackage` qua `--runtime-image`.

## 4. Đóng gói ứng dụng modular với runtime tự tạo

Ứng dụng modular có `module-info.java`. Ví dụ sau tạo module `com.example.app`.

Cấu trúc dự án:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── mods/
├── runtime/
└── packages/
~~~

Nội dung `src/module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Nội dung `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(Main.class.getName());
        logger.fine("Application started");

        String target = args.length == 0 ? "jpackage" : String.join(" ", args);
        System.out.println("Hello from " + target + "!");
    }
}
~~~

Biên dịch module bằng JDK 17 trở lên:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.app, packages | Out-Null
javac -d mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

Có thể chạy module trước khi đóng gói:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main "modular app"
~~~

Kết quả:

~~~text
Hello from modular app!
~~~

Tạo runtime image tùy chỉnh bằng `jlink`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --output runtime
~~~

`jlink` phân giải các dependency của `com.example.app`, gồm `java.logging` và `java.base`, rồi tạo runtime image tại `runtime`.

Dùng runtime đó khi đóng gói application image:

~~~powershell
jpackage --type app-image --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

Application image được tạo trong thư mục `packages`. Trên Windows, launcher thường nằm trong thư mục image với tên ứng dụng và phần mở rộng executable; trên Linux, launcher nằm trong thư mục `bin` của image; trên macOS, ứng dụng thường được đóng gói thành bundle `.app`.

Có thể chạy launcher của application image và truyền đối số cho ứng dụng. Ví dụ, với image trên Windows, đường dẫn launcher thường là:

~~~powershell
.\packages\ExampleApp\ExampleApp.exe "packaged app"
~~~

Kết quả từ ứng dụng:

~~~text
Hello from packaged app!
~~~

Đường dẫn launcher thay đổi theo hệ điều hành. Hãy xem cấu trúc thực tế bên trong `packages` thay vì giả định mọi nền tảng dùng cùng một đường dẫn.

## 5. Để jpackage tự tạo runtime image

Không phải lúc nào cũng cần gọi `jlink` thủ công. Với module ứng dụng đã biên dịch, có thể để `jpackage` tạo runtime image và application image trong cùng một lệnh:

~~~powershell
jpackage --type app-image --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest packages
~~~

Trong trường hợp này:

1. `jpackage` đọc module ứng dụng và thông tin dependency.
2. Công cụ dùng `jlink` để tạo runtime image cần thiết.
3. Công cụ tạo application image với launcher, ứng dụng và runtime.
4. Kết quả được ghi vào thư mục đích.

Cách này phù hợp khi dependency module đã được khai báo đầy đủ và bạn không cần tinh chỉnh runtime riêng.

Có thể truyền thêm module cần thiết hoặc tùy chọn cho bước tạo runtime bằng các tham số được `jpackage` hỗ trợ, chẳng hạn `--add-modules`, `--bind-services` và `--jlink-options`. Không truyền các tùy chọn tạo runtime cùng với `--runtime-image` nếu chúng không tương thích với chế độ dùng runtime có sẵn; hãy xem trợ giúp của đúng phiên bản JDK.

## 6. Đóng gói ứng dụng classpath

Ứng dụng không dùng module descriptor vẫn có thể được đóng gói bằng `jpackage`.

Ví dụ source `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "classpath app" : String.join(" ", args);
        System.out.println("Hello from " + target + "!");
    }
}
~~~

Biên dịch và tạo JAR:

~~~powershell
New-Item -ItemType Directory -Force -Path out, input, packages | Out-Null
javac -d out src/com/example/Main.java
jar --create --file input/app.jar --main-class com.example.Main -C out .
~~~

Đóng gói thành application image:

~~~powershell
jpackage --type app-image --name ClasspathApp --input input --main-jar app.jar --main-class com.example.Main --dest packages
~~~

Trong đó:

- `--input` là thư mục chứa JAR chính và các dependency JAR/resource cần đóng gói.
- `--main-jar` chỉ định JAR chính bên trong thư mục input.
- `--main-class` chỉ định lớp có method `main` nếu manifest không cung cấp hoặc muốn khai báo rõ.
- `--dest` là thư mục chứa application image.

Nếu ứng dụng phụ thuộc các JAR khác, đặt chúng trong thư mục `input` và kiểm thử để bảo đảm launcher có classpath đầy đủ.

Với ứng dụng classpath lớn hoặc có dependency phức tạp, hãy phân tích dependency trước bằng `jdeps` và xác nhận runtime image có đủ các module nền tảng. Nếu cần kiểm soát rõ tập module, tạo runtime riêng bằng `jlink` và truyền vào `--runtime-image`.

## 7. Chọn runtime image có sẵn bằng --runtime-image

`--runtime-image` nhận đường dẫn tới runtime image đã tạo trước, thường bằng `jlink`. Khi dùng tùy chọn này, `jpackage` đóng gói ứng dụng với runtime được chỉ định thay vì tự tạo runtime mới.

Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime

jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

Nên dùng runtime có sẵn khi:

- Cần xác định chính xác module nào có trong runtime.
- Cần dùng `jlink` với các tùy chọn đặc biệt.
- Cần bật service binding cho ứng dụng.
- Muốn kiểm thử runtime độc lập trước khi đóng gói.
- Nhiều ứng dụng dùng chung một cấu hình runtime đã được kiểm chứng.

Runtime image phải tương thích với nền tảng đích và có đủ module cho ứng dụng. Không dùng runtime image Windows để đóng gói ứng dụng Linux hoặc ngược lại. Nếu runtime chứa native library, kiến trúc CPU cũng phải phù hợp.

`--runtime-image` không phải đường dẫn tới JDK cài đặt đầy đủ hoặc thư mục `jmods`. Nó phải trỏ tới runtime image đã được tạo hợp lệ, thường có thư mục `bin` và `lib`.

## 8. Tạo installer từ application image

`jpackage` hỗ trợ tạo application image và các dạng installer theo hệ điều hành.

| Hệ điều hành | Kiểu đầu ra thường dùng |
|---|---|
| Windows | `app-image`, `exe`, `msi` |
| macOS | `app-image`, `dmg`, `pkg` |
| Linux | `app-image`, `deb`, `rpm` |

Ví dụ tạo gói MSI trên Windows:

~~~powershell
jpackage --type msi --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Ví dụ tạo gói DEB trên Linux:

~~~bash
jpackage --type deb --name exampleapp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Ví dụ tạo gói DMG trên macOS:

~~~bash
jpackage --type dmg --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Các định dạng installer chỉ khả dụng trên nền tảng được hỗ trợ và có thể cần công cụ đóng gói hệ điều hành tương ứng. Ví dụ, tạo DEB cần công cụ hệ thống hỗ trợ định dạng DEB; tạo MSI/EXE có yêu cầu riêng theo JDK và môi trường Windows.

`jpackage` không phải công cụ cross-compiler để tạo installer cho mọi hệ điều hành từ một máy bất kỳ. Hãy build và kiểm thử gói trên nền tảng đích, dùng JDK và runtime image tương ứng.

## 9. Cấu hình launcher và tham số runtime

`jpackage` cho phép thiết lập cách launcher khởi chạy ứng dụng.

Một số tùy chọn hữu ích:

| Tùy chọn | Công dụng |
|---|---|
| `--java-options` | Truyền tùy chọn cho JVM, ví dụ `-Xmx1g` |
| `--arguments` | Đối số mặc định truyền cho ứng dụng |
| `--add-launcher` | Tạo launcher bổ sung với cấu hình riêng |
| `--icon` | Đặt icon cho ứng dụng hoặc installer |
| `--resource-dir` | Chỉ định thư mục chứa tài nguyên tùy chỉnh |
| `--license-file` | Đưa file giấy phép vào quy trình đóng gói |
| `--app-version` | Ghi phiên bản ứng dụng |
| `--vendor` | Ghi tên nhà cung cấp |
| `--description` | Mô tả ứng dụng |

Ví dụ đặt heap cho JVM chạy ứng dụng:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --java-options "-Xms256m" --java-options "-Xmx1g" --dest packages
~~~

Phân biệt:

- `--java-options` tác động tới JVM chạy ứng dụng.
- `--arguments` là đối số ứng dụng nhận trong mảng `args`.
- Tùy chọn JVM của compiler, chẳng hạn `javac -J-Xmx1g`, không liên quan đến heap của ứng dụng được đóng gói.

Có thể tạo launcher bổ sung bằng file properties. Ví dụ `admin.properties`:

~~~properties
module=com.example.app/com.example.app.Main
java-options=-Xmx2g
arguments=--mode admin
~~~

Tạo launcher bổ sung:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --add-launcher Admin=admin.properties --dest packages
~~~

Launcher `Admin` có cấu hình riêng. Kiểm tra cú pháp properties và các giá trị được hỗ trợ bằng tài liệu `jpackage` của JDK đang sử dụng.

## 10. Tổ chức resource và dữ liệu ứng dụng

Thư mục input của ứng dụng classpath có thể chứa JAR chính, dependency và resource cần được phân phối. Với ứng dụng modular, các resource nằm trong module hoặc được cung cấp qua cấu hình build phù hợp.

Không nên giả định mọi tệp trong thư mục làm việc hiện tại sẽ tự động được đóng gói. Hãy xác định rõ:

- Tệp cấu hình mặc định.
- Resource, template và dữ liệu tĩnh.
- File log hoặc thư mục dữ liệu có thể ghi.
- Native library và dependency bên ngoài.
- File giấy phép và thông tin phiên bản.

Ứng dụng không nên ghi dữ liệu thay đổi vào thư mục cài đặt nếu hệ điều hành hoặc chính sách cài đặt giới hạn quyền ghi. Hãy dùng vị trí dữ liệu ứng dụng phù hợp với hệ điều hành và người dùng.

Nếu ứng dụng dùng đường dẫn tương đối, kiểm tra working directory thực tế khi khởi chạy từ launcher được tạo bởi `jpackage`. Không giả định working directory luôn bằng thư mục chứa source hoặc thư mục gốc dự án.

## 11. Kiểm tra runtime image và application image

Sau khi tạo runtime image bằng `jlink`, kiểm tra module:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

Kiểm tra phiên bản Java của runtime:

~~~powershell
.\runtime\bin\java.exe -version
~~~

Có thể chạy trực tiếp module bằng runtime image:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main
~~~

Sau khi tạo application image, kiểm tra:

- Có launcher ứng dụng.
- Có thư mục runtime đi kèm nếu cấu hình yêu cầu bundling runtime.
- Module cần thiết xuất hiện trong runtime.
- Tệp cấu hình, resource và dependency được đặt đúng vị trí.
- Đối số và tùy chọn JVM được truyền đúng.
- Ứng dụng chạy trên máy sạch không có JDK dự án.

Trên Windows, dùng PowerShell để liệt kê nội dung image:

~~~powershell
Get-ChildItem -Recurse packages/ExampleApp
~~~

Trên Linux/macOS:

~~~bash
find packages/ExampleApp -maxdepth 4 -type f
~~~

Tên và vị trí launcher có thể thay đổi theo OS và kiểu đóng gói. Dùng danh sách file thực tế để xác định đường dẫn chạy.

## 12. Những giới hạn và lưu ý về nền tảng

### 12.1. Runtime image gắn với hệ điều hành và kiến trúc

Runtime image chứa binary native của JDK. Vì vậy, hãy tạo image cho OS/architecture mục tiêu. Không thể dùng một image Windows làm runtime cho ứng dụng Linux chỉ bằng cách đổi tên thư mục.

### 12.2. Native library cần đúng nền tảng

Nếu ứng dụng dùng JNI hoặc thư viện native, hãy đưa đúng binary cho nền tảng đích và kiểm thử trên môi trường tương ứng. Đảm bảo các dependency native mà thư viện yêu cầu cũng có sẵn.

### 12.3. Module được nạp động cần được bổ sung

`jlink` xây dựng runtime từ module graph và thông tin có thể phân tích. Reflection, plugin, service hoặc tên class đọc từ cấu hình có thể cần module được thêm tường minh. Kiểm thử tính năng thực tế trên runtime image đã đóng gói.

### 12.4. Công cụ build khác với runtime người dùng

`jpackage` và `jlink` là công cụ của JDK. Runtime image phân phối cho người dùng thường chỉ chứa thành phần runtime cần chạy ứng dụng, không nhất thiết chứa các công cụ đóng gói này.

## 13. Lỗi thường gặp khi tạo runtime image hoặc application image

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jpackage` không được nhận diện | PATH đang trỏ tới JRE hoặc JDK bin chưa được cấu hình | Dùng JDK phù hợp và kiểm tra `jpackage --version` |
| `Module ... not found` | Module path thiếu module ứng dụng hoặc dependency | Kiểm tra `--module-path`, `module-info.java` và tên module |
| `jlink` báo thiếu dependency | Root module không có đủ module bắt buộc trên module path | Phân tích dependency và bổ sung module |
| Application image thiếu class | JAR chính hoặc dependency không được đưa vào input/module path | Kiểm tra `--input`, `--main-jar`, `--module-path` và nội dung JAR |
| Ứng dụng chạy bằng JDK nhưng lỗi trong image | Runtime image thiếu module, service, resource hoặc native library | Kiểm tra `--list-modules`, service binding và dependency động |
| Launcher không tìm thấy file cấu hình | Đường dẫn tương đối dựa trên working directory khác dự kiến | Dùng đường dẫn dữ liệu phù hợp và kiểm thử từ launcher thực tế |
| Installer không tạo được | Thiếu công cụ đóng gói hệ điều hành hoặc sai loại installer | Kiểm tra yêu cầu OS/tooling và `jpackage --help` |
| Runtime image không chạy trên máy đích | Image được tạo cho OS/CPU khác hoặc thiếu native dependency | Build lại trên nền tảng mục tiêu và kiểm thử |
| Ứng dụng lỗi do module nạp bằng reflection | Module không nằm trong runtime image | Bổ sung module cần thiết và kiểm thử đường nạp động |
| Gói cài đặt có phiên bản hoặc icon sai | Metadata/resource chưa được cấu hình đúng | Kiểm tra `--app-version`, `--icon`, `--resource-dir` và thông tin vendor |

## 14. Quy trình phát hành khuyến nghị

Một quy trình ổn định có thể thực hiện theo thứ tự:

1. Xác định ứng dụng là modular hay classpath.
2. Xác định hệ điều hành và kiến trúc đích.
3. Build JAR hoặc module từ source bằng JDK đã chọn.
4. Xác định module dependency, service provider, reflection và native library.
5. Quyết định để `jpackage` tự tạo runtime hay tạo runtime riêng bằng `jlink`.
6. Tạo application image bằng `jpackage --type app-image`.
7. Chạy thử launcher trên môi trường sạch, không dựa vào JDK cài sẵn của máy build.
8. Kiểm tra resource, cấu hình, log, đối số, heap và native dependency.
9. Tạo installer tương ứng với nền tảng.
10. Kiểm thử cài đặt, nâng cấp, khởi chạy và gỡ cài đặt trên máy đích.

Tạo và kiểm thử application image trước khi tạo installer giúp tách lỗi runtime/launcher khỏi lỗi riêng của hệ thống đóng gói.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định ứng dụng modular hay classpath.
- [ ] Đã chọn OS và kiến trúc đích.
- [ ] Đã chọn để `jpackage` tự tạo runtime hay truyền `--runtime-image`.
- [ ] Nếu dùng runtime tùy chỉnh, đã tạo và kiểm tra bằng `jlink`.
- [ ] Runtime có đủ module, service provider và dependency cần thiết.
- [ ] Đã kiểm tra launcher, đối số ứng dụng và `--java-options`.
- [ ] Đã đóng gói đầy đủ JAR, dependency, resource và file cấu hình.
- [ ] Native library tương thích nền tảng và kiến trúc.
- [ ] Đã kiểm thử application image trên máy sạch.
- [ ] Đã chọn installer phù hợp: MSI/EXE, DMG/PKG, DEB hoặc RPM.
- [ ] Đã kiểm thử cài đặt, nâng cấp, chạy và gỡ cài đặt.
- [ ] Đã xác nhận version, vendor, icon và license metadata.

Runtime image cung cấp Java runtime đã được liên kết cho ứng dụng; application image do `jpackage` tạo thêm launcher và nội dung ứng dụng; installer đóng gói application image theo hệ điều hành. Với ứng dụng đơn giản, hãy để `jpackage` tự tạo runtime nếu dependency được phân tích đầy đủ. Khi cần kiểm soát module closure, service binding hoặc nội dung runtime, hãy tạo image riêng bằng `jlink` rồi truyền qua `--runtime-image`. Luôn kiểm thử application image và installer trên đúng nền tảng phát hành.
