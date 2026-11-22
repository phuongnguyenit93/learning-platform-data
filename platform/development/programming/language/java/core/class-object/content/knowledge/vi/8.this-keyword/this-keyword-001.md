# `this` là tham chiếu tới đối tượng hiện tại trong Java

Trong Java, từ khóa **`this`** là một biểu thức tham chiếu đến **đối tượng hiện tại** (*current object*) trong ngữ cảnh **instance** phù hợp. Khi một phương thức instance đang chạy trên một đối tượng, `this` biểu diễn chính đối tượng đang nhận lời gọi đó; khi một constructor đang khởi tạo một đối tượng, `this` biểu diễn đối tượng đang được xây dựng, nhưng phải tuân thủ các hạn chế của giai đoạn khởi tạo.

Hiểu đúng `this` giúp đọc được code hướng đối tượng: **đang thao tác trên đối tượng nào**, khi nào `name` là biến cục bộ hay field của object, tại sao có thể trả về `this` để gọi method liên tiếp, và vì sao truyền `this` cho code bên ngoài có thể vô tình làm lộ state.

Bài học dành cho **Java 17+**, tập trung vào `this` với tư cách **tham chiếu đối tượng**. Cú pháp `this(...)` để gọi constructor khác cùng class cũng được phân biệt để tránh nhầm lẫn.

## 1. Đối tượng hiện tại là đối tượng nào?

Xét class:

~~~java
class Counter {
    private int value;

    void increment() {
        this.value++;
    }

    int current() {
        return this.value;
    }
}
~~~

Đây là **đoạn khai báo class**, chưa có `main` để chạy riêng.

Giả sử chương trình tạo hai đối tượng:

~~~java
Counter first = new Counter();
Counter second = new Counter();

first.increment();
first.increment();
second.increment();
~~~

Trong lời gọi `first.increment()`, `this` bên trong `increment()` trỏ tới **đối tượng được tham chiếu bởi `first`**. Trong `second.increment()`, cùng đoạn code nhưng `this` trỏ tới **đối tượng được tham chiếu bởi `second`**.

Kết quả nếu gọi `first.current()` và `second.current()` lần lượt là `2` và `1`. Tên biến `first`, `second` nằm ở nơi gọi, không nằm trong method `increment()`; method sử dụng `this` để biểu diễn instance đang được xử lý.

Sơ đồ khái niệm:

~~~text
Biến first  ─────► Counter object A { value = 2 }
                     this trong first.increment()

Biến second ─────► Counter object B { value = 1 }
                     this trong second.increment()
~~~

Sơ đồ chỉ thể hiện **quan hệ tham chiếu**, không phải địa chỉ bộ nhớ vật lý hay cách JVM bắt buộc bố trí object.

**Điểm cốt lõi:** `this` không có nghĩa là “đối tượng mới nhất được tạo”, “đối tượng được gọi ở dòng code gần nhất” hay “tên của class”. Nó là biểu thức tham chiếu đến **instance hiện tại theo ngữ cảnh thực thi**.

## 2. `this` có kiểu gì, chứa giá trị gì?

Bên trong một instance method của class `Person`, biểu thức `this` có kiểu thích hợp tương ứng với class đang khai báo code, đồng thời giá trị của nó là tham chiếu đến **chính instance nhận lời gọi**.

~~~java
class Person {
    boolean sameInstance(Person other) {
        return this == other;
    }
}
~~~

Method `sameInstance` kiểm tra xem `other` và `this` có trỏ đến **cùng một object** hay không. `==` trên hai tham chiếu object so sánh **identity**, không tự so sánh dữ liệu bên trong object.

Ví dụ:

~~~java
Person a = new Person();
Person alias = a;
Person b = new Person();

System.out.println(a.sameInstance(alias)); // true
System.out.println(a.sameInstance(b));     // false
~~~

Đây là **fragment trong một method**. `alias` và `a` cùng tham chiếu đến một object; `b` là object mới khác. Tên biến khác nhau không buộc tham chiếu trỏ tới object khác nhau; ngược lại, hai object khác nhau có thể có state bằng nhau mà không cùng identity.

### 2.1. `this` không phải tên biến do lập trình viên khai báo

Bạn không cần và không thể khai báo một parameter tên `this` rồi tự gán lại nó giống một biến thường. Java xác định ý nghĩa `this` theo ngữ cảnh lớp/instance; nó là keyword/biểu thức đặc biệt.

