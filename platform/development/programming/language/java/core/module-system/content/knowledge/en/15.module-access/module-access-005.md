# Reflection access khác với compile-time access

Một đoạn code Java có thể biên dịch thành công nhưng thất bại khi dùng reflection. Ngược lại, Reflection API có thể tìm thấy metadata của một thành viên nhưng không được phép đọc, ghi hoặc gọi thành viên đó. Hai tình huống này xảy ra vì Java kiểm tra quyền truy cập ở những thời điểm và theo những quy tắc khác nhau.

Khi làm việc với Java Platform Module System (JPMS, từ Java 9), cần phân biệt ba lớp quyền:

1. **Compile-time access:** trình biên dịch có cho phép source code tham chiếu kiểu, constructor, method hoặc field hay không.
2. **Runtime access thông thường:** JVM có cho phép bytecode truy cập thành viên theo quy tắc Java và module hay không.
3. **Reflective access:** Reflection API có được phép thực hiện thao tác trên thành viên hay không; deep reflection vào thành viên không public còn phụ thuộc package có được mở (**opens**) hay không.

## 1. Compile-time access được kiểm tra khi biên dịch

Compile-time access là quyền truy cập mà **javac** kiểm tra từ source code. Nó dựa trên quy tắc truy cập của ngôn ngữ Java:

- **public:** có thể truy cập từ nơi phù hợp nếu kiểu chứa thành viên cũng truy cập được.
- **protected:** có thể truy cập trong cùng package hoặc theo quy tắc subclass.
- **package-private** (không ghi modifier): chỉ truy cập trong cùng package.
- **private:** chỉ truy cập trong phạm vi lớp khai báo và các trường hợp đặc biệt do ngôn ngữ quy định, chẳng hạn nestmates.

Với named module, việc truy cập giữa các module còn cần hai điều kiện:

- Module gọi phải **đọc được** module chứa API, thông thường thông qua **requires**.
- Package chứa API phải được module cung cấp **export** thông qua **exports**.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.domain;
}
~~~

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Nếu **com.example.app** import một lớp **public** trong **com.example.domain.api**, cả quan hệ đọc module và export package đều cần hợp lệ. Nếu thiếu **requires**, javac có thể báo module không đọc module đích. Nếu package chưa được export, compiler có thể báo package không được hiển thị hoặc không được export.

**opens** không thay thế **exports** cho source code. Một package được mở để reflection không vì thế mà trở thành package có thể import và sử dụng trực tiếp trong code Java thông thường.

## 2. Reflection access được kiểm tra ở runtime

Reflection cho phép chương trình khám phá lớp và thành viên khi ứng dụng đang chạy, ví dụ:

- **Class.forName(...)** để tìm lớp theo tên.
- **getMethod(...)**, **getDeclaredMethod(...)** để tìm method.
- **getField(...)**, **getDeclaredField(...)** để tìm field.
- **Constructor.newInstance(...)**, **Method.invoke(...)**, **Field.get(...)** hoặc **Field.set(...)** để thao tác với thành viên.

Điểm quan trọng: **tìm thấy một thành viên không đồng nghĩa với việc được phép truy cập thành viên đó**.

Ví dụ:

~~~java
Field field = User.class.getDeclaredField("passwordHash");
~~~

Lệnh trên yêu cầu Reflection API tìm field có tên **passwordHash** được khai báo trực tiếp trong **User**. Nó không tự cấp quyền đọc field private. Khi gọi **field.get(user)**, reflection vẫn phải kiểm tra quyền truy cập.

| API | Ý nghĩa | Có tự vượt qua access check không? |
| --- | --- | --- |
| **getMethod(...)** | Tìm public method, kể cả method kế thừa phù hợp | Không |
| **getDeclaredMethod(...)** | Tìm method được khai báo trực tiếp trong lớp, kể cả method không public | Không |
| **getField(...)** | Tìm public field, kể cả field kế thừa phù hợp | Không |
| **getDeclaredField(...)** | Tìm field khai báo trực tiếp, kể cả field không public | Không |
| **Method.invoke(...)** | Gọi method qua reflection | Không; vẫn cần quyền truy cập |
| **Field.get(...) / set(...)** | Đọc/ghi field qua reflection | Không; vẫn cần quyền truy cập |
| **trySetAccessible()** | Thử bật chế độ bỏ qua một số kiểm tra ngôn ngữ | Chỉ thành công khi điều kiện module cho phép |
| **setAccessible(true)** | Yêu cầu bật chế độ bỏ qua access check | Có thể bị từ chối |

