# Bổ sung module được nạp qua reflection mà phân tích tĩnh không phát hiện

## 1. Vì sao jdeps có thể bỏ sót module?

`jdeps` phân tích bytecode để tìm các tham chiếu lớp và module mà compiler ghi nhận. Kết quả `jdeps --print-module-deps` là điểm khởi đầu hữu ích để chọn module cho `jlink`, nhưng không thể hiện đầy đủ mọi dependency được quyết định khi ứng dụng chạy.

Một trường hợp phổ biến là reflection. Ứng dụng có thể đọc tên lớp từ file cấu hình rồi nạp lớp bằng `Class.forName`:

~~~java
class DriverLoader {
    static Object create(String className)
            throws ReflectiveOperationException {
        Class<?> driverType = Class.forName(className);
        return driverType.getDeclaredConstructor().newInstance();
    }
}
~~~

Nếu giá trị `className` là `"com.example.driver.impl.Driver"`, tên lớp nằm dưới dạng chuỗi. Đây không phải tham chiếu kiểu thông thường như `new Driver()` hoặc `Driver.class`, vì vậy không thể dựa vào phân tích dependency tĩnh để bảo đảm module chứa lớp đó được đưa vào runtime image.

Nếu module không được giải quyết và đưa vào runtime image, lời gọi reflection có thể thất bại khi chạy với `ClassNotFoundException` hoặc lỗi liên kết liên quan. Ứng dụng có thể khởi động bình thường rồi mới lỗi khi người dùng chọn tính năng cần driver đó.

## 2. Ghi nhận dependency reflection từ cấu hình và đường chạy

Trước khi tạo runtime image, lập danh sách các lớp và module được nạp động. Nguồn thông tin thường nằm ở:

- File cấu hình ứng dụng chứa tên implementation, driver hoặc adapter.
- Biến môi trường và tham số khởi chạy chọn provider.
- Framework dùng annotation, tên lớp hoặc convention để tìm implementation.
- Thư mục plugin và cơ chế nạp module/lớp khi chạy.
- Các nhánh nghiệp vụ chỉ được gọi trong môi trường production hoặc theo loại dữ liệu đặc biệt.

Ví dụ, một ứng dụng có cấu hình:

~~~properties
storage.driver=com.example.storage.jdbc.JdbcStorageDriver
document.converter=com.example.document.PdfConverter
~~~

Hãy lập bảng ánh xạ tên lớp với module chứa lớp:

| Tên lớp được nạp | Module chứa lớp | Lý do cần có |
| --- | --- | --- |
| `com.example.storage.jdbc.JdbcStorageDriver` | `com.example.storage.jdbc` | Được cấu hình làm storage driver |
| `com.example.document.PdfConverter` | `com.example.document.pdf` | Được chọn làm converter |

Tên module phải lấy từ module descriptor hoặc metadata thực tế của dependency. Không suy ra tên module chỉ bằng cách bỏ phần package khỏi tên lớp.

Nếu nhiều cấu hình có thể chọn các implementation khác nhau, runtime phải chứa mọi module có thể được chọn trong môi trường đó, hoặc các plugin phải được phân phối và nạp theo một cơ chế riêng đã được kiểm thử.

## 3. Bổ sung module tường minh bằng jlink --add-modules

Giả sử ứng dụng là module `com.example.app`, còn implementation được nạp bằng reflection nằm trong module `com.example.storage.jdbc`. Hai module đã được biên dịch hoặc đóng gói thành module rõ ràng trong các thư mục `mods` và `lib-mods`.

Có thể tạo runtime image với cả hai module làm module gốc:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;lib-mods" --add-modules com.example.app,com.example.storage.jdbc --output build\runtime
~~~

Trong lệnh này:

- `--module-path` cung cấp module JDK và các module ứng dụng/dependency.
- `--add-modules` yêu cầu đưa các module được liệt kê vào tập module roots của runtime.
- `jlink` tiếp tục giải quyết các dependency module được khai báo bằng `requires`.
- `--output` chỉ định thư mục runtime image.

Nếu implementation reflection cần thêm `java.sql`, `java.naming` hoặc module JDK khác mà phân tích tĩnh không phát hiện, hãy thêm module đó vào danh sách sau khi xác minh từ code, cấu hình và test:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;lib-mods" --add-modules com.example.app,com.example.storage.jdbc,java.sql,java.naming --output build\runtime
~~~

Danh sách trên chỉ minh họa. Chỉ thêm module thực sự cần cho ứng dụng. Việc chọn module gốc giúp `jlink` giữ lại module được nạp động cùng các dependency module của nó; nó không tự bổ sung các JAR classpath không phải module.

