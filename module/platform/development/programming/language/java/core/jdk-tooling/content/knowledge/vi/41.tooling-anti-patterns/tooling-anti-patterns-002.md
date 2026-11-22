# Trộn classpath và module path trong Java: ranh giới và cách tích hợp an toàn

Java có hai cơ chế tìm và tổ chức code bên ngoài JDK: **classpath** và **module path**. Chúng có thể cùng xuất hiện trong một lệnh build hoặc lệnh chạy, nhưng mỗi cơ chế tạo ra một mô hình truy cập khác nhau.

Classpath gom class và JAR vào **unnamed module** của class loader. Module path tìm các named module, đọc module descriptor, giải quyết dependency graph và áp dụng quy tắc exports/opens. Một ứng dụng có thể phối hợp cả hai cơ chế trong giai đoạn chuyển đổi, nhưng cần biết code nào thuộc module nào và module nào được phép đọc module nào.

Anti-pattern cần tránh là trộn đường dẫn một cách tùy tiện: đưa cùng thư viện vào cả hai nơi, đặt JAR legacy trên classpath rồi khai báo requires như thể nó là named module, hoặc thêm nhiều cờ --add-reads/--add-opens để che giấu module graph chưa đúng. Bài này giải thích khác biệt, các kiểu tích hợp được hỗ trợ, ví dụ chạy được trên Java 17+, và quy trình chuyển đổi an toàn.

## 1. Classpath và module path giải quyết hai vấn đề khác nhau

### Classpath

Classpath là danh sách thư mục và JAR chứa class/resource. Code được tải từ classpath thuộc unnamed module của class loader tương ứng.

Ví dụ:

~~~bash
javac --release 17 -d out src/com/acme/app/Main.java
java --class-path out com.acme.app.Main
~~~

Các cách viết tương đương của classpath option:

~~~text
-cp
-classpath
--class-path
~~~

Một ứng dụng legacy có thể dùng nhiều JAR:

~~~bash
java --class-path "app.jar;lib/*" com.acme.app.Main
~~~

Trên Windows, dấu chấm phẩy phân cách các thành phần classpath. Trên Linux/macOS, dùng dấu hai chấm:

~~~bash
java --class-path "app.jar:lib/*" com.acme.app.Main
~~~

Classpath không yêu cầu mỗi JAR có module descriptor. Nếu JAR có module-info.class mà được đặt trên classpath, descriptor đó bị bỏ qua; các class của JAR được xem là code trong unnamed module.

### Module path

Module path chứa các module để Java compiler hoặc runtime giải quyết. Một module có thể là:

- Explicit module: JAR có module-info.class hoặc exploded module có module-info.class.
- Automatic module: JAR không có module descriptor nhưng được đặt trên module path.

Ví dụ:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Các cách viết tương đương:

~~~text
-p
--module-path
~~~

Module path có module graph. Mỗi named module khai báo dependency bằng requires và package công khai bằng exports. Runtime kiểm tra readability và package access khi resolve module configuration.

### So sánh nhanh

| Đặc điểm | Classpath | Module path |
|---|---|---|
| Đơn vị tổ chức | Class/JAR | Module |
| Module membership | Unnamed module | Explicit hoặc automatic named module |
| module-info.class | Bị bỏ qua | Được dùng nếu là explicit module |
| Dependency | Danh sách đường dẫn | Module graph |
| Package access | Không có exports của JPMS | Tuân theo exports/opens |
| Encapsulation | Lỏng hơn | Strong encapsulation với explicit modules |
| Module name | Không cần | Cần tên explicit hoặc automatic |
| Phù hợp | Ứng dụng legacy, thư viện chưa modular | Ứng dụng và thư viện JPMS |

Classpath không phải một phiên bản khác của module path. Đưa JAR từ classpath sang module path có thể làm thay đổi module membership, readability, reflection và cách service provider được phát hiện.

## 2. Unnamed module, explicit module và automatic module

### Unnamed module

