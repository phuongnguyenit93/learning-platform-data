# Gọi phương thức khác trên cùng đối tượng trong Java với `this.method()`

Trong Java, một **instance method** có thể gọi một instance method khác trên **chính đối tượng đang nhận lời gọi**. Cú pháp tường minh là `this.method(arguments)`. Trong ngữ cảnh instance thông thường, viết `method(arguments)` cũng thường gọi trên receiver ngầm định là `this`. Đây là cách một class chia hành vi lớn thành những method nhỏ hơn nhưng vẫn thao tác trên trạng thái của **cùng một instance**.

Điều quan trọng là: **`this` là tham chiếu đến current object, không phải tên class**, và `this.method()` không mặc nhiên buộc Java gọi implementation được khai báo trong class chứa dòng code. Nếu method có thể được override, Java áp dụng **dynamic dispatch** theo runtime type của object.

Bài học Java 17+ này tập trung vào ý nghĩa của việc gọi method khác trên cùng object: receiver, instance fields, helper methods, gọi ngầm định, kế thừa, constructor, method chaining, class lồng nhau, lambda, đệ quy, concurrent access và các lỗi phổ biến.

## 1. Receiver: method đang chạy trên đối tượng nào?

Xét lớp:

~~~java
class Counter {
    private int count;

    void increment() {
        this.setCount(this.getCount() + 1);
    }

    int getCount() {
        return this.count;
    }

    private void setCount(int count) {
        this.count = count;
    }
}
~~~

Đây là đoạn khai báo, chưa có `main` để chạy độc lập. Khi gọi:

~~~java
Counter first = new Counter();
Counter second = new Counter();

first.increment();
first.increment();
second.increment();
~~~

Các dòng là fragment trong method. Khi `first.increment()` đang chạy, `this` bên trong `increment()` trỏ tới object của `first`. Cả `this.getCount()` và `this.setCount(...)` cùng thao tác với object đó. Khi `second.increment()` chạy, `this` lại trỏ tới object của `second`.

Kết quả `first.getCount()` là `2`, `second.getCount()` là `1`. Hai object sử dụng cùng mã nguồn class nhưng giữ **instance state riêng**.

~~~text
first ------> Counter object A { count = 2 }
                this trong first.increment()

second -----> Counter object B { count = 1 }
                this trong second.increment()
~~~

Sơ đồ là mô hình tham chiếu, không khẳng định địa chỉ bộ nhớ vật lý. **Không có lời gọi `new Counter()` nào bên trong `increment()`**: gọi method khác qua `this` chỉ tiếp tục làm việc trên object hiện tại.

## 2. Cấu trúc lời gọi `this.method(...)`

Biểu thức:

~~~java
this.validateAmount(amount);
~~~

gồm:

- `this`: receiver, tức object hiện tại.
- `.`: chọn thành viên của receiver.
- `validateAmount`: tên method cần gọi.
- `(amount)`: các argument được truyền tới method tương ứng.

Java phân giải method theo các quy tắc tên, phạm vi truy cập, kiểu đối số, overload và kế thừa. Khi chọn implementation của instance method có thể override, Java còn sử dụng runtime dispatch.

Có thể gọi method khác dù nó là `private` trong cùng class:

~~~java
class TicketOffice {
    private int sold;

    void sell(int quantity) {
        this.validateQuantity(quantity);
        this.recordSale(quantity);
    }

    private void validateQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số vé phải dương");
        }
    }

    private void recordSale(int quantity) {
        sold = Math.addExact(sold, quantity);
    }
}
~~~

Đoạn khai báo này không có `main`. Method công khai `sell` làm nhiệm vụ điều phối, hai method private thực hiện validation và cập nhật. Tất cả đang xử lý cùng object `TicketOffice` nhận lời gọi `sell`.

**Lợi ích:** caller chỉ cần biết `sell`; không cần và không được truy cập trực tiếp hai helper private. Class giữ quyền kiểm soát state, giảm lặp logic và thể hiện thứ tự validate trước khi cập nhật.

## 3. `this.method()` và `method()` có luôn giống nhau không?

Trong một instance method bình thường, khi không có vấn đề về phân giải tên, hai cách thường tương đương:

~~~java
class Greeter {
    private String name = "Lan";

    String getName() {
        return name;
    }

    String greetingA() {
        return "Chào " + this.getName();
    }

    String greetingB() {
        return "Chào " + getName();
    }
}
~~~

Trên cùng `Greeter` object, `greetingA()` và `greetingB()` đều gọi `getName()` với receiver là current object, trả `"Chào Lan"`.

Tuy nhiên, không được coi mọi lời gọi bỏ `this.` ở mọi chỗ là tương đương:

- Trong **static method**, không có current instance, nên không thể gọi instance method không có receiver.
- Trong **inner class** hoặc anonymous class, `this` có thể trỏ tới inner/anonymous object, không phải outer object.
- Khi có overload, method được chọn vẫn phụ thuộc số lượng/kiểu argument; thêm `this.` không tự đổi chữ ký method.
- Nếu tên trùng với field/local, `name` không có ngoặc là đọc biến hoặc field; `name()` có ngoặc mới là method call.
- Một lời gọi có receiver khác như `other.getName()` có thể chạy trên object hoàn toàn khác.

Ví dụ phân biệt truy cập field và gọi method:

~~~java
class Student {
    private String name;

    Student(String name) {
        this.name = name; // field = constructor parameter
    }

    String name() {
        return this.name; // field
    }

    String display() {
        return this.name().toUpperCase(); // method call, rồi String method
    }
}
~~~

`this.name` và `this.name()` **không giống nhau**. Dấu ngoặc phân biệt field access với method call. Trong constructor, `this.name = name` xử lý parameter đang shadow field; trong `display`, `this.name()` thực thi method khác của cùng `Student`.

## 4. Chia hành vi: method cấp cao điều phối, method nhỏ xử lý

Một cách thiết kế hay gặp:

~~~java
class Invoice {
    private long subtotal;
    private long tax;

    void update(long subtotal, long tax) {
        this.requireNonNegative(subtotal);
        this.requireNonNegative(tax);

        long checkedTotal = Math.addExact(subtotal, tax);
        this.subtotal = subtotal;
        this.tax = checkedTotal - subtotal;
    }

    long total() {
        return Math.addExact(this.subtotal, this.tax);
    }

    private void requireNonNegative(long value) {
        if (value < 0) {
            throw new IllegalArgumentException("Số tiền âm");
        }
    }
}
~~~

Đây là đoạn minh họa. `update` sử dụng helper để kiểm tra input; cả hai lần gọi `this.requireNonNegative(...)` cùng có receiver là invoice hiện tại. Method `total()` đọc hai field của cùng object.

Trong trường hợp helper **hoàn toàn không phụ thuộc instance state** như `requireNonNegative`, việc đặt nó thành `private static` cũng có thể hợp lý và làm rõ rằng nó chỉ phụ thuộc tham số. `this` giúp nhấn mạnh receiver nhưng không phải lúc nào cũng là lựa chọn thiết kế tốt nhất cho helper thuần tính toán.

**Quan trọng:** tách method không tự đem lại tính atomicity. Nếu một method đã thay đổi state rồi method tiếp theo ném exception, Java không tự rollback. Hãy xác định invariant và tính trước các giá trị có thể gây lỗi trước khi commit trạng thái quan trọng.

## 5. Ví dụ Java 17+ hoàn chỉnh: các method gọi lẫn nhau trên cùng object

Tạo tệp **`SameObjectCallsDemo.java`**:

~~~java
public class SameObjectCallsDemo {
    static final class ScoreBoard {
        private final String player;
        private int score;
        private int updates;

        ScoreBoard(String player) {
            if (player == null || player.isBlank()) {
                throw new IllegalArgumentException("Tên không hợp lệ");
            }
            this.player = player;
        }

        ScoreBoard addPoints(int points) {
            this.requirePositive(points);
            int nextScore = Math.addExact(this.score, points);
            int nextUpdates = Math.incrementExact(this.updates);
            this.score = nextScore;
            this.updates = nextUpdates;
            return this;
        }

        ScoreBoard addBonus() {
            return this.addPoints(2);
        }

