# Hàm khởi tạo sao chép và phương thức tạo bản sao có tên trong Java

Khi cần tạo một đối tượng dựa trên đối tượng đang có, Java thường cho chúng ta hai cách thiết kế minh bạch: **hàm khởi tạo sao chép (copy constructor)** và **phương thức tạo bản sao có tên (named copy factory)**. Cả hai đều là API do lập trình viên định nghĩa, không phải một tính năng tự động được Java sinh cho mọi class.

Hàm khởi tạo sao chép thường có dạng `new Type(existing)`; factory có thể có tên như `Type.copyOf(existing)`, `Type.snapshotOf(source)` hoặc `Type.duplicateAsNew(source, newId)`. Tên gọi giúp người dùng biết điều gì được giữ lại, điều gì được tạo mới và quan hệ sở hữu với các object con có thay đổi hay không.

Điểm quan trọng nhất: **tạo object root mới chưa chắc đã tạo bản sao độc lập**. Nếu root mới vẫn trỏ đến cùng `ArrayList`, `Date`, array hoặc phần tử mutable, thay đổi ở một phía có thể làm phía kia đổi theo. Ngược lại, với immutable value objects, một copy factory còn có thể **trả lại cùng instance** nếu hợp đồng không yêu cầu identity mới.

Bài thuộc **Java core - class-object**, phần **Sao chép đối tượng**. Nội dung sử dụng Java **17+**, giải thích từ cú pháp constructor/factory, luật overload, validation, sao chép nông và sâu, defensive copies, kiểu `final` và `record`, phân biệt với `Object.clone()`, kế thừa và object slicing, copy đồ thị có chu trình, entity identity, ngoại lệ, concurrency và kiểm thử. Các chương trình hoàn chỉnh có tên tệp, lệnh chạy và **stdout xác định**; những snippet chỉ dùng để giải thích được ghi rõ.

## 1. Copy constructor là gì?

Trong Java, một **copy constructor** là constructor của class `T` nhận một đối tượng `T` (hoặc một kiểu nguồn liên quan) để khởi tạo object mới dựa trên dữ liệu có sẵn.

~~~java
final class Pixel {
    private final int x;
    private final int y;

    Pixel(int x, int y) {
        this.x = x;
        this.y = y;
    }

    Pixel(Pixel source) {
        this(source.x, source.y);
    }

    String describe() {
        return "(" + x + "," + y + ")";
    }
}
~~~

Đây là **class hợp lệ**, chưa có `main`. Lời gọi `new Pixel(existingPixel)` thực hiện constructor `Pixel(Pixel)` và tạo **một object Pixel mới**. Lệnh `this(source.x, source.y)` gọi constructor hai tham số trong cùng class, nhờ đó tránh nhân đôi quy tắc khởi tạo.

Không có từ khóa riêng tên `copy` hoặc annotation chuẩn nào khiến Java tự tạo copy constructor. Người thiết kế **phải viết** nó và tự quyết định:

- Field nào được copy nguyên giá trị?
- Field nào cần tạo bản sao object con?
- Có giữ các business IDs hay phải sinh mã mới?
- Có cần validation dữ liệu được lấy từ nguồn?
- Có cho phép `source == null` không?
- Object mới có phải luôn khác source theo `==` không?

Ở ví dụ Pixel chỉ có hai field primitive, copy theo giá trị là đủ để hai đối tượng độc lập về trạng thái ấy.

## 2. Không có copy constructor mặc định như C++

Nếu class Java khai báo:

~~~java
class Customer {
    private String name;

    Customer(String name) {
        this.name = name;
    }
}
~~~

thì Java **không tự sinh** constructor `Customer(Customer other)`. Lời gọi `new Customer(oldCustomer)` không biên dịch, vì constructor đang có chỉ nhận `String`.

Java có thể cung cấp **default no-argument constructor** trong những trường hợp class không khai báo constructor nào, nhưng đó **không phải copy constructor**. Và nếu class đã khai báo constructor, compiler không tự bổ sung constructor không tham số.

Cũng đừng nhầm:

~~~java
Customer second = first;
~~~

Đây là câu lệnh minh họa trong ngữ cảnh có hai biến cùng kiểu; nó **chỉ sao chép giá trị tham chiếu**, không tạo một Customer mới. `first == second` sẽ là true nếu `first` không null.

### Ba cách tạo có kết quả khác nhau

| Biểu thức | Có tạo object root mới? | Ý nghĩa |
| --- | --- | --- |
| `T b = a;` | Không | Hai tham chiếu trỏ cùng object |
| `T b = new T(a);` | Có khi constructor trả bình thường | Copy constructor do bạn tự định nghĩa |
| `T b = T.copyOf(a);` | Tùy hợp đồng factory | Có thể tạo mới hoặc tái sử dụng immutable instance |
| `T b = a.clone();` | Theo hợp đồng `clone` thực tế | Không tự đồng nghĩa deep copy |

Chỉ đọc tên method là **chưa đủ**; cần nhìn hợp đồng tài liệu và phần triển khai.

## 3. Thực nghiệm 1 — gán tham chiếu khác tạo bản sao

Tạo tệp **`CopyConstructorBasicsDemo.java`**:

~~~java
final class PointValue {
    private final int x;
    private final int y;

    PointValue(int x, int y) {
        this.x = x;
        this.y = y;
    }

    PointValue(PointValue source) {
        this(source.x, source.y);
    }

    String describe() {
        return "(" + x + "," + y + ")";
    }

    boolean sameCoordinates(PointValue other) {
        return other != null && x == other.x && y == other.y;
    }
}

public class CopyConstructorBasicsDemo {
    public static void main(String[] args) {
        PointValue first = new PointValue(2, 5);
        PointValue alias = first;
        PointValue copied = new PointValue(first);

        System.out.println("alias identity=" + (first == alias));
        System.out.println("copy identity=" + (first == copied));
        System.out.println("same coordinates="
                + first.sameCoordinates(copied));
        System.out.println("first=" + first.describe());
        System.out.println("copied=" + copied.describe());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CopyConstructorBasicsDemo.java
java CopyConstructorBasicsDemo
~~~

**Stdout chính xác:**

~~~text
alias identity=true
copy identity=false
same coordinates=true
first=(2,5)
copied=(2,5)
~~~

`alias` trỏ chính object `first`; `copied` là object khác với các giá trị ban đầu bằng nhau. `sameCoordinates` là method riêng diễn đạt **bằng giá trị tọa độ**, không phải `Object.equals`.

Mặc dù Pixel và PointValue chứa các fields `final`, copy constructor **vẫn khởi tạo lại fields của object mới** theo đúng quy tắc constructor Java. `final` ngăn gán lại fields của cùng object sau khi khởi tạo, không ngăn tạo object khác có cùng giá trị.

## 4. Có tên rõ hơn: named copy factory

Một **named copy factory** là static method được đặt tên theo mục đích, trả đối tượng hoặc giá trị phù hợp với việc sao chép. Ví dụ:

~~~java
final class Snapshot {
    private final String code;

    private Snapshot(String code) {
        this.code = code;
    }

    static Snapshot copyOf(Snapshot source) {
        java.util.Objects.requireNonNull(source, "source");
        return new Snapshot(source.code);
    }

    static Snapshot fromCode(String code) {
        return new Snapshot(
                java.util.Objects.requireNonNull(code, "code"));
    }

    String code() {
        return code;
    }
}
~~~

Đây là **class hoàn chỉnh không có main**. Factory `copyOf` đọc trạng thái từ đối tượng hiện có và tạo instance mới; `fromCode` nhận dữ liệu thô và tạo object theo một đường khác.

Điểm mạnh của factory so với constructor là **tên có thể diễn đạt nhiều chính sách** mà không phải cố phân biệt tất cả qua kiểu tham số:

- `copyOf(T source)`: giá trị tương đương; identity mới hay tái sử dụng cần công bố rõ.
- `snapshotOf(MutableSource source)`: chụp một ảnh giá trị tại thời điểm gọi.
- `duplicateAsNew(Entity source, String newId)`: nhân dữ liệu cho entity **khác định danh**.
- `deepCopyOf(Graph root)`: cố ý tách mutable graph theo hợp đồng.
- `fromDto(Dto dto)`: chuyển đổi từ representation bên ngoài; không nhất thiết là copy cùng kiểu.
- `withStatus(State next)`: tạo phiên bản mang trạng thái mới.

Không có **ngữ nghĩa Java bắt buộc** cho những tên này; thư viện/ứng dụng phải tài liệu hóa và thực thi nhất quán.

## 5. Copy constructor hay factory? Các khác biệt cốt lõi

| Tiêu chí | Copy constructor | Named copy factory |
| --- | --- | --- |
| Cú pháp | `new T(source)` | `T.copyOf(source)` |
| Tên mô tả mục đích | Chỉ tên class | Có thể `snapshotOf`, `duplicateAsNew`, `copyValidated` |
| Kiểu object đích | Chính class constructor gọi | Có thể trả implementation thích hợp theo hợp đồng |
| Identity root mới | Có, nếu `new` hoàn thành bình thường | Không bắt buộc, có thể tái sử dụng immutable instance |
| Quy tắc khởi tạo | Constructor chain và definite assignment | Logic tùy ý, thường gọi private constructor |
| Dùng với `final` fields | Thuận lợi vì khởi tạo trong constructor | Thuận lợi khi gọi constructor hợp lệ |
| Kiểm soát validation | Tập trung bằng `this(...)` | Tập trung thông qua constructor/private factory |
| Các copy policies khác nhau | Cần overload hoặc parameters | Nhiều tên rõ nghĩa, giảm boolean flags |
| Polymorphism | `new Base(source)` không tự giữ subclass | Có thể điều phối kiểu đích, nhưng phải tự triển khai |
| `null` input | Tùy constructor | Tùy factory, có thể kiểm tra rõ từ đầu |

**Factory không tự deep-copy chỉ vì có tên `deepCopyOf`.** Tính đúng đắn là kết quả của thuật toán và kiểm thử object graph. Tương tự, copy constructor cũng có thể là shallow copy nếu chỉ gán các reference fields.

## 6. Copy constructor nên ủy quyền về đường validation chung

Nếu class có nhiều ràng buộc, đừng nhân bản các khối kiểm tra trong từng constructor:

~~~java
final class RetryPolicy {
    private final int maxRetries;
    private final long timeoutMillis;

    RetryPolicy(int maxRetries, long timeoutMillis) {
        if (maxRetries < 0 || maxRetries > 10) {
            throw new IllegalArgumentException("retry ngoài 0..10");
        }
        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException("timeout không dương");
        }
        this.maxRetries = maxRetries;
        this.timeoutMillis = timeoutMillis;
    }

    RetryPolicy(RetryPolicy other) {
        this(
                java.util.Objects.requireNonNull(
                        other, "other").maxRetries,
                other.timeoutMillis);
    }

    String describe() {
        return maxRetries + "/" + timeoutMillis;
    }
}
~~~

Đây là **class hợp lệ**, không có main. Copy constructor gọi primary constructor, nơi định nghĩa invariant. `Objects.requireNonNull(other)` được kiểm tra khi đánh giá đối số thứ nhất của `this(...)`; với `other=null`, việc đánh giá dừng bằng `NullPointerException`, không tiếp tục đọc `other.timeoutMillis`.

Trong constructor gọi `this(...)`, lời gọi đó phải tuân quy tắc Java về constructor invocation; không thể tùy tiện đặt các lệnh khởi tạo trước `this(...)` trong Java 17. Nếu validation phức tạp, dùng static helper khi đánh giá arguments hoặc factory nhận input rồi gọi constructor hợp lệ.

Nếu copy constructor **bỏ qua primary validation** và gán fields trực tiếp, một thay đổi về invariant sau này có thể không được áp dụng trên mọi đường tạo bản sao.

## 7. Thực nghiệm 2 — validation áp dụng cho cả copy constructor

Tạo tệp **`ValidatedCopyDemo.java`**:

~~~java
import java.util.Objects;

final class Limits {
    private final int min;
    private final int max;

