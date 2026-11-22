# Kiểm chứng ranh giới module và reflection trong Java 17

Java Platform Module System (JPMS) đặt ranh giới rõ ràng giữa các module: module nào được đọc module nào, package nào được công bố cho truy cập thông thường và package nào được mở để framework dùng deep reflection. Khi ứng dụng chạy trên Java 17, việc một class hoặc private member có thể được tìm thấy bằng reflection không có nghĩa chương trình được phép đọc, sửa hoặc gọi thành phần đó.

Bài thực hành này dựng hai named modules để kiểm chứng trực tiếp các ranh giới:

- Module com.example.model cung cấp public API và giữ một field private.
- Module com.example.inspector đọc public API rồi thử truy cập field private bằng reflection.
- Ban đầu package chỉ được exports, vì vậy public API hoạt động nhưng deep reflection bị chặn.
- Sau đó mở đúng package cho đúng module bằng qualified opens, rồi kiểm chứng lại.
- Cuối cùng dùng --add-opens lúc khởi chạy để kiểm tra cùng hành vi mà không sửa module descriptor.

Mục tiêu là biết cách kiểm tra quyền truy cập trong runtime Java 17, đọc đúng lỗi và lựa chọn phạm vi mở package nhỏ nhất cần thiết.

## 1. Ba điều kiện của truy cập module

Để một module dùng một type trong module khác, cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi | Cách khai báo thường gặp |
| --- | --- | --- |
| Readability | Module gọi có đọc được module chứa type không? | requires |
| Export | Package có công bố public type/member cho module gọi không? | exports |
| Open | Package có cho phép deep reflection vào member không public không? | opens |

Ba quyền này phục vụ các mục đích khác nhau:

- requires tạo quan hệ đọc module. Nó không tự công bố package.
- exports cho phép truy cập thông thường tới public type và public member trong package được export. Nó không mở private field hoặc private method.
- opens cho phép reflection sâu ở runtime vào package. Nó không tự cho phép source code import public type từ package đó như một API đã export.

Ví dụ:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.persistence to com.example.orm;
}
~~~

Trong cấu hình này, module khác có thể gọi public API của com.example.model.api nếu nó đọc được module model. Riêng module com.example.orm được phép deep reflection vào package persistence. Các module khác không nhận quyền mở đó.

### exports không đồng nghĩa opens

Đây là khác biệt cần kiểm chứng bằng thực nghiệm:

| Khai báo | Import public type ở compile time | Gọi public API | Deep reflection vào private member |
| --- | --- | --- | --- |
| Không export, không open | Không | Không | Không |
| exports p | Có | Có | Không |
| opens p | Không | Không qua truy cập thông thường | Có ở runtime |
| exports p; opens p; | Có | Có | Có |
| exports p to m; opens p to m; | Chỉ module được chỉ định | Có với module được chỉ định | Có với module được chỉ định |

Một package có thể vừa export vừa open, nhưng chỉ nên làm vậy khi có hai nhu cầu độc lập: public API cho code gọi và deep reflection cho framework.

## 2. Chuẩn bị project hai module

Tạo cấu trúc thư mục:

~~~text
module-reflection-lab/
  src/
    com.example.model/
      module-info.java
      com/example/model/api/Account.java
    com.example.inspector/
      module-info.java
      com/example/inspector/Main.java
~~~

Đặt hai module trên module source path. Mỗi thư mục module có module-info.java riêng.

### Module com.example.model

File src/com.example.model/module-info.java:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Module chỉ export package API. Chưa có khai báo opens.

File src/com.example.model/com/example/model/api/Account.java:

~~~java
package com.example.model.api;

public final class Account {
    private int balance = 1250;

    public int balance() {
        return balance;
    }
}
~~~

Class Account có public method balance() và private field balance. Public method là hợp đồng mà module khác được dùng; field là trạng thái nội bộ.

### Module com.example.inspector

