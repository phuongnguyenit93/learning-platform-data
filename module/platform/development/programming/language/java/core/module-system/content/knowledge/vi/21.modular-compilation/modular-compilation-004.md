# javac --module và compile một module

Từ Java 9, Java Platform Module System (JPMS) cho phép biên dịch và chạy ứng dụng theo từng module có tên. Khi compile một module, compiler cần biết ba điều: **source của module nằm ở đâu**, **module nào cần được biên dịch**, và **các module dependency đã biên dịch nằm ở đâu**.

Lệnh `javac --module` (viết tắt là `javac -m`) chọn module cần compile. Nó thường đi cùng `--module-source-path` để tìm source của các module và `--module-path` để tìm dependency đã biên dịch. Nắm rõ ba tùy chọn này giúp bạn compile riêng một module mà không phải đưa toàn bộ dự án vào classpath.

Các ví dụ dưới đây dùng JDK 21 và một dự án gồm hai module: `com.acme.api` và `com.acme.app`.

## 1. Cấu trúc source của dự án modular

Mỗi module có một file `module-info.java` ở thư mục gốc của module. Các package Java nằm bên dưới thư mục đó.

Ví dụ:

~~~text
project/
├── src/
│   ├── com.acme.api/
│   │   ├── module-info.java
│   │   └── com/acme/api/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── out/
~~~

Tên thư mục module ở đây là `com.acme.api` và `com.acme.app`; chúng phải khớp với tên module khai báo trong `module-info.java`.

Module API:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

File `src/com.acme.api/com/acme/api/Greeter.java`:

~~~java
package com.acme.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("JPMS"));
    }
}
~~~

Ở đây:

- `com.acme.api` export package `com.acme.api`, do đó module khác có thể dùng public API trong package này.
- `com.acme.app` khai báo `requires com.acme.api`, tạo dependency module rõ ràng.
- `com.acme.app` không cần copy source hoặc class của API vào package của mình.

Một module thông thường tự động đọc `java.base`; không cần viết `requires java.base`.

## 2. Ý nghĩa của javac --module

Cú pháp tổng quát:

~~~bash
javac --module-source-path <source-root> -d <output-directory> --module <module-name>
~~~

