# Compile module-info cùng source

## 1. Vì sao module-info.java cần được biên dịch cùng module source?

Trong Java Platform Module System (JPMS), tệp `module-info.java` mô tả module: tên module, dependency, package được export, service được sử dụng hoặc cung cấp và các quy tắc truy cập liên quan.

Tệp này là source code đặc biệt của module. Khi biên dịch, `javac` tạo ra `module-info.class` cùng với các class thuộc module đó. Vì vậy, khi build một module từ source, cần đưa module descriptor và các source file của module vào cùng một lần biên dịch hoặc cùng một quy trình build nhất quán.

Cách thông dụng nhất là dùng `--module-source-path` để chỉ thư mục chứa các module source, rồi chọn module cần biên dịch bằng `-m` hoặc `--module`.

Không cần biên dịch `module-info.java` thành một artifact độc lập trước rồi mới biên dịch các class. Compiler cần biết descriptor để áp dụng module readability, package exports và dependency trong lúc biên dịch source.

## 2. Cấu trúc source chuẩn

Giả sử có module `com.acme.hello`:

```text
project/
└── src/
    └── com.acme.hello/
        ├── module-info.java
        └── com/
            └── acme/
                └── hello/
                    └── Main.java
```

Tệp `src/com.acme.hello/module-info.java`:

```java
module com.acme.hello {
}
```

Tệp `src/com.acme.hello/com/acme/hello/Main.java`:

```java
package com.acme.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a named module");
    }
}
```

Các điểm cần giữ đúng:

- Thư mục trực tiếp dưới `src` đại diện cho một module source root, ở đây là `com.acme.hello`.
- `module-info.java` nằm ngay tại root của module source, không nằm trong package directory.
- Source class nằm dưới đường dẫn tương ứng với package.
- Tên trong `module-info.java` là module name, không phải package name.
- `module-info.java` không có khai báo `package`.

## 3. Biên dịch module-info.java cùng toàn bộ source

Đứng tại thư mục `project`, chạy:

```bash
javac --module-source-path src -d out -m com.acme.hello
```

Hoặc dùng tên đầy đủ của option:

```bash
javac --module-source-path src -d out --module com.acme.hello
```

Ý nghĩa:

- `--module-source-path src`: chỉ ra nơi chứa source của các module. Với cấu trúc mặc định, compiler tìm thư mục module bên dưới `src`.
- `-d out`: ghi các class đã biên dịch vào thư mục output.
- `-m com.acme.hello`: yêu cầu biên dịch module có tên này. Compiler đọc `module-info.java` và các source file của module.

Kết quả có cấu trúc:

```text
out/
└── com.acme.hello/
    ├── module-info.class
    └── com/
        └── acme/
            └── hello/
                └── Main.class
```

Có thể kiểm tra descriptor đã được biên dịch:

```bash
javap -p out/com.acme.hello/module-info.class
```

Hoặc chạy:

```bash
java --module-path out -m com.acme.hello/com.acme.hello.Main
```

Kết quả:

```text
Hello from a named module
```

Điểm cần nhớ là một lần gọi `javac` đã biên dịch cả descriptor và source class thành output của cùng module.

## 4. Biên dịch nhiều module cùng lúc

Khi các module source phụ thuộc lẫn nhau, có thể đặt chúng dưới cùng module source path:

```text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

API module:

```java
module com.acme.api {
    exports com.acme.api;
}
```

Class API:

```java
package com.acme.api;

public record Customer(String name) {
}
```

Application module:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Main class:

```java
package com.acme.app;

