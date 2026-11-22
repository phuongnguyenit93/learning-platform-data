# Truy cập thành viên công khai theo ranh giới module trong Java 17

Trong Java, khai báo một lớp hoặc phương thức là `public` chưa đủ để mọi module đều có thể sử dụng nó. Từ khi Java Platform Module System (JPMS) được đưa vào Java 9, khả năng truy cập giữa các module còn phụ thuộc vào **package có được export hay không** và module sử dụng có khai báo quan hệ phụ thuộc phù hợp hay không.

Điều này cũng áp dụng khi dùng Reflection. Một phương thức có modifier `public` nhưng nằm trong package không được export cho module gọi vẫn có thể không gọi được qua `Method.invoke`. Reflection cho phép tìm thành viên theo metadata của lớp, nhưng **tìm thấy thành viên không đồng nghĩa với việc đã có quyền truy cập thành viên đó**.

Bài này giải thích cách truy cập thành viên công khai qua ranh giới module trong Java 17, cách khai báo `exports`, `requires` và qualified export, cách Reflection kiểm tra quyền truy cập, cùng sự khác nhau giữa `exports` và `opens`.

## 1. Bốn điều kiện cần phân biệt

Giả sử module `com.example.library` cung cấp một lớp:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Một module ứng dụng muốn gọi `greet` cần xét các yếu tố sau:

1. **Kiểu khai báo phải truy cập được:** lớp `GreetingService` là `public`.
2. **Thành viên phải truy cập được:** phương thức `greet` là `public`.
3. **Package phải được module cung cấp export:** module thư viện phải export package `com.example.api` cho module ứng dụng.
4. **Module sử dụng phải khai báo dependency phù hợp:** trong mã Java thông thường, module ứng dụng khai báo `requires com.example.library`.

Nếu thiếu điều kiện export, việc lớp và phương thức đều có modifier `public` vẫn không giúp module khác truy cập chúng bằng mã nguồn thông thường.

Có thể ghi nhớ:

~~~text
Module A (library)
    |
    | exports com.example.api
    v
Package com.example.api
    |
    +-- public class GreetingService
            |
            +-- public method greet(...)

Module B (application)
    |
    +-- requires com.example.library
    |
    +-- có thể dùng GreetingService.greet(...)
~~~

**Ranh giới module được áp dụng ở cấp package.** Directive `exports` export một package, không export riêng một phương thức hoặc một lớp đơn lẻ.

## 2. Khai báo module và export package

Một ứng dụng dùng module path thường có cấu trúc:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── com/example/api/GreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 2.1. Module cung cấp API

File `src/com.example.library/module-info.java`:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Directive:

~~~java
exports com.example.api;
~~~

có nghĩa package `com.example.api` được export cho các module khác. Các kiểu `public` và thành viên `public` của những kiểu đó có thể được module đọc và sử dụng theo các quy tắc truy cập Java.

File `src/com.example.library/com/example/api/GreetingService.java`:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

### 2.2. Module sử dụng API

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Directive `requires` khai báo module ứng dụng phụ thuộc vào module thư viện. Nhờ đó, mã nguồn trong `com.example.app` có thể tham chiếu các kiểu public thuộc package được export từ thư viện.

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("An"));
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac --module-source-path src -d out -m com.example.library,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Xin chào, An
~~~

Trong ví dụ này, ba thành phần phối hợp với nhau:

- `exports com.example.api` ở module thư viện công bố package API.
- `requires com.example.library` ở module ứng dụng khai báo dependency.
- Modifier `public` trên lớp và phương thức cho phép sử dụng chúng từ package khác, sau khi ranh giới module đã cho phép.

### 2.3. Nếu bỏ exports thì điều gì xảy ra?

Nếu module thư viện chỉ khai báo:

~~~java
module com.example.library {
    // Không export com.example.api
}
~~~

thì mã ứng dụng:

~~~java
import com.example.api.GreetingService;
~~~

