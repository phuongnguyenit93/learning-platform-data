# Package-private và private vẫn bị giới hạn trong Java Module System

## 1. Mục tiêu bài học

Khi học Java Platform Module System (JPMS), ta thường gặp các khai báo **requires**, **exports** và **opens** trong file **module-info.java**. Chúng kiểm soát quan hệ giữa các module, nhưng **không thay đổi quy tắc truy cập thành viên của ngôn ngữ Java**.

Sau bài này, bạn sẽ:

- Phân biệt quyền truy cập **public**, **protected**, **package-private** và **private** với quyền truy cập ở mức module.
- Giải thích tại sao một package đã **exports** vẫn không làm các thành viên package-private hay private có thể gọi trực tiếp từ module khác.
- Hiểu khác biệt giữa truy cập thông thường và truy cập qua **reflection** khi package có **opens**.
- Viết và chạy ví dụ hai named module để quan sát các trường hợp hợp lệ, lỗi biên dịch và lỗi truy cập runtime.
- Biết khi nào cần thiết kế public API, khi nào dùng **opens** có phạm vi, và vì sao không nên mở toàn bộ nội bộ module chỉ để né lỗi truy cập.

## 2. Hai lớp kiểm soát truy cập khác nhau

Java có ít nhất hai câu hỏi độc lập khi một đoạn code muốn sử dụng một class hoặc thành viên:

1. **Ở mức module:** Module của code gọi có **đọc** được module chứa class đó không? Package chứa class có được **export** tới module gọi không?
2. **Ở mức Java language:** Bản thân class và thành viên có modifier phù hợp với vị trí gọi hay không, ví dụ **public**, **protected**, **package-private**, **private**?

Với truy cập Java thông thường từ một module khác, **cả hai lớp điều kiện đều phải hợp lệ**.

~~~text
Module com.example.app
        |
        | requires com.example.library
        v
Module com.example.library
        |
        | exports com.example.library.api
        v
public class User
        |
        +-- public String getName()       --> gọi được qua public API
        +-- String internalNote()         --> package-private: không gọi được
        +-- private String secret()        --> private: không gọi được
~~~

Vì vậy, **exports một package không tương đương với chuyển mọi class và member trong package thành public**. JPMS kiểm soát việc package nào được cung cấp cho module khác; modifier Java vẫn quyết định ai có thể truy cập class/member.

## 3. Nhắc lại bốn mức truy cập của Java

| Modifier của thành viên | Bên trong class khai báo | Code cùng package | Code ở package khác |
| --- | --- | --- | --- |
| **public** | Có | Có | Có, nếu class/package cũng truy cập được |
| **protected** | Có | Có | Chủ yếu thông qua kế thừa, theo quy tắc protected |
| **package-private** (không ghi modifier) | Có | Có | Không |
| **private** | Có | Không, trừ các ngoại lệ như nestmates | Không |

Lưu ý quan trọng:

- **Package-private** không phải từ khóa Java; đó là mức truy cập mặc định khi không ghi **public/protected/private**.
- **Private** giới hạn truy cập vào class hoặc **nest** tương ứng; từ Java 11, các class là **nestmates** có thể truy cập private member của nhau theo quy tắc Java. Đây không phải quyền được JPMS cấp.
- Class top-level chỉ có thể là **public** hoặc **package-private**; protected và private không áp dụng trực tiếp cho class top-level.
- Với **protected** ở package khác, subclass phải tuân thủ cả quy tắc kiểu của biểu thức truy cập; không phải cứ kế thừa là được gọi trên mọi đối tượng cùng superclass.
- Có quyền nhìn thấy một **public class** không đồng nghĩa với quyền đọc trường private hoặc gọi phương thức package-private của class đó.

Nếu hai module có cùng tên package, cũng không được giả định rằng điều đó tạo quyền package-private giữa chúng. Trong môi trường modular, quan hệ module và runtime package/class loader có ràng buộc riêng; hãy coi **module API** là ranh giới trao đổi, tránh thiết kế dựa trên việc chia sẻ package name giữa các module.

## 4. exports: công khai package chứa public API

Ví dụ module cung cấp thư viện:

~~~java
// src/com.example.library/module-info.java
module com.example.library {
    exports com.example.library.api;
}
~~~

Class trong package được export:

~~~java
// src/com.example.library/com/example/library/api/User.java
package com.example.library.api;

public class User {
    private final String token = "demo-token";

    public String getName() {
        return "An";
    }

    String internalNote() { // package-private
        return "Chỉ dùng trong package";
    }

    private String secretNote() {
        return "Nội bộ class User";
    }
}
~~~

Module tiêu thụ:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.library;
}
~~~

Trong module **com.example.app**, đoạn sau hợp lệ:

~~~java
import com.example.library.api.User;

User user = new User();
System.out.println(user.getName()); // Hợp lệ: public API
~~~

Nhưng các câu lệnh sau **không biên dịch**:

~~~java
user.internalNote(); // Không hợp lệ: package-private
user.secretNote();   // Không hợp lệ: private
System.out.println(user.token); // Không hợp lệ: private
~~~

Lý do:

- **requires com.example.library** cho phép module app **đọc** module library.
- **exports com.example.library.api** cho phép module app truy cập các **public types** trong package ấy.
- **User** là public; **getName()** cũng public, nên được gọi.
- **internalNote()** là package-private; code trong package **com.example.app** không thuộc package khai báo phương thức.
- **secretNote()** và **token** là private; **exports** không làm thay đổi modifier.

Đây là phân biệt cốt lõi của bài: **JPMS thêm điều kiện truy cập**, không xóa điều kiện vốn có của Java.

### 4.1. Khi package không được export

Nếu đổi module library thành:

~~~java
module com.example.library {
    // Không exports com.example.library.api
}
~~~

thì ngay cả việc import **User** từ module app cũng bị từ chối ở compile time vì package không được export tới module app. Chỉ cần class **User** public là chưa đủ.

### 4.2. Qualified exports không giúp gọi private

Một module có thể chỉ export package cho một số module nhất định:

~~~java
module com.example.library {
    exports com.example.library.api to com.example.app;
}
~~~

Module **com.example.app** vẫn chỉ dùng được các public API mà ngôn ngữ Java cho phép. Cách export có chọn lọc này **không cấp thêm** quyền vào package-private hoặc private member.

## 5. Package-private vẫn dùng được bên trong package

Giả sử cùng package **com.example.library.api**, ta thêm:

~~~java
// src/com.example.library/com/example/library/api/SamePackageDemo.java
package com.example.library.api;

public final class SamePackageDemo {
    private SamePackageDemo() {}

    public static String readInternalNote(User user) {
        // Hợp lệ: SamePackageDemo và User cùng package.
        return user.internalNote();
    }

    // Không hợp lệ:
    // return user.secretNote();
    // return user.token;
}
~~~

**SamePackageDemo** có thể gọi **internalNote()**, vì nó cùng package với **User**. Nếu muốn module app nhận kết quả, thư viện có thể chủ động cung cấp một public API như **SamePackageDemo.readInternalNote(User)**.

Điều này **không làm internalNote trở thành public**; thư viện đang cố ý đưa một thao tác an toàn qua bề mặt API công khai.

Ví dụ này cũng cho thấy sự khác biệt giữa:

- **Quyền của code nội bộ package**: có thể truy cập package-private member.
- **Quyền của module khác thông qua exports**: chỉ truy cập những API được Java cho phép và nằm trong package được export.

Package-private là công cụ hữu ích để chia sẻ helper, factory hoặc logic triển khai trong một package mà không mở rộng public API.

## 6. opens cho reflection: không phải quyền truy cập Java thông thường

**opens** phục vụ **deep reflection**, ví dụ framework ORM, serialization hoặc dependency injection cần truy cập một field/constructor/method không public thông qua API phản chiếu.

Ví dụ:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.app;
}
~~~

Hai dòng đảm nhiệm hai nhiệm vụ khác nhau:

- **exports** cho phép code trong app tham chiếu trực tiếp đến **User** và gọi các phương thức public.
- **opens ... to com.example.app** cho phép code trong app thực hiện deep reflection với package đó, chẳng hạn **Field.setAccessible(true)** rồi đọc field private.

