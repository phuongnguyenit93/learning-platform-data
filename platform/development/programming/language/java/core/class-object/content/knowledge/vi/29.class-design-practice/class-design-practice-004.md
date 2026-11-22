# Chọn lớp có thể thay đổi, lớp bất biến, record hoặc enum — Java 17

## 1. Mục tiêu của quyết định thiết kế

Khi biểu diễn một khái niệm nghiệp vụ bằng Java, ta không nên chọn `class`, `record` hay `enum` chỉ vì cú pháp nào ngắn. Câu hỏi quan trọng hơn là **đối tượng biểu diễn một danh tính có vòng đời và hành vi thay đổi, một giá trị ổn định, một tập giá trị hữu hạn hay một tổ hợp nhiều biến thể**.

Trong Java 17, các lựa chọn điển hình là:

1. **Lớp có thể thay đổi (mutable class)**: trạng thái bên trong instance có thể cập nhật trong vòng đời object, ví dụ giỏ hàng, bộ đếm, phiên làm việc, aggregate nghiệp vụ có thay đổi trạng thái.
2. **Lớp bất biến (immutable class)**: một khi khởi tạo hợp lệ thì trạng thái quan sát được không thay đổi; khi cần giá trị mới, tạo object mới, ví dụ tiền, khoảng ngày, tọa độ, configuration snapshot.
3. **`record`**: cú pháp ngắn cho một **data carrier** có tập components xác định, constructor/accessors/`equals`/`hashCode`/`toString` theo component state; bản thân record **không tự bảo đảm deep immutability**.
4. **`enum`**: mô tả một **tập hằng được định nghĩa trước** với identity singleton cho mỗi enum constant trong cùng class loader, ví dụ trạng thái hữu hạn, phương thức thanh toán có danh sách cố định, hướng la bàn.

Bài này tập trung vào **cách lựa chọn**, không chỉ liệt kê cú pháp. Sau bài học, bạn có thể trả lời được:

- Khi nào một mutable class là hợp lý và khi nào nó gây khó test/concurrency?
- Khi nào cần tự viết immutable class thay vì dùng record?
- Vì sao `record` chỉ tạo bất biến “nông” theo references, và cách thực hiện defensive copy?
- Vì sao `enum` phù hợp với tập **hữu hạn, ổn định**, không phải dữ liệu động từ database?
- Khi nào cần thêm static factory, builder hoặc sealed interface cùng record/enum variants?
- Identity equality (`==`), value equality (`equals`), hashing, API compatibility, serialization và ORM ảnh hưởng lựa chọn thế nào?
- Thiết kế resource-owning objects, mutable entities, immutable snapshots và status constants ra sao?

Các chương trình dưới đây là **Java 17 độc lập**: mỗi ví dụ có file name tương ứng public class, lệnh `javac --release 17` và kết quả stdout; các đoạn cố ý sai được ghi rõ **compile-negative** hoặc **snippet**.

## 2. Một cây quyết định dùng ngay

Bắt đầu từ câu hỏi **“đây có phải một tập ký hiệu cố định do source code định nghĩa không?”**

- **Có** → cân nhắc **`enum`**. Ví dụ `Direction.NORTH`, `OrderStatus.PAID`. Một enum constant không đại diện cho mỗi đơn hàng riêng biệt.
- **Không** → hỏi **“có cần giữ cùng danh tính object trong khi trạng thái thay đổi không?”**
  - **Có** → cân nhắc **mutable class** với invariant và ownership rõ. Ví dụ tài khoản có balance thay đổi, entity có ID riêng.
  - **Không** → hỏi **“đây là một cụm giá trị có schema đơn giản, components xác định và equality theo các components không?”**
    - **Có** → cân nhắc **`record`**, đồng thời kiểm tra các components có thật sự immutable/snapshot không.
    - **Không hoặc cần kiểm soát representation/field layout/inheritance/API khác** → cân nhắc **immutable class** viết thủ công.
- Nếu có **nhiều dạng giá trị khác cấu trúc** (ví dụ thanh toán thành công chứa receipt, thất bại chứa reason) → cân nhắc **sealed interface + final record/class variants**, thay vì ép tất cả thành một enum.

Đây là heuristic, không phải luật cưỡng chế. **Mutable class có thể là value-oriented**, immutable class có thể không override `equals`, record có thể chứa mutable fields, enum có thể tự khai báo state mutable (dù thường nên tránh). Hãy xét contract thực tế.

## 3. Bảng so sánh quan trọng

| Đặc tính | Mutable class | Immutable class | `record` | `enum` |
| --- | --- | --- | --- | --- |
| Trạng thái object thay đổi sau tạo | Có, theo API | Không nếu được thiết kế đúng | Component fields final; **referent có thể mutable** | Thông thường thiết kế immutable; ngôn ngữ không tự cấm mutable instance fields |
| Cú pháp định nghĩa | `class` | `final class` thường gặp | `record Name(...)` | `enum Name { ... }` |
| Constructors | Tùy ý hợp lệ | Thường validate + defensive copy | Canonical constructor và overload delegation | Enum constructors nội bộ, không `new` từ client |
| Accessors | Tự viết | Tự viết | Tự sinh tên `component()` | Tự viết nếu cần |
| `equals/hashCode/toString` | Thường tự định nghĩa hoặc kế thừa `Object` | Tự viết nếu cần value equality | Tự sinh theo component state, có thể override với điều kiện Java | `equals` theo identity của constants; `==` phù hợp |
| Kế thừa | Có nếu không final | Thường final để bảo toàn invariant | Implicitly final, extends `Record` | Không extends class khác; `Enum` base |
| Số lượng instances | Tùy `new`/factories | Tùy `new`/factories | Tùy `new`/factories | Hằng xác định trước, không thêm runtime constants |
| Phù hợp với | Lifecycle, entities, state machine holder | Money/value objects, snapshots | DTO/value tuple, API responses | Fixed options/states/categories |
| Rủi ro điển hình | Side effects, aliasing, concurrency | Defensive copy và boilerplate sai | Nhầm thành deep immutable, array equality | Dùng ordinal bền vững, mutable enum state, đổi constants gây API break |

**Lưu ý:** “immutable class” là **thiết kế ngữ nghĩa**, không phải Java keyword. Trong khi đó `record` và `enum` là các cấu trúc cú pháp của ngôn ngữ, nhưng không bảo đảm mọi nội dung referent bất biến.

## 4. Identity hay value?

Hai câu hỏi khác nhau:

- **Đây có phải *chính instance ấy* không?** Dùng identity (`==` trên references) hoặc một ID nghiệp vụ rõ ràng.
- **Hai instance có cùng giá trị không?** Dùng `equals` theo value semantics phù hợp.

Ví dụ:

- Hai đối tượng `Customer` có cùng tên vẫn có thể là **hai khách hàng khác nhau** (identity business khác).
- Hai đối tượng `Point(2,3)` thường nên được coi là **cùng giá trị tọa độ**, dù là hai instances.
- Hai enum constants `Status.ACTIVE` có identity cố định trong enum type nên `==` phù hợp.
- Hai mutable carts có cùng items ở một thời điểm chưa chắc là một cart nghiệp vụ.

**Không lựa chọn record chỉ vì “muốn class có dữ liệu”** nếu equality dựa trên ID chứ không dựa vào mọi components.

## 5. Mutable class: identity và thay đổi trạng thái

Một mutable object có state thay đổi qua các methods:

```java
final class Counter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
```

Ở đây `count` không final và có mutation operation `increment()`. Caller giữ một reference đến **cùng object** trong suốt quá trình tăng số đếm.

### Khi chọn mutable class

- State thể hiện tiến trình: `NEW → PROCESSING → DONE`.
- Object là aggregate/entity có danh tính cần duy trì.
- Có nhiều operations cập nhật state, phải kiểm tra invariants.
- Cần theo dõi giao dịch hoặc interactions với resource/lifecycle.
- Một framework có lifecycle/proxy/constructor constraints khiến mutable non-final class phù hợp hơn (kiểm tra đúng framework/version).

### Khi cần thận trọng

- Methods thay đổi object chung làm caller khác thấy side effects.
- Aliasing: nhiều references đến cùng instance.
- Concurrency: mutation cần synchronization/thread confinement/atomic operations.
- Hash-based collections có thể hỏng lookup nếu dùng mutable fields trong `equals/hashCode`.

## 6. Runnable: mutable object giữ identity trong lúc state đổi

Lưu **`MutableCounterDemo.java`**:

```java
final class Counter {
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

public class MutableCounterDemo {
    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter alias = first;

        first.increment();
        alias.increment();

        System.out.println(first.value());
        System.out.println(alias.value());
        System.out.println(first == alias);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableCounterDemo.java
java MutableCounterDemo
```

Stdout:

```text
3
3
true
```

Cả hai references trỏ cùng Counter. Đây là khác biệt cốt lõi giữa “cập nhật object” và “tạo một immutable value mới”.

## 7. Mutation nên được kiểm soát qua behavior, không phơi hết fields

Mutable class không nhất thiết có các setters cho mọi fields. Với object có business rules, API nên thể hiện operations hợp lệ:

```java
account.deposit(amount);
account.withdraw(amount);
```

Thay vì:

```java
account.setBalance(-1000);
account.setStatus("anything");
```

Lý do:
- Constructors kiểm tra initial invariant.
- Methods giữ invariant sau từng trạng thái hợp lệ.
- API giúp audit/log/test behavior.
- Người dùng không phải nhớ sửa nhiều fields cùng lúc.

### Lưu ý về concurrency

Một mutable class có kiểm tra `if (balance >= amount)` rồi `balance -= amount` **không tự thread-safe**. Với concurrency, phải thiết kế synchronization/locking/transactions tương ứng. `final class` chỉ ngăn subclassing, không thay atomicity.

## 8. Runnable: mutable progress tracker với identity ổn định

Để thấy vì sao **mutable class** phù hợp khi một object phải giữ identity trong suốt nhiều lần cập nhật, ta dùng một đối tượng theo dõi tiến độ công việc thay cho ví dụ tài khoản ngân hàng đã có bài thực hành riêng.

Tạo **`ProgressTrackerDemo.java`**:

~~~java
public class ProgressTrackerDemo {
    static final class ProgressTracker {
        private final String taskId;
        private final int totalSteps;
        private int completed;

        ProgressTracker(String taskId, int totalSteps) {
            if (taskId == null || taskId.isBlank()
                    || totalSteps <= 0) {
                throw new IllegalArgumentException(
                        "invalid task");
            }
            this.taskId = taskId.strip();
            this.totalSteps = totalSteps;
        }

        void advance(int steps) {
            if (steps <= 0) {
                throw new IllegalArgumentException(
                        "steps must be positive");
            }
            if (steps > totalSteps - completed) {
                throw new IllegalStateException(
                        "too many steps");
            }
            completed += steps;
        }

        String taskId() {
            return taskId;
        }

        int completed() {
            return completed;
        }

        int remaining() {
            return totalSteps - completed;
        }

        boolean finished() {
            return completed == totalSteps;
        }
    }

    public static void main(String[] args) {
        ProgressTracker work =
                new ProgressTracker(" JOB-7 ", 5);
        work.advance(2);
        work.advance(3);

        System.out.println("id=" + work.taskId());
        System.out.println("done=" + work.completed());
        System.out.println("remaining=" + work.remaining());
        System.out.println("finished=" + work.finished());

        try {
            work.advance(1);
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ProgressTrackerDemo.java
java ProgressTrackerDemo
~~~

Stdout dự kiến:

~~~text
id=JOB-7
done=5
remaining=0
finished=true
rejected=too many steps
~~~

`taskId` và `totalSteps` là dữ liệu cố định, còn `completed` thay đổi qua **behavior có guard**. Object giữ nguyên identity từ khi bắt đầu đến lúc kết thúc nhiệm vụ. Một `record ProgressSnapshot(String taskId, int completed, int totalSteps)` có thể lưu giá trị báo cáo tại một thời điểm, nhưng tự nó không cung cấp mutation in-place của cùng progress tracker.

**Ranh giới bài học:** ở đây ví dụ dùng để so sánh *mutable entity với immutable/record value*. Bài thiết kế thao tác nghiệp vụ đào sâu guard và invariant; bài tài khoản triển khai nạp/rút có logic số tiền riêng. Nếu nhiều threads cập nhật `completed`, bản demo cần thêm concurrency policy thay vì chỉ dựa vào `final` của hai fields cố định.

## 9. Immutable class: một giá trị không đổi sau khi tạo

Một immutable class được thiết kế để **trạng thái quan sát được của instance không thay đổi** từ sau khi constructor/factory hoàn thành.

Các nguyên tắc thường gặp:
- Class `final` hoặc được thiết kế chống subclass làm thay đổi contract.
- Fields cần thiết `private final`.
- Validate invariant khi xây dựng.
- Không có methods mutate object.
- Dữ liệu mutable đầu vào được **defensive copy** nếu cần.
- Accessors không trả ra references cho phép caller sửa representation bên trong.
- Không publish `this` trước khi constructor hoàn tất.
- Nếu component chứa object khác, đảm bảo cả **transitive state** không bị sửa ngoài ý muốn.

**`final` không đồng nghĩa immutable.** Field `final List<String> values` có thể vẫn trỏ một mutable ArrayList. `final class` có thể chứa mutable fields.

### Khi chọn immutable class thủ công

- Representation cần hidden fields không trùng API components.
- Constructor/factory logic phức tạp.
- Cần API accessor đặt tên khác convention record.
- Muốn kiểm soát cụ thể equality/hashCode/toString hoặc exposure.
- Cần bảo toàn tương thích với một class API đã có thay vì thay sang record.
- Cần implementation details riêng, caches/derived attributes có kiểm soát và không vi phạm semantic immutability.

## 10. Runnable: immutable `Range` class

Lưu **`ImmutableRangeDemo.java`**:

```java
import java.util.Objects;

final class Range {
    private final int start;
    private final int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }

    int length() {
        return end - start;
    }

    Range shift(int delta) {
        return new Range(
                Math.addExact(start, delta),
                Math.addExact(end, delta));
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Range range)) return false;
        return start == range.start && end == range.end;
    }

    @Override
    public int hashCode() {
        return Objects.hash(start, end);
    }

    @Override
    public String toString() {
        return "Range[" + start + "," + end + "]";
    }
}

public class ImmutableRangeDemo {
    public static void main(String[] args) {
        Range a = new Range(2, 7);
        Range b = a.shift(3);
        Range same = new Range(2, 7);

        System.out.println(a);
        System.out.println(b);
        System.out.println(a.equals(same));
        System.out.println(a == same);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableRangeDemo.java
java ImmutableRangeDemo
```

Stdout:

```text
Range[2,7]
Range[5,10]
true
false
```

Method `shift` **trả instance mới**, không thay đổi `a`. Value equality được viết thủ công, thích hợp cho một value object với hai tọa độ.

**Để ý overflow:** `length()` dùng int subtraction; nếu range có thể trải toàn miền int, hãy dùng long để tính độ dài. Ví dụ này tập trung vào immutability và equality, không phải kiểu dữ liệu khoảng cực lớn.

## 11. Record: cú pháp dữ liệu gọn nhưng không phải “magic immutable”

Một record declaration Java 17:

```java
record Point(int x, int y) {
}
```

trình biên dịch cung cấp:
- Private final **component fields** `x` và `y`.
- Public accessors `x()`, `y()`.
- Canonical constructor tương ứng `Point(int,int)`.
- `equals`, `hashCode`, `toString` theo components, trừ khi override hợp lệ.
- Kế thừa từ `java.lang.Record`; record là implicitly final.

Dùng:

```java
Point a = new Point(2, 3);
Point b = new Point(2, 3);
```

`a.equals(b)` true mặc định; `a == b` false vì hai lần `new` tạo hai instances khác nhau.

### Record là data carrier

Header `(int x, int y)` công bố dữ liệu nền tảng để cấu thành record. Nó không phải cách che mọi implementation detail giống immutable class có private representation và API tùy ý.

Record có thể có:
- Instance methods.
- Static fields/static methods.
- Validation và normalization trong canonical constructor.
- Additional constructors phải delegate đến canonical qua `this(...)`.

Record không được khai báo additional non-static instance fields hoặc instance initializer blocks. Nó không có superclass tùy chọn và không được subclass.

## 12. Runnable: record mang value semantics

Lưu **`RecordPointDemo.java`**:

```java
record Point(int x, int y) {
    int squaredDistance() {
        return x * x + y * y;
    }
}

public class RecordPointDemo {
    public static void main(String[] args) {
        Point a = new Point(3, 4);
        Point b = new Point(3, 4);

        System.out.println(a);
        System.out.println(a.x());
        System.out.println(a.y());
        System.out.println(a.squaredDistance());
        System.out.println(a.equals(b));
        System.out.println(a == b);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordPointDemo.java
java RecordPointDemo
```

Stdout:

```text
Point[x=3, y=4]
3
4
25
true
false
```

Thêm instance method tính toán là hoàn toàn bình thường với record. Lý do chọn record là **x/y là representation và equality theo các components là hợp lý**.

## 13. Record không tự deep immutable

Xét:

```java
record Team(java.util.List<String> members) {
}
```

Field `members` là final: không thể gán lại sau khi constructor hoàn tất. Nhưng nếu caller đưa vào một `ArrayList` mutable, caller có thể sửa list sau khi xây record; `team.members()` mặc định trả **cùng list reference**.

Điều này dẫn tới:
- Value state quan sát qua accessor thay đổi dù record object không gán lại field.
- `toString`/`equals`/`hashCode` có thể thay đổi theo list contents.
- HashMap/HashSet dùng record làm key có nguy cơ lookup bất ổn nếu component list bị mutate.
- Một thread có thể thấy mutation của referent mà không có concurrency discipline.

**Điều record bảo đảm:** shallow component field finality. **Điều nó không bảo đảm:** deep immutability của toàn bộ object graph.

## 14. Runnable: record chứa mutable list bị thay đổi từ bên ngoài

Lưu **`MutableRecordComponentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
}

public class MutableRecordComponentDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team(source);
        source.add("Binh");

        System.out.println(team.members());
        System.out.println(team.members() == source);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableRecordComponentDemo.java
java MutableRecordComponentDemo
```

Stdout:

```text
[An, Binh]
true
```

Dù `Team` là record, source và team accessor vẫn dùng chung mutable ArrayList. Không chọn record với giả định “mọi thứ tự động an toàn” khi thiết kế immutable DTO/snapshot.

## 15. Defensive copy trong compact canonical constructor

Java 17 hỗ trợ compact constructor:

```java
record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
```

Giải thích:
- `members` trong compact body là implicit constructor parameter.
- `List.copyOf(members)` tạo hoặc dùng lại một **unmodifiable list** theo API, và từ chối null elements.
- Sau compact body, compiler gán component field từ parameter `members`.
- Caller sửa list nguồn sau khi tạo Team không làm list snapshot thay đổi.
- Accessor mặc định `members()` trả list unmodifiable, nên caller không add/remove được.
- **Nhưng** nếu list chứa **mutable elements**, `List.copyOf` không deep-clone elements.

**Caveat:** unmodifiable **không đồng nghĩa** “mọi objects reachable từ list bất biến”. Với `List<String>`, String immutable nên đây là value-oriented representation tốt. Với `List<MutableItem>`, còn phải xem elements có thể mutate không.

## 16. Runnable: record compact copy với List<String>

Lưu **`RecordDefensiveListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class RecordDefensiveListDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team(source);
        source.add("Binh");

        System.out.println(team.members());
        System.out.println(source);

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordDefensiveListDemo.java
java RecordDefensiveListDemo
```

Stdout:

```text
[An]
[An, Binh]
unmodifiable
```

Mẫu này thích hợp cho một record **chứa danh sách Strings**, vì cả collection structure và elements được quan sát là immutable trong ví dụ.

## 17. Unmodifiable view khác snapshot copy

Hai API:

```java
List<String> view =
        Collections.unmodifiableList(source);

List<String> snapshot = List.copyOf(source);
```

**Không giống nhau**:
- `Collections.unmodifiableList(source)` là **view không cho sửa thông qua view**, nhưng vẫn phản ánh các thay đổi hợp lệ thực hiện trên `source`.
- `List.copyOf(source)` trả unmodifiable list với elements snapshot ở thời điểm tạo (shallow).
- `List.copyOf` có thể trả lại một instance phù hợp đã unmodifiable; không bảo đảm một object list mới luôn được cấp phát.
- `List.copyOf` từ chối null elements; cân nhắc semantics nếu input có null.

### Runnable

Lưu **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> snapshot =
                List.copyOf(source);

        source.add("B");

        System.out.println(view);
        System.out.println(snapshot);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

Stdout:

```text
[A, B]
[A]
```

Nếu value object phải không đổi, **view** thường không đủ khi caller còn giữ mutable source list.

## 18. Record với array: một bẫy khác list

`record Packet(byte[] data)` có final reference tới array, **nhưng array mutable**:
- Caller thay `data[0]` sau constructor → record quan sát nội dung mới.
- Accessor mặc định `data()` trả array reference → caller sửa qua accessor.
- Record-generated `equals/hashCode` cho array component dựa trên array **reference equality/hashCode**, **không** so từng phần tử giống `Arrays.equals`.

Defensive clone:

```java
record Packet(byte[] data) {
    Packet {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

giải quyết aliasing ở đầu vào/đầu ra nhưng **không tự làm component equality theo nội dung array**. Hai Packets clone từ hai arrays có cùng bytes thường **không equal** theo default record equals.

**Hướng thiết kế:** nếu value equality theo byte contents là quan trọng, cân nhắc custom immutable wrapper với `Arrays.equals/hashCode` nhất quán, hoặc representation khác với API có semantics rõ. Đừng chọn record chỉ vì header ngắn mà bỏ qua array behavior.

## 19. Runnable: defensive clone vẫn không biến arrays thành value-equal

Lưu **`RecordArrayDemo.java`**:

```java
import java.util.Arrays;

record Packet(int[] numbers) {
    Packet {
        numbers = numbers.clone();
    }

    @Override
    public int[] numbers() {
        return numbers.clone();
    }
}

public class RecordArrayDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Packet first = new Packet(source);
        Packet second = new Packet(new int[] {1, 2});

        source[0] = 9;
        int[] leakedCopy = first.numbers();
        leakedCopy[1] = 8;

        System.out.println(Arrays.toString(first.numbers()));
        System.out.println(first.equals(second));
        System.out.println(Arrays.equals(
                first.numbers(), second.numbers()));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordArrayDemo.java
java RecordArrayDemo
```

Stdout:

```text
[1, 2]
false
true
```

First và second chứa **hai arrays khác references** sau cloning. Generated equals của record không deep-compare arrays. Đây là lý do **record + array** cần được review kỹ cả immutability lẫn equality.

## 20. Immutable class thủ công khi representation cần đặc biệt

Một immutable object có thể muốn:
- Ẩn một primitive array.
- Expose một phương thức `bytes()` trả clone.
- So nội dung arrays bằng `Arrays.equals`.
- Cấm subclass qua `final`.
- Cấu trúc cache/hash riêng (nếu bảo toàn semantics).
- Không công bố array như một record component trong API.

Ví dụ:

```java
final class BytesValue {
    private final byte[] bytes;

    BytesValue(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    byte[] toArray() {
        return bytes.clone();
    }

    // equals/hashCode dùng Arrays.equals/hashCode
}
```

Đây là **snippet thiết kế**, chưa phải full class vì phần equals/hashCode được lược để minh họa lựa chọn representation.

### Khi record vẫn dùng được

Record có thể override equals/hashCode để xử lý arrays phù hợp, nhưng điều đó tăng boilerplate và cần kiểm tra quy tắc record equality, consistency, defensive copies, toString. Khi representation quá đặc biệt, **immutable class tự viết** thường truyền tải contract rõ hơn.

## 21. Runnable: immutable array value class

Lưu **`ImmutableBytesDemo.java`**:

```java
import java.util.Arrays;

final class BytesValue {
    private final byte[] bytes;

    BytesValue(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    byte[] toArray() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof BytesValue that)) return false;
        return Arrays.equals(bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return Arrays.toString(bytes);
    }
}

public class ImmutableBytesDemo {
    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        BytesValue a = new BytesValue(source);
        BytesValue b = new BytesValue(new byte[] {1, 2, 3});

        source[0] = 9;
        byte[] snapshot = a.toArray();
        snapshot[1] = 8;

        System.out.println(a);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableBytesDemo.java
java ImmutableBytesDemo
```

Stdout:

```text
[1, 2, 3]
true
true
```

Một immutable class thủ công xử lý cả **defensive copies** và **content equality** của arrays. Với record mặc định, array component equality không được so theo phần tử.

## 22. Enum: tập hằng cố định do chương trình xác định

Enum thích hợp khi mọi giá trị hợp lệ được code định nghĩa:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Client:

```java
Priority priority = Priority.HIGH;
```

Các enum constants là **instances được định nghĩa trước**, không dùng `new Priority()` bên ngoài enum.

Các APIs quen thuộc:
- `Priority.values()` trả array các constants theo thứ tự khai báo.
- `Priority.valueOf("HIGH")` lấy enum constant theo tên chính xác (ném `IllegalArgumentException` nếu sai).
- `priority.name()` trả declared name.
- `priority.ordinal()` trả vị trí khai báo tính từ 0 — **không dùng làm mã dữ liệu bền vững**.
- `EnumSet` và `EnumMap` tận dụng enum types cho các tập/map chuyên biệt.

### Khi enum phù hợp

- Tập giá trị nhỏ, hữu hạn, không thêm tùy ý lúc runtime.
- Mỗi giá trị có nghĩa ổn định trong source code.
- Có thể thêm behavior riêng, display label hoặc stable code.
- Caller cần exhaustiveness qua `switch` trên enum (Java 17 hỗ trợ enum switch).

### Khi enum không phù hợp

- Danh sách countries/products/users cập nhật động từ database.
- Mỗi instance cần payload khác nhau theo từng request.
- Cùng một status enum constant không thể lưu khác mutable per-order state một cách độc lập.

## 23. Runnable: enum constants và switch

Lưu **`EnumPriorityDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumPriorityDemo {
    static String handle(Priority priority) {
        return switch (priority) {
            case LOW -> "later";
            case MEDIUM -> "normal";
            case HIGH -> "now";
        };
    }

    public static void main(String[] args) {
        Priority value = Priority.HIGH;

        System.out.println(handle(value));
        System.out.println(value.name());
        System.out.println(value == Priority.HIGH);
        System.out.println(Priority.values().length);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumPriorityDemo.java
java EnumPriorityDemo
```

Stdout:

```text
now
HIGH
true
3
```

`switch` expression trên enum là tính năng chuẩn của Java 17, không cần preview. Đây là lựa chọn đơn giản cho một tập categories cố định.

## 24. Enum không tự bất biến nếu bạn khai báo mutable fields

Hầu hết enum nên được thiết kế **immutable**:

```java
enum Status {
    NEW, PAID
}
```

Nhưng Java cho phép enum có instance fields và methods; nếu bạn khai báo mutable field và setter, các constants là **shared objects**, nên mutation ảnh hưởng đến mọi nơi dùng cùng constant.

Đây là lỗi thiết kế dễ gây ra global shared state ngoài ý muốn.

### Không ghi runtime data vào enum constant

Không viết `Status.PAID.setCurrentOrderId("123")` để lưu trạng thái từng đơn hàng. Cùng một constant `PAID` có thể được dùng cho rất nhiều orders; không có enum instance riêng cho mỗi order.

Hãy đặt dữ liệu riêng ở `Order` hoặc `OrderSnapshot`, và dùng `Status` chỉ như một **ký hiệu trạng thái**.

## 25. Runnable: enum mutable state là dữ liệu chia sẻ

Lưu **`MutableEnumPitfallDemo.java`**:

```java
enum Mode {
    ACTIVE;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}

public class MutableEnumPitfallDemo {
    public static void main(String[] args) {
        Mode first = Mode.ACTIVE;
        Mode second = Mode.ACTIVE;

        first.hit();
        second.hit();

        System.out.println(first == second);
        System.out.println(first.hits());
        System.out.println(second.hits());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableEnumPitfallDemo.java
java MutableEnumPitfallDemo
```

Stdout:

```text
true
2
2
```

Demo **cố ý thể hiện anti-pattern**: `hits` là state chung của enum constant, không phải số hits riêng của mỗi user/request. Production thường để enum fields final và đặt per-instance mutable state nơi khác.

## 26. Enum có stable code: tránh dùng `ordinal()` làm ID

Một enum:

```java
enum PaymentState {
    NEW, PAID, CANCELLED
}
```

`ordinal()` phản ánh **vị trí** khai báo. Nếu chèn enum constant vào đầu hoặc đổi thứ tự, ordinal của các constants khác thay đổi. Vì vậy không lưu ordinal làm:
- Database status code bền vững.
- API public numeric identifier.
- JSON event field phục vụ consumers ở nhiều versions.
- Kafka message schema.
- Giá trị persist được cần giữ ổn định nhiều năm.

Thiết kế tốt hơn: định nghĩa **stable code** riêng.

```java
enum PaymentState {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

Khi thêm/reorder constants, code vẫn không đổi nếu bạn chủ động bảo toàn nó. Migration database/API cần versioning và compatibility contract cụ thể.

## 27. Runnable: enum stable code và parse

Lưu **`EnumStableCodeDemo.java`**:

```java
enum PaymentState {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static PaymentState fromCode(String code) {
        for (PaymentState state : values()) {
            if (state.code.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        PaymentState state = PaymentState.PAID;

        System.out.println(state.code());
        System.out.println(PaymentState.fromCode("C"));
        System.out.println(state == PaymentState.fromCode("P"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
```

Stdout:

```text
P
CANCELLED
true
```

Không in ordinal như một persistent ID. `fromCode` ném exception với unknown input để caller xử lý rõ. Nếu mỗi enum có nhiều constants, có thể dùng immutable lookup map được validate uniqueness lúc khởi tạo.

## 28. Enum + instance data: kết hợp đúng thay vì chọn một trong hai

Một entity `Order` có thể mutable nhưng chứa enum status:

```java
final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void markPaid() {
        status = OrderStatus.PAID;
    }

    OrderStatus status() {
        return status;
    }
}

enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Ở đây:
- `Order` là object mang identity/lifecycle riêng.
- `OrderStatus` là một enum symbol thuộc tập hữu hạn.
- Cập nhật status làm thay đổi **field của Order**, không làm thay đổi trạng thái singleton enum `OrderStatus.PAID`.

**Thiết kế tốt thường kết hợp nhiều loại**: mutable aggregate + enum state + immutable/record snapshot, chứ không bắt cả hệ thống phải chọn cùng một loại.

## 29. Runnable: mutable entity sử dụng enum status

Lưu **`OrderWithEnumDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID
}

final class Order {
    private final String id;
    private OrderStatus status = OrderStatus.NEW;

    Order(String id) {
        this.id = id;
    }

    void pay() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("already paid");
        }
        status = OrderStatus.PAID;
    }

    String id() {
        return id;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderWithEnumDemo {
    public static void main(String[] args) {
        Order order = new Order("O-1");

        System.out.println(order.status());
        order.pay();
        System.out.println(order.status());
        System.out.println(order.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrderWithEnumDemo.java
java OrderWithEnumDemo
```

Stdout:

```text
NEW
PAID
O-1
```

Nếu payment được thực thi trên nhiều threads hoặc liên quan database transaction, cần bổ sung concurrency/consistency controls. Ví dụ chỉ mô tả lựa chọn **mutable entity + immutable enum symbol**.

## 30. Thời gian và tiền: thường dùng immutable value

Một địa chỉ, giá tiền, khoảng thời gian hoặc tọa độ thường là **giá trị**, không phải đối tượng có identity riêng.

JDK đã có nhiều types bất biến:
- `String`.
- `BigInteger`, `BigDecimal` (với chú ý `equals` xét cả scale).
- `LocalDate`, `LocalTime`, `Instant`, `Duration`.
- `UUID` (value object).
- `Enum` constants theo thiết kế thường dùng như symbols.

Các value objects của bạn có thể là record hoặc immutable class:
- `Money(long cents, Currency currency)` khi dùng currency type phù hợp.
- `Coordinates(double latitude, double longitude)`.
- `DateRange(LocalDate start, LocalDate end)`.

### Số tiền: đừng tùy tiện dùng double

`double` là floating-point binary, không phù hợp mọi quy tắc tiền tệ. Một value object Money có thể lưu **minor units trong long** hoặc dùng `BigDecimal` và scale/rounding policy rõ.

Không tự giả định một currency có 2 decimal digits trong mọi trường hợp; domain quyết định minor unit contract.

## 31. Runnable: immutable Money record với validation

Lưu **`MoneyRecordDemo.java`**:

```java
import java.util.Objects;

enum Currency {
    VND, USD
}

record Money(long minorUnits, Currency currency) {
    Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        Objects.requireNonNull(currency, "currency");
    }

    Money plus(Money other) {
        if (currency != other.currency) {
            throw new IllegalArgumentException("currency mismatch");
        }
        return new Money(
                Math.addExact(minorUnits, other.minorUnits),
                currency);
    }
}

public class MoneyRecordDemo {
    public static void main(String[] args) {
        Money first = new Money(100, Currency.VND);
        Money second = new Money(50, Currency.VND);
        Money total = first.plus(second);

        System.out.println(first);
        System.out.println(total);
        System.out.println(total.currency());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MoneyRecordDemo.java
java MoneyRecordDemo
```

Stdout:

```text
Money[minorUnits=100, currency=VND]
Money[minorUnits=150, currency=VND]
VND
```

`plus` tạo một Money record **mới**. Cả currency symbol và minor units đều được giữ trong representation bất biến. Dùng `Math.addExact` để phát hiện overflow thay vì im lặng wrap long.

## 32. Canonical constructor và invariant của record

Record header định nghĩa components, nhưng **không tự validate business rule**:

```java
record Percentage(int value) {
}
```

Cho phép `new Percentage(-300)` nếu không có validation.

Compact canonical:

```java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("0..100");
        }
    }
}
```

Ưu điểm:
- Tất cả constructor paths cuối cùng phải đến canonical.
- Không phải tự gán component fields trong compact body.
- Constructor validation tập trung.
- API invariant rõ hơn.

### Chỉnh implicit parameters khi chuẩn hóa

`record Email(String address) { Email { address = address.strip().toLowerCase(Locale.ROOT); } }` là pattern hợp lệ. Chú ý null handling và địa chỉ email validation thực tế phức tạp hơn việc chỉ contains `@`.

### Runtime initialization khác mutation

Normalization trong constructor không làm object trở thành mutable. Giá trị được quyết định trước khi object được publish hoàn chỉnh.

## 33. Runnable: compact validation của record

Lưu **`ValidatedRecordDemo.java`**:

```java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("0..100");
        }
    }
}

public class ValidatedRecordDemo {
    public static void main(String[] args) {
        Percentage valid = new Percentage(75);

        System.out.println(valid);

        try {
            new Percentage(101);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ValidatedRecordDemo.java
java ValidatedRecordDemo
```

Stdout:

```text
Percentage[value=75]
0..100
```

Record là **convention ngôn ngữ cho data carrier**, nhưng invariants vẫn do người viết xác định.

## 34. Mutable element làm `List.copyOf` vẫn nông

Giả sử record:

```java
record Snapshot(List<MutableItem> items) {
    Snapshot {
        items = List.copyOf(items);
    }
}
```

`items` giờ unmodifiable ở cấu trúc list, nhưng từng `MutableItem` vẫn có methods thay đổi state. Nếu caller giữ reference đến item, hoặc accessor trả cùng item, snapshot value vẫn có thể thay đổi.

Để đạt deep immutable semantics có hai cách thường gặp:
1. Chuyển từng mutable element thành một **immutable value representation** (ví dụ record riêng) rồi lưu unmodifiable list.
2. Tạo copies sâu theo mức cần thiết, với contract rõ và tests cho nested graphs.

**Deep copy không đơn giản** nếu graph có cycles, shared identities, resource handles và subtype polymorphism. Thiết kế immutable dữ liệu đầu vào ngay từ đầu thường đơn giản hơn copy mọi thứ sau đó.

## 35. Runnable: List.copyOf không deep-copy phần tử

Lưu **`ShallowCopyDemo.java`**:

```java
import java.util.List;

final class MutableItem {
    private String name;

    MutableItem(String name) {
        this.name = name;
    }

    void rename(String value) {
        name = value;
    }

    String name() {
        return name;
    }
}

record BasketView(List<MutableItem> items) {
    BasketView {
        items = List.copyOf(items);
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        MutableItem item = new MutableItem("old");
        BasketView view = new BasketView(List.of(item));

        item.rename("new");

        System.out.println(view.items().get(0).name());
        System.out.println(view.items().size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
```

Stdout:

```text
new
1
```

Dù list là unmodifiable, element vẫn mutable. Không thể kết luận record deep immutable nếu chỉ nhìn `List.copyOf`.

## 36. Snapshot chuyển mutable state thành immutable values

Một mẫu rất hữu ích: mutable aggregate có method trả **record snapshot**.

```java
record AccountView(String id, long balance) {
}
```

Account object có `deposit`, `withdraw`; snapshot chỉ đọc, có value semantics và có thể truyền qua API/reporting boundary.

Ưu điểm:
- Các consumers không được quyền mutate entity thông qua snapshot.
- Snapshot mô tả trạng thái tại một thời điểm.
- UI/cache/reporting dễ làm việc với giá trị.
- Dễ so sánh/test snapshots.

Cần cân nhắc consistency khi snapshot nhiều mutable fields dưới concurrent updates: tạo snapshot phải đọc một trạng thái nhất quán nếu domain yêu cầu; có thể cần lock/transaction.

## 37. Runnable: mutable Account → immutable record snapshot

Lưu **`MutableToRecordSnapshotDemo.java`**:

```java
final class Account {
    private final String id;
    private long balance;

    Account(String id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    void deposit(long amount) {
        balance = Math.addExact(balance, amount);
    }

    AccountSnapshot snapshot() {
        return new AccountSnapshot(id, balance);
    }
}

record AccountSnapshot(String id, long balance) {
}

public class MutableToRecordSnapshotDemo {
    public static void main(String[] args) {
        Account account = new Account("A", 100);

        AccountSnapshot before = account.snapshot();
        account.deposit(50);
        AccountSnapshot after = account.snapshot();

        System.out.println(before);
        System.out.println(after);
        System.out.println(before.equals(after));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableToRecordSnapshotDemo.java
java MutableToRecordSnapshotDemo
```

Stdout:

```text
AccountSnapshot[id=A, balance=100]
AccountSnapshot[id=A, balance=150]
false
```

`before` không tự thay đổi khi entity state thay đổi. Đây là thiết kế thường tốt hơn biến một entity mutable thành record chứa toàn bộ business lifecycle.

## 38. Equality ảnh hưởng cách chọn type

### Mutable class

Với mutable object có ID cố định, equality nên được thiết kế cẩn thận. Không tự sinh `equals/hashCode` dựa trên mọi mutable fields nếu object sẽ làm key trong `HashMap`.

### Immutable value class

Nên định nghĩa value-based `equals/hashCode` nếu semantics yêu cầu (và đảm bảo chúng thống nhất). Một class bất biến **không bắt buộc** override equals về mặt ngôn ngữ, nhưng value objects thường cần.

### Record

Generated equality xét component values. Đối với primitive components, so theo quy tắc record. Với reference components, equality sử dụng semantics của component objects. Mutable components có thể làm equality/hashing của record thay đổi.

### Enum

Enum constants có fixed identity trong enum class; `==` thường là cách so sánh thích hợp. `name()` là identifier source, có thể đổi trong refactor và ảnh hưởng persisted contracts nếu bạn lưu name; stable explicit code là giải pháp nếu cần wire compatibility.

## 39. Mutable key có thể làm Map lookup bất ổn

Nếu bạn dùng một object có `hashCode()` thay đổi sau khi đưa vào HashMap làm key, bucket/hash placement ban đầu không còn tương ứng với hash mới. Khi đó lookup/removal có thể không tìm được mapping.

Đây là anti-pattern:

```java
Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey("A");
map.put(key, "value");
key.setCode("B");
```

Đây là snippet, `MutableKey` có thể được định nghĩa với equals/hashCode theo code. Kết quả lookup phụ thuộc implementation/hash distribution; điểm trọng tâm là **vi phạm invariant hashCode ổn định khi key nằm trong hash map**, không cần một stdout minh họa may rủi.

### Phương án an toàn

- Dùng immutable key record/class có deeply immutable components.
- Dùng immutable business ID làm key (`String`, `UUID`).
- Nếu cần mutable key object, tránh sửa fields góp phần tính equality/hashCode khi key đang trong collection.
- Dùng identity-based collection chỉ khi semantics thực sự yêu cầu object identity.

## 40. Value equality trên số thập phân cần chính sách

`BigDecimal.equals` xét cả **giá trị và scale**. Ví dụ:

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00"))
```

trả `false` mặc dù `compareTo` trả 0.

Nếu record:

```java
record Price(BigDecimal amount) {
}
```

generated equals của Price dùng equals của BigDecimal. Vì vậy hai prices biểu diễn tiền tương đương theo nghiệp vụ có thể không equal nếu scales khác.

Giải pháp tùy domain:
- Chuẩn hóa `amount` trong canonical constructor theo scale/rounding policy cố định.
- Dùng minor units `long` nếu business supports.
- Định nghĩa rõ numeric equality policy nếu custom immutable class/record.
- Không đổi `equals` mà quên `hashCode`.
- Không thay đổi amount sau khi dùng làm map key.

## 41. Runnable: BigDecimal scale tác động value equality

Lưu **`BigDecimalRecordDemo.java`**:

```java
import java.math.BigDecimal;

record Price(BigDecimal amount) {
}

public class BigDecimalRecordDemo {
    public static void main(String[] args) {
        Price first = new Price(new BigDecimal("1.0"));
        Price second = new Price(new BigDecimal("1.00"));

        System.out.println(first.equals(second));
        System.out.println(
                first.amount().compareTo(second.amount()) == 0);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BigDecimalRecordDemo.java
java BigDecimalRecordDemo
```

Stdout:

```text
false
true
```

Đừng gọi record “sai” khi nhận false: nó dùng component equality theo `BigDecimal`. Bạn cần chọn và document business equality semantics phù hợp.

## 42. Enum ordinal không phải identity nghiệp vụ bền vững

`Status.ACTIVE.ordinal()` là index của constant trong declaration. Nó có thể đổi khi:
- Chèn một enum constant ở vị trí trước nó.
- Sắp xếp lại source.
- Xóa/reorganize constants.

**Không ghi `ordinal` vào database hoặc wire protocol như ID bền vững**. Khi migrating legacy ordinals, phải có mapping đúng theo **phiên bản lịch sử**; không thể luôn suy ra mã cũ từ thứ tự enum hiện tại.

`name()` ổn định hơn ordinal trước reorder nhưng vẫn có thể đổi tên constant. Với external long-lived data, explicit stable code/contract giúp quản lý migrations rõ hơn.

### EnumMap và EnumSet

Các collections chuyên biệt có thể dùng enum ordinal nội bộ để tối ưu. Điều đó **không** có nghĩa bạn nên persist ordinal như protocol public. Dùng `EnumMap/EnumSet` theo API, không phụ thuộc layout internal.

## 43. Runnable: EnumSet cho một tập hằng

Lưu **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, DELETE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        System.out.println(granted.contains(Permission.READ));
        System.out.println(granted.contains(Permission.DELETE));
        System.out.println(granted.size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSetDemo.java
java EnumSetDemo
```

Stdout:

```text
true
false
2
```

EnumSet phù hợp cho một **tập permissions thuộc enum type**. Nó không phải chỗ lưu permissions động mà source code không hề biết trước.

## 44. Khi nào dùng sealed interface + record thay enum?

Enum biểu diễn một tập constants. Nhưng đôi khi mỗi **biến thể** có payload với schema khác nhau:

- `Success(receiptId, timestamp)`.
- `Failure(errorCode, reason)`.
- `Pending(retryAt)`.

Ép chúng vào một enum có fields nullable tương ứng từng variant sẽ tạo invalid combinations và khó kiểm tra invariant.

Java 17 có sealed interfaces/classes và records để biểu diễn **tập variant types hữu hạn nhưng mỗi variant có payload riêng**.

```java
sealed interface Result permits Ok, Error {
}

record Ok(String data) implements Result {
}

record Error(String message) implements Result {
}
```

`Result` giới hạn direct permitted subtypes. Mỗi record leaf là implicitly final. Đây là một dạng *sum type* được mô phỏng bằng sealed hierarchy, khác enum constants.

**Java 17 lưu ý:** pattern matching `instanceof` đã stable; pattern matching `switch` trên type patterns khi đó vẫn là preview, không dùng trong ví dụ `javac --release 17` thông thường.

## 45. Runnable: sealed interface và record variants

Lưu **`SealedRecordResultDemo.java`**:

```java
sealed interface Result permits Ok, Error {
}

record Ok(String data) implements Result {
}

record Error(String message) implements Result {
}

public class SealedRecordResultDemo {
    static String describe(Result result) {
        if (result instanceof Ok ok) {
            return "ok:" + ok.data();
        }
        if (result instanceof Error error) {
            return "error:" + error.message();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ok("A")));
        System.out.println(describe(new Error("invalid")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedRecordResultDemo.java
java SealedRecordResultDemo
```

Stdout:

```text
ok:A
error:invalid
```

Nếu mỗi result cần payload khác nhau, sealed interface + record variants có thể rõ hơn enum với các nullable fields không liên quan. Khi thêm variant mới, cập nhật code phân loại và tests; đừng tự giả định chuỗi `if` là exhaustively checked bởi compiler.

## 46. Enum cho trạng thái hay state machine trong class?

Giả sử một workflow có `NEW`, `PAID`, `SHIPPED`, `CANCELLED`:
- Enum dùng làm **tập ký hiệu states**.
- Mutable Order/Process object giữ **current state**.
- Methods điều khiển transitions theo business constraints.

```java
void ship() {
    if (status != Status.PAID) {
        throw new IllegalStateException("not paid");
    }
    status = Status.SHIPPED;
}
```

Nếu có side effects tới payment, inventory, network, database, cần transaction/process orchestration. Enum không đảm bảo state machine consistency chỉ bằng cách tồn tại.

### Khi transition thuần giá trị

Nếu domain muốn bất biến, có thể dùng một immutable record trả về bản mới mỗi lần transition:

```java
record OrderState(String id, Status status) {
    OrderState shipped() {
        if (status != Status.PAID) {
            throw new IllegalStateException();
        }
        return new OrderState(id, Status.SHIPPED);
    }
}
```

Chọn dựa vào identity/lifecycle/consistency model, không phải một quy tắc bắt mọi state machine phải mutable.

## 47. Runnable: state transition bất biến bằng record

Lưu **`ImmutableStateTransitionDemo.java`**:

```java
enum State {
    NEW, PAID, SHIPPED
}

record OrderState(String id, State state) {
    OrderState pay() {
        if (state != State.NEW) {
            throw new IllegalStateException("not new");
        }
        return new OrderState(id, State.PAID);
    }

    OrderState ship() {
        if (state != State.PAID) {
            throw new IllegalStateException("not paid");
        }
        return new OrderState(id, State.SHIPPED);
    }
}

public class ImmutableStateTransitionDemo {
    public static void main(String[] args) {
        OrderState original = new OrderState("A", State.NEW);
        OrderState paid = original.pay();
        OrderState shipped = paid.ship();

        System.out.println(original.state());
        System.out.println(paid.state());
        System.out.println(shipped.state());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableStateTransitionDemo.java
java ImmutableStateTransitionDemo
```

Stdout:

```text
NEW
PAID
SHIPPED
```

Mỗi transition trả **value mới**; original không đổi. Kiểu mô hình này đặc biệt dễ test khi state nhỏ và không cần shared mutable identity.

## 48. Thread safety không tự đến từ keyword

- Mutable class thường cần concurrency control nếu nhiều threads dùng chung.
- Immutable value được **thiết kế đúng và publish an toàn** thường đơn giản hơn để chia sẻ.
- Record fields final giúp xây component state nhưng nếu referents mutable thì concurrency hazards vẫn tồn tại.
- Enum constants là objects chia sẻ; nếu có mutable fields, chúng có thể thành global race condition.
- `volatile` giải quyết một số visibility/happens-before concerns, **không biến mọi compound update thành atomic** và không làm toàn object immutable.
- `synchronized` hoặc `AtomicInteger` giải quyết các nhu cầu cụ thể, không thay kiến trúc ownership.

### Immutability hỗ trợ điều gì?

Khi object thực sự immutable, consumers có thể dùng cùng reference mà không lo updates cạnh tranh trên state của object; dễ caching và reasoning hơn. Tuy nhiên nếu constructor publish `this` trước khi hoàn tất hoặc component graphs mutate, lợi ích bị ảnh hưởng.

**Không nói “mọi immutable object mặc nhiên giải quyết mọi concurrency bug”**: transaction, ordering, external services, atomic snapshots giữa nhiều objects vẫn cần chiến lược riêng.

## 49. Runnable: immutable point được dùng nhiều lần không đổi

Lưu **`ImmutableReuseDemo.java`**:

```java
record Point(int x, int y) {
    Point move(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}

public class ImmutableReuseDemo {
    public static void main(String[] args) {
        Point original = new Point(1, 2);
        Point moved = original.move(3, 4);

        System.out.println(original);
        System.out.println(moved);
        System.out.println(original.equals(moved));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableReuseDemo.java
java ImmutableReuseDemo
```

Stdout:

```text
Point[x=1, y=2]
Point[x=4, y=6]
false
```

Tạo object mới khi thay đổi value là một pattern phù hợp cho dữ liệu nhỏ. Với updates rất nhiều hoặc object graphs cực lớn, cần đánh giá cost thực tế, không vội tối ưu bằng mutation trước khi đo.

## 50. Hiệu năng: tránh kết luận “record nhanh hơn class”

Không có bảo đảm ngôn ngữ rằng:
- `record` luôn dùng ít memory hơn class thủ công.
- Immutable object luôn nhanh hơn mutable.
- Enum luôn nhanh nhất trong mọi cách dùng.
- Tạo nhiều immutable copies luôn chậm tới mức phải bỏ.

JVM JIT, allocation optimizations, GC, object layout, access patterns và workload quyết định kết quả.

Một record Java 17 vẫn là một **reference object**, không phải C struct được đảm bảo stack-allocate. Object creation có thể được JVM tối ưu nhưng không được hứa ở source level.

### Cách quyết định tối ưu

1. Chọn semantics đúng (identity/mutation/value/fixed set).
2. Đo allocation rate, throughput, latency, retained memory bằng benchmark/profiling phù hợp (ví dụ JMH/JFR).
3. Chỉ đổi representation nếu có bottleneck thật.
4. Nếu dữ liệu lớn, cân nhắc batch processing, primitive arrays/streams, bounded caches; tránh thay API semantics chỉ để tiết kiệm vài ký tự source.

**Record là cú pháp và contract minh bạch, không phải performance annotation.**

## 51. API compatibility khi chọn record

Chuyển từ class thường sang record có thể thay đổi:
- Superclass và finality.
- Constructor signatures.
- Accessor naming (getter `getX()` khác component accessor `x()`).
- Reflection metadata.
- Java serialization semantics.
- Framework binding/proxy behavior.
- Equality/hashCode/toString behavior.
- Public API compatibility.
- Cách clients subclass class cũ.

Không coi `class Person` → `record Person` là refactor thuần cú pháp. Hãy xem public callers, serializers, ORMs và backward compatibility.

### Một immutable class cũ vẫn là lựa chọn tốt

Nếu API đã ổn định với `getName()`, class fields private, custom equality và generated proxies, không nhất thiết phải đổi thành record dù object logic bất biến.

## 52. ORM/persistence: entity vs DTO

Các ORM/JPA implementations có thể có requirements về:
- No-arg constructor visibility.
- Entity mutability.
- Proxies hoặc enhancement.
- Finality của class/methods.
- Field/property access.
- Mapping và identity equality.

Do record implicitly final và canonical constructor đặc thù, **không mặc nhiên xem record là JPA entity tương thích**. Một số frameworks hỗ trợ records cho **DTO projections**, embeddables hoặc serialization use cases theo version; phải kiểm tra framework cụ thể.

### Pattern thường gặp

- **Persistence entity:** mutable class (theo framework contract), có business identity và invariants.
- **API/request/response DTO:** record khi components và equality semantics phù hợp.
- **Domain value object:** record hoặc immutable class.
- **Static status column:** enum với stable mapping strategy; không persist ordinal tùy tiện.

**Đừng áp ORM rules lên mọi domain class.** Nếu code không dùng ORM, bạn có thể chọn record/immutable class tự do hơn.

## 53. Serialization và wire format

Dữ liệu truyền qua HTTP/JSON/Kafka/database có hợp đồng tồn tại lâu hơn một object in-memory.

### Mutable class

Có thể được nhiều serializers xây bằng no-arg constructor và setters; nhưng library thực tế có thể hỗ trợ constructor binding hoặc builders. Không giả định tất cả cần setters.

### Immutable class

Có thể cần constructor/factory annotation, mapper configuration hoặc adapter tùy framework.

### Record

Component names/types xuất hiện trong record reflection. Nhiều serializers hiện đại hỗ trợ record constructor binding, nhưng phải kiểm tra version/config. Đổi component names/types có thể làm vỡ schema của external clients.

### Enum

Có thể serialize bằng name/code/ordinal tùy framework. **Chọn stable wire representation rõ ràng**, tránh vô tình default sang ordinal. Hỗ trợ unknown code/version evolution nếu external data có thể đến từ versions tương lai.

**Tách kiểu trong code khỏi wire schema:** một enum có stable code là lựa chọn tốt hơn ordinal cho durable data, nhưng vẫn cần migration policy khi thêm/bỏ codes.

## 54. Null và validation theo từng lựa chọn

Cả bốn kiểu đều cần design rõ:
- Mutable class: constructor + mutation methods bảo vệ invariant, null policy.
- Immutable class: validate trước publish; fields final; không để invalid state.
- Record: canonical/compact constructor validate component arguments; accessors có thể cần defensive copy.
- Enum: enum constants không null khi đã tham chiếu, nhưng một **variable có type enum vẫn có thể nhận null**; `switch(null)` trên enum không tự là xử lý “unknown” an toàn trong Java 17.

### Trường hợp cần “không có trạng thái”

Không tự tạo enum constant `UNKNOWN` nếu domain không muốn; có thể dùng `Optional` ở boundary phù hợp, hoặc explicit status. `Optional` phù hợp chủ yếu làm return type theo JDK guidance, không mặc nhiên dùng cho mọi field/parameter.

### Empty object không tự là invalid

`List.of()` là unmodifiable empty list hợp lệ. Quy tắc cấm empty/null tùy domain.

## 55. Runnable: validate một value record và enum

Lưu **`ValidatedProfileDemo.java`**:

```java
import java.util.Objects;

enum Membership {
    BASIC, PREMIUM
}

record Profile(String name, Membership membership) {
    Profile {
        name = Objects.requireNonNull(name, "name").strip();
        Objects.requireNonNull(membership, "membership");

        if (name.isEmpty()) {
            throw new IllegalArgumentException("empty name");
        }
    }
}

public class ValidatedProfileDemo {
    public static void main(String[] args) {
        Profile profile = new Profile(
                "  An  ", Membership.PREMIUM);

        System.out.println(profile);

        try {
            new Profile(" ", Membership.BASIC);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ValidatedProfileDemo.java
java ValidatedProfileDemo
```

Stdout:

```text
Profile[name=An, membership=PREMIUM]
empty name
```

Normalization trong compact constructor là một phần **construction**, không cho phép mutation sau đó qua record fields.

## 56. Builder khi object immutable có nhiều optional attributes

Một immutable class hoặc record có quá nhiều constructors overload (đặc biệt nhiều parameters cùng type) có thể làm API khó hiểu:

```java
new Config("api", 30, true, false, 4, "asia", ...)
```

Giải pháp:
- Named static factories.
- Builder lưu **mutable intermediate state** rồi xây một **immutable final object**.
- Nhóm các parameters vào những record value types nhỏ có nghĩa.
- Dùng defaults ở nơi business rules rõ, không tự suy đoán.

Builder itself có thể mutable mà **result** bất biến. Đây là kết hợp rất phổ biến và hoàn toàn hợp lý.

## 57. Runnable: mutable builder tạo immutable record

Lưu **`BuilderToRecordDemo.java`**:

```java
record Config(String host, int port, boolean tls) {
    Config {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port");
        }
    }
}

final class ConfigBuilder {
    private String host = "localhost";
    private int port = 8080;
    private boolean tls;

    ConfigBuilder host(String host) {
        this.host = host;
        return this;
    }

    ConfigBuilder port(int port) {
        this.port = port;
        return this;
    }

    ConfigBuilder tls(boolean tls) {
        this.tls = tls;
        return this;
    }

    Config build() {
        return new Config(host, port, tls);
    }
}

public class BuilderToRecordDemo {
    public static void main(String[] args) {
        Config config = new ConfigBuilder()
                .host("example.com")
                .port(443)
                .tls(true)
                .build();

        System.out.println(config);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BuilderToRecordDemo.java
java BuilderToRecordDemo
```

Stdout:

```text
Config[host=example.com, port=443, tls=true]
```

Builder dùng mutable fields như một construction helper; record `Config` được tạo ở cuối và validate invariants. Client có thể bỏ Builder sau khi build.

## 58. Khi nào không nên biến class thành record?

Các dấu hiệu:
- Class cần superclass riêng (record đã extends `java.lang.Record`).
- Class phải được subclass/proxy theo framework architecture.
- Object có nhiều biến đổi state nội tại cần identity.
- API muốn ẩn representation hoàn toàn sau public methods.
- Cần thêm non-static instance fields khác components.
- Equality không nên tự động gắn với record header.
- Field data là mutable graph khó snapshot/defensive copy.
- Backward compatibility với getters/constructors hiện tại quan trọng.
- Class nắm file/socket/resource lifecycle và nên có `close()` rõ.

**Không có lệnh cấm tuyệt đối:** một record có thể implement `AutoCloseable` nếu components giữ resource; nhưng record không tự giải quyết ownership, aliasing, idempotency và premature close. Với resource-owning lifecycle, một class tường minh thường giúp biểu diễn state tốt hơn.

## 59. Khi nào một class immutable tốt hơn record?

Ví dụ:
- Immutable wrapper quanh mutable array cần custom value equality và clone input/output.
- Class che giấu internal indexing/cache/layout.
- Có nhiều dạng construction với normalized representation không muốn công bố trong record components.
- Public API giữ `getX()` hoặc abstraction đã có.
- Value semantics cần invariants custom nhưng record generated methods không thật sự phù hợp.

**Cũng không suy ra rằng record chỉ dành cho DTO:** nếu components hợp lý, một domain value object như `Money`, `DateRange`, `Coordinate` rất phù hợp với record. Quan trọng là contract.

## 60. Khi nào enum không nên là source-of-truth data?

Không chọn enum khi:
- Hàng trăm/millions of products/countries/users được quản lý động.
- Người dùng/admin được phép thêm option không cần deploy code.
- Mỗi option có dữ liệu riêng cần thay theo tenant/request.
- Có date effective ranges/versioning phức tạp cho category entries.
- IDs từ database không ổn định với deployment.
- Hệ thống phải xử lý future codes chưa có trong source.

Thay bằng class/record immutable mô tả **một entity/value từ database**, có stable ID và repository/service. Enum vẫn có thể dùng cho **loại** của entity, không phải thay cả entity.

## 61. Runnable: data động là record, category cố định là enum

Lưu **`DynamicDataVsEnumDemo.java`**:

```java
enum ProductKind {
    BOOK, TOOL
}

record Product(String id, String name, ProductKind kind) {
}

public class DynamicDataVsEnumDemo {
    public static void main(String[] args) {
        Product one = new Product("P-1", "Guide", ProductKind.BOOK);
        Product two = new Product("P-2", "Hammer", ProductKind.TOOL);

        System.out.println(one.name());
        System.out.println(two.kind());
        System.out.println(one.equals(two));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DynamicDataVsEnumDemo.java
java DynamicDataVsEnumDemo
```

Stdout:

```text
Guide
TOOL
false
```

Các Products là data instances có IDs khác nhau; `ProductKind` là một fixed set ký hiệu. Nếu Product cần update tồn kho/trạng thái trên chính instance, cân nhắc mutable entity + record snapshot thay vì record entity.

## 62. Class có thể immutable nhưng vẫn “entity-like”

Không phải entity nào cũng **buộc mutable in-memory**. Một event-sourced domain có thể biểu diễn entities bằng immutable state snapshots và replace references khi có event mới, trong khi business identity vẫn là ID cố định.

Ví dụ:

```java
record AccountState(String accountId, long balance) {
    AccountState deposit(long amount) {
        return new AccountState(
                accountId, Math.addExact(balance, amount));
    }
}
```

Ở đây cùng `accountId` qua snapshots khác nhau, nhưng `equals` của AccountState phân biệt balances khác nhau. Nếu application hỏi “cùng entity?” thì so `accountId`; nếu hỏi “cùng snapshot value?” thì dùng `equals` theo components.

**Đừng đồng nhất “business identity” với Java object identity hay auto-generated record equals**.

## 63. API boundaries: cái gì được chia sẻ và ai được sửa?

Một chiến lược hiệu quả:
- Trong application/domain core, mutable aggregates có thể tồn tại dưới owner rõ.
- Khi gửi dữ liệu qua boundary (API, queue, UI state), tạo immutable snapshot/record.
- Enum biểu diễn mã categories hữu hạn.
- Value objects immutable giữ các invariant địa chỉ, tiền, thời gian.
- Collections ở boundary nên snapshot/copy, không lộ mutable internal references trừ khi API chủ đích cho phép mutation.

Với multi-threaded system, immutable snapshots giảm aliasing, nhưng vẫn cần serialize/coordinate updates đến mutable source.

### Không “chuyển quyền sở hữu” bằng comment suông

Nếu trả thẳng reference tới internal mutable list, consumer có thể thay đổi state dù documentation nói chỉ đọc. API nên bảo vệ representation bằng copy/unmodifiable wrapper đúng semantics, hoặc công bố rõ shared ownership contract.

## 64. API và testing: test gì cho từng kiểu?

**Mutable class:**
- Trạng thái trước/sau operation.
- Invariants ở mọi mutation path.
- Aliasing và concurrent updates nếu nhiều threads.
- Identity/business ID.
- Unsubscribe/close lifecycle nếu có.

**Immutable class:**
- Không sửa được state sau creation.
- Defensive copy input/output (bao gồm nested mutables).
- Equality/hash consistency.
- Factory/constructor validation.
- Không publish partially initialized state.

**Record:**
- Canonical validation, normalization.
- Generated component accessors/toString/equality semantics đúng domain.
- No mutable aliasing nếu intended immutable.
- Array/list component caveats.
- Serialization/mapper compatibility theo environment.

**Enum:**
- Constants, switch behavior.
- Stable code uniqueness và reverse lookup.
- Unknown code/null policy.
- Không có mutable per-request state.
- Persisted schema migration compatibility khi thay đổi constants.

## 65. Một bộ test không cần thư viện ngoài

Lưu **`DesignContractTestDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

enum Level {
    BASIC, PRO
}

record Config(List<String> names, Level level) {
    Config {
        names = List.copyOf(names);
        if (level == null) {
            throw new IllegalArgumentException("level");
        }
    }
}

public class DesignContractTestDemo {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("contract");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Config config = new Config(source, Level.PRO);
        source.add("B");

        require(config.names().equals(List.of("A")));
        require(config.level() == Level.PRO);
        require(config.equals(
                new Config(List.of("A"), Level.PRO)));

        try {
            config.names().add("C");
            throw new AssertionError("expected unmodifiable");
        } catch (UnsupportedOperationException expected) {
            // OK.
        }

        System.out.println("PASS");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DesignContractTestDemo.java
java DesignContractTestDemo
```

Stdout:

```text
PASS
```

Test xác minh value semantics của record, snapshot copy, unmodifiable list và enum identity. Không dựa vào GC, timing hay framework ngoài.

## 66. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`final class` = immutable” | Instance fields vẫn có thể mutable | Private final fields + defensive copies + no mutation |
| “`final List` = unmodifiable list” | Final chỉ ngăn gán lại reference | `List.copyOf` hoặc immutable collection theo contract |
| “`record` = deep immutable” | Components có thể giữ mutable references | Clone/copy + immutable elements |
| “Record array equals so nội dung” | Array component dùng reference equality mặc định | Custom value wrapper / deep comparator consistent |
| “Immutable cần mọi setter để deserialize” | Frameworks khác nhau, constructor binding có thể hỗ trợ | Kiểm tra serializer/version |
| “Enum một instance cho mỗi order” | Enum constant là shared value | Mutable Order chứa enum field |
| “Enum luôn immutable” | Mutable enum instance fields được ngôn ngữ cho phép | Không dùng mutable enum global state |
| “Enum ordinal ổn định” | Thứ tự khai báo có thể đổi | Stable explicit code |
| “Record giống entity ORM ở mọi framework” | Finality/canonical constructor/proxies có constraints | Dùng DTO/embeddable theo framework support |
| “HashMap key được mutate thoải mái” | Hash/equality có thể đổi | Immutable keys hoặc không sửa key-state |
| “Value equality giống identity” | Hai objects equals true vẫn có thể khác `==` | Tách ID và component equality |
| “Immutable object lúc nào cũng thread-safe” | Unsafe publication/transitive mutation vẫn có thể tồn tại | Deep immutable design + publication đúng |
| “`List.copyOf` deep copy” | Copy nông các element references | Chuyển elements sang immutable |
| “Mutable class luôn kém hơn record” | Có use cases đòi identity/mutation | Thiết kế theo lifecycle |
| “Record chắc chắn nhanh hơn class” | Không có performance guarantee | Benchmark workload |
| “Enum phù hợp dữ liệu thêm từ DB” | Constants cố định tại compile/deploy | Record/class với stable IDs |
| “Sealed variants dùng pattern switch ổn định ở Java17” | Java17 pattern switch là preview | `instanceof` stable/polymorphism |

## 67. Checklist ra quyết định thiết kế

- [ ] Đây là **fixed set of symbols** hay values tùy ý?
- [ ] Nếu fixed set, enum constants có ổn định và hữu hạn không?
- [ ] Nếu enum được persist, đã có stable code ngoài ordinal?
- [ ] Nếu constants đổi tên/thứ tự, external consumers có được bảo vệ không?
- [ ] Enum có vô tình lưu mutable per-request data không?
- [ ] Object có business identity riêng không?
- [ ] Có cần cập nhật **cùng instance** sau khi khởi tạo không?
- [ ] Nếu mutable, operations có bảo vệ invariants không?
- [ ] Nếu mutable, concurrency/transactions được thiết kế chưa?
- [ ] Có muốn equality theo toàn bộ giá trị components không?
- [ ] Nếu value carrier, record header có mô tả đúng representation không?
- [ ] Record có cần custom normal/compact canonical validation không?
- [ ] Record có mutable list/array/component object không?
- [ ] Defensive copy cả input lẫn output nếu cần chưa?
- [ ] `List.copyOf` có đủ hay còn mutable elements?
- [ ] Nếu array component, đã xét generated equals/hashCode chưa?
- [ ] Nếu immutable class, đã hạn chế subclass thay đổi invariant?
- [ ] Nếu immutable class, private final state và escape safety đầy đủ?
- [ ] Có cần ẩn representation hơn record cho phép không?
- [ ] Nếu BigDecimal, đã quy định scale/rounding/equality chưa?
- [ ] Hash-based keys có stable equals/hashCode suốt thời gian nằm trong map?
- [ ] Mutable entity và immutable snapshot có vai trò phân biệt không?
- [ ] DTO/request/response có phù hợp record mapping trong framework thực tế không?
- [ ] Nếu ORM cần proxy/no-arg constructors, đã kiểm tra các ràng buộc?
- [ ] Nếu cần inheritance, đã loại record/enum khỏi vị trí superclass không phù hợp?
- [ ] Nếu có nhiều variants mỗi dạng payload riêng, sealed interface + record có tốt hơn enum không?
- [ ] API cần builder/named factory thay constructor overload khó đọc không?
- [ ] Null/unknown/invalid value policy được thể hiện ở constructors/factories?
- [ ] Không expose live mutable internal collections nếu contract là read-only?
- [ ] Có giữ source/binary/serialization compatibility khi đổi class sang record không?
- [ ] Có benchmark trước các thay đổi “tối ưu” đi ngược semantics?
- [ ] Có tests cho value semantics, identity, mutation và defensive copies?
- [ ] Có tests cho stable enum codes và unknown data?
- [ ] Mỗi lựa chọn được giải thích bằng domain rules, không chỉ sở thích cú pháp?

## 68. Bài tập 1 — Một tọa độ

Bạn cần lưu kinh độ/vĩ độ, không muốn mutate, so equality theo hai giá trị.

**Đáp án:** Record `Coordinates(double latitude,double longitude)` hoặc immutable class nếu có validation/representation đặc biệt. Với record, dùng compact canonical để validate ranges theo domain.

## 69. Bài tập 2 — Giỏ hàng

Một shopping cart có ID cố định, người dùng thêm/xóa items trong cùng session.

**Đáp án:** Mutable class/aggregate với operations `addItem/removeItem` và invariants. Có thể cung cấp immutable record snapshot cho UI.

## 70. Bài tập 3 — Trạng thái thanh toán

Tập states `NEW, PAID, CANCELLED` cố định.

**Đáp án:** Enum. Nếu trạng thái thuộc từng Order, đặt field `OrderStatus status` trong Order, không đặt per-order state vào enum constant.

## 71. Bài tập 4 — Countries từ database

Admin có thể thêm một country/category mới trong database mà không deploy.

**Đáp án:** Không ép vào enum; dùng class/record data type với stable ID và repository. Enum chỉ phù hợp nếu fixed set do source code kiểm soát.

## 72. Bài tập 5 — DTO HTTP response

Response có `id`, `name`, `createdAt`, không mutate, mapper hỗ trợ Java 17 records.

**Đáp án:** Record hợp lý, với components immutable và validation nếu cần. Cần kiểm tra serialization names/types của framework cụ thể.

## 73. Bài tập 6 — Final field

`private final List<String> names = new ArrayList<>();` bảo đảm names không bị thay đổi không?

**Đáp án:** Không. Field reference không thể gán lại, nhưng ArrayList contents có thể mutate.

## 74. Bài tập 7 — Array record

`record Bytes(byte[] data) {}`. Vì sao không nên coi nó deep immutable?

**Đáp án:** Caller và accessor có thể mutate cùng array; generated record equality so array references chứ không deep content. Cần clone và custom equality policy hoặc immutable wrapper.

## 75. Bài tập 8 — Immutable value mới

Một immutable Range có method `shift(5)`. Nên làm gì?

**Đáp án:** Trả một Range mới; không mutate instance hiện tại.

## 76. Bài tập 9 — Record state update

`record OrderState(String id, Status status)` muốn chuyển NEW→PAID.

**Đáp án:** Method có thể validate transition rồi return new `OrderState(id,PAID)`. Nếu muốn cùng entity instance mutate, dùng mutable class với enum field.

## 77. Bài tập 10 — Enum ordinal

Persist `Status.PAID.ordinal()` dưới dạng integer. Nguy cơ gì?

**Đáp án:** Reorder/insert constants làm mã đổi nghĩa; dùng explicit stable code có migration strategy.

## 78. Bài tập 11 — Enum mutable field

`enum Mode { ACTIVE; int counter; }` và nhiều requests tăng counter.

**Đáp án:** Counter được chia sẻ giữa mọi nơi dùng ACTIVE, dễ race/global state. Không lưu request data trong enum.

## 79. Bài tập 12 — Map key mutable

Một key có equals/hashCode dựa trên name, name bị sửa sau `map.put(key,value)`.

**Đáp án:** Có thể làm hash lookup thất bại/không nhất quán. Dùng immutable key hoặc stable identity fields.

## 80. Bài tập 13 — List.copyOf

Record lưu `List<MutableItem>` qua `List.copyOf`, có deep immutable không?

**Đáp án:** Không. Cấu trúc list unmodifiable, elements vẫn mutable nếu references cho phép.

## 81. Bài tập 14 — Unmodifiable view

`Collections.unmodifiableList(source)` có phải snapshot không?

**Đáp án:** Không. Source mutation vẫn phản ánh trên view; khác `List.copyOf(source)` shallow snapshot.

## 82. Bài tập 15 — Record constructor

Muốn cấm `new Percentage(150)`, đặt validation ở đâu?

**Đáp án:** Compact canonical constructor của Percentage (hoặc explicit normal canonical), throw exception khi ngoài range.

## 83. Bài tập 16 — Business identity

Hai Accounts có cùng balance nhưng khác ID có nên equals không?

**Đáp án:** Tùy contract, nhưng nếu Account là entity identity-based, chúng thường khác entity; không lấy “cùng balance” làm business identity.

## 84. Bài tập 17 — Record equals

`new Point(1,2).equals(new Point(1,2))` với record Point primitive components.

**Đáp án:** True theo generated component equality; `==` giữa hai new objects là false.

## 85. Bài tập 18 — BigDecimal

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả gì?

**Đáp án:** False do scale khác; `compareTo==0`. Record component equality sẽ phản ánh điều này nếu không normalize.

## 86. Bài tập 19 — ORM entity

Một JPA framework yêu cầu proxy/no-arg constructor theo implementation. Có nên mặc định thay entity bằng record không?

**Đáp án:** Không. Kiểm tra spec/framework; record final và constructor conventions có thể không đáp ứng entity requirements. Record DTO projection có thể là ứng dụng phù hợp nếu được hỗ trợ.

## 87. Bài tập 20 — Số variants có payload

Result thành công mang receiptId, thất bại mang error code + reason; không muốn nhiều fields null.

**Đáp án:** Sealed interface + các record/final class leaves, với Java 17 `instanceof` pattern matching hoặc polymorphism.

## 88. Bài tập 21 — Enum singleton identity

`Priority.HIGH == Priority.HIGH` có hợp lý không?

**Đáp án:** Có; enum constant là named singleton instance của enum type trong runtime classloader context.

## 89. Bài tập 22 — Immutable factory

Một object có 15 optional attributes; constructor rất dài.

**Đáp án:** Builder hoặc named factories có thể giúp. Builder mutable ở construction stage, kết quả immutable class/record nếu copy/validate đúng.

## 90. Bài tập 23 — Thread safety

`final class Counter { int n; void inc(){n++;}}` có tự thread-safe không?

**Đáp án:** Không. Final ngăn subclass, không bảo đảm atomicity của `n++`.

## 91. Bài tập 24 — Resource-owning class

Object nắm socket và có lifecycle close/reopen/error.

**Đáp án:** Class với `AutoCloseable`/resource state rõ thường phù hợp hơn một record thuần data. Không chờ GC finalizer để close.

## 92. Bài tập 25 — Performance

“Đổi hết immutable class sang record vì record chắc chắn nhanh hơn” đúng không?

**Đáp án:** Không. Record không mang bảo đảm performance chung; chọn semantics trước và benchmark nếu thực sự cần.

## 93. Bài tập 26 — API compatibility

Đổi `class User { String getName(); }` sang `record User(String name)` có hoàn toàn source-compatible không?

**Đáp án:** Không mặc nhiên. Record sinh accessor `name()` chứ không tự cung cấp `getName()` và có finality/constructor/serialization khác. Cần giữ API hoặc migration rõ.

## 94. Bài tập 27 — Mutable snapshot

Entity state thay đổi, record snapshot đã tạo có nên tự cập nhật không?

**Đáp án:** Không nếu snapshot chứa primitive/immutable value copies đúng; snapshot mô tả trạng thái tại thời điểm xây.

## 95. Bài tập 28 — Stable enum code

Enum có `code="P"` cho PAID và constant bị đổi vị trí. Điều gì còn ổn định?

**Đáp án:** Explicit code P vẫn ổn định nếu developer giữ contract. Ordinal có thể đổi; `name()` có thể đổi nếu đổi tên source.

## 96. Bài tập 29 — Tập giá trị động

Một bảng trạng thái workflow được cấu hình theo từng khách hàng/tenant.

**Đáp án:** Không mặc định dùng enum cho mọi trạng thái động; có thể dùng data-driven immutable status records/classes và validation từ configuration. Enum có thể dùng cho những category ở mức hệ thống vẫn cố định.

## 97. Bài tập 30 — Quyết định tổng hợp

Một hệ thống bán hàng cần: Order thay đổi, OrderStatus cố định, Money value, OrderResponse gửi API.

**Đáp án:** Mutable class Order cho lifecycle; enum OrderStatus cho ký hiệu trạng thái; immutable Money record/class cho tiền; record OrderResponse cho snapshot API nếu serialization framework hỗ trợ và các components an toàn.

## 98. Đúng/Sai tổng hợp

1. Mutable class luôn thiết kế tệ hơn record.
2. `final class` không tự ngăn mọi mutation.
3. Record có private final fields cho components.
4. Record tự deep-copy arrays và lists.
5. Record-generated equals của array component deep-compare elements.
6. `List.copyOf` là shallow snapshot đối với mutable elements.
7. Enum phù hợp với một tập named constants định nghĩa trước.
8. Enum constant có thể bị sửa trạng thái nếu developer khai báo mutable field.
9. Enum ordinal là mã database bền vững khi reorder.
10. Một entity mutable có thể chứa field enum status.
11. Immutable record có thể trả instance mới cho state transition.
12. `HashMap` key có hashCode thay đổi là thiết kế an toàn.
13. Record luôn nhanh hơn class tự viết trên mọi JVM.
14. Sealed interface + record variants có thể mô hình nhiều dạng payload.
15. Java 17 `instanceof` pattern matching là tính năng chuẩn.
16. Java 17 pattern matching switch trên sealed variants hoạt động không preview.
17. Hai record Points cùng primitive components thường equals true.
18. `BigDecimal("1.0")` và `BigDecimal("1.00")` equals true.
19. Builder có thể mutable nhưng kết quả là immutable.
20. Lựa chọn type nên theo domain identity/value/lifecycle contract.

**Đáp án:** 1 sai; 2 đúng; 3 đúng; 4 sai; 5 sai; 6 đúng; 7 đúng; 8 đúng; 9 sai; 10 đúng; 11 đúng; 12 sai; 13 sai; 14 đúng; 15 đúng; 16 sai; 17 đúng; 18 sai; 19 đúng; 20 đúng.

## 99. Công thức ra quyết định ngắn gọn

- **“Một vật thể có danh tính và tiến trình thay đổi?”** → mutable class có encapsulation/invariants và ownership.
- **“Một giá trị không thay đổi, representation cần che?”** → immutable class thủ công.
- **“Một cụm giá trị có components rõ, equality theo chúng, không muốn boilerplate?”** → record, kèm validation/defensive copy nếu cần.
- **“Một tập hằng hữu hạn từ source code?”** → enum, với stable code cho external data.
- **“Một tập loại có payload khác nhau?”** → sealed interface + record/final variants.
- **“Một process có cả entities, values và statuses?”** → kết hợp nhiều lựa chọn; không ép tất cả cùng một construction.

**Quan trọng nhất:** kiểu dữ liệu phải phản ánh **điều chương trình cam kết với người dùng API**. Cú pháp ngắn và default generated behavior là phương tiện, không phải đích đến.

## 100. Tài liệu Java SE 17 chính thức

- **JLS `8.10 — Record Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- **JLS `8.10.4 — Record Constructors**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4
- **JLS `8.9 — Enum Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.1 — Class Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1
- **JLS `8.1.1.2 — Sealed and Final Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **Java SE 17 `java.lang.Record` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
- **Java SE 17 `java.lang.Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
- **Java SE 17 `List.copyOf` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **Java SE 17 `EnumSet` / `EnumMap` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- **Java SE 17 `BigDecimal` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
