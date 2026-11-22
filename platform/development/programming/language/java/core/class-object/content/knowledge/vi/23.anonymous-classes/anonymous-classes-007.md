# So sánh lớp vô danh với lambda: phạm vi sử dụng và ý nghĩa của `this` trong Java 17

**Anonymous class (lớp vô danh)** và **lambda expression** đều cho phép đặt một hành vi ngay tại nơi chương trình cần dùng, ví dụ callback `Runnable`, `Comparator` hoặc một chiến lược xử lý dữ liệu. Tuy nhiên, chúng **không phải hai cách viết hoàn toàn tương đương của cùng một cơ chế**.

- `new Runnable() { ... }` là **biểu thức khai báo và khởi tạo một lớp vô danh** thực sự. Trong instance method của lớp vô danh, **`this` trỏ tới đối tượng vô danh**.
- `() -> ...` là **lambda expression**, dùng khi có một **functional interface làm target type**. Lambda **không tạo một scope mới cho `this`**: `this` giữ nghĩa của `this` ở ngữ cảnh từ vựng (lexical enclosing context) nơi lambda được viết.
- Cả hai có thể capture local variables hoặc parameters **`final`/effectively final**, nhưng cách xử lý tên, khai báo biến mới, overload, methods, state và `super` có những khác biệt thực tế.

Bài thuộc **Java core – class-object**, nhóm **Lớp vô danh**. Mục tiêu trực tiếp là **so sánh phạm vi sử dụng và `this`**, đặt trong kiến thức Java **17+**. Mỗi chương trình hoàn chỉnh được trình bày trong một tệp riêng và có stdout xác định; các đoạn cố ý lỗi compile-time được đánh dấu rõ.

## 1. Mục tiêu học tập

Sau bài, bạn cần làm được những việc sau:

1. Nhận diện `new Interface() { ... }` và `() -> ...` là hai loại biểu thức khác nhau.
2. Chọn được lambda cho **functional interface**; nhận ra khi nào anonymous class còn cần thiết.
3. Giải thích `this` trong **anonymous method**, **lambda trong instance method**, và **lambda trong static method**.
4. Phân biệt `Outer.this`, `this.field`, tên field đơn giản và biến local được capture.
5. Dự đoán tác động của **shadowing**: anonymous class mở scope lớp mới, còn lambda dùng cùng lexical scope gần với enclosing context.
6. So sánh state riêng trong anonymous object với state nằm trong một đối tượng bên ngoài được lambda tham chiếu.
7. Hiểu cả hai đều yêu cầu local variables/parameters được capture là final hoặc effectively final.
8. Hiểu return trong lambda hay method anonymous không tự kết thúc method bao ngoài.
9. Phân biệt target typing, overload, `@Override`, checked exceptions và khả năng override superclass methods.
10. Phân tích chi phí bảo trì, lifetime, concurrency và những hiểu lầm về runtime identity.

## 2. Hai cú pháp đặt cạnh nhau

Anonymous class:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("anonymous");
    }
};
~~~

Lambda:

~~~java
Runnable task = () -> System.out.println("lambda");
~~~

Đây là **hai snippet hợp lệ bên trong một method**; không ghép hai khai báo có cùng tên `task` vào cùng block.

Cả hai có thể gán cho `Runnable`, vì Runnable có đúng một abstract method `void run()` theo mục đích functional interface. Nhưng những bước khái niệm khác nhau:

| Câu hỏi | Anonymous class | Lambda |
| --- | --- | --- |
| Bạn viết gì? | Một class body không có tên nguồn, kèm `new` | Một biểu thức cung cấp function body cho SAM |
| Kiểu đích | Interface hoặc class có thể làm supertype hợp lệ | Functional interface |
| Cần một class body mới? | Có | Không viết class body |
| Có khai báo instance field riêng? | Có | Không |
| Có cài nhiều abstract methods cùng lúc? | Có, nếu cài đủ | Không |
| `this` trong thân | Anonymous instance | `this` của lexical enclosing context |
| `super` trong thân | Superclass của anonymous instance khi hợp lệ | Lexical enclosing context khi hợp lệ |
| Dùng `@Override` cho method? | Có | Không có method declaration để gắn annotation này |
| Capture local variables | Final/effectively final | Final/effectively final |
| Class extends một abstract class? | Có thể, nếu superclass và constructor hợp lệ | Không |
| Biểu thức ngắn cho một callback | Thường dài hơn | Thường ngắn hơn |
| Tự động chạy callback khi tạo? | Không | Không |

**Không phải mọi interface đều là functional interface.** Lambda chỉ hợp lệ khi target type có **một abstract method về mặt chức năng** (sau các quy tắc của Java về methods từ Object, generic signatures, v.v.). Annotation `@FunctionalInterface` giúp compiler kiểm tra hợp đồng, nhưng **không bắt buộc** để một interface đủ điều kiện làm lambda target.

## 3. Chương trình 1 — cùng chức năng, hai cách viết

Tệp **`AnonymousLambdaBasicsDemo.java`**:

~~~java
public class AnonymousLambdaBasicsDemo {
    static void execute(String label, Runnable action) {
        System.out.println("begin=" + label);
        action.run();
    }

    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("hello from anonymous");
            }
        };

        Runnable lambda = () ->
                System.out.println("hello from lambda");

        execute("A", anonymous);
        execute("L", lambda);
        System.out.println("anonymous class="
                + anonymous.getClass().isAnonymousClass());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousLambdaBasicsDemo.java
java AnonymousLambdaBasicsDemo
~~~

**Stdout:**

~~~text
begin=A
hello from anonymous
begin=L
hello from lambda
anonymous class=true
~~~

Hai objects được cung cấp dưới interface `Runnable`. Method `execute` không cần biết cách implementation được viết: nó chỉ gọi `run()` theo contract của Runnable.

`anonymous.getClass().isAnonymousClass()` trả true vì biểu thức `new Runnable() { ... }` thực sự khai báo một anonymous class. **Đừng suy ngược** rằng lambda buộc phải có cùng một hình dạng runtime class với anonymous class. Java đặc tả lambda theo ngữ nghĩa, không hứa một binary class name hay một cơ chế triển khai cố định để ứng dụng phụ thuộc.

## 4. Phạm vi sử dụng: lambda cần functional interface, anonymous class linh hoạt hơn

Một interface có **hai abstract methods**:

~~~java
interface EventSink {
    void onEvent(String value);
    void onComplete();
}
~~~

Bạn **có thể** dùng anonymous class:

~~~java
EventSink sink = new EventSink() {
    @Override
    public void onEvent(String value) {
        System.out.println("event=" + value);
    }

    @Override
    public void onComplete() {
        System.out.println("complete");
    }
};
~~~

Hai đoạn trên là **snippets hợp lệ** trong các vị trí khai báo thích hợp.

Nhưng không thể viết một lambda `value -> System.out.println(value)` rồi gán cho EventSink, vì interface này **không phải functional interface**. Lambda không chứa nhiều method declarations để implement hai abstract methods.

Mặt khác, với functional interface như `Runnable`, `Supplier<T>`, `Predicate<T>`, `Comparator<T>`, cả hai cách thường đều có thể dùng; tiêu chí chọn tiếp theo là nhu cầu **state**, **`this`**, **nhiều methods**, **nhiều dòng logic** và readability.

## 5. Chương trình 2 — interface hai abstract methods

Tệp **`MultiMethodInterfaceDemo.java`**:

~~~java
interface EventSink {
    void onEvent(String value);
    void onComplete();
}

public class MultiMethodInterfaceDemo {
    static void publish(EventSink sink) {
        sink.onEvent("A");
        sink.onEvent("B");
        sink.onComplete();
    }

