# jpackage kết hợp modular application

## Mục tiêu

Sau bài này, bạn có thể đóng gói một ứng dụng JPMS bằng `jpackage`, tạo app image để kiểm thử, tạo installer theo hệ điều hành, hiểu cách `jpackage` kết hợp module path với runtime image, tùy chỉnh launcher và chuẩn bị artifact có thể phân phối cho người dùng cuối.

## 1. jpackage giải quyết vấn đề gì?

Một modular application thường cần nhiều thành phần để chạy:

- Module ứng dụng chứa main class.
- Các module thư viện mà ứng dụng khai báo bằng `requires`.
- Java runtime tương thích để chạy bytecode và module graph.
- Các file cấu hình, tài nguyên hoặc dữ liệu đi kèm.
- Launcher để người dùng khởi chạy ứng dụng mà không cần tự viết lệnh `java`.

Nếu chỉ phát hành một hoặc nhiều JAR, người dùng thường phải tự cài Java đúng phiên bản, tự cấu hình module path và chạy đúng main module. `jpackage` giúp đóng gói ứng dụng thành application image hoặc native installer, đồng thời có thể tạo runtime image phù hợp bằng `jlink`.

Các loại đầu ra phổ biến:

- **Application image**: thư mục có launcher và runtime cần thiết để chạy ứng dụng.
- **Native installer**: gói cài đặt theo nền tảng, ví dụ MSI/EXE trên Windows, DMG/PKG trên macOS, DEB/RPM trên Linux.

`jpackage` là công cụ của JDK. Hãy dùng JDK có hỗ trợ `jpackage` và `jlink`, không chỉ một JRE rút gọn. Ứng dụng modular được mô tả qua module descriptor; công cụ có thể phân tích dependency để tạo runtime image phù hợp.

## 2. Chuẩn bị một modular application

Ví dụ ứng dụng có hai module:

~~~text
project/
  src/
    com.acme.greeter/
      module-info.java
      com/acme/greeter/Greeter.java
    com.acme.app/
      module-info.java
      com/acme/app/Main.java
  mods/
~~~

Module thư viện:

~~~java
// src/com.acme.greeter/module-info.java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

~~~java
// src/com.acme.greeter/com/acme/greeter/Greeter.java
package com.acme.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Module ứng dụng:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeter.greet(name));
    }
}
~~~

Biên dịch các module vào thư mục `mods`:

~~~bash
javac -d mods --module-source-path src -m com.acme.greeter,com.acme.app
~~~

Sau khi biên dịch, `mods` chứa hai exploded module với `module-info.class` và các class tương ứng. Có thể kiểm tra ứng dụng trước khi đóng gói bằng:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, Java
~~~

Khi ứng dụng chạy được bằng launcher modular thông thường, ta có thể chuyển sang bước đóng gói.

## 3. Tạo application image cho modular app

Cú pháp cốt lõi:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Giải thích:

- `--type app-image` yêu cầu tạo application image thay vì installer.
- `--name AcmeGreeter` đặt tên ứng dụng và launcher.
- `--dest dist` chỉ định thư mục nhận artifact.
- `--module-path mods` chỉ nơi chứa module ứng dụng và các dependency.
- `--module com.acme.app/com.acme.app.Main` chọn root module và main class.

Phần trước dấu gạch chéo là module name; phần sau là tên đầy đủ của main class. Nếu module đã có main class được ghi trong module descriptor, có thể chỉ định module mà không ghi class sau dấu gạch chéo.

Cấu trúc output phụ thuộc nền tảng, nhưng application image thường chứa launcher, thư mục ứng dụng và runtime image. Người dùng có thể chạy launcher được tạo trong image mà không cần tự viết lệnh `java -m`.

Trên Windows, lệnh thường được viết trên một dòng hoặc dùng dấu backtick khi chạy trong PowerShell. Ví dụ một dòng:

~~~powershell
jpackage --type app-image --name AcmeGreeter --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

## 4. Vì sao nên tạo app image trước installer?

Application image giúp kiểm tra artifact gần với sản phẩm phân phối trước khi tạo installer.

Sau khi chạy `jpackage --type app-image`, hãy kiểm tra:

1. Launcher có xuất hiện trong output không?
2. Ứng dụng có khởi động được trên máy không có cấu hình phát triển không?
3. Các module dependency có được đóng gói đầy đủ không?
4. Tài nguyên và file cấu hình cần thiết có được tìm thấy không?
5. Logging, file ghi ra và đường dẫn dữ liệu có hoạt động trong layout mới không?

Đừng giả định working directory của launcher luôn là thư mục source hoặc thư mục hiện tại trong IDE. Ứng dụng đóng gói nên xác định rõ vị trí resource, thư mục cấu hình và thư mục dữ liệu theo quy tắc phù hợp với hệ điều hành.

Nếu app image hoạt động đúng, có thể dùng cùng các thông tin module để tạo installer.

## 5. Tạo native installer

Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name AcmeGreeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Có thể dùng `--type exe` nếu muốn tạo installer EXE trên môi trường Windows có hỗ trợ.

Ví dụ trên macOS:

~~~bash
jpackage --type dmg --name AcmeGreeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Ví dụ trên Linux:

~~~bash
jpackage --type deb --name acme-greeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Linux cũng có thể tạo RPM nếu môi trường hỗ trợ:

~~~bash
jpackage --type rpm --name acme-greeter --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Các loại installer được hỗ trợ phụ thuộc nền tảng và phiên bản JDK. Công cụ thường yêu cầu tiện ích đóng gói hoặc signing tương ứng của hệ điều hành. Hãy kiểm tra tài liệu `jpackage` của JDK đang dùng và cài các công cụ native mà nền tảng yêu cầu.

Native installer được tạo cho nền tảng hiện tại. Muốn phát hành cho Windows, macOS và Linux, hãy build và kiểm thử trên từng nền tảng đích hoặc dùng máy build phù hợp cho từng hệ điều hành. `jpackage` không phải công cụ cross-compile installer tùy ý giữa các hệ điều hành.

## 6. jpackage và runtime image

Nếu không chỉ định runtime image có sẵn, `jpackage` có thể gọi `jlink` để tạo runtime image cho ứng dụng modular. Runtime image giúp giảm nhu cầu yêu cầu người dùng cài một JDK đầy đủ.

Module system cung cấp dependency graph từ module descriptor. Công cụ có thể xác định module ứng dụng và các dependency cần thiết để tạo runtime phù hợp. Điều này đặc biệt hữu ích khi ứng dụng chỉ dùng một phần Java platform.

Có thể truyền tùy chọn cho `jlink` bằng `--jlink-options`. Ví dụ:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main \
  --jlink-options "--strip-debug --no-header-files --no-man-pages"
~~~

Các tùy chọn như `--strip-debug`, `--no-header-files` và `--no-man-pages` giúp loại bỏ một số thành phần không cần thiết trong runtime image. Chỉ bật tùy chọn phù hợp với yêu cầu debug, native integration và vận hành của ứng dụng.

Nếu ứng dụng dùng service provider và cần các provider module được liên kết trong runtime image, hãy xem xét tùy chọn `--bind-services` của `jlink` qua `--jlink-options`. Kiểm tra kỹ các service cần thiết trong ứng dụng sau khi tạo image rút gọn.

### Dùng runtime image tự tạo

Có thể tự tạo runtime image bằng `jlink` khi cần kiểm soát module được đưa vào runtime:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --output runtime-image
~~~

Ví dụ trên dùng dấu hai chấm trên Linux/macOS. Trên Windows, thay bằng dấu chấm phẩy và dùng đường dẫn JDK tương ứng.

Sau đó, truyền runtime image đã tạo vào `jpackage`:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --runtime-image runtime-image \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Runtime image phải tương thích với ứng dụng và nền tảng đích, đồng thời chứa đủ Java module cần thiết. Nếu dùng runtime image tự tạo, hãy kiểm tra các module cần cho ứng dụng, reflection, service loading, charset, logging và native integration trước khi phát hành.

## 7. Đưa resource và file phụ trợ vào gói

Một ứng dụng thực tế thường cần file cấu hình mặc định, template, license hoặc dữ liệu khởi tạo. `--input` chỉ định thư mục chứa các file bổ sung được đưa vào gói.

Ví dụ:

~~~text
project/
  mods/
  package-input/
    config/
      defaults.properties
    templates/
      welcome.html
~~~

Đóng gói:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --input package-input \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Các file trong input directory được đưa vào application image theo layout của công cụ. Hãy kiểm tra vị trí thực tế trong image và dùng đường dẫn tương đối phù hợp trong ứng dụng.

Không nên ghi dữ liệu người dùng vào thư mục cài đặt vì thư mục đó có thể cần quyền administrator hoặc bị thay thế khi nâng cấp. Dữ liệu thay đổi trong quá trình sử dụng nên nằm ở thư mục dữ liệu người dùng phù hợp với nền tảng.

Có thể dùng `--resource-dir` để cung cấp các resource tùy chỉnh cho quá trình đóng gói, ví dụ template launcher hoặc file cấu hình đặc thù của installer. Phân biệt resource phục vụ quá trình tạo gói với file ứng dụng cần đọc ở runtime.

## 8. Tùy chỉnh launcher và metadata

Một số option hữu ích:

| Option | Mục đích |
| --- | --- |
| `--name` | Tên ứng dụng và launcher. |
| `--app-version` | Phiên bản hiển thị của ứng dụng/package. |
| `--vendor` | Tên nhà phát hành. |
| `--description` | Mô tả ứng dụng trong metadata installer nếu nền tảng hỗ trợ. |
| `--icon` | Icon ứng dụng hoặc installer theo định dạng nền tảng yêu cầu. |
| `--arguments` | Các argument mặc định truyền cho ứng dụng khi launcher chạy. |
| `--java-options` | JVM option được truyền cho runtime của ứng dụng. |
| `--add-launcher` | Tạo thêm launcher với cấu hình riêng từ file properties. |
| `--dest` | Thư mục output. |
| `--type` | Loại artifact, ví dụ `app-image`, `msi`, `dmg`, `deb` hoặc `rpm`. |

