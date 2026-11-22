# Lớp lồng static và tham số kiểu độc lập trong Java Generics

## 1. Mục tiêu

Trong Java, một lớp có thể khai báo một lớp khác ở bên trong thân của mình. Nếu lớp thành viên đó dùng từ khóa **static**, nó được gọi là **static nested class** (lớp thành viên lồng static). Khi lớp bao ngoài là generic, cần hiểu rất rõ ranh giới của các **type variables**.

Ví dụ:

~~~java
class Outer<T> {
    static class Nested<U> {
        U value;
    }
}
~~~

Ở đây:

- **T** được khai báo bởi **Outer<T>**.
- **U** được khai báo bởi **Nested<U>**.
- **Nested** là một member class có từ khóa **static**, vì thế nó **không kế thừa phạm vi sử dụng T trong ngữ cảnh static** của Outer.
- **Nested<U>** là một generic class theo nghĩa có type parameter riêng U, dù nó được đặt bên trong Outer.
- Bên ngoài, kiểu lồng được viết **Outer.Nested<String>**, **Outer.Nested<Integer>**, v.v. Không cần chọn trước **Outer<String>** để đặt kiểu cho Nested.

Các mục tiêu học tập:

1. Phân biệt **static nested class** và **non-static inner class** về quan hệ với instance của Outer và khả năng sử dụng T.
2. Nhận diện đúng phạm vi của **T** và **U**, tránh cho rằng type parameter của lớp bao ngoài tự được truyền vào lớp lồng static.
3. Sử dụng cú pháp khai báo, khởi tạo và tham chiếu đúng đối với **Outer.Nested<U>**.
4. Thiết kế phương thức generic trong lớp lồng static khi cần làm việc với **Outer<T>**.
5. Xử lý nhiều type parameters, generic bounds, các member static bên trong lớp lồng và quan hệ với type erasure.
6. Nhận biết các lỗi phổ biến: tham chiếu T sai scope, dùng cú pháp Outer<String>.Nested<U>, nhầm constructor với outer instance và che tên type variable.

Các ví dụ có nhãn tệp đều viết theo Java 17+; các đoạn lỗi được ghi chú riêng để không nhầm với mã runnable.

## 2. Tại sao static tạo ra một ranh giới kiểu?

Hãy bắt đầu bằng một lớp generic thông thường:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

T thuộc khai báo **Box<T>**. Các thành viên instance như field value, constructor và get() có thể dùng T bởi chúng liên quan đến một cách sử dụng Box<T> cụ thể, chẳng hạn Box<String>.

Một thành viên static của Box<T> không thuộc riêng Box<String> hay Box<Integer>. Nó thuộc về **Box** xét ở mức class. Vì vậy không thể viết:

~~~java
// Chỉ minh họa lỗi biên dịch:
class Box<T> {
    // static T lastValue;          // Sai: static field không được dùng T.
    // static T echo(T value) {     // Sai: method static dùng T của lớp.
    //     return value;
    // }
}
~~~

Lớp lồng static có nguyên tắc tương tự đối với type parameter của lớp bao ngoài. Nó được khai báo bên trong Outer về mặt tổ chức tên, nhưng **không tự gắn với một instance Outer<T>**.

~~~java
class Outer<T> {
    private T instanceValue;

    static class Nested {
        // T cached; // Sai: không thể dùng T của Outer tại đây.
    }
}
~~~

Đặt Nested bên trong cặp ngoặc của Outer không làm cho mỗi Nested trở thành “lớp con riêng” cho từng Outer<T>. **Outer.Nested** là một member type tĩnh, không phụ thuộc vào đối số kiểu mà một instance Outer đang mang.

Từ khóa static ở đây không nói “mọi field bên trong Nested đều phải static”. Nested vẫn có thể chứa **instance fields**, constructors và instance methods bình thường; chính **khai báo member type Nested** là static theo quan hệ với Outer.

## 3. Lớp lồng static có thể tự khai báo tham số kiểu

Cú pháp đúng:

~~~java
class Outer<T> {
    static class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }
    }
}
~~~

**<U>** sau Nested là một khai báo type parameter độc lập; trong Nested<U>, U dùng được làm kiểu field value, tham số constructor và kiểu trả về get(). Trong khi đó T của Outer không dùng trực tiếp được trong phần thân Nested chỉ vì nó được khai báo bên ngoài.

Dùng lớp lồng:

~~~java
// Giả sử đang ở cùng package và Nested không bị giới hạn truy cập:
Outer.Nested<String> name = new Outer.Nested<>("Java");
Outer.Nested<Integer> count = new Outer.Nested<>(21);

String text = name.get();
Integer number = count.get();
~~~

Vì Nested được khai báo static, ta dùng **new Outer.Nested<>(...)**. Không cần tạo một instance Outer trước rồi mới có thể tạo Nested. Diamond **<>** suy luận U từ ngữ cảnh và constructor arguments; nó không phải danh sách type parameters mới.

