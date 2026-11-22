# Qualified opens cho reflection có giới hạn

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích qualified opens trong Java Platform Module System (JPMS).
- Khai báo một package chỉ mở cho đúng module cần reflection.
- Phân biệt `opens`, `exports`, `open module` và command-line `--add-opens`.
- Xác định đúng module thực hiện reflection trong framework hoặc thư viện.
- Kiểm tra quyền mở ở runtime và chẩn đoán lỗi `InaccessibleObjectException`.
- Giới hạn rủi ro bằng package cụ thể, target cụ thể và kiểm thử trên module path.

## 1. Vì sao cần qualified opens?

JPMS đóng gói package bên trong named module. Một module không tự động cho phép module khác truy cập mọi thành phần nội bộ. Đây là cơ chế strong encapsulation: module công khai API theo hợp đồng và giữ các chi tiết triển khai ở bên trong.

Một số framework cần reflection sâu để thực hiện công việc của chúng. Ví dụ:

- ORM cần đọc hoặc gán private field của entity.
- Dependency injection framework cần truy cập constructor hoặc field được đánh dấu annotation.
- Serializer cần đọc field để chuyển object thành JSON/XML.
- Framework tạo proxy hoặc khôi phục object từ dữ liệu.

Nếu package chứa các member đó không được mở cho module thực hiện reflection, lời gọi `setAccessible(true)` có thể thất bại với `InaccessibleObjectException`.

Không phải toàn bộ module đều cần mở. Thông thường, chỉ một vài package chứa entity hoặc metadata cần được framework truy cập. **Qualified opens** cho phép mở đúng package cho một hoặc một nhóm module đích đã xác định.

## 2. Cú pháp qualified opens trong module-info.java

Cú pháp:

~~~java
opens <package-name> to <target-module>[, <target-module>...];
~~~

Ví dụ một module domain có API công khai và package persistence dành cho ORM:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Ý nghĩa:

- `com.acme.domain` là module sở hữu package.
- `com.acme.domain.persistence` là package được mở.
- `com.acme.orm` là module được phép thực hiện deep reflection vào package đó.
- Các package khác của module vẫn được đóng gói theo quy tắc bình thường, trừ khi có directive khác.

Nếu có hai framework thực sự cần truy cập cùng package, có thể khai báo cả hai target:

~~~java
module com.acme.domain {
    opens com.acme.domain.persistence
        to com.acme.orm, com.acme.mapper;
}
~~~

Tên target phải là tên module thực tế mà framework chạy trong đó. Đừng đoán tên module từ tên artifact hoặc tên package Java.

### 2.1. Package được mở là package nào?

Directive `opens` áp dụng cho một package cụ thể. Nếu entity nằm trong:

~~~text
com.acme.domain.persistence
~~~

thì mở package đó không tự động mở các package khác như:

~~~text
com.acme.domain.internal
com.acme.domain.security
com.acme.domain.admin
~~~

Nếu một framework cần reflection vào nhiều package, hãy liệt kê từng package có nhu cầu thực tế. Cách này giúp descriptor thể hiện rõ ranh giới được cho phép.

## 3. Qualified opens cho phép điều gì?

Qualified opens cho phép module đích thực hiện reflective access sâu vào package được mở, theo các quy tắc của Java Reflection API.

Ví dụ, entity có private field:

~~~java
package com.acme.domain.persistence;

public class CustomerEntity {

    private Long id;
    private String email;

    public CustomerEntity() {
    }
}
~~~

Một ORM có thể cần tìm field và cho phép truy cập:

~~~java
Field emailField =
        CustomerEntity.class.getDeclaredField("email");

if (!emailField.trySetAccessible()) {
    throw new IllegalStateException(
            "ORM cannot access CustomerEntity.email"
    );
}
~~~

Nếu `com.acme.domain.persistence` được mở cho đúng module chứa đoạn code ORM này, `trySetAccessible()` có thể bật quyền truy cập reflection sâu khi các điều kiện khác được đáp ứng.

