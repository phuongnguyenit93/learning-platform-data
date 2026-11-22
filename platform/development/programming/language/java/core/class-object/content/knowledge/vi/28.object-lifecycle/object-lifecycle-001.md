# Vòng đời đối tượng Java: từ tạo đối tượng, sử dụng đến khi không còn truy cập được

## 1. Mục tiêu bài học

Một đối tượng Java không có vòng đời giống một biến cục bộ. Biến có thể đi ra khỏi scope trong khi đối tượng vẫn còn được tham chiếu ở nơi khác; ngược lại, đối tượng có thể trở nên **không còn truy cập được** trước khi method kết thúc nếu chương trình không còn cần tham chiếu đến nó. Và kể cả khi đối tượng không còn reachable, JVM **không hứa lập tức giải phóng bộ nhớ**.

Để hiểu vòng đời, ta cần phân biệt bốn lớp khái niệm:

1. **Tạo đối tượng:** JVM thực hiện cấp phát và khởi tạo instance theo quy tắc Java.
2. **Sử dụng đối tượng:** Code giữ, truyền, gán hoặc lưu các tham chiếu, gọi instance methods và thay đổi state hợp lệ.
3. **Reachability:** Tại một thời điểm, object còn có thể được đi đến từ những nguồn tham chiếu mà JVM coi là đang sống không?
4. **Quản lý bộ nhớ và tài nguyên:** Garbage collector có thể thu hồi bộ nhớ của object không còn reachable; những resources như file/socket/database connection lại phải được đóng bằng cơ chế khác, không nên đợi GC.

Ví dụ ngắn:

```java
Person person = new Person("An");
person.greet();
person = null;
```

Đây là **mảnh code minh họa**; giả sử `Person` có constructor và method `greet()`.

- `new Person("An")` tạo một đối tượng Person.
- `person` là một biến kiểu tham chiếu, đang trỏ đến object.
- `person.greet()` sử dụng object qua tham chiếu đó.
- `person = null` làm **biến person không còn tham chiếu object cũ**.
- Điều đó **không tự chứng minh** object cũ không còn reachable: có thể một biến khác hoặc một field khác vẫn giữ tham chiếu.
- Ngay cả khi không còn reachable, thời điểm GC chạy và thu hồi bộ nhớ **không xác định bởi câu lệnh gán null**.

**Thông điệp xuyên suốt:** Java tự quản lý bộ nhớ heap ở mức object reachability, nhưng developer vẫn chịu trách nhiệm với lifetime của tham chiếu, tính hợp lệ của trạng thái, và đóng resources kịp thời.

Mọi ví dụ runnable dưới đây nhắm **Java 17+**, tách riêng theo tên file, có lệnh `javac`/`java` và stdout xác định khi phù hợp. Các diễn giải về GC tránh dựa vào việc JVM phải chạy GC ở một thời điểm cố định.

## 2. Đối tượng khác biến tham chiếu như thế nào?

Đối tượng là một instance của class (hoặc array instance), có identity và state theo kiểu của nó. Biến tham chiếu **không chứa toàn bộ object**; nó chứa một giá trị tham chiếu có thể dùng để truy cập object, hoặc `null`.

Tạo **`ObjectAndReferenceDemo.java`**:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class ObjectAndReferenceDemo {
    public static void main(String[] args) {
        Person first = new Person("An");
        Person second = first;

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first == second);

        first = null;
        System.out.println(second.name());
    }
}
```

```bash
javac ObjectAndReferenceDemo.java
java ObjectAndReferenceDemo
```

```text
An
An
true
An
```

`first` và `second` **cùng trỏ một Person**, không phải hai bản sao. Gán `first = null` chỉ thay giá trị **một biến**; `second` vẫn truy cập được object cũ. Đây là lý do không thể gắn vòng đời object vào một tên biến đơn lẻ.

### Sơ đồ tham chiếu

```text
Ban đầu:
first  ──┐
         ├────> Person("An")
second ──┘

Sau first = null:
first  ───────> null
second ───────> Person("An")
```

GC không được tự thu hồi object đang cần thiết cho `second.name()`; object vẫn reachable qua một tham chiếu mạnh hợp lệ.

## 3. Các trạng thái khái niệm của vòng đời

Hãy hình dung tiến trình:

```text
new → cấp phát/khởi tạo → object sẵn sàng được sử dụng
   → các references được truyền/lưu/thay đổi
   → không còn đường strong reachability thích hợp
   → có thể được GC phát hiện và thu hồi
```

Đây là **sơ đồ khái niệm**, không phải một state machine API chính thức của JVM. Đặc biệt:

- Java không cung cấp một method thông thường trả lời chính xác “object X sẽ bị thu hồi vào giây nào”.
- GC có thể hoạt động nhiều lần trong lúc object vẫn sống.
- Object không còn được truy cập từ code **không đồng nghĩa** ngay lập tức được free.
- JVM có thể tối ưu cấp phát và biểu diễn nội bộ; không nên dùng sơ đồ này để khẳng định mọi `new` đều tương ứng một heap allocation vật lý quan sát được.
- Lifetime của **file descriptor, socket, transaction** không đồng nhất với lifetime của wrapper Java object.

Bài tập tư duy đầu tiên: **đừng hỏi “biến ra scope chưa?” trước khi hỏi “còn đường tham chiếu mạnh nào đến object không?”**

## 4. Bước 1: `new` đánh dấu yêu cầu tạo một class instance

Ví dụ:

```java
Person p = new Person("Lan");
```

Một class instance creation expression `new Person(...)` thực hiện quá trình tạo instance theo ngữ nghĩa Java:

1. Xác định class cần tạo và constructor được chọn qua overload resolution.
2. Khi cần, đảm bảo class đã được khởi tạo theo quy tắc class initialization.
3. Cấp phát không gian cho instance theo cơ chế JVM.
4. Các instance fields trước hết có **giá trị mặc định** (0, false, null...) trước phần khởi tạo theo source.
5. Thực hiện constructor chain, gọi superclass constructor thích hợp trước khi thực hiện phần còn lại theo thứ tự Java.
6. Thực hiện field initializers và instance initializer blocks theo thứ tự quy định, cùng constructor body.
7. Nếu construction kết thúc bình thường, expression nhận reference đến instance và code tiếp tục sử dụng.

Thứ tự quan sát được từ source được minh họa ở các phần tiếp theo. Không nên đồng nhất các bước khái niệm này với thứ tự từng instruction machine code trong một JVM tối ưu hóa, miễn behavior vẫn phù hợp Java specification.

## 5. Class initialization và object initialization là hai sự kiện khác nhau

`static` fields/static initializer blocks thuộc **class**, trong khi instance fields/instance initializer blocks và constructor body áp dụng cho **mỗi instance**.

Tạo **`ClassVersusInstanceInitDemo.java`**:

```java
class Widget {
    static {
        System.out.println("class initialized");
    }

    {
        System.out.println("instance initialized");
    }

    Widget() {
        System.out.println("constructor");
    }
}

public class ClassVersusInstanceInitDemo {
    public static void main(String[] args) {
        new Widget();
        new Widget();
    }
}
```

```bash
javac ClassVersusInstanceInitDemo.java
java ClassVersusInstanceInitDemo
```

```text
class initialized
instance initialized
constructor
instance initialized
constructor
```

Trong một execution bình thường của chương trình này:

- Class Widget được initialize khi có active use cần thiết, nên static block chạy **một lần cho class initialization**.
- Tạo hai instances → instance initializer và constructor body chạy cho **mỗi instance**.
- Class initialization không phải synonym của constructor call.
- Khi class đã được initialize, việc tạo object sau đó không lặp static initializer.

**Ngoại lệ quan trọng về ngôn ngữ:** Việc truy cập compile-time constant static field, tham chiếu class literal, hoặc nhiều thao tác reflection có các quy tắc triggering khác nhau. Không nên tuyên bố “hễ nhắc tên class là static block chạy”.

## 6. Giá trị mặc định của instance fields trước explicit initialization

Với fields, Java bảo đảm các default values như:

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int` | 0 |
| `long` | 0L |
| `float` | 0.0f |
| `double` | 0.0d |
| `char` | `'\u0000'` |
| `boolean` | false |
| Reference field | null |

Các instance fields có giai đoạn default initialization trước khi source initializers/constructor gán values.

**Đừng nhầm với local variables:** Local variable trong method **không** tự có default value để được đọc trước definite assignment.

Tạo **`FieldDefaultsDemo.java`**:

```java
class Data {
    int count;
    boolean ready;
    String title;
}

public class FieldDefaultsDemo {
    public static void main(String[] args) {
        Data data = new Data();

        System.out.println(data.count);
        System.out.println(data.ready);
        System.out.println(data.title == null);
    }
}
```

```bash
javac FieldDefaultsDemo.java
java FieldDefaultsDemo
```

```text
0
false
true
```

Đây là **default field values**, không phải bằng chứng Data có explicit zero-argument constructor do tác giả viết. Compiler có thể sinh default constructor nếu class không khai báo constructor nào và các điều kiện cú pháp hợp lệ.

## 7. Constructor chain và thứ tự khởi tạo superclass/subclass

Khi tạo subclass instance, superclass phần tương ứng được khởi tạo trước subclass portion, theo quy tắc constructor invocation của Java.

Tạo **`InheritanceInitializationDemo.java`**:

```java
class Parent {
    int parentField = announce("parent field");

    {
        announce("parent block");
    }

    Parent() {
        announce("parent constructor");
    }

    static int announce(String text) {
        System.out.println(text);
        return 1;
    }
}

class Child extends Parent {
    int childField = announce("child field");

    {
        announce("child block");
    }

    Child() {
        announce("child constructor");
    }
}

public class InheritanceInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac InheritanceInitializationDemo.java
java InheritanceInitializationDemo
```

```text
parent field
parent block
parent constructor
child field
child block
child constructor
```

**Cách đọc:**

- `new Child()` dẫn đến constructor chain gọi superclass constructor phù hợp.
- Parent field initializer và Parent instance block chạy trước Parent constructor body.
- Sau khi superclass initialization path xong, Child field initializer và Child instance block chạy theo source order trước Child constructor body.
- Tất cả những phần này áp dụng cho cùng một Child object đang được tạo; **không có một Parent object độc lập** được tạo rồi nhét vào Child.

Nếu constructors có `this(...)` chaining, hãy kiểm quy tắc constructor invocation để không kết luận mỗi constructor body đều chạy tất cả instance initializers một lần. Các initializers của một class thực hiện đúng theo constructor chain rules.

## 8. Nguy cơ gọi overridable method trong constructor

Superclass constructor có thể gọi một method bị subclass override **trước khi subclass field initializers chạy**. Khi đó method override quan sát thấy subclass fields ở default values.

Tạo **`ConstructorDispatchRiskDemo.java`**:

```java
class Base {
    Base() {
        printState();
    }

    void printState() {
        System.out.println("base");
    }
}

class Derived extends Base {
    private int count = 5;

    @Override
    void printState() {
        System.out.println("count=" + count);
    }
}

public class ConstructorDispatchRiskDemo {
    public static void main(String[] args) {
        Derived object = new Derived();
        object.printState();
    }
}
```

```bash
javac ConstructorDispatchRiskDemo.java
java ConstructorDispatchRiskDemo
```

```text
count=0
count=5
```

Lần đầu gọi `printState()` xảy ra trong `Base()`; dynamic dispatch đi đến implementation của Derived, nhưng `count = 5` chưa chạy. Lần sau constructor hoàn tất thì count là 5.

**Khuyến nghị:** Tránh gọi overridable instance methods từ constructor, đặc biệt những method phụ thuộc subclass state. Constructor nên đảm bảo invariants trước khi object được công bố.

## 9. Nếu constructor ném exception thì chuyện gì xảy ra?

Một constructor có thể ném exception trong quá trình tạo object. Expression `new ...` không trả về một instance bình thường cho caller nếu construction kết thúc đột ngột.

Tạo **`ConstructionFailureDemo.java`**:

```java
class Ticket {
    Ticket(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException(
                    "negative amount");
        }
        System.out.println("ticket constructed");
    }
}

public class ConstructionFailureDemo {
    public static void main(String[] args) {
        try {
            new Ticket(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        new Ticket(3);
    }
}
```

```bash
javac ConstructionFailureDemo.java
java ConstructionFailureDemo
```

```text
negative amount
ticket constructed
```

Đối tượng được cấp phát cho lần construction lỗi không được trả về thành một reference sử dụng bình thường từ biểu thức new. Tuy nhiên, nói “nó chắc chắn biến mất ngay lập tức” là quá mạnh: constructor có thể **làm rò `this`** qua static field/listener/callback trước khi ném exception, dẫn đến một partially initialized object còn reachable.

**Bài học về thiết kế:** Kiểm đầu vào sớm, không publish `this` trước khi invariants hoàn tất và cân nhắc factory khi creation có nhiều bước có thể thất bại.

## 10. Sử dụng đối tượng: gọi method, đọc/ghi fields, giữ references

Sau construction, client có thể:

- Gọi instance methods qua reference.
- Đọc state qua methods/getters phù hợp.
- Thay state nếu class cho phép.
- Lưu reference trong biến khác, instance field, static field, collection, array hoặc closure.
- Truyền reference vào methods/constructors.
- Trả reference cho caller.
- Chia sẻ reference cho thread khác (với thread-safety/safe-publication considerations).

Tạo **`ObjectUsageDemo.java`**:

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}

public class ObjectUsageDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println(counter.value());
    }
}
```

```bash
javac ObjectUsageDemo.java
java ObjectUsageDemo
```

```text
2
```

`Counter` object tồn tại qua nhiều method calls; Java không tạo Counter mới khi gọi `increment()`. Instance field count thuộc **cùng object**, nên state tích lũy.

Trong ví dụ này chạy một thread. Nếu nhiều threads gọi increment cùng lúc, `count++` không tự atomic; lifecycle/reachability không đồng nghĩa thread safety.

## 11. Truyền tham trị trong Java: object không tự bị sao chép

Java truyền **giá trị** của arguments vào parameters. Với reference types, giá trị được copy là **reference value**.

Tạo **`ReferenceParameterDemo.java`**:

```java
class Counter {
    int count;
}

public class ReferenceParameterDemo {
    static void changeState(Counter parameter) {
        parameter.count = 7;
    }

    static void replaceLocalReference(Counter parameter) {
        parameter = new Counter();
        parameter.count = 99;
    }

    public static void main(String[] args) {
        Counter original = new Counter();

        changeState(original);
        System.out.println(original.count);

        replaceLocalReference(original);
        System.out.println(original.count);
    }
}
```

```bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
```

```text
7
7
```

`changeState` sử dụng reference được copy để mutate object chung. `replaceLocalReference` chỉ gán lại parameter cục bộ của method cho object mới; biến `original` vẫn trỏ object cũ.

**Hệ quả vòng đời:** Object mới được tạo trong `replaceLocalReference` có thể không còn reachable sau khi method trả về nếu không có nơi nào giữ nó. Nhưng việc rời method không buộc GC chạy ngay.

## 12. Identity của object và equality của state

Hai objects khác nhau có thể có state giống nhau và `equals()` true nếu class định nghĩa value equality. `==` giữa references vẫn so **cùng object identity**.

Tạo **`IdentityAndEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class IdentityAndEqualityDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point alias = a;

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a == alias);
    }
}
```

```bash
javac IdentityAndEqualityDemo.java
java IdentityAndEqualityDemo
```

```text
false
true
true
```

`a` và `b` là hai record objects khác identity dù equal theo components; `alias` cùng reference a. Để suy luận reachability, **reference identity và đường tham chiếu** mới là yếu tố trọng tâm, không phải `equals`.

Một HashSet giữ record bằng value có thể chọn lưu một instance trong hai objects equal; điều đó không thay đổi quy tắc GC dựa vào references thực sự nằm trong object graph.

## 13. Từ một local variable sang field của object khác

Reference có thể “thoát” khỏi nơi tạo bằng cách được lưu vào field của object còn sống.

Tạo **`ReferenceEscapeDemo.java`**:

```java
class Note {
    final String text;

    Note(String text) {
        this.text = text;
    }
}

class Notebook {
    private Note saved;

    void save(Note note) {
        saved = note;
    }

    String read() {
        return saved.text;
    }
}

public class ReferenceEscapeDemo {
    static void createAndSave(Notebook notebook) {
        Note local = new Note("remember");
        notebook.save(local);
    }

    public static void main(String[] args) {
        Notebook notebook = new Notebook();

        createAndSave(notebook);
        System.out.println(notebook.read());
    }
}
```

```bash
javac ReferenceEscapeDemo.java
java ReferenceEscapeDemo
```

```text
remember
```

Sau khi `createAndSave` return, local variable `local` không còn trong scope. Nhưng Note object vẫn reachable qua:

```text
notebook reference
      |
      v
  Notebook.saved ----> Note("remember")
