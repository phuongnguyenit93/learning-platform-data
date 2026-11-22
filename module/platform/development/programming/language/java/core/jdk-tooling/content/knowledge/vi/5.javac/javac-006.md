# Biên dịch Java module bằng module path

## 1. Module path trong quy trình biên dịch là gì?

Java Platform Module System (JPMS), được đưa vào từ Java 9, cho phép ứng dụng chia mã thành các module có tên. Mỗi named module khai báo tên, các module phụ thuộc và những package được phép truy cập từ bên ngoài. Tệp `module-info.java` là module descriptor, mô tả hợp đồng đó.

Khi biên dịch một module, `javac` cần tìm được:

- Mã nguồn của module đang biên dịch.
- Các module mà module đó khai báo bằng `requires`.
- Các package được những module phụ thuộc `exports`.
- Các module nền tảng của JDK cần cho mã nguồn.

**Module path** là đường dẫn mà compiler dùng để tìm các module đã được biên dịch hoặc đóng gói. Tùy chọn chính là `--module-path` (viết tắt `-p`). Nó có thể chứa modular JAR và thư mục module đã biên dịch (exploded modules).

Module path ở giai đoạn biên dịch không tự cấu hình module path khi chạy ứng dụng. Lệnh `java` cũng cần nhận module path tương ứng khi khởi chạy.

Lệnh khái quát:

~~~bash
javac --module-path <module-path> -d <output-dir> <source-files>
~~~

Khi biên dịch nhiều module từ một cây thư mục nguồn, dùng thêm `--module-source-path` và `--module`:

~~~bash
javac --module-source-path <source-root> --module <module-name> -d <output-dir>
~~~

Không nên nhầm ba khái niệm:

| Đường dẫn | Mục đích |
|---|---|
| `--class-path` hoặc `-cp` | Tìm lớp và JAR thuộc classpath, thường nằm trong unnamed module. |
| `--module-path` hoặc `-p` | Tìm named modules đã biên dịch hoặc modular JAR. |
| `--module-source-path` | Tìm mã nguồn của nhiều module theo cấu trúc thư mục module. |

## 2. Module descriptor: `requires` và `exports`

Một module tối thiểu có thể khai báo như sau:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

Tên module là `com.example.greetings`. Chỉ package `com.example.greetings` được export để module khác có thể dùng các kiểu public trong package đó. Các package không được export vẫn được giữ kín đối với module khác theo quy tắc truy cập của JPMS.

Một module ứng dụng có thể khai báo phụ thuộc:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Các chỉ thị quan trọng:

- `requires module.name;` khai báo module hiện tại cần đọc module khác.
- `requires transitive module.name;` cho phép module phụ thuộc tiếp tục đọc module được yêu cầu thông qua quan hệ phụ thuộc này.
- `requires static module.name;` khai báo phụ thuộc cần lúc biên dịch nhưng có thể không bắt buộc lúc chạy.
- `exports package.name;` cho phép module khác truy cập các kiểu public trong package.
- `exports package.name to other.module;` chỉ export package cho một hoặc nhiều module được nêu tên.
- `opens package.name;` mở package cho truy cập reflection sâu lúc chạy; nó không thay thế `exports` cho việc biên dịch mã nguồn truy cập kiểu public.
- `uses` và `provides ... with ...` khai báo quan hệ sử dụng/cung cấp service.

Mọi module đều đọc được `java.base` mà không cần khai báo `requires java.base;` tường minh. Đây là module nền tảng chứa các kiểu cơ bản như `String`, `Object` và `System`.

## 3. Ví dụ hai module có phụ thuộc

Tạo cây thư mục nguồn theo tên module:

~~~text
project/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greetings/
    │               └── Greeting.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Module thư viện `com.example.greetings`:

Tệp `src/com.example.greetings/module-info.java`:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

Tệp `src/com.example.greetings/com/example/greetings/Greeting.java`:

~~~java
package com.example.greetings;

public class Greeting {
    public static String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module ứng dụng `com.example.app`:

Tệp `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Tệp `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greetings.Greeting;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java modules" : args[0];
        System.out.println(Greeting.message(name));
    }
}
~~~