Reflection API có thể cung cấp metadata về một thành viên mà không cấp quyền thực thi thao tác trên thành viên ấy. Vì vậy, đừng xem việc **getDeclaredField** hoặc **getDeclaredMethod** chạy thành công là bằng chứng package đã được mở.

## 3. Phân biệt exports và opens

Trong JPMS, **exports** và **opens** phục vụ hai mục đích khác nhau.

| Khai báo | Cho phép điều gì? | Dùng ở thời điểm nào? |
| --- | --- | --- |
| **exports p;** | Module khác dùng các kiểu và thành viên public của package p theo quy tắc truy cập Java | Compile time và runtime |
| **exports p to m;** | Chỉ module m được dùng API public của package p | Compile time và runtime |
| **opens p;** | Cho phép deep reflection vào các kiểu/thành viên của package p từ module khác | Runtime |
| **opens p to m;** | Chỉ module m được deep reflection vào package p | Runtime |
| **open module x { ... }** | Mở tất cả package của module cho deep reflection từ module khác | Runtime |

Ví dụ module domain công khai API và chỉ mở model package cho một framework:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.mapper;
}
~~~

Trong cấu hình này:

- Code của module khác có thể import các lớp **public** trong **com.example.domain.api** nếu có quan hệ đọc module phù hợp.
- Framework thuộc **com.example.mapper** có thể dùng deep reflection vào package **com.example.domain.model**.
- Package **com.example.domain.model** không tự trở thành package có thể import trực tiếp chỉ vì có **opens**.
- Module không được nêu trong qualified **opens** không nhận quyền deep reflection đó.

Nếu khai báo **open module com.example.domain { ... }**, tất cả package của module được mở cho reflection. Một open module vẫn có thể dùng **exports** để công khai API cho truy cập thông thường; **open** không biến mọi package thành API public có thể import. Trong một open module, không khai báo thêm các chỉ thị **opens** riêng lẻ vì toàn bộ package đã được mở.

**Quy tắc ghi nhớ:** **exports** dành cho truy cập API public; **opens** dành cho deep reflection. Một package có thể cần cả hai nếu vừa là API được gọi trực tiếp, vừa chứa thành viên nội bộ mà framework cần đọc bằng reflection.

## 4. Java access modifier và module access là hai lớp kiểm tra

Access modifier và module declaration bổ sung cho nhau. **public** không có nghĩa là mọi module đều có thể truy cập; **private** cũng không thể được bỏ qua tùy ý chỉ bằng reflection.

Ví dụ:

~~~java
package com.example.domain.model;

public class User {
    public String displayName = "An";
    private String passwordHash = "hash-value";
}
~~~

Giả sử package **com.example.domain.model** không được export hoặc open cho module gọi.

- **displayName** có modifier **public**, nhưng module khác vẫn không thể truy cập nó như API public thông thường nếu package không được export.
- **passwordHash** có modifier **private**; truy cập trực tiếp từ lớp ngoài vốn không hợp lệ theo quy tắc Java.
- **getDeclaredField("passwordHash")** có thể tìm metadata của field, nhưng không cấp quyền đọc field.
- **setAccessible(true)** có thể bị từ chối vì package không mở cho module gọi.

Nếu package được export, code bên ngoài có thể dùng thành viên public hợp lệ, nhưng điều đó **không** tự cho phép reflection truy cập private field. Nếu package được open, deep reflection có thể được cho phép, nhưng code Java thông thường vẫn không được import package ấy nếu package chưa export.

## 5. Ví dụ: public reflection và deep reflection

Giả sử có hai module:

~~~text
com.example.domain/
  module-info.java
  com/example/domain/api/UserView.java
  com/example/domain/model/UserRecord.java

com.example.framework/
  module-info.java
  com/example/framework/Inspector.java
~~~

Descriptor của module domain:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.framework;
}
~~~

Lớp API public:

~~~java
package com.example.domain.api;

public class UserView {
    public String label() {
        return "User";
    }
}
~~~

Lớp model có field private:

~~~java
package com.example.domain.model;

public class UserRecord {
    private String internalId = "U-100";

    public String getInternalId() {
        return internalId;
    }
}
~~~

Module framework:

~~~java
module com.example.framework {
    requires com.example.domain;
}
~~~

Đoạn code sau có thể gọi public API đã export:

~~~java
UserView view = new UserView();
System.out.println(view.label());
~~~

