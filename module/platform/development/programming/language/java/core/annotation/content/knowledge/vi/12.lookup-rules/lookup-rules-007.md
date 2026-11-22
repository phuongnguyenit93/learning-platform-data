# Phân biệt tìm phương thức được kế thừa với kế thừa annotation của phương thức trong Java

Trong Java, có hai câu hỏi dễ bị nhầm là cùng một:

1. **Một lớp con có thể tìm thấy một phương thức được thừa hưởng từ lớp cha hoặc interface bằng reflection không?**
2. **Nếu lớp con ghi đè (override) phương thức đó, annotation trên phương thức cha có tự xuất hiện trên phương thức ghi đè không?**

Câu trả lời lần lượt là **có trong các điều kiện tra cứu phương thức thích hợp**, và **không theo cơ chế Java reflection chuẩn**. Ví dụ, `Child.class.getMethod("run")` có thể trả về một `Method` **được khai báo trong `Parent`**. Khi đọc annotation từ `Method` ấy, bạn thấy annotation gốc vì đang cầm đúng đối tượng phản chiếu của **phương thức cha**. Nhưng khi `Child` tự khai báo `run()` để override, `getMethod("run")` trả về phương thức **của Child**; annotation chỉ có trên `Parent.run()` không tự được chuyển sang.

Đây là chủ đề về **quy tắc tra cứu reflection và nguồn sở hữu annotation**. Nó đặc biệt quan trọng với framework dùng annotation trên method để đăng ký endpoint, validate, logging, phân quyền hoặc đo thời gian xử lý.

## 1. Ba khái niệm cần tách biệt

**Kế thừa phương thức** là cơ chế ngôn ngữ Java: lớp con có thể sử dụng các phương thức instance không private phù hợp từ superclass, và có thể nhận các phương thức từ interface, kể cả default methods. Phạm vi truy cập, override, interface resolution và các quy tắc liên quan quyết định thành viên nào thật sự được kế thừa. Không phải mọi method được khai báo trên lớp cha đều là một method mà lớp con kế thừa.

**Tìm phương thức bằng reflection** là việc dùng API như `Class.getMethod(...)`, `Class.getMethods()`, `Class.getDeclaredMethod(...)` để lấy đối tượng `java.lang.reflect.Method`. Các API này có phạm vi tìm kiếm khác nhau: public members bao gồm phương thức thừa hưởng, hoặc chỉ các method khai báo ngay trong một class/interface.

**Kế thừa annotation của phương thức** là một quy tắc riêng. Java không có quy tắc tổng quát tự sao chép annotation từ method được override xuống overriding method. Meta-annotation `@Inherited` của Java chỉ có ý nghĩa khi truy vấn annotation trên **class declaration** qua superclass theo hợp đồng `java.lang.annotation.Inherited`.

Một điều có vẻ mâu thuẫn nhưng hoàn toàn chính xác:

> Có thể **tìm được phương thức do lớp cha khai báo**, rồi đọc được annotation có trên chính phương thức đó, mà **không có chuyện annotation của method được kế thừa sang một method mới**.

## 2. So sánh các API lấy Method

| API | Phạm vi tìm | Có lấy method kế thừa? | Lưu ý |
| --- | --- | --- | --- |
| `SomeType.class.getMethod("name", parameterTypes...)` | **Public method** tương ứng với tên và các kiểu tham số | **Có**, theo tra cứu public members từ class, superclass và superinterface | Trả `Method` thuộc về nơi khai báo method được chọn; ném `NoSuchMethodException` nếu không tìm được |
| `SomeType.class.getMethods()` | Tập **public methods** của class/interface, kể cả public members được kế thừa | **Có** | Thứ tự mảng không được bảo đảm; có thể có method tổng hợp/bridge do compiler tạo |
| `SomeType.class.getDeclaredMethod("name", parameterTypes...)` | Method **được khai báo tại chính SomeType** | **Không** | Có thể trả public, protected, package-private, private method; cần đúng tên và kiểu tham số |
| `SomeType.class.getDeclaredMethods()` | Các methods được khai báo trực tiếp trong SomeType | **Không** | Không bao gồm method kế thừa; kết quả không có thứ tự cố định |
| `method.getDeclaringClass()` | Lớp/interface khai báo method được `Method` phản chiếu | Không phải thao tác tìm | Dùng để xác định annotation đang được đọc thực sự thuộc method nào |
| `method.getAnnotation(A.class)` | Annotation loại `A` trên **Method hiện tại** | **Không** tự leo lên method cha | Trả `null` nếu annotation không present trên Method này |
| `method.getAnnotationsByType(A.class)` | Các annotation loại `A` trên **Method hiện tại**, gồm xử lý container của repeatable annotation | **Không** tự leo lên các phương thức bị override | Dùng khi `A` có thể lặp lại |

