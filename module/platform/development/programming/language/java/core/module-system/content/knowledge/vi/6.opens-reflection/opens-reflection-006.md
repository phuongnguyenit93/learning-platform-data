# Framework cần opens để bind, proxy hoặc serialize

Java Platform Module System (JPMS) tạo ranh giới truy cập giữa các mô-đun. Một lớp có thể là public nhưng framework vẫn không được phép đọc hoặc thay đổi field private của lớp đó bằng deep reflection. Đây là lý do ứng dụng modular đôi khi gặp lỗi khi framework thực hiện data binding, dependency injection, tạo proxy hoặc serialization.

Chỉ thị **opens** trong module-info.java cho phép một mô-đun cụ thể thực hiện deep reflection trên một package ở runtime. Khi dùng đúng phạm vi, ứng dụng vẫn giữ được ranh giới API trong khi framework có thể truy cập những thành viên nội bộ mà nó cần.

## 1. Vì sao framework cần opens?

Nhiều framework hoạt động bằng cách kiểm tra cấu trúc lớp lúc runtime. Thay vì chỉ gọi những phương thức public mà mã ứng dụng gọi trực tiếp, chúng có thể cần:

- Đọc metadata của field, method, constructor và annotation.
- Tạo đối tượng bằng constructor mà ứng dụng không gọi trực tiếp.
- Gán giá trị vào field hoặc gọi setter khi bind dữ liệu.
- Đọc field private để serialize object thành JSON hoặc định dạng khác.
- Khôi phục object từ dữ liệu đã serialize.
- Tạo proxy hoặc lớp hỗ trợ dựa trên metadata của lớp gốc.

Ví dụ một entity:

~~~java
package com.example.customer.model;

public class Customer {
    private long id;
    private String name;

    protected Customer() {
    }

    public String getName() {
        return name;
    }
}
~~~

Mã nghiệp vụ có thể dùng getter public. Tuy nhiên, một ORM hoặc thư viện data binding có thể muốn gọi constructor không public và gán trực tiếp field private. Việc framework nhìn thấy lớp Customer không đồng nghĩa nó được phép thực hiện mọi thao tác reflection trên các thành viên của lớp.

Nếu package nằm trong named module và chưa được mở, framework có thể gặp java.lang.reflect.InaccessibleObjectException khi cố truy cập sâu.

## 2. exports và opens giải quyết hai việc khác nhau

Đây là khác biệt quan trọng nhất khi cấu hình JPMS:

| Chỉ thị | Mục đích | Ví dụ sử dụng |
| --- | --- | --- |
| **exports** | Cho phép mô-đun khác truy cập API public của package bằng mã Java thông thường. | Ứng dụng import CustomerService. |
| **opens** | Cho phép deep reflection vào package tại runtime, kể cả thành viên không public theo quy tắc reflection. | ORM đọc field private hoặc serializer truy cập constructor. |

Ví dụ module descriptor:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.model to com.example.orm;
}
~~~

Mô-đun khác có thể sử dụng API public trong com.example.customer.api. Riêng mô-đun com.example.orm được phép deep reflection trên com.example.customer.model.

Khai báo opens không làm package trở thành API có thể import tùy ý. Ngược lại, exports không tự cấp quyền deep reflection vào field private. Một package có thể vừa được export vừa được open nếu thiết kế thực sự cần cả hai khả năng.

## 3. Cách khai báo opens trong module-info.java

### 3.1. Mở package cho mọi mô-đun

~~~java
module com.example.customer {
    opens com.example.customer.model;
}
~~~

Đây là unqualified opens. Mọi mô-đun khác có thể thực hiện deep reflection trên package model tại runtime.

Cách này đơn giản nhưng phạm vi rộng. Nếu chỉ một framework cần truy cập, nên dùng qualified opens để giới hạn quyền.

### 3.2. Chỉ mở cho một framework

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.orm;
}
~~~

Mô-đun com.example.orm được phép deep reflection trên package model. Những mô-đun khác không được cấp quyền chỉ vì chúng đọc được mô-đun customer.