import com.acme.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Ada");
        System.out.println(customer.name());
    }
}
```

Biên dịch cả hai module:

```bash
javac --module-source-path src -d out -m com.acme.api,com.acme.app
```

Compiler biên dịch descriptor và source của cả API lẫn application. Vì cả hai module đều được chọn trong cùng invocation, dependency source giữa chúng được giải quyết trong quá trình biên dịch.

Output:

```text
out/
├── com.acme.api/
│   ├── module-info.class
│   └── com/acme/api/Customer.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
```

Chạy:

```bash
java --module-path out -m com.acme.app/com.acme.app.Main
```

Kết quả:

```text
Ada
```

Nếu source module có dependency tới một module khác cũng đang nằm trong source tree, hãy đưa module đó vào danh sách module cần biên dịch hoặc cung cấp bản đã biên dịch trên module path.

## 5. Biên dịch application với dependency đã biên dịch

Trong dự án lớn, thư viện API thường được build trước và đóng gói thành modular JAR. Khi đó dùng `--module-path` cho dependency đã biên dịch và `--module-source-path` cho module source hiện tại.

Ví dụ:

```text
project/
├── mods/
│   └── com.acme.api.jar
└── src/
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

Biên dịch:

```bash
javac --module-path mods --module-source-path src -d out -m com.acme.app
```

Hai option có vai trò khác nhau:

| Option | Nội dung |
|---|---|
| `--module-source-path` | Tìm source code của module đang biên dịch |
| `--module-path` | Tìm module đã biên dịch, thường là modular JAR hoặc module directory |
| `-d` | Thư mục ghi class output |
| `-m` / `--module` | Module cần biên dịch |

Nếu API JAR không nằm trong `mods`, compiler có thể báo `module not found` dù source của application đã có `requires com.acme.api`.

## 6. Biên dịch source file trực tiếp và vai trò của module-source-path

Có thể truyền danh sách source file trực tiếp cho `javac` trong những build đơn giản, nhưng khi project có nhiều module, `--module-source-path` giúp compiler xác định ranh giới module và tìm source theo module name.

Ví dụ dạng chuẩn:

```bash
javac -d out --module-source-path src -m com.acme.api,com.acme.app
```

Không nên đặt tất cả source của nhiều named module vào một thư mục package tree duy nhất rồi biên dịch như một ứng dụng classpath. Mỗi named module cần một source root và descriptor riêng.

Nếu source layout khác mặc định, có thể dùng module-source-path pattern để chỉ vị trí module source. Ví dụ cấu trúc:

```text
src/
└── modules/
    ├── com.acme.api/
    └── com.acme.app/
```

Có thể chỉ định:

```bash
javac --module-source-path "src/modules/*" -d out -m com.acme.api,com.acme.app
```

Pattern `*` đại diện phần tên module trong đường dẫn. Đảm bảo pattern khớp đúng vị trí thư mục module; nếu không, compiler sẽ không tìm thấy source hoặc module descriptor.

## 7. Thêm compiler options khi build

Có thể kết hợp các option thông dụng:

```bash
javac --release 21 -encoding UTF-8 -Xlint:all --module-source-path src -d out -m com.acme.api,com.acme.app
```

- `--release 21` biên dịch theo API và ngôn ngữ của Java 21, nếu JDK đang dùng hỗ trợ release đó.
- `-encoding UTF-8` xác định encoding của source.
- `-Xlint:all` bật các cảnh báo compiler phổ biến.
- `--module-source-path` và `-m` chọn source modules cần biên dịch.

Chọn `--release` theo baseline JDK thực tế của dự án. Không dùng một release cao hơn phiên bản runtime production nếu ứng dụng cần chạy trên runtime cũ hơn.

Có thể dùng `-g` để sinh debug information hoặc `-parameters` nếu framework cần giữ tên tham số method. Các option này không thay đổi cấu trúc module graph.

## 8. Đóng gói output thành modular JAR

Sau khi compile, mỗi thư mục module trong `out` có thể được đóng gói riêng:

```bash
jar --create --file mods/com.acme.api.jar -C out/com.acme.api .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Đảm bảo `module-info.class` nằm ở root của mỗi JAR. Kiểm tra:

```bash
jar --describe-module --file mods/com.acme.api.jar
jar --describe-module --file mods/com.acme.app.jar
```

Nếu đóng gói nhầm từ một thư mục cấp trên hoặc bỏ sót `module-info.class`, JAR có thể không còn là explicit named module như mong đợi.

Sau khi đóng gói, nên chạy chính các JAR đã tạo:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main
```

Kiểm thử từ JAR giúp phát hiện lỗi packaging mà chạy trực tiếp từ thư mục `out` có thể che khuất.