Code trên classpath thuộc unnamed module. Unnamed module đọc tất cả observable modules và export/open các package của chính nó. Tuy vậy, named module không thể khai báo requires tới unnamed module bằng module-info.java.

Điểm bất đối xứng này giải thích vì sao một ứng dụng classpath có thể dùng API public từ named module đã được resolve, trong khi một named module không thể tự nhiên import thư viện chỉ nằm trên classpath.

Mỗi class loader có thể có unnamed module riêng. Với ứng dụng thông thường, các JAR trên application classpath thuộc unnamed module của application class loader.

### Explicit module

Explicit module có module-info.java:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

Một module consumer khai báo:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Consumer chỉ đọc được API public thuộc package được export bởi module greeter.

### Automatic module

JAR legacy không có module-info.class khi đặt trên module path sẽ trở thành automatic module.

Tên module được lấy từ thuộc tính Automatic-Module-Name trong manifest nếu có. Nếu không, Java suy ra tên từ tên file JAR. Vì tên suy ra có thể thay đổi khi đổi tên file hoặc version suffix, thư viện nên cung cấp Automatic-Module-Name ổn định trong manifest.

Ví dụ manifest của thư viện legacy:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Tạo JAR:

~~~bash
jar --create --file mods/legacy-lib.jar --manifest legacy.mf -C legacy-classes .
~~~

Kiểm tra module name:

~~~bash
jar --describe-module --file mods/legacy-lib.jar
~~~

Kết quả đại diện:

~~~text
No module descriptor found. Derived automatic module.

com.acme.legacy automatic
requires java.base mandated
contains com.acme.legacy
~~~

Automatic module là cầu nối chuyển đổi, không có cùng mức encapsulation như explicit module. Khi được resolve, nó đọc các module khác và các package của nó được xem là exported/open rộng. Hãy thay automatic module bằng explicit module khi thư viện đã sẵn sàng.

## 3. Có thể dùng classpath và module path cùng lúc không?

Có. Java launcher và javac đều hỗ trợ khai báo hai đường dẫn trong cùng một lần chạy.

Ví dụ launcher:

~~~bash
java --module-path mods --add-modules com.acme.greeter --class-path app-classes com.acme.app.Main
~~~

Trong ví dụ này:

- com.acme.greeter được resolve từ module path.
- app-classes được tải từ classpath và thuộc unnamed module.
- Unnamed module có thể đọc package được export từ com.acme.greeter.
- --add-modules đưa com.acme.greeter vào tập module được resolve.

Điều quan trọng là hai đường dẫn không tự biến thành một đường dẫn chung. Mỗi thư viện vẫn thuộc module mà vị trí của nó xác định.

### Quy tắc readability theo chiều

| Code gọi | Dependency nằm ở | Kết quả |
|---|---|---|
| Classpath/unnamed module | Named module đã resolve và export API | Có thể đọc API public |
| Named module | Explicit module có trong module path | Dùng requires |
| Named module | Automatic module trên module path | Dùng requires theo automatic module name |
| Named module | JAR chỉ nằm trên classpath | Không đọc được theo mặc định |
| Classpath/unnamed module | JAR trên classpath | Dùng theo classpath bình thường |

Đừng suy luận rằng vì hai JAR xuất hiện trong cùng lệnh java nên chúng tự động đọc được nhau. Module graph vẫn áp dụng.

## 4. Kiểu tích hợp 1: ứng dụng classpath dùng named module

Đây là cách hữu ích khi ứng dụng legacy vẫn chạy trên classpath nhưng cần dùng một thư viện đã modular hóa.

Cấu trúc ví dụ:

~~~text
hybrid/
├── greeter-src/
│   └── com.acme.greeter/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
├── mods/
└── app-src/
    └── com/acme/app/Main.java
~~~

File greeter-src/com.acme.greeter/module-info.java:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

File Greeter.java:

~~~java
package com.acme.greeter;

public final class Greeter {
    public static String message() {
        return "Hello from named module";
    }
}
~~~

Biên dịch module:

~~~bash
javac --release 17 --module-source-path greeter-src -d mods -m com.acme.greeter
~~~