Hai module có quan hệ rõ ràng: ứng dụng yêu cầu module thư viện, còn thư viện export package chứa API được dùng. Nếu bỏ `requires com.example.greetings;` hoặc bỏ `exports com.example.greetings;`, compiler sẽ báo lỗi vì module ứng dụng không có quyền đọc module hoặc không truy cập được package tương ứng.

## 4. Biên dịch nhiều module bằng `--module-source-path`

Với cây thư mục ở trên, chạy từ thư mục `project`:

~~~bash
javac --release 17 --module-source-path src -d out --module com.example.greetings,com.example.app
~~~

Giải thích:

- `--release 17` yêu cầu compiler kiểm tra theo ngôn ngữ, bytecode và API Java 17.
- `--module-source-path src` chỉ định thư mục gốc chứa các thư mục mã nguồn module.
- `-d out` đặt kết quả biên dịch vào thư mục `out`.
- `--module com.example.greetings,com.example.app` yêu cầu biên dịch hai module có tên đã liệt kê.

Cấu trúc kết quả có dạng:

~~~text
out/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── greetings/
│               └── Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Chạy module ứng dụng bằng Java launcher:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java modules!
~~~

Truyền đối số:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main "Ada Lovelace"
~~~

Stdout:

~~~text
Hello, Ada Lovelace!
~~~

Ở đây `out` là module path lúc chạy vì nó chứa hai thư mục module đã biên dịch. Tùy chọn `-m` chỉ định module chính và lớp có phương thức `main`. Tên lớp phải là tên đầy đủ, gồm package.

## 5. Biên dịch từng module theo thứ tự phụ thuộc

Một cách khác là biên dịch module thư viện trước, sau đó đưa thư mục output của thư viện lên module path khi biên dịch module ứng dụng.

Từ thư mục gốc `project`:

~~~bash
# Biên dịch module thư viện
javac --release 17 -d mods/com.example.greetings src/com.example.greetings/module-info.java src/com.example.greetings/com/example/greetings/Greeting.java

# Biên dịch module ứng dụng, dùng module thư viện đã biên dịch
javac --release 17 --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Chạy module ứng dụng
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java modules!
~~~

Cách này hữu ích khi build pipeline chia module thành các bước riêng, hoặc module thư viện đã được build và đóng gói trước. Đường dẫn `mods` chứa module đã biên dịch `com.example.greetings`; compiler có thể đọc module descriptor và các class public được export từ đó.

Khi biên dịch module ứng dụng, `--module-path mods` là cấu hình compile-time. Khi chạy, cần truyền lại module path cho launcher như ví dụ cuối. Chỉ khai báo module path trong lệnh `javac` không khiến JVM tự biết vị trí module khi chạy.

## 6. Biên dịch module phụ thuộc một modular JAR bên ngoài

Trong dự án thực tế, module phụ thuộc có thể được phân phối dưới dạng JAR. Giả sử thư mục `lib` chứa `com.example.greetings.jar`, một modular JAR có `module-info.class`.

Có thể biên dịch module ứng dụng như sau:

~~~bash
javac --release 17 --module-path lib -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

Và chạy:

~~~bash
java --module-path "out:lib" -m com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách giữa các phần tử đường dẫn là dấu chấm phẩy:

~~~powershell
java --module-path "out;lib" -m com.example.app/com.example.app.Main
~~~

Tên module được khai báo trong `module-info.java` của thư viện phải khớp với tên trong chỉ thị `requires`. Tên tệp JAR không quyết định tên của một explicit named module khi JAR đã có module descriptor.

Có thể xem module descriptor của JAR bằng:

~~~bash
jar --describe-module --file lib/com.example.greetings.jar
~~~

Nếu compiler báo không tìm thấy module, hãy xác nhận JAR nằm trực tiếp trong một phần tử module path hợp lệ, module descriptor khai báo đúng tên, và tên trong `requires` trùng với tên module thực tế.

## 7. Module path và classpath khác nhau thế nào?

Classpath và module path giải quyết hai mô hình đóng gói khác nhau:

| Đặc điểm | Classpath | Module path |
|---|---|---|
| Đơn vị tổ chức | Lớp và package | Named module |
| Mô tả phụ thuộc | Thường do build tool hoặc người chạy cung cấp | Khai báo trong `module-info.java` bằng `requires` |
| Phạm vi package | Không có quy tắc encapsulation module | Chỉ package được export mới là API cho module khác |
| Tên module | Các lớp trên classpath thuộc unnamed module | Module có tên xác định |
| Cách chỉ định khi chạy | `java -cp ... package.Main` | `java -p ... -m module/package.Main` |
| Tính tương thích | Phù hợp nhiều thư viện Java cũ | Phù hợp ứng dụng/thư viện đã modular hóa |

Một named module không tự động đọc được unnamed module trên classpath. Khi buộc phải dùng thư viện cũ đặt trên classpath, có thể thêm cạnh đọc tạm thời bằng `--add-reads module.name=ALL-UNNAMED`. Cách bền vững hơn là dùng modular JAR hoặc automatic module khi thư viện hỗ trợ, và quản lý rõ ràng phiên bản phụ thuộc.

Không nên trộn đường dẫn theo suy đoán. Nếu một thư viện được đặt trên classpath, nó không trở thành named module chỉ vì ứng dụng có `module-info.java`. Nếu đặt một JAR không có module descriptor lên module path, compiler có thể xử lý nó như automatic module với các quy tắc tương thích riêng.

## 8. Automatic module và thư viện chưa modular hóa

Một JAR chưa có `module-info.class` có thể được đưa lên module path như một automatic module. Tên module tự động có thể lấy từ thuộc tính `Automatic-Module-Name` trong manifest; nếu không có, tên thường được suy ra từ tên tệp JAR. Tên suy ra có thể thay đổi khi đổi tên tệp hoặc phiên bản, vì vậy không nên phụ thuộc vào nó nếu có lựa chọn tốt hơn.

Automatic module thường export tất cả package và đọc các named module khác để hỗ trợ chuyển đổi dần từ classpath sang JPMS. Tuy vậy, đây là cơ chế tương thích, không thay thế một module descriptor được thiết kế rõ ràng.

Kiểm tra JAR:

~~~bash
jar --describe-module --file lib/legacy-library.jar
~~~

Khi dùng một automatic module, chỉ thị `requires` trong module ứng dụng phải dùng đúng tên module mà công cụ báo. Đối với thư viện do nhóm phát triển kiểm soát, nên khai báo `Automatic-Module-Name` ổn định hoặc chuyển thư viện sang modular JAR khi phù hợp.

Một số lưu ý:

- JAR trên classpath thuộc unnamed module; JAR trên module path có thể trở thành automatic module.
- Automatic module không cung cấp mức đóng gói package chặt như explicit named module.
- Không nên đoán tên module từ tên artifact Maven/Gradle; hãy kiểm tra bằng `jar --describe-module` hoặc tài liệu của thư viện.
- Kiểm thử cả compile-time và runtime sau khi chuyển thư viện từ classpath sang module path.

## 9. Các tùy chọn `javac` liên quan đến module

| Tùy chọn | Ý nghĩa và trường hợp sử dụng |
|---|---|
| `--module-path path` hoặc `-p path` | Đặt đường dẫn tìm application modules và thư viện module. |
| `--module-source-path path` | Đặt đường dẫn gốc chứa mã nguồn của nhiều module theo cấu trúc module. |
| `--module name` hoặc `-m name` | Chỉ định module cần biên dịch; có thể liệt kê nhiều module cách nhau bằng dấu phẩy. |
| `--add-modules name` | Thêm module gốc vào quá trình phân giải; hỗ trợ `ALL-MODULE-PATH` để thêm các module trên module path. |
| `--limit-modules name` | Giới hạn tập module mà compiler có thể quan sát. |
| `--add-reads module=other` | Thêm quan hệ đọc giữa hai module, thường dùng để tương thích hoặc chẩn đoán. |
| `--add-exports module/package=target` | Tạm export một package cho module đích; có thể dùng `ALL-UNNAMED` cho unnamed modules. |
| `--patch-module module=path` | Bổ sung hoặc thay thế class/resource trong một module khi biên dịch, chủ yếu dùng cho kiểm thử hoặc tình huống đặc biệt. |
| `--upgrade-module-path path` | Cung cấp module thay thế cho các module có thể nâng cấp của hệ thống; ít dùng trong build ứng dụng thông thường. |
| `--module-version version` | Ghi phiên bản module cho các module đang biên dịch. |
| `--processor-module-path path` | Đặt module path riêng cho annotation processors. |

