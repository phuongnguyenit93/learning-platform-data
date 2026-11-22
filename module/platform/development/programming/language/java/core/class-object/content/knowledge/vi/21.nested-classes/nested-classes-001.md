# Phân loại lớp lồng: static, inner, cục bộ và vô danh trong Java

Trong Java, **lớp lồng nhau** (*nested class*) là một lớp được khai báo trong phạm vi của một lớp hoặc một ngữ cảnh cho phép khai báo lớp. Thay vì chỉ viết các lớp độc lập cấp cao nhất (*top-level classes*), Java cho phép tổ chức lớp phụ trợ sát nơi nó được dùng. Việc chọn **static nested class**, **non-static member inner class**, **local class** hay **anonymous class** ảnh hưởng trực tiếp đến khả năng truy cập đối tượng bao ngoài, cách tạo instance, phạm vi tên, khả năng sử dụng biến cục bộ, mức độ đóng gói và vòng đời của đối tượng.

Ví dụ về hai loại member nested class:

```java
class Outer {
    private static int shared = 10;
    private int value = 20;

    static class Nested {
        int readShared() {
            return shared;
        }
    }

    class Inner {
        int readBoth() {
            return shared + value;
        }
    }
}
```

Cách tạo đối tượng:

```java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

`Nested` là **static member nested class**: không cần một `Outer` instance để tạo. `Inner` là **non-static member inner class**: mỗi instance của nó gắn với một **enclosing instance** của `Outer` khi khởi tạo bình thường.

Ở một method, có thể khai báo một lớp có tên chỉ dùng trong phạm vi method (**local class**), hoặc tạo một subclass/implementation không cần đặt tên lớp trong source (**anonymous class**):

```java
void run() {
    int limit = 3;

    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println(limit);
        }
    }

    Runnable first = new LocalTask();

    Runnable second = new Runnable() {
        @Override
        public void run() {
            System.out.println(limit + 1);
        }
    };

    first.run();
    second.run();
}
```

Đoạn trên là phần thân method minh họa, không phải chương trình độc lập. Cả hai lớp có thể sử dụng biến `limit` bởi biến này **final hoặc effectively final**.

Bài học dành cho **Java 17+**, trình bày đầy đủ bốn loại, cách đặt tên và khởi tạo, cơ chế `this`/`Outer.this`, access modifiers, biến được capture, khác biệt anonymous class và lambda, lựa chọn thiết kế, lỗi compile/runtime thường gặp, nhiều tệp Java runnable kèm `javac`/`java` và kết quả, bài tập cùng checklist.

## 1. Bức tranh tổng quan: một lớp có thể nằm ở đâu?

Ở mức khái niệm, có ba vị trí cần phân biệt:

1. **Member class:** khai báo trực tiếp trong body của một class khác, giống vị trí khai báo field/method. Member class có thể là `static` hoặc không `static`.
2. **Local class:** khai báo trong block của một ngữ cảnh thực thi, chẳng hạn body method/constructor hoặc block thích hợp. Nó có tên trong một phạm vi cục bộ, không phải member của lớp bao ngoài.
3. **Anonymous class:** biểu thức tạo một instance của class không có tên khai báo trong mã nguồn, đồng thời khai báo implementation/subclass ngay tại biểu thức.

**Nested class** là thuật ngữ rộng. Trong cách phân loại Java, **inner class** có nghĩa kỹ thuật: một lớp lồng **không được khai báo static theo ngữ cảnh thích hợp**, gồm non-static member inner classes, local classes không static và anonymous classes. Trong nhiều tài liệu nhập môn, “inner” đôi khi được dùng lỏng cho mọi nested class; khi đọc tài liệu chuyên sâu nên dùng đúng phân loại.

### Bảng nhận diện nhanh

| Tiêu chí | Static nested member | Non-static member inner | Local class | Anonymous class |
| --- | --- | --- | --- | --- |
| Có tên trong mã nguồn? | Có | Có | Có, nhưng chỉ trong scope | Không có tên lớp tự khai báo |
| Khai báo ở đâu? | Member của enclosing type | Member của enclosing class | Trong block/ngữ cảnh cục bộ | Ngay tại biểu thức `new` |
| Cần enclosing `Outer` instance để tạo? | Không | Có (trong tạo instance thông thường) | Phụ thuộc static hay instance context | Phụ thuộc context và superclass/target |
| Truy cập member `static` của Outer? | Có, theo access | Có | Có, theo access/scope | Có, theo access/scope |
| Trực tiếp dùng instance field `Outer.this.field`? | Không có enclosing Outer instance chỉ vì nesting | Có nếu đúng enclosing relationship | Có nếu khai báo trong instance context tương ứng | Có nếu có enclosing instance phù hợp |
| Capture local variables? | Không do member declaration | Không do member declaration | Có; phải final/effectively final | Có; phải final/effectively final |
| Khởi tạo điển hình | `new Outer.Nested()` | `outer.new Inner()` | `new Local()` trong scope | `new Interface() { ... }` |
| Có thể sử dụng lại tên lớp nhiều lần trong source? | Có | Có | Có trong scope | Không thể gọi constructor bằng tên anonymous class |
| Dùng tốt khi | Helper không cần outer state | Behavior gắn với một owner instance | Implementation tạm trong một scope | Override/implementation gọn, một lần |

**Lưu ý:** local/anonymous classes có thể truy cập enclosing instances khi được tạo trong một instance context thích hợp, nhưng không phải mọi local/anonymous class đều có enclosing instance của một `Outer`. Hãy xác định **context thật sự**, không chỉ nhìn xem code có nằm trong file Outer.java hay không.

## 2. Khác biệt quan trọng nhất: có hoặc không có enclosing instance

Một **non-static member inner class** gắn với một instance của enclosing class:

```text
Outer object (value = 20)
       ▲
       │ enclosing instance
Inner object
```

Đối tượng `Inner` có thể sử dụng `Outer.this.value` khi ở trong scope hợp lệ.

Với static nested class:

```text
Outer.Nested object
       │
       └─ không yêu cầu Outer object đi kèm
```

Nó vẫn có thể truy cập **private static members** của enclosing class theo access rules, hoặc truy cập instance members nếu được **cấp một Outer reference tường minh**.

### “Nằm trong Outer.java” không đủ để chứng minh có Outer instance

Một static nested class vẫn được khai báo bên trong body Outer, nhưng runtime object của nó **không cần** gắn với một Outer object. Đó là lý do `new Outer.Nested()` hợp lệ mà không có `new Outer()`.

Ngược lại, `new Outer.Inner()` ở nơi không có enclosing instance phù hợp là cú pháp/khởi tạo sai. Cách rõ ràng là:

```java
Outer owner = new Outer();
Outer.Inner part = owner.new Inner();
```

## 3. Static nested member class: khái niệm và cơ chế

**Static nested member class** là một *member type* được tổ chức trong lớp khác và có modifier `static`; nó không cần enclosing **object** của lớp ngoài:

~~~java
class Library {
    private static final String PREFIX = "LIB";
    static class Code {
        String label(int id) { return PREFIX + "-" + id; }
    }
}
~~~

`new Library.Code().label(7)` trả `"LIB-7"`. Đối tượng Code vẫn có instance members của riêng mình; modifier `static` của **type** không khiến mọi field của nó trở thành static. Nếu Code cần đọc instance state của Library, nó phải nhận `Library` reference **tường minh**. Bài **Static nested class không cần đối tượng bao ngoài** là nơi dạy đầy đủ về Builder, access, type parameters, reflection và class initialization.

## 4. Ví dụ runnable: static nested class

Lưu thành **`StaticNestedDemo.java`**:

```java
public class StaticNestedDemo {
    private static final String PREFIX = "ITEM";
    private final String ownerName;

    public StaticNestedDemo(String ownerName) {
        this.ownerName = ownerName;
    }

    public static class Code {
        private final int number;

        public Code(int number) {
            this.number = number;
        }

        public String label() {
            return PREFIX + "-" + number;
        }
    }

    public static void main(String[] args) {
        Code code = new Code(7);
        StaticNestedDemo.Code other =
                new StaticNestedDemo.Code(8);

        System.out.println(code.label());
        System.out.println(other.label());

        StaticNestedDemo owner =
                new StaticNestedDemo("Warehouse");
        System.out.println(owner.ownerName);
    }
}
```

Chạy Java 17+:

```bash
javac -encoding UTF-8 StaticNestedDemo.java
java StaticNestedDemo
```

**Stdout chính xác:**

```text
ITEM-7
ITEM-8
Warehouse
```

Hai instances `Code` được tạo **không cần instance Outer**. Field `PREFIX` là static; field `ownerName` là instance và không thể truy cập trần từ `Code.label()`.

### Nếu cần outer instance state?

Có thể truyền reference **tường minh**:

```java
static class Inspector {
    String inspect(StaticNestedDemo owner) {
        return owner.ownerName;
    }
}
```

Việc `Inspector` là static nested class không cấm nó dùng một object Outer được truyền vào; chỉ có nghĩa **không có Outer instance ngầm định**. Nó vẫn tuân thủ type checking và access control.

## 5. Vì sao static nested class thường là lựa chọn mặc định tốt?

Nếu helper chỉ cần **namespace/encapsulation** của Outer nhưng không cần state của **một Outer instance cụ thể**, `private static class Helper` thường diễn đạt đúng sự độc lập: tạo/test dễ hơn, không có enclosing-instance association bắt buộc. Trường hợp kinh điển là `static nested Builder` tạo outer value object (ví dụ runnable tiếp theo), hoặc `static nested Node` trong collection.

Đừng coi đây là quy tắc tuyệt đối: một inner member class hợp lý khi callback/cursor cần thao tác trên đúng owner instance. **Chọn dựa trên dependency và lifecycle**, không phải ý nghĩ “static lúc nào cũng nhanh hơn”. Bài **Chọn lớp lồng hay lớp cấp cao nhất** trình bày ma trận thiết kế, trade-off public API và refactoring.

## 6. Runnable Builder với static nested class

Lưu **`BuilderNestedDemo.java`**:

```java
public final class BuilderNestedDemo {
    private final String host;
    private final int port;

    private BuilderNestedDemo(Builder builder) {
        host = builder.host;
        port = builder.port;
    }

    @Override
    public String toString() {
        return host + ":" + port;
    }

