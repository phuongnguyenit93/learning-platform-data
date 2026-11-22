# InaccessibleObjectException do thiếu opens

Khi nâng cấp ứng dụng lên Java Platform Module System (JPMS), một lỗi dễ gặp tại runtime là **`java.lang.reflect.InaccessibleObjectException`**. Lỗi thường phát sinh khi thư viện hoặc mã ứng dụng cố dùng reflection để truy cập field, method hay constructor không public trong một named module, nhưng **package chứa thành viên chưa được mở cho module thực hiện reflection**.

Điểm dễ nhầm: một package có thể đã `exports`, kiểu Java có thể là `public`, caller có thể `requires` module nguồn, nhưng thao tác `setAccessible(true)` vẫn bị từ chối. Lý do là **`exports` và `opens` cấp hai loại quyền khác nhau**: export phục vụ truy cập API public theo ngôn ngữ Java; opens phục vụ deep reflection ở runtime.

Bài này hướng dẫn đọc thông báo lỗi, xác định module nguồn và caller, tái hiện một trường hợp bằng hai named module, sửa bằng `opens` hoặc `--add-opens`, nhận diện tình huống framework trên classpath, và kiểm tra cấu hình trong test, build, container.

## 1. Đọc đúng thông báo InaccessibleObjectException

Một thông báo điển hình:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final java.lang.String
com.acme.domain.api.Person.name accessible:
module com.acme.domain does not
"opens com.acme.domain.api" to module com.acme.inspect
    at java.base/java.lang.reflect.AccessibleObject.checkCanSetAccessible(...)
    at java.base/java.lang.reflect.Field.setAccessible(...)
    at com.acme.inspect/com.acme.inspect.Main.main(...)
~~~

Các thành phần cần nhận diện:

- **`com.acme.domain`** là module sở hữu lớp/field bị truy cập.
- **`com.acme.domain.api`** là package cần mở; không nhất thiết phải mở cả module.
- **`com.acme.inspect`** là module đang trực tiếp thực hiện reflective access.
- **`Person.name`** là field private mà đoạn mã cố truy cập.
- **`Field.setAccessible`** là dấu hiệu đang yêu cầu bỏ qua kiểm tra access modifier thông thường.

Nếu thư viện reflection nằm trên classpath, thông báo có thể ghi `to unnamed module` và thông tin class loader hoặc identity. Khi đó module đích không có tên như các named module trên module path.

Không sửa theo phỏng đoán chỉ từ tên ứng dụng chính: một thư viện ORM/JSON/test runner thường mới là caller thực sự của `setAccessible`.

## 2. exports khác opens

Xét một module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Một lớp public:

~~~java
package com.acme.domain.api;

public final class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Module khác có `requires com.acme.domain` có thể gọi public constructor và `name()`:

~~~java
Person person = new Person("An");
System.out.println(person.name());
~~~

Nhưng code sau yêu cầu deep reflection:

~~~java
Field field = Person.class.getDeclaredField("name");
field.setAccessible(true);
System.out.println(field.get(person));
~~~

