# Qualified exports tới một module cụ thể

Trong Java Platform Module System (JPMS), directive **exports** công bố package của một module để module khác có thể sử dụng các kiểu public bên trong package đó. Khi dùng dạng qualified exports, module chỉ công bố package cho những module được nêu tên rõ ràng.

Cú pháp này phù hợp khi một package là API cần chia sẻ giữa một số module nội bộ, adapter hoặc plugin đã biết, nhưng không nên trở thành API chung cho mọi module đọc được module hiện tại. Qualified exports giúp thiết kế ranh giới module hẹp và có chủ đích hơn.

## 1. Cú pháp và ý nghĩa

Cú pháp cơ bản:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting;
}
~~~

Trong ví dụ, module **com.example.catalog** export package **com.example.catalog.api** cho hai module:

- **com.example.catalog.ui**
- **com.example.catalog.reporting**

Một module khác dù khai báo **requires com.example.catalog** vẫn không được truy cập package này nếu tên module đó không nằm trong danh sách sau từ khóa **to**.

Có thể khai báo nhiều module đích, phân tách bằng dấu phẩy. Tên sau **to** là tên module, không phải tên package, tên class hay tên file JAR. Tên module phải khớp với tên được khai báo trong module descriptor của module tiêu thụ.

Hai điều kiện cần được thỏa mãn để mã nguồn của module tiêu thụ dùng được một kiểu trong package được qualified export:

1. Module tiêu thụ phải đọc module sở hữu package, thông thường bằng directive **requires**.
2. Module tiêu thụ phải nằm trong danh sách module đích của qualified exports.

Qualified exports không tự tạo dependency và cũng không thay thế **requires**. Nó quyết định module nào được truy cập package sau khi quan hệ đọc module đã tồn tại.

## 2. Ví dụ với module API và hai module tiêu thụ

Giả sử ứng dụng có ba module:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/Product.java
├── com.example.catalog.ui/
│   ├── module-info.java
│   └── com/example/catalog/ui/Main.java
└── com.example.catalog.reporting/
    ├── module-info.java
    └── com/example/catalog/reporting/Report.java
~~~

Module catalog định nghĩa API:

~~~java
// src/com.example.catalog/module-info.java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting;
}
~~~

Class public nằm trong package được export:

~~~java
// src/com.example.catalog/com/example/catalog/api/Product.java
package com.example.catalog.api;

public final class Product {
    public String name() {
        return "Mechanical Keyboard";
    }
}
~~~

Module giao diện khai báo dependency:

~~~java
// src/com.example.catalog.ui/module-info.java
module com.example.catalog.ui {
    requires com.example.catalog;
}
~~~

Module giao diện có thể sử dụng API:

~~~java
// src/com.example.catalog.ui/com/example/catalog/ui/Main.java
package com.example.catalog.ui;

import com.example.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product();
        System.out.println(product.name());
    }
}
~~~

Module reporting cũng được cấp quyền truy cập package:

~~~java
// src/com.example.catalog.reporting/module-info.java
module com.example.catalog.reporting {
    requires com.example.catalog;
}
~~~

Vì **com.example.catalog.reporting** xuất hiện trong danh sách qualified exports, mã nguồn của module này có thể import và gọi các kiểu public trong package **com.example.catalog.api** theo các quy tắc truy cập Java thông thường.

## 3. Module không nằm trong danh sách sẽ bị giới hạn

Thêm một module audit:

~~~text
src/com.example.catalog.audit/
├── module-info.java
└── com/example/catalog/audit/Audit.java
~~~

Descriptor của module audit:

~~~java
module com.example.catalog.audit {
    requires com.example.catalog;
}
~~~

Nếu mã nguồn audit cố sử dụng Product:

~~~java
package com.example.catalog.audit;

import com.example.catalog.api.Product;

public class Audit {
    public void inspect() {
        Product product = new Product();
        System.out.println(product.name());
    }
}
~~~

Compiler báo package **com.example.catalog.api** không được export tới module **com.example.catalog.audit**. Việc thêm **requires com.example.catalog** chỉ thiết lập khả năng đọc module; nó không cấp quyền truy cập một package đã được export có điều kiện cho module khác.

Nếu audit thực sự cần API này, có thể bổ sung module đó vào danh sách:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting,
           com.example.catalog.audit;
}
~~~

Sau khi thay đổi descriptor của module catalog, cần biên dịch lại module đó và các module tiêu thụ liên quan để kiểm tra module graph và quyền truy cập.

## 4. Biên dịch và chạy ví dụ

Từ thư mục gốc của dự án, có thể biên dịch module catalog và module UI như sau:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog,com.example.catalog.ui
~~~

Sau khi biên dịch, chạy module UI:

~~~bash
java --module-path out \
     -m com.example.catalog.ui/com.example.catalog.ui.Main
~~~

Kết quả:

~~~text
Mechanical Keyboard
~~~

Để kiểm tra giới hạn truy cập, hãy thêm module audit vào lệnh biên dịch:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog,com.example.catalog.ui,com.example.catalog.audit
~~~

Nếu mã nguồn audit import **com.example.catalog.api.Product** nhưng audit chưa có trong danh sách qualified exports, compiler sẽ từ chối truy cập package. Đây là kiểm tra quan trọng: quyền truy cập được xác định từ descriptor và module graph, không dựa vào việc file JAR có nằm trên module path hay không.

Khi đổi descriptor để thêm audit, hãy biên dịch lại từ source tree đầy đủ. Nếu đang kiểm tra JAR đã đóng gói, cần tạo lại JAR chứa module descriptor mới và dùng đúng JAR đó trên module path.

## 5. Qualified exports khác unqualified exports như thế nào?

Hai dạng exports có phạm vi khác nhau:

~~~java
// Export package cho mọi module đọc module này
exports com.example.catalog.api;
~~~

~~~java
// Chỉ export package cho các module được nêu tên
exports com.example.catalog.api
    to com.example.catalog.ui,
       com.example.catalog.reporting;
~~~

| Tiêu chí | Unqualified exports | Qualified exports |
| --- | --- | --- |
| Cú pháp | exports package; | exports package to moduleA, moduleB; |
| Phạm vi | Các module đọc module hiện tại có thể truy cập package | Chỉ các module được liệt kê có thể truy cập package |
| Khả năng mở rộng consumer | Consumer mới có thể sử dụng package khi có quan hệ đọc phù hợp | Consumer mới cần được bổ sung vào danh sách |
| Phù hợp | API công khai, ổn định cho nhiều module | API nội bộ dùng chung có giới hạn |
| Công sức bảo trì | Ít phải cập nhật khi thêm consumer | Descriptor phải được cập nhật khi thêm consumer hợp lệ |

Unqualified exports thường phù hợp với API mà module chủ động công bố cho hệ sinh thái sử dụng. Qualified exports phù hợp với package chia sẻ giữa một nhóm module đã được xác định, chẳng hạn API dành cho adapter, integration module hoặc một số thành phần trong cùng sản phẩm.

Không nên đưa toàn bộ package của module vào danh sách qualified exports chỉ vì một consumer cần một class. JPMS export theo package, không theo từng class hoặc method. Nếu cần công bố một API nhỏ hơn, hãy tách API đó vào package riêng có ranh giới phù hợp.

## 6. Qualified exports chỉ công bố API public

Qualified exports không biến package thành một vùng mở hoàn toàn. Các quy tắc truy cập Java vẫn được áp dụng:

- Consumer được phép truy cập các kiểu public trong package đã export.
- Consumer vẫn phải tuân thủ modifier của class, constructor, field và method.
- Thành viên private hoặc package-private không trở thành API công khai.
- Package con là package độc lập; export package cha không tự export các package con.

Ví dụ, descriptor chỉ export:

~~~java
exports com.example.catalog.api
    to com.example.catalog.ui;
~~~

Nó không tự export:

~~~text
com.example.catalog.api.internal
com.example.catalog.persistence
com.example.catalog.admin
~~~

Nếu module UI cần truy cập package khác, module sở hữu package đó phải có directive tương ứng. Đây là lý do nên tổ chức package theo ranh giới API thay vì dựa vào giả định rằng export một package sẽ mở toàn bộ cây package bên dưới.

## 7. Phân biệt exports với opens

Qualified exports kiểm soát quyền truy cập API thông thường. Framework dùng reflection sâu có thể cần quyền khác.

Ví dụ:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui;

    opens com.example.catalog.model
        to com.example.catalog.persistence;
}
~~~

Trong descriptor này:

- Module UI được truy cập các kiểu public trong package API.
- Module persistence được phép deep reflection vào package model theo cơ chế JPMS.
- Việc export API không tự mở package model.
- Việc open package model không khiến package API trở thành API có thể import và gọi theo cách thông thường.

Có thể dùng qualified opens khi chỉ một framework hoặc module cần reflection. Cách này thường phù hợp với ORM, serializer hoặc framework cần đọc/ghi field không public. Hãy chỉ mở package thực sự cần thiết.

## 8. Những trường hợp sử dụng phù hợp

**API dành cho một số adapter**

Một module domain có thể công bố package SPI cho module adapter đã biết. Các module khác không thể phụ thuộc trực tiếp vào SPI đó nếu chưa được cấp quyền.

**API nội bộ giữa các module cùng sản phẩm**

Một module nền tảng có thể cung cấp package cho module giao diện và reporting. Các module ứng dụng khác chỉ sử dụng phần API công khai đã được thiết kế riêng.

**Giới hạn bề mặt tích hợp**

