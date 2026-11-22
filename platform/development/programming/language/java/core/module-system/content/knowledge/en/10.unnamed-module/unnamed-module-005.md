# Reflection và unnamed module

Trong Java Platform Module System (JPMS), class được nạp từ **classpath** thuộc unnamed module của class loader tương ứng. Unnamed module có một số quy tắc mở và đọc module đặc biệt để duy trì khả năng tương thích với ứng dụng Java truyền thống. Những quy tắc này ảnh hưởng trực tiếp đến reflection, đặc biệt khi ứng dụng kết hợp named module với thư viện hoặc framework vẫn chạy trên classpath.

Cần phân biệt hai hướng truy cập:

- Code trong named module dùng reflection để kiểm tra class được nạp từ classpath.
- Framework được nạp từ classpath dùng reflection để truy cập class trong named module.

Hai trường hợp có hướng truy cập khác nhau và quyền được cấp cũng khác nhau.

## 1. Unnamed module là gì?

Khi class được nạp từ classpath, Java đặt class đó vào unnamed module gắn với class loader đã định nghĩa class. Mỗi class loader có unnamed module riêng; vì vậy không nên hiểu rằng toàn bộ classpath của mọi class loader trong JVM luôn thuộc một unnamed module duy nhất.

Unnamed module không có tên module để khai báo trong **requires** và không có file **module-info.java**. Nó được duy trì để các ứng dụng và thư viện chưa modular hóa tiếp tục hoạt động.

Các đặc điểm quan trọng:

- Unnamed module đọc tất cả module khác trong cấu hình module.
- Tất cả package của unnamed module được export.
- Tất cả package của unnamed module cũng được open cho deep reflection.
- Named module không tự động đọc unnamed module.
- Không thể viết một directive **requires** trỏ tới unnamed module vì nó không có tên.

Vì vậy, classpath vẫn có thể cùng tồn tại với module path. Tuy nhiên, khi code trong named module cần tham chiếu trực tiếp tới kiểu nằm trên classpath, quan hệ đọc phải được xử lý riêng.

## 2. Vì sao unnamed module được mở cho reflection?

Các ứng dụng Java trước JPMS thường dựa vào reflection để làm việc với thư viện, framework và class được nạp động. Nếu classpath bị áp dụng ranh giới đóng gói nghiêm ngặt như named module ngay lập tức, nhiều framework cũ có thể ngừng hoạt động.

Do đó, unnamed module có các package được export và open. Điều này cho phép code từ module khác truy cập API public và thực hiện deep reflection vào class trong unnamed module, miễn là class đã được nạp và các điều kiện truy cập khác được đáp ứng.

Ví dụ class nằm trên classpath:

~~~java
package com.example.legacy;

public class LegacyRecord {
    private String secret = "legacy-value";
}
~~~

Code trong named module có thể tìm class bằng tên và dùng reflection:

~~~java
Class<?> type = Class.forName("com.example.legacy.LegacyRecord");
Object record = type.getDeclaredConstructor().newInstance();

var field = type.getDeclaredField("secret");
field.setAccessible(true);

System.out.println(field.get(record));
~~~

Trong ví dụ này, class đích thuộc unnamed module. Package của unnamed module được open, nên JPMS không chặn deep reflection chỉ vì package đó không có directive **opens** trong module descriptor.

Tuy nhiên, reflection vẫn phụ thuộc vào việc class có thể được class loader tìm thấy, constructor có thể tạo instance và các quy tắc truy cập Java khác. Unnamed module được open không có nghĩa mọi class hoặc thành viên đều tự động public.

## 3. Named module không tự động đọc unnamed module

Chiều ngược lại có một quy tắc quan trọng: named module không tự động đọc unnamed module. Nếu source của named module tham chiếu trực tiếp tới class trên classpath, compiler có thể báo package không được đọc hoặc không thể truy cập.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
}
~~~

Code muốn dùng một class trên classpath:

~~~java
package com.example.app;

import com.example.legacy.LegacyRecord;

public class Main {
    public static void main(String[] args) {
        LegacyRecord record = new LegacyRecord();
        System.out.println(record);
    }
}
~~~

JAR chứa **LegacyRecord** có thể đã được đưa vào classpath, nhưng named module vẫn không tự động có cạnh đọc tới unnamed module. Có thể bổ sung cạnh đọc tạm thời bằng **--add-reads**:

~~~bash
javac --module-path mods \
      --class-path libs/legacy.jar \
      --add-reads com.example.app=ALL-UNNAMED \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Khi chạy, cũng cần cấu hình cạnh đọc tương ứng:

~~~bash
java --module-path out \
     --class-path libs/legacy.jar \
     --add-reads com.example.app=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

**ALL-UNNAMED** là tên đích đặc biệt dành cho tùy chọn launcher. Nó đại diện cho các unnamed module trong môi trường chạy. Không thể dùng **ALL-UNNAMED** như tên module trong directive **requires** của **module-info.java**.

Nếu có thể, nên đưa thư viện cũ lên module path để Java nhận diện nó thành automatic module, rồi khai báo dependency bằng tên module ổn định. **--add-reads** phù hợp như một cầu nối có chủ đích trong quá trình chuyển đổi.

