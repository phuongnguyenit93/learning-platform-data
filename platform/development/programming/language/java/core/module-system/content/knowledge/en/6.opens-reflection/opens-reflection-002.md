# Qualified opens tới module cụ thể

Trong Java Platform Module System (JPMS), module có thể giữ package ở trạng thái đóng đối với reflection sâu, rồi chỉ mở package cần thiết cho một số module được chỉ định. Cách khai báo này gọi là **qualified opens**: dùng chỉ thị `opens` kèm danh sách module đích sau từ khóa `to`.

Qualified opens hữu ích khi một framework cần đọc hoặc thay đổi thành viên không public bằng reflection, nhưng ứng dụng vẫn muốn giới hạn quyền truy cập ở đúng framework đó. Ví dụ, module domain có thể mở package model cho module persistence để ORM ánh xạ entity, trong khi các module khác vẫn không được cấp cùng quyền deep reflection.

## 1. Vì sao cần qualified opens?

JPMS bổ sung ranh giới truy cập ở cấp module. Khi một package không được mở, module khác không mặc nhiên có thể dùng reflection sâu để truy cập các thành viên như private field, private method hoặc constructor không public.

Một số framework cần khả năng này để thực hiện công việc mà không yêu cầu lập trình viên viết mã truy cập thủ công:

- ORM cần đọc field, constructor hoặc metadata của entity.
- Framework dependency injection cần kiểm tra annotation và khởi tạo object.
- Thư viện serialization cần đọc hoặc ghi trạng thái object.
- Framework binding cần ánh xạ dữ liệu bên ngoài vào thuộc tính của object.

Nếu mở toàn bộ module cho reflection, phạm vi truy cập sẽ rộng hơn nhu cầu của một framework cụ thể. Qualified opens giúp module chỉ định package nào được mở và module nào được nhận quyền.

## 2. Cú pháp qualified opens

Cú pháp tổng quát:

```java
module module.name {
    opens package.name to target.module.one, target.module.two;
}
```

Trong đó:

- `opens` là directive mở một package cho deep reflection.
- `package.name` là package thuộc module đang khai báo.
- `to` bắt đầu danh sách module đích được nhận quyền.
- Các tên sau `to` là tên module, phân cách bằng dấu phẩy.

Ví dụ:

```java
module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence,
           com.example.json;
}
```

Package `com.example.customer.model` được mở cho hai module `com.example.persistence` và `com.example.json`. Module khác không có tên trong danh sách sẽ không được cấp quyền deep reflection thông qua directive này.

Qualified opens chỉ áp dụng cho package được ghi rõ. Nếu module có nhiều package cần mở cho cùng một framework, mỗi package cần một directive phù hợp:

```java
module com.example.customer {
    opens com.example.customer.entity
        to com.example.persistence;

    opens com.example.customer.value
        to com.example.persistence;
}
```

Không có wildcard để mở toàn bộ package con theo một prefix. Mỗi package là một đơn vị cần được xem xét và khai báo.

## 3. Ví dụ: mở package entity cho module ORM

Giả sử ứng dụng có hai module:

```text
customer/
└── src/
    └── com.example.customer/
        ├── module-info.java
        └── com/example/customer/
            ├── api/
            │   └── Customer.java
            └── model/
                └── CustomerEntity.java

persistence/
└── src/
    └── com.example.persistence/
        ├── module-info.java
        └── com/example/persistence/
            └── EntityMapper.java
```

Module customer có API công khai và entity nội bộ:

```java
package com.example.customer.api;

public interface Customer {
    String id();
    String email();
}
```

Entity có thể đóng gói trạng thái bằng các field private:

```java
package com.example.customer.model;

public class CustomerEntity {
    private String id;
    private String email;

    protected CustomerEntity() {
    }

    public CustomerEntity(String id, String email) {
        this.id = id;
        this.email = email;
    }
}
```

