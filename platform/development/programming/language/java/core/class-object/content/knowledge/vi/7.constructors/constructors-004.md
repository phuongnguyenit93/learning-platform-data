# Hàm khởi tạo mặc định và điều kiện trình biên dịch tạo tự động trong Java

## 1. Khái niệm: constructor mặc định là gì?

Khi viết một lớp Java thông thường, người lập trình có thể khai báo constructor để quy định cách tạo đối tượng. Nhưng một lớp **không khai báo constructor nào** vẫn có thể được tạo bằng `new ClassName()`, miễn các điều kiện ngôn ngữ khác đều thỏa mãn. Lý do là trình biên dịch Java có thể **tự khai báo một constructor mặc định** (*default constructor*) cho lớp đó.

```java
class Book {
    String title;
}
```

Trong `Book` không hề có dòng `Book() { ... }`. Với trường hợp này, Java mặc nhiên cung cấp constructor **không tham số** để sử dụng:

```java
Book book = new Book();
System.out.println(book.title); // null
```

Hai dòng sau chỉ là **mảnh mã đặt trong method thích hợp**, không phải chương trình chạy độc lập. `Book` có thể được tạo do compiler cấp constructor mặc định; field `title` có giá trị tham chiếu mặc định `null` vì chưa có initializer tường minh.

**Phân biệt ngay từ đầu:**

- **Default constructor** theo thuật ngữ Java Language Specification (JLS): constructor **do compiler ngầm khai báo** khi một lớp thỏa điều kiện **không có bất kỳ constructor declaration nào**.
- **No-argument constructor / no-arg constructor**: constructor **không có tham số**. Nó có thể là **mặc định do compiler tạo** hoặc **được lập trình viên tự viết**.
- **Constructor có tham số**: ví dụ `Book(String title)`. Một khi lớp khai báo **ít nhất một constructor**, compiler **không còn tự tạo default constructor cho lớp ấy**, kể cả khi constructor hiện có không nhận tham số.

Trong các tài liệu nhập môn, “constructor mặc định” đôi khi được dùng lỏng để chỉ mọi constructor không tham số. Khi phân tích **điều kiện trình biên dịch tự tạo**, phải dùng nghĩa chính xác: **ngầm khai báo** khác với **tự khai báo**.

## 2. Quy tắc quyết định có tạo constructor mặc định

Đối với **class Java thông thường**, quy tắc quan trọng là:

> Nếu trong thân lớp **không có khai báo constructor nào**, Java ngầm khai báo một constructor mặc định. Nếu lớp đã có **bất kỳ constructor declaration nào**, compiler **không tự sinh thêm constructor mặc định**.

Bảng xét nhanh:

| Khai báo trong lớp | Compiler tự sinh default constructor? | `new X()` có nhất thiết hợp lệ? |
| --- | --- | --- |
| Không có constructor nào | **Có** | **Chưa chắc**: còn phụ thuộc class có abstract không, superclass có constructor không tham số truy cập được không, và khả năng truy cập chính lớp đó |
| Chỉ có `X() { ... }` do người viết | **Không** | Thường có thể nếu constructor và lớp truy cập được, class tạo instance được và constructor hợp lệ |
| Chỉ có `X(int id) { ... }` | **Không** | Không, trừ khi còn một constructor không tham số khác được khai báo |
| Có `X()` và `X(int)` | **Không** | Có thể dùng bản `X()` **do người viết** |
| Có `private X() { }` | **Không** | Chỉ gọi được ở phạm vi được phép truy cập constructor đó |
| Có method `void X() { }` nhưng không có constructor | **Có** | Phương thức tên `X` **không** được tính là constructor |

Đặc biệt, compiler không “nhìn thấy constructor có tham số rồi tự bổ sung bản rỗng cho tiện”. Sự có mặt của **một constructor do người viết** là đủ để chặn phát sinh default constructor.

### Mẹo nhận diện theo cú pháp

Constructor phải có **tên trùng đúng tên lớp** và **không có kiểu trả về**, kể cả `void`:

```java
class Lamp {
    Lamp() {                 // Constructor do người viết.
        System.out.println("construct");
    }

    void Lamp() {            // Method, KHÔNG phải constructor.
        System.out.println("method");
    }
}
```

Đây là khai báo hợp lệ. Vì đã có `Lamp()` nên compiler **không** thêm default constructor. Nếu bỏ khai báo `Lamp()` và chỉ giữ `void Lamp()`, lớp vẫn **không có constructor tự khai báo** và compiler sẽ cấp default constructor.

Tên method trùng tên lớp là một lựa chọn dễ gây hiểu lầm; trong mã mới nên dùng tên phương thức mô tả hành vi thực sự.

## 3. Mô hình tương đương: compiler sẽ tạo gì?

Xét lớp đơn giản:

```java
class Plain {
}
```

Về **hành vi gọi constructor thông thường**, có thể hình dung một constructor gần tương đương:

```java
class Plain {
    Plain() {
        super();
    }
}
```

**Đây là phép so sánh hai phiên bản riêng biệt, không phải hai khai báo để đặt chung trong một tệp.** Version thứ hai do người lập trình viết không còn là *default constructor* theo định nghĩa, dù có thể tạo object với kết quả tương đương.

Với lớp thông thường khác `java.lang.Object`, constructor mặc định gọi **constructor không tham số của superclass** thích hợp. Nếu không có `extends` tường minh, superclass trực tiếp mặc định là `java.lang.Object`. Sau đó, initializer của instance trong lớp hiện tại được thực hiện theo quy tắc, rồi constructor hoàn tất.

