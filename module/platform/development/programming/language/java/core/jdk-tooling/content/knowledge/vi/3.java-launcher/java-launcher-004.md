# Chạy module bằng Java launcher

Java launcher là chương trình `java` dùng để khởi chạy ứng dụng Java. Với ứng dụng được tổ chức thành module theo Java Platform Module System (JPMS), launcher nhận diện module, phân giải các module phụ thuộc và gọi phương thức `main` của lớp khởi chạy. Từ Java 9, bạn có thể chạy module đã biên dịch trong một thư mục, chạy modular JAR hoặc kết hợp nhiều module trên module path.

Bài này dùng cú pháp Java 17 trở lên và tập trung vào cách khởi chạy module bằng `java`, cách chọn lớp chính, cách phân giải phụ thuộc và cách xử lý lỗi thường gặp.

## 1. Cú pháp khởi chạy module

Cú pháp tổng quát:

~~~text
java [VM options] --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

Các thành phần:

- `java`: gọi Java launcher của JDK hoặc runtime đang được cấu hình trên `PATH`.
- `VM options`: tùy chọn của JVM, ví dụ `-Dname=value`, `-Xmx512m`, `-ea` hoặc `--enable-preview`.
- `--module-path` (`-p`): chỉ định nơi launcher tìm các module.
- `--module` (`-m`): chọn module gốc cần chạy; có thể viết thêm `/main-class` để chỉ rõ lớp chính.
- `application-args`: các đối số được truyền vào `main(String[] args)` của ứng dụng.

Hai cách viết sau tương đương:

~~~powershell
java --module-path mods --module com.example.greeter/com.example.greeter.Main
java -p mods -m com.example.greeter/com.example.greeter.Main
~~~

Nếu không ghi lớp chính sau dấu `/`, launcher cần tìm thông tin lớp chính đã được ghi trong module descriptor. Nếu module không có thông tin này, hãy chỉ định đầy đủ tên lớp chính trong lệnh.

## 2. Chuẩn bị một module để chạy

Một module Java có tên và khai báo phụ thuộc trong tệp `module-info.java`. Ví dụ, tạo cấu trúc sau:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── greeter/
│               └── Main.java
├── mods/
└── mlib/
~~~

