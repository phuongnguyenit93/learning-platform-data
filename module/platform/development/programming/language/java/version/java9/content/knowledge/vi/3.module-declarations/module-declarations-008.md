# Kiểm tra nội dung mô-đun bằng lệnh jar --describe-module

JPMS (Java Platform Module System) dùng module descriptor để mô tả tên module, các module phụ thuộc và những package được công bố. Khi một thư viện được đóng gói thành JAR, descriptor đã biên dịch nằm trong file module-info.class. Công cụ jar của JDK có tùy chọn --describe-module để đọc thông tin module từ chính JAR đó.

Lệnh này hữu ích khi cần kiểm tra artifact đã build có đúng tên module, requires, exports, opens và các khai báo service như mong đợi hay không. Nó cũng cho biết tên automatic module khi JAR không có descriptor tường minh. Cần phân biệt kết quả kiểm tra JAR với metadata của Maven hoặc Gradle: hai nguồn thông tin phục vụ những mục đích khác nhau.

## 1. Lệnh jar --describe-module làm gì?

Cú pháp cơ bản:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Các tùy chọn:

- --describe-module yêu cầu jar hiển thị module descriptor hoặc tên automatic module suy ra từ JAR.
- --file chỉ định file JAR cần kiểm tra.
- Có thể viết ngắn gọn bằng -d và -f, nhưng dạng đầy đủ dễ đọc hơn trong script và tài liệu.

jar là công cụ đi kèm JDK. Hãy dùng jar từ cùng JDK với môi trường build hoặc runtime mà bạn đang kiểm tra. Có thể xác nhận phiên bản bằng:

~~~bash
java --version
jar --version
~~~

Lệnh --describe-module chỉ đọc cấu trúc module của artifact. Nó không sửa JAR, không build lại dự án và không đọc pom.xml hoặc build.gradle để suy ra module descriptor.

## 2. Kiểm tra named module có descriptor tường minh

Một modular JAR có file module-info.class ở thư mục gốc của archive. File này được biên dịch từ module-info.java và chứa các directive của JPMS.

Ví dụ, cấu trúc nguồn của thư viện:

~~~text
src/
└── com.example.greeter/
    ├── module-info.java
    └── com/example/greeter/Greeting.java
~~~

Nội dung module-info.java:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Lớp trong package được export:

~~~java
package com.example.greeter;

public final class Greeting {
    public static String message() {
        return "Hello from JPMS";
    }
}
~~~

Từ thư mục dự án, tạo thư mục đầu ra rồi biên dịch module:

~~~bash
mkdir -p out dist
javac -d out --module-source-path src -m com.example.greeter
~~~

Trên Windows PowerShell, có thể tạo hai thư mục bằng lệnh tương ứng:

~~~powershell
New-Item -ItemType Directory -Force out, dist
~~~

Đóng gói nội dung module đã biên dịch thành JAR:

~~~bash
jar --create --file dist/greeter.jar -C out/com.example.greeter .
~~~

Kiểm tra descriptor của artifact vừa tạo:

~~~bash
jar --describe-module --file dist/greeter.jar
~~~

Output minh họa:

~~~text
com.example.greeter jar:file:///.../dist/greeter.jar!/module-info.class
exports com.example.greeter
requires java.base mandated
~~~

Đường dẫn URI trên dòng đầu phụ thuộc hệ điều hành và vị trí lưu file. Các dòng còn lại cho biết:

- com.example.greeter là tên module lấy từ descriptor.
- exports com.example.greeter cho biết module công bố package này cho module đọc nó.
- requires java.base mandated thể hiện phụ thuộc vào module nền tảng java.base được hệ thống quy định ngầm định.

Để xác nhận descriptor thực sự nằm trong archive, có thể liệt kê nội dung JAR:

~~~bash
jar --list --file dist/greeter.jar
~~~

