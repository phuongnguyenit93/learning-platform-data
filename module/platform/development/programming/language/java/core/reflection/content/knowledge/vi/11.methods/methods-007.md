# Liên kết động khi `Method` của lớp cha được gọi trên lớp con

Một tình huống rất dễ hiểu sai trong Java Reflection: ta tìm thấy `Method` bằng cách nhìn vào **lớp cha**, nhưng lại truyền **đối tượng lớp con** vào `Method.invoke()`. Nếu lớp con ghi đè phương thức instance đó, **Java vẫn thực thi bản ghi đè của lớp con**.

```java
Method method = Parent.class.getMethod("speak");
Object result = method.invoke(new Child());
```

Giả sử `Child extends Parent` và ghi đè `speak()`, `result` là kết quả của `Child.speak()`. Đối tượng `Method` vẫn phản ánh khai báo được tra cứu từ `Parent`; việc chọn phần triển khai để thực thi diễn ra **lúc gọi**, dựa trên kiểu runtime của receiver. Đây là *dynamic method dispatch* (liên kết động), không phải cơ chế riêng biệt do Reflection phát minh.

Bài học thuộc nhóm **Method** trong Java Core Reflection; trọng tâm là phân biệt ba thông tin: **chữ ký phương thức được tra cứu**, **lớp khai báo trên đối tượng `Method`**, và **bản triển khai thực sự được gọi**.

## 1. Nhắc lại: override và kiểu runtime

Trong Java, một lời gọi đến phương thức instance có thể ghi đè được sẽ được chọn theo **kiểu thực tế của đối tượng**:

```java
class Parent {
    String speak() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String speak() {
        return "Child";
    }
}

Parent object = new Child();
System.out.println(object.speak()); // Child
```

Biến `object` có **kiểu khai báo** là `Parent` nhưng đang tham chiếu đến đối tượng có **kiểu runtime** là `Child`. Compiler kiểm tra rằng lời gọi `speak()` hợp lệ trên `Parent`, còn JVM chọn implementation ghi đè phù hợp với receiver thực tế. Nếu lớp con không override, bản triển khai kế thừa tương ứng sẽ chạy.

Override có quy tắc Java riêng: phương thức của lớp con phải tương thích về tên, chữ ký và return type; không được giảm mức truy cập của phương thức ghi đè; không được ghi đè phương thức `final`, `static` hoặc `private`. Với `static` có **method hiding**, không có override.

Khi chuyển lời gọi sang Reflection, bản chất này vẫn giữ nguyên đối với phương thức instance có thể override.

## 2. `Method` đại diện cho khai báo; `invoke()` nhận receiver runtime

`java.lang.reflect.Method` cung cấp metadata như:

| API | Cho biết điều gì? | Điều cần tránh suy diễn |
| --- | --- | --- |
| `method.getDeclaringClass()` | Lớp/interface chứa khai báo mà `Method` đại diện | Không nhất thiết là lớp có body sẽ được chạy khi receiver là lớp con |
| `method.getName()` | Tên khai báo | Không xác định riêng overload nếu thiếu tham số |
| `method.getParameterTypes()` | Các loại tham số theo chữ ký đã được phản ánh | Không được tự thay bằng loại runtime của từng đối số |
| `method.getReturnType()` | Return type trong khai báo tương ứng | Không phải cơ chế dò lại phương thức theo giá trị trả về runtime |
| `method.getModifiers()` | Các modifier của khai báo | Không xác nhận trước một override nào sẽ được chọn |
| `method.invoke(receiver, args...)` | Yêu cầu gọi phương thức trên receiver và đối số đã truyền | Với instance method ghi đè được, implementation được chọn động |

Đặc biệt:

```java
Method fromParent = Parent.class.getDeclaredMethod("speak");
System.out.println(fromParent.getDeclaringClass() == Parent.class); // true

Parent childAsParent = new Child();
Object result = fromParent.invoke(childAsParent);
// Nếu Child ghi đè speak(), result nhận kết quả của Child.speak()
```