    Limits(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        this.min = min;
        this.max = max;
    }

    Limits(Limits source) {
        this(
                Objects.requireNonNull(source, "source").min,
                source.max);
    }

    Limits withBounds(int nextMin, int nextMax) {
        return new Limits(nextMin, nextMax);
    }

    @Override
    public String toString() {
        return "[" + min + "," + max + "]";
    }
}

public class ValidatedCopyDemo {
    public static void main(String[] args) {
        Limits original = new Limits(2, 8);
        Limits copy = new Limits(original);
        Limits updated = copy.withBounds(5, 10);

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);
        System.out.println("updated=" + updated);
        System.out.println("different=" + (original != copy));

        try {
            copy.withBounds(9, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
        System.out.println("copy remains=" + copy);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ValidatedCopyDemo.java
java ValidatedCopyDemo
~~~

**Stdout:**

~~~text
original=[2,8]
copy=[2,8]
updated=[5,10]
different=true
invalid=min > max
copy remains=[2,8]
~~~

Mọi kết quả mới được tạo qua constructor kiểm tra `min <= max`. Phương thức `withBounds` không “sửa từng field của copy”, mà **xây dựng một object khác** bằng constructor hợp lệ.

Bản gốc và copy ban đầu bằng về **giá trị minh họa** nhưng khác identity; update về `[5,10]` cũng không thay đổi copy.

## 8. Sao chép nông: root mới nhưng object con cũ

Xét class:

~~~java
class BadNotebook {
    private java.util.ArrayList<String> tags;

    BadNotebook(java.util.ArrayList<String> tags) {
        this.tags = tags;
    }

    BadNotebook(BadNotebook other) {
        this.tags = other.tags;
    }

    void addTag(String tag) {
        tags.add(tag);
    }
}
~~~

Đây là **class hợp lệ nhưng cố ý có thiết kế sao chép không độc lập**. Mặc dù `new BadNotebook(source)` tạo object Notebook khác, `this.tags = other.tags` chỉ sao chép reference, khiến cả hai notebooks trỏ **cùng ArrayList**.

Sơ đồ:

~~~text
BadNotebook original ------+
                           |
                           v
                     ArrayList tags ["java"]
                           ^
                           |
BadNotebook copy ----------+
~~~

Nếu `copy.addTag("oop")`, bản gốc cũng thấy `oop`. Thao tác ấy được gọi **shallow copy** ở field reference.

Shallow copy không luôn sai: có thể chia sẻ các object **immutable** hoặc dependency được chủ đích dùng chung. Nó sai khi factory/constructor hứa **độc lập dữ liệu mutable** nhưng vẫn giữ alias.

## 9. Thực nghiệm 3 — minh họa alias và copy list độc lập

Tạo tệp **`ShallowAndListCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class LabelBook {
    private final List<String> labels;

    LabelBook(List<String> labels) {
        this.labels = labels;
    }

    LabelBook(LabelBook other) {
        this.labels = other.labels;
    }

    void add(String label) {
        labels.add(label);
    }

    List<String> view() {
        return List.copyOf(labels);
    }

    boolean sharesListWith(LabelBook other) {
        return labels == other.labels;
    }
}

final class SafeLabelBook {
    private final List<String> labels;

    SafeLabelBook(List<String> labels) {
        this.labels = new ArrayList<>(labels);
    }

    SafeLabelBook(SafeLabelBook other) {
        this(other.labels);
    }

    void add(String label) {
        labels.add(label);
    }

    List<String> view() {
        return List.copyOf(labels);
    }

    boolean sharesListWith(SafeLabelBook other) {
        return labels == other.labels;
    }
}

public class ShallowAndListCopyDemo {
    public static void main(String[] args) {
        List<String> supplied = new ArrayList<>();
        supplied.add("java");

        LabelBook original = new LabelBook(supplied);
        LabelBook shallow = new LabelBook(original);
        shallow.add("oop");

        System.out.println("shallow shares="
                + original.sharesListWith(shallow));
        System.out.println("original=" + original.view());
        System.out.println("shallow=" + shallow.view());

        SafeLabelBook safe = new SafeLabelBook(supplied);
        SafeLabelBook copy = new SafeLabelBook(safe);
        copy.add("sql");

        System.out.println("safe shares="
                + safe.sharesListWith(copy));
        System.out.println("safe=" + safe.view());
        System.out.println("copy=" + copy.view());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ShallowAndListCopyDemo.java
java ShallowAndListCopyDemo
~~~

**Stdout chính xác:**

~~~text
shallow shares=true
original=[java, oop]
shallow=[java, oop]
safe shares=false
safe=[java, oop]
copy=[java, oop, sql]
~~~

`SafeLabelBook` tạo một list container mới khi nhận input, và copy constructor lại gọi constructor ấy. Vì các phần tử đều là `String` bất biến, hai phiên bản độc lập về việc thêm/bớt tags.

**Lưu ý:** `SafeLabelBook` trong ví dụ vẫn **mutable** qua `add`. Copy constructor giúp các instances có collections riêng, nhưng không biến chúng thành immutable. Cần tách rõ **copy isolation** và **immutability**: hai mục tiêu có liên quan nhưng không giống nhau.

## 10. Sao chép list không đồng nghĩa sao chép phần tử

Nếu list giữ **mutable elements**, các cách:

~~~java
new java.util.ArrayList<>(originalLines);
java.util.List.copyOf(originalLines);
~~~

là **biểu thức minh họa**, giả định biến `originalLines` có kiểu `List<Line>` và phần tử thích hợp. Chúng tạo/đưa về list chứa **cùng tham chiếu tới các Line**; không tự tạo Line objects mới.

Phân biệt:

1. **Root copy:** tạo đối tượng chứa list mới.
2. **Container copy:** tạo list object mới.
3. **Element copy:** tạo bản sao từng mutable Line.
4. **Nested copy:** nếu Line có object con mutable, tiếp tục xác định ranh giới cần copy.

Một bản deep copy đúng theo miền dữ liệu không nhất thiết copy **mọi thứ**, nhưng phải tách tất cả mutable state mà hợp đồng cam kết không chia sẻ.

Ví dụ nếu `Line` chỉ có `String sku` và `int quantity`, copy Line tạo object mới và vẫn có thể chia sẻ String sku vì String bất biến. Nếu `Line` có một `Date` mutable hoặc `List<Discount>`, phải quyết định copy sâu đến mức nào.

## 11. Thực nghiệm 4 — copy constructor cho từng phần tử mutable

Tạo tệp **`DeepElementCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class MutableLine {
    private final String sku;
    private int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        setQuantity(quantity);
    }

    MutableLine(MutableLine other) {
        this(
                Objects.requireNonNull(other, "other").sku,
                other.quantity);
    }

    void setQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        quantity = next;
    }

    String describe() {
        return sku + ":" + quantity;
    }
}

final class OrderDraft {
    private final List<MutableLine> lines;

    OrderDraft(List<MutableLine> input) {
        Objects.requireNonNull(input, "input");
        List<MutableLine> copied = new ArrayList<>();
        for (MutableLine line : input) {
            copied.add(new MutableLine(line));
        }
        lines = copied;
    }

    OrderDraft(OrderDraft source) {
        this(Objects.requireNonNull(source, "source").lines);
    }

    void changeQuantity(int index, int quantity) {
        lines.get(index).setQuantity(quantity);
    }

