# Khai báo và tạo đối tượng vô danh trong một biểu thức — Java 17+

Trong Java, **anonymous class (lớp vô danh)** cho phép bạn **khai báo một lớp không có tên riêng và tạo ngay một đối tượng của lớp đó bằng cùng một biểu thức**. Thay vì đặt tên cho một class triển khai `Runnable` hoặc một class kế thừa `Base`, bạn viết phần thân lớp ngay sau `new`.

Ví dụ:

~~~java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Xin chào từ anonymous class");
    }
};
action.run();
~~~

Đây là **đoạn Java hợp lệ khi đặt trong một method**. Biểu thức `new Runnable() { ... }` đồng thời:

1. Khai báo một **lớp vô danh mới**, triển khai interface `Runnable`.
2. Định nghĩa method `run()` bắt buộc.
3. Tạo một **instance** của lớp vô danh ấy.
4. Trả một reference có thể gán cho biến kiểu `Runnable`.

Không có class được đặt tên như `MyRunnable` trong source. Nhưng vẫn có **một lớp thực sự ở runtime** và vẫn có **một object thực sự**, có thể có fields, instance initializers, identity và methods.

Bài thuộc **Java core – class-object**, nhóm **Lớp vô danh**. Trọng tâm là cú pháp và cơ chế *declaration + instantiation in one expression*, sau đó là hai dạng `new Interface() { ... }` và `new Base(args) { ... }`, phạm vi, biểu thức `this`, capture dữ liệu, thời gian sống, so sánh với lambda/local class, lỗi biên dịch và cách áp dụng.

Các ví dụ chạy được dùng **Java 17+**. Mỗi chương trình độc lập có tên tệp, lệnh `javac`/`java`, và stdout dự đoán cụ thể. Đoạn cố ý gây lỗi được **đánh dấu không biên dịch**, không được nhầm với chương trình chạy hoàn chỉnh.

## 1. Vì sao cần anonymous class?

Giả sử ứng dụng cần truyền một đối tượng có hành vi `run()` cho một API nhận `Runnable`.

Cách đặt tên riêng:

~~~java
class GreetingTask implements Runnable {
    @Override
    public void run() {
        System.out.println("Hello");
    }
}
~~~

Ở một vị trí khác:

~~~java
Runnable action = new GreetingTask();
action.run();
~~~

Hai đoạn trên là **minh họa**, có thể kết hợp trong cùng phạm vi thích hợp. Nếu kiểu `GreetingTask` được dùng lại ở nhiều chỗ, cách này rất rõ ràng.

Nhưng nếu implementation chỉ có ý nghĩa **ngay tại điểm tạo**, bạn có thể viết:

~~~java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
action.run();
~~~

**Ý nghĩa:** không cần đặt tên cho một class chỉ dùng một lần; phần hành vi được đặt gần nơi cấu hình/cung cấp callback.

**Không có nghĩa** anonymous class “không có class” hoặc chỉ là một function. Nó là một **class thực sự** được khai báo ẩn danh, và mỗi lần biểu thức khởi tạo `new ... { ... }` được đánh giá bình thường đều tạo một instance mới.

## 2. Hai cú pháp nền tảng cần thuộc

**Triển khai một interface:**

~~~java
SomeInterface value = new SomeInterface() {
    @Override
    public void requiredMethod() {
        // Nội dung hiện thực phù hợp với hợp đồng interface.
    }
};
~~~

Đây là **khuôn cú pháp minh họa**, không phải code runnable độc lập vì `SomeInterface` chưa được định nghĩa. Khi interface tồn tại, constructor arguments sau tên interface ở dạng trên phải là **cặp ngoặc rỗng**: interface không có constructor để gọi. Phần thân phải cung cấp implementations cho các abstract methods chưa được thỏa mãn.

**Tạo subclass vô danh của một class có sẵn:**

~~~java
SomeBase value = new SomeBase(constructorArgument) {
    @Override
    public String description() {
        return "Phiên bản được tùy biến";
    }
};
~~~

Đây cũng là **khuôn cú pháp**, giả định `SomeBase` không final, có constructor nhận `constructorArgument`, có method `description()` có thể override và mọi phương thức abstract cần thiết được cài đặt.

Ở dạng thứ hai, biểu thức chạy một constructor phù hợp của **superclass**, rồi thực hiện khởi tạo của anonymous subclass.

Trong cả hai dạng, **dấu `{ ... }` sau `new` là class body**, không phải block lệnh tách biệt sau một câu lệnh `new`.

## 3. Một biểu thức vừa khai báo lớp vừa tạo instance

Một class có tên được khai báo một nơi và dùng `new` nơi khác:

~~~java
class CounterTask implements Runnable {
    @Override
    public void run() {
        System.out.println("work");
    }
}

Runnable task = new CounterTask();
~~~

Các dòng trên là **minh họa**, trong đó biến task cần đặt vào method/initializer thích hợp. Phần khai báo `CounterTask` tạo **kiểu có tên** được tham chiếu về sau bằng tên đó.

Còn:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("work");
    }
};
~~~

phần `new Runnable() { ... }` vừa **định nghĩa** anonymous implementation, vừa **khởi tạo** instance.

**Phân tích chính xác một lời gọi:**

~~~text
Runnable task = new Runnable() { ... };
                └──────────── expression ──────────┘
                ├─ superclass/interface mục tiêu: Runnable
                ├─ class body: định nghĩa run()
                ├─ compiler tạo một class vô danh
                └─ new tạo object, trả reference kiểu tương thích Runnable
~~~

Vì anonymous class không có **source-level simple name**, code ở nơi khác không thể viết `new TênLớpVôDanh()` để khởi tạo lại đúng class ấy theo một tên Java nguồn thông thường.

## 4. Chương trình hoàn chỉnh 1 — tạo và gọi Runnable vô danh

Tạo tệp **`AnonymousRunnableDemo.java`**:

~~~java
public class AnonymousRunnableDemo {
    public static void main(String[] args) {
        System.out.println("before");

        Runnable first = new Runnable() {
            @Override
            public void run() {
                System.out.println("first action");
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
                System.out.println("second action");
            }
        };

        first.run();
        second.run();

        System.out.println("same object=" + (first == second));
        System.out.println("first anonymous="
                + first.getClass().isAnonymousClass());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousRunnableDemo.java
java AnonymousRunnableDemo
~~~

**Stdout chính xác:**

~~~text
before
first action
second action
same object=false
first anonymous=true
~~~

`first` và `second` trỏ tới **hai instances**, được tạo từ **hai anonymous class declarations** riêng biệt. Phần body của từng anonymous class cung cấp cách triển khai `Runnable.run()`.

`first.run()` là lời gọi thông thường qua interface reference; Java chọn implementation trên object thực tế. Method `Class.isAnonymousClass()` cho phép quan sát rằng runtime class tương ứng là anonymous class.

**Chú ý:** `new Runnable() { ... }` **không gọi `run()` tự động**. `run()` chỉ chạy khi bạn gọi nó hoặc giao object cho một API thực sự gọi method đó (ví dụ scheduler phù hợp).

## 5. Gán vào biến, truyền thẳng làm đối số, trả về từ method

Anonymous class là một **biểu thức tạo đối tượng**, nên có thể xuất hiện ở những vị trí mà biểu thức object phù hợp được chấp nhận:

**Gán vào biến:**

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};
~~~

**Truyền thẳng vào method:**

~~~java
execute(new Runnable() {
    @Override
    public void run() {
        System.out.println("B");
    }
});
~~~

Ở đoạn thứ hai, giả định method `execute(Runnable)` tồn tại; đây là **snippet trong một method**, không phải chương trình standalone.

**Trả về từ method:**

~~~java
static Runnable createTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println("C");
        }
    };
}
~~~

Đây là **method hợp lệ khi đặt trong class**. Caller nhận kết quả dưới interface `Runnable`; không cần biết tên bytecode của anonymous class.

**Gọi ngay method trên kết quả:**

