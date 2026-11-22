# opens package cho deep reflection runtime

Trong Java Platform Module System (JPMS), một package có thể được mở để module khác dùng reflection truy cập sâu vào các thành viên không public. Directive `opens` trong `module-info.java` cấp quyền này ở thời gian chạy (runtime). Nó đặc biệt quan trọng với ORM, dependency injection, JSON serializer, framework binding và các thư viện cần đọc hoặc gán field private, gọi constructor không public hay kiểm tra annotation trên implementation.

`opens` không công khai package để mã Java thông thường import và gọi các kiểu public trong package đó. Việc truy cập API ở mức ngôn ngữ vẫn do `exports` và access modifier quyết định. Vì vậy, cần chọn đúng directive theo loại truy cập mà framework cần.

## 1. Reflection thông thường và deep reflection

Reflection cho phép chương trình khám phá class, method, constructor, field và annotation trong runtime. Ví dụ:

```java
Class<?> type = Customer.class;

for (var field : type.getDeclaredFields()) {
    System.out.println(field.getName());
}
```

Các API như `getDeclaredFields()` có thể liệt kê cả field private. Tuy nhiên, nhìn thấy metadata của một thành viên không đồng nghĩa được phép đọc hoặc thay đổi giá trị của nó. Java vẫn áp dụng kiểm tra truy cập khi reflection thực hiện thao tác trên thành viên.

Deep reflection là khả năng vượt qua các giới hạn truy cập thông thường để thao tác với thành viên như `private` hoặc package-private. Trên Java có hệ thống module, một module chứa package cần được mở cho module thực hiện deep reflection. Nếu package không mở phù hợp, việc cố bỏ qua kiểm tra truy cập có thể thất bại với `InaccessibleObjectException`.

Ví dụ một ORM có thể cần đọc field private để ánh xạ cột cơ sở dữ liệu, hoặc gọi constructor không public khi khôi phục entity. Đây là trường hợp `opens` được thiết kế để hỗ trợ.

## 2. Khai báo opens trong module-info.java

Có hai dạng khai báo phổ biến.

### Mở package cho mọi module

```java
module com.acme.domain {
    opens com.acme.domain.entity;
}
```

Package `com.acme.domain.entity` được mở cho tất cả module để deep reflection tại runtime. Cách này thuận tiện khi nhiều framework hoặc module khác nhau cần reflection vào package đó, nhưng phạm vi quyền rộng hơn mức cần thiết.

### Chỉ mở package cho module được chỉ định

```java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
```

Đây là qualified opens. Chỉ module `com.acme.orm` được phép deep reflection vào package `com.acme.domain.entity`. Các module khác vẫn không có quyền đó chỉ vì chúng đọc được `com.acme.domain`.

Có thể chỉ định nhiều module đích:

```java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm, com.acme.json;
}
```

Tên module đích phải đúng với tên trong module descriptor của framework. Dùng qualified opens giúp giới hạn quyền reflection theo đúng các thành phần cần thiết.

## 3. opens khác exports như thế nào?

Hai directive giải quyết hai nhu cầu khác nhau:

| Directive | Mục đích | Truy cập mã Java thông thường | Deep reflection |
|---|---|---|---|
| `exports p` | Công khai package như API cho module khác | Có thể truy cập kiểu public trong package nếu module đọc được và access modifier cho phép | Không tự cấp quyền truy cập sâu vào thành viên private |
| `opens p` | Mở package cho reflection tại runtime | Không cho phép module khác import và gọi API của package theo cách thông thường | Cho phép deep reflection |
| `exports p to m` | Chỉ công khai API cho module đích | Chỉ module được liệt kê | Không tự mở private member |
| `opens p to m` | Chỉ mở reflection cho module đích | Không công khai API ở mức biên dịch | Cho phép module đích deep reflection |

Nếu một package vừa là API công khai vừa cần framework truy cập private field, có thể kết hợp cả hai:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
```

Trong ví dụ này, ứng dụng sử dụng các kiểu public trong package API; ORM được mở quyền reflection vào package entity. Không nên thêm `opens` chỉ vì module khác cần gọi một method public, cũng không nên chỉ thêm `exports` khi framework cần thao tác với field private.

## 4. Ví dụ: mở entity cho ORM

Giả sử module domain chứa entity với field private:

```java
// module-info.java của com.acme.domain
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
```

Entity:

```java
package com.acme.domain.entity;