Descriptor của module customer:

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.model
        to com.example.persistence;
}
```

Hai directive có mục đích riêng:

- `exports com.example.customer.api` công khai API cho truy cập Java thông thường từ module khác.
- `opens com.example.customer.model to com.example.persistence` cấp quyền deep reflection trên package model cho module persistence.

Descriptor của module persistence khai báo dependency tới customer:

```java
module com.example.persistence {
    requires com.example.customer;
}
```

Module persistence có thể tham chiếu API đã export. Framework trong module này cũng có thể dùng reflection sâu trên package model vì module customer đã mở package đó cho đúng module đích.

## 4. Qualified opens cho phép điều gì?

Khi package được mở cho module đích, mã reflection chạy trong module đích có thể truy cập sâu vào các thành viên của lớp thuộc package đó, trong phạm vi các quy tắc reflection của Java.

Ví dụ, module persistence nhận một object entity thông qua API hoặc một luồng xử lý nội bộ. Nó có thể dùng reflection để đọc field private:

```java
package com.example.persistence;

import java.lang.reflect.Field;

public class EntityMapper {
    public Object readEmail(Object entity) throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField("email");

        if (!field.trySetAccessible()) {
            throw new IllegalAccessException(
                    "The entity package is not open to this module"
            );
        }

        return field.get(entity);
    }
}
```

`trySetAccessible()` thử cho phép truy cập reflective vào thành viên. Nếu module chứa lớp entity đã mở package cho module persistence, thao tác có thể được chấp nhận theo quy tắc JPMS. Nếu package không được mở phù hợp, phương thức có thể trả về `false`; các thao tác reflective tiếp theo sẽ không có quyền truy cập cần thiết.

Trong mã thực tế, framework thường tự xử lý việc kiểm tra khả năng truy cập và đưa ra thông báo lỗi. Ví dụ trên chỉ minh họa nơi qualified opens tác động: quyền reflection được cấp theo module chứa mã gọi reflection.

Qualified opens không làm field private trở thành public. Nó không thay đổi access modifier trong bytecode và cũng không biến package thành API Java thông thường. Nó cấp quyền cho cơ chế reflection sâu trong phạm vi được chỉ định.

## 5. Module đích là module nào?

Tên sau từ khóa `to` phải là tên module mà mã cần thực hiện reflection thuộc về. Đây là điểm quan trọng khi tích hợp framework.

Ví dụ, nếu thư viện ORM được đóng gói thành module `com.example.persistence`, descriptor phải mở package cho đúng tên đó:

```java
opens com.example.customer.model
    to com.example.persistence;
```

Tên module không nhất thiết trùng với tên artifact Maven, tên file JAR hoặc tên package Java. Khi dùng thư viện bên thứ ba, cần xác định tên module thực tế từ descriptor của JAR hoặc từ tên automatic module mà JAR công bố.

Có thể kiểm tra tên module của một JAR bằng:

```shell
jar --describe-module --file libs/persistence.jar
```

Nếu JAR là explicit module, kết quả hiển thị tên module trong descriptor. Nếu là automatic module, công cụ cho biết tên module được nhận diện. Dùng đúng tên đó trong qualified opens.

Nếu framework được chia thành nhiều module, cần xác định module nào thực sự thực hiện deep reflection. Không nên suy đoán rằng tên module của artifact tổng thể cũng là tên module thực hiện truy cập. Có thể phải kiểm tra tài liệu framework hoặc module descriptor của từng thành phần.

## 6. Qualified opens khác exports như thế nào?

Đây là hai directive dễ bị nhầm vì cùng nhắc tới package, nhưng chúng cấp các khả năng khác nhau.

| Tiêu chí | `exports` | Qualified `opens` |
|---|---|---|
| Mục đích | Công khai API Java thông thường | Cho phép deep reflection |
| Cú pháp | `exports package.name;` | `opens package.name to module.name;` |
| Phạm vi | Mọi module đọc module sở hữu, trừ khi dùng qualified exports | Chỉ module được liệt kê sau `to` |
| Truy cập kiểu public | Có thể truy cập nếu các quy tắc Java khác cho phép | Không tự công khai package cho truy cập mã nguồn thông thường |
| Truy cập private bằng reflection | Không tự cấp quyền deep reflection | Cấp quyền deep reflection trong phạm vi mở |
| Thời điểm tác động chính | Biên dịch và runtime | Reflection tại runtime |

Ví dụ chỉ export:

```java
module com.example.customer {
    exports com.example.customer.api;
}
```

Module khác có thể biên dịch mã tham chiếu các kiểu public trong package API. Nhưng nếu framework cần deep reflection vào field private của package model, export package API không giúp ích cho package model.

Ví dụ chỉ qualified opens:

```java
module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence;
}
```

Module persistence có thể dùng reflection sâu trong package model, nhưng không vì thế mà có thể import các lớp trong package model như một API Java thông thường. Muốn cho phép truy cập mã nguồn thông thường, cần `exports` phù hợp.

Một module có thể sử dụng cả hai directive cho cùng một package nếu thật sự cần cả API công khai lẫn reflection sâu:

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.model
        to com.example.persistence;
}
```