        String summary() {
            return this.player + ": score=" + this.score
                    + ", updates=" + this.updates;
        }

        boolean sameInstance(ScoreBoard other) {
            return this == other;
        }

        private void requirePositive(int points) {
            if (points <= 0) {
                throw new IllegalArgumentException(
                        "Điểm cộng phải dương");
            }
        }
    }

    public static void main(String[] args) {
        ScoreBoard lan = new ScoreBoard("Lan");
        ScoreBoard mai = new ScoreBoard("Mai");

        lan.addPoints(3).addBonus();
        mai.addPoints(4);

        System.out.println(lan.summary());
        System.out.println(mai.summary());
        System.out.println("Same Lan = " + lan.sameInstance(lan));
        System.out.println("Same Mai = " + lan.sameInstance(mai));

        try {
            lan.addPoints(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Lan after rejection = " + lan.summary());
    }
}
~~~

Lệnh chạy từ thư mục có file mã nguồn, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 SameObjectCallsDemo.java
java SameObjectCallsDemo
~~~

**Stdout chính xác:**

~~~text
Lan: score=5, updates=2
Mai: score=4, updates=1
Same Lan = true
Same Mai = false
Rejected = Điểm cộng phải dương
Lan after rejection = Lan: score=5, updates=2
~~~

**Phân tích từng bước:**

1. `lan.addPoints(3)` được gọi trên object `lan`, nên `this` trong `addPoints` chính là object đó.
2. `this.requirePositive(3)` kiểm tra tham số bằng helper `private`. Nếu input không hợp lệ, method dừng bằng exception trước khi sửa score.
3. `Math.addExact` và `Math.incrementExact` tính trước giá trị mới. Khi không có tràn số, hai field của **cùng ScoreBoard object** được cập nhật.
4. `return this;` trả **tham chiếu tới `lan`**, không tạo object mới. Do đó `.addBonus()` tiếp theo vẫn gọi trên `lan`.
5. Trong `addBonus()`, `this.addPoints(2)` lại gọi method cùng object. Lan nhận tổng điểm `3 + 2 = 5` và có hai lần cập nhật.
6. `mai.addPoints(4)` chạy với một receiver khác; không sửa object của Lan. Mai có điểm 4, một lần cập nhật.
7. `sameInstance` dùng `this == other` để kiểm tra identity của hai tham chiếu. `lan.sameInstance(lan)` là true, còn `lan.sameInstance(mai)` là false.
8. `addPoints(0)` ném `IllegalArgumentException` khi validation thất bại; không thay đổi score/updates nên dòng cuối vẫn `score=5, updates=2`.

Ví dụ minh họa đồng thời **gọi helper trên current instance**, **gọi lại một public method của current instance** và **trả `this` để chain**. Nó được thiết kế cho truy cập đơn luồng; nếu chia sẻ mutable `ScoreBoard` giữa nhiều thread, cần đồng bộ thích hợp.

## 6. Trả `this` để gọi liên tiếp (method chaining)

Một method có thể trả current object nếu return type tương thích:

~~~java
class MessageBuilder {
    private final StringBuilder buffer = new StringBuilder();

    MessageBuilder append(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text null");
        }
        this.buffer.append(text);
        return this;
    }

    String build() {
        return this.buffer.toString();
    }
}
~~~

Nếu có `new MessageBuilder().append("Java").append(" 17").build()`, kết quả là `"Java 17"`. Mỗi lời gọi `append` tiếp tục trên **cùng builder**.

Cần phân biệt:

- `return this;`: trả cùng object hiện tại.
- `return new MessageBuilder();`: tạo object khác nếu constructor thành công.
- `return this.append(text);`: gọi method trên cùng object rồi trả **kết quả mà method đó trả**. Trong ví dụ ScoreBoard, đó chính là `this`.
- Một chain của các method mutable có thể tạo **nhiều side effect**. Nếu bước sau ném exception, các bước trước không tự rollback.

Chaining thuận tiện cho builder và fluent API, nhưng chỉ nên dùng khi mỗi method có hợp đồng rõ: mutate current object hay tạo value object mới.

## 7. `this.method()` và dynamic dispatch khi subclass override

Một điểm rất quan trọng: method trong superclass có thể được gọi trên object thuộc subclass. Khi nó viết `this.otherMethod()`, receiver vẫn là **toàn bộ object runtime**, nên Java có thể chọn override của subclass.

Tạo tệp **`ThisDispatchDemo.java`**:

~~~java
public class ThisDispatchDemo {
    static class Parent {
        String message() {
            return "Parent";
        }

