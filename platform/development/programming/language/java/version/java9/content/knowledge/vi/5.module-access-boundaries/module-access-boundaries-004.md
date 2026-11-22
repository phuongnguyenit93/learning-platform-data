# opens và quyền phản chiếu sâu vào thành viên

Trong Java Platform Module System (JPMS), từ khóa **opens** xác định package nào được phép truy cập bằng reflection ở mức sâu. Đây là cơ chế quan trọng đối với framework cần đọc hoặc ghi field private, gọi constructor không public, tạo object từ metadata hoặc ánh xạ dữ liệu khi chạy.

Từ Java 9, quyền truy cập giữa các module được kiểm soát rõ ràng. Một package có thể được export để module khác sử dụng API public trong mã Java thông thường, được open để module khác thực hiện deep reflection, hoặc được cấp cả hai quyền nếu kiến trúc thật sự cần. Hiểu đúng sự khác biệt này giúp ứng dụng vừa tương thích với framework vừa giữ được ranh giới đóng gói.

Các directive và API được trình bày dưới đây vẫn có trong JDK hiện đại. Ví dụ thực hành dùng cú pháp tương thích Java 17 trở lên.

## 1. Reflection thông thường và deep reflection

Reflection cho phép chương trình kiểm tra class, method, constructor, field và annotation lúc chạy. Ví dụ, **Class.getDeclaredFields()** liệt kê các field được khai báo trực tiếp trong class, còn **getDeclaredConstructor()** tìm constructor theo kiểu tham số.

Có hai mức truy cập cần phân biệt:

- **Truy cập thành viên vốn đã được phép:** chương trình dùng reflection để tìm và gọi một public method hoặc đọc một public field mà quy tắc truy cập Java và ranh giới module cho phép.
- **Deep reflection:** chương trình yêu cầu reflection bỏ qua một phần kiểm tra truy cập thông thường để thao tác với thành viên private, package-private hoặc protected. Ví dụ điển hình là **Field.setAccessible(true)** hoặc **trySetAccessible()** trước khi đọc một field private.

Trước JPMS, nhiều thư viện có thể dùng reflection sâu trên classpath mà không phải khai báo package nào cho phép truy cập. Khi module system được áp dụng, một module có thể giữ package nội bộ đóng kín. Module khác không được tự ý truy cập sâu vào package đó chỉ vì đã lấy được đối tượng Class hoặc Field.

Directive **opens** là cách chủ động cấp quyền deep reflection ở cấp package. Quyền này được xác định trong module descriptor hoặc được bổ sung khi khởi chạy bằng tùy chọn **--add-opens**.

## 2. Phân biệt exports và opens

**exports** và **opens** đều nói về package, nhưng phục vụ hai kiểu truy cập khác nhau.

| Directive | Mục đích | Truy cập mã Java thông thường | Deep reflection |
|---|---|---|---|
| **exports p;** | Công bố API public của package p | Có, cho module đọc module này | Không tự cấp quyền truy cập thành viên private |
| **exports p to m;** | Công bố API public cho module m | Có, chỉ cho module được chỉ định | Không tự cấp quyền deep reflection |
| **opens p;** | Mở package p cho reflection sâu | Không công bố API để import và biên dịch như exports | Có, cho mọi module |
| **opens p to m;** | Mở package p cho module m | Không công bố API để import và biên dịch như exports | Có, chỉ cho module m |
| **open module x { ... }** | Mở tất cả package của module x cho reflection sâu | Vẫn cần exports nếu module khác phải dùng API public | Có, cho mọi module |

Ví dụ, module có thể công bố API ổn định nhưng giữ implementation đóng kín:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.internal to com.example.serializer;
}
~~~

Trong ví dụ này:

- Module client có thể import và gọi các kiểu public trong **com.example.orders.api**, nếu nó đọc module **com.example.orders**.
- Module **com.example.serializer** có thể dùng deep reflection với các kiểu trong **com.example.orders.internal**.
- Các module khác không nhận quyền deep reflection vào package **internal**.
- Quyền **opens** không làm package **internal** trở thành API có thể import trực tiếp khi biên dịch.