## 7. Qualified opens khác qualified exports

Qualified exports và qualified opens đều có danh sách module đích, nhưng ý nghĩa không giống nhau.

Qualified exports:

```java
exports com.example.customer.integration
    to com.example.orders, com.example.reporting;
```

Nó cho phép các module orders và reporting truy cập API Java thông thường trong package integration.

Qualified opens:

```java
opens com.example.customer.model
    to com.example.persistence;
```

Nó cho phép module persistence thực hiện deep reflection trên package model.

Chọn directive dựa trên loại truy cập cần cấp:

- Nếu module khác cần gọi method hoặc tham chiếu kiểu public trong package, xem xét `exports`.
- Nếu framework cần truy cập field, constructor hoặc method không public qua reflection, xem xét `opens`.
- Nếu chỉ một số module cần khả năng đó, dùng dạng qualified để giới hạn đối tượng nhận quyền.

Không cần mở package cho reflection chỉ vì một module khác sử dụng API public của package đó.

## 8. Giới hạn và quy tắc khi khai báo qualified opens

### 8.1. Chỉ mở package thuộc module hiện tại

Directive phải trỏ tới package được khai báo trong module chứa descriptor. Không thể dùng `opens` để mở package thuộc một module khác.

### 8.2. Không mở package con tự động

Nếu khai báo:

```java
opens com.example.customer.model
    to com.example.persistence;
```

thì package `com.example.customer.model` được mở. Các package con như `com.example.customer.model.internal` là package riêng và không tự động được mở theo prefix.

Nếu framework cần reflection sâu ở package con, cần khai báo thêm directive cho package đó.

### 8.3. Qualified opens không phải API compile-time

Mã nguồn trong module đích không thể dựa vào qualified opens để import lớp thuộc package chưa được export. Open chỉ liên quan tới deep reflection tại runtime.

Nếu cần cả hai khả năng, hãy khai báo riêng `exports` và `opens` theo đúng mục đích.

### 8.4. Không khai báo opens riêng trong open module

Nếu module bắt đầu bằng `open module`, tất cả package đã được mở cho deep reflection. Khi đó không khai báo thêm directive `opens` riêng lẻ trong thân module.

Ví dụ sau không hợp lệ về mặt thiết kế cú pháp module:

```java
open module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence;
}
```

Với open module, việc mở đã áp dụng toàn module. Nếu muốn giới hạn quyền cho một số package và module cụ thể, hãy dùng `module` thông thường với qualified opens.

### 8.5. Module đích phải được xác định đúng

Tên module sau `to` là danh tính module của bên nhận quyền reflection. Tên này cần khớp với module mà framework thực sự sử dụng khi chạy.

Khi một thư viện thay đổi cách đóng gói hoặc tách module, cần kiểm tra lại descriptor và cập nhật qualified opens nếu tên module đích thay đổi.

## 9. Ví dụ cấu hình cho nhiều framework

