# Tạo hai named module với requires và exports

## Mục tiêu

Sau bài này, bạn có thể:

- Tạo hai named module độc lập bằng Java Platform Module System (JPMS).
- Viết `module-info.java` cho module cung cấp API và module sử dụng API.
- Dùng `exports` để công khai package và `requires` để khai báo dependency.
- Tổ chức source tree theo tên module và package.
- Biên dịch nhiều module bằng `javac --module-source-path`.
- Chạy ứng dụng bằng module path và hiểu cách JVM resolve hai module.

## 1. Bài thực hành sẽ xây dựng gì?

Ta tạo một ứng dụng nhỏ gồm hai named module:

- `com.acme.greetings`: module thư viện, cung cấp class `Greeter`.
- `com.acme.app`: module ứng dụng, sử dụng `Greeter` để in lời chào.

Module thư viện công khai package `com.acme.greetings.api` bằng `exports`. Module ứng dụng khai báo `requires com.acme.greetings` để có thể đọc và sử dụng API đó.

Dependency direction:

~~~text
+-----------------------+
|     com.acme.app      |
|       Main.java       |
+-----------+-----------+
            |
            | requires
            v
+-----------------------+
|  com.acme.greetings   |
|       Greeter.java    |
|                       |
| exports greetings.api|
+-----------------------+
~~~

Đây là một ví dụ tối thiểu nhưng thể hiện hai directive cốt lõi của named module: module cung cấp quyết định package nào được export; module tiêu thụ khai báo module mà nó cần đọc.

## 2. Tạo cấu trúc thư mục

Tạo project với source root riêng cho từng module:

~~~text
two-modules/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── api/
    │                   └── Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Quy tắc cần nhớ:

- Mỗi named module có một file `module-info.java` ở module root.
- Tên thư mục module trong module source path nên khớp tên khai báo trong descriptor.
- Đường dẫn package bên trong module khớp với câu lệnh `package` trong source.
- `module-info.java` không có khai báo package.
- Mỗi module có thể chứa nhiều package, nhưng chỉ package được export mới là API truy cập thông thường cho module khác.

## 3. Viết module cung cấp API

Trong `src/com.acme.greetings/module-info.java`:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

Directive `exports` công khai package `com.acme.greetings.api` cho các module khác. Nó cho phép module đọc package này truy cập public type và public/protected API theo quy tắc Java.

Tạo class `Greeter` trong `src/com.acme.greetings/com/acme/greetings/api/Greeter.java`:

~~~java
package com.acme.greetings.api;

public final class Greeter {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            name = "World";
        }

        return "Hello, " + name + "!";
    }
}
~~~

Các điểm quan trọng:

- Package của class phải khớp package được export trong descriptor.
- Class cần là `public` để code ở module khác có thể sử dụng.
- Method được consumer gọi cũng phải có mức truy cập phù hợp, ở đây là `public`.
- Class không cần nằm trong package có tên giống module. Module name và package name là hai khái niệm riêng.

Sau bước này, module `com.acme.greetings` đã có một public API nhỏ.

## 4. Viết module ứng dụng sử dụng API

Trong `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

Directive `requires` khai báo rằng module ứng dụng cần đọc module `com.acme.greetings`. Đây là một dependency của module graph.

Tạo class main trong `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.greetings.api.Greeter;

public class Main {

    public static void main(String[] args) {
        Greeter greeter = new Greeter();

        String message = greeter.greet("Java Module System");
        System.out.println(message);
    }
}
~~~

Ứng dụng có thể import `Greeter` vì hai điều kiện được đáp ứng:

1. `com.acme.app` khai báo `requires com.acme.greetings`.
2. `com.acme.greetings` khai báo `exports com.acme.greetings.api`.

Nếu thiếu một trong hai điều kiện, compiler không thể sử dụng API qua module boundary theo cách thông thường.

## 5. Biên dịch cả hai module bằng javac

Mở terminal tại thư mục `two-modules/` và chạy:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
~~~

Ý nghĩa các tùy chọn:

| Thành phần | Ý nghĩa |
|---|---|
| `javac` | Khởi chạy Java compiler |
| `-d out` | Chọn `out/` làm thư mục gốc chứa output |
| `--module-source-path src` | Chỉ định nơi chứa source tree của các module |
| `-m` | Chọn các module cần biên dịch |
| `com.acme.greetings,com.acme.app` | Hai module được đưa vào lần biên dịch |

Compiler đọc descriptor của hai module, tìm dependency từ `requires` và biên dịch các source file cần thiết.