    public static final class Builder {
        private String host = "localhost";
        private int port = 8080;

        public Builder host(String value) {
            host = value;
            return this;
        }

        public Builder port(int value) {
            port = value;
            return this;
        }

        public BuilderNestedDemo build() {
            return new BuilderNestedDemo(this);
        }
    }

    public static void main(String[] args) {
        BuilderNestedDemo first =
                new Builder().build();

        BuilderNestedDemo second =
                new Builder().host("example.test").port(9000).build();

        System.out.println(first);
        System.out.println(second);
    }
}
```

```bash
javac -encoding UTF-8 BuilderNestedDemo.java
java BuilderNestedDemo
```

Stdout:

```text
localhost:8080
example.test:9000
```

Một `Builder` mới được tạo mà **không cần một instance `BuilderNestedDemo`** trước đó. Builder có thể truy cập private constructor/fields theo quan hệ nesting access.

## 7. Non-static member inner class: gắn với một Outer instance

**Non-static member inner class** gắn mỗi inner object với một **enclosing instance** phù hợp:

~~~java
class Account {
    private int balance;
    class Reader {
        int currentBalance() { return balance; }
    }
}
~~~

~~~java
Account account = new Account();
Account.Reader reader = account.new Reader();
~~~

`Reader` là một class thực thụ, có thể có constructor, fields, methods và implement interface; nó **không tự extends Account**. Từ instance method của Account có thể dùng `new Reader()`; từ static context phải cung cấp owner rõ ràng. Bài **Inner member class gắn với một đối tượng bao ngoài** dạy sâu identity nhiều owners, generic membership và những nguyên tắc lifetime.

## 8. Ví dụ runnable: inner class đọc/sửa outer state

Lưu **`InnerClassDemo.java`**:

```java
public class InnerClassDemo {
    private final String accountId;
    private int balance;

    public InnerClassDemo(String accountId, int balance) {
        this.accountId = accountId;
        this.balance = balance;
    }

    public class Teller {
        public void deposit(int amount) {
            balance += amount;
        }

        public String receipt() {
            return accountId + ":" + balance;
        }
    }

    public Teller createTeller() {
        return new Teller();
    }

    public static void main(String[] args) {
        InnerClassDemo a = new InnerClassDemo("A", 100);
        InnerClassDemo b = new InnerClassDemo("B", 200);

        InnerClassDemo.Teller tellerA = a.new Teller();
        InnerClassDemo.Teller tellerB = b.createTeller();

        tellerA.deposit(20);
        tellerB.deposit(5);

        System.out.println(tellerA.receipt());
        System.out.println(tellerB.receipt());
    }
}
```

```bash
javac -encoding UTF-8 InnerClassDemo.java
java InnerClassDemo
```

Stdout:

```text
A:120
B:205
```

Hai `Teller` objects đều là type `InnerClassDemo.Teller`, nhưng gắn với **hai enclosing instances khác nhau**. Việc sửa `balance` qua Teller A không đụng balance của B.

### Phân biệt type và enclosing instance

`InnerClassDemo.Teller` là **cùng một member class** bất kể được tạo từ instance `a` hay `b`. Java không sinh type `a.Teller` khác type `b.Teller`. Chính **reference gắn với instance tại runtime** xác định owner mà `Teller` đọc/sửa.

## 9. `Outer.this` và `Outer.super`

Trong inner instance method, `this` là **inner object**, `Outer.this` là **enclosing Outer object** được chọn theo lexical nesting. Ví dụ:

~~~java
class Outer {
    String name = "OUTER";
    class Inner {
        String name = "INNER";
        String describe() {
            return this.name + "/" + Outer.this.name;
        }
    }
}
~~~

`describe()` trả `"INNER/OUTER"`. Với nhiều tầng nesting, qualified `TypeName.this` chỉ hợp lệ khi có enclosing instance tương ứng, không xuyên qua static boundary để tạo ra một Outer object không tồn tại. Bài **Che khuất tên và định danh bằng Outer.this** giải thích cả local/field shadowing, lambda/anonymous, `Outer.super` và nhiều scope lồng.

## 10. Runnable: `this` khác `Outer.this`

Lưu **`OuterThisDemo.java`**:

```java
public class OuterThisDemo {
    private final String name = "OUTER";

    public class Inner {
        private final String name = "INNER";

        public String show() {
            return this.name + " / " + OuterThisDemo.this.name;
        }

        public boolean sameOwner(OuterThisDemo other) {
            return OuterThisDemo.this == other;
        }
    }

    public static void main(String[] args) {
        OuterThisDemo outer = new OuterThisDemo();
        OuterThisDemo.Inner inner = outer.new Inner();

        System.out.println(inner.show());
        System.out.println(inner.sameOwner(outer));
        System.out.println(inner.sameOwner(new OuterThisDemo()));
    }
}
```

```bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
```

Stdout:

```text
INNER / OUTER
true
false
```

`OuterThisDemo.this` trả enclosing instance gắn với inner object, không tự tạo object mới.

## 11. Inner class có tự động dùng outer instance làm superclass không?

**Không.** Enclosing instance **khác** quan hệ kế thừa `extends`.

```java
class Outer {
    class Inner {
    }
}
```

`Inner` **không** tự extends Outer. Nếu không khai báo superclass khác, Inner extends Object như class thông thường.

- **Nesting** cho access/scope và có thể có enclosing instance.
- **Inheritance** cho quan hệ subtype, overridden methods và method/field inheritance.

Câu `Inner is-a Outer` là sai trừ khi class Inner thật sự được khai báo extends Outer và thỏa constraints. Một member inner class thường không có quan hệ subtype với enclosing class.

### Vậy có dùng interface được không?

Có:

```java
interface Task {
    void execute();
}

class Owner {
    class Worker implements Task {
        @Override
        public void execute() {
            System.out.println("done");
        }
    }
}
```

Inner class là một implementation của Task và đồng thời gắn với Owner instance.

## 12. Phạm vi truy cập private giữa enclosing class và nested classes

Nested classes và enclosing type có thể truy cập `private` members của nhau theo ngữ cảnh nesting, nhưng **quyền truy cập** khác với **cách lấy receiver**. Ví dụ:

~~~java
class Vault {
    private int secret = 42;
    static class Inspector {
        int read(Vault source) { return source.secret; }
    }
    class Reader {
        int read() { return secret; }
    }
}
~~~

Static nested `Inspector` phải nhận Vault instance; member inner `Reader` có enclosing Vault instance. Nesting không công bố private API ra bên ngoài. Từ Java 11, JVM có cơ chế **nestmate access control**; đừng phụ thuộc tên synthetic accessor cụ thể. Bài **Truy cập thành viên private và thành viên bao ngoài** trình bày mọi trường hợp private, multi-level và cách compiler/JVM thực thi.

## 13. Runnable: static và inner đều đọc private state

Lưu **`PrivateAccessDemo.java`**:

```java
public class PrivateAccessDemo {
    private final int number;

    public PrivateAccessDemo(int number) {
        this.number = number;
    }

    private static class StaticReader {
        int read(PrivateAccessDemo target) {
            return target.number;
        }
    }

    private class InnerReader {
        int read() {
            return number;
        }
    }

    public static void main(String[] args) {
        PrivateAccessDemo outer = new PrivateAccessDemo(42);

        StaticReader first = new StaticReader();
        InnerReader second = outer.new InnerReader();

        System.out.println(first.read(outer));
        System.out.println(second.read());
    }
}
```

```bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
```

Stdout:

```text
42
42
```

Cả hai nested classes đều private đối với code bên ngoài, nhưng `main` của enclosing class được phép khởi tạo/chạm đến chúng theo access rules.

## 14. Member access modifiers: nested type có thể public/private/protected

Member nested class có thể khai báo như các class members:
- `public static class Builder`;
- `private static class Node`;
- `protected class InnerHelper`;
- Package-private `class Helper`.

Khi là API được công bố, kiểu nested có thể xuất hiện trong signature:

```java
public final class Result {
    public static record Error(String code) {}
}
```

Tuy nhiên không phải loại nested nào cũng phù hợp làm public API. Một private implementation helper không nên bị lộ không chủ đích qua public return type không truy cập được.

### Top-level class và nested member class khác nhau

Một top-level class thông thường có access ở top level là `public` hoặc package-private; **không được khai báo top-level private/protected**.

Một member class đặt bên trong một enclosing type **có thể private/protected** theo language rules áp dụng.

Local/anonymous class **không phải member class** và không mang cùng bộ access modifiers của member types. Tên local class chỉ sống trong scope khai báo.

## 15. Static context và quyền dùng instance members

Một lỗi kinh điển:

```java
class Outer {
    private int count;

    static class Nested {
        int read() {
            // return count; // Lỗi: không có Outer instance.
            return 0;
        }
    }
}
```

Sửa bằng cách truyền instance:

```java
static class Nested {
    int read(Outer owner) {
        return owner.count;
    }
}
```

Hoặc nếu bản chất class phải gắn với một Outer instance, thay bằng non-static member inner class:

```java
class Inner {
    int read() {
        return count;
    }
}
```

**Quy tắc thiết kế:** chọn static nested theo quan hệ **naming/encapsulation**, chọn inner khi quan hệ **owner instance** là một phần contract.

## 16. Member inner class và giữ reference đến outer: chú ý vòng đời

Non-static member inner object gắn với enclosing instance. Nếu một long-lived registry giữ inner listener, nó **có thể kéo dài vòng đời owner** hơn dự kiến:

~~~text
Event bus → inner listener → enclosing controller
~~~

Đây là vấn đề **reachability và lifecycle**, không phải “mọi inner class đều leak”. Khi listener có thể tiếp tục tồn tại lâu, nên hủy đăng ký theo lifecycle hoặc chọn static nested/explicit dependency nếu phù hợp. Chuyển thành static nested **không sửa** retention nếu helper vẫn tự giữ strong reference tới owner.

Bài **Tham chiếu ngầm tới đối tượng bao ngoài và nguy cơ giữ bộ nhớ** là nơi phân tích GC roots, callbacks, lambdas, method references, subscription cleanup, weak refs và heap inspection. Đây chỉ là cảnh báo sớm để chọn loại class.

## 17. Local class: lớp có tên nhưng chỉ nằm trong phạm vi cục bộ

Một **local class** được khai báo trong block thích hợp của method/constructor, hoặc ngữ cảnh tương đương theo Java rules:

```java
void process() {
    class Formatter {
        String format(int n) {
            return "n=" + n;
        }
    }

    Formatter formatter = new Formatter();
}
```

`Formatter` có **tên type trong scope** từ điểm khai báo theo scoping rules, nhưng code bên ngoài method không thể trực tiếp viết `new Formatter()` vì không thấy tên ấy.

Local class hữu ích khi:
- Logic đủ lớn để có một tên class, constructor và nhiều methods.
- Type chỉ dùng trong một method/block.
- Nó cần đọc một số local variables final/effectively final.
- Không đáng tạo member nested class hay top-level class.

### Local class là một class đầy đủ

Nó có thể:
- Implement interface hoặc extend superclass.
- Có constructor và instance members.
- Override methods.
- Được khởi tạo nhiều lần trong scope.
- Trả về dưới kiểu interface/superclass nếu phù hợp.

**Nhưng** không thể dùng tên local class trực tiếp ngoài scope khai báo; caller thường chỉ nhìn thấy type public/interface mà local class implement.

## 18. Runnable: local class với constructor và hai instances

Lưu **`LocalClassDemo.java`**:

```java
public class LocalClassDemo {
    interface Greeter {
        String greet();
    }

