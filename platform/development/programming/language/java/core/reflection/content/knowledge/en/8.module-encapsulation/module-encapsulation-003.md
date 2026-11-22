# Public reflection khác deep reflection như thế nào trong Java?

Trong Java Reflection, **tra cứu metadata** (`getMethod`, `getDeclaredMethod`) và **thực sự truy cập thành viên** (`invoke`, `Field.get`, `Constructor.newInstance`) là hai bước khác nhau. Bài này phân biệt **public reflection** — sử dụng API public mà caller vốn có quyền truy cập — và **deep reflection** — thao tác cần bỏ qua kiểm tra truy cập Java bằng `trySetAccessible()` hoặc `setAccessible(true)`.

Với named modules, public API dùng xuyên module thường cần `exports`; truy cập private member của module khác thường cần package `opens` cho caller. Đây là hai cách sử dụng Reflection, không phải hai kiểu `Class` hay hai thư viện API riêng. Ví dụ Java 17+ sẽ cho thấy cùng một chương trình thay đổi kết quả như thế nào khi bổ sung quyền mở package.

## 1. Ba lớp câu hỏi cần tách rời

Khi một framework muốn gọi `Person.secret()` hoặc đọc `Person.name`, hãy trả lời theo đúng thứ tự:

1. **Có tìm được thành viên không?** `getMethod("name")` tìm public method; `getDeclaredMethod("secret")` tìm method khai báo trực tiếp, kể cả private.
2. **Caller có được truy cập thành viên bằng Reflection không?** Quy tắc visibility `public`/`private`, quan hệ giữa class/package, và JPMS `exports`/`opens` quyết định điều này.
3. **Việc sử dụng thực tế có thành công không?** `Method.invoke`, `Field.get`, `Field.set`, `Constructor.newInstance` còn có thể thất bại vì receiver, tham số, trạng thái đối tượng hoặc exception bên trong code được gọi.

Ví dụ:

```java
Method method = type.getDeclaredMethod("secret");
```

Lệnh trên chỉ tra cứu metadata. Nếu `secret` là private và caller ở module khác, `method.invoke(object)` chưa chắc được phép. Cần xét việc package đã được `opens` chưa và caller đã bật quyền reflective access hợp lệ hay chưa.

**Cần nhớ:** `public` là mức truy cập của class/member, còn `exports`/`opens` là quan hệ **package giữa các module**. Một method `public` nằm trong class `public` của package không được export vẫn có thể không gọi được từ module khác theo public reflection.

## 2. So sánh trực tiếp

| Khía cạnh | Public reflection | Deep reflection |
|---|---|---|
| Mục đích | Sử dụng API công khai qua runtime metadata | Truy cập thành viên hoặc kiểu không được phép truy cập theo Java access checks thông thường |
| API tra cứu điển hình | `getMethod`, `getField`, `getConstructor` | `getDeclaredMethod`, `getDeclaredField`, `getDeclaredConstructor` |
| Có thể thấy metadata private? | Các API `get...` không trả về private member | Các API `getDeclared...` có thể trả metadata private; **chỉ tra cứu chưa đủ để truy cập** |
| Bỏ qua kiểm tra Java access? | Không cần với API public hợp lệ và package được export | Cần yêu cầu qua `trySetAccessible()` hoặc `setAccessible(true)` khi access checks bình thường không cho phép |
| Named module cung cấp package | Thường dùng `exports package.name` hoặc `exports package.name to caller.module` | Thường dùng `opens package.name` hoặc `opens package.name to caller.module` |
| Cho phép import class từ module khác ở compile time? | `exports` cho phép sử dụng public types khi có module readability phù hợp | Chỉ `opens` không biến package thành API được import như `exports` |
| Rủi ro thiết kế | Phụ thuộc vào hợp đồng API công khai | Phụ thuộc vào chi tiết nội bộ và có thể phá vỡ encapsulation |

Bảng mô tả tình huống **giữa các named modules** thông thường. Có ngoại lệ trong quy tắc `AccessibleObject` cho cùng module, các package vốn mở, hoặc một số public/protected static member với quan hệ subclass phù hợp. Không suy ra rằng cứ thấy `private` là luôn cần sửa `module-info.java`: nếu caller và lớp đích **cùng module**, yêu cầu bật reflective access có thể hợp lệ dù package không `opens` ra ngoài.

## 3. Tra cứu metadata không đồng nghĩa được gọi

Các API tra cứu trên đối tượng `Class<?>`:

```java
// Các đoạn dưới là ví dụ ký hiệu, giả định Sample.class đã tồn tại.
Method publicMethod = Sample.class.getMethod("execute");
Method declaredMethod = Sample.class.getDeclaredMethod("internal");
Field declaredField = Sample.class.getDeclaredField("state");
Constructor<Sample> ctor = Sample.class.getDeclaredConstructor();
```

Phân biệt:

- `getMethod`, `getField`, `getConstructor` chỉ tìm những thành viên **public** theo quy tắc tương ứng; với method/field có thể bao gồm thành viên được kế thừa, còn constructor thì không được kế thừa.
- `getDeclaredMethod`, `getDeclaredField`, `getDeclaredConstructor` tra cứu các thành viên **khai báo trực tiếp** trên lớp, bao gồm public và non-public; không tự đi qua superclass.
- `getDeclaredMethods()` hay `getDeclaredFields()` có thể liệt kê metadata của private members mà không thực hiện được quyền gọi/đọc chúng. **Không cần `opens` chỉ để dùng `getDeclaredMethod` tìm tên method** trong trường hợp minh họa thông thường.
- `Method.invoke`, `Field.get`/`set`, `Constructor.newInstance` mới thực hiện hành động, áp dụng access rules và các điều kiện khác.

Ví dụ đơn giản nếu toàn bộ code nằm trong một package ứng dụng thông thường:

```java
class Example {
    private String secret() {
        return "secret-data";
    }
}
```

```java
Method m = Example.class.getDeclaredMethod("secret");
// Đã có metadata của secret; chưa có quyền gọi method private từ nơi khác.
// Có thể thử m.trySetAccessible(), nếu quan hệ class/module cho phép.
// Chỉ sau khi quyền hợp lệ mới sử dụng m.invoke(instance).
```

Hai đoạn code là **minh họa ngữ nghĩa**, chưa phải chương trình độc lập có `main` và import. Phần kế tiếp có ví dụ đầy đủ biên dịch và chạy được.

## 4. JPMS: vì sao `exports` khác `opens`?

Từ Java 9, `module-info.java` cho phép một named module công bố rõ package nào là API và package nào được mở cho reflective access.

Giả sử module `demo.target` sở hữu package `demo.api`, module `demo.client` chứa caller.

### `exports`: API được sử dụng từ module khác

```java
module demo.target {
    exports demo.api;
}
```

Với khai báo này, `demo.api` được **export** đến mọi module đọc `demo.target`. Nếu `demo.api.Person` là public class và `displayName()` là public method, `demo.client` có thể import/sử dụng class đó và gọi method công khai. Reflection gọi `displayName()` theo access checks bình thường cũng hợp lệ.

`exports` **không cho quyền** truy cập private field/method bằng `setAccessible(true)` từ một module khác. Export cũng không khiến các member package-private/protected tự trở thành public.

Có thể giới hạn API chỉ cho một module:

```java
module demo.target {
    exports demo.api to demo.client;
}
```

### `opens`: cho phép deep reflection tại runtime

```java
module demo.target {
    exports demo.api;
    opens demo.api to demo.client;
}
```

Khi đó `demo.client` có thể tiếp tục dùng API public, đồng thời có quyền **yêu cầu suppress Java language access checks qua Reflection** đối với members trong package `demo.api` theo cơ chế JPMS. Cách `opens ... to ...` giới hạn người nhận tốt hơn so với mở package cho mọi module.

Nếu chỉ khai báo:

```java
module demo.target {
    opens demo.api to demo.client;
}
```

package được mở cho Reflection từ `demo.client`, nhưng **không được export** như API public để `demo.client` import `demo.api.Person` trong Java source một cách thông thường. Framework vẫn có thể sử dụng runtime metadata dựa trên tên lớp và reflective access khi có điều kiện phù hợp.

Cũng có hai dạng rộng hơn:

- `opens demo.api;`: mở package cho deep reflection từ **mọi module**.
- `open module demo.target { ... }`: mở **các package của cả module** cho Reflection. Không nên dùng chỉ để giải quyết nhu cầu của một package.

| Khai báo trong module đích | Public API cho caller ở module khác | Deep reflection từ caller ở module khác |
|---|---|---|
| Không `exports`, không `opens` | Không được tiếp cận như exported public API | Bị giới hạn bởi encapsulation |
| `exports demo.api;` | Có, với class/member public và readability phù hợp | Không cấp quyền vào private members |
| `opens demo.api;` | Không tạo quyền import public API chỉ nhờ `opens` | Được phép yêu cầu suppress access checks |
| `exports demo.api;` và `opens demo.api;` | Có | Có |
| `exports demo.api to demo.client;` và `opens demo.api to demo.client;` | Có, cho `demo.client` | Có, cho `demo.client` |

