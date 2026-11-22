# Đơn kế thừa lớp và quan hệ ngầm định với `Object` trong Java

## 1. Tư tưởng chính: một superclass trực tiếp, một gốc `Object`

Java sử dụng **đơn kế thừa lớp (*single class inheritance*)**: một class thông thường chỉ có thể có **một superclass trực tiếp**. Nếu một class không ghi mệnh đề `extends`, superclass trực tiếp của nó **ngầm định là `java.lang.Object`**, trừ những loại khai báo đặc biệt có quy tắc riêng như `Object`, `enum` và `record`.

Ví dụ:

```java
class Person {
}

class Student extends Person {
}

class GraduateStudent extends Student {
}
```

Quan hệ lớp:

```text
java.lang.Object
       |
       v
     Person
       |
       v
     Student
       |
       v
 GraduateStudent
```

- `Person` không viết `extends`, nên kế thừa trực tiếp từ `Object`.
- `Student` khai báo `extends Person`, nên superclass trực tiếp là `Person`.
- `GraduateStudent` khai báo `extends Student`, nên superclass trực tiếp là `Student`.
- Cả `Student` và `GraduateStudent` cũng là các subtype của `Object` **gián tiếp**.
- Mỗi class chỉ có một **superclass trực tiếp**, nhưng có thể có **nhiều lớp tổ tiên** trên cùng một chuỗi.
- Một class có thể **triển khai nhiều interface**. Điều đó không phá quy tắc đơn kế thừa lớp.

> **Phân biệt hai câu:** “Mỗi class chỉ có một superclass trực tiếp” là đúng với quan hệ kế thừa class của Java. “Một object chỉ có một supertype” là sai: object có thể có nhiều supertypes qua superclass chain và nhiều interfaces.

Đây là nền tảng để hiểu `extends`, tính thay thế subtype, constructor chaining, override methods, dynamic dispatch và mọi object có các khả năng chung từ `Object`.

## 2. `java.lang.Object` là gì?

`java.lang.Object` là **lớp gốc (*root class*)** của hệ thống lớp Java. Hầu hết những object được tạo từ class (kể cả class tự viết, các class thư viện, array objects, enum instances và record instances) đều có `Object` trong hệ thống supertypes thích hợp.

`Object` cung cấp các phương thức chung như:

- `equals(Object)` — hợp đồng so sánh bằng nhau.
- `hashCode()` — mã băm, liên quan tới contract `equals`.
- `toString()` — biểu diễn đối tượng dạng chuỗi.
- `getClass()` — trả runtime `Class` object của receiver.
- `wait(...)`, `notify()`, `notifyAll()` — cơ chế monitor của object.
- `clone()` — protected method với quy tắc clone riêng.
- `finalize()` — API cũ đã bị deprecate và không nên dùng để thiết kế lifecycle; trên các phiên bản hiện đại đã được đánh dấu cần loại bỏ.

Những methods này không đều có cùng access modifier hay cùng khả năng override. Ví dụ `toString` và `equals` có thể override hợp lệ; `getClass` là final, nên không thể override.

`java.lang` được import tự động theo quy tắc Java. Vì vậy trong source thông thường bạn có thể viết `Object` thay vì `java.lang.Object` mà không phải khai báo `import java.lang.Object;`.

**Lưu ý:** Root class không có nghĩa mọi biến trong Java đều có kiểu Object. `int`, `boolean` và các kiểu nguyên thủy khác **không phải class và không kế thừa Object**.

## 3. Viết `extends Object` hay bỏ `extends` đều được

Hai class declaration dưới đây có cùng ý nghĩa về **superclass trực tiếp**:

```java
class Book {
}
```

```java
class Book extends Object {
}
```

Đây là **hai cách khai báo thay thế cùng tên `Book`**, không đặt cạnh nhau trong cùng source file/package.

Với class thông thường không có superclass được chỉ định, Java coi `Object` là superclass trực tiếp. Viết `extends Object` tường minh **hợp lệ** nhưng thường **thừa**, vì không làm class kế thừa thêm một khả năng nào so với mặc định.

### Chương trình Java 17+ kiểm tra superclass bằng reflection

Tạo tệp **`ImplicitObjectDemo.java`**:

```java
class Plain {
}

class Explicit extends Object {
}

public class ImplicitObjectDemo {
    public static void main(String[] args) {
        System.out.println(Plain.class.getSuperclass().getSimpleName());
        System.out.println(Explicit.class.getSuperclass().getSimpleName());

        Plain plain = new Plain();
        System.out.println(plain instanceof Object);
        System.out.println(plain.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy:

```bash
javac ImplicitObjectDemo.java
java ImplicitObjectDemo
```

**Standard output:**

```text
Object
Object
true
Plain
```

Giải thích:

1. `Plain.class.getSuperclass()` trả `Object.class` vì Plain có superclass ngầm định.
2. `Explicit.class.getSuperclass()` cũng trả `Object.class`.
3. `plain instanceof Object` đúng vì instance của Plain là một object Java và Plain kế thừa Object.
4. `plain.getClass()` trả runtime class thực tế của receiver, ở đây là Plain.

Ví dụ dùng `Class.getSuperclass()` để **quan sát mô hình class**, không khẳng định JVM phải biểu diễn mọi quan hệ inheritance dưới dạng sơ đồ bộ nhớ như trên.

## 4. Vì sao `Object` không tự `extends` một lớp nào?

`Object` là điểm dừng của superclass chain. Nếu `Object` cũng có superclass khác thì nó không còn là root class.

Với `Class.getSuperclass()`:

- Trên class thông thường, trả đối tượng `Class` của superclass trực tiếp.
- Trên `Object.class`, trả `null` vì Object không có superclass.
- Trên interface, primitive type hoặc `void`, `getSuperclass()` cũng trả `null` theo API này; những giá trị null đó **không đồng nghĩa tất cả đều là root class như Object**.

### Ví dụ runnable

Tệp **`ObjectRootDemo.java`**:

```java
public class ObjectRootDemo {
    public static void main(String[] args) {
        System.out.println(Object.class.getSuperclass() == null);
        System.out.println(Runnable.class.getSuperclass() == null);
        System.out.println(int.class.getSuperclass() == null);
        System.out.println(String.class.getSuperclass().getSimpleName());
    }
}
```

```bash
javac ObjectRootDemo.java
java ObjectRootDemo
```

```text
true
true
true
Object
```

Ba giá trị `true` đầu có **nguyên nhân khác nhau**:

- `Object` là class gốc nên không có superclass.
- `Runnable` là interface, không phải class có superclass chain như ordinary class.
- `int` là kiểu nguyên thủy, không có superclass.

`String` là một class final kế thừa trực tiếp từ Object, nên kết quả dòng cuối là `Object`.

## 5. Quy tắc: một class không thể `extends` hai class cùng lúc

Java không cho phép:

```java
// Sai cú pháp Java:
// class Student extends Person, Account {
// }
```

Không có “hai superclass trực tiếp” cho một class declaration. Đây là **lỗi compile-time**, không phải trường hợp JVM tùy ý chọn superclass nào.

Một cách diễn đạt rõ:

```java
class Person {
}