## 4. Khác nhau giữa module được đưa vào image và quyền truy cập reflection

Đưa module vào runtime image chỉ giải quyết câu hỏi **module có mặt để được nạp hay không**. Nó không tự cấp mọi quyền truy cập vào package và member bên trong module đó.

Cần phân biệt ba khái niệm:

- **Có mặt trong runtime:** module được giải quyết và có trong runtime image; có thể cần thêm module root bằng `--add-modules`.
- **Readability và exports:** mã trong một module cần quyền đọc module khác; package chứa API công khai cần được export phù hợp.
- **Deep reflection:** framework cần truy cập member không public hoặc trạng thái private thì package đích phải được mở (`opens`) cho module gọi reflection.

Ví dụ module chứa driver có thể khai báo:

~~~java
module com.example.storage.jdbc {
    exports com.example.storage.jdbc;
    opens com.example.storage.internal to com.example.framework;
}
~~~

`exports` cho phép module khác sử dụng các kiểu public trong package API theo quy tắc module. `opens` cho phép reflection sâu từ module được chỉ định vào package nội bộ.

Không nên mở toàn bộ module chỉ để xử lý một lỗi reflection. Hãy mở đúng package và đúng module cần truy cập. Nếu framework chỉ gọi constructor public của một lớp public trong package đã export, không cần mở package chỉ vì thao tác đó sử dụng reflection.

## 5. Khai báo dependency khi module đã biết

Nếu ứng dụng luôn cần một module dependency và có thể khai báo quan hệ module trực tiếp, hãy dùng `requires` trong `module-info.java`:

~~~java
module com.example.app {
    requires com.example.storage.api;
}
~~~

`requires` thể hiện quan hệ module mà ứng dụng cần đọc. Nếu implementation cụ thể được chọn bằng cấu hình và không có tham chiếu tĩnh, module chứa implementation vẫn có thể cần được thêm như module root khi tạo runtime image:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;lib-mods" --add-modules com.example.app,com.example.storage.jdbc --output build\runtime
~~~

Nếu dependency là tùy chọn theo cấu hình, hãy ghi rõ module nào được triển khai trong từng profile. Đừng thêm `requires` bắt buộc cho một provider không có trong mọi bản phân phối nếu thiết kế ứng dụng cho phép provider vắng mặt.

Một lựa chọn khác là dùng SPI với `ServiceLoader` khi bài toán là chọn implementation theo service contract. Với module hóa, khai báo `uses` và `provides` giúp module system thể hiện service dependency rõ hơn; khi tạo runtime image có thể cân nhắc `jlink --bind-services`. Dù vậy, các provider vẫn phải có mặt trong module path và cần được kiểm thử ở runtime.

## 6. Trường hợp dependency là JAR trên classpath

Không phải mọi thư viện được nạp qua reflection đều là named module có thể liên kết bằng `jlink`.

| Loại dependency | Cách xử lý |
| --- | --- |
| Explicit named module | Đưa module vào module path và thêm vào `--add-modules` nếu chỉ được nạp động |
| JAR classpath không có module descriptor | Phân phối JAR cùng ứng dụng và cấu hình classpath/launcher; không thêm JAR đó làm module root cho `jlink` |
| Automatic module | Không dùng làm đầu vào liên kết runtime image bằng `jlink`; cân nhắc chuyển thành explicit module hoặc giữ như dependency ứng dụng theo cách đóng gói phù hợp |
| Plugin được tải từ thư mục bên ngoài | Phân phối plugin riêng và xác định module/class loader cùng dependency của plugin |

`jlink` liên kết module, không gom mọi JAR classpath thành một runtime module. `jpackage` có thể đóng gói JAR và tài nguyên ứng dụng, nhưng dependency classpath vẫn phải được đưa vào application image và launcher phải tìm được chúng.

Nếu dependency JAR có `Automatic-Module-Name` hoặc tên module tự suy ra, điều đó không biến nó thành explicit module phù hợp để liên kết bằng `jlink`. Hãy kiểm tra loại module trước khi thêm vào module path của công cụ.

## 7. Khi jpackage tự tạo runtime

Nếu không truyền `--runtime-image`, `jpackage` có thể gọi `jlink` để tạo runtime trong quá trình đóng gói. Với dependency module chỉ được nạp qua reflection, hãy bổ sung module đó vào cấu hình runtime của `jpackage` bằng `--add-modules`:

~~~powershell
jpackage --type app-image --name StorageApp --module-path mods --module com.example.app/com.example.app.Main --add-modules com.example.storage.jdbc,java.sql --dest dist
~~~

Nếu đã tạo runtime riêng bằng `jlink`, hãy truyền runtime image đó:

~~~powershell
jpackage --type app-image --name StorageApp --module-path mods --module com.example.app/com.example.app.Main --runtime-image build\runtime --dest dist
~~~

Trong trường hợp thứ hai, module reflection phải được đưa vào runtime image ở bước `jlink`. `jpackage` sử dụng image được cung cấp và không tự sửa danh sách module bên trong image đó.

## 8. Kiểm tra module và quyền reflection sau khi tạo image

Sau khi tạo runtime image, kiểm tra module đã được đưa vào:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Tìm module cần nạp, ví dụ `com.example.storage.jdbc`. Nếu module không có trong danh sách, xem lại module path và danh sách `--add-modules`.

Sau đó chạy đúng đường reflection mà ứng dụng sử dụng:

~~~java
String configuredClass = "com.example.storage.jdbc.JdbcStorageDriver";
Object driver = Class.forName(configuredClass)
        .getDeclaredConstructor()
        .newInstance();
~~~

Kiểm tra riêng từng bước:

1. Module có trong runtime image và lớp có thể được tìm thấy.
2. Constructor được tìm thấy và có thể được gọi.
3. Package được export/open đúng mức nếu thao tác cần quyền truy cập tương ứng.
4. Dependency mà constructor hoặc phương thức khởi tạo sử dụng cũng có mặt.
5. Cấu hình production chọn đúng implementation như khi test.

Các lỗi thường gặp có ý nghĩa khác nhau:

| Lỗi | Hướng kiểm tra |
| --- | --- |
| `ClassNotFoundException` | Tên lớp, module/JAR chứa lớp, module path, classpath và module roots |
| `NoClassDefFoundError` | Dependency của lớp được nạp có thiếu hoặc không tương thích không |
| `NoSuchMethodException` | Constructor hoặc method được yêu cầu có tồn tại đúng chữ ký không |
| `IllegalAccessException` | Lớp/member có public và package đã export phù hợp chưa |
| `InaccessibleObjectException` | Framework có cần deep reflection; package đã được mở đúng module chưa |
| `ExceptionInInitializerError` | Static initializer của implementation có lỗi hoặc thiếu dependency không |

Không giải quyết mọi lỗi bằng cách thêm module. Một lỗi access cần xử lý exports/opens; lỗi classpath cần bổ sung JAR; lỗi khởi tạo cần sửa implementation hoặc dependency.

## 9. Dùng test để phát hiện module reflection bị bỏ sót

Một bộ test chỉ chạy đường code chính có thể không phát hiện dependency động còn thiếu. Hãy tạo test cho từng lựa chọn cấu hình:

- Mỗi driver, converter hoặc adapter có thể được chọn.
- Mỗi profile triển khai và biến môi trường liên quan.
- Constructor và phương thức khởi tạo của implementation.
- Truy cập member qua reflection mà framework thực hiện.
- Trường hợp module hoặc plugin tùy chọn không được cài đặt.
- Chạy application image trên máy sạch, không dựa vào JDK hoặc thư viện tình cờ có trên máy build.

Nên chạy các test này bằng runtime image sau khi `jlink` tạo xong, không chỉ bằng JDK đầy đủ trên máy phát triển. JDK đầy đủ thường có nhiều module hơn image tối giản và có thể che giấu module bị thiếu.

## 10. Quy trình thực hiện

1. Chạy `jdeps --print-module-deps` để lấy danh sách module từ dependency tĩnh.
2. Tìm các tên lớp/module được nạp từ cấu hình, reflection, plugin hoặc lựa chọn runtime.
3. Xác định module thật sự chứa từng implementation; kiểm tra dependency có phải explicit module hay JAR classpath.
4. Bổ sung named module bị bỏ sót vào `jlink --add-modules`; bổ sung JAR classpath vào gói ứng dụng theo cơ chế classpath.
5. Kiểm tra `exports` và `opens` riêng nếu reflection cần truy cập API hoặc member không public.
6. Tạo runtime image, xác nhận bằng `--list-modules` và chạy các test cấu hình động.
7. Chỉ sau khi test trên runtime image đạt, đóng gói bằng `jpackage`.

**Ghi nhớ:** Phân tích tĩnh không thể suy luận đáng tin cậy mọi tên lớp lấy từ cấu hình hoặc chuỗi reflection. Hãy lập danh sách implementation được nạp động, xác định module thực tế rồi bổ sung named module bằng `jlink --add-modules`. Việc đưa module vào image khác với cấp quyền `exports`/`opens`; JAR classpath cũng phải được đóng gói riêng. Luôn kiểm thử đường reflection trên chính runtime image sẽ phát hành.