        String fromParent() {
            return "fromParent -> " + this.message();
        }
    }

    static final class Child extends Parent {
        @Override
        String message() {
            return "Child";
        }

        String fromChild() {
            return this.message() + "/" + super.message();
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println(parent.fromParent());
        System.out.println(polymorphic.fromParent());
        System.out.println(child.fromChild());
    }
}
~~~

Chạy:

~~~bash
javac ThisDispatchDemo.java
java ThisDispatchDemo
~~~

Stdout:

~~~text
fromParent -> Parent
fromParent -> Child
Child/Parent
~~~

Giải thích:

- `parent.fromParent()` gọi `this.message()` trên object thật thuộc `Parent`, nên chọn `Parent.message()`.
- `polymorphic` khai báo kiểu `Parent` nhưng tham chiếu object `Child`. `Parent.fromParent()` chạy trên receiver `Child`; lời gọi `this.message()` được **dynamic dispatch** tới `Child.message()`.
- `child.fromChild()` gọi `this.message()` (Child) rồi `super.message()` (Parent) để tạo `Child/Parent`.

| Cú pháp | Ý nghĩa |
| --- | --- |
| `this.message()` | Gọi trên current object; override có thể được chọn theo runtime type |
| `message()` | Trong ngữ cảnh instance thông thường, implicit receiver là current object |
| `super.message()` | Chọn implementation superclass thích hợp trong ngữ cảnh subclass |
| `other.message()` | Gọi trên object do biến `other` tham chiếu, có thể khác object hiện tại |
| `Parent.message()` | Không thay thế được receiver của instance method bằng tên class theo cách gọi static |

**Đừng nhầm overloading và overriding.** Compiler xét overload dựa trên tên, kiểu/số lượng argument và quy tắc applicability. Với instance method được override, runtime dispatch tiếp tục chọn implementation cho kiểu object thực tế. Viết `this.` không tắt bất kỳ cơ chế nào.

## 8. `this.method()` và `this(...)` không giống nhau

Hai cú pháp đều có keyword `this` nhưng một bên gọi method, bên kia là **constructor chaining**:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);   // gọi constructor hai tham số
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh không hợp lệ");
        }
        this.width = width;
        this.height = height;
    }

    int area() {
        return this.width * this.height;
    }

    String describe() {
        return "area=" + this.area();
    }
}
~~~

`this(1, 1)` không phải lời gọi method tên `this`; nó ủy quyền sang constructor cùng class. Trong **Java 17**, `this(...)` là explicit constructor invocation và bắt buộc ở **câu lệnh đầu tiên** trong thân constructor khi dùng. `this.area()` là instance method call bình thường, không có ràng buộc vị trí tương tự.

Constructor không trả giá trị theo cú pháp `return value`, nên không thể viết `this(...)` trong một method instance để “khởi tạo lại object”. Nếu cần khôi phục trạng thái, hãy tạo method có tên và validation thích hợp.

## 9. Không dùng `this` từ static method

Một static method không có **current instance receiver**, vì vậy không được gọi instance method qua `this`:

~~~java
class Configuration {
    private String mode = "normal";

    String mode() {
        return this.mode;       // hợp lệ: instance method
    }

    static void printMode() {
        // this.mode();         // sai: this trong static context
        // mode();              // sai: instance method thiếu receiver
    }
}
~~~

Trong static method, cần một object thật để gọi:

~~~java
class Greeter {
    private final String name;

    Greeter(String name) {
        this.name = name;
    }

    String greeting() {
        return "Chào " + name;
    }

    static String greet(Greeter person) {
        return person.greeting();  // gọi trên receiver cụ thể
    }
}
~~~

`greet(Greeter person)` là static, nhưng có thể gọi instance method `greeting()` qua parameter `person`. Nếu `person == null`, lời gọi sẽ ném `NullPointerException`. Thay `person` bằng `this` trong static context là lỗi biên dịch.