Có thể mở nhiều package cho cùng một framework:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.orm;
    opens com.example.customer.persistence to com.example.orm;
}
~~~

Hoặc mở một package cho nhiều framework:

~~~java
module com.example.customer {
    opens com.example.customer.model to
        com.example.orm,
        com.example.json;
}
~~~

Hãy dùng đúng module name của framework. Tên artifact hoặc tên file JAR không phải lúc nào cũng giống tên mô-đun. Có thể xác minh bằng jar --describe-module --file path/to/framework.jar.

### 3.3. Mở toàn bộ mô-đun

~~~java
open module com.example.customer {
    exports com.example.customer.api;
    requires com.example.validation;
}
~~~

open module mở tất cả package của mô-đun cho deep reflection tại runtime. Đây là lựa chọn có phạm vi rộng và thường chỉ phù hợp khi framework cần reflection trên nhiều package mà không thể liệt kê rõ từng package.

Nếu chỉ ORM cần truy cập package model, mở riêng package đó dễ kiểm soát hơn mở toàn bộ mô-đun.

## 4. Data binding: framework ánh xạ dữ liệu vào object

Data binding chuyển dữ liệu bên ngoài thành object Java hoặc chuyển object thành cấu trúc dữ liệu. Các framework có thể dùng constructor, setter, getter, field và annotation để thực hiện việc ánh xạ.

Ví dụ request JSON:

~~~json
{
  "id": 42,
  "name": "An"
}
~~~

Object đích:

~~~java
package com.example.customer.model;

public class Customer {
    private long id;
    private String name;

    protected Customer() {
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Nếu framework chỉ gọi getter/setter public, nó có thể không cần deep reflection vào field private. Nhưng nếu framework dùng field access hoặc cần gọi constructor không public, package có thể phải được mở.

Ví dụ module descriptor cho một mô-đun mapper:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.mapper;
}
~~~

Cấu hình này cho phép mapper truy cập sâu package model. Nếu mapper cần import một API public khác của customer, vẫn phải khai báo requires và package API phải được exports phù hợp.

Đừng mở package theo suy đoán. Hãy kiểm tra lỗi thực tế hoặc tài liệu của framework để biết package nào và module name nào cần được mở.

## 5. Serialization: đọc object và khôi phục object

Serialization thường cần đọc trạng thái object để tạo JSON, XML hoặc định dạng khác. Deserialization thực hiện chiều ngược lại: tạo object và gán dữ liệu vào các thuộc tính.

Một serializer có thể dùng getter public, nhưng một số cấu hình hoặc thư viện dùng reflection để truy cập field private. Nếu package nằm trong named module, serializer cần được cấp quyền deep reflection.

Ví dụ với mô-đun ứng dụng:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.json;
}
~~~

Tên com.example.json chỉ là tên minh họa. Khi dùng một thư viện JSON thực tế, hãy xác minh module name của đúng phiên bản đang chạy.

Nếu thư viện JSON nằm trên classpath, nó thuộc unnamed module. Module descriptor không thể ghi tên một unnamed module trong qualified opens. Khi đó có thể cấu hình JVM bằng --add-opens với đích ALL-UNNAMED:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=ALL-UNNAMED ...
~~~

Tham số trên mở package model của mô-đun customer cho deep reflection từ các lớp thuộc unnamed module trong runtime đó.

Nếu framework có named module, nên giới hạn đích theo module name của framework thay vì dùng ALL-UNNAMED.

## 6. Proxy và dependency injection

Framework dependency injection hoặc AOP có thể tạo proxy để bổ sung hành vi như transaction, logging, caching, lazy loading hoặc kiểm tra quyền.

Có hai cách triển khai proxy phổ biến:

- **JDK dynamic proxy:** tạo đối tượng proxy dựa trên interface.
- **Subclass/bytecode proxy:** tạo lớp con hoặc lớp bytecode hỗ trợ dựa trên class cần proxy.

