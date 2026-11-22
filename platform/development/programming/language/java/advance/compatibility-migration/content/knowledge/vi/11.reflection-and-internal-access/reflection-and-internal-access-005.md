# setAccessible, MethodHandles và quyền truy cập theo module

Khi nâng một ứng dụng Java từ JDK cũ lên Java 17, 21 hoặc một phiên bản mới hơn, những lỗi khó nhận diện thường đến từ reflection và việc truy cập thành phần nội bộ. Mã nguồn có thể biên dịch thành công, nhưng chương trình chỉ thất bại khi framework tạo object, ánh xạ dữ liệu, gọi method riêng hoặc nạp một plugin. Một lỗi điển hình là InaccessibleObjectException: trước đây thư viện có thể dùng setAccessible(true) để mở một field private, còn trên runtime mới package chứa field không được module chủ sở hữu mở cho thư viện đó.

Cùng lúc, Java cung cấp MethodHandles và VarHandle để biểu diễn phương thức, constructor và biến dưới dạng handle có kiểu. Đây là những công cụ mạnh cho framework, thư viện hiệu năng hoặc cơ chế invocation động, nhưng **không phải cách vượt qua quy tắc module access**. MethodHandles.Lookup cũng được kiểm tra quyền theo class, package, module và phạm vi lookup.

Bài học này thuộc **Java Advance Compatibility Migration**, chương **Reflection và API nội bộ**. Nội dung trình bày cách hoạt động của setAccessible, MethodHandles, MethodHandles.Lookup và privateLookupIn, phân biệt exports với opens trong Java Platform Module System (JPMS), cách xác định lỗi khi nâng JDK và phương pháp thiết kế, cấu hình, kiểm thử để migration an toàn.

## 1. Bản đồ các cơ chế truy cập trong Java

Java có nhiều cơ chế truy cập, mỗi cơ chế phục vụ nhu cầu khác nhau:

- **Gọi trực tiếp:** compiler kiểm tra public, protected, package-private, private, kế thừa và phạm vi package/module.
- **Core reflection:** dùng Class, Field, Method, Constructor để khám phá và thao tác thành phần ở runtime.
- **Method handles:** dùng MethodHandle và MethodHandles.Lookup để tìm và gọi method hoặc constructor với kiểu đã xác định.
- **Variable handles:** dùng VarHandle để truy cập biến, có thể cung cấp những operation về bộ nhớ và atomic khi phù hợp.
- **JPMS:** module-info.java định nghĩa module nào được đọc, package nào được export và package nào được mở cho deep reflection.
- **Runtime command-line options:** có thể điều chỉnh một số ranh giới truy cập khi khởi động JVM, nhưng không thay thế hợp đồng API được hỗ trợ.

Các lớp quyền truy cập thường được hiểu theo sơ đồ:

~~~text
Mã nguồn / thư viện / framework
             |
             v
    Compiler và Java access
             |
             v
   Module readability + exports
             |
       +-----+------+
       |            |
       v            v
  Gọi thông     Reflection sâu
  thường        / private lookup
       |            |
       |            v
       |      opens / open module
       |            |
       +-----+------+
             |
             v
       JVM thực thi
~~~

Sơ đồ mang tính khái niệm. Từng API có điều kiện truy cập cụ thể; không phải mọi thao tác reflection đều cần opens. **Public reflective access** và **deep reflection vào private member** phải được tách riêng.

## 2. Phân biệt bốn loại quyền truy cập

### 2.1. Quyền truy cập theo ngôn ngữ

Java định nghĩa:

| Modifier | Phạm vi truy cập thông thường |
|---|---|
| public | Những nơi có quyền nhìn thấy kiểu chứa member, chịu thêm quy tắc module |
| protected | Cùng package và một số ngữ cảnh subclass được phép |
| Không có modifier | Các class trong cùng package |
| private | Phạm vi được ngôn ngữ cho phép trong kiểu/nest tương ứng |

Một public method trong public class chưa chắc truy cập được từ module khác nếu package chứa class không được export.

### 2.2. Quyền đọc module

Trong JPMS, một module thường cần khai báo requires tới module chứa những API mà nó sử dụng:

~~~java
module com.example.client {
    requires com.example.library;
}
~~~

Điều này hình thành quan hệ readability. Nhưng requires không tự động mở toàn bộ package của module được đọc.

### 2.3. Quyền truy cập package thông thường: exports

Module thư viện có thể công bố API:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Consumer có thể sử dụng các public type trong package được export theo quy tắc Java thông thường. Một package không được export vẫn có thể tồn tại trong module, nhưng không mặc nhiên là public API cho module khác.

### 2.4. Quyền deep reflection: opens

Một module có thể mở package để cho phép reflective access sâu:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.model to com.example.serializer;
}
~~~

Khi package model được mở cho module serializer, framework có thể được phép dùng các reflection operation phù hợp lên member không public ở package này. Nhưng opens không đồng nghĩa public source API: compiler của module serializer không tự động được phép import các public type từ package model nếu package đó chưa được export.

Nếu cần cả public compile-time access lẫn deep reflection, có thể export và open cùng một package, tùy nhu cầu.

## 3. Reflection thông thường và deep reflection khác nhau thế nào?

Java reflection cung cấp hai nhóm hành động:

1. **Khám phá:** lấy Field, Method, Constructor và metadata từ Class.
2. **Truy cập/gọi:** đọc field, ghi field, gọi method hoặc tạo instance.

Ví dụ:

~~~java
Class<?> type = Class.forName("com.example.model.Customer");

for (java.lang.reflect.Field field : type.getDeclaredFields()) {
    System.out.println(field.getName());
}
~~~

