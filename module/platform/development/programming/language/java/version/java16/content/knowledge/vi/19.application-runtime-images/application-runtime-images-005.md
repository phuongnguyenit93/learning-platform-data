# Cấu hình --add-modules cho runtime của ứng dụng

## 1. Vai trò của --add-modules

Khi tạo runtime image bằng `jlink` hoặc để `jpackage` tạo runtime đi kèm ứng dụng, cần xác định những module nào phải có mặt trong runtime. Thông thường, module chính và các dependency được khai báo bằng `requires` đã tạo thành một module graph đủ dùng. Tuy nhiên, ứng dụng có thể còn cần module được chọn theo cấu hình, nạp bằng reflection hoặc dùng như plugin nên không xuất hiện trong quan hệ phụ thuộc tĩnh.

Tùy chọn `--add-modules` dùng để thêm những module được chỉ định vào tập module gốc (*root modules*) của quá trình tạo runtime image. Công cụ liên kết các module gốc đó cùng các dependency bắc cầu của chúng.

Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.shop --output build\runtime
~~~

Lệnh trên chọn `com.example.shop` làm module root. Nếu module này khai báo `requires java.sql`, `jlink` tự giải quyết `java.sql` và các dependency bắc cầu của nó; không cần thêm lại `java.sql` vào danh sách.

`--add-modules` không phải tùy chọn để thêm một file JAR bất kỳ vào classpath, cũng không cấp quyền truy cập package hoặc member private. Nó chọn module roots cho bước liên kết runtime.

## 2. Khi nào cần thêm module tường minh?

Nếu module chính khai báo dependency tĩnh:

~~~java
module com.example.shop.spi {
    exports com.example.shop.spi;
}
~~~

Trong module descriptor của ứng dụng:

~~~java
module com.example.shop {
    requires java.sql;
    requires com.example.shop.spi;
}
~~~

thì khi tạo image từ module `com.example.shop`, `jlink` tự giải quyết `java.sql` và các dependency bắc cầu. Không cần liệt kê lại mọi module phụ thuộc đã được khai báo.

Module bổ sung thường cần được chỉ định khi ứng dụng sử dụng chúng theo cách phân tích tĩnh không thể suy ra, ví dụ:

- Lớp implementation được chọn từ tên lớp trong file cấu hình và nạp bằng `Class.forName`.
- Plugin là named module được chọn theo profile triển khai.
- Driver hoặc adapter được phát hiện khi chạy.
- Ứng dụng cần một API JDK tùy chọn nhưng không có tham chiếu tĩnh đến module chứa API đó.
- Module cần được đưa vào runtime dù module chính không khai báo `requires` trực tiếp hoặc gián tiếp.

Ví dụ module plugin:

~~~java
module com.example.shop.plugin.csv {
    requires com.example.shop.spi;

    exports com.example.shop.plugin.csv;
}
~~~

Ứng dụng đọc tên implementation từ cấu hình:

~~~properties
exporter.class=com.example.shop.plugin.csv.CsvExporter
~~~

Vì tên lớp chỉ xuất hiện trong chuỗi cấu hình, module plugin có thể không nằm trong tập dependency tĩnh mà công cụ suy ra. Khi đó, hãy xác định module thật sự chứa lớp và thêm module đó vào runtime roots.

## 3. Dùng --add-modules trực tiếp với jlink

Giả sử module chính là `com.example.shop`, còn plugin CSV là `com.example.shop.plugin.csv`. Các module đã được biên dịch vào `mods` và `plugins`.

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;plugins" --add-modules com.example.shop,com.example.shop.plugin.csv --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Ý nghĩa:

- `--module-path` cung cấp các module JDK, module ứng dụng và module plugin.
- `--add-modules` chọn module chính cùng module plugin làm module roots.
- `jlink` đưa các module roots và dependency bắc cầu của chúng vào runtime image.
- `--output` xác định thư mục runtime image.

Danh sách module được phân cách bằng dấu phẩy. Tên phải là tên module, không phải tên package hay tên lớp. Tên module cần được xác nhận từ `module-info.java`, `module-info.class` hoặc metadata của module.

