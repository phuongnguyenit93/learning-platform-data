# Đóng gói modular JAR và chạy bằng java -m

Sau khi compile một module, output thường là một thư mục chứa `module-info.class`, các class Java và resource. Để phân phối module, có thể đóng gói thư mục đó thành **modular JAR** bằng công cụ `jar`. Khi chạy, đặt các modular JAR trên module path và dùng `java -m` (hoặc `java --module`) để khởi chạy module.

Khác với một JAR thông thường chỉ chứa class/resource, modular JAR có module descriptor ở gốc archive. Descriptor xác định module name, dependency, package được export/open và service metadata. Nhờ đó Java launcher có thể resolve module graph trước khi gọi main class.

Bài này xây dựng ứng dụng gồm hai module: `com.acme.greeter` cung cấp API và `com.acme.app` sử dụng API đó.

## 1. Cấu trúc source của ứng dụng

Tạo cấu trúc:

~~~text
project/
├── src/
│   ├── com.acme.greeter/
│   │   ├── module-info.java
│   │   └── com/acme/greeter/api/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── out/
└── mods/
~~~

Tên thư mục module trong source path tương ứng với tên module khai báo trong descriptor.

Module API `com.acme.greeter`:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
~~~

File `src/com.acme.greeter/com/acme/greeter/api/Greeter.java`:

~~~java
package com.acme.greeter.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module ứng dụng `com.acme.app`:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.greeter.api.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JPMS" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

Quan hệ giữa hai module:

- `com.acme.greeter` export package chứa API public.
- `com.acme.app` khai báo `requires com.acme.greeter`.
- Ứng dụng chỉ cần biết module API; không cần copy class của Greeter vào module app.

## 2. Compile các module

Từ thư mục gốc `project`, compile hai module:

~~~bash
javac --module-source-path src -d out --module com.acme.greeter,com.acme.app
~~~

Có thể dùng dạng viết tắt:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app
~~~

Javac tìm source module trong `src`, resolve dependency giữa hai module và ghi class file vào `out`.

Kết quả:

~~~text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Mỗi module có một thư mục output riêng. File `module-info.class` nằm ở gốc thư mục module, sẵn sàng được đưa vào gốc modular JAR.

Nếu muốn compile dependency trước và app sau:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter
javac --module-path out --module-source-path src -d out -m com.acme.app
~~~

Cách thứ hai dùng output module đã compile làm module path. Cả hai cách đều tạo module output có thể đóng gói.

## 3. Đóng gói từng module thành modular JAR

Tạo thư mục lưu archive:

~~~bash
mkdir -p mods
~~~

Đóng gói module API:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
~~~

Đóng gói module ứng dụng:

~~~bash
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
~~~

Tùy chọn:

- `--create` hoặc `-c`: tạo archive mới.
- `--file` hoặc `-f`: chỉ định file JAR đầu ra.
- `-C <directory> .`: chuyển vào thư mục chỉ định rồi thêm toàn bộ nội dung từ thư mục đó vào archive.

Điểm quan trọng là thư mục `out/com.acme.greeter` và `out/com.acme.app` đều chứa `module-info.class` ở gốc. Lệnh `-C ... .` giữ descriptor ở gốc archive, không đặt nó trong một thư mục con.

Kết quả:

~~~text
mods/
├── com.acme.greeter.jar
└── com.acme.app.jar
~~~

Hai modular JAR độc lập có thể được phân phối cùng nhau. Module app vẫn tham chiếu module API qua tên trong `requires`, không qua đường dẫn file JAR cố định.

## 4. Tạo executable modular JAR với main class metadata

Có thể ghi main class vào metadata module khi tạo JAR ứng dụng:

~~~bash
jar --create   --file mods/com.acme.app.jar   --main-class com.acme.app.Main   -C out/com.acme.app .
~~~

Tùy chọn `--main-class` (hoặc `-e`) chỉ định entry point của module. Với modular JAR, thông tin main class được ghi vào module descriptor của archive. Nhờ vậy launcher có thể xác định main class khi chỉ truyền module name.

Nếu module descriptor đã có main class metadata phù hợp, không cần chỉ định lại trong lệnh tạo JAR.

Có hai cách chạy:

- Chỉ rõ main class: `java -m com.acme.app/com.acme.app.Main`.
- Dùng main class đã ghi trong descriptor: `java -m com.acme.app`.

Cách thứ hai yêu cầu descriptor của module có main class. Nếu không có metadata đó, launcher sẽ yêu cầu chỉ định class sau dấu gạch chéo.

## 5. Kiểm tra modular JAR

