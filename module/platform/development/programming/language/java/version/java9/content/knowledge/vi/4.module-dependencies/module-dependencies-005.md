# Mô-đun gốc và quá trình phân giải đồ thị

## Mục tiêu

JPMS không tự động nạp mọi module chỉ vì chúng xuất hiện trên module path. Khi khởi chạy một ứng dụng dạng named module, module system bắt đầu từ một tập **root module** (mô-đun gốc), lần theo các directive `requires` để xác định những module cần có, sau đó kiểm tra và tạo cấu hình module có thể chạy.

Quá trình đó được gọi là **module resolution** (phân giải module). Kết quả là một cấu hình gồm các module đã được chọn cùng những quan hệ phụ thuộc cần thiết. Cấu hình này là nền tảng để JVM thiết lập readability và tải lớp trong module layer.

Sau bài này, bạn có thể:

- Giải thích root module và cách launcher chọn root.
- Phân biệt module nằm trên module path với module thực sự được phân giải.
- Mô tả cách module system lần theo `requires` để tạo dependency closure.
- Hiểu vai trò của `--module`, `--add-modules`, `--limit-modules` và `--module-path`.
- Phân biệt tập module được phân giải với khả năng đọc giữa các module.
- Dùng công cụ JDK để quan sát và chẩn đoán module resolution.

Các ví dụ dùng cú pháp JPMS hiện hành và tương thích JDK 17 trở lên.

## 1. Root module là gì?

**Root module** là module được chọn làm điểm bắt đầu khi module system phân giải một cấu hình. Root có thể là module ứng dụng được chỉ định khi khởi chạy hoặc module được thêm rõ ràng bằng tùy chọn launcher.

Ví dụ, lệnh:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

chỉ định:

- `--module-path mods`: nơi tìm các module ứng dụng.
- `--module com.example.app/com.example.app.Main`: chạy class Main thuộc module `com.example.app`.
- `com.example.app` là root module của ứng dụng trong lần khởi chạy này.

Root không có nghĩa là module không phụ thuộc vào module khác. Root chỉ là điểm bắt đầu để module system lần theo dependency.

Nếu `com.example.app` khai báo:

~~~java
module com.example.app {
    requires com.example.model;
}
~~~

thì `com.example.app` là root, còn `com.example.model` được đưa vào cấu hình do quan hệ `requires`.

Đồ thị ban đầu:

~~~text
Root: com.example.app

com.example.app ──requires──> com.example.model
        │                              │
        └──────── implicit requires ───┤
                                       ▼
                                   java.base
~~~

Mọi named module, ngoại trừ `java.base`, có dependency ngầm định đến `java.base`. Vì vậy `java.base` luôn xuất hiện trong cấu hình của ứng dụng modular thông thường.

## 2. Module path và tập module có thể quan sát

Trước khi lần theo dependency, module system cần xác định những module nào có thể tìm thấy.

Nguồn module thường gặp:

- **System modules**: các module thuộc runtime image/JDK hiện tại, ví dụ `java.base`, `java.logging`, `java.sql`.
- **Application modules**: các modular JAR hoặc thư mục module đã biên dịch được đặt trên `--module-path`.
- **Upgrade module path**: cơ chế thay thế một số module hệ thống trong các tình huống triển khai đặc thù; ứng dụng thông thường thường chỉ cần module path.

Một module nằm trên module path mới chỉ là module có thể được tìm thấy. Nó chưa chắc đã được đưa vào cấu hình đang chạy.

Ví dụ, thư mục `mods` có ba module:

~~~text
mods/
├── com.example.app/
├── com.example.model/
└── com.example.audit/
~~~

Nếu app chỉ khai báo `requires com.example.model`, module audit không tự động được phân giải chỉ vì nó nằm cạnh hai module còn lại.

Điều này giúp ứng dụng chỉ đưa vào cấu hình những module có liên quan đến root set và dependency của chúng.

### Module descriptor là nguồn khai báo dependency

Module descriptor nằm trong file `module-info.class`, được biên dịch từ `module-info.java`. Nó khai báo tên module và các directive như:

~~~java
module com.example.app {
    requires com.example.model;
    requires java.logging;
}
~~~

Module system dùng descriptor để tìm các dependency theo **tên module**. Tên package, tên class hay tên file JAR không thay thế cho tên module trong directive `requires`.

## 3. Quá trình phân giải đồ thị

Có thể hình dung module resolution qua các bước sau.

### Bước 1: Xác định tập module có thể quan sát

Module system tìm các module trong những nguồn được cấu hình, chẳng hạn system modules và application module path. `ModuleFinder` là API chuẩn dùng để tìm module reference từ các nguồn này.

Mỗi tên module phải xác định được một module phù hợp trong tập module có thể quan sát. Nếu dependency bắt buộc không tìm thấy, quá trình phân giải thất bại.