Sai lầm cần tránh:

~~~java
class Example {
    void change() {
        // this = new Example(); // Không hợp lệ: không thể gán lại 'this'
    }
}
~~~

Bạn có thể **thay đổi field của object** được `this` tham chiếu, hoặc trả/truyền tham chiếu đó, nhưng không thể gán cho `this` một object mới để “thay đối tượng hiện tại”.

### 2.2. `this` có thể trỏ tới một object thuộc subclass ở runtime

Giả sử method trong superclass được gọi trên instance subclass:

~~~java
class Animal {
    String typeName() {
        return this.getClass().getSimpleName();
    }
}

class Dog extends Animal {
}
~~~

Nếu gọi `new Dog().typeName()`, method body của `Animal` chạy nhưng `this` vẫn là **object Dog thực tế**. Vì vậy `this.getClass().getSimpleName()` trả `"Dog"` trong ví dụ này.

Không phải vì một method được **khai báo ở superclass** mà `this` biến thành “phần superclass” tách rời khỏi object. Java không tạo một object `Animal` riêng chỉ để chạy inherited method này.

## 3. Dùng `this.field` để phân biệt field với tham số cùng tên

Đây là tình huống gặp `this` thường xuyên nhất khi học class-object:

~~~java
class Student {
    private final String name;
    private int age;

    Student(String name, int age) {
        this.name = name;
        this.age = age;
    }

    void setAge(int age) {
        this.age = age;
    }
}
~~~

Phân tích câu lệnh `this.age = age;`:

- **`this.age` bên trái:** field `age` của đối tượng hiện tại.
- **`age` bên phải:** parameter `age` thuộc method/constructor đang chạy.
- Dấu `=` gán giá trị từ parameter vào field của instance.

Nếu viết nhầm:

~~~java
class BadStudent {
    private int age;

    BadStudent(int age) {
        age = age; // Chỉ tự gán cho parameter; không sửa field
    }
}
~~~

đoạn này **có thể biên dịch**, nhưng field `age` vẫn giữ giá trị mặc định `0`. Cả hai từ `age` đều được phân giải thành parameter gần nhất do **shadowing**. Dùng `this.age = age;` để định vị rõ field cần gán.

Nếu parameter không trùng tên field, `this` đôi khi không bắt buộc:

~~~java
class Price {
    private long amount;

    Price(long initialAmount) {
        amount = initialAmount; // Hợp lệ: không có tên cục bộ 'amount' che field
    }
}
~~~

Tuy nhiên, nhiều nhóm lập trình vẫn chọn `this.amount` nhất quán để nhấn mạnh thao tác trên trạng thái instance. Đây là **quy ước style**, không phải yêu cầu bắt buộc của compiler.

### 3.1. Thứ tự tìm tên chưa định danh

Trong một instance method, khi viết `name` mà không có `this.`, compiler xét các quy tắc phạm vi tên và có thể chọn parameter hoặc local variable thay vì field trùng tên. Ví dụ:

~~~java
class Profile {
    private String label = "field";

    void show() {
        String label = "local";

        System.out.println(label);       // local
        System.out.println(this.label);  // field
    }
}
~~~

`label` và `this.label` là **hai biểu thức khác nhau**. `this.label` chọn field của current object; `label` ở phạm vi gần nhất chọn local variable. Đặt tên local/parameter giống field không sai nhưng cần biết chính xác phép gán và phép đọc đang trỏ tới đâu.

### 3.2. `this.field` không vượt qua quy tắc truy cập kiểu Java

`this` chỉ xác định **receiver**; nó không làm biến mất kiểm soát kiểu, visibility, `final` hoặc các ràng buộc khác. Ví dụ, nếu field `id` đã được gán theo quy tắc `final`, một method không thể tự ý viết `this.id = ...`. Nếu method không có quyền truy cập một thành viên, thêm `this.` cũng không cấp quyền.

## 4. Gọi instance method qua `this`

Trong instance method, bạn có thể dùng `this.method(...)` để gọi method trên chính object hiện tại:

~~~java
class Temperature {
    private double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return this.celsius * 9.0 / 5.0 + 32.0;
    }

    String description() {
        return "F = " + this.fahrenheit();
    }
}
~~~

`this.fahrenheit()` gọi instance method trên cùng đối tượng `Temperature` đang xử lý `description()`. Trong trường hợp không có tên gây nhầm và lời gọi hợp lệ, viết `fahrenheit()` thường cho kết quả tương đương.

