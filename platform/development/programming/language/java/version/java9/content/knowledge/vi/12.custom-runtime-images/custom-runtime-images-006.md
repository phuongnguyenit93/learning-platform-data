# Tạo launcher cho ứng dụng mô-đun

Một ứng dụng Java dạng mô-đun được khởi chạy bằng tên module và lớp main. Java launcher phân giải module cùng các dependency trên module path, sau đó gọi điểm vào của chương trình. Với JPMS, có thể chạy trực tiếp các module đã biên dịch, đóng gói thành modular JAR, tạo runtime image bằng jlink hoặc đóng gói thành ứng dụng phân phối bằng jpackage.

Bài học này hướng dẫn cách chuẩn bị module descriptor, biên dịch, chạy và phân phối một ứng dụng mô-đun bằng các công cụ hiện hành của JDK. Các ví dụ dùng Java 17 trở lên.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt classpath và module path khi khởi chạy ứng dụng.
- Xác định module name, main class và cách khai báo điểm vào.
- Chạy module đã biên dịch bằng tùy chọn --module.
- Đóng gói modular JAR có main class và chạy JAR trên module path.
- Tạo runtime image và launcher riêng bằng jlink.
- Đóng gói app image hoặc bộ cài đặt bằng jpackage.
- Truyền JVM options và application arguments đúng vị trí.
- Kiểm tra module graph và xử lý lỗi khởi chạy phổ biến.

## 1. Launcher của ứng dụng mô-đun

### 1.1. Vai trò của Java launcher

Java launcher khởi động JVM và chuyển quyền điều khiển đến điểm vào ứng dụng. Khi khởi chạy một named module, launcher cần biết module gốc, module path, main class, JVM options và tham số ứng dụng.

Cú pháp thường dùng:

~~~text
java [JVM options] --module-path <path> --module <module>[/<main-class>] [application arguments]
~~~

Ví dụ:

~~~bash
java --module-path mods --module launcher.app/com.acme.launcher.Main one two
~~~

Trong đó, --module-path chỉ vị trí các module; --module chọn module cần chạy; launcher.app là module name; com.acme.launcher.Main là main class; one và two là đối số của ứng dụng.

Có thể dùng dạng ngắn -p thay cho --module-path và -m thay cho --module.

### 1.2. Điểm vào ứng dụng

Với Java 17, điểm vào thông dụng là phương thức public static void main(String[] args):

~~~java
package com.acme.launcher;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Nếu module có nhiều lớp chứa main method, lệnh khởi chạy cần chọn đúng lớp hoặc module metadata phải xác định main class mặc định.

Main class không cần nằm trong package export chỉ để Java launcher gọi nó. Export điều chỉnh khả năng truy cập package từ module khác; launcher có thể khởi chạy main class thuộc package không export trong module được chọn.

### 1.3. Module descriptor

Một ứng dụng có thể tách API và launcher:

~~~text
src/
├── greeting.api/
│   ├── module-info.java
│   └── com/acme/greeting/api/Greeter.java
└── launcher.app/
    ├── module-info.java
    └── com/acme/launcher/Main.java
~~~

Module API công bố package chứa hợp đồng:

~~~java
module greeting.api {
    exports com.acme.greeting.api;
}
~~~

Module launcher khai báo dependency:

~~~java
module launcher.app {
    requires greeting.api;
}
~~~

Khi chạy launcher.app, JPMS phân giải greeting.api theo module graph. Package chứa Main không cần export nếu không có module khác cần truy cập package đó.

## 2. Module path và classpath

### 2.1. Module path

Module path là nơi Java launcher tìm named modules. Các phần tử phổ biến gồm:

- Thư mục chứa exploded modules đã biên dịch.
- Modular JAR có module-info.class.
- Thư mục chứa các modular JAR.

Ví dụ module path dạng exploded modules:

~~~text
mods/
├── greeting.api/
│   ├── module-info.class
│   └── com/acme/greeting/api/Greeter.class
└── launcher.app/
    ├── module-info.class
    └── com/acme/launcher/Main.class
~~~

Hoặc module path chứa JAR:

~~~text
mods/
├── greeting.api.jar
└── launcher.app.jar
~~~

Trên Windows, nhiều phần tử module path được phân cách bằng dấu chấm phẩy. Trên Linux và macOS, dùng dấu hai chấm. Đặt giá trị trong dấu ngoặc kép nếu đường dẫn có khoảng trắng.

### 2.2. Classpath

Classpath vẫn được hỗ trợ cho ứng dụng chạy trong unnamed module:

~~~bash
java -cp "lib/*;classes" com.acme.launcher.Main
~~~

Cách chạy này không yêu cầu ứng dụng được định nghĩa thành named module và không áp dụng đầy đủ ranh giới module của JPMS.

Với ứng dụng đã thiết kế bằng module-info.java, hãy đặt module trên module path và khởi chạy bằng -m/--module để JVM sử dụng module descriptor cùng các dependency đã khai báo.

### 2.3. Không nhầm -jar với module launch

Một modular JAR có thể chứa module-info.class, nhưng java -jar đi theo chế độ executable JAR dựa trên manifest Main-Class và classpath. Các dependency trong requires không được phân giải như module dependencies trên module path.

Nếu ứng dụng phụ thuộc greeting.api nhưng chỉ chạy bằng java -jar, có thể gặp NoClassDefFoundError khi greeting.api chỉ nằm trên module path. Với ứng dụng mô-đun, dùng --module-path và -m.

## 3. Biên dịch và chạy exploded modules

### 3.1. Biên dịch nhiều module

Từ thư mục dự án có cấu trúc src, dùng javac:

~~~bash
javac --release 17 --module-source-path src -d out -m greeting.api,launcher.app
~~~

- --release 17 biên dịch theo API và bytecode tương thích Java 17.
- --module-source-path src chỉ thư mục chứa source của các module.
- -d out là thư mục nhận kết quả biên dịch.
- -m liệt kê các module cần biên dịch.

Sau khi biên dịch, out chứa một thư mục cho từng module. Có thể dùng trực tiếp thư mục này làm module path.

### 3.2. Khởi chạy module

Chỉ rõ module và main class:

~~~bash
java --module-path out --module launcher.app/com.acme.launcher.Main one two
~~~

Nếu module đã có main class metadata, có thể chỉ định module name:

~~~bash
java --module-path out --module launcher.app one two
~~~

Với exploded modules được biên dịch trực tiếp bằng javac, ModuleMainClass thường chưa được thiết lập. Khi đó hãy chỉ rõ main class sau dấu gạch chéo.

### 3.3. Application arguments

Mọi đối số nằm sau module target được chuyển tới main method qua String[] args:

~~~java
public static void main(String[] args) {
    for (int i = 0; i < args.length; i++) {
        System.out.println("args[" + i + "]=" + args[i]);
    }
}
~~~

Lệnh:

~~~bash
java --module-path out -m launcher.app/com.acme.launcher.Main --profile production 8080
~~~

truyền ba phần tử vào args: --profile, production và 8080. Launcher không diễn giải chúng thành JVM options sau khi đã xác định application entry point.

## 4. Main class mặc định trong modular JAR

### 4.1. Chỉ định main class trên command line

Cách rõ ràng nhất là ghi module name và main class:

~~~bash
java --module-path mods -m launcher.app/com.acme.launcher.Main
~~~

Cách này không cần metadata main class trong module. Nó hữu ích khi module có nhiều entry point hoặc muốn chọn một chế độ chạy cụ thể.

### 4.2. Ghi main class vào modular JAR

Công cụ jar hỗ trợ tùy chọn --main-class. Khi tạo modular JAR, tùy chọn này ghi main class vào module metadata:

~~~bash
jar --create --file mods/launcher.app.jar --main-class com.acme.launcher.Main -C out/launcher.app .
~~~

Kiểm tra metadata:

~~~bash
jar --describe-module --file mods/launcher.app.jar
~~~

Kết quả có dòng main-class com.acme.launcher.Main nếu metadata được ghi đúng.

### 4.3. Chạy mà không cần ghi tên main class

Khi modular JAR có main class metadata, có thể chạy:

~~~bash
java --module-path mods -m launcher.app
~~~

Launcher dùng main class đã khai báo trong module. Nếu module không có metadata và lệnh không chỉ định class, launcher không thể xác định điểm vào.

## 5. Đóng gói và chạy modular JAR

### 5.1. Đóng gói module API và launcher

Sau khi biên dịch vào out, tạo modular JAR:

~~~bash
jar --create --file mods/greeting.api.jar -C out/greeting.api .
jar --create --file mods/launcher.app.jar --main-class com.acme.launcher.Main -C out/launcher.app .
~~~

Module path lúc này chứa greeting.api.jar và launcher.app.jar.

### 5.2. Chạy modular JAR

Dùng module path và module name:

~~~bash
java --module-path mods -m launcher.app
~~~

Hoặc chọn main class rõ ràng:

~~~bash
java --module-path mods -m launcher.app/com.acme.launcher.Main
~~~

Launcher đọc module descriptor và class trực tiếp từ modular JAR; không cần giải nén JAR.

### 5.3. So sánh các chế độ chạy

| Cách chạy | Cơ chế |
| --- | --- |
| java --module-path mods -m launcher.app | Khởi chạy named module và phân giải requires trên module path |
| java --module-path mods -m launcher.app/com.acme.launcher.Main | Khởi chạy named module và chọn main class rõ ràng |
| java -jar launcher.app.jar | Khởi chạy executable JAR theo manifest Main-Class và classpath |

Tùy chọn -jar không thay thế việc phân giải module dependencies. Nếu chạy JAR theo classpath, phải cung cấp dependencies theo classpath riêng; module-info không tự làm việc đó.

## 6. Tạo runtime image bằng jlink

### 6.1. Vai trò của jlink

jlink kết hợp module ứng dụng với các module nền tảng cần thiết từ JDK để tạo runtime image tùy chỉnh. Image có thể chứa launcher riêng nhờ tùy chọn --launcher.

Lợi ích:

- Phân phối ứng dụng cùng runtime phù hợp.
- Không yêu cầu máy đích cài riêng một JDK đầy đủ.
- Chỉ đưa các module cần thiết vào runtime image.
- Tạo launcher ngắn gọn thay cho lệnh java dài.

jlink tạo runtime image, không tự tạo bộ cài đặt MSI, DMG hoặc DEB.

### 6.2. Chọn module gốc

jlink bắt đầu từ module chỉ định bằng --add-modules rồi phân giải các dependency requires cần thiết.

Nếu launcher.app requires greeting.api, thêm launcher.app làm root sẽ đưa greeting.api vào image khi module có trên module path và graph hợp lệ.

Nếu ứng dụng dùng service provider và cần liên kết provider trong image, có thể cân nhắc --bind-services. Chỉ bật khi service binding phù hợp với cấu hình ứng dụng.

### 6.3. Tạo image trên Windows

Từ thư mục dự án có mods chứa modular JAR, dùng PowerShell:

~~~powershell
$modulePath = "$env:JAVA_HOME\jmods;mods"
jlink --module-path $modulePath --add-modules launcher.app --launcher catalog=launcher.app/com.acme.launcher.Main --output image
~~~

Launcher được tạo trong image/bin. Trên Windows có thể chạy:

~~~powershell
.\image\bin\catalog.bat one two
~~~

### 6.4. Tạo image trên Linux hoặc macOS

