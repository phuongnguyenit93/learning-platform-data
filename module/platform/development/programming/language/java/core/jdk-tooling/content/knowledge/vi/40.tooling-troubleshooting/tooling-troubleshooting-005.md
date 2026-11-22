# Khắc phục lỗi sai module path trong Java

Module path là nơi Java tìm các module đã được biên dịch, chẳng hạn module trong thư mục output hoặc modular JAR. Khi module path sai, compiler hoặc JVM có thể không tìm thấy module được khai báo trong module-info.java, tìm nhầm một bản module khác, hoặc tìm thấy module nhưng không được phép truy cập package cần dùng.

Để sửa đúng, cần phân biệt ba việc: tìm thấy module, module đọc được module phụ thuộc, và package cần dùng được module kia export. Đường dẫn đúng chỉ giải quyết bước tìm module; các khai báo requires và exports vẫn phải đúng.

Bài này dùng Java 17 trở lên và một ví dụ có hai module độc lập. Các lệnh được chạy trên Amazon Corretto 17.0.15+6-LTS trên Windows.

## 1. Module path là gì?

Từ Java 9, Java Platform Module System (JPMS) chia ứng dụng thành các module. Mỗi module có tên và có thể có file mô tả module-info.java. File này khai báo module cần module nào và package nào được công khai cho module khác.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Ứng dụng com.example.app khai báo rằng nó cần module com.example.greeter. Khi biên dịch hoặc chạy, Java phải tìm được module đó trên module path hoặc trong các module có sẵn của JDK.

Module path có thể chứa:

- Modular JAR: file JAR có module-info.class ở thư mục gốc.
- Exploded module: thư mục đã biên dịch, có module-info.class ở thư mục gốc và các package ở bên dưới.
- Automatic module: thư viện JAR chưa có module-info.class nhưng được đặt trên module path. Tên module được lấy từ Automatic-Module-Name trong manifest nếu có, hoặc được suy ra từ tên JAR.

Một thư mục chứa nhiều module thường được tổ chức như sau:

~~~text
mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── greeter/
│               └── Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Khi đó, mods là thư mục module path. Mỗi thư mục con là một exploded module. Nếu các module được đóng gói thành JAR, thư mục lib có thể chứa nhiều modular JAR:

~~~text
lib/
├── com.example.greeter.jar
└── com.example.app.jar
~~~

Đường dẫn trên filesystem và tên module là hai giá trị khác nhau. Tên module được khai báo trong module-info.java hoặc được suy ra với automatic module; đường dẫn chỉ cho Java biết nơi tìm file/module.

## 2. Phân biệt các loại path

Đây là nguyên nhân gây nhầm lẫn phổ biến nhất:

| Tùy chọn | Dùng để tìm gì? | Khi nào dùng? |
|---|---|---|
| `--module-path` hoặc `-p` | Module đã biên dịch, modular JAR, automatic module | Compile và chạy ứng dụng modular |
| `--module-source-path` | Source code của một hoặc nhiều module | Biên dịch nhiều module từ source tree |
| `--class-path`, `-classpath` hoặc `-cp` | Class và JAR trên classpath, thuộc unnamed module | Ứng dụng/classic library không phải named module |
| `--source-path` | Source code theo package hierarchy | Compile source thông thường hoặc một module |
| `--upgrade-module-path` | Bản thay thế cho một số module của JDK | Trường hợp nâng cấp module hệ thống đặc biệt |
| `--patch-module` | Nội dung bổ sung vào một module đã có | Test hoặc vá module trong tình huống chuyên biệt |

Không dùng --module-path để trỏ tới thư mục source chứa module-info.java rồi mong compiler tự tìm mọi source. Khi biên dịch nhiều module, hãy dùng --module-source-path. --module-path là nơi tìm các module đã có thể được sử dụng làm dependency.

Ví dụ hai thư mục khác nhau:

~~~text
project/
├── src/       # module source path
│   ├── com.example.greeter/
│   └── com.example.app/
├── mods/      # compiled module path
│   ├── com.example.greeter/
│   └── com.example.app/
└── lib/       # modular JAR path
~~~

Lệnh compile dùng src và tạo output vào mods. Lệnh run dùng mods hoặc lib. Đưa nhầm src vào --module-path là lỗi phân loại path, ngay cả khi đường dẫn tồn tại.