Kết quả là exploded module mods/com.acme.greeter. Có thể chạy trực tiếp từ module path; hoặc đóng gói thành JAR:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C mods/com.acme.greeter .
~~~

File app-src/com/acme/app/Main.java không có module-info.java:

~~~java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Biên dịch code classpath nhưng cho compiler biết module dependency:

~~~bash
javac --release 17 --module-path mods --add-modules com.acme.greeter -d app-classes app-src/com/acme/app/Main.java
~~~

Chạy:

~~~bash
java --module-path mods --add-modules com.acme.greeter --class-path app-classes com.acme.app.Main
~~~

Stdout chính xác:

~~~text
Hello from named module
~~~

Đây là cách phối hợp hợp lệ: ứng dụng vẫn thuộc unnamed module, còn greeter là named module. API package com.acme.greeter phải được export.

Nếu bỏ --add-modules, custom module trên module path có thể không được đưa vào module configuration cho classpath launcher. Khi classpath application cần một named module cụ thể, hãy resolve module đó bằng --add-modules.

## 5. Kiểu tích hợp 2: named module dùng thư viện legacy dưới dạng automatic module

Đây thường là bước chuyển đổi thuận tiện khi ứng dụng đã có module-info.java nhưng một dependency chưa phát hành explicit module descriptor.

Ví dụ thư viện legacy có class:

~~~java
package com.acme.legacy;

public final class LegacyGreeting {
    public String message() {
        return "Hello from legacy library";
    }
}
~~~

Biên dịch thư viện:

~~~bash
javac --release 17 -d legacy-classes src/com/acme/legacy/LegacyGreeting.java
~~~

Tạo manifest có Automatic-Module-Name:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Đóng gói vào module path:

~~~bash
jar --create --file mods/legacy-lib.jar --manifest legacy.mf -C legacy-classes .
~~~

Module app khai báo:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.legacy.LegacyGreeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new LegacyGreeting().message());
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 --module-path mods --module-source-path app-src -d out -m com.acme.app
~~~

Chạy trên Windows:

~~~powershell
java --module-path "mods;out" -m com.acme.app/com.acme.app.Main
~~~

Trên Linux/macOS:

~~~bash
java --module-path "mods:out" -m com.acme.app/com.acme.app.Main
~~~

Stdout chính xác:

~~~text
Hello from legacy library
~~~

Maven hoặc Gradle vẫn phải khai báo dependency để tải/build JAR. module-info.java mới là nơi khai báo quan hệ JPMS requires. Hai dependency graph cần nhất quán.

### Khi nào automatic module không phù hợp?

Tránh phụ thuộc vào automatic module nếu:

- JAR chứa split package với module khác.
- Module name suy ra từ filename không ổn định.
- Thư viện có nhiều dependency chưa được kiểm soát.
- Thư viện dựa vào package-private access giữa nhiều JAR.
- Framework cần reflection sâu nhưng module không có opens phù hợp.
- Bạn cần encapsulation rõ ràng hoặc runtime image nhỏ.

Ưu tiên thư viện có module-info.class và public API được export có chủ đích.

## 6. Kiểu tích hợp 3: named module tạm thời đọc classpath qua ALL-UNNAMED

Đôi khi một dependency không thể đưa lên module path ngay. Java hỗ trợ --add-reads để tạo readability edge tạm thời từ named module tới unnamed module.

Module descriptor vẫn là:

~~~java
module com.acme.app {
}
~~~

Main class dùng thư viện legacy trên classpath:

~~~java
package com.acme.app;

import com.acme.legacy.LegacyGreeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new LegacyGreeting().message());
    }
}
~~~

Biên dịch trên Java 17+:

~~~bash
javac --release 17 --class-path legacy.jar --add-reads com.acme.app=ALL-UNNAMED --module-source-path src -d out -m com.acme.app
~~~

Chạy:

~~~bash
java --module-path out --class-path legacy.jar --add-reads com.acme.app=ALL-UNNAMED -m com.acme.app/com.acme.app.Main
~~~

