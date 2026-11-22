# Chạy mô-đun bằng java --module hoặc -m

## Mục tiêu

Sau khi biên dịch một ứng dụng modular, bạn cần khởi chạy đúng mô-đun chính, để Java tìm được các dependency trên module path và gọi đúng lớp chứa phương thức main. Java launcher cung cấp hai cách viết cho cùng một tùy chọn:

- **-m** là dạng ngắn.
- **--module** là dạng đầy đủ.

Cả hai đều chỉ định mô-đun cần chạy. Bạn có thể ghi rõ lớp main sau dấu gạch chéo, hoặc để launcher lấy main class đã được khai báo trong metadata của modular JAR.

Bài này tập trung vào cách chạy ứng dụng JPMS trên JDK hiện đại, với ví dụ tương thích Java 17 trở lên.

## 1. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
java [options] --module module[/mainclass] [application-args...]
~~~

Dạng viết ngắn tương đương:

~~~bash
java [options] -m module[/mainclass] [application-args...]
~~~

Trong đó:

- **java** là launcher khởi động môi trường chạy Java.
- **options** chứa các tùy chọn như module path, cấu hình runtime hoặc tùy chọn chẩn đoán.
- **module** là tên mô-đun cần khởi chạy, lấy từ module descriptor.
- **mainclass** là tên đầy đủ của lớp chứa phương thức main, được ngăn cách với tên mô-đun bằng dấu gạch chéo.
- **application-args** là các tham số được truyền vào phương thức main.

Ví dụ:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Lệnh trên yêu cầu launcher tìm mô-đun com.acme.app trong module path mods, sau đó gọi lớp com.acme.app.Main.

Có thể viết tương đương:

~~~bash
java -p mods --module com.acme.app/com.acme.app.Main
~~~

-p là dạng ngắn của --module-path. -m và --module là hai dạng viết của cùng một tùy chọn; chúng không phải hai chế độ chạy khác nhau.

## 2. Module path và cách launcher phân giải mô-đun

Một ứng dụng modular thường gồm nhiều mô-đun. Mô-đun chính có thể yêu cầu các mô-đun khác thông qua requires trong module-info.java.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Khi chạy:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

launcher tìm mô-đun gốc com.acme.app, đọc module descriptor, rồi phân giải các dependency mà mô-đun này yêu cầu. Các mô-đun phụ thuộc cũng phải có sẵn trên module path hoặc thuộc các mô-đun nền tảng mà runtime cung cấp.

### Module path chứa những gì?

Module path có thể trỏ đến:

- Thư mục chứa các thư mục mô-đun đã biên dịch (exploded modules), mỗi thư mục có module-info.class.
- Thư mục chứa các modular JAR.
- Các đầu vào mô-đun khác được module finder hỗ trợ, bao gồm automatic module trong trường hợp thư viện chưa có module descriptor.

Ví dụ:

~~~text
project/
├── src/
│   ├── com.acme.greeter/
│   └── com.acme.app/
├── out/
│   ├── com.acme.greeter/
│   │   ├── module-info.class
│   │   └── com/acme/greeter/api/Greeter.class
│   └── com.acme.app/
│       ├── module-info.class
│       └── com/acme/app/Main.class
└── mods/
    ├── com.acme.greeter.jar
    └── com.acme.app.jar
~~~

Với cấu trúc này:

- out là module path cho các mô-đun đã biên dịch dạng thư mục.
- mods là module path cho các modular JAR.

Tên mô-đun được xác định từ module descriptor hoặc quy tắc đặt tên automatic module. Không nên suy ra tên mô-đun chỉ từ tên file JAR.

### Module path khác classpath

| Tùy chọn | Vai trò |
|---|---|
| --module-path hoặc -p | Cung cấp các mô-đun để module resolver tìm và phân giải |
| --class-path hoặc -cp | Cung cấp lớp và JAR trên classpath, thuộc unnamed module trong ngữ cảnh JPMS |

Khi chạy một named module bằng -m, hãy đặt các mô-đun modular và dependency của chúng trên module path. Classpath vẫn hữu ích cho thư viện hoặc phần mã chưa chuyển sang JPMS, nhưng nó không thay thế quan hệ requires của một named module.

Nếu đặt modular JAR trên classpath, module descriptor không được dùng để phân giải như một named module. Vì vậy, một lệnh có -m cần module path phù hợp.

## 3. Chỉ định lớp main tường minh

Cách rõ ràng nhất khi chạy một mô-đun đã biên dịch là ghi cả tên mô-đun và tên lớp main:

~~~bash
java -p out -m com.acme.app/com.acme.app.Main
~~~

Phần trước dấu gạch chéo là tên mô-đun. Phần sau dấu gạch chéo là tên đầy đủ của lớp Java, bao gồm package.

Lớp main phải nằm trong mô-đun được chỉ định và có phương thức main phù hợp với launcher. Với ứng dụng Java thông thường, chữ ký được dùng phổ biến là:

~~~java
public static void main(String[] args)
~~~

Tên lớp phải được ghi đầy đủ. Ví dụ, nếu lớp khai báo package com.acme.app và tên lớp là Main, tên cần truyền là com.acme.app.Main, không chỉ là Main.

### Trường hợp module không có main class metadata

Với mô-đun dạng thư mục đã biên dịch hoặc modular JAR chưa khai báo main class, hãy chỉ định main class trực tiếp:

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Nếu bỏ phần /mainclass mà mô-đun không có main class metadata, launcher không biết lớp nào cần gọi và sẽ báo lỗi không tìm thấy main class của mô-đun.

## 4. Chạy mô-đun mà không ghi tên lớp main

Có thể chạy bằng tên mô-đun đơn thuần nếu modular JAR đã khai báo main class. Dùng tùy chọn --main-class của công cụ jar khi đóng gói:

~~~bash
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Tùy chọn này ghi main class của mô-đun vào metadata của modular JAR. Sau đó có thể chạy:

~~~bash
java --module-path mods --module com.acme.app
~~~

Hoặc dạng ngắn:

~~~bash
java -p mods -m com.acme.app
~~~

Launcher lấy main class từ metadata đã đóng gói và gọi phương thức main. Đây là cách thuận tiện để phân phối một ứng dụng modular có điểm bắt đầu đã được xác định.

Có thể kiểm tra metadata của JAR:

~~~bash
jar --describe-module --file mods/com.acme.app.jar
~~~

Thông tin mô-đun sẽ cho biết tên mô-đun, các dependency, package và main class nếu metadata đó được khai báo. Nếu JAR không có main class metadata, hãy dùng cú pháp có /mainclass.

## 5. Ví dụ hoàn chỉnh với hai mô-đun

Ví dụ gồm hai mô-đun:

- com.acme.greeter xuất package API chứa lớp Greeter.
- com.acme.app yêu cầu com.acme.greeter và gọi lớp Main.

Cấu trúc mã nguồn:

~~~text
src/
├── com.acme.greeter/
│   ├── module-info.java
│   └── com/acme/greeter/api/Greeter.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### Mô-đun cung cấp thư viện

Tệp src/com.acme.greeter/module-info.java:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
~~~

Tệp src/com.acme.greeter/com/acme/greeter/api/Greeter.java:

~~~java
package com.acme.greeter.api;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Mô-đun ứng dụng

Tệp src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Tệp src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.greeter.api.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

### Biên dịch các mô-đun

Mở terminal tại thư mục chứa src/ và chạy:

~~~bash
javac --release 17 -d out --module-source-path src -m com.acme.greeter,com.acme.app
~~~

Giải thích:

- --release 17 chọn mức ngôn ngữ, API Java SE và class file tương thích Java 17.
- -d out đặt các tệp .class vào thư mục out.
- --module-source-path src chỉ định nơi chứa source của các mô-đun.
- -m com.acme.greeter,com.acme.app yêu cầu javac biên dịch hai mô-đun được liệt kê.

Lưu ý: ở lệnh javac, -m/--module dùng để chọn mô-đun cần biên dịch. Ở lệnh java, -m/--module dùng để chọn mô-đun cần khởi chạy. Ý nghĩa phụ thuộc vào công cụ đang gọi.

Sau khi biên dịch, cấu trúc out có dạng:

~~~text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

### Chạy bằng tên mô-đun và lớp main

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main Ada
~~~

Kết quả:

~~~text
Hello, Ada!
~~~

Có thể dùng dạng ngắn:

~~~bash
java -p out -m com.acme.app/com.acme.app.Main Linh
~~~

Kết quả:

~~~text
Hello, Linh!
~~~

### Đóng gói thành modular JAR

Tạo thư mục mods và đóng gói từng mô-đun:

~~~bash
mkdir mods
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

JAR của greeter chứa module descriptor và package API. JAR của app chứa module descriptor, lớp Main và metadata main class.

Chạy ứng dụng bằng tên mô-đun:

~~~bash
java --module-path mods --module com.acme.app Minh
~~~

Kết quả:

~~~text
Hello, Minh!
~~~

Có thể dùng -m thay cho --module:

~~~bash
java -p mods -m com.acme.app
~~~

Khi không có tham số ứng dụng, chương trình dùng giá trị mặc định Java và in:

~~~text
Hello, Java!
~~~

Ví dụ đã được biên dịch với javac --release 17 và chạy trên JDK 24. Cả hai dạng -m và --module đều chạy đúng với lớp main chỉ định; modular JAR có main class metadata cũng chạy được khi chỉ ghi tên mô-đun.

## 6. Truyền tham số cho ứng dụng

Các tham số nằm sau phần chỉ định mô-đun và lớp main được truyền vào args của phương thức main:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main --name Ada --verbose
~~~

Trong trường hợp này, args nhận các chuỗi:

~~~text
args[0] = --name
args[1] = Ada
args[2] = --verbose
~~~

Launcher xử lý các tùy chọn của chính Java trước phần chỉ định mô-đun. Các đối số đứng sau module selector được chuyển cho ứng dụng. Vì vậy, đặt đúng vị trí dấu gạch chéo và phần tham số để tránh nhầm tùy chọn của JVM với đối số của chương trình.

Nếu ứng dụng cần nhận tham số cấu hình, hãy phân tích args trong main hoặc chuyển nó cho thư viện xử lý command line. java -m chỉ chọn điểm khởi chạy; nó không tự phân tích các tùy chọn nghiệp vụ của ứng dụng.

## 7. Các tùy chọn launcher hữu ích khi chạy mô-đun

| Tùy chọn | Công dụng |
|---|---|
| --module-path, -p | Chỉ định nơi tìm mô-đun |
| --module, -m | Chỉ định mô-đun cần chạy |
| --show-module-resolution | In thông tin các mô-đun được phân giải |
| --list-modules | Liệt kê các mô-đun mà runtime quan sát được |
| --describe-module | Hiển thị mô tả một mô-đun |
| --add-modules | Thêm các mô-đun gốc vào quá trình phân giải khi cần |
| --add-reads | Bổ sung quan hệ readability trong tình huống chuyển đổi hoặc tích hợp đặc biệt |
| --add-exports | Bổ sung quyền xuất package ở runtime cho mô-đun đích |

Ví dụ chẩn đoán quá trình phân giải:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Liệt kê mô-đun:

~~~bash
java --list-modules
~~~

Xem mô-đun cụ thể:

~~~bash
java --describe-module com.acme.app
~~~

Các tùy chọn --add-reads và --add-exports có thể hữu ích khi chuyển đổi hệ thống hoặc xử lý tương thích tạm thời. Trong ứng dụng modular ổn định, nên thể hiện dependency và API trong module descriptor để cấu hình runtime dễ hiểu và có thể tái lập.

## 8. Lỗi thường gặp khi dùng -m hoặc --module

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Error: Module ... not found | Module path không chứa mô-đun hoặc tên mô-đun sai | Kiểm tra -p/--module-path và tên trong module descriptor |
| Module ... does not have a main class | Không chỉ định /mainclass và modular JAR không khai báo main class | Ghi /com.example.Main hoặc đóng gói bằng jar --main-class |
| Main class không tìm thấy | Tên lớp sai, thiếu package hoặc lớp không nằm trong mô-đun | Kiểm tra package, tên lớp và nội dung đầu ra biên dịch |
| Package không đọc được | Thiếu requires hoặc dependency không được phân giải | Kiểm tra module-info.java và module path |
| Package không được truy cập | Mô-đun cung cấp chưa exports package cần dùng | Kiểm tra exports hoặc qualified exports |
| NoClassDefFoundError khi chạy | Dependency runtime thiếu hoặc cấu hình module path/classpath sai | Kiểm tra dependency đã được đóng gói và có mặt khi chạy |
| Chạy nhầm lớp main | Dùng sai module selector hoặc main class metadata | Chỉ định rõ module/mainclass hoặc kiểm tra jar --describe-module |

Khi chẩn đoán, hãy tách các câu hỏi: launcher có tìm thấy mô-đun không, mô-đun có được phân giải không, lớp main có tồn tại không, và ứng dụng có truy cập được dependency không. Mỗi bước tương ứng một phần cấu hình khác nhau.

## 9. Checklist trước khi triển khai

- Xác định đúng tên mô-đun từ module descriptor hoặc kết quả jar --describe-module.
- Đảm bảo mọi dependency được yêu cầu đều có trên module path.
- Chọn main class rõ ràng bằng /mainclass hoặc khai báo main class khi đóng gói modular JAR.
- Kiểm tra lệnh chạy trên đúng JDK/runtime mà sản phẩm hỗ trợ.
- Đặt tham số ứng dụng sau module selector để chúng được truyền vào args.
- Kiểm tra module resolution khi ứng dụng không khởi chạy như dự kiến.
- Dùng --release khi biên dịch để kiểm soát baseline Java SE; đồng thời xác minh dependency bên ngoài tương thích với baseline đó.

## Kết luận

java -m và java --module là hai cách viết tương đương để khởi chạy một named module. Module path cung cấp các mô-đun và dependency cho quá trình phân giải. Có thể chỉ định lớp main trực tiếp bằng module/mainclass; nếu modular JAR đã ghi main class metadata bằng jar --main-class, launcher có thể chạy chỉ với tên mô-đun.

Khi triển khai, hãy kiểm tra đồng thời module path, tên mô-đun, main class và dependency runtime. Nắm vững bốn yếu tố này giúp lệnh chạy modular rõ ràng, dễ chẩn đoán và phù hợp với cách tổ chức JPMS trong Java hiện đại.
