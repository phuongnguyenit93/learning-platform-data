# Thiết kế thư viện dùng API công khai trước, thông báo rõ member và module gây lỗi truy cập

## 1. Vấn đề: reflection hoạt động trong IDE nhưng lỗi khi chạy theo module

Một thư viện ánh xạ dữ liệu có thể cần đọc thuộc tính `id` của một đối tượng do ứng dụng cung cấp. Cách dễ nghĩ đến là tìm field `private` rồi bật quyền truy cập:

~~~java
Field field = object.getClass().getDeclaredField("id");
field.setAccessible(true);
Object id = field.get(object);
~~~

Kỹ thuật này tạo ra nhiều phụ thuộc không cần thiết: tên field là chi tiết cài đặt; package có thể bị đóng trong Java Platform Module System (JPMS); và một API truy cập được để đọc chưa chắc có quyền ghi. Một dự án chạy được trên class path có thể báo `InaccessibleObjectException` khi chuyển sang named module, dù phần xử lý dữ liệu không đổi.

Trong chương **Quyền reflection** của module Java 18, mục tiêu là xây dựng một thư viện sử dụng được trên các JDK hiện hành: **ưu tiên hợp đồng công khai do đối tượng cung cấp**, sau đó mới cân nhắc reflection cho trường hợp tích hợp thực sự cần; nếu quyền truy cập bị từ chối, lỗi phải nêu **member cụ thể, declaring class, package, module sở hữu và module gọi** để người sử dụng sửa đúng chỗ.

### Tình huống mẫu

Giả sử ứng dụng có lớp:

~~~java
package com.example.model.api;

public final class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
~~~

Thư viện có thể đọc `id` bằng `order.id()`, hoặc nhận một hàm `Order::id` từ phía ứng dụng. Không cần lấy field `private` tên `id`. Nếu lớp đổi cách lưu trữ nội bộ nhưng vẫn giữ phương thức `id()`, lời gọi qua hợp đồng công khai tiếp tục hoạt động.

## 2. Thứ tự lựa chọn khi thiết kế API thư viện

| Lựa chọn | Khi nào phù hợp | Phụ thuộc vào quyền truy cập |
| --- | --- | --- |
| Interface, getter, constructor hoặc factory **công khai** | Có thể định nghĩa hoặc yêu cầu hợp đồng dữ liệu từ phía ứng dụng | Quy tắc truy cập Java thông thường và `exports` phù hợp khi dùng named module. |
| Callback / accessor do người dùng truyền (`Function`, method reference) | Thư viện không thể biết trước kiểu dữ liệu; ứng dụng biết cách trích xuất thuộc tính | Ứng dụng tự quyết định cách đọc dữ liệu, thư viện không cần mở private member. |
| Record component accessor | Đọc dữ liệu của record theo API chuẩn | Dùng accessor công khai của record và phạm vi truy cập đến record. |
| Reflection tới **public method** | Plugin/mapper nhận kiểu ở runtime và không có giao diện chung | Class, member và module phải truy cập được tại nơi gọi. |
| Deep reflection tới `private` / package-private member | Tương thích có chủ đích với định dạng hoặc thư viện cũ, không có API thay thế | Có thể cần `opens`, vẫn chịu giới hạn của JDK và hợp đồng member. |
| API nội bộ hoặc cơ chế bỏ kiểm tra truy cập | Không nên dùng làm chiến lược thiết kế thư viện | Không tạo hợp đồng ổn định trên JDK hiện đại. |

Nếu thư viện chỉ cần dữ liệu, một callback thường giúp giảm coupling:

~~~java
import java.util.function.Function;

public final class IdReader {
    public static <T> String readId(
            T value, Function<? super T, String> accessor) {
        return accessor.apply(value);
    }
}

// Tại phía ứng dụng:
String id = IdReader.readId(order, Order::id);
~~~

Cách này tránh việc thư viện phải biết lớp `Order` cất `id` vào field nào, hoặc module của ứng dụng có mở package nội bộ hay không. Ngoài ra, thư viện có thể cung cấp overload nhận một interface như `HasId` nếu cần hợp đồng dùng chung.

