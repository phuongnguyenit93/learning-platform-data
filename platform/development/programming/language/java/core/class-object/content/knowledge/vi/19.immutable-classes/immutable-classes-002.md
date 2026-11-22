# Phân biệt lớp `final`, trường `final` và trạng thái bất biến trong Java

Trong Java, ba ý tưởng **lớp không cho kế thừa**, **trường không cho gán lại** và **đối tượng không thay đổi trạng thái** thường xuất hiện cùng nhau nhưng **không đồng nghĩa**.

- `final class` **cấm tạo subclass** từ class ấy.
- `final` đặt trên field **cấm gán lại field** sau khi được khởi tạo hợp lệ; với reference field, nó **không khóa object được tham chiếu**.
- **Immutability (tính bất biến)** là một **hợp đồng về trạng thái quan sát được**: sau khi một đối tượng được tạo hoàn chỉnh, các thao tác thông thường của ứng dụng không làm thay đổi giá trị logic mà đối tượng biểu diễn.

Ví dụ `final List<String> names` vẫn có thể gọi `names.add("An")` nếu reference đang trỏ tới một `ArrayList` mutable. Ngược lại, một đối tượng có thể bất biến về mặt quan sát dù class không khai báo `final` và implementation dùng bộ nhớ đệm nội bộ không làm thay đổi giá trị logic.

Bài thuộc **Java core - class-object**, phần **Lớp bất biến**. Chúng ta sẽ học chính xác luật của `final` theo Java 17, đối chiếu với immutable state, phân biệt **shallow** và **deep immutability**, sử dụng defensive copying, tạo API kiểu `withX`, đánh giá records và collections, tránh rò rỉ tham chiếu mutable, xem xét kế thừa, đồng thời hiểu giới hạn của `final` đối với concurrency. Các ví dụ đầy đủ đều dùng Java **17+**, có lệnh `javac`/`java`, stdout và lời giải.

## 1. Ba câu hỏi khác nhau

| Câu hỏi | Công cụ/khái niệm | Điều được bảo đảm |
| --- | --- | --- |
| Class này có được `extends` không? | `final class` | Không thể khai báo subclass hợp lệ của class ấy |
| Field này có được gán một giá trị/tham chiếu khác không? | `final` field | Không được gán lại sau phép gán hợp lệ theo các quy tắc definite assignment |
| Object này có thể đổi trạng thái logic sau khi tạo không? | Immutable design | Không có đường mutation hợp lệ làm thay đổi giá trị mà API cam kết |
| Method này có thể bị lớp con override không? | `final` method | Không được override method ấy |
| Biến local/parameter có thể được gán lại không? | `final` local/parameter | Không được gán lại biến sau khi được khởi tạo theo quy tắc ngôn ngữ |

Đừng kết luận từ tên keyword `final` rằng Java tự thực thi “deep freeze” trên cả đồ thị tham chiếu. Java **không có** cơ chế tự động đóng băng toàn bộ những object mà một field `final` trỏ tới.

Ví dụ chính xác: `private final List<String> items = new ArrayList<>();` khóa **ô chứa reference của field**, không khóa các phần tử, độ dài và nội dung của ArrayList.

## 2. `final class`: ngăn kế thừa, không ngăn mutation

Khai báo:

~~~java
final class Meter {
    private int count;

    void increase() {
        count++;
    }

    int count() {
        return count;
    }
}
~~~

Đây là một **class hợp lệ, mutable**. Không có subclass nào được phép `extends Meter`, nhưng `increase()` vẫn thay đổi `count`.

Mã sau cố ý **không biên dịch** nếu được thêm vào cùng chương trình:

~~~java
class ExtendedMeter extends Meter {
}
~~~

Compiler từ chối vì `Meter` là `final`. Đây là lỗi ở **quan hệ kế thừa**, không phải lỗi do muốn thay đổi field `count`.

**Kết luận:** `final class` là một công cụ hữu ích khi thiết kế immutable class vì ngăn subclass đưa ra hành vi phá hợp đồng, nhưng **một mình nó không tạo ra trạng thái bất biến**.

## 3. Chương trình hoàn chỉnh 1 — final class vẫn thay đổi trạng thái

Tạo tệp **`FinalClassMutableDemo.java`**:

~~~java
final class Counter {
    private int value;