**Điểm quan trọng:** `getMethod("run")` nhận **tên method và kiểu tham số**, không nhận kiểu trả về; nếu overload, phải chỉ đúng parameter types, ví dụ `getMethod("save", String.class, int.class)`. Method overload không đồng nghĩa method override. Khi có bridge/covariant return types, việc chọn method bằng reflection có các chi tiết đặc thù; cần xem các method trả về thay vì mặc định mỗi tên/chữ ký nguồn chỉ ứng với một reflection `Method`.

## 3. Không override: tìm được Method của cha và đọc annotation của cha

Xét mã minh họa:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Trace {}

class Parent {
    @Trace
    public void run() {}
}

class Child extends Parent {
    // Không khai báo run().
}
~~~

Nếu trong một method khác viết:

~~~java
var method = Child.class.getMethod("run");
System.out.println(method.getDeclaringClass().getSimpleName()); // Parent
System.out.println(method.isAnnotationPresent(Trace.class));      // true
~~~

Đây là **đoạn mã minh họa cần được đặt trong method có xử lý `ReflectiveOperationException`**; ví dụ hoàn chỉnh có thể chạy ở mục 6.

Tại sao kết quả là `true`?

1. `getMethod("run")` tìm một **public member method** có thể được gọi trên `Child`.
2. `Child` không override `run()`, nên reflection trả đối tượng `Method` đại diện cho `Parent.run()`.
3. `getDeclaringClass()` trả `Parent.class`. Annotation `@Trace` được khai báo **trên chính `Parent.run()`**.
4. `method.getAnnotation(Trace.class)` đọc annotation từ method cha đang được phản chiếu; **không phải một annotation đã được copy sang một method của Child**.

Ngược lại:

~~~java
Child.class.getDeclaredMethod("run"); // Ném NoSuchMethodException.
~~~

Bởi vì `Child` **không khai báo** method `run()`. `getDeclaredMethod` tuyệt đối không mở rộng phạm vi sang các phương thức của superclass; nếu muốn tra cứu trong hierarchy, ứng dụng phải tự đi lên `getSuperclass()` khi cần.

## 4. Có override: annotation trên method cha không tự có ở method con

Thay `Child` bằng:

~~~java
class Child extends Parent {
    @Override
    public void run() {}
}
~~~

Khi đó:

~~~java
var method = Child.class.getMethod("run");
System.out.println(method.getDeclaringClass().getSimpleName()); // Child
System.out.println(method.isAnnotationPresent(Trace.class));      // false
~~~

`@Override` giúp compiler kiểm tra rằng `Child.run()` thực sự override một method thích hợp; nó **không sao chép annotation `@Trace`**. Method ở lớp con là một khai báo khác, có metadata của riêng nó. Nếu yêu cầu annotation cũng có trên method override theo reflection chuẩn, phải **khai báo `@Trace` trực tiếp ở `Child.run()`**, hoặc thiết kế công cụ riêng để tìm metadata của phương thức cha theo một chính sách xác định.

Ngay cả khi annotation `Trace` được định nghĩa như sau:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {}
~~~

…thì **`@Inherited` vẫn không có tác dụng làm `Child.run()` nhận `@Trace` của `Parent.run()`**. Theo tài liệu `java.lang.annotation.Inherited`, annotation này chỉ kích hoạt việc tìm lên **superclass** khi truy vấn một annotation được khai báo trên **class declaration**. Với method declaration (hoặc annotation trên interface), meta-annotation đó không tự tạo cơ chế inheritance tương ứng.