không thể biên dịch qua ranh giới module. Compiler báo package không được export hoặc không hiển thị cho module đang dùng.

Việc thêm `public` vào lớp hoặc phương thức không sửa được vấn đề. Cần điều chỉnh hợp đồng module bằng directive `exports` phù hợp.

## 3. Export công khai và qualified export

Không phải package API nào cũng cần công bố cho tất cả module. Java hỗ trợ **qualified export**, chỉ export package cho một hoặc một nhóm module được chỉ định.

### 3.1. Export cho tất cả module đọc thư viện

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Đây là unqualified export. Package được export cho mọi module có thể đọc module thư viện.

### 3.2. Chỉ export cho module được chọn

~~~java
module com.example.library {
    exports com.example.api to com.example.app;
}
~~~

Trong trường hợp này, package `com.example.api` chỉ được export cho module `com.example.app`. Module khác không tự động có quyền truy cập package đó.

Có thể chỉ định nhiều module:

~~~java
module com.example.library {
    exports com.example.api
            to com.example.app, com.example.integration;
}
~~~

Tên sau `to` là **module name**, không phải package name hay tên class.

### 3.3. Khi nào dùng qualified export?

Qualified export hữu ích khi thư viện chỉ muốn công bố một phần API cho những module cộng tác đã biết, ví dụ:

- Package SPI dành riêng cho module plugin nội bộ.
- Package tích hợp chỉ dùng giữa các module trong cùng sản phẩm.
- API hỗ trợ được công bố cho một module adapter cụ thể.
- Giữ package triển khai ở trạng thái encapsulated với phần còn lại của ứng dụng.

Không nên dùng qualified export để thay thế một API công khai cần được nhiều ứng dụng tiêu thụ. Nếu package là hợp đồng công khai của thư viện, unqualified export thường rõ ràng hơn.

## 4. Export package không có nghĩa export mọi thành viên

Directive `exports` mở quyền truy cập module cho package, nhưng các quy tắc access modifier của Java vẫn được áp dụng.

~~~java
package com.example.api;

public class Account {
    public String id() {
        return "A-100";
    }

    protected void refresh() {
    }

    void internalCheck() {
    }

    private void resetSecret() {
    }
}
~~~

Nếu package `com.example.api` được export:

| Thành viên | Modifier | Module khác truy cập bằng mã nguồn thông thường? |
|---|---|---|
| `id()` | `public` | Có |
| `refresh()` | `protected` | Theo quy tắc protected: cần quan hệ kế thừa và điều kiện truy cập phù hợp |
| `internalCheck()` | package-private | Không |
| `resetSecret()` | `private` | Không |

`exports` không biến mọi thành viên thành public. Nó cho phép module khác tiếp cận các kiểu public trong package và sử dụng thành viên theo modifier, quy tắc kế thừa và quy tắc truy cập Java thông thường.

Một kiểu top-level package-private vẫn không trở thành public chỉ vì package được export.

### 4.1. Thành viên public của lớp không public

Ví dụ:

~~~java
package com.example.api;

class InternalService {
    public void execute() {
    }
}
~~~

Dù `execute` là `public`, lớp `InternalService` không public nên mã nguồn ở package khác không thể tham chiếu trực tiếp đến lớp này.

Để công bố một API cho module khác, cần kiểu khai báo có mức truy cập phù hợp, thường là public class/interface/record và public member trong package được export.

## 5. Module readability: vai trò của requires

Trong mã nguồn module, `requires` khai báo module hiện tại cần đọc một module khác.

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Nếu bỏ directive này, compiler không coi module thư viện là dependency được khai báo của ứng dụng trong quá trình biên dịch module thông thường.

### 5.1. requires không thay thế exports

Hai directive giải quyết hai phía khác nhau:

| Directive | Đặt ở đâu? | Ý nghĩa |
|---|---|---|
| `requires com.example.library;` | Module sử dụng | Khai báo module hiện tại phụ thuộc vào module thư viện |
| `exports com.example.api;` | Module cung cấp | Công bố package cho module khác |
| `exports com.example.api to com.example.app;` | Module cung cấp | Công bố package cho module được chỉ định |

