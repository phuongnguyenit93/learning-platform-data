# Module closure trong jlink

Khi tạo runtime image bằng `jlink`, bạn chọn một hoặc nhiều module gốc. Công cụ phân giải các module mà chúng phụ thuộc, rồi liên kết tập module cần thiết vào image. Tập hợp này được gọi là module closure (bao đóng module).

Hiểu module closure giúp kiểm soát nội dung runtime image, phát hiện dependency bị thiếu và tránh đưa quá nhiều module vào bản phân phối. Nó cũng giúp giải thích vì sao một ứng dụng chỉ khai báo một module gốc nhưng runtime image vẫn chứa nhiều module JDK và module ứng dụng khác.

Bài này sử dụng JDK 17 trở lên, giải thích cách chọn root modules, cách `requires` và service binding ảnh hưởng tới closure, cách phân tích dependency bằng `jdeps`, và cách kiểm tra runtime image sau khi liên kết.

## 1. Module closure là gì?

Một module Java khai báo dependency bằng các directive `requires` trong `module-info.java`. Khi một module được chọn làm module gốc, hệ thống module phải tìm và phân giải các module mà nó cần để hoạt động.

Ví dụ, module ứng dụng `com.example.app` khai báo:

~~~java
module com.example.app {
    requires com.example.lib;
    requires java.logging;
}
~~~

Khi `com.example.app` là root module, module resolver cần tìm:

- `com.example.app`: module gốc được chọn.
- `com.example.lib`: dependency do ứng dụng khai báo.
- `java.logging`: dependency khác do ứng dụng khai báo.
- `java.base`: module nền tảng được mọi module Java thông thường phụ thuộc ngầm định.

Các dependency lại có thể khai báo dependency của riêng chúng. Quá trình phân giải tiếp tục cho tới khi các dependency bắt buộc đã được giải quyết. Tập module có thể truy cập được từ các root module và các dependency được phân giải tạo thành module graph; module closure là tập module cần được đưa vào runtime image theo graph đó.

Một cách nhìn khái quát:

~~~text
com.example.app
├── com.example.lib
│   └── java.base
├── java.logging
│   └── java.base
└── java.base
~~~

Sơ đồ chỉ minh họa quan hệ dependency trực tiếp và gián tiếp. Trong module graph thực tế, một module có thể được yêu cầu bởi nhiều module nhưng chỉ được phân giải một lần.

## 2. Root modules quyết định điểm bắt đầu

`jlink` dùng tùy chọn `--add-modules` để chỉ định root modules cần liên kết.

Cú pháp:

~~~text
jlink --module-path <module-path> --add-modules <module>[,<module>...] --output <directory>
~~~

Ví dụ chọn một module ứng dụng:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
~~~

Trong đó:

- `--module-path` chỉ định nơi tìm module, gồm JMOD hệ thống của JDK và module ứng dụng.
- `--add-modules` chọn module gốc.
- `--output` chỉ định thư mục runtime image.

Có thể chọn nhiều root modules, phân tách bằng dấu phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,com.example.tool --output runtime
~~~

Mỗi root module có thể kéo theo dependency riêng. Nếu hai root cùng phụ thuộc `java.logging`, module này chỉ cần xuất hiện một lần trong image.

Một giá trị đặc biệt là `ALL-MODULE-PATH`, dùng để chọn tất cả module quan sát được trên module path làm root:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules ALL-MODULE-PATH --output runtime
~~~

Cách này tiện khi thử nghiệm hoặc cần liên kết tất cả module có sẵn, nhưng thường tạo image lớn vì nhiều module không cần cho ứng dụng cũng trở thành root. Với sản phẩm, hãy bắt đầu từ module ứng dụng thực sự cần chạy.

## 3. Cách các directive requires ảnh hưởng đến closure

### 3.1. requires

`requires` khai báo dependency module. Khi module A yêu cầu module B, B cần được tìm thấy và phân giải để A hoạt động.

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Nếu `com.example.lib` không có trên module path hoặc không thể phân giải, quá trình biên dịch hoặc liên kết sẽ báo lỗi tương ứng.

### 3.2. requires transitive

`requires transitive` vừa khai báo dependency, vừa làm cho các module đọc module hiện tại có thể đọc module được yêu cầu theo quy tắc readability.

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

