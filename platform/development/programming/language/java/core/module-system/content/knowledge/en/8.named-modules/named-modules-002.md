# Explicit named module từ module-info.java

Trong Java Platform Module System (JPMS), explicit named module là module có tên và khai báo module descriptor tường minh trong file **module-info.java**. Descriptor này xác định danh tính module, dependency mà module cần đọc, package nào được công bố và các service mà module sử dụng hoặc cung cấp.

Khi compiler xử lý module-info.java, nó kiểm tra cấu trúc khai báo và tạo ra file **module-info.class** trong kết quả biên dịch. Khi đóng gói module thành JAR modular, file descriptor nằm ở gốc JAR. Nhờ descriptor đó, Java có thể nhận diện module theo tên đã khai báo và áp dụng quy tắc phân giải module, đọc module và encapsulation của JPMS.

Bài học này tập trung vào cách tạo explicit named module, cấu trúc descriptor, quy trình biên dịch và đóng gói, cách Java nhận diện module trên module path, cùng các lỗi thường gặp khi chuyển một thư viện hoặc ứng dụng từ classpath sang module path.

## 1. Explicit named module là gì?

Một explicit named module có hai đặc điểm:

1. Có tên module ổn định được khai báo trong module descriptor.
2. Có descriptor được biên dịch thành **module-info.class** và đặt ở gốc của module đã biên dịch hoặc gốc JAR modular.

Ví dụ:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Tên module là **com.example.inventory**. Package **com.example.inventory.api** được export để module khác có thể sử dụng các kiểu public trong package đó khi có quan hệ đọc phù hợp.

JPMS còn có hai trường hợp thường được đặt cạnh explicit named module:

| Loại | Cách nhận diện | Đặc điểm |
| --- | --- | --- |
| Explicit named module | Có module-info.class với descriptor module tường minh | Tên, dependency và package access được khai báo rõ |
| Automatic module | JAR không có module descriptor nhưng được đặt trên module path | Tên module được suy ra từ Automatic-Module-Name hoặc tên JAR; có hành vi tương thích khi chuyển đổi |
| Unnamed module | Class và JAR nằm trên classpath | Không có tên module tường minh; mã nguồn truyền thống tiếp tục chạy theo mô hình classpath |

Explicit named module là cách mô tả module đầy đủ nhất. Tên module không cần suy ra từ tên file JAR, và các quy tắc phụ thuộc cùng quyền truy cập được lưu trong descriptor.

## 2. Vai trò của module-info.java

File **module-info.java** là module declaration. Nó nằm ở gốc source của module, cùng cấp với cây package, không nằm bên trong một package Java thông thường.

Cấu trúc tối thiểu:

~~~java
module com.example.inventory {
}
~~~

Đây là một named module có tên **com.example.inventory**. Dù body đang rỗng, compiler vẫn tạo descriptor cho module. Mọi module thông thường đều có dependency ngầm định tới module nền tảng **java.base**, vì vậy không cần viết **requires java.base** trong descriptor.

Một descriptor có thể khai báo các directive sau:

| Directive | Vai trò |
| --- | --- |
| requires | Khai báo module dependency mà module hiện tại cần đọc |
| requires transitive | Truyền khả năng đọc một dependency tới các module phụ thuộc vào module hiện tại |
| requires static | Khai báo dependency cần khi biên dịch nhưng có thể tùy chọn ở runtime |
| exports | Công bố package cho các module đọc module hiện tại |
| exports ... to | Chỉ công bố package cho các module được liệt kê |
| opens | Mở package cho deep reflection |
| opens ... to | Chỉ mở package cho một số module cụ thể |
| uses | Khai báo service mà module cần tìm implementation |
| provides ... with | Khai báo implementation cung cấp cho một service |

Ví dụ descriptor kết hợp dependency và API:

~~~java
module com.example.inventory {
    requires java.logging;

    exports com.example.inventory.api;
}
~~~

Module này đọc module **java.logging** và công bố package API. Các package khác của module vẫn được giữ đóng với module bên ngoài nếu không có directive export tương ứng.

Directive **requires** và **exports** giải quyết hai việc riêng: requires thiết lập khả năng đọc module; exports thiết lập quyền truy cập package. Việc một module đọc được dependency không có nghĩa mọi package của dependency đều được công bố.

## 3. Tổ chức source tree cho explicit named module

Một source tree modular thường đặt mỗi module trong một thư mục riêng có tên khớp với tên module:

~~~text
inventory-project/
└── src/
    └── com.example.inventory/
        ├── module-info.java
        └── com/
            └── example/
                └── inventory/
                    ├── Main.java
                    └── api/
                        └── Product.java
~~~

