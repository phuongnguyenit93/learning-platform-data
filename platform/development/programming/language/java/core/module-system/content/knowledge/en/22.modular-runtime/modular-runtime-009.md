# Xác minh runtime image chứa đúng module

> Phạm vi: Java Platform Module System (JPMS) và công cụ **jlink**. Bài này hướng dẫn kiểm tra một runtime image đã tạo có chứa đúng module cần thiết hay không, xác minh descriptor và chạy thử ứng dụng trực tiếp bằng Java runtime trong image đó.

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định đúng runtime image cần kiểm tra và chạy đúng executable bên trong image.
- Liệt kê module thực sự có trong image bằng **java --list-modules**.
- Kiểm tra descriptor của một module bằng **java --describe-module**.
- Kiểm tra cấu trúc JIMAGE bằng công cụ **jimage**.
- Đối chiếu tập module cần thiết với các module đã link bằng **jdeps** và **jlink**.
- Phát hiện lỗi do thiếu module, dependency, service provider hoặc nhầm runtime.
- Chạy thử ứng dụng trên chính runtime image sẽ được phân phối.

## 1. Runtime image là gì?

**Runtime image** là một bản Java runtime đã được đóng gói thành một cây thư mục có thể chạy độc lập. Với JPMS, công cụ **jlink** tạo image từ các module được chọn cùng dependency của chúng.

Một image do jlink tạo thường có cấu trúc tương tự:

~~~text
runtime-image/
├── bin/
│   └── java
├── conf/
├── include/
├── legal/
├── lib/
│   ├── modules
│   └── ...
└── release
~~~

Trên Windows, executable thường là **bin/java.exe**. Một runtime image có thể được tối giản nên không nhất thiết có mọi thư mục hoặc công cụ của một JDK đầy đủ.

File **lib/modules** là kho module image ở định dạng JIMAGE. Các module được link vào image nằm trong đó. Thư mục **bin** chứa launcher dùng để khởi chạy ứng dụng bằng runtime đã tạo.

Điều cần xác minh là: **runtime image đích có chứa đúng các module mà ứng dụng cần, và chính runtime đó có thể khởi chạy ứng dụng hay không**. Kiểm tra JDK đang dùng để build chưa đủ, vì JDK build có thể chứa nhiều module hơn image đã link.

## 2. Xác định đúng runtime image trước khi kiểm tra

Giả sử image được tạo tại:

~~~text
project/
├── mods/
│   └── com.acme.app.jar
└── runtime-image/
    ├── bin/
    └── lib/
        └── modules
~~~

Hãy gọi executable bằng đường dẫn trực tiếp tới image:

Linux/macOS:

~~~bash
./runtime-image/bin/java --version
~~~

Windows PowerShell:

~~~powershell
.\runtime-image\bin\java.exe --version
~~~

Lệnh này xác nhận phiên bản Java của image đang kiểm tra. Không nên chỉ chạy **java --version** theo PATH của máy, vì lệnh đó có thể gọi một JDK/JRE khác.

Có thể xem đường dẫn Java home mà JVM thực sự sử dụng:

~~~bash
./runtime-image/bin/java -XshowSettings:properties -version
~~~

Trong phần system properties, tìm **java.home**. Giá trị cần trỏ đến runtime image dự định kiểm tra.

Kiểm tra thêm file **release** ở thư mục gốc image để xem thông tin phiên bản và nền tảng như **JAVA_VERSION**, **OS_NAME** và **OS_ARCH** nếu có. Đây là thông tin hỗ trợ nhận diện artifact; lệnh launcher từ image vẫn là cách trực tiếp để kiểm tra module runtime nhìn thấy.

## 3. Liệt kê module có trong runtime image

Cách nhanh nhất là chạy:

~~~bash
./runtime-image/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\runtime-image\bin\java.exe --list-modules
~~~

Launcher sẽ liệt kê các module có thể quan sát được từ runtime đang chạy rồi kết thúc. Mỗi dòng thường có dạng:

~~~text
java.base@21.0.2
java.logging@21.0.2
com.acme.app
~~~

Phần trước ký hiệu **@** là tên module; phần sau là phiên bản nếu module có thông tin phiên bản.

Ví dụ, nếu ứng dụng cần:

- **java.base**;
- **java.logging**;
- **com.acme.app**;

thì kết quả phải có đủ các tên module này. **java.base** luôn có trong Java runtime; các module còn lại phụ thuộc vào ứng dụng và cấu hình link.