Constructor mặc định **không có logic tùy chỉnh** để tự tính tổng, gán mọi field bằng dữ liệu nghiệp vụ, kiểm tra giá trị hay tạo các object con. Nếu field có initializer hoặc lớp có instance initializer block, phần khởi tạo ấy vẫn chạy khi tạo instance — nhưng đó là **khai báo khởi tạo của field/block**, không phải mã nghiệp vụ do default constructor tự bịa ra.

### Ví dụ Java 17+ đầu tiên: class rỗng vẫn tạo object được

Lưu vào tệp **`DefaultConstructorDemo.java`**:

```java
class Student {
    String name;
    int grade;
}

public class DefaultConstructorDemo {
    public static void main(String[] args) {
        Student a = new Student();
        Student b = new Student();

        System.out.println(a.name);
        System.out.println(a.grade);
        System.out.println(a == b);
    }
}
```

Biên dịch và chạy:

```bash
javac DefaultConstructorDemo.java
java DefaultConstructorDemo
```

Kết quả chính xác:

```text
null
0
false
```

Giải thích:

1. Lớp `Student` không khai báo constructor, nên compiler ngầm tạo default constructor không tham số.
2. `new Student()` lần đầu và lần thứ hai tạo **hai instance khác nhau**; phép so sánh `a == b` là `false`.
3. `name` mặc định `null` và `grade` mặc định `0` bởi **quy tắc giá trị mặc định của instance field**, không phải do Java âm thầm chèn `name = null; grade = 0;` vào phần thân constructor theo nghĩa code nguồn.
4. Tệp có một top-level class `public` tên `DefaultConstructorDemo`, nên phải lưu đúng `DefaultConstructorDemo.java`. `Student` là top-level class package-private cùng tệp.

## 4. Viết một constructor có tham số: default constructor biến mất

Đây là tình huống gây lỗi biên dịch phổ biến nhất:

```java
class Product {
    private final String code;

    Product(String code) {
        this.code = code;
    }
}
```

Compiler thấy constructor `Product(String)` đã được khai báo nên **không** thêm `Product()`. Vì thế:

```java
Product one = new Product("P01"); // Hợp lệ.
// Product two = new Product();   // Lỗi: không tìm thấy constructor Product().
```

Đây là mảnh mã minh họa để đặt trong method; dòng lỗi đã được comment. Khi bỏ comment, thông báo của compiler thường cho biết constructor được yêu cầu không áp dụng được cho số/kiểu đối số đã truyền.

**Cách sửa có chủ đích:**

- Nếu sản phẩm **luôn phải có mã**, giữ duy nhất constructor nhận `String` và **không hỗ trợ `new Product()`**. Đây là cách bảo vệ invariant.
- Nếu API thực sự cần tạo sản phẩm với mã mặc định, **tự viết** constructor không tham số và điều phối nó sang constructor chính.

```java
class Product {
    private final String code;

    Product() {
        this("UNKNOWN");
    }

    Product(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

Hai constructor ở phiên bản này đều do người viết khai báo; không có default constructor ngầm nữa. `this("UNKNOWN")` là **constructor chaining**, chỉ tạo **một instance** và tái sử dụng quy tắc kiểm tra ở constructor có tham số.

### Ví dụ đầy đủ: trước và sau khi viết overload không tham số

Tạo tệp **`ExplicitNoArgDemo.java`**:

```java
class Cart {
    private final String owner;

    Cart() {
        this("guest");
    }

    Cart(String owner) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner required");
        }
        this.owner = owner;
    }

    String getOwner() {
        return owner;
    }
}

public class ExplicitNoArgDemo {
    public static void main(String[] args) {
        Cart first = new Cart();
        Cart second = new Cart("Lan");

        System.out.println(first.getOwner());
        System.out.println(second.getOwner());
    }
}
```

Lệnh:

```bash
javac ExplicitNoArgDemo.java
java ExplicitNoArgDemo
```

```text
guest
Lan
```

Tại đây **`Cart()` là constructor không tham số được khai báo tường minh**, không phải constructor mặc định do compiler tự tạo. Bởi constructor có tham số `Cart(String)` cũng tồn tại, nếu bỏ `Cart()`, lời gọi `new Cart()` sẽ lỗi biên dịch.

**Ý nghĩa thiết kế:** không tham số không đồng nghĩa trạng thái được khởi tạo đúng ý muốn. Nếu constructor không tham số thực sự cần tồn tại, lập trình viên nên chọn giá trị mặc định có nghĩa thay vì giả định các field `null`/`0` là hợp lệ.

## 5. Điều kiện quan trọng: superclass phải có constructor không tham số có thể gọi

Việc compiler **ngầm khai báo** constructor cho subclass không bảo đảm class sẽ **biên dịch thành công**.

Xét lớp cha:

```java
class Base {
    Base(int id) {
    }
}

class Derived extends Base {
}
```

Đây là ví dụ **cố ý không biên dịch**. `Base` có một constructor nhận `int`, nên **không có `Base()`**. `Derived` không tự khai báo constructor nên compiler muốn sinh `Derived()`, tương đương phần quan trọng:

```java
// class Derived extends Base {
//     Derived() {
//         super(); // Lỗi vì Base không có Base().
//     }
// }
```

Bởi `super()` không khớp một superclass constructor phù hợp, **lớp con vẫn lỗi biên dịch**. Không thể nói “không khai báo constructor là luôn gọi được `new Derived()`”.

### Hai hướng sửa

**Hướng A — lớp con khai báo constructor và gọi superclass constructor hợp lệ:**

```java
class Base {
    private final int id;

