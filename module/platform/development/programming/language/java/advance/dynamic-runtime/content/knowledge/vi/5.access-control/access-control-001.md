# 5.1 Phân biệt nhìn thấy một thành phần với được phép sử dụng thành phần đó

Khi phân tích quyền truy cập trong Java, cần tách bạch hai câu hỏi:

1. **Có tìm thấy, nhận diện hoặc lấy được thông tin về thành phần đó không?** Ví dụ: tìm được một `Class<?>` bằng `Class.forName(...)`, liệt kê được một trường `private` bằng `getDeclaredField(...)` hoặc thấy tên phương thức trong bytecode.
2. **Mã ở vị trí hiện tại có được phép sử dụng thành phần ấy không?** Ví dụ: được viết biểu thức truy cập trong Java source, đọc trường bằng `Field.get(...)`, gọi phương thức bằng `Method.invoke(...)` hoặc tạo `MethodHandle` tới member đó.

Hai câu hỏi có thể có câu trả lời khác nhau. **Tìm được metadata không tự cấp quyền đọc, ghi, gọi hay khởi tạo.** Một phương thức `public` của lớp không `public` cũng chưa chắc được truy cập từ nơi khác. Trong Java 9+ (bao gồm Java 17), hệ thống module còn thêm ranh giới `requires`, `exports` và `opens`.

Bài học thuộc nhóm **Quyền truy cập** của Java dynamic runtime, nên trọng tâm là ranh giới giữa *khám phá thành phần* và *thực thi thao tác* trong source Java, Reflection, Method Handles và Java Platform Module System (JPMS).

## 1. Dùng từ cho chính xác: “nhìn thấy” là gì?

Trong trao đổi kỹ thuật, “nhìn thấy” (*visible/discoverable*) có ít nhất ba ngữ cảnh:

- **Nhìn thấy tên trong source:** một tên nằm trong phạm vi (*scope*) có thể được giải nghĩa, import hoặc tham chiếu từ đoạn mã đang biên dịch. Tuy nhiên Java vẫn phải kiểm tra *accessibility*, chẳng hạn kiểu có `public` không, cùng package không, hay module có export package không.
- **Tìm thấy lớp khi chạy:** class loader có thể tìm/định nghĩa lớp, hoặc `Class.forName("pkg.Type")` trả về `Class<?>`. Điều đó chưa chứng minh caller được gọi constructor hoặc method.
- **Tìm thấy metadata bằng Reflection:** `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructor()` có thể trả về các thành phần `private`/package-private/protected. Nhận được `Field`/`Method`/`Constructor` chưa đồng nghĩa được sử dụng chúng.

Vì thế, trong bài này **“nhìn thấy” được dùng theo nghĩa rộng là phát hiện tên/kiểu/metadata**; đừng mặc định đó là thuật ngữ chính thức duy nhất của JLS. JLS phân biệt rõ **scope** (phạm vi dùng tên) với **access control** (quyền truy cập khai báo); điều kiện thấy tên và điều kiện được phép dùng tên thường cùng phải thỏa mãn.

**“Được phép sử dụng”** cũng có nhiều dạng: compile-time access, runtime link/access check, quyền Reflection và quyền của `MethodHandles.Lookup`. Một phép kiểm tra thành công ở tầng này không tự động thay thế mọi phép kiểm tra ở tầng khác.

| Câu hỏi | Ví dụ phép kiểm tra hoặc thao tác | Điều có thể xảy ra |
| --- | --- | --- |
| Mã nguồn có tham chiếu được kiểu không? | `import api.Service`, `new Service()` | Compiler từ chối nếu kiểu không accessible hoặc package chưa export |
| Runtime có nạp/tìm thấy class không? | `Class.forName("internal.Helper")` | Trả về `Class<?>` dù kiểu là package-private; có thể thất bại nếu không tìm/khởi tạo được |
| Reflection có liệt kê được member không? | `type.getDeclaredField("secret")` | Trả `Field` cho trường private |
| Caller dùng member trực tiếp được không? | `obj.secret` | Compiler từ chối nếu `secret` private ngoài phạm vi hợp lệ |
| Caller dùng member qua Reflection được không? | `field.get(obj)` | Có thể ném `IllegalAccessException` |
| Có thể bỏ qua access checks của Reflection không? | `field.trySetAccessible()` | Trả `true` nếu có thể, `false` nếu bị chặn bởi quy tắc module/quyền |
| Method Handles có tạo handle được không? | `lookup.findGetter(...)` | Có thể ném `IllegalAccessException` dù metadata có tồn tại |

Quy tắc thực hành: **phải hỏi “ai đang truy cập, đang thực hiện thao tác gì, trên kiểu và member nào, trong package/module nào?”** Mức độ `public` của một member chỉ là một phần câu trả lời.

## 2. Kiểm tra access trong Java source: kiểu và member đều phải accessible

Java có bốn mức access phổ biến đối với các thành viên của class:

| Modifier | Nguyên tắc access của thành viên | Điểm dễ nhầm |
| --- | --- | --- |
| `public` | Cho phép từ mã có thể truy cập declaring type, với ràng buộc module khi qua module khác | `public` của member **không** biến declaring class package-private thành public |
| `protected` | Trong cùng package; hoặc từ subclass bên ngoài package với quy tắc hạn chế biểu thức receiver đối với instance member | Không có nghĩa bất kỳ object lớp cha nào cũng gọi được từ subclass package khác |
| *Không ghi modifier* (package-private) | Mã thuộc cùng **runtime package hợp lệ**; ở source thường nói “cùng package” | Package tên giống nhau trong class loader/module khác có thể không được JVM coi như cùng runtime package |
| `private` | Mã thuộc phạm vi private-access hợp lệ; Java 11+ hỗ trợ nestmates với truy cập private | `private` không có nghĩa metadata không thể bị phát hiện |

Các loại top-level class/interface chỉ có thể là `public` hoặc package-private; không khai báo top-level class `private`/`protected`. Member class có thể mang các modifier phù hợp.

**Hai tầng bắt buộc:** để gọi `Type.member` từ nơi khác, phải truy cập được **`Type`** rồi mới xét **`member`**. Một method `public` nằm trong class package-private vẫn không trở thành public API toàn cục.

### Ví dụ 1: thấy member private bằng Reflection nhưng không đọc được ngay

Tạo ba file thuộc project chạy bằng classpath, trong đó mã gọi và class có field nằm ở **hai package khác nhau** để tránh quyền private của cùng nest:

**`src/catalog/PublicTool.java`**

~~~java
package catalog;

public class PublicTool {
    private String secret = "inside";

    public String greet() {
        return "hello";
    }
}
~~~

**`src/client/ReflectionAccessDemo.java`**

~~~java
package client;

import catalog.PublicTool;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionAccessDemo {
    public static void main(String[] args) throws Exception {
        PublicTool tool = new PublicTool();

        Method method = PublicTool.class.getMethod("greet");
        Field field = PublicTool.class.getDeclaredField("secret");

        System.out.println("found=" + field.getName());
        System.out.println("method.canAccess=" + method.canAccess(tool));
        System.out.println("method.invoke=" + method.invoke(tool));
        System.out.println("field.canAccess.before=" + field.canAccess(tool));

        try {
            field.get(tool);
        } catch (IllegalAccessException ex) {
            System.out.println("field.get=IllegalAccessException");
        }

        System.out.println("trySetAccessible=" + field.trySetAccessible());
        System.out.println("field.canAccess.after=" + field.canAccess(tool));
        System.out.println("field.get=" + field.get(tool));
    }
}
~~~

Tại thư mục gốc của project, biên dịch/chạy bằng JDK 17+:

~~~sh
javac --release 17 -d out src/catalog/PublicTool.java src/client/ReflectionAccessDemo.java
java -cp out client.ReflectionAccessDemo
~~~

**Stdout chính xác trong ví dụ classpath (unnamed module):**

~~~text
found=secret
method.canAccess=true
method.invoke=hello
field.canAccess.before=false
field.get=IllegalAccessException
trySetAccessible=true
field.canAccess.after=true
field.get=inside
~~~

Điều gì xảy ra?

1. `PublicTool` là `public`, method `greet()` cũng `public`, nên `client.ReflectionAccessDemo` có thể tham chiếu và gọi `greet()`.
2. `getDeclaredField("secret")` **tìm thấy khai báo** field `private`, dù caller ngoài package. API trả một `Field` để mô tả field.
3. `field.canAccess(tool)` ban đầu là `false`, và `field.get(tool)` ném `IllegalAccessException`: Reflection vẫn kiểm tra quyền truy cập khi dùng member.
4. `field.trySetAccessible()` thành công trong ví dụ vì cả hai class ở unnamed module, nơi các package mở cho reflective access. Sau đó `Field` cụ thể này có thể đọc field.
5. `trySetAccessible()` **không sửa source modifier** `private` thành `public`. Dòng Java `tool.secret` trong class `client.ReflectionAccessDemo` vẫn không biên dịch. Nếu package nằm trong một named module không `opens` phù hợp, `trySetAccessible()` có thể trả `false`.

**Đừng áp kết quả `trySetAccessible=true` của ví dụ classpath lên mọi ứng dụng modular.** Quyền truy cập Reflection phụ thuộc vào vị trí caller, module và cấu hình mở package; ta sẽ kiểm chứng bằng ví dụ JPMS.

### Compile-time access và Reflection là hai đường khác nhau

Dòng sau cố tình **không biên dịch**, khi thêm vào class `client.ReflectionAccessDemo` ở trên:

~~~java
System.out.println(tool.secret); // lỗi: secret có quyền private
~~~

Không có cách chuyển một phép truy cập Java source bị compiler từ chối thành hợp lệ chỉ bằng việc Reflection trước đó đã gọi `setAccessible(true)`. Reflection là một thao tác runtime trên `Field`/`Method`, không sửa JLS access rules của mã nguồn khác.

Ngược lại, một method `public` được compile chấp nhận không có nghĩa framework luôn gọi được nó trên mọi `Object` tùy ý: khi invoke cần đúng receiver, số/kiểu tham số, và có thể bị exception từ body method. **Access permission là điều kiện cần, chưa phải toàn bộ hợp đồng sử dụng thành phần.**