Nếu thay U bằng T:

~~~java
class Outer<T> {
    static class Nested<T> {
        private T value;
    }
}
~~~

Thì **T của Nested<T> là một type parameter mới**, độc lập với T của Outer<T>. Trong khai báo Nested, tên T mới che tên trùng bên ngoài, nhưng ở một static nested class việc dùng type parameter bên ngoài cũng không hợp lệ. Cú pháp này có thể hợp lệ song **không được khuyến khích** vì người đọc dễ tưởng chúng là cùng một T. Tên **U**, **E**, **K** hoặc **V** thường giúp làm rõ hai phạm vi.

## 4. Ví dụ chạy độc lập: Outer<T> và Nested<U>

Lưu thành **StaticNestedDemo.java**:

~~~java
public class StaticNestedDemo<T> {
    private final T outerValue;

    StaticNestedDemo(T outerValue) {
        this.outerValue = outerValue;
    }

    T getOuterValue() {
        return outerValue;
    }

    static final class Nested<U> {
        private final U item;

        Nested(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }
    }

    public static void main(String[] args) {
        StaticNestedDemo<String> outer =
                new StaticNestedDemo<>("outer-data");

        StaticNestedDemo.Nested<Integer> count =
                new StaticNestedDemo.Nested<>(42);

        StaticNestedDemo.Nested<String> label =
                new StaticNestedDemo.Nested<>("nested-data");

        System.out.println(outer.getOuterValue());
        System.out.println(count.get());
        System.out.println(label.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StaticNestedDemo.java
java StaticNestedDemo
~~~

Stdout chính xác:

~~~text
outer-data
42
nested-data
~~~

Quan sát ba cách lựa chọn kiểu:

- **StaticNestedDemo<String>** chọn T của Outer là String.
- **StaticNestedDemo.Nested<Integer>** chọn U của Nested là Integer.
- **StaticNestedDemo.Nested<String>** chọn U của một instance Nested khác là String.

Không có quan hệ bắt buộc giữa **T = String** của outer và **U = Integer** của count. Chúng là các type arguments ở những khai báo độc lập. Mã có thể tạo count và label mà không cần outer; trong chương trình chỉ tạo outer để minh họa sự tồn tại song song.

Nhờ kiểu trả về **U get()**, compiler biết count.get() là Integer, label.get() là String, không đòi cast thủ công.

## 5. Cú pháp tham chiếu: Outer.Nested<U>, không phải Outer<T>.Nested<U>

Với:

~~~java
class Outer<T> {
    static class Nested<U> {}
}
~~~

Cú pháp mô tả kiểu lớp lồng ở nơi sử dụng là:

~~~java
// Minh họa trong một phương thức:
Outer.Nested<String> a = new Outer.Nested<>();
Outer.Nested<Integer> b = new Outer.Nested<>();
~~~

**Outer.Nested<String>** có nghĩa member type Nested<String> được khai báo trong Outer. Tên Outer đóng vai trò định danh lớp chứa thành viên tĩnh; không cần tham số hóa Outer trước.

Một ngộ nhận phổ biến:

~~~java
// Không hợp lệ, chỉ minh họa:
// Outer<String>.Nested<Integer> value;
~~~

Không thể chọn một static member class từ dạng tên Outer<String> đã tham số hóa như với inner class không static. Dấu **<String>** sau Outer ở đây không có vai trò cho Nested. Dạng đúng là **Outer.Nested<Integer>**.

Dấu chấm trong **Outer.Nested** dùng để định danh thành viên lớp, không hàm ý một object Outer có tham chiếu đến Nested. Lớp lồng static có thể được import bằng tên đầy đủ hoặc static import thích hợp theo luật import Java; khi viết tài liệu học tập, dùng dạng đầy đủ Outer.Nested<U> giúp dễ nhìn ra nơi khai báo.

Nếu Nested được khai báo **private**, mã bên ngoài Outer không thể dùng trực tiếp tên kiểu đó dù cú pháp generic đúng. Access modifiers như public, protected, private và package-private vẫn áp dụng bình thường; phạm vi type variable và quyền truy cập là hai quy tắc khác nhau.

## 6. Đối chiếu đủ để phân biệt với non-static inner class

Một **non-static inner class** có enclosing instance, nên được dùng `T` của `Outer<T>`; một **static nested class** không có liên kết ngầm đó. Xét ví dụ tối thiểu:

~~~java
class Outer<T> {
    private final T value;
    Outer(T value) { this.value = value; }

    class Inner<U> {
        U extra;
        Inner(U extra) { this.extra = extra; }
        T outerValue() { return value; }
    }

    static class Nested<U> {
        U extra;
        Nested(U extra) { this.extra = extra; }
    }
}
~~~

~~~java
Outer<String> owner = new Outer<>("parent");
Outer<String>.Inner<Integer> inner = owner.new Inner<>(5);
Outer.Nested<Integer> nested = new Outer.Nested<>(5);
~~~

Các lệnh sử dụng ở trên phải nằm trong method hoặc ngữ cảnh khai báo biến hợp lệ. Kết quả `inner.outerValue()` có kiểu `String`; `nested` không có outer object ngầm định.

| Điểm so sánh | Static nested | Non-static inner |
| --- | --- | --- |
| Kiểu tham chiếu | `Outer.Nested<U>` | `Outer<T>.Inner<U>` |
| Enclosing instance ngầm | Không | Có |
| Trực tiếp sử dụng `T` của outer | Không | Có, khi không bị che khuất |
| Khởi tạo từ ngoài outer | `new Outer.Nested<>(...)` | `owner.new Inner<>(...)` |
| Instance fields riêng của nó | Có | Có |

Phần khác biệt này đủ để xác định ranh giới **`T` của outer**. Các trường hợp tạo inner, `Outer.this`, lifecycle và aliasing thuộc trọng tâm học riêng về non-static inner class; ở đây tiếp tục phân tích **generic API bên trong static nested type**.

## 7. Tại sao static nested class không được dùng T của Outer trong field?

Giả sử ta muốn viết:

~~~java
// Không biên dịch:
class Holder<T> {
    static class Entry {
        // T data;  // Error: non-static type variable T in static context
    }
}
~~~

Nếu Entry có thể dùng T trực tiếp, câu hỏi sẽ là: “T nào?”. **Holder<String>.Entry** và **Holder<Integer>.Entry** không phải hai member types static được tham số hóa theo Holder. T của một Holder<T> cụ thể không nằm trong phạm vi dùng được bên trong khai báo static Entry.

Sửa theo ý định:

**Nếu Entry cần dữ liệu với một kiểu bất kỳ, tự khai báo U:**

~~~java
class Holder<T> {
    static class Entry<U> {
        U data;

        Entry(U data) {
            this.data = data;
        }
    }
}
~~~

**Nếu Entry phải gắn với một Holder<T> cụ thể, chuyển thành inner class:**

~~~java
class Holder<T> {
    class Entry {
        T data;

        Entry(T data) {
            this.data = data;
        }
    }
}
~~~

**Nếu muốn Entry vẫn static nhưng liên kết kiểu với một Holder khác, truyền mối liên hệ đó một cách tường minh:**

~~~java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    static class Entry<U> {
        private final Holder<U> owner;

        Entry(Holder<U> owner) {
            this.owner = owner;
        }

        U read() {
            return owner.value;
        }
    }
}
~~~

Trong ví dụ cuối, U thuộc Entry<U>. Field **Holder<U> owner** nói rõ owner phải là Holder mang đúng U, và read() trả U. Không cần truy cập T của lớp bao ngoài từ ngữ cảnh static; quan hệ kiểu được thiết lập qua **Holder<U>** như một parameterized type tường minh.

## 8. Static nested class có thể có phương thức generic riêng

Một type parameter của method khác với type parameter của class chứa method.

~~~java
class Outer<T> {
    static class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }

        static <X> X identity(X input) {
            return input;
        }
    }
}
~~~

