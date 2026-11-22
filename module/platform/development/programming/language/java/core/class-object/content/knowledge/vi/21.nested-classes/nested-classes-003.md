# Inner member class gắn với một đối tượng bao ngoài trong Java

**Inner member class** là một class được khai báo như member **không có modifier `static`** trong thân của outer class. Khi tạo một instance của inner member class, Java gắn nó với **một enclosing instance** — tức **đối tượng bao ngoài cụ thể**.

~~~java
class House {
    private final String address;

    House(String address) {
        this.address = address;
    }

    class Room {
        String where() {
            return House.this.address;
        }
    }
}
~~~

Trong trường hợp này, `House.Room` là **tên kiểu**. Một Room object được tạo qua `house.new Room()`; nó không tự xuất hiện khi khai báo class hay khi tạo House. Trong method của Room, `House.this` là reference đến chính House instance dùng lúc tạo Room. Đây là **quan hệ bao ngoài (enclosing)**, không phải quan hệ kế thừa.

Bài thuộc **Java Core — Class & Object / Lớp lồng nhau**, dùng **Java 17+**. Các chương trình Java độc lập có filename, lệnh `javac`/`java` và stdout; snippets không có đầy đủ context được ghi rõ là minh họa.

## 1. Mục tiêu học tập

- Phân biệt outer type, inner member type, outer object và inner object.
- Biết member class không `static` cần enclosing instance khi tạo.
- Sử dụng `outer.new Inner()` từ code bên ngoài outer class.
- Sử dụng `new Inner()` từ instance context của Outer.
- Phân biệt `this` của inner và `Outer.this` của outer.
- Hiểu inner class có thể truy cập private instance state của outer.
- Giải thích shadowing và cách chỉ rõ local/inner/outer fields.
- Phân biệt inner member với static nested, local và anonymous class.
- Hiểu static context không tự có outer instance.
- Biết quan hệ enclosing instance không đổi khi chuyển reference inner sang biến khác.
- Hiểu nhiều inner instances có thể dùng chung outer, hoặc cùng type nhưng khác outer.
- Dự đoán initialization/constructor order và null enclosing qualifier.
- Dùng `Outer<T>.Inner<U>` với generics.
- Hiểu Java 17 cho phép static declarations trong inner class.
- Hiểu runtime metadata không lưu một enclosing outer object cụ thể theo API Class.
- Biết lưu inner lâu dài có thể giữ outer reachable.
- Chọn inner class, static nested helper hoặc composition theo ownership/lifecycle.
- Viết các test kiểm chứng đúng association, state và invariants.

## 2. Tuyên bố class và tạo object là hai thao tác khác nhau

Xét:

~~~java
class Outer {
    class Inner {
    }
}
~~~

Khai báo này tạo **hai class types** có quan hệ lexical nesting. Nó không tự tạo Outer object hoặc Inner object. Để có objects:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

Sơ đồ khái niệm:

~~~text
 Outer instance #1
        ^
        |
 enclosing-instance association
        |
 Inner instance #1
~~~

Có **hai ordinary objects**. Inner **không phải** subclass của Outer và **không nằm vật lý trong bộ nhớ của Outer theo mô hình struct** được Java đảm bảo.

### Inner instance không có nghĩa là field

Chỉ khai báo `class Inner` bên trong Outer không tự tạo `outer.inner` field. Nếu Outer cần lưu một inner instance, phải khai báo field/method:

~~~java
class Outer {
    class Inner {
    }

    private final Inner stored = new Inner();

    Inner stored() {
        return stored;
    }
}
~~~

Ở đây field `stored` được khai báo và khởi tạo rõ; đó là quyết định riêng của author, không phải cơ chế tự động cho mọi inner member class.

## 3. Cú pháp tạo inner instance

Có ba mẫu quan trọng.

**Từ một instance method của Outer:**

~~~java
class Outer {
    class Inner {
    }

    Inner create() {
        return new Inner();
    }
}
~~~

Trong `create()`, `new Inner()` gắn với `this` của Outer.

**Từ code bên ngoài:**

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

`Outer.Inner` xác định kiểu ở phía khai báo, còn `outer.new Inner()` xác định enclosing **instance** ở phía tạo object.

**Tạo Outer và Inner trong một expression:**

~~~java
Outer.Inner inner = new Outer().new Inner();
~~~

Outer mới được tạo trước và dùng làm enclosing object của Inner mới.

### Cú pháp sai

~~~java
// Outer.Inner inner = new Outer.Inner(); // Không hợp lệ với non-static inner member class.
~~~

`new Outer.Inner()` thường là cú pháp cho `static nested class`, không phải non-static inner member class từ bên ngoài.

## 4. Chương trình đầu tiên: hai inner cùng outer

Tạo file **`InnerBasicsDemo.java`**:

~~~java
public class InnerBasicsDemo {
    static final class House {
        private final String address;

        House(String address) {
            this.address = address;
        }

        class Room {
            String where() {
                return address;
            }
        }

        Room createRoom() {
            return new Room();
        }
    }