Trên hệ điều hành dùng dấu hai chấm để phân cách module path:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules launcher.app --launcher catalog=launcher.app/com.acme.launcher.Main --output image
~~~

Chạy launcher:

~~~bash
./image/bin/catalog one two
~~~

Launcher dùng runtime đi kèm image. Nếu cần runtime image cho một phiên bản Java cụ thể, hãy dùng jlink và module nền tảng từ đúng JDK mục tiêu.

### 6.5. Tùy chọn tối ưu image

Một số tùy chọn jlink:

- --strip-debug loại bỏ thông tin debug.
- --no-header-files loại bỏ header files.
- --no-man-pages loại bỏ man pages.
- --compress=2 bật mức nén được hỗ trợ.
- --list-plugins hiển thị plugin jlink có sẵn trong JDK.

Chỉ bật tùy chọn sau khi kiểm tra nhu cầu phân phối và khả năng chẩn đoán. Không loại bỏ dữ liệu cần thiết cho quy trình hỗ trợ lỗi.

## 7. Đóng gói bằng jpackage

### 7.1. Vai trò của jpackage

jpackage tạo gói phân phối cho ứng dụng Java. Công cụ có thể tạo application image hoặc bộ cài đặt phù hợp với nền tảng. Với ứng dụng mô-đun, cung cấp module path và module/main class.

App image thường chứa launcher, ứng dụng và runtime cần thiết. Người dùng có thể chạy launcher mà không cần tự viết lệnh java.

### 7.2. Tạo app image từ modular modules

Khi mods chứa greeting.api.jar và launcher.app.jar:

~~~bash
jpackage --type app-image --name Catalog --dest packages --module-path mods --module launcher.app/com.acme.launcher.Main
~~~

Thư mục packages chứa application image với launcher tương ứng. Trên Windows, launcher thường là file EXE trong thư mục app image.

### 7.3. Tạo bộ cài đặt

Tùy nền tảng và môi trường build, jpackage hỗ trợ các loại gói như:

| Nền tảng | Loại gói thường dùng |
| --- | --- |
| Windows | exe, msi |
| macOS | dmg, pkg |
| Linux | deb, rpm |

Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name Catalog --dest packages --module-path mods --module launcher.app/com.acme.launcher.Main
~~~

Bộ cài đặt chỉ tạo được khi công cụ đóng gói và môi trường build đáp ứng yêu cầu của nền tảng. Hãy chạy jpackage trên hệ điều hành mục tiêu và kiểm tra tùy chọn nền tảng trước khi phát hành.

### 7.4. Thông tin phân phối

jpackage có các tùy chọn cấu hình tên ứng dụng, phiên bản, vendor, icon, thư mục đích và shortcut. Chỉ thêm thông tin phù hợp với quy trình phát hành thực tế.

Nếu đã tạo runtime image riêng bằng jlink, có thể thiết kế quy trình đóng gói sử dụng runtime image đó. Cần đảm bảo runtime image và module ứng dụng tương thích.

## 8. JVM options và cấu hình lúc chạy

### 8.1. Phân biệt JVM options và application arguments

Cú pháp tổng quát:

~~~text
java [JVM options] --module-path <path> --module <module>[/<main-class>] [application arguments]
~~~

JVM options nằm trước module target. Application arguments nằm sau module target.

Ví dụ:

~~~bash
java -Xms128m -Xmx512m -Dapp.env=production --module-path mods -m launcher.app/com.acme.launcher.Main --port 8080
~~~

- -Xms128m và -Xmx512m cấu hình heap.
- -Dapp.env=production đặt system property.
- --module-path và -m chọn module.
- --port 8080 là tham số ứng dụng.

Trong Java:

~~~java
String environment = System.getProperty("app.env");
System.out.println("environment=" + environment);
System.out.println("first argument=" + args[0]);
~~~

### 8.2. Chẩn đoán module resolution

Khi ứng dụng không khởi chạy được, dùng:

~~~bash
java --show-module-resolution --module-path mods -m launcher.app/com.acme.launcher.Main
~~~

Một số lệnh kiểm tra khác:

~~~bash
java --validate-modules --module-path mods
java --list-modules
java --describe-module launcher.app
jar --describe-module --file mods/launcher.app.jar
~~~

- --show-module-resolution hiển thị quá trình phân giải module.
- --validate-modules kiểm tra module graph trên module path được cung cấp.
- --list-modules liệt kê các module runtime quan sát được.
- --describe-module hiển thị thông tin module cụ thể.
- jar --describe-module kiểm tra descriptor trong JAR.

### 8.3. Tùy chọn quyền truy cập bổ sung

Các tùy chọn --add-reads, --add-exports và --add-opens có thể thay đổi readability, export hoặc reflection access trong một lần chạy. Chúng hữu ích cho chẩn đoán hoặc tích hợp có chủ đích với thư viện cần quyền đặc biệt.

Không thêm các tùy chọn này để che lỗi thiết kế module. Hãy sửa module-info.java hoặc thiết kế API khi ứng dụng cần quyền truy cập lâu dài và hợp lệ.

## 9. Launcher script

### 9.1. Script Windows

Khi phân phối các module trong thư mục mods, có thể tạo run-app.bat:

~~~bat
@echo off
set "APP_HOME=%~dp0"
java --module-path "%APP_HOME%mods" -m launcher.app/com.acme.launcher.Main %*
~~~

Script dùng thư mục chứa chính nó để tìm module path. Nếu phân phối runtime image riêng, có thể gọi java.exe trong runtime đi kèm image.

### 9.2. Script Linux hoặc macOS

Có thể tạo run-app.sh:

~~~bash
#!/usr/bin/env sh
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec java --module-path "$APP_DIR/mods" -m launcher.app/com.acme.launcher.Main "$@"
~~~

Cấp quyền thực thi:

~~~bash
chmod +x run-app.sh
~~~

Script giúp người dùng chạy ứng dụng bằng một lệnh ngắn. Với sản phẩm phân phối rộng, jlink hoặc jpackage thường phù hợp hơn vì có thể đóng gói runtime và launcher theo cấu trúc chuẩn.

## 10. Ví dụ hoàn chỉnh: biên dịch, chạy, JAR và runtime image

Ví dụ có hai module: greeting.api công bố interface Greeter; launcher.app yêu cầu greeting.api và chứa main class.

### 10.1. Source code

File src/greeting.api/module-info.java:

~~~java
module greeting.api {
    exports com.acme.greeting.api;
}
~~~

File src/greeting.api/com/acme/greeting/api/Greeter.java:

~~~java
package com.acme.greeting.api;

public interface Greeter {
    String greet(String name);
}
~~~

File src/launcher.app/module-info.java:

~~~java
module launcher.app {
    requires greeting.api;
}
~~~

File src/launcher.app/com/acme/launcher/Main.java:

~~~java
package com.acme.launcher;

import com.acme.greeting.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        Greeter greeter = name -> "Hello, " + name + "!";

        System.out.println("launcher=modular-app");
        System.out.println("module=" + Main.class.getModule().getName());
        System.out.println("greeting=" + greeter.greet("Ada"));
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

### 10.2. Biên dịch và chạy exploded modules

Từ thư mục chứa src:

~~~bash
javac --release 17 --module-source-path src -d out -m greeting.api,launcher.app
java --module-path out -m launcher.app/com.acme.launcher.Main one two
~~~

Stdout:

~~~text
launcher=modular-app
module=launcher.app
greeting=Hello, Ada!
args=one,two
~~~

### 10.3. Tạo modular JAR và chạy

Tạo các JAR:

~~~bash
jar --create --file mods/greeting.api.jar -C out/greeting.api .
jar --create --file mods/launcher.app.jar --main-class com.acme.launcher.Main -C out/launcher.app .
jar --describe-module --file mods/launcher.app.jar
~~~