Một số điểm quan trọng:

- **`this.method()` vẫn là lời gọi instance method.** Nếu method đó có thể bị override, Java áp dụng dynamic dispatch như bình thường.
- `this.method()` **không đồng nghĩa** với “bắt buộc gọi implementation được khai báo trong chính class hiện tại”; với instance method overridable, implementation được chọn theo runtime type của object.
- Một method instance có thể gọi nhiều method khác của cùng object qua `this` để tách logic.
- Đừng gọi method overridable từ constructor nếu implementation của subclass có thể thấy field subclass chưa khởi tạo; đây là một vấn đề thiết kế vòng đời object.

## 5. Chương trình chạy được: `this`, field, chaining, identity và truyền tham chiếu

Tạo tệp **`ThisReferenceDemo.java`**:

~~~java
public class ThisReferenceDemo {
    static final class Person {
        private final String name;
        private int visits;

        Person(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên không hợp lệ");
            }
            this.name = name;
        }

        Person visit() {
            this.visits++;
            return this;
        }

        Person visitTwice() {
            this.visit();
            return this.visit();
        }

        String summary() {
            return this.name + ": " + this.visits;
        }

        boolean sameInstance(Person other) {
            return this == other;
        }

        void register(Registry registry) {
            registry.accept(this);
        }
    }

    static final class Registry {
        private Person last;

        void accept(Person person) {
            this.last = person;
        }

        Person last() {
            return this.last;
        }
    }

    public static void main(String[] args) {
        Person lan = new Person("Lan");
        Person mai = new Person("Mai");

        lan.visit().visit();
        lan.visitTwice();

        System.out.println("Lan = " + lan.summary());
        System.out.println("Mai = " + mai.summary());

        Person alias = lan;
        System.out.println("Same alias = " + lan.sameInstance(alias));
        System.out.println("Same Mai = " + lan.sameInstance(mai));

        Registry registry = new Registry();
        lan.register(registry);
        System.out.println("Registered Lan = "
                + (registry.last() == lan));

        alias.visit();
        System.out.println("After alias = " + lan.summary());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 ThisReferenceDemo.java
java ThisReferenceDemo
~~~

**Stdout chính xác:**

~~~text
Lan = Lan: 4
Mai = Mai: 0
Same alias = true
Same Mai = false
Registered Lan = true
After alias = Lan: 5
~~~

Giải thích:

1. Constructor `Person("Lan")` kiểm tra tên rồi gán `this.name = name`. `this` trong constructor trỏ tới đối tượng `Person` **đang được tạo**.
2. `lan.visit().visit()` gọi `visit()` hai lần trên **cùng một object**: method tăng `this.visits` rồi `return this;`. Vì kết quả trả về là chính `lan`, lời gọi thứ hai tiếp tục trên object đó.
3. `lan.visitTwice()` gọi `this.visit()` hai lần nên `lan` có bốn lượt. `mai` vẫn bằng 0 vì `mai` tham chiếu đến đối tượng khác.
4. `alias = lan` sao chép giá trị tham chiếu; `alias` và `lan` cùng trỏ tới một instance. `sameInstance(alias)` trả `true`, còn `sameInstance(mai)` trả `false`.
5. `register(registry)` truyền `this` cho `Registry.accept(...)`. Registry giữ tham chiếu đến chính object `lan`; vì vậy `registry.last() == lan` là `true`.
6. `alias.visit()` tăng lượt trên object dùng chung; `lan.summary()` sau đó thấy 5.

**Lưu ý:** Method `register` được gọi **sau khi constructor hoàn tất**, nên ví dụ không cố công bố object chưa khởi tạo xong. Truyền `this` cho bên ngoài có thể hợp lệ, nhưng cần xét quyền sở hữu, vòng đời và tính đồng thời của object.

## 6. Trả về `this` có tác dụng gì?

Một instance method có thể trả **chính receiver hiện tại** nếu kiểu trả về tương thích. `return this;` không cấp phát object mới, nên có thể tạo API fluent:

~~~java
class TextBuilder {
    private final StringBuilder value = new StringBuilder();

    TextBuilder append(String part) {
        value.append(part);
        return this;
    }

    String build() {
        return value.toString();
    }
}
~~~

`new TextBuilder().append("Java").append(" 17").build()` cho kết quả `"Java 17"`; hai lần gọi `append` thay đổi cùng một builder. Không mặc định mọi method phải trả `this`: query cần trả dữ liệu, thao tác không cần chaining có thể dùng `void`. Phân biệt với immutable `withX(...)` thường trả **object mới**, và tìm hiểu điều kiện kiểu trả về khi kế thừa ở bài **Truyền this làm đối số và trả về this**.

## 7. Truyền `this` làm đối số

Trong instance method, `this` có thể làm **biểu thức đối số** khi kiểu tham số nhận được tham chiếu tới object hiện tại:

~~~java
class Node {
    void visit(Inspector inspector) {
        inspector.inspect(this);
    }
}

class Inspector {
    void inspect(Node node) {
        System.out.println(node != null);
    }
}
~~~

Java sao chép **giá trị tham chiếu** vào biến tham số `node`; không clone cả `Node`, cũng không cho inspector gán lại biến receiver ở nơi gọi. Khi cộng tác viên giữ reference, nó có thể quan sát/sửa state nếu API cho phép.

**Cảnh báo vòng đời:** truyền hoặc đăng ký `this` từ constructor cho registry/listener/task có thể làm đối tượng bị sử dụng **trước khi khởi tạo xong**. Ví dụ callback có thể đọc field còn null dù constructor định gán ngay sau đó. Chỉ công bố khi state đã sẵn sàng; bài **Rủi ro để this thoát ra khi khởi tạo chưa hoàn tất** phân tích cả callback đồng bộ, thread và safe publication.

## 8. `this` và `this(...)` là hai cú pháp khác nhau

Đây là điểm rất dễ nhầm:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `this` | Biểu thức tham chiếu đến đối tượng hiện tại |
| `this.field` | Truy cập field của đối tượng hiện tại |
| `this.method()` | Gọi instance method trên đối tượng hiện tại |
| `return this;` | Trả tham chiếu đến chính đối tượng hiện tại |
| `otherMethod(this);` | Truyền tham chiếu current object làm đối số |
| `this(...)` trong constructor | **Explicit constructor invocation**: ủy quyền tới constructor khác của cùng class |

Ví dụ **`this(...)`**:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh phải dương");
        }
        this.width = width;
        this.height = height;
    }
}
~~~