Một vài ví dụ:

~~~bash
# Thêm module gốc cần phân giải từ module path
javac --module-path lib --add-modules com.example.optional -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Tạm cho module ứng dụng đọc unnamed module trên classpath
javac --module-path lib --class-path legacy.jar --add-reads com.example.app=ALL-UNNAMED -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Tạm export package nội bộ cho một module cụ thể
javac --add-exports java.base/sun.nio.ch=com.example.app -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

`--add-reads` và `--add-exports` là các điều chỉnh cho đồ thị module trong lúc biên dịch. Nếu ứng dụng cũng cần hành vi đó lúc chạy, phải truyền cấu hình tương ứng cho Java launcher. Đặc biệt, việc export package nội bộ của JDK có thể phụ thuộc implementation và không phải API công khai ổn định; ưu tiên API chuẩn thay vì phụ thuộc package nội bộ.

`--patch-module` cũng cần được cân nhắc ở cả compile-time và runtime nếu cùng một phần mã được biên dịch và chạy theo cấu hình patch. Không dùng các tùy chọn này để che giấu lỗi thiết kế module trong ứng dụng bình thường.

## 10. Kết hợp `--release`, cảnh báo và module path

`--release 17` giúp build bằng JDK mới hơn nhưng giới hạn mã nguồn, bytecode và API theo Java 17. Đây thường là lựa chọn rõ ràng hơn so với đặt riêng `-source 17` và `-target 17`.

Ví dụ:

~~~bash
javac --release 17 -Xlint:all -Werror --module-path lib -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

- `-Xlint:all` bật các cảnh báo compiler phổ biến.
- `-Werror` khiến cảnh báo trở thành lỗi, hữu ích trong CI khi dự án đã xử lý cảnh báo hiện có.
- `--module-path lib` giúp compiler phân giải các module phụ thuộc.
- `-d out` đặt class file và module descriptor đầu ra vào thư mục build.

Nếu bật `-Werror` cho một dự án cũ, trước tiên nên xử lý các cảnh báo hiện tại để tránh build thất bại do cảnh báo không liên quan đến thay đổi mới.

Có thể yêu cầu compiler in chi tiết hoạt động bằng `-verbose` hoặc bật cảnh báo liên quan đến module bằng `-Xlint:module` khi cần chẩn đoán. Dùng `javac --help` và `javac --help-extra` của đúng JDK trong môi trường build để kiểm tra tùy chọn được phiên bản đó hỗ trợ.

## 11. Cách đọc và xử lý lỗi module path

| Thông báo/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `module not found: com.example.lib` | Module không có trên module path hoặc tên trong `requires` sai. | Kiểm tra đường dẫn, nội dung JAR/module descriptor và tên module thực tế. |
| `package ... is not visible` | Package không được module chứa nó export cho module gọi. | Thêm `exports` đúng package trong module cung cấp API, hoặc dùng API công khai khác. |
| `module ... does not read ...` | Module ứng dụng chưa khai báo phụ thuộc cần thiết. | Thêm `requires` vào module descriptor. |
| `package ... does not exist` | Package không nằm trong module path/classpath phù hợp hoặc đường dẫn nguồn sai. | Phân biệt nguồn module với thư viện phụ thuộc; kiểm tra `--module-source-path` và `--module-path`. |
| `not in a module on the module source path` | Cấu trúc thư mục nguồn không khớp với tên module hoặc compiler không nhận được module source path. | Đặt mã nguồn dưới thư mục có tên module và dùng `--module-source-path` đúng gốc. |
| Module được tìm thấy lúc compile nhưng không tìm thấy lúc run | Chỉ cấu hình module path cho `javac`, chưa cấu hình cho `java`. | Truyền module path vào lệnh launcher khi chạy. |
| Module path có nhiều bản JAR cùng module | Dependency trùng hoặc phiên bản không nhất quán. | Loại bỏ bản trùng và cố định dependency trong build tool. |
| Chạy được trên máy phát triển nhưng CI báo thiếu module | CI dùng JDK, thư mục build hoặc dependency khác. | Cố định JDK/toolchain, cache dependency đúng cách và in cấu hình module path khi chẩn đoán. |