getDeclaredFields có thể trả về metadata của các field khai báo trong class, kể cả field private. Tuy nhiên, **khám phá được member không đồng nghĩa có quyền đọc hoặc ghi giá trị của member đó**.

Ví dụ, sau khi tìm một private field:

~~~java
java.lang.reflect.Field field = type.getDeclaredField("secret");
Object value = field.get(customer);
~~~

Lệnh field.get có thể ném IllegalAccessException nếu code gọi không có quyền. Việc Class cho phép liệt kê tên field không tự động cấp quyền truy cập private field.

### 3.1. getField và getDeclaredField

| API | Thành phần tìm kiếm |
|---|---|
| getField(name) | Public field có thể được kế thừa |
| getDeclaredField(name) | Field được khai báo trực tiếp trong class, bất kể modifier |
| getMethod(name, types) | Public method phù hợp, xét cả method kế thừa |
| getDeclaredMethod(name, types) | Method khai báo trực tiếp trong class |
| getConstructor(types) | Public constructor |
| getDeclaredConstructor(types) | Constructor được khai báo trực tiếp, kể cả non-public |

Các method getDeclared... giúp tìm metadata nhưng không có quyền tự động vượt qua Java access checks.

## 4. setAccessible(true) thực hiện điều gì?

Field, Method và Constructor kế thừa cơ chế accessibility của AccessibleObject. Gọi:

~~~java
field.setAccessible(true);
~~~

yêu cầu runtime **cho phép bỏ qua các kiểm tra access theo ngôn ngữ Java** cho thao tác reflection tiếp theo trên đối tượng AccessibleObject đó, trong những trường hợp JDK và JPMS cho phép.

Đây không phải lệnh cấp quyền tuyệt đối. Trên JDK có module system, khả năng bật accessible bị ràng buộc bởi module của caller và module chứa member.

### 4.1. Ví dụ bên trong cùng module

Giả sử có class:

~~~java
package com.example.domain;

public final class Account {
    private final String token;

    public Account(String token) {
        this.token = token;
    }
}
~~~

Một utility nằm trong cùng module có thể dùng reflection:

~~~java
package com.example.inspect;

import com.example.domain.Account;
import java.lang.reflect.Field;

public final class AccountInspector {
    public static String readToken(Account account) throws Exception {
        Field field = Account.class.getDeclaredField("token");
        field.setAccessible(true);
        return (String) field.get(account);
    }
}
~~~

Trong trường hợp code chạy trong cùng module và thỏa điều kiện truy cập của reflection, thao tác có thể thành công. Nhưng đây vẫn là coupling vào private field. Nếu lớp Account đổi tên token, utility sẽ hỏng dù public API của Account có thể không đổi.

Một cách thiết kế tốt hơn, nếu việc đọc token là use case được phép, là cung cấp API có kiểm soát thay vì phụ thuộc reflection. Với token hoặc secret, cần cân nhắc bảo mật; không nên mở một getter tiết lộ bí mật chỉ vì reflection đang được dùng.

### 4.2. setAccessible(false)

Lời gọi:

~~~java
field.setAccessible(false);
~~~

đặt lại cờ override access checks. Nó không làm field trở thành public hay đổi module descriptor; chỉ điều chỉnh việc thao tác reflection có cố bỏ qua access checks hay không.

### 4.3. trySetAccessible và canAccess

Từ Java 9, có thể hỏi một AccessibleObject:

~~~java
boolean accessible = field.trySetAccessible();
~~~

Nếu không được phép bật override theo điều kiện module, trySetAccessible thường trả false thay vì ném InaccessibleObjectException như setAccessible(true). Vẫn phải xử lý những lỗi khác có thể xảy ra theo tài liệu API, ví dụ các hạn chế liên quan bảo mật trong môi trường tương ứng.

Có thể dùng:

~~~java
boolean allowed = field.canAccess(targetObject);
~~~

canAccess kiểm tra xem code gọi hiện tại có thể truy cập member qua reflection theo trạng thái hiện tại hay không. Với instance field cần truyền object phù hợp; với static field truyền null. Đây không phải phương thức hỏi package có open ở mọi tình huống, và kết quả phụ thuộc member, caller và trạng thái override.

Một cách xử lý tránh lỗi khó hiểu:

~~~java
Field field = Account.class.getDeclaredField("token");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Module owning Account does not permit reflective access");
}

String value = (String) field.get(account);
~~~

Cách này cải thiện chẩn đoán nhưng không thay đổi hợp đồng module. Nếu mở private data không phù hợp, giải pháp đúng là thiết kế lại integration.

## 5. Tại sao setAccessible có thể thất bại sau migration?

Từ Java 9, JPMS bổ sung cơ chế đóng gói mạnh ở cấp module. Với named modules, nhiều thao tác private reflection qua biên module chỉ được phép khi package mục tiêu được mở cho module gọi.

Tình huống thường gặp:

~~~text
Module: com.example.domain
  package: com.example.domain.model
  class: Customer
    private String id

Module: com.example.serializer
  code gọi:
    Customer.class.getDeclaredField("id")
    field.setAccessible(true)
~~~

Nếu module domain chỉ export model mà không open package cho serializer, việc truy cập public API có thể hoạt động bình thường nhưng setAccessible(true) trên private field có thể ném InaccessibleObjectException.

Lỗi minh họa:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.example.domain does not "opens
com.example.domain.model" to module com.example.serializer
~~~

Thông điệp thực tế phụ thuộc member, module, JDK và framework.

### 5.1. Các điều kiện thường cho phép bật accessible

Theo quy tắc AccessibleObject, những trường hợp phổ biến gồm:

- Caller và member nằm trong cùng module.
- Caller truy cập public member trong public class thuộc package được export phù hợp.
- Một số trường hợp protected static được quy tắc truy cập Java/module cho phép.
- Package chứa member được open cho module của caller.

