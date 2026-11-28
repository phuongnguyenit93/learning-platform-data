# Kiểm tra module java.base và jdk.httpserver trên JDK đầy đủ hoặc runtime image tùy biến

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Hiểu vai trò khác nhau của `java.base` và `jdk.httpserver`, kiểm tra sự hiện diện của chúng trên JDK đầy đủ và custom runtime image, rồi tạo image tối giản bằng `jlink` để chạy Simple Web Server. Nội dung tập trung vào các module và công cụ còn áp dụng trên JDK hiện đại.

## 1. Vì sao cần kiểm tra module?

Từ Java 9, Java Platform Module System (JPMS) chia nền tảng thành các module có tên. Một ứng dụng có thể chạy trên JDK đầy đủ nhưng thất bại khi được triển khai bằng runtime image tùy biến vì image chỉ chứa những module đã được liên kết.

Hai module trong bài có vai trò rất khác:

- **`java.base`** chứa các API nền tảng như `java.lang`, `java.util`, `java.io`, `java.net`, `java.nio`, `java.time`, `java.lang.reflect` và `java.lang.invoke`. Đây là module nền tảng mà mọi module Java khác phụ thuộc trực tiếp hoặc gián tiếp.
- **`jdk.httpserver`** là module đặc thù của JDK, cung cấp API HTTP server trong `com.sun.net.httpserver`, SPI thay thế implementation và công cụ `jwebserver`. Đây là module tùy chọn trong một runtime image tối giản.

Với nội dung Java 18, sự phân chia này giúp xác định nơi chạy các ví dụ:

| Thay đổi Java 18 | Module / công cụ liên quan | Ý nghĩa khi tạo runtime image |
|---|---|---|
| JEP 400 — UTF-8 by Default | `java.base`, đặc biệt `java.nio.charset` | Module nền tảng luôn có trong runtime image |
| JEP 408 — Simple Web Server | `jdk.httpserver`, `jwebserver`, `SimpleFileServer` | Phải giữ module này nếu ứng dụng cần API hoặc server tĩnh |
| JEP 413 — Javadoc snippet | Công cụ `javadoc` / standard doclet thuộc JDK | Công cụ tạo tài liệu thường chạy từ JDK build, không phải trách nhiệm của runtime image tối giản |
| JEP 418 — Internet-Address Resolution SPI | `java.base`, `java.net.spi` | API nằm trong module nền tảng |
| JEP 416 — Core reflection dùng MethodHandle | `java.base`, `java.lang.reflect` và `java.lang.invoke` | API và triển khai runtime cốt lõi có trong module nền tảng |

**Không nên kết luận rằng mọi tính năng của Java 18 nằm trong một module mới.** JEP 408 bổ sung Simple Web Server vào module `jdk.httpserver` vốn đã tồn tại từ Java 9; các API liên quan JEP 400, 416 và 418 thuộc `java.base`. Bản thân module `java.base` và `jdk.httpserver` đều có mốc `Since: 9` ở cấp module, nhưng các package và API bên trong có lịch sử riêng.

## 2. Hiểu hai module trước khi chạy lệnh

### 2.1. `java.base`: nền tảng bắt buộc

Tài liệu API JDK mô tả `java.base` là module định nghĩa các API nền tảng của Java SE. Những package thường dùng gồm:

| Package | Vai trò | Liên hệ với bài Java 18 |
|---|---|---|
| `java.lang` | Kiểu cơ bản của ngôn ngữ, `String`, `Class`, `System`, `Runtime` | Mọi chương trình Java đều dùng |
| `java.util` | Collections, `ServiceLoader`, properties, tiện ích | Có thể dùng khi kiểm tra provider hoặc cấu hình |
| `java.io` | Stream và I/O | Đọc/ghi dữ liệu |
| `java.net` và `java.net.spi` | Mạng và các SPI liên quan | `InetAddressResolverProvider` của JEP 418 |
| `java.nio`, `java.nio.charset`, `java.nio.file` | Buffer, charset, file system | UTF-8 mặc định JEP 400 |
| `java.lang.reflect` | Reflection | `Method`, `Field`, `Constructor` |
| `java.lang.invoke` | Method handles và dynamic invocation | `MethodHandle`, `MethodHandles` của JEP 416 |
| `java.time` | Ngày, giờ và khoảng thời gian | API thời gian hiện đại |

