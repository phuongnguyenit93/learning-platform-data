# Custom runtime image bằng jlink

Custom runtime image là một bộ runtime Java được tạo riêng cho ứng dụng hoặc nhóm ứng dụng, chỉ chứa các module Java cần thiết để chạy chúng. Thay vì yêu cầu máy đích cài toàn bộ JDK, nhóm phát triển có thể dùng công cụ `jlink` để liên kết các module thành một thư mục runtime độc lập, sau đó phân phối cùng ứng dụng.

Cách làm này giúp kiểm soát phiên bản runtime, giảm các thành phần không cần thiết và tạo launcher riêng cho ứng dụng. Tuy nhiên, runtime image phải được tạo đúng module graph, đúng phiên bản JDK và đúng hệ điều hành/kiến trúc mục tiêu. Một image thiếu module, resource, service provider hoặc native dependency có thể build thành công nhưng lỗi khi chạy.

## 1. Custom runtime image là gì?

JDK là bộ công cụ phát triển Java, thường bao gồm:

- Java launcher và JVM để chạy ứng dụng.
- Các module nền tảng như `java.base`, `java.logging`, `java.sql` và nhiều module khác.
- Trình biên dịch `javac`, công cụ đóng gói `jar`, `jmod`, `javap`, `jdeps`.
- Các công cụ phát triển và tài liệu như `javadoc`, `jshell` cùng những tiện ích khác.

Runtime image do `jlink` tạo ra chỉ chứa các module và thành phần runtime được liên kết cho tập ứng dụng đã chọn. Nó có thể chứa launcher `java`, thư viện runtime, file cấu hình, legal notices và các resource cần thiết. Thông thường nó không chứa toàn bộ công cụ phát triển như `javac` hoặc `javadoc`.

Một runtime image không chỉ là một file JAR hoặc một thư mục chứa riêng `java.exe`. Đây là cấu trúc runtime hoàn chỉnh do JDK tạo ra, có thể được chạy trực tiếp trên nền tảng tương thích mà không cần cài một JDK đầy đủ riêng trên máy đích.

Custom runtime image thường được dùng khi:

- Phân phối ứng dụng desktop hoặc command-line kèm runtime riêng.
- Triển khai dịch vụ Java trên máy chủ hoặc container.
- Tạo runtime có tập module nhỏ, dễ kiểm soát.
- Giữ runtime của ứng dụng nhất quán giữa các môi trường.
- Giảm bề mặt thành phần được triển khai và loại bỏ công cụ không cần trên máy chạy ứng dụng.

## 2. jlink hoạt động như thế nào?

`jlink` đọc module từ module path, phân giải module graph bắt đầu từ các module gốc được chỉ định, rồi liên kết các module cần thiết vào image đầu ra.

Một quy trình cơ bản:

1. Biên dịch ứng dụng thành named module hoặc chuẩn bị modular JAR.
2. Đặt module ứng dụng và các module JDK cần thiết trên module path.
3. Dùng `--add-modules` để chọn module gốc.
4. `jlink` giải quyết các khai báo `requires` và thêm module phụ thuộc cần thiết.
5. Các plugin được chọn có thể loại bỏ debug metadata, header file, man page hoặc nén resource.
6. `jlink` tạo runtime image tại thư mục `--output`.

Mô hình:

~~~text
Application source
       |
       v
     javac
       |
       v
Application module
       |
       +------------------+
       |                  |
       v                  v
Application module    JDK jmods
       |                  |
       +--------+---------+
                |
                v
              jlink
                |
                v
        Custom runtime image
                |
                v
        Application launcher
~~~

`jlink` không biên dịch mã nguồn Java thay cho `javac` và không tự sửa ứng dụng để biến một chương trình classpath thành named module. Công cụ này liên kết module đã được biên dịch hoặc đóng gói.

## 3. Điều kiện đầu vào

Để tạo custom runtime image, cần chuẩn bị:

- Một JDK có công cụ `jlink`.
- Module ứng dụng có module descriptor tường minh, thường là `module-info.class`.
- Các module phụ thuộc có thể tìm thấy trên module path.
- Cấu hình main class nếu muốn tạo launcher riêng.
- Thư mục output mới hoặc rỗng để nhận runtime image.

Ứng dụng chỉ chạy trên classpath, không có module descriptor, cần được chuyển thành named module phù hợp trước khi đưa vào quy trình `jlink`. Automatic module có thể dùng trong một số tình huống module path, nhưng không phải đầu vào phù hợp để `jlink` liên kết thành runtime image. Hãy kiểm tra module descriptor và dependency trước khi tạo image.