Một quy trình chẩn đoán có thứ tự:

1. Xem phiên bản compiler bằng `javac --version`.
2. Xác nhận module descriptor có đúng tên và chỉ thị `requires`/`exports`.
3. Xác nhận module path có chứa đúng modular JAR hoặc exploded module.
4. Nếu biên dịch nhiều module từ nguồn, kiểm tra cấu trúc và `--module-source-path`.
5. Chạy `jar --describe-module` với JAR phụ thuộc để biết tên module thực tế.
6. Xác nhận lệnh `java` lúc runtime dùng cùng tập module cần thiết.
7. Kiểm tra các JAR trùng phiên bản hoặc thư viện cũ được đưa nhầm lên classpath/module path.

## 12. Tích hợp module path với Maven, Gradle và CI

Trong dự án dùng Maven hoặc Gradle, build tool thường quản lý dependency, thứ tự biên dịch và tham số compiler. Khi dự án có `module-info.java`, cần bảo đảm các dependency cần thiết được phân giải theo mô hình module phù hợp và compiler được cấu hình dùng đúng JDK.

Các nguyên tắc thực tế:

- Cố định JDK/toolchain và phiên bản Java đích trong cấu hình build.
- Dùng `--release 17` khi sản phẩm phải tương thích Java 17.
- Không tự ghép classpath và module path theo một chuỗi khó kiểm soát; để build tool quản lý dependency nếu dự án đã dùng Maven/Gradle.
- Kiểm tra module name của thư viện bên ngoài, đặc biệt với automatic modules.
- Chạy build sạch trong CI để tránh class file cũ che giấu lỗi dependency.
- Giữ lệnh compile và run nhất quán: module được tìm thấy lúc compile cũng phải được cung cấp khi chạy hoặc đóng gói.
- Nếu có annotation processor, kiểm tra riêng `--processor-module-path` hoặc đường dẫn processor mà build tool cấu hình.

Khi build thất bại, nên lấy lệnh compiler thực tế từ log Maven/Gradle. Việc nhìn vào cấu hình dependency tổng quát mà không kiểm tra lệnh cuối cùng có thể bỏ sót khác biệt giữa classpath và module path.

## 13. Checklist biên dịch module

- Mỗi named module có `module-info.java` với tên duy nhất và đúng.
- Package được module khác dùng đã được `exports`.
- Module descriptor của ứng dụng có `requires` cho từng module cần đọc.
- Mã nguồn nhiều module được đặt theo cấu trúc phù hợp với `--module-source-path`.
- Modular JAR và exploded module cần thiết đã nằm trên `--module-path`.
- Dùng `--module` để chọn đúng module cần biên dịch khi có nhiều module nguồn.
- Dùng `--release` để cố định API và bytecode mục tiêu.
- Module path runtime được cấu hình trong lệnh `java` hoặc cấu hình đóng gói.
- Không đưa thư viện legacy lên nhầm path; kiểm tra automatic module name khi dùng JAR cũ trên module path.
- Đã kiểm tra stdout và exit code của chương trình sau khi biên dịch thành công.

Khi biên dịch ứng dụng JPMS, hãy khai báo quan hệ bằng `requires`/`exports`, đặt các module phụ thuộc lên `--module-path` và dùng `--module-source-path` khi biên dịch nhiều module từ một cây mã nguồn. Sau khi compiler tạo module output, truyền output đó vào module path của Java launcher để chạy module ứng dụng.