    Base(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}

class Derived extends Base {
    Derived() {
        super(7);
    }
}
```

Khi lớp con tự khai báo `Derived()`, không có default constructor ngầm của `Derived` nữa. Constructor này gọi `super(7)`, nên có thể biên dịch nếu `Base(int)` truy cập được.

**Hướng B — lớp cha cung cấp constructor không tham số:**

```java
class Base {
    Base() {
        System.out.println("Base()");
    }

    Base(int id) {
        System.out.println("Base(" + id + ")");
    }
}

class Derived extends Base {
    // Không khai báo constructor.
}
```

Trong phiên bản này, compiler ngầm khai báo `Derived()` hợp lệ vì `super()` gọi được `Base()`. Hai phiên bản trên là **hai phương án độc lập**, không đặt trùng các lớp cùng tên trong một tệp.

### Chương trình độc lập quan sát chuỗi mặc định

Tệp **`DefaultInheritanceDemo.java`**:

```java
class BaseMachine {
    BaseMachine() {
        System.out.println("BaseMachine()");
    }
}

class PrinterMachine extends BaseMachine {
    // Compiler tự tạo PrinterMachine(), gọi super().
}

public class DefaultInheritanceDemo {
    public static void main(String[] args) {
        new PrinterMachine();
        System.out.println("created");
    }
}
```

Chạy:

```bash
javac DefaultInheritanceDemo.java
java DefaultInheritanceDemo
```

```text
BaseMachine()
created
```

Ở đây `PrinterMachine` không khai báo constructor, nhưng default constructor của nó gọi được `BaseMachine()`. Điều này **không có nghĩa** compiler đã tự thêm `BaseMachine()`: constructor lớp cha này do người viết khai báo rõ.

## 6. Quyền truy cập ảnh hưởng đến việc gọi constructor mặc định

Default constructor có mức truy cập tương ứng với cách khai báo lớp thông thường theo quy tắc JLS (ví dụ top-level `public` hoặc package-private). Nếu code tại nơi gọi **không truy cập được lớp** hoặc **không truy cập được constructor**, `new X()` sẽ bị chặn.

### Lớp top-level không `public`

```java
class PackageItem {
}
```

`PackageItem` là top-level class **package-private** và constructor mặc định của nó cũng không cung cấp quyền truy cập công khai từ mọi package. Mã ở **cùng package** có thể `new PackageItem()` nếu không có rào cản khác; mã ở package khác không thể tham chiếu trực tiếp tới `PackageItem`.

### Lớp top-level `public`

Nếu tệp `PublicItem.java` có:

```java
public class PublicItem {
}
```

Compiler sinh default constructor có mức truy cập `public`. Mã từ package khác có thể gọi `new PublicItem()` nếu các điều kiện như class được nhìn thấy, module exports và classpath/module path đều thỏa mãn.

So sánh với constructor **tường minh package-private**:

```java
public class PublicItem {
    PublicItem() {
    }
}
```

Đây là **phiên bản khác** của `PublicItem.java`, không đặt đồng thời với phiên bản trước. Lớp vẫn `public`, nhưng constructor `PublicItem()` không khai báo `public` nên là **package-private**. Compiler **không** thêm default constructor khác. Vì vậy mã ở package ngoài có thể nhìn thấy kiểu `PublicItem` nhưng **không gọi được `new PublicItem()`**.

**Điểm then chốt:** constructor ngầm sinh có quyền truy cập theo quy tắc của default constructor, còn constructor **do bạn khai báo** có quyền truy cập dựa trên modifier bạn thực sự viết. Hai điều đó có thể khác nhau ngay cả với lớp `public`.

### Constructor `private` và static factory

```java
class Session {
    private final String id;

    private Session(String id) {
        this.id = id;
    }

    static Session guest() {
        return new Session("guest");
    }

    String id() {
        return id;
    }
}
```

Vì `Session` đã khai báo constructor `private Session(String)`, nó **không có default constructor**. Code bên ngoài không thể `new Session()`, cũng không được gọi constructor private từ ngữ cảnh không được phép. Thay vào đó, lớp chủ động cung cấp `Session.guest()` như một **static factory method**. Phương thức factory không phải constructor; nó gọi constructor ở bên trong phạm vi được phép.

Khi đọc lỗi `constructor X(...) has private access`, hãy kiểm tra **quyền truy cập**, không vội kết luận “không có constructor”. Lỗi “không tồn tại constructor với danh sách tham số này” và lỗi “constructor tồn tại nhưng không thể truy cập” là hai tình huống khác nhau.

## 7. `abstract class` vẫn có thể có default constructor

Một **abstract class** không thể được tạo instance trực tiếp, nhưng nó vẫn có thể cần constructor để khởi tạo phần lớp cha khi subclass được tạo.

```java
abstract class Task {
    private String status = "new";