Một package có thể vừa được **exports** vừa được **opens** nếu hai nhu cầu đều tồn tại. Tuy nhiên, hãy cấp đúng quyền cần thiết cho từng package; mở toàn bộ package chỉ để một framework đọc một vài field sẽ làm yếu ranh giới module không cần thiết.

## 3. Khai báo opens trong module-info.java

Directive **opens** được đặt bên trong module declaration, trong tệp **module-info.java**. Có hai dạng chính.

### 3.1. Mở package cho mọi module

~~~java
module com.example.domain {
    opens com.example.domain.model;
}
~~~

Mọi module khác có thể dùng deep reflection vào các kiểu trong package **com.example.domain.model**. Cách này phù hợp khi nhiều framework hoặc plugin đáng tin cậy cần truy cập cùng một package và việc mở rộng quyền đó là một quyết định kiến trúc có chủ đích.

### 3.2. Mở package có giới hạn

~~~java
module com.example.domain {
    opens com.example.domain.model to
            com.example.json,
            com.example.persistence;
}
~~~

Đây là qualified opens. Chỉ các module **com.example.json** và **com.example.persistence** nhận quyền deep reflection vào package **com.example.domain.model**.

Qualified opens thường là lựa chọn tốt khi xác định được module framework hoặc module tích hợp cụ thể. Tên ở vế **to** là tên module thực tế, thường được khai báo trong **module-info.java** của module nhận quyền.

### 3.3. open module

Nếu tất cả package của một module đều cần mở cho reflection, có thể khai báo:

~~~java
open module com.example.legacyintegration {
    requires java.sql;
    requires com.example.persistence;
}
~~~

**open module** mở mọi package của module cho deep reflection từ các module khác. Các directive **exports**, **requires**, **uses** và **provides** vẫn có ý nghĩa bình thường.

Một open module không được khai báo thêm directive **opens** bên trong. Nếu chỉ một hoặc vài package cần mở, hãy dùng **opens** trên từng package để giới hạn quyền rõ ràng hơn.

## 4. Dùng reflection API để kiểm tra và mở quyền truy cập

Các API reflection thường gặp:

- **Class.getDeclaredField(name):** tìm field được khai báo trực tiếp trong class, kể cả field private.
- **Field.trySetAccessible():** thử cho phép reflection bỏ qua kiểm tra truy cập Java thông thường. Trả về true nếu quyền truy cập được bật; trả về false nếu không thể bật.
- **Field.setAccessible(true):** yêu cầu bật quyền truy cập. Nếu module không mở package cần thiết, thao tác có thể ném **InaccessibleObjectException**.
- **Field.get(object):** đọc giá trị field sau khi quyền truy cập phù hợp đã được thiết lập.
- **AccessibleObject.canAccess(object):** kiểm tra liệu đối tượng reflection hiện có thể truy cập thành viên với receiver được cung cấp hay không.

**trySetAccessible()** hữu ích khi ứng dụng muốn xử lý tình huống package chưa được mở một cách có kiểm soát. Nếu trả về false, chương trình có thể báo lỗi cấu hình dễ hiểu hoặc chuyển sang API public thay vì để lỗi xuất hiện muộn hơn.

Ví dụ:

~~~java
Field field = type.getDeclaredField("secret");
if (!field.trySetAccessible()) {
    throw new IllegalStateException("Package is not open to this module");
}
Object value = field.get(instance);
~~~

Lời gọi **getDeclaredField()** tự nó không đồng nghĩa đã được phép đọc field private. Quyền truy cập được kiểm tra khi chương trình cố gắng bỏ qua access check hoặc sử dụng thành viên. Vì vậy, hãy kiểm tra kết quả **trySetAccessible()** trước khi gọi **get**, **set** hoặc method tương ứng.

**opens** không làm thay đổi modifier của field và không biến field private thành public. Nó cấp quyền cho reflection trong module được phép thực hiện thao tác sâu theo quy tắc của Java.

## 5. Giới hạn quyền theo module và theo package

Khi kiểm tra một lỗi reflection, cần xác định ba thông tin:

1. **Module chứa class đích:** module sở hữu package có field, constructor hoặc method mà framework muốn truy cập.
2. **Package chứa thành viên:** directive **opens** phải mở đúng package khai báo class đích. Mở package cha không tự động mở các package con.
3. **Module thực hiện reflection:** nếu dùng qualified opens, tên module ở vế **to** phải khớp với module chứa mã reflection tại runtime.

Ví dụ, các package sau là ba package độc lập:

- **com.example.model**
- **com.example.model.internal**
- **com.example.model.internal.mapping**

Khai báo **opens com.example.model.internal;** không mở **com.example.model.internal.mapping**. Nếu framework cần deep reflection vào cả hai package, phải mở từng package hoặc cân nhắc **open module** nếu toàn bộ module thực sự cần được mở.

Với ứng dụng dùng classpath, thư viện thường thuộc unnamed module. Trong trường hợp đó, qualified opens trong module descriptor không thể ghi **ALL-UNNAMED** như tên module nhận quyền. Tùy chọn dòng lệnh **--add-opens** hỗ trợ trường hợp này.

## 6. Dùng --add-opens khi cần cấu hình lúc chạy

**--add-opens** là tùy chọn JVM để mở một package cho module khác mà không sửa module descriptor của module nguồn. Cú pháp:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Ví dụ mở package **java.lang** của module **java.base** cho tất cả code chạy trên classpath:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

Ví dụ mở package nội bộ của ứng dụng cho một module framework cụ thể:

~~~bash
java --add-opens=com.example.domain/com.example.domain.internal=com.example.serializer -m com.example.app/com.example.app.Main
~~~

Cần phân biệt:

- **source-module** là module sở hữu package cần mở.
- **package** là tên package chính xác, không phải đường dẫn thư mục.
- **target-module** là module được cấp quyền; **ALL-UNNAMED** dùng cho các thư viện chạy trong unnamed module.
- Tùy chọn này có hiệu lực ở runtime của tiến trình được khởi chạy. Nó không thay thế **exports** để biên dịch mã import API public.

**--add-opens** hữu ích trong quá trình chuyển đổi ứng dụng cũ hoặc khi thư viện bên thứ ba chưa hỗ trợ JPMS đầy đủ. Hãy xem đây là cấu hình tương thích có chủ đích: xác định package, module nhận quyền, lý do cần mở và phiên bản framework dự kiến loại bỏ cấu hình đó.

Không nên thêm hàng loạt package JDK vào lệnh chạy chỉ để làm biến mất lỗi. Trước tiên tìm API public được hỗ trợ thay cho truy cập implementation nội bộ. Với module của chính ứng dụng, ưu tiên khai báo quyền cần thiết trong **module-info.java** để cấu hình được quản lý cùng mã nguồn.

## 7. Ví dụ hoàn chỉnh: mở một package nội bộ cho đúng module reflection

Ví dụ gồm hai named module:

- **com.example.model** chứa API tạo đối tượng và một class nội bộ có field private.
- **com.example.inspector** dùng reflection để đọc field private. Module model chỉ mở package nội bộ cho module inspector.

Cấu trúc thư mục:

~~~text
src/
  com.example.model/
    module-info.java
    com/example/model/api/CustomerFactory.java
    com/example/model/internal/CustomerRecord.java
  com.example.inspector/
    module-info.java
    com/example/inspector/Main.java
~~~

**Tệp src/com.example.model/module-info.java:**

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.inspector;
}
~~~

**exports** cho phép module inspector gọi factory public. **opens** cấp quyền deep reflection vào package nội bộ cho đúng module inspector.

**Tệp src/com.example.model/com/example/model/api/CustomerFactory.java:**

~~~java
package com.example.model.api;

import com.example.model.internal.CustomerRecord;

public final class CustomerFactory {
    private CustomerFactory() {
    }

    public static Object create(String email) {
        return new CustomerRecord(email);
    }
}
~~~

Factory trả về **Object** để module inspector không cần import kiểu nội bộ. API public vẫn có thể tạo đối tượng nội bộ và chuyển nó qua ranh giới module.

**Tệp src/com.example.model/com/example/model/internal/CustomerRecord.java:**