Nếu module khác yêu cầu `com.example.api`, dependency `com.example.model` cũng trở thành một phần của module graph cần phân giải. Modifier `transitive` chủ yếu ảnh hưởng khả năng đọc module của các module phụ thuộc; nó không phải một lệnh thêm module tùy ý ngoài dependency graph.

### 3.3. requires static

`requires static` biểu thị dependency cần thiết lúc biên dịch nhưng có thể vắng mặt khi chạy:

~~~java
module com.example.app {
    requires static com.example.optional;
}
~~~

Dependency này là tùy chọn ở runtime. Nếu module tùy chọn có mặt và được phân giải, nó có thể tham gia graph; nếu vắng mặt, riêng directive này không bắt buộc runtime phải có module đó.

Hãy cẩn thận nếu ứng dụng thực sự nạp class từ module tùy chọn bằng reflection, cấu hình hoặc tên lớp được đọc lúc runtime. Khi tính năng đó được bật, module cần có mặt trong runtime image và phải được phân giải. Có thể thêm nó tường minh bằng `--add-modules`.

### 3.4. requires static transitive

Có thể kết hợp hai modifier:

~~~java
module com.example.api {
    requires static transitive com.example.optional.api;
}
~~~

Dependency vẫn tùy chọn ở runtime, trong khi khả năng đọc được truyền tiếp cho module phụ thuộc theo quy tắc `transitive`. Khi đóng gói, cần xác định module tùy chọn có thực sự được dùng trong cấu hình runtime hay không.

## 4. Module closure và module readability là hai khái niệm khác nhau

Module closure cho biết những module nào được phân giải và có trong graph. Readability quyết định một module có thể đọc các kiểu public từ module khác theo quy tắc JPMS hay không.

Việc một module đã có trong runtime image không tự động cho phép mọi package của nó được truy cập.

Các directive có vai trò khác nhau:

| Directive | Vai trò |
|---|---|
| `requires` | Khai báo dependency và khả năng đọc module được yêu cầu |
| `requires transitive` | Truyền khả năng đọc dependency cho module phụ thuộc |
| `exports` | Cho phép module khác truy cập các kiểu public trong package được xuất |
| `opens` | Cho phép truy cập reflective sâu vào package theo phạm vi được mở |
| `uses` | Khai báo module sử dụng một service |
| `provides ... with ...` | Khai báo module cung cấp implementation cho service |

Ví dụ, module A có thể nằm trong closure nhưng package nội bộ của nó chưa được export cho module B. B vẫn không thể truy cập các kiểu trong package đó theo cách thông thường.

Nếu lỗi xảy ra do package chưa export hoặc chưa open, thêm module vào `--add-modules` không giải quyết được vấn đề. Cần kiểm tra module descriptor và quyền truy cập package.

## 5. Service binding có thể mở rộng module closure

Java ServiceLoader cho phép ứng dụng tìm implementation của một service khi chạy. Một module tiêu thụ service khai báo `uses`; module cung cấp implementation khai báo `provides`.

Ví dụ, module ứng dụng có thể khai báo:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Greeting;
}
~~~

Module provider khai báo:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.Greeting
        with com.example.provider.DefaultGreeting;
}
~~~

Nếu provider không được yêu cầu trực tiếp bởi root module nào, chỉ phân giải dependency thông thường có thể chưa đưa provider vào image.

Tùy chọn `--bind-services` yêu cầu `jlink` liên kết các module provider cho service được các module trong graph sử dụng, cùng các dependency cần thiết:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --bind-services --output runtime
~~~

Khi nào cần dùng:

- Ứng dụng dùng `ServiceLoader`.
- Provider được tìm thấy trên module path.
- Provider không được kéo vào graph bằng một `requires` thông thường.
- Runtime image cần chứa implementation để service discovery hoạt động.

`--bind-services` có thể làm image lớn hơn vì bổ sung provider modules và dependency của chúng. Chỉ bật khi ứng dụng cần service binding hoặc khi bạn muốn runtime image bao gồm các provider tương ứng.

Có thể hỏi `jlink` module nào cung cấp một service:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --suggest-providers com.example.spi.Greeting
~~~