Dùng `jar --list` để xem entry:

~~~bash
jar --list --file mods/com.acme.greeter.jar
~~~

Một modular JAR đúng cấu trúc sẽ có các entry tương tự:

~~~text
META-INF/
META-INF/MANIFEST.MF
module-info.class
com/acme/greeter/api/Greeter.class
~~~

Kiểm tra descriptor:

~~~bash
jar --describe-module --file mods/com.acme.greeter.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Output rút gọn có thể cho biết:

~~~text
com.acme.greeter
exports com.acme.greeter.api
requires java.base mandated
~~~

Và module app:

~~~text
com.acme.app
requires com.acme.greeter
requires java.base mandated
~~~

Nếu đã dùng `--main-class`, output mô tả module app sẽ thể hiện main class tương ứng. Đây là cách xác nhận metadata được ghi vào JAR.

Có thể yêu cầu launcher mô tả module trên module path:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

Nếu lệnh không tìm thấy module, kiểm tra module path có trỏ đúng thư mục chứa các JAR hay không và descriptor có tên module như mong đợi hay không.

## 6. Chạy ứng dụng bằng java -m

Từ thư mục gốc dự án:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Cú pháp viết ngắn:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, JPMS!
~~~

Truyền đối số cho main class:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main "Java Modules"
~~~

Kết quả:

~~~text
Hello, Java Modules!
~~~

Nếu JAR app đã có main class metadata:

~~~bash
java -p mods -m com.acme.app
~~~

Launcher sẽ lấy main class từ descriptor. Nếu module không khai báo main class, hãy dùng cú pháp đầy đủ `module/main-class`.

Trên Windows PowerShell, các lệnh tương tự:

~~~powershell
java --module-path mods --module com.acme.app/com.acme.app.Main
java -p mods -m com.acme.app "Java Modules"
~~~

Dấu phân cách module path khi có nhiều thư mục là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS. Trong ví dụ, chỉ có một thư mục `mods`, nên không cần ghép nhiều path.

## 7. Cách Java launcher resolve các modular JAR

Khi chạy:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

launcher thực hiện các bước chính:

1. Tìm module `com.acme.app` trên module path.
2. Đọc `module-info.class` để biết module name, dependency và metadata.
3. Resolve `requires com.acme.greeter`.
4. Tìm `com.acme.greeter` trong cùng module path.
5. Resolve dependency nền tảng như `java.base`.
6. Kiểm tra module graph và quyền truy cập package.
7. Nạp main class và gọi `main(String[] args)`.

Module path chứa các named module. Launcher không cần biết trước tên file JAR của dependency nếu module name trong descriptor đã được xác định. Đây là khác biệt quan trọng so với cách quản lý classpath bằng một danh sách file JAR.

Có thể xem graph lúc khởi chạy:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

Output giúp xác định root module, dependency được resolve và vị trí module được tìm thấy.

## 8. Phân biệt modular JAR với executable JAR trên classpath

Một JAR có thể là:

- **JAR thông thường**: không có module descriptor; khi chạy trên classpath, class thuộc unnamed module.
- **Modular JAR**: có `module-info.class` ở gốc archive; có tên module và khai báo dependency.
- **Executable modular JAR**: modular JAR có main class metadata để launcher biết entry point.

Với ứng dụng modular nhiều dependency, cách chạy rõ ràng là:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Đừng nhầm `java -m` với `java -jar`:

- `-m` / `--module` yêu cầu launcher khởi chạy một named module trên module path.
- `-jar` khởi chạy JAR theo chế độ executable JAR và manifest entry point; không phải cách thay thế tương đương cho việc resolve một module graph gồm nhiều named module trên module path.

Khi mục tiêu là thực hành JPMS, dùng `-m` để thể hiện rõ module name, main class và module path.

## 9. Cập nhật modular JAR khi source thay đổi

Khi code thay đổi, compile lại module và tạo lại archive. Không nên sửa class trong JAR bằng cách chép file thủ công nếu muốn quy trình build có thể tái lập.

Ví dụ:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app

jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Lệnh `jar --create` yêu cầu file đích được tạo mới; nếu file đã tồn tại, xóa hoặc thay thế nó theo quy trình build có kiểm soát trước khi tạo lại. Có thể dùng `jar --update` cho một số cập nhật archive, nhưng thay đổi module descriptor/main class nên được thực hiện qua build đầu vào phù hợp và kiểm tra lại bằng `jar --describe-module`.

Sau khi đóng gói, kiểm tra timestamp/hash của JAR nếu cần xác nhận runtime đang dùng đúng artifact mới. Module path có thể trỏ nhầm một thư mục build cũ dù source đã thay đổi.