Nội dung `src/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Nội dung `src/com/example/greeter/Main.java`:

~~~java
package com.example.greeter;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "module" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

Lớp `Main` có phương thức `public static void main(String[] args)`, là điểm vào quen thuộc của ứng dụng Java. Module descriptor đặt tên module là `com.example.greeter`. Khai báo `exports` cho phép module khác truy cập các kiểu public trong package này; ví dụ đơn giản hiện tại chưa cần module khác gọi đến nó, nhưng khai báo giúp thể hiện cách một module công bố API.

## 3. Chạy module dạng thư mục đã biên dịch

Khi biên dịch module, thư mục đầu ra phải giữ cấu trúc package và có `module-info.class` ở thư mục gốc của module.

Từ thư mục `project`, chạy trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.greeter | Out-Null
javac -d mods/com.example.greeter src/module-info.java src/com/example/greeter/Main.java
java --module-path mods --module com.example.greeter/com.example.greeter.Main Java 17
~~~

Kết quả:

~~~text
Hello, Java 17!
~~~

Giải thích:

1. `javac -d mods/com.example.greeter ...` biên dịch cả module descriptor và lớp `Main`.
2. `mods` là module path. Bên trong nó có thư mục module `com.example.greeter`.
3. `--module com.example.greeter/com.example.greeter.Main` yêu cầu chạy module `com.example.greeter` bằng lớp chính `com.example.greeter.Main`.
4. Các đối số `Java` và `17` xuất hiện sau phần chọn module nên được truyền vào `args` của ứng dụng.

Có thể dùng lệnh ngắn:

~~~powershell
java -p mods -m com.example.greeter/com.example.greeter.Main Java 17
~~~

Trên Linux hoặc macOS, các lệnh `javac` và `java` giống nhau; chỉ khác cách tạo thư mục nếu cần. Có thể dùng `mkdir -p mods/com.example.greeter` thay cho `New-Item`.

## 4. Chạy module từ modular JAR

Sau khi biên dịch, có thể đóng gói module thành modular JAR. Modular JAR chứa `module-info.class`, vì vậy launcher có thể xác định tên module và các phụ thuộc được khai báo.

Từ thư mục `project`, chạy:

~~~powershell
New-Item -ItemType Directory -Force -Path mlib | Out-Null
jar --create --file mlib/com.example.greeter.jar --main-class com.example.greeter.Main -C mods/com.example.greeter .
jar --describe-module --file mlib/com.example.greeter.jar
~~~

Tùy chọn `--main-class` ghi lớp chính vào metadata của modular JAR. Lệnh `jar --describe-module` giúp kiểm tra module name, package được xuất, các yêu cầu và lớp chính đã khai báo.

Khởi chạy modular JAR bằng module name:

~~~powershell
java --module-path mlib --module com.example.greeter Java 17
~~~

Kết quả:

~~~text
Hello, Java 17!
~~~

Vì lớp chính đã được ghi bằng `jar --main-class`, launcher có thể chạy module mà không cần chỉ rõ tên lớp sau dấu `/`. Nếu modular JAR không khai báo lớp chính, chỉ định lớp đó trong lệnh:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main Java 17
~~~

Có thể viết ngắn `--module-path` thành `-p` và `--module` thành `-m`:

~~~powershell
java -p mlib -m com.example.greeter Java 17
~~~

Lưu ý: modular JAR có `module-info.class` và được tìm qua module path. Một JAR thông thường chỉ có `Main-Class` trong manifest không tự động trở thành explicit module; cách chạy JAR thông thường được trình bày ở phần 7.

## 5. Module path và quá trình phân giải module

Module path là danh sách vị trí để Java tìm các module. Mỗi phần tử có thể là modular JAR hoặc thư mục chứa các module đã bung ra. Với ứng dụng có nhiều module, đặt các modular JAR vào một thư mục chung thường thuận tiện.

Ví dụ cấu trúc:

~~~text
project/
├── mlib/
│   ├── com.example.greeter.jar
│   ├── com.example.formatter.jar
│   └── com.example.config.jar
└── ...
~~~

Chạy ứng dụng:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

Launcher tìm module gốc `com.example.greeter`, đọc các khai báo `requires` trong `module-info.class`, rồi phân giải các module phụ thuộc cần thiết. Nếu module cần `com.example.formatter`, module đó phải có mặt trên module path và tên module phải khớp với khai báo.

Ví dụ descriptor của module phụ thuộc:

~~~java
module com.example.greeter {
    requires com.example.formatter;
    exports com.example.greeter;
}
~~~

Khai báo `requires` là quan hệ phụ thuộc ở cấp module. Chỉ đặt JAR vào cùng thư mục không tự động làm cho một module trở thành phụ thuộc của module khác; module cần khai báo phụ thuộc phù hợp.

### 5.1. Nhiều vị trí trên module path

Module path có thể gồm nhiều đường dẫn. Dấu phân cách phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | `;` | `-p "mlib;extra-modules"` |
| Linux/macOS | `:` | `-p "mlib:extra-modules"` |

Ví dụ trên Windows:

~~~powershell
java --module-path "mlib;extra-modules" --module com.example.greeter/com.example.greeter.Main
~~~

Đặt dấu ngoặc kép quanh danh sách đường dẫn nếu có khoảng trắng hoặc ký tự mà shell có thể diễn giải đặc biệt.

### 5.2. Quan sát quá trình phân giải

Khi cần biết launcher đã chọn những module nào, dùng `--show-module-resolution`:

~~~powershell
java --show-module-resolution --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

Tùy chọn này in thông tin các module được phân giải trước khi ứng dụng chạy. Nó hữu ích khi chẩn đoán trường hợp thiếu module, chọn nhầm phiên bản hoặc có nhiều nguồn module trên module path.

Có thể kiểm tra descriptor của một module trong JAR bằng:

~~~powershell
jar --describe-module --file mlib/com.example.greeter.jar
~~~

Và liệt kê các module trong runtime đang dùng:

~~~powershell
java --list-modules
~~~

## 6. Các tùy chọn launcher thường dùng khi chạy module

Các tùy chọn JVM phải đặt trước `-m` hoặc `--module`. Những đối số đặt sau module và lớp chính được chuyển cho ứng dụng.

### 6.1. Thiết lập system property và bộ nhớ

Ví dụ truyền cấu hình môi trường và giới hạn heap:

~~~powershell
java -Dapp.env=dev -Xms128m -Xmx512m --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

- `-Dapp.env=dev` tạo system property có thể đọc bằng `System.getProperty("app.env")`.
- `-Xms128m` đặt heap ban đầu.
- `-Xmx512m` đặt giới hạn heap tối đa.

Giá trị bộ nhớ cần phù hợp với ứng dụng và môi trường triển khai. Các tùy chọn `-X` có thể phụ thuộc phiên bản JVM.

### 6.2. Bật assertion

Nếu chương trình sử dụng `assert`, bật assertion khi chạy bằng `-ea`:

~~~powershell
java -ea --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

Assertion thường dùng để kiểm tra giả định trong quá trình phát triển và kiểm thử. Không nên dựa vào assertion để thay thế kiểm tra đầu vào hoặc xử lý lỗi cần có trong sản phẩm.

### 6.3. Bổ sung module gốc bằng `--add-modules`

Thông thường, module được chỉ định bằng `-m` là module gốc của ứng dụng và launcher tự phân giải các module mà nó yêu cầu. `--add-modules` cho phép thêm module khác vào tập module gốc được phân giải.

Ví dụ:

~~~powershell
java --module-path mlib --add-modules com.example.config --module com.example.greeter/com.example.greeter.Main
~~~

Tùy chọn này hữu ích khi một module cần được đưa vào tập module quan sát dù không được yêu cầu trực tiếp từ module gốc. Nó không thay thế khai báo `requires` khi mã của một named module cần đọc một named module khác.

### 6.4. Bật log phân giải và preview

- `--show-module-resolution`: hiển thị quá trình phân giải module.
- `--enable-preview`: bật tính năng preview của đúng phiên bản Java đang chạy; khi dùng, mã cần được biên dịch bằng tùy chọn preview tương ứng của cùng phiên bản JDK.
- `-Dkey=value`: truyền system property.
- `-ea`: bật assertion.

Ví dụ kết hợp:

~~~powershell
java -Dapp.mode=test -ea --show-module-resolution --module-path mlib --module com.example.greeter/com.example.greeter.Main sample
~~~

Đối số `sample` được chuyển vào ứng dụng. Các tùy chọn JVM nằm trước phần chọn module.

## 7. Phân biệt chạy module với chạy classpath và executable JAR

Java launcher hỗ trợ nhiều chế độ chạy. Chọn đúng chế độ giúp tránh nhầm lẫn giữa tên module, tên lớp và đường dẫn JAR.

| Chế độ | Lệnh mẫu | Cách tìm mã |
|---|---|---|
| Chạy lớp trên classpath | `java -cp out com.example.greeter.Main` | Tìm lớp qua classpath; mã thuộc unnamed module |
| Chạy JAR thông thường | `java -jar app.jar` | Đọc lớp chính từ `Main-Class` trong manifest |
| Chạy module | `java -p mlib -m com.example.greeter/com.example.greeter.Main` | Phân giải named module trên module path |
| Chạy modular JAR có main class metadata | `java -p mlib -m com.example.greeter` | Đọc module descriptor và lớp chính đã khai báo |

Classpath và module path có vai trò khác nhau:

- Classpath (`-cp`, `-classpath`, `--class-path`) là nơi tìm các lớp và JAR thuộc unnamed module.
- Module path (`-p`, `--module-path`) là nơi tìm các named module và modular JAR.
- Một JAR thông thường đặt trên classpath không được biến thành explicit module chỉ vì đổi `-cp` thành `-p`.
- Một JAR không có `module-info.class` có thể được xem như automatic module khi đặt trên module path; tên module tự động thường được suy ra từ tên JAR hoặc metadata. Automatic module có các giới hạn riêng và không tương đương module được thiết kế tường minh.

Nếu ứng dụng là ứng dụng classpath truyền thống, dùng `-cp` hoặc `-jar`. Nếu ứng dụng có module descriptor và cần ranh giới module, dùng `--module-path` cùng `--module`.

## 8. Truyền đối số cho chương trình

Đối số ứng dụng phải đặt sau phần chọn lớp chính hoặc sau tên module nếu module đã có main class metadata.

Ví dụ:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main "Java platform" "module system"
~~~

Với lớp `Main` ở phần 2, chương trình nhận hai đối số. `String.join(" ", args)` ghép chúng thành `Java platform module system`, vì vậy kết quả là:

~~~text
Hello, Java platform module system!
~~~

Dấu ngoặc kép giúp shell giữ cụm từ có khoảng trắng thành một đối số. Cách escape ký tự đặc biệt có thể khác giữa PowerShell, Command Prompt, Bash và Zsh.

Nếu muốn kiểm tra đối số trong mã, dùng `args.length` trước khi truy cập phần tử. Không nên giả định người dùng luôn truyền đủ đối số.

## 9. Lỗi thường gặp khi chạy module

| Thông báo hoặc triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Module com.example.greeter not found` | Module path sai hoặc không chứa module có tên đó | Kiểm tra đường dẫn `-p`, cấu trúc thư mục và tên trong `module-info.java` |
| `Module ... does not contain ...` hoặc không tìm thấy main class | Sai tên lớp chính hoặc module không khai báo main class khi lệnh bỏ phần `/Main` | Dùng `-m module/package.Main` hoặc đóng gói modular JAR với `jar --main-class` |
| `Could not find or load main class` | Dùng cú pháp classpath sai, tên package sai hoặc đặt nhầm vị trí đối số | Kiểm tra lệnh `-m`, module name, main class và cấu trúc package |
| `FindException` hoặc `ResolutionException` | Thiếu module phụ thuộc, có module không tương thích hoặc descriptor không hợp lệ | Đưa module cần thiết lên module path; kiểm tra `requires` và `jar --describe-module` |
| `Package ... is not visible` hoặc lỗi truy cập kiểu trong module khác | Package chưa được xuất hoặc module chưa khai báo đọc module cần thiết | Kiểm tra `exports` và `requires` trong module descriptor |
| Ứng dụng không nhận đối số như mong đợi | Đối số được đặt trước `-m` hoặc shell tách cụm từ có khoảng trắng | Đặt đối số sau module/lớp chính và dùng dấu ngoặc kép phù hợp shell |
| Thay đổi `-cp` nhưng lỗi module vẫn còn | Classpath không thay thế module path của named module | Đặt named module trên `--module-path` và khai báo quan hệ phụ thuộc đúng |