Nếu một module không có trên module path, `jlink` không thể thêm nó. Khi gặp lỗi không tìm thấy module, hãy kiểm tra tên module và đường dẫn chứa module trước khi sửa danh sách.

## 4. jpackage dùng --add-modules khi tự tạo runtime

`jpackage` có tùy chọn `--add-modules` riêng. Danh sách này được chuyển cho `jlink` khi `jpackage` tạo runtime image.

Với ứng dụng modular:

~~~powershell
jpackage --type app-image --name ShopApp --module-path "$env:JAVA_HOME\jmods;mods;plugins" --module com.example.shop/com.example.shop.Main --add-modules com.example.shop.plugin.csv --dest dist
~~~

Khi chỉ định `--module`, `jpackage` đưa module chính và dependency bắc cầu của nó vào runtime. `--add-modules` bổ sung các module roots khác, chẳng hạn plugin được nạp theo cấu hình.

Với ứng dụng không modular, dùng JAR chính và chỉ rõ các module JDK mà ứng dụng cần:

~~~powershell
jpackage --type app-image --name LegacyTool --input input --main-jar tool.jar --main-class com.example.tool.Main --module-path "$env:JAVA_HOME\jmods" --add-modules java.sql,java.naming --dest dist
~~~

Ở đây `--input` trỏ tới thư mục chứa JAR và tài nguyên ứng dụng; `--main-jar` là đường dẫn JAR tương đối với thư mục input. `--add-modules` yêu cầu runtime image có thêm `java.sql` và `java.naming`.

## 5. Phân biệt module có trong image và module được resolve lúc chạy

Đây là hai bước khác nhau:

1. **Đưa module vào runtime image:** `jlink --add-modules` hoặc `jpackage --add-modules` bảo đảm module có mặt trong runtime được đóng gói.
2. **Resolve module vào module layer lúc khởi chạy:** Java launcher dùng tập root modules để tạo cấu hình module cho lần chạy đó. Với một module bổ sung được nạp động, có thể cần truyền `--add-modules` cho chính Java runtime.

Vì vậy, khi plugin là named module và ứng dụng cần nạp nó bằng reflection, cấu hình launcher của `jpackage` có thể cần thêm Java option:

~~~powershell
jpackage --type app-image --name ShopApp --module-path "$env:JAVA_HOME\jmods;mods;plugins" --module com.example.shop/com.example.shop.Main --add-modules com.example.shop.plugin.csv --java-options "--add-modules=com.example.shop.plugin.csv" --dest dist
~~~

Trong lệnh này:

- `--add-modules com.example.shop.plugin.csv` thuộc nhóm tùy chọn tạo runtime image; nó được chuyển cho `jlink`.
- `--java-options "--add-modules=com.example.shop.plugin.csv"` là tùy chọn truyền cho Java launcher của ứng dụng; nó yêu cầu module system resolve plugin như một root module khi chạy.

Nếu chỉ cần module cho dependency tĩnh, không cần thêm launcher option riêng: module chính và dependency đã được resolve qua module graph. Chỉ thêm runtime `--add-modules` khi module cần được resolve độc lập, chẳng hạn plugin được tìm bằng tên cấu hình.

Với runtime image dựng sẵn bằng `jlink`, thêm module ở bước `jlink`; sau đó cấu hình launcher để resolve module khi cần:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;plugins" --add-modules com.example.shop,com.example.shop.plugin.csv --output build\runtime
jpackage --type app-image --name ShopApp --module-path "$env:JAVA_HOME\jmods;mods;plugins" --module com.example.shop/com.example.shop.Main --runtime-image build\runtime --java-options "--add-modules=com.example.shop.plugin.csv" --dest dist
~~~

Khi đã truyền `--runtime-image`, `jpackage` sử dụng image được tạo trước. Hãy hoàn tất việc chọn module trong lệnh `jlink`; không trông đợi `jpackage --add-modules` bổ sung module vào một runtime image đã tồn tại.