```

**Kết luận:** Scope của biến tạo object và lifetime của object không phải một.

## 14. Collection có thể kéo dài vòng đời của object

Nếu một collection còn reachable giữ **strong reference** tới object, object đó thường vẫn reachable qua collection.

Tạo **`CollectionRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> items = new ArrayList<>();

        StringBuilder builder =
                new StringBuilder("stored");
        items.add(builder);
        builder = null;

        System.out.println(items.get(0).toString());

        items.clear();
        System.out.println(items.isEmpty());
    }
}
```

```bash
javac CollectionRetentionDemo.java
java CollectionRetentionDemo
```

```text
stored
true
```

Sau `builder = null`, List vẫn giữ object. `items.clear()` loại bỏ references từ list. Nếu không có strong references khác, builder object **có thể trở thành** unreachable; code không thể đoán GC đã thu hồi ngay hay chưa.

Với cache, queue, map hoặc listener registry, hãy quản lý **removal/eviction policy**. Đối tượng “không dùng nữa về nghiệp vụ” nhưng vẫn nằm trong collection sống sẽ tiếp tục được giữ bộ nhớ.

## 15. Reachability là gì?

Một object được coi là reachable nếu có một đường tham chiếu thích hợp từ các nguồn mà runtime xem là đang sống, thường gọi là **GC roots** trong mô hình giải thích garbage collection.

Những nguồn hay được mô tả gồm:

- Local variables/arguments còn live trong các threads đang chạy.
- Static fields của classes còn được runtime xem là live.
- Thread-related objects và tham chiếu từ các runtime structures.
- References được giữ qua JNI/native handles và các cơ chế VM khác.
- Object fields/array elements đi từ những references trên.

Đây là **mô hình khái niệm**: root set và liveness optimization cụ thể là chuyện của JVM/collector, không phải một API Java bảo đảm mọi local variable luôn là root cho đến dấu `}`.

**Điểm đáng nhớ:** GC quan tâm **khả năng truy cập object qua graph references**, không quan tâm object “hữu ích cho doanh nghiệp” hay không.

## 16. Sơ đồ object graph và các đường giữ sống

```text
GC roots
   |
   +----> AppState
   |          |
   |          +----> UserSession ----> Profile
   |
   +----> live local list ----> Item A
   |                            |
   |                            +----> Item B
   |
   +----> static cache ----> CachedResult
```

Nếu Profile không có direct local variable nhưng vẫn có đường từ AppState → UserSession → Profile, nó reachable. Nếu Item A và Item B chỉ còn tham chiếu lẫn nhau nhưng **không có đường từ root**, chúng có thể được GC thu hồi.

Sự hiện diện của một reference bên trong object đã unreachable **không tự biến object ấy thành root**.

## 17. Gán `null` chỉ xóa một đường tham chiếu

Tạo **`NullDoesNotDestroyDemo.java`**:

```java
class Item {
    final String id;

    Item(String id) {
        this.id = id;
    }
}

public class NullDoesNotDestroyDemo {
    public static void main(String[] args) {
        Item a = new Item("A");
        Item b = a;

        a = null;
        System.out.println(b.id);

        b = null;
        System.out.println("references cleared");
    }
}
```

```bash
javac NullDoesNotDestroyDemo.java
java NullDoesNotDestroyDemo
```

```text
A
references cleared
```

Sau `a = null`, b vẫn trỏ Item. Sau `b = null`, **trong mô hình đơn giản của chương trình này** không còn reference nào được giữ có thể dùng để truy cập Item từ các biến đó.

Nhưng không có một “destructor” chạy tự động ngay tại `b = null`. Java chỉ làm assignment; collector tự quyết định tiến trình dọn dẹp bộ nhớ.

**Đừng thêm `x = null` ở cuối mọi method như một thói quen.** Khi scope/liveness tự nhiên đủ ngắn, các assignments vô ích chỉ làm code rối; quan trọng hơn là không giữ references ngoài ý muốn trong caches, collections hoặc long-lived fields.

## 18. Scope biến khác reachability thực tế

Một biến cục bộ có lexical scope theo source code, nhưng VM/JIT có thể xác định object không còn cần thiết trước khi biến ra khỏi scope. Ngược lại, object có thể được return hoặc lưu vào field và sống lâu hơn method tạo ra.

Hãy phân biệt:

| Khái niệm | Câu hỏi |
| --- | --- |
| Lexical scope | Tên biến còn được phép sử dụng ở dòng code nào? |
| Definite assignment | Biến đã được gán hợp lệ trước khi đọc chưa? |
| Reference liveness | Giá trị tham chiếu còn có thể được dùng cần thiết không? |
| Object reachability | Object còn nằm trên đường tham chiếu từ roots thích hợp không? |
| Garbage collection | VM đã quyết định/tiến hành dọn object chưa? |

Không thể chỉ nhìn vị trí dấu `}` trong source rồi kết luận tại đó GC sẽ hủy object. Sự tối ưu hóa của JVM, thread scheduling và các references khác đều có thể ảnh hưởng.

## 19. Hai objects tham chiếu vòng nhau vẫn có thể được thu gom

Trong reference-counting đơn giản, vòng tham chiếu là khó khăn: mỗi object còn có một reference từ object kia. Garbage collection của Java **không chỉ đếm reference của từng object**; tracing collectors có thể nhận diện cả group unreachable.

Tạo **`CyclicReferencesDemo.java`**:

```java
class Node {
    Node next;
}

public class CyclicReferencesDemo {
    public static void main(String[] args) {
        Node first = new Node();
        Node second = new Node();

        first.next = second;
        second.next = first;

        System.out.println(first.next == second);
        System.out.println(second.next == first);

        first = null;
        second = null;

        System.out.println("cycle no longer held here");
    }
}
```

```bash
javac CyclicReferencesDemo.java
java CyclicReferencesDemo
```

```text
true
true
cycle no longer held here
```

Sau hai assignments, nếu không có external reference khác, **cả hai Node objects dù trỏ nhau đều có thể trở thành unreachable từ roots** và có thể được GC thu hồi.

Không nên suy rằng cycle gây memory leak chỉ vì hai objects giữ nhau. Memory retention xảy ra nếu **vẫn có đường từ root** tới nhóm objects, ví dụ một static list đang giữ first.

## 20. GC eligibility và bộ nhớ thật sự được thu hồi không trùng thời điểm

Khi object không còn strongly reachable, ta thường nói object có thể trở thành **eligible for garbage collection**. Nhưng:

- JVM không bắt buộc chạy GC ngay.
- JVM không bắt buộc thu hồi object ngay ở một safepoint cụ thể.
- Memory usage không cần giảm ngay trên công cụ quan sát.
- JVM có thể giữ lại heap đã cấp phát để phục vụ allocations sau.
- Thời điểm object không còn reachable có thể không quan sát trực tiếp bằng Java application logic.

Tập hợp khái niệm:

```text
Không còn đường tham chiếu mạnh thích hợp
        !=
GC đã chạy
        !=
heap committed memory đã giảm
        !=
OS memory được trả về ngay
```

**Vì thế:** Không viết unit test kiểu “gán null → memory phải giảm ngay” hoặc “`System.gc()` → object phải biến mất ngay”.

## 21. `System.gc()` chỉ là yêu cầu/đề nghị

Java cung cấp `System.gc()`, nhưng không nên xem nó là lệnh đảm bảo collection hoàn tất vào thời điểm gọi.

Tạo **`GarbageCollectionRequestDemo.java`**:

```java
public class GarbageCollectionRequestDemo {
    public static void main(String[] args) {
        byte[] data = new byte[1024];

        System.out.println(data.length);
        data = null;

        System.gc();

        System.out.println("GC was requested");
    }
}
```

```bash
javac GarbageCollectionRequestDemo.java
java GarbageCollectionRequestDemo
```

```text
1024
GC was requested
```

Output chỉ chứng minh lệnh gọi và dòng print đã thực hiện. Nó **không** chứng minh byte[] đã được thu gom.

Tùy JVM flags/implementation, gọi GC explicit có thể bị bỏ qua hoặc có behavior khác nhau. Không dựa vào `System.gc()` để đóng files, socket connections hoặc khống chế chính xác vòng đời đối tượng.

## 22. `null` reference và lỗi `NullPointerException`

`null` không phải một instance object. Nếu một biến `null` được dùng để gọi instance method/đọc instance field trực tiếp, thao tác dereference thường gây `NullPointerException`.

Tạo **`NullReferenceDemo.java`**:

```java
public class NullReferenceDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("hi");
        text = null;

        System.out.println(text == null);

        try {
            text.append("!");
        } catch (NullPointerException ex) {
            System.out.println("cannot dereference null");
        }
    }
}
```

```bash
javac NullReferenceDemo.java
java NullReferenceDemo
```

```text
true
cannot dereference null
```

`text = null` chỉ đổi giá trị biến. Việc gọi `text.append(...)` sau đó mới gây lỗi vì không có object receiver.

**Không nhầm `null` với object đã bị GC thu gom**. Code không thể giữ một reference mạnh hợp lệ trỏ vào “vùng nhớ object đã free” rồi dùng như con trỏ C thông thường; JVM quản lý reachability và memory safety.

## 23. Object lifetime khác Java source block lifetime

Tạo **`ReturnReferenceDemo.java`**:

```java
class Message {
    final String text;