Ở đây:

- **T** của Outer<T> không dùng trực tiếp trong Nested.
- **U** của Nested<U> dùng được trong instance field và instance method get().
- **X** của static generic method identity là type parameter **riêng của method**, không liên quan tới T hoặc U.

Ngay cả Nested<U> là generic class, static method trong nó **không được dùng U của lớp như một kiểu chưa khai báo riêng**:

~~~java
// Không biên dịch:
class Outer<T> {
    static class Nested<U> {
        // static U last;                 // Sai: static field dùng U của Nested.
        // static U echo(U input) {       // Sai: static method dùng U của Nested.
        //     return input;
        // }
    }
}
~~~

Lựa chọn đúng là **static <X> X echo(X input)**. Khi cần trả Nested<X> từ một static factory:

~~~java
class Outer<T> {
    static final class Nested<U> {
        private final U value;

        private Nested(U value) {
            this.value = value;
        }

        static <X> Nested<X> of(X value) {
            return new Nested<>(value);
        }

        U get() {
            return value;
        }
    }
}
~~~

Factory **Nested.of("abc")** có type parameter X do **method of** tự khai báo. Nếu gọi từ ngoài class Outer, dạng đầy đủ là **Outer.Nested.of("abc")**. Phương thức không dùng U từ một instance Nested trước đó; nó tạo một instance Nested<X> mới.

Trong class generic thông thường cũng vậy: **static <X> Box<X> of(X value)** là một generic static factory có type parameter độc lập; không dùng trực tiếp type parameter T của Box<T>.

## 9. Liên kết Outer<T> với Nested<U> qua generic method

Đôi khi cần giữ Nested là static để tránh phụ thuộc ngầm vào outer instance, nhưng vẫn muốn chuyển dữ liệu từ Outer<T> thành Nested<T>. Có thể mô tả quan hệ bằng một **generic method** nhận Outer<X> và trả Nested<X>.

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static final class Nested<U> {
        private final U item;

        private Nested(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }

        static <X> Nested<X> fromOuter(Outer<X> outer) {
            return new Nested<>(outer.value);
        }
    }
}
~~~

