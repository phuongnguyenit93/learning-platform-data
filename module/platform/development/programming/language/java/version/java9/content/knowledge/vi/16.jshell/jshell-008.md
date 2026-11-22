# Cấu hình class path, module path và mô-đun bổ sung trong Java

Java có hai cơ chế tìm và phân giải mã thư viện thường gặp: **class path** cho mã chạy trong unnamed module và **module path** cho các mô-đun có tên trong hệ thống mô-đun Java (JPMS). Khi cần kích hoạt thêm một mô-đun mà ứng dụng không tự kéo vào đồ thị mô-đun ban đầu, có thể dùng tùy chọn `--add-modules`.

Các tùy chọn này được dùng khi biên dịch và chạy chương trình. Ví dụ dưới đây dùng cú pháp hiện hành, tương thích Java 17 trở lên; phần lệnh được kiểm tra bằng JDK 24.

## 1. Class path là gì?

Class path là danh sách thư mục, tệp JAR hoặc ZIP mà trình biên dịch và JVM tìm kiếm các lớp Java. Nó thường được dùng cho ứng dụng chưa khai báo mô-đun hoặc thư viện được đưa vào ứng dụng theo cách truyền thống.

Hai lệnh chính:

- `javac --class-path <path>` hoặc `javac -cp <path>`: chỉ định nơi `javac` tìm lớp phụ thuộc khi biên dịch.
- `java --class-path <path>` hoặc `java -cp <path>`: chỉ định nơi JVM tìm lớp ứng dụng và thư viện khi chạy.

Một mục class path có thể là:

- Thư mục gốc chứa cây package đã biên dịch, ví dụ `out/`.
- Tệp JAR chứa các lớp, ví dụ `lib/textlib.jar`.
- Tệp ZIP chứa các lớp.
- Danh sách nhiều thư mục hoặc archive.

Nếu thư mục chứa lớp `com.example.text.Text`, cấu trúc phải bắt đầu từ thư mục gốc class path như sau:

~~~text
out/
└── com/
    └── example/
        └── text/
            └── Text.class
~~~

JVM tìm lớp theo tên đầy đủ `com.example.text.Text` tương ứng với đường dẫn tương đối `com/example/text/Text.class` bên dưới mỗi mục class path. Các mục được tìm theo thứ tự; nếu cùng một tên lớp xuất hiện ở nhiều vị trí, mục được tìm thấy trước có thể che khuất bản còn lại. Vì vậy, cần tránh đưa nhiều phiên bản khác nhau của cùng một thư viện vào class path.

### Ví dụ: dùng thư viện JAR trên class path

Giả sử thư viện được biên dịch và đóng gói thành `lib/textlib.jar`, chứa lớp sau:

~~~java
package com.example.text;

public class Text {
    public static String message() {
        return "Hello from class path";
    }
}
~~~

Ứng dụng sử dụng lớp đó:

~~~java
package com.example.app;

import com.example.text.Text;

public class Main {
    public static void main(String[] args) {
        System.out.println(Text.message());
    }
}
~~~

Trên PowerShell, tạo các thư mục đầu ra, biên dịch thư viện và đóng gói JAR:

~~~powershell
New-Item -ItemType Directory -Force lib,lib-classes,out | Out-Null
javac --release 17 -d lib-classes src-lib/com/example/text/Text.java
jar --create --file lib/textlib.jar -C lib-classes .
~~~

Biên dịch ứng dụng với thư viện trên class path:

~~~powershell
javac --release 17 --class-path "lib/textlib.jar" -d out src/com/example/app/Main.java
~~~

Chạy ứng dụng trên Windows:

~~~powershell
java --class-path "out;lib/textlib.jar" com.example.app.Main
~~~

Kết quả:

~~~text
Hello from class path
~~~

Trên Linux hoặc macOS, dấu phân cách các mục trong class path là dấu hai chấm (`:`), vì vậy lệnh chạy tương ứng là:

~~~bash
java --class-path "out:lib/textlib.jar" com.example.app.Main
~~~

Có thể dùng wildcard để đưa các JAR trực tiếp trong một thư mục vào class path, ví dụ `lib/*`. Wildcard này giúp tránh phải liệt kê từng JAR; nó không tìm JAR đệ quy trong mọi thư mục con.

