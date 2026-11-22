# `extends`, lớp cha, lớp con và quan hệ kiểu con trong Java

## 1. Mục tiêu và ý tưởng cốt lõi

Trong Java, **kế thừa lớp (*class inheritance*)** cho phép một class mới **mở rộng (*extends*)** một class đã có, nhận những thành viên có thể kế thừa và bổ sung hoặc ghi đè hành vi theo quy tắc của ngôn ngữ. Class được mở rộng gọi là **lớp cha (*superclass*)**; class khai báo `extends` gọi là **lớp con (*subclass*)**.

Từ khóa `extends` không chỉ phục vụ “tái sử dụng vài dòng code”. Nó còn thiết lập **quan hệ kiểu con (*subtype relationship*)**: trong những ngữ cảnh hợp lệ, một đối tượng lớp con có thể được sử dụng qua tham chiếu mang kiểu lớp cha. Đây là nền tảng cho **đa hình (*polymorphism*)** và thiết kế API có thể chấp nhận nhiều kiểu object cùng tuân theo một hợp đồng.

Ví dụ tối giản:

~~~java
class Animal {
    void eat() {
        System.out.println("Eating");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("Woof");
    }
}
~~~

Đây là **hai class minh họa**, chưa có `main` để chạy độc lập.

- `Animal` là superclass trực tiếp của `Dog`.
- `Dog` là subclass của `Animal`.
- `Dog` có thể dùng instance method `eat()` được kế thừa từ `Animal`.
- `Dog` khai báo thêm method `bark()`.
- Một biến kiểu `Animal` có thể tham chiếu tới một `Dog` object: `Animal animal = new Dog();`.
- Chiều ngược lại **không tự động hợp lệ**: không phải mọi Animal đều là Dog.

**Câu hỏi thiết kế cần trả lời trước khi viết `extends`:** *“Mọi instance của class con có thật sự có thể được sử dụng như một instance của class cha theo hợp đồng đã công bố hay không?”* Nếu câu trả lời là không, nhiều khả năng bạn cần **composition**, interface, hoặc một mô hình khác.

Bài Knowledge README này dành cho **Java 17+**. Nội dung giải thích quan hệ is-a, cú pháp `extends`, kế thừa members, truy cập, constructor và khởi tạo, subtype/upcasting/downcasting, kiểu tĩnh và kiểu runtime, overriding và dynamic dispatch, hiding, abstract/final/sealed classes, interface, generics, records, lỗi thiết kế và bài tập. Các chương trình chạy độc lập ghi tệp, lệnh `javac`/`java` và stdout.

## 2. `extends` viết như thế nào?

Cú pháp thường gặp:

~~~java
class Parent {
}

class Child extends Parent {
}
~~~

Class `Child` khai báo **một direct superclass** là `Parent`. Nó có thể mở rộng bằng methods, fields, constructors và nested declarations riêng.

Một chuỗi kế thừa:

~~~java
class LivingThing {
}

class Animal extends LivingThing {
}

class Dog extends Animal {
}
~~~

Có những quan hệ:

- `Animal` là **direct subclass** của `LivingThing`.
- `Dog` là **direct subclass** của `Animal`.
- `Dog` là **indirect subclass** của `LivingThing`.
- `LivingThing` là superclass trực tiếp/gián tiếp tương ứng.
- `Dog` là subtype của `Animal` và `LivingThing` theo quan hệ class inheritance.

### 2.1. Java chỉ cho phép một direct superclass dạng class

Java **không hỗ trợ multiple inheritance of classes**:

~~~java
class A {
}

class B {
}

// class C extends A, B { } // Không hợp lệ trong Java
~~~

Một class có nhiều hành vi cộng tác có thể **implements nhiều interfaces** và sử dụng composition thay vì cố extends nhiều classes:

~~~java
interface Printable {
    void print();
}

interface Saveable {
    void save();
}

class Document implements Printable, Saveable {
    @Override
    public void print() {
        System.out.println("Print");
    }

    @Override
    public void save() {
        System.out.println("Save");
    }
}
~~~

`Document` là **subtype** của cả `Printable` và `Saveable` dù không trực tiếp `extends` hai class. Interface là một quan hệ kiểu khác với class superclass; bài này phân biệt kỹ ở phần sau.

### 2.2. Nếu không ghi `extends`

Một class thông thường không khai báo superclass tường minh sẽ có `java.lang.Object` là direct superclass theo quy tắc Java:

~~~java
class Box {
}
~~~

Về mặt quan hệ lớp, `Box` trực tiếp kế thừa `Object`. Bản thân `Object` là class gốc của hệ thống class thông thường. Không được viết `class X extends String` vì `String` là `final`; cũng không thể kế thừa một `final` class tự định nghĩa.

### 2.3. Quan hệ kiểu và quan hệ object không giống nhau

`Dog extends Animal` là **quan hệ giữa hai class/types**. `Dog ownerDog = new Dog();` tạo một **object** runtime type Dog; object đó có phần state/method được định nghĩa theo superclass chain và các khai báo Dog.

Không phải có hai objects riêng “Animal object bên trong Dog object” theo ngữ nghĩa Java. Constructor Animal và constructor Dog cùng tham gia khởi tạo **một Dog object**. Field hiding có thể tạo hai fields khác nhau trong cùng object, nhưng không biến nó thành hai objects độc lập.

## 3. “Is-a” và khả năng thay thế

Quan hệ `extends` thường được giải thích là **“Dog is an Animal”**: mọi Dog object cũng có thể được dùng như một Animal object khi chương trình chỉ cần hợp đồng của Animal.

~~~java
void feed(Animal animal) {
    animal.eat();
}
~~~

Đây là **đoạn method minh họa**, đặt trong một class thích hợp. Caller có thể truyền `new Dog()` cho parameter `Animal animal`:

~~~java
feed(new Dog());
~~~

Đó là biểu hiện của **subtype polymorphism**: cùng lời gọi `feed(Animal)` nhận nhiều object subtypes.

**Nhưng compiler chỉ kiểm tra quan hệ kiểu và các quy tắc ngôn ngữ**. Nó không tự biết một subclass có thực sự duy trì **ngữ nghĩa nghiệp vụ** mà caller mong đợi từ superclass hay không. Vì vậy, “biên dịch được” chưa đồng nghĩa với “thiết kế đúng”.

### 3.1. Liskov Substitution Principle (LSP)

Một cách hiểu thực dụng: nếu code dùng `Parent` theo hợp đồng của Parent, thay một Parent object bằng Child object nên giữ các kỳ vọng quan trọng của hợp đồng đó.

Ví dụ về hợp đồng:

- Nếu superclass `withdraw(amount)` cho phép rút bất kỳ số tiền hợp lệ trong số dư, subclass không nên lén siết điều kiện vô lý làm mọi caller trước đây hỏng.
- Nếu superclass hứa trạng thái luôn không âm, subclass không được phá invariant ấy.
- Nếu superclass method cam kết một kết quả tương ứng với input, override cần duy trì postcondition thích hợp.
- Nếu public method có side effects được mô tả rõ, subclass không nên âm thầm bỏ hoặc thay bằng tác động mâu thuẫn.

LSP là **nguyên tắc thiết kế**, không phải một Java compiler rule kiểm tra hết precondition/postcondition.

### 3.2. Quan hệ has-a không nên nhầm is-a

Một `Car` **có** `Engine`; không phải Car **là** Engine. Trong thiết kế như thế, `Car extends Engine` thường sai mô hình. Thay bằng composition:

~~~java
interface Engine {
    void start();
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        engine.start();
    }
}
~~~

Kế thừa thể hiện subtype contract, composition thể hiện object **dùng/có** một thành phần. Không dùng `extends` chỉ vì muốn gọi lại một helper method có sẵn.

## 4. Bảng thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Superclass | Class được một class khác trực tiếp/gián tiếp mở rộng |
| Direct superclass | Class xuất hiện ngay sau `extends` của class con |
| Subclass | Class mở rộng một superclass |
| Subtype | Kiểu có thể dùng trong một số ngữ cảnh yêu cầu supertype theo quy tắc Java |
| Supertype | Kiểu rộng hơn, chẳng hạn superclass hoặc superinterface |
| Inheritance | Cơ chế class/interface kế thừa members và thiết lập quan hệ kiểu |
| Overriding | Subclass cung cấp implementation instance method cho method được kế thừa thích hợp |
| Overloading | Các methods cùng tên nhưng khác parameter lists, không phụ thuộc bắt buộc vào inheritance |
| Upcasting | Dùng reference/biểu thức subtype dưới kiểu supertype |
| Downcasting | Ép một reference kiểu rộng sang kiểu con, cần điều kiện runtime hợp lệ |
| Dynamic dispatch | Chọn implementation của overridable instance method theo runtime class receiver |
| Field hiding | Khai báo field cùng tên che field được kế thừa |
| Static method hiding | Static method subclass che static method superclass phù hợp; không override |
| Composition | Kết hợp objects theo has-a/uses-a thay vì subtype inheritance |