~~~java
package com.example.model.internal;

public final class CustomerRecord {
    private final String email;

    public CustomerRecord(String email) {
        this.email = email;
    }
}
~~~

Field **email** là private. Package **com.example.model.internal** không được export; module inspector chỉ có quyền deep reflection vì có qualified opens.

**Tệp src/com.example.inspector/module-info.java:**

~~~java
module com.example.inspector {
    requires com.example.model;
}
~~~

**Tệp src/com.example.inspector/com/example/inspector/Main.java:**

~~~java
package com.example.inspector;

import com.example.model.api.CustomerFactory;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Object customer = CustomerFactory.create("customer@example.test");
        Field email = customer.getClass().getDeclaredField("email");

        if (!email.trySetAccessible()) {
            throw new IllegalStateException("Package is not open to this module");
        }

        System.out.println("Private email: " + email.get(customer));
    }
}
~~~

Biên dịch hai module bằng JDK 17 trở lên, từ thư mục gốc chứa thư mục **src**:

~~~bash
mkdir out
javac --release 17 --module-source-path src -d out -m com.example.model,com.example.inspector
java --module-path out -m com.example.inspector/com.example.inspector.Main
~~~

Kết quả chính xác:

~~~text
Private email: customer@example.test
~~~

Kết quả cho thấy module inspector đọc được field private vì package nội bộ đã được mở cho đúng module. Nếu bỏ directive **opens com.example.model.internal to com.example.inspector;**, **trySetAccessible()** không thể bật quyền deep reflection và ví dụ sẽ dừng ở thông báo package chưa được mở.

Trong ứng dụng thực tế, không nên trả về **Object** chỉ để dùng reflection nếu API có thể cung cấp phương thức nghiệp vụ phù hợp. Ví dụ này cố ý dùng Object để minh họa một tình huống framework nhận instance qua API public nhưng cần đọc metadata hoặc field của implementation nội bộ.

## 8. Strong encapsulation trong JDK hiện đại

JPMS được giới thiệu ở Java 9. Qua các phiên bản sau, JDK tăng cường việc đóng gói các package nội bộ. Từ Java 17, strong encapsulation của các internal API trong JDK được áp dụng mặc định theo JEP 403.

Điều đó có nghĩa là ứng dụng không nên phụ thuộc vào truy cập reflection sâu vào implementation của JDK như một giao kèo ổn định. Một thư viện cũ có thể từng truy cập field private trong **java.base** và chỉ phát cảnh báo ở runtime Java cũ; khi chạy trên JDK hiện đại, thao tác đó có thể bị chặn.

Khi gặp lỗi **InaccessibleObjectException**, xử lý theo thứ tự:

1. Xác định class, package và module nguồn được nêu trong stack trace.
2. Xác định module thực hiện reflection, hoặc xem thư viện đang chạy trong unnamed module.
3. Kiểm tra framework đã có phiên bản hỗ trợ JDK mục tiêu hay chưa.
4. Tìm API public được hỗ trợ để thay thế việc truy cập internal implementation.
5. Nếu chưa thể bỏ truy cập sâu, thêm một **opens** có phạm vi nhỏ hoặc một **--add-opens** tạm thời cho đúng module và package.
6. Ghi lại lý do và điều kiện loại bỏ cấu hình tương thích; kiểm thử lại khi nâng cấp JDK hoặc framework.

Tùy chọn **--illegal-access** từng được dùng trong giai đoạn chuyển tiếp đầu của JPMS đã bị loại bỏ từ Java 17. Không dùng nó làm giải pháp cho ứng dụng mới. Nếu cần một quyền mở rõ ràng ở runtime, **--add-opens** là tùy chọn tương ứng; nếu có thể sửa module descriptor, khai báo **opens** trong **module-info.java**.

## 9. Lưu ý thiết kế và vận hành