## 3. Cấu trúc module source đúng

Với --module-source-path src, mỗi module nằm trong thư mục riêng có tên module. module-info.java ở thư mục gốc module; source của package nằm bên dưới theo package hierarchy.

~~~text
project/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greeter/
    │               └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Nội dung src/com.example.greeter/module-info.java:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Nội dung src/com.example.greeter/com/example/greeter/Greeter.java:

~~~java
package com.example.greeter;

public final class Greeter {
    private Greeter() { }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Nội dung src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Nội dung src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(
            Greeter.greet(args.length == 0 ? "module path" : args[0])
        );
    }
}
~~~

Tên com.example.greeter trong module-info.java phải trùng với tên module mà module khác khai báo trong requires. Tên package com.example.greeter là một khái niệm khác, dù ví dụ này cố ý đặt chúng giống nhau. Một module có thể có nhiều package, và module name không bắt buộc giống bất kỳ package nào.

## 4. Biên dịch nhiều module bằng javac

Mở terminal tại thư mục project và chạy:

~~~bash
javac --module-source-path src -d mods -m com.example.greeter,com.example.app
~~~

Ý nghĩa các tham số:

- --module-source-path src: nơi chứa source của các module.
- -d mods: thư mục output cho class file.
- -m hoặc --module: danh sách module cần biên dịch.

javac sẽ đọc các module-info.java, tìm module dependency và tạo module hierarchy trong mods. Với cấu trúc ví dụ, kết quả có mods/com.example.greeter và mods/com.example.app.

Chạy module ứng dụng:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Có thể dùng dạng rút gọn:

~~~bash
java -p mods -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello, module path!
~~~

Nếu module được đóng gói thành modular JAR và có main class được khai báo trong descriptor, có thể chạy chỉ với tên module. Ví dụ ở phần 8 dùng jar --main-class để khai báo entry point.

### 4.1. Lỗi khi bỏ module path

Nếu ứng dụng đã biên dịch cần một module nằm ngoài JDK, nhưng compiler hoặc JVM không nhận được vị trí module đó, việc resolve dependency sẽ thất bại. Ví dụ:

~~~text
error: module not found: com.example.greeter
~~~

hoặc ở runtime:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.greeter not found
~~~

Cách sửa:

1. Xác định module dependency đã được biên dịch ở đâu.
2. Kiểm tra thư mục đó có module-info.class ở đúng vị trí hoặc có modular JAR hợp lệ.
3. Đưa thư mục cha chứa các module hoặc thư mục JAR vào --module-path.
4. Đảm bảo tên module trong requires khớp với tên thực tế.
5. Đặt --module-path trước --module trong lệnh chạy để dễ đọc và tránh nhầm đối số chương trình.

Ví dụ nếu dependency nằm trong mods, lệnh chạy cần có --module-path mods. Nếu modular JAR nằm trong lib, hãy dùng --module-path lib.

## 5. Biên dịch nhiều module với source path khác nhau

--module-source-path có thể nhận một pattern cho cấu trúc module đồng nhất hoặc đường dẫn riêng cho từng module. Với số module nhỏ, dạng pattern đơn giản thường dễ bảo trì:

~~~bash
javac --module-source-path src -d mods -m com.example.greeter,com.example.app
~~~

Nếu source tree có thêm tầng src/main/java bên trong mỗi module:

~~~text
src/
├── com.example.greeter/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/greeter/Greeter.java
└── com.example.app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Có thể dùng pattern phù hợp với cấu trúc đó:

~~~bash
javac --module-source-path "*/src/main/java" -d mods -m com.example.greeter,com.example.app
~~~

Pattern phải khớp đúng vị trí của module directory và package hierarchy. Nếu source nằm trực tiếp dưới src/<module>/, không thêm /src/main/java vào pattern. Khi biên dịch nhiều module, các source file được chỉ định phải thuộc một trong các module source path đã khai báo.

Với một module duy nhất hoặc code không modular, --source-path có thể phù hợp hơn. Không cố dùng một --source-path package hierarchy cho nhiều named module; trường hợp đó cần --module-source-path.

## 6. Tên module, tên JAR và đường dẫn

Ba giá trị này thường bị nhầm:

- Module name: giá trị trong module-info.java, ví dụ com.example.greeter.
- JAR filename: tên file trên disk, ví dụ greeter-library-1.2.jar.
- Module path: vị trí chứa JAR, ví dụ lib/.

Với modular JAR, module name được lấy từ module descriptor trong JAR. Vì vậy, không cần đổi tên JAR để khớp với requires, nhưng phải đảm bảo descriptor đúng.

Với automatic module, tên có thể được lấy từ manifest:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

Nếu manifest không có Automatic-Module-Name, Java suy ra tên từ tên file JAR. Cách suy ra này có thể thay đổi khi tên file hoặc version suffix thay đổi. Với thư viện dùng lâu dài trên module path, ưu tiên một tên automatic module ổn định do nhà phát hành cung cấp hoặc chọn phiên bản đã có module descriptor.

Kiểm tra tên module trong JAR:

~~~bash
jar --describe-module --file lib/greeter-library-1.2.jar
~~~

Ví dụ output của modular JAR:

~~~text
com.example.app jar:file:///.../com.example.app.jar!/module-info.class
requires com.example.greeter
requires java.base mandated
contains com.example.app
main-class com.example.app.Main
~~~

Nếu tên hiển thị khác với requires trong ứng dụng, hãy sửa module descriptor hoặc chọn đúng JAR version.

## 7. Module tìm thấy nhưng package không truy cập được

Module path có thể đã đúng nhưng compile vẫn báo:

~~~text
error: package com.example.greeter is not visible
(package com.example.greeter is declared in module com.example.greeter,
which does not export it)
~~~

Đây là lỗi export, không phải lỗi vị trí module. Trong module cung cấp API, package phải được export:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

exports cho phép các module đọc module này truy cập public type trong package đó. Nếu module có requires đúng nhưng package không export, compiler vẫn từ chối import.

Phân biệt ba directive:

| Directive | Tác dụng |
|---|---|
| requires module.name | Module hiện tại đọc module dependency |
| exports package.name | Công khai public API của package cho module đọc nó |
| opens package.name | Cho phép deep reflection vào package ở runtime |

opens không thay thế exports cho import và compile thông thường. Nếu framework dùng reflection để truy cập private field/constructor, có thể cần opens cho package tương ứng. Nếu lỗi là InaccessibleObjectException, hãy xem lại quyền reflective access thay vì thay đổi module path.

Có thể giới hạn package chỉ cho một module cụ thể:

~~~java
module com.example.greeter {
    exports com.example.greeter.api to com.example.app;
}
~~~

Khi đó chỉ module com.example.app được truy cập package com.example.greeter.api thông qua module graph phù hợp.

## 8. Đóng gói và chạy modular JAR

Sau khi compile, có thể đóng gói từng module. Từ thư mục project:

~~~bash
mkdir lib
jar --create --file lib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file lib/com.example.app.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

Lệnh đầu đóng gói module thư viện. Lệnh thứ hai đóng gói ứng dụng và ghi main class vào module descriptor của modular JAR.

Kiểm tra descriptor:

~~~bash
jar --describe-module --file lib/com.example.app.jar
~~~

Chạy ứng dụng bằng thư mục chứa cả hai JAR:

~~~bash
java --module-path lib --module com.example.app
~~~

Output:

~~~text
Hello, module path!
~~~

Nếu JAR ứng dụng có main class nhưng thiếu JAR dependency trong lib, JVM vẫn không thể resolve module được yêu cầu. --module-path phải bao gồm mọi module dependency cần thiết, hoặc dependency phải có sẵn trong system modules của JDK.

Có thể dùng một JAR làm module path element trực tiếp, nhưng khi có nhiều dependency, dùng thư mục lib giúp quản lý và review dễ hơn.

## 9. Classpath và module path không thay thế nhau

Classpath đưa class và JAR vào unnamed module. Module path đưa named module hoặc automatic module vào module graph.

Ví dụ một thư viện không có module-info.class:

- Nếu đặt trên classpath, nó thuộc unnamed module.
- Nếu đặt trên module path, nó được xem như automatic module và có tên module suy ra hoặc lấy từ Automatic-Module-Name.

Nếu module-info.java có:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

