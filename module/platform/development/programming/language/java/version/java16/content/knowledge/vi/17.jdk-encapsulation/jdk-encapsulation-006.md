# Vai trò của named module, unnamed module và `ALL-UNNAMED`

Java Platform Module System (JPMS) chia mã Java thành các module để mô tả dependency, giới hạn package được truy cập và kiểm soát quyền reflection. Khi chạy ứng dụng, một class có thể thuộc named module hoặc unnamed module tùy cách class đó được nạp. Khái niệm `ALL-UNNAMED` thường xuất hiện trong các tùy chọn dòng lệnh của JVM để cấp một quyền truy cập cho mọi unnamed module.

Ba khái niệm này liên quan chặt chẽ nhưng không đồng nghĩa:

- **Named module** có tên và module descriptor, thường được mô tả trong `module-info.java`.
- **Unnamed module** chứa các class được nạp từ classpath bởi một class loader; nó không có tên module hay descriptor tường minh.
- **`ALL-UNNAMED`** là ký hiệu đặc biệt trong một số tùy chọn module của `javac` và `java`, đại diện cho tất cả unnamed module. Đây không phải tên của một module thực.

Hiểu đúng ba khái niệm giúp giải quyết lỗi `module does not read`, `package is not visible` hoặc `InaccessibleObjectException` khi ứng dụng và thư viện đang chuyển từ classpath sang module path, đặc biệt sau khi JDK tăng cường đóng gói các API nội bộ.

## 1. Named module là gì?

Named module là module có tên xác định và có module descriptor. Với module tường minh, descriptor được khai báo trong file `module-info.java` ở gốc source của module:

```java
module com.example.orders {
    requires java.logging;
    requires com.example.json;

    exports com.example.orders.api;
    opens com.example.orders.model to com.example.json;
}
```

Trong ví dụ:

- `com.example.orders` là tên module.
- `requires java.logging` khai báo dependency module.
- `exports com.example.orders.api` cho phép module khác truy cập các kiểu public trong package API.
- `opens com.example.orders.model to com.example.json` cho phép module JSON thực hiện deep reflection trên package model ở runtime.

Một module tường minh có thể khai báo thêm `uses`, `provides ... with ...`, `requires transitive`, `requires static`, qualified exports và qualified opens. Descriptor tạo thành hợp đồng module để compiler và runtime kiểm tra dependency và ranh giới truy cập.

Named module thường được đặt trên **module path** bằng `--module-path` hoặc `-p`, sau đó được khởi chạy bằng tên module:

```powershell
java --module-path mods -m com.example.orders/com.example.orders.Main
```

`mods` là thư mục chứa module đã biên dịch hoặc các JAR module. Cú pháp `-m module/class` chỉ định module chính và class main.

Một named module tường minh đọc module `java.base` ngầm định và các module được khai báo bằng `requires` (cùng các cạnh readability được bổ sung hợp lệ). Nó không tự động đọc mọi module trong runtime image. Với `requires transitive`, module khác đọc module hiện tại cũng được đọc dependency được đánh dấu transitive; `requires static` biểu diễn dependency cần khi biên dịch nhưng có thể không cần ở runtime.

## 2. Automatic module cũng là named module

Một JAR không có `module-info.class` nhưng được đặt trên module path có thể được xem là *automatic module*. Tên module được lấy từ thuộc tính `Automatic-Module-Name` trong manifest nếu có; nếu không, runtime suy ra từ tên JAR.

Automatic module là cầu nối hỗ trợ chuyển đổi thư viện từ classpath sang module path:

- Nó có tên module và tham gia vào module resolution như một named module.
- Nó đọc các module khác trong configuration theo quy tắc của automatic module.
- Các package của nó được export để hỗ trợ tương thích với thư viện chưa có descriptor tường minh.
- Nó chưa thể hiện ranh giới dependency và package chặt chẽ như một module có `module-info.java` được thiết kế rõ ràng.

Ví dụ một thư viện được đưa vào module path:

```text
mods/
  com.example.orders/
  jackson-databind-2.x.jar
```

Nếu JAR thư viện không có descriptor, nó có thể được resolve thành automatic module với tên lấy từ manifest hoặc tên file. Hãy kiểm tra tên module mà thư viện công bố trước khi viết `requires`; không đoán tên module từ tên artifact Maven.

Automatic module vẫn là **named module**. Vì vậy, `ALL-UNNAMED` không đại diện cho automatic module, kể cả khi JAR đó vốn được dùng trên classpath ở cấu hình triển khai cũ.

