# Đặt module-info.java ở source root

Trong một dự án Java modular, `module-info.java` phải nằm ở **source root của module**, cùng cấp với các thư mục package ở bên dưới. File này mô tả module và không thuộc package của class ứng dụng.

Vị trí đúng giúp compiler nhận diện ranh giới module, biên dịch descriptor thành `module-info.class` và đặt file đó ở root của output directory hoặc root của modular JAR. Nếu đặt file trong thư mục package, compiler và công cụ build có thể không nhận diện nó như module descriptor của source set.

## 1. Source root là gì?

Source root là thư mục mà từ đó compiler bắt đầu tìm các package của một source set. Ví dụ, nếu class khai báo:

~~~java
package com.example.app;
~~~

thì file thường nằm dưới đường dẫn:

~~~text
<source-root>/com/example/app/
~~~

Với module đơn, cấu trúc phổ biến là:

~~~text
my-app/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
└── out/
~~~

Ở đây:

- `src/` là source root.
- `module-info.java` nằm ngay tại source root.
- `Main.java` nằm trong package `com.example.app`.
- `out/` là nơi compiler ghi class và module descriptor sau khi biên dịch.

Không đặt descriptor tại `src/com/example/app/module-info.java` hoặc trong một package con. Module descriptor không có khai báo `package` và không phải class thuộc package ứng dụng.

## 2. Nội dung của module-info.java

Một module descriptor bắt đầu bằng khai báo `module` hoặc `open module`:

~~~java
module com.example.app {
    requires java.logging;

    exports com.example.app.api;
}
~~~

Một số quy tắc cần nhớ:

- Tên module nằm sau từ khóa `module`.
- File không có dòng `package ...;`.
- Các chỉ thị như `requires`, `exports`, `opens`, `uses` và `provides` nằm bên trong cặp ngoặc nhọn.
- Tên package trong `exports` phải khớp với package thực tế trong source.
- Tên module được dùng trong `requires` phải khớp với tên module mà dependency cung cấp.

Ví dụ đầy đủ:

~~~java
module com.example.app {
    requires java.logging;

    exports com.example.app.api;

    opens com.example.app.model
        to com.example.json;
}
~~~

`module-info.java` chỉ mô tả cấu trúc và quan hệ của module. Các class ứng dụng vẫn nằm trong những file Java thuộc package tương ứng.

## 3. Biên dịch module đơn bằng javac

Giả sử dự án có cấu trúc:

~~~text
my-app/
└── src/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

File `src/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `src/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a named module");
    }
}
~~~

Đứng tại thư mục gốc dự án, biên dịch:

~~~shell
javac -d out src/module-info.java src/com/example/app/Main.java
~~~

Sau khi biên dịch, output có dạng:

~~~text
out/
├── module-info.class
└── com/
    └── example/
        └── app/
            └── Main.class
~~~

Điểm quan trọng là `module-info.class` nằm trực tiếp ở root của output directory, cùng cấp với thư mục package `com/`. Đây là cấu trúc output của một module đã biên dịch.

Có thể chạy module từ output directory:

~~~shell
java --module-path out --module com.example.app/com.example.app.Main
~~~

`--module-path` trỏ tới thư mục chứa module đã biên dịch. `--module` chỉ định tên module và main class.

## 4. Đóng gói modular JAR

Khi đã có output directory đúng cấu trúc, có thể đóng gói thành JAR:

~~~shell
jar --create --file dist/com.example.app.jar -C out .
~~~

JAR sẽ chứa:

~~~text
com.example.app.jar
├── module-info.class
└── com/
    └── example/
        └── app/
            └── Main.class
~~~

Module descriptor đã biên dịch phải nằm ở root của JAR modular. Không tạo một thư mục package bao quanh `module-info.class`.

Kiểm tra descriptor trong artifact:

~~~shell
jar --describe-module --file dist/com.example.app.jar
~~~

Kết quả cần cho thấy tên module `com.example.app` và các package hoặc chỉ thị được khai báo. Đây là cách xác nhận artifact được đóng gói có descriptor mà compiler đã tạo.

Chạy từ JAR:

~~~shell
java --module-path dist --module com.example.app/com.example.app.Main
~~~

Nếu `jar --describe-module` không nhận diện module theo tên mong đợi, hãy kiểm tra lại nội dung JAR, vị trí `module-info.class` và source layout trước khi điều chỉnh module path.