    Message(String text) {
        this.text = text;
    }
}

public class ReturnReferenceDemo {
    static Message create() {
        Message local = new Message("returned");
        return local;
    }

    public static void main(String[] args) {
        Message message = create();

        System.out.println(message.text);
    }
}
```

```bash
javac ReturnReferenceDemo.java
java ReturnReferenceDemo
```

```text
returned
```

Local variable `local` không còn sau khi create return, nhưng reference được trả về cho caller. Object tiếp tục reachable từ `message`.

**Hãy phân biệt:** Object được tạo **ở đâu** không nhất thiết quyết định object sống **bao lâu**. Một factory tạo object rồi trả về có thể tạo ra một object sống trong phần lớn thời gian chạy ứng dụng.

## 24. Static field có thể giữ một object tồn tại rất lâu

Một static field có thể giữ strong reference trong thời gian class/runtime structure liên quan còn live.

Tạo **`StaticRetentionDemo.java`**:

```java
class Registry {
    static StringBuilder current;
}

public class StaticRetentionDemo {
    public static void main(String[] args) {
        StringBuilder local =
                new StringBuilder("cached");

        Registry.current = local;
        local = null;

        System.out.println(Registry.current);

        Registry.current = null;
        System.out.println(
                Registry.current == null);
    }
}
```

```bash
javac StaticRetentionDemo.java
java StaticRetentionDemo
```

```text
cached
true
```

`local = null` không làm StringBuilder unreachable khi `Registry.current` còn giữ nó. Khi static field cũng được clear, reference path đó biến mất.

**Lỗi ứng dụng thường gặp:** Một static Map/List vô hạn, listener registration không được hủy, cache thiếu TTL/eviction, hoặc ThreadLocal không được remove trong thread pool có thể giữ object graph lớn ngoài ý muốn.

## 25. Rò rỉ bộ nhớ trong ngôn ngữ có GC có nghĩa gì?

Trong Java, *memory leak* ở mức application thường là **giữ các objects không còn hữu ích nhưng vẫn reachable**; collector không được thu hồi chúng vì references chưa được giải phóng.

Ví dụ pattern xấu:

```java
class History {
    private static final java.util.List<byte[]> ENTRIES =
            new java.util.ArrayList<>();

    static void add(byte[] data) {
        ENTRIES.add(data);
    }
}
```

Đây là **mảnh khai báo minh họa**, không phải khuyến nghị. Nếu chương trình gọi add liên tục không có giới hạn, ENTRIES có thể giữ ngày càng nhiều arrays.

Cách giảm retention thường là:

- Xác định kích thước/TTL/eviction của cache.
- Xóa entries khi hoàn thành workflow.
- Unregister callbacks/listeners khi không còn cần.
- Clear ThreadLocal values trong `finally` với threads tái sử dụng.
- Không giữ reference đến request/session objects trong singleton không cần thiết.
- Dùng heap dump/profiler khi có bằng chứng để tìm root → object reference paths.

**GC không thể sửa logic vẫn giữ strong references** cho dữ liệu không còn hữu ích.

## 26. Object references trong mảng/collections cũng giữ object sống

Không chỉ local variables và fields đơn: các array elements, map keys/values, list elements cũng là các reference edges.

Tạo **`ArrayReferenceRetentionDemo.java`**:

```java
public class ArrayReferenceRetentionDemo {
    public static void main(String[] args) {
        Object[] slots = new Object[2];

        Object item = new Object();
        slots[0] = item;

        System.out.println(slots[0] == item);

        item = null;
        System.out.println(slots[0] != null);

        slots[0] = null;
        System.out.println(slots[0] == null);
    }
}
```

```bash
javac ArrayReferenceRetentionDemo.java
java ArrayReferenceRetentionDemo
```

```text
true
true
true
```

Sau `item = null`, `slots[0]` giữ reference. Khi `slots[0] = null`, edge ấy biến mất.

**Khi tự triển khai container** như array-backed stack, hãy clear các slots không còn dùng nếu chúng giữ objects không cần thiết. Những Java collection implementations phổ biến tự quản lý nhiều trường hợp; vấn đề thường là giữ container hoặc elements quá lâu về nghiệp vụ.

## 27. Object bị tham chiếu mạnh qua lambda/callback

Một lambda/anonymous object có thể capture giá trị reference, làm object tiếp tục reachable nếu callback còn được giữ ở nơi sống lâu.

Tạo **`LambdaCaptureDemo.java`**:

```java
class CallbackStore {
    static Runnable callback;
}

public class LambdaCaptureDemo {
    public static void main(String[] args) {
        StringBuilder builder =
                new StringBuilder("hello");

        Runnable saved = () ->
                System.out.println(builder.toString());

        CallbackStore.callback = saved;
        CallbackStore.callback.run();

        CallbackStore.callback = null;
        System.out.println("callback cleared");
    }
}
```

```bash
javac LambdaCaptureDemo.java
java LambdaCaptureDemo
```

```text
hello
callback cleared
```

Lambda capture biến `builder` effectively final (không gán lại builder). Nếu callback được lưu trong một static field, callback còn có thể giữ builder qua captured reference. Clear callback field loại một retention path; các references khác vẫn có thể tồn tại.

**Không kết luận** builder đã GC ngay sau callback cleared; ví dụ chỉ minh họa một đường tham chiếu có thể được giữ hoặc loại bỏ.

## 28. Vòng đời tham chiếu giữa nhiều threads

Một object có thể được tạo trong thread A nhưng được đưa vào queue hay field để thread B sử dụng. Object không mất khi method ở thread A kết thúc nếu thread B còn giữ đường reference sống đến object.

**Tách hai mối quan tâm:**

- **Reachability:** Object còn có thể được dùng bởi một thread qua references thích hợp.
- **Visibility/thread safety:** Thread B có quan sát đúng state do thread A cập nhật không? Điều này thuộc Java Memory Model, synchronization và safe publication.

Một object được GC giữ sống **không có nghĩa** các thao tác trên mutable fields tự thread-safe.

### Ví dụ immutable data để truyền giữa threads

Tạo **`ThreadReferenceDemo.java`**:

```java
record Task(String description) {
}