## 3. Unnamed module là gì?

Khi chạy ứng dụng bằng classpath (`-cp` hoặc `--class-path`), các class được nạp từ classpath thuộc unnamed module của class loader tương ứng. Unnamed module không có tên và không có `module-info.java`.

Ví dụ:

```powershell
java --class-path "app.jar;lib/*" com.example.Main
```

Trên Windows, dấu phân cách classpath là `;`; trên Linux và macOS thường là `:`. Lệnh trên đặt `app.jar` và các JAR trong `lib` trên classpath, vì vậy các class đó thuộc unnamed module của class loader nạp chúng.

Các đặc điểm quan trọng:

- Mỗi class loader có unnamed module riêng cho các class không thuộc named module.
- Unnamed module không có tên để ghi trong `requires`.
- Unnamed module đọc tất cả named module trong module configuration.
- Các package của unnamed module được xem là exported và open, giúp mã classpath tương tác với public API của named module và hỗ trợ reflection.
- Việc một package được export không loại bỏ các quy tắc truy cập thông thường của Java như `public`, `protected`, package-private và `private`.

Điều này giải thích vì sao ứng dụng chạy trên classpath thường có thể dùng public API của nhiều JDK module mà không cần khai báo `requires` trong `module-info.java`. Tuy nhiên, khi chuyển ứng dụng thành named module, các dependency và quyền truy cập phải được khai báo rõ ràng hơn.

## 4. `ALL-UNNAMED` là gì?

`ALL-UNNAMED` là một target đặc biệt được hỗ trợ bởi các tùy chọn module như `--add-reads`, `--add-exports` và `--add-opens`. Nó có nghĩa là **mọi unnamed module**, bao gồm unnamed module được tạo sau khi JVM khởi động.

Ví dụ:

```powershell
java --add-opens java.base/java.lang=ALL-UNNAMED --class-path app.jar com.example.Main
```

Lệnh này mở package `java.lang` của module `java.base` cho deep reflection từ tất cả unnamed module trong tiến trình. Nó thường được dùng như một biện pháp tương thích tạm thời khi thư viện cũ chạy trên classpath cần reflection sâu vào JDK hoặc vào một named module.

`ALL-UNNAMED` không phải:

- Một module có thể khai báo trong `module-info.java`.
- Một giá trị có thể dùng ở vế trái của `--add-reads`.
- Tên của tất cả named module.
- Tên module của một JAR automatic module.
- Cơ chế tự động export mọi package của tất cả named module.

Nó chỉ đại diện cho unnamed modules ở vị trí target mà tùy chọn tương ứng cho phép. Named module và automatic module không thuộc nhóm này.

## 5. Phân biệt readability, exports và opens

Để một class trong module A truy cập một kiểu public thuộc package của module B, thông thường phải thỏa mãn hai điều kiện:

1. Module A **đọc được** module B (readability).
2. Module B **export** package chứa kiểu đó cho module A (accessibility qua ranh giới module).

Reflection sâu vào thành viên không public cần thêm quyền `opens` cho package ở runtime.

| Cơ chế | Cấp quyền gì? | Không tự cấp quyền gì? |
| --- | --- | --- |
| `requires` / `--add-reads` | Module nguồn đọc được module đích. | Không tự export package hoặc mở deep reflection. |
| `exports` / `--add-exports` | Cho phép truy cập các kiểu và thành viên public trong package đã export. | Không mở private member cho deep reflection. |
| `opens` / `--add-opens` | Cho phép deep reflection vào package ở runtime. | Không làm package trở thành API public để code nguồn import tùy ý. |

Có thể hình dung luồng truy cập như sau:

```text
Module A muốn dùng public type trong package của module B
        |
        +-- A có readability tới B?
        |       +-- Không: khai báo requires hoặc bổ sung read edge phù hợp
        |
        +-- B export package cho A?
                +-- Không: thiết kế exports hoặc bổ sung export có phạm vi hẹp

Framework cần truy cập private member bằng reflection?
        +-- B phải opens package cho module của framework ở runtime
```

Không nên dùng `--add-opens` để chữa mọi lỗi `module does not read` hoặc lỗi package không visible. Hãy xác định chính xác lớp lỗi thuộc readability, exports hay deep reflection.

## 6. `exports` và `opens` trong module-info.java

`exports` công bố package như một phần API mà module khác được phép dùng:

```java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.spi to com.example.plugin;
}
```

Lệnh đầu export package API cho mọi module đọc được `com.example.catalog`. Lệnh thứ hai là *qualified export*: chỉ module `com.example.plugin` được truy cập package SPI.

`opens` cho phép framework dùng reflection sâu vào package:

```java
module com.example.catalog {
    requires com.example.json;

    exports com.example.catalog.api;
    opens com.example.catalog.model to com.example.json;
}
```

Ở đây package model không trở thành public API cho code nguồn bên ngoài. Module JSON được phép truy cập reflective vào các thành viên trong package theo cơ chế reflection của Java.

Có thể khai báo `open module` để mở tất cả package cho deep reflection, nhưng phạm vi đó rộng hơn nhiều. `open module` không tự động export các package cho code nguồn truy cập public API; việc export vẫn cần khai báo riêng. Với ứng dụng hiện đại, ưu tiên qualified `opens package to framework.module` để chỉ cấp quyền cho đúng framework cần thiết.

## 7. Vai trò của `--add-reads`

`--add-reads` bổ sung một cạnh readability trong module graph tại thời điểm chạy (và có tùy chọn tương ứng ở compiler). Ví dụ một named module cần tạm thời đọc các class vẫn đang ở classpath:

```powershell
java --add-reads com.example.app=ALL-UNNAMED --module-path mods --class-path legacy-lib.jar -m com.example.app/com.example.app.Main
```

Ý nghĩa:

- `com.example.app` là named module nguồn.
- `ALL-UNNAMED` là target gồm các unnamed module chứa code classpath.
- Quyền này chỉ bổ sung readability; package và kiểu cần dùng vẫn phải thỏa điều kiện export/accessibility tương ứng.

Trong `module-info.java`, không thể viết `requires ALL-UNNAMED`. `ALL-UNNAMED` không phải module name. Nếu dependency đã có module name ổn định, cách lâu dài là đặt thư viện trên module path và khai báo `requires <library.module>`.

`--add-reads` phù hợp làm cầu nối trong migration hoặc tích hợp đặc biệt. Nếu ứng dụng cần quyền này lâu dài, hãy xem lại cách đóng gói dependency và ranh giới module.

## 8. Vai trò của `--add-exports`

`--add-exports` export một package của named module tới target module ở ngoài module descriptor. Nó hữu ích trong migration hoặc khi phải tương thích với package chưa được export.

Ví dụ tổng quát với package nội bộ của một thư viện:

```powershell
java --module-path mods --add-modules com.example.library --add-exports com.example.library/com.example.library.internal=ALL-UNNAMED --class-path app.jar com.example.Main
```

Trong ví dụ này, module `com.example.library` nằm trên module path còn ứng dụng `app.jar` nằm trên classpath. Lệnh cho code trong unnamed module truy cập các kiểu public thuộc package `com.example.library.internal` của named module `com.example.library`. Nó không cho phép reflection sâu vào private member của package đó.

Khi dùng JDK internal package, ví dụ `sun.*` hoặc `com.sun.*`, `--add-exports` có thể tạm thời làm code cũ chạy được, nhưng API nội bộ không có cam kết tương thích như Java SE API. Ưu tiên thay bằng API công khai được hỗ trợ; không biến một export nội bộ thành phụ thuộc lâu dài.

## 9. Vai trò của `--add-opens` và `ALL-UNNAMED`

Framework như serializer, dependency injection hoặc ORM đôi khi cần truy cập field/constructor không public bằng reflection. Nếu ứng dụng hoặc framework ở unnamed module, có thể tạm mở package của named module cho `ALL-UNNAMED`:

```powershell
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED --module-path mods -m com.example.app/com.example.app.Main
```

Lệnh này mở package `com.example.app.model` của module `com.example.app` cho mọi unnamed module. Nếu framework đã là named module, nên chỉ mở cho đúng module đó:

```powershell
java --add-opens com.example.app/com.example.app.model=com.example.json --module-path mods -m com.example.app/com.example.app.Main
```

Hoặc khai báo trong module descriptor:

```java
module com.example.app {
    requires com.example.json;
    opens com.example.app.model to com.example.json;
}
```

Chỉ dùng `ALL-UNNAMED` khi consumer thực sự nằm trên classpath và không thể chuyển sang named module. Vì nó mở package cho mọi unnamed module, phạm vi quyền rộng hơn việc mở cho một module cụ thể.