Chi tiết phụ thuộc loại member, class chứa, caller class và quy tắc phản chiếu của JDK. Không nên suy luận rằng exports luôn đủ cho private reflection.

### 5.2. Trường hợp final field

setAccessible(true) không đồng nghĩa có thể thay mọi final field an toàn. Một số loại final field không thể ghi bằng reflection như các field được coi là non-modifiable final theo đặc tả reflection. Ngay cả khi một final instance field nào đó có thể được ghi bằng một đường tương thích, Java Memory Model, JIT và invariant của object có thể khiến việc thay đổi sau khởi tạo không an toàn.

**Không dùng reflection để phá invariant hoặc sửa final field của object đang hoạt động như một cơ chế migration mặc định.**

## 6. exports và opens: bảng quyết định

| Cấu hình module | Gọi public API từ module khác | Private deep reflection từ module khác |
|---|---|---|
| Không exports, không opens | Không theo truy cập thông thường | Không, trừ quyền đặc biệt phù hợp |
| exports package | Có, khi đáp ứng readability và Java access | Không tự động |
| opens package | Không tự cấp compile-time access | Có thể được phép theo reflection rules |
| exports + opens | Có | Có thể được phép |
| exports package to module X | Public access cho X | Không tự động mở private |
| opens package to module X | Không tự cấp compile access | Deep reflection cho X theo quy tắc |
| open module | Các package được mở cho deep reflection | Không tự biến mọi package thành source API được export |

Trong hệ thống thư viện, có thể cần một package chỉ dành cho serializer hoặc ORM framework. Thay vì open toàn bộ module, nên sử dụng **qualified opens** khi framework và deployment cho phép.

## 7. Ví dụ JPMS có module thực tế

Giả sử module chứa model:

~~~text
domain/
  src/main/java/
    module-info.java
    com/example/domain/api/Customer.java
~~~

Nội dung module-info.java:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.api to com.example.inspector;
}
~~~

Class Customer:

~~~java
package com.example.domain.api;

public final class Customer {
    private final String code;

    public Customer(String code) {
        this.code = code;
    }

    public String displayName() {
        return "Customer";
    }
}
~~~

Module dùng reflection:

~~~text
inspector/
  src/main/java/
    module-info.java
    com/example/inspector/Main.java
~~~

module-info.java:

~~~java
module com.example.inspector {
    requires com.example.domain;
}
~~~

Main.java:

~~~java
package com.example.inspector;

import com.example.domain.api.Customer;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("C-001");

        Field field = Customer.class.getDeclaredField("code");
        field.setAccessible(true);

        System.out.println((String) field.get(customer));
    }
}
~~~

Trong ví dụ này, exports cho phép inspector biên dịch với public Customer. opens cho phép inspector thực hiện deep reflection đối với field private code. Nếu bỏ dòng opens và để hai class trong hai named modules khác nhau, lời gọi setAccessible(true) có thể thất bại.

Lưu ý: tên module được khai báo trong qualified opens phải khớp tên module thực tế của code nhận quyền. Nếu framework chạy như unnamed module hoặc tên module thay đổi, cấu hình phải phản ánh topology đó.

## 8. Cờ JVM --add-opens và --add-exports

Khi chưa thể sửa module descriptor hoặc cần một biện pháp chuyển tiếp, runtime có thể nhận thêm tùy chọn.

### 8.1. --add-opens

Ví dụ:

~~~bash
java --add-opens=com.example.domain/com.example.domain.api=com.example.inspector \
     --module-path mods \
     --module com.example.inspector/com.example.inspector.Main
~~~

Cú pháp mở package của một module nguồn cho module đích được chỉ định. Dấu gạch chéo phân tách module với package, còn dấu bằng phân tách tập module được cấp quyền. Đây là ví dụ minh họa, cần điều chỉnh module path và entrypoint theo project.

Nếu một framework chạy trên classpath thuộc unnamed module, thường gặp:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

ALL-UNNAMED cấp quyền tới các unnamed modules tương ứng; đây là quyền rộng, cần được cân nhắc khi dùng ở production.

### 8.2. --add-exports

Ví dụ:

~~~bash
java --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED -jar app.jar
~~~

--add-exports cho phép truy cập các public type/member của package không được export thông thường, theo những giới hạn Java access. Nó **không tự động** cho phép deep reflection vào private field.

### 8.3. So sánh

| Tùy chọn | Mục tiêu chính | Không bảo đảm |
|---|---|---|
| --add-exports | Mở public access của package cho module đích | Truy cập private member bằng setAccessible |
| --add-opens | Mở package cho deep reflection của module đích | Ổn định API nội bộ hoặc an toàn thay đổi private state |
| --add-reads | Điều chỉnh một quan hệ đọc module trong trường hợp cần | Tự export hoặc open package |

Không thể xử lý mọi lỗi bằng một loại cờ duy nhất. Cần xem thông báo JVM cho biết thiếu reads, exports hay opens.

### 8.4. Dùng cờ chỉ như giải pháp chuyển tiếp

Khi thêm runtime flag, hãy ghi:

- Package và module đích.
- Dependency hoặc plugin đang yêu cầu truy cập.
- Phiên bản JDK và thư viện đang dùng.
- Rủi ro và lý do không thể nâng library ngay.
- Owner theo dõi và mốc loại bỏ.
- Test chứng minh app hoạt động khi cờ được bỏ sau nâng cấp dependency.

Đừng mở toàn bộ package nội bộ chỉ để “làm app chạy”. Một package có thể chứa thông tin nhạy cảm, và opens mở khả năng deep reflection cho các đối tượng cùng module đích.

## 9. Tác động của strong encapsulation qua các phiên bản Java

