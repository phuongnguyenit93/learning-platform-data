# Phân biệt giải pháp tạm thời với sửa descriptor lâu dài

## 1. Mục tiêu

Khi chuyển một ứng dụng sang Java Platform Module System (JPMS), có thể gặp lỗi vì module không đọc được module khác, package chưa được export, hoặc thư viện dùng reflection truy cập thành phần bên trong module. Java cung cấp các tùy chọn launcher như `--add-reads`, `--add-exports` và `--add-opens` để điều chỉnh hành vi module graph trong lúc chạy.

Các tùy chọn này hữu ích để chạy thử, hỗ trợ thư viện cũ hoặc làm cầu nối trong quá trình migration. Tuy nhiên, nếu quan hệ phụ thuộc và quyền truy cập là một phần ổn định của thiết kế ứng dụng, cách giải quyết lâu dài thường là sửa `module-info.java` của module mà ta sở hữu, rồi biên dịch và phát hành lại module.

Bài này phân biệt hai cách tiếp cận, chỉ ra mỗi tùy chọn giải quyết loại vấn đề nào và cách chọn phạm vi thay đổi nhỏ nhất.

Sau bài này, bạn có thể:

- Nhận diện lỗi readability, export và reflective access.
- Chọn đúng tùy chọn runtime tương ứng.
- Chuyển một workaround thành khai báo module descriptor phù hợp.
- Hiểu giới hạn của `--add-modules` và `--patch-module`.
- Tránh giữ các quyền truy cập rộng không cần thiết trong cấu hình production.

## 2. Ba quan hệ khác nhau trong JPMS

Trước khi chọn cờ runtime, cần phân biệt ba khái niệm:

**Readability — khả năng đọc module**

Một module chỉ có thể tham chiếu kiểu và API của module khác khi có quan hệ đọc phù hợp. Quan hệ này thường đến từ directive `requires` trong `module-info.java`.

**Export — quyền truy cập package ở mức biên dịch và liên kết**

Một module có thể đọc module khác nhưng vẫn không truy cập được type trong package chưa được module đó export. Directive `exports` xác định package nào được công khai cho module khác.

**Open — quyền truy cập reflection sâu**

Một package được export cho phép truy cập API công khai theo quy tắc ngôn ngữ và module. Điều đó không tự động cho phép reflection truy cập các thành viên private. Directive `opens` cấp quyền mở package cho deep reflection trong runtime.

Ba loại lỗi này không thể thay thế cho nhau. Ví dụ, thêm readability không tự export package; export package cũng không tự mở private member cho reflection.

## 3. Các tùy chọn runtime thường gặp

### --add-reads: bổ sung quan hệ readability

Cú pháp:

~~~bash
java --add-reads <source-module>=<target-module> ...
~~~

Ví dụ:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Tùy chọn này bổ sung quan hệ để module `com.example.app` đọc được module `com.example.legacy` trong lần chạy đó. Nó không tự export package của legacy module. Nếu package cần dùng vẫn chưa được export, ứng dụng còn cần quyền export phù hợp.

Có thể dùng `ALL-UNNAMED` làm target khi muốn thêm readability tới các module unnamed trên classpath:

~~~bash
java --add-reads com.example.app=ALL-UNNAMED ...
~~~

Không nên thêm quan hệ rộng nếu ứng dụng chỉ cần đọc một named module cụ thể.

### --add-exports: export package cho module đích

Cú pháp:

~~~bash
java --add-exports <source-module>/<package>=<target-module> ...
~~~

Ví dụ:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED ...
~~~

Ví dụ này export package nội bộ `sun.nio.ch` của `java.base` cho các module unnamed trong lần chạy hiện tại. Đây thường là workaround khi thư viện cũ trên classpath phụ thuộc vào API nội bộ JDK.

Có thể giới hạn target vào một named module:

~~~bash
java --add-exports java.base/sun.nio.ch=com.example.app ...
~~~

`--add-exports` điều chỉnh quyền truy cập tới các type public trong package được chỉ định. Nó không mở private members cho deep reflection. Nếu lỗi xảy ra khi framework dùng reflection truy cập private field hoặc method, hãy xem xét `--add-opens`.

Tùy chọn `--add-exports` cũng có phiên bản dùng lúc biên dịch với `javac`, để compiler chấp nhận việc tham chiếu package được export bổ sung. Cờ của launcher chỉ giải quyết runtime; nếu source code cần biên dịch với quyền export đó, phải cấu hình compiler tương ứng.

### --add-opens: mở package cho deep reflection

Cú pháp:

~~~bash
java --add-opens <source-module>/<package>=<target-module> ...
~~~

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

Tùy chọn này mở package `java.lang` của `java.base` cho deep reflection từ các module unnamed. Framework có thể dùng quyền này để truy cập private members thông qua reflection trong runtime.

Nên giới hạn module đích nếu biết rõ thư viện nào cần quyền:

~~~bash
java --add-opens java.base/java.lang=com.example.framework ...
~~~

`--add-opens` không phải cách thay thế tổng quát cho `--add-exports`. Nó phục vụ reflective access ở runtime, không làm package trở thành API công khai để source code import tùy ý.

### --add-modules: bổ sung root module cần resolve

Cú pháp:

~~~bash
java --add-modules <module-name>[,<module-name>...] ...
~~~

Ví dụ:

~~~bash
java --add-modules java.sql --module-path mods --module com.example.app/com.example.app.Main
~~~

Tùy chọn này yêu cầu resolver đưa các module được nêu vào tập root modules để resolve. Nó hữu ích khi ứng dụng cần một module có thể quan sát nhưng module đó chưa được kéo vào graph từ các root thông thường.

`--add-modules` không tạo quan hệ readability tùy ý và không export package. Nếu module app cần đọc module được thêm, vẫn phải có quan hệ readability thích hợp, thường là `requires` trong descriptor hoặc một điều chỉnh `--add-reads` có chủ đích.

## 4. Bảng chọn nhanh theo loại lỗi

| Vấn đề | Tùy chọn runtime thường dùng | Khai báo descriptor tương ứng |
| --- | --- | --- |
| Module A cần đọc module B | `--add-reads A=B` | `requires B;` trong A |
| Module B cần công khai package p cho A | `--add-exports B/p=A` | `exports p to A;` trong B |
| Framework cần deep reflection vào package p của B | `--add-opens B/p=A` | `opens p to A;` trong B |
| Cần đưa module M vào tập root để resolve | `--add-modules M` | Không có directive thay thế trực tiếp; kiểm tra root/configuration của ứng dụng |

Descriptor tương ứng chỉ có thể sửa khi bạn sở hữu hoặc có thể phát hành lại module chứa khai báo. Consumer không thể tự sửa `exports` hoặc `opens` bên trong descriptor của một module thư viện bên thứ ba.

## 5. Sửa module-info.java để thể hiện quan hệ lâu dài

Giả sử module app cần dùng API của module library.

Descriptor của app:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Descriptor của library:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Ở đây:

- `requires` khai báo app đọc library.
- `exports` công khai package API cho module đọc library.
- Package nội bộ không cần export vẫn được giữ encapsulated.

Nếu chỉ muốn export package cho một module cụ thể, dùng qualified export:

~~~java
module com.example.library {
    exports com.example.library.api to com.example.app;
}
~~~

Cách này giới hạn module được phép truy cập package, thay vì mở API cho mọi module đọc library.

### Khi cần deep reflection

Nếu framework hợp lệ cần reflection sâu vào một package do bạn sở hữu, có thể khai báo:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
~~~

Directive `opens` không đồng nghĩa với `exports`:

- `exports` phục vụ truy cập API công khai theo quy tắc module.
- `opens` phục vụ reflection sâu trong runtime.
- `opens` không làm package trở thành API để source code module khác import và sử dụng private member.

Nếu cần mở toàn bộ package trong một module cho reflection, có thể dùng dạng open module:

~~~java
open module com.example.domain {
    requires com.example.api;
}
~~~

Một open module mở các package của module cho deep reflection. Khi chỉ một số package cần mở, nên dùng các directive `opens` có phạm vi cụ thể để giữ encapsulation tốt hơn.

## 6. Ví dụ chuyển workaround thành descriptor

Giả sử ứng dụng hiện chạy được nhờ lệnh:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --add-exports com.example.legacy/com.example.legacy.api=com.example.app \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Lệnh trên đang bổ sung hai điều kiện:

1. App đọc được module legacy.
2. Package `com.example.legacy.api` được export cho app.

Nếu bạn sở hữu cả hai module, hãy thể hiện các quan hệ này trong descriptor.

Module app:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Module legacy:

~~~java
module com.example.legacy {
    exports com.example.legacy.api to com.example.app;
}
~~~

Sau khi biên dịch và phát hành lại hai module, lệnh chạy không cần hai cờ workaround nữa:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Đối với deep reflection, làm tương tự: xác định package và module thực sự cần mở, rồi thêm `opens package.name to target.module;` vào descriptor của module sở hữu package đó nếu đây là yêu cầu thiết kế ổn định.

## 7. --patch-module không phải sửa descriptor

Cú pháp:

~~~bash
java --patch-module <module>=<path> ...
~~~

Ví dụ:

~~~bash
java --patch-module com.example.app=build/patches/app ...
~~~

`--patch-module` đưa thêm class hoặc resource vào nội dung của một module hiện có trong runtime. Nó thường phục vụ test, instrumentation hoặc compatibility workaround có kiểm soát.

Nó không sửa nội dung `module-info.class` theo nghĩa cập nhật descriptor đã phát hành. Không nên dùng patch module như cách thay thế lâu dài cho việc thiết kế lại dependency, export hoặc opens.