    public static void main(String[] args) {
        EventSink sink = new EventSink() {
            private int count;

            @Override
            public void onEvent(String value) {
                count++;
                System.out.println(count + ":" + value);
            }

            @Override
            public void onComplete() {
                System.out.println("total=" + count);
            }
        };

        publish(sink);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MultiMethodInterfaceDemo.java
java MultiMethodInterfaceDemo
~~~

**Stdout:**

~~~text
1:A
2:B
total=2
~~~

Anonymous class tự cài hai methods và giữ instance field `count`. **Không thể** thay phần `new EventSink() { ... }` trong chương trình này bằng một lambda duy nhất vì `EventSink` có hai abstract methods.

Nếu cần lambda, phải **thiết kế lại API** để nhận một functional interface khác; không có cú pháp lambda nào tự tạo hai body method độc lập ở một lần viết.

## 6. Anonymous class có thể kế thừa class; lambda không thể

Khi một API nhận hoặc mong đợi một subclass của abstract class, anonymous class là lựa chọn trực tiếp:

~~~java
abstract class Formatter {
    private final String prefix;

    Formatter(String prefix) {
        this.prefix = prefix;
    }

    protected String prefix() {
        return prefix;
    }

    abstract String format(String input);
}
~~~

Có thể tạo:

~~~java
Formatter formatter = new Formatter("OUT:") {
    @Override
    String format(String input) {
        return prefix() + input;
    }
};
~~~

Đây là **snippets hợp lệ** nếu cùng phạm vi. Anonymous class kế thừa Formatter, gọi constructor `Formatter(String)`, rồi override abstract method.

Một lambda **không thể dùng target type là abstract class Formatter**. Lambda cần functional interface, không phải “class có đúng một abstract method”. Đây là giới hạn **loại kiểu**, không phải chỉ do khác cú pháp.

`final class` cũng không thể bị anonymous subclass kế thừa, kể cả khi class body rỗng.

## 7. Chương trình 3 — anonymous subclass dùng `super`

Tệp **`AnonymousSubclassDemo.java`**:

~~~java
class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    String text() {
        return "Hello " + name;
    }
}

public class AnonymousSubclassDemo {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String text() {
                return super.text() + "!";
            }
        };

        System.out.println(greeting.text());
        System.out.println("superclass="
                + greeting.getClass()
                        .getSuperclass().getSimpleName());
        System.out.println("anonymous="
                + greeting.getClass().isAnonymousClass());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousSubclassDemo.java
java AnonymousSubclassDemo
~~~

**Stdout:**

~~~text
Hello An!
superclass=Greeting
anonymous=true
~~~

`super.text()` trong anonymous subclass gọi method của superclass `Greeting`. **Đừng áp dụng cùng giải thích** cho `super` trong lambda: lambda không được dùng để tạo subclass của Greeting.

Đặt code override lớn thành class có tên nếu nó được dùng lại, cần kiểm thử sâu, hoặc có state/invariants quan trọng.

## 8. Trọng tâm: `this` là đối tượng nào?

Trong một **instance method** của một class `Outer`:

~~~java
class Outer {
    private final String name = "outer";

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this.getClass()
                        .isAnonymousClass());
                System.out.println(Outer.this.name);
            }
        };
    }

    Runnable lambda() {
        return () -> {
            System.out.println(
                    this.getClass().getSimpleName());
            System.out.println(this.name);
        };
    }
}
~~~

Đây là class minh họa hợp lệ, không có main.

- `this` trong **anonymous `run()`** là object thuộc lớp vô danh. Vì object ấy triển khai Runnable, `this` **không phải Outer**.
- `Outer.this` trong anonymous `run()` chỉ đúng enclosing Outer object nếu biểu thức được tạo từ instance context phù hợp.
- `this` trong **lambda body** có nghĩa như `this` tại chỗ viết lambda, tức là **Outer instance** trong hai instance methods của ví dụ.
- Lambda không có một `this` mới để diễn đạt “lambda object đang thực thi”.

Đây là khác biệt về **lexical scope**. Nó không liên quan việc anonymous class có được dùng làm callback hay không: cả hai đều có thể implement Runnable nhưng `this` chỉ những objects khác nhau.

## 9. Chương trình 4 — kiểm tra `this` không cần suy đoán

Tệp **`ThisBindingDemo.java`**:

~~~java
final class Controller {
    private final String name;

    Controller(String name) {
        this.name = name;
    }

    Runnable anonymousTask() {
        return new Runnable() {
            @Override
            public void run() {
                Object current = this;
                System.out.println("anonymous class="
                        + current.getClass().isAnonymousClass());
                System.out.println("anonymous outer="
                        + Controller.this.name);
            }
        };
    }

    Runnable lambdaTask() {
        return () -> {
            System.out.println("lambda this class="
                    + this.getClass().getSimpleName());
            System.out.println("lambda this name=" + this.name);
        };
    }
}

public class ThisBindingDemo {
    public static void main(String[] args) {
        Controller controller = new Controller("C1");
        controller.anonymousTask().run();
        controller.lambdaTask().run();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ThisBindingDemo.java
java ThisBindingDemo
~~~

**Stdout:**

~~~text
anonymous class=true
anonymous outer=C1
lambda this class=Controller
lambda this name=C1
~~~

Trong lambda, `this.getClass()` là class của **Controller**, không phải class của một “lambda closure” nào đó. Trong anonymous class, `Object current = this` trỏ tới **anonymous object**, nên `isAnonymousClass()` true.

**Lưu ý:** dùng `Object current` nếu muốn phân tích kiểu runtime rộng hơn, tránh các phép `instanceof` trực tiếp giữa những lớp tĩnh không thể có subtype chung. Ở đây dùng `Class.isAnonymousClass()` cho mục đích quan sát dễ xác định.

## 10. Trong `static` method: anonymous class có `this`, lambda không tự có enclosing `this`

Trong static method không có enclosing instance `this` của class chứa method.

~~~java
class Utility {
    static Runnable makeAnonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this.getClass()
                        .isAnonymousClass());
            }
        };
    }

    static Runnable makeLambda() {
        return () -> System.out.println("hello");
    }
}
~~~

Đây là class minh họa hợp lệ. Anonymous `run()` là **instance method của anonymous object**, do đó `this` trong method đó hợp lệ. Nhưng trong lambda được viết trong static method, **không có enclosing `Utility.this`** để dùng.

Đoạn **cố ý không biên dịch** nếu đặt trong static method:

~~~java
// Runnable invalid = () -> System.out.println(this);
~~~

Lỗi không phải vì Runnable hay lambda “không hỗ trợ this bao giờ”. Lỗi vì lambda **kế thừa lexical context**, mà static method **không có instance this**.

## 11. Chương trình 5 — so sánh trong static context

Tệp **`StaticContextThisDemo.java`**:

~~~java
public class StaticContextThisDemo {
    static Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous self="
                        + this.getClass().isAnonymousClass());
            }
        };
    }

    static Runnable lambda() {
        return () -> System.out.println("lambda from static");
    }

    public static void main(String[] args) {
        anonymous().run();
        lambda().run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StaticContextThisDemo.java
java StaticContextThisDemo
~~~

**Stdout:**

~~~text
anonymous self=true
lambda from static
~~~

`static` là một tính chất của **method đang chứa biểu thức**, không làm anonymous instance method thành static. Còn lambda không tự sinh `this` mới để lập trình viên tham chiếu.

Nếu lambda cần một object cụ thể, truyền nó qua tham số hoặc capture một reference được khai báo hợp lệ, thay vì coi `this` là object lambda.

## 12. `Outer.this` trong anonymous class và trong lambda

Một anonymous class trong instance context có thể dùng `Outer.this` để **chỉ đích danh enclosing object**. Một lambda trong cùng instance context cũng có thể dùng `Outer.this` khi qualified this đó hợp lệ về mặt lexical enclosing context; thông thường `this` đã trỏ chính Outer rồi nên viết `this.field` đủ rõ.

Không phải bất kỳ lambda nào cũng dùng được `Outer.this`. Nếu lambda được viết trong static method không có enclosing instance Outer, `Outer.this` vẫn bất hợp lệ.

**Hãy phân biệt tên và receiver:**

| Biểu thức | Trong anonymous Runnable của Outer | Trong lambda viết ở instance method Outer |
| --- | --- | --- |
| `this` | Anonymous object | Outer object |
| `Outer.this` | Outer object nếu enclosing context hợp lệ | Outer object nếu qualified this hợp lệ |
| `this.toString()` | ToString của anonymous object | ToString của Outer object |
| `this.field` | Field của anonymous object nếu có | Field của Outer object nếu có |
| `Outer.this.field` | Field của Outer object | Field của Outer object |

Quan trọng là **object thực sự được chọn**, không phải đơn thuần tên field `private` hay `public`. Java có quy tắc private access cho các khai báo lồng nhau, nhưng **quyền truy cập** không tạo ra receiver khi đang ở static context.

## 13. Chương trình 6 — Outer field và field trùng tên

Tệp **`FieldShadowingDemo.java`**:

~~~java
final class Panel {
    private final String label = "outer";

    Runnable anonymous() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous this=" + this.label);
                System.out.println("anonymous outer="
                        + Panel.this.label);
            }
        };
    }

    Runnable lambda() {
        return () -> {
            System.out.println("lambda this=" + this.label);
            System.out.println("lambda outer="
                    + Panel.this.label);
        };
    }
}