Đối với codebase chuyển từ Java 8 lên JDK hiện đại, thay đổi lớn là việc truy cập các package nội bộ JDK bị kiểm soát chặt hơn.

Những mốc quan trọng:

| Mốc | Ảnh hưởng tới reflection |
|---|---|
| Java 8 | Chưa có JPMS; nhiều thư viện legacy dựa vào access đến internals |
| Java 9 | JPMS, exports/opens và cảnh báo về illegal reflective access trong các tình huống phù hợp |
| Java 16 | Strong encapsulation là mặc định theo hướng tiến hóa JDK |
| Java 17 | JEP 403 tăng cường strong encapsulation cho JDK internals; không nên dựa vào relaxed encapsulation kiểu cũ |
| Java 21 trở lên | Cần thiết kế integration theo API công khai, module boundaries và phiên bản library được hỗ trợ |

Tùy chọn --illegal-access từng được dùng trong giai đoạn chuyển tiếp, nhưng không còn là một chiến lược đáng tin trên JDK hiện đại. Đối với Java 17 trở lên, nên xem hướng dẫn phiên bản JDK mục tiêu và ưu tiên nâng thư viện hoặc thay đường truy cập nội bộ.

Một số critical internal APIs, chẳng hạn trong jdk.unsupported, có chính sách riêng. Việc một API nội bộ vẫn tồn tại **không có nghĩa** nó mang cam kết ổn định tương đương Java SE API.

## 10. MethodHandles là gì?

Package java.lang.invoke cung cấp cơ chế method handle. Một MethodHandle biểu diễn một phép gọi đến method, constructor hoặc operation tương ứng mà JVM có thể thực thi.

Có thể hiểu:

- java.lang.reflect.Method là đối tượng mô tả một method và có Method.invoke để gọi thông qua reflection.
- MethodHandle là một đối tượng callable với **method type** được xác định, có thể kết hợp qua các adapter trong java.lang.invoke.
- MethodHandles.Lookup là **đối tượng mang ngữ cảnh quyền truy cập** dùng để tìm method handle và một số loại handle khác.

Các thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| MethodHandle | Tham chiếu callable tới method/constructor hoặc phép kết hợp |
| MethodType | Kiểu trả về và kiểu tham số JVM của handle |
| MethodHandles.Lookup | Lookup context cùng quyền truy cập phù hợp |
| MethodHandles.lookup() | Lookup gắn với caller, có quyền dựa vào nơi gọi |
| MethodHandles.publicLookup() | Lookup dùng cho các phần public có thể truy cập |
| MethodHandles.privateLookupIn() | Tạo lookup mang quyền private access ở target class khi được phép |
| VarHandle | Handle cho operation đọc/ghi/atomic trên biến |
| findVirtual | Tìm instance method |
| findStatic | Tìm static method |
| findConstructor | Tìm constructor |
| findGetter/findSetter | Tìm field accessor theo điều kiện truy cập |
| unreflect | Chuyển Method thành MethodHandle nếu quyền cho phép |

**MethodHandle không phải “reflection nhưng không cần quyền”.** Quyền truy cập được kiểm tra khi tìm/tạo handle, và một handle đã được tạo có thể mang khả năng gọi thành phần tương ứng. Vì vậy, không nên vô tình chuyển một lookup toàn quyền hoặc handle nhạy cảm cho plugin không đáng tin cậy.

## 11. Ví dụ MethodHandle với public method

Giả sử có class:

~~~java
public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Dùng MethodHandle:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class PublicHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle greet = lookup.findVirtual(
            Greeter.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        Greeter receiver = new Greeter();
        String message = (String) greet.invokeExact(receiver, "Lan");
        System.out.println(message);
    }
}
~~~

Giải thích:

1. findVirtual tìm method instance greet trên Greeter.
2. MethodType nêu kiểu trả về String và một tham số String của method.
3. Khi gọi handle instance, receiver Greeter được truyền như đối số đầu tiên của invocation.
4. invokeExact yêu cầu chữ ký tại call site khớp chính xác với type của handle.
5. Trong ví dụ, main khai báo throws Throwable vì invocation có thể ném Throwable từ method được gọi hoặc từ cơ chế invocation.

Đối với Java source thực tế, hai public class này cần đặt trong hai file riêng hoặc điều chỉnh visibility theo cấu trúc dự án.

### 11.1. invokeExact, invoke và asType

Ba khái niệm dễ nhầm:

| Operation | Ý nghĩa |
|---|---|
| invokeExact | Yêu cầu method type tại call site khớp chính xác |
| invoke | Cho phép một số chuyển đổi kiểu hợp lệ theo quy tắc method handle invocation |
| asType | Tạo adapter handle cho một method type có thể chuyển đổi |

Ví dụ, biến receiver của invokeExact cần có static type phù hợp với chữ ký handle. Nếu dùng Object thay vì Greeter ở call site nhưng handle yêu cầu Greeter, JVM có thể ném WrongMethodTypeException.

Việc sử dụng invoke không xóa mọi hạn chế kiểu; conversion vẫn chịu quy tắc của MethodHandle API.

### 11.2. Method handle không bảo đảm luôn nhanh hơn reflection

JVM có thể tối ưu method handle tốt trong các tình huống nhất định, đặc biệt khi handle và call site ổn định. Nhưng kết quả phụ thuộc workload, JDK, cách cache, khả năng inlining, allocation, warm-up và chi phí conversion.

Không nên chọn MethodHandles chỉ vì cho rằng tốc độ luôn cao hơn Method.invoke. Trước hết hãy chọn API theo yêu cầu kỹ thuật, contract và quyền truy cập; benchmark sau trong workload thực tế.

## 12. MethodHandles.Lookup và privateLookupIn

### 12.1. Lookup mang quyền của caller

