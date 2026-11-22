# Strong encapsulation của module package

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích strong encapsulation trong Java Platform Module System (JPMS).
- Phân biệt package được export với package được open.
- Khai báo `exports`, qualified exports, `opens`, qualified opens và `open module`.
- Hiểu ảnh hưởng của module encapsulation tới reflection và framework.
- Dùng `--add-exports` hoặc `--add-opens` khi cần tương thích trong lúc phát triển hoặc chạy ứng dụng.
- Nhận biết lỗi truy cập package và chọn cách xử lý phù hợp.

## 1. Strong encapsulation là gì?

Trước JPMS, ứng dụng Java thường tổ chức class theo package nhưng package trên classpath không tạo ra ranh giới module rõ ràng. Một thư viện có thể chứa package nội bộ như `com.example.library.internal`; code khác vẫn có thể import các public class trong package đó nếu class nằm trên classpath.

JPMS đưa ra ranh giới module có chủ đích. Một named module chỉ cho module khác truy cập package của nó theo những quyền được khai báo trong module descriptor. Package không được export sẽ được giữ kín đối với code ở module khác, kể cả khi package chứa public class.

Ví dụ:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Module `com.example.customer` chỉ export package `com.example.customer.api`. Package `com.example.customer.internal` vẫn có thể chứa public class, nhưng module khác không thể sử dụng class đó như API thông thường.

Strong encapsulation có nghĩa là module kiểm soát rõ ràng package nào được truy cập qua ranh giới module và package nào chỉ dành cho nội bộ. Nó giúp giảm phụ thuộc vào implementation, hạn chế việc thư viện bên ngoài sử dụng nhầm API nội bộ và cho phép tác giả module thay đổi implementation mà ít ảnh hưởng đến consumer.

Đây là cơ chế đóng gói ở cấp module, không phải sandbox bảo mật để cô lập mã độc. Không nên xem JPMS là ranh giới bảo vệ thay cho security controls của ứng dụng hoặc hệ điều hành.

## 2. exports: công khai package cho module khác

Directive `exports` cho phép các module khác truy cập các public type trong package được export, cùng các thành viên mà quy tắc truy cập Java cho phép:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Ví dụ package API:

~~~java
package com.example.customer.api;

public class CustomerService {

    public Customer findById(String id) {
        return new Customer(id);
    }
}
~~~

Một module consumer có thể khai báo dependency:

~~~java
module com.example.application {
    requires com.example.customer;
}
~~~

Và import public API:

~~~java
import com.example.customer.api.CustomerService;
~~~

Nếu package `com.example.customer.internal` không được export, module consumer không thể import public class trong package đó theo cách thông thường. Việc class có modifier `public` không tự làm package trở nên công khai qua module boundary.

`exports` không làm private member hoặc package-private member trở thành public. Sau khi package được export, các quy tắc access control thông thường của Java vẫn áp dụng.

### 2.1. Qualified exports

Nếu package chỉ nên được dùng bởi một số module cụ thể, hãy dùng qualified exports:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    exports com.example.customer.spi to com.example.application,
                                      com.example.customer.adapter;
}
~~~

Ở đây:

- `com.example.customer.api` được export không giới hạn cho các module đọc được module này.
- `com.example.customer.spi` chỉ được export cho hai module được liệt kê.
- Module khác không nằm trong danh sách không được truy cập package SPI đó qua module boundary.

Qualified exports hữu ích khi muốn chia sẻ API giữa một nhóm module cộng tác nhưng vẫn giữ package đó ngoài public surface chung của thư viện.

## 3. opens: cho phép deep reflection

`exports` chủ yếu phục vụ truy cập API theo quy tắc Java thông thường. Framework có thể cần truy cập bằng reflection vào constructor, field hoặc method không public, ví dụ:

- Dependency injection cần đọc annotation hoặc gán private field.
- ORM cần đọc và ghi private field của entity.
- JSON mapper cần gọi constructor hoặc truy cập field không public.
- Test framework cần kiểm tra thành phần nội bộ.

Directive `opens` cho phép reflection sâu vào package tại runtime:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.persistence;
}
~~~

Package `com.example.customer.persistence` được mở cho reflection từ các module khác. Điều này không có nghĩa package đó được export để module khác import type trực tiếp trong source code.

### 3.1. Qualified opens

Nếu chỉ một framework module cần reflection, hãy giới hạn quyền mở package:

~~~java
module com.example.customer {
    requires org.hibernate.orm.core;

    exports com.example.customer.api;

    opens com.example.customer.persistence
            to org.hibernate.orm.core;
}
~~~

Trong ví dụ này, Hibernate module được phép deep reflection vào package persistence. Những module khác không nhận quyền đó chỉ vì package đã được mở cho Hibernate.

Hãy dùng qualified opens khi biết rõ module nào cần truy cập. Cách này thể hiện ý định trong module descriptor và tránh mở package rộng hơn mức cần thiết.

## 4. Phân biệt exports và opens

