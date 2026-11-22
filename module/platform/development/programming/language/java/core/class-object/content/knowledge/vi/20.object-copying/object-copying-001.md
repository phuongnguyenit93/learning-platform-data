# Gán tham chiếu khác tạo bản sao đối tượng trong Java

Trong Java, câu lệnh `b = a` với một **kiểu tham chiếu** không tạo object mới. Nó chỉ sao chép **giá trị tham chiếu**, khiến `a` và `b` cùng trỏ tới một object. Muốn có object thứ hai, phải dùng constructor, factory, clone hoặc một cơ chế tạo bản sao được thiết kế rõ ràng.

~~~java
Box a = new Box(10);
Box b = a;                  // Cùng Box object.
Box c = new Box(a.value()); // Box object khác.
~~~

Hai Box objects có thể cùng giá trị 10 nhưng khác **identity**. Càng quan trọng: nếu Box chứa một mutable Address/List, tạo Box mới **có thể vẫn chia sẻ Address/List cũ**. Đó là khác biệt giữa **aliasing**, **shallow copy** và **deep copy**.

Bài thuộc Java Core — **Class & Object / Sao chép đối tượng**, dùng Java 17+. Những chương trình độc lập có tên file, lệnh biên dịch/chạy và stdout. Đoạn mã không độc lập được nêu là minh họa.

## 1. Mục tiêu

Bạn sẽ:

- Hiểu object identity, reference variables và aliases.
- Biết `b = a` với reference không gọi constructor hoặc clone.
- Phân biệt sửa object và gán lại biến reference.
- Phân biệt `==` với `equals` và value equality.
- Hiểu Java luôn pass-by-value, kể cả object arguments.
- Tạo bản sao bằng constructor/factory.
- Phân biệt shallow copy, deep copy, structural snapshot và live view.
- Biết reference arrays và collections thường giữ cùng element references sau khi copy cấu trúc.
- Dùng `List.copyOf` và `ArrayList` đúng semantics.
- Hiểu lợi ích chia sẻ immutable objects và rủi ro alias với mutable objects.
- Hiểu `Object.clone`, `Cloneable` và những giới hạn của cloning.
- Sao chép graph có cycles/shared nodes bằng identity map.
- Xác định ownership, concurrency, polymorphism và test independence.

## 2. Tham chiếu là gì?

Một biến kiểu tham chiếu giữ reference value hoặc null, không chứa toàn bộ object như một struct được copy khi gán.

~~~java
class Box {
    int value;
}

Box a = new Box();
a.value = 10;
Box b = a;
~~~

Sơ đồ:

~~~text
a --------+
          |
          v
       Box #1
       value=10
          ^
          |
b --------+
~~~

Có hai variables nhưng **một** Box object. Sửa `b.value = 20` khiến `a.value` cũng là 20.

Nếu `b = new Box()`, b trỏ sang Box #2 và a vẫn trỏ Box #1. Java assignment cập nhật **giá trị trong biến b**, không tự cập nhật biến a.

## 3. Chương trình chạy: mutation và reassignment

Tạo **`ReferenceDemo.java`**:

~~~java
public class ReferenceDemo {
    static final class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter a = new Counter(5);
        Counter b = a;

        System.out.println("same=" + (a == b));
        b.increment();
        System.out.println("a=" + a.value());