MethodHandles.lookup() trả về lookup gắn với class nơi gọi. Các khả năng truy cập phản ánh phạm vi của caller và điều kiện module hiện tại.

MethodHandles.publicLookup() hạn chế hơn, phù hợp khi chỉ cần tìm những member public được phép truy cập.

Một lookup không phải token vạn năng: nó không tự cấp quyền đọc private member của bất kỳ class nào trên JVM.

### 12.2. privateLookupIn

privateLookupIn là API được dùng khi cần một Lookup có private access cho target class, **nếu điều kiện truy cập của JVM cho phép**.

Ví dụ trong cùng module:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class PrivateLookupDemo {
    private static final class Session {
        private String state = "NEW";
    }

    public static void main(String[] args) throws Throwable {
        Session session = new Session();

        MethodHandles.Lookup privateLookup =
            MethodHandles.privateLookupIn(
                Session.class,
                MethodHandles.lookup()
            );

        VarHandle stateHandle = privateLookup.findVarHandle(
            Session.class,
            "state",
            String.class
        );

        String current = (String) stateHandle.get(session);
        System.out.println(current);
    }
}
~~~

Ví dụ tập trung vào cơ chế lookup. Với class private nested nằm trong cùng code/module, quyền truy cập có thể được cấp; trong trường hợp này việc dùng privateLookupIn chủ yếu nhằm minh họa API.

### 12.3. Qua ranh giới module

Nếu lookup thuộc module A còn target class thuộc module B, privateLookupIn có các yêu cầu về quyền lookup và việc package đích được mở cho module gọi, cùng các điều kiện truy cập khác theo tài liệu Java Platform. Ví dụ package của B được qualified opens cho A:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.api to com.example.inspector;
}
~~~

Khi đó inspector có thể được phép tạo private lookup vào một class của package api. Nếu bỏ opens và không có đường cấp quyền phù hợp khác, privateLookupIn có thể ném IllegalAccessException.

Cần phân biệt lỗi:

- setAccessible(true) thường báo InaccessibleObjectException khi không thể bật override.
- privateLookupIn thường báo IllegalAccessException nếu không đáp ứng quyền lookup hoặc module openness.

Không nên thử privateLookupIn như cách vòng qua quy tắc đóng gói JPMS; nó được thiết kế để **tuân theo** ranh giới đó.

### 12.4. Không phát tán Lookup có quyền rộng tùy tiện

Lookup có private access là một khả năng nhạy cảm. Nếu framework trao lookup này cho plugin bên ngoài, plugin có thể có quyền truy cập nhiều member ngoài dự kiến.

Hãy cung cấp method handle hoặc public facade đúng nhiệm vụ thay vì chuyển cả lookup giàu quyền cho code không kiểm soát. Việc giới hạn capability giúp giữ ranh giới nội bộ ngay cả khi plugin chạy trong cùng JVM.

## 13. VarHandle và sự khác nhau với Field

VarHandle được thiết kế để thao tác với biến thông qua access modes. Ví dụ:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1);
    }
}
~~~

Đoạn code minh họa tìm VarHandle cho instance field và dùng getAndAdd. Field volatile cùng VarHandle operation phù hợp cho một trường hợp đếm đồng thời đơn giản.

VarHandle hỗ trợ nhiều access modes liên quan đến:

- get, set.
- volatile access.
- acquire/release semantics.
- compareAndSet và các atomic update khi loại biến và access mode hỗ trợ.
- Các operation có kiểu dữ liệu cụ thể.

VarHandle không tự mở quyền truy cập private qua module. Bước findVarHandle vẫn cần Lookup có quyền hợp lệ.

### 13.1. Khi nào dùng Field, MethodHandle hay VarHandle?

| Nhu cầu | Công cụ thường thích hợp |
|---|---|
| Đọc annotation, tên field, generic metadata | Core reflection |
| Tìm/gọi method động với chữ ký đã biết | MethodHandle |
| Tạo object qua constructor được chọn ở runtime | Constructor reflection hoặc MethodHandle |
| Thao tác atomic/ordering có kiểm soát với biến | VarHandle |
| Truy cập thông thường trong cùng codebase | Java method/field access trực tiếp |
| Plugin cần extension point ổn định | Public API/SPI, không phụ thuộc private reflection |

Không nên thay mọi Field bằng VarHandle hoặc mọi Method bằng MethodHandle nếu code chủ yếu dùng metadata. Mỗi abstraction có điểm mạnh và quy tắc riêng.

## 14. Chuyển từ Method reflection sang MethodHandle

Ví dụ reflection truyền thống:

~~~java
java.lang.reflect.Method method =
    Greeter.class.getMethod("greet", String.class);

String result = (String) method.invoke(new Greeter(), "Lan");
~~~

Khi dùng Method.invoke, exception do target method ném thường được bọc trong InvocationTargetException. Code xử lý lỗi cần hiểu cơ chế unwrap nguyên nhân.

Với MethodHandle:

~~~java
MethodHandle handle = MethodHandles.lookup().findVirtual(
    Greeter.class,
    "greet",
    MethodType.methodType(String.class, String.class)
);

String result = (String) handle.invokeExact(new Greeter(), "Lan");
~~~

Method handle invocation có quy tắc ném Throwable và kiểu của riêng nó; không mặc nhiên bọc exception của target method theo cách Method.invoke.

### 14.1. Khác biệt cần cân nhắc khi migration

- Chữ ký của invokeExact được kiểm tra chính xác ở call site.
- MethodHandle cần được tạo bằng lookup có quyền phù hợp.
- Invocation exceptions có thể khác cách bọc của Method.invoke.
- Adapter và conversion phải được thiết kế có chủ đích.
- Member lookup có thể báo NoSuchMethodException hoặc IllegalAccessException.
- Cache handle có thể cải thiện chi phí lookup ở đường nóng.
- Việc dùng MethodHandles không tự loại bỏ module access restrictions.