Tóm lại:

- **Không override:** `Child.class.getMethod("run")` có thể trả `Parent.run()`, nên thấy annotation của `Parent.run()`.
- **Có override, không annotate lại:** `Child.class.getMethod("run")` trả `Child.run()`, nên không thấy annotation vốn chỉ có trên `Parent.run()`.
- **Có override và annotate lại:** annotation ở `Child.run()` được đọc bình thường, vì nó được khai báo trực tiếp tại đó.

## 5. @Inherited hoạt động trên class annotation, không phải method annotation

So sánh tình huống method ở trên với class annotation thực sự:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Group {
    String value();
}

@Group("base")
class Parent {}

class Child extends Parent {}
~~~

Đoạn trên là **ví dụ khai báo độc lập về mặt cú pháp**, không dùng chung tên lớp với ví dụ khác trong bài.

~~~java
var group = Child.class.getAnnotation(Group.class);
System.out.println(group.value()); // base
System.out.println(Child.class.getDeclaredAnnotation(Group.class)); // null
~~~

Hai kết quả trên không mâu thuẫn: `Class.getAnnotation(...)` xem xét annotation type có `@Inherited` và có thể tìm annotation trên superclass; `getDeclaredAnnotation(...)` chỉ xem annotation được khai báo trực tiếp trên `Child`. Đối với một `Method`, không có việc tự tìm method cha chỉ vì annotation type có `@Inherited`.

Bảng đối chiếu:

| Truy vấn | Có tự xét annotation ở superclass? |
| --- | --- |
| `Child.class.getAnnotation(Group.class)`, `Group` có `@Inherited` | **Có**, theo quy tắc `@Inherited` trên class |
| `Child.class.getDeclaredAnnotation(Group.class)` | **Không** |
| `Child.class.getMethod("run")` khi không override | Có thể tìm **method cha**; annotation thấy được vì `Method` được trả chính là method cha |
| `Child.run()` override nhưng không annotate, dùng `Method.getAnnotation(Trace.class)` | **Không** tự tìm metadata của `Parent.run()` |
| `Child.class.getAnnotationsByType(Group.class)` | Có thể xét inherited class annotation tùy contract, repeatable/container |
| `childMethod.getAnnotationsByType(Trace.class)` | Chỉ metadata trên method hiện tại/container, không tự duyệt override hierarchy |

Chú ý `@Inherited` **không** khiến annotation từ một **interface** tự động xuất hiện trên class triển khai interface. Trường hợp này cũng cần xử lý riêng khi framework muốn lấy metadata từ interface.

## 6. Ví dụ Java 17 chạy được: đủ cả inherited, overridden và interface default method

