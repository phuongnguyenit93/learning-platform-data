# Main class trong module descriptor hoặc command line

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định main class dùng để khởi chạy một named module.
- Phân biệt main class được lưu trong module descriptor với main class truyền trực tiếp trên command line.
- Dùng `jar --main-class` để đặt entry point cho modular JAR.
- Khởi chạy module bằng `java -m` hoặc `java --module`.
- Hiểu cách command line ghi đè main class đã được lưu trong module.
- Phân biệt module main class với thuộc tính `Main-Class` trong manifest khi chạy `java -jar`.

## 1. Main class của một named module

Một ứng dụng Java cần một entry point để launcher biết class nào sẽ được gọi đầu tiên. Với cách chạy truyền thống trên classpath, bạn thường chỉ rõ fully qualified class name:

~~~bash
java -cp out com.example.app.Main
~~~

Khi ứng dụng được tổ chức thành named module, bạn có thể khởi chạy bằng module name. Launcher cần biết module nào là module khởi đầu và main class nào cần gọi.

Ví dụ, ứng dụng có module name là `com.example.app` và main class là `com.example.app.Main`:

~~~bash
java --module-path out \
     --module com.example.app/com.example.app.Main
~~~

Có hai nơi có thể cung cấp main class:

1. Module descriptor có thể lưu một module main class.
2. Command line có thể chỉ rõ main class sau dấu `/` trong cú pháp `module/mainclass`.

Nếu command line chỉ cung cấp module name, launcher sử dụng main class đã lưu trong module descriptor. Nếu command line cung cấp cả module name và main class, class trên command line được dùng; nó có thể ghi đè main class đã lưu.

## 2. Module descriptor không có directive main-class

