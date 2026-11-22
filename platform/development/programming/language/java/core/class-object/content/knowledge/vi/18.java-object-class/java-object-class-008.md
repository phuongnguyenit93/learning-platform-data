# `clone()`, `Cloneable` và giới hạn của sao chép mặc định trong Java

**Sao chép đối tượng (object copying)** là tạo một đối tượng khác từ trạng thái của đối tượng hiện có. Trong Java, phương thức `Object.clone()` cung cấp một cơ chế sao chép ở mức đối tượng, nhưng **không tự động tạo bản sao sâu** của toàn bộ đồ thị tham chiếu. Interface `Cloneable` cũng có ý nghĩa đặc biệt: nó là **marker interface**, không hề khai báo phương thức `clone()`.

Một đối tượng mới được sao chép nông có thể mang các trường nguyên thủy giống bản gốc nhưng vẫn **chia sẻ tham chiếu tới cùng một object con**, ví dụ cùng `ArrayList`, `Address` hoặc phần tử trong mảng. Nếu người học hiểu `clone()` là “tạo mọi thứ mới hoàn toàn” thì một thay đổi nhỏ ở bản sao có thể làm dữ liệu bản gốc biến đổi ngoài ý muốn.

Bài thuộc **Java core - class-object**, nhóm **Lớp Object**. Nội dung dành cho **Java 17+**, phân biệt object identity và state, cách `Object.clone()` hoạt động, quyền truy cập `protected`, checked exception `CloneNotSupportedException`, các trường hợp mảng, kế thừa, mutable fields, field `final`, cấu trúc có chu trình và các phương án **copy constructor**, **copy factory**, **immutable value object**. Những ví dụ độc lập đều ghi tên tệp, lệnh chạy và stdout để đối chiếu.

## 1. Sao chép cần làm rõ “sao chép cái gì?”

Cho hai biến:

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
~~~

Đây là đoạn Java minh họa hợp lệ. Nó **không sao chép object**: hai biến cùng tham chiếu một `StringBuilder`. Lệnh `second.append("B")` làm nội dung qua `first` trở thành `"AB"`.

Nếu tạo object mới:

~~~java
StringBuilder second = new StringBuilder(first.toString());
~~~

ở một ngữ cảnh có biến `first` tương ứng, `second` lúc này là một object độc lập, dù có nội dung ban đầu giống nhau.

Khi sao chép một object có nhiều trường, cần trả lời:

- **Identity:** object mới có khác object gốc không? Thông thường phải có `copy != original`.
- **Giá trị:** các trường nguyên thủy và thông tin nghiệp vụ nào được giữ lại?
- **Tham chiếu:** object mới có còn chia sẻ field reference với object gốc không?
- **Ownership:** những object con nào phải được sao chép và những object nào nên chia sẻ?
- **Invariant:** constructor và các ràng buộc nghiệp vụ có được bảo toàn sau copy?
- **Tính độc lập:** sửa bản copy có được phép tác động lên bản gốc không?

“Copy” chỉ có ý nghĩa đúng khi **hợp đồng sao chép** trả lời những câu hỏi trên. `clone()` không thể tự suy đoán ownership của mọi loại field.

## 2. `Object.clone()`: chữ ký và ý nghĩa cơ bản

Trong `java.lang.Object`, phương thức có dạng API:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

Đây là **khai báo chữ ký theo JDK**, không phải mã để đặt vào lớp riêng và tự biên dịch. Những thành phần cần nhớ:

| Thành phần | Ý nghĩa |
| --- | --- |
| `protected` | Không phải API công khai cho mọi caller trên mọi object |
| `native` | Triển khai nền tảng do JVM/JDK cung cấp |
| Trả `Object` | Kiểu trả về ở superclass rất rộng |
| `throws CloneNotSupportedException` | Có thể thất bại nếu object không hỗ trợ clone theo quy tắc |
| Không phải `final` | Subclass có thể override để công bố hợp đồng phù hợp |

Với một object thuộc lớp triển khai `Cloneable`, triển khai `Object.clone()` thông thường tạo **object mới cùng runtime class**, sao chép nội dung các trường ở mức thích hợp rồi trả về. Các trường primitive được chép giá trị; các trường reference được chép **giá trị tham chiếu**. Vì vậy bản sao mặc định là **shallow copy**.

Đối với object không thực hiện `Cloneable`, gọi `Object.clone()` trên object đó thông thường dẫn đến **`CloneNotSupportedException`**. Java không có cú pháp `new Object(...)` tương đương tự động cho tất cả object vì nhiều lớp có những invariant hoặc tài nguyên không thể sao chép đơn giản.

**Quan trọng:** `Object.clone()` không gọi constructor của class đối tượng mới theo đường khởi tạo thông thường. Do đó không thể dựa vào validation hoặc side effects trong constructor để “chạy lại” khi clone.

## 3. `Cloneable` là marker interface, không khai báo `clone()`

`java.lang.Cloneable` là một interface **không có method**. Nó đóng vai trò **dấu hiệu** cho cơ chế `Object.clone()` biết lớp cho phép phép sao chép cấp đối tượng này.

~~~java
final class Ticket implements Cloneable {
    private final int number;

    Ticket(int number) {
        this.number = number;
    }