Kiểm tra các công cụ:

~~~bash
java -version
javac -version
jlink --version
~~~

Nên dùng `javac` và `jlink` thuộc cùng một bản JDK để tránh khác biệt giữa module metadata, compiler và linker. Thư mục `jmods` của JDK chứa các module nền tảng ở định dạng JMOD; đây thường là một phần của module path khi liên kết.

## 4. Ví dụ thực hành: tạo ứng dụng modular

Ví dụ này tạo một ứng dụng nhỏ có tên module `com.acme.hello`. Ứng dụng dùng `java.logging` để minh họa dependency module và in một lời chào.

Cấu trúc thư mục nguồn:

~~~text
jlink-demo/
└── src/
    ├── module-info.java
    └── com/
        └── acme/
            └── hello/
                └── Main.java
~~~

Tệp `src/module-info.java`:

~~~java
module com.acme.hello {
    requires java.logging;
}
~~~

Tệp `src/com/acme/hello/Main.java`:

~~~java
package com.acme.hello;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOGGER = Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        LOGGER.fine("Greeting requested");
        System.out.println("Hello, " + name + "!");
    }
}
~~~

`LOGGER.fine` tạo một lời ghi log ở mức FINE. Với cấu hình logging mặc định, mức này không được in ra console, vì vậy stdout của ví dụ chỉ có dòng chào.

## 5. Biên dịch module

Chạy các lệnh từ thư mục gốc `jlink-demo`.

Trên Linux hoặc macOS:

~~~bash
javac -d mods/com.acme.hello src/module-info.java src/com/acme/hello/Main.java
~~~

Trên Windows PowerShell:

~~~powershell
javac -d mods/com.acme.hello src/module-info.java src/com/acme/hello/Main.java
~~~

Sau khi biên dịch, cấu trúc module đầu ra:

~~~text
mods/
└── com.acme.hello/
    ├── module-info.class
    └── com/
        └── acme/
            └── hello/
                └── Main.class
~~~

Thư mục `mods` là module path root. Thư mục con `com.acme.hello` là module directory chứa module descriptor và các class của module.

Có thể kiểm tra module descriptor:

~~~bash
java --describe-module com.acme.hello --module-path mods
~~~

Lệnh này yêu cầu Java launcher đọc module từ module path và mô tả các khai báo của module. Kết quả thể hiện module `com.acme.hello` yêu cầu `java.logging`.

## 6. Phân tích dependency bằng jdeps

Trước khi liên kết image, có thể dùng `jdeps` để phân tích dependency module tĩnh của ứng dụng:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.hello
~~~

Với ví dụ trên, danh sách dependency module có thể gồm:

~~~text
java.base,java.logging
~~~

`java.base` là module nền tảng cốt lõi mà mọi module Java đều đọc ngầm. `java.logging` được yêu cầu tường minh trong `module-info.java`.

Tùy chọn `--print-module-deps` in danh sách module phụ thuộc đã rút gọn, có thể dùng làm đầu vào cho `jlink --add-modules`. Kết quả phân tích tĩnh không nhất thiết phát hiện mọi dependency được nạp động qua reflection, tên lớp trong cấu hình, service provider hoặc native code. Hãy xem lại các đường nạp động và kiểm thử ứng dụng thực tế.

Nếu ứng dụng dùng `ServiceLoader`, kiểm tra khai báo `uses` và `provides` trong module descriptor cũng như các provider module cần có trong image.

## 7. Tạo custom runtime image bằng jlink

`jlink` cần tìm module ứng dụng và module JDK. Vì vậy, module path thường gồm thư mục `jmods` của JDK và thư mục `mods` chứa module ứng dụng.

### Linux và macOS

Dấu phân cách các phần tử module path là dấu hai chấm:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.hello \
  --launcher hello=com.acme.hello/com.acme.hello.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output image
~~~

### Windows PowerShell

Dấu phân cách các phần tử module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.hello --launcher hello=com.acme.hello/com.acme.hello.Main --strip-debug --no-header-files --no-man-pages --output image
~~~

Giải thích các tùy chọn:

| Tùy chọn | Vai trò |
|---|---|
| `--module-path` | Nơi tìm JMOD và module ứng dụng. |
| `--add-modules` | Chọn module gốc cần liên kết; các dependency được phân giải theo module graph. |
| `--launcher` | Tạo launcher riêng có tên `hello` để chạy module và main class đã chỉ định. |
| `--strip-debug` | Loại bỏ debug information khỏi các class được liên kết. |
| `--no-header-files` | Không đưa header file phát triển vào image. |
| `--no-man-pages` | Không đưa man page vào image. |
| `--output` | Thư mục runtime image đầu ra. |

Tên launcher theo cú pháp `name=module/mainclass`. Trong ví dụ, `hello` là tên lệnh, `com.acme.hello` là module và `com.acme.hello.Main` là main class.

Thư mục `image` nên chưa tồn tại hoặc đang rỗng. Nếu image cũ còn ở đó, hãy chọn đường dẫn output mới hoặc dọn đúng thư mục build do dự án quản lý trước khi chạy lại `jlink`.

Các tùy chọn loại bỏ debug/header/man page giúp image gọn hơn. Nếu cần điều tra production bằng line number hoặc cần header để tích hợp native, hãy cân nhắc giữ lại các thành phần tương ứng.

## 8. Chạy ứng dụng từ runtime image

Sau khi `jlink` hoàn tất, runtime image có launcher mặc định `java` và launcher riêng `hello`.

Trên Linux/macOS:

~~~bash
./image/bin/hello Ada
~~~

Trên Windows PowerShell:

~~~powershell
.\image\bin\hello Ada
~~~

Output chính xác:

~~~text
Hello, Ada!
~~~

Có thể chạy ứng dụng bằng Java launcher mặc định của image mà không cần custom launcher:

~~~bash
./image/bin/java -m com.acme.hello/com.acme.hello.Main Ada
~~~

Trên Windows:

~~~powershell
.\image\bin\java.exe -m com.acme.hello/com.acme.hello.Main Ada
~~~

Output:

~~~text
Hello, Ada!
~~~

Custom launcher giúp người dùng chạy ứng dụng bằng tên lệnh riêng mà không cần nhớ cú pháp module/main class. Nó vẫn dùng runtime image đã liên kết và module được chọn khi tạo image.

Nếu ứng dụng cần tham số, truyền chúng sau tên launcher như khi gọi một chương trình dòng lệnh thông thường.

## 9. Cấu trúc runtime image

Cấu trúc cụ thể phụ thuộc hệ điều hành và phiên bản JDK. Một image thường có dạng:

~~~text
image/
├── bin/
│   ├── java
│   └── hello
├── conf/
├── legal/
├── lib/
│   ├── modules
│   └── ...
└── release
~~~

Trên Windows, thư mục `bin` có các executable như `java.exe` và launcher riêng; có thể có thêm file batch hỗ trợ launcher. Tên file và các thư viện native trong image khác nhau theo nền tảng.

Các thành phần chính:

- `bin`: Java launcher, custom launcher và các executable cần thiết.
- `conf`: cấu hình runtime.
- `legal`: thông tin giấy phép và legal notice của các module được liên kết.
- `lib`: runtime library, module image, file cấu hình và native library cần thiết.
- `release`: metadata về bản phân phối runtime.

Image là một cây thư mục có thể được đóng gói thành archive hoặc đưa vào installer theo quy trình phát hành của sản phẩm. Không nên chỉ sao chép riêng `bin/java` ra máy đích vì JVM còn cần các thư viện và dữ liệu trong những thư mục khác.

## 10. Kiểm tra module có trong image

Dùng Java launcher bên trong image để liệt kê các module đã được liên kết:

~~~bash
./image/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\image\bin\java.exe --list-modules
~~~

Với ví dụ, danh sách có thể gồm:

~~~text
com.acme.hello
java.base@24.0.2
java.logging@24.0.2
~~~

Phần phiên bản sau ký tự @ phụ thuộc bản JDK dùng để tạo image. Danh sách trên minh họa kết quả từ JDK 24.0.2; khi dùng JDK khác, phiên bản hiển thị sẽ khác.

Có thể mô tả một module cụ thể:

~~~bash
./image/bin/java --describe-module java.logging
~~~

Nếu image thiếu một module mà ứng dụng cần, hãy kiểm tra module descriptor, dependency và lệnh `--add-modules`. Không thêm tất cả module một cách tùy tiện chỉ để làm lỗi biến mất; hãy xác định module nào thực sự cần thiết.

## 11. Chọn module gốc và quản lý module graph

`--add-modules` nhận một hoặc nhiều tên module, phân cách bằng dấu phẩy:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.hello,java.sql --output image
~~~