**Nguyên tắc tương thích:** Một thay đổi cài đặt nội bộ của class không nên làm hỏng thư viện nếu API công khai vẫn giữ nguyên. Việc phụ thuộc trực tiếp vào tên field `private` khiến thư viện dễ bị phá vỡ bởi refactor.

## 3. Hai lớp kiểm soát: truy cập member và ranh giới module

Trên Java hiện đại, một member được khai báo `public` chưa đủ để mã ở module khác gọi nó. Trước tiên cần xét **class khai báo member có truy cập được hay không**, sau đó xét thành viên và phạm vi module.

| Trường hợp | Mã Java / reflection từ module khác |
| --- | --- |
| `public` class, `public` method trong package được `exports` cho module gọi | Có thể truy cập qua API công khai, nếu những điều kiện Java khác được đáp ứng. |
| `public` class và `public` method nhưng package của named module **không được export** cho module gọi | Lời gọi phản chiếu có thể tìm ra `Method` nhưng không được phép invoke theo quyền thông thường. |
| `private` field trong package được `exports` nhưng **không opens** cho module gọi | `exports` không tự cấp quyền deep reflection vào `private` field. |
| Package được `opens` cho module thư viện | `trySetAccessible()` có thể cho phép bỏ qua kiểm tra truy cập, tùy kiểu member và các điều kiện khác. |
| Hai lớp ở cùng một module | Các điều kiện mở package giữa module không còn là rào cản tương tự; các quy tắc truy cập Java và quyền ghi của member vẫn tồn tại. |

Với named module, có thể khai báo:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Package `com.example.model.api` cung cấp API công khai cho module khác. Thư viện thông thường chỉ cần dùng các API trong package này; không cần yêu cầu người dùng mở `com.example.model.internal`.

Khi **thật sự** phải hỗ trợ deep reflection trong một package riêng, chủ sở hữu module có thể chủ động cấp quyền có giới hạn:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.mapper;
}
~~~

`opens ... to ...` cho phép reflection sâu từ module `com.example.mapper` tới package được chỉ định. Đó là quyết định của chủ sở hữu module, không nên trở thành yêu cầu mặc định chỉ vì thư viện được cài đặt.

Cũng phải phân biệt:

- `exports` phục vụ quyền truy cập API thông thường (và phản chiếu vào các public member hợp lệ).
- `opens` phục vụ truy cập reflection sâu theo phạm vi được cấp.
- `requires` thể hiện phụ thuộc module khi biên dịch/chạy; nó **không tự mở** private member của module được yêu cầu.
- `--add-opens` có thể hữu ích trong tình huống vận hành/tương thích đã được quyết định, nhưng không thay thế việc thiết kế public API.
- `canAccess(...)` và `trySetAccessible()` giải đáp các câu hỏi khác nhau: kiểm tra khả năng truy cập hiện tại và thử bỏ qua kiểm tra truy cập. `trySetAccessible() == true` không hứa hẹn thao tác ghi vào mọi field `final` sẽ được phép.

Vì vậy thư viện cần báo lỗi có căn cứ, thay vì in một câu chung như “Reflection failed, please add --add-opens”.

## 4. Đừng nhầm tìm thấy member với có quyền sử dụng member

Hai dòng sau có chức năng khác nhau:

~~~java
Method method = type.getMethod("id");          // Tìm public method.
Object value = method.invoke(target);          // Gọi qua kiểm tra truy cập.
~~~

`getMethod("id")` tìm phương thức `public` có tên đó, không có tham số, trên class và những supertype phù hợp. `getDeclaredMethod("id")` chỉ tìm phương thức khai báo trực tiếp trong lớp; nó có thể trả về member không public, nhưng kết quả trả về **không cấp quyền gọi**.

Sau khi có `Method`, `invoke` vẫn có thể ném `IllegalAccessException` nếu quyền truy cập không đủ. Nếu phương thức thực sự được gọi nhưng bản thân nó ném exception, `invoke` bọc nguyên nhân trong `InvocationTargetException`. Hai tình huống này phải được báo khác nhau: một lỗi là *cấu hình truy cập*, lỗi kia là *lỗi trong logic ứng dụng*.

Đối với field, `getDeclaredField` cũng chỉ trả về mô tả member; `get` và `set` còn chịu các kiểm tra riêng. Ví dụ một `static final` field có thể đọc được khi có quyền phù hợp, nhưng việc mở quyền truy cập không khiến nó trở thành field có thể ghi.