    static Greeter create(String prefix) {
        int punctuationCount = 2;

        class LocalGreeter implements Greeter {
            private final String name;

            LocalGreeter(String name) {
                this.name = name;
            }

            @Override
            public String greet() {
                return prefix + " " + name
                        + "!".repeat(punctuationCount);
            }
        }

        return new LocalGreeter("An");
    }

    public static void main(String[] args) {
        Greeter first = create("Xin chào");
        Greeter second = create("Hello");

        System.out.println(first.greet());
        System.out.println(second.greet());
    }
}
```

```bash
javac -encoding UTF-8 LocalClassDemo.java
java LocalClassDemo
```

Stdout:

```text
Xin chào An!!
Hello An!!
```

`LocalGreeter` là **local class có tên**, nhưng method trả ra `Greeter` interface. Code `main` không cần (và ngoài scope không thể) dùng tên `LocalGreeter`.

### Có gì được capture?

- `prefix`: parameter của `create`, effectively final.
- `punctuationCount`: local variable, effectively final.
- `name`: instance field riêng của từng LocalGreeter object, không phải captured local variable.

Hai calls đến `create` tạo hai local class instances với các captured values khác nhau.

## 19. Biến cục bộ được capture: `final` hoặc `effectively final`

Local và anonymous classes có thể tham chiếu:
- Local variables;
- Method parameters;
- Exception parameters và các variables trong phạm vi cho phép;

nếu những variables thuộc loại được capture và thỏa điều kiện **final hoặc effectively final** cùng các ràng buộc về definite assignment/scope.

Ví dụ hợp lệ:

```java
void run() {
    int threshold = 10;

    class Checker {
        boolean test(int value) {
            return value > threshold;
        }
    }

    System.out.println(new Checker().test(12));
}
```

`threshold` không viết `final` nhưng không bao giờ được gán lại sau initialization; nó là **effectively final**.

Ví dụ sai:

```java
void run() {
    int threshold = 10;

    class Checker {
        boolean test(int value) {
            return value > threshold;
        }
    }

    threshold = 20; // Làm threshold không effectively final.
}
```

Nếu local class tham chiếu `threshold` trong cách cần capture, việc gán lại biến khiến compiler từ chối.

### Vì sao Java đặt ràng buộc này?

Local class instance có thể sống lâu hơn stack frame method đã kết thúc. Nó phải lưu/duy trì captured values theo semantics, không thể giả định local variable tiếp tục là một ô stack sống mãi để class đọc/ghi.

Ràng buộc final/effectively final giúp tránh ảo tưởng về việc cùng một biến cục bộ có thể bị các callback sống lâu “cùng sửa” trực tiếp.

**Capture biến tham chiếu không có nghĩa object được tham chiếu bất biến.**

## 20. Runnable: capture reference final nhưng mutate object

Lưu **`CapturedReferenceDemo.java`**:

```java
public class CapturedReferenceDemo {
    interface CounterView {
        int read();
    }

    static CounterView make(int[] shared) {
        class Reader implements CounterView {
            @Override
            public int read() {
                return shared[0];
            }
        }

        return new Reader();
    }

    public static void main(String[] args) {
        int[] data = {1};
        CounterView reader = make(data);

        System.out.println(reader.read());

        data[0] = 7;
        System.out.println(reader.read());
    }
}
```

```bash
javac -encoding UTF-8 CapturedReferenceDemo.java
java CapturedReferenceDemo
```

Stdout:

```text
1
7
```

Parameter `shared` không được gán lại trong `make` nên effectively final; local class capture **reference đến cùng mảng**. Mảng vẫn mutable, và thay phần tử ảnh hưởng lần đọc tiếp theo.

**Cảnh báo:** ví dụ một thread. Nếu mảng bị mutate qua nhiều threads, cần synchronization/visibility thích hợp; effectively final không tự làm mutable object thread-safe.

## 21. Local class từ static context không có enclosing Outer instance

Ví dụ:

```java
class Outer {
    private int value = 1;

    static void run() {
        class Local {
            int get() {
                // return value; // Không có Outer instance.
                return 0;
            }
        }
    }
}
```

Vì `run` là static method, local class không có `Outer.this` chỉ nhờ code xuất hiện trong Outer.

Sửa:
- Truyền một `Outer` object cụ thể cho Local constructor.
- Hoặc chuyển logic sang instance method nếu thật sự gắn với enclosing instance.
- Hoặc chỉ sử dụng static state hợp lệ.

Ngược lại, khi local class khai báo trong một **instance method của Outer**, nó có thể truy cập `Outer.this`/instance members thích hợp, đồng thời capture local variables.

### Đừng đồng nhất local class và “inner class member”

Local class không phải member trong class body nên không thể nhắc từ bên ngoài bằng cú pháp `Outer.Local` như `Outer.Nested` hoặc `Outer.Inner`.

## 22. Runnable: local class trong instance method dùng `Outer.this`

Lưu **`LocalEnclosingDemo.java`**:

```java
public class LocalEnclosingDemo {
    private final String owner;

    LocalEnclosingDemo(String owner) {
        this.owner = owner;
    }

    interface Task {
        String describe();
    }

    Task createTask(int id) {
        class LocalTask implements Task {
            @Override
            public String describe() {
                return LocalEnclosingDemo.this.owner
                        + "#" + id;
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        LocalEnclosingDemo a =
                new LocalEnclosingDemo("A");
        LocalEnclosingDemo b =
                new LocalEnclosingDemo("B");

        Task taskA = a.createTask(10);
        Task taskB = b.createTask(20);

        System.out.println(taskA.describe());
        System.out.println(taskB.describe());
    }
}
```

```bash
javac -encoding UTF-8 LocalEnclosingDemo.java
java LocalEnclosingDemo
```

Stdout:

```text
A#10
B#20
```

`id` được capture dưới ràng buộc effectively final; `owner` đến từ enclosing instance. Hai nguồn dữ liệu này có **cơ chế khác nhau**, dù đều truy cập được trong method local class.

## 23. Local class có thể trả về qua interface sau khi method kết thúc

Một local class có tên chỉ thấy trong method, nhưng object của nó có thể sống tiếp:

```java
Runnable makeTask() {
    int number = 7;

    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println(number);
        }
    }

    return new LocalTask();
}
```

Caller sau đó gọi `task.run()` khi method `makeTask` đã return. Việc này hợp lệ; captured value của `number` vẫn được instance dùng.

**Đừng lầm scope tên type với lifetime object:**
- Tên `LocalTask` chỉ được viết trong local scope.
- Runtime instance của LocalTask có thể được lưu trong collection, trả về, đăng ký callback hoặc chạy trong thread sau này.

Chính vì thế cần xem việc capture outer object/dependencies có gây giữ tài nguyên lâu hơn dự định không.

## 24. Anonymous class: class không tên tại một biểu thức `new`

Một anonymous class thường được viết:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
```

Code tạo **một instance của một class không có tên khai báo trong source**; class ấy implements `Runnable` và override `run()`.

Không có khai báo riêng:

```java
class MyRunnable implements Runnable { ... }
```

và cũng không có constructor `new MyRunnable()` bởi anonymous class không có tên source để gọi lại theo cách đó.

### Hai dạng phổ biến

**Implement interface:**

```java
SomeInterface ref = new SomeInterface() {
    @Override
    public void execute() {
        // ...
    }
};
```

**Subclass một class có tên:**

```java
Base ref = new Base(constructorArgs) {
    @Override
    public void work() {
        // ...
    }
};
```

Trong dạng extends class, `Base` phải cho phép subclassing và constructor invocation hợp lệ. Anonymous class không được extend final class theo cách override.

**Không được “implements nhiều interfaces” bằng cú pháp `new A(), B() { }`**. Anonymous class declaration dựa trên một class hoặc interface được chỉ định; có thể kế thừa thêm các interfaces gián tiếp qua superclass.

## 25. Runnable: anonymous implementation của interface

Lưu **`AnonymousInterfaceDemo.java`**:

```java
public class AnonymousInterfaceDemo {
    interface Formatter {
        String format(String value);
    }

    public static void main(String[] args) {
        Formatter upper = new Formatter() {
            @Override
            public String format(String value) {
                return value.toUpperCase(
                        java.util.Locale.ROOT);
            }
        };

        Formatter wrapped = new Formatter() {
            @Override
            public String format(String value) {
                return "[" + value + "]";
            }
        };

        System.out.println(upper.format("java"));
        System.out.println(wrapped.format("java"));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousInterfaceDemo.java
java AnonymousInterfaceDemo
```

Stdout:

```text
JAVA
[java]
```

Mỗi `new Formatter() { ... }` là một anonymous class expression độc lập; hai objects đều có static type `Formatter` khi nhìn qua variables, nhưng chạy logic override khác nhau.

## 26. Anonymous subclass của một class cụ thể

Ví dụ superclass:

```java
class Message {
    private final String text;

    Message(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}
```

Anonymous subclass:

```java
Message message = new Message("hello") {
    @Override
    String render() {
        return "[" + super.render() + "]";
    }
};
```