## 2. Module path là gì?

Module path là danh sách vị trí để Java tìm các mô-đun có tên. Một mô-đun có tên được nhận diện bằng tệp `module-info.class` trong mô-đun đã biên dịch hoặc trong JAR mô-đun. Tệp nguồn `module-info.java` khai báo tên mô-đun, các phụ thuộc và package được công khai cho mô-đun khác.

Tùy chọn chính:

- `javac --module-path <path>` hoặc `javac -p <path>`: nơi trình biên dịch tìm các mô-đun phụ thuộc.
- `java --module-path <path>` hoặc `java -p <path>`: nơi JVM tìm các mô-đun khi chạy.
- `java --module <module>` hoặc `java -m <module>`: khởi chạy mô-đun được chỉ định; có thể thêm `/fully.qualified.MainClass` để chỉ rõ lớp main.

Một mục module path có thể trỏ đến một modular JAR hoặc một thư mục chứa các mô-đun đã giải nén (exploded modules). Ví dụ, nếu thư mục `mods` chứa `com.example.app` và `com.example.greeter`, có thể dùng `mods` làm module path.

### Module descriptor và quan hệ phụ thuộc

Một mô-đun khai báo những gì nó cần và những package nào được phép truy cập từ bên ngoài. Ví dụ:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

`exports` công khai package cho các mô-đun khác đọc mô-đun này. Nó không làm cho mọi package nội bộ trở thành API công khai.

Mô-đun ứng dụng khai báo phụ thuộc bằng `requires`:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Khi mô-đun ứng dụng yêu cầu `com.example.greeter`, trình phân giải mô-đun cần tìm được mô-đun đó trên module path. Những phụ thuộc được khai báo bằng `requires` được đưa vào đồ thị mô-đun khi phân giải ứng dụng.

### Ví dụ: hai mô-đun chạy trên module path

Cấu trúc mã nguồn:

~~~text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

`src/com.example.greeter/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

`src/com.example.greeter/com/example/greeter/Greeter.java`:

~~~java
package com.example.greeter;

public class Greeter {
    public String message() {
        return "Hello from module path";
    }
}
~~~

`src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