class Student extends Person {
}
```

`Student` chỉ có `Person` là direct superclass. Nếu Student cần tài khoản, địa chỉ hoặc công cụ học, thông thường sử dụng **quan hệ has-a/composition** chứ không cố đưa chúng vào danh sách `extends`.

```java
class Student extends Person {
    private final StudyNotebook notebook = new StudyNotebook();
}

class StudyNotebook {
}
```

Trong ví dụ này, `Student` kế thừa `Person` và **có một `StudyNotebook` component**. Đây là khai báo hợp lệ; nó không có hai superclasses.

**Lưu ý thiết kế:** Không phải thiếu đa kế thừa class khiến mọi quan hệ phải dùng composition. Kế thừa vẫn hợp lý khi subclass thực sự là một dạng của superclass theo contract. Composition phù hợp khi đối tượng **có/sử dụng** thành phần khác.

## 6. Đơn kế thừa class không cấm nhiều interfaces

Một class có thể kế thừa **một class** và triển khai **nhiều interfaces**:

```java
class Person {
}

interface Named {
    String name();
}

interface Identified {
    int id();
}

class Student extends Person implements Named, Identified {
    private final String name;
    private final int id;

    Student(String name, int id) {
        this.name = name;
        this.id = id;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public int id() {
        return id;
    }
}
```

Ở đây:

- `Person` là **một** superclass trực tiếp của Student.
- `Named` và `Identified` là **hai direct superinterfaces**.
- Student có thể được sử dụng qua kiểu `Student`, `Person`, `Named`, `Identified` và `Object` khi phù hợp.
- Triển khai nhiều interfaces không biến Java thành ngôn ngữ đa kế thừa **lớp**.

### Ví dụ chạy độc lập với nhiều supertypes

Tệp **`MultipleInterfacesDemo.java`**:

```java
interface Named {
    String name();
}

interface Identified {
    int id();
}

class Person {
}

class Student extends Person implements Named, Identified {
    @Override
    public String name() {
        return "An";
    }

    @Override
    public int id() {
        return 7;
    }
}

public class MultipleInterfacesDemo {
    public static void main(String[] args) {
        Student student = new Student();

        Named named = student;
        Identified identified = student;
        Person person = student;
        Object object = student;

        System.out.println(named.name());
        System.out.println(identified.id());
        System.out.println(person instanceof Student);
        System.out.println(object instanceof Named);
    }
}
```

```bash
javac MultipleInterfacesDemo.java
java MultipleInterfacesDemo
```

```text
An
7
true
true
```

Các biến trên giữ **cùng một Student object**, chỉ khác **kiểu tham chiếu khi compiler kiểm tra lời gọi**. Không hề tạo ra một object Person và hai object interface riêng.

## 7. Interface có thể `extends` nhiều interfaces

Với interface, cú pháp `extends` có thể liệt kê **nhiều superinterfaces**:

```java
interface Readable {
    String read();
}

interface Writable {
    void write(String text);
}

interface ReadWrite extends Readable, Writable {
}
```

Điều này là **đa kế thừa interface**, không trái quy tắc single **class** inheritance. Class implements `ReadWrite` cần thực hiện những instance abstract methods bắt buộc theo contract (trừ khi chính class abstract/được kế thừa implementation thích hợp).

Vì interfaces có thể có `default` methods, Java còn có các quy tắc giải quyết xung đột; khi hai defaults cùng chữ ký không được giải quyết tự động, implementer có thể phải override. Các quy tắc ấy không biến việc triển khai hai interfaces thành việc có hai superclass classes.

### Interface không `extends Object`

Điểm tinh tế: một interface như `Readable` **không viết và không ngầm kế thừa `Object` theo cùng cơ chế superclass của class**.

Dù vậy, object thực tế implement interface vẫn là một `Object` instance, và Java cho phép nhiều lời gọi tới public methods từ Object qua interface-typed reference theo quy tắc interface method members/lookup.

Ví dụ:

```java
Readable readable = new Document();
System.out.println(readable.toString());
```

Đoạn này là **mảnh minh họa** giả định `Document implements Readable`. `readable.toString()` có thể compile vì public Object method tương ứng có thể gọi; không được suy từ đó rằng `Readable extends Object` là một câu lệnh Java hợp lệ.

## 8. Một object là subtype của mọi lớp tổ tiên trên cùng chuỗi

Nếu:

```java
class Animal {
}

class Mammal extends Animal {
}

class Dog extends Mammal {
}
```

một `Dog` là:

- Một `Dog`.
- Một `Mammal` theo quan hệ kế thừa lớp.
- Một `Animal`.
- Một `Object`.

Quan hệ này cho phép **upcasting**:

```java
Dog dog = new Dog();
Mammal mammal = dog;
Animal animal = dog;
Object object = dog;
```

Bốn references có thể trỏ cùng một object Dog. Không có chuyển đổi “cắt mất phần Dog” như một số người liên tưởng từ ngôn ngữ khác. Giá trị runtime vẫn là cùng object.

### Ví dụ runnable kiểm tra `instanceof`

Tệp **`SubtypeChainDemo.java`**:

```java
class Animal {
}

class Mammal extends Animal {
}

class Dog extends Mammal {
}

public class SubtypeChainDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();

        Animal animal = dog;
        Object root = animal;

        System.out.println(dog instanceof Mammal);
        System.out.println(dog instanceof Animal);
        System.out.println(animal instanceof Dog);
        System.out.println(root instanceof Object);
        System.out.println(root.getClass().getSimpleName());
    }
}
```

```bash
javac SubtypeChainDemo.java
java SubtypeChainDemo
```

```text
true
true
true
true
Dog
```

`getClass()` phản ánh **runtime class Dog**, không trả Animal hay Object chỉ vì tham chiếu đã được gán lên một supertype.

## 9. Upcast không làm mất runtime identity, nhưng giới hạn method nhìn thấy khi biên dịch

Một biến kiểu `Object` chỉ cho compiler biết những methods có sẵn qua kiểu Object (và các đặc điểm của expression theo quy tắc ngôn ngữ). Vì vậy:

```java
Object object = new Dog();

// object.bark(); // Không hợp lệ nếu bark chỉ thuộc Dog.
```

**Không phải Dog object đã mất `bark()`**. Vấn đề là **kiểu tĩnh của biến `object`** không khai báo method ấy.

Bạn có thể kiểm tra và downcast khi chắc object có runtime type phù hợp:

```java
if (object instanceof Dog dog) {
    dog.bark();
}
```

Java 17 hỗ trợ **pattern matching cho `instanceof`** như trên. Việc kiểm tra runtime type trước khi sử dụng subtype-specific behavior giúp giảm nguy cơ `ClassCastException`.

### Chương trình runnable

Tệp **`UpcastAndPatternDemo.java`**:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    String breed() {
        return "shepherd";
    }
}

public class UpcastAndPatternDemo {
    public static void main(String[] args) {
        Object value = new Dog();

        System.out.println(value.getClass().getSimpleName());

        if (value instanceof Dog dog) {
            System.out.println(dog.breed());
            System.out.println(dog.sound());
        }

        Animal animal = (Animal) value;
        System.out.println(animal.sound());
    }
}
```