Mọi module đều có quan hệ phụ thuộc ngầm (mandated) tới `java.base`; vì vậy ứng dụng thông thường không cần thêm `requires java.base;` vào `module-info.java`.

Một runtime image Java hợp lệ luôn cần `java.base`. Khi tạo image bằng `jlink`, module này được giải quyết như dependency nền tảng. Không thể tạo một runtime Java bình thường mà loại bỏ `java.base` để giảm dung lượng.

### 2.2. `jdk.httpserver`: module đặc thù của JDK

`jdk.httpserver` cung cấp:

- `com.sun.net.httpserver`: API HTTP server cấp cao, có các kiểu như `HttpServer`, `HttpsServer`, `HttpHandler`, `HttpExchange`.
- `com.sun.net.httpserver.spi`: SPI cho phép thay thế implementation của HTTP server.
- `SimpleFileServer`: server HTTP tĩnh đơn giản dành cho thử nghiệm, phát triển và gỡ lỗi.
- Công cụ `jwebserver`: cách khởi chạy Simple Web Server từ dòng lệnh.

JDK 27 API specification ghi rõ module này là **JDK-specific**, có `Since: 9` và cung cấp công cụ `jwebserver`. JEP 408 giới thiệu Simple Web Server trong Java 18; vì vậy cần phân biệt **tuổi đời module** với **thời điểm bổ sung tính năng**.

Một module đặc thù JDK không đồng nghĩa với một API nội bộ không dùng được. `jdk.httpserver` có API được tài liệu JDK công bố, nhưng ứng dụng cần kiểm tra nó có trong runtime image và khai báo module phù hợp.

### 2.3. `java.base` không thay thế `jdk.httpserver`

`java.base` có các API mạng tổng quát như `java.net`, `java.nio.channels` và SPI phân giải địa chỉ. Những API đó không tự cung cấp `HttpServer` hoặc `SimpleFileServer`.

Ví dụ:

- Dùng `InetAddress.getByName` hoặc `InetAddressResolverProvider`: thuộc `java.base`.
- Dùng `com.sun.net.httpserver.HttpServer` hoặc `SimpleFileServer`: cần `jdk.httpserver`.
- Dùng `jwebserver`: cần module `jdk.httpserver` và công cụ/entry point tương ứng.

Vì vậy, một image chỉ chứa `java.base` vẫn có thể chạy nhiều ứng dụng Java, nhưng không thể chạy code tham chiếu `com.sun.net.httpserver` nếu thiếu module `jdk.httpserver`.

## 3. Phân biệt JDK đầy đủ và custom runtime image

### 3.1. JDK đầy đủ

Một bộ JDK đầy đủ thường có:

- Runtime launcher `java`.
- Compiler `javac`.
- Công cụ tài liệu `javadoc`.
- Công cụ liên kết image `jlink`.
- Các module trong thư mục module/JMOD của JDK, bao gồm `java.base` và `jdk.httpserver` trong các bản phân phối JDK đầy đủ thông thường.
- Công cụ `jwebserver` khi module/tool được nhà phân phối đóng gói.

Có thể kiểm tra bằng:

~~~shell
java --version
java --list-modules
jwebserver --version
jlink --version
~~~

Trên Windows, các lệnh trên thường có executable `.exe` nhưng không cần gõ phần đuôi.

Không nên chỉ kiểm tra thư mục `bin` rồi kết luận module đã được resolve. Một JDK có thể chứa module nhưng module không nằm trong graph đã resolve của một ứng dụng cụ thể. `java --list-modules` cho biết các module quan sát được trong runtime image; `java --describe-module` cho biết descriptor của module. Khi cần xem graph được resolve lúc khởi chạy ứng dụng, dùng thêm `--show-module-resolution`.

### 3.2. Custom runtime image do `jlink` tạo

`jlink` liên kết một tập module cùng các dependency bắc cầu của chúng thành runtime image tùy biến. Mục tiêu thường là giảm thành phần triển khai, chỉ giữ API và module mà ứng dụng cần.