public class ThreadReferenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Task task = new Task("run");

        Thread worker = new Thread(() ->
                System.out.println(task.description()));

        worker.start();
        worker.join();

        System.out.println("worker completed");
    }
}
```

```bash
javac ThreadReferenceDemo.java
java ThreadReferenceDemo
```

```text
run
worker completed
```

Thread lambda giữ reference đến task. `join()` giúp main chờ worker hoàn tất, khiến output này ổn định. Record có String component là example dữ liệu immutable phù hợp; với mutable shared state phải có concurrency policy riêng.

## 29. Weak reference: theo dõi object mà không giữ strong ownership

Java cung cấp `java.lang.ref.WeakReference<T>`. Weak reference không ngăn GC thu gom object nếu object **chỉ còn weakly reachable** theo quy tắc reference processing. Nó phù hợp một số caches/metadata mappings mà lifetime không nên bị giữ chỉ bởi tracking structure.

**Nhưng:** `weakReference.get()` có thể trả T hoặc null tùy GC; không viết test đoán chính xác GC scheduling.

Tạo **`WeakReferenceConceptDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceConceptDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println(weak.get() != null);

        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("strong variable cleared");
    }
}
```

```bash
javac WeakReferenceConceptDemo.java
java WeakReferenceConceptDemo
```

```text
true
strong variable cleared
```

`Reference.reachabilityFence(strong)` đảm bảo referent vẫn strongly reachable đến fence, nên phép đọc ngay trước đó được bảo vệ. Sau `strong = null`, không có cam kết lúc nào weak reference sẽ được clear.

**Không làm:** `System.gc(); assert weak.get() == null;`. Kết quả là nondeterministic và có thể fail trên JVM hợp lệ.

## 30. Soft, weak, phantom references giải quyết nhu cầu khác nhau

Trong `java.lang.ref` có các khái niệm reachability và reference objects phục vụ những use cases chuyên biệt:

| Loại | Ý tưởng | Lưu ý |
| --- | --- | --- |
| Strong reference | Sử dụng object bình thường | Có thể giữ object reachable |
| `SoftReference<T>` | Có thể được clear theo chính sách memory pressure | Không nên dựa làm cache policy chính xác |
| `WeakReference<T>` | Không giữ referent sống khi chỉ còn weak reachability | `get()` có thể chuyển từ value sang null |
| `PhantomReference<T>` | Theo dõi giai đoạn sau khi referent không còn accessible theo cách thông thường | `get()` luôn trả null; thường phối hợp ReferenceQueue |
| `ReferenceQueue<T>` | Nhận thông báo reference objects được enqueue khi JVM xử lý | Không bảo đảm thời điểm cố định |

Các loại này không phải giải pháp mặc định cho phần lớn business classes. Chúng chủ yếu xuất hiện ở cache designs, resource tracking, reachability-sensitive frameworks và runtime infrastructure.

**Phạm vi bài này:** Nhận ra các reference strengths để hiểu object lifetime. Đừng vội dùng `PhantomReference` hay tự viết cleanup infrastructure khi `try-with-resources` đã giải quyết resource scope đơn giản hơn.

## 31. `WeakHashMap` và retention: hiểu đúng key/value

`WeakHashMap<K,V>` có weak keys, nên key không nhất thiết được giữ sống chỉ vì map. Tuy nhiên:

- Value thường được giữ bằng strong reference trong entry khi entry còn tồn tại.
- Nếu value **gián tiếp giữ strong reference về chính key**, key có thể vẫn strongly reachable từ map → value → key, làm yếu đi mục tiêu weak key eviction.
- Việc xóa entries phụ thuộc GC/reference processing và map operations, không là deadline chính xác.
- WeakHashMap không thay thế cache size/TTL policy khi ứng dụng cần deterministic eviction.

**Không suy rằng “dùng WeakHashMap là chắc chắn không leak”.** Hãy kiểm toàn bộ graph và ownership.

## 32. `Reference.reachabilityFence` giải quyết một trường hợp chuyên sâu

VM có thể xác định một referent object không còn cần thiết trước cuối lexical scope. Trong resource wrappers hoặc đoạn code tương tác native resource, đôi khi ta cần bảo đảm object còn **strongly reachable tới một điểm xác định**, ngay cả khi không còn ordinary Java use.

`Reference.reachabilityFence(object)` hỗ trợ tình huống đó.

**Không lạm dụng:** Với code application thông thường, gọi method trên object rồi dùng references trong scope đã đủ rõ. `reachabilityFence` là công cụ chuyên biệt cho semantics tương tác reachability/finalization/cleanup, không phải một lệnh “giữ object sống vĩnh viễn” hoặc cơ chế giải phóng bộ nhớ.

Nếu dùng, đặt fence **sau thao tác cuối thực sự cần object còn reachable**, và đảm bảo có strong reference đến object cần giữ tới chỗ gọi fence.

## 33. Garbage collection chỉ xử lý bộ nhớ, không tự đóng mọi tài nguyên

Một Java object có thể là wrapper cho resources bên ngoài heap:

- `FileInputStream`/`FileOutputStream` → file descriptors.
- `Socket` → network endpoints.
- JDBC `Connection`/`Statement`/`ResultSet` → connection handles.
- Locks, native allocations, memory mapped resources, transaction scopes.

Nếu wrapper object không còn reachable, GC có thể thu hồi **Java memory**; nhưng không có quyền suy rằng resource bên ngoài được đóng **đúng lúc**. Một số thư viện có cleanup fallback riêng, nhưng không nên phụ thuộc vào timing đó.

**Quy tắc chủ động:** Nếu type implements `AutoCloseable` hoặc `Closeable` và hợp đồng yêu cầu đóng, dùng `close()`/`try-with-resources` để xác định thời điểm release.

## 34. `try-with-resources` quản lý vòng đời resource xác định

Tạo **`TryWithResourcesDemo.java`**:

```java
class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void use() {
        System.out.println("used");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }
        System.out.println("after try");
    }
}
```

```bash
javac TryWithResourcesDemo.java
java TryWithResourcesDemo
```

```text
opened
used
closed
after try
```

`try-with-resources` gọi `close()` khi scope của try resource kết thúc, kể cả khi body ném exception theo rules. Nó quản lý **external resource lifetime**, còn DemoResource Java object có thể vẫn reachable hay không tùy references khác.

**Khác biệt cốt lõi:**

- `close()`: method cleanup chạy theo control flow có thể xác định.
- GC: quản lý memory/reachability không có deadline chính xác.
- `close()` không bắt buộc làm reference thành null hoặc object lập tức được GC.

## 35. Nhiều resources được đóng theo thứ tự ngược

Tạo **`MultipleResourcesDemo.java`**:

```java
class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class MultipleResourcesDemo {
    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac MultipleResourcesDemo.java
java MultipleResourcesDemo
```

```text
open A
open B
work
close B
close A
```

Java đóng resources theo **thứ tự ngược** với thứ tự khởi tạo thành công. Điều này hữu ích khi resource sau phụ thuộc resource trước.

Một resource đã close không có nghĩa Java object wrapper biến mất. Nếu giữ reference, bạn vẫn có thể gọi methods trên object, nhưng methods có thể báo “already closed” tùy contract.

## 36. Exception trong body và trong `close()`

Khi try body ném exception và close cũng ném, Java giữ exception chính và gắn exception do close dưới dạng **suppressed exception**.

Tạo **`SuppressedExceptionDemo.java`**:

```java
class FailingResource implements AutoCloseable {
    @Override
    public void close() {
        throw new IllegalStateException("close failed");
    }
}

public class SuppressedExceptionDemo {
    public static void main(String[] args) {
        try (FailingResource resource =
                     new FailingResource()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getSuppressed().length);
        }
    }
}
```

```bash
javac SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

```text
body failed
1
```

Không đồng nhất resource close exception với GC. Đây là **exception handling do Java language định nghĩa** trong quá trình control flow, giúp quản lý resource khi lỗi xảy ra.

## 37. `finalize()` không phải destructor đáng tin cậy

Java từng có finalization mechanism (`Object.finalize()`). Nhưng nó bị deprecated từ lâu và **deprecated for removal** trong các Java versions hiện đại. Nó có các vấn đề nghiêm trọng:

- Không có bảo đảm finalizer chạy vào thời điểm nào.
- Có thể không chạy trước khi chương trình kết thúc.
- Có nguy cơ làm object được **resurrected** nếu finalizer publish lại reference.
- Khó kiểm soát thread, concurrency và lỗi.
- Không phù hợp để đảm bảo tài nguyên quan trọng được đóng.
- Có tác động bảo mật và performance.

**Không viết** một class mới phụ thuộc `finalize()` để in “object destroyed” hay để đóng file. Những chương trình test đợi finalizer output là nondeterministic.

Đối với resources, dùng `AutoCloseable`/`try-with-resources`. Với fallback cleanup chuyên sâu cho một số native allocations, cân nhắc `Cleaner` theo contract Java và thiết kế cẩn trọng, nhưng cleanup fallback vẫn không có deadline thay cho explicit close.

## 38. `Cleaner` cũng không thay thế explicit cleanup

`java.lang.ref.Cleaner` cho phép đăng ký cleanup action gắn với một object's reachability. Nó phù hợp một số thư viện/native resource abstractions.

Tuy nhiên:

1. Cleanup action không nên giữ strong reference tới chính referent khiến cleanup không bao giờ được kích hoạt.
2. Thời điểm cleanup phụ thuộc reference processing và runtime scheduling.
3. Cleanup có thể không diễn ra trước khi process kết thúc.
4. Task cleanup nên idempotent và quản lý errors.
5. Nếu user cần đóng tài nguyên chắc chắn vào cuối block, cung cấp `close()` rõ ràng.

**Thiết kế thực tế:** `Cleaner` là fallback cho resource safety ở thư viện đặc biệt; **`try-with-resources` là đường chính** khi resource lifetime có thể xác định bằng application scope.

## 39. Đối tượng không còn reachable không có “callback hủy” tin cậy