~~~java
new Runnable() {
    @Override
    public void run() {
        System.out.println("D");
    }
}.run();
~~~

Đây là đoạn hợp lệ khi đặt ở vị trí statement trong method. **Không cần lưu biến** nếu object chỉ được dùng một lần ngay tại đó.

## 6. Chương trình hoàn chỉnh 2 — ba vị trí sử dụng một anonymous expression

Tạo tệp **`AnonymousExpressionPositionsDemo.java`**:

~~~java
public class AnonymousExpressionPositionsDemo {
    static void execute(Runnable task) {
        System.out.println("execute begins");
        task.run();
    }

    static Runnable create(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("created=" + message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable variable = new Runnable() {
            @Override
            public void run() {
                System.out.println("variable");
            }
        };
        variable.run();

        execute(new Runnable() {
            @Override
            public void run() {
                System.out.println("argument");
            }
        });

        Runnable returned = create("done");
        returned.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousExpressionPositionsDemo.java
java AnonymousExpressionPositionsDemo
~~~

**Stdout:**

~~~text
variable
execute begins
argument
created=done
~~~

Cả ba anonymous expressions tạo objects bình thường. Việc object được truyền vào tham số hay trả qua `return` chỉ là cách di chuyển **reference**, không làm class body bị khai báo lại dưới một tên mới.

Method `create(String message)` còn minh họa **capture tham số**: anonymous body sử dụng `message`, một tham số effectively final vì không bị gán lại. Nội dung capture được giải thích sâu hơn ở phần sau.

## 7. Anonymous implementation phải thỏa interface contract

Khi viết:

~~~java
Runnable value = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

compiler kiểm tra class vô danh triển khai mọi abstract methods mà nó có trách nhiệm triển khai. `Runnable` có một abstract method `run()`, nên ví dụ đủ.

Với interface có **hai abstract methods**:

~~~java
interface Observer {
    void onNext(String value);
    void onDone();
}
~~~

một anonymous class triển khai Observer phải cài cả `onNext` và `onDone` (trừ các quy tắc abstract implementation từ superclass khi áp dụng; anonymous class bản thân không được khai báo abstract).

**Không hợp lệ nếu chỉ cài một method:**

~~~java
// ĐOẠN CỐ Ý KHÔNG BIÊN DỊCH:
Observer incomplete = new Observer() {
    @Override
    public void onNext(String value) {
        System.out.println(value);
    }
    // Thiếu onDone().
};
~~~

Đây là lỗi compile-time; không tồn tại stdout để mô phỏng. Một lỗi khác là đánh vần sai tên/signature method: `@Override` giúp compiler phát hiện việc method bạn viết không thực sự override method mong đợi.

## 8. Chương trình hoàn chỉnh 3 — interface nhiều method và trạng thái riêng

Tạo tệp **`AnonymousObserverDemo.java`**:

~~~java
interface Observer {
    void onNext(String value);
    void onDone();
}

public class AnonymousObserverDemo {
    static void emit(Observer observer) {
        observer.onNext("start");
        observer.onNext("finish");
        observer.onDone();
    }

    public static void main(String[] args) {
        Observer observer = new Observer() {
            private int received;

            @Override
            public void onNext(String value) {
                received++;
                System.out.println("event#" + received + "=" + value);
            }

            @Override
            public void onDone() {
                System.out.println("total=" + received);
            }
        };

        emit(observer);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AnonymousObserverDemo.java
java AnonymousObserverDemo
~~~

**Stdout chính xác:**

~~~text
event#1=start
event#2=finish
total=2
~~~

Anonymous class có **instance field `received`**, và hai instance methods. Đây là điểm khác biệt quan trọng với cách dùng lambda: một lambda chỉ trực tiếp cung cấp implementation cho **một functional interface method**, không tự khai báo một class body chứa nhiều methods/instance fields như trên.

Anonymous class phù hợp khi implementation cục bộ cần **nhiều callbacks** hoặc **state riêng gắn với một object**. Nếu callback thực sự được chạy từ nhiều threads, field `received++` vẫn không tự thread-safe.

## 9. Anonymous class kế thừa từ superclass

Ngoài interface, anonymous class còn có thể **mở rộng một class hợp lệ không final**:

~~~java
abstract class Message {
    private final String receiver;

    Message(String receiver) {
        this.receiver = receiver;
    }

    protected String receiver() {
        return receiver;
    }

    abstract String render();
}
~~~

Một object có thể được tạo như sau:

~~~java
Message message = new Message("An") {
    @Override
    String render() {
        return "Gửi tới " + receiver();
    }
};
~~~

Đây là những **định nghĩa/snippet hợp lệ nếu đặt trong các ngữ cảnh tương ứng**. Trong biểu thức `new Message("An") { ... }`:

1. `Message` là superclass được chọn.
2. `("An")` cung cấp đối số cho constructor phù hợp của Message.
3. `{ ... }` định nghĩa một subclass vô danh của Message, implement method abstract `render()`.
4. `new` tạo object thuộc anonymous subclass, có thể gán cho reference kiểu Message.

Không được viết `implements InterfaceX` ở sau anonymous class body như một class declaration có tên. Biểu thức anonymous creation đã xác định **một** kiểu class hoặc interface đứng sau `new`; việc kế thừa/triển khai thêm quan hệ được xác định thông qua kiểu đó.

## 10. Chương trình hoàn chỉnh 4 — truyền đối số vào superclass constructor

Tạo tệp **`AnonymousSuperclassDemo.java`**:

~~~java
abstract class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    protected final String name() {
        return name;
    }

    abstract String text();
}

public class AnonymousSuperclassDemo {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String text() {
                return "Xin chào, " + name();
            }
        };

        System.out.println(greeting.text());
        System.out.println("anonymous="
                + greeting.getClass().isAnonymousClass());
        System.out.println("superclass="
                + greeting.getClass()
                        .getSuperclass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousSuperclassDemo.java
java AnonymousSuperclassDemo
~~~

**Stdout:**

~~~text
Xin chào, An
anonymous=true
superclass=Greeting
~~~

`Greeting` là abstract class, **không thể** tạo trực tiếp bằng `new Greeting("An")` nếu không có anonymous class body cung cấp đủ implementations. Trong ví dụ, subclass vô danh triển khai `text()`; constructor `Greeting(String)` khởi tạo field `name`.

**Cần phân biệt:** kiểu tham chiếu ở source là Greeting, runtime type là một subclass vô danh. Anonymous class không có constructor **được bạn khai báo tên riêng**, nhưng construction vẫn diễn ra và superclass constructor vẫn được gọi theo quy tắc Java.

## 11. Không có constructor được đặt tên cho anonymous class

Vì anonymous class không có source-level simple name, bạn **không thể khai báo constructor theo kiểu `AnonymousName(...)`** bên trong body của nó.

Muốn cấp dữ liệu ban đầu, thường dùng:

- **Superclass constructor arguments**, ví dụ `new Base(10) { ... }`.
- **Instance field initializer**, ví dụ `private final int initial = 10;`.
- **Instance initializer block**, ví dụ `{ log("init"); }`.
- **Capture final/effectively final variables** từ phạm vi bao nếu phù hợp.
- **Factory method** bao quanh biểu thức creation để validate/chuẩn bị tham số trước.

Ví dụ:

~~~java
Runnable task = new Runnable() {
    private final String message = "start";

    {
        System.out.println("anonymous initializer");
    }

    @Override
    public void run() {
        System.out.println(message);
    }
};
~~~

Đây là snippet hợp lệ trong method. Khi đánh giá `new Runnable() { ... }`, initializer chạy trong quá trình tạo object; sau đó `task.run()` mới chạy nếu caller gọi.

**Không nhầm instance initializer với method run()**: initializer chạy **khi tạo**; `run()` chạy **khi được gọi**. Tránh gọi overridable methods từ constructor/initializer khi subclass chưa hoàn chỉnh, vì có thể khiến code chạy trên object khởi tạo dở dang.

## 12. Chương trình hoàn chỉnh 5 — superclass constructor và instance initializer

Tạo tệp **`AnonymousInitializationDemo.java`**:

~~~java
abstract class Seed {
    private final int base;

    Seed(int base) {
        this.base = base;
        System.out.println("base constructor=" + base);
    }

    protected final int base() {
        return base;
    }

    abstract int result();
}

public class AnonymousInitializationDemo {
    public static void main(String[] args) {
        Seed value = new Seed(10) {
            private final int offset = 5;

            {
                System.out.println("anonymous init=" + offset);
            }

            @Override
            int result() {
                return base() + offset;
            }
        };

        System.out.println("result=" + value.result());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousInitializationDemo.java
java AnonymousInitializationDemo
~~~

**Stdout chính xác:**

~~~text
base constructor=10
anonymous init=5
result=15
~~~

Khi tạo object, Java thực hiện **construction chain** qua superclass phù hợp. Trong ví dụ, constructor Seed in dòng đầu; initializer của subclass vô danh đọc `offset` đã được khởi tạo và in dòng thứ hai. Sau khi biểu thức new trả object, `result()` mới được gọi và in 15.

**Hàm khởi tạo `Seed(10)` không phải constructor của anonymous class do bạn đặt tên**. Nó là đường khởi tạo superclass mà anonymous subclass sử dụng.

## 13. Instance fields và methods riêng của anonymous class

Một anonymous class có thể khai báo:

~~~java
Runnable counter = new Runnable() {
    private int times;

    private void log() {
        System.out.println("run#" + times);
    }

    @Override
    public void run() {
        times++;
        log();
    }
};
~~~

Đây là snippet hợp lệ trong method. `times` là một instance field **riêng của object vô danh**, không phải local variable của method chứa expression.

Một biến khác trỏ cùng object `counter` sẽ quan sát cùng internal state; tạo **object khác** bằng cách đánh giá expression creation thêm lần nữa (trong một factory hay vòng lặp) sẽ cấp instance state mới.

**Truy cập từ bên ngoài:** khi reference được khai báo là `Runnable`, chỉ các methods khả dụng qua `Runnable` (và Object) mới có thể gọi trực tiếp theo static type. Private helper `log()` không trở thành API của Runnable chỉ vì anonymous class có định nghĩa nó.

## 14. Chương trình hoàn chỉnh 6 — trạng thái tồn tại qua nhiều lần gọi

Tạo tệp **`AnonymousStateDemo.java`**:

~~~java
import java.util.function.IntSupplier;

public class AnonymousStateDemo {
    static IntSupplier counter(int start) {
        return new IntSupplier() {
            private int current = start;

            @Override
            public int getAsInt() {
                current++;
                return current;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier first = counter(10);
        IntSupplier second = counter(10);

        System.out.println("first#1=" + first.getAsInt());
        System.out.println("first#2=" + first.getAsInt());
        System.out.println("second#1=" + second.getAsInt());
        System.out.println("first#3=" + first.getAsInt());
        System.out.println("same=" + (first == second));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousStateDemo.java
java AnonymousStateDemo
~~~

**Stdout:**

~~~text
first#1=11
first#2=12
second#1=11
first#3=13
same=false
~~~

Mỗi lần gọi `counter(10)` đánh giá anonymous creation expression và tạo một **IntSupplier object** mới có field `current` riêng.

`start` là tham số của method `counter`, được **capture** vì effectively final; còn `current` là instance field và được phép thay đổi mỗi khi gọi `getAsInt()`.

**Lưu ý:** method `getAsInt()` ở đây không có synchronization; nếu nhiều threads gọi cùng một supplier đồng thời, `current++` có thể race. Việc class vô danh không có tên không ảnh hưởng tới quy tắc concurrency của Java.

## 15. `this` bên trong anonymous class trỏ vào đâu?

Trong instance method của anonymous class, `this` là **chính anonymous-class object**, không phải enclosing object.

Nếu biểu thức `new ... { ... }` nằm trong instance method của một class `Outer`, `Outer.this` có thể trỏ tới enclosing Outer object khi ngữ cảnh cho phép.

~~~java
class Screen {
    private final String label = "outer";

    Runnable makeTask() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Screen.this.label);
            }
        };
    }
}
~~~

Đây là class minh họa hợp lệ, chưa có main. `this.label` lấy field anonymous object; `Screen.this.label` lấy private field của enclosing Screen. Không cần đổi field outer thành public vì quyền truy cập theo nesting rules cho phép.

Anonymous class **không tự là subclass của Screen**: nó triển khai Runnable. Quan hệ lexical nesting và quan hệ inheritance là hai khái niệm khác nhau.

## 16. Chương trình hoàn chỉnh 7 — shadowing giữa anonymous object và outer

Tạo tệp **`AnonymousThisDemo.java`**:

~~~java
final class Page {
    private final String label;

    Page(String label) {
        this.label = label;
    }

    Runnable action() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("this=" + this.label);
                System.out.println("outer=" + Page.this.label);
                System.out.println("anonymous="
                        + this.getClass().isAnonymousClass());
            }
        };
    }
}

public class AnonymousThisDemo {
    public static void main(String[] args) {
        Page page = new Page("home");
        Runnable action = page.action();
        action.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousThisDemo.java
java AnonymousThisDemo
~~~

**Stdout:**

~~~text
this=anonymous
outer=home
anonymous=true
~~~

`Page.this` chỉ tới đúng Page object đã gọi `action()`, còn `this` trong method `run()` chỉ anonymous Runnable.

Nếu creation expression nằm trong **static method** và không có enclosing Page instance hợp lệ, `Page.this` không khả dụng. Khi đó cần truyền reference Page tường minh nếu anonymous object phải truy cập instance state.

## 17. Capture biến local hoặc tham số: `final` và `effectively final`

Anonymous class có thể dùng local variables và parameters từ phạm vi bao khi chúng **final hoặc effectively final**, và được khởi tạo hợp lệ.

~~~java
static Runnable printTimes(String message) {
    int repeats = 2;

    return new Runnable() {
        @Override
        public void run() {
            for (int i = 0; i < repeats; i++) {
                System.out.println(message);
            }
        }
    };
}
~~~

Đây là method minh họa hợp lệ khi đặt trong một class. `message` là parameter, `repeats` là local variable: cả hai không bị gán lại nên effectively final.

**Không hợp lệ** nếu code bắt anonymous body đọc `count` mà method cũng gán lại count:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
int count = 1;
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println(count);
    }
};
count++;
~~~

Vì `count++` cập nhật biến local được capture, compiler từ chối. Việc update đặt **sau** anonymous expression không tránh được điều kiện compile-time.

Để chuẩn hóa input, nên viết `String normalized = input.trim();` rồi capture `normalized` thay vì gán lại chính biến tham số `input`.

## 18. Chương trình hoàn chỉnh 8 — capture và vòng đời sau khi method trả về

Tạo tệp **`AnonymousCaptureDemo.java`**:

~~~java
public class AnonymousCaptureDemo {
    static Runnable greet(String raw, int times) {
        if (raw == null || times < 0) {
            throw new IllegalArgumentException("invalid argument");
        }
        String message = raw.trim();

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < times; i++) {
                    System.out.println(message + "#" + i);
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = greet(" An ", 2);
        Runnable second = greet(" Binh ", 1);

        first.run();
        second.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

**Stdout:**

~~~text
An#0
An#1
Binh#0
~~~

Các Runnable vẫn chạy sau khi `greet` đã trả về. Java bảo đảm các captured values còn dùng được, dù local stack frame của lần gọi method đã kết thúc.

**Không suy** rằng anonymous object giữ một biến local có thể được gán lại ở nơi khác. Nó được phép giữ **giá trị của biến được capture**; nếu giá trị ấy là reference tới object mutable, state bên trong object vẫn có thể thay đổi qua các aliases.

## 19. Final reference không làm object mà nó trỏ tới bất biến

Một ví dụ:

~~~java
StringBuilder text = new StringBuilder("A");

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(text.toString());
    }
};

text.append("B");
task.run();
~~~

Đây là snippet hợp lệ trong method, in `AB`. Biến local `text` vẫn effectively final vì **không bị gán lại**, dù `StringBuilder` được sửa bằng `append`.

Phân biệt hai việc:

| Thao tác | Có phá effectively final của reference? |
| --- | --- |
| `text = new StringBuilder(...)` | Có |
| `text.append("x")` | Không |
| `list.add("x")` | Không |
| `array[0] = 5` | Không |
| `index++` khi capture index | Có |
| `final int constant = 5;` | Không thể gán lại constant |

Anonymous class **không tự tạo snapshot bất biến** của object đích. Nếu cần ổn định nội dung, hãy chuyển builder thành một `String` trước khi capture; nếu cần shared mutable state đa luồng, dùng synchronization hoặc concurrency primitives phù hợp.

## 20. Chương trình hoàn chỉnh 9 — capture mutable reference

Tạo tệp **`AnonymousMutableCaptureDemo.java`**:

~~~java
public class AnonymousMutableCaptureDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");

        Runnable reader = new Runnable() {
            @Override
            public void run() {
                System.out.println("value=" + source);
            }
        };

        reader.run();
        source.append("B");
        reader.run();

        String snapshot = source.toString();
        Runnable frozen = new Runnable() {
            @Override
            public void run() {
                System.out.println("snapshot=" + snapshot);
            }
        };

        source.append("C");
        frozen.run();
        reader.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousMutableCaptureDemo.java
java AnonymousMutableCaptureDemo
~~~

**Stdout:**

~~~text
value=A
value=AB
snapshot=AB
value=ABC
~~~

Reader giữ reference đến cùng `StringBuilder`, nên quan sát các lần mutate. Frozen giữ `String snapshot`, là immutable value được tạo ở thời điểm `source` có nội dung AB. Những lần sửa source sau đó không ảnh hưởng snapshot.

**Lưu ý concurrency:** `StringBuilder` không được bảo đảm thread-safe. Việc capture một effectively final reference không tự bảo vệ các thao tác khi object ấy bị truy cập đồng thời.

## 21. Vòng lặp và mỗi lần đánh giá biểu thức tạo object

Biểu thức `new Runnable() { ... }` có thể được đánh giá nhiều lần (ví dụ bên trong `for`), tạo nhiều **instances** của **cùng một anonymous class declaration** nếu cùng biểu thức source.

Với `for (int i = 0; i < 3; i++)`, biến `i` không effectively final vì `i++`. Không được capture trực tiếp `i` trong anonymous body. Cần một biến snapshot cho từng iteration:

~~~java
for (int i = 0; i < 3; i++) {
    int index = i;

    tasks.add(new Runnable() {
        @Override
        public void run() {
            System.out.println(index);
        }
    });
}
~~~

Đây là snippet hợp lệ khi `tasks` là collection of Runnable và các imports thích hợp. Mỗi lần chạy loop body tạo một `index` mới với giá trị tương ứng; nó effectively final và có thể được capture.

Điểm tinh tế:

- **Class declaration** nằm ở cùng một vị trí source code trong vòng lặp.
- **Mỗi lần new** vẫn tạo một instance khác.
- Các instances có thể cùng runtime class nhưng giữ những **captured values khác nhau**.
- Muốn kiểm tra `getClass()==`, phải dùng **cùng anonymous class expression**, không phải hai expressions ở hai dòng khác nhau.

## 22. Chương trình hoàn chỉnh 10 — nhiều instances từ một anonymous expression

Tạo tệp **`AnonymousLoopInstancesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousLoopInstancesDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int capturedIndex = i;

            tasks.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("index=" + capturedIndex);
                }
            });
        }

        System.out.println("size=" + tasks.size());
        System.out.println("same instance="
                + (tasks.get(0) == tasks.get(1)));
        System.out.println("same runtime class="
                + (tasks.get(0).getClass()
                   == tasks.get(1).getClass()));

        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousLoopInstancesDemo.java
java AnonymousLoopInstancesDemo
~~~

**Stdout:**

~~~text
size=3
same instance=false
same runtime class=true
index=0
index=1
index=2
~~~

Ba đối tượng khác identity, nhưng được tạo từ **cùng một anonymous class declaration** nên có cùng runtime class trong chương trình này. Mỗi instance mang capturedIndex riêng theo lần thực thi biểu thức.

Hãy phân biệt **class identity** và **object identity**, nhất là khi học anonymous classes và khi debug class metadata.

## 23. `getClass()`: vô danh ở source không có nghĩa vô hình ở JVM

Anonymous class có runtime class nên các method reflection của `Class` vẫn dùng được:

- `getClass().isAnonymousClass()`: nhận diện anonymous class.
- `getClass().getSuperclass()`: trả superclass trực tiếp.
- `getClass().getInterfaces()`: trả các interfaces trực tiếp.
- `getClass().getSimpleName()`: với anonymous class, tên đơn giản là **chuỗi rỗng**.
- `getClass().getName()`: tên binary có thể chứa `$` và số thứ tự do compiler cung cấp, **không nên dùng làm business identifier**.

Nếu một anonymous class implements Runnable, runtime class thường có superclass là Object và một interface trực tiếp là Runnable. Nếu nó extends Base, superclass là Base.

Đừng viết logic phụ thuộc vào `Outer$1`, `Outer$2` hay số thứ tự compiler-generated: thay đổi source/biên dịch có thể làm tên khác đi.

## 24. Chương trình hoàn chỉnh 11 — kiểm tra metadata an toàn

Tạo tệp **`AnonymousMetadataDemo.java`**:

~~~java
public class AnonymousMetadataDemo {
    public static void main(String[] args) {
        Runnable first = new Runnable() {
            @Override
            public void run() {
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
            }
        };

        Class<?> type = first.getClass();

        System.out.println("anonymous=" + type.isAnonymousClass());
        System.out.println("simple empty="
                + type.getSimpleName().isEmpty());
        System.out.println("super is Object="
                + (type.getSuperclass() == Object.class));
        System.out.println("interface Runnable="
                + (type.getInterfaces()[0] == Runnable.class));
        System.out.println("different classes="
                + (first.getClass() != second.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousMetadataDemo.java
java AnonymousMetadataDemo
~~~

**Stdout chính xác:**

~~~text
anonymous=true
simple empty=true
super is Object=true
interface Runnable=true
different classes=true
~~~

Ở đây `first` và `second` đến từ **hai expressions khai báo class khác nhau**, nên runtime classes cũng khác nhau. Điều này **không mâu thuẫn** với ví dụ loop trước: trong loop, mỗi instance xuất phát từ **cùng một declaration**.

Đoạn mã tránh in compiler-generated binary names, vì chúng không phải nội dung mà API nên phụ thuộc lâu dài.

## 25. Anonymous class và lambda: giống nơi dùng, khác ngữ nghĩa

Kể từ Java 8, functional interfaces như Runnable thường có thể dùng lambda:

~~~java
Runnable lambda = () -> System.out.println("Hello");
~~~

hoặc anonymous class:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
~~~

Hai đoạn là snippets trong method, nhưng **không đồng nghĩa mọi hành vi hoàn toàn giống nhau**.

| Tiêu chí | Anonymous class | Lambda |
| --- | --- | --- |
| Cú pháp chính | `new Interface() { ... }` | `() -> ...` |
| Trực tiếp dùng với functional interface? | Có | Có |
| Dùng với interface có nhiều abstract methods? | Có, implement đủ methods | Không |
| Anonymous body có riêng instance field? | Có | Không có class body để khai báo field như vậy |
| `this` trong thân | Anonymous object | `this` lexical của nơi chứa lambda |
| Có thể extends một non-final class? | Có | Không dùng lambda để extends class |
| Runtime class-name ổn định cho app? | Không | Cũng không nên dựa vào |
| Capture locals/parameters | Final/effectively final | Final/effectively final |
| Có nhiều overridden methods? | Có theo hợp đồng type | Lambda triển khai một abstract method |
| Độ dài boilerplate khi chỉ in một dòng | Dài | Ngắn |

**Khuyến nghị:** với một hành vi ngắn cho functional interface, lambda thường rõ hơn. Khi cần anonymous **subclass của class**, nhiều methods hoặc instance fields gắn với một object, anonymous class vẫn hữu ích.

## 26. Khi chuyển anonymous callback sang lambda, `this` có còn là cùng receiver?

Bài nhập môn chỉ cần một phép phân biệt: trong **instance method** của lớp vô danh, `this` chỉ **anonymous object**; trong lambda được viết từ instance method của `Host`, `this` chỉ **Host object** theo lexical scope. Đây không phải một cách viết ngắn hơn mà không thay đổi semantics.

Đoạn **snippet đặt bên trong một instance method của Host**:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.getClass().isAnonymousClass());
    }
};

Runnable lambda = () -> {
    System.out.println(this.getClass().getSimpleName());
};
~~~

Nếu Host chính là runtime class của enclosing instance, callback vô danh in `true`, còn lambda in `Host`. Mục này chỉ giới thiệu cảnh báo về receiver; các chương trình hoàn chỉnh, bảng scope và kiểm chứng `Outer.this` nằm ở bài chuyên biệt “Ý nghĩa this và truy cập đối tượng bao ngoài” và “So sánh lớp vô danh với lambda ở phạm vi sử dụng và this”.

**Tiêu chí refactor:** chỉ đổi sang lambda sau khi chắc chắn body không dựa vào `this` của anonymous callback, `super` của anonymous subclass hoặc fields/methods riêng của lớp vô danh.

## 27. Anonymous class và local class có tên

**Local class** được khai báo trong block method với một tên:

~~~java
void execute() {
    class Task implements Runnable {
        @Override
        public void run() {
            System.out.println("local");
        }
    }

    Runnable task = new Task();
    task.run();
}
~~~

Đây là **method minh họa hợp lệ** khi đặt trong class.

Anonymous class viết cùng implementation tại chỗ:

~~~java
void execute() {
    Runnable task = new Runnable() {
        @Override
        public void run() {
            System.out.println("anonymous");
        }
    };
    task.run();
}
~~~

**Khác biệt chính:** local class có một **tên kiểu trong scope của block** nên có thể tạo nhiều instances bằng `new Task()` từ những vị trí hợp lệ và tổ chức nhiều method/fields dưới tên đó. Anonymous class **không có tên source-level**, nên implementation và creation nằm cùng biểu thức.

Cả hai vẫn có thể sử dụng captured variables final/effectively final từ scope bao và có những quy tắc enclosing-instance tương ứng.

Một implementation được sử dụng nhiều lần, có logic đáng kể và xứng đáng đặt tên? Local class hoặc member class có thể dễ bảo trì hơn anonymous body dài.

## 28. Sử dụng Comparator vô danh với collection

Một ứng dụng phổ biến của anonymous class là cung cấp một comparator ngay tại phép sắp xếp:

~~~java
List<String> words = new ArrayList<>(
        List.of("bbbb", "a", "ccc", "bb"));

words.sort(new Comparator<String>() {
    @Override
    public int compare(String left, String right) {
        int byLength =
                Integer.compare(left.length(), right.length());
        return byLength != 0
                ? byLength : left.compareTo(right);
    }
});
~~~

Đây là snippet hợp lệ khi đặt trong method và import `List`, `ArrayList`, `Comparator`.

`Comparator<String>` có abstract method `compare`, và anonymous class implement nó. Quy tắc sắp xếp là theo **độ dài tăng dần**, nếu bằng độ dài thì theo **thứ tự từ điển tự nhiên của String**.

Đừng dùng `left.length() - right.length()` cho những số nguyên tổng quát có nguy cơ overflow; `Integer.compare(...)` diễn đạt ý định an toàn hơn.

## 29. Chương trình hoàn chỉnh 12 — sắp xếp bằng Comparator vô danh

Tạo tệp **`AnonymousComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AnonymousComparatorDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("bbbb", "a", "ccc", "bb"));

        words.sort(new Comparator<String>() {
            @Override
            public int compare(String left, String right) {
                int length = Integer.compare(
                        left.length(), right.length());
                return length != 0
                        ? length : left.compareTo(right);
            }
        });

        System.out.println(words);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousComparatorDemo.java
java AnonymousComparatorDemo
~~~

**Stdout:**

~~~text
[a, bb, ccc, bbbb]
~~~

Không có class `LengthComparator` đặt tên riêng trong source. Dù vậy, collection nhận được một Comparator **object thực sự**. Nếu chính comparator được dùng ở nhiều nơi hoặc có logic nghiệp vụ dài, đưa nó thành named class, static factory hoặc static constant sẽ rõ hơn.

Với Java 17, có thể dùng `Comparator.comparingInt(String::length).thenComparing(...)`, nhưng cú pháp anonymous class vẫn quan trọng khi đọc Java code cũ và hiểu object-oriented dispatch.

## 30. Anonymous Runnable và Thread: tạo object không tự chạy đa luồng

Hai thao tác sau **khác nhau**:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("working");
    }
};
task.run();
~~~

`task.run()` là lời gọi method **đồng bộ trên thread hiện tại**.

Nếu muốn thực thi Runnable trên **thread mới**, ta cung cấp nó cho Thread:

~~~java
Thread worker = new Thread(new Runnable() {
    @Override
    public void run() {
        System.out.println("working");
    }
});
worker.start();
~~~

Đây là hai snippets trong method. `worker.start()` mới yêu cầu bắt đầu một thread theo Thread API. **Không có phép thuật concurrency** nào được kích hoạt chỉ bởi `new Runnable() { ... }`.

Để có stdout xác định khi minh họa, chương trình đầy đủ cần chờ thread kết thúc bằng `join()` trước khi in dòng tiếp theo ở main.

## 31. Chương trình hoàn chỉnh 13 — truyền anonymous Runnable vào Thread

Tạo tệp **`AnonymousThreadDemo.java`**:

~~~java
public class AnonymousThreadDemo {
    public static void main(String[] args)
            throws InterruptedException {
        String message = "task done";

        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                System.out.println(message);
            }
        });

        worker.start();
        worker.join();
        System.out.println("main done");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousThreadDemo.java