thì dependency com.example.legacy phải được tìm như module trên module path. Đặt JAR đó chỉ trên classpath sẽ không thỏa mãn requires.

Nếu cần tích hợp code cũ nằm trên classpath, có thể tạm thời thêm readability bằng --add-reads:

~~~bash
javac --add-reads com.example.app=ALL-UNNAMED ...
~~~

~~~bash
java --add-reads com.example.app=ALL-UNNAMED ...
~~~

Đây là biện pháp tương thích cho tình huống đặc biệt. Với dependency dùng thường xuyên, nên đưa JAR lên module path để nó có module name ổn định, hoặc giữ ứng dụng trên classpath nếu dự án chưa cần JPMS.

Lưu ý khi dùng java -jar: JAR được chỉ định là nguồn user class duy nhất và các classpath setting khác bị bỏ qua. Nếu chạy ứng dụng modular, dùng --module-path và --module; nếu chạy ứng dụng non-modular, cấu hình manifest/classpath đúng theo cách đóng gói.

## 10. Hiểu module resolution: requires, readability và exports

Module system resolve dependency thành một readability graph. Khi module A khai báo requires B, A đọc B. Nếu B khai báo requires transitive C, module đọc B cũng có thể đọc C theo quy tắc transitive.

Ba bước cần kiểm tra khi lỗi dependency:

1. Module B có được tìm thấy trên module path hoặc system modules không?
2. Module A có khai báo requires B và dependency graph có resolve được không?
3. Package chứa API có được B export cho A không?

Một số directive liên quan:

~~~java
module com.example.api {
    requires java.logging;
    requires transitive com.example.model;
    requires static com.example.optional;
    exports com.example.api;
    opens com.example.api.internal;
    uses com.example.spi.Plugin;
}
~~~

- requires transitive: module dùng kiểu của dependency đó trong public API và muốn module client đọc dependency đó theo graph.
- requires static: dependency cần khi compile nhưng có thể không bắt buộc lúc runtime.
- uses: module dùng một service qua ServiceLoader.
- provides ... with ...: module cung cấp implementation cho service.
- opens: cho phép reflection sâu vào package theo chính sách của module.

Đừng thêm requires một cách ngẫu nhiên để hết lỗi. Đọc thông báo compiler để xác định module nào cần đọc module nào, sau đó sửa descriptor của module sở hữu dependency.

### 10.1. Khi nào dùng add-modules, add-reads và add-exports?

| Tùy chọn | Ý nghĩa | Dùng khi |
|---|---|---|
| --add-modules | Thêm module làm root để resolve | Service hoặc module phụ cần được resolve nhưng không phải dependency trực tiếp |
| --add-reads | Thêm readability edge | Tích hợp code cũ hoặc cấu hình test đặc biệt |
| --add-exports | Tạm export package cho module khác | Công cụ/test cần truy cập API chưa export |
| --add-opens | Mở package cho deep reflection | Framework cần truy cập thành viên private ở runtime |
| --patch-module | Thêm hoặc thay class trong module | Test/patch module theo cách có kiểm soát |

Ví dụ thêm root module:

~~~bash
java --add-modules java.sql --module-path mods --module com.example.app/com.example.app.Main
~~~

--add-modules không làm cho module path tự tìm thấy một JAR đang nằm sai thư mục. Nó cũng không thay thế requires khi source code của named module cần đọc dependency. Nếu module không có trên module path, phải sửa path trước.

Với --add-exports, cú pháp là module/package=target-module. Ví dụ:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Đây là cấu hình truy cập API nội bộ trong tình huống đặc biệt; API nội bộ có thể thay đổi giữa các JDK. Ưu tiên API public hoặc sửa module descriptor của module do dự án quản lý.

## 11. Path separator, khoảng trắng và khác biệt hệ điều hành

Module path có thể chứa nhiều path element. Ký tự phân cách element phụ thuộc hệ điều hành:

| Hệ điều hành | Separator | Ví dụ |
|---|---|---|
| Windows | ; | lib/a.jar;lib/b.jar |
| Linux/macOS | : | lib/a.jar:lib/b.jar |

Không nhầm path separator với dấu / hoặc \ dùng bên trong một filesystem path.

PowerShell:

~~~powershell
$modulePath = "lib\greeter.jar;lib\logging.jar"
java --module-path $modulePath --module com.example.app/com.example.app.Main
~~~