Khi kiểm tra image, hãy chạy đúng **runtime-image/bin/java** và không thêm module path bên ngoài vào lệnh. Nếu truyền thêm **--module-path**, kết quả có thể phản ánh module quan sát được từ đường dẫn bổ sung, làm bạn nhầm module ngoài image là module đã được link vào image.

### Lọc nhanh danh sách module

Linux/macOS:

~~~bash
./runtime-image/bin/java --list-modules | grep -E '^(java.base|java.logging|com\.acme\.app)@?'
~~~

Windows PowerShell:

~~~powershell
.\runtime-image\bin\java.exe --list-modules | Select-String '^(java.base|java.logging|com\.acme\.app)@?'
~~~

Lệnh lọc chỉ hỗ trợ quan sát nhanh. Khi cần xác nhận tập module đầy đủ, hãy lưu và đối chiếu toàn bộ kết quả **--list-modules** với danh sách module mong đợi.

## 4. Kiểm tra descriptor của module cụ thể

Sau khi xác nhận tên module xuất hiện trong danh sách, dùng **--describe-module**:

~~~bash
./runtime-image/bin/java --describe-module java.logging
~~~

Kiểm tra module ứng dụng:

~~~bash
./runtime-image/bin/java --describe-module com.acme.app
~~~

Kết quả hiển thị tên module và các directive trong descriptor, ví dụ **requires**, **exports**, **opens**, **uses** hoặc **provides** nếu có.

Việc này giúp xác nhận:

- Tên module thực tế có đúng với tên mà ứng dụng yêu cầu không.
- Module có descriptor và các dependency như mong đợi không.
- Package nào được export.
- Service nào được sử dụng hoặc provider nào được khai báo.

Nếu module không có trong image, launcher sẽ báo không tìm thấy module khi mô tả. Đừng suy luận rằng một package tồn tại trong một JAR trên máy đồng nghĩa module đó đã có trong runtime image.

## 5. Xác minh module image bằng jimage

**jimage** là công cụ của JDK để kiểm tra nội dung kho module JIMAGE. File cần kiểm tra thường nằm tại:

~~~text
runtime-image/lib/modules
~~~

Liệt kê nội dung:

~~~bash
jimage list runtime-image/lib/modules
~~~

Trên Windows:

~~~powershell
jimage.exe list .\runtime-image\lib\modules
~~~

Kết quả hiển thị các module và entry bên trong image, chẳng hạn đường dẫn lớp thuộc **java.base** hoặc **java.logging**. Có thể tìm tên module hoặc package mong đợi để hỗ trợ điều tra khi danh sách launcher và cấu trúc image có dấu hiệu không khớp.

Kiểm tra tính toàn vẹn của kho image:

~~~bash
jimage verify runtime-image/lib/modules
~~~

**jimage verify** kiểm tra cấu trúc và tính toàn vẹn của file JIMAGE. Nó không thay thế việc xác nhận module graph, dependency của ứng dụng hay chạy thử ứng dụng.

Lưu ý: **jimage** là công cụ thuộc JDK và có thể không nằm trong runtime image tối giản. Hãy dùng công cụ từ một JDK tương thích để kiểm tra file **lib/modules** của image đích. Khi chạy **jimage list**, truyền đúng file **runtime-image/lib/modules**, không truyền thư mục gốc image.

## 6. Đối chiếu module cần thiết trước khi tạo image

Trước khi link, cần biết ứng dụng thực sự cần những module nào.

Ví dụ ứng dụng modular có descriptor:

~~~java
module com.acme.app {
    requires java.logging;
}
~~~

Ứng dụng có module chính **com.acme.app** và phụ thuộc **java.logging**. Khi resolve, **java.base** cũng luôn có mặt.

Có thể dùng **jdeps** để phân tích dependency tĩnh của JAR:

~~~bash
jdeps --print-module-deps --module-path mods mods/com.acme.app.jar
~~~

Tùy cấu trúc dự án, thêm các JAR/module phụ thuộc vào **--module-path** để jdeps có thể phân tích đầy đủ. Kết quả **--print-module-deps** là danh sách module dependency phù hợp để hỗ trợ xác định đầu vào cho jlink.

Ví dụ kết quả có thể là:

~~~text
java.base,java.logging
~~~

Đây là phân tích dependency mà jdeps nhận diện được từ bytecode và các module có thể quan sát. Reflection, tên lớp được tạo động, cấu hình ngoài, plugin hoặc dependency chỉ được nạp lúc chạy có thể không được nhận diện đầy đủ bằng phân tích tĩnh. Vì vậy, hãy kết hợp kết quả jdeps với module descriptor, cấu hình runtime và kiểm thử thực tế.