## 3. “Thấy lớp” nhưng không được dùng lớp: package-private type

Một top-level class không khai báo `public` chỉ có package access. Tuy vậy file `.class` của nó vẫn có thể được class loader tìm, và Reflection có thể quan sát nhiều metadata bên trong.

**`src/internal/PackageTool.java`**

~~~java
package internal;

class PackageTool {
    public PackageTool() {}

    public String run() {
        return "ok";
    }
}
~~~

Class `PackageTool` là **package-private**, dù constructor và `run()` được khai báo `public`. Tạo caller ở package khác.

**`src/client/PackageVisibilityDemo.java`**

~~~java
package client;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class PackageVisibilityDemo {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("internal.PackageTool");
        System.out.println("found=" + type.getSimpleName());

        Constructor<?> constructor = type.getDeclaredConstructor();
        System.out.println("constructor.canAccess=" +
                           constructor.canAccess(null));

        try {
            constructor.newInstance();
        } catch (IllegalAccessException ex) {
            System.out.println("newInstance=IllegalAccessException");
        }

        System.out.println("openConstructor=" +
                           constructor.trySetAccessible());
        Object value = constructor.newInstance();

        Method method = type.getMethod("run");
        System.out.println("methodFound=" + method.getName());
        System.out.println("method.canAccess=" + method.canAccess(value));

        try {
            method.invoke(value);
        } catch (IllegalAccessException ex) {
            System.out.println("invoke=IllegalAccessException");
        }

        System.out.println("methodOpen=" + method.trySetAccessible());
        System.out.println("result=" + method.invoke(value));
    }
}
~~~

~~~sh
javac --release 17 -d out src/internal/PackageTool.java src/client/PackageVisibilityDemo.java
java -cp out client.PackageVisibilityDemo
~~~

**Stdout:**

~~~text
found=PackageTool
constructor.canAccess=false
newInstance=IllegalAccessException
openConstructor=true
methodFound=run
method.canAccess=false
invoke=IllegalAccessException
methodOpen=true
result=ok
~~~

Phân tích:

- `Class.forName("internal.PackageTool")` tìm được runtime type trên classpath, **không biến kiểu đó thành accessible type** đối với package `client`.
- `constructor` được lấy qua `getDeclaredConstructor()`; `method` được lấy qua `getMethod("run")` bởi `run()` là method `public`. Hai kết quả tìm metadata này không bảo đảm việc khởi tạo hay invoke hợp lệ.
- `Constructor.newInstance()` và `Method.invoke()` đều kiểm tra quyền, bao gồm **quyền truy cập declaring class**. Chúng bị từ chối trước khi bật suppression.
- `trySetAccessible()` thành công trong thí nghiệm vì các package nằm trong unnamed module. Sau đó Reflection có thể thao tác trên những đối tượng phản chiếu ấy.
- Nếu thêm `import internal.PackageTool;` hoặc viết `new internal.PackageTool()` trong source ở `client`, compiler vẫn báo lỗi vì class không `public`.

**Điểm cần ghi nhớ:** class/method “có mặt” và “public member” vẫn chưa đủ; declaring type phải accessible từ caller. Nhận được `Class<?>` là bằng chứng tồn tại, không phải giấy phép sử dụng mọi thành phần của class.

## 4. `getMethod` so với `getDeclaredMethod`: phạm vi tìm kiếm, không phải quyền

Reflection có hai nhóm API thường gây hiểu nhầm:

| API | Phạm vi tìm kiếm thông thường | Không chứng minh được điều gì? |
| --- | --- | --- |
| `Class.getMethod(name, types...)` | Method `public` nhìn thấy trong class và method `public` kế thừa phù hợp | Caller có quyền `invoke` với receiver bất kỳ |
| `Class.getMethods()` | Danh sách các method `public` của class và những method `public` kế thừa | Declaring class của tất cả method đều accessible từ caller |
| `Class.getDeclaredMethod(name, types...)` | Method khai báo trực tiếp trong class, kể cả `private`/protected/package-private; không duyệt inherited method | Caller được phép gọi body method |
| `Class.getDeclaredMethods()` | Tập các method khai báo trực tiếp, mọi access modifier | Mọi method trong mảng đều được phép invoke |
| `Class.getField(...)` / `getDeclaredField(...)` | Tương tự đối với field: `public` nhìn thấy so với khai báo trực tiếp | Caller được phép đọc/ghi field |
| `Class.getConstructor(...)` / `getDeclaredConstructor(...)` | Constructor `public` so với constructor khai báo trực tiếp | Caller được phép tạo instance |

Câu nói **“`getDeclaredMethod` lấy được private method”** chỉ nói về khả năng *truy vấn metadata*. Quyền gọi nó là bước khác. Nếu dùng `getMethod` mà không tìm thấy method `private`, `NoSuchMethodException` không hề chứng minh phương thức ấy không tồn tại; có thể chỉ là đã chọn sai phạm vi tìm.

Ngoài Java access, các phép tra cứu metadata có thể ném exception khác (chẳng hạn `SecurityException` trong môi trường áp chính sách liên quan); đừng khẳng định “mọi người luôn được xem mọi metadata”.

### Các check runtime cần dùng đúng mục đích