    String status() {
        return status;
    }
}

class EmailTask extends Task {
    // Không khai báo constructor.
}
```

Cả `Task` và `EmailTask` đều không khai báo constructor, vì vậy compiler cung cấp default constructor phù hợp cho từng lớp. Nhưng:

```java
// Task invalid = new Task();  // Lỗi: không thể khởi tạo trực tiếp abstract class.
Task valid = new EmailTask();   // Hợp lệ trong ngữ cảnh truy cập phù hợp.
```

Hai dòng này là mảnh code để đặt trong method; dòng lỗi được comment. Khi gọi `new EmailTask()`, constructor mặc định của subclass sẽ gọi constructor mặc định thích hợp của `Task` để khởi tạo phần supertype.

### Ví dụ đầy đủ

Tạo tệp **`AbstractConstructorDemo.java`**:

```java
abstract class Animal {
    private String family = "animal";

    String family() {
        return family;
    }

    abstract String sound();
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

public class AbstractConstructorDemo {
    public static void main(String[] args) {
        Animal pet = new Cat();

        System.out.println(pet.family());
        System.out.println(pet.sound());
    }
}
```

```bash
javac AbstractConstructorDemo.java
java AbstractConstructorDemo
```

```text
animal
meow
```

`Animal` là abstract nên không thể tạo trực tiếp, nhưng default constructor của nó vẫn hợp lệ. `Cat` có constructor mặc định gọi `super()`, sau đó implementation `Cat.sound()` được dùng khi gọi qua biến kiểu `Animal`. Không nên suy ra từ việc abstract class không cho `new Animal()` rằng nó “không có constructor”.

## 8. Instance field initializer và instance initializer vẫn chạy khi chỉ có default constructor

Đừng nhầm “compiler tạo constructor ngầm” với “mọi instance field giữ nguyên giá trị mặc định cuối cùng”. Field và initializer vẫn có cơ chế khởi tạo riêng.

Tạo tệp **`DefaultWithInitializersDemo.java`**:

```java
class Counter {
    int value = 3;

    {
        value += 2;
        System.out.println("instance block: " + value);
    }

    // Không khai báo constructor.
}

public class DefaultWithInitializersDemo {
    public static void main(String[] args) {
        Counter first = new Counter();
        Counter second = new Counter();

        System.out.println(first.value);
        System.out.println(second.value);
    }
}
```

```bash
javac DefaultWithInitializersDemo.java
java DefaultWithInitializersDemo
```

```text
instance block: 5
instance block: 5
5
5
```

Trình tự logic cho mỗi instance `Counter`:

1. Instance field có **giá trị mặc định** khi được cấp phát: với `int` là `0`.
2. Constructor của superclass được gọi theo quy tắc.
3. Field initializer `int value = 3;` chạy, đặt `value = 3`.
4. Instance initializer block `{ value += 2; ... }` chạy, nên in `instance block: 5`.
5. Default constructor ngầm hoàn thành, không có thêm logic constructor do người lập trình viết.

Hai lần `new` cho hai instance độc lập nên block in **hai lần**, còn giá trị cuối của mỗi object là `5`.

### Static initializer không chạy một lần cho mỗi object

```java
class Device {
    static int created;

    static {
        System.out.println("Device class initialized");
    }

    {
        created++;
    }
}
```

Đoạn trên không có `main`. Lần khởi tạo lớp thích hợp sẽ chạy `static { ... }`, thường chỉ một lần cho mỗi class được khởi tạo trong class loader tương ứng; còn `{ created++; }` là **instance initializer** và chạy khi tạo mỗi object. Compiler vẫn có thể cấp default constructor cho `Device` vì hai block này **không phải constructor declaration**.

**Lưu ý:** Viết `static { ... }` hay `{ ... }` trong thân lớp không chặn default constructor. Điều kiện chặn là sự tồn tại của **constructor được khai báo**.

## 9. Constructor không tham số do người viết khác constructor mặc định ở đâu?

Bảng phân biệt:

| Tiêu chí | Default constructor | Constructor `X()` do người viết |
| --- | --- | --- |
| Ai khai báo? | Compiler tự khai báo ngầm theo ngữ pháp Java | Lập trình viên khai báo trong class |
| Điều kiện tồn tại | Lớp phù hợp **không có constructor declarations** | Người viết đặt trực tiếp `X() { ... }` |
| Số tham số hiển thị ở mã nguồn | Không có khai báo nguồn của constructor này | **0** |
| Có thể chứa validation/hành vi tùy chỉnh? | Không có body tùy chỉnh do người viết | Có thể, trong giới hạn hợp lệ của constructor |
| Có thể gọi `this(...)` tường minh? | Không do người viết khai báo body để làm việc ấy | Có, nếu có constructor đích thích hợp và tuân thủ quy tắc |
| Gọi superclass constructor | Dùng lời gọi ngầm tương ứng, thường là `super()` | Có thể `super(...)` hoặc `this(...)` tường minh, hoặc implicit `super()` phù hợp |
| Mức truy cập | Theo quy tắc default constructor của class | Theo modifier thực sự khai báo trên constructor |
| Làm mất constructor mặc định? | Là constructor mặc định | **Có**, sự xuất hiện của constructor này ngăn compiler sinh thêm một default constructor |
| Khi lớp thêm constructor có tham số | Default constructor không còn được tự tạo | Constructor `X()` đã viết vẫn tồn tại nếu không bị xóa |

Ví dụ minh họa hai **phiên bản riêng biệt**:

```java
// Phiên bản A:
class NoticeA {
}
// Compiler sinh NoticeA().

// Phiên bản B:
class NoticeB {
    NoticeB() {
        System.out.println("created");
    }
}
// Không có default constructor do compiler sinh cho NoticeB.
```

`NoticeA` và `NoticeB` đều gọi được bằng `new NoticeA()` và `new NoticeB()` khi ở ngữ cảnh truy cập phù hợp, nhưng chỉ bản B in thêm `created`. Một lời gọi `new X()` đơn độc không đủ để bạn biết constructor là **ngầm sinh** hay **tường minh**; phải xem khai báo lớp.

## 10. Lớp lồng nhau: có default constructor nhưng cú pháp tạo object còn phụ thuộc ngữ cảnh

Khi nói `new Inner()` có hợp lệ hay không, cần phân biệt **static nested class** với **non-static member (inner) class**.

```java
class Outer {
    static class StaticNested {
        // Không constructor declaration -> có default constructor.
    }

