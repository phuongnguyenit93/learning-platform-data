# Biên dịch ứng dụng Java bằng javac

## 1. javac dùng để làm gì?

`javac` là trình biên dịch đi kèm JDK. Nó đọc mã nguồn Java trong các file `.java`, kiểm tra cú pháp, kiểu dữ liệu, quyền truy cập và các tham chiếu giữa class, rồi tạo bytecode trong file `.class` để JVM chạy.

Một quy trình Java cơ bản có các bước:

1. Viết source code và sắp xếp theo package.
2. Dùng `javac` biên dịch source thành class file.
3. Đưa resource và dependency cần thiết vào vùng đầu ra hoặc classpath.
4. Dùng `java` chạy main class hoặc đóng gói bằng `jar`.
5. Kiểm thử artifact trên runtime mục tiêu.

`javac` chỉ biên dịch source. Nó không tự đóng gói thư viện bên ngoài, không tự copy resource và không tạo installer. Những việc đó thuộc bước chuẩn bị classpath, đóng gói JAR hoặc công cụ build/phân phối khác.

## 2. Kiểm tra JDK trước khi compile

Kiểm tra compiler và runtime:

~~~bash
java --version
javac --version
jar --version
~~~

Ba lệnh có thể vô tình trỏ tới các JDK khác nhau nếu máy cài nhiều phiên bản. Trên Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

Hãy xác nhận java và javac đến từ JDK dự định dùng. Với ứng dụng cần chạy trên Java 17, có thể dùng JDK 17 hoặc JDK mới hơn cùng `--release 17` để tạo class file tương thích Java 17.

## 3. Cấu trúc source và package

Tên package trong source phải khớp với thư mục chứa file. Ví dụ:

~~~text
javac-demo/
  src/
    main/
      java/
        com/
          example/
            app/
              Main.java
              Formatter.java
      resources/
        app.properties
  build/
    classes/
  dist/
~~~

Nếu source khai báo:

~~~java
package com.example.app;
~~~

thì file nên nằm dưới thư mục `com/example/app/`. Đường dẫn này giúp compiler và công cụ khác tìm đúng class theo tên đầy đủ `com.example.app.Main`.

Quy ước thường dùng:

- Package viết chữ thường, các phần phân cách bằng dấu chấm.
- Tên public class khớp với tên file, ví dụ Main nằm trong Main.java.
- Source đặt riêng với class file đầu ra.
- Resource đặt ở vùng riêng rồi copy vào classpath output khi build.

Có thể biên dịch một file Java không khai báo package, nhưng ứng dụng có cấu trúc rõ ràng nên dùng package để tránh trùng tên và quản lý quyền truy cập.

## 4. Chương trình Java nhỏ nhất

Tạo file `src/HelloWorld.java`:

~~~java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Biên dịch:

~~~bash
javac HelloWorld.java
~~~

Compiler tạo file `HelloWorld.class` trong cùng thư mục vì chưa chỉ định output directory. Chạy bằng tên class, không thêm phần mở rộng `.class`:

~~~bash
java HelloWorld
~~~

Stdout chính xác:

~~~text
Hello, Java!
~~~

Trong ứng dụng thật, nên dùng `-d` để class file không nằm lẫn với source.

## 5. Biên dịch nhiều source file cùng lúc

`javac` có thể biên dịch nhiều source file trong một lần gọi. Các file được xử lý như một nhóm nên compiler có thể giải quyết tham chiếu giữa các khai báo trong nhóm, không cần đoán thứ tự biên dịch.

Ví dụ `Formatter.java`:

~~~java
package com.example.app;

public final class Formatter {
    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

File `Main.java`:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Formatter.greet(name));
    }
}
~~~

Từ thư mục gốc project, biên dịch cả hai file:

~~~bash
javac --release 17 -d build/classes \
  src/main/java/com/example/app/Main.java \
  src/main/java/com/example/app/Formatter.java
~~~

Chạy:

~~~bash
java -cp build/classes com.example.app.Main Linh
~~~

Stdout:

~~~text
Hello, Linh
~~~

Không cần biên dịch `Formatter.java` trước `Main.java` nếu truyền cả hai file trong cùng lệnh. Nếu chỉ truyền `Main.java`, hãy chỉ định source path hoặc bảo đảm compiler có thể tìm thấy source/class phụ thuộc.

## 6. Chọn thư mục class file bằng -d

