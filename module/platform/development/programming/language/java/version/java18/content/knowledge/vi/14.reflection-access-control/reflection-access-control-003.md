# canAccess(receiver): kiểm tra khả năng truy cập và quy tắc receiver cho static hoặc instance

> **Chương:** Quyền reflection  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Sử dụng `AccessibleObject.canAccess(Object receiver)` đúng hợp đồng, phân biệt trường hợp trả về `true`/`false` với `IllegalArgumentException`, chọn receiver đúng cho field/method `static`, field/method instance và constructor; hiểu ảnh hưởng của caller, visibility, JPMS và accessible flag trên các JDK hiện đại.

## 1. Vì sao canAccess(receiver) quan trọng?

Reflection cho phép Java khám phá và sử dụng thành viên của class lúc chạy. Ví dụ:

~~~java
Field field = SomeType.class.getDeclaredField("name");
Method method = SomeType.class.getDeclaredMethod("read");
Constructor<SomeType> constructor =
        SomeType.class.getDeclaredConstructor();
~~~

Việc lấy được đối tượng `Field`, `Method` hoặc `Constructor` **không có nghĩa** code hiện tại chắc chắn được phép đọc field, gọi method hay tạo object bằng constructor đó.

Đôi khi framework muốn kiểm tra khả năng truy cập trước khi thao tác. API thích hợp là:

~~~java
boolean allowed = reflectedMember.canAccess(receiver);
~~~

Ở đây `reflectedMember` là một `Field`, `Method` hoặc `Constructor<?>`. Điểm dễ sai nhất nằm ở tham số `receiver`:

- **Field/method instance:** phải truyền đối tượng instance phù hợp.
- **Field/method static:** phải truyền `null`.
- **Constructor:** phải truyền `null`, vì constructor chưa có receiver instance.

Nếu truyền receiver sai, `canAccess` không đơn giản trả `false`; nó **ném `IllegalArgumentException`**.

Mặc dù module học đề cập Java 18, `AccessibleObject.canAccess(Object)` được giới thiệu từ **Java 9**. Java 18 có JEP 416 tái triển khai core reflection bằng Method Handles, nhưng **không** thay đổi hợp đồng receiver hoặc ý nghĩa của `canAccess`. Đây là các kiến thức vẫn còn được dùng trên JDK hiện đại.

## 2. Nhận diện đúng đối tượng nào hỗ trợ canAccess

`AccessibleObject` là lớp nền của các reflective object tương ứng với:

| Reflective object | Ví dụ tra cứu | Thao tác chính |
|---|---|---|
| `Field` | `getDeclaredField("count")` | `get(receiver)`, `set(receiver, value)` |
| `Method` | `getDeclaredMethod("run")` | `invoke(receiver, args...)` |
| `Constructor<?>` | `getDeclaredConstructor(...)` | `newInstance(args...)` |

Mỗi đối tượng này có phương thức final `canAccess(Object obj)` kế thừa từ `AccessibleObject`.

API kiểm tra **quyền truy cập của caller hiện tại tới member được phản chiếu**, có xét receiver khi là instance member. Nó không kiểm tra rằng lời gọi `Method.invoke` sau đó sẽ thành công về mặt tham số, exception do method ném, hoặc trạng thái nghiệp vụ.

Một method công khai vẫn có thể ném exception khi chạy. Một constructor truy cập được vẫn có thể thất bại bên trong thân constructor. `canAccess` chỉ xử lý câu hỏi về truy cập reflection và tính hợp lệ của receiver.

## 3. Quy tắc receiver: bảng cần ghi nhớ

| Thành viên được phản chiếu | Receiver phải truyền vào `canAccess` | Receiver sai |
|---|---|---|
| `static` field | `null` | Bất kỳ object khác `null` |
| `static` method | `null` | Bất kỳ object khác `null` |
| Instance field | Instance của declaring class hoặc subtype | `null` hoặc object không thuộc kiểu phù hợp |
| Instance method | Instance của declaring class hoặc subtype | `null` hoặc object không thuộc kiểu phù hợp |
| Constructor | `null` | Bất kỳ object khác `null` |

Với instance member, điều kiện kiểu receiver gần với:

~~~java
declaringClass.isInstance(receiver)
~~~

Tức receiver có thể là instance trực tiếp hoặc object của subclass. Nếu member được khai báo trên interface, object implementing interface cũng có thể là receiver hợp lệ theo quan hệ kiểu.

**Quan trọng:** Receiver hợp lệ về kiểu **chưa chắc** khiến `canAccess` trả `true`. Java vẫn kiểm tra quyền truy cập theo caller, visibility, module và trạng thái accessible flag. Ngược lại, receiver không hợp lệ thì ném `IllegalArgumentException` trước khi có một kết quả boolean ý nghĩa.

