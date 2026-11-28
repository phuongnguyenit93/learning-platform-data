# Tạo runtime riêng bằng jlink và truyền --runtime-image cho jpackage

## 1. Khi nào nên tách bước tạo runtime khỏi bước đóng gói?

`jpackage` có thể tự gọi `jlink` để tạo runtime image trong lúc đóng gói ứng dụng. Cách đó phù hợp với nhiều ứng dụng thông thường. Tuy nhiên, có những trường hợp nên tạo runtime riêng trước:

- Cần kiểm soát chính xác module nào được đưa vào runtime.
- Muốn kiểm tra runtime image độc lập trước khi đóng gói.
- Cần dùng tùy chọn `jlink` riêng, chẳng hạn `--bind-services`.
- Nhiều ứng dụng cần dùng cùng một cấu hình runtime đã được chuẩn hóa.
- Muốn tách phiên bản JDK tạo runtime khỏi phiên bản JDK chạy công cụ đóng gói.

Quy trình có hai giai đoạn rõ ràng:

1. Dùng `jlink` tạo runtime image từ các module cần thiết.
2. Truyền thư mục runtime image cho `jpackage` bằng `--runtime-image` để công cụ sao chép runtime đó vào application image.

Khi đã truyền `--runtime-image`, `jpackage` không gọi `jlink` để tạo runtime mới. Nó dùng runtime image được cung cấp. Đây là điểm quan trọng giúp kiểm soát đầu ra triển khai.

## 2. Phân biệt runtime image và application image

Hai loại image có nội dung và mục đích khác nhau:

| Thành phần | Nội dung | Công cụ tạo |
| --- | --- | --- |
| Runtime image | Java runtime và các module được chọn cùng dependency của chúng | `jlink` |
| Application image | Ứng dụng, launcher, tài nguyên và runtime đi kèm | `jpackage` |
| Native installer | Bộ cài đặt theo nền tảng, được tạo từ application image hoặc cấu hình đóng gói | `jpackage` |

Runtime image có thể chạy lệnh Java nhưng chưa phải gói ứng dụng hoàn chỉnh. Application image cung cấp launcher và cấu trúc triển khai để người dùng khởi chạy ứng dụng. Installer bổ sung cách cài đặt, gỡ cài đặt và tích hợp theo hệ điều hành.

## 3. Chuẩn bị ứng dụng modular

Ví dụ sử dụng ứng dụng ghi chú có module chính `com.example.notes`:

~~~text
src/
  com.example.notes/
    module-info.java
    com/
      example/
        notes/
          Main.java
~~~

Nội dung `module-info.java`:

~~~java
module com.example.notes {
    requires java.logging;
}
~~~

Nội dung `Main.java`:

~~~java
package com.example.notes;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.getLogger(Main.class.getName())
                .info("Notes application started");
    }
}
~~~

Module descriptor khai báo `requires java.logging`, nên module logging và các dependency bắc cầu của nó được giải quyết khi liên kết runtime.

Biên dịch module:

~~~powershell
javac --module-source-path src -d mods -m com.example.notes
~~~

Sau bước này, thư mục `mods` chứa module đã biên dịch. Với dự án thực tế, hãy đưa các named module dependency của ứng dụng vào module path tương ứng.

## 4. Tạo runtime image bằng jlink

Trên Windows, có thể dùng lệnh:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.notes --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Giải thích:

- `--module-path` chỉ định nơi tìm module JDK và module ứng dụng.
- `--add-modules com.example.notes` chọn module ứng dụng làm module root.
- `jlink` tự giải quyết các dependency được khai báo bằng `requires`.
- `--strip-debug` loại bỏ thông tin debug không cần cho runtime phân phối thông thường.
- `--no-header-files` và `--no-man-pages` bỏ header native và trang hướng dẫn không cần cho runtime ứng dụng.
- `--output build\runtime` chỉ định thư mục runtime image đầu ra.

Thư mục đầu ra cần là đường dẫn mới hoặc thư mục rỗng theo yêu cầu của `jlink`. Module path dùng dấu chấm phẩy trên Windows; trên Linux và macOS, dấu phân cách thường là dấu hai chấm.

Nếu ứng dụng nạp module theo cấu hình hoặc reflection, bổ sung named module cần thiết vào `--add-modules` sau khi xác định module thực tế. Nếu ứng dụng sử dụng service provider, xem xét `--bind-services`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;plugins" --add-modules com.example.notes,com.example.notes.plugin.csv --bind-services --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Chỉ dùng `--bind-services` khi ứng dụng dựa vào service binding. Nó yêu cầu `jlink` liên kết các module provider phù hợp theo service graph; nó không thay thế việc thêm module plugin được nạp bằng tên lớp từ cấu hình.