Trong danh sách cần thấy module-info.class ở thư mục gốc, bên cạnh các package và class đã biên dịch. Việc có module-info.class trong JAR là bằng chứng trực tiếp rằng artifact chứa descriptor tường minh.

## 3. Đọc các directive trong kết quả

Kết quả của --describe-module trình bày các directive mà module descriptor khai báo. Tùy nội dung module, bạn có thể thấy:

| Dòng trong kết quả | Ý nghĩa |
|---|---|
| requires module.name | Module khai báo phụ thuộc và cần đọc module được nêu tên |
| requires module.name transitive | Quan hệ đọc được truyền tiếp tới module phụ thuộc vào module hiện tại |
| requires static module.name | Phụ thuộc cần cho biên dịch nhưng có thể không bắt buộc có mặt khi chạy |
| exports package.name | Công bố package cho các module đọc module hiện tại |
| exports package.name to module.a | Chỉ công bố package cho những module được liệt kê |
| opens package.name | Mở package cho truy cập reflection lúc chạy |
| opens package.name to module.a | Chỉ mở package cho module được chỉ định |
| uses service.Type | Module khai báo sử dụng một service |
| provides service.Type with implementation.Type | Module khai báo implementation cho một service |

Một số từ khóa bổ sung có thể xuất hiện sau tên module hoặc directive. Ví dụ, mandated đánh dấu phụ thuộc do nền tảng hoặc compiler quy định; transitive và static tương ứng với các dạng requires có cùng tên trong module-info.java.

Không nên chỉ nhìn thấy tên module trong output rồi kết luận mọi class bên trong đều có thể truy cập từ module khác. Việc truy cập API thông thường còn phụ thuộc vào package được exports và quan hệ đọc. opens liên quan đến reflection lúc chạy, không thay thế exports.

## 4. Kiểm tra automatic module

Một JAR không có module-info.class có thể được nhận diện là automatic module khi được đặt trên module path. Tên module được chọn theo thứ tự:

1. Nếu manifest có thuộc tính Automatic-Module-Name, giá trị này là tên automatic module.
2. Nếu không có thuộc tính đó, tên module được suy ra từ tên file JAR theo quy tắc đặt tên automatic module.

Ví dụ một JAR thư viện có manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

Giả sử JAR chứa class trong package com.example.legacy nhưng không có module-info.class. Kiểm tra bằng:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.jar
~~~

Output minh họa:

~~~text
No module descriptor found. Derived automatic module.

com.example.legacy automatic
requires java.base mandated
contains com.example.legacy
~~~

Các dòng cho biết:

- Không có module descriptor tường minh trong JAR.
- JDK nhận diện một automatic module.
- com.example.legacy là tên module lấy từ Automatic-Module-Name trong manifest của ví dụ.
- contains com.example.legacy cho biết archive có package đó.

Nếu manifest không có Automatic-Module-Name, tên module được suy ra từ tên JAR. Tên suy ra có thể thay đổi khi tên file hoặc phiên bản artifact thay đổi. Với thư viện muốn hỗ trợ người dùng module path ổn định, tác giả nên công bố Automatic-Module-Name rõ ràng.

Automatic module tự động export và open các package của nó, đồng thời có khả năng đọc các module quan sát được trong cấu hình. Hành vi này hỗ trợ chuyển đổi từng bước, nhưng ranh giới đóng gói không chặt như named module tường minh.

**Lưu ý:** jar --describe-module đang mô tả module mà JAR có thể đại diện khi đặt trên module path. Chính lệnh này không quyết định cách ứng dụng nạp JAR. Nếu cùng JAR được đặt trên classpath, các lớp của nó thuộc unnamed module của class loader; JAR không tham gia đồ thị automatic module trong lần chạy đó.

## 5. Phân biệt module descriptor với metadata của công cụ build

Đây là hai lớp thông tin khác nhau, dù đều có thể xuất hiện trong cùng một dự án Java.