```bash
javac UpcastAndPatternDemo.java
java UpcastAndPatternDemo
```

```text
Dog
shepherd
woof
woof
```

- `getClass` đọc runtime type.
- `instanceof Dog dog` kiểm tra và tạo pattern variable có kiểu Dog khi điều kiện đúng.
- `Dog.breed` chỉ nhìn thấy khi reference ở kiểu Dog.
- `animal.sound()` là instance call; dynamic dispatch tới override của Dog dù kiểu tĩnh của `animal` là Animal.

## 10. Kế thừa methods của `Object` và dynamic dispatch

`Object` là superclass nên ordinary classes có thể sử dụng public instance methods được kế thừa từ Object theo các quy tắc access/override.

Ví dụ `toString()` có thể override tại subclass:

```java
class Device {
    @Override
    public String toString() {
        return "Device";
    }
}

class Phone extends Device {
    @Override
    public String toString() {
        return "Phone";
    }
}
```

Một tham chiếu `Object` tới Phone vẫn gọi implementation `Phone.toString()`, bởi `toString` là overridable instance method.

### Ví dụ runnable dynamic dispatch từ `Object`

Tệp **`ObjectDispatchDemo.java`**:

```java
class Device {
    @Override
    public String toString() {
        return "Device";
    }
}

class Phone extends Device {
    @Override
    public String toString() {
        return "Phone";
    }
}

public class ObjectDispatchDemo {
    public static void main(String[] args) {
        Object a = new Device();
        Object b = new Phone();

        System.out.println(a.toString());
        System.out.println(b.toString());
        System.out.println(b.getClass().getSimpleName());
    }
}
```

```bash
javac ObjectDispatchDemo.java
java ObjectDispatchDemo
```

```text
Device
Phone
Phone
```

`toString()` được chọn theo runtime receiver khi override. `getClass()` là final method từ Object, không được override; nó trả đúng runtime Class object của Phone.

**Không nhầm:** chỉ vì method khai báo ban đầu trong Object không có nghĩa mọi subclass phải dùng implementation mặc định.

## 11. Constructor chain cũng đi tới `Object`

Quan hệ ngầm định với `Object` không chỉ ảnh hưởng methods. Khi tạo một object của ordinary class, constructor chain còn đi qua các superclass constructors và tới constructor của `Object` theo quy tắc.

Tệp **`ConstructorChainToObjectDemo.java`**:

```java
class Base {
    Base() {
        System.out.println("Base()");
    }
}

class Derived extends Base {
    Derived() {
        System.out.println("Derived()");
    }
}

public class ConstructorChainToObjectDemo {
    public static void main(String[] args) {
        Derived derived = new Derived();

        System.out.println(derived instanceof Object);
    }
}
```

```bash
javac ConstructorChainToObjectDemo.java
java ConstructorChainToObjectDemo
```

```text
Base()
Derived()
true
```

Trình tự ý nghĩa:

1. `new Derived()` yêu cầu tạo một Derived instance.
2. `Derived()` có lời gọi `super()` ngầm định tới `Base()` nếu không ghi explicit constructor invocation.
3. `Base()` có superclass `Object` ngầm định; constructor `Object()` được gọi trong chuỗi.
4. `Object()` không in gì ở ví dụ; sau đó `Base()` in `Base()`.
5. Trở về `Derived()`, nó in `Derived()`.
6. `derived instanceof Object` là true.

**Lưu ý:** `Object` có constructor không tham số accessible cho chuỗi kế thừa bình thường, nhưng không vì vậy mà được hiểu là mỗi object mang một “Object object riêng” được tạo và gán qua field. **Cùng một object** đang được khởi tạo qua constructor chain.

### `super()` không phải method `Object` được kế thừa

`super()` là **explicit constructor invocation**, không phải gọi một instance method. Constructors không được “kế thừa” như `toString()`; subclass cần định nghĩa constructors của mình nếu muốn những chữ ký đó.

## 12. Superclass có constructor tham số: không tự xuất hiện `super()` hợp lệ

Nếu superclass không có no-arg constructor accessible, subclass phải chọn một superclass constructor phù hợp.

Đoạn không biên dịch:

```java
// class Parent {
//     Parent(int id) { }
// }
//
// class Child extends Parent {
//     Child() { } // Ngầm gọi super(), nhưng Parent không có no-arg constructor.
// }
```

Sửa:

Tệp **`ExplicitSuperConstructorDemo.java`**:

```java
class Parent {
    private final int id;

    Parent(int id) {
        this.id = id;
        System.out.println("Parent id=" + id);
    }

    int id() {
        return id;
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child created");
    }
}

public class ExplicitSuperConstructorDemo {
    public static void main(String[] args) {
        Child child = new Child(12);

        System.out.println(child.id());
    }
}
```

```bash
javac ExplicitSuperConstructorDemo.java
java ExplicitSuperConstructorDemo
```

```text
Parent id=12
Child created
12
```

Một lớp có thể chỉ có một **superclass class trực tiếp**, nhưng superclass chain vẫn có thể dài. Constructor invocation từ Child vào Parent, từ Parent vào Object (ngầm định) tuân thủ thứ tự cần thiết.

## 13. Những phương thức public quan trọng nhất của `Object`

| Method | Ý nghĩa khái quát | Có override không? |
| --- | --- | --- |
| `equals(Object other)` | So sánh equality theo contract | **Có**, phải tôn trọng equality contract |
| `hashCode()` | Hash code, tương thích `equals` | **Có**, nhất quán với equals |
| `toString()` | Chuỗi biểu diễn object | **Có** |
| `getClass()` | Trả runtime Class object | **Không**, `final` |
| `wait()` / `wait(long)` / `wait(long,int)` | Chờ trên monitor của receiver theo điều kiện | **Không**, `final` |
| `notify()` | Đánh thức một thread đang chờ monitor đó theo quy tắc | **Không**, `final` |
| `notifyAll()` | Đánh thức các threads đang chờ monitor đó theo quy tắc | **Không**, `final` |

Một số phương thức khác của Object có access/đặc điểm khác:

- `clone()` là `protected`; clone semantics liên quan `Cloneable` và quy tắc riêng, **không tự trở thành public trên mọi object**.
- `finalize()` cũng tồn tại trong API lịch sử Java nhưng bị deprecated for removal trong Java 17; không nên viết logic tài nguyên dựa vào thời điểm finalize chạy.
- `Object()` là **constructor**, không phải instance method được thừa hưởng.

**Không nên** mô tả các methods từ Object như một “interface” bắt buộc subclass phải implement. Chúng có implementation theo Object (trừ những quy tắc override và access được quy định) và có thể được dùng trực tiếp khi phù hợp.

## 14. `toString()` mặc định có thể khó đọc; nên override khi cần

