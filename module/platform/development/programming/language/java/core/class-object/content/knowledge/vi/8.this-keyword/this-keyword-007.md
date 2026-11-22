# Truy cập đối tượng bao ngoài bằng `Outer.this` trong Java

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **đối tượng hiện tại** (`this`) của một lớp bên trong với **đối tượng bao ngoài** (*enclosing instance*) của lớp đó.
- Hiểu cú pháp **`Outer.this`** (*qualified this expression*) và điều kiện dùng nó trong các lớp lồng **không `static`**.
- Truy cập đúng field/method của lớp bao ngoài khi lớp bên trong cũng có thành viên hoặc biến cùng tên.
- Tạo các inner objects bằng `outer.new Inner()`, giải thích mối liên hệ của inner object với outer object cụ thể.
- Dùng `Middle.this` và `Outer.this` khi có nhiều tầng lớp lồng, và dùng qualified `this` từ local/anonymous class ở ngữ cảnh hợp lệ.
- Nhận biết nơi **không** dùng được `Outer.this`: static nested class, static context không có enclosing instance tương ứng, top-level class hoặc lớp không có quan hệ bao ngoài về mặt từ vựng.
- Phân biệt qualified `this` với tham chiếu qua một field, qua biến local, với static member access và với cách `this` hoạt động trong lambda.
- Tránh vấn đề giữ tham chiếu tới outer object ngoài ý muốn khi thiết kế inner class.

## 1. Hai đối tượng trong một non-static inner class

Ví dụ cấu trúc lớp:

~~~java
class Outer {
    private String name = "Outer object";

    class Inner {
        private String name = "Inner object";

        void show() {
            System.out.println(this.name);
            System.out.println(Outer.this.name);
        }
    }
}
~~~

Đây là **khai báo lớp minh họa**, có thể biên dịch trong tệp Java thích hợp nhưng chưa có `main` để chạy riêng.

Trong `Inner.show()` có **hai đối tượng liên quan**:

1. `this` chỉ đến **đối tượng `Inner` đang thực thi method**. Vì vậy `this.name` là field `name` của chính inner object.
2. `Outer.this` chỉ đến **đối tượng `Outer` bao ngoài về mặt từ vựng** gắn với inner object ấy. Vì vậy `Outer.this.name` là field `name` của outer object.

Điểm khác nhau không nằm ở chỗ hai field có tên `name` giống nhau; khác nhau là **tham chiếu nhận field access**:

| Biểu thức trong `Inner` | Tham chiếu chỉ đến | Ví dụ |
| --- | --- | --- |
| `this` | Inner object hiện tại | `this.name` |
| `Outer.this` | Outer object bao ngoài gắn với inner object | `Outer.this.name` |
| `name` (không tiền tố) | Tên được giải quyết theo phạm vi/sự che khuất trong Java | Thường là field của `Inner` nếu field ấy tồn tại |
| `Outer.this.someMethod()` | Gọi instance method trên outer object tương ứng | `Outer.this.describe()` |
| `Outer.staticField` | Static member thuộc lớp `Outer` | Không cần `Outer.this` |

**Không có cú pháp chung `outer.this` với tên biến `outer` viết thường.** `Outer` trong `Outer.this` là **tên kiểu bao ngoài** ở vị trí cú pháp Java cho phép. Nếu bạn đã có biến tham chiếu `Outer outer`, hãy truy cập `outer.name` (nếu được phép); còn `Outer.this` chỉ biểu thị enclosing instance do cấu trúc lớp và đối tượng quyết định.

### 1.1. `Outer.this` không tạo object mới

Biểu thức `Outer.this` **không** gọi constructor, **không** thực thi `new Outer()`, và cũng **không** chép trạng thái outer object. Nó cung cấp tham chiếu tới enclosing instance đã tồn tại.

Nếu `Outer.this` được đánh giá trong một inner object hợp lệ, kết quả là tham chiếu tới một đối tượng bao ngoài phù hợp với quan hệ lồng đã thiết lập; không phải một factory hay cơ chế tìm “Outer object mới nhất”.

## 2. Ví dụ độc lập đầu tiên: `this` và `Outer.this`

Lưu tệp **`OuterThisBasics.java`**:

~~~java
public class OuterThisBasics {
    private final String name;

    public OuterThisBasics(String name) {
        this.name = name;
    }

    private String describe() {
        return "description of " + name;
    }

    class Inner {
        private final String name;

        Inner(String name) {
            this.name = name;
        }

        void print() {
            System.out.println("inner=" + this.name);
            System.out.println("outer=" + OuterThisBasics.this.name);
            System.out.println("outer method=" + OuterThisBasics.this.describe());
        }
    }

