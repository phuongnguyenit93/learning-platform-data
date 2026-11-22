# Phân biệt exports với public trong mã nguồn

Trong Java, từ khóa **`public`** và directive **`exports`** đều liên quan đến khả năng truy cập, nhưng chúng hoạt động ở hai tầng khác nhau. `public` là quy tắc truy cập của ngôn ngữ Java đối với một kiểu hoặc thành viên. `exports` là khai báo ở cấp module, cho phép các module khác truy cập những kiểu public thuộc một package cụ thể.

Vì vậy, một lớp có thể được khai báo `public` nhưng vẫn không thể được module bên ngoài sử dụng nếu package chứa lớp đó chưa được export. Ngược lại, export một package không biến các lớp hoặc thành viên có mức truy cập package-private, protected hay private thành public.

Để hiểu đúng ranh giới này, cần xét đồng thời ba điều kiện: module sử dụng có đọc được module cung cấp hay không, package có được export cho module sử dụng hay không, và kiểu/thành viên có đáp ứng quy tắc truy cập của Java hay không.

## 1. public là quy tắc truy cập của ngôn ngữ Java

Trong mã nguồn Java, `public` là một access modifier. Nó có thể được dùng cho top-level class/interface, constructor, method, field và các thành viên phù hợp khác.

Ví dụ:

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }

    private String internalCode() {
        return "C-001";
    }
}
~~~

Nếu xét riêng quy tắc ngôn ngữ Java:

- Lớp `Customer` là public, nên mã nguồn ở package khác có thể tham chiếu tới lớp này nếu lớp nằm trong phạm vi truy cập hợp lệ.
- Method `getName()` là public, nên có thể được gọi từ mã có quyền truy cập tới lớp.
- Method `internalCode()` là private, nên chỉ mã trong phạm vi được Java cho phép của lớp `Customer` mới có thể truy cập trực tiếp.
- Việc lớp hoặc method là public không tự động công khai package chứa chúng qua ranh giới JPMS.

Các mức truy cập của Java vẫn được áp dụng khi dự án dùng module system. JPMS bổ sung một lớp kiểm soát ở cấp package/module; nó không thay thế access modifier của ngôn ngữ.

## 2. exports là quyền công khai package ở cấp module

Directive `exports` được viết trong `module-info.java`:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Khai báo trên nói rằng module `com.acme.library` công khai package `com.acme.library.api` cho các module khác. Khi module sử dụng đọc được module thư viện, nó có thể truy cập các kiểu public trong package được export, với điều kiện các quy tắc truy cập Java cũng cho phép.

`exports` áp dụng cho toàn bộ package được nêu. Nó không liệt kê từng class hoặc method riêng lẻ. Nếu muốn giới hạn module nào được sử dụng package, có thể dùng qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.api to com.acme.application;
}
~~~

Trong ví dụ này, package `com.acme.library.api` chỉ được export cho module `com.acme.application`. Một module khác dù có khai báo `requires com.acme.library` vẫn không được dùng package này qua ranh giới module.

## 3. Ba điều kiện để module khác dùng được một public type

Giả sử module thư viện chứa:

~~~java
// module-info.java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
// com/acme/library/api/Customer.java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }
}
~~~

Module ứng dụng khai báo:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

Mã ứng dụng có thể sử dụng lớp:

~~~java
package com.acme.application;

import com.acme.library.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer();
        System.out.println(customer.getName());
    }
}
~~~

Khả năng truy cập xuyên module cần thỏa mãn đồng thời:

1. **Readability:** module ứng dụng phải đọc được module thư viện. Trong ví dụ, điều này được khai báo bằng `requires com.acme.library`.
2. **Export:** module thư viện phải export package chứa kiểu. Trong ví dụ, package `com.acme.library.api` được export.
3. **Java access control:** kiểu và thành viên được sử dụng phải có mức truy cập phù hợp. Ở đây, cả lớp `Customer` và method `getName()` đều là public.

Có thể ghi nhớ quy tắc:

~~~text
module đọc được module cung cấp
        +
package được module nguồn export
        +
kiểu/thành viên đáp ứng access modifier Java
        =
mã ở module sử dụng truy cập được API
~~~

Nếu thiếu một trong các điều kiện trên, việc chỉ thêm `public` vào lớp hoặc chỉ thêm `requires` vào module ứng dụng chưa đủ để sử dụng API.

## 4. public không thay thế exports

