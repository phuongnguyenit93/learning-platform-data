# Automatic module đọc các module khác

**Automatic module** là named module được tạo ngầm khi một JAR chưa có module descriptor được đặt trên module path. Nó giúp thư viện cũ tham gia JPMS trong giai đoạn chuyển đổi. Một đặc điểm quan trọng của automatic module là nó **đọc tất cả module khác trong cấu hình đã được giải quyết, kể cả unnamed module**.

Quy tắc này giúp một thư viện cũ tiếp tục tham chiếu các dependency mà nó được biên dịch cho mô hình classpath, trong khi vẫn có thể được một ứng dụng module hóa sử dụng. Tuy nhiên, phạm vi đọc rộng của automatic module không có nghĩa mọi JAR trên đĩa đều tự động được nạp, cũng không có nghĩa module khác được kế thừa toàn bộ quyền đọc của automatic module.

## 1. Automatic module hình thành từ đâu?

Một modular JAR tường minh có file `module-info.class` ở gốc JAR. File này khai báo tên module, dependency và package được export/open.

Một JAR cũ không có `module-info.class` khi được đặt trên module path có thể được coi là **automatic module**. Module system tạo descriptor ngầm cho JAR đó. Tên module được xác định theo thứ tự:

1. Thuộc tính `Automatic-Module-Name` trong manifest, nếu có.
2. Nếu không có thuộc tính trên, tên được suy ra từ tên file JAR.

Ví dụ, một JAR có tên `legacy-logging-2.4.jar` có thể được suy ra thành automatic module tên `legacy.logging`. Tên suy ra phụ thuộc vào quy tắc chuẩn hóa tên file và có thể thay đổi nếu tên JAR thay đổi. Thư viện muốn tên module ổn định nên cung cấp `Automatic-Module-Name` trong manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.logging
~~~

Khi đặt JAR này trên module path, module system nhận diện nó bằng tên `com.acme.legacy.logging`. Thuộc tính manifest giúp các module khác khai báo dependency ổn định mà không phụ thuộc tên file phát hành.

Một JAR đặt trên classpath vẫn thuộc unnamed module, kể cả khi manifest có `Automatic-Module-Name`. Automatic module chỉ được hình thành khi JAR được xử lý qua module path.

## 2. Quy tắc đọc rộng của automatic module

Một explicit named module thông thường chỉ đọc các module mà nó khai báo qua `requires`, cùng các quan hệ được truyền tiếp theo quy tắc JPMS. Automatic module có quy tắc đặc biệt: nó đọc tất cả module khác trong cấu hình đã được giải quyết.

Điều này bao gồm:

- Các explicit named module đã được đưa vào cấu hình runtime.
- Các automatic module khác trong cấu hình.
- Các unnamed module gắn với class loader trong phạm vi quy tắc readability của automatic module.

Có thể mô tả ngắn gọn:

~~~text
automatic module
    ├── reads explicit named modules trong configuration
    ├── reads automatic modules trong configuration
    └── reads unnamed modules
~~~

Từ khóa quan trọng là **trong configuration**. Automatic module không tự biến mọi JAR đang nằm trong một thư mục thành module đã được giải quyết. Module cần được tìm thấy và tham gia cấu hình runtime trước khi quan hệ readability có ý nghĩa.

Đặc điểm read-all này giúp thư viện cũ có thể tiếp tục tham chiếu nhiều dependency mà nó vốn sử dụng trên classpath, dù chưa có descriptor để khai báo từng dependency.

## 3. Automatic module cũng export các package của nó

Ngoài khả năng đọc rộng, automatic module export tất cả package của nó. Đây là điểm khác biệt lớn so với explicit named module, nơi tác giả phải chủ động liệt kê package bằng `exports`.

Giả sử JAR cũ chứa:

~~~text
legacy-logging.jar
└── com/acme/logging/
    ├── Logger.class
    └── internal/
        └── LogConfig.class
~~~

Khi được dùng như automatic module trên module path, các package của JAR được export theo quy tắc automatic module. Một named module phụ thuộc vào nó có thể dùng các kiểu public trong package tương ứng mà không cần JAR khai báo `exports`.

Điều này tiện cho migration nhưng làm giảm khả năng đóng gói. Các package nội bộ của thư viện cũ cũng có thể trở nên truy cập được qua module boundary nếu chứa kiểu public. Khi thư viện được module hóa tường minh, tác giả có thể chọn package API và giữ package triển khai ở trạng thái không export.

Readability và export vẫn là hai khái niệm khác nhau. Việc automatic module đọc tất cả module không tự động export package của các module mà nó đọc. Quyền export được quyết định bởi module nguồn.

## 4. Named module sử dụng automatic module như thế nào?

Một explicit named module có thể khai báo `requires` tới automatic module bằng tên module mà module system nhận diện.

Ví dụ, thư mục `mods` có thư viện `legacy-logging-2.4.jar` với manifest khai báo:

~~~text
Automatic-Module-Name: com.acme.legacy.logging
~~~

Ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.legacy.logging;
}
~~~