Giả sử ứng dụng dùng một module ORM và một module JSON mapper. Hai framework cần đọc trạng thái entity, nhưng ứng dụng muốn chỉ cấp quyền reflection cho đúng hai module đó.

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.entity
        to com.example.persistence,
           com.example.json;
}
```

Ở đây:

- Package `api` được công khai cho các module đọc customer.
- Package `entity` được mở cho module persistence và json.
- Một module khác đọc customer nhưng không nằm trong danh sách `to` không được cấp quyền deep reflection qua directive này.
- Package khác của customer vẫn giữ trạng thái đóng nếu không có directive opens hoặc open module.

Nếu một framework chỉ cần truy cập package entity, không cần mở toàn bộ package api hoặc toàn bộ module. Nếu framework cần thêm một package, hãy bổ sung đúng package đó sau khi xác định nhu cầu thực tế.

## 10. Khi framework chạy trên classpath

Qualified opens liệt kê tên các named module đích. Nếu mã framework chạy trong unnamed module vì được đặt trên classpath, không thể coi tên artifact hoặc package của nó là tên unnamed module để ghi vào danh sách `to`.

Trong một số tình huống tích hợp cũ, có thể cần tùy chọn runtime như `--add-opens` với đích `ALL-UNNAMED` để mở package cho mã chạy trong unnamed module:

```shell
java --add-opens com.example.customer/com.example.customer.entity=ALL-UNNAMED ...
```

Đây là tùy chọn dòng lệnh của JVM, có phạm vi tác động tại lần chạy đó. Nó không thay thế descriptor được thiết kế cho một named module đích. Khi framework được chuyển sang named module, nên xác định tên module thực tế và cân nhắc khai báo qualified opens tương ứng trong descriptor.

Không nên thêm `--add-opens` rộng chỉ để che giấu lỗi cấu hình. Hãy giới hạn package và đích truy cập theo đúng nhu cầu của framework.

## 11. Cách kiểm tra và xử lý lỗi reflection

Khi framework báo lỗi truy cập reflective, có thể lần lượt kiểm tra:

1. Xác định package chứa lớp mà framework đang thao tác.
2. Xác định module sở hữu lớp đó.
3. Xác định module chứa mã reflection của framework.
4. Kiểm tra descriptor của module sở hữu đã có qualified opens tới đúng module đích chưa.
5. Kiểm tra package có bị nhầm với package con hoặc package cùng tên trong module khác không.
6. Xác nhận ứng dụng đang chạy với đúng artifact và module path.
7. Chạy lại để xác nhận lỗi reflection đã được xử lý.

Có thể dùng `jar --describe-module` để xem tên module và các directive của JAR:

```shell
jar --describe-module --file libs/customer.jar
jar --describe-module --file libs/persistence.jar
```

Nếu descriptor chưa mở đúng package, bổ sung qualified opens trong module sở hữu package. Nếu tên module đích không đúng, sửa danh sách `to` theo module thực tế của framework.

## 12. Nguyên tắc thiết kế qualified opens

Khi thiết kế quyền reflection, nên giữ các nguyên tắc:

- Mở đúng package cần thiết, không mở cả namespace theo cảm tính.
- Liệt kê đúng module thực hiện reflection.
- Giữ API Java thông thường trong các package export có chủ đích.
- Chỉ dùng `opens` khi framework thật sự cần deep reflection.
- Ưu tiên qualified opens khi đã biết module đích.
- Kiểm tra lại tên module khi nâng cấp hoặc thay đổi cách đóng gói framework.
- Ghi rõ lý do mở package để người bảo trì hiểu dependency runtime.
- Đánh giá lại directive khi framework không còn cần truy cập package đó.

Qualified opens là một phần của hợp đồng runtime giữa module sở hữu dữ liệu và module framework. Khi khai báo có chủ đích, module có thể hỗ trợ ORM, serialization hoặc dependency injection mà vẫn giữ quyền reflection trong phạm vi cần thiết.

## Kết luận

Qualified opens là directive `opens package.name to target.module;` trong `module-info.java`. Nó mở một package cho deep reflection từ các module được liệt kê, giúp framework truy cập thành viên không public khi cần ánh xạ, inject hoặc tuần tự hóa object.

Nó khác `exports`: exports công khai API Java thông thường, còn qualified opens cấp quyền reflection sâu tại runtime. Qualified opens cũng không tự tạo module dependency và không cho phép mã nguồn import package chưa export.

Khi tích hợp framework, hãy xác định chính xác package cần mở và tên module thực hiện reflection. Giới hạn danh sách module đích giúp duy trì encapsulation, đồng thời cung cấp đủ quyền cho những thành phần runtime thực sự cần dùng.