| Khả năng | `exports p` | `opens p` |
|---|---|---|
| Module khác import public type trong package ở compile time | Có | Không |
| Truy cập public API theo quy tắc Java | Có | Không tự cấp quyền truy cập source |
| Deep reflection vào private member | Không | Có |
| Mục đích chính | Công khai API | Hỗ trợ framework/reflection ở runtime |

Có thể dùng cả hai directive cho cùng một package nếu package vừa là API vừa cần framework truy cập sâu:

~~~java
module com.example.customer {
    exports com.example.customer.model;
    opens com.example.customer.model to org.example.mapper;
}
~~~

Trong nhiều thiết kế, package API và package cần reflection nên được tách riêng. Điều đó giúp module descriptor thể hiện rõ đâu là API dành cho consumer và đâu là package được mở cho framework.

## 5. Reflection bị giới hạn như thế nào?

Giả sử module chứa model:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Class model:

~~~java
package com.example.customer.internal;

public class CustomerRecord {

    private String email;

    public CustomerRecord(String email) {
        this.email = email;
    }
}
~~~

Một framework ở module khác muốn đọc private field `email`:

~~~java
Class<?> type = record.getClass();
Field field = type.getDeclaredField("email");

boolean accessible = field.trySetAccessible();

if (accessible) {
    Object value = field.get(record);
    System.out.println(value);
} else {
    throw new IllegalStateException(
            "Package is not open to the framework module");
}
~~~

Nếu package chứa `CustomerRecord` không được open cho module của framework, `trySetAccessible()` có thể trả về `false`. Dùng `setAccessible(true)` trong tình huống không được phép có thể ném `InaccessibleObjectException`.

Để cho phép framework module truy cập sâu, module sở hữu class có thể khai báo:

~~~java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.internal
            to org.example.mapper;
}
~~~

Nếu framework chạy trong unnamed module trên classpath, có thể mở package cho `ALL-UNNAMED` bằng option launcher, hoặc cân nhắc chuyển framework sang named module để quyền truy cập được khai báo rõ ràng.

Lưu ý: `opens` không làm private field trở thành public. Nó cho phép reflection vượt qua một số kiểm tra truy cập của Java khi caller thuộc module được mở quyền, theo các điều kiện của API reflection.

## 6. open module: mở tất cả package

Nếu một module được thiết kế chủ yếu cho framework cần reflection sâu trên nhiều package, có thể khai báo open module:

~~~java
open module com.example.customer {
    requires java.sql;
    exports com.example.customer.api;
}
~~~

`open module` làm tất cả package trong module được mở cho deep reflection tại runtime.

Điều này không đồng nghĩa với export tất cả package. Module khác vẫn không thể import public type từ package chưa được export theo cách thông thường.

Với open module, không khai báo thêm directive `opens` riêng lẻ trong module descriptor. Nếu chỉ một vài package cần reflection, nên dùng các directive `opens` cụ thể thay vì mở toàn module.

## 7. Bổ sung quyền truy cập bằng command line

Trong quá trình phát triển, migration hoặc tích hợp thư viện cũ, đôi khi bạn chưa thể sửa module descriptor ngay. JDK cung cấp các option để bổ sung quyền truy cập ở thời điểm biên dịch hoặc chạy.

### 7.1. --add-exports

`--add-exports` bổ sung quyền export một package tới module đích:

~~~bash
javac \
    --module-path mods \
    --add-exports com.example.customer/com.example.customer.internal=com.example.application \
    -d out \
    src/com.example.application/module-info.java \
    src/com.example.application/com/example/application/Main.java
~~~

Cú pháp:

~~~text
--add-exports <module>/<package>=<target-module>
~~~

Ví dụ trên cho phép `com.example.application` truy cập public type trong package internal của `com.example.customer` khi biên dịch.

Khi chạy ứng dụng, nếu cần cùng quyền truy cập ở runtime, truyền option tương ứng cho launcher:

~~~bash
java \
    --module-path mods \
    --add-exports com.example.customer/com.example.customer.internal=com.example.application \
    -m com.example.application/com.example.application.Main
~~~

### 7.2. --add-opens

`--add-opens` mở package cho deep reflection tại runtime:

~~~bash
java \
    --module-path mods \
    --add-opens com.example.customer/com.example.customer.internal=org.example.mapper \
    -m com.example.application/com.example.application.Main
~~~

Cú pháp:

~~~text
--add-opens <module>/<package>=<target-module>
~~~

Nếu framework ở classpath, có thể dùng:

~~~bash
java \
    -cp libs/mapper.jar \
    --add-opens com.example.customer/com.example.customer.internal=ALL-UNNAMED \
    -m com.example.application/com.example.application.Main
~~~

`--add-opens` là option runtime; nó không làm package có thể được import trong source code khi biên dịch. Nếu compile code cần truy cập public type trong package chưa export, hãy dùng `--add-exports` hoặc sửa module descriptor.

### 7.3. So sánh các option

| Option | Thời điểm | Tác dụng |
|---|---|---|
| `--add-exports` | Compile time với `javac`, hoặc runtime với `java` | Bổ sung quyền truy cập public API của package |
| `--add-opens` | Runtime | Cho phép deep reflection vào package |
| `--add-reads` | Compile time hoặc runtime tùy công cụ | Bổ sung quan hệ readability giữa các module |