Trong bảng, “có deep reflection” là **mở khả năng đáp ứng yêu cầu suppress access checks** của core Reflection; code vẫn có thể bị ràng buộc bởi hành vi thành viên, kiểu đối tượng, các trường `final` không được ghi tùy trường hợp và exception lúc thực thi.

## 5. Thí nghiệm Java 17+: cùng source, hai kết quả theo quyền module

Tạo cấu trúc tệp:

```text
reflection-demo/
└── src/
    ├── demo.target/
    │   ├── module-info.java
    │   └── demo/api/Person.java
    └── demo.client/
        ├── module-info.java
        └── demo/app/Main.java
```

**Tệp `src/demo.target/module-info.java`:**

```java
module demo.target {
    exports demo.api;
}
```

**Tệp `src/demo.target/demo/api/Person.java`:**

```java
package demo.api;

public class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String displayName() {
        return name;
    }

    private String internalId() {
        return "id-" + name;
    }
}
```

**Tệp `src/demo.client/module-info.java`:**

```java
module demo.client {
    requires demo.target;
}
```

**Tệp `src/demo.client/demo/app/Main.java`:**

```java
package demo.app;

import demo.api.Person;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Module target = Person.class.getModule();
        Module caller = Main.class.getModule();

        System.out.println("exported: " + target.isExported("demo.api", caller));
        System.out.println("opened: " + target.isOpen("demo.api", caller));

        Person person = new Person("Lan");

        Method publicMethod = Person.class.getMethod("displayName");
        System.out.println("public method: " + publicMethod.invoke(person));

        Method privateMethod = Person.class.getDeclaredMethod("internalId");
        System.out.println("private metadata: " + privateMethod.getName());

        boolean deepAllowed = privateMethod.trySetAccessible();
        System.out.println("deep allowed: " + deepAllowed);

        if (deepAllowed) {
            System.out.println("private method: " + privateMethod.invoke(person));
        }
    }
}
```

**Biên dịch hai named modules bằng JDK 17+** (đứng trong thư mục `reflection-demo`):

```bash
javac -d out --module-source-path src -m demo.target,demo.client
```

### Lần 1: chỉ có `exports`, không có `opens`

```bash
java --module-path out -m demo.client/demo.app.Main
```

Stdout chính xác:

```text
exported: true
opened: false
public method: Lan
private metadata: internalId
deep allowed: false
```

Giải thích:

1. `demo.target` export `demo.api` cho `demo.client`; Java source import `Person` được và gọi public API qua `Method.invoke` thành công.
2. `getDeclaredMethod("internalId")` **vẫn tìm ra metadata của private method**.
3. `trySetAccessible()` trả `false` vì package không open cho module gọi, nên code không đi vào nhánh gọi `internalId()`. Đây là minh chứng cho khác biệt giữa metadata discovery và deep access.

### Lần 2: mở package tại runtime, không sửa source

Chạy với tham số JVM `--add-opens`:

```bash
java --module-path out --add-opens demo.target/demo.api=demo.client -m demo.client/demo.app.Main
```

Stdout chính xác:

```text
exported: true
opened: true
public method: Lan
private metadata: internalId
deep allowed: true
private method: id-Lan
```

Lệnh `--add-opens demo.target/demo.api=demo.client` cấp quyền mở package của **target module** cho **caller module** trong lần chạy này. Không cần thay code `Person`, `Main` hoặc biên dịch lại để quan sát khác biệt. Đây là **quyền truy cập runtime**, không phải quyền import thêm class trong quá trình biên dịch.

### Cách làm tương đương bằng `module-info.java`

Thay nội dung `src/demo.target/module-info.java` bằng:

```java
module demo.target {
    exports demo.api;
    opens demo.api to demo.client;
}
```

Biên dịch lại:

```bash
javac -d out --module-source-path src -m demo.target,demo.client
java --module-path out -m demo.client/demo.app.Main
```

Không cần `--add-opens` ở lần chạy này; stdout giống **lần 2**. Với ứng dụng có cấu trúc module rõ ràng, `opens ... to ...` cho framework cụ thể thường dễ kiểm toán hơn một quyền mở rộng áp dụng không cần thiết.