`getDeclaringClass()` **không biến thành `Child.class` sau khi `invoke()`**. Lớp sở hữu khai báo của `Method` và lớp sở hữu phần triển khai được chọn khi gọi là hai góc nhìn khác nhau.

Đối với method instance, receiver truyền vào `invoke` phải là instance của lớp khai báo hoặc một subtype hợp lệ. Vì vậy `Method` lấy từ `Parent` có thể gọi trên `new Child()`; một đối tượng không liên quan sẽ không được chấp nhận.

## 3. Ba giai đoạn cần phân biệt

**Giai đoạn 1 — Lookup.** Ta chọn phương thức để phản ánh theo lớp, tên và danh sách kiểu tham số:

```java
Method method = Parent.class.getDeclaredMethod("speak", String.class);
```

`getDeclaredMethod` chỉ tìm các method **khai báo trực tiếp** trong `Parent` với chữ ký yêu cầu. `getMethod` tìm các phương thức `public` trong phạm vi API hỗ trợ, gồm cả các phương thức inherited. Việc chọn `Parent.class` lúc lookup không có nghĩa ta khóa receiver của mọi lời gọi tương lai vào lớp cha.

**Giai đoạn 2 — Access/arguments.** `Method.invoke` xác định receiver, kiểm tra quyền truy cập theo quy tắc reflection/module và kiểm tra/chuyển đổi đối số. Phương thức có thể được tìm thấy mà lời gọi vẫn thất bại do access checks hoặc receiver không hợp lệ.

**Giai đoạn 3 — Dispatch.** Với instance method có thể override, JVM chọn bản triển khai phù hợp với class runtime của receiver. Nếu `Child` override, `Child` chạy; nếu một `GrandChild extends Child` override tiếp, bản của `GrandChild` có thể chạy.

Quy trình khái quát:

```text
Parent.class.getMethod("speak")
                |
                v
      Method (khai báo Parent)
                |
                v
    invoke(receiver = new Child())
                |
                v
        Kiểu runtime: Child
                |
                v
    Child có override speak()?
           /           \
         Có           Không
          |              |
          v              v
     Child.speak()   Phương thức kế thừa
```

Đó là lý do **không thể suy ra chính xác phần thân sẽ thực thi chỉ từ `getDeclaringClass()`** đối với phương thức ảo được override.

## 4. Ví dụ Java 17+ hoàn chỉnh, chạy độc lập

Lưu chương trình vào `DynamicDispatchDemo.java`:

```java
import java.lang.reflect.Method;

public class DynamicDispatchDemo {
    public static class Parent {
        public String speak(String name) {
            return "Parent:" + name;
        }

        public static String kind() {
            return "Parent-static";
        }

        private String secret() {
            return "Parent-private";
        }

        public final String stable() {
            return "Parent-final";
        }
    }

    public static class Child extends Parent {
        @Override
        public String speak(String name) {
            return "Child:" + name;
        }

        // Overload: khác kiểu tham số, không ghi đè speak(String).
        public String speak(Object name) {
            return "Child-overload:" + name;
        }

        // Hiding static method của Parent.
        public static String kind() {
            return "Child-static";
        }

        // Không override Parent.secret() vì Parent.secret() là private.
        public String secret() {
            return "Child-public";
        }
    }

    public static void main(String[] args) throws Exception {
        Method fromParent =
                Parent.class.getDeclaredMethod("speak", String.class);
        Parent receiver = new Child();

        System.out.println("Method owner: "
                + fromParent.getDeclaringClass().getSimpleName());
        System.out.println("Receiver type: "
                + receiver.getClass().getSimpleName());

        System.out.println("Parent instance: "
                + fromParent.invoke(new Parent(), "Java"));
        System.out.println("Child instance: "
                + fromParent.invoke(receiver, "Java"));

        Method fromChild =
                Child.class.getMethod("speak", String.class);
        System.out.println("Child method owner: "
                + fromChild.getDeclaringClass().getSimpleName());

        System.out.println("Parent static: "
                + Parent.class.getDeclaredMethod("kind").invoke(null));

        Method parentPrivate =
                Parent.class.getDeclaredMethod("secret");
        parentPrivate.setAccessible(true);
        System.out.println("Parent private: "
                + parentPrivate.invoke(receiver));

        System.out.println("Child public secret: "
                + Child.class.getMethod("secret").invoke(receiver));

        System.out.println("Parent final: "
                + Parent.class.getDeclaredMethod("stable").invoke(receiver));

        // Method đã lookup với chữ ký speak(String), không chọn
        // sang overload speak(Object) ở Child.
        System.out.println("Parent chosen overload: "
                + fromParent.invoke(receiver, new Object[] {"Java"}));

        try {
            fromParent.invoke(new Object(), "Java");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Unrelated receiver: IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac DynamicDispatchDemo.java
java DynamicDispatchDemo
```

