# Chạy ứng dụng modular bằng `java -m module/main-class`

## Mục tiêu

Sau bài này, bạn có thể đọc và viết đúng cú pháp `java -m module/main-class`, chọn module path cho ứng dụng JPMS, hiểu cách launcher phân giải root module và dependency trước khi gọi `main`, truyền tham số cho chương trình, đóng gói modular JAR có main class và chẩn đoán các lỗi thường gặp khi chạy ứng dụng modular.

## 1. Cú pháp của lệnh chạy modular

Cú pháp tổng quát:

~~~bash
java [launcher-options] --module module-name[/main-class] [application-args...]
~~~

Dạng viết tắt:

~~~bash
java [launcher-options] -m module-name[/main-class] [application-args...]
~~~

Trong đó:

- `java` gọi Java launcher của JDK.
- `--module-path` hoặc `-p` chỉ định nơi launcher tìm named module.
- `--module` hoặc `-m` yêu cầu chạy một module làm root module.
- `module-name` là tên module, ví dụ `com.acme.app`.
- `main-class` là tên đầy đủ của class có phương thức khởi chạy, ví dụ `com.acme.app.Main`.
- `application-args` là các tham số được truyền vào `main(String[] args)`.

Ví dụ cơ bản:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Viết ngắn:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

Hai lệnh trên tương đương. `-p` là dạng ngắn của `--module-path`, còn `-m` là dạng ngắn của `--module`.

Phần trước dấu gạch chéo là tên module. Phần sau dấu gạch chéo là tên class đầy đủ, bao gồm package. Không ghi tên file `.class`, không dùng đường dẫn thư mục thay cho tên class và không ghi tên module theo kiểu package/class.

## 2. Module path chứa những gì?

Module path là nơi launcher tìm các module được đặt tên. Nó có thể chứa modular JAR và exploded module đã biên dịch. Ví dụ cấu trúc:

~~~text
project/
  mods/
    com.acme.app/
      module-info.class
      com/acme/app/Main.class
    com.acme.greeter/
      module-info.class
      com/acme/greeter/Greeter.class
~~~

Đây là hai exploded module nằm dưới thư mục `mods`. Một cấu trúc khác thường gặp là lưu các module dưới dạng JAR:

~~~text
project/
  mods/
    com.acme.app.jar
    com.acme.greeter.jar
~~~

Cả hai cách đều có thể được tìm qua module path:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Launcher tìm module `com.acme.app` trong module path, sau đó phân giải các dependency được khai báo trong descriptor của module đó.

Nếu module path có nhiều entry, phân tách chúng bằng ký tự phân cách path của hệ điều hành:

- Windows: dấu chấm phẩy `;`.
- Linux và macOS: dấu hai chấm `:`.

Ví dụ trên Windows:

~~~powershell
java --module-path "mods;lib/extra-modules" -m com.acme.app/com.acme.app.Main
~~~

Ví dụ trên Linux/macOS:

~~~bash
java --module-path "mods:lib/extra-modules" -m com.acme.app/com.acme.app.Main
~~~

Hãy đặt đường dẫn trong dấu nháy khi nó chứa khoảng trắng hoặc ký tự đặc biệt của shell.

## 3. Ví dụ hoàn chỉnh với hai module

Ta có module thư viện `com.acme.greeter` và module ứng dụng `com.acme.app`.

### Cấu trúc source

~~~text
src/
  com.acme.greeter/
    module-info.java
    com/acme/greeter/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
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

### Biên dịch các module

Từ thư mục `project`, dùng:

~~~bash
javac -d out --module-source-path src -m com.acme.greeter,com.acme.app
~~~

Trong đó:

- `-d out` đặt output đã biên dịch vào thư mục `out`.
- `--module-source-path src` cho compiler biết thư mục gốc chứa các source module.
- `-m com.acme.greeter,com.acme.app` chỉ định các module cần biên dịch.

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
out/
  com.acme.greeter/
    module-info.class
    com/acme/greeter/Greeter.class
  com.acme.app/
    module-info.class
    com/acme/app/Main.class
~~~

### Chạy module ứng dụng

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, Java
~~~