Mã ứng dụng có thể import kiểu public từ package được automatic module cung cấp:

~~~java
package com.acme.app;

import com.acme.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.info("Application started");
    }
}
~~~

Biên dịch và chạy trên JDK 21:

~~~bash
javac --module-path mods \
      --module-source-path src \
      -d out \
      -m com.acme.app
~~~

~~~bash
java --module-path "out:mods" \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows, thay dấu phân cách module path `:` bằng `;`:

~~~powershell
java --module-path "out;mods" -m com.acme.app/com.acme.app.Main
~~~

Ở đây, ứng dụng có dependency rõ ràng tới automatic module. Khi module `com.acme.app` được giải quyết, automatic module được kéo vào cấu hình. Automatic module có thể đọc các module khác trong cấu hình theo quy tắc read-all của nó.

## 5. Automatic module đọc named module khác mà không cần requires riêng

Giả sử cấu hình có các module sau:

~~~text
com.acme.app
    requires com.acme.legacy.logging

com.acme.legacy.logging
    automatic module

com.acme.metrics
    explicit named module
~~~

Module `com.acme.legacy.logging` không có descriptor để khai báo `requires com.acme.metrics`. Tuy vậy, khi cả hai module đã nằm trong cấu hình được giải quyết, automatic module vẫn đọc được `com.acme.metrics` theo quy tắc đặc biệt của nó.

Nếu mã của thư viện legacy tham chiếu các kiểu public thuộc package được export của `com.acme.metrics`, quan hệ readability này có thể cho phép liên kết và sử dụng các kiểu đó.

Tuy nhiên, module `com.acme.app` không tự động được hưởng khả năng đọc tất cả module của automatic module chỉ vì nó khai báo `requires com.acme.legacy.logging`. Nếu chính mã ứng dụng cần import kiểu từ `com.acme.metrics`, hãy khai báo dependency trực tiếp:

~~~java
module com.acme.app {
    requires com.acme.legacy.logging;
    requires com.acme.metrics;
}
~~~

Cách khai báo trực tiếp làm hợp đồng dependency của ứng dụng rõ ràng và không phụ thuộc vào việc một thư viện trung gian tình cờ là automatic module.

## 6. Automatic module có thể đọc thư viện trên classpath

Một đặc điểm chuyển tiếp quan trọng là automatic module đọc được unnamed module. Điều này giúp thư viện legacy trên module path tiếp tục tham chiếu các dependency vẫn còn nằm trên classpath, trong phạm vi cấu hình và class loader tương ứng.

Ví dụ, một ứng dụng khởi chạy kết hợp module path và classpath:

~~~bash
java --module-path mods \
     --add-modules com.acme.legacy.logging \
     --class-path "lib/legacy-helper.jar:out" \
     com.acme.app.Main
~~~

Trong ví dụ này, `com.acme.legacy.logging` là automatic module được đưa vào cấu hình như root bổ sung. Các lớp từ `legacy-helper.jar` và `out` thuộc unnamed module của class loader classpath. Automatic module có thể đọc unnamed module theo quy tắc của nó.

Nếu ứng dụng chính cũng là named module, hãy khởi chạy bằng `-m` và khai báo các dependency cần thiết trong descriptor. Named module không tự động đọc unnamed module; nếu cần tương thích tạm thời, có thể dùng `--add-reads` với đích `ALL-UNNAMED` cho module named cụ thể.

## 7. Module path không đồng nghĩa mọi JAR đều đã được giải quyết

Một hiểu nhầm phổ biến là: nếu automatic module đọc tất cả module khác, vậy chỉ cần chép mọi JAR vào module path là automatic module có thể dùng tất cả. Cách hiểu này bỏ qua bước module resolution.

Module path là nguồn để module finder quan sát các module. Cấu hình runtime chỉ chứa các module được giải quyết từ root modules, dependency và service binding. Một JAR có thể được tìm thấy nhưng không được đưa vào cấu hình của lần chạy.

Với ứng dụng khởi chạy bằng lớp main trên classpath, có thể yêu cầu module cụ thể làm root:

~~~bash
java --module-path mods \
     --add-modules com.acme.legacy.logging,com.acme.metrics \
     --class-path out \
     com.acme.app.Main
~~~

Hoặc yêu cầu tất cả module quan sát được trên module path làm root:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --class-path out \
     com.acme.app.Main
~~~

Cách thứ hai có thể đưa nhiều module hơn mức ứng dụng cần thiết vào cấu hình. Trong triển khai thực tế, nên chọn root có chủ đích để dependency và phạm vi module runtime dễ hiểu.

Dùng tùy chọn sau để quan sát các module được giải quyết:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.legacy.logging \
     --class-path out \
     com.acme.app.Main
~~~

## 8. Tên automatic module và rủi ro khi đổi tên JAR

Nếu JAR không có `Automatic-Module-Name`, tên module được suy ra từ tên file. Ví dụ, tên `legacy-logging-2.4.jar` có thể được chuẩn hóa thành `legacy.logging`. Khi nhà phát hành đổi tên artifact hoặc cách đặt phiên bản, tên suy ra có thể thay đổi và làm hỏng directive `requires` của ứng dụng.