Dòng **static <X> Nested<X> fromOuter(Outer<X> outer)** nói rõ:

- **X** là type parameter được khai báo riêng cho static method.
- Tham số outer có kiểu **Outer<X>**, vì vậy field outer.value có kiểu X tại ngữ cảnh đó.
- Constructor nhận X, tạo **Nested<X>**.
- Người gọi không cần cast từ Object sang X; compiler kiểm tra mối liên hệ bằng chữ ký method.

Ví dụ:

~~~java
// Minh họa trong một phương thức:
Outer<String> source = new Outer<>("abc");
Outer.Nested<String> copy = Outer.Nested.fromOuter(source);
String result = copy.get();
~~~

Một static nested class được phép truy cập member private của lớp bao ngoài qua **một tham chiếu outer tường minh** nếu luật truy cập Java cho phép; các lớp lồng nhau thuộc cùng phạm vi nest có thể truy cập private members tương ứng. Điều quan trọng là **outer được truyền vào** chứ không ngầm tồn tại.

### Ví dụ runnable: static factory giữ đúng type parameter

Lưu thành **NestedFactoryDemo.java**:

~~~java
public class NestedFactoryDemo<T> {
    private final T stored;

    NestedFactoryDemo(T stored) {
        this.stored = stored;
    }

    static final class Result<U> {
        private final U value;

        private Result(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }

        static <X> Result<X> from(NestedFactoryDemo<X> source) {
            return new Result<>(source.stored);
        }

        static <X> Result<X> of(X value) {
            return new Result<>(value);
        }
    }