Truyền tham số cho chương trình:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main Ada
~~~

Kết quả:

~~~text
Hello, Ada
~~~

Các đối số xuất hiện sau phần module/main-class được truyền vào `String[] args`. Trong ví dụ, `args[0]` có giá trị `Ada`.

## 4. Launcher phân giải module như thế nào?

Khi chạy:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

launcher thực hiện các công việc chính trước khi gọi phương thức `main`:

1. Tìm root module `com.acme.app` trên module path.
2. Đọc module descriptor của root module.
3. Phân giải các dependency cần thiết, ví dụ `requires com.acme.greeter`.
4. Xây dựng module graph hợp lệ từ các module có thể quan sát và các dependency được yêu cầu.
5. Tạo runtime layer cho ứng dụng nếu đang khởi động ứng dụng modular theo cách thông thường.
6. Nạp main class và gọi phương thức `main` với các application arguments.

Vì vậy, module path phải cung cấp đủ module cần thiết trước khi chương trình bắt đầu. Nếu thiếu một dependency bắt buộc, launcher dừng trong quá trình phân giải; code trong `main` chưa được thực thi.

`requires transitive` cũng ảnh hưởng đến readability của graph: nếu module A yêu cầu module B bằng `requires transitive`, module đọc A có thể đọc B theo quy tắc readability. Launcher vẫn phân giải dependency theo module descriptor thay vì tự suy ra dependency từ các class import.

Các module trong JDK như `java.base` thường đã có trong boot layer và được phân giải từ parent configuration. Bạn không cần tự thêm `java.base` vào module path.

## 5. Có thể bỏ phần main class khi nào?

Thông thường, lệnh chạy chỉ rõ cả module và main class:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

Có thể chỉ ghi tên module nếu module descriptor đã lưu main class của ứng dụng bằng thuộc tính `ModuleMainClass`:

~~~bash
java -p mods -m com.acme.app
~~~

Thuộc tính này thường được thiết lập khi tạo modular JAR bằng tùy chọn `--main-class` của công cụ `jar`.

Ví dụ, sau khi đã biên dịch module vào `out/com.acme.app` và `out/com.acme.greeter`, có thể đóng gói từng module:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Lệnh chạy không cần ghi main class:

~~~bash
java --module-path mods --module com.acme.app
~~~

Nếu modular JAR không có main class được ghi trong descriptor và lệnh cũng không chỉ rõ `/main-class`, launcher không biết class nào cần khởi chạy. Khi đó, hãy thêm main class vào lệnh hoặc tạo lại JAR với `jar --main-class`.

## 6. Phân biệt `-m` với `-cp` và `-jar`

Ba kiểu khởi chạy thường gặp có ý nghĩa khác nhau.

### Chạy class trên class path

~~~bash
java -cp "classes;lib/*" com.acme.app.Main
~~~

Class path đưa class và JAR vào unnamed module của class loader. Lệnh này chạy theo mô hình class path truyền thống; nó không chọn root named module bằng `-m`.

### Chạy named module

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Module path và module descriptor được dùng để xác định module graph, dependency và ranh giới truy cập JPMS.

### Chạy executable JAR

~~~bash
java -jar application.jar
~~~

`-jar` chọn JAR làm nguồn khởi chạy executable JAR. Khi cần điều khiển rõ named module, module path và root module, hãy dùng `--module-path` cùng `--module`. Đừng thay `-m module/main-class` bằng `-jar` nếu mục tiêu là kiểm tra cách launcher khởi chạy một named module.

## 7. Các launcher option hữu ích khi chạy modular

| Option | Tác dụng |
| --- | --- |
| `--module-path`, `-p` | Chỉ định nơi tìm module. |
| `--module`, `-m` | Chọn root module và tùy chọn main class. |
| `--show-module-resolution` | In thông tin quá trình phân giải module khi khởi động. |
| `--list-modules` | Liệt kê các module có thể quan sát trong cấu hình launcher. |
| `--describe-module` | Hiển thị descriptor của một module. |
| `--add-modules` | Thêm các module được chỉ định làm root module bổ sung. |
| `--limit-modules` | Giới hạn tập module có thể quan sát khi phân giải. |
| `--add-reads` | Bổ sung readability edge giữa các module. |
| `--add-exports` | Export package của module cho module đích khi chạy. |
| `--add-opens` | Mở package của module cho deep reflection từ module đích. |