Đặc điểm:
- Có **constructor call tới superclass** với tham số `"hello"`.
- Không khai báo constructor riêng mang tên anonymous class.
- Có thể dùng **instance initializer block** nếu cần khởi tạo thêm logic, nhưng tránh side effects khó hiểu.
- Có thể dùng `super.render()` để gọi implementation superclass.
- Không thể override `final` method.

### Khi nào đáng dùng?

Nếu chỉ đổi một method trong một chỗ và không cần reuse/type name, anonymous subclass có thể gọn. Nếu logic phức tạp, có nhiều instances cấu hình khác nhau, hoặc cần kiểm thử độc lập, named class thường dễ duy trì.

## 27. Runnable: anonymous subclass gọi `super`

Lưu **`AnonymousSubclassDemo.java`**:

```java
class Message {
    private final String text;

    Message(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}

public class AnonymousSubclassDemo {
    public static void main(String[] args) {
        Message basic = new Message("hello");

        Message decorated = new Message("hello") {
            @Override
            String render() {
                return "[" + super.render() + "]";
            }
        };

        System.out.println(basic.render());
        System.out.println(decorated.render());
        System.out.println(basic == decorated);
    }
}
```

```bash
javac -encoding UTF-8 AnonymousSubclassDemo.java
java AnonymousSubclassDemo
```

Stdout:

```text
hello
[hello]
false
```

Biến `decorated` khai báo kiểu `Message` nhưng runtime instance thuộc anonymous subclass của Message; lời gọi `render()` dispatch tới override.

## 28. Anonymous class cũng capture local variables

```java
int offset = 5;

java.util.function.IntUnaryOperator add =
        new java.util.function.IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        };
```

`offset` phải final/effectively final.

### Không có tên không có nghĩa không có state

Anonymous class có thể có:
- Instance fields;
- Initializer blocks;
- Methods;
- References tới enclosing instance nếu context hợp lệ;
- Captured local variables;
- Overrides của superclass methods.

Nhưng caller giữ object bằng một **static type** như interface/superclass và không được tự nhiên gọi một method chỉ xuất hiện trong anonymous class mà static type không khai báo.

### Ví dụ về method mới không thấy qua interface

```java
Runnable task = new Runnable() {
    public void helper() {
        System.out.println("help");
    }

    @Override
    public void run() {
        helper();
    }
};

task.run();
// task.helper(); // Không biên dịch vì Runnable không có helper().
```

Code trong anonymous class có thể gọi `helper()`, nhưng API của variable `task` chỉ công bố những methods của `Runnable` (cùng Object methods hợp lệ).

## 29. Runnable: anonymous class dùng captured value và internal state

Lưu **`AnonymousCaptureDemo.java`**:

```java
import java.util.function.IntSupplier;

public class AnonymousCaptureDemo {
    static IntSupplier create(int start) {
        int increment = 2;

        return new IntSupplier() {
            private int value = start;

            @Override
            public int getAsInt() {
                value += increment;
                return value;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier first = create(10);
        IntSupplier second = create(100);

        System.out.println(first.getAsInt());
        System.out.println(first.getAsInt());
        System.out.println(second.getAsInt());
    }
}
```

```bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
```

Stdout:

```text
12
14
102
```

Phân biệt:
- `start`, `increment` là parameters/local values được capture.
- `value` là **mutable instance field** riêng của mỗi anonymous object.
- Effectively-final restriction áp dụng cho **local variables được capture**, không cấm anonymous object có instance fields mutable.

**Không tự động thread-safe:** gọi `getAsInt` đồng thời trên cùng anonymous instance có data race đối với `value` nếu thiếu synchronization.

## 30. `this` trong anonymous class và lambda khác nhau

Anonymous class tạo **một class instance** mới. Bên trong anonymous class instance method, `this` là **anonymous instance**.

Lambda expression có **lexical scope** khác: `this` trong lambda (khi hợp lệ) mang nghĩa `this` của enclosing context, **không phải một “lambda object this”** do lambda tạo riêng trong source.

Đây là khác biệt lớn dù cả hai có thể được gán cho functional interface `Runnable`:

```java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.getClass().getSimpleName());
    }
};

Runnable lambda = () -> {
    // this ở đây trỏ enclosing instance nếu có.
};
```

Tên class sinh ra cho anonymous/lambda **không nên đưa vào expected stdout cố định** nếu code kiểm tra tên runtime type; thay vào đó so sánh identity với owner.

### Một điều nữa: overload và shadowing

Anonymous class là một scope class riêng; nó có thể khai báo field/method làm shadow tên từ enclosing context. Lambda không tạo một class scope kiểu Java source giống vậy và có những quy tắc name resolution riêng.

Vì thế thay anonymous class bằng lambda **không phải luôn là refactor bảo toàn mọi hành vi**, dù implementation chỉ có một abstract method.

## 31. Runnable: so sánh `this` của anonymous và lambda

Lưu **`ThisLambdaComparisonDemo.java`**:

```java
public class ThisLambdaComparisonDemo {
    private final String ownerName = "OWNER";

    void demonstrate() {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        "anonymous this is owner = "
                        + ((Object) this == ThisLambdaComparisonDemo.this));
            }
        };

        Runnable lambda = () -> {
            System.out.println(
                    "lambda this is owner = "
                    + (this == ThisLambdaComparisonDemo.this));
        };

        anonymous.run();
        lambda.run();
        System.out.println(ownerName);
    }

    public static void main(String[] args) {
        new ThisLambdaComparisonDemo().demonstrate();
    }
}
```

```bash
javac -encoding UTF-8 ThisLambdaComparisonDemo.java
java ThisLambdaComparisonDemo
```

Stdout:

```text
anonymous this is owner = false
lambda this is owner = true
OWNER
```

Bên trong anonymous `run`, `this` là instance của anonymous Runnable implementation, nên khác Outer.this. Bên trong lambda, `this` là enclosing `ThisLambdaComparisonDemo` instance.

### Static method chứa lambda có `this` không?

Không. `this` không hợp lệ trong static context chỉ vì được viết trong lambda. Lambda không tạo ra một enclosing instance tự động cho static method.

## 32. Lambda và anonymous class: nên chọn cái nào?

Với **functional interface** (chỉ một abstract method theo định nghĩa áp dụng), lambda thường gọn:

```java
Runnable task = () -> System.out.println("done");
```

Anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("done");
    }
};
```

**Thường ưu tiên lambda khi**:
- Mục tiêu chỉ là cung cấp một behavior ngắn của functional interface.
- Không cần một class riêng có internal mutable fields/methods.
- Không cần anonymous `this` hoặc subclass-specific initializer.
- Không cần override nhiều methods của concrete superclass.

**Dùng anonymous class khi**:
- Cần subclass một class cụ thể ngay tại một điểm.
- Interface/class có nhiều methods cần override trong một implementation inline.
- Cần `super` behavior của anonymous subclass.
- Cần instance state/methods rõ ràng trong đối tượng callback.
- Semantics của `this`/scope trong anonymous class là điều có chủ đích.

**Dùng named local/member class khi** implementation dài, có nhiều hành vi, cần debug/test/reuse hoặc tên type có giá trị giải thích.

### Lambdas có phải anonymous classes không?

Không nên đồng nhất chúng. Lambda là **lambda expression** có semantics riêng trong Java; runtime có thể dùng implementation strategy như invokedynamic. Bạn không nên dựa vào class file names hoặc identity của lambda object như một anonymous class đã được khai báo bằng `new Interface() { ... }`.

## 33. Anonymous class và class trừu tượng

Anonymous class có thể tạo một subclass của abstract class bằng cách cung cấp implementations còn thiếu:

```java
abstract class Operation {
    abstract int compute(int a, int b);
}

Operation sum = new Operation() {
    @Override
    int compute(int a, int b) {
        return a + b;
    }
};
```

Nếu abstract class có constructor yêu cầu tham số, dùng cú pháp `new AbstractBase(args) { ... }` với constructor invocation phù hợp.

**Không thể tạo anonymous subclass của final class.** Với sealed hierarchy Java 17 cũng phải tuân thủ danh sách permitted direct subclasses và các ràng buộc tương ứng; không thể tự ý dùng anonymous subclass để vượt sealed restrictions.

## 34. Runnable: anonymous subclass của abstract class

Lưu **`AnonymousAbstractDemo.java`**:

```java
abstract class Operation {
    private final String label;