Nếu biên dịch thành công, cấu trúc output có dạng:

~~~text
two-modules/
├── src/
│   ├── com.acme.greetings/
│   └── com.acme.app/
└── out/
    ├── com.acme.greetings/
    │   ├── module-info.class
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── api/
    │                   └── Greeter.class
    └── com.acme.app/
        ├── module-info.class
        └── com/
            └── acme/
                └── app/
                    └── Main.class
~~~

Mỗi module có thư mục output riêng. `module-info.java` được biên dịch thành `module-info.class`; các class được đặt theo package path.

Có thể kiểm tra output bằng cách mở thư mục `out/` hoặc dùng công cụ `jar`/`javap` để xem artifact đã biên dịch.

## 6. Chạy ứng dụng bằng module path

Dùng output root làm module path:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Trong đó:

- `--module-path out` yêu cầu JVM tìm các module trong thư mục `out`.
- `-m` chọn module khởi chạy và main class.
- `com.acme.app` là tên module ứng dụng.
- `com.acme.app.Main` là tên đầy đủ của class chứa `main`.

Kết quả:

~~~text
Hello, Java Module System!
~~~

JVM tìm `com.acme.app`, đọc descriptor để biết module này yêu cầu `com.acme.greetings`, sau đó resolve dependency từ module path. Khi ứng dụng gọi `Greeter.greet`, class thuộc module thư viện được nạp theo cơ chế class loading của module layer.

Lệnh biên dịch và chạy đầy đủ:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

## 7. Hiểu đúng requires và exports

Hai directive này giải quyết hai câu hỏi khác nhau.

### 7.1. requires: module nào cần được đọc?

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

`requires` khai báo dependency giữa module. Nó tạo quan hệ readability cần thiết để module ứng dụng tham chiếu type được cung cấp bởi module thư viện.

`requires` không tự công khai mọi package của module đích. Package vẫn phải được export phù hợp.

### 7.2. exports: package nào được công khai?

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

`exports` công khai package cho module khác. Nếu module không export package, module consumer không thể import public type trong package đó theo cách thông thường, dù đã khai báo `requires`.

`exports` không mở package cho deep reflection vào private member. Reflection sâu là mục đích của `opens`, một directive khác.

### 7.3. Cần cả hai phía

| Module cung cấp | Module sử dụng | Kết quả |
|---|---|---|
| Export package API | Requires module cung cấp | Consumer có thể dùng public API |
| Không export package | Requires module cung cấp | Consumer vẫn không truy cập được package |
| Export package | Không requires module cung cấp | Không có readability cần thiết trong module graph thông thường |
| Export package khác | Requires module cung cấp | Consumer chỉ truy cập package được export phù hợp |

Với ví dụ này, `exports` và `requires` phải cùng trỏ tới đúng tên package/module.

## 8. Thử nghiệm khi bỏ một directive

Các lỗi dưới đây giúp hiểu vai trò của từng khai báo.

### 8.1. Bỏ requires khỏi module ứng dụng

Nếu descriptor ứng dụng chỉ còn:

~~~java
module com.acme.app {
}
~~~

nhưng source vẫn import `com.acme.greetings.api.Greeter`, compiler sẽ báo package/module không được đọc hoặc không hiển thị. Module ứng dụng chưa khai báo dependency cần thiết.

Cách sửa: thêm lại:

~~~java
requires com.acme.greetings;
~~~

### 8.2. Bỏ exports khỏi module thư viện

Nếu descriptor thư viện là:

~~~java
module com.acme.greetings {
}
~~~

thì `com.acme.greetings.api` không được công khai cho module khác. Dù `com.acme.app` có `requires`, compiler vẫn không cho phép truy cập package API đó.

Cách sửa: export đúng package:

~~~java
exports com.acme.greetings.api;
~~~

### 8.3. Export nhầm package

Ví dụ descriptor viết:

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

nhưng class `Greeter` nằm trong `com.acme.greetings.api`. Export package cha không tự động export subpackage. Cần export chính xác:

~~~java
exports com.acme.greetings.api;
~~~

Đây là lỗi thường gặp khi nghĩ rằng export một package sẽ bao gồm tất cả package con.

## 9. Thử thêm package nội bộ

Giả sử thư viện có một package triển khai:

~~~text
com/acme/greetings/internal/Formatter.java
~~~

Nếu descriptor chỉ export `com.acme.greetings.api`, package `com.acme.greetings.internal` vẫn được đóng gói.

Consumer không nên import `Formatter` trực tiếp. Đây là cách module bảo vệ implementation khỏi trở thành dependency công khai ngoài ý muốn.