File module-info.java nằm trực tiếp trong thư mục **com.example.inventory/**. Các class Java nằm trong các package bên dưới.

Ví dụ descriptor:

~~~java
// src/com.example.inventory/module-info.java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Class API:

~~~java
// src/com.example.inventory/com/example/inventory/api/Product.java
package com.example.inventory.api;

public final class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Class khởi chạy:

~~~java
// src/com.example.inventory/com/example/inventory/Main.java
package com.example.inventory;

import com.example.inventory.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Keyboard");
        System.out.println(product.name());
    }
}
~~~

Class **Main** không cần nằm trong package được export để Java launcher khởi chạy module đó. Export phục vụ truy cập từ module khác; class main được chọn trực tiếp bằng tên module và tên class trong lệnh chạy.

Tên thư mục module trong source tree là một phần của quy ước tổ chức source khi dùng **--module-source-path**. Tên module có thẩm quyền vẫn là tên trong module-info.java. Giữ tên thư mục và tên module nhất quán giúp dự án dễ đọc và giảm nhầm lẫn khi build.

## 4. Quy tắc đặt tên module

Tên module thường dùng quy ước đảo ngược tên miền, tương tự tên package:

~~~text
com.example.inventory
org.example.reporting
vn.company.learning.module
~~~

Nên chọn tên:

- Ổn định trong suốt vòng đời module.
- Có tính duy nhất trong hệ thống module mà ứng dụng sử dụng.
- Dễ liên hệ với tổ chức hoặc sản phẩm sở hữu module.
- Không phụ thuộc vào tên phiên bản hoặc tên build artifact.

Tên module phân biệt chữ hoa và chữ thường. Các thành phần tên được ngăn cách bằng dấu chấm và tuân theo quy tắc identifier của Java. Không dùng tên package hoặc tên JAR làm tên module một cách tùy tiện; hãy chọn tên rõ nghĩa rồi giữ nguyên trong descriptor và các directive **requires** của consumer.

Tên file JAR không quyết định danh tính của explicit named module. Ví dụ, file **inventory-release.jar** vẫn có thể chứa module tên **com.example.inventory**. Khi một module khác khai báo dependency, nó dùng tên trong descriptor:

~~~java
module com.example.checkout {
    requires com.example.inventory;
}
~~~

Để tránh nhầm lẫn trong build và vận hành, nên đặt tên JAR gần với tên module, nhưng tên module trong descriptor mới là thông tin nền tảng dùng để phân giải.

## 5. Compiler biến module-info.java thành descriptor nhị phân

Compiler Java đọc module-info.java cùng các source file trong module. Kết quả biên dịch có file **module-info.class** ở gốc thư mục output của module.

Ví dụ biên dịch module inventory:

~~~bash
javac -d out --module-source-path src -m com.example.inventory
~~~

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
out/
└── com.example.inventory/
    ├── module-info.class
    └── com/
        └── example/
            └── inventory/
                ├── Main.class
                └── api/
                    └── Product.class
~~~

File module-info.class chứa thông tin descriptor ở dạng bytecode metadata. Nó không phải class Java thông thường mà ứng dụng tạo instance hoặc gọi method. Java compiler, công cụ JAR và module system sử dụng metadata này để nhận diện module.

Có thể xem cấu trúc output bằng lệnh liệt kê file:

~~~text
out/com.example.inventory/module-info.class
out/com.example.inventory/com/example/inventory/Main.class
out/com.example.inventory/com/example/inventory/api/Product.class
~~~

Nếu output không có module-info.class ở gốc module, hãy kiểm tra vị trí module-info.java trong source tree và cách gọi javac. Đặt file descriptor bên trong package, chẳng hạn **src/com.example.inventory/com/example/inventory/module-info.java**, là sai cấu trúc.

## 6. Đóng gói thành modular JAR

Một explicit named module thường được phân phối dưới dạng modular JAR. Khi đóng gói, cần giữ module-info.class ở gốc JAR cùng các class đã biên dịch.

Tạo thư mục chứa JAR:

~~~bash
mkdir -p mods
~~~

Đóng gói module đã biên dịch:

~~~bash
jar --create --file mods/com.example.inventory.jar \
    -C out/com.example.inventory .
~~~

Có thể liệt kê nội dung JAR:

~~~bash
jar --list --file mods/com.example.inventory.jar
~~~

Kết quả cần có descriptor ở gốc:

~~~text
META-INF/
module-info.class
com/example/inventory/Main.class
com/example/inventory/api/Product.class
~~~

Các entry cụ thể có thể khác theo nội dung module, nhưng **module-info.class** phải nằm ở gốc JAR đối với modular JAR thông thường. Nếu descriptor bị đặt sai vị trí hoặc không được đưa vào JAR, công cụ module sẽ không nhận artifact đó như explicit named module theo cách dự định.

Để xác nhận tên module và descriptor:

~~~bash
jar --describe-module --file mods/com.example.inventory.jar
~~~

Lệnh này hiển thị tên module, các package và các directive được ghi trong descriptor. Đây là bước kiểm tra hữu ích sau khi build hoặc khi nhận một JAR từ nhóm khác.

## 7. Đặt explicit named module trên module path

Module path là nơi Java tìm các module để phân giải. Nó có thể là một thư mục chứa modular JAR hoặc các thư mục module đã biên dịch theo cấu trúc exploded module.

Chạy module từ thư mục output:

~~~bash
java --module-path out \
     -m com.example.inventory/com.example.inventory.Main
~~~

Chạy module từ thư mục chứa JAR:

~~~bash
java --module-path mods \
     -m com.example.inventory/com.example.inventory.Main
~~~

Cú pháp **-m module/class** xác định module và class có phương thức main. Tên module phải khớp với descriptor, còn tên class phải là tên đầy đủ của class chứa main.

Nếu muốn chỉ định main class qua tên module mà không viết lại tên class ở lệnh chạy, có thể cấu hình Main-Class trong manifest của modular JAR và sử dụng cách khởi chạy phù hợp với manifest. Với ví dụ học tập, ghi rõ **module/class** giúp nhìn thấy chính xác module và điểm bắt đầu chương trình.

Khi dùng **--module-path**, Java thực hiện module resolution. Module gốc được chọn cùng các dependency mà descriptor yêu cầu sẽ tạo thành cấu hình chạy. Không phải mọi JAR nằm trong thư mục module path đều tự động trở thành module đang chạy; module system phân giải từ các module gốc và dependency liên quan.

## 8. Explicit named module và encapsulation

Một trong những giá trị chính của explicit named module là kiểm soát package được module khác truy cập.

Ví dụ:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Module khác có thể khai báo:

~~~java
module com.example.checkout {
    requires com.example.inventory;
}
~~~

Module checkout có thể sử dụng public type trong package **com.example.inventory.api**. Package **com.example.inventory.internal** không được export nên không trở thành API thông thường cho module checkout.

Một vài quy tắc quan trọng:

- Export được khai báo ở cấp package, không phải từng class hoặc method.
- Chỉ kiểu và thành viên public có khả năng được truy cập theo quy tắc Java thông thường; modifier của class và member vẫn có hiệu lực.
- Export package cha không tự export package con.
- **opens** phục vụ deep reflection, khác với **exports** phục vụ truy cập API thông thường.
- **exports ... to** giới hạn consumer được truy cập package.
- Module không khai báo export vẫn có thể sử dụng package nội bộ của chính nó.

Ví dụ mở package cho framework persistence:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;

    opens com.example.inventory.model
        to com.example.persistence;
}
~~~

Trong descriptor này, package API được công bố cho truy cập thông thường, còn package model chỉ được mở cho module persistence để framework có thể thực hiện deep reflection theo quy tắc JPMS.

## 9. Phân biệt explicit, automatic và unnamed module khi chuyển đổi

Khi di chuyển một ứng dụng từ classpath sang module path, cần xác định loại module của từng dependency.

**Explicit named module**

JAR có module-info.class hợp lệ. Tên module, requires, exports, opens, uses và provides được khai báo rõ. Đây là dạng nên hướng tới khi module đã được thiết kế và kiểm soát.

**Automatic module**

JAR không có module-info.class nhưng được đặt trên module path. Tên module có thể được xác định từ thuộc tính manifest **Automatic-Module-Name**; nếu thuộc tính này không có, Java suy ra tên từ tên file JAR theo quy tắc của module system. Automatic module thường đọc các named module khác và export các package của nó để hỗ trợ chuyển đổi thư viện cũ. Vì vậy, nó không có ranh giới encapsulation được thiết kế tường minh như explicit module.

**Unnamed module**

Các class trên classpath thuộc unnamed module của class loader tương ứng. Nó không có tên module khai báo trong module-info.java. Mã nguồn truyền thống có thể tiếp tục chạy trên classpath trong khi các thành phần khác của ứng dụng đã modular hóa, nhưng cần hiểu rõ các quy tắc tương tác giữa named module và unnamed module.

Thuộc tính **Automatic-Module-Name** trong manifest giúp đặt tên ổn định cho automatic module; nó không thay thế module-info.java và không biến JAR thành explicit named module. Muốn có explicit descriptor, cần tạo module-info.java, biên dịch và đóng gói lại JAR.

## 10. Module mở và open module

Ngoài dạng khai báo thông thường:

~~~java
module com.example.inventory {
    opens com.example.inventory.model;
}
~~~

Java cho phép khai báo một **open module**:

~~~java
open module com.example.inventory {
    requires java.sql;

    exports com.example.inventory.api;
}
~~~

Open module mở tất cả package của module cho deep reflection ở runtime. Có thể dùng khi framework cần truy cập sâu vào nhiều package, nhưng phạm vi mở rộng hơn so với việc chỉ khai báo một vài directive **opens** hoặc **opens ... to**.

Một open module vẫn là explicit named module: nó vẫn có tên và module descriptor. Từ khóa **open** thay đổi chính sách reflection của package, không loại bỏ dependency, exports hoặc module identity. Khi chỉ một số package cần reflection, nên cân nhắc mở đúng package và giới hạn module nhận quyền.

## 11. Kiểm tra module descriptor và dependency

Một số công cụ JDK giúp kiểm tra artifact sau khi biên dịch và đóng gói:

~~~bash
# Hiển thị descriptor của modular JAR
jar --describe-module --file mods/com.example.inventory.jar
~~~

~~~bash
# Liệt kê nội dung JAR để xác nhận module-info.class
jar --list --file mods/com.example.inventory.jar
~~~

~~~bash
# Hiển thị module resolution khi chạy
java --show-module-resolution \
     --module-path mods \
     -m com.example.inventory/com.example.inventory.Main
~~~

~~~bash
# Phân tích dependency module
jdeps --module-path mods --module com.example.inventory
~~~

Khi đọc kết quả, hãy kiểm tra:

1. Tên module trong descriptor có đúng tên mà consumer dùng trong requires không?
2. JAR có chứa module-info.class ở vị trí đúng không?
3. Các dependency được khai báo có thể tìm thấy trên module path không?
4. Package cần chia sẻ có được export tới module tiêu thụ không?
5. Runtime đang dùng đúng artifact vừa được build hay đang lấy một bản JAR cũ?

Nếu build tool tạo JAR, hãy kiểm tra cấu hình đóng gói để chắc chắn module-info.class được giữ lại. Một bản JAR được tạo từ nhầm thư mục output có thể chứa class nhưng thiếu descriptor, khiến hành vi trên module path khác với mong đợi.

## 12. Lỗi thường gặp

**module not found**

Tên module trong requires không khớp với tên descriptor hoặc module dependency không nằm trong module path. Dùng jar --describe-module để kiểm tra tên thực tế của JAR và xem lại vị trí module path.

**module-info.java không được nhận diện**

File descriptor bị đặt trong package, sai tên file hoặc lệnh javac không biên dịch theo cấu trúc module. Đặt module-info.java ở gốc source của module và dùng tùy chọn biên dịch modular phù hợp.

**JAR có class nhưng không được nhận diện là explicit module**

JAR có thể đã bị đóng gói thiếu module-info.class. Liệt kê nội dung JAR, kiểm tra descriptor trong thư mục output và tạo lại artifact từ đúng thư mục module.

**Package is not visible**

Module tiêu thụ có thể chưa requires module sở hữu package hoặc package chưa được export. Kiểm tra cả hai điều kiện; chỉ có JAR trên module path không tự cấp quyền truy cập package.

**Chạy được trên classpath nhưng lỗi trên module path**

Khi chuyển sang module path, JPMS áp dụng module graph và encapsulation. Hãy xác định dependency nào chưa khai báo, package nào chưa export hoặc framework nào cần opens. Không nên khắc phục mọi lỗi bằng cách mở toàn bộ package.

**Tên JAR và tên module khác nhau**

Tên JAR không quyết định tên explicit module. Dùng descriptor làm căn cứ và giữ tên module ổn định trong các directive requires.

## 13. Quy trình tạo explicit named module hoàn chỉnh

Khi bắt đầu một module mới, có thể đi theo trình tự:

1. Chọn tên module ổn định, ví dụ **com.example.inventory**.
2. Tạo thư mục source cho module và đặt **module-info.java** ở gốc.
3. Khai báo dependency bằng requires.
4. Chỉ export package thực sự là API công khai.
5. Chỉ opens package khi framework cần deep reflection.
6. Biên dịch bằng javac theo module source path.
7. Kiểm tra output có module-info.class ở gốc module.
8. Đóng gói JAR và kiểm tra bằng jar --describe-module.
9. Đưa JAR lên module path và chạy bằng cú pháp module/class.
10. Kiểm tra module resolution và dependency trong môi trường triển khai.

Khi đã hoàn thành, bạn có thể giải thích được explicit named module được tạo từ module-info.java như thế nào, descriptor được lưu ở đâu, tên module được dùng trong requires ra sao và vì sao một modular JAR có thể được phân giải trên module path. Đây là nền tảng để thiết kế các module Java có dependency rõ ràng, API công khai có kiểm soát và cấu trúc dễ bảo trì.