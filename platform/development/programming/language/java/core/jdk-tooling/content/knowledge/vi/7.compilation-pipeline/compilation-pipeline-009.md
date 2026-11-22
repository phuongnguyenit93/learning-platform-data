# Biên dịch nhiều module trong Java

Java Platform Module System (JPMS) cho phép chia ứng dụng thành các module có tên, khai báo phụ thuộc và kiểm soát package nào được công khai. Khi một dự án có nhiều module, compiler phải nhìn thấy mã nguồn hoặc artifact của từng module, giải quyết quan hệ phụ thuộc và tạo class file cho đúng module. Java launcher sau đó dùng module path để tìm và khởi chạy module chính.

Bài viết tập trung vào cách biên dịch nhiều module bằng JDK tools, đặc biệt là javac, jar và java. Ví dụ dùng Java 17 trở lên và hai module nhỏ để minh họa toàn bộ luồng từ source tree đến khi chạy ứng dụng.

## 1. Module và module descriptor

**Module** là đơn vị tổ chức mã trong JPMS. Một module có tên, chứa một hoặc nhiều package và khai báo những module mà nó phụ thuộc. Module thường được mô tả bằng tệp module-info.java ở thư mục gốc của source tree hoặc module artifact.

Ví dụ module descriptor:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Các chỉ thị thường gặp:

- **requires module.name** khai báo module hiện tại phụ thuộc vào một module khác.
- **exports package.name** công khai package để module khác có thể truy cập các kiểu public trong package đó.
- **opens package.name** cho phép truy cập phản chiếu sâu vào package trong các tình huống được JPMS kiểm soát; opens không thay thế exports cho truy cập mã nguồn thông thường.
- **requires transitive module.name** truyền yêu cầu đọc module phụ thuộc đến các module phụ thuộc vào module hiện tại.
- **requires static module.name** khai báo phụ thuộc cần khi biên dịch nhưng có thể không bắt buộc ở runtime.
- **uses service.Interface** khai báo module sử dụng một service thông qua ServiceLoader.
- **provides service.Interface with implementation.Type** khai báo implementation được cung cấp cho một service.

Tên module thường dùng quy ước tên ngược miền như com.acme.model hoặc org.example.app. Tên module là định danh trong module graph; nó không nhất thiết phải giống tên package, dù dùng cùng quy ước giúp dự án dễ đọc.

### Module graph

Các chỉ thị requires tạo quan hệ phụ thuộc giữa module. Khi biên dịch hoặc chạy, compiler/launcher cần giải quyết được module graph: module nào cần thiết, module nào đọc được module nào và package nào được phép truy cập.

Ví dụ:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.model
~~~

Trong sơ đồ này, com.acme.app đọc com.acme.model vì module descriptor của ứng dụng khai báo requires com.acme.model. Package mà ứng dụng cần dùng phải được module model exports.

## 2. Cấu trúc source tree cho nhiều module

Khi biên dịch nhiều module từ một cây mã nguồn, javac thường dùng cấu trúc thư mục mà mỗi module có một thư mục con cùng tên module. Mỗi thư mục module chứa module-info.java và các package source.

Ví dụ dự án có hai module:

~~~text
multi-module-demo/
└── src/
    ├── com.acme.model/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── model/
    │               └── Message.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Cần phân biệt ba loại tên:

- Tên module: com.acme.model hoặc com.acme.app.
- Tên package: com.acme.model hoặc com.acme.app.
- Tên lớp đầy đủ: com.acme.model.Message hoặc com.acme.app.Main.

Tên module và package trong ví dụ trùng phần chữ nhưng thuộc hai khái niệm khác nhau. Tệp module-info.java luôn nằm ở gốc source tree của module, không đặt bên trong package.

## 3. Chuẩn bị ví dụ hai module

Module thứ nhất cung cấp kiểu Message.

Tệp src/com.acme.model/module-info.java:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Tệp src/com.acme.model/com/acme/model/Message.java:

~~~java
package com.acme.model;

public record Message(String text) {
}
~~~

Module thứ hai là ứng dụng sử dụng Message.

Tệp src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.model;
}
~~~