Nếu package không được mở cho module gọi, `trySetAccessible()` có thể trả về `false`. Nếu dùng `setAccessible(true)`, lời gọi có thể ném `InaccessibleObjectException`.

Qualified opens không có nghĩa là framework được quyền sửa mọi field trong mọi tình huống. Reflection vẫn chịu các giới hạn của Java, chẳng hạn một số final field của record, hidden class hoặc static final field không thể được biến thành writable chỉ bằng cách mở package.

## 4. Phân biệt opens và exports

`opens` và `exports` phục vụ hai hợp đồng khác nhau.

| Tiêu chí | `exports` | `opens` |
|---|---|---|
| Mục đích | Công khai API của package | Cho phép deep reflection |
| Truy cập source code thông thường | Cho phép module đọc API public nếu có readability | Không tạo quyền import/truy cập API thông thường |
| Reflection vào private member | Không tự cho phép | Cho phép module đích thực hiện deep reflection |
| Phạm vi | Public type/member theo quy tắc Java | Package được mở cho reflection |
| Thời điểm chính | Compile time và runtime | Runtime |

Ví dụ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Module consumer có thể import public API trong `com.acme.domain.api` nếu có quan hệ readability phù hợp. ORM có thể reflection sâu vào `com.acme.domain.persistence`. Hai package có hai mục đích riêng.

Một qualified opens không làm package trở thành public API. Nếu code khác cần import class trong package đó, hãy thiết kế API hoặc export phù hợp thay vì dùng opens để giải quyết lỗi compile.

## 5. Phân biệt qualified opens, unqualified opens và open module

### 5.1. Unqualified opens

~~~java
module com.acme.domain {
    opens com.acme.domain.persistence;
}
~~~

Directive này mở package cho mọi module ở runtime. Nó rộng hơn qualified opens vì không giới hạn target module.

Chỉ dùng khi thiết kế thực sự yêu cầu mọi module có thể reflection sâu vào package đó. Với framework cụ thể, hãy ưu tiên qualified opens.

### 5.2. Open module

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
    requires com.acme.common;
}
~~~

Khai báo `open module` mở tất cả package của module cho deep reflection ở runtime. Đây là phạm vi rất rộng.

Một open module không được khai báo thêm các directive `opens` riêng lẻ bên trong descriptor. Nếu cần mở một vài package có kiểm soát, hãy dùng module bình thường với qualified opens.

### 5.3. Bảng lựa chọn

| Cách khai báo | Phạm vi |
|---|---|
| `opens p to m;` | Chỉ module m |
| `opens p;` | Mọi module |
| `open module M { ... }` | Mọi package của module M |

Với một ORM cần truy cập private field của entity, `opens package to orm.module` thường là lựa chọn thể hiện đúng ý định nhất.

## 6. Xác định đúng module đích của framework

Một lỗi cấu hình phổ biến là mở package cho module của ứng dụng, trong khi code thực hiện reflection lại nằm trong module của framework.

Ví dụ luồng gọi:

~~~text
Application module
       |
       | gọi API
       v
ORM framework module
       |
       | Field.setAccessible(...)
       v
Domain module
  package persistence
~~~

Module cần được đưa vào target của qualified opens là module thực hiện thao tác reflection, trong ví dụ là `com.acme.orm`. Module ứng dụng chỉ gọi API ORM không nhất thiết là module cần quyền đó.

### 6.1. Kiểm tra module name của JAR

Có thể dùng lệnh:

~~~bash
jar --describe-module --file libs/acme-orm.jar
~~~

Lệnh này hiển thị module descriptor hoặc tên automatic module của JAR. Nếu JAR khai báo `Automatic-Module-Name` trong manifest, tên đó thường được dùng làm module name khi chạy trên module path.

Không lấy tên Maven artifact hoặc package name làm module name nếu chưa xác minh.

Có thể kiểm tra module đang được JVM nhận diện bằng:

~~~bash
java --list-modules
~~~