Các module được chọn là root modules. `jlink` tiếp tục phân giải các module được yêu cầu qua `requires` và đưa dependency cần thiết vào image.

Một số điểm cần hiểu:

- `java.base` luôn có mặt trong runtime Java.
- Khai báo `requires` tạo dependency module tường minh.
- Dependency bắc cầu có thể làm module graph mở rộng.
- `requires static` chỉ yêu cầu module trong thời gian biên dịch và không tự buộc module đó có mặt lúc chạy.
- Module được nạp động qua reflection hoặc cấu hình có thể không xuất hiện trong phân tích dependency tĩnh.

Có thể dùng `ALL-MODULE-PATH` để chọn mọi module trên module path, nhưng cách này thường làm image lớn hơn và không thể hiện rõ tập dependency tối thiểu. Chỉ dùng khi mục tiêu thực sự là đưa tất cả module trên module path vào quá trình phân giải.

Tùy chọn `--limit-modules` giới hạn tập module có thể quan sát khi phân giải. Nó hữu ích cho các runtime được kiểm soát chặt, nhưng nếu đặt quá hẹp, quá trình liên kết có thể báo thiếu module. Chỉ dùng sau khi hiểu đầy đủ dependency graph.

## 12. Service binding và ServiceLoader

Một ứng dụng có thể sử dụng Service Provider Interface (SPI) để tìm implementation ở runtime. Module tiêu thụ khai báo `uses`, còn module cung cấp khai báo `provides ... with ...`.

Ví dụ module ứng dụng:

~~~java
module com.acme.app {
    uses com.acme.spi.GreetingProvider;
}
~~~

Module provider:

~~~java
module com.acme.greeting.english {
    requires com.acme.spi;
    provides com.acme.spi.GreetingProvider
        with com.acme.greeting.english.EnglishGreetingProvider;
}
~~~

Khi liên kết runtime, nếu cần tự động đưa provider module và dependency của chúng vào image, có thể dùng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output image
~~~

`--bind-services` yêu cầu jlink liên kết các module cung cấp service cho các service được module đã chọn sử dụng, cùng dependency cần thiết. Tùy chọn này có thể làm image lớn hơn vì provider module cũng được đưa vào.

Nếu ứng dụng không dùng SPI hoặc đã chọn provider module rõ ràng, không nhất thiết phải bật service binding. Khi không chắc module nào cung cấp một service, có thể dùng `jlink --suggest-providers` với tên service type để xem gợi ý từ module path.

## 13. Tùy chỉnh kích thước và thành phần image

Một trong các lý do dùng jlink là giảm những thành phần không cần cho ứng dụng. Các plugin phổ biến:

| Tùy chọn | Tác động |
|---|---|
| `--strip-debug` | Loại bỏ debug metadata. |
| `--no-header-files` | Bỏ header file phục vụ phát triển native. |
| `--no-man-pages` | Bỏ trang hướng dẫn lệnh. |
| `--compress` | Nén resource trong image theo mức mà phiên bản JDK hỗ trợ. |
| `--bind-services` | Thêm provider module và dependency của service. |

Tùy chọn compression thay đổi theo phiên bản JDK. Một số bản cũ dùng giá trị số như `--compress=2`; các bản mới có thể hỗ trợ dạng `--compress=zip-6`. Hãy kiểm tra `jlink --list-plugins` và `jlink --help` trên đúng JDK dùng để build trước khi đưa tùy chọn compression vào script dùng chung.

Xem danh sách plugin:

~~~bash
jlink --list-plugins
~~~

Không nên tối ưu chỉ theo dung lượng. Loại bỏ debug metadata có thể làm việc điều tra lỗi khó hơn; bỏ header file có thể không phù hợp nếu sản phẩm còn cung cấp SDK native. Hãy xác định nội dung runtime và vận hành thực sự cần trước khi bật plugin.

## 14. Ứng dụng dùng resource, reflection hoặc native library

Module ứng dụng có thể chứa resource như file properties, template, certificate hoặc dữ liệu cần lúc chạy. Khi biên dịch và đóng gói module, bảo đảm resource được đặt trong cây module hoặc modular JAR đúng cách để chúng được liên kết vào image.

Một số dependency không thể suy ra hoàn toàn từ bytecode:

- Tên class được tạo từ chuỗi cấu hình và nạp bằng reflection.
- Service provider được phát hiện thông qua ServiceLoader.
- Driver hoặc plugin được đăng ký bên ngoài module graph tĩnh.
- Native library được nạp bằng `System.loadLibrary` hoặc `System.load`.
- File cấu hình hoặc dữ liệu nằm ngoài module.

Với reflection, module cần được đưa vào image nếu ứng dụng có thể nạp nó lúc chạy; đồng thời cần cấu hình quyền truy cập module phù hợp. Với SPI, xem xét `--bind-services` hoặc thêm provider module tường minh. Với native library, bảo đảm binary và các dependency native được phân phối, tìm thấy và tương thích với runtime image.

`jlink` liên kết các module Java; nó không tự biên dịch C/C++, không bảo đảm native dependency bên ngoài được cài trên máy đích và không thay thế quy trình đóng gói native library.

## 15. Khác biệt giữa classpath và module path

`jlink` làm việc với module graph, vì vậy module path là phần quan trọng của cấu hình.

| Khái niệm | Mục đích |
|---|---|
| Classpath | Tìm lớp và JAR theo cơ chế class loader truyền thống. |
| Module path | Tìm named module, modular JAR và JMOD để phân giải module graph. |
| JDK jmods | Các module nền tảng của JDK ở định dạng JMOD. |
| Application module directory | Thư mục chứa `module-info.class` và class của module ứng dụng. |
| Runtime image | Kết quả đã liên kết để chạy ứng dụng trên nền tảng tương thích. |

Một ứng dụng chạy được bằng `java -cp` chưa chắc có thể đưa thẳng vào `jlink`. Cần có module descriptor và các dependency phù hợp với module system.

Đối với ứng dụng cũ phụ thuộc nhiều thư viện classpath, có thể cần thiết kế module descriptor, kiểm tra package split, xác định dependency và thử chạy bằng module path trước khi liên kết runtime.

## 16. Tính tương thích nền tảng và phiên bản JDK

Runtime image có tính đặc thù nền tảng. Image được tạo trên Windows x64 không thể dùng nguyên trạng như runtime Linux x64 hoặc macOS ARM64. Các thư viện native, executable và định dạng binary phụ thuộc hệ điều hành/kiến trúc.

Quy trình build nên tạo image riêng cho từng target:

| Target | Runtime image cần tạo |
|---|---|
| Windows x64 | Image được tạo từ JDK và native dependency tương thích Windows x64. |
| Linux x64 | Image tương thích Linux x64 và ABI native được hỗ trợ. |
| Linux ARM64 | Image tương thích Linux AArch64. |
| macOS ARM64 | Image tương thích macOS trên Apple Silicon. |

Cũng cần kiểm soát phiên bản JDK. Module JMOD của JDK gắn với phiên bản phân phối; hãy dùng bộ JDK phù hợp để compile, link và kiểm thử image. Nếu muốn hỗ trợ nhiều phiên bản Java, hãy tạo và kiểm thử image theo từng phiên bản mục tiêu thay vì giả định một image dùng chung cho mọi runtime.

## 17. Đưa custom runtime image vào phân phối

`jlink` tạo thư mục image, chưa phải installer hoàn chỉnh. Quy trình phân phối thường gồm:

1. Tạo runtime image cho từng hệ điều hành/kiến trúc.
2. Đưa file cấu hình, dữ liệu ngoài module và resource triển khai vào vị trí được ứng dụng mong đợi.
3. Kiểm tra quyền thực thi của launcher trên Unix-like systems.
4. Đóng gói thư mục image cùng tài liệu và thành phần cần thiết.
5. Chạy thử trên môi trường sạch không có JDK đầy đủ.
6. Kiểm tra license/legal notices của các module được phân phối.
7. Ký hoặc xác minh artifact theo chính sách phát hành.
8. Kiểm thử cập nhật, rollback và cấu hình logging/diagnostics.