Ngay cả khi package đã export, field vẫn là private. JPMS không mặc định cho module bên ngoài bỏ qua access checks vào private field. Nếu package không mở cho caller, `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Vì vậy, cần phân biệt:

| Câu hỏi | Cơ chế JPMS |
|---|---|
| Module A có được đọc module B không? | `requires` hoặc quan hệ readability hợp lệ |
| Package của B có được dùng như API từ A không? | `exports` |
| Mã Java có truy cập member theo modifier được không? | `public`, `protected`, package-private, `private` |
| A có được deep reflection vào package của B không? | `opens` hoặc `--add-opens` |

Reflection thông thường với public member của public type thuộc exported package không nhất thiết cần opens. Opens đặc biệt quan trọng khi framework muốn suppress access checks vào thành viên không public.

## 3. Fixture tối giản: hai named module

Tạo thư mục source:

~~~text
src/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/api/Person.java
└── com.acme.inspect/
    ├── module-info.java
    └── com/acme/inspect/Main.java
~~~

Module domain:

~~~java
// src/com.acme.domain/module-info.java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Class chứa private field:

~~~java
// src/com.acme.domain/com/acme/domain/api/Person.java
package com.acme.domain.api;

public final class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Module inspector:

~~~java
// src/com.acme.inspect/module-info.java
module com.acme.inspect {
    requires com.acme.domain;
}
~~~

Main:

~~~java
// src/com.acme.inspect/com/acme/inspect/Main.java
package com.acme.inspect;

import com.acme.domain.api.Person;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Person person = new Person("An");
        System.out.println("Getter: " + person.name());

        Field field = Person.class.getDeclaredField("name");
        field.setAccessible(true);
        System.out.println("Reflect: " + field.get(person));
    }
}
~~~

Biên dịch:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.domain,com.acme.inspect
~~~

Chạy:

~~~bash
java --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

Đầu tiên, public getter chạy được:

~~~text
Getter: An
~~~

Sau đó `setAccessible(true)` thất bại vì `com.acme.domain` chỉ export package mà chưa opens cho `com.acme.inspect`. Đây là khác biệt thực nghiệm giữa quyền truy cập API thông thường và quyền deep reflection.

## 4. Sửa trong module-info.java khi kiểm soát module nguồn

Nếu module inspector thực sự cần reflection vào package API, sửa descriptor module domain:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.api to com.acme.inspect;
}
~~~

Biên dịch lại rồi chạy bằng lệnh cũ:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.domain,com.acme.inspect

java --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

Kết quả mong đợi:

~~~text
Getter: An
Reflect: An
~~~

`opens com.acme.domain.api to com.acme.inspect` là **qualified opens**: package chỉ được mở cho module inspector. Các module khác không tự có quyền reflection tương ứng.

Nếu framework cần reflection vào package model chưa công khai API, có thể tách exports và opens:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serializer;
}
~~~

Module khác có thể import public types trong `api` khi có readability; riêng module `com.acme.serializer` được phép deep reflection vào `model`. `opens` không biến `model` thành package public để import như API thông thường.

## 5. opens không giới hạn và open module

Khi không thể chỉ định một module đích, descriptor có thể mở package cho mọi module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model;
}
~~~

`opens com.acme.domain.model` rộng hơn qualified opens, vì không giới hạn named module đích.

Ngoài ra:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

`open module` mở tất cả package của module cho deep reflection. Cách này đôi khi phục vụ một framework cần truy cập nhiều package, nhưng làm giảm strong encapsulation của toàn bộ module.

Không nên đổi sang `open module` chỉ để chữa một lỗi ở một field. Ưu tiên package nhỏ nhất và module đích cụ thể khi có thể. Trong một `open module` không khai báo thêm các directive `opens` riêng lẻ.

## 6. Workaround tại runtime bằng --add-opens

Nếu chưa sửa được descriptor, Java launcher hỗ trợ:

~~~text
--add-opens source.module/package=target.module
~~~

Ví dụ:

~~~bash
java --module-path out \
     --add-opens com.acme.domain/com.acme.domain.api=com.acme.inspect \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

Tùy chọn `--add-opens` bổ sung quyền mở package trong lần chạy đó, không thay đổi `module-info.class` của JAR. Vì vậy, khi bỏ flag ở lần chạy sau, lỗi có thể xuất hiện lại.

Có thể dùng dạng dấu bằng:

~~~bash
java --add-opens=com.acme.domain/com.acme.domain.api=com.acme.inspect \
     --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

Với nhiều named module đích, tách bằng dấu phẩy:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=com.acme.json,com.acme.orm \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

`com.acme.json` và `com.acme.orm` chỉ là tên minh họa. Trong dự án thực, xác định tên module của framework bằng descriptor trong artifact; không đoán từ package name hoặc tên thư viện trên Maven Central.

Nếu ứng dụng có lỗi compile-time do source import một public type từ package chưa export, `--add-opens` không phải cách sửa đúng. Cần xem `exports` hoặc `--add-exports` và readability.

## 7. Framework trên classpath và ALL-UNNAMED

Khi JSON serializer, ORM hoặc framework test chạy trên classpath, class của nó thuộc unnamed module. Thông báo lỗi thường có dạng:

~~~text
module com.acme.domain does not
"opens com.acme.domain.model" to unnamed module ...
~~~

Workaround:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED \
     --module-path mods \
     --class-path "lib/*" \
     -m com.acme.app/com.acme.app.Main
~~~

`ALL-UNNAMED` là đích đặc biệt của JVM option, cho phép unnamed modules deep reflection vào package đó.

Không viết:

~~~java
// Không phải cú pháp module-info.java hợp lệ:
opens com.acme.domain.model to ALL-UNNAMED;
~~~

Lý do: `ALL-UNNAMED` không phải tên named module. Với descriptor, có thể dùng `opens package;` không giới hạn nếu thực sự có chủ đích, hoặc chuyển framework sang một named module để dùng qualified opens khi khả thi.

`ALL-UNNAMED` có phạm vi rộng hơn việc mở cho một named framework cụ thể. Trong môi trường có nhiều library trên classpath, cân nhắc tác động và chỉ dùng phạm vi rộng khi cần.

## 8. Xác định đúng module thực hiện reflection

Luồng gọi có thể là:

~~~text
com.acme.app
    |
    v
com.acme.serializer
    |
    | Field.setAccessible(true)
    v
com.acme.domain.model.Customer
~~~

Đích của `opens` là **module serializer**, không nhất thiết là `com.acme.app`. App gọi serializer nhưng serializer mới gọi API reflection.

Kiểm tra module của target class:

~~~java
Class<?> target = Person.class;
Module owner = target.getModule();

System.out.println("Class: " + target.getName());
System.out.println("Package: " + target.getPackageName());
System.out.println("Module: " + owner.getName());
~~~

Nếu có thể truy cập class framework:

~~~java
Module caller = SomeFrameworkClass.class.getModule();
System.out.println(caller.getName());
~~~

`Module.getName()` trả `null` với unnamed module.

Khi không có API để import trực tiếp framework class, đọc stack trace: tìm class gọi `Field.setAccessible`, `Constructor.setAccessible` hoặc API reflection tương đương. Đó mới là điểm xuất phát để xác định named/unnamed caller.

## 9. Kiểm tra opens bằng Module API

Có thể dùng:

~~~java
Module domain = Person.class.getModule();
Module inspector = Main.class.getModule();
String pkg = Person.class.getPackageName();

System.out.println(
    "exported=" + domain.isExported(pkg, inspector)
);
System.out.println(
    "open=" + domain.isOpen(pkg, inspector)
);
~~~

Với fixture ban đầu, `exported` có thể là `true` nhưng `open` là `false`. Sau khi thêm đúng `opens` hoặc `--add-opens`, `open` phải thành `true` cho module inspector.

Hai overload cần phân biệt:

- `isOpen(String packageName)` kiểm tra package có được mở không giới hạn hay không.
- `isOpen(String packageName, Module other)` kiểm tra quyền mở package cho module cụ thể.

Đối với qualified opens, dùng overload có target module. `canRead` hay `isExported` có thể trả true nhưng không chứng minh `isOpen` true.

## 10. setAccessible và trySetAccessible

Lỗi thường được kích hoạt bởi:

~~~java
Field field = Person.class.getDeclaredField("name");
field.setAccessible(true);
~~~

Để chủ động kiểm tra quyền trước khi sử dụng:

~~~java
Field field = Person.class.getDeclaredField("name");

if (field.trySetAccessible()) {
    System.out.println(field.get(new Person("An")));
} else {
    System.out.println("Deep reflection is not allowed");
}
~~~

`trySetAccessible()` có thể trả `false` nếu không thể suppress access checks do giới hạn module. Nó giúp tránh một số trường hợp ném `InaccessibleObjectException` của `setAccessible(true)`, nhưng không sửa cấu hình JPMS.

`getDeclaredField` chỉ lấy thông tin metadata về field; tìm thấy field không có nghĩa caller đã được phép đọc/ghi giá trị private. Các ngoại lệ khác như `NoSuchFieldException` hoặc `IllegalAccessException` có nguyên nhân riêng.

Một thư viện có thể chọn public getter/factory khi không được deep reflection; một ORM bắt buộc truy cập field nội bộ có thể cần fail fast kèm hướng dẫn cấu hình cụ thể.

## 11. So sánh các lỗi có tên gần nhau

| Ngoại lệ/lỗi | Vấn đề thường gặp | Hướng kiểm tra |
|---|---|---|
| `InaccessibleObjectException` | Không cho phép suppress access checks qua reflection | `opens`, `--add-opens`, module caller |
| `IllegalAccessException` | Reflection không đủ quyền truy cập khi thao tác | Access modifiers, accessible flag |
| `IllegalAccessError` | Quyền truy cập lúc liên kết/thực thi bytecode không hợp lệ | Readability, exports, runtime artifacts |
| `NoSuchFieldException` | Field không tồn tại theo tên/class tra cứu | Tên field, API version, class thực tế |
| `ClassNotFoundException` | Không tìm thấy class qua loader | Module/class path, layer, loader |
| `FindException` | Module không được tìm trong resolution | Module name, path, runtime image |
| `ServiceConfigurationError` | Provider không được tìm hoặc khởi tạo đúng | `uses`, `provides`, service loading |

Không nên dùng `--add-opens` cho mọi lỗi runtime. Nếu không tìm thấy module thì phải giải quyết nguồn module; nếu public API không được export thì phải xử lý exports; nếu private reflection bị chặn thì opens mới là hướng kiểm tra thích hợp.

## 12. JDK internals và Java 17+

Các thư viện cũ có thể dùng reflection vào những package nội bộ JDK hoặc các lớp Java nền tảng. Một thông báo có thể nhắc tới:

~~~text
module java.base does not "opens java.lang" to unnamed module ...
~~~

Workaround tạm thời:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "lib/*" \
     com.acme.Main
~~~

Điều này có thể giúp một dependency cũ chạy trong lúc chuyển đổi, nhưng không nên coi là giải pháp bền vững.

Từ Java 17, strong encapsulation của các JDK internals được áp dụng chặt hơn. Tùy chọn cũ `--illegal-access` không còn là cách để phục hồi toàn bộ những quyền truy cập nội bộ trước kia. Ưu tiên nâng cấp framework, thư viện hoặc thay việc gọi internal API bằng public API được hỗ trợ.

Không thể sửa `module-info.java` của `java.base` như một module ứng dụng bình thường. Vì vậy `--add-opens java.base/...` có thể là biện pháp tương thích tạm thời, đồng thời cần ghi nhận rủi ro khi nâng JDK tiếp theo.

## 13. ORM, JSON và dependency injection

Framework có thể cần tạo entity qua constructor không public, truy cập field private, hoặc tạo proxy.

Ví dụ descriptor cho module sở hữu entity:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

Package `entity` được mở cho framework ORM, nhưng không được export như một API công khai cho các consumer khác.

Tên module thực tế của framework cần được kiểm tra:

~~~bash
jar --describe-module --file lib/framework.jar
~~~

Cùng một thư viện có thể ở classpath, module path như automatic module hoặc explicit named module, tùy packaging và runtime config. Mỗi trường hợp có cách xác định target opens khác nhau.

Đừng sao chép giá trị `com.acme.orm` vào cấu hình thật nếu nó không phải tên module chính xác. Nếu chỉ cần public constructor/getter ở exported package, nhiều framework có thể hoạt động mà không cần mở package sâu.

## 14. JUnit và test runtime

Trong project modular, JUnit engine hoặc mocking framework đôi khi dùng reflection vào test class không public thuộc named module.

Ví dụ:

~~~text
Test class: com.acme.app.internal.AppTest
Owner module: com.acme.app
Test engine: unnamed module on classpath
~~~

Có thể cần JVM option ở **đúng tiến trình chạy test**:

~~~bash
--add-opens com.acme.app/com.acme.app.internal=ALL-UNNAMED
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named('test', Test) {
    jvmArgs(
        '--add-opens',
        'com.acme.app/com.acme.app.internal=ALL-UNNAMED'
    )
}
~~~

Ví dụ Maven Surefire:

~~~xml
<configuration>
    <argLine>
        --add-opens com.acme.app/com.acme.app.internal=ALL-UNNAMED
    </argLine>
</configuration>
~~~

Cần kiểm tra các JVM options đã đến đúng forked test process. Thêm flag vào JVM chạy build tool chưa chắc làm forked JVM của test runner nhận được flag đó.

Nếu engine là named module, mở cho tên module thực tế thay vì dùng `ALL-UNNAMED`. Nếu test source cần nằm cùng module để truy cập package-private code, xem thêm `--patch-module`; nó giải quyết mục tiêu khác với `--add-opens`.

## 15. Cấu hình CI và container

Một lỗi phổ biến là local chạy được nhưng CI/container bị `InaccessibleObjectException`. Nguyên nhân có thể do JVM arguments không đồng nhất hoặc JDK version khác.

Checklist kiểm tra:

1. Java binary thực tế, vendor và version.
2. Startup command, Docker ENTRYPOINT hoặc process manager.
3. JVM options truyền **trước main class hoặc `-m`**.
4. Named module/classpath placement của framework.
5. Artifact module descriptor/JAR được deploy.
6. Danh sách `--add-opens` ở IDE, Gradle/Maven test, CI và production.
7. Readiness, integration test và đường code gây reflection thật.

Có thể xem command line của JVM đang chạy bằng công cụ JDK:

~~~bash
jcmd <pid> VM.command_line
~~~

`<pid>` là placeholder cần thay process ID.

Nếu chỉ chạy một smoke test đi qua public getters, không có bằng chứng luồng ORM/serialization không còn lỗi. Phải kiểm thử đúng chỗ đã từng gọi `setAccessible`.

## 16. ModuleLayer và quyền mở package động

Một số hệ plugin tạo ModuleLayer ở runtime. `ModuleLayer.Controller` có thể được dùng để điều chỉnh `opens` cho module mà controller quản lý:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parent),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer layer = controller.layer();

Module plugin = layer
    .findModule("com.acme.plugin")
    .orElseThrow();

controller.addOpens(
    plugin,
    "com.acme.plugin.internal",
    frameworkModule
);
~~~

Ví dụ giả định `frameworkModule` là đối tượng `Module` chính xác của framework, và package tồn tại trong plugin module. Không phải controller có quyền mở package tùy ý ở mọi module khác.

`Module.addOpens` cũng có quy tắc caller/ownership riêng: code từ module khác không được tự ý mở một package chưa cấp quyền của module nguồn. Khi thiết kế plugin, nên giới hạn runtime adjustments ở module do framework quản lý và chỉ mở package cần thiết.

## 17. Hướng chuyển đổi bền vững

Khi sửa lỗi, cân nhắc ba chiến lược theo thứ tự:

**A. Loại bỏ private reflection nếu không cần thiết.** Nếu có thể thiết kế public API, constructor, factory, adapter hoặc service interface ổn định, hãy dùng chúng thay cho truy cập trực tiếp private state.

**B. Mô tả opens đúng phạm vi trong descriptor do bạn sở hữu.** Khi reflection là hợp đồng tích hợp thật sự, dùng qualified `opens package to framework.module`. Không export package nội bộ chỉ để framework reflection.

**C. Giữ runtime workaround có kiểm soát.** Với dependency ngoài quyền sửa, dùng `--add-opens` đúng module/package/target; ghi rõ lý do, phiên bản thư viện bị ảnh hưởng và điều kiện loại bỏ khi nâng cấp.

Tránh các thói quen:

- Mở toàn bộ package của `java.base` hoặc mọi module trong ứng dụng chỉ vì một lỗi.
- Chuyển mọi module thành `open module` nếu chỉ một entity cần reflection.
- Thêm `--add-exports` với kỳ vọng nó thay `--add-opens`.
- Ghi thêm flags nhưng quên kiểm tra JVM thực tế chạy trong CI/container.
- Bỏ hết flags ở một lần nâng cấp mà không chạy integration tests.

Mỗi quyền mở cần có lý do cụ thể, phạm vi module/package cụ thể và người chịu trách nhiệm duy trì.

## 18. Quy trình chẩn đoán thực hành

Khi gặp `InaccessibleObjectException`:

1. **Đọc thông báo đầy đủ**, tìm source module, package và target module/unnamed module.
2. **Tìm caller trong stack trace**, xác định thư viện nào gọi reflection.
3. **Kiểm tra class identity**, đúng class/module và JAR như dự kiến.
4. **Xác định nhu cầu**, private reflection có bắt buộc hay có public API thay thế.
5. **Đo quyền**, dùng `Module.isOpen(package, targetModule)` nếu có thể.
6. **Sửa hẹp**, chọn qualified opens hoặc `--add-opens`.
7. **Đảm bảo module target tồn tại**, không đoán từ artifact filename.
8. **Áp dụng vào đúng JVM**, bao gồm test forks hoặc container.
9. **Chạy lại luồng gây lỗi**, không chỉ kiểm tra startup.
10. **Ghi lại phương án lâu dài**, loại bỏ workaround khi dependency hỗ trợ cách tích hợp ổn định.

Nếu sau khi mở package A lỗi chuyển sang package B, đừng lập tức thêm danh sách opens vô hạn. Có thể framework đang phụ thuộc quá sâu vào implementation nội bộ hoặc cấu hình reflection chưa đúng với kiến trúc JPMS.

## 19. Ma trận xử lý nhanh

| Tình huống | Giải pháp ưu tiên |
|---|---|
| Module ứng dụng do nhóm sở hữu cần reflection thường xuyên | Qualified `opens` trong `module-info.java` |
| Framework named module cần đọc private entity fields | `opens entity.package to framework.module` |
| Framework nằm trên classpath | Workaround `--add-opens source/pkg=ALL-UNNAMED` nếu cần |
| Framework cũ reflect vào internal JDK | Nâng cấp/thay API, chỉ mở package JDK có chọn lọc |
| Unit test engine cần reflection | Test-only `--add-opens`, đúng JVM test |
| Không import được public type | Kiểm tra `requires` và `exports` |
| Không tìm thấy module/class | Kiểm tra module path, class loader, ModuleLayer |
| Service provider không được tìm | Kiểm tra `uses`, `provides`, module resolution |
| Chỉ muốn xem metadata của member | Thường không cần opens cho truy vấn metadata đơn giản |
| Muốn truy cập private field | Cần quyền deep reflection phù hợp hoặc đổi thiết kế |

## 20. Ghi nhớ

**`InaccessibleObjectException` thường chỉ ra thiếu quyền deep reflection, không phải thiếu `public` hoặc `requires` đơn thuần.** `exports` cho phép API public được dùng qua module boundary; `opens` cho phép module đích thực hiện reflection vào thành viên không public trong package.

Khi kiểm soát module nguồn, nên dùng `opens pkg to target.module` với phạm vi nhỏ nhất. Khi chưa sửa descriptor được, dùng `--add-opens source.module/pkg=target.module`, hoặc `ALL-UNNAMED` nếu caller nằm trên classpath. Với internal JDK APIs, ưu tiên nâng cấp thư viện và public API thay vì duy trì quyền mở rộng lâu dài.

Để xác nhận khắc phục, hãy tìm chính xác source module/package và caller trong lỗi, kiểm tra trạng thái opens, áp dụng quyền vào đúng JVM process rồi chạy lại luồng code reflection thật. Mục tiêu không phải mở mọi package cho tiện, mà là **mở đúng package, đúng module cần truy cập, trong đúng môi trường và với lý do kỹ thuật rõ ràng**.