Nếu class không override `toString()`, implementation của Object thường tạo dạng dựa trên tên class, ký tự `@` và biểu diễn hex của hash code. Giá trị thực tế của hash code **không thể dự đoán cố định** và **không được giả định là địa chỉ bộ nhớ object**.

Để kết quả log dễ hiểu và test ổn định, nhiều class tự override:

Tệp **`ObjectToStringDemo.java`**:

```java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book[title=" + title + "]";
    }
}

public class ObjectToStringDemo {
    public static void main(String[] args) {
        Book book = new Book("Java Core");

        Object asObject = book;

        System.out.println(book);
        System.out.println(asObject.toString());
    }
}
```

```bash
javac ObjectToStringDemo.java
java ObjectToStringDemo
```

```text
Book[title=Java Core]
Book[title=Java Core]
```

`System.out.println(book)` sử dụng chuỗi biểu diễn object; cách override khiến output có ý nghĩa và không phụ thuộc hash code mặc định.

Không bắt buộc mọi class phải override `toString`, nhưng nếu muốn log/debug một value-like object, cách này thường hữu ích.

## 15. `equals(Object)` mặc định: so sánh cùng object

Implementation `equals` được kế thừa từ `Object` chỉ coi hai references bằng nhau khi chúng đại diện **cùng một object** theo identity equality (tương đương `==` cho trường hợp ấy).

Tệp **`ObjectEqualsIdentityDemo.java`**:

```java
class Token {
    private final String code;

    Token(String code) {
        this.code = code;
    }
}

public class ObjectEqualsIdentityDemo {
    public static void main(String[] args) {
        Token first = new Token("A");
        Token second = new Token("A");
        Token alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(alias));
    }
}
```

```bash
javac ObjectEqualsIdentityDemo.java
java ObjectEqualsIdentityDemo
```

```text
false
false
true
```

Hai Token objects có cùng `code="A"` nhưng là hai instances khác nhau, nên mặc định `equals` không xem chúng bằng nhau. Nếu domain muốn so sánh value theo code, class cần override `equals`/`hashCode` nhất quán, hoặc dùng type có value semantics như record khi phù hợp.

### Không nhầm `==` với `equals`

- `a == b` khi cả hai là references kiểm tra chúng có cùng giá trị tham chiếu không.
- `a.equals(b)` là lời gọi instance method, có thể có implementation khác ở runtime class.
- Nếu `a` là null thì `a.equals(b)` gây `NullPointerException`; có thể dùng `Objects.equals(a,b)` khi cần null-safe equality.
- `String.equals` so sánh nội dung theo contract của String, **không dùng identity equality mặc định của Object**.

## 16. Override `equals` thì phải nhất quán với `hashCode`

Contract quan trọng: nếu `a.equals(b)` là true, `a.hashCode()` và `b.hashCode()` phải có kết quả bằng nhau theo yêu cầu. Ngược lại, hai object có cùng hash code **không nhất thiết equals**.

Ví dụ một immutable value-like class:

Tệp **`ObjectEqualsHashDemo.java`**:

```java
import java.util.Objects;

final class ProductId {
    private final String value;

    ProductId(String value) {
        this.value = Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ProductId id)) {
            return false;
        }
        return value.equals(id.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return "ProductId[" + value + "]";
    }
}

public class ObjectEqualsHashDemo {
    public static void main(String[] args) {
        ProductId first = new ProductId("P1");
        ProductId second = new ProductId("P1");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

```bash
javac ObjectEqualsHashDemo.java
java ObjectEqualsHashDemo
```

```text
false
true
true
ProductId[P1]
```

Điểm học:

1. Method override có chữ ký `public boolean equals(Object other)`, không phải chỉ `equals(ProductId)`.
2. Pattern matching `instanceof ProductId id` dùng được trên Java 17.
3. Hai ProductId objects khác nhau về identity nhưng bằng nhau về giá trị `value` theo contract class.
4. `hashCode` nhất quán với `equals` nhờ dựa trên cùng field.
5. Class `final` tránh một số phức tạp của equality khi subclass thêm state.

**Không suy rằng** `hashCode()` chính là địa chỉ vật lý hoặc phải duy nhất cho từng object; hai giá trị khác nhau có thể trùng mã băm.

## 17. Các phương thức Object nào không cho override?

Một số methods của Object là `final`, ví dụ:

```java
final Class<?> getClass()
final void notify()
final void notifyAll()
final void wait() throws InterruptedException
```

Đoạn trên là **danh sách chữ ký rút gọn để đọc hiểu**; `wait` còn các overloads. Đây không phải source class hợp lệ để đặt nguyên văn vào file của bạn.

Do `final`:

- Subclass không thể override `getClass()` để “giả mạo” runtime class.
- Subclass không thể override những phiên bản `wait`/`notify`/`notifyAll` final của Object.
- Bạn vẫn có thể **gọi** public final methods khi đáp ứng điều kiện API.

Đặc biệt, các method `wait`/`notify` được dùng với **monitor của chính object receiver**; nếu gọi mà thread không giữ monitor đúng điều kiện, có thể ném `IllegalMonitorStateException`.

Cơ chế thread synchronization này **không phải** inheritance constructor chain, cũng không liên quan tới việc tạo nhiều superclasses. Trong code concurrent hiện đại, các tiện ích thuộc `java.util.concurrent` thường diễn đạt ý định rõ hơn khi phù hợp.

## 18. `Object` reference có thể giữ instances từ nhiều lớp khác nhau

Do Object là supertype của class instances, một biến kiểu Object có thể lần lượt giữ references tới những object khác nhau:

```java
Object item = "Java";
item = Integer.valueOf(42);
item = new StringBuilder("text");
```

Ở mỗi lần gán, **biến** `item` đổi giá trị tham chiếu; object thực tế không bị chuyển kiểu hoặc bị thay code.

### Chương trình runnable với các loại giá trị

Tệp **`ObjectReferenceDemo.java`**:

```java
public class ObjectReferenceDemo {
    public static void main(String[] args) {
        Object text = "Java";
        Object number = Integer.valueOf(42);
        Object array = new int[] {1, 2};

        System.out.println(text.getClass().getSimpleName());
        System.out.println(number.getClass().getSimpleName());
        System.out.println(array instanceof Object);
        System.out.println(array.getClass().isArray());
    }
}
```

```bash
javac ObjectReferenceDemo.java
java ObjectReferenceDemo
```

```text
String
Integer
true
true
```

`int[]` là **một array object**, vì vậy tham chiếu tới nó có thể được giữ trong Object variable. Nhưng từng phần tử `int` bên trong vẫn là primitive values, không phải `Integer` objects.

## 19. Primitive `int` không `extends Object`, còn wrapper `Integer` thì có

Một kiểu nguyên thủy như `int` không phải class, không có superclass và không trực tiếp chứa methods của Object.

Ví dụ sai:

```java
// int number = 42;
// number.getClass(); // Sai: int là primitive, không có instance method.
```

Nhưng khi boxing:

```java
Object boxed = 42;
```

Java có thể **autobox** giá trị `int` thành một `Integer` object rồi gán reference tới kiểu Object. Đây là **conversion**, không phải vì `int extends Object`.

### Ví dụ chạy

Tệp **`BoxingObjectDemo.java`**:

```java
public class BoxingObjectDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Object boxed = primitive;

        System.out.println(boxed instanceof Integer);
        System.out.println(boxed.getClass().getSimpleName());
        System.out.println(((Integer) boxed).intValue());
    }
}
```

```bash
javac BoxingObjectDemo.java
java BoxingObjectDemo
```

```text
true
Integer
42
```

**Nhớ:** autoboxing giúp dùng primitive value ở nhiều context yêu cầu reference type. Nó **không biến bản thân kiểu `int` thành subclass của Object**.

## 20. Array objects có quan hệ với `Object` nhưng không khai báo `extends`

Mảng Java được tạo bằng cú pháp:

```java
int[] numbers = new int[3];
String[] names = new String[2];
```

Mảng là **object**. Một array object:

- Có thể được gán cho biến kiểu `Object`.
- Có các methods phù hợp từ Object (như `getClass`, `toString`).
- Có runtime array class riêng do JVM tạo/quản lý.
- Có thể được xem là thực hiện `Cloneable` và `java.io.Serializable` theo các quy tắc của Java arrays.
- Có `length` **field** đặc biệt, không phải instance method `length()` của Object.

Không có source code `class int[] extends Object` mà người lập trình viết theo cú pháp class declaration.

Tệp **`ArrayObjectRelationDemo.java`**:

```java
public class ArrayObjectRelationDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        Object object = numbers;

        System.out.println(object instanceof Object);
        System.out.println(object instanceof Cloneable);
        System.out.println(object instanceof java.io.Serializable);
        System.out.println(numbers.length);
        System.out.println(object.getClass().isArray());
    }
}
```

```bash
javac ArrayObjectRelationDemo.java
java ArrayObjectRelationDemo
```

```text
true
true
true
3
true
```

**Không nhầm** array object với **kiểu primitive của các elements**. `int` primitive, nhưng `int[]` là reference type đại diện array object.

### Array covariance không phải đa kế thừa class

Java arrays kiểu reference có covariant subtype rules trong những điều kiện thích hợp, ví dụ `String[]` có thể upcast thành `Object[]`. Tuy nhiên, viết một phần tử sai runtime component type có thể ném `ArrayStoreException`. Đây là quy tắc array type system, **không** cho một class hai superclasses trực tiếp.

## 21. `record` là class, nhưng direct superclass không phải Object

Java 17 hỗ trợ `record`. Record class là một dạng class chuyên cho value-like data carriers, có superclass **`java.lang.Record`** được quy định bởi ngôn ngữ. Bản thân `Record` lại có superclass `Object`.

```text
java.lang.Object
        |
        v