Dùng `-d` để chỉ định destination directory:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/app/Main.java
~~~

Nếu package là `com.example.app`, output được tạo theo cấu trúc:

~~~text
build/classes/
  com/
    example/
      app/
        Main.class
~~~

`javac` tạo thư mục đích và các thư mục package cần thiết nếu chưa có. Tách output giúp:

- Source không bị lẫn với file build.
- Dễ copy resource vào classpath.
- Dễ tạo JAR từ đúng tập tin đã biên dịch.
- Có thể xóa output cũ trước khi build lại.
- Dễ kiểm tra artifact và cấu hình CI.

Nếu bỏ `-d`, class file được đặt cạnh source file. Điều này phù hợp với thử nghiệm nhỏ, nhưng không nên dùng làm quy trình build của ứng dụng nhiều package.

## 7. Chọn Java release tương thích bằng --release

Nếu dùng JDK mới để build nhưng sản phẩm cần chạy trên Java cũ hơn, hãy đặt `--release`.

Ví dụ compile bằng JDK 24 nhưng target Java 17:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/app/Main.java
~~~

`--release 17` đồng thời kiểm soát:

- Quy tắc ngôn ngữ Java được chấp nhận ở release 17.
- Major version của class file đầu ra tương thích Java 17.
- Bộ API Java/JDK mà source được phép tham chiếu theo release 17.

Không chỉ dùng `-source 17 -target 17` rồi cho rằng API đã tương thích. Hai option đó điều khiển cú pháp và định dạng class file; khi compile trên JDK mới, source vẫn có thể tham chiếu API chỉ xuất hiện ở JDK mới. `--release` giới hạn cả API của release đích.

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lệnh. Kiểm tra class file sau khi compile:

~~~bash
javap -verbose -classpath build/classes com.example.app.Main
~~~

Với Java 17, dòng quan trọng là:

~~~text
major version: 61
~~~

Chọn release thấp nhất mà ứng dụng thực sự cần hỗ trợ. `--release` không thể làm dependency bên ngoài trở nên tương thích với Java cũ; từng JAR trong runtime classpath cũng phải hỗ trợ baseline đó.

## 8. Chỉ định encoding cho source

Nên chỉ định UTF-8 tường minh để build cho kết quả nhất quán giữa Windows, Linux, macOS và CI:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

Nếu bỏ `-encoding`, compiler dùng bộ chuyển đổi ký tự mặc định của môi trường. Một source có tiếng Việt hoặc ký tự ngoài ASCII có thể compile khác nhau giữa các máy nếu encoding mặc định không giống nhau.

Lưu ý: `-encoding` điều khiển cách đọc file source. Nó không quyết định encoding của mọi file resource hoặc dữ liệu runtime. Resource phải được đọc theo encoding mà ứng dụng quy định.

## 9. Đưa thư viện bên ngoài vào classpath

Nếu source sử dụng class từ JAR không thuộc JDK, compiler cần biết vị trí thư viện qua classpath.

Giả sử có dependency:

~~~text
lib/
  greeting-api.jar
~~~

Biên dịch ứng dụng:

~~~bash
javac --release 17 \
  -cp lib/greeting-api.jar \
  -d build/app-classes \
  src/main/java/com/example/app/Main.java
~~~

`-cp` là dạng viết tắt của `--class-path`. Có thể truyền nhiều thư mục/JAR trong một classpath. Ký tự phân cách phụ thuộc hệ điều hành:

| Hệ điều hành | Ví dụ classpath |
|---|---|
| Windows | `build/app-classes;lib/greeting-api.jar` |
| Linux/macOS | `build/app-classes:lib/greeting-api.jar` |

Đặt classpath trong dấu nháy khi có khoảng trắng hoặc khi shell có thể diễn giải ký tự đặc biệt. Nên chỉ định `-cp` rõ ràng thay vì phụ thuộc biến môi trường `CLASSPATH`.

Classpath lúc compile và lúc chạy là hai cấu hình riêng. Sau khi compile, JVM vẫn cần tìm dependency:

Windows:

~~~powershell
java -cp "build/app-classes;lib/greeting-api.jar" com.example.app.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/app-classes:lib/greeting-api.jar" com.example.app.Main
~~~

Nếu quên JAR dependency lúc chạy, chương trình có thể compile thành công nhưng lỗi `NoClassDefFoundError` hoặc `ClassNotFoundException`.

