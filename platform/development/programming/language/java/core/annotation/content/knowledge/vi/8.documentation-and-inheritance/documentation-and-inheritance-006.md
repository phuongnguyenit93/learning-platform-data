# Phân biệt kế thừa annotation với kế thừa thành viên Java

## 1. Hai cơ chế mang tên “kế thừa” nhưng hoạt động khác nhau

Khi viết:

~~~java
class Parent {
    public void execute() {}
}

class Child extends Parent {}
~~~

`Child` có thể gọi `execute()` dù không tự khai báo phương thức ấy. Đây là **kế thừa thành viên Java**: được điều khiển bởi `extends`, `implements`, quyền truy cập, override/hiding và những quy tắc của ngôn ngữ.

Bây giờ xét:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Role {
    String value();
}

@Role("service")
class Parent {}

class Child extends Parent {}
~~~

`Child.class.getAnnotation(Role.class)` có thể trả về `@Role("service")` dù `Child` không khai báo trực tiếp annotation ấy. Đây là **kế thừa annotation theo `@Inherited` khi tra cứu trên class**. Nó khác với việc `Child` kế thừa các method hoặc field từ `Parent`.

Điểm mấu chốt: **`@Inherited` chỉ điều khiển cách tìm một loại annotation trên khai báo class qua hệ thống superclass; nó không sao chép annotation lên mọi field, method, constructor hoặc method override.** Ngược lại, quy tắc kế thừa thành viên Java vẫn hoạt động dù có hay không có `@Inherited`.

## 2. Kế thừa thành viên Java: class con thực sự được sử dụng những gì?

Một class có thể kế thừa các thành viên thích hợp từ superclass hoặc superinterface, tùy loại thành viên và quy tắc truy cập. Các nhóm cần phân biệt:

| Thành viên | Quy tắc quan trọng |
|---|---|
| Instance method | Method phù hợp có thể được kế thừa; subclass có thể **override** method cho phép override. |
| `public`/`protected` field | Field phù hợp có thể được kế thừa; field trùng tên ở subclass **hide** field gốc, không override. |
| Method `static` | Method được kế thừa trong các điều kiện phù hợp; method `static` trùng chữ ký có thể **hide**, không tham gia dynamic dispatch như instance override. |
| Thành viên `private` | Không được kế thừa theo quy tắc ngôn ngữ; method/field private vẫn thuộc class khai báo. |
| Thành viên package-private | Việc được kế thừa/phạm vi truy cập phụ thuộc package và các điều kiện của JLS. |
| Constructor | **Không được kế thừa**; constructor của subclass được khai báo riêng và gọi constructor superclass theo quy tắc khởi tạo. |
| Interface method | Class có thể triển khai abstract method hoặc kế thừa default method, tùy xung đột và quy tắc override. |

Với method instance, một lời gọi trên đối tượng có thể chạy implementation ở subclass nhờ **dynamic dispatch**. Trong khi đó, metadata annotation gắn vào từng method declaration cụ thể; Java không tự sao chép annotation từ method cha sang method override.

Ví dụ:

~~~java
class Parent {
    public String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() {
        return "child";
    }
}
~~~

`new Child().label()` trả về `"child"` do Java chọn method override. Annotation trên `Parent.label()`, nếu có, không tự trở thành annotation trực tiếp của `Child.label()`.

## 3. `@Inherited` thật sự làm gì?

`java.lang.annotation.Inherited` là một **meta-annotation**: bạn đặt nó lên **khai báo annotation type**, không đặt trực tiếp lên class con hay một method để yêu cầu kế thừa.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Environment {
    String value();
}
~~~

Với một annotation type mang `@Inherited`, khi tra cứu annotation đó trên một **class declaration**, nếu class không có annotation tương ứng được khai báo trực tiếp thì cơ chế tra cứu sẽ tiếp tục theo **chuỗi superclass** cho đến khi gặp annotation hoặc tới `Object`.

~~~java
@Environment("production")
class Parent {}

class Middle extends Parent {}

class Child extends Middle {}
~~~

Nếu hỏi `Child.class.getAnnotation(Environment.class)`, reflection có thể tìm đến annotation của `Parent` và trả về `@Environment("production")`.

Điểm cần nhớ:

1. `@Inherited` **không bắt buộc** để một class kế thừa các method/field thông thường.
2. `@Inherited` áp dụng tới việc tra cứu annotation trên **class**, không tự vận dụng cho method, field hay constructor.
3. Nó chỉ lần theo **superclass**. Annotation gắn trên **interface** không được tự truyền sang class triển khai, cũng không tự truyền từ một interface sang subinterface bằng cơ chế `@Inherited`.
4. Nếu subclass khai báo trực tiếp annotation cùng loại, giá trị khai báo tại subclass được dùng; không tự trộn các phần tử của hai annotation.
5. Để tra cứu thông qua reflection lúc chạy, annotation type cần `@Retention(RetentionPolicy.RUNTIME)`. `@Inherited` tự nó **không thay đổi retention**.

### 3.1. `@Target` và `@Retention` có vai trò riêng

`@Target(ElementType.TYPE)` cho phép gắn annotation lên khai báo class và interface; `@Inherited` có hiệu lực khi tìm annotation **trên class** qua superclass. `@Retention(RUNTIME)` mới khiến annotation có thể được Java reflection truy xuất khi ứng dụng chạy.

Nếu một annotation dùng `@Retention(CLASS)` hoặc `@Retention(SOURCE)`, việc thêm `@Inherited` không làm `Class.getAnnotation(...)` bỗng trả dữ liệu lúc runtime. Mặc định, nếu bỏ `@Retention`, annotation có retention `CLASS`.

`@Inherited` cũng không phải cơ chế của `@Documented`: `@Documented` liên quan tới việc đưa annotation vào Javadoc, không điều khiển quy tắc nhận diện annotation trong superclass.

## 4. Nhìn vào API reflection: khai báo trực tiếp hay được tìm qua superclass?

Hai cách truy vấn thường gặp:

~~~java
// Ví dụ minh họa, giả định Environment/Parent/Child ở mục 3 đã được khai báo:
Environment inherited = Child.class.getAnnotation(Environment.class);
Environment declared = Child.class.getDeclaredAnnotation(Environment.class);
~~~

- `getAnnotation(Environment.class)`: trên `Class`, trả annotation nếu trực tiếp hiện diện hoặc hiện diện theo quy tắc kế thừa thích hợp. Với `@Inherited`, có thể tìm trên superclass.
- `getDeclaredAnnotation(Environment.class)`: chỉ xét annotation khai báo **trực tiếp** tại class được hỏi; không tìm qua superclass.
- `getAnnotations()`: thu những annotation trực tiếp hiện diện và những annotation kế thừa được tính là hiện diện theo API tương ứng.
- `getDeclaredAnnotations()`: chỉ thu annotation khai báo trực tiếp tại class.
- `getAnnotationsByType()` và `getDeclaredAnnotationsByType()`: có thêm quy tắc cho annotation `@Repeatable`; khi làm việc với repeated annotation phải đọc đúng contract của hai API này.

Ví dụ minh họa kết quả kỳ vọng nếu `@Environment("production")` chỉ nằm ở `Parent`:

| Truy vấn | Kết quả |
|---|---|
| `Parent.class.getDeclaredAnnotation(Environment.class)` | Có `@Environment("production")` |
| `Child.class.getAnnotation(Environment.class)` | Có `@Environment("production")` nhờ `@Inherited` |
| `Child.class.getDeclaredAnnotation(Environment.class)` | `null` |
| `Child.class.getDeclaredAnnotations()` | Không chứa `Environment` nếu Child không khai báo nó |
| `Child.class.getSuperclass()` | `Middle.class` trong ví dụ ba cấp |

**Một lớp class được tìm thấy annotation qua API không có nghĩa class file của subclass chứa một bản copy trực tiếp của annotation.** Bằng chứng đơn giản là `getAnnotation(...)` có dữ liệu trong khi `getDeclaredAnnotation(...)` trả `null`.

Nếu subclass tự đặt:

~~~java
@Environment("development")
class Child extends Parent {}
~~~

thì `Child.class.getAnnotation(Environment.class).value()` là `"development"`. Hệ thống lấy annotation ở Child; các giá trị không được “hợp nhất” với annotation cùng type ở Parent. Phần tử thiếu tại nơi khai báo sẽ dùng `default` của annotation type nếu có.

## 5. `@Inherited` **không** kế thừa annotation từ interface

Đây là lỗi suy luận phổ biến: Java có thể kế thừa hoặc triển khai method từ interface, nhưng annotation ở **interface declaration** không tham gia tìm kiếm superclass cho `@Inherited`.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("api")
interface Api {}

class ApiImpl implements Api {}
~~~

Dù `Category` mang `@Inherited`, truy vấn sau trả `null`:

~~~java
System.out.println(ApiImpl.class.getAnnotation(Category.class)); // null
~~~

Tương tự, một interface `ExtendedApi extends Api` không tự nhận `@Category("api")` qua `@Inherited`.

Nếu một framework muốn tìm annotation trên interface, nó phải **chủ động duyệt các interface** và xác định chính sách tìm kiếm. Java reflection mặc định của `Class.getAnnotation` không tự bổ sung quy tắc quét interface. Đây là khác biệt thường gặp giữa reflection thuần Java và các utility do framework thiết kế.

## 6. `@Inherited` trên annotation dành cho method/field có tác dụng không?

Một annotation type có thể khai báo `@Inherited` dù `@Target` của nó chỉ gồm `METHOD` hoặc `FIELD`; cú pháp đó không biến annotation thành metadata tự lan sang member của subclass.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Reviewed {}

class Base {
    @Reviewed
    public void execute() {}
}

class Derived extends Base {
    @Override
    public void execute() {}
}
~~~

Hai đối tượng method reflection là khác nhau:

~~~java
Base.class.getDeclaredMethod("execute").isAnnotationPresent(Reviewed.class);    // true
Derived.class.getDeclaredMethod("execute").isAnnotationPresent(Reviewed.class); // false
~~~

`Derived.execute()` override một method Java bình thường. Việc method gốc có `@Reviewed` không tự gắn `@Reviewed` vào method override. Chính sách “method override có hiệu lực annotation của method cha hay không” nếu được yêu cầu phải do thư viện sử dụng annotation quy định và tự tra cứu.

Điều tương tự áp dụng cho field: annotation trên field của `Base` không tự sao chép lên một field mới trùng tên trong `Derived`.

## 7. Điểm dễ nhầm: lấy được annotation của method kế thừa qua `getMethod()`

Đặt lại trường hợp:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Reviewed {}

class Base {
    @Reviewed
    public void execute() {}
}

class Derived extends Base {
    // Không override execute().
}
~~~

Lúc này:

~~~java
var method = Derived.class.getMethod("execute");
System.out.println(method.getDeclaringClass().getSimpleName()); // Base
System.out.println(method.isAnnotationPresent(Reviewed.class)); // true
~~~

Tại sao thấy `true` khi `@Inherited` không áp dụng lên method?

**Bởi vì `getMethod("execute")` tìm được chính method được khai báo tại `Base`** (một method đang được `Derived` kế thừa). Đối tượng `Method` có `getDeclaringClass() == Base.class`, nên annotation `@Reviewed` là annotation **trực tiếp** của method ở Base. Java không tạo method mới rồi chép annotation sang.

Nếu `Derived` override `execute()`, `Derived.class.getMethod("execute")` thường trỏ tới declaration mới tại Derived, không còn annotation gốc nếu người viết không đánh dấu lại. Đây là khác biệt giữa:

- **Phạm vi tìm member**: `Class.getMethod` có thể tra các `public` method kế thừa, trong khi `getDeclaredMethod` chỉ xét method được khai báo tại đúng class.
- **Phạm vi tìm annotation trên member**: `Method.getAnnotation` đọc annotation của method declaration mà đối tượng `Method` biểu diễn; không tự đọc method override ở các superclass khác.

Vì vậy, thấy annotation trên một `Method` trả từ `Derived.class.getMethod(...)` **không đủ bằng chứng** để nói `@Inherited` đã lan truyền annotation cho method.

## 8. Tương tự với field: field kế thừa khác field bị hide

Giả sử:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Column {}

class Parent {
    @Column
    public int id = 1;
}

class Child extends Parent {}           // Kế thừa field id

class ShadowChild extends Parent {
    public int id = 2;                  // Hide field của Parent
}
~~~

Khi gọi:

~~~java
var fromChild = Child.class.getField("id");
var fromShadow = ShadowChild.class.getField("id");
~~~

- `fromChild.getDeclaringClass()` là `Parent.class`; `fromChild` mang `@Column` vì đó là **field gốc** tại Parent.
- `fromShadow.getDeclaringClass()` là `ShadowChild.class`; field mới không tự mang `@Column` dù field trùng tên.
- Nếu trực tiếp hỏi `Parent.class.getDeclaredField("id")`, vẫn thấy field gốc và annotation của nó.
- Không có hiện tượng dynamic dispatch cho field giống như đối với instance method; field hiding được xác định theo kiểu tham chiếu và quy tắc truy cập.