java.lang.Record
        |
        v
record Point(int x, int y)
```

Người viết record **không tự chọn superclass** bằng `extends SomeClass`. Không vì vậy mà record có hai superclass trực tiếp; vẫn chỉ có một, do Java quy định.

### Ví dụ Java 17

Tệp **`RecordSuperclassDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordSuperclassDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(Point.class.getSuperclass().getSimpleName());
        System.out.println(point instanceof Object);
        System.out.println(point);
    }
}
```

```bash
javac RecordSuperclassDemo.java
java RecordSuperclassDemo
```

```text
Record
true
Point[x=2, y=3]
```

Record còn có những implementations được tạo cho `equals`, `hashCode` và `toString` theo contract records. Những methods ấy liên quan Object nhưng **không chứng minh mọi object bình thường có value-based equality tự động**.

**Lưu ý:** Một record chứa mutable component reference như `StringBuilder` hoặc array **không tự deep immutable**. Quy tắc superclass và tính bất biến nội dung là hai vấn đề khác nhau.

## 22. `enum` cũng là class đặc biệt với superclass `Enum`

Một enum Java có superclass do ngôn ngữ xác định: `java.lang.Enum` (thường được hiểu theo generic form `Enum<E>` đối với enum type `E`). `Enum` là một class và kế thừa `Object`.

```text
java.lang.Object
        |
        v
java.lang.Enum
        |
        v
enum Status { NEW, DONE }
```

Bạn không thể khai báo:

```java
// enum Status extends SomeClass { NEW, DONE } // Không hợp lệ.
```

Enums vẫn có quan hệ với Object gián tiếp và có thể triển khai interfaces theo quy tắc enum.

### Ví dụ runnable

Tệp **`EnumSuperclassDemo.java`**:

```java
enum Status {
    NEW, DONE
}

public class EnumSuperclassDemo {
    public static void main(String[] args) {
        System.out.println(Status.class.getSuperclass().getSimpleName());

        Object value = Status.NEW;
        System.out.println(value instanceof Enum);
        System.out.println(value instanceof Object);
        System.out.println(value.toString());
    }
}
```

```bash
javac EnumSuperclassDemo.java
java EnumSuperclassDemo
```

```text
Enum
true
true
NEW
```

`Status.NEW` là enum constant thuộc runtime enum class Status. Nó có `Object` trong superclass chain qua `Enum` nhưng không có hai superclass classes.

**Đừng nhầm:** Có thể có constant-specific class bodies trong enum và một số chi tiết runtime class, nhưng cách học căn bản về superclass trực tiếp của enum declaration là quan hệ với `java.lang.Enum`.

## 23. `final` class: vẫn kế thừa Object, nhưng không thể bị subclass

Một `final class` có thể **kế thừa một superclass**, nhưng không thể làm superclass cho một subclass mới do client khai báo.

```java
final class Receipt {
}
```

`Receipt` không ghi `extends`, nên kế thừa trực tiếp Object. Nhưng:

```java
// class SpecialReceipt extends Receipt { } // Lỗi: Receipt là final.
```

`final` không có nghĩa “Receipt không kế thừa ai”; nó chỉ giới hạn **khả năng các classes khác extends Receipt**.

Ví dụ quan trọng trong JDK là `String`: đây là final class và có Object làm superclass. Nhiều value classes/các class khác cũng có thể final mà vẫn giữ quan hệ Object đúng quy tắc.

## 24. `abstract` class: vẫn chỉ có một superclass trực tiếp

`abstract` cho phép class diễn đạt một abstraction chưa có implementation đầy đủ và không cho tạo instance trực tiếp bằng `new AbstractClass()`.

```java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
```

`Shape` không ghi `extends`, nên superclass trực tiếp của nó là Object. `Circle` extends một class là Shape. Dù Shape có abstract method, nó **không phải interface** và vẫn tuân thủ đơn kế thừa class.

Một abstract class có thể tự extends một superclass và implements nhiều interfaces. Nó không được có hai direct superclass classes.

**Lưu ý:** abstract class vẫn có constructors dùng trong subclass constructor chaining, static/instance fields và implemented instance methods. Không thể kết luận “abstract nên không có Object”.

## 25. `sealed` class giới hạn subclasses, không cho đa kế thừa class

Java 17 có `sealed` types, dùng để kiểm soát những types nào được phép kế thừa/triển khai trong cùng hệ phân cấp phù hợp.

Ví dụ:

```java
sealed class Vehicle permits Car, Bike {
}