Các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--module` hoặc `-m` | Chọn module cần compile; có thể truyền nhiều tên module, phân cách bằng dấu phẩy |
| `--module-source-path` | Chỉ định gốc source chứa các thư mục module |
| `--module-path` hoặc `-p` | Chỉ định nơi tìm các module dependency đã biên dịch hoặc đóng gói |
| `-d` | Chỉ định thư mục chứa class file đầu ra |
| `--release` | Compile theo API và ngôn ngữ của một Java release cụ thể |

Ví dụ compile module độc lập:

~~~bash
javac --module-source-path src -d out --module com.acme.app
~~~

Lệnh này yêu cầu javac tìm source của module `com.acme.app` trong `src` và ghi kết quả vào `out`. Ví dụ trên chỉ compile được nếu dependency của module đã có sẵn để resolve hoặc module không có dependency ứng dụng chưa được biên dịch.

`-m` là cách viết ngắn tương đương:

~~~bash
javac --module-source-path src -d out -m com.acme.app
~~~

Tên sau `--module` là **tên module**, không phải tên package, tên class hay đường dẫn thư mục.

## 3. Compile một module có dependency

Trong ví dụ, `com.acme.app` yêu cầu `com.acme.api`. Có hai cách rõ ràng để compile.

### Cách A: Compile các module cần thiết cùng lúc

~~~bash
javac --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

Javac tìm cả hai module trong source path, compile và ghi kết quả vào thư mục output. Đây là cách thuận tiện khi source của dependency và module đích đều đang có trong cùng dự án.

Kết quả có cấu trúc:

~~~text
out/
├── com.acme.api/
│   ├── module-info.class
│   └── com/acme/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Mỗi module được đặt trong một thư mục riêng bên dưới output directory. Không cần tự tạo thư mục output cho từng module.

### Cách B: Compile dependency trước, sau đó compile riêng module đích

Bước 1 — compile module API:

~~~bash
javac --module-source-path src -d out --module com.acme.api
~~~

Bước 2 — compile module ứng dụng, dùng output đã có làm module path:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.app
~~~

Trong bước 2:

- `--module-path out` cho javac biết module `com.acme.api` đã được compile nằm trong `out`.
- `--module-source-path src` cho javac biết source của module `com.acme.app` nằm ở đâu.
- `--module com.acme.app` chọn đúng module cần compile.
- `-d out` ghi class file của ứng dụng vào `out/com.acme.app`.

Cách này hữu ích khi bạn chỉ thay đổi module ứng dụng, còn module API đã được compile hoặc được cung cấp dưới dạng modular JAR.

Nếu dependency nằm trong file JAR, đặt file JAR đó trên module path, ví dụ:

~~~bash
javac --module-path "lib/com.acme.api.jar" --module-source-path src -d out --module com.acme.app
~~~

Nếu có nhiều mục trên module path, phân cách chúng bằng dấu phân cách đường dẫn của hệ điều hành: dấu hai chấm trên Linux/macOS và dấu chấm phẩy trên Windows.

## 4. Compile và chạy module trên Windows PowerShell

Trong PowerShell, cấu trúc lệnh giống nhau. Nếu đang ở thư mục gốc dự án:

~~~powershell
javac --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

Sau khi compile, chạy main class theo cú pháp module:

~~~powershell
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Có thể viết ngắn:

~~~powershell
java -p out -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, JPMS
~~~

Cú pháp `module-name/main-class` chỉ rõ class main thuộc module nào. Nếu module có nhiều class cùng tên ở các package khác nhau, tên đầy đủ của main class loại bỏ sự mơ hồ.

Nếu module descriptor có khai báo main class trong metadata của JAR, một số cách khởi chạy có thể rút gọn; trong bài này, chỉ định rõ `module/main-class` giúp dễ hiểu và hoạt động nhất quán.

## 5. Phân biệt module-source-path và module-path

Hai tùy chọn có tên gần giống nhưng phục vụ hai nguồn dữ liệu khác nhau:

| Tùy chọn | Chứa gì? | Dùng khi nào? |
|---|---|---|
| `--module-source-path` | Source của các module, bao gồm `module-info.java` và file `.java` | Khi javac cần tìm module source để compile |
| `--module-path` | Module đã biên dịch dạng exploded module hoặc modular JAR | Khi javac cần resolve dependency của module đang compile |

Ví dụ, với:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.app
~~~

- `src` là đầu vào source.
- `out` là nơi javac tìm dependency đã compile và cũng là nơi ghi output.
- `com.acme.app` là module được chọn để compile.

Không dùng `--module-path` để trỏ vào thư mục source thô chưa được tổ chức thành module đã biên dịch. Ngược lại, không dùng `--module-source-path` thay cho nơi chứa modular JAR dependency.

### Module path khác classpath

Classpath phục vụ class và JAR trên classpath, thường thuộc unnamed module. Module path cung cấp các named module có descriptor và dependency được kiểm tra theo JPMS.

Nếu `module-info.java` có:

~~~java
requires com.acme.api;
~~~

thì javac cần tìm module có tên `com.acme.api` trên module path hoặc trong các module source được chọn để compile. Một JAR chỉ đặt trên classpath không tự trở thành named module `com.acme.api`.

Với thư viện cũ chưa có module descriptor, Java có thể xử lý một số JAR như automatic module khi đặt trên module path. Tên automatic module phụ thuộc quy tắc suy ra tên từ JAR; hãy kiểm tra bằng công cụ JDK trước khi dùng trong `requires`.

## 6. Compile một module duy nhất trong dự án lớn

Trong dự án có nhiều module, bạn thường không muốn compile tất cả module mỗi lần. Chỉ định một module bằng `--module` giúp giới hạn phạm vi compile.

Giả sử source tree có:

~~~text
src/
├── com.acme.api/
├── com.acme.app/
├── com.acme.cli/
└── com.acme.testkit/
~~~

Nếu chỉ compile `com.acme.cli`, lệnh có thể là:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.cli
~~~

Điều kiện là các dependency mà `com.acme.cli` khai báo trong `requires` đã có sẵn trên module path hoặc được cung cấp trong lần compile này. Nếu module CLI yêu cầu `com.acme.api` và `com.acme.testkit`, nhưng hai module đó chưa compile, hãy compile chúng trước hoặc chỉ định tất cả module cần thiết:

~~~bash
javac --module-source-path src -d out --module com.acme.api,com.acme.testkit,com.acme.cli
~~~

Javac không nên được xem như một hệ thống build tự động suy ra toàn bộ thứ tự build của dự án. Trong dự án nhiều module, Gradle hoặc Maven thường quản lý dependency graph và incremental compilation; javac là compiler được build tool gọi với các đầu vào đã xác định.

## 7. Kiểm tra module descriptor và kết quả compile

Sau khi compile, kiểm tra module đã tạo:

~~~bash
java --module-path out --describe-module com.acme.app
~~~

Lệnh này yêu cầu runtime mô tả module `com.acme.app` tìm được trên module path. Đầu ra có thể cho thấy:

~~~text
com.acme.app
requires com.acme.api
requires java.base mandated
~~~

Để kiểm tra file class của descriptor:

~~~bash
javap -v out/com.acme.app/module-info.class
~~~

Trong phần output chi tiết, chú ý thuộc tính `Module`: nó chứa module name, requires, exports, opens, uses và provides tương ứng.

Để xem các module có trong thư mục output:

~~~bash
java --module-path out --list-modules
~~~

Lưu ý: `--list-modules` liệt kê module mà runtime tìm thấy trên module path cùng các module hệ thống. Nếu chỉ muốn kiểm tra một descriptor cụ thể, `--describe-module` thường dễ đọc hơn.

## 8. Dùng --release khi cần cố định Java API mục tiêu

Nếu dự án cần tương thích với một Java release cụ thể, có thể thêm `--release`:

~~~bash
javac --release 21 --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

`--release 21` yêu cầu compiler dùng quy tắc ngôn ngữ, bytecode và API nền tảng của Java 21. Chỉ dùng release mà JDK đang cài hỗ trợ.

Không kết hợp `--release` với `--source` hoặc `--target` trong cùng lệnh. Khi đã dùng `--release`, compiler đã nhận đủ thông tin về mức Java mục tiêu.

Nếu dự án dùng preview feature, cần thêm cấu hình preview tương ứng và đảm bảo compile/run cùng release; đó là trường hợp riêng, không cần bật cho module Java thông thường.

## 9. Lỗi thường gặp và cách xử lý

**Module không tìm thấy trên module source path.** Kiểm tra cấu trúc thư mục: `src/com.acme.app/module-info.java`. Tên thư mục module phải tương ứng với tên khai báo trong descriptor và tên sau `--module`.

**Package không tồn tại hoặc không được đọc.** Kiểm tra module khai báo `requires` đúng module API chưa, và module API đã có trên `--module-path` hoặc được compile cùng lần hay chưa. Đồng thời kiểm tra package API đã được `exports` chưa.

**`module not found: com.acme.api`.** Có thể module API chưa compile, module path trỏ nhầm thư mục, hoặc JAR không phải modular/automatic module với tên bạn yêu cầu. Chạy `java --module-path out --describe-module com.acme.api` để kiểm tra module path.

**`package ... is not visible`.** Module có thể đã được resolve nhưng package chứa kiểu cần dùng chưa được export. Thêm `exports package.name` vào descriptor của module sở hữu package nếu đó là API công khai dự kiến.

**Compile được nhưng không chạy được bằng `java -m`.** Kiểm tra module path lúc chạy có chứa tất cả module cần thiết không và chỉ định đúng `module/main-class`. Compile thành công không đảm bảo runtime path đã được cấu hình đúng.

**Dùng nhầm tên package sau `--module`.** `--module` nhận tên module như `com.acme.app`, không nhận `com.acme.app.Main`. Tên class main chỉ được đưa vào lệnh chạy sau dấu gạch chéo.

**Đặt nhiều module vào cùng một output package tree.** Với modular compilation, javac tạo thư mục output riêng theo tên module. Không tự gom class của nhiều module vào một thư mục package chung; điều đó làm mất ranh giới module và có thể gây split package.

## 10. Thực hành

1. Tạo source tree cho `com.acme.api` và `com.acme.app` như ví dụ.
2. Compile cả hai module bằng `javac --module-source-path src -d out --module com.acme.api,com.acme.app`.
3. Xóa thư mục output, sau đó compile riêng API trước và compile riêng app bằng `--module-path out`.
4. Chạy ứng dụng bằng `java --module-path out --module com.acme.app/com.acme.app.Main`.
5. Thử đổi tên sau `--module` thành tên package hoặc tên class để quan sát lỗi, sau đó sửa lại bằng module name.
6. Thử bỏ `exports com.acme.api` khỏi descriptor API và compile lại để thấy sự khác biệt về khả năng truy cập package.
7. Dùng `java --describe-module com.acme.app` và `javap -v` để đối chiếu descriptor sau compile.

Khi compile modular, hãy xác định module đích trước, bảo đảm source tree được tổ chức theo module name, rồi cung cấp dependency đã compile trên module path. `--module` giới hạn module cần biên dịch; `--module-source-path` tìm source; `--module-path` resolve dependency; `-d` giữ output của từng module trong thư mục riêng. Bốn phần đó tạo thành quy trình compile một module có thể lặp lại và kiểm tra được.