    Operation(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    abstract int apply(int a, int b);
}

public class AnonymousAbstractDemo {
    public static void main(String[] args) {
        Operation multiply = new Operation("multiply") {
            @Override
            int apply(int a, int b) {
                return a * b;
            }
        };

        Operation maximum = new Operation("max") {
            @Override
            int apply(int a, int b) {
                return Math.max(a, b);
            }
        };

        System.out.println(multiply.label()
                + "=" + multiply.apply(3, 4));
        System.out.println(maximum.label()
                + "=" + maximum.apply(3, 4));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousAbstractDemo.java
java AnonymousAbstractDemo
```

Stdout:

```text
multiply=12
max=4
```

Cả hai anonymous objects có static type `Operation` khi được lưu trong biến, nhưng runtime subclasses có implementations `apply` khác nhau.

## 35. Kết hợp các loại nested class trong một hệ thống

Một class không bị giới hạn chỉ dùng một dạng nesting. Chúng có thể phục vụ mục đích khác nhau:

- **Static nested `Builder`**: xây dựng một đối tượng mà không cần enclosing instance đã hoàn tất.
- **Member inner `View`**: biểu diễn một view gắn với một instance cụ thể.
- **Local `Validator`**: logic có tên chỉ cần trong một method.
- **Anonymous `Runnable`**: callback một lần với behavior gọn.
- **Lambda**: một lựa chọn khác cho functional behavior, không phải loại anonymous class.

Không có nguyên tắc “nested class càng sâu càng tốt”. Lồng quá nhiều tầng có thể gây khó đọc, coupling và hiểu nhầm `this`/scope.

## 36. Chương trình tổng hợp đủ bốn loại

Lưu **`NestedKindsDemo.java`**:

```java
public class NestedKindsDemo {
    private final String owner;

    NestedKindsDemo(String owner) {
        this.owner = owner;
    }

    static class StaticHelper {
        String describe() {
            return "static";
        }
    }

    class InnerHelper {
        String describe() {
            return "inner:" + owner;
        }
    }

    interface Action {
        String run();
    }

    Action localAction(int n) {
        class LocalAction implements Action {
            @Override
            public String run() {
                return "local:" + n;
            }
        }

        return new LocalAction();
    }

    Action anonymousAction(int n) {
        return new Action() {
            @Override
            public String run() {
                return "anonymous:" + n;
            }
        };
    }

    public static void main(String[] args) {
        NestedKindsDemo outer = new NestedKindsDemo("A");

        StaticHelper one = new StaticHelper();
        NestedKindsDemo.InnerHelper two =
                outer.new InnerHelper();
        Action three = outer.localAction(7);
        Action four = outer.anonymousAction(8);

        System.out.println(one.describe());
        System.out.println(two.describe());
        System.out.println(three.run());
        System.out.println(four.run());
    }
}
```

```bash
javac -encoding UTF-8 NestedKindsDemo.java
java NestedKindsDemo
```

**Stdout:**

```text
static
inner:A
local:7
anonymous:8
```

Tóm tắt:
- `StaticHelper` được tạo không cần Outer instance, chỉ dùng tên namespace.
- `InnerHelper` gắn với outer instance `outer`.
- `LocalAction` là named type chỉ thấy trong `localAction` và capture `n`.
- Anonymous implementation khai báo inline trong `anonymousAction` và cũng capture `n`.

### Bài học từ ví dụ tổng hợp

Bốn kinds đều tạo ra những objects có thể gọi methods như mọi Java class instance. Sự khác biệt nằm ở **declaration location, enclosing context, capture và construction**, không phải mỗi kind có một loại “bộ nhớ đặc biệt” tách khỏi objects thông thường.

## 37. Local và anonymous class có “lưu biến local trên stack” không?

Không nên nghĩ runtime instance chỉ giữ một “con trỏ đến ô stack” của method đã kết thúc. Những giá trị/refs cần thiết được capture theo semantics ngôn ngữ; implementation details do compiler/JVM chọn.

Ví dụ:

```java
Runnable createTask() {
    String message = "done";
    return () -> System.out.println(message);
}
```

Sau `createTask()` return, Runnable vẫn dùng được `message` khi được chạy. Việc lambda/local/anonymous class sống lâu hơn method là hợp lệ, miễn object còn reachable.

### Capture tham chiếu có thể giữ object sống lâu

Nếu captured local variable trỏ một object lớn, callback lưu lâu có thể giữ reference đến object đó. Tương tự, local/anonymous class trong enclosing instance context có thể giữ enclosing object khi cần. Vì vậy:
- Không capture nguyên service/controller nếu chỉ cần một ID/String.
- Xem lifecycle khi đăng ký callback long-lived.
- Hủy listeners/subscriptions đúng lúc.
- Tránh tham chiếu qua enclosing instance không cần thiết.

## 38. Cần dùng `final` viết tường minh không?

Không bắt buộc đối với **effectively final** variables:

```java
int factor = 3;

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(factor);
    }
};
```

`factor` effectively final nếu không bị gán lại theo rules.

Tuy nhiên code:

```java
int factor = 3;
factor++;
Runnable task = () -> System.out.println(factor);
```

không hợp lệ vì `factor` đã bị sửa và không effectively final.

Một **mutable object** được tham chiếu bởi final variable có thể thay đổi nội dung:

```java
final java.util.List<String> items =
        new java.util.ArrayList<>();

Runnable task = () -> System.out.println(items.size());

items.add("A");
task.run(); // 1
```

Nhưng code đồng thời cần synchronization khi một thread mutate list và thread khác đọc, không thể dựa vào `final` alone.

### Workaround dùng array counter có nên không?

Một số người viết `final int[] count = {0};` rồi thay `count[0]++` trong lambda/anonymous class. Cú pháp có thể compile nhưng:
- Nó làm state trở nên mutable ngầm.
- Không thread-safe.
- Gây khó hiểu intent.
- Có thể nên dùng một object holder thiết kế rõ, `AtomicInteger` nếu đúng bài toán, hoặc thay đổi API để return result.

**Đừng xem mảng một phần tử là cách mặc định để “lách effectively final”.**

## 39. `private static` member nested class có phải độc lập với enclosing type không?

Nó độc lập về **enclosing instance requirement**, nhưng không độc lập hoàn toàn:
- Tên type vẫn là thành viên của enclosing type.
- Có thể truy cập private static state/enclosing private instance state qua reference.
- Được compile và mang nest membership theo JVM semantics.
- Bị điều chỉnh visibility theo modifier (`private`, package-private...).
- Có thể phụ thuộc constants/static initialization của enclosing type.

Vì vậy khi gọi “static nested độc lập”, nên hiểu là **không có implicit Outer instance**, không phải “không có bất kỳ quan hệ gì với Outer”.

## 40. Nested interfaces, records và enums: mở rộng phân loại

Bên cạnh nested **classes**, Java cũng cho phép **nested interface**, **nested enum** và **nested record** trong những ngữ cảnh phù hợp. Một số nested types này **mặc nhiên static** theo language rules.

Ví dụ:

```java
class Api {
    interface Handler {
        String handle(String input);
    }

    record Result(int code, String message) {
    }

    enum State {
        READY, DONE
    }
}
```

Có thể dùng:

```java
Api.Handler handler = input -> input;
Api.Result result = new Api.Result(200, "OK");
Api.State state = Api.State.READY;
```

Không cần instance Api để tạo Result hoặc truy cập enum state.

### Lưu ý về Java 17

Nested record declarations có static semantics; record là final class. Một record không tự có implicit enclosing instance chỉ vì nó nằm trong một class khác.

**Không gọi nested interface là “non-static inner interface”** theo nghĩa member inner class. Interface nested type thuộc ngữ nghĩa static thích hợp.

## 41. Runnable: nested interface/record/enum

Lưu **`NestedTypesDemo.java`**:

```java
public class NestedTypesDemo {
    interface Handler {
        Result handle(String input);
    }

    record Result(int code, String data) {
    }

    enum State {
        OK, ERROR
    }

    public static void main(String[] args) {
        Handler handler =
                input -> new Result(200, input.toUpperCase(
                        java.util.Locale.ROOT));

        Result result = handler.handle("java");

        System.out.println(result);
        System.out.println(State.OK);
    }
}
```

```bash
javac -encoding UTF-8 NestedTypesDemo.java
java NestedTypesDemo
```

Stdout:

```text
Result[code=200, data=JAVA]
OK
```

Đây là các **nested types**, nhưng không phải bốn kinds của **nested class** đều có cùng cách tạo instance. Enum constants và interface có quy tắc riêng.

## 42. Static declarations bên trong inner/local class ở Java 17

Một số tài liệu hoặc câu hỏi phỏng vấn cũ nói: **“Inner class không thể có static members trừ constant variables.”** Quy tắc này đã được **nới trong các phiên bản Java mới hơn**. Trong **Java 17**, inner classes được phép khai báo static members phù hợp, kể cả static methods/static nested types, theo language rules hiện hành.

Điều đó **không** biến non-static member inner class thành static nested class:
- Inner instance vẫn gắn với enclosing Outer instance.
- `Outer.this` vẫn hợp lệ trong inner instance context.
- Static method của inner class vẫn **không có `this`**.
- Static nested member class vẫn không yêu cầu Outer instance.

**Không học máy móc quy tắc từ tài liệu Java 8 rồi áp dụng nguyên trạng cho Java 17.** Khi cần kết luận một construct có compile, kiểm tra theo đúng `--release 17`.

### Ví dụ Java 17

Lưu **`InnerStaticMemberDemo.java`**:

```java
public class InnerStaticMemberDemo {
    private final String name = "OUTER";

    class Inner {
        static String type() {
            return "INNER-TYPE";
        }

        String owner() {
            return InnerStaticMemberDemo.this.name;
        }
    }