Quyền truy cập cần thiết phụ thuộc vào cách framework tạo proxy, visibility của interface/class, package chứa kiểu và module của framework. opens có thể cần thiết khi framework phải kiểm tra hoặc truy cập thành viên không public bằng reflection. Tuy nhiên, opens không tự động giải quyết mọi lỗi tạo proxy: việc đọc kiểu, kế thừa lớp, truy cập constructor hoặc định nghĩa lớp proxy còn chịu các quy tắc readability, exports và quyền truy cập của Java.

Ví dụ mô-đun chứa service:

~~~java
package com.example.orders.internal;

public class OrderServiceImpl {
    public void submit() {
        // Xử lý đơn hàng.
    }
}
~~~

Nếu framework AOP cần deep reflection trên package implementation:

~~~java
module com.example.orders {
    opens com.example.orders.internal to com.example.aop;
}
~~~

Nếu framework cần truy cập một interface public từ mô-đun khác, package chứa interface đó còn phải được exports và mô-đun framework phải đọc được mô-đun sở hữu interface.

Khi gặp lỗi proxy, hãy đọc exception để phân biệt:

- InaccessibleObjectException: thường liên quan đến deep reflection; kiểm tra opens.
- IllegalAccessError hoặc lỗi package/type không visible: kiểm tra requires, exports và khả năng truy cập của kiểu.
- Lỗi định nghĩa lớp proxy hoặc truy cập constructor: kiểm tra cơ chế proxy, visibility, package và module layer; không mặc định chỉ cần thêm opens.

## 7. Framework nằm trên module path hay classpath?

Đây là chi tiết quyết định cách khai báo quyền mở.

| Vị trí của framework | Danh tính mô-đun | Cách mở package |
| --- | --- | --- |
| JAR có module descriptor trên module path | Named module | opens package to framework.module; |
| JAR cũ được nhận diện là automatic module trên module path | Automatic module có tên | Có thể dùng module name đã xác minh trong qualified opens. |
| JAR trên classpath | Unnamed module | Dùng --add-opens module/package=ALL-UNNAMED nếu cần deep reflection. |

Ví dụ khi framework là named module:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.fasterxml.jackson.databind;
}
~~~

Tên trên chỉ là ví dụ minh họa cho một module name đã được xác minh. Hãy kiểm tra đúng module name trong artifact thực tế, vì phiên bản thư viện hoặc cách đóng gói có thể ảnh hưởng tên mô-đun.

Nếu framework nằm trên classpath:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=ALL-UNNAMED -jar app.jar
~~~

ALL-UNNAMED áp dụng cho các unnamed module trong runtime tương ứng. Nó rộng hơn qualified opens tới một named module, vì vậy chỉ nên dùng khi framework thực sự chạy từ classpath.

## 8. Cách tìm package và module name cần mở

Khi gặp lỗi reflection, làm theo các bước sau:

1. Đọc đầy đủ exception và tìm dòng nêu tên mô-đun nguồn, package bị đóng và mô-đun đích.
2. Xác định package thuộc mô-đun ứng dụng hay thư viện bên thứ ba.
3. Xác định framework chạy trên module path hay classpath.
4. Nếu framework có JAR riêng, kiểm tra module name bằng jar --describe-module.
5. Mở đúng package cho đúng framework trong module-info.java hoặc cấu hình --add-opens khi cần.
6. Chạy lại test hoặc lệnh khởi chạy thực tế để xác nhận quyền reflection đã đủ.

Ví dụ thông báo:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private java.lang.String
com.example.customer.model.Customer.name accessible:
module com.example.customer does not "opens
com.example.customer.model" to module com.example.mapper
~~~

Thông báo này đã chỉ ra ba dữ kiện: package nguồn là com.example.customer.model, mô-đun sở hữu là com.example.customer, mô-đun đích là com.example.mapper.

Sửa trong descriptor:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.mapper;
}
~~~

Nếu lỗi đến từ framework trên classpath, dùng ALL-UNNAMED trong tham số JVM thay vì ghi tên giả định cho unnamed module.