Đầu ra:

```text
Method owner: Parent
Receiver type: Child
Parent instance: Parent:Java
Child instance: Child:Java
Child method owner: Child
Parent static: Parent-static
Parent private: Parent-private
Child public secret: Child-public
Parent final: Parent-final
Parent chosen overload: Child:Java
Unrelated receiver: IllegalArgumentException
```

**Giải thích theo từng nhóm kết quả:**

1. `Method owner: Parent` vì `fromParent` được tạo từ khai báo `Parent.speak(String)`. Điều này **không đổi** khi receiver là `Child`.
2. `Parent instance: Parent:Java` và `Child instance: Child:Java` sử dụng **cùng một `Method`**. Chỉ receiver khác nhau, nên đối với method override được, phần triển khai được chọn động.
3. `Child method owner: Child` là kết quả của **một lookup khác**, lần này dùng `Child.class.getMethod("speak", String.class)`. API trả về khai báo override của `Child`; không phải từ `Method` cha tự biến đổi.
4. `Parent static: Parent-static` vì `static` được *hide* chứ không override. Method lấy từ `Parent` giữ hành vi static của `Parent`.
5. `Parent private: Parent-private` vì method `private` của `Parent` không được override. `Child.secret()` là một phương thức khác và in ra `Child-public`. Mã ví dụ sử dụng `setAccessible(true)` trong môi trường cùng ứng dụng; việc mở quyền private xuyên named modules có thể bị JPMS chặn.
6. `Parent final: Parent-final` vì `final` không cho phép lớp con override.
7. `Parent chosen overload: Child:Java`: lookup đã chọn chữ ký `speak(String)` và lời gọi dispatch tới override tương ứng; dù `Child` có thêm `speak(Object)`, JVM không tự chuyển sang overload đó.
8. Receiver `new Object()` không phải instance của `Parent` nên `invoke` ném `IllegalArgumentException` trước khi có thể gọi method đích.

Đầu ra trên phản ánh Java 17+ và không phụ thuộc vào thứ tự duyệt mảng reflection, vì tất cả lookup đều nêu tên và chữ ký cụ thể.

## 5. Vì sao `getDeclaringClass()` khác implementation lúc chạy?

Với đoạn:

```java
Method m = Parent.class.getMethod("speak", String.class);
Object value = m.invoke(new Child(), "A");
```

Có hai câu hỏi khác nhau:

- `m.getDeclaringClass() == Parent.class`? **Đúng** trong ví dụ này: đối tượng `m` đại diện khai báo của `Parent`.
- Body nào được thực thi với receiver `Child`? **`Child.speak(String)`**, vì đây là phương thức instance override được và `Child` đã override.

Điều này cũng áp dụng cho lớp con nhiều cấp:

```java
class GrandChild extends Child {
    @Override
    public String speak(String name) {
        return "GrandChild:" + name;
    }
}
```

Đây là đoạn **minh họa bổ sung** để khai báo cùng phạm vi với `Parent` và `Child` trong ví dụ. Khi `fromParent.invoke(new GrandChild(), "Java")`, kết quả dự kiến là `GrandChild:Java`. Method của cha là **điểm vào đã tra cứu**, không phải lời yêu cầu «bắt buộc chạy body của cha».