### Bước 2: Chọn root set

Root set là tập module bắt đầu của lần phân giải. Khi chạy named module bằng `--module`, module ứng dụng được chỉ định là root. Tùy chọn `--add-modules` có thể bổ sung thêm root.

Ví dụ:

~~~bash
java --module-path mods --add-modules com.example.audit --module com.example.app/com.example.app.Main
~~~

Lúc này root set gồm:

~~~text
com.example.app
com.example.audit
~~~

Hai module đều được yêu cầu phân giải. Điều đó không tự tạo quan hệ readability giữa chúng: app không đọc audit nếu descriptor của app không khai báo một quan hệ phù hợp.

### Bước 3: Lần theo các directive `requires`

Với mỗi root, module system đọc module descriptor và tìm những module được yêu cầu. Các module dependency được tìm thấy tiếp tục được kiểm tra descriptor để lần theo dependency của chúng.

Ví dụ:

~~~text
Root: com.example.app

com.example.app
    └── requires com.example.service
            └── requires com.example.model
                    └── implicit requires java.base
~~~

Tập module cần phân giải là closure của root set theo các dependency bắt buộc. Quá trình tiếp tục cho đến khi không còn dependency mới cần bổ sung.

`requires transitive` cũng là một dependency và module được yêu cầu vẫn phải được phân giải. Modifier `transitive` còn ảnh hưởng đến readability: module đọc module hiện tại cũng đọc dependency được truyền tiếp.

### Bước 4: Xử lý dependency tùy chọn và service binding

Dependency khai báo bằng `requires static` bắt buộc phải có khi biên dịch, nhưng có thể vắng mặt khi chạy. Nếu module tùy chọn không có trong môi trường runtime, việc thiếu nó không tự động làm module resolution thất bại. Code sử dụng phần tích hợp tùy chọn phải được thiết kế để không nạp hoặc gọi class của dependency khi dependency vắng mặt.

Service là một cơ chế riêng. Module tiêu thụ service khai báo `uses`; module cung cấp implementation khai báo `provides ... with ...`. Các directive này không giống một cạnh `requires` trực tiếp. API `Configuration.resolveAndBind` có thể mở rộng quá trình phân giải bằng cách tìm và liên kết những module cung cấp service cần thiết. Công cụ `jlink` có tùy chọn `--bind-services` cho mục tiêu tạo runtime image.

### Bước 5: Kiểm tra tính hợp lệ

Module system kiểm tra cấu hình đã chọn. Một số tình huống có thể làm resolution thất bại:

- Dependency bắt buộc không tìm thấy.
- Có module trùng tên trong cấu hình có thể quan sát.
- Đồ thị dependency tạo chu trình không hợp lệ.
- Các module đọc cùng lúc những package xung đột theo quy tắc module system.
- Descriptor hoặc module artifact không hợp lệ.

Khi cấu hình không hợp lệ, JVM không tiếp tục khởi chạy ứng dụng như thể dependency đã được giải quyết.

### Bước 6: Tạo cấu hình và module layer

Kết quả resolution được biểu diễn bởi `Configuration`. Khi chạy ứng dụng thông thường, launcher sử dụng cấu hình boot để tạo môi trường module cho JVM.

Trong ứng dụng cần plugin hoặc nhóm module được nạp độc lập, API `ModuleLayer` có thể tạo layer mới từ một `Configuration`. Mỗi layer có thể có quan hệ parent với layer khác và có class loader được chọn theo cách định nghĩa layer.

Tạo custom layer là nhu cầu nâng cao; ứng dụng thông thường không cần tự triển khai module resolution vì Java launcher đã thực hiện bước này.

## 4. Root set khác với dependency closure

Hai khái niệm này thường bị nhầm lẫn:

- **Root set**: các module được chọn trực tiếp làm điểm bắt đầu.
- **Dependency closure**: các module được đưa vào do root và các module dependency tiếp tục yêu cầu.

Ví dụ:

~~~text
Root set:
{ com.example.app }

Dependency closure:
{ com.example.app, com.example.service, com.example.model, java.base }
~~~

Nếu thêm audit bằng `--add-modules`:

~~~text
Root set:
{ com.example.app, com.example.audit }

Dependency closure:
{ com.example.app, com.example.audit, com.example.service,
  com.example.model, java.base }
~~~

Root set chỉ chứa những module được chọn trực tiếp. Các dependency xuất hiện trong closure không tự biến thành root.

Tương tự, module có mặt trên module path nhưng không thuộc root set hoặc closure có thể không được đưa vào cấu hình.

## 5. Các tùy chọn launcher ảnh hưởng đến resolution

### `--module-path`