## 5. Kiểm tra runtime image trước khi đóng gói

Trước khi dùng runtime image, xác nhận runtime được tạo đúng:

~~~powershell
.\build\runtime\bin\java.exe --version
.\build\runtime\bin\java.exe --list-modules
~~~

Với ví dụ modular, chạy trực tiếp module chính bằng Java nằm trong runtime image:

~~~powershell
.\build\runtime\bin\java.exe -m com.example.notes/com.example.notes.Main
~~~

Ứng dụng phải chạy được bằng runtime image mà không cần dựa vào JDK đầy đủ trên máy build. Nếu thiếu module hoặc dependency, xử lý ở bước tạo runtime và chạy lại các kiểm tra.

`--list-modules` xác nhận module có mặt trong runtime image. Nó không thay thế kiểm thử chức năng: những dependency được nạp qua reflection, cấu hình ngoài, plugin hoặc JNI vẫn cần được gọi trong test.

## 6. Truyền runtime image cho jpackage

Sau khi runtime image đạt kiểm tra, tạo application image:

~~~powershell
jpackage --type app-image --name NotesApp --module-path mods --module com.example.notes/com.example.notes.Main --runtime-image build\runtime --dest dist
~~~

Các tùy chọn quan trọng:

- `--type app-image` yêu cầu tạo thư mục ứng dụng có thể chạy trực tiếp.
- `--name NotesApp` đặt tên ứng dụng và launcher.
- `--module-path mods` giúp `jpackage` tìm module ứng dụng.
- `--module com.example.notes/com.example.notes.Main` xác định module chính và lớp main.
- `--runtime-image build\runtime` chỉ định runtime image đã tạo bằng `jlink`.
- `--dest dist` đặt thư mục chứa application image.

`jpackage` sao chép runtime image được chỉ định vào application image. Nó không tạo lại runtime và không tự bổ sung module còn thiếu vào image đã có. Vì vậy, mọi thay đổi về module roots hoặc service binding phải được thực hiện ở bước `jlink`, sau đó tạo lại runtime image.

## 7. Đóng gói ứng dụng không modular

Ứng dụng classpath cũng có thể dùng runtime image riêng. Điểm khác biệt là `jlink` chỉ tạo runtime chứa các module JDK cần thiết; JAR ứng dụng và thư viện bên thứ ba vẫn được `jpackage` đóng gói riêng.

Giả sử cấu trúc thư mục:

~~~text
input/
  app.jar
  lib/
    database-driver.jar
    report-library.jar
~~~

Dùng `jdeps` để lập danh sách module JDK ban đầu:

~~~powershell
$modules = (jdeps --print-module-deps --recursive --class-path "input\lib\*" input\app.jar).Trim()
~~~

Xem lại giá trị `$modules` trước khi dùng. Nếu lệnh phân tích báo dependency không tìm thấy hoặc không trả về danh sách hợp lệ, hãy sửa classpath và xử lý dependency trước.

Tạo runtime:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules $modules --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Đóng gói ứng dụng cùng runtime:

~~~powershell
jpackage --type app-image --name LegacyTool --input input --main-jar app.jar --main-class com.example.tool.Main --runtime-image build\runtime --dest dist
~~~

`--input` chỉ định thư mục chứa JAR và tài nguyên. `--main-jar` là đường dẫn tương đối tới JAR chính bên trong thư mục input. Các JAR trong `input\lib` được đưa vào payload; launcher và cấu hình classpath phải bảo đảm ứng dụng tìm được chúng.

Với ứng dụng classpath, runtime image không chứa `app.jar` hoặc các JAR bên thứ ba chỉ vì chúng xuất hiện trong classpath. Chúng nằm trong application image do `jpackage` tạo.

## 8. Kiểm thử application image

Sau khi `jpackage` hoàn tất, chạy launcher được tạo trong application image trên chính hệ điều hành build. Kiểm tra các nội dung:

- Launcher khởi động được và dùng runtime đi kèm.
- Các module JDK cần thiết có mặt.
- Module chính, JAR classpath và tài nguyên ứng dụng được tìm thấy.
- Cấu hình reflection, plugin và service provider hoạt động.
- Các file dữ liệu được ghi vào thư mục dữ liệu phù hợp, không ghi vào thư mục runtime.
- Ứng dụng hoạt động trên máy thử không cài JDK riêng.

