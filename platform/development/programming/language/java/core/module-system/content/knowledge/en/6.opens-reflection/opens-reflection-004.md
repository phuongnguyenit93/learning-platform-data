# Phân biệt opens với exports

Trong Java Platform Module System (JPMS), **exports** và **opens** đều xuất hiện trong **module-info.java**, nhưng chúng cấp hai loại quyền truy cập khác nhau. **exports** công bố một package để module khác có thể sử dụng các kiểu công khai theo quy tắc truy cập Java thông thường. **opens** cho phép module được chỉ định truy cập sâu bằng reflection vào các kiểu và thành viên trong package ở runtime.

Phân biệt đúng hai chỉ thị này rất quan trọng khi thiết kế API và tích hợp framework. Một package có thể được export để trở thành API công khai, được open để framework đọc hoặc sửa trạng thái đối tượng bằng reflection, hoặc được cấu hình cả hai nếu có nhu cầu riêng cho từng kiểu truy cập.

## 1. exports công bố API công khai

Một module thường chứa các package API mà module khác được phép sử dụng. Chỉ thị **exports** công bố package đó:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Giả sử package API có kiểu:

~~~java
package com.acme.domain.api;

public final class Customer {
    private final String id;

    public Customer(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
~~~

Module tiêu thụ cần đọc module domain:

~~~java
module com.acme.application {
    requires com.acme.domain;
}
~~~

Sau đó mã nguồn application có thể import và gọi API công khai:

~~~java
package com.acme.application;

import com.acme.domain.api.Customer;

public final class CustomerService {
    public String customerId() {
        Customer customer = new Customer("C-100");
        return customer.id();
    }
}
~~~

Nếu package **com.acme.domain.api** không được export, module application không thể truy cập các kiểu trong package đó theo cách sử dụng Java thông thường, dù class hoặc method có modifier **public**.

**exports** không biến mọi thành viên của package thành public. Quy tắc truy cập Java vẫn được áp dụng: module tiêu thụ có thể dùng public type và public/protected member phù hợp, nhưng không thể truy cập private field hoặc private method chỉ nhờ package được export.

## 2. opens cho phép truy cập sâu bằng reflection

Reflection cho phép chương trình khám phá class, field, method và constructor tại runtime. Nhiều framework dùng reflection để tạo đối tượng, ánh xạ dữ liệu, inject dependency, đọc annotation hoặc truy cập field không public.

Trong JPMS, package của một named module được đóng kín với truy cập reflective sâu từ module khác, trừ khi package được mở. Chỉ thị **opens** mở package cho reflection:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity;
}
~~~

Với khai báo này, các module khác có thể thực hiện deep reflection vào package **com.acme.domain.entity** tại runtime, theo quy tắc JPMS. Tuy nhiên, package này không được công bố thành API để mã nguồn module khác import và sử dụng class trực tiếp. **opens** không thay thế **exports**.

Ví dụ entity có field private:

~~~java
package com.acme.domain.entity;

public class CustomerEntity {
    private String email;