Linux/macOS:

~~~bash
MODULE_PATH="lib/greeter.jar:lib/logging.jar"
java --module-path "$MODULE_PATH" --module com.example.app/com.example.app.Main
~~~

Nếu đường dẫn có khoảng trắng, hãy quote toàn bộ giá trị:

~~~powershell
java --module-path "C:\Java Libraries\mods" --module com.example.app/com.example.app.Main
~~~

~~~bash
java --module-path "/opt/java libraries/mods" --module com.example.app/com.example.app.Main
~~~

Một lỗi hay gặp là copy nguyên dấu : từ lệnh Linux sang Windows, hoặc dùng ; trên Linux. Dấu phân cách sai có thể khiến JVM hiểu nhiều path element thành một đường dẫn duy nhất.

Windows thường không phân biệt chữ hoa/chữ thường trong tên file, trong khi Linux thường phân biệt. Hãy giữ nhất quán chính tả của module name, package name, thư mục và tên file source để tránh lệnh chạy được trên máy này nhưng thất bại trên CI.

## 12. Kiểm tra module path bằng công cụ JDK

Có thể chẩn đoán mà không cần sửa code trước.

### 12.1. Liệt kê module quan sát được

~~~bash
java --module-path mods --list-modules
~~~

Kiểm tra module của ứng dụng có xuất hiện trong danh sách không. Nếu không, xem lại module path, module descriptor và cấu trúc thư mục.

### 12.2. Xem descriptor của một module

~~~bash
java --module-path mods --describe-module com.example.greeter
~~~

Output của module ví dụ:

~~~text
com.example.greeter
exports com.example.greeter
requires java.base mandated
~~~

Nếu dùng modular JAR:

~~~bash
jar --describe-module --file lib/com.example.greeter.jar
~~~

Lệnh này giúp xác định tên module và package được export trong artifact thực tế.

### 12.3. Xác thực module graph

~~~bash
java --module-path mods --validate-modules
~~~

Lệnh này kiểm tra xung đột trong các module quan sát được trên module path. Khi thành công, lệnh không cần in nội dung. Nếu thất bại, đọc thông báo để tìm module trùng tên, split package hoặc descriptor không hợp lệ.

### 12.4. Xem thứ tự resolve dependency

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Output có thể chứa nhiều module của JDK do service binding. Tìm các dòng có tên module ứng dụng và dependency:

~~~text
root com.example.app ...
com.example.app requires com.example.greeter ...
~~~

### 12.5. Kiểm tra dependency bằng jdeps

~~~bash
jdeps --module-path lib --check com.example.app
~~~

jdeps hiển thị module descriptor và graph dependency được đề xuất. Dùng nó để phát hiện module dependency còn thiếu hoặc khai báo chưa phù hợp trong modular JAR.

Khi cần xem chi tiết compiler tìm file ở đâu:

~~~bash
javac -verbose --module-path lib ...
~~~

Thông tin verbose giúp xác định compiler đang đọc module/JAR nào. Đừng chỉ kiểm tra lệnh compile thành công; hãy kiểm tra runtime cũng dùng cùng module path và dependency version.

## 13. Các lỗi phổ biến và cách xử lý

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| module not found: com.example.greeter | Module không có trong module path hoặc sai module name | Kiểm tra thư mục/JAR, descriptor và --module-path |
| FindException: Module ... not found | Runtime không tìm thấy dependency | Thêm đúng module/JAR vào module path khi chạy |
| package ... is not visible | Module tìm thấy nhưng package không được export | Thêm exports trong module sở hữu package |
| module ... does not read ... | Thiếu dependency readability | Khai báo requires đúng module |
| package ... does not exist | Sai package/import hoặc nhầm classpath và module path | Kiểm tra package declaration, JAR contents và loại path |
| module not found dù JAR tồn tại | JAR không phải modular/automatic module hợp lệ hoặc tên suy ra khác | Dùng jar --describe-module, kiểm tra manifest và filename |
| InvalidModuleDescriptorException | module-info.class hoặc descriptor sai | Build lại JAR, kiểm tra module-info.java và cấu trúc archive |
| ResolutionException | Dependency graph xung đột, module trùng tên hoặc split package | Kiểm tra các bản JAR trên module path và package ownership |
| InaccessibleObjectException | Framework reflection vào package chưa mở | Thêm opens có giới hạn hoặc cấu hình --add-opens theo yêu cầu |
| Chạy được trên IDE nhưng lỗi ở terminal | IDE và terminal dùng JDK, module path hoặc dependency khác nhau | So sánh SDK, compiler options và runtime arguments |
| Chạy được trên Windows nhưng lỗi Linux | Khác chữ hoa/chữ thường hoặc path separator | Kiểm tra tên module/file và separator : |
| Build có module-info.java nhưng dependency không resolve | Build tool không đưa dependency vào module path hoặc thiếu inference | Xem compiler command và cấu hình modularity của build tool |