Chỉ định nơi tìm application modules:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Có thể chỉ định nhiều đường dẫn, phân tách bằng dấu phân cách đường dẫn của hệ điều hành. Trên Windows dùng dấu chấm phẩy; trên Linux và macOS dùng dấu hai chấm.

### `--module` hoặc `-m`

Chỉ định module và class chính:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Module `com.example.app` trở thành root của ứng dụng.

### `--add-modules`

Bổ sung một hoặc nhiều module vào root set:

~~~bash
java --module-path mods --add-modules com.example.audit --module com.example.app/com.example.app.Main
~~~

Có thể chỉ định nhiều tên module, phân tách bằng dấu phẩy. Token đặc biệt `ALL-MODULE-PATH` chọn tất cả module tìm thấy trên module path làm root:

~~~bash
java --module-path mods --add-modules ALL-MODULE-PATH --module com.example.app/com.example.app.Main
~~~

Dùng token này có chủ đích vì nó có thể đưa vào cấu hình nhiều module không cần thiết đối với ứng dụng.

### `--limit-modules`

Giới hạn tập module có thể quan sát khi phân giải:

~~~bash
java --limit-modules java.base,java.logging --module-path mods --module com.example.app/com.example.app.Main
~~~

Nếu một dependency bắt buộc bị loại khỏi tập module có thể quan sát, resolution có thể thất bại. Tùy chọn này hữu ích khi muốn giới hạn module hệ thống có thể được dùng trong môi trường chạy.

### `--show-module-resolution`

Hiển thị các module và quan hệ được phân giải:

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Đầu ra thường có các dòng dạng:

~~~text
root com.example.app ...
com.example.app requires com.example.model ...
~~~

Ngoài các module ứng dụng, đầu ra có thể chứa những module hệ thống và quan hệ service binding do JDK thiết lập.

## 6. Ví dụ thực hành: module không được chọn làm root

Ví dụ có ba module. App phụ thuộc model; audit độc lập và không được app yêu cầu.

Cấu trúc thư mục:

~~~text
module-demo/
└── src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Customer.java
    ├── com.example.audit/
    │   ├── module-info.java
    │   └── com/example/audit/Audit.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### Module model