Image thường có launcher `bin/java` và cấu trúc runtime riêng. Nó **không phải JDK đầy đủ** chỉ vì có thể chạy chương trình Java.

Một image tối giản có thể không có:

- `javac` để biên dịch source.
- `javadoc` để tạo tài liệu.
- `jlink` để tạo image tiếp theo.
- `jwebserver` như một executable riêng.
- Các module JDK tùy chọn mà ứng dụng không yêu cầu.

Điều này không phải lỗi. Nếu ứng dụng chỉ cần chạy và các module đã đủ, runtime image tối giản là kết quả đúng. Nếu cần compiler hoặc tool khác ở môi trường build, dùng JDK đầy đủ cho build; không cần nhồi tất cả công cụ vào runtime production.

### 3.3. Quan hệ giữa module được chọn và dependency

`jlink --add-modules` chỉ định các **root module**. `jlink` tự resolve và thêm các dependency bắc cầu cần thiết.

Ví dụ, khi chọn `jdk.httpserver`, `java.base` sẽ có trong image vì module HTTP server phụ thuộc nền tảng Java. Không cần khai báo một danh sách mọi module phụ thuộc bằng tay.

~~~text
jlink --add-modules jdk.httpserver
                 |
                 v
       Root module: jdk.httpserver
                 |
                 v
       Resolve requires dependencies
                 |
                 v
       Runtime image có jdk.httpserver
       và các dependency, gồm java.base
~~~

Nếu ứng dụng có module riêng khai báo `requires jdk.httpserver;`, khi chọn module ứng dụng làm root thì resolver sẽ đưa module HTTP server và dependency của nó vào image. Nếu code dùng API qua reflection hoặc cấu hình runtime mà không có quan hệ `requires` rõ ràng, có thể cần thêm module làm root tường minh.

## 4. Kiểm tra trên JDK đầy đủ

### 4.1. Liệt kê module đang quan sát được

Trên Linux/macOS:

~~~shell
java --list-modules | grep -E '^(java.base|jdk.httpserver)@'
~~~

Trên PowerShell:

~~~powershell
java --list-modules |
    Select-String '^(java\.base|jdk\.httpserver)@'
~~~

Trong JDK đầy đủ thông thường, kết quả sẽ có dạng:

~~~text
java.base@27
jdk.httpserver@27
~~~

Số phiên bản hiển thị tùy JDK cài đặt. Dùng lệnh sau để xem toàn bộ danh sách nếu cần:

~~~shell
java --list-modules
~~~

**Cách diễn giải:**

- Có `java.base`: runtime có module nền tảng.
- Có `jdk.httpserver`: module HTTP server có trong tập module quan sát được của runtime hiện tại.
- Không có `jdk.httpserver`: có thể đang dùng custom runtime image hoặc bản phân phối đã lược module; kiểm tra JDK home và danh sách module đầy đủ.

### 4.2. Mô tả từng module

~~~shell
java --describe-module java.base
java --describe-module jdk.httpserver
~~~

Lệnh đầu cho biết module nền tảng, package export và các service liên quan. Lệnh thứ hai cho biết package `com.sun.net.httpserver`, SPI và mô tả module JDK HTTP server.

Trên Windows, nếu cần chỉ định một JDK cụ thể:

~~~powershell
& (Join-Path $env:JAVA_HOME 'bin/java.exe') --describe-module java.base
& (Join-Path $env:JAVA_HOME 'bin/java.exe') --describe-module jdk.httpserver
~~~

Trên Linux/macOS:

~~~shell
"$JAVA_HOME/bin/java" --describe-module java.base
"$JAVA_HOME/bin/java" --describe-module jdk.httpserver
~~~

Lệnh `--describe-module` kiểm tra descriptor của module theo góc nhìn runtime đang được gọi; nó không tự chứng minh module đã được resolve vào graph của ứng dụng. Nếu dùng nhầm executable qua PATH, kết quả có thể không mô tả JDK bạn dự định kiểm tra.

Để xem module graph của một ứng dụng modular đang khởi chạy:

~~~shell
java --show-module-resolution -m com.example.preview/com.example.preview.Main
~~~