### 3.1. Không dùng this một cách máy móc

Trong code generic, đừng truyền `this` cho mọi loại member:

~~~java
// Sai nếu member là static hoặc constructor:
boolean accessible = member.canAccess(this);
~~~

Hãy phân loại member trước. Với `Field` hoặc `Method`, dùng `Modifier.isStatic(member.getModifiers())`. Với `Constructor`, receiver luôn là `null`.

## 4. Ví dụ đầy đủ: một file Java và mọi kiểu thành viên

Tạo file `CanAccessReceivers.java` lưu UTF-8:

~~~java
import java.lang.reflect.AccessibleObject;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class Sample {
    public static int staticCount = 10;
    public int instanceCount = 20;
    private int secret = 30;

    public Sample() {}

    private Sample(String ignored) {}

    public static void ping() {}
    public void tick() {}
    private void hidden() {}
}

class SampleChild extends Sample {}

public class CanAccessReceivers {
    private static void show(
            String label,
            AccessibleObject member,
            Object receiver) {
        try {
            System.out.println(label + "=" + member.canAccess(receiver));
        } catch (IllegalArgumentException exception) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();
        SampleChild child = new SampleChild();

        Field staticField = Sample.class.getDeclaredField("staticCount");
        Field instanceField = Sample.class.getDeclaredField("instanceCount");
        Field secretField = Sample.class.getDeclaredField("secret");

        Method staticMethod = Sample.class.getDeclaredMethod("ping");
        Method instanceMethod = Sample.class.getDeclaredMethod("tick");
        Method privateMethod = Sample.class.getDeclaredMethod("hidden");

        Constructor<Sample> publicCtor =
                Sample.class.getDeclaredConstructor();
        Constructor<Sample> privateCtor =
                Sample.class.getDeclaredConstructor(String.class);

        show("staticField/null", staticField, null);
        show("staticField/object", staticField, sample);

        show("instanceField/object", instanceField, sample);
        show("instanceField/subclass", instanceField, child);
        show("instanceField/null", instanceField, null);
        show("instanceField/unrelated", instanceField, new Object());

        show("staticMethod/null", staticMethod, null);
        show("staticMethod/object", staticMethod, sample);
        show("instanceMethod/object", instanceMethod, sample);
        show("instanceMethod/null", instanceMethod, null);

        show("publicCtor/null", publicCtor, null);
        show("publicCtor/object", publicCtor, sample);

        show("privateField/before", secretField, sample);
        show("privateMethod/before", privateMethod, sample);
        show("privateCtor/before", privateCtor, null);

        System.out.println("enablePrivateField="
                + secretField.trySetAccessible());
        show("privateField/after", secretField, sample);
    }
}
~~~

Compile bằng JDK hiện đại:

~~~shell
javac -encoding UTF-8 -d out CanAccessReceivers.java
~~~

Chạy:

~~~shell
java -cp out CanAccessReceivers
~~~

Kết quả mong đợi khi chạy đúng file này trên classpath (unnamed module):

~~~text
staticField/null=true
staticField/object=IllegalArgumentException
instanceField/object=true
instanceField/subclass=true
instanceField/null=IllegalArgumentException
instanceField/unrelated=IllegalArgumentException
staticMethod/null=true
staticMethod/object=IllegalArgumentException
instanceMethod/object=true
instanceMethod/null=IllegalArgumentException
publicCtor/null=true
publicCtor/object=IllegalArgumentException
privateField/before=false
privateMethod/before=false
privateCtor/before=false
enablePrivateField=true
privateField/after=true
~~~

### 4.1. Vì sao private member ban đầu trả false?

`CanAccessReceivers` và `Sample` là **hai top-level class riêng**, dù cùng source file và cùng package mặc định. Code trong `CanAccessReceivers` không có quyền Java language access trực tiếp tới các private member của `Sample`.

`getDeclaredField`/`getDeclaredMethod`/`getDeclaredConstructor` vẫn có thể lấy metadata về private member; điều đó không đồng nghĩa có quyền sử dụng nó.

Nếu đặt `Sample` làm nested class bên trong `CanAccessReceivers`, kết quả có thể khác vì **nestmate access** cho phép các class thuộc cùng nest truy cập private member của nhau. Vì thế, khi kiểm thử quy tắc private, dùng các top-level class tách biệt như ví dụ.

### 4.2. Vì sao trySetAccessible thành công trong ví dụ?