File src/com.example.inspector/module-info.java:

~~~java
module com.example.inspector {
    requires com.example.model;
}
~~~

Khai báo requires cho phép inspector đọc module model. Module model đã export package com.example.model.api, vì vậy inspector có thể import class Account.

File src/com.example.inspector/com/example/inspector/Main.java:

~~~java
package com.example.inspector;

import com.example.model.api.Account;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account();

        // Truy cập public API theo hợp đồng của module.
        System.out.println("Public balance = " + account.balance());

        Field field = Account.class.getDeclaredField("balance");
        System.out.println("canAccess before = "
                + field.canAccess(account));

        boolean opened = field.trySetAccessible();
        System.out.println("trySetAccessible = " + opened);

        if (opened) {
            System.out.println("canAccess after = "
                    + field.canAccess(account));
            System.out.println("Private balance = "
                    + field.get(account));
        } else {
            System.out.println(
                    "Deep reflection is not permitted for this package");
        }
    }
}
~~~

Ví dụ dùng getDeclaredField() để lấy metadata về field khai báo trực tiếp trong class. Việc tìm thấy Field không tự cấp quyền đọc field. trySetAccessible() kiểm tra liệu quyền truy cập sâu có thể được bật trong ngữ cảnh module hiện tại hay không.

## 3. Biên dịch và chạy với package chỉ được export

Đứng tại thư mục module-reflection-lab, biên dịch cả hai module:

~~~bash
javac --release 17 \
      --module-source-path src \
      -d out \
      -m com.example.model,com.example.inspector
~~~

Chạy module inspector:

~~~bash
java --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

Kết quả dự kiến:

~~~text
Public balance = 1250
canAccess before = false
trySetAccessible = false
Deep reflection is not permitted for this package
~~~

Public API hoạt động vì:

1. com.example.inspector đọc com.example.model qua requires.
2. com.example.model export package com.example.model.api.
3. Account và method balance() là public.

Deep reflection bị từ chối vì package chỉ được export, chưa được open cho module inspector. Điều này chứng minh exports không mở private member.

### Vì sao getDeclaredField() vẫn thành công?

getDeclaredField("balance") trả về metadata của field được khai báo trong class. Nó không đồng nghĩa caller đã được quyền truy cập giá trị field. Quyền truy cập được kiểm tra khi đọc/ghi bằng Field.get(), Field.set() hoặc khi yêu cầu bỏ qua access check.

Không nên viết logic dựa trên giả định rằng:

~~~java
Field field = Account.class.getDeclaredField("balance");
Object value = field.get(account);
~~~

sẽ luôn thành công chỉ vì getDeclaredField() không ném exception. Khi chưa được cấp quyền, thao tác get() có thể ném IllegalAccessException.

## 4. Phân biệt canAccess, trySetAccessible và setAccessible

Các API này có nhiệm vụ khác nhau:

| API | Ý nghĩa | Khi không được phép |
| --- | --- | --- |
| canAccess(object) | Kiểm tra member có thể được truy cập theo access state hiện tại không | Trả false |
| trySetAccessible() | Thử bật quyền bỏ qua language access check nếu module boundary cho phép | Trả false |
| setAccessible(true) | Yêu cầu bật quyền truy cập sâu | Có thể ném InaccessibleObjectException |
| setAccessible(false) | Tắt trạng thái accessible override | Khôi phục kiểm tra truy cập thông thường |

Với field instance, truyền object đích cho canAccess. Với static field, truyền null. Nếu truyền sai dạng, API có thể ném IllegalArgumentException.

### Kiểm chứng setAccessible(true) khi package chưa open

Có thể thay phần thử truy cập trong Main bằng:

~~~java
try {
    field.setAccessible(true);
    System.out.println("setAccessible succeeded");
    System.out.println("Private balance = " + field.get(account));
} catch (java.lang.reflect.InaccessibleObjectException ex) {
    System.out.println("Deep reflection denied: "
            + ex.getMessage());
}
~~~