Đầu ra liệt kê các module được resolve và quan hệ phụ thuộc. Thay tên module/lớp main bằng entry point của ứng dụng thực tế.

### 4.3. Kiểm tra module file trong JDK đầy đủ

JDK đầy đủ thường có thư mục `jmods`. Có thể xem descriptor của module:

~~~shell
jmod describe "$JAVA_HOME/jmods/jdk.httpserver.jmod"
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

Trên PowerShell:

~~~powershell
jmod describe (Join-Path $env:JAVA_HOME 'jmods/jdk.httpserver.jmod')
jmod describe (Join-Path $env:JAVA_HOME 'jmods/java.base.jmod')
~~~

`jmod describe` đọc metadata của file JMOD. Nó hữu ích để kiểm tra module có trong bộ JDK dùng để tạo image hay không; nó không chứng minh module đã được resolve vào một runtime image đang chạy. Muốn kiểm tra image, chạy `bin/java --list-modules` từ chính image đó.

Một runtime image do `jlink` tạo thường không chứa thư mục `jmods` như JDK đầy đủ. Đừng dùng việc thiếu JMOD trong image để kết luận module đã bị xóa khỏi runtime.

## 5. Kiểm tra công cụ `jwebserver` trên JDK đầy đủ

### 5.1. Kiểm tra lệnh và module

~~~shell
jwebserver --version
jwebserver --help
java --describe-module jdk.httpserver
~~~

`jwebserver` là công cụ của module `jdk.httpserver`. Theo tool specification JDK 27, nó phục vụ một cây thư mục tĩnh qua HTTP/1.1, hỗ trợ `GET` và `HEAD`; không hỗ trợ HTTPS hay HTTP/2.

Mặc định server bind loopback và cổng 8000. Có thể chọn thư mục và địa chỉ:

~~~shell
jwebserver -b 127.0.0.1 -p 8000 -d public
~~~

Từ terminal khác:

~~~shell
curl -I http://127.0.0.1:8000/
~~~

Dừng bằng `Ctrl+C`. Dùng thư mục thử nghiệm không chứa secret hoặc file cấu hình nhạy cảm.

### 5.2. Khởi chạy qua module entry point

Tài liệu module cho biết entry point của `jdk.httpserver` cũng có thể chạy qua:

~~~shell
java -m jdk.httpserver
~~~

Có thể truyền các tùy chọn tương tự:

~~~shell
java -m jdk.httpserver -b 127.0.0.1 -p 8000 -d public
~~~

Cách này đặc biệt hữu ích trong custom runtime image: image có thể không chứa executable riêng `jwebserver` nhưng có launcher `java` và module `jdk.httpserver`. Nếu module có main entry point, `java -m` khởi chạy nó trực tiếp.

**Không nhầm công cụ với API:** `jwebserver` là cách dùng nhanh cho tệp tĩnh; `com.sun.net.httpserver.SimpleFileServer` là API để tạo và quản lý server từ code; `HttpServer`/`HttpsServer` là API cấp cao hơn cho handler ứng dụng. Simple Web Server vẫn không phải web server production đầy đủ.

## 6. Tạo custom runtime image chỉ với module HTTP server và dependency

### 6.1. Image thử nghiệm chỉ để chạy Simple Web Server

Dùng `jlink` từ một JDK đầy đủ. Tại thư mục làm việc, chạy:

~~~shell
jlink --add-modules jdk.httpserver --output http-runtime
~~~

`jlink` sẽ đưa `jdk.httpserver` và dependency bắc cầu cần thiết vào image. `java.base` luôn được resolve vì là nền tảng bắt buộc.

Kiểm tra image vừa tạo trên Linux/macOS:

~~~shell
./http-runtime/bin/java --list-modules
./http-runtime/bin/java --describe-module java.base
./http-runtime/bin/java --describe-module jdk.httpserver
~~~

Trên Windows PowerShell:

~~~powershell
.\http-runtime\bin\java.exe --list-modules
.\http-runtime\bin\java.exe --describe-module java.base
.\http-runtime\bin\java.exe --describe-module jdk.httpserver
~~~