## 4. Framework trên classpath reflection vào named module

Một tình huống rất phổ biến là ứng dụng chính đã modular hóa, nhưng framework vẫn được nạp từ classpath. Khi đó framework thuộc unnamed module và có thể đọc các named module. Tuy nhiên, nếu framework cần truy cập private field, constructor hoặc method trong named module, package sở hữu class phải được mở cho framework.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Giả sử entity nằm trong package:

~~~java
package com.example.app.model;

public class Customer {
    private String email;
}
~~~

Framework ORM trên classpath muốn truy cập field **email** bằng reflection. Package **com.example.app.model** chưa được mở, nên deep reflection có thể bị chặn.

Có thể mở package ở runtime cho tất cả unnamed module bằng:

~~~bash
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

Tùy chọn này có nghĩa:

- **com.example.app** là module sở hữu package.
- **com.example.app.model** là package cần mở.
- **ALL-UNNAMED** là các unnamed module, nơi framework trên classpath được nạp.

Một điểm cần nhớ: unnamed module đọc được named module không có nghĩa named module đã mở mọi package cho framework. Khả năng đọc module và quyền deep reflection là hai vấn đề riêng.

## 5. opens trong module-info.java và ALL-UNNAMED

Trong **module-info.java**, có thể mở package cho một named module cụ thể:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.model to com.example.orm;
}
~~~

Cách này phù hợp khi framework ORM cũng là một named module có tên **com.example.orm**.

Nếu framework nằm trên classpath, nó thuộc unnamed module và không có tên để đưa vào danh sách module đích trong directive **opens ... to ...**. Vì vậy, không viết **ALL-UNNAMED** trong module descriptor. Thay vào đó, có thể dùng tùy chọn launcher:

~~~bash
--add-opens com.example.app/com.example.app.model=ALL-UNNAMED
~~~

Hoặc mở package không giới hạn module đích:

~~~java
module com.example.app {
    opens com.example.app.model;
}
~~~

Directive **opens package;** mở package đó cho mọi module ở runtime. Nếu mục tiêu là chỉ cho framework trên classpath truy cập, **--add-opens ...=ALL-UNNAMED** thể hiện phạm vi hẹp hơn so với mở package cho mọi module.

Không nên đổi toàn bộ module thành **open module** chỉ để hỗ trợ một framework classpath. Cách đó mở mọi package trong module cho reflection sâu và rộng hơn nhu cầu thông thường.

## 6. Phân biệt --add-reads và --add-opens

Hai tùy chọn thường xuất hiện cùng nhau khi tích hợp code modular với thư viện cũ, nhưng chúng cấp quyền khác nhau.

| Tùy chọn | Cấp quyền gì? | Trường hợp điển hình |
|---|---|---|
| **--add-reads** | Bổ sung cạnh đọc giữa hai module | Named module cần đọc kiểu trong unnamed module |
| **--add-opens** | Mở package của module nguồn cho deep reflection từ module đích | Framework trên classpath cần truy cập private member trong named module |

Ví dụ bổ sung cả hai trong một lệnh:

~~~bash
java --module-path mods \
     --class-path libs/legacy.jar \
     --add-reads com.example.app=ALL-UNNAMED \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

Ở đây, **--add-reads** cho phép module ứng dụng đọc unnamed module. **--add-opens** cho phép unnamed module reflection sâu vào package model của module ứng dụng.

Không nên dùng một tùy chọn thay cho tùy chọn còn lại. Mở package không tự tạo cạnh đọc cho code cần tham chiếu kiểu; thêm cạnh đọc cũng không tự cho phép reflection sâu vào private member của package đóng.

## 7. Reflection vào classpath và reflection vào named module

Hai hướng truy cập có thể được so sánh như sau:

| Hướng reflection | Module đích | Quy tắc chính |
|---|---|---|
| Named module reflection vào classpath class | Unnamed module | Package của unnamed module đã open |
| Framework classpath reflection vào named-module class | Named module | Package đích phải open cho unnamed module nếu cần deep reflection |
| Named module gọi trực tiếp kiểu classpath | Unnamed module | Named module cần cạnh đọc, ví dụ --add-reads |
| Framework classpath gọi API public của named module | Named module | Package API cần export phù hợp; unnamed module đọc các named module |

Bảng này giúp tránh nhầm lẫn rằng vì unnamed module được open nên mọi package trong named module cũng tự động mở. Quyền mở của unnamed module chỉ áp dụng cho package thuộc unnamed module đó.

## 8. Ví dụ hoàn chỉnh: framework trên classpath truy cập entity

Giả sử module ứng dụng có cấu trúc:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        ├── Main.java
        └── model/Customer.java

libs/
└── legacy-orm.jar
~~~

Module descriptor:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Entity:

~~~java
package com.example.app.model;

public class Customer {
    private String email = "customer@example.com";
}
~~~

Framework trên classpath dùng reflection để đọc field:

~~~java
package com.example.orm;

import java.lang.reflect.Field;