| Nguồn thông tin | Ví dụ | Vai trò | jar --describe-module có đọc không? |
|---|---|---|---|
| JPMS module descriptor | module-info.java và module-info.class | Khai báo tên module, requires, exports, opens, uses và provides | Có, khi descriptor được đóng gói trong JAR |
| JAR manifest | META-INF/MANIFEST.MF, Automatic-Module-Name, Main-Class, Implementation-Version | Metadata của archive; Automatic-Module-Name cung cấp tên cho automatic module khi không có descriptor tường minh | Có thể dùng Automatic-Module-Name để xác định tên automatic module; không coi toàn bộ manifest là module descriptor |
| Maven project metadata | pom.xml, groupId, artifactId, version, dependencies, plugin configuration | Mô tả tọa độ artifact, dependency và cách build dự án | Không |
| Gradle build metadata | build.gradle, build.gradle.kts, dependencies, plugins, toolchain | Cấu hình dependency, plugin, toolchain, task và quy trình build | Không |

### 5.1. Module descriptor

Module descriptor thuộc mô hình JPMS. Ví dụ:

~~~java
module com.example.app {
    requires com.example.greeter;
    exports com.example.app.api;
}
~~~

Khi biên dịch và đóng gói đúng cách, module-info.class được đặt ở gốc JAR. Đây là thông tin mà compiler và module system sử dụng để thiết lập quan hệ đọc và ranh giới package.

### 5.2. Maven hoặc Gradle metadata

Maven có thể khai báo dependency trong pom.xml:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>legacy-utils</artifactId>
    <version>2.4</version>
</dependency>
~~~

Gradle có thể khai báo dependency tương tự:

~~~kotlin
dependencies {
    implementation("org.example:legacy-utils:2.4")
}
~~~

Các khai báo này giúp công cụ build tìm và đưa thư viện vào classpath hoặc module path theo cấu hình dự án. Chúng không tự động thay thế module-info.java và không chứng minh rằng JAR đầu ra có descriptor JPMS.

Các khái niệm cần tách biệt:

- groupId, artifactId và version là tọa độ artifact trong hệ thống quản lý dependency; chúng không nhất thiết là tên module JPMS.
- dependencies trong Maven hoặc Gradle mô tả dependency của quá trình build và các scope tương ứng. requires trong module descriptor mô tả quan hệ đọc giữa các module JPMS.
- Compiler plugin, Java toolchain và cấu hình source/target hoặc release điều khiển cách build; chúng không tự tạo ra các directive exports hoặc opens nếu dự án không khai báo module descriptor.
- Automatic-Module-Name là thuộc tính trong manifest của JAR. Nó cung cấp tên ổn định cho automatic module, nhưng không khai báo đầy đủ requires, exports, opens, uses hoặc provides như module-info.class.

Vì vậy, một dự án có thể khai báo đầy đủ dependency trong pom.xml hoặc build.gradle nhưng JAR tạo ra vẫn không có module-info.class. Khi đó, jar --describe-module sẽ báo không có descriptor và hiển thị automatic module nếu JAR có thể được đặt tên theo quy tắc tương ứng.

Ngược lại, một JAR có module-info.class vẫn không cho biết toàn bộ cấu hình build ban đầu, chẳng hạn dependency test, plugin Maven, Gradle task hay cách dependency được resolve trong từng môi trường.

## 6. Quy trình kiểm tra artifact sau khi build

Có thể dùng quy trình sau trong CI hoặc khi kiểm tra một thư viện nhận từ bên ngoài:

1. Xác định đúng JDK đang dùng bằng java --version và jar --version.
2. Chạy build của dự án để tạo artifact cuối cùng. Kiểm tra đúng file JAR mà ứng dụng sẽ phân phối hoặc triển khai.
3. Dùng jar --list --file path/to/library.jar để kiểm tra cấu trúc archive và tìm module-info.class ở gốc JAR.
4. Chạy jar --describe-module --file path/to/library.jar để đọc tên module và các directive.
5. Đối chiếu tên module, requires, exports, opens, uses và provides với module-info.java trong mã nguồn.
6. Kiểm tra manifest nếu JAR không có descriptor tường minh, đặc biệt là Automatic-Module-Name.
7. Đối chiếu dependency trong pom.xml hoặc build.gradle với dependency thực sự được công bố trong module descriptor. Xác định rõ khác biệt về scope và mục đích.
8. Nếu cần xác minh khả năng phân giải khi chạy, chạy ứng dụng trên module path với cấu hình runtime thực tế. --describe-module chỉ kiểm tra metadata của một JAR, không chứng minh toàn bộ đồ thị module của ứng dụng sẽ phân giải thành công.

Ví dụ kiểm tra một module trong thư mục dist:

~~~bash
jar --list --file dist/greeter.jar
jar --describe-module --file dist/greeter.jar
~~~

Khi đưa vào CI, có thể lưu output của lệnh thứ hai làm bằng chứng cho artifact đã phát hành. Nếu tên module hoặc directive thay đổi ngoài dự kiến, pipeline có thể cảnh báo để người duy trì xem xét trước khi phát hành.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Error: Unable to access jarfile | Sai đường dẫn, file chưa được build hoặc tên file không khớp | Kiểm tra thư mục làm việc và đường dẫn JAR |
| No module descriptor found. Derived automatic module. | JAR không có module-info.class | Xác định đây có phải automatic module mong muốn không; kiểm tra Automatic-Module-Name |
| Tên module hiển thị khác tên mong đợi | Tên được suy ra từ tên file hoặc manifest có Automatic-Module-Name khác | Kiểm tra manifest và tên JAR; dùng tên module được báo trong output khi cấu hình requires |
| pom.xml có dependency nhưng output không có requires tương ứng | Dependency build và dependency JPMS là hai khai báo khác nhau | Kiểm tra module-info.java và cách build đặt dependency trên module path |
| Dự án có module-info.java nhưng JAR không có module-info.class | Build chưa biên dịch hoặc chưa đóng gói descriptor vào artifact cuối | Kiểm tra source set, cấu hình compiler và nội dung JAR đầu ra |
| Lệnh chạy được nhưng ứng dụng không phân giải được module | Kiểm tra một JAR riêng lẻ không đảm bảo các dependency còn lại có mặt hoặc đúng phiên bản | Kiểm tra module path và chạy ứng dụng với cấu hình runtime thực tế |

Không nên xem thông báo No module descriptor found là lỗi trong mọi trường hợp. Với thư viện cũ chưa modular hóa, automatic module có thể là trạng thái dự kiến. Điều cần xác định là tên module, package được cung cấp và cách ứng dụng thực sự nạp JAR.

## 8. Checklist khi đọc kết quả

- [ ] Đúng JAR được build hoặc phát hành đang được kiểm tra.
- [ ] Phiên bản JDK và công cụ jar đã được xác nhận.
- [ ] Đã xác định JAR có module-info.class hay là automatic module.
- [ ] Tên module khớp với tên được dùng trong requires.
- [ ] Các directive requires, exports, opens, uses và provides phù hợp với thiết kế.
- [ ] Nếu là automatic module, đã kiểm tra Automatic-Module-Name hoặc tên được suy ra từ file.
- [ ] Không nhầm module descriptor với pom.xml, build.gradle hoặc tọa độ artifact.
- [ ] Đã kiểm tra riêng cấu hình runtime khi cần xác minh toàn bộ đồ thị module.

## 9. Tài liệu tham khảo

- [Oracle JDK 26 — jar command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): cú pháp và các tùy chọn của công cụ jar, gồm --describe-module.
- [Oracle JDK 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): cấu trúc JAR, manifest và các mục trong archive.
- [Dev.java — Organizing Code into Modules](https://dev.java/learn/organizing/modules/): cách tổ chức module và sử dụng JPMS.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc metadata và dependency của Maven.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): cấu hình build Java trong Gradle.
