# InaccessibleObjectException khi reflection sâu

## 1. InaccessibleObjectException là gì?

**InaccessibleObjectException** là unchecked exception trong Java Reflection, xuất hiện khi chương trình cố gắng mở quyền truy cập sâu vào một thành viên mà JPMS không cho phép truy cập. Lỗi thường gặp khi framework gọi **setAccessible(true)** trên field, method hoặc constructor private thuộc một package của named module chưa được mở cho module gọi.

Từ Java 9, Java Platform Module System (JPMS) bổ sung ranh giới đóng gói giữa các module. Một package có thể tồn tại và class có thể được nạp, nhưng điều đó không có nghĩa module khác được phép truy cập mọi thành viên bên trong package.

Ví dụ, một framework có thể tìm thấy class entity và đọc metadata của nó, nhưng khi cố gắng truy cập field private để ánh xạ dữ liệu, JVM từ chối thao tác. Khi đó, việc tìm thấy class không đồng nghĩa với việc reflection sâu được cho phép.

Thông báo lỗi thường có dạng:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module ... does not "opens ..." to ...
~~~

Phần thông báo nêu module sở hữu package, package bị chặn và module đang yêu cầu quyền truy cập. Đây là thông tin quan trọng để xác định cần mở package nào và mở cho ai.

## 2. Vì sao JPMS chặn reflection sâu?

Trước JPMS, nhiều thư viện thường dựa vào reflection để truy cập field private, constructor hoặc method nội bộ. Một số framework dùng cách này cho dependency injection, ORM, serialization, proxy hoặc mapping.

JPMS bổ sung hai khái niệm đóng gói quan trọng:

- **exports** cho phép module khác truy cập các kiểu public trong một package.
- **opens** cho phép module khác dùng reflection sâu vào các thành viên trong package, kể cả thành viên không public.

Vì vậy, khai báo **exports** không tự động cho phép framework gọi **setAccessible(true)** lên field private. Nếu framework cần truy cập sâu, package phải được mở bằng **opens** hoặc bằng tùy chọn runtime phù hợp.

JDK cũng áp dụng strong encapsulation cho các package nội bộ. Những package như **sun.* ** hoặc các package nội bộ khác không phải API công khai được bảo đảm tương thích. Một framework cũ có thể hoạt động trên JDK trước đây nhưng phát sinh lỗi khi chạy trên JDK mới vì nó dựa vào truy cập nội bộ.

Từ JDK 17, strong encapsulation được áp dụng mặc định đối với các package nội bộ của JDK. Tùy chọn cũ **--illegal-access** không còn là cách để mở lại hàng loạt package nội bộ. Cần cập nhật thư viện hoặc mở đúng package nếu có lý do triển khai cụ thể.

## 3. Phân biệt tìm class, truy cập public và reflection sâu

Khi điều tra lỗi reflection, hãy tách riêng ba bước:

1. **Discovery:** framework tìm class hoặc tài nguyên bằng package scan, annotation, ServiceLoader hoặc cấu hình.
2. **Loading:** classloader hoặc module layer nạp được class.
3. **Access:** framework được phép đọc hoặc thay đổi thành viên mà nó cần.

Ví dụ, một module có thể xuất package API để framework gọi phương thức public. Framework vẫn có thể không truy cập được field private trong cùng package nếu package chưa được mở cho nó.

### Truy cập public qua package đã export

Module chứa API:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Framework có thể sử dụng kiểu public trong package đã export nếu module framework đọc module model:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

Đây là truy cập API Java thông thường. Không cần mở package cho deep reflection nếu framework chỉ gọi các phương thức public được phép truy cập.

### Truy cập private bằng reflection

Giả sử class có field private:

~~~java
package com.example.model.api;

public class Customer {
    private String email = "customer@example.com";

    public String email() {
        return email;
    }
}
~~~

Framework muốn truy cập field private:

~~~java
Field field = Customer.class.getDeclaredField("email");
field.setAccessible(true);

String value = (String) field.get(customer);
~~~