- **Mở đúng package:** **opens** áp dụng theo package. Package con không tự được mở theo package cha.
- **Giới hạn module nhận quyền:** qualified opens giảm phạm vi truy cập so với mở package cho mọi module.
- **Không nhầm với exports:** mở reflection không công bố API public để module khác import khi biên dịch.
- **Không nhầm với open module:** open module mở mọi package cho reflection; chỉ dùng khi tất cả package đều cần quyền này.
- **Ưu tiên API public:** nếu một framework có thể hoạt động qua constructor, getter, setter hoặc API mở rộng chính thức, hãy cân nhắc cách đó trước khi cấp quyền deep reflection.
- **Theo dõi dependency:** framework ORM, serializer, dependency injection hoặc công cụ kiểm thử có thể cần mở package để ánh xạ hoặc tạo instance. Xác định module thực sự thực hiện reflection trước khi thêm directive.
- **Kiểm tra tên module runtime:** tên module thực tế có thể khác tên artifact Maven/Gradle. Dùng module descriptor hoặc công cụ **jar --describe-module** để xác nhận khi cần.
- **Đánh giá cấu hình theo môi trường:** tham số JVM trong IDE, test runner, container và production có thể khác nhau. Đảm bảo cấu hình **--add-opens** được truyền tới đúng JVM process.
- **Không mở package JDK tùy tiện:** truy cập internal API có thể hỏng khi JDK cập nhật. Chuyển sang API được hỗ trợ khi có thể.
- **Kiểm thử quyền truy cập:** có test xác nhận framework đọc được thành viên cần thiết và test xác nhận package khác vẫn đóng nếu kiến trúc yêu cầu giới hạn quyền.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **trySetAccessible()** trả về false | Package không mở cho module thực hiện reflection | Thêm qualified opens đúng package và module nhận quyền, hoặc dùng API public |
| **setAccessible(true)** ném **InaccessibleObjectException** | JPMS chặn việc bỏ qua access check | Kiểm tra module nguồn, package, module đích; chỉ thêm **--add-opens** khi thật sự cần |
| Đã thêm **opens** nhưng vẫn lỗi | Mở nhầm package hoặc nhầm module nhận quyền | Kiểm tra package của class đích và module chứa code reflection |
| Mã Java không import được class trong package đã mở | Nhầm **opens** với **exports** | Thêm **exports** nếu cần truy cập API public khi biên dịch |
| Framework chạy trong classpath vẫn bị chặn | Framework thuộc unnamed module nhưng directive qualified opens chỉ nêu một named module | Cân nhắc **--add-opens=module/package=ALL-UNNAMED** trong cấu hình JVM |
| Package con vẫn không truy cập sâu được | **opens** không áp dụng đệ quy cho package con | Mở riêng từng package cần thiết |
| Ứng dụng phụ thuộc vào **--illegal-access** | Dùng cấu hình chuyển tiếp đã bị loại bỏ từ Java 17 | Nâng cấp framework và thay bằng API được hỗ trợ hoặc **--add-opens** có phạm vi nhỏ |
| Tất cả package bị mở dù chỉ cần một package | Dùng **open module** quá rộng | Chuyển sang qualified opens cho package cần thiết |

## 11. Checklist trước khi khai báo opens

- [ ] Đã xác định class và package thực sự cần deep reflection.
- [ ] Đã xác định module nguồn sở hữu package.
- [ ] Đã xác định module thực hiện reflection tại runtime.
- [ ] Đã cân nhắc API public hoặc cách tích hợp không cần truy cập private.
- [ ] Đã chọn **opens** không qualified, qualified opens hoặc **open module** theo phạm vi tối thiểu cần thiết.
- [ ] Không dùng **opens** để thay thế **exports** khi cần import API public.
- [ ] Nếu dùng **--add-opens**, đã đặt tham số trên đúng JVM process và ghi lại lý do.
- [ ] Không dựa vào **--illegal-access** hoặc truy cập internal API cũ.
- [ ] Ví dụ và integration test chạy trên JDK mục tiêu.
- [ ] Đã xác nhận các package khác vẫn đóng nếu yêu cầu kiến trúc cần giới hạn quyền.

## 12. Tài liệu tham khảo

- [Java Language Specification — Module Declarations, §7.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Java Language Specification — Module Imports and Exports, §7.7.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
- [Java SE API — java.lang.Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html)
- [Java SE API — AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