    class Inner {
        // Không constructor declaration -> có default constructor.
    }
}
```

Cả `StaticNested` lẫn `Inner` đều không khai báo constructor, nên có default constructor tương ứng. Nhưng cách tạo instance khác nhau:

```java
Outer.StaticNested a = new Outer.StaticNested();

Outer outer = new Outer();
Outer.Inner b = outer.new Inner();
```

Đây là **mảnh mã để đặt trong method**. Static nested class không cần instance của `Outer`. Non-static inner class lại gắn với một **enclosing instance**, nên ở ngoài `Outer` phải dùng cú pháp `outer.new Inner()` (với các điều kiện truy cập cho phép).

Về mặt triển khai, compiler có thể cần mang tham chiếu đến enclosing instance khi xây dựng non-static inner class. Điều đó **không có nghĩa** bạn phải tự khai báo `Inner(Outer outer)` trong nguồn chỉ để dùng default constructor.

### Ví dụ Java 17+ chạy được

Tệp **`NestedDefaultDemo.java`**:

```java
class House {
    private final String name = "Blue";

    class Room {
        String describe() {
            return name + " room";
        }
    }

    static class Key {
        String describe() {
            return "key";
        }
    }
}

public class NestedDefaultDemo {
    public static void main(String[] args) {
        House house = new House();
        House.Room room = house.new Room();
        House.Key key = new House.Key();

        System.out.println(room.describe());
        System.out.println(key.describe());
    }
}
```

```bash
javac NestedDefaultDemo.java
java NestedDefaultDemo
```

```text
Blue room
key
```

`House`, `Room` và `Key` đều không tự khai báo constructor. Vì vậy không cần viết constructor thủ công trong bất kỳ lớp nào để chạy ví dụ này. Nhưng cú pháp tạo `Room` cần một `House` cụ thể, còn `Key` thì không.

## 11. Các loại kiểu có quy tắc constructor đặc biệt

Quy tắc “không khai báo constructor → default constructor” ở phần đầu nhằm giải thích **class Java thông thường**. Khi sang **enum** hoặc **record**, Java có những quy tắc constructor chuyên biệt; không nên sao chép máy móc cách gọi `new ClassName()`.

### Enum: không khởi tạo bằng `new` từ mã ứng dụng

```java
enum Status {
    NEW, DONE
}
```

Đây là một enum hợp lệ. Giá trị enum được biểu diễn bằng các hằng `NEW` và `DONE` do ngôn ngữ quản lý. Không thể viết `new Status()` để tùy ý tạo enum instance như class thường. Enum constructors còn có các quy định đặc thù về quyền truy cập và cách khởi tạo.

Vì thế khi học default constructor cho **class thông thường**, đừng dùng `enum` làm ví dụ chứng minh rằng “không khai báo constructor thì `new X()` luôn được”.

### Record: thành phần record gắn với canonical constructor

```java
record Point(int x, int y) {
}
```

Java 17 hỗ trợ `record`. Khi không tự khai báo canonical constructor, record có **canonical constructor được sinh ngầm** theo thành phần của record; cách tạo object đúng ở đây là `new Point(2, 3)`, không phải một default no-arg constructor giống class rỗng. Nếu record có thành phần `x` và `y` mà bạn gọi `new Point()` mà không khai báo constructor phù hợp, sẽ lỗi vì thiếu đối số.

Record có thể có các constructor bổ sung trong những giới hạn đặc thù của record; điều kiện áp dụng không trùng hoàn toàn với lớp Java thông thường. Trọng tâm của bài này là default constructor **do compiler tạo cho class thông thường**.

### Anonymous class và các ngoại lệ nâng cao

Một anonymous class (ví dụ `new Runnable() { ... }`) có quy tắc ngầm khai báo constructor khác với class được đặt tên; nó gắn với biểu thức tạo anonymous object và siêu kiểu được khai báo. Không nên cố gọi một constructor của anonymous class bằng tên lớp vì anonymous class **không có tên lớp nguồn** để gọi như vậy.

Khi đọc đặc tả, các trường hợp enum, record, anonymous/local/inner classes có những chi tiết riêng. Để giải quyết những lỗi `new X()` cơ bản, trước hết kiểm tra **X là class thông thường hay loại khai báo đặc biệt**.

## 12. Điều gì xảy ra nếu constructor superclass không truy cập được?

Không chỉ **thiếu** constructor không tham số mới gây lỗi; **không có quyền truy cập** constructor đó cũng đủ khiến lớp con không thể gọi ngầm `super()`.

Ví dụ (hai class trong cùng một tệp, cùng package nhưng private constructor vẫn bị giới hạn theo lớp và quy tắc nested access):

```java
class LockedBase {
    private LockedBase() {
    }
}

class LockedChild extends LockedBase {
    // Compiler muốn tạo default constructor, gọi super().
    // Nhưng LockedBase() private nên không truy cập được từ đây.
}
```

Đây là **ví dụ cố ý không biên dịch**. `LockedBase()` tồn tại, nhưng là `private`, nên `LockedChild` không thể gọi nó. Trường hợp này khác với việc superclass chỉ khai báo constructor có tham số; ở cả hai trường hợp, điều cần thiết là **một constructor superclass không tham số có thể truy cập** nếu subclass cần implicit `super()`.

Nếu muốn cho phép subclass, hãy thiết kế superclass constructor có quyền truy cập phù hợp (ví dụ `protected` khi có ý định hỗ trợ kế thừa), hoặc cung cấp constructor superclass với tham số và yêu cầu subclass gọi rõ `super(args)` trong constructor do subclass khai báo.

### Ví dụ sửa hợp lệ

```java
class ParentRecord {
    private final String id;