public class Customer {
    private String email;

    public Customer(String email) {
        this.email = email;
    }
}
```

Module ORM khai báo dependency nếu nó cần đọc module domain:

```java
module com.acme.orm {
    requires com.acme.domain;
}
```

Khi ORM nhận được một đối tượng `Customer` từ ứng dụng hoặc từ cơ chế tạo entity, nó có thể truy cập field bằng reflection:

```java
import java.lang.reflect.Field;

public class EntityInspector {
    public static Object readEmail(Object entity)
            throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField("email");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Module does not open the entity package to this ORM"
            );
        }

        return field.get(entity);
    }
}
```

Khi đoạn mã trên chạy từ module `com.acme.orm`, package `com.acme.domain.entity` được mở cho module đó nên `trySetAccessible()` có thể thành công. Nếu bỏ directive `opens`, JVM có thể từ chối việc bỏ qua access check, dù reflection vẫn tìm thấy field có tên `email`.

Ví dụ này tập trung vào thao tác reflection trên một object đã được cung cấp. Nếu ORM cần tham chiếu trực tiếp kiểu `Customer` trong mã nguồn, package chứa kiểu đó còn phải được export phù hợp. `opens` không thay thế yêu cầu đó.

## 5. Các API reflection liên quan

Các lớp trong `java.lang.reflect` cung cấp những API thường dùng khi làm deep reflection:

- `AccessibleObject.trySetAccessible()`: thử bật quyền truy cập bỏ qua kiểm tra ngôn ngữ Java; trả về `true` nếu thành công và `false` nếu không thể bật.
- `AccessibleObject.setAccessible(true)`: yêu cầu bật quyền truy cập; có thể ném `InaccessibleObjectException` khi module system không cho phép.
- `AccessibleObject.canAccess(target)`: kiểm tra hiện tại có thể truy cập thành viên với receiver cụ thể hay không.
- `Field.get(target)` và `Field.set(target, value)`: đọc hoặc ghi field sau khi quyền truy cập phù hợp đã được thiết lập.
- `Method.invoke(target, args...)`: gọi method bằng reflection.
- `Constructor.newInstance(args...)`: tạo object bằng constructor được tìm thấy qua reflection.

Ví dụ xử lý trường hợp không được mở:

```java
Field field = entity.getClass().getDeclaredField("email");

if (field.trySetAccessible()) {
    Object value = field.get(entity);
    System.out.println(value);
} else {
    System.out.println("The package is not open to this module");
}
```

Ưu tiên `trySetAccessible()` khi ứng dụng cần xử lý có kiểm soát trường hợp package không mở. Nếu dùng `setAccessible(true)`, hãy chuẩn bị xử lý `InaccessibleObjectException`. Không nên gọi `setAccessible(true)` trên mọi thành viên một cách máy móc; chỉ bật quyền cho thành viên thực sự cần thao tác.

## 6. Mở toàn bộ module bằng open module

Nếu module khai báo:

```java
open module com.acme.domain {
    requires java.sql;
}
```

thì tất cả package của module được mở cho deep reflection từ mọi module tại runtime. Đây là lựa chọn rộng hơn các directive `opens` riêng lẻ.

Một open module không cần khai báo từng package bằng `opens`; việc mở áp dụng cho toàn bộ package của module. Không nên dùng `open module` chỉ để giải quyết một framework cần truy cập một package, vì điều đó mở rộng phạm vi reflection cho tất cả package.

Với ứng dụng có yêu cầu đóng gói chặt, ưu tiên `opens package to framework.module;` để chỉ cấp quyền cho package và framework cụ thể. Dùng open module khi thiết kế thực sự yêu cầu tất cả package có thể được reflection từ nhiều module.

## 7. Mở package bằng tham số JVM --add-opens

Khi không thể sửa `module-info.java` của thư viện, có thể mở package tại lúc khởi chạy JVM bằng `--add-opens`.

Cú pháp:

```shell
java --add-opens source.module/package=target.module ...
```

Ví dụ mở package của module ứng dụng cho ORM:

```shell
java --add-opens com.acme.domain/com.acme.domain.entity=com.acme.orm \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

