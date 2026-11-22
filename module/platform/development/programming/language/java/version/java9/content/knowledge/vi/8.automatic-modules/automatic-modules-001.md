# JAR trên class path và mô-đun không tên (unnamed module)

## Mục tiêu

Trong Java Platform Module System (JPMS), một JAR được đặt trên **class path** được nạp như mã thuộc **mô-đun không tên (unnamed module)** của class loader tương ứng. JAR đó không trở thành named module chỉ vì ứng dụng còn sử dụng JPMS hoặc vì JAR có tên giống một module.

Hiểu ranh giới này giúp chọn đúng cách chạy ứng dụng Java cũ, tích hợp thư viện chưa modular và chuyển dần sang module có tên. Bài này tập trung vào hành vi còn được hỗ trợ trong các JDK hiện đại.

## 1. Class path là gì?

Class path là danh sách thư mục và JAR mà compiler hoặc JVM tìm kiếm các lớp Java. Các tùy chọn thường dùng:

- `javac --class-path` hoặc `javac -cp`: chỉ nơi tìm lớp/JAR khi biên dịch.
- `java --class-path` hoặc `java -cp`: chỉ nơi tìm lớp/JAR khi chạy.
- `-classpath` là cách viết đầy đủ tương đương của `-cp`.

Ví dụ, ứng dụng có thể được biên dịch và chạy bằng class path như sau:

```powershell
javac -cp lib/greeter.jar -d app-classes app-src/com/example/app/Main.java
java -cp "app-classes;lib/greeter.jar" com.example.app.Main
```

Trên Windows, dấu phân cách giữa các mục class path là dấu chấm phẩy `;`. Trên Linux và macOS, dùng dấu hai chấm `:`:

```bash
java -cp "app-classes:lib/greeter.jar" com.example.app.Main
```

Mỗi mục có thể là thư mục chứa các file `.class` hoặc một JAR. JVM dùng class loader để tìm lớp khi ứng dụng cần nạp chúng. Nếu một lớp có trong lúc biên dịch nhưng JAR hoặc thư mục tương ứng bị thiếu lúc chạy, ứng dụng có thể gặp `NoClassDefFoundError`; lời gọi nạp lớp tường minh cũng có thể ném `ClassNotFoundException`.

## 2. Unnamed module hình thành như thế nào?

JPMS gán các lớp được nạp bởi một class loader vào module tương ứng. Với mã được nạp từ class path, các lớp thuộc **unnamed module** gắn với class loader đó.

Đặc điểm chính:

- Unnamed module không có tên module và không có `module-info.java` để khai báo `requires`, `exports` hay `opens`.
- Các lớp class path do cùng một class loader nạp thuộc unnamed module của loader đó. Một class loader khác có unnamed module riêng.
- Unnamed module được xem là đọc được các module đã được phân giải trong cấu hình chạy; các package của nó được export và open theo quy tắc của unnamed module.
- Với ứng dụng class path thông thường, lớp `Main` thường thuộc unnamed module của application class loader.

Có thể quan sát trực tiếp bằng API `Class.getModule()`: `Module.isNamed()` trả về `false` và `Module.getName()` trả về `null` đối với unnamed module.

## 3. JAR trên class path khác JAR trên module path

Vị trí của JAR quyết định cách JPMS xem JAR đó:

| Vị trí JAR | Cách JVM phân loại | Cách khai báo phụ thuộc |
|---|---|---|
| `--class-path` | Các lớp thuộc unnamed module của class loader | Không có tên module để viết trong `requires` |
| `--module-path`, JAR có `module-info.class` | Named module tường minh | `requires ten.module;` |
| `--module-path`, JAR không có descriptor module | Automatic module | Có thể dùng tên automatic module trong `requires` |

Một JAR không modular khi đặt trên module path có thể được JPMS coi là **automatic module**. Tên của nó lấy từ thuộc tính `Automatic-Module-Name` trong manifest nếu có; nếu không, tên được suy ra từ tên file JAR theo quy tắc đặt tên module. Automatic module có tên, export các package của nó và đọc các named module khác. Đây là cầu nối phục vụ quá trình chuyển đổi thư viện cũ.

Cùng JAR đó nếu đặt trên class path thì các lớp của nó vẫn thuộc unnamed module. JAR không được tự chuyển thành automatic module. Vì vậy, `requires` trong một module descriptor không thể tham chiếu trực tiếp đến một JAR đang chỉ nằm trên class path.

## 4. Ví dụ chạy đầy đủ: thư viện JAR trên class path

Ví dụ sau tạo một thư viện chưa có `module-info.java`, đóng gói thành JAR rồi gọi từ ứng dụng class path. Cả ứng dụng và thư viện đều thuộc unnamed module của application class loader.

Cấu trúc dự án:

```text
project/
├── lib-src/
│   └── com/example/greeter/Greeter.java
├── lib-classes/
├── lib/
│   └── greeter.jar
├── app-src/
│   └── com/example/app/Main.java
└── app-classes/
```