## 5. Source root trong Maven và Gradle

Các build tool Java phổ biến đã định nghĩa source root mặc định. Với một module Maven hoặc Gradle thông thường, cấu trúc thường là:

~~~text
project/
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── module-info.java
    │   │   └── com/example/app/Main.java
    │   └── resources/
    └── test/
        └── java/
            └── ...
~~~

Trong cấu trúc này, `src/main/java/` là source root của main source set. Vì vậy, đặt descriptor tại:

~~~text
src/main/java/module-info.java
~~~

Không đặt tại:

~~~text
src/main/java/com/example/app/module-info.java
~~~

Maven và Gradle sẽ tìm source trong source root đã cấu hình. Nếu dự án thay đổi `sourceSets` hoặc `sourceDirectory`, vị trí đúng cũng phải thay đổi theo source root mới.

### Maven

Với Maven Compiler Plugin, `module-info.java` được biên dịch cùng source của module khi source root là `src/main/java`. Ví dụ descriptor:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Sau khi chạy:

~~~shell
mvn clean package
~~~

Kiểm tra JAR tạo ra:

~~~shell
jar --describe-module --file target/com.example.app-1.0.jar
~~~

Tên file JAR phụ thuộc vào `artifactId` và `version` trong `pom.xml`. Tên module vẫn lấy từ descriptor, không nhất thiết được suy ra từ tên file.

Nếu dự án cần biên dịch module với một release cụ thể, hãy cấu hình `maven.compiler.release` phù hợp với JDK mục tiêu. Module System được giới thiệu từ Java 9, vì vậy source/target thấp hơn Java 9 không thể biên dịch module descriptor theo cách này.

### Gradle

Với Gradle Java plugin, source root mặc định của main source set cũng là `src/main/java`:

~~~text
src/main/java/
├── module-info.java
└── com/example/app/Main.java
~~~

Sau khi chạy:

~~~shell
./gradlew clean jar
~~~

JAR thường được tạo trong:

~~~text
build/libs/
~~~

Kiểm tra descriptor:

~~~shell
jar --describe-module --file build/libs/<artifact-name>.jar
~~~

Nếu dự án dùng custom source set hoặc thay đổi `java.srcDirs`, hãy đặt descriptor ở root của source directory tương ứng. Đừng giả định mọi dự án Gradle đều dùng cùng một source root sau khi cấu hình đã được tùy chỉnh.

## 6. Cấu trúc source cho nhiều module

Khi một dự án có nhiều module được biên dịch cùng lúc, có thể tổ chức mỗi module thành một thư mục riêng dưới module source path:

~~~text
workspace/
└── src/
    ├── com.example.api/
    │   ├── module-info.java
    │   └── com/example/api/Greeting.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Mỗi thư mục con trực tiếp dưới `src/` đại diện cho một module source. Trong từng module source:

- `module-info.java` nằm ở root của module.
- Package source nằm trong các thư mục con.
- Tên module trong descriptor phải tương ứng với module mà source tree đại diện.

Ví dụ `src/com.example.api/module-info.java`:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