Không chỉ chạy ứng dụng bằng `java` trên máy phát triển rồi kết luận gói đã đúng. Launcher trong application image có thể có đường dẫn, classpath hoặc Java options khác với lệnh chạy thủ công.

## 9. Tạo native installer từ application image đã kiểm thử

Sau khi application image chạy đúng, có thể tạo installer từ image đó. Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name NotesApp --app-image dist\NotesApp --dest installers
~~~

Khi đóng gói từ application image có sẵn, dùng `--app-image`. Không cần truyền lại `--runtime-image` vì runtime đã nằm trong application image.

Các định dạng installer phụ thuộc hệ điều hành:

| Nền tảng build | Một số định dạng |
| --- | --- |
| Windows | `msi`, `exe` |
| Linux | `deb`, `rpm` |
| macOS | `pkg`, `dmg` |

`jpackage` không hỗ trợ tạo installer native cho một hệ điều hành khác từ máy build hiện tại. Hãy tạo runtime image và application image trên từng nền tảng/kiến trúc đích, rồi kiểm thử installer tương ứng.

## 10. Phiên bản JDK của jlink và jpackage

Runtime image được tạo từ các module của JDK cung cấp cho `jlink`. Vì vậy, phiên bản runtime được quyết định bởi JDK dùng để tạo image, không phải bởi mức source hoặc target của ứng dụng.

`jpackage` có thể nhận runtime image dựng sẵn, kể cả khi runtime đó được tạo bằng một JDK khác với JDK đang chạy công cụ đóng gói. Cách này hữu ích khi cần giữ runtime ở một phiên bản đã chọn trong khi vẫn dùng công cụ đóng gói mới hơn.

Tuy nhiên, cần chọn runtime còn được nhà cung cấp hỗ trợ và phù hợp với dependency của ứng dụng. Java 16 là bản phát hành không phải LTS và đã hết vòng đời hỗ trợ; không nên chọn runtime Java 16 cho hệ thống production mới chỉ vì ứng dụng được biên dịch hoặc phát triển từ Java 16.

Nên dùng bộ công cụ `jlink` tương ứng với runtime mục tiêu, sau đó kiểm tra application image bằng đúng runtime đó. Việc dùng `jpackage` mới hơn để đóng gói runtime image dựng sẵn không thay thế kiểm thử tương thích.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jlink` báo không tìm thấy module | Sai tên module hoặc module path thiếu dependency | Kiểm tra module descriptor, module path và module roots |
| Runtime chạy được trên máy build nhưng lỗi trên máy sạch | Máy build có JDK đầy đủ hoặc dependency ngoài image | Chạy test bằng runtime image trên môi trường sạch |
| `ClassNotFoundException` khi reflection | Module hoặc JAR được chọn từ cấu hình chưa được đóng gói | Bổ sung named module ở bước `jlink` hoặc JAR vào application payload |
| `ServiceLoader` không tìm thấy provider | Provider không được liên kết vào runtime image | Kiểm tra `uses`/`provides` và cân nhắc `--bind-services` |
| Application image không tìm thấy tài nguyên | Đường dẫn tài nguyên phụ thuộc thư mục làm việc của máy build | Đóng gói tài nguyên và dùng đường dẫn tương đối theo vị trí ứng dụng |
| Installer không chạy trên hệ điều hành khác | Runtime image và installer gắn với nền tảng build | Build và kiểm thử riêng cho từng hệ điều hành/kiến trúc |

## 12. Quy trình triển khai đề xuất

1. Xác định ứng dụng modular hay classpath, module chính và dependency.
2. Dùng `jdeps` và kiểm tra cấu hình để lập danh sách module cần có.
3. Tạo runtime image bằng `jlink`; bổ sung module động và service binding khi cần.
4. Kiểm tra runtime bằng `--version`, `--list-modules` và chạy ứng dụng thử.
5. Truyền runtime image cho `jpackage --runtime-image` để tạo application image.
6. Kiểm thử launcher trên môi trường sạch và các luồng nghiệp vụ quan trọng.
7. Tạo installer native từ application image đã kiểm thử trên nền tảng đích.

**Ghi nhớ:** Tạo runtime riêng giúp kiểm soát module, tùy chọn liên kết và phiên bản Java được phân phối. `jlink` tạo runtime image; `jpackage --runtime-image` sao chép image đó vào application image mà không gọi lại `jlink`. Hãy kiểm tra runtime độc lập, sau đó kiểm thử launcher và installer trên đúng nền tảng trước khi phát hành.

## Nguồn tham khảo chính thức

- [The jpackage Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html)
- [Image and Runtime Modifications — JDK 25](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