Ví dụ thêm metadata và JVM option:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --app-version 1.2.0 \
  --vendor "Acme Software" \
  --description "Modular greeting application" \
  --java-options "-Dapp.environment=production" \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

`--java-options` dành cho option của JVM, ví dụ system property, heap size hoặc module opening cần thiết. `--arguments` dành cho argument của ứng dụng. Đừng nhầm hai nhóm này: JVM option được xử lý bởi Java runtime, còn application argument xuất hiện trong `main(String[] args)`.

Để tạo launcher bổ sung, `--add-launcher` nhận tên launcher và file properties mô tả main module/class, arguments hoặc JVM options riêng. Điều này hữu ích khi một sản phẩm có nhiều chế độ chạy, ví dụ giao diện chính và công cụ quản trị.

## 9. Tích hợp `--add-opens` và các JVM option

Một framework cũ có thể cần deep reflection vào package cụ thể. Khi chạy bằng lệnh `java`, ta thường thêm `--add-opens` trực tiếp vào JVM arguments. Với ứng dụng được đóng gói, có thể cấu hình JVM option qua `--java-options`:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main \
  --java-options "--add-opens=java.base/java.lang=ALL-UNNAMED"
~~~

Option này sẽ được truyền cho JVM của launcher được tạo. Chỉ thêm package và target module thực sự cần thiết. Nếu framework là named module, ưu tiên target module cụ thể thay vì `ALL-UNNAMED`.

Nếu dùng file cấu hình launcher riêng với `--add-launcher`, có thể quản lý JVM options theo từng launcher. Hãy xác nhận option xuất hiện trong launcher cuối cùng và kiểm thử bằng chính application image, vì chạy từ IDE không đảm bảo môi trường đóng gói có cùng cấu hình.

## 10. Kiểm tra artifact trước khi phát hành

Một quy trình thực tế:

1. Biên dịch các module và kiểm tra module descriptor.
2. Chạy thử bằng `java --module-path ... --module ...`.
3. Tạo app image bằng `jpackage --type app-image`.
4. Chạy launcher từ app image trên máy sạch hoặc môi trường gần với người dùng.
5. Kiểm tra resource, log, dữ liệu, JVM option và hành vi cập nhật.
6. Tạo installer theo nền tảng đích.
7. Cài đặt, chạy, gỡ cài đặt và kiểm tra nâng cấp nếu sản phẩm hỗ trợ.
8. Ký artifact nếu quy trình phân phối hoặc hệ điều hành yêu cầu.

Đừng chỉ kiểm tra lệnh `jpackage` kết thúc thành công. Artifact có thể tạo được nhưng thiếu resource hoặc có lỗi runtime chỉ xuất hiện trên máy không có JDK cài sẵn.

Với native installer, kiểm tra tên package, phiên bản, vendor, vị trí cài đặt, shortcut/menu entry và khả năng uninstall theo đặc điểm nền tảng.

## 11. Lỗi thường gặp

### Module not found hoặc dependency không được phân giải

Kiểm tra `--module-path` có chứa root module và dependency không. Dùng `jar --describe-module` để xem tên module thật trong JAR, và chạy ứng dụng bằng `java -p ... -m ...` trước khi đóng gói.

### Không tìm thấy main class

Kiểm tra phần `module/main-class` trong `--module`. Tên class phải đầy đủ package. Nếu bỏ main class, module cần có main class được ghi trong descriptor.

### jlink không tạo được runtime image

Kiểm tra module path, dependency, JDK đang dùng và các `jlink-options`. Nếu ứng dụng dùng native library hoặc service provider, kiểm tra module tương ứng có nằm trong runtime image không.

### Installer không được hỗ trợ trên máy build

Một số loại package cần tool native của hệ điều hành. Hãy dùng môi trường build đúng nền tảng và cài tiện ích mà phiên bản `jpackage` yêu cầu. Nếu chỉ cần kiểm tra app image, dùng `--type app-image` để tách vấn đề đóng gói runtime khỏi vấn đề tạo installer.

### Ứng dụng không tìm thấy file sau khi cài đặt

Không giả định current working directory giống lúc chạy từ IDE. Kiểm tra layout của application image, vị trí input files và cách ứng dụng xác định resource. Đối với file có thể thay đổi, dùng thư mục dữ liệu người dùng thay vì ghi vào thư mục cài đặt.

### JVM option không có tác dụng

Xác nhận option được truyền bằng `--java-options` và nằm trong launcher đúng. Với `--add-opens`, kiểm tra source module, package và target module có khớp với thông báo lỗi reflection không.

## Ghi nhớ

`jpackage` đóng gói modular application thành app image hoặc native installer. Với modular app, dùng `--module-path` để chỉ các module và `--module module/main-class` để chọn entry point. Nếu không cung cấp runtime image, công cụ có thể dùng `jlink` để tạo runtime phù hợp; có thể cung cấp image tự tạo bằng `--runtime-image`. Tạo và kiểm thử app image trước, sau đó build installer trên nền tảng đích. Dùng `--java-options` cho JVM option và `--arguments` cho argument của ứng dụng.