Hai class thuộc cùng unnamed module. Với điều kiện module cho phép, `trySetAccessible()` có thể bật cờ suppress Java language access checks trên **đối tượng Field phản chiếu đó**. Sau khi bật, `secretField.canAccess(sample)` trả true.

Không suy rộng rằng `trySetAccessible()` luôn thành công với private member của module khác. Ở named module có strong encapsulation, package có thể cần `opens` phù hợp.

## 5. Static field: chỉ dùng canAccess(null)

Ví dụ:

~~~java
Field f = Sample.class.getDeclaredField("staticCount");

System.out.println(f.canAccess(null));          // true
System.out.println(f.canAccess(new Sample()));  // IllegalArgumentException
~~~

Field `static` gắn với class, không gắn với một instance cụ thể. Vì vậy, `canAccess` yêu cầu đối số `null`.

Một lỗi phổ biến là truyền một object chỉ vì object đó “có field”:

~~~java
// Không đúng hợp đồng của canAccess cho static member:
f.canAccess(sample);
~~~

Dù `sample` là instance hợp lệ của class khai báo field, đây vẫn là receiver **sai**.

### 5.1. Khác biệt đáng chú ý với Field.get

Với static field, `Field.get(Object obj)` cho phép tham số object bị bỏ qua; người gọi có thể truyền `null`. Hợp đồng `canAccess` **nghiêm ngặt hơn** về receiver: đối số bắt buộc là `null`.

~~~java
Field f = Sample.class.getDeclaredField("staticCount");

// Khi quyền truy cập được phép:
Object value = f.get(null);     // Đọc static field
boolean access = f.canAccess(null);
~~~

Đừng sao chép receiver từ lời gọi `Field.get(object)` hoặc từ framework generic sang `canAccess` mà không kiểm tra thành viên có static hay không.

## 6. Static method: canAccess(null) khác Method.invoke(obj)

Với static method:

~~~java
Method m = Sample.class.getDeclaredMethod("ping");
System.out.println(m.canAccess(null));           // true
System.out.println(m.canAccess(new Sample()));   // IllegalArgumentException
~~~

`Method.invoke(Object obj, Object... args)` cho phép bỏ qua tham số `obj` đối với static method. Nhưng `canAccess` bắt buộc truyền `null` cho static method.

Ví dụ để phân biệt hai hợp đồng:

~~~java
Method m = Sample.class.getDeclaredMethod("ping");

// Static Method.invoke cho phép obj bị bỏ qua:
m.invoke(new Object());

// Static canAccess bắt buộc receiver là null:
System.out.println(m.canAccess(null));

// Sai:
m.canAccess(new Object());  // IllegalArgumentException
~~~

Hai API trả lời câu hỏi khác nhau. Không suy luận rằng vì `invoke` bỏ qua object ở static method thì `canAccess` cũng bỏ qua.

Trong thực hành thông thường, vẫn nên dùng `m.invoke(null)` cho static method để code rõ ràng và tránh nhầm lẫn.

## 7. Instance field và method: object đúng kiểu là bắt buộc

Với instance field:

~~~java
Field field = Sample.class.getDeclaredField("instanceCount");
Sample sample = new Sample();

System.out.println(field.canAccess(sample)); // true
~~~

Với instance method:

~~~java
Method method = Sample.class.getDeclaredMethod("tick");
System.out.println(method.canAccess(sample)); // true
~~~

Truyền `null`:

~~~java
field.canAccess(null);  // IllegalArgumentException
method.canAccess(null); // IllegalArgumentException
~~~

Truyền object không phải instance của declaring class:

~~~java
field.canAccess("not a Sample");  // IllegalArgumentException
~~~

Với object subclass:

~~~java
SampleChild child = new SampleChild();
System.out.println(field.canAccess(child)); // true trong ví dụ
~~~

Ở đây `field` được khai báo bởi `Sample`, và `SampleChild` kế thừa từ `Sample`. Kiểm tra kiểu receiver hợp lệ; sau đó Java mới xác định quyền truy cập của caller.

### 7.1. getDeclaringClass() và getClass() không giống nhau

`field.getDeclaringClass()` là class **khai báo** field, không nhất thiết là runtime class của receiver.

~~~java
Field field = Sample.class.getDeclaredField("instanceCount");
Sample child = new SampleChild();

System.out.println(field.getDeclaringClass().getName()); // Sample
System.out.println(child.getClass().getName());          // SampleChild
System.out.println(field.canAccess(child));               // true
~~~

Nếu dùng `receiver.getClass() == field.getDeclaringClass()` để tự validate, bạn sẽ từ chối sai subclass. `Class.isInstance` phù hợp hơn với quy tắc receiver.

## 8. Constructor: không truyền instance