**Thư viện — `lib-src/com/example/greeter/Greeter.java`**

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Hello from a class-path JAR";
    }
}
```

**Ứng dụng — `app-src/com/example/app/Main.java`**

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println("moduleName=" + Main.class.getModule().getName());
        System.out.println("isNamed=" + Main.class.getModule().isNamed());
    }
}
```

Trên Windows PowerShell, chạy từ thư mục `project`:

```powershell
New-Item -ItemType Directory -Force lib-classes, lib, app-classes
javac -d lib-classes lib-src/com/example/greeter/Greeter.java
jar --create --file lib/greeter.jar -C lib-classes .
javac -cp lib/greeter.jar -d app-classes app-src/com/example/app/Main.java
java -cp "app-classes;lib/greeter.jar" com.example.app.Main
```

Trên Linux hoặc macOS, có thể tạo các thư mục bằng `mkdir -p lib-classes lib app-classes`. Các lệnh biên dịch và đóng gói giữ nguyên; lệnh chạy thay class path bằng dấu `:`:

```bash
java -cp "app-classes:lib/greeter.jar" com.example.app.Main
```

Stdout:

```text
Hello from a class-path JAR
moduleName=null
isNamed=false
```

Kết quả xác nhận lớp `Main` được nạp trong unnamed module: tên module là `null`, và `isNamed()` trả về `false`. Thư viện `Greeter` được tìm thấy qua JAR trên class path.

## 5. Ứng dụng class path dùng API của named module

Unnamed module có thể đọc các named module đã được phân giải trong cấu hình chạy. Nếu ứng dụng class path cần dùng một module trên module path, module đó phải được đưa vào tập module gốc khi khởi động nếu chưa được module khác yêu cầu. Dùng `--add-modules` để yêu cầu phân giải module đó.

Ví dụ module API có descriptor:

```java
module com.example.api {
    exports com.example.api;
}
```

Package `com.example.api` phải được export không giới hạn cho module nhận. Ứng dụng class path có thể gọi kiểu `public` trong package được export:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println(com.example.api.Greeting.message());
        System.out.println("unnamed=" + !Main.class.getModule().isNamed());
    }
}
```

Giả sử module đã được biên dịch vào `mods` và lớp ứng dụng vào `app-classes`, lệnh chạy là:

```bash
java --module-path mods --add-modules com.example.api -cp app-classes com.example.app.Main
```

Đây là chiều tương tác thuận tiện khi giữ ứng dụng cũ trên class path nhưng muốn dùng API đã modular hóa. Unnamed module có thể đọc named module đã được phân giải; package của named module vẫn phải được export phù hợp.

## 6. Named module sử dụng JAR đang nằm trên class path

Chiều ngược lại có quy tắc khác. Named module **không tự động đọc unnamed module**, nên một named module không thể chỉ viết `requires` để phụ thuộc vào JAR đang nằm trên class path.

Trong giai đoạn tương thích, có thể thêm quan hệ đọc bằng tùy chọn:

```text
--add-reads com.example.app=ALL-UNNAMED
```

`ALL-UNNAMED` là đích đặc biệt của tùy chọn `--add-reads`, đại diện cho các unnamed module. Ví dụ descriptor của ứng dụng vẫn có thể là:

```java
module com.example.app {
}
```

Giả sử `Main.java` trong module `com.example.app` gọi `com.example.greeter.Greeter` từ `lib/greeter.jar`. Biên dịch trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac --module-source-path src --class-path lib/greeter.jar --add-reads com.example.app=ALL-UNNAMED -d out -m com.example.app
```

Chạy ứng dụng:

```powershell
java --module-path out --class-path lib/greeter.jar --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
```

Trên Linux hoặc macOS, lệnh tạo thư mục là `mkdir -p out`; các tùy chọn `javac` và `java` còn lại giống nhau.

Khi có `--add-reads`, ví dụ chạy thành công và cho kết quả:

```text
Hello from a class-path JAR
moduleName=com.example.app
isNamed=true
```

Nếu bỏ `--add-reads`, module `com.example.app` không đọc unnamed module chứa `Greeter`; truy cập lớp khi chạy có thể thất bại với `IllegalAccessError` nêu rõ module gọi không đọc unnamed module. Tùy chọn này chỉ thêm quan hệ readability. Nó không biến JAR thành named module, không tự cung cấp các lớp còn thiếu và không thay thế việc export package.

`--add-reads ...=ALL-UNNAMED` phù hợp như cầu nối tương thích có chủ đích. Với ứng dụng modular mới, nên chuyển dependency sang named module hoặc automatic module trên module path để quan hệ phụ thuộc được khai báo và kiểm soát rõ ràng.

## 7. Automatic module là lựa chọn chuyển tiếp cho JAR cũ