Nếu framework chạy trên classpath và thuộc unnamed module, có thể dùng `ALL-UNNAMED`:

```shell
java --add-opens com.acme.domain/com.acme.domain.entity=ALL-UNNAMED \
     -jar application.jar
```

`--add-opens` chỉ bổ sung quyền mở package cho runtime của lần chạy đó. Nó không sửa file JAR, không thay đổi `module-info.java` trong artifact và không tự tạo quyền truy cập ở thời điểm biên dịch. Với cấu hình build hoặc môi trường triển khai, cần đặt tham số này vào đúng lệnh JVM thực tế.

Không nhầm hai tùy chọn:

- `--add-opens` cấp quyền deep reflection ở runtime.
- `--add-exports` cho phép truy cập các kiểu public của package qua ranh giới module; nó không mở private member cho deep reflection.

## 8. Kiểm tra package đã được mở hay chưa

Có thể kiểm tra module và trạng thái mở package ngay trong Java:

```java
Module sourceModule = Customer.class.getModule();
Module callerModule = EntityInspector.class.getModule();

boolean opened = sourceModule.isOpen(
    "com.acme.domain.entity",
    callerModule
);

System.out.println("Package opened: " + opened);
```

Phương thức `Module.isOpen(packageName, otherModule)` kiểm tra package có mở cho module đích hay không. Phương thức `Module.isExported(packageName, otherModule)` kiểm tra quyền export cho truy cập API thông thường. Hai phép kiểm tra này giúp phân biệt lỗi do thiếu export với lỗi do thiếu opens.

Khi cần xem descriptor của JAR:

```shell
jar --describe-module --file domain.jar
```

Thông tin descriptor cho biết package nào được export hoặc mở và module đích nào được khai báo trong qualified opens. Khi kiểm tra ứng dụng đang chạy, cũng cần xem đúng JAR và đúng lệnh JVM được sử dụng trong môi trường đó.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `InaccessibleObjectException` khi gọi `setAccessible(true)` | Package của module chứa class chưa mở cho module gọi | Thêm qualified `opens` hoặc `--add-opens` phù hợp |
| `trySetAccessible()` trả về `false` | Module system không cho phép bỏ qua access check | Kiểm tra caller module và directive opens |
| Framework thấy field nhưng không đọc được giá trị | Tìm metadata thành công nhưng quyền deep reflection chưa được cấp | Mở package cho đúng module framework |
| Mã ứng dụng không import được class trong package chỉ có `opens` | `opens` không công khai API ở thời điểm biên dịch | Thêm `exports` nếu thực sự cần API public |
| Cấu hình chạy bằng IDE khác môi trường triển khai | Tham số `--add-opens` chỉ được cấu hình ở một lệnh JVM | Đồng bộ VM options ở môi trường chạy thực tế |

Khi xử lý lỗi, cần xác định module thực hiện reflection. Module đó có thể là module của framework, module tự động hoặc unnamed module. Mở package cho module ứng dụng chính chưa chắc đủ nếu thao tác reflection thực tế do một module framework khác thực hiện.

## 10. Nguyên tắc sử dụng opens an toàn

- Chỉ mở package có framework hoặc thư viện thực sự cần deep reflection.
- Ưu tiên qualified opens để giới hạn module đích.
- Giữ package API riêng với package entity/implementation khi kiến trúc cho phép.
- Chỉ dùng `open module` khi mọi package đều cần reflection rộng rãi.
- Dùng `--add-opens` như cấu hình runtime có chủ đích khi chưa thể sửa module descriptor; ghi nhận nó trong cấu hình triển khai.
- Không nhầm quyền reflection với quyền gọi API public; dùng `exports` cho API và `opens` cho deep reflection.
- Kiểm tra đúng caller module khi framework báo lỗi, vì quyền được cấp cho một module không tự động áp dụng cho module khác.

`opens` là cơ chế cho phép framework tương tác với implementation bên trong module mà không cần biến mọi field hoặc method thành API public. Mở đúng package cho đúng module giúp các framework hoạt động trong môi trường JPMS, đồng thời vẫn giữ được ranh giới truy cập của ứng dụng.