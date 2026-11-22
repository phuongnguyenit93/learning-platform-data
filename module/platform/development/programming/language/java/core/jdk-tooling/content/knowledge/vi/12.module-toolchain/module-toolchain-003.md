# Chỉ thị exports trong Java Module System

Trong Java Platform Module System (JPMS), một module có thể chứa nhiều package nhưng không phải package nào cũng được phép dùng từ module khác. Chỉ thị **exports** trong tệp module-info.java công khai một package để các module được phép đọc module đó có thể sử dụng API public của package.

exports là một phần cốt lõi của thiết kế module: nó xác định ranh giới API công khai, giúp module che giấu phần triển khai nội bộ và giảm phụ thuộc giữa các thành phần. Muốn dùng một kiểu public từ module khác, thường cần cả hai điều kiện: module sử dụng khai báo **requires** module cung cấp, và module cung cấp **exports** package chứa kiểu đó.

## 1. exports dùng để làm gì?

Một named module có thể chứa:

- **Package công khai:** chứa API mà module khác được phép sử dụng.
- **Package nội bộ:** chứa lớp triển khai, helper hoặc chi tiết nội bộ không muốn công khai.
- **Module descriptor:** tệp module-info.java khai báo tên module, dependency và các ranh giới truy cập.

Ví dụ module có tên com.acme.library:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Chỉ thị này công khai package com.acme.library.api. Một module khác có thể sử dụng các kiểu public trong package đó nếu module sử dụng đọc được com.acme.library.

Package com.acme.library.internal, nếu tồn tại nhưng không được exports, vẫn có thể được dùng bên trong module com.acme.library; module khác không thể import các kiểu trong package đó như API thông thường.

### exports kiểm soát package, không phải từng lớp

Chỉ thị exports áp dụng cho cả package. Nó không có cú pháp để chỉ xuất riêng một lớp trong package.

Nếu package được export:

- Các kiểu public trong package có thể được module đọc module truy cập.
- Quy tắc access modifier của Java vẫn được áp dụng cho lớp, phương thức và trường.
- Các kiểu package-private vẫn không trở thành public.
- Các lớp nội bộ có thể được giữ trong package khác không được export.

Vì vậy, khi thiết kế API, nên đặt các kiểu cần công khai trong package API riêng và giữ implementation trong package nội bộ.

## 2. Cú pháp của exports

Có hai dạng chính:

~~~java
exports package.name;
exports package.name to module.one, module.two;
~~~

### Unqualified export

Dạng không có từ khóa to:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Đây là **unqualified export**. Package được công khai cho mọi module đọc com.acme.library. Đây là lựa chọn phù hợp cho API công khai mà module muốn hỗ trợ cho nhiều người dùng.

### Qualified export

Dạng có từ khóa to:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin, com.acme.testkit;
}
~~~

Đây là **qualified export**. Package com.acme.library.spi chỉ được công khai cho các module được liệt kê trong danh sách to.

Qualified export hữu ích khi một package chỉ dành cho một nhóm module hợp tác, ví dụ:

- API SPI chỉ dành cho các plugin được kiểm soát.
- Package tích hợp nội bộ giữa hai module cùng hệ thống.
- Package hỗ trợ test được mở cho module test harness.
- Giao diện mở rộng dành cho một implementation cụ thể.

Qualified export vẫn là cơ chế công khai ở cấp package; nó không làm các lớp trong package trở thành private hay thay đổi access modifier của Java.

### Không có wildcard và không tự động bao gồm subpackage

exports phải chỉ định tên package cụ thể. Không có cú pháp kiểu:

~~~java
exports com.acme.library.*;
~~~

Nếu module có các package:

- com.acme.library.api
- com.acme.library.api.model
- com.acme.library.internal

thì exports com.acme.library.api chỉ export package com.acme.library.api. Nó không tự động export com.acme.library.api.model hoặc com.acme.library.internal. Muốn công khai package con, cần khai báo riêng từng package.

## 3. Điều kiện để module khác sử dụng package đã export

Để module com.acme.app gọi API từ com.acme.library, cần có cả module readability và package accessibility.

Module descriptor của thư viện:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Module descriptor của ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Hai chỉ thị có trách nhiệm khác nhau:

- **requires com.acme.library** tạo quan hệ đọc: module app có thể đọc module library.
- **exports com.acme.library.api** cho phép module đọc library truy cập các kiểu public thuộc package api.