Constructor không tham số gọi `this(1, 1)` để ủy quyền cho constructor hai tham số. Còn `this.width = width` là truy cập field qua current object; hai cú pháp dùng keyword giống nhau nhưng **không cùng vai trò**.

Với Java 17:

- `this(...)` chỉ dùng như lời gọi constructor tường minh trong constructor, theo quy tắc bắt buộc **là câu lệnh đầu tiên** của thân constructor.
- Một constructor chỉ có thể bắt đầu bằng `this(...)` **hoặc** `super(...)` như lời gọi tường minh tương ứng; không dùng cả hai.
- Các lời gọi `this(...)` không được tạo vòng lặp gọi constructor đệ quy.
- Các đối số của lời gọi constructor tường minh chịu hạn chế **không được sử dụng `this` hoặc instance members theo cách vi phạm quy tắc ngữ cảnh trước khi superclass/instance được khởi tạo**. Ví dụ không dùng `this.width` làm đối số để gọi `this(...)` trong constructor Java 17.

Đừng diễn giải `this(...)` như “gọi method tên `this`” hay “gọi lại cùng method”: đó là cú pháp chuyên dụng cho **constructor chaining**.

## 9. `this` và `super` khác nhau

`this` chỉ **đối tượng hiện tại**. `super` là cú pháp dùng khi cần truy cập cách triển khai/thành viên của superclass theo quy tắc ngôn ngữ; nó không phải một tham chiếu đến một object superclass độc lập.

~~~java
class Base {
    String label() {
        return "Base";
    }

    String describe() {
        return this.label();
    }
}

class Derived extends Base {
    @Override
    String label() {
        return "Derived";
    }

    String both() {
        return this.label() + "/" + super.label();
    }
}
~~~

Trong ví dụ:

- `new Derived().both()` trả `"Derived/Base"`.
- `this.label()` dùng dynamic dispatch nên gọi `Derived.label()`.
- `super.label()` yêu cầu implementation của superclass `Base` trong ngữ cảnh đó.
- `new Derived().describe()` trả `"Derived"`, dù phần thân `describe()` được khai báo ở `Base`. `this` bên trong inherited instance method vẫn trỏ tới object `Derived` đang nhận lời gọi.