    Counter(int initial) {
        value = initial;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class FinalClassMutableDemo {
    public static void main(String[] args) {
        Counter counter = new Counter(3);

        System.out.println("before=" + counter.value());
        counter.increment();
        System.out.println("after=" + counter.value());
        System.out.println("runtime="
                + counter.getClass().getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinalClassMutableDemo.java
java FinalClassMutableDemo
~~~

**Stdout chính xác:**

~~~text
before=3
after=4
runtime=Counter
~~~

Object vẫn đổi từ 3 sang 4. Việc runtime class tên `Counter` hay class được khai báo `final` không tác động đến phương thức `increment()`.

**Tại sao dùng final class cho immutable design?** Nếu subclass được phép mở rộng một value object, nó có thể thêm mutable fields hoặc override methods và làm người dùng khó dự đoán kết quả. Không cho subclass là một **chiến lược bảo vệ hợp đồng**, không thay thế kiểm soát fields và API.

## 4. `final` field: khóa phép gán, không khóa đối tượng đích

Một field `final` có thể là primitive hoặc reference.

~~~java
class Example {
    private final int id = 5;
    private final StringBuilder text =
            new StringBuilder("A");

    void append() {
        text.append("B");
    }

    String text() {
        return text.toString();
    }
}
~~~

Đây là class minh họa hợp lệ. Không thể viết `id = 7;` hay `text = new StringBuilder();` trong method thông thường, nhưng `text.append("B")` **hợp lệ**.

Với primitive field: `final int id` không đổi giá trị trong object thông qua các phép gán Java thông thường sau khởi tạo.

Với reference field: `final StringBuilder text` luôn trỏ tới **cùng StringBuilder** sau khởi tạo, nhưng object StringBuilder đó **vẫn có thể thay đổi nội dung**.

**Quy tắc nhớ:** khóa reference không đồng nghĩa khóa đối tượng được reference.

## 5. Chương trình hoàn chỉnh 2 — final reference đến mutable object

Tạo tệp **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Notebook {
    private final List<String> tags = new ArrayList<>();
    private final StringBuilder title =
            new StringBuilder("Java");

    void addTag(String tag) {
        tags.add(tag);
    }

    void renameByAppending(String extra) {
        title.append(extra);
    }

    String title() {
        return title.toString();
    }

    List<String> tags() {
        return List.copyOf(tags);
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Notebook notebook = new Notebook();

        System.out.println("before title=" + notebook.title());
        notebook.addTag("core");
        notebook.renameByAppending(" 17");

        System.out.println("after title=" + notebook.title());
        System.out.println("tags=" + notebook.tags());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Stdout:**

~~~text
before title=Java
after title=Java 17
tags=[core]
~~~

Hai fields `tags` và `title` đều là final references, nhưng object `Notebook` **mutable**. `List.copyOf(tags)` chỉ tạo một kết quả đọc không sửa được qua list trả về, không hề biến collection nội bộ thành trạng thái bất biến. Các phương thức của Notebook vẫn chủ động mutate object.

Đừng bỏ qua sự khác biệt giữa **không công bố setter cho field** và **không có bất kỳ mutation nào**. Nếu API có `addTag`, object thay đổi dù không có `setTags`.

## 6. `final` field khởi tạo đúng như thế nào?

Field `final` có thể được gán qua **field initializer** hoặc, nếu là **blank final instance field**, trong constructor hợp lệ theo luật *definite assignment*.

~~~java
final class ProductCode {
    private final String code;

    ProductCode(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code không hợp lệ");
        }
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Đây là class minh họa hợp lệ. Field `code` được gán ở constructor sau validation. Với mỗi constructor hoàn thành bình thường, luật definite assignment đòi blank final fields được gán hợp lệ.

Nếu class có nhiều constructor, có thể dùng **constructor chaining** để tập trung kiểm tra. Không được gán lại field đã được gán hợp lệ chỉ vì đang ở một phương thức riêng.

**Không có nghĩa** `final` khiến compiler chứng minh mọi invariant nghiệp vụ. Nó chỉ kiểm tra quy tắc gán; ví dụ field `final String code` vẫn có thể mang `null` nếu constructor cho phép.

## 7. Chương trình hoàn chỉnh 3 — final fields và constructor chaining

Tạo tệp **`FinalInitializationDemo.java`**:

~~~java
final class Ticket {
    private final String code;
    private final int priority;

    Ticket(String code) {
        this(code, 1);
    }

    Ticket(String code, int priority) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code trống");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("priority ngoài 1..5");
        }
        this.code = code;
        this.priority = priority;
    }

    String describe() {
        return code + ":" + priority;
    }
}

public class FinalInitializationDemo {
    public static void main(String[] args) {
        Ticket standard = new Ticket("A");
        Ticket urgent = new Ticket("B", 5);

        System.out.println("standard=" + standard.describe());
        System.out.println("urgent=" + urgent.describe());

        try {
            new Ticket("C", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FinalInitializationDemo.java
java FinalInitializationDemo
~~~

**Stdout:**

~~~text
standard=A:1
urgent=B:5
reject=priority ngoài 1..5
~~~

Các fields `code` và `priority` được gán một lần trong constructor có validation. Constructor một tham số gọi `this(code, 1)` để tái sử dụng một quy trình khởi tạo, không tạo thêm object.

Nếu constructor ném exception vì priority sai, lời gọi `new Ticket("C",0)` không trả object hợp lệ. Đây là validation do lập trình viên thiết kế, **không tự phát sinh chỉ nhờ từ khóa final**.

## 8. `final` local variable, parameter và method

Từ khóa `final` còn có nhiều vị trí khác:

~~~java
class LocalRules {
    void print(final StringBuilder builder) {
        final int length = builder.length();
        builder.append("!");
        System.out.println(length + ":" + builder);
    }

    final void fixedOperation() {
        System.out.println("fixed");
    }
}
~~~

Đây là class minh họa hợp lệ. Tham số `builder` không thể bị **gán lại** bằng một StringBuilder khác trong method, nhưng object mà nó tham chiếu vẫn có thể gọi `append`. Local `length` cũng không được gán lại sau khởi tạo.

`final void fixedOperation()` là **final method**: subclass không được override method đó. Nó **không khẳng định method không có side effects** hoặc object không mutable.

Những chỗ cần phân biệt:

- `final class`: cấm subclass.
- `final method`: cấm override.
- `final field`: cấm gán lại field theo quy tắc Java.
- `final local/parameter`: cấm gán lại biến.
- **Immutable object**: cam kết hành vi không làm thay đổi trạng thái logic.

Một method final có thể gọi code làm thay đổi fields mutable; ngược lại, method không final vẫn có thể hoàn toàn không gây mutation.

## 9. Định nghĩa immutable object ở mức API

Một đối tượng **bất biến theo hành vi quan sát được** nếu sau khi xây dựng hoàn chỉnh, trạng thái logic mà nó biểu diễn **không thể bị thay đổi** bằng những thao tác hợp lệ trong hợp đồng công khai của API.

Ví dụ một giá trị tọa độ `(x,y)`: object có thể cung cấp `x()`, `y()`, `translate(dx,dy)`, nhưng `translate` nên **trả object mới** thay vì sửa `x/y` của object cũ.

Bất biến có thể là:

- **Shallow immutability:** các trường trực tiếp không bị gán lại, nhưng có thể còn tham chiếu mutable reachable.
- **Deep immutability theo phạm vi:** toàn bộ trạng thái mutable thuộc sở hữu object được cách ly, và API không để caller thay đổi gián tiếp.
- **Logical/observational immutability:** implementation có thể dùng một **cache nội bộ** để tối ưu nhưng giá trị logic quan sát được không thay đổi. Cache cần thiết kế concurrency và công bố an toàn riêng.

Không có một keyword Java duy nhất mang nghĩa “object graph này immutable”. Đó là **kết quả của thiết kế class, dữ liệu đầu vào, cách lưu tham chiếu và API đầu ra**.

## 10. Vì sao mọi field final chưa đủ cho bất biến sâu?

Xét:

~~~java
final class UserGroup {
    private final java.util.List<String> members;

    UserGroup(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

Class final, field final và không có setter. Nhưng constructor **giữ trực tiếp** list do caller đưa vào, còn getter **trả lại chính list**. Caller có thể thay đổi cả qua input lẫn getter.

Đây là lỗi **representation exposure** (rò rỉ biểu diễn nội bộ). Field `final` chỉ cấm gán lại `members` sang một list khác; chính list vẫn có thể bị sửa.

Một giải pháp cho `List<String>` là tạo snapshot `List.copyOf(members)` trong constructor, vì `String` bất biến và list trả về không cho caller thêm/xóa. Với `List<MutableMember>`, chỉ copy list container vẫn chưa đủ; cần sao chép phần tử hoặc không công bố API mutation trên phần tử.

## 11. Chương trình hoàn chỉnh 4 — immutable `List<String>` snapshot

Tạo tệp **`ImmutableRosterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Roster {
    private final String teamName;
    private final List<String> members;

    Roster(String teamName, List<String> members) {
        if (teamName == null || teamName.isBlank()) {
            throw new IllegalArgumentException("teamName trống");
        }
        this.teamName = teamName;
        this.members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }

    String teamName() {
        return teamName;
    }

    List<String> members() {
        return members;
    }

    Roster withMember(String next) {
        Objects.requireNonNull(next, "next");
        List<String> updated = new ArrayList<>(members);
        updated.add(next);
        return new Roster(teamName, updated);
    }
}

public class ImmutableRosterDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Roster source = new Roster("Java", input);
        input.add("Bình");

        System.out.println("source=" + source.members());

        Roster updated = source.withMember("Chi");
        System.out.println("updated=" + updated.members());
        System.out.println("unchanged=" + source.members());
        System.out.println("team=" + updated.teamName());

        try {
            source.members().add("Dũng");
        } catch (UnsupportedOperationException ex) {
            System.out.println("readonly="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImmutableRosterDemo.java
java ImmutableRosterDemo
~~~

**Stdout:**

~~~text
source=[An]
updated=[An, Chi]
unchanged=[An]
team=Java
readonly=UnsupportedOperationException
~~~

### Tại sao Roster bất biến trong phạm vi đã định nghĩa?

1. Class `final`, fields `private final`, không có method sửa state.
2. Constructor **chụp snapshot** bằng `List.copyOf` nên `input.add("Bình")` sau đó không làm source đổi.
3. `List.copyOf` từ chối phần tử null và trả list không hỗ trợ các thao tác mutation qua interface.
4. Tên team và từng member là `String`, bản thân bất biến.
5. `withMember` tạo list ứng viên mới và **tạo một Roster khác**, không sửa source.

Các điều kiện là kết quả của thiết kế **kết hợp**, không chỉ do `final`. Một class final có `members.add(...)` trong method công khai sẽ không còn immutable.

## 12. Defensive copy phải tính cả chiều vào lẫn chiều ra

Đối với mutable input như `Date`, array hoặc `ArrayList`, có hai đường rò rỉ:

**Chiều vào:** constructor giữ reference đầu vào; caller vẫn còn quyền sửa object đầu vào sau khi constructor kết thúc.

**Chiều ra:** getter trả reference mutable nội bộ; caller sửa trực tiếp object đã được dùng làm field.

Mẫu bảo vệ:

~~~text
Input mutable
    |
    | constructor sao chép khi nhận
    v
Bản sở hữu riêng của object
    |
    | getter trả snapshot/copy hoặc immutable view an toàn
    v
Output không cho caller mutate state nội bộ
~~~

Nếu chỉ copy ở constructor mà getter trả chính mutable object nội bộ, người gọi vẫn sửa được sau đó. Nếu chỉ copy ở getter mà constructor vẫn giữ original mutable reference, caller sửa được qua reference đã có từ trước.

Với một kiểu con mutable, **copy nông outer list** không bảo vệ khỏi mutation của phần tử. Luôn phân tích ranh giới ownership theo object graph.

## 13. `final Date` vẫn là tham chiếu đến object mutable

`java.util.Date` có `setTime`, nên `private final Date createdAt` **không bảo đảm** thời điểm bên trong object không bị thay đổi. Nếu input và getter cùng trả/giữ reference ấy, caller có thể sửa trạng thái qua cả hai đường.

Trong ví dụ lớp sau, cả constructor và getter đều tạo `Date` mới:

~~~java
final class AuditStamp {
    private final java.util.Date createdAt;

    AuditStamp(java.util.Date source) {
        java.util.Objects.requireNonNull(source, "source");
        this.createdAt = new java.util.Date(source.getTime());
    }

    java.util.Date createdAt() {
        return new java.util.Date(createdAt.getTime());
    }
}
~~~

Đây là **khai báo lớp** chưa có `main`. Ví dụ phản chứng: khi truyền `new Date(1000L)` và sửa thời điểm trên biến input hoặc bản copy do getter trả, trạng thái của `AuditStamp` vẫn biểu diễn mốc 1000 milliseconds.

**Điểm cần rút ra của bài `final`:** modifier chỉ cấm gán lại field, không ngăn mutation trên referenced object; phải xem toàn bộ đường aliasing. Bài **“Sao chép phòng vệ đầu vào và đầu ra có thể thay đổi”** trình bày runnable Date demo, defensive copy policies và các kiểu mutable khác. Khi phù hợp, ưu tiên kiểu thời gian bất biến như `java.time.Instant` để giảm nhu cầu copy.

## 14. Collection không sửa được khác object graph bất biến

Cần phân biệt:

- **Unmodifiable list view**: ví dụ `Collections.unmodifiableList(backing)` chặn thao tác `add/remove` qua view, nhưng **phản ánh thay đổi** nếu code còn giữ và sửa `backing`.
- **Unmodifiable snapshot**: ví dụ `List.copyOf(backing)` tạo danh sách giá trị tại thời điểm gọi với hợp đồng không sửa được (với đầu vào phù hợp). Nó không nhất thiết luôn tạo identity container mới khi nguồn đã là unmodifiable.
- **Deeply immutable data**: các phần tử được chứa cũng là giá trị bất biến, hoặc trạng thái mutable được cô lập hoàn toàn.

Nếu `List.copyOf` nhận một `List<StringBuilder>`, caller **không thể add/remove** qua list kết quả, nhưng vẫn có thể gọi `list.get(0).append(...)`. Không có deep copy của StringBuilder.

`Map.copyOf` và `Set.copyOf` có ý nghĩa tương tự ở mức collection; key/value/element mutable vẫn cần chiến lược riêng. `Map.copyOf` cũng không cho các key/value null. Không đánh đồng “immutable wrapper” với “mọi object bên trong đều frozen”.

## 15. Chương trình hoàn chỉnh 6 — view sống và snapshot

Tạo tệp **`ListViewSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListViewSnapshotDemo {
    public static void main(String[] args) {
        List<String> backing = new ArrayList<>();
        backing.add("A");

        List<String> view =
                Collections.unmodifiableList(backing);
        List<String> snapshot = List.copyOf(backing);

        backing.add("B");
        System.out.println("backing=" + backing);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view add rejected");
        }

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add rejected");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ListViewSnapshotDemo.java
java ListViewSnapshotDemo
~~~

**Stdout:**

~~~text
backing=[A, B]
view=[A, B]
snapshot=[A]
view add rejected
snapshot add rejected
~~~

Cả hai danh sách trả ra đều không cho phép `add` qua API ấy, nhưng `view` vẫn **quan sát list backing** đang thay đổi, còn snapshot giữ các giá trị đã chụp trước khi thêm B.

Do vậy getter trả `Collections.unmodifiableList(internalList)` **không nhất thiết** là API immutable nếu chính object vẫn có method làm thay đổi internalList hoặc caller nào đó vẫn giữ backing list.

## 16. `final List<MutableElement>`: vấn đề shallow copy của phần tử

Giả sử `Order` chứa `List<Line>`, mà `Line` có method `setQuantity`. Constructor làm `List.copyOf(lines)` sẽ cấm thêm/xóa qua list nội bộ, nhưng **không tách các object Line** khỏi caller.

Điều này gây một đường thay đổi gián tiếp:

~~~text
Caller tạo Line L1, quantity=2
Caller đưa [L1] vào Order
Order lưu List.copyOf(...)
Caller vẫn giữ L1
Caller gọi L1.setQuantity(9)
Order giờ quan sát quantity=9
~~~

Nếu API hứa Order bất biến theo cả số lượng trên từng dòng, phải sao chép mỗi Line sang một immutable value, hoặc sao chép Line khi nhận **và** khi trả, không cấp quyền truy cập mutation tới Line nội bộ.

Một bản copy sâu có ý nghĩa nghiệp vụ phải mô tả phần nào của đồ thị đối tượng được sở hữu. Không phải mọi object ngoài là dependency dùng chung đều nên được copy; nhưng những dữ liệu mutable thuộc trạng thái logic của immutable aggregate cần được bảo vệ.

## 17. Chương trình hoàn chỉnh 7 — immutable order với snapshot phần tử

Tạo tệp **`ImmutableOrderDemo.java`**:

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
        this(other.sku, other.quantity);
    }

    String sku() {
        return sku;
    }

    int quantity() {
        return quantity;
    }

    void setQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        quantity = next;
    }
}

final class OrderSnapshot {
    private final List<MutableLine> lines;

    OrderSnapshot(List<MutableLine> input) {
        Objects.requireNonNull(input, "input");
        List<MutableLine> copied = new ArrayList<>();
        for (MutableLine line : input) {
            copied.add(new MutableLine(
                    Objects.requireNonNull(line, "line")));
        }
        lines = List.copyOf(copied);
    }

    List<MutableLine> lines() {
        List<MutableLine> copied = new ArrayList<>();
        for (MutableLine line : lines) {
            copied.add(new MutableLine(line));
        }
        return List.copyOf(copied);
    }

    int totalQuantity() {
        int total = 0;
        for (MutableLine line : lines) {
            total += line.quantity();
        }
        return total;
    }
}

public class ImmutableOrderDemo {
    public static void main(String[] args) {
        MutableLine inputLine = new MutableLine("P1", 2);
        List<MutableLine> input = new ArrayList<>();
        input.add(inputLine);

        OrderSnapshot order = new OrderSnapshot(input);
        inputLine.setQuantity(9);
        input.add(new MutableLine("P2", 5));

        System.out.println("order total="
                + order.totalQuantity());
        System.out.println("input size=" + input.size());

        MutableLine outputLine = order.lines().get(0);
        outputLine.setQuantity(100);

        System.out.println("output qty="
                + outputLine.quantity());
        System.out.println("order after output change="
                + order.totalQuantity());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ImmutableOrderDemo.java
java ImmutableOrderDemo
~~~

**Stdout chính xác:**

~~~text
order total=2
input size=2
output qty=100
order after output change=2
~~~

### Vì sao cần copy ở cả hai chiều?

`MutableLine` có `setQuantity`, nên một tham chiếu tới line nội bộ là quyền sửa số lượng. `OrderSnapshot` sao chép từng line trong constructor, để việc sửa `inputLine` không tác động tới object được lưu. Getter `lines()` lại trả danh sách chứa **các bản copy mới** của từng line; sửa `outputLine` cũng không tác động tới OrderSnapshot.

Cách này có thêm chi phí cấp phát và copy. Nếu được phép thay `MutableLine` bằng một `record Line(String sku, int quantity)` có validation và không giữ tham chiếu mutable, chỉ cần một list snapshot, thiết kế sẽ đơn giản hơn. Chọn kiểu dữ liệu bất biến từ đầu thường hiệu quả hơn bảo vệ liên tục một kiểu mutable.

## 18. Records Java 17: components final nhưng bất biến chỉ ở mức nông

Một record như:

~~~java
record UserTags(java.util.List<String> tags) {
}
~~~

được Java sinh các thành phần liên quan, lưu component `tags` trong một field private final và cung cấp accessor `tags()`. Nhưng **record mặc định không tự defensive-copy một `ArrayList` mà caller đưa vào**.

Do vậy bản thân cú pháp `record` **không đảm bảo bất biến sâu**. Nếu component là mutable reference, caller vẫn có thể thay đổi nội dung qua reference ban đầu hoặc accessor nếu implementation không bảo vệ.

Có thể viết **compact canonical constructor** trong record:

~~~java
record SafeTags(java.util.List<String> tags) {
    SafeTags {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Ở Java 17, phần tham số `tags` trong compact constructor có thể được chuẩn hóa/đưa qua defensive copy trước khi Java thực hiện phép gán ngầm vào record component field. Với `List<String>`, do String bất biến, một immutable list snapshot mang lại trạng thái bất biến về các phần tử.

Nếu record chứa `Date`, array hoặc `List<MutableLine>`, phải phân tích và copy riêng, thậm chí override accessor để tránh lộ mutable internal state.

## 19. Chương trình hoàn chỉnh 8 — record nông và record an toàn

Tạo tệp **`RecordImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record LooseTags(List<String> tags) {
}

record SafeTags(List<String> tags) {
    SafeTags {
        tags = List.copyOf(tags);
    }
}

public class RecordImmutabilityDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        LooseTags loose = new LooseTags(input);
        SafeTags safe = new SafeTags(input);

        input.add("B");

        System.out.println("loose=" + loose.tags());
        System.out.println("safe=" + safe.tags());

        try {
            safe.tags().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("safe rejects add");
        }
        System.out.println("safe after=" + safe.tags());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RecordImmutabilityDemo.java
java RecordImmutabilityDemo
~~~

**Stdout:**

~~~text
loose=[A, B]
safe=[A]
safe rejects add
safe after=[A]
~~~

Ở `LooseTags`, Java tạo final field `tags`, nhưng field giữ cùng mutable list ban đầu. Ở `SafeTags`, compact constructor sao chép list trước khi lưu, nên những thay đổi về sau của `input` không làm safe record đổi.

Records rất phù hợp cho các **value carriers** có dữ liệu bất biến; nhưng tính bất biến của **component types** vẫn là quyết định quan trọng hơn keyword `record`.

## 20. Khi mọi field final mà lớp vẫn mutable: mảng, builder, cache

Ba trường hợp dễ bỏ sót:

**Mảng:** `private final int[] scores` giữ cùng tham chiếu array, nhưng `scores[0] = ...` vẫn hợp lệ trong method. Constructor phải copy mảng khi nhận, getter cũng phải clone/copy khi trả nếu cần bất biến.

**Builder:** `private final StringBuilder title` không biến StringBuilder thành String. Đối với trạng thái bất biến, lưu `String` đã hoàn tất thường dễ hơn.

**Cache:** một đối tượng có thể giữ mutable cache nội bộ (ví dụ giá trị đã tính) mà người dùng **không thấy thay đổi giá trị logic**. Đây là *observational immutability*, nhưng thread-safety của cache phải có cơ chế đúng và cache không được làm hành vi công khai phụ thuộc vào thứ tự cập nhật theo cách trái hợp đồng.

Không nên suy ra “object có bất kỳ mutable field nội bộ nào thì không thể logically immutable”. Hãy đánh giá **trạng thái logic có thể quan sát** và các đường công bố reference. Nhưng với Java Core mới học, thiết kế toàn bộ state bất biến rõ ràng dễ kiểm tra hơn thiết kế cache lười phức tạp.

## 21. Chương trình hoàn chỉnh 9 — clone array trong constructor và getter

Tạo tệp **`ImmutableScoresDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

final class ScoreCard {
    private final int[] scores;

    ScoreCard(int[] input) {
        this.scores = Objects.requireNonNull(
                input, "input").clone();
    }

    int scoreAt(int index) {
        return scores[index];
    }

    int[] scores() {
        return scores.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(scores);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] input = {7, 8};
        ScoreCard card = new ScoreCard(input);

        input[0] = 99;
        int[] output = card.scores();
        output[1] = 100;

        System.out.println("card=" + card);
        System.out.println("first=" + card.scoreAt(0));
        System.out.println("output="
                + Arrays.toString(output));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableScoresDemo.java
java ImmutableScoresDemo
~~~

**Stdout:**

~~~text
card=[7, 8]
first=7
output=[7, 100]
~~~

Vì `int[]` chứa primitive values, `clone()` tạo array container mới và các phần tử độc lập. Đây là đủ cho mảng **một chiều primitive**. Với `StringBuilder[]`, clone chỉ tạo array mới nhưng vẫn chia sẻ các StringBuilder phần tử; với `int[][]`, clone mảng ngoài **không copy các hàng**.

Do vậy không nên dạy “dùng `array.clone()` luôn khiến class deeply immutable”. Cần xét component types và chiều sâu object graph.

## 22. Giá trị bất biến và phương thức `withX`

Một immutable object không có method `setX` làm thay đổi chính object. Khi cần một giá trị khác, có thể thiết kế `withX` tạo object mới.

Tạo tệp **`ImmutablePointDemo.java`**:

~~~java
import java.util.Objects;

public final class ImmutablePointDemo {
    private final int x;
    private final int y;
    private final String label;

    public ImmutablePointDemo(int x, int y, String label) {
        this.x = x;
        this.y = y;
        this.label = Objects.requireNonNull(label, "label");
    }

    public ImmutablePointDemo moveBy(int dx, int dy) {
        return new ImmutablePointDemo(x + dx, y + dy, label);
    }

    public ImmutablePointDemo withLabel(String next) {
        return new ImmutablePointDemo(x, y,
                Objects.requireNonNull(next, "next"));
    }

    @Override
    public String toString() {
        return label + "(" + x + "," + y + ")";
    }

    public static void main(String[] args) {
        ImmutablePointDemo source =
                new ImmutablePointDemo(2, 3, "A");
        ImmutablePointDemo moved = source.moveBy(5, -1);
        ImmutablePointDemo renamed = moved.withLabel("B");

        System.out.println("source=" + source);
        System.out.println("moved=" + moved);
        System.out.println("renamed=" + renamed);
        System.out.println("same object=" + (source == moved));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImmutablePointDemo.java
java ImmutablePointDemo
~~~

**Stdout:**

~~~text
source=A(2,3)
moved=A(7,2)
renamed=B(7,2)
same object=false
~~~

Mỗi operation tạo một instance mới được kiểm tra bởi constructor. Object gốc không thay đổi, nên caller có thể giữ nhiều phiên bản để so sánh, undo hoặc chia sẻ mà không phải lo hai nơi cùng sửa một value object.

**Đánh đổi:** tạo object mới có chi phí. Tuy nhiên, đối với objects nhỏ và dữ liệu immutable dùng làm value, lợi ích rõ ràng về API/test/concurrency thường đáng giá; tối ưu hiệu năng nên dựa trên profile thực tế, không mặc định chọn mutable trước.

## 23. Bất biến và equality/hashCode

Với value object, `equals/hashCode` thường dựa trên **giá trị logic**. Nếu các trường dùng để tính hash có thể thay đổi sau khi đối tượng được thêm vào `HashSet` hoặc dùng làm key `HashMap`, collection có thể không tìm được object sau mutation.

Immutable value object làm hợp đồng equality dễ giữ:

- Các trường tham gia `equals/hashCode` không thay đổi.
- Có thể cache hash một cách phù hợp nếu cần, nhưng phải tránh concurrency bug.
- Giá trị cùng nội dung có thể được xem là bằng nhau dù `==` false.
- Không cần lấy `System.identityHashCode()` làm định danh nghiệp vụ.

Những records chứa immutable components thường được sinh `equals/hashCode` hữu ích, nhưng **một record chứa array** cần chú ý: array equality mặc định dựa trên identity nếu được dùng như component theo phép so sánh được sinh; record không tự deep-compare array contents theo ý nghĩa nghiệp vụ.

Không suy từ `final class` rằng Java tự sinh `equals` theo giá trị: một final class bình thường vẫn kế thừa `Object.equals` nếu không override.

## 24. `static final`: hằng số tham chiếu chưa chắc bất biến

Từ khóa `static final` thường được dùng cho constants:

~~~java
static final int MAX_RETRIES = 3;
static final String DEFAULT_NAME = "guest";
~~~

Hai khai báo trên (đặt trong một class) là **constant variables** nếu initializer là constant expressions thích hợp.

Nhưng:

~~~java
static final java.util.List<String> USERS =
        new java.util.ArrayList<>();
~~~

chỉ là một **reference field static final**. Code có quyền truy cập `USERS` vẫn có thể `USERS.add("An")`. Từ khóa static không làm thay đổi ngữ nghĩa final ở mức mutable object được tham chiếu.

Đối với dữ liệu global, **mutable static shared state** có thể gây rủi ro concurrency và test interference. Nếu mục tiêu là tập hằng số không sửa được, dùng `List.of(...)`, `Set.of(...)`, `Map.of(...)` với elements/values bất biến thích hợp.

## 25. Chương trình hoàn chỉnh 10 — static final reference nhưng dữ liệu mutable

Tạo tệp **`StaticFinalCollectionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class AppState {
    static final List<String> EVENTS = new ArrayList<>();
    static final List<String> DEFAULT_ROLES =
            List.of("reader", "writer");

    private AppState() {
    }
}

public class StaticFinalCollectionDemo {
    public static void main(String[] args) {
        AppState.EVENTS.add("startup");
        AppState.EVENTS.add("login");

        System.out.println("events=" + AppState.EVENTS);
        System.out.println("roles=" + AppState.DEFAULT_ROLES);

        try {
            AppState.DEFAULT_ROLES.add("admin");
        } catch (UnsupportedOperationException ex) {
            System.out.println("roles cannot add");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticFinalCollectionDemo.java
java StaticFinalCollectionDemo
~~~

**Stdout:**

~~~text
events=[startup, login]
roles=[reader, writer]
roles cannot add
~~~

`EVENTS` là final reference nhưng list đích mutable. `DEFAULT_ROLES` cũng final reference, song object `List.of` tạo ra không hỗ trợ thay đổi cấu trúc. Vì các giá trị `String` là immutable, danh sách vai trò phù hợp làm dữ liệu bất biến.

Nếu dùng `List.of(new MutableProfile(...))`, list không cho thêm/xóa nhưng profile có thể đổi; lại cần xét immutability của phần tử. **`static final` không thay thế loại collection và hợp đồng object con**.

## 26. `final class` có thể kế thừa trạng thái mutable từ superclass

Một class được đánh dấu `final` vẫn có thể **extends một superclass khác**. `final` chỉ ngăn **người khác extends chính class đó**; nó không thay đổi code đã kế thừa.

Tạo tệp **`FinalSubclassStillMutableDemo.java`**:

~~~java
class MutableBase {
    private int value;

    MutableBase(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

final class FinishedCounter extends MutableBase {
    FinishedCounter(int initial) {
        super(initial);
    }
}

public class FinalSubclassStillMutableDemo {
    public static void main(String[] args) {
        FinishedCounter counter = new FinishedCounter(10);
        System.out.println("before=" + counter.value());
        counter.increment();
        System.out.println("after=" + counter.value());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinalSubclassStillMutableDemo.java
java FinalSubclassStillMutableDemo
~~~

**Stdout:**

~~~text
before=10
after=11
~~~

`FinishedCounter` không thể bị subclass thêm nữa, nhưng nó đã kế thừa method `increment()` từ `MutableBase`. Vì vậy nó vẫn mutable. Khi đánh giá một class có bất biến không, hãy xét **toàn bộ hành vi kế thừa**, không chỉ fields khai báo tại class cuối.

## 27. Có thể có class không final mà object bất biến không?

Có. Tính bất biến không được Java định nghĩa qua việc **bắt buộc** có keyword `final`. Một class không final nhưng không cung cấp API mutation và không rò rỉ state có thể tạo ra những instances bất biến.

Tuy nhiên, nếu subclass được phép mở rộng tùy ý, code sử dụng một tham chiếu base **không thể mặc định biết mọi subclass sẽ giữ cùng hợp đồng**. Subclass có thể thêm mutable state hoặc override method làm hành vi quan sát được phụ thuộc trạng thái mới.

Một số thiết kế cần subclassing nhưng vẫn giữ immutable behavior có thể:

- Đặt invariants quan trọng trong những methods `final`.
- Dùng `private` fields và defensive copies.
- Xác định hợp đồng superclass đủ mạnh cho subclasses.
- Dùng **sealed hierarchy** (Java 17) để giới hạn tập subclasses khi điều đó phù hợp, nhưng sealed cũng **không tự đảm bảo immutability**.
- Ưu tiên `final` value types khi không cần inheritance.

**Đừng đồng nhất “non-final class” với “mọi instance đều mutable”.** Đây là vấn đề hợp đồng kiểu và khả năng mở rộng chứ không phải một phép thử đơn giản trên từ khóa.

## 28. Concurrency: immutable giúp chia sẻ, final field không giải quyết mọi race

Immutable object được khởi tạo đầy đủ và công bố an toàn thường **dễ chia sẻ giữa các luồng**: nhiều threads chỉ đọc giá trị logic, không cạnh tranh cập nhật cùng state.

Java Memory Model còn có **ngữ nghĩa đặc biệt cho final fields**: nếu object được khởi tạo đúng cách (không để `this` thoát ra trong constructor), các thread khác có những bảo đảm initialization safety cho final fields theo JLS §17.5.

Nhưng đừng suy diễn quá mức:

- `final List<String> list` vẫn có thể trỏ tới **mutable ArrayList** và bị sửa đồng thời; final không làm `add` thread-safe.
- Một field `final` không làm các fields mutable khác trong class tự synchronized.
- Việc giữ một tham chiếu immutable object không khiến **một biến mutable giữ tham chiếu ấy** được cập nhật atomically theo ý định ứng dụng.
- Một collection of immutable elements vẫn có thể là collection **mutable** và cần synchronization nếu nhiều threads sửa collection đó.
- Lazy caches và các resource phụ thuộc concurrency vẫn phải có thiết kế visibility/atomicity riêng.
- “Immutable object” không đồng nghĩa “mọi phép toán trên toàn hệ thống đều không có race”.

Tránh công bố `this` từ constructor vào listener, static registry hoặc thread khác khi object chưa hoàn tất khởi tạo. Đây cũng là nguyên tắc quan trọng để bảo đảm ý nghĩa của final-field initialization.

## 29. Mutable builder + immutable snapshot: phân tách vai trò

Một pattern hữu ích là dùng **builder mutable trong giai đoạn xây dựng**, rồi công bố một **immutable snapshot**.

Ví dụ về quy trình:

~~~text
Nhận dữ liệu đầu vào
    |
    v
Builder có quyền thêm/sửa/xóa trong phạm vi tạo
    |
    v
Kiểm tra invariant, loại bỏ/chuẩn hóa dữ liệu sai
    |
    v
Tạo object immutable với defensive copies
    |
    v
Các API tiêu thụ chỉ đọc hoặc tạo snapshot mới
~~~

Đây là cách kết hợp **tiện khi xây dựng** và **an toàn khi sử dụng**. Nhưng phải đảm bảo builder và immutable result **không chia sẻ mutable references** ngoài ý muốn. Nếu `build()` chỉ truyền thẳng một `ArrayList` còn được builder nắm giữ, builder có thể sửa object đã “đóng gói”.

Không phải ứng dụng nào cũng cần builder. Với ít fields, constructor hoặc static factory có validation là đủ. Builder hữu ích khi có nhiều tham số tùy chọn và việc ghép dữ liệu cần nhiều bước.

## 30. Chương trình hoàn chỉnh 11 — builder không làm thay đổi snapshot đã tạo

Tạo tệp **`BuilderSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Palette(List<String> colors) {
    Palette {
        colors = List.copyOf(colors);
    }
}

final class PaletteBuilder {
    private final List<String> colors = new ArrayList<>();

    PaletteBuilder add(String color) {
        colors.add(Objects.requireNonNull(color, "color"));
        return this;
    }

    Palette build() {
        return new Palette(colors);
    }
}

public class BuilderSnapshotDemo {
    public static void main(String[] args) {
        PaletteBuilder builder = new PaletteBuilder();
        builder.add("red");

        Palette first = builder.build();
        builder.add("blue");
        Palette second = builder.build();

        System.out.println("first=" + first.colors());
        System.out.println("second=" + second.colors());
        System.out.println("different="
                + (first != second));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

**Stdout:**

~~~text
first=[red]
second=[red, blue]
different=true
~~~

Mỗi lần `build()` gọi canonical constructor của record `Palette`; constructor dùng `List.copyOf` để giữ snapshot không sửa được. Do đó sửa builder sau khi tạo first không ảnh hưởng first.

Nếu record chỉ viết `record Palette(List<String> colors) {}` mà không copy, hai objects có thể **chia sẻ mutable list** của builder, phá kỳ vọng snapshot.

## 31. Immutable object với business invariants

Bất biến có giá trị vì object **tự bảo vệ hợp đồng**: không có thao tác làm lệch trạng thái đã được kiểm tra. Chẳng hạn một `Money` value object có thể cần:

- Currency hợp lệ và không null.
- Số tiền ở đúng thang đo/đơn vị tính.
- Không chấp nhận giá trị không biểu diễn được.
- Operation `add` kiểm tra hai giá trị cùng currency trước khi trả instance mới.
- Các fields được khởi tạo một lần, không công bố mutable representation.
- `equals/hashCode` theo giá trị nếu đó là hợp đồng phù hợp.

Một class `final` với `final BigDecimal amount` chưa đủ nếu constructor không validate currency và không chuẩn hóa theo những luật nghiệp vụ đã công bố. **Immutability và validity là hai tiêu chí khác nhau**, dù immutable design giúp giữ validity sau khi object được tạo.

Tương tự, một immutable `OrderSummary` giữ `items` không sửa được nhưng vẫn có thể chứa dữ liệu sai do nhập vào. Cần validation, không chỉ dùng `final`.

## 32. Lỗi thường gặp và cách sửa

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| “`final class` có nghĩa mọi field không đổi.” | Final class chỉ cấm extends | Xét tất cả mutable fields/methods |
| “`final` field reference trỏ object immutable.” | Final chỉ cấm gán lại reference | Chọn immutable target/defensive copy |
| “Không có setter là immutable.” | Input/getter có thể rò rỉ mutable references | Defensive copy hai chiều |
| “Mọi field final nên class immutable.” | List, Date, array, builder có thể mutable | Xét trạng thái cả đồ thị sở hữu |
| “Unmodifiable view là snapshot bất biến.” | View phản ánh backing list thay đổi | Dùng snapshot đúng khi cần |
| “`List.copyOf` deep-copy phần tử.” | Copy nông ở mức collection | Dùng immutable elements/copy element |
| “`record` luôn deep immutable.” | Record chỉ tự khóa component references | Compact constructor và accessor an toàn |
| “`final int[] scores` không cho sửa phần tử.” | Array vẫn có mutation | Clone ở chiều nhận và trả |
| “Method final không có side effects.” | Final method chỉ cấm override | Thiết kế logic không mutation |
| “Static final list là hằng số dữ liệu.” | Reference final vẫn có mutable target | `List.of` và immutable values |
| “Final subclass chắc chắn immutable.” | Vẫn kế thừa mutable methods | Kiểm tra superclass |
| “Mọi non-final class luôn mutable.” | Không phải định nghĩa bắt buộc | Đánh giá hợp đồng quan sát được |
| “Immutable không cần validation.” | Bất biến khác tính hợp lệ | Validate constructor/factory |
| “Final fields tự làm ArrayList thread-safe.” | Thread safety thuộc mutable target | Immutable snapshot/synchronization |
| “Immutable object không thể có bất kỳ cache nội bộ.” | Logical immutability có thể có cache | Đảm bảo giá trị quan sát không đổi và concurrency |
| “`withX` nên sửa `this` rồi trả về.” | Trái hợp đồng immutable value | Trả instance mới được kiểm tra |

## 33. Quy trình thiết kế một class bất biến

1. **Xác định giá trị logic** mà object biểu diễn, bao gồm business invariants và những dữ liệu nào thuộc ownership.
2. Quyết định có cần subclassing không. Nếu không, cân nhắc **`final class`** hoặc record với components an toàn.
3. Đưa các fields biểu diễn trạng thái về `private` và chọn `final` khi phù hợp.
4. **Validate constructor parameters** trước khi tạo một object hoàn chỉnh.
5. **Copy đầu vào mutable** trước khi lưu; không giữ alias của collection, Date, array hoặc mutable element không được phép chia sẻ.
6. **Không công bố reference mutable nội bộ** qua getter, callback, listener hoặc method phụ.
7. Thay vì setters, cung cấp operations **trả value mới** như `withName`, `moveBy`, `withStatus`.
8. Với collection, phân biệt unmodifiable **view**, snapshot và sâu/nông. Dùng immutable elements khi có thể.
9. Với records, xem xét canonical/compact constructor và accessor nếu component chứa mutable reference.
10. Nếu dùng lazy cache, bảo đảm nó không đổi giá trị logic và được xử lý đồng thời đúng.
11. Không để `this` thoát sớm khỏi constructor.
12. Viết `equals/hashCode` phù hợp nghĩa value và bảo đảm các field tham gia không đổi.
13. **Test mutation isolation** từ cả đầu vào và các getter đầu ra.
14. Test các phương thức update không làm thay đổi object gốc.
15. Nếu có inheritance, kiểm tra toàn bộ inherited APIs có thể gây mutation.
16. Nếu có nhiều threads, phân tích an toàn công bố và các mutable dependencies riêng biệt.

## 34. Bài tập tự luyện

**Bài 1.** `final class Counter` có `int count` và `increment()`. Counter có bất biến không? Tại sao?

**Bài 2.** `private final ArrayList<String> names` có cấm `names.add("An")` không? Lệnh nào bị `final` chặn?

**Bài 3.** `final StringBuilder buffer` có làm `buffer.append("!")` không hợp lệ không?

**Bài 4.** Với blank final field `private final String id;`, constructor phải bảo đảm điều gì trên đường hoàn thành bình thường?

**Bài 5.** `final void save()` cấm điều gì? Nó có tự ngăn `save()` sửa trường mutable không?

**Bài 6.** Class final, tất cả fields final, constructor lưu trực tiếp `List<String>` mutable caller đưa vào. Bất biến sâu được bảo đảm chưa?

**Bài 7.** Tại sao chỉ dùng `Collections.unmodifiableList(backing)` chưa chắc tạo immutable snapshot?

**Bài 8.** `List.copyOf(List<MutableLine>)` có deep-copy `MutableLine` không? Nếu không, cần thêm bước gì?

**Bài 9.** `Date` là mutable. Một class lưu Date muốn immutable cần làm gì ở constructor và getter?

**Bài 10.** `final int[] values` có ngăn `values[0] = 5` không? Nếu trả chính array qua getter thì sao?

**Bài 11.** `record Box(List<String> values) {}` có tự defensive-copy List không? Có thể dùng compact constructor ra sao?

**Bài 12.** Vì sao `List.of("a")` an toàn cho các phần tử String, nhưng `List.of(new StringBuilder("a"))` không làm StringBuilder bất biến?

**Bài 13.** `static final List<String> shared = new ArrayList<>()` có bảo đảm dữ liệu không thay đổi không?

**Bài 14.** Một `final class Child extends MutableParent` kế thừa `increment()`. Child có mặc nhiên bất biến không?

**Bài 15.** `withLabel("new")` trong immutable value object nên trả gì và làm gì với object gốc?

**Bài 16.** Vì sao các kiểu immutable thường dễ làm key của HashMap hơn mutable objects với `hashCode()` phụ thuộc state?

**Bài 17.** Các field final trong object giúp gì theo Java Memory Model? Vì sao không đủ để làm mutable ArrayList thread-safe?

**Bài 18.** Một record chứa `List<MutableItem>`, constructor dùng `List.copyOf`. Caller vẫn giữ các MutableItem. Có thể sửa state logic của record không?

**Bài 19.** Nếu một immutable object có cache tính toán nội bộ được cập nhật lười, có nhất thiết vi phạm bất biến theo hành vi không? Điều kiện gì cần giữ?

**Bài 20.** Một builder tạo immutable snapshot bằng `new Snapshot(builder.list)` nhưng constructor lưu thẳng list. Sau `build`, builder tiếp tục thêm dữ liệu. Hậu quả gì?

### Đáp án và giải thích

1. Không; final class chỉ cấm subclass, method vẫn đổi `count`.
2. Không cấm add; final cấm gán lại field `names` sang một tham chiếu khác.
3. Không; `append` mutate object đích chứ không gán lại reference variable.
4. Blank final field phải được gán đúng theo definite assignment trước khi constructor hoàn thành bình thường.
5. Cấm subclass override method; method final vẫn có thể gây side effects.
6. Chưa. Caller có thể giữ reference list và sửa; cần defensive copy đầu vào.
7. Vì đó là view sống phản ánh thay đổi của list backing.
8. Không. Cần copy elements hoặc chuyển thành immutable values rồi bảo vệ những reference đi ra.
9. Copy Date khi nhận và copy khi trả, hoặc dùng một kiểu thời điểm immutable như Instant.
10. Không; phần tử mảng mutable. Trả mảng nội bộ cho caller có thể để caller sửa state; cần clone khi nhận và trả.
11. Không. Compact constructor có thể thực hiện `values = List.copyOf(values)` trước khi record lưu component.
12. List không cho add/remove nhưng object element mutable vẫn được gọi method sửa nội dung; String thì bất biến.
13. Không. Static final chỉ khóa reference, ArrayList vẫn mutable và còn có vấn đề concurrency.
14. Không; Child vẫn dùng được inherited mutator.
15. Tạo object mới với label mới, giữ nguyên trạng thái object gốc.
16. Các fields dùng cho equality/hash ổn định, không gây lỗi mất dấu key khi mutable state đổi.
17. Có bảo đảm initialization safety thích hợp khi xây dựng đúng; không tự bảo đảm atomicity/visibility cho các mutation sau này ở collection.
18. Có thể; List.copyOf giữ các element references, caller mutate các element đó thì giá trị logic có thể đổi.
19. Không nhất thiết, nếu cache không thay đổi kết quả logic quan sát được và được quản lý concurrency đúng.
20. Snapshot bị alias với list builder, thay đổi builder sau đó làm object kết quả đổi; constructor phải tạo snapshot riêng.

## 35. Tài liệu chính thức Java 17 để đối chiếu

- [JLS 17 §8.1.1.2 — final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): class final và giới hạn subclassing.
- [JLS 17 §8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): quy tắc final field.
- [JLS 17 §8.4.3.3 — final Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.3): final method và overriding.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final variable, constant variable.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): blank final field và definite assignment.
- [JLS 17 §17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields trong Java Memory Model.
- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): thành phần, compact constructor và đặc tính record.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot và giới hạn đối với elements.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view phản ánh backing collection.
- [Java SE 17 — List.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of(E...)): tạo danh sách không hỗ trợ sửa trực tiếp.
- [Java SE 17 — Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html): ví dụ reference type mutable.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): kiểu thời điểm bất biến.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): kiểm tra null.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): superclass của các record classes.

**Kết luận:** `final class` chỉ **ngăn kế thừa**, còn `final field` chỉ **ngăn gán lại field** sau khi khởi tạo đúng cách. **Trạng thái bất biến** đòi một hợp đồng sâu hơn: validation, không có mutators làm đổi giá trị logic, defensive copies ở mọi ranh giới sở hữu mutable, và không để caller sửa state qua collection, array hoặc object con. Records và `List.copyOf` rất hữu ích nhưng chỉ mang tính bất biến **nông** nếu các components hoặc elements vẫn mutable. Hãy thiết kế immutability từ ý nghĩa dữ liệu và đường tham chiếu, không đoán từ sự xuất hiện của từ khóa `final`.