Tên service cần là fully qualified class name của service interface. Lệnh này hỗ trợ tìm provider có sẵn trên module path.

## 6. Ví dụ thực hành: hai module và dependency closure

Ví dụ sau tạo hai module:

- `com.example.lib`: cung cấp lớp `MessageService`.
- `com.example.app`: gọi thư viện trên và dùng `java.logging`.

Cấu trúc dự án:

~~~text
project/
├── src/
│   ├── com.example.lib/
│   │   ├── module-info.java
│   │   └── com/example/lib/MessageService.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/
└── runtime/
~~~

Nội dung `src/com.example.lib/module-info.java`:

~~~java
module com.example.lib {
    exports com.example.lib;
}
~~~

Nội dung `src/com.example.lib/com/example/lib/MessageService.java`:

~~~java
package com.example.lib;

public class MessageService {
    public String message() {
        return "Hello from module closure!";
    }
}
~~~

Nội dung `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.lib;
    requires java.logging;
}
~~~

Nội dung `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.lib.MessageService;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(Main.class.getName());
        logger.fine("Application started");
        System.out.println(new MessageService().message());
    }
}
~~~

Từ thư mục gốc `project`, biên dịch thư viện trước:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.lib, mods/com.example.app | Out-Null
javac -d mods/com.example.lib src/com.example.lib/module-info.java src/com.example.lib/com/example/lib/MessageService.java
~~~

Biên dịch ứng dụng với module path chứa module thư viện:

~~~powershell
javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

Chạy trực tiếp từ thư mục module đã biên dịch:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello from module closure!
~~~

Tạo runtime image chỉ định module ứng dụng làm root:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
~~~

Dù chỉ chọn `com.example.app`, image phải có các dependency cần thiết, gồm `com.example.lib`, `java.logging` và `java.base`. Dependency gián tiếp của các module này cũng được phân giải.

Chạy ứng dụng bằng Java runtime vừa tạo:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello from module closure!
~~~

Trên Linux/macOS, dùng dấu hai chấm trong module path và gọi executable `runtime/bin/java`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
./runtime/bin/java -m com.example.app/com.example.app.Main
~~~

Ví dụ này cho thấy `--add-modules` chọn điểm bắt đầu; `jlink` tự phân giải dependency được khai báo thay vì yêu cầu liệt kê thủ công từng module JDK.

## 7. Phân tích dependency trước khi liên kết bằng jdeps

`jdeps` là công cụ phân tích dependency ở cấp class và module. Nó hữu ích khi kiểm tra một JAR hoặc ứng dụng đã biên dịch để biết những module nền tảng nào được tham chiếu.

Với JAR ứng dụng và thư viện phụ thuộc:

~~~powershell
jdeps --print-module-deps --module-path "lib/*" app.jar
~~~

Lệnh in ra danh sách module cần thiết theo phân tích dependency tĩnh, thường ở dạng danh sách phân tách bằng dấu phẩy. Kết quả có thể dùng để hỗ trợ lựa chọn root module hoặc rà soát cấu hình liên kết.

Để xem chi tiết dependency:

~~~powershell
jdeps --list-deps --module-path "lib/*" app.jar
~~~

Với multi-release JAR, chỉ định release cần phân tích:

~~~powershell
jdeps --multi-release 17 --print-module-deps --module-path "lib/*" app.jar
~~~

Cần hiểu giới hạn của `jdeps`:

- Phân tích chủ yếu dựa trên tham chiếu có thể nhận diện trong bytecode.
- Tên class được tạo từ cấu hình, reflection hoặc nạp động có thể không được phát hiện đầy đủ.
- Service provider, plugin hoặc module được nạp theo điều kiện runtime cần được kiểm tra riêng.
- Dependency của thư viện bên ngoài phải được cung cấp trên classpath hoặc module path phù hợp để kết quả đầy đủ.

Dùng `jdeps` làm bằng chứng phân tích, sau đó kiểm thử trên runtime image thực tế.

## 8. Kiểm tra module closure trong runtime image

Sau khi `jlink` hoàn tất, dùng Java launcher bên trong image để liệt kê module đã được liên kết:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

Trên Linux/macOS:

~~~bash
./runtime/bin/java --list-modules
~~~