    public static void main(String[] args) {
        House home = new House("Ha Noi");
        House.Room first = home.new Room();
        House.Room second = home.createRoom();

        System.out.println("first=" + first.where());
        System.out.println("second=" + second.where());
        System.out.println("different rooms=" + (first != second));
        System.out.println("same inner class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerBasicsDemo.java
java InnerBasicsDemo
~~~

Stdout:

~~~text
first=Ha Noi
second=Ha Noi
different rooms=true
same inner class=true
~~~

`first` và `second` là **hai Room objects**. Cả hai được tạo gắn với `home`, nên cùng đọc address của một House. Chúng cũng thuộc cùng runtime type `House.Room`.

## 5. `this` và `Outer.this`

Bên trong một instance method của Inner:

- `this` là **Inner object hiện tại**.
- `Outer.this` là **enclosing Outer object**.
- `Outer.this.field` chỉ rõ field của outer.
- `Outer.this.method()` chỉ rõ gọi method của outer.

Ví dụ:

~~~java
class Account {
    private final String id;

    Account(String id) {
        this.id = id;
    }

    class Audit {
        String id() {
            return Account.this.id;
        }

        boolean belongsTo(Account candidate) {
            return Account.this == candidate;
        }
    }
}
~~~

`Account.this` không chỉ Account object mới nhất, không truy cập một global Account và cũng không tự tạo Account. Nó chỉ đến **đúng enclosing instance** đã gắn với Audit khi Audit được tạo.

## 6. Chương trình chạy: identity của enclosing outer

Tạo **`OuterThisDemo.java`**:

~~~java
public class OuterThisDemo {
    static final class Account {
        private final String id;

        Account(String id) {
            this.id = id;
        }

        class Audit {
            boolean belongsTo(Account value) {
                return Account.this == value;
            }

            String description() {
                return "audit:" + Account.this.id;
            }
        }
    }

    public static void main(String[] args) {
        Account first = new Account("A");
        Account second = new Account("B");

        Account.Audit audit = first.new Audit();

        System.out.println(audit.description());
        System.out.println("first=" + audit.belongsTo(first));
        System.out.println("second=" + audit.belongsTo(second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
~~~

Stdout:

~~~text
audit:A
first=true
second=false
~~~

Inner Audit biết enclosing Account bằng `Account.this`, vì thế phân biệt first và second dù chúng cùng runtime class.

## 7. Enclosing instance association không đổi khi gán reference

~~~java
Outer first = new Outer();
Outer second = new Outer();
Outer.Inner inner = first.new Inner();
Outer.Inner alias = inner;
~~~

`alias = inner` chỉ tạo thêm alias tới **cùng Inner object**. Nó không đổi enclosing instance từ first sang second.

Nếu muốn inner được gắn với second, phải tạo **một Inner object mới**:

~~~java
Outer.Inner another = second.new Inner();
~~~

Java không có phép gán built-in để thay enclosing instance của một Inner đã xây dựng. Muốn thay association theo domain, thường phải thiết kế một field explicit/indirection khác; nó sẽ là một quan hệ dữ liệu riêng, không thay thế `Outer.this`.

## 8. Chương trình chạy: nhiều outer instances

Tạo **`MultipleOuterDemo.java`**:

~~~java
public class MultipleOuterDemo {
    static final class Shelf {
        private final String label;

        Shelf(String label) {
            this.label = label;
        }

        class Slot {
            String shelfLabel() {
                return label;
            }

            boolean belongsTo(Shelf candidate) {
                return Shelf.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Shelf left = new Shelf("LEFT");
        Shelf right = new Shelf("RIGHT");

        Shelf.Slot a = left.new Slot();
        Shelf.Slot b = left.new Slot();
        Shelf.Slot c = right.new Slot();

        System.out.println("a=" + a.shelfLabel());
        System.out.println("b=" + b.shelfLabel());
        System.out.println("c=" + c.shelfLabel());
        System.out.println("a==b=" + (a == b));
        System.out.println("a class==c class=" +
                (a.getClass() == c.getClass()));
        System.out.println("c belongs right=" + c.belongsTo(right));
        System.out.println("c belongs left=" + c.belongsTo(left));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultipleOuterDemo.java
java MultipleOuterDemo
~~~

Stdout:

~~~text
a=LEFT
b=LEFT
c=RIGHT
a==b=false
a class==c class=true
c belongs right=true
c belongs left=false
~~~

Hai Slots từ left có same enclosing outer instance. Slot từ right có khác enclosing outer instance. **Class object của cả ba Slots vẫn giống nhau** trong cùng class-loader context, vì enclosing **object identity** không tạo Java **class type** mới.

## 9. Inner member class có thể truy cập private outer members

Một member inner class được phép truy cập private fields/methods của outer theo Java nesting access rules.

~~~java
class Vault {
    private String secret = "KEY";

    class Inspector {
        String inspect() {
            return secret;
        }
    }
}
~~~

`secret` ở đây là field của **enclosing Vault**. Điều đó không biến field thành public cho arbitrary external classes.

### Outer cũng truy cập private members của inner được

~~~java
class Outer {
    class Inner {
        private int code = 7;
    }

    int read(Inner object) {
        return object.code;
    }
}
~~~

Outer cần reference tới Inner cụ thể để đọc instance field code. Compiler/JVM hỗ trợ nested private access; từ Java 11, khái niệm **nestmates** được dùng trong JVM để biểu diễn private access giữa các types cùng nest.

## 10. Chương trình chạy: private access hai chiều

Tạo **`PrivateAccessDemo.java`**:

~~~java
public class PrivateAccessDemo {
    static final class Vault {
        private final String secret;

        Vault(String secret) {
            this.secret = secret;
        }

        class Inspector {
            private final String tag;

            Inspector(String tag) {
                this.tag = tag;
            }

            String inspect() {
                return Vault.this.secret + ":" + tag;
            }
        }

        String tagOf(Inspector inspector) {
            return inspector.tag;
        }
    }

    public static void main(String[] args) {
        Vault vault = new Vault("KEY");
        Vault.Inspector inspector =
                vault.new Inspector("I1");

        System.out.println("inspection=" +
                inspector.inspect());
        System.out.println("tag=" + vault.tagOf(inspector));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
~~~

Stdout:

~~~text
inspection=KEY:I1
tag=I1
~~~

Inner đọc private outer state; outer method đọc private inner state. Cả hai access hợp lệ vì lexical nesting, không phải vì modifier `private` bị bỏ qua hoàn toàn.

## 11. Shadowing và cách ghi rõ scope

Nếu parameter, inner field và outer field cùng tên:

~~~java
class Outer {
    int number = 10;

    class Inner {
        int number = 20;

        void show(int number) {
            System.out.println(number);
            System.out.println(this.number);
            System.out.println(Outer.this.number);
        }
    }
}
~~~

Khi gọi `show(30)`:

- `number` là method parameter 30.
- `this.number` là Inner field 20.
- `Outer.this.number` là Outer field 10.

### Chương trình chạy

Tạo **`ShadowingDemo.java`**:

~~~java
public class ShadowingDemo {
    static final class Outer {
        private int number = 10;

        class Inner {
            private int number = 20;

            void print(int number) {
                System.out.println("parameter=" + number);
                System.out.println("inner=" + this.number);
                System.out.println("outer=" +
                        Outer.this.number);
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();
        inner.print(30);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShadowingDemo.java
java ShadowingDemo
~~~

Stdout:

~~~text
parameter=30
inner=20
outer=10
~~~

Đây là lý do `Outer.this` hữu ích ngay cả khi Java đôi khi cho truy cập outer member bằng simple name: nó làm mục tiêu của expression rõ ràng.

## 12. Gọi outer method từ inner method

~~~java
class Machine {
    private int total;

    private void add(int delta) {
        total += delta;
    }

    class Control {
        void click() {
            Machine.this.add(1);
        }
    }
}
~~~

Inner có thể gọi method private của enclosing outer. Nếu không có method trùng tên/che khuất, đôi khi viết `add(1)` cũng được; qualified `Machine.this.add(1)` rõ ràng hơn.

**Không nhầm với `super`:** `super` trong Inner liên quan **superclass của Inner**, không phải enclosing Outer. Nesting và inheritance là hai quan hệ khác nhau.

## 13. Từ static method cần explicit outer instance

Một static method không có receiver `Outer.this`. Vì vậy:

~~~java
class Outer {
    class Inner {
    }

    static void invalid() {
        // Inner inner = new Inner(); // Lỗi: thiếu enclosing Outer instance.
    }

    static Inner valid(Outer outer) {
        return outer.new Inner();
    }
}
~~~

Để tạo inner trong static context, truyền nhận một Outer object hoặc tạo Outer mới. Nếu helper không cần outer context, cân nhắc static nested class.

### Chương trình chạy

Tạo **`StaticContextDemo.java`**:

~~~java
public class StaticContextDemo {
    static final class Outer {
        private final int id;

        Outer(int id) {
            this.id = id;
        }

        class Inner {
            int ownerId() {
                return id;
            }
        }

        static Inner create(Outer source) {
            return source.new Inner();
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer(7);
        Outer.Inner first = outer.new Inner();
        Outer.Inner second = Outer.create(outer);

        System.out.println("first=" + first.ownerId());
        System.out.println("second=" + second.ownerId());
        System.out.println("different=" + (first != second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
first=7
second=7
different=true
~~~

## 14. Nếu outer qualifier null thì sao?

~~~java
Outer missing = null;
// Outer.Inner inner = missing.new Inner();
~~~

Đây có thể là biểu thức hợp lệ khi compile (nếu type/constructor accessible), nhưng tại runtime không có enclosing instance để cung cấp và sẽ ném `NullPointerException`.

Tạo **`NullOuterDemo.java`**:

~~~java
public class NullOuterDemo {
    static final class Outer {
        class Inner {
        }
    }

    public static void main(String[] args) {
        Outer outer = null;

        try {
            Outer.Inner inner = outer.new Inner();
            System.out.println(inner);
        } catch (NullPointerException ex) {
            System.out.println("missing outer");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullOuterDemo.java
java NullOuterDemo
~~~

Stdout:

~~~text
missing outer
~~~

Nếu API có nullable Outer parameter, validate trước. Non-static member inner class được tạo để có enclosing instance, không phải tùy ý thiếu owner.

## 15. Thứ tự tạo với `new Outer().new Inner()`

Outer instance được tạo trước rồi Inner instance. Có thể kiểm tra thứ tự constructor calls:

Tạo **`ConstructionOrderDemo.java`**:

~~~java
public class ConstructionOrderDemo {
    static final class Outer {
        Outer() {
            System.out.println("outer constructed");
        }

        class Inner {
            Inner() {
                System.out.println("inner constructed");
            }
        }
    }

    public static void main(String[] args) {
        Outer.Inner inner = new Outer().new Inner();
        System.out.println("created=" + (inner != null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructionOrderDemo.java
java ConstructionOrderDemo
~~~

Stdout:

~~~text
outer constructed
inner constructed
created=true
~~~

Một Outer không phải chỉ là “bước cú pháp” bị bỏ đi; nó là ordinary object được tạo. Nếu Outer constructor ném exception, Inner constructor không được hoàn thành.

## 16. Inner có constructor parameters và state của riêng mình

~~~java
class Department {
    private final String name;

    Department(String name) {
        this.name = name;
    }

    class Employee {
        private final int id;

        Employee(int id) {
            this.id = id;
        }

        String label() {
            return name + ":" + id;
        }
    }
}
~~~

Ở đây `Department.Employee` có id của riêng Employee. `name` đọc từ enclosing Department. Tạo:

~~~java
Department sales = new Department("Sales");
Department.Employee e = sales.new Employee(42);
~~~

Số `42` là explicit constructor argument cho Employee; enclosing Department instance được cung cấp qua `sales.new`, không phải một source-level constructor parameter do bạn khai báo.

### Chương trình chạy

Tạo **`InnerConstructorDemo.java`**:

~~~java
public class InnerConstructorDemo {
    static final class Department {
        private final String name;

        Department(String name) {
            this.name = name;
        }

        class Employee {
            private final int id;

            Employee(int id) {
                this.id = id;
            }

            String label() {
                return name + ":" + id;
            }
        }
    }

    public static void main(String[] args) {
        Department dev = new Department("Engineering");
        Department biz = new Department("Sales");

        Department.Employee first = dev.new Employee(42);
        Department.Employee second = biz.new Employee(42);

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerConstructorDemo.java
java InnerConstructorDemo
~~~

Stdout:

~~~text
Engineering:42
Sales:42
same class=true
~~~

## 17. Inner member khác static nested class

~~~java
class Outer {
    class MemberInner {
    }

    static class NestedStatic {
    }
}
~~~

| Thuộc tính | Non-static member inner | Static nested |
| --- | --- | --- |
| Có enclosing Outer instance khi tạo | Có | Không |
| Cách tạo bên ngoài | `outer.new MemberInner()` | `new Outer.NestedStatic()` |
| Có thể dùng `Outer.this` | Có, trong instance context của inner | Không |
| Trực tiếp đọc outer instance field | Có | Không, nếu không có explicit reference |
| Phù hợp helper độc lập outer | Thường không | Thường có |
| Cùng là nested types | Có | Có |

**Đừng nhầm:** static nested class được khai báo bên trong Outer nhưng **không gắn với một Outer object** khi tạo instance. Tên Outer trong `Outer.NestedStatic` chỉ là namespace/declaring type context.

### Chương trình chạy

Tạo **`StaticNestedVsInnerDemo.java`**:

~~~java
public class StaticNestedVsInnerDemo {
    static final class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class MemberInner {
            String show() {
                return "inner:" + name;
            }
        }

        static class Nested {
            String show() {
                return "nested";
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("A");

        Outer.MemberInner first = outer.new MemberInner();
        Outer.Nested second = new Outer.Nested();

        System.out.println(first.show());
        System.out.println(second.show());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticNestedVsInnerDemo.java
java StaticNestedVsInnerDemo
~~~

Stdout:

~~~text
inner:A
nested
~~~

## 18. Member inner khác local và anonymous class

**Member inner** là non-static member được khai báo trực tiếp trong class body:

~~~java
class Outer {
    class Member {
    }
}
~~~

**Local class** khai báo bên trong block/method:

~~~java
void run() {
    class Local {
    }
    Local local = new Local();
}
~~~

**Anonymous class** không khai báo tên class rõ, dùng expression:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("task");
    }
};
~~~

Local/anonymous classes có quy tắc capture local variables **final hoặc effectively final** khi thích hợp. Member inner class được khai báo ở class-body, không tự capture các local variables trong mọi methods của outer.

Một local class trong static context không có enclosing outer instance giống instance method. Vì vậy không được áp dụng mọi quy tắc member inner cho tất cả nested classes một cách máy móc.

## 19. Inner member không tự extends Outer

Đây là một khác biệt quan trọng:

~~~java
class Outer {
    class Inner {
    }
}
~~~

Inner **không extends Outer**. Nếu Inner không khai báo superclass, superclass bình thường là Object. Outer và Inner là **hai kiểu khác nhau**, hai ordinary objects khác nhau.

Do vậy `Outer.this` khác `super`:

- `this` → Inner instance.
- `Outer.this` → enclosing Outer instance.
- `super` → superclass context của Inner.

Một Outer object **không phải** instance của Inner và ngược lại. Java nesting không phải inheritance.

## 20. Generic outer và inner member

Khi Outer có type parameter:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Viewer {
        T read() {
            return value;
        }
    }
}
~~~

Kiểu declaration cho viewer dùng generic outer type:

~~~java
Box<String> box = new Box<>("Java");
Box<String>.Viewer viewer = box.new Viewer();
String result = viewer.read();
~~~

`Box<String>.Viewer` biểu diễn member type trong parameterized Outer type; nó **không mã hóa identity của một particular Box object**.

### Chương trình chạy

Tạo **`GenericInnerDemo.java`**:

~~~java
public class GenericInnerDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        class Viewer {
            T read() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        Box<Integer> numbers = new Box<>(17);

        Box<String>.Viewer textViewer = words.new Viewer();
        Box<Integer>.Viewer numberViewer = numbers.new Viewer();

        System.out.println("text=" + textViewer.read());
        System.out.println("number=" + numberViewer.read());
        System.out.println("same runtime class=" +
                (textViewer.getClass() ==
                        numberViewer.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericInnerDemo.java
java GenericInnerDemo
~~~

Stdout:

~~~text
text=Java
number=17
same runtime class=true
~~~

Hai viewers có generic outer type arguments khác nhau ở compile time, nhưng dùng cùng runtime member class metadata do type erasure.

## 21. Inner cũng có generic parameters của riêng nó

~~~java
class Holder<T> {
    private final T base;

    Holder(T base) {
        this.base = base;
    }

    class Pair<U> {
        private final U extra;

        Pair(U extra) {
            this.extra = extra;
        }

        String label() {
            return base + ":" + extra;
        }
    }
}
~~~

Khi sử dụng:

~~~java
Holder<String> holder = new Holder<>("A");
Holder<String>.Pair<Integer> pair =
        holder.new Pair<>(7);
~~~

T xuất phát từ Holder, U thuộc Pair. Outer instance vẫn chính là holder, không có chuyện inner type parameter U khiến inner gắn với outer mới.

### Chương trình chạy

Tạo **`GenericPairDemo.java`**:

~~~java
public class GenericPairDemo {
    static final class Holder<T> {
        private final T base;

        Holder(T base) {
            this.base = base;
        }

        class Pair<U> {
            private final U extra;

            Pair(U extra) {
                this.extra = extra;
            }

            String label() {
                return base + ":" + extra;
            }
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("A");
        Holder<String>.Pair<Integer> pair =
                holder.new Pair<>(7);

        System.out.println(pair.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericPairDemo.java
java GenericPairDemo
~~~

Stdout:

~~~text
A:7
~~~

## 22. Java 17 cho phép static declarations trong inner classes

Một tài liệu cũ có thể nói “inner class không được có static method/field, trừ constant variables”. **Quy tắc hạn chế này đã được thay đổi từ Java SE 16**. Với Java 17, static declarations trong inner classes được cho phép.

Việc Inner có static method **không làm Inner trở thành static nested class**. Inner instance vẫn cần enclosing outer khi tạo.

Tạo **`InnerStaticMemberDemo.java`**:

~~~java
public class InnerStaticMemberDemo {
    static final class Outer {
        private final int base;

        Outer(int base) {
            this.base = base;
        }

        class Inner {
            static final String KIND = "inner";

            static int doubleOf(int n) {
                return n * 2;
            }

            int plus(int n) {
                return base + n;
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer(10);
        Outer.Inner inner = outer.new Inner();

        System.out.println("kind=" + Outer.Inner.KIND);
        System.out.println("double=" +
                Outer.Inner.doubleOf(4));
        System.out.println("plus=" + inner.plus(3));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InnerStaticMemberDemo.java
java InnerStaticMemberDemo
~~~

Stdout:

~~~text
kind=inner
double=8
plus=13
~~~

**Static method không có inner/outer receiver** và không thể dùng `Outer.this`. Quy tắc Java 17 về static declarations không thay đổi quy tắc tạo instance `outer.new Inner()`.

## 23. Metadata Class khác enclosing instance

Class reflection cho biết declaration relationship:

- `Outer.Inner.class.getDeclaringClass()` → Class object cho Outer.
- `Outer.Inner.class.getEnclosingClass()` → Class object cho Outer.
- `Outer.Inner.class.isMemberClass()` → true.

Nhưng Class API không mặc định trả **một outer object cụ thể** của mỗi Inner instance. Hai Inner objects gắn với hai Outer instances vẫn có **cùng Class object** cho Inner.

### Chương trình chạy

Tạo **`InnerMetadataDemo.java`**:

~~~java
public class InnerMetadataDemo {
    static final class Outer {
        class Inner {
        }

        static class Nested {
        }
    }

    public static void main(String[] args) {
        Class<?> inner = Outer.Inner.class;
        Class<?> nested = Outer.Nested.class;

        System.out.println("inner member=" + inner.isMemberClass());
        System.out.println("inner declaring=" +
                (inner.getDeclaringClass() == Outer.class));
        System.out.println("inner enclosing=" +
                (inner.getEnclosingClass() == Outer.class));
        System.out.println("nested member=" + nested.isMemberClass());
        System.out.println("nested declaring=" +
                (nested.getDeclaringClass() == Outer.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerMetadataDemo.java
java InnerMetadataDemo
~~~

Stdout:

~~~text
inner member=true
inner declaring=true
inner enclosing=true
nested member=true
nested declaring=true
~~~

Cả Inner và Nested là member classes. Nhưng **chỉ instance của non-static Inner cần enclosing outer instance**.

## 24. Reflection constructor có thêm enclosing-instance parameter

Với inner class khai báo source constructor `Inner(int code)`, reflection thường nhìn thấy parameter outer instance bên cạnh `int`. JVM cần biết enclosing object khi tạo inner.

Tạo **`ReflectiveInnerDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

public class ReflectiveInnerDemo {
    static final class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        public class Inner {
            private final int code;

            public Inner(int code) {
                this.code = code;
            }

            String description() {
                return id + ":" + code;
            }
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Outer outer = new Outer("R");

        Constructor<Outer.Inner> ctor =
                Outer.Inner.class.getDeclaredConstructor(
                        Outer.class, int.class);

        Outer.Inner inner = ctor.newInstance(outer, 7);

        System.out.println("parameters=" +
                ctor.getParameterCount());
        System.out.println("description=" + inner.description());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectiveInnerDemo.java
java ReflectiveInnerDemo
~~~

Stdout:

~~~text
parameters=2
description=R:7
~~~

Source constructor nhận `int code`, còn reflection signature có enclosing Outer parameter. Chi tiết synthetic field/parameter names (ví dụ tên compiler có thể sinh ra) là implementation detail; **không dùng tên synthetic như một public contract**. Với Java code thông thường, cú pháp `outer.new Inner(7)` dễ đọc và an toàn hơn.

## 25. Inner object có thể kéo dài vòng đời outer object

Một inner callback được lưu trong long-lived registry/listener manager có thể giữ enclosing outer reachable:

~~~text
application registry
        |
        v
 inner callback object
        |
        v
 enclosing screen object
~~~

Nếu screen đáng ra được giải phóng khi cửa sổ đóng, nhưng handler vẫn nằm trong registry, bộ nhớ hoặc resource lớn của screen có thể bị giữ lâu.

Trong Java, enclosing-instance semantics tồn tại ở cấp ngôn ngữ, nhưng Java compiler có thể biểu diễn association bằng các implementation details khác nhau; không coi một synthetic field name là API ổn định. Khi inner thực sự dùng outer state, cần đặc biệt chú ý reachability.

### Cách kiểm soát

- Unregister handler đúng lifecycle.
- Không lưu inner vượt quá thời gian cần thiết.
- Dùng static nested helper khi không cần outer instance.
- Nếu cần dependency nhỏ, truyền explicit dependency thay vì capture toàn bộ owner.
- Nếu dùng static nested và vẫn giữ strong Outer reference, retention **vẫn có thể xảy ra**. Chỉ đổi keyword không tự khắc phục retention.

## 26. Callback inner class

Inner tiện vì callback có thể thao tác trực tiếp private state của enclosing owner.

Tạo **`InnerCallbackDemo.java`**:

~~~java
public class InnerCallbackDemo {
    static final class Screen {
        private int clicks;

        class ClickHandler implements Runnable {
            @Override
            public void run() {
                clicks++;
            }
        }

        Runnable handler() {
            return new ClickHandler();
        }

        int clicks() {
            return clicks;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen();
        Runnable handler = screen.handler();

        handler.run();
        handler.run();

        System.out.println("clicks=" + screen.clicks());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerCallbackDemo.java
java InnerCallbackDemo
~~~

Stdout:

~~~text
clicks=2
~~~

`ClickHandler` là Inner object dùng state của Screen. Nếu đăng ký handler vào một registry sống lâu, code cần thiết kế cleanup/unregister để tránh vô tình kéo dài lifetime Screen.

## 27. Inner truy cập private outer không đồng nghĩa được phá invariants

Vì Inner có thể sửa private outer state, designer phải bảo vệ domain invariants.

Ví dụ không tốt:

~~~java
class Wallet {
    private long cents;

    class Operator {
        void change(long delta) {
            cents += delta; // Có thể phá invariant không âm.
        }
    }
}
~~~

Thiết kế tốt hơn: Inner gọi private outer method **đã validate**:

Tạo **`InnerInvariantDemo.java`**:

~~~java
public class InnerInvariantDemo {
    static final class Wallet {
        private long cents;

        private void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative");
            }
            cents = Math.addExact(cents, amount);
        }

        long cents() {
            return cents;
        }

        class Operator {
            void deposit(long amount) {
                Wallet.this.add(amount);
            }
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet();
        Wallet.Operator operator = wallet.new Operator();

        operator.deposit(100);
        System.out.println("balance=" + wallet.cents());

        try {
            operator.deposit(-5);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + wallet.cents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerInvariantDemo.java
java InnerInvariantDemo
~~~

Stdout:

~~~text
balance=100
rejected=negative
after=100
~~~

Inner method gọi outer validated logic, tránh tự thao tác unsafe trên field. Private access cho inner là một **khả năng**, không phải bằng chứng state tự an toàn.

## 28. Khi nào nên dùng inner member class?

Nên cân nhắc khi:

- Inner behavior gắn **tự nhiên với một outer instance cụ thể**.
- Helper cần truy cập private state của owner, và owner quản lý lifecycle.
- Inner tồn tại dưới dạng implementation detail ít bị expose ra ngoài.
- Một owner có thể tạo nhiều inner helpers có state riêng.
- Không cần inner tồn tại độc lập owner.
- Association và reachability được hiểu rõ, có cleanup nếu callback được đăng ký ngoài owner.

Ví dụ: iterator gắn với collection instance, view/editor gắn với document instance, một listener được quản lý bởi UI component.

### Khi nào nên chọn cách khác?

Chọn **static nested class** hoặc top-level class khi helper không dùng outer state. Chọn composition/interface và explicit constructor dependency khi ownership cần rõ. Chọn immutable DTO nếu chỉ muốn cung cấp snapshot dữ liệu, không cần giữ owner sống theo inner.

Một API public expose `Outer.Inner` có thể gắn clients chặt với implementation nesting. Đừng expose inner type chỉ vì cú pháp tiện khi một interface độc lập sẽ phù hợp hơn.

## 29. Bảng so sánh bốn dạng nested constructs

| Dạng | Nơi khai báo | Enclosing instance |
| --- | --- | --- |
| Member inner class | Trong class body, không `static` | Cần outer instance |
| Static nested class | Trong class body, có `static` | Không cần outer instance |
| Local class | Trong block/method/constructor | Phụ thuộc enclosing context, có capture locals phù hợp |
| Anonymous class | Tại class instance creation expression | Phụ thuộc enclosing context |

Một class được khai báo bên trong một interface thường là **implicit static member type**, không có enclosing interface object như non-static inner class của ordinary outer class. Không gộp các trường hợp này thành một quy tắc “mọi class viết trong class khác đều cần outer object”.

## 30. Những sai lầm thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “Outer.Inner là một inner object.” | Đây là tên type; chưa có object. |
| “Tạo Outer luôn tự tạo Inner.” | Chỉ khi code chủ động tạo Inner. |
| “Inner extends Outer.” | Nesting khác inheritance. |
| “new Outer.Inner() luôn hợp lệ.” | Non-static inner từ bên ngoài cần outer.new Inner(). |
| “Static method có thể new Inner() không qualifier.” | Cần explicit outer instance. |
| “this bên trong Inner là Outer.” | this là inner; Outer.this là outer. |
| “Outer.this chọn Outer được tạo gần nhất.” | Nó là enclosing outer của chính inner hiện tại. |
| “Hai Inner từ hai Outer là hai Java class khác nhau.” | Cùng member runtime type, khác enclosing instances. |
| “Gán inner sang biến khác thay outer association.” | Không; chỉ alias reference. |
| “Inner không đọc được private Outer fields.” | Có, theo nesting access rules. |
| “Private outer fields không thể bị inner làm sai invariant.” | Inner có thể sửa, nên cần validate. |
| “Member inner và static nested giống hệt.” | Static nested không có enclosing outer instance. |
| “Inner class Java 17 bị cấm mọi static methods.” | Hạn chế cũ đã thay đổi từ Java SE 16. |
| “Reflection getDeclaringClass trả outer object.” | Trả Class metadata của outer type. |
| “Synthetic field this$0 có thể dùng như API.” | Không, implementation detail. |
| “Inner listener không thể giữ owner reachable.” | Có thể kéo dài lifetime owner. |
| “Chuyển sang static nested luôn hết memory retention.” | Nếu vẫn giữ explicit strong Outer ref thì không. |
| “Tên Inner gắn với Outer nghĩa inner không thể làm parameter.” | Inner instance vẫn là ordinary reference value. |

## 31. Bài tập 1 — Đếm instances

~~~java
class Car {
    class Wheel {}
}

Car car = new Car();
Car.Wheel front = car.new Wheel();
Car.Wheel rear = car.new Wheel();
~~~

**Đáp án:** Một Car instance và hai Wheel instances, cùng enclosing Car. `front != rear` true. Member class declaration không tự tạo Wheel objects.

## 32. Bài tập 2 — Sửa cú pháp

~~~java
class Outer {
    class Inner {}
}
// Outer.Inner inner = new Outer.Inner();
~~~

**Đáp án:** Với non-static inner cần:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

Nếu Inner thực sự không cần Outer instance, khai báo `static class Inner` rồi dùng `new Outer.Inner()`.

## 33. Bài tập 3 — Scope và shadowing

Outer field `int number=10`, Inner field `int number=20`, method parameter `int number=30`.

**Đáp án:** `number` là 30; `this.number` là 20; `Outer.this.number` là 10. Dùng qualification để nói rõ field thuộc owner nào.

## 34. Bài tập 4 — Một class type, nhiều owner objects

Hai outer objects a và b; hai inner objects `a.new Inner()` và `b.new Inner()`.

**Đáp án:** Inner objects gắn owner khác nhau, dù cùng runtime inner class type. `==` giữa hai inner references false nếu chúng được tạo bằng hai new expressions riêng.

## 35. Bài tập 5 — Static context và null

Trong static method có `Outer outer = null; Outer.Inner item = outer.new Inner();`, kết quả?

**Đáp án:** Khi expression chạy, `NullPointerException`. Nếu viết `new Inner()` không qualifier trong static method của Outer, thường lỗi compile vì thiếu enclosing instance. Hai lỗi thuộc hai giai đoạn khác nhau.

## 36. Bài tập 6 — Reflection

`Outer.Inner.class.getDeclaringClass()` trả cái gì?

**Đáp án:** Class object đại diện Outer **type**, không trả specific outer instance. Nếu client cần owner object, có thể thiết kế method trên Inner dùng `Outer.this` để trả owner theo access contract.

## 37. Bài tập 7 — Memory retention

Một Screen tạo ClickHandler inner, đăng ký nó vào global registry, không unregister khi Screen đóng. Tại sao có vấn đề?

**Đáp án:** Registry giữ handler; handler có enclosing association dùng state Screen, nên có thể giữ Screen reachable. Cần lifecycle unregister, hoặc thiết kế callback/dependency phù hợp. Static nested với strong Screen field vẫn có thể giữ owner.

## 38. Bài tập 8 — Java 17 static declarations

`class Inner { static int twice(int n) { return n*2; } }` khai báo trong class Outer không static có hợp lệ ở Java 17 không?

**Đáp án:** Có, kể từ Java SE 16 đã cho phép static declarations trong inner classes. Nhưng Inner instance vẫn cần enclosing outer, và method static không có `Outer.this` receiver.

## 39. Checklist cuối bài

- [ ] Tôi biết member inner class là non-static member nested class.
- [ ] Tôi phân biệt type declaration với object creation.
- [ ] Tôi hiểu inner instance có enclosing outer instance.
- [ ] Tôi biết Outer object và Inner object là hai ordinary objects riêng.
- [ ] Tôi biết outer.new Inner() từ code bên ngoài.
- [ ] Tôi biết new Inner() trong Outer instance method.
- [ ] Tôi hiểu new Outer().new Inner() khởi tạo outer trước inner.
- [ ] Tôi không dùng new Outer.Inner() cho non-static inner từ bên ngoài.
- [ ] Tôi biết static context cần explicit outer object.
- [ ] Tôi biết null outer qualifier gây NullPointerException.
- [ ] Tôi phân biệt this và Outer.this.
- [ ] Tôi hiểu parameter/inner/outer field shadowing.
- [ ] Tôi biết inner truy cập được private outer members.
- [ ] Tôi biết outer có thể truy cập private inner members theo nesting rules.
- [ ] Tôi biết nesting không phải inheritance.
- [ ] Tôi biết một Outer có thể tạo nhiều Inner instances.
- [ ] Tôi biết nhiều Outer objects có thể tạo Inner cùng runtime class type.
- [ ] Tôi không nghĩ gán lại inner reference đổi enclosing association.
- [ ] Tôi phân biệt static nested, local và anonymous class.
- [ ] Tôi biết generic Outer<T>.Inner<U> type usage.
- [ ] Tôi biết inner Java 17 có thể khai báo static members.
- [ ] Tôi biết Class.getDeclaringClass() trả type metadata.
- [ ] Tôi biết reflection constructor có enclosing outer parameter.
- [ ] Tôi không dựa vào synthetic field names như API.
- [ ] Tôi hiểu callback inner có thể kéo dài outer reachability.
- [ ] Tôi biết cleanup/unregister trong lifecycle phù hợp.
- [ ] Tôi không expose outer owner vô tình qua public API.
- [ ] Tôi bảo vệ outer invariants dù inner có private access.
- [ ] Tôi chọn static nested/helper độc lập nếu không cần outer.
- [ ] Tôi đọc và giải thích được stdout các ví dụ Java 17+.

**Kết luận:** Một **inner member class** không static được khai báo trong Outer **có thể tạo nhiều inner objects**, và **mỗi inner object gắn với đúng một enclosing Outer instance** tại lúc tạo. Cú pháp cốt lõi là `outer.new Inner()`; bên trong Inner, `this` đại diện inner còn `Outer.this` đại diện owner. Đây là nesting/enclosing relationship, không phải inheritance, không tự tạo inner khi outer được tạo và không mã hóa outer object identity vào inner type. Dùng inner khi helper thực sự phụ thuộc owner; chọn static nested class/composition khi không cần, và luôn quản lý invariant cùng callback lifecycle.
