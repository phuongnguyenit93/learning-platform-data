# Lớp cục bộ trong ngữ cảnh static và ngữ cảnh đối tượng — Java 17+

**Local class (lớp cục bộ)** là một lớp có tên được khai báo trong một block, chẳng hạn thân phương thức, constructor, instance initializer hoặc static initializer. **Cùng là local class nhưng môi trường khai báo quyết định nó có thể truy cập đối tượng bao ngoài (`Outer.this`) hay không.**

- Trong **ngữ cảnh đối tượng (instance context)** của `Outer`, local class có thể truy cập instance fields/methods của đối tượng `Outer` hiện tại và dùng `Outer.this`.
- Trong **ngữ cảnh `static`**, không tồn tại một receiver `Outer.this` ngầm định. Local class vẫn có thể truy cập static members và bắt giữ các local variables/parameters đủ điều kiện.
- Cả hai ngữ cảnh đều có quy tắc capture: local variables hoặc parameters được local class sử dụng phải **`final` hoặc `effectively final`**; điều này không có nghĩa object được tham chiếu trở thành bất biến.

Ví dụ đối chiếu:

~~~java
class Counter {
    private int count = 10;
    private static int seed = 100;

    int instanceExample(int delta) {
        class InstanceLocal {
            int value() {
                return Counter.this.count + delta;
            }
        }
        return new InstanceLocal().value();
    }

    static int staticExample(int delta) {
        class StaticLocal {
            int value() {
                return seed + delta;
            }
        }
        return new StaticLocal().value();
    }
}
~~~

Method `instanceExample` có thể dùng `Counter.this.count`. Method `staticExample` không có `Counter.this`, nhưng đọc được `seed` vì đó là static field và `delta` vì parameter effectively final.

Bài thuộc **Java Core — Class & Object / Lớp cục bộ**, dùng Java 17+. Các ví dụ chạy độc lập ghi tên file, lệnh `javac`/`java` và stdout dự kiến. Đoạn lỗi biên dịch được **comment rõ** để không bị nhầm là chương trình chạy được.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt *lexical scope của local class* với *ngữ cảnh static/instance nơi khai báo*.
2. Khai báo và tạo local class object trong instance method.
3. Khai báo và tạo local class object trong static method.
4. Dùng `Outer.this` chỉ trong context có enclosing Outer instance.
5. Phân biệt `this` của local class với `Outer.this` của đối tượng bao ngoài.
6. Đọc đúng instance fields, static fields, instance methods và static methods.
7. Giải thích vì sao static method không tự biết đối tượng Outer nào để dùng.
8. Truyền explicit Outer reference khi logic static cần một object cụ thể.
9. Hiểu local class trong instance/static initializer blocks và constructor.
10. Phân biệt capture biến cục bộ với access outer instance fields.
11. Biết captured local phải final/effectively final, dù khai báo trong static hay instance method.
12. Phân biệt gán lại biến với mutate object được captured reference trỏ tới.
13. Hiểu vì sao outer instance fields có thể thay đổi dù captured method locals thì không được reassign.
14. Tránh nhầm static nested member class với local class khai báo trong static method.
15. Hiểu Java 17 cho phép static declarations trong inner/local classes theo quy tắc hiện hành.
16. Biết local record/enum là implicitly static và không capture enclosing instance như local class thông thường.
17. Phân biệt lambda `this` với local-class `this`.
18. Phân biệt local class trong generic static và generic instance methods.
19. Hiểu local class có thể thoát khỏi enclosing method qua interface reference.
20. Nhận biết memory retention, unsafe publication, thread safety và lifecycle.
21. Phân tích reflection `isLocalClass`, `getEnclosingMethod` và runtime identity.
22. Sửa các lỗi compiler phổ biến qua các bài tập dự đoán kết quả.

## 2. Hai nghĩa của “bao ngoài”

Cần tách **bao ngoài về cú pháp (lexical enclosure)** và **gắn với một đối tượng bao ngoài (enclosing instance)**.

Một local class trong `Outer.staticMethod()` vẫn được **viết bên trong source của Outer** và reflection có thể cho biết enclosing method là staticMethod. Nhưng local class ấy **không tự có một Outer object** để `Outer.this` trỏ tới.

Một local class trong `outer.instanceMethod()` có lexical context tương ứng với instance method và có thể tham chiếu `Outer.this` — tức đối tượng đã được dùng làm receiver của method invocation.

~~~text
Outer type
  |
  +--- instanceMethod()        [có receiver Outer.this]
  |      |
  |      +--- class LocalA    [có thể truy cập outer instance]
  |
  +--- staticMethod()          [không có Outer.this]
         |
         +--- class LocalB    [có thể truy cập static members]
~~~

“Static context” ở đây nói về **vùng code nơi declaration nằm**, không có nghĩa rằng `LocalB` biến thành một `static member class`. LocalB vẫn là local class, tên chỉ hợp lệ trong block; không thể gọi `new Outer.LocalB()` từ ngoài.

## 3. So sánh nhanh

| Khía cạnh | Local class trong instance context | Local class trong static context |
| --- | --- | --- |
| Có enclosing Outer instance ngầm định | Có, ở context phù hợp | Không |
| Dùng `Outer.this` | Có | Không |
| Đọc instance field của Outer không qua explicit reference | Có | Không |
| Đọc static field của Outer | Có | Có |
| Đọc local variable effectively final | Có | Có |
| Có fields/constructors/instance methods | Có | Có |
| Có tên như `Outer.Local` để dùng ngoài method | Không | Không |
| Được dùng `new Local()` trong scope sau declaration | Có | Có |
| Có thể trả object qua interface | Có | Có |
| Class metadata `isLocalClass()` | True | True |
| Automatically singleton hoặc một object mới mỗi declaration | Không | Không |
| Tự động thread-safe | Không | Không |

**Quy tắc mấu chốt:** Static method thuộc **class-level API**, không được gọi trên một receiver instance ngầm định. Bất cứ truy cập vào state của một Outer object nào ở static context đều cần **explicit reference** tới object đó.

## 4. Lớp cục bộ trong instance method

Xét:

~~~java
class Notebook {
    private final String name;

    Notebook(String name) {
        this.name = name;
    }

    String describe(int page) {
        class PageDescription {
            String text() {
                return Notebook.this.name + ":page=" + page;
            }
        }
        return new PageDescription().text();
    }
}
~~~

Trong `describe`:

- `this` khi ở thân `Notebook.describe` là Notebook receiver.
- `this` trong `PageDescription.text` là PageDescription object.
- `Notebook.this` bên trong PageDescription là Notebook receiver đã tạo ra local class object.
- `page` là method parameter effectively final được local class capture.

Không cần khai báo `Notebook` reference trong PageDescription constructor để dùng `Notebook.this`. Java định nghĩa enclosing-instance semantics cho local class trong instance context.

## 5. Chương trình chạy: instance method

Tạo **`InstanceContextDemo.java`**:

~~~java
public class InstanceContextDemo {
    static final class Notebook {
        private final String name;

        Notebook(String name) {
            this.name = name;
        }

        String describe(int page) {
            class PageDescription {
                String text() {
                    return Notebook.this.name + ":page=" + page;
                }
            }
            return new PageDescription().text();
        }
    }