Trong các ví dụ, từ “kiểu tĩnh” (*compile-time type*) chỉ kiểu compiler biết ở một biểu thức hoặc biến. “Kiểu runtime” là class thực tế của object ở thời điểm chạy. Hai khái niệm quyết định hai phần khác nhau của cơ chế đa hình.

## 5. Kế thừa những thành viên nào?

Một subclass có thể có quyền dùng các **instance methods**, **fields** và **static members** thích hợp của superclass theo quy tắc inheritance và access control. Nhưng “kế thừa” **không có nghĩa** mọi khai báo trong superclass đều được copy lại thành khai báo riêng trong subclass.

Ví dụ:

~~~java
class Account {
    protected long balance;

    public long getBalance() {
        return balance;
    }

    protected void deposit(long amount) {
        balance += amount;
    }

    private void audit(String event) {
        System.out.println(event);
    }
}

class SavingsAccount extends Account {
    void earnBonus() {
        deposit(5);
    }
}
~~~

Đây là đoạn minh họa cú pháp, không phải thiết kế tài khoản production: `deposit` chưa có validation hoặc overflow check.

`SavingsAccount` có thể dùng những members thích hợp của `Account`, ví dụ `getBalance()` và `deposit(...)`. Nhưng `audit(String)` là **private**, không được subclass kế thừa thành method nó có thể gọi trực tiếp.

### 5.1. Visibility của thành viên superclass

| Modifier | Ý nghĩa truy cập tiêu biểu |
| --- | --- |
| `public` | Member có thể được truy cập ở nơi class/member và module visibility cho phép |
| `protected` | Cho phép truy cập trong cùng package và trong subclasses theo các quy tắc đặc biệt |
| Không modifier (package-private) | Truy cập trong cùng package |
| `private` | Chỉ trong phạm vi Java cho phép của declaring class/nest; không được kế thừa như accessible member ở subclass |

Cẩn thận: protected ở **khác package** không tương đương public. Trong subclass ở package khác, truy cập protected instance member qua một **biểu thức receiver bất kỳ kiểu superclass** có thể bị compiler từ chối. Phải tuân thủ quy tắc receiver type và context; cách an toàn là dùng member trên `this`/receiver subclass phù hợp khi hợp đồng cho phép.

### 5.2. Private field vẫn tồn tại trong phần superclass state của object

Nếu một superclass có `private int secret`, không có nghĩa field ấy bị xóa khỏi object subclass. Class con chỉ **không được truy cập trực tiếp theo access rules**. Superclass methods vẫn có thể dùng field ấy trên cùng object.

~~~java
class Base {
    private int count = 3;

    public int count() {
        return count;
    }
}

class Derived extends Base {
    int readCount() {
        return count(); // Dùng public method inherited
    }
}
~~~

`Derived` có thể đọc kết quả qua `count()` mà không cần hoặc không được dùng `this.count` trực tiếp.

### 5.3. Constructors **không được kế thừa**

`Child extends Parent` **không** làm constructors của Parent trở thành constructors của Child. Để khởi tạo phần superclass, constructor Child **gọi** constructor của Parent bằng `super(...)` (tường minh hoặc ngầm định), nhưng caller không thể xem `Parent(int)` là `Child(int)` tự nhiên chỉ vì Child extends Parent.

### 5.4. Static methods/fields cũng có các quy tắc kế thừa, nhưng không có overriding instance

Một subclass có thể truy cập inherited static field/method khi hợp lệ. Tuy nhiên, static method **không dispatch theo runtime object**. Nếu subclass khai báo static method cùng signature tương ứng, nó **hide**, không override method superclass. Field cùng tên cũng có thể hide field khác. Sẽ có chương trình riêng minh họa.

## 6. Chương trình hoàn chỉnh 1: subclass là subtype và overriding tạo đa hình

Tạo tệp **`AnimalHierarchyDemo.java`**:

~~~java
import java.util.List;

public class AnimalHierarchyDemo {
    static abstract class Animal {
        private final String name;

        protected Animal(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            this.name = name;
        }

        public final String name() {
            return name;
        }

        public abstract String sound();

        public String describe() {
            return name() + " says " + sound();
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "Woof";
        }

        public void fetch() {
            System.out.println(name() + " fetches");
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "Meow";
        }
    }

    static void introduce(Animal animal) {
        System.out.println(animal.describe());
    }

    public static void main(String[] args) {
        Dog dog = new Dog("Milo");
        Cat cat = new Cat("Luna");

        Animal first = dog; // Upcast, không tạo object mới
        Animal second = cat;

        introduce(first);
        introduce(second);

        List<Animal> animals = List.of(first, second);
        for (Animal animal : animals) {
            System.out.println(animal.name() + ":" + animal.sound());
        }

        dog.fetch();

        System.out.println("Dog is Animal = " + (dog instanceof Animal));
        System.out.println("Same object = " + (first == dog));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 AnimalHierarchyDemo.java
java AnimalHierarchyDemo
~~~

**Stdout chính xác:**

~~~text
Milo says Woof
Luna says Meow
Milo:Woof
Luna:Meow
Milo fetches
Dog is Animal = true
Same object = true
~~~

**Phân tích:**

1. `Animal` là **abstract superclass**, có field private `name` và public method `name()`. Constructor Animal kiểm tra tên.
2. `Dog extends Animal` và `Cat extends Animal`, nên Dog và Cat là **subtypes** của Animal.
3. Mỗi subclass gọi `super(name)` trong constructor để Parent khởi tạo field thuộc phần superclass.
4. Method `sound()` là abstract ở Animal; Dog/Cat bắt buộc hiện thực vì chúng là concrete classes.
5. `Animal first = dog` là **upcast** hợp lệ, không clone Dog object, không gọi constructor mới. Identity vẫn là cùng một Dog object.
6. `introduce(Animal animal)` gọi `animal.describe()`. Bên trong `describe()`, lời gọi `sound()` tiếp tục dispatch theo runtime object: Dog → Woof, Cat → Meow.
7. Vòng lặp trên `List<Animal>` xử lý hai concrete runtime types bằng cùng một contract.
8. `dog.fetch()` hợp lệ vì biến `dog` có compile-time type Dog. `first.fetch()` sẽ **không biên dịch** nếu không cast hoặc narrow type, vì compiler chỉ thấy Animal API ở `first`.
9. `dog instanceof Animal` là true; `first == dog` là true vì upcast không tạo object mới.

Đây là ví dụ của **polymorphism dựa trên subtype và overriding**, không phải một bộ `if (type == Dog)` hoặc `if (type == Cat)` được viết tay cho từng class.

## 7. Kiểu tĩnh và kiểu runtime

Xét:

~~~java
Animal pet = new Dog("Milo");
~~~

Có hai sự thật đồng thời:

- **Compile-time type của `pet`:** `Animal`.
- **Runtime class của object mà `pet` tham chiếu:** `Dog`.

Khi compiler phân tích `pet.someMethod()`, nó kiểm tra method có thể gọi qua **kiểu tĩnh Animal** không. Nếu hợp lệ và là overridable instance method, runtime dispatch có thể chọn implementation của **Dog**.

~~~java
pet.sound(); // Hợp lệ nếu Animal khai báo sound()
~~~

~~~java
// pet.fetch(); // Lỗi compile: Animal không có fetch()
~~~

Đây là fragments dựa trên các class ở ví dụ trước. Runtime object là Dog **không tự làm compiler chấp nhận method chỉ có ở Dog** trên một biến khai báo Animal.

### 7.1. Upcasting là gán tham chiếu, không biến object thành superclass object khác

~~~java
Dog dog = new Dog("Milo");
Animal animal = dog;
~~~

`animal` và `dog` tham chiếu tới **một object**. Upcasting không tạo object Animal riêng, không bỏ bớt phần Dog state, và không thay runtime class của object.

Nhưng API có thể gọi **qua biến animal** bị giới hạn bởi **kiểu tĩnh**. Đây là một chủ đích an toàn: code chấp nhận Animal chỉ nên dựa vào contract Animal, không tự cho rằng mọi Animal là Dog.

### 7.2. Mọi subclass là một instance của superclass, nhưng không ngược lại

Nếu Parent là concrete:

~~~java
class Vehicle {
}

class Car extends Vehicle {
}
~~~

`Vehicle v = new Car();` hợp lệ. `Car c = new Vehicle();` không hợp lệ vì một Vehicle object không nhất thiết là Car. Dùng cast tường minh cũng không biến object đang là Vehicle thành Car.

### 7.3. `null` có thể gán cho reference subtype/supertype

~~~java
Animal animal = null;
Dog dog = null;
~~~

Hai phép gán là hợp lệ cho reference types. Nhưng `animal.sound()` khi `animal == null` sẽ ném `NullPointerException`. Quan hệ subtype không loại bỏ quy tắc null dereference.

`null instanceof Dog` cho kết quả **false**. Dùng `instanceof` với pattern matching có thể giúp kiểm tra đối tượng trước khi gọi subtype-only API.

## 8. Overriding: lớp con thay implementation, không thay contract tùy tiện

Một subclass override một **instance method** khi khai báo method phù hợp với signature và các quy tắc Java:

~~~java
class Parent {
    String label() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String label() {
        return "Child";
    }
}
~~~

Với `Parent p = new Child();`, gọi `p.label()` có thể trả `"Child"` do dynamic dispatch.

### 8.1. `@Override` nên được sử dụng

`@Override` yêu cầu compiler kiểm tra rằng method thực sự override/implement một method phù hợp. Nó giúp phát hiện lỗi đánh máy:

~~~java
class Base {
    void execute() {
    }
}

class Derived extends Base {
    // @Override
    // void excute() { } // Sai chính tả, compiler sẽ báo
}
~~~

Không bắt buộc về cú pháp đối với mọi override, nhưng thường là thói quen hữu ích để phát hiện sai signature khi sửa API superclass.

### 8.2. Một số điều kiện quan trọng khi override

Khi subclass override instance method:

- Không được **giảm quyền truy cập** của method override, ví dụ từ `public` thành `protected`.
- Return type phải phù hợp; Java cho phép **covariant return types** với reference types.
- Với **checked exceptions**, overriding method không được mở rộng thêm checked exceptions trái quy tắc của method bị override.
- Không được override `final` instance method.
- Không được dùng một static method để override một instance method cùng signature.
- `private` method của superclass không được subclass override như một inherited method bình thường.
- Overload với parameter list khác **không phải** override.
- Cần tuân thủ contract nghiệp vụ (LSP), ngoài những quy tắc compiler kiểm tra được.

Ví dụ covariant return:

~~~java
class Food {
}

class Bone extends Food {
}

class Animal {
    Food favoriteFood() {
        return new Food();
    }
}

class Dog extends Animal {
    @Override
    Bone favoriteFood() {
        return new Bone();
    }
}
~~~

Đây là đoạn minh họa. Return type `Bone` là subtype của `Food`, nên Java cho phép override trả một kiểu cụ thể hơn. Compiler có thể tạo *bridge methods* trong những trường hợp generics/covariant cần bảo đảm compatibility; đó là cơ chế compiler, không phải yêu cầu viết tay ở đây.

### 8.3. Instance dispatch có thể tiếp tục từ code superclass

~~~java
class Parent {
    String describe() {
        return "P:" + value();
    }

    String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    String value() {
        return "child";
    }
}
~~~

Với `new Child().describe()`, implementation `Parent.describe()` có thể chạy (nếu không override describe), nhưng lời gọi `value()` bên trong nó vẫn có thể dispatch đến `Child.value()`. Đây là nền tảng của **template method**, đồng thời tạo nguy cơ nếu gọi hook quá sớm trong constructor.

## 9. Constructors, `super(...)` và quá trình khởi tạo subclass

Một class con không thể bỏ qua superclass initialization. Nếu subclass constructor không ghi explicit constructor invocation, compiler sẽ cố dùng `super()` ngầm định theo quy tắc Java 17.

~~~java
class Base {
    Base() {
        System.out.println("Base constructor");
    }
}

class Child extends Base {
    Child() {
        // super() được gọi ngầm định trước phần thân constructor.
        System.out.println("Child constructor");
    }
}
~~~

Tạo `new Child()` in Base trước Child.

Nếu Base **không có constructor không tham số có thể truy cập**, Child phải gọi constructor thích hợp:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }
}