public class FieldShadowingDemo {
    public static void main(String[] args) {
        Panel panel = new Panel();
        panel.anonymous().run();
        panel.lambda().run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

**Stdout:**

~~~text
anonymous this=anonymous
anonymous outer=outer
lambda this=outer
lambda outer=outer
~~~

Anonymous class tạo một **instance scope riêng** chứa field `label="anonymous"`. Lambda **không có class body khai báo field `label` của riêng nó**; `this.label` là field Outer Panel.

Nếu một method bao ngoài có biến local cũng tên `label`, name lookup có thể chọn local variable khi dùng tên đơn giản. Lúc ấy `Panel.this.label` và `this.label` giúp chỉ rõ field theo object.

## 14. Shadowing local variables: phạm vi của lambda chặt hơn

Lambda **không mở một lexical scope độc lập như class declaration để bạn tái khai báo một tên local đang có trong scope bao**.

Đoạn **cố ý không biên dịch**:

~~~java
void invalid() {
    int value = 10;

    Runnable lambda = () -> {
        // int value = 20; // Không được khai báo trùng local value.
        System.out.println(value);
    };
}
~~~

Method minh họa trên **biên dịch nếu giữ dòng trùng tên ở dạng comment**; bỏ comment làm phát sinh lỗi khai báo trùng tên. `value` ở ngoài vẫn trong scope của lambda body.

Anonymous class thì lại có **scope của một class khác**. Nó có thể khai báo instance field hoặc parameter có tên trùng với local value ngoài theo các quy tắc lexical scopes của nested classes:

~~~java
void allowed() {
    int value = 10;

    Runnable anonymous = new Runnable() {
        private int value = 20;

        @Override
        public void run() {
            System.out.println(this.value);
        }
    };

    anonymous.run();
}
~~~

Đây là method minh họa hợp lệ khi đặt trong class. `this.value` ở đây là field anonymous class, không phải local `value=10`. Việc redeclare field có thể khiến code khó đọc; không nên dùng trùng tên nếu không có lý do.

**Tóm lại:** lambda dùng scope từ vựng gần với enclosing context; anonymous class có thêm **class scope mới** chứa fields/method parameters riêng. Đây là khác biệt nhìn rõ nhất khi compiler báo lỗi “variable ... is already defined”.

## 15. Chương trình 7 — scope và shadowing khác nhau

Tệp **`LexicalScopeDemo.java`**:

~~~java
public class LexicalScopeDemo {
    public static void main(String[] args) {
        int value = 10;

        Runnable anonymous = new Runnable() {
            private int value = 20;

            @Override
            public void run() {
                int local = 30;
                System.out.println("anonymous field="
                        + this.value);
                System.out.println("anonymous local=" + local);
            }
        };

        Runnable lambda = () -> {
            int additional = 40;
            System.out.println("lambda captured=" + value);
            System.out.println("lambda local=" + additional);
        };

        anonymous.run();
        lambda.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LexicalScopeDemo.java
java LexicalScopeDemo
~~~

**Stdout:**

~~~text
anonymous field=20
anonymous local=30
lambda captured=10
lambda local=40
~~~

Chương trình không lạm dụng tên trùng ở local variables trong lambda. `additional` là tên mới nên hoàn toàn hợp lệ; `value` được capture và không bị gán lại.

Muốn thấy lỗi thật, thử thêm **một dòng không chạy** `int value = 99;` vào lambda body trong bản sao thí nghiệm; compiler sẽ từ chối khai báo trùng. Không cần thay đổi runtime hoặc cố gán biến `value` bằng lệnh khác để kiểm tra sự khác biệt về scope.

## 16. Cả hai capture biến local `final` hoặc `effectively final`

Dù khác scope và `this`, anonymous class và lambda cùng bị ràng buộc khi đọc **local variables hoặc formal parameters** từ phạm vi chứa:

- Biến được tham chiếu phải có scope hợp lệ và **definitely assigned**.
- Với local variable/parameter, biến phải **final hoặc effectively final** theo JLS.
- **Gán lại** biến sau initializer, `++`, `--`, compound assignment `+=`… làm mất điều kiện effectively final trong các tình huống thông thường.
- Không bắt buộc ghi keyword `final` nếu cách gán đã đáp ứng effectively final.
- Cả hai có thể được trả từ method rồi dùng captured values về sau.

Cặp snippets minh họa:

~~~java
int number = 5;

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(number);
    }
};

Runnable lambda = () -> System.out.println(number);
~~~

Đây là code hợp lệ khi đặt trong method mà `number` không bị gán lại.

Nếu thêm `number++;` trong method, **cả hai** expressions đều không được capture `number`. Đây là **lỗi compile-time**, không phải lỗi chỉ xảy ra khi callback chạy.

## 17. Chương trình 8 — mỗi lần gọi factory capture giá trị riêng

Tệp **`CaptureBothFormsDemo.java`**:

~~~java
public class CaptureBothFormsDemo {
    static Runnable anonymous(String name) {
        int repeats = 2;

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < repeats; i++) {
                    System.out.println("A:" + name + ":" + i);
                }
            }
        };
    }

    static Runnable lambda(String name) {
        int repeats = 2;
        return () -> {
            for (int i = 0; i < repeats; i++) {
                System.out.println("L:" + name + ":" + i);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = anonymous("An");
        Runnable second = lambda("Binh");

        first.run();
        second.run();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CaptureBothFormsDemo.java
java CaptureBothFormsDemo
~~~

**Stdout:**

~~~text
A:An:0
A:An:1
L:Binh:0
L:Binh:1
~~~

Tham số `name` và biến local `repeats` của từng method không bị gán lại nên đều effectively final. Objects/actions đã được tạo có thể chạy sau khi `anonymous()` và `lambda()` trả về.

**Đừng gộp** hai biến `repeats` của hai invocations thành một biến static dùng chung: mỗi lần gọi method có một nguồn giá trị độc lập, còn biểu thức capture tuân theo những giá trị của lần gọi ấy.

## 18. Capture reference không đồng nghĩa snapshot đối tượng

Nếu một local variable là `StringBuilder`, `List` hay array, việc biến ấy effectively final **chỉ ngăn việc gán lại reference**. Nó không cấm method khác sửa object đang được reference trỏ tới.

~~~java
StringBuilder text = new StringBuilder("A");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(text);
    }
};

Runnable lambda = () -> System.out.println(text);
text.append("B");
~~~

Đây là snippet hợp lệ trong method. Cả hai callbacks sẽ thấy **AB** nếu chạy sau `append`, vì chúng giữ reference tới cùng mutable StringBuilder.

Nếu cần snapshot giá trị tại thời điểm tạo, viết `String frozen = text.toString();` rồi capture `frozen`, không capture builder mutable.

Nếu dữ liệu được share giữa threads, final/effectively final **không tự bảo đảm visibility hay atomicity của các writes trên object mutable**.

## 19. Chương trình 9 — hai forms cùng nhìn mutable object

Tệp **`MutableCaptureComparisonDemo.java`**:

~~~java
public class MutableCaptureComparisonDemo {
    public static void main(String[] args) {
        StringBuilder shared = new StringBuilder("A");

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + shared);
            }
        };

        Runnable lambda =
                () -> System.out.println("lambda=" + shared);

        anonymous.run();
        lambda.run();

        shared.append("B");
        anonymous.run();
        lambda.run();

        String snapshot = shared.toString();
        Runnable frozen =
                () -> System.out.println("frozen=" + snapshot);
        shared.append("C");
        frozen.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MutableCaptureComparisonDemo.java