Không nên giả định máy đích đã có cùng thư viện hệ thống như máy build. Nếu ứng dụng cần native library hoặc công cụ bên ngoài, phải đưa chúng vào gói cài đặt hoặc ghi rõ dependency môi trường.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: Module ... not found` | Module path thiếu JMOD hoặc module ứng dụng. | Kiểm tra `--module-path`, tên module và vị trí module directory/JAR/JMOD. |
| `jlink` không chấp nhận ứng dụng classpath | Ứng dụng chưa có module descriptor tường minh. | Chuyển ứng dụng thành named module và khai báo dependency. |
| `FindException` hoặc module resolution error | Thiếu module được yêu cầu, phiên bản dependency không phù hợp hoặc module path sai. | Kiểm tra `module-info.java`, `jdeps` và module path. |
| Launcher chạy nhưng báo thiếu class | Module hoặc dependency không được đưa vào image, hoặc resource/dynamic dependency bị bỏ sót. | Xác định module cần thêm, kiểm tra reflection/service và chạy integration test. |
| `ServiceLoader` không tìm thấy provider | Provider module không được liên kết hoặc descriptor thiếu `provides`. | Thêm provider module hoặc dùng `--bind-services` phù hợp. |
| Image lớn hơn dự kiến | Chọn quá nhiều root module, bật `ALL-MODULE-PATH` hoặc liên kết service provider không cần thiết. | Phân tích dependency và chỉ chọn module gốc cần thiết. |
| Output directory không dùng được | Thư mục output đã tồn tại và không rỗng. | Chọn thư mục mới hoặc dọn đúng thư mục build đã xác định. |
| Image chạy trên máy build nhưng lỗi máy đích | Khác OS/CPU, thiếu native library hoặc shared library phụ thuộc. | Tạo image riêng cho target và kiểm thử trên môi trường tương thích. |
| Image không có công cụ mong muốn | Chỉ liên kết module runtime cần thiết; công cụ phát triển không được thêm. | Xác định công cụ có thể đóng gói riêng hoặc module JDK tương ứng có thể liên kết hay không. |
| Không tìm thấy launcher riêng | Tên launcher hoặc cú pháp module/main class sai, hoặc đang xem nhầm thư mục output. | Kiểm tra `--launcher` và danh sách file trong `image/bin`. |

Để chẩn đoán module resolution, có thể chạy jlink với `--verbose` để xem thông tin liên kết:

~~~bash
jlink --verbose --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.hello --output image
~~~

Kiểm tra danh sách module trong image bằng `java --list-modules` và thử chạy ứng dụng từ chính runtime image. Build thành công không thay thế được bước chạy thử.

## 19. Quy trình build và kiểm thử khuyến nghị

Một quy trình có thể tái lập nên thực hiện:

1. Chọn JDK và target platform.
2. Biên dịch ứng dụng thành named module.
3. Kiểm tra module descriptor và dependency.
4. Dùng `jdeps --print-module-deps` để hỗ trợ phân tích dependency tĩnh.
5. Xem xét reflection, ServiceLoader, resource, JNI và dependency ngoài module graph.
6. Dùng `jlink --module-path` và `--add-modules` để tạo image.
7. Thêm `--launcher` nếu muốn cung cấp command riêng.
8. Chỉ bật plugin tối ưu phù hợp với nhu cầu vận hành.
9. Liệt kê module bằng runtime image và kiểm tra launcher.
10. Chạy unit/integration test trên image cuối cùng.
11. Kiểm thử trên máy sạch và từng hệ điều hành/kiến trúc mục tiêu.
12. Lưu lại JDK version, module list, lệnh jlink và metadata artifact để tái tạo image.

Nếu muốn so sánh hai lần build, hãy giữ ổn định JDK, dependency, compiler options, module list và plugin. Thay đổi một trong các yếu tố đó có thể làm kích thước hoặc nội dung image khác nhau.

## 20. Checklist trước khi phát hành

- Ứng dụng là named module và có module descriptor hợp lệ.
- Tất cả module phụ thuộc đều được tìm thấy trên module path.
- Module gốc trong `--add-modules` phản ánh đúng ứng dụng.
- Service provider và dependency được thêm khi cần.
- Resource, reflection và native library đã được kiểm tra.
- Runtime image được tạo bằng JDK phù hợp với target.
- Launcher mặc định và launcher riêng đều chạy được.
- `java --list-modules` cho thấy đúng tập module dự kiến.
- Integration test chạy trên runtime image, không chỉ trên JDK phát triển.
- Image được thử trên môi trường sạch và đúng OS/CPU.
- Legal notices và yêu cầu phân phối được giữ lại.
- Script build ghi lại phiên bản JDK, module path, module roots và tùy chọn jlink.

Custom runtime image giúp phân phối ứng dụng Java cùng một runtime có tập module được kiểm soát. `jlink` giải quyết module graph từ các root module, liên kết runtime và tạo launcher trong image. Muốn image nhỏ mà vẫn chạy đúng, cần phân tích dependency, tính tới service/reflection/native code, kiểm thử image cuối cùng trên đúng nền tảng và duy trì quy trình build có thể tái lập.