    protected ParentRecord(String id) {
        this.id = id;
    }

    String id() {
        return id;
    }
}

class ChildRecord extends ParentRecord {
    ChildRecord() {
        super("child-default");
    }
}
```

Đây là khai báo lớp biên dịch được. `ChildRecord` **không có default constructor do compiler sinh** vì đã có `ChildRecord()` tự khai báo. Nó gọi được constructor `protected ParentRecord(String)` của superclass bằng `super("child-default")`.

Một lựa chọn khác là đưa constructor không tham số `protected ParentRecord()` vào superclass nếu việc tạo object từ mặc định thật sự có nghĩa. Không nên tạo constructor rỗng chỉ nhằm “hết lỗi compile” nếu superclass sẽ bị đặt vào trạng thái không hợp lệ.

## 13. Những điều trình biên dịch KHÔNG tự làm khi sinh default constructor

Việc tồn tại default constructor **không đảm bảo** các điều sau:

1. **Không tự sinh mọi overload cần thiết.** Class `Car { }` có thể có `Car()` ngầm, nhưng không tự có `Car(String model)` hoặc `Car(int year)`.
2. **Không sửa superclass thiếu constructor phù hợp.** Nếu superclass chỉ có `Base(int)`, compiler không tự sinh `Base()` bổ sung để giúp subclass.
3. **Không bỏ qua quyền truy cập.** Constructor superclass phải truy cập được; tại nơi gọi, class và constructor đích cũng phải truy cập được.
4. **Không vượt qua `abstract`.** Một abstract class có thể có default constructor nhưng vẫn không `new` trực tiếp được.
5. **Không tự khởi tạo dữ liệu nghiệp vụ hợp lệ.** Field kiểu tham chiếu mặc định `null` và kiểu số mặc định 0; nếu ràng buộc nghiệp vụ yêu cầu khác, phải dùng initializer, constructor hoặc thiết kế phù hợp.
6. **Không tự kiểm tra tham số.** Constructor mặc định không nhận tham số; nó không thể xác minh tên, mã, số lượng nhập vào.
7. **Không tự tạo “đối tượng con” cho field tham chiếu.** Ví dụ `Address address;` vẫn là `null` nếu chưa được khởi tạo.
8. **Không tạo object khi chỉ khai báo biến.** `User user;` chưa gọi constructor. Chỉ biểu thức tạo instance thích hợp (ví dụ `new User()`) mới khởi tạo một object.
9. **Không tạo default constructor nếu class đã có bất kỳ constructor declaration nào.** Kể cả một constructor private, protected, package-private, public hoặc bản không tham số do người viết.
10. **Không biến constructor thành method bình thường.** Constructor không có kiểu trả về và không được thừa hưởng/override như instance method.

Các giới hạn ấy giải thích phần lớn lỗi beginner khi thêm constructor đầu tiên hoặc mở rộng một class có constructor bắt buộc nhận tham số.

## 14. Một chương trình tổng hợp: mặc định, tường minh và kế thừa

Tạo tệp **`ConstructorCasesDemo.java`**:

```java
class EmptyBox {
    int size;
    // Compiler cấp EmptyBox().
}

class TaggedBox {
    private final String tag;

    TaggedBox() {
        this("untagged");
    }

    TaggedBox(String tag) {
        this.tag = tag;
    }

    String tag() {
        return tag;
    }
}

class DeviceBase {
    DeviceBase() {
        System.out.println("DeviceBase()");
    }
}

class MobileDevice extends DeviceBase {
    private String model = "Generic";