Static method khác được gọi qua tên class hoặc tên không định danh thích hợp, ví dụ `Math.abs(-3)`. Không cần và không có `this` để gọi nó.

## 10. Gọi method trên `this` khác gọi trên object khác

~~~java
class Note {
    private String text;

    Note(String text) {
        this.text = text;
    }

    void appendBang() {
        this.append("!");
    }

    void append(String suffix) {
        this.text += suffix;
    }

    String text() {
        return text;
    }
}
~~~

Nếu `Note first = new Note("A")` và `Note second = new Note("B")` thì `first.appendBang()` chỉ sửa object thứ nhất: `first.text()` là `"A!"`, `second.text()` vẫn là `"B"`.

Nhưng nếu `Note alias = first`, `alias.appendBang()` sửa **cùng Note object** như `first`. Tên biến khác nhau không đồng nghĩa với object khác nhau; đây là khái niệm **aliasing** của giá trị tham chiếu.

Trong method có thêm parameter object khác:

~~~java
class Box {
    private int amount;

    void add(int n) {
        amount = Math.addExact(amount, n);
    }

    void passTo(Box target, int n) {
        this.amount -= n;   // sửa current object
        target.add(n);      // sửa object mà target tham chiếu
    }
}
~~~

Đây là đoạn minh họa receiver, **không phải API chuyển tiền/giá trị đủ an toàn**: nó chưa validation số âm, đủ lượng, overflow, null, tự chuyển hay race. Thực tế phải xử lý tất cả ràng buộc đó. Trong ví dụ, `this.amount` và `target.add(n)` có thể tác động lên hai object khác nhau, hoặc cùng object nếu `target == this`.

## 11. Đệ quy: `this.method()` có thể gọi lại chính nó

Một method gọi chính nó thông qua `this` là một lời gọi đệ quy. Nếu không có điểm dừng, nó có thể làm đầy call stack:

~~~java
class BadCounter {
    private int count;

    int count() {
        return this.count(); // sai logic: gọi lại method vô hạn
    }
}
~~~

Đây là code biên dịch được, nhưng khi gọi `count()`, nó tiếp tục gọi `count()` mãi và thường gây `StackOverflowError`. Nếu ý định là đọc field, cần viết `return this.count;` **không có ngoặc**.

Đệ quy giữa hai method cũng có thể vô hạn:

~~~java
class Loop {
    int left() {
        return this.right();
    }

    int right() {
        return this.left();
    }
}
~~~

Đệ quy hợp lệ cần có base case:

~~~java
class Countdown {
    String describe(int n) {
        if (n <= 0) {
            return "done";
        }
        return this.describe(n - 1);
    }
}
~~~

`this.describe(n - 1)` vẫn gọi trên cùng object, nhưng tham số giảm dần cho tới khi dừng. Dù có điểm dừng, giá trị `n` quá lớn có thể vẫn vượt giới hạn stack; với phép đếm tuyến tính đơn giản, vòng lặp thường thích hợp hơn.

## 12. Cẩn thận khi gọi method overridable trong constructor

Constructor superclass có thể chạy khi phần khởi tạo của subclass chưa hoàn thành. Nếu constructor superclass gọi `this.method()` và method đó bị override, code subclass có thể quan sát field chưa được gán.

Tạo tệp **`ConstructorDispatchDemo.java`**:

~~~java
public class ConstructorDispatchDemo {
    static class Parent {
        Parent() {
            this.show();
        }

        void show() {
            System.out.println("Parent");
        }
    }

    static class Child extends Parent {
        private String label = "ready";

        @Override
        void show() {
            System.out.println("Child label = " + label);
        }
    }

    public static void main(String[] args) {
        new Child();
    }
}
~~~

Chạy:

~~~bash
javac ConstructorDispatchDemo.java
java ConstructorDispatchDemo
~~~

Stdout:

~~~text
Child label = null
~~~

Khi `Parent()` gọi `this.show()`, receiver runtime đã là object `Child`, nên override `Child.show()` được chọn. Nhưng field initializer `label = "ready"` của subclass chưa chạy; `label` vẫn là giá trị mặc định `null`.