Nếu package **com.example.model.api** chỉ được export mà không được mở cho module framework, lệnh **setAccessible(true)** có thể ném **InaccessibleObjectException**. Quyền truy cập public và quyền reflection sâu là hai quyền khác nhau.

## 4. Đọc đúng nội dung lỗi

Một thông báo điển hình:

~~~text
Unable to make field private ... accessible:
module com.example.model does not "opens com.example.model.api"
to module com.example.framework
~~~

Có thể đọc thông báo theo các phần:

- **com.example.model** là module sở hữu class và package.
- **com.example.model.api** là package đang bị truy cập sâu.
- **com.example.framework** là module gọi reflection và cần được cấp quyền.
- Từ khóa **opens** cho biết thao tác cần quyền deep reflection.

Nếu thông báo nói package không được mở cho **ALL-UNNAMED**, caller đang thuộc unnamed module, thường là thư viện chạy từ classpath. Nếu thông báo nêu tên module cụ thể, cần mở package cho đúng named module đó.

Không nên mở một package bất kỳ chỉ vì tên package xuất hiện trong stack trace. Hãy xác định class thực sự được truy cập và module caller được ghi trong thông báo.

## 5. Cách 1: Mở package trong module-info.java

Nếu bạn sở hữu module chứa class cần reflection, có thể khai báo **opens** trong module descriptor.

Ví dụ:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.api
        to com.example.framework;
}
~~~

Khai báo này cho phép module **com.example.framework** truy cập sâu bằng reflection vào package **com.example.model.api**. Module khác không được hưởng quyền mở này.

Nếu framework cần reflection sâu vào một package riêng, nên mở đúng package đó:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.internal
        to com.example.framework;
}
~~~

Trong ví dụ này, API công khai nằm ở package **com.example.model.api**, còn package implementation **com.example.model.internal** được mở có mục tiêu cho framework.

Có thể mở package không chỉ định module đích:

~~~java
module com.example.model {
    opens com.example.model.internal;
}
~~~

Dạng này mở package cho mọi module có quyền truy cập sâu. Chỉ dùng khi phạm vi đó thực sự cần thiết.

### open module

Có thể khai báo toàn module là open:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

Một **open module** mở tất cả package của module cho deep reflection. Cách này phù hợp khi framework cần truy cập nhiều package và việc mở toàn bộ đã được chấp nhận trong thiết kế. Với ứng dụng thông thường, mở có mục tiêu bằng **opens package to module** thường dễ kiểm soát hơn.

Không thể khai báo các chỉ thị **opens** riêng lẻ bên trong một **open module**; trạng thái mở đã áp dụng cho tất cả package.

## 6. Cách 2: Dùng --add-opens khi khởi chạy

Nếu không thể sửa module descriptor, hoặc muốn thử nghiệm một thay đổi trước khi đưa vào mã nguồn, có thể dùng tùy chọn **--add-opens** của Java launcher.

Cú pháp:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Ví dụ mở package của module ứng dụng cho framework:

~~~bash
java \
  --add-opens com.example.model/com.example.model.api=com.example.framework \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Trong đó:

- **com.example.model** là module sở hữu package.
- **com.example.model.api** là package cần mở.
- **com.example.framework** là module được phép deep reflection.

Nếu framework chạy từ classpath, caller thuộc unnamed module. Có thể mở package cho tất cả unnamed module bằng **ALL-UNNAMED**:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

Lệnh này minh họa việc mở package **java.lang** trong module **java.base** cho code chạy trong unnamed module. Nó thường xuất hiện khi thư viện cũ cần reflection sâu vào một số class JDK.

Nếu framework là named module, hãy chỉ định tên module cụ thể thay cho **ALL-UNNAMED**:

~~~bash
java \
  --add-opens java.base/java.lang=com.example.framework \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Có thể mở cho nhiều module đích bằng danh sách phân tách dấu phẩy:

~~~bash
java --add-opens com.example.model/com.example.model.api=com.example.framework,com.example.test
~~~