Một refactor an toàn nên có contract tests bảo đảm kết quả, exception, side effect và trạng thái concurrency tương đương với đường reflection cũ.

## 15. Các lỗi thường gặp khi nâng JDK

### 15.1. InaccessibleObjectException

Ví dụ dạng lỗi:

~~~text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to unnamed module
~~~

Nguyên nhân thường là thư viện dùng setAccessible(true) với private member trong package không được open.

Hướng xử lý:

1. Xác định caller library bằng stack trace.
2. Xác định module/package bị đóng.
3. Kiểm tra bản thư viện mới có hỗ trợ JDK mục tiêu không.
4. Thay đường deep reflection bằng public API khi có thể.
5. Nếu bắt buộc dùng tạm --add-opens, ghi rõ scope và mốc loại bỏ.

### 15.2. IllegalAccessException

Có thể xuất hiện với reflection hoặc method handle lookup khi quyền truy cập chưa đủ. Không nên đoán rằng thêm opens giải quyết mọi IllegalAccessException; kiểm tra member visibility, lookup class, readability, exports và điều kiện private lookup.

### 15.3. IllegalAccessError

Là lỗi ở cấp liên kết/runtime access, thường có thể gặp khi bytecode tham chiếu kiểu hoặc member mà runtime hiện tại không cho phép truy cập. Đây khác với checked IllegalAccessException từ một số API reflection/lookup.

### 15.4. NoSuchFieldException hoặc NoSuchMethodException

Nguyên nhân có thể là tên, signature hoặc member đã thay đổi; có thể do framework dựa vào implementation detail. Nếu public API được hỗ trợ đã đổi, cần thực hiện migration theo hướng dẫn chính thức. Không nên mở module để tìm một member đã không còn tồn tại.

### 15.5. WrongMethodTypeException

Thường liên quan đến MethodHandle call site không khớp chữ ký. Xem kiểu receiver, return type, primitive boxing/unboxing, arity và adapter.

### 15.6. UnsupportedClassVersionError

Phát sinh nếu bytecode của dependency hoặc plugin yêu cầu Java runtime mới hơn runtime đang chạy. Cờ --add-opens không xử lý được lỗi class-file version.

### 15.7. ServiceConfigurationError hoặc ClassCastException

Trong hệ thống framework/plugin có thể liên quan đến service registration, classloader, module layer, type identity hoặc dependency version. Không nhất thiết là lỗi setAccessible.

Phân loại lỗi chính xác giúp tránh thêm JVM flag không cần thiết.

## 16. Framework và annotation processor bị ảnh hưởng thế nào?

Nhiều framework dựa vào reflection để:

- Tạo object qua constructor không public.
- Thiết lập field khi deserialize JSON/XML.
- Ánh xạ entity của ORM.
- Tạo proxy hoặc invoke lifecycle callback.
- Đọc annotation và generic metadata.
- Thực hiện dependency injection.
- Chạy mock/test instrumentation.
- Tìm service provider hoặc plugin.

Khi framework dùng reflection vào class thuộc **module ứng dụng**, thường cần mở package ứng dụng cho module framework. Khi framework dùng reflection vào **JDK internals**, nguyên nhân lại có thể nằm ở phiên bản framework/agent chưa tương thích với JDK mới.

Hai hướng cần xử lý khác nhau:

| Hướng truy cập | Ví dụ | Cách xử lý ưu tiên |
|---|---|---|
| Framework → private member ứng dụng | ORM đọc entity field | opens package đúng framework hoặc đổi mapping |
| Ứng dụng → internals của framework | Dùng private field của framework | Dùng API/SPI framework được hỗ trợ |
| Thư viện cũ → JDK internals | setAccessible vào java.base internals | Nâng/thay thư viện, tránh flag dài hạn |
| Annotation processor → compiler internals | javac implementation API | Nâng processor tương thích compiler |
| Test agent → internals/class loading | Mock/profiler instrumentation | Nâng agent và test trên JDK mục tiêu |

Đừng chỉ nhìn stack trace ở dòng của application code. Một lỗi có thể xuất phát từ dependency transitive hoặc Java agent được khởi động trước ứng dụng.

## 17. Reflection với JDK compiler, annotation processing và tooling

Một số annotation processor, Lombok-like tooling hoặc plugin tạo mã có thể dựa vào class triển khai của javac. Khi nâng JDK build, các công cụ đó có thể gặp lỗi access ngay cả khi production runtime giữ nguyên.

Cần tách:

- **JDK chạy build tool:** JVM chạy Maven/Gradle.
- **Compiler JDK:** javac đang xử lý source.
- **Release target:** cú pháp/API/class-file version mà artifact hướng tới.
- **Production JDK:** JVM thực thi ứng dụng.
- **Processor/plugin runtime:** vị trí mà processor/plugin chạy.

Ví dụ, cấu hình --release 17 không có nghĩa annotation processor chạy trong môi trường của JDK 17 nếu compiler toolchain là JDK 21. Processor được chạy trong ngữ cảnh compiler tương ứng, nên có thể chịu tác động của thay đổi javac internals.

Giải pháp ưu tiên là nâng processor/plugin lên bản hỗ trợ compiler đó. Thêm --add-exports cho package javac nội bộ chỉ là một biện pháp tạm khi đã hiểu rủi ro và hạn chế môi trường áp dụng.

## 18. Classpath, module path và plugin loader

JPMS còn làm migration phức tạp khi một ứng dụng có nhiều classloader hoặc ModuleLayer.

### 18.1. Unnamed module