Kết quả cần có cả `java.base` và `jdk.httpserver`. Image cũng có thể chứa các dependency khác do module resolution đưa vào; đừng kỳ vọng chỉ đúng hai module. Danh sách này xác nhận module có trong image, còn graph thực tế của ứng dụng phụ thuộc entry point và các tùy chọn khởi chạy.

### 6.2. Chạy server trong image

Nếu image có module `jdk.httpserver`, thử:

~~~shell
./http-runtime/bin/java -m jdk.httpserver -b 127.0.0.1 -p 8000 -d public
~~~

Trên Windows:

~~~powershell
.\http-runtime\bin\java.exe -m jdk.httpserver -b 127.0.0.1 -p 8000 -d public
~~~

Nếu server khởi động, mở `http://127.0.0.1:8000/` hoặc gửi HEAD request. Phép thử này xác nhận cả module lẫn entry point hoạt động trong image.

Image được tạo cho mục đích runtime; không giả định nó có `javac`, `javadoc` hay `jlink`. Tạo image bằng JDK đầy đủ, sau đó kiểm tra image qua launcher của chính nó.

### 6.3. Tạo launcher có tên riêng (tùy chọn)

Nếu muốn gọi `jwebserver` bằng tên riêng trong image, có thể yêu cầu `jlink` tạo launcher:

~~~shell
jlink --add-modules jdk.httpserver --launcher jwebserver=jdk.httpserver --output http-runtime
~~~

Trên Linux/macOS có thể viết nhiều dòng:

~~~shell
jlink --add-modules jdk.httpserver \
  --launcher jwebserver=jdk.httpserver \
  --output http-runtime
~~~

Trên PowerShell có thể dùng dấu nối dòng backtick; ví dụ:

~~~powershell
jlink --add-modules jdk.httpserver `
      --launcher jwebserver=jdk.httpserver `
      --output http-runtime
~~~

Launcher do `jlink` tạo có tên `jwebserver` và trỏ đến main entry của module. Nếu không cần tên lệnh riêng, dùng `bin/java -m jdk.httpserver` là đủ. Luôn kiểm tra `http-runtime/bin` sau khi link thay vì giả định mọi file launcher từ JDK đầy đủ được sao chép nguyên vẹn.

## 7. Tạo image cho ứng dụng modular dùng `jdk.httpserver`

### 7.1. Khai báo dependency trong module ứng dụng

Ví dụ module ứng dụng `com.example.preview` dùng `SimpleFileServer`:

~~~java
module com.example.preview {
    requires jdk.httpserver;
}
~~~

Trong class main:

~~~java
package com.example.preview;

import com.sun.net.httpserver.SimpleFileServer;
import java.net.InetSocketAddress;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) {
        Path root = Path.of(args.length == 0 ? "public" : args[0])
                .toAbsolutePath();

        var address = new InetSocketAddress("127.0.0.1", 8000);
        var server = SimpleFileServer.createFileServer(
                address, root, SimpleFileServer.OutputLevel.INFO);

        server.start();
    }
}
~~~

Ở đây `requires jdk.httpserver;` là dependency tường minh. Module resolution sẽ tìm `jdk.httpserver` và các dependency của nó. `java.base` vẫn được yêu cầu ngầm, không cần ghi thêm.

### 7.2. Biên dịch module ứng dụng

Giả sử cấu trúc source và output:

~~~text
src/
└── com.example.preview/
    ├── module-info.java
    └── com/example/preview/Main.java
mods/
~~~

Dùng JDK đầy đủ:

~~~shell
javac \
  -d mods/com.example.preview \
  src/com.example.preview/module-info.java \
  src/com.example.preview/com/example/preview/Main.java
~~~

Javac dùng các module hệ thống của JDK đang chạy để giải quyết `requires jdk.httpserver;`. Nếu biên dịch không tìm thấy module, kiểm tra compiler có thuộc JDK đầy đủ và module đó có trong JDK đang dùng hay không. Trên Windows PowerShell, dấu phân cách module path của lệnh jlink ở phần tiếp theo khác Linux/macOS.

### 7.3. Liên kết image chứa ứng dụng