Với ví dụ hai module, hãy tìm các tên:

~~~text
com.example.app
com.example.lib
java.base
java.logging
~~~

Phiên bản hiển thị có thể khác theo JDK, và một image thực tế có thể chứa thêm module do các thành phần khác yêu cầu. Dùng danh sách này để xác nhận những module quan trọng đã có mặt.

Có thể kiểm tra module descriptor của module ứng dụng bằng:

~~~powershell
.\runtime\bin\java.exe --describe-module com.example.app
~~~

Lệnh `java --describe-module` hiển thị mô tả module trong môi trường runtime đang được gọi. Hãy dùng launcher bên trong image để xác minh module được liên kết trong chính image đó.

Kiểm tra sự tồn tại của launcher và các thư mục runtime:

~~~powershell
Get-ChildItem runtime
Get-ChildItem runtime/bin
~~~

Đừng chỉ dựa vào việc lệnh `jlink` kết thúc thành công. Hãy chạy ứng dụng, kiểm tra service provider, reflection, resource, native library và các tính năng được nạp động.

## 9. Giới hạn tập module với --limit-modules

`--limit-modules` giới hạn tập module mà công cụ có thể quan sát trong quá trình phân giải. Tùy chọn này có thể hữu ích khi muốn kiểm soát môi trường module và ngăn các module không mong muốn tham gia vào graph.

Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --limit-modules java.base,java.logging,com.example.lib,com.example.app --output runtime
~~~

Danh sách giới hạn phải bao gồm các module cần thiết cùng dependency của chúng. Nếu loại bỏ module mà một dependency bắt buộc cần, quá trình liên kết sẽ thất bại vì không thể phân giải graph.

`--limit-modules` không phải cách thay thế cho việc khai báo dependency đúng trong `module-info.java`. Trước khi áp dụng, hãy xác định graph thực tế bằng `jdeps`, module descriptor và thử liên kết. Khi không có nhu cầu giới hạn rõ ràng, chỉ định root modules bằng `--add-modules` thường đủ.

## 10. Dependency tĩnh và dependency động

Không phải mọi dependency runtime đều được thể hiện đầy đủ bằng các directive `requires`.

Các trường hợp cần chú ý:

| Cách sử dụng | Vì sao có thể thiếu trong closure tĩnh? | Cách xử lý |
|---|---|---|
| `requires static` | Dependency có thể vắng mặt khi chạy | Thêm module tường minh nếu tính năng runtime cần nó |
| `ServiceLoader` | Provider không nhất thiết được yêu cầu trực tiếp | Cân nhắc `--bind-services` hoặc thêm provider module |
| Reflection với tên class từ cấu hình | Tên class không xuất hiện như symbolic reference thông thường | Bổ sung module và kiểm thử đường chạy reflection |
| Plugin được nạp theo cấu hình | Plugin chỉ được biết lúc runtime | Xác định plugin modules và đưa vào module path/image |
| JNI hoặc native library | Native dependency không phải lúc nào cũng hiện ra trong Java module graph | Đóng gói native content phù hợp và kiểm thử theo OS/architecture |
| Resource được nạp theo tên | Resource có thể không được phát hiện từ dependency class | Kiểm tra resource có trong image và đúng đường dẫn |

Nếu ứng dụng dùng class name động, plugin hoặc native code, hãy lập danh sách các thành phần cần có dựa trên cấu hình triển khai và test thực tế. `jlink` chỉ có thể liên kết module có thể quan sát được trên module path.

## 11. Giảm kích thước image mà vẫn giữ closure đúng

Module closure quyết định module cần thiết. Các tùy chọn tối ưu image điều chỉnh nội dung hoặc cách lưu trữ, nhưng không thay thế việc chọn dependency đúng.

Một số tùy chọn hữu ích:

| Tùy chọn | Tác dụng |
|---|---|
| `--strip-debug` | Loại bỏ debug information khỏi các class file trong image |
| `--no-header-files` | Không đưa header files vào image |
| `--no-man-pages` | Không đưa man pages vào image |
| `--compress=1` | Nén resource bằng mức ZIP |
| `--compress=2` | Nén resource bằng ZIP và mức nén cao hơn theo hỗ trợ của JDK |

Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Hãy đo kích thước image và chạy lại test sau khi thay đổi các tùy chọn. Không bỏ module chỉ để giảm kích thước nếu ứng dụng hoặc tính năng runtime còn cần module đó.