Với `Field`, `Method` và `Constructor` (đều kế thừa `AccessibleObject`):

- `canAccess(Object target)`: hỏi **caller hiện tại** có thể dùng reflected object này trên target tương ứng không, xét cả trạng thái suppression của chính reflected object. Với **instance field/method**, target phải là instance thích hợp; với **static field/method** và constructor, truyền `null`. Gọi sai loại target có thể nhận `IllegalArgumentException`; không dùng `canAccess` như hàm trả `false` cho mọi target sai.
- `trySetAccessible()`: **thử bật** suppression của Java access checks; trả `true` hoặc `false` khi không thể theo quy tắc module. Không phải phép truy vấn không tác dụng phụ: khi thành công nó **thay đổi accessible flag** của reflected object.
- `setAccessible(true)`: yêu cầu bật suppression; có thể ném `InaccessibleObjectException` khi bị module chặn, và một số trường hợp còn có `SecurityException`.
- `isAccessible()`: đã deprecated từ Java 9. Tên dễ gây hiểu nhầm; nó chỉ đọc **flag suppression**, không xác nhận caller có quyền thực tế. Ưu tiên `canAccess(target)` cho câu hỏi “dùng được ngay không?”.
- `getModifiers()` với `Modifier.isPublic/isPrivate/isProtected(...)`: mô tả **modifier được khai báo**, không tự xác nhận toàn bộ quyền của một caller cụ thể. Còn phải xét declaring class, package, receiver và module.

**Ví dụ quan trọng:** một `public Method` có `isAccessible() == false` theo giá trị mặc định của accessible flag nhưng `canAccess(obj) == true` nếu caller được quyền public access. Vì thế `isAccessible() == false` không được diễn giải thành “bị cấm gọi”.

### Access không đồng nghĩa với khả năng thay đổi giá trị

Ngay cả khi `trySetAccessible()` trả `true`, một số final fields vẫn không được write qua reflection, như `static final` fields, final fields trong records và hidden classes theo Java 17 API. Việc đổi suppression flag **không bãi bỏ toàn bộ các ràng buộc bất biến và tính hợp lệ của thao tác**. Tương tự, một reflective method call có quyền vẫn cần receiver và arguments đúng kiểu.

## 5. JPMS (Java 9+): `requires`, `exports` và `opens` quyết định những quyền khác nhau

Từ Java 9, với **named modules**, một type hay member `public` chưa đủ để API sử dụng xuyên module. Cần xét module graph và package directives.

| Cơ chế | Ý nghĩa chính | Điều không được suy ra |
| --- | --- | --- |
| `requires another.module;` | Tạo quan hệ đọc module cho mã của module hiện tại; hỗ trợ việc dùng public API được export | Module được đọc tự động mở private members |
| `exports p;` | Expose public/protected API của package `p` cho các module được phép đọc module nguồn | Cho phép truy cập private member của `p` bằng `setAccessible(true)` |
| `exports p to consumer.mod;` | Chỉ export package cho module được chỉ rõ | Các module khác cũng nhìn thấy API để compile |
| `opens p;` | Cho phép deep reflection vào package `p` ở runtime cho các module khác | Cho phép source ở module khác import type của package đó khi chưa `exports` |
| `opens p to consumer.mod;` | Chỉ mở package cho deep reflection của module được chỉ rõ | Mở cho mọi module trên module path |
| `open module m { ... }` | Mở các package của module để Reflection theo hợp đồng của open module | Tự động thay mọi public API hoặc thiết kế encapsulation thành an toàn |
| `--add-opens source.module/pkg=target.module` | Bổ sung quyền mở package lúc chạy cho module đích được chỉ định | Sửa đổi source modifier, quan hệ kế thừa hoặc quyền compile-time |
| `--add-exports source.module/pkg=target.module` | Bổ sung export cho module đích theo cấu hình chạy/biên dịch phù hợp | Tự cho phép private-field deep reflection như `--add-opens` |

**Phân biệt trọng tâm:**

- **`exports`** hỗ trợ việc compile/link và reflective access thông thường tới API `public` có declaring type accessible. Nó **không** tự cho phép deep reflection vào private members.
- **`opens`** hỗ trợ reflective access ở runtime, kể cả những thành phần không public nếu có API/quyền phù hợp; riêng `opens` **không** tạo quyền import dùng trực tiếp như `exports`.
- Với named modules, `public` của class/method chỉ là điều kiện thuộc **ngôn ngữ**, còn export/open thuộc **ranh giới module**.
- Unnamed module (ứng dụng classpath thông thường) có tính chất mở khác named module: các package của unnamed module mở cho reflective access, nên kết quả các ví dụ classpath phía trên có thể khác ứng dụng triển khai trên module path.

Đối với Reflection, tài liệu `AccessibleObject` còn có một điểm tinh tế: khi thực hiện phép kiểm tra access trên reflected object, runtime **giả định quan hệ đọc module** cho mục đích kiểm tra này. Vì vậy không nên dùng `field.canAccess(...)` như phép thay thế duy nhất cho việc kiểm tra `requires` trong source. Khi cần khẳng định module đang đọc module khác, dùng `Module.canRead(...)` và đánh giá module graph thực tế; khi cần kiểm tra package export/open, dùng `Module.isExported(...)` / `Module.isOpen(...)` với module đích phù hợp.