Với module model chỉ export package, setAccessible(true) đối với private field có thể ném InaccessibleObjectException. Đây là runtime exception cho biết module system không cho phép mở quyền truy cập sâu theo yêu cầu.

trySetAccessible() phù hợp khi ứng dụng muốn kiểm tra khả năng mở quyền mà không dùng exception làm luồng điều khiển thông thường. Nếu trả false, framework nên báo lỗi cấu hình rõ ràng hoặc dùng public API thay thế.

### Đừng nhầm metadata với quyền truy cập

Reflection có thể liệt kê method hoặc field non-public trong một số trường hợp, nhưng quyền gọi/đọc/sửa vẫn phải thỏa access check. Các thao tác sau đều có thể thất bại nếu package/module không cho phép:

- Field.get() và Field.set().
- Method.invoke().
- Constructor.newInstance().
- MethodHandles.privateLookupIn().

## 5. Mở đúng package cho đúng module

Nếu framework thật sự cần deep reflection vào Account, hãy sửa module descriptor của module sở hữu package.

File src/com.example.model/module-info.java:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.inspector;
}
~~~

Đây là qualified opens. Package com.example.model.api chỉ được mở cho module com.example.inspector.

Biên dịch lại:

~~~bash
javac --release 17 \
      --module-source-path src \
      -d out \
      -m com.example.model,com.example.inspector
~~~

Chạy lại:

~~~bash
java --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

Kết quả dự kiến:

~~~text
Public balance = 1250
canAccess before = false
trySetAccessible = true
canAccess after = true
Private balance = 1250
~~~

canAccess ban đầu vẫn là false vì field private chưa được bật accessible override. Sau khi trySetAccessible() thành công, access check thông thường được bỏ qua cho đối tượng Field đó và canAccess trả true.

### Vì sao nên dùng qualified opens?

Khai báo:

~~~java
opens com.example.model.api to com.example.inspector;
~~~

giới hạn quyền deep reflection cho module cần thiết. Nếu mở package cho tất cả module:

~~~java
opens com.example.model.api;
~~~

thì mọi module phù hợp có thể deep-reflect vào package đó. Phạm vi rộng hơn làm giảm tính đóng gói và khiến việc thay đổi private implementation khó kiểm soát hơn.

Nếu framework ORM là module com.example.orm, hãy mở cho đúng module ORM. Không mở cho module inspector chỉ vì ví dụ lab dùng tên đó; tên module đích trong sản phẩm phải là module thực sự gọi reflection.

## 6. Kiểm chứng bằng --add-opens lúc khởi chạy

Có thể thử quyền mở package mà không sửa module-info.java. Trả module descriptor về cấu hình chỉ có exports, biên dịch lại rồi chạy:

~~~bash
java --module-path out \
     --add-opens com.example.model/com.example.model.api=com.example.inspector \
     -m com.example.inspector/com.example.inspector.Main
~~~

Kết quả deep reflection tương tự khi khai báo qualified opens trong descriptor. Tùy chọn --add-opens tạo một mở package ở runtime cho module đích được chỉ định.

Điều này hữu ích khi:

- Chẩn đoán framework cũ cần deep reflection.
- Thử xác nhận một package/module boundary có phải nguyên nhân gây lỗi.
- Cung cấp workaround có phạm vi hẹp trong giai đoạn chuyển tiếp.

Nếu workaround trở thành cấu hình triển khai lâu dài, cần ghi lại module nguồn, package, module đích, lý do và kế hoạch bỏ. Với module ứng dụng do mình sở hữu, khai báo qualified opens trong module-info.java thường dễ review và quản lý hơn việc tích lũy nhiều JVM flags.

### Caller nằm trên classpath

Code chạy trên classpath thuộc unnamed module. Nếu một ứng dụng classpath cần deep reflection vào package của named module, target có thể là ALL-UNNAMED:

~~~bash
java --module-path mods \
     --add-modules com.example.model \
     --add-opens com.example.model/com.example.model.api=ALL-UNNAMED \
     -cp app.jar \
     com.example.Main
~~~

ALL-UNNAMED mở package cho các unnamed modules. Đây là phạm vi rộng hơn một qualified open tới một named module cụ thể; chỉ dùng khi caller thực sự chạy trên classpath và cần quyền đó.

--add-opens là tùy chọn runtime. Nó không làm package trở thành package được export để source code khác import public type trong quá trình biên dịch.

## 7. Kiểm tra ranh giới bằng API Module

Java cung cấp API runtime để hỏi module có đọc module khác, export package hay open package cho module cụ thể không.

Thêm đoạn sau vào Main:

~~~java
Module sourceModule = Account.class.getModule();
Module callerModule = Main.class.getModule();
String packageName = "com.example.model.api";

System.out.println("Source module = " + sourceModule.getName());
System.out.println("Caller module = " + callerModule.getName());
System.out.println("Caller can read source = "
        + callerModule.canRead(sourceModule));
System.out.println("Package exported to caller = "
        + sourceModule.isExported(packageName, callerModule));
System.out.println("Package open to caller = "
        + sourceModule.isOpen(packageName, callerModule));
~~~

Khi module model chỉ export package, kết quả dự kiến:

~~~text
Caller can read source = true
Package exported to caller = true
Package open to caller = false
~~~

Sau khi thêm qualified opens cho com.example.inspector:

~~~text
Caller can read source = true
Package exported to caller = true
Package open to caller = true
~~~

Các phương thức liên quan:

| API | Công dụng |
| --- | --- |
| Module.getName() | Lấy tên module; unnamed module có tên null |
| Module.canRead(other) | Kiểm tra quan hệ readability |
| Module.isExported(packageName, other) | Kiểm tra package được export cho module đích |
| Module.isOpen(packageName, other) | Kiểm tra package được open cho deep reflection với module đích |
| Class.getModule() | Lấy module chứa class |

Đây là cách kiểm tra trực tiếp trong ứng dụng hoặc diagnostic code. Kết quả isExported() và isOpen() cần được diễn giải theo đúng module đích; một package có thể mở cho module A nhưng không mở cho module B.

## 8. Kiểm chứng MethodHandles.privateLookupIn

Reflection field không phải cách duy nhất để truy cập động. MethodHandles cung cấp lookup có quyền truy cập và VarHandle cho thao tác trên field.

Thêm ví dụ sau trong module inspector:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Account.class,
                MethodHandles.lookup());

VarHandle balanceHandle = privateLookup.findVarHandle(
        Account.class,
        "balance",
        int.class);

int value = (int) balanceHandle.get(account);
System.out.println("Balance through VarHandle = " + value);
~~~

Để đoạn code chạy, package com.example.model.api phải được open cho module inspector. Nếu package chưa open, privateLookupIn() có thể ném IllegalAccessException.

privateLookupIn() không phải lối tắt vượt qua JPMS. Caller phải có quyền đọc module target, và package target phải được mở cho module caller theo quy tắc module access.

Nếu chỉ cần gọi public method, dùng publicLookup() hoặc gọi trực tiếp API công khai. Không yêu cầu private lookup khi public API đã đáp ứng nhu cầu.

## 9. Kiểm tra package không được export

Thử thu hẹp module model:

~~~java
module com.example.model {
    // Không export com.example.model.api
}
~~~

Lúc này module inspector không thể biên dịch source có:

~~~java
import com.example.model.api.Account;
~~~

vì package không được export cho module inspector. Đây là lỗi truy cập API ở compile time.

Nếu package được opens nhưng không exports, quyền deep reflection ở runtime không biến package thành public compile-time API. Framework có thể dùng cơ chế runtime phù hợp để làm việc với type mà nó được cung cấp, nhưng code module khác vẫn không được import type đó như một API công khai.