## 10. Tổ chức thư mục phân phối

Một layout triển khai đơn giản:

~~~text
distribution/
├── app/
│   └── com.acme.app.jar
└── lib/
    └── com.acme.greeter.jar
~~~

Khi đó chạy:

~~~bash
java --module-path "app:lib" --module com.acme.app/com.acme.app.Main
~~~

Trên Windows:

~~~powershell
java --module-path "app;lib" --module com.acme.app/com.acme.app.Main
~~~

Có thể phân phối nhiều modular JAR trong một thư mục chung để đơn giản hóa:

~~~text
distribution/
└── mods/
    ├── com.acme.app.jar
    └── com.acme.greeter.jar
~~~

Sau đó:

~~~bash
java -p mods -m com.acme.app
~~~

Lợi ích của cấu trúc này là dependency có thể được thay thế độc lập nếu giữ module name và contract tương thích. Tuy nhiên, không đặt hai phiên bản cùng module name trong cùng module path; điều đó làm module resolution mơ hồ hoặc thất bại.

## 11. Lỗi thường gặp và cách xử lý

**Module not found.** Kiểm tra `--module-path` trỏ tới thư mục chứa JAR, không phải trỏ vào một file JAR đơn lẻ nếu bạn định dùng nhiều dependency. Kiểm tra tên module trong descriptor bằng `jar --describe-module`.

**Package is not visible.** Module API chưa export package cần dùng, hoặc app chưa khai báo `requires` module API. Kiểm tra descriptor của cả hai module.

**Không tìm thấy main class khi chạy `java -m com.acme.app`.** Module descriptor chưa có main class metadata. Chạy rõ `java -m com.acme.app/com.acme.app.Main` hoặc tạo lại modular JAR với `jar --main-class`.

**JAR không phải modular JAR.** Có thể `module-info.class` không nằm ở gốc archive. Dùng `jar --list --file` để xác nhận entry. Nếu descriptor bị đặt dưới thư mục con, launcher sẽ không nhận nó như module descriptor của JAR.

**Module name khác tên file.** Module name nằm trong descriptor hoặc được suy ra theo quy tắc automatic module. Không đổi tên file để giả định tên module đã đổi; kiểm tra bằng `jar --describe-module`.

**Chạy được trong IDE nhưng không chạy từ terminal.** IDE có thể tự cấu hình module path, working directory và runtime JDK. Chạy lại với command line rõ ràng, đúng JDK và đúng thư mục distribution.

**Thay JAR nhưng app vẫn dùng phiên bản cũ.** Kiểm tra module path có thư mục trùng hoặc artifact cũ đứng trước trong cấu hình. Dùng `--show-module-resolution` để xem module location.

**Dùng `java -jar` cho ứng dụng nhiều module rồi thiếu dependency.** `-jar` không thay thế module path graph của `-m`. Chạy ứng dụng modular bằng `--module-path` và `--module`.

## 12. Thực hành

1. Tạo hai module `com.acme.greeter` và `com.acme.app` theo ví dụ.
2. Compile cả hai bằng `javac --module-source-path src -d out -m com.acme.greeter,com.acme.app`.
3. Đóng gói từng module thành modular JAR trong thư mục `mods`.
4. Dùng `jar --list` để xác nhận `module-info.class` nằm ở gốc từng JAR.
5. Dùng `jar --describe-module` để đọc `requires`, `exports` và main class metadata.
6. Chạy bằng `java -p mods -m com.acme.app/com.acme.app.Main`.
7. Tạo lại JAR app với `--main-class`, sau đó thử chạy chỉ bằng `java -p mods -m com.acme.app`.
8. Thử bỏ `requires com.acme.greeter` hoặc bỏ `exports com.acme.greeter.api`; quan sát lỗi compile/resolution và khôi phục descriptor.
9. Bật `--show-module-resolution` để xem module nào được chọn và từ vị trí nào.
10. Chép thư mục `mods` sang một thư mục distribution mới và chạy ứng dụng từ đó để kiểm tra tính độc lập với source tree.

Khi phân phối ứng dụng modular, hãy giữ `module-info.class` ở gốc mỗi modular JAR, bảo đảm dependency nằm trên module path và khởi chạy bằng `java -m`. Nếu muốn bỏ qua tên main class trong lệnh chạy, ghi entry point vào descriptor bằng `jar --main-class`. Quy trình compile, package, inspect và launch như trên giúp kiểm tra module graph rõ ràng trước khi triển khai.