Chỉ có `requires` mà package không export thì ứng dụng vẫn không được truy cập package đó theo mã nguồn thông thường.

Chỉ có `exports` nhưng ứng dụng không khai báo dependency phù hợp thì cấu hình module ứng dụng vẫn chưa hoàn chỉnh.

### 5.2. requires transitive

Một module có thể công bố API chứa kiểu đến từ module phụ thuộc. Khi đó `requires transitive` có thể giúp các module đọc module hiện tại cũng đọc được dependency được truyền tiếp:

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

Ví dụ, API public của `com.example.api` có thể trả về kiểu `com.example.model.User`. Module sử dụng API cần đọc được cả module API và module model để dùng kiểu xuất hiện trong chữ ký public.

Không dùng `requires transitive` chỉ vì muốn “mở quyền” truy cập một package. Nó giải quyết quan hệ readability được truyền tiếp, còn quyền truy cập package vẫn do export và access modifier quyết định.

## 6. Truy cập thành viên public bằng Reflection

Reflection cho phép chương trình tìm và gọi thành viên dựa trên đối tượng `Class` tại runtime. Nhưng Reflection không bỏ qua ranh giới module.

Ví dụ với module thư viện export `com.example.api`:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Module ứng dụng có thể gọi qua Reflection:

~~~java
package com.example.app;

import java.lang.reflect.Method;

public class ReflectiveMain {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName("com.example.api.GreetingService");

        Object service = type.getConstructor().newInstance();

        Method method = type.getMethod("greet", String.class);
        Object result = method.invoke(service, "An");

        System.out.println(result);
    }
}
~~~

Vì lớp và phương thức đều public, package được export cho module gọi, thao tác phản chiếu này được phép.

### 6.1. getMethod và getDeclaredMethod

Hai API thường gặp:

~~~java
Method publicMethod = type.getMethod("greet", String.class);
Method declaredMethod = type.getDeclaredMethod("greet", String.class);
~~~

- `getMethod` tìm phương thức public của lớp, bao gồm phương thức public kế thừa.
- `getDeclaredMethod` tìm phương thức được khai báo trực tiếp trong lớp, không giới hạn ở public; nó có thể tìm private, protected hoặc package-private method.

**Khả năng tìm thấy khác với khả năng gọi được.** Một method có thể được tìm thấy qua Reflection nhưng khi gọi, access check vẫn có thể từ chối.

Ví dụ:

~~~java
Method method = type.getDeclaredMethod("internalOperation");
method.invoke(instance); // Có thể thất bại nếu caller không có quyền truy cập.
~~~

Không nên dùng `getDeclaredMethod` như một cách tự động vượt qua module encapsulation.

### 6.2. Public member trong package không được export

Giả sử module thư viện có:

~~~java
module com.example.library {
    exports com.example.api;
    // Không export com.example.internal
}
~~~

và lớp:

~~~java
package com.example.internal;

public class InternalDiagnostics {
    public String status() {
        return "internal";
    }
}
~~~

Lớp và phương thức đều public, nhưng package `com.example.internal` không export cho module ứng dụng. Module khác có thể gặp giới hạn khi cố truy cập reflective member.

Ví dụ mã thử:

Module thư viện có thể cung cấp một factory public trong package đã export để tạo đối tượng nội bộ mà không công bố kiểu triển khai:

~~~java
package com.example.api;

public class DiagnosticsFactory {
    public Object create() {
        return new com.example.internal.InternalDiagnostics();
    }
}
~~~

Module ứng dụng nhận đối tượng dưới dạng `Object`, sau đó tìm method public:

~~~java
import com.example.api.DiagnosticsFactory;

Object instance = new DiagnosticsFactory().create();
Method method = instance.getClass().getMethod("status");

System.out.println(method.invoke(instance));
~~~