Đối với thư viện/framework, điểm này quan trọng: một proxy subclass hoặc một subclass do framework tạo ra có thể override một method. Khi gọi method của superclass bằng Reflection, code override trên proxy/subclass vẫn có thể tham gia thực thi.

## 6. Khi nào không có dynamic dispatch kiểu override?

Các phương thức Java không phải lúc nào cũng là lời gọi ảo có thể override. Cần phân biệt:

| Loại method | Child có thể override cùng method? | Khi dùng `Method` lấy từ `Parent` và receiver là `Child` |
| --- | --- | --- |
| Instance `public`/`protected`/package-private có thể override hợp lệ | Có, nếu Java access và quy tắc kế thừa cho phép | Thực thi bản override gần nhất phù hợp ở lớp runtime |
| `static` | Không; có thể **hide** method static | Gọi method static được khai báo ở `Parent`; receiver không quyết định dispatch |
| `private` | Không; phương thức không được kế thừa như method override | Gọi đúng body private của `Parent` nếu reflection access được phép |
| `final` instance | Không | Gọi body từ khai báo của `Parent` vì không có override hợp lệ |
| Constructor | Không thuộc `Method`, không có override | Dùng `Constructor.newInstance`, không có virtual dispatch như instance method |

### `static` là hiding, không phải overriding

```java
class Base {
    static String label() { return "Base"; }
}
class Derived extends Base {
    static String label() { return "Derived"; }
}

// Method lấy từ Base -> vẫn gọi Base.label().
Method m = Base.class.getDeclaredMethod("label");
System.out.println(m.invoke(null)); // Base
```

Đây là **đoạn minh họa cần import `java.lang.reflect.Method`**. Với method `static`, nên truyền `null` vào đối số receiver của `Method.invoke` vì target object không được sử dụng.

### `private` không override

Nếu cả `Parent` và `Child` đều có method tên `secret()`, nhưng method ở `Parent` là `private`, thì hai method **không có quan hệ override**. Reflection lấy `Method` từ `Parent` có thể gọi body private của `Parent` sau khi được phép truy cập. Không suy ra việc «tên giống nhau» tạo liên kết động.

### `final` giới hạn override

Phương thức instance `final` vẫn là instance method, nhưng subclass không thể khai báo override. Vì không có override hợp lệ ở subclass, ví dụ `Parent.finalMethod` trên receiver `Child` vẫn thực thi implementation đó. Tính `final` ở đây ngăn sự thay thế body bởi subclass.

## 7. Override khác overload: Reflection không tự chọn overload tốt nhất

**Overriding**: Lớp con cung cấp implementation thay thế cho một phương thức instance được kế thừa theo quy tắc Java, ví dụ `speak(String)` ở `Parent` và `Child`.

**Overloading**: Nhiều phương thức có cùng tên nhưng khác danh sách tham số, ví dụ `speak(String)` và `speak(Object)`.

`getMethod("speak", String.class)` và `getMethod("speak", Object.class)` có thể trả về **hai đối tượng `Method` khác nhau**, đại diện hai chữ ký. Khi đã chọn `Method` cho `speak(String)`, `invoke(receiver, value)` **không thực hiện thuật toán overload resolution của compiler Java từ đầu** theo giá trị runtime. Nó chỉ kiểm tra/chuyển đối số cho chữ ký đã chọn rồi dispatch override tương ứng nếu có.

Ví dụ khi `Child` khai báo thêm `speak(Object)`, gọi `Parent.speak(String)` bằng reflection trên receiver `Child` vẫn tới `Child.speak(String)` chứ không tới `Child.speak(Object)`.

Nếu viết framework router theo tên method, cần quyết định chữ ký cụ thể: `getParameterTypes()`, số lượng tham số, boxing/unboxing, widening, varargs và policy chọn overload. **Dynamic dispatch không giải quyết thay bạn bài toán chọn overload.**

## 8. Lookup trên lớp cha hoặc lớp con có gì khác?

Các API thường dùng:

| Cách lấy `Method` | Hành vi tìm kiếm | Mức độ phù hợp |
| --- | --- | --- |
| `Parent.class.getDeclaredMethod("m", types...)` | Chỉ method khai báo trực tiếp trong `Parent`, kể cả non-public | Cần chính xác khai báo của cha |
| `Parent.class.getMethod("m", types...)` | Method `public` theo quy tắc tra cứu `getMethod` | Cần contract công khai ở cha |
| `Child.class.getDeclaredMethod("m", types...)` | Chỉ method khai báo trực tiếp trong `Child` | Cần biết subclass có khai báo method với chữ ký đó không |
| `Child.class.getMethod("m", types...)` | Method `public` có thể tìm thấy trên `Child`, gồm inherited | Cần thao tác qua API công khai của Child |

Ví dụ `Child.class.getDeclaredMethod("stable")` sẽ thất bại nếu `stable()` chỉ được `Parent` khai báo, dù `Child` **kế thừa và gọi được** method `stable()`. Trong khi `Child.class.getMethod("stable")` có thể thành công, trả method public được kế thừa có `getDeclaringClass() == Parent.class`.

Với override `Child.speak(String)`, `Child.class.getMethod("speak", String.class)` tìm thấy khai báo của `Child`; trong khi `Parent.class.getMethod("speak", String.class)` cho method của `Parent`. Nhưng cả hai có thể gọi cùng implementation của `Child` khi receiver là đối tượng `Child` và chữ ký tương ứng được override.

**Chọn lookup dựa theo ý định metadata**, không dùng việc lookup trên `Parent` làm «mẹo» để né override.

## 9. Điều kiện nhận receiver và những exception quan trọng

`Method.invoke(Object receiver, Object... arguments)` phân biệt method instance và static:

- **Instance method:** receiver phải khác `null` và phải tương thích với class/interface khai báo method. `new Child()` hợp lệ khi `Child extends Parent`; `new Object()` không hợp lệ với method khai báo trong `Parent`.
- **Static method:** receiver bị bỏ qua; truyền `null` giúp mã rõ ràng.
- **Tham số:** số lượng và kiểu đối số phải tương thích với chữ ký được `Method` đại diện. Reflection có thể áp dụng unboxing và widening primitive thích hợp, nhưng không tự chọn overload khác.
- **Quyền truy cập:** trước khi gọi, reflection vẫn tuân thủ Java access checks và giới hạn module nếu chưa suppress được checks. Method tồn tại chưa đồng nghĩa caller được phép invoke.

| Exception | Ngữ cảnh điển hình | Ý nghĩa |
| --- | --- | --- |
| `NoSuchMethodException` | `getDeclaredMethod`/`getMethod` | Tên hoặc danh sách kiểu tham số không khớp phạm vi tìm kiếm |
| `IllegalAccessException` | `Method.invoke` | Không được truy cập method theo access checks hiện tại |
| `IllegalArgumentException` | `Method.invoke` | Receiver không phù hợp, sai số/kiểu đối số |
| `NullPointerException` | `Method.invoke` trên instance method với receiver `null` | Không có đối tượng để gọi instance method |
| `InvocationTargetException` | `Method.invoke` khi method đích ném exception | Phần thân method đã ném lỗi; xem `getCause()` |
| `InaccessibleObjectException` | `setAccessible(true)` | Không thể suppress access checks, thường do package của named module chưa được mở |

Quan trọng: `InvocationTargetException` không có nghĩa thuật toán dispatch thất bại. Nó thường nói rằng **method đích đã được chọn và chạy**, sau đó tự ném exception.

`Method.invoke` không thể được dùng như một cơ chế đặc biệt để «đi xuyên» module encapsulation. Ví dụ `setAccessible(true)` có thể bị JPMS từ chối dù một `Method` đã được tìm thấy qua `getDeclaredMethod`.

## 10. Interface method, abstract method và default method

Virtual dispatch không giới hạn ở class cha cụ thể. Giả sử một interface khai báo `String name()`, các implementation khác nhau thực thi theo receiver:

```java
interface Named {
    String name();
}

class First implements Named {
    public String name() { return "First"; }
}

class Second implements Named {
    public String name() { return "Second"; }
}

Method method = Named.class.getMethod("name");
System.out.println(method.invoke(new First()));  // First
System.out.println(method.invoke(new Second())); // Second
```

Đây là **đoạn minh họa cần import `java.lang.reflect.Method`**. Trong hai lời gọi, `Method.getDeclaringClass()` vẫn là `Named.class`, còn implementation được chọn theo class của receiver.

Tương tự, `Method` có thể đại diện một phương thức `abstract` của abstract superclass hoặc interface và được invoke trên instance của subclass concrete triển khai nó. Nếu interface có **default method**, lớp triển khai có thể kế thừa default implementation hoặc override nó; `Method.invoke` vẫn tuân theo cơ chế dispatch thích hợp.

Không nên lẫn chuyện này với lời gọi `super.m()` được ràng buộc đặc biệt ở mã Java. Một `Method` phản ánh method của superclass và dùng `invoke(child)` **không tương đương** lệnh `super.m()` của lớp con. Để chủ động gọi một implementation bị override ở superclass phải xem các cơ chế method handles/special invocation và quyền truy cập liên quan; `Method.invoke` thông thường không có tham số «bỏ qua override».

## 11. Bridge method, generic và proxy: tình huống thực tế

Với generic, compiler đôi khi sinh **bridge method** để duy trì tính đa hình sau type erasure. Ví dụ về ý tưởng:

```java
class Box<T> {
    T normalize(T value) { return value; }
}

class TextBox extends Box<String> {
    @Override
    String normalize(String value) {
        return value.trim();
    }
}
```

Vì type erasure, chữ ký erased trên `Box<T>` sử dụng `Object`. Compiler có thể sinh bridge ở `TextBox` để chuyển lời gọi `normalize(Object)` tới implementation `normalize(String)` và bảo toàn override. Một framework phản chiếu các method từ `getDeclaredMethods()` của `TextBox` có thể thấy cả method source và method bridge/synthetic; kiểm tra `method.isBridge()` và `method.isSynthetic()` trước khi quyết định chọn method nào.

Với **proxy subclass** do ORM, mocking framework hoặc AOP tạo ra, lớp runtime có thể override public/protected method để thêm interceptors. Khi gọi `Method` lấy từ superclass với receiver là proxy subclass, dispatch vẫn có thể tới override trên proxy. Đó là hành vi JVM phù hợp với dynamic dispatch, không phải `Method.invoke` luôn ưu tiên body của class được lookup.

Tuy nhiên, proxy dùng **interface-based delegation** khác với subclass proxy; không thể suy ra mọi loại proxy đều là subclass của target class. Xác định hierarchy/runtime class thật trước khi kết luận.

## 12. Các hiểu nhầm thường gặp

**Hiểu nhầm 1 — «Lấy `Method` từ `Parent.class` thì luôn chạy code của `Parent`».** Sai với overridable instance method. `invoke(new Child())` vẫn gọi override của `Child` nếu có.

**Hiểu nhầm 2 — «`getDeclaringClass()` cho biết implementation đã chạy».** Không nhất thiết. Nó chỉ báo lớp/interface chứa khai báo mà đối tượng `Method` đang phản ánh. Với receiver polymorphic, phải xem runtime class và quan hệ override.

**Hiểu nhầm 3 — «Cứ trùng tên là override».** Sai. `static` tạo hiding, `private` không được override, chữ ký tham số khác là overload; method `final` không được override.

**Hiểu nhầm 4 — «Reflection sẽ chọn overload tốt nhất theo class runtime của đối số».** Sai. Chữ ký được chốt ở bước `getMethod(name, parameterTypes)` hoặc `getDeclaredMethod(...)`. `invoke` thực hiện chuyển đổi đối số cho method đã chọn và dispatch override nếu cần.