`Constructor` là reflective object tương ứng với quá trình tạo object; việc kiểm tra khả năng gọi constructor không liên quan tới một receiver instance có sẵn.

~~~java
Constructor<Sample> ctor = Sample.class.getDeclaredConstructor();

System.out.println(ctor.canAccess(null));           // true
System.out.println(ctor.canAccess(new Sample()));   // IllegalArgumentException
~~~

Với private constructor trong ví dụ:

~~~java
Constructor<Sample> privateCtor =
        Sample.class.getDeclaredConstructor(String.class);

System.out.println(privateCtor.canAccess(null)); // false
~~~

`Constructor.newInstance(Object... initargs)` nhận **tham số constructor**, không nhận receiver:

~~~java
Constructor<Sample> ctor = Sample.class.getDeclaredConstructor();
Sample sample = ctor.newInstance();
~~~

Đừng truyền một instance vào `canAccess` chỉ vì muốn thử “đối tượng có thể được tạo”. Với constructor, quy tắc luôn là `canAccess(null)`.

## 9. Phân biệt return false và IllegalArgumentException

Hợp đồng `canAccess` có hai tầng:

**Tầng A — Kiểm tra receiver hợp lệ:**

- Static field/method hoặc constructor → receiver phải là `null`.
- Instance field/method → receiver phải là instance phù hợp và không được `null`.
- Nếu sai → `IllegalArgumentException`.

**Tầng B — Kiểm tra quyền truy cập:**

- Nếu accessible flag đã được bật, có thể trả `true`.
- Nếu không, đánh giá Java language access của **caller**, member visibility, declaring class và module.
- Trả `true` nếu được phép, `false` nếu không được phép.

| Tình huống | Kết quả |
|---|---|
| Public instance field, receiver đúng, caller được phép | `true` |
| Private instance field, receiver đúng, caller khác class/nest không được phép | `false` |
| Public instance field, receiver `null` | `IllegalArgumentException` |
| Public instance method, receiver object sai kiểu | `IllegalArgumentException` |
| Public static field, receiver object bất kỳ khác `null` | `IllegalArgumentException` |
| Public static method, receiver `null` và caller được phép | `true` |
| Constructor, receiver object bất kỳ khác `null` | `IllegalArgumentException` |
| Private constructor, receiver `null`, caller không có quyền | `false` |

Đừng viết:

~~~java
if (!method.canAccess(null)) {
    // "Không được phép" — sai nếu method là instance!
}
~~~

Lời gọi này có thể ném exception trước khi đi vào nhánh `if`. Muốn kiểm tra an toàn, trước hết phân biệt static/instance và chọn receiver đúng.

### 9.1. Không bắt IllegalArgumentException rồi coi như false

Hành vi sai:

~~~java
try {
    return method.canAccess(null);
} catch (IllegalArgumentException exception) {
    return false;
}
~~~

Đoạn này có thể che lỗi lập trình (đã truyền sai receiver) thành kết luận “không có quyền”. Thay vì thế, xác định đúng member kind và bảo đảm receiver hợp lệ. Trong public API tổng quát, hãy báo lỗi sử dụng không hợp lệ một cách rõ ràng.

## 10. canAccess phụ thuộc caller

`canAccess` là phép kiểm tra **của code gọi phương thức này**, không phải một thuộc tính “public/true” cố định cho member trong toàn JVM.

Ví dụ, một private field của class `Account` có thể được code **trong chính class Account** truy cập hợp lệ, nhưng một class helper khác không phải nestmate thì không có quyền.

Cùng một `Field` object có thể cho kết quả khác nhau khi `canAccess` được gọi từ hai class khác nhau, nếu accessible flag chưa được bật và Java language access của caller khác nhau.

Điều cần nhớ:

- Caller là class thực hiện lời gọi `canAccess(...)`.
- Không phải class nơi `getDeclaredField(...)` được thực thi trước đó.
- Không phải luôn là class đã tạo ra target object.
- Nếu dời việc kiểm tra sang một helper ở package/module khác, kết quả có thể khác.

### 10.1. Tránh “preflight” ở caller khác với caller thực hiện thao tác

Giả sử framework A gọi `canAccess` hộ framework B, rồi B mới gọi `Field.get`. Kết quả của A không nhất thiết là bằng chứng quyền Java language access của B.

Khi có thể, kiểm tra gần điểm thực hiện thao tác. Nếu kiến trúc có tầng helper, phải hiểu rằng check dựa trên caller của helper; cân nhắc thiết kế API không phụ thuộc vào việc phản chiếu member không public.

### 10.2. Trường hợp protected instance

