# Kiểm tra thay đổi mặc định service binding theo phiên bản jpackage

## 1. Vì sao phải kiểm tra phiên bản jpackage?

`jpackage` tạo application image hoặc installer kèm một Java runtime để ứng dụng có thể chạy trên máy người dùng. Nếu không truyền runtime dựng sẵn bằng `--runtime-image`, công cụ sẽ gọi `jlink` để tạo runtime image.

Hành vi mặc định liên quan đến service binding đã thay đổi ở JDK 25. Một ứng dụng modular dùng `ServiceLoader` có thể tìm thấy provider khi được đóng gói bằng JDK 24 hoặc cũ hơn, nhưng không tìm thấy provider khi dùng `jpackage` JDK 25 trở lên nếu không cấu hình lại.

Đây là thay đổi về tập module được đưa vào runtime image do `jpackage` tạo. API `ServiceLoader`, directive `uses`/`provides` và tùy chọn `jlink --bind-services` vẫn là cơ chế hiện hành.

## 2. Mốc thay đổi theo phiên bản

| Phiên bản JDK chạy jpackage | Service bindings trong runtime image do jpackage tự tạo | Cách xử lý |
| --- | --- | --- |
| JDK 16–24 | Được bao gồm mặc định | Hành vi cũ; thông thường không cần thêm tùy chọn |
| JDK 25 trở lên | Không còn được bao gồm mặc định | Thêm `--bind-services` vào `--jlink-options` nếu ứng dụng cần service binding |

Oracle ghi nhận thay đổi này trong JDK 25 Release Notes, mã vấn đề JDK-8345185. Tài liệu Packaging Overview của JDK 26 cũng xác nhận hành vi từ JDK 25 trở lên và hướng dẫn khôi phục hành vi cũ bằng `--jlink-options` cùng `--bind-services`.

Không nên suy luận hành vi chỉ từ phiên bản source code hoặc bytecode của ứng dụng. Hãy kiểm tra đúng executable `jpackage` được dùng trong pipeline, vì đó là công cụ quyết định cách tạo runtime image.

## 3. Service binding ảnh hưởng tới trường hợp nào?

Service binding liên quan trực tiếp đến ứng dụng modular sử dụng JPMS:

- Module consumer khai báo `uses com.example.spi.Service`.
- Module provider khai báo `provides com.example.spi.Service with com.example.impl.Provider`.
- Provider module nằm trên module path khi `jlink` giải quyết module graph.
- `jlink --bind-services` liên kết provider module cùng các dependency của provider vào runtime image.

Nếu provider chỉ là JAR trên classpath và khai báo bằng file `META-INF/services`, service discovery dựa vào class loader và nội dung JAR. `jlink --bind-services` không đọc các file classpath đó để biến JAR thành provider module. Trong trường hợp này, phải đóng gói JAR và giữ nguyên file service configuration trong application image.

Vì vậy, không phải ứng dụng nào dùng `ServiceLoader` cũng cần bật service binding của `jlink`. Cần xác định provider thuộc named module hay classpath trước khi thay đổi cấu hình đóng gói.

## 4. Ví dụ module consumer và provider

Giả sử service contract nằm trong module API:

~~~java
module com.example.image.api {
    exports com.example.image.api;
}
~~~

Interface service:

~~~java
package com.example.image.api;

public interface ImageFormat {
    String name();
}
~~~

Module ứng dụng khai báo service mà nó sử dụng:

~~~java
module com.example.image.app {
    requires com.example.image.api;
    uses com.example.image.api.ImageFormat;
}
~~~

Module provider khai báo implementation:

~~~java
module com.example.image.png {
    requires com.example.image.api;

    provides com.example.image.api.ImageFormat
            with com.example.image.png.PngFormat;
}
~~~

Ứng dụng tìm provider:

~~~java
ServiceLoader<ImageFormat> formats =
        ServiceLoader.load(ImageFormat.class);

formats.forEach(format ->
        System.out.println(format.name()));
~~~

Nếu runtime image không chứa provider module, ứng dụng có thể không tìm thấy implementation dù module ứng dụng và module API vẫn khởi động bình thường.

## 5. Xác định phiên bản và đường dẫn jpackage thực sự được dùng

Trên Windows PowerShell, kiểm tra executable trong môi trường build:

~~~powershell
jpackage --version
java --version
where.exe jpackage
where.exe java
~~~

`jpackage --version` in ra phiên bản công cụ. `where.exe jpackage` cho biết các đường dẫn có thể được Windows tìm thấy qua `PATH`. Nếu có nhiều JDK cài trên máy, lệnh đầu tiên trong `PATH` có thể không thuộc JDK mà pipeline dự định dùng.