**Lưu ý:** `--add-opens` phải được truyền cho JVM **trước** `-m` trong ví dụ. Phần `demo.target/demo.api` là `module/package`, bên phải dấu `=` là module được mở quyền. Đường dẫn thư mục `out` chứa các module đã biên dịch.

## 6. `trySetAccessible`, `setAccessible` và `canAccess`

Các đối tượng `Field`, `Method`, `Constructor` kế thừa từ `java.lang.reflect.AccessibleObject`; các API tiêu biểu là:

```java
boolean ok = member.trySetAccessible();
member.setAccessible(true);
boolean canUse = member.canAccess(receiver);
```

Các dòng trên là **các lựa chọn API minh họa**, không phải đoạn chương trình cần gọi liên tiếp. `member` là một `AccessibleObject` thực tế có kiểu `Field`, `Method` hoặc `Constructor`; receiver phụ thuộc loại member.

- `trySetAccessible()`: thử bật quyền **suppress Java language access checks**. Trả `true` nếu cho phép; trả `false` nếu không thể mở theo các ràng buộc đó. Phù hợp với framework muốn hỗ trợ nhiều cấu hình module mà không ném exception khi deep access bị chặn.
- `setAccessible(true)`: yêu cầu bật chế độ này; có thể ném **`InaccessibleObjectException`** nếu không thể bật do encapsulation của module. Với mô hình cũ hoặc access đã mở, lệnh có thể thành công.
- `canAccess(receiver)`: kiểm tra quyền hiện có cho member đối với caller tại thời điểm gọi; đây là truy vấn, **không tự mở** quyền. Với instance field/method, `receiver` phải là đối tượng hợp lệ. Với static field/method và constructor, receiver phải là `null`.

Cụm “suppress Java language access checks” không có nghĩa tắt mọi cơ chế bảo vệ JVM. Một số trường `final` thuộc nhóm **non-modifiable final fields** (chẳng hạn record components hay hidden-class final fields) không thể ghi bằng core Reflection kể cả sau khi `setAccessible(true)` thành công; các ràng buộc runtime khác cũng vẫn tồn tại.

### Thực hành xử lý thất bại

Khi framework chủ động hỗ trợ private members:

```java
Method internal = Person.class.getDeclaredMethod("internalId");
if (!internal.trySetAccessible()) {
    throw new IllegalStateException(
            "Module demo.target must open demo.api to demo.client");
}
Object result = internal.invoke(new Person("Lan"));
```

Đây là **đoạn minh họa** nằm trong module `demo.client` của thí nghiệm, không phải tệp chạy độc lập. Cần cung cấp quyền `opens` hợp lệ trước khi gọi. Với một thư viện dùng thực tế, thông báo lỗi nên mô tả cả module đích, package và module caller được lấy từ `Class.getModule()`, tránh hard-code nếu thư viện hỗ trợ nhiều module.

Không dùng `setAccessible(true)` hàng loạt cho mọi field/method chỉ để “đề phòng”: việc yêu cầu truy cập chi tiết nội bộ nên có mục đích rõ, quyền hẹp và đường xử lý lỗi.

## 7. Public member trong package không export vẫn có thể bị chặn

Xét `demo.target` có thêm package `demo.hidden`, nhưng `module-info.java` chỉ export `demo.api`:

```java
module demo.target {
    exports demo.api;
}
```

Bên trong `demo.hidden` tồn tại `public class HiddenApi` với `public static String status()`. Dù class và method đều ghi `public`, module `demo.client` **không thể import `demo.hidden.HiddenApi` như một public API hợp lệ**, vì package không được export cho nó.

Nếu chương trình có được đối tượng `Class` của `HiddenApi` bằng một đường runtime hợp lệ, việc tra cứu `getMethod("status")` có thể tìm ra metadata. Tuy nhiên, việc gọi qua `Method.invoke` với Java access checks bình thường **không tự động được phép**. Đây là lý do không được đánh đồng hai câu “method được khai báo public” và “module caller có quyền gọi method đó”.

Hai tùy chọn JVM hay bị nhầm:

```bash
# Tăng quyền truy cập public của package chưa export cho demo.client:
--add-exports demo.target/demo.hidden=demo.client

# Mở package cho deep reflection từ demo.client:
--add-opens demo.target/demo.hidden=demo.client
```