Với output module đã biên dịch trong thư mục `mods`:

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.preview \
  --launcher preview=com.example.preview/com.example.preview.Main \
  --output preview-image
~~~

Trên Windows, dấu phân cách nhiều phần tử module path là dấu chấm phẩy:

~~~powershell
$modulePath = "$env:JAVA_HOME/jmods;mods"
jlink --module-path $modulePath --add-modules com.example.preview --launcher preview=com.example.preview/com.example.preview.Main --output preview-image
~~~

Vì `com.example.preview` khai báo `requires jdk.httpserver;`, module server sẽ được resolve vào image. `java.base` cũng được đưa vào như dependency bắt buộc. Có thể thêm `jdk.httpserver` tường minh vào `--add-modules` nếu muốn thể hiện nó là root module độc lập, nhưng dependency khai báo trong module descriptor đã đủ cho trường hợp này.

Chạy launcher:

~~~shell
./preview-image/bin/preview public
~~~

Trên Windows:

~~~powershell
.\preview-image\bin\preview.bat public
~~~

Sau đó kiểm tra bằng browser hoặc `curl -I`. Với ứng dụng thật, cần đóng gói tài nguyên, cấu hình port và quản lý vòng đời server theo yêu cầu sản phẩm.

## 8. Dùng `jdeps` để hỗ trợ xác định module cần thiết

Khi ứng dụng lớn, không nên tự đoán danh sách module. `jdeps` có thể phân tích phụ thuộc tĩnh và đề xuất module platform cần cho một JAR hoặc module:

~~~shell
jdeps --print-module-deps --recursive app.jar
~~~

Với ứng dụng modular hoặc có dependency trên module path, chỉ định đường dẫn phù hợp:

~~~shell
jdeps --print-module-deps --recursive --module-path "mods:lib/*" app.jar
~~~

Kết quả là danh sách module cần thiết theo phân tích tĩnh. Có thể dùng danh sách này làm đầu vào cho `jlink --add-modules`, sau đó bổ sung module cần thiết do cấu hình runtime, service loading hoặc reflection.

**Giới hạn của jdeps:** phân tích bytecode tĩnh không thể luôn suy ra lớp được tải bằng tên từ cấu hình, resource, reflection, JNI hoặc mọi provider được chọn động. Nếu ứng dụng dùng ServiceLoader, xem xét `jlink --bind-services` và xác minh provider cần thiết có trong image. Không dùng `jdeps` như bằng chứng tuyệt đối rằng image đã chứa mọi thứ ứng dụng cần.

Quy trình an toàn:

1. Chạy `jdeps` trên artefact và dependency thực tế.
2. Kiểm tra module descriptor (`module-info`) và `uses/provides` nếu có.
3. Xác định module cần thêm tường minh như `jdk.httpserver`.
4. Tạo image bằng `jlink`.
5. Chạy `java --list-modules` từ image.
6. Chạy smoke/integration test trên chính image đó.
7. Khi thay dependency hoặc JDK patch, tạo lại image và chạy lại test.

## 9. Hiểu đúng service binding và module resolution

### 9.1. Module dependency và service provider là hai việc khác nhau

`requires` biểu thị module phụ thuộc module khác trong graph. `uses`/`provides` mô tả quan hệ dịch vụ thông qua ServiceLoader.

- `requires jdk.httpserver` cho biết ứng dụng cần module HTTP server.
- `uses com.sun.net.httpserver.spi.HttpServerProvider` cho biết module dùng service provider.
- `provides ... with ...` khai báo module cung cấp implementation.
- `jlink --bind-services` yêu cầu linker đưa các provider phù hợp và dependency của chúng vào image.

Không phải ứng dụng nào cũng cần `--bind-services`. Nếu chỉ dùng implementation mặc định đã có trong module `jdk.httpserver`, trước tiên kiểm tra module graph và chạy thử. Nếu ứng dụng phụ thuộc provider bên ngoài, cần xác định provider module và dùng service binding hoặc thêm module tương ứng theo yêu cầu.

### 9.2. Kiểm tra provider có sẵn

`jlink` hỗ trợ:

~~~shell
jlink --suggest-providers com.sun.net.httpserver.spi.HttpServerProvider
~~~