    int number() {
        return number;
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
~~~

Đây là một **lớp Java hoàn chỉnh** có thể được sử dụng bởi một class chứa `main` trong cùng package. `Ticket` khai báo `implements Cloneable` để `Object.clone()` có cơ sở thực hiện thao tác sao chép, đồng thời tự override method để **mở mức truy cập thành `public`** và trả kiểu cụ thể `Ticket`.

Vì `Cloneable` không khai báo `clone`, việc một class viết `implements Cloneable` **không tự biến `object.clone()` thành lời gọi public**. Nếu class không công bố public clone method, caller bên ngoài có thể không gọi được `clone()` dù object đánh dấu `Cloneable`.

Trường `final int number` trong ví dụ là primitive. Giá trị số được sao chép, nhưng phép clone không chạy lại constructor `Ticket(int)`.

## 4. Chương trình hoàn chỉnh 1 — clone cơ bản và identity

Tạo tệp **`SimpleCloneDemo.java`**:

~~~java
final class Point implements Cloneable {
    private int x;
    private int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }

    @Override
    public Point clone() {
        try {
            return (Point) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return "(" + x + "," + y + ")";
    }
}

public class SimpleCloneDemo {
    public static void main(String[] args) {
        Point source = new Point(2, 3);
        Point copy = source.clone();

        System.out.println("same reference=" + (source == copy));
        System.out.println("source=" + source);
        System.out.println("copy=" + copy);

        copy.move(5, -1);
        System.out.println("after source=" + source);
        System.out.println("after copy=" + copy);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SimpleCloneDemo.java
java SimpleCloneDemo
~~~

**Stdout chính xác:**

~~~text
same reference=false
source=(2,3)
copy=(2,3)
after source=(2,3)
after copy=(7,2)
~~~

Với hai trường primitive `x` và `y`, shallow clone là **đủ** để hai object độc lập về trạng thái này: hai bản có giá trị ban đầu giống nhau nhưng sửa trường ở bản copy không tác động tới source.

Không nên suy ra rằng `clone()` luôn độc lập như vậy khi class có `List`, `Date`, `StringBuilder`, một mảng hoặc các object con mutable.

## 5. Không `Cloneable`: điều gì thật sự xảy ra?

Nếu một class không đánh dấu `Cloneable` nhưng gọi `super.clone()`, `Object.clone()` sẽ kiểm tra đối tượng thực tế và có thể ném **`CloneNotSupportedException`**.

Tạo tệp **`NotCloneableDemo.java`**:

~~~java
class PlainRecord {
    private final int id;

    PlainRecord(int id) {
        this.id = id;
    }

    PlainRecord attemptClone()
            throws CloneNotSupportedException {
        return (PlainRecord) super.clone();
    }

    int id() {
        return id;
    }
}

public class NotCloneableDemo {
    public static void main(String[] args) {
        PlainRecord item = new PlainRecord(7);

        try {
            PlainRecord copy = item.attemptClone();
            System.out.println("copy id=" + copy.id());
        } catch (CloneNotSupportedException ex) {
            System.out.println("exception="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NotCloneableDemo.java
java NotCloneableDemo
~~~

**Stdout:**

~~~text
exception=CloneNotSupportedException
~~~

Method `attemptClone()` là một wrapper trong chính class con nên được phép gọi `super.clone()` thuộc `Object` dù nó là protected. Caller bên ngoài **không** gọi trực tiếp `item.clone()`: method đó vẫn không phải một API public được `PlainRecord` công bố.

Điểm quyết định không phải “có một method tên attemptClone”. Object runtime chưa implement `Cloneable`, nên cơ chế `Object.clone()` từ chối thao tác.

Khi một class **không** hứa hỗ trợ clone, đó có thể là lựa chọn thiết kế có chủ đích: tài nguyên file/socket, handle, lock, object phụ thuộc lifecycle và các invariant phức tạp không nên sao chép tùy tiện.

## 6. Clone nông (shallow copy): chép tham chiếu, không chép object con

Giả sử object `Notebook` giữ:

~~~text
Notebook N1
    title -> "Java"
    tags  -> ArrayList A ["core"]

clone N1 bằng Object.clone():
    Notebook N2 (object mới)
    title -> cùng giá trị tham chiếu String "Java"
    tags  -> vẫn trỏ ArrayList A
~~~

Về mặt cấu trúc, shallow clone tạo `N2 != N1`, nhưng `N2.tags == N1.tags` là true. Điều đó có nghĩa:

- Thêm phần tử vào `N2.tags` cũng nhìn thấy qua `N1.tags`.
- Gán lại field `N2.tags = new ArrayList<>(...)` sau clone có thể tách riêng collection, nếu field không final và code cho phép.
- Thay field reference `N2.title` bằng chuỗi khác không sửa `N1.title`. Các object `String` vốn **bất biến**, nên việc chia sẻ một String không tạo rủi ro mutation nội tại giống ArrayList.

**Shallow copy không sai tự thân.** Nó phù hợp khi mọi object được tham chiếu là immutable, hoặc khi thiết kế cố ý cho hai object chia sẻ dependency. Nó **không** phù hợp nếu người dùng API được hứa có bản sao độc lập của một mutable list mà implementation lại chia sẻ chính list đó.

## 7. Chương trình hoàn chỉnh 2 — thấy alias sau shallow clone

Tạo tệp **`ShallowCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class Notebook implements Cloneable {
    private String title;
    private List<String> tags = new ArrayList<>();

    Notebook(String title) {
        this.title = title;
    }

    void addTag(String tag) {
        tags.add(tag);
    }

    void rename(String next) {
        title = next;
    }

    List<String> tags() {
        return List.copyOf(tags);
    }

    String title() {
        return title;
    }

    boolean sharesTagsWith(Notebook other) {
        return tags == other.tags;
    }

    @Override
    public Notebook clone() {
        try {
            return (Notebook) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class ShallowCloneDemo {
    public static void main(String[] args) {
        Notebook source = new Notebook("Java");
        source.addTag("core");

        Notebook copy = source.clone();
        System.out.println("same object=" + (source == copy));
        System.out.println("same tags="
                + source.sharesTagsWith(copy));

        copy.rename("Java Copy");
        copy.addTag("oop");

        System.out.println("source title=" + source.title());
        System.out.println("copy title=" + copy.title());
        System.out.println("source tags=" + source.tags());
        System.out.println("copy tags=" + copy.tags());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ShallowCloneDemo.java
java ShallowCloneDemo
~~~

**Stdout:**

~~~text
same object=false
same tags=true
source title=Java
copy title=Java Copy
source tags=[core, oop]
copy tags=[core, oop]
~~~

`rename()` **gán lại field reference `title`** của copy nên không đổi title của source. Nhưng `addTag()` thay đổi **chính ArrayList** mà hai notebooks cùng tham chiếu, nên source cũng xuất hiện `oop`.

Ngay cả `tags()` trả `List.copyOf(tags)` để không lộ mutable collection trực tiếp cũng **không sửa được alias đã có giữa hai Notebook do clone**. Bản snapshot chỉ bảo vệ caller khỏi sửa danh sách qua getter.

## 8. Sao chép sâu (deep copy): định nghĩa theo phạm vi ownership

Deep copy thường được hiểu là **tạo bản sao mới cho các object con mutable thuộc sở hữu của object gốc**, để những thay đổi có ý nghĩa trên bản sao không tác động tới bản gốc. Nhưng không có một “deep clone chuẩn” áp dụng cho mọi object graph Java.

Ví dụ một `Invoice` có danh sách `Line`:

~~~text
Invoice source -> List A -> Line A1 (sku="P1", qty=2)
Invoice copy   -> List B -> Line B1 (sku="P1", qty=2)
~~~

Nếu `List A != List B` nhưng `A1 == B1`, ta mới **copy collection**, chưa deep-copy phần tử mutable. Nếu `List A != List B` và `A1 != B1`, đồng thời các trường quan trọng của Line được sao chép độc lập, mới có sự tách biệt ở mức này.

Một số object có thể **chia sẻ an toàn**: `String`, những value objects bất biến, enum constants, class tokens hoặc resource được chủ đích chia sẻ theo hợp đồng. Deep copy **không cần** tạo lại mọi object bất biến. Thậm chí copy một resource như connection/socket có thể là khái niệm không hợp lệ.

Vì thế, khi thiết kế deep copy hãy ghi rõ **ranh giới sở hữu** và **đối tượng nào cần độc lập sau sao chép**.

## 9. Chương trình hoàn chỉnh 3 — sao chép list và từng phần tử

Tạo tệp **`DeepCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class Line implements Cloneable {
    private final String sku;
    private int quantity;

    Line(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        this.quantity = quantity;
    }

    int quantity() {
        return quantity;
    }

    @Override
    public Line clone() {
        try {
            return (Line) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class Invoice implements Cloneable {
    private List<Line> lines = new ArrayList<>();

    void add(Line line) {
        lines.add(line);
    }

    Line line(int index) {
        return lines.get(index);
    }

    boolean sharesListWith(Invoice other) {
        return lines == other.lines;
    }

    @Override
    public Invoice clone() {
        try {
            Invoice copy = (Invoice) super.clone();
            copy.lines = new ArrayList<>();
            for (Line line : lines) {
                copy.lines.add(line.clone());
            }
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class DeepCloneDemo {
    public static void main(String[] args) {
        Invoice source = new Invoice();
        source.add(new Line("P1", 2));

        Invoice copy = source.clone();
        copy.line(0).setQuantity(9);

        System.out.println("same invoice=" + (source == copy));
        System.out.println("same list="
                + source.sharesListWith(copy));
        System.out.println("same line="
                + (source.line(0) == copy.line(0)));
        System.out.println("source qty="
                + source.line(0).quantity());
        System.out.println("copy qty="
                + copy.line(0).quantity());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DeepCloneDemo.java
java DeepCloneDemo
~~~

**Stdout chính xác:**

~~~text
same invoice=false
same list=false
same line=false
source qty=2
copy qty=9
~~~

Giải thích:

1. `super.clone()` trước tiên tạo `Invoice` mới với field `lines` đang trỏ **cùng list**.
2. `copy.lines = new ArrayList<>()` tách collection ra khỏi source.
3. Vòng lặp tạo từng `Line.clone()` riêng để không giữ alias của phần tử mutable.
4. `String sku` và số lượng primitive an toàn với cách sao chép của `Line`: String bất biến, primitive copy theo giá trị.
5. Sửa quantity ở bản clone không ảnh hưởng source.

**Giới hạn:** ví dụ cố tình đơn giản và đơn luồng. Nếu `Line` sau này được bổ sung một field mutable như `Address` hoặc danh sách discount, `Line.clone()` cũng cần được xem lại hợp đồng. Deep copy là **cam kết về toàn bộ trạng thái liên quan**, không phải kết quả tự động từ từ khóa `Cloneable`.

## 10. Vì sao chỉ copy `ArrayList` chưa chắc là deep copy?

Những cách sau đều **tạo list container mới**:

~~~java
List<Line> other = new ArrayList<>(lines);
List<Line> snapshot = List.copyOf(lines);
~~~

Đây là các câu lệnh minh họa đặt trong nơi có `lines` kiểu `List<Line>` không chứa null. Tuy nhiên:

- `new ArrayList<>(lines)` tạo **list mới có thể sửa**, chứa **cùng những tham chiếu Line**.
- `List.copyOf(lines)` trả **list không hỗ trợ thay đổi nội dung qua API list**, nhưng **cũng giữ các object Line ban đầu**. Nó là snapshot **nông** và không đảm bảo object list trả về có identity khác trong mọi trường hợp đầu vào immutable.
- Nếu `Line` mutable, sửa `other.get(0).setQuantity(...)` hoặc `snapshot.get(0).setQuantity(...)` vẫn có thể sửa chính Line mà source list chứa.

**Read-only collection không đồng nghĩa immutable object graph**. Nếu muốn sao chép dữ liệu nội bộ tới một value object độc lập, hãy copy các phần tử hoặc chuyển chúng sang các immutable DTO/value objects thích hợp.

## 11. `clone()` không chạy constructor của object sao chép

Một tính chất quan trọng của `Object.clone()`: nó tạo đối tượng đã sao chép trường **mà không thực thi constructor thông thường của lớp đối tượng mới**.

Tạo tệp **`CloneConstructorDemo.java`**:

~~~java
class TrackedObject implements Cloneable {
    private static int nextId;
    private final int id;

    TrackedObject() {
        id = ++nextId;
        System.out.println("constructor id=" + id);
    }

    int id() {
        return id;
    }

    @Override
    public TrackedObject clone() {
        try {
            return (TrackedObject) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CloneConstructorDemo {
    public static void main(String[] args) {
        TrackedObject source = new TrackedObject();
        TrackedObject copy = source.clone();

        System.out.println("different objects="
                + (source != copy));
        System.out.println("source id=" + source.id());
        System.out.println("copy id=" + copy.id());

        TrackedObject next = new TrackedObject();
        System.out.println("next id=" + next.id());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CloneConstructorDemo.java
java CloneConstructorDemo
~~~

**Stdout:**

~~~text
constructor id=1
different objects=true
source id=1
copy id=1
constructor id=2
next id=2
~~~

Sao chép không in `constructor id=...` lần thứ hai, vì constructor `TrackedObject()` **không được chạy cho bản clone**. Do trường `id` được copy nguyên trạng, **hai object khác nhau có cùng ID**.

Đây là một ví dụ về invariant/identity bị phá về mặt nghiệp vụ nếu `id` được yêu cầu **duy nhất cho mỗi object**. `Object.clone()` không hiểu yêu cầu ấy và không tự phát sinh ID mới.

Nếu bắt buộc có ID mới, đừng tin rằng gọi `super.clone()` sẽ tự chạy logic cấp ID trong constructor. Hãy thiết kế **copy factory hoặc một cơ chế tạo mới** với quy tắc cấp ID rõ.

## 12. Trường `final` và giới hạn việc sửa bản clone

Sao chép bằng `Object.clone()` cũng sao chép giá trị các field `final`. Nhưng `final` áp đặt quy tắc gán trong Java source: method thông thường **không thể gán lại** một instance field `final` sau khi object đã được khởi tạo.

Ví dụ:

~~~java
final class Basket implements Cloneable {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String item) {
        items.add(item);
    }

    @Override
    public Basket clone() {
        try {
            return (Basket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
~~~

Đây là một class minh họa hợp lệ. Sau shallow clone, `items` trong cả hai Baskets cùng trỏ một `ArrayList`. Ta **không thể** sửa thành `copy.items = new ArrayList<>(items)` trong phương thức clone vì field đã `final`.

Điểm tinh tế: **`final` khóa việc gán lại tham chiếu field, không làm object tham chiếu tới trở thành immutable.** `items.add(...)` vẫn sửa list được.

Nếu class chứa `final` references tới mutable objects mà muốn **bản copy sở hữu dữ liệu mới**, copy constructor hoặc factory tạo object thông qua constructor là một giải pháp dễ hiểu hơn. Dùng reflection hoặc thủ thuật phá `final` chỉ để ép clone có thể làm vi phạm hợp đồng ngôn ngữ và memory model; không nên làm.

## 13. Chương trình hoàn chỉnh 4 — copy constructor với defensive copy

Tạo tệp **`CopyConstructorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class SafeBasket {
    private final String owner;
    private final List<String> items;

    SafeBasket(String owner, List<String> items) {
        this.owner = Objects.requireNonNull(owner, "owner");
        this.items = new ArrayList<>(
                Objects.requireNonNull(items, "items"));
    }

    SafeBasket(SafeBasket other) {
        this(other.owner, other.items);
    }

    void add(String item) {
        items.add(Objects.requireNonNull(item, "item"));
    }

    List<String> items() {
        return List.copyOf(items);
    }

    String owner() {
        return owner;
    }
}

public class CopyConstructorDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("book");

        SafeBasket source = new SafeBasket("An", input);
        SafeBasket copy = new SafeBasket(source);

        input.add("external");
        copy.add("pen");

        System.out.println("same=" + (source == copy));
        System.out.println("owner=" + copy.owner());
        System.out.println("source=" + source.items());
        System.out.println("copy=" + copy.items());
        System.out.println("input=" + input);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CopyConstructorDemo.java
java CopyConstructorDemo
~~~

**Stdout:**

~~~text
same=false
owner=An
source=[book]
copy=[book, pen]
input=[book, external]
~~~

Ở đây:

- Constructor nhận `items` tạo `ArrayList` riêng, bảo vệ khỏi alias đến collection của caller.
- Copy constructor `SafeBasket(SafeBasket other)` **tạo object mới theo constructor bình thường**, nên các field final được khởi tạo hợp lệ.
- `String` bất biến, nên `owner` có thể chia sẻ an toàn.
- `List<String>` dùng String bất biến; một list container mới là đủ để hai Baskets độc lập về thay đổi danh sách.

**Đánh đổi:** copy constructor **biết kiểu đích cụ thể**. Nếu có hierarchy và cần giữ nguyên subclass động, một constructor kiểu base không tự động tạo subclass. Đây là hợp đồng phải thiết kế rõ thay vì giả định copy constructor cung cấp polymorphic clone.

## 14. Copy factory: nêu ý định thay vì ép mọi thứ vào `clone()`

Một factory có tên có thể diễn đạt chính xác kiểu sao chép:

~~~java
final class AccountSnapshot {
    private final String id;
    private final long balance;

    private AccountSnapshot(String id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    static AccountSnapshot of(String id, long balance) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        return new AccountSnapshot(id, balance);
    }

    AccountSnapshot copy() {
        return AccountSnapshot.of(id, balance);
    }

    AccountSnapshot withBalance(long next) {
        return AccountSnapshot.of(id, next);
    }

    long balance() {
        return balance;
    }
}
~~~

Đây là **lớp Java hoàn chỉnh**, được thiết kế immutable và không cần implements `Cloneable`. `copy()` tạo một object mới theo cùng dữ liệu; `withBalance()` tạo **giá trị mới** với balance khác.

Một số value objects bất biến còn có thể trả `this` từ một thao tác “copy” nếu hợp đồng **không yêu cầu identity mới**. Nhưng đừng trả `this` từ API được mô tả là “fresh independent instance” mà chưa ghi rõ hành vi.

**Lợi ích của factory/copy constructor:** có thể chạy validation, chọn chính sách sao chép mutable references, đặt tên dễ hiểu, không cần xử lý checked exception đặc biệt của `Object.clone()`.

## 15. Mảng là một trường hợp đặc biệt: hỗ trợ `clone()`

Mảng Java có phương thức `clone()` public phù hợp với kiểu mảng; các array objects triển khai `Cloneable` và `java.io.Serializable`. Vì vậy:

~~~java
int[] values = {1, 2, 3};
int[] copy = values.clone();
~~~

là cú pháp bình thường, không cần tự `implements Cloneable` và không cần bắt `CloneNotSupportedException` ở nơi gọi.

Mảng một chiều primitive: mỗi phần tử là giá trị nguyên thủy nên clone tạo mảng mới với giá trị độc lập.

Mảng references: clone tạo **mảng mới** nhưng các phần tử vẫn trỏ tới **cùng object con**.

Mảng nhiều chiều: `int[][]` thực chất là **mảng chứa tham chiếu tới các mảng `int[]`**. `matrix.clone()` chỉ sao chép mảng **ngoài cùng**, còn các mảng hàng bên trong được chia sẻ.

Đừng kết luận từ cú pháp tiện lợi `array.clone()` rằng Java đã thực hiện đệ quy clone mọi cấp.

## 16. Chương trình hoàn chỉnh 5 — mảng primitive, reference và hai chiều

Tạo tệp **`ArrayCloneDemo.java`**:

~~~java
public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;

        System.out.println("numbers[0]=" + numbers[0]);
        System.out.println("copy[0]=" + numberCopy[0]);
        System.out.println("same primitive array="
                + (numbers == numberCopy));

        StringBuilder[] labels = {
                new StringBuilder("A")
        };
        StringBuilder[] labelCopy = labels.clone();
        labelCopy[0].append("!");

        System.out.println("same reference array="
                + (labels == labelCopy));
        System.out.println("same element="
                + (labels[0] == labelCopy[0]));
        System.out.println("original label=" + labels[0]);

        int[][] grid = {{1, 2}, {3, 4}};
        int[][] gridCopy = grid.clone();
        gridCopy[0][0] = 8;

        System.out.println("same outer="
                + (grid == gridCopy));
        System.out.println("same first row="
                + (grid[0] == gridCopy[0]));
        System.out.println("original grid[0][0]="
                + grid[0][0]);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ArrayCloneDemo.java
java ArrayCloneDemo
~~~

**Stdout chính xác:**

~~~text
numbers[0]=1
copy[0]=9
same primitive array=false
same reference array=false
same element=true
original label=A!
same outer=false
same first row=true
original grid[0][0]=8
~~~

Phép clone của `int[]` cho một object mảng độc lập vì bản chất phần tử là primitive values. Còn `StringBuilder[]` sao chép các **tham chiếu StringBuilder**, không sao chép StringBuilder. `grid.clone()` chia sẻ các object hàng, nên thay một phần tử trong hàng có thể quan sát qua cả hai mảng ngoài.

Nếu cần copy độc lập các hàng của `int[][]`, phải sao chép từng hàng, ví dụ dùng `grid[i].clone()` cho từng `int[]` không null. Nếu các hàng có thể null hoặc nếu phần tử là object mutable, cần thêm quy tắc null và copy sâu phù hợp.

## 17. `Arrays.copyOf` và `System.arraycopy` cũng thường là shallow với references

Các API sao chép mảng phổ biến:

- `array.clone()` tạo một array mới cùng runtime array type.
- `Arrays.copyOf(array, newLength)` tạo array mới với độ dài mong muốn, sao chép phần tử có sẵn và thêm giá trị mặc định nếu dài hơn.
- `System.arraycopy(src, pos, dest, pos, length)` sao chép một vùng giữa các arrays đã có.
- `Arrays.copyOfRange` sao chép đoạn xác định.

Đối với reference arrays, các thao tác này **sao chép giá trị tham chiếu**, không tự clone object con. Nếu đổi một element ở array mới sang object khác, array gốc giữ reference cũ; nhưng nếu **mutate chính object** được hai arrays trỏ tới, cả hai nhìn thấy mutation.

Cần chú ý `System.arraycopy` có thể gây `ArrayStoreException` nếu kiểu phần tử runtime không tương thích, và trong một số trường hợp copy có thể đã chuyển một phần tử trước lỗi; đừng dùng nó như giao dịch rollback tự động cho các phép copy không tương thích.

## 18. Kế thừa: class con có field mutable khiến clone của lớp cha thiếu sâu

Với hierarchy, override `clone()` ở superclass có thể trả đúng **runtime class** nhờ `super.clone()` nhưng vẫn copy nông các field mà subclass bổ sung. Không thể tự động biết mỗi subclass có những dữ liệu mutable nào cần tách riêng.

Tạo tệp **`InheritedCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class BaseProfile implements Cloneable {
    private final String id;

    BaseProfile(String id) {
        this.id = id;
    }

    String id() {
        return id;
    }

    @Override
    public BaseProfile clone() {
        try {
            return (BaseProfile) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class DetailedProfile extends BaseProfile {
    private List<String> skills = new ArrayList<>();

    DetailedProfile(String id) {
        super(id);
    }

    void addSkill(String skill) {
        skills.add(skill);
    }

    List<String> skills() {
        return List.copyOf(skills);
    }

    boolean sharesSkills(DetailedProfile other) {
        return skills == other.skills;
    }

    @Override
    public DetailedProfile clone() {
        DetailedProfile copy = (DetailedProfile) super.clone();
        copy.skills = new ArrayList<>(skills);
        return copy;
    }
}

public class InheritedCloneDemo {
    public static void main(String[] args) {
        DetailedProfile source = new DetailedProfile("P1");
        source.addSkill("Java");

        DetailedProfile copy = source.clone();
        copy.addSkill("SQL");

        System.out.println("same object=" + (source == copy));
        System.out.println("copy class="
                + copy.getClass().getSimpleName());
        System.out.println("shares skills="
                + source.sharesSkills(copy));
        System.out.println("source=" + source.skills());
        System.out.println("copy=" + copy.skills());
        System.out.println("source id=" + source.id());
        System.out.println("copy id=" + copy.id());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InheritedCloneDemo.java
java InheritedCloneDemo
~~~

**Stdout:**

~~~text
same object=false
copy class=DetailedProfile
shares skills=false
source=[Java]
copy=[Java, SQL]
source id=P1
copy id=P1
~~~

Ở đây `BaseProfile.clone()` tạo bản sao cùng runtime class `DetailedProfile`. Nhưng để field mutable `skills` độc lập, `DetailedProfile.clone()` phải **bổ sung bước copy list** của chính subclass.

Nếu `DetailedProfile` không override, clone kế thừa từ BaseProfile sẽ trả một object `DetailedProfile` thật, nhưng danh sách `skills` bị alias. Đây là lý do thiết kế một hierarchy mở có hợp đồng clone phức tạp: subclass mới thêm field mutable có thể vô tình phá giả định “clone là độc lập”.

## 19. Vì sao override `clone()` trong hierarchy khó bảo trì?

Trong một hierarchy, có thể có nhiều tầng:

~~~text
BaseDocument
    |
    +-- PdfDocument
    |      |
    |      +-- SignedPdfDocument
    |
    +-- HtmlDocument
~~~

Mỗi tầng có thể thêm field primitive, immutable, mutable, resource handle hoặc object graph có quan hệ vòng. Mỗi implementation clone phải biết **phần dữ liệu của chính mình** và thỏa hợp đồng chung với superclass.

Các rủi ro:

1. Superclass gọi `super.clone()` nhưng class con quên copy mutable field.
2. Một subclass không mong muốn được clone nhưng kế thừa public `clone()` từ superclass.
3. Field `final` chứa mutable object khó tách sau `super.clone()`.
4. Lớp cha thay đổi constructor validation nhưng cloning **bỏ qua constructor**.
5. Quan hệ giữa các object con có thể bị hỏng nếu chúng được sao chép độc lập mà không giữ identity/chia sẻ cần thiết.
6. Thêm subclass mới làm giả định kiểu đích của copy constructor trở nên không đủ.

Khi API không cần clone polymorphic, một số thiết kế chọn **class `final` + copy constructor/factory** để tập trung kiểm soát invariant. Khi cần polymorphic copying, có thể định nghĩa một method `copy()` thuộc interface/domain contract với quy tắc rõ, thay vì dựa vào `Object.clone()` ngầm định.

## 20. Cyclic graph: deep copy không thể cứ đệ quy vô hạn

Đối tượng có thể tham chiếu tới chính nó hoặc chia sẻ chung một object con:

~~~text
A -> B -> A         (chu trình)
C -> Shared
D -> Shared         (hai đường tới cùng một object)
~~~

Nếu viết thuật toán deep copy đơn giản theo kiểu “copy A, rồi copy từng field, rồi copy từng field của B”, có thể lặp vô tận trên chu trình A↔B. Còn nếu sao chép mỗi lần gặp một tham chiếu mà không ghi nhớ, hai đường tới object Shared sẽ tạo **hai copies khác nhau**, làm thay đổi ngữ nghĩa **chia sẻ** của graph.

Giải pháp khái niệm: dùng một **identity map** ánh xạ object gốc sang bản sao:

~~~text
copy(node):
    nếu node đã có trong identity map -> trả bản sao cũ
    tạo node copy
    ghi map[node gốc] = node copy trước khi đi sâu
    copy các liên kết con, dùng lại map
    trả node copy
~~~

Với identity map, cần so sánh object theo **tham chiếu**, không theo `equals()`, bởi hai nodes khác identity có thể cùng giá trị mà vẫn là hai đỉnh graph riêng biệt.

## 21. Chương trình hoàn chỉnh 6 — copy đồ thị có chu trình

Tạo tệp **`GraphCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public class GraphCopyDemo {
    private static final class Node {
        private final String name;
        private final List<Node> neighbors = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void connect(Node neighbor) {
            neighbors.add(neighbor);
        }

        Node neighbor(int index) {
            return neighbors.get(index);
        }

        Node deepCopy(Map<Node, Node> visited) {
            Node previous = visited.get(this);
            if (previous != null) {
                return previous;
            }

            Node copy = new Node(name);
            visited.put(this, copy);
            for (Node neighbor : neighbors) {
                copy.neighbors.add(neighbor.deepCopy(visited));
            }
            return copy;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.connect(b);
        b.connect(a);

        Node copiedA = a.deepCopy(new IdentityHashMap<>());
        Node copiedB = copiedA.neighbor(0);

        System.out.println("new root=" + (copiedA != a));
        System.out.println("new child=" + (copiedB != b));
        System.out.println("cycle preserved="
                + (copiedB.neighbor(0) == copiedA));
        System.out.println("original untouched="
                + (a.neighbor(0) == b));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
~~~

**Stdout:**

~~~text
new root=true
new child=true
cycle preserved=true
original untouched=true
~~~

Cơ chế quan trọng: `visited.put(this, copy)` xảy ra **trước** khi đi sâu vào neighbors. Khi bản sao B đi tới reference ngược về A, map đã biết bản sao A và trả lại nó, tránh đệ quy vô hạn.

Ví dụ dùng `IdentityHashMap` vì bài toán cần **identity của đỉnh graph**, không phải equality theo tên. Đây là một deep-copy method với constructor thường, **không dùng `Object.clone()`**; nó cho thấy sâu/nông là đặc tính của thuật toán copy, không phải của tên method `clone`.

## 22. Deep copy cần bảo toàn cả quan hệ và invariant

Không phải cứ tạo object mới cho từng field là đúng. Ví dụ hai fields `billingAddress` và `shippingAddress` có thể được chủ đích trỏ tới **cùng một Address object** nếu khách chọn “giao hàng tới địa chỉ thanh toán”.

Nếu deep copy tạo hai Address copies độc lập, bản copy làm mất quan hệ alias có ý nghĩa trong mô hình gốc. Nếu bản gốc có chu trình parent/child hoặc hai phía của một association, clone thủ công từng object mà không dùng identity map có thể khiến quan hệ bị đứt hoặc phát sinh object dư.

Hãy xác định:

- Phải giữ **cùng giá trị** hay còn phải giữ **cấu trúc chia sẻ reference**?
- Quan hệ nào thuộc phạm vi ownership của object được copy?
- Object nào nên tiếp tục tham chiếu **nguồn ngoài** (service, repository, immutable metadata)?
- Những object con nào có ID cần phát sinh mới, và object nào giữ ID vì cùng thực thể?
- Có callback, listener, thread hoặc transaction state không nên sao chép?
- Sau copy, invariant có còn đúng khi chạy mọi phương thức nghiệp vụ?

Một hợp đồng deep copy rõ sẽ dễ kiểm thử hơn khẩu hiệu “clone tất cả trường”.

## 23. `equals()`, `hashCode()` và `==` sau clone

Ba khái niệm khác nhau:

- `original == copy` so sánh **identity tham chiếu**; với bản clone đúng nghĩa thông thường trả object mới thì phải là false.
- `original.equals(copy)` phụ thuộc **hợp đồng `equals`** của class. Nếu class không override `Object.equals`, kết quả mặc định thường false vì so identity. Nếu là value object và equals so các trường, có thể true.
- `hashCode()` có hợp đồng với equals: **nếu equals true thì hashCode phải bằng nhau**, nhưng hai object khác nhau không bắt buộc có hash khác nhau. Không dùng kết quả hashCode để kết luận một object “đã clone hay chưa”.

Nếu class có ID duy nhất thuộc miền, cần quyết định bản copy giữ hay nhận ID mới. Nếu giữ cùng ID, hai object khác identity có thể được xem là **cùng entity** theo cách định nghĩa equality, dù dữ liệu còn khác. Nếu cấp ID mới, phải có một phương thức tạo mới có kiểm soát thay vì trông đợi `Object.clone()` tự chạy bộ cấp ID.

`System.identityHashCode(obj)` là một giá trị liên quan identity nhưng **không phải khóa unique toàn cục**; có thể collision, không nên dùng làm mã định danh nghiệp vụ.

## 24. Immutable value objects có thể không cần `clone()`

Một object bất biến có thể được **chia sẻ an toàn** giữa nhiều nơi vì không có trạng thái mutable cần cách ly.

~~~java
record Coordinates(int x, int y) {
    Coordinates move(int dx, int dy) {
        return new Coordinates(x + dx, y + dy);
    }
}
~~~

Đây là record Java 17 hoàn chỉnh. `move` **không sửa record cũ**, mà tạo một `Coordinates` mới với giá trị khác. Record có các component primitive nên bất biến về state đơn giản.

Với `String`, `Integer` và những value objects immutable khác, không nhất thiết tạo bản sao identity mới chỉ để tránh mutation. Nhưng một record có **component là `List` mutable** không tự trở thành deep immutable: record components là final references, object được tham chiếu vẫn có thể mutate nếu không defensive copy.

Thiết kế bất biến thường làm **copy dễ hơn** bằng cách thay thế việc thay đổi trong chỗ bằng việc tạo giá trị mới có validation.

## 25. Khi nào nên dùng copy constructor, factory hoặc `clone()`?

| Lựa chọn | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| `super.clone()` + `Cloneable` | Có thể copy runtime class, chép fields nhanh ở mức nông | Constructor không chạy, mutable references alias |
| Override `clone()` và deep copy cần thiết | Có thể công bố API clone phù hợp với class | Bảo trì khó trong hierarchy, xử lý final refs/cycles |
| Copy constructor `new T(original)` | Rõ ràng, chạy constructor, khởi tạo `final` hợp lệ | Không tự polymorphic theo runtime subclass |
| Static factory `T.copyOf(original)` | Tên/hợp đồng dễ diễn đạt, dễ validate | Cần code copy do ứng dụng định nghĩa |
| Immutable `withX` / value replacement | Ít nguy cơ alias mutable, thuận lợi khi chia sẻ | Có thể tạo nhiều object mới, phải cân nhắc hiệu năng |
| Registry/graph-aware copy | Bảo toàn identity và chu trình theo phạm vi | Phức tạp hơn copy một object đơn giản |

**Gợi ý cho Java Core:** không coi `Cloneable` là “đường tắt bắt buộc” để hỗ trợ copy. Đối với domain objects có invariants/ownership phức tạp, copy constructor hoặc factory thường làm hợp đồng minh bạch hơn.

Nếu đang làm việc với một API JDK cụ thể yêu cầu `Cloneable` hoặc cung cấp `clone()` public rõ ràng, hãy đọc chính hợp đồng API đó thay vì áp một giả định cho mọi lớp.

## 26. Kiểm thử hành vi clone/copy đúng cách

Để chứng minh một phương thức copy an toàn, hãy thiết kế test nhiều tầng:

| Kiểm thử | Cần xác nhận |
| --- | --- |
| Identity cấp root | `copy != source` nếu hợp đồng yêu cầu object mới |
| Primitive fields | Giá trị được giữ đúng |
| Immutable fields | Có thể chia sẻ mà không tạo mutable alias |
| Mutable collections | `copy.list != source.list` nếu hứa độc lập |
| Mutable elements | `copy.list.get(0) != source.list.get(0)` khi phần tử thuộc sở hữu cần deep copy |
| Mutation isolation | Sửa bản copy không làm source đổi và ngược lại |
| Final fields | Copy có invariant hợp lệ, không cần phá final |
| Constructor invariants | Có được validate/phục hồi theo hợp đồng không |
| Repeated references | Hai liên kết tới cùng object con trong source vẫn chia sẻ đúng trong copy |
| Cycles | Graph clone kết thúc và tái lập quan hệ vòng đúng |
| Subclass fields | Clone giữ class runtime và bảo vệ field mutable được subclass thêm |
| Exceptions | Invalid input/copy failure không để source bị sửa bất ngờ |
| Resource handles | Không clone socket/lock/file handle trái lifecycle |
| Concurrency | Copy có yêu cầu snapshot nhất quán hay phải đồng bộ với writer |

Có thể dùng JUnit, nhưng **không cần framework** cho những kiểm tra cơ bản; câu `if (...) throw new AssertionError(...)` cho phép viết self-test với JDK thuần.

Nên kiểm tra **hành vi sau mutation**, không chỉ kiểm tra `copy.equals(source)` ngay sau khi copy. Shallow clone có thể có cùng dữ liệu ban đầu và vẫn có bug alias bị lộ chỉ khi bắt đầu thay đổi.

## 27. Copy và đồng thời: snapshot không tự thread-safe

Nếu một thread đang sửa `ArrayList`, thread khác đồng thời clone object chứa list đó, `Object.clone()` không tự cung cấp **snapshot nhất quán nguyên tử** của cả object graph.

Một số rủi ro:

- Giá trị các field được đọc/copy vào những thời điểm khác nhau, tạo snapshot không nhất quán.
- Một mutable collection được duyệt trong lúc thread khác sửa có thể dẫn tới kết quả sai hoặc exception tùy API.
- Shallow copy chỉ sao chép references, không tạo synchronization hay ownership.
- Deep copy nhiều bước có thể cần giữ lock hoặc lấy snapshot immutable theo một giao thức nhất quán.

Nếu ứng dụng yêu cầu concurrent snapshots, hãy thiết kế synchronization, immutable persistent structures, read/write locks hoặc cơ chế versioning/transactions phù hợp. **`Cloneable` không phải một contract thread-safe**.

Không nên “khắc phục” concurrency bằng việc gọi `clone()` nhiều lần cho tới khi không lỗi; độ chính xác cần một quy tắc consistency rõ ràng.

## 28. Copy đối tượng chứa tài nguyên và external state

Không phải mọi trạng thái Java đều có thể copy về mặt nghiệp vụ:

- `Socket` hoặc database connection là tài nguyên ngoài, không thể tạo bản sao kết nối hợp lệ chỉ bằng chép fields.
- `InputStream` có vị trí đọc, trạng thái đóng/mở và dữ liệu nền; chia sẻ hoặc cố copy field có thể hỏng vòng đời.
- `Thread`, lock và condition objects có các trạng thái gắn với đồng bộ/lịch thực thi; chúng không phải data values cần copy nông.
- Object có identity bên ngoài như giao dịch, booking hoặc entity database có thể cần ID mới hoặc không được phép nhân bản.

Khi một domain object giữ những dependency này, thường nên copy **dữ liệu miền** sang object mới và **tiêm dependencies** theo vòng đời thích hợp, chứ không clone nguyên reference graph rồi mong mọi tài nguyên hoạt động độc lập.

Trong nhiều trường hợp, tạo **DTO/record snapshot** của dữ liệu quan trọng là lựa chọn chính xác hơn copy cả domain entity đang sống.

## 29. Có nên dùng serialization để deep copy?

Một số code cũ thử deep copy bằng cách serialize object ra bytes rồi deserialize thành object mới. Cách ấy có thể sao chép một graph thuộc phạm vi serialization, nhưng **không phải giải pháp copy tổng quát an toàn**:

- Không phải mọi object đều serializable.
- Serialization có hợp đồng riêng cho `transient`, custom read/write methods, identity, versioning và object resolution.
- Constructor/invariants có quy tắc riêng khi deserialize.
- Có chi phí CPU, bộ nhớ và rủi ro an ninh khi deserialize dữ liệu không đáng tin.
- Các resources sống như socket/connection không phù hợp để “copy qua byte stream”.
- Serialization không giải quyết hộ mục đích nghiệp vụ “đối tượng nào giữ ID, đối tượng nào phải mới”.

Vì vậy đừng dùng serialization chỉ để tránh viết copy constructor/factory rõ ràng. Nếu hệ thống vốn có một định dạng dữ liệu được kiểm soát và cần tạo DTO độc lập, hãy đánh giá serialization như **một thành phần riêng** với kiểm thử và an ninh phù hợp.

## 30. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Gọi `clone()` luôn copy sâu.” | `Object.clone()` mặc định copy nông các field references |
| “`Cloneable` định nghĩa `clone()` public.” | Marker interface không khai báo phương thức nào |
| “Implement `Cloneable` là mọi caller gọi `obj.clone()` được.” | `Object.clone()` protected; class thường phải công bố API riêng |
| “Không implement Cloneable thì `super.clone()` vẫn hoạt động.” | `Object.clone()` có thể ném `CloneNotSupportedException` |
| “`clone()` luôn gọi constructor rồi chép fields.” | `Object.clone()` không chạy constructor đối tượng copy |
| “Field final List tự bất biến.” | Final chặn gán reference, không chặn `List.add` |
| “`new ArrayList<>(old)` là deep copy list.” | Container mới, phần tử reference vẫn chia sẻ |
| “`List.copyOf` deep-copy mọi phần tử.” | Snapshot nông, phần tử mutable có thể vẫn alias |
| “`array.clone()` deep-copy các phần tử.” | Array mới, phần tử reference vẫn giữ chung |
| “Clone một `int[][]` độc lập mọi hàng.” | Mảng ngoài mới, các hàng bên trong mặc định chia sẻ |
| “Superclass clone tự biết copy field mutable của subclass.” | Subclass cần duy trì hợp đồng và copy field thích hợp |
| “Có chu trình thì cứ copy đệ quy.” | Cần nhớ map identity để tránh vòng vô hạn và giữ sharing |
| “Copy xong hai object phải có cùng mã nghiệp vụ.” | Cần hợp đồng riêng cho ID, equality và identity |
| “Object khác nhau phải có `hashCode` khác.” | Có thể collision; identity không bằng hash |
| “Clone trong một thread khác tự tạo snapshot nhất quán.” | Cần synchronization/consistency riêng |
| “Có thể clone connection/lock như dữ liệu.” | Resource ownership và lifecycle không copy bằng field |
| “Copy constructor luôn giữ runtime subclass.” | Constructor tạo chính kiểu được gọi, không tự virtual |
| “Object immutable bắt buộc phải clone để an toàn.” | Có thể chia sẻ an toàn tùy hợp đồng |

## 31. Hướng dẫn giải bài tập về shallow/deep copy

Khi đề cho class và hỏi sau `clone()` chương trình in gì:

1. Xem object runtime **có implement `Cloneable`** hay không và method clone thực sự gọi tới đâu.
2. Kiểm tra method clone có public/covariant return hay caller chỉ đang cố truy cập protected method.
3. Với `super.clone()`, hình dung **object root mới** và **từng field** được sao chép.
4. Đánh dấu primitive fields bằng giá trị độc lập; reference fields ban đầu **cùng trỏ** tới object con.
5. Nếu clone method gán lại một field bằng bản copy mới, vẽ lại cạnh tham chiếu ấy.
6. Nếu clone từng phần tử mutable, xem các object con đã mới hay còn chia sẻ references bên trong.
7. Khi có subclass, xem override clone nào được gọi và trường subclass nào đã được copy sâu.
8. Khi có final field, xem code có cố gán lại trong method thường hay không; lỗi biên dịch phải được xác định trước khi tính stdout.
9. Khi gặp mảng nhiều chiều, tách **mảng ngoài và từng hàng** thành các object riêng.
10. Nếu có mutation sau clone, xác định **object nào thực sự bị mutate**, rồi kiểm tra mọi reference đang trỏ tới object ấy.
11. Với copy constructor, đi theo các lệnh constructor: validation, defensive copy và những field được khởi tạo.
12. Với graph, cần xem có sharing/cycles và map identity không.
13. Cuối cùng mới tính `==`, `equals`, giá trị field và stdout.

Đừng trả lời “clone tạo bản sao nên không ảnh hưởng nhau” mà chưa chỉ ra **tham chiếu ở cấp nào** đã được sao chép.

## 32. Bài tập tự luyện

**Câu 1.** `Cloneable` có khai báo method `clone()` không? Vì sao một class implements Cloneable vẫn có thể không cho caller bên ngoài gọi `clone()`?

**Câu 2.** `Object.clone()` mặc định copy kiểu dữ liệu nguyên thủy và reference fields như thế nào?

**Câu 3.** Một class không implements Cloneable nhưng có method gọi `super.clone()`. Khi method chạy, chuyện gì xảy ra?

**Câu 4.** `Point` chỉ có hai field primitive `int x, y`. Sao chép nông đủ để độc lập trạng thái của hai field này không?

**Câu 5.** `Notebook` giữ `List<String> tags`. Sau `super.clone()`, bản copy gọi `tags.add("new")`. Bản gốc nhìn thấy gì? Vì sao?

**Câu 6.** Vì sao `List.copyOf(tags)` ở getter không tự sửa được alias do shallow clone tạo ra?

**Câu 7.** Một class giữ `final List<String> items`. Sau `super.clone()`, có thể viết `copy.items = new ArrayList<>(items)` trong clone method không?

**Câu 8.** Nếu constructor cấp một ID tăng dần, tại sao clone có thể tạo hai object có cùng ID?

**Câu 9.** `int[] a = {1,2}; int[] b=a.clone(); b[0]=9;`. Giá trị `a[0]` là gì?

**Câu 10.** `StringBuilder[] a` có một phần tử chứa `StringBuilder("X")`; `b=a.clone(); b[0].append("Y");`. Phần tử `a[0]` sẽ hiển thị gì?

**Câu 11.** `int[][] m={{1},{2}}; int[][] c=m.clone(); c[0][0]=7;`. `m[0][0]` còn là 1 hay đổi thành 7?

**Câu 12.** Một superclass implements Cloneable với public clone nông; subclass bổ sung field `ArrayList`. Nếu không override clone, rủi ro gì?

**Câu 13.** Khi deep copy graph A↔B bằng đệ quy, vì sao phải đưa A vào identity map **trước khi** duyệt cạnh A→B?

**Câu 14.** Hai fields trong source cùng trỏ một object con. Khi deep copy, có phải cứ tạo hai copies riêng của object con ấy mới là đúng không?

**Câu 15.** Khi nào copy constructor thích hợp hơn `Object.clone()`? Khi nào copy constructor không tự giải quyết đa hình?

**Câu 16.** Nếu `equals` của class được định nghĩa theo ID, `clone` giữ ID, `source == copy` và `source.equals(copy)` có thể lần lượt như thế nào?

**Câu 17.** Vì sao clone object đang được thread khác sửa có thể không tạo snapshot nhất quán?

**Câu 18.** Có thể xem serialization/deserialization là một phương thức deep copy hoàn hảo cho mọi object không?

### Lời giải

1. Không; Cloneable là marker interface. `Object.clone()` protected, class cần công bố method truy cập phù hợp nếu muốn người gọi dùng được.
2. Primitive fields chép giá trị; reference fields chép **giá trị tham chiếu**, nên object con có thể vẫn chia sẻ.
3. Thường nhận `CloneNotSupportedException` từ `Object.clone()`.
4. Có đối với đúng những field đó, nếu không có mutable object con khác.
5. Source cũng nhìn thấy phần tử `"new"`, vì hai notebooks đang trỏ cùng list.
6. `List.copyOf` chỉ tạo danh sách đọc/snapshot cho caller, không thay đổi field `tags` vốn đã alias giữa hai notebooks.
7. Không; field `final` không được gán lại trong phương thức thường. Dùng constructor/factory hay thiết kế khác.
8. Clone không chạy lại constructor cấp ID; giá trị ID được sao chép nguyên.
9. `1`: mảng primitive mới giữ giá trị riêng.
10. `"XY"`: hai mảng cùng trỏ StringBuilder phần tử.
11. `7`: mảng hàng được chia sẻ vì chỉ clone mảng ngoài.
12. Bản sao giữ cùng list của subclass; mutate copy có thể sửa source.
13. Để khi B đi ngược về A, map trả bản sao A đã tạo, tránh đệ quy vô hạn.
14. Không nhất thiết. Nếu sharing có nghĩa, dùng identity map để hai cạnh trong bản copy cùng trỏ một bản sao của object chung.
15. Copy constructor phù hợp khi cần validation/final fields/defensive copy; nó tạo kiểu được gọi chứ không tự động bảo toàn subclass runtime.
16. `false` và có thể `true`, nếu equals dựa trên ID giữ nguyên. Cần xem hợp đồng equality cụ thể.
17. Nhiều field/collection có thể được đọc ở các thời điểm khác nhau; clone không tự khóa mọi writer.
18. Không. Serialization có hợp đồng, ràng buộc type, lifecycle, hiệu năng và rủi ro an ninh riêng.

## 33. Checklist thiết kế một API sao chép

- Caller cần **object identity mới** hay chỉ cần một value view?
- Source có cần giữ nguyên sau copy, kể cả khi copy thất bại?
- Các primitive/immutable fields nào có thể sao chép giá trị/chia sẻ?
- Mutable references nào thuộc ownership của object và phải tách?
- Collection có mutable elements hay chỉ immutable values?
- Các reference lặp và chu trình có cần bảo toàn cấu trúc alias?
- Có field `final` khiến hậu xử lý clone khó/không hợp lệ?
- Constructor có kiểm tra invariant hoặc cấp ID duy nhất không?
- Hệ thống có subclasses thêm mutable fields không?
- `equals/hashCode` của bản copy mang ý nghĩa gì?
- Có tài nguyên không thể/không nên copy?
- Caller có được phép chỉnh trực tiếp mutable collection sau copy?
- Có hỗ trợ concurrency/snapshot nhất quán không?
- Có test mutation isolation theo **cả hai chiều** không?
- Nên đặt tên `clone()`, `copy()`, `snapshot()`, `withX()` hay `duplicateAsNew()` để truyền đúng ý nghĩa?
- Tài liệu API có nói rõ shallow/deep, identity, ownership, trường hợp null và failure policy không?

## 34. Tài liệu chính thức Java 17

- [Object.clone — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): quyền truy cập, shallow field copy và ngoại lệ.
- [Cloneable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface và ý nghĩa đối với Object.clone.
- [CloneNotSupportedException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CloneNotSupportedException.html): loại checked exception khi thao tác clone không được hỗ trợ.
- [Array — Java Language Specification 17, §10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): mảng, clone mảng và kiểu phần tử.
- [Object Creation — JLS 17 §12.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): khởi tạo object thông thường, khác với cơ chế native clone.
- [Final Fields — JLS 17 §17.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): ngữ nghĩa final fields trong Java Memory Model.
- [ArrayList — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): list mutable và copy constructor.
- [List.copyOf — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): immutable list snapshot ở mức collection.
- [Arrays.copyOf — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): sao chép mảng.
- [IdentityHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): so keys theo reference identity, phù hợp một số bài toán copy object graphs.
- [Effective Java, Third Edition — Item 13](https://www.pearson.com/en-us/subject-catalog/p/effective-java/P200000000182): chủ đề override `clone()` thận trọng; xem như gợi ý đọc thêm, không thay thế đặc tả Java.

**Kết luận:** `Cloneable` chỉ báo class cho phép cơ chế `Object.clone()`, không cung cấp method copy công khai; `Object.clone()` cơ bản **tạo object mới và copy nông các field** mà **không gọi constructor**. Với object chỉ chứa primitive/immutable values, bản sao nông có thể đủ. Với mutable references, collections, mảng nhiều chiều, các subclass và đồ thị có chu trình, cần thiết kế **copy semantics có chủ đích** và kiểm thử mutation isolation. Copy constructor/factory thường là lựa chọn rõ ràng hơn khi cần validation, field `final`, lifecycle và invariant của miền dữ liệu.