Tệp src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.model.Message;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("Hello, modules!");
        System.out.println(message.text());
    }
}
~~~

Ở đây:

- com.acme.model exports package com.acme.model, vì vậy module khác có thể dùng kiểu public Message.
- com.acme.app requires com.acme.model, vì vậy compiler có thể giải quyết import và launcher có thể giải quyết module graph.
- Message là record, một tính năng chính thức từ Java 16, nên ví dụ tương thích với Java 17.
- Phương thức text() là accessor được compiler tạo cho thành phần record tên text.

## 4. Biên dịch nhiều module trong một lần

Với cấu trúc source tree ở trên, có thể biên dịch cả hai module bằng một lệnh javac:

~~~bash
javac --release 17 --module-source-path src -d out -m com.acme.model,com.acme.app
~~~

Ý nghĩa các tùy chọn:

- **--release 17** chọn API Java SE, mức ngôn ngữ và định dạng class file mục tiêu Java 17.
- **--module-source-path src** chỉ định gốc chứa các source tree của module.
- **-d out** chỉ định thư mục nhận class file đã biên dịch.
- **-m** là dạng viết tắt của --module; danh sách theo sau là các module cần biên dịch.
- **com.acme.model,com.acme.app** yêu cầu compiler biên dịch hai module được liệt kê.

Javac đọc module descriptor, giải quyết quan hệ requires và kiểm tra truy cập package. Nếu module app cần model, compiler phải tìm được module model trong các module source được chỉ định hoặc trên module path.

Sau khi biên dịch, cấu trúc đầu ra có dạng:

~~~text
out/
├── com.acme.model/
│   ├── module-info.class
│   └── com/
│       └── acme/
│           └── model/
│               └── Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/
        └── acme/
            └── app/
                └── Main.class
~~~

Đây là các **exploded modules**: mỗi module nằm trong một thư mục có module-info.class ở gốc. Thư mục out có thể được dùng trực tiếp làm module path.

### Chạy các module đã biên dịch

Khởi chạy lớp main của module ứng dụng:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Có thể dùng tùy chọn viết tắt:

~~~bash
java -p out -m com.acme.app/com.acme.app.Main
~~~

Trong đó:

- **--module-path out** hoặc **-p out** chỉ định nơi launcher tìm module.
- **-m** hoặc **--module** chọn module và lớp main theo dạng module.name/class.name.
- com.acme.app là module cần chạy.
- com.acme.app.Main là lớp chứa phương thức main.

Output chính xác:

~~~text
Hello, modules!
~~~

Nếu module descriptor của module ứng dụng có khai báo Main-Class trong manifest của modular JAR, có thể dùng cách khởi chạy module phù hợp với cấu hình JAR. Với exploded module, cú pháp module/class ở trên thể hiện rõ điểm vào.

## 5. Biên dịch từng module theo thứ tự phụ thuộc

Trong một số quy trình, mỗi module được biên dịch thành một bước riêng. Khi đó cần biên dịch dependency trước, sau đó đưa thư mục module đã biên dịch vào module path khi biên dịch module phụ thuộc.

Tạo thư mục đầu ra:

~~~bash
mkdir -p mods/com.acme.model mods/com.acme.app
~~~

Biên dịch module model:

~~~bash
javac --release 17 -d mods/com.acme.model \
  src/com.acme.model/module-info.java \
  src/com.acme.model/com/acme/model/Message.java
~~~

Biên dịch module app, dùng mods làm module path để compiler tìm thấy com.acme.model:

~~~bash
javac --release 17 --module-path mods -d mods/com.acme.app \
  src/com.acme.app/module-info.java \
  src/com.acme.app/com/acme/app/Main.java
~~~

Cấu trúc đầu ra lúc này là:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Chạy bằng module path mods:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, modules!
~~~

Phương pháp biên dịch từng module hữu ích khi các module có build lifecycle riêng hoặc dependency được tạo thành artifact ở bước trước. Điều kiện quan trọng là module path của compiler phải chứa module dependency đã biên dịch và tên module phải khớp với chỉ thị requires.

## 6. Đóng gói module thành JAR