### Ví dụ 3: type `public` dùng được, private field thấy được nhưng Reflection bị module chặn

Tạo ứng dụng gồm hai named modules. Thư mục và tên tệp:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── example/library/api/Account.java
└── com.example.app/
    ├── module-info.java
    └── example/app/Main.java
~~~

**`src/com.example.library/module-info.java`**

~~~java
module com.example.library {
    exports example.library.api;
}
~~~

**`src/com.example.library/example/library/api/Account.java`**

~~~java
package example.library.api;

public class Account {
    private String pin = "4242";

    public String status() {
        return "READY";
    }
}
~~~

**`src/com.example.app/module-info.java`**

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**`src/com.example.app/example/app/Main.java`**

~~~java
package example.app;

import example.library.api.Account;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account();
        System.out.println("public=" + account.status());

        Field field = Account.class.getDeclaredField("pin");
        System.out.println("fieldFound=" + field.getName());
        System.out.println("canAccess=" + field.canAccess(account));

        boolean enabled = field.trySetAccessible();
        System.out.println("trySetAccessible=" + enabled);
        if (enabled) {
            System.out.println("fieldValue=" + field.get(account));
        } else {
            System.out.println("fieldValue=DENIED");
        }

        try {
            field.setAccessible(true);
            System.out.println("setAccessible=enabled");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible=InaccessibleObjectException");
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên từ thư mục chứa `src`:

~~~sh
javac --release 17 -d mods --module-source-path src src/com.example.library/module-info.java src/com.example.library/example/library/api/Account.java src/com.example.app/module-info.java src/com.example.app/example/app/Main.java
java --module-path mods -m com.example.app/example.app.Main
~~~

**Stdout khi library chỉ `exports`, chưa `opens`:**

~~~text
public=READY
fieldFound=pin
canAccess=false
trySetAccessible=false
fieldValue=DENIED
setAccessible=InaccessibleObjectException
~~~

Giải thích:

1. Module `com.example.app` có `requires com.example.library` và package `example.library.api` đã được export. Vì vậy caller compile và gọi `account.status()` bình thường.
2. `getDeclaredField("pin")` vẫn lấy được metadata `Field` cho trường private.
3. `field.canAccess(account)` là `false`. Khi chưa mở package, `trySetAccessible()` không bật được suppression qua module boundary và trả `false`.
4. `setAccessible(true)` yêu cầu tương tự, nhưng thay vì trả `false` nó ném `InaccessibleObjectException`. Cách bắt exception ở trên chỉ giúp hiển thị trường hợp bị module từ chối; không phải mọi nguyên nhân cấm Reflection đều cùng loại exception.
5. Trường `pin` được đánh dấu `private` và thuộc một named module chưa mở package. `exports` cung cấp public API chứ không cho phép deep reflection vào trường này.

**Thử cấp quyền mở package khi chạy**, giữ nguyên toàn bộ source và class files:

~~~sh
java --module-path mods --add-opens com.example.library/example.library.api=com.example.app -m com.example.app/example.app.Main
~~~

**Stdout của lần chạy có `--add-opens`:**

~~~text
public=READY
fieldFound=pin
canAccess=false
trySetAccessible=true
fieldValue=4242
setAccessible=enabled
~~~

Một alternative ở source module library là thêm:

~~~java
module com.example.library {
    exports example.library.api;
    opens example.library.api to com.example.app;
}
~~~

Sau khi **biên dịch lại**, module đích `com.example.app` có thể deep-reflect vào package được mở. Nếu framework không cần Java source trực tiếp import API, đôi khi thiết kế chỉ dùng `opens`, nhưng phải xét từng API và module resolution cụ thể.

**Lựa chọn thiết kế:** mở đúng package cho đúng module consumer nếu thật sự cần, thay vì mở toàn bộ module vô điều kiện. Không dùng `--add-opens` để thay thế thiết kế public API ở mọi nơi.

## 6. Method Handles: nhận được `Class` không đủ để có `Lookup` phù hợp

`java.lang.invoke.MethodHandles.Lookup` là một đối tượng mang **ngữ cảnh quyền truy cập**. Với `findVirtual`, `findStatic`, `findGetter`, `findSetter` hoặc `findConstructor`, runtime xét quyền của lookup và declaring type/member trước khi trả `MethodHandle`.

Tức là:

- `Class<?>` và tên member mô tả **cái gì cần tìm**.
- `MethodHandles.Lookup` mô tả **ai đang yêu cầu truy cập và có mode nào**.
- Không thể suy ra “lấy được `Class<?>`” → “tạo được mọi method handle trên class ấy”.

`MethodHandles.lookup()` tạo lookup có quyền theo **class gọi**; `MethodHandles.publicLookup()` rất hạn chế, chỉ dùng public members/types trong các package được export theo điều kiện của API. `MethodHandles.privateLookupIn(targetClass, callerLookup)` có thể tạo lookup quyền private cho target khi caller có quyền tương ứng; ở **hai named modules khác nhau**, còn cần quan hệ reads và package nguồn `opens` cho module caller. Nó không phải lệnh vượt qua mọi module boundary.

### Ví dụ 4: cùng class, lookup thường bị từ chối, private lookup được phép

Dùng lại `src/catalog/PublicTool.java` ở ví dụ 1, giữ field `private String secret = "inside";`. Tạo file mới **`src/client/LookupDemo.java`**:

~~~java
package client;

import catalog.PublicTool;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class LookupDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        try {
            lookup.findGetter(PublicTool.class, "secret", String.class);
        } catch (IllegalAccessException ex) {
            System.out.println("findGetter=IllegalAccessException");
        }

        MethodHandles.Lookup privileged =
            MethodHandles.privateLookupIn(PublicTool.class, lookup);
        MethodHandle getter =
            privileged.findGetter(PublicTool.class, "secret", String.class);

        System.out.println("value=" +
                           (String) getter.invoke(new PublicTool()));
    }
}
~~~