        b = new Counter(100);
        System.out.println("same now=" + (a == b));
        System.out.println("a now=" + a.value());
        System.out.println("b now=" + b.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceDemo.java
java ReferenceDemo
~~~

Stdout:

~~~text
same=true
a=6
same now=false
a now=6
b now=100
~~~

`b.increment()` sửa Counter #1 do a và b cùng tham chiếu. `b = new Counter(100)` tạo Counter #2 rồi thay reference của b. Không có thay đổi nào đối với biến a.

## 4. Đếm số object được tạo

~~~java
Box a = new Box();
Box b = a;
Box c = new Box();
~~~

Có hai lời gọi `new Box()` nên hai Box objects; b không phải object thứ ba.

Tạo **`ConstructorCountDemo.java`**:

~~~java
public class ConstructorCountDemo {
    static final class Item {
        private static int created;

        Item() {
            created++;
        }

        static int created() {
            return created;
        }
    }

    public static void main(String[] args) {
        Item a = new Item();
        Item b = a;
        Item c = new Item();

        System.out.println("created=" + Item.created());
        System.out.println("a==b=" + (a == b));
        System.out.println("a==c=" + (a == c));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorCountDemo.java
java ConstructorCountDemo
~~~

Stdout:

~~~text
created=2
a==b=true
a==c=false
~~~

Đếm constructor chỉ minh họa `new`: một số cơ chế runtime khác như `Object.clone()` hay deserialization có đường tạo object riêng. Không lấy số lần constructor làm định nghĩa tổng quát của mọi cách tạo object trong JVM.

## 5. Reference assignment và object copy khác nhau trên sơ đồ

**Gán reference:**

~~~text
a ----+
      +----> Person #1 (name="Mai")
b ----+
~~~

**Tạo object mới:**

~~~text
a ----> Person #1 (name="Mai")
b ----> Person #2 (name="Mai")
~~~

Nếu tạo `b = new Person(a.name())`, hai Person objects riêng. Nhưng chúng có thể có cùng String name value. Phải tách ba câu hỏi:

1. `a == b`: cùng object reference hay không?
2. `a.equals(b)`: bằng nhau theo value/business contract hay không?
3. Mutation của a có ảnh hưởng b không? Phụ thuộc mutable state và nested references.

`equals` true **không chứng minh** một bản sao đã được deep-copy.

## 6. Copy constructor cho một object đơn giản

Tạo **`CopyConstructorDemo.java`**:

~~~java
import java.util.Objects;

public class CopyConstructorDemo {
    static final class Person {
        private String name;

        Person(String name) {
            this.name = Objects.requireNonNull(name);
        }

        Person(Person other) {
            this(other.name);
        }

        String name() {
            return name;
        }

        void rename(String value) {
            name = Objects.requireNonNull(value);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai");
        Person alias = original;
        Person copy = new Person(original);

        System.out.println("alias same=" + (alias == original));
        System.out.println("copy same=" + (copy == original));
        System.out.println("before=" +
                original.name() + "/" + copy.name());

        original.rename("An");
        System.out.println("after=" +
                original.name() + "/" + copy.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyConstructorDemo.java
java CopyConstructorDemo
~~~

Stdout:

~~~text
alias same=true
copy same=false
before=Mai/Mai
after=An/Mai
~~~

Copy constructor tạo Person mới. String là immutable, nên sharing initial String object không dẫn đến việc nội dung String bị sửa tại chỗ. Method rename chỉ gán Person.original.name sang một String khác.

## 7. `==` khác `equals`

Với references, `==` hỏi chúng có trỏ cùng object không. `equals` được class định nghĩa; nếu không override, Object.equals mặc định dựa trên identity. String/record thường có semantics value equality.

Tạo **`IdentityEqualityDemo.java`**:

~~~java
public class IdentityEqualityDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point alias = original;
        Point copy = new Point(original.x(), original.y());

        System.out.println("alias same=" +
                (original == alias));
        System.out.println("copy same=" +
                (original == copy));
        System.out.println("copy equals=" +
                original.equals(copy));
        System.out.println("hash equal=" +
                (original.hashCode() == copy.hashCode()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IdentityEqualityDemo.java
java IdentityEqualityDemo
~~~

Stdout:

~~~text
alias same=true
copy same=false
copy equals=true
hash equal=true
~~~

Point record có primitive components nên generated equals theo values. Nhưng với object graph có mutable references, `equals` true không đủ để kết luận nested objects đã được tách.

## 8. Gán lại reference không hủy object ngay

Nếu:

~~~java
Box a = new Box();
Box b = a;
b = null;
~~~

a vẫn tham chiếu Box. Gán b thành null không xóa Box hay chạy destructor ngay. Khi object không còn reachable từ GC roots, JVM có thể thu hồi bộ nhớ lúc phù hợp.

Tương tự:

~~~java
Box previous = a;
a = new Box();
~~~

previous vẫn trỏ object cũ. Object cũ có thể còn sống vì references khác, không phụ thuộc việc biến a đã được gán lại.

## 9. Java luôn truyền tham trị, kể cả object references

Khi truyền object vào method, Java sao chép **reference value** vào parameter local. Method có thể mutate shared object, nhưng **không** thay reference variable của caller chỉ bằng việc reassign parameter.

Tạo **`PassByValueDemo.java`**:

~~~java
public class PassByValueDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 99;
    }

    static void reassign(Box box) {
        box = new Box(700);
        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box caller = new Box(10);
        mutate(caller);
        System.out.println("after mutate=" + caller.value);

        reassign(caller);
        System.out.println("after reassign=" + caller.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PassByValueDemo.java
java PassByValueDemo
~~~

Stdout:

~~~text
after mutate=99
inside=700
after reassign=99
~~~

Method mutate sửa cùng Box instance. Method reassign thay **parameter local** sang Box khác; biến caller không đổi. Đây là pass-by-value, không phải pass-by-reference.

## 10. Reference đặt trong field vẫn là alias

~~~java
class Team {
    Member leader;

    Team(Member leader) {
        this.leader = leader;
    }
}
~~~

Nếu Team giữ nguyên reference tới Member argument, biến Member của caller và `team.leader` trỏ cùng object. Nếu Member mutable, Team có thể thấy mutation từ bên ngoài.

Điều này có thể **đúng** nếu Member là entity được chia sẻ có chủ đích. Nhưng nếu Team muốn immutable snapshot lúc tạo, cần copy relevant values vào một immutable representation.

**Không mặc định copy mọi entity reference.** Hãy xác định ownership và identity: chia sẻ cùng customer entity có thể đúng, nhưng chia sẻ mutable billing address như một immutable historical snapshot có thể sai.

## 11. `final` reference không biến assignment thành copy

~~~java
final Person original = new Person("Mai");
Person alias = original;
~~~

`final` chỉ ngăn gán lại biến original; nó không ngăn alias hay mutate Person state. Tương tự:

~~~java
final java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("Mai"); // Hợp lệ.
~~~

Một final reference tới mutable List không phải List immutable. `final field`, `final class` và deep immutability là những khái niệm riêng.

## 12. Shallow copy là gì?

**Shallow copy** thường tạo một top-level object mới, sao chép các field values:

- Primitive field → sao chép primitive value.
- Reference field → sao chép reference value, **không clone target object**.

~~~text
Original Person #1 ----address----+
                                   |
                                   v
                                Address #7
                                   ^
                                   |
Copy Person #2 --------address----+
~~~

Dù hai Person instances khác nhau, chúng dùng chung mutable Address. Vì vậy sửa city qua Person copy có thể ảnh hưởng original.

Shallow copy không luôn sai: nếu Address bất biến, sharing an toàn cho state. Vấn đề là **contract có yêu cầu independence của nested data hay không**.

## 13. Ví dụ chạy: shallow copy của Person–Address

Tạo **`ShallowCopyDemo.java`**:

~~~java
public class ShallowCopyDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person copy = original.shallowCopy();

        System.out.println("same Person=" + (original == copy));
        System.out.println("same Address=" +
                (original.address == copy.address));

        copy.address.city = "Da Nang";

        System.out.println("original city=" +
                original.address.city);
        System.out.println("copy city=" + copy.address.city);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
~~~

Stdout:

~~~text
same Person=false
same Address=true
original city=Da Nang
copy city=Da Nang
~~~

Copy top-level thành công nhưng Address vẫn shared. Bài học: `copy != original` chỉ xác minh top-level identity, **không** xác minh deep isolation.

## 14. Deep copy phải có phạm vi rõ

Một deep copy trong graph đơn giản có thể làm:

~~~java
Person deepCopy() {
    return new Person(name, new Address(address.city));
}
~~~

Đây là ví dụ method minh họa. Person và Address đều được tạo mới, String name immutable nên có thể share.

Nhưng nếu Address có List of Phones, hoặc graph có cycles, phải xét sâu hơn. Deep copy là **hợp đồng về mutable graph cần độc lập**, không phải ngôn ngữ Java cung cấp một lệnh sao chép mọi thứ.

### Ví dụ chạy: shallow và deep

Tạo **`ShallowVsDeepDemo.java`**:

~~~java
public class ShallowVsDeepDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address copy() {
            return new Address(city);
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person deepCopy() {
            return new Person(name, address.copy());
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person shallow = original.shallowCopy();
        Person deep = original.deepCopy();

        System.out.println("shallow same Address=" +
                (original.address == shallow.address));
        System.out.println("deep same Address=" +
                (original.address == deep.address));

        original.address.city = "Da Nang";

        System.out.println("original=" + original.address.city);
        System.out.println("shallow=" + shallow.address.city);
        System.out.println("deep=" + deep.address.city);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowVsDeepDemo.java
java ShallowVsDeepDemo
~~~

Stdout:

~~~text
shallow same Address=true
deep same Address=false
original=Da Nang
shallow=Da Nang
deep=Hue
~~~

Với graph Person→Address, deep copy đã tạo independent Address. Không suy rộng rằng nó đã copy mọi loại external resource hoặc arbitrary cycles.

## 15. Primitive arrays và reference arrays có hai mức copy khác nhau

~~~java
int[] a = {1, 2};
int[] b = a.clone();
~~~

b là array mới chứa primitive values riêng.

~~~java
Member[] a = {member};
Member[] b = a.clone();
~~~

b là array mới, nhưng `a[0] == b[0]` true; cả hai slots giữ same Member reference.

### Ví dụ chạy

Tạo **`ArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayCopyDemo {
    static final class Item {
        String name;

        Item(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        int[] primitives = {1, 2};
        int[] primitiveCopy = primitives.clone();
        primitiveCopy[0] = 9;
        System.out.println("primitive original=" +
                Arrays.toString(primitives));
        System.out.println("primitive copy=" +
                Arrays.toString(primitiveCopy));

        Item[] originals = {new Item("Mai")};
        Item[] referenceCopy = originals.clone();

        System.out.println("same arrays=" +
                (originals == referenceCopy));
        System.out.println("same item=" +
                (originals[0] == referenceCopy[0]));

        referenceCopy[0].name = "An";
        System.out.println("original item=" +
                originals[0].name);

        referenceCopy[0] = new Item("Binh");
        System.out.println("original now=" +
                originals[0].name);
        System.out.println("copy now=" +
                referenceCopy[0].name);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayCopyDemo.java
java ArrayCopyDemo
~~~

Stdout:

~~~text
primitive original=[1, 2]
primitive copy=[9, 2]
same arrays=false
same item=true
original item=An
original now=An
copy now=Binh
~~~

Sửa **element object** có thể ảnh hưởng cả hai reference arrays; thay **slot** ở array copy chỉ ảnh hưởng array copy.

## 16. Sao chép cấu trúc `List` không phải tạo lại phần tử

Với `List<Member> original`, biểu thức `new ArrayList<>(original)` tạo list **riêng**, nhưng những ô phần tử vẫn trỏ tới **cùng Member objects**. Thêm/xóa phần tử trong list mới không làm list nguồn thay đổi; mutate một `Member` được chia sẻ thì cả hai list cùng quan sát thay đổi đó.

## 17. `List.copyOf` tạo danh sách không sửa được, không tạo bản sao sâu

`List.copyOf(source)` cung cấp **unmodifiable structural snapshot** từ nguồn mutable và không cho thêm/xóa qua kết quả. Nhưng mutable element vẫn được giữ bằng reference. Nó có thể trả cùng instance nếu đầu vào đã thuộc một dạng unmodifiable phù hợp; đừng kiểm `source != snapshot` như một bảo đảm API.

## 18. View và snapshot có khác nhau không?

`Collections.unmodifiableList(source)` tạo **unmodifiable view**: caller không thêm/xóa qua view, nhưng sửa nguồn có thể phản ánh vào view. `List.copyOf(source)` là structural snapshot; thay đổi cấu trúc nguồn sau đó không phản ánh vào snapshot.

Chương trình ngắn **`ListCopyDecisionDemo.java`** minh họa **cả ba** khái niệm trong một phép thử:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListCopyDecisionDemo {
    static final class Task {
        String label;

        Task(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        List<Task> source = new ArrayList<>();
        source.add(new Task("A"));

        List<Task> shallow = new ArrayList<>(source);
        List<Task> snapshot = List.copyOf(source);
        List<Task> view = Collections.unmodifiableList(source);

        source.get(0).label = "X";
        source.add(new Task("B"));

        System.out.println("sizes=" + source.size() + "/" +
                shallow.size() + "/" + snapshot.size() + "/" + view.size());
        System.out.println("same child=" + (source.get(0) == shallow.get(0)));
        System.out.println("snapshot child=" + snapshot.get(0).label);
        try {
            snapshot.add(new Task("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListCopyDecisionDemo.java
java ListCopyDecisionDemo
~~~

~~~text
sizes=2/1/1/2
same child=true
snapshot child=X
snapshot is unmodifiable
~~~

**Kết luận cho bài gán tham chiếu:** Đừng suy “có từ copy là tất cả dữ liệu mới”. Cần phân biệt **identity của list**, **identity của các phần tử** và **chế độ cập nhật structure**. Các phép copy Map, array và nested elements đều đòi hỏi phân biệt tương tự; kiến thức về độ sâu được triển khai riêng khi chọn shallow/deep-copy policy.

## 19. Immutable objects thường không cần copy để bảo vệ state

String immutable:

~~~java
String a = "Java";
String b = a;
a = "Kotlin";
~~~

`b` vẫn là "Java". Lệnh gán lại a không sửa String object cũ.

### Ví dụ chạy: String và StringBuilder

Tạo **`ImmutableVsMutableDemo.java`**:

~~~java
public class ImmutableVsMutableDemo {
    public static void main(String[] args) {
        String a = "Hi";
        String b = a;
        a = a + "!";

        System.out.println("String a=" + a);
        System.out.println("String b=" + b);

        StringBuilder builder = new StringBuilder("Hi");
        StringBuilder alias = builder;
        alias.append("!");

        System.out.println("builder=" + builder);
        System.out.println("same=" + (builder == alias));

        StringBuilder copy =
                new StringBuilder(builder.toString());
        copy.append("?");

        System.out.println("builder after copy=" + builder);
        System.out.println("copy=" + copy);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
~~~

Stdout:

~~~text
String a=Hi!
String b=Hi
builder=Hi!
same=true
builder after copy=Hi!
copy=Hi!?
~~~

Sharing immutable String không gây nguy cơ mutable alias. Sharing StringBuilder có thể khiến cả hai references quan sát mutation.

## 20. Copy factory tạo immutable snapshot

Một mutable draft có thể chuyển thành record snapshot:

Tạo **`SnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SnapshotDemo {
    static final class Draft {
        private String title;
        private final List<String> tags = new ArrayList<>();

        Draft(String title) {
            this.title = title;
        }

        void rename(String next) {
            title = next;
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        String title() {
            return title;
        }

        List<String> tags() {
            return tags;
        }
    }

    record Snapshot(String title, List<String> tags) {
        Snapshot {
            tags = List.copyOf(tags);
        }

        static Snapshot from(Draft draft) {
            return new Snapshot(draft.title(), draft.tags());
        }
    }

    public static void main(String[] args) {
        Draft source = new Draft("First");
        source.addTag("java");

        Snapshot copy = Snapshot.from(source);

        source.rename("Second");
        source.addTag("object");

        System.out.println("source=" + source.title());
        System.out.println("copy=" + copy.title());
        System.out.println("source tags=" + source.tags());
        System.out.println("copy tags=" + copy.tags());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SnapshotDemo.java
java SnapshotDemo
~~~

Stdout:

~~~text
source=Second
copy=First
source tags=[java, object]
copy tags=[java]
~~~

Record Snapshot chứa String và List<String> immutable structure; các thay đổi sau của Draft không ảnh hưởng snapshot. Nếu elements mutable hoặc state được thread khác sửa trong khi copy, cần contract và cơ chế snapshot consistent mạnh hơn.

## 21. `Object.clone()`: tạo object mới nhưng shallow mặc định

`Object.clone()` có thể tạo một object khác, sao chép field values theo shallow semantics. Class thông thường cần hỗ trợ `Cloneable` và override clone nếu muốn public typed API.

Tạo **`CloneDemo.java`**:

~~~java
public class CloneDemo {
    static final class Details {
        String note;

        Details(String note) {
            this.note = note;
        }
    }

    static final class Item implements Cloneable {
        String name;
        Details details;

        Item(String name, Details details) {
            this.name = name;
            this.details = details;
        }

        @Override
        public Item clone() {
            try {
                return (Item) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        Item original = new Item("A", new Details("old"));
        Item copy = original.clone();

        System.out.println("same Item=" + (original == copy));
        System.out.println("same Details=" +
                (original.details == copy.details));

        copy.name = "B";
        copy.details.note = "new";

        System.out.println("original name=" + original.name);
        System.out.println("copy name=" + copy.name);
        System.out.println("original note=" +
                original.details.note);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CloneDemo.java
java CloneDemo
~~~

Stdout:

~~~text
same Item=false
same Details=true
original name=A
copy name=B
original note=new
~~~

Clone tạo top-level Item khác, nhưng nested Details vẫn shared.

### Vì sao thường nên ưu tiên copy constructor/factory?

`Object.clone()` không gọi constructor theo đường bình thường; copy final references và invariants có thể khó xử lý. `Cloneable` chỉ là marker interface, không tự khai báo public clone method. Copy constructor/factory cho phép kiểm soát validation và ownership rõ hơn.

## 22. Copy base class không tự preserve subtype

Constructors không override polymorphically. Với `Dog extends Animal`, `new Animal(dog)` tạo Animal, không tự giữ Dog.age hoặc runtime class Dog.

Tạo **`BaseCopyDemo.java`**:

~~~java
public class BaseCopyDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        Animal(Animal other) {
            name = other.name;
        }

        String name() {
            return name;
        }
    }

    static final class Dog extends Animal {
        private final int age;

        Dog(String name, int age) {
            super(name);
            this.age = age;
        }
    }

    public static void main(String[] args) {
        Animal original = new Dog("Milo", 3);
        Animal copy = new Animal(original);

        System.out.println("original class=" +
                original.getClass().getSimpleName());
        System.out.println("copy class=" +
                copy.getClass().getSimpleName());
        System.out.println("names=" +
                original.name() + "/" + copy.name());
        System.out.println("same object=" + (original == copy));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BaseCopyDemo.java
java BaseCopyDemo
~~~

Stdout:

~~~text
original class=Dog
copy class=Animal
names=Milo/Milo
same object=false
~~~

Đây là **base projection copy** chứ không phải copy giữ mọi subclass fields. Nếu cần preserve subtype, thiết kế instance method `copy()` có contract và test từng implementation hoặc hạn chế hierarchy bằng final/sealed types.

## 23. Một bản sao sâu có thể phải giữ cả quan hệ tham chiếu

Nếu trong graph nguồn có hai trường cùng trỏ **một** child, một thuật toán deep copy tạo child mới cho mỗi trường sẽ làm mất quan hệ `left == right`. Nếu các nodes còn tham chiếu ngược tạo **cycle**, đệ quy copy ngây thơ có thể không dừng.

Sơ đồ:

~~~text
Nguồn: root.left ──┐
                   ├──> shared child ──> root (cycle)
       root.right ─┘

Bản sao cần giữ topology:
copy.left ──────┐
                ├──> cloned child ────> copy
copy.right ─────┘
~~~

## 24. Quy tắc dừng và tái sử dụng clone của cùng node

Khi contract yêu cầu giữ object graph topology, dùng một bảng **original identity → copied node**, thường là `IdentityHashMap`. Thứ tự xử lý là:

1. Nguồn `null` → trả `null`.
2. Nguồn đã có trong map → trả **cùng clone** đã tạo.
3. Nguồn mới → cấp phát clone, **ghi mapping trước**, sau đó mới copy child references.
4. Với graph có vòng, khi quay lại node cũ thì map cắt vòng đệ quy.
5. Kiểm `original != copy`, `copy.left == copy.right`, và back-reference của clone trỏ clone tương ứng, **không** trỏ graph cũ.

Đây là **định hướng ranh giới** của bài nhập môn reference-vs-copy; xử lý BFS/DFS, alias topology, payload mutable và graph cycles được thực hành sâu khi thiết kế thuật toán graph copy. Không cần deep-copy cả services, file handles hoặc database connections chỉ vì chúng nằm trong fields.

## 25. Deep copy không tự nhân đôi live resources

Object có thể chứa sockets, file streams, database connections, threads, locks hoặc native handles. Những thứ ấy không có một deep-copy mặc định hợp lý. Domain copy policy phải xác định:

- Chỉ copy configuration data?
- Giữ shared reference tới resource?
- Mở resource mới?
- Hay từ chối copying resource owner?

Serialization/deserialization cũng không phải deep-copy utility tổng quát: còn vấn đề security, versioning, custom hooks, excluded state và runtime resources.

## 26. Copy và invariants

Một copy operation phải bảo toàn các điều kiện hợp lệ:

~~~java
final class Range {
    private final int start;
    private final int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
        this.start = start;
        this.end = end;
    }

    Range(Range other) {
        this(other.start, other.end);
    }
}
~~~

Đây là class minh họa; copy constructor đi qua validation. Nếu nhận source từ untrusted polymorphic interface với overridable getters, cần kiểm soát consistency và behavioral contract của getters.

Một copy thất bại không nên để caller nhìn thấy object đang xây dựng dở. Với graph copy two-phase nội bộ, chỉ publish kết quả sau khi hoàn tất, trừ khi API có contract rõ khác.

## 27. Concurrency: copy không tự tạo snapshot nhất quán

Nếu thread A đọc firstName, thread B sửa firstName/lastName, rồi A đọc lastName, copy có thể ghép hai phiên bản khác nhau. Deep copy bảo đảm object graph độc lập **sau khi hoàn thành** không đồng nghĩa đã đọc source atomically.

Tùy domain, dùng:

- Lock quanh toàn bộ snapshot và mutations.
- Immutable state replacement với safe publication.
- Versioned read/retry.
- DB transaction với isolation phù hợp.
- Copy-on-write/immutable data structures.

Không coi assignment, clone hay copy constructor tự là một synchronization primitive.

## 28. Copy-on-write không thay Java assignment

Copy-on-write (COW) là chiến lược nội bộ của container hoặc data structure: chỉ copy khi có mutation theo API. Ví dụ `CopyOnWriteArrayList` tạo bản sao internal array khi mutating operations theo contract.

Nhưng `CopyOnWriteArrayList<String> b = a;` vẫn là **reference assignment**, không tạo một second CopyOnWriteArrayList. COW nói về **cách object thực hiện mutation**, không thay semantics của toán tử `=`.

Immutable persistent collections cũng có thể dùng structural sharing an toàn giữa các versions, vì shared nodes là immutable.

## 29. Bảng so sánh

| Thao tác | Top-level object mới? | Nested objects có thể shared? |
| --- | --- | --- |
| `b = a` | Không | Toàn bộ là cùng object |
| `b = new Box(a.value)` | Có | Tùy fields được truyền |
| `b = new Box(a)` | Có, nếu copy constructor tạo object | Tùy implementation |
| `b = a.clone()` | Theo clone contract, thường có | Thường shallow |
| `int[] b = a.clone()` | Array mới | Primitive elements độc lập |
| `Member[] b = a.clone()` | Array mới | Cùng Member elements |
| `new ArrayList<>(a)` | List mới | Cùng elements |
| `List.copyOf(a)` | Không hứa identity mới | Cùng elements |
| `Collections.unmodifiableList(a)` | View wrapper thường gặp | Live source data |
| `deepCopy(a)` | Theo domain contract | Theo graph policy |
| Immutable `withX(...)` | Theo API | Có thể share immutable internals |

Đừng suy luận identity solely từ method name `copyOf`. `List.copyOf` có thể reuse existing suitable unmodifiable list; read contract.

## 30. Test independence cần kiểm tra cả hai chiều

Chỉ assert `copy != original` chưa đủ. Cần kiểm tra:

1. Initial copied values chính xác.
2. Top-level identity khác nếu contract đòi.
3. Nested mutable identity khác nếu hứa deep isolation.
4. Sửa original không làm copy đổi.
5. Sửa copy không làm original đổi.
6. Collection structure và elements theo đúng ownership policy.
7. Null/error behavior, cycles, aliases, subtype và invariant.
8. Consistent snapshot khi API hứa concurrency safety.

### Chương trình chạy: copy contract tests

Tạo **`CopyContractDemo.java`**:

~~~java
public class CopyContractDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address copy() {
            return new Address(city);
        }
    }

    static final class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person copy() {
            return new Person(name, address.copy());
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person copy = original.copy();

        check(original != copy, "same person");
        check(original.address != copy.address, "same address");

        original.address.city = "Da Nang";
        check(copy.address.city.equals("Hue"),
                "copy changed with source");

        copy.name = "An";
        check(original.name.equals("Mai"),
                "source changed with copy");

        System.out.println("identity PASS");
        System.out.println("nested isolation PASS");
        System.out.println("reverse isolation PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyContractDemo.java
java CopyContractDemo
~~~

Stdout:

~~~text
identity PASS
nested isolation PASS
reverse isolation PASS
~~~

Test mô hình Person→Address, không chứng minh deep-copy arbitrary resources/graphs. Trong dự án lớn, dùng JUnit và contract tests chung cho nhiều implementations.

## 31. Bài tập — identity

~~~java
class Box { int value; }
Box a = new Box();
Box b = a;
Box c = new Box();
System.out.println(a == b);
System.out.println(a == c);
~~~

**Đáp án:**

~~~text
true
false
~~~

## 32. Bài tập — mutate và reassign

~~~java
Box a = new Box();
a.value = 10;
Box b = a;
b.value = 20;
b = new Box();
b.value = 30;
System.out.println(a.value);
System.out.println(b.value);
~~~

**Đáp án:** In 20 và 30. Trước reassign, hai biến share Box; sau reassign, b trỏ Box khác.

## 33. Bài tập — array clone

~~~java
StringBuilder text = new StringBuilder("A");
StringBuilder[] a = {text};
StringBuilder[] b = a.clone();
b[0].append("B");
System.out.println(a[0]);
~~~

**Đáp án:** `AB`. Clone array không clone StringBuilder element.

## 34. Bài tập — parameter passing

~~~java
static void replace(Box box) {
    box = new Box();
    box.value = 100;
}
~~~

Caller truyền Box value=5. Sau `replace(box)` caller thấy 5, vì method chỉ reassign local parameter reference.

## 35. Bài tập — List copy

`new ArrayList<>(old)` tạo List mới. Hai Lists có elements kiểu mutable Member; đổi Member qua copy có ảnh hưởng old không?

**Đáp án:** Có thể, nếu cùng Member reference. Sửa List structure thì độc lập; sửa shared element state thì ảnh hưởng.

## 36. Bài tập — immutable String

~~~java
String a = "Java";
String b = a;
a = "Kotlin";
System.out.println(b);
~~~

**Đáp án:** `Java`. String cũ immutable và b vẫn tham chiếu nó.

## 37. Bài tập — deep copy graph có cycle

Node A.next=B, B.next=A. Vì sao copy đệ quy next mà không có visited map có thể lỗi?

**Đáp án:** A→B→A→B… vô hạn và có thể `StackOverflowError`. Phải nhớ source→target theo identity trước khi copy edges.

## 38. Bài tập — equals không chứng minh independent copy

Hai record Point được tạo riêng với components bằng nhau; equals true và == false. Điều đó chứng minh gì?

**Đáp án:** Hai objects khác identity nhưng value-equal; không chứng minh mọi nested mutable objects (nếu có) đã được deep copy.

## 39. Sai lầm thường gặp

| Sai lầm | Sự thật |
| --- | --- |
| `b = a` tạo object mới | Chỉ sao chép reference |
| Hai variables luôn hai objects | Có thể aliases |
| Gán null hủy object ngay | GC dựa trên reachability |
| Java truyền objects by-reference | Luôn pass-by-value |
| Reassign parameter thay caller variable | Không |
| `==` false nghĩa contents khác | Chỉ khác identity |
| `equals` true chứng minh deep copy | Không |
| final reference làm object immutable | Không |
| Array clone deep-copy elements | Reference elements vẫn shared |
| `new ArrayList<>(source)` deep-copy | Chỉ copy structure |
| `List.copyOf` deep-copy elements | Không |
| Unmodifiable view là snapshot | Thường vẫn phản ánh source |
| Cloneable/Object.clone tự deep copy | Mặc định shallow |
| Copy base giữ subclass fields | Constructors không polymorphic |
| Copy graph cycles không cần memoization | Cần identity map |
| Deep copy tự sao chép sockets/threads | Không có universal contract |
| Copy mutable source đồng thời luôn nhất quán | Cần đồng bộ |
| Immutable object bắt buộc copy khi share | Sharing thường an toàn |

## 40. Checklist cuối bài

- [ ] Tôi biết `b = a` chỉ copy reference value.
- [ ] Tôi phân biệt variables và object identity.
- [ ] Tôi vẽ được object graph với nhiều aliases.
- [ ] Tôi hiểu sửa object khác reassign variable.
- [ ] Tôi phân biệt `==` và `equals`.
- [ ] Tôi biết `new` tạo top-level object khác.
- [ ] Tôi hiểu Java pass-by-value cho references.
- [ ] Tôi biết field/array/list reference assignment cũng chỉ share target.
- [ ] Tôi phân biệt shallow/deep copy.
- [ ] Tôi biết primitive array clone tách primitive slots.
- [ ] Tôi biết reference array clone vẫn share elements.
- [ ] Tôi biết ArrayList copy chỉ copy structure.
- [ ] Tôi hiểu List.copyOf khác unmodifiable live view.
- [ ] Tôi biết mutable elements phải được snapshot nếu cần isolation.
- [ ] Tôi không nghĩ final reference tự clone object.
- [ ] Tôi biết immutable String/value objects có thể share an toàn.
- [ ] Tôi hiểu Cloneable/Object.clone limitations.
- [ ] Tôi biết copy base không tự giữ subtype.
- [ ] Tôi biết graph cycles cần visited identity map.
- [ ] Tôi xác định ownership và resource policy trước khi copy.
- [ ] Tôi biết concurrent snapshot cần consistency design.
- [ ] Tôi test independence từ cả original và copy.
- [ ] Tôi giải thích được stdout các chương trình Java 17+.

**Kết luận:** Với reference types, **`b = a` chỉ tạo alias, không tạo bản sao đối tượng**. Constructor, factory hoặc clone có thể tạo top-level object mới, nhưng copy vẫn có thể **chia sẻ nested mutable references**. Shallow copy tách phần ngoài; deep copy phải theo hợp đồng về mutable object graph, aliases, cycles và resources. Với immutable values, chia sẻ cùng object thường đúng và hiệu quả. Hãy vẽ object graph, xác định ownership và kiểm thử mutation ở cả hai phía trước khi khẳng định một bản sao độc lập.