    public static void main(String[] args) {
        Notebook first = new Notebook("Java");
        Notebook second = new Notebook("Algorithms");

        System.out.println(first.describe(3));
        System.out.println(second.describe(7));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceContextDemo.java
java InstanceContextDemo
~~~

Stdout:

~~~text
Java:page=3
Algorithms:page=7
~~~

Cùng một local class declaration `PageDescription` ở method describe, nhưng mỗi object sử dụng enclosing Notebook tương ứng với invocation đã tạo nó.

## 6. Lớp cục bộ trong static method

Static method không có receiver instance `Outer.this`. Ví dụ:

~~~java
class Notebook {
    private static final String PREFIX = "book:";

    static String label(String name) {
        class Formatter {
            String result() {
                return PREFIX + name;
            }
        }
        return new Formatter().result();
    }
}
~~~

Formatter có quyền truy cập `PREFIX` là static member; `name` là effectively final parameter. Nhưng Formatter **không thể** dùng `Notebook.this` vì nó được khai báo từ một static context.

### Chương trình chạy

Tạo **`StaticContextDemo.java`**:

~~~java
public class StaticContextDemo {
    private static final String PREFIX = "book:";

    static String label(String name) {
        class Formatter {
            String result() {
                return PREFIX + name;
            }
        }

        return new Formatter().result();
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label("Algorithms"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
book:Java
book:Algorithms
~~~

Code hợp lệ dù Formatter không gắn với một instance StaticContextDemo nào. `name` vẫn được capture theo từng method invocation.

## 7. Vì sao `Outer.this` sai trong static context?

Giả sử:

~~~java
class Outer {
    private int instanceValue = 7;

    static void method() {
        class Local {
            int wrong() {
                // return Outer.this.instanceValue; // Compile error.
                return 0;
            }
        }
    }
}
~~~

Method static được gọi bằng `Outer.method()`. Có thể chưa có bất kỳ Outer object nào, hoặc có nhiều Outer objects. Java không thể suy ra một receiver object duy nhất để `Outer.this` trỏ tới.

Tương tự:

~~~java
// return instanceValue; // Không hợp lệ ở static local context nếu không có receiver.
~~~

Đây là **lỗi ngữ cảnh**, không phải lỗi access modifier: ngay cả khi field là public, static method vẫn cần object reference để đọc một particular instance field.

## 8. Cần outer instance trong static method? Truyền reference tường minh

Nếu một static method phải xử lý state của một đối tượng, truyền nó qua parameter:

~~~java
class Outer {
    private final int value;

    Outer(int value) {
        this.value = value;
    }

    static int read(Outer target) {
        class Reader {
            int get() {
                return target.value;
            }
        }
        return new Reader().get();
    }
}
~~~

`target` là effectively final parameter và được capture. Lúc này Reader không có `Outer.this` ngầm định, nhưng nó có **một reference explicit** đến target và dùng reference đó để truy cập private field theo Java access rules.

Cần phân biệt:
- *Enclosing instance tự động*: `Outer.this` trong instance context.
- *Object dependency explicit*: `target` captured vào local class trong static context.

Hai cách có thể đọc cùng field nhưng có semantics ownership và lifetime khác nhau.

## 9. Chương trình chạy: explicit Outer reference trong static method

Tạo **`ExplicitReceiverDemo.java`**:

~~~java
public class ExplicitReceiverDemo {
    static final class Account {
        private final int number;

        Account(int number) {
            this.number = number;
        }

        static String describe(Account account) {
            class Reader {
                String read() {
                    return "account-" + account.number;
                }
            }
            return new Reader().read();
        }
    }

    public static void main(String[] args) {
        Account a = new Account(10);
        Account b = new Account(20);

        System.out.println(Account.describe(a));
        System.out.println(Account.describe(b));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitReceiverDemo.java
java ExplicitReceiverDemo
~~~

Stdout:

~~~text
account-10
account-20
~~~

Local Reader ở static method không có `Account.this`. Nó tham chiếu vào **account parameter**, nên caller quyết định Account object nào được đọc.

## 10. `this` của local class không phải `Outer.this`

Trong method của local class, `this` là **instance của local class**, bất kể nó được khai báo trong instance hay static method.

~~~java
class Outer {
    void act() {
        class Local {
            boolean selfCheck() {
                return this instanceof Local;
            }

            boolean ownerCheck() {
                return Outer.this != null;
            }
        }
    }
}
~~~

`this` ở `selfCheck` không tự trở thành Outer object. `Outer.this` chỉ Outer receiver riêng biệt.

Trong **static context**, `this` **vẫn hợp lệ bên trong instance method của local class**, vì lúc ấy `this` là local class object. Chỉ có `Outer.this` mới không tồn tại.

## 11. Chương trình chạy: `this` trong hai ngữ cảnh

Tạo **`ThisScopeDemo.java`**:

~~~java
public class ThisScopeDemo {
    private final String id;

    ThisScopeDemo(String id) {
        this.id = id;
    }

    String instanceRun() {
        class Local {
            String show() {
                return "local=" + (this instanceof Local)
                        + ", outer=" + ThisScopeDemo.this.id;
            }
        }

        return new Local().show();
    }

    static String staticRun() {
        class Local {
            String show() {
                return "local=" + (this instanceof Local);
            }
        }

        return new Local().show();
    }

    public static void main(String[] args) {
        System.out.println(new ThisScopeDemo("A").instanceRun());
        System.out.println(ThisScopeDemo.staticRun());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThisScopeDemo.java
java ThisScopeDemo
~~~

Stdout:

~~~text
local=true, outer=A
local=true
~~~

Cả hai local class objects đều có instance receiver `this` trong method show. Chỉ local class của `instanceRun` có enclosing ThisScopeDemo instance để dùng `ThisScopeDemo.this`.

## 12. Capture local variables: quy tắc giống nhau

Cả instance lẫn static context đều cho local class dùng surrounding method locals/parameters nếu chúng **final hoặc effectively final**, và definitely assigned trước khi được dùng.

~~~java
int base = 10; // Effectively final nếu không bị gán lại.

class Local {
    int compute(int input) {
        return base + input;
    }
}
~~~

Biến `base` không có từ khóa final nhưng được dùng hợp lệ nếu nó không bị reassigned theo quy tắc Java.

**Ví dụ làm mất effectively final:**

~~~java
int base = 10;
base = 20;

class Local {
    int compute() {
        // return base; // Compile error: base không effectively final.
        return 0;
    }
}
~~~

Lỗi xuất phát từ **capture của local variable**, không phụ thuộc việc declaration nằm trong static hay instance method.

## 13. Chương trình chạy: capture ở hai ngữ cảnh

Tạo **`CaptureInBothContextsDemo.java`**:

~~~java
public class CaptureInBothContextsDemo {
    private final int multiplier;

    CaptureInBothContextsDemo(int multiplier) {
        this.multiplier = multiplier;
    }

    int instanceCalculate(int input) {
        int offset = 2;

        class Calculator {
            int result() {
                return multiplier * input + offset;
            }
        }

        return new Calculator().result();
    }

    static int staticCalculate(int input) {
        int multiplier = 3;
        int offset = 2;

        class Calculator {
            int result() {
                return multiplier * input + offset;
            }
        }

        return new Calculator().result();
    }

    public static void main(String[] args) {
        CaptureInBothContextsDemo value =
                new CaptureInBothContextsDemo(4);

        System.out.println("instance=" +
                value.instanceCalculate(5));
        System.out.println("static=" +
                staticCalculate(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureInBothContextsDemo.java
java CaptureInBothContextsDemo
~~~

Stdout:

~~~text
instance=22
static=17
~~~

Trong instance method, `multiplier` là outer field, còn input/offset là captured method values. Trong static method, multiplier/offset đều là captured local values, không hề có outer instance field.

## 14. Outer instance fields không bị yêu cầu effectively final

Một field `Outer.counter` có thể đổi theo thời gian:

~~~java
class Outer {
    private int counter;

    Runnable createTask() {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(Outer.this.counter);
            }
        }
        return new Task();
    }

    void setCounter(int next) {
        counter = next;
    }
}
~~~

Task đọc **field hiện tại của enclosing Outer object** mỗi lần run, không phải snapshot của counter tại lúc createTask.

So với method-local variable:

~~~java
int initialCounter = counter;

class Task {
    int snapshot() {
        return initialCounter;
    }
}
~~~

`initialCounter` là một local value được capture; nếu đó là primitive int, mỗi Task có semantics đọc giá trị đã captured khi instance được tạo, không đọc field thay đổi về sau.

## 15. Chương trình chạy: field động và local snapshot

Tạo **`FieldVsCapturedLocalDemo.java`**:

~~~java
public class FieldVsCapturedLocalDemo {
    private int count;

    FieldVsCapturedLocalDemo(int count) {
        this.count = count;
    }

    interface Reader {
        String read();
    }

    Reader createReader() {
        int snapshot = count;

        class ReaderImpl implements Reader {
            @Override
            public String read() {
                return "field=" + FieldVsCapturedLocalDemo.this.count
                        + ", snapshot=" + snapshot;
            }
        }

        return new ReaderImpl();
    }

    void setCount(int next) {
        count = next;
    }

    public static void main(String[] args) {
        FieldVsCapturedLocalDemo owner =
                new FieldVsCapturedLocalDemo(10);

        Reader reader = owner.createReader();
        System.out.println(reader.read());

        owner.setCount(99);
        System.out.println(reader.read());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldVsCapturedLocalDemo.java
java FieldVsCapturedLocalDemo
~~~

Stdout:

~~~text
field=10, snapshot=10
field=99, snapshot=10
~~~

Sự khác biệt cốt lõi: `Outer.this.count` đọc trạng thái field của object được giữ, còn `snapshot` là captured primitive local value. Một local class có thể kết hợp cả hai semantics trong cùng method.

## 16. Reassign local reference khác mutate referenced object

Effectively final áp dụng cho **biến**, không tự đóng băng object mà biến trỏ tới.

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();

class Collector {
    void add(String name) {
        names.add(name); // Hợp lệ: names không bị gán lại.
    }
}
~~~

`names.add` sửa List object, nhưng không reassign local variable `names`. Vì vậy capture hợp lệ trong static hoặc instance method.

Ngược lại:

~~~java
// names = new ArrayList<>(); // Nếu thực hiện, names không còn effectively final.
~~~

Việc khai báo biến là `final` cũng không làm `ArrayList` thread-safe hoặc immutable. Nếu shared mutable object thoát method hoặc được dùng giữa threads, cần ownership/synchronization riêng.

## 17. Chương trình chạy: capture mutable reference ở static method

Tạo **`MutableCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableCaptureDemo {
    static List<String> collect() {
        List<String> names = new ArrayList<>();

        class Collector {
            void add(String name) {
                names.add(name);
            }
        }

        Collector collector = new Collector();
        collector.add("Mai");
        collector.add("An");

        return names;
    }

    public static void main(String[] args) {
        System.out.println(collect());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableCaptureDemo.java
java MutableCaptureDemo
~~~

Stdout:

~~~text
[Mai, An]
~~~

Method là static nhưng capture không có vấn đề vì List reference là effectively final. Nội dung List vẫn mutable và được thay qua Collector.

## 18. Local class có thể sống lâu hơn method

Scope tên local class kết thúc ở dấu `}` của block, nhưng object tạo từ local class có thể được trả qua interface/superclass accessible:

~~~java
static Runnable task(String message) {
    class PrintTask implements Runnable {
        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new PrintTask();
}
~~~

Sau khi `task(...)` return, caller không thấy tên `PrintTask`, nhưng object vẫn tồn tại và sử dụng captured message.

**Điều này đúng cả với static method và instance method.** Khác biệt là local class trong instance method có thể giữ enclosing owner ngoài các captured local values, nếu implementation cần outer state.

## 19. Chương trình chạy: task từ hai ngữ cảnh

Tạo **`EscapingLocalClassDemo.java`**:

~~~java
public class EscapingLocalClassDemo {
    private final String owner;

    EscapingLocalClassDemo(String owner) {
        this.owner = owner;
    }

    Runnable fromInstance(String message) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(owner + ":" + message);
            }
        }
        return new Task();
    }

    static Runnable fromStatic(String message) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("static:" + message);
            }
        }
        return new Task();
    }

    public static void main(String[] args) {
        Runnable first = new EscapingLocalClassDemo("A")
                .fromInstance("hello");
        Runnable second = fromStatic("world");

        first.run();
        second.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EscapingLocalClassDemo.java
java EscapingLocalClassDemo
~~~

Stdout:

~~~text
A:hello
static:world
~~~

Cả hai local Task objects được giữ sau khi factory method return. Task từ instance context dùng enclosing object state; Task từ static context chỉ dùng captured message và static context code.

## 20. Một static method có thể được gọi từ object reference không?

Java cho phép gọi static method qua expression trong một số cú pháp, nhưng đó là style không nên dùng:

~~~java
Owner owner = new Owner();
// owner.staticFactory(); // Có thể hợp lệ nhưng không biến staticFactory thành instance method.
Owner.staticFactory();    // Nên dùng kiểu này.
~~~

**Quan trọng:** Không vì có syntactic qualifier là một object mà local class trong staticFactory tự nhiên nhận enclosing owner instance. Static method vẫn static; instance reference không trở thành `Owner.this` cho local class.

Nếu cần owner, hãy làm parameter explicit:

~~~java
static Runnable factory(Owner owner) {
    // Tạo local class capture owner.
}
~~~

Lựa chọn tường minh làm semantics đúng và tránh kỳ vọng sai về `this`.

## 21. Static field và instance field khi bị shadow tên

Giả sử Outer có:

~~~java
class Outer {
    private static int shared = 100;
    private int own = 10;
}
~~~

Local class trong instance method có thể đọc cả `shared` và `Outer.this.own`. Trong static method chỉ đọc được `shared` nếu không có explicit Outer reference.

Nếu local class có field tên `shared`:

~~~java
class Local {
    private int shared = 5;

    int sum() {
        return shared + Outer.shared;
    }
}
~~~

`shared` không qualified trỏ field Local, còn `Outer.shared` chỉ static field. Nếu local class cần outer instance field, viết `Outer.this.own` khi context cho phép.

**Nhớ:** `Outer.this` là object-level reference, `Outer.shared` là class-level access.

## 22. Chương trình chạy: static và instance cùng tên

Tạo **`FieldResolutionDemo.java`**:

~~~java
public class FieldResolutionDemo {
    private static int shared = 100;
    private int own = 10;

    String instanceView() {
        class Local {
            int shared = 5;

            String show() {
                return shared + "/" + FieldResolutionDemo.shared
                        + "/" + FieldResolutionDemo.this.own;
            }
        }

        return new Local().show();
    }

    static String staticView() {
        class Local {
            int shared = 7;

            String show() {
                return shared + "/" + FieldResolutionDemo.shared;
            }
        }

        return new Local().show();
    }

    public static void main(String[] args) {
        System.out.println(new FieldResolutionDemo().instanceView());
        System.out.println(staticView());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldResolutionDemo.java
java FieldResolutionDemo
~~~

Stdout:

~~~text
5/100/10
7/100
~~~

Local fields và outer static field cùng tên nhưng là fields khác. `FieldResolutionDemo.this.own` chỉ có trong instance context; không có trong `staticView`.

## 23. Local class trong constructor: instance context và khởi tạo

Constructor không phải static method. Một local class khai báo trong constructor thường có access đến enclosing object theo context thích hợp, và có thể capture constructor parameters final/effectively final.

Tuy nhiên **cẩn trọng khi truy cập trạng thái chưa hoàn thành**. Nếu local object được publish từ constructor hoặc gọi overridable methods lúc object đang xây dựng, code có thể thấy fields chưa initialized đầy đủ.

Ví dụ an toàn là local class thực hiện validation từ constructor parameter trước khi gán field:

~~~java
final class Amount {
    private final int value;

    Amount(int value) {
        class Validator {
            boolean positive() {
                return value > 0;
            }
        }
        if (!new Validator().positive()) {
            throw new IllegalArgumentException("non-positive");
        }
        this.value = value;
    }
}
~~~

Đây là class minh họa (không có main); local Validator đọc constructor parameter được capture. Với validation một điều kiện đơn giản, dùng `if (value <= 0)` sẽ ít phức tạp hơn; không cần local class vô điều kiện.

## 24. Chương trình chạy: constructor local class

Tạo **`ConstructorContextDemo.java`**:

~~~java
public class ConstructorContextDemo {
    static final class Interval {
        private final int length;

        Interval(int value) {
            class Validator {
                boolean valid() {
                    return value > 0;
                }
            }

            if (!new Validator().valid()) {
                throw new IllegalArgumentException("length must be positive");
            }
            length = value;
        }

        int length() {
            return length;
        }
    }

    public static void main(String[] args) {
        Interval first = new Interval(7);
        System.out.println("length=" + first.length());

        try {
            new Interval(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorContextDemo.java
java ConstructorContextDemo
~~~

Stdout:

~~~text
length=7
rejected=length must be positive
~~~

Constructor parameter `value` không bị reassign nên effectively final. Local Validator chỉ dùng parameter, không truy cập partial object state và không publish `this`.

## 25. Local class trong instance initializer

Instance initializer block chạy trong construction của mỗi object theo Java initialization order. Local class khai báo tại đây có instance context và có thể truy cập những outer members đã được khởi tạo theo thứ tự thích hợp.

Tạo **`InstanceInitializerDemo.java`**:

~~~java
public class InstanceInitializerDemo {
    static final class Holder {
        private final String text;

        {
            class Formatter {
                String format() {
                    return "ready";
                }
            }

            text = new Formatter().format();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        Holder holder = new Holder();
        System.out.println(holder.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceInitializerDemo.java
java InstanceInitializerDemo
~~~

Stdout:

~~~text
ready
~~~

Local Formatter chỉ visible trong initializer block. Demo cố ý không đọc fields chưa initialized; trong code thực, hiểu thứ tự field initializers, instance initializer blocks, constructor chaining trước khi thêm logic phức tạp.

## 26. Local class trong static initializer

Static initializer block chạy khi class được initialize theo JVM semantics. Không có enclosing Outer instance; local class tại đây thuộc static context.

Tạo **`StaticInitializerDemo.java`**:

~~~java
public class StaticInitializerDemo {
    private static final String STATUS;

    static {
        class Builder {
            String build() {
                return "initialized";
            }
        }

        STATUS = new Builder().build();
    }

    public static void main(String[] args) {
        System.out.println(STATUS);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializerDemo.java
java StaticInitializerDemo
~~~

Stdout:

~~~text
initialized
~~~

Đừng hiểu local class trong static initializer thành static nested member class. `Builder` vẫn là local name trong block `static { ... }`, không phải `StaticInitializerDemo.Builder` mà client được phép dùng.

## 27. Trong nested blocks: context được kế thừa theo vị trí lexical

Static/instance context của local class phụ thuộc vào vị trí nó được khai báo:

~~~java
class Outer {
    void instanceMethod(boolean enabled) {
        if (enabled) {
            class InstanceLocal {
                String show() {
                    return Outer.this.toString();
                }
            }
        }
    }

    static void staticMethod(boolean enabled) {
        if (enabled) {
            class StaticLocal {
                String show() {
                    return "static";
                }
            }
        }
    }
}
~~~

Một nested `if` block không tự biến instance method thành static hoặc ngược lại. Nó chỉ thu hẹp **scope của tên local class và local variables**.

### Scope của tên

Trong ví dụ trên, `InstanceLocal` không visible ngoài `if` block. Không thể `new InstanceLocal()` từ code ở dòng sau block dù vẫn trong cùng instanceMethod.

Scope của tên không làm object tự hủy: nếu object được gán ra một interface reference accessible hơn, nó có thể tiếp tục sống sau block.

## 28. Static nested member class không phải “local class trong static method”

Hai khai báo:

~~~java
class Outer {
    static class MemberNested {
    }

    static void method() {
        class MethodLocal {
        }
    }
}
~~~

khác nhau:

- `MemberNested` là **member class** khai báo ở class body, có tên `Outer.MemberNested`.
- `MethodLocal` là **local class** khai báo trong method body, chỉ có tên trong scope method.
- `MemberNested` có thể được tạo từ code phù hợp bằng `new Outer.MemberNested()`.
- `MethodLocal` không thể được tạo bằng `new Outer.MethodLocal()` bên ngoài.
- Cả hai ở ví dụ này không có enclosing Outer instance ngầm định, nhưng **lý do về declaration scope là khác nhau**.

Đừng dùng cụm “static local class” như thể có syntax `static class Local` trực tiếp trong method. Local class khai báo trong static context không được **gắn member modifier `static`** chỉ vì method là static.

## 29. Ví dụ đối chiếu static nested member và static-method local

Tạo **`NestedVsStaticLocalDemo.java`**:

~~~java
public class NestedVsStaticLocalDemo {
    static class MemberNested {
        String name() {
            return "member-nested";
        }
    }

    static String fromMethod() {
        class Local {
            String name() {
                return "method-local";
            }
        }
        return new Local().name();
    }

    public static void main(String[] args) {
        MemberNested nested = new MemberNested();

        System.out.println(nested.name());
        System.out.println(fromMethod());
        System.out.println("member=" +
                MemberNested.class.isMemberClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedVsStaticLocalDemo.java
java NestedVsStaticLocalDemo
~~~

Stdout:

~~~text
member-nested
method-local
member=true
~~~

MemberNested.class.isMemberClass true. Local class cũng có Class metadata, nhưng có `isLocalClass()` true, không phải member class type.

## 30. Local class và generic method type parameters

Trong instance method hoặc static generic method, local class có thể tham chiếu các type parameters phù hợp scope:

~~~java
static <T> String describe(T input) {
    class Description {
        String text() {
            return String.valueOf(input);
        }
    }
    return new Description().text();
}
~~~

`T` là compile-time type parameter. Local class đọc `input` vì nó effectively final, không vì có enclosing outer object.

Trong instance generic method tương tự, local class còn có thể dùng `Outer.this` để truy cập outer instance. Generic context và static/instance context là **hai trục độc lập**.

## 31. Chương trình chạy: generic local class trong hai ngữ cảnh

Tạo **`GenericContextsDemo.java`**:

~~~java
public class GenericContextsDemo {
    private final String prefix;

    GenericContextsDemo(String prefix) {
        this.prefix = prefix;
    }

    <T> String instanceDescribe(T input) {
        class Description {
            String text() {
                return prefix + String.valueOf(input);
            }
        }
        return new Description().text();
    }

    static <T> String staticDescribe(T input) {
        class Description {
            String text() {
                return "static:" + String.valueOf(input);
            }
        }
        return new Description().text();
    }

    public static void main(String[] args) {
        GenericContextsDemo demo = new GenericContextsDemo("owner:");

        System.out.println(demo.instanceDescribe(17));
        System.out.println(staticDescribe("Java"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericContextsDemo.java
java GenericContextsDemo
~~~

Stdout:

~~~text
owner:17
static:Java
~~~

Cả hai generic methods có T được dùng tại compile time. Không có Class object mới cho mỗi generic argument do type erasure.

## 32. Local class cũng có type parameters riêng

~~~java
static void method() {
    class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    Holder<String> text = new Holder<>("Java");
    Holder<Integer> number = new Holder<>(17);
}
~~~

`Holder<T>` là local class generic; khai báo của nó vẫn có lexical scope. Nó có thể được tạo với type arguments khác nhau trong block đó.

### Chương trình chạy

Tạo **`GenericLocalTypeDemo.java`**:

~~~java
public class GenericLocalTypeDemo {
    static void run() {
        class Holder<T> {
            private final T value;

            Holder(T value) {
                this.value = value;
            }

            T get() {
                return value;
            }
        }

        Holder<String> words = new Holder<>("Java");
        Holder<Integer> number = new Holder<>(17);

        System.out.println("words=" + words.get());
        System.out.println("number=" + number.get());
        System.out.println("same runtime type=" +
                (words.getClass() == number.getClass()));
    }

    public static void main(String[] args) {
        run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericLocalTypeDemo.java
java GenericLocalTypeDemo
~~~

Stdout:

~~~text
words=Java
number=17
same runtime type=true
~~~

Mỗi instance khác value và generic T ở compile time, nhưng thuộc cùng erased runtime local class type trong same defining-loader context.

## 33. Local class có constructors, instance fields và interfaces trong cả hai ngữ cảnh

Dù declaration nằm trong static method, local class **không bị giới hạn thành static utility**. Nó vẫn có thể có instance fields, constructors, methods, và implements interface.

~~~java
static Runnable makeJob(String text) {
    class Job implements Runnable {
        private final String message;

        Job(String message) {
            this.message = message;
        }

        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new Job(text);
}
~~~

Job object có instance field riêng. Constructor nhận String explicit. Không cần Outer instance vì Job được khai báo trong static context; sự tồn tại của instance field trong Job không thay đổi điều đó.

Trong instance method cũng có thể viết cấu trúc tương tự và đồng thời truy cập outer instance state nếu cần.

## 34. Java 17: static declarations bên trong local class

Một số giáo trình cũ (trước Java SE 16) nói inner classes không được khai báo static methods/fields, ngoại trừ constant variables. **Java SE 16 đã nới hạn chế này**, nên trong **Java 17**, local class có thể có static method theo Java language rules hiện hành.

Điều này **không thay đổi** việc local class nằm trong block và không thay đổi sự tồn tại của outer instance trong context khai báo.

### Chương trình chạy

Tạo **`StaticMemberInLocalDemo.java`**:

~~~java
public class StaticMemberInLocalDemo {
    static int compute() {
        class LocalMath {
            static int doubleOf(int value) {
                return value * 2;
            }

            int increment(int value) {
                return value + 1;
            }
        }

        return LocalMath.doubleOf(4)
                + new LocalMath().increment(2);
    }

    public static void main(String[] args) {
        System.out.println("result=" + compute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticMemberInLocalDemo.java
java StaticMemberInLocalDemo
~~~

Stdout:

~~~text
result=11
~~~

`LocalMath` được khai báo trong static method, nhưng method `increment` là instance method của chính LocalMath object; còn `doubleOf` là static method của LocalMath. Class name LocalMath vẫn chỉ visible trong block compute.

**Lưu ý:** Static method của local class không tự có receiver của local/outer instances. Đừng kỳ vọng nó dùng `Outer.this` hoặc captured method locals như một instance method.

## 35. Local record là implicitly static, kể cả trong instance method

Java 17 cho phép **local record declarations**:

~~~java
void process(int input) {
    record Pair(int left, int right) {}

    Pair pair = new Pair(input, 2);
}
~~~

Một local record có **implicitly static semantics**. Nó không thể trực tiếp capture `Outer.this` hoặc local variables từ enclosing method trong record body như local class thông thường. Muốn dùng data từ context, **truyền qua record components/constructor**.

Điểm tinh tế: **Record được khai báo trong instance method** không vì vị trí ấy mà có enclosing Outer instance. Record có đặc điểm riêng của static nested record declarations.

## 36. Chương trình chạy: local class vs local record trong instance method

Tạo **`LocalRecordContrastDemo.java`**:

~~~java
public class LocalRecordContrastDemo {
    private final int factor;

    LocalRecordContrastDemo(int factor) {
        this.factor = factor;
    }

    int calculate(int input) {
        class LocalCalculator {
            int result() {
                return LocalRecordContrastDemo.this.factor * input;
            }
        }

        record Pair(int left, int right) {
            int product() {
                return left * right;
            }
        }

        LocalCalculator calculator = new LocalCalculator();
        Pair pair = new Pair(factor, input);

        System.out.println("class=" + calculator.result());
        System.out.println("record=" + pair.product());

        return pair.product();
    }

    public static void main(String[] args) {
        new LocalRecordContrastDemo(4).calculate(5);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LocalRecordContrastDemo.java
java LocalRecordContrastDemo
~~~

Stdout:

~~~text
class=20
record=20
~~~

LocalCalculator đọc outer field trực tiếp. Pair không capture Outer; `factor` và `input` được truyền explicit cho record components tại `new Pair(factor, input)`.

## 37. Local enum không có enclosing instance, kể cả trong instance method

Một local enum có ngữ nghĩa **implicitly static** dù được khai báo trong instance method hay static method. Nó vẫn là type có tên trong block, nhưng enum body không được tự truy cập `Outer.this` hoặc fields của particular outer instance:

~~~java
class Outer {
    int value = 8;

    void instanceWork() {
        enum State { NEW, DONE }
        System.out.println(State.NEW.name());
        // Enum State không tự capture Outer instance.
    }

    static void staticWork() {
        enum State { NEW, DONE }
        System.out.println(State.DONE.name());
    }
}
~~~

Đây là **class fragment**, với hai `State` là hai type declarations khác nhau theo lexical location. Nếu cần outer data, truyền vào một collaborator hoặc xử lý bên ngoài enum body. Bài local enum/record đi sâu vào constants, constructors và explicit data flow; ở đây trọng tâm là phân biệt **vị trí khai báo** với **quan hệ enclosing instance**.

## 38. `this` trong lambda khác `this` trong local class

Trong instance method của outer:

- `this` trong **method của local class** trỏ local object.
- `Outer.this` trong local class trỏ outer object.
- `this` bên trong **lambda** dùng lexical `this` của enclosing context, thường là outer object.

Trong static method, không có outer `this` để dùng từ lambda; local class vẫn có instance `this` khi method của local class được gọi.

### Chương trình chạy: identity của `this`

Tạo **`LambdaVsLocalThisDemo.java`**:

~~~java
public class LambdaVsLocalThisDemo {
    private final String id;

    LambdaVsLocalThisDemo(String id) {
        this.id = id;
    }

    void compare() {
        class Local {
            String who() {
                return "local:" +
                        (this instanceof Local) + ":" +
                        LambdaVsLocalThisDemo.this.id;
            }
        }

        java.util.function.Supplier<String> lambda =
                () -> "lambda:" + this.id;

        System.out.println(new Local().who());
        System.out.println(lambda.get());
    }

    public static void main(String[] args) {
        new LambdaVsLocalThisDemo("A").compare();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaVsLocalThisDemo.java
java LambdaVsLocalThisDemo
~~~

Stdout:

~~~text
local:true:A
lambda:A
~~~

Lambda không khai báo một local class name và không có cùng `this` semantics. Nó không phải đơn giản là một local class có cú pháp ngắn hơn trong mọi khía cạnh.

## 39. Phạm vi tên của local class không đổi theo static/instance

Trong cả hai contexts, tên local class có scope từ declaration đến hết block liên quan:

~~~java
static void example() {
    {
        class Local {}
        Local first = new Local();
    }

    // Local second = new Local(); // Compile error: ngoài scope.
}
~~~

Tương tự trong instance method. Việc method static không khiến local class trở thành member type `Outer.Local` có thể truy cập từ ngoài.

### Hai local classes cùng simple name ở hai methods

Nếu instanceMethod khai báo `class Task` và staticMethod cũng khai báo `class Task`, đây là **hai declarations riêng**, không phải một Java class dùng chung vì tên giống nhau. Mỗi class có lexical declaring location riêng.

Không suy luận class identity chỉ bằng `getSimpleName()`; generated binary names/class loaders quyết định runtime type identity.

## 40. Runtime metadata không phải enclosing object

Reflection có thể trả:

- `type.isLocalClass()` — true với local class.
- `type.getEnclosingMethod()` — enclosing method metadata khi local class khai báo trong method.
- `type.getEnclosingConstructor()` — constructor metadata nếu local class được khai báo trong constructor.
- `type.getEnclosingClass()` — Class object của enclosing type.
- `type.getDeclaringClass()` — thường null với local class vì nó không phải member class.

**Quan trọng:** `getEnclosingClass()` trả một **Class metadata object**, không phải một **Outer instance** cụ thể. Reflection không mặc định cung cấp `getCapturedOuterObject()` qua Class API.

Muốn phân biệt local class trong static method và instance method, có thể kiểm tra modifier của `getEnclosingMethod()` cùng với behavior, không xem `isLocalClass` đơn lẻ là đủ.

## 41. Chương trình chạy: reflection phân biệt hai ngữ cảnh

Tạo **`LocalContextMetadataDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class LocalContextMetadataDemo {
    Class<?> instanceType() {
        class InstanceLocal {}
        return InstanceLocal.class;
    }

    static Class<?> staticType() {
        class StaticLocal {}
        return StaticLocal.class;
    }

    public static void main(String[] args) {
        LocalContextMetadataDemo owner =
                new LocalContextMetadataDemo();

        Class<?> a = owner.instanceType();
        Class<?> b = staticType();

        Method m1 = a.getEnclosingMethod();
        Method m2 = b.getEnclosingMethod();

        System.out.println("instance local=" + a.isLocalClass());
        System.out.println("static local=" + b.isLocalClass());
        System.out.println("first method=" + m1.getName());
        System.out.println("second method=" + m2.getName());
        System.out.println("first is static=" +
                Modifier.isStatic(m1.getModifiers()));
        System.out.println("second is static=" +
                Modifier.isStatic(m2.getModifiers()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalContextMetadataDemo.java
java LocalContextMetadataDemo
~~~

Stdout:

~~~text
instance local=true
static local=true
first method=instanceType
second method=staticType
first is static=false
second is static=true
~~~

Cả hai là local classes. Reflection biết enclosing **method declaration**, nhưng không phải “một object owner của tất cả instances”; local class trong static context cũng có enclosing class metadata.

## 42. Reflection constructor và captured parameters: đừng lệ thuộc synthetic details

Compiler có thể biểu diễn captured locals, enclosing instance hoặc other captured values bằng synthetic fields/constructor parameters trong bytecode. Những chi tiết này phục vụ implementation của Java language semantics.

- Đừng hardcode `this$0` hoặc tên field synthetic khác.
- Đừng giả định constructor signature bằng source declaration chỉ bằng cách nhìn số parameters qua reflection.
- Đừng dựa vào generated binary class name như `Outer$1Local` để phân biệt static/instance context.
- Ưu tiên tạo local object bằng `new Local(...)` ngay trong lexical scope.
- Nếu bắt buộc reflection, dựa vào public `Class/Method/Constructor` APIs và kiểm tra contracts.

Local classes và anonymous classes có compiler-generated names; nội dung name/number có thể khác tùy compiler, version hoặc source changes.

## 43. Enclosing method không đồng nghĩa mỗi lần gọi tạo một Class object

Nếu method chứa `class Task` và return `new Task()`, nhiều lời gọi method có thể tạo nhiều Task **instances**, nhưng chúng là instances của **cùng runtime local class definition** trong một class-loader context.

Ví dụ:

~~~java
static Runnable task(String text) {
    class Task implements Runnable {
        public void run() {
            System.out.println(text);
        }
    }
    return new Task();
}
~~~

Hai objects có captured texts khác nhau nhưng `a.getClass() == b.getClass()` true ở same runtime environment.

### Chương trình chạy

Tạo **`LocalClassIdentityDemo.java`**:

~~~java
public class LocalClassIdentityDemo {
    static Runnable task(String text) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(text);
            }
        }
        return new Task();
    }

    public static void main(String[] args) {
        Runnable a = task("A");
        Runnable b = task("B");

        System.out.println("same object=" + (a == b));
        System.out.println("same Class=" +
                (a.getClass() == b.getClass()));
        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalClassIdentityDemo.java
java LocalClassIdentityDemo
~~~

Stdout:

~~~text
same object=false
same Class=true
A
B
~~~

Static context không biến mỗi invocation thành một separate class type. Captured state là **per-instance behavior/data**, không phải một class mới cho từng argument.

## 44. Static nested code và enclosing static method: có thể capture gì?

Một local class trong một static method của **static nested class** cũng không tự có enclosing object của nested class:

~~~java
class Outer {
    static class Helper {
        private final String id;

        Helper(String id) {
            this.id = id;
        }

        static Runnable fromStatic(Helper helper) {
            class Task implements Runnable {
                public void run() {
                    System.out.println(helper.id);
                }
            }
            return new Task();
        }
    }
}
~~~

Task có `helper` explicit reference, không có `Outer.this` hay `Helper.this` do declaration nằm trong static method. Nhưng nếu Helper khai báo instance method chứa local class, nó có thể truy cập `Helper.this` — là **Helper instance**, không tự có enclosing Outer instance vì Helper là static nested member class.

**Kết luận:** Xác định chính xác **class nào có receiver**, chứ không chỉ nhìn một chuỗi các tên nested classes.

## 45. Instance method của inner member class: nhiều tầng enclosing instances

Nếu `Inner` là **non-static member class** của Outer, và nó khai báo instance method có một local class:

~~~java
class Outer {
    private final String name;

    Outer(String name) {
        this.name = name;
    }

    class Inner {
        Runnable task() {
            class LocalTask implements Runnable {
                public void run() {
                    System.out.println(Outer.this.name);
                }
            }
            return new LocalTask();
        }
    }
}
~~~

LocalTask được khai báo ở **instance context của Inner**, và có thể tham chiếu đúng `Outer.this` qua các enclosing instance relationships hợp lệ. Nó không cần tự tạo một Outer khác.

Trong static context của một static nested class, chuỗi enclosing instances này không tồn tại theo cách ấy.

### Không lạm dụng

Khi code có nhiều tầng Outer.Inner.Local, qualified `this` có thể khó đọc. Thường nên tách dependency thành explicit interface/constructor argument nếu chỉ cần một giá trị nhỏ.

## 46. Chương trình chạy: nhiều tầng bao ngoài

Tạo **`MultiLevelContextDemo.java`**:

~~~java
public class MultiLevelContextDemo {
    private final String label;

    MultiLevelContextDemo(String label) {
        this.label = label;
    }

    class Inner {
        Runnable task(String suffix) {
            class LocalTask implements Runnable {
                @Override
                public void run() {
                    System.out.println(
                            MultiLevelContextDemo.this.label + ":" + suffix);
                }
            }
            return new LocalTask();
        }
    }

    public static void main(String[] args) {
        MultiLevelContextDemo outer = new MultiLevelContextDemo("A");
        Inner inner = outer.new Inner();
        Runnable task = inner.task("done");

        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultiLevelContextDemo.java
java MultiLevelContextDemo
~~~

Stdout:

~~~text
A:done
~~~

Trong static main, `Inner` muốn được tạo thì cần `outer.new Inner()`; sau đó instance method `inner.task(...)` có đủ context để tạo LocalTask. Code không suy ra enclosing outer từ static main.

## 47. Static và instance context trong callback/lifecycle

Một local class được trả qua `Runnable` có thể được lưu trong event listener registry hoặc executor queue lâu hơn method tạo nó.

- Local class từ instance method nếu dùng outer state có thể giữ Outer reachable.
- Local class từ static method capture một explicit Outer reference cũng có thể giữ Outer reachable.
- Local class từ static method chỉ dùng String snapshot nhỏ có thể không cần giữ owner object.
- Lambda/anonymous classes cũng có capture semantics và rủi ro retention khi reference graph yêu cầu.

**Keyword `static` không phải thuốc chữa memory leak.** Nếu bạn capture một large service/entity reference và giữ task trong global registry, resource vẫn có thể bị giữ sống. Hãy unregister callbacks/close lifecycles theo API contracts.

## 48. Thread safety không tự đến từ effective final

Một captured local reference có thể trỏ mutable List, Map, counter hoặc object graph. Multiple threads cùng gọi local-class methods có thể có data race nếu không dùng synchronization thích hợp.

Chẳng hạn:

~~~java
static Runnable task(java.util.List<String> shared) {
    class LocalTask implements Runnable {
        public void run() {
            shared.add("x");
        }
    }
    return new LocalTask();
}
~~~

`shared` parameter effectively final, nhưng `ArrayList.add` không tự thread-safe. Cần synchronized ownership, concurrent collection, immutable snapshots hoặc thiết kế threading phù hợp.

### Chương trình chạy: thread-safe counter qua capture

Tạo **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    static Runnable incrementer(AtomicInteger target) {
        class IncrementTask implements Runnable {
            @Override
            public void run() {
                target.incrementAndGet();
            }
        }
        return new IncrementTask();
    }

    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = incrementer(counter);

        increment.run();
        increment.run();

        System.out.println("counter=" + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

Stdout:

~~~text
counter=2
~~~

AtomicInteger đảm bảo atomic increment semantics cho operation ấy; effective-final rule chỉ bảo vệ việc parameter target không bị reassign, không tạo synchronization cho mutable object.

## 49. Memory/CPU: chọn local class khi có lý do

Local named class có thể hữu ích khi cần:

- Một implementation nhỏ, giàu ý nghĩa nhưng chỉ dùng trong một method/block.
- Nhiều instance methods hoặc instance fields.
- Constructor có tham số để tạo behavior có cấu hình.
- Implement interface và giấu concrete type khỏi public API.
- Capture vài dependencies final/effectively final rõ ràng.

Không cần tạo local class cho một phép cộng đơn giản. Nếu logic cần reuse ở nhiều methods, một private static nested/top-level class hoặc helper method có thể rõ và test-friendly hơn.

**Quy tắc thiết kế:** Khai báo trong instance context khi behavior thật sự phụ thuộc enclosing owner; dùng static context hoặc explicit dependencies khi owner không cần thiết. Không di chuyển class chỉ để né compiler mà quên thay đổi contract ownership.

## 50. Bảng so sánh năm lựa chọn

| Lựa chọn | Có tên trong block? | Outer instance access | Local capture |
| --- | --- | --- | --- |
| Local class trong instance method | Có | Có thể dùng `Outer.this` | Final/effectively final |
| Local class trong static method | Có | Không tự có `Outer.this` | Final/effectively final |
| Static nested member class | Không phải local, có member type name | Không tự có Outer instance | Không capture method locals tùy ý |
| Anonymous class trong instance context | Không có simple name declaration | Có thể dùng outer instance | Final/effectively final |
| Lambda trong instance context | Không có class name ở source | Lexical `this` của outer | Final/effectively final |

Nếu cần một **local record** trong instance method, nhớ nó implicitly static và nhận surrounding values qua constructor/components; không coi nó là local ordinary inner class capture-enabled.

## 51. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Outer.this` trong static-method local class | Không có enclosing Outer instance | Truyền `Outer target` explicit |
| Đọc `outerField` trong static-method local class | Instance field cần receiver | `target.outerField` |
| `return localVar` sau khi `localVar++` | Variable không effectively final | Không reassign; truyền giá trị vào constructor |
| Dùng `this` mong là Outer từ local-class instance method | `this` là Local instance | Dùng `Outer.this` trong instance context |
| Mong captured int cập nhật theo mutable outer field | Capture local value khác outer-field lookup | Đọc `Outer.this.field` khi cần live state |
| Gán captured List sang List khác | Reassignment phá effectively final | Không gán lại local hoặc dùng explicit holder |
| Nghĩ `names.add` phá effectively final | Mutate object khác reassignment | Capture hợp lệ nhưng quản lý mutability |
| Gọi `new Outer.Local()` | Local không là Outer member type | `new Local()` trong scope |
| Gọi `Outer.this` trong local record | Local record implicitly static | Truyền dữ liệu qua components |
| Nghĩ Java 17 cấm static methods trong local class | Quy tắc cũ trước Java SE 16 | Dùng Java 17 syntax khi thực sự cần |
| Cho task escape constructor và dùng partial state | Object chưa xây dựng xong | Không publish `this` sớm |
| Lưu callback lâu dài rồi quên cleanup | Captured refs giữ resources reachable | Lifecycle/unregister/ownership |
| Cho nhiều threads cùng sửa captured ArrayList | Không thread-safe | Synchronization/concurrent structure |
| Parse tên `Outer$1Local` như contract | Generated names không ổn định | Dùng Reflection APIs |
| Xem static context là “không được tạo object” | Static method vẫn được `new Local()` | Không có outer instance, nhưng local objects vẫn bình thường |

## 52. Bài tập 1 — Instance và static đối chiếu

Cho:

~~~java
class Sample {
    int own = 4;
    static int shared = 8;

    int runInstance() {
        class Local {
            int x() { return Sample.this.own + shared; }
        }
        return new Local().x();
    }

    static int runStatic() {
        class Local {
            int x() { return shared; }
        }
        return new Local().x();
    }
}
~~~

**Đáp án:** `new Sample().runInstance()` trả 12; `Sample.runStatic()` trả 8. Instance local đọc own+shared; static local chỉ đọc shared.

## 53. Bài tập 2 — Vì sao lỗi?

~~~java
static void run() {
    int number = 10;
    number++;
    class Local {
        int value() {
            // return number;
            return 0;
        }
    }
}
~~~

**Đáp án:** Nếu bỏ comment ở return number, compiler từ chối capture vì number đã bị reassign bằng ++, không còn effectively final. Static context không phải nguyên nhân gây lỗi capture.

## 54. Bài tập 3 — Mutable reference có được capture?

~~~java
static void run() {
    java.util.List<String> list =
            new java.util.ArrayList<>();

    class Local {
        void add() {
            list.add("Java");
        }
    }

    new Local().add();
}
~~~

**Đáp án:** Hợp lệ. Biến list không reassign; `add` mutate List object. Không tự suy ra thread safety.

## 55. Bài tập 4 — Capture và field khác nhau

Một local class trong instance method có `int snapshot = owner.count`, method của local class đọc cả `snapshot` và `Owner.this.count`. Owner.count thay từ 5 thành 9.

**Đáp án:** snapshot vẫn 5; field lookup trả 9. Snapshot là captured primitive local value, field lookup đọc state hiện tại của enclosing object.

## 56. Bài tập 5 — Static method nhận Outer

~~~java
static Runnable task(Outer owner) {
    class Local implements Runnable {
        public void run() {
            System.out.println(owner.id);
        }
    }
    return new Local();
}
~~~

**Đáp án:** Hợp lệ nếu Outer.id accessible theo nesting rules và owner không bị reassign; local class capture explicit owner reference. Nó không có `Outer.this` tự động.

## 57. Bài tập 6 — `this` trong static-method local class

Trong `static void method()` khai báo `class Local { boolean check(){ return this instanceof Local; }}` rồi gọi `new Local().check()`.

**Đáp án:** Hợp lệ và trả true. `this` trong Local.check là Local object; static context chỉ cấm **enclosing Outer.this**, không cấm instance methods của Local.

## 58. Bài tập 7 — Local record trong instance method

~~~java
int compute(int n) {
    record Pair(int a, int b) {
        int sum() { return a + b; }
    }
    return new Pair(n, 2).sum();
}
~~~

**Đáp án:** Hợp lệ trong Java 17. Pair nhận n qua constructor, **không capture trực tiếp** parameter n từ body của local record. Kết quả là n+2.

## 59. Bài tập 8 — Phân biệt local và member nested

Trong `static void work() { class Helper {} }`, có tạo `new Outer.Helper()` ở nơi khác được không?

**Đáp án:** Không. Helper là local class, tên chỉ scope trong work. Nếu cần access từ nhiều methods, khai báo `static class Helper` ở class body, không đặt trong method.

## 60. Bài tập 9 — Runtime class metadata

Một instance-method local class và một static-method local class đều gọi `getClass().isLocalClass()`. Kết quả?

**Đáp án:** Cả hai true. Muốn biết enclosing method có static modifier không, dùng `getEnclosingMethod()` và `Modifier.isStatic(...)` theo metadata.

## 61. Bài tập 10 — Lifecycle và capture

Một instance method trả local Runnable dùng `Outer.this`. Caller lưu Runnable trong global registry rất lâu. Rủi ro nào?

**Đáp án:** Runnable có thể giữ enclosing Outer reachable, kéo dài lifecycle của Outer. Cần ownership/unregister. Tạo task trong static method và capture explicit Outer reference cũng có rủi ro tương tự.

## 62. Checklist cuối bài

- [ ] Tôi biết local class có tên được khai báo trong block.
- [ ] Tôi không nhầm local class với static nested member class.
- [ ] Tôi hiểu lexical enclosing class và enclosing object không giống nhau.
- [ ] Tôi biết instance-method local có thể dùng Outer.this.
- [ ] Tôi biết static-method local không có Outer.this.
- [ ] Tôi biết local class trong static context vẫn có own `this`.
- [ ] Tôi biết static method có thể new Local trong block.
- [ ] Tôi truyền explicit owner reference nếu static logic cần một instance.
- [ ] Tôi phân biệt static field access và instance field access.
- [ ] Tôi phân biệt captured local value với outer field lookup.
- [ ] Tôi biết captured locals/parameters phải final hoặc effectively final.
- [ ] Tôi biết ++, reassignment làm biến mất effectively final.
- [ ] Tôi không coi captured mutable reference là immutable object.
- [ ] Tôi biết local object có thể sống lâu hơn method qua interface.
- [ ] Tôi biết local class trong constructor/instance initializer có instance context.
- [ ] Tôi biết static initializer không có Outer.this.
- [ ] Tôi không publish partial object từ constructor.
- [ ] Tôi đọc đúng shadowing của local class fields và outer members.
- [ ] Tôi biết generic local class và generic method type parameters.
- [ ] Tôi hiểu Java 17 cho phép static declarations trong local class.
- [ ] Tôi không nhầm local record/enum implicitly static với ordinary local class.
- [ ] Tôi phân biệt lambda lexical this với local-class this.
- [ ] Tôi biết class metadata `isLocalClass` không cho enclosing instance object.
- [ ] Tôi dùng `getEnclosingMethod` và Modifier khi cần kiểm tra context.
- [ ] Tôi không hardcode compiler-generated class names.
- [ ] Tôi hiểu lifetime của captured references và memory retention.
- [ ] Tôi biết effective final không tự giải quyết concurrency.
- [ ] Tôi chọn static nested/top-level class khi logic cần tái sử dụng.
- [ ] Tôi giải thích được các chương trình Java 17+ và bài tập trên.

**Kết luận:** **Local class trong ngữ cảnh đối tượng** có thể truy cập enclosing instance bằng `Outer.this` cùng các outer instance members; **local class trong ngữ cảnh `static`** không có enclosing object ngầm định, nhưng vẫn có own instances, constructors, methods và capture các final/effectively final locals. Khác biệt này thuộc **vị trí và ngữ cảnh khai báo**, không phải local class trong static method trở thành static nested member class. Khi cần owner trong static code, **truyền reference tường minh**; khi cần snapshot, capture immutable values; và khi local object thoát block, quản lý mutability, lifetime và thread safety đúng hợp đồng.