Lệnh này giúp xem module provider quan sát được trên module path. Nó không tự cài provider và không thay cho kiểm tra cấu hình runtime thực tế.

Khi dùng custom runtime image, ghi rõ service provider nào phải có, module nào cung cấp và cách ứng dụng tìm thấy chúng. Tránh phụ thuộc vào provider tình cờ được cài trên máy phát triển nhưng không được đóng gói trong image.

## 10. Phân biệt lỗi module với lỗi classpath, API và tool

| Hiện tượng | Lớp vấn đề có thể gặp | Hướng kiểm tra |
|---|---|---|
| `Module jdk.httpserver not found` | Module không có trong image hoặc module path | `java --list-modules`, `--describe-module`, kiểm tra JDK/JMOD |
| `package com.sun.net.httpserver is not visible` | Module chưa được resolve hoặc ứng dụng modular chưa khai báo dependency | Thêm `requires jdk.httpserver;` hoặc cấu hình module phù hợp |
| `ClassNotFoundException` | Classpath/module path hoặc tên lớp động không đúng | Kiểm tra dependency và class loader |
| `NoClassDefFoundError` | Thiếu lớp khi runtime link/load, module hoặc dependency không có | Đối chiếu module graph và dependency thực tế |
| `jwebserver: command not found` | Custom image không có executable riêng hoặc PATH không đúng | Dùng `java -m jdk.httpserver` nếu module có mặt |
| `java -m jdk.httpserver` báo không tìm thấy module | Runtime image chưa chứa module | Tạo lại image với `--add-modules jdk.httpserver` |
| `javac` không tồn tại trong image | Image runtime không đóng gói compiler | Biên dịch ở JDK đầy đủ; không yêu cầu runtime image làm build JDK |
| Server chạy nhưng không truy cập được | Bind address, port, firewall hoặc request sai | Kiểm tra loopback, port, log và GET/HEAD |
| App chạy ở JDK đầy đủ nhưng lỗi trong image | Image thiếu module, resource, provider hoặc cấu hình | Chạy test trên image, kiểm tra module graph và service binding |

Phân biệt `ClassNotFoundException` và `NoClassDefFoundError` theo ngữ cảnh: cái đầu thường xuất hiện khi code chủ động tìm class qua class loader; cái sau thường xuất hiện khi JVM cần một lớp trong quá trình liên kết/khởi tạo nhưng không thể cung cấp. Không xử lý cả hai bằng cách thêm bừa mọi module vào image.

## 11. Các lưu ý khi triển khai custom runtime image

### 11.1. Image phải được cập nhật cùng JDK

`jlink` tạo runtime image tại thời điểm build. Khi nhà phân phối phát hành bản vá bảo mật hoặc JDK update mới, image cũ **không tự cập nhật**. Đội phát triển chịu trách nhiệm tạo image mới từ JDK đã vá, chạy kiểm thử và triển khai lại.

Đây là yêu cầu vận hành quan trọng hơn việc chỉ làm image nhỏ. Cần lưu phiên bản JDK/vendor dùng để link, module list và checksum/artefact image trong pipeline.

### 11.2. Image gắn với nền tảng mục tiêu

Runtime image chứa launcher và thư viện native phù hợp nền tảng. Không mặc định tạo một image trên Windows rồi dùng nguyên trạng trên Linux hoặc macOS. Tạo và kiểm thử image theo OS/architecture được triển khai, hoặc dùng cơ chế cross-target chính thức của toolchain nếu có và đã được xác minh.

### 11.3. Đừng loại module theo kích thước nếu chưa hiểu phụ thuộc

Giảm dung lượng image có thể hữu ích, nhưng loại module một cách tùy tiện dễ tạo lỗi chỉ xuất hiện ở runtime. Đặc biệt:

- Không thể bỏ `java.base`.
- Giữ `jdk.httpserver` nếu ứng dụng cần `com.sun.net.httpserver` hoặc `jwebserver`.
- Nếu dùng charset ngoài nhóm chuẩn trong `java.base`, kiểm tra có cần `jdk.charsets`.
- Nếu dùng provider, reflection, JNI hoặc cấu hình động, kiểm tra phần phụ thuộc không thể suy ra bằng phân tích tĩnh.
- Kiểm thử image thực tế, không chỉ kiểm thử trên JDK đầy đủ.