## 6. --add-modules không thay thế requires, exports hoặc opens

Các tùy chọn và khai báo module có mục đích khác nhau:

| Cơ chế | Mục đích |
| --- | --- |
| `requires` | Khai báo dependency module trong module descriptor |
| `jlink --add-modules` | Chọn module roots để liên kết vào runtime image |
| `jpackage --add-modules` | Chuyển thêm module roots cho `jlink` khi `jpackage` tự tạo runtime |
| Java launcher `--add-modules` | Thêm root modules cần resolve khi ứng dụng khởi chạy |
| `exports` | Cho phép module khác truy cập các kiểu public trong package được export |
| `opens` | Cho phép reflection sâu vào package được mở |

Đưa module vào runtime image không tự làm package của module đó trở nên accessible. Nếu framework cần gọi API public, hãy kiểm tra quan hệ readability và `exports`. Nếu framework cần truy cập field hoặc constructor private, hãy mở đúng package cho đúng module bằng `opens` khi thiết kế cho phép.

Không dùng `--add-modules` để xử lý lỗi `IllegalAccessException` hoặc `InaccessibleObjectException`; đó là vấn đề quyền truy cập, không phải vấn đề module có mặt trong image.

## 7. Phân biệt --add-modules với --bind-services

Khi ứng dụng sử dụng SPI và `ServiceLoader`, có thể chọn module provider theo cơ chế service binding thay vì liệt kê từng provider thủ công, miễn là module khai báo `uses` và provider khai báo `provides` phù hợp.

Ví dụ module ứng dụng:

~~~java
module com.example.shop {
    requires com.example.shop.spi;
    uses com.example.shop.spi.Exporter;
}
~~~

Module provider:

~~~java
module com.example.shop.exporter.csv {
    requires com.example.shop.spi;

    provides com.example.shop.spi.Exporter
            with com.example.shop.exporter.csv.CsvExporter;
}
~~~

Hai cơ chế khác nhau:

- `--add-modules` thêm module roots mà bạn chỉ định rõ.
- `--bind-services` yêu cầu `jlink` liên kết các module cung cấp service và dependency của chúng theo service graph.

Trong các JDK hiện hành từ JDK 25, `jpackage` không còn tự thêm service bindings vào runtime image mà nó tạo. Nếu ứng dụng dựa vào provider được phát hiện qua service binding, truyền `--bind-services` qua `--jlink-options`:

~~~powershell
jpackage --type app-image --name ShopApp --module-path "$env:JAVA_HOME\jmods;mods;plugins" --module com.example.shop/com.example.shop.Main --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" --dest dist
~~~

Khi tự đặt `--jlink-options`, hãy giữ lại các tùy chọn tối ưu mặc định mà bạn vẫn cần. Nếu đã tạo runtime bằng `jlink` riêng, dùng `jlink --bind-services` ở bước đó rồi truyền image cho `jpackage --runtime-image`.

Nếu provider được nạp bằng tên lớp trong cấu hình và không được khai báo qua SPI, `--bind-services` không thay thế việc thêm module cụ thể bằng `--add-modules`.

## 8. Chọn module path và loại dependency phù hợp

`jlink` chỉ liên kết các module có thể quan sát trên module path, chẳng hạn JMOD, modular JAR hoặc exploded module. Không thể thêm một JAR classpath bất kỳ vào runtime image bằng cách ghi tên file JAR trong `--add-modules`.

| Dependency | Cách xử lý |
| --- | --- |
| Named module có trên module path | Thêm tên module vào `--add-modules` nếu không được kéo vào qua dependency graph |
| Module JDK | Dùng tên module, ví dụ `java.sql`, `java.naming` |
| JAR chỉ dùng trên classpath | Đóng gói JAR cùng ứng dụng và cấu hình classpath/launcher |
| Plugin ngoài runtime image | Thiết kế cơ chế phân phối và nạp plugin riêng; bảo đảm module path và module layer được cấu hình khi chạy |
| Service provider khai báo `provides` | Cân nhắc `--bind-services` và kiểm thử `ServiceLoader` |