Điều đó giải thích tại sao không nên nghĩ “`this` luôn trỏ đúng class có chứa source code của method”. **Giá trị tham chiếu là object runtime**, còn việc compiler kiểm tra tên/member phụ thuộc kiểu và ngữ cảnh khai báo.

Khi constructor của subclass gọi `super(...)`, đó là **constructor invocation** tới superclass để khởi tạo **cùng object** theo quy tắc kế thừa, không phải tạo một object superclass riêng rồi ghép vào subclass.

## 10. Khi nào không dùng được `this`?

`this` chỉ hợp lệ khi có **instance hiện tại trong ngữ cảnh từ vựng thích hợp**. Static method và static initializer không có receiver object:

~~~java
class Device {
    private int id;

    void show() {
        System.out.println(this.id); // Hợp lệ
    }

    static void report(Device device) {
        // System.out.println(this.id); // Sai: static context
        System.out.println(device.id); // Hợp lệ: receiver tường minh
    }
}
~~~

Một instance method có thể đọc static member bằng tên lớp, nhưng điều đó không biến static method thành nơi có `this`. Ngược lại, **instance method của một static nested class** có `this` của **nested object**, dù không có `Outer.this` ngầm định. Trong lambda, `this` kế thừa ngữ cảnh bao quanh; trong anonymous class, `this` biểu thị chính instance anonymous. Bài **Giới hạn sử dụng this trong ngữ cảnh static** kiểm tra sâu các ranh giới này; `this(...)` là cú pháp gọi constructor khác chứ **không phải** biểu thức receiver.

## 11. `Outer.this` trong inner class

Một **non-static inner class** có instance của riêng nó và liên kết với enclosing instance của lớp ngoài. Vì vậy, trong instance method của inner class, `this` là inner object; `Outer.this` là **outer object** tương ứng:

~~~java
class Outer {
    private String label = "outer";

    class Inner {
        private String label = "inner";

        String both() {
            return this.label + "/" + Outer.this.label;
        }
    }
}
~~~

Nếu `Outer outer = new Outer();` và `Outer.Inner inner = outer.new Inner();`, `inner.both()` trả `"inner/outer"`. `Outer.this` không tạo object mới và không có trong static nested class thiếu enclosing instance. Bài **Truy cập đối tượng bao ngoài bằng Outer.this** đi sâu vào nhiều tầng lồng nhau, shadowing, lambda/anonymous và vòng đời object.

## 12. `this` trong lambda và anonymous class: dễ bị nhầm

Hai dạng code có thể cùng thực thi qua interface `Runnable` nhưng có ngữ nghĩa `this` khác nhau:

~~~java
class JobOwner {
    String name = "owner";

    Runnable lambdaJob() {
        return () -> System.out.println(this.name);
    }

    Runnable anonymousJob() {
        return new Runnable() {
            String name = "anonymous";

            @Override
            public void run() {
                System.out.println(this.name);
            }
        };
    }
}
~~~

Đây là đoạn khai báo. `lambdaJob()` là **lambda**, nên `this` trong thân lambda có cùng ý nghĩa với `this` ở ngữ cảnh instance method `lambdaJob()`: trỏ tới `JobOwner`. `anonymousJob()` tạo object của **anonymous class**; `this` bên trong `run()` là anonymous object ấy.

Không nên suy luận rằng lambda “tương đương 100% anonymous class” trong mọi trường hợp: khác biệt về lexical scope và `this` là một ví dụ rất cụ thể.

## 13. Gọi method và virtual dispatch: `this.method()` không khóa implementation

Xem ví dụ:

~~~java
class Parent {
    void invoke() {
        this.describe();
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    @Override
    void describe() {
        System.out.println("Child");
    }
}
~~~

Nếu thực hiện:

~~~java
Parent object = new Child();
object.invoke();
~~~

Stdout là:

~~~text
Child
~~~

Phần này là **fragment trong method**, có thể kết hợp với hai class trên. `Parent.invoke()` gọi `this.describe()`; `this` là object `Child` thực tế nên dynamic dispatch chọn `Child.describe()`. Đây là đặc tính bình thường của instance method overriding.

**Hệ quả khi thiết kế constructor:** superclass constructor gọi `this.overridableMethod()` có thể chuyển điều khiển sang override của subclass **trước khi phần field initializer và constructor body của subclass hoàn tất**. Không nên gọi overridable methods trong constructor nếu chúng có thể đòi hỏi state subclass đã được khởi tạo.

## 14. So sánh `this == other` và `this.equals(other)`

Hai cách hỏi không nhất thiết giống nhau.

### 14.1. Identity với `==`

~~~java
class Node {
    boolean sameObject(Node other) {
        return this == other;
    }
}
~~~

Kết quả `true` khi hai tham chiếu trỏ đến chính một object, kể cả khi chúng là hai biến khác tên. `null` là một giá trị tham chiếu hợp lệ của parameter `other`; `this == null` không thể `true` trong một instance method đang được gọi bình thường trên một object.

### 14.2. Equality theo nội dung với `equals`

~~~java
class Tag {
    private final String code;