Một module có thể được đóng gói thành modular JAR. Modular JAR chứa module-info.class ở gốc archive. Khi đặt JAR đó trên module path, Java có thể nhận diện tên module và các chỉ thị trong descriptor.

Sau khi đã biên dịch hai module vào mods, tạo thư mục chứa JAR:

~~~bash
mkdir -p mlib
~~~

Đóng gói module model:

~~~bash
jar --create --file mlib/com.acme.model.jar -C mods/com.acme.model .
~~~

Đóng gói module app và chỉ định lớp chính:

~~~bash
jar --create --file mlib/com.acme.app.jar \
  --main-class com.acme.app.Main \
  -C mods/com.acme.app .
~~~

Chạy ứng dụng từ module path chứa cả hai JAR:

~~~bash
java --module-path mlib -m com.acme.app
~~~

Launcher tìm com.acme.app, đọc requires com.acme.model và phân giải module model từ cùng module path. Vì JAR app có main class trong manifest, có thể chọn lớp chính bằng cấu hình đó. Để chỉ rõ lớp main mà không dựa vào thuộc tính Main-Class, dùng:

~~~bash
java --module-path mlib -m com.acme.app/com.acme.app.Main
~~~

Lệnh jar không biên dịch mã nguồn; nó đóng gói các tệp đã biên dịch. Hãy bảo đảm module-info.class được đưa vào JAR. Nếu thiếu descriptor, JAR có thể được xử lý như automatic module khi đặt trên module path, với quy tắc đặt tên và khả năng đóng gói khác.

## 7. Module path và classpath

**Module path** là nơi tìm các named module hoặc automatic module. **Classpath** là nơi tìm các lớp và tài nguyên theo cơ chế classpath truyền thống.

| Đặc điểm | Module path | Classpath |
|---|---|---|
| Đơn vị tổ chức | Module | Lớp và tài nguyên |
| Descriptor | Có thể có module-info.class | Không dùng module descriptor để xác định unnamed module |
| Phụ thuộc | Khai báo bằng requires | Thường được xác định qua classpath và cơ chế nạp lớp |
| Truy cập package | Chịu quy tắc exports/opens và module readability | Không có ranh giới named module theo cách đó |
| Tên module | Named hoặc automatic module | Các lớp thuộc unnamed module tương ứng với class loader |

### Named module, automatic module và unnamed module

- **Named module** có tên và module descriptor được khai báo rõ ràng.
- **Automatic module** là module được suy ra khi một JAR không có module descriptor được đặt trên module path. Tên có thể lấy từ thuộc tính Automatic-Module-Name trong manifest hoặc được suy ra từ tên JAR theo quy tắc nền tảng.
- **Unnamed module** chứa các lớp được nạp từ classpath. Nó không có tên module được khai báo trong module-info.java.

Named module không thể khai báo requires đến unnamed module. Vì vậy, nếu ứng dụng đã chuyển sang JPMS mà một thư viện chỉ có thể được đưa vào classpath truyền thống, cần xem xét cách đóng gói hoặc chuyển đổi thư viện phù hợp. Automatic module thường là bước tương thích trong quá trình chuyển đổi, nhưng không thay thế việc thiết kế module descriptor rõ ràng cho thư viện lâu dài.

### Đặt thư viện bên ngoài trên module path

Nếu thư viện là modular JAR, thêm thư mục chứa JAR vào module path:

~~~bash
javac --module-path "mods:lib" -d mods/com.acme.app \
  src/com.acme.app/module-info.java \
  src/com.acme.app/com/acme/app/Main.java
~~~

Ví dụ dùng dấu hai chấm làm dấu phân cách trên Linux/macOS. Trên Windows, module path nhiều mục thường dùng dấu chấm phẩy. Có thể dùng dấu ngoặc kép để shell giữ nguyên chuỗi đường dẫn theo cú pháp của môi trường.

## 8. Tùy chọn javac quan trọng khi biên dịch module