class Employee extends Person {
    private final int employeeNumber;

    Employee(String name, int employeeNumber) {
        super(name);
        this.employeeNumber = employeeNumber;
    }
}
~~~

`super(name)` là **constructor invocation**; nó không có nghĩa “hãy tạo riêng một Person object”. Superclass state được khởi tạo trên cùng Employee object đang được xây dựng.

### 9.1. Constructors không được kế thừa

Nếu chỉ có `Person(String)`, compiler **không** tự sinh `Employee(String)` có body tương đương. Employee phải khai báo constructor thích hợp hoặc có default constructor hợp lệ nếu điều kiện cho phép.

### 9.2. Thứ tự khởi tạo cơ bản

Với một instance subclass:

1. Fields của object trước hết có **default values**.
2. Superclass constructor chain được thực hiện theo quy tắc.
3. Field initializers và instance initializer blocks của từng class chạy ở giai đoạn class đó được khởi tạo, theo thứ tự khai báo thích hợp.
4. Constructor body của subclass chạy sau bước superclass, trừ các chi tiết constructor chaining `this(...)`.
5. Khi mọi bước hoàn tất bình thường, caller mới nhận object từ `new`.

Cần phân biệt **instance initialization** với **static class initialization**. Static fields/blocks có quy tắc khởi tạo class riêng; không chạy lại một lần cho mỗi object tạo ra.

### 9.3. Rủi ro đặc biệt: gọi overridable method từ constructor

Superclass constructor gọi `hook()` có thể dispatch tới subclass override **trước khi subclass fields được khởi tạo**:

~~~java
class Base {
    Base() {
        hook(); // Nguy hiểm nếu Child override dùng state chưa sẵn sàng.
    }

    void hook() {
    }
}

class Child extends Base {
    private String message = "ready";

    @Override
    void hook() {
        System.out.println(message);
    }
}
~~~

Khi `new Child()` chạy, `hook()` có thể in `null`, vì field initializer `message = "ready"` của Child chưa chạy. **Không dùng constructor như nơi gọi polymorphic hooks dựa trên subclass state**. Hãy truyền dữ liệu cần thiết bằng `super(args)` hoặc gọi hook **sau khi toàn bộ object đã hoàn tất constructor**.

## 10. Chương trình hoàn chỉnh 2: thứ tự khởi tạo lớp cha và lớp con

Tạo tệp **`ConstructorOrderDemo.java`**:

~~~java
public class ConstructorOrderDemo {
    static class Base {
        private final String id;
        private int baseValue = initBaseValue();

        private int initBaseValue() {
            System.out.println("Base field initializer");
            return 10;
        }

        Base(String id) {
            this.id = id;
            System.out.println("Base constructor " + id);
        }

        public final String id() {
            return id;
        }

        public final int baseValue() {
            return baseValue;
        }
    }

    static final class Child extends Base {
        private int childValue = initChildValue();
        private final String tag;

        private int initChildValue() {
            System.out.println("Child field initializer");
            return 20;
        }

        Child(String id, String tag) {
            super(id);
            this.tag = tag;
            System.out.println("Child constructor " + tag);
        }

        String summary() {
            return id() + "/" + tag
                    + "/base=" + baseValue()
                    + "/child=" + childValue;
        }
    }