Ở package khác, một subclass có thể có quyền truy cập protected instance member theo Java language rules, nhưng receiver bị giới hạn theo kiểu phù hợp với subclass.

Ví dụ hai file:

~~~java
// src/base/Base.java
package base;
public class Base {
    protected int score = 7;
}
~~~

~~~java
// src/app/Child.java
package app;
import base.Base;
import java.lang.reflect.Field;

public class Child extends Base {
    public static void main(String[] args) throws Exception {
        Field score = Base.class.getDeclaredField("score");

        Child child = new Child();
        Base base = new Base();

        System.out.println(score.canAccess(child));
        System.out.println(score.canAccess(base));
    }
}
~~~

Compile/chạy trên classpath:

~~~shell
javac -encoding UTF-8 -d out src/base/Base.java src/app/Child.java
java -cp out app.Child
~~~

Kết quả mong đợi:

~~~text
true
false
~~~

Cả `child` và `base` đều là instance của declaring class `Base`, nên **đều là receiver hợp lệ về kiểu**. Nhưng caller `Child` ở package khác chỉ có Java protected access đối với receiver phù hợp với quy tắc protected của subclass. Vì vậy, một receiver hợp lệ chưa đủ để `canAccess` trả `true`.

Không cố dùng `trySetAccessible()` để né quy tắc protected của ứng dụng khi có thể thiết kế một public API hoặc một method được gọi theo quyền ngôn ngữ thông thường.

## 11. canAccess và accessible flag là hai khái niệm khác nhau

Ba API dễ bị nhầm:

| API | Vai trò | Có thay đổi trạng thái truy cập? |
|---|---|---|
| `canAccess(receiver)` | Hỏi caller có thể truy cập member bằng receiver này không | Không |
| `trySetAccessible()` | Cố bật suppress access checks nếu module cho phép | Có, trên reflective object đó nếu thành công |
| `setAccessible(true/false)` | Yêu cầu bật/tắt suppress access checks | Có hoặc ném lỗi nếu không cho phép bật |

Ví dụ:

~~~java
Field secret = Sample.class.getDeclaredField("secret");
Sample target = new Sample();

System.out.println(secret.canAccess(target)); // false

boolean enabled = secret.trySetAccessible();
System.out.println(enabled);                  // true trong ví dụ classpath
System.out.println(secret.canAccess(target)); // true khi bật thành công

secret.setAccessible(false);
System.out.println(secret.canAccess(target)); // false
~~~

Phương thức `trySetAccessible()` **không phải** chỉ là kiểm tra; khi thành công, nó **thay đổi accessible flag** trên đối tượng phản chiếu.

`setAccessible(true)` có thể ném `InaccessibleObjectException` khi không thể bật access. `trySetAccessible()` trả `false` thay vì exception này trong trường hợp không được mở quyền, nhưng code vẫn cần xử lý các lỗi khác có thể phát sinh theo contract và ngữ cảnh runtime.

### 11.1. Không dùng isAccessible() để trả lời câu hỏi hiện đại

`AccessibleObject.isAccessible()` đã deprecated từ Java 9 vì tên dễ gây hiểu nhầm. Nó chỉ báo accessible flag có bật để suppress access checks hay không, **không** trả lời caller hiện tại có thể truy cập member hay không.

Một public method có thể truy cập hoàn toàn hợp lệ trong khi accessible flag vẫn đang `false`. Vì vậy, hãy dùng `canAccess(receiver)` khi muốn kiểm tra khả năng truy cập, thay vì dựa vào API deprecated.

## 12. Ảnh hưởng của module exports và opens

Từ Java 9, JPMS định nghĩa ranh giới module. `canAccess` vẫn áp dụng cả visibility của Java và quyền module. Trong named module, các package không mặc nhiên mở cho deep reflection.

Phân biệt:

- `exports p;`: cho module khác biên dịch và truy cập các **public types/members** trong package `p` theo Java module rules.
- `opens p;`: cho phép deep reflection vào các type/member trong package `p` theo điều kiện caller module.
- `opens p to some.module;`: chỉ mở package cho module được chỉ định.
- `open module ...`: mở tất cả package cho deep reflection, thường không nên sử dụng rộng nếu chỉ cần một package.

Ví dụ module cung cấp API:

~~~java
module catalog.core {
    exports com.example.catalog;
}
~~~

Và module gọi:

~~~java
module inspector.app {
    requires catalog.core;
}
~~~

Nếu `com.example.catalog.Product` là public class với public method, caller `inspector.app` có thể dùng reflection tới public member khi đáp ứng các quy tắc truy cập. Nhưng `exports` **không** đồng nghĩa module khác được phép bật private access cho mọi member của `Product`.