### Khi nào dùng --add-exports?

Nếu cần kiểm tra một package public type không được export, --add-exports có thể bổ sung quyền truy cập thông thường cho module đích:

~~~bash
javac --release 17 \
      --module-path mods \
      --add-exports com.example.model/com.example.model.internal=com.example.inspector \
      ...
~~~

Khi chạy, cũng cần quyền tương ứng:

~~~bash
java --module-path mods \
     --add-exports com.example.model/com.example.model.internal=com.example.inspector \
     -m com.example.inspector/com.example.inspector.Main
~~~

--add-exports dành cho truy cập tới public type/member trong package được export bổ sung. Nó không cho phép truy cập private member. Nếu mục tiêu là deep reflection, cần opens hoặc --add-opens.

Không dùng --add-exports để biến package JDK nội bộ thành API ổn định. Nếu một ứng dụng phụ thuộc package jdk.internal.*, hãy tìm API công khai hoặc thư viện được hỗ trợ thay thế.

## 10. open module và phạm vi mở rộng

Có thể khai báo:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

open module mở tất cả package của module cho deep reflection lúc runtime. Nó không tự export tất cả package cho truy cập Java thông thường.

Đây là phạm vi rộng hơn nhiều so với:

~~~java
opens com.example.model.api to com.example.inspector;
~~~

Trong ứng dụng thật, ưu tiên qualified opens cho package và module cụ thể. Chỉ dùng open module khi có yêu cầu framework rộng, đã hiểu tác động và chấp nhận việc module không còn đóng các package đối với deep reflection.

## 11. Đọc và phân loại lỗi reflection

Các lỗi phổ biến khi kiểm chứng module boundary:

| Exception/lỗi | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| InaccessibleObjectException | Không thể bật accessible override do module/package không mở | Xác định module nguồn, package và caller; dùng public API hoặc mở package có giới hạn |
| IllegalAccessException | Thao tác reflection/MethodHandles không có quyền truy cập | Kiểm tra exports/opens, readability và access level |
| NoSuchFieldException | Field không tồn tại trong class được hỏi | Xác minh tên/type; không dựa vào private field của implementation |
| NoSuchMethodException | Method/signature không tồn tại | Kiểm tra API version và chữ ký method |
| ClassNotFoundException | Không tìm thấy class theo class loader/module path | Kiểm tra module resolution, classpath và tên class |
| NoClassDefFoundError | Class cần khi chạy không được nạp hoặc initialization thất bại | Kiểm tra dependency/runtime và nguyên nhân gốc trong log |
| InvocationTargetException | Method được invoke đã ném exception bên trong | Xem getCause() để tìm lỗi từ method đích |
| IllegalArgumentException từ canAccess | Truyền receiver không phù hợp, ví dụ instance/static sai | Dùng object cho instance member và null cho static member |

### Thông tin cần ghi khi báo lỗi

Khi framework báo không truy cập được member, ghi:

- Tên class và package chứa member.
- Module của class đích.
- Module của caller.
- Tên member và loại member (field/method/constructor).
- Access modifier.
- canRead, isExported và isOpen theo caller.
- JDK vendor/version.
- Stack trace đầy đủ và JVM arguments.

Thông tin này giúp phân biệt lỗi module boundary với lỗi thiếu class, sai phiên bản dependency hoặc lỗi logic bên trong method được invoke.

## 12. Công cụ kiểm tra module ở ngoài runtime

Ngoài API Module, có thể dùng công cụ JDK 17 để quan sát module graph và artifact.

### Hiển thị module resolution

~~~bash
java --show-module-resolution \
     --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

Tùy chọn này hiển thị các module được resolve khi khởi chạy. Nó giúp phát hiện module không được tìm thấy hoặc quan hệ phụ thuộc khác với dự kiến.

