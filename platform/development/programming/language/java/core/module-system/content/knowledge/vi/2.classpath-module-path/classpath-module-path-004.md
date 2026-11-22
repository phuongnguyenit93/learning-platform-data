# Named module, automatic module và unnamed module

## 1. Ba cách một thư viện Java tham gia vào ứng dụng

Khi một ứng dụng Java dùng nhiều thư viện JAR, vị trí đặt JAR quyết định cách Java phân loại chúng. Với JPMS (Java Platform Module System, từ Java 9), một thư viện có thể được xử lý theo ba dạng thường gặp:

- **Explicit named module**: module có descriptor `module-info.java` (được biên dịch thành `module-info.class`). Tên module và các quan hệ phụ thuộc, package công bố được khai báo tường minh.
- **Automatic module**: JAR chưa có module descriptor nhưng được đặt trên module path. Module system tạo một descriptor tổng hợp cho JAR đó.
- **Unnamed module**: các lớp được nạp từ classpath thuộc unnamed module của class loader tương ứng. Module này không có tên và không có descriptor.

Automatic module cũng là một named module vì nó có tên trong module graph. Điểm khác biệt là descriptor của nó được suy ra tự động, trong khi explicit named module có descriptor do tác giả thư viện khai báo. Unnamed module không có tên để một module khác khai báo `requires`.

## 2. Explicit named module: hợp đồng module được khai báo rõ

Một explicit named module thường được đóng gói trong modular JAR, có `module-info.class` ở thư mục gốc JAR, hoặc tồn tại dưới dạng exploded module trong thư mục đầu ra.

Ví dụ:

~~~java
module com.acme.customer {
    requires java.sql;
    requires com.acme.logging;

    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

Descriptor trên thể hiện các phần chính:

- Tên module là `com.acme.customer`.
- Module đọc `java.sql` và `com.acme.logging` thông qua `requires`.
- Package `com.acme.customer.api` được công bố cho các module đọc module này.
- Package `com.acme.customer.model` được mở cho reflection sâu từ module `com.acme.persistence`.

Mặc định, một package trong explicit named module không được export chỉ vì nó chứa lớp `public`. Module khác cần đọc module cung cấp và package cần dùng phải được export phù hợp. Quy tắc truy cập Java như `public`, `protected`, package-private và `private` vẫn được áp dụng sau các kiểm tra ở cấp module.

Explicit named module cho phép chủ thư viện kiểm soát API công khai và giữ package triển khai ở bên trong module. Đây là dạng nên hướng tới khi thư viện đã sẵn sàng tham gia JPMS đầy đủ.

## 3. Automatic module: cầu nối cho JAR chưa có module-info

Một JAR không chứa `module-info.class`, khi được đặt trên **module path**, có thể được module system coi là automatic module. Java tạo một module descriptor tổng hợp cho JAR đó, vì vậy một named module khác có thể khai báo `requires` tới nó.

### Tên automatic module được xác định như thế nào?

Có hai trường hợp:

1. Nếu manifest của JAR có thuộc tính `Automatic-Module-Name`, giá trị đó được dùng làm tên module.
2. Nếu không có thuộc tính này, tên module được suy ra từ tên file JAR theo quy tắc đặt tên của module system, bao gồm việc xử lý phần phiên bản và các dấu phân cách.

Ví dụ, manifest của một thư viện có thể chứa:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Một module ứng dụng có thể khai báo:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Khi tên module được suy ra từ tên file, đổi tên file JAR có thể làm thay đổi tên module mà ứng dụng phải yêu cầu. Với thư viện do nhóm phát triển kiểm soát, nên đặt `Automatic-Module-Name` ổn định trước khi phát hành để người dùng không phụ thuộc vào tên file cụ thể.

Có thể xem tên module mà JAR cung cấp bằng lệnh:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

### Automatic module có những quyền gì?

Automatic module được thiết kế để thư viện cũ có thể tham gia module path với ít thay đổi:

- Tất cả package của automatic module được export.
- Automatic module đọc tất cả các module khác trong cấu hình, kể cả các unnamed module.
- Named module có thể khai báo `requires` tới tên automatic module.
- JAR vẫn chưa có hợp đồng phụ thuộc và ranh giới package do tác giả khai báo đầy đủ như explicit named module.

Việc đọc và export rộng giúp migration dễ hơn, nhưng cũng làm giảm lợi ích đóng gói của JPMS. Một module có thể vô tình phụ thuộc vào package của thư viện khác mà nó chưa khai báo trực tiếp trong descriptor. Vì vậy, automatic module phù hợp như bước chuyển tiếp; không nên xem nó là kết quả thiết kế module cuối cùng.

## 4. Unnamed module: thế giới classpath truyền thống

Các lớp được nạp từ classpath thuộc unnamed module gắn với class loader tương ứng. Mỗi class loader có unnamed module của riêng nó. Unnamed module không có tên và không có `module-info.java`.

Ví dụ chạy ứng dụng theo classpath:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Các lớp trong `app.jar` và những thư viện trên classpath được nạp vào unnamed module của class loader tương ứng. Mô hình này giữ cách sử dụng thư viện truyền thống: không cần từng JAR khai báo `requires` hoặc `exports`.

Unnamed module có các đặc điểm quan trọng:

- Nó đọc tất cả named module trong cùng module layer.
- Tất cả package của nó được export và open.
- Nó không có tên để ghi trong một chỉ thị `requires` của explicit named module.
- Các ranh giới package và dependency không được kiểm soát chặt ở cấp module như với explicit named module.

Điều này giải thích vì sao mã chạy trên classpath thường vẫn truy cập được nhiều thư viện theo cách cũ. Tuy nhiên, một explicit named module không tự động đọc unnamed module. Nếu cần tích hợp tạm thời mã classpath với mã module, có thể bổ sung quan hệ đọc từ dòng lệnh:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --module-path mods -m com.acme.app/com.acme.app.Main
~~~

`ALL-UNNAMED` là tên đích đặc biệt của tùy chọn dòng lệnh, đại diện cho các unnamed module. Đây là cơ chế tương thích khi chuyển đổi; nó không phải tên module có thể dùng trong `module-info.java`.

## 5. Vị trí JAR quyết định cách module system xử lý

Cùng một JAR có thể được xử lý khác nhau tùy vị trí đặt:

| Loại JAR | Đặt trên classpath | Đặt trên module path |
|---|---|---|
| JAR có `module-info.class` | Descriptor module không được dùng; lớp được nạp như mã classpath trong unnamed module | Được xử lý như explicit named module |
| JAR không có `module-info.class` | Lớp thuộc unnamed module | Có thể được xử lý như automatic module |

Ví dụ:

~~~text
app.jar
mods/
  com.acme.domain.jar
  legacy-library.jar
~~~

Giả sử `com.acme.domain.jar` có `module-info.class`, còn `legacy-library.jar` chưa có descriptor:

- Đặt cả hai trên module path: domain là explicit named module; legacy-library là automatic module.
- Đặt `legacy-library.jar` trên classpath: các lớp của nó thuộc unnamed module.
- Đặt một modular JAR trên classpath: module descriptor của nó không tạo ranh giới JPMS trong lần chạy đó; JAR được dùng theo cách classpath.

Vì vậy, khi gặp lỗi về tên module, readability hoặc package visibility, hãy kiểm tra cả nội dung JAR lẫn vị trí JAR được đưa vào lúc biên dịch và lúc chạy.

## 6. So sánh ba dạng module

| Tiêu chí | Explicit named module | Automatic module | Unnamed module |
|---|---|---|---|
| Nguồn tạo descriptor | Tác giả khai báo `module-info.java` | Module system suy ra descriptor từ JAR | Không có descriptor |
| Có tên module | Có, khai báo tường minh | Có, lấy từ manifest hoặc tên JAR | Không |
| Vị trí sử dụng điển hình | Module path | Module path | Classpath |
| Quan hệ đọc | Theo các chỉ thị `requires` và quy tắc JPMS | Đọc tất cả module trong cấu hình | Đọc tất cả named module trong layer |
| Package export | Theo `exports` | Tất cả package | Tất cả package |
| Package mở cho reflection | Theo `opens` hoặc `open module` | Không nên suy ra quyền reflection chỉ từ việc package được export; kiểm tra descriptor/runtime khi tích hợp framework | Tất cả package được open |
| Có thể được named module yêu cầu bằng `requires` | Có | Có | Không |
| Mức độ đóng gói | Rõ ràng, có kiểm soát | Rộng, thuận tiện cho chuyển đổi | Theo mô hình classpath |

Cần phân biệt hai khái niệm: **export** cho phép mã module khác truy cập các kiểu công khai trong package theo quy tắc Java; **open** cho phép reflection sâu. Một package được export không đồng nghĩa package đó được mở cho reflection.

## 7. Dùng lẫn classpath và module path trong giai đoạn chuyển đổi

JPMS cho phép ứng dụng giữ lại một số thư viện trên classpath trong khi các module mới đã chuyển sang module path. Đây là cách migration từng phần, nhưng cần hiểu chiều của quan hệ đọc:

- Unnamed module có thể đọc các named module trong layer của nó.
- Automatic module đọc các named module và unnamed module trong cấu hình.
- Explicit named module chỉ đọc dependency theo các quan hệ module được thiết lập; nó không tự động đọc unnamed module.
- Muốn explicit named module đọc mã classpath trong giai đoạn chuyển tiếp, có thể dùng `--add-reads module=ALL-UNNAMED` ở lệnh chạy. Sau đó nên chuyển dependency đó thành module có tên và khai báo `requires` rõ ràng.

Ví dụ một ứng dụng đã có module descriptor nhưng vẫn cần một thư viện cũ trên classpath:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --class-path "legacy/*" --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Lệnh trên bổ sung khả năng đọc từ module `com.acme.app` tới các unnamed module. Nó chỉ giải quyết readability; các vấn đề khác như thiếu lớp, xung đột package hoặc API không tương thích vẫn cần được xử lý riêng.

## 8. Lộ trình chuyển JAR cũ thành module

Có thể chuyển dần theo các bước sau:

1. **Kiểm kê dependency**: xác định JAR nào đã có `module-info.class`, JAR nào có `Automatic-Module-Name`, và JAR nào chỉ dùng classpath.
2. **Kiểm tra tên module**: dùng `jar --describe-module --file <jar>` để xem tên và descriptor mà Java nhận diện.
3. **Ổn định tên cho thư viện cũ**: nếu có quyền phát hành lại JAR, thêm `Automatic-Module-Name` vào manifest để người dùng có tên module ổn định.
4. **Đưa JAR tương thích lên module path**: khai báo `requires` tới automatic module và kiểm tra ứng dụng ở cả compile time lẫn runtime.
5. **Tạo descriptor tường minh**: khi có thể sửa thư viện, thêm `module-info.java`, chọn dependency cần thiết và chỉ export các package thuộc API.
6. **Loại bỏ cầu nối tạm thời**: khi dependency đã là explicit named module, bỏ các tùy chọn `--add-reads ...=ALL-UNNAMED` và các cấu hình tương thích không còn cần thiết.

Không nên đưa mọi JAR lên module path mà không kiểm tra tên module. Hai JAR có tên module xung đột hoặc các package trùng lặp có thể làm quá trình phân giải module thất bại hoặc khiến cấu hình khó bảo trì.

## 9. Chẩn đoán module mà một JAR cung cấp

Các lệnh sau giúp xác định JAR đang được Java nhận diện như thế nào:

~~~bash
jar --describe-module --file libs/legacy.jar
jar --describe-module --file libs/domain.jar
~~~

Để quan sát các module được phân giải khi chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Để xem dependency module mà công cụ `jdeps` phát hiện:

~~~bash
jdeps --print-module-deps --module-path mods app.jar
~~~

Khi kết quả không như mong đợi, kiểm tra lần lượt:

- JAR có thực sự nằm trên classpath hay module path?
- JAR có `module-info.class` hay chỉ có manifest?
- Tên module được khai báo có khớp với tên mà `jar --describe-module` hiển thị không?
- Explicit named module đã khai báo `requires` tới dependency chưa?
- Package cần dùng đã được export chưa?
- Dependency có xuất hiện trong cấu hình runtime giống như cấu hình compile time không?

## 10. Lỗi thường gặp khi nhầm ba dạng module

- **`module not found`**: JAR chưa nằm trên module path, tên module yêu cầu không khớp, hoặc module không được phân giải.
- **`module A does not read module B`**: module A thiếu quan hệ readability; kiểm tra `requires`, `requires transitive` hoặc cấu hình chuyển tiếp phù hợp.
- **Không thể viết `requires` tới thư viện trên classpath**: thư viện đó thuộc unnamed module và không có tên module. Có thể tạm dùng `--add-reads A=ALL-UNNAMED`, hoặc đưa JAR cũ lên module path để nó trở thành automatic module.
- **Package không được export**: module đã được đọc nhưng package của explicit named module chưa được công bố cho module gọi.
- **Lỗi reflection trong framework**: kiểm tra `opens` hoặc `open module`; `exports` không thay thế `opens`.
- **Tên module thay đổi sau khi đổi tên JAR**: JAR không khai báo `Automatic-Module-Name`, nên tên được suy ra từ filename có thể thay đổi.

## Kết luận

Explicit named module, automatic module và unnamed module là ba cách mã Java tham gia vào cấu hình chạy:

- Explicit named module có descriptor tường minh, kiểm soát dependency và package API.
- Automatic module giúp JAR cũ tham gia module path với tên module và khả năng đọc rộng, phù hợp cho giai đoạn migration.
- Unnamed module giữ cách tổ chức classpath truyền thống, không có tên và không thể được yêu cầu trực tiếp bằng `requires`.

Khi kiểm tra một dependency, hãy xác định JAR nằm ở đâu, Java nhận diện nó thành module nào, rồi mới kiểm tra quan hệ readability và package export. Nắm rõ ba dạng này giúp chuyển ứng dụng sang JPMS từng bước mà vẫn hiểu được ranh giới truy cập ở cả compile time và runtime.