~~~sh
javac --release 17 -d out src/catalog/PublicTool.java src/client/LookupDemo.java
java -cp out client.LookupDemo
~~~

~~~text
findGetter=IllegalAccessException
value=inside
~~~

Trong ví dụ classpath, `client.LookupDemo` không được đọc private field qua lookup mặc định. `privateLookupIn` thành công vì hai class thuộc unnamed module có thể deep-reflect theo quy tắc API. Nếu chuyển `PublicTool` sang **named module khác** mà không mở package cho caller, thao tác `privateLookupIn` có thể ném `IllegalAccessException`.

Khác với `Field.trySetAccessible()`, đây là một cơ chế tạo lookup/method handle với quyền tương ứng. Đừng trộn lẫn hai API hoặc giả định đổi accessible flag của `Field` sẽ cấp quyền cho mọi `Lookup` đã có.

## 7. `protected`: “được nhìn thấy bởi subclass” vẫn có điều kiện receiver

`protected` đặc biệt dễ nhầm ở ranh giới package. Trong **cùng package**, những thành phần `protected` nhìn chung truy cập được theo quy tắc package. Ở **package khác**, cần ngữ cảnh subclass hợp lệ và đối với instance member, JLS còn áp quy tắc lên **kiểu của biểu thức receiver**.

Ví dụ minh họa (mỗi phần ở file/package riêng, không biên dịch các dòng được ghi chú lỗi):

**`src/base/Parent.java`**

~~~java
package base;

public class Parent {
    protected String name() {
        return "parent";
    }
}
~~~

**`src/child/Child.java`**

~~~java
package child;

import base.Parent;

public class Child extends Parent {
    public String allowed() {
        return this.name();  // hợp lệ: gọi trên this của subclass
    }

    public String alsoAllowed(Child other) {
        return other.name(); // hợp lệ: receiver có kiểu Child
    }

    // Nếu bỏ comment, dòng dưới không biên dịch:
    // public String forbidden(Parent other) { return other.name(); }
}
~~~

Ngay cả khi `other` thực tế tham chiếu instance `Child`, compiler vẫn xét **kiểu của biểu thức** khi kiểm tra protected access theo JLS `6.6.2`. “Tôi là subclass” chưa đủ để gọi `other.name()` với mọi biến kiểu `Parent` ở package khác. Với Reflection, access checks cũng xét caller và receiver theo quy tắc API; `Modifier.isProtected(...) == true` không phải kết luận cuối cùng.

## 8. Java runtime còn những ranh giới nào?

### Classpath/ClassLoader không tự cấp phép Java access

Class loader quyết định việc tìm và định nghĩa class. Java access control (source/JVM/Reflection) quyết định việc dùng kiểu/member từ ngữ cảnh caller. Kết quả `Class.forName(...)` thành công cho biết runtime đã tìm một class trong ngữ cảnh loader thích hợp; nó không cam kết caller có quyền gọi private constructor, đọc field, hoặc invoke bất kỳ method nào.

Ngược lại, một class `public` trong exported package vẫn có thể không load được nếu dependency không có, phiên bản bytecode sai, module không được resolve hoặc class initialization thất bại. **Được phép truy cập** không có nghĩa thao tác chắc chắn thành công về mặt kỹ thuật.

### Scope, access, reflection metadata và security là các câu hỏi khác nhau

- **Scope:** tên `local variable` chỉ tồn tại trong block; không phải vì nó có access modifier `private`.
- **Java access:** `public/protected/package-private/private` cùng declaring type và module quyết định được phép tham chiếu từ source/ngữ cảnh phù hợp.
- **Reflection metadata:** `getDeclared*` có thể trả về member nonpublic; việc tìm được không xác nhận caller được thao tác.
- **Suppression:** `trySetAccessible`/`setAccessible` có thể cho phép một số thao tác runtime theo hợp đồng của API và module, không sửa khai báo thành phần.
- **Runtime linkage:** mã bytecode bị tạo/sửa tránh compiler có thể gặp `IllegalAccessError` khi JVM liên kết một tham chiếu bất hợp lệ. Đây không phải cùng exception với `IllegalAccessException` của Reflection.
- **Method Handles:** `Lookup` có quyền và mode riêng; `privateLookupIn` bị ràng buộc bởi module và độ tin cậy của caller lookup.
- **Encapsulation:** `private` là hàng rào truy cập ở mức Java language/runtime, không phải cơ chế mã hóa dữ liệu. Với quyền Runtime phù hợp, một số framework vẫn có thể introspect; hãy thiết kế và bảo vệ bí mật theo yêu cầu an ninh riêng.