Xét module thư viện không export package:

~~~java
module com.acme.library {
    // Không export com.acme.library.api
}
~~~

Lớp trong package vẫn có thể được khai báo public:

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }
}
~~~

Một module khác có thể khai báo `requires com.acme.library`, nhưng mã nguồn của nó vẫn không được phép import `com.acme.library.api.Customer`. Lý do là package chưa được module thư viện export. Từ khóa `public` trên `Customer` chỉ đáp ứng điều kiện truy cập ở tầng ngôn ngữ; nó không vượt qua ranh giới đóng gói của JPMS.

Khi biên dịch ứng dụng, compiler có thể báo package không được export hoặc package không hiển thị từ module thư viện. Nếu chạy một chương trình được biên dịch trong cấu hình không phù hợp, việc truy cập cũng có thể thất bại ở runtime. Cần kiểm tra descriptor của module nguồn, không chỉ kiểm tra khai báo class.

Một cách sửa đúng nếu package thực sự là API công khai là thêm directive:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Nếu package chỉ là chi tiết triển khai, hãy giữ nó không export và cung cấp một API public ở package khác được export.

## 5. exports không biến mọi kiểu thành public

Chiều ngược lại cũng quan trọng. Khi module export một package, nó chỉ mở package đó qua ranh giới module; các access modifier bên trong package vẫn giữ nguyên ý nghĩa.

Ví dụ:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }

    String getInternalLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }
}
~~~

Module sử dụng có thể tạo `Customer` và gọi `getName()`. Nó không thể gọi `getInternalLabel()` vì method đó có package-private access; cũng không thể gọi `secret()` vì method đó private.

Tương tự, một top-level class không khai báo `public` sẽ không trở thành public chỉ vì package được export:

~~~java
package com.acme.library.api;

class InternalCustomerMapper {
    // Package-private top-level class
}
~~~

Module khác không thể import `InternalCustomerMapper`. Export package không bỏ qua quy tắc truy cập của Java.

Do đó, API của một module được xác định bởi sự kết hợp giữa package export và các kiểu/thành viên public thực sự được định nghĩa trong package đó. Không nên xem `exports` như một thao tác làm mọi nội dung package trở thành API.

## 6. public, exports và opens có vai trò khác nhau

Ba khái niệm thường bị nhầm lẫn:

| Cơ chế | Phạm vi | Tác dụng |
|---|---|---|
| `public` | Kiểu/thành viên Java | Cho phép truy cập theo quy tắc ngôn ngữ Java |
| `exports` | Package trong module | Cho phép module khác truy cập các kiểu public trong package |
| `opens` | Package trong module | Cho phép deep reflection vào package ở runtime |

`exports` phục vụ truy cập API thông thường. `opens` phục vụ reflection, chẳng hạn framework cần đọc hoặc ghi field private, gọi constructor không public hoặc phân tích metadata bằng reflection.

Ví dụ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Module khác có thể dùng API public trong `com.acme.domain.api` nếu đọc được module `com.acme.domain`. Module `com.acme.json` được phép deep reflection vào `com.acme.domain.model`. Việc mở package không làm các kiểu trong package đó trở thành API public để mã nguồn module khác import.

Một package đã export cũng không mặc nhiên mở cho deep reflection vào các thành viên không public. Nếu framework cần truy cập sâu, hãy khai báo `opens` riêng cho package và module đích phù hợp.

## 7. Qualified exports: chỉ công khai cho module được chọn

Một module có thể export package cho tất cả module hoặc chỉ cho một danh sách module đích.

Export không giới hạn:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.spi to
        com.acme.plugin.alpha,
        com.acme.plugin.beta;
}
~~~

Qualified export hữu ích khi module muốn cho phép một số module tích hợp sử dụng SPI, trong khi giữ package đó khỏi các module khác. Tên module đích phải là tên module hợp lệ trong cấu hình; việc chỉ khai báo `requires com.acme.library` ở một module không được liệt kê không cấp quyền truy cập package.

Ví dụ, `com.acme.plugin.alpha` có thể import các kiểu public trong `com.acme.library.spi` nếu nó đọc được module thư viện. `com.acme.application` không thể import các kiểu đó nếu không nằm trong danh sách đích của qualified export.

Qualified export vẫn không thay đổi access modifier. Một class package-private trong `com.acme.library.spi` vẫn không thể được import từ module plugin.

## 8. Module trên classpath và unnamed module