Hai dòng này là **các JVM options minh họa**, không phải lệnh shell chạy độc lập. `--add-exports` giải quyết quyền tiếp cận public API của package trong tình huống module đích chưa export; riêng nó không cấp quyền xâm nhập private members bằng deep reflection. `--add-opens` mở quyền reflective access sâu cho package. Hãy chọn đúng tùy mục tiêu, ưu tiên khai báo module rõ ràng hoặc API công khai thay vì nới rộng quyền tùy tiện.

## 8. Ảnh hưởng của classpath, unnamed module và framework

Ứng dụng Java có thể dùng cả **module path** và **classpath**:

- Class được nạp từ classpath thông thường thuộc một **unnamed module**; các package của unnamed module được export và open theo cơ chế tương thích.
- Một **open module** cho phép reflective access vào các package trong module của nó theo quy tắc JPMS.
- Trong **named module thông thường**, các package không tự động export/open cho module khác. Việc di chuyển mã đang chạy trên classpath vào named module có thể làm framework từng truy cập private members gặp lỗi `InaccessibleObjectException`.

Ví dụ:

- **JSON serialization / ORM**: framework thường tìm field hoặc constructor non-public và có thể cần quyền deep reflection. Nếu module `app.model` quản lý các class entity, có thể dùng `opens app.model.entity to some.framework.module;` theo module thực của framework.
- **Dependency injection**: nếu container gọi constructor public từ package được export, public reflection có thể đủ. Nếu container cần private field injection hoặc truy cập non-public constructor, cần xét quyền mở package.
- **Công cụ introspection**: nếu chỉ liệt kê tên method, parameter types hoặc annotation metadata, có thể không cần mở private access. Đừng mở package chỉ vì dùng `getDeclaredMethods()`.
- **API client**: với public interface/service API, `exports` và `getMethod` là lựa chọn tự nhiên, giảm phụ thuộc vào chi tiết triển khai.

**Tên module của framework phải chính xác.** Qualified `opens ... to framework.module` chỉ có hiệu lực với module được nêu đúng tên. Với framework chạy trong unnamed module, một số cấu hình launcher cần dùng `ALL-UNNAMED`, ví dụ `--add-opens my.module/my.pkg=ALL-UNNAMED`; đây là lựa chọn runtime để phục vụ công cụ cũ, không phải mặc định nên áp dụng cho mọi module.

Ngoài core Reflection, `MethodHandles.privateLookupIn` cũng là cơ chế truy cập sâu dưới các điều kiện module phù hợp; nó **không cho phép tự vượt** `opens` của module khác.

## 9. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân điển hình | Hướng giải quyết |
|---|---|---|
| `NoSuchMethodException` khi gọi `getMethod` | Method không public, tên/chữ ký tham số sai, hoặc không tồn tại | Xác nhận đúng tên, parameter types; dùng `getDeclaredMethod` nếu cần metadata của method khai báo trực tiếp |
| `NoSuchFieldException` khi `getField` | Field không public hoặc không tồn tại đúng tên | Kiểm tra field thực tế và cân nhắc `getDeclaredField` |
| `IllegalAccessException` khi `Method.invoke` hoặc `Field.get` | Caller không có quyền access theo visibility và/hoặc module encapsulation | Kiểm tra class/member `public`, package export, hoặc quyền deep reflection hợp lệ |
| `InaccessibleObjectException` ở `setAccessible(true)` | Module đích không open package cho caller | Dùng `opens ... to ...` hoặc `--add-opens` có chủ đích; ưu tiên API public khi có thể |
| `trySetAccessible()` trả `false` | Không thể bật suppression theo quy tắc module/encapsulation | Chọn public API hoặc cấu hình `opens` đúng module; xử lý fallback minh bạch |
| `InvocationTargetException` sau khi được phép invoke | **Code được gọi** ném exception | Xem `getCause()`; đây là lỗi khi thực thi method/constructor, không phải bằng chứng thiếu `opens` |
| Compile báo package không visible | Thiếu `requires`, package chưa export hoặc module graph không phù hợp | Kiểm tra `requires` ở caller, `exports` ở target và module path |
| Hoạt động trên classpath nhưng lỗi khi chuyển sang module path | Strong encapsulation của named modules | Xác định nhu cầu public/deep và khai báo export/open ở phạm vi tối thiểu |

Ở Java 17+, đừng dựa vào cơ chế truy cập trái phép tới JDK internals như trên một số runtime Java cũ. Quy tắc strong encapsulation được tăng cường; chuyển đổi framework cũ nên ưu tiên cập nhật thư viện và cấu hình module đúng phạm vi.

## 10. Những nhầm lẫn cần tránh