    public static void main(String[] args) {
        System.out.println("Before");
        Child child = new Child("ID-1", "X");
        System.out.println("After = " + child.summary());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorOrderDemo.java
java ConstructorOrderDemo
~~~

**Stdout chính xác:**

~~~text
Before
Base field initializer
Base constructor ID-1
Child field initializer
Child constructor X
After = ID-1/X/base=10/child=20
~~~

**Giải thích:**

- `Before` được in trước khi tạo object.
- Constructor `Child(String,String)` gọi `super(id)`.
- Trong quá trình khởi tạo Base, Base instance field initializer chạy, rồi Base constructor body in ID.
- Sau khi Base constructor hoàn tất, Child instance field initializer chạy rồi Child constructor gán `tag` và in thông báo.
- Method `summary()` chỉ được gọi **sau khi `new Child(...)` hoàn tất**, nên đọc được state đã khởi tạo.

**Không có hai objects riêng Base và Child**: cùng một Child object mang Base fields và Child fields.

## 11. Phạm vi dùng `super`: gọi superclass implementation rõ ràng

Trong một instance method của subclass, `super.method()` cho phép chọn implementation được kế thừa từ superclass phù hợp, thay vì implementation override hiện tại.

~~~java
class Base {
    String greeting() {
        return "Hello";
    }
}

class Child extends Base {
    @Override
    String greeting() {
        return super.greeting() + ", Java";
    }
}
~~~

`new Child().greeting()` trả `"Hello, Java"`. Lời gọi `super.greeting()` **không tạo Base object mới** và không bỏ qua mọi virtual dispatch bên trong method Base. Nếu Base.greeting gọi một overridable helper, helper ấy vẫn có thể dispatch dựa trên runtime receiver.

### 11.1. `super(...)` và `super.method()` không giống nhau

- `super(arguments)`: explicit invocation của **superclass constructor**, trong constructor subclass theo quy tắc cú pháp.
- `super.method(arguments)`: lời gọi một **instance method implementation** từ superclass trong instance context phù hợp.

Trong Java 17, explicit `super(...)`/`this(...)` thông thường phải đứng đầu constructor body; không gọi `super(...)` từ ordinary static/instance method.

### 11.2. `this` vẫn là object subclass runtime

Nếu code trong constructor Base gọi `this.toString()`, runtime method có thể là override từ Child, kể cả khi Child chưa khởi tạo xong. Vì thế tránh log `this` hoặc gọi overridable members sớm trong constructor.

## 12. Field hiding khác method overriding

Một trong những khác biệt quan trọng của Java: **instance fields không có dynamic dispatch như overridable instance methods**. Nếu subclass khai báo field cùng tên, nó có thể **hide** field superclass; Java chọn field theo kiểu tĩnh/lexical qualification thích hợp, không theo runtime method dispatch.

~~~java
class Parent {
    String label = "Parent-field";

    String describe() {
        return "Parent-method";
    }
}

class Child extends Parent {
    String label = "Child-field";

    @Override
    String describe() {
        return "Child-method";
    }
}
~~~

Nếu:

~~~java
Parent ref = new Child();
~~~

thì `ref.label` chọn **Parent.label**; còn `ref.describe()` chạy **Child.describe()** do overriding.

### 12.1. Không khai báo field trùng tên để “override data”

Field hiding dễ gây hiểu nhầm:

- Có **hai field khác nhau** trong cùng object khi subclass định nghĩa field trùng tên.
- Field của Parent không tự biến mất khi Child hide nó.
- Trong subclass, `super.label` có thể truy cập superclass field theo quy tắc phù hợp.
- Gọi method inherited mà body đọc `label` khai báo trong superclass vẫn có thể đọc **superclass field**, không “tự động chuyển” sang field Child.

Thực tế nên ưu tiên **private fields + methods có hợp đồng rõ**, tránh dùng field hiding như công cụ mô phỏng overriding.

## 13. Static method hiding không phải overriding

Một lớp con có thể khai báo `static` method cùng chữ ký thích hợp với static method của lớp cha; Java gọi đó là **method hiding**, không phải overriding. Khác với một instance method đã override, static call được xác định theo **kiểu mà compiler sử dụng để phân giải lời gọi**, không theo class runtime của object.

~~~java
class Parent {
    static String label() { return "Parent-static"; }
    String describe() { return "Parent-instance"; }
}
class Child extends Parent {
    static String label() { return "Child-static"; }
    @Override String describe() { return "Child-instance"; }
}
~~~

Nếu đặt các câu lệnh sau trong một method:

~~~java
Parent value = new Child();
System.out.println(value.label());    // Parent-static
System.out.println(value.describe()); // Child-instance
~~~

Cú pháp `value.label()` được Java cho phép nhưng dễ gây hiểu nhầm; trong mã mới hãy gọi `Parent.label()` hoặc `Child.label()` khi muốn chỉ rõ static member. Ví dụ này nhằm **phân biệt subtype và dispatch**, không phải khuyến nghị dùng static để mô phỏng polymorphism.

Phần chuyên sâu về **field hiding, static method hiding, mối quan hệ với `super`, compile-time lookup và nhiều ví dụ runtime** thuộc bài **“Che khuất trường và phương thức static theo kiểu khai báo”**. Hãy nhớ một quy tắc ở bài nhập môn: **chỉ overridable instance methods được điều phối động theo receiver runtime; fields và static methods không hoạt động như vậy**.

## 14. Overloading không phải overriding

**Overloading** là khai báo nhiều methods cùng tên với **parameter lists khác nhau**, trong cùng class hoặc inheritance context. **Overriding** là cung cấp implementation instance method với chữ ký thích hợp từ superclass.

~~~java
class Base {
    void log(Object value) {
        System.out.println("Object");
    }
}

class Child extends Base {
    void log(String value) {
        System.out.println("String");
    }
}
~~~

`Child.log(String)` ở đây **overload** `Base.log(Object)`, không override nó, vì parameter type khác.

### 14.1. Overload resolution chịu ảnh hưởng của compile-time types

~~~java
Child child = new Child();
Object text = "Java";
child.log(text);       // Chọn log(Object)
child.log("Java");     // Chọn log(String)
~~~

Compiler chọn overload phù hợp theo **kiểu biểu thức tại compile time**. Runtime object của biến `text` là String nhưng compile-time type Object, nên lời gọi `log(text)` chọn `log(Object)`.

Nếu method được chọn là overridable instance method, runtime dispatch sau đó vẫn có thể chọn override tương ứng theo runtime class. **Overload resolution và override dispatch là hai bước khác nhau**.

### 14.2. Chỉ đổi kiểu trả về không tạo overload

~~~java
class Wrong {
    // int calculate() { return 1; }
    // String calculate() { return "1"; }
}
~~~

Nếu uncomment cả hai, class không biên dịch vì Java không dùng riêng return type để phân biệt overloads cùng parameter list.

## 15. Upcasting và downcasting trong quan hệ kiểu con

Một điểm quan trọng của `extends` là cho phép **upcasting**: sử dụng một `Dog` ở nơi yêu cầu `Animal` mà không tạo object mới. Nếu `Dog extends Animal`:

~~~java
Animal animal = new Dog();  // Upcast ngầm định.
~~~

Compiler chỉ cho gọi members mà **kiểu tĩnh `Animal`** cung cấp. Muốn gọi API riêng của Dog thì cần receiver được kiểm tra/thu hẹp kiểu:

~~~java
if (animal instanceof Dog dog) {
    dog.fetch();  // Pattern matching for instanceof, chuẩn từ Java 17.
}
~~~

`instanceof` trả false cho `null`. Downcast trực tiếp `(Dog) animal` chỉ thành công khi object runtime tương thích; nếu không, JVM ném `ClassCastException`. **Ép kiểu không đổi runtime class và không tạo một object khác**.

Ví dụ độc lập **`SubtypeIntroDemo.java`**:

~~~java
public class SubtypeIntroDemo {
    static class Animal {
        String name() { return "Animal"; }
    }
    static final class Dog extends Animal {
        @Override String name() { return "Dog"; }
        String fetch() { return "Fetch"; }
    }
    static final class Cat extends Animal {
        @Override String name() { return "Cat"; }
    }
    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();
        System.out.println(first.name());
        if (first instanceof Dog dog) {
            System.out.println(dog.fetch());
        }
        System.out.println(second instanceof Dog);
        try {
            Dog wrong = (Dog) second;
            System.out.println(wrong.fetch());
        } catch (ClassCastException ex) {
            System.out.println("incompatible cast rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SubtypeIntroDemo.java
java SubtypeIntroDemo
~~~

Stdout:

~~~text
Dog
Fetch
false
incompatible cast rejected
~~~

Bài nhập môn `extends` chỉ cần hiểu **quan hệ subtype tạo đường upcast**, còn kiểm tra runtime quyết định cast xuống có an toàn hay không. Các quy tắc sâu hơn của `instanceof`, flow scoping, `null`, generics erasure, arrays và `ClassCastException` được học trọng tâm ở bài **“Ép kiểu lên, ép kiểu xuống, instanceof và ClassCastException”**.

## 16. Tham chiếu superclass giới hạn method API nhưng không đổi object identity

Một upcast reference vẫn chỉ đến object ban đầu:

~~~java
Child child = new Child();
Parent parent = child;
System.out.println(parent == child); // true
~~~

Dù kiểu tĩnh của `parent` là Parent, object không bị copy. Điều này kéo theo:

- Sửa **instance state được chia sẻ của cùng object** qua một reference có thể được quan sát qua reference khác.
- Override dispatch hoạt động dựa trên cùng runtime receiver.
- `getClass()` trên object cho runtime class tương ứng, không phải kiểu khai báo biến.
- Nếu Parent có fields riêng và Child thêm fields, toàn bộ fields đó cùng thuộc một object.
- Cast reference không gọi constructor, không sao chép dữ liệu, không tự thay access modifier của API.

### 16.1. Khi nào một cast về subtype là dấu hiệu thiết kế đáng xem lại?

Một function nhận `Animal` nhưng luôn viết:

~~~java
if (animal instanceof Dog dog) {
    dog.fetch();
} else if (animal instanceof Cat cat) {
    // Hành vi khác dành riêng Cat
}
~~~

có thể cho thấy function **cần một abstraction khác** (ví dụ `Playable`) hoặc nên giao behavior cho polymorphic method. Tuy nhiên, pattern matching vẫn hợp lý khi logic thực sự phụ thuộc vào **dạng dữ liệu** hoặc cần phân biệt một số subtypes, nhất là trong xử lý AST, compiler hoặc dữ liệu được mô hình hóa bằng sealed hierarchy.

## 17. `Object` là gốc của class inheritance

Các reference classes Java thông thường đều có quan hệ đến `java.lang.Object`. Những methods quen thuộc của Object gồm:

- `toString()`
- `equals(Object)`
- `hashCode()`
- `getClass()`
- `wait()`, `notify()`, `notifyAll()` (liên quan synchronization)
- `clone()` (protected, có điều kiện)
- `finalize()` ở Java 17 còn tồn tại nhưng deprecated; không nên xây dựng lifecycle vào nó.

Một subclass có thể override các methods phù hợp như `toString()`, `equals(...)` và `hashCode()` theo contract. Không thể override `getClass()` vì method đó là final trong Object.

### 17.1. `equals` và `hashCode` là một phần của subtype contract

Khi override `equals`, cần bảo đảm các tính chất quan trọng như symmetry, transitivity, consistency và tuân thủ contract với `hashCode`.

Một rủi ro với inheritance là:

- Superclass coi hai objects bằng nhau dựa trên ID.
- Subclass thêm field và định nghĩa equality dựa trên ID **và** field mới.
- `base.equals(child)` có thể khác `child.equals(base)` nếu không thiết kế cẩn thận.

**Không tự động bổ sung mọi subclass field vào `equals/hashCode`** chỉ vì dùng kế thừa. Với value objects, final class hoặc record đôi khi cho mô hình equality rõ hơn. Với entities, xem identity và trạng thái mutable để tránh lỗi HashMap/HashSet khi key thay hash.

### 17.2. `Object` không phải sự thay thế API giàu ngữ nghĩa

Có thể khai báo `Object value = new Dog()`, nhưng qua kiểu tĩnh Object, compiler không cho gọi `sound()` hoặc `fetch()` trực tiếp. Nếu muốn contract chung, tốt hơn dùng `Animal` hoặc một interface thích hợp.

## 18. Abstract superclass và concrete subclass

Một **abstract class** cho phép định nghĩa state/behavior chung và những methods chưa có implementation hoàn chỉnh:

~~~java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    String color() {
        return color;
    }

    abstract double area();
}
~~~

Subclass concrete triển khai abstract method:

~~~java
final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(String color, double width, double height) {
        super(color);
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Kích thước sai");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}
~~~

`new Shape(...)` không hợp lệ vì Shape abstract; `new Rectangle(...)` hợp lệ khi constructor validate thành công.

### 18.1. Abstract class vẫn có constructor

Abstract class **không được tạo object trực tiếp bằng `new AbstractClass()`**, nhưng constructor của nó **được chạy khi tạo concrete subclass**. Nó có thể validate và gán superclass fields.

Tránh gọi abstract hoặc overridable instance method từ abstract superclass constructor nếu method đó phụ thuộc vào state subclass chưa khởi tạo xong. Java vẫn có thể dispatch vào subclass implementation quá sớm.

### 18.2. Khi nào dùng abstract class?

Khi có một **hợp đồng chung kèm một phần state/implementation có ý nghĩa** và subclasses thật sự là subtypes của superclass. Nếu chỉ muốn công bố behavior và cho nhiều implementations không có chung implementation base, interface thường đơn giản hơn.

## 19. Interface là supertype, nhưng `implements` khác `extends class`

~~~java
interface Payable {
    long amountCents();
}

class Invoice implements Payable {
    private final long amount;

    Invoice(long amount) {
        this.amount = amount;
    }

    @Override
    public long amountCents() {
        return amount;
    }
}
~~~

`Invoice` là subtype của `Payable`. Biến `Payable payable = new Invoice(500);` là hợp lệ nếu class và constructor access phù hợp.

Một class có thể **extends một class** và **implements nhiều interfaces**:

~~~java
class Entity {
}

interface Identified {
    String id();
}

interface Auditable {
    void audit();
}

class Document extends Entity
        implements Identified, Auditable {
    @Override
    public String id() {
        return "D-1";
    }

    @Override
    public void audit() {
        System.out.println("Audited");
    }
}
~~~

Document vừa là subtype của Entity vừa là subtype của hai interfaces.

### 19.1. Interface có thể `extends` các interfaces khác

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

**Interface inheritance** cho phép nhiều superinterfaces. Đừng nhầm với class inheritance, nơi một class chỉ có một direct superclass.

### 19.2. Default methods không phải “đa kế thừa class đầy đủ”

Interfaces có thể khai báo default methods. Khi nhiều defaults có conflict, Java có các quy tắc giải quyết và đôi khi class implementing phải override để chọn hành vi rõ.

~~~java
interface A {
    default String name() {
        return "A";
    }
}

interface B {
    default String name() {
        return "B";
    }
}

class Both implements A, B {
    @Override
    public String name() {
        return A.super.name() + B.super.name();
    }
}
~~~

Đây là đoạn khai báo hợp lệ trong một tệp thích hợp. `A.super.name()` và `B.super.name()` gọi implementation default được chỉ rõ theo interface, không tạo objects mới.

## 20. `final` ngăn class extension hoặc method override

Một `final class` không thể được extends:

~~~java
final class ImmutableToken {
    private final String value;

    ImmutableToken(String value) {
        this.value = value;
    }
}

// class SpecialToken extends ImmutableToken {} // Lỗi compile
~~~

`final` trên class ngăn subclasses; **không tự bảo đảm toàn bộ instance immutable**, vì class final vẫn có thể có non-final mutable fields.

Một `final method` trong superclass không thể bị subclass override:

~~~java
class Base {
    public final String id() {
        return "fixed";
    }
}

class Child extends Base {
    // @Override
    // public String id() { return "changed"; } // Lỗi
}
~~~

Có thể dùng final method để giữ entry point validation hoặc orchestration nhất quán khi vẫn mở một số hooks khác.

### 20.1. Không phải cứ muốn tái sử dụng là bỏ final

Nếu một class có semantic ổn định và không có subtype contract, dùng final + composition có thể phù hợp hơn việc mở inheritance chỉ để chia sẻ vài dòng code. Khi quyết định public API cho phép `extends`, bạn đang cam kết nhiều chi tiết về lifecycle, accessibility và method contracts mà subclasses có thể phụ thuộc.

### 20.2. Class abstract không được đồng thời final

`abstract` dự kiến có subclasses implement những abstract methods; `final` cấm subclass. Vì thế tổ hợp `abstract final class` là không hợp lệ.

## 21. Sealed class trong Java 17: giới hạn các subtypes được phép

Java 17 hỗ trợ **sealed classes/interfaces** để khai báo một **tập direct permitted subclasses/implementations** được kiểm soát.

Ví dụ:

~~~java
sealed abstract class Result
        permits Success, Failure {
}

final class Success extends Result {
}

final class Failure extends Result {
}
~~~

Nếu khác source files, các permitted subclasses phải tuân thủ quy tắc package/module của sealed hierarchy. Một direct subclass của sealed class phải khai báo một trong các modifier phù hợp: `final`, `sealed` hoặc `non-sealed` (trừ trường hợp đặc thù như record implicitly final).

**Ý nghĩa:** compiler biết những direct permitted subclasses, và API giới hạn extension tùy ý. Nhưng hierarchy vẫn có inheritance, subtype và dynamic dispatch như phù hợp.

### 21.1. `non-sealed` mở lại việc subclassing

~~~java
sealed class Base permits Closed, Open {
}

final class Closed extends Base {
}

non-sealed class Open extends Base {
}
~~~

Class `Open` là permitted subclass của Base và chọn `non-sealed`, nên bản thân Open có thể được mở rộng tiếp (nếu các quy tắc khác cho phép). Tập **direct** subclasses của Base được kiểm soát; không nhất thiết mọi descendant đều hữu hạn khi có nhánh non-sealed.

### 21.2. Records không thể `extends` một class ứng dụng khác

Record types là implicitly final và trực tiếp kế thừa `java.lang.Record` theo ngữ nghĩa ngôn ngữ, nên bạn không thể viết:

~~~java
// record UserView(String name) extends Person {} // Không hợp lệ
~~~

Record có thể **implement interface**:

~~~java
interface Named {
    String name();
}

record UserView(String name) implements Named {
}
~~~

`UserView` là subtype của Named, mặc dù không dùng `extends Person`. Đây là một hướng tốt để biểu diễn immutable-style value data với hợp đồng interface; nhớ rằng record chỉ bảo đảm **shallow immutability**, không tự deep-copy mutable reference components.

## 22. Chương trình hoàn chỉnh 5: sealed hierarchy và subtypes Java 17

Tạo tệp **`SealedShapeDemo.java`**:

~~~java
public class SealedShapeDemo {
    sealed interface Shape permits Square, Rectangle {
        int area();
    }

    record Square(int side) implements Shape {
        Square {
            if (side <= 0) {
                throw new IllegalArgumentException("Cạnh sai");
            }
        }

        @Override
        public int area() {
            return Math.multiplyExact(side, side);
        }
    }

    record Rectangle(int width, int height)
            implements Shape {
        Rectangle {
            if (width <= 0 || height <= 0) {
                throw new IllegalArgumentException("Cạnh sai");
            }
        }

        @Override
        public int area() {
            return Math.multiplyExact(width, height);
        }
    }

    static void printArea(Shape shape) {
        System.out.println(
                shape.getClass().getSimpleName()
                        + "=" + shape.area());
    }

    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 5);

        printArea(a);
        printArea(b);

        System.out.println("Square is Shape = "
                + (a instanceof Shape));

        try {
            new Square(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy với Java 17:

~~~bash
javac -encoding UTF-8 SealedShapeDemo.java
java SealedShapeDemo
~~~

**Stdout chính xác:**

~~~text
Square=9
Rectangle=10
Square is Shape = true
Rejected = Cạnh sai
~~~

**Giải thích:**

1. `Shape` là sealed interface chỉ cho phép các direct implementors `Square` và `Rectangle` được liệt kê.
2. Hai records implicitly final, vì vậy phù hợp quy tắc permitted implementations.
3. Mỗi record định nghĩa `area()` để hoàn thành interface contract; `Shape` reference có thể gọi `shape.area()` và runtime dispatch chọn implementation record tương ứng.
4. `getClass().getSimpleName()` với các nested records trong tệp này trả tên đơn giản `Square` hoặc `Rectangle`.
5. Compact constructors validate dữ liệu; `new Square(0)` ném exception trước khi object hợp lệ được trả về.
6. Dùng `Math.multiplyExact` để phát hiện overflow thay vì âm thầm trả diện tích sai nếu đối số quá lớn.

**Chú ý:** records ở đây là **nested member types** trong `SealedShapeDemo`; điều kiện permitted subclasses cùng module/package đều được đáp ứng. Nếu tách files hoặc packages, cần tuân thủ quy tắc sealed type declaration tương ứng.

## 23. Generic types: subclass relation không tự suy ra subtype giữa mọi parameterizations

Nếu `Dog extends Animal`, ta có:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

Nhưng **`List<Dog>` không phải subtype của `List<Animal>`**:

~~~java
java.util.List<Dog> dogs = new java.util.ArrayList<>();

// java.util.List<Animal> animals = dogs; // Lỗi compile
~~~

Vì sao? Nếu cho phép gán, caller có thể thêm một Cat vào `animals`, trong khi cùng collection runtime vốn phải chứa Dogs. **Java generics invariant** cho các parameterized types dạng thông thường, dù Dog là subtype của Animal.

### 23.1. Wildcard `? extends Animal` để đọc từ nguồn chứa subtypes

~~~java
static void printAnimals(
        java.util.List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.sound());
    }
}
~~~

Method có thể nhận `List<Dog>` hoặc `List<Cat>` khi class definitions phù hợp. Nhưng qua `List<? extends Animal>`, không thể tùy ý thêm `new Animal(...)` hoặc `new Cat()` vào list, vì compiler không biết element type cụ thể của list nhận vào.

Nguyên tắc thường dùng **PECS**:
- **Producer Extends:** nếu collection chủ yếu cung cấp values kiểu Animal cho caller đọc, `? extends Animal` có thể phù hợp.
- **Consumer Super:** nếu collection nhận Dogs được thêm vào, `? super Dog` có thể phù hợp.

PECS là heuristic sử dụng wildcard, không làm mọi generic type trở thành covariant.

### 23.2. Generics và array covariance là hai cơ chế khác nhau

Java arrays của reference types là **covariant**: `Dog[]` có thể được gán cho `Animal[]`. Nhưng ghi một Cat vào array vốn là Dog[] sẽ bị kiểm tra runtime và ném `ArrayStoreException`.

~~~java
Dog[] dogs = new Dog[1];
Animal[] animals = dogs;
// animals[0] = new Cat(); // Runtime ArrayStoreException
~~~

Đây là fragment. Việc arrays covariant không có nghĩa generics `List<Dog>` cũng covariant. Không nên dùng cast raw types để vô hiệu hóa kiểm tra generic chỉ nhằm ép một subtype relation không hợp lệ.

## 24. Access control qua packages khi extends

Inheritance không bỏ qua visibility.

Một ví dụ tổ chức hai package:

~~~text
src/
  model/
    Base.java
  app/
    Derived.java
~~~

Nội dung `src/model/Base.java`:

~~~java
package model;

public class Base {
    private int privateValue = 1;
    int packageValue = 2;
    protected int protectedValue = 3;
    public int publicValue = 4;

    protected void check() {
        System.out.println(protectedValue);
    }
}
~~~

Nội dung `src/app/Derived.java`:

~~~java
package app;

public class Derived extends model.Base {
    public int read() {
        check();
        return protectedValue + publicValue;
    }

    // Không truy cập trực tiếp privateValue hoặc packageValue.
}
~~~

Ở subclass khác package, `check()` và `protectedValue` được dùng từ instance context của Derived theo quy tắc protected. `privateValue` và `packageValue` không được truy cập trực tiếp từ Derived.

### 24.1. Protected access qua reference không tùy ý

Trong code package `app` của Derived, những thao tác như:

~~~java
// model.Base other = new model.Base();
// int x = other.protectedValue; // Không được truy cập tùy ý
~~~

là khác với `this.protectedValue` trong subclass instance context. Java đặt quy tắc receiver type cho protected instance members khi declaring class nằm ở package khác; **protected không có nghĩa toàn bộ objects của Base công khai field ấy cho mọi subclasses**.

### 24.2. Public class cũng chịu module rules

Trong code tổ chức theo **Java Platform Module System (JPMS)**, truy cập types giữa modules còn liên quan đến `requires`/`exports` và các rules khác. Một class public nằm trong package không export đúng cách có thể không truy cập được từ module khác. Inheritance không phá ranh giới module.

Bài này tập trung cơ chế class-object, nên các ví dụ chạy độc lập không yêu cầu cấu hình JPMS.

## 25. Đừng tăng visibility chỉ để subclass truy cập state trực tiếp

Một superclass có field:

~~~java
protected long balance;
~~~

cho subclasses quyền đọc/ghi field theo access rules. Điều đó có thể làm subclass phá invariant của base nếu viết `balance = -100;`.

Đôi khi API tốt hơn là:

~~~java
abstract class Account {
    private long balance;

    protected final void credit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount sai");
        }
        balance = Math.addExact(balance, amount);
    }

    public final long balance() {
        return balance;
    }
}
~~~

Subclass có thể dùng `credit(...)`, không gán field tự do. Method `final` giúp bảo vệ contract của thao tác cập nhật. Nhưng superclass vẫn cần quyết định cụ thể những protected hooks nào hợp lý cho inheritance contract; không phải mọi domain class đều cần được extends.

**Nguyên tắc:** cho subclass đúng những khả năng cần thiết, hạn chế coupling đến representation nội bộ.

## 26. LSP: thiết kế đúng subtype khó hơn chia sẻ code

Hãy tưởng tượng superclass `Rectangle` có `setWidth`/`setHeight` cho phép thay hai chiều độc lập. Một subclass `Square extends Rectangle` muốn ép width luôn bằng height. Nếu người dùng có code:

~~~java
void resize(Rectangle rectangle) {
    rectangle.setWidth(10);
    rectangle.setHeight(20);
}
~~~

Caller có thể mong width=10 và height=20 ở cuối. Nhưng một Square subclass bắt buộc width==height có thể khiến hậu điều kiện này không còn đúng. Đây là ví dụ kinh điển cho thấy **hình học “hình vuông là hình chữ nhật” không mặc nhiên tạo một inheritance API tốt khi các lớp mutable có setter contract không tương thích**.

Những lựa chọn khác:

- Immutable shape value types với shared `area()` interface.
- Rectangle/Square độc lập implement Shape.
- Composition của một immutable Dimensions object.
- Bỏ setters khiến subtype contract khả thi hơn.
- Định nghĩa shared behavior bằng interface, không ép mọi kiểu chung state/constructor base.

Một kế thừa đúng là khi **subclass thực sự tuân thủ toàn bộ những gì superclass hứa**, kể cả trạng thái, exceptions, lifecycle và side effects.

### 26.1. Behavioral subtyping không chỉ nói “cùng method name”

Một override có cùng signature vẫn có thể phá LSP nếu:

- Ném exception mới khi input vốn hợp lệ với superclass contract.
- Trả kết quả sai invariants.
- Có side effects không phù hợp.
- Không tôn trọng thread-safety contract superclass.
- Thay semantics mà callers không dự liệu.
- Dùng superclass constructor với hooks được override chưa sẵn sàng.

Java compiler kiểm tra một số quy tắc ngôn ngữ như checked exceptions và access widening, **không chứng minh toàn bộ behavioral contract**.

## 27. Fragile base class problem và rủi ro thay đổi superclass

Một base class công khai khả năng subclassing tạo phụ thuộc từ subclasses:

- Subclass có thể override protected method được gọi bởi methods khác.
- Base class có thể gọi overridable methods trong một trình tự.
- Base fields/constructor hooks có thể tạo lifecycle assumptions.
- Thêm method mới vào Base đôi khi xung đột với method sẵn có ở subclass.
- Thay implementation Base có thể đổi số lần hoặc thời điểm gọi hook mà subclass phụ thuộc.

Đó là một phần của **fragile base class problem**: thay đổi superclass tưởng nội bộ có thể làm subclasses bị tác động.

### 27.1. Thiết kế superclass để kế thừa

Nếu class **cố ý** là extension point, nên:

1. Tài liệu hóa invariants, preconditions và postconditions.
2. Nêu rõ methods nào overridable, methods nào final.
3. Không gọi overridable methods từ constructor khi subclass state chưa sẵn sàng.
4. Đặt protected API tối thiểu và có chủ đích.
5. Dùng template method nếu cần giữ workflow và chỉ cho hook ở các bước phù hợp.
6. Tách state không nên bị sửa sang private fields/controlled methods.
7. Kiểm thử với nhiều concrete subclasses.
8. Xem backward compatibility khi thay đổi public/protected API.

Nếu không muốn hỗ trợ inheritance contract, **final class hoặc composition** thường rõ ràng hơn việc mở `extends` theo mặc định.

## 28. Override, access modifier và checked exception: minh họa chính xác

Superclass:

~~~java
import java.io.IOException;

class BaseReader {
    protected Number read() throws IOException {
        return 1;
    }
}
~~~

Subclass:

~~~java
class FastReader extends BaseReader {
    @Override
    public Integer read() {
        return 2;
    }
}
~~~

Override hợp lệ vì:

- `public` không hẹp hơn `protected`.
- `Integer` là subtype của `Number` (covariant return).
- Không khai báo checked exception mới hoặc rộng hơn.
- Signature và ngữ cảnh overriding phù hợp.

Một override như:

~~~java
// @Override
// private Number read() throws Exception { return 0; }
~~~

sẽ không hợp lệ trong class con vì giảm quyền truy cập và mở rộng checked exception trái contract. Dòng này chỉ minh họa lỗi, không phải Java source độc lập.

### 28.1. Checked vs unchecked exceptions

Một overriding method thường có thể ném unchecked exception như `IllegalArgumentException` mà Java không bắt buộc khai báo throws. Tuy nhiên, **behavioral contract** vẫn cần được tôn trọng. Đừng dùng khả năng ném unchecked exception để né nghĩa vụ substitutability.

## 29. Abstract method, default method và overload resolution ở nhiều cấp

Một class có thể:

- Thừa hưởng concrete instance method từ superclass.
- Override method đó.
- Cung cấp overload khác với parameter list mới.
- Implement abstract method của superclass.
- Implement hoặc nhận default method từ interface nếu không có conflict với class method/other defaults.

**Khi đọc `object.method(args)` hãy giải hai câu hỏi:**

1. *Compiler chọn method declaration nào?* Dựa vào compile-time types, overload applicability/access.
2. *Runtime chạy implementation nào?* Nếu declaration tương ứng với overridable instance method, dynamic dispatch theo runtime receiver.

Sự phân đôi này giúp giải thích tại sao field/static method không hành xử như virtual instance methods và vì sao downcast có thể làm compiler nhìn thấy thêm API.

## 30. `getClass()`, `instanceof` và việc kiểm tra kiểu có giới hạn

~~~java
Animal animal = new Dog("Milo");
System.out.println(animal.getClass().getSimpleName());
~~~

Kết quả là `Dog` nếu dùng các class Dog tương ứng, vì `getClass()` báo runtime class.

Nhưng không nên điều khiển toàn bộ domain logic bằng:

~~~java
if (animal.getClass() == Dog.class) {
    // ...
}
~~~

So sánh class **chính xác** bằng `getClass() == ...` bỏ qua instances của subclasses khác, trong khi `instanceof Dog` kiểm tra sự tương thích kiểu Dog. Hai mục đích khác nhau.

Nếu hành vi là một phần contract Animal, thường nên gọi **virtual method Animal** thay vì `getClass()` rồi `if/else`. Exact runtime type checks phù hợp khi nghiệp vụ thực sự phải phân biệt exact class, nhưng đó không phải default cho thiết kế OOP.

## 31. Một số lỗi biên dịch và runtime thường gặp

### 31.1. Cố extends hai classes

~~~java
// class C extends A, B {} // Không hợp lệ
~~~

Java chỉ có một direct class superclass; dùng interface hoặc composition nếu cần nhiều capabilities.

### 31.2. Extends một class `final`

~~~java
// class SpecialString extends String {} // Không hợp lệ
~~~

`String` là final. Không phải mọi class trong JDK đều được mở inheritance.

### 31.3. Dựa vào constructor superclass như constructor subclass

~~~java
class Base {
    Base(int code) {
    }
}

class Child extends Base {
    // Không tự có Child(int). Cần constructor gọi super(int).
}
~~~

Đây là đoạn **không biên dịch** nếu giữ nguyên Child không có constructor: compiler cố sinh constructor mặc định gọi `super()`, nhưng Base không có constructor không tham số. Cần khai báo:

~~~java
class Child extends Base {
    Child(int code) {
        super(code);
    }
}
~~~

Trong ví dụ thật, chỉ sử dụng một phiên bản Child ở một tệp; các đoạn trên tách biệt để minh họa tình huống sai/đúng.

### 31.4. Gọi method chỉ có trong subclass qua superclass reference

~~~java
// Animal pet = new Dog("Milo");
// pet.fetch(); // Animal không khai báo fetch
~~~

Nếu use case cần method `fetch`, có thể giữ Dog reference, pattern matching với `instanceof` hoặc thiết kế interface thích hợp. Đừng cast bừa chỉ vì biết một object “thường là Dog”.

### 31.5. Downcast không tương thích

~~~java
// Animal a = new Cat("Luna");
// Dog dog = (Dog) a; // Runtime ClassCastException
~~~

Compiler có thể chấp nhận cast giữa hai reference types có quan hệ phù hợp, nhưng runtime object phải thực sự thuộc subtype cần cast.

### 31.6. Dùng `@Override` cho overload nhầm

~~~java
class Base {
    void print(Object data) {
    }
}

class Child extends Base {
    // @Override
    // void print(String data) {} // Không override print(Object)
}
~~~

Bỏ annotation nếu thực sự muốn overload, hoặc sửa parameter signature nếu muốn override.

### 31.7. Giảm visibility method override

Superclass public method không thể bị subclass override thành package-private/protected/private.

### 31.8. Override static method như instance method

Không thể dùng instance method để override static method cùng signature của superclass, và không thể dùng static method để hide một instance method cùng signature theo cách hợp lệ.

### 31.9. Nghĩ field có dynamic dispatch

`Parent p = new Child(); p.field` đọc field theo static access rules, không tự chọn Child.field. Dùng overridable method nếu cần runtime polymorphism.

### 31.10. Gọi overridable method từ constructor

Subclass override có thể chạy khi fields subclass còn null/0; có thể gây NPE hoặc tác dụng phụ. Tránh hook động trong constructor initialization chain.

### 31.11. Đổi mọi field thành `protected` để subclass dùng

Điều này làm lộ representation, khiến subclasses có thể phá invariant. Ưu tiên private fields và protected/public behaviors có kiểm soát.

### 31.12. Coi `List<Dog>` là `List<Animal>`

Generics invariant. Dùng `List<? extends Animal>` cho read-only producer-style parameter khi phù hợp hoặc tạo danh sách Animal độc lập.

### 31.13. Coi `extends` là giải pháp đa nhiệm tự động

Nếu class con chỉ muốn một chức năng của superclass nhưng không tuân toàn bộ contract, quan hệ is-a không phù hợp. Composition thường rõ hơn.

### 31.14. Dùng subclassing chỉ để mock trong test

Một final service có thể cộng tác qua injectable interface/constructor; test có thể dùng fake collaborator. Không nhất thiết mở inheritance cho toàn bộ class chỉ vì cần thay một dependency.

### 31.15. Dùng class cast như cách “thêm method” cho object

Cast không tạo behavior mới. Nó chỉ thay cách reference được kiểm tra/nhìn nhận; runtime object vẫn có type ban đầu.

## 32. Thiết kế trước khi viết `extends`: checklist thực tế

Trước khi khai báo `class Child extends Parent`:

1. **Is-a đúng không?** Caller dùng Parent contract có được thay bằng Child?
2. **Parent có được thiết kế để subclass không?** Có documentation về hooks/lifecycle không?
3. **Có dependency chỉ cần has-a không?** Composition có thể đơn giản hơn.
4. **Superclass fields có private không?** Subclass có access qua controlled methods?
5. **Constructor chain có hợp lệ không?** Parent có constructor phù hợp để `super(...)` gọi?
6. **Có gọi overridable method sớm không?** Xem cả field initializers và constructor call graph.
7. **Child có cần thêm invariant không?** Nó có mâu thuẫn Parent behavior?
8. **Override có làm hẹp precondition hoặc phá postcondition không?** Kiểm tra LSP.
9. **Methods dùng `@Override` chưa?** Có vô tình overload?
10. **Static methods/fields có trùng tên không?** Tránh hiding gây khó hiểu.
11. **Có nhu cầu nhiều capabilities không?** Implements interfaces có phù hợp hơn multiple inheritance giả?
12. **Class parent là `final`, sealed hay abstract?** Hiểu giới hạn extension.
13. **Runtime casts có nhiều không?** Có thể cần API polymorphic tốt hơn.
14. **Generics có cần wildcard không?** `List<Child>` không tự là `List<Parent>`.
15. **Protected access qua package khác có đúng không?** Chú ý receiver và module rules.
16. **Equality/hashCode contract có bền vững dưới inheritance không?** Xem symmetry, mutable state.
17. **Thay đổi superclass có ảnh hưởng subclasses bên ngoài không?** Xem backward compatibility.
18. **Thiết kế có còn dễ hiểu hơn composition không?** Ưu tiên mô hình đúng domain.

## 33. Bài tập tự kiểm tra có đáp án

**Câu 1.** `class Dog extends Animal` thiết lập những quan hệ nào?

**Đáp án:** Dog là direct subclass của Animal (nếu Animal được ghi ngay sau extends), Dog có quan hệ subtype với Animal và có thể dùng ở nhiều ngữ cảnh yêu cầu Animal reference.

**Câu 2.** Java cho phép `class C extends A, B` không?

**Đáp án:** Không. Mỗi class chỉ có một direct superclass dạng class. Một class có thể implements nhiều interfaces.

**Câu 3.** Nếu không khai báo `extends` cho class thông thường, direct superclass là gì?

**Đáp án:** Thông thường là `java.lang.Object`; bản thân Object là gốc ngoại lệ.

**Câu 4.** `Animal animal = new Dog();` có tạo Animal object mới ngoài Dog object không?

**Đáp án:** Không. Đây là upcast reference tới cùng Dog object.

**Câu 5.** Với `Animal animal = new Dog();`, compiler có cho `animal.fetch()` nếu fetch chỉ khai báo trong Dog không?

**Đáp án:** Không, vì kiểu tĩnh của animal là Animal. Runtime Dog không tự thay compile-time method availability.

**Câu 6.** `animal.sound()` gọi method ở đâu nếu Dog override Animal.sound?

**Đáp án:** Instance method call được runtime dispatch tới Dog implementation khi runtime receiver là Dog.

**Câu 7.** `Parent p = new Child(); p.label` chọn field nào khi cả hai classes có `label`?

**Đáp án:** Field được phân giải theo compile-time type Parent của p; field hiding không phải overriding.

**Câu 8.** `p.staticMethod()` gọi Parent hay Child khi Child hide static method cùng signature?

**Đáp án:** Chọn theo compile-time type của expression (Parent), không theo runtime object Child. Nên gọi static qua tên class để rõ ý định.

**Câu 9.** Constructor của Parent có được kế thừa thành constructor Child không?

**Đáp án:** Không. Child khai báo constructors riêng; chúng gọi Parent constructor thông qua `super(...)` tường minh hoặc ngầm định thích hợp.

**Câu 10.** Nếu Base chỉ có `Base(int)`, một Child không khai báo constructor có tự biên dịch không?

**Đáp án:** Không nếu compiler không thể gọi constructor Base không tham số hợp lệ. Child cần constructor gọi `super(int)` với đối số thích hợp.

**Câu 11.** Vì sao không nên gọi overridable method từ superclass constructor?

**Đáp án:** Runtime dispatch có thể chọn subclass override trước khi subclass fields/constructor body được khởi tạo xong, khiến method thấy null/0 hoặc ném exception.

**Câu 12.** Khi nào dùng `super.method()`?

**Đáp án:** Trong instance context phù hợp của subclass, để gọi superclass implementation thay vì chính override hiện tại.

**Câu 13.** `this(...)` và `super(...)` là gì?

**Đáp án:** Explicit constructor invocations: `this(...)` gọi constructor khác của cùng class, `super(...)` gọi constructor superclass; không phải ordinary method calls.

**Câu 14.** Overloading và overriding khác nhau ở đâu?

**Đáp án:** Overloading khác parameter list, compiler chọn overload theo static types; overriding cung cấp instance implementation phù hợp cho inherited method và có runtime dispatch.

**Câu 15.** `@Override` có ích gì?

**Đáp án:** Nó làm compiler xác nhận method thật sự override/implement phù hợp, phát hiện lỗi signature hoặc typo.

**Câu 16.** Một method public ở Parent có thể bị Child override thành protected không?

**Đáp án:** Không, vì quyền truy cập hẹp hơn trái quy tắc overriding.

**Câu 17.** Có thể override final method không?

**Đáp án:** Không. Final class cũng không thể được extends.

**Câu 18.** Abstract superclass có constructor không?

**Đáp án:** Có. Constructor abstract superclass chạy trong lúc concrete subclass được khởi tạo; không thể trực tiếp new abstract superclass.

**Câu 19.** Một class có thể vừa extends class vừa implements hai interfaces không?

**Đáp án:** Có, với cú pháp `extends Base implements I1, I2` khi các contracts được đáp ứng.

**Câu 20.** `record Product(String name)` có thể `extends BaseProduct` không?

**Đáp án:** Không. Record implicitly final và kế thừa java.lang.Record theo ngữ nghĩa Java, nhưng có thể implements interfaces.

**Câu 21.** Sealed class kiểm soát điều gì?

**Đáp án:** Nó kiểm soát direct permitted subclasses. Các permitted subclasses phải khai báo modifier phù hợp như final, sealed hoặc non-sealed theo quy tắc Java 17.

**Câu 22.** `List<Dog>` có phải subtype của `List<Animal>` không?

**Đáp án:** Không. Generic parameterizations thông thường invariant. Cân nhắc `List<? extends Animal>` cho producer list.

**Câu 23.** `Dog[]` có thể gán sang `Animal[]` không?

**Đáp án:** Có với array covariance, nhưng lưu Cat vào array có runtime Dog[] sẽ gây ArrayStoreException.

**Câu 24.** `animal instanceof Dog d` có lợi ích gì trong Java 17?

**Đáp án:** Nó kiểm tra runtime type và binding Dog reference trong nhánh hợp lệ, tránh explicit cast lặp lại.

**Câu 25.** Cast `(Dog) cat` có biến Cat object thành Dog không?

**Đáp án:** Không. Cast chỉ kiểm tra/treat reference theo kiểu yêu cầu. Nếu runtime object không tương thích, ném ClassCastException.

**Câu 26.** Tại sao `Square extends Rectangle` có thể sai thiết kế với mutable setters?

**Đáp án:** Nếu Square bắt buộc width==height thì override setters có thể phá hợp đồng của Rectangle cho phép đổi width/height độc lập; vi phạm behavioral substitutability.

**Câu 27.** Private field của Parent có biến mất khỏi Child object không?

**Đáp án:** Không. Nó vẫn là một phần state theo superclass declaration; Child không được truy cập trực tiếp do visibility rules.

**Câu 28.** Subclass có thể có field trùng tên với superclass không?

**Đáp án:** Có trong một số ngữ cảnh, nhưng đó là field hiding, không phải overriding; dễ gây nhầm khi code dùng Parent/Child references.

**Câu 29.** `Animal animal = null;` có hợp lệ không và `animal instanceof Dog` cho gì?

**Đáp án:** Gán null cho reference Animal hợp lệ. `null instanceof Dog` là false; gọi instance method trực tiếp qua null ném NPE.

**Câu 30.** Khi nào nên dùng composition thay `extends`?

**Đáp án:** Khi class cần **có/sử dụng** một collaborator hoặc tái sử dụng một khả năng, nhưng không thật sự là subtype tuân thủ toàn bộ contract của class ấy.

## 34. Kết luận: subtype là một cam kết, không phải chỉ một dấu mũi tên

`extends` là cú pháp thiết lập class inheritance và subtype relation trong Java. Một subclass có thể nhận members được kế thừa, khai báo state/behavior mới, gọi superclass constructor bằng `super(...)` và **override** instance methods để tham gia dynamic dispatch. Upcasting cho phép code sử dụng Child object qua Parent reference mà không tạo object mới. Nhưng compile-time type vẫn quyết định API có thể gọi và overload resolution, trong khi runtime class quyết định implementation của overridable instance methods.

Để sử dụng đúng cần phân biệt **overriding với hiding**, **subtype với cast**, **constructor invocation với inherited method**, **class inheritance với interface implementation**, và **is-a với has-a**. Các modifiers như `final`, `abstract` và `sealed` giúp kiểm soát cách hierarchy được mở rộng trong Java 17.

Quan trọng hơn cả: **mỗi `extends` là một cam kết thiết kế** rằng lớp con có thể thay thế lớp cha trong những tình huống mà hợp đồng cha mô tả. Nếu mục tiêu chỉ là ghép các thành phần làm việc cùng nhau, composition thường rõ nghĩa và linh hoạt hơn. Nếu thực sự cần subtype polymorphism, hãy thiết kế superclass/interface contract chặt chẽ, giữ invariants và kiểm thử các concrete subclasses — đó mới là cách tận dụng kế thừa bền vững trong Java.