Nếu cần framework bên ngoài đọc private field có chủ đích, module sở hữu package có thể mở có giới hạn:

~~~java
module catalog.core {
    exports com.example.catalog;
    opens com.example.catalog to inspector.app;
}
~~~

Trong trường hợp đó, `trySetAccessible()` đối với private member có thể thành công từ `inspector.app`.

Một số điểm cần tách biệt:

1. `canAccess(receiver)` không tự mở package.
2. `setAccessible(true)` không thể vượt qua mọi ranh giới module một cách tùy ý.
3. `trySetAccessible()` có thể trả `false` khi package không mở thích hợp.
4. Receiver `null`/instance đúng vẫn bắt buộc, kể cả khi accessible flag bật.
5. Khi reflection truy cập cross-module, hợp đồng `AccessibleObject` có một khác biệt với Java source access: **assume readability** trong kiểm tra reflective access; không nên đồng nhất nó với kết quả biên dịch source giữa hai module.

### 12.1. Không biến --add-opens thành giải pháp kiến trúc mặc định

Tùy chọn `--add-opens module/package=target.module` có thể hỗ trợ chẩn đoán hoặc migration ở môi trường có quyền cấu hình JVM. Nhưng với code thuộc dự án của mình, ưu tiên khai báo `opens` có giới hạn trong `module-info.java` hoặc xây dựng public API đủ dùng.

Không khuyến nghị `--illegal-access`: tùy chọn này đã lỗi thời và không còn là cơ chế mở sâu các module JDK trên bản Java hiện đại. Không dựa vào internal reflection hook để vượt strong encapsulation.

## 13. Điều gì xảy ra sau khi canAccess trả true?

`true` không phải lời hứa thao tác tiếp theo chắc chắn thành công. Các tình huống vẫn có thể lỗi:

- `Method.invoke` truyền sai số lượng hoặc kiểu tham số → lỗi argument.
- Method được gọi ném exception → reflection bọc trong `InvocationTargetException`.
- `Field.set` vào field không thể sửa → có thể thất bại dù phép đọc được cho phép.
- Constructor được phép gọi nhưng code bên trong ném exception.
- Receiver hợp lệ lúc check nhưng call thực tế truyền một object khác hoặc `null`.
- Code ứng dụng cần permission/validation nghiệp vụ khác ngoài Java language access.

Ví dụ:

~~~java
Method method = String.class.getDeclaredMethod(
        "substring", int.class);

String value = "Java";

if (method.canAccess(value)) {
    try {
        System.out.println(method.invoke(value, 1)); // "ava"
    } catch (ReflectiveOperationException exception) {
        throw new RuntimeException("Invocation failed", exception);
    }
}
~~~

Nếu đổi tham số `1` thành một index không hợp lệ, phương thức được phép truy cập vẫn có thể ném `StringIndexOutOfBoundsException`, được reflection bọc bởi `InvocationTargetException`.

### 13.1. final field và record không trở thành mutable

Dù `setAccessible(true)` có thể bật cờ truy cập trong một số trường hợp, nó không cấp khả năng ghi tùy ý vào các non-modifiable final field được Javadoc xác định, gồm static final fields, final fields thuộc hidden class hoặc record.

`canAccess` nói về khả năng dùng reflected object theo access checks; không phải API kiểm tra toàn bộ tính khả biến của field.

## 14. Hàm tiện ích chọn receiver cho Field/Method/Constructor

Nếu công cụ xử lý nhiều loại reflective member, có thể viết helper để chọn receiver đúng loại trước khi gọi `canAccess`.

~~~java
import java.lang.reflect.AccessibleObject;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class ReflectionAccessCheck {

    public static boolean canUse(
            AccessibleObject member,
            Object instance) {

        if (member instanceof Constructor<?>) {
            return member.canAccess(null);
        }

        if (member instanceof Field field) {
            if (Modifier.isStatic(field.getModifiers())) {
                return field.canAccess(null);
            }
            requireReceiver(field.getDeclaringClass(), instance);
            return field.canAccess(instance);
        }

        if (member instanceof Method method) {
            if (Modifier.isStatic(method.getModifiers())) {
                return method.canAccess(null);
            }
            requireReceiver(method.getDeclaringClass(), instance);
            return method.canAccess(instance);
        }

        throw new IllegalArgumentException(
                "Unsupported reflected member: " + member);
    }

    private static void requireReceiver(
            Class<?> declaringClass,
            Object instance) {

        if (!declaringClass.isInstance(instance)) {
            throw new IllegalArgumentException(
                    "Expected receiver instance of "
                            + declaringClass.getName());
        }
    }
}
~~~