Việc lấy được đối tượng và `Method` không làm package nội bộ trở thành package được export. Lệnh `invoke` vẫn có thể ném `IllegalAccessException` vì method được khai báo trong lớp thuộc package không export cho caller.

Việc tải được metadata lớp hoặc lấy được đối tượng `Method` không đảm bảo `invoke` được phép. Nếu package không được export hoặc mở cho caller theo cách phù hợp, thao tác truy cập có thể ném `IllegalAccessException`.

Cách giải quyết đúng phụ thuộc vào ý định thiết kế:

- Nếu đây là API public cho module ứng dụng, export package phù hợp.
- Nếu đây là chi tiết nội bộ chỉ cần Reflection sâu cho một framework/module cụ thể, cân nhắc qualified `opens`.
- Nếu package không được thiết kế để sử dụng bên ngoài, không nên dựa vào việc truy cập nó bằng Reflection.

## 7. exports và opens: hai cơ chế khác nhau

Đây là khác biệt quan trọng nhất khi làm việc với Reflection trong hệ thống module.

| Directive | Truy cập mã nguồn thông thường | Reflection với public member | Deep reflection vào thành viên non-public |
|---|---|---|---|
| `exports p` | Có, theo access modifier | Có | Không tự động |
| `exports p to m` | Có, chỉ module được chỉ định | Có, chỉ module được chỉ định | Không tự động |
| `opens p` | Không cấp quyền truy cập mã nguồn thông thường | Có thể bật access override bằng `trySetAccessible` khi cần | Có thể cho phép deep reflection |
| `opens p to m` | Không cấp quyền truy cập mã nguồn thông thường | Module `m` có thể bật access override khi cần | Có thể cho phép deep reflection cho `m` |

### 7.1. exports dành cho API công khai

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Dùng khi module khác cần:

- Import và tham chiếu public class/interface/record.
- Gọi public constructor và method.
- Truy cập public field theo quy tắc Java.
- Dùng Reflection trên public member của public type trong package đã export.

Đây là cách phù hợp để công bố API công khai của thư viện.

### 7.2. opens dành cho Reflection tại runtime

~~~java
module com.example.library {
    opens com.example.internal;
}
~~~

`opens` không cho module khác import package đó trong mã nguồn Java như một package được export. Nó cho phép Reflection tại runtime tiếp cận các kiểu và thành viên trong package, bao gồm deep reflection theo các quy tắc của JPMS.

Một framework có thể cần đọc hoặc ghi field private để ánh xạ object. Trong tình huống đó, `opens` có thể là directive phù hợp hơn `exports`.

### 7.3. Qualified opens

Nếu chỉ một module framework cần deep reflection:

~~~java
module com.example.library {
    exports com.example.api;
    opens com.example.model to com.example.mapper;
}
~~~

Trong ví dụ:

- `com.example.api` là API công khai cho các module sử dụng.
- `com.example.model` được mở cho module `com.example.mapper` để Reflection tại runtime.
- Các module khác không tự động được deep reflection vào `com.example.model`.

Qualified opens giúp giới hạn bề mặt truy cập nội bộ.

### 7.4. Open module

Java cho phép khai báo:

~~~java
open module com.example.library {
    requires com.example.model;
}
~~~

Một `open module` mở các package của module cho Reflection tại runtime. Tuy nhiên, điều đó **không đồng nghĩa mọi package đều được export cho truy cập mã nguồn thông thường**.

Đây là lựa chọn rộng. Trong thiết kế module, nên mở đúng package và đúng module cần thiết bằng qualified `opens` khi có thể.

## 8. Kiểm soát deep reflection với trySetAccessible

Java 9 trở đi có API `trySetAccessible` để thử bật quyền truy cập bỏ qua access check cho một thành viên. API trả về boolean để cho biết có thể bật hay không.

Ví dụ:

~~~java
import java.lang.reflect.Field;

Field field = type.getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(instance);
    System.out.println(value);
} else {
    System.out.println("Module không mở package cho deep reflection");
}
~~~