File `src/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model;
}
~~~

File `src/com.example.model/com/example/model/Customer.java`:

~~~java
package com.example.model;

public record Customer(String id) {
}
~~~

### Module audit

File `src/com.example.audit/module-info.java`:

~~~java
module com.example.audit {
    exports com.example.audit;
}
~~~

File `src/com.example.audit/com/example/audit/Audit.java`:

~~~java
package com.example.audit;

public final class Audit {
    public static String status() {
        return "audit-ready";
    }
}
~~~

### Module app

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.model;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        System.out.println("Customer " + new Customer("C-001").id());
    }
}
~~~

### Biên dịch cả ba module

Chạy từ thư mục `module-demo`:

~~~bash
javac -d out --module-source-path src -m com.example.model,com.example.audit,com.example.app
~~~

Lệnh biên dịch tạo ba module trong thư mục `out`. Việc biên dịch audit không có nghĩa audit sẽ luôn được phân giải khi chạy app.

### Chạy với root mặc định là app

~~~bash
java --show-module-resolution --module-path out --module com.example.app/com.example.app.Main
~~~

Root set có `com.example.app`. Module model được phân giải vì app khai báo `requires com.example.model`. Audit có mặt trên module path nhưng không nằm trong closure của app, vì vậy nó không được chọn.

Kết quả stdout của chương trình:

~~~text
Customer C-001
~~~

### Bổ sung audit vào root set

Chạy lại:

~~~bash
java --show-module-resolution --module-path out --add-modules com.example.audit --module com.example.app/com.example.app.Main
~~~

Lúc này `com.example.audit` cũng được phân giải như một root bổ sung. App vẫn in cùng kết quả:

~~~text
Customer C-001
~~~

App không đọc audit chỉ vì audit đã được đưa vào cấu hình. Muốn sử dụng public API của audit, app vẫn cần một quan hệ readability phù hợp và package tương ứng phải được export.

## 7. Readability graph và resolved module set

Module resolution và readability liên quan chặt chẽ nhưng trả lời hai câu hỏi khác nhau:

- **Resolved module set**: những module nào đã được chọn và phân giải trong cấu hình?
- **Readability graph**: module nào được phép đọc module nào?

Ví dụ, `--add-modules com.example.audit` có thể đưa audit vào resolved module set mà không làm app đọc audit. Ngược lại, `requires transitive` truyền readability từ một dependency đã được phân giải sang module đọc module hiện tại.

Một module muốn sử dụng kiểu public từ module khác cần đáp ứng cả hai điều kiện:

1. Module cung cấp phải có trong cấu hình và module sử dụng phải đọc được nó.
2. Package chứa kiểu phải được export cho module sử dụng.

`exports` không chọn root và không tự đưa module vào dependency closure. `opens` chỉ điều khiển reflective access ở runtime, không thay thế dependency hoặc readability.

## 8. Module tự động và classpath trong quá trình phân giải

Khi một JAR không có explicit module descriptor được đặt trên module path, nó có thể được coi là **automatic module**. Tên module được suy ra theo quy tắc đặt tên của module system hoặc được xác định qua metadata của JAR.

Automatic module là cơ chế hỗ trợ chuyển đổi thư viện từ classpath sang module path. Nó có quy tắc readability/export rộng hơn explicit named module và có thể làm đồ thị lớn hơn. Với module mới, nên ưu tiên modular JAR có `module-info.java` rõ ràng.

JAR đặt trên classpath thuộc unnamed module. Unnamed module có quy tắc readability riêng; nó không tự biến thành named module. Khi học hoặc triển khai JPMS, hãy xác định rõ ứng dụng đang dùng classpath hay module path để tránh hiểu sai kết quả resolution.

## 9. Lỗi thường gặp và cách chẩn đoán

### Module không tìm thấy

Ví dụ: `java.lang.module.FindException: Module com.example.model not found`.

Kiểm tra tên module trong `requires`, vị trí modular JAR hoặc exploded module, và đường dẫn `--module-path`.

### Module có trên module path nhưng không được phân giải

Đây thường là hành vi đúng nếu module không thuộc root set hoặc dependency closure. Nếu cần module độc lập đó trong cấu hình, thêm nó bằng `--add-modules`.

### Thiếu dependency do giới hạn module

`--limit-modules` có thể làm module cần thiết không còn quan sát được. Hãy kiểm tra tập module bị giới hạn và các directive `requires` trong dependency chain.

### Đồ thị dependency có chu trình

Nếu module A yêu cầu B và B lại yêu cầu A, module system không thể phân giải cấu hình hợp lệ. Hãy tách abstraction chung thành module thứ ba hoặc điều chỉnh ranh giới dependency để loại bỏ chu trình.

### Trùng module hoặc xung đột package

Kiểm tra các bản JAR trùng tên module, package bị chia giữa nhiều module được đọc cùng lúc và các artifact cũ còn sót trên module path.

### Công cụ kiểm tra

~~~bash
# Hiển thị module và dependency được phân giải khi chạy
java --show-module-resolution --module-path out --module com.example.app/com.example.app.Main

# Kiểm tra tính hợp lệ của các module quan sát được
java --validate-modules --module-path out

# Xem descriptor của một modular JAR
jar --describe-module --file mods/com.example.app.jar

# Phân tích dependency module từ bytecode
jdeps --print-module-deps app.jar
~~~

`--show-module-resolution` hữu ích nhất khi cần xác định root và dependency thực tế. `jar --describe-module` giúp kiểm tra descriptor đã đóng gói; `jdeps` hỗ trợ phân tích dependency bytecode để đối chiếu với thiết kế module.

## 10. Nguyên tắc thiết kế và vận hành

- Chọn root theo chức năng thực sự cần chạy; tránh đưa mọi module trên module path vào root set nếu không có lý do.
- Khai báo dependency trực tiếp trong `module-info.java`; giữ dependency graph rõ ràng và không tạo chu trình.
- Dùng `requires transitive` khi dependency là một phần API public mà consumer cần đọc.
- Dùng `requires static` cho dependency tùy chọn ở runtime và bảo đảm code xử lý khi module vắng mặt.
- Phân biệt module đã được phân giải với module mà ứng dụng có readability.
- Giữ module path ổn định giữa môi trường build, test và production.
- Khi dùng `--limit-modules`, kiểm tra toàn bộ dependency closure trước khi triển khai.
- Với plugin hoặc module nạp động, tìm hiểu `Configuration` và `ModuleLayer` thay vì cố thay đổi boot layer sau khi JVM đã khởi động.
- Quan sát resolution bằng `--show-module-resolution` khi gặp lỗi chỉ xuất hiện ở runtime.

## Tóm tắt

Root module là điểm bắt đầu của module resolution. Java launcher chọn module chính làm root và có thể bổ sung root bằng `--add-modules`. Module system tìm các module quan sát được trên system modules và module path, lần theo dependency `requires` để tạo dependency closure, kiểm tra tính hợp lệ rồi tạo cấu hình module cho JVM. Một module có trên module path chưa chắc được phân giải; một module đã được phân giải cũng chưa chắc được app đọc. Hiểu rõ root set, dependency closure và readability graph giúp kiểm soát chính xác module nào có mặt và module nào được phép sử dụng API của module khác.

## Tài liệu tham khảo chính thức

- [Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java SE 26 API — Configuration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/Configuration.html)
- [Java SE 26 API — ModuleFinder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [Java SE 26 API — ModuleLayer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java Language Specification 26 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html)