### Xem descriptor của JAR

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Lệnh cho biết JAR có module descriptor hay được xem là automatic module, cùng các package và quan hệ được công bố theo metadata của artifact.

### Kiểm tra dependency graph

~~~bash
jdeps --module-path out --check com.example.inspector
~~~

jdeps hỗ trợ phân tích dependency giữa module và phát hiện một số vấn đề về module graph. Dùng kết quả cùng module descriptor và runtime test; phân tích tĩnh không chứng minh mọi reflective access ở runtime đều hợp lệ.

### Tìm dependency vào JDK internals

~~~bash
jdeps --jdk-internals application.jar
~~~

Tùy chọn này giúp tìm một số tham chiếu tĩnh tới internal API của JDK. Reflection theo tên chuỗi hoặc dynamic loading có thể không được phát hiện đầy đủ, nên cần kết hợp tìm kiếm source và test.

## 13. Kiểm chứng từ classpath và unnamed module

Nhiều ứng dụng vẫn chạy code trên classpath. Code đó thuộc unnamed module. Khi tương tác với named module:

- Caller cần đọc được module chứa type.
- Package vẫn phải được export nếu code cần truy cập public type/member theo cách thông thường.
- Deep reflection vẫn cần package được open cho caller.
- ALL-UNNAMED là target dùng khi muốn mở package cho các unnamed modules.

Ví dụ:

~~~bash
java --module-path mods \
     --add-opens com.example.model/com.example.model.api=ALL-UNNAMED \
     -cp app.jar \
     com.example.Main
~~~

Nếu chỉ muốn mở cho một named module, chỉ định tên module đó thay vì ALL-UNNAMED. Đây là cách giảm phạm vi quyền và làm cấu hình dễ kiểm soát hơn.

JAR đặt trên module path nhưng không có module-info.class có thể được xem là automatic module. Automatic module có quy tắc export và readability rộng hơn named module được thiết kế chặt chẽ. Khi kiểm chứng ranh giới module, dùng named modules với descriptor rõ ràng để kết quả không bị che bởi hành vi tự động của dependency.

## 14. Kiểm tra tương thích framework dùng reflection

Framework ORM, serializer, dependency injection, mapper, mocking và test engine thường dùng reflection. Khi chuyển một ứng dụng sang Java 17, cần kiểm tra framework đang truy cập package nào và vì lý do gì.

Quy trình:

1. Chạy test bằng JDK 17 đúng vendor/version mục tiêu.
2. Tìm lỗi InaccessibleObjectException và IllegalAccessException.
3. Xác định package đích thuộc ứng dụng, thư viện bên thứ ba hay JDK.
4. Nâng framework lên phiên bản hỗ trợ Java 17.
5. Ưu tiên constructor, accessor, annotation hoặc SPI được framework công bố.
6. Nếu package ứng dụng cần deep reflection, thêm qualified opens đúng package cho module framework.
7. Nếu tạm dùng --add-opens, ghi lại phạm vi, lý do và kế hoạch bỏ.
8. Chạy lại test trên đúng module path/classpath và runtime production.

Nếu lỗi xảy ra khi framework truy cập private member của JDK, không tự động mở toàn bộ java.base. Tìm phiên bản framework mới đã hỗ trợ strong encapsulation hoặc thay cơ chế tích hợp.

### Phân biệt package của ứng dụng và package của JDK

Với package ứng dụng, nhóm phát triển kiểm soát module-info.java và có thể quyết định mở một package cho framework.

Với package JDK, ứng dụng không kiểm soát descriptor của module hệ thống. --add-opens có thể tạo workaround runtime có phạm vi rõ ràng, nhưng nó không biến private implementation thành API ổn định. Hãy ưu tiên API Java SE được công bố.

## 15. Viết test tự động cho ranh giới module

Các kiểm chứng có thể được đưa vào test suite của ứng dụng modular. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.model.api.Account;
import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