    public CustomerEntity(String email) {
        this.email = email;
    }
}
~~~

Một framework hoặc đoạn mã reflection có thể lấy field và yêu cầu quyền truy cập sâu:

~~~java
Field field = CustomerEntity.class.getDeclaredField("email");

if (field.trySetAccessible()) {
    Object value = field.get(entity);
    System.out.println(value);
}
~~~

Nếu module chứa entity không mở package tương ứng cho module gọi reflection, **trySetAccessible()** có thể trả về **false**. Với **setAccessible(true)**, JVM có thể ném **InaccessibleObjectException** khi module access rules không cho phép mở quyền truy cập.

Mục đích của **opens** là hỗ trợ truy cập runtime có kiểm soát. Nó không cấp quyền gọi các class hoặc method package-private/private bằng mã nguồn Java thông thường.

## 3. So sánh exports và opens

| Khía cạnh | exports | opens |
|---|---|---|
| Mục đích | Công bố API cho truy cập Java thông thường. | Cho phép deep reflection tại runtime. |
| Thời điểm quan trọng | Biên dịch và runtime. | Runtime reflection. |
| Public type/member | Module đọc được có thể truy cập theo quy tắc Java thông thường. | Có thể được khám phá bằng reflection; không tự tạo quyền truy cập mã nguồn. |
| Private member | Không cấp quyền truy cập private. | Cho phép reflection vượt qua kiểm tra truy cập khi caller và runtime đáp ứng quy tắc JPMS. |
| Framework ORM/serialization | Có thể cần nếu framework dùng public API. | Thường cần khi framework đọc/ghi field hoặc constructor không public. |
| Thay thế cho nhau? | Không. | Không. |

Có thể nhớ theo mục tiêu: **exports** dành cho người dùng API; **opens** dành cho cơ chế reflection. Một package có thể cần cả hai nếu vừa cung cấp API công khai vừa cho phép framework truy cập sâu vào trạng thái nội bộ.

## 4. Qualified exports và qualified opens

Không phải lúc nào package cũng cần mở hoặc export cho tất cả module. JPMS hỗ trợ giới hạn quyền truy cập vào một danh sách module cụ thể.

### Qualified exports

Cú pháp:

~~~java
module com.acme.domain {
    exports com.acme.domain.spi to com.acme.plugin, com.acme.adapter;
}
~~~

Chỉ các module được nêu tên mới nhận quyền truy cập package **com.acme.domain.spi** qua quy tắc exports. Module khác dù đọc được **com.acme.domain** vẫn không thể sử dụng package đó như API thông thường.

Qualified exports phù hợp với SPI hoặc API nội bộ được chia sẻ giữa một số module đã biết, chẳng hạn plugin host và các adapter chính thức.

### Qualified opens

Cú pháp:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

Chỉ module **com.acme.orm** được phép deep reflection vào package entity. Module khác không nhận quyền này chỉ vì chúng đọc được domain.

Qualified opens thường phù hợp khi ứng dụng dùng một framework ORM hoặc serializer cụ thể. Việc mở package đúng module giúp giới hạn bề mặt reflection và tránh cấp quyền rộng không cần thiết.

Tên module đích trong qualified directive phải là tên module JPMS hợp lệ, khớp với module thực tế trên module path. Nếu framework chạy trong unnamed module trên classpath, không thể viết **ALL-UNNAMED** như một tên đích trong **opens ... to ...** của descriptor; trường hợp đó có thể cần tùy chọn runtime **--add-opens**.

## 5. Ví dụ tích hợp framework ORM

Giả sử ứng dụng có hai module:

- **com.acme.domain** sở hữu entity và nghiệp vụ.
- **com.acme.persistence** chứa adapter ORM.

Module domain:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.persistence;
}
~~~

Module persistence:

~~~java
module com.acme.persistence {
    requires com.acme.domain;
    requires some.orm.framework;
}
~~~

Package **com.acme.domain.api** được export để application hoặc adapter gọi API công khai. Package **com.acme.domain.entity** chỉ được mở cho persistence để ORM có thể đọc annotation, khởi tạo entity hoặc ánh xạ field private bằng reflection.

Nếu persistence cần tham chiếu trực tiếp class entity trong mã nguồn, package entity cũng cần được export phù hợp, ví dụ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.entity to com.acme.persistence;
    opens com.acme.domain.entity to com.acme.persistence;
}
~~~

Ở đây hai directive giải quyết hai nhu cầu riêng: qualified exports cho phép code của persistence dùng public type trong entity package; qualified opens cho phép ORM thực hiện deep reflection vào package đó. Nếu adapter chỉ cần reflection và không tham chiếu class entity trực tiếp trong mã nguồn, có thể chỉ cần opens, tùy cách framework phát hiện và tải entity.

Không nên mở toàn bộ domain chỉ vì một framework cần truy cập vài entity. Hãy xác định package nào chứa kiểu cần ánh xạ và chỉ mở package đó cho module thực sự cần quyền.

## 6. open module và opens theo package

JPMS cung cấp hai mức cấu hình mở package.

Mở một package cụ thể:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity;
    opens com.acme.domain.value;
}
~~~