## 7. Tạo runtime image bằng jlink

**jlink** liên kết các module tường minh và dependency của chúng thành một runtime image. Công cụ này cần JDK và module đầu vào phù hợp; automatic module không thể được link trực tiếp. Nếu thư viện vẫn là automatic module, cần chuyển nó thành explicit module trước khi dùng làm đầu vào jlink.

Ví dụ, module ứng dụng đã được đóng gói tại **mods/com.acme.app.jar**, còn các JDK module nằm trong **$JAVA_HOME/jmods**.

Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime-image
~~~

Giải thích:

- **--module-path** cung cấp các module JDK trong thư mục **jmods** và module ứng dụng trong **mods**.
- **--add-modules com.acme.app** chọn module gốc cần link.
- jlink resolve các dependency được khai báo trong module graph và đưa chúng vào image.
- **--output runtime-image** chỉ định thư mục đầu ra.

Nếu ứng dụng cần service provider, có thể dùng tùy chọn **--bind-services** để liên kết các provider module cho service được dùng cùng dependency của chúng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output runtime-image
~~~

Chỉ thêm **--bind-services** khi muốn liên kết provider theo cơ chế service binding. Nếu ứng dụng tự nạp plugin hoặc provider từ vị trí bên ngoài image, cần thiết kế và kiểm tra module path/layer tương ứng khi chạy.

Có thể thêm các tùy chọn tối ưu dung lượng như **--strip-debug**, **--no-header-files**, **--no-man-pages** hoặc **--compress=2**. Các tùy chọn này ảnh hưởng nội dung đóng gói; sau khi thay đổi cấu hình link, hãy xác minh lại image mới.

## 8. Xác minh image sau khi link

Sau khi jlink hoàn tất, kiểm tra theo trình tự:

1. Xác nhận image có executable tại **bin/java** (hoặc **bin/java.exe**).
2. Chạy **runtime-image/bin/java --version** để xác nhận đúng runtime.
3. Chạy **runtime-image/bin/java --list-modules** để liệt kê module trong image.
4. Đối chiếu đủ các module mong đợi, gồm module ứng dụng và dependency.
5. Chạy **runtime-image/bin/java --describe-module <module-name>** cho các module quan trọng.
6. Dùng **jimage list** hoặc **jimage verify** khi cần kiểm tra nội dung và tính toàn vẹn của **lib/modules**.
7. Chạy thử ứng dụng bằng chính executable trong image.

Ví dụ kiểm tra:

~~~bash
./runtime-image/bin/java --list-modules
./runtime-image/bin/java --describe-module com.acme.app
./runtime-image/bin/java --validate-modules
~~~

**--validate-modules** yêu cầu launcher xác thực các module có thể quan sát trong cấu hình hiện tại rồi kết thúc. Chạy nó bằng Java của image và không bổ sung module path ngoài nếu mục tiêu là xác thực image độc lập.

Một số bản build có thể hiển thị module kèm phiên bản, số khác có thể không. Khi đối chiếu, so sánh module name trước; chỉ so sánh version khi yêu cầu triển khai có ràng buộc phiên bản cụ thể.

## 9. Chạy thử ứng dụng từ chính runtime image

Một danh sách module đúng vẫn chưa chứng minh ứng dụng chạy được. Hãy khởi chạy main module bằng Java trong image:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main
~~~

Trên Windows:

~~~powershell
.\runtime-image\bin\java.exe --module com.acme.app/com.acme.app.Main
~~~

Nếu ứng dụng nhận đối số:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main --config config/app.properties
~~~

Các đối số sau **module/main-class** được truyền vào **String[] args** của phương thức main.

Có thể tạo launcher riêng khi link image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Sau đó chạy launcher được tạo:

~~~bash
./runtime-image/bin/app
~~~

Trên Windows, dùng **runtime-image\bin\app.bat** nếu launcher được tạo dưới dạng script batch. Hãy kiểm tra tên file thực tế trong thư mục **bin** của image.