Một số ngôn ngữ có deterministic destructors gọi khi scope kết thúc; Java không làm theo mô hình đó cho ordinary objects.

Tạo class:

```java
class Message {
    Message() {
        System.out.println("created");
    }
}
```

Nếu chỉ có constructor, output “created” không kéo theo một output đối xứng “destroyed” lúc biến rời scope. Không có destructors do Java gọi tự động khi reference-count giảm về 0.

**Đừng cố định nghĩa lifecycle bằng log từ GC/finalizers.** Hãy dùng explicit lifecycle operations như `start()/stop()`, `open()/close()` hoặc `AutoCloseable` khi cần.

## 40. Số lần tạo object và số lần sử dụng không đồng nhất

Một instance có thể được dùng nhiều lần mà không tạo mới:

```java
StringBuilder builder = new StringBuilder();
builder.append("A");
builder.append("B");
builder.append("C");
```

Đây là **mảnh minh họa**. Chỉ có một `new StringBuilder()` rõ ràng; ba lần append mutate cùng object.

Ngược lại, lặp:

```java
for (int i = 0; i < 3; i++) {
    new Object();
}
```

có ba class instance creation expressions được đánh giá trong ngữ nghĩa source. JVM có thể áp dụng tối ưu hóa không làm thay đổi observable behavior; không đoán thẳng số heap allocations vật lý hoặc GC actions từ số lần xuất hiện từ khóa `new`.

**Quy tắc profile:** Nếu performance thật sự quan trọng, dùng benchmark/profiler phù hợp thay vì suy đoán object allocation cost theo cú pháp.

## 41. Escape analysis và stack allocation: tránh tuyên bố tuyệt đối

Các JVM hiện đại có thể tối ưu hóa object creation qua escape analysis, scalar replacement hoặc các kỹ thuật khác. Điều này có nghĩa:

- Không được coi mọi `new` chắc chắn là một heap allocation tồn tại vật lý theo cách đơn giản.
- Không được tuyên bố một object Java “luôn sống trên stack” chỉ vì reference local.
- Java Language Specification định nghĩa behavior; implementation có quyền tối ưu miễn giữ semantics quan sát được.
- JVM flags, compiler tier và workload ảnh hưởng khả năng tối ưu.

**Mô hình học tập hợp lý:** Hình dung objects trên heap và references trỏ đến chúng để hiểu reachability; khi bàn hiệu năng/GC implementation, công nhận VM có thể làm khác ở nội bộ.

## 42. Vòng đời object có thể kết thúc đối với một owner nhưng không đối với toàn app

Ví dụ một request handler bỏ reference sau khi xử lý; nhưng một global cache, một event bus hoặc background task giữ reference đến request object. Với request handler, công việc đã hoàn tất; đối với GC, object vẫn reachable.

Hãy đặt câu hỏi về **ownership**:

- Ai tạo object?
- Ai được phép giữ reference?
- Có transfer ownership hay shared ownership?
- Khi xong, cấu trúc nào phải clear/remove reference?
- Có callback/task/closure giữ resource owner không?
- Đối tượng có đóng được resource dù chính object vẫn sống không?

Không nên dùng `null` assignment như **ownership protocol**. Một API tốt cần làm rõ ai chịu trách nhiệm đóng hoặc giải phóng logical associations.

## 43. Ví dụ quản lý owner qua `close()` tách biệt reachability

Tạo **`ResourceOwnerDemo.java`**:

```java
class ResourceOwner implements AutoCloseable {
    private boolean closed;

    void work() {
        if (closed) {
            throw new IllegalStateException("already closed");
        }
        System.out.println("working");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ResourceOwnerDemo {
    public static void main(String[] args) {
        ResourceOwner owner = new ResourceOwner();

        owner.work();
        owner.close();

        System.out.println(owner != null);

        try {
            owner.work();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac ResourceOwnerDemo.java
java ResourceOwnerDemo
```

```text
working
closed
true
already closed
```

Sau `owner.close()`, object **vẫn reachable qua biến owner**, nhưng logical resource state là closed. Java object lifetime và resource usable lifetime là hai trục khác nhau.

### Mô hình hai trục

| Object reachable? | Resource open? | Có thể có? |
| --- | --- | --- |
| Có | Có | Có, khi đang sử dụng |
| Có | Không | Có, sau close |
| Không | Có | Có thể xảy ra do bỏ quên close; không an toàn |
| Không | Không | Có, nếu resource được close trước khi object mất reachability |

Đừng sử dụng GC làm cách chuyển trạng thái resource từ open sang closed khi phải có deadline.

## 44. Khi nào nên dùng `try-with-resources`?

Dùng khi resource type implements `AutoCloseable` và **bên nhận sở hữu tài nguyên** cần đóng khi kết thúc scope:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    String line = reader.readLine();
    // Xử lý line.
}
```

Đây là **mảnh code minh họa** cần biến `path` kiểu Path phù hợp trong method; không phải ví dụ standalone.

**Không đóng object mà bạn không sở hữu** chỉ vì nó AutoCloseable. Ví dụ stream/socket được caller quản lý có thể được truyền vào method; phải thống nhất contract ai close.

Hãy tránh cả hai lỗi:

1. Không close resource thuộc trách nhiệm của mình.
2. Close resource do người khác sở hữu rồi làm những callers tiếp theo lỗi.

## 45. Object pooling và tái sử dụng: đừng nhầm reused object với newly created

Một pool có thể trả lại instance đang tồn tại thay vì tạo instance mới. Vì vậy operation “mượn resource” không mặc nhiên tạo một Java object mới.

```java
Connection connection = dataSource.getConnection();
```

Đây là **mảnh ví dụ khái niệm**, cần các declarations/imports thích hợp. DataSource implementation có thể sử dụng connection pooling và trả một wrapper handle; không nên suy chính xác số Java objects, network connections được tạo từ một dòng code.

**Dù pooling**, phải tuân thủ contract `close()` của API; trong nhiều pool, close wrapper có thể trả connection về pool thay vì đóng physical connection. Điều cần đảm bảo là **release quyền sở hữu theo API**, không phải đoán nó tương ứng GC.

## 46. `WeakReference.get()` trả null không chứng minh file đã close

Nếu weak reference tới một resource wrapper trở thành null, điều đó cho biết referent không còn lấy được qua weak reference. Nó **không** chứng minh những external resources trước kia đã được giải phóng đúng hạn hoặc giao dịch được commit/rollback.

Cũng vậy:

- `System.gc()` không thay thế `commit()/rollback()/close()`.
- `finalize()` không là destructor đáng tin.
- `Cleaner` không thay thế explicit close deadline.
- Việc class có một field `closed = true` chỉ là trạng thái logic, phải đảm bảo close implementation thật sự làm đúng những việc cần thiết.

**Đánh giá correctness theo resource contract**, không theo bằng chứng gián tiếp về heap reachability.

## 47. Array cũng là đối tượng có vòng đời

Trong Java, arrays là objects. Ví dụ:

```java
int[] values = new int[3];
```

`values` là reference đến một array object. Array có length và elements; array references có thể được lưu, alias, truyền, gán null giống class instances.

Tạo **`ArrayLifecycleDemo.java`**:

```java
import java.util.Arrays;