Các option này giải quyết ba khía cạnh khác nhau: package visibility, reflective access và module readability. Một module có thể đọc module khác nhưng vẫn không được truy cập package chưa export; package được export cũng không tự động mở private member cho deep reflection.

## 8. Quan sát trạng thái export và open bằng Java API

`java.lang.Module` cung cấp các phương thức để kiểm tra quan hệ module:

~~~java
Module source = record.getClass().getModule();
Module caller = Mapper.class.getModule();

boolean canRead = caller.canRead(source);

boolean exported =
        source.isExported(
                "com.example.customer.internal",
                caller);

boolean open =
        source.isOpen(
                "com.example.customer.internal",
                caller);

System.out.println("Can read: " + canRead);
System.out.println("Exported: " + exported);
System.out.println("Open: " + open);
~~~

Ý nghĩa:

- `canRead(...)` kiểm tra module caller có readability tới module source hay không.
- `isExported(packageName, target)` kiểm tra package có được export cho module đích không.
- `isOpen(packageName, target)` kiểm tra package có được mở cho deep reflection đối với module đích không.

Các API này hữu ích khi framework cần chẩn đoán vì sao reflection hoặc truy cập type không thành công. Chúng cũng giúp log rõ module nào đang thiếu quyền thay vì chỉ báo một lỗi reflection chung chung.

## 9. Strong encapsulation của JDK internals

JPMS được giới thiệu từ Java 9, và quá trình siết chặt truy cập tới API nội bộ của JDK diễn ra qua nhiều phiên bản.

Từ Java 16, strong encapsulation được áp dụng mặc định rộng hơn đối với các API nội bộ của JDK. Java 17 tiếp tục hoàn tất việc encapsulate mạnh các phần nội bộ của JDK theo JEP 403. Một số API nội bộ quan trọng vẫn có ngoại lệ tương thích, nhưng ứng dụng không nên dựa vào package `sun.*` hoặc các implementation detail không được hỗ trợ.

Option `--illegal-access` từng hỗ trợ chuyển tiếp cho một số truy cập reflection cũ trong các phiên bản trước. Từ JDK 17, option này không còn khôi phục cơ chế truy cập cũ; nó bị vô hiệu hóa và chỉ phát cảnh báo khi được dùng.

Nếu thư viện cũ gặp lỗi truy cập, hướng xử lý nên là:

1. Cập nhật thư viện lên phiên bản hỗ trợ JPMS và JDK đang dùng.
2. Ưu tiên API công khai, được hỗ trợ của JDK thay cho internal API.
3. Nếu cần tương thích tạm thời, xác định chính xác module/package/target rồi dùng `--add-exports` hoặc `--add-opens` phù hợp.
4. Ghi lại và loại bỏ các override tạm thời khi thư viện đã được cập nhật.

Không nên mở hàng loạt package JDK hoặc thêm quyền rộng chỉ để làm mất thông báo lỗi. Làm như vậy khiến dependency vào implementation detail khó được phát hiện và duy trì.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `package ... is not visible` | Package chưa được export tới module consumer | Khai báo `exports` hoặc `--add-exports` |
| `InaccessibleObjectException` | Package chưa mở cho module đang reflection | Dùng `opens` hoặc `--add-opens` |
| `trySetAccessible()` trả về `false` | Điều kiện truy cập sâu chưa được đáp ứng | Kiểm tra package, module caller và quan hệ open |
| Framework truy cập được public API nhưng không đọc private field | Package chỉ được export, chưa được open | Thêm qualified `opens` cho framework |
| Code đọc được module nhưng không import được package | Readability có nhưng package visibility chưa có | Kiểm tra riêng `requires` và `exports` |
| Ứng dụng phụ thuộc `sun.*` lỗi sau khi nâng JDK | Internal API đã bị encapsulate mạnh | Chuyển sang API được hỗ trợ hoặc cập nhật thư viện |

Khi xử lý lỗi, hãy xác định ba thông tin: module sở hữu package, package cần truy cập và module caller. Sau đó mới quyết định cần readability, export hay open. Việc chọn đúng quyền giúp module descriptor phản ánh đúng thiết kế thay vì cấp quyền quá rộng.

## 11. Tóm tắt

Strong encapsulation của JPMS đặt package dưới sự kiểm soát của module descriptor. `exports` công khai package cho truy cập API theo quy tắc Java; `opens` cho phép deep reflection ở runtime. Qualified exports và qualified opens giới hạn quyền cho từng module cụ thể, còn `open module` mở tất cả package cho reflection mà không tự export chúng.

Khi gặp lỗi truy cập, hãy phân biệt readability, package export và reflective open. Dùng `--add-exports` hoặc `--add-opens` như override có mục tiêu khi cần, sau đó đưa quyền cần thiết vào module descriptor hoặc cập nhật framework để ứng dụng giữ được ranh giới module rõ ràng.

Tài liệu tham khảo:

- [The Java Module System — JLS, Chapter 7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [AccessibleObject — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