`--add-opens` là tùy chọn runtime. Nó không thay thế `exports` để code nguồn import public type khi biên dịch. Nếu lỗi xuất hiện ở compile time, hãy kiểm tra `requires` và `exports` trước.

## 10. So sánh ba tùy chọn dòng lệnh

| Tùy chọn | Ví dụ | Dùng để |
| --- | --- | --- |
| `--add-reads` | `--add-reads com.example.app=ALL-UNNAMED` | Cho named module đọc unnamed module. |
| `--add-exports` | `--add-exports com.example.lib/com.example.lib.internal=ALL-UNNAMED` | Cho target module truy cập public type trong package chưa export. |
| `--add-opens` | `--add-opens com.example.app/com.example.app.model=ALL-UNNAMED` | Cho unnamed module deep reflection vào package ở runtime. |

Định dạng chung của hai tùy chọn export/opens là:

```text
--add-exports <source-module>/<package>=<target-module>
--add-opens   <source-module>/<package>=<target-module>
```

`ALL-UNNAMED` xuất hiện ở vế target. Với `--add-reads`, named module là vế source và `ALL-UNNAMED` có thể là vế target. Các tùy chọn này không làm thay đổi file `module-info.java`: `--add-reads` và `--add-exports` có thể dùng ở compiler/runtime tương ứng, còn `--add-opens` là quyền mở package ở runtime.

## 11. Cách đọc lỗi module phổ biến

| Thông báo hoặc triệu chứng | Vấn đề có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `module X does not read module Y` | Thiếu readability. | Khai báo `requires Y`; chỉ dùng `--add-reads` làm cầu nối có kiểm soát. |
| `package ... is not visible` | Package chưa export hoặc module chưa được đọc. | Kiểm tra cả `requires` và `exports`. |
| `IllegalAccessError` | Truy cập bị chặn ở runtime do module access hoặc binary linkage. | Kiểm tra descriptor, exports và cấu hình module lúc chạy. |
| `InaccessibleObjectException` | Reflection sâu vào package chưa open. | Dùng `opens` có phạm vi hẹp hoặc `--add-opens` tạm thời. |
| Classpath app chạy được nhưng named module không chạy | Classpath trước đây dùng unnamed module với quyền rộng hơn. | Chuyển dependency sang module path, khai báo module descriptor và mở đúng package cho framework. |
| Thư viện hoạt động trên classpath nhưng tên module không resolve | JAR trên module path có tên automatic module khác dự kiến hoặc có vấn đề module resolution. | Kiểm tra `Automatic-Module-Name`, module descriptor và tên module thực tế. |

Không xử lý mọi lỗi bằng cách thêm nhiều `--add-opens ...=ALL-UNNAMED`. Một lỗi readability không được giải quyết bằng opens; một lỗi deep reflection cũng không được giải quyết chỉ bằng exports.

## 12. Đóng gói JDK và strong encapsulation trong Java hiện đại

JPMS giúp JDK đóng gói các module nền tảng và giới hạn truy cập vào package không được công bố. Java 16 đánh dấu bước chuyển quan trọng khi strong encapsulation của các internal API trong JDK trở thành mặc định (JEP 396). Từ Java 17, JEP 403 tiếp tục tăng cường đóng gói các internal element của JDK.

Điều này ảnh hưởng tới thư viện cũ từng dùng reflection hoặc import trực tiếp các class nội bộ như `sun.*`. Việc code cũ từng chạy trên một JDK trước đó không bảo đảm nó tiếp tục chạy khi nâng JDK.

Tùy chọn `--illegal-access` từng là cơ chế tương thích trong giai đoạn chuyển đổi module ban đầu. Từ Java 17, tùy chọn này không còn mở lại các package nội bộ theo cách cũ; không dùng nó làm giải pháp cho ứng dụng hiện đại. Hãy nâng thư viện và chuyển sang Java SE API được hỗ trợ. Nếu thật sự cần compatibility bridge, dùng một `--add-exports` hoặc `--add-opens` cụ thể, có phạm vi hẹp, có ghi nhận và kế hoạch loại bỏ.

Không nên nhầm việc module có tên với việc package đã được export. JDK có thể chứa một package trong module `java.base` nhưng vẫn không export package đó cho ứng dụng. Tương tự, có một class public không đồng nghĩa mọi module đều được phép truy cập class đó qua ranh giới module.

## 13. Quy trình chuyển ứng dụng từ classpath sang named module

Một lộ trình thực tế có thể chia thành các bước:

1. **Lập danh sách dependency:** xác định JAR đang chạy trên classpath, phiên bản và chức năng sử dụng.
2. **Kiểm tra module name:** ưu tiên descriptor chính thức; nếu chưa có, kiểm tra `Automatic-Module-Name` hoặc tên automatic module được suy ra.
3. **Chuyển dependency có hỗ trợ:** đặt JAR phù hợp trên module path và xác nhận module resolution.
4. **Tạo `module-info.java`:** khai báo `requires` cho dependency trực tiếp, chỉ `exports` package API và `opens` package cần reflection.
5. **Xử lý thư viện còn trên classpath:** nếu named module buộc phải đọc chúng trong giai đoạn chuyển tiếp, dùng `--add-reads module=ALL-UNNAMED` có chủ đích.
6. **Xử lý reflection:** ưu tiên qualified `opens` trong descriptor; chỉ dùng `--add-opens ...=ALL-UNNAMED` nếu framework vẫn ở classpath.
7. **Loại bỏ internal API:** thay truy cập JDK internals bằng Java SE API hoặc API được nhà cung cấp hỗ trợ.
8. **Kiểm thử trên JDK mục tiêu:** chạy compile, test, integration test và đóng gói trong đúng cấu hình module path của production.
9. **Thu hẹp workaround:** khi thư viện được nâng cấp hoặc chuyển thành named module, bỏ các quyền `ALL-UNNAMED` không còn cần thiết.

Không cần biến toàn bộ ứng dụng thành named module trong một lần. Có thể chuyển dần dependency, nhưng cần biết rõ JAR nào ở classpath, JAR nào ở module path và module nào đang được cấp quyền bổ sung.

## 14. Ví dụ cấu hình có cả named module và classpath library

Giả sử ứng dụng đã là named module, nhưng một thư viện cũ vẫn nằm trên classpath và cần reflection vào model. Cấu hình tạm thời có thể gồm:

```java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
```

Lệnh chạy:

```powershell
java --add-reads com.example.app=ALL-UNNAMED --add-opens com.example.app/com.example.app.model=ALL-UNNAMED --module-path mods --class-path legacy-json.jar -m com.example.app/com.example.app.Main
```

Hai quyền giải quyết hai vấn đề khác nhau:

- `--add-reads` cho `com.example.app` đọc các class thuộc unnamed module.
- `--add-opens` cho code trong unnamed module reflection sâu vào package model của ứng dụng.

Khi thư viện JSON chuyển sang named module, hãy khai báo `requires com.example.json` và ưu tiên `opens ... to com.example.json` trong `module-info.java`. Khi dependency không còn nằm trên classpath, bỏ `--add-reads ...=ALL-UNNAMED`; nếu còn cần quyền bổ sung ngoài descriptor, target nên là tên module cụ thể.

## 15. Những điểm cần nhớ

- Named module có tên và descriptor; explicit module khai báo bằng `module-info.java`.
- Automatic module vẫn là named module, dù JAR chưa có descriptor tường minh.
- Classpath code thuộc unnamed module của class loader; unnamed module đọc tất cả named module và có các package được export/open.
- `ALL-UNNAMED` là target đặc biệt đại diện cho mọi unnamed module, không phải module thật và không bao gồm automatic module.
- `requires`/`--add-reads` điều khiển readability; `exports`/`--add-exports` điều khiển truy cập public type; `opens`/`--add-opens` cho deep reflection ở runtime.
- `--add-opens` không thay thế `--add-exports` hoặc `--add-reads`.
- Ưu tiên module descriptor và quyền mở package có phạm vi hẹp; chỉ dùng `ALL-UNNAMED` làm cầu nối khi consumer vẫn ở classpath.
- Java 16 và các JDK hiện đại tăng cường strong encapsulation; không dựa vào `--illegal-access` hoặc JDK internal API cho thiết kế mới.

Hãy xem named module là cách khai báo dependency và API rõ ràng, unnamed module là môi trường tương thích cho code classpath, còn `ALL-UNNAMED` là công cụ cấp quyền có phạm vi rộng cho nhóm classpath đó. Khi ứng dụng tiến tới module hóa hoàn chỉnh, hãy thay các quyền `ALL-UNNAMED` bằng dependency và `opens`/`exports` có tên cụ thể để giữ ranh giới module dễ kiểm soát.

## Tài liệu tham khảo

- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [The Java Module System – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [java launcher options – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Module – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