public class ArrayLifecycleDemo {
    public static void main(String[] args) {
        int[] values = new int[3];
        int[] alias = values;

        alias[0] = 7;
        System.out.println(Arrays.toString(values));

        values = null;
        System.out.println(Arrays.toString(alias));
    }
}
```

```bash
javac ArrayLifecycleDemo.java
java ArrayLifecycleDemo
```

```text
[7, 0, 0]
[7, 0, 0]
```

Sau `values = null`, array vẫn reachable qua alias. Mặc dù elements là primitives, chính array vẫn là reference object có identity.

Với array of objects như `Person[]`, mỗi element là một reference field giữ object khác (hoặc null) và ảnh hưởng reachability của cả object graph.

## 48. Immutable object và mutable object đều chịu quản lý reachability

Một record hoặc immutable class giúp tránh việc thay đổi state sau construction. Nhưng tính immutable **không thay đổi quy tắc GC**.

Ví dụ:

```java
record Coordinate(int x, int y) {
}
```

Hai Coordinate instances có thể equal theo values nhưng có object identities khác nhau. Nếu còn strong reference từ root, một instance immutable vẫn reachable; nếu không còn, nó có thể được thu hồi.

**Tách bạch:**

- **Immutability**: state có thể thay đổi sau construction hay không.
- **Reachability**: object còn được truy cập qua references thích hợp không.
- **Resource lifecycle**: external resource cần được release khi nào.
- **Equality**: hai objects được xem là bằng nhau theo hợp đồng nào.

Những khái niệm này liên quan trong thiết kế nhưng không thay thế nhau.

## 49. Chuỗi câu hỏi chẩn đoán memory retention

Khi thấy heap tăng và nghi ngờ objects không được giải phóng, đừng lập tức thêm `System.gc()` hay null assignments. Hãy kiểm:

1. Có collections/maps/static caches giữ references không?
2. TTL/eviction/lifecycle của caches đúng không?
3. Có listener/observer nào quên unregister không?
4. Có thread pool task/queue giữ captured references không?
5. Có `ThreadLocal` chưa được remove khi thread tái sử dụng không?
6. Có session/request objects được gắn vào singleton không?
7. Có số lượng live objects thực sự tăng qua GC cycles không?
8. Có external resource leak không liên quan trực tiếp heap?
9. Có soft/weak references được dùng đúng semantics không?
10. Có đường root → object nào trong heap dump giải thích retention không?

**Dụng cụ phân tích thường dùng:** Java Flight Recorder (JFR), heap dump, memory profiler, GC logs, Java Mission Control hoặc diagnostic utilities phù hợp JVM. Cách dùng phụ thuộc môi trường và quyền truy cập.

Đừng đánh giá chỉ bằng một lần quan sát memory footprint của process: heap đã committed có thể được giữ lại để tái sử dụng ngay cả khi object count giảm.

## 50. Những kết luận sai phổ biến

| Khẳng định sai | Cách hiểu đúng |
| --- | --- |
| “Ra khỏi block là object bị hủy” | Biến hết scope không đồng nghĩa object hết mọi references |
| “Gán null lập tức chạy GC” | Null chỉ loại một reference edge |
| “Một object chỉ có một biến trỏ tới nó” | Nhiều references có thể alias cùng object |
| “`==` và `equals()` đều đo cùng object” | `==` là identity; equals tùy contract |
| “Java truyền object bằng tham chiếu” | Java truyền **giá trị reference** |
| “Mọi `new` đều chắc chắn cấp phát object vật lý trên heap” | VM có thể tối ưu khi giữ semantics |
| “Static field chỉ giữ dữ liệu nhỏ” | Static field có thể giữ cả object graph |
| “Collection không ảnh hưởng GC” | Strong element references có thể giữ objects |
| “Cycle reference luôn leak” | Tracing GC có thể thu nhóm unreachable có cycle |
| “GC thu ngay khi object không reachable” | Không có timing guarantee |
| “`System.gc()` bảo đảm bộ nhớ được trả về” | Chỉ là request/hint, phụ thuộc VM |
| “Không còn reference thì file chắc chắn đã close” | Resource cleanup là contract riêng |
| “`finalize()` là destructor chuẩn của Java” | Không đáng tin và deprecated for removal |
| “`Cleaner` luôn chạy trước khi app thoát” | Không có timing guarantee |
| “`close()` làm object biến mất” | Object có thể còn reachable sau close |
| “Object reachable thì chắc chắn resources open” | Có thể reachable nhưng đã closed |
| “Object immutable không cần GC” | Immutability độc lập reachability |
| “WeakReference giữ object sống mãi” | Weak reference không bảo đảm strong reachability |
| “WeakHashMap giải quyết mọi memory leak” | Values và reference paths khác vẫn có thể retain keys |
| “Lexical scope quyết định GC roots chính xác” | JVM liveness/optimization phức tạp hơn |
| “Thread-safe vì object chưa bị GC” | Reachability khác synchronization |
| “Log trong finalizer là cách đo lifetime chuẩn” | Finalizer scheduling nondeterministic |
| “Heap committed memory không giảm là object leak” | Heap có thể được giữ để tái sử dụng |

## 51. Ví dụ tổng hợp: tạo, alias, lưu, bỏ references

Tạo **`LifecycleWalkthroughDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Message {
    private final String text;

    Message(String text) {
        this.text = text;
        System.out.println("constructed:" + text);
    }

    String text() {
        return text;
    }
}

public class LifecycleWalkthroughDemo {
    public static void main(String[] args) {
        List<Message> inbox = new ArrayList<>();

        Message original = new Message("hello");
        Message alias = original;

        inbox.add(original);

        System.out.println(original == alias);
        System.out.println(inbox.get(0).text());

        original = null;
        alias = null;

        System.out.println(inbox.get(0).text());

        inbox.clear();
        System.out.println(inbox.isEmpty());
        System.out.println("no GC timing claim");
    }
}
```

```bash
javac LifecycleWalkthroughDemo.java
java LifecycleWalkthroughDemo
```

```text
constructed:hello
true
hello
hello
true
no GC timing claim
```

Diễn giải theo thời gian:

1. `new Message("hello")` tạo instance và constructor in một dòng.
2. `original` và `alias` trỏ cùng instance, nên `==` true.
3. `inbox.add(original)` tạo đường strong reference từ List đến instance.
4. Hai biến được gán null nhưng inbox vẫn giữ message.
5. `inbox.clear()` loại đường reference từ list.
6. Chương trình **không** giả định GC chạy/đã chạy sau clear.

Đây là cách mô tả **observable application behavior** mà không bịa một thời điểm destructor.

## 52. Self-test: kiểm reference semantics không phụ thuộc GC

Tạo **`ObjectLifecycleSelfTest.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Payload {
    final int id;

    Payload(int id) {
        this.id = id;
    }
}

public class ObjectLifecycleSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Payload original = new Payload(7);
        Payload alias = original;

        check(original == alias, "shared identity");

        List<Payload> holder = new ArrayList<>();
        holder.add(original);

        original = null;

        check(alias.id == 7, "alias still valid");
        check(holder.get(0) == alias, "list keeps same object");

        holder.clear();
        check(holder.isEmpty(), "holder cleared");

        alias = null;

        System.out.println("reference semantics PASS");
    }
}
```

```bash
javac ObjectLifecycleSelfTest.java
java ObjectLifecycleSelfTest
```

```text
reference semantics PASS
```

Các checks là deterministic: identity, alias và list ownership trong mã nguồn. Test không cần bật `-ea` vì `check` chủ động ném AssertionError.

**Không dùng weak-reference disappearance làm điều kiện PASS** cho một unit test bình thường; GC scheduling không phải một input kiểm soát được bằng cách gọi System.gc.

## 53. Bài tập 1: vẽ graph và đánh dấu reachability

Cho mảnh code:

```java
class Box {
    Box next;
}

Box a = new Box();
Box b = new Box();
Box c = new Box();

a.next = b;
b.next = c;

Box root = a;
a = null;
b = null;
c = null;
```

Đây là **mảnh minh họa** trong một method có Box declaration phù hợp.

**Câu hỏi:** Ba Box objects đã trở nên unreachable chưa?

**Đáp án:** Chưa chắc. `root` còn tham chiếu tới object a ban đầu; qua `root.next` và `root.next.next`, cả ba vẫn có đường reachable trong mô hình. Chỉ khi đường từ root bị mất (và không có root khác), cả nhóm mới có thể trở thành unreachable.

**Nâng cao:** Đổi `root.next = null` trước khi bỏ root. Khi đó b và c có thể trở thành một nhóm riêng unreachable nếu không có đường khác tới chúng, dù root vẫn giữ a.

## 54. Bài tập 2: tìm lỗi thiết kế resource lifecycle

Mã sau có vấn đề:

```java
void read() throws java.io.IOException {
    java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path);
    String line = reader.readLine();
    System.out.println(line);
}
```

Đây là **mảnh method minh họa** với biến `path` giả định hợp lệ.

Vấn đề: reader có thể không được close đúng lúc, nhất là khi readLine hoặc print ném exception. Không thể dựa vào GC của reader để đảm bảo resource kịp đóng.

### Bản sửa

```java
void read() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        String line = reader.readLine();
        System.out.println(line);
    }
}
```

Dùng `try-with-resources` để close theo control flow. Đây vẫn là **mảnh method**, muốn chạy cần một class và Path field/parameter thực tế.

## 55. Bài tập 3: phân biệt ba mốc lifecycle

Đặt tên cho những mốc sau:

1. `new Widget()` bắt đầu tạo instance.
2. `Widget w2 = w1` copy reference value.
3. `w1 = null` loại một reference.
4. `w2 = null` loại thêm một reference.
5. GC có thể thu hồi object lúc nào đó.
6. `resource.close()` trả resource về trạng thái closed.

**Đáp án:**

1. Object creation/initialization.
2. Reference aliasing.
3. Reference reassignment; chưa thể kết luận object unreachable.
4. Có thể trở thành unreachable nếu không có reference path nào khác.
5. Garbage collection không có deadline cố định từ source.
6. Explicit resource cleanup; không đồng nghĩa memory free.

## 56. Bài tập 4: phân tích constructor chain

Dự đoán output:

```java
class A {
    A() {
        System.out.println("A");
    }
}