Với ứng dụng đang chạy, có thể ghi nhận module của class thực hiện reflection:

~~~java
Module frameworkModule = OrmInternalAccessor.class.getModule();

System.out.println(frameworkModule.getName());
~~~

Nếu `getName()` trả về `null`, class đang thuộc unnamed module. Trường hợp đó cần xử lý khác với qualified opens trong descriptor.

## 7. Trường hợp framework chạy trên classpath

Qualified opens trong `module-info.java` chỉ định target bằng tên module. Nó không thể khai báo target đặc biệt `ALL-UNNAMED`.

Nếu framework vẫn chạy trong unnamed module trên classpath, có thể dùng command-line option tạm thời:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.persistence=ALL-UNNAMED -cp app.jar:libs/* com.acme.Main
~~~

Cờ này mở package ở runtime cho các unnamed module. Nó hữu ích để xác nhận chẩn đoán hoặc hỗ trợ một thư viện chưa thể chuyển sang named module.

Nếu framework đã là named module, hãy mở package cho đúng module đó:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.persistence=com.acme.orm --module-path mods -m com.acme.app/com.acme.Main
~~~

`--add-opens` là cấu hình runtime bên ngoài. Nó không thay đổi source descriptor đã đóng gói trong module và không phải một directive compile-time của `javac`.

Về lâu dài, hãy cân nhắc chuyển framework sang module path nếu thư viện hỗ trợ, sau đó ghi qualified opens trong descriptor của module sở hữu package. Như vậy, quyền reflection trở thành một phần của hợp đồng module có thể review và version cùng source code.

## 8. Kiểm tra openness tại runtime

Java cung cấp API để truy vấn module có mở package cho module khác hay không.

~~~java
Module domainModule = CustomerEntity.class.getModule();
Module ormModule = OrmInternalAccessor.class.getModule();

boolean openToOrm = domainModule.isOpen(
        "com.acme.domain.persistence",
        ormModule
);

System.out.println("Persistence package open to ORM: " + openToOrm);
~~~

`Module.isOpen(packageName, otherModule)` kiểm tra package có mở cho module đích được chỉ định hay không. Nó giúp xác nhận runtime đang nhìn thấy quan hệ openness như dự kiến.

Có thể kết hợp kiểm tra với `trySetAccessible()` trên member thực sự cần truy cập:

~~~java
Field field = CustomerEntity.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package is not open to the framework module"
    );
}
~~~

Hai phép kiểm tra có mục đích khác nhau:

- `isOpen` xác nhận cấu hình module.
- `trySetAccessible` xác nhận member cụ thể có thể bật quyền truy cập reflection trong ngữ cảnh hiện tại hay không.

Đừng chỉ kiểm tra bằng một test chạy trên classpath. Khi mọi code nằm trong unnamed module, ranh giới module có thể khác với production. Hãy chạy integration test trên module path giống môi trường triển khai.

## 9. Rủi ro khi mở package quá rộng

### 9.1. Lộ chi tiết triển khai

Khi package được mở cho framework, framework có thể phụ thuộc vào private field, tên member hoặc cấu trúc object. Một refactor nội bộ có thể phá ứng dụng dù public API không thay đổi.

### 9.2. Tăng coupling với framework

Qualified opens tạo một quan hệ vận hành giữa module domain và framework. Khi đổi ORM hoặc serializer, target module name và danh sách package có thể cần thay đổi.

### 9.3. Mở nhầm module

Nếu mở cho module ứng dụng trong khi framework thực hiện reflection, cấu hình vẫn không giải quyết được lỗi. Nếu mở cho `ALL-UNNAMED`, nhiều thư viện trên classpath có thể nhận quyền rộng hơn dự kiến.

### 9.4. Kiểm thử không phản ánh production

Test chạy trên classpath có thể không tái hiện lỗi encapsulation của named module. Ngược lại, test JVM có cờ `--add-opens` toàn cục có thể che giấu việc descriptor thiếu qualified opens.

### 9.5. Khó nâng cấp

Framework có thể đổi module name, đổi cách reflection hoặc không còn cần package cũ. Descriptor cũ có thể giữ quyền không cần thiết, hoặc khiến module resolution thất bại nếu target module không còn trong runtime configuration.

## 10. Quy trình thiết kế qualified opens có giới hạn

### Bước 1: Xác định member và package thực sự cần reflection

Ghi lại class, package và thao tác reflection gây lỗi. Đừng mở toàn bộ domain module chỉ vì một entity field bị chặn.

### Bước 2: Xác định module thực hiện reflection

Lấy module từ class thực hiện `setAccessible` hoặc `trySetAccessible`. Xác minh module name của framework bằng JAR descriptor hoặc runtime inspection.

### Bước 3: Khai báo qualified opens

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Chỉ thêm package và target có nhu cầu đã xác nhận.

### Bước 4: Chạy integration test trên module path

Kiểm tra:

- Module domain resolve thành công.
- Framework được nạp trong module đích dự kiến.
- Reflection vào member cần thiết hoạt động.
- Package không liên quan vẫn đóng.
- Các đường chạy serialize, hydrate entity hoặc injection hoạt động như mong đợi.

### Bước 5: Ghi nhận hợp đồng và thời điểm review

Trong tài liệu module hoặc cấu hình kiến trúc, ghi:

- Vì sao package phải mở.
- Framework/module đích đang nhận quyền.
- Thành phần nào sở hữu directive.
- Phiên bản framework đã kiểm thử.
- Điều kiện để thu hẹp hoặc gỡ directive khi framework thay đổi.

## 11. Ví dụ hoàn chỉnh

Giả sử project có hai module:

~~~text
modules/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/
│       ├── api/
│       │   └── CustomerService.java
│       └── persistence/
│           └── CustomerEntity.java
└── com.acme.orm/
    ├── module-info.java
    └── com/acme/orm/
        └── OrmInternalAccessor.java
~~~

Descriptor domain:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Descriptor ORM:

~~~java
module com.acme.orm {
    requires com.acme.domain;
}
~~~

Trong ví dụ, ORM có thể sử dụng public API được export của domain và reflection sâu vào package persistence đã mở. Nó không được tự động reflection sâu vào package khác của domain.

Khi chạy, cả hai module phải có mặt trên module path và module name phải khớp với qualified opens:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

Nếu target module `com.acme.orm` không có trong runtime configuration hoặc tên trong descriptor không khớp tên module thực tế, cấu hình không thể đáp ứng mục đích thiết kế.

## 12. Checklist review

Trước khi thêm hoặc giữ một qualified opens, hãy xác nhận:

- [ ] Đã xác định package cụ thể chứa member cần reflection.
- [ ] Đã xác định đúng module thực hiện reflection.
- [ ] Target trong directive khớp module name thực tế.
- [ ] Chỉ mở package cần thiết, không dùng `open module` cho một nhu cầu hẹp.
- [ ] Không dùng `exports` thay cho `opens` khi cần deep reflection.
- [ ] Đã kiểm tra `Module.isOpen` hoặc hành vi `trySetAccessible` ở runtime.
- [ ] Integration test chạy trên module path tương tự production.
- [ ] Đã ghi lý do, framework version và người sở hữu directive.
- [ ] Có kế hoạch review khi nâng cấp framework hoặc thay đổi package.

## Kết luận

Qualified opens là cách khai báo rõ ràng rằng một package cần hỗ trợ deep reflection cho một module cụ thể. Nó giữ các package còn lại trong trạng thái encapsulated và giúp module descriptor thể hiện đúng nhu cầu tích hợp với ORM, serializer hoặc dependency injection framework.

Hãy bắt đầu từ member và package cần truy cập, tìm đúng module thực hiện reflection, rồi mở package cho target đó. **Mở đúng package, đúng module và kiểm thử trên module path** giúp giữ được lợi ích của strong encapsulation trong khi vẫn hỗ trợ các framework cần reflection.