### Nestmates và private access

Java 11+ hỗ trợ *nest-based access control*: các class cùng một nest hợp lệ (ví dụ một class ngoài và một số nested classes) có thể truy cập private members của nhau theo quy tắc JVM. Vì vậy ví dụ đặt tất cả các lớp dưới một **top-level outer class** đôi khi khiến `Field.canAccess` trả `true` dù đang cố minh họa truy cập bị cấm. Các ví dụ phần 2–3 cố tình tách source thành package/class độc lập để quan sát kết quả rõ ràng.

Điểm này không thay đổi nguyên tắc: phải xét **caller thực tế**. Hai đoạn code cùng đọc một `private Field` có thể cho `canAccess(...)` khác nhau vì caller thuộc nest/package/module khác nhau.

### Một `Method` có thể được lấy nhưng không invoke được, hoặc invoke được nhưng body ném lỗi

Có `Method` hợp lệ chưa bảo đảm `invoke` thành công. Với instance method, receiver phải phù hợp; argument phải đúng; quyền truy cập phải hợp lệ; method body có thể ném exception và Reflection sẽ bọc bằng `InvocationTargetException`. Đặc biệt, **dynamic dispatch** có thể chọn override của lớp con khi gọi instance method, nhưng điều đó độc lập với việc caller có đủ quyền gọi method qua Reflection. Không nên gộp lỗi access với lỗi chọn implementation.

## 9. Phân loại lỗi khi điều tra ứng dụng thực tế

| Hiện tượng | Vấn đề thường nằm ở đâu? | Hướng kiểm tra |
| --- | --- | --- |
| `cannot find symbol` khi compile | Tên, import, scope, dependency | Tên đầy đủ, classpath/module path, scope |
| Compiler báo type/member “not public” hoặc “has private access” | Java source access | Declaring class, modifier, package, subclass |
| `ClassNotFoundException` | Runtime không tìm được class theo loader/path, hoặc cách tìm không hợp lệ | Binary name, class loader, module resolution |
| `NoSuchMethodException` / `NoSuchFieldException` | Không tìm thấy thành phần theo API tra cứu/chữ ký | `get*` hay `getDeclared*`; kiểu tham số chính xác |
| `IllegalAccessException` tại `Field.get`/`Method.invoke`/`Constructor.newInstance` | Reflection access check từ chối | `canAccess`, declaring type, caller, module `exports/opens` |
| `trySetAccessible() == false` | Không bật suppression được theo quy tắc access/module | Package có `opens` cho caller không; quyền caller |
| `InaccessibleObjectException` tại `setAccessible(true)` | Không thể mở access theo ràng buộc module/quyền | Named modules, `opens`, `--add-opens` |
| `IllegalAccessException` tại `privateLookupIn`/`findGetter` | Lookup thiếu quyền, mode hoặc module access | `Lookup` caller, readability, package `opens` |
| `IllegalAccessError` khi thực thi bytecode | JVM linkage/runtime access check thấy tham chiếu bất hợp lệ | Build version, modifier thay đổi, generated bytecode, modules |
| `InvocationTargetException` sau `Method.invoke` | Target method đã chạy rồi ném lỗi | `getCause()`; stack trace của method gốc |
| `IllegalArgumentException` khi gọi access API | Target/argument không phù hợp | Static vs instance, declaring class, kiểu/số tham số |

**Phân tích theo thứ tự** để tránh đi sai hướng:

1. **Xác định nơi thất bại:** source compile, class loading, metadata lookup, access check, invoke hay code bên trong target?
2. **Xác định caller thực tế:** class/package/module nào đang gọi `get`/`invoke`/`Lookup`? Đừng chỉ xem class sở hữu object.
3. **Xác định kiểu khai báo và member:** `getDeclaringClass()`, `getModifiers()`, tên, chữ ký, static/instance. Member `public` trong declaring class inaccessible vẫn có thể bị chặn.
4. **Xác định receiver:** cho instance member, kiểm tra runtime type và quy tắc access/override; cho `canAccess` trên static member hoặc constructor, truyền `null`.
5. **Xác định module boundary:** khi named modules, kiểm tra `requires`/readability, `exports` cho public API, `opens` cho deep reflection.
6. **Chọn API kiểm chứng:** `canAccess` để hỏi có dùng được ngay không; `trySetAccessible` chỉ khi thật sự muốn bật suppression; `Module.isOpen/isExported` cho package-level module policy.
7. **Chọn giải pháp đúng mức:** ưu tiên public API hoặc method handle do module đích chủ động cung cấp; chỉ mở package hoặc bypass checks khi có nhu cầu kiến trúc rõ ràng. Không mở toàn bộ JDK internals chỉ để che đi lỗi thiết kế.

### Mẫu kiểm tra metadata cho công cụ chẩn đoán