class B extends A {
    B() {
        System.out.println("B");
    }
}

class C extends B {
    C() {
        System.out.println("C");
    }
}
```

Nếu `new C()`:

```text
A
B
C
```

Superclass constructors chạy trước subclass constructor bodies theo chain. Không có ba đối tượng độc lập A, B và C; tất cả là construction path của **một C instance**.

## 57. Checklist review vòng đời đối tượng

- [ ] Phân biệt rõ **object instance** và **reference variable**?
- [ ] Hiểu `new`, constructor và class initialization không đồng nhất?
- [ ] Nắm default values của fields trước initializers?
- [ ] Nắm superclass initialization trước subclass initialization?
- [ ] Không gọi overridable method từ constructor khi subclass state chưa sẵn sàng?
- [ ] Constructor validation bảo vệ invariants?
- [ ] Không publish `this` quá sớm trong construction?
- [ ] Hiểu Java truyền reference **theo giá trị**?
- [ ] Xác định được alias references đến một object?
- [ ] Phân biệt `==` và `equals()` khi vẽ object graph?
- [ ] Biết object có thể thoát ra khỏi local scope qua return/field/collection?
- [ ] Không gắn lifetime object với một biến local duy nhất?
- [ ] Nhận diện static caches, ThreadLocal, listeners, background tasks có thể giữ references?
- [ ] Biết cycle không tự gây leak nếu không còn đường từ GC roots?
- [ ] Không dựa vào `null` assignment để buộc GC chạy?
- [ ] Không dựa vào `System.gc()` để bảo đảm free?
- [ ] Không viết deterministic tests dựa vào weak reference phải được clear ngay?
- [ ] Hiểu soft/weak/phantom references ở mức cần thiết?
- [ ] Không dùng finalize làm destructor?
- [ ] Dùng `AutoCloseable`/`try-with-resources` khi sở hữu resource?
- [ ] Không close resource thuộc ownership của caller nếu không có contract?
- [ ] Phân biệt resource closed và object unreachable?
- [ ] Không suy runtime heap allocation vật lý tuyệt đối từ `new`?
- [ ] Với shared mutable object, xét safe publication/thread safety độc lập reachability?
- [ ] Khi nghi memory leak, kiểm đường root → object bằng công cụ phù hợp?
- [ ] Ví dụ runnable có tệp/public class, lệnh `javac`/`java`, stdout được kiểm?

## 58. Câu hỏi ôn tập có đáp án

**1.** Biến tham chiếu và object giống nhau không?

*Không. Reference variable chứa một reference value (hoặc null); object là instance được tham chiếu.*

**2.** `Person b = a` có tạo một Person mới không?

*Không, chỉ copy reference.*

**3.** `a = null` có hủy object ngay không?

*Không, chỉ gán lại reference variable.*

**4.** Nếu `b` vẫn trỏ object sau khi `a = null` thì object reachable không?

*Có, nếu b là live strong reference được chương trình còn sử dụng.*

**5.** Ra khỏi method tạo object có buộc object bị GC không?

*Không. Reference có thể được return hoặc lưu ngoài method.*

**6.** Nếu object không còn đường từ roots, GC chắc chắn thu ngay không?

*Không có timing guarantee.*

**7.** `System.gc()` có bảo đảm object được free không?

*Không.*

**8.** Object được tạo có thể có bao nhiêu references?

*Không có giới hạn một reference; nhiều biến/fields/array elements có thể cùng trỏ.*

**9.** Cycle A → B → A có luôn memory leak không?

*Không. Tracing GC có thể thu cả nhóm khi không còn reachable từ roots.*

**10.** Static field có thể giữ object lâu hơn local scope không?

*Có.*

**11.** Constructor body của subclass chạy trước superclass không?

*Không; superclass initialization path đi trước.*

**12.** Một instance field int chưa explicit initialize có giá trị ban đầu gì?

*0.*

**13.** Local variable int chưa được assign có được đọc thành 0 không?

*Không; phải definite assignment.*

**14.** Gọi overridable method từ superclass constructor có thể gây gì?

*Subclass override nhìn thấy subclass fields chưa explicit initialized, chỉ ở default state.*

**15.** Nếu constructor ném exception, new expression có trả object bình thường không?

*Không. Nhưng nếu this đã escape, reference tới object partially initialized vẫn có thể tồn tại.*

**16.** Đối tượng immutable có thể bị GC không?

*Có; immutability không quyết định reachability.*

**17.** `equals()` true có nghĩa là cùng object identity không?

*Không; `==` mới so reference identity.*

**18.** `WeakReference` có giữ referent mạnh không?

*Không; weak reference không bảo đảm object sống khi không còn strong reachability.*

**19.** Có nên assert weak.get()==null sau System.gc không?

*Không; GC không deterministic.*

**20.** `Reference.reachabilityFence` để làm gì?

*Bảo đảm referent còn strongly reachable đến một điểm trong control flow khi cần, nhất là resource/native scenarios.*

**21.** `close()` có đồng nghĩa object bị GC không?

*Không; close giải phóng logical/external resource theo contract, object vẫn có thể reachable.*

**22.** Khi có `AutoCloseable`, mẫu khuyến nghị là gì?

*Try-with-resources với ownership contract phù hợp.*

**23.** Nhiều resources trong try được close theo thứ tự nào?

*Ngược thứ tự khởi tạo thành công.*

**24.** Finalization có phải destructor đáng tin không?

*Không; deprecated for removal và không có timing guarantee.*

**25.** `Cleaner` có thay thế close deadline không?

*Không, phù hợp fallback chuyên sâu.*

**26.** Một list giữ object không dùng nữa có là memory retention không?

*Có thể; nếu list reachable và còn strong element reference, GC vẫn giữ object.*

**27.** Vì sao heap usage không giảm ngay sau GC không chắc là leak?

*JVM có thể giữ heap đã commit để tái sử dụng.*

**28.** Thread B dùng object do Thread A tạo có làm object sống qua method của A không?

*Có thể, nếu có reference path sống; cần safe publication cho mutable state.*

**29.** `new` luôn đồng nghĩa một heap allocation vật lý đo được không?

*Không được tuyên bố tuyệt đối; JVM có thể tối ưu miễn giữ observable semantics.*

**30.** Một câu tóm tắt vòng đời Java object là gì?

*Object được tạo và khởi tạo, được sử dụng qua references, có thể trở nên unreachable khi mất mọi đường tham chiếu mạnh thích hợp, và được GC thu hồi vào thời điểm JVM quyết định; external resources cần cleanup chủ động.*

## 59. Nguồn tham khảo chuẩn

- *Java Language Specification, Java SE 17 — `12 Execution:* https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html — class initialization, instance creation và initialization.
- *Java Language Specification, Java SE 17 — `15.9 Class Instance Creation Expressions:* https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9 — ngữ nghĩa `new` và constructor invocation.
- *Java API — `java.lang.ref`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html — reference objects và reachability concepts.
- *Java API — `java.lang.ref.Reference.reachabilityFence`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html — giữ referent strongly reachable đến một điểm code.
- *Java API — `AutoCloseable`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html — resource closing contract và try-with-resources.

---

**Ghi nhớ cuối bài:** Vòng đời Java object bắt đầu bằng **tạo/khởi tạo instance**, tiếp tục bằng **sử dụng thông qua một hoặc nhiều references**, rồi có thể chuyển sang trạng thái **không còn reachable** khi không còn đường tham chiếu mạnh thích hợp từ GC roots. **Gán null**, **ra khỏi method** hay **clear một collection** chỉ loại những đường tham chiếu cụ thể; không tự chứng minh object đã được GC. GC có thể thu hồi nhóm objects unreachable, kể cả cycles, nhưng **không hứa thời điểm thu hồi** hoặc lúc bộ nhớ trả về OS. Đặc biệt, **đóng resources không phải trách nhiệm của GC**: dùng `close()` và `try-with-resources` theo ownership contract. Hiểu rõ identity, aliasing, object graph, liveness và resource lifecycle sẽ giúp tránh leak, lỗi khởi tạo và những giả định sai về JVM.