Tạo file duy nhất **MethodInheritanceDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface ClassTag { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Inherited
@interface Action { String value(); }

@ClassTag("parent-class")
class Parent {
    @Action("parent-inherited")
    public void inherited() {}

    @Action("parent-change")
    public void change() {}

    @Action("parent-protected")
    protected void guarded() {}
}

class Child extends Parent {}

class OverridingChild extends Parent {
    @Override public void change() {}
}

interface Greeter {
    @Action("interface-default")
    default void hello() {}
}

class GreeterChild implements Greeter {}
class GreeterOverride implements Greeter {
    @Override public void hello() {}
}

public class MethodInheritanceDemo {
    static void show(String label, Class<?> type, String methodName) throws Exception {
        Method method = type.getMethod(methodName);
        Action marker = method.getAnnotation(Action.class);
        System.out.println(label + ":owner=" +
                method.getDeclaringClass().getSimpleName() +
                ",annotation=" + (marker == null ? "none" : marker.value()));
    }

    public static void main(String[] args) throws Exception {
        show("inherited", Child.class, "inherited");
        show("sameSignature", Child.class, "change");
        show("overridden", OverridingChild.class, "change");
        show("defaultInherited", GreeterChild.class, "hello");
        show("defaultOverridden", GreeterOverride.class, "hello");
        System.out.println("childDeclared=" +
                Arrays.stream(Child.class.getDeclaredMethods())
                    .anyMatch(m -> m.getName().equals("inherited")));
        System.out.println("childPublicMethodsContains=" +
                Arrays.stream(Child.class.getMethods())
                    .anyMatch(m -> m.getName().equals("inherited")));
        System.out.println("protectedInGetMethods=" +
                Arrays.stream(Child.class.getMethods())
                    .anyMatch(m -> m.getName().equals("guarded")));
        System.out.println("protectedDeclaredOnParent=" +
                Parent.class.getDeclaredMethod("guarded")
                        .getAnnotation(Action.class).value());
        System.out.println("classAnnotationInherited=" +
                OverridingChild.class.getAnnotation(ClassTag.class).value());
    }
}
~~~

Dùng JDK 17 trở lên, mở terminal ở thư mục có file rồi chạy:

~~~bash
javac --release 17 -encoding UTF-8 MethodInheritanceDemo.java
java MethodInheritanceDemo
~~~

**Stdout đã được kiểm chứng khi biên dịch bằng `--release 17` và chạy chương trình:**

~~~text
inherited:owner=Parent,annotation=parent-inherited
sameSignature:owner=Parent,annotation=parent-change
overridden:owner=OverridingChild,annotation=none
defaultInherited:owner=Greeter,annotation=interface-default
defaultOverridden:owner=GreeterOverride,annotation=none
childDeclared=false
childPublicMethodsContains=true
protectedInGetMethods=false
protectedDeclaredOnParent=parent-protected
classAnnotationInherited=parent-class
~~~

### Đọc output để hiểu đúng bản chất

**Hai dòng đầu (`inherited` và `sameSignature`).** `Child` không khai báo lại `inherited()` hoặc `change()`. `getMethod` lấy hai `Method` của `Parent` và annotation đi kèm **chính các method đó**. `getDeclaringClass()` cho biết đây là metadata của `Parent`, không phải một annotation mới được khai báo trên `Child`.

**Dòng `overridden`.** `OverridingChild` override `change()` nhưng không gắn `@Action` trên method override. Reflection trả `OverridingChild.change()`, annotation vắng mặt, dù annotation type `Action` **cố ý có `@Inherited`**. Đây là bằng chứng trực tiếp rằng `@Inherited` không mở cơ chế kế thừa method annotations.

**Hai dòng `defaultInherited` và `defaultOverridden`.** `GreeterChild` dùng default method `Greeter.hello()` mà không override, nên `getMethod("hello")` trả method khai báo trên interface `Greeter` và thấy annotation của chính method đó. `GreeterOverride` có method override riêng, không annotate lại nên không thấy annotation. Đây vẫn là **tra cứu Method**, không phải kế thừa annotation method từ interface.

**Ba dòng về declared/public/protected.** `getDeclaredMethods()` của `Child` không có method `inherited()` vì `Child` không khai báo nó; `getMethods()` có vì method của cha là public. Method `Parent.guarded()` là protected, nên không có trong danh sách public `getMethods()`; nhưng `Parent.class.getDeclaredMethod("guarded")` trả method đó, và có thể đọc `@Action`.

**Dòng `classAnnotationInherited`.** `OverridingChild` không gắn `@ClassTag` nhưng `Class.getAnnotation(ClassTag.class)` đọc được giá trị `parent-class` từ lớp cha vì annotation **trên class** được đánh dấu `@Inherited`. Đó là cơ chế riêng, không ảnh hưởng method.

Trong ứng dụng thật, nếu một method được override mà metadata từ cha vẫn có ý nghĩa, cần có **quy tắc kết hợp annotation do framework/ứng dụng định nghĩa**. Java reflection chuẩn không tự quyết định kế thừa metadata theo chính sách nghiệp vụ đó.

## 7. Các trường hợp tra cứu dễ gây hiểu nhầm

### 7.1. Public method so với protected/private method

`getMethod` và `getMethods` chỉ tập trung vào **public methods**. Nếu một phương thức cha là protected, package-private hoặc private, không tìm nó bằng `Child.class.getMethod(...)` chỉ vì subclass có quyền gọi hoặc nhìn thấy nó ở một ngữ cảnh Java khác.

- `Parent.class.getDeclaredMethod("protectedMethod")` có thể lấy method protected nếu tên/tham số đúng.
- `Child.class.getDeclaredMethod("protectedMethod")` vẫn không thấy method cha nếu Child không khai báo lại.
- Khi cần tự đi trong class hierarchy, bắt đầu từ `Child.class` và lần lượt dùng `getDeclaredMethod`, `getSuperclass`; phải xác định rõ phạm vi muốn tìm.
- **Private methods không được override theo nghĩa Java.** Một method cùng tên/chữ ký ở subclass có thể là khai báo riêng; đừng ghép chúng thành một chuỗi override rồi suy ra metadata được kế thừa.

Việc lấy `Method` qua reflection và **đọc annotation** khác với việc gọi method bằng `invoke` hoặc thay đổi accessibility. Với module có encapsulation, truy cập/invoke thành viên không public có thể bị kiểm soát bởi Java access checks và JPMS. Không mặc định rằng tìm được method nghĩa là có thể gọi nó.

### 7.2. Interface method và default method

`getMethods()` và `getMethod(...)` có thể trả public methods từ interfaces, kể cả default methods. Nếu class không override, đối tượng `Method` được chọn có thể thuộc về interface gốc, vì vậy có annotation của interface method.

Nhưng nếu class **implement** một abstract interface method bằng method riêng, hoặc **override** default method, annotation trên interface method **không tự có** trên method của class triển khai.

Ví dụ:

~~~java
interface Api {
    @Action("declared-on-interface")
    void submit();
}

class ApiImpl implements Api {
    @Override public void submit() {}
}
~~~

Đây là **đoạn minh họa**, yêu cầu annotation type `Action` tồn tại. `ApiImpl.class.getMethod("submit").getAnnotation(Action.class)` trả `null` nếu implementation không annotate lại; `Api.class.getMethod("submit")` có `@Action`. Muốn framework chấp nhận annotation từ interface như cấu hình mặc định, nó phải tự tra cứu interface hierarchy.

### 7.3. Annotation lặp cũng không thay đổi quy tắc method inheritance

Khi `@Action` hoặc annotation khác là **repeatable**, dùng `method.getAnnotationsByType(Action.class)` để lấy nhiều annotation có thể được lưu trong một container tại **cùng một method**.

Nhưng `getAnnotationsByType` không tự tìm superclass method đã bị override. Nó giải quyết việc **mở container**, không giải quyết việc **duyệt override hierarchy**. Để kết hợp cả hai, ứng dụng phải xác định cách tìm method cha/interface rồi gọi `getAnnotationsByType` riêng trên mỗi `Method`, sau đó quyết định ưu tiên, ghi đè hay cộng dồn.

### 7.4. Bridge/synthetic methods và generic override

Khi generic method hoặc covariant return types tham gia override, Java compiler có thể tạo **bridge methods** để duy trì binary compatibility. Reflection có thể thấy các method này qua `getDeclaredMethods()` và xác định chúng bằng `Method.isBridge()`/`Method.isSynthetic()`.

Một framework quét annotation không nên mặc định “một method ở source chỉ có một đối tượng `Method` trong bytecode”. Khi nhiều method cùng tên và parameter types xuất hiện do bridge/return types, phải chọn đúng method nghiệp vụ bằng tiêu chí rõ ràng. Không suy từ bridge metadata rằng annotation đã được thừa kế theo quy tắc `@Inherited`; cách compiler xử lý annotation trên method tổng hợp không thay thế một chính sách tra cứu hierarchy.

### 7.5. Method.getDeclaringClass() là bước chẩn đoán có giá trị

Nếu thấy `Child.class.getMethod("work").isAnnotationPresent(A.class)` trả true dù `Child` không chứa khai báo `work` trong source, in thêm:

~~~java
System.out.println(method.getDeclaringClass().getName());
~~~

Nếu kết quả là superclass hoặc interface, lời giải thích thường là **Method của chính lớp/interface đó đã được tìm thấy**. Nếu kết quả là `Child`, cần kiểm tra annotation trên method khai báo trực tiếp tại Child, bridge methods, và framework riêng có thể sử dụng metadata của class cha trong một tầng khác.

## 8. Nếu framework muốn tìm annotation từ overridden method thì làm thế nào?

Đây là **quyết định API do bạn thiết kế**, không phải hành vi ngầm định của `Method.getAnnotation`. Hãy xác định câu hỏi trước:

1. **Chỉ chấp nhận annotation trên method triển khai hiện tại?** Dùng `type.getMethod(name, parameterTypes)` (đối với public method) rồi đọc `getDeclaredAnnotation` hoặc `getAnnotationsByType` trên `Method` được trả. Nếu override không annotate, coi là không có.
2. **Cho phép method ở superclass cung cấp annotation mặc định?** Sau khi xác định method hiện tại, chủ động duyệt superclass bằng `getDeclaredMethod(name, parameterTypes)`. Nếu gặp annotation trực tiếp ở lớp cha, áp chính sách ưu tiên rõ ràng, ví dụ “annotation của method gần subclass nhất thắng”.
3. **Cho phép metadata khai báo ở interface?** Phải duyệt các superinterfaces trực tiếp/gián tiếp, không chỉ `getSuperclass()`. Xác định quy tắc xung đột nếu hai interfaces khai báo cùng method với metadata khác nhau.
4. **Có annotation lặp?** Cần quyết định là hợp nhất tất cả, chọn gần nhất, hay annotation ở subclass che annotation ở cha. Không tự gộp mù quáng.
5. **Có overload, generic bridge hoặc covariant return?** Phải resolve method tương ứng theo signature phù hợp; khi thực hiện policy scan cần cân nhắc `isBridge()`/`isSynthetic()` và matching tham số sau type erasure.
6. **Có method private/static hoặc method chỉ có cùng tên?** Đừng nhận chúng là quan hệ override khi ngôn ngữ không xem đó là override. Nếu metadata trên các method đó vẫn cần xét, đặt rõ một chính sách khác, ví dụ “scan mọi declaration cùng tên”.

Một chiến lược đơn giản cho framework chỉ dùng methods công khai:

~~~text
Bắt đầu từ class đích
    ↓
Xác định Method public thực sự được chọn: getMethod(name, parameters)
    ↓
Kiểm tra annotation được khai báo trên chính Method
    ↓
Nếu không có và policy cho phép fallback:
    duyệt các superclass declarations và superinterface declarations
    ↓
Chỉ đọc annotation từ Method tìm được, có xử lý override/signature
    ↓
Áp quy tắc ưu tiên, conflict và repeatable đã công bố
~~~

Đây là **pseudocode quy trình**, không phải source Java có thể biên dịch. Java không cung cấp một cờ `inheritMethodAnnotations=true` cho các reflection methods; framework cấp cao có thể triển khai convention của riêng mình, nên luôn đọc hợp đồng của thư viện thay vì suy diễn trực tiếp từ Java reflection.

Nếu triển khai thủ công, cần làm rõ **thứ tự duyệt**: class hiện tại, superclass gần nhất, interfaces gần nhất, interfaces kế thừa, và cách xử lý diamond interfaces. Thứ tự này phải ổn định và có test, nhất là với security annotations hoặc các quy tắc có thể thay đổi hành vi ứng dụng.

## 9. Những lỗi phổ biến và cách tránh

**Lỗi 1 — Nghĩ getMethod thấy annotation là annotation đã được lớp con kế thừa.** Hãy in `method.getDeclaringClass()`. Nếu nó là class cha, bạn đang đọc metadata của method cha được tìm thấy, chưa có method override ở con.

**Lỗi 2 — Cho rằng @Inherited làm method override giữ annotation.** `@Inherited` chỉ có tác dụng với việc truy vấn **class declaration** qua superclass. Trên method annotations, nó không mở inheritance.

**Lỗi 3 — Dùng getDeclaredMethod để tìm inherited methods.** API này chỉ đọc khai báo trực tiếp; dùng `getMethod` cho public inherited members hoặc tự duyệt hierarchy nếu cần protected/package-private method.

**Lỗi 4 — Dùng getMethods rồi cho rằng mọi kết quả là method của class đang xét.** Method trong kết quả có thể được khai báo trên superclass hoặc interface; kiểm tra `getDeclaringClass()` trước khi gắn metadata vào class đang duyệt.

**Lỗi 5 — Đọc annotation của class thay cho annotation của method.** `Child.class.getAnnotation(A.class)` và `Child.class.getMethod("work").getAnnotation(A.class)` nói về hai annotated elements khác nhau, với quy tắc inheritance khác nhau.

**Lỗi 6 — Tưởng getAnnotationsByType sẽ tự đi lên method cha.** API này xử lý repeatable annotations cùng một element; muốn hợp nhất method hierarchy phải tự làm.

**Lỗi 7 — Chỉ quét superclass mà quên interface methods.** Annotation ở abstract/default method của interface có thể quan trọng cho framework; nhưng Java reflection không tự chuyển nó sang implementation.

**Lỗi 8 — Quét theo tên, bỏ qua parameter types và overloads.** Hai method cùng tên nhưng khác tham số không phải cùng declaration; phải dùng parameter types chính xác, cân nhắc bridge methods khi generic override.

**Lỗi 9 — Gọi reflection và nghĩ annotation tự kích hoạt hành vi.** Annotation chỉ là metadata. Đối với logging, transaction hay authorization, phải có consumer xử lý metadata và kiểm thử đường đi thực thi cụ thể.

## 10. Bài tập tự kiểm tra

Cho ba class:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audit {}

class A {
    @Audit public void save() {}
}

class B extends A {}

class C extends A {
    @Override public void save() {}
}
~~~

*Đây là đoạn ví dụ ngắn; cần import `java.lang.annotation.*` khi biên dịch riêng.*

**Câu 1.** `B.class.getMethod("save").getDeclaringClass()` là gì? **`A.class`**, vì B không override.

**Câu 2.** `B.class.getMethod("save").isAnnotationPresent(Audit.class)` trả gì? **`true`**, vì đang truy vấn chính Method `A.save()`.

**Câu 3.** `B.class.getDeclaredMethod("save")` có thành công không? **Không**, ném `NoSuchMethodException` vì B không khai báo method đó.

**Câu 4.** `C.class.getMethod("save").isAnnotationPresent(Audit.class)` trả gì? **`false`**, vì Method được trả đại diện cho `C.save()`, không annotate.

**Câu 5.** Nếu thêm `@Inherited` vào khai báo `Audit`, đáp án câu 4 có thay đổi không? **Không**; meta-annotation đó không kế thừa method annotations.

**Câu 6.** Nếu muốn C cũng có `@Audit` qua reflection chuẩn, cách đơn giản nhất là gì? **Gắn `@Audit` trực tiếp lên `C.save()`**. Nếu muốn quy tắc “lấy annotation cha khi method con không annotate”, phải viết hoặc dùng một consumer có chính sách tra cứu bổ sung.

**Câu 7.** Nếu muốn tìm `@Audit` trên `A.save()` khi chỉ bắt đầu từ `C.class`, nhưng vẫn giữ method override không annotate, làm sao? **Lấy `A.class.getDeclaredMethod("save")` sau khi đi lên superclass**, rồi đọc annotation trên Method của A; việc ghép kết quả với C là một quyết định riêng.

## 11. Tài liệu chính thức

- Java SE 21 — **Class.getMethod/getMethods/getDeclaredMethod/getDeclaredMethods**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — **Method.getDeclaringClass, getAnnotation, isBridge**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 — **java.lang.annotation.Inherited**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html
- Java SE 21 — **AnnotatedElement** (repeatable và present/declared annotations): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- JLS Java SE 21 — **Method declarations/overriding `8.4.8**, **@Inherited `9.6.4.3**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8 và https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.3

Khi reflection đọc được annotation sau một phép tìm trên class con, hãy nhìn vào **`Method.getDeclaringClass()`** trước khi nói về “kế thừa annotation”. Nếu method ấy thực sự được khai báo trong superclass hoặc interface, annotation vẫn thuộc method ở nơi khai báo. Nếu subclass override method, Java reflection không tự kế thừa method annotation; mọi quy tắc truy tìm metadata từ cha hoặc interface là trách nhiệm rõ ràng của framework/ứng dụng.