Trên Windows, các mục trong module path được phân cách bằng dấu chấm phẩy (`;`); Linux và macOS thường dùng dấu hai chấm (`:`). Danh sách tên module trong `--add-modules` được phân cách bằng dấu phẩy, không dùng dấu phân cách đường dẫn.

Không chọn toàn bộ module hệ thống hoặc toàn bộ module trên module path chỉ để né lỗi thiếu module nếu mục tiêu là runtime gọn. Hãy xác định module thực sự cần thiết và kiểm thử các tính năng sử dụng chúng.

## 9. Kiểm tra module đã được đóng gói và resolve

Sau khi tạo runtime image, xem các module có thể quan sát:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Đầu ra giúp xác nhận module như `com.example.shop.plugin.csv` có mặt trong image. Tuy nhiên, `--list-modules` không chứng minh module đã được resolve vào boot layer của một lần chạy ứng dụng cụ thể.

Có thể kiểm tra module layer trong ứng dụng:

~~~java
boolean pluginResolved = ModuleLayer.boot()
        .findModule("com.example.shop.plugin.csv")
        .isPresent();

System.out.println("Plugin resolved: " + pluginResolved);
~~~

Sau đó chạy test cho chính chức năng nạp plugin hoặc reflection. Kiểm tra cả cấu hình chọn provider, constructor, dependency của provider và quyền truy cập package nếu framework cần reflection sâu.

## 10. Lỗi thường gặp khi cấu hình --add-modules

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Module ... not found` khi chạy `jlink` | Module không có trên module path hoặc sai tên | Kiểm tra module descriptor và `--module-path` |
| Runtime image thiếu module plugin | Quên thêm module root, hoặc dependency chỉ xuất hiện trong cấu hình | Kiểm tra kết quả `--list-modules` và danh sách cấu hình |
| `ClassNotFoundException` khi nạp lớp | JAR/module không có trong image hoặc classpath | Xác định nơi chứa lớp và cơ chế class loader |
| Module có trong image nhưng không tìm thấy trong boot layer | Module chưa được resolve lúc khởi chạy | Thêm Java launcher `--add-modules` khi phù hợp |
| `ServiceLoader` không tìm thấy provider | Provider không có trong module graph hoặc service binding chưa được cấu hình | Kiểm tra `uses`/`provides`, module path và `--bind-services` |
| `InaccessibleObjectException` | Package chưa mở cho deep reflection | Xem lại `opens` hoặc `--add-opens` có phạm vi phù hợp |
| Runtime image quá lớn | Thêm quá nhiều module roots | Loại module không cần sau khi kiểm thử đầy đủ |

## 11. Quy trình chọn module roots

1. Xác định module chính và các dependency tĩnh từ `module-info.java`.
2. Phân tích dependency tĩnh bằng `jdeps` để lập danh sách ban đầu.
3. Rà cấu hình, reflection, plugin và service để tìm module không được tham chiếu tĩnh.
4. Thêm named module bị bỏ sót vào `jlink --add-modules` hoặc `jpackage --add-modules` khi công cụ tự tạo runtime.
5. Nếu module động cần được resolve lúc ứng dụng khởi chạy, truyền thêm Java launcher `--add-modules` qua cấu hình launcher, chẳng hạn `jpackage --java-options`.
6. Nếu dùng service provider, xác định rõ `uses`/`provides` và cấu hình `--bind-services` khi cần.
7. Kiểm tra module trong runtime image, xác nhận module layer và chạy test trên đúng gói sẽ phát hành.

**Ghi nhớ:** `--add-modules` chọn module roots để tạo runtime image; các dependency `requires` được giải quyết tự động. Với module được nạp động, còn phải xem module có cần được resolve ở thời điểm khởi chạy hay không và cấu hình launcher tương ứng. `--bind-services` phục vụ service provider, còn `exports`/`opens` kiểm soát quyền truy cập. Chọn đúng cơ chế cho từng mục tiêu giúp runtime đủ module mà vẫn gọn và dễ kiểm thử.
