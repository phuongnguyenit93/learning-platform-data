# Khai báo exports và opens có đích trong module-info.java của ứng dụng

**Module:** JAVA_VERSION_JAVA16  
**Chương:** Đóng gói JDK  
**Áp dụng:** Java 16 trở lên; các directive JPMS exports và opens tiếp tục là cơ chế chuẩn trong JDK hiện đại.

Một ứng dụng Java module hóa thường có hai nhu cầu khác nhau: công khai một phần API để module khác gọi trực tiếp, và cho phép framework truy cập sâu vào model hoặc entity bằng reflection. Không nên mở toàn bộ module chỉ để đáp ứng cả hai nhu cầu.

Trong module-info.java, dùng **qualified exports** để công khai package cho một danh sách module cụ thể, và dùng **qualified opens** để cho một danh sách module cụ thể deep reflection tại runtime:

- **exports package.name to module.one, module.two;** cho phép các module được nêu sử dụng public API trong package theo quy tắc truy cập Java.
- **opens package.name to module.one, module.two;** cho phép các module được nêu truy cập sâu các thành viên không public trong package bằng reflection tại runtime.

Hai directive này giới hạn quyền theo module đích. Chúng không thay thế nhau, không tự tạo quan hệ dependency requires và không mở package cho mọi module.

## 1. Vì sao ứng dụng cần khai báo có đích?

Giả sử ứng dụng billing có:

- Package com.acme.billing.api chứa các kiểu public mà CLI và reporting cần dùng.
- Package com.acme.billing.model chứa entity mà JSON framework cần đọc/ghi bằng reflection.
- Package com.acme.billing.persistence chứa class nội bộ mà ORM cần ánh xạ.

Nếu dùng unqualified exports hoặc opens, mọi module đọc được module ứng dụng có thể nhận quyền tương ứng trên package. Điều đó làm phạm vi API hoặc reflection rộng hơn nhu cầu.

Qualified directive cho phép ứng dụng thể hiện hợp đồng rõ ràng:

| Package | Module được cấp quyền | Mục đích |
| --- | --- | --- |
| com.acme.billing.api | com.acme.cli, com.acme.reporting | Gọi public API |
| com.acme.billing.model | com.acme.json | Deep reflection để ánh xạ JSON |
| com.acme.billing.persistence | com.acme.orm | Deep reflection để ánh xạ persistence |

Các package khác tiếp tục được đóng kín. Khi thêm framework hoặc consumer mới, ứng dụng phải quyết định package nào thực sự cần công khai hoặc mở.

## 2. Khai báo qualified exports trong module-info.java

Directive exports có đích có cú pháp:

```java
exports package.name to module.one, module.two;
```

Ví dụ:

```java
module com.acme.billing {
    exports com.acme.billing.api
        to com.acme.cli, com.acme.reporting;
}
```

Module com.acme.cli và com.acme.reporting có thể truy cập các kiểu public trong com.acme.billing.api, nếu chúng đọc module com.acme.billing và tuân thủ các modifier truy cập Java.

Module consumer khai báo dependency:

```java
module com.acme.cli {
    requires com.acme.billing;
}
```

Sau đó consumer có thể import API:

```java
package com.acme.cli;

import com.acme.billing.api.Invoice;

public final class InvoiceCommand {
    public String display(Invoice invoice) {
        return invoice.number();
    }
}
```

Module com.acme.reporting cũng cần requires com.acme.billing nếu mã của nó sử dụng các kiểu public trong module billing. Directive exports ... to ... ở phía billing không tự tạo cạnh đọc module cho consumer.

## 3. Khai báo qualified opens cho framework

Directive opens có đích có cú pháp:

```java
opens package.name to module.one, module.two;
```

Ví dụ:

```java
module com.acme.billing {
    opens com.acme.billing.model to com.acme.json;
    opens com.acme.billing.persistence to com.acme.orm;
}
```

Ý nghĩa:

- Module com.acme.json có thể dùng deep reflection trên thành viên trong com.acme.billing.model.
- Module com.acme.orm có thể dùng deep reflection trên thành viên trong com.acme.billing.persistence.
- Các module khác không nhận quyền deep reflection thông qua hai directive này.

opens chỉ cấp quyền reflection tại runtime. Nó không cho phép mã nguồn module khác import trực tiếp kiểu trong package nếu package đó chưa được export. Nếu framework vừa cần gọi public API của ứng dụng vừa cần truy cập private field, hãy xác định riêng dependency và quyền cần thiết cho từng mục đích.

## 4. Kết hợp requires, exports và opens trong module ứng dụng

Một module-info hoàn chỉnh có thể trông như sau:

```java
module com.acme.billing {
    // Ứng dụng gọi API của các framework này.
    requires com.acme.json;
    requires com.acme.orm;

    // Public API chỉ dành cho các consumer được chọn.
    exports com.acme.billing.api
        to com.acme.cli, com.acme.reporting;

    // Chỉ mở các package cần deep reflection.
    opens com.acme.billing.model to com.acme.json;
    opens com.acme.billing.persistence to com.acme.orm;
}
```

Mỗi directive có một trách nhiệm:

| Directive | Trách nhiệm |
| --- | --- |
| requires com.acme.json | Module billing đọc và sử dụng API của module JSON |
| requires com.acme.orm | Module billing đọc và sử dụng API của ORM |
| exports ... to ... | Chọn module nào được gọi public API của billing |
| opens ... to ... | Chọn module nào được deep reflection vào package của billing |

Không thêm requires chỉ vì một module xuất hiện sau từ khóa to. Ví dụ, billing không cần requires com.acme.cli chỉ vì export API cho CLI. Quan hệ dependency thông thường đi từ consumer tới module cung cấp API.

Ngược lại, nếu code billing gọi trực tiếp API của JSON hoặc ORM, billing cần requires tương ứng. Nếu framework được khởi động hoàn toàn qua cơ chế khác, hãy khai báo đúng dependency theo kiến trúc thực tế; opens không tự thêm readability edge.

## 5. Ví dụ đầy đủ với API public và model private

Module descriptor:

```java
module com.acme.billing {
    requires com.acme.json;

    exports com.acme.billing.api to com.acme.cli;
    opens com.acme.billing.model to com.acme.json;
}
```

API công khai:

```java
package com.acme.billing.api;

public record InvoiceView(String number, long totalCents) {}
```

Model nội bộ:

```java
package com.acme.billing.model;

public final class InvoiceEntity {
    private String number;
    private long totalCents;

    public InvoiceEntity() {}

    public String number() {
        return number;
    }
}
```

Module CLI:

```java
module com.acme.cli {
    requires com.acme.billing;
}
```

Module JSON có thể dùng reflection để ánh xạ InvoiceEntity vì package model đã mở cho đúng module framework. Module CLI có thể gọi API InvoiceView, nhưng không được tự do deep reflection vào package model chỉ vì nó đọc module billing.

Ví dụ này minh họa ranh giới module; code thực tế cần thêm factory, constructor hoặc mapper để chuyển entity thành DTO và ngược lại. Đừng export package model chỉ vì muốn framework đọc private field.

## 6. Qualified exports không giới hạn theo từng class hoặc method

exports có đích áp dụng cho toàn package, không chọn riêng từng class hay method. Khi một package được export cho module đích:

- Các kiểu public trong package có thể được module đích sử dụng theo quy tắc Java.
- Modifier truy cập của từng class/member vẫn được áp dụng.
- Thành viên private không trở thành public.
- Các package con không tự động được export cùng package cha.

Ví dụ exports com.acme.billing.api to com.acme.cli; không export com.acme.billing.api.internal. Nếu consumer cần package con, phải quyết định rõ có export riêng hay thiết kế lại API để không lộ package nội bộ.