java AnonymousThreadDemo
~~~

**Stdout (khi thread chạy thành công):**

~~~text
task done
main done
~~~

`message` effectively final nên anonymous class capture được. `worker.join()` làm main đợi worker kết thúc trước khi in `main done`, nhờ đó thứ tự hai dòng được xác định trong chương trình.

Trong ứng dụng thật, một anonymous Runnable có thể được giao cho executor, callback hoặc event loop. Khi đó cần hiểu API nào **thực sự gọi** `run()` hoặc method khác, tại thread nào, và khi nào.

## 32. Kỹ thuật ẩn implementation qua factory trả interface

Khi một anonymous class chỉ là implementation detail của một method, method có thể trả về interface:

~~~java
interface IntRule {
    boolean matches(int value);
}

final class Rules {
    private Rules() {
    }

    static IntRule atLeast(int threshold) {
        return new IntRule() {
            @Override
            public boolean matches(int value) {
                return value >= threshold;
            }
        };
    }
}
~~~

Đây là những định nghĩa Java hợp lệ, chưa có main. Caller chỉ cần dùng `IntRule`, không biết hoặc cần biết tên compiler-generated anonymous class.

**Ưu điểm:** không xuất bản thêm class tên riêng chỉ dùng bên trong một factory, nhưng vẫn cung cấp một object với hợp đồng interface rõ. **Nhược điểm:** khi implementation phình to, code lồng trong method có thể khó đọc và test độc lập hơn một named class.