Chỉ có requires mà package không được export thì module app vẫn không thể dùng API trong package đó theo cách thông thường. Chỉ có exports mà module app không đọc module library thì ứng dụng cũng không thể tự động import API.

### Sơ đồ quan hệ

~~~text
com.acme.app
    |
    | requires com.acme.library
    v
com.acme.library
    |
    | exports com.acme.library.api
    v
com.acme.library.api
    |
    v
Public API có thể được app sử dụng
~~~

Module descriptor vừa mô tả dependency giữa module, vừa mô tả package nào là bề mặt API.

## 4. Ví dụ hoàn chỉnh: export một API package

Ví dụ dưới đây có hai module:

- com.acme.greetings cung cấp lớp Greeter.
- com.acme.app sử dụng Greeter.

Cấu trúc source tree:

~~~text
exports-demo/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

### Module cung cấp API

Tệp src/com.acme.greetings/module-info.java:

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

Tệp src/com.acme.greetings/com/acme/greetings/Greeter.java:

~~~java
package com.acme.greetings;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Module sử dụng API

Tệp src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

Tệp src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.greetings.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        String name = args.length == 0 ? "Java" : args[0];

        System.out.println(greeter.greet(name));
    }
}
~~~

### Biên dịch cả hai module

Từ thư mục exports-demo, chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d out \
  -m com.acme.greetings,com.acme.app
~~~

Lệnh dùng --module-source-path để tìm source tree, -d out để đặt class file và -m để chọn hai module cần biên dịch.

### Chạy ứng dụng

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java!
~~~

Truyền tham số ứng dụng:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main "Module System"
~~~

Output:

~~~text
Hello, Module System!
~~~

Ví dụ cho thấy ứng dụng chỉ cần requires module thư viện; package API được truy cập vì module thư viện đã export package com.acme.greetings.

## 5. Qualified exports: chỉ công khai cho module được chọn

Giả sử thư viện có API công khai cho mọi người dùng và SPI chỉ dành cho module plugin.

Module descriptor của thư viện:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin;
}
~~~

Module descriptor của plugin:

~~~java
module com.acme.plugin {
    requires com.acme.library;
}
~~~

Trong thiết kế này:

- com.acme.plugin có thể truy cập các kiểu public trong com.acme.library.api.
- com.acme.plugin cũng có thể truy cập các kiểu public trong com.acme.library.spi.
- Một module khác đọc com.acme.library nhưng không nằm trong danh sách to chỉ truy cập được package api; package spi vẫn bị đóng với module đó.

Qualified export không thay thế requires. Module plugin vẫn phải khai báo requires com.acme.library để đọc module thư viện.

### Khi nào nên dùng qualified export?

Dùng khi có một ranh giới module được kiểm soát và package chỉ cần chia sẻ với một số module cụ thể. Tránh liệt kê quá nhiều module nội bộ vào qualified export nếu mục tiêu thực sự là xây dựng API công khai; danh sách đó làm tăng liên kết giữa các module và có thể khiến việc tái cấu trúc khó hơn.

Nếu module đích đổi tên, qualified export cũng phải được cập nhật theo tên module mới. Đây là một phụ thuộc có chủ đích và cần được quản lý trong quá trình build.

## 6. exports và opens khác nhau như thế nào?

Hai chỉ thị này đều liên quan đến khả năng truy cập package, nhưng giải quyết hai nhu cầu khác nhau.

| Khía cạnh | exports | opens |
|---|---|---|
| Mục đích | Công khai API Java cho module khác | Cho phép truy cập phản chiếu sâu vào package |
| Truy cập mã nguồn | Cho phép import và dùng kiểu public theo quy tắc Java | Không tự cho phép import package như API |
| Reflection trên public API | Cho phép truy cập reflective thông thường đối với API được export | Cũng cho phép deep reflection |
| Reflection vào thành viên non-public | Không tự cấp quyền deep reflection | Cho phép trong phạm vi opens |
| Đối tượng thường dùng | Người dùng API | Framework, serializer, dependency injection và công cụ reflection |

Ví dụ export:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Ví dụ qualified open:

~~~java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to com.acme.json;
}
~~~

Trong ví dụ thứ hai:

- Module đọc com.acme.model có thể sử dụng public API trong com.acme.model.api.
- Module com.acme.json được phép deep reflection vào com.acme.model.internal.
- Module khác không nhận quyền deep reflection vào package internal thông qua chỉ thị opens có phạm vi giới hạn này.

Có thể dùng opens package; để mở package cho mọi module, hoặc opens package to module.name; để mở có giới hạn. Tùy chọn open module ở đầu module descriptor mở tất cả package của module cho deep reflection, nhưng không biến tất cả package thành API source-level được export.

Không nên dùng opens thay cho exports khi mục tiêu là cho module khác import và gọi API Java bình thường.

## 7. exports không bỏ qua access modifier của Java

Export package không biến mọi lớp và thành viên trong package thành public.

Ví dụ:

~~~java
package com.acme.library.api;

public class PublicService {
    public void execute() {
        // API công khai
    }

    void internalStep() {
        // package-private
    }

    private void hiddenStep() {
        // private
    }
}
~~~

Nếu module export package com.acme.library.api:

- Module khác có thể gọi new PublicService() và execute() vì lớp và phương thức là public.
- Module khác không thể gọi internalStep() vì phương thức package-private.
- Module khác không thể gọi hiddenStep() bằng truy cập Java thông thường vì phương thức private.

Quy tắc truy cập của ngôn ngữ Java vẫn áp dụng sau khi JPMS cho phép package được đọc. JPMS bổ sung ranh giới module ở phía ngoài các access modifier truyền thống.

## 8. exports và requires transitive

requires và exports là hai phần độc lập của module descriptor. Một tình huống cần chú ý là API public của module A sử dụng kiểu được định nghĩa trong module B.

Ví dụ module com.acme.api trả về kiểu Type của com.acme.types trong chữ ký API. Nếu người dùng com.acme.api cần đọc kiểu Type để biên dịch mã sử dụng API, module api có thể cần khai báo:

~~~java
module com.acme.api {
    requires transitive com.acme.types;
    exports com.acme.api;
}
~~~

requires transitive làm cho module đọc com.acme.api cũng đọc được com.acme.types theo module graph. Điều này hữu ích khi dependency là một phần của public API.

Cần phân biệt:

- **exports** công khai package của chính module khai báo directive.
- **requires** khai báo module hiện tại đọc một module khác.
- **requires transitive** cho phép quan hệ đọc được truyền tới module phụ thuộc vào module hiện tại.

requires transitive không tự export package của module phụ thuộc. Package đó vẫn phải được module sở hữu nó export theo quy tắc riêng.

## 9. Cách kiểm tra package được export

Có thể dùng javap để xem module descriptor đã biên dịch:

~~~bash
javap -p -v out/com.acme.greetings/module-info.class
~~~

Trong output, tìm phần module descriptor và directive exports. Tên class file module-info.class nằm ở gốc exploded module.

Nếu đã đóng gói module thành modular JAR, có thể dùng:

~~~bash
jar --describe-module --file com.acme.greetings.jar
~~~

Lệnh này hiển thị tên module, các package được export và các quan hệ module mà công cụ đọc được từ archive.

Có thể dùng javap để xem chữ ký public của một lớp API:

~~~bash
javap -classpath out/com.acme.greetings com.acme.greetings.Greeter
~~~

Lệnh cuối chỉ kiểm tra chữ ký lớp trên classpath; nó không thay thế việc kiểm tra module descriptor hoặc module resolution của toàn ứng dụng.

## 10. Lỗi thường gặp liên quan đến exports

### Package is not visible hoặc package is not exported

Module sử dụng có thể đã requires module cung cấp, nhưng package chứa lớp cần dùng chưa được export.

Cách xử lý:

- Kiểm tra module descriptor của module sở hữu package.
- Thêm exports package.name; nếu package là API công khai.
- Dùng qualified export nếu chỉ một số module cụ thể được phép sử dụng package.
- Biên dịch lại module và chạy lại với đúng module path.

### Module not found

Module sử dụng chưa tìm thấy module cung cấp. Kiểm tra requires, module name, module path và artifact đầu ra. exports không tự đưa module vào module graph.

### Class is not public hoặc member is not accessible

Package có thể đã được export nhưng kiểu hoặc thành viên vẫn không public. Kiểm tra access modifier của lớp, constructor, phương thức và trường. exports không thay đổi modifier trong mã nguồn.