Để quan sát module graph được phân giải khi khởi chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Để xem descriptor của một module:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

Để xem các module mà runtime có thể liệt kê:

~~~bash
java --module-path mods --list-modules
~~~

Các option như `--add-reads`, `--add-exports` và `--add-opens` hữu ích khi chẩn đoán hoặc hỗ trợ tương thích. Với cấu hình ứng dụng ổn định, nên khai báo dependency và ranh giới truy cập trong `module-info.java` thay vì phụ thuộc lâu dài vào các override lúc chạy.

## 8. Lỗi thường gặp khi dùng `java -m`

### Module not found

Ví dụ:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.acme.app not found
~~~

Nguyên nhân thường gặp:

- Tên module trong lệnh không đúng với tên trong descriptor.
- Thư mục hoặc JAR chứa module không nằm trong module path.
- Dùng nhầm thư mục con làm module path.
- Module chưa được biên dịch hoặc đóng gói.

Kiểm tra cấu trúc thư mục, `module-info.class` và giá trị tên module. Thử:

~~~bash
java --module-path mods --list-modules
~~~

### Missing required module

Nếu module ứng dụng có `requires com.acme.greeter` nhưng module path không chứa dependency đó, quá trình phân giải thất bại trước khi vào `main`.

Hãy bổ sung JAR hoặc exploded module tương ứng vào module path. Nếu có nhiều entry, dùng đúng path separator của hệ điều hành.

### Main class không được tìm thấy

Kiểm tra phần sau dấu gạch chéo:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

`com.acme.app.Main` phải là tên đầy đủ của class, đúng package và nằm trong module được chọn. Không thêm đuôi `.class` và không thay dấu chấm package bằng dấu gạch chéo thư mục.

Nếu bỏ main class, hãy chắc chắn modular JAR đã ghi `ModuleMainClass` bằng `jar --main-class`.

### Class hoặc package không truy cập được

Kiểm tra:

- Module ứng dụng có `requires` module chứa kiểu được dùng hay chưa.
- Module sở hữu package có `exports` package đó cho module ứng dụng hay chưa.
- Nếu lỗi đến từ reflection sâu, package có được `opens` cho module thực hiện reflection hay chưa.

Readability, exports và opens là ba điều kiện khác nhau. Chỉ có module path đúng không tự động làm mọi package public hoặc private có thể truy cập.

### Đang chạy nhầm Java runtime

Có thể kiểm tra phiên bản và đường dẫn Java được shell sử dụng:

~~~bash
java -version
~~~

Trên Windows PowerShell, có thể xem executable được tìm thấy:

~~~powershell
Get-Command java
~~~

Đảm bảo runtime dùng để chạy tương thích với bytecode và các module đã biên dịch. JPMS có từ Java 9 trở lên.

## 9. Checklist trước khi chạy ứng dụng modular

1. Module ứng dụng có `module-info.class` và tên module đúng.
2. Main class nằm trong module ứng dụng, có entry point hợp lệ.
3. Tất cả dependency bắt buộc có thể tìm thấy trên module path hoặc trong các parent layer.
4. Lệnh dùng `--module-path` để chỉ đúng vị trí các module.
5. Lệnh dùng `-m module/main-class`, hoặc module descriptor đã ghi main class.
6. Các application arguments nằm sau phần module/main-class.
7. Nếu gặp lỗi phân giải, dùng `--show-module-resolution` và `--describe-module` để xem module graph và descriptor.

## Ghi nhớ

`java -m module/main-class` yêu cầu Java launcher chạy một named module và gọi main class bên trong module đó. `--module-path` xác định nơi tìm module; launcher phân giải root module cùng dependency trước khi thực thi chương trình. Có thể bỏ main class khỏi lệnh khi module descriptor đã lưu `ModuleMainClass`, thường được thiết lập bằng `jar --main-class`. Dùng `--show-module-resolution` và `--describe-module` để hiểu launcher đang phân giải module nào khi debug.