final class Car extends Vehicle {
}

final class Bike extends Vehicle {
}
```

`Vehicle` không ghi `extends` nên vẫn kế thừa Object. `Car` và `Bike` mỗi class có một superclass trực tiếp là Vehicle.

`sealed` kiểm soát **danh sách direct subclasses được phép**, không thay quy tắc mỗi class chỉ có một superclass trực tiếp. Các subclass hợp lệ phải đáp ứng quy tắc `final`, `sealed` hoặc `non-sealed` trong bối cảnh áp dụng.

Nếu cần một class thể hiện nhiều capabilities, dùng nhiều interfaces thay vì cố tạo “sealed multiple class inheritance”.

## 26. `Object` không làm mọi phép ép kiểu trở nên hợp lệ

Mặc dù mọi ordinary class instance đều là Object, bạn **không thể** tự ý downcast một Object reference về bất cứ class nào mà không có tương thích runtime.

Tệp **`ObjectCastDemo.java`**:

```java
class Cat {
    String meow() {
        return "meow";
    }
}

class Dog {
    String bark() {
        return "woof";
    }
}

public class ObjectCastDemo {
    public static void main(String[] args) {
        Object value = new Cat();

        System.out.println(value instanceof Cat);
        System.out.println(value instanceof Dog);

        try {
            Dog wrong = (Dog) value;
            System.out.println(wrong.bark());
        } catch (ClassCastException ex) {
            System.out.println("invalid downcast");
        }

        Cat cat = (Cat) value;
        System.out.println(cat.meow());
    }
}
```

```bash
javac ObjectCastDemo.java
java ObjectCastDemo
```

```text
true
false
invalid downcast
meow
```

`Cat` và `Dog` có thể cùng thừa hưởng Object, nhưng chúng là **hai class branches khác nhau**. Một Cat object không tự biến thành Dog chỉ vì cả hai cùng có superclass Object.

Nếu không chắc type, dùng `instanceof` hoặc thiết kế abstraction chung phù hợp thay vì ép kiểu bừa bãi.

## 27. Object methods qua biến interface

Một interface **không có superclass Object như ordinary class**, nhưng Java cho phép những public Object methods thích hợp được nhìn thấy qua interface-typed reference.

Ví dụ runnable:

Tệp **`InterfaceObjectMethodsDemo.java`**:

```java
interface Named {
    String name();
}

final class Person implements Named {
    private final String value;

    Person(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }

    @Override
    public String toString() {
        return "Person(" + value + ")";
    }
}

public class InterfaceObjectMethodsDemo {
    public static void main(String[] args) {
        Named named = new Person("An");

        System.out.println(named.name());
        System.out.println(named.toString());
        System.out.println(named instanceof Object);
    }
}
```

```bash
javac InterfaceObjectMethodsDemo.java
java InterfaceObjectMethodsDemo
```

```text
An
Person(An)
true
```

Ở đây `named` có static type Named, nhưng runtime object là Person:

- `named.name()` gọi interface method implementation ở Person.
- `named.toString()` hợp lệ và dispatch tới `Person.toString()`.
- `named instanceof Object` true vì runtime value là Person instance, kế thừa Object qua class chain.

**Một cách nói chính xác:** Object là gốc superclass **của lớp hiện thực**, còn interface có bộ quy tắc method members/subtyping riêng; đừng dùng cú pháp `interface Named extends Object`.

## 28. Một superclass trực tiếp không có nghĩa superclass bắt buộc khai báo fields

Ví dụ:

```java
class Marker {
}

class Tagged extends Marker {
}
```

`Tagged` vẫn kế thừa Marker (và Object), dù Marker không có field, method riêng hoặc constructor tường minh. Kế thừa là **quan hệ kiểu trong ngôn ngữ**, không phải chỉ “copy các dòng code hữu ích”.

Tuy nhiên, kế thừa một class trống chỉ để làm marker type có thể không cần thiết. Một marker interface hoặc annotation đôi khi truyền đạt ý định linh hoạt hơn vì không chiếm slot superclass duy nhất của class.

**Nhìn từ thiết kế API:** Quyết định `extends SomeBase` ảnh hưởng tất cả subclasses tương lai; tránh chiếm khả năng kế thừa class chỉ cho một chi tiết dễ biểu diễn bằng interface/composition.

## 29. `Object` reference và collection tổng quát

Vì Object có thể giữ references tới nhiều class instances, một `List<Object>` có thể lưu nhiều loại:

```java
java.util.List<Object> values = java.util.List.of(
        "Java",
        Integer.valueOf(7),
        Boolean.TRUE
);
```

Nhưng khi đọc:

```java
Object value = values.get(0);
```

compiler chỉ biết `value` là Object. Nếu code cần operations đặc trưng của String, phải cast an toàn hoặc thiết kế generic collection có element type cụ thể hơn như `List<String>`.

### Ví dụ runnable

Tệp **`ObjectListDemo.java`**:

```java
import java.util.List;

public class ObjectListDemo {
    public static void main(String[] args) {
        List<Object> mixed = List.of("Java", 7, true);

        for (Object value : mixed) {
            System.out.println(value.getClass().getSimpleName()
                    + ":" + value);
        }
    }
}
```

```bash
javac ObjectListDemo.java
java ObjectListDemo
```

```text
String:Java
Integer:7
Boolean:true
```

Các literal primitive `7` và `true` được boxing thành wrapper objects khi truyền vào generic method phù hợp. Không phải vì primitive types có superclass Object.

**Đừng dùng `List<Object>` ở mọi nơi chỉ vì tiện.** Generic type cụ thể như `List<Student>` giúp compiler kiểm tra types, IDE gợi ý methods và tránh ép kiểu runtime không cần thiết.

## 30. Không có “object Object riêng nằm bên trong mọi object”

Một mô hình trực quan về hierarchy thường vẽ:

```text
Object
  |
  Animal
    |
    Dog
```

Đây là sơ đồ **quan hệ subtyping/class inheritance**, không phải khẳng định mỗi `new Dog()` tạo ba objects độc lập `Object`, `Animal` và `Dog`.

Trong Java:

```java
Dog dog = new Dog();
Animal a = dog;
Object o = dog;
```

Ba biến có thể tham chiếu **cùng một object**. `dog == a` và `a == o` đều là true khi các biến được gán như trên.

Các superclass constructors tham gia quá trình khởi tạo **cùng object đang được tạo** theo quy tắc instance initialization. Chúng không tạo một object mới cho từng superclass bằng `new Parent()`.

Cách hiểu này quan trọng khi phân tích aliasing, state, method override và identity.

## 31. Lưu ý về static methods và fields trong superclass

Một class con có thể sử dụng static members của superclass theo quy tắc inheritance/access, nhưng điều đó **không phải dynamic polymorphism** giống instance overrides.

```java
class Parent {
    static String name() {
        return "Parent";
    }
}