Ví dụ module descriptor đang khai báo:

~~~java
module com.acme.app {
    requires legacy.logging;
}
~~~

Nếu JAR mới được đặt tên khiến automatic module được suy ra thành `legacy.logging.v3`, quá trình resolution có thể không tìm thấy module `legacy.logging` như ứng dụng yêu cầu.

Có thể kiểm tra tên thực tế:

~~~bash
jar --describe-module --file mods/legacy-logging-2.4.jar
~~~

Nếu cần tên ổn định, ưu tiên thư viện công bố `Automatic-Module-Name`. Khi có thể, nâng cấp thư viện lên phiên bản cung cấp explicit module descriptor sẽ giúp kiểm soát dependency và package export rõ ràng hơn.

## 9. Giới hạn của automatic module

Automatic module hữu ích cho migration, nhưng không nên xem nó là thiết kế module cuối cùng:

- **Readability quá rộng:** module có thể đọc mọi module khác trong cấu hình, làm dependency thực tế khó nhìn thấy từ descriptor.
- **Export quá rộng:** mọi package của automatic module được export, kể cả package vốn chỉ phục vụ triển khai.
- **Không có hợp đồng dependency tường minh:** JAR không khai báo danh sách `requires` trong `module-info.class`.
- **Tên suy ra có thể thiếu ổn định:** nếu không có `Automatic-Module-Name`, việc đổi tên JAR có thể ảnh hưởng tên module.
- **Khó kiểm soát encapsulation:** package nội bộ có thể bị module khác sử dụng ngoài ý muốn.

Khi thư viện sẵn sàng hỗ trợ JPMS, nên bổ sung `module-info.java`, khai báo dependency thật sự cần, chỉ export API công khai và chỉ mở package cần cho framework reflection.

## 10. Các lỗi thường gặp và hướng kiểm tra

| Triệu chứng | Nguyên nhân có thể gặp | Hướng kiểm tra |
|---|---|---|
| `FindException: Module ... not found` | Tên automatic module không khớp hoặc JAR không có trên module path | Dùng `jar --describe-module`, kiểm tra `Automatic-Module-Name` và tên file |
| Automatic module không thấy module khác | Module kia chưa được đưa vào cấu hình runtime | Kiểm tra root modules, dependency và `--show-module-resolution` |
| Named module không dùng được kiểu từ automatic module | Named module chưa khai báo `requires` tới automatic module | Thêm dependency rõ ràng vào `module-info.java` |
| Package không truy cập được dù automatic module đã được resolve | Package cần dùng thuộc module nguồn khác và module nguồn chưa export | Kiểm tra descriptor của module nguồn |
| Mã classpath không dùng được module trên module path | Module chưa thuộc boot layer hoặc package chưa export | Kiểm tra `--add-modules` và `exports` |
| Sau khi đổi tên JAR, ứng dụng không resolve được module | Tên automatic module suy ra đã thay đổi | Khai báo/kiểm tra `Automatic-Module-Name` |

## 11. Quy trình chẩn đoán

Khi một automatic module không thể sử dụng kiểu từ module khác, hãy kiểm tra theo thứ tự:

1. **Xác định tên automatic module:** chạy `jar --describe-module --file ...` để biết tên thực tế.
2. **Kiểm tra vị trí JAR:** bảo đảm JAR nằm trên module path, không chỉ nằm trên classpath.
3. **Kiểm tra cấu hình resolution:** dùng `--show-module-resolution` để xác nhận cả automatic module và module đích có trong cấu hình.
4. **Kiểm tra package nguồn:** package chứa kiểu cần dùng phải được module nguồn export.
5. **Kiểm tra chiều dependency:** named module sử dụng automatic module cần khai báo `requires`; automatic module có quy tắc đọc rộng của riêng nó.
6. **Kiểm tra classpath nếu có:** automatic module có thể đọc unnamed module, nhưng named module không tự động đọc unnamed module.
7. **Ổn định tên module:** dùng `Automatic-Module-Name` hoặc explicit module descriptor để tránh phụ thuộc vào tên file.

## 12. Ghi nhớ

Automatic module là cầu nối giữa thư viện classpath cũ và JPMS. Khi được đưa vào cấu hình đã giải quyết, nó đọc tất cả module khác trong cấu hình, kể cả unnamed module, và export tất cả package của chính nó. Nhờ vậy, thư viện cũ có thể tiếp tục sử dụng nhiều dependency mà chưa cần descriptor riêng.

Khả năng đọc rộng này không có nghĩa mọi JAR trên module path tự động được resolve, cũng không làm named module sử dụng nó tự động đọc mọi module khác. Hãy phân biệt module path với resolved configuration, readability với export, và automatic module với unnamed module. Khi migration ổn định, chuyển thư viện sang explicit named module để khai báo dependency và API với phạm vi rõ ràng.