**Cách xử lý:** không gọi method overridable từ constructor nếu logic cần trạng thái hoàn chỉnh. Ưu tiên helper `private`/`static`/`final` phù hợp, hoặc thực hiện thao tác cần toàn bộ object qua factory/bước khởi động sau khi tạo. Tương tự, không đăng ký callback hoặc truyền `this` ra ngoài constructor quá sớm (*this escape*).

## 13. Inner class: `this.method()` và `Outer.this.method()` có receiver khác nhau

Trong một **non-static inner class**, `this` là inner instance, còn `Outer.this` biểu diễn enclosing outer instance thích hợp.

Tạo tệp **`NestedMethodCallsDemo.java`**:

~~~java
public class NestedMethodCallsDemo {
    private final String label = "outer";

    private String describe() {
        return "Outer:" + label;
    }

    class Inner {
        private final String label = "inner";

        private String describe() {
            return "Inner:" + label;
        }

        String both() {
            return this.describe()
                    + " | "
                    + NestedMethodCallsDemo.this.describe();
        }
    }

    public static void main(String[] args) {
        NestedMethodCallsDemo outer = new NestedMethodCallsDemo();
        NestedMethodCallsDemo.Inner inner = outer.new Inner();
        System.out.println(inner.both());
    }
}
~~~

Chạy:

~~~bash
javac NestedMethodCallsDemo.java
java NestedMethodCallsDemo
~~~

Stdout:

~~~text
Inner:inner | Outer:outer
~~~

Trong `Inner.both()`, `this.describe()` gọi trên **inner object**, còn `NestedMethodCallsDemo.this.describe()` gọi trên **outer object**. Việc có cùng tên method `describe` không làm cho hai receiver này nhập một.

`Outer.this` chỉ có ý nghĩa khi có enclosing instance phù hợp; **static nested class** không tự có enclosing outer instance. Bên trong static nested object, `this` vẫn hợp lệ ở instance method của **chính static nested class**, không phải của outer class.

## 14. `this` trong lambda, anonymous class và bound method reference

Một lambda được khai báo trong instance method giữ cách hiểu `this` theo **lexical enclosing context**. Anonymous class thì có object riêng; `this` bên trong method của anonymous class trỏ tới object anonymous đó.

~~~java
class JobOwner {
    String label() {
        return "outer";
    }

    Runnable lambdaJob() {
        return () -> System.out.println(this.label());
    }

    Runnable anonymousJob() {
        return new Runnable() {
            private String label() {
                return "anonymous";
            }

            @Override
            public void run() {
                System.out.println(this.label());
                System.out.println(JobOwner.this.label());
            }
        };
    }
}
~~~

**Lưu ý về tính hợp lệ:** Trong anonymous class, method `label()` ở ví dụ là `private` nên không override method có phạm vi package-private của `JobOwner` vì đó không phải superclass của anonymous `Runnable`; nó là method riêng của anonymous object. Nếu gọi `new JobOwner().lambdaJob().run()`, stdout là `outer`. Nếu gọi `new JobOwner().anonymousJob().run()`, lần lượt in `anonymous` và `outer`.

### 14.1. Bound method reference `this::method`

Ngoài gọi ngay bằng `this.method()`, ta có thể viết `this::method` để tạo một **method reference** gắn với current receiver cho một functional interface:

~~~java
class Alarm {
    private int rings;

    void ring() {
        this.rings++;
    }

    Runnable callback() {
        return this::ring;
    }

    int ringCount() {
        return rings;
    }
}
~~~

Nếu:

~~~java
Alarm alarm = new Alarm();
Runnable callback = alarm.callback();

callback.run();
callback.run();
System.out.println(alarm.ringCount()); // 2
~~~

thì callback đã ràng buộc đúng object `alarm`, nên `rings` được tăng hai lần trên object đó.

**Khác biệt quan trọng:** `this.ring()` gọi ngay; `this::ring` tự nó **chưa thực thi `ring()`** mà tạo method reference để gọi về sau. Đăng ký callback mang tham chiếu tới `this` cũng phải chú ý vòng đời object, nhất là khi callback được lưu hoặc kích hoạt trước khi constructor hoàn tất.