## 9. Tích hợp vào build tool

### Maven

Với Maven, source của module thường nằm trong `src/main/java`, còn `module-info.java` ở ngay root source directory:

```text
src/main/java/
├── module-info.java
└── com/acme/app/Main.java
```

Maven Compiler Plugin biên dịch source và module descriptor theo cấu hình JDK/compiler plugin. Ví dụ cấu hình tối thiểu:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đảm bảo phiên bản Maven Compiler Plugin và JDK hỗ trợ release mục tiêu. Với multi-module Maven project, mỗi module Maven thường có artifact và descriptor riêng; dependency được khai báo trong POM phải tương thích với module name trong `module-info.java`.

### Gradle

Với Gradle Java plugin, `module-info.java` được đặt trong source set cùng source Java:

```text
src/main/java/
├── module-info.java
└── com/acme/app/Main.java
```

Cấu hình toolchain/release theo JDK mục tiêu và đảm bảo Gradle version hỗ trợ modular compilation phù hợp. Khi cần module path inference, kiểm tra cấu hình compile/test tasks và dependency được đặt đúng module path thay vì classpath.

Build tool có thể tự tổ chức compiler invocation, nhưng nguyên tắc vẫn vậy: descriptor phải được compiler xử lý cùng module source và dependency phải được cung cấp đúng loại path.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `module not found: X` | Dependency không có trên module path hoặc source path không tìm thấy module | Kiểm tra tên module, `--module-path` và `--module-source-path` |
| `module X does not read module Y` | Thiếu `requires Y` | Thêm dependency trong descriptor của module consumer |
| Package is not visible | Module sở hữu package chưa export hoặc consumer không đọc module | Kiểm tra cả `requires` và `exports` |
| `module-info.java` không được tìm thấy | Sai vị trí module source root hoặc pattern | Đặt descriptor ở root module và sửa module-source-path |
| Package declaration does not match directory | Source file nằm sai package path | Đồng bộ khai báo package với thư mục source |
| Main class không tìm thấy khi chạy | Sai module name, class name hoặc output layout | Kiểm tra output và dùng đúng `-m module/class` |
| JAR không được nhận là explicit module | Thiếu `module-info.class` trong artifact | Kiểm tra cách đóng gói và `jar --describe-module` |
| Build tool chạy được nhưng javac thủ công lỗi | Build tool đã thêm compiler/module path options | In hoặc kiểm tra compiler arguments và tái tạo đúng cấu hình |

Khi gặp lỗi, hãy đọc tên module/package trong thông báo trước khi sửa descriptor. Không thêm `exports` hoặc `requires transitive` một cách rộng rãi chỉ để làm cho compile pass.

## 11. Quy trình build có thể tái lập

Một quy trình build modular rõ ràng có thể gồm:

1. Kiểm tra source layout: mỗi module có root riêng và `module-info.java` đúng vị trí.
2. Kiểm tra tên module và dependency trong descriptor.
3. Build các module source cùng invocation nếu chúng phụ thuộc nhau, hoặc build dependency trước rồi đưa lên module path.
4. Dùng compiler release và encoding cố định.
5. Đóng gói từng module, bảo đảm giữ `module-info.class`.
6. Kiểm tra artifact bằng `jar --describe-module`.
7. Chạy từ module path bằng đúng JAR sẽ phát hành.
8. Lưu compiler/JDK version và build configuration để có thể tái lập.

## Ghi nhớ

- `module-info.java` là source đặc biệt của module và được biên dịch thành `module-info.class`.
- Đặt descriptor tại root của module source, bên cạnh cây package.
- Dùng `--module-source-path` để compiler tìm module source và `-m` để chọn module cần biên dịch.
- Biên dịch nhiều module source bằng cách liệt kê module names trong `-m`.
- Dùng `--module-path` cho dependency đã biên dịch; không nhầm với module source path.
- Đóng gói output sao cho `module-info.class` nằm ở root của modular JAR.
- Luôn kiểm thử artifact đã đóng gói bằng `java --module-path`, không chỉ chạy từ thư mục class output.
