# Khởi tạo lớp cha trước lớp con trong Java

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích chính xác ý nghĩa của **“lớp cha khởi tạo trước lớp con”** trong hai bối cảnh khác nhau: **class initialization** (thành viên `static`) và **object initialization** (instance fields, initializer blocks và constructors).
- Dự đoán thứ tự thực thi khi `new Child()`: việc khởi tạo class cần thiết, cấp giá trị mặc định cho fields của object, chuỗi gọi constructor `super(...)`, instance initializers và thân constructors.
- Hiểu `this(...)` và `super(...)` trong Java 17, constructor chaining nhiều tầng, yêu cầu constructor superclass khả dụng và các lỗi biên dịch thường gặp.
- Phân biệt static initialization **một lần cho runtime class** với instance initialization **mỗi object**.
- Giải thích tại sao constructor lớp cha có thể gọi một phương thức bị override ở lớp con **trước khi các field initializers của lớp con chạy**, và vì sao đây là một rủi ro thiết kế.
- Nhận ra rằng đọc một static field **khai báo ở superclass** qua tên subclass chưa chắc kích hoạt khởi tạo subclass.
- Hiểu vai trò của access modifiers, `final`, field hiding, interface initialization và lỗi xảy ra trong constructor/class initializer.
- Biên dịch/chạy các ví dụ độc lập tương thích JDK 17+, đọc stdout chính xác và tự phân tích một cây kế thừa.

## 1. Một câu nói, hai cơ chế phải phân biệt

Với:

~~~java
class Parent {
}

class Child extends Parent {
}
~~~

`Child` là subclass của `Parent`. Nói “Parent khởi tạo trước Child” có thể đề cập hai tiến trình **khác nhau**:

1. **Khởi tạo lớp (class initialization):** JVM thực hiện những static field initializer expressions và `static { ... }` của `Parent` trước khi thực hiện các phần tương ứng của `Child` khi khởi tạo `Child`.
2. **Khởi tạo một đối tượng Child (object initialization):** khi một `Child` object được tạo, chuỗi constructor của superclass đi trước phần khởi tạo instance fields và constructor body của subclass, theo quy tắc Java.

Hai tiến trình liên quan nhưng **không phải một**. Một class có thể được khởi tạo `static` từ trước mà chưa tạo object nào; sau đó, mỗi lần `new Child()` vẫn thực hiện trình tự **instance initialization** cho object mới.

### 1.1. Một dòng thời gian tổng quát

~~~text
Khi new Child() lần đầu trong một JVM đơn giản:

CLASS INITIALIZATION (nếu các class chưa initialized):
  Parent: static fields / static blocks
  Child:  static fields / static blocks

OBJECT CREATION:
  Cấp phát object Child; fields mang giá trị mặc định ban đầu
  Constructor chain đi lên Parent / Object
  Khởi tạo instance fields, instance blocks của lớp cha
  Chạy constructor body của lớp cha
  Khởi tạo instance fields, instance blocks của lớp con
  Chạy constructor body của lớp con
  Trả tham chiếu Child object đã tạo thành công
~~~

Sơ đồ chỉ mô tả cây kế thừa đơn giản. Trong thực tế còn có grandparent classes, constructor delegation `this(...)`, superinterfaces có default methods, initialization đã hoàn thành trước đó và ngoại lệ làm dừng quy trình.

**Điểm quan trọng:** không có quy tắc “mọi khối static chỉ chạy khi tạo object”. Chúng chạy khi class được **initialized**, mà `new` chỉ là một trong các tình huống kích hoạt.

## 2. Phân biệt class loading, linking, initialization và tạo object

Để nói đúng về thứ tự, cần nhận diện bốn khái niệm:

| Giai đoạn | Việc chính | Quan hệ với `new Child()` |
| --- | --- | --- |
| **Loading** | Tìm/định nghĩa dạng nhị phân của class ở runtime | Có thể đã xảy ra trước đó |
| **Linking** | Verification, preparation và resolution theo quy tắc JVM | Static fields được chuẩn bị; các chi tiết có thể diễn ra ở thời điểm khác nhau |
| **Class initialization** | Thực thi các static initializers đúng quy tắc và phụ thuộc superclass | Parent được initialized trước Child khi Child cần initialized |
| **Object initialization** | Tạo và khởi tạo state của **một instance** | Constructor chain và instance initializers được thực thi cho object |

`static` fields thuộc runtime class; instance fields thuộc mỗi object. Dù cả hai có thể nhận **giá trị mặc định** trước khi các initializer expressions chạy, không được hiểu rằng “được cấp mặc định” nghĩa là constructor đã hoàn thành hoặc invariant nghiệp vụ đã đúng.

### 2.1. Giá trị mặc định của fields không phải initializer hoàn chỉnh

Ví dụ:

~~~java
class Child extends Parent {
    int age = 18;
    String name = "An";
}
~~~

Trước khi instance field initializers `age = 18` và `name = "An"` được thực hiện cho object, vùng fields có giá trị mặc định tương ứng `0` và `null`. Những giá trị mặc định này đặc biệt quan trọng nếu một method bị override được gọi quá sớm từ constructor của superclass.

Với local variables trong method, Java có quy tắc *definite assignment* riêng: không thể suy rằng local variable được đọc với mặc định 0/null giống instance fields.

## 3. Ví dụ class initialization: static của cha trước static của con

Lưu **`ParentChildStaticDemo.java`**:

~~~java
public class ParentChildStaticDemo {
    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }

    static class Parent {
        static int parentNumber = trace("Parent.static field", 10);

        static {
            System.out.println("Parent.static block");
        }
    }

    static class Child extends Parent {
        static int childNumber = trace("Child.static field", 20);

        static {
            System.out.println("Child.static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        System.out.println("childNumber=" + Child.childNumber);
        System.out.println("childNumber again=" + Child.childNumber);
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac ParentChildStaticDemo.java
java ParentChildStaticDemo
~~~

**Stdout chính xác:**

~~~text
main starts
Parent.static field
Parent.static block
Child.static field
Child.static block
childNumber=20
childNumber again=20
~~~

Diễn biến:

1. JVM initialize outer class `ParentChildStaticDemo` để chạy `main`; outer class không có static initializer in dòng nào.
2. `main` in `main starts`.
3. Lần đầu đọc `Child.childNumber`, field do `Child` khai báo và là non-constant static field, nên `Child` cần initialization.
4. Trước khi thực thi static initializers của `Child`, superclass `Parent` được initialized theo quy tắc JLS.
5. Trong mỗi class, static field initializers và static blocks chạy **theo thứ tự xuất hiện trong class body**.
6. Đọc `Child.childNumber` lần thứ hai không chạy lại initializers; giá trị vẫn 20.

**Không nhầm:** Java không chạy tất cả static fields của toàn bộ hierarchy trước mọi static blocks. Thứ tự là **superclass trước subclass**, và **bên trong mỗi class** là thứ tự khai báo của field initializer/block.

### 3.1. Vì sao `trace` gọi được trước khi có `main`?

`trace` là static method đã được khai báo trong outer class. Khi một field initializer gọi `trace`, method ấy thực thi và in dòng tương ứng. Thứ tự source của method declaration so với static field không phải lời hứa rằng method được “chạy trước”; nó chỉ cần được phân giải hợp lệ khi biểu thức được thực thi.

### 3.2. Lần gọi thứ hai không khởi tạo lại class

Theo quy tắc JVM, trạng thái initialized được quản lý cho **runtime class**. Trong trường hợp thông dụng một JVM và một defining class loader, cùng `Parent`/`Child` không chạy lại static blocks sau khi đã initialized.

Nếu bạn khởi động một tiến trình Java mới, các runtime classes trong JVM mới lại có vòng đời mới. Với class loaders khác nhau có thể tồn tại những runtime class riêng mang cùng binary name; đừng tóm tắt tuyệt đối “chỉ một lần cho toàn bộ mọi chương trình”.

## 4. Ví dụ thứ tự tạo object: cha trước con, mỗi instance

Lưu **`ParentChildInstanceDemo.java`**:

~~~java
public class ParentChildInstanceDemo {
    static int trace(String name, int value) {
        System.out.println(name);
        return value;
    }

    static class Parent {
        int parentValue = trace("Parent.instance field", 10);

        {
            System.out.println("Parent.instance block");
        }

        Parent() {
            System.out.println("Parent.constructor value=" + parentValue);
        }
    }

    static class Child extends Parent {
        int childValue = trace("Child.instance field", 20);

        {
            System.out.println("Child.instance block");
        }

        Child() {
            super();
            System.out.println("Child.constructor value=" + childValue);
        }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        new Child();
        System.out.println("after new");
    }
}
~~~

Chạy:

~~~bash
javac ParentChildInstanceDemo.java
java ParentChildInstanceDemo
~~~

**Output:**

~~~text
before new
Parent.instance field
Parent.instance block
Parent.constructor value=10
Child.instance field
Child.instance block
Child.constructor value=20
after new
~~~

Đọc thứ tự:

- `new Child()` bắt đầu tạo **một object Child**, trong đó có phần fields được khai báo trong `Parent` và `Child`.
- Constructor của `Child` có explicit `super()`, gọi constructor không tham số của `Parent`.
- Trước phần body của `Parent()`, các instance field initializers và instance initializer blocks thuộc `Parent` được thực thi theo thứ tự class body.
- Sau khi `Parent()` hoàn tất, các instance initializers của `Child` chạy rồi mới tới phần body của `Child()`.
- `main` in `after new` sau khi constructor `Child()` trả về bình thường.

Ở ví dụ này, không có static block in dòng nào. Điều đó **không** có nghĩa static initialization bị bỏ qua: chỉ đơn giản không có static initializer có side effect quan sát được.

### 4.1. Thứ tự bên trong mỗi class cũng là thứ tự khai báo

~~~java
class Parent {
    int a = log("field a");
    {
        log("instance block");
    }
    int b = log("field b");

    Parent() {
        log("constructor body");
    }
}
~~~

Đây là đoạn minh họa với method `log(String)` phù hợp. Thứ tự của phần instance initialization thuộc `Parent` là field a → instance block → field b → constructor body. Java **không** mặc định chạy tất cả field initializers trước mọi instance blocks.

Nếu subclass cũng có các field/block, những bước của subclass được thực hiện ở giai đoạn subclass tương ứng, sau khi chuỗi constructor superclass đã thực hiện theo quy tắc.

### 4.2. Constructor không được kế thừa

Dù `Child extends Parent`, constructors của `Parent` không trở thành constructors của `Child`. `new Child(...)` chỉ hợp lệ nếu `Child` có constructor tương thích được khai báo hoặc compiler cung cấp implicit default constructor theo điều kiện.

Một `Child` constructor **gọi** `Parent` constructor bằng `super(...)`; đó không phải là “kế thừa constructor”.

## 5. Ví dụ kết hợp: static một lần, constructor nhiều lần

Lưu **`StaticAndInstanceLifecycleDemo.java`**:

~~~java
public class StaticAndInstanceLifecycleDemo {
    static class Parent {
        static {
            System.out.println("Parent.static");
        }

        {
            System.out.println("Parent.instance");
        }

        Parent() {
            System.out.println("Parent.constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child.static");
        }

        {
            System.out.println("Child.instance");
        }

        Child() {
            System.out.println("Child.constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("first");
        new Child();
        System.out.println("second");
        new Child();
    }
}
~~~

Lệnh:

~~~bash
javac StaticAndInstanceLifecycleDemo.java
java StaticAndInstanceLifecycleDemo
~~~

Stdout:

~~~text
first
Parent.static
Child.static
Parent.instance
Parent.constructor
Child.instance
Child.constructor
second
Parent.instance
Parent.constructor
Child.instance
Child.constructor
~~~

Với object thứ nhất:

1. `Parent.static` rồi `Child.static`.
2. `Parent.instance`, `Parent.constructor`.
3. `Child.instance`, `Child.constructor`.

Với object thứ hai, hai class đã initialized, nên chỉ có bước **instance** và **constructor**. Tên `Parent.static` trong output thể hiện khối static chạy **một lần cho runtime Parent**, không phải “một lần cho object Parent nằm trong object Child”.

### 5.1. Một object Child có bao nhiêu phần instance state?

Tạo `new Child()` không tạo **hai objects tách biệt**, một Parent và một Child. Nó tạo **một object** có runtime type `Child`, và object đó có state/behavior được định nghĩa theo cấu trúc kế thừa thích hợp. Constructors superclass và subclass đều tham gia khởi tạo **cùng object** ấy.

Nếu constructor `Parent()` in `this.getClass().getSimpleName()` trong trường hợp này, runtime class của object có thể là `Child`, ngay cả khi code đang chạy bên trong `Parent()`. Điều này liên quan trực tiếp tới rủi ro dynamic dispatch sẽ học ở phần sau.

## 6. Đa tầng kế thừa: Object → Grandparent → Parent → Child

Khi chuỗi kế thừa có nhiều tầng, việc khởi tạo đi qua các superclass từ trên xuống theo thứ tự phù hợp.

Lưu **`ThreeLevelInitializationDemo.java`**:

~~~java
public class ThreeLevelInitializationDemo {
    static class Grandparent {
        static {
            System.out.println("Grandparent.static");
        }

        {
            System.out.println("Grandparent.instance");
        }

        Grandparent() {
            System.out.println("Grandparent.constructor");
        }
    }

    static class Parent extends Grandparent {
        static {
            System.out.println("Parent.static");
        }

        {
            System.out.println("Parent.instance");
        }

        Parent() {
            System.out.println("Parent.constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child.static");
        }

        {
            System.out.println("Child.instance");
        }

        Child() {
            System.out.println("Child.constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("create");
        new Child();
        System.out.println("complete");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThreeLevelInitializationDemo.java
java ThreeLevelInitializationDemo
~~~

Output:

~~~text
create
Grandparent.static
Parent.static
Child.static
Grandparent.instance
Grandparent.constructor
Parent.instance
Parent.constructor
Child.instance
Child.constructor
complete
~~~

Cấu trúc cây:

~~~text
java.lang.Object
       |
   Grandparent
       |
     Parent
       |
      Child
~~~

Các static initializers của các classes tự khai báo đi theo thứ tự superclass trước subclass trong tình huống này. Constructor chain luôn phải đi lên tới superclass thích hợp, cuối cùng tới `Object` (mặc dù `Object` không in gì trong ví dụ), rồi phần instance initialization/constructor body hoàn thành từ lớp trên xuống lớp dưới.

**Không có ba lần `new` cho Grandparent, Parent, Child.** Chỉ có một lần `new Child()`, với chuỗi constructors tham gia.

## 7. `super(...)`: chọn constructor lớp cha cần chạy

Một constructor subclass có thể khai báo explicit constructor invocation tới superclass:

~~~java
class Parent {
    private final String name;

    Parent(String name) {
        this.name = name;
    }
}

class Child extends Parent {
    Child() {
        super("default");
    }
}
~~~

Hai classes trên là **mã minh họa** hợp lệ trong file/package thích hợp. `super("default")` chọn constructor `Parent(String)`, bảo đảm superclass khởi tạo phần state riêng.

### 7.1. Nếu không viết `super()` thì sao?

Trong Java 17, khi constructor body không bắt đầu bằng explicit `this(...)` hoặc `super(...)`, Java xem như có implicit `super()` trước phần body.

~~~java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    Child() {
        System.out.println("Child()");
    }
}
~~~

Đây là mã minh họa; khi tạo Child, `Parent()` được gọi trước `Child()`.

**Nhưng** implicit `super()` chỉ hợp lệ nếu superclass có **constructor không tham số accessible và có thể gọi**. Compiler không tự chuyển sang `super("x")` hay `super(0)` để “chọn đại” một constructor khác.

### 7.2. Trường hợp không có superclass no-arg constructor

Ví dụ cố ý sai:

~~~java
class Parent {
    Parent(int id) {
    }
}

class Child extends Parent {
    // Child() { } // Lỗi vì compiler ngầm chèn super() nhưng
    //              // Parent không có constructor không tham số.
}
~~~

Ngay cả khi để `Child` không khai báo constructor nào, compiler tạo default constructor cho Child và vẫn cần gọi `super()`; vì vậy class `Child` này **không biên dịch** với `Parent` như trên. Chỉ comment constructor không đủ làm source code ví dụ trở thành hợp lệ: toàn bộ **cặp lớp này** được đưa ra để minh họa lỗi.

Sửa:

~~~java
class Parent {
    Parent(int id) {
        System.out.println("Parent id=" + id);
    }
}

class Child extends Parent {
    Child() {
        super(10);
        System.out.println("Child()");
    }
}
~~~

Bây giờ constructor `Child()` gọi rõ `Parent(int)`. Nếu chạy `new Child()`, output là:

~~~text
Parent id=10
Child()
~~~

Đây là **hai phiên bản thay thế** của các lớp Parent/Child, không đặt cả hai cặp cùng tên vào một package và build đồng thời.

### 7.3. Accessible constructor là yêu cầu riêng

Một subclass không mặc nhiên gọi được một `private Parent()`. Nếu parent constructor inaccessible tại điểm gọi, `super()` không hợp lệ. `protected` constructors, public constructors và package-private constructors tuân các quy tắc truy cập riêng.

Thay đổi `private` constructor thành `public` để làm compiler hết lỗi không phải lúc nào cũng đúng: nên xác định thiết kế cho phép ai tạo loại object nào và cung cấp constructor/factory thích hợp.

## 8. `this(...)`: nhiều constructors của subclass nhưng không chạy initializer nhiều lần

Trong cùng class, một constructor có thể **ủy quyền sang constructor khác** bằng `this(...)`.

Lưu **`ConstructorChainingDemo.java`**:

~~~java
public class ConstructorChainingDemo {
    static class Parent {
        Parent(String name) {
            System.out.println("Parent(" + name + ")");
        }
    }

    static class Child extends Parent {
        {
            System.out.println("Child.instance block");
        }

        Child() {
            this(7);
            System.out.println("Child()");
        }

        Child(int id) {
            super("root");
            System.out.println("Child(int) id=" + id);
        }
    }

    public static void main(String[] args) {
        new Child();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConstructorChainingDemo.java
java ConstructorChainingDemo
~~~

Output:

~~~text
Parent(root)
Child.instance block
Child(int) id=7
Child()
~~~

Truy vết:

1. `new Child()` gọi `Child()`.
2. `Child()` bắt đầu bằng `this(7)`, chuyển tới `Child(int)`.
3. `Child(int)` bắt đầu bằng `super("root")`, gọi `Parent(String)`.
4. Khi constructor Parent hoàn tất, **instance initializer block của Child chạy một lần**.
5. Thân `Child(int)` in `Child(int) id=7`.
6. Điều khiển quay lại phần còn lại của `Child()` và in `Child()`.

Điều quan trọng là **khối instance initialization của Child không chạy hai lần** chỉ vì có hai constructor bodies tham gia một chuỗi `this(...)`. Nó chạy cho object Child mới trong quy trình khởi tạo phù hợp.

### 8.1. Trong Java 17, constructor invocation phải là câu lệnh đầu tiên

Ví dụ cố ý sai:

~~~java
class Child extends Parent {
    Child() {
        // System.out.println("before super");
        super();
    }
}
~~~

Trong **Java 17**, không được đặt statement thông thường trước explicit `super(...)` hoặc `this(...)` trong constructor body. Dòng in đã được comment để nhấn mạnh giới hạn. Còn ví dụ cần có superclass Parent với constructor no-arg truy cập được để biên dịch.

Không dùng các cú pháp/nhượng bộ từ phiên bản Java mới hơn để suy luận hành vi của Java 17.

### 8.2. `this(...)` và `super(...)` không được cùng xuất hiện như hai constructor invocations

Mỗi constructor chỉ có **một** explicit constructor invocation ở đầu (hoặc implicit `super()` khi thích hợp), không thể viết cả `this(...)` rồi `super(...)` liên tiếp. Việc khởi tạo superclass được constructor đích của chuỗi `this(...)` thực hiện.

Một chuỗi `this(...)` không thể vòng quanh tự gọi lẫn nhau mãi; các quy tắc compiler ngăn recursive constructor invocation.

## 9. Lớp cha được khởi tạo trước, nhưng lớp con có thể vẫn đang ở giá trị mặc định

Có một ngoại lệ rất quan trọng đối với trực giác “cha trước con”: **instance method của superclass được gọi trong constructor vẫn dispatch động đến override của subclass**, ngay cả khi instance initializers của subclass chưa thực thi.

~~~java
class Parent {
    Parent() { display(); }
    void display() { System.out.println("Parent"); }
}
class Child extends Parent {
    private String label = "READY";
    @Override void display() { System.out.println(label); }
}
~~~

Đây là **snippet**: nếu tạo `new Child()` lần đầu và không có side effect khác, lời gọi `display()` từ constructor Parent có thể in `null`, vì `label` chưa nhận `"READY"`. Object đã cấp phát và các instance fields mang **giá trị mặc định**, còn việc gán initializer của Child chỉ chạy sau superclass construction. Đây không phải “Java không override trước khi dựng xong”: chính dynamic dispatch là nguyên nhân.

**Thiết kế an toàn:** đừng gọi overridable method phụ thuộc subclass state từ constructor; đặt validation của superclass trong private/final helper phù hợp hoặc chuyển hook đa hình sang giai đoạn sau khi tạo object thành công. Bài “Gọi phương thức ghi đè khi đối tượng chưa khởi tạo xong” là nơi phân tích chính: trace `null/0`, method gián tiếp, `toString()`, `this` escape và phương án factory/lifecycle.

### Field hiding không giống method overriding

Fields **không** dispatch động như overridden instance methods:

~~~java
class Parent {
    int value = 1;
}
class Child extends Parent {
    int value = 2;
}
~~~

Với biến `Child child`, `child.value` truy cập field Child, còn `((Parent) child).value` truy cập field Parent. Đó là **hai fields trong cùng object**, không phải virtual dispatch của một method. Trong thực tế nên tránh hiding fields khi nó làm semantics khó đọc.

## 10. Tạo object Child không tạo riêng một object Parent khác

Một câu hỏi thường gặp: `new Child()` có phải gọi `new Parent()` ngầm không?

**Không theo nghĩa tạo hai independent objects.** Việc gọi `super(...)` điều khiển khởi tạo phần superclass của **cùng một Child object**, không cấp phát một Parent object riêng rồi gắn nó vào Child.

Dữ liệu:

~~~java
class Parent {
    int baseId = 10;
}

class Child extends Parent {
    int childId = 20;
}
~~~

Một Child object có thể chứa cả `baseId` và `childId`. Constructor của Parent làm phần việc của superclass; constructor Child làm phần việc subclass. Cơ chế này **khác composition**, nơi Child có một field `Parent component = new Parent()` — khi ấy `new Parent()` thực sự tạo object riêng.

### 10.1. `super` không phải biến chứa đối tượng cha độc lập

`super.method()` là cách chọn implementation/method thuộc superclass theo quy tắc Java, không phải một field reference trỏ tới “object Parent ở trong object Child” tách biệt. Kể cả khi gọi `super.method()`, `this` vẫn là cùng object có runtime type Child.

Sự phân biệt này rất quan trọng khi lý giải state và constructor chain.

## 11. Static field kế thừa: `Child.PARENT_FIELD` không nhất thiết khởi tạo Child

Một điều dễ hiểu sai là “nhắc tới Child ở bất cứ biểu thức nào chắc chắn khởi tạo Child”.

Theo JLS, khi đọc một **non-constant static field** bằng tên có thể viết qua subclass, việc initialization liên quan **class thực sự khai báo field**.

Lưu **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int CODE = init();

        private static int init() {
            System.out.println("Parent initialized");
            return 10;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("before field");
        System.out.println("code=" + Child.CODE);
        System.out.println("before new");
        new Child();
    }
}
~~~

Chạy:

~~~bash
javac InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

**Output:**

~~~text
before field
Parent initialized
code=10
before new
Child initialized
Child constructor
~~~

Giải thích:

- `CODE` **được khai báo trong Parent**, không phải Child.
- Đọc `Child.CODE` buộc khởi tạo Parent khi chưa initialized, nhưng **không tự buộc khởi tạo Child**.
- `new Child()` sau đó là active use của Child, nên Child initialized và in `Child initialized`.
- Parent đã initialized ở bước đầu, nên không in lại `Parent initialized`.

**Đừng rút ra quy tắc rằng mỗi tên `Child.` đều bỏ qua Child initialization.** Nếu field đó được **khai báo trong Child**, và không phải compile-time constant variable, lần đọc có thể khởi tạo Child, kéo theo superclass nếu chưa initialized.

### 11.1. Compile-time constants là ngoại lệ khác

Nếu Parent khai báo:

~~~java
static final int CONSTANT = 42;
~~~

với một constant expression initializer, việc đọc `Child.CONSTANT` **không tự đòi** initialization của Parent hoặc Child, vì đây là một constant variable. Compiler có thể dùng trực tiếp giá trị 42 tại call site.

`static final int RUNTIME = compute();` lại **không** là compile-time constant; đọc nó có thể trigger initialization của class khai báo.

Để hiểu đầy đủ, cần kiểm tra **field declaring class** và **có phải constant variable không**, không chỉ static/final modifiers.

## 12. Tên kiểu, class literal và static methods: các trigger khác nhau

Một class `Child` được **tham chiếu dưới dạng kiểu** trong code không đồng nghĩa nó chắc chắn đã chạy static initializer.

Ví dụ:

~~~java
Class<?> type = Child.class;
~~~

Class literal tạo/lấy `Class` object tương ứng, nhưng tự nó không phải một thao tác nhất thiết initialize Child theo quy tắc thông dụng. Việc gọi `Class.forName("...")` với overload mặc định hoặc truy cập một non-constant static field phù hợp có thể kích hoạt initialization.

Cũng cần phân biệt:

- **Gọi static method khai báo trong Child**: có thể là active use làm Child initialized.
- **Gọi static method thực sự khai báo trong Parent nhưng viết `Child.parentMethod()`**: initializer liên quan declaring class Parent theo quy tắc; không mặc định Child initialized chỉ vì qualifier.
- **Gọi instance method thông qua một Child object đã được tạo**: trong ngữ cảnh thông thường Child đã cần initialized khi object được tạo; không suy ra method instance có một “class initialization riêng” mỗi lần gọi.

Khi phân tích output, hãy xác định **phép toán nào đầu tiên thật sự bắt class initialized**, thay vì chỉ nhìn thấy chữ `Child`.

## 13. Constructor chain khi superclass có `final` fields

Đối tượng cần được xây dựng ở trạng thái hợp lệ, và superclass có thể bảo vệ state qua `private final` fields.

Lưu **`ConstructorValidationDemo.java`**:

~~~java
public class ConstructorValidationDemo {
    static class Parent {
        private final String id;

        Parent(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
            System.out.println("Parent validated " + id);
        }

        final String id() {
            return id;
        }
    }

    static class Child extends Parent {
        private final int level;

        Child(String id, int level) {
            super(id);
            if (level <= 0) {
                throw new IllegalArgumentException("level must be positive");
            }
            this.level = level;
            System.out.println("Child validated level=" + level);
        }

        int level() {
            return level;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("A", 3);
        System.out.println(child.id() + ":" + child.level());

        try {
            new Child("", 3);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid parent id rejected");
        }

        try {
            new Child("B", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid child level rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac ConstructorValidationDemo.java
java ConstructorValidationDemo
~~~

Output:

~~~text
Parent validated A
Child validated level=3
A:3
invalid parent id rejected
Parent validated B
invalid child level rejected
~~~

**Diễn giải:**

- Trường hợp hợp lệ: superclass kiểm tra và gán `id`, rồi subclass kiểm tra và gán `level`. Hai fields `final` được gán theo constructor chain.
- Với `new Child("", 3)`, superclass constructor ném exception **trước** khi in hoặc trước khi body subclass chạy; caller bắt lỗi, không nhận Child object được tạo thành công.
- Với `new Child("B", -1)`, superclass constructor **đã** in `Parent validated B`, nhưng subclass constructor phát hiện level sai rồi ném exception. Caller không nhận Child object thành công.
- Nếu superclass constructor thực hiện I/O hoặc sửa shared state rồi subclass constructor thất bại, các side effects đó **không tự được rollback**. Đây là một lý do nên hạn chế side effects khó phục hồi trong constructors.

### 13.1. Bảo vệ invariants ở đúng cấp

Superclass nên bảo vệ invariants liên quan tới state mà nó sở hữu, không giả định subclass đã initialized đầy đủ. Subclass nên xác nhận state riêng trước khi object được công bố theo API.

Không nên mở `protected` mutable fields rồi để subclasses thay đổi trực tiếp mọi state mà không validation. Cân nhắc `private` fields và protected/public methods với contract rõ nếu subclass cần extension points.

## 14. Lỗi trong static initializer của lớp cha ảnh hưởng lớp con

Nếu Parent không initialized thành công, một lần active use Child phụ thuộc vào Parent có thể thất bại trước khi static initializer của Child hoặc constructor của Child có cơ hội chạy.

Lưu **`ParentInitializationFailureDemo.java`**:

~~~java
public class ParentInitializationFailureDemo {
    static class Parent {
        static int STATUS = prepare();

        private static int prepare() {
            System.out.println("Parent preparing");
            throw new IllegalStateException("parent configuration invalid");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        try {
            new Child();
        } catch (Error error) {
            System.out.println("first=" +
                    error.getClass().getSimpleName());
        }

        try {
            new Child();
        } catch (Error error) {
            System.out.println("second=" +
                    error.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac ParentInitializationFailureDemo.java
java ParentInitializationFailureDemo
~~~

**Output:**

~~~text
Parent preparing
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

- Lần đầu khởi tạo Child cần Parent initialized trước. Parent gọi `prepare()` rồi ném `IllegalStateException`; JVM thường báo `ExceptionInInitializerError` cho ngoại lệ không thuộc `Error`.
- `Child static` và `Child constructor` **không** được in vì Parent initialization thất bại.
- Khi thử active use lại runtime class liên quan sau khi bị đánh dấu erroneous, `NoClassDefFoundError` có thể xuất hiện, như chương trình minh họa.
- Các chi tiết thông báo lỗi và chuỗi nguyên nhân có thể khác phiên bản JDK; ví dụ chỉ in simple class name để output ổn định.

**Chỉ bắt `Error` trong ví dụ nhằm quan sát cơ chế**, không phải hướng dẫn ứng dụng thông thường bắt rồi bỏ qua mọi `Error`. Trong hệ thống thật hãy thiết kế startup failure/monitoring rõ ràng, xem cause và không kỳ vọng gọi `new` lần nữa sẽ tự chạy lại static initializer đã thất bại.

## 15. Constructor của superclass ném exception thì subclass có chạy không?

Nếu `super(...)` không hoàn thành bình thường, quy trình tạo Child dừng; instance initializers và constructor body của Child chưa được thực hiện.

Ví dụ:

~~~java
class Parent {
    Parent(int id) {
        if (id < 0) {
            throw new IllegalArgumentException("invalid id");
        }
    }
}

class Child extends Parent {
    int value = print("Child field");

    Child(int id) {
        super(id);
        System.out.println("Child body");
    }

    private static int print(String text) {
        System.out.println(text);
        return 10;
    }
}
~~~

Đây là **đoạn lớp minh họa**, khi gọi `new Child(-1)` superclass constructor ném trước khi các dòng `Child field` hay `Child body` được thực hiện. Nếu constructor Parent có side effects đã hoàn thành trước khi ném, chúng không tự rollback.

Điều này khác class initialization error: constructor failure **không mặc định khiến bản thân class bị đánh dấu initialization erroneous**. Nếu lớp đã initialized thành công và dữ liệu đầu vào ở lần tạo object sau hợp lệ, bạn thường có thể thử tạo object mới, tùy contract và side effects.

## 16. Ghi nhớ các giai đoạn trong object creation chính xác hơn

Khi `new Child()` với class hierarchy hợp lệ:

1. **Active use/initialization:** class Child phải initialized trước khi hoàn thành instance creation, theo đúng quy tắc superclass/interface khi cần.
2. **Allocate object:** object Child được cấp phát và các instance fields của hierarchy mang **giá trị mặc định ban đầu**.
3. **Evaluate constructor argument expressions** theo quy tắc Java (có thể có side effects và exceptions).
4. **Constructor invocation chain:** `Child(...)` gọi `this(...)` hoặc `super(...)`, rồi tiếp tục lên superclass như cần.
5. **Superclass initialization of the instance:** tại cấp superclass tương ứng, instance field initializers và instance initializer blocks chạy theo textual order, sau phần gọi superclass phía trên, rồi tới constructor body của cấp này.
6. **Subclass initialization of the instance:** sau khi superclass constructor hoàn tất, các instance field initializers/blocks của subclass chạy theo textual order và constructor body của subclass được thực hiện.
7. **Constructor returns normally:** `new` trả reference tới object. Nếu có exception, không có kết quả tạo object thành công cho biểu thức `new` đó.

Đây là mô hình học tập cho Java 17; JLS `12.5 và `8.8.7.1` mô tả trình tự chính xác hơn, bao gồm instance initializer exceptions, constructor delegation và evaluation.

### 16.1. Đừng diễn đạt thành “constructor cha chạy xong rồi mọi field con mới tồn tại”

Object Child và các fields được cấp vùng lưu theo quy tắc cấp phát **trước khi toàn bộ constructors hoàn thành**. Điều chạy muộn là **explicit instance field initializer expressions** của Child, không phải việc fields mới được “tạo” sau khi Parent constructor trả về.

Vì fields đã có default values, dynamic dispatch sớm có thể đọc các giá trị đó. Đây chính là gốc của `Child.describe label=null,level=0` ở ví dụ trước.

### 16.2. Không đồng nhất “class initialized” với “mọi instances initialized”

Một class `Child` được initialized ở cấp `static` không có nghĩa một object cụ thể của nó đã được tạo. Bạn có thể gọi static method/đọc nonconstant static field để initialize class nhưng chưa từng `new Child()`.

Ngược lại, sau class initialization lần đầu, hàng ngàn objects Child có thể được tạo và mỗi object vẫn chạy constructor chain của riêng nó.

## 17. Interface initialization không hoàn toàn giống superclass chain

Một class Java có thể `extends` một class và `implements` nhiều interfaces. Thứ tự khởi tạo class và interface có những chi tiết riêng:

- Khi initialized một class, JVM/JLS yêu cầu initialized superclass và các superinterfaces liên quan có khai báo default methods theo quy tắc.
- Khởi tạo một interface **không mặc nhiên kéo theo khởi tạo mọi superinterface** như chuỗi superclass constructor.
- Một interface không có constructor hay instance initializer blocks giống class; interface fields ngầm `public static final`, nhưng một số field có runtime initializer, không phải compile-time constant.

Vì vậy, không nên lấy quy tắc **“Parent class trước Child class”** rồi áp dụng nguyên xi cho mọi interface trong cây implements/extends.

### 17.1. Không có “super()” của interface

Một class không gọi `super()` tới một interface constructor vì interface **không có constructor cho object**. `super(...)` trong constructor liên quan tới immediate superclass class. Những cú pháp như `InterfaceName.super.defaultMethod()` khi hợp lệ là thao tác gọi default method cụ thể, không phải khởi tạo interface instance riêng.

Đối với ví dụ nhập môn về class-object, hãy tách rõ:
- **Class inheritance:** `extends` và constructor chain.
- **Interface contract:** `implements`, default methods, static interface fields và quy tắc initialization khác.

## 18. Vì sao thứ tự khởi tạo quan trọng trong thiết kế OOP?

Thứ tự superclass → subclass là cơ chế nền tảng cho các trách nhiệm:

- **Superclass validation:** đảm bảo phần state thuộc Parent hợp lệ trước khi Child hoàn tất.
- **Code reuse:** Parent khởi tạo các fields chung qua constructor được kế thừa về mặt hành vi, không kế thừa chính constructor.
- **Polymorphism:** object Child là subtype của Parent và có runtime dispatch; nhưng polymorphism quá sớm trong constructor có thể quan sát incomplete state.
- **Encapsulation:** mỗi cấp nên kiểm soát phần state mà nó sở hữu, hạn chế lộ fields mutable cho subclass.
- **Failure safety:** nếu constructor hoặc class initialization thất bại, mọi side effects cần được cân nhắc.
- **Testability:** một stdout trace có thể cho thấy constructor nào được gọi và thời điểm các initializer expressions chạy.

### 18.1. Thiết kế parent constructor an toàn

Một cách thường rõ ràng:

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    final String id() {
        return id;
    }
}
~~~

`Parent` kiểm tra dữ liệu đầu vào của chính nó và không gọi overridable method trong constructor. `final id()` cũng tránh cho subclass override getter nếu contract cần cố định. `Child` có thể gọi `super(id)` và thực hiện validation state riêng sau đó.

### 18.2. Nếu cần subclass hook, gọi sau khi tạo xong

Không nên đặt hook có thể override trong `Parent()` nếu hook cần state của Child. Hãy cân nhắc factory:

~~~java
static Child createChild(String id) {
    Child child = new Child(id);
    child.afterConstruction();
    return child;
}
~~~

Đây là đoạn **minh họa** trong class/factory phù hợp. `afterConstruction()` nếu được thiết kế như lifecycle method chạy sau khi constructor hoàn tất, nó có thể quan sát instance fields đã được khởi tạo. Nhưng cần xác định hợp đồng rõ ràng: object không nên bị công bố cho code ngoài trước khi bước khởi tạo bắt buộc kết thúc, và không nên để callers quên gọi lifecycle method.

Với các invariants quan trọng, ưu tiên constructor/factory tự tạo object **hoàn chỉnh** trước khi trả ra thay vì phụ thuộc vào callback public thủ công.

## 19. Một vài điểm về `final` và thứ tự khởi tạo

- `final` instance fields có thể được gán trong field initializer hoặc constructor theo quy tắc definite assignment của Java.
- Một superclass có `final` fields không bị subclass gán lại trực tiếp chỉ vì `extends`.
- Một method `final` không được subclass override, nên gọi nó từ constructor không gặp **đúng dạng** rủi ro dispatch tới method override; nhưng logic của method vẫn phải tránh state chưa sẵn sàng hoặc external side effects.
- Một class `final` không có subclass, làm giảm rủi ro override từ class con, nhưng vẫn phải bảo vệ invariants khi khởi tạo state.
- `static final` fields theo constant-expression rules có thể là compile-time constant; đọc chúng không bắt buộc initialize class. Đây là câu chuyện riêng với `final` instance fields.

Không đồng nhất `final`, immutability, thread safety và class initialization order.

## 20. Các lỗi phổ biến khi phân tích output

| Sai lầm | Điều đúng |
| --- | --- |
| “`new Child()` chạy constructor Child rồi Parent.” | Chaining gọi superclass trước khi body Child hoàn tất. |
| “Static block chạy mỗi lần tạo Child object.” | Static block thuộc class initialization, thông thường chạy một lần cho runtime class. |
| “Parent và Child static field initializers được gom thành một nhóm.” | Mỗi class initialized theo quy tắc; Parent trước Child, textual order bên trong mỗi class. |
| “Mọi instance fields của Child đã có giá trị initializer trước Parent constructor.” | Chưa; chúng có giá trị mặc định trước khi initializer Child chạy. |
| “Constructor Parent gọi `virtualMethod()` chắc chạy Parent implementation.” | Override có thể được dispatch tới Child dù Child chưa initialized xong. |
| “Constructor Parent làm xong là object Parent riêng được tạo.” | Cùng một Child object đang được khởi tạo qua hierarchy. |
| “Constructor của Parent được kế thừa trong Child.” | Constructors không được kế thừa; Child constructor có thể gọi super constructor. |
| “Nếu Parent không có no-arg constructor, Child() tự gọi constructor khác.” | Không; cần explicit `super(args)` hoặc cấu trúc constructor phù hợp. |
| “`this(...)` trong Child khiến Child field/block chạy hai lần.” | Một chuỗi constructor delegation của cùng object không lặp instance initialization như vậy. |
| “Trong Java 17 có thể in một dòng trước `super()`.” | Explicit constructor invocation phải là câu lệnh đầu tiên theo Java 17. |
| “Đọc `Child.CODE` luôn initialized Child.” | Nếu CODE được khai báo ở Parent, có thể chỉ initialized Parent. |
| “Đọc static final constant luôn chạy static block.” | Constant variable có thể được inline, không kích hoạt initialization. |
| “`Child.class` luôn initialized Child.” | Class literal không tự yêu cầu class initialization trong ngữ cảnh thông thường. |
| “Parent static initializer thất bại nhưng Child static initializer vẫn chạy.” | Parent failure có thể ngăn Child initialized hoàn chỉnh. |
| “Constructor ném exception thì mọi class trở thành erroneous.” | Constructor failure không đồng nghĩa class initialization failure. |
| “Interface constructor cũng chạy trước class constructor.” | Interface không có instance constructor. |
| “Field shadowing và method overriding là cùng cơ chế.” | Field lookup thường dựa static type; method instance có dynamic dispatch. |
| “Superclass constructor luôn an toàn khi gọi method có thể override.” | Method override của Child có thể đọc fields còn ở default values. |
| “Class initialization thread-safe nghĩa mọi static mutable state thread-safe.” | Đồng bộ lúc init khác với synchronization khi update về sau. |

## 21. Checklist dự đoán chương trình trước khi chạy

Với một ví dụ có `new Child()`:

1. **Tìm hierarchy**: `Child extends Parent`, Parent extends ai, có interface default methods liên quan không?
2. **Xác định class nào đã initialized từ trước**; có active use nào xảy ra trước `new`?
3. **Viết static initializers của mỗi class** theo textual order, bắt đầu từ superclass chưa initialized phù hợp.
4. **Xem constructor mà `new Child(arguments)` chọn** và các argument expressions có thể có side effects.
5. **Lần theo `this(...)` hoặc `super(...)`** ở đầu mỗi constructor của Java 17; implicit `super()` khi không có explicit invocation.
6. **Đến superclass xa nhất cần thiết**, sau đó xử lý instance initializers và constructor bodies khi control đi xuống hierarchy.
7. **Đánh dấu giá trị mặc định của subclass fields** nếu superclass code có thể truy cập chúng qua dynamic dispatch.
8. **Phân biệt method overriding với field hiding** khi dự đoán chỗ lấy giá trị.
9. **Nếu method/initializer ném exception**, dừng phần khởi tạo còn lại và theo đường catch/unwind phù hợp.
10. **Nếu `new` chạy lần thứ hai**, không in lại static initializers của classes đã initialized; chỉ chạy instance/constructor logic.
11. **Kiểm tra stdout thật** bằng Java 17 nhưng không bỏ qua phần lý giải nguyên nhân mỗi dòng.
12. **Xem nguy cơ thiết kế:** overridden callbacks trong constructor, side effects khi thất bại, mutable static state, thread safety và API constructor access.

## 22. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Class `Parent` và `Child extends Parent` đều có static block. Khi tạo Child lần đầu, block nào chạy trước?  
**Đáp án:** Khởi tạo Parent trước Child theo quy tắc class initialization (giả sử cả hai chưa initialized).

**Câu 2.** Vì sao tạo Child lần thứ hai thường không in static blocks lần nữa?  
**Đáp án:** Các runtime classes đã initialized; static initialization không lặp mỗi instance.

**Câu 3.** `Child() { super(); ... }` gọi constructor của lớp nào?  
**Đáp án:** Constructor không tham số của immediate superclass Parent, nếu accessible/hợp lệ.

**Câu 4.** Java 17 làm gì khi constructor `Child()` không có explicit `this(...)`/`super(...)`?  
**Đáp án:** Compiler áp dụng implicit `super()`. Nếu Parent không có constructor no-arg accessible, sẽ báo lỗi.

**Câu 5.** Parent chỉ có `Parent(int)`. Làm sao Child constructor không tham số có thể hợp lệ?  
**Đáp án:** Child() phải gọi constructor Parent phù hợp bằng explicit `super(value)`, ví dụ `super(10)`.

**Câu 6.** Nếu `Child()` gọi `this(10)` rồi `Child(int)` gọi `super()`, instance initializer của Child chạy mấy lần cho một object?  
**Đáp án:** Một lần trong chuỗi constructor delegation của object.

**Câu 7.** Vì sao constructor Parent có thể gọi `Child.override()`?  
**Đáp án:** Instance method overriding dùng dynamic dispatch theo runtime type Child, kể cả khi thực thi từ Parent constructor.

**Câu 8.** Khi Parent constructor gọi override của Child, Child field `int level=9` thường có giá trị bao nhiêu nếu chưa chạy field initializer?  
**Đáp án:** `0` — giá trị mặc định của instance field `int`. Giá trị 9 được gán ở giai đoạn Child instance initialization sau đó.

**Câu 9.** `String label="READY"` của Child có thể là `null` khi override được gọi từ Parent constructor không?  
**Đáp án:** Có. Trước khi initializer Child chạy, reference field có default `null`.

**Câu 10.** `new Child()` có tạo một Parent object riêng và một Child object riêng không?  
**Đáp án:** Không. Một Child object được khởi tạo qua constructor chain của hierarchy.

**Câu 11.** Parent và Child cùng khai báo `int value`. `((Parent)child).value` có luôn đọc field Child không?  
**Đáp án:** Không. Field access phụ thuộc static type/name lookup; cast Parent chọn field Parent (nếu accessible).

**Câu 12.** `Child.CODE` khi `CODE` là static field khai báo ở Parent có chắc chạy static block Child không?  
**Đáp án:** Không. Việc đọc field có thể chỉ initialized declaring class Parent.

**Câu 13.** Nếu `CODE` là compile-time constant variable, đọc nó có bắt buộc initialize Parent không?  
**Đáp án:** Không. Compiler có thể dùng giá trị constant mà không khởi tạo class khai báo.

**Câu 14.** Static initialization của Parent ném `IllegalStateException` trong lần Child active use đầu; thường thấy lỗi gì?  
**Đáp án:** `ExceptionInInitializerError`; các lần dùng tiếp có thể `NoClassDefFoundError` do trạng thái initialization thất bại.

**Câu 15.** Constructor Parent ném `IllegalArgumentException` khi `super(...)` chạy. Instance initializer Child có tiếp tục không?  
**Đáp án:** Không. Constructor chain không hoàn thành, nên những bước của Child chưa tới không chạy.

**Câu 16.** Constructor Child ném exception sau khi Parent constructor in log; dòng log từ Parent có tự bị hoàn tác không?  
**Đáp án:** Không. Side effects trước đó không tự rollback khi constructor Child thất bại.

**Câu 17.** Trong Java 17 có thể đặt `System.out.println("x")` trước `super()` trong constructor không?  
**Đáp án:** Không. Explicit constructor invocation phải là statement đầu tiên.

**Câu 18.** Nếu class Child có static fields, `Child.class` có nhất thiết thực thi static block Child không?  
**Đáp án:** Không; class literal tự nó không bắt buộc initialization.

**Câu 19.** Interface có `super()` instance constructor giống superclass class không?  
**Đáp án:** Không. Interfaces không có constructors; class constructor chain chỉ áp dụng cho các classes.

**Câu 20.** Một Parent constructor nên tránh điều gì nếu Child có thể override methods?  
**Đáp án:** Tránh gọi overridable methods cần subclass state chưa initialized; ưu tiên private/final logic an toàn hoặc gọi extension points sau khi tạo object hoàn chỉnh.

**Câu 21.** Khối `static` của Parent in trước Child, nhưng các instance blocks có được in nếu chỉ đọc `Child.staticValue` không?  
**Đáp án:** Không, nếu chưa tạo object. Class initialization và object initialization khác nhau.

**Câu 22.** Constructor và static initializer đều có thể ném exception. Hai kiểu thất bại này có cùng trạng thái class sau lỗi không?  
**Đáp án:** Không. Lỗi class initialization có thể để runtime class erroneous; constructor invocation thất bại không tự đồng nghĩa class initialization thất bại.

## 23. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): thời điểm khởi tạo class và superclass.
- Java Language Specification (Java SE 17), [`12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, declaring class và constants.
- Java Language Specification (Java SE 17), [`12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): quy trình initialization và lỗi.
- Java Language Specification (Java SE 17), [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): trình tự tạo object và chạy instance initializers.
- Java Language Specification (Java SE 17), [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): khai báo constructor.
- Java Language Specification (Java SE 17), [`8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)`, `super(...)` và quy tắc Java 17.
- Java Language Specification (Java SE 17), [`8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): khối instance.
- Java Language Specification (Java SE 17), [`8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): khối static.
- Java Language Specification (Java SE 17), [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): hoạt động của lời gọi method, hữu ích khi xét dynamic dispatch.

## Kết luận

“**Lớp cha khởi tạo trước lớp con**” đúng trong hai ngữ cảnh cần được nói rõ: **static initialization** của superclass trước subclass và **constructor/instance initialization** của object đi qua phần state của superclass trước phần của subclass. Trong mỗi class, instance field initializers và initializer blocks có thứ tự theo source; constructor body của lớp đó thực hiện ở bước tương ứng. `this(...)` và `super(...)` xác định chuỗi constructor, không tạo một object Parent độc lập.

Quan trọng nhất, **cha chạy trước con không có nghĩa mọi fields con đã nhận giá trị initializer khi cha đang chạy**. Do dynamic dispatch, constructor superclass gọi overridable method có thể vô tình truy cập fields con còn ở `0` hoặc `null`. Hãy thiết kế constructors tập trung vào state do chính cấp lớp đó sở hữu, tránh callbacks tới subclass trước khi object hoàn chỉnh, và phân biệt rõ class initialization **một lần** với object initialization **mỗi object**. Đây là nền tảng để hiểu inheritance trong Java một cách chính xác và tránh những bug khó phát hiện do thứ tự khởi tạo.