**opens không khiến user.internalNote() hoặc user.secretNote() biên dịch được.** Java compiler vẫn áp dụng modifier như cũ.

### 6.1. Reflection có hai bước

Quan sát reflection:

~~~java
import com.example.library.api.User;
import java.lang.reflect.Field;

User user = new User();
Field field = User.class.getDeclaredField("token");
field.setAccessible(true);       // Cố gắng bật deep reflective access
Object value = field.get(user);  // Đọc trường đã được cho phép
System.out.println(value);
~~~

Với **opens com.example.library.api to com.example.app**, đoạn trên có thể chạy thành công từ module app.

Nếu bỏ **opens**, lời gọi **setAccessible(true)** có thể ném **java.lang.reflect.InaccessibleObjectException** vì package chứa field không mở cho module của caller. **getDeclaredField** có thể tìm được metadata về member nhưng bước tìm metadata không tự cấp quyền dùng member.

Trong các trường hợp API cho phép, **trySetAccessible()** có thể được dùng để kiểm tra và nhận **false** thay vì kỳ vọng mọi lời gọi **setAccessible(true)** luôn thành công:

~~~java
Field field = User.class.getDeclaredField("token");
if (field.trySetAccessible()) {
    System.out.println(field.get(user));
} else {
    System.out.println("Không được phép truy cập sâu bằng reflection");
}
~~~

Không nên coi reflective access là con đường mặc định để dùng private API. Nó làm code phụ thuộc vào chi tiết cài đặt, dễ hỏng khi đổi tên trường hoặc nâng cấp thư viện.

### 6.2. exports không thay thế opens và ngược lại

| Khai báo trong module library | App import User và gọi getName() | App gọi trực tiếp internalNote()/secretNote() | Deep reflection vào private field |
| --- | --- | --- | --- |
| **exports api;** | Có | Không | Thường bị chặn khi caller ở module khác |
| **opens api to app;** | Không, nếu không có exports phù hợp | Không | Có thể, khi caller là module app được mở |
| **exports api; opens api to app;** | Có | Không | Có thể, khi caller là module app được mở |
| Không exports, không opens | Không | Không | Thường bị chặn |

Trong bảng, **api** là viết tắt của package **com.example.library.api** và **app** là module **com.example.app**.

Đối với reflection vào public member của public class thuộc exported package, quy tắc có thể cho phép truy cập mà không cần **opens**. **opens** trở nên quan trọng khi code cần bỏ qua kiểm tra truy cập Java thông thường cho các member hoặc class không public.

## 7. Thực hành hoàn chỉnh với hai named module

Ví dụ dưới đây kết hợp **exports**, **opens**, package-private và private trong một chương trình chạy được.

### 7.1. Cấu trúc thư mục

~~~text
src/
  com.example.library/
    module-info.java
    com/example/library/api/
      User.java
      SamePackageDemo.java
  com.example.app/
    module-info.java
    com/example/app/
      Main.java
~~~

**src/com.example.library/module-info.java**:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.app;
}
~~~

**src/com.example.library/com/example/library/api/User.java**:

~~~java
package com.example.library.api;

public final class User {
    private final String token = "demo-token";

    public String getName() {
        return "An";
    }

    String internalNote() {
        return "package-private OK trong package";
    }

    private String secretNote() {
        return "private chỉ thuộc logic của User";
    }
}
~~~

**src/com.example.library/com/example/library/api/SamePackageDemo.java**:

~~~java
package com.example.library.api;

public final class SamePackageDemo {
    private SamePackageDemo() {}

    public static String readInternalNote(User user) {
        return user.internalNote();
    }
}
~~~

**src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.library.api.SamePackageDemo;
import com.example.library.api.User;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Exception {
        User user = new User();

        // (1) Truy cập qua public API trong exported package.
        System.out.println("Public: " + user.getName());

        // (2) Code cùng package library truy cập package-private.
        System.out.println("Package: "
                + SamePackageDemo.readInternalNote(user));

        // Hai lệnh sau không biên dịch vì Java access modifiers:
        // user.internalNote();
        // user.secretNote();

        // (3) App được opens package, nên có deep reflection.
        Field tokenField = User.class.getDeclaredField("token");
        tokenField.setAccessible(true);
        System.out.println("Private field qua reflection: "
                + tokenField.get(user));

        Method privateMethod =
                User.class.getDeclaredMethod("secretNote");
        privateMethod.setAccessible(true);
        System.out.println("Private method qua reflection: "
                + privateMethod.invoke(user));
    }
}
~~~