class ModuleBoundaryTest {
    @Test
    void apiIsExportedButPrivateStateIsNotOpen() throws Exception {
        Account account = new Account();
        Module source = Account.class.getModule();
        Module caller = getClass().getModule();

        assertTrue(caller.canRead(source));
        assertTrue(source.isExported(
                "com.example.model.api", caller));
        assertFalse(source.isOpen(
                "com.example.model.api", caller));

        Field balance = Account.class.getDeclaredField("balance");
        assertFalse(balance.canAccess(account));
        assertFalse(balance.trySetAccessible());
    }
}
~~~

Test này xác nhận cấu hình module chưa mở package cho caller. Nếu module descriptor có qualified opens, kỳ vọng của test phải đổi tương ứng. Không nên để test khẳng định package luôn đóng nếu thiết kế thực tế chủ đích mở package cho ORM.

Một test khác có thể xác nhận package được mở:

~~~java
@Test
void persistencePackageIsOpenToOrm() {
    Module source = Account.class.getModule();
    Module orm = OrmEntryPoint.class.getModule();

    assertTrue(source.isOpen(
            "com.example.model.persistence", orm));
}
~~~

Trong ví dụ, OrmEntryPoint là class thuộc module ORM thật. Test nên đặt trong module có quyền truy cập phù hợp và kiểm tra đúng package mà framework cần.

### Không kiểm tra private field như một hợp đồng nghiệp vụ

Test module boundary có mục tiêu xác nhận cấu hình đóng gói. Nó không nên làm cho mọi private field của domain object trở thành một phần hợp đồng của test. Nếu logic nghiệp vụ cần xác minh, ưu tiên public behavior. Chỉ kiểm tra deep reflection ở test khi đang kiểm tra chính tích hợp framework hoặc module configuration.

## 16. Checklist thực hành

Khi kiểm chứng module boundary và reflection:

1. Xác định module nguồn, module caller và package chứa class.
2. Xác nhận caller có readability tới module nguồn.
3. Xác nhận package có được export nếu source cần gọi public API.
4. Kiểm tra Module.isExported() và Module.isOpen() theo đúng caller.
5. Dùng getDeclaredField()/getDeclaredMethod() để lấy metadata, nhưng không coi việc tìm thấy member là quyền truy cập.
6. Dùng canAccess() để kiểm tra access state.
7. Dùng trySetAccessible() để kiểm tra deep reflection mà không dựa vào exception làm luồng điều khiển.
8. Dùng qualified opens cho đúng package và đúng framework module khi thật sự cần.
9. Dùng --add-opens như cấu hình runtime có phạm vi rõ ràng để chẩn đoán hoặc chuyển tiếp.
10. Dùng MethodHandles.privateLookupIn() chỉ khi package được mở và cần lookup có quyền riêng.
11. Phân biệt --add-exports cho public access với --add-opens cho deep reflection.
12. Chạy test trên JDK 17 và module path giống production.
13. Không mở rộng JDK internals như giải pháp mặc định; nâng framework hoặc dùng API công khai.

## 17. Kết luận thực hành

Một module có thể công bố public API mà vẫn giữ private implementation đóng. requires cho biết module nào đọc module nào, exports công bố public API và opens cho phép deep reflection ở runtime. Các API Module, AccessibleObject và MethodHandles cho phép kiểm chứng những quyền này ngay trong Java 17.

Khi framework cần truy cập sâu, hãy mở đúng package cho đúng module và xác nhận bằng test. Nếu dùng --add-opens, hãy coi đó là một phần cấu hình runtime có chủ sở hữu và lý do rõ ràng. Cách làm này giữ được ranh giới module, giúp phát hiện sớm lỗi reflection và tránh phụ thuộc không cần thiết vào implementation nội bộ của JDK.

## Tài liệu tham khảo Java 17

- [Java Language Specification, Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html)
- [Module API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [AccessibleObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [MethodHandles API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [javac options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