## 12. Lỗi thường gặp khi xử lý module closure

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Module ... not found` | Module dependency không có trên module path | Kiểm tra `--module-path`, tên module và artifact đầu vào |
| `Module ... does not read ...` | Thiếu `requires` hoặc module readability không đúng | Kiểm tra `module-info.java` và `requires transitive` |
| `package ... is not visible` | Package không được export cho module gọi | Kiểm tra `exports` hoặc API module |
| `jlink` báo thiếu dependency | Root module kéo theo dependency không có hoặc không thể phân giải | Thêm đúng module dependency vào module path |
| Service không tìm thấy provider | Provider module chưa được liên kết | Kiểm tra `uses`/`provides`, dùng `--bind-services` hoặc thêm provider tường minh |
| Ứng dụng lỗi `ClassNotFoundException` khi chạy image | Class được nạp động không có trong image hoặc không được phân giải | Bổ sung module/plugin cần thiết và kiểm thử đường nạp động |
| Runtime image lớn bất thường | Chọn quá nhiều root hoặc dùng `ALL-MODULE-PATH` | Chỉ định root modules tối thiểu; phân tích dependency bằng `jdeps` |
| `--limit-modules` làm liên kết thất bại | Giới hạn đã loại bỏ dependency bắt buộc | Bổ sung module cần thiết hoặc bỏ giới hạn không phù hợp |
| Chạy được trên JDK đầy đủ nhưng lỗi trong image | JDK đầy đủ có nhiều module hơn image tùy chỉnh | Kiểm tra `--list-modules`, service, reflection, resource và native dependencies |

## 13. Quy trình xây dựng và xác minh closure

Thực hiện theo thứ tự:

1. Xác định module ứng dụng hoặc các module cần làm root.
2. Kiểm tra `module-info.java` của từng module, đặc biệt là `requires`, `requires transitive`, `requires static`, `uses` và `provides`.
3. Phân tích dependency của ứng dụng và thư viện bằng `jdeps`.
4. Xác định dependency động, service provider, plugin, reflection và native library cần có khi chạy.
5. Dùng `jlink --add-modules` để chọn root modules; bật `--bind-services` nếu cần service provider binding.
6. Chỉ dùng `--limit-modules` khi có lý do rõ ràng và đã xác nhận graph không thiếu dependency.
7. Tạo runtime image và kiểm tra bằng `java --list-modules`.
8. Chạy ứng dụng cùng test tích hợp trên runtime image, bao gồm các tính năng tải động và service.
9. Đo kích thước image; chỉ áp dụng tùy chọn strip/compress sau khi chức năng đã được xác nhận.

## 14. Checklist trước khi phát hành runtime image

- [ ] Root modules được chọn đúng theo ứng dụng cần chạy.
- [ ] Các directive `requires` và `requires transitive` đã được rà soát.
- [ ] Dependency `requires static` đã được đánh giá theo tính năng runtime thực tế.
- [ ] Service consumer/provider được khai báo và liên kết đầy đủ.
- [ ] Dependency phân tích bằng `jdeps` đã được đối chiếu với cấu hình runtime.
- [ ] Reflection, plugin, JNI, native library và resource động đã được kiểm tra.
- [ ] `--bind-services` được bật khi cần provider binding.
- [ ] `--limit-modules` không loại bỏ dependency bắt buộc.
- [ ] `java --list-modules` trên image hiển thị các module cần thiết.
- [ ] Ứng dụng và test tích hợp chạy thành công trên chính runtime image.
- [ ] Image được tạo và kiểm thử cho đúng hệ điều hành/kiến trúc mục tiêu.

Module closure là tập module được phân giải từ các root modules cùng dependency của chúng. Trong `jlink`, hãy chọn root phù hợp, kiểm tra `requires` và service binding, rồi xác minh kết quả bằng `jdeps`, `java --list-modules` và test trên runtime image. Những dependency được nạp động hoặc phụ thuộc môi trường cần được bổ sung và kiểm thử riêng để runtime tùy chỉnh vẫn chạy đủ chức năng.