## 9. Mở package ở module-info.java hay dùng --add-opens?

Hai cách có mục đích hơi khác nhau:

| Cách | Phù hợp khi | Đặc điểm |
| --- | --- | --- |
| opens trong module-info.java | Bạn quản lý mô-đun và biết framework nào cần reflection | Quyền mở được ghi trong module descriptor, dễ review cùng mã nguồn. |
| --add-opens | Cần tích hợp thư viện không thể sửa, kiểm tra nhanh hoặc điều chỉnh cấu hình triển khai | Quyền mở được cấp lúc chạy qua tham số JVM. |

Ví dụ tham số:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=com.example.mapper -m com.example.app/com.example.app.Main
~~~

Không nên thêm --add-opens cho mọi package để làm biến mất lỗi. Hãy giữ phạm vi nhỏ và ghi lại framework nào cần quyền đó, để cấu hình có thể được xem xét khi nâng cấp dependency.

## 10. Những nhầm lẫn thường gặp

**Package có lớp public thì framework luôn truy cập được:** Không đúng. JPMS còn kiểm soát package có được export hoặc mở hay không.

**Thêm exports sẽ sửa mọi lỗi reflection:** Không đúng. exports dành cho API truy cập thông thường; deep reflection vào thành viên không public cần opens.

**opens làm package có thể import từ mã nguồn:** Không đúng. opens không thay thế exports.

**Mọi framework đều có tên mô-đun:** Không đúng. Framework chạy trên classpath thuộc unnamed module; không thể ghi tên đó như một mô-đun đích trong qualified opens.

**Thêm opens là đủ để proxy hoạt động:** Không phải lúc nào cũng vậy. Cơ chế proxy còn phụ thuộc interface/class visibility, constructor, package, readability và module layer.

**Mở toàn bộ mô-đun luôn an toàn và tiện nhất:** Phạm vi mở rộng làm giảm khả năng đóng gói. Hãy mở đúng package và đúng framework cần truy cập.

## 11. Ví dụ descriptor cho ứng dụng dùng ORM và serializer

Giả sử ứng dụng có API public, model nội bộ cần ORM và JSON mapper truy cập sâu:

~~~java
module com.example.customer {
    requires java.sql;

    exports com.example.customer.api;

    opens com.example.customer.model to
        com.example.orm,
        com.example.json;
}
~~~

Ý nghĩa:

- Mô-đun customer đọc java.sql.
- Mô-đun khác có thể sử dụng API public trong package api nếu có quan hệ requires phù hợp.
- ORM và JSON mapper được deep reflection trên package model.
- Các package nội bộ khác vẫn giữ nguyên ranh giới đóng gói.

Nếu JSON mapper thực tế chạy trên classpath, hãy bỏ tên minh họa đó khỏi qualified opens và cấu hình --add-opens ...=ALL-UNNAMED theo runtime. Nếu framework dùng named module, thay bằng module name thực tế đã xác minh.

## 12. Checklist khi tích hợp framework với JPMS

- Xác định framework cần gọi API public hay cần deep reflection.
- Xác định package chứa model/entity/DTO mà framework truy cập.
- Xác định framework là named module, automatic module hay unnamed module.
- Dùng requires và exports cho dependency/API thông thường.
- Dùng opens hoặc --add-opens cho deep reflection.
- Giới hạn quyền mở vào package và framework thực sự cần.
- Kiểm tra riêng lỗi proxy vì opens không thay thế mọi quy tắc truy cập kiểu và package.
- Chạy test binding, proxy và serialization trên đúng module path hoặc classpath của môi trường triển khai.

JPMS không cấm framework hoạt động với object có field private. Nó yêu cầu mô-đun sở hữu package tuyên bố rõ package nào được mở cho reflection. Khi cấu hình đúng, framework vẫn có thể bind, tạo proxy hoặc serialize dữ liệu trong khi các package nội bộ khác tiếp tục được đóng gói.