## 15. Việc gọi helper không làm một thao tác trở nên thread-safe

~~~java
class ConcurrentCounter {
    private int value;

    void increment() {
        this.recordIncrement();
    }

    private void recordIncrement() {
        this.value++; // không phải atomic read-modify-write
    }
}
~~~

Hai thread đồng thời gọi `increment()` trên **cùng object** vẫn có thể bị **lost update**. `this` không phải lock, memory barrier hay atomic variable. Chia một method thành các helper cũng không khiến từng thay đổi trở thành atomic.

Ví dụ dùng monitor cho thao tác tăng:

~~~java
class SafeCounter {
    private int value;

    synchronized void increment() {
        this.recordIncrement();
    }

    synchronized int current() {
        return this.value;
    }

    private void recordIncrement() {
        this.value++;
    }
}
~~~

Khi mọi truy cập vào `value` đều tuân thủ cùng chiến lược đồng bộ, mỗi lời gọi `increment()` giữ monitor của receiver trong lúc gọi helper. Nếu có code khác bỏ qua monitor và sửa field, thiết kế vẫn có thể bị phá.

Nên xét cả việc **hai biến cùng trỏ một object**: `Counter a = new Counter(); Counter b = a;` không tạo hai state độc lập; gọi method đồng thời qua `a` và `b` vẫn truy cập chung object.

## 16. Trường hợp method có kết quả và side effect

Một method gọi method khác của chính object có thể:

- Chỉ **đọc dữ liệu**: `this.currentBalance()`, `this.isEmpty()`.
- **Thay đổi dữ liệu**: `this.deposit(amount)`, `this.clear()`.
- **Trả chính receiver**: `return this;` để chain.
- **Trả object khác**: `return this.createSnapshot();` khi helper tạo snapshot.
- **Ném exception**: `this.validate(amount)` có thể chặn các bước sau.
- **Gọi collaborator khác**: `this.notifyObservers()` có thể phát sinh I/O/callback.

`this.method()` tự nó **không nói** method có side effect hay không; phải hiểu hợp đồng của method được gọi. Chẳng hạn một getter trông vô hại nhưng thực hiện lazy initialization sẽ thay đổi state triển khai. Khi chia logic, cần giữ ý định từng method rõ ràng, nhất là với API command/query.

Nếu nhiều method được gọi tuần tự trong một nghiệp vụ, hãy xác định **thao tác nào có thể thất bại** và **trạng thái nào phải được duy trì nếu thất bại**. Java không tự hoàn tác các lệnh gọi đã chạy khi method sau ném exception.

## 17. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Điều đúng |
| --- | --- |
| “`this.method()` luôn gọi method được viết trong class này.” | Method overridable có thể dispatch sang implementation subclass |
| “`method()` không có receiver.” | Trong instance context thông thường, receiver ngầm định là `this` |
| “Viết `this.` sẽ tạo object mới.” | Không, `this` giữ tham chiếu đến object hiện tại |
| “Gọi cùng method trên hai biến khác nhau luôn sửa hai object.” | Hai biến có thể alias cùng object |
| “`this.field` và `this.field()` giống nhau.” | Một bên truy cập field, bên kia gọi method |
| “Có thể gọi `this.instanceMethod()` trong static method.” | Static context không có current instance |
| “`this(...)` là lời gọi method bình thường.” | Đó là constructor invocation |
| “`super.method()` tạo object superclass khác.” | Không, nó chọn hành vi superclass trên cùng object |
| “`this.method()` không gây recursion.” | Nó có thể gọi lại chính method, cần base case |
| “Gọi method trong constructor luôn an toàn.” | Nếu method overridable, có thể chạy trên state subclass chưa khởi tạo |
| “`this.method()` tự bảo vệ dữ liệu giữa thread.” | Không; phải có concurrency protocol riêng |
| “`this::method` sẽ gọi method ngay.” | Nó tạo method reference để được thực thi qua functional interface |

## 18. Bài tập tự kiểm tra

**Câu 1.** Trong `Counter.increment()`, hai lời gọi `this.getCount()` và `this.setCount(n)` có tạo hai object không?