## 10. Phân biệt classpath và module path

Hai đường dẫn phục vụ hai kiểu tổ chức code:

- **Classpath (`-cp` hoặc `--class-path`):** tìm class và JAR theo package. Đây là cách phổ biến với ứng dụng classpath truyền thống.
- **Module path (`-p` hoặc `--module-path`):** tìm các module có module descriptor hoặc module tự động. Module khai báo dependency và package export bằng `module-info.java`.

Nếu dependency là modular JAR, có thể đặt nó trên module path. Nếu ứng dụng chưa dùng Java Platform Module System, tiếp tục dùng classpath là hợp lệ.

Không trộn classpath và module path tùy tiện để che lỗi dependency. Hãy xác định ứng dụng đang dùng unnamed module hay named module và cấu hình theo đúng mô hình.

## 11. Dùng source path cho source phụ thuộc chưa liệt kê

Nếu chỉ đưa `Main.java` vào command line nhưng source tham chiếu một class khác chưa được compile, `--source-path` cho biết nơi compiler có thể tìm source phụ thuộc.

Ví dụ:

~~~bash
javac --release 17 \
  --source-path src/main/java \
  -d build/classes \
  src/main/java/com/example/app/Main.java
~~~

Compiler có thể tìm `Formatter.java` tại:

~~~text
src/main/java/com/example/app/Formatter.java
~~~

Source path phải tổ chức theo package hierarchy. Nếu muốn chắc chắn chính xác những file nào được biên dịch, liệt kê tất cả source file trên command line hoặc dùng argument file.

`--source-path` dùng cho source bổ sung của package-oriented compilation. Khi biên dịch nhiều module, dùng `--module-source-path`.

## 12. Copy resource vào output directory

`javac` chỉ tạo class file và output do annotation processor sinh ra. Nó không tự copy các file như `.properties`, `.xml`, ảnh hoặc template.

Ví dụ resource:

~~~text
src/main/resources/app.properties
~~~

Nội dung:

~~~properties
banner=READY javac
~~~

Sau khi compile, copy resource vào classpath output.

PowerShell:

~~~powershell
Copy-Item src/main/resources/* build/classes/ -Recurse
~~~

Linux/macOS:

~~~bash
cp -R src/main/resources/. build/classes/
~~~

Trong Java, đọc resource bằng classloader:

~~~java
try (InputStream in = Main.class.getResourceAsStream("/app.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    Properties properties = new Properties();
    properties.load(in);
}
~~~

Đường dẫn resource tính từ root của classpath/JAR. Khi đóng gói JAR, hãy đưa resource vào cùng cấu trúc output để runtime tìm thấy.

## 13. Đóng gói class file thành executable JAR

Sau khi biên dịch và copy resource, có thể đóng gói thành JAR:

~~~bash
jar --create \
  --file dist/hello-app.jar \
  --main-class com.example.app.Main \
  -C build/classes .
~~~

Tạo thư mục `dist` trước khi chạy lệnh nếu thư mục chưa tồn tại. `-C build/classes .` yêu cầu `jar` chuyển vào thư mục `build/classes` rồi thêm nội dung của thư mục đó vào archive.

Chạy JAR:

~~~bash
java -jar dist/hello-app.jar Linh
~~~

Stdout:

~~~text
READY javac: Hello, Linh
~~~

Có thể xem nội dung JAR:

~~~bash
jar --list --file dist/hello-app.jar
~~~

JAR là định dạng archive; nó không tự chứa JDK. Người dùng vẫn cần một Java runtime tương thích để chạy.

## 14. JAR có dependency bên ngoài

Một executable JAR chỉ chứa application classes và resource không tự động đóng gói mọi dependency bên ngoài.

Nếu chạy bằng `java -jar`, các thiết lập classpath bên ngoài trên command line bị bỏ qua. Có hai cách phổ biến:

1. Dùng `java -cp` với JAR ứng dụng và các dependency, sau đó gọi main class đầy đủ.
2. Khai báo `Class-Path` trong manifest để JVM tìm các JAR dependency theo đường dẫn tương đối với JAR chính.

Ví dụ classpath:

Windows:

~~~powershell
java -cp "dist/app.jar;lib/greeting-api.jar" com.example.app.Main
~~~

Linux/macOS:

~~~bash
java -cp "dist/app.jar:lib/greeting-api.jar" com.example.app.Main
~~~

Nếu dùng manifest `Class-Path`, các đường dẫn phải tương ứng với cấu trúc thư mục lúc triển khai. Kiểm tra archive sau khi đóng gói và thử chạy từ một working directory khác để phát hiện đường dẫn phụ thuộc môi trường.

## 15. Biên dịch ứng dụng modular

Một module có file `module-info.java`. Ví dụ hai module:

~~~text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/Greeter.java
  com.example.app/
    module-info.java
    com/example/app/Main.java
~~~

Module thư viện:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Class thư viện:

~~~java
package com.example.greeter;

public final class Greeter {
    public static String message() {
        return "READY modular javac";
    }
}
~~~

Module ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Biên dịch cả hai module:

~~~bash
javac --release 17 \
  --module-source-path src \
  -d mods \
  -m com.example.greeter,com.example.app
~~~

Chạy module ứng dụng:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
READY modular javac
~~~

`--module-source-path` chỉ vị trí source của các module đang compile. `--module-path` chỉ vị trí module đã biên dịch hoặc module dependency. Hai option có mục đích khác nhau.

## 16. Annotation processing

`javac` hỗ trợ annotation processor để phân tích annotation và có thể sinh thêm source file hoặc resource trong quá trình compile. Các thư viện như code generator có thể sử dụng cơ chế này.

Các option thường gặp:

| Option | Công dụng |
|---|---|
| `--processor-path` | Vị trí JAR chứa annotation processor |
| `--processor-module-path` | Module path của processor |
| `-processor` | Chỉ định tên processor cần chạy |
| `-Akey=value` | Truyền cấu hình riêng cho processor |
| `-s` | Thư mục source file được processor sinh ra |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chỉ chạy annotation processing |

Ví dụ cấu hình processor rõ ràng:

~~~bash
javac --release 17 \
  --processor-path tools/codegen.jar \
  --processor com.example.codegen.BuilderProcessor \
  -s build/generated-sources \
  -d build/classes \
  src/main/java/com/example/Order.java
~~~

Annotation processor là code chạy trong tiến trình build và có thể truy cập tài nguyên mà tiến trình đó được cấp. Chỉ dùng processor từ nguồn tin cậy, pin version và đưa dependency của processor vào kiểm soát build. Không bật/tắt annotation processing tùy tiện nếu ứng dụng dựa vào class được sinh tự động.

## 17. Các option javac thường dùng

| Option | Ý nghĩa |
|---|---|
| `--release 17` | Chọn source rules, API và class file target Java 17 |
| `-d build/classes` | Thư mục chứa class file đầu ra |
| `-cp` / `--class-path` | Dependency trên classpath |
| `-p` / `--module-path` | Dependency trên module path |
| `--source-path` | Vị trí source phụ thuộc |
| `--module-source-path` | Vị trí source của nhiều module |
| `-encoding UTF-8` | Encoding của source file |
| `-g` | Tạo thông tin debug |
| `-parameters` | Lưu tên tham số method/constructor cho reflection |
| `-Xlint:all` | Bật các cảnh báo lint |
| `-Werror` | Dừng compile nếu có warning |
| `-deprecation` | Hiển thị chi tiết API deprecated |
| `-verbose` | Hiển thị hoạt động compiler |

Ví dụ compile nghiêm ngặt:

~~~bash
javac --release 17 \
  -encoding UTF-8 \
  -Xlint:all \
  -Werror \
  -d build/classes \
  src/main/java/com/example/app/Main.java
~~~

`-Werror` hữu ích trong CI khi team muốn coi warning là lỗi. Trước khi bật, xử lý warning hiện có hoặc xác định rõ category nào được phép. Không dùng `-nowarn` để che lỗi chất lượng.

## 18. Dùng argument file cho project nhiều source

Command line có thể trở nên quá dài khi project có nhiều file. Dùng argument file để lưu option và source file, rồi gọi `javac @tên-file`.

Ví dụ `compile.args`:

~~~text
--release
17
-encoding
UTF-8
-d
build/classes
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/Formatter.java
~~~

Chạy:

~~~bash
javac @compile.args
~~~

Có thể đặt mỗi option và giá trị trên một dòng. Nếu đường dẫn có khoảng trắng, đặt toàn bộ đường dẫn trong dấu nháy kép. Đường dẫn tương đối bên trong argument file được tính từ working directory hiện tại, không phải thư mục chứa argument file.

Argument file giúp quản lý lệnh compile dài, nhưng cần cập nhật nó khi thêm/bớt source file. Wildcard không được mở rộng bên trong argument file.

## 19. Kiểm tra class file và kết quả biên dịch

Sau khi compile, dùng `javap` để kiểm tra class:

~~~bash
javap -classpath build/classes com.example.app.Main
javap -verbose -classpath build/classes com.example.app.Main
~~~

`javap` có thể hiển thị method, field, constant pool và class file version. Đây là cách xác nhận compiler đã tạo đúng class file target.

Dùng `jar --list --file` để kiểm tra nội dung archive. Chạy `java -cp` hoặc `java -jar` trên output thực tế để xác nhận runtime tìm được class và resource.

Một lệnh `javac` trả exit code 0 chỉ cho biết bước compile thành công. Nó không chứng minh chương trình chạy đúng, dependency có đủ, resource được đóng gói hay runtime production tương thích.

## 20. Phân biệt javac với source-file mode của java

JDK có thể chạy trực tiếp một source file:

~~~bash
java HelloWorld.java
~~~

Đây là source-file mode của launcher `java`. Launcher biên dịch source để chạy, hữu ích cho script nhỏ, demo hoặc thử nghiệm nhanh.

Nếu cần kiểm soát compiler option, lưu class file, tạo JAR, chạy annotation processor hoặc đưa bước compile vào pipeline, dùng `javac` tường minh. Source-file mode không thay thế toàn bộ quy trình build ứng dụng.

## 21. Biên dịch lặp lại và tránh class file cũ

Trong project thật, class file cũ có thể còn sót lại sau khi đổi package, xóa class hoặc thay cấu trúc source. Nếu chỉ ghi đè một phần output, JAR có thể vô tình chứa class không còn được source hiện tại tạo ra.

Quy trình build sạch:

Linux/macOS:

~~~bash
rm -rf build/classes
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes @compile.args
~~~

PowerShell:

~~~powershell
Remove-Item build/classes -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force build/classes | Out-Null
javac @compile.args
~~~

Đảm bảo `compile.args` trỏ đúng output directory. Sau khi clean compile, copy resource và tạo JAR từ output mới.

Với project lớn, Maven/Gradle quản lý incremental compilation, dependency và lifecycle thuận tiện hơn. `javac` vẫn là compiler thực thi bên dưới; hiểu cách gọi trực tiếp giúp đọc log và xử lý lỗi build.

## 22. Lỗi thường gặp khi dùng javac

### javac is not recognized hoặc command not found

Máy chưa cài JDK hoặc PATH chưa trỏ tới thư mục `bin` của JDK. Kiểm tra `javac --version`, `JAVA_HOME` và đường dẫn executable.

### package ... does not exist

Compiler không tìm thấy package dependency. Kiểm tra `-cp`, `--module-path`, tên package, vị trí JAR và repository/dependency đã được tải hay chưa.

### cannot find symbol

Có thể do sai tên class/method/field, thiếu import, source phụ chưa được truyền hoặc source path/classpath chưa đúng. Đọc dòng đầu tiên của diagnostic để tìm symbol và vị trí lỗi.

### class X is public, should be declared in a file named X.java

Tên file không khớp tên public top-level class. Đổi tên file hoặc class theo đúng quy tắc Java.

### invalid source release

JDK compiler hiện tại không hỗ trợ release được yêu cầu, hoặc cú pháp option không đúng. Kiểm tra `javac --version` và dùng JDK phù hợp.

### bad class file hoặc class file has wrong version

Dependency đã compile bằng Java mới hơn compiler/runtime mục tiêu. Nâng JDK hoặc chọn dependency tương thích baseline; không chỉ đổi `--release` của source hiện tại.

### Compile được nhưng chạy lỗi NoClassDefFoundError

Dependency có thể đã có trên compile classpath nhưng thiếu trên runtime classpath. Cấu hình lại lệnh `java`, manifest `Class-Path` hoặc cách đóng gói dependency.

### Không tìm thấy resource

Resource chưa được copy vào output/JAR hoặc đường dẫn resource sai. Kiểm tra `jar --list --file` và dùng `getResourceAsStream` với đường dẫn đúng từ classpath root.

### java -jar không tìm thấy thư viện ngoài

Khi dùng `-jar`, classpath command line bên ngoài bị bỏ qua. Đặt dependency trong manifest `Class-Path` hoặc chạy main class bằng `java -cp`.

### NoSuchMethodError sau khi compile thành công

Class file có thể đã load được nhưng dependency lúc chạy không có method mà code đã compile tham chiếu. Kiểm tra version JAR được dùng lúc compile và runtime; đồng bộ dependency thay vì thay đổi cú pháp javac.

## 23. Quy trình compile một ứng dụng từ đầu đến cuối

Dùng cấu trúc source:

~~~text
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/Formatter.java
src/main/resources/app.properties
~~~

Ví dụ `Formatter.java`:

~~~java
package com.example.app;

public final class Formatter {
    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Ví dụ `Main.java`:

~~~java
package com.example.app;

import java.io.InputStream;
import java.util.Properties;

public final class Main {
    public static void main(String[] args) throws Exception {
        String name = args.length == 0 ? "Java" : args[0];
        Properties properties = new Properties();

        try (InputStream in = Main.class.getResourceAsStream("/app.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(in);
        }

        System.out.println(properties.getProperty("banner") + ": " + Formatter.greet(name));
    }
}
~~~

File resource `app.properties`:

~~~properties
banner=READY javac
~~~

Biên dịch trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes \
  src/main/java/com/example/app/Main.java \
  src/main/java/com/example/app/Formatter.java
~~~

Copy resource vào classpath output.

PowerShell:

~~~powershell
Copy-Item src/main/resources/* build/classes/ -Recurse
~~~

Linux/macOS:

~~~bash
cp -R src/main/resources/. build/classes/
~~~

Chạy ứng dụng:

~~~bash
java -cp build/classes com.example.app.Main Linh
~~~

Stdout chính xác:

~~~text
READY javac: Hello, Linh
~~~

Tạo thư mục `dist`, rồi đóng gói:

~~~bash
jar --create --file dist/hello-app.jar --main-class com.example.app.Main -C build/classes .
~~~

Chạy JAR:

~~~bash
java -jar dist/hello-app.jar Linh
~~~

Stdout vẫn là:

~~~text
READY javac: Hello, Linh
~~~

## 24. Kiểm thử thực tế và tiêu chí hoàn thành

Ví dụ end-to-end trên Azul JDK 24.0.2 được biên dịch với `--release 17`:

- Biên dịch hai source file cùng lúc vào output directory.
- Copy resource vào classpath output.
- Chạy main class với tham số `Linh`.
- Đóng gói executable JAR và chạy bằng `java -jar`.
- Biên dịch ứng dụng có JAR dependency bằng `-cp`.
- Biên dịch hai named module bằng `--module-source-path`.
- Dùng argument file `@compile.args` để truyền option và source file.

Kết quả kiểm thử:

~~~text
READY javac: Hello, Linh
READY javac: Hello, Linh
READY classpath
READY modular javac
READY javac argfile: Hello, Linh
~~~

`javap -verbose` xác nhận class file tạo bằng `--release 17` có `major version: 61` và `minor version: 0`.

Trước khi xem một build là hoàn thành, hãy xác nhận:

1. `javac` đến từ JDK dự định dùng.
2. Package/source path và tên file đúng.
3. Tất cả source và dependency cần thiết đều được compiler tìm thấy.
4. `--release` và encoding được pin rõ ràng.
5. Class file được ghi vào output directory riêng.
6. Resource đã được copy vào classpath.
7. Runtime classpath/module path có đủ dependency.
8. JAR chứa đúng class, resource và manifest.
9. Ứng dụng chạy được trên runtime thấp nhất mà sản phẩm hỗ trợ.

## 25. Tài liệu tham khảo

- [Oracle JDK 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cú pháp compiler, --release, classpath, module path, source path, annotation processing, diagnostics và argument files.
- [Oracle JDK 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): chạy main class, executable JAR, module, classpath và source-file mode.
- [Oracle JDK 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): cấu trúc JAR, manifest, Main-Class, Class-Path và modular JAR.
- [Oracle JDK 26 — JDK Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html): danh mục công cụ JDK như javac, java, jar, javap và javadoc.

javac biến source Java thành class file có thể chạy trên JVM. Để biên dịch ứng dụng ổn định, hãy tổ chức package đúng, pin release và encoding, quản lý classpath/module path, copy resource, kiểm tra output rồi mới đóng gói và chạy artifact.