### 11.4. Công cụ build và công cụ runtime có thể khác nhau

Một pipeline hợp lý có thể:

- Dùng JDK đầy đủ để chạy `javac`, `javadoc`, `jdeps` và `jlink`.
- Tạo image chỉ gồm module cần thiết như `java.base`, `jdk.httpserver` và module ứng dụng.
- Đưa runtime image cùng ứng dụng đến máy đích.
- Dùng JDK đầy đủ trong môi trường phát triển, không cần cài JDK đầy đủ trên máy chỉ chạy ứng dụng.

Không dùng runtime image tối giản như môi trường biên dịch hoặc tạo Javadoc nếu image không chứa các tool đó.

## 12. Bài thực hành

### Bài 1 — Kiểm tra hai module trên JDK đầy đủ

Chạy `java --list-modules`, `java --describe-module java.base` và `java --describe-module jdk.httpserver`. Dùng `jwebserver --version` để xác minh tool.

**Tiêu chí đạt:** Chỉ ra `java.base` là module nền tảng; `jdk.httpserver` là module đặc thù JDK có API HTTP server và Simple Web Server.

### Bài 2 — Tạo image chỉ có HTTP server

Dùng `jlink --add-modules jdk.httpserver --output http-runtime`. Chạy `http-runtime/bin/java --list-modules` và xác nhận `java.base` cùng `jdk.httpserver` có mặt.

**Tiêu chí đạt:** Giải thích được vì sao `java.base` xuất hiện dù không chỉ định rõ và vì sao image có thể không có `javac`/`javadoc`.

### Bài 3 — Chạy Simple Web Server từ runtime image

Chạy `http-runtime/bin/java -m jdk.httpserver -b 127.0.0.1 -p 8000 -d public`, sau đó gửi `curl -I`.

**Tiêu chí đạt:** Server chạy qua module entry point ngay cả khi không có executable `jwebserver` riêng.

### Bài 4 — Tạo app module có dependency

Tạo `module-info.java` với `requires jdk.httpserver;`, dùng `SimpleFileServer` và link image bằng `jlink`.

**Tiêu chí đạt:** Ứng dụng chạy trong image, module server và dependency được resolve, không cần JDK đầy đủ trên máy đích.

### Bài 5 — Kiểm tra giới hạn của jdeps

Chạy `jdeps --print-module-deps` trên artefact. Thêm một class được tải qua tên từ cấu hình hoặc một service provider để thảo luận vì sao phân tích tĩnh có thể chưa đủ.

**Tiêu chí đạt:** Biết bổ sung module cho dependency động và kiểm thử trên image cuối cùng.

## 13. Tài liệu chính thức

1. [Module java.base — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/module-summary.html): phạm vi API nền tảng và các package được export.
2. [Module jdk.httpserver — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): API HTTP server, SPI, SimpleFileServer và công cụ `jwebserver`.
3. [The jlink Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): tạo runtime image, root modules, dependency resolution, launcher và service binding.
4. [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--list-modules`, `--describe-module`, `--add-modules` và module launcher.
5. [The jwebserver Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): giới hạn HTTP/1.1, GET/HEAD, bind address, port và cách chạy qua module.
6. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu và phạm vi tính năng được đưa vào Java 18.
7. [Creating Runtime and Application Images with jlink — dev.java](https://dev.java/learn/organizing/jlink/): cách chọn module và dependency để tạo image.
8. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): liên hệ default charset với API nền tảng.
9. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): API resolver trong nền tảng Java.
10. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai reflection trên nền tảng API cốt lõi.

**Kết quả cần đạt:** Có thể kiểm tra `java.base` và `jdk.httpserver` trên JDK đầy đủ, tạo custom runtime image giữ module HTTP server, xác nhận dependency `java.base` được đưa vào, rồi chạy `jwebserver` qua module entry point. Hiểu rõ JDK đầy đủ phục vụ build và công cụ, còn runtime image tùy biến chỉ chứa những module và thành phần được chọn cho ứng dụng.