`src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().message());
    }
}
~~~

Biên dịch cả hai mô-đun từ thư mục gốc dự án:

~~~bash
javac --release 17 -d mods --module-source-path src -m com.example.greeter,com.example.app
~~~

`--module-source-path src` cho biết cách tìm mã nguồn theo cấu trúc thư mục mô-đun; `-m` chọn các mô-đun cần biên dịch; `-d mods` đặt đầu ra đã biên dịch vào thư mục `mods`.

Sau khi biên dịch, thư mục đầu ra có dạng:

~~~text
mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Chạy mô-đun ứng dụng:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello from module path
~~~

Có thể đóng gói mỗi thư mục mô-đun thành modular JAR bằng công cụ `jar`:

~~~bash
mkdir -p mlib
jar --create --file mlib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file mlib/com.example.app.jar -C mods/com.example.app .
java --module-path mlib --module com.example.app/com.example.app.Main
~~~

Khi chạy, JVM tìm hai modular JAR trong `mlib`, đọc descriptor, phân giải `requires com.example.greeter` và khởi chạy lớp main của `com.example.app`.

## 3. Khác nhau giữa class path và module path

| Tiêu chí | Class path | Module path |
|---|---|---|
| Đơn vị tìm kiếm | Thư mục lớp, JAR, ZIP | Modular JAR hoặc thư mục mô-đun đã giải nén |
| Mô hình mã | Unnamed module | Named modules |
| Khai báo phụ thuộc | Thường dựa vào thư viện được đưa vào class path | `requires` trong `module-info.java` |
| Công khai package | Mã class path không có ranh giới export theo JPMS | `exports` xác định package được mô-đun khác truy cập |
| Cách chạy phổ biến | Chỉ định lớp main | Chỉ định mô-đun bằng `-m` hoặc `--module` |
| Cách chỉ định | `-cp` hoặc `--class-path` | `-p` hoặc `--module-path` |

Class path và module path có thể cùng xuất hiện trong một lệnh chạy. Khi đó, lớp từ class path thuộc unnamed module; các mô-đun có tên được phân giải từ module path. Cần bảo đảm ứng dụng và thư viện nằm đúng cơ chế mà cấu trúc của chúng yêu cầu.

Nếu đặt một JAR có `module-info.class` lên class path, ứng dụng dùng JAR đó như thư viện class path; descriptor không được dùng để tạo một named module trong lần chạy này. Vì vậy, vị trí của JAR có thể làm thay đổi cách Java áp dụng ranh giới mô-đun.

Một JAR không có `module-info.class` nhưng được đặt trên module path có thể được xử lý như **automatic module**. Tên mô-đun có thể lấy từ thuộc tính `Automatic-Module-Name` trong manifest hoặc được suy ra từ tên JAR. Cơ chế này hỗ trợ tích hợp dần các thư viện; với mô-đun do mình phát triển, descriptor tường minh giúp tên, phụ thuộc và API ổn định hơn.

## 4. Bổ sung mô-đun bằng --add-modules

`--add-modules` yêu cầu trình phân giải đưa một hoặc nhiều mô-đun làm root module bổ sung, bên cạnh các mô-đun ban đầu của ứng dụng. Tùy chọn này có trên cả `java` và `javac`.

Cú pháp:

~~~bash
java --add-modules module.name --class-path out com.example.Main
javac --add-modules module.name --class-path lib/example.jar -d out src/com/example/Main.java
~~~

Có thể chỉ định nhiều mô-đun bằng dấu phẩy:

~~~bash
java --add-modules java.sql,jdk.httpserver --class-path out com.example.Main
~~~

Một số giá trị đặc biệt được hỗ trợ:

- `ALL-DEFAULT`: các mô-đun mặc định.
- `ALL-SYSTEM`: tất cả mô-đun hệ thống.
- `ALL-MODULE-PATH`: tất cả mô-đun tìm thấy trên module path.

Chỉ dùng giá trị bao quát khi thực sự cần mở rộng tập mô-đun được phân giải. Thông thường nên chỉ định tên mô-đun cụ thể để cấu hình dễ hiểu và hạn chế phụ thuộc ngoài dự kiến.

### Ví dụ: thêm mô-đun hệ thống jdk.httpserver

Ứng dụng sau sử dụng API `HttpServer` thuộc mô-đun hệ thống `jdk.httpserver`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;

public class HttpModuleCheck {
    public static void main(String[] args) throws Exception {
        HttpServer server =
            HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);

        System.out.println(server.getAddress().getPort() > 0);
        server.stop(0);
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.httpserver -d out src/HttpModuleCheck.java
java --add-modules jdk.httpserver --class-path out HttpModuleCheck
~~~

Kết quả:

~~~text
true
~~~

Cổng được yêu cầu là `0` để hệ điều hành chọn một cổng trống. Chương trình kiểm tra cổng đã cấp có giá trị dương rồi dừng server; kết quả không phụ thuộc vào số cổng cụ thể.

Khi một named module đã được khai báo trong `requires` của mô-đun ứng dụng, trình phân giải tự đưa nó vào đồ thị phụ thuộc. Không cần thêm `--add-modules` chỉ để lặp lại một phụ thuộc đã khai báo. Tùy chọn này hữu ích khi cần bổ sung root module mà ứng dụng không yêu cầu trực tiếp, chẳng hạn một mô-đun hệ thống được ứng dụng class path sử dụng.

## 5. Phân biệt --add-modules với các tùy chọn truy cập mô-đun

Một số lỗi JPMS không phải do thiếu mô-đun. Các tùy chọn sau xử lý những khía cạnh khác nhau:

- `--add-reads source=target` bổ sung quan hệ đọc giữa hai mô-đun.
- `--add-exports source/package=target` cho phép mô-đun đích truy cập package được chỉ định của mô-đun nguồn.
- `--add-opens source/package=target` mở package cho truy cập phản chiếu sâu (deep reflection) từ mô-đun đích.

Các tùy chọn này không thay thế `--add-modules`. Nếu mô-đun chưa được tìm thấy hoặc chưa được phân giải, cần kiểm tra module path và đồ thị mô-đun trước. Chỉ dùng các tùy chọn mở rộng quyền truy cập khi có yêu cầu tương thích cụ thể; với mã mới, nên khai báo `requires`, `exports` hoặc `opens` đúng trong descriptor của mô-đun do mình quản lý.

## 6. Kiểm tra và chẩn đoán cấu hình

Các lệnh sau giúp xác định Java đang nhìn thấy những mô-đun nào và vì sao cấu hình chạy thất bại:

| Lệnh | Mục đích |
|---|---|
| `java --list-modules` | Liệt kê các mô-đun hệ thống và mô-đun có thể quan sát từ runtime. |
| `java --describe-module java.sql` | Xem descriptor của một mô-đun cụ thể. |
| `java --show-module-resolution -m com.example.app/com.example.app.Main` | Hiển thị quá trình phân giải mô-đun khi khởi chạy. |
| `java --validate-modules` | Kiểm tra tính hợp lệ và xung đột trong tập mô-đun quan sát được. |
| `javac --module-path mods ...` | Biên dịch khi cần tìm các mô-đun phụ thuộc. |

Một số thông báo lỗi phổ biến:

- **`ClassNotFoundException` hoặc `NoClassDefFoundError`:** kiểm tra class path lúc chạy, tên lớp đầy đủ và việc JAR có thực sự chứa lớp cần dùng hay không.
- **`package ... does not exist` khi biên dịch:** kiểm tra class path hoặc module path được truyền cho `javac`, tên package và thư viện đã biên dịch.
- **`module not found`:** kiểm tra tên trong `requires` hoặc `--add-modules`, đường dẫn module path và cấu trúc modular JAR/thư mục mô-đun.
- **Package không được export hoặc mô-đun không đọc được:** kiểm tra `exports` và `requires` trong descriptor. Chỉ cân nhắc tùy chọn `--add-exports` hoặc `--add-reads` khi cần tương thích đặc biệt.
- **Nhiều phiên bản thư viện gây hành vi không nhất quán:** kiểm tra thứ tự class path và loại bỏ các bản JAR trùng lặp không cần thiết.

Luôn kiểm tra lệnh biên dịch và lệnh chạy riêng biệt. Một thư viện có mặt trong class path của `javac` nhưng không có trong class path của `java` vẫn có thể khiến ứng dụng biên dịch thành công nhưng lỗi khi chạy.

## 7. Thực hành tốt khi cấu hình dependency

- Dùng `--class-path` cho ứng dụng class path và `--module-path` cho ứng dụng/module có tên; không trộn hai cơ chế theo thói quen.
- Khai báo phụ thuộc của named module trong `module-info.java` bằng `requires`, và chỉ `exports` package cần làm API.
- Giữ một nguồn rõ ràng cho từng phiên bản thư viện; kiểm tra thứ tự class path khi có lớp trùng tên.
- Dùng đường dẫn tương đối hoặc cấu hình build có thể tái lập; đặt trong dấu nháy khi đường dẫn chứa khoảng trắng.
- Nhớ rằng dấu phân cách nhiều mục là `;` trên Windows và `:` trên Linux/macOS.
- Dùng `--add-modules` cho root module bổ sung cụ thể; tránh thêm toàn bộ mô-đun nếu ứng dụng không cần.
- Kiểm tra module path bằng `--show-module-resolution` và `--validate-modules` khi có lỗi phân giải.
- Với dự án dùng Maven hoặc Gradle, quản lý dependency và cấu hình module thông qua build script; lệnh `javac`/`java` trực tiếp hữu ích để hiểu hoặc tái hiện lỗi cấu hình.
- Tránh đặt class path toàn cục trong môi trường phát triển dùng chung. Truyền class path và module path rõ ràng theo từng lệnh giúp cấu hình dễ tái hiện và chẩn đoán hơn.

Khi chọn đúng cơ chế, class path giúp ứng dụng và thư viện không dùng descriptor mô-đun làm việc cùng nhau; module path bổ sung phân giải phụ thuộc có tên và ranh giới package rõ ràng. `--add-modules` chỉ mở rộng tập root module được phân giải trong trường hợp cần thiết.