java MutableCaptureComparisonDemo
~~~

**Stdout:**

~~~text
anonymous=A
lambda=A
anonymous=AB
lambda=AB
frozen=AB
~~~

Sự khác nhau giữa anonymous/lambda về `this` **không khiến biến shared biến thành dữ liệu bất biến**. Hai callbacks cùng quan sát StringBuilder theo các lần `append`.

`frozen` capture `String` độc lập với những thay đổi tiếp theo của builder; nó tiếp tục in AB, không in ABC.

## 20. State riêng của anonymous object và state ở ngoài lambda

Anonymous class có thể **tự khai báo instance field** trong body:

~~~java
java.util.function.IntSupplier supplier =
        new java.util.function.IntSupplier() {
            private int count;

            @Override
            public int getAsInt() {
                return ++count;
            }
        };
~~~

Đây là snippet hợp lệ trong method. `count` là **field của anonymous object**, không bị quy tắc capture local effectively final áp vào.

Lambda `() -> ++count` không có một `count` riêng được khai báo trong class body. Nếu `count` là **local variable** bao ngoài, việc tăng nó khiến compiler từ chối capture. Nhưng lambda vẫn có thể sử dụng state ở một **object được capture**, một **field của enclosing object**, hoặc một **holder** được thiết kế tường minh.

Một ví dụ thay thế được kiểm soát là `AtomicInteger` hoặc một class `Counter` có methods rõ ràng. Đừng dùng `int[] cell={0}` để “lách” final ở code đa luồng mà không hiểu thread safety.

## 21. Chương trình 10 — anonymous có field, lambda dùng holder rõ ràng

Tệp **`StateOwnershipDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntSupplier;

public class StateOwnershipDemo {
    static IntSupplier anonymous() {
        return new IntSupplier() {
            private int count;

            @Override
            public int getAsInt() {
                return ++count;
            }
        };
    }

    static IntSupplier lambda() {
        AtomicInteger counter = new AtomicInteger();
        return () -> counter.incrementAndGet();
    }

    public static void main(String[] args) {
        IntSupplier a = anonymous();
        IntSupplier b = lambda();

        System.out.println("anonymous=" + a.getAsInt());
        System.out.println("anonymous=" + a.getAsInt());
        System.out.println("lambda=" + b.getAsInt());
        System.out.println("lambda=" + b.getAsInt());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StateOwnershipDemo.java
java StateOwnershipDemo
~~~

**Stdout:**

~~~text
anonymous=1
anonymous=2
lambda=1
lambda=2
~~~

Trong anonymous, `count` là private **instance field** của anonymous object. Trong lambda, `counter` là một local variable effectively final trỏ tới **AtomicInteger object**; method `incrementAndGet()` thay đổi state của AtomicInteger chứ không gán lại reference counter.

Đây là **hai cách quản lý state khác nhau** cho ra giá trị tương tự, không chứng minh lambda “không có state”. Nó chỉ không có class body để lập trình viên khai báo fields/methods như với anonymous class.

## 22. Trong vòng lặp: cùng quy tắc snapshot chỉ số

Cả hai không được capture trực tiếp basic-for index `i` khi `i++` làm nó không effectively final:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH nếu bỏ comment:
for (int i = 0; i < 3; i++) {
    // Runnable invalid = () -> System.out.println(i);
}
~~~

Anonymous class cũng bị cùng hạn chế.

Cách đúng:

~~~java
for (int i = 0; i < 3; i++) {
    int index = i;

    Runnable anonymous = new Runnable() {
        @Override
        public void run() {
            System.out.println("A:" + index);
        }
    };

    Runnable lambda = () -> System.out.println("L:" + index);
    anonymous.run();
    lambda.run();
}
~~~

Đây là snippet hợp lệ trong method. Mỗi iteration có biến `index` được gán một lần trong body và không bị gán lại, vì thế capture hợp lệ.

**Enhanced for** như `for (String word : words)` cũng thường cho phép capture `word` nếu code không gán lại biến ấy. Không được suy rằng mọi loop variable đều không effectively final; phải nhìn đúng loại vòng lặp và cách variable được gán.

## 23. Chương trình 11 — hai callbacks giữ từng index

Tệp **`LoopCaptureComparisonDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureComparisonDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 2; i++) {
            int index = i;

            actions.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("anonymous=" + index);
                }
            });

            actions.add(() ->
                    System.out.println("lambda=" + index));
        }

        System.out.println("actions=" + actions.size());
        for (Runnable action : actions) {
            action.run();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LoopCaptureComparisonDemo.java
java LoopCaptureComparisonDemo
~~~

**Stdout:**

~~~text
actions=4
anonymous=0
lambda=0
anonymous=1
lambda=1
~~~

Đã tạo bốn callbacks rồi mới thực thi. Mỗi cặp anonymous/lambda capture cùng index của iteration tương ứng. **Hai cơ chế đều không tự tham chiếu “giá trị cuối của i sau vòng lặp”.**

## 24. `return` trong lambda và anonymous method

Một lambda có body block và target type trả kết quả có thể viết `return` để trả **giá trị của lần thực thi lambda body**:

~~~java
java.util.function.IntUnaryOperator twice = value -> {
    return value * 2;
};
~~~

Trong anonymous class, `return` trả kết quả từ **instance method được override**:

~~~java
java.util.function.IntUnaryOperator twice =
        new java.util.function.IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value * 2;
            }
        };
~~~

Hai đoạn là snippets hợp lệ khi đặt trong method; không khai báo hai biến `twice` cùng scope trong code thực tế.

**Cả hai `return` không tự return khỏi method bao ngoài** đang tạo và trả object. Cũng không thể dùng `break` trong lambda body để thoát một vòng lặp **bên ngoài lambda**; jump statements phải tuân lexical targets hợp lệ.

Khác biệt quan trọng về diễn đạt: anonymous class **định nghĩa method `applyAsInt`**, còn lambda cung cấp body theo function type được compiler xác định từ target interface.

## 25. Chương trình 12 — `return` chỉ kết thúc callback invocation