Nếu thư viện chưa có `module-info.java`, có thể đặt JAR lên module path để JPMS tạo automatic module. Khi đó module ứng dụng có tên có thể khai báo `requires` tới tên automatic module, thay vì phụ thuộc vào unnamed module.

Ví dụ manifest của thư viện có thể xác định tên ổn định:

```text
Automatic-Module-Name: com.example.greeter
```

Module ứng dụng khi đó khai báo:

```java
module com.example.app {
    requires com.example.greeter;
}
```

Đặt `greeter.jar` trên `--module-path` để nó được phân giải như automatic module. Dùng `jar --describe-module --file lib/greeter.jar` để xem tên module mà JDK nhận diện.

Automatic module giúp di chuyển từng bước nhưng vẫn là cầu nối: nó export toàn bộ package và đọc các named module khác. Khi có thể sửa thư viện, nên cung cấp module descriptor tường minh, xác định API export và dependency cần thiết. Đừng nhầm automatic module với unnamed module: automatic module có tên và có thể được `requires`; unnamed module không có tên để khai báo trong descriptor.

## 8. Lỗi thường gặp

- **`ClassNotFoundException` hoặc `NoClassDefFoundError`:** kiểm tra JAR có trên class path runtime, đường dẫn có đúng và lớp có tồn tại trong JAR không.
- **`module not found`:** nếu lỗi xảy ra khi phân giải `requires`, kiểm tra module path và tên module. Một JAR chỉ nằm trên class path không đáp ứng `requires` có tên.
- **`IllegalAccessError` giữa named và unnamed module:** kiểm tra module gọi có cần đọc class path không. Trong tình huống tương thích, dùng `--add-reads module.name=ALL-UNNAMED` ở cả cấu hình biên dịch và chạy.
- **Package không được truy cập:** kiểm tra package của named module đã được export chưa. `--add-reads` không tự export package.
- **Chạy được trên máy phát triển nhưng lỗi khi triển khai:** so sánh class path/module path của lệnh build và lệnh chạy; đừng giả định dependency lúc biên dịch tự có mặt lúc runtime.
- **Hai phiên bản của cùng lớp hoặc thư viện:** loại bỏ JAR trùng và kiểm soát thứ tự class path. Class path không cung cấp ranh giới module rõ ràng để cô lập phiên bản và package.
- **JAR chạy được trên class path nhưng không dùng được trong `requires`:** kiểm tra xem JAR đang ở class path hay module path. Nếu muốn dùng như module, chuyển JAR lên module path và kiểm tra tên automatic module hoặc descriptor.

## 9. Hướng chuyển ứng dụng cũ sang JPMS

1. **Kiểm kê dependency.** Ghi lại JAR, phiên bản, package được dùng và các thư viện có module descriptor.
2. **Giữ ứng dụng chạy ổn định trên class path trước.** Xác minh class path build/runtime và loại bỏ JAR trùng.
3. **Thử đưa thư viện cũ lên module path.** Kiểm tra tên automatic module bằng `jar --describe-module`; đặt tên ổn định bằng `Automatic-Module-Name` nếu bạn là bên phát hành thư viện.
4. **Modular hóa từng phần.** Tạo module descriptor, khai báo `requires` và chỉ export API thực sự cần thiết.
5. **Giảm các cầu nối tạm.** Đánh giá và loại bỏ `--add-reads ...=ALL-UNNAMED` khi dependency đã trở thành named module.
6. **Kiểm thử cả build và runtime.** Chạy trên đúng JDK mục tiêu, kiểm tra module path, class path, service loading và các đường chạy thực tế.

Không cần chuyển toàn bộ hệ thống trong một lần. Có thể duy trì phần ứng dụng trên class path trong khi một số thư viện đã là named module, miễn là module path có các module cần thiết và các package API được export đúng.

## Tóm tắt phân biệt

| Câu hỏi | JAR trên class path | JAR trên module path |
|---|---|---|
| Thuộc module nào? | Unnamed module của class loader | Named hoặc automatic module |
| Có tên để `requires` không? | Không | Có |
| Có `module-info.java` được dùng để phân giải không? | Không | Có nếu là explicit module; automatic module được suy ra cho JAR không descriptor |
| Named module đọc được mặc định không? | Không | Theo quan hệ module và quy tắc của automatic/explicit module |
| Phù hợp nhất với | Ứng dụng và thư viện class path cũ | Ứng dụng modular và thư viện đang chuyển đổi sang JPMS |

## Tài liệu tham khảo

1. [Java Language Specification, Java SE 24 — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7.5), quy tắc unnamed module và khả năng đọc.
2. [Java Platform Module System — ModuleFinder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html), tìm module từ module path.
3. [Java SE 24 API — Module](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Module.html), API kiểm tra tên, trạng thái named/unnamed và quan hệ module.
4. [The java Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html), tùy chọn `--class-path`, `--module-path`, `--add-modules` và `--add-reads`.
5. [The javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html), tùy chọn class path, module path và module source path.
6. [The jar Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html), tạo JAR và kiểm tra module descriptor.