Một module có thể duy trì package API công khai rộng rãi, đồng thời dùng qualified exports cho một package hỗ trợ tích hợp chỉ cần một số module tiêu thụ.

**Tách implementation khỏi contract**

Module triển khai có thể export một package contract cho một nhóm module phối hợp. Các package chứa chi tiết nội bộ và implementation vẫn được giữ đóng.

Qualified exports hữu ích nhất khi danh sách consumer có thể quản lý và có lý do kiến trúc rõ ràng. Nếu danh sách module đích thay đổi liên tục hoặc có nhiều consumer bên ngoài không thể dự đoán, một API công khai ổn định có thể là lựa chọn phù hợp hơn.

## 9. Kiểm tra descriptor và quyền truy cập

Khi module đã được đóng gói thành JAR, dùng công cụ jar để xem descriptor:

~~~bash
jar --describe-module --file out/com.example.catalog.jar
~~~

Thông tin mô tả module cho biết package được export và các module đích của qualified exports. Hãy kiểm tra đúng file JAR đang được đưa lên module path, vì source descriptor và JAR cũ có thể không cùng phiên bản.

Có thể dùng **jdeps** để phân tích dependency module:

~~~bash
jdeps --module-path mods --module com.example.catalog.ui
~~~

Lệnh này giúp xem module phụ thuộc vào module nào. Nó không thay thế việc kiểm tra qualified exports: dependency đọc module và quyền truy cập package là hai điều kiện riêng.

Ở runtime, API Module cho phép kiểm tra package có được export tới một module cụ thể hay không:

~~~java
Module owner = Product.class.getModule();
Module consumer = Main.class.getModule();

boolean exported =
    owner.isExported("com.example.catalog.api", consumer);

System.out.println("Qualified export available: " + exported);
~~~

Lời gọi **isExported(packageName, targetModule)** trả về true khi package được export tới module đích theo cấu hình runtime hiện tại. Nó hữu ích khi debug ứng dụng modular hoặc khi cần xác nhận quan hệ giữa hai module.

## 10. Lỗi thường gặp và cách xử lý

**Package is not visible**

Kiểm tra module tiêu thụ đã requires module sở hữu package chưa. Sau đó kiểm tra package có được export và tên module tiêu thụ có nằm trong danh sách qualified exports không.

**Module not found hoặc tên module không khớp**

Kiểm tra tên module trong module-info.java của consumer và danh sách sau **to**. Đối chiếu với descriptor thực tế bằng **jar --describe-module**. Tên file JAR không nhất thiết là tên module.

**Đã thêm module vào danh sách nhưng vẫn lỗi**

Có thể compiler hoặc runtime đang dùng một bản module khác trên module path. Hãy xác định chính xác thư mục output, JAR và module path mà lệnh đang sử dụng; sau đó build lại module descriptor và chạy với artifact mới.

**Consumer đọc được module nhưng không import được package**

Đây là trường hợp dễ nhầm giữa **requires** và **exports**. requires tạo khả năng đọc module; exports xác định package nào có thể được truy cập và qualified exports còn giới hạn module nhận quyền.

**Framework báo lỗi reflection**

Kiểm tra package cần truy cập sâu có được open cho module framework không. Bổ sung qualified opens khi cần, thay vì mở rộng qualified exports với mục đích xử lý reflection private.

**Mã trên classpath không truy cập được package qualified export**

Các class trên classpath thuộc unnamed module. Unnamed module không thể được nêu tên như một module đích trong directive qualified exports. Nếu ứng dụng cần dùng package đó từ classpath, hãy cân nhắc thiết kế API unqualified exports hoặc chuyển consumer thành named module có tên ổn định.

## 11. Nguyên tắc thiết kế và bảo trì

- Chỉ dùng qualified exports khi có danh sách module tiêu thụ cụ thể và có lý do rõ ràng để giới hạn quyền truy cập.
- Đặt tên module đích chính xác, ổn định và trùng với tên trong descriptor của consumer.
- Giữ package API nhỏ, tách package implementation và package nội bộ.
- Nhớ rằng package export là đơn vị truy cập; không có cơ chế export riêng từng class.
- Cập nhật descriptor khi thêm hoặc bỏ module tiêu thụ, rồi biên dịch và kiểm tra lại toàn bộ module liên quan.
- Dùng qualified opens cho nhu cầu deep reflection thay vì nhầm lẫn với exports.
- Kiểm tra JAR thực tế trên module path khi lỗi chỉ xuất hiện sau đóng gói hoặc triển khai.
- Không coi qualified exports là cơ chế sandbox hay ranh giới bảo mật cho mã không tin cậy.

Qualified exports giúp module công bố đúng package cho đúng nhóm consumer. Khi kết hợp với requires, exports và opens được thiết kế rõ ràng, ứng dụng có thể duy trì API cần thiết giữa các module mà vẫn giữ những package nội bộ ngoài phạm vi truy cập của các module khác.