Còn nếu framework cần đọc **internalId** qua reflection:

~~~java
package com.example.framework;

import com.example.domain.model.UserRecord;
import java.lang.reflect.Field;

public class Inspector {
    public static void main(String[] args) throws Exception {
        UserRecord user = new UserRecord();

        Field field = UserRecord.class.getDeclaredField("internalId");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Không được phép deep reflection vào internalId"
            );
        }

        Object value = field.get(user);
        System.out.println(value);
    }
}
~~~

Ví dụ này minh họa quyền deep reflection do **opens com.example.domain.model to com.example.framework** cấp. Nếu bỏ dòng **opens**, việc tìm field có thể vẫn thành công, nhưng **trySetAccessible()** không thể bật quyền truy cập private trong package đóng đó; thao tác đọc field sẽ không được phép.

Nếu chỉ khai báo:

~~~java
exports com.example.domain.model;
~~~

framework có thể sử dụng các thành viên public trong package theo quy tắc thông thường, nhưng không vì thế mà được đọc field private bằng deep reflection.

## 6. Dùng canAccess, trySetAccessible và setAccessible đúng cách

Từ Java 9, **AccessibleObject** cung cấp các API hữu ích để kiểm tra và yêu cầu quyền truy cập.

### canAccess(Object obj)

Dùng để kiểm tra caller hiện tại có thể truy cập reflected member với receiver đã cho hay không. Với member instance, truyền đối tượng receiver tương ứng; với static member hoặc constructor, truyền **null**.

~~~java
Field field = UserRecord.class.getDeclaredField("internalId");
UserRecord user = new UserRecord();

if (field.canAccess(user)) {
    System.out.println(field.get(user));
}
~~~

**canAccess** không tự mở package hoặc thay đổi cấu hình module. Nó chỉ kiểm tra khả năng truy cập hiện tại.

### trySetAccessible()

Dùng khi ứng dụng cần thử bật chế độ bỏ qua kiểm tra truy cập theo quy tắc Java:

~~~java
Field field = UserRecord.class.getDeclaredField("internalId");

if (field.trySetAccessible()) {
    Object value = field.get(user);
    System.out.println(value);
} else {
    System.out.println("Module chưa cho phép deep reflection");
}
~~~

Nếu module không cho phép mở package, **trySetAccessible()** trả về **false**. Cách này phù hợp khi ứng dụng muốn xử lý trường hợp không có quyền mà không cần để exception **InaccessibleObjectException** xuất hiện ngay tại điểm gọi.

### setAccessible(true)

~~~java
field.setAccessible(true);
Object value = field.get(user);
~~~

Lệnh này yêu cầu bật quyền truy cập bị bỏ qua. Nếu điều kiện JPMS không cho phép, JVM có thể ném **InaccessibleObjectException**. Vì vậy, không nên giả định **setAccessible(true)** luôn thành công.

**setAccessible(true)** không thể mở tùy ý mọi thành viên của mọi module. Nó không thay thế descriptor module hoặc cấu hình runtime. Chỉ dùng deep reflection khi có nhu cầu rõ ràng và module đích chủ động cho phép.

## 7. --add-exports khác --add-opens

Hai cờ này thường bị dùng nhầm khi xử lý lỗi reflection.

**--add-exports** bổ sung quyền export package cho module đích. Nó hỗ trợ truy cập các kiểu/thành viên public theo quy tắc thông thường. Có thể cần ở compile time và runtime:

~~~bash
# Compile time
javac --add-exports com.example.domain/com.example.domain.internal=com.example.app ...

# Runtime
java --add-exports com.example.domain/com.example.domain.internal=com.example.app ...
~~~

**--add-opens** mở package cho deep reflection ở runtime:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.framework ...
~~~