Nếu package được mở cho module gọi, thao tác có thể thành công theo các điều kiện của JPMS. Nếu package không được mở và không có ngoại lệ cho phép khác, phương thức trả về `false`.

### 8.1. setAccessible(true) có thể thất bại

Cách cũ hơn:

~~~java
field.setAccessible(true);
~~~

có thể ném `InaccessibleObjectException` khi không thể mở quyền truy cập. Vì vậy, với code cần kiểm soát kết quả, `trySetAccessible` thường giúp xử lý rõ ràng hơn.

Không nên giả định gọi `setAccessible(true)` luôn vượt qua được module boundary. Strong encapsulation trong JPMS được áp dụng có chủ đích để bảo vệ API và implementation nội bộ.

### 8.2. canAccess để kiểm tra khả năng truy cập hiện tại

`AccessibleObject.canAccess(Object)` kiểm tra khả năng truy cập hiện tại tới thành viên:

~~~java
Method method = type.getMethod("greet", String.class);

boolean accessible = method.canAccess(instance);
System.out.println(accessible);
~~~

Với thành viên instance, truyền đối tượng đích. Với thành viên static, truyền `null`.

`canAccess` không thay đổi quyền truy cập. `trySetAccessible` mới là phương thức thử bật quyền bỏ qua kiểm tra truy cập trong những trường hợp được module system cho phép.

## 9. Ví dụ hoàn chỉnh: export API và opens package model

Giả sử có ba module:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   ├── com/example/api/UserService.java
│   └── com/example/model/UserRecord.java
├── com.example.mapper/
│   ├── module-info.java
│   └── com/example/mapper/MapperMain.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Module thư viện:

~~~java
module com.example.library {
    exports com.example.api;
    exports com.example.model;
    opens com.example.model to com.example.mapper;
}
~~~

Public API:

~~~java
package com.example.api;

import com.example.model.UserRecord;

public class UserService {
    public UserRecord findUser() {
        return new UserRecord("U01", "An");
    }
}
~~~

Model:

~~~java
package com.example.model;

public class UserRecord {
    private final String id;
    private String name;