**Đáp án:** Không. Cả hai đều thực thi trên current `Counter` object; chỉ có state của receiver được đọc/ghi.

**Câu 2.** Bỏ `this.` ở `this.getCount()` có làm đổi receiver không?

**Đáp án:** Trong ngữ cảnh instance phù hợp và khi `getCount()` phân giải tới cùng method, không. Lời gọi `getCount()` dùng implicit receiver là `this`.

**Câu 3.** Nếu `Parent.run()` gọi `this.show()` nhưng runtime receiver là `Child` và `Child` override `show()`, implementation nào chạy?

**Đáp án:** Instance dispatch chọn override của `Child` theo runtime type của receiver.

**Câu 4.** `this(10)` ở đầu constructor có tương đương `this.setValue(10)` không?

**Đáp án:** Không. `this(10)` gọi constructor khác trong cùng class; `this.setValue(10)` gọi instance method.

**Câu 5.** Vì sao method `int count() { return this.count(); }` có thể gây lỗi?

**Đáp án:** Nó gọi chính `count()` lặp lại, không hề đọc field `count`. Nếu không có base case sẽ dẫn đến đệ quy vô hạn.

**Câu 6.** `return this;` giúp gọi `a.add(1).add(2)` như thế nào?

**Đáp án:** `add(1)` trả chính receiver `a`, nên lời gọi `add(2)` tiếp tục trên object đó.

**Câu 7.** Trong non-static inner class, khác biệt giữa `this.describe()` và `Outer.this.describe()` là gì?

**Đáp án:** Lời gọi thứ nhất sử dụng inner receiver, lời gọi thứ hai sử dụng enclosing outer receiver phù hợp.

**Câu 8.** Hai thread cùng gọi `this.increment()` trên một object và method dùng `value++`. Viết `this.` có làm phép tăng atomic không?

**Đáp án:** Không. `this` chỉ định receiver, không tạo synchronization. Cần lock, atomic variable hoặc thiết kế khác tùy yêu cầu.

**Câu 9.** Vì sao constructor superclass gọi `this.show()` có thể quan sát null từ field subclass?

**Đáp án:** Dynamic dispatch có thể chọn implementation ở subclass trong khi initializer/constructor body của subclass chưa chạy.

**Câu 10.** `this::ring` có tự tăng biến `rings` ngay lúc biểu thức method reference được tạo không?

**Đáp án:** Không. Nó ràng buộc receiver và hành vi; biến `rings` tăng khi functional method tương ứng được thực thi.

## 19. Checklist thực hành

Khi thấy một method gọi method khác, hãy hỏi:

1. **Receiver là ai?** `this`, implicit current object, `other` hay `Outer.this`?
2. **Ngữ cảnh có instance không?** Static method không có `this`.
3. **Method được phân giải thế nào?** Kiểu/số lượng tham số quyết định overload; runtime type có thể quyết định override.
4. **Có thay đổi field của current object không?** Method khác được gọi có thể là query, command hoặc cả hai.
5. **Có đường gọi đệ quy không?** Base case có chắc chắn đạt được không?
6. **Có đang chạy trong constructor không?** Tránh gọi overridable method và làm lộ object chưa hoàn chỉnh.
7. **Nếu trả `this`, caller có biết nó nhận cùng instance không?**
8. **Nếu method đầu thay đổi state rồi method sau lỗi, invariant còn đúng không?**
9. **Nếu các method chạy đồng thời, dữ liệu có được bảo vệ đúng không?**
10. **Nếu có inner/lambda/anonymous class, `this` đang trỏ đến instance nào?**

**Kết luận:** `this.method()` là cách tường minh để **gọi một phương thức khác trên đối tượng hiện tại**. Cách viết này hỗ trợ chia nhỏ hành vi và sử dụng lại logic trong class, nhưng tính đúng đắn vẫn phụ thuộc receiver, dynamic dispatch, invariant, thứ tự khởi tạo và concurrency. Phân biệt chính xác `this.method()`, `other.method()`, `super.method()`, `Outer.this.method()` và `this(...)` sẽ giúp code Java rõ ràng, dễ kiểm thử và ít lỗi hơn.