    public static void main(String[] args) {
        InnerStaticMemberDemo outer =
                new InnerStaticMemberDemo();
        Inner inner = outer.new Inner();

        System.out.println(Inner.type());
        System.out.println(inner.owner());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InnerStaticMemberDemo.java
java InnerStaticMemberDemo
```

Stdout:

```text
INNER-TYPE
OUTER
```

Mục đích ví dụ là minh họa **sự khác nhau giữa “một class là inner” và “class đó có static member”** theo Java 17, không khuyến khích lồng quá nhiều static members trong một inner class nếu khó đọc.

## 43. Lớp lồng nhau và generic type parameters

Một member inner class trong một generic Outer có thể sử dụng type parameter của enclosing instance context:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }
}
```

Một static nested class **không thể tham chiếu trực tiếp type parameter `T` của Outer** như một type parameter instance được nó tự kế thừa:

```java
class Box<T> {
    static class StaticReader {
        // T read() { ... } // Không hợp lệ: T của Outer không trong scope kiểu đó.
    }
}
```

Nó có thể tự khai báo type parameters:

```java
static class StaticReader<U> {
    U identity(U value) {
        return value;
    }
}
```

### Ví dụ về type name của inner class

Với `Box<String> box = new Box<>("Java");`, kiểu non-static member inner có thể được nhắc là `Box<String>.Reader`.

Đối với static nested class, kiểu thường là `Box.StaticReader<U>`, không phải `Box<String>.StaticReader<U>` vì static member type không gắn với từng parameterization of Outer theo cú pháp đó.

## 44. Runnable: generics và inner/static nested classes

Lưu **`GenericNestedDemo.java`**:

```java
public class GenericNestedDemo<T> {
    private final T value;

    GenericNestedDemo(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }

    static class Holder<U> {
        private final U value;

        Holder(U value) {
            this.value = value;
        }

        U read() {
            return value;
        }
    }

    public static void main(String[] args) {
        GenericNestedDemo<String> box =
                new GenericNestedDemo<>("Java");

        GenericNestedDemo<String>.Reader reader =
                box.new Reader();

        GenericNestedDemo.Holder<Integer> holder =
                new GenericNestedDemo.Holder<>(17);

        System.out.println(reader.read());
        System.out.println(holder.read());
    }
}
```

```bash
javac -encoding UTF-8 GenericNestedDemo.java
java GenericNestedDemo
```

Stdout:

```text
Java
17
```

`Reader` gắn với một `GenericNestedDemo<String>` instance; static `Holder<U>` có generic parameter `U` riêng và không yêu cầu enclosing instance.

## 45. Shadowing: cùng tên biến ở nhiều scope

Khi parameter, inner field và outer field trùng tên, Java dùng scope/shadowing để phân giải:

~~~java
class Outer {
    int value = 1;
    class Inner {
        int value = 2;
        void show(int value) {
            System.out.println(value);            // 3
            System.out.println(this.value);       // 2
            System.out.println(Outer.this.value); // 1
        }
    }
}
~~~

Gọi `show(3)` in lần lượt 3, 2, 1. Truy cập `private` được phép hay không là một vấn đề riêng với phân giải tên. Bài **Che khuất tên và định danh bằng Outer.this** phân tích chi tiết khi có nhiều tiers, inherited members, method resolution và lambda/anonymous.

## 46. Runnable: local, inner, outer cùng tên

Lưu **`NestedShadowingDemo.java`**:

```java
public class NestedShadowingDemo {
    private int value = 1;

    class Inner {
        private int value = 2;

        void show(int value) {
            System.out.println(value);
            System.out.println(this.value);
            System.out.println(NestedShadowingDemo.this.value);
        }
    }

    public static void main(String[] args) {
        NestedShadowingDemo outer =
                new NestedShadowingDemo();
        Inner inner = outer.new Inner();

        inner.show(3);
    }
}
```

```bash
javac -encoding UTF-8 NestedShadowingDemo.java
java NestedShadowingDemo
```

Stdout:

```text
3
2
1
```

Lời giải không dựa vào runtime class name; nó dựa vào lexical name resolution và explicit qualifiers.

## 47. Reflection: xác định class là member, local hay anonymous

Java Reflection cung cấp những operations như:
- `Class.isMemberClass()`;
- `Class.isLocalClass()`;
- `Class.isAnonymousClass()`;
- `Class.getDeclaringClass()`;
- `Class.getEnclosingClass()`;
- `Class.getSimpleName()`.

Một static nested class và một non-static member inner class đều là **member classes** khi xét `isMemberClass()`. Phân biệt static/nons-static bằng modifiers, chẳng hạn `Modifier.isStatic(clazz.getModifiers())` đối với member class.

Local class trả `isLocalClass() == true`, anonymous class trả `isAnonymousClass() == true`. Một named top-level class không thuộc ba nhóm đó.

### Không dựa vào compiler-generated binary names làm API

Bạn có thể nhìn thấy files/tên như:
- `Outer$Nested.class`;
- `Outer$Inner.class`;
- `Outer$1Local.class`;
- `Outer$1.class`.

Những ví dụ này chỉ để **nhận diện thường gặp**, không phải danh sách tên chắc chắn cho mọi compiler/source/anonymous expression. Thứ tự numbering và chi tiết generated names không nên làm business contract.

## 48. Runnable: reflection phân loại bốn kinds

Lưu **`NestedReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

public class NestedReflectionDemo {
    static class Nested {
    }

    class Inner {
    }

    static void inspect() {
        class Local {
        }

        Object anonymous = new Object() {
        };

        print("static", Nested.class);
        print("inner", Inner.class);
        print("local", Local.class);
        print("anonymous", anonymous.getClass());
    }

    static void print(String label, Class<?> type) {
        System.out.println(label + ": "
                + type.isMemberClass() + ","
                + type.isLocalClass() + ","
                + type.isAnonymousClass() + ","
                + Modifier.isStatic(type.getModifiers()));
    }

    public static void main(String[] args) {
        inspect();
    }
}
```

```bash
javac -encoding UTF-8 NestedReflectionDemo.java
java NestedReflectionDemo
```

Stdout theo các API reflection trên Java 17:

```text
static: true,false,false,true
inner: true,false,false,false
local: false,true,false,false
anonymous: false,false,true,false
```

Không in `getName()` hoặc `getSimpleName()` ở đây để tránh phụ thuộc tên compiler-generated của anonymous/local classes. Dòng cuối `Modifier.isStatic` cho biết anonymous class không được khai báo là static member type; nó không phải câu trả lời thay thế cho việc hỏi enclosing instance có tồn tại không.

## 49. Source file organization và bytecode

Một file source có thể chứa:
- Một public top-level class đúng tên file.
- Nhiều nested member classes.
- Local classes khai báo trong methods.
- Anonymous class expressions.
- Các package-private top-level classes khác nếu cần.

Ví dụ khi biên dịch:

```bash
javac -encoding UTF-8 NestedKindsDemo.java
```

Compiler thường sinh nhiều `.class` files cho các runtime classes liên quan. Điều này bình thường: **nested trong source không có nghĩa mọi bytecode nằm trong duy nhất một file**.

Có thể nghiên cứu:

```bash
javap -p NestedKindsDemo
```

Nhưng output chi tiết phụ thuộc compiler và class file structure; không suy đoán số file hay các field names nội bộ làm contract API.

## 50. Nesting và đóng gói: lợi ích không phải giấu mọi thứ

Nested class hữu ích khi một type **thực sự là implementation detail** của enclosing type:

```java
public final class LinkedBag {
    private static final class Node {
        Object value;
        Node next;
    }
}
```

`Node` là private static helper, không cần outer `LinkedBag` instance.

Nhưng nếu một nested class ngày càng lớn và được nhiều modules/packages dùng như type độc lập, có thể đưa ra top-level class với package-private/public API thích hợp.

### Câu hỏi thiết kế

- Type có ý nghĩa khi đứng riêng không?
- Có cần access private members quá thường xuyên không?
- Có bị coupling quá chặt với Outer không?
- Có phải nó chỉ là helper implementation?
- Có cần unit test trực tiếp bằng public contract?
- Nếu class được tái sử dụng ở nhiều nơi, nested name có làm code cồng kềnh?
- Có cần lifetime owner object để thực hiện behavior?

**Chọn nesting vì ownership/encapsulation**, không phải chỉ để giảm số source files.

## 51. Tránh anonymous class quá dài

Anonymous class dài hàng trăm dòng thường khó:
- Đọc và debug khi stack traces chỉ hiển thị generated type names.
- Test trực tiếp logic nếu nó gắn sâu trong method.
- Reuse behavior giữa các call sites.
- Đặt meaningful name cho design abstraction.
- Review state/capture/enclosing-instance dependencies.

Khi anonymous class bắt đầu có nhiều fields, nhiều helper methods và branches, xem xét:
- Named local class nếu scope chỉ trong một method.
- Private static nested class nếu không cần enclosing state.
- Private member inner class nếu thật sự cần enclosing state.
- Separate top-level class nếu logic là reusable domain service.
- Lambda nếu chỉ còn một functional operation ngắn.

Một anonymous class không xấu; **chọn đúng kích thước và contract** mới quan trọng.

## 52. Anonymous class không có explicit constructor riêng

Bạn không thể định nghĩa:

```java
new Runnable() {
    // Runnable() { }  // Không có tên constructor riêng theo anonymous type.
};
```

Anonymous class object có thể khai báo **instance initializer block**:

```java
Runnable task = new Runnable() {
    private final int seed;

    {
        seed = 7;
    }

    @Override
    public void run() {
        System.out.println(seed);
    }
};
```

Với subclass của một named class, phần `new Base(args) { ... }` sẽ dùng matching superclass constructor invocation theo rules.

### Cẩn thận initializer gọi overridable methods

Giống những classes thông thường, constructor/init sequence có thể tạo hazards khi gọi overridable methods trước khi state sẵn sàng. Đừng dùng anonymous initializers cho side effects phức tạp mà caller không dễ nhìn thấy.

## 53. Runnable: initializer của anonymous class

Lưu **`AnonymousInitializerDemo.java`**:

```java
public class AnonymousInitializerDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private final int seed;

            {
                seed = 7;
            }

            @Override
            public void run() {
                System.out.println("seed = " + seed);
            }
        };

        task.run();
    }
}
```

```bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
```

Stdout:

```text
seed = 7
```

Trong anonymous class, initializer block chạy trong quá trình tạo instance. `seed` là instance field final được gán trong initializer block.

## 54. Vì sao static nested class nên dùng với data structures?

Node của stack/list/tree thường không cần state của **container instance**. Vì vậy:

~~~java
final class IntStack {
    private Node head;
    private static final class Node {
        final int value;
        final Node next;
        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }
}
~~~

`Node` là nested type private phục vụ tổ chức mã, không có enclosing `IntStack` instance bắt buộc và không phải singleton. Nếu cần owner state, hãy cung cấp reference hoặc chọn inner đúng contract. Bài **Chọn lớp lồng hay lớp cấp cao nhất** xem xét tổng thể cohesion, access, testability và memory footprint; bài tiếp theo vẫn giữ chương trình chạy được dùng static Node.

## 55. Runnable: stack với private static Node

Lưu **`StaticNodeStackDemo.java`**:

```java
public final class StaticNodeStackDemo {
    private Node top;

    private static final class Node {
        final int value;
        final Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }

    public void push(int value) {
        top = new Node(value, top);
    }

    public int pop() {
        if (top == null) {
            throw new IllegalStateException("empty");
        }

        int value = top.value;
        top = top.next;
        return value;
    }

    public static void main(String[] args) {
        StaticNodeStackDemo stack =
                new StaticNodeStackDemo();

        stack.push(3);
        stack.push(5);

        System.out.println(stack.pop());
        System.out.println(stack.pop());
    }
}
```

```bash
javac -encoding UTF-8 StaticNodeStackDemo.java
java StaticNodeStackDemo
```

Stdout:

```text
5
3
```

`Node` được private trong source và static nested để tránh enclosing-instance dependency không cần thiết. Đây là một ứng dụng điển hình chứ không chỉ là cú pháp học thuộc.

## 56. Inner class thích hợp khi behavior luôn gắn với owner

**Inner member class** phù hợp khi behavior thực sự thuộc một owner object cụ thể, chẳng hạn cursor/iterator hay command thay đổi state của một document/counter instance:

~~~java
class Counter {
    private int value;
    class IncrementCommand {
        void execute() { value++; }
    }
}
~~~

Tạo command qua `counter.new IncrementCommand()` liên kết nó với đúng Counter; hai counters có thể có commands riêng dù cùng kiểu Inner. Nhưng callback giữ lâu có thể giữ owner lâu hơn ý định, nên phải xác định lifecycle. Cần helper chỉ dùng data snapshot? Cân nhắc static nested class với dependency tường minh. Phân tích lựa chọn chi tiết thuộc bài **Chọn lớp lồng hay lớp cấp cao nhất**.

## 57. Runnable: command gắn owner instance

Lưu **`InnerCommandDemo.java`**:

```java
public class InnerCommandDemo {
    private final String name;
    private int count;

    InnerCommandDemo(String name) {
        this.name = name;
    }

    class IncrementCommand implements Runnable {
        @Override
        public void run() {
            count++;
        }
    }

    int count() {
        return count;
    }

    public static void main(String[] args) {
        InnerCommandDemo a = new InnerCommandDemo("A");
        InnerCommandDemo b = new InnerCommandDemo("B");

        Runnable commandA = a.new IncrementCommand();
        Runnable commandB = b.new IncrementCommand();

        commandA.run();
        commandA.run();
        commandB.run();

        System.out.println(a.name + ":" + a.count());
        System.out.println(b.name + ":" + b.count());
    }
}
```

```bash
javac -encoding UTF-8 InnerCommandDemo.java
java InnerCommandDemo
```

Stdout:

```text
A:2
B:1
```

Ví dụ chạy tuần tự; nếu gọi commands đồng thời trên cùng Counter, cần bảo vệ `count` bằng synchronization/atomic semantics phù hợp.

## 58. `static` modifier và anonymous class không phải một cặp lựa chọn

Bạn có thể viết anonymous class trong **static method**:

```java
static Runnable make() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println("task");
        }
    };
}
```

Điều này hợp lệ và không làm anonymous class trở thành **static member nested class**. Nó vẫn là anonymous class, chỉ được khai báo/khởi tạo trong static context không có enclosing instance `this` của Outer.

Vì vậy hai chiều phân loại cần tách:
- **Hình thức khai báo**: named member, local, anonymous.
- **Ngữ cảnh instance/static**: có enclosing instance nào phù hợp không.

Một anonymous class trong instance method có thể truy cập Outer state; anonymous class trong static method không tự có Outer.this.

## 59. Định nghĩa scope khi anonymous/local class nằm trong nested static helper

Giả sử:

```java
class Outer {
    static class Nested {
        Runnable create() {
            int id = 7;

            return new Runnable() {
                @Override
                public void run() {
                    System.out.println(id);
                }
            };
        }
    }
}
```

Anonymous class capture `id` trong `Nested.create`. Nó không có Outer instance chỉ vì Nested là nested trong Outer. Nó có thể gắn với `Nested` enclosing instance ở context phù hợp.

Nếu muốn truy cập một Outer object, phải có một reference rõ ràng đến object ấy.

### Các tầng nesting rất sâu

Nhiều tầng local/anonymous/member types làm việc xác định enclosing instance phức tạp. Nếu người đọc cần liên tục hỏi “`this` đang là ai?”, cân nhắc refactor thành types có tên và dependencies tường minh.

## 60. Lỗi compiler phổ biến khi học bốn loại nested classes

| Code/hiện tượng | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `new Outer.Inner()` ở code ngoài | Member inner cần enclosing Outer instance | `outer.new Inner()` |
| `new Outer.Nested()` nhưng class Nested là private | Access không cho caller bên ngoài | Factory ở Outer hoặc đổi API hợp lý |
| Static nested đọc `Outer.this.x` | Không có implicit enclosing Outer instance | Truyền Outer reference hoặc dùng inner |
| Instance field `x` được đọc trực tiếp trong static nested method | Không có Outer receiver instance | `owner.x` |
| `new Inner()` từ static method của Outer | Không có `this` Outer ngầm định | `outer.new Inner()` |
| Local class name được dùng ngoài method | Tên type chỉ trong local scope | Return interface/superclass hoặc đưa ra member class |
| Captured variable bị gán lại | Không final/effectively final | Giữ variable không gán lại/đổi thiết kế |
| Dùng `this` trong anonymous mà tưởng là Outer | `this` là anonymous object | `Outer.this` nếu hợp lệ |
| Dùng `this` trong lambda tại static method | Static context không có instance `this` | Truyền receiver cụ thể |
| Anonymous implements interface nhưng không override abstract method | Implementation chưa đầy đủ | Override đủ abstract methods |
| Anonymous extends final class | Final cấm subclass | Chọn strategy/interface khác |
| `Runnable r = new Runnable(){ void helper(){} }; r.helper();` | Static type Runnable không có helper | Đưa method vào interface hoặc named type |
| Dùng `new Interface() { }` mà Interface có abstract method chưa implement | Anonymous class concrete chưa hoàn chỉnh | Implement method hoặc dùng lambda nếu functional |
| Tưởng local class làm member `Outer.Local` | Local type không phải member | Dùng member class nếu cần type public |
| Tưởng static nested không có access private Outer | Nesting cho access hợp lệ | Truyền outer object để đọc instance state |
| Anonymous/lambda giữ mutable state không đồng bộ | Effectively-final reference không khóa referent | Synchronized/atomics theo contract |
| Inner listener làm owner sống lâu | Enclosing-instance relation/lifecycle | Static helper, explicit capture, unregister |
| Giả định `Outer$1` là binary name cố định | Compiler-generated detail | Không đưa generated names vào business logic |
| Dùng lời dạy Java 8 “inner cấm static methods” cho Java 17 | Rules thay đổi theo version | Kiểm tra `--release 17` |
| Dùng quá nhiều anonymous blocks cho nghiệp vụ lớn | Logic khó đặt tên/test | Local/member/top-level named class |

## 61. Kỹ thuật giải bài dự đoán output với nested classes

Khi xem một đoạn code, thực hiện theo thứ tự:

1. **Xác định declaration location**: member, block local, hay expression anonymous?
2. **Nếu là member class**, có modifier `static` không?
3. **Nếu non-static member inner**, instance Outer được chỉ định ở đâu khi `new`?
4. **Nếu local/anonymous**, code được tạo trong static hay instance context?
5. **Xác định receiver `this`** trong từng body.
6. **Nếu cần instance Outer**, `Outer.this` có hợp lệ tại điểm đó không?
7. **Tên field bị shadow** bởi local/parameter/inner fields không?
8. **Captured local variable** có final/effectively final không?
9. **Static type của reference** có method được gọi không?
10. **Runtime implementation** có override theo superclass/interface không?
11. **Thứ tự tạo objects và initialize fields** như thế nào?
12. Có nguy cơ giữ reference đến outer/captured mutable object quá lâu không?
13. Khi in stdout, tránh dự đoán compiler-generated class names, identity hash hoặc scheduling nếu không được bảo đảm.

### Bảng nhận diện ngắn

| Biểu thức | Ý nghĩa |
| --- | --- |
| `new Outer.Nested()` | Tạo static nested member instance |
| `outer.new Inner()` | Tạo member inner instance gắn với `outer` |
| `new Inner()` trong Outer instance method | Dùng enclosing `this` ngầm định |
| `new Local()` trong method | Tạo local named class instance trong scope |
| `new Runnable() { ... }` | Tạo anonymous implementation |
| `new Base(args) { ... }` | Tạo anonymous subclass của Base |
| `Outer.this` | Enclosing instance của Outer khi tồn tại hợp lệ |
| `this` trong member inner method | Inner instance |
| `this` trong anonymous method | Anonymous instance |
| `this` trong lambda ở instance context | Enclosing instance theo lexical scope |

## 62. Bài tập 1 — Static nested có cần Outer object?

```java
class Outer {
    static class Nested {
        int value() {
            return 10;
        }
    }
}
```

**Hỏi:** `new Outer.Nested().value()` có cần `new Outer()` trước không?

**Đáp án:** Không. Static nested member class không cần implicit enclosing Outer instance. Kết quả là `10`.

## 63. Bài tập 2 — Khởi tạo inner

```java
class Outer {
    class Inner {
    }
}
```

**Hỏi:** cách tạo Inner từ bên ngoài Outer?

**Đáp án:**

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

`new Outer.Inner()` mà không có enclosing instance tương ứng là sai.

## 64. Bài tập 3 — Hai owners khác nhau

```java
class Counter {
    int count;

    class Reader {
        int get() {
            return count;
        }
    }
}
```

Hai Counter objects `a` và `b` có `count` khác nhau, tạo `a.new Reader()` và `b.new Reader()`. Hai Readers đọc cùng biến `count` không?

**Đáp án:** Không. Mỗi Reader gắn với một enclosing Counter instance riêng, nên cùng tên field nhưng state thuộc hai objects khác nhau.

## 65. Bài tập 4 — `this` và `Outer.this`

```java
class Outer {
    int value = 1;

    class Inner {
        int value = 2;

        int sum() {
            return this.value + Outer.this.value;
        }
    }
}
```

**Đáp án:** `sum()` trả `3` vì `this.value = 2` và `Outer.this.value = 1`.

## 66. Bài tập 5 — Static nested đọc private outer field

```java
class Outer {
    private int value = 7;

    static class Nested {
        int read(Outer owner) {
            return owner.value;
        }
    }
}
```

**Hỏi:** có biên dịch không?

**Đáp án:** Có. Static nested class có thể truy cập private instance field qua explicit `owner` reference nhờ nesting access. Không có `owner` thì không được đọc instance field như static.

## 67. Bài tập 6 — Local captured variable

```java
void run() {
    int factor = 2;

    class Local {
        int calculate() {
            return factor * 5;
        }
    }

    System.out.println(new Local().calculate());
}
```

**Đáp án:** In `10`. `factor` effectively final vì không bị gán lại.

## 68. Bài tập 7 — Biến local bị sửa

```java
void run() {
    int factor = 2;

    class Local {
        int calculate() {
            return factor * 5;
        }
    }

    factor = 3;
}
```

**Đáp án:** Không biên dịch vì factor được capture nhưng không effectively final. Sửa bằng cách giữ value cố định, truyền state vào một object với contract rõ, hoặc thiết kế flow khác.

## 69. Bài tập 8 — Capture reference đến mảng

```java
int[] number = {1};

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(number[0]);
    }
};

number[0] = 9;
task.run();
```

**Đáp án:** In `9`. Reference `number` vẫn effectively final, nhưng nội dung mảng mutable. Không phải capture deep snapshot.

## 70. Bài tập 9 — Local class dùng được ngoài method không?

Method tạo local class `Helper` và trả về interface `Runnable`. Caller có thể viết `new Helper()` ngoài method không?

**Đáp án:** Không. Tên `Helper` chỉ ở trong local scope. Runtime instance có thể sống tiếp qua reference interface `Runnable`.

## 71. Bài tập 10 — Anonymous subclass gọi superclass method

```java
class Base {
    String text() {
        return "A";
    }
}

Base value = new Base() {
    @Override
    String text() {
        return super.text() + "B";
    }
};

System.out.println(value.text());
```

**Đáp án:** `AB`. Anonymous class override method và dùng `super.text()` để gọi Base implementation.

## 72. Bài tập 11 — Anonymous implements nhiều abstract methods?

```java
interface Actions {
    void open();
    void close();
}
```

**Hỏi:** có thể tạo `new Actions() { ... }` chỉ override `open()` không?

**Đáp án:** Không nếu thiếu implementation hợp lệ của `close()`. Anonymous class được tạo phải concrete và thực hiện đầy đủ abstract method requirements. Lambda cũng không dùng được vì interface này không phải functional interface theo hai abstract methods.

## 73. Bài tập 12 — `this` trong anonymous class

Một anonymous `Runnable` trong instance method của Outer so sánh `this == Outer.this`.

**Đáp án:** `false` vì `this` trong anonymous instance method là anonymous object, còn `Outer.this` là enclosing Outer instance.

## 74. Bài tập 13 — `this` trong lambda

Một lambda `Runnable` trong instance method của Outer so sánh `this == Outer.this`.

**Đáp án:** `true` vì lambda dùng lexical `this` của enclosing instance context.

## 75. Bài tập 14 — Anonymous class có constructor tên riêng?

**Đáp án:** Không khai báo explicit constructor theo tên anonymous class vì nó không có source name. Có thể truyền arguments tới superclass constructor và có instance initializer block.

## 76. Bài tập 15 — Access helper không thuộc interface

```java
Runnable r = new Runnable() {
    void helper() {
        System.out.println("help");
    }

    @Override
    public void run() {
        helper();
    }
};
```

**Hỏi:** có gọi `r.helper()` từ bên ngoài được không?

**Đáp án:** Không. Static type `Runnable` không khai báo `helper`. Bên trong body anonymous class, `run` vẫn gọi helper được.

## 77. Bài tập 16 — Static nested class hay inner class cho Node?

Một `Tree` có hàng nghìn nodes, mỗi node chỉ chứa `int value` và child references, không bao giờ cần state của Tree object.

**Đáp án:** Thường chọn **private static nested Node**. Nó giữ namespace/encapsulation mà không gắn implicit enclosing Tree instance không cần thiết.

## 78. Bài tập 17 — Inner callback gây giữ owner object

Một UI screen đăng ký một member inner listener vào singleton event bus và quên unregister. Nguy cơ gì?

**Đáp án:** Listener có quan hệ với enclosing screen instance và nếu được giữ lâu có thể khiến screen không được GC khi mong đợi. Khắc phục bằng lifecycle unregister, capture tối thiểu, hoặc static helper/explicit dependencies nếu phù hợp.

## 79. Bài tập 18 — Generic outer và static nested class

```java
class Box<T> {
    static class Helper {
        // T read() { ... }
    }
}
```

**Đáp án:** Static nested Helper không được trực tiếp sử dụng type parameter `T` của Outer như instance member inner class. Helper có thể khai báo type parameter riêng, ví dụ `Helper<U>`, hoặc nhận một parameterized `Box<T>` theo context được khai báo phù hợp.

## 80. Bài tập 19 — Reflection phân biệt local/anonymous

**Hỏi:** hai methods reflection thường dùng để biết một `Class<?>` là local hay anonymous?

**Đáp án:** `clazz.isLocalClass()` và `clazz.isAnonymousClass()`. Với member nested class, dùng `isMemberClass()`; để biết modifier static của member class, kiểm tra `Modifier.isStatic(clazz.getModifiers())`.

## 81. Bài tập 20 — Quy tắc cũ của Java 8

Một tài liệu cũ khẳng định mọi inner class đều không được khai báo static method. Có áp dụng nguyên vẹn cho `javac --release 17` không?

**Đáp án:** Không. Java 17 cho phép những static declarations trong inner classes theo quy tắc hiện hành. Vẫn phải phân biệt class có static member với class được khai báo là static nested member; đó là hai thuộc tính khác nhau.

## 82. Bài tập 21 — Local class trong static method

```java
class Outer {
    int count;

    static void work() {
        class Local {
            int read() {
                // return count;
                return 0;
            }
        }
    }
}
```

**Đáp án:** Không thể đọc `count` trần như một enclosing Outer field vì local class được khai báo trong static method không có implicit Outer instance. Truyền explicit Outer reference vào Local hoặc chuyển ngữ cảnh thành instance method.

## 83. Bài tập 22 — Có nên anonymous class cho business rule dài?

Một anonymous `PaymentStrategy` có 200 dòng, nhiều instance fields, vài helper methods và cần dùng ở ba nơi.

**Đáp án:** Thường nên tách thành named class, static nested helper hoặc top-level implementation tùy ownership và khả năng test/reuse. Anonymous class chỉ gọn khi scope và behavior đủ nhỏ.

## 84. Bài tập 23 — Một class có thể nằm trong anonymous class?

**Đáp án:** Java cho phép các declarations/nesting phù hợp bên trong anonymous class body theo language rules. Nhưng việc lồng quá nhiều tầng có thể làm name scope/receiver phức tạp; không nên xem anonymous class là một “chỉ có đúng một method” bắt buộc.

## 85. Bài tập 24 — Type visibility và runtime object lifetime

Một local class `LocalTask` nằm trong method trả `Runnable`. Sau khi method return, object trả về có chết cùng stack frame không?

**Đáp án:** Không. Object có thể còn sống nếu reachable qua `Runnable` reference. Tên class bị giới hạn scope, không hạn chế lifetime instance theo cách đó.

## 86. Bài tập 25 — Chọn giải pháp

Tình huống:
1. Một `Builder` tạo immutable `Request`.
2. Một `Cursor` đọc/sửa đúng `Document` enclosing instance.
3. Một validator có tên, chỉ dùng trong một method.
4. Một `Runnable` ngắn, chỉ dùng một lần.

**Gợi ý:**
1. `static nested Builder`.
2. `inner Cursor` nếu coupling đến owner instance là chủ đích; hoặc static với explicit owner để rõ lifecycle.
3. `local class`.
4. `anonymous class`, hoặc lambda nếu chỉ cần functional behavior và không cần anonymous class semantics.

## 87. Checklist lựa chọn nested class

1. Type đang là **member**, **local**, hay **anonymous**?
2. Nó có cần **một enclosing instance** không?
3. Có cần đọc/sửa Outer instance fields mà không nhận tham số không?
4. Nếu không cần outer instance, đã cân nhắc **static nested** chưa?
5. Class có cần tên được reuse/test trực tiếp không?
6. Nếu logic chỉ trong một block nhưng khá dài, local named class có hợp lý không?
7. Nếu một implementation chỉ dùng một lần và nhỏ, anonymous class có đủ rõ không?
8. Nếu interface functional, lambda có thể đơn giản hơn không?
9. Có cần override nhiều methods hoặc subclass concrete class làm lambda không phù hợp không?
10. `this` trong mỗi nested scope trỏ object nào?
11. Có cần `Outer.this` hay một explicit owner field?
12. Có field/parameter shadowing dễ gây nhầm không?
13. Captured local variables đã **final/effectively final** chưa?
14. Captured references có trỏ mutable objects không?
15. Nếu callback chạy nhiều threads, captured state có thread-safe không?
16. Có gây giữ outer instance/tài nguyên lâu hơn lifecycle mong muốn không?
17. Visibility `public/private/protected` có phù hợp API không?
18. Có đang expose private nested type qua public signature không?
19. Cách tạo instance dùng `new Outer.Nested()` hay `outer.new Inner()` đã đúng chưa?
20. Có áp dụng **Java 17 rules** thay vì học theo hạn chế của Java 8 không?
21. Có anonymous class đang quá dài và khó test không?
22. Có code phụ thuộc compiler-generated `$1` class names không?
23. Với generic Outer, type parameter có đang bị dùng sai trong static nested class không?
24. Có nested interface/record/enum nào mặc nhiên static thay vì inner không?
25. Có nhu cầu domain khiến một top-level type rõ ràng hơn nesting không?
26. Ví dụ build dùng đúng tên public class/file name và language level không?
27. Output có tránh identity hash, class generated names và thread scheduling không được bảo đảm không?

## Ghi nhớ

- **Static nested member class** có tên, nằm trong enclosing type nhưng **không yêu cầu enclosing instance**; dùng `new Outer.Nested()`.
- **Non-static member inner class** có tên, gắn với **một Outer instance** khi được tạo; từ ngoài dùng `outer.new Inner()`.
- **Local class** có tên trong một **block/scope cục bộ**, có thể capture variables final/effectively final và có object sống lâu hơn method.
- **Anonymous class** không có tên khai báo trong source; dùng biểu thức `new Interface() { ... }` hoặc `new Base(args) { ... }` để tạo implementation/subclass ngay tại chỗ.
- `this` trong member inner/anonymous class là **instance của class đó**, còn `Outer.this` là enclosing instance phù hợp; `this` trong lambda mang **lexical enclosing context**.
- **Static nested không tự đọc Outer instance fields**, nhưng vẫn có thể truy cập private Outer state qua **reference được cấp tường minh**.
- **Local/anonymous capture** không biến mutable objects thành immutable. Final/effectively final giới hạn **gán lại local variable**, không cấm mutate referent.
- **Lambda không phải anonymous class** và không thay được mọi anonymous implementation, đặc biệt khi cần subclass concrete class hoặc class-scoped state/`super`.
- Trong Java 17, quy tắc static members của inner classes khác các hướng dẫn Java cũ; luôn kiểm tra đúng release.
- Chọn loại nested class theo **enclosing instance requirement, phạm vi tên, API visibility, khả năng reuse và lifecycle**, không chỉ theo độ ngắn của cú pháp.

Khi đọc một class lồng nhau, cách hiểu nhanh nhất là xác định **nơi class được khai báo**, **instance nào bị gắn/capture**, và **tên/members nào được nhìn thấy tại compile time**. Ba câu hỏi đó giải thích phần lớn sự khác nhau giữa static nested, member inner, local và anonymous classes.