Không có cú pháp wildcard kiểu exports com.acme.billing.*. Hãy khai báo từng package cụ thể để phạm vi API có thể được review.

## 7. Qualified opens cũng áp dụng theo package

opens có đích mở toàn bộ package được chỉ định cho module đích, không giới hạn riêng field mà framework đang dùng:

- Framework có thể deep reflection vào các thành viên không public trong package đó theo quy tắc reflection.
- Các package khác không được mở theo directive này.
- Package được mở không đồng nghĩa với việc package được export cho truy cập Java thông thường.
- Mọi class trong package nên được xem là nằm trong phạm vi tin cậy của module framework được mở.

Vì vậy, tránh đặt credential, key material hoặc class nhạy cảm chung package với entity chỉ để framework ánh xạ. Nếu cần mở model cho ORM, tách package persistence/model có ranh giới rõ và chỉ mở phần cần thiết.

## 8. Tên module đích phải là module name

Phần sau to nhận tên module, không phải tên package, tên class hay tên artifact Maven/Gradle.

Ví dụ:

```java
exports com.acme.billing.api to com.acme.cli, com.acme.reporting;
opens com.acme.billing.model to com.acme.json;
```

Các tên như com.acme.cli, com.acme.reporting và com.acme.json phải khớp module name mà runtime nhận diện. Đừng suy luận tên module chỉ từ tên file JAR.

Có thể kiểm tra module name của thư viện:

```sh
jar --describe-module --file libs/json-framework.jar
```

Nếu JAR là automatic module, tên module có thể được suy ra từ metadata hoặc tên JAR. Với dependency production, ưu tiên thư viện công bố module name ổn định qua module descriptor hoặc Automatic-Module-Name; tránh dựa vào tên file có thể thay đổi khi nâng version.

Compiler có thể cảnh báo khi module đích trong qualified directive không tìm thấy trên module path lúc biên dịch. Hãy xác minh module name và cấu hình module path thay vì bỏ qua cảnh báo.

## 9. Module trên classpath và ALL-UNNAMED

Qualified exports và opens trong module-info.java nhắm tới named module. Code chạy trên classpath thuộc unnamed module, không có module name riêng để ghi sau to.

ALL-UNNAMED là target đặc biệt của một số tùy chọn launcher như --add-opens; nó không phải tên module hợp lệ để thay thế trong directive opens ... to ... của module-info.java.

Nếu framework vẫn chạy trên classpath và cần deep reflection, có thể dùng tùy chọn runtime hẹp theo package:

```sh
java --add-opens com.acme.billing/com.acme.billing.model=ALL-UNNAMED \
     -m com.acme.application/com.acme.application.Main
```

Đây là cấu hình runtime, không phải khai báo module descriptor. Với hệ thống module hóa hoàn toàn, ưu tiên chuyển framework thành named module và dùng qualified opens cho đúng module đó.

## 10. Kiểm tra module access trong code

API Module cho phép kiểm tra package có được export hoặc open cho một module đích:

```java
Module source = InvoiceEntity.class.getModule();
Module framework = JsonMapper.class.getModule();

boolean exported = source.isExported(
    "com.acme.billing.model", framework
);
boolean opened = source.isOpen(
    "com.acme.billing.model", framework
);
```

Trong ví dụ này, opened mới là điều cần kiểm tra nếu framework cần deep reflection. exported trả lời câu hỏi về ordinary access. Hai kết quả có thể khác nhau và không nên dùng thay nhau.

Có thể kiểm tra reflection trực tiếp từ code chạy trong module framework:

```java
Field field = InvoiceEntity.class.getDeclaredField("number");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "com.acme.billing.model is not open to the JSON module"
    );
}
```

Thử nghiệm phải chạy trên module path với đúng named module của framework. Nếu test chạy trên classpath, code thuộc unnamed module và kết quả không đại diện cho qualified opens tới một named module.

## 11. Xác minh module descriptor khi đóng gói