### 7.2. Biên dịch và chạy

Tại thư mục cha chứa **src/**, sử dụng JDK 17 trở lên:

~~~bash
javac --module-source-path src -d mods -m com.example.library,com.example.app
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Kết quả dự kiến:

~~~text
Public: An
Package: package-private OK trong package
Private field qua reflection: demo-token
Private method qua reflection: private chỉ thuộc logic của User
~~~

Đây là ví dụ **minh họa cơ chế**: một ứng dụng thực tế không nên truy xuất token/secret bằng reflection chỉ vì có thể thực hiện.

### 7.3. Ba thí nghiệm hữu ích

**Thí nghiệm A — bỏ opens:** Xóa dòng **opens com.example.library.api to com.example.app;** và biên dịch/chạy lại. Phần gọi **getName()** và **SamePackageDemo.readInternalNote()** vẫn hoạt động, nhưng thao tác **setAccessible(true)** vào private field không còn được cho phép từ module app.

**Thí nghiệm B — bỏ exports:** Giữ **opens** nhưng bỏ **exports**. Code app còn import trực tiếp **User** và **SamePackageDemo** sẽ không biên dịch được. Muốn thao tác phản chiếu thuần túy trong cấu hình opens-only, cần viết app không tham chiếu tĩnh đến các class ấy, đồng thời nạp class và thực hiện reflection theo quy tắc module.

**Thí nghiệm C — thêm lời gọi trực tiếp:** Bỏ comment ở dòng **user.internalNote()** hoặc **user.secretNote()**. Java compiler từ chối cho dù module library đã có cả **exports** lẫn **opens**. Đây chính là kết quả cần ghi nhớ.

## 8. Vì sao --add-exports và --add-opens vẫn không biến private thành public?

Một số lỗi JPMS gợi ý sử dụng tùy chọn launcher:

~~~bash
java --add-exports com.example.library/com.example.library.api=com.example.app ...
java --add-opens com.example.library/com.example.library.api=com.example.app ...
~~~

Ý nghĩa:

- **--add-exports** thêm quyền export package cho module đích trong môi trường tương ứng; nó giúp dùng các **public types/members** mà Java có thể cho phép truy cập.
- **--add-opens** mở package cho **deep reflection** tới module đích lúc chạy.
- Cả hai tùy chọn đều **không viết lại modifier Java** thành viên. Gọi trực tiếp package-private/private member từ package khác vẫn vi phạm quy tắc ngôn ngữ.

Trong code được biên dịch trước, hãy phân biệt tùy chọn của **javac** và của **java**: quyền bổ sung lúc chạy không thể tự sửa một lỗi truy cập đã xảy ra ở compile time. Không dựa vào flag để thay thế hợp đồng public API ổn định.

## 9. Những hiểu lầm phổ biến

### “Module đã requires thì gọi được tất cả class của dependency”

Sai. **requires** thiết lập readability ở mức module; code vẫn cần package được export và class/member có quyền truy cập hợp lệ. Một module có thể readable nhưng vẫn che hầu hết package triển khai.

### “Package đã exports thì package-private trở thành public”

Sai. **exports** áp dụng cho public API có thể truy cập theo luật Java. Package-private method vẫn chỉ dành cho code cùng package.

### “opens cho phép gọi private method như bình thường”

Sai. **opens** chỉ mở đường cho các cơ chế reflection được hỗ trợ, sau khi code thực hiện API truy cập tương ứng. Gọi **user.secretNote()** trực tiếp vẫn bị compiler từ chối.

### “setAccessible(true) lúc nào cũng thành công”

Sai. JPMS mạnh về encapsulation và có thể chặn deep reflection khi package không được mở cho module gọi. API **setAccessible** có thể ném **InaccessibleObjectException**. Thành công còn phụ thuộc vào trường hợp truy cập cụ thể.

### “Đặt class ở package cùng tên trong một module khác sẽ truy cập được package-private”

Không nên giả định. Trong JPMS, tên package giống nhau không có nghĩa chúng chia sẻ một phạm vi package runtime có quyền truy cập giống nhau. Named modules còn có giới hạn liên quan đến split packages, class loader và module resolution. Hãy để class nội bộ trong đúng module/package của nó, hoặc thiết kế public API rõ ràng.

### “Private luôn luôn chỉ được class khai báo truy cập”

Trong Java hiện đại có ngoại lệ **nestmates** cho các class cùng nest, ví dụ outer/nested class. Nhưng điều này là quy tắc access của Java, không phải chức năng của **requires**, **exports** hay **opens**.

## 10. Thiết kế module API đúng cách

Khi xây dựng thư viện hoặc hệ thống nhiều module:

1. Đặt **API được hỗ trợ** vào package rõ ràng, class public, member public cần thiết và khai báo **exports** package đó.
2. Đặt helper/package-private implementation bên trong package/module sở hữu. Dùng private cho trạng thái và chi tiết chỉ dành cho class/nest.
3. Giữ các package implementation không export nếu code ngoài module không nên dùng trực tiếp.
4. Nếu framework cần deep reflection, chỉ **opens package phù hợp cho module framework cụ thể** khi khả thi, ví dụ **opens com.example.library.model to org.hibernate.orm.core;** với module name đúng thực tế của phiên bản thư viện đang dùng.
5. Ưu tiên constructor, interface, factory, DTO và các public API có chủ đích. Reflection nên là lựa chọn có lý do cụ thể và hợp đồng rõ ràng.
6. Không để việc “chạy được bằng --add-opens” che lấp một ranh giới phụ thuộc bị thiết kế sai.

Một thiết kế thường gặp:

~~~java
module com.example.order {
    exports com.example.order.api;

    // Chỉ framework cần phản chiếu model mới được mở package này:
    // opens com.example.order.model to ten.module.framework.thuc.te;
}
~~~

Trong ví dụ trên, dòng **opens** được comment để nhấn mạnh việc phải thay tên module framework bằng tên module thực tế trước khi áp dụng. Public API và package triển khai được quản lý theo nhu cầu cụ thể, không cần công khai mọi thứ.

## 11. Câu hỏi ôn tập

1. Module A khai báo **requires B**, còn B khai báo **exports b.api**. Vì sao A vẫn không thể gọi phương thức package-private của public class trong **b.api**?
2. **exports b.api** và **opens b.api to a** khác nhau thế nào đối với compiler và reflective access?
3. Nếu bỏ **opens** trong ví dụ thực hành, dòng nào có khả năng ném **InaccessibleObjectException**?
4. Một public method trong một public class nằm trong package không được export có thể import trực tiếp từ named module khác không? Vì sao?
5. Khi nào code cùng package có thể truy cập package-private member? Vì sao điều đó không cho phép mọi class từ module khác cùng tên package làm vậy?
6. Vì sao một thiết kế plugin/framework tốt thường cần public service interface ổn định thay vì dùng reflection vào private member của plugin?
7. Dùng **--add-exports** có giúp gọi **user.secretNote()** trực tiếp không? Dùng **--add-opens** có giúp compiler chấp nhận lời gọi đó không?

## 12. Ghi nhớ

**JPMS áp dụng quyền truy cập ở mức module, còn Java modifier áp dụng quyền truy cập ở mức class/member.** Để một lời gọi thông thường từ module khác hoạt động, module gọi phải đọc được module cung cấp, package được export phù hợp và class/member phải có mức truy cập được Java cho phép.

**Package-private vẫn là package-private; private vẫn là private**, kể cả khi package đã **exports**. **opens** cho phép một số thao tác deep reflection, nhưng không thay đổi khả năng gọi trực tiếp theo cú pháp Java.

Tài liệu tham khảo:

- [Java Language Specification, Chapter 6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html) (phạm vi tên và khả năng truy cập).
- [Java Language Specification, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html) (khai báo package/module, exports và opens).
- [java.lang.reflect.AccessibleObject — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html) (quy tắc cho phép truy cập phản chiếu).