    // Không khai báo constructor.
    String model() {
        return model;
    }
}

public class ConstructorCasesDemo {
    public static void main(String[] args) {
        EmptyBox box = new EmptyBox();
        TaggedBox tagged = new TaggedBox();
        MobileDevice mobile = new MobileDevice();

        System.out.println("size=" + box.size);
        System.out.println("tag=" + tagged.tag());
        System.out.println("model=" + mobile.model());
    }
}
```

Chạy:

```bash
javac ConstructorCasesDemo.java
java ConstructorCasesDemo
```

Output:

```text
DeviceBase()
size=0
tag=untagged
model=Generic
```

Phân tích theo loại constructor:

- `EmptyBox`: **default constructor được compiler sinh** vì không có constructor declaration; field `size` mặc định `0`.
- `TaggedBox`: **không có default constructor ngầm**; `TaggedBox()` và `TaggedBox(String)` do người viết khai báo, bản không tham số dùng `this(...)` để khởi tạo `tag`.
- `DeviceBase`: có constructor **do người viết** là `DeviceBase()`; constructor ấy in `DeviceBase()` khi được gọi.
- `MobileDevice`: không có constructor declaration, nên compiler ngầm sinh default constructor và gọi `super()`; trước khi hoàn tất, field initializer đặt `model = "Generic"`.
- Thứ tự dòng `DeviceBase()` xuất hiện trước ba dòng `println` còn lại vì lệnh `new MobileDevice()` thực hiện constructor lớp cha **trước khi** luồng chính bắt đầu in các dòng thông tin cuối.

Ví dụ cũng cho thấy cùng một tệp Java có thể chứa nhiều top-level class package-private, nhưng chỉ có một top-level class `public` là `ConstructorCasesDemo`.

## 15. Khi nào nên dựa vào constructor mặc định?

Default constructor phù hợp trong các lớp có quá trình tạo object đơn giản, không cần nhận dữ liệu đầu vào bắt buộc, và các giá trị mặc định/field initializer đã đủ bảo đảm trạng thái.

Ví dụ:

```java
class TimerSettings {
    int retries = 3;
    boolean enabled = true;
}
```

Lớp không khai báo constructor, nên `new TimerSettings()` hợp lệ trong phạm vi truy cập tương ứng. Các field initializer tạo giá trị mặc định có ý nghĩa hơn `0` và `false` nếu thiết kế ứng dụng mong muốn `3` lần thử và trạng thái bật.

Ngược lại, nếu một object **bắt buộc phải có** mã, tên hoặc tham chiếu không null, constructor có tham số là cách thể hiện rõ hợp đồng:

```java
class Invoice {
    private final String number;

    Invoice(String number) {
        if (number == null || number.isBlank()) {
            throw new IllegalArgumentException("number required");
        }
        this.number = number;
    }