    public UserRecord(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Module mapper:

~~~java
module com.example.mapper {
    requires com.example.library;
}
~~~

Mã Reflection trong mapper:

~~~java
package com.example.mapper;

import com.example.api.UserService;

import java.lang.reflect.Field;

public class MapperMain {
    public static void main(String[] args) throws Exception {
        Object user = new UserService().findUser();

        Field nameField = user.getClass().getDeclaredField("name");

        if (nameField.trySetAccessible()) {
            System.out.println(nameField.get(user));
        } else {
            System.out.println("Không được mở quyền truy cập");
        }
    }
}
~~~

Package `com.example.model` cũng được export vì kiểu `UserRecord` xuất hiện trong chữ ký public của `UserService`. Vì vậy các module đọc thư viện có thể dùng public API của `UserRecord`. Package này đồng thời chỉ được mở cho mapper, nên mapper có thể thực hiện deep reflection vào field private; module app không nhận quyền truy cập sâu đó.

Module ứng dụng bình thường:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Mã trong app có thể gọi `UserService` và dùng public API của `UserRecord` vì cả hai package đều được export. Nhưng app không được mặc nhiên truy cập deep reflection vào package `com.example.model`, bởi package này chỉ được mở cho `com.example.mapper`.

Điều này cho phép thư viện công bố API ổn định, đồng thời chỉ mở phần model cho framework được chỉ định.

## 10. Qualified export và qualified opens trong thực tế

Hãy xem module thư viện:

~~~java
module com.example.library {
    exports com.example.api to com.example.app, com.example.integration;
    opens com.example.model to com.example.mapper;
}
~~~

Có thể đọc như sau:

- Module `com.example.app` và `com.example.integration` có thể truy cập API public trong `com.example.api`.
- Module `com.example.mapper` có thể dùng Reflection sâu trong `com.example.model`.
- Module khác không có các quyền đó chỉ vì chúng có thể đọc module thư viện.

Đây là nguyên tắc **least privilege**: chỉ công bố package và mở Reflection cho module thực sự cần quyền.

Khi một framework báo lỗi Reflection, đừng lập tức mở toàn bộ module. Trước tiên hãy xác định:

1. Framework đang truy cập package nào?
2. Module của framework có tên gì?
3. Nó cần gọi public API hay cần truy cập private field/method?
4. Package cần `exports` hay `opens`?
5. Có thể giới hạn directive bằng qualified export/open hay không?

## 11. Các trường hợp dễ nhầm

### 11.1. Public class nhưng package không export

~~~java
package com.example.internal;

public class InternalApi {
    public void execute() {
    }
}
~~~

Nếu `com.example.internal` không export, module khác không thể tham chiếu lớp này qua mã nguồn thông thường. Modifier `public` không vượt qua ranh giới module.

### 11.2. Package được export nhưng private member vẫn private

~~~java
package com.example.api;

public class User {
    private String password;
}
~~~

`exports com.example.api` cho phép module khác sử dụng public API của package. Nó không tự cho phép đọc `password` qua deep reflection. Muốn framework truy cập private member, cần mở package cho module framework hoặc thiết kế API truy cập rõ ràng.

### 11.3. Package được opens nhưng không export

~~~java
module com.example.library {
    opens com.example.model to com.example.mapper;
}
~~~

Module mapper có thể dùng Reflection trong phạm vi được mở, nhưng mã nguồn mapper không thể import kiểu từ `com.example.model` chỉ dựa trên directive `opens`. Nếu mapper cần dùng kiểu đó trong chữ ký mã nguồn, package còn cần được export cho mapper.

### 11.4. getDeclaredMethod không vượt qua access check

~~~java
Method method = type.getDeclaredMethod("secretOperation");
~~~

Lệnh này có thể tìm private method, nhưng gọi `method.invoke(...)` vẫn chịu quy tắc truy cập. Nếu package không được mở phù hợp, Reflection sâu bị từ chối.

### 11.5. HTTP status hoặc lỗi I/O không liên quan đến module access

Nếu `Method.invoke` ném `InvocationTargetException`, cần phân biệt:

- `IllegalAccessException`: caller không được phép truy cập method.
- `InvocationTargetException`: method đã được gọi nhưng code bên trong method ném exception.
- `InaccessibleObjectException`: không thể bật access override bằng API Reflection.
- `ClassNotFoundException`: không tìm thấy lớp theo tên được yêu cầu.

Đọc đúng loại lỗi giúp phân biệt vấn đề module/access với lỗi logic bên trong phương thức.

### 11.6. Không nhầm classpath với module path

Mã chạy trên classpath thường thuộc unnamed module. Unnamed module có quy tắc truy cập khác với các named module trong ứng dụng modular. Vì vậy, một chương trình chạy được trên classpath chưa chứng minh cấu hình `exports`/`opens` giữa các named module đã đúng.

Khi muốn kiểm tra ranh giới JPMS, hãy biên dịch và chạy các module trên module path như ví dụ trong bài.

## 12. Xử lý lỗi Reflection có chủ đích

Khi gọi method bằng Reflection, nên xử lý riêng các nhóm lỗi quan trọng:

~~~java
try {
    Method method = type.getMethod("greet", String.class);
    Object result = method.invoke(instance, "An");
    System.out.println(result);

} catch (NoSuchMethodException e) {
    System.err.println("API không có method mong muốn");

} catch (IllegalAccessException e) {
    System.err.println("Không có quyền truy cập method qua module boundary");

} catch (InvocationTargetException e) {
    System.err.println("Method bên trong đã ném lỗi: "
            + e.getCause());
}
~~~

Nếu cần deep reflection:

~~~java
Field field = type.getDeclaredField("secret");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package chưa được mở cho module hiện tại"
    );
}
~~~

Không nên bắt mọi exception rồi tiếp tục như thể truy cập đã thành công. Khi module boundary từ chối quyền, hãy xử lý ở cấu hình module hoặc thay đổi thiết kế API.