Một module descriptor source thông thường được viết trong `module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Java không có cú pháp directive `main-class` trong `module-info.java`. Bạn không viết một dòng như `main-class com.example.app.Main;` trong module declaration.

Thông tin main class được lưu ở dạng binary attribute có tên `ModuleMainClass` trong file `module-info.class`. Đây là metadata của module descriptor, không phải một directive Java source.

API `java.lang.module.ModuleDescriptor` cung cấp phương thức:

~~~java
Optional<String> mainClass = descriptor.mainClass();
~~~

Phương thức `mainClass()` trả về tên đầy đủ của module main class nếu descriptor có khai báo; nếu không có thì trả về `Optional.empty()`.

Trong quy trình build thông thường, bạn có thể dùng JDK `jar` tool để thêm thông tin này vào modular JAR bằng option `--main-class`.

## 3. Chuẩn bị module và main class

Giả sử project có cấu trúc:

~~~text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.Arrays;

public class Main {

    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

Main class dùng method entry point chuẩn:

~~~java
public static void main(String[] args)
~~~

Compile module bằng module source path:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.app
~~~

Sau khi compile, output có dạng:

~~~text
out/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Ở thời điểm này, `module-info.class` có module descriptor nhưng chưa có module main class do ta chưa thiết lập metadata đó bằng công cụ đóng gói. Bạn vẫn có thể chạy ứng dụng bằng cách chỉ rõ main class trên command line.

## 4. Chỉ định main class trên command line

Cú pháp khởi chạy một module:

~~~text
java [options] -m module[/mainclass] [args...]
~~~

Hoặc dùng dạng dài:

~~~text
java [options] --module module[/mainclass] [args...]
~~~

Với ví dụ trên:

~~~bash
java --module-path out \
     --module com.example.app/com.example.app.Main \
     hello world
~~~

Giải thích:

- `--module-path out` chỉ vị trí chứa các named module.
- `--module` hoặc `-m` yêu cầu launcher chạy một module.
- `com.example.app` là tên module.
- `com.example.app.Main` là fully qualified name của main class.
- `hello world` là hai argument được chuyển vào `main(String[] args)`.

Bạn có thể viết ngắn hơn:

~~~bash
java -p out -m com.example.app/com.example.app.Main hello world
~~~

`-p` là dạng rút gọn của `--module-path`; `-m` là dạng rút gọn của `--module`.

Cách này phù hợp khi:

- Chạy exploded module trong thư mục build.
- Muốn chọn entry point khác nhau cho từng lần chạy.
- Module descriptor chưa lưu module main class.
- Muốn override main class mặc định mà modular JAR đã khai báo.

## 5. Lưu main class trong module descriptor bằng jar --main-class

Khi đóng gói module thành modular JAR, dùng option `--main-class` của `jar`:

~~~bash
jar --create \
    --file dist/com.example.app.jar \
    --main-class com.example.app.Main \
    -C out/com.example.app .
~~~

Option `--main-class` (viết ngắn là `-e`) chỉ định entry point cho ứng dụng được đóng gói trong modular JAR. Với modular JAR, `jar` ghi thông tin module main class vào module descriptor nhị phân.

Có thể cập nhật một JAR đã tồn tại:

~~~bash
jar --update \
    --file dist/com.example.app.jar \
    --main-class com.example.app.Main
~~~

Để kiểm tra descriptor sau khi đóng gói:

~~~bash
jar --describe-module --file dist/com.example.app.jar
~~~

Kết quả sẽ có thông tin tương tự:

~~~text
com.example.app
requires java.base mandated
main-class com.example.app.Main
~~~

Dòng `main-class` cho biết module descriptor đã lưu entry point.

Giờ đây có thể chạy module mà không phải viết tên class:

~~~bash
java --module-path dist \
     --module com.example.app \
     hello world
~~~

Launcher đọc module descriptor, lấy module main class và gọi method `main` của class đó.

## 6. Command line có thể ghi đè main class đã lưu

Giả sử module descriptor lưu `com.example.app.Main`, nhưng ứng dụng cũng có class `com.example.app.AdminMain` với method main hợp lệ.

Có thể chọn class thứ hai khi chạy:

~~~bash
java --module-path dist \
     --module com.example.app/com.example.app.AdminMain
~~~

Trong trường hợp này, launcher sử dụng class được ghi trên command line thay cho module main class đã lưu.

Bảng hành vi:

| Lệnh | Kết quả |
|---|---|
| `java -p dist -m com.example.app` | Dùng main class trong module descriptor |
| `java -p dist -m com.example.app/com.example.app.Main` | Chạy `Main` được chỉ định tường minh |
| `java -p dist -m com.example.app/com.example.app.AdminMain` | Chạy `AdminMain`, ghi đè entry point mặc định |
| `java -p out -m com.example.app/com.example.app.Main` | Chạy main class tường minh, dù descriptor không lưu main class |

Nếu module descriptor không có main class và command line cũng chỉ cung cấp module name, launcher không có entry point để gọi và lệnh khởi chạy sẽ thất bại. Khi đó, hãy chỉ rõ `module/mainclass` hoặc đóng gói module với `--main-class`.

## 7. Phân biệt module main class và manifest Main-Class

Hai cơ chế thường bị nhầm lẫn:

- `ModuleMainClass` là attribute trong binary module descriptor `module-info.class`.
- `Main-Class` là manifest attribute trong `META-INF/MANIFEST.MF`, được launcher sử dụng khi chạy `java -jar`.

So sánh:

| Cách chạy | Nguồn lấy main class |
|---|---|
| `java -m module` | Module main class trong module descriptor |
| `java -m module/mainclass` | Main class được chỉ định trên command line |
| `java -jar app.jar` | `Main-Class` trong JAR manifest |
| `java -cp out package.Main` | Class name được chỉ định trực tiếp trên command line |

`java -jar` và `java -m` là hai chế độ khởi chạy khác nhau. Khi dùng `-jar`, launcher lấy entry point từ manifest. Khi dùng `-m`, launcher lấy module main class từ descriptor nếu command line không cung cấp class.

Option `jar --main-class` là cách thuận tiện để đóng gói một modular JAR có entry point. Nếu cần kiểm tra hai metadata sau khi đóng gói, có thể xem module descriptor bằng `jar --describe-module` và xem manifest bằng:

~~~bash
jar --extract --file dist/com.example.app.jar META-INF/MANIFEST.MF
~~~

## 8. Kiểm tra main class bằng Java API

Nếu ứng dụng hoặc công cụ build cần đọc metadata của module, có thể dùng `ModuleDescriptor`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

public class InspectModule {

    public static void main(String[] args) {
        ModuleFinder finder =
                ModuleFinder.of(Path.of("dist/com.example.app.jar"));

        ModuleDescriptor descriptor =
                finder.find("com.example.app")
                        .orElseThrow()
                        .descriptor();

        descriptor.mainClass().ifPresentOrElse(
                name -> System.out.println("Main class: " + name),
                () -> System.out.println("No module main class configured")
        );
    }
}
~~~

Ở ví dụ này:

1. `ModuleFinder.of(...)` đọc module từ modular JAR.
2. `find(...)` tìm module theo tên.
3. `descriptor()` lấy module descriptor.
4. `mainClass()` trả về `Optional<String>`.
5. `ifPresentOrElse(...)` xử lý trường hợp descriptor có hoặc không có main class.

Đây là cách kiểm tra metadata mà không cần giải nén `module-info.class` hoặc tự phân tích class-file attribute.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy main class khi chỉ truyền module name | Descriptor chưa lưu entry point | Dùng `-m module/mainclass` hoặc đóng gói với `jar --main-class` |
| `Could not find or load main class` | Sai fully qualified class name hoặc class không nằm trong module | Kiểm tra package, tên class và module output |
| `Module ... not found` | Module path không chứa module cần chạy | Kiểm tra `--module-path` và tên module |
| `Main method not found` hoặc method không hợp lệ | Main class không có entry point được launcher chấp nhận | Kiểm tra chữ ký `public static void main(String[] args)` |
| `java -jar` không dùng main class mong đợi | Manifest thiếu hoặc đặt sai `Main-Class` | Kiểm tra `META-INF/MANIFEST.MF` |
| `java -m` chạy class khác với mong đợi | Command line đã chỉ rõ `/mainclass` và override metadata | Kiểm tra lại phần sau dấu `/` |

Hãy luôn kiểm tra module name và fully qualified class name. Module name không nhất thiết trùng package name hoặc tên JAR file.

## 10. Tóm tắt

Một named module có thể lưu main class trong binary module descriptor thông qua `ModuleMainClass` attribute. `module-info.java` không có directive `main-class`; với modular JAR, dùng `jar --main-class` để ghi entry point vào descriptor.

Khi chạy, `java -m module` sử dụng main class đã lưu trong descriptor. Nếu command line chỉ rõ `module/mainclass`, class được chỉ định sẽ được chạy và có thể ghi đè giá trị mặc định. Còn `java -jar` sử dụng `Main-Class` trong manifest. Hiểu rõ ba nơi lưu/chọn entry point này giúp build và chạy modular application nhất quán.

Tài liệu tham khảo:

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [ModuleDescriptor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [The Java Virtual Machine Specification: ModuleMainClass](https://docs.oracle.com/javase/specs/jvms/se21/jvms21.pdf)