class Child extends Parent {
    static String name() {
        return "Child";
    }
}
```

Nếu:

```java
Parent p = new Child();
System.out.println(p.name()); // "Parent" — static method hiding.
```

Đây là **mảnh minh họa trong method**, không phải chương trình độc lập. Static method selection dựa trên compile-time information thích hợp, không dispatch theo runtime receiver như instance override.

**Quan hệ `extends Object` không biến static methods thành dynamic methods**. Để hiểu đa hình của Java, phải phân biệt:

- Instance method overriding → runtime dispatch.
- Static method hiding → compile-time method resolution.
- Field hiding → field được chọn theo compile-time type/lookup.
- Constructor → không override; được gọi trong constructor chain.

Đừng dựa vào object expression để gọi static method; dùng `Parent.name()` hoặc `Child.name()` rõ ràng hơn.

## 32. Lỗi thiết kế khi lạm dụng superclass gốc

Các câu viết kiểu “mọi thứ đều là Object nên chỉ cần truyền Object” thường dẫn đến thiết kế thiếu type safety:

```java
void process(Object value) {
    // Phải kiểm tra kiểu, ép kiểu và xử lý nhiều trường hợp.
}
```

Có các lựa chọn tốt hơn tùy nhu cầu:

- **Common superclass** khi có quan hệ is-a thật sự và shared instance behavior có ý nghĩa.
- **Interface** khi nhiều unrelated classes cùng hỗ trợ một capability.
- **Generics** khi thuật toán xử lý cùng cấu trúc nhưng giữ nguyên thông tin type.
- **Composition/delegation** khi class cần dùng object khác, không phải là subtype của nó.
- **Record/value object** khi cần mang dữ liệu với contract rõ.

Ví dụ nếu cả Printer và FileLogger đều `write(String)`, một interface `Writable` có thể hữu ích hơn việc buộc cả hai extends một abstract class chỉ để chia sẻ method signature. Nhờ implements nhiều interfaces, chúng vẫn có thể giữ quyền extends superclass thích hợp khác.

## 33. Những lỗi thường gặp trong bài tập về đơn kế thừa

| Sai lầm | Vì sao sai | Cách hiểu/cách sửa |
| --- | --- | --- |
| “Không viết `extends` thì class không có superclass” | Ordinary class có Object ngầm định | Xem `Class.getSuperclass()` |
| “Java cho `extends A,B`” | Một class chỉ có một direct superclass | Dùng implements interfaces/composition |
| “Mọi class trực tiếp extends Object” | Nhiều class extends superclass trung gian | Object có thể là ancestor gián tiếp |
| “Object cũng extends một superclass” | Object là root class | `Object.class.getSuperclass()==null` |
| “Interface ngầm `extends Object` như class” | Interface rules khác | Objects implement interface vẫn là Object |
| “`implements A,B` là đa kế thừa class” | A, B là interfaces | Phân biệt class vs interface |
| “Subclass có hai fields cùng tên là override fields” | Field hiding, không dynamic dispatch | Xem compile-time field access |
| “Upcast tạo một instance superclass mới” | Cùng object, reference type thay đổi | So sánh `==` |
| “Biến Object gọi trực tiếp mọi method subclass” | Compiler chỉ biết static type Object | Dùng interface/downcast an toàn |
| “Có chung superclass Object thì mọi cast đều hợp lệ” | Runtime object phải phù hợp target type | Dùng `instanceof`/pattern |
| “Object.equals mặc định so sánh field content” | Default equality dựa identity | Override equals/hashCode hoặc record |
| “Hashcode mặc định chính là địa chỉ RAM” | Không có contract đó | Không dựa vào địa chỉ |
| “Override equals mà không cần hashCode” | Phá contract của hash-based collections | Override cả hai nhất quán |
| “`getClass` có thể override như `toString`” | getClass là final | Dùng chính implementation từ Object |
| “Constructor Object không tham gia instance construction” | Constructor chain tới Object | Xét implicit/explicit super |
| “Tất cả final classes không có superclass” | Final chỉ cấm subclasses | Final class vẫn kế thừa |
| “Record trực tiếp extends Object” | Record extends `java.lang.Record` | Object là ancestor gián tiếp |
| “Enum trực tiếp extends Object” | Enum extends `java.lang.Enum` | Object là ancestor gián tiếp |
| “Array không phải object vì phần tử có thể là int” | Mảng là reference type/object | `array instanceof Object` |
| “int có `getClass()` vì boxing” | int primitive, boxing tạo Integer | Phân biệt conversion với inheritance |
| “Không khai báo constructor thì bỏ qua Object()” | Default constructor vẫn gọi superclass chain | Compiler chèn implicit invocation |
| “Có superclass không no-arg thì subclass không thể tồn tại” | Có thể gọi explicit `super(args)` | Cung cấp constructor hợp lệ |
| “Single inheritance đồng nghĩa một supertype duy nhất” | Một chuỗi tổ tiên + nhiều interfaces | Phân biệt direct superclass và supertypes |
| “Sealed cho phép class kế thừa nhiều classes” | Sealed giới hạn permitted subclasses | Vẫn một direct superclass |

## 34. Bài thực hành tổng hợp: dự đoán output trước khi chạy

Tệp **`SingleInheritanceTraceDemo.java`**:

```java
interface RunnableThing {
    void run();
}

class RootItem {
    RootItem() {
        System.out.println("RootItem()");
    }

    String label() {
        return "root";
    }
}

class SpecializedItem extends RootItem implements RunnableThing {
    SpecializedItem() {
        System.out.println("SpecializedItem()");
    }

    @Override
    String label() {
        return "special";
    }

    @Override
    public void run() {
        System.out.println("running");
    }

    @Override
    public String toString() {
        return "SpecializedItem";
    }
}