## 13. Kiểm tra trạng thái module tại runtime

Các API của `Module` giúp quan sát cấu hình export/open:

~~~java
Module targetModule = GreetingService.class.getModule();
Module callerModule = Main.class.getModule();

System.out.println(targetModule.getName());

boolean exported = targetModule.isExported(
        "com.example.api",
        callerModule
);

boolean opened = targetModule.isOpen(
        "com.example.api",
        callerModule
);

System.out.println("Exported: " + exported);
System.out.println("Opened: " + opened);
~~~

- `isExported(packageName, otherModule)` kiểm tra package có được export cho module đích không.
- `isOpen(packageName, otherModule)` kiểm tra package có được mở cho Reflection đối với module đích không.

Đây là các API quan sát trạng thái module. Chúng hữu ích khi debug cấu hình module phức tạp hoặc lỗi Reflection trong framework.

Không nên dùng kết quả `isOpen` để suy luận rằng mã nguồn có thể import package; `opens` và `exports` có mục đích khác nhau.

## 14. Lựa chọn thiết kế API

Khi thiết kế một thư viện modular, hãy xác định package nào thực sự là API công khai:

| Mục tiêu | Thiết kế phù hợp |
|---|---|
| Module khác import và gọi public API | `exports` package API |
| Chỉ một số module được dùng package API | Qualified `exports` |
| Framework cần truy cập private field/method | Qualified `opens` cho package model |
| Package là implementation detail | Không export package |
| Nhiều package cần Reflection nội bộ nhưng không muốn mở toàn bộ module | Mở từng package cần thiết |
| Module khác cần đọc kiểu xuất hiện trong public API | Khai báo `requires` phù hợp; dùng `requires transitive` nếu dependency cần được truyền tiếp |
| Muốn kiểm tra ranh giới module thực tế | Chạy trên module path, không chỉ classpath |

Một API tốt nên công bố những kiểu mà người dùng cần tham chiếu, giữ package triển khai ở trạng thái đóng, và chỉ mở deep reflection khi framework có lý do cụ thể.

### 14.1. Không dùng Reflection để né thiết kế API

Nếu module khác thường xuyên cần đọc private field hoặc gọi private method, có thể API đang thiếu thao tác công khai phù hợp.

Ví dụ, thay vì mở toàn bộ model để framework sửa field tùy ý, cân nhắc:

~~~java
public class User {
    private String displayName;

    public String displayName() {
        return displayName;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = newName;
    }
}
~~~

API công khai giữ được bất biến của đối tượng và giúp module sở hữu dữ liệu kiểm soát cách thay đổi.

## 15. Ví dụ nhỏ để tự kiểm tra quyền truy cập

Giả sử module library:

~~~java
module demo.library {
    exports demo.api;
}
~~~

Trong package `demo.api`:

~~~java
package demo.api;

public class PublicService {
    public void run() {
        System.out.println("public API");
    }

    private void secret() {
        System.out.println("secret");
    }
}
~~~

Trong module app:

~~~java
module demo.app {
    requires demo.library;
}
~~~

Mã app:

~~~java
package demo.app;

import demo.api.PublicService;

public class Main {
    public static void main(String[] args) throws Exception {
        PublicService service = new PublicService();
        service.run();

        var method = PublicService.class.getDeclaredMethod("secret");

        System.out.println(method.trySetAccessible());
    }
}
~~~

Kết quả:

- `service.run()` chạy bình thường vì lớp và method public trong package được export.
- `trySetAccessible()` cho private method có thể trả về `false` vì package không được mở cho module app.
- Nếu cần deep reflection, module library có thể thêm `opens demo.api to demo.app;`, nhưng việc đó mở quyền Reflection sâu cho module app và cần cân nhắc thiết kế.

Biên dịch và chạy:

~~~bash
javac --module-source-path src -d out -m demo.library,demo.app
java --module-path out -m demo.app/demo.app.Main
~~~