    public static void main(String[] args) {
        NestedFactoryDemo<String> text =
                new NestedFactoryDemo<>("hello");

        NestedFactoryDemo.Result<String> fromOuter =
                NestedFactoryDemo.Result.from(text);

        NestedFactoryDemo.Result<Integer> independent =
                NestedFactoryDemo.Result.of(99);

        System.out.println(fromOuter.get());
        System.out.println(independent.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedFactoryDemo.java
java NestedFactoryDemo
~~~

Stdout:

~~~text
hello
99
~~~

**from(text)** suy luận X = String nhờ tham số NestedFactoryDemo<X>. Còn **of(99)** suy luận X = Integer qua đối số int được boxing thành Integer. Cả hai factory nằm trong static nested Result<U>; X không phải U của một Result instance nào trước đó.

## 10. Tùy chọn dùng nhiều type parameters riêng

Static nested generic class có thể khai báo nhiều type parameters:

~~~java
class Context<T> {
    static final class Entry<K, V> {
        private final K key;
        private final V value;

        Entry(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() {
            return key;
        }

        V value() {
            return value;
        }
    }
}
~~~

**K và V** đều được khai báo riêng trên Entry; **T** của Context không được tự động liên hệ tới K hoặc V.

Trong cùng package:

~~~java
Context.Entry<String, Integer> entry =
        new Context.Entry<>("count", 5);

String name = entry.key();
Integer number = entry.value();
~~~

Một static nested class cũng có thể dùng một type parameter như U để tham số hóa các kiểu generic khác:

~~~java
class Library<T> {
    static class Group<U> {
        private final java.util.List<U> items =
                new java.util.ArrayList<>();

        void add(U item) {
            items.add(item);
        }

        java.util.List<U> snapshot() {
            return java.util.List.copyOf(items);
        }
    }
}
~~~

T trong Library<T> không dùng trực tiếp ở Group<U>. Group<U> khai báo U, sau đó dùng U làm type argument cho List<U>. **List.copyOf** không chấp nhận phần tử null; đây là chính sách của List.copyOf, không phải giới hạn riêng của static nested class.

Không có yêu cầu number of parameters của Outer và Nested phải bằng nhau. Outer<T> có thể chứa Nested<U>, Nested<K,V> hoặc một static nested class không generic tùy trách nhiệm. Thiết kế tốt dùng đúng số type parameters cần diễn tả quan hệ kiểu thật sự.

## 11. Type bounds: giới hạn U độc lập với giới hạn của T

Một lớp bao ngoài có bound không truyền bound ấy ngầm vào static nested class.

~~~java
class NumericOuter<T extends Number> {
    static class Holder<U> {
        private final U item;

        Holder(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }
    }
}
~~~

**T extends Number** chỉ giới hạn type arguments của NumericOuter<T>. Nó **không giới hạn U** của NumericOuter.Holder<U>. Do đó:

~~~java
// Minh họa:
NumericOuter.Holder<String> words =
        new NumericOuter.Holder<>("hello");
~~~

là hợp lệ; String không cần là Number để dùng làm U.

Nếu chính nested class cần thao tác với Number, khai báo bound trực tiếp trên U:

~~~java
class NumericOuter<T extends Number> {
    static class NumericHolder<U extends Number> {
        private final U item;

        NumericHolder(U item) {
            this.item = item;
        }

        double asDouble() {
            return item.doubleValue();
        }
    }
}
~~~

**NumericOuter.NumericHolder<Integer>** hợp lệ; **NumericOuter.NumericHolder<String>** không hợp lệ. U được giới hạn do khai báo **U extends Number** trên Nested, không phải do T extends Number ở Outer.

Không được tham chiếu đến T của Outer trong bound của static nested class:

~~~java
// Không biên dịch:
class Outer<T> {
    // static class Nested<U extends T> {}
}
~~~

Muốn biểu diễn quan hệ giữa U và một kiểu khác, có thể khai báo đầy đủ type parameters trên nested class và đặt bound giữa chúng:

~~~java
class Outer<T> {
    static class Related<X, Y extends X> {
        private final X parentValue;
        private final Y detail;

        Related(X parentValue, Y detail) {
            this.parentValue = parentValue;
            this.detail = detail;
        }
    }
}
~~~

X và Y là type parameters của Related; **Y extends X** là một quan hệ bound hợp lệ do cả X và Y đều nằm trong phạm vi của chính nested class. Nó vẫn không tự liên hệ với T của Outer. Quan hệ với một Outer<X> cụ thể phải được tạo qua tham số, field hoặc method thích hợp.

## 12. Static fields của nested class vẫn dùng chung giữa các `U`

Một `static nested class` có thể chứa cả **instance field kiểu `U`** và **static field kiểu cụ thể**:

~~~java
class Outer<T> {
    static class Counter<U> {
        private static int created;
        private final U value;

        Counter(U value) {
            this.value = value;
            created++;
        }

        U get() { return value; }
        static int createdCount() { return created; }
    }
}
~~~

Nếu tạo một `Outer.Counter<String>` và một `Outer.Counter<Integer>`, mỗi object giữ một `value` riêng nhưng cùng tăng trường `Counter.created`; giá trị trả bởi `Outer.Counter.createdCount()` là `2` nếu chưa có lần tạo nào khác. **Không** có bộ đếm riêng được Java tự sinh ra theo type argument `U`.

Không thể viết `static U lastValue` trong `Counter<U>` vì `U` thuộc generic class, còn field static không mang một `U` của instance. Với nhiều thread, `created++` không nguyên tử: dùng `AtomicInteger` hoặc đồng bộ nếu cần đếm chính xác. Nếu cần thống kê theo từng kiểu, hãy tự thiết kế map có key phân nhóm; type erasure không tạo static state riêng cho mỗi cách tham số hóa.

Ở đây điểm cần học là **hai lớp ranh giới static**: `Nested<U>` không được mượn `T` từ outer, và chính static members của `Nested<U>` cũng không được mượn `U` từ nested instance. Chi tiết class loading, `Class<T>` làm khóa và concurrency thuộc chủ đề riêng về trạng thái static dùng chung.

## 13. Không dùng trực tiếp outer instance members từ Nested

Static nested class vẫn có thể tham chiếu đến **static members** của Outer theo quyền truy cập. Nó không thể đọc **instance member** của Outer nếu chưa có outer reference.

~~~java
class Outer<T> {
    private static final String PREFIX = "item:";
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static class Nested<U> {
        private final U item;

        Nested(U item) {
            this.item = item;
        }

        String describe() {
            return PREFIX + item; // Hợp lệ: PREFIX là static.
        }

        // T readOuter() { return value; } // Sai: T và instance value không tự có.
    }
}
~~~

Muốn đọc outer value trong Nested, truyền một Outer<X>:

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static class Nested<U> {
        static <X> X read(Outer<X> outer) {
            return outer.value;
        }
    }
}
~~~

Ở đây **X** là type parameter của method read, không phải T của Outer hay U của Nested. Nó liên kết với kiểu của Outer<X> được truyền. Không có outer reference ngầm nào được tạo ra.

Một sự nhầm lẫn cần tránh là cho rằng việc nested class có quyền truy cập private member của Outer đồng nghĩa có thể gọi instance members khi không có instance. **Quyền truy cập (access control)** và **việc có receiver/biến kiểu đúng scope** là hai vấn đề độc lập.

## 14. Lớp lồng trong interface và record

Một số khai báo kiểu lồng trong Java có tính static theo quy tắc ngôn ngữ dù không viết từ khóa static.

### Class được khai báo bên trong interface

~~~java
interface Source<T> {
    T read();

    class Metadata<U> {
        private final U information;

        public Metadata(U information) {
            this.information = information;
        }

        public U information() {
            return information;
        }
    }
}
~~~

Member class Metadata bên trong interface được xem là **public static** (theo quy tắc implicit của interface member types). Nó không thể tự dùng type parameter T của Source<T>; vì thế khai báo U riêng.

Một cách dùng:

~~~java
Source.Metadata<String> metadata =
        new Source.Metadata<>("details");
~~~

Không viết **Source<String>.Metadata<String>** để chọn kiểu cho T của Source, vì Metadata không gắn với một instance Source<String>.

### Member record lồng trong generic class

Từ Java 16, record là một cấu trúc dữ liệu có component và các phương thức được sinh. Member record có tính static nên tự khai báo type parameter nếu cần:

~~~java
class Container<T> {
    record Entry<U>(U value) {}
}
~~~

Kiểu hợp lệ ở nơi sử dụng là **Container.Entry<Integer>**. T của Container<T> không dùng trực tiếp trong component của Entry; U thuộc khai báo record Entry<U>.

Điểm chung với static nested class là giới hạn phạm vi type variable của outer. Nếu record cần gói một giá trị kiểu T của một Container<T> cụ thể, có thể tạo generic factory nhận Container<X> và trả Entry<X> hoặc chuyển dữ liệu vào constructor Entry<X> như một tham số.

## 15. Type erasure và identity của static nested generic class

Generics trong Java chủ yếu là cấu trúc kiểm tra kiểu khi biên dịch. Việc tạo một object:

~~~java
Outer.Nested<String> words = new Outer.Nested<>("A");
Outer.Nested<Integer> counts = new Outer.Nested<>(1);
~~~

không tạo hai runtime classes khác nhau cho String và Integer. Thông thường cả hai object đều có cùng runtime Class là Outer.Nested, với thông tin type arguments đã được kiểm tra ở source code.

Với static nested class, tên bytecode thường có dạng **Outer$Nested.class**. Đây là tên lớp được javac tạo ra khi biên dịch một member nested class; dấu **$** ở file class không phải dấu phân cách ta dùng trong cú pháp Java source. Trong Java source, tham chiếu là **Outer.Nested<U>**.

Nếu dùng reflection, runtime có thể đọc metadata generic của **khai báo** nested class (ví dụ tên type parameter U). Nhưng không thể kết luận rằng getClass() trên một object bất kỳ sẽ tiết lộ đầy đủ đối số U của biến đã trỏ tới object đó. Muốn kiểm tra String hay Integer của dữ liệu runtime, phải có thông tin/giá trị kiểm tra phù hợp, ví dụ Class<U> được truyền riêng hoặc một cơ chế type token chuyên dụng.

Không dùng **new U()**, **U.class** hoặc **new U[10]** trong Nested<U> như thể U là một runtime class cụ thể. Các giới hạn cơ bản của type erasure áp dụng cho U giống các type variables khác.

## 16. Các lỗi phổ biến và cách sửa

### Lỗi 1: Dùng T của Outer trong static nested class

~~~java
// Cố ý sai:
class Outer<T> {
    static class Nested {
        // T item; // Error: cannot reference T from static context.
    }
}
~~~

**Sửa:** Nested tự khai báo **<U>**, hoặc bỏ static nếu thực sự cần inner class gắn với Outer<T>. Nếu cần truyền dữ liệu một lần, đưa nó vào constructor hoặc generic factory.

### Lỗi 2: Dùng Outer<String>.Nested<Integer>

~~~java
class Outer<T> {
    static class Nested<U> {}
}

// Cố ý sai:
// Outer<String>.Nested<Integer> entry;
~~~

**Sửa:** **Outer.Nested<Integer> entry;**. Lớp lồng static không có type argument T của một outer instance.

### Lỗi 3: Tạo static nested qua outer.new

~~~java
class Outer<T> {
    static class Nested<U> {}
}

// Không hợp lệ:
// Outer<String> owner = new Outer<>();
// var n = owner.new Nested<String>();
~~~

**Sửa:** **new Outer.Nested<String>()** hoặc **new Outer.Nested<>()** khi compiler suy luận được U. Cú pháp **owner.new Inner<>(...)** chỉ phù hợp cho inner class không static.

### Lỗi 4: Dùng U của Nested trong static method

~~~java
class Outer<T> {
    static class Nested<U> {
        // static U copy(U value) { return value; }
    }
}
~~~

**Sửa:** **static <X> X copy(X value)** hoặc dùng một instance method được phép sử dụng U.

### Lỗi 5: Để tên T giống nhau rồi tưởng hai type variables liên kết

~~~java
class Outer<T> {
    static class Nested<T> {
        T item;
    }
}
~~~

T bên trong Nested<T> là **một khai báo mới**. Dù dùng cùng ký hiệu T, Nested<T> không liên hệ kiểu với Outer<T>. **Sửa:** dùng **Nested<U>** cho dễ hiểu hoặc thiết kế field **Outer<U> owner** nếu thật sự cần liên hệ.

### Lỗi 6: Cận trên của Outer được hiểu nhầm là cận của Nested

~~~java
class Outer<T extends Number> {
    static class Nested<U> {}
}
~~~

**Outer.Nested<String>** vẫn có thể hợp lệ. Nếu U phải là Number, tự viết **static class Nested<U extends Number>**.

### Lỗi 7: Tham chiếu field instance của Outer không có object

~~~java
class Outer<T> {
    private T value;

    static class Nested<U> {
        // Object read() { return value; } // Sai, thiếu outer instance.
    }
}
~~~

**Sửa:** nhận một **Outer<X> outer** làm tham số vào generic method hoặc lưu tham chiếu Outer<U> thích hợp trong nested object.

### Lỗi 8: Tin static nested class không có instance state

~~~java
class Outer<T> {
    static class Nested<U> {
        private U value; // Hoàn toàn hợp lệ.
    }
}
~~~

Từ khóa static ở cấp member class chỉ xác định quan hệ với lớp bao ngoài. Nested vẫn là class có object, constructor, instance fields và instance methods bình thường.

### Lỗi 9: Tin static field phân chia theo type argument U

~~~java
class Outer<T> {
    static class Nested<U> {
        static int count;
    }
}
~~~

Cả Nested<String> và Nested<Integer> dùng chung static field count. Nếu cần dữ liệu theo kiểu runtime, phải thiết kế cơ chế định danh và map riêng; không dựa vào U sau erasure.

### Lỗi 10: Dùng Object và ép kiểu để vượt ranh giới

~~~java
// Thiết kế không an toàn kiểu, minh họa:
class Outer<T> {
    static class Nested {
        Object data;
    }
}
~~~

Khi caller nhận Object rồi tự cast, an toàn kiểu giảm. Nếu nested chứa dữ liệu có kiểu cụ thể, ưu tiên **Nested<U>**, **U get()**, generic factory, hay **Outer<U> owner** để compiler kiểm tra mối liên hệ.

### Lỗi 11: Xem static nested như subclass của Outer

**Outer.Nested<U>** không tự extends Outer<T>; nó chỉ được khai báo bên trong Outer. Quan hệ subtyping chỉ xuất hiện khi Nested có **extends SomeClass** hoặc **implements SomeInterface** riêng. Quyền truy cập giữa các lớp lồng nhau không tương đương kế thừa.

### Lỗi 12: Tạo inner class nhưng quên type arguments của outer

Với inner class dùng T của Outer, tên kiểu ngoài là **Outer<String>.Inner<Integer>**, tạo bằng **outer.new Inner<>(...)**. Nếu dùng raw Outer hoặc bỏ type information tùy tiện, ta có thể gặp cảnh báo hay mất độ chính xác của kiểu. Khi cần outer reference, hãy khai báo outer variable theo parameterized type đầy đủ.

## 17. Chọn static nested class hay inner class

Không có lựa chọn nào luôn tốt hơn. Xét mối quan hệ thực:

- **Chọn static nested class** khi loại dữ liệu/helper về mặt tổ chức thuộc Outer nhưng mỗi instance không cần một outer instance ngầm định. Tham số kiểu của nó nên được khai báo riêng, ví dụ **Outer.Entry<K,V>**, **Outer.Result<U>**.
- **Chọn inner class không static** khi mỗi inner instance cần truy cập trạng thái instance của một Outer<T> cụ thể và quan hệ ấy là bản chất của mô hình. Khi đó T của outer có thể dùng trực tiếp và tên kiểu ở nơi sử dụng là **Outer<T>.Inner<U>**.
- **Chọn static nested class + explicit Outer<U> reference** nếu muốn quan hệ được thể hiện rõ ở field/constructor, kiểm soát vòng đời và tránh một enclosing-instance reference tự động.
- **Chọn top-level class** nếu kiểu đó không thực sự có quan hệ tổ chức hoặc API với Outer; việc lồng class không phải điều kiện tiên quyết của generics.
- **Chọn generic method trong nested class** khi kiểu liên hệ chỉ cần cho một thao tác, chẳng hạn **static <X> Nested<X> from(Outer<X> source)**; không cần buộc mọi Nested instance mang cùng một outer object.

Khi thiết kế API, hãy xem tên kiểu xuất hiện tại nơi sử dụng có dễ hiểu không. **Outer.Nested<U>** giúp nhóm các kiểu cùng chức năng; nhưng nếu nesting quá sâu, generic signatures có thể khó đọc hơn so với một top-level type có tên rõ ràng.

## 18. Bài thực hành tự kiểm tra

**Câu 1.** Trong **class Outer<T> { static class Nested<U> {} }**, T và U có cùng scope không?

**Đáp án:** Không. T thuộc Outer<T>, U thuộc Nested<U>. Static nested class không tự dùng được T của outer trong phần thân; U dùng trong các instance members của Nested.

**Câu 2.** Có thể khai báo biến **Outer<String>.Nested<Integer> v** không?

**Đáp án:** Không. Với static nested class, viết **Outer.Nested<Integer> v**. Type argument String của Outer<String> không có vai trò ở static member type này.

**Câu 3.** Có cần instance Outer trước khi gọi **new Outer.Nested<String>()** không?

**Đáp án:** Không. Static nested class không có enclosing instance ngầm định, nên có thể tạo qua tên kiểu Outer.Nested.

**Câu 4.** Tại sao **static class Nested<T>** trong Outer<T> vẫn dùng được ký hiệu T?

**Đáp án:** Vì Nested tự khai báo **một type parameter T mới**. Nó độc lập với T được khai báo bởi Outer, dù cùng tên chữ.

**Câu 5.** Muốn Nested dùng được T của một Outer<String> cụ thể và có outer reference ngầm định, chọn loại class nào?

**Đáp án:** **Non-static inner class**, ví dụ **class Inner<U>** trong Outer<T>. Sử dụng kiểu **Outer<String>.Inner<Integer>** và khởi tạo với **outer.new Inner<>(...)**.

**Câu 6.** Nếu static nested class cần đọc giá trị từ một Outer<T> nhưng vẫn không muốn gắn ngầm với outer instance thì làm gì?

**Đáp án:** Truyền một **Outer<X>** vào constructor hoặc generic method, sử dụng X làm type parameter cục bộ của nested class/method và công bố đúng quan hệ kiểu.

**Câu 7.** Trong **static class Nested<U>**, có thể viết **static U get(U input)** không?

**Đáp án:** Không, vì U thuộc generic class và không khả dụng từ static context. Viết **static <X> X get(X input)** nếu method cần generic độc lập.

**Câu 8.** Outer<T extends Number> có buộc Nested<U> chỉ nhận U extends Number không?

**Đáp án:** Không. U độc lập. Muốn giới hạn, viết rõ **static class Nested<U extends Number>**.

**Câu 9.** Field static **count** của Nested<U> có một bản cho Nested<String> và một bản cho Nested<Integer> không?

**Đáp án:** Không. Các cách sử dụng type arguments khác nhau chia sẻ static state của cùng nested runtime class.

**Câu 10.** Tại sao **Outer.Nested<String>** và **Outer.Nested<Integer>** có thể dùng cùng một runtime class?

**Đáp án:** Java generics sử dụng type erasure; compiler kiểm tra type arguments tại source code nhưng không tạo class runtime khác nhau cho từng U.

**Câu 11.** Một nested class nằm trong interface generic có được ngầm hiểu là static không?

**Đáp án:** Có. Member class trong interface có tính public static, nên không tự có type variable của interface bao ngoài; cần khai báo type parameter riêng hoặc truyền kiểu vào một method/constructor.

**Câu 12.** Member record khai báo trong Outer<T> có dùng trực tiếp T làm record component type không?

**Đáp án:** Không. Member record có tính static; nếu muốn kiểu thành phần linh hoạt, khai báo **record Entry<U>(U value)** rồi dùng Outer.Entry<U>.

## 19. Checklist khi đọc hoặc viết mã

1. **Xác định từ khóa static.** Member type là **static class Nested** hay **class Inner**?
2. **Ghi rõ người sở hữu mỗi type variable.** T thuộc Outer, U thuộc Nested, X thuộc generic method.
3. **Kiểm tra tên kiểu dùng bên ngoài.** Static: **Outer.Nested<U>**. Inner: **Outer<T>.Inner<U>**.
4. **Kiểm tra cách khởi tạo.** Static: **new Outer.Nested<>(...)**. Inner: **outer.new Inner<>(...)**.
5. **Kiểm tra nguồn dữ liệu outer.** Nếu Nested cần instance members của Outer, có outer reference tường minh không?
6. **Kiểm tra static members trong Nested<U>.** Chúng không được dùng U của Nested như một type variable thuộc static context.
7. **Kiểm tra bounds.** Ràng buộc của outer T không tự áp dụng cho nested U.
8. **Kiểm tra thiết kế sau erasure.** Không kỳ vọng static state hay runtime class được tách theo mỗi type argument.
9. **Kiểm tra access modifiers.** Một static nested class private không thể được sử dụng trực tiếp từ bên ngoài lớp khai báo dù cú pháp generic chính xác.
10. **Ưu tiên kiểu rõ ràng.** Nếu cần liên hệ với Outer<T>, biểu diễn nó trong method signature hoặc một field kiểu Outer<U>, tránh raw type và cast không kiểm tra.

## 20. Kết luận

**Static nested class có thể generic nhưng type parameters của nó độc lập với generic outer class.** Với **class Outer<T> { static class Nested<U> {} }**, T thuộc Outer còn U thuộc Nested. Cú pháp sử dụng là **Outer.Nested<U>** và có thể khởi tạo bằng **new Outer.Nested<>(...)** mà không cần một Outer instance.

Khi thật sự cần ràng buộc cùng một kiểu với một Outer<T> cụ thể, hãy chọn **inner class không static** hoặc đưa quan hệ vào **Outer<X>** và generic method/constructor một cách tường minh. Hiểu đúng ranh giới static này giúp tránh lỗi scope, giữ an toàn kiểu và thiết kế các nested APIs rõ ràng trên Java.