public class SingleInheritanceTraceDemo {
    public static void main(String[] args) {
        SpecializedItem item = new SpecializedItem();

        RootItem parent = item;
        Object root = item;
        RunnableThing task = item;

        System.out.println(parent.label());
        System.out.println(root.toString());
        System.out.println(item instanceof Object);
        System.out.println(item.getClass().getSuperclass().getSimpleName());
        task.run();
    }
}
```

```bash
javac SingleInheritanceTraceDemo.java
java SingleInheritanceTraceDemo
```

**Output:**

```text
RootItem()
SpecializedItem()
special
SpecializedItem
true
RootItem
running
```

### Lời giải chi tiết

1. `new SpecializedItem()` đi qua superclass constructor chain: `Object()` không in gì, `RootItem()` in, rồi `SpecializedItem()` in.
2. `RootItem parent = item` upcast reference; không tạo RootItem object mới.
3. `Object root = item` cũng trỏ cùng object SpecializedItem.
4. `RunnableThing task = item` trỏ cùng object qua interface type.
5. `parent.label()` là instance method override, dispatch tới `SpecializedItem.label()`, in `special`.
6. `root.toString()` gọi override của SpecializedItem, in `SpecializedItem`.
7. `item instanceof Object` true.
8. `item.getClass()` là SpecializedItem; superclass trực tiếp là RootItem, không phải Object, nên in `RootItem`.
9. `task.run()` gọi implementation interface instance method, in `running`.

**Bài học của chương trình:** một object có thể được nhìn qua **nhiều supertype references**, nhưng subclass vẫn chỉ có **một direct superclass class**.

## 35. Bài tập mở rộng có đáp án gợi ý

**Bài 1.** Hãy vẽ superclass chain của `class C extends B`, `class B extends A`, `class A`.

*Đáp án:* `Object → A → B → C`. C có B là direct superclass, A/Object là indirect ancestors.

**Bài 2.** `class D extends A, B` có hợp lệ không nếu A và B là classes?

*Đáp án:* Không. Java không hỗ trợ cú pháp đa kế thừa lớp.

**Bài 3.** `class D extends A implements X,Y` có hợp lệ không nếu X/Y là interfaces và methods cần thiết được cài đặt?

*Đáp án:* Có, nếu thỏa đầy đủ quy tắc inheritance, access, method implementation và không có xung đột chưa xử lý.

**Bài 4.** Nếu `class A` không có `extends`, `A.class.getSuperclass()` trả gì?

*Đáp án:* `Object.class` cho ordinary class thông thường.

**Bài 5.** Nếu `Object.class.getSuperclass()` được gọi, có exception không?

*Đáp án:* Không. Nó trả `null`.

**Bài 6.** Một `record Point(int x,int y)` có thể viết `extends Shape` không?

*Đáp án:* Không. Record class có direct superclass `java.lang.Record` do ngôn ngữ xác định.

**Bài 7.** `enum Direction` có direct superclass nào?

*Đáp án:* `java.lang.Enum`, không phải Object trực tiếp.

**Bài 8.** `Object o = new int[2];` có hợp lệ không?

*Đáp án:* Có. Mảng là object dù element type `int` nguyên thủy.

**Bài 9.** `Object o = 10;` có hợp lệ không?

*Đáp án:* Có khi boxing conversion áp dụng; nó không chứng minh `int` là subclass của Object.

**Bài 10.** Hai objects có `equals` true thì `hashCode` có phải giống nhau?

*Đáp án:* Có, theo hợp đồng equals/hashCode mà implementations cần tuân thủ.

**Bài 11.** Hai objects có `hashCode` bằng nhau thì có nhất thiết equals không?

*Đáp án:* Không. Hash collisions hợp lệ.

**Bài 12.** Nếu `Object o = new Dog();`, `o.bark()` có được compiler chấp nhận khi bark chỉ khai báo ở Dog không?

*Đáp án:* Không. Dùng Dog reference hoặc pattern matching/cast an toàn.

**Bài 13.** Lời gọi `o.toString()` có dùng override Dog không?

*Đáp án:* Có nếu Dog override toString hợp lệ; runtime dispatch vào implementation phù hợp.

**Bài 14.** `final class A` có thể `extends B` không?

*Đáp án:* Có khi B được phép kế thừa; `final` cấm các class khác extends A.

**Bài 15.** Nếu superclass có constructor `Base(int)` duy nhất, constructor subclass không viết `super(...)` có thể sai vì sao?

*Đáp án:* Implicit `super()` không tìm thấy no-arg superclass constructor accessible; phải gọi `super(value)` hợp lệ.

**Bài 16.** Interfaces có “superclass Object ngầm định” không?

*Đáp án:* Không theo ordinary class inheritance. Interface có quan hệ với public Object methods/subtyping theo quy tắc riêng; object implements interface vẫn có class chain tới Object.

**Bài 17.** Thấy một `String`, có thể viết `class MyString extends String` không?

*Đáp án:* Không. String là final class, không được subclass.

**Bài 18.** `Class.getSuperclass()` trả null cho interface có nghĩa interface là root class tương tự Object?

*Đáp án:* Không. Interface không phải class superclass chain kiểu đó.

## 36. Checklist để tự đánh giá hiểu đúng

- [ ] Tôi biết mỗi class bình thường chỉ có **một superclass trực tiếp**?
- [ ] Tôi biết không khai báo `extends` thì ordinary class kế thừa `Object` ngầm định?
- [ ] Tôi hiểu Object là root class và `Object.class.getSuperclass()==null`?
- [ ] Tôi phân biệt **direct superclass** với **superclass chain** và mọi supertypes?
- [ ] Tôi biết `implements` có thể liệt kê nhiều interfaces?
- [ ] Tôi hiểu interface `extends` nhiều interfaces nhưng không `extends Object` như ordinary class?
- [ ] Tôi phân biệt **is-a** và **has-a**, không dùng extends chỉ để tái sử dụng hành vi?
- [ ] Tôi có thể vẽ Object→A→B→C và giải thích upcast không tạo object mới?
- [ ] Tôi biết Object methods nào override được và `getClass` là final?
- [ ] Tôi hiểu `toString`, `equals` và `hashCode` có contract riêng?
- [ ] Tôi biết default Object equality khác value equality của String/record?
- [ ] Tôi dùng `instanceof` trước khi downcast khi runtime type chưa chắc?
- [ ] Tôi không nhầm boxing primitive với inheritance của primitive?
- [ ] Tôi biết mảng là objects và có quan hệ Object, Cloneable, Serializable?
- [ ] Tôi biết direct superclass của `record` là `Record` và `enum` là `Enum`?
- [ ] Tôi hiểu `final` và `sealed` giới hạn subclass nhưng không tạo nhiều superclasses?
- [ ] Tôi biết constructor chain của ordinary classes đi về `Object`?
- [ ] Tôi hiểu `super(...)` là constructor invocation, không phải method được kế thừa?
- [ ] Tôi phân biệt static method hiding với instance method overriding?
- [ ] Tôi có thể kiểm tra superclass bằng reflection và nhận diện các trường hợp trả `null` khác nhau?
- [ ] Tôi đã thử các chương trình Java 17+ có tên tệp đúng public class, lệnh `javac`/`java` và stdout đáng tin?

---

**Ghi nhớ cuối bài:** Java có **đơn kế thừa lớp**: mỗi ordinary class chỉ có **một superclass trực tiếp**. Nếu không viết `extends`, superclass ấy mặc định là **`java.lang.Object`**; với nhiều tầng `extends`, Object vẫn là lớp tổ tiên ở gốc. Java không cho `extends ClassA, ClassB` nhưng cho phép **implements nhiều interfaces** và interface có thể `extends` nhiều interfaces. Object cung cấp những methods chung như `equals`, `hashCode`, `toString`, `getClass` và góp mặt trong constructor chain; **upcast tới Object không tạo object mới**. Đừng nhầm ngoại lệ có quy tắc riêng: `record` trực tiếp extends `Record`, `enum` trực tiếp extends `Enum`, mảng là objects, còn primitive types không phải subclasses của Object. Hiểu đúng những điều này giúp xây quan hệ lớp chính xác, sử dụng đa hình an toàn và thiết kế API Java dễ bảo trì.