Nếu một module khác thật sự cần sử dụng một type, hãy xem xét type đó có thuộc API contract hay không. Nếu có, đặt nó trong package API và export rõ ràng. Không export toàn bộ package chỉ để né lỗi compile.

## 10. Thử nghiệm với qualified exports

Nếu chỉ một module consumer được phép truy cập package, có thể dùng qualified export:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api to com.acme.app;
}
~~~

Cách này giới hạn quyền truy cập package cho module `com.acme.app`. Module khác dù có `requires com.acme.greetings` cũng không tự động được truy cập package đó.

Qualified exports hữu ích khi API chỉ dành cho một tập consumer được xác định. Với thư viện công khai cho nhiều ứng dụng, unqualified `exports` thường phù hợp hơn.

## 11. Tách bước compile và run

Trong thực tế, compile và run thường là hai bước riêng.

Biên dịch:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
~~~

Chạy:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Điều này có nghĩa:

- Compiler cần source tree và module descriptor để kiểm tra dependency.
- JVM cần module đã biên dịch trên module path để resolve và chạy.
- Source directory `src` không phải module path runtime trong ví dụ này.
- Output directory `out` chứa các exploded module và được dùng khi chạy.

Nếu chạy mà báo không tìm thấy module, hãy kiểm tra module path có trỏ đúng thư mục cha chứa hai module hay không.

## 12. Đóng gói thành modular JAR (tùy chọn)

Sau khi biên dịch, có thể đóng gói từng exploded module thành modular JAR:

~~~bash
jar --create --file dist/com.acme.greetings.jar -C out/com.acme.greetings .
jar --create --file dist/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Thư mục `dist/` cần tồn tại trước khi chạy lệnh. Các file JAR giữ lại `module-info.class` nên module identity và dependency được bảo toàn.

Chạy từ modular JAR:

~~~bash
java --module-path dist -m com.acme.app/com.acme.app.Main
~~~

Có thể dùng `jar --describe-module` để xem descriptor trong từng JAR:

~~~bash
jar --describe-module --file dist/com.acme.greetings.jar
jar --describe-module --file dist/com.acme.app.jar
~~~

Bước đóng gói không thay đổi quan hệ `requires` và `exports` đã khai báo trong source descriptor.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `module not found` | Module dependency không có trên module path/source path | Kiểm tra tên module và vị trí source/output |
| `package ... is not visible` | Package chưa export hoặc module chưa readable | Kiểm tra cả `exports` và `requires` |
| `module ... does not read ...` | Thiếu `requires` hoặc dependency không có trong graph | Khai báo đúng dependency |
| `package does not exist` | Package name, source path hoặc import sai | Đối chiếu package declaration và folder |
| JVM không tìm thấy main module | Module path trỏ sai thư mục | Trỏ đến thư mục cha chứa module |
| Main class không tìm thấy | Tên class sau dấu / sai hoặc class chưa được compile | Kiểm tra package, class name và output |

Khi debug, kiểm tra theo thứ tự:

1. Source tree có đúng module root và package path không?
2. Mỗi module có `module-info.java` không?
3. Module cung cấp đã export đúng package chưa?
4. Module sử dụng đã requires đúng module chưa?
5. Cả hai module có trong output/module path không?
6. Tên module và tên main class trong lệnh chạy có chính xác không?

## 14. Checklist hoàn thành bài thực hành

- [ ] Có hai module root riêng dưới `src/`.
- [ ] Module `com.acme.greetings` có `module-info.java`.
- [ ] Module thư viện export `com.acme.greetings.api`.
- [ ] Class `Greeter` nằm trong package đã export và có public method.
- [ ] Module `com.acme.app` có `module-info.java`.
- [ ] Module ứng dụng khai báo `requires com.acme.greetings`.
- [ ] Lệnh javac biên dịch được cả hai module.
- [ ] Output có `module-info.class` cho mỗi module.
- [ ] JVM chạy được ứng dụng bằng `--module-path`.
- [ ] Kết quả hiển thị đúng lời chào mong đợi.

## Kết luận

Bài thực hành đã tạo hai named module có quan hệ rõ ràng: `com.acme.greetings` cung cấp public API qua `exports`; `com.acme.app` khai báo dependency qua `requires` và sử dụng API đó.

Hãy ghi nhớ: **requires trả lời module nào cần được đọc; exports trả lời package nào được công khai**. Khi cả hai directive cùng được khai báo chính xác, compiler có thể kiểm tra module dependency và JVM có thể resolve, nạp các module để chạy ứng dụng.