| Tùy chọn | Công dụng |
|---|---|
| --module-source-path | Chỉ định source tree chứa các module |
| -m hoặc --module | Chọn module cần biên dịch |
| -d | Chỉ định thư mục đầu ra |
| --module-path hoặc -p | Chỉ định nơi tìm các module phụ thuộc |
| --release | Chọn phiên bản nền tảng Java mục tiêu |
| --module-version | Ghi phiên bản module vào module descriptor đầu ra |
| --patch-module | Bổ sung hoặc thay thế nội dung của một module trong các tình huống kiểm thử/vá phù hợp |
| --add-reads | Bổ sung quan hệ đọc module trong tình huống đặc biệt |
| --add-exports | Mở một package cho module khác truy cập trong tình huống đặc biệt |

Các tùy chọn --patch-module, --add-reads và --add-exports thường phục vụ kiểm thử, công cụ hoặc tình huống tương thích đặc biệt. Không nên dùng chúng như cách sửa mặc định cho một module descriptor được thiết kế sai. Với ứng dụng bình thường, hãy sửa requires và exports đúng trong module-info.java.

Có thể bật cảnh báo module khi biên dịch:

~~~bash
javac -Xlint:module --release 17 --module-source-path src -d out \
  -m com.acme.model,com.acme.app
~~~

Cảnh báo giúp phát hiện một số vấn đề về module declaration và dependency. Không phải mọi cảnh báo đều là lỗi biên dịch; hãy đọc nội dung cảnh báo và đánh giá trong ngữ cảnh dự án.

## 9. Kiểm tra module và module resolution

Khi compiler hoặc launcher không tìm được module, hãy kiểm tra tên module, vị trí module-info.class và module path.

Một số lệnh hữu ích:

~~~bash
jar --describe-module --file mlib/com.acme.model.jar
~~~

Lệnh này hiển thị tên module và các khai báo liên quan của modular JAR.

~~~bash
java --show-module-resolution --module-path mlib -m com.acme.app
~~~

Tùy chọn --show-module-resolution in thông tin quá trình launcher phân giải module, hữu ích khi điều tra dependency nào được tìm thấy và module nào được đưa vào graph.

Có thể dùng jdeps để phân tích dependency của JAR:

~~~bash
jdeps --module-path mlib --print-module-deps mlib/com.acme.app.jar
~~~

Kết quả phụ thuộc vào các lớp và thư viện mà JAR tham chiếu. jdeps hỗ trợ phân tích phụ thuộc; nó không thay thế việc kiểm tra module descriptor và kiểm thử ứng dụng.

## 10. Lỗi thường gặp khi biên dịch nhiều module

### Module not found

Nguyên nhân thường gặp:

- Module dependency chưa được biên dịch hoặc chưa được đóng gói.
- Module path trỏ sai thư mục.
- Tên trong requires khác với tên module thực tế.
- Đưa nhầm thư mục source root hoặc thư mục chứa package vào module path thay vì thư mục gốc của module.

Cách xử lý: kiểm tra module-info.java, vị trí module-info.class hoặc modular JAR, rồi chỉ định module path đến đúng thư mục chứa các module.

### Package is not visible hoặc package is not exported

Module đã được tìm thấy nhưng package cần dùng chưa được exports. Thêm exports package phù hợp vào module descriptor của module cung cấp API. Nếu chỉ cần truy cập phản chiếu sâu, đánh giá opens theo đúng yêu cầu; opens không thay thế exports cho import Java thông thường.

### Package không thuộc module được khai báo

Cấu trúc thư mục package và tên package trong tệp Java có thể không khớp. Kiểm tra package declaration, vị trí source file và source tree của module.

### Split package

Một package cùng tên xuất hiện trong nhiều named module có thể gây lỗi hoặc xung đột khi module graph được giải quyết. Tránh chia cùng một package qua nhiều module; chuyển lớp về một module sở hữu package hoặc thiết kế lại ranh giới package.

### Cyclic dependence

Nếu module A requires B và module B requires A, module graph có chu trình không hợp lệ. Phá vòng phụ thuộc bằng cách tách API chung sang module thứ ba hoặc đảo lại hướng phụ thuộc.

### Invalid module name hoặc module descriptor không hợp lệ

Tên module không tuân theo quy tắc định danh, module-info.java đặt sai vị trí hoặc khai báo trùng lặp có thể làm compiler từ chối. Đặt module descriptor ở gốc source tree và dùng tên module ổn định, không dùng tên package để thay cho cấu trúc thư mục module.