Khi một JAR được đặt trên classpath, JVM nạp các lớp của nó vào unnamed module gắn với class loader tương ứng. Nếu JAR chứa `module-info.class`, descriptor đó bị bỏ qua trong cách nạp classpath thông thường.

Unnamed module có quy tắc truy cập khác named module: nó đọc các module trong boot layer và các package của unnamed module được export/open theo cơ chế tương ứng. Do đó, một lớp public trên classpath có thể được ứng dụng classpath truyền thống sử dụng mà không cần `exports` trong descriptor.

Điều này giải thích vì sao một thư viện có thể chạy khi nằm trên classpath nhưng gặp lỗi truy cập sau khi chuyển lên module path. Khi chuyển sang module path, descriptor bắt đầu có hiệu lực và package chưa export sẽ bị đóng đối với module bên ngoài.

Đừng dùng kết quả chạy trên classpath để kết luận rằng module descriptor đã công khai API đúng. Hãy thử chạy trong cấu hình JPMS thực tế.

## 9. Quan sát package được export

Dùng `jar --describe-module` để xem descriptor trong JAR:

~~~bash
jar --describe-module --file mods/com.acme.library.jar
~~~

Output có thể chứa:

~~~text
com.acme.library jar:file:///.../com.acme.library.jar!/module-info.class
exports com.acme.library.api
requires java.base mandated
~~~

Dòng `exports com.acme.library.api` cho biết package đã được export. Nếu package không xuất hiện trong phần exports, hãy kiểm tra `module-info.java` hoặc descriptor được đóng gói.

Có thể dùng `javap` để xem descriptor nhị phân:

~~~bash
javap --module-path mods --module com.acme.library module-info
~~~

Lệnh này giúp kiểm tra các directive đã biên dịch. Nếu sửa `module-info.java` nhưng vẫn dùng một JAR cũ, kết quả có thể vẫn phản ánh descriptor cũ. Hãy bảo đảm đã biên dịch và đóng gói lại đúng artifact trước khi chẩn đoán.

## 10. Ví dụ tổng hợp và các trường hợp lỗi

Giả sử thư viện có ba package:

~~~text
com.acme.library
├── com.acme.library.api
├── com.acme.library.internal
└── com.acme.library.spi
~~~

Descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin;
}
~~~

Kết quả truy cập:

| Nội dung | Module plugin | Module ứng dụng khác |
|---|---|---|
| Public class trong `api` | Truy cập được nếu đọc module thư viện | Truy cập được nếu đọc module thư viện |
| Public class trong `spi` | Truy cập được nếu đọc module thư viện | Không truy cập được qua module boundary |
| Public class trong `internal` | Không truy cập được qua module boundary | Không truy cập được qua module boundary |
| Package-private class trong `api` | Không truy cập được | Không truy cập được |
| Private member của public class | Không truy cập trực tiếp theo Java access control | Không truy cập trực tiếp theo Java access control |

Một số tình huống thường gặp:

- **Class public nhưng package không export:** mã ở module khác không thể import class qua ranh giới JPMS.
- **Package đã export nhưng class package-private:** module khác vẫn không thể import class đó.
- **Package export nhưng member private:** mã bên ngoài không thể gọi member private theo quy tắc Java.
- **Module có requires nhưng package không export:** readability đã có, nhưng accessibility chưa đủ.
- **Package được opens nhưng không exports:** framework có thể deep reflection theo cấu hình, nhưng mã nguồn module khác vẫn không thể dùng package như API thông thường.
- **JAR chạy được trên classpath nhưng không chạy được trên module path:** cần kiểm tra descriptor, requires và exports; classpath đã bỏ qua module descriptor.

## 11. Ghi nhớ

`public` trả lời câu hỏi **kiểu hoặc thành viên có được truy cập theo quy tắc Java hay không**. `exports` trả lời câu hỏi **package nào của module được công khai cho module khác**. Để dùng một public type xuyên module, module sử dụng cần đọc module cung cấp, package chứa kiểu phải được export cho module đó, và kiểu/thành viên phải đáp ứng access modifier của Java.

`exports` không làm class package-private trở thành public, không làm member private trở thành public, và `public` không tự động mở package qua JPMS. Khi thiết kế API module, hãy chọn package cần export, giữ package nội bộ không export, dùng qualified exports cho SPI giới hạn, và dùng `opens` riêng khi framework thật sự cần deep reflection.