Điểm đúng:

- Constructor → `canAccess(null)`.
- Static field/method → `canAccess(null)`.
- Instance field/method → kiểm tra `Class.isInstance` trước, rồi `canAccess(instance)`.
- Receiver không phù hợp → phát hiện và báo lỗi lập trình, không âm thầm trả `false`.

**Giới hạn quan trọng:** Helper này hỏi quyền của **class ReflectionAccessCheck** là caller trực tiếp của `canAccess`. Nếu code khác ở package/module khác dùng helper rồi tự truy cập member, kết quả không nhất thiết giống với lời gọi `canAccess` được thực hiện ngay tại code đó. Helper hữu ích khi chính nó cũng thực hiện thao tác reflection hoặc khi bạn đã thiết kế rõ trust boundary.

Vì dùng pattern matching for `instanceof`, ví dụ cần JDK hỗ trợ tính năng đã trở thành final từ Java 16. Nếu dự án đặt baseline Java 17+ hay JDK hiện đại, cú pháp này phù hợp; nếu target cũ hơn, dùng cast truyền thống.

## 15. Quy trình chẩn đoán khi canAccess trả false hoặc throw

Khi một framework báo không truy cập được thành viên:

1. Xác định reflective object là `Field`, `Method` hay `Constructor`.
2. In `getDeclaringClass().getName()` và `getModifiers()` để biết class khai báo và modifier.
3. Dùng `Modifier.isStatic(...)` nếu là field/method.
4. Chọn receiver: static/constructor → `null`; instance → object phù hợp.
5. Nếu vẫn có `IllegalArgumentException`, xem lỗi receiver hoặc loại member trước tiên.
6. Nếu nhận `false`, kiểm tra visibility của member và declaring class.
7. Kiểm tra class thực hiện lời gọi `canAccess` là class nào; helper/caller khác nhau có thể thay đổi kết quả.
8. Nếu dùng named modules, kiểm tra `exports` và `opens` trên module sở hữu.
9. Nếu cần deep reflection, thử `trySetAccessible()` có chủ đích và xử lý `false`.
10. Không dùng `isAccessible()` deprecated để thay `canAccess`.
11. Xác minh đường thao tác thật: `Field.get`, `Method.invoke` hoặc `Constructor.newInstance`.
12. Tách lỗi quyền truy cập khỏi lỗi tham số, lỗi body method và lỗi final field.
13. Ghi JDK version, class/module/package và đường gọi để chẩn đoán có thể tái hiện.

Để tiện quan sát:

~~~java
import java.lang.reflect.Member;
import java.lang.reflect.Modifier;

static void describe(Member member) {
    System.out.println("declaring=" + member.getDeclaringClass().getName());
    System.out.println("modifiers=" + Modifier.toString(member.getModifiers()));
}
~~~

Khi dùng `Field`/`Method`/`Constructor`, tất cả đều thực hiện interface `Member`, nên có thể dùng helper đọc metadata này.

Không log dữ liệu nhạy cảm từ private field khi chỉ cần kiểm tra access control; metadata thường đủ để định vị lỗi.

## 16. Những hiểu nhầm thường gặp

| Nhầm lẫn | Quy tắc đúng |
|---|---|
| `canAccess(null)` kiểm tra được mọi member | Với instance field/method, nó ném `IllegalArgumentException` |
| Static field/method có thể truyền instance vào `canAccess` | Bắt buộc truyền `null` |
| Constructor cần truyền một object thử nghiệm | Constructor yêu cầu `null` |
| Receiver object sai kiểu sẽ trả `false` | Sai kiểu → `IllegalArgumentException` |
| `canAccess` trả `true` vì đã lấy được member bằng `getDeclared...` | Lấy metadata không cấp quyền sử dụng |
| Private member luôn trả `false` | Caller cùng class/nest hoặc accessible flag có thể khiến `true` |
| `canAccess` là thuộc tính cố định của member | Phụ thuộc caller, receiver, accessibility và module |
| `trySetAccessible()` chỉ kiểm tra, không thay đổi gì | Nó có thể bật accessible flag |
| `isAccessible()` là cách kiểm tra quyền tương đương | Deprecated; chỉ phản ánh accessible flag |
| `exports` cho phép deep reflection vào private | Cần `opens` phù hợp để bật suppress checks cross-module |
| Method.invoke static cho phép object nên canAccess cũng vậy | Hợp đồng hai API khác nhau |
| canAccess true đảm bảo invoke/set thành công | Tham số, body exception, final field vẫn có thể khiến thao tác lỗi |
| JEP 416 thêm mới canAccess trong Java 18 | `canAccess` có từ Java 9; JEP 416 đổi implementation core reflection |