### Main class not found hoặc module không khởi chạy

Kiểm tra module path có chứa module ứng dụng, lớp main có nằm trong package được khai báo đúng và cú pháp -m có chỉ đúng module/class hay không. Với modular JAR, kiểm tra manifest và module descriptor.

### Compiler và runtime khác phiên bản

Một module được biên dịch với API hoặc class file mới hơn có thể không chạy trên runtime cũ. Dùng --release để kiểm soát phiên bản mục tiêu và kiểm tra java --version cùng javac --version trong môi trường build.

## 11. Build tool và dự án nhiều module

Trong dự án lớn, việc gọi javac thủ công hữu ích để hiểu cơ chế nhưng build tool thường điều phối dependency graph, thứ tự build, test và đóng gói.

- **Maven multi-module:** parent project thường liệt kê các submodule. Mỗi submodule có thể tạo một JAR riêng; module-info.java khai báo quan hệ JPMS nếu dự án dùng named modules.
- **Gradle multi-project:** các project con được khai báo trong settings; task compile có thể phụ thuộc artifact của project khác. Toolchain chọn JDK và version mục tiêu.
- **IDE:** cần nhận diện mỗi source root/module, module descriptor và dependency. Cấu hình project SDK phải tương thích với release mục tiêu.

Cần phân biệt **multi-module của build tool** và **Java Platform Module System**. Maven/Gradle module là ranh giới project/build; JPMS module là đơn vị module graph ở thời điểm biên dịch và runtime. Một dự án Maven/Gradle nhiều module không tự động có module-info.java hoặc trở thành modular JAR.

Khi build nhiều module, nên giữ nhất quán phiên bản JDK, compiler release, module path và dependency version giữa máy phát triển và CI. Tránh để build tool và IDE sử dụng JDK khác nhau mà không có chủ đích.

## 12. Checklist biên dịch nhiều module

- Xác định rõ ranh giới module và tên module ổn định.
- Đặt module-info.java ở gốc source tree của từng module.
- Khai báo requires cho dependency và exports cho package API cần công khai.
- Giữ mỗi package thuộc về một named module phù hợp; tránh split package.
- Tổ chức source tree theo module name để dùng --module-source-path.
- Khi biên dịch cùng lúc, liệt kê các module cần build bằng -m.
- Khi biên dịch từng module, build dependency trước và đưa artifact vào --module-path.
- Dùng --release để thống nhất API và class file target.
- Kiểm tra output có module-info.class và package class file đúng vị trí.
- Đóng gói modular JAR bằng jar và giữ module descriptor ở gốc archive.
- Chạy bằng java --module-path và -m.
- Dùng jar --describe-module, --show-module-resolution và jdeps khi cần chẩn đoán.
- Kiểm thử ứng dụng trên đúng JDK runtime mục tiêu.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| JPMS | Java Platform Module System, hệ thống module của Java |
| Module descriptor | Tệp module-info.java mô tả tên và quan hệ module |
| requires | Khai báo phụ thuộc module |
| exports | Công khai package cho module khác |
| opens | Cho phép truy cập phản chiếu sâu vào package |
| Module graph | Đồ thị module và quan hệ phụ thuộc đã được phân giải |
| Module source path | Vị trí source tree của các module |
| Module path | Vị trí chứa exploded module hoặc modular JAR |
| Exploded module | Module đã biên dịch nằm trong một thư mục |
| Modular JAR | JAR chứa module descriptor ở gốc archive |
| Automatic module | Module được suy ra từ JAR không có descriptor khi đặt trên module path |
| Unnamed module | Module chứa lớp được nạp từ classpath |
| Split package | Một package bị chia giữa nhiều module |
| Module resolution | Quá trình xác định module cần thiết và quan hệ đọc |

Biên dịch nhiều module có ba việc phải làm đúng: **tổ chức source tree theo module, khai báo dependency và package visibility trong module descriptor, rồi cung cấp đúng module source path hoặc module path cho javac**. Khi các bước này nhất quán, Java launcher có thể phân giải module graph và khởi chạy ứng dụng từ exploded modules hoặc modular JAR.