Đoạn sau là **snippet minh họa**, sử dụng biến `field` (kiểu `Field`) và `receiver` có sẵn; không phải chương trình độc lập:

~~~java
Class<?> owner = field.getDeclaringClass();
Class<?> caller = MyInspector.class;

System.out.println("owner=" + owner.getName());
System.out.println("modifier=" +
    java.lang.reflect.Modifier.toString(field.getModifiers()));
System.out.println("ownerModule=" + owner.getModule().getName());
System.out.println("callerModule=" + caller.getModule().getName());
System.out.println("canRead=" +
    caller.getModule().canRead(owner.getModule()));
System.out.println("packageExported=" +
    owner.getModule().isExported(owner.getPackageName(), caller.getModule()));
System.out.println("packageOpen=" +
    owner.getModule().isOpen(owner.getPackageName(), caller.getModule()));
System.out.println("usableNow=" + field.canAccess(receiver));
~~~

Trong snippet, `receiver` phải hợp lệ cho loại field đang xét; với `static Field`, thay bằng `null`. `MyInspector` là tên lớp minh họa nơi phát sinh caller; trong ứng dụng thật dùng đúng class làm điểm kiểm tra. `Module.getName()` có thể trả `null` cho unnamed module, nên output phụ thuộc môi trường; **không** trình bày đoạn này như chương trình có stdout cố định.

## 10. Tự kiểm tra

**Câu 1.** `getDeclaredField("secret")` trả về `Field` của trường `private`. Có chắc `Field.get(instance)` thành công không?

**Đáp án:** Không. Tra cứu metadata khác với quyền dùng field. Kiểm tra `canAccess(instance)` và các ràng buộc caller/module trước khi thao tác.

**Câu 2.** Class `internal.PackageTool` là package-private nhưng khai báo `public void run()`. Mã ngoài package dùng `Class.forName` tìm được class. Có thể viết `new internal.PackageTool().run()` trong source khác package không?

**Đáp án:** Không. Declaring class không accessible từ package ngoài. Cả constructor và method có thể được Reflection tìm ra, nhưng thao tác reflective vẫn phải qua access checks.

**Câu 3.** Vì sao `method.isAccessible() == false` chưa chắc có nghĩa method không invoke được?

**Đáp án:** API deprecated này báo flag suppression đang tắt. Một method `public` thuộc declaring type accessible vẫn invoke bình thường với flag tắt. Dùng `canAccess(target)` phù hợp ngữ cảnh.

**Câu 4.** Module `lib` khai báo `exports api;`, consumer có `requires lib;`. Có thể đọc private field của `api.PublicType` bằng `setAccessible(true)` từ consumer không?

**Đáp án:** Không mặc định. `exports` hỗ trợ public API; muốn deep reflection qua module boundary thường cần package `opens` cho consumer hoặc cấu hình mở package tương đương.

**Câu 5.** Nếu module chỉ khai báo `opens api;` nhưng không `exports api;`, consumer có tự động được `import api.PublicType` không?

**Đáp án:** Không. `opens` chủ yếu phục vụ reflective access runtime; nó không tự cấp quyền source-level access của `exports`.

**Câu 6.** Vì sao `privateLookupIn` có thể ném `IllegalAccessException` dù `Class.forName` đã tìm được class?

**Đáp án:** `Class.forName` trả metadata/kiểu; `Lookup` mang quyền caller và `privateLookupIn` kiểm tra quyền, readability và package openness theo API.

**Câu 7.** Trong một subclass khác package, có phải gọi `parentReference.protectedMethod()` luôn hợp lệ vì caller là subclass?

**Đáp án:** Không. Với protected instance member ngoài package, JLS còn ràng buộc kiểu biểu thức receiver. `this.protectedMethod()` có thể hợp lệ trong khi biến kiểu `Parent` không được phép gọi.

**Câu 8.** Khi `Method.invoke` trả `InvocationTargetException`, có thể kết luận thiếu access permission không?

**Đáp án:** Không. Phần lớn trường hợp đây là exception do target method ném và bị Reflection bọc lại. Cần xem `getCause()`; lỗi access của Reflection thường có loại khác như `IllegalAccessException`.

## 11. Tài liệu chuẩn Java 17 để đối chiếu

- JLS `6.3 (Scope of a Declaration) và `6.6 (Access Control), bao gồm luật `protected` qua package: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html
- JLS `7.7.2 (Exported and Opened Packages): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2
- Java SE 17 `Class`: `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `AccessibleObject`: `canAccess`, `trySetAccessible`, `setAccessible` và ghi chú về module readability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17 `Field` và `Method`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 `MethodHandles`, `privateLookupIn` và `Lookup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 `java.lang.Module`: `canRead`, `isExported`, `isOpen`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html

**Ghi nhớ:** *Nhìn thấy* một tên/`Class`/`Field`/`Method` là một sự kiện về **phạm vi, nạp lớp hoặc tra cứu metadata**. *Được phép sử dụng* là kết quả của **access checks trong đúng ngữ cảnh caller**, gồm declaring type, member, receiver, class loader/runtime package, module và API truy cập. Luôn kiểm tra riêng hai câu hỏi để chẩn đoán chính xác và tránh vô tình mở rộng quyền truy cập của ứng dụng.