Stdout chính xác:

~~~text
Hello from ALL-UNNAMED
~~~

Phải cấp readability ở cả compile time và runtime. Chỉ thêm cờ lúc chạy không sửa được lỗi compile; chỉ thêm cờ lúc compile cũng không tạo readability ở runtime.

Đây là escape hatch cho migration hoặc framework legacy. Nó làm dependency graph kém tường minh và mở rộng khả năng đọc tới tất cả unnamed modules. Nếu có thể, hãy đưa JAR thành automatic module hoặc tạo explicit module descriptor.

## 7. Anti-pattern: đặt JAR trên classpath nhưng khai báo requires

Một lỗi thường gặp là đặt JAR legacy trong classpath rồi viết:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Lệnh compile sai:

~~~bash
javac --class-path legacy.jar --module-source-path src -d out -m com.acme.app
~~~

Lỗi đại diện:

~~~text
error: module not found: com.acme.legacy
module com.acme.app { requires com.acme.legacy; }
~~~

Lý do: requires chỉ tìm named module trong module graph. JAR trên classpath thuộc unnamed module nên không thể được tìm bằng module name com.acme.legacy.

Sửa theo một trong các hướng:

1. Đưa JAR lên module path để nó trở thành automatic module và giữ requires.
2. Dùng explicit module version của thư viện.
3. Trong giai đoạn chuyển tiếp, dùng --add-reads module=ALL-UNNAMED và giữ JAR trên classpath.
4. Giữ ứng dụng trên classpath cho tới khi dependency sẵn sàng modular hóa.

Không đổi tên JAR hoặc thêm module-info rỗng chỉ để làm lỗi biến mất. Descriptor phải phản ánh dependency và package boundary thật.

## 8. Anti-pattern: đặt cùng một JAR trên cả hai đường dẫn

Không thêm cùng một thư viện vào cả classpath và module path:

~~~bash
java --module-path "mods;lib/customer.jar" --class-path "lib/customer.jar;app.jar" ...
~~~

Một bản sao trên module path có thể được resolve thành named/automatic module; bản sao trên classpath thuộc unnamed module. Cùng một tên class khi được định nghĩa bởi các module hoặc class loader khác nhau có thể tạo hai kiểu runtime khác nhau.

Hậu quả có thể gồm:

- Class cast thất bại dù tên class giống nhau.
- Service provider được phát hiện hai lần hoặc không theo dự kiến.
- Version khác nhau được nạp tùy đường dẫn.
- Module graph và classpath graph không khớp.
- Khó truy vết class thực tế đang chạy.

Mỗi artifact nên có một vị trí runtime rõ ràng. Kiểm tra dependency tree và launch command để bảo đảm không có bản sao cùng thư viện ở cả hai đường dẫn.

## 9. Anti-pattern: chuyển mọi JAR lên module path mà không kiểm tra

JAR không có module-info.class có thể trở thành automatic module, nhưng không phải mọi thư viện legacy đều tương thích ngay.

Kiểm tra từng JAR:

~~~bash
jar --describe-module --file lib/example.jar
~~~

Nếu output nói automatic module, ghi lại tên module thực tế và các package chứa trong JAR.

Dùng jdeps:

~~~bash
jdeps --multi-release 17 --print-module-deps lib/example.jar
~~~

Kiểm tra module graph của ứng dụng:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Những lỗi cần tìm:

- Split package giữa nhiều module.
- Module name không ổn định.
- Dependency bị thiếu.
- Package nội bộ bị truy cập.
- Reflection vào package chưa mở.
- Service provider không được khai báo hoặc phát hiện.
- JAR cần classpath behavior đặc thù.

Không đưa cả thư mục lib lên module path nếu chưa biết nội dung của nó. Module path là tập hợp module; mỗi JAR được xem là một module, không phải một phần tử classpath vô danh.

## 10. Split package và duplicate class

### Split package

Split package xảy ra khi cùng một package được chia giữa nhiều named module.

Ví dụ:

~~~text
module com.acme.core
    contains com.acme.shared