Chỉ các package được liệt kê mới được mở cho deep reflection từ các module khác.

Mở toàn bộ package của module:

~~~java
open module com.acme.legacy {
    requires some.framework;
    exports com.acme.legacy.api;
}
~~~

Một **open module** làm cho tất cả package trong module được mở cho deep reflection tại runtime. Điều đó không có nghĩa tất cả package đều được export để truy cập mã nguồn thông thường. Module vẫn cần các chỉ thị **exports** nếu muốn công bố API cho module khác.

Dùng open module có thể thuận tiện khi di chuyển một ứng dụng cũ phụ thuộc nhiều vào reflection. Tuy nhiên, nó mở rộng đáng kể phạm vi package mà module khác có thể truy cập sâu. Với thư viện hoặc hệ thống mới, ưu tiên **opens** theo từng package và qualified opens theo từng module.

Một open module không khai báo thêm các chỉ thị **opens** riêng trong descriptor; bản thân từ khóa **open** đã áp dụng cho mọi package. Các chỉ thị **exports** vẫn có thể được khai báo để xác định API công khai.

## 7. exports có cho phép reflection không?

Cần phân biệt reflection thông thường với deep reflection.

Khi package được export cho một module, module đó có thể truy cập public class và public member theo quy tắc Java. Reflection cũng có thể khám phá và gọi các thành phần public được phép truy cập. Nhưng export không cho phép caller vượt qua kiểm tra truy cập để đọc hoặc ghi private field, gọi private method hay constructor không public.

Ví dụ, package được export:

~~~java
module com.acme.user {
    exports com.acme.user.api;
}
~~~

Class:

~~~java
package com.acme.user.api;

public class User {
    private String token;

    public String username() {
        return "alice";
    }
}
~~~

Module tiêu thụ có thể dùng **User.username()**. Nhưng gọi:

~~~java
Field token = User.class.getDeclaredField("token");
token.setAccessible(true);
~~~

có thể thất bại vì package không được mở cho module caller. Để cho phép deep reflection, module cung cấp cần khai báo **opens com.acme.user.api to ...** cho module caller, hoặc dùng một open module nếu chủ đích là mở tất cả package.

Điều này giúp API công khai vẫn được bảo vệ khỏi việc truy cập sâu tùy tiện vào trạng thái nội bộ, ngay cả khi package đã export.

## 8. Tùy chọn --add-opens và --add-exports

Trong quá trình migration hoặc chẩn đoán lỗi framework, có thể cần mở quyền truy cập từ dòng lệnh mà chưa chỉnh descriptor. Tùy chọn **--add-opens** có dạng:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.entity=com.acme.persistence \
     --module-path mods \
     --module com.acme.application
~~~

Phần bên trái dấu bằng là module nguồn và package; phần bên phải là module đích nhận quyền deep reflection. Có thể dùng **ALL-UNNAMED** làm target khi caller nằm trong unnamed module, chẳng hạn framework chạy trên classpath:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.entity=ALL-UNNAMED \
     -cp "lib/*" com.acme.legacy.Main
~~~

Tùy chọn **--add-exports** có dạng tương tự nhưng cấp quyền truy cập package theo quy tắc exports:

~~~bash
java --add-exports com.acme.domain/com.acme.domain.internal=com.acme.adapter \
     --module-path mods \
     --module com.acme.application
~~~

**--add-exports** không cấp deep reflection vào private member; **--add-opens** không biến package thành API có thể import trong mã nguồn. Đây là hai quyền khác nhau.

Các tùy chọn này phù hợp làm giải pháp tương thích tạm thời, kiểm thử hoặc cấu hình runtime có chủ đích. Với thư viện do nhóm kiểm soát, nên đưa yêu cầu truy cập ổn định vào descriptor thay vì bắt mọi ứng dụng tiêu thụ tự nhớ thêm tham số JVM.