### Đã dùng opens nhưng import vẫn lỗi

opens phục vụ deep reflection, không thay thế exports cho truy cập mã nguồn. Nếu cần import và gọi public API, hãy export package tương ứng.

### Package con vẫn không truy cập được

exports chỉ áp dụng cho đúng package được khai báo. Cần export riêng package con nếu nó cũng là một phần của API công khai.

### Qualified export không có tác dụng với module mong muốn

Kiểm tra tên module trong mệnh đề to có đúng với module name trong module-info.java hay không. Tên package hoặc tên JAR không nhất thiết là tên module. Module đích cũng cần đọc module cung cấp bằng requires.

### API bị lộ quá rộng

Một package nội bộ bị export không cần thiết có thể trở thành bề mặt API mà module khác phụ thuộc vào. Chuyển lớp triển khai sang package không export hoặc tách package API và implementation để kiểm soát hợp đồng công khai.

## 11. Nguyên tắc thiết kế API với exports

Khi thiết kế module, nên coi mỗi chỉ thị exports là một quyết định về hợp đồng API:

1. **Chỉ export package cần công khai.** Giữ helper, implementation và chi tiết nội bộ trong package không export.
2. **Ưu tiên package API rõ ràng.** Tên như com.acme.product.api hoặc com.acme.product.spi giúp người dùng nhận biết bề mặt hỗ trợ.
3. **Dùng qualified export có chủ đích.** Chỉ giới hạn cho module đích khi có ranh giới hợp tác cụ thể.
4. **Tránh export package con theo thói quen.** Mỗi package được export mở rộng phạm vi phụ thuộc của người dùng.
5. **Không nhầm exports với opens.** API source-level và deep reflection là hai yêu cầu khác nhau.
6. **Quản lý dependency công khai.** Nếu chữ ký API dùng kiểu từ module khác, đánh giá requires transitive.
7. **Giữ tương thích API.** Khi đã export package, các module khác có thể phụ thuộc vào kiểu public trong đó; thay đổi hoặc xóa kiểu cần được quản lý như thay đổi API.
8. **Kiểm tra module descriptor trong CI.** Biên dịch module và kiểm thử ứng dụng để phát hiện package thiếu export hoặc dependency thiếu requires.

## 12. Checklist khi dùng exports

- Đặt chỉ thị exports trong module-info.java của module sở hữu package.
- Xác định package có thực sự là API công khai hay không.
- Dùng exports package.name; để công khai cho mọi module đọc module hiện tại.
- Dùng exports package.name to module.name; để giới hạn module được truy cập.
- Nhớ rằng exports không tự tạo quan hệ requires.
- Nhớ rằng exports package cha không tự export package con.
- Giữ access modifier Java phù hợp; exports không biến lớp package-private thành public.
- Dùng opens cho nhu cầu deep reflection, không dùng thay cho exports.
- Cân nhắc requires transitive khi dependency xuất hiện trong chữ ký API công khai.
- Kiểm tra module descriptor bằng javap hoặc jar --describe-module.
- Biên dịch và chạy ví dụ trên module path để xác nhận module graph và package visibility.
- Tránh export package nội bộ nếu không muốn biến nó thành bề mặt API được hỗ trợ.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| exports | Công khai một package của module cho module khác |
| Unqualified export | Export package cho mọi module đọc module hiện tại |
| Qualified export | Export package chỉ cho các module được liệt kê sau to |
| Package accessibility | Khả năng module khác truy cập kiểu trong package |
| Module readability | Quan hệ đọc giữa module, thường được khai báo bằng requires |
| requires | Khai báo module phụ thuộc |
| requires transitive | Truyền quan hệ đọc đến module phụ thuộc vào module hiện tại |
| opens | Cho phép deep reflection vào package |
| open module | Mở tất cả package cho deep reflection |
| API package | Package chứa các kiểu public được hỗ trợ cho người dùng |
| SPI | Service Provider Interface, giao diện dành cho implementation hoặc plugin |

Điểm cốt lõi: **requires quyết định module nào được đọc; exports quyết định package nào được công khai; opens quyết định package nào được mở cho deep reflection**. Thiết kế ba phần này rõ ràng giúp module giữ được tính đóng gói, công khai đúng API và hạn chế phụ thuộc không cần thiết.