JAR trên classpath truyền thống thường thuộc unnamed module của classloader liên quan. Khi lỗi ghi “to unnamed module”, caller có thể là ứng dụng hoặc thư viện chạy trên classpath, không phải named module.

Cờ ALL-UNNAMED được dùng để chỉ tập unnamed modules, chứ không có nghĩa mở package cho một named module được chỉ định.

### 18.2. Named module

Khi sử dụng module path, module-info.java có thể chỉ rõ requires, exports và opens. Qualified opens cho module framework giúp giới hạn phạm vi deep reflection.

### 18.3. Automatic module

Một JAR không có explicit module descriptor có thể được đưa lên module path dưới dạng automatic module, với các đặc điểm truy cập khác so với explicit named module. Không nên đoán tên module từ filename khi cấu hình opens; cần xác minh bằng công cụ hoặc runtime resolution.

### 18.4. Plugin isolation

Một plugin có thể dùng classloader riêng, nên:

- Cùng tên class nhưng loader khác có thể là hai kiểu khác nhau.
- Lookup được tạo trong một module/loader không tự có quyền tới module/loader khác.
- ServiceLoader và context classloader ảnh hưởng discovery.
- ModuleLayer có thể tạo ranh giới và đường resolve riêng.
- Tên module mà qualified opens nhắm tới phải đúng nơi code reflection chạy.

Khi kiểm thử lỗi reflection, hãy tái tạo topology classloader/module path giống production. Một unit test trên flat classpath chưa chắc biểu hiện lỗi ở plugin host thực tế.

## 19. Bảo mật và giới hạn của việc mở reflective access

Dù reflection là công cụ hợp pháp của Java, việc mở quyền không nên được dùng tùy tiện. Một số nguyên tắc:

1. Mở đúng package cần thiết, không mở toàn bộ module nếu không có lý do.
2. Ưu tiên qualified opens khi triển khai bằng named modules và biết module đích.
3. Tránh trao MethodHandles.Lookup giàu quyền cho plugin không tin cậy.
4. Không đọc/ghi private secret chỉ vì công cụ cho phép.
5. Không dùng --add-opens để thay kiểm soát phân quyền nghiệp vụ.
6. Đánh giá third-party libraries và Java agents trước khi cấp quyền runtime.
7. Theo dõi runtime flags trong cấu hình deployment và tài liệu migration.

Module encapsulation **không phải security sandbox hoàn chỉnh** để chạy code độc hại trong cùng tiến trình. Một plugin không tin cậy thực sự có thể cần cô lập ở tiến trình/container riêng và một giao thức API rõ ràng. Ngược lại, việc mở module cũng không tự giải quyết các vấn đề authentication, authorization hoặc secret handling.

## 20. Reflection trong native image hoặc AOT

Một ứng dụng chạy trên JVM với reflection động có thể cần cấu hình bổ sung khi chuyển sang native image hoặc môi trường Ahead-of-Time compilation.

Tùy công cụ AOT/native image và framework, việc truy cập một class hoặc method qua tên động có thể cần metadata hoặc hint để được đưa vào binary. Mở package bằng JPMS không tự đảm bảo công cụ build nhìn thấy mọi điểm reflection.

Vì vậy, khi migration kết hợp nâng JDK và chuyển mô hình đóng gói, nên phân biệt:

- Lỗi Java access/module openness.
- Lỗi thiếu reflection metadata của native image.
- Lỗi class/resource không được đưa vào artifact.
- Lỗi dynamic proxy, JNI hoặc service provider registration.

Mỗi nhóm có hướng giải quyết riêng; không nên quy toàn bộ cho setAccessible.

## 21. Công cụ chẩn đoán nên biết

### 21.1. Xem module của một JAR

~~~bash
jar --describe-module --file library.jar
~~~

Giúp xem module declaration hoặc thông tin module liên quan tới artifact.

### 21.2. Xem module JDK

~~~bash
java --describe-module java.base
~~~

Có thể kiểm tra những package nào được export/open theo module declaration của JDK đang chạy.

### 21.3. Xem quá trình resolve module

~~~bash
java --show-module-resolution --module-path mods \
     --module com.example.app/com.example.Main
~~~

Hữu ích để kiểm tra module nào được resolve trong một mô hình module path.

### 21.4. Dùng jdeps kiểm tra nội bộ JDK

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu phân tích cả dependency:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

jdeps có thể phát hiện tham chiếu bytecode tĩnh tới internal API. Nó không tự nhìn thấy mọi đường reflection bằng string hoặc class nạp động, nên cần xem cả source và runtime logs.

### 21.5. Kiểm tra cấu hình JVM thực tế

Ghi nhận lệnh khởi động và các JVM options trong:

- Shell script.
- Docker entrypoint hoặc container image.
- Kubernetes deployment.
- Service manager.
- Maven/Gradle test JVM arguments.
- IDE run configuration.
- Application server.
- Java agent initialization.

Một ứng dụng chạy được ở local nhờ --add-opens có thể lỗi trên production nếu flag không được triển khai tương ứng. Ngược lại, flag vô tình còn sót lại có thể che một dependency nội bộ chưa được sửa.

## 22. Quy trình migration khi gặp lỗi reflection

### Bước 1 — Xác định cấu hình thực tế

Ghi:

- JDK distribution và version.
- Build JDK, compiler/toolchain và release target.
- Runtime classpath/module path.
- Module declaration của ứng dụng.
- Framework/agent versions.
- JVM arguments.
- Tình huống runtime gây lỗi.

### Bước 2 — Đọc stack trace đầy đủ

Xác định:

- Exception cụ thể là gì?
- Class/member nào đang được truy cập?
- Module nguồn và module đích là gì?
- Package bị thiếu exports hay opens?
- Ai gọi setAccessible hoặc privateLookupIn?
- Code thuộc ứng dụng, framework, plugin hay JDK internal dependency?