Khởi chạy module bằng main class đã lưu trong metadata:

~~~bash
java --module-path mods -m launcher.app one two
~~~

Stdout giống ví dụ exploded modules:

~~~text
launcher=modular-app
module=launcher.app
greeting=Hello, Ada!
args=one,two
~~~

### 10.4. Tạo runtime image

Trên Windows PowerShell:

~~~powershell
$modulePath = "$env:JAVA_HOME\jmods;mods"
jlink --module-path $modulePath --add-modules launcher.app --launcher catalog=launcher.app/com.acme.launcher.Main --output image
.\image\bin\catalog.bat one two
~~~

Stdout:

~~~text
launcher=modular-app
module=launcher.app
greeting=Hello, Ada!
args=one,two
~~~

Runtime image đã chứa runtime và launcher catalog. Khi phân phối image, người dùng chạy launcher trong image/bin.

## 11. Lỗi thường gặp khi khởi chạy ứng dụng mô-đun

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Module not found | Module path sai hoặc thiếu module JAR/thư mục module | Kiểm tra --module-path, tên module và nội dung JAR |
| FindException hoặc ResolutionException | Dependency không có hoặc module graph xung đột | Kiểm tra requires và module path bằng --show-module-resolution |
| Main method not found | Chọn sai main class hoặc class không có entry point phù hợp | Kiểm tra tên lớp và public static main(String[] args) |
| Không xác định được main class | Module không có ModuleMainClass và lệnh không chỉ định class | Dùng -m module/main.class hoặc đóng gói bằng jar --main-class |
| NoClassDefFoundError khi dùng -jar | Dependency mô-đun chỉ có trên module path nhưng ứng dụng được chạy theo classpath | Khởi chạy bằng --module-path và -m |
| InvalidModuleDescriptorException | module-info.class hoặc descriptor trong JAR không hợp lệ | Biên dịch lại module và kiểm tra bằng jar --describe-module |
| jlink không tìm thấy module | Thiếu JDK jmods hoặc module ứng dụng trong module path | Thêm đúng JDK jmods và module path ứng dụng |
| jpackage không tạo được bộ cài | Loại gói hoặc công cụ nền tảng không có trên máy build | Chạy trên nền tảng mục tiêu và kiểm tra yêu cầu của loại gói |

Khi gặp lỗi, hãy xác định đang lỗi ở bước tìm module, phân giải dependency, chọn main class hay khởi tạo runtime. Mỗi bước có cách kiểm tra riêng; thay đổi classpath hoặc thêm quyền module không giải quyết được mọi loại lỗi.

## 12. Checklist phát hành launcher

- [ ] Mỗi module có tên và module-info.java hợp lệ.
- [ ] Module launcher khai báo đầy đủ requires.
- [ ] Main class và chữ ký main method đã được xác nhận.
- [ ] Đã chọn module path và tên module đúng.
- [ ] Application arguments được truyền sau module target.
- [ ] Modular JAR có ModuleMainClass nếu muốn bỏ tên main class khỏi lệnh.
- [ ] Không dùng -jar như cách thay thế module-path cho ứng dụng modular.
- [ ] Đã kiểm tra module graph bằng --show-module-resolution hoặc --validate-modules.
- [ ] Runtime image được tạo từ JDK mục tiêu bằng jlink.
- [ ] Launcher của runtime image chạy được trên môi trường đích.
- [ ] Nếu dùng jpackage, đã kiểm tra loại gói trên hệ điều hành mục tiêu.
- [ ] Các JVM options và system properties cần thiết được cấu hình rõ.
- [ ] Các tùy chọn add-reads/add-exports/add-opens chỉ được dùng khi có lý do cụ thể.
- [ ] Đã kiểm thử từ đúng working directory và với đường dẫn có khoảng trắng.