Một constructor cũng không được kế thừa: `Child` có thể gọi constructor của `Parent` thông qua `super(...)`, nhưng nó không “sở hữu” bản sao constructor hay annotation ở constructor cha. Annotation của parameter cũng không tự sao chép vào constructor subclass.

## 9. Ví dụ Java 17+ chạy được: đối chiếu các tình huống

Tạo file **Main.java** trong một thư mục riêng với toàn bộ nội dung sau:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Mark {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {}

@Role("base")
@LocalOnly
class Base {
    @Mark
    public String report() {
        return "base";
    }

    @FieldMark
    public int id = 7;
}

class PlainChild extends Base {}

class Child extends Base {
    @Override
    public String report() {
        return "child";
    }
}

@Role("child")
class OwnRoleChild extends Base {}

class ShadowChild extends Base {
    public int id = 9;
}

@Role("interface")
interface Api {
    @Mark
    default String ping() {
        return "api";
    }
}

class ApiImpl implements Api {}

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("plainRole="
                + PlainChild.class.getAnnotation(Role.class).value());
        System.out.println("plainRoleDeclared="
                + (PlainChild.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("plainLocalOnly="
                + (PlainChild.class.getAnnotation(LocalOnly.class) != null));
        System.out.println("ownRole="
                + OwnRoleChild.class.getAnnotation(Role.class).value());
        System.out.println("apiImplRole="
                + (ApiImpl.class.getAnnotation(Role.class) != null));

        System.out.println("plainMethodDeclaring="
                + PlainChild.class.getMethod("report")
                        .getDeclaringClass().getSimpleName());
        System.out.println("plainMethodMark="
                + PlainChild.class.getMethod("report")
                        .isAnnotationPresent(Mark.class));
        System.out.println("overriddenMethodDeclaring="
                + Child.class.getMethod("report")
                        .getDeclaringClass().getSimpleName());
        System.out.println("overriddenMethodMark="
                + Child.class.getMethod("report")
                        .isAnnotationPresent(Mark.class));
        System.out.println("childMethodResult=" + new Child().report());

        System.out.println("plainFieldDeclaring="
                + PlainChild.class.getField("id")
                        .getDeclaringClass().getSimpleName());
        System.out.println("plainFieldMark="
                + PlainChild.class.getField("id")
                        .isAnnotationPresent(FieldMark.class));
        System.out.println("shadowFieldDeclaring="
                + ShadowChild.class.getField("id")
                        .getDeclaringClass().getSimpleName());
        System.out.println("shadowFieldMark="
                + ShadowChild.class.getField("id")
                        .isAnnotationPresent(FieldMark.class));

        System.out.println("apiImplPingMark="
                + ApiImpl.class.getMethod("ping")
                        .isAnnotationPresent(Mark.class));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả:

~~~text
plainRole=base
plainRoleDeclared=false
plainLocalOnly=false
ownRole=child
apiImplRole=false
plainMethodDeclaring=Base
plainMethodMark=true
overriddenMethodDeclaring=Child
overriddenMethodMark=false
childMethodResult=child
plainFieldDeclaring=Base
plainFieldMark=true
shadowFieldDeclaring=ShadowChild
shadowFieldMark=false
apiImplPingMark=true
~~~

Hãy đọc từng nhóm kết quả theo đúng bản chất:

1. `plainRole=base` nhưng `plainRoleDeclared=false`: `@Inherited` giúp reflection tìm metadata class trên superclass; PlainChild không khai báo trực tiếp `@Role`.
2. `plainLocalOnly=false`: annotation type `LocalOnly` không có `@Inherited`, nên không tự có trên PlainChild dù Base mang nó.
3. `ownRole=child`: annotation cùng type được Child (ở đây `OwnRoleChild`) khai báo trực tiếp sẽ ưu tiên dữ liệu tại subclass.
4. `apiImplRole=false`: annotation từ interface `Api` không được tự kế thừa bằng `@Inherited`.
5. `plainMethodDeclaring=Base` và `plainMethodMark=true`: `getMethod` trả về method ở Base; không phải lan truyền annotation lên method mới.
6. `overriddenMethodDeclaring=Child` và `overriddenMethodMark=false`: annotation không tự sao chép sang method override.
7. `childMethodResult=child`: Java vẫn dùng dynamic dispatch và gọi implementation ở Child bất kể annotation.
8. `plainFieldDeclaring=Base`, `plainFieldMark=true`: Field kế thừa đang được phản ánh là field gốc ở Base.
9. `shadowFieldDeclaring=ShadowChild`, `shadowFieldMark=false`: field mới hide field cũ, không tự nhận metadata của field cũ.
10. `apiImplPingMark=true`: `ApiImpl.class.getMethod("ping")` nhìn thấy method `default` gốc ở `Api`; annotation của method này là annotation tại interface method đó, **không phải kết quả của `@Inherited` trên method**.

Hai annotation type `Mark` và `FieldMark` trong ví dụ **cố ý mang `@Inherited`** để chứng minh meta-annotation này không làm annotation “di chuyển” từ method/field cha sang declaration mới ở subclass.

## 10. `@Override` và `@Inherited` không liên quan trực tiếp

`@Override` được gắn lên **method declaration** và dùng để yêu cầu compiler kiểm tra method có thực sự override/implement method hợp lệ theo quy tắc Java hay không. Nó không có nhiệm vụ sao chép annotation giữa các method.

~~~java
class Base {
    public void save() {}
}

class Child extends Base {
    @Override
    public void save() {}
}
~~~

`@Override` trong Child chỉ xác nhận quan hệ override hợp lệ. Nếu Base.save() có thêm `@Mark`, điều đó **không** khiến Child.save() nhận `@Mark`. Nếu một thư viện yêu cầu annotation tại chính method implementation, phải đánh dấu tại declaration phù hợp hoặc xây dựng logic tìm metadata theo hierarchy.

Kể cả trong trường hợp không có `@Override`, quan hệ override vẫn được Java quyết định theo signature, visibility, inheritance và các quy tắc liên quan. Vì thế `@Override` là công cụ bắt lỗi compile-time, không phải điều kiện tạo ra kế thừa method.

## 11. Khi dùng framework hoặc tự viết công cụ đọc annotation

Ví dụ một thư viện muốn biết class nào mang một “role” hoặc method nào mang “policy”. Có những chính sách tìm khác nhau:

| Nhu cầu | API/cách tiếp cận phù hợp | Điều cần cân nhắc |
|---|---|---|
| Tìm class-level annotation hỗ trợ superclass inheritance | `clazz.getAnnotation(Role.class)` | Cần `@Inherited` và `RUNTIME`; không đi vào interface. |
| Chỉ tìm class-level annotation khai báo tại class hiện tại | `clazz.getDeclaredAnnotation(Role.class)` | Bỏ qua superclass. |
| Đọc annotation trên một method được tìm theo API public | `clazz.getMethod(...).getAnnotation(Mark.class)` | Có thể nhận `Method` khai báo ở superclass/interface; hỏi `getDeclaringClass()`. |
| Chỉ đọc method khai báo ở class hiện tại | `clazz.getDeclaredMethod(...)` | Không tự truy ngược method bị override, có thể ném `NoSuchMethodException`. |
| Đọc field annotation | `getField(...)` hoặc `getDeclaredField(...)` | Phân biệt field kế thừa với field bị hide. |
| Tìm annotation từ superclass method bị override | Tự duyệt superclass và tìm method tương ứng | Phải xử lý signature, override, visibility, bridge/generic methods theo contract. |
| Tìm class annotation trên interface | Tự duyệt interface hierarchy nếu policy yêu cầu | `@Inherited` không tự tìm interface. |

Khi tự implement việc tra cứu sâu, cần quyết định rõ **có ưu tiên metadata ở subclass**, có hợp nhất/override giá trị không, xử lý interface nào, xử lý `@Repeatable` ra sao. Đây là **quy ước của thư viện**, không tự phát sinh từ `@Inherited`.

Framework có thể cung cấp các utility riêng để tìm annotation trong nhiều tầng class, interface hoặc method. Đừng lấy kết quả của utility framework để suy ra quy tắc mặc định của `Class.getAnnotation()`; hãy đọc contract API cụ thể.

Một ví dụ dễ xảy ra trong ứng dụng: `@Role` của class cha có thể được `Child.class.getAnnotation(Role.class)` tìm thấy, trong khi annotation đánh dấu `Base.save()` không tồn tại trên `Child.save()` sau khi override. Nếu logic bảo mật/validation của bạn chỉ quét annotation tại method implementation thì cần đặt annotation đúng vị trí hoặc sử dụng một cơ chế truy vấn nhất quán.

## 12. Các sai lầm thường gặp và cách kiểm tra

### Sai lầm 1: “Child kế thừa method thì cũng kế thừa annotation ở method”

Không đúng khi Child **override** method: method override là một declaration mới. Nếu Child không override, `getMethod` có thể trả về chính method cha với annotation sẵn có. Cần kiểm tra `Method.getDeclaringClass()` trước khi kết luận.

### Sai lầm 2: “Thêm `@Inherited` là annotation từ interface cũng truyền xuống”

Không đúng: `@Inherited` tra theo superclass class, không tìm interface và không tra hết toàn bộ cây type.

### Sai lầm 3: “Tôi thấy annotation từ `getAnnotation()` nên annotation trực tiếp nằm trên subclass”

Hãy kiểm tra `getDeclaredAnnotation()`. Nếu `getAnnotation()` khác `null` nhưng `getDeclaredAnnotation()` là `null`, đó có thể là annotation class-level tìm được qua `@Inherited`.

### Sai lầm 4: “Field cùng tên ở subclass dùng lại annotation của field cha”

Field ở subclass có thể **hide** field cũ, nhưng hai field là hai declaration. Hãy kiểm tra `Field.getDeclaringClass()`.

### Sai lầm 5: “`@Override` tự kế thừa annotation của method bị override”

`@Override` chỉ yêu cầu kiểm tra override tại compile-time, không tự chép metadata annotation.

### Sai lầm 6: “`@Inherited` biến annotation thành quy tắc runtime tự chạy”

Annotation là metadata. Muốn thay đổi hành vi của ứng dụng, phải có compiler, công cụ hoặc runtime framework **đọc và diễn giải** metadata. `@Inherited` chỉ ảnh hưởng cách annotation có thể được tìm thấy trong những trường hợp hợp lệ.

### Sai lầm 7: “Chỉ cần `@Inherited`, không cần `@Retention(RUNTIME)`”

Không đúng nếu code định đọc annotation bằng reflection lúc chạy. Annotation với retention mặc định `CLASS` không tự có trong kết quả của `Class.getAnnotation` ở runtime.

### Sai lầm 8: “Constructor cha được kế thừa nên annotation constructor cũng được kế thừa”

Constructor không được kế thừa. Annotation trên constructor của superclass không tự trở thành annotation trên constructor của subclass, kể cả khi subclass gọi `super(...)`.

## 13. Quy trình ngắn để chẩn đoán một annotation “bị mất”

Khi annotation không được tìm thấy như dự kiến, hãy lần lượt kiểm tra:

1. **Vị trí khai báo**: annotation ở `class`, `interface`, `method`, `field`, `constructor` hay `parameter`?
2. **Đích áp dụng**: xem `@Target` có `TYPE`, `METHOD`, `FIELD`... phù hợp với vị trí đó hay không.
3. **Retention**: reflection runtime cần `@Retention(RUNTIME)`.
4. **Quan hệ Java**: class đang `extends` superclass, `implements` interface, hay có method `override`/field `hide`?
5. **API đang gọi**: `getAnnotation` hay `getDeclaredAnnotation`, `getMethod` hay `getDeclaredMethod`, `getField` hay `getDeclaredField`?
6. **Declaring class**: với `Method`/`Field`, gọi `getDeclaringClass()` để biết thực sự đang đọc member nào.
7. **Ý nghĩa nghiệp vụ**: nếu muốn truy tìm annotation dọc method hierarchy hoặc interface hierarchy, xác định và triển khai chính sách ấy rõ ràng.

Đừng sửa lỗi bằng cách thêm `@Inherited` vào mọi annotation type: giải pháp đó sẽ không giúp ích cho method override, field hiding hoặc class triển khai interface.

## 14. Tài liệu chuẩn

- [Java SE 17 JLS §9.6.4.3 — `@Inherited`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): annotation inheritance chỉ trong superclass của class.
- [Java SE 17 API — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): mô tả chính thức về phạm vi và giới hạn đối với interface, method.
- [Java SE 17 API — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): sự khác biệt giữa `getAnnotation`, `getDeclaredAnnotation`, repeatable annotation.
- [Java SE 17 JLS §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): quy tắc kế thừa và override/hiding trong class.
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField` và các API reflection.

**Ghi nhớ:** Java member inheritance trả lời **subclass có thể sử dụng method/field nào**. `@Inherited` trả lời **một class-level annotation có thể được tìm qua superclass khi tra cứu metadata hay không**. Method override và field hiding tạo ra declaration riêng không tự nhận annotation của member cha; method/field đang được kế thừa có thể mang annotation vì bản thân đối tượng reflection trỏ tới declaration gốc.