public class EntityInspector {
    public static Object readField(Object entity, String fieldName)
            throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(entity);
    }
}
~~~

Vì framework thuộc unnamed module, package model trong named module cần được mở cho nó. Có thể cấu hình:

~~~bash
java --module-path mods \
     --class-path libs/legacy-orm.jar \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

Nếu bỏ **--add-opens**, thao tác reflection sâu vào field private có thể thất bại với **InaccessibleObjectException**. Khi thêm đúng tùy chọn, quyền được cấp cho unnamed module mà framework thuộc về, trong phạm vi package model.

Nếu framework được chuyển sang named module, có thể thay **ALL-UNNAMED** bằng module name cụ thể và chuyển directive vào **module-info.java**:

~~~java
module com.example.app {
    opens com.example.app.model to com.example.orm;
}
~~~

Đây là cách thể hiện quyền tích hợp rõ ràng hơn khi cả hai phía đều có module descriptor.

## 9. Lưu ý khi dùng framework và test trên classpath

Các framework như ORM, JSON mapper, dependency injection hoặc test framework có thể dùng reflection theo nhiều cách. Không phải mọi thao tác reflection đều cần opens. Truy cập public API đã export thường không cần deep reflection.

Khi cấu hình môi trường chạy:

- Xác định framework đang thuộc named module hay unnamed module.
- Xác định package của ứng dụng mà framework thực sự cần truy cập sâu.
- Dùng qualified opens cho named module đích nếu framework đã modular hóa.
- Dùng **--add-opens package=ALL-UNNAMED** khi framework thuộc classpath.
- Đặt tùy chọn vào đúng JVM process chạy ứng dụng hoặc test; cấu hình cho compiler không tự động áp dụng cho tiến trình test/runtime.
- Sau khi nâng cấp framework hoặc chuyển framework sang module path, xem lại các tùy chọn mở package cũ và loại bỏ những tùy chọn không còn cần thiết.

Đối với Gradle hoặc Maven, các tùy chọn JVM cần được truyền vào forked test JVM hoặc application run task tương ứng. Chỉ đặt tùy chọn ở terminal chạy một tiến trình khác không làm thay đổi JVM đang chạy test.

## 10. Lỗi thường gặp

**InaccessibleObjectException khi framework truy cập private field**

Kiểm tra package của class thuộc named module nào. Nếu framework thuộc unnamed module, mở đúng package cho **ALL-UNNAMED** bằng **--add-opens**.

**Đã dùng --add-reads nhưng reflection vẫn thất bại**

Add-reads chỉ bổ sung quan hệ đọc. Nếu framework cần deep reflection vào package của named module, cần opens hoặc --add-opens riêng.

**Đã dùng --add-opens nhưng code named module vẫn không import được class trên classpath**

Add-opens chỉ cấp quyền reflection. Named module cần cạnh đọc tới unnamed module nếu source tham chiếu trực tiếp tới kiểu classpath, ví dụ bằng **--add-reads**.

**Mở package trong module-info.java cho ALL-UNNAMED không biên dịch**

**ALL-UNNAMED** là ký hiệu đặc biệt của tùy chọn launcher, không phải tên module hợp lệ trong directive opens của module descriptor. Dùng **--add-opens** ở runtime hoặc mở package cho một named module có tên cụ thể.

**Framework vẫn bị chặn dù module đã có opens**

Kiểm tra package và module đích có chính xác không. Framework có thể được nạp từ classpath trong unnamed module khác, hoặc lỗi đến từ một package khác mà framework cũng cần xử lý.

**Đã mở toàn bộ module nhưng vẫn không import được package**

Open module chỉ mở package cho reflection sâu, không export mọi package cho truy cập thông thường. Cần thêm exports phù hợp nếu module khác phải dùng API public.

## 11. Ghi nhớ

- Mỗi class loader có unnamed module riêng cho các class do nó định nghĩa trong unnamed module.
- Unnamed module đọc mọi module và tất cả package của nó được export, open.
- Named module không tự động đọc unnamed module; code tham chiếu trực tiếp tới classpath có thể cần **--add-reads**.
- Framework trên classpath có thể đọc named module, nhưng deep reflection vào package của named module cần package được mở cho unnamed module.
- **--add-opens module/package=ALL-UNNAMED** mở package cụ thể cho các unnamed module.
- Không thể ghi **ALL-UNNAMED** làm module đích trong directive opens của **module-info.java**.
- **--add-reads** và **--add-opens** giải quyết hai loại quyền khác nhau.
- Nên mở package model cần thiết cho framework, giữ các package khác đóng gói và tránh open module toàn bộ nếu không có yêu cầu rõ ràng.

Khi tích hợp framework classpath vào ứng dụng modular, hãy xác định chiều reflection trước. Nếu code modular reflection vào classpath, package đích đã được open theo quy tắc unnamed module. Nếu framework classpath reflection vào named module, module sở hữu class phải mở package cụ thể cho **ALL-UNNAMED**. Cách phân biệt này giúp cấu hình JPMS đúng phạm vi và giữ ranh giới module có chủ đích.