Nếu module cần một package API mới, hãy sửa source và descriptor của module rồi build lại. Nếu đang test một thay đổi class trước khi đóng gói, patch module có thể là công cụ tạm thời phù hợp.

## 8. Cách đặt tùy chọn vào lệnh chạy

Các tùy chọn module của launcher được đặt trước tùy chọn xác định ứng dụng, ví dụ `-m` hoặc `-jar`.

Chạy modular application:

~~~bash
java --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Chạy executable JAR trên classpath:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar app.jar
~~~

Nếu cần nhiều quyền, có thể khai báo nhiều tùy chọn:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --add-exports com.example.legacy/com.example.legacy.api=com.example.app \
     --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Hãy lưu cấu hình launch trong script hoặc cấu hình deployment có kiểm soát nếu workaround phải được áp dụng nhất quán. Điều này giúp các môi trường chạy cùng một tập tham số và tránh việc mỗi máy phát triển tự thêm cờ khác nhau.

## 9. Giới hạn và rủi ro của workaround

Các cờ runtime có phạm vi ảnh hưởng rõ ràng, nhưng nếu giữ chúng lâu dài mà không quản lý sẽ tạo ra chi phí bảo trì:

- **Ẩn lỗi thiết kế module:** dependency hoặc package boundary chưa đúng có thể bị che đi bởi các quyền được cấp thêm.
- **Tăng phạm vi truy cập:** `ALL-UNNAMED` cấp quyền cho toàn bộ unnamed modules, rộng hơn một module đích cụ thể.
- **Phụ thuộc cấu hình khởi chạy:** chạy qua IDE, service wrapper, container hoặc script khác có thể quên truyền các cờ cần thiết.
- **Phụ thuộc implementation nội bộ:** package như `sun.nio.ch` không phải API được cam kết ổn định. Bản JDK mới có thể thay đổi hoặc loại bỏ implementation.
- **Khó đóng gói và kiểm soát:** quyền truy cập nằm trong tham số triển khai thay vì contract module được review cùng source.

Từ JDK 17, cơ chế strong encapsulation đối với các package nội bộ của JDK được áp dụng chặt chẽ; tùy chọn cũ `--illegal-access` đã bị loại bỏ. Khi thư viện cũ truy cập nội bộ JDK, hãy ưu tiên nâng cấp thư viện hoặc chuyển sang API được hỗ trợ. Cờ `--add-opens` hay `--add-exports` chỉ nên là cầu nối có phạm vi và thời hạn rõ ràng.

## 10. Quy trình xử lý nên áp dụng

Khi gặp lỗi module access, thực hiện theo trình tự:

1. Đọc chính xác thông báo lỗi để xác định đó là readability, export hay deep reflection.
2. Xác định module nguồn, package và module đích được nhắc đến trong lỗi.
3. Kiểm tra descriptor bằng `jar --describe-module` hoặc `java --describe-module`.
4. Nếu cần xác nhận giả thuyết nhanh, thêm đúng một cờ runtime với target hẹp rồi chạy lại.
5. Nếu workaround xác nhận đúng nguyên nhân, xác định module nào thuộc quyền sở hữu của dự án.
6. Với module do dự án sở hữu, sửa `requires`, `exports` hoặc `opens` cho đúng contract, rồi build và test lại.
7. Với thư viện bên thứ ba, ưu tiên nâng cấp hoặc thay thư viện. Nếu buộc phải giữ workaround, quản lý cờ trong cấu hình triển khai và ghi rõ dependency nào yêu cầu quyền đó.
8. Sau khi descriptor hoặc thư viện đã được sửa, bỏ cờ tạm thời và xác nhận ứng dụng vẫn chạy.

Không thêm tất cả các cờ cùng lúc ngay từ đầu. Thay đổi từng quyền nhỏ giúp xác định chính xác nguyên nhân và tránh cấp quyền thừa.

## 11. Ghi nhớ

- `--add-reads` bổ sung readability; descriptor tương ứng thường là `requires`.
- `--add-exports` công khai package cho module đích; descriptor tương ứng là `exports`.
- `--add-opens` mở package cho deep reflection; descriptor tương ứng là `opens`.
- `--add-modules` bổ sung root module cần resolve, không thay thế `requires`, `exports` hoặc `opens`.
- `--patch-module` thêm nội dung vào module khi chạy, không phải cách sửa descriptor lâu dài.
- Cờ launcher phù hợp để chẩn đoán, thử nghiệm hoặc làm cầu nối migration.
- Quan hệ ổn định và thuộc quyền sở hữu của dự án nên được thể hiện trong `module-info.java`, kiểm thử và phát hành cùng module.

Hãy xem workaround runtime như một bằng chứng giúp xác định quyền nào đang thiếu. Khi đã biết nguyên nhân và kiểm soát được module liên quan, chuyển quan hệ đó vào descriptor phù hợp để cấu hình chạy trở nên đơn giản, nhất quán và dễ bảo trì.