Tệp **`ReturnSemanticsDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ReturnSemanticsDemo {
    static IntUnaryOperator anonymous() {
        System.out.println("make anonymous");
        return new IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                if (value < 0) {
                    return 0;
                }
                return value + 1;
            }
        };
    }

    static IntUnaryOperator lambda() {
        System.out.println("make lambda");
        return value -> {
            if (value < 0) {
                return 0;
            }
            return value + 1;
        };
    }

    public static void main(String[] args) {
        IntUnaryOperator a = anonymous();
        IntUnaryOperator b = lambda();

        System.out.println("a=" + a.applyAsInt(-5));
        System.out.println("b=" + b.applyAsInt(2));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReturnSemanticsDemo.java
java ReturnSemanticsDemo
~~~

**Stdout:**

~~~text
make anonymous
make lambda
a=0
b=3
~~~

Các methods `anonymous()` và `lambda()` in lời thông báo và trả những callbacks. Về sau khi `applyAsInt(...)` chạy, `return` nằm **bên trong callback implementation**, không quay ngược để kết thúc `main()` sớm.

## 26. Target typing: vì sao lambda không thể đứng “một mình” như `new Runnable`

Anonymous creation expression nêu rõ kiểu sau `new`:

~~~java
new Runnable() {
    @Override
    public void run() {
    }
}
~~~

Còn lambda không tự mang một kiểu object source-level duy nhất, mà cần **target functional interface** từ ngữ cảnh:

~~~java
Runnable r = () -> System.out.println("work");
~~~

Ví dụ lambda sau **cố ý không biên dịch**:

~~~java
// Object invalid = () -> System.out.println("work");
~~~

Vì `Object` **không phải functional interface**, compiler không có target function type để chuyển lambda thành Object trực tiếp. Muốn lưu dưới Object, hãy tạo lambda với target rõ ràng rồi mới upcast:

~~~java
Object value = (Runnable) () -> System.out.println("work");
~~~

Đây là snippet hợp lệ trong method: cast cung cấp target type Runnable cho lambda, sau đó kết quả được gán vào Object.

Đối với anonymous class, `Object value = new Runnable() { ... };` là hợp lệ vì biểu thức `new` đã tạo object thuộc anonymous class implements Runnable và có thể upcast lên Object.

## 27. Chương trình 13 — cast cung cấp target type cho lambda

Tệp **`LambdaTargetTypeDemo.java`** hoàn chỉnh, chạy độc lập trên Java 17+:

~~~java
public class LambdaTargetTypeDemo {
    static void accept(Object value) {
        System.out.println("runnable=" + (value instanceof Runnable));
        if (value instanceof Runnable task) {
            task.run();
        }
    }

    public static void main(String[] args) {
        Object anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("from anonymous");
            }
        };

        Object lambda = (Runnable) () ->
                System.out.println("from lambda");

        accept(anonymous);
        accept(lambda);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
~~~

**Stdout chính xác của chương trình trên:**

~~~text
runnable=true
from anonymous
runnable=true
from lambda
~~~

Cast `(Runnable)` cung cấp target type cho lambda trong biểu thức gán vào `Object`. Cả anonymous class và lambda đều thực hiện `Runnable`; phép kiểm tra `instanceof` và hai callback tạo ra bốn dòng output xác định, không phụ thuộc tên lớp triển khai do JVM tạo.

## 28. Overload và target types: lambda có thể cần định kiểu rõ ràng

Nếu có overloads nhận các functional interfaces khác nhau, một lambda có thể:

- Chọn được một overload vì parameter types/return shape đủ khác nhau;
- Hoặc **gây mơ hồ** nếu nhiều target function types đều tương thích.

Chẳng hạn:

~~~java
void use(Runnable task) {
    task.run();
}

void use(java.util.concurrent.Callable<String> task)
        throws Exception {
    System.out.println(task.call());
}
~~~

Đây là **method snippets**, đặt trong một class.

Lời gọi `use(() -> "hi")` tương thích với `Callable<String>` (trả String), không với `Runnable` (không cho body là expression có kết quả String trong trường hợp này). Nhưng lambda body như `() -> someVoidMethod()` có những quy tắc overload khác, và overloads cùng arity/SAM shape có thể gây ambiguity.

Khi khó đọc, hãy **đặt vào biến đã khai target type**:

~~~java
Runnable action = () -> System.out.println("work");
use(action);
~~~

Hoặc dùng cast tường minh `use((Runnable) () -> ...)` nếu API cần.

Với anonymous class, kiểu `new Runnable() { ... }` đã nằm ngay trong biểu thức creation, nên compiler thường có nhiều thông tin kiểu hơn ngay từ đầu.

## 29. Chương trình 14 — phân giải overload bằng kiểu tường minh

Tệp **`OverloadTargetDemo.java`**:

~~~java
import java.util.concurrent.Callable;

public class OverloadTargetDemo {
    static void use(Runnable action) {
        System.out.print("runnable=");
        action.run();
    }

    static void use(Callable<String> action)
            throws Exception {
        System.out.println("callable=" + action.call());
    }

    public static void main(String[] args)
            throws Exception {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("A");
            }
        };

        Runnable lambda =
                () -> System.out.println("L");

        use(anonymous);
        use(lambda);
        use((Callable<String>) () -> "C");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OverloadTargetDemo.java
java OverloadTargetDemo
~~~

**Stdout:**

~~~text
runnable=A
runnable=L
callable=C
~~~

Cả `anonymous` lẫn `lambda` được khai báo rõ kiểu Runnable, vì vậy `use(...)` chọn đúng overload. Cast trên lambda cuối chỉ rõ `Callable<String>`.

Không nên suy từ ví dụ này rằng mọi overload có lambda đều cần cast; đó là phương án làm code rõ nghĩa khi các target types có nguy cơ mơ hồ.

## 30. Functional interface có thể có default/static methods

Một interface vẫn là functional interface nếu có **đúng một abstract method** theo quy tắc SAM, dù có thêm default hoặc static methods.

~~~java
@FunctionalInterface
interface Transformer {
    String apply(String text);

    default String applyUpper(String text) {
        return apply(text).toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Cả lambda và anonymous class có thể cung cấp implementation cho `apply`:

~~~java
Transformer lambda = text -> "L:" + text;

Transformer anonymous = new Transformer() {
    @Override
    public String apply(String text) {
        return "A:" + text;
    }
};
~~~

Các snippets hợp lệ nếu `Transformer` đã khai báo. Method `applyUpper` là **default method có sẵn** trên interface; cả hai objects có thể gọi thông qua interface reference.

Anonymous class có thể **override default method** nếu muốn. Lambda body không phải một class declaration có method override riêng; để tùy biến nhiều methods, dùng anonymous/named implementation hoặc điều chỉnh interface thiết kế.

## 31. Chương trình 15 — default method và lambda/anonymous

Tệp **`DefaultMethodComparisonDemo.java`**:

~~~java
import java.util.Locale;

@FunctionalInterface
interface Transformer {
    String apply(String value);

    default String upper(String value) {
        return apply(value).toUpperCase(Locale.ROOT);
    }
}

public class DefaultMethodComparisonDemo {
    public static void main(String[] args) {
        Transformer anonymous = new Transformer() {
            @Override
            public String apply(String value) {
                return "A:" + value;
            }

            @Override
            public String upper(String value) {
                return "CUSTOM:" + apply(value);
            }
        };

        Transformer lambda = value -> "L:" + value;

        System.out.println("anonymous apply="
                + anonymous.apply("java"));
        System.out.println("anonymous upper="
                + anonymous.upper("java"));
        System.out.println("lambda apply="
                + lambda.apply("java"));
        System.out.println("lambda upper="
                + lambda.upper("java"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DefaultMethodComparisonDemo.java
java DefaultMethodComparisonDemo
~~~

**Stdout:**

~~~text
anonymous apply=A:java
anonymous upper=CUSTOM:A:java
lambda apply=L:java
lambda upper=L:JAVA
~~~

Anonymous class override cả `apply` và default method `upper`, còn lambda chỉ cung cấp hành vi SAM `apply`; `upper` vẫn chạy default implementation của interface.

Vì `upper` dùng `Locale.ROOT`, việc chuyển chuỗi `"L:java"` thành `"L:JAVA"` có kết quả nhất quán không phụ thuộc locale mặc định của máy.

## 32. Method references: lựa chọn thứ ba khi chỉ chuyển tiếp một method

Ngoài anonymous và lambda, Java cho phép **method reference** khi target functional interface phù hợp:

~~~java
Runnable lambda = () -> System.out.println("ready");
Runnable methodReference = System.out::println;
~~~

Đây là snippet về cú pháp, nhưng `System.out::println` **không phù hợp làm Runnable không tham số** vì `PrintStream.println` có overload không tham số và có thể phù hợp; khi chạy Runnable này, nó chỉ in một dòng trống. Nó không có cùng hành vi với lambda in "ready".

Nếu muốn thực sự tương đương về giá trị in, hãy viết:

~~~java
java.util.function.Consumer<String> a =
        value -> System.out.println(value);

java.util.function.Consumer<String> b =
        System.out::println;
~~~

Hai Consumers đều nhận String và gọi println.

Method reference giống lambda về **target functional interface**, nhưng không có lambda parameter body để bạn viết `this`. Khi dùng `this::method` trong instance method, `this` vẫn chỉ enclosing instance theo lexical context.

Không cần chọn method reference bằng mọi giá: nếu binding hoặc overload làm người đọc khó biết method nào được gọi, lambda tường minh thường rõ hơn.

## 33. Chương trình 16 — method reference và lambda cùng target type

Tệp **`MethodReferenceDemo.java`**:

~~~java
import java.util.function.Function;

public class MethodReferenceDemo {
    public static void main(String[] args) {
        Function<String, Integer> lambda =
                text -> text.length();

        Function<String, Integer> reference =
                String::length;

        System.out.println("lambda=" + lambda.apply("Java"));
        System.out.println("reference="
                + reference.apply("Java"));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 MethodReferenceDemo.java
java MethodReferenceDemo
~~~

**Stdout:**

~~~text
lambda=4
reference=4
~~~

Cả hai có target type `Function<String,Integer>`; compiler điều chỉnh trả `int` từ `String.length()` thành `Integer` qua boxing phù hợp.

Method reference ở đây là cách viết ngắn cho việc chuyển tiếp tới một method tồn tại sẵn; không có thêm state, constructor hoặc `this` riêng trong source.

## 34. `super` trong lambda là lexical, không phải superclass của một lambda object

Ở anonymous subclass của một class, `super.method()` trong anonymous method gọi implementation từ superclass của anonymous class.

Trong lambda viết bên trong một **instance method của một class con có named superclass**, `super.method()` (khi hợp lệ) được hiểu theo **ngữ cảnh lexical của class chứa lambda**. Nó không nói về superclass của một lớp lambda do JVM có thể dùng khi triển khai.

Ví dụ khái niệm:

~~~java
class Base {
    String label() {
        return "base";
    }
}

class Derived extends Base {
    Runnable action() {
        return () -> System.out.println(super.label());
    }
}
~~~

Đây là class minh họa hợp lệ. Khi `new Derived().action().run()`, lambda gọi `Base.label()` thông qua `super` của Derived. Điều đó phù hợp với việc `this` trong lambda chỉ Derived instance.

Đừng dùng reflection xem JVM đã sinh class nào để suy ngược về `super` hoặc `this` của lambda. Quy tắc lexical của Java source mới là cơ sở chính xác.

## 35. Chương trình 17 — `super` trong lambda của subclass

Tệp **`LexicalSuperDemo.java`**:

~~~java
class Parent {
    String name() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String name() {
        return "Child";
    }

    Runnable lambda() {
        return () -> {
            System.out.println("this=" + this.name());
            System.out.println("super=" + super.name());
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("outer="
                        + Child.this.name());
            }
        };
    }
}

public class LexicalSuperDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.lambda().run();
        child.anonymous().run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LexicalSuperDemo.java
java LexicalSuperDemo
~~~

**Stdout:**

~~~text
this=Child
super=Parent
outer=Child
~~~

Trong lambda, `this` và `super` tương ứng Child instance và Parent implementation của Child. Trong anonymous Runnable, `Child.this` được dùng để gọi đúng enclosing Child instance.

Nếu viết `super.name()` **trực tiếp** trong anonymous Runnable, superclass của anonymous Runnable thường là Object, vốn không có `name()`; nó **không** tự gọi `Parent.name()` của enclosing Child. Đó chính là khác biệt cần nhớ.

## 36. `equals`, object identity và runtime implementation

Anonymous creation expression có `new` và class body, nên mỗi lần đánh giá thành công một object creation mới có một object reference mới, theo các quy tắc Java.

Với lambda, **không nên áp đặt** rằng hai lần evaluate cùng lambda expression luôn tạo hai identity khác nhau. JLS cho phép implementation linh hoạt về việc cấp phát/tái sử dụng đối tượng function. Vì vậy, **đừng dùng `==` giữa lambda objects để quyết định nghiệp vụ**.

Tương tự:

- `getClass().getName()` của anonymous object có thể chứa tên binary do compiler sinh; không ổn định như business ID.
- Implementation class/name của lambda là chi tiết JVM/runtime, không phải API contract để serialize hoặc lưu database.
- `toString()`, `hashCode()` và object identity không thay thế cho một định danh nghiệp vụ.
- Nếu cần so sánh cấu hình hai callbacks, hãy giữ **dữ liệu cấu hình trong value object có equality rõ**, thay vì hy vọng hai executable objects tự `equals` theo code body.

**Không suy** “lambda nhanh hơn anonymous class trong mọi trường hợp” chỉ vì lambda có thể được runtime tối ưu. Hãy profile workload thực tế nếu hiệu năng là yêu cầu.

## 37. Chương trình 18 — identity của hai anonymous instances

Tệp **`AnonymousIdentityDemo.java`**:

~~~java
public class AnonymousIdentityDemo {
    static Runnable anonymous(String text) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(text);
            }
        };
    }

    static Runnable lambda(String text) {
        return () -> System.out.println(text);
    }

    public static void main(String[] args) {
        Runnable first = anonymous("A");
        Runnable second = anonymous("B");
        Runnable third = lambda("C");

        System.out.println("anonymous distinct="
                + (first != second));
        System.out.println("anonymous same class="
                + (first.getClass() == second.getClass()));
        System.out.println("lambda Runnable="
                + (third instanceof Runnable));
        first.run();
        second.run();
        third.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousIdentityDemo.java
java AnonymousIdentityDemo
~~~

**Stdout:**

~~~text
anonymous distinct=true
anonymous same class=true
lambda Runnable=true
A
B
C
~~~

Hai lần gọi `anonymous(...)` tạo instances khác nhau của anonymous class khai báo trong **cùng một expression** của factory, nên có cùng runtime class nhưng identity khác.

Đối với lambda, chương trình chỉ kiểm tra **contract Runnable**, không dự đoán identity hay implementation class do JVM chọn. Đây là cách viết test bền vững.

## 38. Phạm vi ảnh hưởng của `this`: callbacks chạy ở thread khác

Nếu lambda được viết trong instance method và giữ reference tới `this`, nó có thể duy trì **reachability** của enclosing object chừng nào callback còn được giữ. Anonymous class tạo trong instance context cũng có thể gắn với enclosing instance tương ứng khi cần dùng nó.

Nhưng **`this` không thay đổi vì callback được chạy từ thread khác**. Nó vẫn chỉ object theo quy tắc lexical/anonymous scope, không tự trở thành Thread đang chạy.

Muốn biết thread thực thi, dùng `Thread.currentThread()` — đó là **thread hiện tại**, khác với object `this` của callback.

Cần cân nhắc:

- Callback được lưu trong registry sống lâu có thể giữ objects reachable lâu hơn dự kiến.
- Capture một mutable field/object không tạo synchronization.
- Nếu lambda/callback có side effects trong `AtomicReference.updateAndGet`, logic có thể bị gọi lại do CAS retry, gây side effects lặp.
- Với listener lifecycle dài, nên có unsubscribe/close policy khi API cung cấp.
- `final` trên reference không làm mutable object thread-safe.

## 39. Chương trình 19 — `this` khác với thread hiện hành

Tệp **`CallbackThreadContextDemo.java`**:

~~~java
final class Service {
    private final String label = "service";

    Runnable lambda() {
        return () -> {
            System.out.println("lambda owner=" + this.label);
            System.out.println("worker thread="
                    + Thread.currentThread().getName());
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous owner="
                        + Service.this.label);
            }
        };
    }
}

public class CallbackThreadContextDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Service service = new Service();
        Thread worker = new Thread(service.lambda(), "worker-1");
        worker.start();
        worker.join();
        service.anonymous().run();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CallbackThreadContextDemo.java
java CallbackThreadContextDemo
~~~

**Stdout (khi worker kết thúc bình thường):**

~~~text
lambda owner=service
worker thread=worker-1
anonymous owner=service
~~~

Lambda body chạy trên thread có tên do chính chương trình chỉ định, nhưng `this` vẫn là Service instance. Việc `worker.join()` đảm bảo hai dòng từ worker hoàn tất trước khi main gọi anonymous Runnable, vì thế thứ tự output xác định.

**Không có quy tắc** “anonymous class luôn đồng bộ” hoặc “lambda luôn bất đồng bộ”. Threading phụ thuộc **API gọi callback**; cả hai chỉ là cách cung cấp behavior.

## 40. Exceptions và method signatures

Một anonymous class implement interface method phải giữ đúng quy tắc signature, checked exceptions và visibility:

~~~java
java.util.concurrent.Callable<String> task =
        new java.util.concurrent.Callable<>() {
            @Override
            public String call() throws Exception {
                return "done";
            }
        };
~~~

Lambda:

~~~java
java.util.concurrent.Callable<String> task =
        () -> "done";
~~~

Hai snippets hợp lệ riêng rẽ khi đặt trong method. Chúng đều tạo một Callable có `call()` trả String. Nếu body ném một **checked exception**, tính hợp lệ được xét theo `throws` của abstract method tương ứng và các quy tắc target typing; lambda không tự loại bỏ checked exceptions.

Với Runnable, `run()` không khai báo checked exceptions, nên không thể ném checked IOException ra ngoài mà không xử lý trong body, dù dùng anonymous hay lambda.

`@Override` chỉ xuất hiện trên method declaration trong anonymous class; lambda không có `run()` declaration riêng để gắn annotation ấy.

## 41. Chọn hình thức theo nhu cầu — không chỉ theo số ký tự

**Chọn lambda** khi:

- Target type thực sự là functional interface.
- Chỉ cần triển khai một hành vi ngắn, không cần thêm instance fields/methods.
- Muốn dùng `this` theo lexical enclosing instance, hoặc đơn giản không cần `this`.
- Functional composition (`map`, `filter`, `Comparator.comparing`, `Predicate.and`) làm code tự nhiên.
- Muốn tập trung vào **hành vi** hơn là một class declaration.

**Chọn anonymous class** khi:

- Cần một subclass của non-final superclass tại điểm sử dụng.
- Interface có nhiều abstract methods cần hiện thực.
- Cần override default method của interface cùng lúc với abstract method.
- Muốn instance fields, initializer, helper methods bên trong một object cục bộ.
- Cần `this` trỏ vào chính anonymous instance hoặc `super` của anonymous superclass.
- Implementation ngắn và chỉ được dùng tại một chỗ.

**Chọn named local/static nested/top-level class** khi implementation phức tạp, cần tái sử dụng, test riêng, khai báo contracts rõ hoặc dễ bị anonymous body dài che mất logic xung quanh.

Không có tiêu chí “lambda hiện đại hơn nên luôn đúng”. Chọn theo **type contract, scope, state ownership, `this` và readability**.

## 42. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Dùng lambda với interface có hai abstract methods | Không phải functional interface | Anonymous/named class hoặc đổi API |
| Dùng lambda để extends abstract class | Lambda chỉ dùng target functional interface | Anonymous subclass |
| Nghĩ `this` trong anonymous là enclosing object | `this` chỉ anonymous instance | `Outer.this` khi hợp lệ |
| Nghĩ `this` trong lambda là lambda object | Lambda giữ lexical this | `this` là enclosing instance trong instance context |
| Viết `this` trong lambda ở static method | Không có lexical enclosing instance | Capture dependency tường minh |
| Viết local variable trùng tên enclosing local trong lambda body | Lambda không cho redeclare kiểu ấy | Dùng tên mới |
| Gán lại captured variable | Không effectively final | Tạo snapshot local mới |
| Capture StringBuilder rồi mong snapshot | Object mutable vẫn đổi | `toString()`/immutable copy |
| Cập nhật local counter bằng `counter++` trong lambda | Captured local không effectively final | Dùng field/holder có contract rõ |
| Nghĩ anonymous creation tự gọi run | `new` khác method invocation | Gọi `run()` hoặc giao cho executor |
| Dùng `==` để so sánh lambda business behavior | Identity/runtime representation không được hứa | So sánh state/config theo value |
| Dựa vào `Outer$1` hoặc lambda class name | Compiler/JVM implementation details | Dùng interface, type contracts |
| In stdout phụ thuộc thread scheduling | Kết quả có thể nondeterministic | `join`/synchronization khi dạy |
| Cho rằng lambda luôn thread-safe | Capture không đồng bộ mutable state | Đồng bộ và ownership phù hợp |
| Method `run()` trên anonymous Runnable thiếu public | Implement interface method phải public | `@Override public void run()` |
| Lambda thiếu target type khi gán Object | Object không functional interface | Cast tới Runnable hoặc typed variable |
| Coi `super` trong lambda là của generated lambda class | `super` dùng lexical context | Phân tích enclosing class |
| Anonymous body trở nên quá dài | Khó debug và bảo trì | Tách named class |

## 43. Hướng dẫn tự phân tích một đoạn code

Gặp một lambda hoặc anonymous class, hãy phân tích theo thứ tự:

1. **Target type là gì?** Interface hay superclass? Functional interface không?
2. **Hình thức source:** `new T(args) { ... }`, `() -> ...`, `T::method`?
3. **Anonymous body có methods/fields/init blocks gì?** Có đủ override/constructor access không?
4. **Lambda body nằm ở lexical context nào?** Static method hay instance method?
5. **`this` trong body chỉ cái gì?** Anonymous object hay enclosing instance?
6. **`Outer.this` có hợp lệ không?** Có enclosing instance được chọn đúng không?
7. **Có shadowing không?** Fields của anonymous có che outer fields? Lambda có redeclare local name sai không?
8. **Local variables được capture là gì?** Đã definitely assigned và effectively final chưa?
9. **Mutable references có bị alias không?** State có tiếp tục đổi sau khi callback được tạo không?
10. **Lúc nào callback chạy?** Tạo object không tự thực thi; ai gọi SAM method?
11. **Có checked exceptions, return, overload ambiguity không?**
12. **Một expression được đánh giá bao lần?** Với anonymous, mỗi `new` tạo instance khác; lambda identity không dùng làm contract.
13. **Có thread/context thay đổi không?** Điều đó không đổi binding lexical `this`, nhưng ảnh hưởng đến mutable state.
14. **Nên chọn cách diễn đạt nào rõ nhất cho người đọc?** Lambda/anonymous/named class.

Luôn kiểm tra **compile-time trước khi tính stdout**. Nếu code không có target functional interface hoặc `this` ở static context, không nên đoán một kết quả runtime cho chương trình vốn không biên dịch.

## 44. Bài tập tự luyện

**Câu 1.** `Runnable a = new Runnable(){ public void run(){} };` và `Runnable b = () -> {};` giống nhau ở API được gọi, khác nhau ở định nghĩa kiểu thế nào?

**Câu 2.** Một interface có hai abstract methods. Chọn lambda hay anonymous class? Vì sao?

**Câu 3.** Một abstract class có một abstract method. Có gán lambda trực tiếp cho kiểu abstract class ấy không?

**Câu 4.** Anonymous class tạo trong `Controller.action()` đọc `this`. `this` chỉ object nào?

**Câu 5.** Lambda tạo trong `Controller.action()` đọc `this`. `this` chỉ object nào?

**Câu 6.** Lambda tạo trong static method đọc `this.name`. Có hợp lệ không?

**Câu 7.** Anonymous class tạo trong static method có thể gọi `this.getClass()` trong instance method của nó không?

**Câu 8.** Anonymous class có `private int count` và tăng count trong run. Có vi phạm effectively final không?

**Câu 9.** Lambda đọc `int count=0` trong enclosing method rồi tăng `count++`. Có được không?

**Câu 10.** Capture `StringBuilder` effectively final rồi gọi append ở nơi khác. Anonymous/lambda sẽ đọc giá trị cũ hay mới?

**Câu 11.** Anonymous body có thể khai báo field trùng tên một local ở enclosing method không? Lambda body có thể khai báo local trùng tên đó không?

**Câu 12.** `this.label` trong anonymous class và `Outer.this.label` có thể đọc hai field khác nhau không?

**Câu 13.** `this.label` trong lambda instance method trỏ vào field nào?

**Câu 14.** Hai lần đánh giá cùng một anonymous `new ... { ... }` có bắt buộc trả cùng instance không?

**Câu 15.** So sánh `lambda1==lambda2` có phù hợp làm quyết định nghiệp vụ không?

**Câu 16.** Method `use(Object)` được gọi với literal `() -> run()` không cast. Vì sao có thể không hợp lệ?

**Câu 17.** Khi hai overloads cùng nhận functional interfaces có chữ ký tương thích, có thể xử lý lambda ambiguity bằng cách nào?

**Câu 18.** `return 1;` trong lambda body có làm method bao ngoài kết thúc và trả 1 luôn không?

**Câu 19.** Nếu interface có một abstract method và một default method, lambda có sử dụng được default method không?

**Câu 20.** Nếu cần override cả abstract method và default method, cách nào trực tiếp hơn?

**Câu 21.** Trong subclass method, `super.name()` đặt trong lambda nhắm tới superclass của class nào?

**Câu 22.** Anonymous Runnable tạo trong subclass gọi `super.name()` trực tiếp, liệu có tự chọn superclass của enclosing subclass không?

**Câu 23.** Nếu callback được chạy từ thread khác, `this` của lambda có tự thành Thread object không?

**Câu 24.** Vì sao anonymous/lambda capture mutable ArrayList cần chú ý concurrency riêng?

**Câu 25.** Khi nào method reference có thể thay lambda để đơn giản code?

**Câu 26.** `@Override` có dùng trên lambda body không? Có ích thế nào trên anonymous method?

**Câu 27.** Một callback được đăng ký trong registry dài hạn và capture enclosing service. Có nguy cơ lifecycle nào?

**Câu 28.** Nếu implementation có nhiều fields, nhiều methods và dài hàng trăm dòng, anonymous class còn là lựa chọn duy nhất không?

### Đáp án và giải thích

1. Cả hai cung cấp Runnable, nhưng anonymous khai báo anonymous class + object; lambda là biểu thức của target functional interface.
2. Anonymous/named class; lambda cần một functional interface có một abstract method.
3. Không. Lambda không dùng một abstract class làm target type.
4. `this` là anonymous-class object.
5. `this` là Controller instance theo lexical context.
6. Không vì static method không có enclosing this.
7. Có. `this` hợp lệ trong instance method của anonymous object.
8. Không. `count` là field của anonymous object, không phải captured local variable.
9. Không. Captured local `count` phải final/effectively final.
10. Giá trị mới của StringBuilder sau mutation; capture reference không snapshot nội dung.
11. Có thể khai field trong anonymous class theo quy tắc scope; lambda không cho redeclare local name đang trong scope của enclosing method.
12. Có. `this.label` thuộc anonymous object; `Outer.this.label` thuộc enclosing Outer.
13. Field của lexical enclosing instance nếu tên hợp lệ, không phải field của một lambda object nguồn.
14. Không; mỗi `new` thành công tạo object mới.
15. Không. Runtime có thể tái sử dụng lambda object; identity không mô tả chức năng nghiệp vụ.
16. Object không phải functional interface, nên không cung cấp target type cho lambda.
17. Gán lambda vào biến của functional interface cụ thể hoặc cast lambda rõ target.
18. Không. `return` trả từ lần gọi của functional method body.
19. Có. Object/function target type có thể sử dụng default method trên interface.
20. Anonymous/named class, vì có thể khai hai method implementations/overrides.
21. Superclass của lexical enclosing subclass, không phải một generated lambda class.
22. Không. `super` trong anonymous body chỉ superclass của chính anonymous class; dùng `Outer.this` hoặc API thích hợp.
23. Không. Binding của `this` không phụ thuộc thread thực thi.
24. Final/effectively final chỉ quản lý reference variable, không đồng bộ writes trên mutable list.
25. Khi chỉ chuyển tiếp tới method đã có và target function signature phù hợp, ví dụ `String::length`.
26. Lambda không khai method nên không có `@Override`; trong anonymous `@Override` giúp compiler xác thực method đúng.
27. Callback giữ enclosing object còn reachable lâu, có thể gây retention và cần unregister/close policy.
28. Không. Local/static nested/top-level named class giúp đọc và kiểm thử tốt hơn.

## 45. Checklist cho code review

- Target type của lambda thật sự là functional interface?
- Anonymous expression chọn interface hoặc superclass hợp lệ, không final?
- Interface nhiều abstract methods đã có đầy đủ implementations nếu dùng anonymous?
- Khi nói `this`, đã chỉ rõ đó là anonymous object hay enclosing object?
- Nếu expression được viết ở static context, đã tránh dùng lexical `this` trong lambda?
- Có dùng `Outer.this` đúng nơi có enclosing instance?
- Tên local trong lambda có bị redeclare trong cùng lexical scope không?
- Captured variables có final/effectively final và definitely assigned?
- Captured mutable object có tạo alias/concurrency risks không?
- Nếu cần state riêng, có thiết kế fields/holder rõ ràng?
- Có phân biệt `return` trong callback với return của enclosing method?
- Có hiểu lambda target typing và overload ambiguity?
- Có tránh suy đoán class name/identity của lambda implementation?
- Có tránh dùng `==` trên callbacks làm value equality?
- Với `super`, có chọn đúng lexical superclass hoặc anonymous superclass?
- Nếu code dựa vào default interface methods, có hiểu khác biệt override?
- Nếu dùng method reference, overload binding có rõ nghĩa?
- Các methods/callbacks có được gọi đúng thời điểm do API quyết định?
- Với concurrency, có synchronization/immutable state thích hợp?
- Với callback sống lâu, có xem xét reachability và cleanup?
- Đã thử compile Java 17 và kiểm tra stdout chỉ gồm các dòng có thứ tự/hành vi xác định?
- Nếu implementation lớn, đã cân nhắc một named class thay vì anonymous body quá dài?

## 46. Tài liệu Java 17 chính thức

- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): anonymous class body, constructor và cú pháp `new`.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda body, target type và ngữ nghĩa lexical.
- [JLS 17 §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2): body và các quy tắc statement.
- [JLS 17 §15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): functional interface target typing.
- [JLS 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): định nghĩa SAM và interfaces hợp lệ.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): tên trùng và scope.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing objects.
- [JLS 17 §15.8.3 — this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): biểu thức `this` ở ngữ cảnh hợp lệ.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this`.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): captured variables và effectively final.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution.
- [Java SE 17 — FunctionalInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/FunctionalInterface.html): annotation kiểm tra hợp đồng SAM.
- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): interface callback không trả kết quả.
- [Java SE 17 — Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): interface callback có kết quả và checked exceptions.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): quản lý mutable counter có chủ đích.
- [Java SE 17 — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): nhận diện anonymous runtime class.

**Tổng kết:** Khi muốn thực hiện một callback ngắn của functional interface, **lambda** thường cô đọng và giữ `this` theo lexical enclosing context. Khi cần một object triển khai nhiều methods, có instance fields riêng, override default method hay kế thừa một class, **anonymous class** phù hợp hơn; `this` trong instance method của nó chỉ **anonymous object**. Cả hai đều tuân quy tắc capture final/effectively final, nhưng khác nhau rõ ở **phạm vi khai báo tên, target typing, inheritance và object identity**. Trước khi chọn, hãy trả lời ba câu: *target type là gì, `this` phải trỏ object nào, và state/callback sẽ sống bao lâu?*