    List<String> describe() {
        return lines.stream()
                .map(MutableLine::describe)
                .toList();
    }
}

public class DeepElementCopyDemo {
    public static void main(String[] args) {
        MutableLine supplied = new MutableLine("P1", 2);
        List<MutableLine> input = new ArrayList<>();
        input.add(supplied);

        OrderDraft source = new OrderDraft(input);
        OrderDraft copy = new OrderDraft(source);

        supplied.setQuantity(99);
        copy.changeQuantity(0, 8);

        System.out.println("input=" + supplied.describe());
        System.out.println("source=" + source.describe());
        System.out.println("copy=" + copy.describe());
        System.out.println("same root=" + (source == copy));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DeepElementCopyDemo.java
java DeepElementCopyDemo
~~~

**Stdout:**

~~~text
input=P1:99
source=[P1:2]
copy=[P1:8]
same root=false
~~~

Ở đây constructor của `OrderDraft` thực hiện **element copy**, nên source không phụ thuộc vào `supplied` sau khi nhận input; bản copy không phụ thuộc vào source khi sửa quantity.

Getter `describe()` trả các chuỗi `String` bất biến, **không công bố MutableLine nội bộ**. Dù list được xây mới và các phần tử được copy khi tạo, nếu getter trả thẳng `MutableLine` bên trong thì caller vẫn có thể sửa state và làm hỏng chính sách sở hữu. Defensive copying có thể cần **cả chiều vào và chiều ra**.

## 12. Copy constructor bảo vệ đầu vào không đồng nghĩa bảo vệ đầu ra

Ví dụ một `Schedule` lưu `Date` mutable:

~~~java
final class Schedule {
    private final java.util.Date when;

    Schedule(java.util.Date when) {
        this.when = new java.util.Date(
                java.util.Objects.requireNonNull(when).getTime());
    }

    Schedule(Schedule other) {
        this(other.when);
    }

    java.util.Date when() {
        return new java.util.Date(when.getTime());
    }
}
~~~

Đây là class hợp lệ, không có `main`. Nó copy `Date` khi nhận, copy ở copy constructor và copy trước khi trả khỏi getter. Nếu bỏ việc tạo `new Date(...)` ở getter, caller có thể nhận reference của `Date` nội bộ rồi gọi `setTime`.

Khi xây immutable value objects, sẽ dễ hơn nếu chọn dữ liệu vốn bất biến, ví dụ `java.time.Instant`. Nhưng khi tích hợp API cũ dùng Date hoặc collections mutable, defensive copy là kỹ thuật cần thiết.

## 13. Thực nghiệm 5 — ngày giờ và factory tạo snapshot

Tạo tệp **`TimestampCopyDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

final class TimestampSnapshot {
    private final Date instant;

    TimestampSnapshot(Date input) {
        Date checked = Objects.requireNonNull(input, "input");
        instant = new Date(checked.getTime());
    }

    TimestampSnapshot(TimestampSnapshot other) {
        this(Objects.requireNonNull(other, "other").instant);
    }

    static TimestampSnapshot snapshotOf(Date input) {
        return new TimestampSnapshot(input);
    }

    static TimestampSnapshot copyOf(TimestampSnapshot source) {
        return new TimestampSnapshot(source);
    }

    Date toDate() {
        return new Date(instant.getTime());
    }

    long epochMillis() {
        return instant.getTime();
    }
}

public class TimestampCopyDemo {
    public static void main(String[] args) {
        Date input = new Date(1000L);
        TimestampSnapshot first =
                TimestampSnapshot.snapshotOf(input);
        TimestampSnapshot second =
                TimestampSnapshot.copyOf(first);

        input.setTime(2000L);
        Date extracted = second.toDate();
        extracted.setTime(3000L);

        System.out.println("input=" + input.getTime());
        System.out.println("first=" + first.epochMillis());
        System.out.println("second=" + second.epochMillis());
        System.out.println("extracted=" + extracted.getTime());
        System.out.println("different=" + (first != second));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 TimestampCopyDemo.java
java TimestampCopyDemo
~~~

**Stdout chính xác:**

~~~text
input=2000
first=1000
second=1000
extracted=3000
different=true
~~~

`snapshotOf(Date)` diễn đạt rõ “chụp giá trị timestamp từ một nguồn mutable”; `copyOf(TimestampSnapshot)` diễn đạt “tạo bản sao từ snapshot hiện có”. Cả hai sử dụng cùng một constructor đảm bảo tính độc lập.

Sử dụng `Instant` thay `Date` trong thiết kế mới có thể cho phép chia sẻ reference an toàn hơn, vì `Instant` là immutable. Đối với thời điểm, đừng nhầm đối tượng `Date` là bất biến chỉ vì field giữ nó được đánh dấu `final`.

## 14. Phương thức có tên giúp phân biệt sao chép ID và nhân thực thể mới

Giả sử ứng dụng có `DocumentDraft` với:

- `documentId`: định danh bản thảo.
- `title`: tiêu đề.
- `sections`: danh sách các đoạn văn.

Hai yêu cầu khác hẳn nhau:

1. **Snapshot của cùng draft**: giữ ID và dữ liệu để so sánh/audit.
2. **Tạo draft mới từ template cũ**: giữ nội dung nhưng nhận **ID mới** do caller hoặc hệ thống cung cấp.

Nếu cả hai đều là `new DocumentDraft(old)`, người đọc khó biết cách xử lý ID. Factory có tên `copyPreservingId` và `duplicateAsNew` làm sự khác biệt rõ ràng.

Các business rules như ID duy nhất, quyền tạo bản sao và trạng thái “draft” phải được kiểm tra tại tầng thích hợp. **Chỉ tạo ID chuỗi mới trong RAM không đảm bảo duy nhất toàn hệ thống**, và không thay thế unique constraint ở database.

## 15. Thực nghiệm 6 — `copyPreservingId` và `duplicateAsNew`

Tạo tệp **`NamedCopyPoliciesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class DocumentDraft {
    private final String id;
    private final String title;
    private final List<String> sections;

    private DocumentDraft(
            String id, String title, List<String> sections) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        this.id = id;
        this.title = Objects.requireNonNull(title, "title");
        this.sections = List.copyOf(sections);
    }

    static DocumentDraft create(
            String id, String title, List<String> sections) {
        return new DocumentDraft(id, title, sections);
    }

    static DocumentDraft copyPreservingId(
            DocumentDraft source) {
        Objects.requireNonNull(source, "source");
        return new DocumentDraft(
                source.id, source.title, source.sections);
    }

    static DocumentDraft duplicateAsNew(
            DocumentDraft source, String newId) {
        Objects.requireNonNull(source, "source");
        return new DocumentDraft(
                newId, source.title, source.sections);
    }

    DocumentDraft withTitle(String next) {
        return new DocumentDraft(id, next, sections);
    }

    String describe() {
        return id + ":" + title + sections;
    }
}

public class NamedCopyPoliciesDemo {
    public static void main(String[] args) {
        DocumentDraft original = DocumentDraft.create(
                "D1", "Java", List.of("A", "B"));

        DocumentDraft snapshot =
                DocumentDraft.copyPreservingId(original);
        DocumentDraft duplicated =
                DocumentDraft.duplicateAsNew(original, "D2");
        DocumentDraft renamed =
                duplicated.withTitle("Java 17");

        System.out.println("original=" + original.describe());
        System.out.println("snapshot=" + snapshot.describe());
        System.out.println("duplicated=" + duplicated.describe());
        System.out.println("renamed=" + renamed.describe());
        System.out.println("different roots="
                + (original != snapshot));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NamedCopyPoliciesDemo.java
java NamedCopyPoliciesDemo
~~~

**Stdout:**

~~~text
original=D1:Java[A, B]
snapshot=D1:Java[A, B]
duplicated=D2:Java[A, B]
renamed=D2:Java 17[A, B]
different roots=true
~~~

Các versions đều chứa immutable `String` và unmodifiable snapshot `List<String>`, nên có thể chia sẻ thành phần bất biến mà không tạo mutable alias. `withTitle` tạo object mới cùng ID nhưng tiêu đề mới.

**Quan trọng về nghiệp vụ:** Hai objects cùng `id=D1` không có nghĩa có hai documents khác nhau trong database; `copyPreservingId` chỉ là **snapshot value trong bộ nhớ**. Trong hệ thống lưu trữ, bản ghi được tạo mới phải tuân chính sách định danh và transaction riêng.

## 16. `copyOf` trên immutable value có thể trả lại `this`

Trong thư viện chuẩn Java, một số factory `copyOf` dành cho immutable collections **không cam kết luôn tạo object khác identity**. Ví dụ `List.copyOf` có thể tái sử dụng một input vốn là unmodifiable list thích hợp.

Một named copy factory của immutable value object cũng có thể chọn cách này:

~~~java
record Coordinates(int x, int y) {
    static Coordinates copyOf(Coordinates source) {
        return java.util.Objects.requireNonNull(source);
    }
}
~~~

Đây là record hợp lệ. Method có tên `copyOf` ở đây chỉ yêu cầu kết quả **tương đương giá trị**; nó trả source trực tiếp để tránh cấp phát.

Đừng gọi contract này là **fresh independent identity copy**. Nếu API hứa object mới bằng `!=`, cần viết một factory khác rõ ràng, ví dụ `freshCopyOf`, và thật sự tạo object bằng `new`.

### Quy tắc lựa chọn

- Immutable value: chia sẻ object có thể an toàn.
- Mutable object: trả cùng object khi caller kỳ vọng bản copy riêng thường phá hợp đồng.
- Entity: identity mới hay giữ ID là **quyết định nghiệp vụ**.
- Snapshot: có thể dùng shared immutable nodes nếu tất cả mutation paths được cách ly.
- Graph: phải quyết định có giữ các quan hệ alias nội bộ không.

## 17. Thực nghiệm 7 — factory trả cùng instance hoặc tạo fresh instance

Tạo tệp **`ReusableValueCopyDemo.java`**:

~~~java
import java.util.Objects;

record Coordinates(int x, int y) {
    static Coordinates copyOf(Coordinates source) {
        return Objects.requireNonNull(source, "source");
    }

    static Coordinates freshCopyOf(Coordinates source) {
        Objects.requireNonNull(source, "source");
        return new Coordinates(source.x(), source.y());
    }
}

public class ReusableValueCopyDemo {
    public static void main(String[] args) {
        Coordinates original = new Coordinates(3, 7);
        Coordinates reused = Coordinates.copyOf(original);
        Coordinates fresh = Coordinates.freshCopyOf(original);

        System.out.println("reused identity="
                + (original == reused));
        System.out.println("fresh identity="
                + (original == fresh));
        System.out.println("fresh value="
                + original.equals(fresh));
        System.out.println("original=" + original);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ReusableValueCopyDemo.java
java ReusableValueCopyDemo
~~~

**Stdout chính xác:**

~~~text
reused identity=true
fresh identity=false
fresh value=true
original=Coordinates[x=3, y=7]
~~~

Cả `copyOf` và `freshCopyOf` đều trả giá trị đúng. Khác biệt là **lời hứa về identity**. `record` có `equals` dựa trên components ở trường hợp này, nên một fresh instance vẫn có thể bằng giá trị với source.

Đây là ví dụ lý do nên đọc tài liệu của API `copyOf` chứ không mặc định “copy” luôn tạo thêm object.

## 18. Copy constructors và records Java 17

Record có canonical constructor nhận **từng component**, nhưng Java **không tự sinh** copy constructor `RecordType(RecordType other)`. Bạn có thể tự viết constructor dạng đó:

~~~java
record EmployeeInfo(String name, int level) {
    EmployeeInfo {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        if (level < 1) {
            throw new IllegalArgumentException("level sai");
        }
    }

    EmployeeInfo(EmployeeInfo source) {
        this(source.name(), source.level());
    }

    EmployeeInfo withLevel(int nextLevel) {
        return new EmployeeInfo(name, nextLevel);
    }
}
~~~

Đây là một **record Java 17 hợp lệ**, không có main. Constructor sao chép dùng `this(source.name(), source.level())`; tham chiếu nguồn null sẽ dẫn tới `NullPointerException` khi đọc component nếu không được chặn trước.

Record components được giữ trong private final fields, nhưng **không tự deep-copy mutable components** như `List` hoặc array. Vì vậy thêm copy constructor nhận record rồi gọi canonical constructor chưa đủ nếu canonical constructor cũng giữ mutable reference trực tiếp.

Với records chứa dữ liệu mutable, nên đặt defensive copy trong **compact canonical constructor**, và bảo vệ accessor nếu component vẫn mutable.

## 19. Thực nghiệm 8 — record copy constructor và update có kiểm tra

Tạo tệp **`RecordCopyConstructorDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

record Labels(List<String> values) {
    Labels {
        values = List.copyOf(
                Objects.requireNonNull(values, "values"));
    }

    Labels(Labels source) {
        this(Objects.requireNonNull(source, "source").values());
    }

    Labels withAdded(String value) {
        Objects.requireNonNull(value, "value");
        var next = new java.util.ArrayList<>(values);
        next.add(value);
        return new Labels(next);
    }
}

public class RecordCopyConstructorDemo {
    public static void main(String[] args) {
        var input = new java.util.ArrayList<String>();
        input.add("java");

        Labels original = new Labels(input);
        Labels copy = new Labels(original);
        Labels expanded = copy.withAdded("oop");

        input.add("external");

        System.out.println("original=" + original.values());
        System.out.println("copy=" + copy.values());
        System.out.println("expanded=" + expanded.values());
        System.out.println("new root=" + (original != copy));
        System.out.println("same value="
                + original.equals(copy));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 RecordCopyConstructorDemo.java
java RecordCopyConstructorDemo
~~~

**Stdout:**

~~~text
original=[java]
copy=[java]
expanded=[java, oop]
new root=true
same value=true
~~~

Compact constructor `Labels { values = List.copyOf(...); }` đảm bảo source input không còn khả năng sửa list representation bên trong record. `String` elements bất biến, nên list snapshot đủ cho dữ liệu này.

`new Labels(original)` tạo record mới, nhưng cùng component values; `equals` của record so components và trả true. `expanded` là phiên bản giá trị khác, không mutate original hay copy.

## 20. `final` fields có thuận lợi gì cho copy constructors?

Với một class có field `final`:

~~~java
final class FileInfo {
    private final String path;
    private final long length;

    FileInfo(String path, long length) {
        this.path = java.util.Objects.requireNonNull(path);
        if (length < 0) {
            throw new IllegalArgumentException("length âm");
        }
        this.length = length;
    }

    FileInfo(FileInfo source) {
        this(source.path, source.length);
    }
}
~~~

Đây là class hợp lệ. Copy constructor **khởi tạo một object mới**, nên có thể gán các blank final fields thông qua constructor chain đúng luật Java.

Điều này khác với `Object.clone()`: `super.clone()` thường sao chép các giá trị fields mà **không chạy constructors thường**; khi field `final` trỏ tới mutable object, không thể tùy ý viết `copy.finalList = new ArrayList<>(...)` sau clone trong code Java bình thường.

Copy constructor/factory thường thuận tiện hơn khi:

- Muốn chạy validation/normalization.
- Có final reference fields cần trỏ tới **những object con mới**.
- Muốn cấp ID hoặc resource theo quy tắc riêng.
- Muốn phân biệt shallow copy, deep copy và duplicate bằng các tên API.
- Không cần tự động preserve subclass runtime class.

Nhưng tạo bằng constructor không **tự động deep-copy**: vẫn cần code sao chép cho mutable data.

## 21. So sánh với `Object.clone()` và `Cloneable`

| Khía cạnh | Copy constructor/factory | `Object.clone()` |
| --- | --- | --- |
| Cần `implements Cloneable`? | Không | Thường có nếu dựa trên `super.clone()` |
| Có chạy constructor để tạo object? | Có với `new T(...)` | Không chạy constructor bình thường của object clone |
| Quy tắc sao chép | Do constructor/factory viết | `super.clone()` cơ bản copy nông các fields |
| Xử lý mutable references | Cần thiết kế | Cần thiết kế |
| `final` fields | Khởi tạo thuận lợi trong constructor | Khó thay reference final sau shallow clone |
| Exception | Theo validation/operation đã định nghĩa | `CloneNotSupportedException` theo cơ chế gốc |
| Preserve runtime subclass | Không tự động | `super.clone()` tạo object cùng runtime class |
| API tên rõ ràng | Đặt tên theo policy | Method thường chỉ mang tên `clone` |
| Polymorphic copying | Cần virtual copy contract riêng nếu muốn | Có cơ chế của clone nhưng phải xem hợp đồng hierarchy |

**Cloneable là marker interface**, không khai báo `clone()`. `Object.clone()` có quyền `protected`; tự viết `implements Cloneable` không tự làm caller bên ngoài có một public method `clone()`.

Đối với domain models muốn validation và control, copy constructor/factory thường **dễ diễn đạt hợp đồng** hơn. Điều đó không có nghĩa không bao giờ dùng `clone()`: nhiều APIs có phương thức clone riêng được tài liệu hóa và phù hợp với nhu cầu cụ thể.

## 22. Kế thừa: copy constructor của superclass có thể “cắt” dữ liệu subclass

Khi có:

~~~java
class Document {
    final String title;

    Document(String title) {
        this.title = title;
    }

    Document(Document source) {
        this(source.title);
    }
}

class PdfDocument extends Document {
    final int pages;

    PdfDocument(String title, int pages) {
        super(title);
        this.pages = pages;
    }
}
~~~

Đây là các class minh họa hợp lệ, không có main. Nếu `Document source = new PdfDocument("Guide", 12)`, lời gọi `new Document(source)` tạo **chính Document**, không phải PdfDocument, vì Java đã biết class constructor đang được gọi.

Dữ liệu `pages` riêng của PdfDocument **không có chỗ để lưu** trong Document mới. Hiện tượng này đôi khi được gọi là **object slicing ở cấp mô hình**, tương tự thuật ngữ trong các ngôn ngữ khác; trong Java object chưa từng “bị cắt bộ nhớ”, mà ta đã **chủ động tạo một Base object mới thiếu state subclass**.

### Subclass copy constructor cần copy state của chính mình

~~~java
class CopyableDocument extends Document {
    final int version;

    CopyableDocument(String title, int version) {
        super(title);
        this.version = version;
    }

    CopyableDocument(CopyableDocument other) {
        super(other);
        this.version = other.version;
    }
}
~~~

Đây là lớp minh họa hợp lệ khi đứng cùng các lớp Document ở trên. `super(other)` gọi copy constructor của superclass; subclass sau đó khởi tạo field `version` của mình.

Nếu subclass có field mutable thì cần sao chép theo ownership, không chỉ `this.mutable = other.mutable`.

## 23. Thực nghiệm 9 — phân biệt copy lớp cơ sở và copy đúng subclass

Tạo tệp **`InheritanceCopyDemo.java`**:

~~~java
class Report {
    private final String name;

    Report(String name) {
        this.name = name;
    }

    Report(Report other) {
        this(other.name);
    }

    String describe() {
        return "Report:" + name;
    }
}

final class PdfReport extends Report {
    private final int pages;

    PdfReport(String name, int pages) {
        super(name);
        this.pages = pages;
    }

    PdfReport(PdfReport other) {
        super(other);
        this.pages = other.pages;
    }

    @Override
    String describe() {
        return super.describe() + ",pages=" + pages;
    }
}

public class InheritanceCopyDemo {
    public static void main(String[] args) {
        PdfReport pdf = new PdfReport("Guide", 12);
        Report asBase = pdf;

        Report baseCopy = new Report(asBase);
        PdfReport exactCopy = new PdfReport(pdf);

        System.out.println("source=" + pdf.describe());
        System.out.println("base copy=" + baseCopy.describe());
        System.out.println("exact copy=" + exactCopy.describe());
        System.out.println("base type="
                + baseCopy.getClass().getSimpleName());
        System.out.println("exact type="
                + exactCopy.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InheritanceCopyDemo.java
java InheritanceCopyDemo
~~~

**Stdout chính xác:**

~~~text
source=Report:Guide,pages=12
base copy=Report:Guide
exact copy=Report:Guide,pages=12
base type=Report
exact type=PdfReport
~~~

`new Report(asBase)` không thể tự biết nên gọi `new PdfReport(...)`; constructor không virtual dispatch như một instance method bình thường. `new PdfReport(pdf)` mới giữ các trường của subtype.

**Cảnh báo:** nếu API hứa “copy nhưng giữ đúng kiểu thực tế”, dùng constructor `new Base(source)` sẽ không đáp ứng khi source có subclass. Cần virtual `copy()` trong hierarchy, một registry/visitor, hoặc một policy cụ thể khác.

## 24. Polymorphic copying bằng method `copy()` được override

Một hierarchy có thể định nghĩa virtual copy contract:

~~~java
abstract class Message {
    abstract Message copy();
}

final class Email extends Message {
    private final String subject;

    Email(String subject) {
        this.subject = subject;
    }

    Email(Email source) {
        this(source.subject);
    }

    @Override
    Email copy() {
        return new Email(this);
    }
}
~~~

Đây là mã minh họa hợp lệ (không có main). Khi `Message message = new Email("Hello")` rồi gọi `message.copy()`, **runtime dispatch** chọn `Email.copy()`; kết quả có runtime class Email.

Điểm khác với copy constructor: virtual `copy()` có thể bảo toàn **kiểu dynamic** nếu từng subclass triển khai đúng. Nhưng cần kiểm thử tất cả subclasses, nhất là nếu chúng chứa mutable fields hoặc nghiệp vụ riêng.

**Covariant return** cho phép `Email.copy()` trả kiểu `Email` thay vì `Message` khi override phù hợp. Điều đó giúp code dùng concrete subtype không phải ép kiểu vô cớ.

## 25. Thực nghiệm 10 — phương thức copy đa hình giữ runtime type

Tạo tệp **`PolymorphicCopyDemo.java`**:

~~~java
abstract class Notice {
    private final String text;

    Notice(String text) {
        this.text = text;
    }

    Notice(Notice source) {
        this(source.text);
    }

    String text() {
        return text;
    }

    abstract Notice copy();
}

final class EmailNotice extends Notice {
    private final String subject;

    EmailNotice(String text, String subject) {
        super(text);
        this.subject = subject;
    }

    EmailNotice(EmailNotice source) {
        super(source);
        this.subject = source.subject;
    }

    @Override
    EmailNotice copy() {
        return new EmailNotice(this);
    }

    @Override
    public String toString() {
        return "Email:" + subject + "/" + text();
    }
}

final class SmsNotice extends Notice {
    SmsNotice(String text) {
        super(text);
    }

    SmsNotice(SmsNotice source) {
        super(source);
    }

    @Override
    SmsNotice copy() {
        return new SmsNotice(this);
    }

    @Override
    public String toString() {
        return "SMS:" + text();
    }
}

public class PolymorphicCopyDemo {
    static void inspect(Notice source) {
        Notice result = source.copy();
        System.out.println("copy=" + result);
        System.out.println("type="
                + result.getClass().getSimpleName());
        System.out.println("different=" + (source != result));
    }

    public static void main(String[] args) {
        inspect(new EmailNotice("Hello", "Welcome"));
        inspect(new SmsNotice("Short"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PolymorphicCopyDemo.java
java PolymorphicCopyDemo
~~~

**Stdout:**

~~~text
copy=Email:Welcome/Hello
type=EmailNotice
different=true
copy=SMS:Short
type=SmsNotice
different=true
~~~

`Notice.copy()` là abstract contract. Các concrete subclasses tự triển khai bằng copy constructors cụ thể, nhờ đó có thể giữ đúng runtime type.

**Không nên gọi `new Notice(source)`**, vì Notice abstract và constructor không thể phân nhánh đa hình theo subtype. Nếu một hierarchy quá phức tạp để mọi subclass duy trì copy semantics, đôi khi tốt hơn chuyển sang một immutable DTO hoặc một factory có danh sách subtype hữu hạn.

## 26. `copyOf` có thể nhận một interface thay vì concrete class

Một named copy factory có thể tạo snapshot từ dữ liệu mà không phụ thuộc concrete implementation. Ví dụ:

~~~java
interface ReadOnlyMetrics {
    int succeeded();
    int failed();
}

record MetricsSnapshot(int succeeded, int failed) {
    MetricsSnapshot {
        if (succeeded < 0 || failed < 0) {
            throw new IllegalArgumentException("count âm");
        }
    }

    static MetricsSnapshot snapshotOf(ReadOnlyMetrics source) {
        java.util.Objects.requireNonNull(source, "source");
        return new MetricsSnapshot(
                source.succeeded(), source.failed());
    }
}
~~~

Đây là những định nghĩa hợp lệ, không có main. Factory `snapshotOf(ReadOnlyMetrics)` tạo một **representation bất biến** dựa trên interface, bất kể nguồn là service, mutable bean hay adapter.

Điểm mạnh của cách này: caller không phải biết constructor của từng implementation; result có cấu trúc nhất quán và không giữ nguyên reference tới source.

**Giới hạn:** nếu source thay đổi đồng thời giữa lúc đọc `succeeded()` và `failed()`, snapshot có thể lấy hai giá trị ở **hai thời điểm khác nhau**. Copy factory không tự cấp một cơ chế atomic read; muốn một snapshot nhất quán theo thời điểm, cần synchronization/versioning hoặc API snapshot nguyên tử ở nguồn.

## 27. Thực nghiệm 11 — factory sao chép qua một interface

Tạo tệp **`InterfaceSnapshotDemo.java`**:

~~~java
interface MetricsView {
    int success();
    int failure();
}

final class MutableMetrics implements MetricsView {
    private int success;
    private int failure;

    void addSuccess() {
        success++;
    }

    void addFailure() {
        failure++;
    }

    @Override
    public int success() {
        return success;
    }

    @Override
    public int failure() {
        return failure;
    }
}

record MetricsSnapshot(int success, int failure) {
    MetricsSnapshot {
        if (success < 0 || failure < 0) {
            throw new IllegalArgumentException("negative metric");
        }
    }

    static MetricsSnapshot snapshotOf(MetricsView source) {
        java.util.Objects.requireNonNull(source, "source");
        return new MetricsSnapshot(
                source.success(), source.failure());
    }
}

public class InterfaceSnapshotDemo {
    public static void main(String[] args) {
        MutableMetrics source = new MutableMetrics();
        source.addSuccess();

        MetricsSnapshot first =
                MetricsSnapshot.snapshotOf(source);
        source.addFailure();
        MetricsSnapshot second =
                MetricsSnapshot.snapshotOf(source);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("source failure=" + source.failure());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InterfaceSnapshotDemo.java
java InterfaceSnapshotDemo
~~~

**Stdout:**

~~~text
first=MetricsSnapshot[success=1, failure=0]
second=MetricsSnapshot[success=1, failure=1]
source failure=1
~~~

Hai snapshots không phụ thuộc vào những lần cập nhật sau của MutableMetrics. Tuy vậy, **chúng không tự ghi lại lịch sử bên ngoài JVM**; đây chỉ là hai value objects độc lập được giữ trong bộ nhớ.

Factory từ interface cũng giúp viết test với fake implementation mà không phụ thuộc vào một concrete class khó khởi tạo.

## 28. Copy graph có chu trình: constructor một bước thường không đủ

Với object graph:

~~~text
Node A ----> Node B
   ^           |
   +-----------+

Node C ----> Shared Node
Node D ----> Shared Node
~~~

Nếu mỗi `Node(Node source)` lại tự gọi `new Node(child)` với mọi child, chu trình A↔B sẽ làm sao chép đệ quy vô hạn. Và nếu có hai đường tới **cùng một object con**, mỗi lần gặp đều tạo copy khác sẽ làm mất cấu trúc chia sẻ.

Giải pháp tổng quát là **ghi nhớ object gốc → object copy** trong một map theo **reference identity**:

~~~text
copy(source, map):
    nếu source == null: trả null
    nếu source đã có trong map: trả copy cũ
    tạo Node copy với dữ liệu cơ bản
    ghi map[source] = copy NGAY
    sao chép các liên kết con qua cùng map
    trả copy
~~~

Tại sao ghi map trước khi đệ quy? Vì khi gặp cạnh quay lại source, thuật toán phải tìm được bản copy đang được xây dựng, thay vì tạo mới vô hạn.

Một **named factory** `GraphCopies.deepCopyOf(root)` rất phù hợp vì nó có thể quản lý memo map và phạm vi toàn bộ graph, thay vì buộc mỗi copy constructor công khai tự xử lý chu trình một cách độc lập.

## 29. Thực nghiệm 12 — `deepCopyOf` bảo toàn chu trình và chia sẻ

Tạo tệp **`NamedGraphCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

final class GraphNode {
    private final String name;
    private final List<GraphNode> links = new ArrayList<>();

    GraphNode(String name) {
        this.name = name;
    }

    void connect(GraphNode other) {
        links.add(other);
    }

    GraphNode link(int index) {
        return links.get(index);
    }

    String name() {
        return name;
    }

    List<GraphNode> links() {
        return List.copyOf(links);
    }
}

final class GraphCopies {
    private GraphCopies() {
    }

    static GraphNode deepCopyOf(GraphNode root) {
        return copy(root, new IdentityHashMap<>());
    }

    private static GraphNode copy(
            GraphNode source, Map<GraphNode, GraphNode> memo) {
        if (source == null) {
            return null;
        }

        GraphNode existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        GraphNode result = new GraphNode(source.name());
        memo.put(source, result);
        for (GraphNode next : source.links()) {
            result.connect(copy(next, memo));
        }
        return result;
    }
}

public class NamedGraphCopyDemo {
    public static void main(String[] args) {
        GraphNode a = new GraphNode("A");
        GraphNode b = new GraphNode("B");

        a.connect(b);
        a.connect(b);
        b.connect(a);

        GraphNode copiedA = GraphCopies.deepCopyOf(a);
        GraphNode copiedB = copiedA.link(0);

        System.out.println("new root=" + (copiedA != a));
        System.out.println("new child=" + (copiedB != b));
        System.out.println("shared link="
                + (copiedA.link(0) == copiedA.link(1)));
        System.out.println("cycle="
                + (copiedB.link(0) == copiedA));
        System.out.println("original cycle="
                + (b.link(0) == a));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NamedGraphCopyDemo.java
java NamedGraphCopyDemo
~~~

**Stdout chính xác:**

~~~text
new root=true
new child=true
shared link=true
cycle=true
original cycle=true
~~~

Đây là deep copy theo **các GraphNode và links thuộc sở hữu của graph**. `String name` được chia sẻ an toàn do bất biến. `IdentityHashMap` tránh việc nhầm hai Node khác nhau có cùng tên hoặc cùng `equals`.

**Cần lưu ý:** một graph copy hoàn tất nhưng không bất biến: GraphNode có method `connect`. Công dụng ở đây là **cách ly object graph** giữa bản gốc và bản copy, không chứng minh mọi object trong đó immutable.

## 30. Chọn ranh giới deep copy, không cố clone toàn bộ thế giới

Một object có thể giữ:

- Dữ liệu miền: `List<Line>`, `Address`, `Configuration`.
- Immutable value: `String`, `Instant`, record chứa giá trị đơn giản.
- External dependency: `Logger`, `Repository`, `DataSource`.
- Live resource: `Socket`, `InputStream`, file handle, thread, lock.
- Entity reference: ID hoặc object đại diện cùng database row.

Không thể máy móc áp “copy tất cả references” cho toàn bộ những loại này. Một bản sao của domain document **không nên** tạo một kết nối database mới chỉ vì document có field repository. Một bản snapshot dữ liệu thường **chỉ copy state thuộc ownership của snapshot**, còn external dependencies không tham gia snapshot hoặc được quản lý riêng.

Hãy vẽ object graph và phân loại từng cạnh:

| Cạnh reference | Chính sách hợp lý |
| --- | --- |
| Root → immutable String | Chia sẻ an toàn |
| Root → mutable ArrayList thuộc sở hữu riêng | Copy container |
| Root → mutable Line thuộc sở hữu riêng | Copy element |
| Root → shared immutable configuration | Có thể chia sẻ |
| Root → socket/connection | Không deep-copy như data |
| Root → child cần giữ back-reference | Graph-aware copy với memo map |
| Root → database entity ngoài aggregate | Có thể chỉ giữ ID hoặc policy tách biệt |

**Deep copy có nghĩa theo phạm vi nghiệp vụ**, không phải “JVM có thuật toán để copy mọi loại object”.

## 31. `equals`, `hashCode` và identity sau copy

Một copy constructor **đảm bảo object mới** khi `new` hoàn thành bình thường, nên `copy != source` về reference. Nhưng `copy.equals(source)` phụ thuộc class:

- Với class không override `Object.equals`, hai objects khác nhau thường `equals` false (so identity).
- Với immutable value object override `equals/hashCode` theo state, bản copy có thể **equals true** dù `== false`.
- Với entity equality theo business ID, copy giữ ID có thể được coi bằng entity cũ; duplicateAsNew đổi ID thường không bằng cũ theo hợp đồng đó.
- `hashCode` **không** phải mã định danh unique của instance; hai objects có thể trùng hash dù không bằng nhau.

Nếu factory `copyOf` được phép trả lại cùng immutable object, `copy == source` có thể true. Không viết test mặc định mong `!=` nếu hợp đồng không nói fresh identity.

Đừng override `equals/hashCode` theo mutable fields rồi dùng objects làm keys của `HashMap` trong thời gian các fields thay đổi; copy constructor không tự giải quyết rủi ro key có hash biến đổi.

## 32. Ngoại lệ khi copy: giữ nguồn nguyên trạng

Một API copy an toàn nên cố gắng:

1. **Không mutate object nguồn** trong quá trình sao chép.
2. Kiểm tra nguồn null và ràng buộc nghiệp vụ.
3. Chuẩn bị dữ liệu mới trước khi công bố kết quả.
4. Nếu có lỗi, không trả một object bán hoàn thành qua API.
5. Không xóa hay giải phóng tài nguyên của nguồn trừ khi hợp đồng rõ là **move/transfer ownership** thay vì copy.

Sự khác biệt giữa **copy** và **move** rất quan trọng. Trong C++ tồn tại move constructors; trong Java Core không có constructor move ngôn ngữ tự sinh tương tự. Một factory tên `takeOwnershipOf` có thể được thiết kế để chuyển ownership nhưng **không nên gọi nó là copy** nếu sau đó caller không còn được sửa nguồn hay nguồn bị vô hiệu hóa.

Với mutable source bị thread khác sửa trong lúc copy, việc không mutate source từ method copy **chưa bảo đảm snapshot nhất quán**. Phần concurrency cần cơ chế riêng.

## 33. Thực nghiệm 13 — validate trước khi tạo bản sao có chính sách mới

Tạo tệp **`CopyFailureSafetyDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

record Shipment(String id, List<String> products) {
    Shipment {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        products = List.copyOf(
                Objects.requireNonNull(products, "products"));
        if (products.isEmpty()) {
            throw new IllegalArgumentException("empty shipment");
        }
    }

    static Shipment duplicateAsNew(Shipment old, String newId) {
        Objects.requireNonNull(old, "old");
        return new Shipment(newId, old.products());
    }
}

public class CopyFailureSafetyDemo {
    public static void main(String[] args) {
        Shipment source = new Shipment("S1", List.of("P1"));
        Shipment copied =
                Shipment.duplicateAsNew(source, "S2");

        System.out.println("source=" + source);
        System.out.println("copied=" + copied);

        try {
            Shipment.duplicateAsNew(source, "");
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }

        System.out.println("source after=" + source);
        System.out.println("copied after=" + copied);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CopyFailureSafetyDemo.java
java CopyFailureSafetyDemo
~~~

**Stdout:**

~~~text
source=Shipment[id=S1, products=[P1]]
copied=Shipment[id=S2, products=[P1]]
reject=id rỗng
source after=Shipment[id=S1, products=[P1]]
copied after=Shipment[id=S2, products=[P1]]
~~~

`duplicateAsNew` gọi canonical constructor của record, nơi kiểm tra ID và danh sách sản phẩm. Khi newId rỗng, method ném exception, nhưng **source và bản copy đã tạo trước đó không đổi**.

**Đây chưa phải ACID transaction:** nếu factory có gửi event, gọi repository hoặc cấp resource ngoài, những side effects đó cần quản lý riêng. Ví dụ dùng value objects thuần túy nên không có những tác dụng phụ ấy.

## 34. Concurrency: copy constructor không tự tạo snapshot nguyên tử

Giả sử `MutableMetrics` có hai counters:

~~~java
final class MutableMetrics {
    private int success;
    private int failure;

    void update() {
        success++;
        failure++;
    }

    int success() {
        return success;
    }

    int failure() {
        return failure;
    }
}
~~~

Đây là class minh họa hợp lệ. Nếu một thread đang `update()` và thread khác làm:

~~~java
MetricsSnapshot snap =
        new MetricsSnapshot(source.success(), source.failure());
~~~

đây là **lời gọi minh họa** trong ngữ cảnh có `source` và `MetricsSnapshot` phù hợp; copy thread có thể đọc một count trước và count còn lại sau thay đổi, khiến snapshot không tương ứng một thời điểm nhất quán.

Các phương án phụ thuộc yêu cầu:

- Dùng một **lock chung** cho cập nhật source và tạo snapshot.
- Cung cấp method `snapshot()` ở source có synchronization thích hợp.
- Quản lý state như một immutable aggregate rồi **atomic publication** toàn bộ reference.
- Dùng versioning/retry với kiểm tra nhất quán nếu thuật toán thật sự bảo đảm.
- Với dữ liệu bền vững, dùng transaction isolation phù hợp.

**Copy constructor tự thân không là synchronization primitive.** `final` fields ở kết quả giúp một số bảo đảm initialization safety nếu object được xây dựng đúng, nhưng không giải quyết race khi **đọc mutable source**.

## 35. Lưu trữ và entity identity: copy không phải INSERT tự động

Trong ORM/database, một object entity có thể chứa:

- ID gắn với bản ghi database.
- Version phục vụ optimistic locking.
- Collections/lazy proxies gắn persistence context.
- Trạng thái đã lưu/chưa lưu, audit metadata và quan hệ với entities khác.

Nếu copy nguyên fields rồi gọi repository.save, không thể suy ra hệ thống sẽ luôn tạo bản ghi mới: hành vi phụ thuộc ORM, mapping, ID state và repository. Những lỗi có thể là duplicate key, cập nhật nhầm bản ghi cũ hoặc copy các quan hệ không nên sao chép.

Do đó nên phân biệt:

**Snapshot:** ghi nhận trạng thái logic hiện tại, có thể giữ ID để biết nguồn; thường dùng DTO/record immutable.

**Duplicate as new:** tạo một thực thể miền khác, xác định ID mới, reset fields như status/version nếu nghiệp vụ yêu cầu, chọn các liên kết được phép copy.

**Copy for editing:** tạo một draft riêng để sửa, nhưng phải định nghĩa cách merge/commit về entity gốc và xử lý conflicts.

**Clone toàn entity:** dễ gây nhầm ngữ nghĩa và lifecycle nếu API không nói rõ. Không nên xem `Object.clone()` như cách tạo một bản ghi database mới.

## 36. Copy constructor và named factory có tác động gì tới kế thừa?

Một constructor:

~~~java
new Base(source)
~~~

luôn gọi constructor của `Base`; nó **không** virtual dispatch theo runtime subtype của source. Trong hierarchy mở, điều đó khiến copy có thể làm mất state của subclass.

Một factory:

~~~java
Base copyOf(Base source)
~~~

**có thể** viết logic chọn subclass bằng `instanceof` hoặc delegation qua `source.copy()`, nhưng Java **không tự thêm phép phân nhánh** ấy. Factory chỉ là method do bạn viết; nếu factory luôn `return new Base(source)`, nó có cùng hạn chế.

Nếu tập subtypes là hữu hạn, một sealed hierarchy và factory có thể quản lý rõ mọi trường hợp. Nếu hierarchy mở, virtual `copy()` được override ở từng subclass có thể phù hợp hơn; đồng thời cần đảm bảo subclasses duy trì hợp đồng copy khi thêm mutable state.

Không nhất thiết mọi application cần polymorphic copying. Đôi khi chuyển sang **DTO value** cụ thể đơn giản hơn và an toàn hơn tạo bản sao trọn một object hierarchy.

## 37. Copy-on-write và immutable collections

Một đối tượng immutable có thể chứa `List<String>` được chụp bằng `List.copyOf`:

~~~java
record Notebook(List<String> pages) {
    Notebook {
        pages = List.copyOf(pages);
    }

    Notebook withPage(String page) {
        var list = new java.util.ArrayList<>(pages);
        list.add(java.util.Objects.requireNonNull(page));
        return new Notebook(list);
    }
}
~~~

Đây là record Java 17 hợp lệ. `withPage` tạo **list ứng viên mới**, rồi tạo Notebook mới, không sửa Notebook cũ.

Đây là **copy-on-write ở mức ứng dụng**. Nó khác lớp `java.util.concurrent.CopyOnWriteArrayList`: collection kia hỗ trợ mutating operations đồng thời bằng cách copy backing array theo chính sách của nó, **không** tự bảo đảm một domain object chứa collection là immutable.

Với nhiều updates trên list lớn, mỗi lần copy có thể tốn O(n) và tạo nhiều objects. Nếu hiệu năng thành vấn đề, dùng mutable builder trong phạm vi đóng rồi tạo snapshot hoặc cân nhắc persistent data structures. Tối ưu nên dựa vào profile, không dùng shallow copy sai để đạt tốc độ.

## 38. Bẫy Java generics: hai copy constructors chỉ khác type argument

Java sử dụng **type erasure** cho nhiều generic types. Giả sử class cố khai báo:

~~~java
// Minh họa CỐ Ý KHÔNG BIÊN DỊCH:
class Catalog {
    Catalog(java.util.List<String> codes) {
    }

    Catalog(java.util.List<Integer> ids) {
    }
}
~~~

Hai constructors `Catalog(List<String>)` và `Catalog(List<Integer>)` có cùng erasure về `List`, nên tạo **name clash** theo quy tắc overload của Java. Không thể phân biệt chúng chỉ bằng generic type argument.

Named factories giúp biểu đạt hai nguồn đầu vào rõ:

~~~java
final class SafeCatalog {
    private final java.util.List<String> codes;

    private SafeCatalog(java.util.List<String> codes) {
        this.codes = java.util.List.copyOf(codes);
    }

    static SafeCatalog fromCodes(
            java.util.List<String> codes) {
        return new SafeCatalog(codes);
    }

    static SafeCatalog fromNumericIds(
            java.util.List<Integer> ids) {
        java.util.List<String> codes = ids.stream()
                .map(String::valueOf)
                .toList();
        return new SafeCatalog(codes);
    }
}
~~~

Đây là class hợp lệ vì factories **khác tên**. Cả hai có thể nhận `List<...>` sau erasure, nhưng method name khác nên không clash.

Cũng tránh dùng một `boolean isNumeric` chỉ để phân biệt chính sách chuyển đổi khi hai tên factory riêng sẽ dễ hiểu hơn.

## 39. Kiểm thử một copy contract

Kiểm thử cần phản ánh **lời hứa thực tế** của từng API, không dùng cùng tiêu chí cho mọi loại copy.

| Hợp đồng | Kiểm thử quan trọng |
| --- | --- |
| Fresh root object | `copy != source` |
| Value equivalence | Các trường logic phù hợp, có thể dùng `equals` nếu đúng hợp đồng |
| Immutable reuse allowed | Không mặc định kiểm tra `copy != source` |
| Mutable list isolation | Sửa list copy không ảnh hưởng list source |
| Mutable element isolation | Sửa phần tử ở copy không ảnh hưởng phần tử source |
| Defensive input | Sửa input của constructor sau đó không ảnh hưởng state riêng |
| Defensive output | Caller không sửa được nội bộ qua getter |
| Business ID policy | `copyPreservingId` giữ ID; `duplicateAsNew` dùng ID mới |
| Constructor validation | Copy và creation cùng enforce invariants |
| Polymorphic copy | Copy giữ đúng runtime subtype nếu hợp đồng có hứa |
| Cyclic graph | Không đệ quy vô hạn; sharing/cycles được giữ đúng |
| Exception safety | Source giữ nguyên sau copy thất bại |
| Resource policy | Không vô tình copy live connections/locks |
| Concurrency snapshot | Source và copy có cơ chế bảo vệ tính nhất quán phù hợp |

Đặc biệt, **test mutation isolation theo cả hai chiều**: sửa copy rồi kiểm tra source, sau đó sửa source rồi kiểm tra copy. Chỉ so nội dung ngay sau constructor chưa phát hiện alias mutable.

Nếu copy constructor dành cho `Date`, kiểm tra constructor copy lẫn getter trả Date; nếu dùng list có phần tử mutable, kiểm tra từng element. Nếu class mở cho kế thừa, phải test lớp con có thêm mutable field.

## 40. Những lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Sửa thế nào? |
| --- | --- | --- |
| Nghĩ `T second=first` là copy | Hai biến trỏ cùng object | Gọi constructor/factory thật nếu cần |
| Nghĩ Java tự sinh `T(T)` | Lỗi compile-time | Tự khai báo copy constructor |
| Copy constructor gán cùng mutable list | Hai roots chia sẻ mutable state | Defensive copy container |
| Chỉ copy list mà không copy mutable elements | Element mutation vẫn lan sang source | Copy elements hoặc dùng immutable elements |
| Chỉ copy khi nhận, getter trả mutable object | Caller sửa internal state | Defensive output/projection |
| Copy constructor không dùng chung validation | Dễ có objects sai invariant | Gọi `this(...)`/factory có validation |
| Dùng một factory tên `copyOf` cho hai chính sách ID | Caller không biết tạo snapshot hay entity mới | Tách tên `copyPreservingId`/`duplicateAsNew` |
| Cho rằng `copyOf` luôn fresh | Kiểm tra `==` sai với immutable reuse | Đọc contract, tách `freshCopyOf` |
| Copy root Base và nghĩ giữ subtype | Mất subclass state | Subclass copy constructor/virtual copy |
| Dùng `super.clone()` nghĩ constructor sẽ chạy | Validation/ID initializer không chạy | Chọn copy constructor nếu cần constructor logic |
| Có `final List` nghĩ dữ liệu đóng băng | List target có thể mutate | Immutable snapshot/deep copy |
| Deep copy graph không dùng memo map | Vòng lặp vô hạn hoặc mất sharing | Identity map gốc→bản sao |
| Copy `Socket`/`Repository` như một value | Sai lifecycle/resource semantics | Chỉ copy data theo ownership |
| Hai constructors chỉ khác `List<T>` | Name clash sau erasure | Named factories khác tên |
| Tự coi copy là snapshot nguyên tử | Source concurrent mutation có thể xen vào | Snapshot dưới lock/versioning |
| Clone entity với cùng ID rồi insert | Duplicate key/cập nhật nhầm | Chính sách ID, mapping và transaction rõ |
| Dùng hashCode làm mã định danh copy | Có thể collision/không bền | Business ID có hợp đồng riêng |
| Không thử mutation sau copy | Lỗi alias bị bỏ sót | Test trước–sau và hai chiều |

## 41. Quy trình thiết kế một API sao chép dễ dùng

**Bước 1 — định nghĩa kết quả.** Đây là fresh object, equivalent immutable value, snapshot hay duplicate entity mới? Có bắt buộc giữ runtime subtype không?

**Bước 2 — xác định ownership.** Vẽ references từ root tới mutable collections, elements, dependencies và resources. Chọn cạnh nào phải copy.

**Bước 3 — xác định invariant.** Tập trung validation ở constructor hoặc factory dùng chung; không có đường tạo bản sao bypass kiểm tra.

**Bước 4 — chọn hình thức API.** Ít chính sách và kiểu đích cố định: `new T(source)`. Nhiều chính sách hoặc chuyển kiểu: `copyOf`/`snapshotOf`/`duplicateAsNew`.

**Bước 5 — xử lý dữ liệu con.** Với immutable components, có thể chia sẻ. Với mutable components thuộc sở hữu riêng, copy container/element/graph đúng phạm vi.

**Bước 6 — bảo vệ đầu ra.** Không trả references mutable nội bộ qua getters nếu hợp đồng đòi isolation.

**Bước 7 — xem xét inheritance.** Copy constructor Base không tự preserve subtype; nếu cần, định nghĩa polymorphic copy.

**Bước 8 — viết test.** Kiểm tra identity, giá trị, mutations, failure, cycles, subclass state và ID policy.

**Bước 9 — xem xét concurrency và persistence.** Nếu snapshot phải nhất quán, bảo vệ đọc source; nếu duplicate là entity thật, kiểm tra transaction, unique IDs, relationships.

**Bước 10 — tài liệu hóa.** Ghi rõ có thể trả `this` không, deep-copy đến đâu, có được giữ external dependencies không, và những ngoại lệ có thể gặp.

## 42. Bài tập tự luyện

**Bài 1.** `Order second = first;` và `Order second = new Order(first);` khác gì về object identity nếu constructor là copy constructor chuẩn?

**Bài 2.** Vì sao Java không tự biên dịch `new Customer(old)` nếu class chỉ có constructor `Customer(String)`?

**Bài 3.** Với class chỉ có `int x,y`, copy constructor gọi `this(other.x,other.y)` có đủ tách state của hai objects không?

**Bài 4.** `Notebook(Notebook other) { this.tags = other.tags; }` có tạo root mới không? Tags có độc lập không?

**Bài 5.** `new ArrayList<>(other.lines)` sao chép được những gì nếu Line có setter `setQuantity`?

**Bài 6.** Để copy `List<String>` thuộc ownership, tại sao tạo một ArrayList mới thường đủ? Điều gì thay đổi nếu là `List<StringBuilder>`?

**Bài 7.** Nếu constructor nhận `Date` và copy input, nhưng getter trả chính Date nội bộ, object đã an toàn chưa?

**Bài 8.** Sao chép một entity có ID `D1` để làm **snapshot** khác gì sao chép nó để tạo một entity mới `D2`?

**Bài 9.** Named factory `copyOf` cho immutable record trả `source` có thể hợp lệ không? Khi nào phải tạo object mới?

**Bài 10.** Record có tự sinh constructor `RecordType(RecordType other)` không?

**Bài 11.** Một record chứa mutable list, copy constructor chỉ gọi canonical constructor, nhưng canonical constructor giữ nguyên list input. Có đạt deep immutability không?

**Bài 12.** `Base x = new Child(); new Base(x)` có giữ kiểu Child và fields Child không?

**Bài 13.** Với polymorphic `copy()`, tại sao cần subclass override và có thể trả kiểu con cụ thể hơn?

**Bài 14.** Nếu object graph A↔B có chu trình, vì sao một copy constructor gọi đệ quy `new Node(child)` dễ gặp lỗi?

**Bài 15.** Hai references tới cùng object con trong source nên tạo mấy bản sao con trong graph copy nếu cần giữ cấu trúc sharing?

**Bài 16.** Vì sao dùng `IdentityHashMap` hợp lý khi muốn phân biệt các graph nodes theo `==`?

**Bài 17.** Tại sao hai constructors `Catalog(List<String>)` và `Catalog(List<Integer>)` đụng tên sau type erasure? Named factories giải quyết thế nào?

**Bài 18.** Một source đang được thread khác cập nhật. Copy constructor đọc hai fields liên tiếp có bảo đảm snapshot nguyên tử không?

**Bài 19.** Nếu copy constructor không mutate source nhưng factory gọi repository rồi ném exception, toàn thao tác có chắc không side effect không?

**Bài 20.** Khi dùng copy constructor với final fields, có cần phá `final` để gán fields của object mới không?

**Bài 21.** Vì sao `new Base(source)` và `source.copy()` có hành vi khác nhau trên reference kiểu Base chứa subclass?

**Bài 22.** Có nên copy toàn bộ `Socket`, thread, lock, database connection vào bản sao domain object không? Vì sao?

**Bài 23.** Một factory nhận `List<MutableItem>` rồi dùng `List.copyOf`. Caller mutate element cũ. Bản copy có đổi giá trị logic không?

**Bài 24.** Nếu two immutable values có cùng dữ liệu, `==`, `equals` và `hashCode` có quan hệ thế nào?

### Đáp án và giải thích

1. Gán chỉ copy giá trị reference, `first==second`; constructor tạo root mới nên `first!=second` khi hoàn thành bình thường.
2. Java không tự tạo copy constructor; khai báo đang có không nhận Customer.
3. Đủ đối với hai primitive fields ấy, nếu class không có mutable state khác.
4. Root mới có, nhưng tags cùng trỏ mutable list nên không độc lập.
5. Copy list container, vẫn chia sẻ các Line objects, nên mutate quantity có thể xuất hiện ở cả hai.
6. String immutable, list mới đủ tách việc thêm/bớt; StringBuilder mutable nên cần copy từng element hoặc lưu String.
7. Chưa. Caller có thể nhận Date nội bộ rồi `setTime`; cần defensive copy ở getter.
8. Snapshot có thể giữ ID để truy vết nguồn; duplicateAsNew phải có chính sách ID mới/relationships/lifecycle.
9. Hợp lệ nếu hợp đồng cho phép tái sử dụng immutable object; nếu hứa fresh root phải dùng `new` hoặc logic cấp phát mới.
10. Không. Record sinh canonical constructor và các thành viên theo quy tắc record; copy constructor phải do bạn khai báo.
11. Không. Canonical constructor vẫn giữ mutable reference, nên cả hai object dễ alias.
12. Không. `new Base(x)` tạo Base, không copy tự động subclass fields.
13. Runtime dispatch chọn implementation phù hợp subclass; covariant return giúp trả subtype từ override.
14. Khi từ B gặp cạnh quay lại A, việc copy đệ quy không có memo sẽ tạo A mới vô hạn.
15. Một bản sao object con chung, được hai references trong graph copy cùng trỏ tới, nếu sharing là invariant.
16. Vì map so keys theo object identity, không nhầm hai nodes khác nhau có cùng giá trị/tên.
17. Cả hai constructors có erasure `List`; factories khác tên phân biệt được hai hành vi.
18. Không. Cần lock/versioning/snapshot nguyên tử của nguồn nếu contract yêu cầu.
19. Không. Side effect bên ngoài vẫn có thể tồn tại; cần transaction/compensation riêng.
20. Không. Fields được khởi tạo đúng trong constructor mới; final không cấm tạo instance khác.
21. Constructor chọn kiểu Base cố định, còn method instance `copy()` có thể virtual dispatch tới subtype.
22. Không nên tự động; resource có ownership/lifecycle ngoài phạm vi data copy.
23. Có thể. `List.copyOf` không deep-copy mutable elements.
24. `==` so identity; `equals` theo hợp đồng value có thể true; `equals true` đòi hashCode bằng nhau, nhưng hashCode trùng không chứng minh equals true.

## 43. Tổng kết kiến thức trọng tâm

- **Copy constructor** là constructor tự viết dạng `T(T source)`, tạo root object mới khi dùng `new` thành công. Java không tự sinh nó.
- **Named copy factory** là static method tự viết; các tên như `copyOf`, `snapshotOf`, `duplicateAsNew` giúp phân biệt mục đích.
- **Copy sâu/nông** không được quyết định bởi tên constructor/factory mà do **các references thực sự được sao chép**.
- Với mutable fields, phải xét copy container, copy elements và getter không lộ representation; với immutable values, sharing thường an toàn.
- Copy constructors/factories thuận lợi cho validation và các `final` fields vì dùng constructor bình thường.
- `new Base(source)` **không tự polymorphic**: muốn giữ runtime subtype phải có API/thiết kế riêng.
- Factory immutable `copyOf` **có thể trả cùng object** nếu identity mới không thuộc hợp đồng.
- Nếu graph có chu trình hoặc shared nodes, dùng memo theo identity để bảo toàn cấu trúc.
- Sao chép domain data không đồng nghĩa copy resources, tạo bản ghi database mới hay atomic snapshot trước concurrent mutation.

## 44. Tài liệu Java 17 để đối chiếu

- [Java Language Specification 17 — §8.8 Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): khai báo, overload và lời gọi constructor.
- [JLS 17 — §8.8.7.1 Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)` và `super(...)` trong constructors.
- [JLS 17 — §8.3.1.2 final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): quy tắc final fields.
- [JLS 17 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): canonical constructor, compact constructor và components.
- [JLS 17 — §4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): vì sao overload theo generic type arguments bị name clash.
- [JLS 17 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` và kiểu class được khởi tạo.
- [Java SE 17 — Object.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): so sánh cơ chế clone mặc định với copy theo constructor.
- [Java SE 17 — Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): ý nghĩa marker interface.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list, null policies và shallow element references.
- [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): tạo list container mới từ collection.
- [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): xác thực input copy.
- [Java SE 17 — IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): ánh xạ theo reference identity khi copy graph.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): ví dụ value object bất biến thay cho Date khi phù hợp.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view và khác biệt so với snapshot.

**Kết luận:** dùng `new T(source)` khi cần một bản sao cùng kiểu với constructor dễ hiểu; dùng `T.copyOf(source)`, `T.snapshotOf(source)` hoặc `T.duplicateAsNew(source,newId)` khi **ý định sao chép** cần được biểu đạt rõ. Trong cả hai trường hợp, hãy xác định identity, invariant, mutable ownership và khả năng kế thừa **trước khi viết code**. Một bản sao đúng không chỉ có dữ liệu ban đầu giống nguồn: nó phải duy trì chính xác **quan hệ chia sẻ và mức độc lập mà API đã cam kết**, kể cả sau khi người dùng thay đổi các object mutable.