module com.acme.plugin
    contains com.acme.shared
~~~

JPMS không cho phép một module configuration thông thường resolve hai named modules cùng chứa package đó. Runtime có thể báo package conflict hoặc split package.

Giải pháp:

- Đưa package về một module duy nhất.
- Tạo module API dùng chung.
- Chuyển implementation sang package riêng.
- Gộp thư viện nếu thiết kế cũ cố tình chia một package qua nhiều JAR.

Classpath không áp dụng cùng quy tắc split-package của named modules, nhưng duplicate class và package sealing vẫn có thể gây lỗi.

### Duplicate class trên classpath

Nếu hai JAR có cùng fully qualified class name, class loader có thể lấy bản đầu tiên theo thứ tự tìm kiếm classpath. Thay đổi thứ tự JAR có thể làm ứng dụng chạy code version khác.

Đừng dùng thứ tự classpath như cơ chế version selection. Loại bỏ duplicate dependency hoặc khóa một version duy nhất.

### Duplicate module name trên module path

Nếu hai module có cùng module name xuất hiện trong module path, resolution có thể thất bại hoặc một module không thể được xác định theo ý định của dự án. Giữ module name duy nhất và ổn định.

## 11. Anti-pattern: dùng add-reads, add-exports và add-opens thay cho thiết kế module

Ba cờ này giải quyết ba vấn đề khác nhau:

| Option | Vấn đề giải quyết | Ví dụ |
|---|---|---|
| --add-reads | Readability giữa module | com.acme.app đọc ALL-UNNAMED |
| --add-exports | Cho phép truy cập public types trong package chưa export | java.base/sun.nio.ch=ALL-UNNAMED |
| --add-opens | Cho phép deep reflection vào package ở runtime | java.base/java.lang=ALL-UNNAMED |
| --patch-module | Bổ sung/thay class hoặc resource trong module | Dùng cho test hoặc patch có kiểm soát |

Ví dụ:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED ...
~~~

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED ...
~~~

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

Không dùng các cờ trên như một tập tùy chọn thử-sai để làm chương trình chạy. Chúng làm thay đổi module graph hoặc ranh giới truy cập, nên cần ghi rõ lý do và phạm vi.

### exports và opens không giống nhau

- exports cho phép code module khác truy cập public types/public members trong package.
- opens cho phép reflective access sâu hơn ở runtime, kể cả non-public members theo cơ chế reflection.
- opens không thay thế requires.
- add-exports không tự cấp deep reflection.
- add-opens không làm public API trở thành dependency hợp lệ lúc compile.

Nếu framework cần reflection vào DTO của module app, ưu tiên:

~~~java
module com.acme.app {
    opens com.acme.app.dto to com.acme.json;
}
~~~

Nếu framework nằm trên classpath, target có thể là ALL-UNNAMED. Chỉ mở đúng package cần thiết.

## 12. Anti-pattern: nhầm module path với class loader

Module path và class loader liên quan nhưng không đồng nhất.

Module system quyết định module configuration, readability, exports và opens. Class loader chịu trách nhiệm định nghĩa/nạp class. Một module có thể được gắn với class loader; module layer có thể được tạo bằng API để xây dựng cấu hình runtime riêng.

Đừng giả định:

- Mỗi module luôn có một class loader riêng.
- Đổi JAR từ classpath sang module path sẽ tự tạo class loader mới theo ý muốn.
- Thêm JAR vào module path tự động sửa mọi xung đột class.
- Tất cả dependency trên module path đều được resolve nếu không có root module.
- Module path là classpath có thêm tên module.

Nếu ứng dụng plugin cần cách ly class loader, hãy thiết kế ModuleLayer/ClassLoader riêng thay vì trông chờ vào vị trí của JAR trong command line.

## 13. Classpath wildcard, environment và lệnh java -jar

### Không dựa vào thứ tự wildcard

Classpath wildcard như:

~~~bash
java -cp "lib/*" com.acme.app.Main
~~~