**Hiểu nhầm 5 — «`setAccessible(true)` sẽ ép chạy method của cha».** Sai. `setAccessible` chỉ yêu cầu suppress Java language access checks khi được phép; nó không tắt virtual dispatch và không thay thế lời gọi bằng `super.m()`.

**Hiểu nhầm 6 — «Method lấy từ superclass luôn gọi được với bất kỳ Object nào».** Sai. Receiver của instance method phải thuộc lớp khai báo hoặc subtype thích hợp, nếu không `invoke` ném `IllegalArgumentException`.

**Hiểu nhầm 7 — «Override thực thi sai là do Reflection».** Cần xem code override, proxy/interceptor, exception do target ném và quan hệ inheritance. Reflection tuân theo cơ chế dispatch Java bình thường đối với overridable instance methods.

## 13. Checklist khi xây dựng framework sử dụng `Method`

Khi một thư viện lưu `Method` của interface/superclass và gọi trên đối tượng runtime:

1. **Chốt contract:** chọn đúng method và chữ ký trong `getMethod`/`getDeclaredMethod`; đừng tự giả định overload.
2. **Kiểm tra receiver:** nhận `receiver.getClass()` để biết runtime type, đồng thời kiểm tra receiver tương thích với lớp khai báo. Receiver `null` chỉ phù hợp với static method.
3. **Kiểm tra modifier:** `Modifier.isStatic(method.getModifiers())`, `Modifier.isPrivate(...)` hoặc `Modifier.isFinal(...)` để biết có khả năng override không.
4. **Dự kiến dynamic dispatch:** với overridable instance method, override của receiver, subclass/proxy có thể chạy ngay cả khi `Method` đến từ superclass/interface.
5. **Xử lý access/module:** không coi metadata lookup là quyền gọi; chỉ `setAccessible`/`trySetAccessible` khi có nhu cầu và hiểu JPMS.
6. **Xử lý lỗi đúng tầng:** phân biệt lỗi lookup, receiver/argument, access, và exception do method đích ném (`InvocationTargetException.getCause()`).
7. **Xử lý compiler-generated methods:** nếu đang xây dựng bộ quét method và gặp generics/bridge methods, dùng `isBridge()`, `isSynthetic()` và luật chọn method có chủ đích.

### Tự kiểm tra

**Câu 1.** `Parent.class.getMethod("speak", String.class)` trả về method có `getDeclaringClass() == Parent.class`. Với `new Child()` ghi đè `speak(String)`, implementation nào chạy?  
**Đáp án:** `Child.speak(String)`, vì dynamic dispatch dựa trên receiver runtime.

**Câu 2.** Nếu `Parent.speak(String)` là `static`, `Child` khai báo method `static` cùng chữ ký, `Method` lấy từ `Parent` gọi method nào?  
**Đáp án:** `Parent.speak(String)`; static hiding không phải overriding.

**Câu 3.** Tại sao `Child.class.getDeclaredMethod("stable")` có thể ném `NoSuchMethodException` dù `Child` gọi được `stable()`?  
**Đáp án:** Vì `getDeclaredMethod` chỉ tìm khai báo trực tiếp; method `stable()` được khai báo ở `Parent` và kế thừa.

**Câu 4.** Có thể dùng `fromParent.setAccessible(true)` để ép `fromParent.invoke(new Child())` chạy body `Parent.speak(String)` không?  
**Đáp án:** Không. Accessibility và virtual dispatch là hai cơ chế khác nhau.

## Kết luận

Trong Java Reflection, **lớp dùng để tra cứu `Method` quyết định khai báo được chọn**, còn **receiver thực tế quyết định bản triển khai của overridable instance method tại thời điểm gọi**. Bởi vậy:

```text
Method lấy từ Parent
       +
receiver runtime Child
       +
Child override hợp lệ
       =
chạy Child implementation
```

Chỉ khi hiểu rõ ranh giới giữa **lookup → access/argument check → dynamic dispatch**, ta mới diễn giải đúng `Method.invoke()`, đặc biệt trong inheritance, interface, generic bridge và subclass proxy.