Trong CI hoặc script phát hành, nên gọi `jpackage` bằng đường dẫn toolchain đã cố định, hoặc cấu hình `JAVA_HOME`/`PATH` nhất quán. Ghi lại phiên bản công cụ trong log build để có thể đối chiếu khi runtime image khác nhau.

Không dùng phiên bản `javac` hoặc mức `--release` để suy ra phiên bản `jpackage`. Compiler và packaging tool có thể đến từ các JDK khác nhau.

## 6. Hành vi mặc định trước JDK 25

Với JDK 16–24, khi `jpackage` tự tạo runtime image, service bindings được bao gồm mặc định. Ví dụ:

~~~powershell
jpackage --type app-image --name ImageViewer --module-path "mods;providers" --module com.example.image.app/com.example.image.app.Main --dest dist
~~~

Nếu module consumer khai báo `uses` và provider module khai báo `provides`, service binding mặc định trước JDK 25 cho phép `jpackage` tạo runtime image có các provider module phù hợp được liên kết.

Điều này giải thích vì sao cùng một lệnh đóng gói có thể tạo runtime image chứa nhiều module hơn trên JDK 24 so với JDK 25 trở lên. Đây là khác biệt hành vi của packaging tool, không nhất thiết là thay đổi trong mã nguồn ứng dụng.

## 7. Hành vi mặc định từ JDK 25 trở lên

Từ JDK 25, runtime image do `jpackage` tạo không còn service bindings mặc định. Cùng lệnh ở ví dụ trước có thể tạo runtime image nhỏ hơn và bỏ qua provider module chỉ được phát hiện thông qua service binding.

Nếu ứng dụng cần giữ hành vi cũ, truyền `--bind-services` cho `jlink` qua `jpackage --jlink-options`:

~~~powershell
jpackage --type app-image --name ImageViewer --module-path "mods;providers" --module com.example.image.app/com.example.image.app.Main --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" --dest dist
~~~

Trong ví dụ:

- `--jlink-options` chuyển các tùy chọn liên kết runtime cho `jlink`.
- `--bind-services` yêu cầu `jlink` liên kết provider module và dependency của chúng theo service graph.
- Bốn tùy chọn còn lại giữ các thiết lập tối ưu mặc định mà `jpackage` thường truyền cho `jlink`.

Khi tự chỉ định `--jlink-options`, danh sách tùy chọn do bạn cung cấp thay cho danh sách mặc định của công cụ. Vì vậy, nếu vẫn cần bỏ debug symbols, native commands, man pages và header files, hãy ghi rõ các tùy chọn đó cùng `--bind-services` như ví dụ.

## 8. Không nhầm jpackage tự tạo runtime với runtime dựng sẵn

`--jlink-options` chỉ có tác dụng khi `jpackage` gọi `jlink` để tạo runtime image. Nếu truyền `--runtime-image`, `jpackage` sao chép runtime image có sẵn vào application image và không chạy `jlink` để tạo lại nó.

Ví dụ dùng runtime dựng sẵn:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;providers" --add-modules com.example.image.app --bind-services --output build\runtime
jpackage --type app-image --name ImageViewer --module-path "mods;providers" --module com.example.image.app/com.example.image.app.Main --runtime-image build\runtime --dest dist
~~~

Ở đây service binding được quyết định ở bước `jlink`. `jpackage` chỉ dùng image đã tạo; thêm `--jlink-options` vào lệnh đóng gói không thể sửa module graph của runtime image đó.

## 9. Giữ nguyên default jlink options khi bật bind-services

Nếu chỉ truyền:

~~~powershell
jpackage --type app-image --name ImageViewer --module-path "mods;providers" --module com.example.image.app/com.example.image.app.Main --jlink-options "--bind-services" --dest dist
~~~

thì bạn đã tự chỉ định danh sách tùy chọn `jlink`. Các tùy chọn mặc định mà `jpackage` thường thêm khi không có `--jlink-options` sẽ không tự động được ghép vào danh sách này.

Nếu muốn vừa bật service binding vừa giữ cấu hình mặc định, dùng:

~~~text
--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services
~~~

Không phải mọi ứng dụng đều cần service binding. Runtime image có thể lớn hơn vì provider module và dependency của chúng được liên kết. Chỉ bật khi ứng dụng thực sự dùng provider module qua service graph và đã kiểm thử kết quả.

## 10. Cách kiểm tra service binding có cần thiết không

Thực hiện kiểm tra theo thứ tự:

1. Xác nhận consumer có directive `uses` cho service.
2. Xác nhận provider module có directive `provides` đúng service type.
3. Xác nhận provider module có trên module path của bước tạo runtime.
4. Tạo application image bằng đúng phiên bản `jpackage` sẽ dùng trong phát hành.
5. Chạy ứng dụng bằng launcher trong application image và gọi chức năng sử dụng service.
6. Nếu provider không được tìm thấy trên JDK 25+, tạo lại image với `--bind-services` rồi chạy lại test.

Có thể kiểm tra module có trong runtime image bằng:

~~~powershell
.\dist\ImageViewer\runtime\bin\java.exe --list-modules
~~~

Đường dẫn thực tế phụ thuộc cấu trúc application image của nền tảng. Danh sách module chỉ xác nhận module hiện diện; cần chạy `ServiceLoader` để xác nhận provider thực sự được phát hiện và khởi tạo.

## 11. Phân biệt lỗi service binding với lỗi cấu hình SPI

Không phải mọi lỗi `ServiceLoader` đều được giải quyết bằng `--bind-services`:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Consumer báo thiếu `uses` | Module descriptor chưa khai báo service consumer | Bổ sung `uses` và build lại module |
| Provider module không có trong runtime | Thiếu service binding hoặc provider không có trên module path | Kiểm tra phiên bản `jpackage`, `--bind-services` và module path |
| Provider có trong image nhưng khởi tạo lỗi | Constructor/provider method hoặc dependency bị lỗi | Kiểm tra provider và dependency |
| Classpath provider không tìm thấy | Thiếu JAR hoặc file `META-INF/services` | Kiểm tra input directory và classpath của launcher |
| Không truy cập được member khi reflection | Package chưa được mở hoặc export phù hợp | Kiểm tra `exports`/`opens`; service binding không cấp quyền truy cập |
| Runtime dựng sẵn không có provider | `jlink` ban đầu không dùng service binding | Tạo lại runtime image với `jlink --bind-services` |

Với provider dạng JAR classpath, giữ nguyên file `META-INF/services` và bảo đảm launcher đưa JAR vào classpath. Không cần thêm `--bind-services` chỉ vì ứng dụng classpath sử dụng `ServiceLoader`.

## 12. Ma trận lựa chọn cấu hình

| Tình huống | Cấu hình phù hợp |
| --- | --- |
| JDK 16–24, `jpackage` tự tạo runtime, provider là named module | Service binding được bao gồm mặc định; kiểm thử gói đầu ra |
| JDK 25+, `jpackage` tự tạo runtime, provider là named module | Thêm `--bind-services` qua `--jlink-options` nếu ứng dụng cần provider |
| Mọi JDK, runtime được tạo riêng bằng `jlink` | Quyết định service binding trong lệnh `jlink`; truyền image qua `--runtime-image` |
| Provider là JAR classpath | Đóng gói JAR và `META-INF/services`; kiểm tra classpath launcher |
| Ứng dụng không dùng service provider module | Không cần bật service binding chỉ để đóng gói |

## 13. Quy trình kiểm tra trong pipeline phát hành

1. Ghi nhận kết quả `jpackage --version` và đường dẫn executable.
2. Xác định ứng dụng dùng named-module provider hay provider JAR trên classpath.
3. Nếu dùng named-module provider, kiểm tra `uses`/`provides` và module path.
4. Với JDK 16–24, xác nhận service provider hoạt động trên image mặc định.
5. Với JDK 25+, bật `--bind-services` qua `--jlink-options` nếu ứng dụng cần service binding.
6. Nếu dùng `--runtime-image`, kiểm tra service binding ở bước tạo runtime image, không phải bước `jpackage`.
7. Kiểm tra module list và chạy integration test trên launcher của application image.
8. Lưu phiên bản JDK, lệnh đóng gói và kết quả kiểm thử cùng artifact phát hành.

**Ghi nhớ:** JDK 25 là mốc thay đổi: `jpackage` trước JDK 25 bao gồm service bindings mặc định trong runtime image do công cụ tạo; từ JDK 25 trở đi không còn. Khi cần giữ provider module, truyền `--bind-services` qua `--jlink-options` và giữ lại các default `jlink` options cần thiết. Nếu dùng runtime dựng sẵn, hãy bật service binding khi tạo image bằng `jlink`. Provider JAR trên classpath vẫn cần được đóng gói cùng `META-INF/services` và classpath launcher.

## Nguồn tham khảo chính thức

- [JDK 25 Release Notes — JDK-8345185](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
- [Packaging Overview — JDK 26, Java Runtime Requirements](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [The jpackage Command — JDK 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
