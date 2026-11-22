# Constructor mặc định khác constructor không tham số được khai báo tường minh

## 1. Hai khái niệm dễ nhầm

Trong Java, **default constructor** (constructor mặc định theo Java Language Specification, JLS `8.8.9) là constructor được **trình biên dịch khai báo ngầm định** khi một class không khai báo **bất kỳ constructor nào**. Đối với class top-level hoặc class lồng `static` thông thường, nó không nhận tham số và gọi constructor không tham số của superclass bằng `super()`. Trường hợp inner member class không `private` có thêm tham số ngầm định cho enclosing instance, sẽ xét riêng.

**Constructor không tham số được khai báo tường minh** (explicit no-argument constructor) là constructor do người lập trình **thực sự viết trong source** với danh sách tham số rỗng, ví dụ `User() {}`. Nó cũng có thể được gọi bằng `new User()`, nhưng **không phải default constructor do compiler tự sinh**. Khi đã có một khai báo constructor bất kỳ, Java không tự sinh default constructor cho class đó nữa.

Ví dụ tối giản:

~~~java
// Trích đoạn minh họa: ba class top-level trong cùng package.
class Auto {
    // Không khai báo constructor: compiler tạo default Auto().
}

class Written {
    Written() {
        // Constructor không tham số được viết tường minh.
    }
}

class ParamsOnly {
    ParamsOnly(int value) {
        // Đã khai báo một constructor => không có default ParamsOnly().
    }
}
~~~

Do đó:

- `new Auto()` hợp lệ nhờ default constructor ngầm định.
- `new Written()` hợp lệ nhờ constructor không tham số được khai báo tường minh.
- `new ParamsOnly()` **không hợp lệ khi biên dịch**; chỉ `new ParamsOnly(5)` hợp lệ trong phạm vi ví dụ.
- Constructor không được kế thừa từ superclass. `Child` không tự “có” constructor của `Parent`.

**Phân biệt thêm hai nghĩa của “default”:** Trong cụm “default constructor”, từ “default” là thuật ngữ JLS dành cho việc compiler tạo constructor. Trong cụm “default access” hoặc “package-private”, “default” nói về **mức truy cập không ghi modifier**. Một constructor `Written() {}` ở class package-private có *package access*, nhưng vẫn là constructor **tường minh** chứ không phải constructor mặc định do compiler sinh.

## 2. Điều kiện hình thành và tính chất của default constructor

Quy tắc cho class thông thường (không xét đặc thù enum/record/anonymous class):

1. Nếu **không có constructor declaration** nào trong phần thân class, compiler ngầm khai báo một default constructor.
2. Nếu class có **dù chỉ một** constructor được khai báo (`A()`, `A(int)`, `A(String)`, private constructor…), compiler **không** tạo default constructor.
3. Default constructor không có mệnh đề `throws`. Đối với class thông thường không phải `Object`, thân constructor tương đương lời gọi `super()` tới superclass không tham số.
4. Quyền truy cập của default constructor được suy từ modifier truy cập của class: ví dụ class `public` thì constructor mặc định `public`; class package-private thì constructor mặc định package-private. Member class có thể là `protected` hoặc `private` và quy tắc tương ứng được áp dụng. Không suy rằng tất cả default constructors đều `public`.
5. Với **non-private inner member class**, default constructor có thêm tham số ngầm định đại diện cho enclosing instance. Vì thế ở mức Reflection/bytecode, không thể mặc định rằng mọi constructor ngầm sinh đều có `getParameterCount() == 0`.

Bảng đối chiếu:

| Thuộc tính | Default constructor ngầm định | Constructor không tham số tường minh |
| --- | --- | --- |
| Ai tạo khai báo? | Compiler, khi class không có constructor declaration. | Lập trình viên viết `ClassName()`. |
| Có trong source? | Không có constructor declaration. | Có declaration trong source. |
| Có thể tùy chọn modifier truy cập? | Suy từ mức truy cập của class theo JLS. | `public`/`protected`/package-private/`private` theo khai báo hợp lệ. |
| Có thể viết thân tùy ý? | Không; hành vi ngầm định gọi `super()` (cùng cơ chế khởi tạo instance). | Có thể viết logic, kiểm tra đầu vào, `this(...)` hoặc `super(...)`. |
| Có thể khai báo `throws`? | Không. | Có. |
| Có thể gắn annotation constructor trong source? | Không có vị trí khai báo constructor để gắn trực tiếp. | Có thể dùng annotation có `@Target(CONSTRUCTOR)`. |
| Có thể dùng `new X()`? | Thường có nếu constructor truy cập được và class khởi tạo được. | Có nếu constructor truy cập được và phần thân hoàn thành bình thường. |
| `getDeclaredConstructor()` tìm thấy? | Có, với class thông thường có đúng zero-arg ở cấp Reflection. | Có, nếu thật sự không có tham số ở cấp Reflection. |
| `isSynthetic()` phân biệt được? | Không: mặc định không nên coi nó là dấu nhận dạng “do compiler sinh”. | Không: cùng có thể trả `false`. |

**Điểm chung:** cả hai dẫn đến một phương thức khởi tạo thực tế trong class file mà JVM dùng; chỉ nhìn số tham số rỗng không chứng minh nguồn gốc constructor.

## 3. Compiler còn tự làm gì khi có constructor tường minh?

Đối với constructor tường minh không bắt đầu bằng lời gọi constructor khác (`this(...)` hoặc `super(...)`), compiler cũng chèn lời gọi `super()` ngầm định theo quy tắc constructor invocation. Vì vậy, **có `super()` ngầm trong body không đồng nghĩa là default constructor được sinh**.

~~~java
// Hai constructor minh họa, cú pháp tương đương ở phần gọi superclass.
class A {
    A() {
        // compiler chèn super() trước phần body này
    }
}

class B {
    B() {
        super(); // được viết tường minh
    }
}
~~~

Trong cả hai class, `A()` và `B()` là các constructor **đã được khai báo tường minh**. Không có default constructor khác được bổ sung. Java cho phép chỉ một constructor invocation dẫn đầu phù hợp, và `this(...)`/`super(...)` không thể tùy tiện gọi ở cuối body.

### Field initializer và instance initializer vẫn chạy

Việc constructor mặc định không chứa logic tùy biến trong source **không có nghĩa** đối tượng không được khởi tạo giá trị.

~~~java
class Counter {
    int count = 12; // instance field initializer
    {
        count++;     // instance initializer block
    }
    // Compiler tạo constructor mặc định.
}
~~~

`new Counter().count` bằng `13`. Field initializers và instance initializer blocks thực thi trong quá trình tạo đối tượng theo thứ tự khởi tạo do ngôn ngữ quy định (sau chuỗi khởi tạo superclass, trước phần thân constructor của class). Vì thế không kết luận mọi field có giá trị mặc định `0` chỉ vì không có constructor tường minh.

Constructor tường minh có thể chứa thêm logic khác:

~~~java
class Account {
    private int balance;
    Account() {
        this.balance = 100; // Không thể thêm lệnh tùy ý vào constructor mặc định.
    }
}
~~~

`Account()` vẫn là zero-arg constructor, nhưng vì được viết trực tiếp nên không phải default constructor.

## 4. Ví dụ Java 17+ biên dịch và chạy được

Tạo một file `ConstructorKindsDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;

public class ConstructorKindsDemo {
    public static class Auto {
        int value = 10; // Có field initializer, không khai báo constructor.
    }

    public static class Written {
        int value;
        public Written() {
            value = 20;
        }
    }

    public static class ParamsOnly {
        int value;
        public ParamsOnly(int value) {
            this.value = value;
        }
    }

    public static class Overloaded {
        public Overloaded() {}
        public Overloaded(String text) {}
    }

    public static class Base {
        protected Base(int value) {}
    }

    public static class Child extends Base {
        public Child() {
            super(99); // Phải gọi constructor hiện có của Base.
        }
    }

    public static class Outer {
        public class Inner {
            // Constructor mặc định cần enclosing instance.
        }
    }

    static void inspect(String label, Class<?> type)
            throws ReflectiveOperationException {
        Constructor<?> constructor = type.getDeclaredConstructor();
        System.out.println(label
                + ": count=" + type.getDeclaredConstructors().length
                + ", public=" + Modifier.isPublic(constructor.getModifiers())
                + ", synthetic=" + constructor.isSynthetic());
    }

    public static void main(String[] args) throws Exception {
        inspect("Auto", Auto.class);
        inspect("Written", Written.class);

        System.out.println("ParamsOnly: count="
                + ParamsOnly.class.getDeclaredConstructors().length
                + ", noArg=" + hasNoArg(ParamsOnly.class));
        System.out.println("Overloaded: count="
                + Overloaded.class.getDeclaredConstructors().length
                + ", noArg=" + hasNoArg(Overloaded.class));

        System.out.println("Auto.value=" + new Auto().value);
        System.out.println("Written.value=" + new Written().value);
        System.out.println("Child created=" + (new Child() != null));

        Constructor<?> innerConstructor =
                Outer.Inner.class.getDeclaredConstructor(Outer.class);
        Object created = innerConstructor.newInstance(new Outer());
        System.out.println("Inner: parameterCount="
                + innerConstructor.getParameterCount()
                + ", enclosingType="
                + innerConstructor.getParameterTypes()[0].getSimpleName()
                + ", created=" + (created instanceof Outer.Inner));
    }

    static boolean hasNoArg(Class<?> type) {
        try {
            type.getDeclaredConstructor();
            return true;
        } catch (NoSuchMethodException e) {
            return false;
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConstructorKindsDemo.java
java ConstructorKindsDemo
~~~

Kết quả với JDK 17/21:

~~~text
Auto: count=1, public=true, synthetic=false
Written: count=1, public=true, synthetic=false
ParamsOnly: count=1, noArg=false
Overloaded: count=2, noArg=true
Auto.value=10
Written.value=20
Child created=true
Inner: parameterCount=1, enclosingType=Outer, created=true
~~~

Giải thích:

- `Auto` không khai báo constructor nên compiler tạo một default constructor `public` do `Auto` là `public static class`. `Written` có đúng một constructor `public Written()` do lập trình viên viết.
- Reflection thấy `count=1` và constructor `public` cho cả hai. `isSynthetic() == false` trong trường hợp này cho thấy **không thể** dùng `isSynthetic` để phát hiện constructor default.
- `ParamsOnly` chỉ có `ParamsOnly(int)`, vì vậy gọi `getDeclaredConstructor()` (không truyền parameter types) không tìm thấy.
- `Overloaded` có constructor zero-arg **tường minh** và một constructor một tham số; compiler không tạo thêm bản khác.
- Field initializer làm `Auto.value == 10` dù không viết body constructor. `Written` gán `20` trong body tường minh.
- `Child` gọi `Base(int)` một cách tường minh nên biên dịch được dù `Base` không có constructor zero-arg.
- `Outer.Inner` là **non-private inner member class**. Ở Reflection, constructor nhận tham số `Outer` là enclosing instance. `Outer.Inner.class.getDeclaredConstructor()` không phải phép tìm kiếm đúng ở ví dụ này.

## 5. Vì sao subclass có thể không biên dịch khi trông như “chẳng cần constructor”?

Xét fragment **cố ý không biên dịch** sau (để hiểu quy tắc, không đưa chung vào file demo):

~~~java
class Parent {
    Parent(int id) {}
}

class Child extends Parent {
    // Không khai báo constructor.
}
~~~

Compiler muốn sinh default constructor `Child()`, mà constructor mặc định đó gọi `super()`. Nhưng `Parent` chỉ có `Parent(int)`; không tồn tại `Parent()` thích hợp, nên `Child` bị lỗi biên dịch. Java **không** tự biến `super()` thành `super(0)`.

Cách sửa là khai báo constructor cho `Child` và chọn đúng constructor superclass:

~~~java
class Parent {
    Parent(int id) {}
}

class Child extends Parent {
    Child() {
        super(42);
    }
}
~~~

Lúc này `Child()` là constructor không tham số **tường minh**, không còn default constructor ngầm định.

### Trường hợp superclass constructor ném checked exception

Default constructor không khai báo `throws`, vì thế nếu constructor zero-arg được chọn ở superclass ném checked exception, class con không tự giải quyết được:

~~~java
// Fragment minh họa lỗi biên dịch do checked exception.
import java.io.IOException;

class Parent {
    Parent() throws IOException {}
}

class Child extends Parent {
    // Default Child() ngầm định không có throws IOException.
}
~~~

Có thể sửa bằng cách viết constructor rõ ràng và khai báo/giải quyết checked exception:

~~~java
// Fragment thay thế hợp lệ khi đặt vào file Java có import IOException.
class Child extends Parent {
    Child() throws IOException {
        super();
    }
}
~~~

Điều này chỉ có thể làm trong constructor **tường minh**, không thể “thêm `throws`” vào default constructor do compiler sinh.

## 6. Tác động của access modifier

Default constructor **kế thừa mức truy cập của class theo quy tắc JLS**, trong khi constructor tường minh có thể dùng modifier khác miễn hợp lệ.

~~~java
public class PublicAuto {
    // Compiler tạo public PublicAuto().
}
~~~

~~~java
public class PublicLocked {
    private PublicLocked() {
        // Ngăn việc khởi tạo trực tiếp từ bên ngoài.
    }
}
~~~

Đây là hai source minh họa **ở hai file riêng** (không để cả hai public top-level classes trong một file). `PublicAuto` có default public constructor; `PublicLocked` có constructor private được viết tường minh và không có default constructor. Kể cả Reflection nhìn thấy `PublicLocked()` qua `getDeclaredConstructors()`, việc gọi `newInstance()` phải tuân quyền truy cập/module.

Một class `abstract` cũng có thể có default constructor nhưng không thể tạo instance trực tiếp bằng `new AbstractClass()`, dù Reflection có thể đọc metadata constructor. “Constructor tồn tại” và “class khởi tạo được” là hai điều khác nhau.

## 7. Quan sát bằng Reflection: điều gì biết được, điều gì không?

Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getDeclaredConstructors()` | Trả tất cả constructor được class khai báo ở cấp Reflection, kể cả private và constructor mặc định do compiler tạo; **không** trả constructor kế thừa vì constructor không được kế thừa. Thứ tự mảng không được bảo đảm. |
| `getConstructors()` | Trả các constructor `public` của class, không phải constructor kế thừa từ cha. |
| `getDeclaredConstructor(Class<?>... types)` | Tìm constructor theo đúng danh sách kiểu tham số ở mức Reflection. Không tham số `getDeclaredConstructor()` tìm zero-arg constructor nếu có. |
| `getConstructor(Class<?>... types)` | Tìm constructor `public` theo danh sách kiểu tham số. |
| `Constructor.getParameterCount()` | Số tham số Reflection quan sát; inner member class có thể có enclosing-instance parameter. |
| `Constructor.isSynthetic()` | Cho biết constructor có đánh dấu synthetic theo metadata JVM hay không; **không** trả lời chắc chắn constructor được viết trong source hay là default. |
| `Constructor.newInstance(args...)` | Gọi constructor và tạo instance khi class/constructor có quyền, tham số hợp lệ và quá trình khởi tạo thành công; có thể ném exception. |

**Không có API Reflection chuẩn dạng `isDefaultConstructor()` hoặc `isDeclaredExplicitlyInSource()`.** Một constructor ngầm định `public Auto()` và một constructor tường minh `public Written() {}` có thể trông giống nhau ở metadata: cùng số tham số, modifier, tên `<init>` trong bytecode và `isSynthetic()==false`. Không nên suy đoán nguồn gốc chỉ từ Reflection.

Biên dịch sang class file vẫn tạo phương thức khởi tạo `<init>`. Dùng `javap -p -c` để xem bytecode (ví dụ với các nested classes trong demo) có thể thấy các lệnh khởi tạo và gọi superclass, nhưng **sự hiện diện của `<init>()V` không chứng minh** constructor được viết hay được compiler sinh. Một số chi tiết như annotation hoặc debug metadata có thể cung cấp gợi ý trong trường hợp cụ thể, không phải dấu nhận dạng tổng quát. Muốn phân biệt một cách đáng tin cậy, cần biết **source declaration** hoặc metadata riêng của công cụ biên dịch/source parser.

Đối với framework, đa số nhu cầu chỉ là “có constructor phù hợp để gọi hay không?” thay vì “nó xuất phát từ source hay compiler?”. Khi chọn constructor, hãy xét accessibility, module, signature, annotation, exception và mục đích nghiệp vụ, thay vì tự đoán nguồn gốc.

## 8. Ngoại lệ quan trọng: inner class, enum, record, anonymous class

Quy tắc default constructor phải được hiểu trong đúng ngữ cảnh loại class.

### Non-static inner member class

Một inner member class không `private` cần enclosing instance. Constructor mà `Outer.Inner.class.getDeclaredConstructor(...)` nhìn thấy có thể nhận tham số `Outer` mặc dù source không viết tham số nào. Vì vậy, công cụ Reflection không nên suy ra “không có default constructor” chỉ do `getDeclaredConstructor()` không tồn tại khi truyền zero parameters. Ví dụ chạy ở trên đã chứng minh constructor có `parameterCount=1`.

### Enum

Enum có quy tắc constructor đặc biệt trong JLS `8.9.2. Constructor khai báo trong enum không thể là `public` hoặc `protected`; các giá trị enum được tạo theo cơ chế do compiler/JVM quản lý. Không áp dụng trực tiếp quy tắc class thường để dùng `Constructor.newInstance()` tạo thêm enum constant: Reflection không cho tạo enum object bằng cách đó. Các tham số nội bộ trong constructor enum cũng không nên được diễn giải như API constructor thông thường.

### Record (Java 16+)

Record có **canonical constructor** gắn với record components. Khi không viết canonical constructor, Java có thể sinh **implicit canonical constructor** theo quy tắc record, **khác khái niệm default constructor của class thông thường**. Ví dụ `record Point(int x, int y) {}` có canonical constructor nhận `int, int`, chứ không tự có `Point()`. Với `record Empty() {}`, canonical constructor tình cờ có zero parameters nhưng bản chất vẫn là **canonical constructor**.

~~~java
// Các record declaration minh họa, có thể đặt trong file Java 17 thích hợp.
record Point(int x, int y) {}
record Empty() {}
~~~

Lời gọi `new Point()` không hợp lệ trừ khi người lập trình có thêm constructor không tham số hợp lệ tự ủy quyền cho canonical constructor.

### Anonymous class

Anonymous class không có cú pháp đặt tên constructor trong source; constructor của nó tuân quy tắc riêng ở JLS `15.9.5.1. Đừng lấy metadata constructor của anonymous class làm ví dụ đơn giản để xác định default constructor của một class đặt tên.

## 9. Sai lầm thường gặp

1. **“Class nào cũng có default constructor.”** Sai: có một constructor tường minh bất kỳ là compiler không sinh default constructor khác.
2. **“Constructor zero-arg là default constructor.”** Sai: zero-arg có thể do lập trình viên khai báo; record zero-component còn có canonical constructor zero-arg.
3. **“Nếu khai báo `A(int)` thì Java vẫn giữ `A()`.”** Sai: muốn cả hai phải viết cả `A()` lẫn `A(int)`.
4. **“Default constructor luôn public.”** Sai: mức truy cập phụ thuộc class (và các quy tắc riêng của loại class).
5. **“Default constructor không chạy khởi tạo field.”** Sai: instance field initializers và instance initializer blocks vẫn chạy.
6. **“Có `super()` ngầm tức constructor là default.”** Sai: constructor viết tường minh không gọi `this(...)`/`super(...)` cũng nhận một lời gọi `super()` ngầm định.
7. **“Con tự dùng constructor có tham số của cha.”** Sai: constructors không được kế thừa, và default constructor ở con chỉ cố gọi `super()`.
8. **“Reflection tự phân biệt constructor do compiler sinh.”** Sai: `isSynthetic` không phải bộ phân loại này, và constructor mặc định vẫn nằm trong `getDeclaredConstructors()`.
9. **“`getDeclaredConstructor()` luôn tìm đúng default constructor.”** Sai với trường hợp non-private inner member class: có tham số enclosing instance ở Reflection.
10. **“Record và enum giống class thường trong mọi trường hợp.”** Sai: loại class này có quy tắc constructor đặc thù.

## 10. Tình huống thực hành và cách kiểm thử

- Bỏ hết constructor declarations khỏi `ParamsOnly` rồi gọi `getDeclaredConstructor()`: quan sát compiler bắt đầu sinh default constructor.
- Thêm một constructor `ParamsOnly(String)` và thử `new ParamsOnly()`: nêu rõ tại sao bị lỗi biên dịch.
- Đổi constructor zero-arg trong `Written` thành `private Written()`: dự đoán thay đổi ở `getConstructors()` và `getDeclaredConstructors()`, sau đó thử gọi từ một class không có quyền.
- Tạo superclass chỉ có constructor `Parent(int)` rồi khai báo subclass không có constructor: giải thích vì sao default `Child()` không biên dịch.
- Tạo superclass zero-arg constructor ném checked exception: giải thích vì sao cần constructor tường minh `throws` ở lớp con.
- So sánh `Auto.class.getDeclaredConstructor().isSynthetic()` và `Written.class.getDeclaredConstructor().isSynthetic()`, tránh kết luận nguồn gốc theo boolean này.
- Với `Outer.Inner`, thử lấy constructor bằng `getDeclaredConstructor(Outer.class)` và gọi `newInstance(new Outer())`.
- Với `record Point(int x, int y) {}`, kiểm tra danh sách constructor Reflection và phân biệt canonical constructor với default constructor.

## 11. Tài liệu tham khảo

- [Java Language Specification 17 — `8.8.9 Default Constructor](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.9): điều kiện sinh, quyền truy cập, lời gọi superclass, `throws` và ngoại lệ inner class.
- [Java Language Specification 17 — `8.8.7 Constructor Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7): cơ chế `this(...)`/`super(...)` và lời gọi ngầm.
- [Java SE 17 — Class#getDeclaredConstructors và getDeclaredConstructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): constructor mặc định xuất hiện trong Reflection, phạm vi declared/public, inner member class parameter.
- [Java Language Specification 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): canonical constructor của record và quy tắc sinh riêng.
- [Java Language Specification 17 — `8.9 Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): constructor enum và giới hạn riêng.

**Ghi nhớ:** “mặc định” mô tả **nguồn gốc do compiler ngầm khai báo khi không có constructor nào**, còn “không tham số” mô tả **hình dạng tham số của một constructor**. Đừng dùng hai khái niệm thay thế nhau khi giải thích mã nguồn, thiết kế subclass hoặc sử dụng Reflection.