Ví dụ `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

Biên dịch nhiều module bằng module source path:

~~~shell
javac --module-source-path src -d out -m com.example.api,com.example.app
~~~

Output sẽ có cấu trúc:

~~~text
out/
├── com.example.api/
│   ├── module-info.class
│   └── com/example/api/Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Ở đây, mỗi module có output root riêng và có `module-info.class` tại root của chính module đó.

Có thể chạy app với:

~~~shell
java --module-path out --module com.example.app/com.example.app.Main
~~~

Không nhầm lẫn giữa source root của một module đơn (`src/`) với module source path chứa nhiều module (`src/com.example.api/`, `src/com.example.app/`). Cả hai đều đặt `module-info.java` ở root tương ứng, nhưng cấp thư mục khác nhau.

## 7. Source root, package root và module root khác nhau thế nào?

Các thuật ngữ này dễ bị nhầm khi cấu hình IDE hoặc build tool:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Project root | `my-app/` | Thư mục gốc của dự án |
| Source root | `my-app/src/main/java/` | Gốc của source set Java |
| Package directory | `src/main/java/com/example/app/` | Nơi chứa class thuộc package `com.example.app` |
| Module source root | `src/com.example.app/` | Gốc source của một module trong multi-module source path |
| Compiled module root | `out/` hoặc `out/com.example.app/` | Nơi chứa `module-info.class` và package class |
| JAR root | Root entries bên trong file JAR | Nơi chứa descriptor và package entries của module |

`module-info.java` không đặt trong package directory. Nó được compiler xử lý như module descriptor của source root.

Trong IDE, cần đánh dấu đúng thư mục là Sources Root hoặc Source Folder. Nếu IDE đánh dấu `src/main/java/com/example/app` là source root thay vì `src/main/java`, package có thể bị nhận diện sai và descriptor ở cấp trên không còn thuộc source root mà IDE đang biên dịch.

## 8. Các lỗi thường gặp khi đặt module-info.java

### Đặt descriptor trong package directory

Sai:

~~~text
src/
└── com/example/app/
    ├── module-info.java
    └── Main.java
~~~

Đúng:

~~~text
src/
├── module-info.java
└── com/example/app/
    └── Main.java
~~~

### Thêm package declaration vào module-info.java

Sai:

~~~java
package com.example.app;

module com.example.app {
}
~~~

Đúng:

~~~java
module com.example.app {
}
~~~

Module descriptor không có package declaration.

### Đặt sai source root trong IDE

Nếu IDE không nhận `src/main/java` là source root, nó có thể báo package không tồn tại, module không tìm thấy hoặc không biên dịch descriptor. Kiểm tra cấu hình source folder của module và bảo đảm file descriptor nằm trực tiếp trong source root đã đánh dấu.

### Biên dịch chỉ một class mà bỏ qua descriptor

Nếu biên dịch riêng `Main.java` mà không đưa module descriptor hoặc module path phù hợp vào compiler, kết quả có thể là một class không được biên dịch trong module context mong muốn.

Với module đơn, hãy biên dịch descriptor và source liên quan cùng nhau:

~~~shell
javac -d out src/module-info.java src/com/example/app/Main.java
~~~

Với nhiều module, dùng `--module-source-path` và `-m` để compiler biết các module source cần biên dịch.

### Đặt nhầm module-info.class trong JAR

Một JAR modular cần có `module-info.class` tại root. Nếu lệnh đóng gói đưa cả thư mục `out/` thành một entry folder bên trong JAR, cấu trúc có thể không như mong đợi. Hãy kiểm tra lệnh `jar -C out .` và kết quả `jar --describe-module`.

### Nhầm tên file JAR với tên module

Tên file như `com.example.app-1.0.jar` không phải nguồn xác định duy nhất của module name. Với explicit module, tên lấy từ `module-info.class`. Hãy dùng `jar --describe-module` để kiểm tra tên module thực tế.

## 9. Quy trình kiểm tra nhanh

Khi tạo một modular JAR mới, có thể làm theo trình tự:

1. Xác định source root mà compiler hoặc build tool đang sử dụng.
2. Đặt `module-info.java` ngay tại root đó.
3. Đặt class trong các thư mục package bên dưới source root.
4. Kiểm tra descriptor không có package declaration và tên module hợp lệ.
5. Biên dịch với JDK hỗ trợ JPMS và cấu hình source/release phù hợp.
6. Kiểm tra `module-info.class` nằm ở root output của module.
7. Đóng gói JAR sao cho descriptor nằm ở root của JAR.
8. Chạy `jar --describe-module` trên artifact cuối.
9. Chạy thử với `--module-path` và `--module` để xác nhận runtime nhận diện module.

Có thể dùng các lệnh sau làm checklist tối thiểu:

~~~shell
# Compile a single module.
javac -d out src/module-info.java src/com/example/app/Main.java

# Inspect compiled module descriptor.
javap -p out/module-info.class

# Package the module.
jar --create --file dist/com.example.app.jar -C out .

# Inspect the packaged module.
jar --describe-module --file dist/com.example.app.jar

# Launch the named module.
java --module-path dist --module com.example.app/com.example.app.Main
~~~

## Kết luận

`module-info.java` phải nằm tại source root của module, cùng cấp với các thư mục package. Compiler chuyển file này thành `module-info.class` và đặt descriptor ở root của output module; khi đóng gói, descriptor tiếp tục nằm ở root của modular JAR. Với dự án nhiều module, mỗi module có source root riêng và descriptor nằm ở root tương ứng. Xác định đúng source root trong javac, Maven, Gradle hoặc IDE là bước đầu tiên để tạo một modular JAR có cấu trúc hợp lệ.