## 14. Quy trình xử lý khi gặp sai module path

Thực hiện lần lượt để xác định đúng lớp lỗi:

1. Chạy java --version và javac --version; đảm bảo compiler/runtime dùng JDK phù hợp.
2. Đọc tên module trong requires của module-info.java.
3. Chạy jar --describe-module --file path/to/dependency.jar hoặc java --module-path path --describe-module module.name.
4. Xác nhận dependency là modular JAR, automatic module hay exploded module.
5. Kiểm tra thư mục module path chứa đúng module hoặc modular JAR.
6. Dùng --module-source-path cho source của nhiều module và --module-path cho module đã biên dịch.
7. Kiểm tra requires và exports của từng module liên quan.
8. Chạy java --validate-modules và jdeps --module-path ... --check ....
9. Chạy ứng dụng với --show-module-resolution để xem module graph runtime.
10. So sánh lệnh compile/run ở IDE, Gradle/Maven và terminal; tìm dependency hoặc option khác nhau.

Khi build tool tạo command line thay cho bạn, bật log chi tiết. Với Gradle:

~~~bash
./gradlew compileJava --info
~~~

Với Maven:

~~~bash
mvn -X -DskipTests compile
~~~

Tìm --module-path, --module-source-path, --class-path và các dependency JAR trong log. Kiểm tra build tool có đang dùng một bản JAR khác với IDE hay không. Nếu module path bị truyền qua environment variable như JDK_JAVA_OPTIONS, kiểm tra cả biến môi trường đó vì launcher sẽ thêm các option của biến này vào command line.

## 15. Checklist trước khi kết luận đã sửa xong

- [ ] Đã xác nhận JDK dùng để compile và runtime.
- [ ] Đã xác nhận module name trong module-info.java.
- [ ] module-info.java nằm ở root của từng module source.
- [ ] Source tree khớp với --module-source-path.
- [ ] Module output có module-info.class ở root của từng module.
- [ ] Module path trỏ đến thư mục chứa module hoặc modular JAR.
- [ ] requires khai báo đúng dependency.
- [ ] Package cần truy cập đã được exports.
- [ ] Đã phân biệt --module-path, --module-source-path và --class-path.
- [ ] Đã kiểm tra path separator và dấu nháy cho đường dẫn có khoảng trắng.
- [ ] Không có module trùng tên hoặc split package ngoài ý muốn.
- [ ] java --validate-modules chạy thành công.
- [ ] jdeps --check không phát hiện vấn đề dependency chưa xử lý.
- [ ] Ứng dụng chạy được từ terminal/CI bằng module path dự kiến.

## 16. Ghi nhớ

--module-path xác định nơi Java tìm module đã biên dịch; --module-source-path xác định nơi javac tìm source của nhiều module; --class-path phục vụ code trên classpath và unnamed module. Khi biên dịch nhiều module, hãy đặt source theo module hierarchy, dùng --module-source-path, rồi ghi output vào một thư mục module hierarchy.

Một module dependency chỉ hoạt động khi module được tìm thấy, graph có requires phù hợp và package API được export. Hãy dùng jar --describe-module, java --describe-module, java --validate-modules, --show-module-resolution và jdeps --check để xác định lỗi nằm ở path, descriptor hay quyền truy cập package. Sau khi sửa, kiểm tra cả compile lẫn runtime trên cùng dependency set.

Tài liệu tham khảo:

- [The javac Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [The java Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [java.lang.module — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html)
- [ModuleDescriptor — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [The jar Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [The jdeps Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)