Khi gặp lỗi, kiểm tra theo thứ tự: module path có trỏ đúng nơi không; module name có khớp descriptor không; module có đủ phụ thuộc không; lớp chính có tồn tại và có phương thức `main` hợp lệ không; cuối cùng mới kiểm tra tùy chọn JVM và đối số ứng dụng.

## 10. Checklist trước khi chạy module

- [ ] Dùng đúng Java runtime/JDK mà ứng dụng yêu cầu.
- [ ] Module đã được biên dịch với `module-info.java` nếu cần explicit module.
- [ ] Module path chứa module gốc và tất cả named module phụ thuộc.
- [ ] Tên module sau `-m` khớp tên khai báo trong module descriptor.
- [ ] Lớp chính được chỉ định bằng `/package.Main` hoặc đã được ghi trong metadata của modular JAR.
- [ ] Các tùy chọn JVM được đặt trước `-m`; đối số ứng dụng đặt sau phần chọn module.
- [ ] Đã kiểm tra module resolution khi có lỗi bằng `--show-module-resolution`.
- [ ] Đã chạy thử trên đúng phiên bản Java và môi trường triển khai.

Java launcher cung cấp một điểm vào thống nhất để chạy lớp, JAR và module. Khi chạy module, hãy xác định đúng module path, chọn module bằng `-m` và bảo đảm lớp chính có thể được tìm thấy. Khi ứng dụng có nhiều module phụ thuộc, module descriptor và thông tin phân giải của launcher là hai nơi quan trọng nhất để kiểm tra.