## 16. Bài tập thực hành

### Bài 1: Tại sao public method không truy cập được?

Module `store.core` chứa:

~~~java
package store.internal;

public class StorageEngine {
    public void start() {
    }
}
~~~

Module `store.app` khai báo `requires store.core` nhưng module core không export `store.internal`.

**Câu hỏi:** Vì sao app không thể import `StorageEngine`?

**Đáp án:** `requires` chỉ khai báo dependency/readability. Package `store.internal` chưa được export từ `store.core`. Cần export package nếu đó là API công khai; nếu nó là implementation detail thì app không nên truy cập trực tiếp.

### Bài 2: Chọn exports hay opens?

Một module ứng dụng cần import và gọi public method trong `com.example.api`. Chọn directive nào?

**Đáp án:** `exports com.example.api;`.

Một framework mapper cần truy cập private field trong `com.example.model` tại runtime. Chọn directive nào?

**Đáp án:** `opens com.example.model to tên.module.mapper;`, với module name thực tế của framework.

### Bài 3: Qualified export

Chỉ module `com.example.admin` được phép sử dụng package `com.example.adminapi`. Hãy viết module descriptor.

**Đáp án:**

~~~java
module com.example.platform {
    exports com.example.adminapi to com.example.admin;
}
~~~

### Bài 4: Reflection tìm thấy nhưng không gọi được

`getDeclaredMethod("secret")` trả về một `Method`. Vì sao `invoke` vẫn có thể ném `IllegalAccessException`?

**Đáp án:** API tìm kiếm Reflection không tự cấp quyền truy cập. Việc gọi vẫn chịu access check của Java và JPMS. Package phải được export/open phù hợp với loại truy cập; deep reflection còn cần quyền mở package.

### Bài 5: requires có thay thế exports không?

Module app đã có `requires com.example.library`. Vì sao vẫn không dùng được lớp public trong package không export?

**Đáp án:** `requires` tạo quan hệ phụ thuộc/readability. `exports` mới công bố package cho module khác. Hai directive giải quyết hai điều kiện khác nhau.

### Bài 6: Kiểm tra module runtime

Dùng `Module.isExported` và `Module.isOpen` để kiểm tra package `com.example.api` có export/open cho module app hay không.

**Đáp án tham khảo:**

~~~java
Module library = PublicService.class.getModule();
Module app = Main.class.getModule();

System.out.println(library.isExported("com.example.api", app));
System.out.println(library.isOpen("com.example.api", app));
~~~

## 17. Ghi nhớ

Khi truy cập thành viên public qua ranh giới module trong Java 17, hãy kiểm tra theo thứ tự:

1. Lớp hoặc interface được công bố có phải public không?
2. Thành viên cần gọi có phải public không?
3. Package chứa kiểu đó đã được module cung cấp export cho caller chưa?
4. Module sử dụng đã khai báo dependency/readability phù hợp trong module graph chưa?
5. Nếu dùng Reflection, bạn chỉ gọi public member hay đang cần deep reflection vào private/package-private member?
6. Nếu cần deep reflection, package đã được opens cho đúng module caller chưa?

**`exports` công bố API; `opens` cấp quyền Reflection tại runtime.** Hai directive không thay thế nhau. Khi chỉ cần gọi public API, export đúng package là thiết kế phù hợp. Khi framework thật sự cần truy cập sâu vào implementation, mở package có kiểm soát cho module đó.

## 18. Tài liệu tham khảo

- [Oracle Java SE 17 — Module Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): cú pháp module declaration, `requires`, `exports` và `opens`.
- [Oracle Java SE 17 — Module API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): kiểm tra module, package exports và opens tại runtime.
- [Oracle Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible` và access override.
- [Oracle Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): tìm và gọi method bằng Reflection.
- [Oracle Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getMethod`, `getDeclaredMethod` và metadata lớp.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): thiết kế JPMS, readability, exports và opens.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): bối cảnh strong encapsulation của các implementation nội bộ JDK.