**--add-opens** là tùy chọn runtime của Java launcher. Đặt nó trong lệnh **javac** không giải quyết lỗi deep reflection khi ứng dụng chạy. Nếu ứng dụng khởi chạy qua script, service hoặc container, hãy thêm tùy chọn vào đúng cấu hình khởi chạy của process Java đó.

## 7. Phân biệt exports, opens, --add-exports và --add-opens

Bốn cơ chế này có mục đích khác nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| **exports package** | Module descriptor | Công khai kiểu public trong package cho module khác |
| **opens package** | Module descriptor | Cho phép deep reflection vào package |
| **--add-exports** | Tùy chọn dòng lệnh biên dịch/runtime | Bổ sung quyền truy cập các kiểu public trong package chưa export |
| **--add-opens** | Tùy chọn Java launcher lúc runtime | Mở package cho deep reflection trong process hiện tại |

Ví dụ, nếu mã nguồn cần import một kiểu public nằm trong package chưa export của module khác, **--add-exports** có thể giải quyết lỗi truy cập kiểu public:

~~~bash
javac \
  --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
  -cp "lib/*" \
  -d out \
  src/com/example/Main.java
~~~

Tuy nhiên, **--add-exports** không cho phép reflection sâu vào private field hoặc private method. Với trường hợp đó, cần **opens** hoặc **--add-opens**.

Ngược lại, **--add-opens** không làm package trở thành API public có thể import trong mã nguồn. Nó chỉ cấp quyền reflection sâu ở runtime.

Nếu lỗi xuất hiện khi biên dịch do module không đọc module khác, hãy xem **requires** hoặc **--add-reads**. Nếu lỗi do package chưa export, xem **exports** hoặc **--add-exports**. Nếu lỗi do truy cập private qua reflection, xem **opens** hoặc **--add-opens**.

## 8. trySetAccessible và cách xử lý trong code

Thay vì giả định reflection luôn thành công, framework có thể dùng **trySetAccessible()** để kiểm tra quyền truy cập:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Package is not open for deep reflection"
    );
}

String value = (String) field.get(customer);
~~~

Nếu module không mở package phù hợp, **trySetAccessible()** trả về **false**. Đây là cách xử lý có kiểm soát để framework đưa ra thông báo rõ ràng hoặc chuyển sang API public.

Nếu gọi trực tiếp:

~~~java
field.setAccessible(true);
~~~

JVM có thể ném **InaccessibleObjectException** khi không thể cho phép truy cập sâu. Nên bắt lỗi ở lớp tích hợp reflection nếu cần bổ sung thông tin về module, package và tùy chọn cấu hình.

**canAccess(target)** có thể dùng để kiểm tra trạng thái truy cập hiện tại. Với field hoặc method instance, truyền đối tượng đích; với thành viên static, truyền **null**.

Không nên bắt **InaccessibleObjectException** rồi âm thầm bỏ qua mọi field. Việc bỏ qua có thể làm mất dữ liệu, khiến mapping sai hoặc tạo ra lỗi khó phát hiện ở bước sau.

## 9. Vì sao lỗi thường xuất hiện trên JDK mới?

Một số thư viện được viết từ thời chưa có JPMS dựa vào cấu trúc nội bộ của JDK. Chúng có thể truy cập field private của class JDK, hoặc dùng package nội bộ để tối ưu.

Khi chạy trên JDK mới:

- Package nội bộ có thể bị đóng gói mạnh hơn.
- Reflection vào thành viên private có thể bị từ chối.
- Một API nội bộ trước đây dùng được có thể đã thay đổi hoặc bị loại bỏ.
- Tùy chọn tương thích cũ có thể không còn hiệu lực.

Từ JDK 17, không nên dựa vào **--illegal-access** để khôi phục hành vi truy cập nội bộ như trước. Cách xử lý bền vững là nâng cấp thư viện, chuyển sang API công khai hoặc chỉ mở package cần thiết nếu nhà cung cấp thư viện yêu cầu và việc đó được chấp nhận.

Có thể dùng jdeps để tìm một số tham chiếu bytecode tới API nội bộ:

~~~bash
jdeps --jdk-internals app.jar
~~~