Kiểm thử trên image cuối cùng giúp phát hiện các vấn đề mà danh sách module không cho biết, như file cấu hình thiếu, tài nguyên không được đóng gói, native library sai nền tảng, đường dẫn làm việc hoặc dependency được nạp động.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Module cần thiết không xuất hiện trong **--list-modules** | Module chưa được chọn làm root, không nằm trong module path lúc link hoặc không được resolve vào image | Kiểm tra **--add-modules**, module path và descriptor **requires**; tạo lại image |
| **--describe-module** báo không tìm thấy module | Đang gọi nhầm Java runtime hoặc module không có trong image | Dùng đường dẫn đầy đủ tới **runtime-image/bin/java** và kiểm tra **--list-modules** |
| Chạy được trên JDK build nhưng lỗi trên runtime image | JDK build có nhiều module hơn image tối giản | Chạy ứng dụng bằng executable của image; bổ sung module cần thiết khi link |
| **jlink** báo không hỗ trợ automatic module | Một đầu vào chưa có module descriptor tường minh | Thêm **module-info.java** và đóng gói thành explicit modular JAR |
| Ứng dụng dùng ServiceLoader nhưng provider không có | Provider không được resolve/bind vào image hoặc không có trong layer mà ứng dụng tìm | Kiểm tra **uses/provides**, module path và cân nhắc **--bind-services** |
| Module có mặt nhưng ứng dụng vẫn không chạy | Thiếu tài nguyên, cấu hình, native library hoặc dependency nạp động | Chạy thử ứng dụng trên image và kiểm tra lỗi runtime cụ thể |
| Image chạy trên máy build nhưng không chạy trên máy đích | Image không tương thích OS, kiến trúc CPU hoặc môi trường native của máy đích | Tạo image phù hợp nền tảng mục tiêu và thử trên môi trường tương ứng |
| **jimage verify** thất bại | File **lib/modules** hỏng hoặc không phải image hợp lệ | Tạo lại image từ đầu vào đáng tin cậy và kiểm tra quá trình đóng gói |

### Lưu ý về module bị thiếu

Nếu module ứng dụng khai báo **requires java.sql** nhưng **java.sql** không có trong image, hãy kiểm tra module graph trước khi tạo lại. Với một explicit module, dependency bắt buộc phải resolve thành công để link. Không nên thêm hàng loạt module theo phỏng đoán; hãy xác định dependency trực tiếp và dependency do service, reflection hoặc cấu hình runtime yêu cầu.

### Lưu ý về service provider

Nếu ứng dụng dùng **ServiceLoader**, module ứng dụng cần khai báo **uses** và provider module cần khai báo **provides**. Tùy cách tạo image, **--bind-services** giúp jlink tìm và liên kết các provider cho service được sử dụng. Sau khi link, kiểm tra module provider có xuất hiện trong **--list-modules**, mô tả nó bằng **--describe-module**, rồi chạy thử luồng sử dụng service.

## 11. Checklist xác minh runtime image

- [ ] Đã xác định đúng thư mục runtime image cần phân phối.
- [ ] Đã gọi trực tiếp **bin/java** bên trong image.
- [ ] Phiên bản Java và nền tảng phù hợp mục tiêu triển khai.
- [ ] **--list-modules** có đủ module ứng dụng và dependency mong đợi.
- [ ] Các module quan trọng có descriptor phù hợp khi dùng **--describe-module**.
- [ ] **--validate-modules** hoàn tất thành công.
- [ ] Nếu cần điều tra nội dung JIMAGE, đã kiểm tra **lib/modules** bằng **jimage**.
- [ ] Nếu ứng dụng dùng service, đã xác nhận provider được link và có thể tìm thấy.
- [ ] Ứng dụng khởi chạy thành công bằng chính runtime image.
- [ ] Đã thử image trên nền tảng đích hoặc môi trường tương đương.

Checklist này là quy trình vận hành để xác minh artifact. Một kết quả **--list-modules** đúng không thay thế kiểm thử ứng dụng, còn kiểm thử ứng dụng thành công trên máy build không chứng minh image tương thích với mọi nền tảng.

## 12. Ghi nhớ

- Runtime image do **jlink** tạo chứa tập module được link cùng dependency đã resolve.
- Dùng **runtime-image/bin/java --list-modules** để xem module mà image cung cấp.
- Dùng **--describe-module** để xem descriptor của module cụ thể.
- Dùng **jimage list** và **jimage verify** để kiểm tra nội dung và tính toàn vẹn của kho module **lib/modules**.
- Dùng **jdeps --print-module-deps** để hỗ trợ phân tích dependency trước khi link, nhưng vẫn phải kiểm thử dependency động.
- **jlink** yêu cầu module đầu vào tường minh; automatic module không thể link trực tiếp.
- **--bind-services** hữu ích khi cần đưa service provider vào runtime image.
- Bài kiểm tra cuối cùng là chạy ứng dụng bằng đúng Java executable bên trong image sẽ phát hành.

## Tài liệu tham khảo

- [The jlink Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jimage Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jimage.html)
- [The jdeps Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282)