1. **“`getDeclaredMethod` đã là deep reflection.”** Chưa đúng: chỉ lấy metadata; deep access phải vượt qua ràng buộc quyền truy cập bằng cơ chế hợp lệ khi cần.
2. **“Class public và method public thì module nào cũng gọi được.”** Sai nếu package không được export phù hợp giữa named modules.
3. **“`exports` cho phép mở private members.”** Sai: export phục vụ public API; `opens` dành cho runtime reflective access sâu.
4. **“`opens` và `exports` tương đương.”** Sai: `opens` không tự cho phép Java source ở module khác import public types như exported package.
5. **“`setAccessible(true)` luôn thành công.”** Sai: có thể ném `InaccessibleObjectException` khi module/package không mở phù hợp.
6. **“`trySetAccessible()` trả false nghĩa là member không tồn tại.”** Sai: metadata đã tìm thấy, nhưng không bật được quyền suppress access checks.
7. **“Method.invoke gặp `InvocationTargetException` chứng tỏ bị module chặn.”** Sai: exception này gói lỗi bên trong method/constructor đã chạy.
8. **“Một package open phải mở cho tất cả.”** Sai: qualified `opens pkg to specific.module` cho phép giới hạn quyền.
9. **“Reflection chỉ đọc metadata cũng cần `--add-opens`.”** Không phải mặc định: hãy phân biệt introspection metadata với deep access trước khi cấp thêm quyền.
10. **“Mở một package nghĩa là framework được ghi mọi field final.”** Sai: nhiều hạn chế của JVM vẫn còn hiệu lực.

## 11. Tự kiểm tra

**Câu 1.** Module `catalog.core` export `catalog.api` chứa `public class Item` và `public String code()`. Module `catalog.client` requires `catalog.core`. Public reflection gọi `code()` được không?

**Trả lời:** Có trong điều kiện class/member public hợp lệ và package được export cho caller. `Item.class.getMethod("code")` trả `Method`; `invoke` với instance hợp lệ có thể chạy mà không cần mở package cho deep reflection.

**Câu 2.** Cùng lớp `Item` có field `private String internalKey`. `getDeclaredField("internalKey")` thành công nhưng `trySetAccessible()` trả false. Điều đó nói gì?

**Trả lời:** Chương trình đã tìm được metadata, nhưng không có quyền bật suppress access checks trong quan hệ class/module hiện tại. Với hai named modules, nên kiểm tra `opens catalog.api to catalog.client` nếu deep reflection thực sự cần thiết.

**Câu 3.** Thêm `exports catalog.api;` có đủ để client đọc private field bằng `Field.get` sau `setAccessible(true)` không?

**Trả lời:** Không. Với caller ở module khác, `exports` không thay `opens`; cần cấu hình mở package phù hợp hoặc thiết kế public API thay thế.

**Câu 4.** Nếu chỉ muốn liệt kê tên các method khai báo trực tiếp, cần gọi `setAccessible(true)` trên toàn bộ method không?

**Trả lời:** Không. `getDeclaredMethods()` trả metadata; đọc tên qua `Method.getName()` không phải thực thi method hay bỏ access checks.

**Câu 5.** Tại sao `--add-opens target.module/p=caller.module` có thể giải quyết lỗi deep reflection trong lần chạy nhưng không làm source `import p.SomeType;` biên dịch được?

**Trả lời:** `--add-opens` là quyền reflective access runtime, khác với xuất public API qua `exports`. Compile-time visibility cần cấu hình module graph và exported package tương ứng.

## Tài liệu chính thức

- Java SE API — `java.lang.reflect.AccessibleObject`: `trySetAccessible`, `setAccessible`, `canAccess`, quy tắc access giữa modules.
- Java SE API — `java.lang.Class`: `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField` và `getModule`.
- Java SE API — `java.lang.Module`: `isExported`, `isOpen` và quan hệ quyền truy cập package.
- Java Language Specification — Chương 7 và phần về modules, packages, access control.
- Java Platform Module System (`java` launcher, `javac`) — các tùy chọn `--module-path`, `--module-source-path`, `--add-exports`, `--add-opens`.

**Ghi nhớ:** Public reflection dùng **API công khai** mà caller được phép truy cập; deep reflection yêu cầu **truy cập sâu vào phần triển khai** và có thể cần suppress access checks. Trong JPMS, `exports` công bố public API, `opens` mở quyền runtime Reflection. Tìm ra `Method`/`Field` không có nghĩa đã được phép gọi hoặc đọc nó.