giúp nạp nhiều JAR trong thư mục lib, nhưng thứ tự mở rộng wildcard không được đảm bảo. Không đặt hai version của cùng dependency trong một thư mục wildcard và trông chờ một bản luôn được chọn trước.

### Hạn chế CLASSPATH environment variable

Biến môi trường CLASSPATH có thể làm build local và CI chạy khác nhau. Ưu tiên truyền classpath tường minh từ Maven, Gradle hoặc script khởi chạy được version control.

### Lưu ý java -jar

Khi dùng:

~~~bash
java -jar app.jar
~~~

JAR là nguồn chính của user classes và các tùy chọn classpath trên command line bị bỏ qua. Nếu cần dependency, hãy khai báo trong manifest Class-Path, dùng launcher script với -cp, hoặc dùng cách khởi chạy module phù hợp.

Đừng giả định lệnh java -jar app.jar -cp lib/* sẽ thêm dependency như mong muốn.

### Separator phụ thuộc hệ điều hành

| Hệ điều hành | Path separator |
|---|---|
| Windows | ; |
| Linux/macOS | : |

Trong PowerShell, bọc module path có dấu chấm phẩy trong dấu ngoặc kép vì dấu chấm phẩy là ký tự phân tách lệnh.

## 14. Reflection và ServiceLoader khi chuyển đường dẫn

### Reflection

Code chạy trên classpath có thể đã dựa vào quyền truy cập rộng hơn mà nó từng có. Khi dependency chuyển sang named module, framework reflection có thể gặp:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Hãy xác định module/package bị đóng và chọn một giải pháp:

1. Cập nhật framework để dùng public API hoặc module-aware access.
2. Thêm opens có phạm vi rõ ràng trong module descriptor.
3. Dùng --add-opens như giải pháp tương thích tạm thời.
4. Thiết kế lại API để tránh deep reflection nếu có thể.

### ServiceLoader

Trên classpath, service provider truyền thống được đăng ký bằng:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

Trên explicit module, service consumer và provider có thể khai báo:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

~~~java
module com.acme.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.json.JsonFormatter;
}
~~~

Khi chuyển provider từ classpath sang module path, kiểm tra lại service metadata. Một ứng dụng classpath có thể đọc provider module nếu module đã được resolve và service được cấu hình đúng. Ứng dụng modular nên khai báo uses/provides rõ ràng.

Nếu dùng jlink để tạo runtime image, xem xét --bind-services để liên kết các service provider cần thiết.

## 15. Cấu hình Maven và Gradle

Maven/Gradle quản lý dependency artifact. JPMS quản lý module readability và package access. Đây là hai lớp cấu hình khác nhau.

### Maven

POM dependency:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>legacy-lib</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

POM làm cho JAR có mặt trong build dependency graph. requires khai báo quan hệ JPMS. Nếu JAR không có module-info.class, module name có thể lấy từ Automatic-Module-Name trong manifest.

Khi dùng Maven Compiler Plugin, kiểm tra version plugin và cách plugin suy luận module path từ module-info.java. Đảm bảo test runtime, surefire/failsafe và application launcher dùng cùng mô hình dependency đã được xác nhận.

Chạy:

~~~bash
mvn clean verify
mvn dependency:tree
~~~

### Gradle

Với dự án modular:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}

dependencies {
    implementation files('libs/legacy-lib.jar')
}
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Gradle có thể suy luận module path cho Java compilation khi project modular. Tên automatic module cần ổn định; kiểm tra bằng jar --describe-module.

Với dự án classpath thuần không có module-info.java, dependency thường ở compileClasspath/runtimeClasspath và code thuộc unnamed module.

Kiểm tra dependency graph:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency legacy-lib --configuration runtimeClasspath
~~~

Không giả định khai báo implementation/api trong Gradle tự động tạo requires directive. Hãy duy trì module-info.java và build dependency cùng nhau.

## 16. Quy trình chuyển đổi từ classpath sang module path

Chuyển đổi theo từng bước để mỗi lỗi có thể truy vết.

1. **Ghi nhận trạng thái hiện tại:** lưu classpath, JDK version, build tool, dependency tree và test baseline.
2. **Kiểm kê JAR:** dùng jar --describe-module để nhận diện explicit/automatic module; dùng jdeps để phân tích dependency.
3. **Kiểm tra package:** tìm split package, duplicate class, reflective access và service descriptor.
4. **Chọn module đầu tiên:** ưu tiên thư viện nhỏ, API rõ ràng, ít dependency.
5. **Đưa dependency lên module path:** nếu chưa modular, dùng automatic module có tên ổn định.
6. **Tạo module-info.java:** khai báo requires và exports tối thiểu.
7. **Căn chỉnh compile và runtime:** compiler, test runner, IDE và launcher phải dùng cùng module graph.
8. **Kiểm tra service/reflection:** thêm uses/provides/opens phù hợp.
9. **Thay automatic module:** dùng phiên bản explicit module khi có thể.
10. **Gỡ workaround:** loại add-reads/add-exports/add-opens không còn cần.
11. **Chạy integration tests:** kiểm tra trên đúng JDK và môi trường phát hành.
12. **Ghi lại module graph:** tài liệu hóa module names và API boundaries.

Không cần modular hóa toàn bộ ứng dụng trong một lần. Một hệ thống có thể tiếp tục giữ một số ứng dụng trên classpath trong khi các thư viện lõi đã trở thành explicit modules.

## 17. Chẩn đoán module graph và class loading

Các lệnh hữu ích:

### Kiểm tra descriptor

~~~bash
jar --describe-module --file lib/example.jar
~~~

### Kiểm tra module resolution

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

### Kiểm tra module path

~~~bash
java --validate-modules --module-path mods
~~~

### Liệt kê module

~~~bash
java --list-modules
~~~

### Phân tích dependency

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

~~~bash
jdeps --module-path mods --print-module-deps app.jar
~~~

### Xem nguồn class được nạp

~~~bash
java -Xlog:class+load=info --class-path "app.jar;lib/*" com.acme.app.Main
~~~

Trên Linux/macOS thay separator bằng dấu hai chấm. Log class loading giúp phát hiện class đang đến từ JAR hoặc directory nào khi có duplicate dependency.

### Xem lệnh compiler thực tế

Với Maven, dùng mvn -X để kiểm tra compiler arguments. Với Gradle, dùng --info hoặc --debug và kiểm tra task compileJava/compileTestJava. So sánh module path của compile, test và run; một dự án có thể compile thành công nhưng runtime lại thiếu module.

## 18. Troubleshooting

### error: module not found

Module cần requires nhưng JAR chỉ nằm trên classpath. Đưa JAR lên module path với module name đúng, hoặc dùng --add-reads như giải pháp tạm thời.

### package is not visible

Module consumer chưa requires module provider hoặc provider chưa exports package. Kiểm tra cả hai module descriptor.

### module does not read unnamed module

Named module đang import code chỉ có trên classpath. Đưa dependency thành automatic/explicit module hoặc cấp --add-reads module=ALL-UNNAMED tạm thời.

### package is declared in module but module does not export it

Package không được export. Chỉ export API dự định công khai; không export toàn bộ package để che lỗi thiết kế.

### split package hoặc package conflict

Hai named modules cùng chứa một package. Tách package, gộp ownership hoặc tạo module API chung.

### NoClassDefFoundError

JAR có thể thiếu khỏi runtime path, nằm sai đường dẫn, hoặc chỉ có mặt lúc compile. So sánh compile classpath/module path với runtime path.

### ClassCastException dù class name giống nhau

Có thể class được định nghĩa từ hai JAR hoặc hai class loader khác nhau. Xác định nguồn class bằng -Xlog:class+load=info và loại bỏ duplicate artifact.

### InaccessibleObjectException

Framework reflection truy cập package không được mở. Ưu tiên cập nhật framework hoặc khai báo opens có phạm vi. --add-opens chỉ nên là compatibility workaround có ghi nhận.

### ServiceConfigurationError hoặc provider không được tìm thấy

Kiểm tra META-INF/services, uses/provides, module resolution và --bind-services khi dùng jlink.

### Ứng dụng chạy trong IDE nhưng lỗi ở terminal/CI

IDE có thể dùng classpath/module path khác với build tool. Xuất hoặc xem launch configuration, kiểm tra JDK, working directory, dependency và các cờ module.

### Hai môi trường chọn dependency version khác nhau

Kiểm tra wildcard classpath, transitive dependencies, dependency locking, repository metadata và thứ tự đường dẫn. Pin dependency version và loại bỏ JAR trùng.

## 19. Checklist trước khi trộn classpath và module path

- Biết chính xác mỗi JAR nằm trên classpath hay module path.
- Không đặt cùng artifact trên cả hai đường dẫn.
- Kiểm tra module name bằng jar --describe-module.
- Dùng Automatic-Module-Name ổn định cho thư viện legacy.
- Named module chỉ requires module có thể resolve trên module path.
- Classpath application resolve named module bằng --add-modules khi cần.
- Không dựa vào module path để tự động biến mọi dependency thành readable.
- Kiểm tra exports/opens trước khi chạy framework reflection.
- Kiểm tra split package và duplicate class.
- Kiểm tra META-INF/services và uses/provides.
- Compile, test và run dùng module graph nhất quán.
- Hạn chế --add-reads/--add-exports/--add-opens trong production.
- Không dùng wildcard classpath khi có duplicate version.
- Kiểm tra Maven/Gradle dependency graph cùng JPMS graph.
- Chạy smoke test trên đúng JDK/runtime sẽ phát hành.
- Ghi lại workaround và kế hoạch loại bỏ chúng.

## 20. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Classpath | Danh sách thư mục/JAR cung cấp class cho unnamed module |
| Module path | Danh sách named modules để module system resolve |
| Unnamed module | Module chứa code không có module descriptor, thường từ classpath |
| Explicit module | Module có module-info.class |
| Automatic module | JAR không có descriptor được xem là module khi đặt trên module path |
| Module graph | Đồ thị dependency/readability giữa các module |
| Readability | Quan hệ một module được phép đọc module khác |
| exports | Công khai package cho module khác |
| opens | Cho phép reflective access sâu vào package |
| ALL-UNNAMED | Đích chỉ tất cả unnamed modules |
| --add-reads | Bổ sung readability edge lúc chạy/compile |
| --add-exports | Bổ sung qualified export |
| --add-opens | Mở package cho reflection |
| Split package | Một package bị chia giữa nhiều named modules |
| Duplicate class | Cùng fully qualified class name xuất hiện ở nhiều nơi |
| Automatic-Module-Name | Manifest attribute đặt module name ổn định cho JAR legacy |
| ModuleLayer | Runtime layer chứa module configuration |
| ServiceLoader | Cơ chế tìm service provider |
| jdeps | Công cụ phân tích dependency của Java |
| jlink | Công cụ tạo custom runtime image |

Classpath và module path có thể phối hợp trong một hệ thống Java, nhưng mỗi đường dẫn tạo ra một module membership và quy tắc truy cập riêng. Hãy chọn một mô hình rõ ràng cho từng dependency, dùng automatic module như cầu nối có kiểm soát, khai báo requires/exports/opens đúng mục đích và chỉ dùng các cờ add-reads/add-opens khi cần migration. Khi compile, test và runtime cùng dùng một module graph được hiểu rõ, ứng dụng sẽ dễ chẩn đoán, đóng gói và bảo trì hơn.

## Tài liệu tham khảo

- Oracle JDK 24 — The java Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — The javac Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle Java SE 24 — java.lang.module package: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html
- Oracle Java SE 24 — ModuleDescriptor and automatic modules: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Oracle Java SE 24 — ModuleFinder: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html
- Oracle JDK 24 — jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- OpenJDK — JEP 261: Module System: https://openjdk.org/jeps/261
- Gradle — Building Java Modules: https://docs.gradle.org/current/userguide/java_library_plugin.html