    Tag(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true; // Cùng object: tối ưu an toàn
        }
        if (!(other instanceof Tag tag)) {
            return false;
        }
        return this.code.equals(tag.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

Đây là đoạn khai báo với **pattern matching for instanceof** có trong Java 17. `equals` dùng `this == other` để nhận diện nhanh cùng object, sau đó so nội dung `code` khi `other` là một `Tag`.

Nếu hai đối tượng `new Tag("A")` khác nhau, phép `==` trên hai tham chiếu là `false` nhưng `equals` có thể là `true` vì code bằng nhau. Khi override `equals`, phải override `hashCode` phù hợp để không phá hợp đồng của collection dựa trên hash.

**Không dùng `this.equals(other)` một cách vô điều kiện nếu chưa hiểu hợp đồng.** Trong `equals`, tự gọi lại `this.equals(other)` không thay thế được logic so sánh và có thể dẫn đến đệ quy vô hạn.

## 15. Những ngộ nhận thường gặp về `this`

| Ngộ nhận | Thực tế |
| --- | --- |
| “`this` là tên class.” | `this` là tham chiếu đến current object, không phải tên class |
| “`this` trỏ đến object được tạo gần nhất.” | Nó trỏ đến receiver hiện tại của instance context |
| “Có hai biến tham chiếu thì có hai `this` khác object.” | Hai biến có thể cùng alias một object; khi gọi trên cùng object, `this` cùng identity |
| “`this.age = age` và `age = age` luôn giống nhau.” | Không nếu parameter/local `age` đang che field |
| “Cứ là instance method thì luôn bắt buộc viết `this.`.” | Thường có thể bỏ khi tên không bị che, compiler dùng receiver ngầm |
| “`return this` sao chép object.” | Không; trả cùng tham chiếu |
| “Gán lại `this = new X()` được.” | Không; `this` không phải biến có thể gán |
| “Trong static method có `this`.” | Không có implicit current instance trong static context |
| “`super` là một object riêng.” | Không; là cú pháp chọn hành vi thành viên của superclass trên cùng object |
| “`this(...)` và `this.method()` cùng là lời gọi method.” | `this(...)` là explicit constructor invocation; `this.method()` là instance method call |
| “`this` trong lambda luôn là lambda object.” | Không; `this` trong lambda giữ lexical enclosing meaning |
| “`this` trong anonymous class luôn là outer object.” | Không; `this` là anonymous class instance; dùng `Outer.this` nếu có enclosing instance phù hợp |
| “`this.field` bảo vệ khỏi race giữa nhiều thread.” | Không; `this` không tạo synchronization hoặc atomicity |
| “Truyền `this` khỏi constructor luôn an toàn.” | Có thể dẫn đến this escape trước khi object hoàn tất |

### 15.1. `this` không làm một thao tác trở nên thread-safe

~~~java
class Counter {
    private int count;

    void increment() {
        this.count++; // Vẫn không atomic trong nhiều thread
    }
}
~~~

Trong môi trường hai thread gọi cùng instance, `this.count++` có thể bị lost update giống `count++` nếu không có synchronization phù hợp. `this` chỉ định receiver; nó **không** là lock, memory barrier, `volatile` hay atomic variable.

Tương tự, hai biến tham chiếu `a` và `b` alias cùng một object thì gọi `a.increment()` và `b.increment()` trên hai thread vẫn tranh chấp **cùng field** của object.

## 16. Bài tập tự kiểm tra

**Câu 1.** Trong constructor `User(String name)` có field `String name`, tại sao `name = name;` có thể là bug?

**Đáp án:** Parameter `name` che field cùng tên; hai vế của phép gán chọn parameter. Dùng `this.name = name;` để gán giá trị của parameter vào field.

**Câu 2.** Nếu `A a1 = new A(); A a2 = a1;`, gọi `a1.method()` và `a2.method()` thì `this` có trỏ đến hai object khác nhau không?

**Đáp án:** Không. Cả hai biến đều trỏ cùng object; `this` ở mỗi lời gọi instance method biểu diễn object đó.

**Câu 3.** Method `A returnSelf() { return this; }` có tạo A mới không?

**Đáp án:** Không. Nó trả tham chiếu đến current object. Một lần gọi `new A()` mới tạo object theo đường khởi tạo thông thường.

**Câu 4.** Có thể viết `System.out.println(this);` trong một `static void main(String[] args)` không?

**Đáp án:** Không. `main` là static method nên không có current instance của class. Có thể tạo object rồi in tham chiếu hoặc gọi instance method của nó.

**Câu 5.** `this(10)` trong constructor có phải gọi một method tên `this` không?

**Đáp án:** Không. Đây là lời gọi constructor khác trong cùng class. Trong Java 17, lời gọi tường minh phải là câu lệnh đầu tiên trong constructor.

**Câu 6.** Trong `Outer.Inner` (non-static inner class), `this` và `Outer.this` phân biệt thế nào?

**Đáp án:** `this` là inner object hiện tại; `Outer.this` là enclosing outer object phù hợp.

**Câu 7.** `this` bên trong lambda được tạo bởi một instance method có trỏ tới một đối tượng lambda riêng không?

**Đáp án:** Không. Nó giữ ngữ nghĩa của `this` trong lexical enclosing context. Trong instance method bình thường, đó là enclosing instance.

**Câu 8.** Tại sao không nên viết `registry.add(this)` ngay đầu constructor khi object có các field bắt buộc chưa khởi tạo?

**Đáp án:** Vì code khác có thể quan sát object chưa hoàn chỉnh. Điều này có thể vi phạm invariant và nguyên tắc safe publication. Nên xây dựng xong rồi mới đăng ký.

**Câu 9.** Superclass method gọi `this.describe()` trên một object thuộc subclass và subclass override `describe()`. Implementation nào được chọn?

**Đáp án:** Instance method dispatch động thường chọn override của runtime class subclass. `this` không ép gọi implementation của superclass; `super.describe()` là cú pháp có mục đích khác.

**Câu 10.** `this == other` và `this.equals(other)` có luôn cùng kết quả không?

**Đáp án:** Không. `==` so sánh identity, còn `equals` có thể được class override để so sánh giá trị/nội dung.

## 17. Checklist áp dụng `this` khi viết class

1. **Xác định instance:** method/constructor này đang xử lý object nào?
2. **Kiểm tra shadowing:** field có trùng tên parameter/local không? Dùng `this.field` khi cần định vị field.
3. **Hiểu lời gọi nội bộ:** `this.method()` là method call trên current object, có thể chịu dynamic dispatch.
4. **Hiểu phép trả về:** `return this;` trả object hiện tại; không copy object.
5. **Khi truyền ra ngoài:** collaborator có thể lưu, sửa hoặc chia sẻ tham chiếu đó không?
6. **Trong constructor:** tránh công bố `this` khi object chưa xây dựng xong và tránh gọi overridable method rủi ro.
7. **Phân biệt cú pháp:** `this` là reference expression, `this(...)` là constructor delegation.
8. **Trong static context:** không có `this`; cần receiver instance hoặc parameter.
9. **Trong inner class/lambda/anonymous class:** xác định chính xác lexical/running receiver, khi phù hợp dùng `Outer.this`.
10. **Không suy ra thread-safety:** `this` không bảo vệ field khỏi race; nếu nhiều thread dùng chung object, cần chiến lược đồng bộ.

**Ghi nhớ ngắn:** `this` trả lời câu hỏi **“đối tượng nào đang nhận lời gọi instance hiện tại?”**. Khi viết `this.name`, `this.method()`, `return this;` hay truyền `this` làm đối số, bạn vẫn đang làm việc với **cùng một object**, chỉ khác thao tác trên object đó. Hiểu chính xác điều này là nền tảng để nắm vững constructor, encapsulation, chaining, inheritance và lớp lồng nhau trong Java.