    String number() {
        return number;
    }
}
```

Ở đây việc compiler **không tự sinh** `Invoice()` là điều có lợi: nó ngăn caller tạo `Invoice` mà không cung cấp số hóa đơn.

### “Thêm constructor” có thể làm hỏng code cũ

Giả sử bản đầu:

```java
class Customer {
}
```

Code khác đã viết `new Customer()`. Sau đó bạn sửa thành:

```java
class Customer {
    Customer(String name) {
    }
}
```

Nếu **biên dịch lại** các nơi gọi, `new Customer()` sẽ bị lỗi vì default constructor đã biến mất. Để duy trì cách gọi không tham số, cần khai báo `Customer()` tường minh **và** bảo đảm trạng thái hợp lệ; không phải cứ thêm constructor mới là tự động giữ constructor cũ.

Đối với thư viện phát hành công khai, thay đổi từ constructor mặc định public sang chỉ constructor có tham số còn có thể ảnh hưởng tính tương thích của mã đã biên dịch, tùy cách API thay đổi. Kiểm thử API từ code khách hàng khi thêm constructor.

## 16. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `constructor X in class X cannot be applied to given types` khi `new X()` | Chỉ có constructor nhận tham số | Truyền đối số đúng hoặc **tự viết** constructor không tham số |
| Compiler báo lỗi tại khai báo subclass không có constructor | Default constructor muốn gọi `super()` nhưng superclass không có constructor không tham số phù hợp | Tạo constructor subclass với `super(args)` hoặc thiết kế constructor superclass phù hợp |
| `X() has private access` | Constructor tồn tại nhưng không truy cập được | Kiểm tra phạm vi và modifier, dùng factory nếu được thiết kế |
| `X is abstract; cannot be instantiated` | `X` là abstract class | Tạo concrete subclass; default constructor của abstract class vẫn có thể tồn tại |
| `new Outer.Inner()` không hợp lệ | `Inner` là non-static member class cần enclosing instance | Dùng `outer.new Inner()` theo quyền truy cập |
| `new EnumName()` không được | Enum có quy tắc tạo instance riêng | Dùng các enum constants |
| `new RecordName()` thiếu đối số | Record có canonical constructor theo components | Truyền đủ components hoặc khai báo constructor bổ sung hợp lệ |
| Field `String name` sau `new X()` vẫn `null` | Field không có initializer hay phép gán | Khởi tạo field hoặc yêu cầu thông tin qua constructor |
| Gọi `new X()` từ package khác không được | Class/constructor không có mức truy cập phù hợp | Kiểm tra `public` class, constructor, package/module |
| Viết `void X()` rồi tưởng có constructor tùy chỉnh | Đó là method, không phải constructor | Bỏ kiểu trả về khi muốn khai báo constructor |

### Lỗi tinh tế: “không khai báo constructor” không có nghĩa “không có constructor”

Lớp `class A {}` thường **có một constructor mặc định ngầm**. Vì vậy việc thấy không có dòng `A()` trong source không đủ kết luận `new A()` là lỗi. Phải kiểm tra ngữ cảnh thừa kế, abstract, visibility và loại class.

### Lỗi tinh tế khác: “có constructor không tham số” không chắc là default constructor

Trong `class B { B() {} }`, constructor không tham số tồn tại nhưng là **explicit no-arg constructor**. Khi báo cáo về quy tắc compiler, gọi nó là constructor do compiler tạo sẽ sai.

### Lỗi về lớp cha: hiểu nhầm `super()`

`super()` trong ngữ cảnh constructor là **lời gọi constructor superclass**, không phải lệnh “tạo thêm một object superclass độc lập”. Một instance subclass chứa phần trạng thái của superclass; chuỗi constructor khởi tạo các phần của **cùng object** theo quy tắc Java.

### Lỗi về field: mặc định không bằng hợp lệ

`String id;` nhận `null` lúc tạo object, nhưng nếu API yêu cầu `id` không null thì default constructor trống có thể tạo trạng thái không hợp lệ. Phải chọn constructor/initializer dựa vào **invariant**, không chỉ để compiler không báo lỗi.

## 17. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Lớp `class A { }` có constructor không tham số hay không? Ai khai báo?

**Đáp án:** Có **default constructor** không tham số do compiler ngầm khai báo (với các quy tắc class thông thường), không phải do người viết.

**Câu 2.** Với `class B { B(int n) { } }`, `new B()` có hợp lệ không?

**Đáp án:** Không. Lớp đã khai báo `B(int)` nên compiler không cấp `B()` ngầm; cần `new B(5)` hoặc tự khai báo `B()`.

**Câu 3.** `class C { C() { } }` có default constructor do compiler tạo không?

**Đáp án:** Không. `C()` là **explicit no-arg constructor**; sự tồn tại của nó chặn default constructor.

**Câu 4.** `class D { void D() { } }` có được compiler sinh default constructor không?

**Đáp án:** Có. `void D()` là method có kiểu trả về `void`, không phải constructor declaration.

**Câu 5.** `abstract class E { }` có default constructor không? Có thể `new E()` không?

**Đáp án:** Có default constructor theo quy tắc class thông thường; **không** tạo instance trực tiếp vì E là abstract class. Concrete subclass có thể gọi superclass constructor phù hợp.

**Câu 6.** `class Base { Base(int x) {} } class Sub extends Base {}` có biên dịch không?

**Đáp án:** Không. Default constructor của `Sub` cần `super()` nhưng `Base` không có constructor không tham số.

**Câu 7.** Nếu sửa `Sub` thành `class Sub extends Base { Sub() { super(1); } }` thì sao?

**Đáp án:** Hợp lệ nếu `Base(int)` truy cập được. `Sub()` là constructor do người viết, **không phải default constructor ngầm**.

**Câu 8.** Top-level `public class PublicThing {}` (trong `PublicThing.java`) có constructor mặc định mức truy cập gì?

**Đáp án:** `public` theo quy tắc default constructor. Nếu tự khai báo `PublicThing() {}` mà không ghi `public`, constructor do người viết là package-private.

**Câu 9.** Lớp có `int count = 10;` và không constructor declaration: `new X().count` có còn `0` không?

**Đáp án:** Không. Field ban đầu được cấp giá trị `0`, nhưng instance field initializer gán `10` trước khi constructor hoàn thành.

**Câu 10.** Một class có `static { ... }` và `{ ... }` nhưng không khai báo constructor. Compiler có tạo default constructor không?

**Đáp án:** Có; static/instance initializer blocks **không phải constructor declarations**.

**Câu 11.** Vì sao `new House.Room()` không hợp lệ nếu `Room` là non-static inner class dù không có constructor tự viết?

**Đáp án:** Cần enclosing instance của `House`; cú pháp từ bên ngoài thường là `house.new Room()`. Việc có default constructor không bỏ qua yêu cầu enclosing instance.

**Câu 12.** Với `record Pair(int left, int right) {}`, `new Pair()` có tự hợp lệ vì record không tự viết constructor không?

**Đáp án:** Không. Record nhận canonical constructor theo components; lời gọi thông thường là `new Pair(1, 2)` nếu không có constructor bổ sung được khai báo hợp lệ.

## 18. Checklist khi gặp lỗi `new ClassName()`

Để xác định vì sao một lời gọi constructor không tham số bị lỗi, hãy kiểm tra theo thứ tự:

1. **Đây là class thông thường, abstract class, enum, record hay inner class?** Loại khai báo ảnh hưởng cú pháp và khả năng tạo instance.
2. **Trong class có bất kỳ constructor declaration nào không?** Nếu không, class thông thường có default constructor; nếu có, **không** được compiler thêm default constructor.
3. **Có explicit no-arg constructor không?** Nếu có, kiểm tra mức truy cập và logic của chính constructor ấy.
4. **Nếu chỉ có default constructor, constructor superclass không tham số có truy cập được không?** Kiểm tra có constructor cha với danh sách tham số thích hợp, có bị private/khác package hạn chế không.
5. **Bản thân class có thể khởi tạo trực tiếp không?** Abstract và enum tạo ra các ràng buộc khác.
6. **Mã gọi có nhìn thấy class và constructor không?** Quan tâm `public`, package-private, nested access và module visibility.
7. **Đối với inner class, đã có enclosing instance chưa?** Cần `outer.new Inner()` khi ở ngoài ngữ cảnh phù hợp.
8. **Constructor và initializers có để trạng thái hợp lệ không?** Hết lỗi compile không đồng nghĩa object thỏa ràng buộc nghiệp vụ.

---

**Ghi nhớ:** Với **class thông thường**, chỉ khi **không có bất kỳ constructor declaration nào** thì Java mới ngầm tạo **default constructor** không tham số. Một constructor `X()` do bạn viết cũng không nhận tham số nhưng **không phải constructor mặc định do compiler sinh**. Default constructor cần gọi được superclass constructor không tham số thích hợp, và không vượt qua quy tắc `abstract`, quyền truy cập hay yêu cầu enclosing instance. Hãy dùng constructor tường minh khi object cần dữ liệu bắt buộc hoặc quy trình khởi tạo có ý nghĩa nghiệp vụ.