    public static void main(String[] args) {
        OuterThisBasics outer = new OuterThisBasics("Room A");
        OuterThisBasics.Inner inner = outer.new Inner("Seat 1");
        inner.print();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 OuterThisBasics.java
java OuterThisBasics
~~~

Output chính xác:

~~~text
inner=Seat 1
outer=Room A
outer method=description of Room A
~~~

**Phân tích:**

- `new OuterThisBasics("Room A")` tạo outer object và gán field `name = "Room A"`.
- `outer.new Inner("Seat 1")` tạo một **non-static inner object** gắn với đúng outer object đang nằm trong biến `outer`.
- Constructor `Inner(String name)` dùng `this.name = name`: `this` là đối tượng `Inner`; tên parameter trùng tên field `Inner.name` nên phải phân biệt rõ.
- `this.name` trong `print` trả `"Seat 1"`.
- `OuterThisBasics.this.name` trả `"Room A"`.
- `OuterThisBasics.this.describe()` gọi được private method của outer class vì quyền truy cập giữa các lớp lồng cho phép trường hợp này trong Java. Không cần biến `outer` của `main` hiện diện bên trong `Inner`.

**Lưu ý:** field `name` của `OuterThisBasics` là `private`; việc inner class truy cập thành viên private của enclosing class được Java hỗ trợ theo quy tắc truy cập thành viên lồng. Điều đó **không** nghĩa một lớp bất kỳ ngoài cấu trúc lồng đều truy cập được `private`.

## 3. Vì sao cần qualified `this` khi tên bị che khuất?

**Shadowing (che khuất tên)** xảy ra khi một khai báo nằm trong phạm vi gần hơn có cùng tên với một khai báo bên ngoài. Trong inner class có thể có cả field của outer, field của inner, tham số và biến cục bộ trùng tên.

Xem đoạn sau:

~~~java
class Screen {
    private String title = "Outer title";

    class Panel {
        private String title = "Inner title";

        void rename(String title) {
            // title ở đây là tham số.
            this.title = title;
            // Screen.this.title là field thuộc outer object.
        }

        void show() {
            String title = "Local title";

            System.out.println(title);
            System.out.println(this.title);
            System.out.println(Screen.this.title);
        }
    }
}
~~~

Đây là khai báo lớp minh họa, chưa có `main`.

Trong `show()`:

| Biểu thức | Kết quả ở trạng thái ban đầu |
| --- | --- |
| `title` | Local variable `"Local title"` |
| `this.title` | Instance field của `Panel`: `"Inner title"` |
| `Screen.this.title` | Instance field của `Screen`: `"Outer title"` |

`this` giúp phân biệt local/parameter với field của inner class, còn `Screen.this` giúp chọn **field của outer class**, bất kể bên trong có field trùng tên.

### 3.1. Chương trình chạy được: cả local, parameter, inner field và outer field

Lưu **`ShadowingOuterThisDemo.java`**:

~~~java
public class ShadowingOuterThisDemo {
    private String label = "OUTER";

    class Inner {
        private String label = "INNER";

        void changeInner(String label) {
            this.label = label;
        }

        void show() {
            String label = "LOCAL";
            System.out.println("local=" + label);
            System.out.println("inner=" + this.label);
            System.out.println("outer=" + ShadowingOuterThisDemo.this.label);
        }

        void changeOuter(String label) {
            ShadowingOuterThisDemo.this.label = label;
        }
    }

    public static void main(String[] args) {
        ShadowingOuterThisDemo outer = new ShadowingOuterThisDemo();
        ShadowingOuterThisDemo.Inner inner = outer.new Inner();

        inner.show();
        inner.changeInner("NEW INNER");
        inner.changeOuter("NEW OUTER");
        inner.show();
    }
}
~~~

Chạy:

~~~bash
javac ShadowingOuterThisDemo.java
java ShadowingOuterThisDemo
~~~

Output:

~~~text
local=LOCAL
inner=INNER
outer=OUTER
local=LOCAL
inner=NEW INNER
outer=NEW OUTER
~~~

Khi gọi `changeInner("NEW INNER")`, tham số `label` che khuất field cùng tên; `this.label = label` cập nhật **inner field**. Còn `ShadowingOuterThisDemo.this.label = label` trong `changeOuter` cập nhật **outer field**. Điều này cho thấy qualified `this` có thể dùng cho cả **đọc** lẫn **ghi**, miễn quyền truy cập và quy tắc khác (ví dụ `final`) cho phép.

## 4. Tạo inner object và xác định enclosing instance

Một **non-static member class** như `Outer.Inner` có mối liên kết đến một instance của `Outer`. Có thể tạo inner object theo các cách hợp lệ:

~~~java
Outer first = new Outer();
Outer.Inner child = first.new Inner();
~~~

Đây là mã minh họa khi lớp `Outer` có constructor không tham số và inner class `Inner` có constructor phù hợp. Dấu chấm trong `first.new Inner()` thể hiện rõ object `first` là enclosing instance được chọn.

Khi đang ở **instance method hoặc constructor của `Outer`**, có thể khởi tạo inner class trực tiếp bằng `new Inner()` nếu ngữ cảnh cung cấp enclosing instance và quyền truy cập cho phép:

~~~java
class Outer {
    class Inner { }

    Inner create() {
        return new Inner();
    }
}
~~~

Với `create()` ở trên, inner object tạo ra gắn với **`this` của `Outer`** gọi `create`.

Ngược lại, trong **static method của `Outer`** không có `this` của `Outer`, nên thông thường cần một biến tham chiếu tới outer object:

~~~java
class Outer {
    class Inner { }

    static Inner createFrom(Outer outer) {
        return outer.new Inner();
    }
}
~~~

`createFrom` là static method nhưng **vẫn tạo được inner object** vì nó nhận rõ một `Outer outer`. Điều không hợp lệ là dùng `Outer.this` ngay trong thân static method đó; static context của `Outer` không có enclosing `Outer` instance tương ứng.

### 4.1. Inner object giữ liên kết với outer object đã chọn

Không được hiểu rằng `Outer.this` “tự tìm” biến outer nào đang trỏ tới instance đó vào thời điểm gọi method. Liên kết enclosing instance được thiết lập khi inner object được tạo; một phép gán lại biến local bên ngoài **không chuyển** inner object sang enclosing instance khác.

Ví dụ đầy đủ **`EnclosingBindingDemo.java`**:

~~~java
public class EnclosingBindingDemo {
    private final String id;

    private EnclosingBindingDemo(String id) {
        this.id = id;
    }

    class Inner {
        void printOuter() {
            System.out.println("enclosing=" + EnclosingBindingDemo.this.id);
        }
    }

    public static void main(String[] args) {
        EnclosingBindingDemo first = new EnclosingBindingDemo("A");
        EnclosingBindingDemo second = new EnclosingBindingDemo("B");

        EnclosingBindingDemo.Inner a = first.new Inner();
        EnclosingBindingDemo.Inner b = second.new Inner();

        first = second;

        a.printOuter();
        b.printOuter();
        System.out.println("variable first=" + first.id);
    }
}
~~~

Lệnh:

~~~bash
javac EnclosingBindingDemo.java
java EnclosingBindingDemo
~~~

Output:

~~~text
enclosing=A
enclosing=B
variable first=B
~~~

`a` được tạo từ đối tượng A, `b` từ B. Dù biến `first` sau đó được gán sang B, `a` vẫn có enclosing instance là A.

**Lưu ý quan trọng:** inner object và outer object là hai object khác nhau, không phải hai tên của cùng một object. `a` giữ liên kết đến A; `EnclosingBindingDemo.this` bên trong `a` trả tham chiếu A, còn `this` trả tham chiếu `a` tự nó.

## 5. Nhiều cấp lồng nhau: `Inner.this`, `Middle.this`, `Outer.this`

Lớp trong có thể chứa một lớp trong khác. Khi một method nằm ở cấp sâu, Java cho phép dùng **tên lớp bao ngoài phù hợp** để xác định instance ở đúng tầng.

Ví dụ **`NestedLevelsDemo.java`**:

~~~java
public class NestedLevelsDemo {
    private final String level = "OUTER";

    class Middle {
        private final String level = "MIDDLE";

        class Inner {
            private final String level = "INNER";

            void show() {
                System.out.println("inner=" + this.level);
                System.out.println("middle=" + Middle.this.level);
                System.out.println("outer=" + NestedLevelsDemo.this.level);
            }
        }
    }

    public static void main(String[] args) {
        NestedLevelsDemo outer = new NestedLevelsDemo();
        NestedLevelsDemo.Middle middle = outer.new Middle();
        NestedLevelsDemo.Middle.Inner inner = middle.new Inner();

        inner.show();
    }
}
~~~

Chạy:

~~~bash
javac NestedLevelsDemo.java
java NestedLevelsDemo
~~~

Output:

~~~text
inner=INNER
middle=MIDDLE
outer=OUTER
~~~

Ở trong `Inner.show()`:

- `this.level` là field trên **`Inner`**.
- `Middle.this.level` là field trên **enclosing instance `Middle`**.
- `NestedLevelsDemo.this.level` là field trên **enclosing instance `NestedLevelsDemo`**.

Đây là **quan hệ lồng nhau từ vựng** (*lexical nesting*), không phải quá trình “lần lên theo kiểu cha” như kế thừa.

### 5.1. Lồng nhau khác kế thừa

`extends` biểu diễn quan hệ subtype/superclass; **inner class** biểu diễn một khai báo class nằm trong phạm vi class khác và có enclosing instance tương ứng khi không `static`.

Ví dụ `class Inner extends Base` có thể vừa có **superclass `Base`** vừa có **enclosing class `Outer`**, là hai quan hệ độc lập:

~~~java
class Base {
    String source = "base";
}

class Outer {
    String source = "outer";

    class Inner extends Base {
        void show() {
            System.out.println(super.source);
            System.out.println(Outer.this.source);
        }
    }
}
~~~

Đây là mã lớp minh họa hợp lệ. `super.source` truy cập thành viên từ nhánh **kế thừa `Base`**, còn `Outer.this.source` truy cập field của **enclosing `Outer` object**. Không thay `Outer.this` bằng `super` nếu bạn muốn lấy đúng enclosing instance.

## 6. Qualified `this` trong local class và anonymous class

`Outer.this` không chỉ xuất hiện trong member inner class. Nó còn có thể dùng trong **local class** (khai báo class bên trong block/method) hoặc **anonymous class** nằm trong ngữ cảnh có enclosing instance tương ứng.

### 6.1. Local class bên trong instance method

Lưu **`LocalClassOuterThisDemo.java`**:

~~~java
public class LocalClassOuterThisDemo {
    private final String owner;

    LocalClassOuterThisDemo(String owner) {
        this.owner = owner;
    }

    void runTasks() {
        int repeat = 2;

        class Task {
            void execute() {
                System.out.println("task=" + LocalClassOuterThisDemo.this.owner
                        + ":" + repeat);
            }
        }

        new Task().execute();
    }

    public static void main(String[] args) {
        new LocalClassOuterThisDemo("Lan").runTasks();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LocalClassOuterThisDemo.java
java LocalClassOuterThisDemo
~~~

Output:

~~~text
task=Lan:2
~~~

Lớp local `Task` được khai báo bên trong **instance method** `runTasks()` của `LocalClassOuterThisDemo`. Bên trong `Task.execute()`, `this` là object `Task`, còn `LocalClassOuterThisDemo.this` là object đã gọi `runTasks()`.

Biến local `repeat` được sử dụng từ local class vì nó là **effectively final** (không bị gán lại). Đây là quy tắc capture của local variables, khác với việc qualified `this` cung cấp tham chiếu tới enclosing instance.

### 6.2. Anonymous class và `this` riêng của nó

Lưu **`AnonymousOuterThisDemo.java`**:

~~~java
public class AnonymousOuterThisDemo {
    private final String label = "OUTER";

    void demo() {
        Runnable action = new Runnable() {
            private final String label = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("this=" + this.label);
                System.out.println("outer=" + AnonymousOuterThisDemo.this.label);
            }
        };

        action.run();
    }

    public static void main(String[] args) {
        new AnonymousOuterThisDemo().demo();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousOuterThisDemo.java
java AnonymousOuterThisDemo
~~~

Output:

~~~text
this=ANONYMOUS
outer=OUTER
~~~

Trong thân `run()` của **anonymous class**:

- `this` là instance của anonymous class triển khai `Runnable`.
- `AnonymousOuterThisDemo.this` là instance của lớp bao ngoài.
- `label` tại hai cấp có thể trùng tên nhưng không phải cùng field.

**Đừng nhầm với lambda:** một lambda expression **không tạo ra ngữ nghĩa `this` riêng như thân anonymous class**. Trong lambda viết trực tiếp trong instance method, `this` tiếp tục có ý nghĩa theo ngữ cảnh enclosing. Mục tiếp theo minh họa cụ thể.

## 7. `this` trong lambda khác anonymous class

Khi viết lambda trong một **instance method** của `Outer`, `this` trong thân lambda thường chỉ **đối tượng `Outer` hiện tại**, không phải một “lambda object” để truy cập bằng `this`.

Lưu **`LambdaThisDemo.java`**:

~~~java
public class LambdaThisDemo {
    private final String name = "OWNER";

    void compare() {
        Runnable lambda = () -> {
            System.out.println("lambda this=" + this.name);
            System.out.println("lambda outer=" + LambdaThisDemo.this.name);
        };

        Runnable anonymous = new Runnable() {
            private final String name = "ANON";

            @Override
            public void run() {
                System.out.println("anonymous this=" + this.name);
                System.out.println("anonymous outer=" + LambdaThisDemo.this.name);
            }
        };

        lambda.run();
        anonymous.run();
    }

    public static void main(String[] args) {
        new LambdaThisDemo().compare();
    }
}
~~~

Chạy:

~~~bash
javac LambdaThisDemo.java
java LambdaThisDemo
~~~

Output:

~~~text
lambda this=OWNER
lambda outer=OWNER
anonymous this=ANON
anonymous outer=OWNER
~~~

Giải thích:

1. Lambda là biểu thức có **lexical scoping**: `this` trong lambda của instance method `compare()` trỏ đến `LambdaThisDemo` object.
2. `LambdaThisDemo.this.name` trong lambda cũng trỏ đến object đó.
3. Trong anonymous class, `this.name` trỏ đến field `name` của instance anonymous.
4. `LambdaThisDemo.this.name` trong anonymous class vẫn truy cập outer instance.

Không nên viết `this` bên trong lambda rồi suy đoán rằng nó luôn là đối tượng triển khai functional interface. Nếu cần hành vi thực thể riêng của một loại `Runnable`, hãy chọn class phù hợp thay vì lợi dụng semantics của lambda.

## 8. Không dùng được `Outer.this` ở đâu?

Cú pháp qualified `this` chỉ hợp lệ khi tồn tại **enclosing instance phù hợp trong ngữ cảnh từ vựng**; không thể yêu cầu Java tạo hoặc tìm outer instance tùy ý.

### 8.1. Static nested class KHÔNG mang enclosing `Outer` instance

~~~java
class Outer {
    private String name = "Outer";

    static class Nested {
        void invalid() {
            // System.out.println(Outer.this.name); // Không biên dịch
        }
    }
}
~~~

Trong `static class Nested`, không có một enclosing `Outer` instance được gắn **tự động** vào mỗi `Nested` object. Vì vậy `Outer.this` không hợp lệ bên trong method bình thường của `Nested`.

Nhưng bạn vẫn có thể **truyền một tham chiếu Outer một cách tường minh**:

~~~java
class Outer {
    private final String name;

    Outer(String name) {
        this.name = name;
    }

    static class Nested {
        private final Outer owner;

        Nested(Outer owner) {
            this.owner = owner;
        }

        void show() {
            System.out.println(owner.name);
        }
    }
}
~~~

Đây là một **phương án thay thế** của class `Outer`; nó biên dịch được khi đặt trong tệp riêng/phù hợp. `owner.name` hoạt động vì `owner` là field chứa tham chiếu được truyền vào, **không phải vì static nested class có `Outer.this`**.

### 8.2. Static method của Outer không có `Outer.this`

~~~java
class Outer {
    int value = 10;

    static void inspect(Outer object) {
        // System.out.println(Outer.this.value); // Sai: static context
        System.out.println(object.value);       // Đúng khi object khác null
    }
}
~~~

Static method có thể **nhận một đối tượng `Outer` làm tham số**, và tham chiếu qua biến đó, nhưng bản thân static method không có current `Outer` instance để dùng `Outer.this`.

### 8.3. Outer class không được lồng trong Outer khác

Trong chính một **top-level class `Outer`**, `this` là tham chiếu phù hợp tới object hiện tại trong instance context. Không có một outer instance khác cùng tên chỉ bởi vì bạn viết `Outer.this`. Qualified `this` có ý nghĩa khi tên kiểu nằm trong phạm vi từ vựng của một enclosing instance tương ứng; đừng dùng như cách trang trí thay `this` ở mọi nơi.

### 8.4. Không thể trỏ qua một lớp không phải lexical enclosing type

Giả sử có `OuterA.InnerA` và `OuterB.InnerB`. Trong `OuterA.InnerA` bạn không được tùy ý viết `OuterB.this` chỉ vì chương trình có một object `OuterB` ở đâu đó. Nếu cần dùng object thuộc lớp không bao ngoài về mặt lexical scope, hãy truyền nó qua parameter, field hoặc dependency tương ứng.

### 8.5. Ranh giới tĩnh lồng giữa hai tầng

Một static nested class nằm giữa các tầng lồng không tự mang enclosing instance của tầng phía ngoài. Vì vậy ở phía bên trong một lớp tiếp tục lồng bên dưới nó, không thể giả định `Outer.this` vẫn tồn tại. Cần phân biệt **lồng nhau về tên kiểu** với **có enclosing instance thực sự** trong ngữ cảnh đang xét.

## 9. Ví dụ độc lập: static nested class dùng owner field thay vì qualified `this`

Lưu **`StaticNestedOwnerDemo.java`**:

~~~java
public class StaticNestedOwnerDemo {
    private final String id;

    StaticNestedOwnerDemo(String id) {
        this.id = id;
    }

    static class Nested {
        private final StaticNestedOwnerDemo owner;

        Nested(StaticNestedOwnerDemo owner) {
            this.owner = java.util.Objects.requireNonNull(owner);
        }

        void print() {
            System.out.println("owner=" + owner.id);
        }
    }

    public static void main(String[] args) {
        StaticNestedOwnerDemo outer = new StaticNestedOwnerDemo("A");
        Nested nested = new Nested(outer);
        nested.print();
    }
}
~~~

Chạy:

~~~bash
javac StaticNestedOwnerDemo.java
java StaticNestedOwnerDemo
~~~

Output:

~~~text
owner=A
~~~

`Nested` được khai báo `static`, nên không có cú pháp `StaticNestedOwnerDemo.this` để lấy enclosing instance; trường `owner` là một quan hệ **được thiết kế tường minh**. Đây là lựa chọn phù hợp khi muốn truyền một outer-like object cụ thể mà không cần ngữ nghĩa non-static inner class.

## 10. Các quy tắc truy cập thành viên và che khuất tên

`Outer.this` cung cấp **tham chiếu**, nhưng không biến Java thành ngôn ngữ bỏ qua type checking hoặc các modifier.

### 10.1. Truy cập field và method trên outer object

~~~java
class Outer {
    private int count = 10;

    private int doubleCount() {
        return count * 2;
    }

    class Inner {
        int result() {
            return Outer.this.doubleCount();
        }
    }
}
~~~

Đây là lớp biên dịch hợp lệ. Inner class có thể gọi private method của enclosing class; bên trong `Outer.doubleCount()`, `this` (nếu được viết ra) là outer object.

Cũng có thể viết `Outer.this.count`. Việc chọn tên đầy đủ đặc biệt hữu ích khi có thành viên trùng tên.

### 10.2. Không phải lúc nào cũng bắt buộc viết `Outer.this`

Nếu bên trong `Inner` không có field/method/local che khuất một thành viên outer, Java có thể cho phép truy cập qua **tên đơn giản**:

~~~java
class Outer {
    String message = "hello";

    class Inner {
        void show() {
            System.out.println(message);
            System.out.println(Outer.this.message);
        }
    }
}
~~~

Hai dòng trên có cùng tác dụng trong ví dụ. Tuy nhiên, viết `Outer.this.message` đôi khi diễn đạt rõ **ý định phụ thuộc vào outer instance** và bảo vệ khả năng đọc hiểu khi class lớn lên.

Đừng lạm dụng qualified `this` nếu mã đơn giản và không có nhập nhằng; đặt tên field/method rõ ràng và thiết kế class hợp lý thường quan trọng hơn viết tiền tố dài ở mọi dòng.

### 10.3. Đọc và gán vào outer object phải tuân quy tắc field

Nếu `Outer.this.count` là field thông thường, inner method có thể thay đổi nó khi quyền truy cập cho phép. Nếu đó là field `final` đã khởi tạo, không được tùy tiện gán lại qua qualified `this`. Nếu nhiều luồng truy cập cùng field có thể thay đổi, `Outer.this` không tự tạo đồng bộ hóa/thread safety; vẫn phải xem Java Memory Model.

## 11. `Outer.this` và vòng đời object: nguy cơ giữ outer object lâu hơn dự kiến

Một **non-static inner object** có liên hệ với enclosing instance. Nếu inner object được lưu trong một cấu trúc sống lâu, nó có thể khiến outer object **tiếp tục reachable** lâu hơn mong muốn.

Ví dụ thiết kế minh họa:

~~~java
class Screen {
    private final byte[] buffer = new byte[1024 * 1024];

    class Listener {
        void onEvent() {
            System.out.println(Screen.this.buffer.length);
        }
    }

    Listener listener() {
        return new Listener();
    }
}
~~~

Nếu `Listener` được đăng ký vào một **global event bus** và không được hủy đăng ký, listener vẫn có quan hệ enclosing tới `Screen`, có thể góp phần giữ `Screen` và bộ nhớ đệm lâu hơn mong muốn. Đây là một dạng rủi ro **retention/memory leak do tham chiếu còn sống**, không phải vì có `Outer.this` là tự động rò rỉ.

Một số lựa chọn giảm rủi ro:

- Dùng **static nested class** khi không cần implicit outer instance, rồi truyền **chỉ những dữ liệu/dependency cần thiết**.
- Hủy đăng ký listener, đóng subscription hoặc quản lý lifecycle rõ ràng.
- Không lưu inner object sống lâu hơn outer nếu thiếu lý do; cân nhắc việc ai sở hữu ai.
- Nếu thật sự cần tham chiếu yếu, hiểu rõ `WeakReference` và hợp đồng lifecycle trước khi áp dụng; không phải phương thuốc chung cho mọi bài toán.

**Quan trọng:** hình dạng trường tổng hợp do compiler/JVM tạo ra để phục vụ inner class có thể khác nhau theo compiler và tối ưu hóa. Bạn nên suy luận ở **mức ngữ nghĩa enclosing instance**, không phụ thuộc một tên nội bộ như `this$0` trong bytecode.

## 12. Dùng `Outer.this` có giúp thực thi đa luồng an toàn không?

Không. `Outer.this` chỉ chọn **đúng object** để đọc/ghi; nó **không** cấp lock, không tạo atomicity hay happens-before.

Ví dụ trong inner method:

~~~java
Outer.this.count++;
~~~

Với một field `count` có thể thay đổi, phép `++` không được bảo đảm atomic khi nhiều luồng cùng cập nhật. Nếu đây là shared state đa luồng, cân nhắc đồng bộ hóa hoặc cấu trúc chuyên dụng như `AtomicInteger` tùy nhu cầu.

Ngược lại, inner object gắn với outer object riêng có thể giúp mô hình hóa state rõ ràng hơn nhưng không đủ để khẳng định “mỗi thread có bản sao dữ liệu riêng”; các luồng khác vẫn có thể cùng tham chiếu đến một outer object.

## 13. Phân biệt `Outer.this`, `Outer.class`, `Outer.staticMethod()` và `super`

| Cú pháp | Giá trị/ý nghĩa | Dùng khi |
| --- | --- | --- |
| `this` | Instance hiện tại của lớp chứa ngữ cảnh `this` | Instance method/constructor hoặc ngữ cảnh phù hợp |
| `Outer.this` | Qualified `this`: enclosing instance của `Outer` | Inner/local/anonymous context có enclosing `Outer` instance hợp lệ |
| `Outer.class` | Class literal: đối tượng `Class<Outer>` | Reflection và metadata kiểu |
| `Outer.staticMethod()` | Gọi static method trên kiểu `Outer` | Chức năng không cần receiver instance |
| `super.method()` | Truy cập phương thức trong nhánh superclass theo quy tắc Java | Quan hệ kế thừa |
| `outerVariable.method()` | Gọi method qua tham chiếu lưu trong một biến | Có biến reference, không nhất thiết là enclosing instance |

Một câu dễ nhớ: **`Outer.this` nói “đối tượng Outer bao ngoài của inner object này”**, không nói “lớp Outer” và cũng không nói “superclass”.

### 13.1. Có thể dùng tham chiếu trực tiếp thay `Outer.this` không?

Được, nếu bạn **có tham chiếu phù hợp**. Ví dụ một inner class có constructor nhận `Outer other` và lưu nó vào field `other`; `other.name` truy cập object đó, có thể khác enclosing instance. `Outer.this.name` luôn chỉ đến enclosing instance của inner object hiện hành. Hai cách viết có cùng giá trị chỉ khi `other` thực sự tham chiếu đúng object đó.

## 14. Lỗi phổ biến

| Tình huống hoặc lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `non-static variable this cannot be referenced from a static context` | Thử dùng `Outer.this` trong static context không có instance | Truyền `Outer` qua parameter/field hoặc chuyển code đến instance context phù hợp |
| Dùng `Outer.this` bên trong `static class Nested` | Static nested class không có enclosing Outer instance tự động | Dùng `owner` field được truyền vào, hoặc non-static inner class nếu thật sự cần |
| `new Outer.Inner()` từ bên ngoài | Cú pháp sai cho non-static member inner class cần enclosing instance | Tạo `Outer outer`, rồi `outer.new Inner()` |
| Đọc `this.name` mà muốn outer field | `this` bên trong `Inner` trỏ inner instance | Dùng `Outer.this.name` |
| Gọi `super.name` mà mong outer field | `super` dùng quan hệ kế thừa, không phải lexical enclosing | Dùng `Outer.this.name` |
| Tạo `Inner` với `outerA`, rồi gán biến `outerA=outerB` và kỳ vọng liên kết đổi | Enclosing instance được gắn khi tạo inner | Tạo inner mới từ `outerB` nếu muốn liên kết với B |
| Dùng `Outer.this` ở một lớp không được bao ngoài bởi Outer về mặt ngữ nghĩa | Qualified `this` cần enclosing instance phù hợp | Truyền tham chiếu Outer trực tiếp |
| Coi `Outer.this` là constructor | Qualified `this` chỉ là biểu thức tham chiếu | Tạo object qua `new Outer(...)` khi thật sự cần object mới |
| Truy cập field `final` rồi cố gán lại | Qualified `this` không bỏ qua quy tắc `final` | Chỉ đọc hoặc thiết kế trạng thái có thể thay đổi hợp lệ |
| Tưởng `Outer.this` tự bảo đảm đồng bộ hóa | Nó chỉ chọn object, không bảo đảm atomicity | Dùng concurrency primitives hoặc synchronization phù hợp |
| Listener inner class tồn tại lâu và giữ outer | Enclosing instance liên kết với inner object, có thể gây retention | Quản lý subscription hoặc chọn static nested class |
| Nhầm `this` của lambda với anonymous class | Lambda có lexical `this`, anonymous class có own `this` | Xác định loại lớp/biểu thức và vị trí khai báo |

**Lưu ý về lỗi cụ thể:** Thông điệp của compiler có thể khác nhau theo JDK và ngữ cảnh. Hãy dựa trên **quy tắc lexical enclosing instance và static context** chứ không chờ một chuỗi lỗi chính xác duy nhất.

## 15. Quy trình xác định `this` khi đọc code

Khi gặp một biểu thức như `Outer.this.field`:

1. **Xác định lớp đang chứa đoạn mã**: top-level class, member inner class, static nested class, local class, anonymous class hay lambda?
2. **Tìm lexical enclosing class tên `Outer`** phù hợp. Lồng nhau về tên không tự bảo đảm có enclosing instance nếu gặp ranh giới static.
3. **Kiểm tra ngữ cảnh hiện tại** có cho phép truy cập instance hay không. Static method/static initializer thường không có `this` tương ứng.
4. **Xác định inner object cụ thể** và enclosing instance đã được gắn với nó ở thời điểm tạo object, nếu có.
5. **Phân giải field/method**: `this.field` ở lớp hiện tại, `Outer.this.field` ở outer; nếu field cùng tên, qualified `this` làm rõ ý định.
6. **Kiểm tra quyền truy cập, type checking và mutability** của field/method được dùng.
7. **Khi code liên quan lifecycle/concurrency**, xem inner object có giữ outer sống quá lâu hoặc chia sẻ mutable state không.

Nếu không có enclosing instance phù hợp, **đừng cố ép cú pháp `Outer.this`**. Hãy truyền một reference hợp lệ, đổi cách tổ chức lớp, hoặc dùng static nested class tùy mục tiêu.

## 16. Bài tập vận dụng có lời giải

### Bài 1. Hai field cùng tên

~~~java
class Host {
    String id = "host";

    class Guest {
        String id = "guest";

        String values() {
            return this.id + "/" + Host.this.id;
        }
    }
}
~~~

Đây là đoạn lớp hợp lệ. Nếu viết `Host h = new Host(); Host.Guest g = h.new Guest();` rồi gọi `g.values()`, kết quả là **`guest/host`**. `this.id` là `Guest.id`, còn `Host.this.id` là `Host.id`.

### Bài 2. Gán lại biến outer

Một biến `Outer a` ban đầu trỏ tới object A; sau `Outer.Inner child = a.new Inner()`, gán `a = objectB`. Khi `child` gọi `Outer.this`, nó trỏ A hay B?  
**Đáp án:** A. Inner object đã gắn với A khi tạo; biến local `a` bị gán lại không thay đổi enclosing instance.

### Bài 3. Local class trong instance method

Một local class `Task` trong instance method `run()` của `Outer` có thể dùng `Outer.this` không?  
**Đáp án:** Có, nếu được khai báo trong ngữ cảnh có enclosing `Outer` instance tương ứng. `this` trong `Task` là object `Task`, còn `Outer.this` là enclosing outer object.

### Bài 4. Static nested class

Trong `static class Nested` nằm trong `Outer`, có thể viết `Outer.this.name` không?  
**Đáp án:** Không, vì `Nested` không mang enclosing instance `Outer`. Nếu cần, hãy truyền `Outer` vào và dùng một field như `owner.name`.

### Bài 5. Anonymous class và lambda

Trong instance method của `Outer`, nếu cùng tạo anonymous `Runnable` và lambda `Runnable`, `this` trong mỗi thân biểu diễn điều gì?  
**Đáp án:** Trong anonymous class, `this` trỏ instance anonymous; trong lambda, `this` giữ lexical meaning của ngữ cảnh enclosing, thường trỏ object `Outer`.

### Bài 6. Hai cấp bao ngoài

Trong `Outer.Middle.Inner` với cả ba là các lớp lồng không `static`, hãy viết biểu thức truy cập `value` của mỗi cấp.  
**Đáp án:** `this.value` cho `Inner`, `Middle.this.value` cho `Middle`, và `Outer.this.value` cho `Outer` (nếu các tên kiểu và quyền truy cập đúng với code cụ thể).

### Bài 7. Kế thừa so với bao ngoài

`Inner extends Base` được khai báo bên trong `Outer`. `super.value` có phải là `Outer.this.value` không?  
**Đáp án:** Không. `super.value` gắn với superclass `Base`; `Outer.this.value` lấy field trên enclosing `Outer` instance.

### Bài 8. Quyền truy cập

Field `private int secret` nằm ở `Outer`; inner member class có đọc qua `Outer.this.secret` không?  
**Đáp án:** Có trong ngữ cảnh lồng hợp lệ theo quy tắc Java; inner/outer classes trong quan hệ lồng có quyền truy cập tới private members của nhau. Điều này không có nghĩa mọi class bên ngoài cũng truy cập được.

### Bài 9. Thread safety

Nếu nhiều thread gọi `Inner.increment()`, trong đó code viết `Outer.this.counter++`, có an toàn về race không?  
**Đáp án:** Không có bảo đảm chỉ nhờ qualified `this`. Phép `++` không atomic theo yêu cầu đa luồng; cần thiết kế đồng bộ hóa/atomicity phù hợp.

### Bài 10. `Outer.this` và `Outer.class`

Hai biểu thức này cùng là một giá trị tham chiếu tới outer object không?  
**Đáp án:** Không. `Outer.this` là outer instance reference trong ngữ cảnh hợp lệ; `Outer.class` là class literal, có kiểu `Class<Outer>`.

## Tài liệu tham khảo

- Java Language Specification, [§15.8.4 — Qualified `this`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.8.4): quy tắc qualified `this` expression.
- Java Language Specification, [§8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.3): quan hệ inner classes/enclosing instances.
- Java Language Specification, [§15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9): cú pháp tạo class instance và mối liên hệ đến enclosing instance.
- Java Language Specification, [§15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.27): lexical scoping và `this` trong lambda.

## Ghi nhớ

Trong **non-static inner class**, `this` chỉ **inner object hiện tại**, còn **`Outer.this`** chỉ **outer object bao ngoài** gắn với inner object ấy. Qualified `this` đặc biệt hữu ích khi tên field/method bị che khuất, hoặc khi một method cần gọi rõ logic của enclosing object. Inner object được tạo với một enclosing instance cụ thể, ví dụ `outer.new Inner()`; gán lại biến `outer` không thay đổi liên kết đó.

**Không có `Outer.this` tự động trong static nested class hoặc ngữ cảnh static không có enclosing instance tương ứng.** Khi cần dùng một outer object trong những nơi ấy, hãy truyền tham chiếu qua parameter/field. Cuối cùng, `Outer.this` chỉ là cách chọn đúng object: nó không tạo instance mới, không bypass `final`, không tự đồng bộ hóa và có thể góp phần giữ outer object còn reachable nếu inner object sống lâu.