Dữ liệu `threshold` được capture một cách an toàn ở **mức giá trị primitive** vì tham số không bị gán lại. Nếu capture mutable reference, cần phân tích ownership riêng.

## 33. Chương trình hoàn chỉnh 14 — factory trả interface

Tạo tệp **`AnonymousFactoryDemo.java`**:

~~~java
interface IntRule {
    boolean matches(int value);
}

final class Rules {
    private Rules() {
    }

    static IntRule atLeast(int threshold) {
        return new IntRule() {
            @Override
            public boolean matches(int value) {
                return value >= threshold;
            }
        };
    }
}

public class AnonymousFactoryDemo {
    public static void main(String[] args) {
        IntRule adult = Rules.atLeast(18);
        IntRule positive = Rules.atLeast(1);

        System.out.println("adult 17=" + adult.matches(17));
        System.out.println("adult 20=" + adult.matches(20));
        System.out.println("positive 2="
                + positive.matches(2));
        System.out.println("different=" + (adult != positive));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousFactoryDemo.java
java AnonymousFactoryDemo
~~~

**Stdout:**

~~~text
adult 17=false
adult 20=true
positive 2=true
different=true
~~~

Hai lời gọi `Rules.atLeast(...)` tạo hai instances của cùng anonymous implementation được khai báo trong factory, nhưng capture **hai threshold khác nhau**.

Khi interface chỉ có một abstract method đơn giản, có thể viết factory ngắn gọn hơn bằng lambda. Anonymous class vẫn là một cách hợp lệ, đặc biệt nếu implementation cần nhiều methods hoặc instance fields.

## 34. Truy cập methods chỉ có ở anonymous implementation

Với:

~~~java
Object value = new Object() {
    String describe() {
        return "local";
    }
};
~~~

đây là snippet hợp lệ trong method. Nhưng **không thể** gọi `value.describe()` khi static type của biến là Object, vì Object không khai báo method `describe()`.

Trường hợp `var` trong Java 10+ có một điểm thú vị:

~~~java
var local = new Object() {
    String describe() {
        return "local";
    }
};

System.out.println(local.describe());
~~~

Đây là đoạn hợp lệ trong method ở Java 17, vì compiler suy ra kiểu của `local` từ biểu thức khởi tạo và có thể cho phép truy cập method tương ứng trong phạm vi ấy.

**Không nên lấy trường hợp `var` làm cách xây dựng API công khai**. Anonymous class không có tên ở source, và local variable type inference có những quy tắc riêng; nếu caller cần gọi một method, nên định nghĩa nó trên **interface hoặc superclass được công bố**, thay vì dựa vào method chỉ tồn tại ở một anonymous implementation.

## 35. Chương trình hoàn chỉnh 15 — `var` và phương thức bổ sung

Tạo tệp **`AnonymousVarDemo.java`**:

~~~java
public class AnonymousVarDemo {
    public static void main(String[] args) {
        var local = new Object() {
            String describe() {
                return "extra method";
            }
        };

        Object wide = local;

        System.out.println("local=" + local.describe());
        System.out.println("wide anonymous="
                + wide.getClass().isAnonymousClass());
        System.out.println("same=" + (local == wide));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousVarDemo.java
java AnonymousVarDemo
~~~

**Stdout:**

~~~text
local=extra method
wide anonymous=true
same=true
~~~

Đây là **trường hợp chuyên biệt** của local variable type inference, không thay đổi quy tắc rằng `Object wide` không có method `describe()` tại compile time.

Dù cùng reference, những methods có thể gọi trực tiếp phụ thuộc **static type** của biểu thức ở từng vị trí. Anonymous runtime type không có nghĩa mọi reference Object sẽ tự truy cập được những method riêng ấy.

## 36. Anonymous class không thể mở rộng một `final` class

Khi một class được khai báo `final`, không class nào được kế thừa nó, kể cả anonymous class.

~~~java
final class Closed {
}
~~~

Đoạn **cố ý không biên dịch** nếu thêm vào method:

~~~java
// Object bad = new Closed() { };
~~~

Class body dù rỗng vẫn đang yêu cầu **khai báo subclass vô danh của Closed**, nên vi phạm final class restriction.

Đừng nhầm với việc tạo một object Closed bình thường:

~~~java
Closed okay = new Closed();
~~~

Đây là đoạn hợp lệ nếu constructor được quyền truy cập. **Không có class body**, nên không có anonymous subclass nào được khai báo.

Tương tự, `new String() { ... }` không hợp lệ vì String final; không thể override `String` bằng anonymous class.

## 37. Lỗi constructors, method signatures và `@Override`

Các lỗi compile-time thường gặp:

**Không có constructor phù hợp:**

~~~java
class Base {
    Base(int id) {
    }
}
~~~

Nếu gọi `new Base() { ... }`, việc không cung cấp tham số `int` gây lỗi, vì Base không có constructor không tham số có thể gọi.

**Method được override là final:**

~~~java
class Base {
    final void locked() {
    }
}
~~~

Không thể dùng `new Base() { @Override void locked() {} }` để override locked.

**Method private của superclass không được override:**

~~~java
class Base {
    private void secret() {
    }
}
~~~

Một method cùng tên/signature bên anonymous subclass **không override** private method từ Base. Nếu bạn thêm `@Override` trên method ấy khi không có method thích hợp khác để override, compiler báo lỗi.

**Interface method phải dùng quyền truy cập đúng:** khi implement `Runnable.run()`, method phải là `public void run()`; không được giảm visibility thành package-private hoặc private.

Các ví dụ trong mục này là **định nghĩa/snippets minh họa độc lập**, không ghép ba class tên Base vào cùng file.

## 38. `new Interface() { ... }` không phải gọi constructor của interface

Java interface **không có constructor instance**. Vì vậy:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

không có nghĩa bạn đang “khởi tạo interface Runnable”. Bạn đang tạo **một class vô danh implements Runnable**; mọi object trong Java đều là instance của một concrete class nào đó, kể cả khi reference được gán vào interface type.

Lỗi tư duy thường gặp:

- “Interface không được new, vậy cú pháp này đáng ra sai.” → Không: có anonymous class body, vì thế đó là object của **một implementation class vô danh**.
- “Cần viết `implements Runnable` phía sau.” → Không: `new Runnable() { ... }` đã cung cấp tên superinterface.
- “Method run tự chạy ngay.” → Không: tạo object không tự gọi run.
- “Không có class nên không có state.” → Không: anonymous class có thể có instance fields.
- “Mọi interface đều được dùng với lambda.” → Không: lambda cần functional interface, còn anonymous class có thể implement nhiều abstract methods.

## 39. Một số ràng buộc của anonymous class body

Một anonymous class **không có source-level name và không khai báo constructor có tên**. Nó có thể khai báo fields, instance methods, instance initializer blocks và những nested declarations hợp lệ theo Java 17.

Anonymous class có các giới hạn từ ngữ cảnh:

- Không thể `extends` một final class.
- Không thể khai báo trực tiếp rằng anonymous class extends hai classes (Java không đa kế thừa class).
- Không viết `implements A, B` thêm sau `new X() { ... }` như cú pháp khai báo class có tên.
- Phải tuân access của superclass constructor và các abstract methods còn lại.
- Không được giảm visibility khi implement public interface methods.
- Không được override methods final/private theo cách trái JLS.
- Các locals/parameters được capture phải final/effectively final.
- Constructor riêng có tên không thể xuất hiện vì anonymous class không có tên nguồn.
- Modifier `static` trên members vẫn chịu quy tắc dành cho inner classes và static contexts trong Java 17, không được tùy tiện khai báo mọi static state trong anonymous class.

Nếu implementation có quá nhiều trách nhiệm, nên chuyển sang local class có tên, static nested class hoặc top-level class. Anonymous class phù hợp với **logic tập trung tại vị trí sử dụng**, không phải để giấu cả một subsystem.

## 40. Không dùng anonymous class như một subclass chỉ để truy cập field private

Nesting và inheritance là hai quan hệ khác nhau:

- Một anonymous class được khai báo **bên trong instance method** của Outer có thể truy cập private state của enclosing Outer khi ngữ cảnh cho phép.
- Một anonymous subclass **kế thừa từ Base** không tự có quyền đọc private fields của Base theo inheritance. Dùng protected/public API thích hợp.
- Một anonymous class được tạo trong static method không tự có `Outer.this`.
- Dùng reflection để phá encapsulation không phải phương pháp chính thống thay cho thiết kế API.

Ví dụ ở mục 10, `Greeting` có `private String name`; anonymous subclass gọi `protected final String name()`, **không đọc `name` trực tiếp** chỉ vì nó là subclass. Đây là ví dụ tách đúng quyền member khỏi quan hệ subclass.

Nếu anonymous class được khai báo **lexically trong chính Greeting** thì nesting access rules có thể cho quyền khác. Hãy xét **vị trí khai báo cụ thể**, không chỉ tên subtype.

## 41. Side effects và vòng đời của anonymous objects

Một anonymous object có thể được:

- Dùng ngay rồi không còn reference, ví dụ `new Runnable(){...}.run()`.
- Giữ trong biến local.
- Trả ra qua factory/interface.
- Lưu vào collection/listener registry.
- Truyền cho Thread/Executor, có thể sống lâu hơn method tạo ra nó.

Nếu anonymous object **capture một reference tới một object lớn** hoặc tới enclosing Outer, nó có thể kéo dài reachability của object ấy. Đây không phải lỗi ngôn ngữ tự động, nhưng là điều cần xét khi thiết kế callback lâu dài.

Không suy rằng anonymous class tự bị thu hồi sau một lần gọi method. GC dựa trên **reachability**, không dựa vào việc class có tên hay không.

Cũng không suy rằng field mutable bên trong anonymous class đã được quản lý thread-safe: state và synchronization vẫn do bạn thiết kế.

## 42. Khi nào nên chọn anonymous, lambda, local class có tên, nested class?

| Nhu cầu | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Một hành vi ngắn của functional interface | Lambda | Ngắn gọn, mô tả hành vi trực tiếp |
| Override một method trên non-final class ngay tại điểm dùng | Anonymous class | Không cần class có tên chỉ để tùy biến |
| Interface có nhiều abstract methods | Anonymous hoặc named class | Lambda không cung cấp trực tiếp nhiều methods |
| Implementation cục bộ có nhiều fields/methods cần tên | Local class có tên | Dễ đọc/tạo nhiều instances từ type local |
| Helper/Builder liên quan lâu dài đến Outer | Static nested/member class | API, visibility và ownership rõ |
| Kiểu dùng rộng rãi ở nhiều nơi | Top-level/named class | Dễ reuse, test, documentation |
| Callback chỉ dùng trong một lời gọi và khá nhỏ | Anonymous class hoặc lambda | Code gần nơi dùng |
| Service/domain object lớn với nhiều invariants | Named class | Tránh anonymous body quá dài khó kiểm chứng |

Một tiêu chí thực tế: **anonymous class nên làm code dễ đọc hơn**, không phải ngắn hơn bằng mọi giá. Nếu phải cuộn qua hàng trăm dòng để tìm logic bên ngoài một anonymous expression, hãy cân nhắc tách class.

## 43. Những sai lầm và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `new Runnable()` mà không có class body | Interface không có instance constructor | Dùng `new Runnable(){ public void run(){...} }` |
| Bỏ `run()` hoặc sai signature | Không implement đủ abstract method | Dùng `@Override` và signature chính xác |
| Dùng `void run()` không public | Không được giảm visibility interface method | `public void run()` |
| Nghĩ `new Runnable(){...}` tự chạy | Creation khác invocation | Gọi `run()` hoặc API quản lý task |
| Coi anonymous object là singleton | Mỗi biểu thức new được đánh giá tạo instance | Chỉ chia sẻ khi cố ý lưu cùng reference |
| Lấy `this` làm Outer | `this` trong anonymous body là anonymous object | Dùng `Outer.this` khi hợp lệ |
| Gán lại local được capture | Không effectively final | Snapshot vào local mới |
| Capture StringBuilder rồi mong snapshot cố định | Object đích mutable | Capture String bất biến đã tạo |
| Anonymous implementation cần gọi method riêng qua Runnable ref | Static type không khai method ấy | Công bố interface đúng hoặc API có tên |
| Dùng anonymous subclass của final class | Không cho phép extends | Tạo object thông thường hoặc composition |
| Nghĩ anonymous extends class chạy constructor do mình đặt trong body | Anonymous không có constructor khai báo riêng | Gọi superclass constructor bằng args; dùng initializer phù hợp |
| Dùng lambda cho interface hai abstract methods | Không phải functional interface | Anonymous hoặc named class |
| So class names kiểu `Outer$1` | Tên sinh ra có thể thay đổi | Dùng interface/contracts/reflection APIs |
| Dùng counter field trên anonymous object ở nhiều threads mà không đồng bộ | Race condition | Atomic/synchronized/immutable state |
| Giữ callback lâu đời capture cả Outer không cần thiết | Retention/coupling | Chỉ giữ dữ liệu/dependency cần |
| Viết anonymous body quá lớn | Khó test, khó bảo trì | Local/nested/named class |

## 44. Quy trình đọc một biểu thức anonymous creation

Khi thấy code `new X(args) { ... }`:

1. **X là interface hay class?** Nếu interface, anonymous class implements X. Nếu class, anonymous class extends X.
2. **X có final không?** Nếu là final class thì không thể dùng anonymous subclass.
3. **Constructor nào được gọi?** Với class, xem overload/visibility của constructor X nhận args; với interface, ngoặc đơn rỗng.
4. **Những abstract methods nào phải cài?** Kiểm tra signature, access và `@Override`.
5. **Class body có fields/init blocks không?** Phân biệt thời điểm object construction và thời điểm gọi method.
6. **Reference trả về kiểu gì?** Static type quyết định những methods caller được phép gọi trực tiếp.
7. **Có capture local/parameter không?** Chúng phải final/effectively final, được definite assignment hợp lệ.
8. **`this` trỏ object nào?** Trong anonymous body, `this` là instance vô danh.
9. **Có `Outer.this` hợp lệ không?** Chỉ khi có enclosing instance thích hợp theo ngữ cảnh.
10. **Có mutable references được share không?** Capture không bảo đảm bất biến hay thread safety.
11. **Khi nào method được chạy?** Tạo object không tự gọi callback; API sử dụng quyết định thời điểm.
12. **Một declaration hay nhiều declarations?** Cùng expression lặp nhiều lần tạo instances của cùng runtime class; hai expressions khác nhau định nghĩa hai anonymous classes riêng.
13. **Có side effects/lifecycle dài hạn không?** Đánh giá object reachability, execution context và cleanup theo API.
14. **Kiểu nào dễ bảo trì nhất?** Nếu anonymous body dài hoặc cần reuse, đặt tên cho class hoặc dùng lambda thích hợp.

## 45. Bài tập tự luyện

**Câu 1.** Giải thích vì sao `new Runnable() { ... }` là hợp lệ dù interface Runnable không thể được khởi tạo trực tiếp.

**Câu 2.** Với `Runnable action = new Runnable() { public void run() {...} };`, hành vi `run()` có thực hiện ngay tại biểu thức new không?

**Câu 3.** Khi dùng `new InterfaceName() { ... }`, có được viết `implements InterfaceName` phía sau body không?

**Câu 4.** Anonymous class triển khai interface có hai abstract methods phải cài bao nhiêu method nếu không có implementation kế thừa phù hợp?

**Câu 5.** `new Base(10) { ... }` chọn constructor nào? Có thể tạo subclass vô danh nếu Base final không?

**Câu 6.** Có thể khai báo constructor mang tên class vô danh bên trong `{ ... }` không? Kể những cách khởi tạo fields thay thế.

**Câu 7.** `this` trong anonymous Runnable được tạo bên trong `Page.action()` chỉ đối tượng nào? `Page.this` chỉ đối tượng nào?

**Câu 8.** Một `Runnable` reference trỏ tới anonymous implementation có private method `help()`; có gọi `runnable.help()` từ ngoài được không?

**Câu 9.** `int n = 1;` được capture vào anonymous body; sau đó viết `n++`. Có biên dịch không?

**Câu 10.** Capture `StringBuilder builder`, rồi gọi `builder.append("x")`. Điều đó có làm biến builder mất effectively final không?

**Câu 11.** Một anonymous class declaration nằm trong vòng lặp được đánh giá ba lần. Có bao nhiêu instances? Chúng có thể cùng runtime class không?

**Câu 12.** Hai anonymous creation expressions viết ở hai vị trí source khác nhau nhưng cùng implements Runnable. Runtime classes có phải một không?

**Câu 13.** `getClass().getSimpleName()` của anonymous object thông thường trả gì? Có nên lưu `Outer$1` vào database như một định danh business không?

**Câu 14.** Anonymous class và lambda giống và khác nhau thế nào về `this`?

**Câu 15.** Vì sao lambda không thay thế được trực tiếp một anonymous subclass của abstract class `Greeting`?

**Câu 16.** Khi nào nên chuyển một anonymous implementation dài thành named local class hoặc static nested class?

**Câu 17.** Vì sao `new Runnable(){...}.run()` và `new Thread(new Runnable(){...}).start()` không tương đương?

**Câu 18.** Nếu một anonymous class capture `ArrayList` rồi hai threads cùng sửa list ấy, effectively final có làm code an toàn không?

**Câu 19.** Với `var local = new Object(){ String describe(){...} };`, Java 17 cho `local.describe()` ở chỗ khai báo thích hợp. Vì sao biến `Object wide = local` không cho gọi `wide.describe()` trực tiếp?

**Câu 20.** Một factory trả `IntRule` bằng anonymous class. Caller có cần biết tên bytecode implementation để gọi `matches()` không?

**Câu 21.** Đâu là thời điểm instance initializer trong anonymous class chạy so với superclass constructor và so với `run()` sau đó?

**Câu 22.** Anonymous class có thể khai báo instance fields khác nhau cho mỗi object không?

**Câu 23.** `@Override` giúp phát hiện loại lỗi nào khi implement `Runnable.run()`?

**Câu 24.** Nếu một anonymous Runnable được đăng ký vào listener registry sống lâu và capture Outer object, hậu quả có thể là gì?

### Đáp án tham khảo

1. Vì biểu thức tạo instance của **lớp vô danh implements Runnable**, không tạo một object interface trừu tượng.
2. Không; new tạo object. `run()` chỉ thực hiện khi được gọi hoặc bởi API dùng object.
3. Không; cú pháp new-interface kèm anonymous class body đã chỉ định superinterface.
4. Hai, nếu cả hai là abstract methods chưa được implement.
5. Gọi constructor Base phù hợp với đối số 10; nếu Base final thì không thể extends bằng anonymous class.
6. Không; dùng superclass constructor args, field initializer, instance initializer hoặc captured values.
7. `this` là anonymous object; `Page.this` là enclosing Page instance thích hợp.
8. Không qua static type Runnable; interface không có help và helper lại private.
9. Không; `n++` làm n không effectively final.
10. Không. Builder reference không bị gán lại, chỉ object đích mutate.
11. Ba instances; nếu cùng một expression/declaration, có thể cùng runtime class.
12. Không; hai anonymous class declarations riêng biệt, dù cùng superinterface.
13. Chuỗi rỗng; không dựa vào compiler-generated binary name làm business ID.
14. Cùng có thể capture final/effectively final; `this` của anonymous là anonymous object, `this` trong lambda dùng lexical enclosing context.
15. Lambda hiện thực functional interface, không extends một class tùy ý.
16. Khi logic lớn, nhiều responsibilities, cần reuse, test hoặc public contract rõ hơn.
17. Gọi `run()` trực tiếp trên thread hiện tại khác với `Thread.start()` tạo execution thread theo API.
18. Không; List mutable cần bảo vệ concurrency riêng.
19. Static type của wide là Object, nên không có method describe trong API Object; local var suy ra kiểu expression chuyên biệt.
20. Không; caller làm việc qua `IntRule.matches`.
21. Superclass constructor chạy trước phần khởi tạo instance của anonymous subclass; `run()` chỉ chạy về sau khi được gọi.
22. Có; mỗi object có bộ instance fields riêng.
23. Sai tên/signature, hoặc method không thật sự override method phù hợp, được phát hiện lúc compile.
24. Registry có thể giữ anonymous object và các references mà nó giữ/capture còn reachable lâu hơn dự kiến, gây retention/coupling.

## 46. Checklist trước khi đưa anonymous class vào chương trình

- Đã xác định `new X(args) { ... }` extends class hay implements interface?
- X không phải final class khi cần anonymous subclass?
- Constructor args có phù hợp nếu X là superclass?
- Các abstract methods đã được implement chính xác, với visibility thích hợp?
- Có dùng `@Override` cho các methods cần override?
- Anonymous class body có fields/initializers được thiết kế rõ và hợp lệ?
- Biến được capture có final/effectively final và definite assignment không?
- Có phân biệt việc tạo object với việc gọi callback method?
- Nếu có outer instance, đã phân biệt `this` với `Outer.this`?
- Có tránh phụ thuộc compiler-generated anonymous binary name?
- Interface/superclass trả về có công bố đủ methods caller cần?
- Nếu cần state giữa các lần callback, đã chọn instance field thay vì gán lại captured local?
- Nếu capture object mutable, đã phân tích aliasing và concurrency?
- Có hiểu một expression lặp tạo nhiều instances cùng một anonymous class?
- Anonymous implementation có ngắn, gần điểm sử dụng và dễ hiểu?
- Nếu implementation lớn, đã cân nhắc named local/member class?
- Nếu functional interface đơn giản, đã cân nhắc lambda?
- Nếu callback sống lâu, đã cân nhắc retention và cleanup?
- Nếu dùng Thread/Executor, đã hiểu thread nào thực thi và quản lý lifecycle?
- Các ví dụ đã được biên dịch Java 17+ và stdout chỉ phản ánh thứ tự xác định?

## 47. Tài liệu Java 17 chính thức

- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): vị trí khai báo và ý nghĩa anonymous class body.
- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): ngữ pháp `new`, arguments và instance creation.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): anonymous inner classes và enclosing context.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final/effectively final captured variables.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): khởi tạo captured variables.
- [JLS 17 §8.4.8 — Inheritance, Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): hành vi override và visibility.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): so sánh lexical `this` và capture.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): hợp đồng `run()`.
- [Java SE 17 API — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparator objects và sorting.
- [Java SE 17 API — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): nhận diện runtime anonymous class.
- [Java SE 17 API — Class.getSimpleName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getSimpleName()): simple names cho classes.
- [Java SE 17 API — Thread.start](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#start()): thực thi task trên thread.
- [Java SE 17 API — Thread.join](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#join()): đợi thread kết thúc.

**Tổng kết:** biểu thức `new Interface() { ... }` hoặc `new Base(args) { ... }` cho phép **khai báo lớp vô danh và khởi tạo object trong cùng một bước của source code**. Implementation vẫn là một class có instance state, constructors kế thừa theo quy tắc và runtime identity; không phải chỉ là một hàm hay một instance của interface trừu tượng. Hãy dùng anonymous class khi hành vi cần tùy biến ngay tại nơi sử dụng, nhất là callback nhiều methods hoặc anonymous subclass. Đồng thời kiểm soát **`this`**, captured variables, object lifetimes, thread safety và static type của reference. Nếu implementation đơn giản thuộc functional interface, lambda thường ngắn hơn; nếu implementation lớn hoặc được tái sử dụng, một class có tên sẽ dễ quản lý hơn.