Lệnh này hỗ trợ phát hiện tham chiếu tĩnh. Những tên class được tạo từ chuỗi cấu hình hoặc reflection động không nhất thiết được phát hiện, vì vậy vẫn cần xem stack trace và cấu hình framework.

## 10. Quy trình điều tra và sửa lỗi

Khi gặp **InaccessibleObjectException**, có thể thực hiện theo trình tự:

1. Đọc đầy đủ thông báo lỗi để xác định source module, package và caller module.
2. Xác định framework đang truy cập public API hay cần deep reflection vào private member.
3. Kiểm tra module descriptor của module chứa class và caller.
4. Nếu package thuộc module do dự án sở hữu, thêm **opens package to framework.module** đúng phạm vi.
5. Nếu chưa thể sửa descriptor, thử **--add-opens source.module/package=framework.module** trong lệnh khởi chạy.
6. Nếu caller thuộc classpath, dùng **ALL-UNNAMED** khi cần và giới hạn package được mở.
7. Nếu package thuộc JDK, tìm API công khai hoặc nâng cấp thư viện trước khi quyết định mở package JDK.
8. Chạy lại đúng process Java và kiểm thử các chức năng reflection liên quan.

Khi sửa xong, xác nhận rằng ứng dụng không chỉ khởi động được mà còn thực hiện thành công các thao tác thực sự cần reflection: tạo entity, inject dependency, serialize/deserialize, tạo proxy hoặc ánh xạ dữ liệu tùy trường hợp.

## 11. Các lỗi cấu hình thường gặp

**Mở nhầm module hoặc package**

Tên trong **--add-opens** phải là tên module và tên package thực tế. Package dùng dấu chấm, không phải đường dẫn thư mục. Module đích phải là module framework đang gọi reflection.

**Dùng ALL-UNNAMED cho framework dạng named module**

**ALL-UNNAMED** chỉ áp dụng cho unnamed module, thường là code trên classpath. Nếu framework nằm trong named module, hãy chỉ định tên module framework.

**Dùng exports để sửa lỗi private reflection**

**exports** cho phép truy cập kiểu public. Nó không cấp quyền truy cập sâu vào private field hoặc method. Hãy dùng **opens**.

**Thêm --add-opens vào javac**

Tùy chọn này thuộc Java launcher ở runtime. Nếu lỗi xảy ra khi ứng dụng chạy, hãy cấu hình process Java thực tế.

**Đã mở package nhưng vẫn lỗi**

Kiểm tra package có đúng là package khai báo trong lỗi hay không, caller module có đúng không, lệnh khởi chạy có thực sự nhận tùy chọn hay không và ứng dụng có đang chạy trong một module layer/process khác không.

**Mở toàn bộ JDK**

Mở rộng quyền cho nhiều package của JDK làm giảm tính đóng gói và tăng phụ thuộc vào implementation nội bộ. Hãy mở đúng package, đúng caller và chỉ khi không có giải pháp API công khai phù hợp.

## 12. Ghi nhớ

- **InaccessibleObjectException** thường báo rằng reflection sâu không được JPMS cho phép.
- **exports** cho phép truy cập kiểu public; **opens** cho phép deep reflection.
- **--add-opens** cấp quyền deep reflection khi khởi chạy process Java; nó không sửa module descriptor.
- **ALL-UNNAMED** dùng cho code thuộc unnamed module, thường là thư viện trên classpath.
- **trySetAccessible()** cho phép kiểm tra khả năng mở quyền trước khi thao tác.
- Strong encapsulation của JDK giúp bảo vệ implementation nội bộ; ưu tiên API công khai và thư viện đã hỗ trợ JPMS.
- Chỉ mở package thực sự cần thiết cho đúng module framework.

Khi hiểu rõ module sở hữu package, caller module và loại truy cập mà framework cần, có thể sửa lỗi reflection với phạm vi quyền nhỏ và dễ kiểm soát. Hãy xem **opens** hoặc **--add-opens** là cấu hình truy cập có chủ đích, đồng thời kiểm thử lại ứng dụng trên đúng phiên bản JDK triển khai.