Nếu caller thuộc unnamed module (chẳng hạn ứng dụng hoặc framework chạy trên classpath), có thể dùng **ALL-UNNAMED**:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;libs/*" com.example.Main
~~~

Ví dụ này dùng dấu phân cách classpath của Windows. Trên Linux/macOS, thay dấu **;** bằng **:**.

Một số điểm cần nhớ:

- **--add-exports** không mở private member cho deep reflection.
- **--add-opens** không làm package có thể import trực tiếp trong source code.
- **--add-opens** là tùy chọn runtime; không dùng nó để chữa lỗi compile-time access.
- **ALL-UNNAMED** nhắm tới các unnamed module, thường là code trên classpath.
- Nếu sở hữu module nguồn, khai báo **exports** hoặc **opens** trong **module-info.java** thường dễ bảo trì hơn việc phụ thuộc vào cờ khởi chạy bên ngoài.

Đừng thêm cả hai cờ theo thói quen. Đọc thông báo lỗi để xác định đang thiếu quyền truy cập API public hay quyền deep reflection.

## 8. Reflection và Method Handles

Reflection không phải cách duy nhất để thao tác động với thành viên. Java còn có Method Handles qua **java.lang.invoke**.

**MethodHandles.Lookup** có các mức quyền truy cập riêng. Với trường hợp cần tạo lookup có quyền private trong một lớp thuộc module khác, **MethodHandles.privateLookupIn(...)** yêu cầu điều kiện module phù hợp, bao gồm module của caller đọc module đích và package đích được mở cho caller.

Ví dụ khái quát:

~~~java
MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
    UserRecord.class,
    MethodHandles.lookup()
);
~~~

Nếu package không mở hoặc quan hệ module không đáp ứng điều kiện, thao tác này thất bại với lỗi truy cập tương ứng. **privateLookupIn** không phải cách lách JPMS; nó tuân theo quy tắc module và quyền của lookup.

Khi chỉ cần gọi API public, nên dùng lời gọi Java thông thường hoặc method handle với quyền phù hợp. Chỉ dùng deep reflection/lookup private cho các tình huống framework, serializer, dependency injection hoặc công cụ cần thao tác nội bộ có chủ đích.

## 9. Đọc đúng exception để xác định lớp quyền bị thiếu

| Thông báo/lỗi | Ý nghĩa thường gặp | Nên kiểm tra |
| --- | --- | --- |
| **package ... is not visible** | Compile-time code không thể sử dụng package | **requires**, **exports**, module path |
| **IllegalAccessError** | Bytecode đã biên dịch nhưng truy cập runtime không hợp lệ | Descriptor module, phiên bản module/JAR, export tại runtime |
| **IllegalAccessException** | Reflection không được phép thực hiện thao tác trên member | Modifier, package export/open, caller module |
| **InaccessibleObjectException** | Yêu cầu bật access suppression bị module system từ chối | **opens**, qualified opens, **--add-opens** |
| **ClassNotFoundException** | Không tìm thấy lớp theo tên trong cấu hình loader | Classpath, module path, class loader |
| **NoSuchFieldException / NoSuchMethodException** | Không tìm thấy member có tên/signature được yêu cầu | Tên, kiểu tham số, lớp khai báo, phiên bản thư viện |
| **InvocationTargetException** | Method được gọi qua reflection đã ném exception bên trong | Xem **getCause()** để tìm lỗi thật của method |

Không nên nhầm **InvocationTargetException** với lỗi quyền truy cập. Nó là wrapper cho exception do chính method đích ném ra sau khi lời gọi đã được thực hiện.

Tương tự, **NoSuchMethodException** không có nghĩa module chưa mở package. Có thể chương trình tìm sai overload, sai kiểu tham số hoặc tìm method ở lớp không khai báo method đó.

## 10. Quy trình chẩn đoán khi compile thành công nhưng reflection thất bại

Làm theo thứ tự sau để khoanh vùng nhanh:

1. **Xác nhận thao tác reflection.** Lỗi xảy ra ở **getDeclaredField**, **trySetAccessible**, **Field.get**, **Method.invoke** hay **Constructor.newInstance**? Ghi lại chính xác dòng ném lỗi.
2. **Xác định member và package.** Ghi tên module chứa lớp, package, class, member và access modifier.
3. **Xác định caller module.** Code reflection nằm trong named module nào hay unnamed module trên classpath?
4. **Kiểm tra export.** Nếu chỉ cần truy cập public API, package có được export tới caller không?
5. **Kiểm tra open.** Nếu cần private/package-private/protected deep reflection, package có được mở tới caller không?
6. **Kiểm tra cách khởi chạy.** IDE, test runner, container hoặc lệnh production có truyền đúng **--add-opens** hay không?
7. **Kiểm tra khác biệt môi trường.** So sánh JDK, module path, classpath và phiên bản dependency giữa máy local, CI và production.
8. **Chọn sửa đổi hẹp nhất.** Ưu tiên mở đúng package cho đúng module; tránh mở toàn bộ module nếu chỉ cần một package.

Có thể dùng các lệnh sau để kiểm tra cấu hình:

~~~bash
java -version
javac -version

# Xem module descriptor và package được export/open
jar --describe-module --file libs/domain.jar

# Xem module resolution lúc khởi động
java --show-module-resolution --module-path mods \
  -m com.example.framework/com.example.framework.Inspector

# Xem class được nạp từ nguồn nào (Java 9+)
java -Xlog:class+load=info --module-path mods \
  -m com.example.framework/com.example.framework.Inspector
~~~

Khi chạy trên Windows PowerShell hoặc CMD, có thể viết mỗi lệnh trên một dòng hoặc dùng cú pháp nối dòng phù hợp với shell đang sử dụng.

## 11. Những cách sửa dễ gây vấn đề

**Mở toàn bộ module để chữa một field private.** Dùng **open module** hoặc **--add-opens ...=ALL-UNNAMED** làm phạm vi truy cập rộng hơn nhu cầu. Hãy ưu tiên qualified **opens package to module** nếu biết chính xác framework cần quyền.

**Export package rồi kỳ vọng đọc được private field.** **exports** cấp quyền truy cập API public. Private field cần deep reflection và package phải được mở.

**Thêm --add-opens để chữa lỗi import.** Source code không thể import package chỉ vì package được mở. Hãy dùng **exports** khi cần truy cập API public ở compile time.

**Gọi setAccessible(true) trên mọi field.** Cách này dễ làm ứng dụng phụ thuộc vào chi tiết triển khai nội bộ của thư viện/JDK. Ưu tiên getter, constructor, API public, annotation hoặc extension point được thư viện cung cấp.

**Mở package của JDK mà không có lý do.** Các package nội bộ của JDK được đóng gói mạnh. Nếu framework cũ cần reflection vào JDK internals, ưu tiên nâng framework hoặc chuyển sang API được hỗ trợ. Cờ mở package chỉ nên là biện pháp tương thích có phạm vi rõ ràng.

**Chỉ kiểm tra bằng unit test trên một JDK.** Cấu hình module có thể khác giữa test runner và ứng dụng thực. Cần xác nhận lệnh khởi chạy và phiên bản JDK ở môi trường đích.

## 12. Chọn cơ chế đúng theo nhu cầu

| Nhu cầu | Cơ chế nên dùng |
| --- | --- |
| Source code import và gọi public API của module khác | **requires** và **exports** |
| Chỉ cho một module sử dụng public API | Qualified **exports ... to ...** |
| Framework cần đọc private field hoặc gọi private method | Qualified **opens ... to ...** |
| Ứng dụng legacy trên classpath cần deep reflection | **--add-opens package=ALL-UNNAMED** trong runtime, nếu thật sự cần |
| Thư viện muốn hỗ trợ framework qua reflection | Công bố package mở có chủ đích hoặc cung cấp API/extension point rõ ràng |
| Cần truy cập động nhưng không cần private access | Reflection trên public API đã export hoặc Method Handles với quyền phù hợp |
| Cần quyền private qua Method Handles | **privateLookupIn** cùng điều kiện readability và open của module |

Một nguyên tắc thiết kế hữu ích: **API public nên được công khai bằng exports; chi tiết nội bộ chỉ mở cho framework thật sự cần bằng opens**. Điều này giúp module giữ được ranh giới đóng gói và giảm phụ thuộc vào cấu trúc bên trong.

## 13. Câu hỏi tự kiểm tra

1. **getDeclaredField()** có đảm bảo **Field.get()** sẽ thành công không? Vì sao?
2. **exports** khác **opens** ở mục đích và thời điểm kiểm tra nào?
3. Package được **opens** nhưng không **exports** có thể được import trực tiếp từ module khác không?
4. Khi caller chạy trên classpath, target module trong **--add-opens** có thể là giá trị nào?
5. Vì sao **setAccessible(true)** có thể ném **InaccessibleObjectException** dù field tồn tại?
6. Nếu chỉ cần gọi một method public đã export, có cần mở toàn bộ package không?
7. **InvocationTargetException** cho biết lỗi xảy ra ở giai đoạn nào?
8. Nếu **trySetAccessible()** trả về **false**, nên kiểm tra descriptor hoặc runtime option nào?

Nếu trả lời được các câu hỏi trên, bạn có thể phân biệt rõ lỗi do Java access modifier, module readability/export hay deep reflection. Khi điều tra một lỗi thực tế, hãy bắt đầu từ thao tác reflection thất bại, xác định caller và package đích, rồi chọn **exports** hoặc **opens** đúng với nhu cầu.