## 9. Lỗi thường gặp khi dùng reflection trong named module

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **InaccessibleObjectException** khi gọi setAccessible(true) | Package của module nguồn chưa mở cho module caller. | Thêm qualified **opens** hoặc cấu hình **--add-opens** đúng module/package. |
| **trySetAccessible()** trả về false | JPMS không cho caller mở quyền truy cập sâu vào thành viên. | Kiểm tra caller module và quyền opens; không giả định public class đồng nghĩa private field có thể truy cập. |
| **package is not visible** khi import class | Package chưa export cho module tiêu thụ hoặc module tiêu thụ chưa đọc module nguồn. | Kiểm tra **requires** và **exports**; opens không giải quyết truy cập mã nguồn. |
| Framework chạy trên classpath vẫn lỗi khi ứng dụng modular | Framework thuộc unnamed module và package chưa được mở cho ALL-UNNAMED. | Cân nhắc **--add-opens module/package=ALL-UNNAMED** hoặc chuyển framework sang named module. |
| Mở package này nhưng framework vẫn lỗi ở package khác | Framework đang truy cập một package khác chưa được mở. | Xác định chính xác package từ thông báo lỗi và mở đúng phạm vi cần thiết. |
| IDE chạy được nhưng production lỗi | IDE có cấu hình VM options hoặc module access khác môi trường production. | Đồng bộ runtime arguments và module descriptor giữa các môi trường. |

Khi xử lý lỗi, hãy đọc đầy đủ thông báo exception. Các thông báo của JPMS thường nêu module nguồn, package và module caller, giúp xác định directive cần xem xét. Tránh thêm hàng loạt **--add-opens** cho mọi package vì điều đó che khuất thiết kế truy cập thực tế và làm giảm tính đóng gói.

## 10. Thiết kế quyền truy cập theo nhu cầu

Một số lựa chọn điển hình:

| Nhu cầu | Directive phù hợp |
|---|---|
| Công bố API công khai để module khác import và gọi public method | **exports package.name** |
| Chỉ công bố API cho một số module đã biết | **exports package.name to target.module** |
| Cho framework truy cập sâu vào private field/constructor tại runtime | **opens package.name** |
| Chỉ cho một framework/module thực hiện deep reflection | **opens package.name to framework.module** |
| Tạm thời mở package cho framework chạy trong classpath | Runtime option **--add-opens module/package=ALL-UNNAMED** |
| Migration ứng dụng cũ cần deep reflection trên nhiều package | Cân nhắc **open module**, sau đó thu hẹp quyền theo package khi có thể |

Với module domain, một descriptor có thể trông như sau:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin.host;
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

API công khai được export cho mọi module đọc domain; SPI chỉ được export cho plugin host; entity chỉ được mở cho ORM. Các package khác vẫn được đóng kín. Đây là cách dùng module descriptor để thể hiện rõ ranh giới giữa API, điểm mở rộng và dữ liệu nội bộ cần reflection.

## 11. Checklist khi chọn opens hay exports

Trước khi thay đổi **module-info.java**, hãy xác định:

- Module tiêu thụ có cần import class và gọi public API bằng mã nguồn Java không? Nếu có, kiểm tra **exports**.
- Framework có cần truy cập private field, constructor hoặc method bằng reflection không? Nếu có, kiểm tra **opens**.
- Quyền truy cập cần áp dụng cho tất cả module hay chỉ một framework/adapter? Ưu tiên qualified directive khi biết rõ module đích.
- Package có thực sự cần được mở toàn bộ không, hay chỉ một package entity/configuration cụ thể?
- Caller là named module hay unnamed module? Trường hợp unnamed module có thể cần **ALL-UNNAMED** ở runtime option.
- Môi trường chạy thực tế có cùng VM options và module path với môi trường phát triển không?
- Directive có vô tình làm lộ package nội bộ hoặc tạo quyền reflection rộng hơn nhu cầu không?

**exports** và **opens** cùng phục vụ ranh giới module nhưng không thay thế nhau. Export một package để công bố API; open một package để cho phép deep reflection tại runtime. Chỉ cấp đúng quyền mà module tiêu thụ hoặc framework thực sự cần để giữ tính đóng gói, làm rõ hợp đồng API và giảm lỗi truy cập khi ứng dụng chạy trên module path.