Sau khi build modular JAR, dùng jar để kiểm tra descriptor được đóng gói:

```sh
jar --describe-module --file build/libs/billing.jar
```

Có thể quan sát module resolution khi chạy ứng dụng:

```sh
java --show-module-resolution \
     -m com.acme.billing/com.acme.billing.Main
```

Các bước xác minh hữu ích:

1. Xác nhận JAR thực sự chứa module-info.class.
2. Xác nhận module name đúng với tên được ghi sau to.
3. Chạy ứng dụng trên module path thay vì vô tình đưa JAR lên classpath.
4. Kiểm tra public API consumer có thể compile và chạy.
5. Kiểm tra framework chỉ deep reflection được vào package đã mở.
6. Thử một module không nằm trong danh sách để xác nhận package không bị mở/export ngoài ý muốn.

module-info.java không có tác dụng như một module descriptor đang hoạt động nếu ứng dụng được chạy theo cách classpath thông thường. Hãy xác minh cấu hình đóng gói và launch command thực tế.

## 12. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Consumer không import được public class | Package chưa export cho consumer hoặc consumer chưa requires module nguồn | Kiểm tra cả qualified exports và module readability |
| Framework nhận object nhưng trySetAccessible() trả false | Package chưa mở cho module thực sự gọi reflection | Thêm qualified opens đúng package và module name |
| InaccessibleObjectException | Deep reflection bị module encapsulation chặn | Kiểm tra caller module và opens; không dùng exports để thay thế |
| Cảnh báo module đích không tìm thấy | Sai module name hoặc module chưa có trên module path lúc compile | Kiểm tra descriptor và module path của dependency |
| Directive đúng nhưng test vẫn không phản ánh | Test chạy trên classpath/unnamed module | Chạy test trong module path với named test/framework module |
| Mở package cho ALL-UNNAMED trong module-info | Nhầm target đặc biệt của launcher với module name | Dùng named module trong descriptor hoặc cấu hình --add-opens riêng khi thật sự cần |

Đừng thêm open module hoặc mở tất cả package chỉ để làm biến mất lỗi. Xác định đúng caller module và package bị chặn, rồi sửa directive nhỏ nhất đáp ứng nhu cầu.

## 13. Nguyên tắc thiết kế exports và opens

- Export package API ổn định, không export package implementation nếu consumer không cần.
- Dùng qualified exports khi chỉ một số module được phép compile và gọi API.
- Dùng qualified opens cho framework thật sự cần deep reflection.
- Tách package model/persistence khỏi package API để giới hạn vùng mở.
- Khai báo requires theo dependency code thực sự sử dụng; không nhầm nó với exports hoặc opens.
- Dùng module name ổn định của dependency, không dựa vào tên file JAR dễ thay đổi.
- Không mở package chứa dữ liệu nhạy cảm cho nhiều framework nếu không cần.
- Kiểm tra descriptor và quyền truy cập trong module path của môi trường chạy thật.

**Ghi nhớ:** Trong module-info.java, dùng exports package to moduleA, moduleB; để cấp ordinary access tới public API cho module được chọn; dùng opens package to moduleA; để cấp deep reflection tại runtime cho framework được chọn. Consumer vẫn cần requires để đọc module cung cấp API. Tên sau to là module name; ALL-UNNAMED chỉ thuộc một số tùy chọn launcher, không dùng trong directive. Giữ package API và package nội bộ tách biệt để giới hạn bề mặt truy cập.

## Tài liệu chính thức

- [JEP 261 — Module System: exports, opens và qualified directives](https://openjdk.org/jeps/261).
- [Java Language Specification — Module Declarations, Section 7.7](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html#jls-7.7).
- [Java SE 26 API — Module.isExported và Module.isOpen](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html).
- [Java SE 26 API — AccessibleObject.trySetAccessible](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible()).
- [Java SE 26 jar Tool — --describe-module](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html).
- [Java SE 26 java Launcher — --show-module-resolution và --add-opens](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