Không thay đổi cờ JVM dựa trên một đoạn lỗi đã bị cắt mất caller hoặc module.

### Bước 3 — Phân loại đường truy cập

| Đường truy cập | Giải pháp ưu tiên |
|---|---|
| Gọi public API của module khác | Kiểm tra requires, exports và dependency |
| Framework reflection vào model của ứng dụng | opens đúng package cho framework, nếu hợp đồng cho phép |
| Ứng dụng reflection vào private member của framework | Tìm public API/SPI thay thế |
| Dependency gọi JDK internals | Nâng dependency/agent lên bản hỗ trợ JDK |
| MethodHandle lookup thất bại | Kiểm tra lookup class, quyền, method type và module openness |
| Native/AOT thiếu metadata | Bổ sung cấu hình AOT theo framework, không chỉ opens |

### Bước 4 — Ưu tiên sửa thiết kế hoặc dependency

Nếu thư viện đã có bản không dùng internal API, nâng thư viện. Nếu có public facade hoặc SPI, chuyển sang hợp đồng đó. Nếu framework cần reflection vào model application, mở đúng package là một cấu hình chính đáng.

Chỉ dùng --add-opens/--add-exports tạm thời nếu cần để duy trì dịch vụ trong quá trình chuyển đổi và có kế hoạch loại bỏ.

### Bước 5 — Kiểm thử trên đúng JDK/module layout

Các bài kiểm tra nên bao gồm:

- Startup và dependency injection.
- Deserialize/serialize.
- ORM mapping và database access.
- Proxy, aspect, dynamic invocation.
- Annotation processing, generated code.
- Test/mocking framework.
- Java agent và tracing.
- Plugin discovery/load/callback.
- Các nhánh lỗi và cleanup.

### Bước 6 — Xác nhận không còn flag không cần thiết

Sau khi nâng library và sửa code, thử chạy ứng dụng trên staging với danh sách runtime flag tối thiểu. Nếu vẫn cần flag, phải biết cụ thể vì sao và bên nào chịu trách nhiệm loại bỏ.

### Bước 7 — Tài liệu hóa quyết định

Một hồ sơ migration có thể dùng mẫu:

~~~text
APPLICATION / MODULE
  App:
  Build JDK:
  Target runtime JDK:
  Classpath or module path:
  Framework/agent version:

ACCESS FAILURE
  Exception:
  Caller class/module:
  Target class/module/package:
  Member and access type:
  Stack trace reference:

ROOT CAUSE
  Public API / internal API / reflection:
  Missing readability / exports / opens:
  Dependency version:
  Temporary JVM option:

RESOLUTION
  Public API replacement:
  Library/agent upgrade:
  Module-info change:
  JVM option removal milestone:
  Owner:

VALIDATION
  Compile:
  Reflection integration test:
  Framework test:
  Plugin/classloader test:
  Runtime smoke test:
  Deployment/rollback:
~~~

## 23. Những nhầm lẫn phổ biến

### “setAccessible(true) làm mọi private member truy cập được”

Không đúng. JVM kiểm tra quyền và giới hạn module; deep reflection qua module boundary thường cần package được open.

### “exports tương đương opens”

Không đúng. exports chủ yếu phục vụ public access, còn opens phục vụ reflective access sâu. Một package có thể được opens mà không được export.

### “MethodHandles vượt qua được JPMS”

Không đúng. MethodHandles.Lookup có quyền của caller và privateLookupIn chịu điều kiện module openness.

### “trySetAccessible trả false nghĩa là member không tồn tại”

Không đúng. Member có thể tồn tại nhưng caller không được cấp quyền bật override.

### “Mở module là sửa xong dependency”

Không đúng. Cờ runtime chỉ thay quyền truy cập; internal API vẫn có thể đổi hoặc biến mất trong JDK tương lai.

### “Một class public là public API ổn định”

Không đúng. Public là visibility, không phải chính sách hỗ trợ. Cần kiểm tra documentation và support contract.

### “MethodHandle luôn nhanh hơn reflection”

Không có bảo đảm tổng quát. Hiệu năng phụ thuộc cách tạo/cache handle, kiểu call site và workload thực tế.

### “Build thành công nghĩa là không còn lỗi reflection”

Không đúng. Phần lớn lỗi reflection xuất hiện khi framework hoặc plugin thực hiện đường runtime cụ thể.

### “Không có cảnh báo jdeps nghĩa là hoàn toàn tương thích”

Không đúng. Reflection động, class loading bằng tên và các path dựa trên cấu hình có thể không được phân tích tĩnh đầy đủ.

## 24. Ghi nhớ

Khi làm migration liên quan đến reflection, hãy trả lời năm câu hỏi:

1. **Ai đang truy cập ai?** Xác định caller, target class, member và module.
2. **Đó là public invocation hay deep reflection?** Chọn đúng quy tắc access.
3. **Thiếu quyền gì?** requires/readability, exports, opens hay quyền riêng của MethodHandles.Lookup?
4. **Có cần truy cập nội bộ thật không?** Ưu tiên API/SPI được hỗ trợ hoặc nâng dependency.
5. **Đã kiểm chứng trên runtime mục tiêu chưa?** Chạy integration tests với classloader/module layout và JVM options thực tế.

setAccessible, MethodHandles và JPMS không phải ba cơ chế độc lập. Chúng gặp nhau tại cùng một ranh giới: **đối tượng nào được quyền nhìn thấy và thao tác với thành phần nào của một module**. Hiểu đúng ranh giới này giúp nhóm phân biệt lỗi compile với lỗi runtime, cấu hình opens đúng phạm vi, tránh phụ thuộc vào JDK internals và giữ lộ trình nâng Java bền vững hơn.