## 17. Bài tập thực hành

### Bài 1 — Matrix receiver

Chạy `CanAccessReceivers.java`. Ghi kết quả cho static field/method, instance field/method và constructor, với receiver null, đúng kiểu và sai kiểu.

**Tiêu chí đạt:** Giải thích chính xác trường hợp `true`, `false` hoặc `IllegalArgumentException`.

### Bài 2 — Subclass receiver

Tạo subclass của `Sample` và truyền object subclass vào `canAccess` của một public instance field hoặc method được khai báo trên `Sample`.

**Tiêu chí đạt:** Không yêu cầu runtime class của receiver phải bằng declaring class; kiểm tra quan hệ kế thừa phù hợp.

### Bài 3 — Private access và nestmates

Đưa `Sample` thành nested class bên trong class kiểm tra, rồi so sánh private field access với trường hợp hai top-level class riêng.

**Tiêu chí đạt:** Nhận ra vì sao kết quả có thể đổi khi caller trở thành nestmate.

### Bài 4 — Protected receiver giữa các package

Chạy ví dụ `Base` và `Child`. Kiểm tra một receiver là `Child`, một receiver là `Base`.

**Tiêu chí đạt:** Giải thích vì sao cả hai đều hợp lệ về kiểu nhưng quyền protected instance có thể khác.

### Bài 5 — JPMS exports và opens

Tạo hai named modules: một module có public type với private field, module kia dùng reflection. Thử chỉ `exports`, rồi thêm `opens ... to ...`.

**Tiêu chí đạt:** `canAccess` đối với private field ban đầu là false ở caller ngoài module; `trySetAccessible` chỉ bật khi package được mở phù hợp.

### Bài 6 — Public method nhưng lỗi khi invoke

Dùng `Method.invoke` gọi một public method với đối số không hợp lệ sau khi `canAccess` trả `true`.

**Tiêu chí đạt:** Phân biệt quyền truy cập hợp lệ với `InvocationTargetException` hoặc lỗi tham số của operation.

## 18. Checklist khi dùng canAccess trong framework

- [ ] Đã phân biệt `Field`, `Method` và `Constructor`.
- [ ] Với static field/method, luôn gọi `canAccess(null)`.
- [ ] Với constructor, luôn gọi `canAccess(null)`.
- [ ] Với instance field/method, đã có receiver khác null.
- [ ] Receiver là instance của declaring class hoặc kiểu con hợp lệ.
- [ ] Không gộp `IllegalArgumentException` của receiver thành kết quả false.
- [ ] Hiểu caller hiện tại là class gọi `canAccess`.
- [ ] Không xem kết quả là thuộc tính global vĩnh viễn của member.
- [ ] Không nhầm `getDeclared...` với quyền truy cập.
- [ ] Không dùng `isAccessible()` deprecated.
- [ ] Dùng `trySetAccessible` có chủ đích nếu thật sự cần deep reflection.
- [ ] Đã kiểm tra `exports`/`opens` khi qua named module.
- [ ] Không mặc định `--add-opens` là giải pháp kiến trúc lâu dài.
- [ ] Tách access check với khả năng ghi final field và exception của invoked code.
- [ ] Có test classpath/module path và protected/nestmate khi phù hợp.
- [ ] Kiểm chứng bằng Javadoc trên chính bản JDK đang chạy.

## 19. Tài liệu chính thức

1. [AccessibleObject — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): hợp đồng `canAccess(Object)`, receiver, `trySetAccessible`, `setAccessible`, module access và `isAccessible` deprecated.
2. [Field — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html): `get`/`set` và ý nghĩa receiver với static field.
3. [Method — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, receiver của static và instance method, exception.
4. [Constructor — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance` và constructor access.
5. [Modifier — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Modifier.html): `isStatic`, `isPublic`, modifier bits.
6. [Java Language Specification `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.6): public/protected/package/private access.
7. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi implementation core reflection trong Java 18, không thay hợp đồng receiver.
8. [JEP 261 — Module System](https://openjdk.org/jeps/261): bối cảnh exports/opens và strong encapsulation.

**Kết quả cần đạt:** Bạn biết dùng `canAccess(null)` cho static member và constructor, truyền instance phù hợp cho instance field/method, nhận diện đúng `IllegalArgumentException` khi receiver sai và `false` khi quyền truy cập không được phép. Bạn cũng hiểu quyền reflection phụ thuộc caller, accessible flag và ranh giới module; JEP 416 thay implementation ở Java 18 chứ không làm thay đổi những quy tắc này.