## 5. Mẫu Java: đọc qua public accessor và chẩn đoán lỗi đúng module

Ví dụ sau chạy độc lập trên JDK hiện đại. Nó ưu tiên một `public` accessor có tên `id()`, chỉ dùng reflection để tìm method khi kiểu của đối tượng được biết tại runtime. Khi lỗi truy cập xảy ra, thông điệp chỉ ra chữ ký member, declaring class, package và module của hai phía.

Tệp `PublicAccessorReader.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Objects;

public final class PublicAccessorReader {

    public static final class Order {
        private final String id;

        public Order(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    public static String readId(Object target) {
        Objects.requireNonNull(target, "target");

        Class<?> actualType = target.getClass();
        Method method;

        try {
            method = actualType.getMethod("id");
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Missing public accessor id() on "
                            + actualType.getName(), e);
        }

        if (method.getReturnType() != String.class) {
            throw new IllegalArgumentException(
                    "Expected String return type for "
                            + method.toGenericString());
        }

        try {
            return (String) method.invoke(target);
        } catch (IllegalAccessException e) {
            throw new IllegalStateException(accessDiagnostic(method), e);
        } catch (InvocationTargetException e) {
            throw new IllegalStateException(
                    "Accessor executed but threw: "
                            + method.toGenericString(),
                    e.getCause());
        }
    }

    private static String accessDiagnostic(Method method) {
        // Declaring class có thể là superclass hoặc interface, không
        // nhất thiết trùng với target.getClass().
        Class<?> owner = method.getDeclaringClass();
        Module ownerModule = owner.getModule();
        Module libraryModule = PublicAccessorReader.class.getModule();
        String packageName = owner.getPackageName();

        return "Cannot invoke member " + method.toGenericString()
                + "; declaringClass=" + owner.getName()
                + "; package=" + packageName
                + "; ownerModule=" + moduleName(ownerModule)
                + "; callerModule=" + moduleName(libraryModule)
                + "; sameModule=" + (ownerModule == libraryModule)
                + "; ownerClassPublic="
                        + Modifier.isPublic(owner.getModifiers())
                + "; memberPublic="
                        + Modifier.isPublic(method.getModifiers())
                + "; exportedToCaller="
                        + ownerModule.isExported(packageName, libraryModule)
                + "; openedToCaller="
                        + ownerModule.isOpen(packageName, libraryModule);
    }

    private static String moduleName(Module module) {
        return module.isNamed()
                ? module.getName()
                : "<unnamed module>";
    }

    public static void main(String[] args) {
        System.out.println(readId(new Order("ORD-42")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PublicAccessorReader.java
java PublicAccessorReader
~~~

Khi `Order` là lớp nested `public` trong cùng môi trường như ví dụ, kết quả là:

~~~text
ORD-42
~~~

Khi đóng gói thành hai named module, một phương thức `public` có thể vẫn không gọi được nếu package chứa declaring class không được export cho module thư viện. Khi đó, thông báo có thể cho thấy:

~~~text
Cannot invoke member public java.lang.String com.example.model.internal.Order.id();
declaringClass=com.example.model.internal.Order;
package=com.example.model.internal;
ownerModule=com.example.model;
callerModule=com.example.mapper;
sameModule=false;
ownerClassPublic=true;
memberPublic=true;
exportedToCaller=false;
openedToCaller=false
~~~

Khối trên là **ví dụ minh họa cấu trúc thông tin lỗi**, không phải output nguyên văn đã chạy của chương trình. Nếu đóng gói và tên module khác, các giá trị sẽ khác. Khi ứng dụng thực tế cần truyền `Order` qua ranh giới module, việc phát hiện và truyền đối tượng cũng phải tuân thủ các quy tắc riêng của ứng dụng.

### Vì sao lấy module từ declaring class?

`method.getDeclaringClass()` là lớp/interface **khai báo member**. Nếu đối tượng có kiểu `CustomerOrder` kế thừa phương thức từ `BaseOrder`, package và module chứa `BaseOrder` mới là dữ kiện quan trọng đối với quyền truy cập phương thức đó. Chỉ in `target.getClass().getModule()` có thể chỉ sai vị trí cần sửa.

Với lỗi `NoSuchMethodException`, lúc đó chưa có một `Method` để hỏi declaring class; báo tên kiểu đã được yêu cầu, tên method và chữ ký dự kiến. Với `IllegalAccessException`, đã có member thực nên báo cả `declaringClass` và module chứa nó.

### Ý nghĩa của các cờ chẩn đoán

`isExported(packageName, callerModule)` và `isOpen(packageName, callerModule)` giúp giải thích cấu hình module hiện tại; chúng **không phải** một công thức hoàn chỉnh để kết luận mọi member đều gọi được. Ví dụ, class khai báo không public, member không public, hoặc mã gọi ở cùng module đều ảnh hưởng đến khả năng truy cập. Vì thế thông điệp còn kèm `sameModule`, `ownerClassPublic` và `memberPublic`.

Thư viện cũng có thể kiểm tra `method.canAccess(target)` khi cần quan sát quyền truy cập tại thời điểm đó. Tham số truyền vào phải phù hợp: đối với instance method là receiver hợp lệ; đối với static method dùng `null`. `canAccess` kiểm tra quyền truy cập hiện tại, không phải một phép cấp quyền mới.

## 6. Phân loại lỗi đúng để có hướng xử lý hữu ích

Một thư viện nên biến lỗi thành thông điệp đủ cụ thể, nhưng phải giữ nguyên nguyên nhân và phân biệt các loại sự cố.

| Tín hiệu | Điều thực sự xảy ra | Thông điệp / hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | Không tìm thấy public method với tên và tham số đã yêu cầu | Báo kiểu, tên method, chữ ký mong đợi; kiểm tra API/phiên bản thay vì mở module. |
| `NoSuchFieldException` | Field không được khai báo ở class được hỏi bằng `getDeclaredField` | Báo tên field và class được kiểm tra; cân nhắc accessor thay vì field nội bộ. |
| `IllegalAccessException` khi `Method.invoke` | Tìm thấy method nhưng không đủ quyền gọi | Báo exact member, declaring module, caller module, package, trạng thái `exports`. |
| `InaccessibleObjectException` khi `setAccessible(true)` | Không thể mở truy cập sâu qua ranh giới module hoặc điều kiện truy cập | Báo member, module, package; nếu deep reflection thật sự cần, chủ module cân nhắc `opens ... to ...`. |
| `trySetAccessible() == false` | Không thể bỏ qua access checks theo quyền hiện tại | Báo member/module tương tự; không lặp thử trên mọi request. |
| `InvocationTargetException` | Member đã được gọi nhưng code bên trong ném exception | Giữ lại `getCause()`; không đưa ra lời khuyên `--add-opens`. |
| `IllegalArgumentException` khi invoke / set | Receiver, tham số hoặc kiểu giá trị không phù hợp | In chữ ký API mong đợi và loại giá trị/receiver; tránh in dữ liệu nhạy cảm. |

Một lỗi `ClassCastException` sau khi invoke có thể là do kết quả thực tế không khớp hợp đồng kiểu mà thư viện kỳ vọng. Trường hợp ấy cần sửa hợp đồng mapper hoặc cách kiểm tra kiểu, không phải cấp quyền reflection rộng hơn.

**Không gộp mọi `ReflectiveOperationException` thành “Access denied”.** `NoSuchMethodException` và `InvocationTargetException` không có cùng nguyên nhân với `IllegalAccessException`.

## 7. Mẫu thông báo lỗi dành cho người sử dụng thư viện

Thông báo tốt chứa đủ ngữ cảnh để tìm chỗ cấu hình:

~~~text
Cannot access member:
  member           = com.example.model.internal.Order#id()
  declaring class  = com.example.model.internal.Order
  declaring module = com.example.model
  caller module    = com.example.mapper
  package          = com.example.model.internal
  operation        = invoke public accessor
  exported         = false
  opened           = false
  cause            = java.lang.IllegalAccessException

Suggested action:
  Prefer a public accessor in an exported API package.
  If deep reflection is explicitly required, the module owner
  can open the specific package to the specific library module.
~~~

Các thành phần nên có:

1. **Thao tác thất bại:** tra cứu, invoke, read, write hay try-open. Một message chỉ ghi “reflection error” chưa đủ.
2. **Member chính xác:** declaring class, tên member, kiểu tham số/kết quả nếu cần. Có thể dùng `Method.toGenericString()` hoặc `Field.toGenericString()`.
3. **Module hai phía:** module sở hữu declaring class và module chứa code đang thực hiện reflection. Module không có tên nên hiển thị rõ là `<unnamed module>`.
4. **Package và quyền liên quan:** member có public không, package được `exports` hay `opens` cho module gọi không.
5. **Nguyên nhân gốc:** exception class, cause chain; không nuốt `InvocationTargetException.getCause()`.
6. **Một hướng sửa đúng trường hợp:** API công khai nếu có; chỉ đề xuất `opens` khi thật sự dùng deep reflection và chủ module chấp thuận.

Không cần ghi giá trị field, nội dung token, mật khẩu, thông tin cá nhân hoặc toàn bộ object vào log. Lỗi truy cập thường có thể được chẩn đoán chỉ bằng **metadata về kiểu và module**.

## 8. Dùng getMethod, getDeclaredMethod và trySetAccessible đúng mục đích

Giả sử `Account` có `public String id()` và field `private String id`. Thư viện muốn đọc ID.

Cách phù hợp:

~~~java
Method accessor = account.getClass().getMethod("id");
String id = (String) accessor.invoke(account);
~~~

Cách cần thận trọng:

~~~java
Field field = account.getClass().getDeclaredField("id");
if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Cannot open field " + field.toGenericString()
                    + " in module "
                    + field.getDeclaringClass().getModule().getName());
}
String id = (String) field.get(account);
~~~

Ví dụ thứ hai minh họa việc kiểm tra thất bại một cách minh bạch; **không phải gợi ý dùng nó mặc định**. Cần kiểm tra cả member, module gọi và package để thông báo chính xác; `getName()` của unnamed module có thể là `null`, nên thư viện sản phẩm nên format tên module rõ ràng.

`getDeclaredField("id")` không tìm field được thừa kế. `getDeclaredMethod(...)` cũng chỉ tìm member được khai báo trực tiếp, trong khi `getMethod(...)` làm việc theo public method lookup. Đừng dùng `getDeclaredMethod` chỉ vì muốn gọi một public accessor; thay đổi này dễ làm hỏng hỗ trợ kế thừa.

Nếu cần deep reflection theo một hợp đồng tương thích cũ, nên đưa nó vào một tính năng **opt-in** riêng, có thông báo nêu các yêu cầu module cụ thể và không hoạt động âm thầm. Mọi lần không mở được truy cập cần báo nguyên nhân, thay vì cố thử các kỹ thuật bỏ qua giới hạn của JDK.

## 9. Ví dụ hai module và đường sửa đúng

Ứng dụng có module dữ liệu:

~~~java
// com.example.model/module-info.java
module com.example.model {
    exports com.example.model.api;
}
~~~

Thư viện tích hợp có module:

~~~java
// com.example.mapper/module-info.java
module com.example.mapper {
    requires com.example.model;
}
~~~

Thư viện có thể sử dụng class `public` và method `public` ở `com.example.model.api` theo hợp đồng được export. Nó không nên mặc định cố đọc `private` field trong `com.example.model.internal`.

Nếu cần đưa một property của internal class ra cho mapper, có hai lựa chọn phù hợp:

**Lựa chọn A — Điều chỉnh API của ứng dụng:** chuyển hợp đồng cần thiết sang một interface, public DTO/record hoặc accessor trong package được export. Đây thường là giải pháp bền vững nhất khi người dùng kiểm soát mã nguồn hai phía.

**Lựa chọn B — Cho phép adapter ở phía ứng dụng:** phía ứng dụng truyền một callback/method reference, hoặc tạo adapter đọc các member mà chính ứng dụng có quyền truy cập. Thư viện nhận kết quả qua public contract và không cần quyền xem private field.

Nếu không thể áp dụng A/B và cần tính năng tương thích dựa trên reflection sâu, chủ module có thể cấp quyền:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.mapper;
}
~~~

Lúc đó thư viện vẫn phải kiểm tra `trySetAccessible()` và lỗi thao tác tương ứng. `opens` không cho phép ghi `static final` hoặc field `final` của record. Không nên khuyên mở toàn bộ module hay mở mọi package khi chỉ một package cần được truy cập.

### Cần phân biệt nguồn gốc lỗi

Nếu API public nằm trong package chưa export, người duy trì module cần quyết định liệu package ấy có được thiết kế thành API không. Tự động đề nghị `opens` cho mọi lỗi invoke sẽ khiến người dùng vô tình mở các chi tiết nội bộ. Nếu ý định chỉ là gọi public API, **`exports` đúng phạm vi** mới phản ánh hợp đồng thư viện.

## 10. Vai trò của MethodHandle và các lựa chọn runtime khác

Khi mã tích hợp cần gọi một phương thức nhiều lần, `MethodHandle` có thể là công cụ phù hợp sau khi đã xác định một member có thể truy cập. Tuy nhiên, `MethodHandles.publicLookup()` hoặc `MethodHandles.lookup()` vẫn chịu hợp đồng kiểm tra quyền, module và lookup modes tương ứng; chúng không phải cách tự động vượt qua việc package chưa export.

`MethodHandles.privateLookupIn(...)` có điều kiện truy cập riêng, bao gồm việc package/module cho phép private lookup khi đi qua ranh giới module. Thay `Method.invoke` bằng `MethodHandle` không tự làm một private member trở thành public API.

Đối với thư viện hiệu năng cao, có thể cache kết quả tìm kiếm method theo class và chữ ký thay vì mỗi request đều tra cứu lại. Cần thiết kế cache tránh giữ class loader của plugin quá lâu, và không cache một kết quả thiếu quyền như thể quyền truy cập không bao giờ thay đổi trong mọi ngữ cảnh. Việc cache phải dựa trên use case và mô hình class loading thực tế, không nên làm phức tạp ví dụ cơ bản.

Khi đã có typed interface/callback và các lời gọi có thể được biên dịch trực tiếp, ưu tiên chúng vì đơn giản, dễ kiểm thử và tránh nhiều lỗi runtime.

## 11. Kiểm chứng trên JDK hiện hành

Một bộ kiểm thử hữu ích nên mô tả **hợp đồng truy cập** mà thư viện hứa hẹn:

| Trường hợp | Bố trí | Kỳ vọng |
| --- | --- | --- |
| Public accessor hợp lệ | Public class, public method, package được export | Đọc dữ liệu thành công. |
| Method không tồn tại | Cấu hình tên `id()` nhưng kiểu không có method tương ứng | `NoSuchMethodException` được chuyển thành lỗi cấu hình rõ tên kiểu và method. |
| Public member nhưng package không export | Named module của model chứa public method trong package không export cho caller | Báo member, declaring module, caller module và trạng thái export; không khuyên `opens` vô điều kiện. |
| Private member chưa mở | Deep reflection opt-in vào private field trong named module không mở package | `trySetAccessible()` thất bại hoặc `setAccessible(true)` ném `InaccessibleObjectException` theo đường API được dùng; báo package/module. |
| Private member đã được mở có chủ đích | Model `opens package to module` phù hợp | Deep reflection có thể truy cập nếu mọi điều kiện khác thỏa mãn. |
| Getter ném exception | Public accessor chủ động ném `IllegalStateException` | Thư viện giữ cause từ `InvocationTargetException`, không đánh nhãn lỗi JPMS. |
| Mutable / final field | Đọc và ghi field với các modifier khác nhau | Không suy diễn quyền ghi chỉ từ kết quả `trySetAccessible()`. |

Để đánh giá việc chuyển từ class path sang module path, hãy chạy ít nhất hai cấu hình độc lập và ghi lại:

- Phiên bản JDK thực tế (`java -version`).
- Module name của declaring class và của thư viện.
- Trạng thái `exports`/`opens` đối với package cần truy cập.
- Chữ ký member và loại thao tác thất bại.
- Exception type và nguyên nhân gốc.

Không cần chạy lại quá nhiều phép thử giống nhau sau khi điều kiện đã được xác nhận. Điều quan trọng là có một test dương cho public API và test âm cho cấu hình quyền chưa đủ; các test đó giúp phát hiện regression khi đổi JPMS configuration hoặc nâng JDK.

## 12. Những phản mẫu cần tránh

**Tự động gọi `setAccessible(true)` trên mọi member.** Thư viện dễ ném `InaccessibleObjectException` trên named module và phát sinh yêu cầu mở private package không cần thiết. Chỉ mở khi có hợp đồng tương thích cụ thể.

**Bắt mọi exception rồi đề nghị `--add-opens`.** `NoSuchMethodException` có thể do phiên bản API, `InvocationTargetException` có thể do logic người dùng; không phải vấn đề module.

**Chỉ ghi “class X inaccessible”.** Khi method kế thừa từ một supertype, cần báo `method.getDeclaringClass()`; nếu không, người sử dụng sẽ sửa nhầm module hoặc package.

**Dùng tên field private làm giao diện thư viện.** Refactor một field nội bộ có thể phá vỡ thư viện ngay cả khi accessor public vẫn giữ nguyên.

**Bỏ qua quyền truy cập khi đã thấy Modifier.PUBLIC.** Module export, declaring class và ngữ cảnh caller có thể tiếp tục ngăn gọi member.

**Giải quyết lỗi bằng API nội bộ hoặc bỏ giới hạn Java.** Cách này tạo phụ thuộc vào hành vi không ổn định và làm khó việc nâng JDK.

## 13. Checklist review thư viện

- [ ] Có interface, accessor, constructor, factory, adapter hoặc callback công khai trước khi chọn deep reflection.
- [ ] Các trường hợp dùng reflection được ghi rõ: cần public lookup hay deep reflection, thao tác đọc hay ghi.
- [ ] Module của dữ liệu `exports` đúng package API công khai mà thư viện cần.
- [ ] Nếu cần deep reflection, package được mở có chủ đích tới module cụ thể, có đường xử lý khi không mở được.
- [ ] Thông báo lỗi nêu member + declaring class + package + owner module + caller module + operation.
- [ ] Lỗi member không tồn tại, lỗi quyền truy cập và lỗi trong getter được xử lý theo ba hướng riêng.
- [ ] Log chỉ ghi metadata cần cho chẩn đoán, không xuất giá trị nhạy cảm của field/đối tượng.
- [ ] Không giả định `trySetAccessible() == true` đồng nghĩa mọi thao tác `set` đều hợp lệ.
- [ ] Đã thử chạy với named module và JDK mục tiêu, không chỉ class path trong IDE.

## 14. Câu hỏi tự kiểm tra

1. Một thư viện chỉ cần đọc ID của đối tượng. Vì sao callback `Order::id` giúp giảm phụ thuộc hơn `getDeclaredField("id")`?
2. `public` method trong class `public` có thể bị từ chối khi invoke từ named module khác trong tình huống nào?
3. Sự khác biệt giữa `exports` và `opens` là gì? Vì sao không nên đề nghị `opens` cho mọi lỗi?
4. Vì sao cần sử dụng `method.getDeclaringClass()` khi báo lỗi truy cập thay vì chỉ `target.getClass()`?
5. Trong trường hợp nào `InvocationTargetException` xuất hiện, và nó có nói lên lỗi module hay không?
6. `trySetAccessible()` trả về `true` có bảo đảm ghi được `static final` hoặc field `final` của record không?
7. Khi cần thông báo nguyên nhân lỗi, những metadata nào là đủ mà không cần log giá trị dữ liệu của đối tượng?
8. Vì sao thay `Method.invoke` bằng `MethodHandle` không thể tự chữa vấn đề thiếu quyền truy cập?

## 15. Ghi nhớ

Thiết kế thư viện Java bền vững bắt đầu từ **hợp đồng công khai**, nhận dữ liệu qua accessor, interface hoặc callback do ứng dụng cung cấp. Chỉ dùng reflection khi có yêu cầu thực tế và xác định rõ cần **public lookup** hay **deep reflection**. Khi gặp lỗi, hãy báo chính xác **member nào**, **declaring class và package nào**, **module nào sở hữu**, **module nào gọi** và thao tác nào bị từ chối. Cách làm này giúp người sử dụng sửa đúng API hoặc quyền JPMS, đồng thời giữ thư viện phù hợp với giới hạn reflection đang được thực thi trên JDK hiện đại.

